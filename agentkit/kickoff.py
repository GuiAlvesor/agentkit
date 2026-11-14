"""Início de projeto guiado: pasta de requisitos e backlog de tarefas.

Fluxo no projeto-alvo:
  requisitos/           o usuário escreve (o AgentKit cria o modelo uma única vez)
  /iniciar-projeto      requirements-analyst + architect geram docs/plano/{PERGUNTAS,ARQUITETURA,BACKLOG}.md
  /proxima-tarefa       executa uma tarefa do backlog com o fluxo de agentes e para

Este módulo cria o modelo e lê o BACKLOG.md (para `agentkit backlog`, a interface e o doctor).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates" / "requisitos"

# - [ ] T-003 · Cadastro de usuário  (RF-02) · depende: T-001, T-002
_TASK = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX~!])\]\s*(?P<id>T-\d+)\s*[·\-–:|]?\s*(?P<rest>.*)$")
_DEPS = re.compile(r"depende(?:\s+de)?\s*:\s*(?P<deps>[^·|]*)", re.I)
_REQS = re.compile(r"\b(R(?:N)?F-\d+)\b")
STATUS = {" ": "pendente", "~": "em andamento", "x": "feita", "!": "bloqueada"}


@dataclass
class Task:
    id: str
    title: str
    status: str
    depends: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    milestone: str = ""


def scaffold(root: Path, cfg: dict) -> list[str]:
    """Cria a pasta de requisitos com o modelo, se ela ainda não existir. Devolve o que foi criado."""
    folder = Path(root) / cfg["kickoff"]["dir"]
    if folder.exists():
        return []
    folder.mkdir(parents=True)
    created = []
    for tpl in sorted(TEMPLATES.glob("*.md")):
        (folder / tpl.name).write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")
        created.append((folder / tpl.name).relative_to(root).as_posix())
    return created


def parse_backlog(text: str) -> list[Task]:
    tasks: list[Task] = []
    milestone = ""
    for line in text.splitlines():
        if line.startswith("## "):
            milestone = line[3:].strip()
            continue
        m = _TASK.match(line)
        if not m:
            continue
        rest = m.group("rest")
        deps_m = _DEPS.search(rest)
        deps = re.findall(r"T-\d+", deps_m.group("deps")) if deps_m else []
        title = rest[: deps_m.start()] if deps_m else rest
        title = re.sub(r"\(\s*R(?:N)?F-[\d,\sRNF-]*\)", "", title)  # remove "(RF-01, RF-02)"
        title = title.strip(" ·|-–")
        tasks.append(Task(id=m.group("id"), title=title, status=STATUS[m.group("mark").lower()],
                          depends=deps, requirements=_REQS.findall(rest), milestone=milestone))
    return tasks


def backlog_path(root: Path, cfg: dict) -> Path:
    return Path(root) / cfg["kickoff"]["plan_dir"] / "BACKLOG.md"


def load_backlog(root: Path, cfg: dict) -> list[Task] | None:
    path = backlog_path(root, cfg)
    if not path.exists():
        return None
    from .installer import read_user_text
    return parse_backlog(read_user_text(path))


def next_task(tasks: list[Task]) -> Task | None:
    """Primeira tarefa pendente cujas dependências estão todas feitas."""
    done = {t.id for t in tasks if t.status == "feita"}
    for t in tasks:
        if t.status == "pendente" and all(d in done for d in t.depends):
            return t
    return None


def progress(tasks: list[Task]) -> dict:
    counts = {s: 0 for s in STATUS.values()}
    for t in tasks:
        counts[t.status] += 1
    nxt = next_task(tasks)
    return {"total": len(tasks), **counts, "proxima": f"{nxt.id} · {nxt.title}" if nxt else None}


def state(root: Path, cfg: dict) -> dict:
    """Resumo para a interface e o doctor: em que etapa do ciclo o projeto está."""
    root = Path(root)
    req_dir = root / cfg["kickoff"]["dir"]
    tasks = load_backlog(root, cfg)
    filled = req_dir.exists() and any(
        p.name != "README.md" and _filled(p) for p in req_dir.glob("**/*.md"))
    if tasks is None:
        stage = "sem requisitos" if not req_dir.exists() else ("preencher requisitos" if not filled else "rodar /iniciar-projeto")
        return {"stage": stage, "requirements_dir": cfg["kickoff"]["dir"], "backlog": None}
    p = progress(tasks)
    stage = "concluído" if p["total"] and p["feita"] == p["total"] else "rodar /proxima-tarefa"
    return {"stage": stage, "requirements_dir": cfg["kickoff"]["dir"], "backlog": p}


def _filled(path: Path) -> bool:
    """O arquivo tem conteúdo além do modelo? (ignora placeholders <...> e títulos)."""
    from .installer import read_user_text
    text = read_user_text(path)
    if path.name == "00-visao.md" and text == (TEMPLATES / "00-visao.md").read_text(encoding="utf-8"):
        return False
    lines = [re.sub(r"<[^>]*>", "", ln).strip(" -*|#>") for ln in text.splitlines()]
    return sum(1 for ln in lines if len(ln) > 15) >= 3
