"""v209: shock_scan -- mode, thresholds, regular-hours gate, VIX, snapshot."""
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.marketdata.shared.tape import TapeEntry
from swingbot.core.scanning import shock_scan

UTC = timezone.utc
D0 = date(2026, 11, 5)                                  # Thursday, EST (UTC-5)
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)          # 10:00 ET, 30 min after the open
TH = shock.ShockThresholds(min_names=2)
CLASSES = {"GLD": "etf", "XAUUSD": "fx", "SPY": "etf", "QQQ": "etf"}


def _frame(last_day=D0, n=30, close=100.0, partial=None):
    idx = pd.bdate_range(end=pd.Timestamp(last_day), periods=n)
    df = pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                       "Close": close, "Volume": 1e6}, index=idx)
    if partial is not None:
        df.iloc[-1, df.columns.get_loc("Close")] = partial
    return df


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(shock_scan.asset_class, "classify", lambda t: CLASSES.get(t, "equity"))
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {})


@pytest.mark.parametrize("raw,mode", [("off", "off"), ("shadow", "shadow"), ("LIVE", "live"),
                                      ("bogus", "off"), ("", "off")])
def test_mode_reads_config_and_anything_unknown_is_off(monkeypatch, raw, mode):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", raw)
    assert shock_scan.shock_mode() == mode


def test_thresholds_map_every_field_and_keep_ints_int(monkeypatch):
    assert set(shock_scan.THRESHOLD_ATTRS) == {f.name for f in fields(shock.ShockThresholds)}
    assert len(set(shock_scan.THRESHOLD_ATTRS.values())) == 17
    monkeypatch.setattr(config, "SHOCK_ATR_K", 1.5)
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 7.0)
    th = shock_scan.thresholds_from_config()
    assert th.atr_k == 1.5 and th.min_names == 7 and isinstance(th.min_names, int)


@pytest.mark.parametrize("step_shock,mode,now,expected", [
    (True, "shadow", NOW, True),
    (True, "live", NOW, True),
    (False, "shadow", NOW, False),                                        # !check, recap, admin
    (True, "off", NOW, False),
    (True, "shadow", datetime(2026, 11, 5, 13, 0, tzinfo=UTC), False),    # 08:00 ET pre-market
    (True, "shadow", datetime(2026, 11, 5, 21, 0, tzinfo=UTC), False),    # 16:00 ET close
    (True, "shadow", datetime(2026, 11, 7, 15, 0, tzinfo=UTC), False),    # Saturday
    (True, "shadow", datetime(2026, 11, 26, 15, 0, tzinfo=UTC), False),   # Thanksgiving
    (True, "shadow", datetime(2026, 11, 27, 17, 0, tzinfo=UTC), True),    # half day, 12:00 ET
    (True, "shadow", datetime(2026, 11, 27, 18, 30, tzinfo=UTC), False),  # after the 13:00 close
])
def test_only_a_flagged_pass_in_the_nyse_regular_session_steps(monkeypatch, step_shock, mode,
                                                                 now, expected):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
    assert shock_scan.should_step(step_shock, now) is expected


def _vix(monkeypatch, entry):
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {"^VIX": entry})


def test_a_fresh_vix_row_is_read(monkeypatch):
    at = NOW - timedelta(seconds=60)
    _vix(monkeypatch, TapeEntry("^VIX", 21.13, 27.21, False, None, at))
    assert shock_scan.read_vix(NOW, TH) == shock.VixTape(21.13, 27.21, at)


@pytest.mark.parametrize("entry", [
    None,
    TapeEntry("^VIX", 21.0, 5.0, False, None, NOW - timedelta(seconds=601)),   # stale
    TapeEntry("^VIX", 21.0, 5.0, True, "VIXY", NOW),                           # proxy, not ^VIX
    TapeEntry("^VIX", None, None, False, None, NOW),                           # no price
    TapeEntry("^VIX", 21.0, 5.0, False, None, None),                           # no time
])
def test_missing_stale_or_proxy_vix_is_empty(monkeypatch, entry):
    _vix(monkeypatch, entry)
    assert shock_scan.read_vix(NOW, TH) == shock.VixTape(None, None, None)


def test_a_failing_tape_read_is_empty(monkeypatch):
    def boom(symbols):
        raise RuntimeError("layer down")
    monkeypatch.setattr(shock_scan.tape, "read_tape", boom)
    assert shock_scan.read_vix(NOW, TH) == shock.VixTape(None, None, None)


def _snap(frames, quotes, *, quotes_at=NOW, sector_of=None, spy_df=None):
    return shock_scan.build_snapshot(frames, quotes, sector_of or {}, now=NOW,
                                     quotes_at=quotes_at, vix=shock.VixTape(None, None, None),
                                     th=TH, spy_ticker="SPY", spy_df=spy_df)


def test_prev_close_is_the_last_completed_bar_and_last_is_the_live_quote():
    frames = {"AAA": _frame(partial=95.0), "BBB": _frame(last_day=D0 - timedelta(days=1))}
    snap = _snap(frames, {"AAA": 94.0}, sector_of={"AAA": "Tech"})
    aaa, bbb = snap.names
    assert (aaa.prev_close, aaa.last, aaa.sector, aaa.is_equity) == (100.0, 94.0, "Tech", True)
    assert aaa.atr14 == pytest.approx(2.0)
    assert bbb.prev_close == 100.0 and bbb.last is None and bbb.sector is None   # no quote


def test_fewer_than_fifteen_completed_bars_has_no_atr():
    frames = {"AAA": _frame(n=15), "BBB": _frame(last_day=D0 - timedelta(days=1), n=15)}
    aaa, bbb = _snap(frames, {"AAA": 99.0, "BBB": 99.0}).names
    assert aaa.atr14 is None and bbb.atr14 == pytest.approx(2.0)


@pytest.mark.parametrize("quotes_at", [None, NOW - timedelta(seconds=301)])
def test_stale_or_untimed_quotes_drop_every_last(quotes_at):
    snap = _snap({"AAA": _frame()}, {"AAA": 94.0}, quotes_at=quotes_at)
    assert snap.names[0].last is None


@pytest.mark.parametrize("bad", [0.0, -3.0, float("nan"), None, "n/a"])
def test_a_non_positive_or_garbage_quote_is_absent(bad):
    assert _snap({"AAA": _frame()}, {"AAA": bad}).names[0].last is None


def test_empty_frames_are_skipped():
    snap = _snap({"AAA": _frame(), "EMPTY": _frame().iloc[0:0], "NONE": None}, {})
    assert [r.ticker for r in snap.names] == ["AAA"]


def test_non_equities_are_flagged_and_benchmarks_come_from_spy_df_and_frames():
    frames = {"GLD": _frame(), "XAUUSD": _frame(), "SPY": _frame(close=1.0),
              "QQQ": _frame(close=400.0)}
    snap = _snap(frames, {"SPY": 495.0, "QQQ": 396.0}, spy_df=_frame(close=500.0))
    equity = {r.ticker: r.is_equity for r in snap.names}
    assert equity["GLD"] is False and equity["XAUUSD"] is False
    assert (snap.spy.prev_close, snap.spy.last, snap.spy.is_equity) == (500.0, 495.0, False)
    assert (snap.qqq.prev_close, snap.qqq.last) == (400.0, 396.0)
    assert snap.as_of == NOW and snap.session_date == D0
    assert snap.minutes_since_open == pytest.approx(30.0)


def test_the_spy_frame_falls_back_to_frames_and_missing_benchmarks_are_none():
    assert _snap({"SPY": _frame(close=480.0)}, {}).spy.prev_close == 480.0
    snap = _snap({"AAA": _frame()}, {})
    assert snap.spy is None and snap.qqq is None
