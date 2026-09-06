"""Tests de la couche d'accès aux bases de données.

Aucun test ne requiert de serveur : les URL sont vérifiées hors connexion et
SQLite en mémoire sert de banc d'essai pour les méthodes de requêtage.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from src.database import (
    DatabaseManager,
    DatabaseType,
    build_oracle_url,
    build_postgres_url,
)
from src.exceptions import ConfigurationError, QueryError
from src.settings import OracleSettings, PostgresSettings


def test_build_postgres_url_uses_psycopg3(postgres_env: dict[str, str]) -> None:
    url = build_postgres_url(PostgresSettings.from_env())
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "pg.test.local"
    assert url.database == "app_db"


def test_build_postgres_url_escapes_special_characters(
    postgres_env: dict[str, str],
) -> None:
    url = build_postgres_url(PostgresSettings.from_env())
    rendered = url.render_as_string(hide_password=False)
    assert "p%40ss%2Fword%3A1" in rendered


def test_postgres_url_hides_password_by_default(postgres_env: dict[str, str]) -> None:
    url = build_postgres_url(PostgresSettings.from_env())
    assert "p@ss/word:1" not in url.render_as_string()


def test_build_oracle_url_prefers_service_name(oracle_env: dict[str, str]) -> None:
    url = build_oracle_url(OracleSettings.from_env())
    assert url.drivername == "oracle+oracledb"
    assert url.query["service_name"] == "ORCLPDB1"


def test_build_oracle_url_falls_back_to_sid() -> None:
    settings = OracleSettings(
        host="ora", port=1521, user="u", password="p", service_name="", sid="XE"
    )
    url = build_oracle_url(settings)
    assert url.database == "XE"
    assert "service_name" not in url.query


def test_get_engine_without_configuration_raises() -> None:
    manager = DatabaseManager()
    with pytest.raises(ConfigurationError, match="PostgreSQL"):
        manager.get_engine(DatabaseType.POSTGRES)
    with pytest.raises(ConfigurationError, match="Oracle"):
        manager.get_engine(DatabaseType.ORACLE)


def test_engine_is_cached(postgres_env: dict[str, str]) -> None:
    manager = DatabaseManager(postgres=PostgresSettings.from_env())
    assert manager.get_engine(DatabaseType.POSTGRES) is manager.get_engine(
        DatabaseType.POSTGRES
    )
    manager.dispose()


def test_from_env_tolerates_partial_configuration(
    postgres_env: dict[str, str],
) -> None:
    manager = DatabaseManager.from_env(load_dotenv_file=False)
    assert manager.get_engine(DatabaseType.POSTGRES) is not None
    with pytest.raises(ConfigurationError):
        manager.get_engine(DatabaseType.ORACLE)
    manager.dispose()


@pytest.fixture
def sqlite_manager() -> DatabaseManager:
    """Gestionnaire dont l'engine PostgreSQL est remplacé par SQLite en mémoire."""
    manager = DatabaseManager()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    manager._engines[DatabaseType.POSTGRES] = engine  # noqa: SLF001 - banc d'essai
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE incident (id INTEGER PRIMARY KEY, libelle TEXT)"
        )
        connection.exec_driver_sql(
            "INSERT INTO incident (id, libelle) VALUES (1, 'cable'), (2, 'signal')"
        )
    return manager


def test_fetch_all_returns_dicts(sqlite_manager: DatabaseManager) -> None:
    rows = sqlite_manager.fetch_all(
        DatabaseType.POSTGRES, "SELECT id, libelle FROM incident ORDER BY id"
    )
    assert rows == [
        {"id": 1, "libelle": "cable"},
        {"id": 2, "libelle": "signal"},
    ]


def test_fetch_one_with_named_parameter(sqlite_manager: DatabaseManager) -> None:
    row = sqlite_manager.fetch_one(
        DatabaseType.POSTGRES,
        "SELECT libelle FROM incident WHERE id = :id",
        {"id": 2},
    )
    assert row == {"libelle": "signal"}


def test_fetch_one_returns_none_when_empty(sqlite_manager: DatabaseManager) -> None:
    assert (
        sqlite_manager.fetch_one(
            DatabaseType.POSTGRES,
            "SELECT libelle FROM incident WHERE id = :id",
            {"id": 99},
        )
        is None
    )


def test_execute_returns_affected_rows(sqlite_manager: DatabaseManager) -> None:
    affected = sqlite_manager.execute(
        DatabaseType.POSTGRES,
        "UPDATE incident SET libelle = :libelle WHERE id = :id",
        {"libelle": "cable sectionne", "id": 1},
    )
    assert affected == 1


def test_read_dataframe(sqlite_manager: DatabaseManager) -> None:
    frame = sqlite_manager.read_dataframe(
        DatabaseType.POSTGRES, "SELECT id, libelle FROM incident ORDER BY id"
    )
    assert frame.shape == (2, 2)
    assert list(frame.columns) == ["id", "libelle"]


def test_invalid_sql_raises_query_error(sqlite_manager: DatabaseManager) -> None:
    with pytest.raises(QueryError):
        sqlite_manager.fetch_all(DatabaseType.POSTGRES, "SELECT * FROM table_absente")


def test_ping_returns_false_on_error() -> None:
    assert DatabaseManager().ping(DatabaseType.POSTGRES) is False


def test_context_manager_disposes_engines(sqlite_manager: DatabaseManager) -> None:
    with sqlite_manager as manager:
        assert manager.fetch_one(DatabaseType.POSTGRES, "SELECT 1 AS ok") == {"ok": 1}
    assert not sqlite_manager._engines  # noqa: SLF001 - vérification du nettoyage
