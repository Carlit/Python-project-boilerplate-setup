"""Point d'entrée applicatif — vérifie la configuration et les connexions.

Usage :
    python -m src.main
    python -m src.main --check postgres
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

from src.database import DatabaseManager, DatabaseType
from src.exceptions import AppError
from src.logging_config import setup_logging
from src.settings import PROJECT_ROOT, AppSettings, load_env

logger: Final[logging.Logger] = logging.getLogger(__name__)

_EXIT_OK: Final[int] = 0
_EXIT_FAILURE: Final[int] = 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Vérifie la configuration et les connexions aux bases.",
    )
    parser.add_argument(
        "--check",
        choices=[db.value for db in DatabaseType] + ["all"],
        default="all",
        help="Moteur à tester (défaut : all).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Chemin d'un fichier de log rotatif (optionnel).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Exécute la vérification de connectivité.

    Returns:
        0 si toutes les vérifications passent, 1 sinon.
    """
    args: argparse.Namespace = parse_args(argv)

    load_env()
    app: AppSettings = AppSettings.from_env()
    setup_logging(app.log_level, log_file=args.log_file)

    logger.info("Démarrage (env=%s, racine=%s)", app.app_env, PROJECT_ROOT)

    targets: list[DatabaseType] = (
        list(DatabaseType) if args.check == "all" else [DatabaseType(args.check)]
    )

    failures: list[str] = []
    try:
        with DatabaseManager.from_env(load_dotenv_file=False) as manager:
            for db_type in targets:
                if not manager.ping(db_type):
                    failures.append(db_type.value)
    except AppError as exc:
        logger.error("Erreur applicative : %s", exc)
        return _EXIT_FAILURE

    if failures:
        logger.error("Vérification en échec pour : %s", ", ".join(failures))
        return _EXIT_FAILURE

    logger.info("Toutes les vérifications ont réussi.")
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
