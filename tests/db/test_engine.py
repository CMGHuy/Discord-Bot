"""Engine construction is lazy, singleton-scoped, and validates its URL."""
import pytest

from swingbot import config
from swingbot.core.db import engine as dbengine


@pytest.fixture(autouse=True)
def _clean_engine():
    dbengine.reset_engine()
    yield
    dbengine.reset_engine()


def test_missing_url_fails_clearly(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    with pytest.raises(dbengine.DatabaseUnavailable, match="DATABASE_URL"):
        dbengine.get_engine()


def test_engine_is_a_singleton_and_reset_rebuilds_it(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    first = dbengine.get_engine()
    assert dbengine.get_engine() is first
    dbengine.reset_engine()
    assert dbengine.get_engine() is not first


def test_url_must_select_the_installed_psycopg_driver(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:p@localhost/db")
    with pytest.raises(dbengine.DatabaseUnavailable, match="postgresql\\+psycopg://"):
        dbengine.get_engine()


def test_database_fields_have_the_correct_safety_flags():
    fields = {field.key: field for field in config.FIELDS}
    assert fields["DATABASE_URL"].sensitive is True
    assert fields["DATABASE_URL"].hot_reloadable is False
    assert fields["POSTGRES_PASSWORD"].sensitive is True
    assert fields["POSTGRES_PASSWORD"].hot_reloadable is False
    assert fields["DB_STORES"].sensitive is False
    assert fields["DB_STORES"].hot_reloadable is True
