from tests.conftest import make_ohlcv
from swingbot.core.analytics.mfe_mae import compute_mfe_mae


def test_bullish_mfe_mae_and_exit_efficiency():
    # Flat bars (spread_pct=0.0) so High == Low == Close on every bar --
    # lets us place the swing high (108) and swing low (98) on separate
    # bars using only make_ohlcv's real (closes, spread_pct) signature.
    # Bars: 2026-03-02..03-05 (bdate_range skips the weekend that would
    # otherwise fall in this run).
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00",
         "status": "win"}
    m = compute_mfe_mae(t, df)
    assert m["mfe_r"] == 2.0            # (108-100)/4
    assert m["mae_r"] == 0.5            # (100-98)/4
    assert m["exit_efficiency"] == 0.5  # realized r=1.0 of a 2.0R max move


def test_bearish_mirror():
    df = make_ohlcv([100, 92, 102, 96], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bearish", "entry": 100.0, "stop_loss": 104.0, "exit_price": 96.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00",
         "status": "win"}
    m = compute_mfe_mae(t, df)
    assert m["mfe_r"] == 2.0            # (100-92)/4
    assert m["mae_r"] == 0.5            # (102-100)/4
    assert m["exit_efficiency"] == 0.5


def test_zero_risk_returns_none():
    df = make_ohlcv([100, 100], start="2026-03-02")
    t = {"entry": 100, "stop_loss": 100, "direction": "bullish",
         "opened_at": "2026-03-02T00:00:00+00:00", "closed_at": "2026-03-03T00:00:00+00:00"}
    assert compute_mfe_mae(t, df) is None


def test_missing_dates_or_empty_df_returns_none():
    from swingbot.core.analytics.mfe_mae import compute_mfe_mae as f
    df = make_ohlcv([100, 101], start="2026-03-02")
    t = {"entry": 100.0, "stop_loss": 96.0, "direction": "bullish"}  # no opened_at/closed_at
    assert f(t, df) is None
    assert f(dict(t, opened_at="2026-03-02T00:00:00+00:00",
                  closed_at="2026-03-03T00:00:00+00:00"), None) is None


def test_same_day_trade_with_nonmidnight_times():
    """Regression test for Bug #1: same-day trades with non-midnight times.
    Before the fix, the entry-day bar (indexed at midnight) would be excluded
    because the comparison would be 2026-03-02 00:00:00 >= 2026-03-02 15:00:00,
    which is False. This caused same-day trades to spuriously return None.

    With spread_pct=1.0, the bar has High/Low ±0.5% around the close, giving
    us measurable favorable/adverse movement on the single day."""
    df = make_ohlcv([100], spread_pct=1.0, start="2026-03-02")
    # For close=100, spread_pct=1.0: High=100.5, Low=99.5
    t = {
        "direction": "bullish",
        "entry": 100.0,
        "stop_loss": 99.0,
        "exit_price": 100.5,
        "opened_at": "2026-03-02T15:00:00+00:00",
        "closed_at": "2026-03-02T18:00:00+00:00",  # same day as opened_at
        "status": "win",
    }
    m = compute_mfe_mae(t, df)
    # After the fix, this should return a real result instead of None
    assert m is not None
    risk = 100.0 - 99.0  # 1.0
    assert m["mfe_r"] == 0.5  # (100.5 - 100) / 1.0
    assert m["mae_r"] == 0.5  # (100 - 99.5) / 1.0


def test_entry_day_bar_contains_price_extreme():
    """Regression test for Bug #1: entry-day bar contains the trade's real extreme.
    Create a scenario where the entry-day bar holds the trade's maximum (for bullish)
    or minimum (for bearish). Before the fix, the entry-day bar would be excluded
    from the slice, causing mfe_r to be understated."""
    # Bars: [100 (entry), 99, 101]
    # Trade opens at bar 1 (100), closes at bar 3 (101)
    # The real max is 101 on the close day, but the entry day itself is 100
    df = make_ohlcv([100, 99, 101], spread_pct=0.0, start="2026-03-02")
    t = {
        "direction": "bullish",
        "entry": 100.0,
        "stop_loss": 96.0,
        "exit_price": 101.0,
        "opened_at": "2026-03-02T10:00:00+00:00",
        "closed_at": "2026-03-04T14:00:00+00:00",
        "status": "win",
    }
    m = compute_mfe_mae(t, df)
    # After the fix, mfe_r should correctly reflect the maximum encountered
    assert m is not None
    # Max high across bars is 101, entry is 100, risk is 4
    assert m["mfe_r"] == 0.25  # (101-100)/4
    # Min low across bars is 99, entry is 100, risk is 4
    assert m["mae_r"] == 0.25  # (100-99)/4
