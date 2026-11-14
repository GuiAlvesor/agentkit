"""Testes do RAG: chunking, BM25, indexação incremental, busca híbrida, MCP e instalador.

Nenhum teste chama API externa: os vetores vêm de um embedder falso e determinístico.
"""
import asyncio
import hashlib
import json
import math

import pytest

from agentkit import config as cfgmod
from agentkit.installer import install, parse_agent_markdown, plan
from agentkit.rag.bm25 import BM25, tokenize
from agentkit.rag.chunking import chunk_file, split_windows
from agentkit.rag.index import Searcher, index_project, search, status


class FakeEmbedder:
    """Saco de palavras com hashing em 64 dimensões: textos com as mesmas palavras ficam próximos."""
    id = "fake:64"

    def __init__(self):
        self.calls = 0

    def _vec(self, text):
        v = [0.0] * 64
        for tok in tokenize(text):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        self.calls += len(texts)
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture
def docs_project(tmp_path):
    (tmp_path / "requisitos").mkdir()
    (tmp_path / "requisitos" / "00-visao.md").write_text(
        "# Visão\n\n## Pagamentos\nO cliente paga com Pix ou cartão de crédito. Estorno em até 7 dias.\n\n"
        "## Entregas\nA entrega é feita por transportadora; o frete é calculado pelo CEP.\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "arquitetura.md").write_text(
        "# Arquitetura\n\n## Banco de dados\nUsamos PostgreSQL com migrações Alembic.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Loja\nProjeto de exemplo.\n", encoding="utf-8")
    cfg = cfgmod.normalize({"project": {"name": "loja"}})
    cfg["rag"]["embedder"] = "none"
    return tmp_path, cfg


# ---------------------------------------------------------------- chunking e BM25
def test_chunking_markdown_por_titulo():
    text = "# Guia\nintro\n\n## Instalar\npip install\n\n```bash\n# comentário, não é título\n```\n\n## Usar\nrode"
    chunks = chunk_file("docs/guia.md", text)
    sections = [c.metadata["section"] for c in chunks]
    assert sections == ["Guia", "Guia > Instalar", "Guia > Usar"]
    assert chunks[1].text.startswith("[docs/guia.md · Guia > Instalar]")
    assert "# comentário" in chunks[1].text


def test_chunking_python_por_funcao():
    code = "import os\n\nX = 1\n\ndef soma(a, b):\n    return a + b\n\nclass Conta:\n    pass\n"
    sections = [c.metadata["section"] for c in chunk_file("app/m.py", code)]
    assert sections == ["módulo", "def soma", "class Conta"]


def test_split_windows_respeita_tamanho_e_sobreposicao():
    text = "\n\n".join(f"parágrafo {i} " + "x" * 80 for i in range(20))
    parts = split_windows(text, 300, 60)
    assert len(parts) > 3 and all(len(p) <= 300 for p in parts)


def test_tokenize_sem_acentos_e_camelcase():
    toks = tokenize("Configuração do getUserName e max_files_per_change")
    assert "configuracao" in toks and "user" in toks and "name" in toks
    assert "max_files_per_change" in toks and "files" in toks and "do" not in toks


def test_bm25_ranqueia_documento_certo():
    bm = BM25(["o frete é calculado pelo CEP", "pagamento com Pix", "banco PostgreSQL"])
    assert bm.top("como calcular o frete", 1)[0][0] == 0


# ---------------------------------------------------------------- indexação e busca
def test_indexacao_incremental(docs_project):
    root, cfg = docs_project
    emb = FakeEmbedder()
    r1 = index_project(root, cfg, embedder=emb, log=None)
    assert r1["added"] == 3 and r1["full"]
    first_calls = emb.calls

    r2 = index_project(root, cfg, embedder=emb, log=None)
    assert r2["unchanged"] == 3 and emb.calls == first_calls  # nada reprocessado

    (root / "docs" / "arquitetura.md").write_text("# Arquitetura\n\n## Fila\nUsamos RabbitMQ.\n", encoding="utf-8")
    (root / "README.md").unlink()
    assert status(root, cfg)["stale"]
    r3 = index_project(root, cfg, embedder=emb, log=None)
    assert (r3["updated"], r3["removed"], r3["unchanged"]) == (1, 1, 1)
    assert not status(root, cfg)["stale"]

    hits = search(root, cfg, "RabbitMQ", embedder=emb)
    assert hits[0].chunk.source == "docs/arquitetura.md"
    # o conteúdo antigo saiu do índice
    assert all("PostgreSQL" not in h.chunk.text for h in search(root, cfg, "PostgreSQL Alembic", 10, embedder=emb))


def test_trocar_embedder_reindexa_tudo(docs_project):
    root, cfg = docs_project
    index_project(root, cfg, embedder=None, log=None)
    rep = index_project(root, cfg, embedder=FakeEmbedder(), log=None)
    assert rep["full"] and rep["added"] == 3


def test_busca_hibrida_e_filtro_por_arquivo(docs_project):
    root, cfg = docs_project
    emb = FakeEmbedder()
    index_project(root, cfg, embedder=emb, log=None)
    s = Searcher(root, cfg, embedder=emb)
    assert s._load() is None and s._store is not None  # vetores em uso
    top = s.search("estorno do pagamento com cartão", 2)
    assert top[0].chunk.metadata["section"] == "Visão > Pagamentos"
    only_docs = s.search("banco de dados", 5, source_glob="docs/*")
    assert only_docs and all(h.chunk.source.startswith("docs/") for h in only_docs)


def test_busca_so_bm25_sem_embedder(docs_project):
    root, cfg = docs_project
    index_project(root, cfg, embedder=None, log=None)
    hits = search(root, cfg, "frete CEP", embedder=None)
    assert hits[0].chunk.metadata["section"] == "Visão > Entregas"


def test_avaliacao_hit_rate(docs_project):
    from agentkit.rag.evaluate import evaluate
    root, cfg = docs_project
    index_project(root, cfg, embedder=None, log=None)
    (root / "requisitos" / "rag-eval.yaml").write_text(
        "- pergunta: como é calculado o frete?\n  esperado: requisitos/00-visao.md\n"
        "- pergunta: qual banco de dados usamos?\n  esperado: docs/*.md\n", encoding="utf-8")
    res = evaluate(root, cfg, root / "requisitos" / "rag-eval.yaml", embedder=None)
    assert res["total"] == 2 and res["hit_rate"] == 1.0 and res["mrr"] > 0.5


# ---------------------------------------------------------------- MCP
def test_servidor_mcp_search_docs(docs_project):
    from agentkit.rag.mcp_server import build_server
    root, cfg = docs_project
    index_project(root, cfg, embedder=None, log=None)
    server = build_server(root, cfg, embedder=None)

    async def call():
        tools = {t.name for t in await server.list_tools()}
        result = await server.call_tool("search_docs", {"query": "Pix cartão"})
        return tools, result

    tools, result = asyncio.run(call())
    assert {"search_docs", "list_sources"} <= tools
    assert "requisitos/00-visao.md" in json.dumps(result, default=str, ensure_ascii=False)


# ---------------------------------------------------------------- instalador
def test_instalador_registra_mcp_e_libera_ferramenta(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"outro": {"command": "x"}}}), encoding="utf-8")
    cfg = cfgmod.normalize({"project": {"name": "p"}})

    install(tmp_path, cfg)  # RAG desligado: .mcp.json intacto, sem a ferramenta
    assert "agentkit-rag" not in json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    meta, _ = parse_agent_markdown((tmp_path / ".claude/agents/architect.md").read_text(encoding="utf-8"))
    assert "search_docs" not in meta["tools"]

    cfg["rag"]["enabled"] = True
    install(tmp_path, cfg)
    servers = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["outro"] == {"command": "x"}
    assert servers["agentkit-rag"] == {"command": "agentkit", "args": ["rag", "serve"]}
    for name in ("architect", "code-writer", "requirements-analyst"):
        meta, body = parse_agent_markdown((tmp_path / f".claude/agents/{name}.md").read_text(encoding="utf-8"))
        assert "mcp__agentkit-rag__search_docs" in meta["tools"] and "search_docs" in body
    meta, _ = parse_agent_markdown((tmp_path / ".claude/agents/guardrail.md").read_text(encoding="utf-8"))
    assert "search_docs" not in meta["tools"]
    assert ".agentkit/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert all(i["status"] != "mesclar" for i in plan(tmp_path, cfg) if i["path"] == ".mcp.json")

    cfg["rag"]["enabled"] = False
    install(tmp_path, cfg)
    assert json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"] == {"outro": {"command": "x"}}


def test_instalador_remove_mcp_json_que_era_so_do_agentkit(tmp_path):
    cfg = cfgmod.normalize({"project": {"name": "p"}})
    cfg["rag"]["enabled"] = True
    install(tmp_path, cfg)
    assert (tmp_path / ".mcp.json").exists()
    cfg["rag"]["enabled"] = False
    install(tmp_path, cfg)
    assert not (tmp_path / ".mcp.json").exists()


def test_migracao_config_v1():
    cfg = cfgmod.normalize({"version": 1, "rag": {"provider": "chroma", "sources": ["docs/**/*.md", "README.md"]}})
    assert cfg["version"] == 2 and cfg["rag"]["provider"] == "local"
    assert cfg["rag"]["sources"][0] == "requisitos/**/*.md"
    kept = cfgmod.normalize({"version": 2, "rag": {"provider": "chroma"}})
    assert kept["rag"]["provider"] == "chroma"


def test_runner_passa_servidor_mcp(tmp_path):
    from agentkit.runner import _options
    cfg = cfgmod.normalize({"project": {"name": "p"}})
    cfg["rag"]["enabled"] = True
    opts = _options(tmp_path, cfg, model="sonnet", tools=["Read"], append="")
    assert opts.mcp_servers["agentkit-rag"]["args"] == ["rag", "serve"]


def test_busca_vetorial_com_erro_cai_para_bm25(docs_project):
    root, cfg = docs_project

    class Quebrado(FakeEmbedder):
        def embed_query(self, text):
            raise ConnectionError("sem rede")

    emb = Quebrado()
    index_project(root, cfg, embedder=emb, log=None)
    hits = Searcher(root, cfg, embedder=emb).search("frete CEP")
    assert hits and hits[0].chunk.metadata["section"] == "Visão > Entregas"
