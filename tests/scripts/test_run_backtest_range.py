"""run_backtest_range.py's pooled per-strategy max-DD helper (Task E22)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_backtest_range as rbr  # noqa: E402


def _trade(entry_date, r_multiple):
    return SimpleNamespace(entry_date=entry_date, r_multiple=r_multiple)


def test_pooled_max_dd_pct_golden():
    # 1% risk per trade, compounding: 1.0 -> 1.01 -> 1.0908 (peak) -> 0.98172
    # dd from peak = (0.98172 - 1.0908) / 1.0908 * 100 = -10.0%
    trades = [
        _trade("2020-01-01", 1.0),
        _trade("2020-01-02", 8.0),
        _trade("2020-01-03", -10.0),
    ]
    dd = rbr.pooled_max_dd_pct(trades, risk_pct=1.0)
    assert dd == pytest.approx(-10.0)


def test_pooled_max_dd_pct_sorts_by_entry_date():
    # Same trades, passed out of order -- result must be order-independent
    # of input list order (sorted internally by entry_date).
    trades = [
        _trade("2020-01-03", -10.0),
        _trade("2020-01-01", 1.0),
        _trade("2020-01-02", 8.0),
    ]
    assert rbr.pooled_max_dd_pct(trades, risk_pct=1.0) == pytest.approx(-10.0)


def test_pooled_max_dd_pct_no_drawdown_is_zero_not_none():
    trades = [_trade("2020-01-01", 1.0), _trade("2020-01-02", 2.0)]
    assert rbr.pooled_max_dd_pct(trades) == 0.0


def test_pooled_max_dd_pct_empty_is_none():
    assert rbr.pooled_max_dd_pct([]) is None


def test_pooled_max_dd_pct_skips_trades_with_no_r_multiple():
    trades = [_trade("2020-01-01", None), _trade("2020-01-02", None)]
    assert rbr.pooled_max_dd_pct(trades) is None


def test_tickers_for_run_uses_named_universe(monkeypatch):
    import swingbot.core.universe as universe

    def boom():
        raise AssertionError("load_watchlist should not be called when a universe is given")

    monkeypatch.setattr(rbr, "load_watchlist", boom)
    monkeypatch.setattr(universe, "universe_symbols", lambda name: ["QQQ", "SPY"])
    assert rbr._tickers_for_run("etfs") == ["QQQ", "SPY"]


def test_tickers_for_run_defaults_to_watchlist(monkeypatch):
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["ZZZ", "AAA"])
    assert rbr._tickers_for_run(None) == ["AAA", "ZZZ"]


# --- V49: the acceptance gate and the evidence-inflation warning -------------

def _stats(n_eval, win_rate, expectancy_r, excluded_share=0.0, wins=None):
    return {"n_eval": n_eval, "win_rate": win_rate, "expectancy_r": expectancy_r,
            "excluded_share": excluded_share,
            "wins": wins if wins is not None else round((win_rate or 0) / 100 * n_eval)}


def test_passes_does_not_gate_on_win_rate():
    """Plan v8 V6 Step 3 voided `win_rate >= 80`: it is the ranking objective,
    not a threshold. V16 measured a ~78% ceiling, so gating on 80 rejected
    everything -- including configs the plan's own rule accepts."""
    assert rbr.passes(_stats(100, 66.0, +0.05), min_n=15) is True
    assert rbr.passes(_stats(100, 20.0, +0.05), min_n=15) is True


def test_passes_still_enforces_the_criteria_v6_kept():
    assert rbr.passes(_stats(100, 95.0, -0.01), min_n=15) is False       # expectancy
    assert rbr.passes(_stats(10, 95.0, +0.05), min_n=15) is False        # sample size
    assert rbr.passes(_stats(100, 95.0, +0.05, 0.75), min_n=15) is False  # dead share


def test_wilson_lower_bound_punishes_small_samples():
    """The bound is the whole point of V6 Step 5: the same win rate on a
    tenth of the sample must not read as the same evidence."""
    big = rbr.wilson_lower_bound(80, 100)
    small = rbr.wilson_lower_bound(8, 10)
    assert big == pytest.approx(70.8, abs=0.5)
    assert small == pytest.approx(49.0, abs=1.0)
    assert small < big
    assert rbr.wilson_lower_bound(0, 0) is None


def test_wilson_str_derives_wins_when_absent():
    """Scenario rows carry win_rate but not `wins`; both paths must agree."""
    with_wins = rbr._wilson_str({"n_eval": 100, "win_rate": 80.0, "wins": 80})
    derived = rbr._wilson_str({"n_eval": 100, "win_rate": 80.0})
    assert with_wins == derived
    assert rbr._wilson_str({"n_eval": 0, "win_rate": None}) == "n/a"
