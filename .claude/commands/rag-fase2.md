---
description: Inicia a fase 2 do AgentKit (RAG e banco vetorial) com o fluxo de agentes
argument-hint: "[banco preferido: chroma | pgvector | qdrant]"
---
Vamos começar a fase 2 do AgentKit: RAG e banco vetorial. Banco preferido: $ARGUMENTS (se vazio, comece pelo chroma, que é local, e deixe pgvector e qdrant atrás da mesma interface).

Contexto: leia `CLAUDE.md` (seção "Próximos passos"), `docs/HISTORICO_DO_CHAT.md` (seção 2) e `agentkit/rag/__init__.py`.

1. Delegue ao `architect` um plano para: indexador incremental, `VectorStore` (chroma/pgvector/qdrant), embeddings Voyage, busca híbrida + reranking, servidor MCP `search_docs` registrado no `.mcp.json` pelo instalador quando `rag.enabled` for true, e `agentkit rag index|search|eval`. Dependências pesadas devem ser opcionais (`pip install agentkit[rag]`).
2. Mostre o plano e espere minha aprovação antes de implementar.
3. Depois siga o fluxo padrão: code-writer → code-reviewer → guardrail. Os testes não podem chamar APIs externas (use um Embedder falso).
