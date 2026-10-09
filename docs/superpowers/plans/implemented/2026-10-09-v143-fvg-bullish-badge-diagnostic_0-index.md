# v143 FVG (bullish) badge diagnostic: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V143-3` or `grep -n "^### Task V143-3:" -A 640 docs/superpowers/plans/2026-10-09-v143-fvg-bullish-badge-diagnostic_*.md`.

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/implemented/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md`](../../specs/implemented/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md) (as amended in `f91a87b5`, `2a00d5a2` and `c29e2e12`: nine features, replay quality score, gap matched on the scenario's clustered level and looked up on the map bar)

**Goal:** Measure once, on TRAIN 2020-01-01..2023-12-31 only, whether any of nine features knowable at the signal bar separates the "FVG (bullish)" confluence plans that work from the ones that do not, at the live geometry and at first targets of 1.25R and 1.00R. It gates nothing and changes nothing live.

**Architecture:** All arithmetic lives in one new module, `swingbot/core/backtesting/fvg_diagnostic.py` (features, gap matching, the replay quality score, geometry copies, the candidate rule, the tables and the markdown renderer). It imports live helpers; no live path imports it, pinned by a test. `scripts/backtest/measure_fvg_bullish_diagnostic.py` is a thin driver: it runs `replay_scenarios` + `simulate_exit` per ticker in a process pool, saves the trade rows under `logs/` before rendering, checks the population against the expected 1,278, and writes one results document. The replay runs exactly once, through `backtest-runner`.

**Tech Stack:** Python 3.11, pandas/numpy, pytest. Existing symbols used (all read on `main`): `backtest_scenarios.replay_scenarios` / `build_confluence_plan` (module attribute) / `_resolve_replay_workers`, `exit_sim.simulate_exit`, `fvg.find_fair_value_gaps_detailed` / `is_displacement_gap` / `DEFAULT_DISPLACEMENT_ATR_K`, `indicators.atr`, `levels.count_confirming_strategies`, `strategy_types.HORIZONS` / `LEGACY_HORIZONS`, `planning.quality.score_plan` / `atr_percentile`, `scanning.regime.get_htf_bias`, `scan_params.ScanParams`, `earnings_calendar.next_reaction_distance` / `CsvSource` / `EARNINGS_CSV_DIR`, `acceptance.CLOSED` / `DECIDED`, `acceptance_levels.enabled_arms`, `session.SessionCalendar`, `universe.is_etf`, and from `scripts/backtest/`: `measure_arms.load_frame`, `measure_acceptance_exits.cache_universe`, `measure_earnings_blackout.load_calendar` / `reaction_positions`.

## Where to work

- **Branch and worktree:** `2026-10-09-v143-fvg-bullish-badge-diagnostic` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic`. V143-1 Step 0 creates it with the `worktree-lifecycle` skill. Every task and the one replay happen there. Name the worktree in every subagent dispatch, and after each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` to confirm the main tree is unchanged.
- **Backtest cache:** `data/backtest_cache/` is gitignored, so the worktree has none. Prefix every real run with `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache` (`backtest_cache._cache_dir` reads it once at import). Never fetch into any cache from this plan.
- **Earnings CSVs:** `market_data/` is gitignored too, and `earnings_calendar.EARNINGS_CSV_DIR` resolves relative to the module file, so inside the worktree it points at a directory that does not exist. Every real run passes `--earnings-dir E:/Documents/Private/Projects/Discord-Bot/market_data/earnings`. The script refuses to replay when that directory holds no CSV, so the earnings feature cannot silently come out empty.
- **Config:** the worktree has no `.env`. `swingbot/config.py:_load_dotenv_file` falls back to python-dotenv's upward search, which finds the main tree's `.env`, the config the expected 1,278 was measured with. `data/universe/` is tracked, so `universe.is_etf` works in the worktree.
- **Skills:** `no-lookahead` before V143-1 and V143-2 (they decide what a bar knew). `backtest-gate` before the V143-5 smoke run and before V143-6. `worktree-lifecycle` before creating, merging and removing the worktree.

## Parts

| Part | File | Tasks | Content |
|---|---|---|---|
| 0 | `_0-index` (this file) | none | Header, constraints, frozen readings, parallelisation |
| 1 | [`_1-instrument`](2026-10-09-v143-fvg-bullish-badge-diagnostic_1-instrument.md) | V143-1 .. V143-4 | The module and its tests |
| 2 | [`_2-script-run-close-out`](2026-10-09-v143-fvg-bullish-badge-diagnostic_2-script-run-close-out.md) | V143-5 .. V143-8 | The driver, the one replay, close-out, the full suite |

## File map

| File | Created by | Responsibility |
|---|---|---|
| `swingbot/core/backtesting/fvg_diagnostic.py` | V143-1 (extended by V143-2, 3, 4) | Every number and every table. No I/O |
| `tests/backtesting/test_fvg_diagnostic_import_guard.py` | V143-1 | No live path imports the module |
| `tests/backtesting/test_fvg_diagnostic_features.py` | V143-1 | Feature values, gap matching, replay quality, no lookahead |
| `tests/backtesting/test_fvg_diagnostic_outcomes.py` | V143-2 | Geometry copies, the population rule |
| `tests/backtesting/fvg_diagnostic_rows.py` | V143-3 | Hand-built trade rows (helper, not collected) |
| `tests/backtesting/test_fvg_diagnostic_rule.py` | V143-3 | The candidate rule, one table failing each clause |
| `tests/backtesting/test_fvg_diagnostic_report.py` | V143-4 | Report shape, coverage, the results document |
| `scripts/backtest/measure_fvg_bullish_diagnostic.py` | V143-5 | Process-pool replay, target capture, refusals, progress, rows file |
| `tests/scripts/test_measure_fvg_bullish_diagnostic.py` | V143-5 | Driver behaviour without a real replay |
| `docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md` | V143-6 (written by the script) | The result |
| `docs/claude/backtest-methodology.md`, `tests/backtesting/test_preregistration_ledger_file.py`, the spec's `Status:` line | V143-7 | Close-out |

## Global Constraints

- **TRAIN only.** Signal dates 2020-01-01..2023-12-31. The 2024-2025 VALIDATION window is never read: the script has no flag that widens the window.
- **Read-only.** No change to `replay_scenarios`, `fvg.py`, `levels.py`, `builders.py`, `quality.py`, `analyze.py`, plans, alerts, charts, the registry, or any config default. No registry row is written or edited by hand. No ledger row: v143 is a diagnostic that spends no budget.
- **Import direction.** The diagnostic may import live code; live code must not import the diagnostic. Live helpers are imported, never copied.
- **No lookahead.** Every feature, and every input to the replay quality score, is computed on `df.iloc[:i + 1]`, `i` the signal bar. The gap is looked up on the window ending at the map bar, which is never later than `i`. Only the exit simulation walks forward.
- **Nine features, 27 looks.** Share of gap filled was dropped before the run as not testable on this population; it is not in the code, and the results document says so. Feature 9, gap open at the signal bar, is its testable form on the replay.
- **The rule is fixed.** A (feature, geometry) pair is a candidate only when its favourable side has N >= 150 closed trades, win rate >= 50%, expectancy > 0, expectancy at least +0.10R above the unfavourable side, and expectancy > 0 in at least 3 of the 4 years 2020-2023. No feature is combined with another. No threshold, favourable side, tolerance or geometry is moved, before or after the run.
- **Under 80% computable is "not tested".** Such a feature cannot be a candidate and is not closed by this diagnostic. The renderer and the closed-table row use those words.
- **Expected population N = 1,278** (of 8,089 triggered confluence plans). The script exits non-zero and writes no results document when N differs by more than 2%. Nobody edits `EXPECTED_N` or `N_TOLERANCE` to get past it.
- **The replay runs once**, through the `backtest-runner` agent (V143-6). `--tickers N` is a development smoke flag and may only write to a scratch `--out-dir`.
- **The script keeps its `if __name__ == "__main__":` guard.** Windows spawns pool workers by re-importing the script; a missing guard killed the prototype.
- **Progress:** a flushed line per ticker, and `logs/measure_fvg_bullish_diagnostic.progress` (a percent figure, rewritten per ticker, deleted on completion).
- **Complexity:** every function ends below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing at 15 or above (`docs/claude/code-complexity.md`).
- **Tests:** per task, `python scripts/dev/testrun.py file <the one test file>`. The full suite runs once, in V143-8.
- **Commits** go on the branch, one per task, staging only the files the task names.

## Frozen readings (how the spec's wording maps to code; fixed here, before the run)

1. **Replay quality score (feature 5).** `fvg_diagnostic.replay_quality` calls `quality.score_plan(direction=plan.direction, badge_status=plan.badge, **inputs)`, the call `planning.params._apply_quality` makes. The inputs mirror `scanning.analyze._build_quality_inputs` on `window = df.iloc[:i + 1]`:
   - `htf_bias`: `get_htf_bias(window, plan.horizon_key)["bias"]`, or `None` when it returns `None` (too little history, or `HTF_CONFLUENCE_ENABLED` off, as live).
   - `volume_ratio`: last volume over its 20-bar mean, `None` under 20 bars.
   - `atr_pct`: `quality.atr_percentile(window)`, the function `analyze.py` imports as `_atr_percentile`.
   - `trigger_distance_pct`: `abs(plan.trigger_price - close) / close * 100`.
   - `confluence_count`: reading 2.
   - `regime`, `rs_percentile`, `breadth`: `None`.
2. **Confluence count.** Live sets `item.target_confluence = levels.count_confirming_strategies(df, h, price, scenario.take_profit, tolerance_pct=CONFLUENCE_DEVIATION_PCT)` and the quality input is its count. `replay_scenarios` returns the plan but not the scenario, and `plan.tp1` is re-selected structurally, so it can differ from `scenario.take_profit`. The driver therefore wraps the module attributes `backtest_scenarios.build_confluence_plan` and `backtest_scenarios.levels_asof` for the duration of one `replay_scenarios` call, records each built plan's scenario (a `levels.Scenario`: `take_profit`, `target_sources`, `stop_loss`, `stop_sources`), and restores both attributes in a `finally` (the `acceptance_replay._break_retest_plans` pattern). Nothing in `replay_scenarios` or any live module is edited. The count is then `levels.count_confirming_strategies(window, HORIZONS[horizon_key], close, target, tolerance_pct=ScanParams.from_config().confluence_deviation_pct)[0]`: the live call, on the as-of window. Without a count the score is `None`; a count is never made up.
3. **Feature 8 (earnings distance)** uses v82's coverage rule (`measure_earnings_blackout.exposure_row`): not computable for an ETF, a ticker with no earnings CSV, or a signal outside the span from the first to the last recorded reaction. Otherwise `next_reaction_distance(signal_pos, positions)` on the SPY-bar session calendar.
4. **Gap matching mirrors how the scan labels the plan.** A plan is "FVG (bullish)" because `levels._cluster_levels` merged the gap's mid, as the candidate `(mid, "FVG (bullish)")`, into the level that became the scenario's target or stop: `primary_strategy_for` ranks `scenario.target_sources + scenario.stop_sources`, and `FVG` is first in `METHOD_PRIORITY`. Clustering is a greedy chain over price-sorted candidates (join while within `CLUSTER_TOLERANCE_PCT` = 1.5% of the bucket's running mean; the level's price is the final mean), so membership is not a single distance test and cannot be re-derived from the level price alone. `count_confirming_strategies` is a separate, looser pass (`abs(price - target) / target * 100 <= tolerance_pct`) that feeds the confluence gate and the quality count; it never writes a label. `match_gap` therefore: tries the target level only when `"FVG (bullish)"` is in the captured `target_sources`, then the stop level only when it is in `stop_sources`; on that level takes the bullish gap from `find_fair_value_gaps_detailed(window)` whose `mid` is nearest it, when `abs(mid - level) / level * 100 <= confluence_deviation_pct` (inclusive). The source check is the one addition to the spec's wording: without it a gap within 5% of the target would be called `target` on a plan whose FVG source sits in the stop's cluster.
   - **The gap is looked up on the map bar.** `replay_scenarios` keeps one level map per `bar_index // LEVEL_REFRESH_BARS` bucket (`levels_asof`, `backtest_scenarios.py:63`), built by the first bar in the bucket that asks: the warm-up bar `MIN_BARS[horizon]`, then every multiple of 5. So the map behind a plan can be up to 4 bars older than the signal bar, and a gap it clustered can have been traded through since. The driver does not assume that arithmetic: its `levels_asof` wrapper records the bar of each call that ADDED a map to the replay's cache, and that bar travels with the plan as `SignalContext.map_bar`. `match_gap` reads `find_fair_value_gaps_detailed(df.iloc[:map_bar + 1])`, with `map_bar` clamped to `i`. A test pins the recorded bar against the real `replay_scenarios`.
   - **Feature 9, gap open at the signal bar:** true when `find_fair_value_gaps_detailed(df.iloc[:i + 1])` still returns the matched gap (same `bar_index`, same `direction`). The finder keeps the freshest three gaps per side, so a gap pushed out by newer ones reads as not open, exactly as the scan would no longer see it. Gap age is `i - gap.bar_index`; height uses ATR14 at the signal bar.
   - **Live builds its map fresh (checked):** `scanning/analyze.py:822-824` calls `levels.collect_candidate_levels(df, h, current_price, ...)` and `levels.build_level_map(df, h, current_price, candidates=candidates)` inside the per-horizon loop of every scan, on that scan's frame. There is no level-map cache across scans or bars under `swingbot/core/scanning/`; the only one is the replay's (`backtest_scenarios.py:63-73`). So the spec's sentence is right: a gap filled before the scan cannot label a live plan FVG.
5. **1R is measured from `plan.entry_price`, else `plan.trigger_price`** (the `acceptance.arm_trade_from_plan` rule), for feature 4 and for the `g125` / `g100` targets.
6. **Medians** (features 5 and 7) are taken over identified trades; a value equal to the median is on the favourable side. Unidentified trades are still split on features 4-8; only the four gap features (1, 2, 3 and 9) exclude them.
7. **Computable share** is computable trades over the whole population N.
8. **An empty unfavourable side fails the +0.10R clause** (there is nothing to be better than). **A year with no closed trade on the favourable side is not a positive year.** Years are signal-date calendar years.
9. **The script also prints the count of all triggered confluence plans** beside the expected 8,089, and one `coverage:` line with the unidentified count and every feature's computable share. Both are disclosures; only the 1,278 gates.

## Review Focus

- A feature or quality input that reads past bar `i`. The truncation tests in V143-1 are the pin; every function slices before it computes.
- The capture wrapper leaving `backtest_scenarios.build_confluence_plan` or `levels_asof` replaced after an exception.
- The gap lookup reading a window later than the signal bar (`map_bar` is clamped to `i`).
- A geometry copy that mutates the shared plan (`dataclasses.replace`, never attribute assignment).
- A threshold or favourable side that differs from the spec's table.
- Any path by which a smoke run could write into `docs/superpowers/results/`, or a second replay could start.

## Parallelisation

One chain, as the spec says. There is no parallel group.

- **Sequential:** V143-1 → V143-2 → V143-3 → V143-4. All four edit `swingbot/core/backtesting/fvg_diagnostic.py`, and each consumes the previous task's symbols (V143-2 calls `features`; V143-3 reads the row shape `trade_row` produces; V143-4 calls `stats`, `side` and `candidate_failures`).
- **Sequential:** V143-5 after V143-4 (the script imports `SignalContext`, `trade_row`, `target_confluence_count`, `earnings_distance`, `population_ok`, `build_report` and `render`).
- **Sequential:** V143-6 after V143-5 (the replay needs the finished script and the smoke run's timing). V143-7 after V143-6 (every number in the closed-table row is copied from the results document). V143-8 last (the one full suite over everything).

## Task list

| Task | Title |
|---|---|
| V143-1 | Worktree, features, gap matching, replay quality, import guard |
| V143-2 | Geometry copies and the trade row |
| V143-3 | Statistics and the candidate rule |
| V143-4 | Report, coverage and results-document renderer |
| V143-5 | Driver script, its tests, and a two-ticker smoke run |
| V143-6 | The one TRAIN replay (`backtest-runner`) |
| V143-7 | Close-out: closed-table row, `EXEMPT`, spec status |
| V143-8 | Full-suite verification |
