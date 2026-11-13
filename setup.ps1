# Prepara o ambiente de desenvolvimento do AgentKit no Windows.
# Uso (PowerShell, na pasta do projeto):  .\setup.ps1
# Se o PowerShell bloquear o script:      Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python não encontrado. Instale o Python 3.10+ (python.org) marcando 'Add python.exe to PATH'."
}

if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

if (-not (Test-Path .git)) {
    git init -q 2>$null
    git add -A 2>$null
    git commit -qm "chore: AgentKit inicial" 2>$null
}

Write-Host ""
Write-Host "Pronto. Próximos passos:" -ForegroundColor Green
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  pytest -q"
Write-Host "  claude            # abre o Claude Code com o contexto deste chat (CLAUDE.md)"
Write-Host "  agentkit gui      # interface de configuração"
