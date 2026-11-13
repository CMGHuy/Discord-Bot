"""v227: record_feed_post -- one row per accepted simple-channel post, never raising,
only through the fail-fast side engine, pruned at most once an hour."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import schema, side_engine
from swingbot.core.db.engine import DatabaseUnavailable
from swingbot.core.db.repositories import feed_posts as repo_module
from swingbot.core.infra import feed_posts as recorder
from swingbot.core.presentation import components
from swingbot.core.presentation.kinds import Kind

CONN = object()


class _Repo:
    def __init__(self):
        self.inserts, self.prunes = [], []

    def insert(self, kind, ticker, headline, *, conn):
        self.inserts.append((kind, ticker, headline, conn))
        return len(self.inserts)

    def prune(self, days, *, conn):
        self.prunes.append((days, conn))
        return 0


@pytest.fixture
def env(monkeypatch):
    """Recording on, a fake side connection and a recording repository."""
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", True)
    state = SimpleNamespace(repo=_Repo(), connections=0, raise_on_connect=None, now=1000.0)

    @contextmanager
    def fake_side_connection():
        state.connections += 1
        if state.raise_on_connect is not None:
            raise state.raise_on_connect
        yield CONN

    monkeypatch.setattr(side_engine, "side_connection", fake_side_connection)
    monkeypatch.setattr(repo_module, "feed_posts_repo", lambda: state.repo)
    monkeypatch.setattr(recorder, "_clock", lambda: state.now)
    recorder.reset_prune_clock()
    yield state
    recorder.reset_prune_clock()


def test_an_accepted_post_inserts_one_row_through_the_side_connection(env):
    embed = components.push_embed(Kind.FILLED, "MSFT", "bullish")
    recorder.record_feed_post(embed, "MSFT")
    assert env.repo.inserts == [("FILLED", "MSFT", "Order filled, MSFT", CONN)]


def test_an_explicit_kind_wins_over_the_embeds(env):
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "MSFT", kind=Kind.CANCEL)
    assert env.repo.inserts[0][:2] == ("CANCEL", "MSFT")


def test_an_embed_without_a_kind_records_nothing(env):
    recorder.record_feed_post(SimpleNamespace(), "MSFT")
    recorder.record_feed_post(components.status_embed("t", "d", 0), "MSFT")
    assert env.repo.inserts == [] and env.connections == 0


def test_a_blank_ticker_is_stored_as_null(env):
    recorder.record_feed_post(SimpleNamespace(kind=Kind.RISK_CAP), "")
    assert env.repo.inserts == [("RISK_CAP", None, "Cancelled by risk cap", CONN)]


def test_switched_off_it_touches_no_connection_and_no_embed(env, monkeypatch):
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", False)

    class Exploding:
        @property
        def kind(self):
            raise AssertionError("read the embed with the switch off")

    recorder.record_feed_post(Exploding(), "MSFT")
    assert env.connections == 0 and env.repo.inserts == []


@pytest.mark.parametrize("exc", [DatabaseUnavailable("down"),
                                 sa.exc.OperationalError("SELECT 1", {}, Exception("timeout")),
                                 RuntimeError("boom")])
def test_a_failing_connection_is_swallowed(env, exc):
    env.raise_on_connect = exc
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "MSFT")   # must not raise
    assert env.repo.inserts == [] and env.repo.prunes == []


def test_a_broken_embed_is_swallowed(env):
    class Broken:
        @property
        def kind(self):
            raise RuntimeError("boom")

    recorder.record_feed_post(Broken(), "MSFT")
    assert env.repo.inserts == []


def test_the_first_post_prunes_then_not_again_within_the_hour(env):
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "A")
    env.now += recorder.PRUNE_EVERY_S - 1
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "B")
    assert env.repo.prunes == [(recorder.RETENTION_DAYS, CONN)]
    env.now += 1
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "C")
    assert len(env.repo.prunes) == 2


def test_a_failing_prune_is_swallowed_and_not_retried_every_post(env):
    def boom(days, *, conn):
        env.repo.prunes.append((days, conn))
        raise RuntimeError("prune failed")

    env.repo.prune = boom
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "A")
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "B")
    assert len(env.repo.inserts) == 2 and len(env.repo.prunes) == 1


def test_constants():
    assert (recorder.RETENTION_DAYS, recorder.PRUNE_EVERY_S) == (7, 3600)


def test_the_module_imports_no_presentation_or_repository_at_load():
    source = recorder.__file__
    text = open(source, encoding="utf-8").read()
    top = text.split("def record_feed_post", 1)[0]
    assert "swingbot.core.presentation" not in top
    assert "repositories.feed_posts" not in top


@pytest.fixture
def side_db(db_committed, db_engine, monkeypatch):
    """The real side engine pointed at this worker's test database (tests/db/test_side_engine.py)."""
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 250)
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", True)
    side_engine.reset()
    recorder.reset_prune_clock()
    yield db_committed
    side_engine.reset()
    recorder.reset_prune_clock()


def test_a_real_row_lands_through_the_side_engine(side_db):
    embed = components.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish", "Lv3")
    embed.entry_price = 187.5
    recorder.record_feed_post(embed, "AAPL")
    rows = side_db.execute(sa.select(schema.feed_posts.c.kind, schema.feed_posts.c.ticker,
                                     schema.feed_posts.c.headline)).all()
    assert [tuple(r) for r in rows] == [("SETUP_SIMPLE", "AAPL", "New long alert, AAPL, buy at 187.50")]
