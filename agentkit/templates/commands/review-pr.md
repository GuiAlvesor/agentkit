---
description: Revisa a branch atual (ou o PR informado) com pr-reviewer e guardrail
argument-hint: "[número do PR]"
---
Delegue ao agente `pr-reviewer` a revisão de: $ARGUMENTS (se vazio, a branch atual contra `{{ p.base_branch }}`).
{%- if "guardrail" in enabled %}
Em paralelo, delegue ao `guardrail` a verificação do mesmo diff.
{%- endif %}
Junte as duas respostas em um único comentário de revisão em Markdown. Não publique o comentário; mostre-o para mim.
