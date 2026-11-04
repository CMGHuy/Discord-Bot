"""swing_db resolves the one local database from .env without exposing it."""
import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def swing_db():
    spec = importlib.util.spec_from_file_location("swing_db_mod", REPO / "scripts/dev/swing_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_takes_credentials_from_env_and_swaps_host_port_database(swing_db, tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("SWING_DB_PORT", raising=False)
    env = _env(tmp_path, "X=1\nDATABASE_URL='postgresql+psycopg://bot:s3cret@db:5432/swingbot'\n")
    assert swing_db.local_url(env_file=env) == "postgresql+psycopg://bot:s3cret@127.0.0.1:56789/swingbot_test"
    assert swing_db.local_url("swingbot_prod_replica", env_file=env).endswith("@127.0.0.1:56789/swingbot_prod_replica")


def test_port_override_and_explicit_test_url(swing_db, tmp_path, monkeypatch):
    env = _env(tmp_path, "DATABASE_URL=postgresql://u:p@db/swingbot\n")
    monkeypatch.setenv("SWING_DB_PORT", "60000")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert ":60000/" in swing_db.local_url(env_file=env)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://ci:ci@h:1/t")
    assert swing_db.local_url(env_file=env) == "postgresql+psycopg://ci:ci@h:1/t"
    # The explicit URL names the TEST database only; another database is still derived.
    assert swing_db.local_url("swingbot_prod_replica", env_file=env).endswith("/swingbot_prod_replica")


def test_missing_or_empty_env_falls_back(swing_db, tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    assert swing_db.local_url(env_file=tmp_path / "absent") == swing_db.FALLBACK_URL
    assert swing_db.local_url(env_file=_env(tmp_path, "OTHER=1\n")) == swing_db.FALLBACK_URL


def test_main_checkout_has_a_git_dir(swing_db):
    assert (swing_db.main_checkout() / ".git").exists()
