"""V180-5: Turtle Soup fills at the next open. An open at or below the stop cancels, a stop
farther than the 3% ceiling from the fill drops the plan, and one whole-position leg walks
from the fill bar with gap fills and a ten-session cap (fill = session 1)."""
import pytest

from swingbot.core.market.strategy_types import COMPRESSION_SHORT, HORIZONS, TURTLE_SOUP
from swingbot.core.planning import exit_sim
from swingbot.core.planning import next_open_entry as noe
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.time_exit import PROXY_BASIS, TIME_EXIT_REASON
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

SIGNAL = 30
FLAT = (100.0, 100.5, 99.5, 100.0)      # open, high, low, close: never reaches 98 or 104


def _bars(overrides=None, n=60):
    rows = [FLAT] * n
    for i, row in (overrides or {}).items():
        rows[i] = row
    return make_ohlcv(rows, start="2024-01-02")


def _ts(**kw):
    shape = PLAN_SHAPES[TURTLE_SOUP]
    base = dict(strategy=TURTLE_SOUP, horizon_key="2w", direction="bullish",
                entry_type=shape["entry_type"], expiry_bars=shape["expiry_bars"],
                tp1_fraction=shape["tp1_fraction"],
                breakeven_trigger_fraction=shape["breakeven_trigger_fraction"],
                hold_cap_bars=shape["hold_cap_bars"], trigger_price=100.0,
                stop_loss=98.0, tp1=104.0, tp2=None)
    base.update(kw)
    return _plan(**base)


def _run(df, plan=None):
    return simulate_exit(df, SIGNAL, plan or _ts(), scale_out=True)


def test_turtle_soup_is_the_only_next_open_strategy():
    assert noe.NEXT_OPEN_STRATEGIES == frozenset({TURTLE_SOUP})
    assert noe.uses_next_open_fill(_ts())
    assert not noe.uses_next_open_fill(_plan())          # a Fibonacci market plan


def test_fills_at_the_next_open_not_the_signal_close():
    result = _run(_bars({SIGNAL + 1: (100.2, 100.6, 99.8, 100.3)}))
    assert result.entry_index == SIGNAL + 1 and result.entry_price == 100.2


def test_other_market_plans_still_fill_at_the_signal_close():
    result = simulate_exit(_bars(), SIGNAL, _plan(), scale_out=True)
    assert result.entry_index == SIGNAL and result.entry_price == 100.0


@pytest.mark.parametrize("bar_open", [98.0, 97.0])
def test_an_open_at_or_below_the_stop_cancels(bar_open):
    result = _run(_bars({SIGNAL + 1: (bar_open, 99.0, bar_open - 0.5, 98.5)}))
    assert result.outcome == "not_triggered"
    assert result.cancel_reason == noe.OPEN_THROUGH_STOP == "open_through_stop"
    assert result.legs == [] and result.entry_index is None


def test_a_stop_beyond_three_percent_of_the_fill_is_dropped():
    # (101.5 - 98) / 101.5 = 3.45% > the 2w ceiling of 3.0%
    result = _run(_bars({SIGNAL + 1: (101.5, 101.8, 101.0, 101.4)}))
    assert result.outcome == "not_triggered"
    assert result.cancel_reason == noe.RISK_CAP == "risk_cap"


def test_a_stop_inside_the_ceiling_fills_and_is_never_moved():
    # (100.9 - 98) / 100.9 = 2.87%: fills; the stop the walk honours is still 98
    df = _bars({SIGNAL + 1: (100.9, 101.0, 100.5, 100.8),
                SIGNAL + 3: (99.0, 99.2, 97.9, 98.5)})
    result = _run(df)
    assert result.entry_price == 100.9
    assert result.outcome == "loss" and result.r_total == -1.0
    assert result.legs[0]["exit_price"] == 98.0 and result.legs[0]["reason"] == "stop"


def test_a_gap_through_the_stop_fills_at_the_open():
    result = _run(_bars({SIGNAL + 3: (97.0, 97.5, 96.5, 97.2)}))
    assert result.outcome == "loss" and result.exit_index == SIGNAL + 3
    assert result.legs[0] == {"fraction": 1.0, "exit_price": 97.0, "r": -1.5,
                              "reason": noe.GAP_STOP_REASON}
    assert result.r_total == -1.5


def test_a_gap_through_the_target_fills_at_the_better_open():
    result = _run(_bars({SIGNAL + 3: (105.0, 105.5, 104.6, 105.2)}))
    assert result.outcome == "win" and result.r_total == 2.5
    assert result.legs[0]["exit_price"] == 105.0
    assert result.legs[0]["reason"] == noe.GAP_TARGET_REASON == "gap_target"


def test_an_open_through_the_target_on_the_fill_bar_is_a_scratch():
    # stop 99, target 101; the fill opens at 101.2 (2.17% risk): out at the fill, 0R gross
    plan = _ts(stop_loss=99.0, tp1=101.0)
    result = _run(_bars({SIGNAL + 1: (101.2, 101.5, 100.9, 101.3)}), plan)
    assert result.outcome == "scratch" and result.r_total == 0.0
    assert result.entry_index == result.exit_index == SIGNAL + 1
    assert result.legs[0]["reason"] == "gap_target"


def test_the_fill_bar_is_walked_stop_before_target():
    result = _run(_bars({SIGNAL + 1: (100.0, 104.5, 97.5, 103.0)}))
    assert result.outcome == "loss" and result.r_total == -1.0
    assert result.exit_index == SIGNAL + 1 and result.legs[0]["reason"] == "stop"


def test_an_intraday_target_touch_is_a_win_at_the_target():
    result = _run(_bars({SIGNAL + 4: (100.0, 104.2, 99.8, 104.0)}))
    assert result.outcome == "win" and result.exit_index == SIGNAL + 4
    assert result.legs[0]["exit_price"] == 104.0 and result.legs[0]["reason"] == "tp1"
    assert result.r_total == 2.0


def test_the_hold_cap_closes_the_tenth_session_counting_the_fill():
    result = _run(_bars())
    assert result.outcome == "timeout"
    assert result.exit_index == result.entry_index + 9 == SIGNAL + 10     # the screen's t+10 close
    leg = result.legs[0]
    assert leg["reason"] == TIME_EXIT_REASON and leg["price_basis"] == PROXY_BASIS
    assert result.r_total == 0.0


def test_a_walk_cut_short_by_the_data_is_a_plain_timeout():
    df = _bars(n=SIGNAL + 5)
    result = _run(df)
    assert result.outcome == "timeout" and result.exit_index == len(df) - 1
    assert result.legs[0]["reason"] == "timeout" and "price_basis" not in result.legs[0]


def test_a_signal_on_the_last_bar_never_fills():
    result = _run(_bars(n=SIGNAL + 1))
    assert result.outcome == "not_triggered" and result.cancel_reason is None


def test_the_v129_acceptance_exit_closes_at_the_bar_close():
    plan = _ts(acceptance_close_below=99.0)
    result = _run(_bars({SIGNAL + 3: (99.5, 99.8, 98.6, 98.8)}), plan)
    assert result.outcome == "loss" and result.exit_index == SIGNAL + 3
    assert result.legs[0]["reason"] == "acceptance_exit" and result.r_total == -0.6


def test_a_bearish_plan_is_refused():
    with pytest.raises(ValueError):
        noe.next_open_exit(_bars(), SIGNAL, _ts(direction="bearish", stop_loss=102.0, tp1=96.0), 9)


def test_hold_cap_counts_the_fill_session_for_both_session_one_strategies():
    assert exit_sim.SESSION_ONE_HOLD_CAP == frozenset({COMPRESSION_SHORT, TURTLE_SOUP})
    assert exit_sim._hold_cap_bars(_ts(), 14) == 9
    compression = _plan(strategy=COMPRESSION_SHORT, horizon_key="2w", hold_cap_bars=10)
    assert exit_sim._hold_cap_bars(compression, 14) == 9
    assert exit_sim._hold_cap_bars(_plan(hold_cap_bars=10), 14) == 10
    assert exit_sim._hold_cap_bars(_ts(), 5) == 5


def test_the_two_week_horizon_admits_the_ten_session_hold():
    assert HORIZONS["2w"]["max_holding_days"] >= PLAN_SHAPES[TURTLE_SOUP]["hold_cap_bars"]
