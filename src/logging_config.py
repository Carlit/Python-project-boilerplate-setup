"""Configuration centralisée de la journalisation.

Un seul point d'entrée : :func:`setup_logging`, appelé une fois au démarrage.
Les modules se contentent ensuite de `logger = logging.getLogger(__name__)`.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

_LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
)
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_BACKUP_COUNT: Final[int] = 5

_configured: bool = False


def setup_logging(
    level: str = "INFO",
    *,
    log_file: Path | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure le logger racine (console + fichier optionnel).

    Args:
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Chemin d'un fichier de log rotatif. Aucun fichier si None.
        force: Reconfigure même si la configuration a déjà été appliquée.

    Returns:
        Le logger racine configuré.
    """
    global _configured
    root: logging.Logger = logging.getLogger()

    if _configured and not force:
        return root

    numeric_level: int = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.setLevel(numeric_level)

    # Les drivers sont bavards : on ne remonte que leurs avertissements.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    _configured = True
    return root


__all__ = ["setup_logging"]
