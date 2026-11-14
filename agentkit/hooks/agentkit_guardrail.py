#!/usr/bin/env python3
"""Guardrail determinístico do AgentKit (hook PreToolUse do Claude Code / Agent SDK).

Roda ANTES de cada uso de Bash, Write, Edit e MultiEdit e pode:
  - negar (deny): comandos perigosos, escrita em arquivos protegidos, segredos no conteúdo;
  - pedir confirmação (ask): comandos sensíveis como push, deploy, publish.

Só usa a biblioteca padrão, para funcionar em qualquer projeto.
Configuração: .claude/agentkit/guardrails.json (gerado pelo AgentKit).
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path

SECRET_PATTERNS = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "chave privada": r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    "token do GitHub": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "token do Slack": r"xox[abposr]-[A-Za-z0-9-]{10,}",
    "chave de API (sk-)": r"\bsk-(ant-|proj-|live_)?[A-Za-z0-9_\-]{20,}",
    "chave do Google": r"AIza[0-9A-Za-z_\-]{35}",
    "string de conexão com senha": r"[a-z]+://[^\s:/@]+:[^\s@/]{3,}@[^\s]+",
    "segredo atribuído": r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"\s$<{]{8,}['\"]",
}
WRITE_HINT = re.compile(r"(>>?|\brm\b|\bmv\b|\bcp\b|\btee\b|\bsed\s+-i|\btruncate\b|\bchmod\b|\bunlink\b)")
# redirecionamentos que não escrevem em arquivo do projeto (descartar a saída, juntar stderr):
# sem isto, "ls .env 2>/dev/null" (só leitura) era negado como se alterasse o .env
HARMLESS_REDIRECT = re.compile(r"\d*>>?\s*(/dev/null|NUL|\$null)\b|\d*>&\d", re.I)


def project_dir() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]  # <proj>/.claude/hooks/este_arquivo


def load_config(root: Path) -> dict:
    path = root / ".claude" / "agentkit" / "guardrails.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def is_protected(path_str: str, root: Path, patterns: list[str]) -> str | None:
    if not path_str:
        return None
    p = Path(path_str)
    try:
        rel = (p if p.is_absolute() else (root / p)).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = p.as_posix()
    base = p.name
    for pat in patterns:
        simple = pat.replace("**/", "")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, simple) or fnmatch.fnmatch(base, simple):
            return pat
    return None


def find_secret(text: str) -> str | None:
    for label, pattern in SECRET_PATTERNS.items():
        if re.search(pattern, text or ""):
            return label
    return None


def log(root: Path, decision: str, tool: str, reason: str) -> None:
    try:
        logfile = root / ".claude" / "agentkit" / "guardrail.log"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().isoformat(timespec="seconds")
        with logfile.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}\t{decision}\t{tool}\t{reason}\n")
    except OSError:
        pass


def decide(payload: dict, cfg: dict, root: Path) -> tuple[str, str] | None:
    tool = payload.get("tool_name", "")
    data = payload.get("tool_input", {}) or {}
    protected = cfg.get("protected_paths", [])

    if tool == "Bash":
        cmd = data.get("command", "")
        for pat in cfg.get("blocked_commands", []):
            if re.search(pat, cmd, re.I):
                return "deny", f"Comando bloqueado pela política do projeto (regra: {pat})."
        if WRITE_HINT.search(HARMLESS_REDIRECT.sub(" ", cmd)):
            try:
                tokens = shlex.split(cmd, posix=True)
            except ValueError:
                tokens = cmd.split()
            for tok in tokens:
                tok = tok.lstrip(">")
                hit = is_protected(tok, root, protected) if tok and not tok.startswith("-") else None
                if hit:
                    return "deny", f"O comando altera um caminho protegido ({tok}, regra {hit})."
        if cfg.get("scan_secrets", True) and find_secret(cmd):
            return "deny", "O comando contém o que parece ser um segredo. Use variáveis de ambiente."
        for pat in cfg.get("confirm_commands", []):
            if re.search(pat, cmd, re.I):
                return "ask", f"Comando sensível; requer confirmação humana (regra: {pat})."
        return None

    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = data.get("file_path") or data.get("notebook_path") or ""
        hit = is_protected(path, root, protected)
        if hit:
            return "deny", f"{path} é um arquivo protegido (regra {hit}). Altere-o manualmente se for necessário."
        if cfg.get("scan_secrets", True):
            parts = [data.get("content", ""), data.get("new_string", ""), data.get("new_source", "")]
            parts += [e.get("new_string", "") for e in data.get("edits", []) or []]
            label = find_secret("\n".join(p for p in parts if p))
            if label:
                return "deny", f"O conteúdo parece conter um segredo ({label}). Use variáveis de ambiente."
    return None


def main() -> int:
    try:  # bytes + UTF-8 explícito: no Windows o stdin padrão é cp1252
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return 0  # entrada inesperada: não bloqueia, mas também não decide nada
    root = project_dir()
    cfg = load_config(root)
    result = decide(payload, cfg, root)
    if not result:
        return 0
    decision, reason = result
    log(root, decision, payload.get("tool_name", ""), reason)
    out = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[AgentKit guardrail] {reason}",
        }
    }, ensure_ascii=False)
    sys.stdout.buffer.write(out.encode("utf-8") + b"\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
