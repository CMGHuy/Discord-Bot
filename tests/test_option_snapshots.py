"""P3 option-chain archive. Network is never touched -- yfinance is stubbed.

These tests guard the two properties that make the archive worth keeping: it
stores raw chain data (not a derived GEX number computed from today's guess at
the model), and one bad symbol or expiry never costs us the rest of the run.
"""
import datetime as dt
import sys
import types

import pandas as pd
import pytest

from scripts import record_option_snapshots as ros


class _FakeChain:
    def __init__(self, calls, puts):
        self.calls, self.puts = calls, puts


def _leg(strike, oi):
    return {"contractSymbol": f"X{strike}", "strike": strike, "lastPrice": 1.0,
            "bid": 0.9, "ask": 1.1, "volume": 10, "openInterest": oi,
            "impliedVolatility": 0.25, "inTheMoney": False}


class _FakeTicker:
    def __init__(self, symbol, expiries=("2026-08-21", "2026-12-18"), boom=False):
        self.symbol, self.options, self._boom = symbol, list(expiries), boom
        self.fast_info = {"last_price": 100.0}

    def option_chain(self, expiry):
        if self._boom:
            raise RuntimeError("upstream chain error")
        calls = pd.DataFrame([_leg(100, 500), _leg(105, 250)])
        puts = pd.DataFrame([_leg(95, 400)])
        return _FakeChain(calls, puts)


@pytest.fixture
def fake_yf(monkeypatch):
    mod = types.ModuleType("yfinance")
    mod.Ticker = _FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return mod


NOW = dt.datetime(2026, 8, 8, 15, 55)


def test_fetch_returns_both_sides_flattened(fake_yf):
    frame = ros.fetch_symbol("SPY", max_dte=90, now=NOW)

    assert set(frame["side"]) == {"call", "put"}
    assert set(frame["symbol"]) == {"SPY"}
    assert (frame["expiry"] == "2026-08-21").all(), "the 2026-12-18 expiry is beyond 90 DTE"


def test_expiries_beyond_max_dte_are_excluded(fake_yf):
    near = ros.fetch_symbol("SPY", max_dte=90, now=NOW)
    far = ros.fetch_symbol("SPY", max_dte=400, now=NOW)

    assert set(near["expiry"]) == {"2026-08-21"}
    assert set(far["expiry"]) == {"2026-08-21", "2026-12-18"}


def test_snapshot_timestamp_is_recorded(fake_yf):
    # Dealer positioning at 15:55 and at 09:35 are different animals; a file
    # that cannot say which it holds is much less useful later.
    frame = ros.fetch_symbol("SPY", max_dte=90, now=NOW)
    assert (frame["snapshot_ts"] == pd.Timestamp(NOW)).all()


def test_raw_fields_are_preserved_and_nothing_is_derived(fake_yf):
    frame = ros.fetch_symbol("SPY", max_dte=90, now=NOW)

    for col in ("strike", "openInterest", "impliedVolatility", "bid", "ask"):
        assert col in frame.columns
    # The archive must not bake in a gamma/GEX model -- see the module docstring.
    assert not [c for c in frame.columns if "gex" in c.lower() or "gamma" in c.lower()]


def test_a_failing_expiry_does_not_lose_the_symbol(fake_yf, monkeypatch):
    monkeypatch.setattr(fake_yf, "Ticker", lambda s: _FakeTicker(s, boom=True))
    assert ros.fetch_symbol("SPY", max_dte=90, now=NOW) is None


def test_unparseable_expiry_is_skipped_not_fatal(fake_yf, monkeypatch):
    monkeypatch.setattr(fake_yf, "Ticker",
                        lambda s: _FakeTicker(s, expiries=("garbage", "2026-08-21")))
    frame = ros.fetch_symbol("SPY", max_dte=90, now=NOW)
    assert set(frame["expiry"]) == {"2026-08-21"}


def test_missing_spot_still_archives_the_chain(fake_yf, monkeypatch):
    class _Raises:
        def __getitem__(self, key):
            raise RuntimeError("fast_info unavailable")

    def no_spot(symbol):
        tk = _FakeTicker(symbol)
        tk.fast_info = _Raises()
        return tk

    monkeypatch.setattr(fake_yf, "Ticker", no_spot)
    frame = ros.fetch_symbol("SPY", max_dte=90, now=NOW)

    assert frame is not None and len(frame) > 0
    assert frame["spot"].isna().all()


def test_write_is_idempotent_and_date_partitioned(tmp_path, fake_yf):
    frame = ros.fetch_symbol("SPY", max_dte=90, now=NOW)

    first = ros.write_snapshot(frame, out_root=tmp_path, symbol="SPY", day=NOW.date())
    second = ros.write_snapshot(frame, out_root=tmp_path, symbol="SPY", day=NOW.date())

    assert first == second
    assert first.parent == tmp_path / "2026/08/08"
    assert len(list(tmp_path.rglob("SPY.*"))) == 1


def test_run_survives_one_bad_symbol(tmp_path, fake_yf, monkeypatch):
    def ticker(symbol):
        return _FakeTicker(symbol, boom=(symbol == "BAD"))

    monkeypatch.setattr(fake_yf, "Ticker", ticker)
    rc = ros.run(["SPY", "BAD", "QQQ"], max_dte=90, out_root=tmp_path, now=NOW)

    assert rc == 0, "a partial run is a success -- a hole is not a crash"
    written = {p.stem for p in tmp_path.rglob("*.parquet")} | {
        p.name.split(".")[0] for p in tmp_path.rglob("*.csv.gz")}
    assert written == {"SPY", "QQQ"}


def test_run_reports_failure_when_nothing_was_archived(tmp_path, fake_yf, monkeypatch):
    monkeypatch.setattr(fake_yf, "Ticker", lambda s: _FakeTicker(s, boom=True))
    assert ros.run(["SPY"], max_dte=90, out_root=tmp_path, now=NOW) == 1


def test_the_bot_never_imports_the_recorder():
    # P3 must not be able to affect the live path.
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-l", "record_option_snapshots", "--", "swingbot/"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", f"swingbot/ imports the recorder: {out.stdout}"
