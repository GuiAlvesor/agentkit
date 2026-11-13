# Histórico da conversa que originou o AgentKit

Resumo fiel da conversa no Claude (12 e 13/11/2026), para que o Claude Code tenha o mesmo contexto.

---

## 1. "Como criar diferentes agentes (revisor de código, contexto do projeto, escritor, revisor de arquitetura, deployer…)"

**Resposta:** usar **subagentes do Claude Code**, ou seja, arquivos Markdown com frontmatter YAML e o prompt de sistema no corpo.

- Locais: `.claude/agents/` (do projeto, versionado) e `~/.claude/agents/` (pessoais). Também dá para criar pelo comando `/agents`.
- Campos: `name`, `description` (é o que o Claude usa para decidir quando delegar; "use PROACTIVELY…" faz a delegação ser automática), `tools` (limita o que o agente pode fazer) e `model`.
- Agentes sugeridos: `project-context` (haiku, só leitura), `code-writer` (sonnet, escreve e roda testes), `code-reviewer` (sonnet, sem escrita, achados 🔴/🟡/🟢 com arquivo:linha), `architect-reviewer` (opus, sem escrita, trade-offs e ADRs) e `deployer` (sonnet, Read+Bash, testes → confirmação → deploy → health check).
- O contexto permanente do projeto fica melhor no `CLAUDE.md`, que todos os agentes leem.
- Formas de uso: automática (pela description), explícita ("use o code-reviewer…") ou encadeada.
- Boas práticas: um papel por agente, menor privilégio, modelo conforme o custo da tarefa, versionar `.claude/agents/`, pedir um resumo objetivo no fim (cada subagente tem contexto próprio).
- Fora do Claude Code: Claude Agent SDK, ou `claude -p` headless no GitHub Actions.

## 2. "Como implementar RAG e banco vetorial"

**Conceito:** RAG = recuperar trechos relevantes dos seus documentos e colocá-los no prompt. O banco vetorial busca por significado.

- **Indexação:** carregar → dividir em chunks (300–1000 tokens, com sobreposição) → gerar embeddings → salvar vetor + texto + metadados.
- **Consulta:** embedding da pergunta → top-k por similaridade de cosseno → prompt com o contexto → resposta.
- **Bancos:** Chroma (protótipo/local), **pgvector** (já usa Postgres; ótima escolha padrão), Qdrant (produção, open source), Pinecone (gerenciado), Weaviate/Milvus (grande escala, busca híbrida nativa).
- **Embeddings:** Voyage AI (`voyage-3`; `voyage-code-3` para código), recomendada pela Anthropic; alternativas: OpenAI ou `sentence-transformers` local.
- Exemplo mínimo mostrado: Chroma + Voyage + Claude em Python, e a versão com pgvector (`vector(1024)`, índice `hnsw` com `vector_cosine_ops`, `ORDER BY embedding <=> $1 LIMIT 5`).
- **O que mais melhora a qualidade** (por ordem de impacto): chunking por estrutura; busca híbrida (vetorial + BM25); reranking (buscar 20–50 e reordenar para 5); *contextual retrieval* (prefixar cada chunk com uma frase de contexto gerada pelo Claude); filtros por metadados (inclusive permissão de acesso); avaliação com 30–100 perguntas.
- **Integração com agentes:** como ferramenta (*RAG agêntico*: o agente decide quando buscar) ou como **servidor MCP** conectado ao Claude Code.
- Para código dentro do repositório, `Grep`/`Glob`/`Read` costumam bastar; o RAG vale mais para documentação, wikis, tickets e conteúdo fora do repositório.

## 3. Pedido do projeto

> Projeto portátil para outros projetos com pequenas modificações para funcionar. Agente orquestrador, revisor, escritor, arquiteto, commit/pull request reviewer, deployer, release summary (resumir transações que ocorreram e mudanças do código), guardrail. Implementação (posteriormente) de RAG e banco vetorial. Controle do modelo que cada agente vai usar. Interface gráfica simples para configurar o projeto e adaptar para cada diretório que for inserido.

**Perguntas feitas e respostas do usuário:**
- Onde os agentes vão rodar? → **Os dois** (Claude Code + Agent SDK/CI).
- Stack do kit e da interface? → **Python + web local**.
- Onde acontecem os deploys? → **Genérico (configurável)**.

**O que foi construído (v0.1.0):** veja o `CLAUDE.md` (tabela de decisões e mapa do código) e o `README.md` (uso). Pontos principais:
- 7 subagentes + orquestrador na sessão principal; comandos `/ship`, `/review-pr`, `/release-notes` e `/deploy`.
- Hook de guardrail determinístico: nega `rm -rf /`, force push, `curl | sh`, escrita em `.env`/chaves e segredos no conteúdo; pede confirmação para push, kubectl/helm, terraform, publish e `vercel --prod`.
- Interface web: escolher pasta, detecção automática, abas Projeto/Comandos/Agentes e modelos/Guardrails/CI/RAG, pré-visualização dos prompts, "Ver o que vai mudar" e "Salvar e instalar".
- Runner do Agent SDK (`agentkit run|agent|review|release`) + workflow opcional do GitHub Actions.
- 16 testes passando; a interface também foi testada num navegador headless.

## 4. "Portabilize esse chat para o Claude Code"

Este arquivo, o `CLAUDE.md` do repositório e o AgentKit instalado nele mesmo (agentes em `.claude/agents/`) foram criados para continuar o trabalho no Claude Code. Também houve ajustes para Windows: UTF-8 explícito, `python` em vez de `python3` no hook e console com UTF-8.
