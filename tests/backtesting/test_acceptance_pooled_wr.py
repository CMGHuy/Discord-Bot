"""v180 A1 (the v119 A1-A4 amendment, adopted verbatim): the pooled, unstandardised dWR.
The standardised dWR weights strata by the BASELINE's mix, so a strategy the baseline lacks
is weightless and dWR is exactly 0 for any additive arm."""
import pytest

from swingbot.core.backtesting.acceptance import (WR_STATISTICS, ArmTrade, delta_pooled_win_rate,
                                                  delta_standardised_win_rate, evaluate,
                                                  render_json, win_rate_statistic)


def _trade(ticker, strategy, horizon, day, outcome):
    r = {"win": 2.0, "loss": -1.0}.get(outcome, 0.0)
    return ArmTrade(ticker, strategy, horizon, f"2022-{1 + day // 28:02d}-{1 + day % 28:02d}",
                    outcome, r, 2.0, "strategy", "bullish")


def _arms(n_tickers=40, lift=4):
    """Baseline: 10 MACD/3m trades per ticker, 2 + t % 5 wins (pooled 40% when n_tickers is a
    multiple of 5). Component: the same rows plus 10 Turtle Soup/2w trades per ticker with
    2 + (3t) % 5 + lift wins (pooled 40% + 10 * lift pp). Tickers differ, so the bootstrap has spread."""
    baseline, added = [], []
    for t in range(n_tickers):
        base_wins, added_wins = 2 + t % 5, min(10, 2 + (3 * t) % 5 + lift)
        for i in range(10):
            baseline.append(_trade(f"T{t}", "MACD", "3m", i, "win" if i < base_wins else "loss"))
            added.append(_trade(f"T{t}", "Turtle Soup", "2w", 40 + i,
                                "win" if i < added_wins else "loss"))
    return baseline, baseline + added


def test_the_standardised_statistic_is_blind_to_an_added_strategy():
    baseline, component = _arms()
    assert delta_standardised_win_rate(baseline, component) == pytest.approx(0.0)
    assert delta_pooled_win_rate(baseline, component) == pytest.approx(20.0)   # 40% -> 60%


def test_pooled_counts_decided_trades_only():
    baseline, component = _arms(n_tickers=5, lift=0)                          # 40% -> 40%
    undecided = [_trade("T0", "Turtle Soup", "2w", 80, "timeout"),
                 _trade("T0", "Turtle Soup", "2w", 81, "scratch")]
    assert delta_pooled_win_rate(baseline, component + undecided) == pytest.approx(0.0)


def test_pooled_is_none_when_an_arm_decides_nothing():
    baseline, component = _arms(n_tickers=5)
    undecided = [_trade("T0", "MACD", "3m", 0, "timeout")]
    assert delta_pooled_win_rate(undecided, component) is None
    assert delta_pooled_win_rate(baseline, undecided) is None


def test_statistics_are_name_keyed():
    assert WR_STATISTICS == {"standardised": delta_standardised_win_rate,
                             "pooled": delta_pooled_win_rate}
    assert win_rate_statistic("pooled") is delta_pooled_win_rate
    with pytest.raises(ValueError, match="standardised"):
        win_rate_statistic("mixed")


def test_evaluate_defaults_to_the_standardised_statistic_unchanged():
    baseline, component = _arms()
    result = evaluate(baseline, component, stage="walkforward", n_resamples=200)
    assert result.wr_statistic == "standardised"
    assert result.clause("win_rate").detail.startswith("standardised dWR")
    assert result.clause("win_rate").verdict == "FAIL"          # blind: the point is 0.0
    assert "wr_statistic" not in render_json(result)


def test_evaluate_pooled_sees_the_added_strategy():
    baseline, component = _arms()
    result = evaluate(baseline, component, stage="walkforward", n_resamples=200,
                      wr_statistic="pooled")
    clause = result.clause("win_rate")
    assert clause.verdict == "PASS" and clause.value == pytest.approx(20.0)
    assert clause.detail.startswith("pooled dWR")
    assert result.wr_statistic == "pooled"
    assert render_json(result)["wr_statistic"] == "pooled"


def test_pooled_changes_clause_one_only():
    """A4: thresholds, the bootstrap and clauses 2-6 do not depend on the statistic."""
    baseline, component = _arms()
    common = dict(stage="validation", permutation_p=0.01, n_resamples=200)
    std = evaluate(baseline, component, **common)
    pooled = evaluate(baseline, component, wr_statistic="pooled", **common)
    assert ([c for c in std.clauses if c.name != "win_rate"]
            == [c for c in pooled.clauses if c.name != "win_rate"])
    assert (std.strata, std.split, std.seed, std.cluster) == (pooled.strata, pooled.split,
                                                              pooled.seed, pooled.cluster)
    assert pooled.clause("mechanism").verdict == "SKIPPED"


def test_an_unknown_statistic_is_refused_before_any_work():
    baseline, component = _arms(n_tickers=5)
    with pytest.raises(ValueError, match="standardised"):
        evaluate(baseline, component, stage="walkforward", n_resamples=50, wr_statistic="mixed")
