"""Catálogo de agentes e configuração padrão do AgentKit.

Tudo que é "portável" mora aqui: cada projeto só sobrescreve o que precisa
no próprio agentkit.yaml.
"""
from __future__ import annotations

import copy
import sys

# Aliases aceitos pelo Claude Code e pelo Agent SDK. Também é possível
# informar um ID completo (ex.: "claude-sonnet-5-5") na interface.
MODEL_OPTIONS = ["haiku", "sonnet", "opus", "inherit"]

# Metadados de cada agente. "tools" segue o princípio do menor privilégio.
AGENTS: dict[str, dict] = {
    "orchestrator": {
        "title": "Orquestrador",
        "summary": "Planeja a tarefa e delega aos outros agentes na ordem certa.",
        "tools": [],  # roda na sessão principal; não vira arquivo em .claude/agents
        "default_model": "opus",
        "main_thread": True,
    },
    "requirements-analyst": {
        "title": "Analista de requisitos",
        "summary": "Lê requisitos/, aponta lacunas e mantém o backlog de tarefas em docs/plano/.",
        "tools": ["Read", "Grep", "Glob", "Write", "Edit"],
        "default_model": "sonnet",
    },
    "architect": {
        "title": "Arquiteto",
        "summary": "Planeja mudanças estruturais e avalia impacto arquitetural.",
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "default_model": "opus",
    },
    "code-writer": {
        "title": "Escritor",
        "summary": "Implementa funcionalidades e correções seguindo os padrões do projeto.",
        "tools": ["Read", "Write", "Edit", "Grep", "Glob", "Bash"],
        "default_model": "sonnet",
    },
    "code-reviewer": {
        "title": "Revisor",
        "summary": "Revisa as mudanças locais: bugs, segurança, legibilidade e testes.",
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "default_model": "sonnet",
    },
    "pr-reviewer": {
        "title": "Revisor de commit/PR",
        "summary": "Revisa commits e pull requests contra a branch base.",
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "default_model": "sonnet",
    },
    "deployer": {
        "title": "Deployer",
        "summary": "Executa o deploy configurado com checagens e confirmação.",
        "tools": ["Read", "Bash"],
        "default_model": "sonnet",
    },
    "release-summary": {
        "title": "Release summary",
        "summary": "Resume commits, PRs e mudanças de código entre duas versões.",
        "tools": ["Read", "Grep", "Glob", "Bash", "Write"],
        "default_model": "haiku",
    },
    "guardrail": {
        "title": "Guardrail",
        "summary": "Barra segredos, caminhos protegidos e mudanças de risco antes do commit/deploy.",
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "default_model": "haiku",
    },
}

DEFAULT_CONFIG: dict = {
    "version": 2,
    "project": {
        "name": "",
        "description": "",
        "language": "",
        "frameworks": [],
        "base_branch": "main",
        "conventions": "",
        "commit_convention": "conventional",  # conventional | free
        "response_language": "português do Brasil",  # idioma das respostas, resumos e documentos dos agentes
    },
    "commands": {
        "install": "",
        "test": "",
        "lint": "",
        "typecheck": "",
        "build": "",
        "deploy_staging": "",
        "deploy_production": "",
        "health_check": "",
        "rollback": "",
    },
    "agents": {
        name: {
            "enabled": True,
            "model": meta["default_model"],
            "extra_instructions": "",
        }
        for name, meta in AGENTS.items()
    },
    "guardrails": {
        # no Windows "python3" costuma ser só o atalho da Microsoft Store
        "python_cmd": "python" if sys.platform == "win32" else "python3",
        "blocked_commands": [
            r"rm\s+-rf\s+(/|~|\$HOME)(\s|$)",
            r"git\s+push\s+.*(--force|-f)(\s|$)",
            r"git\s+reset\s+--hard\s+origin",
            r"DROP\s+(DATABASE|SCHEMA)",
            r"mkfs\.",
            r":\(\)\s*\{\s*:\|:&\s*\};:",
            r"curl[^|]*\|\s*(sudo\s+)?(ba)?sh",
        ],
        "confirm_commands": [
            r"git\s+push",
            r"(kubectl|helm)\s+(apply|delete|upgrade|rollback)",
            r"terraform\s+(apply|destroy)",
            r"(npm|pnpm|yarn)\s+publish",
            r"vercel\s+.*--prod",
        ],
        "protected_paths": [
            ".env",
            ".env.*",
            "**/*.pem",
            "**/*.key",
            "**/secrets/**",
            ".git/**",
        ],
        "scan_secrets": True,
        "require_confirmation_for_production": True,
        "max_files_per_change": 30,
    },
    "ci": {
        "github_actions": False,
        # como o CI instala o AgentKit (ajuste para o seu repositório ou índice privado)
        "install_spec": "agentkit @ git+https://github.com/GuiAlvesor/agentkit.git",
        "post_review_comment": True,
        "permission_mode": "acceptEdits",
        "max_turns": 40,
        "max_budget_usd": 5.0,
    },
    "rag": {
        "enabled": False,
        "provider": "local",  # local (SQLite, sem dependências) | chroma | pgvector | qdrant
        # auto: Voyage se houver VOYAGE_API_KEY; senão fastembed local, se instalado; senão só BM25
        "embedder": "auto",  # auto | voyage | local | none
        "embedding_model": "voyage-3",
        "local_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "rerank": False,  # reranking da Voyage (exige VOYAGE_API_KEY)
        "sources": ["requisitos/**/*.md", "docs/**/*.md", "README.md"],
        "chunk_size": 1200,
        "chunk_overlap": 150,
        "top_k": 6,
        "connection": "",  # pgvector/qdrant; use ${VARIAVEL} para não gravar credenciais
        "mcp_command": "agentkit",  # comando que inicia o servidor MCP (precisa estar no PATH)
    },
    "kickoff": {
        "dir": "requisitos",  # onde o usuário escreve os requisitos iniciais
        "plan_dir": "docs/plano",  # PERGUNTAS.md, ARQUITETURA.md e BACKLOG.md gerados pelos agentes
        "commit_each_task": False,  # /proxima-tarefa faz commit ao concluir cada tarefa
    },
}


# Agentes que ganham a ferramenta de busca do RAG quando rag.enabled = true
RAG_TOOL = "mcp__agentkit-rag__search_docs"
RAG_AGENTS = ("requirements-analyst", "architect", "code-writer", "code-reviewer", "pr-reviewer")


def default_config() -> dict:
    return copy.deepcopy(DEFAULT_CONFIG)
