# v212 — Confluence limit entry partway to the support (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V212-11:" -A 400 docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_3-*.md`.

**Bump:** bot patch (the knob ships inert at 0; no observable difference until a pass and a partner decision)
**Split:** the live path (G4; written here as part 2, V212-6..V212-10 with V212-9b) moved to [v216](2026-11-06-v216-confluence-limit-live-path.md) on 2026-11-06 at the 20-task cap, renumbered V216-1..6; v216 is implemented only after a Stage 3 pass here. Task ids V212-6..V212-10 are retired, never reused.
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
  session open), used by `exit_sim_v2` (V212-5) here and by `plan_manager` in v216.
- **Live path:** not in this plan — v216 (`_step_limit` arm branch,
  heat at fill, event registration, alert text, admin mapping), gated on a
  Stage 3 pass here.
- **Measurement** (V212-11..14): `backtesting/confluence_limit_replay.py`
  (paired reference/arm alerts derived from one knob-0 replay, so both arms
  see the same plan stream and cooldown), `backtest_wf.portfolio_replay`
  gains notional caps, a cluster callback and per-reason skips;
  `scripts/backtest/measure_confluence_limit.py` (stage chain, clauses,
  plateau, thin seal, per-ticker checkpoint) and the disclosures module.
- **Runs** (V212-15..17, on `main`): pre-registration record before compute,
  Stage −1 → 3 through `backtest-runner`, results doc, ledger rows,
  closed-row or pass report, `/panel`, `/close-out`.

**Tech stack:** Python 3.11, pandas/numpy, pytest.

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

1. **Gap open through the stop on a pending arm limit.** Replay books a fill **at the open** and an exit at that same open: about 0R less frictions, with `outcome="loss"` because the stop fired, and `filled_stopped_gap`. The from-L reading lives only in the disclosed `gap_stop_r_from_limit` (spec rule 6, corrected 2026-11-06). The live counterpart is v216. It is never `cancelled_gap_through_stop` and never silently dropped. Owners: V212-4 (rule), V212-5 (replay).
2. **A bar that trades both L and TP1, and TP1 printed exactly at the level.** Both cancel (inclusive, conservative); a v131/v113 limit plan with the same bar still uses the strict `limit_cancelled`. Owners: V212-4, V212-5.
3. **A level at exactly 2% from M, and a missing level (`acceptance_level is None`).** Exactly 2% is out of scope (`clamped_distance` returns None) and the plan is today's; a missing level is out of scope, never a crash. Owners: V212-2, V212-11.
4. **A heat cap reached at the fill date in the portfolio pass.** The signal is skipped with its reason counted (`skip_reasons`), never opened over the cap; pending limits reserve nothing (signals dated at the fill). Owners: V212-12, V212-13b.
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
| D measurement | V212-11, V212-12 (parallel) → V212-13 → V212-14 | C `confluence_limit_replay.py` (11); `backtest_wf.py` (12); C `measure_confluence_limit.py` (13); C `confluence_limit_disclosures.py` + measure script (14) | 11 needs V212-3 and V212-5; 12 is disjoint (no contract with 11); 13 consumes both; 14 extends 13's script |
| E runs | V212-15 → V212-16 → V212-17 | results docs, ledger, methodology, plan/spec | on `main` after A–D merged and CI green; pre-registration precedes compute; verdict precedes close-out |

Group B may run beside V212-3 (disjoint files). Group D's V212-12 may run
beside group B.
Sequential edges named: `builders.py` (V212-2, V212-3) and
`measure_confluence_limit.py` (V212-13 → V212-13b → V212-13c → V212-14c).

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V212-1 | Knob `CONFLUENCE_LIMIT_ENTRY_F`: config field, ScanParams, `.env.example`, reachability row | 1 | sonnet | M `swingbot/config.py` (Field after `CONFLUENCE_STOP_DROP_PCT`, `searchable` set); M `swingbot/scan_params.py`; M `.env.example`; M `swingbot/core/backtesting/arms/reachability.py`; M `tests/market/test_v115_strategy_work_off.py` (knob table row); C `tests/test_config_v212_limit_entry.py` | `config.CONFLUENCE_LIMIT_ENTRY_F: float` (default 0.0); `ScanParams.confluence_limit_entry_f: float = 0.0` read in `from_config()`; `reachability.REGISTRY["CONFLUENCE_LIMIT_ENTRY_F"]` (REACHABLE, observed_by `C`, reason cites the dedicated v212 replay) |
| V212-2 | Limit geometry helper and `limit_entry_f` plan field | 1 | opus | M `swingbot/core/planning/builders.py`; M `swingbot/core/planning/plan_types.py` (`limit_entry_f`, `_OMIT_WHEN_NONE`); C `tests/planning/test_confluence_limit_geometry.py` | `builders.LIMIT_STOP_BUFFER = 0.0025`; `builders.LIMIT_EXPIRY_BARS = 3`; `builders.LIMIT_DROP_REASONS = ("limit_scope", "limit_stop_beyond_cap", "limit_rr_fail")`; `class LimitGeometry(NamedTuple): limit: float; stop_loss: float; level_distance_pct: float`; `confluence_limit_geometry(entry: float, level: float \| None, is_bull: bool, tp1: float \| None, f: float, min_rr: float) -> LimitGeometry \| str \| None` (None = out of scope, str = drop reason); `to_limit_plan(plan: TradePlanV2, geom: LimitGeometry, f: float) -> TradePlanV2` (deep copy: `entry_type="limit"`, `trigger_price=L`, `entry_price=None`, `stop_loss`, `status=PENDING` with a fresh history, `expiry_bars=3`, `limit_cancel_level=tp1`, `limit_strict_fill=True`, `limit_entry_f=f`, `stop_ceiling_pct=None`); `apply_confluence_limit(plan: TradePlanV2, level: float \| None, f: float, min_rr: float) -> TradePlanV2 \| str` (f == 0, non-market or out of scope → `plan` unchanged; drop → reason); `TradePlanV2.limit_entry_f: float \| None = None` |
| V212-3 | Wire the rule into `build_confluence_plan`; drop reasons in attach; knob-0 plan and replay goldens | 1 | opus | M `swingbot/core/planning/builders.py` (`build_confluence_plan` via a helper, `confluence_limit_dropped`); M `swingbot/core/scanning/analyze.py` (`_no_plan_reason`); C `tests/planning/test_v212_plan_golden.py`, C `tests/fixtures/v212/plan_golden.json`; C `tests/backtesting/test_v212_flag_off_golden.py`, C `tests/fixtures/v212/replay_golden.json`; C `tests/scanning/test_v212_limit_rejects.py` | `builders.confluence_limit_dropped(scenario, df, level_map, params) -> str \| None` (the drop reason `build_confluence_plan` returned None for); `_no_plan_reason` returns it first; live limit plans carry `limit_entry_f` |
| V212-4 | Shared fill rule `bar_outcome` | 1 | opus | C `swingbot/core/planning/limit_entry_rule.py`; C `tests/planning/test_limit_entry_rule.py` | `class BarOutcome(NamedTuple): kind: str  # "fill" \| "cancel" \| "none"; fill: float \| None; gap_stopped: bool`; `is_arm_limit(plan) -> bool` (`entry_type == "limit"` and `limit_entry_f is not None`); `tp1_reached(plan, high: float, low: float) -> bool` (inclusive); `bar_outcome(plan, *, open_: float \| None, high: float, low: float, touch: bool = False) -> BarOutcome` |
| V212-5 | Replay: arm limit path in `exit_sim_v2` (gap-through-stop realised, touch sensitivity) | 1 | opus | M `swingbot/core/planning/exit_sim_v2.py` (`_ENTRIES` dispatch helper, `_arm_limit_entry_v2`, `_gap_stopped_exit`); C `tests/planning/test_exit_sim_v2_arm_limit.py` | `simulate_exit_v2(..., touch_fill: bool = False)` keyword (ignored by non-arm plans); `ExitResult.exit_reason` values `"limit_expired"`, `"limit_tp1_cancel"`, `"filled_stopped_gap"` for arm plans; fill bar index readable as `res.entry_index` (writer confirms the existing field name and records it in the task) |
| V212-11 | Replay module: paired reference/arm alerts, census, entry rows, frictions at scoring | 3 | opus | C `swingbot/core/backtesting/confluence_limit_replay.py`; C `tests/backtesting/test_confluence_limit_replay.py` | `F_GRID = (1/3, 1/2, 2/3)`; `cell_key(f: float) -> str` (`"f0.333"`, `"f0.5"`, `"f0.667"`); `CELLS`; `paired_alerts(ticker, df, horizon_key, *, cells=F_GRID, gates=None) -> list[tuple[int, TradePlanV2, dict[str, TradePlanV2 \| str]]]` (in-scope alerts only; str = drop reason); `census_row(df, i, ref, arms) -> dict` (outcome-blind: scope, d, drops, `filled` per cell); `entry_rows(df, i, ref, arms, *, touch=False) -> list[dict]` (keys `key`, `arm` (`"ref"` or cell key), `ticker`, `horizon_key`, `direction`, `entry_date`, `fill_date`, `exit_date`, `entry`, `stop_loss`, `stop_pct`, `outcome`, `r_gross`, `r_net`, `exit_reason`, `gap_stopped`, `early_stop`, `atr14_pct`, `d_pct`); `net_r(direction, entry, exit_legs, risk, days) -> float`; `census(ticker, frame, horizons, window) -> list[dict]`; `replay_entries(ticker, frame, horizons, window, *, touch=False) -> list[dict]` |
| V212-11b | Replay module, part 2: entry rows (fill, gap stop, TP1 cancel, touch sensitivity) and `replay_entries` | 3 | opus | M `swingbot/core/backtesting/confluence_limit_replay.py`; tests per the task | `entry_rows`, `replay_entries` (see V212-11's row) |
| V212-12 | `portfolio_replay`: notional caps, cluster callback, skip reasons, taken keys | 3 | opus | M `swingbot/core/backtesting/backtest_wf.py` (`portfolio_replay` via helpers); C `tests/backtesting/test_portfolio_replay_v212.py` | `portfolio_replay(..., max_position_pct: float \| None = None, max_position_value: float \| None = None, cluster_fn: Callable[[list[dict], dict, float], bool] \| None = None, track_keys: bool = False)`; signals may carry `stop_pct`, `key`; result gains `notional_capped`, `skip_reasons` (dict), `taken_keys` (list) only when a new option is set |
| V212-13 | Measure script: stage chain, clauses, plateau, thin seal, checkpoint, ledger rows | 3 | opus | C `scripts/backtest/measure_confluence_limit.py`; C `tests/backtest_scripts/test_measure_confluence_limit.py` | `REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}`; `FILLS_SHARE = 0.5`; `WR_SLACK_PP = 2.0`; `THIN_PER_DIRECTION = 30`; `require_preregistration(path) -> None`; `portfolio_pass(rows, arm: str, *, sectors, cluster_fn) -> list[dict]`; `clauses(arm_rows, ref_rows) -> dict`; `neighbours(key) -> list[str]`; `plateau(results: dict) -> str \| None`; `thin(rows) -> bool`; CLI `census`, `rows`, `stage --stage {-1,0,1,2,3}`, `--checkpoint-dir`, `--out`, `--preregistration` |
| V212-13b | Measure script, part 2: Stage −1 census, populations, the three clauses, plateau, thin seal, portfolio pass | 3 | opus | M `scripts/backtest/measure_confluence_limit.py`; tests per the task | `clauses`, `plateau`, `thin`, `portfolio_pass` |
| V212-13c | Measure script, part 3: Stage 0..3, the stage runner, one-shot refusal, ledger rows, `stage` / `ledger` CLI | 3 | opus | M `scripts/backtest/measure_confluence_limit.py`; C `tests/backtest_scripts/test_measure_confluence_limit_stages.py` | `run_stage`, `STAGE_RUNNERS`, `ledger_rows` |
| V212-14 | Disclosures, part 1: paired ΔR, D ranges, adverse/gap/stop-run, ATR, SPY down days, earnings, notional, heat, risk and ruin | 3 | sonnet | C `swingbot/core/backtesting/confluence_limit_disclosures.py`; C `tests/backtesting/test_confluence_limit_disclosures.py` | `disclosures(arm_rows, ref_rows, census_rows, *, spy, earnings, portfolio) -> dict`; `render_disclosures(d: dict) -> str`; `alert_volume_per_day(census_rows, arm_rows) -> float` |
| V212-14b | Disclosures, part 2: notional-capped share, portfolio skip reasons, per-direction table, risk and ruin, `disclosures` and `render_disclosures` | 3 | sonnet | M `swingbot/core/backtesting/confluence_limit_disclosures.py`; tests per the task | `disclosures(...)`, `render_disclosures(d)` |
| V212-14c | Disclosures wired into `STAGE_RUNNERS` entries 1 and 3 (touch sensitivity, SPY, earnings) | 3c | sonnet | M `scripts/backtest/measure_confluence_limit.py`; M `tests/backtest_scripts/test_measure_confluence_limit_stages.py` | a `disclosures` key in the Stage 1 and Stage 3 files |
| V212-15 | Pre-registration record, then Stage −1 census and `observed_n` | 4 | sonnet | C `docs/superpowers/results/<run-date>-v212-preregistration.md`; C `docs/superpowers/results/v212/stage-1.json` (run output) | the committed pre-registration path every later stage passes as `--preregistration`; `observed_n` per cell appended before Stage 0 |
| V212-15b | Stage −1 census and `observed_n`, before Stage 0 | 4 | sonnet | C `docs/superpowers/results/v212/stage-1.json`, census rows; M pre-registration (`## observed_n`) | `observed_n` per cell |
| V212-16 | Stages 0..3 through `backtest-runner`; results doc; ledger rows | 4 | sonnet | C `docs/superpowers/results/v212/v212-stage{0,1,2,3}.json`; C `docs/superpowers/results/<run-date>-v212-confluence-limit-entry.md`; M `docs/superpowers/results/preregistration-ledger.jsonl` (one row per look) | the verdict (PASS / NO-LIFT / UNDERPOWERED / THIN) and the winning cell, if any |
| V212-17 | Record the verdict (closed row or pass report), `/panel`, `/close-out` | 4 | sonnet | M `docs/claude/backtest-methodology.md` (§ Closed pre-registrations, on no pass); M `AGENTS.md` only if it mirrors that table; M plan/spec (moved by `/close-out`) | — |

18 ledger rows.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-06-v212-confluence-limit-entry_1-rule-and-replay.md` | V212-1 .. V212-5 | knob; geometry helper and plan field; builder wiring, drop reasons, knob-0 goldens; shared fill rule; `exit_sim_v2` arm path |
| 3 | `2026-11-06-v212-confluence-limit-entry_3-measurement.md` | V212-11 .. V212-13 (incl. V212-11b) | paired replay module with frictions; portfolio pass with notional caps; measure script; disclosures |
| 3b | `2026-11-06-v212-confluence-limit-entry_3b-measurement-stages.md` | V212-13b, V212-13c, V212-14, V212-14b | census, clauses, plateau, thin seal, portfolio pass; stage chain and ledger rows; disclosures module |
| 3c | `2026-11-06-v212-confluence-limit-entry_3c-disclosures-wiring.md` | V212-14c | disclosures in the Stage 1 and Stage 3 files |
| 4 | `2026-11-06-v212-confluence-limit-entry_4-runs-closeout.md` | V212-15 .. V212-17 (incl. V212-15b) | pre-registration, Stage −1..3 via `backtest-runner`, results and ledger, verdict record, `/panel`, `/close-out` |

## Handoff

_Updated 2026-11-12 (session resumed at V212-15b). Main tree, not the worktree._

**Done:** V212-1..14c merged (`4497ddd8`); V212-15 pre-registration (`3aedb886`); V212-15b Stage −1 census → `REACHABLE`, `observed_n` filled, committed `0b0915e2`. The v212 worktree was fast-forwarded to main and holds no work of its own.

**In flight (V212-16 Step 1/2):** TRAIN entry rows, primary then `--touch`, started in the background with `--workers 8` via the scratch script `logs/v212/run_rows.sh` (git-ignored; it exports `MEASURE_ARMS_UNIVERSE=cache` and `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`, then runs `measure_confluence_limit.py rows --window train [--touch] --workers 8 --preregistration docs/superpowers/results/2026-11-11-v212-preregistration.md --checkpoint-dir logs/v212/ckpt-rows-train[-touch] --out docs/superpowers/results/v212`). Progress: `tail logs/v212/rows-train.log` (X/650); finish marker `logs/v212/rows.res` (`step1 exit=0`, `step2 exit=0`). A single worker would take ~24 h per leg.

**To resume after a crash or a new session:** re-run the same command(s); per-ticker checkpoints skip finished tickers. Never delete `logs/v212/ckpt-*`. If the process is dead, `bash logs/v212/run_rows.sh` (step 2 appends to its log).

**Next, in order:** (1) `python logs/v212/check_rows.py` on both rows files (scratch; text is in V212-16 Step 1; a failed assert is a wiring bug: stop and report). (2) Stage 0, then Stage 1, then Stage 2 (V212-16 Steps 2–4; `backtest-gate` before each, one runner at a time, `render_stage.py` for the numbers). (3) Commit the TRAIN files (V212-16 Step 8 commit (a)) **before** Stage 3. (4) Stage 3 is the one-shot VALIDATION run; never twice. (5) V212-17: verdict record, `/panel`, `/close-out`.

**Traps:** the driver names the Stage −1 file `v212-stageM1.json` (the plan says `stage-1.json`; `logs/v212/observed_n.py` was patched to match). No edit under `swingbot/` or `scripts/` until the last stage file. `CONFLUENCE_LIMIT_ENTRY_F` stays `"0"`. CI on the v212 merge push was not confirmed green (`gh run list --workflow=CI` finds no such workflow; the workflow is "Deploy Discord Swing Trade Bot to Hetzner"): check before Stage 3.
