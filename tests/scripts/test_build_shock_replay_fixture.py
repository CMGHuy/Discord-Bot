"""v209 V209-12: the 2026-11-05 replay fixture builder."""
import gzip
import json
import sys
from datetime import date, datetime, timedelta, timezone
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


D_EDT = date(2025, 7, 15)
D_HALF = date(2024, 11, 29)                      # day after Thanksgiving: 13:00 ET close
INFO = {"class": "shock", "spy_prev_close": 600.0, "spy_open": 590.0, "spy_close": 580.0,
        "vix_prev_close": 20.0, "vix_open": 22.0, "vix_close": 25.0}


def U(d, h, m):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


def test_session_bounds_follow_dst_and_half_days():
    assert bsr.session_bounds(date(2026, 11, 5)) == (T(14, 30), T(21, 0))
    assert bsr.session_bounds(D_EDT) == (U(D_EDT, 13, 30), U(D_EDT, 20, 0))
    assert bsr.session_bounds(D_HALF) == (U(D_HALF, 14, 30), U(D_HALF, 18, 0))
    assert (bsr.OPEN_UTC, bsr.CLOSE_UTC) == (T(14, 30), T(21, 0))


def test_step_times_take_a_session_date():
    steps = bsr.step_times(D_EDT)
    assert (steps[0], steps[-1], len(steps)) == (U(D_EDT, 13, 45), U(D_EDT, 20, 0), 26)
    half = bsr.step_times(D_HALF)
    assert (half[0], half[-1], len(half)) == (U(D_HALF, 14, 45), U(D_HALF, 18, 0), 14)


def test_daily_vix_path_ramps_from_the_open_change_to_the_close_change():
    o, c = bsr.session_bounds(D_EDT)
    assert bsr.daily_vix_path(o, o, c, INFO) == {"level": 22.0, "chg_pct": 10.0}
    assert bsr.daily_vix_path(U(D_EDT, 16, 45), o, c, INFO) == {"level": 23.5, "chg_pct": 17.5}
    assert bsr.daily_vix_path(c, o, c, INFO) == {"level": 25.0, "chg_pct": 25.0}
    assert bsr.daily_vix_path(c + timedelta(hours=1), o, c, INFO)["chg_pct"] == 25.0


def test_a_step_takes_an_explicit_vix(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    daily = {"AAA": bsr.to_daily(_daily(100.0)), "SPY": bsr.to_daily(_daily(500.0))}
    bars = {"AAA": _m15([99.0, 97.0]), "SPY": _m15([498.0, 495.0])}
    vix = {"level": 30.0, "chg_pct": 40.0}
    assert bsr.fixture_step(T(15, 0), daily, bars, {"AAA": "Tech"}, vix=vix)["vix"] == vix


def _daily_before(day, close=100.0, n=30):
    idx = pd.date_range(end=pd.Timestamp(day) - pd.Timedelta(days=1), periods=n, freq="B", tz=UTC)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1000}, index=idx)


class RecordingFetch:
    """Stands in for bsr.fetch_raw; records every call."""

    def __init__(self, day):
        self.day, self.calls = day, []

    def __call__(self, provider, ticker, timeframe, start, end, *, limiter):
        self.calls.append((ticker, timeframe, start, end))
        if timeframe == "daily":
            return _daily_before(self.day)
        return _m15([99.0, 97.0, 95.0, 94.0], start=bsr.session_bounds(self.day)[0])


def test_validation_fetch_is_per_day_and_ticker_and_daily_bars_end_before_the_session(
        tmp_path, monkeypatch):
    rec = RecordingFetch(D_EDT)
    monkeypatch.setattr(bsr, "fetch_raw", rec)
    bsr.load_or_fetch("AAA", None, None, tmp_path / D_EDT.isoformat(), day=D_EDT)
    assert rec.calls == [
        ("AAA", "daily", D_EDT - timedelta(days=127), U(D_EDT, 0, 0)),
        ("AAA", "15min", D_EDT, U(D_EDT, 20, 0))]
    assert (tmp_path / "2025-07-15" / "AAA.json").exists()
    bsr.load_or_fetch("AAA", None, None, tmp_path / D_EDT.isoformat(), day=D_EDT)
    assert len(rec.calls) == 2


def _equities(monkeypatch, n):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    monkeypatch.setattr("swingbot.core.scanning.fetch._sector_etfs_for_tickers",
                        lambda tickers: ({t: "Tech" for t in tickers},))
    return [f"E{i:02d}" for i in range(n)]


def test_a_validation_day_carries_its_header_and_the_daily_vix_path(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "fetch_raw", RecordingFetch(D_EDT))
    fx = bsr.build_day_fixture(D_EDT, INFO, _equities(monkeypatch, 20), provider=None,
                               limiter=None, cache_root=tmp_path)
    o, c = bsr.session_bounds(D_EDT)
    assert fx["source"] == "alpaca" and fx["class"] == "shock" and fx["vix_interpolated"] is True
    assert (fx["session_date"], fx["open_utc"], fx["close_utc"]) == (
        "2025-07-15", o.isoformat(), c.isoformat())
    assert fx["spy_daily"] == {"prev_close": 600.0, "open": 590.0, "close": 580.0}
    assert len(fx["steps"]) == 26 and fx["steps"][0]["minutes_since_open"] == 15.0
    assert fx["steps"][0]["vix"] == bsr.daily_vix_path(U(D_EDT, 13, 45), o, c, INFO)
    assert sum(n["is_equity"] for n in fx["steps"][0]["names"]) == 20


def test_too_few_equities_is_unbuildable_and_never_synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "fetch_raw", RecordingFetch(D_EDT))
    fx = bsr.build_day_fixture(D_EDT, INFO, _equities(monkeypatch, 3), provider=None,
                               limiter=None, cache_root=tmp_path)
    assert fx["source"] == "unbuildable" and fx["steps"] == []
    assert "fewer than 20 equities" in fx["note"] and fx["class"] == "shock"


def _days_file(tmp_path, days=("2025-07-15", "2024-11-29")):
    path = tmp_path / "validation_days.json"
    path.write_text(json.dumps({"days": {d: dict(INFO) for d in days}}), encoding="utf-8")
    return path


def test_run_validation_writes_one_gz_per_day_and_skips_finished_days(tmp_path, monkeypatch):
    built = []

    def fake(day, info, tickers, **kw):
        built.append(day)
        return bsr.unbuildable_fixture(day, info, "fake")
    monkeypatch.setattr(bsr, "build_day_fixture", fake)
    out = tmp_path / "out"
    kw = dict(provider=None, limiter=None, cache_root=tmp_path / "cache", out_dir=out)
    assert bsr.run_validation(_days_file(tmp_path), ["AAA"], **kw) == ["2024-11-29", "2025-07-15"]
    fx = bsr.read_gz(out / "2025-07-15.json.gz")
    assert fx["source"] == "unbuildable" and fx["session_date"] == "2025-07-15"
    assert bsr.run_validation(_days_file(tmp_path), ["AAA"], **kw) == [] and len(built) == 2


def test_gz_bytes_are_deterministic(tmp_path):
    payload = {"b": [1, 2.5], "a": "x"}
    bsr.write_gz(tmp_path / "1.json.gz", payload)
    bsr.write_gz(tmp_path / "2.json.gz", payload)
    assert (tmp_path / "1.json.gz").read_bytes() == (tmp_path / "2.json.gz").read_bytes()
    assert bsr.read_gz(tmp_path / "1.json.gz") == payload
    with gzip.open(tmp_path / "1.json.gz", "rt", encoding="utf-8") as fh:
        assert json.load(fh) == payload


def test_validation_mode_without_keys_writes_nothing(tmp_path, monkeypatch):
    def no_keys():
        raise bsr.AlpacaAuthError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
    monkeypatch.setattr(bsr, "make_provider", no_keys)
    out = tmp_path / "out"
    rc = bsr.main(["--validation-days", str(_days_file(tmp_path)), "--out-dir", str(out),
                   "--tickers", "AAA"])
    assert rc == 2 and not out.exists()


def test_an_operator_records_an_unbuildable_day_with_its_reason(tmp_path):
    out, days = tmp_path / "out", _days_file(tmp_path)
    args = ["--validation-days", str(days), "--out-dir", str(out), "--reason", "HTTP 500 x3"]
    assert bsr.main([*args, "--unbuildable", "2025-07-15"]) == 0
    fx = bsr.read_gz(out / "2025-07-15.json.gz")
    assert fx["source"] == "unbuildable" and "HTTP 500 x3" in fx["note"]
    assert bsr.main([*args, "--unbuildable", "2025-07-16"]) == 2      # not on the frozen list


def test_fixture_tickers_are_the_frozen_watchlist(tmp_path):
    fx = {"steps": [{"names": [{"ticker": "MU"}, {"ticker": "AMD"}]},
                    {"names": [{"ticker": "MU"}, {"ticker": "XAUUSD"}]}]}
    path = tmp_path / "fx.json"
    path.write_text(json.dumps(fx), encoding="utf-8")
    assert bsr.fixture_tickers(path) == ["AMD", "MU", "XAUUSD"]
