"""Gera e instala os arquivos do AgentKit em um projeto.

Arquivos gerados no projeto-alvo:
  agentkit.yaml                         configuração (fonte da verdade, versionável)
  CLAUDE.md                             seção gerenciada entre marcadores; o resto é preservado
  .claude/agents/<agente>.md            um por agente habilitado
  .claude/commands/{ship,review-pr,release-notes,deploy,iniciar-projeto,proxima-tarefa}.md
  .claude/hooks/agentkit_guardrail.py   hook determinístico
  .claude/agentkit/guardrails.json      política lida pelo hook
  .claude/agentkit/manifest.json        hashes do que o AgentKit gerou
  .claude/settings.json                 mesclado: hook + modelo do orquestrador
  .mcp.json                             mesclado: servidor agentkit-rag (só com rag.enabled)
  .github/workflows/agentkit-review.yml (opcional)

Se você editou à mão um arquivo gerado, ele NÃO é sobrescrito: a versão nova
vai para <arquivo>.agentkit-new (a menos que use --force).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import config as cfgmod
from .defaults import AGENTS, RAG_AGENTS, RAG_TOOL

PKG = Path(__file__).parent
MANIFEST = ".claude/agentkit/manifest.json"
HOOK_REL = ".claude/hooks/agentkit_guardrail.py"
MARK_START = "<!-- agentkit:start (gerado pelo AgentKit; edite pelo agentkit.yaml) -->"
MARK_END = "<!-- agentkit:end -->"
MCP_FILE = ".mcp.json"
MCP_NAME = "agentkit-rag"
MARK_RE = re.compile(r"<!-- agentkit:start.*?-->.*?<!-- agentkit:end -->\n?", re.S)

_env = Environment(
    loader=FileSystemLoader(PKG / "templates"),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=False,
    lstrip_blocks=False,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_user_text(path: Path) -> str:
    """Lê um arquivo que o usuário pode ter salvo em qualquer editor.

    UTF-8 (com ou sem BOM) primeiro; se falhar, cp1252 (o "ANSI" do Windows em português).
    O AgentKit sempre regrava em UTF-8.
    """
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # bytes indefinidos no cp1252 (ex.: 0x81) viram "?"; aceitável para
        # arquivos de configuração do AgentKit, que são sempre regravados em UTF-8
        text = data.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n")


def enabled_agents(cfg: dict) -> dict[str, dict]:
    return {n: m for n, m in AGENTS.items() if cfg["agents"][n]["enabled"] and not m.get("main_thread")}


def _ctx(cfg: dict) -> dict:
    return {
        "p": cfg["project"], "c": cfg["commands"], "g": cfg["guardrails"],
        "ci": cfg["ci"], "rag": cfg["rag"], "k": cfg["kickoff"], "agents": cfg["agents"],
        "enabled": enabled_agents(cfg),
    }


def _tidy(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def agent_tools(name: str, cfg: dict) -> list[str]:
    """Ferramentas do agente; com o RAG ligado, os agentes que consultam ganham search_docs."""
    tools = list(AGENTS[name]["tools"])
    if cfg["rag"]["enabled"] and name in RAG_AGENTS:
        tools.append(RAG_TOOL)
    return tools


def render_agent(name: str, cfg: dict) -> str:
    acfg = cfg["agents"][name]
    tpl = _env.get_template(f"agents/{name}.md")
    text = _tidy(tpl.render(**_ctx(cfg), a=acfg, tools=", ".join(agent_tools(name, cfg)), model=acfg["model"]))
    # garante YAML válido no frontmatter (descrições podem conter ":")
    return re.sub(r"^description: (?!\")(.*)$",
                  lambda m: "description: " + json.dumps(m.group(1), ensure_ascii=False),
                  text, count=1, flags=re.M)


def render_orchestrator(cfg: dict) -> str:
    return _tidy(_env.get_template("orchestrator.md").render(**_ctx(cfg)))


def render_claude_section(cfg: dict) -> str:
    body = _env.get_template("CLAUDE.section.md").render(**_ctx(cfg), orchestrator=render_orchestrator(cfg))
    return f"{MARK_START}\n{_tidy(body)}{MARK_END}\n"


def guardrails_json(cfg: dict) -> str:
    g = cfg["guardrails"]
    keys = ("blocked_commands", "confirm_commands", "protected_paths", "scan_secrets", "max_files_per_change")
    return json.dumps({k: g[k] for k in keys}, indent=2, ensure_ascii=False) + "\n"


def render_files(cfg: dict) -> dict[str, str]:
    """Todos os arquivos 100% gerenciados (relativos à raiz do projeto)."""
    files: dict[str, str] = {}
    for name in enabled_agents(cfg):
        files[f".claude/agents/{name}.md"] = render_agent(name, cfg)

    ctx = _ctx(cfg)
    commands = {"ship": ("code-writer",), "review-pr": ("pr-reviewer",),
                "release-notes": ("release-summary",), "deploy": ("deployer",),
                "iniciar-projeto": ("requirements-analyst",),
                "proxima-tarefa": ("requirements-analyst", "code-writer")}
    for cmd, needs in commands.items():
        if all(n in ctx["enabled"] for n in needs):
            files[f".claude/commands/{cmd}.md"] = _tidy(_env.get_template(f"commands/{cmd}.md").render(**ctx))

    files[HOOK_REL] = (PKG / "hooks" / "agentkit_guardrail.py").read_text(encoding="utf-8")
    files[".claude/agentkit/guardrails.json"] = guardrails_json(cfg)

    if cfg["ci"]["github_actions"]:
        files[".github/workflows/agentkit-review.yml"] = _env.get_template("ci/agentkit-review.yml").render(**ctx)
    return files


# ---------------------------------------------------------------- settings.json
def _merge_settings(existing: dict, cfg: dict) -> dict:
    s = json.loads(json.dumps(existing))  # cópia
    py = cfg["guardrails"].get("python_cmd") or "python3"
    hook_cmd = f'{py} "$CLAUDE_PROJECT_DIR/{HOOK_REL}"'

    hooks = s.setdefault("hooks", {})
    pre = [m for m in hooks.get("PreToolUse", [])
           if not any("agentkit_guardrail" in h.get("command", "") for h in m.get("hooks", []))]
    pre.append({
        "matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [{"type": "command", "command": hook_cmd, "timeout": 10}],
    })
    hooks["PreToolUse"] = pre

    orch_model = cfg["agents"]["orchestrator"]["model"]
    if orch_model and orch_model != "inherit":
        s["model"] = orch_model
    elif s.get("model") in ("haiku", "sonnet", "opus"):
        s.pop("model")  # remove o que o AgentKit colocou antes

    deny = s.setdefault("permissions", {}).setdefault("deny", [])
    for pat in cfg["guardrails"]["protected_paths"]:
        for tool in ("Edit", "Write"):
            rule = f"{tool}({pat})"
            if rule not in deny:
                deny.append(rule)
    return s


# ---------------------------------------------------------------- .mcp.json
def mcp_entry(cfg: dict) -> dict:
    return {"command": cfg["rag"].get("mcp_command") or "agentkit", "args": ["rag", "serve"]}


def _merge_mcp(existing: dict, cfg: dict) -> dict:
    """Adiciona/remove só o servidor agentkit-rag; preserva os demais servidores."""
    s = json.loads(json.dumps(existing))
    servers = s.setdefault("mcpServers", {})
    if cfg["rag"]["enabled"]:
        servers[MCP_NAME] = mcp_entry(cfg)
    else:
        servers.pop(MCP_NAME, None)
    return s


def _mcp_status(root: Path, cfg: dict) -> str | None:
    path = root / MCP_FILE
    if not path.exists():
        return "novo" if cfg["rag"]["enabled"] else None
    try:
        existing = json.loads(read_user_text(path))
    except json.JSONDecodeError:
        return "mesclar"
    return "igual" if _merge_mcp(existing, cfg) == existing else "mesclar"


def _write_mcp(root: Path, cfg: dict, report: dict) -> None:
    path = root / MCP_FILE
    if not path.exists() and not cfg["rag"]["enabled"]:
        return
    try:
        existing = json.loads(read_user_text(path)) if path.exists() else {}
    except json.JSONDecodeError:
        existing = {}
        path.rename(path.with_suffix(".json.bak"))
    merged = _merge_mcp(existing, cfg)
    if merged == existing:
        report["unchanged"].append(MCP_FILE)
        return
    if not merged.get("mcpServers") and set(merged) == {"mcpServers"} and path.exists():
        path.unlink()  # só tinha o servidor do AgentKit
        report["removed"].append(MCP_FILE)
        return
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["written"].append(MCP_FILE)


# ---------------------------------------------------------------- plano/instalação
def _load_manifest(root: Path) -> dict:
    try:
        return json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _status(root: Path, rel: str, content: str, manifest: dict) -> str:
    path = root / rel
    if not path.exists():
        return "novo"
    current = read_user_text(path)
    if current == content:
        return "igual"
    if manifest.get(rel) == _sha(current):
        return "atualizar"  # não foi editado à mão desde a última geração
    return "conflito"


def plan(project: str | Path, cfg: dict) -> list[dict]:
    root = Path(project).expanduser().resolve()
    cfg = cfgmod.normalize(cfg)
    manifest = _load_manifest(root)
    files = render_files(cfg)
    out = [{"path": rel, "status": _status(root, rel, content, manifest)} for rel, content in files.items()]

    for rel in manifest:
        if rel not in files and (root / rel).exists():
            out.append({"path": rel, "status": "remover"})

    claude_md = root / "CLAUDE.md"
    section = render_claude_section(cfg)
    if not claude_md.exists():
        out.append({"path": "CLAUDE.md", "status": "novo"})
    else:
        text = read_user_text(claude_md)
        has = MARK_RE.search(text)
        out.append({"path": "CLAUDE.md", "status": "igual" if has and has.group(0) == section
                    else ("atualizar" if has else "adicionar seção")})
    out.append({"path": ".claude/settings.json", "status": "mesclar" if (root / ".claude/settings.json").exists() else "novo"})
    mcp = _mcp_status(root, cfg)
    if mcp:
        out.append({"path": MCP_FILE, "status": mcp})
    out.append({"path": cfgmod.CONFIG_FILE, "status": "atualizar" if (root / cfgmod.CONFIG_FILE).exists() else "novo"})
    return sorted(out, key=lambda i: i["path"])


def install(project: str | Path, cfg: dict, force: bool = False) -> dict:
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {root}")
    cfg = cfgmod.normalize(cfg)
    if not cfg["project"]["name"]:
        cfg["project"]["name"] = root.name

    manifest = _load_manifest(root)
    files = render_files(cfg)
    report = {"written": [], "unchanged": [], "conflicts": [], "removed": []}
    new_manifest: dict[str, str] = {}

    for rel, content in files.items():
        path = root / rel
        status = _status(root, rel, content, manifest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if status == "igual":
            report["unchanged"].append(rel)
        elif status == "conflito" and not force:
            alt = path.with_name(path.name + ".agentkit-new")
            alt.write_text(content, encoding="utf-8")
            report["conflicts"].append(rel)
            new_manifest[rel] = manifest.get(rel, "")
            continue
        else:
            path.write_text(content, encoding="utf-8")
            report["written"].append(rel)
        if rel.endswith(".py"):
            path.chmod(0o755)
        new_manifest[rel] = _sha(content)

    # remove arquivos de agentes desabilitados (apenas se não foram editados à mão)
    for rel, digest in manifest.items():
        if rel in files:
            continue
        path = root / rel
        if path.exists() and (force or _sha(read_user_text(path)) == digest):
            path.unlink()
            report["removed"].append(rel)

    # CLAUDE.md: só a seção gerenciada
    claude_md = root / "CLAUDE.md"
    section = render_claude_section(cfg)
    if claude_md.exists():
        text = read_user_text(claude_md)
        new = MARK_RE.sub(lambda _m: section, text, count=1) if MARK_RE.search(text) else text.rstrip() + "\n\n" + section
    else:
        text = None
        new = section
    if text is None or new != text:
        claude_md.write_text(new, encoding="utf-8")
        report["written"].append("CLAUDE.md")

    # settings.json mesclado
    settings_path = root / ".claude" / "settings.json"
    try:
        existing = json.loads(read_user_text(settings_path)) if settings_path.exists() else {}
    except json.JSONDecodeError:
        existing = {}
        settings_path.rename(settings_path.with_suffix(".json.bak"))
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(_merge_settings(existing, cfg), indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    report["written"].append(".claude/settings.json")
    _write_mcp(root, cfg, report)

    (root / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (root / MANIFEST).write_text(json.dumps(new_manifest, indent=2) + "\n", encoding="utf-8")
    _ensure_gitignore(root)
    cfgmod.save(root, cfg)
    report["written"].append(cfgmod.CONFIG_FILE)
    return report


def _ensure_gitignore(root: Path) -> None:
    gi = root / ".gitignore"
    lines = [".claude/agentkit/guardrail.log", "*.agentkit-new", ".claude/settings.local.json", ".agentkit/"]
    text = read_user_text(gi) if gi.exists() else ""
    missing = [line for line in lines if line not in text.splitlines()]
    if missing:
        sep = "" if not text or text.endswith("\n") else "\n"
        gi.write_text(text + sep + "\n# AgentKit\n" + "\n".join(missing) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- uso no runner
def parse_agent_markdown(text: str) -> tuple[dict, str]:
    """Separa o frontmatter YAML do corpo (prompt) de um arquivo de agente."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip()
