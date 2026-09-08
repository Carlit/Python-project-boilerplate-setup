"""CLI de sauvegarde : exporte toutes les tables d'un schéma en CSV.

Avant toute manipulation risquée (suppression d'un utilisateur, migration
destructive), ce script découvre les tables du schéma cible — aucune liste
codée en dur, le schéma évolue — et exporte chacune intégralement, table par
table, dans un dossier horodaté. Un `manifest.csv` récapitule ce qui a été
exporté, pour vérifier qu'une restauration est complète.

Limite connue : la découverte par défaut interroge `information_schema.
tables`, standard SQL pris en charge par PostgreSQL mais pas par Oracle
(qui expose son catalogue via `ALL_TABLES`/`USER_TABLES`) — `--db oracle`
échouera donc à l'étape de découverte tant qu'une stratégie dédiée n'est
pas ajoutée.

Usage :
    python scripts/backup.py --db postgres --schema public
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

# `src` n'est importable que si la racine du projet est sur sys.path : ce
# script est lancé directement (`python scripts/backup.py`), pas via `-m`,
# donc seul le dossier scripts/ y est ajouté par défaut.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseManager, DatabaseType  # noqa: E402
from src.exceptions import AppError  # noqa: E402
from src.export import ExportFormat, export_batches, export_dataframe  # noqa: E402
from src.logging_config import setup_logging  # noqa: E402
from src.settings import AppSettings, load_env  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover - import réservé au typage
    import pandas as pd

logger: Final[logging.Logger] = logging.getLogger(__name__)

_EXIT_OK: Final[int] = 0
_EXIT_FAILURE: Final[int] = 1

_DEFAULT_BATCH_SIZE: Final[int] = 50_000
_DEFAULT_SCHEMA: Final[str] = "public"

_LIST_TABLES_QUERY: Final[str] = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = :schema
      AND table_type = 'BASE TABLE'
    ORDER BY table_name
"""

# Stratégie de découverte des tables : information_schema.tables par défaut,
# injectable pour les tests (SQLite n'a pas information_schema).
ListTables = Callable[[DatabaseManager, DatabaseType, str], list[str]]


@dataclass(frozen=True, slots=True)
class TableBackupResult:
    """Résultat de l'export d'une table."""

    table: str
    row_count: int
    error: str | None = None

    @property
    def success(self) -> bool:
        """Indique si l'export de cette table a réussi."""
        return self.error is None


def list_tables_information_schema(
    manager: DatabaseManager, db_type: DatabaseType, schema: str
) -> list[str]:
    """Découvre les tables d'un schéma via `information_schema.tables`.

    Args:
        manager: Gestionnaire de connexions.
        db_type: Moteur cible.
        schema: Nom du schéma à inspecter.

    Returns:
        Les noms de table du schéma, triés.

    Raises:
        QueryError: Si l'exécution échoue.
    """
    rows = manager.fetch_all(db_type, _LIST_TABLES_QUERY, {"schema": schema})
    return [str(row["table_name"]) for row in rows]


def _quote_identifier(name: str) -> str:
    """Met un identifiant SQL entre guillemets doubles, échappés.

    Un identifiant (table, schéma) ne peut pas être un paramètre lié — SQL
    ne paramètre que des valeurs, jamais des identifiants. Ceux traités ici
    proviennent du catalogue système, pas d'une saisie utilisateur, mais
    restent mis entre guillemets et échappés par prudence.

    Args:
        name: Nom brut, table ou schéma.

    Returns:
        L'identifiant entre guillemets doubles, `"` interne doublé.
    """
    return '"' + name.replace('"', '""') + '"'


def _qualified_table(schema: str, table: str) -> str:
    """Nom de table qualifié par son schéma, ou seul si `schema` est vide."""
    quoted_table = _quote_identifier(table)
    if not schema:
        return quoted_table
    return f"{_quote_identifier(schema)}.{quoted_table}"


def _build_select_all_query(schema: str, table: str) -> str:
    """Construit `SELECT * FROM <table qualifiée>`."""
    return f"SELECT * FROM {_qualified_table(schema, table)}"


def _build_count_query(schema: str, table: str) -> str:
    """Construit `SELECT COUNT(*) FROM <table qualifiée>`."""
    return f"SELECT COUNT(*) AS total FROM {_qualified_table(schema, table)}"


def _backup_one_table(
    manager: DatabaseManager,
    db_type: DatabaseType,
    schema: str,
    table: str,
    backup_dir: Path,
    batch_size: int,
) -> TableBackupResult:
    """Exporte une table en CSV ; capture l'échec au lieu de le propager.

    Une table vide (0 ligne) ne produit aucun lot via `iter_dataframes` —
    ce n'est pas une erreur, mais il faut une requête dédiée pour obtenir
    quand même les colonnes attendues dans le CSV.
    """
    try:
        total_row = manager.fetch_one(db_type, _build_count_query(schema, table))
        total: int = int(total_row["total"]) if total_row else 0
        query: str = _build_select_all_query(schema, table)

        if total == 0:
            empty_frame: "pd.DataFrame" = manager.read_dataframe(
                db_type, f"{query} WHERE 1=0"
            )
            export_dataframe(empty_frame, backup_dir / table, ExportFormat.CSV)
            row_count = 0
        else:
            batches: Iterator["pd.DataFrame"] = manager.iter_dataframes(
                db_type, query, batch_size=batch_size
            )
            _, row_count = export_batches(batches, backup_dir / table, ExportFormat.CSV)
    except AppError as exc:
        logger.error("Échec de l'export de %s : %s", table, exc)
        return TableBackupResult(table=table, row_count=0, error=str(exc))

    logger.info("Table %s exportée : %d ligne(s)", table, row_count)
    return TableBackupResult(table=table, row_count=row_count)


def _write_manifest(
    backup_dir: Path, results: list[TableBackupResult], timestamp: datetime
) -> Path:
    """Écrit `manifest.csv` : table, lignes exportées, statut, horodatage."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "table": [r.table for r in results],
            "lignes_exportees": [r.row_count for r in results],
            "statut": ["ok" if r.success else "echec" for r in results],
            "erreur": [r.error or "" for r in results],
            "horodatage": [timestamp.isoformat(timespec="seconds")] * len(results),
        }
    )
    return export_dataframe(frame, backup_dir / "manifest", ExportFormat.CSV)


def run_backup(
    manager: DatabaseManager,
    db_type: DatabaseType,
    schema: str,
    output_dir: Path,
    *,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    list_tables: ListTables = list_tables_information_schema,
    now: Callable[[], datetime] | None = None,
) -> tuple[Path, list[TableBackupResult]]:
    """Exporte toutes les tables d'un schéma dans un dossier horodaté.

    Chaque table est exportée indépendamment : l'échec d'une table est
    journalisé et n'interrompt pas les suivantes.

    Args:
        manager: Gestionnaire de connexions, déjà configuré.
        db_type: Moteur cible.
        schema: Schéma à sauvegarder.
        output_dir: Dossier racine sous lequel créer le dossier horodaté.
        batch_size: Lignes par lot lues depuis la base.
        list_tables: Stratégie de découverte des tables — injectable pour
            les tests, `information_schema.tables` par défaut.
        now: Source de l'horodatage — injectable pour les tests.

    Returns:
        Le dossier horodaté créé, et le résultat de chaque table.
    """
    timestamp: datetime = (now or datetime.now)()
    backup_dir: Path = output_dir / f"backup_{timestamp:%Y%m%d_%H%M}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    tables: list[str] = list_tables(manager, db_type, schema)
    logger.info("%d table(s) découverte(s) dans le schéma %s", len(tables), schema)

    results: list[TableBackupResult] = [
        _backup_one_table(manager, db_type, schema, table, backup_dir, batch_size)
        for table in tables
    ]

    _write_manifest(backup_dir, results, timestamp)
    return backup_dir, results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="python scripts/backup.py",
        description=(
            "Exporte toutes les tables d'un schéma en CSV, une table par "
            "fichier, dans un dossier horodaté."
        ),
    )
    parser.add_argument(
        "--db",
        choices=[db.value for db in DatabaseType],
        default=DatabaseType.POSTGRES.value,
        help="Moteur cible (défaut : postgres).",
    )
    parser.add_argument(
        "--schema",
        default=_DEFAULT_SCHEMA,
        help=f"Schéma à sauvegarder (défaut : {_DEFAULT_SCHEMA}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("exports"),
        help="Dossier racine sous lequel créer le dossier horodaté (défaut : exports/).",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Chemin d'un fichier de log rotatif (optionnel).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Sauvegarde toutes les tables d'un schéma en CSV, une table par fichier.

    Returns:
        0 si toutes les tables ont été exportées, 1 si au moins une a
        échoué (les autres sont exportées quand même).
    """
    args: argparse.Namespace = parse_args(argv)

    load_env()
    app: AppSettings = AppSettings.from_env()
    setup_logging(app.log_level, log_file=args.log_file)

    db_type: DatabaseType = DatabaseType(args.db)

    try:
        with DatabaseManager.from_env() as manager:
            backup_dir, results = run_backup(
                manager, db_type, args.schema, args.output_dir
            )
    except AppError as exc:
        logger.error("Sauvegarde impossible : %s", exc)
        return _EXIT_FAILURE

    failures: list[TableBackupResult] = [r for r in results if not r.success]
    logger.info(
        "Sauvegarde terminée : %s (%d table(s), %d échec(s))",
        backup_dir,
        len(results),
        len(failures),
    )
    return _EXIT_FAILURE if failures else _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
