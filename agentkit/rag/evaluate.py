"""Avaliação da recuperação: hit@k e MRR.

Formato do arquivo (YAML), por padrão `requisitos/rag-eval.yaml` ou `docs/rag-eval.yaml`:

    - pergunta: Como o guardrail trata force push?
      esperado: agentkit/hooks/agentkit_guardrail.py     # arquivo (ou glob) que deveria aparecer
    - pergunta: Qual o modelo padrão do arquiteto?
      esperado: CLAUDE.md

Comece com 20–30 perguntas reais e rode depois de mudar chunking, embedder ou fontes.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

from .index import _UNSET, Searcher

DEFAULT_FILES = ("requisitos/rag-eval.yaml", "docs/rag-eval.yaml")


def find_eval_file(root: Path) -> Path | None:
    for rel in DEFAULT_FILES:
        if (root / rel).exists():
            return root / rel
    return None


def evaluate(root: Path, cfg: dict, path: Path, top_k: int | None = None, embedder=_UNSET) -> dict:
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    k = top_k or cfg["rag"].get("top_k", 6)
    searcher = Searcher(root, cfg, embedder)
    rows, hits, rr = [], 0, 0.0
    for item in items:
        question = item.get("pergunta") or item.get("question") or ""
        expected = item.get("esperado") or item.get("expected") or ""
        sources = [h.chunk.source for h in searcher.search(question, k)]
        rank = next((n for n, s in enumerate(sources, 1) if fnmatch.fnmatch(s, expected) or s == expected), None)
        if rank:
            hits += 1
            rr += 1 / rank
        rows.append({"pergunta": question, "esperado": expected, "posicao": rank, "obtidos": sources[:3]})
    n = len(rows) or 1
    return {"total": len(rows), "k": k, "hit_rate": hits / n, "mrr": rr / n, "itens": rows}
