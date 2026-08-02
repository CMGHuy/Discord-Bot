"""Plan v8 Task V44: the journal must not fetch live bars on trade close.

`journal_trade_close` used to call `data.get_daily_data()` -- an unguarded
`yf.download()` -- inline in the live trade-close path, every close. That is
what exposed the journal to both of V3's corruption modes: a network hiccup
degrades the entry to no-MFE, and a bad snapshot writes a wild number
(mfe_r = -1845.95 live) that nothing downstream can tell from a real one.
"""
import datetime as dt

import pandas as pd
import pytest

from swingbot.core.analytics import journal
from swingbot.core.analytics.mfe_mae import MAX_PLAUSIBLE_R, compute_mfe_mae


def _bars(start="2026-07-01", days=40, high=110.0, low=95.0):
    idx = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame(
        {"Open": 100.0, "High": high, "Low": low, "Close": 101.0, "Volume": 1_000},
        index=idx)


def _trade(opened="2026-07-05T10:00:00", closed="2026-07-20T15:00:00"):
    return {"id": "t1", "ticker": "AAPL", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
            "opened_at": opened, "closed_at": closed, "status": "win",
            "exit_price": 110.0}


def test_the_cache_is_used_and_no_live_fetch_happens(monkeypatch):
    """The whole point: a trade close must not reach the network."""
    calls = []
    monkeypatch.setattr(journal, "log", journal.log)
    import swingbot.core.backtest_cache as bc
    monkeypatch.setattr(bc, "load_cached", lambda t: _bars())

    import swingbot.core.data as data
    def _boom(*a, **k):
        calls.append("live")
        raise AssertionError("live fetch must not happen when the cache covers the trade")
    monkeypatch.setattr(data, "get_daily_data", _boom)

    df = journal.bars_for_journal(_trade())
    assert df is not None and len(df) == 40
    assert calls == []


def test_it_falls_back_to_live_when_the_ticker_is_not_cached(monkeypatch):
    import swingbot.core.backtest_cache as bc
    import swingbot.core.data as data
    monkeypatch.setattr(bc, "load_cached", lambda t: None)
    sentinel = _bars()
    monkeypatch.setattr(data, "get_daily_data", lambda t, **k: sentinel)

    assert journal.bars_for_journal(_trade()) is sentinel


def test_it_falls_back_when_the_cache_stops_before_the_close_date(monkeypatch):
    """A cache that ends mid-trade would slice to a shorter window and hand
    back an MFE that silently UNDERSTATES the real excursion -- worse than no
    number, because it is indistinguishable from a real one."""
    import swingbot.core.backtest_cache as bc
    import swingbot.core.data as data
    stale = _bars(start="2026-06-01", days=10)          # ends 2026-06-10
    monkeypatch.setattr(bc, "load_cached", lambda t: stale)
    fresh = _bars()
    monkeypatch.setattr(data, "get_daily_data", lambda t, **k: fresh)

    assert journal.bars_for_journal(_trade()) is fresh


def test_a_cache_read_failure_never_breaks_the_close(monkeypatch):
    import swingbot.core.backtest_cache as bc
    import swingbot.core.data as data
    monkeypatch.setattr(bc, "load_cached", lambda t: (_ for _ in ()).throw(OSError("disk")))
    fresh = _bars()
    monkeypatch.setattr(data, "get_daily_data", lambda t, **k: fresh)

    assert journal.bars_for_journal(_trade()) is fresh


def test_both_sources_failing_degrades_to_none_not_an_exception(monkeypatch):
    """Bookkeeping must never be able to un-close a trade."""
    import swingbot.core.backtest_cache as bc
    import swingbot.core.data as data
    monkeypatch.setattr(bc, "load_cached", lambda t: None)
    monkeypatch.setattr(data, "get_daily_data",
                        lambda t, **k: (_ for _ in ()).throw(RuntimeError("yfinance down")))

    assert journal.bars_for_journal(_trade()) is None


def test_journal_trade_close_itself_goes_through_the_cache(monkeypatch, tmp_path):
    """The wiring test. A helper that nothing calls is this repo's most
    common failure shape (known-traps.md), so drive the REAL close path and
    prove the live fetch is not reached and the entry still gets its MFE."""
    import swingbot.core.backtest_cache as bc
    import swingbot.core.data as data
    monkeypatch.setattr(bc, "load_cached", lambda t: _bars())
    monkeypatch.setattr(data, "get_daily_data",
                        lambda *a, **k: pytest.fail("journal_trade_close reached live yfinance"))

    store = journal.JournalStore(path=str(tmp_path / "journal.json"))
    monkeypatch.setattr(journal, "JournalStore", lambda *a, **k: store)

    journal.journal_trade_close(_trade())

    entry = store.get("t1")
    assert entry is not None
    assert entry["mfe_r"] == pytest.approx(2.0)


# --- Step 2: the corruption tripwire ---------------------------------------

def test_a_normal_excursion_is_recorded_untouched():
    out = compute_mfe_mae(_trade(), _bars())
    assert out is not None
    assert out["mfe_r"] == pytest.approx(2.0)      # (110-100)/5
    assert out["mae_r"] == pytest.approx(1.0)      # (100-95)/5


def test_an_absurd_excursion_degrades_to_none(caplog):
    """The live failure: a glitched snapshot wrote mfe_r = -1845.95 as a plain
    number, so every average that touched it moved and nothing could tell."""
    caplog.set_level("WARNING")
    glitched = _bars(high=100_000.0)
    assert compute_mfe_mae(_trade(), glitched) is None
    assert "bars are almost certainly wrong" in caplog.text


def test_the_ceiling_is_generous_enough_to_keep_real_outliers():
    """A tripwire, not a plausibility filter -- a genuine 20R run is real
    data and must survive."""
    twenty_r = _bars(high=200.0)                   # (200-100)/5 = 20R
    out = compute_mfe_mae(_trade(), twenty_r)
    assert out is not None and out["mfe_r"] == pytest.approx(20.0)
    assert 20.0 < MAX_PLAUSIBLE_R


def test_exit_efficiency_never_derives_from_rejected_bars():
    """The check runs before exit_efficiency is computed, so a bad denominator
    can't leak through a field the ceiling didn't look at."""
    assert compute_mfe_mae(_trade(), _bars(high=100_000.0)) is None
