"""The test runner should turn an absent optional database into one hint."""
import importlib.util
import pathlib
import socket

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def testrun():
    spec = importlib.util.spec_from_file_location("testrun_mod", REPO / "scripts/dev/testrun.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_url_matches_db_fixture(testrun):
    from tests.db.conftest import DEFAULT_TEST_URL
    assert testrun.TEST_DB_URL_DEFAULT == DEFAULT_TEST_URL


def test_preflight_returns_actionable_text_when_unreachable(testrun, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", refuse)
    assert "docker compose --profile test up -d db-test" in testrun.db_preflight()


def test_preflight_is_silent_when_reachable(testrun, monkeypatch):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *_args, **_kwargs: Socket())
    assert testrun.db_preflight() is None
