"""Export de DataFrames vers des fichiers (CSV, Excel, Parquet).

Ce module ne connaît rien aux bases de données : il reçoit des DataFrames
déjà chargés et écrit des fichiers. Testable sans aucune connexion.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from enum import Enum
from pathlib import Path
from typing import Final

import pandas as pd

from src.exceptions import AppError

logger: Final[logging.Logger] = logging.getLogger(__name__)

EXCEL_MAX_ROWS: Final[int] = 1_048_576

_CSV_SEPARATOR: Final[str] = ";"
# Le BOM (utf-8-sig) est nécessaire : sans lui, Excel casse les accents à
# l'ouverture d'un CSV en détectant mal l'encodage.
_CSV_ENCODING: Final[str] = "utf-8-sig"


class ExportError(AppError):
    """Échec d'écriture d'un export (chemin, format, ou capacité dépassée)."""


class ExportFormat(str, Enum):
    """Formats de fichier pris en charge par l'export."""

    CSV = "csv"
    EXCEL = "excel"
    PARQUET = "parquet"

    @property
    def suffix(self) -> str:
        """Extension de fichier associée au format.

        Returns:
            L'extension avec le point (ex. ".csv").
        """
        if self is ExportFormat.CSV:
            return ".csv"
        if self is ExportFormat.EXCEL:
            return ".xlsx"
        return ".parquet"


def resolve_output_path(path: Path, export_format: ExportFormat) -> Path:
    """Ajoute ou corrige l'extension du chemin de sortie selon le format.

    Args:
        path: Chemin souhaité, avec ou sans extension.
        export_format: Format d'export cible.

    Returns:
        `path` inchangé si son extension correspond déjà au format, sinon
        `path` avec l'extension attendue par `export_format`.
    """
    if path.suffix.lower() == export_format.suffix:
        return path
    return path.with_suffix(export_format.suffix)


def export_dataframe(
    frame: pd.DataFrame,
    path: Path,
    export_format: ExportFormat = ExportFormat.CSV,
    *,
    sheet_name: str = "export",
) -> Path:
    """Écrit un DataFrame dans un fichier, au format demandé.

    Args:
        frame: Données à écrire.
        path: Chemin de sortie ; l'extension est ajoutée ou corrigée.
        export_format: Format d'export.
        sheet_name: Nom de la feuille, pour le format Excel uniquement.

    Returns:
        Le chemin effectivement écrit.

    Raises:
        ExportError: Si le nombre de lignes atteint EXCEL_MAX_ROWS en Excel,
            ou si l'écriture échoue (droits, disque, dépendance manquante).
    """
    if export_format is ExportFormat.EXCEL and len(frame) >= EXCEL_MAX_ROWS:
        raise ExportError(
            f"{len(frame)} ligne(s) atteignent ou dépassent la limite Excel "
            f"({EXCEL_MAX_ROWS}) : utiliser CSV ou Parquet."
        )

    resolved: Path = resolve_output_path(path, export_format)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    try:
        if export_format is ExportFormat.CSV:
            frame.to_csv(
                resolved, sep=_CSV_SEPARATOR, encoding=_CSV_ENCODING, index=False
            )
        elif export_format is ExportFormat.EXCEL:
            frame.to_excel(resolved, sheet_name=sheet_name, index=False)
        elif export_format is ExportFormat.PARQUET:
            frame.to_parquet(resolved, index=False)
        else:  # pragma: no cover - garde-fou, l'énumération est exhaustive
            raise ExportError(f"Format d'export non pris en charge : {export_format!r}")
    except (OSError, ValueError, ImportError) as exc:
        raise ExportError(f"Écriture de {resolved} en échec : {exc}") from exc

    logger.info(
        "Export %s écrit : %s (%d ligne(s))", export_format.value, resolved, len(frame)
    )
    return resolved


def export_batches(
    batches: Iterable[pd.DataFrame],
    path: Path,
    export_format: ExportFormat = ExportFormat.CSV,
    *,
    sheet_name: str = "export",
) -> tuple[Path, int]:
    """Écrit une série de DataFrames dans un seul fichier.

    En CSV, chaque lot est ajouté au fil de l'eau (l'en-tête n'est écrit
    qu'une fois) : rien n'est concaténé en mémoire. Excel et Parquet ne
    supportent pas l'écriture incrémentale ; les lots y sont concaténés
    avant écriture.

    Args:
        batches: Lots de lignes à écrire, dans l'ordre.
        path: Chemin de sortie ; l'extension est ajoutée ou corrigée.
        export_format: Format d'export.
        sheet_name: Nom de la feuille, pour le format Excel uniquement.

    Returns:
        Un tuple (chemin écrit, nombre total de lignes écrites).

    Raises:
        ExportError: Si `batches` est vide, si l'export Excel dépasse
            EXCEL_MAX_ROWS, ou si l'écriture échoue.
    """
    resolved: Path = resolve_output_path(path, export_format)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    if export_format is ExportFormat.CSV:
        return _export_batches_csv(batches, resolved)
    return _export_batches_concatenated(batches, resolved, export_format, sheet_name)


def _export_batches_csv(
    batches: Iterable[pd.DataFrame], resolved: Path
) -> tuple[Path, int]:
    """Écrit les lots CSV au fil de l'eau, en-tête écrit une seule fois."""
    iterator: Iterator[pd.DataFrame] = iter(batches)
    try:
        first_batch: pd.DataFrame = next(iterator)
    except StopIteration as exc:
        raise ExportError("Aucun lot à exporter : l'itérable est vide.") from exc

    total_rows = 0
    try:
        with resolved.open("w", newline="", encoding=_CSV_ENCODING) as handle:
            first_batch.to_csv(handle, sep=_CSV_SEPARATOR, index=False, header=True)
            total_rows += len(first_batch)
            for batch in iterator:
                batch.to_csv(handle, sep=_CSV_SEPARATOR, index=False, header=False)
                total_rows += len(batch)
    except (OSError, ValueError, ImportError) as exc:
        raise ExportError(f"Écriture de {resolved} en échec : {exc}") from exc

    logger.info("Export csv écrit : %s (%d ligne(s), par lots)", resolved, total_rows)
    return resolved, total_rows


def _export_batches_concatenated(
    batches: Iterable[pd.DataFrame],
    resolved: Path,
    export_format: ExportFormat,
    sheet_name: str,
) -> tuple[Path, int]:
    """Concatène les lots en mémoire avant écriture (Excel, Parquet)."""
    frames: list[pd.DataFrame] = list(batches)
    if not frames:
        raise ExportError("Aucun lot à exporter : l'itérable est vide.")

    combined: pd.DataFrame = pd.concat(frames, ignore_index=True)
    export_dataframe(combined, resolved, export_format, sheet_name=sheet_name)
    return resolved, len(combined)


__all__ = [
    "EXCEL_MAX_ROWS",
    "ExportError",
    "ExportFormat",
    "export_batches",
    "export_dataframe",
    "resolve_output_path",
]
