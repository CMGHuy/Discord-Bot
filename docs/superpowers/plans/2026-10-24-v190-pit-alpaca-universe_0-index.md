# v190 — Instrument v3: the point-in-time S&P 500 on Alpaca bars, research 2017–2025 on purged folds, 2026 holdout: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V190-7:" -A 300 docs/superpowers/plans/2026-10-24-v190-pit-alpaca-universe_2-backtest-wiring.md`.

**Bump:** bot patch
**Edge:** none (integrity) — buys statistical power and removes survivorship from the funnel's population; it changes nothing that is traded, and the re-baseline is a description that decides nothing.
**Screen:** exempt (integrity)
**Spec:** [2026-10-24-v190-pit-alpaca-universe-design.md](../specs/2026-10-24-v190-pit-alpaca-universe-design.md)
**Brief:** `.superpowers/briefs/2026-10-24-v190-pit-alpaca-universe.md`
**Worktree:** implement every code task in `.claude/worktrees/2026-10-24-v190-pit-alpaca-universe` (branch of the same name, created in V190-1's first step; `docs/claude/document-lifecycle.md`). The data tasks (V190-18..V190-24) run from the same worktree but read and write the **main checkout's** git-ignored data directories by absolute path. The merge to `main` is V190-25's last step.

## Goal

The research funnel runs on the wrong population. v158 built instrument v2
(point-in-time S&P 500, purged anchored folds, a sealed 2026 holdout, v2
fills and costs), but v2 needs bars back to 2009, which only the yfinance
cache has for 626 of 848 members. v162 then moved training data to the
Alpaca SIP store, which holds only about 77 watchlist names from 2016. So
every pre-registration since runs on instrument v1 and the watchlist, and
the ledger shows the price: v129 arm B underpowered, v122/v135/v180 NO-LIFT
at Stage 0 on 72–134 tickers, and v180's own record unable to say whether
data source, universe or window explains its non-replication. A 2026-10-23
probe found that Alpaca serves full series for delisted S&P members from
2016 (TWTR, XLNX, SIVB, CELG …), so v2's contract can run on the vendor
v162 chose, with survivorship removed and no paid data. It also found the
trap: MON's bars run four years past Monsanto's exit because the symbol
was reused.

Once this ships there is a local point-in-time Alpaca store,
`data/market_data_pit/` (daily, hourly and 15-min bars for every
`sp500_pit` member from 2016-01-04, plus SPY and the context ETFs), an
integrity report that decides — with a stated reason for every cut — which
bars and which signal dates a run may use, and an **instrument v3**:
v2's contract with `store="pit"`, warm-up from 2016-01-04, research
2017-01-01..2025-12-31 on five purged anchored folds (test years
2021–2025), and the 2026 holdout sealed. `--instrument v3` on
`run_backtest_range.py` and `tune_strategy.py` reads that store; nothing
else does.

How it works, in idea: the store is chosen by the instrument, never by a
universe name or an environment variable. `contract.resolve("v3").store`
is `"pit"`; `fetch_backtest_data.apply_data_source` — the one call every
backtest script already makes before reading a bar — sees it and selects
the PIT store in `training_data`, with the frozen `_integrity.json` and a
`research_end` cut. Two mechanisms carry the integrity verdict: **frame
trims** remove a reused symbol's foreign bars inside the loaders, before
any indicator or exit walk reads them, and **signal-date cuts** (runs of
more than 5 missing sessions, and dates whose trailing 60 sessions hold
under 95% of their bars) are subtracted from the membership spans the
signal mask already applies. Both are causal: every decision uses only bars
on or before the date. Worker processes receive the store choice
explicitly, because a pool initializer re-selects by source name only.

What it leaves alone: v1 and v2 read exactly the data they read today,
every script's default ticker list is unchanged, the default instrument
stays `v1`, the funnel (`validate_component.py`) refuses v3 until a later
methodology spec maps its stages to five folds, no badge moves, and no
closed pre-registration is re-run. Nothing goes to the VM.

Success is measured by tests and by one recorded description. The tests
pin: v1 and v2 smoke runs byte-identical with the PIT store on disk; a v3
smoke run on a fixture store applying one frame trim and one span cut; no
bar dated on or after 2026-01-01 reachable in a v3 run (ticker, context
and intraday frames); the watchlist store's exclusion rule unchanged; v3
taking the v2 path at all 17 instrument branch sites; existing calibration
labels unchanged. The re-baseline then runs every live strategy and
confluence under v3 (leg A), under v3 on the watchlist's PIT members only
(leg C) and under v1 on the watchlist (leg B), and records N, the A/B and
C/B ratios, coverage, first counted dates and the MDE (ticker-cluster and
week-cluster) as the citable power columns, with WR and ExpR printed as
description only, under the standing line *"describes an instrument
change; never a lift; selects nothing"*.

## Architecture

- **Instrument v3 (V190-1).** `InstrumentSpec` gains `store: str | None = None`. `_SPECS["v3"]` is `replace(_SPECS["v2"], version="v3", **_V3_WINDOW)` with `store="pit"`, `warmup_start="2016-01-04"`, `research_start="2017-01-01"`, `research_end="2025-12-31"`, `holdout_start="2026-01-01"`, `fold_test_years=tuple(range(2021, 2026))`; fills, costs, liquidity floor, purge and the 270-day embargo are v2's. `folds.MIN_TRAIN_YEARS` stays 4. `VERSIONS` becomes `("v1", "v2", "v3")`, which extends every `--instrument` choice list.
- **Two store roots, worktree-aware (V190-2).** `history_store.store_root(store=None)`: `None`/`"watchlist"` keeps today's rule (`HISTORY_STORE_DIR`, else `<DATA_DIR>/market_data`); `"pit"` is `<DATA_DIR>/market_data_pit` and **never reads `HISTORY_STORE_DIR`**. Both default roots go through `resolve_data_root(name)`: inside `.claude/worktrees/<x>/`, a missing `data/<name>` resolves to the main checkout's. Every path/manifest/load helper gains a keyword-only `store=None`.
- **Integrity reader and frame trims (V190-3).** New `swingbot/core/marketdata/pit_integrity.py` reads `<pit root>/_integrity.json` (shape in § Contracts). `history_store.load(..., store="pit")` applies the ticker's trim window before returning, for every timeframe.
- **PIT selection in `training_data` (V190-4).** `select(name=None, store=None, until=None)` (positional, so a pool initializer can pass all three). The PIT store refuses without `_integrity.json`, refuses a manifest whose sha256 differs from the one frozen in it (`StaleIntegrityError`), admits by `_pit_exclusions` (ok and `flagged: no-reference` in; `short-overlap`, `price-mismatch`, integrity exclusions out; the watchlist store's `_manifest_exclusions` is byte-identical and pinned), cuts every frame at `until`, and exposes `load_intraday`, `signal_cuts()`, `active_store()`, `selection_args()`. `provenance()` gains `store` (alpaca branch) and `integrity_sha256` (PIT). `cache_dir_source.pool_kwargs` and the three `initializer=training_data.select` sites pass `selection_args()`, which is `(source,)` for the watchlist store, so their existing pins hold.
- **Signal-span cuts (V190-5).** `pit_membership.subtract_spans(spans, cuts)` and `membership_map(universe, symbols, cuts=None)`; with `cuts=None` the result is byte-identical.
- **The instrument picks the store (V190-6).** `fetch_backtest_data.apply_data_source(args)` resolves `args.instrument` when present; a spec with `store="pit"` calls `training_data.select("alpaca", "pit", spec.research_end)`, refuses `--data-source yfinance`, and refuses (`SystemExit`) when the regime ticker or any `etfs.json` symbol is not in the store. Since SPY and the ETFs load through `training_data.load_daily`, the `until` cut also cuts every context frame at `research_end`.
- **`run_backtest_range` (V190-7).** Only `_membership_for_run` changes (passes `training_data.signal_cuts()`); `main` (legacy F(62)) gains no branch. Tests pin the v3 end-to-end path on a fixture store, the as-of build seeing no bar after `research_end`, and v1/v2 byte-identity with a PIT store on disk.
- **Branch audit (V190-8).** A test walks the 17 `spec.version` sites and asserts v3 takes the v2 path at each; the two `resolve("v2")` analytics hard-codes get a "v2 alone" comment.
- **Coverage gate (V190-9).** `coverage.check_store_coverage(symbols, required_start, root)` reads the store layout; `check_cache_coverage.py --instrument v3` uses it against the PIT root and 2016-01-04.
- **Labels, ledger vocabulary (V190-10).** `_WINDOW_KINDS["2017-01-01..2025-12-31"] = "RESEARCH"` (additive, existing labels pinned); `stats.INSTRUMENTS` gains `"v3"`, `stats.VERDICTS` gains `"DESCRIPTION"`; a DESCRIPTION row must carry `p: null` and may carry `exp_r: null`.
- **Funnel refusal (V190-11).** `validate_component.py` gains `--instrument` (default v1, behaviour unchanged); `v3` exits with `V3_FUNNEL_REFUSAL`; `v2` exits through `instrument_cli.require_v1`.
- **Fetcher (V190-12).** `--universe sp500_pit` reads the member list via `universe_symbols`, applies `data/universe/symbol_aliases.json` (fetch the Alpaca symbol, store under the membership symbol, manifest entry gains `"alias"`), and turns the `market_dir` identity fallback off (`identity.reference_frame(..., market_dir=None)`).
- **Integrity detectors (V190-13, V190-14).** `scripts/data/alpaca_history/pit_coverage.py` (SPY-calendar expected sessions, missing runs, the causal trailing-60 rule) and `scripts/data/alpaca_history/reuse.py` (break test on every member, start/end gaps against membership and the yfinance reference, kept side from the spans, edge breaks `unresolved`).
- **`check_history_store.py --pit` (V190-15).** Builds `_integrity.json` (identity re-derived against `backtest_cache_ext` only, reference source and sha256, bars dropped before reference, no-bars list, coverage cuts, trims, thresholds, detector blob shas, three manifest sha256s) and a Markdown summary under `docs/superpowers/results/`.
- **Re-baseline report (V190-16).** `scripts/reports/v190_rebaseline_report.py`, modelled on `v162_rebaseline_report.py`. Leg C is leg A's trade rows filtered to watchlist tickers that are PIT members (no second v3 run; v3 refuses `--tickers-file` like v2).
- **Docs (V190-17)**, then **data (V190-18..V190-24)**: wait for and complete the running member backfill, the context pass, aliases, the frozen integrity run, the coverage gate and a v3 smoke run, the three legs via `backtest-runner`, the results doc and the ledger DESCRIPTION row. **Release (V190-25)**: bump, the single full-suite run, merge.

## Global Constraints

- Local only: no VM, no cron, no `ssh-hetzner.sh` call anywhere in this plan. The PIT store never leaves this laptop.
- The Alpaca key lives in the local `.env`; scripts load it, nothing prints, echoes or logs it.
- **One fetcher per root at a time.** The member backfill started 2026-10-24 is already running into the main checkout's `data/market_data_pit/`. No task starts `fetch_alpaca_history.py` (any mode) on that root while another fetcher process runs; V190-18 checks the process list first. No test ever runs the fetcher or `check_history_store.py` against the real store.
- Data tasks pass **absolute** main-checkout paths: `--root E:/Documents/Private/Projects/Discord-Bot/data/market_data_pit`, `--backtest-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`.
- Fetcher guards unchanged: US-regular-session refusal, 3 GB disk floor (`MIN_FREE_BYTES`), `RATE_PER_MINUTE = 120`.
- Store selection belongs to the instrument: no new environment variable, and no universe name (`*_pit` included) ever selects the PIT store. v2 keeps the watchlist store.
- v1 and v2: windows, data, outputs and closed ledger rows unchanged; byte-identity pins in V190-4 and V190-7.
- Exact v3 values: `store="pit"`, `warmup_start="2016-01-04"`, `research_start="2017-01-01"`, `research_end="2025-12-31"`, `holdout_start="2026-01-01"`, `fold_test_years=(2021, 2022, 2023, 2024, 2025)`, `MIN_TRAIN_YEARS = 4` unchanged.
- Integrity thresholds (Claude's calls in the spec): missing-session run cut `> 5`; trailing window 60 sessions, admitted at `>= 0.95` present; reuse break `abs(close/prev_close - 1) > 0.50` with `>= 10×` shift in 50-day median volume or price level, no revert within 20 sessions; start/end gap flag `> 20` sessions; edge break = within 20 bars of first/last bar. V190-21 may recalibrate them on MON, the probe names and one forward and one reverse split, then freezes them in `_integrity.json` and the results doc **before any strategy result is read**; never tuned on outcomes.
- Store window for coverage: membership spans clipped to `2016-01-04..2025-12-31`; expected sessions = dates SPY has a daily bar in the PIT store.
- On the PIT store the identity reference is `backtest_cache_ext` only, never the root `market_data/daily` fallback.
- Re-baseline order: integrity frozen (V190-21) → legs run (V190-23) → result recorded (V190-24). No `--mode update` on either store in between; `StaleIntegrityError` enforces it for the PIT store.
- MDE: unpaired `acceptance_harvest.mde_expectancy_r` at the observed N, reported with the ticker-cluster bootstrap and with `stats.week_cluster_bootstrap`; each names its seed (`WEEK_BOOTSTRAP_SEED` for the week design only).
- Re-baseline report: no per-cell pass/fail or significance mark; prints the cell count (strategies × directions × horizons × legs) and the top-two-horizon share of N and of ExpR; standing line verbatim: *"describes an instrument change; never a lift; selects nothing"*; states that every v3 fold is in-sample or tainted for today's strategies.
- Every function written or changed stays under cyclomatic complexity 15; `run_backtest_range.main` (F(62), legacy) and `_resolve_data_source` gain no branch — new logic goes into helpers.
- Tests use fixture stores under `tmp_path`, never `data/market_data_pit/` or `data/market_data/`. Per-task verification is `python scripts/dev/testrun.py file <test>`; the full suite runs once, in V190-25.
- No new `tests/` directory: every new test file joins an existing directory (and so its suite).
- Each `docs/claude/*.md` edit ships its `AGENTS.md` condensed mirror in the same commit.
- Date literals stay out of `scripts/backtest/*.py` (`test_date_literal_guard.py`); v3 dates live in `contract.py`.
- Stored records change additively only (`docs/claude/schema-evolution.md`): manifest entry `alias`, provenance `store`/`integrity_sha256`, ledger vocabulary `v3`/`DESCRIPTION`.

## Contracts

```python
# swingbot/core/backtesting/instrument/contract.py              (V190-1)
@dataclass(frozen=True)
class InstrumentSpec:
    ...                                   # existing fields unchanged
    store: str | None = None              # None = today's selection (v1, v2); "pit" = v3
STORES = (None, "pit")
_V3_WINDOW: dict                          # the v3 values in Global Constraints
_SPECS["v3"]                              # replace(_SPECS["v2"], version="v3", **_V3_WINDOW)
VERSIONS == ("v1", "v2", "v3")

# swingbot/core/marketdata/history_store.py                      (V190-2, V190-3)
PIT = "pit"; WATCHLIST = "watchlist"
PIT_DIRNAME = "market_data_pit"
def resolve_data_root(name: str) -> Path        # <DATA_DIR>/<name>, else main checkout's when in a worktree
def store_root(store: str | None = None) -> Path
def timeframe_dir(timeframe, *, store=None) -> Path
def file_path(ticker, timeframe, *, store=None) -> Path
def manifest_path(timeframe, *, store=None) -> Path
def manifest(timeframe, *, store=None) -> dict | None
def require_manifest(timeframe, *, store=None) -> dict
def load(ticker, timeframe, session="rth", *, store=None) -> pd.DataFrame | None   # PIT: trim applied (V190-3)

# swingbot/core/marketdata/pit_integrity.py                      (V190-3)
INTEGRITY_NAME = "_integrity.json"
SCHEMA_VERSION = 1
@dataclass(frozen=True)
class Integrity:
    sha256: str                     # sha256 of the _integrity.json file bytes
    doc: dict
    def trim_window(self, ticker: str) -> tuple[str | None, str | None]   # (keep_from incl., keep_before excl.)
    def signal_cuts(self, ticker: str) -> list[tuple[str, str]]           # [(start, end_excl)]
    def exclusion(self, ticker: str) -> str | None                        # reason, None = admitted
    def manifest_sha256(self, timeframe: str) -> str | None
def integrity_path(root: Path) -> Path
def load_integrity(root: Path) -> Integrity | None
def apply_trim(frame: pd.DataFrame | None, window: tuple[str | None, str | None]) -> pd.DataFrame | None

# _integrity.json (written by V190-15, read by V190-3)
{"schema": 1, "generated_at": iso, "store_start": "2016-01-04", "store_end": "2025-12-31",
 "thresholds": {"max_missing_run": 5, "trailing_sessions": 60, "min_trailing_share": 0.95,
                "break_move": 0.5, "break_ratio": 10.0, "revert_sessions": 20,
                "gap_sessions": 20, "edge_sessions": 20},
 "detector_sha": {"scripts/data/alpaca_history/reuse.py": blob, "scripts/data/alpaca_history/pit_coverage.py": blob},
 "manifest_sha256": {"daily": hex, "hourly": hex, "15min": hex},
 "no_bars": [TICKER, ...],
 "tickers": {TICKER: {
     "admitted": bool, "reason": str | None,
     "identity": status, "identity_manifest": status,          # re-derived vs as fetched
     "reference": {"source": "backtest_cache_ext" | None, "sha256": hex | None},
     "dropped_before": int,
     "first_bar": date | None, "last_bar": date | None,
     "coverage": [{"span": [start, end_excl], "expected": int, "present": int,
                   "missing_runs": [[start, end_excl, sessions]]}],
     "signal_cuts": [[start, end_excl, reason]],
     "trim": {"keep_from": date | None, "keep_before": date | None, "reason": str | None},
     "breaks": [{"date": date, "kind": str, "resolution": "trim_after" | "trim_before" | "in_span" | "unresolved"}]}}}

# swingbot/core/marketdata/training_data.py                      (V190-4)
class StaleIntegrityError(history_store.MissingStoreError)
def select(name: str | None = None, store: str | None = None, until: str | None = None) -> str
def active_store() -> str                    # "watchlist" | "pit"
def selection_args() -> tuple                # ("alpaca",) / ("yfinance",) / ("alpaca", "pit", until)
def signal_cuts() -> dict[str, list[tuple[str, str]]] | None    # None unless the PIT store
def load_intraday(ticker: str, timeframe: str, session: str = "rth") -> pd.DataFrame | None
def _pit_exclusions(manifest: dict, integrity: Integrity, *, store: str) -> dict[str, str]
PIT_ADMITTED = ("ok", "flagged: no-reference")   # literal strings; marketdata never imports scripts/
provenance()  # alpaca branch gains "store"; PIT also "integrity_sha256"

# swingbot/core/marketdata/pit_membership.py                     (V190-5)
def subtract_spans(spans: list[tuple[str, str]], cuts: list[tuple[str, str]]) -> list[tuple[str, str]]
def membership_map(universe, symbols, cuts: dict[str, list[tuple[str, str]]] | None = None) -> dict | None

# scripts/data/fetch_backtest_data.py                            (V190-6)
def instrument_store_spec(args) -> InstrumentSpec | None     # resolved spec when it has a store
def require_context_frames() -> None                         # SystemExit naming every missing symbol
def apply_data_source(args) -> str                           # same signature; PIT branch inside

# swingbot/core/backtesting/instrument/coverage.py               (V190-9)
def store_first_bar(root: Path, symbol: str) -> pd.Timestamp | None
def check_store_coverage(symbols, required_start: str, root: Path) -> CoverageReport

# swingbot/core/analytics/calibration.py                         (V190-10)
_WINDOW_KINDS["2017-01-01..2025-12-31"] == "RESEARCH"
# swingbot/core/backtesting/instrument/stats.py                  (V190-10)
INSTRUMENTS == ("v1", "v2", "screen-v1", "v3"); "DESCRIPTION" in VERDICTS

# scripts/backtest/validate_component.py                         (V190-11)
V3_FUNNEL_REFUSAL: str     # names the follow-up methodology spec that must map Stage 2/3 to five folds

# scripts/data/alpaca_history/aliases.py                         (V190-12)
ALIASES_PATH = Path("data/universe/symbol_aliases.json")   # relative to the project root
@dataclass(frozen=True)
class Alias: member: str; alpaca: str; start: str; end: str | None
def load_aliases(path: Path) -> dict[str, Alias]            # {} when the file is absent
# symbol_aliases.json: {"aliases": [{"member": "FB", "alpaca": "META", "start": "...", "end": null, "note": "..."}]}
# scripts/data/alpaca_history/identity.py                        (V190-12)
def reference_path(ticker, *, backtest_dir: Path, market_dir: Path | None) -> Path | None
def reference_frame(ticker, *, backtest_dir: Path, market_dir: Path | None)   # None = no fallback
# scripts/data/fetch_alpaca_history.py: --universe {sp500_pit}, --aliases PATH; manifest entry "alias"

# scripts/data/alpaca_history/pit_coverage.py                    (V190-13)
STORE_START = "2016-01-04"; STORE_END = "2025-12-31"
MAX_MISSING_RUN = 5; TRAILING_SESSIONS = 60; MIN_TRAILING_SHARE = 0.95
def expected_sessions(spy_daily: pd.DataFrame) -> pd.DatetimeIndex
def clip_span(span: tuple[str, str]) -> tuple[str, str] | None
def missing_runs(bars: pd.DatetimeIndex, sessions: pd.DatetimeIndex, span) -> list[tuple[str, str, int]]
def trailing_failures(bars, sessions, span) -> list[tuple[str, str]]
def coverage_entry(bars, sessions, spans) -> tuple[list[dict], list[tuple[str, str, str]]]   # (coverage, signal_cuts)

# scripts/data/alpaca_history/reuse.py                           (V190-14)
@dataclass(frozen=True)
class Thresholds: break_move=0.50; break_ratio=10.0; revert_sessions=20; gap_sessions=20; edge_sessions=20
THRESHOLDS = Thresholds()
@dataclass(frozen=True)
class Break: date: str; kind: str
def find_breaks(frame, thresholds=THRESHOLDS, *, sessions_from=None) -> list[Break]
def series_gaps(frame, spans, reference_last: str | None, sessions, thresholds=THRESHOLDS) -> list[dict]
def resolve(breaks, spans, frame, thresholds=THRESHOLDS) -> dict     # the "trim" + per-break "resolution"

# scripts/data/check_history_store.py                            (V190-15)
--pit  --backtest-dir PATH  --results-dir PATH
def build_integrity(root, *, intervals, backtest_dir, thresholds, now) -> dict
def write_integrity(root, doc) -> Path
def render_integrity_md(doc) -> str

# scripts/reports/v190_rebaseline_report.py                      (V190-16)
LEG_NAMES = {"A": "v3, PIT S&P 500", "C": "v3, watchlist PIT members", "B": "v1, watchlist"}
STANDING_LINE = "describes an instrument change; never a lift; selects nothing"
def leg_c(trades, watchlist, members) -> list[Trade]
def power_columns(trades, *, seed) -> dict
def build_report(legs, provenance, *, folds, integrity_sha, ...) -> dict
def ledger_row(report, *, date) -> dict          # instrument "v3", verdict "DESCRIPTION", p None
```

## Review Focus

- **A pool worker under v3 silently reading the watchlist store.** `cache_dir_source.pool_kwargs` and the `initializer=training_data.select` sites re-select by name only; V190-4 pins `selection_args()` carrying `("alpaca", "pit", until)` and a worker-side `select(*selection_args())` landing on the PIT root with the same cut.
- **`HISTORY_STORE_DIR` set (it is set on the VM and in tests) redirecting the PIT store.** V190-2 pins that `store_root("pit")` ignores it, and that `store_root()` still honours it.
- **A worktree that has its own `data/market_data` (or none).** V190-2 pins: an existing local directory wins; a missing one in `.claude/worktrees/<x>/` resolves to the main checkout's; outside a worktree nothing changes.
- **A store refreshed after the integrity freeze.** V190-4 pins `StaleIntegrityError` when the daily manifest's sha256 differs from `_integrity.json`, so a `--mode update` between V190-21 and V190-23 cannot slip through.
- **A member trimmed to nothing, or with zero coverage in its span.** V190-3 pins `apply_trim` returning `None` for an empty result and V190-4 pins it excluded with a stated reason (never a crash, never a silent drop); V190-13 pins a zero-coverage span cut whole.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V190-1 | — | first task: creates the worktree; `InstrumentSpec.store` and `_SPECS["v3"]` are read by V190-6..V190-11 |
| V190-2 | V190-5, V190-10, V190-13, V190-14 | after V190-1 (worktree); file `history_store.py` is V190-3's too |
| V190-3 | V190-5, V190-10, V190-13, V190-14 | after V190-2: same file `history_store.py`; uses `store_root("pit")` |
| V190-4 | V190-5, V190-10, V190-13, V190-14 | after V190-3: calls `load(store=)`, `load_integrity`, `Integrity.exclusion` |
| V190-5 | V190-2..V190-4 | after V190-1 (worktree); disjoint file `pit_membership.py`, no contract dependency |
| V190-6 | V190-8, V190-10, V190-11 | after V190-1 (`spec.store`) and V190-4 (`select(..., store, until)`) — contract dependency |
| V190-7 | V190-8, V190-9 | after V190-5 (`membership_map(cuts=)`) and V190-6 (store selection); file `run_backtest_range.py` |
| V190-8 | V190-6, V190-7, V190-9..V190-11 | after V190-1 (`_SPECS["v3"]`); tests only plus two comments in `analytics/override_*.py` |
| V190-9 | V190-7, V190-8, V190-10 | after V190-1 and V190-2 (`store_root("pit")`, store layout) |
| V190-10 | V190-2..V190-9 | after V190-1 (worktree); disjoint files `calibration.py`, `stats.py` |
| V190-11 | V190-6, V190-8, V190-10 | after V190-1 (`VERSIONS` holds `v3`); disjoint file `validate_component.py` |
| V190-12 | V190-13, V190-14 | after V190-1 (worktree); files `fetch_alpaca_history.py`, `identity.py`, new `aliases.py` |
| V190-13 | V190-2..V190-12, V190-14 | after V190-1 (worktree); new file only |
| V190-14 | V190-2..V190-13 | after V190-1 (worktree); new file only |
| V190-15 | V190-16 | after V190-3 (reads its own output back through `load_integrity`), V190-12 (`reference_path`, aliases), V190-13, V190-14 |
| V190-16 | V190-15, V190-17 | after V190-10 (`v3` / `DESCRIPTION` in the ledger vocabulary) |
| V190-17 | V190-16, V190-18 | after V190-2, V190-4, V190-7, V190-15: documents what they built |
| V190-18 | V190-13..V190-17 | after V190-12 (`--universe sp500_pit`) **and** the running backfill exiting; data only, main-checkout root |
| V190-19 | V190-15..V190-17 | after V190-18: one fetcher per root |
| V190-20 | — | after V190-19 (one fetcher per root) and V190-12 (aliases) |
| V190-21 | — | after V190-20 (store complete) and V190-15 (`--pit`) |
| V190-22 | — | after V190-21 (frozen integrity), V190-7 and V190-9 |
| V190-23 | — | after V190-22 (gate green) and V190-8; legs via `backtest-runner`, chunked per strategy |
| V190-24 | — | after V190-23 (trade rows) and V190-16 (report script) |
| V190-25 | — | after every other task: bump, the plan's single full-suite run, merge |

At most 2 implementers at once (shared tree, CPU). Suggested pairs: V190-2 + V190-5, V190-3 + V190-13, V190-4 + V190-14, V190-6 + V190-10, V190-7 + V190-8, V190-9 + V190-11, V190-12 + V190-16, V190-15 + V190-17. Data tasks run one at a time; V190-18 may overlap code tasks because it writes only the main checkout's git-ignored store.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-24-v190-pit-alpaca-universe_1-store-and-selection.md` | V190-1..V190-6 | worktree and instrument v3, two worktree-aware store roots, integrity reader and frame trims, PIT selection in `training_data`, signal-span subtraction, the instrument selecting the store |
| 2 | `2026-10-24-v190-pit-alpaca-universe_2-backtest-wiring.md` | V190-7..V190-11 | `run_backtest_range` v3 path and byte-identity pins, the 17-site branch audit, the v3 coverage gate, calibration label and ledger vocabulary, the funnel's v3 refusal |
| 3 | `2026-10-24-v190-pit-alpaca-universe_3-fetcher-and-integrity.md` | V190-12..V190-15 | fetcher `--universe` and aliases with no identity fallback, causal coverage cuts, the reused-symbol detector, `check_history_store.py --pit` writing `_integrity.json` |
| 4 | `2026-10-24-v190-pit-alpaca-universe_4-rebaseline-data-and-release.md` | V190-16..V190-25 | re-baseline report script, docs and Codex mirror, backfill completion, context pass, aliases, frozen integrity, coverage gate and smoke run, legs A/B/C, results and ledger row, release and full suite |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V190-1 | Worktree, `InstrumentSpec.store`, `_SPECS["v3"]` | 1 | sonnet | M `swingbot/core/backtesting/instrument/contract.py`, `swingbot/core/backtesting/instrument/cli.py` (help text), `tests/backtesting/instrument/test_contract.py`, `tests/backtesting/instrument/test_folds.py`, `tests/backtesting/instrument/test_instrument_cli.py` | worktree branch; `InstrumentSpec.store`, `STORES`, `_V3_WINDOW`, `resolve("v3")`, `VERSIONS == ("v1","v2","v3")` |
| V190-2 | Two store roots, worktree fallback for both | 1 | sonnet | M `swingbot/core/marketdata/history_store.py`, `tests/history_store/test_history_store.py`, `scripts/dev/select_tests.py`, `tests/dev/test_select_tests.py` | `PIT`, `WATCHLIST`, `PIT_DIRNAME`, `resolve_data_root(name)`, `store_root(store=None)`, keyword `store=` on `timeframe_dir`/`file_path`/`manifest_path`/`manifest`/`require_manifest`/`load`; `DATA_READERS` rows for `data/market_data_pit/` and `data/universe/symbol_aliases.json` |
| V190-3 | Integrity reader; frame trims in `history_store.load` | 1 | opus | C `swingbot/core/marketdata/pit_integrity.py`, `tests/history_store/test_pit_integrity.py`; M `swingbot/core/marketdata/history_store.py` | `INTEGRITY_NAME`, `SCHEMA_VERSION`, `Integrity` (`trim_window`, `signal_cuts`, `exclusion`, `manifest_sha256`), `integrity_path`, `load_integrity`, `apply_trim` |
| V190-4 | PIT selection in `training_data`; worker store hand-off | 1 | opus | M `swingbot/core/marketdata/training_data.py`, `scripts/backtest/cache_dir_source.py`, `scripts/backtest/measure_arms.py`, `scripts/backtest/measure_acceptance_exits.py`, `scripts/backtest/measure_fvg_bullish_diagnostic.py`, `tests/history_store/test_training_data.py`; C `tests/history_store/test_training_data_pit.py` | `select(name, store, until)`, `StaleIntegrityError`, `active_store()`, `selection_args()`, `signal_cuts()`, `load_intraday(...)`, `_pit_exclusions(...)`, `PIT_ADMITTED`, provenance keys `store`, `integrity_sha256` |
| V190-5 | Signal-span subtraction in `pit_membership` | 1 | sonnet | M `swingbot/core/marketdata/pit_membership.py`; C `tests/history_store/test_pit_membership_cuts.py` | `subtract_spans(spans, cuts)`, `membership_map(universe, symbols, cuts=None)` |
| V190-6 | The instrument selects the store; context refusal | 1 | opus | M `scripts/data/fetch_backtest_data.py`; C `tests/history_store/test_apply_data_source_instrument.py` | `instrument_store_spec(args)`, `require_context_frames()`, PIT branch of `apply_data_source(args)` |
| V190-7 | `run_backtest_range` v3 path, signal cuts, byte-identity pins | 2 | opus | M `scripts/backtest/run_backtest_range.py` (`_membership_for_run` only); C `tests/backtest_scripts/test_run_backtest_range_v3.py` | — (`_membership_for_run(universe, tickers)` same signature, now applies cuts) |
| V190-8 | Instrument branch audit: v3 takes the v2 path at all 17 sites | 2 | sonnet | C `tests/backtesting/instrument/test_v3_branch_audit.py`; M `swingbot/core/analytics/override_fidelity.py`, `swingbot/core/analytics/override_verdict.py` (comments only) | — |
| V190-9 | v3 coverage gate on the store layout | 2 | sonnet | M `swingbot/core/backtesting/instrument/coverage.py`, `scripts/data/check_cache_coverage.py`, `tests/backtesting/instrument/test_window_coverage.py` | `store_first_bar(root, symbol)`, `check_store_coverage(symbols, required_start, root)` |
| V190-10 | Additive calibration label; ledger `v3` and `DESCRIPTION` | 2 | opus | M `swingbot/core/analytics/calibration.py`, `swingbot/core/backtesting/instrument/stats.py`, `tests/analytics/test_calibration.py`, `tests/backtesting/test_instrument_stats_ledger.py`, `tests/analytics/test_override_verdict.py` (VERDICTS slice) | `_WINDOW_KINDS["2017-01-01..2025-12-31"] = "RESEARCH"`, `"v3"` in `INSTRUMENTS`, `"DESCRIPTION"` in `VERDICTS`, DESCRIPTION-row rule (`p` None required, `exp_r` None allowed) |
| V190-11 | `validate_component --instrument`, refusing v3 | 2 | sonnet | M `scripts/backtest/validate_component.py`, `tests/backtesting/instrument/test_date_literal_guard.py` (drop from `NO_REPLAY`); C `tests/backtest_scripts/test_validate_component_instrument.py` | `V3_FUNNEL_REFUSAL` |
| V190-12 | Fetcher `--universe sp500_pit`, aliases, no identity fallback | 3 | sonnet | M `scripts/data/fetch_alpaca_history.py`, `scripts/data/alpaca_history/identity.py`, `tests/history_store/test_fetch_alpaca_history.py`, `tests/history_store/test_identity.py`; C `scripts/data/alpaca_history/aliases.py`, `tests/history_store/test_aliases.py` | `Alias`, `ALIASES_PATH`, `load_aliases(path)`, `identity.reference_path(...)`, `reference_frame(..., market_dir=None)`, `--universe`, `--aliases`, manifest entry key `alias` |
| V190-13 | Causal coverage cuts | 3 | opus | C `scripts/data/alpaca_history/pit_coverage.py`, `tests/history_store/test_pit_coverage.py` | `STORE_START`, `STORE_END`, `MAX_MISSING_RUN`, `TRAILING_SESSIONS`, `MIN_TRAILING_SHARE`, `expected_sessions`, `clip_span`, `missing_runs`, `trailing_failures`, `coverage_entry` |
| V190-14 | Reused-symbol detector and kept side | 3 | opus | C `scripts/data/alpaca_history/reuse.py`, `tests/history_store/test_reuse.py` | `Thresholds`, `THRESHOLDS`, `Break`, `find_breaks`, `series_gaps`, `resolve` |
| V190-15 | `check_history_store.py --pit`: `_integrity.json` and summary | 3 | sonnet | M `scripts/data/check_history_store.py`; C `tests/history_store/test_check_history_store_pit.py` | `--pit`, `--backtest-dir`, `--results-dir`, `build_integrity(...)`, `write_integrity(root, doc)`, `render_integrity_md(doc)` |
| V190-16 | v190 re-baseline report script | 4 | opus | C `scripts/reports/v190_rebaseline_report.py`, `tests/history_store/test_v190_rebaseline.py` | `LEG_NAMES`, `STANDING_LINE`, `leg_c`, `power_columns`, `build_report`, `ledger_row`, CLI `--leg A=... --leg B=... --watchlist ... --integrity ... --json ... --md ...` |
| V190-17 | Docs: methodology § Windows v3, known-traps, architecture, AGENTS.md | 4 | haiku | M `docs/claude/backtest-methodology.md`, `docs/claude/known-traps.md`, `docs/claude/architecture.md`, `AGENTS.md` | — |
| V190-18 | Wait for the member backfill; verify and complete it | 4 | sonnet | data only (main-checkout `data/market_data_pit/`); C `docs/superpowers/results/2026-10-v190-pit-backfill-log.md` | complete member manifests for daily, hourly, 15min |
| V190-19 | Context pass: SPY, regime ticker, `etfs.json`, all timeframes | 4 | haiku | data only; M `docs/superpowers/results/2026-10-v190-pit-backfill-log.md` | context symbols in all three PIT manifests |
| V190-20 | Rename aliases: map `no-bars` members, fetch them | 4 | sonnet | C `data/universe/symbol_aliases.json`; M `docs/superpowers/results/2026-10-v190-pit-backfill-log.md` | committed alias table; aliased members in the PIT store |
| V190-21 | Calibrate and freeze the integrity report | 4 | opus | M `scripts/data/alpaca_history/reuse.py` (frozen thresholds, only if calibration moves them), `scripts/data/alpaca_history/pit_coverage.py` (same rule); C `docs/superpowers/results/2026-10-v190-pit-integrity.md` | main-checkout `data/market_data_pit/_integrity.json` (frozen) |
| V190-22 | v3 coverage gate and smoke run on the real store | 4 | sonnet | M `docs/superpowers/results/2026-10-v190-pit-integrity.md` (gate and smoke section) | — |
| V190-23 | Re-baseline legs A and B via `backtest-runner` | 4 | sonnet | data only: `data/backtest_results/v190/leg-<A|B>-<slug>.jsonl` (+ `.provenance.json`) | trade-row files for every live strategy (no confluence: `--scenarios` refused under v3) |
| V190-24 | Re-baseline results doc and ledger DESCRIPTION row | 4 | sonnet | C `docs/superpowers/results/2026-10-v190-v3-rebaseline.md`, `docs/superpowers/results/2026-10-v190-v3-rebaseline.json`; M `docs/superpowers/results/preregistration-ledger.jsonl` | the recorded description |
| V190-25 | Version bump, full suite, merge | 4 | sonnet | M `VERSION.json`, `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`) | merged branch on `main`; `/close-out` follows |
