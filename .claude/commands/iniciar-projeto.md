---
description: Inicia o ciclo de desenvolvimento a partir dos requisitos em requisitos/ (perguntas, arquitetura e backlog)
argument-hint: "[observações para os agentes]"
---
Vamos iniciar o desenvolvimento deste projeto a partir dos requisitos em `requisitos/`. Observações do usuário: $ARGUMENTS

Siga as etapas na ordem e **pare onde indicado**:

1. **Conferir a entrada.** Se `requisitos/` não existir ou só tiver o modelo sem preencher, diga ao usuário para preenchê-lo (`requisitos/00-visao.md`) e pare.
2. **Análise.** Delegue ao `requirements-analyst` a Tarefa 1 (gravar `docs/plano/PERGUNTAS.md`). Se `PERGUNTAS.md` já existir, peça para ele incorporar as respostas que o usuário escreveu lá.
3. **PARE se houver bloqueios.** Mostre as perguntas de bloqueio numeradas e peça as respostas (o usuário pode responder aqui no chat ou no próprio `PERGUNTAS.md`). Volte ao passo 2 com as respostas (o analista as registra no `PERGUNTAS.md`) até não haver bloqueio. Ambiguidades e lacunas sem resposta seguem com as suposições declaradas.
4. **Arquitetura.** Delegue ao `architect` a proposta de arquitetura para os requisitos (stack, se ainda não estiver definida; módulos; modelo de dados; integrações; testes; deploy), passando os requisitos e as respostas. Em seguida, peça ao `requirements-analyst` para gravar a proposta em `docs/plano/ARQUITETURA.md`, sem alterá-la (com as decisões como ADRs curtos).
5. **Backlog.** Delegue ao `requirements-analyst` a Tarefa 2 (gravar `docs/plano/BACKLOG.md`).
6. **PARE para aprovação.** Mostre um resumo: arquitetura em 5 linhas, marcos e quantidade de tarefas, as 3 primeiras tarefas. Pergunte se pode seguir ou o que ajustar.

Não escreva código de produção neste comando. Para começar a implementar, o usuário roda `/proxima-tarefa`.
