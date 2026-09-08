"""Tests de scripts/backup.py.

`information_schema.tables` n'existe pas sous SQLite : la découverte des
tables est donc injectée (`list_tables=...`) plutôt que simulée en
fabriquant un faux résultat SQL au format information_schema — c'est
`run_backup` (l'orchestration) qui est testé ici, avec une stratégie de
découverte SQLite réelle (`sqlite_master`), pas une façade.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from scripts import backup
from src.database import DatabaseManager, DatabaseType

_FIXED_NOW = datetime(2026, 9, 7, 21, 43)


def _fixed_now() -> datetime:
    return _FIXED_NOW


def _sqlite_list_tables(
    manager: DatabaseManager, db_type: DatabaseType, schema: str
) -> list[str]:
    """Stratégie de découverte pour les tests : `sqlite_master`.

    SQLite n'a pas de schémas au sens PostgreSQL/Oracle : `schema` est
    ignoré, tout comme le ferait une base à schéma unique.
    """
    del schema
    rows = manager.fetch_all(
        db_type,
        "SELECT name AS table_name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )
    return [str(row["table_name"]) for row in rows]


@pytest.fixture
def sqlite_manager() -> DatabaseManager:
    """Gestionnaire dont l'engine PostgreSQL est remplacé par SQLite en mémoire."""
    manager = DatabaseManager()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    manager._engines[DatabaseType.POSTGRES] = engine  # noqa: SLF001 - banc d'essai
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE comptes (id INTEGER PRIMARY KEY, libelle TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO comptes (id, libelle) VALUES (1, 'joint'), (2, 'perso')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE mouvements (id INTEGER PRIMARY KEY, montant REAL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO mouvements (id, montant) VALUES (1, 12.5)"
        )
        connection.exec_driver_sql("CREATE TABLE vide (id INTEGER, valeur TEXT)")
    return manager


# --------------------------------------------------- decouverte des tables


def test_list_tables_information_schema_queries_correct_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(
        db_type: DatabaseType, query: str, params: dict[str, str] | None = None
    ) -> list[dict[str, str]]:
        captured["query"] = query
        captured["params"] = params
        return [{"table_name": "comptes"}, {"table_name": "mouvements"}]

    manager = DatabaseManager()
    monkeypatch.setattr(manager, "fetch_all", fake_fetch_all)

    result = backup.list_tables_information_schema(
        manager, DatabaseType.POSTGRES, "public"
    )

    assert result == ["comptes", "mouvements"]
    assert captured["params"] == {"schema": "public"}
    assert "information_schema.tables" in str(captured["query"])


def test_sqlite_list_tables_finds_created_tables(
    sqlite_manager: DatabaseManager,
) -> None:
    tables = _sqlite_list_tables(sqlite_manager, DatabaseType.POSTGRES, "")
    assert tables == ["comptes", "mouvements", "vide"]


# -------------------------------------------------------------- run_backup


def test_run_backup_creates_timestamped_folder(
    tmp_path: Path, sqlite_manager: DatabaseManager
) -> None:
    backup_dir, results = backup.run_backup(
        sqlite_manager,
        DatabaseType.POSTGRES,
        "",
        tmp_path,
        list_tables=_sqlite_list_tables,
        now=_fixed_now,
    )

    assert backup_dir == tmp_path / "backup_20260907_2143"
    assert backup_dir.is_dir()
    assert {r.table for r in results} == {"comptes", "mouvements", "vide"}


def test_run_backup_exports_table_contents(
    tmp_path: Path, sqlite_manager: DatabaseManager
) -> None:
    backup_dir, _ = backup.run_backup(
        sqlite_manager,
        DatabaseType.POSTGRES,
        "",
        tmp_path,
        list_tables=_sqlite_list_tables,
        now=_fixed_now,
    )

    comptes = pd.read_csv(backup_dir / "comptes.csv", sep=";", encoding="utf-8-sig")
    assert len(comptes) == 2
    assert list(comptes.columns) == ["id", "libelle"]


def test_run_backup_empty_table_gets_headers_only(
    tmp_path: Path, sqlite_manager: DatabaseManager
) -> None:
    backup_dir, results = backup.run_backup(
        sqlite_manager,
        DatabaseType.POSTGRES,
        "",
        tmp_path,
        list_tables=_sqlite_list_tables,
        now=_fixed_now,
    )

    vide_result = next(r for r in results if r.table == "vide")
    assert vide_result.success
    assert vide_result.row_count == 0

    content = (backup_dir / "vide.csv").read_text(encoding="utf-8-sig")
    assert "id;valeur" in content


def test_run_backup_writes_manifest(
    tmp_path: Path, sqlite_manager: DatabaseManager
) -> None:
    backup_dir, _ = backup.run_backup(
        sqlite_manager,
        DatabaseType.POSTGRES,
        "",
        tmp_path,
        list_tables=_sqlite_list_tables,
        now=_fixed_now,
    )

    manifest = pd.read_csv(backup_dir / "manifest.csv", sep=";", encoding="utf-8-sig")
    assert list(manifest.columns) == [
        "table",
        "lignes_exportees",
        "statut",
        "erreur",
        "horodatage",
    ]
    assert set(manifest["table"]) == {"comptes", "mouvements", "vide"}
    assert (manifest["statut"] == "ok").all()

    lignes = dict(zip(manifest["table"], manifest["lignes_exportees"]))
    assert lignes["comptes"] == 2
    assert lignes["mouvements"] == 1
    assert lignes["vide"] == 0


def test_run_backup_continues_after_one_table_fails(
    tmp_path: Path, sqlite_manager: DatabaseManager
) -> None:
    def list_with_missing_table(
        manager: DatabaseManager, db_type: DatabaseType, schema: str
    ) -> list[str]:
        del manager, db_type, schema
        return ["comptes", "table_inexistante", "mouvements"]

    backup_dir, results = backup.run_backup(
        sqlite_manager,
        DatabaseType.POSTGRES,
        "",
        tmp_path,
        list_tables=list_with_missing_table,
        now=_fixed_now,
    )

    by_table = {r.table: r for r in results}
    assert by_table["comptes"].success
    assert by_table["mouvements"].success
    assert not by_table["table_inexistante"].success
    assert by_table["table_inexistante"].error is not None

    assert (backup_dir / "comptes.csv").is_file()
    assert (backup_dir / "mouvements.csv").is_file()
    assert not (backup_dir / "table_inexistante.csv").is_file()

    manifest = pd.read_csv(backup_dir / "manifest.csv", sep=";", encoding="utf-8-sig")
    statut = dict(zip(manifest["table"], manifest["statut"]))
    assert statut["table_inexistante"] == "echec"
    assert statut["comptes"] == "ok"


# ---------------------------------------------------------------- parse_args


def test_parse_args_defaults() -> None:
    args = backup.parse_args([])
    assert args.db == "postgres"
    assert args.schema == "public"
    assert args.output_dir == Path("exports")
    assert args.log_file is None


def test_parse_args_accepts_oracle() -> None:
    args = backup.parse_args(["--db", "oracle", "--schema", "app"])
    assert args.db == "oracle"
    assert args.schema == "app"
