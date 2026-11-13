# {{ p.name }}
{% if p.description %}
{{ p.description }}
{% endif %}
- Linguagem: {{ p.language or "não informada" }}{% if p.frameworks %} · Frameworks: {{ p.frameworks | join(", ") }}{% endif %}
- Branch base: `{{ p.base_branch }}`

## Comandos
| Ação | Comando |
|---|---|
{%- for key, label in [("install","Instalar"),("test","Testes"),("lint","Lint"),("typecheck","Tipos"),("build","Build"),("deploy_staging","Deploy staging"),("deploy_production","Deploy produção"),("health_check","Health check"),("rollback","Rollback")] %}
{%- if c[key] %}
| {{ label }} | `{{ c[key] }}` |
{%- endif %}
{%- endfor %}
{% if p.conventions %}
## Convenções
{{ p.conventions }}
{% endif %}
## Regras de segurança
- Não altere: {{ g.protected_paths | join(", ") }}.
- Nunca grave segredos no código ou em logs.
- Comandos perigosos são bloqueados pelo hook `.claude/hooks/agentkit_guardrail.py`; não tente contorná-lo.

{{ orchestrator }}
