"""v147 V147-2: simulate_blocked core -- signal bar, price basis, walk, status."""
import math

import pytest

from swingbot.core.backtesting import gate_counterfactual as gc
from swingbot import config
from swingbot.core.market import levels
from swingbot.core.planning import params as plan_params
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


# --- V147-3: truncated plan build, pinned overrides, no-lookahead ---

REBUILD_SIGNAL = 300


def _sine_frame():
    """Steady uptrend: the RSI ATR-branch plan builds; a 6% confluence target does not qualify."""
    return make_ohlcv([100 + 0.15 * i + 3 * math.sin(i / 4.0) for i in range(340)], start="2021-01-04")


def _pullback_frame():
    """Uptrend, decline, base: the window's resistances give a confluence target."""
    up = [100 + 0.2 * i + 3 * math.sin(i / 4.0) for i in range(240)]
    down = [up[-1] - 0.35 * i + 2 * math.sin(i / 3.0) for i in range(1, 61)]
    base = [down[-1] + 0.3 * math.sin(i / 2.0) for i in range(1, 41)]
    return make_ohlcv(up + down + base, start="2021-01-04")


def _signal_date(frame) -> str:
    return str(frame.index[REBUILD_SIGNAL].date())


def _scenario(price: float) -> dict:
    sc = levels.Scenario(
        direction="bullish", entry=price, market_price=price, stop_loss=price * 0.985,
        stop_sources=["Support/Resistance"], stop_distance_pct=1.5, tight_stop=False,
        atr_floor_pct=1.0, take_profit=price * 1.06, target_distance_pct=6.0,
        target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
        target2_sources=None)
    return gc.scenario_to_dict(sc)


def _confluence(frame, **kw) -> gc.BlockedCandidate:
    price = float(frame["Close"].iloc[REBUILD_SIGNAL])
    base = dict(ticker="T", gate="rs", reason="rs_blocked", source="confluence",
                strategy="Fibonacci", horizon="2w", direction="bullish",
                signal_date=_signal_date(frame), scenario=_scenario(price))
    base.update(kw)
    return gc.BlockedCandidate(**base)


def _strategy(frame, **kw) -> gc.BlockedCandidate:
    base = dict(ticker="T", gate="rs", reason="rs_blocked", source="strategy", strategy="RSI",
                horizon="2w", direction="bullish", signal_date=_signal_date(frame),
                scan_params={"stop_mult": None, "tp2_r": None, "time_stop_days": None,
                             "params": None})
    base.update(kw)
    return gc.BlockedCandidate(**base)


def _same_plan(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k != "plan_id"} == \
        {k: v for k, v in b.items() if k != "plan_id"}


def test_scenario_round_trip():
    d = _scenario(100.0)
    assert gc.scenario_to_dict(gc.scenario_from_dict(d)) == d
    assert gc.scenario_from_dict({**d, "unknown": 1}).entry == 100.0


def test_strategy_rebuild_from_the_truncated_frame_equals_the_full_frame_result():
    full = _sine_frame()
    cand = _strategy(full)
    truncated = gc.build_candidate_plan(cand, full.iloc[:REBUILD_SIGNAL + 1])
    assert truncated is not None
    res = gc.simulate_blocked(cand, full)
    assert res.cf_status == "filled"
    assert _same_plan(res.plan, plan_to_dict(truncated))


def test_confluence_rebuild_from_the_truncated_frame_equals_the_full_frame_result():
    full = _pullback_frame()
    cand = _confluence(full)
    truncated = gc.build_candidate_plan(cand, full.iloc[:REBUILD_SIGNAL + 1])
    assert truncated is not None and truncated.source == "confluence"
    assert truncated.strategy == "Fibonacci"           # the stored primary_strategy_for label
    res = gc.simulate_blocked(cand, full)
    assert res.cf_status in ("filled", "no-fill")
    assert _same_plan(res.plan, plan_to_dict(truncated))


def test_confluence_without_a_qualifying_target_is_no_plan():
    full = _sine_frame()
    assert gc.build_candidate_plan(_confluence(full), full.iloc[:REBUILD_SIGNAL + 1]) is None
    assert gc.simulate_blocked(_confluence(full), full).cf_status == "no-plan"


def test_short_lane_rebuilds_like_confluence():
    full = _pullback_frame()
    a = gc.build_candidate_plan(_confluence(full), full.iloc[:REBUILD_SIGNAL + 1])
    b = gc.build_candidate_plan(_confluence(full, source="short_lane"), full.iloc[:REBUILD_SIGNAL + 1])
    assert _same_plan(plan_to_dict(a), plan_to_dict(b))


def test_builder_sees_only_bars_up_to_the_signal(monkeypatch):
    full = _sine_frame()
    seen = []
    real = gc.build_candidate_plan

    def spy(candidate, window):
        seen.append((len(window), str(window.index[-1].date())))
        return real(candidate, window)

    monkeypatch.setattr(gc, "build_candidate_plan", spy)
    gc.simulate_blocked(_strategy(full), full)
    assert seen == [(REBUILD_SIGNAL + 1, _signal_date(full))]


def test_appended_bars_change_no_rebuilt_outcome():
    full = _sine_frame()
    shorter = full.iloc[:REBUILD_SIGNAL + 1 + 30]
    a, b = gc.simulate_blocked(_strategy(full), full), gc.simulate_blocked(_strategy(full), shorter)
    assert (a.cf_status, a.cf_r, a.win, a.bars_sha256) == (b.cf_status, b.cf_r, b.win, b.bars_sha256)


def _journal_must_not_be_read(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("live journal read at resolution time")
    for name in ("_resolve_stop_mult", "_resolve_tp2_r", "_resolve_time_stop_days"):
        monkeypatch.setattr(plan_params, name, boom)


def test_pinned_overrides_ignore_a_changed_live_journal(monkeypatch):
    full = _sine_frame()
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)
    _journal_must_not_be_read(monkeypatch)
    pins = {"stop_mult": 1.25, "tp2_r": 2.0, "time_stop_days": 6, "params": None}
    plan = gc.build_candidate_plan(_strategy(full, scan_params=pins), full.iloc[:REBUILD_SIGNAL + 1])
    assert plan is not None
    assert plan.stop_mult_applied == 1.25 and plan.time_stop_days == 6


def test_unpinned_override_with_the_flag_on_is_no_data(monkeypatch):
    full = _sine_frame()
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", True)
    _journal_must_not_be_read(monkeypatch)
    with pytest.raises(gc.UnpinnableBuild):
        gc.build_candidate_plan(_strategy(full), full.iloc[:REBUILD_SIGNAL + 1])
    assert gc.simulate_blocked(_strategy(full), full).cf_status == "no-data"


@pytest.mark.parametrize("flag", ["STALL_EXIT_ENABLED", "OPEX_CAUTION_ENABLED"])
def test_wall_clock_flags_make_a_strategy_rebuild_unpinnable(monkeypatch, flag):
    full = _sine_frame()
    monkeypatch.setattr(config, flag, True)
    assert gc.simulate_blocked(_strategy(full), full).cf_status == "no-data"


def test_pinned_scan_params_reads_a_plan_or_the_resolvers(monkeypatch):
    full = _sine_frame()
    plan = gc.build_candidate_plan(_strategy(full), full.iloc[:REBUILD_SIGNAL + 1])
    from_plan = gc.pinned_scan_params("RSI", plan=plan)
    assert set(from_plan) == {"stop_mult", "tp2_r", "time_stop_days", "params"}
    assert from_plan["stop_mult"] == plan.stop_mult_applied
    monkeypatch.setattr(plan_params, "_resolve_stop_mult", lambda s: 1.5)
    monkeypatch.setattr(plan_params, "_resolve_tp2_r", lambda s: None)
    monkeypatch.setattr(plan_params, "_resolve_time_stop_days", lambda s: 4)
    assert gc.pinned_scan_params("RSI") == {"stop_mult": 1.5, "tp2_r": None,
                                            "time_stop_days": 4, "params": None}


def test_stored_scan_params_round_trip_into_the_build():
    from swingbot.scan_params import ScanParams
    full = _pullback_frame()
    params = ScanParams.from_config()
    stored = gc.pinned_scan_params("Fibonacci", params=params)
    assert gc._scan_params_of(_confluence(full, scan_params=stored)) == params


def test_reanchored_scenario_rebuilds_on_the_cache_basis():
    full = _pullback_frame()
    price = float(full["Close"].iloc[REBUILD_SIGNAL])
    halved = full.copy()
    for col in ("Open", "High", "Low", "Close"):
        halved[col] = halved[col] * 0.5
    stored = _confluence(full, signal_close=price)           # scenario in the pre-split basis
    res = gc.simulate_blocked(stored, halved)
    plain = gc.simulate_blocked(_confluence(full, signal_close=price), full)
    assert res.reanchored is True
    assert res.plan["trigger_price"] == pytest.approx(plain.plan["trigger_price"] * 0.5)
    assert res.cf_status == plain.cf_status
