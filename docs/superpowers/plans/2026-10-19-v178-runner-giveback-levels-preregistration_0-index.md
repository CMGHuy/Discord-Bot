# v178 — Pre-registered test of runner give-back levels (range-multiple and profit-share arms): Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V178-3:" -A 400 docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_1-simulator-and-funnel.md`.

**Bump:** bot patch
**Edge:** harvest — locks in more of a runner's run before a reversal; the predicted paired ΔExpR against the live fixed 5% is small (|Δ| under 0.05R, sign unknown) and the stated base case is that every arm is refused at stage 0.
**Screen:** harvest-headroom docs/superpowers/results/2026-10-02-v123-runner-headroom.md
**Spec:** [2026-10-19-v178-runner-giveback-levels-preregistration-design.md](../specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md)
**Brief:** `.superpowers/briefs/2026-10-19-v178-runner-giveback-levels-preregistration.md`
**Worktree:** implement V178-1..V178-7 in `.claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration` (branch of the same name, created in V178-1; `docs/claude/document-lifecycle.md`); the merge to `main` is V178-7's last step. V178-8..V178-11 (the measurement runs, the one-shot VALIDATION, the record and close-out) run on `main` in the main tree.

## Goal

The live bot ends a runner (the half of a trade left open after TP1) when price
falls 5% from its best close since TP1 (v176). A fixed 5% is a different bet on
each stock: on a name whose daily range is 8% of price it is about half a day's
normal move, so ordinary noise ends the runner; on a calm name it is more than
two days' range. v176's own TRAIN reading was NO-LIFT (+0.003R), and 47% of its
give-back exits were followed by a new best price within ten bars. The partner
asked for a pullback level that adapts to each trade.

This plan builds the measurement the spec pre-registered and runs it once. Two
families of adaptive level are added to the exit simulators only: range
multiples (`best − k × ATR`, k ∈ {0.75, 1.0, 1.25}) and profit shares with a
range floor (`best − max(f × profit, 1.0 × ATR)`, f ∈ {0.25, 0.33, 0.50}). Each
is another tightening term on the runner stop, exactly the shape of the v176
rule: it never widens the stop, never goes beyond the runner floor, and is set
from data through bar `j` to first test bar `j + 1`. A bespoke script simulates
the same entries under all eight arms (six candidates, control A = the live 5%,
control B = no give-back), books frictions, and puts the six candidates through
the harvest funnel: stage −1 reachability on the pilot, stage 0 paired MDE on
the pooled fold-train window, stage 1 plateau plus a family-wide same-sign rule,
stage 2 the harvest walk-forward gate with at least 30 changed outcomes per
improving fold, and stage 3 a single VALIDATION shot for at most one surviving
arm, only after the partner says go.

Nothing the user or the live bot sees changes. The new modes are module
constants in `exit_sim.py` with default `pct`, which is the live v176 rule
byte-for-byte; `plan_manager.py`, `.env`, `config.py` and the live tick path are
untouched. A pass does not ship anything: wiring an arm into the live bot is
Phase B, its own spec and panel.

Success is a finished, honest record: one ledger row `v178-giveback-levels`,
a results doc with every gate reading, the seven descriptive blocks, the
Holm-adjusted p across the six arms, the week-clustered interval, the cells
looked at, and the closed-pre-registration row. A refusal at stage 0 for every
arm is the expected outcome and a complete result; the 5% stays live.

## Architecture

- **Simulator (V178-1, V178-2).** `exit_sim.py` gains `GIVEBACK_MODE` ∈
  `GIVEBACK_MODES` (`pct` default, `range`, `profit_share`), `GIVEBACK_K`,
  `GIVEBACK_F`, `GIVEBACK_FLOOR_ATR` (fixed 1.0) and their bounds, next to the
  v176 `GIVEBACK_EXTREME_BASIS`; a pure `giveback_allowance()` and a dispatcher
  `giveback_term()` (pct → the unchanged `giveback_level()`; adaptive modes →
  `best ∓ allowance`, None when ATR is NaN, zero, negative, infinite or
  missing). Both walks compute the term per bar from the give-back extreme and
  `atr_series.iloc[j]`, tighten through `tighter_stop`, and carry the level
  that set the stop (`_carried_level`) so `runner_stop_source` labels an
  ATR-dependent level set on an earlier bar "giveback", not "trail". The live
  `giveback_level(extreme, direction)` keeps its 2-arg signature and result.
- **Funnel logic (V178-3)** — `swingbot/core/backtesting/giveback_levels_funnel.py`,
  pure functions over the row contract below: the frozen arm table, windows
  from `arms.windows.STAGES`, paired ΔExpR with the ticker-cluster bootstrap,
  stage 0/1/2 decisions, the stage-3 pick, Holm, week-cluster interval,
  `cells_looked_at`, and `run_funnel()` which stops at the first stage that
  closes everything.
- **Descriptive blocks (V178-4)** — `swingbot/core/backtesting/giveback_levels_blocks.py`,
  the spec's seven blocks per arm plus per-horizon, concentration, arm-vs-B,
  near-duplicate (S vs R k=1.0), trend/chop split and outcome flips. Never gate.
- **Script (V178-5, V178-6)** — `scripts/backtest/measure_giveback_levels.py`,
  on the v176 template: one control-A entry pass per ticker, each entry
  re-simulated under every arm in-process (`arm_settings()` sets the module
  constants and config flag, restores after), frictions via `net_r`, rows
  persisted gzipped under `logs/v178/`, then `--stage report` runs the funnel
  on the rows. Stages: `pilot`, `train` (fold-train ∪ fold-test span, frames
  cut at the walk-forward end so no VALIDATION bar is run), `report`
  (`--basis close` gating, `--basis high_low` sensitivity), `validation` (the
  one shot, writes a `validate_component.py`-format arms file for
  `--stage validation --gate harvest --bespoke-instrument`).
- **Runs (V178-8..V178-10)** — `backtest-runner`, one invocation per stage,
  logged and backgrounded, with an explicit stop/continue gate after each.

## Global Constraints

- Default `GIVEBACK_MODE = "pct"` keeps the live v176 rule and every existing test byte-identical; no existing test is edited to make it pass (spec § Testing: "the existing v176 tests pass unmodified").
- `swingbot/core/planning/plan_manager.py`, `swingbot/config.py`, `.env.example`, `swingbot/scan_params.py` and `arms/reachability.py` are not modified. The new knobs are simulator-only module constants, never `.env` fields.
- `giveback_level(extreme, direction)` and `runner_giveback_pct()` keep their signatures and results (live calls them, `plan_manager.py:1116,1151-1157,1379`).
- "Never widens": every new level goes through `tighter_stop`; an ATR that is NaN, zero, negative, infinite or missing yields **no term** (None), never `_safe_atr_value`'s 2%-of-entry substitute.
- No lookahead: the level for bar `j + 1` uses the extreme through bar `j` and `atr_series.iloc[j]` (ATR(14) through bar `j`), the same index `_chandelier_ratchet` reads.
- `ExitResult` gains no field and `legs` keep exactly `fraction, exit_price, r, reason`.
- The arms are frozen: R k ∈ {0.75, 1.0, 1.25}; S f ∈ {0.25, 0.33, 0.50} with a fixed 1.0 × ATR floor; control A fixed 5% of the best close; control B give-back off. No other value is ever run.
- Windows come from `swingbot/core/backtesting/arms/windows.py:STAGES` and the instrument contract; no date or year literal in `scripts/backtest/measure_giveback_levels.py` (`tests/backtesting/instrument/test_date_literal_guard.py`); the script calls `instrument_cli.add_instrument_arg` and `instrument_cli.require_v1(instrument_cli.spec_from_args(args), ...)`.
- Data source `yfinance` (75-ticker cache), both engines (`StrategyEngine.iter_trades` + `replay_scenarios`), all ten horizons (`windows.ALL_HORIZONS`), `scale_out=True`, instrument v1, `SLIPPAGE_BPS` and `COMMISSION_PER_TRADE` non-zero (refused otherwise), R net of frictions via `expectancy_attribution.net_r`.
- One look: every output file is refused if it exists; VALIDATION is read once, only for the single stage-3 arm, only after the partner's explicit go (`AskUserQuestion`), and never for the high/low sensitivity.
- Stage rules, verbatim from the spec: stage 0 refuses when the measured pooled fold-train ΔExpR (arm − A) is below the paired MDE on the same pairs; stage 1 = `plateau_report()` per family with adopted value = highest pooled fold-train ΔExpR, **and** all three family arms have a fold-train ΔExpR of the adopted arm's sign on at least 2 of 3 fold-train windows (a stage-0-refused arm still counts as a neighbour); stage 2 = `backtest_wf.gate` (≥ 2 of 3 improving, none below −`GATE_MAX_DEGRADATION_R` = 0.05R, `GATE_MIN_N_PER_FOLD`) where a fold counts as improving only with ≥ 30 changed outcomes; stage 3 = all clauses of `evaluate_harvest`, `structurally_immune_to_wr=True`.
- At most one arm reaches stage 3: the best stage-2 mean paired ΔExpR among arms that passed stages 1–2; tie → family R.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`); the full suite runs once, in V178-7.
- Every function written or changed stays below cyclomatic complexity 15 (`scripts/dev/complexity_gate.py`).
- Every result doc states the v92 overlap disclosure (nearest v92 cell `trigger_r=2.50, mult=1.50`, ΔExpR −0.0045R to +0.0091R across its grid, best cell lower bound −0.0131R, context never a threshold) and the liquid-universe limit (75 liquid names; says nothing about thin names).
- Implementation tasks commit on the worktree branch, in scoped commits (one per task, more where a task says so); measurement and record tasks commit on `main`.

## Row contract (V178-5 produces, V178-3/V178-4/V178-6 consume)

One row per entry, the entry set taken from one control-A pass. Kept only when
control A's outcome is in `acceptance.CLOSED` (`win`, `loss`, `scratch`,
`timeout`). The pre-TP1 path is identical across arms, so every arm has the
same outcome class on a row.

```python
row = {
    "ticker": str,
    "source": "strategy" | "scenario",
    "strategy": str,          # plan.strategy, suffixed "#2", "#3", ... when the
                              # (ticker, strategy, horizon_key, signal_date, source,
                              # direction) key repeats inside one ticker: ArmTrade keys stay unique
    "horizon_key": str,       # one of windows.ALL_HORIZONS
    "direction": "bullish" | "bearish",
    "signal_date": "YYYY-MM-DD",
    "planned_rr": float | None,
    "risk": float,            # |control A entry fill - plan.stop_loss|
    "runner_fraction": float, # 1 - plan.tp1_fraction
    "regime": "trend" | "chop" | None,   # ADX(14) at the signal bar >= ADX_TREND_MIN (20.0) -> trend; NaN -> None
    "arms": {arm_id: arm_result for arm_id in ARMS},
}
arm_result = {
    "outcome": str,               # ExitResult.outcome
    "r_net": float,               # net_r(entry_price, plan.stop_loss, direction, legs)
    "runner_r": float | None,     # legs[1]["r"] on a 2-leg win, else None
    "entry_index": int, "exit_index": int, "exit_date": "YYYY-MM-DD",
    "exit_price": float,          # legs[-1]["exit_price"]
    "reason": str,                # runner_outcome or outcome
    "stop_source": str | None,    # ExitResult.runner_stop_source
    "tp1_index": int | None,      # first bar from entry_index+1 touching tp1; runners only
    "best": float | None,         # best close in [tp1_index, exit_index - 1]; runners only
    "best_index": int | None,     # bar of that best close
    "allowance_pct": float | None,# allowance / best at bar exit_index - 1 (A: 0.05; B: None); runners only
    "floor_bound": bool | None,   # S arms: f*|best - entry| < GIVEBACK_FLOOR_ATR*ATR at that bar; else None
    "stop_moves": int | None,     # changes of the runner stop in the v1 trace; runners only
    "gap_r": float | None,        # runner stop exits: min(0, (open[exit] - exit_price)*sign/risk) * runner_fraction
    "new_best_within_10": bool | None,  # runner stop exits: a close beyond `best` in the 10 bars after exit
    "shock": bool | None,         # runners: an earnings reaction session or a bar with
                                  # true range > TR_SHOCK_ATR (2.0) x ATR(14) in [tp1_index, exit_index]
}
```

"Changed" between arm X and control A on a row means
`(exit_index, exit_price)` differ (`giveback_levels_funnel.changed_count`); a
post-TP1 rule cannot flip `outcome`, so `arms.pairing.changed_outcomes` would
read zero and is not used for this count.

## Funnel contract (V178-3, consumed by V178-4, V178-6)

```python
# swingbot/core/backtesting/giveback_levels_funnel.py
PCT = 5.0
ARMS: dict[str, dict] = {
    "A": {"enabled": True, "mode": "pct"},  "B": {"enabled": False, "mode": "pct"},
    "R0.75": {"enabled": True, "mode": "range", "k": 0.75},
    "R1.00": {"enabled": True, "mode": "range", "k": 1.0},
    "R1.25": {"enabled": True, "mode": "range", "k": 1.25},
    "S0.25": {"enabled": True, "mode": "profit_share", "f": 0.25},
    "S0.33": {"enabled": True, "mode": "profit_share", "f": 0.33},
    "S0.50": {"enabled": True, "mode": "profit_share", "f": 0.50},
}
CONTROLS = ("A", "B")
CANDIDATES = ("R0.75", "R1.00", "R1.25", "S0.25", "S0.33", "S0.50")
FAMILIES = {"R": ("R0.75", "R1.00", "R1.25"), "S": ("S0.25", "S0.33", "S0.50")}
FAMILY_PARAM = {"R": ("k", (0.75, 1.0, 1.25)), "S": ("f", (0.25, 0.33, 0.50))}
MIN_CHANGED_PER_FOLD = 30
SAME_SIGN_MIN_WINDOWS = 2
def pooled_window() -> tuple[str, str]                      # STAGES["selection"].signal_window
def fold_train_windows() -> list[tuple[str, tuple[str, str]]]  # STAGES["selection"].folds -> [("2020", (lo, hi)), ...]
def fold_test_windows() -> list[tuple[str, tuple[str, str]]]   # STAGES["walkforward"].folds
def rows_in(rows: list[dict], window: tuple[str, str]) -> list[dict]
def arm_trades(rows: list[dict], arm: str) -> list[ArmTrade]
def changed_count(rows: list[dict], arm: str, *, against: str = "A") -> int
def paired_delta(rows, arm, *, against="A", n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict
    # {"arm", "against", "n", "changed", "delta_r", "ci_lo", "ci_hi", "p"}
def week_interval(rows, arm, *, against="A", n_resamples=WEEK_BOOTSTRAP_RESAMPLES) -> dict  # {"lo", "hi"}
def stage0(rows, arm, *, n_resamples=BOOTSTRAP_RESAMPLES) -> dict
    # paired_delta on rows_in(pooled_window) + {"mde_paired", "verdict": "RESOLVABLE" | "REFUSED"}
def fold_train_deltas(rows, arm) -> list[float | None]      # one per fold_train_windows()
def stage1(rows, family: str, stage0_by_arm: dict[str, dict]) -> dict
    # {"family", "adopted", "pooled", "fold_train", "plateau", "same_sign", "verdict": "PASS"|"FAIL"|"NO-CANDIDATE"}
def stage2(rows, arm) -> dict
    # {"arm", "folds": [{"test_year", "delta_expectancy_r", "n", "changed", "improving"}],
    #  "gate", "improving_folds", "mean_delta_r", "verdict": "PASS"|"FAIL"}
def pick_stage3(stage2_by_arm: dict[str, dict]) -> str | None
def holm(pvalues: dict[str, float | None]) -> dict[str, float | None]
def cells_looked_at(*, arms=6, fold_train=3, fold_test_arms=6, fold_test=3, horizons=10,
                    control_b=6, blocks=7, regime_arms=3, sensitivity=0) -> int   # defaults -> 150
def run_funnel(rows, *, n_resamples=BOOTSTRAP_RESAMPLES) -> dict
    # {"stage0": {arm: ...}, "stage1": {family: ...}, "stage2": {arm: ...},
    #  "stopped_at": "stage0" | "stage1" | "stage2" | None, "stage3_arm": str | None,
    #  "holm": {arm: p}, "week_interval": {arm: ...}}
```

## Blocks contract (V178-4, consumed by V178-6)

```python
# swingbot/core/backtesting/giveback_levels_blocks.py
SHAKEOUT_BARS = 10; QUICK_STOP_BARS = 3; TR_SHOCK_ATR = 2.0; ADX_TREND_MIN = 20.0
def book(rows, arm, *, risk_dollars: float) -> dict           # block 1 (arm and A side by side)
def allowance_share(rows, arm) -> dict | None                 # block 2 (p10, p50, p90)
def shakeouts(rows, arm) -> dict                              # block 3
def given_back(rows, arm, *, risk_dollars: float) -> dict     # block 4
def stop_moves(rows, arm) -> dict | None                      # block 5
def worst_week(rows, arm, *, risk_dollars: float) -> dict     # block 6
def shock_split(rows, arm) -> dict                            # block 7
def seven_blocks(rows, arm, *, risk_dollars: float) -> dict   # keys "1_book" .. "7_shock"
def per_horizon(rows, arm) -> dict
def concentration(rows, arm) -> dict                          # top2_horizon_share, long, short
def versus_b(rows, arm) -> dict
def near_duplicate(rows, arm) -> dict | None                  # S arms only
def regime_split(rows, arm) -> dict
def flips(rows, arm) -> int
def describe_arm(rows, arm, *, risk_dollars: float) -> dict
```

## Simulator contract (V178-1, consumed by V178-2, V178-5)

```python
# swingbot/core/planning/exit_sim.py
GIVEBACK_MODES: tuple[str, ...] = ("pct", "range", "profit_share")
GIVEBACK_MODE: str = "pct"
GIVEBACK_K: float = 1.0
GIVEBACK_F: float = 0.33
GIVEBACK_FLOOR_ATR: float = 1.0
GIVEBACK_K_BOUNDS = (0.25, 3.0)
GIVEBACK_F_BOUNDS = (0.05, 0.95)
def giveback_allowance(mode: str, extreme: float, entry: float, atr: float | None,
                       *, k: float, f: float) -> float | None
def giveback_term(extreme: float | None, entry: float, atr: float | None,
                  direction: str) -> float | None
def _giveback_term(ctx, j: int, extreme: float | None, atr_series) -> float | None
def _carried_level(runner_stop: float, level: float | None, carried: float | None) -> float | None
def _runner_bar_exit(ctx, j, runner_stop, floor, gb_level=None)   # 5th arg is now the level
# exit_sim_v2.py (V178-2): _runner_bar_v2(ctx, j, runner_stop, floor, gb_level=None);
# _giveback_ratchet and _stop_source are deleted once neither walk uses them.
```

## Script contract (V178-5/V178-6, consumed by V178-8..V178-10)

```
python scripts/backtest/measure_giveback_levels.py --stage pilot      [--basis close] [--out-dir D] [--rows-dir R] [--tickers ...] [--workers N] [--earnings-dir E]
python scripts/backtest/measure_giveback_levels.py --stage train      --basis close|high_low [...]
python scripts/backtest/measure_giveback_levels.py --stage report     --basis close|high_low [--resamples N]
python scripts/backtest/measure_giveback_levels.py --stage validation --arm <id> --preregistration <committed spec>
```
Outputs (defaults `--out-dir docs/superpowers/results/v178`, `--rows-dir logs/v178`):
`pilot-close.json`; `logs/v178/rows-train-<basis>.json.gz`; `funnel-close.json`;
`sensitivity-high_low.json`; `logs/v178/validation-arms.json` (validate_component
format: `{"provenance": {...}, "baseline": [A ArmTrade dicts], "component": [arm ArmTrade dicts]}`);
`validation-readings.json`. Python symbols: `arm_settings(arm)`, `stage_window(stage)`,
`frame_end(stage)`, `entry_row(...)`, `rows_for(...)`, `build_rows(...)`,
`write_rows(path, rows)`, `read_rows(path)` (V178-5); `main(argv)`, `_refusal(args, target)`,
`cmd_pilot`, `cmd_train`, `cmd_report`, `cmd_validation`, `validation_arms_blob(rows, arm)`,
`BESPOKE_REASON` (V178-6).

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V178-1 | V178-3, V178-4 | first task: creates the worktree the others work in |
| V178-2 | V178-3, V178-4 | after V178-1: `exit_sim_v2.py` imports `_giveback_term`, `_carried_level` and the new `_runner_bar_exit` semantics from V178-1 (contract dependency) |
| V178-3 | V178-1, V178-2, V178-4 | disjoint files; consumes only the row contract above |
| V178-4 | V178-1, V178-2, V178-3 | disjoint files; consumes only the row contract above |
| V178-5 | — | after V178-1 (reads `exit_sim.GIVEBACK_MODE/K/F`, `giveback_allowance`) and V178-3 (`ARMS`, `PCT`); V178-2 not required by code but must be merged on the branch before V178-6's tests run both walks |
| V178-6 | — | after V178-5 (same file `measure_giveback_levels.py` and its test file) and V178-3/V178-4 (`run_funnel`, `describe_arm`) |
| V178-7 | — | after every code task: the plan's single full-suite run, then the merge and bump |
| V178-8 | — | after V178-7: runs the merged script on `main`; the frozen block must be committed before any window is read |
| V178-9 | — | after V178-8's gate (every candidate refused at stage −1 stops the plan) |
| V178-10 | — | after V178-9's gate and only if exactly one arm survived stages 0–2; needs the partner's go |
| V178-11 | — | after V178-9 or V178-10, whichever ended the funnel: the record reads their outputs |

At most 2 implementers at once (V178-1 with V178-3, then V178-4 with V178-2).
V178-8..V178-10 each launch a long `backtest-runner` job; never run two heavy
replays at once (shared tree, CPU).

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-19-v178-runner-giveback-levels-preregistration_1-simulator-and-funnel.md` | V178-1..V178-4 | simulator modes in both walks, funnel logic, descriptive blocks |
| 2 | `2026-10-19-v178-runner-giveback-levels-preregistration_2-script-and-runs.md` | V178-5..V178-11 | measurement script, full suite and merge, the runs with their gates, VALIDATION shot, record and close-out |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V178-1 | Adaptive give-back modes in the v1 walk | 1 | opus | M `swingbot/core/planning/exit_sim.py`; C `tests/planning/test_giveback_levels.py` | `GIVEBACK_MODES`, `GIVEBACK_MODE`, `GIVEBACK_K`, `GIVEBACK_F`, `GIVEBACK_FLOOR_ATR`, `GIVEBACK_K_BOUNDS`, `GIVEBACK_F_BOUNDS`, `giveback_allowance(mode, extreme, entry, atr, *, k, f)`, `giveback_term(extreme, entry, atr, direction)`, `_giveback_term(ctx, j, extreme, atr_series)`, `_carried_level(runner_stop, level, carried)`, `_runner_bar_exit(..., gb_level)` |
| V178-2 | v2 walk parity and the pinned witnesses | 1 | opus | M `swingbot/core/planning/exit_sim_v2.py`, `swingbot/core/planning/exit_sim.py` (delete `_giveback_ratchet`, `_stop_source`); C `tests/planning/test_exit_sim_v2_giveback_levels.py` | `_runner_bar_v2(..., gb_level)`; v1 = v2 on every arm |
| V178-3 | Funnel logic: stages 0–2, stage-3 pick, Holm, cells | 1 | opus | C `swingbot/core/backtesting/giveback_levels_funnel.py`, `tests/backtesting/test_giveback_levels_funnel.py` | Funnel contract above (`ARMS`, `run_funnel`, `stage0/1/2`, `pick_stage3`, `holm`, `cells_looked_at`, `arm_trades`, `changed_count`, `paired_delta`, `week_interval`) |
| V178-4 | Descriptive blocks | 1 | sonnet | C `swingbot/core/backtesting/giveback_levels_blocks.py`, `tests/backtesting/test_giveback_levels_blocks.py` | Blocks contract above (`describe_arm`, `seven_blocks`, `regime_split`, `SHAKEOUT_BARS`, `QUICK_STOP_BARS`, `TR_SHOCK_ATR`, `ADX_TREND_MIN`) |
| V178-5 | Measurement script: arms, entries, rows | 2 | opus | C `scripts/backtest/measure_giveback_levels.py`, `tests/backtest_scripts/test_measure_giveback_levels.py` | `arm_settings`, `stage_window`, `frame_end`, `entry_row`, `rows_for`, `build_rows`, `write_rows`, `read_rows`; the row contract |
| V178-6 | Measurement script: stages, refusals, report, validation file | 2 | opus | M `scripts/backtest/measure_giveback_levels.py`, `tests/backtest_scripts/test_measure_giveback_levels.py` | CLI above, `cmd_pilot/train/report/validation`, `validation_arms_blob`, `BESPOKE_REASON`, output files |
| V178-7 | Full suite, merge, bot patch bump | 2 | sonnet | M `VERSION.json`, `version_history.json` (regenerated) | merged branch on `main` |
| V178-8 | Frozen block and stage −1 pilot (gate) | 2 | sonnet | C `docs/superpowers/results/v178/pilot-close.json`, the results doc's frozen block | pilot verdicts |
| V178-9 | Train simulation, stages 0–2 and the TRAIN-side sensitivity (gates) | 2 | sonnet | C `docs/superpowers/results/v178/funnel-close.json`, `docs/superpowers/results/v178/sensitivity-high_low.json` (only if an arm passes stage 0) | `stage3_arm` |
| V178-10 | Stage 3: the one VALIDATION shot (conditional, partner go) | 2 | sonnet | C `docs/superpowers/results/v178/validation-readings.json`, `docs/superpowers/results/v178/validation-gate.md`, `docs/superpowers/results/v178/validation-gate.json` | stage-3 verdict |
| V178-11 | Results doc, ledger row, closed row, /panel, /close-out | 2 | sonnet | C results doc; M `docs/superpowers/results/preregistration-ledger.jsonl`, `docs/claude/backtest-methodology.md`, `.claude/hooks/guardrails.py`; plan moved by `/close-out` | ledger row `v178-giveback-levels` |
