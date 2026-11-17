# v232 — Live versus replay reconciliation, per direction: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-7" -A 400 <part file>`); never read a part whole.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) — including its binding section `## Clarifications from the code brief`.
**Brief:** `.superpowers/briefs/2026-11-16-v232-live-replay-reconciliation.md`

## Goal

The partner wants LONG and SHORT each to be profitable, and wants to change
the backtest process to get there. Before any replay rule is made stricter,
we need to know how far the backtest is from what the live paper bot
actually did, and why. Nothing in the repo answers that today: the existing
parity reports compare engines with each other, data providers with each
other, or manual closes with the exit engine, never the live book with the
backtest plan by plan. Live is intraday (scans in session, enters at the
current price, polls exits every 60 seconds); the backtest is daily (enters
at a close or the next open, walks daily bars). The difference between the
two has never been measured, per direction.

Once shipped, a re-runnable report script
(`scripts/reports/live_replay_reconcile.py`) and one committed results doc
say, for LONG and SHORT separately and for both fill models, how many R
separate the live book from the backtest of the same plans, split trade by
trade into an **entry** effect, an **exit** effect and **modelled costs**
that add up exactly (no remainder line; a self-check fails the run on a
0.01R mismatch). It counts which signals each side took that the other did
not, names the mechanisms (same-day exits, wicks the poll never saw, gaps,
opening minutes, moved stops, ...) with counts, and records a `DESCRIPTION`
row in the pre-registration ledger.

How it works: layer 1 rehydrates each stored live plan to its issued state
and runs it through the unchanged public exit engines (`R_as_backtest`) and
through a new from-fill wrapper that walks the same exit rules from the live
fill (`R_exit_only`), on **unadjusted** daily bars fetched once into a
scratch history store; everything is expressed in the live trade's own risk
unit. Layer 2 runs the live scan code over the window through
`scan_replay` and matches its signals to live plans, keeping counts only:
its adapter drops every outcome field before anything is stored.

What it leaves alone: every replay rule, fill model and cost; the live bot
(nothing it scans, alerts on or posts changes); the existing `rows` export
mode; every existing engine function (two additions only: a public
from-fill wrapper per engine and a defaulted `adjustment` parameter on the
Alpaca daily fetch, default byte-identical). **Partner binding:** no outcome
(R, win/loss, exit date) of a signal live did not trade is ever stored or
printed, and backtest R appears per direction only, never keyed by
strategy, horizon, ticker, ledger or parameter.

Success is measured by: the per-direction reconciliation tables reproduce
the live book's net total within 0.01R from per-trade rows; the parity
tests pin both wrappers to the engines; the leak test passes over the
committed Markdown and JSON; and the results doc opens with the paper-book
caveat and carries the ledger row `v232-reconciliation`.

## Architecture

- **Export** — `scripts/ops/export_book_rows.sh` gains a read-only
  `reconcile <since>` mode (`psql -X -q -A -t` + `row_to_json`, its own
  `READ ONLY` guard, no second `COPY (`, no `UNION ALL`). One JSONL stream,
  each line tagged with `kind` (shapes in the ledger, V232-1).
- **Engine wrappers** — `exit_sim.simulate_exit_from_fill` (v1 walk) and
  `exit_sim_v2.simulate_exit_v2_from_fill` (v2 fills, the
  `override_fidelity.engine_path` precedent). Both take `fill_bar_check`;
  parity tests pass the engine's own setting per entry type; layer 1 always
  passes `False`.
- **Raw bars** — `AlpacaProvider.daily_bars_between(..., *, adjustment=Adjustment.ALL)`;
  `scripts/reports/reconcile/raw_bars.py` fetches `RAW` and `SPLIT` bars
  into two scratch stores under `data/v232/bars/` (each with its own
  `daily/_manifest.json`), reads them back with `history_store.load(ticker, "daily")`
  under `HISTORY_STORE_DIR`, and refuses split-in-window and short-bars
  tickers.
- **Report package** — `scripts/reports/reconcile/` (shaped like
  `scripts/reports/autopsy/`): `sessions.py` (time), `records.py` (export
  rows, populations, rehydration), `layer1.py` (values, units, costs),
  `tags.py` (mechanisms, distributions), `checkpoint.py` + `layer1_run.py`
  (per-trade rows, checkpointed), `layer2.py` (adapter, match, counts),
  `layer2_run.py` (scan replay, checkpointed per lane), `table.py`
  (reconciliation lines, self-check), `intervals.py` (one-arm week-cluster
  bootstrap, cells), `render.py` (report dict, Markdown, leak guard). CLI:
  `scripts/reports/live_replay_reconcile.py`.
- **Data flow:** export JSONL → `records.load_export` → layer 1
  (`layer1_run.run_layer1`, raw bars) → `TradeRow`s in
  `data/v232/trade-rows.jsonl` (git-ignored) ; export + adjusted store
  frames → `layer2_run.run_layer2` → `ReplaySignal`s → `layer2.match` →
  selection counts ; rows + counts → `render.build_report` (tables via
  `table.build_table` + `table.self_check`, cells via `intervals`) →
  `render.leaks` guard → `.md` + `.json` in `docs/superpowers/results/`.

## Global Constraints

- **Holdout (partner binding).** No outcome (R, win/loss/scratch/timeout class, exit date) of a signal live did not trade is stored, printed or committed. Unfilled plans keep only `would_fill: bool | None` per fill model; still-open trades keep nothing from the backtest; `ReplaySignal` has no `outcome`, `r_multiple` or `exit_date` field. `scan_replay._alert` keeps using replay exit days internally (the live one-open-trade rule, clarification 5).
- **No component R.** Backtest R (`r_as_backtest`, `r_exit_only`, `r_rebased`, entry/exit effects) appears per direction (and fill model, era) only. The ledger split (`main`/`weak`) is shown for live figures only. Committed JSON holds aggregates; per-trade rows go to `data/v232/` (git-ignored) and the doc records their SHA-256. `render.leaks(report)` must return `[]` or the CLI exits 2.
- **Nothing existing is edited in behaviour.** In `swingbot/` only: `exit_sim.simulate_exit_from_fill` (new), `exit_sim_v2.simulate_exit_v2_from_fill` (new), the defaulted `adjustment` keyword on `AlpacaProvider._bars` / `daily_bars_between` (default `Adjustment.ALL`, byte-identical). `simulate_exit`, `_single_leg_exit_walk`, `simulate_exit_v2`, `override_fidelity.*`, `scan_replay.*` are not touched.
- **One R unit.** Every value is in the live trade's risk unit `|live fill − issued stop|`; `R_live = r_realized × |trade.entry − trade.stop_loss| / live_risk`; engine results convert via `r_total × |result.entry_price − plan.stop_loss| / live_risk`; the re-based figure (`r_total`) is printed beside it with the median stop-distance shift in percent.
- **Timing.** Signal bar = `issue_session(stamp)` (stamp = plan `issued_at`, else `created_at`, source recorded). Fill bar of `R_exit_only` = `issue_session(trade.opened_at)`; the walk starts at the bar after it (`fill_bar_check=False`). All zone work in Python `zoneinfo` (`session.US_MARKET_TZ`); never Git Bash `TZ=`.
- **Frozen cut-offs.** `SLIP_TAG_R = 0.05`, `SHORT_GAP_PCT = 0.03`, `FIRST_MINUTES = 15`, `MATCH_SESSIONS = 1`, `TOLERANCE_R = 0.01`, `SCRATCH_R = 0.05`, `SPLIT_DRIFT = 0.01`, era boundary `autopsy.eras.ERA_BOUNDARY_UTC`, `MANUAL_REASONS = ("manual", "manual_bulk")`.
- **Statistics.** Intervals only from `instrument/stats.py:week_cluster_bootstrap` with `WEEK_BOOTSTRAP_SEED` (42) and `WEEK_BOOTSTRAP_RESAMPLES` (10 000), one-arm (`baseline=[]`), clustered by entry week; label `"descriptive; under-covers below 20 clusters"`; thin flag `autopsy.cells.is_thin`; tag means carry no interval.
- **Long run.** Layer 1 appends one row per trade (`JsonlCheckpoint`, fsync per line); layer 2 checkpoints per lane (see Handoff note below); raw bars per ticker via the bar manifests; a restart skips finished units. The run is dispatched to `backtest-runner`.
- **Production.** Read-only, only through `bash scripts/ops/ssh-hetzner.sh`; `.env` values never printed. No database tests (sqlite/in-memory fixtures and synthetic frames only).
- **Tests.** New report tests in `tests/scout/` (suite `scout`, no `tests/suites.toml` edit); wrapper parity in `tests/planning/` (suite `planning`); provider in `tests/marketdata/test_alpaca_provider.py`. Report tests import with `sys.path.insert(0, str(REPO / "scripts" / "reports"))` then `from reconcile import <module>`. Per-task verification: `python scripts/dev/testrun.py file <test>`; **no task runs the full suite** (CI does).
- **Complexity < 15** on every new function (`scripts/dev/complexity_gate.py`); the tag classifier is table-driven (`tags.RULES`).
- **Files** written with `encoding="utf-8", newline="\n"`.
- **Commits.** The implementer commits per task in the plan's worktree, single-line messages; plan writers do not commit.

## Parallelisation

At most 2 implementers at once (session rule).

- **V232-1 ∥ V232-2 ∥ V232-3 ∥ V232-4 ∥ V232-5.** Disjoint files, no contract between them (export script; `exit_sim.py`; `exit_sim_v2.py`; provider + `raw_bars.py`; `sessions.py` + package `__init__` + `.gitignore`). V232-4 creates `raw_bars.py` inside the package V232-5 creates: V232-4 creates `scripts/reports/reconcile/__init__.py` only if absent, with the docstring fixed in V232-5's ledger row, so either order works.
- **Sequential (contract):** V232-4b runs after V232-4 (same two files).
- **Sequential (contract):** V232-6 needs V232-1 (JSONL shapes) and V232-5 (`sessions.to_utc`, `stamp_source`, `issue_session`).
- **V232-7 ∥ V232-8 ∥ V232-10** after V232-6. Disjoint files; V232-7 also needs V232-2 and V232-3 (wrappers); V232-8 consumes only `records` and `sessions` (its `TagInput` takes `r_exit_only` and classes as plain values); V232-10 consumes `records` and `sessions`.
- **Sequential (contract):** V232-9 needs V232-4 (`raw_bars.load_bars`) and V232-4b (`refusal`), V232-7 (`score`, `Values`) and V232-8 (`tags_for`, `gap_detail`, `entry_slip`, `poll_fill`).
- **Sequential (contract):** V232-11 needs V232-10 (`adapt`, `ReplaySignal`).
- **V232-12 ∥ V232-13** after V232-9 (`TradeRow`); V232-12 also needs V232-10 (`MatchResult`, `selection_counts` shape). Disjoint files.
- **Sequential (contract):** V232-14 needs V232-12 and V232-13. V232-15 needs V232-4, V232-4b, V232-9, V232-11, V232-14.
- **Sequential (operations):** V232-16 needs everything merged into the worktree, plus the production export and the raw bars; a group of one.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V232-1 | `reconcile` export mode | 1 | sonnet | M `scripts/ops/export_book_rows.sh`, M `tests/scout/test_export_script.py` | `bash -s -- reconcile <since YYYY-MM-DD>` (bad/missing date: exit 2); JSONL lines: `{"kind":"plan","plan":{plan doc},"trade":{trade doc}\|null,"journal":{journal doc}\|null}` (plans `created_at >= since`, LEFT JOIN `trades` on `trades.doc->>'plan_id' = plans.plan_id`, LEFT JOIN `journal_entries` on `trade_id`); `{"kind":"rejection","ticker","gate","strategy","horizon","signal_date"}` (`signal_date >= since`); `{"kind":"watchlist","ticker","added_at"}` (all rows); `{"kind":"deploy","entry":{deploys.jsonl object}}` (none when the file is absent); `rows` mode and `EXPECTED_COLUMNS`, `SCRIPT`, `select_aliases` unchanged |
| V232-2 | `simulate_exit_from_fill` (v1) and parity | 1 | opus | M `swingbot/core/planning/exit_sim.py`, C `tests/planning/test_exit_sim_from_fill.py` | `exit_sim.simulate_exit_from_fill(df, fill_index: int, fill_price: float, plan: TradePlanV2, *, scale_out: bool, fill_bar_check: bool = False, max_holding_days: int \| None = None) -> ExitResult` (hold cap = `_hold_cap_bars(plan, max_holding_days or HORIZONS[plan.horizon_key]["max_holding_days"])`; `fill_bar_check` runs `_fill_bar_exit` first; then `_walk_for(plan, scale_out)(df, fill_index, fill_price, plan, cap)`) |
| V232-3 | `simulate_exit_v2_from_fill` and parity | 1 | opus | M `swingbot/core/planning/exit_sim_v2.py`, C `tests/planning/test_exit_sim_v2_from_fill.py` | `exit_sim_v2.simulate_exit_v2_from_fill(df, fill_index: int, fill_price: float, plan: TradePlanV2, instrument: InstrumentSpec, *, scale_out: bool, fill_bar_check: bool = False, max_holding_days: int \| None = None, indicator_df=None) -> ExitResult` (`fill_bar_exit` when checked, then `walk_v2`) |
| V232-4 | Raw daily bars: provider `adjustment` keyword and the scratch stores | 1 | sonnet | M `swingbot/core/marketdata/providers/alpaca_provider.py`, M `tests/marketdata/test_alpaca_provider.py`, C `scripts/reports/reconcile/raw_bars.py` (and `scripts/reports/reconcile/__init__.py` if absent), C `tests/scout/test_reconcile_raw_bars.py` | `AlpacaProvider._bars(..., *, adjustment=Adjustment.ALL)`, `daily_bars_between(tickers, start, end, *, adjustment=Adjustment.ALL)`; `raw_bars.KINDS = ("raw", "split")`; `SPLIT_DRIFT = 0.01`; `REFUSALS = ("no_bars", "split_in_window", "bars_end_early")`; `store_dir(root: Path, kind: str) -> Path`; `use_store(path: Path)` (context manager, sets/restores `HISTORY_STORE_DIR`); `write_frame(store: Path, ticker: str, frame: pd.DataFrame) -> str` (sha256); `fetch_bars(tickers, start: date, end: date, root: Path, *, provider, out=print) -> dict` (resumes per ticker); `load_bars(ticker: str, root: Path, kind: str = "raw") -> pd.DataFrame \| None`; `refusal(raw, split, *, start: date, last_exit: date \| None) -> str \| None`; `bars_manifest(root: Path) -> dict` |
| V232-4b | Raw-bar refusals and the bars manifest | 1 | sonnet | M `scripts/reports/reconcile/raw_bars.py`, M `tests/scout/test_reconcile_raw_bars.py` | `raw_bars.SPLIT_DRIFT`, `REFUSALS`, `refusal(raw, split, *, start, last_exit)`, `bars_manifest(root)` (split out of V232-4 for the 20 KB task cap; the V232-4 row's signatures are unchanged) |
| V232-5 | Package, sessions and the ignore rule | 1b | sonnet | C `scripts/reports/reconcile/__init__.py` (if absent), C `scripts/reports/reconcile/sessions.py`, C `tests/scout/test_reconcile_sessions.py`, M `.gitignore`, C `tests/scout/test_reconcile_ignored.py` | package docstring `"""v232: live versus replay reconciliation (scripts/reports/live_replay_reconcile.py)."""` and `WORK_DIR = Path("data/v232")`; `.gitignore` line `data/v232/`; `sessions.to_utc(value: str \| dt.datetime) -> dt.datetime`; `ny_time(stamp) -> dt.datetime`; `issue_session(stamp) -> dt.date`; `stamp_source(plan_doc: dict) -> tuple[dt.datetime, str]` (`"issued_at"` \| `"created_at"`); `ISSUE_BUCKETS = ("open_to_1030", "mid_day", "last_hour", "outside_session")`; `issue_bucket(stamp) -> str`; `in_regular_session(stamp) -> bool`; `minutes_after_open(stamp) -> float \| None`; `sessions_apart(a: dt.date, b: dt.date) -> int` |
| V232-6 | Export records, populations and rehydration | 2 | sonnet | C `scripts/reports/reconcile/records.py`, C `tests/scout/test_reconcile_records.py` | `KINDS = ("plan", "rejection", "watchlist", "deploy")`; `MANUAL_REASONS`; `CLASSES = ("closed", "manual", "still_open", "unfilled")`; `@dataclass(frozen=True) LiveRecord(plan_id, ticker, direction, plan: dict, trade: dict \| None, journal: dict \| None)` with `.side` (`"long"`/`"short"`); `@dataclass(frozen=True) Export(records: tuple, rejections: tuple, watchlist: tuple[str, ...], deploys: tuple)`; `load_export(path, *, input_fingerprints=None, until: dt.date \| None = None) -> Export`; `class_of(rec) -> str`; `era_of(rec, boundary=ERA_BOUNDARY_UTC) -> str` (`"headline"`/`"earlier"`); `ledger_of(rec) -> str`; `unfilled_reason(rec) -> str`; `rehydrate(plan_doc: dict) -> tuple[TradePlanV2, bool]` (issued state, `scale_out`); `deploys_between(export, start, end) -> list[dict]` |
| V232-7 | Layer 1 values, the live R unit and costs | 2 | opus | C `scripts/reports/reconcile/layer1.py`, C `tests/scout/test_reconcile_layer1.py` | `FILL_MODELS = ("v1", "v2")`; `SCRATCH_R = 0.05`; `OUTCOME_CLASSES = ("win", "loss", "scratch", "timeout")`; `live_risk(rec) -> float`; `r_live(rec) -> float`; `live_cost_r(rec, frictions: dict) -> float` (positive cost; borrow only for shorts); `bar_position(df, day: dt.date) -> int \| None`; `@dataclass(frozen=True) Values(fill_model, r_exit_only, exit_only_outcome, exit_only_class, r_as_backtest: float \| None, r_rebased: float \| None, stop_shift_pct: float \| None, backtest_no_fill: bool)`; `score(rec, df, fill_model) -> Values`; `effects(r_live: float, v: Values) -> dict` (`exit`, `entry` or None); `would_fill(rec, df, fill_model) -> bool \| None`; `outcome_class(outcome: str \| None, r: float) -> str` |
| V232-8 | Mechanism tags and the slip distributions | 2 | sonnet | C `scripts/reports/reconcile/tags.py`, C `tests/scout/test_reconcile_tags.py` | `TAGS` (17 names, spec order + `entry_slip`, `poll_fill`); `SLIP_TAG_R = 0.05`; `SHORT_GAP_PCT = 0.03`; `FIRST_MINUTES = 15`; `@dataclass(frozen=True) TagInput(rec, df, fill_pos: int, exit_pos: int \| None, live_risk: float, r_live: float, r_exit_only: float, live_class: str, exit_only_class: str)`; `RULES: dict[str, Callable[[TagInput], bool]]`; `tags_for(t) -> tuple[str, ...]`; `gap_detail(t) -> dict \| None` (`gap_r`, `gap_pct`, `exit_vs_open_r`, `exit_vs_stop_r`); `entry_slip(t) -> tuple[float, float]` (bps, R; adverse positive); `poll_fill(t) -> tuple[float, float] \| None` |
| V232-9 | Layer 1 runner and per-trade checkpoint | 2 | sonnet | C `scripts/reports/reconcile/checkpoint.py`, C `scripts/reports/reconcile/layer1_run.py`, C `tests/scout/test_reconcile_layer1_run.py` | `class JsonlCheckpoint(path: Path)`: `done() -> set[str]`, `append(key: str, row: dict) -> None`, `rows() -> list[dict]`, `.path`; `@dataclass(frozen=True) TradeRow(trade_id, plan_id, ticker, strategy, horizon_key, ledger, side, era, klass, refusal, entry_date, stamp_source, issue_bucket, r_live_gross, cost_r, r_live_net, values: dict, effects: dict, tags: tuple, gap: dict \| None, entry_slip: tuple \| None, poll_fill: tuple \| None, live_class, unfilled_reason, would_fill: dict)` with `to_dict()` / `TradeRow.from_dict(d)` and `.scored` (klass `closed`, no refusal); `row_for(rec, bars, *, frictions) -> TradeRow` (`bars(ticker) -> tuple[raw_df \| None, split_df \| None]`); `run_layer1(export, bars, checkpoint, *, frictions, start: dt.date, out=print) -> list[TradeRow]` (key = `plan_id`) |
| V232-10 | Layer 2 adapter, matching and selection counts | 3 | sonnet | C `scripts/reports/reconcile/layer2.py`, C `tests/scout/test_reconcile_layer2.py` | `OUTCOME_FIELDS = ("outcome", "r_multiple", "exit_date")`; `MATCH_SESSIONS = 1`; `@dataclass(frozen=True) ReplaySignal(lane, ticker, direction, source, mode, decision_date, horizon_key, strategy, entry, stop, target)` + `to_dict` / `from_dict`; `adapt(alert) -> ReplaySignal`; `@dataclass(frozen=True) LivePlan(plan_id, ticker, direction, source, session: dt.date, horizon_key, bucket, entry, stop, target, r_live_net: float \| None)`; `live_plans(export, rows_by_plan: dict) -> list[LivePlan]`; `@dataclass MatchResult(matched: list, live_only: list, replay_only: list, outside_replay: list)`; `match(signals, plans) -> MatchResult`; `REPLAY_ONLY_REASONS = ("gate_rejection", "open_position", "unexplained")`; `replay_only_reason(signal, export) -> tuple[str, str \| None]`; `level_diffs(plan, signal) -> dict`; `selection_counts(result, export) -> dict` keyed by side (`long`/`short`) |
| V232-11 | Layer 2 runner over `scan_replay` | 3 | opus | C `scripts/reports/reconcile/layer2_run.py`, C `tests/scout/test_reconcile_layer2_run.py` | `replay_tickers(export) -> tuple[str, ...]`; `live_short_modes() -> frozenset[str]`; `reference_symbols(modes) -> tuple[str, ...]`; `load_frames(symbols, *, load=history_store.load) -> tuple[dict, list[str]]`; `coverage(frames, window, *, base_tickers, modes, snapshot_fn) -> dict`; `params_digest(params) -> str`; `run_layer2(frames, window: tuple[str, str], params, *, base_tickers, modes, checkpoint_dir: Path, out=print) -> list[ReplaySignal]` (files `lane-base.jsonl`, `lane-extra.jsonl`) |
| V232-12 | Reconciliation table and self-check | 3 | sonnet | C `scripts/reports/reconcile/table.py`, C `tests/scout/test_reconcile_table.py` | `TOLERANCE_R = 0.01`; `class ReconcileError(RuntimeError)`; `LINE_KEYS = ("backtest", "entry", "exit", "live_gross", "costs", "live_net", "backtest_no_fill", "manual", "refused", "book_net")`; `@dataclass(frozen=True) Line(key, label, total_r, n)`; `build_table(rows, *, side, fill_model, era="headline") -> list[Line]`; `book_total(rows, *, side, era) -> float`; `self_check(lines, rows, *, side, fill_model, era) -> None`; `selection_line(counts: dict, rows, *, side, era) -> str` |
| V232-13 | Intervals, cells, confusion and distributions | 4 | sonnet | C `scripts/reports/reconcile/intervals.py`, C `tests/scout/test_reconcile_intervals.py` | `INTERVAL_LABEL = "descriptive; under-covers below 20 clusters"`; `@dataclass(frozen=True) WeekItem(entry_date: str, value: float)`; `one_arm_interval(items, *, n_resamples, seed) -> tuple[float, float] \| None`; `@dataclass(frozen=True) CellStats(n, weeks, total, mean, largest_week_share, interval, thin)` + `to_dict()`; `cell_stats(items, *, n_resamples, seed, with_interval=True) -> CellStats`; `confusion(rows, fill_model) -> dict[str, dict[str, int]]`; `distribution(values) -> dict` (`n`, `median`, `p90`); `tag_means(rows, fill_model) -> dict[str, dict]`; `cell_count(report: dict) -> int` |
| V232-14 | Report assembly, Markdown and the leak guard | 4 | sonnet | C `scripts/reports/reconcile/render.py`, C `tests/scout/test_reconcile_render.py` | `CAVEAT` (spec paragraph, verbatim); `FORBIDDEN_KEYS = ("strategy", "horizon", "horizon_key", "ticker", "ledger", "parameter", "params")`; `BACKTEST_R_KEYS`; `build_report(rows, selection: dict, export, *, meta: dict, n_resamples: int, seed: int) -> dict`; `leaks(report: dict, markdown: str) -> list[str]`; `render_markdown(report: dict) -> str` |
| V232-15 | The CLI, manifest and end-to-end run on fixtures | 4 | sonnet | C `scripts/reports/live_replay_reconcile.py`, C `tests/scout/test_live_replay_reconcile.py` | `main(argv=None) -> int` (0 ok, 2 refused); flags `--export`, `--since`, `--until`, `--bars-root` (default `data/v232/bars`), `--work-dir` (default `data/v232`), `--fetch-bars`, `--date`, `--results-dir` (default `docs/superpowers/results`), `--resamples`, `--seed`, `--expect-params-digest`, `--short-modes` (comma list of `broad`/`isolated`, `none` for the base lane only; default `layer2_run.live_short_modes()`); outputs `<results-dir>/<date>-v232-live-replay-reconciliation.md` and `.json`, `<work-dir>/trade-rows.jsonl`, `<work-dir>/layer2/lane-*.jsonl` |
| V232-16 | Run: export, raw bars, reconciliation and the ledger row | 4 | sonnet | C `docs/superpowers/results/<date>-v232-live-replay-reconciliation.md`, C `docs/superpowers/results/<date>-v232-live-replay-reconciliation.json`, M `docs/superpowers/results/preregistration-ledger.jsonl` | ledger row `v232-reconciliation` (`instrument` `v1`, verdict `DESCRIPTION`, `p` null, `exp_r` null) |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-16-v232-live-replay-reconciliation_1-foundations.md` | V232-1..V232-4b | export mode, both from-fill wrappers, raw bars and their refusals |
| 1b | `2026-11-16-v232-live-replay-reconciliation_1b-sessions.md` | V232-5 | package, sessions and the ignore rule (moved out of part 1 for the 1500-line cap) |
| 2 | `2026-11-16-v232-live-replay-reconciliation_2-layer1.md` | V232-6..V232-9 | records and populations, layer 1 values, tags, runner with checkpoint |
| 3 | `2026-11-16-v232-live-replay-reconciliation_3-layer2-table.md` | V232-10..V232-12 | layer 2 adapter and matching, the scan replay runner, the reconciliation table |
| 4 | `2026-11-16-v232-live-replay-reconciliation_4-report-run.md` | V232-13..V232-16 | intervals, renderer and leak guard, the CLI, the run and the ledger row |

## Handoff

- **Layer 2 checkpoints per lane, not per ticker (plan writer's call, from the code).** `scan_replay` is cross-sectional per decision date: `_base_day` computes breadth (`rs_factors.breadth_pct_above_50ema`), the RS cache and sector frames over all base tickers at once, and `measure_arms._produce_population` states "the replay is cross-sectional per decision date, not per ticker". A per-ticker replay would change the signals. The checkpoint unit is therefore one lane (`base`, `extra`), written atomically when the lane finishes; the window is about 45 sessions, so a lane is minutes, not hours. Layer 1 checkpoints per trade as the spec says.
- **Layer 2 frames are the adjusted watchlist store** (`history_store.load(t, "daily")`, default root) — the bars the live scan saw; only layer 1 reads the raw scratch stores.
- **Today's parameters are production's.** The run (V232-16) prints only a SHA-256 of production's `ScanParams` and its live short lanes (no `.env` value), and the CLI refuses (`--expect-params-digest`) when the local `ScanParams.from_config()` digest differs.
- **Ledger `n`.** `LEDGER_FIELDS` holds one integer `n`; the row carries the total headline scored trades and the per-direction counts live in the results doc it names.
- **`created_at`-sourced stamps (for V232-10).** A plan doc's `created_at` is a date with no time of day; without `issued_at`, `sessions.stamp_source` uses that session's close, so `issue_bucket` returns `outside_session`. V232-10 counts `created_at`-sourced live-only plans separately, never as outside-session issues (V232-5's rules).
- **V232-2 routes on plan type** beyond the ledger's one-liner: Turtle Soup goes to `gap_aware_single_leg_walk` (with `fill_bar_check=False` it walks a copy whose fill bar is flattened to the fill price); a v192 waiting plan's fill-bar check uses `market_next_open.next_open_fill_bar`; the compression short's risk-cap cancel is not re-applied.
