"""Testes do início de projeto: modelo de requisitos, backlog e comandos gerados."""
import yaml

from agentkit import config as cfgmod
from agentkit.cli import main
from agentkit.installer import install, parse_agent_markdown
from agentkit.kickoff import next_task, parse_backlog, progress, scaffold, state

BACKLOG = """# Backlog

## Marco 1 — MVP
- [x] T-001 · Esqueleto do projeto  (RNF-01) · depende: —
  - Aceite: testes rodando
- [~] T-002 · Cadastro de usuário  (RF-01, RF-02) · depende: T-001
- [ ] T-003 · Login  (RF-03) · depende: T-002
- [ ] T-004 · Página inicial · depende: T-001

## Marco 2
- [!] T-005 · Pagamentos  (RF-07) · depende: T-003
  - Bloqueio: falta escolher o gateway
"""


def test_parse_backlog():
    tasks = parse_backlog(BACKLOG)
    assert [t.id for t in tasks] == ["T-001", "T-002", "T-003", "T-004", "T-005"]
    t2 = tasks[1]
    assert t2.title == "Cadastro de usuário" and t2.status == "em andamento"
    assert t2.depends == ["T-001"] and t2.requirements == ["RF-01", "RF-02"]
    assert tasks[0].depends == [] and tasks[4].milestone == "Marco 2" and tasks[4].status == "bloqueada"


def test_proxima_tarefa_respeita_dependencias():
    tasks = parse_backlog(BACKLOG)
    assert next_task(tasks).id == "T-004"  # T-003 depende de T-002, que não está feita
    p = progress(tasks)
    assert (p["total"], p["feita"], p["em andamento"], p["bloqueada"]) == (5, 1, 1, 1)
    assert p["proxima"] == "T-004 · Página inicial"


def test_scaffold_cria_uma_vez_e_nao_sobrescreve(tmp_path):
    cfg = cfgmod.normalize({})
    created = scaffold(tmp_path, cfg)
    assert created == ["requisitos/00-visao.md", "requisitos/README.md"]
    assert state(tmp_path, cfg)["stage"] == "preencher requisitos"

    visao = tmp_path / "requisitos" / "00-visao.md"
    visao.write_text("# Visão\n\nUma loja online de roupas para o público jovem.\n"
                     "RF-01 o cliente se cadastra com e-mail e senha.\n"
                     "RF-02 o cliente compra e paga com Pix.\n", encoding="utf-8")
    assert scaffold(tmp_path, cfg) == []
    assert "loja online" in visao.read_text(encoding="utf-8")
    assert state(tmp_path, cfg)["stage"] == "rodar /iniciar-projeto"

    (tmp_path / "docs" / "plano").mkdir(parents=True)
    (tmp_path / "docs" / "plano" / "BACKLOG.md").write_text(BACKLOG, encoding="utf-8")
    st = state(tmp_path, cfg)
    assert st["stage"] == "rodar /proxima-tarefa" and st["backlog"]["total"] == 5


def test_instalacao_gera_comandos_e_analista(tmp_path):
    cfg = cfgmod.normalize({"project": {"name": "p"}})
    install(tmp_path, cfg)
    for cmd in ("iniciar-projeto", "proxima-tarefa"):
        text = (tmp_path / f".claude/commands/{cmd}.md").read_text(encoding="utf-8")
        meta, body = parse_agent_markdown(text)
        assert meta["description"] and "{{" not in body and "{%" not in body
        assert "docs/plano" in body
    meta, body = parse_agent_markdown((tmp_path / ".claude/agents/requirements-analyst.md").read_text(encoding="utf-8"))
    assert meta["name"] == "requirements-analyst" and "Write" in meta["tools"] and "Bash" not in meta["tools"]
    assert "requisitos/" in body
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "/iniciar-projeto" in claude_md and "/proxima-tarefa" in claude_md

    cfg["agents"]["requirements-analyst"]["enabled"] = False
    install(tmp_path, cfg)
    assert not (tmp_path / ".claude/commands/iniciar-projeto.md").exists()
    assert "/iniciar-projeto" not in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_commit_por_tarefa_configuravel(tmp_path):
    cfg = cfgmod.normalize({"project": {"name": "p"}})
    install(tmp_path, cfg)
    assert "Não faça commit" in (tmp_path / ".claude/commands/proxima-tarefa.md").read_text(encoding="utf-8")
    cfg["kickoff"]["commit_each_task"] = True
    install(tmp_path, cfg)
    assert "faça um commit" in (tmp_path / ".claude/commands/proxima-tarefa.md").read_text(encoding="utf-8")


def test_cli_init_cria_requisitos_e_backlog(tmp_path, capsys):
    main(["init", str(tmp_path)])
    assert (tmp_path / "requisitos" / "00-visao.md").exists()
    yaml.safe_load((tmp_path / "agentkit.yaml").read_text(encoding="utf-8"))
    main(["backlog", str(tmp_path)])
    assert "/iniciar-projeto" in capsys.readouterr().out

    other = tmp_path / "outro"
    other.mkdir()
    main(["init", str(other), "--sem-requisitos"])
    assert not (other / "requisitos").exists()
