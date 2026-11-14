"""Indexação incremental e busca híbrida.

Catálogo em `<projeto>/.agentkit/rag/index.db` (SQLite):
  meta(key, value)                      embedder e parâmetros de chunking usados
  files(source, sha)                    hash de cada arquivo indexado
  chunks(id, source, section, text)     texto de cada chunk (base do BM25)

Os vetores vão para o provedor escolhido (`store.open_store`). Só arquivos com hash
novo são reprocessados; arquivos apagados saem do índice; se o embedder ou o
chunking mudarem, tudo é reindexado.

Busca: BM25 (sempre) + vetorial (se houver embedder), fundidos por Reciprocal Rank
Fusion; reranking opcional pela Voyage.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

from . import Chunk, Hit
from .bm25 import BM25
from .chunking import chunk_file
from .embedders import get_embedder
from .store import open_store

DATA_DIR = ".agentkit/rag"
SKIP_DIRS = {".git", ".agentkit", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
MAX_FILE_BYTES = 1_000_000
RRF_K = 60

_UNSET = object()  # "não informado": escolher o embedder pela configuração


def data_dir(root: Path) -> Path:
    return root / DATA_DIR


def _collection(cfg: dict, root: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", cfg["project"].get("name") or root.name)[:60] or "agentkit"


def _read(path: Path) -> str:
    from ..installer import read_user_text  # UTF-8 com fallback cp1252
    return read_user_text(path)


def collect_sources(root: Path, globs: list[str]) -> dict[str, Path]:
    """Arquivos que casam com `rag.sources`, como {caminho relativo posix: Path}."""
    found: dict[str, Path] = {}
    for pattern in globs:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in SKIP_DIRS for part in rel.parts[:-1]):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            found[rel.as_posix()] = path
    return dict(sorted(found.items()))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Catalog:
    def __init__(self, root: Path):
        d = data_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(d / "index.db")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS files (source TEXT PRIMARY KEY, sha TEXT);
            CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, source TEXT, section TEXT, text TEXT);
            CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source);
        """)

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def files(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT source, sha FROM files"))

    def remove(self, source: str) -> None:
        self.db.execute("DELETE FROM chunks WHERE source = ?", (source,))
        self.db.execute("DELETE FROM files WHERE source = ?", (source,))

    def add(self, source: str, sha: str, chunks: list[Chunk]) -> None:
        self.db.executemany("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?)",
                            [(c.id, c.source, c.metadata.get("section", ""), c.text) for c in chunks])
        self.db.execute("INSERT OR REPLACE INTO files VALUES (?, ?)", (source, sha))

    def clear(self) -> None:
        self.db.executescript("DELETE FROM chunks; DELETE FROM files;")

    def chunks(self) -> list[Chunk]:
        return [Chunk(id=i, text=t, source=s, metadata={"section": sec})
                for i, s, sec, t in self.db.execute("SELECT id, source, section, text FROM chunks ORDER BY source, rowid")]

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.close()


def _signature(rag: dict, embedder) -> dict[str, str]:
    return {"embedder": getattr(embedder, "id", "none"),
            "chunking": f"{rag['chunk_size']}:{rag['chunk_overlap']}",
            "provider": rag.get("provider", "local")}


def status(root: Path, cfg: dict) -> dict:
    """Quantos arquivos estão novos, alterados ou apagados, sem gerar embeddings."""
    root = Path(root).resolve()
    sources = collect_sources(root, cfg["rag"]["sources"])
    if not (data_dir(root) / "index.db").exists():
        return {"indexed": 0, "chunks": 0, "new": len(sources), "changed": 0, "removed": 0, "stale": True}
    cat = Catalog(root)
    try:
        known = cat.files()
        n_chunks = cat.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        cat.close()
    new = [s for s in sources if s not in known]
    changed = [s for s, p in sources.items() if s in known and known[s] != _sha(p)]
    removed = [s for s in known if s not in sources]
    return {"indexed": len(known), "chunks": n_chunks, "new": len(new), "changed": len(changed),
            "removed": len(removed), "stale": bool(new or changed or removed)}


def index_project(root: Path, cfg: dict, *, full: bool = False, embedder=_UNSET, log=print) -> dict:
    """Indexa (incrementalmente) as fontes de `rag.sources`. Devolve um relatório."""
    root = Path(root).resolve()
    rag = cfg["rag"]
    if embedder is _UNSET:
        embedder = get_embedder(rag)
    sig = _signature(rag, embedder)
    cat = Catalog(root)
    store = open_store(rag, data_dir(root), _collection(cfg, root)) if embedder else None
    report = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0, "chunks": 0,
              "embedder": sig["embedder"], "full": False}
    try:
        previous = {k: cat.get_meta(k) for k in sig}
        if full or any(previous[k] != v for k, v in sig.items()):
            cat.clear()
            if store:
                store.clear()
            report["full"] = True

        sources = collect_sources(root, rag["sources"])
        known = cat.files()
        for source in [s for s in known if s not in sources]:
            cat.remove(source)
            if store:
                store.delete_source(source)
            report["removed"] += 1

        for source, path in sources.items():
            sha = _sha(path)
            if known.get(source) == sha and not report["full"]:
                report["unchanged"] += 1
                continue
            chunks = chunk_file(source, _read(path), rag["chunk_size"], rag["chunk_overlap"])
            if store:
                store.delete_source(source)
                if chunks:
                    store.upsert(chunks, embedder.embed_documents([c.text for c in chunks]))
            cat.remove(source)
            cat.add(source, sha, chunks)
            report["chunks"] += len(chunks)
            report["updated" if source in known and not report["full"] else "added"] += 1
            if log:
                log(f"  indexado: {source} ({len(chunks)} trechos)")

        for k, v in sig.items():
            cat.set_meta(k, v)
        cat.commit()
    finally:
        cat.close()
    return report


class Searcher:
    """Busca híbrida. Mantém o BM25 em memória enquanto o índice não muda (servidor MCP)."""

    def __init__(self, root: Path, cfg: dict, embedder=_UNSET):
        self.root, self.cfg = Path(root).resolve(), cfg
        self.rag = cfg["rag"]
        self.embedder = get_embedder(self.rag) if embedder is _UNSET else embedder
        self._version = None
        self._chunks: list[Chunk] = []
        self._bm25: BM25 | None = None
        self._store = None

    def _load(self) -> None:
        path = data_dir(self.root) / "index.db"
        version = path.stat().st_mtime_ns if path.exists() else None
        if version == self._version:
            return
        cat = Catalog(self.root)
        try:
            self._chunks = cat.chunks()
            indexed_with = cat.get_meta("embedder")
        finally:
            cat.close()
        self._bm25 = BM25([c.text for c in self._chunks])
        # vetores só valem se foram gerados pelo mesmo embedder que vai gerar a consulta
        use_vectors = self.embedder is not None and indexed_with == getattr(self.embedder, "id", None)
        self._store = open_store(self.rag, data_dir(self.root), _collection(self.cfg, self.root)) if use_vectors else None
        self._version = version

    def search(self, query: str, top_k: int | None = None, source_glob: str | None = None) -> list[Hit]:
        self._load()
        top_k = top_k or self.rag.get("top_k", 6)
        if not self._chunks or not query.strip():
            return []
        allowed = None
        if source_glob:
            allowed = {i for i, c in enumerate(self._chunks) if fnmatch.fnmatch(c.source, source_glob)}
        pool = top_k * 4
        by_id = {c.id: i for i, c in enumerate(self._chunks)}

        rankings: list[list[int]] = []
        lexical = [i for i, _ in self._bm25.top(query, len(self._chunks)) if allowed is None or i in allowed]
        rankings.append(lexical[:pool])
        if self._store is not None:
            try:
                hits = self._store.search(self.embedder.embed_query(query), pool * (3 if allowed else 1))
            except Exception as exc:  # rede/chave/banco fora do ar: segue só com BM25
                print(f"agentkit-rag: busca vetorial indisponível ({exc}); usando só BM25", file=sys.stderr)
                hits = []
            semantic = [by_id[h.chunk.id] for h in hits if h.chunk.id in by_id]
            rankings.append([i for i in semantic if allowed is None or i in allowed][:pool])

        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        order = sorted(fused, key=fused.get, reverse=True)

        if self.rag.get("rerank") and hasattr(self.embedder, "rerank") and order:
            cand = order[: top_k * 3]
            try:
                order = [cand[j] for j in self.embedder.rerank(query, [self._chunks[i].text for i in cand], top_k)]
            except Exception as exc:
                print(f"agentkit-rag: reranking indisponível ({exc})", file=sys.stderr)

        return [Hit(self._chunks[i], round(fused.get(i, 0.0), 6)) for i in order[:top_k]]


def search(root: Path, cfg: dict, query: str, top_k: int | None = None,
           source_glob: str | None = None, embedder=_UNSET) -> list[Hit]:
    return Searcher(root, cfg, embedder).search(query, top_k, source_glob)


def format_hits(hits: list[Hit]) -> str:
    """Texto pronto para o modelo ler (usado pelo MCP e pelo `agentkit rag search`)."""
    if not hits:
        return "Nenhum trecho encontrado. Tente outras palavras ou rode `agentkit rag index`."
    parts = []
    for n, h in enumerate(hits, 1):
        section = h.chunk.metadata.get("section") or ""
        body = h.chunk.text
        if body.startswith("[") and "\n" in body:  # o cabeçalho [arquivo · seção] já vai no título
            body = body.split("\n", 1)[1]
        parts.append(f"### {n}. {h.chunk.source}{' · ' + section if section else ''}\n{body}")
    return "\n\n".join(parts)
