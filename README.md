# AgentKit

Kit portátil de agentes para levar a qualquer projeto. Você instala uma vez, aponta para um diretório, ajusta o que for específico daquele projeto (comandos, modelos, convenções, políticas) e o AgentKit gera tudo o que o **Claude Code** e o **Claude Agent SDK** precisam.

| Agente | Papel | Ferramentas | Modelo padrão |
|---|---|---|---|
| Orquestrador | Planeja e delega na ordem certa (sessão principal) | todas | opus |
| `architect` | Plano de implementação e impacto arquitetural | leitura + Bash | opus |
| `code-writer` | Implementa seguindo os padrões do projeto | leitura + escrita + Bash | sonnet |
| `code-reviewer` | Revisa as mudanças locais | leitura + Bash | sonnet |
| `pr-reviewer` | Revisa commits e PRs contra a branch base | leitura + Bash | sonnet |
| `deployer` | Roda o deploy configurado, com checagens e confirmação | Read + Bash | sonnet |
| `release-summary` | Resume commits, PRs e mudanças entre versões | leitura + Bash + Write | haiku |
| `guardrail` | Barra segredos, arquivos protegidos e mudanças de risco | leitura + Bash | haiku |

O guardrail tem duas camadas: o **agente** (julgamento: escopo, dependências suspeitas, dados pessoais) e um **hook determinístico** que roda antes de cada comando ou edição e não pode ser "convencido" pelo modelo.

## Instalação

```bash
git clone <seu-repo>/agentkit && cd agentkit
pip install -e .            # ou: pipx install .
```

No Windows (PowerShell, com pyenv-win): `.\setup.ps1` usa o Python do `.python-version`, cria o `.venv` e instala tudo; depois `.venv\Scripts\Activate.ps1`.

Requer Python 3.10+. Para rodar os agentes você precisa do Claude Code (uso interativo) e/ou de `ANTHROPIC_API_KEY` (Agent SDK/CI).

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
```

### No Claude Code (dentro do projeto)
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
.claude/commands/*.md                 ← /ship, /review-pr, /release-notes, /deploy
.claude/hooks/agentkit_guardrail.py   ← hook PreToolUse (só biblioteca padrão)
.claude/agentkit/guardrails.json      ← política lida pelo hook
.claude/agentkit/manifest.json        ← hashes do que foi gerado
.claude/settings.json                 ← mesclado: hook, modelo do orquestrador, deny de arquivos protegidos
.github/workflows/agentkit-review.yml ← opcional
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

## RAG (próxima fase)

A configuração (`rag:` no YAML e aba RAG) já existe e é salva. A implementação planejada está descrita em `agentkit/rag/__init__.py`: indexador incremental, chroma/pgvector/qdrant com a mesma interface, busca híbrida com reranking e um servidor MCP `search_docs` registrado automaticamente para que todos os agentes consultem a base.

## Testes

```bash
pip install -e ".[dev]" && pytest
```
