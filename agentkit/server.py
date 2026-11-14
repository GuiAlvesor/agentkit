"""Interface web local (FastAPI) para configurar o AgentKit em cada diretório."""
from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import __version__
from . import config as cfgmod
from .defaults import AGENTS, MODEL_OPTIONS
from .detect import detect
from .installer import install, plan, render_agent, render_claude_section

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="AgentKit", version=__version__)
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


@app.middleware("http")
async def only_local(request: Request, call_next):
    # protege contra DNS rebinding: a interface só atende chamadas locais
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Acesso permitido apenas via localhost."}, status_code=403)
    return await call_next(request)


class PathIn(BaseModel):
    path: str


class ConfigIn(BaseModel):
    path: str
    config: dict
    force: bool = False


class SearchIn(BaseModel):
    path: str
    config: dict
    query: str
    top_k: int | None = None


class PreviewIn(BaseModel):
    path: str
    config: dict
    file: str


def _dir(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise HTTPException(400, "Informe o caminho absoluto do diretório.")
    p = p.resolve()
    if not p.is_dir():
        raise HTTPException(404, f"Diretório não encontrado: {p}")
    return p


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/meta")
def meta():
    return {
        "version": __version__,
        "agents": AGENTS,
        "models": MODEL_OPTIONS,
        "defaults": cfgmod.default_config(),
        "recent": cfgmod.recent(),
        "home": str(Path.home()),
        "start_path": os.environ.get("AGENTKIT_START_PATH", ""),
    }


@app.get("/api/browse")
def browse(path: str = ""):
    base = Path(path).expanduser() if path else Path.home()
    try:
        base = base.resolve()
        dirs = sorted(
            (d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=lambda d: d.name.lower(),
        )[:300]
    except (OSError, PermissionError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "path": str(base),
        "parent": str(base.parent) if base.parent != base else None,
        "dirs": [{"name": d.name, "path": str(d), "is_project": any((d / m).exists() for m in (
            ".git", "package.json", "pyproject.toml", "go.mod", "Cargo.toml", "agentkit.yaml"))} for d in dirs],
    }


@app.post("/api/load")
def load(body: PathIn):
    root = _dir(body.path)
    detected = detect(root)
    existing = cfgmod.load(root)
    if existing:
        return {"config": existing, "detected": detected, "source": "agentkit.yaml"}
    cfg = cfgmod.normalize({})
    cfg["project"].update({k: detected[k] for k in ("name", "language", "frameworks", "base_branch")})
    cfg["commands"].update({k: v for k, v in detected["commands"].items() if v})
    return {"config": cfg, "detected": detected, "source": "detecção"}


@app.post("/api/plan")
def do_plan(body: ConfigIn):
    return {"files": plan(_dir(body.path), body.config)}


@app.post("/api/preview")
def preview(body: PreviewIn):
    cfg = cfgmod.normalize(body.config)
    if body.file == "CLAUDE.md":
        return {"content": render_claude_section(cfg)}
    if body.file in AGENTS and not AGENTS[body.file].get("main_thread"):
        return {"content": render_agent(body.file, cfg)}
    raise HTTPException(404, "Arquivo sem pré-visualização.")


@app.post("/api/install")
def do_install(body: ConfigIn):
    root = _dir(body.path)
    try:
        report = install(root, body.config, force=body.force)
    except OSError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"report": report, "config": cfgmod.load(root)}


# ---------------------------------------------------------------- RAG
@app.post("/api/rag/status")
def rag_status(body: ConfigIn):
    from .rag.embedders import describe
    from .rag.index import status

    cfg = cfgmod.normalize(body.config)
    return {"index": status(_dir(body.path), cfg), "search": describe(cfg["rag"])}


@app.post("/api/rag/index")
def rag_index(body: ConfigIn):
    from .rag.index import index_project

    try:
        return {"report": index_project(_dir(body.path), cfgmod.normalize(body.config), full=body.force, log=None)}
    except SystemExit as exc:  # embedder/provedor indisponível: mensagem já explica o que instalar
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rag/search")
def rag_search(body: SearchIn):
    from .rag.index import search

    try:
        hits = search(_dir(body.path), cfgmod.normalize(body.config), body.query, body.top_k)
    except SystemExit as exc:
        raise HTTPException(400, str(exc)) from exc
    def body(text: str) -> str:  # o cabeçalho [arquivo · seção] já aparece no título do resultado
        return text.split("\n", 1)[1] if text.startswith("[") and "\n" in text else text

    return {"hits": [{"source": h.chunk.source, "section": h.chunk.metadata.get("section", ""),
                      "score": h.score, "text": body(h.chunk.text)} for h in hits]}


# ---------------------------------------------------------------- início de projeto
@app.post("/api/kickoff/state")
def kickoff_state(body: ConfigIn):
    from .kickoff import state

    return state(_dir(body.path), cfgmod.normalize(body.config))


@app.post("/api/kickoff/scaffold")
def kickoff_scaffold(body: ConfigIn):
    from .kickoff import scaffold, state

    root, cfg = _dir(body.path), cfgmod.normalize(body.config)
    return {"created": scaffold(root, cfg), "state": state(root, cfg)}


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True, start_path: str | None = None):
    import uvicorn

    if start_path:
        os.environ["AGENTKIT_START_PATH"] = str(Path(start_path).expanduser().resolve())
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    print(f"AgentKit em {url}  (Ctrl+C para sair)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
