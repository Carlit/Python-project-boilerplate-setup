<#
.SYNOPSIS
    Prépare l'environnement de développement local (Windows / PowerShell).

.DESCRIPTION
    Crée le venv .venv, met pip à jour, installe les dépendances runtime et dev,
    puis copie .env.example vers .env s'il est absent.

.EXAMPLE
    .\scripts\bootstrap.ps1
#>

[CmdletBinding()]
param(
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPath = Join-Path $root '.venv'

if ($Recreate -and (Test-Path $venvPath)) {
    Write-Host 'Suppression du venv existant...' -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}

if (-not (Test-Path $venvPath)) {
    Write-Host 'Création du venv .venv...' -ForegroundColor Cyan
    python -m venv .venv
}

$python = Join-Path $venvPath 'Scripts\python.exe'

Write-Host 'Mise à jour de pip...' -ForegroundColor Cyan
& $python -m pip install --upgrade pip

Write-Host 'Installation des dépendances...' -ForegroundColor Cyan
& $python -m pip install -r requirements.txt -r requirements-dev.txt

if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item '.env.example' '.env'
    Write-Host '.env créé depuis .env.example — renseigner les valeurs.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Environnement prêt.' -ForegroundColor Green
Write-Host 'Activation : .\.venv\Scripts\Activate.ps1'
Write-Host 'Vérification : python -m src.main --check all'
