# v209 — Market-shock detector (shadow), Track 1 (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (main @ 437dd4d5; the spec's closing *Plan-briefer reconciliation* paragraph overrides earlier spec text; § What changes → *Plans* puts Track 1 in this plan and Track 2 in a separate one)
**Amended:** A1 (2026-11-10), [A1 index](2026-11-05-v209-market-shock-detector-a1_0-index.md): entry rule re-registered (`depth_frac`, sustained breadth; `SHOCK_SECTORS_FRAC` removed), validation set and one-shot acceptance. Its ledger (V209-A1-1..A1-4) runs before V209-13; superseded text below is marked, not rewritten.
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` (code context for every part; §5 D1–D8 and §7 T1–T18 are the traps; the Track 2 sections of the brief are not used by this plan)

## Goal

On 2026-11-05 the live book closed 26 trades for −13.9R, its worst day of the
last 25: the market turned at about 14:36 UTC, the bot kept buying memory and
chip names (18 longs after the turn, MU five times), and most stops sat inside
normal price movement. The partner asked the bot to stop buying and start
shorting when the market turns sharply, and to watch price and VIX to know
when to switch back. The live-book counterfactuals that motivated it are
in-sample over about 84 effective days, so they justify a **measurement, not
a gate**: this plan builds that measurement (Track 1 of the spec).

Once it ships, every scheduled scan pass in NYSE regular hours takes one
**reading** of the watchlist (share of equities down at least 1 ATR from the
prior close, sectors down, the speed of that drop, SPY/QQQ ATR moves, VIX
level and change) and steps a **NORMAL → SHOCK → RECOVERY → NORMAL** state
machine with hysteresis, minimum dwells, an open-settle rule and a cheap
second-leg re-entry. The state is stored in two new tables, and every new
plan's `entry_context` gains `shock_state` (so the live book can measure
shock cohorts directly). Notices and admin badge: plan v210 (the
`market_shock` ops-channel notice and the tape badge, carved out of this plan
at the 20-task cap; it follows this one and consumes its contracts).
In `shadow` mode, which is the default and the only meaning `live` has in
this spec, **no trade changes**: no long blocked, no short issued, no stop
moved. `MARKET_SHOCK_MODE=off` is a byte-identical kill switch.

**Track 2 is a separate plan.** The two pre-registered one-shot screens
(`shock_support_break_short`, `shock_failed_bounce_short`, family
`shock_breakdown`), the screen runner's `CONTEXT_KIND = "level"` path, the
`BREADTH_ATR1` / `^VIX` context files, the `listing()` exclusion and the
results/ledger rows are built by the Track 2 plan, written later under the
next free number (v211 or later) with its `**Spec:**` line pointing at the
same spec. It neither depends on this plan nor blocks it, and it owns the
`/close-out` of the spec itself; this plan's close-out moves only the v209
plan files.

What it leaves alone: every trade decision, sizing, stops, alert embeds, the
two existing notify-queue kinds, `edge/context.py:FEATURE_KEYS`, the screen
runner and every idea module, the `COHORT_UNKNOWN` defect, and the closed
pre-registrations (v17 P2a, v34, v191, v104 Part B, v182).

Success is measured by tests and by production, not by ExpR
(`Edge: none (integrity)`): the detector replayed over the frozen 2026-11-05
fixture reaches SHOCK no later than 15:00 UTC (the earliest the
open-settle and two-reading rules allow); every transition, hysteresis
band, dwell and carry case is pinned; long and short plans are byte-identical
under `off` and differ only by `entry_context.shock_state` under `shadow`;
`!check`, the recap, the admin-UI scan and the SHORT lane never write a
reading; after the deploy, `market_shock_readings` gains about 28 rows per
full session on production.

## Architecture

- **Pure detector** (V209-2..V209-4): `swingbot/core/market/shock.py`, no I/O
  and no config import; frozen dataclasses in, frozen dataclasses out;
  `measure` builds a reading from a snapshot and the previous reading;
  `step` is table-driven, one rule function per transition, every function
  < 15.
- **Config** (V209-1): new "Market Shock" section in `swingbot/config.py`:
  `MARKET_SHOCK_MODE` (select `off|shadow|live`, default `shadow`) and 18
  numeric fields, all hot-reloadable.
- **Persistence** (V209-5, V209-5b): Alembic `v209_001` on `v197_001`;
  tables `market_shock_state` (single row) and `market_shock_readings`, both
  with `PROMOTION_REASONS` entries (V209-5); `MarketShockRepository.record()`
  writes reading + state (+ optional notice event in the v197 queue) in one
  transaction, and the nightly `daily_recap` prunes readings older than
  `SHOCK_READINGS_KEEP_DAYS` (V209-5b).
- **Shock pass** (V209-6): new `swingbot/core/scanning/shock_scan.py` holds
  every wiring decision (NYSE-regular-hours gate, snapshot from frames + live
  quotes + sector map, no quote fetch of its own, VIX from the
  tape, measure/step/record, current label).
- **Scan wiring** (V209-6b, V209-6c): `_sync_run_scan` gains one `quotes_at`
  line and one guarded call line (`_shock_state_for_pass`, `None` on a raise),
  no branch; `run_scan(*, step_shock=False)`; only `loops.py:252` passes
  `step_shock=True`. V209-6c appends SPY and QQQ to the scan's one existing
  live-price fetch on stepped passes and hides them from every other
  consumer of `live_prices`.
- **Plan stamp** (V209-7, V209-8): the label travels as an argument
  (`shock_state`) through `_attach_item_plan`, `_rebuild_item`,
  `_maybe_run_strategy_pass`'s `asof_of`, `attach_plan_v2`, and
  `QualifyContext` (SHORT lane: from the lane dict);
  `params.stamp_entry_context` merges it into `entry_context` after the
  feature dict. Never in `FEATURE_KEYS`.
- **Notices and admin badge:** plan v210 (the `market_shock` queue kind and
  notice, the tape API `shock` object, the SPA badge).
- **Replay** (V209-12): a frozen 2026-11-05 fixture (Alpaca 15-minute bars,
  synthetic fallback recorded as such) replayed through `measure`/`step`.
- **Release** (V209-13): production checks, rollback doc line, bump, deploy
  in `shadow`.
- **Close-out** (V209-14): `/panel` with the spec's three roles over the
  merged diff, then `/close-out` without a second bump.

**Tech stack:** Python 3.11, SQLAlchemy + psycopg 3, Alembic, discord.py,
Flask, pandas/numpy, pytest.

## Global Constraints

- **No trade changes.** `shadow` and `live` behave identically in this plan. No long is blocked, no short issued, no stop moved, no plan's levels, size or status altered by the detector.
- **LONG issuing is unchanged on every day (partner, 2026-11-06).** This plan exists to measure for SHORT work; on a bullish or any other day the long lane issues exactly the plans, alerts, sizes and timings it issues today. Concretely: (a) long plans differ from pre-v209 only by the `entry_context["shock_state"]` record key under `shadow`/`live` and not at all under `off` (V209-8b pins it); (b) the shock pass adds **no network call of its own** to the scan's path before the plan builders: SPY and QQQ quotes ride the scan's existing one batched live-price fetch, only in the last chunk's free room so the chunk count never changes (V209-6c), and a pass that finds SPY unquoted records the reading without it instead of fetching (V209-6a); (c) a shock pass that raises or whose store is down leaves the scan's long plans byte-identical to a scan with the pass stubbed to `None` (V209-8b pins it); (d) nothing downstream of the plan builders (gates, ranking, heat, alert posting) reads `shock_state` in this plan.
- **`MARKET_SHOCK_MODE=off` is a byte-identical kill switch:** no reading, no state write, no notice, no `entry_context["shock_state"]` key (absent, not `None`). Unknown mode values fall back to `off`. The nightly prune is retention, not detector behaviour: it trims old rows in every mode.
- **`shock_state` is never added to `swingbot/core/edge/context.py:FEATURE_KEYS`** and never stamped by `entry_context()` itself; it is merged into `plan.entry_context` by `params.stamp_entry_context` after the feature dict is built, and also after a feature-build failure (so `{"shock_state": ...}` survives T3's `entry_context = {}` fallback).
- **Only the scheduled `session_scan` steps the state** (`loops.py:252`, `step_shock=True` keyword), and only while **`swingbot/core/market/session.py:is_nyse_regular_session(now)`** is true (the spec's `is_regular_session` window narrowed to skip NYSE holidays and stop at a half-day close, because on those days the "live" quote is the last close and a zero-move reading would walk SHOCK into RECOVERY). Never gate on `data.is_us_market_active()`, `bot_core.in_session()` or plain `is_regular_session`. `!check` (`commands.py:199`), the recap (`recap.py:104`), the admin-UI scan (`loops.py:489`) and the SHORT lane read the stored label and never write.
- **`run_scan` takes `step_shock: bool = False` by keyword only.** `_sync_run_scan` (CC 94), `_session_scan_tick` (CC 15), `attach_plan_v2` (12) and `_maybe_run_strategy_pass` gain **no branch**; all logic lives in `shock_scan.py` / named helpers.
- **`run_shock_pass` takes `spy_df: pd.DataFrame | None = None`** (`_sync_run_scan` passes its `spy_df = fresh_data.get(config.MARKET_REGIME_TICKER)`; `None` ⇒ the SPY row comes from `frames` when present). `run_shock_pass` **never fetches**: on a stepped pass SPY and QQQ ride the scan's one batched live-price call (`shock_scan.quote_tickers`, V209-6c), and a benchmark still absent from the fresh quotes gives its row `last=None`, so the reading is recorded with `spy_*`/`qqq_atr_move` `None` from breadth, sectors and VIX (V209-6a). `_sync_run_scan` calls it through `scan_run._shock_state_for_pass`, which returns `None` if it ever raises (V209-6b).
- **Planning never reads the shock repository.** The SHORT lane reads the stored label once per run through the lane dict: `short_run._lane_state(...)` adds `"shock_state": shock_scan.current_label()`, and `_qualify_context(require_confirmation, frames, lane)` passes `lane.get("shock_state")` into `QualifyContext.shock_state`.
- **Labels** are exactly `"NORMAL"`, `"SHOCK"`, `"RECOVERY"` (`shock.LABELS`). The db layer imports nothing from `swingbot/core/market`, so the repository restates the three labels and a test pins them equal to `shock.LABELS`. No row stored yet ⇒ `current_label()` returns `"NORMAL"` under `shadow`/`live`, `None` under `off`.
- **The repository stores the full `ShockReading.as_row()` in each reading's `doc`** (and `{"state": ShockState.as_row()}` in the state row's `doc`), because a `None` promoted column would otherwise vanish on merge; promoted columns are copies for querying.
- **Reading rules (spec § The reading):** `breadth_frac` = share of contributing equities with `(last − prev_close) / atr14 ≤ −atr_k`, where a name is an equity **only if `swingbot/core/marketdata/asset_class.classify(ticker) == "equity"`** (ETFs, indices, futures, FX and crypto never count); `sectors_down` counts sectors with ≥ 2 contributing members whose median ratio ≤ −atr_k; `sectors_total` counts sectors with ≥ 2 contributing members; the depth clause needs `sectors_total ≥ 1` and `sectors_down ≥ ceil(sectors_frac × sectors_total)` (**superseded by A1:** `depth_frac ≥ 0.50` with breadth ≥ 0.40, or breadth ≥ 0.50 alone); `breadth_speed` only within the same session, else `None`; names with < 15 completed bars or no fresh live quote are excluded; `n_names < min_names` ⇒ `insufficient=True` and `step` returns the state unchanged.
- **"Last" is the pass's live quote** (`live_prices`), never the frame's last bar. `live_prices` carry no timestamp, so the pass records `quotes_at` right after `fetch._fetch_live_prices` returns; when `now − quotes_at > SHOCK_QUOTE_MAX_AGE_S` every quote is treated as absent. `prev_close` is the close of the last **completed** session's bar (bar[-2] when bar[-1] is dated today in `US_MARKET_TZ`, else bar[-1]); `atr14` = `indicators.atr(completed_bars, 14)` last value.
- **Entry from NORMAL** needs the condition on **two consecutive** readings, and a reading with `minutes_since_open < SHOCK_OPEN_SETTLE_MIN` resets the streak to 0 and never counts. The open-settle rule also applies to RECOVERY → SHOCK re-entry; re-entry needs one qualifying reading, and "new SPY session low" needs an earlier reading in the same session.
- **VIX:** read from the tape's `^VIX` row via `read_tape` (never fetches); a row older than `SHOCK_VIX_MAX_AGE_S` or missing ⇒ `vix_*` fields `None`. Prior VIX close = `price / (1 + change_pct/100)`. Session high = running max of readings this session. Missing VIX never blocks entry into SHOCK; it leaves the RECOVERY VIX clause unmet.
- **RECOVERY → NORMAL** needs the RECOVERY conditions to hold on every reading for `RECOVERY_MIN_DWELL_MIN`; a reading where they fail resets the hold clock (`ShockState.hold_since = None`) without leaving RECOVERY unless a re-entry rule fires.
- Notice copy, rate limit, routing, the tape `shock` object and the badge rules: plan v210's Global Constraints. This plan's `MarketShockRepository.record(notice_event=)` keeps the hook v210 uses.
- **The two existing queue kinds are untouched** (`trade_closed`, `plan_transition`): their validators, renderers and tests do not change.
- **Revision id `v209_001`, `down_revision = "v197_001"`**, file `swingbot/core/db/migrations/versions/v209_001_market_shock.py`; working `downgrade()` dropping both tables; exactly one Alembic head. Neither table joins `TABLE_CHANNELS` (no SSE).
- **No screen-runner, idea-module, context-file or ledger change** in this plan: those are Track 2's plan. `PARITY_DIGESTS` and `test_long_byte_identical.py` are not touched.
- Every function written or changed < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py`); no legacy function's CC rises.
- Narrow test runs only: `python scripts/dev/testrun.py file <test>`. **No task runs the full suite**; CI does after the push. A task whose tests reach Postgres runs `/replicate-prod-db` first (one shared `swing-db` container, port 56789, `.env` credentials never printed). Every new test file sits in an existing `tests/` directory, so `tests/suites.toml` is unchanged.
- `.env` values are read, never printed; production is reached only through `bash scripts/ops/ssh-hetzner.sh`.
- Commit steps run on the plan's worktree branch, never on `main`.

## Review Focus

1. **Stale bars outside regular hours.** A pass at 08:00 ET (inside `is_us_market_active()`), at 22:00 Berlin (inside `in_session()`), on an NYSE holiday or after a half-day close must not write a reading. Owner: V209-6 (gate), V209-6b (only `loops.py:252` steps).
2. **Overnight carry.** The first reading of a new session has `breadth_speed=None`, a new `vix_session_high`, a new SPY prior close; a gap-up repair reaches RECOVERY, a second leg down stays SHOCK. Owner: V209-4.
3. **Kill switch.** Under `off`, a plan built by each of the three lanes and both rebuild paths has no `shock_state` key and is byte-identical to the pre-v209 plan. Owner: V209-7, V209-8, V209-8b.
4. **Second-leg notice** — moved to plan v210 (its Review Focus 1).
5. **One transaction.** Reading, state row and notice event commit together or not at all; a failing enqueue leaves no reading. Owner: V209-5b.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A config | V209-1 | `config.py`, `.env.example`, `tests/test_config_v209_keys.py` | none; may start at once |
| B detector | V209-2 → V209-2b → V209-3 → V209-4 | `swingbot/core/market/shock.py` + `tests/market/test_shock_*.py` | one module: 2b adds `measure` to 2's types, 3 adds `step` entry rules, 4 adds the exit/carry rules to 3's table |
| C storage | V209-5 → V209-5b | `schema.py`, migration, `repositories/market_shock.py`, `loops.py` (`daily_recap` prune), `tests/db/*` | 5b's repository reads 5's tables; may run beside A and B (contract in the ledger) |
| D wiring | V209-6 → V209-6a → V209-6b → V209-6c → V209-7 → V209-8 → V209-8b | `shock_scan.py`, `scan_run.py`, `loops.py:252`, `analyze.py`, `params.py`, `strategy_pass.py`, `qualify.py`, `short_run.py` | 6 needs A, B and 5b's repository; 6b edits `scan_run.py` and `loops.py` after 6 (and after 5b, which also edits `loops.py`); 6c edits `shock_scan.py` and the same `_sync_run_scan` lines after 6b and extends 6b's test file; 7 edits `scan_run.py` after 6c and consumes 6b's `shock_state` local; 8 consumes 6's `current_label` and 7's `stamp_entry_context` merge |
| G replay | V209-12 → V209-12b | `scripts/data/build_shock_replay_fixture.py`, `tests/fixtures/shock_replay_2026_11_05.json`, `tests/market/test_shock_replay_2026_11_05.py`, `tests/scripts/test_build_shock_replay_fixture.py` | needs B complete; may run beside C and D |
| H release | V209-13 | `docs/deploy/DEPLOY_HETZNER.md`, `VERSION.json`, `swingbot/admin/version_history.json` | needs V209-1..V209-8b and V209-12 merged and CI green, and A1's V209-A1-4 recorded PASS |
| I close-out | V209-14 | plan files (moved), `VERSION.json` untouched | needs V209-13 deployed and the shadow log writing on production |

Track 2's plan shares no file with this plan, so the two may be implemented
in either order or side by side on separate worktrees.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V209-1 | "Market Shock" config section: `MARKET_SHOCK_MODE` + 18 thresholds | 1 | haiku | M `swingbot/config.py` (new section, `_MODE_VALUES` entry); M `.env.example`; C `tests/test_config_v209_keys.py` | `config.MARKET_SHOCK_MODE` (str, `off\|shadow\|live`, default `shadow`); floats `SHOCK_ATR_K` 1.0, `SHOCK_BREADTH_ENTER` 0.40, `SHOCK_SECTORS_FRAC` 0.6, `SHOCK_BREADTH_FAST` 0.25, `SHOCK_SPEED_ENTER` 0.10, `SHOCK_VIX_SPIKE_PCT` 15.0, `SHOCK_VIX_RELIEF` 0.05, `SHOCK_BREADTH_REENTER` 0.30, `SHOCK_BREADTH_EXIT` 0.20, `RECOVERY_VIX_OFF_HIGH_PCT` 5.0, `RECOVERY_SPY_RETRACE` 0.5; ints `SHOCK_MIN_DWELL_MIN` 45, `RECOVERY_MIN_DWELL_MIN` 30, `SHOCK_MIN_NAMES` 20, `SHOCK_VIX_MAX_AGE_S` 600, `SHOCK_OPEN_SETTLE_MIN` 15, `SHOCK_QUOTE_MAX_AGE_S` 300, `SHOCK_READINGS_KEEP_DAYS` 180; section `"Market Shock"`, all `hot_reloadable=True`, help text names `v209` |
| V209-2 | `shock.py`: types and thresholds | 1 | sonnet | C `swingbot/core/market/shock.py`; C `tests/market/test_shock_measure.py` | `LABELS = ("NORMAL","SHOCK","RECOVERY")`; frozen `ShockThresholds(atr_k=1.0, breadth_enter=0.40, sectors_frac=0.6, breadth_fast=0.25, speed_enter=0.10, vix_spike_pct=15.0, vix_relief=0.05, breadth_reenter=0.30, breadth_exit=0.20, recovery_vix_off_high_pct=5.0, recovery_spy_retrace=0.5, min_dwell_min=45, recovery_min_dwell_min=30, min_names=20, vix_max_age_s=600, open_settle_min=15, quote_max_age_s=300)`; frozen `NameRow(ticker: str, sector: str \| None, last: float \| None, prev_close: float \| None, atr14: float \| None, is_equity: bool)`; frozen `VixTape(level: float \| None, chg_pct: float \| None, as_of: datetime \| None)`; frozen `ShockSnapshot(as_of: datetime, session_date: date, minutes_since_open: float, names: tuple[NameRow, ...], spy: NameRow \| None, qqq: NameRow \| None, vix: VixTape)`; frozen `ShockReading(as_of, session_date, minutes_since_open, breadth_frac: float \| None, sectors_down: int, sectors_total: int, breadth_speed: float \| None, spy_atr_move, qqq_atr_move, spy_last, spy_prev_close, spy_session_low: float \| None, spy_new_low: bool, spy_retrace: float \| None, vix_level, vix_chg_pct, vix_session_high, vix_off_high_pct: float \| None, n_names: int, insufficient: bool)` with `as_row() -> dict` (JSON-safe, ISO datetimes) and `classmethod from_row(row: dict) -> ShockReading`; `measure(snapshot, prev: ShockReading \| None, th: ShockThresholds = ShockThresholds()) -> ShockReading` (`spy_retrace` = 1.0 when the session low ≥ prior close, `None` without SPY) |
| V209-2b | `shock.py`: `measure` and its tests | 1 | sonnet | M `swingbot/core/market/shock.py`; M `tests/market/test_shock_measure.py` | `measure(snapshot, prev: ShockReading \| None, th: ShockThresholds = ShockThresholds()) -> ShockReading`, exactly as V209-2's row describes |
| V209-3 | `shock.py`: `ShockState` + `step` entry rules | 1 | sonnet | M `swingbot/core/market/shock.py`; C `tests/market/test_shock_step_entry.py` | frozen `ShockState(label="NORMAL", since: datetime \| None = None, session_date: date \| None = None, vix_session_high: float \| None = None, spy_prev_close: float \| None = None, entry_streak: int = 0, hold_since: datetime \| None = None, prev_breadth: float \| None = None)` with `as_row() -> dict`, `classmethod from_row(row: dict \| None) -> ShockState`; `step(state, reading, th) -> ShockState` (insufficient ⇒ state unchanged); `entry_condition(reading, th) -> bool`; `RULES: dict[str, Callable[[ShockState, ShockReading, ShockThresholds], ShockState]]` keyed by label |
| V209-4 | `shock.py`: SHOCK → RECOVERY → NORMAL, second leg, overnight carry | 1 | sonnet | M `swingbot/core/market/shock.py`; C `tests/market/test_shock_step_exit.py` | `recovery_condition(state, reading, th) -> bool`; `reentry_condition(state, reading, th) -> bool`; `RULES["SHOCK"]`, `RULES["RECOVERY"]` complete; `ShockState.session_date`/`vix_session_high`/`spy_prev_close`/`prev_breadth` carried as specified |
| V209-5 | `v209_001` tables, `PROMOTION_REASONS`, migration, schema test | 2 | opus | M `swingbot/core/db/schema.py` (two `register(...)` tables above `PROMOTION_REASONS`; two `PROMOTION_REASONS` entries at its end); C `swingbot/core/db/migrations/versions/v209_001_market_shock.py`; C `tests/db/test_v209_market_shock_schema.py`; M `tests/db/test_unknown_field_round_trip.py` (two `NOT_REPOSITORY_BACKED` entries) | `schema.market_shock_state`: `id` SmallInteger PK (always 1), `label` Text NOT NULL, `since` TIMESTAMPTZ NULL, `session_date` Date NULL, `vix_session_high` Float(53) NULL, `last_reading_id` BigInteger NULL FK → `market_shock_readings.id` ON DELETE SET NULL, `last_notice_at` TIMESTAMPTZ NULL, + `doc`, `updated_at`; `schema.market_shock_readings`: `id` BigInteger identity PK, `as_of` TIMESTAMPTZ NOT NULL (indexed), `session_date` Date NOT NULL, `state_after` Text NOT NULL, `breadth_frac`, `breadth_speed`, `spy_atr_move`, `qqq_atr_move`, `vix_level`, `vix_chg_pct`, `vix_off_high_pct` Float(53) NULL, `sectors_down`, `sectors_total`, `n_names` Integer NOT NULL, `insufficient` Boolean NOT NULL, + `doc`, `updated_at`; `schema.PROMOTION_REASONS["market_shock_state"]`, `["market_shock_readings"]`; Alembic revision `v209_001` (sole head) |
| V209-5b | `MarketShockRepository` + nightly `_prune_shock_readings` | 2 | opus | C `swingbot/core/db/repositories/market_shock.py`; M `swingbot/commands/scanning/loops.py` (`_prune_shock_readings` beside `_prune_alert_posts`; one `await _prune_shock_readings()` line in `daily_recap`); C `tests/db/test_market_shock_repository.py`; C `tests/commands/test_shock_readings_prune.py` | `market_shock.LABELS` (restated, pinned equal to `shock.LABELS`); `market_shock_repo() -> MarketShockRepository` with `record(reading: dict, state: dict, *, state_after: str, notice_event: dict \| None = None, conn=None) -> int` (one transaction: insert reading with full `as_row()` in `doc`, upsert state row 1 with `last_reading_id` and `doc={"state": state}`, enqueue `notice_event` via `NotifyQueueRepository().enqueue(event, conn=)` and set `last_notice_at` when given; returns reading id), `current_state(*, conn=None) -> dict \| None` (keys `label`, `since`, `session_date`, `vix_session_high`, `last_reading_id`, `last_notice_at`, `updated_at`, `doc`), `latest_reading(*, conn=None) -> dict \| None` (stored `as_row()` + `id`, `state_after`), `prune_before(cutoff: datetime, *, conn=None) -> int`; `loops._prune_shock_readings() -> None` (async, never raises, every mode) |
| V209-6 | `shock_scan.py`: mode, thresholds, VIX read, snapshot, step gate | 2 | opus | C `swingbot/core/scanning/shock_scan.py`; C `tests/scanning/test_shock_scan.py` | `shock_mode`, `THRESHOLD_ATTRS`, `thresholds_from_config`, `read_vix` (a proxied `^VIX` row counts as missing), `build_snapshot`, `should_step` |
| V209-6a | `shock_scan.py`: `run_shock_pass`, `current_label` | 2 | opus | M `swingbot/core/scanning/shock_scan.py` (imports `market_shock_repo` only, never `fetch`); C `tests/scanning/test_shock_pass.py` | `run_shock_pass` and `current_label` with the signatures in Global Constraints (`run_shock_pass` never fetches a quote: an absent SPY/QQQ quote gives `last=None` and a reading with `spy_*` `None`; `current_label()` returns `None` when the store cannot be read, so that pass stamps no key); private `_stepped_pass(frames, live_prices, sector_of, quotes_at, spy_df, now, repo)` and `_load_prior(repo)` for plan v210's V210-2b to extend |
| V209-6b | Scan wiring: `run_scan(step_shock=)`, `quotes_at`, the guarded shock call, `loops.py:252` | 3 | opus | M `swingbot/core/scanning/scan_run.py` (`run_scan`, `_run_scan_in_context`, `_sync_run_scan`: one `quotes_at` line + one `shock_state = _shock_state_for_pass(...)` line; new module helper `_shock_state_for_pass`); M `swingbot/commands/scanning/loops.py` (line 252 call adds `step_shock=True`); M `tests/scanning/test_run_scan_scan_id.py`, `tests/scanning/test_run_scan_publishes_progress.py` (fakes accept `step_shock`); C `tests/commands/test_shock_step_gate.py` | `run_scan(..., *, step_shock: bool = False)`; `_sync_run_scan(..., step_shock: bool = False)` binds local `shock_state: str \| None` before the plan builders run; `scan_run._shock_state_for_pass(**kwargs) -> str \| None` (`run_shock_pass(**kwargs)`, `None` + swallow tag `scan.shock.call` on a raise); test fixture `worker` (returns `frames, order, asked`), `QUOTES`, `_Halt(BaseException)`; `!check`, recap and admin-UI scan pinned to `step_shock=False` |
| V209-6c | SPY and QQQ ride the scan's one live-price fetch | 3 | opus | M `swingbot/core/scanning/shock_scan.py` (`QQQ_TICKER`, `_benchmarks`, `quote_tickers`, `scan_quotes`); M `swingbot/core/scanning/scan_run.py` (`_sync_run_scan`: the `_fetch_live_prices` line takes `quote_tickers(tickers, step_shock)`, one `scan_quotes` line, the shock call gets `shock_prices`); M `tests/commands/test_shock_step_gate.py` | `shock_scan.QQQ_TICKER = "QQQ"`; `quote_tickers(tickers: list, step_shock: bool) -> list` (same list object unless stepping and mode not `off`; then SPY, QQQ appended, deduped, order kept); `scan_quotes(prices: dict, tickers: list) -> dict` (benchmarks not on the watchlist removed; same dict when none); still exactly one `_fetch_live_prices` call per scan |
| V209-7 | Stamp `shock_state` on confluence, requote and strategy plans | 3 | opus | M `swingbot/core/planning/params.py` (`stamp_entry_context` merge); M `swingbot/core/scanning/analyze.py` (`attach_plan_v2(..., shock_state=None)`); M `swingbot/core/scanning/scan_run.py` (`_attach_item_plan`, `_rebuild_item`, the `functools.partial`, `_maybe_run_strategy_pass` + its `asof_of`); C `tests/scanning/test_shock_state_stamp.py`; C `tests/planning/test_stamp_entry_context_shock.py` | `attach_plan_v2(..., shock_state: str \| None = None)` (adds `"shock_state"` to the asof dict only when not `None`); `_attach_item_plan(item, scenario, df, regimes, regime, shock_state=None)`; `_rebuild_item(..., shock_state=None)`; `_maybe_run_strategy_pass(..., shock_state: str \| None = None)`; `stamp_entry_context` writes `plan.entry_context["shock_state"]` when `asof.get("shock_state") is not None`, after the feature dict and after the failure fallback |
| V209-8 | SHORT lane reads the label via the lane dict | 3 | opus | M `swingbot/core/scanning/qualify.py` (`QualifyContext.shock_state`, `_attach_plan`); M `swingbot/core/scanning/short_run.py` (`_lane_state`, `_qualify_context`, `_bare_context`); C `tests/scanning/test_shock_short_lane.py` | `QualifyContext.shock_state: str \| None = None` (last field); `short_run._lane_state(reference, snapshot, regime)` dict gains `"shock_state": shock_scan.current_label()` (the only `current_label()` call per SHORT run); `_qualify_context(require_confirmation, frames, lane)` passes `lane.get("shock_state")`; `_bare_context(..., shock_state=None)` |
| V209-8b | Byte-identical plan pins under `off`, `shadow` and a failed shock pass | 3b | opus | C `tests/scanning/test_shock_plans_byte_identical.py` | none (regression pins only; six lanes × no-arg/`off`/`shadow`, plus confluence and requote long plans under a raising pass and an unreachable store, each byte-identical to a pass stubbed to `None`) |
| V209-12 | 2026-11-05 replay fixture (Alpaca, synthetic fallback) + replay test | 5 | sonnet | C `scripts/data/build_shock_replay_fixture.py`; C `tests/fixtures/shock_replay_2026_11_05.json`; C `tests/scripts/test_build_shock_replay_fixture.py` | fixture JSON `{"source": "alpaca" \| "synthetic", "vix_interpolated": true, "note": str, "steps": [{"as_of", "minutes_since_open", "vix": {"level", "chg_pct"}, "spy": NameRow-dict, "qqq": NameRow-dict \| null, "names": [NameRow-dict]}]}`; replay asserts first SHOCK `as_of ≤ 2026-11-05T15:00:00Z` (earliest the settle + two-reading rules allow; reports how many of the 18 post-14:36 longs opened before it) |
| V209-12b | Replay test over the 2026-11-05 fixture (superseded by A1: V209-A1-4) | 5 | sonnet | C `tests/market/test_shock_replay_2026_11_05.py` | none (asserts first SHOCK `as_of ≤ 2026-11-05T15:00:00Z`; reports longs opened before it from the fixture's `long_entries`) |
| V209-13 | Release: prod checks, rollback line, bump, deploy in `shadow` (after A1 PASS; re-checks empty `market_shock_readings`) | 5 | opus | M `docs/deploy/DEPLOY_HETZNER.md` (image-only rollback line + `### v209: market shock tables` section); M `VERSION.json`; M `swingbot/admin/version_history.json` | production `MARKET_SHOCK_MODE=shadow`; verified `TAPE_SHARED_ENABLED`, `MARKETDATA_LAYER`, `DAILY_DELTA_FETCH`, live-price path; release commit `release(bot): <version> -- v209 market-shock detector (shadow)` and its `chore(...)` regeneration commit, which V209-14 detects to skip a second bump |
| V209-14 | `/panel` (staff-engineer, quant-researcher, veteran-trader) + `/close-out` without a second bump | 5 | sonnet | M (moved by `/close-out`) every v209 plan file (index + parts 1, 1b, 2, 3, 3b, 5) and the A1 stem (`-a1_0-index`, `-a1_1`, `-a1_2`) `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_*.md` → `docs/superpowers/plans/implemented/`; the spec stays in `specs/` (Track 2's plan is still live and closes it); `VERSION.json` and `version_history.json` **not** modified | none (last task). Double-bump guard: before `/close-out` Step 3, run `git log --oneline -- VERSION.json` and confirm the V209-13 `release(bot): ... -- v209` commit is present and `VERSION.json` still holds that version; if so, tell the close-out that the bump is already released (Steps 3–4 skipped, Step 5's prediction check still runs) and record `bump released in V209-13 (<sha>)` in the close-out commit message. If the release commit is missing, stop and report — never bump here |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-05-v209-market-shock-detector_1-detector-core.md` | V209-1, V209-2, V209-2b, V209-3 | config section; pure `shock.py` (types, `measure`, `step` entry rules) — written, committed |
| 1b | `2026-11-05-v209-market-shock-detector_1b-detector-exit.md` | V209-4 | `step` exit and carry rules (split from part 1 at the 1500-line cap) — written, committed |
| 2 | `2026-11-05-v209-market-shock-detector_2-storage-and-wiring.md` | V209-5, V209-5b, V209-6, V209-6a | `v209_001` tables + migration; repository + nightly prune; the `shock_scan.py` pass module |
| 3 | `2026-11-05-v209-market-shock-detector_3-scan-wiring-and-stamp.md` | V209-6b, V209-6c, V209-7, V209-8 | `run_scan(step_shock=)` wiring; SPY/QQQ on the one live-price fetch; label threading through every lane |
| 3b | `2026-11-05-v209-market-shock-detector_3b-byte-identical-pins.md` | V209-8b | byte-identical pins, incl. a failed shock pass (moved from part 3 at the 1500-line cap) |
| 5 | `2026-11-05-v209-market-shock-detector_5-replay-release-closeout.md` | V209-12, V209-12b, V209-13, V209-14 | 2026-11-05 replay; release in `shadow`; `/panel` + `/close-out` |

18 ledger rows (`b`/`c` rows included). Rows V209-1, -2, -2b, -3 and -6 state the pre-A1 contract; the A1 ledger supersedes their `sectors_frac` / `SHOCK_SECTORS_FRAC` parts (20 config fields after A1). Amendment A1 is its own stem, [A1 index](2026-11-05-v209-market-shock-detector-a1_0-index.md) (parts `-a1_1-rule-and-tooling`, `-a1_2-data-and-acceptance`), because 18 + its rows would pass the 20-task cap. Notices and admin badge (old V209-9..V209-11,
part 4) moved to plan v210 (`2026-11-06-v210-market-shock-notices-and-badge_0-index.md`).

## Notes for part writers

- **Part 2 is a rewrite of the uncommitted draft** at the same filename:
  the draft's V209-5 (28.5 KB) splits into V209-5 (schema, `PROMOTION_REASONS`,
  migration, schema test, `test_unknown_field_round_trip.py` edit) and V209-5b
  (repository, its tests, `_prune_shock_readings` and its test), and the
  draft's header must say "V209-5, V209-5b, V209-6" with the decided choices
  from Global Constraints. V209-6 is the `shock_scan.py` module and its unit
  tests only; the `scan_run.py` / `loops.py:252` edits belong to V209-6b in
  part 3.
- **The ShockState fields beyond the spec's list** (`entry_streak`,
  `hold_since`, `prev_breadth`) are the bookkeeping the two-consecutive rule,
  the RECOVERY hold and the "rising breadth" re-entry need; they live in
  `market_shock_state.doc["state"]`, not in promoted columns.
- **`measure` takes `th` as a defaulted third argument**: the spec writes
  `measure(snapshot, prev)`, and the call stays valid; `atr_k`, `min_names`
  and `vix_max_age_s` come from `th`.
- **Quote freshness** (V209-6): `live_prices` has no per-quote time, so the
  whole pass's quotes share `quotes_at`; a name absent from `live_prices` is
  excluded from the reading. SPY and QQQ quotes share the same `quotes_at`
  (they come from the same batched call, V209-6c); the pass never fetches.
- **`loops.py` is edited by V209-5b (prune) and V209-6b (line 252)**: the
  6b writer re-reads the line number after 5b's insertion rather than
  trusting `252`.
- **Open longs and the notice line format** moved with the notices to plan v210.
- **The bump** is released in V209-13 (the deploy needs it); V209-14's
  `/close-out` reads `VERSION.json` and must not bump a second time — the
  task carries the guard in its ledger row.
