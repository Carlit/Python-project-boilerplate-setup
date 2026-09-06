#!/usr/bin/env bash
# Prépare l'environnement de développement local (Linux / macOS / WSL).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
    echo "Création du venv .venv..."
    python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo ".env créé depuis .env.example — renseigner les valeurs."
fi

echo
echo "Environnement prêt."
echo "Activation   : source .venv/bin/activate"
echo "Vérification : python -m src.main --check all"
