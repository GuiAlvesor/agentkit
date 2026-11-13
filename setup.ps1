# Prepara o ambiente de desenvolvimento do AgentKit no Windows usando pyenv-win.
# Uso (PowerShell, na pasta do projeto):  .\setup.ps1
# Se o PowerShell bloquear o script:      Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. Descobre o Python: pyenv (versão do .python-version) ou, na falta dele, o python do PATH
$py = $null
if (Get-Command pyenv -ErrorAction SilentlyContinue) {
    if (Test-Path .python-version) {
        $ver = (Get-Content .python-version -TotalCount 1).Trim()
        if (-not ((pyenv versions --bare) -contains $ver)) { pyenv install $ver }
    }
    $py = (pyenv which python | Select-Object -Last 1).Trim()
}
if (-not $py) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Error "Nem pyenv nem python encontrados. Instale o pyenv-win: https://github.com/pyenv-win/pyenv-win"
    }
    $py = "python"
}
Write-Host "Usando: $py ($(& $py --version))"

# 2. Ambiente virtual + dependências
if (-not (Test-Path .venv)) { & $py -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

Write-Host ""
Write-Host "Pronto. Próximos passos:" -ForegroundColor Green
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  pytest -q"
Write-Host "  claude            # abre o Claude Code com o contexto do chat (CLAUDE.md)"
Write-Host "  agentkit gui      # interface de configuração"
