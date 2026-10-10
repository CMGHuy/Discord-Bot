# v158 Instrument v2, phase 3: window contract and folds. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief WC4` or `grep -n "^### Task WC4" -A 200 docs/superpowers/plans/2026-10-10-v158-instrument-v2-window-contract_*.md`.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (phase 3 row of "Phases", section 1 "Window contract and folds", cross-cutting rule 2, "Testing", "Data precondition")
**Bump:** bot minor
**Edge:** none (integrity)

**Goal:** `contract.py` becomes the only place an instrument's window dates, universe, fold scheme, purge/embargo and liquidity floor are defined. A new `folds.py` builds purged, embargoed, anchored yearly folds (test years 2014..2025) and pools out-of-fold trades. A causal point-in-time universe gate checks S&P 500 membership and a trailing-dollar-volume floor on the **signal** date. Every live backtest script takes `--instrument v1|v2` and reads its window from the contract. A guard test fails on any date or year literal under `scripts/backtest/` outside an allow-list of closed scripts. A cache-coverage check lists every PIT member whose cached history does not reach back to 2009-06. v1 stays the default and stays byte-identical.

**Architecture:** `InstrumentSpec` gains keyword-with-default fields, appended after `cost_model`. The defaults are v1's values, so the `_SPECS["v1"]` line stays as it is. v2's values are applied with `dataclasses.replace` in a separate statement after the `_SPECS` dict, so the `"v2": InstrumentSpec(...)` line that v157 rewrites is not touched. Four new units live under `swingbot/core/backtesting/instrument/`, each tested alone:
- `coverage.py` reads each cached CSV's first bar.
- `folds.py` builds the folds and does purge, embargo and out-of-fold pooling.
- `universe_gate.py` holds the signal-date membership mask, the causal liquidity floor and the watchlist-slice verdict.
- `cli.py` provides `--instrument`, resolves the window, and gives the v2 refusal for paths a later phase owns.

Scripts call these units. They define no dates. `run_backtest_range.py` and `tune_strategy.py` get real v2 paths: research span, PIT S&P 500, signal-date gate and watchlist slice; the tuner also selects per fold and reports pooled out-of-fold ExpR. Every other live script takes the flag, keeps v1 exactly, and refuses v2 with a message naming the phase that wires it. Closed scripts are left alone and go on the guard's allow-list.

**Tech Stack:** Python 3.11, pandas/numpy, pytest (+xdist via `scripts/dev/testrun.py`), radon, `ast` (guard test). Synthetic OHLCV frames and CSVs are built in `tmp_path`. No backtest cache exists on the dev machine.

## Progress

Not started. Update this block when a phase closes.

## Where to work

- **Branch and worktree:** `2026-10-10-v158-instrument-v2-window-contract`, at `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v158-instrument-v2-window-contract` (written `$WT` below). The main tree is `$R` = `/home/user/Discord-Bot`. Create the worktree in WC1 Step 0 with the `worktree-lifecycle` skill, and name it in every subagent dispatch.
- **Never `cd`.** Use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/...` resolves test paths against `$WT`.
- **No backtest cache on the dev machine.** `data/backtest_cache*` is absent here, so every test builds synthetic frames and CSVs in `tmp_path`. The one real-data step is WC3, the coverage run. It runs wherever `data/backtest_cache_ext/` exists (the partner's laptop or the Hetzner VM, through `scripts/ops/ssh-hetzner.sh`). It records its gap list in a results doc.
- **This plan file is committed on `main`.** Only the implementation is branched. Each task commits on the branch. After every task, run `git -C $R status --short` and confirm the main tree is unchanged.
- **The bump (`bot` minor) is applied at close-out (`/close-out`)**, after WC12 is green. No task here edits `VERSION.json`.
- **Parallel plan v157 (fills/costs, phase 2)** is written alongside this one. The cross-plan contract is listed under Global Constraints. Whichever plan merges second resolves the trivial `contract.py` / `test_contract.py` merge.

## Global Constraints

- **Rule 1, verbatim from the spec:** "v1 is byte-identical until cutover. `resolve("v1")` reproduces today's behaviour exactly, and a pinned golden run proves it at every phase." `tests/backtesting/instrument/test_v1_golden.py` stays green after every task. Script-level v1 identity has its own proof: WC7's pinned-literal test asserts that every v1 window (`run_backtest_range.TRAIN`/`VALIDATION`, the tuners' `TRAIN`, `admin/jobs.TRAIN_WINDOW`/`VALIDATION_WINDOW`/`_VALIDATION_START_TUPLE`, `arms/windows.VALIDATION_START`) equals today's literal tuples. Under `--instrument v1` (the default) every script passes `instrument=None` to `run_backtest`, which is exactly what it passes today (`cli.run_instrument`).
- **Rule 2, verbatim:** "Scripts never define dates. Every backtest script takes `--instrument v1|v2` and reads spans from the contract. A guard test fails on a date literal under `scripts/backtest/` (an allow-list covers closed, historical scripts that must keep reproducing their committed results)." How this plan applies it:
  - **Closed scripts** stay v1-only. They take no `--instrument` flag and sit on the guard's `ALLOW` map, each with a one-line reason (partner decision 3).
  - **Non-replay utilities** (`compare_backtest_json.py`, `harvest_select.py`, `validate_component.py`) never run a backtest or choose a window. They sit on a separate `NO_REPLAY` map with reasons and take no flag.
  - **Every other script under `scripts/backtest/`** must call `cli.add_instrument_arg`, and the guard checks this.
  - **The guard catches year-only constants as well as ISO dates:** `range(2013, 2026)`, `("2021", "2022")`.
- **The cross-plan contract with v157 (binding):**
  - Under v2, `BacktestTrade.entry_date` is the actual fill date. v157 adds a `signal_date` field that carries the signal bar's date.
  - Folds assign a trade by `entry_date`. PIT membership and the liquidity floor read `signal_date` through `universe_gate.signal_day(trade)`. That function falls back to `entry_date` while the field is absent, i.e. before v157 lands. Under v1 entry date and signal date are the same bar, so the fallback is exact there.
  - v158 appends keyword-with-default fields to `InstrumentSpec` and never edits `FillModel`, `CostModel` or the `"v2": InstrumentSpec(...)` line. v157 edits only those.
  - This plan does not touch `exit_sim`, `fills.py`, `costs.py`, the arms/strategy/confluence engines or `backtest_wf.py`.
- **Partner decisions (2026-10-10), binding:**
  1. A **causal PIT liquidity floor**: average `Close*Volume` over the `lookback_bars` bars ending at the signal bar, plus a price floor on the signal bar's close, with thresholds frozen in `contract.py` and used by v2 only. A no-lookahead test proves it reads no bar after the signal date. The values equal today's live floor: $20M average dollar volume, $5 price, 20 bars (`config.UNIVERSE_MIN_DOLLAR_VOL` / `UNIVERSE_MIN_PRICE` defaults). They are frozen literals, not read from config.
  2. **`embargo_days`**: a per-horizon lookup, `folds.embargo_days_for(hk)`, reads `strategy_types.HORIZONS[hk]["max_holding_days"]`. The contract field holds the global maximum (270) as the default for callers that pool horizons.
  3. **Allow-list**: as above.
  4. **v1 windows** live in the contract as v1-only fields `train_window` / `validation_window`. Script-level names become aliases of them.
  5. The **v157 contract**: as above.
  6. **Folds**: yearly test folds 2014..2025, i.e. 12 folds with at least 4 training years before the first. The closed scripts keep their own `FOLD_YEARS`.
  7. **Coverage**: unit-tested on synthetic CSVs. The real run is WC3.
- **Embargo under anchored folds:** an anchored train fold ends the day before its test fold starts, so no train trade can enter after the test fold's end, and the embargo never fires there. `folds.split_fold` still implements it generically (a `Fold` whose `train_end` lies past `test_end`). The fold tests prove both the boundary and the no-op. Purge does bite under anchored folds: a train trade still open at the test fold's start is dropped.
- **v2's holdout is sealed.** `cli.window_for(spec, "validation")` under v2 raises `SystemExit` with `cli.HOLDOUT_SEALED`. A `--from/--to` window under v2 must lie inside the research span. Reading the holdout (one shot per pre-registration) is not built here. `admin/jobs.assert_train_only` stays v1-pinned and behaviour-identical.
- **Out of scope here:** fills and costs (v157); a v2 `arms/windows.STAGES` table, a v2 `measure_arms`, v2 `wf_*`, and the scenario/confluence replay under v2 (phases 5/6: those scripts refuse v2 through `cli.require_v1`); `ANCHORED_FOLDS` and the 2018-06 stage literals in `swingbot/core/backtesting/` (v1 machinery outside the guard's scope, left as is); the week-clustered bootstrap mapping (phase 6); the registry `instrument_version` column (phase 6); the `backtest-methodology.md` update (phase 6).
- **Complexity:** every new or changed function must be < 15 (`python -m radon cc -s -n C <files>`). Legacy functions must never get worse. Measured on `main` at `b180c882`: `run_backtest_range.main` 65 (F), `run_scenario_mode` 19, `pool` 15. WC8 therefore adds v2 behaviour through helpers called from `main`, and extracts window resolution out of `main`, so `main`'s score must go down, not up.
- **Config determinism in tests:** any test that runs `run_backtest` first calls `pin_code_defaults(monkeypatch)` from `tests/backtesting/test_pullback_dryup_witness.py`.
- **Two OHLCV caches:** the coverage check reads `swingbot.core.marketdata.backtest_cache.CACHE_DIR` (`data/backtest_cache[_ext]/`), never `market_data/`. `BACKTEST_CACHE_DIR` is read once at import. Tests patch the `CACHE_DIR` module attribute or pass `cache_dir=` explicitly.
- **Green means `0 failed` and `0 xfailed`.**

## Parallelisation

| Task | Files (disjoint?) | Depends on | Why sequential |
|---|---|---|---|
| WC1 contract fields | `instrument/contract.py`, `tests/backtesting/instrument/test_contract.py` | — | Every later task imports the new fields |
| WC2 coverage module + script | `instrument/coverage.py`, `scripts/data/check_cache_coverage.py`, `tests/backtesting/instrument/test_window_coverage.py` | WC1 | Reads `spec.warmup_start` / `spec.universe` / `spec.research_span` |
| WC3 coverage run | `docs/superpowers/results/2026-10-10-v158-cache-coverage.md` | WC2 | Runs WC2's script on the real cache |
| WC4 folds | `instrument/folds.py`, `tests/backtesting/instrument/test_folds.py` | WC1 | Can run **in parallel with WC2, WC3, WC5, WC6**: disjoint files, and it needs only the contract fields |
| WC5 universe gate | `instrument/universe_gate.py`, `tests/backtesting/instrument/test_universe_gate.py` | WC1 | Can run **in parallel with WC2–WC4, WC6**: disjoint files, and it needs only `LiquidityFloor` |
| WC6 CLI helper | `instrument/cli.py`, `tests/backtesting/instrument/test_instrument_cli.py` | WC1 | Can run **in parallel with WC2–WC5** |
| WC7 v1 window aliases | `run_backtest_range.py`, `tune_strategy.py`, `tune_exit_v2.py`, `tune_confluence_gates.py`, `swingbot/admin/jobs.py`, `arms/windows.py`, `tests/backtesting/instrument/test_v1_windows_pinned.py` | WC1 | Edits the same script files as WC8, WC9 and WC10, so it must land before them |
| WC8 `run_backtest_range --instrument` | `scripts/backtest/run_backtest_range.py`, `tests/scripts/test_run_backtest_range_instrument.py` | WC5, WC6, WC7 | Calls `universe_gate` (WC5) and `cli` (WC6); same file as WC7 |
| WC9 `tune_strategy --instrument` (folds) | `scripts/backtest/tune_strategy.py`, `tests/scripts/test_tune_strategy_instrument.py` | WC4, WC5, WC6, WC7 | Calls `folds` (WC4), `universe_gate` (WC5) and `cli` (WC6); same file as WC7. Can run **in parallel with WC8 and WC10** (disjoint files; it only imports existing `run_backtest_range` helpers, whose signatures WC8 leaves unchanged) |
| WC10 flag on the remaining live scripts | `tune_exit_v2.py`, `tune_confluence_gates.py`, `measure_arms.py`, `wf_run.py`, `wf_components.py`, `permutation_test.py`, `quarterly_revalidation.py`, `emit_cohort_registry.py`, `ablation.py`, `measure_strategy_arm.py`, `tests/scripts/test_instrument_flag_scripts.py` | WC6, WC7 | Calls `cli` (WC6); two of its files are also edited by WC7. Can run **in parallel with WC8 and WC9** |
| WC11 date-literal guard | `tests/backtesting/instrument/test_date_literal_guard.py` (+ any one-line literal fix it surfaces in a live script) | WC7, WC8, WC9, WC10 | The guard asserts on the end state of every live script |
| WC12 full suite | — | WC1–WC11 | Final gate |

Recommended order: WC1, then {WC2→WC3, WC4, WC5, WC6} with at most 2 implementers at once, then WC7, then {WC8, WC9, WC10}, then WC11 and WC12.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates, consumed later |
|---|---|---|---|---|---|
| WC1 | Contract span, universe, fold and floor fields | 1 | sonnet | M `swingbot/core/backtesting/instrument/contract.py`, M `tests/backtesting/instrument/test_contract.py` | `LiquidityFloor(min_avg_dollar_vol: float, min_price: float, lookback_bars: int)` (frozen dataclass). New `InstrumentSpec` fields, in this order after `cost_model`, defaults = v1: `universe: str \| None = None`, `research_start: str = "2020-01-01"`, `research_end: str = "2023-12-31"`, `holdout_start: str = "2024-01-01"`, `fold_scheme: str = "none"`, `fold_test_years: tuple[int, ...] = ()`, `purge: bool = False`, `embargo_days: int = 0`, `train_window: tuple[str, str] \| None = ("2020-01-01", "2023-12-31")`, `validation_window: tuple[str, str] \| None = ("2024-01-01", "2025-12-31")`, `warmup_start: str \| None = None`, `liquidity_floor: LiquidityFloor \| None = None`. Property `research_span -> tuple[str, str]`. v2 values: `universe="sp500_pit"`, `research_start="2010-01-01"`, `research_end="2025-12-31"`, `holdout_start="2026-01-01"`, `fold_scheme="anchored_yearly"`, `fold_test_years=tuple(range(2014, 2026))`, `purge=True`, `embargo_days=270`, `train_window=None`, `validation_window=None`, `warmup_start="2009-06-01"`, `liquidity_floor=V2_LIQUIDITY_FLOOR`, where `V2_LIQUIDITY_FLOOR = LiquidityFloor(20_000_000.0, 5.0, 20)`. These are set via `_SPECS["v2"] = dataclasses.replace(_SPECS["v2"], **_V2_WINDOW)` after the dict |
| WC2 | Cache-coverage check | 1 | sonnet | C `swingbot/core/backtesting/instrument/coverage.py`, C `scripts/data/check_cache_coverage.py`, C `tests/backtesting/instrument/test_window_coverage.py` | `first_bar_date(path: Path) -> str \| None`; `CoverageReport(required_start: str, covered: tuple[str, ...], late: tuple[tuple[str, str], ...], missing: tuple[str, ...])` with property `gaps -> int`; `research_members(spec) -> list[str]`; `check_coverage(symbols, required_start: str, cache_dir: Path) -> CoverageReport`; `render_markdown(report, first_membership: dict[str, str]) -> str`. CLI: `python scripts/data/check_cache_coverage.py --instrument v2 [--out PATH]`, which exits 1 when `gaps > 0` |
| WC3 | Run the coverage check on the real cache and record gaps | 1 | sonnet | C `docs/superpowers/results/2026-10-10-v158-cache-coverage.md` | The gap list (read by the partner; no code consumer) |
| WC4 | Purged, embargoed anchored folds | 1 | opus | C `swingbot/core/backtesting/instrument/folds.py`, C `tests/backtesting/instrument/test_folds.py` | `Fold(test_year: int, train_start: str, train_end: str, test_start: str, test_end: str)` (frozen); `anchored_folds(spec) -> tuple[Fold, ...]` (empty when `fold_scheme == "none"`); `embargo_days_for(horizon_key: str) -> int`; `split_fold(trades, fold, *, embargo_days: int, purge: bool = True) -> tuple[list, list]` (train, test); `OutOfFold(choices: tuple[tuple[int, Any], ...], trades: list)`; `out_of_fold(trades_by_config: Mapping[Any, Sequence], folds, select: Callable[[Mapping[Any, list]], Any], *, embargo_days: int, purge: bool = True) -> OutOfFold` |
| WC5 | Causal PIT universe gate and watchlist slice | 2 | opus | C `swingbot/core/backtesting/instrument/universe_gate.py`, C `tests/backtesting/instrument/test_universe_gate.py` | `signal_day(trade) -> str`; `causal_liquidity_reason(df, day: str, floor: LiquidityFloor) -> str \| None`; `eligible_trades(trades, spans, df, floor) -> list`; `WATCHLIST_SLICE_MIN_N = 30`; `SliceVerdict(status: str, n: int, expectancy_r: float \| None)` with status in `{"pass", "fail", "thin"}`; `watchlist_slice_verdict(n: int, expectancy_r: float \| None, min_n: int = WATCHLIST_SLICE_MIN_N) -> SliceVerdict` |
| WC6 | `--instrument` CLI helper | 2 | sonnet | C `swingbot/core/backtesting/instrument/cli.py`, C `tests/backtesting/instrument/test_instrument_cli.py` | `add_instrument_arg(parser) -> None` (`--instrument`, `choices=contract.VERSIONS`, `default="v1"`); `spec_from_args(args) -> InstrumentSpec`; `run_instrument(spec) -> InstrumentSpec \| None` (None for v1); `HOLDOUT_SEALED: str`; `window_for(spec, stage: str) -> tuple[str, str]` (stage `"train"` or `"validation"`); `check_inside_research(spec, date_from: str, date_to: str) -> None`; `require_v1(spec, script: str, owner: str) -> None` (SystemExit under v2) |
| WC7 | v1 windows sourced from the contract | 2 | sonnet | M `scripts/backtest/run_backtest_range.py`, M `scripts/backtest/tune_strategy.py`, M `scripts/backtest/tune_exit_v2.py`, M `scripts/backtest/tune_confluence_gates.py`, M `swingbot/admin/jobs.py`, M `swingbot/core/backtesting/arms/windows.py`, C `tests/backtesting/instrument/test_v1_windows_pinned.py` | `run_backtest_range.TRAIN`/`VALIDATION`, `tune_*.TRAIN`, `jobs.TRAIN_WINDOW`/`VALIDATION_WINDOW`, `windows.VALIDATION_START`: same names and values, now aliases of `contract.resolve("v1")` |
| WC8 | `run_backtest_range.py --instrument v1\|v2` | 2 | opus | M `scripts/backtest/run_backtest_range.py`, C `tests/scripts/test_run_backtest_range_instrument.py` | `_resolve_window(args, spec) -> tuple[str, str, int, str]` (extracted from `main`); `_v2_window_trades(summary, date_from, date_to, spans, df, spec) -> list`; `_watchlist_slice(trade_rows, watchlist) -> tuple[str, dict]` (`trade_rows` = main's existing `[(ticker, strat, hk, trade)]` list; returns the report line and the JSON dict `{status, n, expectancy_r}`). v2 JSON gains a top-level `"_watchlist_slice"` key; v1 JSON is unchanged |
| WC9 | `tune_strategy.py --instrument`, fold-selected under v2 | 3 | opus | M `scripts/backtest/tune_strategy.py`, C `tests/scripts/test_tune_strategy_instrument.py` | — |
| WC10 | `--instrument` on the remaining live scripts | 3 | sonnet | M `scripts/backtest/{tune_exit_v2,tune_confluence_gates,measure_arms,wf_run,wf_components,permutation_test,quarterly_revalidation,emit_cohort_registry,ablation,measure_strategy_arm}.py`, C `tests/scripts/test_instrument_flag_scripts.py` | — |
| WC11 | Date-literal guard and flag census | 3 | sonnet | C `tests/backtesting/instrument/test_date_literal_guard.py` | `ALLOW: dict[str, str]`, `NO_REPLAY: dict[str, str]` (rel path → one-line reason) |
| WC12 | Full suite | 3 | haiku | — | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-10-v158-instrument-v2-window-contract_1-contract-coverage-folds.md` | WC1–WC4 | Phase A: contract fields, cache coverage (module and real run). Phase B: folds |
| 2 | `2026-10-10-v158-instrument-v2-window-contract_2-gate-cli-range.md` | WC5–WC8 | Phase B: universe gate. Phase C: CLI helper, v1 aliases, `run_backtest_range` |
| 3 | `2026-10-10-v158-instrument-v2-window-contract_3-tuner-scripts-guard.md` | WC9–WC12 | Phase C: tuner folds, remaining scripts, guard. Phase D: full suite |
