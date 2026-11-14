"""Geradores de embeddings (opcionais).

- `voyage`: Voyage AI (`pip install "agentkit[rag]"` + VOYAGE_API_KEY). Melhor qualidade.
- `local`: fastembed (`pip install "agentkit[rag-local]"`). Gratuito e offline depois do
  primeiro download do modelo (~100 MB).
- `auto` (padrão): Voyage se houver chave e pacote; senão, o local se o fastembed estiver
  instalado; senão nenhum, e a busca fica só por palavras (BM25).
- `none`: só BM25.
"""
from __future__ import annotations

import os
from importlib.util import find_spec


class VoyageEmbedder:
    name = "voyage"

    def __init__(self, model: str = "voyage-3", batch: int = 64):
        import voyageai  # importação tardia: dependência opcional

        self.client = voyageai.Client()  # lê VOYAGE_API_KEY
        self.model, self.batch = model, batch
        self.id = f"voyage:{model}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            res = self.client.embed(texts[i:i + self.batch], model=self.model, input_type="document")
            out.extend(res.embeddings)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed([text], model=self.model, input_type="query").embeddings[0]

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[int]:
        """Índices de `docs` reordenados pelo reranker da Voyage."""
        res = self.client.rerank(query, docs, model="rerank-2", top_k=top_k)
        return [r.index for r in res.results]


class LocalEmbedder:
    name = "local"

    def __init__(self, model: str):
        from fastembed import TextEmbedding  # dependência opcional

        self.model = TextEmbedding(model_name=model)
        self.id = f"local:{model}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, next(iter(self.model.embed([text])))))


def _voyage_ready() -> bool:
    return bool(os.environ.get("VOYAGE_API_KEY")) and find_spec("voyageai") is not None


def get_embedder(rag_cfg: dict):
    """Escolhe o embedder conforme `rag.embedder`. Devolve None para busca só por palavras."""
    mode = (rag_cfg.get("embedder") or "auto").lower()
    if mode == "none":
        return None
    if mode == "voyage":
        if not _voyage_ready():
            raise SystemExit('RAG: embedder "voyage" exige VOYAGE_API_KEY e `pip install "agentkit[rag]"`.')
        return VoyageEmbedder(rag_cfg.get("embedding_model") or "voyage-3")
    if mode == "local":
        if find_spec("fastembed") is None:
            raise SystemExit('RAG: embedder "local" exige `pip install "agentkit[rag-local]"`.')
        return LocalEmbedder(rag_cfg.get("local_model"))
    # auto
    if _voyage_ready():
        return VoyageEmbedder(rag_cfg.get("embedding_model") or "voyage-3")
    if find_spec("fastembed") is not None:
        return LocalEmbedder(rag_cfg.get("local_model"))
    return None


def describe(rag_cfg: dict) -> str:
    """Texto curto do que o modo atual vai usar, sem carregar modelos (para doctor/status)."""
    mode = (rag_cfg.get("embedder") or "auto").lower()
    if mode == "none":
        return "só palavras (BM25)"
    if mode in ("voyage", "auto") and _voyage_ready():
        return f"BM25 + Voyage ({rag_cfg.get('embedding_model') or 'voyage-3'})"
    if mode in ("local", "auto") and find_spec("fastembed") is not None:
        return f"BM25 + local ({rag_cfg.get('local_model')})"
    if mode == "auto":
        return "só palavras (BM25): defina VOYAGE_API_KEY ou instale agentkit[rag-local] para busca por significado"
    return f"embedder {mode} indisponível"
