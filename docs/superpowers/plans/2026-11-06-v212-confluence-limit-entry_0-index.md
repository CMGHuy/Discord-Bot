# v212 — Confluence limit entry partway to the support (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V212-6:" -A 400 docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_2-*.md`.

**Bump:** bot patch (the knob ships inert at 0; no observable difference until a pass and a partner decision)
**Edge:** expectancy — a prediction: on clamped confluence plans a limit partway to the support with its stop under the support raises ExpR on filled trades, with fewer trades and fewer noise stop-outs. If no cell passes, the closing commit amends this to "expectancy, measured none" with one clause.
**Screen:** exempt (post-signal)
**Spec:** [v212 — Confluence limit entry partway to the support (pre-registration)](../specs/2026-11-06-v212-confluence-limit-entry.md)
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md` (§2 signatures, §3a–3h excerpts, §4 test patterns, §6 traps)
**Worktree:** implement V212-1..V212-14 in `.claude/worktrees/2026-11-06-v212-confluence-limit-entry` (branch of the same name, created in V212-1's first step; `docs/claude/document-lifecycle.md`). V212-15..V212-17 run on `main` after V212-1..14 are merged and the CI run on that push is green.

## Goal

The live book's losses since September are fast (median life 2.2 h), tight
(stop about 1.77% from price against a median ATR14 of about 4.7%) and often
wrong only in timing (57% of stopped losses reached TP1 within 10 sessions).
The geometry explains it: a confluence long enters at market and, when the
nearest support is more than 2% below, the v115 clamp moves its stop to
market −1.75% — above the support, in empty air. Moving the stop out is
closed (v139 NO-LIFT, v191 UNDERPOWERED), and v131 closed a resting limit on
the Fibonacci strategy. This plan measures the one mechanism no closed row
covers: moving the **entry** on clamped **confluence** plans.

Once shipped, a single knob `CONFLUENCE_LIMIT_ENTRY_F` (default 0, inert)
turns an in-scope plan — a confluence market plan whose pre-clamp level lies
more than 2% from market M — into a resting limit at `L = M − f·(M − S)`
with its stop 0.25% beyond the support, TP1/TP2 unchanged, valid three
sessions, cancelled if TP1 trades first. One fill rule (trade-through, gap
fills at the open, a gap through the stop is a realised loss, inclusive TP1
cancel, same-bar conflict cancels) is shared by replay, live and the
measurement. Live gains resting-order alert wording, a follow-up on every
state change, two new events (`cancelled_heat_at_fill`,
`filled_stopped_gap`) and a heat/sector/cluster/max-open re-check at fill.
The measurement scores each cell's filled trades against the same in-scope
plans' reference trades after frictions and one portfolio pass with
notional caps and heat at fill.

What it leaves alone: out-of-scope plans, breakout `stop_entry` plans,
strategy-source plans, the 2% cap, the clamp and the floors — all
byte-identical, pinned by plan- and replay-level goldens at knob 0. Nothing
is switched on. Success is the three-cell pre-registration run once,
honestly: a cell passes only if its ExpR beats the reference, its fills
reach 50% of the reference's trades and its win rate sits no more than
2 pp below, with a plateau and a non-THIN Stage 3; the partner then decides
whether to set the knob live. A fail closes the rule for good.

## Architecture

- **Knob and rule** (V212-1..3, `swingbot/config.py`, `scan_params.py`,
  `planning/builders.py`, `planning/plan_types.py`, `scanning/analyze.py`):
  a pure geometry helper and one `apply_confluence_limit` call that both
  `build_confluence_plan` (live) and the replay module (measurement) use;
  drops logged through the existing `plan rejected (` lines.
- **Fill rule** (V212-4, new `planning/limit_entry_rule.py`): `bar_outcome`
  decides fill / cancel / nothing for one bar (or one live tick plus the
  session open), used by `exit_sim_v2` (V212-5) and `plan_manager` (V212-6).
- **Live path** (V212-6..10): `_step_limit` arm branch, `filled_stopped_gap`,
  risk-cap read from the planned `|L − stop|`; `fill_guard` heat re-check;
  event registration in every table; alert and follow-up text; the admin
  `levels-block` limit mapping.
- **Measurement** (V212-11..14): `backtesting/confluence_limit_replay.py`
  (paired reference/arm alerts derived from one knob-0 replay, so both arms
  see the same plan stream and cooldown), `backtest_wf.portfolio_replay`
  gains notional caps, a cluster callback and per-reason skips;
  `scripts/backtest/measure_confluence_limit.py` (stage chain, clauses,
  plateau, thin seal, per-ticker checkpoint) and the disclosures module.
- **Runs** (V212-15..17, on `main`): pre-registration record before compute,
  Stage −1 → 3 through `backtest-runner`, results doc, ledger rows,
  closed-row or pass report, `/panel`, `/close-out`.

**Tech stack:** Python 3.11, pandas/numpy, pytest; Angular (one mapping in
`frontend/src/app/workspaces/trades/why/levels-block.ts`).

## Global Constraints

- **Knob 0 is byte-identical.** `CONFLUENCE_LIMIT_ENTRY_F = 0` (config default `"0"`, `ScanParams.confluence_limit_entry_f = 0.0`) leaves every plan, every replay and every live step as today. The v212 plan golden and replay golden (captured from the base in V212-3, `V212_CAPTURE_GOLDEN=1`, never regenerated) and the existing v139/v191 goldens pass untouched. A changed golden is a stop, never an update.
- **Scope (spec § The rule, verbatim intent):** confluence plan, `entry_type` today `market` (not `scenario_is_breakout`), `builders.clamped_distance(M, level, is_bull) is not None` (level more than 2% from M). Never read scope from `stop_moved_by` (only v191's band sets it).
- **Frozen constants:** `LIMIT_STOP_BUFFER = 0.0025` (stop `S·(1 − 0.0025)` long, `S·(1 + 0.0025)` short, rounded to the tick away from L); L rounded to the tick toward M; drop when `(L − stop)/L > 2%` (`HARD_MAX_PLANNED_LOSS_PCT`); `LIMIT_EXPIRY_BARS = 3` (replay bars t+1..t+3; live through the close of the 3rd full session after the alert session); `limit_cancel_level = tp1`, `limit_strict_fill = True`; TP1/TP2 keep today's prices; `MIN_RISK_REWARD_RATIO` checked from L (`limit_rr_fail`); `MIN_STOP_DISTANCE_PCT` not applied to these plans. Tick size: `swingbot.core.market.atr_band.tick_size`.
- **Grid (pre-registered):** `F_GRID = (1/3, 1/2, 2/3)`, cell keys `"f0.333"`, `"f0.5"`, `"f0.667"`. **Looks: 3**, verdict pooled over both directions; per-direction disclosed; a pass ships both directions or neither.
- **Pass rule, per cell, point estimates:** (1) arm ExpR > reference ExpR; (2) arm fills ≥ 50% of reference trades (pooled directions; replaces `VOLUME_MAX_CUT_PCT`); (3) arm win rate ≥ reference − 2.0 pp. Gate family `--gate harvest`, Stage 2 `backtest_wf.gate_expectancy_harvest`; Stage 0 paired MDE over keys present in both arms, `observed_n` = filled keys; UNDERPOWERED keeps the budget; Stage 1 plateau = best passing cell whose every grid neighbour clears 1–3; Stage 3 < 30 filled trades per direction = THIN; 3 looks join `ledger_qvalues`.
- **One fill rule** (`limit_entry_rule.bar_outcome`) for replay, live and measurement: trade-through (low ≤ L − tick) primary, touch (low ≤ L) only as the disclosed sensitivity; open ≤ L fills at the open; fill at/through the stop fills and stops at the open (realised loss, never a 0R scratch); TP1 cancel inclusive (`≥` long, `≤` short); a bar reaching both L and TP1 is cancelled. Arm-only: out-of-scope limit plans (v113 fade, v131 Fibonacci Limit) keep `_limit_entry_v2`, `limit_cancelled` and `cancelled_gap_through_stop` exactly as today.
- **Frictions** (`swingbot/core/edge/frictions.py`, non-zero, both arms, every trade) are applied at scoring in the replay module; `simulate_exit_v2` stays frictionless.
- **Sizing:** fixed dollar risk on `|L − stop|`; `MAX_POSITION_SIZE_PCT` and `MAX_POSITION_VALUE_ABSOLUTE` bind in replay (portfolio pass), measurement and live; R is scored on the plan's stop; every kept plan asserts `|L − stop|/L ≤ 2%` (replay: `ValueError`; live: the existing `risk_cap` reject in `attach_plan_v2` and the planned-risk check in `_fill_pending`).
- **Heat at fill:** pending limits reserve nothing; at fill, heat, sector, cluster and `MAX_OPEN_POSITIONS` re-run against the then-open book with the fill's actual risk; a breach cancels (`cancelled_heat_at_fill`, status reason `heat_at_fill`). Replay applies the same rule in the portfolio pass (arm signals dated at the fill date).
- **Drop reasons** are bare tokens `limit_scope`, `limit_stop_beyond_cap`, `limit_rr_fail` (scripts/ops/export_book_rows.sh greps `(<reason>[,)]`).
- **No lookahead:** M, S, targets, ATR from bars ≤ t only; the replay module derives arm plans from the knob-0 reference plan's `trigger_price` (M), `acceptance_level` (S, v129 pre-clamp level), `tp1`, `tp2` — all frozen at bar t.
- **Cooldown:** `_REPLAY_COOLDOWN_BARS` stays set at plan acceptance; arms are derived from the reference stream, so a dropped or unfilled limit consumes it exactly as the reference plan does.
- **Caches:** backtests read `data/backtest_cache_ext` via `BACKTEST_CACHE_DIR` (v131 precedent); live reads root `market_data/` through `plan_manager`'s existing `daily_frame_fn`. State which one each change reads.
- **Complexity < 15** for every function written or changed (`python scripts/dev/complexity_gate.py`); `build_confluence_plan` (12), `attach_plan_v2` (12), `_step_pending` (11) gain no branch — new logic goes in named helpers.
- **New `TradePlanV2` field** `limit_entry_f: float | None = None` joins `_OMIT_WHEN_NONE`; it lives in the plans `doc` JSON (no promoted column, no Alembic revision; `schema-evolution.md` § The four operations, "add").
- Narrow test runs only: `python scripts/dev/testrun.py file <test>`. **No task runs the full suite**; CI does. Tasks touching the plan store or trade log run `/replicate-prod-db` first (shared `swing-db`, port 56789). New test files sit in existing directories (`tests/planning`, `tests/backtesting`, `tests/backtest_scripts`, `tests/edge`, `tests/presentation`, `tests/scanning`), so `tests/suites.toml` changes only if a suite passes `max_tests`.
- `.env` values are never printed. `.env.example` documents the knob at 0. No production change; the partner decides any switch-on via `mirror-prod`.

## Review Focus

1. **Gap open through the stop on a pending arm limit.** Replay books a fill **at the open** and an exit at that same open: about 0R less frictions, with `outcome="loss"` because the stop fired, and `filled_stopped_gap`. The from-L reading lives only in the disclosed `gap_stop_r_from_limit` (spec rule 6, corrected 2026-11-06). Live fills, persists the fill, closes it at the price in one step and posts `filled_stopped_gap`. It is never `cancelled_gap_through_stop` and never silently dropped. Owners: V212-4 (rule), V212-5 (replay), V212-6 (live).
2. **A bar that trades both L and TP1, and TP1 printed exactly at the level.** Both cancel (inclusive, conservative); a v131/v113 limit plan with the same bar still uses the strict `limit_cancelled`. Owners: V212-4, V212-5.
3. **A level at exactly 2% from M, and a missing level (`acceptance_level is None`).** Exactly 2% is out of scope (`clamped_distance` returns None) and the plan is today's; a missing level is out of scope, never a crash. Owners: V212-2, V212-11.
4. **A heat-at-fill cancel on a plan with a placeholder trade.** `cancelled_heat_at_fill` is in `PENDING_CANCEL_EVENTS`, so the placeholder is discarded and the follow-up posts; the enforcement test fails if any routing table misses either new event. Owners: V212-7, V212-8.
5. **A fill whose notional cap cut its size.** Portfolio pass opens it at reduced risk, its R stays scored on the plan's stop, and the capped share is counted; with both caps `None`, `portfolio_replay` returns exactly today's dict. Owners: V212-12, V212-14.

## OPEN (decisions the controller should check)

- **`limit_scope` meaning.** The spec lists it as a drop reason but defines no scope drop (out-of-scope plans are untouched). The plan uses it for an in-scope plan whose rounded geometry is degenerate (L not strictly between the stop and M, or a non-finite level) — rare by construction; counted.
- **`filled_stopped_gap` and `PENDING_CANCEL_EVENTS`.** It joins every routing table `cancelled_limit` is in **except** `PENDING_CANCEL_EVENTS`/`PLACEHOLDER_DISCARD_EVENTS`: a placeholder there would be deleted, erasing the realised loss. Its placeholder is resized by the fill and closed by the stop instead; the enforcement test checks "never left open" for both events.
- **`observed_n`.** The pre-registration record is committed before any compute with every frozen item; Stage −1 (outcome-blind census: scope, drops, fills per cell) then appends `observed_n` in a second commit before Stage 0, as the spec's Stage 0 needs a fill count that only a census can give.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A rule | V212-1 → V212-2 → V212-3 | config/scan_params/.env.example/reachability (1); builders.py, plan_types.py (2); builders.py, analyze.py, goldens (3) | 2 reads the knob on `ScanParams`; 3 wires 2's helper into `build_confluence_plan` and both edit `builders.py` |
| B fill rule | V212-4 → V212-5 | C `planning/limit_entry_rule.py` (4); `planning/exit_sim_v2.py` (5) | 5 consumes `bar_outcome`; V212-4 needs only V212-2's `limit_entry_f` field (contract), so it may start once V212-2 is merged, beside V212-3 |
| C live | V212-6 → V212-7 → V212-8 → V212-9 → V212-9b; V212-10 any time | `plan_manager.py` (6, 7), C `edge/fill_heat.py` (7), event tables (8), `instructions.py`/`session_expiry.py` (9), `plan_table.py`/`lifecycle_embeds.py` (9b), `levels-block.ts` (10) | 6 needs V212-4; 7 edits `plan_manager.py` after 6; 8 registers the events 6 and 7 emit; 9 writes their text and the tables 8 lists; 10 is frontend-only, no contract |
| D measurement | V212-11, V212-12 (parallel) → V212-13 → V212-14 | C `confluence_limit_replay.py` (11); `backtest_wf.py` (12); C `measure_confluence_limit.py` (13); C `confluence_limit_disclosures.py` + measure script (14) | 11 needs V212-3 and V212-5; 12 is disjoint (no contract with 11); 13 consumes both; 14 extends 13's script |
| E runs | V212-15 → V212-16 → V212-17 | results docs, ledger, methodology, plan/spec | on `main` after A–D merged and CI green; pre-registration precedes compute; verdict precedes close-out |

Group B may run beside V212-3 (disjoint files). Group C's V212-10 may run
beside anything. Group D's V212-12 may run beside all of groups B and C.
Sequential edges named: `builders.py` (V212-2, V212-3), `plan_manager.py`
(V212-6, V212-7), `measure_confluence_limit.py` (V212-13, V212-14), and the
event names V212-8/9 register from V212-6/7.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V212-1 | Knob `CONFLUENCE_LIMIT_ENTRY_F`: config field, ScanParams, `.env.example`, reachability row | 1 | sonnet | M `swingbot/config.py` (Field after `CONFLUENCE_STOP_DROP_PCT`, `searchable` set); M `swingbot/scan_params.py`; M `.env.example`; M `swingbot/core/backtesting/arms/reachability.py`; M `tests/market/test_v115_strategy_work_off.py` (knob table row); C `tests/test_config_v212_limit_entry.py` | `config.CONFLUENCE_LIMIT_ENTRY_F: float` (default 0.0); `ScanParams.confluence_limit_entry_f: float = 0.0` read in `from_config()`; `reachability.REGISTRY["CONFLUENCE_LIMIT_ENTRY_F"]` (REACHABLE, observed_by `C`, reason cites the dedicated v212 replay) |
| V212-2 | Limit geometry helper and `limit_entry_f` plan field | 1 | opus | M `swingbot/core/planning/builders.py`; M `swingbot/core/planning/plan_types.py` (`limit_entry_f`, `_OMIT_WHEN_NONE`); C `tests/planning/test_confluence_limit_geometry.py` | `builders.LIMIT_STOP_BUFFER = 0.0025`; `builders.LIMIT_EXPIRY_BARS = 3`; `builders.LIMIT_DROP_REASONS = ("limit_scope", "limit_stop_beyond_cap", "limit_rr_fail")`; `class LimitGeometry(NamedTuple): limit: float; stop_loss: float; level_distance_pct: float`; `confluence_limit_geometry(entry: float, level: float \| None, is_bull: bool, tp1: float \| None, f: float, min_rr: float) -> LimitGeometry \| str \| None` (None = out of scope, str = drop reason); `to_limit_plan(plan: TradePlanV2, geom: LimitGeometry, f: float) -> TradePlanV2` (deep copy: `entry_type="limit"`, `trigger_price=L`, `entry_price=None`, `stop_loss`, `status=PENDING` with a fresh history, `expiry_bars=3`, `limit_cancel_level=tp1`, `limit_strict_fill=True`, `limit_entry_f=f`, `stop_ceiling_pct=None`); `apply_confluence_limit(plan: TradePlanV2, level: float \| None, f: float, min_rr: float) -> TradePlanV2 \| str` (f == 0, non-market or out of scope → `plan` unchanged; drop → reason); `TradePlanV2.limit_entry_f: float \| None = None` |
| V212-3 | Wire the rule into `build_confluence_plan`; drop reasons in attach; knob-0 plan and replay goldens | 1 | opus | M `swingbot/core/planning/builders.py` (`build_confluence_plan` via a helper, `confluence_limit_dropped`); M `swingbot/core/scanning/analyze.py` (`_no_plan_reason`); C `tests/planning/test_v212_plan_golden.py`, C `tests/fixtures/v212/plan_golden.json`; C `tests/backtesting/test_v212_flag_off_golden.py`, C `tests/fixtures/v212/replay_golden.json`; C `tests/scanning/test_v212_limit_rejects.py` | `builders.confluence_limit_dropped(scenario, df, level_map, params) -> str \| None` (the drop reason `build_confluence_plan` returned None for); `_no_plan_reason` returns it first; live limit plans carry `limit_entry_f` |
| V212-4 | Shared fill rule `bar_outcome` | 1 | opus | C `swingbot/core/planning/limit_entry_rule.py`; C `tests/planning/test_limit_entry_rule.py` | `class BarOutcome(NamedTuple): kind: str  # "fill" \| "cancel" \| "none"; fill: float \| None; gap_stopped: bool`; `is_arm_limit(plan) -> bool` (`entry_type == "limit"` and `limit_entry_f is not None`); `tp1_reached(plan, high: float, low: float) -> bool` (inclusive); `bar_outcome(plan, *, open_: float \| None, high: float, low: float, touch: bool = False) -> BarOutcome` |
| V212-5 | Replay: arm limit path in `exit_sim_v2` (gap-through-stop realised, touch sensitivity) | 1 | opus | M `swingbot/core/planning/exit_sim_v2.py` (`_ENTRIES` dispatch helper, `_arm_limit_entry_v2`, `_gap_stopped_exit`); C `tests/planning/test_exit_sim_v2_arm_limit.py` | `simulate_exit_v2(..., touch_fill: bool = False)` keyword (ignored by non-arm plans); `ExitResult.exit_reason` values `"limit_expired"`, `"limit_tp1_cancel"`, `"filled_stopped_gap"` for arm plans; fill bar index readable as `res.entry_index` (writer confirms the existing field name and records it in the task) |
| V212-6 | Live: arm branch in `_step_limit` (shared rule, `filled_stopped_gap`, planned risk-cap, marketable at alert) | 2 | opus | M `swingbot/core/planning/plan_manager.py` (`_step_limit` dispatch, `_step_arm_limit`, `_fill_and_stop_gap`, `_session_open_for`, `_fill_pending` planned-risk helper); C `tests/planning/test_plan_manager_arm_limit.py` | event `"filled_stopped_gap"` (detail `entry_price`, `exit_price`, `live_price`, `stop_loss`, `leg`, `trade_id`); `"filled"` detail gains `"marketable_at_alert": True` only when the first poll in the alert session finds price ≤ L |
| V212-7 | Heat at fill: pure check, `fill_guard`, `cancelled_heat_at_fill` | 2 | opus | C `swingbot/core/edge/fill_heat.py`; M `swingbot/core/planning/plan_manager.py` (`__init__(..., fill_guard=None)`, guard call before the fill transition, `_manager()` wiring); C `tests/edge/test_fill_heat.py`; C `tests/planning/test_plan_manager_heat_at_fill.py` | `fill_heat.heat_at_fill_reason(*, open_trades: list, balance: float, risk_pct: float, ticker: str, sectors: dict \| None, cluster_chk: dict \| None, max_open: int \| None) -> str \| None` (`"heat"`, `"sector"`, `"cluster"`, `"max_open"`); `fill_heat.make_fill_guard(trade_log, account_cfg_fn, frames_fn) -> Callable[[TradePlanV2, float], str \| None]`; event `"cancelled_heat_at_fill"` (detail `entry_price`, `live_price`, `cap`), status reason `"heat_at_fill"` |
| V212-8 | Register both new events in every routing table; enforcement test | 2 | sonnet | M `swingbot/core/planning/plan_manager.py` (`PENDING_CANCEL_EVENTS` += `cancelled_heat_at_fill`; `NOTICE_EVENTS` += `filled_stopped_gap`; `_TRANSITION_LOG`); M `swingbot/commands/scanning/follow_notify.py`; M `swingbot/core/scanning/execution_embeds.py` (`_EVENT_KINDS`); M `swingbot/core/scanning/lifecycle_embeds.py` (`PLAN_EVENT_KINDS`); M `swingbot/core/planning/session_expiry.py`; C `tests/planning/test_v212_event_tables.py` | `tests/planning/test_v212_event_tables.py::ROUTING_TABLES` (name → collection), extended by V212-9 with the text tables |
| V212-9 | Alert and follow-up text: limit ticket and every follow-up instruction | 2 | sonnet | M `swingbot/core/presentation/instructions.py` (`ticket_for` limit branch, `_sides` entry-limit verbs, `_filled` arm line, `_BUILDERS`, `_cancel_why`, `_CANCEL_LEADS`); M `tests/planning/test_v212_event_tables.py` (`TEXT_TABLES` with `_BUILDERS`); C `tests/presentation/test_instructions_arm_limit.py` | `instructions.limit_order_lines(plan) -> list[str]` (the four G4 lines: "BUY LIMIT L" / "SELL LIMIT L", "On fill: stop S′, TP1 T1 (TP2 T2)", "Cancel the order if price trades at T1 before it fills", "Valid through the close of <date>") |
| V212-9b | Entry line and lifecycle embed fields for arm limit plans | 2 | sonnet | M `swingbot/core/scanning/plan_table.py` (`entry_line`); M `swingbot/core/scanning/lifecycle_embeds.py` (field builders, `_fields_for`, `_EVENT_FIELDS`); M `tests/planning/test_v212_event_tables.py` (`TEXT_TABLES` += `_EVENT_FIELDS`); C `tests/scanning/test_plan_table_arm_limit.py`; C `tests/scanning/test_lifecycle_embeds_arm_limit.py` | — (after V212-9) |
| V212-10 | Admin: pin the `levels-block` limit mapping (already on main since V151-10) with a render test | 2 | haiku | M `frontend/src/app/workspaces/trades/why/levels-block.spec.ts`; M `frontend/src/app/workspaces/trades/why/levels-block.ts` only if the test fails | `limit: {bullish: 'Buy limit', bearish: 'Sell limit', fallback: 'Limit entry'}` (existing) |
| V212-11 | Replay module: paired reference/arm alerts, census, entry rows, frictions at scoring | 3 | opus | C `swingbot/core/backtesting/confluence_limit_replay.py`; C `tests/backtesting/test_confluence_limit_replay.py` | `F_GRID = (1/3, 1/2, 2/3)`; `cell_key(f: float) -> str` (`"f0.333"`, `"f0.5"`, `"f0.667"`); `CELLS`; `paired_alerts(ticker, df, horizon_key, *, cells=F_GRID, gates=None) -> list[tuple[int, TradePlanV2, dict[str, TradePlanV2 \| str]]]` (in-scope alerts only; str = drop reason); `census_row(df, i, ref, arms) -> dict` (outcome-blind: scope, d, drops, `filled` per cell); `entry_rows(df, i, ref, arms, *, touch=False) -> list[dict]` (keys `key`, `arm` (`"ref"` or cell key), `ticker`, `horizon_key`, `direction`, `entry_date`, `fill_date`, `exit_date`, `entry`, `stop_loss`, `stop_pct`, `outcome`, `r_gross`, `r_net`, `exit_reason`, `gap_stopped`, `early_stop`, `atr14_pct`, `d_pct`); `net_r(direction, entry, exit_legs, risk, days) -> float`; `census(ticker, frame, horizons, window) -> list[dict]`; `replay_entries(ticker, frame, horizons, window, *, touch=False) -> list[dict]` |
| V212-12 | `portfolio_replay`: notional caps, cluster callback, skip reasons, taken keys | 3 | opus | M `swingbot/core/backtesting/backtest_wf.py` (`portfolio_replay` via helpers); C `tests/backtesting/test_portfolio_replay_v212.py` | `portfolio_replay(..., max_position_pct: float \| None = None, max_position_value: float \| None = None, cluster_fn: Callable[[list[dict], dict, float], bool] \| None = None, track_keys: bool = False)`; signals may carry `stop_pct`, `key`; result gains `notional_capped`, `skip_reasons` (dict), `taken_keys` (list) only when a new option is set |
| V212-13 | Measure script: stage chain, clauses, plateau, thin seal, checkpoint, ledger rows | 3 | opus | C `scripts/backtest/measure_confluence_limit.py`; C `tests/backtest_scripts/test_measure_confluence_limit.py` | `REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}`; `FILLS_SHARE = 0.5`; `WR_SLACK_PP = 2.0`; `THIN_PER_DIRECTION = 30`; `require_preregistration(path) -> None`; `portfolio_pass(rows, arm: str, *, sectors, cluster_fn) -> list[dict]`; `clauses(arm_rows, ref_rows) -> dict`; `neighbours(key) -> list[str]`; `plateau(results: dict) -> str \| None`; `thin(rows) -> bool`; CLI `census`, `rows`, `stage --stage {-1,0,1,2,3}`, `--checkpoint-dir`, `--out`, `--preregistration` |
| V212-14 | Disclosures: paired ΔR, D ranges, adverse/gap/stop-run, ATR, SPY down days, earnings, notional, heat, risk and ruin | 3 | sonnet | C `swingbot/core/backtesting/confluence_limit_disclosures.py`; M `scripts/backtest/measure_confluence_limit.py` (stage output calls it); C `tests/backtesting/test_confluence_limit_disclosures.py` | `disclosures(arm_rows, ref_rows, census_rows, *, spy, earnings, portfolio) -> dict`; `render_disclosures(d: dict) -> str`; `alert_volume_per_day(census_rows, arm_rows) -> float` |
| V212-15 | Pre-registration record, then Stage −1 census and `observed_n` | 4 | sonnet | C `docs/superpowers/results/<run-date>-v212-preregistration.md`; C `docs/superpowers/results/v212/stage-1.json` (run output) | the committed pre-registration path every later stage passes as `--preregistration`; `observed_n` per cell appended before Stage 0 |
| V212-16 | Stages 0..3 through `backtest-runner`; results doc; ledger rows | 4 | sonnet | C `docs/superpowers/results/v212/stage{0,1,2,3}.json`; C `docs/superpowers/results/<run-date>-v212-confluence-limit-entry.md`; M `docs/superpowers/results/preregistration-ledger.jsonl` (one row per look) | the verdict (PASS / NO-LIFT / UNDERPOWERED / THIN) and the winning cell, if any |
| V212-17 | Record the verdict (closed row or pass report), `/panel`, `/close-out` | 4 | sonnet | M `docs/claude/backtest-methodology.md` (§ Closed pre-registrations, on no pass); M `AGENTS.md` only if it mirrors that table; M plan/spec (moved by `/close-out`) | — |

18 ledger rows.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-06-v212-confluence-limit-entry_1-rule-and-replay.md` | V212-1 .. V212-5 | knob; geometry helper and plan field; builder wiring, drop reasons, knob-0 goldens; shared fill rule; `exit_sim_v2` arm path |
| 2 | `2026-11-06-v212-confluence-limit-entry_2-live-path.md` | V212-6 .. V212-10 (incl. V212-9b) | live arm fill/gap-stop/risk-cap; heat at fill; event registration; alert and follow-up text; entry line and embed fields; admin mapping pin |
| 3 | `2026-11-06-v212-confluence-limit-entry_3-measurement.md` | V212-11 .. V212-14 | paired replay module with frictions; portfolio pass with notional caps; measure script; disclosures |
| 4 | `2026-11-06-v212-confluence-limit-entry_4-runs-closeout.md` | V212-15 .. V212-17 | pre-registration, Stage −1..3 via `backtest-runner`, results and ledger, verdict record, `/panel`, `/close-out` |
