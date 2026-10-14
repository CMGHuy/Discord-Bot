"""v147 V147-2: simulate_blocked core -- signal bar, price basis, walk, status."""
import pytest

from swingbot.core.backtesting import gate_counterfactual as gc
from swingbot.core.planning.exit_sim import _not_triggered, _no_trade
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from tests.helpers import make_ohlcv

FLAT = (100.2, 100.6, 99.8, 100.3)          # no stop, no BE trigger, no TP1
SIGNAL = 2                                  # positional index of the signal bar


def _plan(**kw) -> dict:
    base = dict(plan_id="p1", ticker="AAPL", created_at="2024-01-04", source="confluence",
                strategy="Fibonacci", horizon_key="2w", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=102.0,
                tp1_fraction=0.5, tp2=105.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


def _candidate(plan=None, **kw) -> gc.BlockedCandidate:
    base = dict(ticker="AAPL", gate="plan_rejected", reason="risk_cap", source="confluence",
                strategy="Fibonacci", horizon="2w", direction="bullish",
                signal_date="2024-01-04", plan=plan)
    base.update(kw)
    return gc.BlockedCandidate(**base)


def _frame(after, *, n_after=20, scale=1.0):
    """Two warm-up bars, the signal bar (close 100), `after`, then FLAT bars."""
    rows = [(100.0, 100.5, 99.5, 100.0)] * 3 + list(after)
    rows += [FLAT] * max(0, n_after - len(after))
    rows = [tuple(x * scale for x in r) for r in rows]
    return make_ohlcv(rows, start="2024-01-02")       # 2024-01-04 is index 2


def _replay_r(frame, plan_dict):
    return simulate_exit(frame, SIGNAL, plan_from_dict(plan_dict), scale_out=True)


def test_statuses_are_frozen():
    assert gc.CF_STATUSES == ("pending", "filled", "no-fill", "no-plan", "no-data")
    assert gc.REANCHOR_TOLERANCE == 0.005


def test_win_is_tp1_touched_and_matches_the_replay_call():
    plan = _plan()
    frame = _frame([(100.5, 103.0, 100.4, 102.5)])
    res = gc.simulate_blocked(_candidate(plan), frame)
    assert res.cf_status == "filled" and res.win is True and res.cf_r > 0
    assert res.cf_r == _replay_r(frame, plan).r_total


def test_loss_books_minus_one_r():
    res = gc.simulate_blocked(_candidate(_plan()), _frame([(99.0, 99.5, 94.0, 95.5)]))
    assert (res.cf_status, res.cf_r, res.win) == ("filled", -1.0, False)


def test_gap_through_the_stop_books_the_instruments_stop_fill():
    # exit_sim books a pre-TP1 stop at the stop price, so a gap below it is -1R,
    # not worse; the counterfactual uses the instrument unchanged (both arms alike).
    plan = _plan()
    frame = _frame([(90.0, 91.0, 89.0, 90.0)])
    res = gc.simulate_blocked(_candidate(plan), frame)
    assert res.cf_status == "filled" and res.cf_r == _replay_r(frame, plan).r_total == -1.0


def test_scratch_after_breakeven_move():
    frame = _frame([(100.5, 101.2, 100.1, 101.0), (100.5, 100.6, 99.9, 100.2)])
    res = gc.simulate_blocked(_candidate(_plan()), frame)
    assert (res.cf_status, res.cf_r, res.win) == ("filled", 0.0, False)


def test_timeout_is_filled_and_marked_to_close():
    plan = _plan()
    frame = _frame([])
    res = gc.simulate_blocked(_candidate(plan), frame)
    expected = _replay_r(frame, plan)
    assert expected.outcome == "timeout"
    assert res.cf_status == "filled" and res.win is False and res.cf_r == expected.r_total


def test_no_fill_via_expiry_is_never_a_zero_r_trade():
    plan = _plan(entry_type="stop_entry", trigger_price=103.0, entry_price=None, tp1=108.0)
    res = gc.simulate_blocked(_candidate(plan), _frame([]))
    assert (res.cf_status, res.cf_r, res.win) == ("no-fill", None, None)


def test_no_fill_via_invalidation():
    plan = _plan(entry_type="stop_entry", trigger_price=103.0, entry_price=None, tp1=108.0)
    res = gc.simulate_blocked(_candidate(plan), _frame([(99.0, 99.5, 93.5, 94.0)]))
    assert (res.cf_status, res.cf_r, res.win) == ("no-fill", None, None)


def test_no_plan_when_nothing_to_simulate():
    res = gc.simulate_blocked(_candidate(None, reason="no_qualifying_target"), _frame([]))
    assert (res.cf_status, res.cf_r, res.plan) == ("no-plan", None, None)


def test_zero_risk_plan_is_no_plan():
    res = gc.simulate_blocked(_candidate(_plan(stop_loss=100.0)), _frame([]))
    assert res.cf_status == "no-plan" and res.cf_r is None


def test_result_from_exit_applies_the_one_population_rule():
    assert gc.result_from_exit(_not_triggered()) == ("no-fill", None, None)
    assert gc.result_from_exit(_not_triggered("expired")) == ("no-fill", None, None)
    assert gc.result_from_exit(_no_trade(3, 100.0)) == ("no-plan", None, None)


def test_signal_date_needs_an_exact_bar():
    frame = _frame([])
    assert gc.simulate_blocked(_candidate(_plan(), signal_date="2024-01-06"), frame).cf_status == "no-data"
    assert gc.simulate_blocked(_candidate(_plan()), None).cf_status == "no-data"


def test_bars_after_the_last_session_are_dropped_first():
    frame = _frame([])
    res = gc.simulate_blocked(_candidate(_plan()), frame, last_session="2024-01-03")
    assert res.cf_status == "no-data"


def test_tz_aware_index_matches_on_the_naive_date():
    frame = _frame([(100.5, 103.0, 100.4, 102.5)])
    aware = frame.tz_localize("America/New_York")
    a = gc.simulate_blocked(_candidate(_plan()), frame)
    b = gc.simulate_blocked(_candidate(_plan()), aware)
    assert (a.cf_status, a.cf_r) == (b.cf_status, b.cf_r)


def test_pending_until_the_walk_has_every_bar_then_resolved():
    plan = _plan()
    short = _frame([], n_after=5)
    pending = gc.simulate_blocked(_candidate(plan), short)
    assert pending.cf_status == "pending" and pending.cf_r is None and pending.bars_sha256 is None
    assert pending.last_bar_date == str(short.index[-1].date())
    assert gc.simulate_blocked(_candidate(plan), _frame([])).cf_status == "filled"


def test_appended_bars_after_expiry_change_nothing():
    plan = _plan()
    base = _frame([(100.5, 103.0, 100.4, 102.5)], n_after=20)
    longer = _frame([(100.5, 103.0, 100.4, 102.5)], n_after=60)
    a, b = gc.simulate_blocked(_candidate(plan), base), gc.simulate_blocked(_candidate(plan), longer)
    assert (a.cf_r, a.win, a.exit_index, a.bars_sha256, a.last_bar_date) == \
        (b.cf_r, b.win, b.exit_index, b.bars_sha256, b.last_bar_date)


def test_bars_sha256_is_reproducible_and_content_sensitive():
    frame = _frame([])
    assert gc.bars_sha256(frame) == gc.bars_sha256(frame.copy())
    changed = frame.copy()
    changed.iloc[5, changed.columns.get_loc("Close")] += 0.01
    assert gc.bars_sha256(changed) != gc.bars_sha256(frame)


def test_split_adjusted_cache_reanchors_every_level():
    plan = _plan()
    after = [(100.5, 103.0, 100.4, 102.5)]
    res = gc.simulate_blocked(_candidate(plan, signal_close=100.0), _frame(after, scale=0.5))
    unsplit = gc.simulate_blocked(_candidate(plan, signal_close=100.0), _frame(after))
    assert res.reanchored is True and unsplit.reanchored is False
    assert res.plan["stop_loss"] == pytest.approx(47.5) and res.plan["tp1"] == pytest.approx(51.0)
    assert res.cf_status == unsplit.cf_status == "filled"
    assert res.cf_r == pytest.approx(unsplit.cf_r, abs=1e-3)


def test_drift_under_tolerance_does_not_reanchor():
    res = gc.simulate_blocked(_candidate(_plan(), signal_close=100.3), _frame([]))
    assert res.reanchored is False and res.plan["stop_loss"] == 95.0


def test_walk_is_the_replays_exact_call(monkeypatch):
    seen = {}

    def spy(df, signal_index, plan, **kwargs):
        seen.update(kwargs, signal_index=signal_index)
        return simulate_exit(df, signal_index, plan, **kwargs)

    monkeypatch.setattr(gc, "simulate_exit", spy)
    gc.simulate_blocked(_candidate(_plan()), _frame([]))
    assert seen == {"scale_out": True, "signal_index": SIGNAL}
