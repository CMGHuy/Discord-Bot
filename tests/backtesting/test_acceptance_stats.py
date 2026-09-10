"""Win rate is over win+loss only; expectancy is over all CLOSED trades
(scratches and timeouts included, not_triggered excluded). That split is
the methodology doc's, and measure_dcb_veto._aggregate already obeys it.
"""
from swingbot.core.backtesting.acceptance import (
    ArmTrade, expectancy_r, standardised_win_rate, stratum_table,
    stratum_weights, win_rate,
)


def mk(strategy, horizon, outcome, r=0.0, ticker="AAPL", date="2021-01-01"):
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon,
                    entry_date=date, outcome=outcome, r_multiple=r,
                    planned_rr=2.0)


def test_win_rate_ignores_scratches_and_timeouts():
    trades = [mk("MACD", "3m", "win"), mk("MACD", "3m", "loss"),
              mk("MACD", "3m", "scratch"), mk("MACD", "3m", "timeout")]
    assert win_rate(trades) == 50.0


def test_win_rate_is_none_with_no_decided_trades():
    assert win_rate([mk("MACD", "3m", "scratch")]) is None


def test_expectancy_includes_scratches_and_timeouts():
    trades = [mk("MACD", "3m", "win", r=2.0), mk("MACD", "3m", "loss", r=-1.0),
              mk("MACD", "3m", "scratch", r=0.0)]
    assert abs(expectancy_r(trades) - (1.0 / 3.0)) < 1e-12


def test_expectancy_excludes_not_triggered():
    trades = [mk("MACD", "3m", "win", r=2.0),
              mk("MACD", "3m", "not_triggered", r=None)]
    assert expectancy_r(trades) == 2.0


def test_stratum_weights_sum_to_one_over_decided_trades():
    trades = [mk("MACD", "3m", "win"), mk("MACD", "3m", "loss"),
              mk("RSI", "4w", "win"), mk("RSI", "4w", "scratch")]
    w = stratum_weights(trades)
    assert abs(sum(w.values()) - 1.0) < 1e-12
    # RSI/4w has ONE decided trade (the scratch does not count)
    assert abs(w[("RSI", "4w")] - 1 / 3) < 1e-12


def test_mix_shift_alone_produces_zero_standardised_delta():
    """THE regression test for finding 7.

    Baseline: a strong stratum at 80% WR and a weak one at 20%, equally
    sized. The 'feature' removes half the weak stratum and nothing else --
    no within-stratum outcome changes at all. Raw win rate jumps; the
    standardised one must not move, because nothing actually improved.
    """
    strong = [mk("MACD", "3m", "win") for _ in range(8)] + \
             [mk("MACD", "3m", "loss") for _ in range(2)]
    # Interleaved 1-in-5 so ANY prefix of `weak` is still 20% -- otherwise
    # the slice below would change the stratum's own win rate and the test
    # would be measuring two things at once.
    weak = ([mk("RSI", "4w", "win")] + [mk("RSI", "4w", "loss")] * 4) * 2
    baseline = strong + weak
    component = strong + weak[:5]      # drops 5 of the weak stratum's 10

    weights = stratum_weights(baseline)
    raw_delta = win_rate(component) - win_rate(baseline)
    std_delta = (standardised_win_rate(component, weights)
                 - standardised_win_rate(baseline, weights))

    assert raw_delta > 5.0             # materially non-zero
    assert abs(std_delta) < 1e-9       # and entirely an artifact


def test_real_within_stratum_improvement_survives_standardisation():
    """The mirror case: the feature removes only LOSERS from one stratum.
    That is genuine discrimination and must show up standardised."""
    baseline = [mk("MACD", "3m", "win") for _ in range(5)] + \
               [mk("MACD", "3m", "loss") for _ in range(5)]
    component = [mk("MACD", "3m", "win") for _ in range(5)] + \
                [mk("MACD", "3m", "loss") for _ in range(2)]
    weights = stratum_weights(baseline)
    std_delta = (standardised_win_rate(component, weights)
                 - standardised_win_rate(baseline, weights))
    assert std_delta > 10.0


def test_stratum_table_reports_both_arms_per_stratum():
    baseline = [mk("MACD", "3m", "win"), mk("MACD", "3m", "loss"),
                mk("RSI", "4w", "loss")]
    component = [mk("MACD", "3m", "win")]
    rows = stratum_table(baseline, component)
    by = {r["stratum"]: r for r in rows}
    assert by[("MACD", "3m")]["baseline_n"] == 2
    assert by[("MACD", "3m")]["component_n"] == 1
    assert by[("MACD", "3m")]["component_win_rate"] == 100.0
    # A stratum the component emptied still appears, with None, not a gap.
    assert by[("RSI", "4w")]["component_n"] == 0
    assert by[("RSI", "4w")]["component_win_rate"] is None
