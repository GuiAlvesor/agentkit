"""Servidor MCP `agentkit-rag` (stdio) com a busca na documentação do projeto.

Registrado no `.mcp.json` do projeto pelo instalador quando `rag.enabled: true`:
    {"mcpServers": {"agentkit-rag": {"command": "agentkit", "args": ["rag", "serve"]}}}

Ferramentas:
  search_docs(query, top_k?, source_glob?)  trechos mais relevantes (busca híbrida)
  list_sources()                            arquivos indexados

O stdout pertence ao protocolo MCP; mensagens vão para o stderr.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .index import _UNSET, Catalog, Searcher, format_hits, index_project, status

INSTRUCTIONS = (
    "Busca na documentação e nos requisitos deste projeto (requisitos/, docs/, README...). "
    "Use search_docs antes de assumir algo sobre regras de negócio, requisitos ou decisões "
    "de arquitetura. Cite o arquivo de origem ao usar um trecho."
)


def _server_class():
    try:
        from mcp.server.mcpserver import MCPServer  # mcp 2.x
        return MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x
        return FastMCP


def build_server(root: Path, cfg: dict, embedder=_UNSET):
    """Cria o servidor. `embedder` só é passado nos testes."""
    searcher = Searcher(root, cfg, embedder)
    server = _server_class()(name="agentkit-rag", instructions=INSTRUCTIONS)

    @server.tool()
    def search_docs(query: str, top_k: int = 0, source_glob: str = "") -> str:
        """Busca trechos relevantes na documentação e nos requisitos do projeto.

        query: pergunta ou palavras-chave (português ou inglês).
        top_k: quantos trechos devolver (0 = padrão do projeto).
        source_glob: filtra por arquivo, ex.: "requisitos/*" ou "docs/**/*.md".
        """
        return format_hits(searcher.search(query, top_k or None, source_glob or None))

    @server.tool()
    def list_sources() -> str:
        """Lista os arquivos indexados (para saber o que pode ser buscado)."""
        cat = Catalog(searcher.root)
        try:
            files = sorted(cat.files())
        finally:
            cat.close()
        return "\n".join(files) if files else "Índice vazio: rode `agentkit rag index`."

    return server


def serve(root: Path, cfg: dict) -> None:
    root = Path(root).resolve()
    try:
        if status(root, cfg)["stale"]:
            rep = index_project(root, cfg, log=None)
            print(f"agentkit-rag: índice atualizado ({rep['added']} novos, {rep['updated']} alterados, "
                  f"{rep['removed']} removidos)", file=sys.stderr)
    except (SystemExit, Exception) as exc:  # embedder indisponível, rede fora etc.: serve o índice que existe
        print(f"agentkit-rag: não foi possível atualizar o índice: {exc}", file=sys.stderr)
    build_server(root, cfg).run()
