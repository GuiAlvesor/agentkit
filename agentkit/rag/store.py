"""Bancos vetoriais com a mesma interface (`VectorStore`).

- `local` (padrão): SQLite da biblioteca padrão + cosseno em Python puro. Zero
  dependências; atende bem documentação de projeto (até dezenas de milhares de chunks).
- `chroma`, `qdrant`, `pgvector`: adaptadores para quem já usa esses bancos. Instale o
  extra correspondente (`pip install "agentkit[chroma]"` etc.).

Os textos e metadados ficam sempre no catálogo local (index.py); aqui só os vetores.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from array import array
from pathlib import Path

from . import Chunk, Hit


def _norm(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _expand(conn: str) -> str:
    """Permite `${VAR}` na conexão, para não gravar credenciais no agentkit.yaml."""
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), conn or "")


class LocalStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, source TEXT, vec BLOB)")
        self.db.execute("CREATE INDEX IF NOT EXISTS vectors_source ON vectors(source)")

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        rows = [(c.id, c.source, array("f", _norm(e)).tobytes()) for c, e in zip(chunks, embeddings)]
        self.db.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)", rows)
        self.db.commit()

    def search(self, embedding: list[float], top_k: int, filters: dict | None = None) -> list[Hit]:
        q = _norm(embedding)
        allowed = set(filters["ids"]) if filters and "ids" in filters else None
        scored = []
        for cid, source, blob in self.db.execute("SELECT id, source, vec FROM vectors"):
            if allowed is not None and cid not in allowed:
                continue
            v = array("f")
            v.frombytes(blob)
            scored.append((sum(a * b for a, b in zip(q, v)), cid, source))
        scored.sort(reverse=True)
        return [Hit(Chunk(id=cid, text="", source=src), s) for s, cid, src in scored[:top_k]]

    def delete_source(self, source: str) -> None:
        self.db.execute("DELETE FROM vectors WHERE source = ?", (source,))
        self.db.commit()

    def clear(self) -> None:
        self.db.execute("DELETE FROM vectors")
        self.db.commit()


class ChromaStore:
    def __init__(self, path: Path, collection: str):
        import chromadb  # dependência opcional

        self.client = chromadb.PersistentClient(path=str(path))
        self.name = collection
        self.col = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})

    def upsert(self, chunks, embeddings):
        self.col.upsert(ids=[c.id for c in chunks], embeddings=embeddings,
                        metadatas=[{"source": c.source} for c in chunks])

    def search(self, embedding, top_k, filters=None):
        res = self.col.query(query_embeddings=[embedding], n_results=top_k)
        return [Hit(Chunk(id=i, text="", source=m["source"]), 1 - d)
                for i, m, d in zip(res["ids"][0], res["metadatas"][0], res["distances"][0])]

    def delete_source(self, source):
        self.col.delete(where={"source": source})

    def clear(self):
        self.client.delete_collection(self.name)
        self.col = self.client.get_or_create_collection(self.name, metadata={"hnsw:space": "cosine"})


class QdrantStore:
    def __init__(self, url: str, collection: str):
        from qdrant_client import QdrantClient  # dependência opcional

        self.client = QdrantClient(url=url or "http://localhost:6333", api_key=os.environ.get("QDRANT_API_KEY"))
        self.name = collection

    def _ensure(self, dim: int):
        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(self.name):
            self.client.create_collection(self.name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    @staticmethod
    def _pid(cid: str) -> str:
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_URL, cid))

    def upsert(self, chunks, embeddings):
        from qdrant_client.models import PointStruct

        if not chunks:
            return
        self._ensure(len(embeddings[0]))
        self.client.upsert(self.name, points=[
            PointStruct(id=self._pid(c.id), vector=e, payload={"cid": c.id, "source": c.source})
            for c, e in zip(chunks, embeddings)])

    def search(self, embedding, top_k, filters=None):
        if not self.client.collection_exists(self.name):
            return []
        res = self.client.query_points(self.name, query=embedding, limit=top_k).points
        return [Hit(Chunk(id=p.payload["cid"], text="", source=p.payload["source"]), p.score) for p in res]

    def delete_source(self, source):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if self.client.collection_exists(self.name):
            self.client.delete(self.name, points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source))]))

    def clear(self):
        if self.client.collection_exists(self.name):
            self.client.delete_collection(self.name)


class PgVectorStore:
    def __init__(self, dsn: str, collection: str):
        import psycopg  # dependência opcional

        if not dsn:
            raise SystemExit("RAG: pgvector exige rag.connection (ex.: ${DATABASE_URL}).")
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.table = re.sub(r"\W", "_", f"agentkit_{collection}").lower()
        self.dim: int | None = None

    def _ensure(self, dim: int):
        if self.dim == dim:
            return
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {self.table} "
                          f"(id TEXT PRIMARY KEY, source TEXT, embedding vector({dim}))")
        self.conn.execute(f"CREATE INDEX IF NOT EXISTS {self.table}_hnsw ON {self.table} "
                          "USING hnsw (embedding vector_cosine_ops)")
        self.dim = dim

    def upsert(self, chunks, embeddings):
        if not chunks:
            return
        self._ensure(len(embeddings[0]))
        with self.conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {self.table} (id, source, embedding) VALUES (%s, %s, %s::vector) "
                "ON CONFLICT (id) DO UPDATE SET source = EXCLUDED.source, embedding = EXCLUDED.embedding",
                [(c.id, c.source, json.dumps(e)) for c, e in zip(chunks, embeddings)])

    def search(self, embedding, top_k, filters=None):
        try:
            rows = self.conn.execute(
                f"SELECT id, source, 1 - (embedding <=> %s::vector) FROM {self.table} "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (json.dumps(embedding), json.dumps(embedding), top_k)).fetchall()
        except Exception:  # tabela ainda não criada
            return []
        return [Hit(Chunk(id=i, text="", source=s), float(score)) for i, s, score in rows]

    def delete_source(self, source):
        try:
            self.conn.execute(f"DELETE FROM {self.table} WHERE source = %s", (source,))
        except Exception:
            pass

    def clear(self):
        self.conn.execute(f"DROP TABLE IF EXISTS {self.table}")
        self.dim = None


def open_store(rag_cfg: dict, data_dir: Path, collection: str):
    provider = (rag_cfg.get("provider") or "local").lower()
    conn = _expand(rag_cfg.get("connection", ""))
    try:
        if provider == "local":
            return LocalStore(data_dir / "vectors.db")
        if provider == "chroma":
            return ChromaStore(data_dir / "chroma", collection)
        if provider == "qdrant":
            return QdrantStore(conn, collection)
        if provider == "pgvector":
            return PgVectorStore(conn, collection)
    except ImportError as exc:
        raise SystemExit(f'RAG: o provedor "{provider}" exige `pip install "agentkit[{provider}]"` ({exc}).') from exc
    raise SystemExit(f"RAG: provedor desconhecido: {provider}. Use local, chroma, qdrant ou pgvector.")
