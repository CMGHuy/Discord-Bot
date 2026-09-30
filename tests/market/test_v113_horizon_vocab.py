"""v113: no swingbot/ code iterates HORIZONS (which now holds masked 1w)."""
import numpy as np

from swingbot.core.market import strategy_types as st
from tests.helpers import make_ohlcv
from tests.horizon_iteration import ROOT, offenders

# Deliberate: an ORDER map (1w first is harmless), the MTF ladder (1w sits below
# 2w and never becomes anyone's "next horizon up"), and an analytics filter's
# accepted values (a real 1w trade must be filterable once one exists).
ALLOWED = {
    ("swingbot/admin/api_v1/analytics.py", "order = {h: i for i, h in enumerate(HORIZONS)}"),
    ("swingbot/core/market/mtf.py", "_LADDER = list(HORIZONS.keys())"),
    ("swingbot/core/analytics/scope.py", 'horizon=_choice(args, "horizon", tuple(HORIZONS), None),'),
}


def _package_files():
    files = sorted((ROOT / "swingbot").rglob("*.py")) + [ROOT / "bot.py", ROOT / "admin_ui.py"]
    return [f for f in files if f.name != "strategy_types.py"]


def test_no_swingbot_code_iterates_horizons():
    assert offenders(_package_files(), ALLOWED) == []


def test_slash_horizon_choices_are_the_live_vocabulary():
    from swingbot.commands import slash
    assert [choice.value for choice in slash.HORIZON_CHOICES] == [*st.LEGACY_HORIZONS, "all"]


def test_evaluate_all_never_reports_1w():
    from swingbot.core.market.strategy import evaluate_all
    rng = np.random.default_rng(7)
    df = make_ohlcv(100 * np.cumprod(1 + rng.normal(0.0005, 0.015, 420)))
    assert "1w" not in {result.horizon_key for result in evaluate_all("X", df)}


def test_run_full_backtest_walks_the_live_vocabulary(monkeypatch):
    from swingbot.core.backtesting import backtest
    seen = []
    monkeypatch.setattr(backtest, "run_backtest",
                        lambda ticker, df, strategy, horizon, frictions=True: seen.append(horizon))
    backtest.run_full_backtest("X", None)
    assert sorted(set(seen)) == sorted(st.LEGACY_HORIZONS)


def test_arm_producer_vocabulary_stays_legacy():
    from swingbot.core.backtesting.arms import windows
    assert windows.ALL_HORIZONS == st.LEGACY_HORIZONS
