"""Tests de la couche de configuration."""

from __future__ import annotations

import pytest

from src.exceptions import ConfigurationError
from src.settings import (
    REQUIRED_ANY_OF_ENV_KEYS,
    REQUIRED_ENV_KEYS,
    AppSettings,
    OracleSettings,
    PoolSettings,
    PostgresSettings,
    get_env_bool,
    get_env_int,
)

# Environnements complets et valides, utilisés pour vérifier que
# REQUIRED_ENV_KEYS / REQUIRED_ANY_OF_ENV_KEYS restent la source unique :
# retirer une clé à la fois doit lever une ConfigurationError si et
# seulement si elle appartient à la constante correspondante.
_FULL_POSTGRES_ENV: dict[str, str] = {
    "PG_HOST": "pg.test.local",
    "PG_PORT": "5432",
    "PG_USER": "app_user",
    "PG_PASSWORD": "secret",
    "PG_DB_NAME": "app_db",
    "PG_SCHEMA": "metier",
    "PG_SSLMODE": "require",
}

_FULL_ORACLE_ENV: dict[str, str] = {
    "ORACLE_HOST": "ora.test.local",
    "ORACLE_PORT": "1521",
    "ORACLE_USER": "app_user",
    "ORACLE_PASSWORD": "secret",
    "ORACLE_SERVICE_NAME": "ORCLPDB1",
    "ORACLE_SID": "ORCL",
    "ORACLE_CLIENT_MODE": "thin",
    "ORACLE_CLIENT_LIB_DIR": "",
}


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


@pytest.mark.parametrize("key", sorted(_FULL_POSTGRES_ENV))
def test_postgres_required_keys_match_constant(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """REQUIRED_ENV_KEYS doit décrire exactement les clés `required=True`
    lues par PostgresSettings.from_env() : retirer une clé de cette
    constante lève une ConfigurationError, retirer toute autre clé de
    l'environnement postgres n'en lève aucune.
    """
    for name, value in _FULL_POSTGRES_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(key, raising=False)

    if key in REQUIRED_ENV_KEYS:
        with pytest.raises(ConfigurationError, match=key):
            PostgresSettings.from_env()
    else:
        PostgresSettings.from_env()


@pytest.mark.parametrize("key", sorted(_FULL_ORACLE_ENV))
def test_oracle_required_keys_match_constant(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """Même garantie côté Oracle pour les clés `required=True` seules.

    ORACLE_SERVICE_NAME et ORACLE_SID sont ici toutes deux renseignées, afin
    que retirer l'une d'elles ne déclenche pas la contrainte séparée du
    couple (voir test_oracle_any_of_keys_match_constant) et n'exerce que la
    logique `required=True`.
    """
    for name, value in _FULL_ORACLE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(key, raising=False)

    if key in REQUIRED_ENV_KEYS:
        with pytest.raises(ConfigurationError, match=key):
            OracleSettings.from_env()
    else:
        OracleSettings.from_env()


def test_oracle_any_of_keys_match_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    """REQUIRED_ANY_OF_ENV_KEYS doit être le couple exigé par
    OracleSettings.__post_init__ : une seule des deux clés suffit, aucune
    des deux ne lève une ConfigurationError.
    """
    for name, value in _FULL_ORACLE_ENV.items():
        monkeypatch.setenv(name, value)

    for key in REQUIRED_ANY_OF_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
        OracleSettings.from_env()  # l'autre clé du couple suffit
        monkeypatch.setenv(key, _FULL_ORACLE_ENV[key])

    for key in REQUIRED_ANY_OF_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigurationError, match=REQUIRED_ANY_OF_ENV_KEYS[0]):
        OracleSettings.from_env()
