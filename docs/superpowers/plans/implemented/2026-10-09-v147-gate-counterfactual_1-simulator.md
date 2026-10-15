# v147 Gate counterfactual: Part 1, simulator and TRAIN row recorder

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V147-2:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_1-simulator.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md)
**Index:** [`2026-10-09-v147-gate-counterfactual_0-index.md`](2026-10-09-v147-gate-counterfactual_0-index.md): Global Constraints, Parallelisation, the task ledger and the shared gate-row shape live there and bind every task below.

Scope of this part: V147-1 (verify the block-point enumeration from code), V147-2 (`simulate_blocked` core), V147-3 (truncated plan build with pinned overrides), V147-4 (TRAIN gate-row recorder module). Nothing here touches a gate, a scan path or a replay; the hooks that call these functions are Part 2 and Part 3.

**Additive symbols beyond the ledger (consumed by Part 3, no shared contract changed):** V147-3 also creates `UnpinnableBuild(RuntimeError)`, `PIN_KEYS = ("stop_mult", "tp2_r", "time_stop_days")` and `pinned_scan_params(strategy, *, plan=None, params=None) -> dict`, which fixes the shape of `BlockedCandidate.scan_params`: `{"stop_mult", "tp2_r", "time_stop_days", "params": dataclasses.asdict(ScanParams) | None}`. V147-9's `record_rejection` should build `scan_params` through it.

**Instrument note (read before V147-2):** the spec's test list asks for "a gap through the stop yields `cf_r < -1`". `exit_sim`'s v2 walk books every pre-TP1 stop at the stop price (`_pre_tp1_phase`, `round(-1.0, 3)`), so a gap below the stop is exactly `-1.0` and no path of `simulate_exit` returns less. The simulator must call `simulate_exit` unchanged (spec § Walk), so V147-2 pins the instrument's real behaviour (`cf_r == -1.0`, identical to the replay call) instead of an assertion that cannot pass. Both arms share the instrument, so the blocked − taken difference is unaffected; the controller decides whether a gap-fill instrument change is a later spec.

---

# Phase 1: Simulator

### Task V147-1: Enumerate block points from code

**Model:** sonnet — reading code paths and writing a table; no code change, but the judgement "is this one of the three gates" needs care.

**Cross-plan (audit 2026-10-10):** other plans add block reasons that are **not** one of v147's three gates. If present at HEAD, add each to the Out-of-scope table (rows O11, O12, ...) with its line number: v135's `headroom` reject (`git grep -n "headroom" -- swingbot/core/scanning swingbot/core/backtesting/backtest_scenarios.py`), and v139's `stop_beyond_confluence_ceiling` and `risk_sizing` reasons (`git grep -n "stop_beyond_confluence_ceiling\|\"risk_sizing\"" -- swingbot`). Reason: they are separate gates from separate plans; the report keeps them out of every v147 cell (`cell_key` maps any unknown reason to `"other"`, which is not in `CELLS`, V147-13). If an L4/L6 hook would record them as `plan_rejected`, say so in the row: the rows are stored, never pooled into `risk_cap`.

**Files:**
- Create: `docs/superpowers/results/2026-10-09-v147-block-points.md`

The index's block-point table (L1–L6, T1–T3, O1–O8) is the starting point, not the contract. This task re-derives it from the code at implementation time, so every later hook task (V147-5, V147-6, V147-10) works from a list that was checked against HEAD. It writes no Python.

**Rules for this task:** do not grep for any closed RS, earnings-blackout or dry-up knob name (a PreToolUse hook blocks it, and the spec forbids sweeping them); read the dry-up gate through `_dryup_blocked` and `gates.pullback_dryup_blocks`, the RS gate through `rs_verdict` / `_rs_blocked`.

- [ ] **Step 1: List every reject or skip in the three live paths**

Run (one batched call):

```bash
git grep -n "rs_blocked\|plan_v2_rejected\|_count_compression_reject\|_count_plan_none\|sizing_blocked\|already_emitted\|_dryup_blocked\|stored_only" -- swingbot/core/scanning
git grep -n "Rejected(" -- swingbot/core/scanning
git grep -n "veto_bullish_for\|apply_regime_gate\|REGIME_GATES_ENABLED\|kill_switch\|heat_cap\|cluster_cap\|_stamp_risk_flags" -- swingbot/core/scanning swingbot/core/edge
git grep -n "_REQUIREMENT_STAGE" -- swingbot/core/scanning/short_funnel.py
```

Expected: hits in `strategy_pass.py` (`_emit_signal`, `_count_compression_reject`, `_count_plan_none`), `scan_run.py` (`_sync_run_scan` RS block and `plan_v2_rejected` drop, `_skip_rejected_plan`), `qualify.py` (`Rejected(item, "rs", ...)`, `Rejected(item, "plan", ...)`), `analyze.py` (`_reject_plan`, `veto_bullish_for`), `short_run.py` (`_qualified_items`, `_stamp_risk_flags`).

- [ ] **Step 2: Read each site and classify it**

Read only the line ranges the hits point at (`sed -n '<a>,<b>p' <file>`), not whole files. For each site decide:

1. Does it **drop** the candidate (`continue` / `return` / `Rejected`) or only **flag** it (size 0, a warning, a counter beside a kept item)? Flags are out of scope.
2. If it drops: is the deciding rule the RS gate, the plan-rejection gate (`no_qualifying_target`, `risk_cap`) or the compression/earnings decision (`decide_compression_entry`)? Only those three are covered.
3. Is it reached from the **live** scan, from the **TRAIN** replays (`backtest_scenarios.replay_scenarios`, `arms/strategy_engine.StrategyEngine._candidate_plan`), or both?

Confirm in particular, and note the line numbers you saw:
- `scan_run._sync_run_scan` drops a rejected plan only when `config.PLAN_ENGINE_V2 == "on"` (under `shadow` a rejected plan is not dropped, so it is not a block).
- The RS block in `_sync_run_scan` runs only under `config.RS_GATE`; a `None` RS value is `exempt`, not `block`.
- `qualify_short_item` is also called from `scanning/outlook_run.py`, `scanning/scan_replay.py` and `backtesting/arms/short_universe_engine.py` (run `git grep -n "qualify_short_item" -- swingbot`), so the live hook belongs in `short_run._qualified_items`, never inside `qualify.py`.
- `veto_bullish_for` (dead-cat-bounce veto, `analyze.py`) runs inside `_scan_one` scenario building: the bullish scenario is never built, so there is no candidate to record. Classify it out of scope with that reason.
- The regime gate (`apply_regime_gate` / `REGIME_GATES_ENABLED`): find whether it drops a candidate or only annotates; record what you find with the reason.
- `StrategyEngine._compression_stamp` returns `not_pit_member` before the decision: that is the research universe mask, not the gate, so it is excluded.

- [ ] **Step 3: Write the results doc**

Create `docs/superpowers/results/2026-10-09-v147-block-points.md` with this structure, filling the `Line` column with the line numbers seen at HEAD and adding a row for every further site found in Step 2:

```markdown
# v147 block-point enumeration

**Plan:** [`2026-10-09-v147-gate-counterfactual_0-index.md`](../plans/2026-10-09-v147-gate-counterfactual_0-index.md)
**Verified at:** <git rev-parse --short HEAD> on <date>

Every place a candidate is thrown away in the live scan or the TRAIN replays,
and whether v147 records it. Covered = one of the three gates in the spec
(RS, plan rejected, compression/earnings).

## Covered

| # | Path | File:line | Site | `gate` / `reason` | Population | Hook task |
|---|---|---|---|---|---|---|
| L1 | strategy | `strategy_pass.py:<n>` | `_emit_signal` → `_rs_blocked` | `rs` / `rs_blocked` | live | V147-10 |
| L2 | strategy | `strategy_pass.py:<n>` | `_emit_signal` → compression reject | `compression` / decide reason (`earnings_*` included) | live | V147-10 |
| L3 | confluence | `scan_run.py:<n>` | `_sync_run_scan` RS block (`config.RS_GATE`) | `rs` / `rs_blocked` | live | V147-10 |
| L4 | confluence | `scan_run.py:<n>` | `_sync_run_scan` `plan_v2_rejected` drop (`PLAN_ENGINE_V2 == "on"`) | `plan_rejected` / `no_qualifying_target`, `risk_cap` | live | V147-10 |
| L5 | short lane | `short_run.py:<n>` | `_qualified_items` sees `Rejected(stage="rs")` | `rs` / `rs_blocked` | live | V147-10 |
| L6 | short lane | `short_run.py:<n>` | `_qualified_items` sees `Rejected(stage="plan")` | `plan_rejected` / reason | live | V147-10 |
| T1 | TRAIN strategy | `arms/strategy_engine.py:<n>` | `_candidate_plan` compression reject (decide reasons only) | `compression` | TRAIN, in-sample | V147-6 |
| T2 | TRAIN confluence | `backtest_scenarios.py:<n>` | `replay_scenarios` `plan is None` | `plan_rejected` / `no_qualifying_target` | TRAIN | V147-5 |
| T3 | TRAIN confluence | `backtest_scenarios.py:<n>` | shadow in `_replay_ticker` after `simulate_exit` | `plan_rejected` / `risk_cap` | TRAIN shadow, over-cap | V147-5 |

## Out of scope

| # | Path | File:line | Site | Why not recorded |
|---|---|---|---|---|
| O1 | strategy | `strategy_pass.py:<n>` | `plan is None` for non-compression strategies | the constructor found no geometry; not one of the three gates; nothing to simulate |
| O2 | strategy | `strategy_pass.py:<n>` | `risk_sizing_ok(plan)` false (`sizing_blocked`) | v104 configuration fail-closed guard, not a quality gate |
| O3 | all | `strategy_pass.py:<n>`, `scan_run.py:<n>` | dedup (`already_emitted`), cooldown | "already have this trade" |
| O4 | strategy / confluence | `strategy_pass.py:<n>`, `analyze.py:<n>` | pullback dry-up | inactive since v122 (its scope knob defaults off, so the filter is a no-op) |
| O5 | confluence / short | `short_funnel.py:<n>` | requirement rejects (`_REQUIREMENT_STAGE`) | out by the spec |
| O6 | confluence | `scan_run.py:<n>`, `short_run.py:<n>` | heat cap, correlated-cluster cap, kill switch, `_stamp_risk_flags` | flagged, never dropped (size 0) |
| O7 | strategy | `strategy_pass.py:<n>` | masked strategies (`_goes_live` false → `stored_only`) | stored, not rejected |
| O8 | TRAIN strategy | `arms/strategy_engine.py:<n>` | plan None, `_skipped` not_triggered | O1's twin; fill-time cancels are taken-arm `no-fill` rows |
| O9 | confluence | `analyze.py:<n>` | dead-cat-bounce veto (`veto_bullish_for`) | the bullish scenario is never built inside `_scan_one` (a `map_tickers` worker); no candidate exists to record |
| O10 | confluence | `scan_run.py:<n>` | regime gate | <what Step 2 found> |
| O11 | confluence | `<file>:<n>` | v135 `headroom` reject (only if present at HEAD) | a v135 gate, not one of the three; `cell_key` -> `"other"`, never pooled into `risk_cap` |
| O12 | confluence / strategy | `<file>:<n>` | v139 `stop_beyond_confluence_ceiling` / `risk_sizing` (only if present at HEAD) | v139 gates, not one of the three; `cell_key` -> `"other"`, never pooled into `risk_cap` |
```

Drop O11 / O12 when the grep finds nothing (those plans not merged); never leave a `<n>` placeholder.

If Step 2 finds a site that **drops** a candidate under one of the three gates and is not in the Covered table, stop and report it to the controller (it changes V147-10's hook list) instead of adding it silently.

- [ ] **Step 4: Verify the doc**

Run: `grep -c "^| [LTO][0-9]" docs/superpowers/results/2026-10-09-v147-block-points.md`
Expected: at least `19` (L1–L6, T1–T3, O1–O10), and `grep -n "<n>" docs/superpowers/results/2026-10-09-v147-block-points.md` prints nothing (every line number filled).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-10-09-v147-block-points.md
git commit -m "docs(v147): verified block-point enumeration (V147-1)"
```

### Task V147-2: `simulate_blocked` core: signal bar, price basis, walk, status

**Model:** opus — the one instrument every verdict rests on: no-lookahead, the one population rule and the price-basis re-anchor must be exactly right.

**Files:**
- Create: `swingbot/core/backtesting/gate_counterfactual.py`
- Create: `tests/backtesting/test_gate_counterfactual.py`

Creates for later tasks (ledger): `BlockedCandidate`, `CounterfactualResult`, `CF_STATUSES`, `simulate_blocked(candidate, bars, *, last_session=None)`, `result_from_exit(exit_result)`, `REANCHOR_TOLERANCE = 0.005`, `bars_sha256(frame)`. This task handles a candidate that **carries** a plan (`risk_cap`, stored plans); a candidate without one is `no-plan` here, and V147-3 adds the truncated rebuild behind the same `_plan_for` seam.

Symbols used, all verified at HEAD: `exit_sim.simulate_exit` (`swingbot/core/planning/exit_sim.py:625`), `exit_sim._not_triggered` (`:76`), `exit_sim._no_trade` (`:354`), `ExitResult` (`:60`), `plan_types.plan_to_dict` / `plan_from_dict` (`plan_types.py:185/192`), `strategy_types.HORIZONS` (`max_holding_days`, `"2w"` = 14), `tests.helpers.make_ohlcv` (`tests/helpers.py:10`, accepts `(o, h, l, c)` tuples, business-day index).

Design points the tests pin:
- `simulate_exit(used, signal_index, plan, scale_out=True)`: the replays' exact call (`arms/strategy_engine.py` `iter_trades`, `backtest_scenarios._replay_ticker`), `max_holding_days` left `None`.
- The walk gets `frame.iloc[:signal_index + bars_needed(plan) + 1]`, where `bars_needed` = the horizon's `max_holding_days` (market entry) or `expiry_bars + max_holding_days` (stop/limit entry). That slice holds every bar the walk can read, so appending later bars changes neither `cf_r` nor `bars_sha256`, and the hash is of the exact slice used. Fewer bars than that → `cf_status = "pending"` (the resolver's grace counter handles it; TRAIN caches always run past the window).
- `not_triggered` → `no-fill`, `no_trade` (risk per share <= 0) → `no-plan`; neither carries an `r`. `win` = TP1 touched (`outcome == "win"` or a `tp1` leg).
- Signal bar: exact tz-naive date match after dropping bars dated after `last_session`; no match → `no-data`.
- Price basis: `ratio = cache close on signal_date / candidate.signal_close`; `|ratio − 1| > 0.005` multiplies every stored plan and scenario price level by `ratio` and sets `reanchored = True`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_gate_counterfactual.py`:

```python
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_gate_counterfactual.py`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.gate_counterfactual'`.

- [ ] **Step 3: Implement the module**

Create `swingbot/core/backtesting/gate_counterfactual.py`:

```python
"""v147: what a candidate thrown away by a gate would have done.

One pure function, ``simulate_blocked(candidate, bars)``, shared unchanged by
the TRAIN recorders and the live resolver. It finds the signal bar by exact
date, re-anchors stored prices when the bar basis moved (split/dividend), takes
the stored plan (V147-3 adds the truncated rebuild), and walks it through
``exit_sim.simulate_exit(..., scale_out=True)`` -- the exact call the replays
make (``arms/strategy_engine.py``, ``backtest_scenarios.py``), with
``max_holding_days`` left None so it resolves to the horizon's value.

NO-LOOKAHEAD: the plan reads ``bars.iloc[:signal_index + 1]`` only; the walk
reads bars strictly after the signal bar (simulate_exit's own contract).
``not_triggered`` is ``no-fill`` and never a 0R trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_types import TradePlanV2, plan_from_dict, plan_to_dict

log = logging.getLogger(__name__)

CF_STATUSES = ("pending", "filled", "no-fill", "no-plan", "no-data")
REANCHOR_TOLERANCE = 0.005
OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
PLAN_PRICE_FIELDS = (
    "trigger_price", "entry_price", "stop_loss", "tp1", "tp2", "working_stop",
    "notified_stop", "acceptance_level", "acceptance_close_below",
    "limit_cancel_level", "runner_high_close", "first_seen_price",
)
SCENARIO_PRICE_FIELDS = ("entry", "market_price", "stop_loss", "take_profit", "target2_price")


@dataclass(frozen=True)
class BlockedCandidate:
    """One blocked candidate, as recorded at the gate (all prices in the signal-day basis)."""

    ticker: str
    gate: str
    reason: str | None
    source: str                      # "strategy" | "confluence" | "short_lane"
    strategy: str
    horizon: str
    direction: str
    signal_date: str                 # YYYY-MM-DD, the completed signal bar
    plan: dict | None = None         # plan_to_dict of a plan that existed at the gate
    scenario: dict | None = None     # scenario_to_dict, confluence / short lane
    scan_params: dict | None = None  # pinned overrides + ScanParams fields (V147-3)
    signal_close: float | None = None
    margin: float | None = None


@dataclass(frozen=True)
class CounterfactualResult:
    cf_status: str                   # one of CF_STATUSES
    cf_r: float | None               # None unless filled
    win: bool | None                 # None unless filled; True = TP1 touched
    exit_index: int | None
    last_bar_date: str | None
    bars_sha256: str | None
    reanchored: bool
    plan: dict | None


def result_from_exit(exit_result) -> tuple[str, float | None, bool | None]:
    """(cf_status, cf_r, win) of one ExitResult under the one population rule.

    ``not_triggered`` carries a placeholder r_total of 0.0 -- it is no-fill,
    never a 0R trade. ``no_trade`` (risk_per_share <= 0) means no valid plan."""
    if exit_result.outcome == "not_triggered":
        return "no-fill", None, None
    if exit_result.outcome == "no_trade":
        return "no-plan", None, None
    legs = exit_result.legs or []
    won = exit_result.outcome == "win" or any(leg.get("reason") == "tp1" for leg in legs)
    return "filled", float(exit_result.r_total), bool(won)


def bars_sha256(frame) -> str:
    """Reproducible hash of the exact OHLCV slice a resolution used."""
    columns = [c for c in OHLCV_COLUMNS if c in frame.columns]
    payload = frame[columns].to_csv(date_format="%Y-%m-%d", float_format="%.10g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _session_dates(frame) -> pd.Index:
    """The frame's bar dates as tz-naive YYYY-MM-DD strings."""
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    return index.strftime("%Y-%m-%d")


def _completed(bars, last_session: str | None):
    """Drop every bar after the last completed session (no-op when None)."""
    if last_session is None:
        return bars
    return bars.loc[np.asarray(_session_dates(bars) <= last_session)]


def _signal_index(frame, signal_date: str) -> int | None:
    """Positional index of the bar dated exactly signal_date; no nearest-bar fallback."""
    hits = np.flatnonzero(np.asarray(_session_dates(frame) == signal_date))
    return int(hits[0]) if len(hits) else None


def _reanchor_ratio(candidate: BlockedCandidate, frame, index: int) -> float | None:
    """cache close / stored close when they drift past REANCHOR_TOLERANCE, else None."""
    stored = candidate.signal_close
    if stored is None or not float(stored) > 0:
        return None
    ratio = float(frame["Close"].iloc[index]) / float(stored)
    return ratio if abs(ratio - 1.0) > REANCHOR_TOLERANCE else None


def _scaled(record: dict | None, fields: tuple, ratio: float) -> dict | None:
    if record is None:
        return None
    out = dict(record)
    for name in fields:
        if out.get(name) is not None:
            out[name] = float(out[name]) * ratio
    return out


def _rebased(candidate: BlockedCandidate, ratio: float | None) -> BlockedCandidate:
    """The candidate with every stored price level moved onto the cache's basis."""
    if ratio is None:
        return candidate
    return dataclasses.replace(
        candidate,
        plan=_scaled(candidate.plan, PLAN_PRICE_FIELDS, ratio),
        scenario=_scaled(candidate.scenario, SCENARIO_PRICE_FIELDS, ratio),
        signal_close=float(candidate.signal_close) * ratio,
    )


def bars_needed(plan: TradePlanV2) -> int:
    """Bars after the signal bar the walk can read: pending window + horizon hold."""
    hold = int(HORIZONS[plan.horizon_key]["max_holding_days"])
    return hold if plan.entry_type == "market" else int(plan.expiry_bars) + hold


def _last_date(frame) -> str | None:
    return str(_session_dates(frame)[-1]) if len(frame) else None


def _status_only(status: str, *, reanchored: bool = False, last_bar_date: str | None = None,
                 plan: dict | None = None) -> CounterfactualResult:
    return CounterfactualResult(status, None, None, None, last_bar_date, None, reanchored, plan)


def _outcome(frame, index: int, plan: TradePlanV2, reanchored: bool) -> CounterfactualResult:
    """Walk the plan, or ``pending`` while the bars it can read are not all in."""
    end = index + bars_needed(plan)
    if len(frame) - 1 < end:
        return _status_only("pending", reanchored=reanchored, last_bar_date=_last_date(frame),
                            plan=plan_to_dict(plan))
    used = frame.iloc[:end + 1]
    exit_result = simulate_exit(used, index, plan, scale_out=True)
    status, cf_r, win = result_from_exit(exit_result)
    return CounterfactualResult(status, cf_r, win, exit_result.exit_index, _last_date(used),
                                bars_sha256(used), reanchored, plan_to_dict(plan))


def _plan_for(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The stored plan as stored. V147-3 adds the truncated rebuild from ``window``."""
    if candidate.plan is not None:
        return plan_from_dict(candidate.plan)
    return None


def simulate_blocked(candidate: BlockedCandidate, bars, *,
                     last_session: str | None = None) -> CounterfactualResult:
    """What ``candidate`` would have done on ``bars`` (one ticker, daily OHLCV)."""
    if bars is None or len(bars) == 0:
        return _status_only("no-data")
    frame = _completed(bars, last_session)
    index = _signal_index(frame, candidate.signal_date)
    if index is None:
        return _status_only("no-data")
    ratio = _reanchor_ratio(candidate, frame, index)
    plan = _plan_for(_rebased(candidate, ratio), frame.iloc[:index + 1])
    if plan is None:
        return _status_only("no-plan", reanchored=ratio is not None)
    return _outcome(frame, index, plan, ratio is not None)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_gate_counterfactual.py`
Expected: PASS, `20 passed`, `0 failed`.

- [ ] **Step 5: Complexity and syntax**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/gate_counterfactual.py && python -m py_compile swingbot/core/backtesting/gate_counterfactual.py`
Expected: no output from radon (every function below C), no error.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/gate_counterfactual.py tests/backtesting/test_gate_counterfactual.py
git commit -m "feat(v147): simulate_blocked core -- signal bar, price basis, walk, status (V147-2)"
```

### Task V147-3: Truncated plan build, pinned overrides, no-lookahead and replay-parity tests

**Model:** opus — NO-LOOKAHEAD and journal-pinning in a builder shared with the live constructors; a subtle slip silently inflates every blocked-arm number.

**Files:**
- Modify: `swingbot/core/backtesting/gate_counterfactual.py`
- Modify: `tests/backtesting/test_gate_counterfactual.py`

Creates for later tasks (ledger): `build_candidate_plan(candidate, window) -> TradePlanV2 | None`, `scenario_from_dict(d) -> levels.Scenario`, `scenario_to_dict(sc) -> dict`. Additive (see the part header): `UnpinnableBuild`, `PIN_KEYS`, `pinned_scan_params(strategy, *, plan=None, params=None) -> dict`.

Symbols used, verified at HEAD: `builders.build_strategy_plan` (`swingbot/core/planning/builders.py:398`; overrides `stop_mult`, `tp2_r`, `time_stop_days`, `scan_params`), `builders.build_confluence_plan` (`:556`; `primary_strategy`, `level_map`, `quality_inputs`, `params`), `levels.Scenario` (`swingbot/core/market/levels.py:615`), `levels.build_level_map(df, h, current_price)` (`:578`), `params._resolve_stop_mult` / `_resolve_tp2_r` / `_resolve_time_stop_days` (`swingbot/core/planning/params.py:99/116/130`, read the live journal iff `config.DATA_DRIVEN_STOPS_ENABLED`), `swingbot.scan_params.ScanParams` (frozen dataclass, `from_config()`), `TradePlanV2.stop_mult_applied` / `tp2_r_applied` / `time_stop_days`.

How the rebuild mirrors live, and where it deliberately does not:
- **Strategy candidate** (`source == "strategy"`): `build_strategy_plan(window, len(window) - 1, ...)` with no `level_map` and no `quality_inputs`, exactly as `strategy_pass.build_strategy_plan_at` calls it, plus the pinned `stop_mult` / `tp2_r` / `time_stop_days` and the stored `ScanParams`.
- **Confluence / short-lane candidate**: `build_confluence_plan(scenario_from_dict(candidate.scenario), window, ...)` with `level_map = levels.build_level_map(window, HORIZONS[h], last close)` (the live `analyze.py` call shape) and `primary_strategy = candidate.strategy`, which the recorder stores as `primary_strategy_for(scenario)` (ledger, `gate_rejections` record). Using the stored label keeps the matplotlib chain `primary_strategy_for` imports out of the resolver. No scenario → `None` (→ `no-plan`).
- **`quality_inputs=None`**: quality sets only `quality_score`, `quality_breakdown` and `confidence_level` (`params._apply_quality`), none of which `simulate_exit` reads, so the outcome is invariant; the live builder of those inputs needs the scan `item` (`analyze._build_quality_inputs`), which a stored row does not have.
- **Pinning**: the stored overrides are passed as explicit arguments, so a non-`None` pin never reaches a resolver. A `None` pin with `config.DATA_DRIVEN_STOPS_ENABLED` on would make the builder read today's journal; the rebuild refuses (`UnpinnableBuild`) and `simulate_blocked` returns `no-data` with one warning. The same holds for `STALL_EXIT_ENABLED` (journal) and `OPEX_CAUTION_ENABLED` (wall clock), which no stored field can pin; this mirrors `backtest._LIVE_STATE_FLAGS`, which the replays refuse for the same reason. All three default off (`.env.example`).
- **Re-anchoring** already scales the stored scenario (V147-2's `_rebased`), so a confluence rebuild on a split-adjusted cache builds on the cache's basis.

- [ ] **Step 1: Write the failing tests**

In `tests/backtesting/test_gate_counterfactual.py`, replace the import block at the top (everything from `import pytest` down to `from tests.helpers import make_ohlcv`) with:

```python
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
```

Then append to the end of the file:

```python


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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_gate_counterfactual.py`
Expected: FAIL, `AttributeError: module 'swingbot.core.backtesting.gate_counterfactual' has no attribute 'scenario_to_dict'` (and siblings); V147-2's 20 tests still pass.

- [ ] **Step 3: Extend the module**

In `swingbot/core/backtesting/gate_counterfactual.py`:

(a) In the module docstring, replace

```python
the stored plan (V147-3 adds the truncated rebuild), and walks it through
```

with

```python
the stored plan or rebuilds it on the frame truncated at the signal bar
(overrides pinned to the stored scan params), and walks it through
```

(b) Replace the import block (from `import numpy as np` through the `plan_types` import) with:

```python
import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import params as plan_params
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_types import TradePlanV2, plan_from_dict, plan_to_dict
```

(c) Replace the whole `_plan_for` function and the whole `simulate_blocked` function (the last two definitions in the file) with:

```python
class UnpinnableBuild(RuntimeError):
    """A strategy rebuild would read live state (journal / wall clock) no stored field pins."""


PIN_KEYS = ("stop_mult", "tp2_r", "time_stop_days")
_WALL_CLOCK_FLAGS = ("STALL_EXIT_ENABLED", "OPEX_CAUTION_ENABLED")


def scenario_to_dict(scenario) -> dict:
    """JSON-safe dict of a levels.Scenario (sources kept as plain strings)."""
    out = dataclasses.asdict(scenario)
    for key in ("stop_sources", "target_sources", "target2_sources"):
        if out.get(key) is not None:
            out[key] = [str(s) for s in out[key]]
    return out


def scenario_from_dict(d: dict) -> levels.Scenario:
    """Inverse of scenario_to_dict; unknown keys are ignored."""
    known = {f.name for f in dataclasses.fields(levels.Scenario)}
    return levels.Scenario(**{k: v for k, v in d.items() if k in known})


def pinned_scan_params(strategy: str, *, plan: TradePlanV2 | None = None, params=None) -> dict:
    """The candidate's ``scan_params``: the three data-driven-stops overrides as they
    stood at the gate, plus the ScanParams fields. Read off the plan when one
    exists, else resolved now (the block time) through the live resolvers."""
    if plan is not None:
        pins = {"stop_mult": plan.stop_mult_applied, "tp2_r": plan.tp2_r_applied,
                "time_stop_days": plan.time_stop_days}
    else:
        pins = {"stop_mult": plan_params._resolve_stop_mult(strategy),
                "tp2_r": plan_params._resolve_tp2_r(strategy),
                "time_stop_days": plan_params._resolve_time_stop_days(strategy)}
    pins["params"] = dataclasses.asdict(params) if params is not None else None
    return pins


def _scan_params_of(candidate: BlockedCandidate):
    """The stored ScanParams, or None (the builder's own default)."""
    stored = (candidate.scan_params or {}).get("params")
    if not stored:
        return None
    from swingbot.scan_params import ScanParams
    known = {f.name for f in dataclasses.fields(ScanParams)}
    return ScanParams(**{k: v for k, v in stored.items() if k in known})


def _strategy_pins(candidate: BlockedCandidate) -> dict:
    """The pinned overrides; raises UnpinnableBuild when the build would read live state."""
    on = [name for name in _WALL_CLOCK_FLAGS if getattr(config, name, False)]
    if on:
        raise UnpinnableBuild(f"{', '.join(on)} on: the rebuild would read live state")
    stored = candidate.scan_params or {}
    pins = {key: stored.get(key) for key in PIN_KEYS}
    if config.DATA_DRIVEN_STOPS_ENABLED and any(v is None for v in pins.values()):
        raise UnpinnableBuild("DATA_DRIVEN_STOPS_ENABLED on and an override is not pinned")
    return pins


def _strategy_plan(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The live strategy constructor on the truncated frame, overrides pinned."""
    pins = _strategy_pins(candidate)
    return build_strategy_plan(
        window, len(window) - 1, ticker=candidate.ticker, strategy=candidate.strategy,
        horizon_key=candidate.horizon, direction=candidate.direction,
        stop_mult=pins["stop_mult"], tp2_r=pins["tp2_r"],
        time_stop_days=pins["time_stop_days"], scan_params=_scan_params_of(candidate))


def _confluence_plan(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The live confluence constructor; level_map from the truncated frame."""
    if candidate.scenario is None:
        return None
    price = float(window["Close"].iloc[-1])
    level_map = levels.build_level_map(window, HORIZONS[candidate.horizon], price)
    return build_confluence_plan(
        scenario_from_dict(candidate.scenario), window, ticker=candidate.ticker,
        horizon_key=candidate.horizon, primary_strategy=candidate.strategy,
        level_map=level_map, quality_inputs=None, params=_scan_params_of(candidate))


def build_candidate_plan(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """Rebuild the plan the gate threw away, from ``window`` (bars <= signal) only."""
    if candidate.source == "strategy":
        return _strategy_plan(candidate, window)
    return _confluence_plan(candidate, window)


def _plan_for(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The stored plan as stored; otherwise the truncated rebuild."""
    if candidate.plan is not None:
        return plan_from_dict(candidate.plan)
    return build_candidate_plan(candidate, window)


def _built_plan(candidate: BlockedCandidate, window) -> tuple[TradePlanV2 | None, bool]:
    """(plan | None, unpinnable)."""
    try:
        return _plan_for(candidate, window), False
    except UnpinnableBuild as exc:
        log.warning("gate counterfactual: %s %s %s -- %s; no-data", candidate.ticker,
                    candidate.strategy, candidate.signal_date, exc)
        return None, True


def simulate_blocked(candidate: BlockedCandidate, bars, *,
                     last_session: str | None = None) -> CounterfactualResult:
    """What ``candidate`` would have done on ``bars`` (one ticker, daily OHLCV)."""
    if bars is None or len(bars) == 0:
        return _status_only("no-data")
    frame = _completed(bars, last_session)
    index = _signal_index(frame, candidate.signal_date)
    if index is None:
        return _status_only("no-data")
    ratio = _reanchor_ratio(candidate, frame, index)
    plan, unpinnable = _built_plan(_rebased(candidate, ratio), frame.iloc[:index + 1])
    if unpinnable:
        return _status_only("no-data", reanchored=ratio is not None)
    if plan is None:
        return _status_only("no-plan", reanchored=ratio is not None)
    return _outcome(frame, index, plan, ratio is not None)
```

`build_candidate_plan` is looked up as a module global inside `_plan_for`, so `test_builder_sees_only_bars_up_to_the_signal` can spy on it with `monkeypatch.setattr(gc, "build_candidate_plan", ...)`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_gate_counterfactual.py`
Expected: PASS, `34 passed`, `0 failed`. If `test_strategy_rebuild_...` fails with `truncated is not None`, `RSI` no longer builds on the synthetic uptrend: pick another ATR-branch strategy from `backtest.ALL_STRATEGIES` that does (`python -c` loop over `build_strategy_plan(_sine_frame().iloc[:301], 300, ...)`), never loosen the assertion.

- [ ] **Step 5: Complexity, syntax, and the neighbouring suites**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/gate_counterfactual.py && python -m py_compile swingbot/core/backtesting/gate_counterfactual.py`
Expected: no radon output, no error.

Run: `python scripts/dev/testrun.py changed`
Expected: `0 failed` (only the new module and its test changed, so this selects the new file).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/gate_counterfactual.py tests/backtesting/test_gate_counterfactual.py
git commit -m "feat(v147): truncated plan rebuild with pinned overrides, no-lookahead tests (V147-3)"
```

# Phase 2: TRAIN row recorder

### Task V147-4: TRAIN gate-row recorder module

**Model:** sonnet — a pure helper module against a fixed row shape; the cap check is copied verbatim from `attach_plan_v2`.

**Cross-plan (audit 2026-10-10):** if `swingbot/core/backtesting/instrument/contract.py` exposes a v1 train window (v158 merged: `contract.resolve("v1").train_window`), derive `TRAIN_WINDOW = tuple(contract.resolve("v1").train_window)` from it (import `from swingbot.core.backtesting.instrument import contract`); its value is the same `("2020-01-01", "2023-12-31")`, so every test below holds unchanged. Otherwise keep the literal shown in Step 3.

**Files:**
- Create: `swingbot/core/backtesting/blocked_recorder.py`
- Create: `tests/backtesting/test_blocked_recorder.py`

Creates for later tasks (ledger, consumed by V147-5 and V147-6): `TRAIN_WINDOW = ("2020-01-01", "2023-12-31")`; `require_train_window(date_from, date_to, *, validation=False) -> None` (prints `--record-blocked: <why>` to stderr and raises `SystemExit(2)`); `over_cap(plan) -> bool`; `risk_cap_margin(plan) -> float`; `dollar_risk(cf_r, planned_loss) -> float | None`; `gate_row(*, population, arm, source, ticker, strategy, horizon, direction, signal_date, gate, reason, margin, cf_status, cf_r, win, planned_loss_pct=None, expiry_bars=None, in_sample=False) -> dict`; `row_from_exit(exit_result, plan, **row_fields) -> dict`; `write_gate_rows(rows, path) -> int`.

Symbols used, verified at HEAD: `risk_limits.HARD_MAX_PLANNED_LOSS_PCT` (`swingbot/core/risk_limits.py:9`, `2.0`), `risk_limits.planned_loss_pct(entry_price, stop_loss)` (`:17`, `inf` when invalid), `gate_counterfactual.result_from_exit` (V147-2), `exit_sim.ExitResult` / `_not_triggered` / `_no_trade`.

Contract details the tests pin:
- `over_cap(plan)` is `planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9`, character for character the check at `analyze.attach_plan_v2` (`swingbot/core/scanning/analyze.py`, the `risk_cap` branch). It is the **plan-time** cap; exit_sim's fill-time `_not_triggered("risk_cap")` is a different rule and is never consulted here.
- `risk_cap_margin` = planned loss % − 2.0 (spec § margin).
- `dollar_risk(cf_r, planned_loss) = cf_r * planned_loss / HARD_MAX_PLANNED_LOSS_PCT` (index § Deviations): `None` when either input is `None` or the loss is not finite.
- `gate_row` emits exactly the index's shared shape, with `entry_date == signal_date` (the `week_cluster_bootstrap` key), `cf_r`/`win`/`dollar_risk` forced to `None` unless `cf_status == "filled"`, and rejects unknown `population`/`arm`/`source`/`gate`/`cf_status` (including `pending`) with `ValueError`, so a mislabelled row fails the TRAIN run loudly instead of polluting a cell. Taken-arm rows pass `reason=None`.
- `row_from_exit` reads `ticker`, `strategy`, `horizon`, `direction`, `expiry_bars` off the plan; explicit `row_fields` win.
- No RS row is ever produced by a TRAIN recorder (v34 closed): the module accepts `gate="rs"` only because live rows share the shape; V147-5/V147-6 never pass it.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_blocked_recorder.py`:

```python
"""v147 V147-4: TRAIN gate-row recorder module."""
import json

import pytest

from swingbot.core.backtesting import blocked_recorder as br
from swingbot.core.planning.exit_sim import ExitResult, _not_triggered, _no_trade
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct


def _plan(trigger=100.0, stop=97.0, **kw) -> TradePlanV2:
    base = dict(plan_id="p1", ticker="MSFT", created_at="2021-03-01", source="confluence",
                strategy="Fibonacci", horizon_key="4w", direction="bullish", entry_type="stop_entry",
                trigger_price=trigger, entry_price=None, expiry_bars=3, stop_loss=stop, tp1=106.0,
                tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


def _row(**kw) -> dict:
    base = dict(population="train", arm="blocked", source="confluence", ticker="MSFT",
                strategy="Fibonacci", horizon="4w", direction="bullish", signal_date="2021-03-01",
                gate="plan_rejected", reason="risk_cap", margin=1.0, cf_status="filled",
                cf_r=-1.0, win=False)
    base.update(kw)
    return br.gate_row(**base)


def _win(r=1.4) -> ExitResult:
    return ExitResult(outcome="win", runner_outcome="runner_be", entry_index=4, exit_index=7,
                      entry_price=100.0, r_total=r,
                      legs=[{"fraction": 0.5, "exit_price": 106.0, "r": 2.0, "reason": "tp1"}])


SHAPE = {"population", "arm", "source", "ticker", "strategy", "horizon", "direction",
         "signal_date", "entry_date", "gate", "reason", "margin", "cf_status", "cf_r", "win",
         "planned_loss_pct", "dollar_risk", "expiry_bars", "in_sample"}


def test_train_window_is_frozen():
    assert br.TRAIN_WINDOW == ("2020-01-01", "2023-12-31")


@pytest.mark.parametrize("kwargs", [
    {"date_from": "2020-01-01", "date_to": "2023-12-31", "validation": True},
    {"date_from": "2019-12-31", "date_to": "2023-12-31"},
    {"date_from": "2020-01-01", "date_to": "2024-01-02"},
])
def test_require_train_window_refuses_outside_train(kwargs, capsys):
    with pytest.raises(SystemExit) as exc:
        br.require_train_window(**kwargs)
    assert exc.value.code == 2
    assert "--record-blocked" in capsys.readouterr().err


@pytest.mark.parametrize("date_from,date_to", [
    ("2020-01-01", "2023-12-31"), ("2021-06-01", "2022-06-30"), (None, None)])
def test_require_train_window_accepts_train(date_from, date_to):
    assert br.require_train_window(date_from, date_to) is None


@pytest.mark.parametrize("trigger,stop", [(100.0, 97.0), (100.0, 98.0), (100.0, 98.5),
                                          (50.0, 48.9999), (200.0, 204.5)])
def test_over_cap_agrees_with_attach_plan_v2s_check(trigger, stop):
    direction = "bullish" if stop < trigger else "bearish"
    plan = _plan(trigger, stop, direction=direction)
    live = planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9
    assert br.over_cap(plan) is live


def test_exactly_at_the_cap_is_not_over():
    assert br.over_cap(_plan(100.0, 98.0)) is False
    assert br.risk_cap_margin(_plan(100.0, 98.0)) == pytest.approx(0.0)


def test_risk_cap_margin_is_planned_loss_past_the_cap():
    assert br.risk_cap_margin(_plan(100.0, 97.0)) == pytest.approx(1.0)
    assert br.risk_cap_margin(_plan(100.0, 98.5)) == pytest.approx(-0.5)


def test_dollar_risk_scales_r_by_stop_width_over_the_cap():
    assert br.dollar_risk(-1.0, 3.0) == pytest.approx(-1.5)
    assert br.dollar_risk(2.0, 2.0) == pytest.approx(2.0)
    assert br.dollar_risk(None, 3.0) is None
    assert br.dollar_risk(1.0, None) is None
    assert br.dollar_risk(1.0, float("inf")) is None


def test_gate_row_has_the_shared_shape():
    row = _row(planned_loss_pct=3.0, expiry_bars=3)
    assert set(row) == SHAPE
    assert row["entry_date"] == row["signal_date"] == "2021-03-01"
    assert row["dollar_risk"] == pytest.approx(-1.5)
    assert row["in_sample"] is False
    json.dumps(row)


def test_non_filled_rows_carry_no_r_and_no_win():
    for status in ("no-fill", "no-plan", "no-data"):
        row = _row(cf_status=status, cf_r=0.0, win=False, planned_loss_pct=3.0)
        assert (row["cf_r"], row["win"], row["dollar_risk"]) == (None, None, None)


@pytest.mark.parametrize("field,value", [("population", "holdout"), ("arm", "both"),
                                         ("gate", "dryup"), ("cf_status", "pending"),
                                         ("source", "outlook")])
def test_gate_row_rejects_unknown_labels(field, value):
    with pytest.raises(ValueError):
        _row(**{field: value})


def test_row_from_exit_fills_from_the_plan():
    row = br.row_from_exit(_win(), _plan(), population="train", arm="taken", source="confluence",
                           signal_date="2021-03-01", gate="plan_rejected", reason=None,
                           margin=None, in_sample=False)
    assert (row["cf_status"], row["cf_r"], row["win"]) == ("filled", 1.4, True)
    assert (row["ticker"], row["strategy"], row["horizon"], row["direction"], row["expiry_bars"]) \
        == ("MSFT", "Fibonacci", "4w", "bullish", 3)


def test_row_from_exit_never_scores_a_no_fill_or_no_trade():
    kw = dict(population="train", arm="taken", source="strategy", signal_date="2021-03-01",
              gate="compression", reason=None, margin=None, in_sample=True)
    assert br.row_from_exit(_not_triggered("expired"), _plan(), **kw)["cf_status"] == "no-fill"
    assert br.row_from_exit(_no_trade(4, 100.0), _plan(), **kw)["cf_status"] == "no-plan"
    assert br.row_from_exit(_not_triggered(), _plan(), **kw)["cf_r"] is None


def test_write_gate_rows_round_trips(tmp_path):
    rows = [_row(), _row(ticker="AAPL", cf_status="no-fill", cf_r=None, win=None)]
    path = tmp_path / "logs" / "v147-blocked-confluence.jsonl"
    assert br.write_gate_rows(rows, path) == 2
    back = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert back == rows
    assert br.write_gate_rows([], path) == 0 and path.read_text(encoding="utf-8") == ""
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_blocked_recorder.py`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.blocked_recorder'`.

- [ ] **Step 3: Implement the module**

Create `swingbot/core/backtesting/blocked_recorder.py`:

```python
"""v147: the TRAIN gate-row recorder's shared pieces.

The row shape both TRAIN recorders write (``--record-blocked``) and the
report reads, the TRAIN-window guard, and the ``risk_cap`` shadow: a
record-only copy of ``analyze.attach_plan_v2``'s plan-time 2% check. It is
unrelated to exit_sim's fill-time ``_not_triggered("risk_cap")`` cancel.
No RS row is ever written on TRAIN (v34 closed).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from swingbot.core.backtesting.gate_counterfactual import result_from_exit
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

TRAIN_WINDOW = ("2020-01-01", "2023-12-31")
POPULATIONS = ("train", "live")
ARMS = ("blocked", "taken")
SOURCES = ("strategy", "confluence", "short_lane")
GATES = ("rs", "plan_rejected", "compression")
ROW_STATUSES = ("filled", "no-fill", "no-plan", "no-data")
_CAP_EPSILON = 1e-9               # analyze.attach_plan_v2's own tolerance


def _refuse(message: str) -> None:
    print(f"--record-blocked: {message}", file=sys.stderr, flush=True)
    raise SystemExit(2)


def require_train_window(date_from: str | None, date_to: str | None, *,
                         validation: bool = False) -> None:
    """Exit 2 unless the run sits inside TRAIN (2020-01-01..2023-12-31)."""
    start, end = TRAIN_WINDOW
    if validation:
        _refuse("refuses --validation; gate rows are recorded on TRAIN only")
    if date_from is not None and str(date_from) < start:
        _refuse(f"--from {date_from} is before the TRAIN window ({start})")
    if date_to is not None and str(date_to) > end:
        _refuse(f"--to {date_to} is after the TRAIN window ({end})")


def _planned_loss(plan) -> float:
    return planned_loss_pct(plan.trigger_price, plan.stop_loss)


def over_cap(plan) -> bool:
    """attach_plan_v2's plan-time check, verbatim: True means live rejects as risk_cap."""
    return _planned_loss(plan) > HARD_MAX_PLANNED_LOSS_PCT + _CAP_EPSILON


def risk_cap_margin(plan) -> float:
    """Planned loss % of entry past the 2% cap (positive = over the cap)."""
    return _planned_loss(plan) - HARD_MAX_PLANNED_LOSS_PCT


def dollar_risk(cf_r: float | None, planned_loss: float | None) -> float | None:
    """The outcome in units of the 2% dollar cap at the notional a 2%-wide stop sizes."""
    if cf_r is None or planned_loss is None or not math.isfinite(planned_loss):
        return None
    return float(cf_r) * float(planned_loss) / HARD_MAX_PLANNED_LOSS_PCT


def _check(name: str, value, allowed: tuple) -> None:
    if value not in allowed:
        raise ValueError(f"gate row {name}={value!r} not in {allowed}")


def gate_row(*, population, arm, source, ticker, strategy, horizon, direction, signal_date,
             gate, reason, margin, cf_status, cf_r, win, planned_loss_pct=None,
             expiry_bars=None, in_sample=False) -> dict:
    """One row of the shared gate-row shape (see the plan index)."""
    for name, value, allowed in (("population", population, POPULATIONS), ("arm", arm, ARMS),
                                 ("source", source, SOURCES), ("gate", gate, GATES),
                                 ("cf_status", cf_status, ROW_STATUSES)):
        _check(name, value, allowed)
    filled = cf_status == "filled"
    r = float(cf_r) if filled and cf_r is not None else None
    return {
        "population": population, "arm": arm, "source": source, "ticker": ticker,
        "strategy": strategy, "horizon": horizon, "direction": direction,
        "signal_date": str(signal_date), "entry_date": str(signal_date),
        "gate": gate, "reason": reason,
        "margin": None if margin is None else float(margin),
        "cf_status": cf_status, "cf_r": r, "win": bool(win) if filled and win is not None else None,
        "planned_loss_pct": None if planned_loss_pct is None else float(planned_loss_pct),
        "dollar_risk": dollar_risk(r, planned_loss_pct),
        "expiry_bars": None if expiry_bars is None else int(expiry_bars),
        "in_sample": bool(in_sample),
    }


def row_from_exit(exit_result, plan, **row_fields) -> dict:
    """A gate row from a replayed ExitResult; ticker/strategy/horizon/direction/expiry from the plan."""
    status, cf_r, win = result_from_exit(exit_result)
    fields = {"ticker": plan.ticker, "strategy": plan.strategy, "horizon": plan.horizon_key,
              "direction": plan.direction, "expiry_bars": plan.expiry_bars}
    fields.update(row_fields)
    return gate_row(cf_status=status, cf_r=cf_r, win=win, **fields)


def write_gate_rows(rows, path) -> int:
    """Write rows as JSONL (overwrite); returns the row count."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_blocked_recorder.py`
Expected: PASS, `25 passed`, `0 failed`.

- [ ] **Step 5: Complexity and syntax**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/blocked_recorder.py && python -m py_compile swingbot/core/backtesting/blocked_recorder.py`
Expected: no radon output (`gate_row` measures B(9) at writing), no error.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/blocked_recorder.py tests/backtesting/test_blocked_recorder.py
git commit -m "feat(v147): TRAIN gate-row recorder module (V147-4)"
```

