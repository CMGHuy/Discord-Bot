"""V191-14: the band replay joins the baseline and every cell on (signal
index, direction), so newly admitted and dropped plans survive as rows; the
census reads no outcome but the baseline's stop-then-reversal disclosure; the
dollar view sizes through gap_sizing exactly as live does."""
import math
import types

import pytest

from swingbot import config
from swingbot.core.backtesting import atr_band_replay as abr
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import atr_band
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.exit_sim import ExitResult
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.risk_limits import planned_loss_pct
from tests.market.test_atr_band import _frame

KEYS = ("k0.75", "k1", "k1.5")


def _plan(*, stop=98.25, level=99.0, tp1=104.0, moved=None, ceiling=None, direction="bullish"):
    return TradePlanV2(
        plan_id="p", ticker="XYZ", created_at="2024-01-02", source="confluence",
        strategy="S/R Confluence", horizon_key="4w", direction=direction, entry_type="stop_entry",
        trigger_price=100.0, entry_price=None, expiry_bars=5, stop_loss=stop, tp1=tp1,
        tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, acceptance_level=level, stop_ceiling_pct=ceiling,
        stop_moved_by=moved)


TODAY = _plan()                                                    # i=30: today's 1.75% stop
BAND = _plan(stop=96.0, moved="floor", ceiling=4.25)               # i=30 with the floor on
NEW = _plan(stop=96.0, level=99.5, moved="floor", ceiling=4.25)    # i=40: refused today (d 0.5%)
DROPPED = _plan(stop=98.0, level=98.0)                              # i=50: the band drops it
BLOCKED_SC = types.SimpleNamespace(direction="bullish", entry=100.0, stop_loss=98.0)


def _fake_replay(calls):
    def replay(ticker, df, horizon_key, k, mode, gates, blocked=None):
        calls.append((float(k), mode, blocked is not None))
        if k == 0.0:
            return [(30, TODAY), (50, DROPPED)]
        if blocked is not None:
            blocked.append((50, BLOCKED_SC))
        if k == 1.5:
            return [(30, TODAY), (40, NEW)]       # band_no_atr fallback: today's plan
        return [(30, BAND), (40, NEW)]
    return replay


def _stop_exit(df, i, plan, scale_out=True):
    return ExitResult(outcome="loss", runner_outcome=None, entry_index=i + 1, exit_index=i + 3,
                      entry_price=plan.trigger_price, r_total=-1.0,
                      legs=[{"fraction": 1.0, "exit_price": plan.stop_loss, "r": -1.0,
                             "reason": "stop"}])


@pytest.fixture
def fakes(monkeypatch):
    calls, simulated = [], []

    def exit_spy(df, i, plan, scale_out=True):
        simulated.append(plan)
        return _stop_exit(df, i, plan)

    monkeypatch.setattr(abr, "_replay", _fake_replay(calls))
    monkeypatch.setattr(abr, "_blocked_reasons",
                        lambda ticker, df, hk, k, mode, gates, blocked:
                        {(int(i), sc.direction): (sc, atr_band.REASON_RR_DROP) for i, sc in blocked})
    monkeypatch.setattr(abr, "simulate_exit", exit_spy)
    return types.SimpleNamespace(calls=calls, simulated=simulated)


def test_frozen_constants_and_keys():
    assert abr.ARMS == {"R": "rechoose", "K": "keep"}
    assert abr.K_STEPS == atr_band.FLOOR_GRID == (0.75, 1.0, 1.5)
    assert tuple(abr.cell_key(k) for k in abr.K_STEPS) == KEYS
    assert (abr.FLOOR_KNOB, abr.MODE_KNOB) == ("CONFLUENCE_ATR_STOP_FLOOR",
                                                "CONFLUENCE_ATR_TARGET_MODE")
    budget = abr.REFERENCE_ACCOUNT["balance"] * abr.REFERENCE_ACCOUNT["risk_pct"] / 100
    assert budget == 100.0 and abr.REFERENCE_ACCOUNT["sizing_mode"] == "risk_pct"


def test_a_v139_knob_refuses_the_measurement(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 3.0)
    with pytest.raises(RuntimeError, match="must be 0 while measuring v191"):
        abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="K")


def test_an_unknown_arm_is_refused(fakes):
    with pytest.raises(ValueError, match="arm must be one of"):
        abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="S")


def test_baseline_is_floor_zero_and_cells_use_the_arm_mode(fakes):
    abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="K")
    assert fakes.calls == [(0.0, "rechoose", False), (0.75, "keep", False),
                           (1.0, "keep", False), (1.5, "keep", False)]


def test_rows_are_the_union_so_new_and_dropped_plans_survive(fakes):
    rows = abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="R")
    assert [r["signal_index"] for r in rows] == [30, 40, 50]
    today, new, dropped = rows
    assert today["baseline"] is not None and today["newly_admitted"] == dict.fromkeys(KEYS, False)
    assert new["baseline"] is None
    assert new["newly_admitted"] == {"k0.75": True, "k1": True, "k1.5": True}
    assert dropped["cells"] == dict.fromkeys(KEYS, None) and dropped["baseline"] is not None
    assert [r["d"] for r in rows] == [pytest.approx(1.0), pytest.approx(0.5), pytest.approx(2.0)]
    assert all(r["atr_pct"] == pytest.approx(4.0) for r in rows)
    assert {r["arm"] for r in rows} == {"R"}


def test_moved_by_is_the_plan_band_or_the_band_a_dropped_plan_would_carry(fakes):
    today, new, dropped = abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="R")
    assert today["moved_by"] == {"k0.75": "floor", "k1": "floor", "k1.5": None}
    assert new["moved_by"] == {"k0.75": "floor", "k1": "floor", "k1.5": "floor"}
    # DROPPED: d 2.0% against lo = k * 4% -> under the floor at every k
    assert dropped["moved_by"] == dict.fromkeys(KEYS, "floor")


def test_a_cell_on_today_geometry_reuses_the_baseline_record(fakes):
    today = abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="R")[0]
    assert today["cells"]["k1.5"] is today["baseline"]
    assert today["cells"]["k1"] is not today["baseline"]
    assert today["cells"]["k1"]["stop_moved_by"] == "floor"


def test_record_carries_every_reported_field(fakes):
    rec = abr.replay_entries("XYZ", _frame(n=80), ("4w",), arm="R")[0]["cells"]["k1"]
    assert {"ticker", "strategy", "horizon_key", "entry_date", "outcome", "r_multiple",
            "planned_rr", "source", "direction", "exit_mix", "gap_through",
            "fill_beyond_ceiling", "stop_moved_by", "stop_distance_pct", "stop_distance_atr",
            "early_stop", "gap_overshoot_r", "regime2_state", "shares", "dollar_pnl",
            "dollar_exceeds_budget"} <= set(rec)
    assert rec["stop_distance_pct"] == pytest.approx(4.0)
    assert rec["stop_distance_atr"] == pytest.approx(1.0)
    assert rec["early_stop"] is True                    # stopped two sessions after the fill
    assert rec["fill_beyond_ceiling"] is False
    assert rec["dollar_exceeds_budget"] is False        # sized on the worst fill: loss <= $100


def test_dollar_view_sizes_a_band_plan_on_the_worst_fill_and_flags_a_gap(monkeypatch):
    df = _frame(n=80)
    df.iloc[33, df.columns.get_loc("Open")] = 94.0     # the stop bar opens through 96

    def gap_exit(frame, i, plan, scale_out=True):
        return ExitResult(outcome="loss", runner_outcome=None, entry_index=i + 1,
                          exit_index=i + 3, entry_price=100.0, r_total=-1.5,
                          legs=[{"fraction": 1.0, "exit_price": 94.0, "r": -1.5,
                                 "reason": "stop"}])

    monkeypatch.setattr(abr, "simulate_exit", gap_exit)
    rec = abr._record(df, 30, BAND, 4.0)
    shares = math.floor(100.0 / gs.worst_fill_distance(96.0, 4.25, "bullish") * 100) / 100
    assert rec["shares"] == pytest.approx(shares)
    assert rec["dollar_pnl"] == pytest.approx(round(shares * -6.0, 2))
    assert rec["dollar_exceeds_budget"] is True
    assert rec["gap_through"] is True
    assert rec["gap_overshoot_r"] == pytest.approx(0.5)   # |94 - 96| / |100 - 96|


def test_dollar_view_ignores_the_run_date_opex_scaling(monkeypatch):
    monkeypatch.setattr(abr.opex, "size_mult", lambda *a, **k: 0.5)
    monkeypatch.setattr(abr, "simulate_exit", _stop_exit)
    rec = abr._record(_frame(n=80), 30, BAND, 4.0)
    assert rec["shares"] * gs.worst_fill_distance(96.0, 4.25, "bullish") == \
        pytest.approx(100.0, abs=0.05)


def test_census_simulates_only_baseline_plans_and_names_dropped_reasons(fakes):
    rows = abr.census("XYZ", _frame(n=80), ("4w",), arm="K")
    assert {id(p) for p in fakes.simulated} <= {id(TODAY), id(DROPPED)}
    assert all(with_blocked for _, _, with_blocked in fakes.calls[1:])   # cells pass blocked=[]
    by_index = {r["signal_index"]: r for r in rows}
    assert by_index[50]["dropped"] == dict.fromkeys(KEYS, atr_band.REASON_RR_DROP)
    assert by_index[50]["in_cell"] == dict.fromkeys(KEYS, False) and by_index[50]["in_baseline"]
    assert by_index[30]["dropped"] == dict.fromkeys(KEYS, None)
    assert by_index[40]["in_baseline"] is False and by_index[40]["in_cell"]["k1"] is True
    assert not any(key in rows[0] for key in ("baseline", "cells", "outcome"))
    assert by_index[30]["size_zero"] == dict.fromkeys(KEYS, False)


def test_census_life_end_is_the_horizon_hold_capped_at_the_last_bar(fakes):
    df = _frame(n=80)
    rows = {r["signal_index"]: r for r in abr.census("XYZ", df, ("4w",), arm="K")}
    hold = bs.HORIZONS["4w"]["max_holding_days"]
    assert rows[30]["life_end_date"] == str(df.index[min(30 + hold, 79)].date())
    assert rows[50]["life_end_date"] == str(df.index[min(50 + hold, 79)].date())


def test_size_zero_is_flagged_for_an_account_too_small_for_one_cent(fakes, monkeypatch):
    monkeypatch.setitem(abr.REFERENCE_ACCOUNT, "balance", 1.0)
    rows = {r["signal_index"]: r for r in abr.census("XYZ", _frame(n=80), ("4w",), arm="R")}
    assert rows[40]["size_zero"] == dict.fromkeys(KEYS, True)
    assert rows[30]["size_zero"] == {"k0.75": True, "k1": True, "k1.5": False}  # k1.5: no band


def test_reversal_counts_tp1_before_a_k_atr_breach(monkeypatch):
    df = _frame(n=80)                                   # ATR 4%: lines 97 / 96 / 94
    df.iloc[32, df.columns.get_loc("Low")] = 97.0       # stopped at 98.25, touches 97
    df.iloc[34, df.columns.get_loc("High")] = 104.5     # then TP1 104
    monkeypatch.setattr(abr, "simulate_exit", lambda f, i, p, scale_out=True:
                        ExitResult(outcome="loss", runner_outcome=None, entry_index=31,
                                   exit_index=32, entry_price=100.0, r_total=-1.0,
                                   legs=[{"fraction": 1.0, "exit_price": 98.25, "r": -1.0,
                                          "reason": "stop"}]))
    assert abr._reversal(df, 30, TODAY, 4.0, abr.K_STEPS) == \
        {"k0.75": False, "k1": True, "k1.5": True}
    assert abr._reversal(df, 30, None, 4.0, abr.K_STEPS) is None
    assert abr._reversal(df, 30, TODAY, None, abr.K_STEPS) is None


def test_reversal_is_none_for_a_baseline_that_did_not_stop(monkeypatch):
    monkeypatch.setattr(abr, "simulate_exit", lambda f, i, p, scale_out=True:
                        ExitResult(outcome="win", runner_outcome=None, entry_index=31,
                                   exit_index=34, entry_price=100.0, r_total=2.0,
                                   legs=[{"fraction": 1.0, "exit_price": 104.0, "r": 2.0,
                                          "reason": "tp1"}]))
    assert abr._reversal(_frame(n=80), 30, TODAY, 4.0, abr.K_STEPS) is None


def test_signal_window_filters_on_the_signal_date(fakes):
    df = _frame(n=80)
    start = str(df.index[40].date())
    rows = abr.replay_entries("XYZ", df, ("4w",), arm="R", start=start)
    assert [r["signal_index"] for r in rows] == [40, 50]


# --- integration on the frozen DELL fixture (real replay, slow) ------------------------

@pytest.mark.slow
def test_dell_baseline_is_today_and_band_plans_store_their_ceiling():
    from tests.backtesting.test_backtest_scenarios import GATES
    from tests.fixtures.ohlcv_parity import load_ohlcv
    frame = load_ohlcv("DELL").loc[:"2019-12-31"]
    sigs = abr.signals("DELL", frame, "4w", arm="R", gates=GATES)
    today = bs.replay_scenarios("DELL", frame, "4w", gates=GATES)
    assert [(s.i, s.direction) for s in sigs if s.base is not None] == \
        sorted((int(i), p.direction) for i, p in today)
    floor_moved = newly = 0
    for sig in sigs:
        for key, plan in sig.plans.items():
            if plan is None or plan.stop_moved_by is None:
                continue
            assert plan.stop_ceiling_pct == pytest.approx(
                planned_loss_pct(plan.trigger_price, plan.stop_loss) + 0.25)
            floor_moved += plan.stop_moved_by == "floor" and key == "k1.5"
            newly += sig.base is None
    assert floor_moved > 0, "the 1.5 x ATR floor must move at least one DELL plan"
    assert newly > 0, "the band must admit at least one scenario the legacy 2.0% floor refused"


def test_signal_context_matches_truncated_history_and_ignores_future():
    df = _frame(n=80)
    sig = abr.Signal(30, "bullish", TODAY, {}, {})
    before = abr._context(df.iloc[:31], sig)
    df.iloc[31:, df.columns.get_loc("High")] = 1000.0
    df.iloc[31:, df.columns.get_loc("Volume")] = 100_000_000.0
    assert abr._context(df, sig) == before
    assert before == {"d": 1.0, "atr_pct": 4.0, "adv_dollars": 100_000_000.0}


def test_record_stamps_only_signal_history_without_mutating_the_plan(monkeypatch):
    def stamp(plan, window):
        plan.gap_sizing = {"seen": len(window)}

    def size(plan, **kwargs):
        return {"shares": float(plan.gap_sizing["seen"])}

    monkeypatch.setattr(abr, "simulate_exit", _stop_exit)
    monkeypatch.setattr(gs, "stamp_gap_sizing", stamp)
    monkeypatch.setattr(gs, "size_for_plan", size)
    plan = _plan(stop=96.0, moved="floor", ceiling=4.25)
    assert abr._record(_frame(n=80), 30, plan, 4.0)["shares"] == 31.0
    assert plan.gap_sizing is None


def test_blocked_reason_uses_the_replay_bucket_level_map(monkeypatch):
    df = _frame(n=400)
    signal_index = 303
    bucket_index = bs.bucket_bar(signal_index, "4w")

    def levels_asof(ticker, frame, i, hk, cache):
        cache["map_index"] = i

    def bar_scenarios(scope, frame, i, cache, dcb_params):
        return frame.iloc[:i + 1], 100.0, cache.get("map_index"), []

    monkeypatch.setattr(bs, "levels_asof", levels_asof)
    monkeypatch.setattr(bs, "_bar_scenarios", bar_scenarios)
    monkeypatch.setattr(abr, "band_no_plan_reason", lambda sc, level_map, params: level_map)
    reasons = abr._blocked_reasons("XYZ", df, "4w", 1.0, "keep", None,
                                   [(signal_index, BLOCKED_SC)])
    assert reasons[(signal_index, "bullish")][1] == bucket_index
