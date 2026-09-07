"""Chargement et validation de la configuration depuis l'environnement.

La configuration provient exclusivement de variables d'environnement (chargées
depuis un fichier `.env` en développement). Aucun secret n'est écrit en dur.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

from src.exceptions import ConfigurationError

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"

_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on", "oui"})

# Clés lues avec `required=True` par PostgresSettings.from_env() et
# OracleSettings.from_env(). Source unique pour tout code qui doit connaître
# la liste des variables obligatoires (ex. scripts/check_config.py) sans la
# redéfinir à côté.
REQUIRED_ENV_KEYS: Final[frozenset[str]] = frozenset(
    {
        "PG_HOST",
        "PG_USER",
        "PG_PASSWORD",
        "PG_DB_NAME",
        "ORACLE_HOST",
        "ORACLE_USER",
        "ORACLE_PASSWORD",
    }
)

# OracleSettings.__post_init__ exige au moins une de ces deux clés (service
# name prioritaire sur SID) : ni l'une ni l'autre n'est individuellement
# `required=True`, mais leur absence conjointe lève une ConfigurationError.
REQUIRED_ANY_OF_ENV_KEYS: Final[tuple[str, ...]] = ("ORACLE_SERVICE_NAME", "ORACLE_SID")

# Clés d'hôte dont la valeur par défaut du modèle (.env.example, "localhost")
# reste valide pour une base locale mais est suspecte si jamais personnalisée.
HOST_ENV_KEYS: Final[frozenset[str]] = frozenset({"PG_HOST", "ORACLE_HOST"})


def load_env(env_file: Path | None = None, *, override: bool = False) -> None:
    """Charge le fichier `.env` s'il existe.

    Args:
        env_file: Chemin du fichier `.env`. Par défaut celui de la racine projet.
        override: Si True, écrase les variables déjà présentes dans l'environnement.
    """
    target: Path = env_file if env_file is not None else ENV_FILE
    if target.is_file():
        load_dotenv(dotenv_path=target, override=override)


def get_env(name: str, default: str | None = None, *, required: bool = False) -> str:
    """Lit une variable d'environnement sous forme de chaîne.

    Args:
        name: Nom de la variable.
        default: Valeur retournée si la variable est absente ou vide.
        required: Si True, lève une erreur lorsque aucune valeur n'est disponible.

    Returns:
        La valeur lue, ou `default`.

    Raises:
        ConfigurationError: Si `required` et qu'aucune valeur n'est disponible.
    """
    raw: str | None = os.environ.get(name)
    value: str | None = raw.strip() if raw is not None else None
    if not value:
        if required and not default:
            raise ConfigurationError(
                f"Variable d'environnement obligatoire manquante : {name}"
            )
        return default or ""
    return value


def get_env_int(name: str, default: int) -> int:
    """Lit une variable d'environnement entière, avec valeur de repli."""
    raw: str = get_env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"La variable {name} doit être un entier (valeur reçue : {raw!r})"
        ) from exc


def get_env_bool(name: str, default: bool = False) -> bool:
    """Lit une variable d'environnement booléenne, avec valeur de repli."""
    raw: str = get_env(name)
    if not raw:
        return default
    return raw.lower() in _TRUE_VALUES


@dataclass(frozen=True, slots=True)
class PoolSettings:
    """Paramètres du pool de connexions SQLAlchemy."""

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    connect_timeout: int = 10

    @classmethod
    def from_env(cls) -> "PoolSettings":
        """Construit les paramètres de pool depuis l'environnement."""
        return cls(
            pool_size=get_env_int("DB_POOL_SIZE", 5),
            max_overflow=get_env_int("DB_MAX_OVERFLOW", 10),
            pool_timeout=get_env_int("DB_POOL_TIMEOUT", 30),
            pool_recycle=get_env_int("DB_POOL_RECYCLE", 1800),
            connect_timeout=get_env_int("DB_CONNECT_TIMEOUT", 10),
        )


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    """Paramètres de connexion PostgreSQL."""

    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str = ""
    sslmode: str = "prefer"

    @classmethod
    def from_env(cls) -> "PostgresSettings":
        """Construit la configuration PostgreSQL depuis l'environnement.

        Raises:
            ConfigurationError: Si une variable obligatoire est absente.
        """
        return cls(
            host=get_env("PG_HOST", required=True),
            port=get_env_int("PG_PORT", 5432),
            user=get_env("PG_USER", required=True),
            password=get_env("PG_PASSWORD", required=True),
            database=get_env("PG_DB_NAME", required=True),
            schema=get_env("PG_SCHEMA"),
            sslmode=get_env("PG_SSLMODE", "prefer"),
        )


@dataclass(frozen=True, slots=True)
class OracleSettings:
    """Paramètres de connexion Oracle.

    `service_name` est prioritaire sur `sid` : Oracle recommande l'usage du
    service name, le SID étant conservé pour les bases anciennes.
    """

    host: str
    port: int
    user: str
    password: str
    service_name: str = ""
    sid: str = ""
    client_mode: str = "thin"
    client_lib_dir: str = ""

    def __post_init__(self) -> None:
        if not self.service_name and not self.sid:
            raise ConfigurationError(
                "Configuration Oracle invalide : renseigner ORACLE_SERVICE_NAME "
                "ou ORACLE_SID."
            )
        if self.client_mode not in {"thin", "thick"}:
            raise ConfigurationError(
                "ORACLE_CLIENT_MODE doit valoir 'thin' ou 'thick' "
                f"(valeur reçue : {self.client_mode!r})"
            )

    @classmethod
    def from_env(cls) -> "OracleSettings":
        """Construit la configuration Oracle depuis l'environnement.

        Raises:
            ConfigurationError: Si une variable obligatoire est absente ou invalide.
        """
        return cls(
            host=get_env("ORACLE_HOST", required=True),
            port=get_env_int("ORACLE_PORT", 1521),
            user=get_env("ORACLE_USER", required=True),
            password=get_env("ORACLE_PASSWORD", required=True),
            service_name=get_env("ORACLE_SERVICE_NAME"),
            sid=get_env("ORACLE_SID"),
            client_mode=get_env("ORACLE_CLIENT_MODE", "thin").lower(),
            client_lib_dir=get_env("ORACLE_CLIENT_LIB_DIR"),
        )


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Configuration transverse de l'application."""

    app_env: str = "local"
    log_level: str = "INFO"
    sql_echo: bool = False

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Construit la configuration applicative depuis l'environnement."""
        return cls(
            app_env=get_env("APP_ENV", "local"),
            log_level=get_env("LOG_LEVEL", "INFO").upper(),
            sql_echo=get_env_bool("SQL_ECHO", False),
        )


__all__ = [
    "PROJECT_ROOT",
    "ENV_FILE",
    "HOST_ENV_KEYS",
    "REQUIRED_ANY_OF_ENV_KEYS",
    "REQUIRED_ENV_KEYS",
    "AppSettings",
    "OracleSettings",
    "PoolSettings",
    "PostgresSettings",
    "get_env",
    "get_env_bool",
    "get_env_int",
    "load_env",
]
