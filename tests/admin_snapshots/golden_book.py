"""The seeded book and frozen request-time payloads for v204 parity tests."""
from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from tests.admin.conftest import _clear_login_limiter, admin_app, client  # noqa: F401
from tests.store_seed import seed_store


GOLDEN_DIR = Path(__file__).with_name("golden")
GOLDEN_NAMES: tuple[str, ...] = (
    "risk", "performance_main", "equity_curve_main", "calendar_pnl",
    "analytics_snapshot", "sparkline",
)
GOLDEN_NOW = datetime(2026, 10, 28, 21, 0, tzinfo=timezone.utc)
GOLDEN_MONTH = "2026-06"
BAR_SYMBOLS: tuple[str, ...] = ("AAPL", "MSFT", "SAP.DE", "SPY")
QUOTE_CODES = {"SAP.DE": "EUR"}
FX_RATES = {("EUR", "USD"): 1.1}
SECTORS = {"AAPL": "Technology", "MSFT": "Technology"}  # SAP.DE is intentionally unmapped.
NETWORK: tuple[tuple[str, str], ...] = (
    ("swingbot.core.marketdata.yf_safe", "download"),
    ("swingbot.core.marketdata.data", "get_quote_batch"),
    ("swingbot.core.marketdata.data", "get_current_price"),
    ("swingbot.core.marketdata.data", "get_current_price_batch"),
    ("swingbot.core.marketdata.data", "prefetch_prices"),
    ("swingbot.core.marketdata.data", "_provider_currency_code"),
    ("swingbot.core.marketdata.data_refresh", "refresh_symbol"),
    ("swingbot.core.marketdata.fx", "_refreshed_frame"),
)
VOLATILE_KEYS = frozenset({"checked_at", "built_at"})
TOP_LEVEL_DROPPED = ("killswitch", "scan_health", "as_of")
WALL_CLOCK_PATHS: tuple[str, ...] = ()


@dataclass
class GoldenBook:
    client: object
    tmp_path: Path
    network_calls: list[str] = field(default_factory=list)


def _bars(symbol: str) -> pd.DataFrame:
    phase = BAR_SYMBOLS.index(symbol)
    index = pd.bdate_range(end=GOLDEN_NOW.date(), periods=300, name="Date")
    close = [
        round(100 + 5 * math.sin(i / 7 + phase) + 0.02 * i * (phase + 1), 4)
        for i in range(len(index))
    ]
    return pd.DataFrame({
        "Open": [c - 0.5 for c in close],
        "High": [c + 1 for c in close],
        "Low": [c - 1 for c in close],
        "Close": close,
        "Volume": [1_000_000 + i for i in range(len(index))],
    }, index=index)


def _open_trades() -> list[dict]:
    rows = [
        ("AAPL", 100.0, 95.0, 10),
        ("MSFT", 200.0, 190.0, 5),
        ("SAP.DE", 150.0, 140.0, 4),
    ]
    return [
        {"id": f"o{i:015d}", "ticker": ticker, "status": "open", "direction": "bullish",
         "strategy": "VWAP", "horizon_key": "1m", "ledger": "main", "confidence_level": 3,
         "entry": entry, "stop_loss": stop, "take_profit": entry * 1.2, "shares": shares,
         "opened_at": "2026-08-03T14:00:00+00:00"}
        for i, (ticker, entry, stop, shares) in enumerate(rows, 1)
    ]


def _closed(trade_id: str, ticker: str, opened: datetime, win: bool, ledger: str) -> dict:
    exit_price = 110.0 if win else 92.0
    return {
        "id": trade_id, "ticker": ticker, "status": "win" if win else "loss",
        "direction": "bullish", "strategy": "VWAP", "horizon_key": "1m", "ledger": ledger,
        "confidence_level": 3,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 120.0, "exit_price": exit_price,
        "shares": 10, "realized_pnl_amount": round((exit_price - 100.0) * 10, 2),
        "opened_at": opened.isoformat(), "closed_at": (opened + timedelta(days=3)).isoformat(),
    }


def _closed_trades() -> list[dict]:
    start = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
    tickers = ("AAPL", "MSFT", "SAP.DE")
    main = [
        _closed(f"c{i:015d}", tickers[i % 3], start + timedelta(days=15 * i), i % 2 == 0, "main")
        for i in range(12)
    ]
    weak = [
        _closed(f"w{i:015d}", "AAPL", datetime(2026, 3, 2 + 7 * i, 14, tzinfo=timezone.utc),
                i == 0, "weak")
        for i in range(2)
    ]
    return main + weak


def _read_bars(symbol) -> pd.DataFrame | None:
    from swingbot.core.marketdata import daily_delta

    return daily_delta.read_daily(str(symbol).upper(), basis=daily_delta.BASIS_YF)


def _write_bars() -> None:
    from swingbot.core.marketdata import daily_delta, data_store

    for symbol in BAR_SYMBOLS:
        _bars(symbol).to_csv(daily_delta.cache_file(symbol, daily_delta.BASIS_YF))
    data_store.clear_normalized_frame_cache()


def _reject_network(calls: list[str], entry_point: str):
    def reject(*args, **kwargs):
        calls.append(entry_point)
        raise AssertionError(f"Golden capture reached {entry_point}")

    return reject


def _poison(monkeypatch, calls: list[str]) -> None:
    for module, name in NETWORK:
        monkeypatch.setattr(
            importlib.import_module(module), name, _reject_network(calls, f"{module}.{name}"),
        )


def _drop_volatile(value):
    if isinstance(value, dict):
        return {key: _drop_volatile(item) for key, item in value.items() if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_drop_volatile(item) for item in value]
    return value


def _drop_path(body: dict, dotted: str) -> None:
    *parents, key = dotted.split(".")
    for parent in parents:
        body = body.get(parent)
        if not isinstance(body, dict):
            return
    body.pop(key, None)


def normalise(body: dict) -> dict:
    result = json.loads(json.dumps(body, sort_keys=True))
    for key in TOP_LEVEL_DROPPED:
        result.pop(key, None)
    _drop_path(result, "availability.killswitch")
    result = _drop_volatile(result)
    for path in WALL_CLOCK_PATHS:
        _drop_path(result, path)
    return result


def golden_payload(name: str) -> dict:
    if name not in GOLDEN_NAMES:
        raise KeyError(name)
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text("utf-8"))


def assert_matches_golden(name: str, body: dict) -> None:
    got = normalise(body)
    want = golden_payload(name)
    missing = set(want) - set(got)
    assert not missing, f"{name} is missing golden keys: {sorted(missing)}"
    assert {key: got[key] for key in want} == want


@pytest.fixture
def golden_book(client, tmp_path, monkeypatch):
    from swingbot.core.analytics import snapshots
    from swingbot.core.backtesting import registry
    from swingbot.core.marketdata import data, fx, universe

    monkeypatch.chdir(tmp_path)
    for attr, value in (("ADMIN_REFRESHER", "off"), ("MARKETDATA_LAYER", "off"),
                        ("MARKET_REGIME_TICKER", "SPY"), ("CURRENCY_SYMBOL", "$")):
        monkeypatch.setattr(config, attr, value)
    monkeypatch.setattr(snapshots, "DEFAULT_PATH", str(tmp_path / "analytics_snapshot.json"))
    monkeypatch.setattr(registry, "load_registry", lambda path=None: [])
    monkeypatch.setattr(universe, "sector_map", lambda name: dict(SECTORS))
    monkeypatch.setattr(fx, "quote_currency_code",
                        lambda ticker, **_kw: QUOTE_CODES.get(str(ticker).upper(), "USD"))
    monkeypatch.setattr(fx, "fx_rate", lambda src, dst, on=None, **_kw:
                        1.0 if src == dst else FX_RATES.get((src, dst)))
    monkeypatch.setattr(data, "get_daily_data", lambda ticker, period="2y", **_kw: _read_bars(ticker))
    monkeypatch.setattr(data, "get_daily_data_batch", lambda tickers, period="2y", **_kw: {
        str(t).upper(): f for t in tickers if (f := _read_bars(t)) is not None})
    book = GoldenBook(client=client, tmp_path=tmp_path)
    _poison(monkeypatch, book.network_calls)
    _write_bars()
    seed_store("account", {
        "balance": 10000.0, "base_balance": 10000.0, "risk_pct": 1.0,
        "max_position_pct": 20.0, "sizing_mode": "risk_pct", "balance_history": [],
    })
    seed_store("trades", _open_trades() + _closed_trades())
    risk = importlib.import_module("swingbot.admin.api_v1.risk")
    risk._invalidate_cache()
    try:
        response = client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200
        yield book
    finally:
        risk._invalidate_cache()
