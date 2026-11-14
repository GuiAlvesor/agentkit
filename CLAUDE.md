# AgentKit — contexto para o Claude Code

Este repositório é o **AgentKit**: um kit portátil de agentes (Claude Code + Claude Agent SDK) que se instala em qualquer projeto com pequenas adaptações. Ele nasceu de uma conversa no Claude; o histórico completo, com as decisões e as explicações, está em `docs/HISTORICO_DO_CHAT.md`. Leia esse arquivo quando precisar entender **por que** algo foi feito de certo jeito.

O usuário escreve em português do Brasil, usa **Windows**, e quer respostas e código comentado em português.

## Objetivo do projeto (pedido original)
- Projeto portátil para outros projetos, com pequenas modificações para funcionar.
- Agentes: orquestrador, revisor, escritor, arquiteto, revisor de commit/PR, deployer, release summary (resumir transações e mudanças de código) e guardrail.
- Controle do modelo que cada agente usa.
- Interface gráfica simples para configurar e adaptar o kit a cada diretório.
- **Depois:** RAG e banco vetorial.

## Decisões já tomadas (não reabrir sem motivo)
| Tema | Decisão | Motivo |
|---|---|---|
| Onde os agentes rodam | **Os dois**: Claude Code (interativo) e Agent SDK (CI/scripts), usando os mesmos `.claude/agents/*.md` | Escolha do usuário; uma definição só, comportamento idêntico |
| Stack | **Python + interface web local** (FastAPI + uma página HTML sem build) | Escolha do usuário |
| Deploy | **Genérico**: o deployer só executa os comandos configurados no `agentkit.yaml` | Escolha do usuário; nunca inventar comando de deploy |
| Orquestrador | Roda na **sessão principal** (fluxo no `CLAUDE.md` gerado, modelo no `.claude/settings.json`); no SDK, vira o `system_prompt` de `agentkit run` | Subagentes do Claude Code não chamam outros subagentes |
| Guardrail | Duas camadas: **agente** (julgamento) + **hook PreToolUse determinístico** (`agentkit/hooks/agentkit_guardrail.py`, só biblioteca padrão) | O hook não pode ser "convencido" pelo modelo e vale também no SDK |
| Fonte da verdade | `agentkit.yaml` em cada projeto-alvo | Versionável, editável à mão ou pela interface |
| Edições manuais | Preservadas: manifest com hashes; conflito vai para `*.agentkit-new`; no `CLAUDE.md` só a seção entre `<!-- agentkit:start/end -->` é gerenciada | O kit não pode destruir ajustes do usuário |
| Menor privilégio | Revisores, arquiteto e guardrail sem `Write`/`Edit`; deployer só `Read, Bash`; deployer só roda no SDK com `--allow-deploy` | Segurança |
| Modelos padrão | orquestrador/architect `opus`; writer/reviewers/deployer `sonnet`; guardrail/release-summary `haiku`; aceita ID completo ou `inherit` | Custo × complexidade da tarefa |

## Mapa do código
```
agentkit/
  defaults.py      catálogo dos agentes (ferramentas, modelo padrão) e DEFAULT_CONFIG
  config.py        load/save/normalize do agentkit.yaml; lista de projetos recentes (~/.agentkit/recent.json)
  detect.py        detecção de stack: Node (npm/pnpm/yarn/bun), Python (uv/poetry/pip), Go, Rust, Maven, Gradle, .NET, Makefile, Vercel/Fly
  installer.py     renderiza templates Jinja2 e instala (plan/install, manifest, mescla do settings.json, .gitignore)
  runner.py        Agent SDK: run_task (orquestrador), run_agent, review (pr-reviewer + guardrail em paralelo), release
  cli.py           comandos: init, install, detect, gui, run, agent, review, release, doctor
  doctor.py        checagens do ambiente (usado por `agentkit doctor` e pelos setup.ps1/setup.sh)
  server.py        API FastAPI da interface (só aceita Host localhost)
  static/index.html  interface (HTML/CSS/JS puro, tema claro/escuro)
  hooks/agentkit_guardrail.py   hook copiado para cada projeto
  templates/       agents/*.md (+ _context.md incluído em todos), orchestrator.md, CLAUDE.section.md, commands/*.md, ci/agentkit-review.yml
  rag/__init__.py  interfaces (Chunk, Hit, VectorStore, Embedder) e o plano da fase 2
tests/             pytest: detecção, instalação, preservação de edições, hook, API, runner
```

## Comandos de desenvolvimento (Windows / PowerShell)
O Python do projeto é gerenciado pelo **pyenv-win** (versão fixada em `.python-version`); o `.venv` é criado com esse Python.
```powershell
pyenv versions                   # versões instaladas; a do projeto vem do .python-version
.\setup.ps1                      # usa o Python do pyenv, cria .venv e instala com dependências de dev
.venv\Scripts\Activate.ps1
pytest -q                        # 19 testes devem passar
agentkit doctor                  # checa Python, git, Claude Code, chave de API e o projeto
agentkit gui                     # interface em http://localhost:8765
agentkit init C:\caminho\projeto --dry-run
```

## Convenções
- Código, comentários, mensagens de erro e textos da interface em português.
- Ler e gravar arquivos sempre com `encoding="utf-8"` (no Windows o padrão é cp1252).
- Caminhos com `pathlib`; comparar caminhos relativos com `.as_posix()`.
- O hook de guardrail só pode usar a biblioteca padrão (roda em qualquer projeto).
- `setup.ps1` deve ficar em UTF-8 **com BOM** (o PowerShell 5.1 lê sem BOM como cp1252); há teste para isso.
- Ao mudar um template, rode os testes: eles verificam que o frontmatter é YAML válido e que nenhuma tag Jinja vaza para o arquivo gerado.
- Mudanças nos padrões de todos os projetos: `defaults.py` e `templates/`.

## Próximos passos (roadmap)
1. **Fase 2 — RAG e banco vetorial** (próxima). Plano em `agentkit/rag/__init__.py` e em `docs/HISTORICO_DO_CHAT.md`:
   - Indexador incremental (chunking por estrutura: títulos de Markdown, funções/classes; reindexar só arquivos com hash novo).
   - `VectorStore` com chroma (local), pgvector e qdrant sob a mesma interface.
   - Embeddings Voyage (`voyage-3`, `voyage-code-3` para código), busca híbrida (vetorial + BM25), reranking e *contextual retrieval*.
   - Servidor MCP `agentkit-rag` com `search_docs(query, top_k, filters)`, registrado no `.mcp.json` do projeto quando `rag.enabled` for true.
   - `agentkit rag index|search|eval` + conjunto de perguntas para avaliar a recuperação.
   - A configuração `rag:` e a aba RAG da interface já existem.
2. Ajustar `ci.install_spec` para o repositório real do usuário no GitHub.
3. Ideias em aberto: histórico de execuções na interface. (`agentkit doctor` e o setup guiado já existem.)

Use `/rag-fase2` para começar a fase 2 com o fluxo de agentes.

<!-- agentkit:start (gerado pelo AgentKit; edite pelo agentkit.yaml) -->
# AgentKit

Kit portátil de agentes (Claude Code + Agent SDK) com interface de configuração.

- Linguagem: python · Frameworks: fastapi, jinja2, claude-agent-sdk
- Branch base: `main`

## Comandos
| Ação | Comando |
|---|---|
| Instalar | `pip install -e ".[dev]"` |
| Testes | `pytest -q` |

## Convenções
- Tudo em português (código comentado, mensagens, interface).
- Ler/gravar arquivos com encoding="utf-8".
- O hook de guardrail usa só a biblioteca padrão.
- Dependências de RAG devem ser opcionais (extra [rag]).
- Testes nunca chamam APIs externas.

## Regras de segurança
- Não altere: .env, .env.*, **/*.pem, **/*.key, **/secrets/**, .git/**.
- Nunca grave segredos no código ou em logs.
- Comandos perigosos são bloqueados pelo hook `.claude/hooks/agentkit_guardrail.py`; não tente contorná-lo.

## Fluxo de agentes (AgentKit)

Você é o **orquestrador** deste projeto. Você não faz o trabalho especializado sozinho: entende o pedido, escolhe os agentes certos, delega com instruções completas e junta os resultados. Cada subagente começa sem o contexto desta conversa, então inclua na delegação tudo o que ele precisa saber (objetivo, arquivos, decisões já tomadas, resultado do agente anterior).

Agentes disponíveis:
- `architect` — Planeja mudanças estruturais e avalia impacto arquitetural.
- `code-writer` — Implementa funcionalidades e correções seguindo os padrões do projeto.
- `code-reviewer` — Revisa as mudanças locais: bugs, segurança, legibilidade e testes.
- `pr-reviewer` — Revisa commits e pull requests contra a branch base.
- `release-summary` — Resume commits, PRs e mudanças de código entre duas versões.
- `guardrail` — Barra segredos, caminhos protegidos e mudanças de risco antes do commit/deploy.

### Fluxo padrão para mudanças de código
1. **Planejar** — para mudanças que tocam mais de um módulo, criam componentes novos ou mexem em dados/APIs, delegue ao `architect` e siga o plano. Para mudanças pequenas e locais, pule este passo.
2. **Implementar** — delegue ao `code-writer` com o plano (ou a especificação) e os critérios de aceite.
3. **Revisar** — delegue ao `code-reviewer`. Se o veredito for "MUDANÇAS NECESSÁRIAS", volte ao `code-writer` com os achados 🔴. Limite: 3 ciclos; depois disso, pare e peça ajuda humana.
4. **Guardrail** — antes de qualquer commit, PR ou deploy, delegue ao `guardrail` informando a tarefa original. Se a primeira linha for `GUARDRAIL: BLOQUEIA`, pare e mostre os achados ao usuário.
5. **Commit** — só faça commit se o usuário pediu. Use Conventional Commits. Nunca faça push sem pedido explícito.
6. **PR** — para revisar a branch ou um PR, delegue ao `pr-reviewer`.
7. **Release** — para notas de versão ou "o que mudou desde X", delegue ao `release-summary`.

### Regras
- Pedidos simples (uma pergunta, uma leitura, um ajuste de uma linha) você resolve direto, sem delegar.
- Agentes revisores (`architect`, `code-reviewer`, `pr-reviewer`, `guardrail`) não editam arquivos. Quem edita é o `code-writer`.
- Ao terminar, responda com: o que foi feito, os vereditos de revisão e guardrail, e o que ficou pendente.
<!-- agentkit:end -->
