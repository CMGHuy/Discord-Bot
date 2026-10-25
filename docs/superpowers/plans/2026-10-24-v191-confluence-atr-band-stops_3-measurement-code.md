# v191 — Confluence ATR-band stops, part 3: measurement code, replay and Stages −1..1 (V191-14..V191-15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this part whole**: `grep -n "^### Task V191-15:" -A 300 <this file>`.

**Spec:** [2026-10-24-v191-confluence-atr-band-stops-design.md](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md)
**Index:** [2026-10-24-v191-confluence-atr-band-stops_0-index.md](2026-10-24-v191-confluence-atr-band-stops_0-index.md) — § Global Constraints, § Contracts, § Review Focus, § Parallelisation and the task ledger are binding here; this part never changes a shared name, signature or path.

Every path below is relative to the worktree root `.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops` (created by V191-1); run every command from there, never from the main checkout. Every code task ends with `python scripts/dev/complexity_gate.py` passing and the V191-1 golden still green:

```bash
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
```

Scope of this part: the band replay (census and outcome rows per arm, V191-14) and the funnel's Stages −1..1 (V191-15). Part 3 overflows the 1500-line cap, so V191-16..V191-18 (Stages 2..3, the Holm family and the reports; the staged driver `scripts/backtest/measure_atr_band_stop.py`; the Part B impact report's `--side`) live in [`2026-10-24-v191-confluence-atr-band-stops_3b-funnel-tail-driver-and-impact-report.md`](2026-10-24-v191-confluence-atr-band-stops_3b-funnel-tail-driver-and-impact-report.md); ids, files and contracts are exactly the index ledger's. No code here runs a measurement: V191-20..V191-22 (part 4) do, through `backtest-runner`.

Names consumed from parts 1 and 2: `atr_band.FLOOR_GRID`, `atr_band.raw_atr14_pct`, `atr_band.band_stop`, `atr_band.MOVED_*`, `atr_band.REASON_*` (V191-7); `builders.band_no_plan_reason(scenario, level_map, params)` (V191-8); `replay_scenarios(..., blocked=)` building band plans when `CONFLUENCE_ATR_STOP_FLOOR > 0` reaches `ScanParams` (V191-9); `gap_sizing.stamp_gap_sizing` stamping every band plan with `BAND_KEY`, `gap_sizing.size_for_plan` taking the band branch, `gap_sizing.worst_fill_distance`, `stop_scope.band_sizing_verdict` (V191-11); `TradePlanV2.stop_moved_by` (V191-4); `gap_stats` keys `p99_down_gap_pct` / `n_down`, `gap_sizing.MIN_DOWN_GAPS`, stamp key `down_gap_p99_pct` (V191-5); `config.CONFLUENCE_ATR_STOP_FLOOR`, `config.CONFLUENCE_ATR_TARGET_MODE`, `config.LONG_GAP_SIZING` and the `_V191` reachability text (V191-2).

Pre-existing names this part reuses (verified on `main` with `git grep -n`): `backtest_scenarios.replay_scenarios`, `_replay_params`, `_ReplayScope`, `_bar_scenarios`, `HORIZONS`; `acceptance.arm_trade_from_plan`, `bootstrap_delta`, `delta_expectancy_r`, `expectancy_r`, `win_rate`, `median_planned_rr`, `mde_paired`, `project_target_n`, `render_json`, `CLOSED`, `BOOTSTRAP_RESAMPLES`; `acceptance_replay.UNTRIGGERED`, `_exit_mix`, `_gap_through`; `acceptance_exit_funnel.arm_trades`, `_flips`, `_sides`, `_triggered_once`, `_pp`, `sign_flip_p`, `ELIGIBILITY_CLAUSES`, `PERMUTATION_N`; `acceptance_harvest.evaluate_harvest`; `backtest_wf.plateau_report`, `PLATEAU_TOLERANCE_R`; `giveback_levels_funnel.holm`; `instrument.stats.ledger_qvalues`; `instrument.cli.add_instrument_arg`, `spec_from_args`, `require_v1`; `training_data.select`, `load_daily`; `exit_sim.simulate_exit`, `ExitResult`; `stop_scope.plan_stop_ceiling`; `builders.STOP_GEOMETRY_TOL`; `strategy_types.LEGACY_HORIZONS`; `arms.knobs.apply_knobs`; `tests.backtesting.acceptance_rows.record`.

---

# Phase 8 — Measurement code

### Task V191-14: Band replay rows: census and outcome rows per arm

**Model:** opus — every measured number comes from these rows; the band changes which plans exist, so a wrong join (zipping by position, as v139 could) silently mispairs trades, and the census must read no outcome beyond the one disclosed reversal count.

**Files:**
- Create: `swingbot/core/backtesting/atr_band_replay.py`
- Test: `tests/backtesting/test_atr_band_replay.py` (create; joins the suite that already holds `tests/backtesting/`)

**Interfaces:**
- Consumes: `atr_band.FLOOR_GRID`, `raw_atr14_pct`, `band_stop`, `REASON_SIZE_ZERO`, `REASON_RR_DROP` (V191-7); `builders.band_no_plan_reason(scenario, level_map, params)` (V191-8); `bs.replay_scenarios(ticker, df, horizon_key, gates=, blocked=)` producing band plans when the floor reaches `ScanParams` through config (V191-9; `apply_knobs` reaches both `ScanParams.from_config()` sites, the legacy-gates one included); `gap_sizing.stamp_gap_sizing(plan, df)` / `size_for_plan(plan, entry=, account_cfg=)` band branch, `gap_sizing.worst_fill_distance`, `stop_scope.band_sizing_verdict(plan, sizing_fn=)` (V191-11); `TradePlanV2.stop_moved_by` (V191-4); `tests.market.test_atr_band._frame` (V191-7 test helper: flat closes, Wilder ATR14 exactly `2 * half_range` from bar 14 on).
- Produces (index § Contracts, final):
  - `FLOOR_KNOB = "CONFLUENCE_ATR_STOP_FLOOR"`, `MODE_KNOB = "CONFLUENCE_ATR_TARGET_MODE"`, `ARMS = {"R": "rechoose", "K": "keep"}`, `K_STEPS = FLOOR_GRID`, `REFERENCE_ACCOUNT` (exact dict in § Contracts), `cell_key(k)` → `"k0.75"`, `"k1"`, `"k1.5"`.
  - `census(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS, gates=None) -> list[dict]` and `replay_entries(...)` (same signature).
  - Outcome row keys: `arm, ticker, horizon_key, entry_date, signal_index, direction, d, atr_pct, adv_dollars, baseline, cells, moved_by, newly_admitted`. Record keys: the `ArmTrade` fields plus `exit_mix, gap_through, fill_beyond_ceiling, stop_moved_by, stop_distance_pct, stop_distance_atr, early_stop, gap_overshoot_r, regime2_state, shares, dollar_pnl, dollar_exceeds_budget`.
  - Census row keys: `arm, ticker, horizon_key, entry_date, signal_index, direction, d, atr_pct, adv_dollars, in_baseline, life_end_date, in_cell, moved_by, newly_admitted, dropped, size_zero, reversal`.
  - Semantics V191-15/16 rely on: `moved_by[key]` is the cell plan's `stop_moved_by`; when the cell has no plan but the baseline has one, it is the band the baseline plan **would** have carried (`band_stop` on its trigger and `acceptance_level`), so a plan the band dropped stays in its stratum as a removed trade; `newly_admitted[key]` is `baseline plan is None and cell plan is not None`; a cell plan with no band (`stop_moved_by is None`) and today's geometry reuses the baseline record object.
  - Additions beyond the § Contracts record list, consumed only inside this part: record keys `gap_overshoot_r`, `regime2_state`, `shares`; row key `adv_dollars`. They serve spec § Reporting (gap overshoot in R, the regime cut, dollar volume of newly admitted plans). `Signal` (NamedTuple) and `signals(...)` are module-public for the DELL integration test; nothing outside this module consumes them.

Design, fixed here:

- **Join, never zip.** Per ticker and horizon: one baseline replay at floor 0 and one replay per cell at floor `k` with the arm's target mode, each keyed by `(signal index, direction)`; the rows are the sorted union of the keys. Newly admitted, dropped and cooldown-shifted plans all survive as rows with one side `None`.
- **Knobs.** `apply_knobs({FLOOR_KNOB: k, MODE_KNOB: mode})` around each replay; the baseline uses `{FLOOR_KNOB: 0.0, MODE_KNOB: "rechoose"}`. Raises `RuntimeError` when either v139 knob is non-zero (index § Global Constraints).
- **Dollar view.** Each traded record is sized on `REFERENCE_ACCOUNT` at the fill, with `LONG_GAP_SIZING` and `SHORT_GAP_SIZING` both on (the coupled live configuration a floor requires) and OPEX scaling pinned to 1.0, through `gap_sizing.stamp_gap_sizing` on a copy of the plan (as-of window `df.iloc[:i + 1]`) and `gap_sizing.size_for_plan(copy, entry=fill, account_cfg=REFERENCE_ACCOUNT)` — the one sizing function live uses. `dollar_pnl = shares × Σ legs fraction × (exit − fill) × side`; `dollar_exceeds_budget` is a loss past `balance × risk_pct / 100` by more than `EXCEED_TOL_DOLLARS = 0.5` (rounding noise of 0.01-share sizing). R is untouched: `r_multiple` is `simulate_exit`'s `r_total`.
- **Census reads no outcome** except the spec's one disclosure: for a baseline plan that exits at its stop, whether price then reached TP1 within the horizon (`HORIZONS[h]["max_holding_days"]` bars from the fill) without first breaching `k × ATR` from the trigger. Only baseline plans are ever simulated in the census. `life_end_date` (signal bar + `max_holding_days`, capped at the last bar) is a plan-life proxy for the concurrency count, not an outcome.
- **Dropped reasons.** The cell replay passes `blocked=[]`; each blocked `(i, scenario)` gets `band_no_plan_reason(scenario, level_map, params)` with the bar's own level map from `bs._bar_scenarios` and the build params the replay used (`ScanParams.from_config()` under legacy gates, else the replay params), under the same knobs.

- [ ] **Step 1: Write the failing tests** in `tests/backtesting/test_atr_band_replay.py`

```python
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
        [(int(i), p.direction) for i, p in today]
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_atr_band_replay.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.atr_band_replay'`.

- [ ] **Step 3: Write `swingbot/core/backtesting/atr_band_replay.py`**

```python
"""v191 ATR-band replay: every confluence signal replayed with the floor off
(baseline) and at each floor k for one target arm, from the same bars.

Unlike v139 arm S, the band changes WHICH plans exist: scenarios the percent
floor refused are admitted (newly_admitted), arm K drops plans under the
minimum reward:risk (band_rr_drop), arm R drops plans with no target
(band_no_target), and the per-direction cooldown can shift. So the baseline
and each cell are joined on the union of (signal index, direction) per ticker
and horizon, never zipped by position.

Two row shapes, both plain JSON types: census rows (Stage -1 -- plans only,
plus the spec's one outcome-adjacent disclosure, stop-then-reversal on the
BASELINE) and outcome rows (Stages 0-3).

Dollar view: each traded record is sized on REFERENCE_ACCOUNT at the fill
with both gap-sizing flags on (the coupled configuration a live floor
requires) and OPEX scaling pinned to 1.0, through gap_sizing -- the one
sizing function the alert and the engine use. R is never re-priced.
"""
from __future__ import annotations

import copy
import dataclasses
from contextlib import contextmanager
from typing import NamedTuple
from unittest import mock

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.acceptance_replay import UNTRIGGERED, _exit_mix, _gap_through
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.market import atr_band, opex
from swingbot.core.planning import gap_sizing
from swingbot.core.planning.builders import STOP_GEOMETRY_TOL, band_no_plan_reason
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.stop_scope import band_sizing_verdict, plan_stop_ceiling
from swingbot.core.risk_limits import planned_loss_pct
from swingbot.scan_params import ScanParams

FLOOR_KNOB = "CONFLUENCE_ATR_STOP_FLOOR"
MODE_KNOB = "CONFLUENCE_ATR_TARGET_MODE"
#: PRE-REGISTERED (spec § Arm R / § Arm K): arm -> CONFLUENCE_ATR_TARGET_MODE.
ARMS = {"R": "rechoose", "K": "keep"}
#: PRE-REGISTERED floor grid (spec § Definitions). A new step is a new pre-registration.
K_STEPS = atr_band.FLOOR_GRID
REFERENCE_ACCOUNT = {"balance": 10000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct",
                     "position_pct": 10.0, "max_position_pct": 100.0,
                     "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
DOLLAR_VIEW_FLAGS = {"LONG_GAP_SIZING": True, "SHORT_GAP_SIZING": True}
#: A loss past the budget by more than this is an exceedance; less is the
#: rounding noise of 0.01-share sizing.
EXCEED_TOL_DOLLARS = 0.5
EARLY_STOP_SESSIONS = 2
ADV_BARS = 20
_BASELINE = (0.0, "rechoose")


def cell_key(k) -> str:
    """Stable JSON key for a floor: 'k0.75', 'k1', 'k1.5'."""
    return f"k{float(k):g}"


class Signal(NamedTuple):
    """One (signal index, direction) of one ticker and horizon, on every side."""
    i: int
    direction: str
    base: object        # baseline TradePlanV2 | None
    plans: dict         # cell_key -> TradePlanV2 | None
    blocked: dict       # cell_key -> (scenario, band reason | None) | None


# --- replay -------------------------------------------------------------------

def _check_knobs_off() -> None:
    if config.CONFLUENCE_STRUCTURAL_STOP_PCT or config.CONFLUENCE_STOP_DROP_PCT:
        raise RuntimeError(
            "CONFLUENCE_STRUCTURAL_STOP_PCT and CONFLUENCE_STOP_DROP_PCT must be 0 while "
            "measuring v191: a v139 knob is never set with a v191 knob.")


def _mode(arm) -> str:
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {sorted(ARMS)}, got {arm!r}")
    return ARMS[arm]


def _delta(k, mode) -> dict:
    return {FLOOR_KNOB: float(k), MODE_KNOB: mode}


def _replay(ticker, df, horizon_key, k, mode, gates, blocked=None) -> list:
    """replay_scenarios at floor k and target mode; apply_knobs reaches both
    ScanParams.from_config() call sites inside the replay."""
    with apply_knobs(_delta(k, mode)):
        return bs.replay_scenarios(ticker, df, horizon_key, gates=gates, blocked=blocked)


def _blocked_reasons(ticker, df, horizon_key, k, mode, gates, blocked) -> dict:
    """{(i, direction): (scenario, reason)} for the scenarios a cell's plan
    build refused, the reason named by builders.band_no_plan_reason with the
    bar's own level map and the build params the replay used. First per key."""
    out: dict = {}
    if not blocked:
        return out
    with apply_knobs(_delta(k, mode)):
        params, legacy = bs._replay_params(None, gates)
        scope = bs._ReplayScope(ticker, horizon_key, bs.HORIZONS[horizon_key], params, legacy, None)
        build_params = ScanParams.from_config() if legacy else params
        for i, sc in blocked:
            key = (int(i), sc.direction)
            if key not in out:
                level_map = bs._bar_scenarios(scope, df, int(i), {}, None)[2]
                out[key] = (sc, band_no_plan_reason(sc, level_map, build_params))
    return out


def _by_key(plans) -> dict:
    return {(int(i), plan.direction): plan for i, plan in plans}


def _cell_side(ticker, df, horizon_key, k, mode, gates, with_blocked) -> tuple:
    blocked = [] if with_blocked else None
    plans = _by_key(_replay(ticker, df, horizon_key, k, mode, gates, blocked))
    reasons = _blocked_reasons(ticker, df, horizon_key, k, mode, gates, blocked) \
        if with_blocked else {}
    return plans, reasons


def signals(ticker, df, horizon_key, *, arm, cells=K_STEPS, gates=None,
            with_blocked=False) -> list[Signal]:
    """The union of the baseline's and every cell's (signal index, direction),
    sorted. `gates` is the replay_scenarios test seam (None = live ScanParams)."""
    _check_knobs_off()
    mode = _mode(arm)
    base = _by_key(_replay(ticker, df, horizon_key, *_BASELINE, gates))
    by_cell, blocked_by_cell = {}, {}
    for k in cells:
        by_cell[cell_key(k)], blocked_by_cell[cell_key(k)] = _cell_side(
            ticker, df, horizon_key, k, mode, gates, with_blocked)
    keys = set(base).union(*by_cell.values(), *blocked_by_cell.values())
    return [Signal(i, d, base.get((i, d)),
                   {key: plans.get((i, d)) for key, plans in by_cell.items()},
                   {key: reasons.get((i, d)) for key, reasons in blocked_by_cell.items()})
            for i, d in sorted(keys)]


# --- row context ----------------------------------------------------------------

def _anchor(sig) -> tuple:
    """(entry, level) of the signal: any plan's trigger and pre-clamp level,
    else the blocked scenario's entry and stop."""
    plan = sig.base or next((p for p in sig.plans.values() if p is not None), None)
    if plan is not None:
        return plan.trigger_price, plan.acceptance_level
    sc = next(b[0] for b in sig.blocked.values() if b is not None)
    return sc.entry, sc.stop_loss


def _adv(window) -> float | None:
    if window.empty or "Volume" not in window:
        return None
    tail = window.tail(ADV_BARS)
    return float((tail["Close"] * tail["Volume"]).mean())


def _context(df, sig) -> dict:
    entry, level = _anchor(sig)
    window = df.iloc[: sig.i + 1]
    return {"d": None if level is None else planned_loss_pct(entry, level),
            "atr_pct": atr_band.raw_atr14_pct(window, entry), "adv_dollars": _adv(window)}


def _identity(ticker, horizon_key, df, sig, arm) -> dict:
    return {"arm": arm, "ticker": ticker, "horizon_key": horizon_key,
            "entry_date": str(df.index[sig.i].date()), "signal_index": sig.i,
            "direction": sig.direction}


def _would_move(plan, atr_pct, k) -> str | None:
    """The band a baseline plan would have carried at floor k."""
    if plan is None or plan.acceptance_level is None:
        return None
    band = atr_band.band_stop(plan.trigger_price, plan.acceptance_level,
                              plan.direction == "bullish", atr_pct, k)
    return None if band is None else band.moved_by


def _moved_by(sig, atr_pct, cells) -> dict:
    out = {}
    for k in cells:
        plan = sig.plans[cell_key(k)]
        out[cell_key(k)] = plan.stop_moved_by if plan is not None \
            else _would_move(sig.base, atr_pct, k)
    return out


def _newly_admitted(sig, cells) -> dict:
    return {cell_key(k): sig.base is None and sig.plans[cell_key(k)] is not None for k in cells}


# --- dollar view ------------------------------------------------------------------

@contextmanager
def _dollar_env():
    with apply_knobs(DOLLAR_VIEW_FLAGS), mock.patch.object(opex, "size_mult", return_value=1.0):
        yield


def _account() -> dict:
    return dict(REFERENCE_ACCOUNT)


def _budget() -> float:
    return REFERENCE_ACCOUNT["balance"] * REFERENCE_ACCOUNT["risk_pct"] / 100.0


def _stamped(window, plan):
    sized = copy.copy(plan)
    gap_sizing.stamp_gap_sizing(sized, window)
    return sized


def _shares(window, plan, fill) -> float:
    with _dollar_env():
        result = gap_sizing.size_for_plan(_stamped(window, plan), entry=fill,
                                          account_cfg=_account())
    return float((result or {}).get("shares") or 0.0)


def _dollar_pnl(plan, res, shares) -> float:
    side = 1.0 if plan.direction == "bullish" else -1.0
    move = sum(float(leg["fraction"]) * (float(leg["exit_price"]) - res.entry_price)
               for leg in res.legs)
    return round(shares * side * move, 2)


def _size_zero(df, i, plan) -> bool:
    if plan is None or plan.stop_moved_by is None:
        return False
    with _dollar_env():
        verdict = band_sizing_verdict(
            _stamped(df.iloc[: i + 1], plan),
            sizing_fn=lambda p: gap_sizing.size_for_plan(p, account_cfg=_account()))
    return verdict == atr_band.REASON_SIZE_ZERO


# --- outcome records ----------------------------------------------------------------

def _early_stop(res) -> bool:
    return _exit_mix(res) == "stop" and res.exit_index - res.entry_index <= EARLY_STOP_SESSIONS


def _overshoot_r(df, plan, res) -> float:
    bar_open = float(df["Open"].values[res.exit_index])
    return abs(bar_open - plan.stop_loss) / abs(res.entry_price - plan.stop_loss)


def _record(df, i, plan, atr_pct) -> dict | None:
    """One side's exit as ArmTrade fields plus the disclosures, or None when
    the plan never became a trade. fill_beyond_ceiling: a fill live
    plan_manager would cancel (cancelled_risk_cap) that the replay keeps."""
    res = simulate_exit(df, i, plan, scale_out=True)
    if res.outcome in UNTRIGGERED:
        return None
    trade = arm_trade_from_plan(plan, entry_date=str(df.index[i].date()),
                                outcome=res.outcome, r_multiple=res.r_total)
    shares = _shares(df.iloc[: i + 1], plan, res.entry_price)
    pnl = _dollar_pnl(plan, res, shares)
    distance = planned_loss_pct(plan.trigger_price, plan.stop_loss)
    gap = _gap_through(df, plan, res)
    return {**dataclasses.asdict(trade), "exit_mix": _exit_mix(res), "gap_through": gap,
            "fill_beyond_ceiling": planned_loss_pct(res.entry_price, plan.stop_loss)
            > plan_stop_ceiling(plan) + STOP_GEOMETRY_TOL,
            "stop_moved_by": plan.stop_moved_by, "stop_distance_pct": distance,
            "stop_distance_atr": distance / atr_pct if atr_pct else None,
            "early_stop": _early_stop(res),
            "gap_overshoot_r": _overshoot_r(df, plan, res) if gap else None,
            "regime2_state": (plan.entry_context or {}).get("regime2_state"),
            "shares": shares, "dollar_pnl": pnl,
            "dollar_exceeds_budget": pnl < -(_budget() + EXCEED_TOL_DOLLARS)}


def _same_geometry(a, b) -> bool:
    return (a.trigger_price, a.stop_loss, a.tp1, a.tp2, a.entry_type) == \
        (b.trigger_price, b.stop_loss, b.tp1, b.tp2, b.entry_type)


def _cell_record(df, i, plan, base, baseline, atr_pct) -> dict | None:
    if plan is None:
        return None
    if base is not None and plan.stop_moved_by is None and _same_geometry(plan, base):
        return baseline          # no band on this plan (band_no_atr): today's trade
    return _record(df, i, plan, atr_pct)


def entry_row(ticker, horizon_key, df, sig, arm, cells) -> dict | None:
    """One signal under the baseline and every cell; None when nothing traded."""
    ctx = _context(df, sig)
    baseline = None if sig.base is None else _record(df, sig.i, sig.base, ctx["atr_pct"])
    records = {cell_key(k): _cell_record(df, sig.i, sig.plans[cell_key(k)], sig.base, baseline,
                                         ctx["atr_pct"]) for k in cells}
    if baseline is None and all(record is None for record in records.values()):
        return None
    return {**_identity(ticker, horizon_key, df, sig, arm), **ctx,
            "baseline": baseline, "cells": records,
            "moved_by": _moved_by(sig, ctx["atr_pct"], cells),
            "newly_admitted": _newly_admitted(sig, cells)}


# --- census -------------------------------------------------------------------------

def _crossed(bull, low, high, level, *, below) -> bool:
    if bull:
        return low <= level if below else high >= level
    return high >= level if below else low <= level


def _reached_tp1_first(df, start, end, plan, lo_pct) -> bool:
    bull = plan.direction == "bullish"
    line = plan.trigger_price * (1 - lo_pct / 100 if bull else 1 + lo_pct / 100)
    lows, highs = df["Low"].values, df["High"].values
    for j in range(start, end + 1):
        if _crossed(bull, lows[j], highs[j], line, below=True):
            return False
        if _crossed(bull, lows[j], highs[j], plan.tp1, below=False):
            return True
    return False


def _reversal(df, i, base, atr_pct, cells) -> dict | None:
    """Spec § Stage -1: a baseline stop exit whose price later reached TP1
    within the horizon without first breaching k x ATR. Outcome-adjacent,
    read once, never selects k. None unless the baseline stopped out."""
    if base is None or atr_pct is None:
        return None
    res = simulate_exit(df, i, base, scale_out=True)
    if res.outcome in UNTRIGGERED or _exit_mix(res) != "stop":
        return None
    end = min(res.entry_index + bs.HORIZONS[base.horizon_key]["max_holding_days"], len(df) - 1)
    return {cell_key(k): _reached_tp1_first(df, res.entry_index, end, base, atr_pct * float(k))
            for k in cells}


def _life_end(df, i, horizon_key) -> str:
    end = min(i + bs.HORIZONS[horizon_key]["max_holding_days"], len(df) - 1)
    return str(df.index[end].date())


def _dropped_reason(sig, key) -> str | None:
    if sig.plans[key] is not None or sig.blocked.get(key) is None:
        return None
    return sig.blocked[key][1]


def census_row(ticker, horizon_key, df, sig, arm, cells) -> dict:
    """Plans only; the baseline alone is simulated, for the reversal count."""
    ctx = _context(df, sig)
    keys = [cell_key(k) for k in cells]
    return {**_identity(ticker, horizon_key, df, sig, arm), **ctx,
            "in_baseline": sig.base is not None,
            "life_end_date": _life_end(df, sig.i, horizon_key),
            "in_cell": {key: sig.plans[key] is not None for key in keys},
            "moved_by": _moved_by(sig, ctx["atr_pct"], cells),
            "newly_admitted": _newly_admitted(sig, cells),
            "dropped": {key: _dropped_reason(sig, key) for key in keys},
            "size_zero": {key: _size_zero(df, sig.i, sig.plans[key]) for key in keys},
            "reversal": _reversal(df, sig.i, sig.base, ctx["atr_pct"], cells)}


# --- entry points -------------------------------------------------------------------

def _in_window(signal_date, start, end) -> bool:
    return not ((start and signal_date < start) or (end and signal_date > end))


def _rows(make, ticker, df, horizons, arm, start, end, cells, gates, with_blocked) -> list:
    rows = []
    for horizon_key in horizons:
        for sig in signals(ticker, df, horizon_key, arm=arm, cells=cells, gates=gates,
                           with_blocked=with_blocked):
            if not _in_window(str(df.index[sig.i].date()), start, end):
                continue
            row = make(ticker, horizon_key, df, sig, arm, cells)
            if row is not None:
                rows.append(row)
    return rows


def replay_entries(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS,
                   gates=None) -> list[dict]:
    """Outcome rows for one ticker and arm. `start`/`end` (ISO or None)
    restrict the SIGNAL date; the exit walk may run past `end`. Stage 3 and
    the 2023 fold pass the one selected cell so no other cell is read."""
    return _rows(entry_row, ticker, df, horizons, arm, start, end,
                 tuple(float(k) for k in cells), gates, False)


def census(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS,
           gates=None) -> list[dict]:
    """Plan-only rows for one ticker and arm (Stage -1)."""
    return _rows(census_row, ticker, df, horizons, arm, start, end,
                 tuple(float(k) for k in cells), gates, True)
```

Notes for the implementer: `_check_knobs_off` and `_mode(arm)` run at the top of `signals`, before any replay, so the v139 refusal needs no fakes and an unknown arm fails before the fake replay is touched. `plan.entry_context` is a `TradePlanV2` field today (`plan_types.py:69`); if it is missing in the worktree, stop and report rather than guard it. `bs._bar_scenarios`, `bs._replay_params` and `bs._ReplayScope` are module-private in `backtest_scenarios.py`; this module is their one new reader, in the same package, and must not change them. The `abs=0.05` in the OPEX test is the 0.01-share floor on a ~4.26 distance.

- [ ] **Step 4: Run the tests and the gates**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_atr_band_replay.py
python -m pytest tests/backtesting/test_atr_band_replay.py -m slow -v
python scripts/dev/testrun.py file tests/backtesting/test_confluence_stop_replay.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed` (the slow DELL test included); every new function under complexity 15 (`signals`, `_record` and `_blocked_reasons` are the largest, all well under).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/atr_band_replay.py tests/backtesting/test_atr_band_replay.py
git commit -m "feat(backtest): v191 band replay -- census and outcome rows per arm, joined on (signal, direction), dollar view through gap_sizing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V191-15: Funnel Stages −1..1: census verdict, paired MDE, plateau selection

**Model:** opus — freezes the pre-registered selection rule (floor-moved stratum alone, plateau with the edge-cell rule, MDE on the paired rows) in code before fold-train is read; an off-by-one in the stratum or the neighbour rule changes which cell gets the one VALIDATION shot.

**Files:**
- Create: `swingbot/core/backtesting/atr_band_funnel.py`
- Create: `tests/backtesting/test_atr_band_funnel.py` (the tests; also hosts the synthetic row builders V191-16 and V191-17 import)

**Interfaces:**
- Consumes: `atr_band_replay.K_STEPS`, `cell_key`, `FLOOR_KNOB`, `REFERENCE_ACCOUNT` and the census / outcome row shapes (V191-14); `atr_band.MOVED_FLOOR`, `MOVED_CEILING`, `MOVED_UNTOUCHED`, `REASON_RR_DROP`, `REASON_NO_TARGET` (V191-7); existing `acceptance.mde_paired`, `delta_expectancy_r`, `project_target_n`, `render_json`, `CLOSED`, `BOOTSTRAP_RESAMPLES`; `acceptance_exit_funnel.arm_trades`, `ELIGIBILITY_CLAUSES`; `acceptance_harvest.evaluate_harvest`; `backtest_wf.plateau_report`, `PLATEAU_TOLERANCE_R`; `config.PORTFOLIO_HEAT_CAP_PCT`.
- Produces (index § Contracts, final): `FOLD_TRAIN = ("2018-06-01", "2022-12-31")`, `VALIDATION = ("2024-01-01", "2025-12-31")`, `FOLD_YEARS = (2021, 2022, 2023)`, `FOLD_2023 = ("2023-01-01", "2023-12-31")`, `MIN_FOLD_N = 30`, `MIN_POSITIVE_FOLDS = 2`, `MDE_CEILING_R = 0.10`, `MDE_POWER = 0.80`, `CLUSTER = "week"`, `INSTRUMENT = "v1"`, `DATA_SOURCE = "alpaca"`, `HOLM_ALPHA = 0.05`; `floor_moved(rows, key) -> list`; `stage_minus1(census_rows, arm, cells=K_STEPS) -> dict` (verdict `REACHABLE` | `refused:zero-diff`, plus `"reachable_cells": [k, ...]`); `stage0(rows, arm, cells=K_STEPS) -> dict` (verdict `POWERED` | `UNDERPOWERED`, plus `"powered_cells": [k, ...]`); `stage1(rows, arm, cells=K_STEPS, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict` (verdict `SELECTED` | `NO_ELIGIBLE_CELL`, `"selected": {"cell", "k"} | None`).
- Test helpers produced in `tests/backtesting/test_atr_band_funnel.py` (consumed by V191-16 and V191-17): `KEYS`, `band_record(ticker, date, outcome, r, *, moved="floor", pnl=None, exceeds=False, direction="bullish", horizon="4w")`, `band_row(baseline, cells, *, moved=None, d=1.0, atr=4.0)`, `lifted_band_rows(lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021, moved="floor")`, `census_row(moved=("floor",)*3, *, in_baseline=True, in_cell=(True,)*3, newly=(False,)*3, dropped=(None,)*3, size_zero=(False,)*3, reversal=None, d=1.0, atr=4.0, ticker="T00", date="2021-01-15", life_end="2021-02-22", horizon="4w", direction="bullish")`.

Rules frozen here (spec § Gate, § Stage −1; index § Global Constraints):

- **Decision stratum.** Every clause, every stage, is scored on `floor_moved(rows, key)`: the rows whose `moved_by[key] == "floor"`. Untouched and ceiling strata are reported (V191-16), never selected on.
- **Stage −1 per cell:** `REACHABLE` when the floor moves at least one plan (`in_cell` and `moved_by == "floor"`), else `refused:zero-diff` — a cell with no floor-moved plan cannot be scored. The arm is `REACHABLE` when any cell is; `reachable_cells` lists them. Disclosed per cell and per `horizon/direction` stratum: plans today, floor / ceiling / untouched counts, newly admitted, `band_rr_drop`, `band_no_target`, `band_size_zero`, removed, stop-then-reversal; arm-wide: the v139 arm S overlap (`2% < d ≤ 2 × a`), the `a` distribution in 0.5-point buckets, concurrency of open band plans per business day (max, p95, and days over `PORTFOLIO_HEAT_CAP_PCT / risk_pct` slots), and grid neighbours with identical floor-moved sets.
- **Stage 0 per cell:** paired MDE on the floor-moved rows where both sides traded, statistic ΔExpR, `acceptance.mde_paired(..., power=0.80, cluster="week")`, observed N = closed baseline trades, target N projected by window length (`project_target_n`, fold-train days → VALIDATION days). Powered when `mde ≤ 0.10`. A cell over the ceiling is refused; the arm is `POWERED` when at least one cell is, and `powered_cells` lists them. Newly admitted rows have no pair; their count is disclosed.
- **Stage 1:** every grid cell gets the v92 harvest gate at `stage="walkforward"` on its floor-moved rows (week-clustered) and its point ΔExpR. A candidate (a cell in `cells`, i.e. powered) is selectable when clauses 1–3 (`ELIGIBILITY_CLAUSES`) PASS **and** `plateau_report(FLOOR_KNOB, grid, ΔExpR, k)["is_plateau"]` holds — every existing neighbour in `(0.75, 1.0, 1.5)` within `PLATEAU_TOLERANCE_R` (0.03) of its ΔExpR, whatever that neighbour's own eligibility; an edge cell needs its one neighbour; a cell whose neighbour has no ΔExpR is a spike. Winner: highest point ΔExpR; a tie goes to the smaller `k` (`max` keeps the first).

- [ ] **Step 1: Write the failing tests** in `tests/backtesting/test_atr_band_funnel.py`

```python
"""V191-15/16: the v191 funnel on synthetic band rows. Every clause is scored
on the floor-moved stratum alone; Stage -1 reads plans only; Stage 0 is the
paired dExpR MDE; Stage 1 is the plateau selection with the edge-cell rule."""
import pytest

from swingbot import config
from swingbot.core.backtesting import atr_band_funnel as funnel
from swingbot.core.backtesting.backtest_wf import PLATEAU_TOLERANCE_R
from tests.backtesting.acceptance_rows import record

KEYS = ("k0.75", "k1", "k1.5")
N = 200                     # bootstrap resamples: enough for the synthetic signal


def band_record(ticker, date, outcome, r, *, moved="floor", pnl=None, exceeds=False,
                direction="bullish", horizon="4w"):
    rec = record(ticker, date, outcome, r, horizon=horizon)
    return {**rec, "direction": direction, "fill_beyond_ceiling": False, "stop_moved_by": moved,
            "stop_distance_pct": 4.0 if moved else 1.75, "stop_distance_atr": 1.0 if moved else 0.44,
            "early_stop": False, "gap_overshoot_r": None, "regime2_state": None, "shares": 23.46,
            "dollar_pnl": 100.0 * r if pnl is None else pnl, "dollar_exceeds_budget": exceeds}


def band_row(baseline, cells, *, moved=None, d=1.0, atr=4.0):
    """`baseline` and each `cells` value are band_record() dicts or None."""
    anchor = baseline or next(c for c in cells.values() if c is not None)
    return {"arm": "K", "ticker": anchor["ticker"], "horizon_key": anchor["horizon_key"],
            "entry_date": anchor["entry_date"], "signal_index": 30,
            "direction": anchor["direction"], "d": d, "atr_pct": atr, "adv_dollars": 5e7,
            "baseline": baseline, "cells": cells,
            "moved_by": moved if moved is not None else {key: "floor" for key in cells},
            "newly_admitted": {key: baseline is None and cells[key] is not None for key in cells}}


def lifted_band_rows(lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021,
                     moved="floor"):
    """n_tickers * per_ticker paired rows. The baseline alternates win (+2R)
    and loss (-1R); each cell keeps the outcome and adds lifts[key], plus
    +jitter on even trades and -jitter on odd ones."""
    rows = []
    for t in range(n_tickers):
        for k in range(per_ticker):
            ticker, date = f"T{t:02d}", f"{year}-{k + 1:02d}-15"
            outcome, base_r = ("win", 2.0) if k % 2 == 0 else ("loss", -1.0)
            wobble = jitter if k % 2 == 0 else -jitter
            cells = {key: band_record(ticker, date, outcome, base_r + lift + wobble, moved=moved)
                     for key, lift in lifts.items()}
            rows.append(band_row(band_record(ticker, date, outcome, base_r, moved=None), cells,
                                 moved={key: moved for key in lifts}))
    return rows


def census_row(moved=("floor", "floor", "floor"), *, in_baseline=True, in_cell=(True, True, True),
               newly=(False, False, False), dropped=(None, None, None),
               size_zero=(False, False, False), reversal=None, d=1.0, atr=4.0, ticker="T00",
               date="2021-01-15", life_end="2021-02-22", horizon="4w", direction="bullish"):
    return {"arm": "K", "ticker": ticker, "horizon_key": horizon, "entry_date": date,
            "signal_index": 30, "direction": direction, "d": d, "atr_pct": atr,
            "adv_dollars": 5e7, "in_baseline": in_baseline, "life_end_date": life_end,
            "in_cell": dict(zip(KEYS, in_cell)), "moved_by": dict(zip(KEYS, moved)),
            "newly_admitted": dict(zip(KEYS, newly)), "dropped": dict(zip(KEYS, dropped)),
            "size_zero": dict(zip(KEYS, size_zero)),
            "reversal": None if reversal is None else dict(zip(KEYS, reversal))}


# --- constants and the stratum -----------------------------------------------------------

def test_the_frozen_block():
    assert funnel.FOLD_TRAIN == ("2018-06-01", "2022-12-31")
    assert funnel.VALIDATION == ("2024-01-01", "2025-12-31")
    assert funnel.FOLD_YEARS == (2021, 2022, 2023)
    assert funnel.FOLD_2023 == ("2023-01-01", "2023-12-31")
    assert (funnel.MIN_FOLD_N, funnel.MIN_POSITIVE_FOLDS) == (30, 2)
    assert (funnel.MDE_CEILING_R, funnel.MDE_POWER) == (0.10, 0.80)
    assert (funnel.CLUSTER, funnel.INSTRUMENT, funnel.DATA_SOURCE) == ("week", "v1", "alpaca")
    assert funnel.HOLM_ALPHA == 0.05
    assert PLATEAU_TOLERANCE_R == 0.03          # reused unchanged (index § Global Constraints)


def test_floor_moved_keeps_only_the_floor_stratum():
    rows = (lifted_band_rows({"k1": 0.3}, n_tickers=2, moved="floor")
            + lifted_band_rows({"k1": 0.3}, n_tickers=2, moved="untouched")
            + lifted_band_rows({"k1": 0.3}, n_tickers=2, moved="ceiling"))
    assert len(funnel.floor_moved(rows, "k1")) == 8
    assert all(r["moved_by"]["k1"] == "floor" for r in funnel.floor_moved(rows, "k1"))


# --- Stage -1 ------------------------------------------------------------------------------

def test_stage_minus1_reachable_cells_and_counts():
    rows = [census_row(("floor", "floor", "floor"), ticker="T01"),
            census_row(("untouched", "floor", "floor"), ticker="T02", d=3.5),
            census_row(("untouched", "untouched", "floor"), ticker="T03", d=4.5),
            census_row(("floor", "floor", "floor"), in_baseline=False, newly=(True, True, True),
                       ticker="T04", d=0.8),
            census_row(("floor", "floor", "floor"), in_cell=(False, False, False),
                       dropped=("band_rr_drop",) * 3, ticker="T05", d=1.5),
            census_row(("ceiling", "ceiling", "untouched"), ticker="T06", d=9.0),
            census_row((None, None, None), ticker="T07", reversal=(False, True, True))]
    out = funnel.stage_minus1(rows, "K")
    assert out["verdict"] == "REACHABLE" and out["reachable_cells"] == [0.75, 1.0, 1.5]
    k1 = out["totals"]["cells"]["k1"]
    assert (k1["floor"], k1["ceiling"], k1["untouched"]) == (3, 1, 1)
    assert (k1["newly_admitted"], k1["band_rr_drop"], k1["band_no_target"]) == (1, 1, 0)
    assert k1["removed"] == 1 and k1["reversal"] == 1 and k1["baseline_stop_exits"] == 1
    assert out["totals"]["plans_today"] == 6
    assert out["totals"]["arm_s_overlap"] == 2          # 2% < d <= 2 x 4%: T02 (3.5) and T03 (4.5)
    assert out["totals"]["atr_buckets"] == {"4.0-4.5": 7}
    assert set(out["by_stratum"]) == {"4w/bullish"}


def test_a_cell_with_no_floor_moved_plan_is_refused():
    rows = [census_row(("untouched", "floor", "floor")), census_row(("ceiling", "floor", "floor"))]
    out = funnel.stage_minus1(rows, "R")
    assert out["cell_verdicts"]["k0.75"] == "refused:zero-diff"
    assert out["reachable_cells"] == [1.0, 1.5]
    assert out["identical_adjacent"] == [["k1", "k1.5"]]


def test_zero_floor_moved_anywhere_closes_the_arm():
    out = funnel.stage_minus1([census_row(("untouched",) * 3)], "K")
    assert out["verdict"] == "refused:zero-diff" and out["reachable_cells"] == []


def test_concurrency_counts_open_band_plans_per_business_day(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 1.0)        # one 1% slot
    rows = [census_row(ticker="A", date="2021-01-04", life_end="2021-01-06"),
            census_row(ticker="B", date="2021-01-05", life_end="2021-01-07"),
            census_row(ticker="C", date="2021-01-05", life_end="2021-01-05",
                       moved=(None, None, None))]
    conc = funnel.stage_minus1(rows, "K")["totals"]["cells"]["k1"]["concurrency"]
    assert conc["max"] == 2                              # Jan 5 and 6: A and B
    assert conc["heat_slots"] == 1.0 and conc["days_over_heat_slots"] == 2


# --- Stage 0 -------------------------------------------------------------------------------

def test_stage0_powered_cells_and_the_disclosed_unpaired_count():
    rows = lifted_band_rows({key: 0.3 for key in KEYS})
    rows.append(band_row(None, {key: band_record("T99", "2021-06-15", "win", 2.0)
                                for key in KEYS}))
    out = funnel.stage0(rows, "K")
    assert out["verdict"] == "POWERED" and out["powered_cells"] == [0.75, 1.0, 1.5]
    cell = out["cells"][1]
    assert (cell["cell"], cell["paired_n"], cell["newly_admitted_n"]) == ("k1", 80, 1)
    assert cell["mde_r"] == pytest.approx(0.0, abs=1e-9)   # a constant lift has no spread


def test_stage0_refuses_a_cell_over_the_mde_ceiling_but_keeps_the_others():
    rows = lifted_band_rows({"k0.75": 0.3, "k1": 0.3, "k1.5": 0.3})
    for r in rows:
        r["cells"]["k1.5"]["r_multiple"] += 6.0 if r["entry_date"][5:7] in ("01", "03") else -6.0
    out = funnel.stage0(rows, "K")
    assert out["powered_cells"] == [0.75, 1.0]
    assert out["verdict"] == "POWERED"


def test_stage0_with_nothing_paired_is_underpowered():
    rows = [band_row(None, {key: band_record("T01", "2021-02-15", "win", 2.0) for key in KEYS})]
    out = funnel.stage0(rows, "K")
    assert out["verdict"] == "UNDERPOWERED" and out["powered_cells"] == []


def test_stage0_reads_only_the_floor_moved_stratum():
    rows = lifted_band_rows({key: 0.3 for key in KEYS}, moved="untouched")
    assert funnel.stage0(rows, "K")["verdict"] == "UNDERPOWERED"


# --- Stage 1 -------------------------------------------------------------------------------

def _stage1(lifts, **kw):
    return funnel.stage1(lifted_band_rows(lifts), "K", n_resamples=N, **kw)


def test_stage1_picks_the_highest_plateau_cell():
    out = _stage1({"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29})
    assert out["verdict"] == "SELECTED" and out["selected"] == {"cell": "k1", "k": 1.0}


def test_stage1_an_edge_cell_is_adoptable_with_its_one_neighbour():
    out = _stage1({"k0.75": 0.30, "k1": 0.32, "k1.5": 0.20})
    # k1 is not a plateau (k1.5 is 0.12 away); k0.75's only neighbour is 0.02 away
    assert out["selected"] == {"cell": "k0.75", "k": 0.75}


def test_stage1_a_spike_does_not_proceed():
    out = _stage1({"k0.75": 0.10, "k1": 0.50, "k1.5": 0.10})
    assert out["verdict"] == "NO_ELIGIBLE_CELL" and out["selected"] is None


def test_stage1_a_cell_failing_a_clause_is_not_selectable():
    out = _stage1({"k0.75": -0.30, "k1": -0.31, "k1.5": -0.29})
    assert out["verdict"] == "NO_ELIGIBLE_CELL"
    assert not any(cell["eligible"] for cell in out["cells"])


def test_stage1_only_powered_cells_are_candidates_but_all_cells_are_neighbours():
    out = _stage1({"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29}, cells=(0.75, 1.5))
    assert out["selected"] == {"cell": "k0.75", "k": 0.75}
    assert [c["candidate"] for c in out["cells"]] == [True, False, True]


def test_stage1_a_tie_goes_to_the_smaller_floor():
    out = _stage1({"k0.75": 0.30, "k1": 0.30, "k1.5": 0.30})
    assert out["selected"] == {"cell": "k0.75", "k": 0.75}


def test_stage1_ignores_rows_outside_the_floor_stratum():
    rows = (lifted_band_rows({"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29})
            + lifted_band_rows({"k0.75": -3.0, "k1": -3.0, "k1.5": -3.0}, year=2022,
                               moved="untouched"))
    out = funnel.stage1(rows, "K", n_resamples=N)
    assert out["selected"] == {"cell": "k1", "k": 1.0}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_atr_band_funnel.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.atr_band_funnel'`.

- [ ] **Step 3: Write `swingbot/core/backtesting/atr_band_funnel.py`** (Stages −1..1; V191-16 appends below the Stage 1 block)

```python
"""v191 ATR-band funnel: Stage -1 census verdicts and Stages 0-3 over
atr_band_replay rows, for one target arm at a time.

Every constant is PRE-REGISTERED (spec § Gate; plan index § Global
Constraints). The gate is the v92 harvest gate (acceptance_harvest), scored
on the FLOOR-MOVED STRATUM ALONE (spec § Not a re-run): a pooled pass the
floor-moved stratum does not carry is a fail. Untouched and ceiling strata
are reported, never selected on. Changing a constant here is a new
pre-registration, not a tuning step.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market.atr_band import (MOVED_CEILING, MOVED_FLOOR, MOVED_UNTOUCHED,
                                           REASON_NO_TARGET, REASON_RR_DROP)

from .acceptance import (BOOTSTRAP_RESAMPLES, CLOSED, delta_expectancy_r, mde_paired,
                         project_target_n, render_json)
from .acceptance_exit_funnel import ELIGIBILITY_CLAUSES, arm_trades
from .acceptance_harvest import evaluate_harvest
from .atr_band_replay import FLOOR_KNOB, K_STEPS, REFERENCE_ACCOUNT, cell_key
from .backtest_wf import PLATEAU_TOLERANCE_R, plateau_report

FOLD_TRAIN = ("2018-06-01", "2022-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
FOLD_YEARS = (2021, 2022, 2023)
FOLD_2023 = ("2023-01-01", "2023-12-31")
MIN_FOLD_N = 30
MIN_POSITIVE_FOLDS = 2
MDE_CEILING_R = 0.10
MDE_POWER = 0.80
CLUSTER = "week"
INSTRUMENT = "v1"
DATA_SOURCE = "alpaca"
HOLM_ALPHA = 0.05
A_BUCKET_PCT = 0.5
#: v139 arm S's ceiling range started past 2% (spec § Not a re-run).
ARM_S_FLOOR_PCT = 2.0
MOVED = (MOVED_FLOOR, MOVED_CEILING, MOVED_UNTOUCHED)


def floor_moved(rows, key) -> list:
    """The decision stratum: rows whose stop the floor moved at this cell."""
    return [r for r in rows if r["moved_by"].get(key) == MOVED_FLOOR]


def _keys(cells) -> list:
    return [cell_key(k) for k in cells]


# --- Stage -1 (plans only) -------------------------------------------------------

def _bucket(a) -> str:
    lo = math.floor(a / A_BUCKET_PCT) * A_BUCKET_PCT
    return f"{lo:.1f}-{lo + A_BUCKET_PCT:.1f}"


def _row_id(row) -> tuple:
    return row["ticker"], row["horizon_key"], row["entry_date"], row["direction"]


def _in_cell(rows, key) -> list:
    return [r for r in rows if r["in_cell"][key]]


def _band_days(rows, key) -> Counter:
    per_day: Counter = Counter()
    for r in _in_cell(rows, key):
        if r["moved_by"][key] is not None:
            per_day.update(pd.bdate_range(r["entry_date"], r["life_end_date"]))
    return per_day


def _concurrency(rows, key) -> dict:
    """Open band plans per business day, signal date to the horizon's hold.
    heat_slots: how many full-budget candidates PORTFOLIO_HEAT_CAP_PCT admits."""
    slots = float(config.PORTFOLIO_HEAT_CAP_PCT) / float(REFERENCE_ACCOUNT["risk_pct"])
    counts = sorted(_band_days(rows, key).values())
    if not counts:
        return {"max": 0, "p95": 0.0, "heat_slots": slots, "days_over_heat_slots": 0}
    return {"max": counts[-1], "p95": float(np.percentile(counts, 95)), "heat_slots": slots,
            "days_over_heat_slots": sum(1 for c in counts if c > slots)}


def _cell_census(rows, key) -> dict:
    present = _in_cell(rows, key)
    moved = Counter(r["moved_by"][key] for r in present)
    dropped = Counter(r["dropped"][key] for r in rows if r["dropped"][key])
    reversals = [r["reversal"] for r in rows if r["reversal"] is not None]
    return {"plans": len(present), **{name: moved.get(name, 0) for name in MOVED},
            "newly_admitted": sum(1 for r in rows if r["newly_admitted"][key]),
            "removed": sum(1 for r in rows if r["in_baseline"] and not r["in_cell"][key]),
            REASON_RR_DROP: dropped.get(REASON_RR_DROP, 0),
            REASON_NO_TARGET: dropped.get(REASON_NO_TARGET, 0),
            "band_size_zero": sum(1 for r in present if r["size_zero"][key]),
            "baseline_stop_exits": len(reversals),
            "reversal": sum(1 for rev in reversals if rev.get(key)),
            "concurrency": _concurrency(rows, key)}


def _arm_s_overlap(rows) -> int:
    return sum(1 for r in rows if r["in_baseline"] and r["d"] is not None
               and r["atr_pct"] is not None
               and ARM_S_FLOOR_PCT < r["d"] <= 2.0 * r["atr_pct"])


def _atr_buckets(rows) -> dict:
    buckets = Counter(_bucket(r["atr_pct"]) for r in rows if r["atr_pct"] is not None)
    return dict(sorted(buckets.items(), key=lambda kv: float(kv[0].split("-")[0])))


def _census_table(rows, cells) -> dict:
    return {"plans_today": sum(1 for r in rows if r["in_baseline"]),
            "arm_s_overlap": _arm_s_overlap(rows), "atr_buckets": _atr_buckets(rows),
            "atr_missing": sum(1 for r in rows if r["atr_pct"] is None),
            "cells": {key: _cell_census(rows, key) for key in _keys(cells)}}


def _strata(rows) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(f"{row['horizon_key']}/{row['direction']}", []).append(row)
    return out


def _floor_sets(rows, cells) -> dict:
    return {key: frozenset(_row_id(r) for r in _in_cell(rows, key)
                           if r["moved_by"][key] == MOVED_FLOOR) for key in _keys(cells)}


def _identical_adjacent(sets) -> list:
    keys = list(sets)
    return [[a, b] for a, b in zip(keys, keys[1:]) if sets[a] == sets[b]]


def stage_minus1(census_rows, arm, cells=K_STEPS) -> dict:
    """The census verdict, before any outcome is read. A cell whose floor
    moves no plan is refused:zero-diff (it has no decision stratum); the arm
    is REACHABLE when any cell is."""
    cells = tuple(float(k) for k in cells)
    sets = _floor_sets(census_rows, cells)
    verdicts = {key: "REACHABLE" if sets[key] else "refused:zero-diff" for key in sets}
    reachable = [k for k in cells if verdicts[cell_key(k)] == "REACHABLE"]
    return {"stage": -1, "arm": arm, "verdict": "REACHABLE" if reachable else "refused:zero-diff",
            "reachable_cells": reachable, "cell_verdicts": verdicts,
            "cells": _keys(cells), "totals": _census_table(census_rows, cells),
            "by_stratum": {name: _census_table(rows, cells)
                           for name, rows in sorted(_strata(census_rows).items())},
            "identical_adjacent": _identical_adjacent(sets)}


# --- Stage 0 -------------------------------------------------------------------------

def _days(window) -> int:
    start, end = (dt.date.fromisoformat(x) for x in window)
    return (end - start).days + 1


def _paired(rows, key) -> list:
    return [r for r in rows if r["baseline"] is not None and r["cells"][key] is not None]


def _mde_cell(rows, k) -> dict:
    key = cell_key(k)
    stratum = floor_moved(rows, key)
    paired = _paired(stratum, key)
    baseline, component = arm_trades(paired, key)
    observed_n = sum(1 for t in baseline if t.outcome in CLOSED)
    target_n = project_target_n(observed_n=observed_n, observed_days=_days(FOLD_TRAIN),
                                target_days=_days(VALIDATION))
    mde = mde_paired(baseline, component, delta_expectancy_r, observed_n=observed_n,
                     target_n=target_n, power=MDE_POWER, cluster=CLUSTER) if observed_n else None
    return {"cell": key, "k": float(k), "stratum_n": len(stratum), "paired_n": len(paired),
            "newly_admitted_n": sum(1 for r in stratum if r["newly_admitted"][key]),
            "observed_n": observed_n, "target_n": target_n, "mde_r": mde,
            "powered": mde is not None and mde <= MDE_CEILING_R}


def stage0(rows, arm, cells=K_STEPS) -> dict:
    """Paired dExpR MDE on fold-train, per cell, on the floor-moved stratum.
    A cell over the ceiling is refused; the arm is POWERED when any cell is."""
    out = [_mde_cell(rows, k) for k in cells]
    powered = [cell["k"] for cell in out if cell["powered"]]
    return {"stage": 0, "arm": arm, "verdict": "POWERED" if powered else "UNDERPOWERED",
            "powered_cells": powered, "mde_ceiling_r": MDE_CEILING_R, "power": MDE_POWER,
            "cluster": CLUSTER, "cells": out}


# --- Stage 1 -------------------------------------------------------------------------

def _selection_cell(rows, k, n_resamples, seed) -> dict:
    key = cell_key(k)
    baseline, component = arm_trades(floor_moved(rows, key), key)
    result = evaluate_harvest(baseline, component, stage="walkforward",
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    eligible = all(result.clause(name).verdict == "PASS" for name in ELIGIBILITY_CLAUSES)
    return {"cell": key, "k": float(k), "n_baseline": len(baseline),
            "n_component": len(component), "eligible": eligible,
            "delta_expr": delta_expectancy_r(baseline, component), "gate": render_json(result)}


def _plateau(table, k) -> bool:
    """plateau_report over the whole grid; a neighbour with no dExpR is a spike."""
    grid = list(table)
    i = grid.index(k)
    window = [grid[j] for j in (i - 1, i, i + 1) if 0 <= j < len(grid)]
    if any(table[c]["delta_expr"] is None for c in window):
        return False
    values = [table[c]["delta_expr"] for c in grid]
    return plateau_report(FLOOR_KNOB, grid, values, k)["is_plateau"]


def stage1(rows, arm, cells=K_STEPS, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """Fold-train selection over k. Candidates are `cells` (Stage 0's powered
    cells); every grid cell is a neighbour. Winner: the highest point dExpR
    among candidates whose clauses 1-3 pass and that sit on a plateau."""
    candidates = {float(k) for k in cells}
    table = {float(k): _selection_cell(rows, k, n_resamples, seed) for k in K_STEPS}
    for k, cell in table.items():
        cell["candidate"] = k in candidates
        cell["plateau"] = _plateau(table, k)
    pool = [c for c in table.values() if c["candidate"] and c["eligible"] and c["plateau"]]
    selected = None
    if pool:
        best = max(pool, key=lambda cell: cell["delta_expr"])
        selected = {"cell": best["cell"], "k": best["k"]}
    return {"stage": 1, "arm": arm, "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "tolerance_r": PLATEAU_TOLERANCE_R,
            "cells": list(table.values())}
```

Notes for the implementer: `plateau_report` is called with the whole grid so its `neighbors` dict stays the familiar shape; the pre-check in `_plateau` only guards `None` arithmetic. `mde_paired` keeps its default 10 000 resamples (`stage0` takes no `n_resamples` by contract); the synthetic tests stay fast because 80 rows bootstrap in well under a second. `test_stage0_refuses_a_cell_over_the_mde_ceiling...` gives k1.5 ±6R noise that differs by entry week (the bootstrap cluster), so its paired SE, hence its MDE, is far above 0.10R while k0.75 and k1 stay at zero spread.

- [ ] **Step 4: Run the tests and the gates**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_atr_band_funnel.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; complexity gate passes (`_cell_census` is the largest new function, a flat dict build).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/atr_band_funnel.py tests/backtesting/test_atr_band_funnel.py
git commit -m "feat(backtest): v191 funnel stages -1..1 -- census verdict, paired dExpR MDE, plateau selection on the floor-moved stratum

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

