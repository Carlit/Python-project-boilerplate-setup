"""Fixtures partagées par les tests."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

_PG_ENV: dict[str, str] = {
    "PG_HOST": "pg.test.local",
    "PG_PORT": "5432",
    "PG_USER": "app_user",
    "PG_PASSWORD": "p@ss/word:1",
    "PG_DB_NAME": "app_db",
    "PG_SCHEMA": "metier",
    "PG_SSLMODE": "require",
}

_ORACLE_ENV: dict[str, str] = {
    "ORACLE_HOST": "ora.test.local",
    "ORACLE_PORT": "1521",
    "ORACLE_USER": "app_user",
    "ORACLE_PASSWORD": "secret",
    "ORACLE_SERVICE_NAME": "ORCLPDB1",
    "ORACLE_CLIENT_MODE": "thin",
}

_ALL_KEYS: tuple[str, ...] = tuple(_PG_ENV) + tuple(_ORACLE_ENV) + (
    "ORACLE_SID",
    "APP_ENV",
    "LOG_LEVEL",
    "SQL_ECHO",
    "DB_POOL_SIZE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isole chaque test des variables d'environnement du poste."""
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def postgres_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Positionne un jeu complet de variables PostgreSQL."""
    for key, value in _PG_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(_PG_ENV)


@pytest.fixture
def oracle_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Positionne un jeu complet de variables Oracle."""
    for key, value in _ORACLE_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(_ORACLE_ENV)


@pytest.fixture
def env_snapshot() -> dict[str, str]:
    """Copie de l'environnement courant (diagnostic)."""
    return dict(os.environ)
