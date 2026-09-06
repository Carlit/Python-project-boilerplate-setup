"""Hiérarchie d'exceptions applicatives.

Toute erreur remontée par le code métier doit dériver de :class:`AppError`.
Cela permet aux appelants de distinguer une erreur maîtrisée d'un bug.
"""

from __future__ import annotations


class AppError(Exception):
    """Erreur applicative de base."""


class ConfigurationError(AppError):
    """Configuration absente, incomplète ou invalide."""


class DatabaseError(AppError):
    """Erreur liée à une base de données."""


class ConnectionFailedError(DatabaseError):
    """Impossible d'établir une connexion après épuisement des tentatives."""


class QueryError(DatabaseError):
    """Échec d'exécution d'une requête SQL."""


__all__ = [
    "AppError",
    "ConfigurationError",
    "DatabaseError",
    "ConnectionFailedError",
    "QueryError",
]
