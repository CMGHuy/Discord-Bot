# v163 Idea screen: a trailing-exit race shape for momentum ideas. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief V163-3` or `grep -n "^### Task V163-3" -A 300 docs/superpowers/plans/2026-10-15-v163-screen-trail-race_*.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-10-15-v163-screen-trail-race-design.md`](../../specs/implemented/2026-10-15-v163-screen-trail-race-design.md) (all sections; every applied `## Panel review` finding is a requirement)
**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)

**Goal:** Let a Stage −2 screen idea declare `RACE = "trail"` and be raced (events and matched null alike) through a chandelier 3 ATR trailing stop with no target, while every existing fixed idea's race, null, results doc and ledger row stay byte-identical; plus an A/A calibration that shows the unchanged pass rule rarely passes noise under the trail shape.

**Architecture:** A new `swingbot/core/backtesting/screen/trail.py` holds the vectorised trail race (`race_trail`, its own `_first_exit_trail` over a per-row, per-bar stop matrix). `race.py` grows two outcome codes (appended), a per-shape outcome table and a `race_for(shape)` dispatcher (lazy import of `trail`, so no import cycle); `run_book` and `null.matched_null` take `shape`. `Idea` carries `race_shape`, validated with the trail cap floor. `scripts/backtest/screen_idea.py` passes the shape through, renders per shape, and for trail ideas only adds a "Trail race" section (N, overlap skips, timeout share and mean R per book, a 2 × slippage ΔExpR line). A standalone `scripts/backtest/screen_trail_calibration.py` drives the real `screen_ticker` + `verdict.decide` on seeded fat-tailed synthetic data.

**Tech Stack:** Python 3.11, numpy/pandas, pytest via `scripts/dev/testrun.py`, radon.

## Progress

Complete: V163-1..V163-10 merged to main. A/A calibration false-pass 6/200 = 3.0%, coverage 91.5%, mean N 794.3 (docs/superpowers/results/2026-10-16-trail-race-calibration.md). Panel (quant-researcher, quant-engineer, veteran-trader): no BLOCKING, advisories only.

## Where to work

- **Branch and worktree:** `2026-10-15-v163-screen-trail-race`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race` (written `$WT` below). The main tree is `$R` = `E:/Documents/Private/Projects/Discord-Bot`. V163-1 Step 0 creates the worktree with the `worktree-lifecycle` skill (reuse it if `git worktree list` already shows it); name `$WT` in every subagent dispatch.
- **Never `cd`** (it breaks the guardrail hooks). Use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/...` resolves test paths against `$WT`.
- **This plan file is committed on `main`.** Only the implementation is branched. Each task commits on the branch. After every task, `git -C $R status --short` must show the main tree unchanged.

## Global Constraints

- **Bump: none.** No task edits `VERSION.json` or `version_history.json`. Only `swingbot/core/backtesting/screen/`, `scripts/backtest/`, `tests/`, `docs/claude/backtest-methodology.md`, `AGENTS.md` and `docs/superpowers/results/` change. No running bot or UI code changes.
- **Fixed path byte-identical.** A fixed idea's race, null, results doc and ledger row are unchanged. `OUTCOMES` grows only by appending `"trail"`, `"gap_trail"` (indices 5 and 6). The existing race, null and screen-script tests pass **untouched** (only additions to those files, and the two call-site renames V163-2 makes to `_mix`/`_render_arms` callers inside `screen_idea.py`).
- **Trail rule, verbatim from the spec:** entry open of t+1; 1R = 1.5 × ATR14[t]; initial stop entry − 1R; no target; `stop_j = max(entry − 1R, max(High[t+1 .. j−1]) − 3 × ATR14[t])`; bar j's own high never raises bar j's stop; the stop never moves down; ATR frozen at t. Exits in order on bar j with `raised_j = stop_j > entry − 1R` (strictly): open ≤ `stop_j` → exit at the open, `gap_stop` / `gap_trail`; else low ≤ `stop_j` → exit at `stop_j[row, j]`, `stop` / `trail`; after bar t+cap → close, `timeout`. `r` always in the initial 1R; costs as the fixed race (`apply_frictions` both fills, then `commission_r()` / the passed commission).
- **Numerics:** the running high is `np.maximum.accumulate` over the event's high matrix shifted one column right with column 0 = `-inf` (never NaN).
- **One shape per idea:** `race_shape` pinned per registered idea in `tests/backtesting/screen/test_ideas_registry.py` (`"fixed"` for all six). A trail idea needs `time_cap_bars >= 60`.
- **Unchanged:** K = 20, `null.eligible_mask`, `race.non_overlapping`, warm-up mask, window 2010–2019 / events from 2011, PIT universe, the four pass clauses in `verdict.py`. The 2 × slippage line is printed, never gating.
- **No lookahead** (`no-lookahead` skill territory for V163-3): `stop_j` reads highs of bars t+1..j−1 only.
- **Closed ideas stay closed under either shape** — no task re-screens anything; the calibration never reads `data/backtest_cache_ext` or `data/backtest_cache`.
- **Complexity < 15** for every function written or changed (`python -m radon cc -s -n C <files>` prints nothing).
- **Per-task verification is the narrow run** (`python $WT/scripts/dev/testrun.py file <test>`); one full-suite run as the final task (V163-10).

## Deviations from the spec text (controller decisions, binding)

1. **Screen-script tests live in `tests/scripts/test_screen_idea.py`** (where they are today), not `tests/backtesting/screen/`. The calibration smoke test likewise goes in `tests/scripts/test_screen_trail_calibration.py`. Both directories are already in suites; no `tests/suites.toml` edit.
2. **The trail `CAP >= 60` refusal lives in `Idea.__post_init__`** (beside the other `ValueError`s), keyed on `time_cap_bars` when `race_shape == "trail"`. `_load` still refuses such a module, because it constructs an `Idea`; the check is testable without a fake module.
3. **`race.race_for` imports `trail` lazily inside the function**, so `trail.py` can import `race` (for `STOP_ATR`, `OUTCOMES`, `RaceResult`, `_check_positions`) without a cycle.
4. **Rendering per shape:** `_mix` and `_render_arms` take the shape's own outcome tuple (`race.SHAPE_OUTCOMES[idea.race_shape]`; fixed = the first five). A test pins a fixed idea's rendered doc byte-identical to a literal captured on `main @ 316c57e9`, before any change.
5. **`TickerScreen` gains `null_timeout_r` and `stressed`** (defaults, so the hand-built `TickerScreen(...)` in the existing test keeps working). Fixed ideas leave them empty / `None` and render nothing new.
6. **The overlap-skip count is already printed** in the universe table; the trail doc's new "Trail race" section restates it beside N.
7. **AGENTS.md mirror** amends the Stage −2 text at `AGENTS.md:161-170` in the same commit as the `backtest-methodology.md` amendment; `tests/hooks/test_codex_mirror.py` must pass.
8. **No guardrails task:** the three-ticker dry-run limit is already pinned (`tests/hooks/test_guardrails.py:761-793`).

## Parallelisation

Strictly sequential V163-1 → V163-8, then V163-10; only V163-9 may run beside others.

- V163-2 needs V163-1 (`Idea.race_shape` selects the outcome tuple when rendering).
- V163-3 needs V163-2 (`race.OUTCOMES` indices 5 `trail` and 6 `gap_trail`, which `_first_exit_trail` emits).
- V163-4 needs V163-3 (`race_for("trail")` returns `trail.race_trail`).
- V163-5 needs V163-4 (`run_book(..., shape=)`, `matched_null(..., shape=)`) and V163-1 (`idea.race_shape`); it shares `screen_idea.py` and `tests/scripts/test_screen_idea.py` with V163-2 and V163-6.
- V163-6 needs V163-5 (`summary["timeouts"]`, `summary["stress"]`) and shares its files.
- V163-7 needs V163-5 (`screen_ticker` racing trail ideas) — it drives the whole screen.
- V163-8 runs the V163-7 script.
- V163-9 (docs only: `docs/claude/backtest-methodology.md`, `AGENTS.md`) touches no file another task touches and consumes no code contract; it may run beside any of V163-3..V163-8.
- V163-10 (full suite) runs last, after all others are committed.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates, consumed later |
|---|---|---|---|---|---|
| V163-1 | `Idea.race_shape`, `RACE_SHAPES`, trail cap floor, `_load` reads `RACE`; registry pins | 1 | sonnet | M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `tests/backtesting/screen/test_ideas_registry.py` | `RACE_SHAPES = ("fixed", "trail")`; `TRAIL_MIN_CAP = 60`; `Idea.race_shape: str = "fixed"` (last field, after `source`); `Idea.__post_init__` raises `ValueError` for a shape not in `RACE_SHAPES` and for `race_shape == "trail"` with `time_cap_bars < TRAIL_MIN_CAP`; `_load(name)` passes `race_shape=getattr(module, "RACE", "fixed")` |
| V163-2 | Append trail outcome codes, per-shape outcome table, per-shape arms rendering; fixed doc + ledger byte-identity pins | 1 | sonnet | M `swingbot/core/backtesting/screen/race.py`, M `scripts/backtest/screen_idea.py`, M `tests/backtesting/screen/test_race.py`, M `tests/scripts/test_screen_idea.py` | `race.OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout", "trail", "gap_trail")`; `race.SHAPE_OUTCOMES: dict[str, tuple[str, ...]] = {"fixed": OUTCOMES[:5], "trail": ("gap_stop", "stop", "gap_trail", "trail", "timeout")}`; `screen_idea._mix(outcomes: Counter, names: tuple) -> list`; `screen_idea._render_arms(summary: dict, names: tuple) -> list`; test helper `_fixed_doc_inputs() -> tuple[Idea, dict, Universe, dict]` and literals `FIXED_DOC: str`, `FIXED_HYPOTHESIS: str` in `tests/scripts/test_screen_idea.py` (captured on `main @ 316c57e9`) |
| V163-3 | Trail race: `trail.py` with `race_trail`, `trail_stops`, `_first_exit_trail` | 1 | opus | C `swingbot/core/backtesting/screen/trail.py`, C `tests/backtesting/screen/test_trail.py` | `trail.TRAIL_ATR = 3.0`; `trail.trail_stops(h: np.ndarray, entry: np.ndarray, risk: np.ndarray) -> np.ndarray` (rows × cap matrix, `stop[:, j]` = stop in force on bar column j); `trail._first_exit_trail(O, H, L, C, stops, initial) -> tuple[np.ndarray, np.ndarray, np.ndarray]` (price, code into `race.OUTCOMES`, column j); `trail.race_trail(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None) -> race.RaceResult` |
| V163-4 | `race.race_for` dispatcher; `run_book` and `null.matched_null` take `shape` | 1 | sonnet | M `swingbot/core/backtesting/screen/race.py`, M `swingbot/core/backtesting/screen/null.py`, M `tests/backtesting/screen/test_race.py`, M `tests/backtesting/screen/test_null.py` | `race.race_for(shape: str) -> Callable[..., RaceResult]` (`"fixed"` → `race.race`, `"trail"` → `trail.race_trail`, else `ValueError`); `race.run_book(df, events, cap: int, *, member, warm, atr, slippage_bps=None, commission=None, shape: str = "fixed")`; `null.matched_null(df, event_pos, eligible, k: int, seed, *, cap: int, atr, trend, slippage_bps=None, commission=None, shape: str = "fixed") -> NullDraw` |
| V163-5 | `screen_ticker` races the idea's shape; trail-only timeout and 2 × slippage data; `summarise` aggregates them | 2 | opus | M `scripts/backtest/screen_idea.py`, M `tests/scripts/test_screen_idea.py` | `screen_idea.STRESS_SLIPPAGE_FACTOR = 2`; `screen_idea.base_slippage(slippage_bps) -> float` (`getattr(config, "SLIPPAGE_BPS", 5.0)` when `None`); `TickerScreen` new fields `null_timeout_r: list = field(default_factory=list)` (net R of every null-race `timeout`) and `stressed: list \| None = None` (trail only: dicts `entry_date`, `r_event`, `r_null` re-raced at `STRESS_SLIPPAGE_FACTOR × base_slippage`); `summarise(...)` adds `"timeouts": {"event": (count, share, mean_r), "null": (count, share, mean_r)}` (share/mean `None` when empty) and `"stress": verdict.Verdict \| None` (`None` when every screen's `stressed is None`) |
| V163-6 | Trail rendering: per-shape trade line, "Trail race" section, per-shape ledger hypothesis, docstring | 2 | sonnet | M `scripts/backtest/screen_idea.py`, M `tests/scripts/test_screen_idea.py` | `screen_idea._render_trade(idea, run) -> str`; `screen_idea._render_trail(summary: dict, run: dict) -> list` (heading `## Trail race (reported, never gating)`); `screen_idea.hypothesis(idea) -> str` (trail text contains `chandelier 3.0 ATR trail race, initial stop 1.5 ATR, cap <cap>`) |
| V163-7 | A/A calibration script and its smoke test | 2 | opus | C `scripts/backtest/screen_trail_calibration.py`, C `tests/scripts/test_screen_trail_calibration.py` | Constants `REPLICATES = 200`, `SEED = 20261015`, `TICKERS = 24`, `BARS = 2600`, `EVENT_RATE = 0.02`, `T_DF = 3`, `VOL_STATES = (0.010, 0.025)`, `SWITCH_PROB = (0.02, 0.05)`, `CAP = 60`, `FALSE_PASS_MAX = 0.05`; `synthetic_frame(rng, bars=BARS, start="2010-01-04") -> pd.DataFrame`; `random_events(index, rng, rate=EVENT_RATE) -> pd.Series`; `replicate(seed: int, *, tickers=TICKERS, bars=BARS, rate=EVENT_RATE, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES) -> verdict.Verdict`; `calibrate(replicates=REPLICATES, seed=SEED, *, tickers=TICKERS, n_resamples=..., out=print) -> dict` (keys `replicates, verdicts, false_pass, false_pass_rate, covered, coverage, mean_n`); `render(result: dict, params: dict, day: str) -> str`; CLI `python scripts/backtest/screen_trail_calibration.py [--replicates N] [--seed N] [--tickers N] [--resamples N] [--date YYYY-MM-DD] [--out-dir DIR] [--dry-run]` writing `<out-dir>/<date>-trail-race-calibration.md`; exit 0 iff `false_pass_rate <= FALSE_PASS_MAX` |
| V163-8 | Run the 200-replicate calibration and commit its results doc | 2 | sonnet | C `docs/superpowers/results/2026-10-15-trail-race-calibration.md` (dated the run day) | The recorded false-pass rate and coverage; a rate above 5% stops the plan (partner question, no tuning) |
| V163-9 | Methodology doc: Stage −2 names both shapes; `AGENTS.md` mirror | 2 | haiku | M `docs/claude/backtest-methodology.md`, M `AGENTS.md` | — |
| V163-10 | Full suite, once | 2 | haiku | — | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `docs/superpowers/plans/2026-10-15-v163-screen-trail-race_1-race-core.md` | V163-1..V163-4 | Idea shape field, outcome codes and per-shape rendering pins, the trail race, the dispatcher through `run_book` and the null |
| 2 | `docs/superpowers/plans/2026-10-15-v163-screen-trail-race_2-screen-calibration.md` | V163-5..V163-10 | Screen script wiring and trail doc, A/A calibration script and run, methodology doc + AGENTS.md, full suite |
