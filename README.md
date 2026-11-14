# AgentKit

Kit portátil de agentes para levar a qualquer projeto. Você instala uma vez, aponta para um diretório, ajusta o que for específico daquele projeto (comandos, modelos, convenções, políticas) e o AgentKit gera tudo o que o **Claude Code** e o **Claude Agent SDK** precisam.

| Agente | Papel | Ferramentas | Modelo padrão |
|---|---|---|---|
| Orquestrador | Planeja e delega na ordem certa (sessão principal) | todas | opus |
| `requirements-analyst` | Lê `requisitos/`, aponta lacunas e mantém o backlog | leitura + escrita (só `docs/plano/`) | sonnet |
| `architect` | Plano de implementação e impacto arquitetural | leitura + Bash | opus |
| `code-writer` | Implementa seguindo os padrões do projeto | leitura + escrita + Bash | sonnet |
| `code-reviewer` | Revisa as mudanças locais | leitura + Bash | sonnet |
| `pr-reviewer` | Revisa commits e PRs contra a branch base | leitura + Bash | sonnet |
| `deployer` | Roda o deploy configurado, com checagens e confirmação | Read + Bash | sonnet |
| `release-summary` | Resume commits, PRs e mudanças entre versões | leitura + Bash + Write | haiku |
| `guardrail` | Barra segredos, arquivos protegidos e mudanças de risco | leitura + Bash | haiku |

O guardrail tem duas camadas: o **agente** (julgamento: escopo, dependências suspeitas, dados pessoais) e um **hook determinístico** que roda antes de cada comando ou edição e não pode ser "convencido" pelo modelo.

## Instalação

### Pré-requisitos
- **Python ≥ 3.10** (recomendado 3.12; a versão fixada do projeto está em `.python-version`).
- **git**.
- **Claude Code CLI** (`npm install -g @anthropic-ai/claude-code`) para uso interativo **ou** `ANTHROPIC_API_KEY` para uso via Agent SDK/CI.
- *(Opcional, recomendado)* **pyenv-win** (Windows) ou **pyenv** (macOS/Linux) para gerenciar a versão do Python.

### Um comando

```bash
git clone https://github.com/GuiAlvesor/agentkit.git && cd agentkit
.\setup.ps1          # Windows (PowerShell)
./setup.sh           # macOS / Linux   (ou: bash setup.sh)
```

O `setup` é um **wizard guiado**: verifica cada pré-requisito, cria o `.venv`, instala, roda os testes, oferece instalar o comando `agentkit` global (via `pipx`, necessário para o RAG dentro do Claude Code) e roda o `agentkit doctor`. Em caso de ausência de algo opcional (Claude Code, API key) ele avisa e pergunta se prossegue. Para modo não-interativo (CI): `-y` / `-Yes`.

A qualquer momento, `agentkit doctor` repete as checagens sem reinstalar nada.

> Para usar no dia a dia (quando cada agente é acionado, como ler o pipeline, troubleshooting), veja [`docs/MANUAL.md`](docs/MANUAL.md).

## Começando um projeto novo: requisitos → backlog → tarefas

```
requisitos/00-visao.md   ← você escreve (o `agentkit init` cria o modelo)
        │  /iniciar-projeto
        ▼
docs/plano/PERGUNTAS.md  ← dúvidas e lacunas (você responde no chat ou no arquivo)
docs/plano/ARQUITETURA.md← proposta do architect (stack, módulos, dados, ADRs)
docs/plano/BACKLOG.md    ← tarefas T-001… com critérios de aceite e dependências  → você aprova
        │  /proxima-tarefa   (repita)
        ▼
uma tarefa: code-writer → code-reviewer → guardrail → marcada [x] no backlog → para para você conferir
```

1. `agentkit init C:\caminho\projeto` (cria `requisitos/` com o modelo; `--sem-requisitos` para pular).
2. Preencha `requisitos/00-visao.md` (objetivo, usuários, RF-xx, RNF-xx, restrições, critérios de aceite) e, se quiser, outros `.md` na pasta.
3. No Claude Code: **`/iniciar-projeto`**. Os agentes param para você responder os bloqueios e aprovar o backlog.
4. **`/proxima-tarefa`** (ou `/proxima-tarefa T-007`): implementa, revisa e passa pelo guardrail **uma** tarefa e para.
5. `agentkit backlog` mostra o progresso a qualquer momento. Commit por tarefa é opcional (`kickoff.commit_each_task`).

## Uso

### Interface gráfica
```bash
agentkit gui                 # abre http://localhost:8765
agentkit gui ~/projetos/app  # já abre esse projeto
```
1. Escolha o diretório (caminho ou **Procurar…**). A stack, os comandos e a branch base são detectados.
2. Ajuste as abas: **Projeto**, **Comandos**, **Agentes e modelos**, **Guardrails**, **CI / Agent SDK**, **RAG**.
3. **Ver o que vai mudar** mostra o plano; **Salvar e instalar** grava.

### Linha de comando
```bash
agentkit init ~/projetos/app           # detecta e instala
agentkit init ~/projetos/app --dry-run # só mostra o plano
agentkit install                       # reaplica o agentkit.yaml após editar à mão
agentkit detect .                      # mostra o que foi detectado
agentkit requisitos                    # cria o modelo de requisitos/ num projeto já instalado
agentkit backlog                       # progresso do docs/plano/BACKLOG.md
agentkit rag index | search "…" | status | eval   # RAG (veja abaixo)
agentkit doctor                        # checa ambiente, RAG e etapa do ciclo
```

### No Claude Code (dentro do projeto)
- `/iniciar-projeto`: requisitos → perguntas → arquitetura → backlog
- `/proxima-tarefa [T-xxx]`: uma tarefa do backlog com o fluxo completo
- `/ship <tarefa>`: fluxo completo (arquiteto → escritor → revisor → guardrail)
- `/review-pr [número]`: pr-reviewer + guardrail
- `/release-notes [v1.2.0..HEAD]`
- `/deploy staging|production`
- Ou peça direto: "use o architect para planejar X".

### Fora do Claude Code (Agent SDK)
```bash
agentkit run "adicionar paginação em /pedidos" -C ~/projetos/app
agentkit agent code-reviewer "revise minhas mudanças" -C .
agentkit review --base origin/main -o review.md --fail-on-block   # ideal para CI
agentkit release v1.4.0..HEAD -o RELEASE_NOTES.md
agentkit run "deploy em staging" --allow-deploy                    # deployer só com a flag
```
Os mesmos arquivos `.claude/agents/*.md` são usados nos dois modos, então o comportamento é idêntico.

## O que é gerado no projeto

```
agentkit.yaml                         ← fonte da verdade (versione)
CLAUDE.md                             ← só a seção entre <!-- agentkit:start/end -->; o resto é seu
.claude/agents/*.md                   ← um por agente habilitado
.claude/commands/*.md                 ← /iniciar-projeto, /proxima-tarefa, /ship, /review-pr, /release-notes, /deploy
.claude/hooks/agentkit_guardrail.py   ← hook PreToolUse (só biblioteca padrão)
.claude/agentkit/guardrails.json      ← política lida pelo hook
.claude/agentkit/manifest.json        ← hashes do que foi gerado
.claude/settings.json                 ← mesclado: hook, modelo do orquestrador, deny de arquivos protegidos
.github/workflows/agentkit-review.yml ← opcional
.mcp.json                             ← mesclado: servidor agentkit-rag (só com rag.enabled)
requisitos/                           ← modelo criado uma vez pelo `init`; é seu, nunca é sobrescrito
.agentkit/rag/                        ← índice do RAG (no .gitignore)
```

**Suas edições são preservadas.** Se você editar à mão um arquivo gerado, a reinstalação não o sobrescreve: a versão nova vai para `arquivo.agentkit-new` (use `--force` ou a opção da interface para sobrescrever). Ao desabilitar um agente, o arquivo dele é removido só se você não o editou.

## Controle de modelo

Cada agente tem o seu modelo no `agentkit.yaml` (ou na aba **Agentes e modelos**):

```yaml
agents:
  orchestrator: { model: opus }               # vai para .claude/settings.json → "model"
  code-writer:  { model: sonnet }
  guardrail:    { model: haiku }
  architect:    { model: claude-opus-5-5 }    # ID completo também funciona
  code-reviewer:{ model: inherit }            # usa o mesmo da sessão principal
```

## Adaptando a outro projeto

Na maioria dos projetos basta `agentkit init` e revisar os comandos. O que costuma mudar:

- **Comandos**: principalmente `deploy_staging`, `deploy_production`, `health_check` e `rollback`. O deployer só executa o que estiver aqui; nunca inventa comandos.
- **Convenções** (aba Projeto): entram no CLAUDE.md e em todos os agentes.
- **Instruções adicionais por agente**: regras que só valem para um agente naquele projeto.
- **Guardrails**: caminhos protegidos e comandos que exigem confirmação (ex.: `kubectl apply`).

Para mudar o padrão de **todos** os projetos futuros, edite `agentkit/defaults.py` e os templates em `agentkit/templates/`.

## CI (GitHub Actions)

Marque **Gerar workflow** na aba CI, ajuste `install_spec` (de onde o CI instala o AgentKit) e crie o secret `ANTHROPIC_API_KEY`. A cada PR, o `pr-reviewer` e o `guardrail` rodam em paralelo, o resultado é publicado como comentário e o job falha se o guardrail bloquear.

## RAG (busca na documentação para os agentes)

Ligue em `rag.enabled: true` (ou na aba **RAG**) e reinstale. O AgentKit registra o servidor MCP `agentkit-rag` no `.mcp.json` e libera a ferramenta `search_docs` para analista, arquiteto, escritor e revisores, que passam a consultar requisitos, plano e documentação antes de supor algo.

```bash
agentkit rag index            # incremental: só reprocessa arquivos alterados (--full refaz tudo)
agentkit rag search "como é calculado o frete?" --source "requisitos/*"
agentkit rag status           # o que está indexado, o que está pendente e que tipo de busca está ativa
agentkit rag eval             # hit@k e MRR a partir de requisitos/rag-eval.yaml
```

| Peça | Padrão (zero configuração) | Opcional |
|---|---|---|
| Busca | **BM25** (palavras, sem acentos), em Python puro | + vetores, fundidos por Reciprocal Rank Fusion |
| Embeddings | nenhum | `VOYAGE_API_KEY` + `pip install "agentkit[rag]"` (Voyage) ou `pip install "agentkit[rag-local]"` (fastembed, offline) |
| Banco vetorial | `local` (SQLite em `.agentkit/rag/`) | `chroma`, `qdrant`, `pgvector` (`pip install "agentkit[chroma]"` etc.) |
| Reranking | desligado | `rag.rerank: true` (Voyage) |

O chunking respeita a estrutura: seções de Markdown (com o caminho dos títulos) e funções/classes Python. O servidor MCP atualiza o índice ao iniciar, se algo mudou. Para o Claude Code iniciar o servidor, o comando `agentkit` precisa estar no PATH (ou ajuste `rag.mcp_command`).

## Testes

```bash
pip install -e ".[dev]" && pytest
```
