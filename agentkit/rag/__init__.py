"""Ponto de extensão para RAG (fase 2).

A configuração já existe em `agentkit.yaml > rag`. O plano de implementação:

1. `Indexer`  — lê `rag.sources`, divide em chunks (por título/função), gera embeddings
   (`rag.embedding_model`) e grava no `VectorStore` com metadados (arquivo, seção, hash).
   Reindexa só arquivos cujo hash mudou.
2. `VectorStore` — implementações para chroma (local), pgvector e qdrant, todas com a
   mesma interface abaixo. Busca híbrida (vetorial + BM25) e reranking opcional.
3. Servidor MCP `agentkit-rag` com a ferramenta `search_docs(query, top_k, filters)`,
   registrado no `.mcp.json` do projeto pelo instalador quando `rag.enabled` for true.
   Assim qualquer agente (architect, code-writer, revisores) passa a consultar a base.
4. Comando `agentkit rag index|search|eval` e um conjunto de perguntas de avaliação.
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


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
