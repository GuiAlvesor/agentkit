#!/usr/bin/env bash
# Prepara o ambiente de desenvolvimento do AgentKit no macOS/Linux usando pyenv.
# Uso (na pasta do projeto):  ./setup.sh
# Se não for executável:      chmod +x setup.sh
set -euo pipefail
cd "$(dirname "$0")"

# 1. Descobre o Python: pyenv (versão do .python-version) ou, na falta dele, o python3 do PATH
py=""
if command -v pyenv >/dev/null 2>&1; then
    if [ -f .python-version ]; then
        ver="$(head -n 1 .python-version | tr -d '[:space:]')"
        if ! pyenv versions --bare | grep -qx "$ver"; then
            pyenv install "$ver"
        fi
        # usa o caminho direto do prefix para não depender do shim estar atualizado
        py="$(pyenv prefix "$ver")/bin/python3"
    else
        py="$(pyenv which python | tail -n 1)"
    fi
fi
if [ -z "$py" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Nem pyenv nem python3 encontrados. Instale o pyenv: https://github.com/pyenv/pyenv" >&2
        exit 1
    fi
    py="python3"
fi
echo "Usando: $py ($("$py" --version))"

# 2. Ambiente virtual + dependências
if [ ! -d .venv ]; then
    "$py" -m venv .venv
fi
./.venv/bin/python -m pip install --upgrade pip >/dev/null
./.venv/bin/python -m pip install -e ".[dev]"

echo
echo "Pronto. Próximos passos:"
echo "  source .venv/bin/activate"
echo "  pytest -q"
echo "  claude            # abre o Claude Code com o contexto do chat (CLAUDE.md)"
echo "  agentkit gui      # interface de configuração"
