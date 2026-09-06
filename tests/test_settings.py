"""Tests de la couche de configuration."""

from __future__ import annotations

import pytest

from src.exceptions import ConfigurationError
from src.settings import (
    AppSettings,
    OracleSettings,
    PoolSettings,
    PostgresSettings,
    get_env_bool,
    get_env_int,
)


def test_postgres_settings_from_env(postgres_env: dict[str, str]) -> None:
    settings = PostgresSettings.from_env()
    assert settings.host == postgres_env["PG_HOST"]
    assert settings.port == 5432
    assert settings.schema == "metier"
    assert settings.sslmode == "require"


def test_postgres_settings_missing_variable_raises() -> None:
    with pytest.raises(ConfigurationError, match="PG_HOST"):
        PostgresSettings.from_env()


def test_oracle_settings_from_env(oracle_env: dict[str, str]) -> None:
    settings = OracleSettings.from_env()
    assert settings.service_name == "ORCLPDB1"
    assert settings.sid == ""
    assert settings.client_mode == "thin"


def test_oracle_settings_requires_service_or_sid() -> None:
    with pytest.raises(ConfigurationError, match="ORACLE_SERVICE_NAME"):
        OracleSettings(
            host="h", port=1521, user="u", password="p", service_name="", sid=""
        )


def test_oracle_settings_rejects_unknown_client_mode() -> None:
    with pytest.raises(ConfigurationError, match="ORACLE_CLIENT_MODE"):
        OracleSettings(
            host="h",
            port=1521,
            user="u",
            password="p",
            service_name="SVC",
            client_mode="fat",
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("TRUE", True), ("1", True), ("oui", True), ("false", False)],
)
def test_get_env_bool(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("SQL_ECHO", raw)
    assert get_env_bool("SQL_ECHO") is expected


def test_get_env_int_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "beaucoup")
    with pytest.raises(ConfigurationError, match="DB_POOL_SIZE"):
        get_env_int("DB_POOL_SIZE", 5)


def test_defaults_are_applied() -> None:
    assert PoolSettings.from_env().pool_size == 5
    assert AppSettings.from_env().log_level == "INFO"
