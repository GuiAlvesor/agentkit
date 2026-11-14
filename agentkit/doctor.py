"""Verifica se o ambiente está pronto para usar o AgentKit.

Checa: Python >= 3.10, git, Claude Code CLI (opcional), ANTHROPIC_API_KEY
(opcional), pacote agentkit instalado e, se o diretório atual é um projeto
já instalado, a presença dos arquivos gerados.

Imprime o resultado colorido no terminal e devolve exit code 0 (tudo ok ou
só avisos) ou 1 (há impedimento). Pode ser usado pós-instalação ou pelos
scripts de setup para validar o ambiente antes de prosseguir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# Códigos ANSI; desligados quando a saída não é um terminal interativo.
def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def _green(t: str) -> str: return _c("1;32", t)
def _red(t: str) -> str: return _c("1;31", t)
def _yellow(t: str) -> str: return _c("1;33", t)
def _cyan(t: str) -> str: return _c("1;36", t)
def _dim(t: str) -> str: return _c("2", t)


@dataclass
class Check:
    """Resultado de uma checagem.

    level: "ok" (verde), "warn" (amarelo, não bloqueia) ou "fail" (vermelho, bloqueia).
    """
    name: str
    level: str
    detail: str = ""
    hint: str = ""


def _python_version() -> Check:
    v = sys.version_info
    label = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < (3, 10):
        return Check("Python >= 3.10", "fail", label,
                     "Instale Python 3.10+ (recomendado 3.12). Veja https://www.python.org/downloads/")
    return Check("Python >= 3.10", "ok", label)


def _git() -> Check:
    path = shutil.which("git")
    if not path:
        return Check("git no PATH", "fail", "",
                     "Instale o git: https://git-scm.com/downloads")
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=5)
        return Check("git no PATH", "ok", out.stdout.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        return Check("git no PATH", "warn", f"encontrado mas falhou: {exc}")


def _claude_cli() -> Check:
    path = shutil.which("claude")
    if not path:
        return Check("Claude Code CLI", "warn", "não encontrado",
                     "Instale: npm install -g @anthropic-ai/claude-code "
                     "(ou use só o Agent SDK com ANTHROPIC_API_KEY)")
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10)
        return Check("Claude Code CLI", "ok", out.stdout.strip() or path)
    except (OSError, subprocess.SubprocessError):
        return Check("Claude Code CLI", "ok", path)


def _anthropic_key() -> Check:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Check("ANTHROPIC_API_KEY", "ok", "definida")
    return Check("ANTHROPIC_API_KEY", "warn", "não definida",
                 "Defina só se for usar o Agent SDK (CI/scripts). "
                 "Para uso interativo via Claude Code não é necessária.")


def _agentkit_installed() -> Check:
    try:
        import agentkit  # noqa: F401
        return Check("pacote agentkit instalado", "ok", getattr(agentkit, "__version__", ""))
    except ImportError:
        return Check("pacote agentkit instalado", "fail", "",
                     "Rode `pip install -e .` na raiz do repositório ou `.\\setup.ps1` / `./setup.sh`")


def _project_files(cwd: Path) -> list[Check]:
    """Se o cwd é um projeto já instalado pelo AgentKit, verifica os arquivos gerados."""
    cfg = cwd / "agentkit.yaml"
    if not cfg.exists():
        return [Check("projeto instalado neste diretório", "warn", "sem agentkit.yaml",
                      f"Rode `agentkit init {cwd}` para instalar neste projeto.")]
    out = [Check("agentkit.yaml", "ok", str(cfg.relative_to(cwd)))]
    for rel in (".claude/agents", ".claude/hooks/agentkit_guardrail.py",
                ".claude/settings.json"):
        path = cwd / rel
        if path.exists():
            out.append(Check(rel, "ok"))
        else:
            out.append(Check(rel, "fail", "ausente",
                             "Rode `agentkit install` para regerar"))
    return out


def run_checks(cwd: Path | None = None) -> list[Check]:
    cwd = cwd or Path.cwd()
    checks = [
        _python_version(),
        _git(),
        _agentkit_installed(),
        _claude_cli(),
        _anthropic_key(),
    ]
    checks.extend(_project_files(cwd))
    return checks


_SYMBOLS = {
    "ok":   ("✓", _green),
    "warn": ("!", _yellow),
    "fail": ("✗", _red),
}


def render(checks: list[Check]) -> int:
    """Imprime os resultados e devolve exit code (0 = sem falhas, 1 = com falhas)."""
    print(_cyan("AgentKit · doctor"))
    print(_dim("─" * 60))
    width = max(len(c.name) for c in checks) + 2
    for c in checks:
        sym, color = _SYMBOLS[c.level]
        tail = f"  {_dim(c.detail)}" if c.detail else ""
        print(f"  {color(sym)}  {c.name:<{width}}{tail}")
        if c.hint and c.level != "ok":
            print(f"      {_dim('→ ' + c.hint)}")
    fails = [c for c in checks if c.level == "fail"]
    warns = [c for c in checks if c.level == "warn"]
    print(_dim("─" * 60))
    if fails:
        print(_red(f"{len(fails)} problema(s) encontrado(s). Resolva os itens acima e rode de novo."))
        return 1
    if warns:
        print(_yellow(f"{len(warns)} aviso(s). Nada impede o uso, mas vale olhar."))
    else:
        print(_green("Tudo pronto."))
    return 0


def main(cwd: Path | None = None) -> int:
    return render(run_checks(cwd))


if __name__ == "__main__":
    sys.exit(main())
