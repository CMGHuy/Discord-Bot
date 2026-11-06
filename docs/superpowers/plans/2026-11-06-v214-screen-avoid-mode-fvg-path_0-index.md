# v214 — Avoid mode for the idea screen, and the overhead bearish-gap idea — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md`](../specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md)

## Goal

The live book's loss review (2026-11-06,
`docs/superpowers/results/2026-11-06-loss-review-sep-nov.md`) singled out one
population: longs whose plan target sits at an older, unfilled bearish fair-value
gap overhead (N = 68 since Sep 1, ExpR −0.199R, 19% WR). The obvious next step
would be a veto that removes these longs. But the repo cannot license a veto
today. The Stage −2 idea screen only passes ideas that **beat** a matched random
baseline by +0.10R. An avoid idea selects the bars to skip, so it can never pass
in keep form, and a plain sign flip is easier to clear than the edge bar. Four
closed screens would already have cleared it.

This plan gives the screen an **avoid mode**. An idea module declares
`MODE = "avoid"`, and the verdict then requires the event to do worse than two
baselines by at least 0.10R, under six frozen clauses:
- the matched random null, on mean, upper confidence bound and years;
- a **control arm**: bars where an old bearish gap also exists, but beyond the
  race's reach.

Holding "a gap exists" constant and varying only "within reach" rules out the
bull-window flattery that makes a sign flip cheap. The plan then freezes one
idea, `fvg_overhead_aged`, under that mode. It uses the live FVG detector
called per bar on a truncated frame, gaps at least 5 bars old, and a gap bottom
within `Close + 3 × ATR14`. The plan spends that idea's one shot through
`backtest-runner`.

The plumbing carries the mode everywhere:
- the verdict module and the `SCREEN-AVOID-PASS` ledger label;
- every `decide` call site, plus the admin research API that lists the labels;
- the spec-header hook, which accepts `<id> SCREEN-AVOID-PASS (veto)` for an
  `Edge: expectancy` spec only;
- the methodology docs and their Codex mirror.

What it leaves alone: no live code path changes, and no veto ships. An avoid
pass only buys a later veto spec, which runs the unchanged funnel on the bot's
own replay. Every existing edge idea keeps its verdict and output byte for
byte, pinned by v211's parity digests, `test_long_byte_identical.py` and the
hypothesis golden.

Success is measured in two steps:
- the narrow test runs per task are green, and CI is green after the push;
- one ledger row `screen-fvg_overhead_aged` exists, with a results doc that
  records the window, universe, seed derivation, events per year, errors per
  ticker, control-floor and exclusion shares, the overnight-reach share, the
  calibration printout and the ledger order relative to v211's shots.

The verdict, whatever it is, is recorded in the spec's closing commit.

## Architecture

- **G4, detector.** `swingbot/core/market/fvg.py` gains a raising helper,
  `scan_fair_value_gaps`. The live `find_fair_value_gaps_detailed` becomes
  `try: return scan_fair_value_gaps(...) except Exception: return []`, which is
  byte-identical.
- **G1/G5, verdict.** `swingbot/core/backtesting/screen/verdict.py` gains
  `MODES`, `SCREEN_AVOID_PASS`, mirrored clauses, `years_negative`, a
  mode-aware bootstrap p, a `ControlArm` record, and
  `decide(events, *, mode="edge", control=None, ...)`. The clauses and the label
  are table-driven per mode, and edge mode returns today's exact `Verdict`
  values and 4-key clause dict.
- **G3, idea.** The new idea module computes one `states(df)` frame per ticker
  with these columns:
  - `event`: per-gap onset, once per gap identity;
  - `control_condition`: no gap within reach, but an aged gap beyond reach;
  - `condition`: any gap within reach;
  - `bottom`: the lowest qualifying gap bottom on event bars.

  The runner reads it once per ticker. `Idea` gains `mode` and `states`, read
  from the module's `MODE` and `states`.
- **Runner (`scripts/backtest/screen_idea.py`).**
  - `condition` bars leave the null pool through the existing `exclude` hook.
  - The control arm reuses `null.matched_null` with the mask
    `null pool & control_condition`, the `null.MIN_CANDIDATES` floor and the
    seed `null_seed(idea.name + ":control", ticker)`.
  - A detector failure raises `screen.errors.IdeaError`, which aborts that
    ticker only and is counted per ticker.
  - The summary, the verdict render and the hypothesis are chosen per mode, and
    a `## Avoid mode` block prints the non-gating read-outs.
- **G5, other call sites.** `screen/diagnostics.py` and
  `scripts/backtest/screen_trail_calibration.py` thread `mode`. The calibration
  counts only edge passes as false passes.
- **G6/G7, gate and docs.** The hook and the docs accept and describe
  `SCREEN-AVOID-PASS (veto)`.

**Tech stack:** Python 3.11, pandas/numpy, pytest; no new dependency.

## Global Constraints

- **Sequencing gate: no v214 task starts before v211's V211-4 (the
  `Idea.context_kind` field) and V211-6 (`screen_universe(checkpoint_dir=)` and
  `_run_screens`) are merged on `main`.** This comes from the spec's
  § Constraints. Plan: `docs/superpowers/plans/2026-11-06-v211-shock-short-screens_*`,
  owned by another session. **Never edit those plan files.**
  - **Before every task**, check for the symbols, not the commit messages:
    - `git grep -n context_kind main -- swingbot/core/backtesting/screen/ideas/__init__.py`
    - `git grep -n checkpoint_dir main -- scripts/backtest/screen_idea.py`

    Both must print a match; otherwise stop and report `BLOCKED`. A commit
    message grep is not enough: v211's docs commits already name V211-4..6.
  - If later v211 tasks (V211-5, 8/9, 11, 11b, 12) have also merged, build on
    their shape. Line numbers in this plan are indicative; symbols are
    authoritative.
- **v211's pins stay green untouched:**
  - `tests/backtest_scripts/test_screen_context_runner.py::PARITY_DIGESTS`;
  - `tests/backtesting/screen/test_long_byte_identical.py`;
  - the hypothesis golden (`tests/backtest_scripts/golden/hypotheses_pre_v211.json`).

  Every task touching `screen_idea.py`, `verdict.py` or `ideas/__init__.py`
  runs them.
- **Field and registry placement:**
  - New dataclass fields go **after** v211's: `Idea.mode`/`Idea.states` after
    `context_kind`; `TickerScreen.avoid` after `shock` (when V211-11 has
    landed; otherwise last).
  - `IDEA_MODULES` appends `fvg_overhead_aged` after v211's two shock ideas.
  - The exact-equality pins in `tests/backtesting/screen/test_ideas_registry.py`
    are extended, never loosened.
- **Edge-mode identity.** No existing idea's verdict, results doc, hypothesis,
  `Verdict.clauses` (exactly `{"exp_r", "ci", "years", "n"}`) or ledger row
  changes. `decide(...)` called without `mode` behaves exactly as today,
  `functools.partial(verdict.decide, n_resamples=500)` monkeypatching included.
- **Avoid rule (G1), frozen.** Six clauses, all required for `SCREEN-AVOID-PASS`:
  - d = R_event − mean(R_null): mean d ≤ −(0.10 − `_TOLERANCE`), so exactly
    −0.10 passes;
  - d: `ci_high < 0` (strict; 10,000 week-cluster resamples, seed 42);
  - d: mean d < 0 (strict) in ≥ 7 of 2011–2019, where an empty year counts
    against;
  - N ≥ 300;
  - d_c = R_event − mean(R_control): mean d_c ≤ −(0.10 − `_TOLERANCE`);
  - d_c: `ci_high < 0` and N_c ≥ 300.

  N < 300 or N_c < 300 gives `SCREEN-UNDERPOWERED` (closed). Any other failure
  gives `SCREEN-FAIL`.
- **Avoid p** = the share of bootstrap resamples ≥ 0. It enters
  `stats.ledger_qvalues`, the same BH family as every row (G2). The one-shot
  refusal in `screen_idea.refusal` is unchanged.
- **Control arm.** It is drawn per kept event, K = 20, from the same ticker,
  month and trend state. The pool is `null pool & control_condition`, with
  condition bars excluded. The floor is `null.MIN_CANDIDATES` (5). The seed is
  `null.null_seed(idea.name + ":control", ticker)`.
- **The idea (G3), frozen:**
  - daily bars, Wilder ATR14 (`screen.indicators.atr`);
  - gaps from the live detector per bar on `df.iloc[:t+1]` with live defaults
    (`LOOKBACK_BARS = 100`, `MAX_GAPS_PER_SIDE = 3`, wick-touch fill);
  - bearish gaps only;
  - age `t − bar_index ≥ 5`;
  - within reach: `Close[t] < g.bottom ≤ Close[t] + 3 × ATR14[t]`;
  - an event fires once per gap `bar_index`, at its first qualifying bar;
  - `CAP = 20`, `RACE = "fixed"`, `DIRECTION = "long"`, `ENTRY = "next_open"`,
    `MODE = "avoid"`;
  - never vectorised: the per-bar call is the implementation.
- **Anti-goals.** No retry is ever planned: no other age, mid or top anchor,
  k × ATR reach, displacement mode, dropped control clause or short mirror. The
  event never keys on decline size, drawdown, distance from a high, or a gap on
  its formation bar.
- **Verdict vocabulary.** `"SCREEN-AVOID-PASS"` is appended last to
  `stats.VERDICTS`. The committed ledger is never edited.
- **Hook (G6).**
  - `<ledger-id> SCREEN-AVOID-PASS (veto)` is accepted only with
    `Edge: expectancy`, and only if the row's verdict is `SCREEN-AVOID-PASS`.
  - The avoid label without `(veto)` is rejected.
  - `(veto)` beside `SCREEN-PASS` is rejected.
- **Complexity.** Every touched function stays < 15
  (`scripts/dev/complexity_gate.py`). Split into helpers and table-drive the
  mode branches.
- **Tests.** Every task ships its tests. The per-task run is
  `python scripts/dev/testrun.py file <test>`. **No task runs the full suite**;
  CI does after the push.
- **Codex mirror.** `AGENTS.md` changes in the same commit as the
  `docs/claude/` text it mirrors; `tests/hooks/test_codex_mirror.py` is green.
- **Bash and the screen hook.** A PreToolUse hook tokenises any Bash command
  that mentions the screen runner. Keep such commands shell-parsable (no
  unbalanced quotes, no heredoc prose); write files with the editor tools.
- **Branch and worktree.** Code tasks commit on the implementation branch
  `2026-11-06-v214-screen-avoid-mode-fvg-path` in
  `.claude/worktrees/2026-11-06-v214-screen-avoid-mode-fvg-path`. V214-12 runs
  on `main` after the merge and a green CI.

## Review Focus

1. **A ticker whose every event has fewer than 5 control candidates.** Its
   events still count in N; only N_c shrinks. If N_c < 300 overall, the label
   is `SCREEN-UNDERPOWERED`, never `SCREEN-FAIL`. Tested in V214-2
   (`decide(control=[])`) and V214-6 (the below-floor count).
2. **The detector raises mid-ticker.** That ticker alone is skipped. Its name
   and error are counted under `skipped["idea_error:<TICKER>"]`, the run
   continues, and an edge idea's run never catches anything new. Tested in
   V214-6.
3. **Warm-up bars with NaN ATR14.** No condition, no control, no event, and the
   gap is **not** marked fired. A gap first reachable after warm-up still fires
   once. Tested in V214-5.
4. **A wick that touches the gap bottom exactly (`High == bottom`).** The gap
   is filled and never fires afterwards, as live. Tested in V214-5.
5. **An edge idea passing through the new avoid branches.** Its `ctx` has no
   avoid keys, so the results doc, the hypothesis and the summary are
   byte-identical. Tested in V214-6 and V214-7 via the v211 pins and a direct
   equality test.

## Parallelisation

All tasks wait on the sequencing gate (v211 V211-4 and V211-6 on `main`).
After it:

| Wave | Tasks | Why together / why after |
|---|---|---|
| A | V214-1, V214-2, V214-3, V214-4, V214-10, V214-11 | Disjoint files: `fvg.py`; `verdict.py`; `stats.py` + admin test; `ideas/__init__.py` + registry test; the hook file; the three docs. No contract between them. |
| B | V214-5, V214-9 | V214-5 needs V214-1's `scan_fair_value_gaps` and V214-4's `Idea.mode`/`states`; it also edits `ideas/__init__.py` and `test_ideas_registry.py` (V214-4's files). V214-9 needs V214-2's `decide(mode=)` and V214-4's `Idea.mode`. Their files are disjoint. |
| C | V214-6 | Needs V214-4 and V214-5 (`errors.IdeaError`, the `states` contract). It edits `screen_idea.py`, the file v211 also edits. |
| D | V214-7 | Same file as V214-6 (`screen_idea.py`). Also needs V214-2's `Verdict.mode`/`ControlArm` and V214-3's vocabulary. |
| E | V214-8 | Same file as V214-7. It renders V214-7's summary keys. |
| F | V214-12 | The one shot. It needs every code task merged on `main` and CI green, and it writes the ledger. |

Sequential edges, named:
- **V214-1 → V214-5:** the idea calls the helper.
- **V214-4 → V214-5:** `Idea.mode` and `states`; also the same registry files.
- **V214-2 → V214-9:** `decide(mode=)`.
- **V214-4 → V214-9:** `idea.mode`.
- **V214-5 → V214-6:** `IdeaError`.
- **V214-6 → V214-7 → V214-8:** one file, and the summary keys.
- **V214-2/3 → V214-7:** cross-checks of `MODES` and the vocabulary.
- **All → V214-12.**

V214-10 and V214-11 are content-related (the docs describe the hook) but
touch disjoint files.

## Task ledger

| Id | Title | Part | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V214-1 | Raising FVG scan helper; live detector byte-identical (G4) | 1 | sonnet | M `swingbot/core/market/fvg.py`; C `tests/market/test_fvg_scan_helper.py` | `fvg.scan_fair_value_gaps(df: pd.DataFrame, lookback: int = LOOKBACK_BARS, max_per_side: int = MAX_GAPS_PER_SIDE) -> list[dict]` — today's body without the `try`, raises on bad input; `find_fair_value_gaps_detailed` = `try: return scan_fair_value_gaps(df, lookback, max_per_side)` / `except Exception: return []` |
| V214-2 | Verdict avoid mode: mirrored clauses, control arm, mode-aware p (G1, G5) | 1 | opus | M `swingbot/core/backtesting/screen/verdict.py`; C `tests/backtesting/screen/test_verdict_avoid.py` | `verdict.MODES = ("edge", "avoid")`; `verdict.SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"`; `years_negative(table) -> int` (strict mean < 0, an empty year not counted); `avoid_mean_clause(delta) -> bool` (`delta <= -PASS_EXP_R + _TOLERANCE`); `avoid_ci_clause(high) -> bool` (`high < 0`); `bootstrap(events, *, n_resamples, seed, mode="edge")` → p = share ≤ 0 (edge) / ≥ 0 (avoid); `@dataclass(frozen=True) ControlArm(n: int, delta_exp_r: float \| None, ci_low: float \| None, ci_high: float \| None, per_year: dict)`; `Verdict` gains trailing `mode: str = "edge"`, `years_negative: int \| None = None`, `control: ControlArm \| None = None`; `decide(events, *, mode: str = "edge", control=None, n_resamples=..., seed=...) -> Verdict` (avoid clause keys exactly `("exp_r", "ci", "years", "n", "control_exp_r", "control_ci", "control_n")`; `ValueError` for a mode outside `MODES`) |
| V214-3 | `SCREEN-AVOID-PASS` in the ledger vocabulary and the admin research API (G5) | 1 | haiku | M `swingbot/core/backtesting/instrument/stats.py`; M `tests/backtesting/test_instrument_stats_ledger.py`; M `tests/admin/test_api_v1_research.py` | `stats.VERDICTS` = today's 13 + `"SCREEN-AVOID-PASS"` last |
| V214-4 | `Idea.mode` and `Idea.states`; edge-mode witness pin (G1) | 1 | sonnet | M `swingbot/core/backtesting/screen/ideas/__init__.py`; M `tests/backtesting/screen/test_ideas_registry.py` | `ideas.MODES = ("edge", "avoid")`; `Idea.mode: str = "edge"` and `Idea.states: Callable[[pd.DataFrame], pd.DataFrame] \| None = None` (after `context_kind`), read from module `MODE` / `states`; `_mode_problem(idea) -> str \| None` (mode outside `MODES`; avoid without `states`; edge with `states`; avoid with `entry != "next_open"` or `race_shape != "fixed"`) |
| V214-5 | Idea `fvg_overhead_aged` (G3) | 1 | opus | C `swingbot/core/backtesting/screen/errors.py`; C `swingbot/core/backtesting/screen/ideas/fvg_overhead_aged.py`; M `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES` append); C `tests/backtesting/screen/test_idea_fvg_overhead_aged.py`; M `tests/backtesting/screen/test_ideas_registry.py` | `errors.IdeaError(RuntimeError)`; module `fvg_overhead_aged`: `CAP = 20`, `MODE = "avoid"`, `RACE = "fixed"`, `DIRECTION = "long"`, `ENTRY = "next_open"`, `MIN_AGE_BARS = 5`, `REACH_ATR = 3.0`, `STATE_COLUMNS = ("event", "control_condition", "condition", "bottom")`, `states(df) -> pd.DataFrame` (index `df.index`; bool `event`/`control_condition`/`condition`, float `bottom` = lowest within-reach gap bottom on event bars, NaN elsewhere; detector failure → `IdeaError`), `events(df) -> pd.Series` named `"fvg_overhead_aged"` |
| V214-6 | Runner: avoid books — condition exclusion, control arm, per-ticker errors | 2 | opus | M `scripts/backtest/screen_idea.py` (`TickerScreen.avoid`, `CONTROL_SEED_SUFFIX`, `_avoid_context`, `ticker_context`, `_avoid_arm`, `screen_ticker`, `count_ticker`, the per-ticker screen call inside V211-6's `screen_universe`/`_screen_or_resume`); C `tests/backtest_scripts/test_screen_avoid_mode.py` | `TickerScreen.avoid: dict \| None = None` = `{"control": rows, "below_floor": int, "kept": int, "excluded": int, "population": int, "overnight": int}` (`rows` as `_event_rows`, `r_null` = mean control R); `ctx` keys `"control_condition"`, `"condition"`, `"bottom"` (avoid ideas only); `screen_idea.CONTROL_SEED_SUFFIX = ":control"`; an `IdeaError` sets `skipped["idea_error"] += 1` and `skipped[f"idea_error:{ticker}"] = 1`, prints `[<idea>] <ticker>: idea error: <msg>` via `out`, and the run continues |
| V214-7 | Runner: mode-threaded verdicts and the avoid verdict table (G5) | 2 | opus | M `scripts/backtest/screen_idea.py` (`summarise`, `_avoid_pairs`, `_stress`, `_decide`, `with_short_blocks` caller, `_run_screens`, `_render_verdict`, `_render_edge_verdict`, `_render_avoid_verdict`, `publish` print line); M `tests/backtest_scripts/test_screen_avoid_mode.py` (append) | `summarise(screens, skipped=None, *, mode: str = "edge") -> dict` (avoid: `verdict.decide(paired, mode="avoid", control=_avoid_pairs(screens))`); `_avoid_pairs(screens) -> list[verdict.PairedEvent]`; `_stress(screens, mode="edge")`; `_decide(rows, mode="edge")`; `_render_verdict(v)` dispatches on `v.mode` |
| V214-8 | Runner: avoid read-outs, calibration printout, avoid hypothesis, ledger order | 2 | sonnet | M `scripts/backtest/screen_idea.py` (`CALIBRATION_IDS`, `with_avoid_blocks`, `_avoid_run`, `_render_avoid`, `_avoid_hypothesis`, `hypothesis`, `render_results`, `publish`, `_run_screens`); M `tests/backtest_scripts/test_screen_avoid_mode.py` (append) | `CALIBRATION_IDS = ("screen-high52w", "screen-gap_volume", "screen-sweep_reclaim_bos", "screen-range_breakdown_close")`; `with_avoid_blocks(summary, screens, idea) -> dict` adds `"avoid"` = `{"below_floor", "kept", "excluded", "population", "overnight", "errors": {ticker: 1}}`; `_avoid_run(run, idea, rows, row) -> dict` adds `"calibration"` (rows) and `"ledger_order"` (`{"position": int, "preceding_v211": [ids]}`); `render_results` appends `## Avoid mode` for `idea.mode == "avoid"` |
| V214-9 | `decide` call sites in diagnostics and trail calibration take `mode` (G5) | 2 | sonnet | M `swingbot/core/backtesting/screen/diagnostics.py` (`_decide`, `_overlap`, `_selloff`, `compute`); M `scripts/backtest/screen_trail_calibration.py` (`replicate`, `_false_passes`, `calibrate`); M `tests/backtesting/screen/test_diagnostics.py`; M `tests/backtest_scripts/test_screen_trail_calibration.py` | `diagnostics._decide(rows, mode="edge")`; `_overlap(events, restricted, cap, mode="edge")`; `_selloff(events, signals, days, spy_r5, mode="edge")`; `screen_trail_calibration._false_passes(verdicts) -> int` (counts `verdict.SCREEN_PASS` only) |
| V214-10 | Spec-header hook accepts `SCREEN-AVOID-PASS (veto)` for `Edge: expectancy` only (G6) | 2 | sonnet | M `tests/hooks/test_spec_screen_header.py` | hook kind `"avoid_veto"` with `_EDGES_FOR["avoid_veto"] = {"expectancy"}`; regexes `_AVOID_VETO`, `_AVOID_BARE`, `_PASS_VETO` |
| V214-11 | Docs: Stage −2 avoid mode, `Screen:` avoid row, `AGENTS.md` mirror (G7) | 2 | sonnet | M `docs/claude/backtest-methodology.md` (§ Funnel stages, Stage −2 bullet); M `docs/claude/document-conventions.md` (`Screen:` table + hook sentence); M `AGENTS.md` (Screen paragraph) | — |
| V214-12 | The one shot via `backtest-runner`; results doc, ledger row; `/panel`; `/close-out` (G8) | 2 | sonnet | C `docs/superpowers/results/<run-date>-screen-fvg_overhead_aged.md`; M `docs/superpowers/results/preregistration-ledger.jsonl`; M `docs/claude/backtest-methodology.md` (closed table, on FAIL/UNDERPOWERED only); M the spec (verdict line) | ledger row `screen-fvg_overhead_aged` |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-06-v214-screen-avoid-mode-fvg-path_1-core.md` | V214-1..V214-5 | detector helper, verdict avoid mode, vocabulary, `Idea` mode fields, the idea module |
| 2 | `2026-11-06-v214-screen-avoid-mode-fvg-path_2-runner-shot.md` | V214-6..V214-12 | runner books and render, diagnostics and calibration call sites, hook, docs, the shot and close-out |
