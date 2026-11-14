"""BM25 em Python puro (busca por palavras), adequado ao português.

Funciona sem nenhuma dependência e sem chave de API: é a base da busca híbrida
e o modo de operação quando não há embeddings configurados.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9_]+")
# palavras muito comuns que só atrapalham o ranqueamento
STOPWORDS = frozenset("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para pra
com sem sob sobre e ou que se nao sim ao aos à às é ser foi sao esta este isto essa esse isso
como mais menos muito muita mas ja quando onde qual quais seu sua seus suas meu minha the of
and or to in on for is are be with this that it as at by an
""".split())


def tokenize(text: str) -> list[str]:
    """Minúsculas, sem acentos, divide snake_case/camelCase e remove stopwords."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)  # camelCase -> camel Case
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    out = []
    for tok in _TOKEN.findall(text):
        parts = [p for p in tok.split("_") if p] if "_" in tok else [tok]
        if len(parts) > 1:
            out.append(tok)
        out.extend(p for p in parts if len(p) > 1 and p not in STOPWORDS)
    return out


class BM25:
    """Índice BM25 (Okapi) em memória sobre uma lista de documentos."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = [t for t in tokenize(query) if t in self.idf]
        out = []
        for tf, length in zip(self.tfs, self.lens):
            s = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * length / (self.avg or 1))
                    s += self.idf[t] * f * (self.k1 + 1) / denom
            out.append(s)
        return out

    def top(self, query: str, k: int) -> list[tuple[int, float]]:
        ranked = sorted(enumerate(self.scores(query)), key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in ranked[:k] if s > 0]
