---
description: Deploy com checagens (guardrail + deployer)
argument-hint: "staging | production"
---
Quero fazer deploy em: $ARGUMENTS (se vazio, pergunte o ambiente).
{%- if "guardrail" in enabled %}
1. Delegue ao `guardrail` a verificação do estado atual. Se bloquear, pare.
{%- endif %}
2. Delegue ao `deployer`, informando o ambiente e o resultado do guardrail.
