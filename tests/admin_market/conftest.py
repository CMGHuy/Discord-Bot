"""Fakes for the v201 request-path door: quote cache, queue, marks, heartbeat.

The admin app fixtures are reused as-is from tests/admin/conftest.py. Its
autouse `_pin_admin_refresher_off` is deliberately NOT imported."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import DataKind, Entry, QuoteDetail
from tests.admin.conftest import _clear_login_limiter, admin_app, auth, client  # noqa: F401


def utcnow():
    return datetime.now(timezone.utc)


def quote_entry(symbol, price, *, age_s, source="alpaca-iex"):
    at = utcnow() - timedelta(seconds=age_s)
    doc = QuoteDetail(symbol=symbol, price=price, trade_at=at, bid=None, ask=None,
                      quote_at=None, source=source).to_doc()
    return Entry(doc, at, source, "ok")


@dataclass
class FakeQueue:
    pending: dict = field(default_factory=dict)          # (kind, key) -> priority

    def enqueue(self, kind, keys, *, priority):
        added = 0
        for key in keys:
            old = self.pending.get((kind, key))
            if old is None:
                added += 1
            if old is None or priority < old:
                self.pending[(kind, key)] = priority
        return added


@dataclass
class FakeMarks:
    in_flight: set = field(default_factory=set)
    errors_by_key: dict = field(default_factory=dict)
    changed: list = field(default_factory=list)

    def active(self, keys, now=None):
        return {k for k in keys if k in self.in_flight}

    def errors(self, keys):
        return {k: self.errors_by_key[k] for k in keys if k in self.errors_by_key}

    def changed_since(self, since):
        return list(self.changed)


@dataclass
class FakeHeartbeat:
    row: dict | None = None

    def read(self):
        return self.row


@dataclass
class Market:
    cache: dict = field(default_factory=dict)             # (kind, SYMBOL) -> Entry
    queue: FakeQueue = field(default_factory=FakeQueue)
    marks: FakeMarks = field(default_factory=FakeMarks)
    heartbeat: FakeHeartbeat = field(default_factory=FakeHeartbeat)

    def quote(self, symbol, price, *, age_s, kind=DataKind.QUOTE, source="alpaca-iex"):
        self.cache[(kind, symbol.upper())] = quote_entry(
            symbol.upper(), price, age_s=age_s, source=source)


@pytest.fixture
def market(monkeypatch):
    from swingbot.core.db.repositories import market_refresh
    from swingbot.core.marketdata.shared import layer
    state = Market()
    monkeypatch.setattr(layer, "last_cached", lambda kind, symbols, params="": {
        s: state.cache[(kind, s)] for s in symbols if (kind, s) in state.cache})
    monkeypatch.setattr(market_refresh, "refresh_queue_repo", lambda: state.queue)
    monkeypatch.setattr(market_refresh, "refresh_mark_repo", lambda: state.marks)
    monkeypatch.setattr(market_refresh, "refresher_heartbeat_repo", lambda: state.heartbeat)
    return state


@pytest.fixture
def session_is(monkeypatch):
    from swingbot.core.market import session

    def pin(state):
        monkeypatch.setattr(session, "session_state", lambda now=None: state)
    pin("regular")
    return pin


@pytest.fixture
def refresher_on(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")


@pytest.fixture
def on_client(admin_app, market, session_is, auth, monkeypatch):
    # After admin_app, which pins MARKETDATA_LAYER="off" for the admin suite.
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    c = admin_app.test_client()
    c.environ_base["HTTP_AUTHORIZATION"] = auth["Authorization"]
    return c
