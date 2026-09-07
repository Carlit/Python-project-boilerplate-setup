"""Vérifie que `.env` couvre `.env.example` avec des valeurs exploitables.

Contrôles effectués, sans jamais afficher la valeur d'une variable :

1. Clé présente dans le modèle mais absente de `.env` -> ERREUR.
2. Valeur laissée à "changeme" (insensible à la casse), ou valeur vide sur
   une variable obligatoire -> ERREUR.
3. Valeur d'un hôte (`PG_HOST`, `ORACLE_HOST`) identique à celle du
   modèle -> AVERTISSEMENT ("localhost" est légitime en local, mais suspect
   si jamais personnalisé).
4. Clé présente dans `.env` mais absente du modèle -> AVERTISSEMENT.

Les variables obligatoires viennent de `src.settings` (REQUIRED_ENV_KEYS,
REQUIRED_ANY_OF_ENV_KEYS) : cette liste n'est pas dupliquée ici.

Ne se connecte à aucune base.

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

# `src` n'est importable que si la racine du projet est sur sys.path : ce
# script est lancé directement (`python scripts/check_config.py`), pas via
# `-m`, donc seul le dossier scripts/ y est ajouté par défaut.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.settings import (  # noqa: E402 -- import après réglage de sys.path
    HOST_ENV_KEYS,
    REQUIRED_ANY_OF_ENV_KEYS,
    REQUIRED_ENV_KEYS,
)

_EXIT_OK: Final[int] = 0
_EXIT_FAILURE: Final[int] = 1

_PLACEHOLDER: Final[str] = "changeme"

_LABEL_MISSING: Final[str] = "MANQUANT"
_LABEL_EXTRA: Final[str] = "EN TROP"
_LABEL_ERROR: Final[str] = "ERREUR"
_LABEL_WARNING: Final[str] = "AVERTISSEMENT"


def read_env(path: Path) -> dict[str, str]:
    """Extrait les paires clé/valeur d'un fichier au format dotenv.

    Args:
        path: Chemin du fichier à analyser.

    Returns:
        Un dictionnaire clé -> valeur, dans l'ordre d'apparition. Les
        commentaires et lignes vides sont ignorés ; les valeurs sont
        dépouillées des espaces de bordure.
    """
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped: str = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        values[key.strip()] = raw_value.strip()
    return values


def read_keys(path: Path) -> set[str]:
    """Extrait les noms de variables d'un fichier au format dotenv.

    Args:
        path: Chemin du fichier à analyser.

    Returns:
        L'ensemble des noms de variables déclarés.
    """
    return set(read_env(path))


def _is_placeholder(value: str) -> bool:
    """Indique si une valeur est encore le placeholder du modèle.

    Args:
        value: Valeur brute (déjà dépouillée) à évaluer.

    Returns:
        True si la valeur vaut "changeme", indépendamment de la casse.
    """
    return value.lower() == _PLACEHOLDER


def _is_usable(value: str) -> bool:
    """Indique si une valeur est exploitable (ni vide, ni placeholder).

    Args:
        value: Valeur brute (déjà dépouillée) à évaluer.

    Returns:
        True si la valeur est renseignée et n'est pas "changeme".
    """
    return bool(value) and not _is_placeholder(value)


def validate_values(
    actual: dict[str, str], model: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Valide les valeurs de `.env`, sans jamais exposer leur contenu.

    Args:
        actual: Paires clé/valeur lues dans `.env`.
        model: Paires clé/valeur lues dans `.env.example`.

    Returns:
        Un tuple (messages d'erreur, messages d'avertissement). Chaque
        message ne cite que des noms de clés et la nature du problème.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for key in sorted(actual):
        if _is_placeholder(actual[key]):
            errors.append(f"{key} : valeur laissée à '{_PLACEHOLDER}'")

    for key in sorted(REQUIRED_ENV_KEYS):
        if key in actual and not actual[key]:
            errors.append(f"{key} : valeur obligatoire vide")

    if not any(_is_usable(actual.get(key, "")) for key in REQUIRED_ANY_OF_ENV_KEYS):
        names = " ou ".join(REQUIRED_ANY_OF_ENV_KEYS)
        errors.append(f"{names} : aucune valeur exploitable (une au moins requise)")

    for key in sorted(HOST_ENV_KEYS):
        value = actual.get(key, "")
        if value and value == model.get(key, "") and not _is_placeholder(value):
            warnings.append(f"{key} : identique au modèle, jamais personnalisée ?")

    return errors, warnings


def _print_section(label: str, items: list[str]) -> None:
    """Affiche une série de lignes préfixées par un label aligné.

    Args:
        label: Nature du constat (ex. "ERREUR").
        items: Messages à afficher, un par ligne.
    """
    for item in items:
        print(f"{label:<14}{item}")


def main() -> int:
    """Compare `.env` à `.env.example` et valide les valeurs obligatoires.

    Returns:
        0 si la configuration ne comporte aucune erreur bloquante (des
        avertissements peuvent subsister), 1 sinon.
    """
    if not EXAMPLE_FILE.is_file():
        print(f"Fichier modèle introuvable : {EXAMPLE_FILE}", file=sys.stderr)
        return _EXIT_FAILURE

    if not ENV_FILE.is_file():
        print(".env absent — copier .env.example en .env.", file=sys.stderr)
        return _EXIT_FAILURE

    model: dict[str, str] = read_env(EXAMPLE_FILE)
    actual: dict[str, str] = read_env(ENV_FILE)

    missing: list[str] = sorted(set(model) - set(actual))
    extra: list[str] = sorted(set(actual) - set(model))
    errors, warnings = validate_values(actual, model)

    _print_section(_LABEL_MISSING, missing)
    _print_section(_LABEL_EXTRA, extra)
    _print_section(_LABEL_ERROR, errors)
    _print_section(_LABEL_WARNING, warnings)

    total_errors: int = len(missing) + len(errors)
    if total_errors:
        print(f"\n{total_errors} erreur(s) détectée(s).", file=sys.stderr)
        return _EXIT_FAILURE

    if warnings:
        print(f"\n{len(warnings)} avertissement(s), aucune erreur bloquante.")
    else:
        print(f"\nConfiguration valide : {len(model)} clé(s) vérifiées.")
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
