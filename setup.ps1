# Instalação guiada do AgentKit no Windows.
# Uso:    .\setup.ps1          (interativo, com confirmações)
#         .\setup.ps1 -Yes     (silencioso, assume sim em todas as perguntas; ideal para CI)
# Se o PowerShell bloquear o script:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
[CmdletBinding()]
param(
    [Alias('y')]
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ─── UI helpers ────────────────────────────────────────────────
$script:step = 0
$script:total = 7
function Header($text) {
    Write-Host ""
    Write-Host "┌─ AgentKit · instalação guiada " -NoNewline -ForegroundColor Cyan
    Write-Host ("─" * (28 - [math]::Min(28, $text.Length))) -ForegroundColor Cyan
    Write-Host "│ $text" -ForegroundColor Cyan
    Write-Host "└$('─' * 60)" -ForegroundColor Cyan
}
function Step($label) {
    $script:step++
    Write-Host ("[{0}/{1}] {2}" -f $script:step, $script:total, $label) -ForegroundColor Cyan
}
function Ok($msg)    { Write-Host "       ✓ $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "       ! $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "       ✗ $msg" -ForegroundColor Red }
function Hint($msg)  { Write-Host "         → $msg" -ForegroundColor DarkGray }
function Ask($prompt, $default = "s") {
    # Modo -Yes: usa a resposta padrão (assim "abrir a GUI?", padrão não, não trava o CI)
    if ($Yes) { return $default -eq "s" }
    $suffix = if ($default -eq "s") { "[S/n]" } else { "[s/N]" }
    $resp = Read-Host "       ? $prompt $suffix"
    if (-not $resp) { $resp = $default }
    return $resp -match '^[sSyY]'
}

Header "Prepara seu ambiente para rodar o AgentKit"

# ─── 1. Python ────────────────────────────────────────────────
Step "Verificando Python >= 3.10"
$py = $null
if (Get-Command pyenv -ErrorAction SilentlyContinue) {
    if (Test-Path .python-version) {
        $ver = (Get-Content .python-version -TotalCount 1).Trim()
        if (-not ((pyenv versions --bare) -contains $ver)) {
            Hint "Instalando Python $ver via pyenv (isso pode demorar alguns minutos)..."
            pyenv install $ver
        }
    }
    $py = (pyenv which python | Select-Object -Last 1).Trim()
}
if (-not $py) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Fail "Nem pyenv nem python encontrados no PATH."
        Hint "Instale: https://www.python.org/downloads/ (ou pyenv-win: https://github.com/pyenv-win/pyenv-win)"
        exit 1
    }
    $py = "python"
    Warn "pyenv-win não encontrado; usando o Python do PATH."
    Hint "Recomendamos pyenv-win para fixar a versão do projeto (3.12.10)."
}
$versionLine = & $py --version 2>&1
if ($versionLine -match '(\d+)\.(\d+)') {
    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Fail "$versionLine (precisa ser >= 3.10)"
        Hint "Instale Python 3.12 e tente de novo."
        exit 1
    }
}
Ok "$versionLine ($py)"

# ─── 2. git ────────────────────────────────────────────────
Step "Verificando git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git não está no PATH."
    Hint "Instale: https://git-scm.com/download/win"
    exit 1
}
Ok (git --version)

# ─── 3. Claude Code CLI (opcional, mas recomendado) ─────────
Step "Verificando Claude Code CLI (opcional)"
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Ok ((claude --version) -replace '\r?\n', ' ')
} else {
    Warn "Claude Code CLI não encontrado."
    Hint "Para uso interativo: npm install -g @anthropic-ai/claude-code"
    Hint "Para uso só via Agent SDK: defina ANTHROPIC_API_KEY (próximo passo)."
    if (-not (Ask "Prosseguir mesmo assim?" "s")) { exit 1 }
}

# ─── 4. ANTHROPIC_API_KEY (opcional) ────────────────────────
Step "Verificando ANTHROPIC_API_KEY (opcional)"
if ($env:ANTHROPIC_API_KEY) {
    Ok "definida"
} else {
    Warn "ANTHROPIC_API_KEY não está definida."
    Hint "Necessária só para Agent SDK/CI. Para definir nesta sessão:"
    Hint "    `$env:ANTHROPIC_API_KEY = `"sua-chave`""
    Hint "Para definir permanentemente: [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY','...','User')"
}

# ─── 5. Ambiente virtual + dependências ─────────────────────
Step "Criando .venv e instalando dependências"
# No PowerShell 5.1, com "Stop", qualquer linha no stderr de um programa externo
# (ex.: o aviso "[notice]" do pip) aborta o script. Daqui em diante os erros são
# conferidos pelo $LASTEXITCODE.
$ErrorActionPreference = "Continue"
if (-not (Test-Path .venv)) {
    & $py -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "não foi possível criar o .venv."; exit 1 }
    Ok ".venv criado"
} else {
    Ok ".venv já existe (reutilizando)"
}
Hint "pip install -e `".[dev]`" (pode demorar na primeira vez)"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip 2>&1 | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]" 2>&1 | ForEach-Object {
    if ($_ -match '^(Successfully|Installing|Building)') { Write-Host "       $_" -ForegroundColor DarkGray }
}
if ($LASTEXITCODE -ne 0) {
    Fail "pip install falhou. Role para cima para ver o erro."
    exit 1
}
Ok "dependências instaladas"

# ─── 6. Testes e doctor ─────────────────────────────────────
Step "Validando a instalação"
& .\.venv\Scripts\python.exe -m pytest -q 2>&1 | ForEach-Object {
    if ($_ -match 'passed|failed|error') { Write-Host "       $_" -ForegroundColor DarkGray }
}
if ($LASTEXITCODE -ne 0) {
    Fail "pytest falhou. Role para cima para ver o erro."
    exit 1
}
Ok "testes passaram"

# ─── 7. Comando agentkit global (para o RAG no Claude Code) ──
Step "Comando agentkit no PATH (necessário para o RAG no Claude Code)"
# O Claude Code inicia o servidor de busca (.mcp.json) com o comando "agentkit";
# o do .venv não fica visível fora dele, então instalamos uma cópia global com pipx.
$global = Get-Command agentkit -ErrorAction SilentlyContinue
if (-not $global -and (Test-Path "$HOME\.local\bin\agentkit.exe")) { $global = "$HOME\.local\bin\agentkit.exe" }
if ($global) {
    Ok "já instalado ($(if ($global.Source) { $global.Source } else { $global }))"
} elseif ($Yes) {
    Warn "pulado no modo -Yes (CI não precisa)."
    Hint "Para instalar depois: $py -m pip install --user pipx; $py -m pipx install --editable . --python $py"
} elseif (Ask "Instalar o comando agentkit global com pipx? (editável: acompanha este código)" "s") {
    & $py -m pip install --user --quiet pipx 2>&1 | Out-Null
    & $py -m pipx install --editable . --python $py 2>&1 | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) {
        Fail "pipx install falhou (saída acima). O kit funciona; só o RAG no Claude Code depende disso."
    } else {
        & $py -m pipx ensurepath 2>&1 | Out-Null
        Ok "agentkit instalado em $HOME\.local\bin"
        Hint "Abra um terminal novo (e reabra o Claude Code) para o PATH valer."
    }
} else {
    Warn "pulado. Sem ele, o RAG funciona pela linha de comando, mas não dentro do Claude Code."
}

Write-Host ""
& .\.venv\Scripts\python.exe -m agentkit doctor

# ─── Fim ────────────────────────────────────────────────────
Write-Host ""
Write-Host "┌─ Pronto! Próximos passos ──────────────────────────────────" -ForegroundColor Green
Write-Host "│  • Ativar o ambiente:       .venv\Scripts\Activate.ps1" -ForegroundColor Green
Write-Host "│  • Usar neste repositório:  claude" -ForegroundColor Green
Write-Host "│  • Instalar em outro projeto: agentkit init C:\caminho\projeto" -ForegroundColor Green
Write-Host "│    → preencha requisitos\00-visao.md e rode /iniciar-projeto no Claude Code" -ForegroundColor Green
Write-Host "│  • Busca na documentação:   agentkit rag index; agentkit rag search `"pergunta`"" -ForegroundColor Green
Write-Host "│  • Interface gráfica:       agentkit gui" -ForegroundColor Green
Write-Host "│  • Doctor a qualquer hora:  agentkit doctor" -ForegroundColor Green
Write-Host "└────────────────────────────────────────────────────────────" -ForegroundColor Green

if (Ask "Abrir a interface gráfica agora?" "n") {
    & .\.venv\Scripts\agentkit.exe gui
}
