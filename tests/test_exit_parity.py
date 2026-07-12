from pathlib import Path
import pandas as pd
import pytest

from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.plan_engine import TradePlanV2, PlanStatus, simulate_exit
from swingbot.core.strategy_types import HORIZONS

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "backtest_cache"
SAMPLE_TICKERS = ["AAPL", "MSFT", "TSLA"]
HORIZON_KEYS = ["4w", "3m"]

pytestmark = pytest.mark.skipif(not CACHE_DIR.is_dir(),
                                reason="no OHLCV cache present")

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
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
    )

@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
@pytest.mark.parametrize("ticker", SAMPLE_TICKERS)
def test_exit_parity(ticker, strategy, horizon_key):
    path = CACHE_DIR / f"{ticker}.csv"
    if not path.exists():
        pytest.skip(f"{ticker}.csv missing")
    df = pd.read_csv(path, index_col="Date", parse_dates=True)

    summary = run_backtest(ticker, df, strategy, horizon_key)
    if not summary.trades:
        pytest.skip("no trades")

    date_to_idx = {str(d.date()): i for i, d in enumerate(df.index)}
    for t in summary.trades:
        i = date_to_idx[t.entry_date]
        plan = _plan_from_backtest_trade(t, ticker, strategy, horizon_key)
        res = simulate_exit(df, i, plan, scale_out=False)
        assert res.outcome == t.outcome, (
            f"{ticker}/{strategy}/{horizon_key} {t.entry_date}: "
            f"outcome {res.outcome} != legacy {t.outcome}")
        assert str(df.index[res.exit_index].date()) == t.exit_date
        # legacy r_multiple is rounded to 3dp in BacktestTrade
        assert res.r_total == pytest.approx(t.r_multiple, abs=5e-4)
