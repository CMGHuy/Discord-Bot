"""Fixtures for the v205 admin read-performance tests (suite `admin-perf`).

The app, client, auth header and the admin suite's autouse pins are tests/admin's,
imported not copied (DATA_DIR isolation, module reloads, the seeded 10,000 account,
the refresher pinned off). The tests live here because the admin suite sits at its
max_tests cap (precedent: tests/live_api/conftest.py)."""
import importlib
import json
import sys
import types

import pytest

from tests.admin.conftest import (  # noqa: F401
    _clear_login_limiter, _pin_admin_refresher_off, admin_app, auth, client)
from tests.store_seed import seed_store


@pytest.fixture
def sql_counted(db_engine):
    """The admin's statement counter on the test engine.

    In tests `engine.get_engine` is the autouse lazy lookup (tests/conftest.py
    `_store_database`), so the admin's engine hook never sees `db_engine`; attach
    the listener to it directly. Idempotent, and inert outside a request."""
    from swingbot.admin import request_timing
    request_timing._attach(db_engine)
    return db_engine


@pytest.fixture
def logged_in(client):
    """Session login, as tests/admin/test_api_v1_dashboard.py:96-104."""
    from swingbot.admin import app as admin_module
    response = client.post("/api/v1/session", json={"username": admin_module.ADMIN_USERNAME,
                                                   "password": admin_module.ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


@pytest.fixture
def frozen_clock(admin_app, monkeypatch):
    """golden_book.CLOCK_MODULES read FROZEN_NOW (after admin_app's module reloads)."""
    from tests.admin_perf import golden_book as gb
    gb.freeze(monkeypatch, [importlib.import_module(name) for name in gb.CLOCK_MODULES])


@pytest.fixture
def probe_clock(admin_app, monkeypatch):
    """Every loaded swingbot module frozen, recording its clock reads in gb.CALLERS."""
    from tests.admin_perf import golden_book as gb
    gb.freeze(monkeypatch, [m for n, m in list(sys.modules.items()) if n.startswith("swingbot.") and m])
    gb.CALLERS.clear()


@pytest.fixture
def golden_seed(admin_app, tmp_path, monkeypatch):
    """The golden book in the stores, and every outside read pinned to it."""
    import swingbot.admin.dashboard as dash
    from swingbot.admin.api_v1 import risk
    from swingbot.core.analytics import snapshots
    from swingbot.core.marketdata import data, data_refresh, data_store, fx
    from tests.admin_perf import golden_book as gb

    snapshot = tmp_path / "analytics_snapshot.json"
    monkeypatch.setattr(snapshots, "DEFAULT_PATH", str(snapshot))
    snapshot.write_text(json.dumps(snapshots.build_snapshot([], 10000.0, [])), encoding="utf-8")
    seed_store("plans", gb.plans())
    seed_store("trades", gb.trades())
    monkeypatch.setattr(fx, "account_currency_code", lambda: gb.ACCOUNT_CODE)
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker, **_kw: gb.QUOTES.get(str(ticker).upper()))
    monkeypatch.setattr(fx, "_quote_codes", {})
    frames: dict = {}
    monkeypatch.setattr(data_refresh, "refresh_symbol", lambda *a, **k: {"status": "fresh"})
    monkeypatch.setattr(data_store, "load_normalized", lambda symbol, interval, *a, **k: frames.get(symbol))
    monkeypatch.setattr(dash, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(dash, "get_current_price", lambda ticker: gb.PRICES.get(ticker))
    monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(data, "get_current_price_detail",
                        lambda t: data.PriceQuote(gb.PRICES[t], False) if t in gb.PRICES else None)
    for name, value in (("get_daily_data", None), ("get_daily_data_batch", {}), ("get_quote_batch", {})):
        monkeypatch.setattr(data, name, lambda *a, _value=value, **k: _value, raising=False)

    def set_fx(scale: float = 1.0) -> None:
        """Pin every FX rate to FX_CLOSES x scale and drop the process caches holding the old ones."""
        frames.clear()
        frames.update(gb.bars())
        frames.update(gb.fx_frames(scale))
        monkeypatch.setattr(fx, "_frames", {})
        risk._invalidate_cache()

    set_fx(1.0)
    yield types.SimpleNamespace(set_fx=set_fx)
    risk._invalidate_cache()
