---
description: Executa a próxima tarefa do backlog ({{ k.plan_dir }}/BACKLOG.md) com o fluxo completo de agentes e para para revisão
argument-hint: "[T-xxx (opcional): tarefa específica]"
---
Execute **uma** tarefa do backlog `{{ k.plan_dir }}/BACKLOG.md`. Tarefa pedida: $ARGUMENTS (se vazio, a próxima disponível).

1. **Escolher.** Se `BACKLOG.md` não existir, diga para rodar `/iniciar-projeto` e pare. Use a tarefa pedida ou a primeira `[ ]` cujas dependências estão todas `[x]` (`agentkit backlog` mostra isso). Se houver uma tarefa `[~]` (em andamento), pergunte se deve retomá-la.
2. **Marcar em andamento.** Peça ao `requirements-analyst` (Tarefa 3) para mudar o marcador da tarefa para `[~]`.
3. **Contexto.** Reúna para os agentes: a tarefa com os critérios de aceite, os RFs ligados (de `{{ k.dir }}/`), as decisões de `{{ k.plan_dir }}/ARQUITETURA.md` e o que as tarefas anteriores já criaram.
4. **Fluxo padrão** (seção "Fluxo de agentes" do CLAUDE.md): `architect` só se a tarefa exigir decisão estrutural nova → `code-writer` (com os critérios de aceite como definição de pronto, incluindo testes) → `code-reviewer` (até 3 ciclos) → `guardrail`.
5. **Concluir.** O `requirements-analyst` atualiza o marcador no backlog:
   - Aprovado: marque `[x]`.
   - Revisão sem acordo após 3 ciclos, guardrail BLOQUEIA ou faltou informação: marque `[!]`, escreva `- Bloqueio: <motivo>` abaixo da tarefa e pare.
{%- if k.commit_each_task %}
   - Com a tarefa `[x]`, faça um commit (Conventional Commits) com a mensagem `<tipo>: <título> (T-xxx)`. Não faça push.
{%- else %}
   - Não faça commit; o usuário decide (ele pode pedir "commit").
{%- endif %}
6. **PARE.** Responda com: tarefa concluída, arquivos alterados, vereditos de revisão e guardrail, progresso (X de Y feitas) e qual é a próxima tarefa. Não comece a próxima sem o usuário pedir.
