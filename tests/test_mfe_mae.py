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
