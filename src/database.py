"""Couche d'accès aux bases de données PostgreSQL et Oracle via SQLAlchemy.

Point d'entrée unique : :class:`DatabaseManager`.

Principes appliqués :
    * une seule fabrique d'engine par moteur, créée paresseusement et mise en cache ;
    * aucun secret construit par concaténation de chaînes (`URL.create` gère
      l'échappement des mots de passe) ;
    * toute requête passe par une transaction explicite ou un contexte fermé ;
    * les erreurs des drivers sont converties en exceptions applicatives typées ;
    * les messages de log ne contiennent jamais de mot de passe.

Exemple :
    >>> from src.database import DatabaseManager, DatabaseType
    >>> db = DatabaseManager.from_env()
    >>> rows = db.fetch_all(DatabaseType.POSTGRES, "SELECT 1 AS ok")
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.exceptions import ConfigurationError, ConnectionFailedError, QueryError
from src.settings import (
    OracleSettings,
    PoolSettings,
    PostgresSettings,
    get_env_bool,
    load_env,
)

if TYPE_CHECKING:  # pragma: no cover - import réservé au typage
    import pandas as pd
    from sqlalchemy.engine import Connection

logger: Final[logging.Logger] = logging.getLogger(__name__)

_RETRY_ATTEMPTS: Final[int] = 3
_RETRY_BASE_DELAY_SECONDS: Final[float] = 1.0

SqlParams = Mapping[str, Any]


class DatabaseType(str, Enum):
    """Moteurs de base de données pris en charge."""

    POSTGRES = "postgres"
    ORACLE = "oracle"


def build_postgres_url(settings: PostgresSettings) -> URL:
    """Construit l'URL SQLAlchemy PostgreSQL (driver psycopg 3).

    Args:
        settings: Paramètres de connexion PostgreSQL.

    Returns:
        L'URL SQLAlchemy correspondante.
    """
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


def build_oracle_url(settings: OracleSettings) -> URL:
    """Construit l'URL SQLAlchemy Oracle (driver python-oracledb).

    Le service name est privilégié ; le SID sert de repli pour les bases
    anciennes.

    Args:
        settings: Paramètres de connexion Oracle.

    Returns:
        L'URL SQLAlchemy correspondante.

    Raises:
        ConfigurationError: Si ni le service name ni le SID ne sont renseignés.
    """
    if settings.service_name:
        return URL.create(
            drivername="oracle+oracledb",
            username=settings.user,
            password=settings.password,
            host=settings.host,
            port=settings.port,
            query={"service_name": settings.service_name},
        )
    if settings.sid:
        return URL.create(
            drivername="oracle+oracledb",
            username=settings.user,
            password=settings.password,
            host=settings.host,
            port=settings.port,
            database=settings.sid,
        )
    raise ConfigurationError(
        "Configuration Oracle invalide : ni service name ni SID renseigné."
    )


def _init_oracle_thick_client(lib_dir: str) -> None:
    """Initialise le client Oracle en mode thick (Instant Client requis).

    Args:
        lib_dir: Répertoire des bibliothèques Oracle Instant Client.

    Raises:
        ConfigurationError: Si l'initialisation du client échoue.
    """
    try:
        import oracledb

        oracledb.init_oracle_client(lib_dir=lib_dir or None)
    except Exception as exc:  # noqa: BLE001 - remontée en erreur de configuration
        raise ConfigurationError(
            f"Initialisation du client Oracle thick impossible : {exc}"
        ) from exc
    logger.info("Client Oracle initialisé en mode thick (lib_dir=%s)", lib_dir or "auto")


class DatabaseManager:
    """Gestionnaire de connexions PostgreSQL et Oracle.

    Les engines sont créés à la première utilisation puis réutilisés. Une
    instance unique doit être partagée dans l'application ; appeler
    :meth:`dispose` à l'arrêt.
    """

    def __init__(
        self,
        postgres: PostgresSettings | None = None,
        oracle: OracleSettings | None = None,
        pool: PoolSettings | None = None,
        *,
        echo: bool = False,
    ) -> None:
        """Initialise le gestionnaire.

        Args:
            postgres: Configuration PostgreSQL, ou None si le moteur est inutilisé.
            oracle: Configuration Oracle, ou None si le moteur est inutilisé.
            pool: Paramètres du pool de connexions.
            echo: Journalise le SQL émis par SQLAlchemy (debug uniquement).
        """
        self._postgres: PostgresSettings | None = postgres
        self._oracle: OracleSettings | None = oracle
        self._pool: PoolSettings = pool or PoolSettings()
        self._echo: bool = echo
        self._engines: dict[DatabaseType, Engine] = {}

    @classmethod
    def from_env(cls, *, load_dotenv_file: bool = True) -> "DatabaseManager":
        """Construit un gestionnaire à partir des variables d'environnement.

        Une configuration incomplète pour un moteur n'est pas bloquante : le
        moteur concerné est simplement indisponible, et l'erreur n'est levée
        qu'à sa première utilisation.

        Args:
            load_dotenv_file: Charge le fichier `.env` avant lecture.

        Returns:
            Un gestionnaire prêt à l'emploi.
        """
        if load_dotenv_file:
            load_env()

        postgres: PostgresSettings | None = None
        oracle: OracleSettings | None = None

        try:
            postgres = PostgresSettings.from_env()
        except ConfigurationError as exc:
            logger.warning("Configuration PostgreSQL indisponible : %s", exc)

        try:
            oracle = OracleSettings.from_env()
        except ConfigurationError as exc:
            logger.warning("Configuration Oracle indisponible : %s", exc)

        return cls(
            postgres=postgres,
            oracle=oracle,
            pool=PoolSettings.from_env(),
            echo=get_env_bool("SQL_ECHO", False),
        )

    # ------------------------------------------------------------------ engines

    def get_engine(self, db_type: DatabaseType) -> Engine:
        """Retourne l'engine du moteur demandé, en le créant si nécessaire.

        Args:
            db_type: Moteur cible.

        Returns:
            L'engine SQLAlchemy correspondant.

        Raises:
            ConfigurationError: Si le moteur n'est pas configuré.
        """
        engine: Engine | None = self._engines.get(db_type)
        if engine is not None:
            return engine

        created: Engine = self._create_engine(db_type)
        self._engines[db_type] = created
        return created

    def _create_engine(self, db_type: DatabaseType) -> Engine:
        """Crée l'engine correspondant au moteur demandé."""
        if db_type is DatabaseType.POSTGRES:
            if self._postgres is None:
                raise ConfigurationError(
                    "PostgreSQL n'est pas configuré (variables PG_* manquantes)."
                )
            url: URL = build_postgres_url(self._postgres)
            connect_args: dict[str, Any] = {
                "connect_timeout": self._pool.connect_timeout,
                "sslmode": self._postgres.sslmode,
            }
            if self._postgres.schema:
                connect_args["options"] = f"-csearch_path={self._postgres.schema}"
        elif db_type is DatabaseType.ORACLE:
            if self._oracle is None:
                raise ConfigurationError(
                    "Oracle n'est pas configuré (variables ORACLE_* manquantes)."
                )
            if self._oracle.client_mode == "thick":
                _init_oracle_thick_client(self._oracle.client_lib_dir)
            url = build_oracle_url(self._oracle)
            connect_args = {"tcp_connect_timeout": self._pool.connect_timeout}
        else:  # pragma: no cover - garde-fou, l'énumération est exhaustive
            raise ConfigurationError(f"Moteur non pris en charge : {db_type!r}")

        try:
            engine: Engine = create_engine(
                url,
                echo=self._echo,
                pool_pre_ping=True,
                pool_size=self._pool.pool_size,
                max_overflow=self._pool.max_overflow,
                pool_timeout=self._pool.pool_timeout,
                pool_recycle=self._pool.pool_recycle,
                connect_args=connect_args,
                future=True,
            )
        except SQLAlchemyError as exc:
            raise ConnectionFailedError(
                f"Création de l'engine {db_type.value} impossible : {exc}"
            ) from exc

        # render_as_string() masque le mot de passe par défaut.
        logger.info(
            "Engine %s créé (%s)", db_type.value, url.render_as_string(hide_password=True)
        )
        return engine

    # -------------------------------------------------------------- connexions

    def _open_connection(self, db_type: DatabaseType) -> "Connection":
        """Ouvre une connexion avec réessais et backoff exponentiel.

        Seule l'ouverture de la connexion est réessayée : une requête en échec
        ne doit jamais être rejouée automatiquement.

        Args:
            db_type: Moteur cible.

        Returns:
            Une connexion SQLAlchemy ouverte.

        Raises:
            ConnectionFailedError: Si la connexion échoue après tous les essais.
        """
        engine: Engine = self.get_engine(db_type)
        last_error: SQLAlchemyError | None = None

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                return engine.connect()
            except SQLAlchemyError as exc:
                last_error = exc
                if attempt == _RETRY_ATTEMPTS:
                    break
                delay: float = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Connexion %s en échec (tentative %d/%d) : %s — "
                    "nouvel essai dans %.1fs",
                    db_type.value,
                    attempt,
                    _RETRY_ATTEMPTS,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise ConnectionFailedError(
            f"Connexion à {db_type.value} impossible après {_RETRY_ATTEMPTS} "
            f"tentatives : {last_error}"
        ) from last_error

    @contextmanager
    def connect(self, db_type: DatabaseType) -> Iterator["Connection"]:
        """Ouvre une connexion dans une transaction explicite.

        La transaction est validée à la sortie normale du bloc et annulée en
        cas d'exception. Les erreurs survenant dans le corps du bloc sont
        propagées telles quelles, sans réessai.

        Args:
            db_type: Moteur cible.

        Yields:
            Une connexion SQLAlchemy active.

        Raises:
            ConnectionFailedError: Si la connexion échoue après tous les essais.
        """
        connection: "Connection" = self._open_connection(db_type)
        transaction = connection.begin()
        try:
            yield connection
        except BaseException:
            transaction.rollback()
            raise
        else:
            transaction.commit()
        finally:
            connection.close()

    @contextmanager
    def session(self, db_type: DatabaseType) -> Iterator[Session]:
        """Ouvre une session ORM transactionnelle.

        Args:
            db_type: Moteur cible.

        Yields:
            Une session SQLAlchemy ; commit à la sortie, rollback sur exception.

        Raises:
            QueryError: Si la transaction échoue.
        """
        factory = sessionmaker(bind=self.get_engine(db_type), expire_on_commit=False)
        db_session: Session = factory()
        try:
            yield db_session
            db_session.commit()
        except SQLAlchemyError as exc:
            db_session.rollback()
            logger.error("Transaction %s annulée : %s", db_type.value, exc)
            raise QueryError(f"Transaction {db_type.value} en échec : {exc}") from exc
        finally:
            db_session.close()

    # ---------------------------------------------------------------- requêtes

    def fetch_all(
        self,
        db_type: DatabaseType,
        query: str,
        params: SqlParams | None = None,
    ) -> list[dict[str, Any]]:
        """Exécute une requête de lecture et retourne toutes les lignes.

        Args:
            db_type: Moteur cible.
            query: Requête SQL, paramétrée par noms (`:nom`).
            params: Valeurs des paramètres nommés.

        Returns:
            La liste des lignes sous forme de dictionnaires.

        Raises:
            QueryError: Si l'exécution échoue.
        """
        try:
            with self.connect(db_type) as connection:
                result = connection.execute(text(query), params or {})
                rows: list[dict[str, Any]] = [dict(row) for row in result.mappings()]
        except SQLAlchemyError as exc:
            logger.error("Échec de la requête sur %s : %s", db_type.value, exc)
            raise QueryError(f"Requête en échec sur {db_type.value} : {exc}") from exc

        logger.debug("%d ligne(s) lue(s) sur %s", len(rows), db_type.value)
        return rows

    def fetch_one(
        self,
        db_type: DatabaseType,
        query: str,
        params: SqlParams | None = None,
    ) -> dict[str, Any] | None:
        """Exécute une requête et retourne la première ligne, ou None.

        Args:
            db_type: Moteur cible.
            query: Requête SQL paramétrée.
            params: Valeurs des paramètres nommés.

        Returns:
            La première ligne, ou None si le résultat est vide.

        Raises:
            QueryError: Si l'exécution échoue.
        """
        try:
            with self.connect(db_type) as connection:
                result = connection.execute(text(query), params or {})
                row = result.mappings().first()
        except SQLAlchemyError as exc:
            logger.error("Échec de la requête sur %s : %s", db_type.value, exc)
            raise QueryError(f"Requête en échec sur {db_type.value} : {exc}") from exc

        return dict(row) if row is not None else None

    def execute(
        self,
        db_type: DatabaseType,
        statement: str,
        params: SqlParams | Sequence[SqlParams] | None = None,
    ) -> int:
        """Exécute une instruction d'écriture (INSERT/UPDATE/DELETE/DDL).

        Args:
            db_type: Moteur cible.
            statement: Instruction SQL paramétrée.
            params: Paramètres, ou séquence de jeux de paramètres pour un
                traitement par lot.

        Returns:
            Le nombre de lignes affectées (-1 si le driver ne le fournit pas).

        Raises:
            QueryError: Si l'exécution échoue.
        """
        try:
            with self.connect(db_type) as connection:
                result = connection.execute(text(statement), params or {})
                affected: int = result.rowcount
        except SQLAlchemyError as exc:
            logger.error("Échec de l'instruction sur %s : %s", db_type.value, exc)
            raise QueryError(
                f"Instruction en échec sur {db_type.value} : {exc}"
            ) from exc

        logger.info("%d ligne(s) affectée(s) sur %s", affected, db_type.value)
        return affected

    def read_dataframe(
        self,
        db_type: DatabaseType,
        query: str,
        params: SqlParams | None = None,
    ) -> "pd.DataFrame":
        """Exécute une requête et retourne le résultat sous forme de DataFrame.

        Args:
            db_type: Moteur cible.
            query: Requête SQL paramétrée.
            params: Valeurs des paramètres nommés.

        Returns:
            Un DataFrame pandas contenant le résultat.

        Raises:
            QueryError: Si l'exécution échoue.
        """
        import pandas as pd

        try:
            with self.connect(db_type) as connection:
                frame: pd.DataFrame = pd.read_sql_query(
                    sql=text(query), con=connection, params=dict(params or {})
                )
        except (SQLAlchemyError, ValueError) as exc:
            logger.error("Échec du chargement DataFrame sur %s : %s", db_type.value, exc)
            raise QueryError(
                f"Chargement DataFrame en échec sur {db_type.value} : {exc}"
            ) from exc

        logger.debug("DataFrame %s chargé : %s", db_type.value, frame.shape)
        return frame

    # ------------------------------------------------------------ diagnostics

    def ping(self, db_type: DatabaseType) -> bool:
        """Teste la connexion au moteur demandé.

        Args:
            db_type: Moteur cible.

        Returns:
            True si la connexion aboutit, False sinon (aucune exception levée).
        """
        probe: str = (
            "SELECT 1" if db_type is DatabaseType.POSTGRES else "SELECT 1 FROM DUAL"
        )
        try:
            self.fetch_one(db_type, probe)
        except (ConnectionFailedError, QueryError, ConfigurationError) as exc:
            logger.error("Test de connexion %s en échec : %s", db_type.value, exc)
            return False

        logger.info("Test de connexion %s réussi", db_type.value)
        return True

    def dispose(self) -> None:
        """Ferme tous les pools de connexions ouverts."""
        for db_type, engine in self._engines.items():
            engine.dispose()
            logger.info("Engine %s libéré", db_type.value)
        self._engines.clear()

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.dispose()


__all__ = [
    "DatabaseManager",
    "DatabaseType",
    "build_oracle_url",
    "build_postgres_url",
]
