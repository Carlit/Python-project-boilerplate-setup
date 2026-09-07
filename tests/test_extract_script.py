"""Tests de scripts/extract.py.

`parse_parameter` et `read_query` sont testés sans aucune base. L'exécution
par lots (`iter_dataframes`) et le scénario bout en bout s'appuient sur
SQLite en mémoire, injecté à la place de PostgreSQL — jamais de connexion
réelle, jamais de lecture du vrai `.env`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from scripts import extract
from src.database import DatabaseManager, DatabaseType
from src.exceptions import AppError

# ------------------------------------------------------------- parse_parameter


def test_parse_parameter_defaults_to_str() -> None:
    assert extract.parse_parameter("nom=dupont") == ("nom", "dupont")


def test_parse_parameter_int() -> None:
    assert extract.parse_parameter("id:int=42") == ("id", 42)


def test_parse_parameter_float() -> None:
    assert extract.parse_parameter("seuil:float=3.14") == ("seuil", 3.14)


def test_parse_parameter_splits_only_on_first_equals() -> None:
    assert extract.parse_parameter("filtre=a=b") == ("filtre", "a=b")


def test_parse_parameter_missing_equals_raises() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        extract.parse_parameter("id42")


def test_parse_parameter_unknown_type_raises() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="bool"):
        extract.parse_parameter("actif:bool=true")


def test_parse_parameter_unconvertible_value_raises() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="id"):
        extract.parse_parameter("id:int=abc")


def test_parse_parameter_empty_name_raises() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        extract.parse_parameter(":int=5")


# ------------------------------------------------------------------ read_query


def test_read_query_strips_trailing_semicolon(tmp_path: Path) -> None:
    query_file = tmp_path / "requete.sql"
    query_file.write_text("SELECT * FROM t;\n", encoding="utf-8")
    assert extract.read_query(query_file) == "SELECT * FROM t"


def test_read_query_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(AppError):
        extract.read_query(tmp_path / "absent.sql")


def test_read_query_empty_file_raises(tmp_path: Path) -> None:
    query_file = tmp_path / "vide.sql"
    query_file.write_text("   ;  \n", encoding="utf-8")
    with pytest.raises(AppError, match="vide"):
        extract.read_query(query_file)


# -------------------------------------------------------------- iter_dataframes


@pytest.fixture
def sqlite_manager() -> DatabaseManager:
    """Gestionnaire dont l'engine PostgreSQL est remplacé par SQLite en mémoire."""
    manager = DatabaseManager()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    manager._engines[DatabaseType.POSTGRES] = engine  # noqa: SLF001 - banc d'essai
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, libelle TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO t (id, libelle) VALUES "
            "(1, 'a'), (2, 'b'), (3, 'c'), (4, 'd'), (5, 'e')"
        )
    return manager


def test_iter_dataframes_batches_rows(sqlite_manager: DatabaseManager) -> None:
    batches = list(
        sqlite_manager.iter_dataframes(
            DatabaseType.POSTGRES,
            "SELECT id, libelle FROM t ORDER BY id",
            batch_size=2,
        )
    )
    assert [len(batch) for batch in batches] == [2, 2, 1]


def test_iter_dataframes_rejects_non_positive_batch_size(
    sqlite_manager: DatabaseManager,
) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        sqlite_manager.iter_dataframes(DatabaseType.POSTGRES, "SELECT 1", batch_size=0)


# --------------------------------------------------------------------- main()


def test_main_end_to_end_writes_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, libelle TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO t (id, libelle) VALUES (1, 'a'), (2, 'b'), (3, 'c')"
        )

    def fake_from_env(*, load_dotenv_file: bool = True) -> DatabaseManager:
        manager = DatabaseManager()
        manager._engines[DatabaseType.POSTGRES] = engine  # noqa: SLF001 - banc d'essai
        return manager

    monkeypatch.setattr(DatabaseManager, "from_env", staticmethod(fake_from_env))
    # Ne jamais lire le vrai .env du dépôt pendant un test.
    monkeypatch.setattr(extract, "load_env", lambda: None)

    query_file = tmp_path / "requete.sql"
    query_file.write_text("SELECT id, libelle FROM t ORDER BY id;", encoding="utf-8")
    output = tmp_path / "sortie"

    exit_code = extract.main(
        [
            "--db",
            "postgres",
            "--query",
            str(query_file),
            "--output",
            str(output),
            "--format",
            "csv",
            "--batch-size",
            "2",
        ]
    )

    assert exit_code == 0
    written = output.with_suffix(".csv")
    reread = pd.read_csv(written, sep=";", encoding="utf-8-sig")
    assert reread.to_dict("records") == [
        {"id": 1, "libelle": "a"},
        {"id": 2, "libelle": "b"},
        {"id": 3, "libelle": "c"},
    ]
