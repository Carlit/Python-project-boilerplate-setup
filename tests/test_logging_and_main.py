"""Tests de la journalisation et du point d'entrée."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src import settings as settings_module
from src.database import DatabaseType
from src.logging_config import setup_logging
from src.main import main, parse_args


def test_setup_logging_configures_console_handler() -> None:
    root = setup_logging("DEBUG", force=True)
    assert root.level == logging.DEBUG
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)


def test_setup_logging_writes_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "app.log"
    logger = setup_logging("INFO", log_file=log_file, force=True)
    logger.info("message de test")
    for handler in logger.handlers:
        handler.flush()
    assert log_file.is_file()
    assert "message de test" in log_file.read_text(encoding="utf-8")


def test_setup_logging_silences_sqlalchemy_engine() -> None:
    setup_logging("DEBUG", force=True)
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.check == "all"
    assert args.log_file is None


def test_parse_args_accepts_each_database() -> None:
    for db_type in DatabaseType:
        assert parse_args(["--check", db_type.value]).check == db_type.value


def test_parse_args_rejects_unknown_database() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--check", "mysql"])


def test_main_returns_failure_without_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ENV_FILE est résolu depuis l'emplacement du module (src/settings.py),
    # pas depuis le répertoire courant : changer le cwd ne l'isole pas. Il
    # faut rediriger ENV_FILE lui-même pour ignorer le vrai `.env` du dépôt.
    monkeypatch.setattr(settings_module, "ENV_FILE", tmp_path / ".env")
    assert main(["--check", "postgres"]) == 1
