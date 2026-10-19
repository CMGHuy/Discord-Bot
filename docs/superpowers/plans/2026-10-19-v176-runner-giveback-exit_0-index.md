# v176 — Runner give-back exit: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot minor
**Edge:** harvest
**Screen:** harvest-headroom docs/superpowers/results/2026-10-02-v123-runner-headroom.md
**Spec:** [2026-10-19-v176-runner-giveback-exit-design.md](../specs/2026-10-19-v176-runner-giveback-exit-design.md)
**Brief:** `.superpowers/briefs/2026-10-19-v176-runner-giveback-exit.md`
**Worktree:** implement in a `.claude/worktrees/` worktree named per `docs/claude/document-lifecycle.md` (tasks V176-1..V176-10); V176-11 onwards run on `main` in the main tree.

## Goal

A runner (the part of a position left open after TP1 is banked) today exits
only on the runner floor (`entry + 2/3 × (TP1 − entry)`) or the ATR
chandelier trail. On a high-volatility name the chandelier stays wider than
the floor for the whole run, so a runner can give back most of a large move
before it exits. The live RKLB short (plan `47f7fd16-…-376c85`) is the case
that prompted this: best price 49.94, bounce to about 52.30, working stop
still 59.11.

Once this ships, every runner also carries a **give-back stop** 5% off its
best price since TP1 (`E × (1 − p)` long, `E × (1 + p)` short). The
effective stop is the tightest of the existing terms and the give-back
level, so it only ever tightens; the floor and the chandelier keep working
unchanged. It is on by default (the partner's decision) and reaches runners
already open at deploy on their first tick, because the tighten step runs on
every tick, not only on a new extreme. One pure helper, `giveback_stop`,
carries the arithmetic so the live tick path, the bar catch-up path and both
simulators cannot drift on the formula. No new exit reason string is added:
the close stays `tp1_runner_trail` / `runner_trail`, and a `stop_source`
tag (`floor` / `trail` / `giveback`) rides beside it on the live runner leg
and on the simulator result so the close embed and the measurement can tell
a give-back exit apart.

It leaves alone: plans before TP1, legacy trades without a `plan_id`, TP2
handling, the adaptive trail and the structure exit (both off in
production; the give-back is ordered before the structure step so enabling
it later cannot drop the give-back), and every closed pre-registration's
recorded result.

Success is measured two ways. Operationally: the deploy gate lists every
open `PARTIAL` plan's old and new stop before the image restarts, and after
deploy the RKLB runner's `working_stop` reads 52.44 (or the plan closed on
its first tick if price was already past it). Statistically, after ship and
as a report, not a gate: one TRAIN-only paired look (flag off vs on at 5%,
v123's instrument, frictions in both arms) giving pooled per-trade runner-leg
ΔR with a ticker-cluster bootstrap interval and `mde_paired`, one ledger row.
The spec's prior is a pooled effect near 0.01R, |Δ ExpR| < 0.05R; this
ships on the partner's decision, not on a predicted lift.

## Architecture

- **Pure arithmetic** in `swingbot/core/planning/exit_sim.py` next to
  `chandelier_stop` (V176-1): `giveback_stop`, the clamp
  `runner_giveback_pct`, the flag-aware `giveback_level`, `tighter_stop`
  and `runner_stop_source`; re-exported from `plan_engine.py` like
  `chandelier_stop`. Config reads happen at call time (SIGHUP hot reload).
- **Live tick path** (`PlanManager._step_partial`, V176-2): new
  `_track_extreme` (persists `runner_high_close` on every tick, independent
  of `atr_fn`) then `_apply_giveback` (tightens `working_stop`, persists and
  logs only when it moves), both before `_structure_runner_step`; the
  chandelier reads the already-tracked extreme. The closing leg carries
  `stop_source` through `_close_runner`'s existing `extra`.
- **Bar catch-up path** (`_check_bar_partial`, V176-3): the same tighten
  from the *stored* extreme before the bar test; the checked bar's own
  high/low is never read for `E` (no intrabar lookahead).
- **Close embed** (V176-4): one "Give-back" line when the leg's
  `stop_source == "giveback"`.
- **Simulators** (V176-5): `_giveback_ratchet` applied after the chandelier
  from the extreme close, effective the next bar, in both `_runner_phase`
  and `exit_sim_v2._runner_v2`; `ExitResult.runner_stop_source` carries the
  source out (legs untouched, so no exact-dict test breaks).
- **Tests pinned to pre-v176 numbers** (V176-6) are pinned flag-off or
  re-pinned per the decision table below.
- **Ship tooling** (V176-7..9): the deploy-gate scripts, the TRAIN
  measurement script and the live-book counterfactual script, all tested
  before the single full-suite run (V176-10), so post-merge tasks change no
  code.

**Tech Stack:** Python 3.11, pandas/numpy, pytest (Postgres-backed
`PlanStore` via the autouse `_store_database` fixture), discord.py embeds,
Docker Compose on the Hetzner VM.

## Global Constraints

- Formula, verbatim from the spec: long `giveback = E × (1 − p)`, short `giveback = E × (1 + p)`, `p = RUNNER_GIVEBACK_PCT / 100`; effective stop long `max(working_stop, giveback)`, short `min(working_stop, giveback)`. It only ever tightens. `E is None` → no give-back term.
- `E` is `plan.runner_high_close` (live: extreme **tick** since TP1, extended-hours ticks included); simulator: extreme **close**, effective the next bar.
- Config: `RUNNER_GIVEBACK_ENABLED` bool default `true`; `RUNNER_GIVEBACK_PCT` float default `5.0`, read through a clamp to `[0.5, 49]`; Field `min=0.5`, `max=49.0` so the admin save path enforces the same range. Both hot-reloaded, read at call time, never cached; `search_class` stays `"excluded"`.
- Off does not loosen: a persisted `working_stop` never widens; no automatic revert.
- No new exit reason string: live `tp1_runner_trail` / `tp1_runner_be`, sim `runner_trail` / `runner_be`. `stop_source` ∈ {`floor`, `trail`, `giveback`}.
- Give-back runs before `_structure_runner_step` on every tick (not only on a new extreme).
- Bar path uses the stored extreme, never the checked bar's own high/low.
- No schema migration: `runner_high_close`, `working_stop` and leg `extra` already exist; `stop_source` is an additive leg key (`schema-evolution.md`).
- Every function written or changed stays at cyclomatic complexity < 15 (`_step_partial` is C=11 today: new logic lives in the new helpers).
- Measurement: TRAIN `2020-01-01..2023-12-31` only, VALIDATION neither run nor read; 75-ticker local cache; `StrategyEngine.iter_trades` + `replay_scenarios`; all ten horizons; `scale_out=True`; non-zero frictions both arms; arms off vs on at 5%, same entries; one look, one ledger row; win rate not reported as a result.
- Closed pre-registrations are not re-run because of the default change.
- Production: only through `scripts/ops/ssh-hetzner.sh`; the deploy gate list is shown to the partner and recorded **before** `git push origin main` (the push triggers the deploy workflow).
- Per-task verification is `python scripts/dev/testrun.py file <test>`; one full suite (V176-10) as the last code task.

## Parallelisation

Disjoint-file, no-contract-dependency pairs may run together (at most 2 implementers at once):

- **V176-1 first, alone.** Every other task consumes its helpers or config fields.
- **V176-2 → V176-3 sequential:** same file (`plan_manager.py`) and same new test file (`tests/planning/test_plan_manager_giveback.py`); V176-3 also calls `_apply_giveback` / `_runner_stop_extra` created by V176-2.
- **V176-4 parallel with V176-2, V176-3, V176-5:** touches only `lifecycle_embeds.py` and a new embed test; it consumes only the leg-key contract fixed in this ledger, not V176-2's code.
- **V176-5 parallel with V176-2/V176-3/V176-4:** `exit_sim.py` / `exit_sim_v2.py` and a new sim test, disjoint from `plan_manager.py`. Sequential after V176-1 because both edit `exit_sim.py`.
- **V176-5 → V176-6 sequential:** the pinned goldens move only once the simulator applies the give-back; V176-6 also strips V176-5's new `ExitResult` field in the witness.
- **V176-7 parallel with V176-2..V176-6:** new `scripts/ops/` files and a new `tests/scripts/` file; consumes only V176-1's `giveback_stop` / `tighter_stop`.
- **V176-8 after V176-5** (reads `ExitResult.runner_stop_source` and `exit_sim.GIVEBACK_EXTREME_BASIS`); parallel with V176-6 and V176-7 (disjoint files).
- **V176-9 after V176-2 and V176-5** (reads leg `stop_source` and simulates the flag-off counterfactual); parallel with V176-6/7/8.
- **V176-10 after V176-1..V176-9:** the one full-suite run covers all code.
- **V176-11 → V176-12 → V176-13 → V176-14 strictly sequential:** merge before deploy (the push deploys); the measurement is after ship by the spec ("after ship, reported"); `/panel` and `/close-out` need the measurement recorded.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-19-v176-runner-giveback-exit_1-live-path.md` | V176-1..V176-4 | helpers + config, live tick path, bar path, close embed |
| 2 | `2026-10-19-v176-runner-giveback-exit_2-simulator.md` | V176-5..V176-6 | simulator parity, pinned/golden tests |
| 3 | `2026-10-19-v176-runner-giveback-exit_3-ship.md` | V176-7..V176-14 | gate/measurement/counterfactual scripts, full suite, merge+bump, deploy gate + deploy, TRAIN measurement, panel + close-out |

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V176-1 | `giveback_stop` helpers + config fields | 1 | sonnet | M `swingbot/core/planning/exit_sim.py`, M `swingbot/core/planning/plan_engine.py`, M `swingbot/config.py`, M `.env.example`, C `tests/planning/test_giveback_stop.py`, C `tests/infra/test_runner_giveback_config.py` | `exit_sim.GIVEBACK_PCT_BOUNDS = (0.5, 49.0)`; `giveback_stop(extreme: float, pct: float, direction: str) -> float` (pct in percent, `ValueError` unless `0 < pct < 100`); `runner_giveback_pct() -> float` (clamps `config.RUNNER_GIVEBACK_PCT`); `giveback_level(extreme: float \| None, direction: str) -> float \| None` (None when flag off or `extreme is None`); `tighter_stop(stop: float, other: float \| None, is_bull: bool) -> float`; `runner_stop_source(stop: float, floor: float, giveback: float \| None) -> str` (`"floor"` if `stop == floor`, else `"giveback"` if `stop == giveback`, else `"trail"`); all five re-exported from `plan_engine`; `config.RUNNER_GIVEBACK_ENABLED: bool`, `config.RUNNER_GIVEBACK_PCT: float` (section `"Exit quality"`) |
| V176-2 | Live tick path: track extreme, apply give-back, `stop_source` | 1 | sonnet | M `swingbot/core/planning/plan_manager.py`, C `tests/planning/test_plan_manager_giveback.py`, M `tests/planning/test_plan_manager_structure_exit.py` | `PlanManager._track_extreme(self, plan, price: float, is_bull: bool) -> bool` (True when `E` moved; persists); `PlanManager._apply_giveback(self, plan, price: float) -> None` (tightens + persists + `_plan_line("giveback stop", …)` only on a move); `PlanManager._ratchet_chandelier(self, plan, is_bull: bool, entry: float, moved: bool) -> None` (no `price` arg; reads `plan.runner_high_close`); `PlanManager._runner_stop_extra(self, plan, stop: float) -> dict`; **leg keys:** always `"stop_source"`; when `"giveback"` also `"giveback_pct": float`, `"giveback_extreme": float`, `"giveback_stop": float` |
| V176-3 | Bar catch-up path tightens before the bar test | 1 | opus | M `swingbot/core/planning/plan_manager.py`, M `tests/planning/test_plan_manager_giveback.py` | `_check_bar_partial` calls `_apply_giveback(plan, bar_open)` before its test and passes `extra=self._runner_stop_extra(plan, stop)` |
| V176-4 | Close embed give-back line | 1 | sonnet | M `swingbot/core/scanning/lifecycle_embeds.py`, C `tests/scanning/test_giveback_embed.py` | `lifecycle_embeds._giveback_line(plan, detail: dict) -> str \| None` → e.g. `"5% give-back from the low of 49.94: stop 52.44"` (`high` for bullish, `low` for bearish; pct via `f"{pct:g}%"`, prices `:.2f`); field name `"Give-back"`, `inline=False` |
| V176-5 | Simulator parity in `exit_sim` and `exit_sim_v2` | 2 | opus | M `swingbot/core/planning/exit_sim.py`, M `swingbot/core/planning/exit_sim_v2.py`, C `tests/planning/test_exit_sim_giveback.py` | `exit_sim.GIVEBACK_EXTREME_BASIS: str = "close"` (`"close"` \| `"high_low"`, measurement-only module constant, not config); `_giveback_ratchet(ctx, extreme: float, runner_stop: float) -> float`; `ExitResult.runner_stop_source: str \| None = None` (last dataclass field; None for non-stop runner exits and single-leg walks); `_runner_phase(...) -> (price, index, reason, stop_source)`; `exit_sim_v2._runner_v2(...) -> (price, index, reason, kind, stop_source)`; `exit_sim_v2._booked(ctx, outcome, exit_index, legs, runner_outcome=None, runner_stop_source=None)` |
| V176-6 | Pinned and golden tests: flag-off pins and re-pins | 2 | sonnet | M `tests/backtesting/test_pullback_dryup_witness.py`, M `tests/planning/test_exit_sim_scaleout_witness.py`, M `tests/backtesting/test_v139_flag_off_golden.py`, M `tests/backtesting/test_v129_flag_off_golden.py`, M `tests/backtesting/test_v131_witness.py`, M `tests/market/test_v113_horizon_witness.py`, M `tests/backtesting/test_headroom_witness.py`, M `tests/backtesting/test_runner_structure_parity.py`, M `tests/planning/test_exit_sim_runner_structure.py`, M `tests/scripts/test_runner_headroom.py`; conditionally (only if they move) the numeric tests in the decision table | `pin_code_defaults(monkeypatch, *, giveback: bool = False) -> None` (code defaults, then `RUNNER_GIVEBACK_ENABLED = giveback`) |
| V176-7 | Deploy-gate scripts (prod read-only rows + local gate table) | 3 | sonnet | C `scripts/ops/partial_runner_rows.py`, C `scripts/ops/giveback_deploy_gate.py`, C `tests/scripts/test_giveback_deploy_gate.py` | `partial_runner_rows.py`: piped to `docker compose exec -T bot python -` on the **old** image (uses only `PlanStore().open_plans()` and `get_current_price`), prints a JSON list of `{plan_id, ticker, direction, entry_price, stop_loss, tp1, working_stop, runner_high_close, last_price}` for `PARTIAL` plans; `giveback_deploy_gate.py`: `gate_row(row: dict, pct: float) -> dict` (adds `floor`, `current_stop`, `giveback_stop`, `new_stop`, `past`), `render_table(rows: list[dict]) -> str` (markdown), `main(argv: list[str] \| None = None) -> int` (`--rows <json path>`, `--pct 5.0`) |
| V176-8 | TRAIN paired measurement script | 3 | opus | C `scripts/backtest/measure_runner_giveback.py`, C `tests/backtest_scripts/test_measure_runner_giveback.py` | CLI `python scripts/backtest/measure_runner_giveback.py --out-dir docs/superpowers/results/v176 [--basis close\|high_low] [--tickers T ...] [--workers N]`; writes `<out-dir>/train-<basis>.json`; functions `paired_trades(ticker: str, df, *, basis: str) -> list[dict]`, `summarise(rows: list[dict]) -> dict` |
| V176-9 | Live-book give-back counterfactual script | 3 | sonnet | C `scripts/reports/giveback_live_counterfactual.py`, C `tests/scripts/test_giveback_live_counterfactual.py` | `counterfactual_exit(plan: dict, bars) -> dict`; `main(argv=None) -> int`; prints `"no conclusion below 30 give-back exits"` while `n < 30` |
| V176-10 | Full suite (the plan's one full run) | 3 | haiku | none | — |
| V176-11 | Merge to `main` + bump bot minor + regenerate version history | 3 | haiku | M `VERSION.json`, M `version_history.json` | merged `main` (not pushed) |
| V176-12 | Deploy gate, deploy, verify RKLB | 3 | sonnet | C `docs/superpowers/results/2026-10-19-v176-deploy-gate.md` | gate table recorded before the push |
| V176-13 | TRAIN measurement run + ledger row | 3 | opus | C `docs/superpowers/results/v176/train-close.json`, C `docs/superpowers/results/v176/train-high_low.json`, C `docs/superpowers/results/2026-10-19-v176-giveback-train.md`, M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger id `v176-giveback` |
| V176-14 | `/panel` pre-close-out and `/close-out` | 3 | sonnet | M plan files (moved to `implemented/` by `/close-out`) | — |

### Pinned-test decisions (spec § Risks, "decided per test")

Rule: a **witness or golden** exists to prove an unrelated change did not
move numbers, so it is **pinned flag-off** and its fixture is never
regenerated. A test of the **current engine behaviour** is **re-pinned** to
the newly measured value (with a `# v176: give-back on` comment) if it
moves. "If moved" rows are decided by running the test in V176-6; a row
that does not move gets no edit.

| Test | Decision | Why |
|---|---|---|
| `tests/planning/test_exit_sim_scaleout_witness.py` (+ `fixtures/scale_out_witness.sha256`) | flag-off; drop `runner_stop_source` from `asdict` before hashing; fixture unchanged | byte-identity witness of the v123 refactor |
| `tests/backtesting/test_v139_flag_off_golden.py` | flag-off | docstring: "never regenerate it" |
| `tests/backtesting/test_v129_flag_off_golden.py` | flag-off | same |
| `tests/backtesting/test_v131_witness.py` | flag-off; drop `runner_stop_source` if it dumps `asdict` | witness |
| `tests/market/test_v113_horizon_witness.py` | flag-off | witness |
| `tests/backtesting/test_headroom_witness.py` | flag-off | witnesses v123's headroom instrument, the spec's cited baseline |
| every `pin_code_defaults` caller (`instrument/golden.py`, `test_v1_golden.py`, `test_live_constructor_replay.py`, `test_constructor_parity.py`, `test_fills_costs_replay.py`, `arms/test_engine_instrument.py`, `test_pullback_dryup_witness.py`, `tests/planning/test_exit_sim_v2_walk.py`, `test_exit_sim_v2_entry.py`, `tests/backtest_scripts/test_measure_fib_diagnostic.py`) | flag-off through `pin_code_defaults(giveback=False)` (the default) | goldens captured on pre-v176 code defaults |
| `tests/backtesting/test_v74_no_behaviour_change.py` | flag-off if moved | witness (plans expected exit-independent) |
| `tests/backtesting/test_runner_structure_parity.py`, `tests/planning/test_exit_sim_runner_structure.py` | flag-off | isolate the structure rule |
| `tests/scripts/test_runner_headroom.py` | flag-off | v123 instrument |
| `tests/planning/test_exit_sim_acceptance.py`, `tests/planning/test_acceptance_runner_aggregation.py`, `tests/backtesting/test_acceptance_replay.py` | flag-off if moved | they test the acceptance exit, not the runner |
| `tests/backtesting/test_backtest_engine.py`, `tests/planning/test_exit_sim_scaleout.py` | re-pin if moved | they test current engine output |
| `tests/planning/test_plan_manager_structure_exit.py` (existing tests) | flag-off autouse fixture, in V176-2 | isolate the structure rule; V176-2 adds the give-back-first test with the flag on |
| `tests/planning/test_plan_manager_partial.py`, `test_plan_manager_feed.py`, `test_near_stop_event.py`, `test_plan_manager_gaps.py` | re-pin if moved, in V176-2 / V176-3 | live behaviour is default-on |
