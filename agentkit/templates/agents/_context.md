## Contexto do projeto
- Projeto: **{{ p.name }}**{% if p.description %} — {{ p.description }}{% endif %}
{%- if p.language %}
- Linguagem: {{ p.language }}{% if p.frameworks %} ({{ p.frameworks | join(", ") }}){% endif %}
{%- endif %}
- Branch base: `{{ p.base_branch }}`
- Leia `CLAUDE.md` na raiz antes de começar; ele tem as regras e convenções do projeto.
{%- if c.test or c.lint or c.typecheck or c.build %}

Comandos do projeto (use exatamente estes):
{%- if c.test %}
- Testes: `{{ c.test }}`
{%- endif %}
{%- if c.lint %}
- Lint: `{{ c.lint }}`
{%- endif %}
{%- if c.typecheck %}
- Tipos: `{{ c.typecheck }}`
{%- endif %}
{%- if c.build %}
- Build: `{{ c.build }}`
{%- endif %}
{%- endif %}
{%- if p.conventions %}

Convenções específicas:
{{ p.conventions }}
{%- endif %}
{%- if rag.enabled %}

Base de conhecimento (RAG): a ferramenta `search_docs` (servidor MCP `agentkit-rag`) busca em requisitos, documentação e plano do projeto ({{ rag.sources | join(", ") }}). Quando ela estiver disponível para você, use-a antes de supor regras de negócio, requisitos ou decisões já tomadas, e cite o arquivo de origem.
{%- endif %}
