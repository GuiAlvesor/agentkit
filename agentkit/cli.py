"""Linha de comando do AgentKit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import config as cfgmod
from .detect import detect
from .installer import install, plan


def config_from_detection(path: str) -> dict:
    d = detect(path)
    cfg = cfgmod.normalize({})
    cfg["project"].update({k: d[k] for k in ("name", "language", "frameworks", "base_branch")})
    cfg["commands"].update({k: v for k, v in d["commands"].items() if v})
    return cfg


def cmd_init(a):
    existing = cfgmod.load(a.path)
    cfg = existing if existing and not a.redetect else config_from_detection(a.path)
    if a.dry_run:
        for item in plan(a.path, cfg):
            print(f"  {item['status']:<16} {item['path']}")
        return
    rep = install(a.path, cfg, force=a.force)
    print(f"✔ AgentKit instalado em {Path(a.path).resolve()}")
    for key, label in (("written", "gravados"), ("unchanged", "sem mudança"),
                       ("conflicts", "conflitos (veja *.agentkit-new)"), ("removed", "removidos")):
        if rep[key]:
            print(f"  {label}: {len(rep[key])}")
            if key in ("conflicts", "removed"):
                for f in rep[key]:
                    print(f"    - {f}")
    print("Próximo passo: revise o agentkit.yaml (ou rode `agentkit gui`) e abra o projeto no Claude Code.")


def cmd_detect(a):
    print(json.dumps(detect(a.path), indent=2, ensure_ascii=False))


def cmd_gui(a):
    from .server import serve
    serve(host=a.host, port=a.port, open_browser=not a.no_browser, start_path=a.path)


def cmd_run(a):
    from .runner import run_task
    run_task(a.project, " ".join(a.task), allow_deploy=a.allow_deploy)


def cmd_agent(a):
    from .runner import run_agent
    run_agent(a.project, a.name, " ".join(a.prompt))


def cmd_review(a):
    from .runner import review
    body = review(a.project, a.base, a.output)
    if not a.output:
        print(body)
    if a.fail_on_block and "GUARDRAIL: BLOQUEIA" in body:
        sys.exit(2)


def cmd_release(a):
    from .runner import release
    release(a.project, a.range, a.output)


def cmd_doctor(a):
    from .doctor import main as doctor_main
    sys.exit(doctor_main(Path(a.path).resolve()))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # console do Windows (cp1252) e emojis
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="agentkit", description="Kit portátil de agentes para Claude Code e Agent SDK")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="detecta a stack e instala/atualiza os agentes num projeto")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--redetect", action="store_true", help="ignora o agentkit.yaml existente e detecta de novo")
    s.add_argument("--force", action="store_true", help="sobrescreve arquivos editados à mão")
    s.add_argument("--dry-run", action="store_true", help="só mostra o que mudaria")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("install", help="reaplica o agentkit.yaml do projeto (após editar à mão)")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_init, redetect=False)

    s = sub.add_parser("detect", help="mostra o que foi detectado no diretório")
    s.add_argument("path", nargs="?", default=".")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("gui", help="abre a interface de configuração no navegador")
    s.add_argument("path", nargs="?", default=None)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_gui)

    s = sub.add_parser("run", help="orquestrador completo via Agent SDK")
    s.add_argument("task", nargs="+")
    s.add_argument("-C", "--project", default=".")
    s.add_argument("--allow-deploy", action="store_true", help="libera o agente deployer nesta execução")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("agent", help="executa um agente específico via Agent SDK")
    s.add_argument("name")
    s.add_argument("prompt", nargs="+")
    s.add_argument("-C", "--project", default=".")
    s.set_defaults(func=cmd_agent)

    s = sub.add_parser("review", help="revisão de PR (pr-reviewer + guardrail), ideal para CI")
    s.add_argument("-C", "--project", default=".")
    s.add_argument("--base", default=None, help="ref base, ex.: origin/main")
    s.add_argument("--output", "-o", default=None)
    s.add_argument("--fail-on-block", action="store_true", help="sai com código 2 se o guardrail bloquear")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("release", help="resumo da release via release-summary")
    s.add_argument("range", nargs="?", default=None, help="ex.: v1.2.0..HEAD")
    s.add_argument("-C", "--project", default=".")
    s.add_argument("--output", "-o", default=None)
    s.set_defaults(func=cmd_release)

    s = sub.add_parser("doctor", help="verifica se o ambiente está pronto (Python, git, Claude Code, ANTHROPIC_API_KEY, pacote)")
    s.add_argument("path", nargs="?", default=".", help="projeto a inspecionar (padrão: diretório atual)")
    s.set_defaults(func=cmd_doctor)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
