# v230 Plan 1 — Screen v2 and the re-screen: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V230-7" -A 400 <part file>`); never read a part whole.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) — this plan is the spec's **Plan 1 (Part A)** plus its section "Found while briefing Plan 1 (2026-11-16)". Parts B (ladder) and C (additive gate) are Plan 2, written later.
**Brief:** `.superpowers/briefs/2026-11-16-v230-screen-v2-rescreen.md`

## Goal

Since the Stage −2 idea screen went live on 2026-10-08, two of twelve ideas
passed it, and the ones that passed and failed look alike on their own trades:
the event arm sits near +0.07..+0.12R for `uptrend_pullback`, `turtle_soup`,
`high52w` and `gap_volume` alike. What moves is the null. The v1 null
(`screen/null.py`) draws each event's 20 comparison bars from the same ticker,
the same calendar month and the same trend state, on both sides of the event.
A month that holds a dip trigger holds a drop, and a month that holds a
breakout holds a run-up, so the null races into the very move the trigger
marks: it scored −0.29R for a dip idea and +0.58R for a breakout idea. If that
is right, the screen has been failing breakout and momentum ideas mechanically
and passing dip ideas cheaply, and every verdict since October is suspect.

This plan first **measures** that bias instead of assuming it. A placebo
harness builds two universes with no edge by construction (a regime-switching
random walk and the real cache with whole trading days shuffled across
time) on the real 2010–2019 calendar, defines six placebo triggers that copy
the shapes of the real ones, and runs them through the screen's own pipeline
under the v1 null. If every |Δ| stays within 0.02R the spec's premise is wrong:
the plan records that and **stops**. Otherwise it builds the v2 null in
`screen/null_v2.py`: a three-stage pipeline (panel per ticker, draw per date,
race per null ticker) whose pool for an event on ticker *i* at date *t* is
**other** tickers on the same date, same trend state and same ATR% tercile, so
no null bar comes from the event's neighbourhood. Market-wide triggers declare
`SCOPE = "market"` and draw from the same ticker's trailing 252 sessions
instead. The same placebo must then score zero under v2 (every cell
|Δ| ≤ 0.02R with a half-width ≤ 0.02R, plus a planted +0.5 ATR edge recovered)
before any real idea is read under v2; one failing cell **stops** the plan
with no fallback null.

Once v2 passes, the screen gains a fifth clause for first-shot edge ideas
(the week-clustered lower bound of the event arm's own net mean R is above
zero), `screen_idea.py` runs v2 only, the ledger instrument becomes
`screen-v2`, and the twelve `screen-v1` ideas are re-screened **once** as
`screen2-<name>` under every frozen parameter of their first run (partner
decision 2, a dated, limited exception to "closed pre-registrations never
re-run"). For these twelve the fifth clause is reported and never gates,
because their event arm has already been read.

What it leaves alone: v1's `null.py` (a golden test pins one v1 draw), every
v1 ledger row (byte-identical), the live bot, every funnel row, the v72 and
v92 gates, and Parts B and C. Success is a committed placebo results doc that
measures the v1 bias and accepts v2, twelve `screen2-` rows in the
pre-registration ledger with their results docs, and a re-screen summary that
puts the old and new verdicts side by side; the v2 verdict supersedes v1's for
licensing a strategy spec.

## Architecture

- **Placebo harness** — `swingbot/core/backtesting/screen/placebo.py` holds
  the two universes (`gbm`, `shuffled`), the six triggers, the planted drift,
  the per-cell statistic and the acceptance rule;
  `scripts/backtest/screen_placebo.py` drives the screen pipeline over them
  (v1: `screen_idea.screen_universe`; v2: `screen_v2.run_v2`) and writes
  `docs/superpowers/results/<date>-v230-null-placebo.md` plus one JSON of
  cells per null under `docs/superpowers/results/v230/`.
- **v2 null** — `swingbot/core/backtesting/screen/null_v2.py`, no frame I/O:
  `ticker_panel` (stage 1 values from one ticker's context), `cross_section`
  (dates × tickers), `draw_ticker_scope` / `draw_market_scope` /
  `draw_ticker_level` / `draw_control` behind one `draw` dispatcher with the
  `SCOPE_MISMATCH` / `NULL_STARVED` refusals, `race_pass` (per null ticker,
  one frame resident) and `scatter` back to events. Stage checkpoints are
  `StageCheckpoint` directories with their own manifest (`null_version`,
  `scope`, `stage`).
- **v2 orchestration** — `swingbot/core/backtesting/screen/screen_v2.py`
  (`run_v2`) runs the three stages with callbacks into the script for frame
  loading, the per-ticker context (`screen_idea.ticker_context`) and the
  event-side blocks that read no null (rank, overlap). `screen_idea.py`
  gains only thin wiring: `NULL_VERSION`, the v2 runner, the TickerScreen
  adapter, the re-screen flag and refusal; the v2 report text lives in
  `screen/v2_report.py`, the re-screen policy in `screen/rescreen.py`.
- **Verdict** — `verdict.py` gains `EventBound`, `event_bound` and
  `apply_event_clause`; v1's `decide`, `label` and clause functions are
  untouched.
- **Guardrail** — `.claude/hooks/guardrails.py` `_rule_screen_rerun` allows
  `--rescreen-v1` for exactly the twelve names while `screen2-<name>` has no
  row and no results doc; everything else it denies today stays denied.
- **Data flow (v2 run):** frames → `ticker_context` → `race.run_book` (event
  book) + `null_v2.ticker_panel` (stage 1, per-ticker checkpoint) →
  `cross_section` → `draw` (stage 2, one artefact) → `race_pass` (stage 3,
  per-null-ticker checkpoint) → `scatter` → `V2Ticker` → `TickerScreen`
  adapter → `summarise` → `with_event_clause` → `v2_report` blocks →
  `publish`.

## Global Constraints

- **Chain with two stops.** V230-5 records the v1 placebo measurement first. If every cell has |Δ| ≤ 0.02R, the results doc says the premise is wrong, the index `## Handoff` records it and **V230-6..V230-17 do not run** (Parts B and C proceed on the v1 null). V230-13 is the v2 placebo acceptance: every cell |Δ| ≤ 0.02R **and** 95% half-width ≤ 0.02R (both inclusive), and the planted edge recovered; a noisy cell (half-width > 0.02R) is re-run on an enlarged universe, never waved through; **one failing cell stops the plan** — V230-14..V230-17 do not run and no fallback null is tried.
- **No real idea is read under v2 before V230-13 accepts.** Tasks V230-6..V230-12 test on synthetic fixtures only; no `screen_idea.py` real run, dry run or `--count-only` on the real cache before V230-17.
- **v1 is frozen.** `swingbot/core/backtesting/screen/null.py` is not edited; `null_seed`'s signature stays; v1's `verdict.decide`, `label`, clause functions and existing tests stay unchanged and green. `tests/backtesting/screen/test_null_golden.py` pins one v1 draw and one v2 draw. Every v1 ledger row stays byte-identical (append only).
- **Seeds and order.** v2 ticker scope: one generator per date, `null_seed(f"{idea}:v2", "YYYY-MM-DD")`, consumed over that date's events in sorted-ticker order (positions ascending within a ticker). Market scope: one generator per ticker, `null_seed(f"{idea}:v2", ticker)`, events ascending. Avoid control: `f"{idea}:v2:control"` in place of `f"{idea}:v2"`. Level replacements: `null.child_seed(<that seed>)`. Placebo universes: `PLACEBO_SEED = 42`, per-ticker seed `[42, crc32(ticker)]`.
- **Pools.** `K = null.K` (20), floor `null.MIN_CANDIDATES` (5). Ticker scope: other tickers eligible at *t*, same trend state, same ATR% tercile of that date's eligible cross-section, no raw event of this idea at *t*. Market scope: same ticker, positions in the 252 trading sessions before *t*, eligible, same trend state, no position within `CAP` bars of any of the ticker's raw event bars. `SCOPE_MISMATCH` (ticker scope) / `NULL_STARVED` (market scope) when more than half of the event dates have an event whose pool is under the floor; raised before any race.
- **No lookahead.** Every stage-1 value at *t* reads that ticker's bars ≤ *t*, except race completeness (`pos + cap <= n - 1`), as v1; truncation tests prove it. No null bar postdates its event in market scope.
- **Long runs.** Real and placebo runs go to the `backtest-runner` agent; every stage checkpoints (stage 1 and 3 per ticker, stage 2 as one artefact, placebo per cell) and a restart skips finished units. `screen2-*` ids are one shot; a crashed run that wrote no result may run once more, recorded in `run-marker.json` / `crash.json` beside the checkpoints and in its results doc.
- **Fifth clause.** Gates first-shot `MODE = "edge"` ideas under `screen-v2`; reported-only for `screen2-` ids; absent in avoid mode.
- **One BH family.** Every q reported (head line and the context block) runs over all ledger rows (`stats.ledger_qvalues`); q never gates.
- **Ledger schema unchanged.** `screen-v2` joins `stats.INSTRUMENTS`; a `screen2-` row names its v1 row in its `hypothesis` text and its results doc, never in a new field.
- **Placement.** New logic goes in modules under `swingbot/core/backtesting/screen/`; `scripts/backtest/screen_idea.py` (1940 lines) gets wiring only. Nothing outside `swingbot/core/backtesting/` imports the screen (`test_import_guard.py`). New scripts under `scripts/backtest/` get a `test_date_literal_guard.py` `ALLOW` or `NO_REPLAY` entry.
- **Complexity < 15** on every new or changed function (`scripts/dev/complexity_gate.py`).
- **Tests.** New test files live in `tests/backtesting/screen/` (suite `backtesting-arms`), `tests/backtest_scripts/` (suite `backtest-scripts`) or `tests/hooks/` (suite `dev-setup`); no `tests/suites.toml` edit. No database. Per-task verification is `python scripts/dev/testrun.py file <test>` (or `suite <name>`); **no task runs the full suite** (CI does). Results docs and Markdown are written with `encoding="utf-8", newline="\n"`; new CLIs call `screen_idea._utf8_stdout()`.
- **Codex mirror.** The screen skill edit ships with `python scripts/dev/sync_codex.py` and the `AGENTS.md` update in the same commit; `tests/hooks/test_codex_mirror.py` stays green.
- **Commits.** The implementer commits per task in the plan's worktree; plan writers do not commit. V230-5, V230-13 and V230-17 are run tasks whose results docs commit on the worktree branch with the code that produced them.

## Parallelisation

The plan is a chain with two stops; the parallel room is small.

- **V230-1 ∥ V230-2.** Disjoint files (`ideas/` vs the new `placebo.py`); `placebo.py` sets `scope=` on `Idea` only from V230-3, so V230-2 needs nothing from V230-1.
- **Sequential (same file `placebo.py`):** V230-2 → V230-2b → V230-3 → V230-3b (split halves of two tasks, each appending to the module and its test file).
- **Sequential (contract):** V230-3 needs V230-1 (`Idea.scope`) and V230-2b (`write_universe`, universes). V230-4 needs V230-3 (`TRIGGERS`, `placebo_idea`) and V230-3b (`cell_from_rows`).
- **Sequential (stop gate 1):** V230-5 needs V230-4b; V230-6..17 run only if V230-5 finds a bias.
- **Sequential (same file `null_v2.py`):** V230-6 → V230-7 → V230-8 → V230-9 → V230-10. The spec notes the level-entry and avoid paths are independent once the draw pass exists, but they share `null_v2.py` and its test layout, so they stay in one lane. V230-9 also needs V230-8 (the `draw` dispatcher covers both scopes).
- **Sequential (contract):** V230-11 needs V230-6..10 (every `null_v2` stage). V230-12 needs V230-11 (`run_v2`, `V2Ticker`). V230-13 needs V230-12 (v2 wiring) and V230-4b (CLI).
- **Sequential (stop gate 2):** V230-14..17 run only if V230-13 accepts.
- **Sequential (contract):** V230-15 needs V230-14 (`with_event_clause(gating=)`). V230-16 needs V230-15 (its drift test pins `_RESCREEN_V1` to `rescreen.RESCREEN_V1`).
- V230-16 merges the guardrail and the methodology/skill/Codex-mirror work (partner, 2026-11-17, to keep the plan at 20 tasks after V230-4 split into V230-4/4b).
- **Sequential (operations):** V230-17 needs V230-14..16 merged into the worktree (code, hook, the dated methodology paragraph that licenses the runs).
- At most 2 implementers at once (session rule).

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V230-1 | `SCOPE` on ideas and the three market-scope declarations | 1 | sonnet | M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `swingbot/core/backtesting/screen/ideas/turn_of_month.py`, M `swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py`, M `swingbot/core/backtesting/screen/ideas/dollar_drop.py`, M `tests/backtesting/screen/test_ideas_registry.py` | `ideas.SCOPES = ("ticker", "market")`; `Idea.scope: str = "ticker"` (last field, after `states`); `_scope_problem(scope, mode, entry) -> str \| None` (unknown scope; `market` with `mode="avoid"` or `entry="level"` refused: "not built in v230"); `_load` reads module `SCOPE` (default `"ticker"`); `SCOPE = "market"` in the three modules; `test_every_registered_idea_pins_its_scope` |
| V230-2 | Placebo universes: calendar, quartiles and the `gbm` frame | 1 | opus | C `swingbot/core/backtesting/screen/placebo.py`, C `tests/backtesting/screen/test_placebo_universes.py` | `PLACEBO_SEED = 42`; `GBM_TICKERS = 200`; `INDEX_TICKER = "SPY"`; `MEMBERSHIP_FILE = "membership.csv"`; `MANIFEST_FILE = "universe.json"`; `OHLCV`; `ticker_seed(ticker, base=PLACEBO_SEED) -> list` (`[base, zlib.crc32(ticker)]`); `read_frame(path) -> pd.DataFrame` (V230-2b, V230-3 use it); `trading_calendar(spy_csv, start, end) -> pd.DatetimeIndex`; `atr_pct_quartiles(cache_dir, calendar, tickers=None) -> tuple[float, float, float, float]`; `market_states(calendar, seed) -> np.ndarray` (bool, True = stressed); `gbm_frame(ticker, calendar, *, level, stressed, seed=PLACEBO_SEED) -> pd.DataFrame`. `gbm_frame` carries an optional `seed` keyword beyond the ledger's signature so `gbm_universe(seed=...)` (V230-2b) reaches it; the ledger's call shape still works. `_source_files(cache_dir, tickers=None)` and `_on_calendar(path, calendar)` are reused by V230-2b. |
| V230-2b | Placebo universes on disk: index, layout, `gbm` and `shuffled` | 1 | opus | M `swingbot/core/backtesting/screen/placebo.py`, M `tests/backtesting/screen/test_placebo_universes.py` | `equal_weight_index(frames) -> pd.DataFrame`; `write_universe(out_dir, frames, *, kind, meta) -> Path` (`<T>.csv` with `Date,Open,High,Low,Close,Volume`, `membership.csv` one span per ticker from the first session with blank end, synthetic `SPY.csv`, `universe.json` `{kind, seed, tickers, calendar_start, calendar_end, **meta}`, written last); `gbm_universe(out_dir, calendar, quartiles, *, n_tickers=GBM_TICKERS, seed=PLACEBO_SEED) -> Path` (tickers `G000`..); `shuffled_universe(out_dir, source_dir, calendar, *, seed=PLACEBO_SEED, copies=1) -> Path` (`meta["source_sha256"] = {file: sha256}`, `meta["copies"]`). Public helpers `day_permutation(n, seed) -> np.ndarray`, `shuffle_frame(df, perm) -> pd.DataFrame`. V230-3 (`plant_universe`) and V230-4 (`build_universes`) call `write_universe`, `gbm_universe`, `shuffled_universe`. |
| V230-3 | Placebo triggers and planted drift | 1 | opus | M `swingbot/core/backtesting/screen/placebo.py`, C `tests/backtesting/screen/test_placebo_triggers.py` | `PLACEBO_CAP = 10`; `PLANT_ATR = 0.5`; `TOLERANCE_R = 0.02`; `PlaceboTrigger(name, scope, events)` (`events(ticker_frame, index_frame) -> pd.Series`); `TRIGGERS` (`p_high20`, `p_rsi2_dip`, `p_gap_up`, `p_sweep20` ticker scope; `p_market_down`, `p_month_turn` market scope); `placebo_idea(trigger, index_frame) -> Idea`; `plant_drift(df, events, atr, *, cap=PLACEBO_CAP, atr_mult=PLANT_ATR) -> pd.DataFrame`; `plant_universe(base_dir, out_dir) -> Path` (planted frames plus `planted_events.json` `{ticker: [ISO dates]}`); `planted_trigger(universe_dir) -> PlaceboTrigger` (`p_high20_planted`); `planted_value(base_rows, planted_rows) -> float \| None`. Also `PLANT_SPACING = 120`, `PLANTED_FILE = "planted_events.json"`. |
| V230-3b | Placebo cells and the acceptance rule | 1 | opus | M `swingbot/core/backtesting/screen/placebo.py`, M `tests/backtesting/screen/test_placebo_triggers.py` | `@dataclass(frozen=True) Cell(universe, trigger, null, n, mean_r_event, mean_r_null, delta, ci_low, ci_high)` with `.half_width`, `to_dict()`, `Cell.from_dict(d)`; `cell_from_rows(universe, trigger, null_version, rows, *, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, seed=stats.WEEK_BOOTSTRAP_SEED) -> Cell` (rows are the screen's event rows: `ticker`, `entry_date`, `r_event`, `r_null`); `accept_cell(cell) -> str` in `("PASS", "FAIL", "NOISY")`; `v1_premise_holds(cells) -> bool`; `planted_recovered(cell, value) -> bool`; `acceptance(cells, planted_cell, value) -> dict` with keys `verdict` (`ACCEPT`/`STOP`/`ENLARGE`), `cells` (`{"<universe>/<trigger>": verdict}`), `planted` (`value`, `cell`, `recovered`, `noisy`). V230-4 and V230-13 consume all of them. |
| V230-4 | Pipeline parameters, placebo universes on disk and the v1 cell runner | 2 | sonnet | M `scripts/backtest/screen_idea.py`, C `scripts/backtest/screen_placebo.py`, C `tests/backtest_scripts/test_screen_placebo.py`, M `tests/backtesting/instrument/test_date_literal_guard.py` | the `screen_idea` keywords of the ledger row (a non-default `event_start` adds an `event_start` key to the checkpoint manifest; the default manifest is unchanged); `screen_placebo.NULLS = ("v1", "v2")`, `KINDS = ("gbm", "shuffled")`, `DEFAULT_WORK`, `DEFAULT_JSON`, `universe_label(kind, size) -> str` (`gbm-<n>`, `shuffled-c<copies>`), `load_cells(path)`, `save_cell(path, cell)`, `run_cell_v1(universe_dir, trigger: PlaceboTrigger, *, checkpoint_dir) -> list[dict]`, `RUNNERS = {"v1": run_cell_v1}`, `build_universes(args) -> dict[str, Path]` (universes at `<work-dir>/universes/<label>/`, reused when `universe.json` exists). V230-4b adds the cell loop, the doc, the parser and `main`; until then the module has no `__main__`. |
| V230-4b | Placebo CLI: the cell loop, the gate, the results doc and `main` | 2 | sonnet | M `scripts/backtest/screen_placebo.py`, M `tests/backtest_scripts/test_screen_placebo.py` | `latest_cells(cells) -> list[Cell]` (largest universe per kind × trigger × null), `v1_gate(cells) -> str \| None` (`BIAS` / `NO-BIAS`), `render_doc(cells, *, date, manifests, planted=None, acceptance=None) -> str` (`planted`: the planted `Cell`; `acceptance`: `placebo.acceptance(...)`'s dict — V230-13 passes both), `write_doc(args, *, planted=None, acceptance=None) -> Path`, `build_parser()`, `main(argv=None) -> int`; flags `--null {v1,v2}`, `--universes`, `--triggers`, `--work-dir`, `--source-cache`, `--gbm-tickers`, `--shuffled-copies`, `--date`, `--results-dir`, `--json-dir`. Per-ticker checkpoints at `<work-dir>/checkpoints/<null>/<label>/<trigger>/`. |
| V230-5 | Run: the v1 placebo measurement (stop gate 1) | 2 | sonnet | C `docs/superpowers/results/<date>-v230-null-placebo.md`, C `docs/superpowers/results/v230/placebo-v1.json`, M this index (`## Handoff`) | the recorded v1 table; gate outcome `BIAS` (continue) or `NO-BIAS` (stop V230-6..17) |
| V230-6 | v2 panel, cross-section and stage checkpoints | 3 | opus | C `swingbot/core/backtesting/screen/null_v2.py`, C `tests/backtesting/screen/test_null_v2_panel.py` | `NULL_VERSION = "v2"`; `STAGES = ("panel", "draw", "race")`; `@dataclass(frozen=True, eq=False) TickerPanel(ticker, dates: np.ndarray, eligible, trend, atr_pct, event, control: np.ndarray \| None, level_bars: np.ndarray \| None)` (`level_bars` shape (n, 4): Open, High, Low, ATR14[t-1]; NaN at row 0); `ticker_panel(ticker, df, ctx, *, cap, control=None, keep_bars=False) -> TickerPanel` (`eligible = null.eligible_mask(raw, member, warm, cap)` minus `ctx["condition"]` when present; `event = ctx["raw"]`; `atr_pct = ATR14 / Close`); `@dataclass(frozen=True, eq=False) CrossSection(dates: pd.DatetimeIndex, tickers: tuple[str, ...], eligible, trend, tercile (int8, -1 off), event, control \| None, pos (int32, -1 absent))`; `atr_terciles(atr_pct_row, eligible_row) -> np.ndarray`; `cross_section(panels: Mapping[str, TickerPanel]) -> CrossSection`; `class StageCheckpoint` (`load(key)`, `save(key, obj)`, `done() -> set[str]`; no-op when its directory is None); `open_stage(root, stage, manifest, out=print) -> StageCheckpoint` (dir `<root>/<stage>/`, manifest adds `null_version`, `stage`; mismatch `ValueError`); `resumable_map(keys, fn, *, checkpoint, out=print, label="") -> dict` |
| V230-7 | v2 ticker-scope draw, refusals and the golden draws | 3 | opus | M `swingbot/core/backtesting/screen/null_v2.py`, C `tests/backtesting/screen/test_null_v2_draw.py`, C `tests/backtesting/screen/test_null_golden.py`, C `tests/backtesting/screen/golden/null_draws.json` | `DRAW_COLUMNS = ("event_ticker", "event_pos", "event_date", "null_ticker", "null_pos", "fill")`; `date_seed(idea, day) -> list` (`null.null_seed(f"{idea}:v2", day.strftime("%Y-%m-%d"))`); `ticker_pool(xs, row, col, *, require_control=False) -> np.ndarray` (column indices); `@dataclass(frozen=True) DrawResult(table: pd.DataFrame, dropped: Counter, event_dates: int, starved_dates: int, slots: int, unfilled: int)`; `draw_ticker_scope(xs, booked: Mapping[str, np.ndarray], *, idea: str, k=null.K) -> DrawResult`; `SCOPE_MISMATCH = "SCOPE_MISMATCH"`; `NULL_STARVED = "NULL_STARVED"`; `STARVED_SHARE = 0.5`; `class NullRefusal(ValueError)` with `.code`; `check_starvation(result, scope) -> None` |
| V230-8 | v2 market-scope draw | 3 | opus | M `swingbot/core/backtesting/screen/null_v2.py`, C `tests/backtesting/screen/test_null_v2_market.py` | `TRAILING_DAYS = 252`; `market_pool(panel, pos, *, cap) -> np.ndarray` (own-frame positions); `draw_market_scope(panels, booked, *, idea, cap, k=null.K) -> DrawResult` (`null_ticker == event_ticker`) |
| V230-9 | v2 level-entry and avoid-control draws, and the dispatcher | 4 | opus | M `swingbot/core/backtesting/screen/null_v2.py`, C `tests/backtesting/screen/test_null_v2_level.py` | `level_fill(bar_row, depth, direction) -> float` (NaN when unfilled; v1 `_null_fills` semantics on a `level_bars` row); `draw_ticker_level(xs, panels, booked, depths: Mapping[str, np.ndarray], *, idea, direction, k=null.K) -> DrawResult` (`fill` column set; unfilled slots replaced from the rest of the date's pool in `child_seed` permutation order); `draw_control(xs, booked, *, idea, k=null.K) -> DrawResult` (control flag required of *j*, seed `f"{idea}:v2:control"`); `draw(xs, panels, booked, *, idea: Idea, depths=None) -> DrawResult` (dispatch by `idea.scope` / `idea.entry`, then `check_starvation`) |
| V230-10 | v2 race pass and scatter | 4 | opus | M `swingbot/core/backtesting/screen/null_v2.py`, C `tests/backtesting/screen/test_null_v2_race.py` | `race_pass(table, load, *, shape, cap, direction, costs, level_factor=race.LEVEL_SLIPPAGE_FACTOR, horizons=forward.HORIZONS, checkpoint=None, out=print) -> pd.DataFrame` (adds `r`, `gross_r`, `outcome`, `fwd_<h>`; `load(ticker) -> tuple[pd.DataFrame, pd.Series] \| None`, frame and ATR14; one frame resident); `@dataclass(frozen=True) EventNull(mean_r, mean_gross_r, outcomes: Counter, fwd: dict[int, float], timeout_r: tuple, slots: int, unfilled: int)`; `scatter(raced) -> dict[tuple[str, int], EventNull]` |
| V230-11 | v2 orchestration with staged checkpoints | 4 | opus | C `swingbot/core/backtesting/screen/screen_v2.py`, C `tests/backtesting/screen/test_screen_v2.py` | `@dataclass(frozen=True) V2Inputs(load: Callable[[str], pd.DataFrame \| None], context: Callable[[str, pd.DataFrame], dict], extras: Callable[[str, pd.DataFrame, dict], dict])`; `@dataclass V2Ticker(ticker, counters: Counter, events: list[dict], null_outcomes: Counter, excess: dict[int, list], extras: dict, null_timeout_r: list, null_slots: int, null_unfilled: int, depths: dict \| None, avoid_control: list \| None)`; event row keys `ticker, entry_date, exit_date, r_event, r_null, outcome, cost_event, cost_null`; `run_v2(idea, names, inputs, *, costs, checkpoint_dir=None, manifest=None, out=print, event_tickers=None) -> list[V2Ticker]` (raises `NullRefusal` after stage 2, before stage 3) |
| V230-12 | `screen_idea` v2 wiring, `screen-v2` instrument and the v2 report blocks | 5 | opus | M `scripts/backtest/screen_idea.py`, C `swingbot/core/backtesting/screen/v2_report.py`, C `tests/backtesting/screen/test_v2_report.py`, C `tests/backtest_scripts/test_screen_v2_wiring.py`, C `tests/backtest_scripts/conftest.py`, M the seven `tests/backtest_scripts/test_screen_*.py` modules that call `screen_idea.main`, M `swingbot/core/backtesting/instrument/stats.py`, M tests pinning `stats.INSTRUMENTS` | `screen_idea.NULL_VERSION = "v2"`; `INSTRUMENT_V2 = "screen-v2"`; `instrument() -> str`; `screen_universe_v2(idea, universe, cache_dir, *, start, end, tickers=None, out=print, context=None, checkpoint_dir=None, event_start=EVENT_START) -> tuple[list[TickerScreen], Counter]`; `_v2_screen(t: V2Ticker) -> TickerScreen`; `NullRefusal` printed as `refused: <code>: ...`, exit 2; `_render_head` prints null version and scope; fixture `screen_null_v1` in `tests/backtest_scripts/conftest.py`; `stats.INSTRUMENTS` gains `"screen-v2"`; `v2_report`: `REGIMES`, `OMITTED_V2_BLOCKS: tuple[tuple[str, str], ...]`, `MEANING: dict[str, str]` (by scope), `load_sectors(path) -> dict[str, str] \| None`, `v2_summary(events, *, scope, sectors) -> dict`, `render_v2(block) -> list[str]` |
| V230-13 | Placebo under v2: planted check and acceptance (stop gate 2) | 5 | opus | M `scripts/backtest/screen_placebo.py`, M `tests/backtest_scripts/test_screen_placebo.py`, M `docs/superpowers/results/<date>-v230-null-placebo.md`, C `docs/superpowers/results/v230/placebo-v2.json`, C `docs/superpowers/results/v230/placebo-planted.json`, M this index (`## Handoff`) | `RUNNERS["v2"] = run_cell_v2`; `run_cell_v2(universe_dir, trigger, *, checkpoint_dir) -> list[dict]`; `--planted` flag; gate outcome `ACCEPT` (continue) or `STOP` (V230-14..17 do not run) |
| V230-14 | The fifth clause and one BH family | 5 | opus | M `swingbot/core/backtesting/screen/verdict.py`, C `tests/backtesting/screen/test_verdict_event.py`, M `swingbot/core/backtesting/screen/diagnostics.py`, M `tests/backtesting/screen/test_diagnostics.py`, M `scripts/backtest/screen_idea.py`, M `tests/backtest_scripts/test_screen_v2_wiring.py`, M tests pinning the "`screen-v1` family" text | `verdict.EVENT_CLAUSE = "event_r"`; `@dataclass(frozen=True) EventBound(n, mean, ci_low, ci_high, p, holds: bool, gating: bool)`; `event_clause(low) -> bool`; `event_bound(events: list[PairedEvent], *, gating, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, seed=stats.WEEK_BOOTSTRAP_SEED) -> EventBound`; `apply_event_clause(v, bound) -> Verdict`; `diagnostics.screen_family_q(rows, row, instrument=None) -> float \| None` (all rows); `screen_idea.with_event_clause(summary, idea, *, gating: bool) -> dict` (adds `summary["event_bound"]`) |
| V230-15 | Re-screen mode, run marker and the summary script | 6 | sonnet | C `swingbot/core/backtesting/screen/rescreen.py`, C `tests/backtesting/screen/test_rescreen.py`, M `scripts/backtest/screen_idea.py`, C `scripts/backtest/rescreen_summary.py`, C `tests/backtest_scripts/test_screen_rescreen.py`, M `tests/backtesting/instrument/test_date_literal_guard.py` | `rescreen.RESCREEN_V1: tuple[str, ...]` (the twelve, ledger order); `RESCREEN_PREFIX = "screen2-"`; `rescreen_id(name) -> str`; `v1_row(rows, name) -> dict \| None`; `rescreen_refusal(name, rows, results_dir) -> str \| None`; `rescreen_hypothesis(base, v1) -> str`; `class RunMarker(directory)` with `start() -> str \| None`, `finish() -> None`, `crash_note() -> str \| None`; `MEANS_RE`; `summary_rows(rows, results_dir) -> list[dict]`; `render_summary(rows, *, date) -> str`; `screen_idea` flag `--rescreen-v1` (needs `--checkpoint-dir` on a real run), results path `<date>-screen2-<name>.md`; `rescreen_summary.main(argv=None) -> int` writing `<date>-v230-rescreen-summary.md` |
| V230-16 | Guardrail, methodology doc, screen skill and Codex mirror | 6 | sonnet | M `.claude/hooks/guardrails.py`, M `tests/hooks/test_guardrails.py`; `.codex/hooks.json` verified (it registers the same `guardrails.py`; edited only if a registration changes); M `docs/claude/backtest-methodology.md` (inside the Stage −2 bullet only), M `.claude/skills/screen/SKILL.md`, M `.agents/skills/screen/SKILL.md` (via `sync_codex.py`), M `AGENTS.md`, M `tests/hooks/test_doc_sections.py` | `_RESCREEN_V1` (pinned to `rescreen.RESCREEN_V1` by a drift test); `--rescreen-v1` in `_SCREEN_FLAG_OPTIONS`; `flags["rescreen_v1"]`; `_rescreen_deny_reason(flags) -> str \| None`; dated paragraph recording partner decision 2 and its limit; v2 null, fifth clause, `SCOPE`, `screen2-` ids in the skill |
| V230-17 | Run: the batch re-screen and its summary | 6 | sonnet | C `docs/superpowers/results/<date>-screen2-<name>.md` (twelve), M `docs/superpowers/results/preregistration-ledger.jsonl` (twelve appended rows), C `docs/superpowers/results/<date>-v230-rescreen-summary.md` | twelve `screen2-<name>` rows (`instrument: "screen-v2"`) |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-16-v230-screen-v2-rescreen_1-placebo.md` | V230-1..V230-3b | `SCOPE`, the placebo universes, triggers, planted drift, cells and the acceptance rule |
| 2 | `2026-11-16-v230-screen-v2-rescreen_2-placebo-cli.md` | V230-4..V230-5 (with V230-4b) | pipeline parameters and the placebo CLI, the v1 measurement (stop gate 1) |
| 3 | `2026-11-16-v230-screen-v2-rescreen_3-null-v2-draw.md` | V230-6..V230-8 | v2 panel and cross-section, ticker-scope and market-scope draws, golden draws |
| 4 | `2026-11-16-v230-screen-v2-rescreen_4-null-v2-race.md` | V230-9..V230-11 | level and avoid draws with the dispatcher, the race pass, the orchestration |
| 5 | `2026-11-16-v230-screen-v2-rescreen_5-wiring.md` | V230-12..V230-14 | `screen_idea` v2 wiring and report blocks, the v2 placebo acceptance (stop gate 2), the fifth clause and one BH family |
| 6 | `2026-11-16-v230-screen-v2-rescreen_6-rescreen.md` | V230-15..V230-17 | re-screen mode, guardrail, methodology doc and skill, the batch run |

## Decisions this index fixes (inside the spec's "left to the builder")

- Placebo triggers share one frozen race: `CAP = 10`, long, fixed 1.5/3 ATR, next-open entry (spec A1 names the triggers, not their race).
- The planted value is measured, not assumed: the mean, over the planted events, of the event arm's R on the planted universe minus its R on the base universe (`planted_value`); v2 must recover a Δ whose 95% interval contains it.
- `shuffled` keeps only tickers with a bar on every calendar session (a permuted day must exist for every ticker); enlarging it adds universe-wide permutation copies `<T>_c<n>`.
- A market-scope idea in avoid mode or with a level entry is refused at registration (`_scope_problem`): no such idea exists and the spec's market pool is defined for the next-open edge path only.
- `--count-only` keeps its v1 draw counts (it races nothing and gates nothing); under v2 a dry run with `--tickers` restricts the **event** tickers while stage 1 covers the whole cached universe, because the pool is the cross-section.
- Descriptive blocks under v2: forward-drift excess, null timeouts and level null depths are computed per null bar on its own ticker's frame; `restricted`, `stressed`, `repriced`, `shock` and `control` are omitted and listed by `v2_report.OMITTED_V2_BLOCKS` in every v2 results doc.
- A date counts as starved when at least one of its events found a pool under the floor; the refusal fires when starved dates exceed half of the event dates.
- Placebo cells are keyed by universe **label** (`gbm-<n>`, `shuffled-c<copies>`), so an enlarged run writes a new cell beside the noisy one; `acceptance` (V230-4 CLI, V230-13) reads only the **latest cell per universe kind and trigger**, otherwise the superseded NOISY cell keeps returning ENLARGE.
- Builder calls recorded in Part 1 (V230-2..3b task text explains each): `ATR_PER_SIGMA = 1.9` (from a simulation); planted events are `p_high20` events spaced at least `PLANT_SPACING` = 120 bars so null bars stay out of the drift ramp; `planted_trigger` identifies a ticker by its first five closes (the screen's `events(df)` gets no ticker name); `accept_cell` returns FAIL for an interval wholly outside ±0.02R even when wide, and a noisy or missing planted cell yields ENLARGE.
- Part 3 contracts for V230-9..11 (beyond the ledger rows): `null_v2.py` private helpers created in V230-7 and reused by V230-9's level and control draws: `_v2_name(idea)`, `_records(event_ticker, event_pos, day, null_tickers, null_pos, fills=None)`, `_table(records)`, `_events_by_row(xs, booked)` (`{row: [(col, pos)]}`, columns ascending; `ValueError` on an unknown ticker), `class _Tally` (`records`, `dropped`, `add`, `count_slots`, `count_unfilled`, `mark_date(day, starved)`, `result()`). `DrawResult.dropped` is a Counter per event ticker; V230-11 sets each `V2Ticker.counters["dropped_no_match"]` from it. `STAGE_MANIFEST = "manifest.json"`; `ticker_pool(..., require_control=True)` raises `ValueError` when `xs.control` is None; `NullRefusal` text is `"<code>: <detail>"`; `check_starvation` raises `ValueError` on an unknown scope. `open_stage` adds only `null_version` and `stage`, so V230-11 puts `scope` in the manifest it passes; `open_stage` refuses a root holding a v1 `manifest.json` or `*.pkl`. Tercile cut points come from the date's eligible ATR%, but every ticker with a finite ATR% gets a tercile (the event ticker is never eligible at its own bar).
- Part 4 contracts for V230-12..17 (beyond the ledger rows): level draws write one row per drawn slot; a slot still unfilled after replacement is a sentinel row (`null_ticker=""`, `null_pos=-1`, `fill=NaN`), so for level draws `DrawResult.slots == len(table)` and `unfilled == (null_pos < 0).sum()`; next-open, market and control tables never hold sentinels. `null_v2.UNFILLED = "unfilled"`; `race_pass` keeps input columns and row order, needs a unique index, skips sentinels, and raises `ValueError` on a ticker mixing level and next-open rows or whose `load` returns None. `V2Ticker.counters` = `run_book` counters + `dropped_no_match` (+ `control_below_floor` in avoid mode); event rows' `cost_event` / `cost_null` are `gross_r - r` (null side: mean over filled slots); an event is kept when its null has at least one filled slot; `null_timeout_r` only for the trail shape; `depths` = `{"event", "null"}` for level ideas only; `avoid_control` rows have the `events` keys. `inputs.extras(name, df, ctx)` runs on event tickers only and its `ctx` carries `"book"` (the pre-draw `RaceResult`), so V230-12 takes avoid kept/overnight counts from `V2Ticker.events`. Stage manifest = `{"idea", **caller manifest, "scope", "event_tickers_sha256", "costs"}` (changed event tickers or costs are refused); stage keys: per ticker in `panel`, the single key `draw` holding `(DrawResult, DrawResult | None)`, per null ticker in `race`. `screen_v2._ENTRY_OFFSET` copies `screen_idea._ENTRY_OFFSET`; V230-12 adds a drift test pinning them equal.

## Handoff

- 2026-11-17: partner decided to **split this plan at stop gate 1**. V230-1..V230-5 (Parts 1-2, committed) stay as this plan. V230-6..V230-17 move to a new numbered plan (run /new-doc for its vN; rename the ids in committed Parts 3-4 and their ledger rows; the Part 5 header is committed in `_5-wiring.md`, no tasks yet). V230-12 measured 32 KB and splits into two tasks in the new plan (natural cut: stats + `v2_report.py` + its test / conftest + the seven v1 pins + `screen_idea` wiring + wiring tests); full single-task draft at `.superpowers/briefs/v230-12-draft.md`. Part 5 contracts that Part 6 needs are in the `_5-wiring.md` header. Partner still to confirm: V230-13 treats a placebo `refused:` exit as record-and-ask (not an automatic STOP/ENLARGE); V230-14 keeps `screen_family_q(rows, row, instrument=None)` (None = every ledger row).
