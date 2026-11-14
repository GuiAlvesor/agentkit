"""Divide arquivos em chunks respeitando a estrutura do conteúdo.

- Markdown: um chunk por seção (títulos # a ###); o caminho dos títulos vai para
  os metadados e para o início do texto, o que ajuda tanto o BM25 quanto os embeddings.
- Python: um chunk por função/classe de nível superior (via `ast`), mais o "resto"
  do módulo (imports, constantes).
- Outros textos: janelas por tamanho.

Seções grandes demais são quebradas em janelas de `size` caracteres com `overlap`,
cortando de preferência em linha em branco.
"""
from __future__ import annotations

import ast
import hashlib
import re

from . import Chunk

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")


def _chunk_id(source: str, n: int, text: str) -> str:
    digest = hashlib.sha1(f"{source}\n{n}\n{text}".encode("utf-8")).hexdigest()[:16]
    return f"{source}#{n}-{digest}"


def split_windows(text: str, size: int, overlap: int) -> list[str]:
    """Quebra `text` em janelas de até `size` caracteres com `overlap` de sobreposição."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    overlap = max(0, min(overlap, size // 2))
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            # corta num parágrafo (ou ao menos numa quebra de linha) dentro da segunda metade da janela
            cut = text.rfind("\n\n", start + size // 2, end)
            if cut == -1:
                cut = text.rfind("\n", start + size // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        nxt = max(end - overlap, start + 1)
        # começa a sobreposição numa palavra inteira (não no meio de uma)
        space = re.compile(r"\s").search(text, nxt, end)
        start = space.end() if space and space.end() < end else nxt
    return out


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    """Devolve [(caminho dos títulos, corpo)]. Ignora '#' dentro de blocos de código."""
    sections: list[tuple[str, str]] = []
    path: list[str] = []
    buf: list[str] = []
    in_code = False

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append((" > ".join(path), body))
        buf.clear()

    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[: level - 1] + [m.group(2).strip()]
            buf.append(line)
        else:
            buf.append(line)
    flush()
    return sections


def _python_sections(text: str) -> list[tuple[str, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [("", text)]
    lines = text.splitlines()
    used = [False] * len(lines)
    sections = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([d.lineno for d in node.decorator_list] + [node.lineno]) - 1
            end = node.end_lineno or node.lineno
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            sections.append((f"{kind} {node.name}", "\n".join(lines[start:end])))
            for i in range(start, end):
                used[i] = True
    rest = "\n".join(line for line, u in zip(lines, used) if not u).strip()
    if rest:
        sections.insert(0, ("módulo", rest))
    return sections


def chunk_file(source: str, text: str, size: int = 1200, overlap: int = 150) -> list[Chunk]:
    """Gera os chunks de um arquivo. `source` é o caminho relativo (posix)."""
    lower = source.lower()
    if lower.endswith((".md", ".markdown", ".mdx")):
        sections = _markdown_sections(text)
    elif lower.endswith(".py"):
        sections = _python_sections(text)
    else:
        sections = [("", text)]

    chunks: list[Chunk] = []
    for section, body in sections:
        for piece in split_windows(body, size, overlap):
            # o contexto (arquivo + seção) no início melhora a recuperação dos trechos
            header = f"[{source}{' · ' + section if section else ''}]"
            full = f"{header}\n{piece}"
            chunks.append(Chunk(id=_chunk_id(source, len(chunks), full), text=full, source=source,
                                metadata={"section": section, "position": len(chunks)}))
    return chunks
