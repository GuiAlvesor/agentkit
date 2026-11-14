# Manual do AgentKit

Este manual complementa o `README.md`. O README responde "o que é e como instalar"; este arquivo responde **como usar no dia a dia** — quando cada agente é acionado, como ler o que o pipeline está fazendo, e o que fazer quando algo dá errado.

> **Dois CLAUDE.md diferentes.** Este repositório tem um `CLAUDE.md` próprio, que serve ao desenvolvimento do **próprio AgentKit** (quem edita o kit). Cada projeto onde você rodar `agentkit init` ganha **outro** `CLAUDE.md`, gerado a partir dos templates, que serve ao uso do kit **dentro daquele projeto**. Quando este manual falar em "o `CLAUDE.md` gerado", é o segundo.

---

## 0. Primeiros passos

### Instalar o kit
```bash
git clone https://github.com/GuiAlvesor/agentkit.git && cd agentkit
.\setup.ps1          # Windows
./setup.sh           # macOS / Linux
```
O wizard verifica pré-requisitos, cria `.venv`, instala, roda os testes e oferece instalar o comando `agentkit` global com `pipx` (o Claude Code usa esse comando para iniciar o servidor do RAG). `-y` para modo silencioso (CI; pula o passo do `pipx`).

### Dois cenários de uso após instalar

| Cenário | Comando | O que acontece |
|---|---|---|
| **Usar o AgentKit neste próprio repositório** (desenvolvendo o kit) | abra `claude` aqui | Os arquivos `.claude/agents/*`, `.claude/settings.json` e `agentkit.yaml` já estão versionados — o kit se auto-aplica ao próprio código |
| **Usar o AgentKit em outro projeto** | `agentkit init /caminho/do/projeto` (ou `agentkit gui /caminho/do/projeto`) | Detecta a stack, gera `CLAUDE.md`, `.claude/agents/*`, hook, `settings.json` e `agentkit.yaml` naquele projeto |

### Diagnóstico a qualquer hora
```bash
agentkit doctor          # checa Python, git, Claude Code, API key, arquivos do projeto
```
Saída colorida. Exit code 0 = ok ou só avisos; 1 = há bloqueio.

---

## 1. Como o pipeline decide

O AgentKit **não** tem um pipeline fixo que dispara a cada prompt. Quem decide é o **orquestrador**, que é o próprio Claude Code rodando na sessão principal, lendo as regras do `CLAUDE.md` gerado no projeto.

### Modelo mental

Pense no orquestrador como um tech lead: ele ouve o pedido, decide se precisa de especialista, delega com contexto completo e junta os resultados. Cada subagente começa **sem** memória da conversa — tudo que ele precisa saber tem que vir na delegação.

### Regra de decisão por tipo de pedido

| Pedido típico | Pipeline |
|---|---|
| Uma pergunta, uma leitura, ajuste de uma linha | Orquestrador responde direto |
| Mudança de código pequena e local | `code-writer` → `code-reviewer` → `guardrail` |
| Mudança estrutural, módulo novo, mexer em dados/APIs | `architect` → `code-writer` → `code-reviewer` → `guardrail` |
| Revisar a branch atual ou um PR | `pr-reviewer` |
| "O que mudou entre v1 e v2?" | `release-summary` |
| Projeto novo com `requisitos/` preenchido | `/iniciar-projeto`: `requirements-analyst` → (você responde) → `architect` → `requirements-analyst` (backlog) → (você aprova) |
| Avançar no backlog | `/proxima-tarefa`: `requirements-analyst` marca `[~]` → `code-writer` → `code-reviewer` → `guardrail` → marca `[x]` |
| Antes de qualquer commit, PR ou deploy | `guardrail` (obrigatório) |
| Deploy | `deployer` (se habilitado; só com `--allow-deploy` no SDK, só depois de revisão) |

### Contratos invariantes

- **Agentes revisores não editam.** `architect`, `code-reviewer`, `pr-reviewer` e `guardrail` não têm `Write`/`Edit`. Quem escreve código é o `code-writer`; o `requirements-analyst` só escreve em `docs/plano/` e nunca na pasta `requisitos/`, que é sua.
- **Guardrail tem duas camadas.** Além do agente, o hook `.claude/hooks/agentkit_guardrail.py` roda em todo tool call (determinístico, só biblioteca padrão). O hook não pode ser "convencido".
- **Limite de ciclo.** Se o `code-reviewer` retornar "MUDANÇAS NECESSÁRIAS", o orquestrador volta ao `code-writer` com os achados. Máximo 3 ciclos — depois, pausa e pede ajuda humana.
- **Commit e push só a pedido.** O orquestrador nunca comita sozinho. Push nunca acontece sem pedido explícito.

### Slash commands disponíveis

| Comando | O que aciona |
|---|---|
| `/iniciar-projeto` | Requisitos → `PERGUNTAS.md` → `ARQUITETURA.md` → `BACKLOG.md`, parando para suas respostas e sua aprovação |
| `/proxima-tarefa [T-xxx]` | Uma tarefa do backlog com o fluxo completo; marca o status e para |
| `/ship <tarefa>` | Fluxo completo: `architect` (se necessário) → `code-writer` → `code-reviewer` → `guardrail` |
| `/review-pr [número]` | `pr-reviewer` + `guardrail` em paralelo |
| `/release-notes [v1.2.0..HEAD]` | `release-summary` |
| `/deploy staging\|production` | `deployer` (se habilitado, depois de revisão aprovada) |

Em todos os casos você também pode descrever o que quer em linguagem natural. O slash command é só um atalho que já traz o contexto esperado.

---

### Ciclo de desenvolvimento a partir dos requisitos

1. **Requisitos (você).** `agentkit init` cria `requisitos/README.md` e `requisitos/00-visao.md`. Preencha objetivo, usuários, escopo, `RF-xx`, `RNF-xx`, restrições e critérios de aceite. Pode acrescentar outros `.md` (telas, regras, integrações).
2. **`/iniciar-projeto`.** O analista grava `docs/plano/PERGUNTAS.md` com bloqueios, ambiguidades, lacunas e suposições. **O fluxo para** e mostra os bloqueios; responda no chat ou no próprio arquivo e rode de novo. Sem bloqueios, o `architect` propõe a arquitetura (gravada em `ARQUITETURA.md`) e o analista monta o `BACKLOG.md`. **O fluxo para** de novo para você aprovar.
3. **`/proxima-tarefa`.** Pega a primeira tarefa `[ ]` cujas dependências estão `[x]`, implementa com os critérios de aceite como definição de pronto, revisa, passa pelo guardrail, marca `[x]` (ou `[!]` com o motivo) e **para**. Commit só se você pedir ou se `kickoff.commit_each_task: true`.
4. **Acompanhar.** `agentkit backlog` lista as tarefas por marco, mostra o progresso e a próxima tarefa. `agentkit doctor` e a interface (aba Projeto) mostram em que etapa o projeto está.

Formato de uma tarefa no backlog (dá para editar à mão):
```
- [ ] T-003 · Login  (RF-03) · depende: T-002
  - Aceite: bloqueia após 5 tentativas; testes de sucesso e erro
```
Status: `[ ]` pendente · `[~]` em andamento · `[x]` feita · `[!]` bloqueada.

Requisitos mudaram? Edite `requisitos/` e rode `/iniciar-projeto` de novo: o analista atualiza perguntas e backlog sem desfazer as tarefas `[x]`.

### RAG: como os agentes consultam a documentação

Com `rag.enabled: true`, o Claude Code inicia o servidor `agentkit-rag` (registrado no `.mcp.json`) e os agentes que planejam, escrevem ou revisam ganham a ferramenta `search_docs`. Eles a usam para encontrar requisitos, decisões de arquitetura e trechos da documentação antes de supor algo.

- Sem chave nem pacote extra, a busca é por palavras (BM25). Com `VOYAGE_API_KEY` + `agentkit[rag]`, ou com `agentkit[rag-local]`, ela soma a busca por significado.
- O índice fica em `.agentkit/rag/` (fora do git) e é incremental. O servidor atualiza o índice ao iniciar; `agentkit rag index` força a atualização.
- Na primeira vez que o Claude Code encontrar o `.mcp.json`, ele pede para você aprovar o servidor `agentkit-rag`.
- Para medir a qualidade: crie `requisitos/rag-eval.yaml` com 20–30 perguntas reais (`pergunta:` + `esperado:` com o arquivo) e rode `agentkit rag eval`.

---

## 2. Cenários com transcrição

As transcrições abaixo são resumos fiéis do que o orquestrador faz. "Você" é quem está no Claude Code; "Orq." é o orquestrador (sessão principal); "Agente X" é um subagente delegado.

### Cenário A — pergunta simples (sem delegação)

```
Você:  qual a situação atual do projeto?
Orq.:  [lê git status, git log, roda pytest]
       Branch main, 3 commits, 4 arquivos modificados sem commit.
       Testes: 16 passed. Quer o diff?
```

Nenhum subagente foi acionado. Pedidos de leitura e diagnóstico resolvem direto.

### Cenário B — mudança pequena com revisão e commit

```
Você:  arruma o encoding do subprocess do git em detect.py — deve ser UTF-8

Orq.:  [edita detect.py: passa encoding="utf-8", errors="replace"]
       [roda pytest — 16 passed]
       [delega code-reviewer e guardrail em paralelo]

code-reviewer:  APROVADO. Mudança mínima, cobertura mantida.
guardrail:      GUARDRAIL: PASSA. Nenhum segredo ou caminho protegido.

Orq.:  Revisão limpa. Posso commitar?
Você:  sim
Orq.:  [git commit com Conventional Commits]
       Commit abc1234 na main. Nenhum push feito.
```

Mesmo em mudança trivial, o `guardrail` roda **antes** do commit.

### Cenário C — mudança estrutural com `architect`

```
Você:  /ship adicionar índice incremental de markdown para o RAG

Orq.:  [delega architect]
architect:  Plano em 4 passos:
            1. agentkit/rag/indexer.py (chunking por heading + hash por arquivo)
            2. agentkit/rag/store.py (interface já existe, implementar chroma)
            3. CLI: agentkit rag index .
            4. Testes com fixture de repo pequeno
            Impacto: toca rag/__init__.py e cli.py.

Orq.:  [delega code-writer com o plano]
code-writer:  [cria indexer.py, store.py, estende cli.py, adiciona testes]
              [roda pytest — 18 passed]

Orq.:  [delega code-reviewer]
code-reviewer:  MUDANÇAS NECESSÁRIAS. Chunker não trata arquivos
                sem heading (quebra em docs sem título).

Orq.:  [delega code-writer com o achado — ciclo 2/3]
code-writer:  [adiciona fallback: arquivo sem heading vira um chunk único]

Orq.:  [delega code-reviewer — ciclo 2/3]
code-reviewer:  APROVADO.

Orq.:  [delega guardrail]
guardrail:  GUARDRAIL: PASSA.

Orq.:  Pronto, pode commitar?
```

O `architect` produz o plano **antes** de qualquer edição. O ciclo revisor↔writer pode acontecer até 3 vezes; depois disso, o orquestrador para e pede ajuda.

### Cenário D — revisão de PR

```
Você:  /review-pr 42

Orq.:  [delega pr-reviewer e guardrail em paralelo com o PR #42]
pr-reviewer:  Mensagens de commit ok. Escopo: 3 arquivos, 1 teste novo.
              Risco: médio — mexe em migração de banco.
              Não vi rollback plan na descrição.
guardrail:    GUARDRAIL: PASSA.

Orq.:  Resumo do pr-reviewer + guardrail. Recomendação: antes de
       merge, documentar rollback no corpo do PR.
```

O `pr-reviewer` não faz merge. Ele avalia e devolve veredito. Merge é decisão sua.

---

## 3. Troubleshooting

### O guardrail bloqueou e eu quero ver o porquê

1. **Agente guardrail** sempre diz a razão na saída. A primeira linha é `GUARDRAIL: PASSA` ou `GUARDRAIL: BLOQUEIA`; abaixo vem a lista de achados.
2. **Hook determinístico** registra em `.claude/agentkit/guardrail.log` (gitignorado). Abra o log para ver o comando/edição que foi barrada e o motivo (regex, caminho protegido, comando perigoso).
3. **Política** vive em `.claude/agentkit/guardrails.json`. Esse arquivo é **gerado** a partir do `agentkit.yaml` e regravado a cada `agentkit install` — nunca edite o JSON diretamente, as mudanças serão perdidas. Se um bloqueio é falso positivo (ex.: você precisa mesmo editar um arquivo que casa com o padrão), edite o `agentkit.yaml` na aba Guardrails e rode `agentkit install`.

Nunca contorne o hook com `--no-verify` ou editando o próprio hook. Se a regra está errada, corrija a regra.

### `code-reviewer` retornou "MUDANÇAS NECESSÁRIAS" três vezes

O orquestrador para no terceiro ciclo. Opções:

- **Leia os três vereditos.** Se o mesmo ponto está sendo citado, o `code-writer` provavelmente não entendeu a correção — reescreva o pedido com um exemplo concreto.
- **Divida a tarefa.** Se cada ciclo encontrou um problema diferente, a mudança está grande demais para uma iteração — peça ao `architect` para quebrar em passos menores.
- **Decida manualmente.** Em divergência de estilo (não de correção), você pode aprovar com uma instrução direta: "faça do jeito do ciclo 2, ignore a sugestão do ciclo 3 sobre X".

### Hook falhou com erro de encoding no Windows

Causa quase sempre: cp1252 vs UTF-8. O hook abre arquivos com `encoding="utf-8"` e lê stdin/stdout em UTF-8. Se mesmo assim falhar:

1. Confirme que o `setup.ps1` rodou e criou `.venv` com o Python do `.python-version`.
2. Verifique se o arquivo que foi editado foi salvo em "ANSI" (cp1252) por algum editor. A instalação regrava em UTF-8, mas edições manuais podem reintroduzir cp1252.
3. `agentkit install --force` regrava os arquivos gerados em UTF-8.

### Modelo "inherit" não está claro

No `agentkit.yaml`, `model: inherit` significa "o agente usa o mesmo modelo da sessão principal (orquestrador)". Útil para `code-reviewer` quando você quer alinhar o rigor da revisão com a complexidade do que o orquestrador está usando. Aceita também ID completo (`claude-opus-5-5`) ou apelido (`opus`, `sonnet`, `haiku`).

### Quero adicionar um agente novo

1. Crie `agentkit/templates/agents/<nome>.md` com frontmatter (`name`, `description`, `tools`, `model`) e corpo.
2. Registre em `agentkit/defaults.py` no catálogo `AGENTS` (ferramentas padrão, modelo padrão, resumo).
3. Se ele participa do fluxo padrão, edite `agentkit/templates/orchestrator.md` adicionando o passo com `{% if "<nome>" in enabled %}`.
4. Rode `pytest` — os testes checam que o frontmatter é YAML válido e que nenhuma tag Jinja vaza no arquivo gerado.
5. Em projetos já instalados: `agentkit install` traz o novo agente (com `--force` se você editou os existentes à mão e eles ficaram em conflito).

### Quero mudar a ordem do pipeline

A ordem está no template `agentkit/templates/orchestrator.md` e é renderizada para o `CLAUDE.md` gerado. Mude o template, reinstale, e o novo fluxo vale em todos os projetos. Para mudar só em **um** projeto, edite a seção entre `<!-- agentkit:start -->` e `<!-- agentkit:end -->` do `CLAUDE.md` daquele projeto — ao reinstalar, o AgentKit só regrava essa seção se você não a tiver editado à mão; se editou, a versão nova vai para `CLAUDE.md.agentkit-new`.

### O agente não encontra a ferramenta `search_docs`
- `agentkit doctor` mostra se o comando do servidor (`rag.mcp_command`, padrão `agentkit`) está no PATH. Se o AgentKit só existe no `.venv` dele, ative esse ambiente antes de abrir o `claude` ou aponte `rag.mcp_command` para o executável completo (ex.: `C:\ferramentas\agentkit\.venv\Scripts\agentkit.exe`).
- No Claude Code, `/mcp` lista os servidores; confirme que `agentkit-rag` está aprovado e conectado.
- Depois de ligar o RAG, rode `agentkit install` para regerar `.mcp.json` e os agentes.

### `agentkit rag search` não acha o que eu sei que está lá
- `agentkit rag status`: o arquivo está nas fontes (`rag.sources`)? Está pendente de indexação?
- A busca por palavras precisa de termos que aparecem no texto. Com embeddings (Voyage ou local), perguntas com outras palavras também funcionam.

### A interface gráfica não abre / porta ocupada

`agentkit gui` usa a porta 8765 e só aceita conexões do localhost. Se a porta estiver ocupada, feche a instância anterior ou use `agentkit gui --port 8766`. A interface não tem autenticação porque só aceita `Host: localhost` — nunca exponha essa porta na rede.

### Testes falham com mensagem sobre CRLF

Git no Windows avisa `LF will be replaced by CRLF`. Isso é só aviso de `core.autocrlf`, não é erro. Se os testes realmente falharem com mismatch de linha, provavelmente um arquivo foi salvo com CRLF e o teste compara com LF — a função `read_user_text` em `installer.py` normaliza para LF na leitura, então grave em UTF-8 sem forçar CRLF.
