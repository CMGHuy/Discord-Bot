"""v209 V209-12: the 2026-11-05 replay fixture builder."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import build_shock_replay_fixture as bsr  # noqa: E402

from swingbot.core.market import shock  # noqa: E402

UTC = timezone.utc


def T(h, m):
    return datetime(2026, 11, 5, h, m, tzinfo=UTC)


def _daily(close=100.0, n=30):
    idx = pd.date_range(end="2026-11-04 05:00", periods=n, freq="B", tz=UTC)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1000}, index=idx)


def _m15(closes, start=None):
    start = start or T(14, 30)
    idx = pd.DatetimeIndex([start + timedelta(minutes=15 * i) for i in range(len(closes))])
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 10}, index=idx)


class FakeProvider:
    def __init__(self):
        self.calls = []

    def history_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe))
        return _m15([99.0, 97.0, 95.0]) if timeframe == "15min" else _daily()


def test_steps_are_the_bar_ends_from_the_settled_open_to_the_close():
    steps = bsr.step_times()
    assert (steps[0], steps[-1], len(steps)) == (T(14, 45), T(21, 0), 26)
    assert all(b - a == timedelta(minutes=15) for a, b in zip(steps, steps[1:]))


def test_last_is_the_close_of_the_last_finished_bar():
    bars = _m15([10.0, 11.0])                    # bars start 14:30 and 14:45
    assert bsr.last_at(bars, T(14, 40)) is None
    assert bsr.last_at(bars, T(14, 45)) == 10.0
    assert bsr.last_at(bars, T(15, 0)) == 11.0
    assert bsr.last_at(None, T(15, 0)) is None


def test_vix_path_climbs_to_the_tape_reading_then_holds():
    prior = 21.13 / 1.2721
    assert bsr.vix_path(T(14, 30)) == {"level": round(prior, 4), "chg_pct": 0.0}
    assert bsr.vix_path(T(14, 55))["chg_pct"] == pytest.approx(13.605, abs=1e-3)
    late = bsr.vix_path(T(18, 0))
    assert late["chg_pct"] == pytest.approx(27.21)
    assert late["level"] == pytest.approx(21.13, abs=1e-3)


def test_a_step_applies_the_live_snapshot_rules(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    daily = {"AAA": bsr.to_daily(_daily(100.0)), "SPY": bsr.to_daily(_daily(500.0))}
    bars = {"AAA": _m15([99.0, 97.0]), "SPY": _m15([498.0, 495.0])}
    step = bsr.fixture_step(T(15, 0), daily, bars, {"AAA": "Tech"})
    (aaa,) = [n for n in step["names"] if n["ticker"] == "AAA"]
    assert (aaa["last"], aaa["prev_close"], aaa["sector"], aaa["is_equity"]) == (97.0, 100.0, "Tech", True)
    assert aaa["atr14"] == pytest.approx(2.0)
    assert step["spy"]["last"] == 495.0 and step["qqq"] is None
    assert step["as_of"] == "2026-11-05T15:00:00+00:00" and step["minutes_since_open"] == 30.0
    assert step["vix"] == bsr.vix_path(T(15, 0))


def test_long_entries_keep_longs_from_the_turn_to_the_close_sorted():
    trades = [
        {"ticker": "AMD", "direction": "bullish", "opened_at": "2026-11-05T15:10:00+00:00"},
        {"ticker": "STX", "direction": "bullish", "opened_at": "2026-11-05T14:36:00+00:00"},
        {"ticker": "MU", "direction": "bullish", "opened_at": "2026-11-05T14:20:00+00:00"},
        {"ticker": "SNDK", "direction": "bearish", "opened_at": "2026-11-05T15:00:00+00:00"},
        {"ticker": "LRCX", "direction": "bullish", "opened_at": "2026-11-06T14:40:00+00:00"},
    ]
    assert bsr.long_entries(trades) == [
        {"ticker": "STX", "opened_at": "2026-11-05T14:36:00+00:00"},
        {"ticker": "AMD", "opened_at": "2026-11-05T15:10:00+00:00"},
    ]


def test_synthetic_steps_are_sufficient_and_sector_balanced():
    steps = bsr.synthetic_steps()
    assert [s["as_of"] for s in steps] == [t.isoformat() for t in bsr.step_times()]
    names = steps[0]["names"]
    sectors = {n["sector"] for n in names}
    assert sum(n["is_equity"] for n in names) >= shock.ShockThresholds().min_names
    assert all(sum(n["sector"] == s for n in names) >= 2 for s in sectors)


def _run(tmp_path, monkeypatch, provider, tickers=("AAA", "BBB")):
    monkeypatch.setattr(bsr, "_trades", lambda: [])
    out = tmp_path / "fx.json"
    rc = bsr.main(["--tickers", ",".join(tickers), "--out", str(out),
                   "--cache-dir", str(tmp_path / "cache")],
                  provider=provider, limiter=bsr.TokenBucket(10**6))
    return rc, json.loads(out.read_text())


def test_too_few_names_falls_back_to_synthetic_and_says_why(tmp_path, monkeypatch):
    rc, fx = _run(tmp_path, monkeypatch, FakeProvider())
    assert rc == 0 and fx["source"] == "synthetic" and fx["vix_interpolated"] is True
    assert "fewer than 20 equities" in fx["note"] and len(fx["steps"]) == 26


def test_missing_keys_fall_back_to_synthetic(tmp_path, monkeypatch):
    def no_keys():
        raise bsr.AlpacaAuthError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
    monkeypatch.setattr(bsr, "make_provider", no_keys)
    _, fx = _run(tmp_path, monkeypatch, None)
    assert fx["source"] == "synthetic" and "AlpacaAuthError" in fx["note"]


def test_each_ticker_is_checkpointed_and_a_rerun_fetches_nothing(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, FakeProvider())
    cached = sorted(p.stem for p in (tmp_path / "cache").glob("*.json"))
    assert cached == ["AAA", "BBB", "QQQ", "SPY"]
    again = FakeProvider()
    _run(tmp_path, monkeypatch, again)
    assert again.calls == []
