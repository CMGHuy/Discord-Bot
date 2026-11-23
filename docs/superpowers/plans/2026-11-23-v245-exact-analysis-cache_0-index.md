# v245 — Exact analysis caching: make the live scan cheap per ticker — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-8" -A 400 <part file>`); never read a part whole.

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Brief:** `.superpowers/briefs/2026-11-23-v245-exact-analysis-cache.md` (code context, line numbers as of eec00b44; gitignored)
**Gates:** V245-6 is a **stop gate** (exit criterion). V245-15 waits **5 trading days** of shadow with zero diffs. V245-17 waits **10 trading days** of `on` with no incident.

## Goal

The live scan no longer fits its own interval. On production (92 tickers,
`SCAN_WORKERS=1`, the bot capped at one CPU) a scan takes 385 s at the median
against a 300 s `SCAN_INTERVAL_MINUTES`, and 76 % of that is the analysis
phase: about 3.2 s per ticker. Most of that time re-derives the same answer
from the same input. Every five minutes `_scan_one` re-detects years of
confirmed pivots and re-runs the O(pivots³) trendline pair search over them,
although only the last bar and the live price have changed. A cheaper
analysis phase is one of the two preconditions for a larger watchlist (the
other, the fetch path, is a separate spec).

This plan works in up to three phases and stops as early as the numbers
allow. **Phase A** pins today's output with golden characterisation tests,
profiles one scan's frames to find where the time goes, tags each hot spot
with whether it reads the last row or the live price, and ships only
byte-identical fixes (work done twice for the same input, done once). It then
measures analysis time per ticker on production. **If the p50 is at or under
0.7 s per ticker, the plan ends there** and the spec closes with its results.
Only if Phase A misses does **Phase B** build an exact prefix cache: anything
that is a pure function of `df.iloc[:m]` (the frame minus its last `W` rows)
is cached per ticker under a fingerprint of that prefix, and everything that
reads the tail or the price is recomputed every scan, exactly as today. The
trendline pair search is the main unit: pair geometry and touches against
confirmed pivots are cached; tail pivots, recency, both price gates and the
pick stay per scan. **Phase C** proves the cache changes nothing on
production: a `shadow` mode reruns a rotating third of the watchlist uncached
and compares the results field by field, for five trading days with zero
diffs, before the switch goes to `on`.

What it leaves alone: no strategy, filter, exit, threshold or alert changes;
every alert is byte-identical to today's at all times, during market hours or
not. Outlook and replay call `_scan_one` with no cache. The watchlist size,
the fetch path, container limits and logging are later sub-projects.

Success is measured on production, never on the laptop: analysis p50 per
ticker (`phases_s.analysis / tickers` in `scan_telemetry.jsonl`) ≤ 0.7 s, with
the characterisation goldens byte-identical through every commit, zero shadow
diffs over five trading days (Phase C), and `rss_mb` showing the cache's
memory cost.

## Architecture

- **Characterisation first (V245-1).** A golden helper module
  (`tests/scanning/v245_golden_cases.py`) runs `_scan_one` over fixture frames
  with a hermetic `ScanIO` and a frozen clock, projects the stats to an exact
  JSON snapshot (floats as `float.hex`), and compares it to a committed
  golden. Every later task that touches analysis must keep it byte-identical;
  later tests (property, wiring, shadow) reuse `run_case` and `snapshot`.
- **Profile and tag (V245-2, V245-3).** `scripts/perf/profile_analysis.py`
  replays the 92 production tickers' local frames through `_scan_one` under
  `cProfile` and `tracemalloc`, with and without a synthesised forming bar,
  and reports each candidate's share and the bytes of each candidate
  cacheable object. The results doc ranks byte-identical fixes (`F1..Fn`) and
  prefix-pure units (`U1..Un`) with their tags.
- **Byte-identical fixes (V245-4, V245-5).** Two fix slots, each taking the
  next fix from the doc's ranked list, one commit per fix. Each slot carries a
  prepared design for a hot spot the code already shows (zigzag computed
  twice per frame for the two trendline sides; indicators recomputed per
  horizon over the same frame).
- **Measure and decide (V245-6).** `scripts/perf/analysis_phase_report.py`
  summarises production telemetry; the verdict goes into the spec's
  `## Results`. Met: stop and close out. Missed: Phase B.
- **Cache core (V245-7).** `swingbot/core/scanning/structure.py`:
  `StructureCache`, a lock-guarded bounded LRU keyed
  `(ticker, unit, prefix_fingerprint)`, cleared on every config-changing
  SIGHUP and resized when `STRUCTURE_CACHE_MAX` changes, through
  `bot_core.on_config_reload`. Config: `ANALYSIS_CACHE` (`off|shadow|on`,
  default `off`) and `STRUCTURE_CACHE_MAX` (default 600, lowered by the V245-3
  bytes figure if 600 entries would exceed 150 MB).
- **Trendline prefix split (V245-8).** `trendlines.py` gains a frozen
  `TrendlinePrefix` (confirmed pivots plus, per `i<j` pair, geometry and
  touches against confirmed pivots) built from `trimmed.iloc[:m]`.
  `_find_best_trendline` always runs through prefix + tail (one code path); it
  verifies on every scan that the full frame's pivots start with the prefix's
  confirmed pivots, and falls back to an empty prefix (today's algorithm)
  when they do not.
- **Wiring (V245-9).** `_scan_one` gains `structure` and `now`; the two live
  call sites pass the cache (base lane `scan_run.py:754`; SHORT lane through
  `ExtraScanContext.structure` into `analyze.py:1375`). `ScanItem` carries
  `prefix_results` so `rescenario` never looks the cache up later.
- **Proof and extras (V245-10, V245-11, V245-12).** Prefix property test over
  truncations; further prefix-pure units the profile found (or none);
  telemetry (`cache_*`, `phases_s.analysis_prefix`, `rss_mb`).
- **Shadow (V245-13, V245-14).** `swingbot/core/scanning/cache_shadow.py`:
  rotating-third sampling, a side-effect-free comparison `ScanIO`, a
  thread-scoped log-demotion filter, a field-by-field comparator and a
  20 MB × 3 rotating jsonl. Wired into the base lane only.
- **Rollout (V245-15..17).** Deploy `off` → `shadow` soak (5 trading days, zero
  diffs) → `on`, measure, record; then remove the shadow scaffolding.

## Decisions this index fixes (spec silent; controller may override)

1. **Golden clock.** `_scan_one` has no `now` until V245-9. V245-1 freezes the
   clock by monkeypatching the `datetime` reference that
   `analyze._apply_pullback_dryup` and `analyze._band_live` read (the
   implementer confirms the attribute with
   `git grep -n "datetime.now" swingbot/core/scanning/analyze.py`).
   `GOLDEN_NOW = 2024-03-15 19:00 UTC` (15:00 New York, intraday). A
   "forming bar" frame's last row is dated 2024-03-15; a "completed" frame
   ends 2024-03-14. From V245-9 on, `run_case` also passes `now=GOLDEN_NOW`
   explicitly; both must give the same golden.
2. **Golden floats.** Stored as `float.hex()` strings. If CI (Linux) disagrees
   with a golden generated on Windows on *unchanged* code, the V245-1
   implementer regenerates the golden under WSL or from CI's output and says
   so in the commit message; goldens are never loosened to a rounding
   tolerance.
3. **`now` captured once per scan, base lane only.** `scan_run` captures
   `scan_now = datetime.now(timezone.utc)` once at the start of the analysis
   phase and passes it to every `_scan_one` (spec § Knob and shadow check).
   `scan_extra_candidate` keeps passing no `now`: its `ExtraScanContext.now`
   is the replay date in `scan_replay.py:346`, and passing it would change
   replay output. The shadow comparison runs only in the base lane, so the
   SHORT lane needs none.
4. **Trendline prefix window.** `TRENDLINE_PREFIX_TAIL_BARS = 1` (the prefix is
   the trimmed frame minus its last row, constant across the intraday scans
   of one session day) and `UNSTABLE_PREFIX_PIVOTS = 2` (the last two pivots
   of a kind found on the prefix are left to the tail, because zigzag's last
   pivots are unconfirmed extremes). Correctness never rests on these two
   constants: every scan verifies that the full frame's pivot list starts
   with the prefix's confirmed pivots, element for element, and on a mismatch
   computes with an empty prefix (today's algorithm, same code path).
5. **Fingerprint.** `prefix_fingerprint(frame, m)` =
   `(m, str(frame.index[0]), float(frame["Close"].iloc[0]),
   str(frame.index[m - 1]), O, H, L, C, V of row m - 1)`. The first row's date
   covers the 1500-bar trim start without a separate field. `m == 0` gives
   `(0,)`.
6. **SIGHUP hook location.** The `on_config_reload` callback lives in
   `swingbot/commands/scanning/loops.py` next to
   `_apply_scan_interval_change` (core never imports `bot_core`); it calls
   `structure.apply_config_change(changed)`.
7. **Log quieting is thread-scoped.** A `logging.Filter` on the scan loggers
   demotes records emitted by the comparison run's thread to DEBUG, so a
   future `SCAN_WORKERS > 1` does not quiet other tickers' lines.
8. **Shadow sampling.** `zlib.crc32(ticker.encode()) % 3 == scan_seq % 3`,
   with `scan_seq` a process-local counter bumped once per base-lane scan in
   `shadow`: each ticker is compared every third scan.
9. **Deploys.** Phase A merges to `main` before V245-6's deploy; Phase B
   before V245-15's. A deploy follows `docs/deploy/DEPLOY_HETZNER.md`; any
   `.env` change on the VM runs `mirror-prod`. The `VERSION.json` bot patch
   bump is done at close-out unless the deploy procedure demands it earlier,
   in which case the controller bumps at the first deploy and close-out does
   not bump again.
10. **Shadow removal leaves `off|on`.** After V245-17,
    `_MODE_VALUES["ANALYSIS_CACHE"] = ("off", "on")`; a stale `shadow` value
    falls back to `off` (same output, slower) with the existing warning.

## Global Constraints

- **Every alert byte-identical.** The V245-1 golden must pass unchanged after
  every task from V245-2 on. A task that needs to regenerate it has found a
  behaviour change: stop and report, never regenerate.
- **No-lookahead:** anything reading the last row, the forming bar, `now` or
  `current_price` is recomputed every scan. `_apply_pullback_dryup`,
  `_band_live`, `_trendln_fallback_levels`, floor pivots (`levels.py:320`),
  rolling S/R, Donchian, EMA/ATR/VWAP/Bollinger series, `get_htf_bias`,
  `horizon_trend`, `_cluster_levels`, scenarios, confluence, confidence and
  requirements are never cached (spec § Exact prefix caching table).
- **Cache rule:** a cached value is a pure function of `frame.iloc[:m]` under
  its `prefix_fingerprint`; a horizon-specific unit names the horizon; a
  horizon missing from an entry is a miss; cached objects are frozen (tuples;
  `Level.sources` copied to a tuple if a `Level` is ever cached).
- **One code path:** refactored functions take an optional prefix result and
  build it themselves when given none. No second analysis body.
- **Cache-free callers:** `outlook_run.py:114`, `scan_replay.py:299` and
  `scan_replay.py:346` call `_scan_one` / `scan_extra_candidate` with no cache,
  unchanged.
- **Config:** `ANALYSIS_CACHE` `off|shadow|on`, default `off`, hot-reloaded;
  `STRUCTURE_CACHE_MAX` default 600 (or the V245-3 figure), hot-reloaded;
  every config-changing SIGHUP clears the whole cache.
- **Failure handling:** a prefix build failure logs WARNING with the ticker,
  stores nothing, and that ticker computes uncached this scan; a comparator
  failure is logged through `swallowed` and never touches posting.
- **Shadow output:** `cache_compared` and `cache_diffs` per scan in
  `scan_telemetry`; one JSON line per diff in
  `logs/analysis_cache_shadow.jsonl`, `RotatingFileHandler` 20 MB × 3.
- **Telemetry:** `phases_s.analysis_prefix`, `cache_hits`, `cache_misses`,
  `cache_evictions`, `cache_entries`, `rss_mb` (from `/proc/self/status`
  `VmRSS`, `None` where unavailable); hit and miss counts in the INFO scan
  summary line.
- **Complexity < 15** for every new or changed function; `_scan_one` (35),
  `collect_candidate_levels` (42) and `_sync_run_scan` (94) must not grow:
  new code goes into helpers. `_find_best_trendline` and
  `_volume_confirmed_pivots` are at 15; touching them leaves them < 15
  (`python scripts/dev/complexity_gate.py`).
- **Tests:** existing suites only (`scanning` for `tests/scanning/`,
  `market-signals` for `tests/market/`, `tooling` for `tests/scripts/`); no new
  `tests/` directory. Per-task runs are
  `python scripts/dev/testrun.py file <test>`; no task runs the full suite
  (CI does).
- **Production numbers** come only from read-only access through
  `bash scripts/ops/ssh-hetzner.sh`; the laptop gives shares, never the 0.7 s
  verdict.
- **Implementers never edit plan files;** each task commits its own code in
  scoped commits.

## Parallelisation

Default is sequential in id order. Safe pairs (disjoint files, no contract
dependency), at most two implementers at once:

- **V245-1 ∥ V245-2.** Golden tests (`tests/scanning/`, `tests/fixtures/`) and
  the profiler (`scripts/perf/`, `tests/scripts/`) share no file; the
  profiler does not import the golden helper.
- **V245-7 ∥ V245-8.** Cache core (`structure.py`, `config.py`, `loops.py`,
  `.env.example`) and the trendline split (`trendlines.py`,
  `tests/market/test_trendline_split.py`) share no file; the split does not
  use the cache.
- **V245-10 ∥ V245-12.** The property test only adds a test file; telemetry
  edits `scan_run.py` and `structure.py`. Neither consumes the other.
- **V245-12 ∥ V245-13.** Telemetry and the new `cache_shadow.py` share no file;
  V245-13 consumes only V245-1's helper and `analyze.ScanIO`.

Sequential edges and why:
- V245-1 → V245-3 onward: every behaviour-preserving change is gated by the
  golden.
- V245-2 → V245-3 → V245-4 → V245-5: the doc's ranking picks what each slot
  fixes; V245-5 takes the fixes after V245-4's.
- V245-5 → V245-6: production measures the shipped fixes. **V245-6 is a stop
  gate**: if the exit criterion is met, V245-7..17 are not executed.
- V245-8 → V245-9: wiring calls `custom_scanner_levels(..., prefixes=)`.
- V245-7 → V245-9: wiring needs `StructureCache` and `prefix_fingerprint`.
- V245-9 → V245-10, V245-11, V245-12, V245-14: all need `_scan_one(structure=,
  now=)` and `ScanItem.prefix_results`.
- V245-11 → V245-14: the shadow must compare the final set of cached units.
- V245-13 → V245-14: the wiring imports `cache_shadow`.
- V245-14 → V245-15 → V245-16 → V245-17: rollout order, with the soak and the
  10-day wait between them.

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify, D delete) | Symbols for later tasks |
|---|---|---|---|---|---|
| V245-1 | Characterisation goldens for `_scan_one` | 1 | sonnet | C `tests/scanning/v245_golden_cases.py`, C `tests/scanning/test_v245_scan_one_golden.py`, C `tests/fixtures/scanning/v245_scan_one_golden.json` | `GOLDEN_NOW: datetime` (2024-03-15 19:00 UTC); `HERMETIC_IO: analyze.ScanIO`; `@dataclass(frozen=True) GoldenCase(name: str, frame: Callable[[], DataFrame \| None], horizons: tuple[str, ...], allowed_directions: object, mtf_adjacent_gate: bool, live_price: Callable[[DataFrame], float \| None])`; `CASES: tuple[GoldenCase, ...]`; `frozen_clock(monkeypatch, now=GOLDEN_NOW) -> None`; `run_case(case: GoldenCase, *, structure=None) -> dict` (calls `_scan_one`, returns `snapshot(stats)`); `snapshot(stats: dict) -> dict` (JSON-able, floats `float.hex`); `GOLDEN_PATH: Path`; regen env var `V245_REGEN_GOLDEN=1` |
| V245-2 | Analysis profiler `scripts/perf/profile_analysis.py` | 1 | sonnet | C `scripts/perf/__init__.py`, C `scripts/perf/profile_analysis.py`, C `tests/scripts/test_profile_analysis.py` | `CANDIDATES: tuple[tuple[str, str], ...]` (label, `module:function`); `synth_forming_bar(df: DataFrame, atr_mult: float = 0.5) -> DataFrame`; `load_frames(tickers: list[str]) -> dict[str, DataFrame]`; `profile_scan(frames: dict, horizons: list[str], *, forming: bool) -> tuple[pstats.Stats, float]`; `candidate_shares(stats, total_s: float) -> list[dict]` (`label, cum_s, share, calls`); `object_bytes(obj) -> int` (pickled size); `main(argv=None) -> int` (writes `logs/v245-profile/profile.json`) |
| V245-3 | Profile run, tags and results doc | 1 | opus | C `docs/superpowers/results/2026-11-23-v245-analysis-profile.md` | Doc sections `## Shares`, `## Tags` (per candidate: reads last row y/n, reads `current_price` y/n, prefix-pure y/n), `## Bytes per object`, `## Byte-identical fixes` (ranked `F1..Fn`), `## Prefix-pure units` (ranked `U1..Un`, `U1` = trendline pair search), `## Cache size` (recommended `STRUCTURE_CACHE_MAX`) |
| V245-4 | Hot-spot fix slot 1 (doc `F1`; prepared: one zigzag per trimmed frame for both trendline sides) | 2 | opus | per doc `F1`; prepared design: M `swingbot/core/market/trendlines.py`, C `tests/market/test_trendline_shared_pivots.py` | prepared design: `trendlines._volume_confirmed_pivots(df, kind, all_pivots: list \| None = None) -> list` (same result); no new cross-task contract |
| V245-5 | Hot-spot fix slot 2 (doc `F2..`; prepared: per-ticker indicator memo across horizons) | 2 | opus | per doc `F2..`; prepared design: C `swingbot/core/market/frame_memo.py`, M `swingbot/core/market/levels.py`, M `swingbot/core/scanning/analyze.py`, C `tests/market/test_frame_memo.py` | prepared design: `frame_memo.ticker_memo() -> ContextManager[None]`; `frame_memo.memo(df, key: tuple, fn: Callable[[], T]) -> T` (computes directly when no memo is active) |
| V245-6 | Production measurement and exit decision (**stop gate**) | 2 | sonnet | C `scripts/perf/analysis_phase_report.py`, C `tests/scripts/test_analysis_phase_report.py`, M `docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md` (`## Results`) | `per_ticker_seconds(row: dict) -> float \| None`; `summarise(rows: list[dict], since: str \| None = None) -> dict` (`scans, p50, p90, prefix_p50, cache_hit_rate, rss_mb_max`); `main(argv=None) -> int` (`--since ISO`, `--path`) |
| V245-7 | `StructureCache`, config fields and SIGHUP clear/resize | 3 | sonnet | C `swingbot/core/scanning/structure.py`, M `swingbot/config.py`, M `swingbot/commands/scanning/loops.py`, M `.env.example`, C `tests/scanning/test_structure_cache.py` | `class StructureCache(max_entries: int = 600)`: `get(key) -> object \| None`, `put(key, value) -> None`, `get_or_build(key: tuple, build: Callable[[], object], *, ticker: str = "") -> object \| None` (build error: WARNING, nothing stored, returns `None`; build time added to `prefix_build_s`), `clear()`, `resize(max_entries: int)`, `stats() -> dict` (`cache_hits, cache_misses, cache_evictions, cache_entries`), `prefix_build_s: float`, `reset_counters()`; `STRUCTURE_CACHE: StructureCache`; `prefix_fingerprint(frame: DataFrame, m: int) -> tuple`; `analysis_cache_mode() -> str`; `cache_for_mode(mode: str) -> StructureCache \| None` (`off` -> None); `apply_config_change(changed: dict) -> None`; config attrs `ANALYSIS_CACHE: str`, `STRUCTURE_CACHE_MAX: int`; `loops._apply_structure_cache_change(changed: dict)` |
| V245-8 | Trendline prefix split | 3 | opus | M `swingbot/core/market/trendlines.py`, C `tests/market/test_trendline_split.py` | `TRENDLINE_PREFIX_TAIL_BARS = 1`; `UNSTABLE_PREFIX_PIVOTS = 2`; `@dataclass(frozen=True) TrendlinePrefix(side: str, m: int, confirmed: tuple, pairs: tuple)` (`pairs[i][j - i - 1]` = `None` or `(slope, intercept, touches: tuple)` over `confirmed`); `trimmed_frame(df) -> tuple[DataFrame, int]` (`(frame, trim_start)`); `prefix_length(trimmed: DataFrame) -> int`; `build_trendline_prefix(trimmed: DataFrame, side: str, m: int) -> TrendlinePrefix`; `_find_best_trendline(df, current_price: float, side: str, prefix: TrendlinePrefix \| None = None) -> dict \| None`; `custom_scanner_levels(df, current_price: float, prefixes: dict[str, TrendlinePrefix] \| None = None) -> list` |
| V245-9 | Wire the cache and `now` into the two live call sites; `ScanItem.prefix_results`; `rescenario` | 3 | opus | M `swingbot/core/scanning/analyze.py`, M `swingbot/core/scanning/scan_run.py`, M `swingbot/core/scanning/short_run.py`, M `swingbot/core/scanning/structure.py`, M `tests/scanning/v245_golden_cases.py`, C `tests/scanning/test_analysis_cache_wiring.py` | `_scan_one(..., io=None, structure: StructureCache \| None = None, now=None)`; `ScanItem.prefix_results: dict \| None = None`; `_horizon_scenarios(..., now=None, prefix_results: dict \| None = None)`; `ExtraScanContext.structure: object = None`; `structure.TRENDLINE_UNITS = {"support": "trendline:support", "resistance": "trendline:resistance"}`; `@dataclass(frozen=True) PrefixUnit(name: str, build: Callable[[DataFrame], tuple[tuple, Callable[[], object]]])` (returns `(fingerprint, builder)`); `structure.PREFIX_UNITS: tuple[PrefixUnit, ...]`; `structure.ticker_prefixes(cache: StructureCache \| None, ticker: str, df) -> dict \| None` (unit name -> value; `None` when cache is None); `scan_run._analysis_cache() -> tuple[str, StructureCache \| None]` (read once per scan) |
| V245-10 | Prefix property test and immutability | 4 | sonnet | C `tests/scanning/test_analysis_cache_property.py` | none |
| V245-11 | Further prefix-pure units from the profile (doc `U2..`; none -> recorded no-op) | 4 | opus | per doc `U2..`: M `swingbot/core/scanning/structure.py`, M the unit's module under `swingbot/core/market/`, M `docs/superpowers/results/2026-11-23-v245-analysis-profile.md`, C `tests/market/test_prefix_units.py` | appends to `structure.PREFIX_UNITS`; consumers read `prefix_results.get(<unit name>)` with a `None` fallback that computes the unit directly |
| V245-12 | Cache telemetry: `cache_*`, `phases_s.analysis_prefix`, `rss_mb`, summary line | 4 | sonnet | M `swingbot/core/scanning/scan_run.py`, M `swingbot/core/scanning/structure.py`, C `tests/scanning/test_analysis_cache_telemetry.py` | `structure.rss_mb(status_path: str = "/proc/self/status") -> float \| None`; `scan_run._cache_telemetry(mode: str, cache: StructureCache \| None) -> dict` (`cache_mode, cache_hits, cache_misses, cache_evictions, cache_entries, rss_mb`) |
| V245-13 | Shadow comparator module | 5 | sonnet | C `swingbot/core/scanning/cache_shadow.py`, C `tests/scanning/test_cache_shadow.py` | `SAMPLE_EVERY = 3`; `SHADOW_LOG_PATH = "logs/analysis_cache_shadow.jsonl"`; `SCAN_LOGGERS: tuple[str, ...]`; `next_scan_seq() -> int`; `in_sample(ticker: str, scan_seq: int) -> bool`; `recording_io(base: ScanIO) -> tuple[ScanIO, dict]`; `comparison_io(answers: dict) -> ScanIO`; `demoted_logs(names: tuple[str, ...] = SCAN_LOGGERS) -> ContextManager[None]`; `compare_stats(ticker: str, cached: dict, uncached: dict) -> list[dict]` (`ticker, horizon, direction, field, cached, uncached`); `write_diffs(diffs: list[dict], path: str = SHADOW_LOG_PATH) -> None` |
| V245-14 | Wire shadow into the base-lane scan | 5 | opus | M `swingbot/core/scanning/scan_run.py`, C `tests/scanning/test_cache_shadow_wiring.py`, M `tests/market/test_swallowed_tags_oh14.py` (only if it pins the tag list) | `@dataclass _AnalysisCtx(mode: str, cache, scan_now, scan_seq: int, compared: int = 0, diffs: int = 0)`; `scan_run._scan_ticker(ticker: str, df, scan_kwargs: dict, ctx: _AnalysisCtx) -> dict`; telemetry keys `cache_compared`, `cache_diffs`; swallowed tag `analysis_cache_shadow` |
| V245-15 | Deploy `off`, then `shadow`; soak report | 6 | sonnet | C `scripts/perf/analysis_cache_soak_report.py`, C `tests/scripts/test_analysis_cache_soak_report.py` | `soak_days(rows: list[dict]) -> list[dict]` (per New York date: `date, scans, compared, diffs`); `verdict(days: list[dict], need: int = 5) -> str` (`PASS`/`WAIT`/`FAIL`); `main(argv=None) -> int` |
| V245-16 | Switch `on`, measure, record `## Results`, align docs | 6 | sonnet | M `docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md`, M `docs/claude/known-traps.md`, M `docs/deploy/DEPLOY_HETZNER.md` | none |
| V245-17 | Remove the shadow scaffolding (after 10 trading days of `on`) | 6 | sonnet | D `swingbot/core/scanning/cache_shadow.py`, D `tests/scanning/test_cache_shadow.py`, D `tests/scanning/test_cache_shadow_wiring.py`, M `swingbot/core/scanning/scan_run.py`, M `swingbot/config.py`, M `.env.example`, M `tests/scanning/test_structure_cache.py` | `_MODE_VALUES["ANALYSIS_CACHE"] = ("off", "on")` |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-23-v245-exact-analysis-cache_1-golden-and-profile.md` | V245-1, V245-2, V245-3 | characterisation goldens, profiler, results doc with tags |
| 2 | `2026-11-23-v245-exact-analysis-cache_2-fixes-and-exit.md` | V245-4, V245-5, V245-6 | byte-identical fix slots, production measurement, exit gate |
| 3 | `2026-11-23-v245-exact-analysis-cache_3-cache-core.md` | V245-7, V245-8, V245-9 | `StructureCache` and config, trendline prefix split, live wiring |
| 4 | `2026-11-23-v245-exact-analysis-cache_4-proof-and-telemetry.md` | V245-10, V245-11, V245-12 | property test, further units, telemetry |
| 5 | `2026-11-23-v245-exact-analysis-cache_5-shadow.md` | V245-13, V245-14 | shadow comparator and its wiring |
| 6 | `2026-11-23-v245-exact-analysis-cache_6-rollout.md` | V245-15, V245-16, V245-17 | deploy and soak, switch on and record, scaffolding removal |

## What follows

- If V245-6 meets the exit criterion: `/close-out` right after it (Phases B
  and C not executed; the spec's `## Results` says so).
- If Phase B ships and `on` still misses 0.7 s: the spec's § Deferred
  alternative (frozen completed-bar structure) returns to the partner as its
  own decision; a process pool is revisited only then.
- Watchlist growth needs sub-project B (fetch path) first; not this plan.
