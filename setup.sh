#!/usr/bin/env bash
# Instalação guiada do AgentKit no macOS/Linux.
# Uso:  ./setup.sh           (interativo)
#       ./setup.sh -y        (silencioso, assume sim; ideal para CI)
# Se não for executável:     chmod +x setup.sh    (ou invoque:  bash setup.sh)
set -euo pipefail
cd "$(dirname "$0")"

YES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) YES=1 ;;
    esac
done

# ─── UI helpers ────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    CYAN=$'\033[1;36m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'
    RED=$'\033[1;31m'; DIM=$'\033[2m'; RST=$'\033[0m'
else
    CYAN=''; GREEN=''; YELLOW=''; RED=''; DIM=''; RST=''
fi
step=0
total=7
header() {
    printf '\n%s┌─ AgentKit · instalação guiada ──────────────────────────────%s\n' "$CYAN" "$RST"
    printf '%s│ %s%s\n' "$CYAN" "$1" "$RST"
    printf '%s└──────────────────────────────────────────────────────────────%s\n' "$CYAN" "$RST"
}
step()   { step=$((step + 1)); printf '%s[%d/%d] %s%s\n' "$CYAN" "$step" "$total" "$1" "$RST"; }
ok()     { printf '       %s✓ %s%s\n' "$GREEN" "$1" "$RST"; }
warn()   { printf '       %s! %s%s\n' "$YELLOW" "$1" "$RST"; }
fail()   { printf '       %s✗ %s%s\n' "$RED" "$1" "$RST"; }
hint()   { printf '         %s→ %s%s\n' "$DIM" "$1" "$RST"; }
ask() {
    local prompt="$1" default="${2:-s}" resp
    # Modo -y: usa a resposta padrão (assim "abrir a GUI?", padrão não, não trava o CI)
    if [ "$YES" -eq 1 ]; then [ "$default" = "s" ]; return; fi
    local suffix="[S/n]"; [ "$default" = "n" ] && suffix="[s/N]"
    read -r -p "       ? $prompt $suffix " resp || resp=""
    [ -z "$resp" ] && resp="$default"
    case "$resp" in [sSyY]*) return 0 ;; *) return 1 ;; esac
}

header "Prepara seu ambiente para rodar o AgentKit"

# ─── 1. Python ────────────────────────────────────────────────
step "Verificando Python >= 3.10"
py=""
if command -v pyenv >/dev/null 2>&1; then
    if [ -f .python-version ]; then
        ver="$(head -n 1 .python-version | tr -d '[:space:]')"
        if ! pyenv versions --bare | grep -qx "$ver"; then
            hint "Instalando Python $ver via pyenv (pode demorar alguns minutos)..."
            pyenv install "$ver"
        fi
        py="$(pyenv prefix "$ver")/bin/python3"
    else
        py="$(pyenv which python | tail -n 1)"
    fi
fi
if [ -z "$py" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        fail "Nem pyenv nem python3 encontrados no PATH."
        hint "Instale pyenv: https://github.com/pyenv/pyenv ou Python 3.12 do sistema."
        exit 1
    fi
    py="python3"
    warn "pyenv não encontrado; usando o python3 do PATH."
    hint "Recomendamos pyenv para fixar a versão do projeto."
fi
version="$("$py" --version 2>&1)"
minor="$(echo "$version" | sed -n 's/Python 3\.\([0-9]*\).*/\1/p')"
if [ -z "$minor" ] || [ "$minor" -lt 10 ]; then
    fail "$version (precisa ser >= 3.10)"
    hint "Instale Python 3.12 e tente de novo."
    exit 1
fi
ok "$version ($py)"

# ─── 2. git ────────────────────────────────────────────────
step "Verificando git"
if ! command -v git >/dev/null 2>&1; then
    fail "git não está no PATH."
    hint "Instale: https://git-scm.com/downloads"
    exit 1
fi
ok "$(git --version)"

# ─── 3. Claude Code CLI (opcional, mas recomendado) ─────────
step "Verificando Claude Code CLI (opcional)"
if command -v claude >/dev/null 2>&1; then
    ok "$(claude --version 2>&1 | tr '\n' ' ')"
else
    warn "Claude Code CLI não encontrado."
    hint "Para uso interativo: npm install -g @anthropic-ai/claude-code"
    hint "Para uso só via Agent SDK: defina ANTHROPIC_API_KEY (próximo passo)."
    if ! ask "Prosseguir mesmo assim?" "s"; then exit 1; fi
fi

# ─── 4. ANTHROPIC_API_KEY (opcional) ────────────────────────
step "Verificando ANTHROPIC_API_KEY (opcional)"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    ok "definida"
else
    warn "ANTHROPIC_API_KEY não está definida."
    hint "Necessária só para Agent SDK/CI. Para definir nesta sessão:"
    hint "    export ANTHROPIC_API_KEY=\"sua-chave\""
    hint "Para definir permanentemente, adicione a linha acima ao ~/.bashrc ou ~/.zshrc."
fi

# ─── 5. Ambiente virtual + dependências ─────────────────────
step "Criando .venv e instalando dependências"
if [ ! -d .venv ]; then
    "$py" -m venv .venv
    ok ".venv criado"
else
    ok ".venv já existe (reutilizando)"
fi
hint "pip install -e \".[dev]\" (pode demorar na primeira vez)"
./.venv/bin/python -m pip install --upgrade pip >/dev/null
# Guarda a saída para mostrar o erro completo se algo falhar (e não deixar o set -e
# encerrar o script em silêncio).
if ! out="$(./.venv/bin/python -m pip install -e ".[dev]" 2>&1)"; then
    echo "$out" | tail -n 30
    fail "pip install falhou (saída acima)."
    exit 1
fi
echo "$out" | grep -E '^(Successfully|Installing|Building)' | sed 's/^/       /' || true
ok "dependências instaladas"

# ─── 6. Testes e doctor ─────────────────────────────────────
step "Validando a instalação"
if ! out="$(./.venv/bin/python -m pytest -q 2>&1)"; then
    echo "$out" | tail -n 30
    fail "pytest falhou (saída acima)."
    exit 1
fi
echo "$out" | grep -E 'passed|failed|error' | sed 's/^/       /' || true
ok "testes passaram"

# ─── 7. Comando agentkit global (para o RAG no Claude Code) ──
step "Comando agentkit no PATH (necessário para o RAG no Claude Code)"
# O Claude Code inicia o servidor de busca (.mcp.json) com o comando "agentkit";
# o do .venv não fica visível fora dele, então instalamos uma cópia global com pipx.
if command -v agentkit >/dev/null 2>&1 || [ -x "$HOME/.local/bin/agentkit" ]; then
    ok "já instalado ($(command -v agentkit || echo "$HOME/.local/bin/agentkit"))"
elif [ "$YES" -eq 1 ]; then
    warn "pulado no modo -y (CI não precisa)."
    hint "Para instalar depois: $py -m pip install --user pipx && $py -m pipx install --editable . --python $py"
elif ask "Instalar o comando agentkit global com pipx? (editável: acompanha este código)" "s"; then
    if command -v pipx >/dev/null 2>&1; then pipx_cmd=(pipx); else
        "$py" -m pip install --user --quiet pipx >/dev/null 2>&1 || true
        pipx_cmd=("$py" -m pipx)
    fi
    if "${pipx_cmd[@]}" install --editable . --python "$py"; then
        "${pipx_cmd[@]}" ensurepath >/dev/null 2>&1 || true
        ok "agentkit instalado em ~/.local/bin"
        hint "Abra um terminal novo (e reabra o Claude Code) para o PATH valer."
    else
        fail "pipx install falhou (saída acima). O kit funciona; só o RAG no Claude Code depende disso."
        hint "Em distros com Python gerenciado pelo sistema: sudo apt install pipx (ou brew install pipx)."
    fi
else
    warn "pulado. Sem ele, o RAG funciona pela linha de comando, mas não dentro do Claude Code."
fi

echo
./.venv/bin/python -m agentkit doctor

# ─── Fim ────────────────────────────────────────────────────
echo
printf '%s┌─ Pronto! Próximos passos ──────────────────────────────────%s\n' "$GREEN" "$RST"
printf '%s│  • Ativar o ambiente:       source .venv/bin/activate%s\n' "$GREEN" "$RST"
printf '%s│  • Usar neste repositório:  claude%s\n' "$GREEN" "$RST"
printf '%s│  • Instalar em outro projeto: agentkit init /caminho/projeto%s\n' "$GREEN" "$RST"
printf '%s│    → preencha requisitos/00-visao.md e rode /iniciar-projeto no Claude Code%s\n' "$GREEN" "$RST"
printf '%s│  • Busca na documentação:   agentkit rag index; agentkit rag search "pergunta"%s\n' "$GREEN" "$RST"
printf '%s│  • Interface gráfica:       agentkit gui%s\n' "$GREEN" "$RST"
printf '%s│  • Doctor a qualquer hora:  agentkit doctor%s\n' "$GREEN" "$RST"
printf '%s└────────────────────────────────────────────────────────────%s\n' "$GREEN" "$RST"

if ask "Abrir a interface gráfica agora?" "n"; then
    ./.venv/bin/agentkit gui
fi
