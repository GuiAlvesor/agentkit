"""Executa os agentes fora do Claude Code, com o Claude Agent SDK (CI, scripts, cron).

As definições vêm dos mesmos arquivos .claude/agents/*.md instalados no projeto,
então o comportamento é idêntico ao do Claude Code. O hook de guardrail e o
CLAUDE.md também são carregados (setting_sources=["project"]).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from . import config as cfgmod
from .defaults import AGENTS
from .installer import enabled_agents, parse_agent_markdown, render_agent, render_orchestrator


def _sdk():
    try:
        import claude_agent_sdk as sdk
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Instale o SDK: pip install claude-agent-sdk") from exc
    return sdk


def load_project(project: str | Path) -> tuple[Path, dict]:
    root = Path(project).expanduser().resolve()
    cfg = cfgmod.load(root)
    if cfg is None:
        raise SystemExit(f"{root} não tem agentkit.yaml. Rode `agentkit init {root}` ou use a interface.")
    return root, cfg


def agent_spec(root: Path, cfg: dict, name: str) -> dict:
    """Lê o agente instalado (respeita edições manuais); se não existir, renderiza."""
    path = root / ".claude" / "agents" / f"{name}.md"
    text = path.read_text(encoding="utf-8") if path.exists() else render_agent(name, cfg)
    meta, prompt = parse_agent_markdown(text)
    tools = meta.get("tools") or AGENTS[name]["tools"]
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]
    return {
        "description": meta.get("description", AGENTS[name]["summary"]),
        "prompt": prompt,
        "tools": tools,
        "model": meta.get("model") or cfg["agents"][name]["model"],
    }


def build_agents(root: Path, cfg: dict, allow_deploy: bool = False) -> dict:
    sdk = _sdk()
    agents = {}
    for name in enabled_agents(cfg):
        if name == "deployer" and not allow_deploy:
            continue
        s = agent_spec(root, cfg, name)
        agents[name] = sdk.AgentDefinition(
            description=s["description"], prompt=s["prompt"], tools=s["tools"],
            model=None if s["model"] == "inherit" else s["model"],
        )
    return agents


async def _stream(prompt: str, options, echo: bool = True) -> str:
    sdk = _sdk()
    final, cost = "", None
    async for msg in sdk.query(prompt=prompt, options=options):
        if isinstance(msg, sdk.AssistantMessage) and echo:
            for block in msg.content:
                if isinstance(block, sdk.TextBlock) and block.text.strip():
                    print(block.text, flush=True)
                elif isinstance(block, sdk.ToolUseBlock):
                    target = block.input.get("subagent_type") or block.input.get("command") or block.input.get("file_path") or ""
                    print(f"  ↳ {block.name} {str(target)[:100]}", file=sys.stderr, flush=True)
        elif isinstance(msg, sdk.ResultMessage):
            final = msg.result or final
            cost = msg.total_cost_usd
    if cost is not None:
        print(f"\n[custo estimado: US$ {cost:.4f}]", file=sys.stderr)
    return final


def _options(root: Path, cfg: dict, *, model: str, tools: list[str], append: str,
             agents: dict | None = None, permission_mode: str | None = None):
    sdk = _sdk()
    ci = cfg["ci"]
    return sdk.ClaudeAgentOptions(
        cwd=str(root),
        model=None if model == "inherit" else model,
        system_prompt={"type": "preset", "preset": "claude_code", "append": append},
        allowed_tools=tools,
        agents=agents or None,
        setting_sources=["project"],  # CLAUDE.md + .claude/settings.json (hook de guardrail)
        permission_mode=permission_mode or ci.get("permission_mode", "acceptEdits"),
        max_turns=ci.get("max_turns", 40),
        max_budget_usd=ci.get("max_budget_usd") or None,
    )


# ---------------------------------------------------------------- comandos de alto nível
def run_task(project: str | Path, task: str, allow_deploy: bool = False) -> str:
    """Orquestrador completo: delega para os subagentes habilitados."""
    root, cfg = load_project(project)
    agents = build_agents(root, cfg, allow_deploy)
    tools = ["Agent", "Task", "Read", "Grep", "Glob", "Bash", "TodoWrite"]
    opts = _options(root, cfg, model=cfg["agents"]["orchestrator"]["model"], tools=tools,
                    append=render_orchestrator(cfg), agents=agents)
    return asyncio.run(_stream(task, opts))


def run_agent(project: str | Path, name: str, prompt: str, echo: bool = True) -> str:
    """Executa um agente específico diretamente (sem orquestrador)."""
    root, cfg = load_project(project)
    if name not in AGENTS or AGENTS[name].get("main_thread"):
        raise SystemExit(f"Agente desconhecido: {name}. Opções: {', '.join(enabled_agents(cfg))}")
    if not cfg["agents"][name]["enabled"]:
        raise SystemExit(f"O agente {name} está desabilitado no agentkit.yaml.")
    s = agent_spec(root, cfg, name)
    opts = _options(root, cfg, model=s["model"], tools=s["tools"], append=s["prompt"])
    return asyncio.run(_stream(prompt, opts, echo))


def review(project: str | Path, base: str | None = None, output: str | None = None) -> str:
    """Revisão de PR para CI: pr-reviewer + guardrail em paralelo, um único Markdown."""
    root, cfg = load_project(project)
    base = base or cfg["project"]["base_branch"]
    jobs = []
    if cfg["agents"]["pr-reviewer"]["enabled"]:
        jobs.append(("pr-reviewer", f"Revise a branch atual contra `{base}` (use `git diff {base}...HEAD` e "
                                    f"`git log {base}..HEAD`). Responda só com o comentário em Markdown."))
    if cfg["agents"]["guardrail"]["enabled"]:
        jobs.append(("guardrail", f"Verifique as mudanças de `git diff {base}...HEAD` e os arquivos novos. "
                                  "Siga exatamente o formato de resposta."))
    if not jobs:
        raise SystemExit("Habilite pr-reviewer e/ou guardrail para usar `agentkit review`.")

    async def _all():
        tasks = []
        for name, prompt in jobs:
            s = agent_spec(root, cfg, name)
            opts = _options(root, cfg, model=s["model"], tools=s["tools"], append=s["prompt"],
                            permission_mode="default")
            tasks.append(_stream(prompt, opts, echo=False))
        return await asyncio.gather(*tasks)

    results = asyncio.run(_all())
    parts = []
    for (name, _), text in zip(jobs, results):
        parts.append(text.strip() if name == "pr-reviewer" else f"### 🛡️ Guardrail\n\n{text.strip()}")
    body = "\n\n---\n\n".join(parts) + "\n\n<sub>Gerado pelo AgentKit</sub>\n"
    if output:
        Path(output).write_text(body, encoding="utf-8")
    return body


def release(project: str | Path, rng: str | None = None, output: str | None = None) -> str:
    prompt = f"Resuma as mudanças em: {rng}." if rng else "Resuma as mudanças desde a última tag até HEAD."
    if output:
        prompt += f" Salve o resultado em `{output}`."
    return run_agent(project, "release-summary", prompt)
