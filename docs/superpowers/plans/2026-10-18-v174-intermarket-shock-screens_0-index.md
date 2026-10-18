# v174 Intermarket shock screens: do sharp bond or dollar moves precede stock gains? Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief V174-4` or `grep -n "^### Task V174-4:" -A 300 docs/superpowers/plans/2026-10-18-v174-intermarket-shock-screens_*.md`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v174-intermarket-shock-screens-design.md`](../specs/2026-10-18-v174-intermarket-shock-screens-design.md) (at a9040d84, including the brief-findings amendment: scope sentence in the ledger `hypothesis`, `CONTEXT_START = "2009-06-01"`, raw-file index checks, committed hash JSON, screen-only BH family; every applied `## Panel review` finding is a requirement)
**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Brief:** `.superpowers/briefs/2026-10-18-v174-intermarket-shock-screens.md` (code context: signatures, excerpts, test patterns)

**Goal:**

Murphy's intermarket work says bonds and the dollar move before stocks, but
the Stage −2 screen can only look at one ticker's own bars, and the screen
cache holds no bond or dollar series. Nothing in the pre-registration ledger
has ever tested a cross-asset input, so the claim is neither used nor ruled
out.

Once this ships, a screen idea can declare named context series
(`CONTEXT = ("TLT",)`) and read them point in time, aligned to the stock's
own dates by exact date and never forward-filled. TLT and UUP adjusted bars
sit in `data/backtest_cache_ext`, pinned by a committed SHA-256 file. Two
frozen fast-event ideas, `bond_spike_rebound` (TLT 5-day return z ≥ +2.0
against its trailing 252 values) and `dollar_drop` (UUP z ≤ −2.0), are each
screened exactly once. Each gets a ledger row whose hypothesis carries the
scope sentence, and a results doc that prints six diagnostics: effective
sample, null overlap, SPY selloff split, per-episode concentration,
screen-family BH q and scope. None of these diagnostics gates the verdict.

The six existing ideas stay byte for byte as they are: same call
(`events(df)`, one argument), same `TickerScreen`, same results doc and same
ledger text. The matched baseline, race shapes, costs and pass rule are
untouched, and nothing reaches the live scan. Success is measured three ways.
The real-call-path parity test passes for the six old ideas. Both shots run
once, serially, from `main`. Each commits its ledger row and results doc, and
the first also commits the hash JSON. A pass licenses only a later
`Edge: expectancy` filter spec. A fail, the likely outcome with ~25 shock
episodes per idea, closes exactly the frozen definition.

**Architecture:** A new pure module `swingbot/core/backtesting/screen/context.py` holds the point-in-time math (`r_lookback`, `trailing_z`, `z_gate`, `context_on`, `near_mask`), the load checks on raw and loaded frames, the file record (rows, dates, fetch date, SHA-256) and the `ContextData` carrier. The registry's `Idea` gains `context: tuple[str, ...] = ()`. `scripts/backtest/screen_idea.py` dispatches `events` through a two-entry table keyed on `bool(idea.context)`. It loads context frames once per universe (`load_context`) and refuses (exit 2) before any ticker runs or any ledger write when a load check or the hash check fails. For context ideas only, it adds a restricted-null pass per ticker (`TickerScreen.restricted`). A second new pure module, `swingbot/core/backtesting/screen/diagnostics.py`, computes and renders the §5 section. Nothing outside `swingbot/core/backtesting/` imports either module (`tests/backtesting/screen/test_import_guard.py`).

**Tech Stack:** Python 3.11, pandas/numpy, pytest, yfinance (one-off fetch only), the v140 Stage −2 screen (`screen/null.py`, `screen/verdict.py`, `instrument/stats.py`).

## Progress

Not started. Update this block when a phase closes.

## Where to work

- **Branch and worktree:** `2026-10-18-v174-intermarket-shock-screens`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens` (written `$WT` below). The main tree is `$R` = `E:/Documents/Private/Projects/Discord-Bot`. V174-1 Step 1 creates the worktree with the `worktree-lifecycle` skill (reuse it if `git worktree list` already shows it). Name `$WT` in every subagent dispatch and check `git -C $R status --short` after each task.
- **Never `cd`** in a Bash call; use absolute paths and `git -C $WT`. Tests: `python $WT/scripts/dev/testrun.py file tests/...`.
- **Bash hook:** a PreToolUse hook rejects Bash commands that contain the string `screen_idea` with an unbalanced quote (heredocs included). Write and edit files with Write/Edit, never with a Bash heredoc; keep Bash commands that name the runner free of apostrophes.
- **Data lives in the main tree only.** `data/` is gitignored. Every fetch and every shot reads `--cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext` (absolute), from the worktree and from `main` alike.
- **This plan is committed on `main`.** V174-1..V174-8 commit on the branch. V174-9 runs the full suite there. V174-10 merges. V174-11 and V174-12 (the two shots) commit their results on `main`. V174-13 closes out on `main`. V174-5 (data fetch) writes only gitignored files and commits nothing.

## Global Constraints

- **Old ideas unchanged, byte for byte.** An idea with `context == ()` is called `idea.events(df)` with exactly one argument. Its `TickerScreen`, results doc (`FIXED_DOC` pin, `tests/backtest_scripts/test_screen_idea.py:411`) and ledger hypothesis (`FIXED_HYPOTHESIS`, `:417`) are identical to today's. Every new doc line, ledger text and summary key is conditional on `idea.context`.
- **Contexted call:** `idea.events(df, {name: context[name] for name in idea.context})`, chosen by the table `_EVENT_CALLS[bool(idea.context)]` in `raw_events`. No `if` chain grows `screen_ticker`.
- **Context window:** `CONTEXT_START = "2009-06-01"` (`context.py`; re-exported as `screen_idea.CONTEXT_START`) to the run's `end` (`WINDOW_END = "2019-12-31"` on a real run). The stock window stays `WINDOW_START = "2010-01-01"` and `EVENT_START = "2011-01-01"`.
- **Load checks, all refusing (exit 2, `refused: <reason>` on stderr) before `screen_universe` runs and before any results doc, hash file or ledger write:**
  1. The context CSV is missing.
  2. The **raw** CSV index (`pd.read_csv(path, parse_dates=["Date"], index_col="Date")`, before `load_frame`) is not monotonic increasing, not unique, tz-aware, or not normalised (a time other than midnight).
  3. A SPY session in `[CONTEXT_START, end]` (from `load_frame(cache_dir / "SPY.csv", CONTEXT_START, end).index`) is missing from the loaded context frame. A missing `SPY.csv` also refuses.
  4. Defined z covers < 95% (`MIN_Z_COVERAGE = 0.95`) of SPY sessions in `[EVENT_START, end]`.
  The frame handed to the idea is `load_frame(path, CONTEXT_START, end)`.
- **Point in time:** `context_on(df_index, series)` = exact-date reindex, a missing date is `False`, never forward-filled; a value at t uses context bars dated ≤ t only. Proven with `tests.backtesting.screen.helpers.assert_prefix_stable` and a "change a bar after t" test.
- **z, frozen:** `r(t) = close(t) / close(t-5) - 1` (row offset, made sound by check 3). `W = r[t-252..t-1]` is trailing and excludes t; `z = (r(t) - mean(W)) / std(W, ddof=0)`. z is NaN (and the gate `False`) when W has < 252 values, any NaN in W or `r(t)`, or `std(W) <= 1e-12` (the floating-point form of the spec's `std(W) == 0`). Gates end in `.fillna(False)` and return `bool` dtype.
- **Ideas, frozen (spec §3):** `bond_spike_rebound`: `CONTEXT = ("TLT",)`, event `z_TLT(t) >= +2.0`, `PARAMS = {"series": "TLT", "lookback": 5, "window": 252, "z": 2.0, "side": "long"}`. `dollar_drop`: `CONTEXT = ("UUP",)`, event `z_UUP(t) <= -2.0`, `PARAMS = {"series": "UUP", "lookback": 5, "window": 252, "z": -2.0, "side": "long"}`. Both `CAP = 10`, `RACE = "fixed"`, `SOURCE = "Murphy (2004), Intermarket Analysis — shock proxy, see v174 § What the two shots can and cannot say"`. `IDEA_MODULES` appends `"bond_spike_rebound", "dollar_drop"` in that order.
- **Data:** a single fetch, `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --tickers TLT,UUP --start 2009-06-01 --end 2020-01-01`, adjusted closes (`auto_adjust=True`, the script's existing call). **Never refetch** after V174-5, and never `--force`.
- **Hash file:** `docs/superpowers/results/2026-10-18-v174-context-hashes.json`, `{ticker: sha256}` over the sorted union of every registered idea's `CONTEXT` (`TLT`, `UUP`), indented 2, sorted keys, trailing newline. A real (non-dry) run of a context idea writes it after the results doc and before the ledger row, only when absent. Any run of a context idea, dry or real, refuses when the file exists and a ticker's current SHA-256 differs from it or is missing from it. CLI flag `--context-hashes PATH`, default that path.
- **Ledger:** no new field (`validate_ledger_row` rejects extras). The scope sentence goes into the `hypothesis` text of a context idea's row. `instrument` stays `"screen-v1"` and `data_source` stays `"yfinance"`.
- **BH:** the head line keeps today's whole-ledger q. The diagnostics section adds the screen-family q = `stats.ledger_qvalues([r for r in rows + [row] if r["instrument"] == "screen-v1"])[row["id"]]`.
- **Diagnostics never gate.** `summary["verdict"]` is computed exactly as today. Every diagnostic decide goes through `verdict.decide` looked up on the module at call time, so the autouse 500-resample patch reaches it.
- **Complexity:** every function written or changed < 15 (`python -m radon cc -s -n C <files> | head`); `summarise`, `screen_universe`, `main` and `publish` grow only through new named helpers.
- **Tests:** context, ideas, diagnostics and registry tests in `tests/backtesting/screen/` (suite `backtesting-arms`); runner tests in a new file `tests/backtest_scripts/test_screen_context_runner.py` (suite `backtest-scripts`). `tests/suites.toml` is not edited. Per-task runs are narrow (`testrun.py file ...`); the full suite runs once, in V174-9.
- **Shots:** each one is dispatched to `backtest-runner` under the `backtest-gate` skill, serially, once. It runs from the main tree after the merge. `screen_idea.py` refuses a second shot by itself (`screen-<name>` in the ledger). No re-run, no other parameters, no third idea.

## Review Focus

- V174-1: `trailing_z` excludes t from W and returns NaN for every undefined case. `context_on` never forward-fills.
- V174-3: the parity test compares digests captured on the **unmodified** code (Step 1) with the modified code, and an old idea's `events` sees exactly one positional argument.
- V174-4: every refusal fires before `screen_universe` and before any write, and the hash check also covers a dry run.
- V174-7: an entry date maps to the SPY session before it (the signal day), and episodes split on a gap of more than 5 sessions.
- V174-8: the restricted-null pass reuses the same seed, K and cap, never touches `summary["verdict"]`, and `FIXED_DOC` / `FIXED_HYPOTHESIS` still pass.

## Parallelisation

Disjoint files and no contract dependency are required for two tasks to run at once. At most 2 implementers run at a time.

- **Wave A (parallel):** V174-1 (creates `screen/context.py` + `tests/backtesting/screen/test_context.py`) and V174-3 (modifies `ideas/__init__.py`, `screen_idea.py`, creates the runner test file). V174-3's seam needs no symbol from `context.py`. V174-5 (data fetch) can run any time before V174-11; it touches no repo file.
- **Wave B (parallel, after A):** V174-2 (appends to `context.py` and its test, so after V174-1) and V174-6 (creates the two idea modules and their tests, modifies `ideas/__init__.py` and `test_ideas_registry.py`). V174-6 needs V174-1's `trailing_z`/`z_gate`/`context_on` and V174-3's `Idea.context`; it runs after V174-3 because both edit `ideas/__init__.py`.
- **Wave C (parallel, after B):** V174-4 (modifies `screen_idea.py` and the runner test; needs V174-2's checks and `ContextData`, and V174-3's seam) and V174-7 (creates `screen/diagnostics.py` + `tests/backtesting/screen/test_diagnostics.py`; needs V174-1's `r_lookback` and V174-2's `ContextData`).
- **Sequential edges:**
  - V174-8 runs after V174-4, V174-6 and V174-7. It edits `screen_idea.py` (as V174-4 does), calls `diagnostics.compute`/`render`, and its end-to-end test runs `bond_spike_rebound`.
  - V174-9 runs after every code task (full suite).
  - V174-10 runs after V174-9 (the merge).
  - V174-11 runs after V174-10 and V174-5: it needs the merged code and the TLT/UUP files.
  - V174-12 runs after V174-11. Both shots append to `preregistration-ledger.jsonl`, and the second shot checks the hash JSON the first one committed.
  - V174-13 runs last (it moves this plan).

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-18-v174-intermarket-shock-screens_1-context-hook.md` | V174-1..V174-5 | worktree, `context.py` (PIT math, load checks, file record), registry field and runner seam with parity, context loading and hash refusals in the runner, TLT/UUP fetch |
| 2 | `2026-10-18-v174-intermarket-shock-screens_2-ideas-diagnostics-shots.md` | V174-6..V174-8 | the two frozen ideas, diagnostics module, restricted null and results-doc wiring |
| 2b | `2026-10-18-v174-intermarket-shock-screens_2b-suite-merge-shots.md` | V174-9..V174-13 | full suite, merge, the two shots, close-out (split from part 2 to stay under 1500 lines) |

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates, consumed later |
|---|---|---|---|---|---|
| V174-1 | Worktree; point-in-time context math | 1 | opus — no-lookahead territory: trailing z and exact-date alignment | C `swingbot/core/backtesting/screen/context.py`, C `tests/backtesting/screen/test_context.py` | `CONTEXT_START = "2009-06-01"`; `LOOKBACK = 5`; `Z_WINDOW = 252`; `STD_FLOOR = 1e-12`; `r_lookback(close: pd.Series, lookback: int = LOOKBACK) -> pd.Series`; `trailing_z(close: pd.Series, lookback: int = LOOKBACK, window: int = Z_WINDOW) -> pd.Series` (float, NaN where undefined); `z_gate(z: pd.Series, threshold: float) -> pd.Series` (`z >= threshold` when `threshold > 0`, else `z <= threshold`; `.fillna(False)`, bool); `context_on(df_index: pd.DatetimeIndex, series: pd.Series) -> pd.Series` (bool, index `df_index`); `near_mask(raw: np.ndarray, cap: int) -> np.ndarray` (bool: some True position p with \|i − p\| < cap) |
| V174-2 | Context load checks and file record | 1 | sonnet — file and index checks in one module, behaviour fixed by the spec | M `swingbot/core/backtesting/screen/context.py`, M `tests/backtesting/screen/test_context.py` | `MIN_Z_COVERAGE = 0.95`; `class ContextError(ValueError)`; `check_raw_index(index: pd.Index, name: str) -> None`; `check_contiguous(index: pd.DatetimeIndex, sessions: pd.DatetimeIndex, name: str) -> None`; `check_z_coverage(z: pd.Series, sessions: pd.DatetimeIndex, name: str, *, event_start: str, minimum: float = MIN_Z_COVERAGE) -> None` (all raise `ContextError`); `file_record(path) -> dict` keys `ticker, rows, first, last, fetched, sha256` (`fetched` = file mtime as ISO date; raises `ContextError` when missing); `@dataclass(frozen=True) ContextData(frames: Mapping[str, pd.DataFrame], calendar: pd.DataFrame, records: Mapping[str, dict])` (`calendar` = the loaded SPY frame) |
| V174-3 | `Idea.context`; table-driven `events` dispatch; `screen_ticker`/`screen_universe` `context=`; real-call-path parity | 1 | opus — the call seam every past and future screen runs through, pinned byte for byte | M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `scripts/backtest/screen_idea.py`, M `tests/backtesting/screen/test_ideas_registry.py`, C `tests/backtest_scripts/test_screen_context_runner.py` | `Idea.context: tuple[str, ...] = ()` (field after `race_shape`; `_load` reads `tuple(getattr(module, "CONTEXT", ()))`); `screen_idea._EVENT_CALLS: dict[bool, Callable]`; `screen_idea.raw_events(idea: Idea, df: pd.DataFrame, context: Mapping \| None) -> pd.Series`; `screen_ticker(idea, ticker, df, spans, *, slippage_bps=None, commission=None, context: Mapping \| None = None) -> TickerScreen`; `screen_universe(idea, universe, cache_dir, *, start=WINDOW_START, end=WINDOW_END, tickers=None, out=print, context: Mapping \| None = None)` (passes `context` to every `screen_ticker`; loading is added in V174-4); test helpers `_digest(screen) -> str`, `_ctx_cache(tmp_path, *, tickers=("AAA", "BBB"), context=("TLT", "UUP")) -> Path` in the runner test file |
| V174-4 | Context loading once per universe; load and hash refusals in `main` | 1 | sonnet — runner CLI and refusals inside one script, behaviour fixed by the spec | M `scripts/backtest/screen_idea.py`, M `tests/backtest_scripts/test_screen_context_runner.py` | `screen_idea.CONTEXT_START` (re-export); `CONTEXT_HASHES = RESULTS_DIR / "2026-10-18-v174-context-hashes.json"`; CLI `--context-hashes` (`type=Path`, default `CONTEXT_HASHES`); `context_tickers() -> tuple[str, ...]` (sorted union of `idea.context` over `IDEAS`); `load_context(cache_dir, tickers: tuple[str, ...], *, end: str = WINDOW_END) -> context.ContextData` (raises `context.ContextError`); `hash_refusal(records: Mapping[str, dict], path) -> str \| None`; `write_hashes(records: Mapping[str, dict], path) -> bool` (writes only when absent); `_context_step(args, idea) -> tuple[context.ContextData \| None, str \| None]` called by `main`; `screen_universe` calls `load_context` once when `idea.context` and `context is None` |
| V174-5 | Fetch TLT and UUP adjusted bars into `backtest_cache_ext` | 1 | haiku — one fixed command and a read-back check, no code | none in git (writes gitignored `data/backtest_cache_ext/TLT.csv`, `UUP.csv`) | the two CSVs: first bar 2009-06-01 (or the first session after), last bar ≤ 2019-12-31, header `Date,Open,High,Low,Close,Volume` |
| V174-6 | The two frozen ideas and their registry pins | 2 | opus — entry signals in no-lookahead territory | C `swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py`, C `swingbot/core/backtesting/screen/ideas/dollar_drop.py`, C `tests/backtesting/screen/test_idea_bond_spike_rebound.py`, C `tests/backtesting/screen/test_idea_dollar_drop.py`, M `swingbot/core/backtesting/screen/ideas/__init__.py`, M `tests/backtesting/screen/test_ideas_registry.py` | `IDEAS["bond_spike_rebound"]`, `IDEAS["dollar_drop"]`; module constants `CONTEXT, CAP, RACE, PARAMS, SUMMARY, SOURCE` and `events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series` (bool, named after the idea); `SUMMARY` texts `"TLT 5-day return z >= +2.0 vs its trailing 252 values"` and `"UUP 5-day return z <= -2.0 vs its trailing 252 values"` |
| V174-7 | Diagnostics module: effective sample, null overlap, selloff split, concentration, screen-family q, scope | 2 | opus — statistical read-outs printed beside a pre-registered verdict, with signal-day mapping | C `swingbot/core/backtesting/screen/diagnostics.py`, C `tests/backtesting/screen/test_diagnostics.py` | `EPISODE_GAP = 5`; `shock_days(idea, data: ContextData, *, event_start: str, event_end: str) -> pd.DatetimeIndex` (= `idea.events(data.calendar, frames)` true dates in the event window); `signal_days(entry_dates: list[str], sessions: pd.DatetimeIndex) -> list[pd.Timestamp]`; `episodes(days: pd.DatetimeIndex, sessions: pd.DatetimeIndex, gap: int = EPISODE_GAP) -> list[pd.DatetimeIndex]`; `screen_family_q(rows: list[dict], row: dict, instrument: str) -> float \| None`; `scope_sentence(idea) -> str`; `compute(idea, events: list[dict], restricted: list[dict] \| None, data: ContextData, *, event_start: str, event_end: str) -> dict` keys `sample, overlap, selloff, concentration`; `render(diag: dict, data: ContextData, *, context_start: str, window_start: str, screen_q: float \| None, scope: str) -> list[str]` (first line `## Intermarket diagnostics (printed, never gating)`) |
| V174-8 | Restricted null per ticker; diagnostics, context data and scope wired into the results doc and ledger row | 2 | opus — touches the matched-null path that feeds the verdict, under byte-identity pins | M `scripts/backtest/screen_idea.py`, M `tests/backtest_scripts/test_screen_context_runner.py` | `TickerScreen.restricted: list \| None = None`; `_books(idea, ticker, df, ctx, costs, exclude: np.ndarray \| None = None)`; `_restricted(idea, ticker, df, ctx, costs) -> list \| None`; `hypothesis(idea)` context branch ending in `diagnostics.scope_sentence(idea)`; `render_results(idea, summary, universe, run)` appends `diagnostics.render(...)` when `idea.context` (reads `summary["context"]` and `run["screen_q"]`, `run["context"]`) |
| V174-9 | Full suite | 2 | haiku — one command through the `test-runner` agent | none | green suite on the branch |
| V174-10 | Merge the branch into `main` | 2 | sonnet — merge with the `worktree-lifecycle` skill, conflict judgement | none (merge commit) | merged code on `main` |
| V174-11 | Shot 1: `bond_spike_rebound` | 2 | sonnet — dispatch to `backtest-runner` under `backtest-gate`, record and commit | C `docs/superpowers/results/2026-10-18-v174-context-hashes.json`, C `docs/superpowers/results/<run date>-screen-bond_spike_rebound.md`, M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `screen-bond_spike_rebound`; the committed hash JSON read by V174-12 |
| V174-12 | Shot 2: `dollar_drop` | 2 | sonnet — dispatch to `backtest-runner` under `backtest-gate`, record and commit | C `docs/superpowers/results/<run date>-screen-dollar_drop.md`, M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `screen-dollar_drop` |
| V174-13 | Close-out | 2 | haiku — the `/close-out` ritual, no code | M this plan's files (moved to `implemented/` or `no-lift/`), M `version_history.json` if the ritual regenerates it | none |

## What follows

Part writers append tasks in id order to their part file. Each part file starts with a short header (title, `**Spec:**` link, a pointer to this index for Global Constraints and Parallelisation). A part writer that finds a ledger contract wrong in a way another part depends on stops with `BLOCKED:` instead of changing it.
