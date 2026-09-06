"""Vérifie que le fichier `.env` couvre bien toutes les clés de `.env.example`.

Ne se connecte à aucune base et n'affiche aucune valeur : seuls les noms de
clés manquantes ou surnuméraires sont listés.

Usage :
    python scripts/check_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"
EXAMPLE_FILE: Final[Path] = PROJECT_ROOT / ".env.example"

_EXIT_OK: Final[int] = 0
_EXIT_FAILURE: Final[int] = 1


def read_keys(path: Path) -> set[str]:
    """Extrait les noms de variables d'un fichier au format dotenv.

    Args:
        path: Chemin du fichier à analyser.

    Returns:
        L'ensemble des noms de variables déclarés.
    """
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped: str = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def main() -> int:
    """Compare `.env` et `.env.example`.

    Returns:
        0 si la configuration est complète, 1 sinon.
    """
    if not EXAMPLE_FILE.is_file():
        print(f"Fichier modèle introuvable : {EXAMPLE_FILE}", file=sys.stderr)
        return _EXIT_FAILURE

    if not ENV_FILE.is_file():
        print(".env absent — copier .env.example en .env.", file=sys.stderr)
        return _EXIT_FAILURE

    expected: set[str] = read_keys(EXAMPLE_FILE)
    actual: set[str] = read_keys(ENV_FILE)

    missing: list[str] = sorted(expected - actual)
    extra: list[str] = sorted(actual - expected)

    for key in missing:
        print(f"MANQUANT  {key}")
    for key in extra:
        print(f"EN TROP   {key}")

    if missing:
        print(f"\n{len(missing)} clé(s) manquante(s).", file=sys.stderr)
        return _EXIT_FAILURE

    print(f"Configuration complète : {len(expected)} clé(s) présentes.")
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
