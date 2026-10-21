# v182 — Idea screen for shorts, and two Schwab range-breakdown short screens: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V182-7:" -A 400 docs/superpowers/plans/2026-10-21-v182-short-screen-range-breakdown_2-*.md`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md)
**Brief:** `.superpowers/briefs/2026-10-21-v182-short-screen-range-breakdown.md`
**Worktree:** implement V182-1..V182-21 in `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` (branch of the same name, created in V182-1's first step; `docs/claude/document-lifecycle.md`). The golden long capture (V182-1) is the worktree's **first** commit, before any engine file changes. V182-21 runs the full suite, merges to `main`, then `/panel` (spec's Panel line) and `/close-out` run on `main`.

## Goal

The live book issues few shorts and its recent ones lose. Every dedicated
short mechanism the bot ever had is masked after a closed negative
pre-registration, and the repo rule says a new entry needs a `SCREEN-PASS`
ledger row before its spec. But the Stage −2 idea screen refuses any
non-long idea (`ideas/__init__.py:51`). So no short idea can even be asked
the question today. The partner wants more shorts and a higher short win
rate. The two Schwab sources add one thing the bot has never tested: a
breakdown below a defined sideways range, inside the stock's own downtrend.

Once shipped, the screen can race a short idea as the exact mirror of a long
one. That holds for both race shapes: stop above, target below, the null raced
short, drift sign-adjusted, and a 0.5 %/year borrow fee charged only to
shorts. The screen also gains a second entry mode, `level`, for a resting
sell-stop that fills on the event bar at the broken level. That mode has a
worst-case entry-bar stop rule, 2 × stop-market slippage, and a matched null
that copies each event's fill depth. Two frozen ideas are added:
`range_breakdown_close` (close below the range low, next-open entry) and
`range_breakdown_stop` (sell-stop at the range low). Both are counted
outcome-blind with a new `--count-only` flag before either shot is spent.

How it works, in idea:

- A short race is computed as a long race on negated prices
  (O, H, L, C → −O, −L, −H, −C). The mirror identity is then a property of
  the code, not a hope. The long path never takes the new branch, so its
  float operations stay the same, byte for byte.
- Level mode receives explicit fill prices. The null draws its replacement
  fills from a child random generator, so every next-open idea's null is
  untouched.

What it leaves alone:

- every long result: a golden capture taken before the first engine edit pins
  every registered idea's race, null, drift, rank and verdict, plus the
  calibration script's long output, byte for byte, through every task;
- all live code: RS gate, regime penalty, masks, plans, alerts;
- the ledger row schema;
- the two shots' pass rule.

Success means:

- the mirror, equivalence and byte-identity tests are green;
- both synthetic A/As (short next-open, short level) show at most 10 false
  passes in 200 and are committed before any ledger row;
- the outcome-blind counts note is committed before any shot, and check 5
  gates the stop idea;
- each idea is screened exactly once by `backtest-runner`. A count under 300
  or a failed check 5 stops the plan and goes to the partner instead.

## Architecture

- **New `swingbot/core/backtesting/screen/sides.py`** (V182-4) owns direction:
  - `oriented()` returns the OHLC arrays as the long race reads them
    (negated for a short);
  - `net_r()` is the one place frictions are applied per fill. Long uses
    today's expression unchanged. Short swaps the sides and subtracts
    `frictions.borrow_r`.
  - `race.py` and `trail.py` call both helpers. The only change to the
    existing long expressions is that they move into `net_r()`, operand
    order kept.
- **`race.py`** gains `direction` (V182-4) and level mode (V182-9): `fill`
  per event, entry on bar t, risk from ATR[t−1], a stop-only check on the
  entry bar, and entry slippage × `LEVEL_SLIPPAGE_FACTOR`. `run_book` gains
  `direction` / `levels` / `level_factor`, and `candidate_events` gains
  `entry` (warm-up read at t−1).
- **`null.py`** races the null in the idea's direction (V182-6). V182-10
  splits it into `draw_groups()` (positions and fills, no race; reused by
  `--count-only`) and `matched_null()` (draw, then race). Depth copying and
  replacement draws run on the child stream `default_rng([*seed, 1])`.
- **`forward.py`** negates the forward return for a short idea, once
  (V182-6). `diagnostics.py` is untouched.
- **`ideas/__init__.py`** (V182-3): `Idea` gains `direction="short"`,
  `entry`, `levels`, `control` and `family`. `_load` reads `DIRECTION`,
  `ENTRY`, `levels`, `control_events` and `FAMILY` with `getattr` defaults.
- **`ideas/_range_breakdown.py`** (V182-13) holds the one frozen range and
  trend definition. `range_breakdown_close.py` / `range_breakdown_stop.py`
  (V182-14/15) are thin modules over it.
- **New `screen/descriptive.py`** (V182-16/17) holds pure, never-gating
  block maths: depth summary, check 5, event overlap, regime split and the
  control delta. `scripts/backtest/screen_idea.py` threads direction and
  levels through `_books`. It also adds `--count-only` and renders the short
  and level blocks only for short or level ideas.
- **`scripts/backtest/screen_trail_calibration.py`** gains `--direction` /
  `--entry` (the default run is byte-identical), a Wilson interval and one
  doc name per mode.
- **`.claude/hooks/guardrails.py`** learns `--count-only` as a valueless
  flag that writes nothing and is allowed.

**Tech stack:** Python 3.11, numpy, pandas, pytest; no new dependency.

## Global Constraints

- **Long byte-identity (partner rule, 2026-10-21):** every existing long result stays byte-identical. This covers both race shapes, the nulls, drift, rank correlation, verdicts, counters, results-doc text, the hypothesis text and the calibration script's default output. `tests/backtesting/screen/test_long_byte_identical.py` and `tests/backtest_scripts/test_calibration_long_golden.py` (V182-1) must pass after **every** task. Never `approx`; floats compare exactly. A long expression may move into a helper only with its operand order kept.
- `borrow_r` is never called for a long trade. The 2 × entry slippage applies only to level-mode entries. No existing idea changes `ENTRY`, `RACE` or direction.
- No live code changes: nothing under `swingbot/core/scanning/`, `swingbot/core/edge/` except `frictions.py` (`borrow_r` added), `swingbot/core/planning/`, the bot or the admin.
- Short race = exact mirror: entry open t+1, risk 1.5 × ATR14[t], stop entry + risk, target entry − 2 × risk. Gap stop is open ≥ stop and gap target is open ≤ target. Intrabar, high ≥ stop is checked first, then low ≤ target. The trail is 3 × ATR over the lowest low of earlier bars, never raised. Gross R = (entry − exit) / risk. Frictions: entry "sell", exit "buy".
- `BORROW_RATE_ANNUAL = 0.005`; `borrow_r(entry, risk, days) = entry × 0.005 / 365 × days / risk`, where days = calendar days from entry date to exit date and entry is the fill price (also in level mode). It is charged once per short trade, on events and null trades alike.
- Level mode (fixed shape only):
  - The order is placed before bar t opens, from levels known at ≤ t−1, and lives one bar.
  - Short fill = `min(Open[t], level)`; the event inequality is `Low[t] < level`.
  - Risk = 1.5 × ATR14[t−1].
  - On bar t the stop counts if `High[t] ≥ stop` (exit at the stop, `exit_pos = t`) and the target never counts. Bars t+1..t+cap race as usual.
  - Entry slippage is `LEVEL_SLIPPAGE_FACTOR = 2.0` × base for events and null alike. The 3 × base repricing (`REPRICE_SLIPPAGE_FACTOR = 3.0`) is printed and never gates.
  - `entry_date = index[t]`; warm-up is read at t−1.
- Level null (V182-10):
  - Event depth is `d_e = (Open[t] − fill) / ATR14[t−1]` (0 for a gap fill).
  - A null bar p fills at `Open[p] − d_e × ATR14[p−1]` when `Low[p] ≤` that level and ATR14[p−1] is finite and > 0.
  - An unfilled draw is replaced from the same pool via the child generator `np.random.default_rng([*seed, 1])` (`seed` as a list; an int seed is wrapped first).
  - `null_slots` = Σ min(K, pool) and `null_unfilled` = slots left unfilled. An event left with zero filled nulls counts as `dropped_no_match`.
  - The next-open draw order is unchanged (test-pinned).
- Range definition (frozen, never tuned):
  - window t−30..t−1; S = min Low, R = max High;
  - `R − S ≤ 5 × ATR14[t−1]`;
  - at least 2 window bars with `Low ≤ S + 0.25 × ATR14[t−1]`, earliest and latest ≥ 5 bars apart, and the same for `High ≥ R − 0.25 × ATR14[t−1]`;
  - `SMA50[t−1] < SMA50[t−11]` and `Close[t−1] < SMA50[t−1]`;
  - first break: `Close[t−1] ≥ S`;
  - every clause `.fillna(False)`; ATR14[t−1] NaN or ≤ 0 means no event;
  - warm-up: bar position t ≥ 61.
- `range_breakdown_close`: `Close[t] < S`, ENTRY next_open. `range_breakdown_stop`: `Low[t] < S`, ENTRY level at S. Both are RACE fixed, CAP 20, DIRECTION short, source Schwab "The Ins and Outs of a Swing Trade" (2025-03-07), downswing breakout.
- Calibration:
  - seeds 0..199 (`--seed 0 --replicates 200`), 24 tickers, the v163 generator;
  - gate: false passes ≤ 10 of 200, with the Wilson 95 % interval printed and never gating;
  - docs `docs/superpowers/results/<date>-short-race-calibration.md` (next-open) and `<date>-short-level-race-calibration.md` (level), committed before any ledger row.
  - A failed A/A stops the plan: fix, re-run; no short idea runs.
- Check 5 (stop idea, inside `--count-only`, outcome-blind): `|median null depth − median event depth| ≤ 0.05` ATR and `null_unfilled ≤ 20 %` of null slots. A fail means `range_breakdown_stop` is not run and the partner is told.
- Count ≥ 300 → the one shot. Count < 300 → no run, no ledger row; report to the partner (at most one renamed variant per idea, the partner's call).
- **One shot per idea, run by `backtest-runner`, never re-run.** `git status --short swingbot/core/backtesting/screen/` must be clean before a real run.
- Every new or changed function stays at cyclomatic complexity < 15 (`scripts/dev/complexity_gate.py`).
- `.claude/hooks/guardrails.py` is shared verbatim with Codex through `.codex/hooks.json`, so no mirror file changes. `tests/hooks/test_codex_mirror.py` is run to prove it.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`). One full suite only, in V182-21.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Several scoped commits, never one big one.

## Review Focus

1. **A level-mode event or null bar with ATR14[t−1] NaN or ≤ 0** (start of history, a halted ticker) must produce no event and no null fill. It must never produce a NaN R that silently poisons the mean. Pinned in V182-9 (`test_level_event_with_nan_prior_atr_is_dropped_as_warmup`) and V182-10 (`test_null_bar_with_nan_prior_atr_never_fills`).
2. **A level event within cap bars of the frame end** must drop as `dropped_window`, not raise IndexError on `t+cap`. Pinned in V182-9 (`test_level_event_near_the_end_drops_as_window`).
3. **A null pool exhausted by depth copying** must keep fewer null trades. An event with zero fills drops as `dropped_no_match`; it is never averaged over an empty group. Pinned in V182-10 (`test_event_with_no_fillable_null_drops_as_no_match`).
4. **An entry-bar stop-out at t followed by an event at t+1** is two trades, because `exit_pos = t` and the non-overlap rule is unchanged. Pinned in V182-9 (`test_entry_bar_stop_lets_the_next_bar_trade`).
5. **A same-day or over-the-weekend short holding** charges borrow on calendar days: 0 days costs nothing, Friday→Monday is 3 days. Pinned in V182-2 (`test_borrow_is_zero_for_a_same_day_exit`, `test_borrow_counts_calendar_days_over_a_weekend`) and V182-4 (`test_short_net_r_charges_borrow_on_calendar_days`).

## Parallelisation

At most two implementers at once, both in the one worktree. Two tasks run together only when their files are disjoint and neither consumes the other's contract.

- **V182-2 ∥ V182-3:** `frictions.py` and its test vs `ideas/__init__.py` and `test_ideas_registry.py`, disjoint, no contract between them.
- **V182-13 ∥ V182-9..V182-12:** the range helper (`ideas/_range_breakdown.py`, `indicators.py`, `test_range_breakdown_rules.py`) shares no file with race, null, screen_idea or the calibration script.

Sequential edges, each with its reason:

- V182-1 → everything: the golden must be captured on unchanged engine code (partner rule).
- V182-2 → V182-4: `sides.net_r` calls `frictions.borrow_r` (contract).
- V182-3 → V182-6: `_books` reads `idea.direction`; `Idea(direction="short")` must construct (contract).
- V182-4 → V182-5: `trail.py` imports `sides.oriented` / `sides.net_r` (contract).
- V182-4, V182-5 → V182-6: the null races through `race_for(shape)(…, direction=)` (contract).
- V182-6 → V182-7 → V182-8: the calibration script runs the real `screen_ticker` in short (contract). V182-8 runs V182-7's code.
- V182-8 → V182-9: Part A's calibration must pass before Part B builds on the race (spec gate).
- V182-9 → V182-10 → V182-11 → V182-12: `race(fill=)`/`level_fills` → `draw_groups(depth=)` → `_books` level threading → level A/A (contract chain). V182-9 and V182-10 both touch `race.py` / `null.py` tests.
- V182-3, V182-13 → V182-14 → V182-15: both idea modules use the helper and the `Idea` fields; both edit `IDEA_MODULES` and `test_ideas_registry.py` (shared file).
- V182-11, V182-15 → V182-16: `--count-only` calls `draw_groups(depth=)` and needs both ideas registered (`--idea` choices) (contract).
- V182-16 → V182-17: both edit `screen_idea.py`, `descriptive.py` and `test_screen_idea.py` (shared files).
- V182-12, V182-17 → V182-18: the counts run needs every code change committed and both A/A docs on disk (spec gate).
- V182-18 → V182-19 → V182-20 → V182-21: count gate before shots, one shot at a time on a clean screen package, full suite last by rule.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-21-v182-short-screen-range-breakdown_1-golden-and-short-race.md` | V182-1..V182-4 | golden long capture + regression tests, `borrow_r`, `Idea` direction/entry fields, `sides.py` + short fixed race with mirror identity |
| 2 | `2026-10-21-v182-short-screen-range-breakdown_2-short-null-and-calibration.md` | V182-5..V182-8 | short trail race, null + forward + `screen_idea` short threading, calibration `--direction`, short A/A run |
| 3 | `2026-10-21-v182-short-screen-range-breakdown_3-level-entry-race.md` | V182-9..V182-12 | level-mode race, depth-copy null with child stream, level threading in `screen_idea`, level A/A run |
| 4 | `2026-10-21-v182-short-screen-range-breakdown_4-breakdown-ideas-and-counts.md` | V182-13..V182-16 | range helper + `rolling_min`, the two idea modules, `--count-only` + check 5 + guardrail |
| 5 | `2026-10-21-v182-short-screen-range-breakdown_5-descriptive-blocks-and-shots.md` | V182-17..V182-21 | overlap / trend-only control / SPY split / 3 × / unfilled blocks, counts note, the two one-shot runs, full suite + merge |

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V182-1 | Golden long outputs and the byte-identity regression tests | 1 | sonnet | C `tests/backtesting/screen/long_golden.py`, C `tests/backtesting/screen/golden/long_v182.json`, C `tests/backtesting/screen/test_long_byte_identical.py`, C `tests/backtest_scripts/golden/trail_calibration_v182.txt`, C `tests/backtest_scripts/test_calibration_long_golden.py` | `long_golden.capture() -> dict` (JSON-safe, floats as `repr` strings); `long_golden.GOLDEN_PATH`; `python tests/backtesting/screen/long_golden.py --write` regenerates (only ever run in V182-1) |
| V182-2 | Borrow fee in frictions | 1 | haiku | M `swingbot/core/edge/frictions.py`, M `tests/edge/test_edge_frictions.py` | `BORROW_RATE_ANNUAL = 0.005`; `borrow_r(entry, risk, days)` → same shape as inputs (float or ndarray), `entry * BORROW_RATE_ANNUAL / 365.0 * days / risk` |
| V182-3 | `Idea` accepts short, an entry mode, levels, a control and a family | 1 | sonnet | M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `tests/backtesting/screen/test_ideas_registry.py` | `DIRECTIONS = ("long", "short")`; `ENTRY_MODES = ("next_open", "level")`; `Idea` fields appended after `context`: `entry: str = "next_open"`, `levels: Callable[[pd.DataFrame], pd.Series] \| None = None`, `control: Callable[[pd.DataFrame], pd.Series] \| None = None`, `family: tuple[str, ...] = ()`; `_load` reads `DIRECTION`, `ENTRY`, `levels`, `control_events`, `FAMILY` |
| V182-4 | `sides.py` and the short fixed race (mirror identity) | 1 | opus | C `swingbot/core/backtesting/screen/sides.py`, M `swingbot/core/backtesting/screen/race.py`, C `tests/backtesting/screen/test_sides.py`, C `tests/backtesting/screen/test_race_short.py` | `sides.oriented(o, h, l, c, direction) -> tuple[np.ndarray, ...]` (long: same objects; short: `(-o, -l, -h, -c)`); `sides.holding_days(index, entry_pos, exit_pos) -> np.ndarray`; `sides.net_r(entry, price, risk, *, direction, days, slippage_bps=None, entry_bps=None, commission=None) -> np.ndarray`; `race.race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long")`; `run_book(..., direction="long")` |
| V182-5 | Short trail race | 2 | opus | M `swingbot/core/backtesting/screen/trail.py`, C `tests/backtesting/screen/test_trail_short.py` | `trail.race_trail(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long")` |
| V182-6 | Null raced in the idea's direction, drift flipped once, short threading in `screen_idea` | 2 | opus | M `swingbot/core/backtesting/screen/null.py`, M `swingbot/core/backtesting/screen/forward.py`, M `scripts/backtest/screen_idea.py`, M `tests/backtesting/screen/test_null.py`, M `tests/backtesting/screen/test_forward.py`, M `tests/backtest_scripts/test_screen_idea.py` | `null.matched_null(..., direction="long")`; `forward.forward_atr(df, atr, h, direction="long")` (short: negated); `screen_idea._short_hypothesis(idea) -> str`; `_render_trade` short line; `_books` passes `direction=idea.direction` |
| V182-7 | Calibration script: `--direction`, cap-20 short idea, Wilson interval, doc name per mode | 2 | sonnet | M `scripts/backtest/screen_trail_calibration.py`, M `tests/backtest_scripts/test_screen_trail_calibration.py` | `SHORT_CAP = 20`; `CAL_IDEA_NAMES = {("long","next_open"): "aa_trail_calibration", ("short","next_open"): "aa_short_calibration", ("short","level"): "aa_short_level_calibration"}`; `_idea(events, *, direction="long", entry="next_open", levels=None) -> Idea`; `wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]`; `doc_name(direction, entry, day) -> str`; `replicate(..., direction="long", entry="next_open")`; `calibrate(..., direction="long", entry="next_open")`; parser `--direction {long,short}` and `--entry {next_open,level}` (level rejected until V182-12) |
| V182-8 | Run the short next-open A/A (backtest-runner) and commit its doc | 2 | sonnet | C `docs/superpowers/results/<run-date>-short-race-calibration.md` | the committed doc (gate: ≤ 10 of 200) |
| V182-9 | Level-mode race: fill on bar t, entry-bar stop rule, 2 × entry slippage | 3 | opus | M `swingbot/core/backtesting/screen/race.py`, C `tests/backtesting/screen/test_race_level.py` | `LEVEL_SLIPPAGE_FACTOR = 2.0`; `REPRICE_SLIPPAGE_FACTOR = 3.0`; `race.race(..., fill: np.ndarray \| None = None, level_factor: float = LEVEL_SLIPPAGE_FACTOR)`; `race.level_fills(df, event_pos, levels, atr, direction) -> tuple[np.ndarray, np.ndarray]` (fill, depth in ATR[t−1]); `candidate_events(events, member, warm, cap, *, entry="next_open")`; `run_book(..., levels: np.ndarray \| None = None, level_factor=LEVEL_SLIPPAGE_FACTOR)` |
| V182-10 | Level null: depth copy, replacement on the child stream, `null_unfilled` | 3 | opus | M `swingbot/core/backtesting/screen/null.py`, C `tests/backtesting/screen/test_null_level.py` | `LEVEL_STREAM = 1`; `child_seed(seed) -> list[int]`; `NullGroups(event_pos, groups, fills, dropped_no_match, null_slots, null_unfilled, null_depths)` frozen dataclass (`fills` None in next-open); `draw_groups(df, event_pos, eligible, k, seed, *, atr, trend, direction="long", depth=None) -> NullGroups`; `matched_null(..., depth=None, level_factor=race.LEVEL_SLIPPAGE_FACTOR)`; `NullDraw` appended fields `null_slots: int = 0`, `null_unfilled: int = 0`, `null_depths: tuple = ()` |
| V182-11 | Level threading in `screen_idea`: levels, entry date, depths, 3 × repricing | 3 | opus | M `scripts/backtest/screen_idea.py`, M `swingbot/core/backtesting/screen/verdict.py` (comment only), M `tests/backtest_scripts/test_screen_idea.py` | `raw_levels(idea, df) -> np.ndarray \| None`; `_event_rows(ticker, index, kept, null_mean_r, entry_offset: int = 1)`; `TickerScreen` appended fields `null_slots: int = 0`, `null_unfilled: int = 0`, `depths: dict \| None = None` (`{"event": list[float], "null": list[float]}`), `repriced: list \| None = None`; `_repriced(idea, ticker, df, ctx, costs) -> list \| None` |
| V182-12 | Calibration level mode and the level A/A run | 3 | sonnet | M `scripts/backtest/screen_trail_calibration.py`, M `tests/backtest_scripts/test_screen_trail_calibration.py`, C `docs/superpowers/results/<run-date>-short-level-race-calibration.md` | `LEVEL_OFFSET_ATR = 0.5`; `level_events(df, rng, rate) -> tuple[pd.Series, pd.Series]` (events, levels = Close[t−1] − 0.5 × ATR14[t−1]); `--entry level` enabled |
| V182-13 | Range and trend helper, `rolling_min` | 4 | opus | M `swingbot/core/backtesting/screen/indicators.py`, C `swingbot/core/backtesting/screen/ideas/_range_breakdown.py`, C `tests/backtesting/screen/test_range_breakdown_rules.py` | `indicators.rolling_min(values, n) -> pd.Series`; `_range_breakdown`: `WINDOW = 30`, `HEIGHT_ATR = 5.0`, `TOUCH_ATR = 0.25`, `TOUCH_SPAN = 5`, `SMA_LEN = 50`, `SMA_LAG = 10`, `WARMUP = 61`, `PARAMS: dict`, `SOURCE: str`, `FAMILY = ("range_breakdown_close", "range_breakdown_stop")`; `support(df) -> pd.Series`, `resistance(df) -> pd.Series`, `prior_atr(df) -> pd.Series`, `in_range(df) -> pd.Series`, `downtrend(df) -> pd.Series`, `first_break(df) -> pd.Series`, `setup(df) -> pd.Series`, `control_setup(df) -> pd.Series` (all bool, `.fillna(False)`) |
| V182-14 | Idea `range_breakdown_close` | 4 | opus | C `swingbot/core/backtesting/screen/ideas/range_breakdown_close.py`, C `tests/backtesting/screen/test_idea_range_breakdown_close.py`, M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `tests/backtesting/screen/test_ideas_registry.py` | module: `CAP = 20`, `RACE = "fixed"`, `DIRECTION = "short"`, `PARAMS`, `SUMMARY`, `SOURCE`, `FAMILY`, `events(df)`, `control_events(df)`; `IDEA_MODULES` += `"range_breakdown_close"` |
| V182-15 | Idea `range_breakdown_stop` | 4 | opus | C `swingbot/core/backtesting/screen/ideas/range_breakdown_stop.py`, C `tests/backtesting/screen/test_idea_range_breakdown_stop.py`, M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `tests/backtesting/screen/test_ideas_registry.py` | module adds `ENTRY = "level"`, `levels(df)` (= S on every bar), `events(df)`, `control_events(df)`; `IDEA_MODULES` += `"range_breakdown_stop"` |
| V182-16 | `--count-only`, check 5 and the guardrail flag | 4 | opus | C `swingbot/core/backtesting/screen/descriptive.py`, C `tests/backtesting/screen/test_descriptive.py`, M `scripts/backtest/screen_idea.py`, M `tests/backtest_scripts/test_screen_idea.py`, M `.claude/hooks/guardrails.py`, M `tests/hooks/test_guardrails.py` | `descriptive.DEPTH_MEDIAN_TOL = 0.05`, `NULL_UNFILLED_MAX = 0.20`, `depth_summary(values) -> dict` (`n`, `q1`, `median`, `q3`, `gap_share`), `check_fill_depth(event_depths, null_depths, null_slots, null_unfilled) -> tuple[bool, list[str]]`; `screen_idea.count_ticker(idea, ticker, df, spans) -> dict`, `count_universe(idea, universe, cache_dir, *, start, end, out=print) -> dict`, `render_counts(idea, counts, args) -> str`; parser `--count-only`; guardrail `_SCREEN_FLAG_OPTIONS = ("--dry-run", "--count-only")`, `flags["count_only"]` |
| V182-17 | Descriptive blocks: overlap, trend-only control, SPY regime split, 3 ×, unfilled | 5 | opus | M `swingbot/core/backtesting/screen/descriptive.py`, M `tests/backtesting/screen/test_descriptive.py`, M `scripts/backtest/screen_idea.py`, M `tests/backtest_scripts/test_screen_idea.py` | `descriptive.event_overlap(own, other) -> dict`, `spy_above_200(spy) -> pd.Series`, `regime_split(events, above) -> dict`, `paired_delta(rows) -> tuple[int, float \| None]`; `TickerScreen` appended `control: list \| None = None`, `overlap: dict \| None = None`; `with_short_blocks(summary, screens, idea, spy) -> dict`; `_render_short_blocks(idea, summary, run) -> list` |
| V182-18 | Outcome-blind counts for both ideas and the counts note | 5 | sonnet | C `docs/superpowers/results/<run-date>-v182-counts.md` | the committed counts note (count per idea; check 5 table and verdict) |
| V182-19 | One-shot screen of `range_breakdown_close` | 5 | sonnet | C `docs/superpowers/results/<run-date>-screen-range_breakdown_close.md`, M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `ledger_id("range_breakdown_close")` |
| V182-20 | One-shot screen of `range_breakdown_stop` | 5 | sonnet | C `docs/superpowers/results/<run-date>-screen-range_breakdown_stop.md`, M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `ledger_id("range_breakdown_stop")` |
| V182-21 | Full suite, merge, panel, close-out | 5 | sonnet | none (merge commit; `/close-out` moves spec and plan) | — |
