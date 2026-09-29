import pytest

from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.planning.plan_engine import TradePlanV2, PlanStatus, simulate_exit

from tests.fixtures.ohlcv_parity import PARITY_CASES, load_ohlcv

def _plan_from_backtest_trade(t, ticker, strategy, horizon_key):
    """Market-entry plan with the legacy trade's exact numbers, so
    simulate_exit re-walks the identical exit problem."""
    return TradePlanV2(
        plan_id="parity", ticker=ticker, created_at=t.entry_date,
        source="strategy", strategy=strategy, horizon_key=horizon_key,
        direction=t.direction, entry_type="market", trigger_price=t.entry,
        entry_price=t.entry, expiry_bars=5, stop_loss=t.stop_loss,
        tp1=t.take_profit, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
    )

@pytest.mark.parametrize(("ticker", "strategy", "horizon_key"), PARITY_CASES)
def test_exit_parity(ticker, strategy, horizon_key):
    df = load_ohlcv(ticker)

    # frictions=False: this test re-walks the legacy v1 trade through the v2
    # exit simulator and expects near-identical outcome/exit-bar/r_total --
    # a Task E11 friction haircut on the v1 side would move the fed-in entry
    # price and r_multiple away from what simulate_exit (unmodified, no
    # frictions concept) computes, which is unrelated to this test's purpose.
    summary = run_backtest(ticker, df, strategy, horizon_key, frictions=False)
    assert summary.trades, (
        f"{ticker}/{strategy}/{horizon_key} no longer trades on the fixture; "
        "swap in another ticker in tests/fixtures/ohlcv_parity.py")

    date_to_idx = {str(d.date()): i for i, d in enumerate(df.index)}
    for t in summary.trades:
        i = date_to_idx[t.entry_date]
        plan = _plan_from_backtest_trade(t, ticker, strategy, horizon_key)
        res = simulate_exit(df, i, plan, scale_out=False)
        assert res.outcome == t.outcome, (
            f"{ticker}/{strategy}/{horizon_key} {t.entry_date}: "
            f"outcome {res.outcome} != legacy {t.outcome}")
        assert str(df.index[res.exit_index].date()) == t.exit_date
        # Legacy r_multiple is rounded to 3dp in BacktestTrade. Outcome and
        # exit bar are asserted exactly above; r_total may differ in the 3rd
        # decimal on deep-history sub-dollar (split-adjusted) prices where the
        # two paths' intermediate rounding diverges -- a relative tolerance
        # absorbs that penny-price noise without masking a classification or
        # timing divergence.
        assert res.r_total == pytest.approx(t.r_multiple, rel=2e-2, abs=2e-3)
