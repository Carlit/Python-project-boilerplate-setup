<#
.SYNOPSIS
    Prépare l'environnement de développement local (Windows / PowerShell).

.DESCRIPTION
    Crée le venv .venv, met pip à jour, installe les dépendances runtime et dev,
    puis copie .env.example vers .env s'il est absent.
    Le script s'arrête en erreur si une étape pip échoue.

.EXAMPLE
    .\scripts\bootstrap.ps1
    .\scripts\bootstrap.ps1 -Recreate
#>

[CmdletBinding()]
param(
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'

# Force l'UTF-8 en sortie : sans cela, PowerShell 5.1 affiche les accents en
# mojibake dans certaines consoles.
$OutputEncoding = [System.Text.Encoding]::UTF8
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    Write-Verbose "Encodage console inchangé : $($_.Exception.Message)"
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPath = Join-Path $root '.venv'

function Invoke-Step {
    <#
    .SYNOPSIS
        Exécute une commande externe et interrompt le script si elle échoue.
        $ErrorActionPreference ne couvre pas le code de retour des exécutables
        natifs : la vérification de $LASTEXITCODE est indispensable.
    #>
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Action
    )

    Write-Host $Label -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Label : échec (code $LASTEXITCODE)."
    }
}

if ($Recreate -and (Test-Path $venvPath)) {
    Write-Host 'Suppression du venv existant...' -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}

if (-not (Test-Path $venvPath)) {
    Invoke-Step 'Création du venv .venv...' { python -m venv .venv }
}

$python = Join-Path $venvPath 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Interpréteur introuvable dans le venv : $python"
}

$version = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
Write-Host "Interpréteur du venv : Python $version" -ForegroundColor DarkGray

Invoke-Step 'Mise à jour de pip...' { & $python -m pip install --upgrade pip }

Invoke-Step 'Installation des dépendances...' {
    & $python -m pip install -r requirements.txt -r requirements-dev.txt
}

if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item '.env.example' '.env'
    Write-Host '.env créé depuis .env.example — renseigner les valeurs.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Environnement prêt.' -ForegroundColor Green
Write-Host 'Activation    : .\.venv\Scripts\Activate.ps1'
Write-Host 'Tests         : python -m pytest'
Write-Host 'Vérification  : python -m src.main --check all'