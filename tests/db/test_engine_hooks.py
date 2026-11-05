"""v205 V205-2: hooks get_engine runs on every engine it creates (index "Engine hook")."""
import pytest

from swingbot import config
from swingbot.core.db import engine

pytestmark = pytest.mark.real_engine

#: Never reached: create_engine opens no connection until first use.
URL = "postgresql+psycopg://v205:v205@127.0.0.1:1/v205_hooks"


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(engine, "_ENGINE_HOOKS", [])
    monkeypatch.setattr(engine, "_engine", None)
    monkeypatch.setattr(config, "DATABASE_URL", URL)
    yield
    if engine._engine is not None:
        engine._engine.dispose()


def test_a_hook_runs_on_the_engine_get_engine_creates(fresh):
    seen = []
    engine.add_engine_hook(seen.append)
    created = engine.get_engine()
    assert seen == [created]
    assert engine.get_engine() is created and seen == [created]   # the cached engine is not re-hooked


def test_a_hook_survives_reset_engine(fresh):
    seen = []
    engine.add_engine_hook(seen.append)
    first = engine.get_engine()
    engine.reset_engine()
    second = engine.get_engine()
    assert seen == [first, second] and first is not second


def test_adding_a_hook_applies_it_to_an_existing_engine_at_once(fresh):
    existing = engine.get_engine()
    seen = []
    engine.add_engine_hook(seen.append)
    assert seen == [existing]


def test_the_same_hook_is_added_once(fresh):
    calls = []

    def hook(created):
        calls.append(created)

    engine.add_engine_hook(hook)
    engine.add_engine_hook(hook)
    engine.get_engine()
    assert engine._ENGINE_HOOKS == [hook] and len(calls) == 1


def test_a_failing_hook_never_breaks_get_engine(fresh):
    from swingbot.core.infra import swallowed

    def broken(_created):
        raise RuntimeError("listener failed")

    seen = []
    engine.add_engine_hook(broken)
    engine.add_engine_hook(seen.append)
    created = engine.get_engine()
    assert seen == [created]                          # later hooks still run
    assert swallowed.snapshot()["ops.db_engine.apply_hooks"]["count"] >= 1
