# v105 PENDING daily range continuation — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-25-v105-pending-range-continuation-design.md`
**Bump:** none until alert enablement; bot minor only if a direction ships
**Edge:** expectancy

**Progress:** Not started. No code, backtest or production work is implied by
the creation of this plan.

**Goal:** Produce a causally correct, measurable source of pre-break PENDING
range plans; test directional pressure against the unfiltered range source;
keep alerts shadow-only until the frozen evidence and execution-feed gates pass.

**Architecture:** A pure candidate module (`swingbot/core/market/range_candidate.py`)
owns range geometry, trend, confirmed pivot and the pressure predicate. A
builder (`swingbot/core/planning/range_builder.py`) turns one candidate into a
`TradePlanV2`. The live scan and the replay both call that pair through
`swingbot/core/planning/range_source.py:range_plan_at`. A source-specific
rearm rule (`may_rearm`) stops a rolling window from re-issuing the same range.
The replay (`swingbot/core/backtesting/range_replay.py`) emits keyed rows. The
arms module (`range_arms.py`) turns them into provenance-stamped, paired v72
arms. Notifications reuse `PlanManager`'s `pending_notice` → `resend_notices` →
`notify_plan_events` → `ack_notified` loop, which already retries until
delivery, through one new feed transition, `range_pending`.

**Tech stack:** Python 3.11+, pandas/numpy, pytest, existing JSON/Postgres
PlanStore and Discord presentation. No TrendSpider integration is assumed.

## Parts

| File | Tasks | Content |
|---|---|---|
| `_1a-candidate-builder.md` | 1–3 | file map for Phase 1, as-of freeze note, candidate + fixtures, builder + shared source entry point |
| `_1b-replay-live.md` | 4–5 | daily replay, masked live source, PENDING feed notice, broker-unknown risk-cap notice |
| `_2a-arms-shadow.md` | 6–7 | file map for Phases 2–3, paired arms + measure script, prospective shadow telemetry |
| `_2b-measure-release.md` | 8–12 | TRAIN run, holdout freeze, holdout shot, enablement, final suite |

Every task carries its complete test and source code. Pull one task:
`grep -n "^### Task 3:" -A 450 docs/superpowers/plans/2026-09-25-v105-pending-range-continuation_1a-candidate-builder.md`.

## Facts verified at plan-writing time (HEAD 46872d3b)

These were read from code, not assumed. Task 1 re-verifies them before any edit.

- **v100 `ArmEngine` has not landed** (no `ArmEngine`/`arm_producer` in `swingbot/`).
  Task 6 uses a bespoke `range_arms` adapter feeding the existing
  `swingbot/core/backtesting/acceptance.py:evaluate` and
  `scripts/backtest/validate_component.py`.
- **v104 has no code** (`stop_scope.py`, `short_builders.py`, `short_entries.py`
  absent; no `dollar_risk` symbol). The current risk model is
  `swingbot/core/risk_limits.py`: `HARD_MAX_PLANNED_LOSS_PCT = 2.0`,
  `capped_planned_loss_pct`, `planned_loss_pct`. Sizing is
  `swingbot/core/planning/account.py:compute_position_size`, applied at
  trade-log time for every source; the builder does not size.
- `select_structural_target` (`swingbot/core/planning/targets.py:10`) returns a
  **synthetic** `entry ± risk·max_rr` price when the nearest real level sits
  beyond the band. The spec forbids a projected target, so the range builder
  refuses that case (`target_beyond_band`).
- `simulate_exit` (`swingbot/core/planning/exit_sim.py:322`) walks exits from
  `entry_index + 1`. The fill bar is never stop/target-checked. The replay
  labels this in its output (`EXIT_LIMITATION`) and does separate entry-bar
  diagnostics.
- `PlanManager._step_pending` (`plan_manager.py:502`) fills at
  `max(live, trigger)` and emits `cancelled_risk_cap` above 2%. The feed text
  for that (`presentation/instructions.py:256`) says "never filled", which is
  **false for a resting broker stop order that gapped**. Task 5 changes that
  text for the range source only and records the confluence instance as a
  separate integrity finding in the Task 1 note.
- `PriceQuote` (`marketdata/data.py:409`) has `price` and `stale` only, with no
  timestamp. The fresh path is `get_current_price_detail(t, allow_stale=False)`
  with a 15 s TTL (`_PRICE_CACHE_TTL_SECONDS`). The scan's `live_prices` may be
  up to 15 min old, so the range pass fetches its own fresh quote per candidate.
- Plan identity in `PlanStore` is `plan_id` only. `TradePlanV2.source` is
  currently `"strategy" | "confluence"`. The registry lookup and `ledger_for`
  key off `source`. Task 3 adds `"range_continuation"` to the weak-ledger rule.

## Global constraints

- Before implementing, read `docs/claude/architecture.md`, `known-traps.md`,
  `backtest-methodology.md`, `edge-priorities.md`, `code-complexity.md`, and the
  `.claude/skills/no-lookahead`, `edge-module`, `alert-surface` and
  `backtest-gate` checklists. Reinspect the exact code after any v104/v100
  merge. This plan's paths and line numbers are starting points, not
  authority over changed code.
- No production deployment, SSH or live configuration change is in scope.
  The source stays masked (`RANGE_ALERTS_MODE=off`) until Task 11's explicit
  evidence decision.
- The live universe is the current watchlist. Measurement uses the full
  available cached universe × all ten horizons. Report ticker and sector
  concentration; one sector cluster is not independent replication.
- The decision on session `t` reads completed daily bars only through `t-1`.
  The live quote can decide proximity/crossing, never range geometry. Every
  signal feature has a full-series-versus-truncated-series test.
- One source ID, `range_continuation` (`SOURCE_ID`). Existing confluence and
  v104 B1/B2 entry logic are unchanged. v69, v88 and v90 are not reopened.
- Spec constants are frozen in `range_candidate.py`: `N_GRID=(10,15,20)`,
  `D_GRID=(0.25,0.50,0.75)`, `TOUCH_ATR=0.25`, `MIN_TOUCH_GAP=2`,
  `MIN_WIDTH_ATR=2.0`, `MAX_WIDTH_ATR=8.0`, `TREND_SMA=30`,
  `TREND_SLOPE_BARS=5`, `TRIGGER_BUFFER_ATR=0.10`, `STOP_CUSHION_ATR=0.10`,
  pressure = 2 of the last 3 closes in the direction-side quarter plus a rising
  last low (LONG) / falling last high (SHORT). No rescue filter, and no grid
  expansion after a failed gate.
- Pressure-off and pressure-on share entry, stop, target and exits for every
  shared candidate. `range_replay` caches one plan per `(bar, horizon)` and
  both arms read it.
- A PENDING paper event never implies the bot placed or cancelled a broker
  order. Fill, expiry, invalidation and risk-cap divergence reach the user
  as actionable execution-feed instructions.
- Every changed function stays below cyclomatic complexity 15
  (`python -m radon cc -s -n C <files>`). Iterate with one narrow test file
  per task (`python scripts/dev/testrun.py file <test>`). `0 failed` and
  `0 xfailed` is green. The full suite runs once, in Task 12.
- Commit each finished task separately. Stage explicit paths. Run
  `git status` and `git worktree list` before each commit (concurrent
  sessions share this tree). The version bump is a separate release commit,
  only if alert behaviour ships.

## Acceptance and measurement contract

1. Stage −1 (Task 8 pilot) proves the candidate is reachable, live/replay plans
   are field-identical at the same as-of time (Task 4 parity test), and the
   filled counts make the predeclared effect detectable (`validate_component
   --stage mde`). Failure ends measurement with no holdout shot.
2. TRAIN = `2020-01-01..2023-12-31` (`run_backtest_range.TRAIN`). Fold-test years
   are 2021/2022/2023, the `validate_component --stage walkforward` contract.
   TRAIN selects one `{N,d}` cell with the rule frozen in `range_arms.select_cell`
   (plateau: eligible cell with ≥2 eligible grid neighbours; eligible means
   component n ≥ 30, ΔWR > 0, ΔExpR ≥ −0.01; the highest ΔExpR wins; ties go to
   the smaller `d`, then the larger `N`). Source baseline profitability is
   reported separately from pressure's incremental effect.
3. Stage 2 is the repository's fold-consistency rule. Stage 3 is one
   prospective, untouched holdout shot (Tasks 9–10). The 2024–25 window and
   v104's 2026 holdout are refused by code (`range_arms.FORBIDDEN_WINDOWS`).
4. Score LONG and SHORT separately. Pressure as a feature is judged by all six
   v72 clauses (`acceptance.evaluate`). The source badge must clear its own
   absolute gate before live enablement.
5. Daily OHLC reports trigger-then-close-back-inside (`close_back_inside`) and
   `unresolved` entry-bar ordering. It does not count entry-day stops. Lead
   time, late alerts, gaps, cancellations and delivery come from the
   prospective shadow feed (Task 7).

## Review focus

The five failure modes most likely to bite a user. Each is pinned by a named test:

1. **Overnight gap fill, then paper `cancelled_risk_cap`.** The broker order
   may have filled, so the notice must say broker status is UNKNOWN and give
   an exit instruction. Test:
   `test_gap_fill_risk_cap_marks_broker_status_unknown` (Task 5).
2. **Stale quote treated as fresh.** The scan's `live_prices` can be up to 15 min
   old. The range pass must use `allow_stale=False` and refuse on `None`. Test:
   `test_stale_quote_refuses_notice` (Task 5).
3. **Rolling-window re-issue.** The day after a plan is issued, the same range
   (shifted by one bar) must not produce a second PENDING plan. Test:
   `test_overlap_suppression_one_plan_per_range` (Task 4) and
   `test_new_range_rearm_only` (Task 5).
4. **Entry-day stop described as tested.** Both stop and target inside the
   fill bar gives `unresolved`, never a guessed win/loss. Test:
   `test_entry_bar_both_touched_is_unresolved` (Task 4).
5. **Future bar leaking into range geometry.** A dramatic future breakout
   must leave earlier candidates and pressure unchanged. Test:
   `test_future_breakout_leaves_earlier_candidates_unchanged` (Task 2), and
   the replay-versus-direct equality `test_replay_candidates_equal_truncated_calls`
   (Task 4).

## Parallelisation

- **Sequential throughout Phase 1:** Task 2 → 3 → 4 (the builder consumes
  `RangeCandidate`; the replay consumes `range_plan_at`). Task 5 needs
  `range_plan_at`, `may_rearm` and `SOURCE_ID` from Tasks 2–3.
- **Group A (parallel after Task 5):** Tasks 6 and 7. Disjoint files
  (`backtesting/range_arms.py` and `scripts/backtest/measure_pending_range.py`
  versus `scanning/range_shadow.py` and `scripts/reports/range_shadow_report.py`).
  Neither consumes a symbol the other introduces. **Exception:** Task 7 edits
  `scan_run.py:_maybe_run_range_pass`, which Task 5 created. Task 6 does not
  touch it.
- **Sequential:** Task 8 after Task 6 (it runs Task 6's script). Task 9 after
  Tasks 7–8. Task 10 after the pre-registered window matures. Task 11 after
  Task 10. Task 12 last.
- No parallel subagent execution is required.
