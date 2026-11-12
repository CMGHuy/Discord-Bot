# v226 — Stop-width attribution: does a stop tight in ATR terms cost expectancy? (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v226 — Stop-width attribution: does a stop that is tight in ATR terms cost expectancy?](../specs/2026-11-12-v226-stop-width-attribution-design.md) (all sections; § Panel review findings are applied in the spec and not reopened here)

## Goal

Production showed many losing trades on 2026-11-12. A read-only look at the
live book found no defect, but it did find that every plan since 2026-10-01
carries a stop 1.75–2.00% from the signal close, on a watchlist whose ATR14
sits near 5% of price. The obvious remedies (a wider structural stop, ATR-band
stops, a regime gate, a re-entry cooldown) are already measured and closed.
What has never been measured is whether the plans whose stop is very tight
*relative to the ticker's own volatility* form a population that loses. If
they do, the remedy would be to skip those setups, a veto idea, rather than to
widen the stop again.

Once this plan ships, the v146 attribution script gains a `--study
stop-width` flag. It reads a fresh TRAIN confluence replay
(2020-01-06..2023-12-29 signal dates, today's live stop settings) and the
live book, buckets every row by `entry_context["stop_atr"]` (stop distance
from the signal close in ATR14 units) on quartile edges frozen from TRAIN
alone, compares each bucket with the rest through the existing week-clustered
bootstrap, and applies a six-clause pre-registered rule computed once. It
writes `data/reports/stop-width-attribution.json` and prints the Markdown that
becomes the results doc. The verdict is one of `VETO-CANDIDATE` (licenses a
Stage −2 avoid screen, never a veto), `NO CANDIDATE` (closes the question as
measured) or `UNDERPOWERED` (leaves it open and names the N that would power
it). The live book is printed beside TRAIN and never gates.

Two pieces of replay plumbing make the run trustworthy. The TRAIN replay
today holds every row in memory and writes the `--trades-jsonl` file once at
the end; it gains per-ticker persistence with skip-on-restart, so an
interruption costs one ticker, not the run, and the printed table after a
restart is rebuilt from the persisted rows and equals an uninterrupted run.
It also gains a run sidecar (`<path>.run.json`: git HEAD, window, watchlist,
membership as-of, command line, the three stop settings) beside the existing
store provenance sidecar, so the results doc can quote exactly what ran.

It leaves alone: every stop, the v115 clamp, `MIN_STOP_DISTANCE_PCT`, sizing,
alerts, admission and the TRAIN row contract (`scenario_rows.ROW_KEYS`,
`expectancy_attribution.ROW_KEYS`, `live_row`, `_train_row`). The default
attribution report stays byte-identical and the v146 verdict of record is
never recomputed. Nothing the bot posts, trades or shows changes, hence
`Bump: none`.

Success is measured by the tests each task adds (outcome-blind edges, edge
and unknown handling, every verdict clause boundary, the study's own BH
family size, the removal arithmetic, the restart-equals-uninterrupted test,
the `stop_atr` truncation test, the byte-identical default-report pin), by a
TRAIN replay that completes with both sidecars, and by a committed results
doc that states the verdict, records it in the pre-registration ledger and,
for `NO CANDIDATE`, in `backtest-methodology.md` § Closed pre-registrations.

## Architecture

- **Replay hook (`swingbot/core/backtesting/backtest_scenarios.py`):**
  `run_scenario_backtest` gains a keyword `on_ticker_result=None`, called
  `on_ticker_result(ticker, exits, rows)` in task order as each ticker's
  result arrives, only when `collect_rows=True`. `_drain` gains an
  `on_result(index, result)` parameter; `on_ticker_done(done, total)` keeps
  its signature. Stats are unchanged.
- **Checkpointing and sidecar (`scripts/backtest/run_backtest_range.py`):**
  with `--trades-jsonl <path>` the script writes `<path>.run.json` at start,
  appends each finished ticker's rows to `<path>` and a line to
  `<path>.done.jsonl`, and on restart (done file present, sidecar equal)
  truncates `<path>` to rows of done tickers and replays only the rest. The
  as-of map is always built on the **full** frame set (it is
  cross-sectional: `rs_pctile` ranks across tickers), then the remaining
  frames are replayed with it. `pooled`/`by_horizon` are rebuilt from the
  persisted rows plus the done file's `not_triggered` counts through
  `backtest_scenarios._aggregate`. All new logic lives in new helpers;
  `run_scenario_mode` (C 19) and `main` (F 62) do not grow.
- **Study (`swingbot/core/analytics/expectancy_attribution.py`):** new
  functions only, appended after `run`: rows (`stop_width_row`, two loaders),
  edges (`frozen_edges`, `edge_labels`, `edge_label`, `stop_width_groups`),
  verdict (`stop_width_verdict`, its own BH family via
  `stats.bh_qvalues`, never `assign_qvalues`), disclosures
  (`stop_width_disclosures`), report (`build_stop_width_report`,
  `run_stop_width`, `stop_width_markdown`). Writes through
  `jsonio.atomic_write_json`, never `write_latest` (that one carries v146's
  `verdict_of_record`).
- **Script (`scripts/reports/expectancy_attribution.py`):** `--study
  stop-width` routes to `run_stop_width` and prints `stop_width_markdown`;
  without the flag the call to `study.run(train_jsonl, seed=, write=)` and
  the printed summary are unchanged.

**Tech stack:** Python 3.11, numpy, pytest, the existing week-cluster
bootstrap and BH helpers (`swingbot/core/backtesting/instrument/stats.py`),
`backtest-runner` for the replay, `/replicate-prod-db` for the live rows.

## Global Constraints

- `stop_atr` = `entry_context["stop_atr"]` = `abs(signal close − stop) / ATR14`, both from the signal bar; measured from the **signal close, not the planned entry or trigger**. A row whose `entry_context` is absent, or whose `stop_atr` is missing, non-numeric (bools count as non-numeric), non-finite or ≤ 0, is `unknown`.
- `atr_pct` = `stop_pct / stop_atr`, **disclosed only**, never a look. `|rho| ≥ 0.8` (Spearman, TRAIN) → the results doc states the verdict is about **ticker volatility**, not stop placement.
- `frozen_edges(rows, "stop_atr")`: TRAIN quartile cut points, `numpy.quantile(values, [0.25, 0.5, 0.75], method="linear")` over known values only, reading no `r`. Coinciding edges are merged; an empty bucket is never produced. A value equal to an edge goes to the upper bucket. Live rows are bucketed with the **TRAIN** edges. The live cut points 0.35 / 0.5 / 0.75 are never used.
- Labels: `Q1 (<a)`, `Q2 (a–b)`, `Q3 (b–c)`, `Q4 (≥c)` (en dash `–`, `≥`), values `:.2f`; with no edge the single bucket is `Q1 (all)`; `unknown` is the label of unknown rows.
- A bucket is a veto candidate when all six hold: (1) Δ ≤ −0.10R (exactly −0.10 passes); (2) upper 95% bound of Δ < 0 (exactly 0 fails); (3) bucket ExpR < 0 (exactly 0 fails); (4) Δ < 0 in at least 3 of the 4 TRAIN calendar years 2020–2023 (a year with no bucket rows counts against); (5) bucket N ≥ 300; (6) BH q < 0.10 over **this study's own family** of bucket looks (at most 4), never pooled with v146's family or with live looks.
- Δ = bucket ExpR − rest ExpR in net R, rest = every other TRAIN row with a known `stop_atr`; looks through `expectancy_attribution._look(rest, bucket, seed)` (10,000 resamples, seed 42; tests monkeypatch `N_RESAMPLES`).
- Study verdict: `VETO-CANDIDATE` (names every passing bucket) when any bucket passes; else `UNDERPOWERED` when fewer than two buckets reach N ≥ 300 (does **not** close the question); else `NO CANDIDATE` (closes "tight stops in ATR terms" as measured).
- At most 4 looks; `unknown` is disclosed, never a look. The live book is printed beside TRAIN and **never gates**. VALIDATION is never read.
- Removal arithmetic per bucket: pooled ExpR over known TRAIN rows, ExpR without the bucket (equals rest ExpR), ΔTotal R = −(sum of the bucket's `r`), N removed.
- `stop_clamped` share is a **lower-bound provenance flag** (identity-based; reads `CLAMP_STOP_TO_HARD_CAP` at run time); `None` rows leave the denominator and their count is printed.
- Live only: strategy-family shares and the share of losses closed on the entry day (`opened_at`/`closed_at`). Never computed for TRAIN; the TRAIN row contract is not widened.
- Unchanged and pinned: `scenario_rows.ROW_KEYS`, `expectancy_attribution.ROW_KEYS`, `live_row`, `_train_row`, `_PLAIN_GROUPINGS`, `assign_qvalues`, `write_latest`, the default report and `study.run(train_jsonl, *, seed, write)`'s signature.
- Preflight: the run fails if `CLAMP_STOP_TO_HARD_CAP`, `MIN_STOP_DISTANCE_PCT` or `MAX_STOP_LOSS_PCT` in the local `swingbot.config` differ from production `.env`; production is read only through `bash scripts/ops/ssh-hetzner.sh`, and values are compared without being printed (hashes or a MATCH/MISMATCH line only). `.env` values are never printed, echoed or logged.
- The TRAIN replay reads the v162 training-data store; a stale or truncated store fails the run and the store is not refetched mid-study.
- Every new or changed function stays below cyclomatic complexity 15 (`python scripts/dev/complexity_gate.py`); `run_scenario_mode` (19) and `main` (62) never get worse.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`). **No task runs the full suite; CI does after the push.**
- Tests stay in their existing suites: `tests/backtesting/test_s*.py` (`backtesting-scenarios`), `tests/analytics/` (`analytics`), `tests/backtest_scripts/` (`backtest-scripts`). No new test directory.
- Implementation runs in worktree `.claude/worktrees/2026-11-12-v226-stop-width-attribution` (branch of the same name). Name it in every dispatch. Several scoped commits, never one big one.
- `VERSION.json` unchanged (`Bump: none`).

## Review Focus

1. **A restart that changes the rows.** The as-of map is cross-sectional; building it on the remaining frames only would silently change `rs_pctile` and `regime2_state` for every ticker replayed after a restart. Pinned by V226-4 (the as-of builder receives the full frame list on restart; restarted rows and table equal an uninterrupted run).
2. **Outcome leaking into the edges.** `frozen_edges` must never read `r`. Pinned by V226-7 (shuffling `r` leaves edges identical; live rows bucketed on TRAIN edges).
3. **The BH family widening.** The verdict's q-values come from `stats.bh_qvalues` over this study's bucket looks only. Pinned by V226-8 (family size equals bucket count, ≤ 4).
4. **Clause boundaries.** −0.10 passes / −0.099 fails, upper bound 0 fails, ExpR 0 fails, 3/4 years passes and 2/4 fails, empty year counts against, N 299 / 300. Pinned by V226-8.
5. **The default report moving.** Pinned by V226-5 (golden hashes recorded before any analytics change) and re-run in V226-11.
6. **Point-in-time `stop_atr`.** Pinned by V226-1 (altering every bar after the signal leaves each replayed plan's `entry_context["stop_atr"]` unchanged).

## Parallelisation

| Group | Tasks | Why this order |
|---|---|---|
| A | V226-1 | Test-only, disjoint file; no contract. May run beside anything. |
| B | V226-2 → V226-3 → V226-4 → V226-4b | V226-4b consumes V226-4's helpers (same file); V226-4 consumes V226-2's `on_ticker_result` and V226-3's `run_sidecar`/`_run_sidecar_path`; V226-3 and V226-4 both edit `run_backtest_range.py` (same file). |
| C | V226-5 → V226-6 → V226-7 → V226-8 → V226-9 → V226-10 | V226-5's golden pin must be recorded before any change to `expectancy_attribution.py`; V226-6..10 all append to that one file (same file: sequential) and each consumes the previous task's symbols. |
| D | V226-11 | Needs V226-10 (`run_stop_width`, `stop_width_markdown`); edits the script and its test only. |
| E | V226-12 → V226-13 → V226-14 | Sequential edge on everything: the run needs B and D merged into the worktree branch; the results doc needs the run's report; the release needs the results doc. |

Groups B and C are disjoint (different files, no contract) and may run side by side. At most 2 implementers at once (`CLAUDE.md`). Suggested waves: (V226-1 ∥ V226-5), (V226-2 ∥ V226-6), (V226-3 ∥ V226-7), (V226-4 ∥ V226-8), (V226-4b ∥ V226-9), V226-10, V226-11, V226-12, V226-13, V226-14.

## Task ledger

| Id | Title | Part | Model | Files created / modified | Symbols for later tasks |
|---|---|---|---|---|---|
| V226-1 | `entry_context["stop_atr"]` truncation test on the replay path | 1 | opus | C `tests/backtesting/test_scenario_stop_atr_pit.py` | — (test only; no production change unless it fails, in which case the task stops and reports) |
| V226-2 | Per-ticker result hook in the scenario replay | 1 | sonnet | M `swingbot/core/backtesting/backtest_scenarios.py` (`_drain`, `_run_replay_tasks`, `_replay_with_rows`, `run_scenario_backtest`); C `tests/backtesting/test_scenario_ticker_hook.py` | `run_scenario_backtest(..., on_ticker_result=None)`: callable `on_ticker_result(ticker: str, exits: dict[str, list[ExitResult]], rows: list[dict]) -> None`, fired in task order after each ticker, only when `collect_rows=True`; `_drain(results, total, on_ticker_done, on_result=None)` with `on_result(index: int, result) -> None` |
| V226-3 | Run sidecar `<path>.run.json` | 1 | sonnet | M `scripts/backtest/run_backtest_range.py`; C `tests/backtesting/test_scenario_run_sidecar.py` | `STOP_SETTING_NAMES = ("CLAMP_STOP_TO_HARD_CAP", "MIN_STOP_DISTANCE_PCT", "MAX_STOP_LOSS_PCT")`; `stop_settings() -> dict` (name → `getattr(config, name)`); `RUN_SIDECAR_KEYS = ("git_head", "window", "watchlist", "membership_asof", "command", "stop_settings")`; `_run_sidecar_path(trades_jsonl) -> Path` (`<path>.run.json`); `_git_head() -> str \| None`; `_membership_asof(membership: dict \| None, today: str) -> str` (latest span boundary for a PIT map, else `today`); `run_sidecar(*, date_from: str, date_to: str, tickers: list[str], universe: str \| None, membership: dict \| None, argv: list[str], today: str) -> dict` (keys exactly `RUN_SIDECAR_KEYS`; `window={"from","to"}`, `watchlist={"universe": universe or "watchlist", "tickers": sorted(tickers)}`, `command=list(argv)`); `write_run_sidecar(trades_jsonl, sidecar: dict) -> Path` (`indent=1, sort_keys=True`) |
| V226-4 | Per-ticker row persistence, done-list and skip-on-restart for `--trades-jsonl` | 1 | opus | M `scripts/backtest/run_backtest_range.py` (`_scenario_stats` delegates to new helpers); M `tests/backtesting/test_scenario_trade_rows_cli.py` (`_stub_scenario_mode` fires `on_ticker_result`); C `tests/backtesting/test_scenario_checkpoint_cli.py` | `_done_path(trades_jsonl) -> Path` (`<path>.done.jsonl`; one line per ticker `{"ticker": str, "rows": int, "not_triggered": {horizon_key: int}}`); `_resume_checkpoint(trades_jsonl, sidecar: dict) -> dict[str, dict]` (done entries by ticker; no done file → fresh start, truncates `<path>`, writes sidecar; done file + differing sidecar → `SystemExit(2)`); `_checkpoint_writer(trades_jsonl) -> Callable[[str, dict, list], None]`; `_stats_from_checkpoint(trades_jsonl, horizons: list[str]) -> dict` (`{"pooled", "by_horizon"}`); `RESUME_KEYS` (`RUN_SIDECAR_KEYS` minus `membership_asof`); `_utc_today()`; `_jsonl_lines` |
| V226-4b | `_checkpointed_stats` and restart parity | 1 | opus | M `scripts/backtest/run_backtest_range.py` (`_scenario_stats` delegates); M `tests/backtesting/test_scenario_trade_rows_cli.py` (stub fires `on_ticker_result`); M `tests/backtesting/test_scenario_checkpoint_cli.py` (restart tests) | `_checkpointed_stats(frames, date_from, date_to, *, scale_out, universe, membership, trades_jsonl) -> dict` |
| V226-5 | Golden pin of the default attribution report and summary | 2 | sonnet | C `tests/analytics/test_expectancy_attribution_default_pin.py` | `DEFAULT_REPORT_SHA256`, `DEFAULT_SUMMARY_SHA256` constants (recorded at the pre-change HEAD) |
| V226-6 | `stop_width_row` and the two stop-width loaders | 2 | sonnet | M `swingbot/core/analytics/expectancy_attribution.py`; C `tests/analytics/test_stop_width_rows.py` | `STOP_WIDTH_KEYS = ("stop_atr", "atr_pct", "stop_clamped")`; `STOP_WIDTH_LIVE_KEYS = ("opened_at", "closed_at", "strategy")`; `stop_width_row(base_row: dict, source: dict, *, live: bool = False) -> dict` (`{**base_row, stop_atr: float \| None, atr_pct: float \| None, stop_clamped: bool \| None}` plus the live keys when `live`); `_positive_number(value) -> float \| None`; `load_stop_width_train_rows(path, *, source=None) -> list[dict]`; `load_stop_width_live_rows() -> list[dict]` |
| V226-7 | Frozen TRAIN edges, labels and the two bucketed populations | 2 | opus | M `swingbot/core/analytics/expectancy_attribution.py`; C `tests/analytics/test_stop_width_edges.py` | `UNKNOWN = "unknown"`; `frozen_edges(rows: list[dict], key: str) -> list[float]`; `edge_labels(edges: list[float]) -> list[str]`; `edge_label(value, edges: list[float]) -> str`; `stop_width_groups(train_rows: list[dict], live_rows: list[dict]) -> dict` = `{"edges": list[float], "labels": list[str], "train": POP, "live": POP}`, `POP = {"buckets": {label: list[dict]} (every label, in order), "known": list[dict], "unknown": int}` |
| V226-8 | Pre-registered verdict: six clauses, own BH family, study verdict | 2 | opus | M `swingbot/core/analytics/expectancy_attribution.py`; C `tests/analytics/test_stop_width_verdict.py` | `VETO_DELTA = -0.10`, `VETO_MIN_N = 300`, `VETO_Q = 0.10`, `VETO_YEARS = ("2020", "2021", "2022", "2023")`, `VETO_MIN_YEARS = 3`; `stop_width_verdict(train_groups: dict, *, seed: int) -> dict` (`train_groups` = `groups["train"]`) = `{"verdict": "VETO-CANDIDATE" \| "UNDERPOWERED" \| "NO CANDIDATE", "candidates": list[str], "family_size": int, "powered": int, "n_needed": 300, "looks": {label: LOOK}}`, `LOOK = {"n", "exp_r", "delta", "ci_low", "ci_high", "p", "q", "years": {year: float \| None}, "years_negative": int, "clauses": {"delta", "upper_bound", "negative_exp_r", "years", "n", "bh"}: bool, "candidate": bool}` |
| V226-9 | Disclosures: bucket stats, mix, clamped share, live same-day losses, rho, overlap, removal arithmetic | 2 | sonnet | M `swingbot/core/analytics/expectancy_attribution.py`; C `tests/analytics/test_stop_width_disclosures.py` | `stop_width_disclosures(groups: dict) -> dict` = `{"train": DISC, "live": DISC}`, `DISC = {"unknown": int, "rho": float \| None, "overlap": float \| None, "buckets": {label: {"n", "win_rate", "exp_r", "exp_r_gross", "median_rr", "direction_share", "horizon_share", "delta_by_direction", "clamped_share", "clamped_none", "removal": {"pooled_exp_r", "without_exp_r", "delta_total_r", "n_removed"}, + live only "family_share", "same_day_loss_share"}}}`; `VOLATILITY_RHO = 0.8` |
| V226-10 | Report, run and Markdown for the stop-width study | 3 | sonnet | M `swingbot/core/analytics/expectancy_attribution.py`; C `tests/analytics/test_stop_width_report.py` | `STUDY_ID = "v226-stop-width"`; `stop_width_report_path() -> Path` (`Path(config.DATA_DIR) / "reports" / "stop-width-attribution.json"`, resolved at call time); `build_stop_width_report(train_rows, live_rows, *, seed: int, generated_at: str \| None = None) -> dict` (keys `generated_at, study, seed, edges, labels, verdict, disclosures, volatility_note, provenance`); `run_stop_width(train_jsonl, *, seed: int = WEEK_BOOTSTRAP_SEED, write: bool = True) -> dict`; `stop_width_markdown(report: dict) -> str` |
| V226-11 | `--study stop-width` flag on the attribution script | 3 | sonnet | M `scripts/reports/expectancy_attribution.py`; M `tests/analytics/test_expectancy_attribution_report.py` (script tests) | CLI `--study {stop-width}` (default None) → `study.run_stop_width(train_jsonl, seed=, write=)` and `print(study.stop_width_markdown(report))` |
| V226-12 | Preflight, live replica, TRAIN replay and the study run | 3 | sonnet | none in code; outputs `data/reports/v226-train-scenarios.jsonl` (+ `.run.json`, `.provenance.json`, `.done.jsonl`), `data/reports/stop-width-attribution.json`, `logs/v226/` logs (not committed) | the report JSON and the printed Markdown, consumed by V226-13 |
| V226-13 | Results doc, pre-registration ledger row, closed-pre-registration record per verdict | 3 | opus | C `docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md`; M `docs/superpowers/results/preregistration-ledger.jsonl` (via script); M `docs/claude/backtest-methodology.md` (§ Closed pre-registrations, `NO CANDIDATE` only); M `AGENTS.md` only if a mirrored rule changes | — |
| V226-14 | Release (Bump none), merge, CI watch, `/panel` close-out review, `/close-out` | 3 | sonnet | none planned (`VERSION.json` unchanged) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-11-12-v226-stop-width-attribution_1-replay.md`](2026-11-12-v226-stop-width-attribution_1-replay.md) | V226-1..V226-4b | `stop_atr` truncation test; per-ticker replay hook; run sidecar; checkpointing with restart parity |
| 2 | [`2026-11-12-v226-stop-width-attribution_2-study.md`](2026-11-12-v226-stop-width-attribution_2-study.md) | V226-5..V226-9 | Default-report golden pin; stop-width rows and loaders; frozen edges and groups; the verdict; the disclosures |
| 3 | [`2026-11-12-v226-stop-width-attribution_3-report-run.md`](2026-11-12-v226-stop-width-attribution_3-report-run.md) | V226-10..V226-14 | Report/run/Markdown; the `--study` flag; preflight and run; results doc and records; release and close-out |

## Notes for part writers

- **V226-1:** use `tests/backtesting/test_scenario_rows.py`'s `_structured_df`, `GATES` and `_legacy_scorer` pattern (copy, files stay independent; mark `pytest.mark.slow`). Replay `bs.replay_scenarios_detailed("AAPL", df, "4w", gates=GATES)` on the frame and on a copy whose OHLC after a cut index `k` is multiplied by 3.0; for every hit with `hit.i < k`, assert `hit.plan.entry_context["stop_atr"]` (and `stop_pct`) are equal and not None. Also call `entry_context(df.iloc[:i+1], …)` directly for one hit against the spiked frame cut at the same bar. If the assertion fails, stop: that is a lookahead finding for the controller, not something to patch inside this task.
- **V226-2:** the hook is additive; `on_ticker_done` keeps `(done, total)`. `_replay_with_rows` wraps `on_result` as `lambda i, res: on_ticker_result(tasks[i][0], res[0], res[1])`. `pool.map` yields in task order, so index `i` is the task index. Test with `workers=1` and with a stub worker; assert call order equals `list(frames)` and stats are byte-equal with and without the hook.
- **V226-3:** `_git_head()` runs `git rev-parse HEAD` (cwd = repo root from `Path(__file__)`), returns None on failure. `_membership_asof`: for a PIT map, the max ISO string over every non-None span start/end; for `None`, `today` (the date the watchlist was read). `today` is passed in (UTC ISO date) so tests are deterministic. Sidecar values only; never `.env` contents beyond the three stop settings.
- **V226-4:** `_scenario_stats` with `trades_jsonl` calls `_checkpointed_stats` and returns its stats; without it, the code path is byte-for-byte today's. `_checkpointed_stats` order: build `sidecar = run_sidecar(..., tickers=list(frames), argv=sys.argv[1:], today=<UTC date>)`; `done = _resume_checkpoint(trades_jsonl, sidecar)`; `asof_map = _build_asof_map(list(frames), frames, universe)` on the **full** frame set; `remaining = {t: df for t, df in frames.items() if t not in done}`; `run_scenario_backtest(remaining, …, asof_map=asof_map, collect_rows=True, on_ticker_done=_scenario_progress(trades_jsonl), on_ticker_result=_checkpointed_writer)`; then `_stats_from_checkpoint`, unlink `.progress`, print `Wrote {n} trade rows to {path}`. The writer appends rows (`json.dumps(row, default=_jsonable)`), flushes and `os.fsync`s, then appends the done line. `_resume_checkpoint` with a done file keeps only `<path>` lines whose `"ticker"` is in the done set (drops a half-written tail). `_stats_from_checkpoint` reads `<path>` rows into `SimpleNamespace(outcome, runner_outcome, r_total)` per `horizon_key` plus `not_triggered` placeholders and calls `backtest_scenarios._aggregate`; horizons are `list(LEGACY_HORIZONS)`. A slow test proves `_stats_from_checkpoint` equals `run_scenario_backtest`'s own stats on `_structured_df` for one ticker. The restart test interrupts the fake replay after the first ticker (raise `KeyboardInterrupt` from the hook), restarts with the same arguments, and compares `<path>` and `backtest_range_summary.txt` with an uninterrupted run in another `tmp_path`, plus asserts the as-of builder saw the full ticker list on the restart. The existing `test_scenario_mode_writes_rows_and_clears_the_progress_file` stub must fire `on_ticker_result` for AAA and BBB instead of returning `stats["rows"]`.
- **V226-5:** before any edit to `expectancy_attribution.py`: build fixed live/TRAIN rows with the `population()`/`_trade()` helper style (copy), `monkeypatch.setattr(ea, "N_RESAMPLES", 200)`, call `ea.build_report(live, train, seed=42, generated_at="2026-11-12T00:00:00+00:00")`, hash `json.dumps(report, sort_keys=True, default=str)`; import the script's `summary()` and hash its output for the same report. Record the two hex digests as constants in the test, run it green at the pre-change HEAD, commit it alone.
- **V226-6:** `_positive_number` rejects bool, non-int/float, NaN/inf and ≤ 0. `atr_pct` = `stop_pct / stop_atr` only when both are positive numbers. `stop_clamped` keeps a real bool, anything else is None. Live keys: `str(value)` when present, else None. The loaders reuse `_train_row`/`live_row` and `closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None))` exactly as the v146 loaders, then wrap with `stop_width_row`. Tests assert `tuple(ea.live_row(_trade())) == ea.ROW_KEYS` still holds and that `tuple(row)` of a stop-width row is `ea.ROW_KEYS + STOP_WIDTH_KEYS (+ STOP_WIDTH_LIVE_KEYS)`.
- **V226-7:** `frozen_edges`: known values = `_positive_number(row.get(key))` not None; fewer than 2 known values → `[]`; quantiles, dedupe preserving order, drop any edge ≤ min(values), then drop any edge whose bucket `[prev, edge)` holds no value, then drop the last edge while the top bucket `≥ last` is empty (cannot happen after the min rule, but test-pinned). `edge_label` uses `bisect.bisect_right(edges, value)` for the bucket index. `stop_width_groups` computes edges from TRAIN only and buckets live with them; unknown rows are counted, never placed in `buckets` or `known`.
- **V226-8:** per label in order: `bucket = buckets[label]`, `rest = [r for r in known if id(r) not in ids]`, `look = _look(rest, bucket, seed)`; `exp_r = _mean(bucket r)`; year of a row = `row["week"][:4]`; year Δ = mean(bucket rows of that year) − mean(rest rows of that year), None when either side is empty (counts against). `qs = stats.bh_qvalues([look["p"] for each label])`; `family_size = len(labels)`. Clause 2 and 6 are False when `ci_high`/`q` is None. Tests monkeypatch `ea._look` to inject exact deltas/bounds/p for the boundary cases and spy `stats.bh_qvalues` for the family size.
- **V226-9:** per population (TRAIN and live separately, live with the TRAIN edges): `bucket_stats` for n/win_rate/exp_r/exp_r_gross; `median_rr` over non-None `risk_reward_ratio`; shares are `{label: fraction}` over the bucket; `delta_by_direction[d]` = bucket ExpR − rest ExpR within direction `d` when that stratum's bucket N ≥ 100, else None; `clamped_share` = True / (True + False), `clamped_none` = count of None; `family_share` (from `strategy`) and `same_day_loss_share` (losses `r < 0` with `opened_at[:10] == closed_at[:10]`, over losses) on live only; `rho = _spearman(stop_atr, atr_pct)` over known rows with `atr_pct`; `overlap` = share of those rows whose `stop_atr` bucket index equals `n_atr_buckets − 1 − atr_pct bucket index`, `atr_pct` edges from TRAIN `frozen_edges(train_known, "atr_pct")`; removal arithmetic over that population's known rows.
- **V226-10:** `build_stop_width_report` = groups → verdict (TRAIN) → disclosures; `volatility_note = rho is not None and abs(rho) >= VOLATILITY_RHO` (TRAIN). `run_stop_width` provenance: `train_rows {path, rows, sha256}`, `run_sidecar` (parsed `<train_jsonl>.run.json` or None), `store_provenance` (parsed `training_data.provenance_path(train_jsonl)` or None), `frictions`, `live_fills_include_frictions`, `n_resamples`; writes with `jsonio.atomic_write_json(str(stop_width_report_path()), report)` when `write`. `stop_width_markdown` renders: verdict line, edges, per-bucket TRAIN table with the six clauses, live table beside it, disclosures, the volatility sentence when flagged, the "descriptive, not a veto" paragraph and the what-each-verdict-buys line.
- **V226-11:** `--study` is `choices=("stop-width",)`, default None. The existing `fake_run` script test and printed lines stay byte-identical; a new test asserts `--study stop-width` calls `run_stop_width` only (spy `ea.run` is not called) and writes nothing but `stop-width-attribution.json` under a tmp `DATA_DIR`. Re-run V226-5's pin.
- **V226-12:** in the worktree. Preflight 1: `python -c` locally and through `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -"` (stdin script) each print only `sha256(json.dumps([config.CLAMP_STOP_TO_HARD_CAP, config.MIN_STOP_DISTANCE_PCT, config.MAX_STOP_LOSS_PCT]))`; compare in the shell and print MATCH/MISMATCH; MISMATCH stops the task. Preflight 2: training-data store integrity (`python scripts/data/fetch_backtest_data.py` is **not** run; a stale store stops the task and is reported). Then `/replicate-prod-db`. Then dispatch `backtest-runner`: `python scripts/backtest/run_backtest_range.py --scenarios --train --exit-model v2 --scale-out --trades-jsonl data/reports/v226-train-scenarios.jsonl` (v146's flags), logs to `logs/v226/`; on interruption restart with the same command. Then `python scripts/reports/expectancy_attribution.py --train-jsonl data/reports/v226-train-scenarios.jsonl --study stop-width > logs/v226/stop-width.md`. Computed once; never re-run to change a verdict.
- **V226-13:** the results doc follows `results/2026-10-15-v146-expectancy-attribution.md`'s shape: verdict first, the pre-registered rule quoted verbatim from the spec, TRAIN and live tables, disclosures, both sidecars quoted, observations. Ledger row via `python scripts/reports/preregistration_ledger.py --id v226-stop-width --instrument v1 --hypothesis "<spec rule, one line>" --n <decisive bucket N> --exp-r <its TRAIN ExpR> --p <its p> --verdict <PASS for VETO-CANDIDATE | NO-LIFT for NO CANDIDATE | INCONCLUSIVE for UNDERPOWERED> --record docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md --data-source <from the store provenance>`; the decisive bucket is the most negative Δ (the candidate with the most negative Δ when there is one). `NO CANDIDATE` adds a § Closed pre-registrations row (reopening needs a mechanism other than "a TRAIN quartile of stop distance in ATR14 units"). `VETO-CANDIDATE` adds a "What follows" line naming the Stage −2 avoid idea; `UNDERPOWERED` names the N that would power it.
- **V226-14:** `Bump: none`: `VERSION.json` untouched, no `version_history` regeneration. Merge via `worktree-lifecycle` after the partner's yes (`AskUserQuestion`), push, `gh run watch` in the background and fix failures until green, `/panel quant-researcher,quant-engineer` on the diff and results doc, then `/close-out` (no-lift/ or implemented/ per the results; a measurement with a verdict is `implemented/`), Step 5b skill alignment (`backtest-gate` cites `run_backtest_range.py --trades-jsonl`: add the checkpoint/sidecar files if it names outputs).
