# v228 — Intraday MFE/MAE for the journal: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V228-5" -A 400 <part file>`); never read a part whole.

**Bump:** bot patch, ui patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-14-v228-intraday-excursion-design.md](../../specs/implemented/2026-11-14-v228-intraday-excursion-design.md)
**Brief:** `.superpowers/briefs/2026-11-14-v228-intraday-excursion.md`

## Goal

The journal's MFE, MAE and exit efficiency are computed from **daily** bars
sliced from the entry day to the exit day. That was fine when trades lived for
days. Since 2026-10-01 stops sit at 1.75–2.0% of price and 54% of LONG trades
close the day they open, so for most of the book the daily bar's range includes
price action before the fill and after the exit. Measured on production
2026-11-14, the median stored MFE of a losing LONG is 1.24R while 5-minute bars
say 0.31R; only 13 of 192 losers truly reached +1R. Everything that reads those
fields inherits the error: `exit_efficiency`, the `near_miss_tp` tag,
`_auto_lesson`, the admin exit-quality charts, the Discord trade-view chart and
every give-back read the trade scout makes from the book export.

Once this ships, every journal entry records **which bars measured it**
(`excursion_source`: `5min`, `15min`, `hourly` or `daily`). The excursion is
taken from the finest archived frame that covers the trade without holes; the
entry bar is dropped (it holds pre-fill prices), the exit bar is kept, and the
entry and exit prices are always points on the path, so a trade inside one bar
still gets a bounded answer. At close time the sub-hourly archives are up to a
day stale, so the entry is usually written from `daily`; a pass in the bot's
`market_data_refresh` loop, once per UTC date and fenced to 60 seconds in a
worker thread, upgrades entries of the last seven days as soon as finer bars
are on disk, through a conditional JSONB patch that can only move a source
finer and never touches the partner's note. A data revision labels every
existing entry `daily`, and an operator script backfills the whole book from
the VM's merge-only 5-minute archive (it starts 2026-06-23, before the first
live trade).

Readers stop trusting short daily figures: exit-quality aggregates use only
intraday-sourced entries or holds of two days or more and say how many they
left out; the admin SPA marks a short-hold daily figure `est. (daily bars)`
with a tap- and keyboard-reachable explanation on phone, tablet and desktop;
the Discord chart suffixes `(daily est.)`; the book export carries the source
as column 39 and the autopsy builds MFE-derived cells from intraday rows only,
refusing an old CSV loudly.

What it leaves alone: alerts, plans, stops, targets, lifecycle messages, the
partner's resting orders, every backtest and replay path (`exit_sim` measures
its own excursions), and `r_realized`, `outcome`, `holding_days`,
`risk_features` on existing rows. It buys no edge itself (`Edge: none
(integrity)`); it makes every later harvest read honest. Success is measured
on production after the backfill: the report line shows entries upgraded to
`5min`, and the median stored MFE of post-2026-10-01 losing LONGs moves from
about 1.24R towards the 0.31R the results doc measured.

## Architecture

- **Pure core** (`swingbot/core/analytics/mfe_mae.py`): `compute_excursion(trade,
  frames)` walks an ordered `{name: DataFrame}` mapping finest first and returns
  the first frame that passes the coverage and density rules; `compute_mfe_mae`
  becomes a thin daily wrapper. `frame_verdicts` exposes why each frame was
  skipped so the upgrade report can count `no_coverage` and `density` apart.
- **Loading** (`swingbot/core/analytics/excursion_frames.py`, new): one
  `load_frames(ticker)` that reads the archives through
  `data_store.load_normalized` and tells a missing file from an unreadable one
  (`FrameSet`). Used by `journal_trade_close`, the upgrade pass and the two
  re-journal scripts.
- **Write path**: `Repository.patch` gains an optional `where=` clause;
  `JournalRepository.patch_if_coarser` uses it so the `UPDATE` itself matches
  only while the stored `excursion_source` is coarser than the new one. No
  read-then-write, no `JournalStore.add`.
- **Upgrade pass** (`swingbot/core/analytics/excursion_upgrade.py`, new): joins
  journal entries to `TradeLog` trades by id, groups by ticker, loads frames
  once per ticker, patches only finer results, counts every skip by reason.
  Called from `market_data_refresh` (bot container) and from
  `scripts/ops/backfill_excursions.py` (per-ticker checkpoints).
- **Data revision** `v228_001` stamps `daily` on entries with a non-null
  `mfe_r` and no source; downgrade is a no-op, `ROLLBACK_SAFE` declared.
- **Readers**: `exit_quality.is_trusted` / `is_daily_estimate` are the one rule
  (source intraday, or `holding_days >= 2`); the SPA mirrors it in
  `ui/excursion-estimate.ts`; `pnl_calendar.ROW_KEYS`, the export script and the
  autopsy loader carry the field.

**Tech stack:** Python 3.11, pandas, SQLAlchemy Core + Alembic on Postgres
(JSONB `doc`), discord.py loop, matplotlib/mplfinance charts, Angular (zoneless,
signals) + vitest, bash/psql export script, pytest suites from `tests/suites.toml`.

## Global Constraints

- Frames are tried finest first: `5min`, `15min`, `hourly`, `daily`; the result's `excursion_source` is the name of the frame used.
- Coverage, intraday: first bar starts at or before `opened_at`, last bar starts at or after `closed_at` minus one bar length. `daily` covers when today's date-level slice is non-empty.
- Density: inside the slice window, two consecutive bars on the same calendar date are at most **four bar lengths** apart, else the frame is skipped like an uncovered one.
- Time basis: journal times are aware UTC ISO strings; archive indexes from `load_normalized` are naive UTC bar **starts**; trade times are converted to naive UTC before comparing; an aware frame index is converted to UTC and made naive; nothing is compared across bases.
- Slice, intraday: bar start `>= opened_at` and `<= closed_at`; the bar containing the entry is excluded, the bar containing the exit is kept.
- Anchors (intraday only): `mfe_r >= max(0, r at exit)`, `mae_r >= max(0, -r at exit)`; an empty intraday slice is answered from the anchors, never `None`.
- `daily` keeps today's arithmetic byte for byte (no anchors, empty slice → no answer); `compute_mfe_mae(trade, df)` keeps its contract.
- Exit efficiency: `r_multiple(trade) / mfe_r` clamped to `[-5, 1]` when `mfe_r > 0`; all figures rounded to 4 dp.
- No bars at all: `mfe_r`, `mae_r`, `exit_efficiency` and `excursion_source` are all `None`.
- The upgrade pass rewrites exactly six fields: `mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`, `tags`, `auto_lesson`; never downgrades; an unchanged entry is not written; writes only through `JournalRepository.patch_if_coarser`.
- Refresh-loop pass: at most once per UTC date, through `asyncio.to_thread`, 60-second budget, window = last 7 days, one `log.info` report line, any exception logged and never fails the refresh.
- Report counts: `read`, `upgraded` per source, `no_trade`, `no_file`, `unreadable`, `no_coverage`, `density`, `no_inputs`, `lost_race`, `budget_hit`; a missing file, an unreadable file and an uncovered trade are counted apart.
- Data revision `v228_001`, `down_revision` = the Alembic head when the task runs (`v208_001` on 2026-11-14; re-read with `python -m alembic heads`); downgrade is a no-op; `ROLLBACK_SAFE` names the one loss.
- Trust rule everywhere (aggregates, SPA, Discord): a figure is an estimate when `excursion_source == "daily"` and the hold is under two days (`holding_days < 2`, `held_hours < 48`).
- SPA visible marker text: `est. (daily bars)`; explanation: "Held under 2 days, intraday bars unavailable, the range may be overstated." in a tap-reachable, keyboard-focusable `sb-hint` with an `aria-label`; never hover-only.
- Execution tab caption: "n of N trades; M short holds on daily bars excluded".
- Discord chart suffix: ` (daily est.)` on the MFE and MAE annotations, charts drawn after ship only.
- Export: `excursion_source` is column 39 in **both** `UNION` branches (`NULL::text` in the plan branch); positional `ORDER BY` unchanged.
- Autopsy: MFE/MAE-derived cells from intraday-source rows only, with the dropped count printed; a 38- or 36-column CSV stops with a message naming the fix unless `--no-excursion-cells`.
- Every changed function ends at cyclomatic complexity < 15 (`scripts/dev/complexity_gate.py`); the `mfe_mae:compute_mfe_mae` baseline row is removed; `journal.tags_for` and `_auto_lesson` gain no branches.
- Tests per task with the narrow run `python scripts/dev/testrun.py file <test>`; no task runs the full suite (CI does). A task with DB tests runs `/replicate-prod-db` first, in the shared `swing-db` container.
- New tests for the excursion core live in a new `tests/excursion/` directory joined to a new `excursion` suite (V228-2); `tests/analytics/` is near `max_tests = 1200` and the limit is never raised.
- UI tasks: one page per task, checked at 390, 768 and 1440 px with `node frontend/scripts/layout-audit.mjs` (1440 is the audit's desktop width; the spec's 1280 sits inside the same desktop band).
- Production changes only under `mirror-prod`, connections only through `bash scripts/ops/ssh-hetzner.sh`.

## Review Focus

- V228-2: the entry-bar exclusion and the anchors are the no-lookahead surface; check a bar starting exactly at `opened_at` is kept (it holds no pre-fill price) and one starting a minute earlier is dropped.
- V228-3/V228-5: the rank guard must be inside the `UPDATE` statement; a test runs the coarser write after the finer one and proves a no-op.
- V228-7: `WHERE doc->>'mfe_r' IS NOT NULL AND doc->'excursion_source' IS NULL` — an explicit JSON `null` `mfe_r` (no bars at close) stays unlabelled; a later upgrade can still give it an intraday source.
- V228-16: the autopsy must refuse an old CSV, not quietly drop every MFE cell.

## OPEN (decisions the controller should check)

- The spec's Testing line says the data revision's "downgrade restores"; the body and the staff-engineer panel item make the downgrade a no-op. The plan follows the body: V228-7 tests that downgrade leaves stamped rows unchanged.
- No 5-minute or 15-minute archive exists on this machine. V228-1 pins the time basis on **real** archive rows copied read-only from the VM (AAPL, Alpaca-eligible; GC_F, Yahoo-only) into `tests/fixtures/v228/archive/`, spanning the 2026-11-01 DST change.
- `workspaces/calendar/calendar.ts` has an older drawer that also prints MFE/MAE (brief §1). Resolved: the spec (§5 and its 2026-11-14 panel line) marks it like the card, so V228-12 covers `calendar.ts` and its spec file too.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A core | V228-1 → V228-2 → V228-4 → V228-5 → V228-6, V228-8 (parallel after V228-5) | marketdata test + fixtures (1); `mfe_mae.py`, baseline, `suites.toml` (2); C `excursion_frames.py`, `journal.py`, two scripts (4); C `excursion_upgrade.py` (5); `loops.py` (6); C `backfill_excursions.py` (8) | 2 implements the time basis 1 pins (1's outcome decides whether 2 converts per frame); 4 consumes `compute_excursion` and the source constants; 5 consumes `load_frames` and 3's `patch_if_coarser`; 6 and 8 both call 5's functions, touch disjoint files, no contract between them |
| B write guard | V228-3 (parallel with V228-1/2) | `repositories/base.py`, `repositories/journal.py`, two `tests/db` files | disjoint from A; V228-5 needs it merged |
| C revision | V228-7 (parallel with anything) | C `migrations/versions/v228_001_excursion_source.py`, C its test | disjoint; only task adding a revision, so one Alembic head |
| D backend readers | V228-9 → V228-14; V228-10 parallel | `exit_quality.py`, `api_v1/analytics.py` (9); `lifecycle_embeds.py`, `trade_chart.py` (14); `pnl_calendar.py` + 3 contract tests (10) | 14 imports 9's `is_daily_estimate`; 10 is disjoint from both |
| E SPA | V228-11 → (V228-12 ∥ V228-13) | `models.ts`, C `ui/excursion-estimate.ts`, trade-detail store/template (11); `day-trade-card.ts` (12); `analytics/tabs/execution.ts` (13) | 12 and 13 consume 11's `models.ts` fields and `sb-excursion-est`; only 11 edits `models.ts`. E reads the JSON shapes of V228-9/10 but its fields are optional, so it may start beside D |
| F export | V228-15 → V228-16 | `export_book_rows.sh`, `autopsy/rows.py` + 2 scout tests (15); `rows.py`, `exits.py`, `report.py`, `book_autopsy.py`, scout fixtures, trade-scout skill (16) | 16 edits `rows.py` after 15 and needs column 39 in place |
| G production | V228-17 | VM only, plus the mirror note in this plan's `## Handoff` | last: needs every task merged, CI green and the image built; the revision (7), the pass (6) and the script (8) must all be in the deployed image |

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V228-1 | Pin the archive time basis on real Yahoo and Alpaca archive rows | 1 | sonnet | C `tests/fixtures/v228/archive/{5min,15min,hourly}/{AAPL,GC_F}.csv` (rows copied read-only from the VM, sessions 2026-10-30 and 2026-11-03); C `tests/marketdata/test_archive_time_basis.py` | The verdict `ARCHIVE_TIME_BASIS_OK` recorded in the task's commit message: `load_normalized` returns naive-UTC bar starts for every fixture, mixed offsets → `None`; if a provider fails, V228-2 converts that frame (contract stays the same either way) |
| V228-2 | `compute_excursion` with coverage, density, slice and anchors; `compute_mfe_mae` as a wrapper | 1 | opus | M `swingbot/core/analytics/mfe_mae.py`; M `scripts/dev/complexity_baseline.json` (drop `mfe_mae:compute_mfe_mae`); M `tests/suites.toml` (new `[suites.excursion]` with `paths = ["tests/excursion/"]`); C `tests/excursion/__init__.py`; C `tests/excursion/test_compute_excursion.py` | `EXCURSION_SOURCES = ("5min", "15min", "hourly", "daily")`; `INTRADAY_SOURCES = ("5min", "15min", "hourly")`; `BAR_MINUTES = {"5min": 5, "15min": 15, "hourly": 60}`; `source_rank(source: str \| None) -> int` (5min 0 … daily 3, None/unknown 4); `coarser_sources(source: str) -> tuple[str \| None, ...]` (sources ranked coarser, then `None`); `frame_verdicts(trade: dict, frames: Mapping[str, pd.DataFrame \| None]) -> dict[str, str]` (values `"ok"`, `"empty"`, `"coverage"`, `"density"`, `"unsupported"`; `{}` when the trade has no usable risk or dates); `compute_excursion(trade: dict, frames: Mapping[str, pd.DataFrame \| None]) -> dict \| None` (keys `mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`); `compute_mfe_mae(trade, df) -> dict \| None` unchanged contract |
| V228-2b | `compute_mfe_mae` becomes the wrapper over `compute_excursion`; baseline row dropped; parity and edge-case tests | 1 | opus | M `swingbot/core/analytics/mfe_mae.py`; M `scripts/dev/complexity_baseline.json` (drop `mfe_mae:compute_mfe_mae`); M `tests/excursion/test_compute_excursion.py` | `compute_mfe_mae(trade, df) -> dict \| None` unchanged contract, now delegating to `compute_excursion(trade, {"daily": df})` |
| V228-3 | Conditional `Repository.patch(where=)` and `JournalRepository.patch_if_coarser` | 1 | sonnet | M `swingbot/core/db/repositories/base.py`; M `swingbot/core/db/repositories/journal.py`; M `tests/db/test_repository_base.py`; M `tests/db/test_journal_repository.py` | `Repository.patch(self, key_value, changes: dict, *, conn=None, where: sa.ColumnElement[bool] \| None = None) -> dict \| None` (`where` ANDed into the `UPDATE`; `None` when no row matched, missing or guarded); `JournalRepository.patch_if_coarser(self, trade_id: str, changes: dict, *, coarser: tuple[str \| None, ...], conn=None) -> dict \| None` (matches only while `coalesce(doc->>'excursion_source', '')` is in `coarser`, `None` mapped to `''`) |
| V228-4 | Frames loader; `build_entry`/`journal_trade_close` take frames and record `excursion_source`; both re-journal scripts | 1 | opus | C `swingbot/core/analytics/excursion_frames.py`; M `swingbot/core/analytics/journal.py`; M `scripts/data/backfill_journal.py`; M `scripts/ops/rejournal_fill_mismatch.py` (`EXIT_FIELDS` gains `excursion_source`); C `tests/excursion/test_excursion_frames.py`; M `tests/analytics/test_journal.py`; M `tests/analytics/test_journal_risk_features.py`; M `tests/tracking/test_origin.py`; M `tests/scripts/test_rejournal_fill_mismatch.py` | `@dataclass(frozen=True) class FrameSet: frames: dict[str, pd.DataFrame]; missing: tuple[str, ...]; unreadable: tuple[str, ...]`; `load_frames(ticker: str, *, daily: pd.DataFrame \| None = None, daily_from_archive: bool = False, base_dir: str = DATA_DIR) -> FrameSet` (intraday names in `INTRADAY_SOURCES` order, then `daily`); `build_entry(trade: dict, frames: Mapping[str, pd.DataFrame \| None] \| None) -> dict` (adds `"excursion_source"`); `journal_trade_close(trade)` loads `load_frames(ticker, daily=get_daily_data(ticker))` |
| V228-5 | `upgrade_excursions`: join trades, finer-only conditional patch, report | 5 | opus | C `swingbot/core/analytics/excursion_upgrade.py`; C `tests/excursion/test_excursion_upgrade.py` | `@dataclass class UpgradeReport` (fields `read`, `upgraded: dict[str, int]`, `no_trade`, `no_file`, `unreadable`, `no_coverage`, `density`, `no_inputs`, `lost_race`: int; `budget_hit: bool`; `line() -> str`; `as_dict() -> dict`; `absorb(counts: dict) -> None`); `pending_by_ticker(since: str \| None, until: str \| None = None) -> dict[str, list[tuple[dict, dict \| None]]]` (entry, trade-or-None; only entries with `source_rank(excursion_source) > 0`); `upgrade_ticker(ticker: str, pairs: list[tuple[dict, dict \| None]], report: UpgradeReport, *, base_dir: str = DATA_DIR, deadline: float \| None = None) -> bool` (False when `time.monotonic()` passed `deadline`); `upgrade_excursions(since: str \| None, until: str \| None = None, *, budget_seconds: float \| None = None, base_dir: str = DATA_DIR) -> UpgradeReport` |
| V228-6 | Run the pass from `market_data_refresh`: once per UTC date, worker thread, 60 s budget | 2 | sonnet | M `swingbot/commands/scanning/loops.py`; M `tests/commands/test_market_data_refresh_task.py` | `loops.EXCURSION_PASS_DAYS = 7`; `loops.EXCURSION_PASS_BUDGET_S = 60.0`; `loops._EXCURSION_PASS_DATE: dt.date \| None`; `async def loops._run_excursion_pass(today: dt.date \| None = None) -> None` |
| V228-7 | Data revision `v228_001`: stamp `daily` on rows with `mfe_r` and no source | 2 | opus | C `swingbot/core/db/migrations/versions/v228_001_excursion_source.py`; C `tests/db/test_v228_excursion_source_migration.py` | revision `v228_001` (the single head); `ROLLBACK_SAFE` string mentioning `excursion_source` |
| V228-8 | Operator script `backfill_excursions.py` with per-ticker checkpoints | 2 | sonnet | C `scripts/ops/backfill_excursions.py`; C `tests/scripts/test_backfill_excursions.py` | `FINGERPRINT = "v228-excursion-backfill-1"`; `run(checkpoint_dir: Path, *, since: str \| None = None, base_dir: str = DATA_DIR) -> UpgradeReport`; `main(argv: list[str] \| None = None) -> int`; CLI `--checkpoint-dir` (default `logs/backfill_excursions.ckpt`), `--report-file` (default `logs/backfill_excursions.report.txt`), `--since`; prints `resuming: n/N tickers restored` then one final `excursion upgrade: …` line |
| V228-9 | Exit-quality trust rule, per-source counts, endpoint `excursion` block | 2 | sonnet | M `swingbot/core/analytics/exit_quality.py`; M `swingbot/admin/api_v1/analytics.py` (`analytics_exit_quality`); M `tests/analytics/test_exit_quality.py`; M `tests/admin/test_api_v1_analytics.py` | `exit_quality.TRUSTED_MIN_HOLD_DAYS = 2.0`; `is_trusted(entry: dict) -> bool`; `is_daily_estimate(entry: dict) -> bool` (`source == "daily"` and `holding_days < 2`); `excursion_summary(entries: list[dict]) -> dict` = `{"sources": {name or "none": int}, "included": int, "excluded": int, "total": int}`; scatter points gain `"excursion_source"`; endpoint JSON gains `"excursion"` (efficiency, mae and scatter built from trusted entries) |
| V228-10 | `excursion_source` in `pnl_calendar.ROW_KEYS` and the three contract tests | 2 | haiku | M `swingbot/core/analytics/pnl_calendar.py`; M `tests/analytics/test_pnl_calendar.py`; M `tests/admin/test_api_v1_calendar.py`; M `tests/admin/test_api_journal.py` (`_ENTRY_SHAPE`) | calendar rows carry `"excursion_source": str \| None` |
| V228-11 | SPA trade detail: shared `sb-excursion-est`, models, `estimate` flag on MFE/MAE/efficiency | 3 | sonnet | M `frontend/src/app/api/models.ts` (`JournalEntry.excursion_source?`, `CalendarTrade.excursion_source?`, `AnalyticsExitQuality.excursion?`); C `frontend/src/app/ui/excursion-estimate.ts`; C `frontend/src/app/ui/excursion-estimate.spec.ts`; M `frontend/src/app/stores/trade-detail.store.ts`; M `frontend/src/app/stores/trade-detail.store.spec.ts`; M `frontend/src/app/workspaces/trades/trade-detail.ts`; M `frontend/src/app/workspaces/trades/trade-detail.spec.ts` | `EXCURSION_EST_LABEL = 'est. (daily bars)'`; `EXCURSION_EST_EXPLANATION`; `isDailyEstimate(source: string \| null \| undefined, heldDays: number \| null \| undefined): boolean`; component `ExcursionEstimate` (selector `sb-excursion-est`, no inputs); `AnalyticsExitQuality.excursion?: { sources: Record<string, number>; included: number; excluded: number; total: number }` |
| V228-12 | SPA calendar day card: marker inside the `MFE · MAE` line | 3 | sonnet | M `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`; M `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts`; M `frontend/src/app/workspaces/calendar/calendar.ts`; M `frontend/src/app/workspaces/calendar/calendar.spec.ts` (older drawer, same marker) | `rowIsEstimate(trade: CalendarTrade): boolean` exported from `day-trade-card.ts` |
| V228-13 | SPA analytics execution tab: exclusion caption and verdict hint | 3 | sonnet | M `frontend/src/app/workspaces/analytics/tabs/execution.ts`; M `frontend/src/app/workspaces/analytics/tabs/execution.spec.ts` | — |
| V228-14 | Discord trade-view chart: `(daily est.)` suffix | 3 | opus | M `swingbot/core/scanning/lifecycle_embeds.py` (`_excursion_markers` helper split out of `regenerate_chart_for_trade`); M `swingbot/core/charts/trade_chart.py`; M `tests/charts/test_plan_chart_overlays.py`; C `tests/scanning/test_v228_chart_markers.py` | markers dict gains `"estimate": bool` |
| V228-15 | Export column 39 `excursion_source` and the autopsy column contract | 4 | sonnet | M `scripts/ops/export_book_rows.sh`; M `scripts/reports/autopsy/rows.py` (`EXPORT_COLUMNS`, `PRE_EXCURSION_COLUMNS`, `BookRow.excursion_source`); M `tests/scout/test_export_script.py`; M `tests/scout/test_autopsy_rows.py` | `rows.EXCURSION_COLUMN = "excursion_source"`; `rows.EXPORT_COLUMNS` (39, last is `excursion_source`); `rows.PRE_EXCURSION_COLUMNS = EXPORT_COLUMNS[:-1]` (38); `rows.LEGACY_EXPORT_COLUMNS` (36, unchanged value); `BookRow.excursion_source: str \| None = None` |
| V228-16 | Autopsy: intraday-only MFE cells, drop count, loud refusal, `--no-excursion-cells` | 4 | sonnet | M `scripts/reports/autopsy/rows.py` (`load_rows(..., allow_no_excursion=False)`, `MissingExcursionColumn`); M `scripts/reports/autopsy/exits.py`; M `scripts/reports/autopsy/report.py`; M `scripts/reports/book_autopsy.py`; M `tests/scout/test_autopsy_exits.py`; M `tests/scout/test_book_autopsy.py`; M `tests/scout/test_autopsy_rows.py` | `rows.INTRADAY_SOURCES`; `class MissingExcursionColumn(ValueError)`; `exits.giveback_summary(trades) -> {"n", "mean", "median", "dropped"}` |
| V228-16b | Skills aligned: trade-scout and exit-harvester name the intraday-only MFE cells; skill pin test; Codex mirror | 4 | haiku | M `.claude/skills/trade-scout/SKILL.md`; M `.claude/skills/exit-harvester/SKILL.md`; M `tests/scout/test_trade_scout_skill.py`; M `.agents/skills/` mirror via `python scripts/dev/sync_codex.py` | — |
| V228-17 | Production: PITR-drill check, deploy, timeframes check, detached backfill, read-back, mirror | 4 | opus | M `docs/superpowers/plans/2026-11-14-v228-intraday-excursion_0-index.md` (`## Handoff` production record) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-14-v228-intraday-excursion_1-core.md` | V228-1 .. V228-4 (incl. V228-2b) | time-basis pin; `compute_excursion` and the wrapper; conditional patch; frames loader and journal |
| 2 | `2026-11-14-v228-intraday-excursion_2-wiring.md` | V228-6 .. V228-10 | refresh-loop hook; data revision; backfill script; exit-quality rule; calendar row keys |
| 3 | `2026-11-14-v228-intraday-excursion_3-readers.md` | V228-11 .. V228-14 | SPA trade detail, calendar day card, execution tab; Discord chart suffix |
| 4 | `2026-11-14-v228-intraday-excursion_4-export-and-prod.md` | V228-15 .. V228-17 (incl. V228-16b) | export column 39; autopsy refusal and intraday cells; production run under `mirror-prod` |
| 5 | `2026-11-14-v228-intraday-excursion_5-upgrade.md` | V228-5 | upgrade pass — moved out of part 1 for the 1500-line cap; runs after V228-4, before V228-6/V228-8 |

## Handoff

- 2026-11-15, plan writing: V228-2 split into V228-2 (add `compute_excursion`) and V228-2b (wrapper, baseline row, parity tests) — first draft was 24 KB. Ledger is 18 rows.
- 2026-11-15: V228-5 moved to its own file `_5-upgrade.md` (part 1 would have reached 1708 lines). Execution order is unchanged: after V228-3 and V228-4, before V228-6 and V228-8.
- 2026-11-15, V228-9 decision (part 2): a `daily` entry with missing or NaN `holding_days` counts as a short hold — `is_daily_estimate` True, `is_trusted` False; the SPA `isDailyEstimate` matches. `excursion.excluded` counts only short daily holds.
- 2026-11-15, V228-6: the UTC date is stamped before the pass runs, so a failed or budget-hit pass retries the next day, not the same day.
- 2026-11-15, V228-7 adds no `INCOMPATIBLE_BOUNDARIES` entry (`rollback_plan.py` is not in the ledger; downgrade is a tested no-op).
- 2026-11-15, V228-5: a skipped entry is classed by why the `5min` frame failed (the finest frame any pending entry can reach). `UpgradeReport()` builds all-zero; `as_dict()`/`absorb()` round-trip the dict V228-8 (part 2 header) spells out.
- V228-1 facts from a read-only production check: archive CSV header `Datetime,Close,High,Low,Open,Volume`, every row `+00:00`; per-session rows AAPL 156/52/14, GC_F 528/176/44 (5min/15min/hourly).
- 2026-11-15, V228-12: also edits `calendar.ts`/`calendar.spec.ts` so the older drawer carries the marker (spec §5); adds the exported helper `rowIsEstimate(trade)`.
- 2026-11-15, V228-13 caption: "n of N trades; M short holds on daily bars excluded", plus "; K without excursion figures" when `total - included - excluded > 0`; verdict hint `N=<n> · M short holds on daily bars excluded`.
- 2026-11-15, V228-14: label text moves into a new `_marker_label` helper; `generate_trade_chart` complexity goes 191 -> 190 and `complexity_baseline.json` is left alone.
- 2026-11-15, V228-16 split: V228-16b holds the trade-scout and exit-harvester skill edits, the skill pin test and `sync_codex.py` (mirror lives under `.agents/skills/`, not `.codex/`). Ledger is 19 rows. V228-16 also edits `tests/scout/test_autopsy_rows.py` (the refusal flips its two old-header tests).
- 2026-11-15, V228-16: `rows.INTRADAY_SOURCES` is a literal pinned by test to `mfe_mae.INTRADAY_SOURCES`, so V228-16 needs V228-2 merged first. The autopsy drops a `daily` row whatever its hold (source only); `exclusions.py` keeps the default and also refuses old CSVs.
- 2026-11-15, V228-17: the PITR check and the "before" snapshot (Steps 1-5) run BEFORE the v228 merge is pushed -- the push is the deploy and applies `v228_001`. If already pushed, the task records a late check here and carries on.
- 2026-11-17, V228-17 production (mirror-prod): `main` was already pushed (the merge's first deploy run failed CI on 3 jobs, nothing deployed); fixed by b9aa3899 (gallery lists `sb-excursion-est`), b8ff1dd1 (two new broad excepts through `swallowed()`), 10bd4451 (complexity baseline 191 -> 190) and 206f5c5a (two tests patched `log.exception`, now `log.error`); deployed `main` 206f5c5a (CI run 44117413049). Last PITR drill 2026-10-01 PASS, `pgbackrest info` status ok, newest backup 2026-11-17 (diff); rollback target T0 = 2026-11-17T15:36:46Z (`scripts/ops/rollback_to.sh`; the first deploy that applied v228_001 was the run for 206f5c5a, a few minutes later). `alembic current` = v228_001; v228_001 labelled 1065 rows `daily`, 0 unlabelled. The "before" snapshot was taken after the deploy, before the backfill (the revision does not touch notes). Timeframes TIMEFRAMES_OK; 5min archive 92 files from 2026-06-23. Backfill `scripts/ops/backfill_excursions.py` run detached in `bot`, about 2 min (15:48-15:50Z); report: `excursion upgrade: read 1132, upgraded 5min=968 15min=0 hourly=40 daily=0, no_trade 12, no_file 10, unreadable 0, no_coverage 1, density 0, no_inputs 0, lost_race 101, budget_hit no`. Sources after: 5min 1060, hourly 49, daily 15, (none) 8. LONG last-leg losers since 2026-10-01: N 187 -> 209, median stored MFE 1.18 -> 0.21 R, reached +1R 101 -> 14. Notes fingerprint unchanged (2 notes). Refresh-loop pass line seen 2026-11-17 15:49:17 (`read 115 ... budget_hit yes`: it resumes on the next UTC date). Follow-up, not a v228 fault: one cached frame, CRM hourly, has an unparseable index (`data_store._normalize_cached`, tz-aware datetime without utc=True); it was logged, skipped and counted. No file on the VM edited by hand; no `.env` change.
- 2026-11-17, close-out panel (quant-engineer, staff-engineer, ux-designer) over 1fcf7edf..a2c7db93: no BLOCKING from any seat; 19 ADVISORY carried as follow-ups, none applied here. Highest value: (1) `opened_at` is the placeholder-trade log time for stop_entry/limit plans, so the intraday slice may include pre-fill bars (quant-engineer; check `activated_at` and the share of such trades in the 1132 backfilled entries before trusting the 209-loser figure); (2) a missing whole session in a multi-day hold passes the density check (`mfe_mae._dense`); (3) an empty-slice result is labelled by its bar size and counted trusted; (4) the refresh pass walks tickers in name order under a 60 s budget and never resumes (`budget_hit yes` on its first run), so late-alphabet tickers can starve; (5) a closed trade's cached `_view.png` keeps the daily figures and suffix after an upgrade; (6) `store.add` in `journal_trade_close` and `rejournal_fill_mismatch.py` can write a coarser source over an upgraded entry; (7) the CRM hourly frame has no owner. UX: the analytics tile hint says "0 short holds" when none, three identical markers in the trade-detail grid, 14 px hint trigger, and the web label "est. (daily bars)" differs from the Discord "(daily est.)". The UX widths were reviewed statically, not measured at 390/768/1280.
- 2026-11-17, closed out: `Bump:` held (bot patch 2.19.2, ui patch 1.44.1); `Edge:` held; skills: none affected beyond V228-16b (trade-scout, exit-harvester, Codex mirror already shipped).
