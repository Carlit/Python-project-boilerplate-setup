"""Tests de scripts/check_config.py.

Chaque test construit un `.env` et un `.env.example` isolés dans `tmp_path` :
aucun accès au vrai `.env` du dépôt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_config

_MODEL: str = """\
APP_ENV=local
PG_HOST=localhost
PG_PORT=5432
PG_USER=changeme
PG_PASSWORD=changeme
PG_DB_NAME=changeme
PG_SCHEMA=
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_USER=changeme
ORACLE_PASSWORD=changeme
ORACLE_SERVICE_NAME=changeme
ORACLE_SID=
"""

_VALID_ENV: str = """\
APP_ENV=local
PG_HOST=pg.prod.internal
PG_PORT=5432
PG_USER=app_user
PG_PASSWORD=s3cret
PG_DB_NAME=app_db
PG_SCHEMA=
ORACLE_HOST=ora.prod.internal
ORACLE_PORT=1521
ORACLE_USER=app_user
ORACLE_PASSWORD=s3cret
ORACLE_SERVICE_NAME=ORCLPDB1
ORACLE_SID=
"""


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


@pytest.fixture(autouse=True)
def _redirect_to_tmp_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fait pointer le script sur des fichiers temporaires, jamais le vrai `.env`."""
    monkeypatch.setattr(check_config, "EXAMPLE_FILE", tmp_path / ".env.example")
    monkeypatch.setattr(check_config, "ENV_FILE", tmp_path / ".env")


def test_main_nominal_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    _write(tmp_path / ".env", _VALID_ENV)

    exit_code = check_config.main()

    assert exit_code == 0
    assert "Configuration valide" in capsys.readouterr().out


def test_main_missing_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    env = _VALID_ENV.replace("PG_DB_NAME=app_db\n", "")
    _write(tmp_path / ".env", env)

    exit_code = check_config.main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "MANQUANT" in out
    assert "PG_DB_NAME" in out


def test_main_changeme_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    env = _VALID_ENV.replace("PG_PASSWORD=s3cret", "PG_PASSWORD=CHANGEME")
    _write(tmp_path / ".env", env)

    exit_code = check_config.main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "ERREUR" in out
    assert "PG_PASSWORD" in out
    assert "CHANGEME" not in out


def test_main_host_still_localhost_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    env = _VALID_ENV.replace("PG_HOST=pg.prod.internal", "PG_HOST=localhost")
    _write(tmp_path / ".env", env)

    exit_code = check_config.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "AVERTISSEMENT" in out
    assert "PG_HOST" in out


def test_main_required_variable_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    env = _VALID_ENV.replace("PG_USER=app_user", "PG_USER=")
    _write(tmp_path / ".env", env)

    exit_code = check_config.main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "ERREUR" in out
    assert "PG_USER" in out
    assert "obligatoire" in out


def test_main_extra_key_is_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    _write(tmp_path / ".env", _VALID_ENV + "DEBUG_TOOLBAR=true\n")

    exit_code = check_config.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "EN TROP" in out
    assert "DEBUG_TOOLBAR" in out


def test_main_oracle_requires_service_name_or_sid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / ".env.example", _MODEL)
    env = _VALID_ENV.replace("ORACLE_SERVICE_NAME=ORCLPDB1", "ORACLE_SERVICE_NAME=")
    _write(tmp_path / ".env", env)

    exit_code = check_config.main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "ORACLE_SERVICE_NAME" in out
    assert "ORACLE_SID" in out


def test_no_value_leaks_in_captured_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "tr3s-s3cr3t-p@ssw0rd"
    _write(tmp_path / ".env.example", _MODEL)
    env = _VALID_ENV.replace("PG_PASSWORD=s3cret", f"PG_PASSWORD={secret}")
    _write(tmp_path / ".env", env)

    check_config.main()

    assert secret not in capsys.readouterr().out
