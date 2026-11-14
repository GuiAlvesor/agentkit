"""RAG do AgentKit: indexa a documentação do projeto e a expõe aos agentes.

Módulos:
  chunking.py    divide arquivos por estrutura (títulos de Markdown, funções/classes Python)
  bm25.py        busca por palavras em Python puro (funciona sem chave nem dependência)
  embedders.py   Voyage (agentkit[rag]) ou fastembed local (agentkit[rag-local]); modo "auto"
  store.py       bancos vetoriais: local (SQLite, padrão), chroma, qdrant, pgvector
  index.py       catálogo incremental (hash por arquivo) e busca híbrida (BM25 + vetores, RRF)
  mcp_server.py  servidor MCP `agentkit-rag` com search_docs/list_sources para os agentes
  evaluate.py    hit@k e MRR a partir de um arquivo de perguntas

Uso: `agentkit rag index|search|status|eval|serve` ou `rag.enabled: true` no agentkit.yaml
(o instalador registra o servidor no .mcp.json e libera a ferramenta para os agentes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Hit:
    chunk: Chunk
    score: float


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    def search(self, embedding: list[float], top_k: int, filters: dict | None = None) -> list[Hit]: ...
    def delete_source(self, source: str) -> None: ...
    def clear(self) -> None: ...


class Embedder(Protocol):
    id: str
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def index_project(*args, **kwargs):
    from .index import index_project as _f
    return _f(*args, **kwargs)


def search(*args, **kwargs):
    from .index import search as _f
    return _f(*args, **kwargs)
