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
        if getattr(a, "scaffold", False) and not (Path(a.path) / cfg["kickoff"]["dir"]).exists():
            print(f"  {'novo':<16} {cfg['kickoff']['dir']}/ (modelo de requisitos)")
        return
    rep = install(a.path, cfg, force=a.force)
    print(f"✔ AgentKit instalado em {Path(a.path).resolve()}")
    if getattr(a, "scaffold", False):
        from .kickoff import scaffold
        created = scaffold(Path(a.path).resolve(), cfgmod.load(a.path))
        if created:
            print(f"  modelo de requisitos criado: {cfg['kickoff']['dir']}/ (preencha e rode /iniciar-projeto)")
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


def _project(path: str) -> tuple[Path, dict]:
    root = Path(path).expanduser().resolve()
    cfg = cfgmod.load(root)
    if cfg is None:
        raise SystemExit(f"{root} não tem agentkit.yaml. Rode `agentkit init {root}` antes.")
    return root, cfg


def cmd_requisitos(a):
    from .kickoff import scaffold
    root, cfg = _project(a.path)
    created = scaffold(root, cfg)
    if created:
        print("✔ Modelo de requisitos criado:")
        for f in created:
            print(f"  {f}")
        print("Preencha e rode /iniciar-projeto no Claude Code.")
    else:
        print(f"{cfg['kickoff']['dir']}/ já existe; nada foi alterado.")


def cmd_backlog(a):
    from .kickoff import backlog_path, load_backlog, progress
    root, cfg = _project(a.path)
    tasks = load_backlog(root, cfg)
    if tasks is None:
        print(f"Sem backlog ({backlog_path(root, cfg).relative_to(root).as_posix()}). Rode /iniciar-projeto no Claude Code.")
        return
    icons = {"pendente": "[ ]", "em andamento": "[~]", "feita": "[x]", "bloqueada": "[!]"}
    milestone = None
    for t in tasks:
        if t.milestone != milestone:
            milestone = t.milestone
            if milestone:
                print(f"\n{milestone}")
        deps = f"  (depende: {', '.join(t.depends)})" if t.depends else ""
        print(f"  {icons[t.status]} {t.id} · {t.title}{deps}")
    p = progress(tasks)
    print(f"\nProgresso: {p['feita']}/{p['total']} feitas · {p['em andamento']} em andamento · {p['bloqueada']} bloqueadas")
    print(f"Próxima: {p['proxima'] or '— (nenhuma disponível)'}")


def cmd_rag(a):
    from .rag import index as ragidx
    root, cfg = _project(a.project)
    if a.rag_cmd == "index":
        rep = ragidx.index_project(root, cfg, full=a.full)
        print(f"✔ Índice: {rep['added']} novos, {rep['updated']} alterados, {rep['removed']} removidos, "
              f"{rep['unchanged']} sem mudança · embedder: {rep['embedder']}")
    elif a.rag_cmd == "search":
        print(ragidx.format_hits(ragidx.search(root, cfg, " ".join(a.query), a.k, a.source)))
    elif a.rag_cmd == "status":
        from .rag.embedders import describe
        st = ragidx.status(root, cfg)
        print(f"RAG {'habilitado' if cfg['rag']['enabled'] else 'desabilitado'} · banco: {cfg['rag']['provider']} · "
              f"busca: {describe(cfg['rag'])}")
        print(f"Indexados: {st['indexed']} arquivos / {st['chunks']} trechos · pendentes: "
              f"{st['new']} novos, {st['changed']} alterados, {st['removed']} removidos")
        if st["stale"]:
            print("→ rode `agentkit rag index`")
    elif a.rag_cmd == "eval":
        from .rag.evaluate import evaluate, find_eval_file
        path = Path(a.file).resolve() if a.file else find_eval_file(root)
        if not path or not path.exists():
            raise SystemExit("Arquivo de avaliação não encontrado (crie requisitos/rag-eval.yaml; veja agentkit/rag/evaluate.py).")
        res = evaluate(root, cfg, path, a.k)
        for item in res["itens"]:
            mark = f"#{item['posicao']}" if item["posicao"] else "✗"
            print(f"  {mark:>3}  {item['pergunta']}  → esperado {item['esperado']}")
        print(f"\nhit@{res['k']}: {res['hit_rate']:.0%} · MRR: {res['mrr']:.2f} · {res['total']} perguntas")
    elif a.rag_cmd == "serve":
        from .rag.mcp_server import serve
        serve(root, cfg)


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
    s.add_argument("--sem-requisitos", dest="scaffold", action="store_false",
                   help="não cria a pasta de requisitos (requisitos/)")
    s.set_defaults(func=cmd_init, scaffold=True)

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

    s = sub.add_parser("requisitos", help="cria a pasta de requisitos com o modelo (início de projeto)")
    s.add_argument("path", nargs="?", default=".")
    s.set_defaults(func=cmd_requisitos)

    s = sub.add_parser("backlog", help="mostra o backlog (docs/plano/BACKLOG.md) e o progresso")
    s.add_argument("path", nargs="?", default=".")
    s.set_defaults(func=cmd_backlog)

    s = sub.add_parser("rag", help="RAG: indexar, buscar, avaliar e servidor MCP")
    rs = s.add_subparsers(dest="rag_cmd", required=True)
    r = rs.add_parser("index", help="indexa as fontes de rag.sources (incremental)")
    r.add_argument("--full", action="store_true", help="reindexa tudo do zero")
    r = rs.add_parser("search", help="busca na base")
    r.add_argument("query", nargs="+")
    r.add_argument("-k", type=int, default=None, help="quantos trechos (padrão: rag.top_k)")
    r.add_argument("--source", default=None, help='filtra por arquivo, ex.: "requisitos/*"')
    rs.add_parser("status", help="estado do índice e do embedder")
    r = rs.add_parser("eval", help="avalia a recuperação (hit@k e MRR)")
    r.add_argument("file", nargs="?", default=None)
    r.add_argument("-k", type=int, default=None)
    rs.add_parser("serve", help="servidor MCP stdio (usado pelo Claude Code via .mcp.json)")
    for r in rs.choices.values():
        r.add_argument("-C", "--project", default=".")
    s.set_defaults(func=cmd_rag)

    s = sub.add_parser("doctor", help="verifica se o ambiente está pronto (Python, git, Claude Code, ANTHROPIC_API_KEY, pacote)")
    s.add_argument("path", nargs="?", default=".", help="projeto a inspecionar (padrão: diretório atual)")
    s.set_defaults(func=cmd_doctor)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
