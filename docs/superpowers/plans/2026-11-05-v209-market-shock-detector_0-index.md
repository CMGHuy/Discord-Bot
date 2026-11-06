# v209 — Market-shock detector (shadow), Track 1 (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot minor, ui patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (main @ 437dd4d5; the spec's closing *Plan-briefer reconciliation* paragraph overrides earlier spec text; § What changes → *Plans* puts Track 1 in this plan and Track 2 in a separate one)
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
second-leg re-entry. The state is stored in two new tables, every new plan's
`entry_context` gains `shock_state` (so the live book can measure shock
cohorts directly), a `market_shock` notice goes to the ops channel on every
transition (listing open longs with last price, open R and "THROUGH STOP" on
entry into SHOCK), and the admin tape shows a NORMAL/SHOCK/RECOVERY badge.
In `shadow` mode, which is the default and the only meaning `live` has in
this spec, **no trade changes**: no long blocked, no short issued, no stop
moved. `MARKET_SHOCK_MODE=off` is a byte-identical kill switch.

**Track 2 is a separate plan.** The two pre-registered one-shot screens
(`shock_support_break_short`, `shock_failed_bounce_short`, family
`shock_breakdown`), the screen runner's `CONTEXT_KIND = "level"` path, the
`BREADTH_ATR1` / `^VIX` context files, the `listing()` exclusion and the
results/ledger rows are built by the plan the spec calls "plan v210", written
later under the next free number with its `**Spec:**` line pointing at the
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
  quotes + sector map, one SPY quote fetch on stepped passes, VIX from the
  tape, measure/step/record, current label).
- **Scan wiring** (V209-6b): `_sync_run_scan` gains one `quotes_at` line and
  one call line, no branch; `run_scan(*, step_shock=False)`; only
  `loops.py:252` passes `step_shock=True`.
- **Plan stamp** (V209-7, V209-8): the label travels as an argument
  (`shock_state`) through `_attach_item_plan`, `_rebuild_item`,
  `_maybe_run_strategy_pass`'s `asof_of`, `attach_plan_v2`, and
  `QualifyContext` (SHORT lane: from the lane dict);
  `params.stamp_entry_context` merges it into `entry_context` after the
  feature dict. Never in `FEATURE_KEYS`.
- **Notices** (V209-9, V209-10): a third v197 queue kind `market_shock`
  (validator, renderer, delivery dispatch); payload, open-long lines and the
  rate limit in new `swingbot/core/scanning/shock_notices.py`.
- **Admin** (V209-11): `/api/v1/market/tape` gains a `shock` object; the SPA
  tape shows a badge.
- **Replay** (V209-12): a frozen 2026-11-05 fixture (Alpaca 15-minute bars,
  synthetic fallback recorded as such) replayed through `measure`/`step`.
- **Release** (V209-13): production checks, rollback doc line, bump, deploy
  in `shadow`.
- **Close-out** (V209-14): `/panel` with the spec's three roles over the
  merged diff, then `/close-out` without a second bump.

**Tech stack:** Python 3.11, SQLAlchemy + psycopg 3, Alembic, discord.py,
Flask, pandas/numpy, pytest; Angular standalone components + signals,
Vitest via `frontend/scripts/ng-test.mjs`.

## Global Constraints

- **No trade changes.** `shadow` and `live` behave identically in this plan. No long is blocked, no short issued, no stop moved, no plan's levels, size or status altered by the detector.
- **`MARKET_SHOCK_MODE=off` is a byte-identical kill switch:** no reading, no state write, no notice, no `entry_context["shock_state"]` key (absent, not `None`). Unknown mode values fall back to `off`. The nightly prune is retention, not detector behaviour: it trims old rows in every mode.
- **`shock_state` is never added to `swingbot/core/edge/context.py:FEATURE_KEYS`** and never stamped by `entry_context()` itself; it is merged into `plan.entry_context` by `params.stamp_entry_context` after the feature dict is built, and also after a feature-build failure (so `{"shock_state": ...}` survives T3's `entry_context = {}` fallback).
- **Only the scheduled `session_scan` steps the state** (`loops.py:252`, `step_shock=True` keyword), and only while **`swingbot/core/market/session.py:is_nyse_regular_session(now)`** is true (the spec's `is_regular_session` window narrowed to skip NYSE holidays and stop at a half-day close, because on those days the "live" quote is the last close and a zero-move reading would walk SHOCK into RECOVERY). Never gate on `data.is_us_market_active()`, `bot_core.in_session()` or plain `is_regular_session`. `!check` (`commands.py:199`), the recap (`recap.py:104`), the admin-UI scan (`loops.py:489`) and the SHORT lane read the stored label and never write.
- **`run_scan` takes `step_shock: bool = False` by keyword only.** `_sync_run_scan` (CC 94), `_session_scan_tick` (CC 15), `attach_plan_v2` (12) and `_maybe_run_strategy_pass` gain **no branch**; all logic lives in `shock_scan.py` / named helpers.
- **`run_shock_pass` takes `spy_df: pd.DataFrame | None = None`** (`_sync_run_scan` passes its `spy_df = fresh_data.get(config.MARKET_REGIME_TICKER)`; `None` ⇒ the SPY row comes from `frames` when present). On a **stepped** pass whose `live_prices` lack the SPY quote, `run_shock_pass` fetches it **once** (`fetch._fetch_live_prices` for that one symbol); an unstepped pass never fetches anything.
- **Planning never reads the shock repository.** The SHORT lane reads the stored label once per run through the lane dict: `short_run._lane_state(...)` adds `"shock_state": shock_scan.current_label()`, and `_qualify_context(require_confirmation, frames, lane)` passes `lane.get("shock_state")` into `QualifyContext.shock_state`.
- **Labels** are exactly `"NORMAL"`, `"SHOCK"`, `"RECOVERY"` (`shock.LABELS`). The db layer imports nothing from `swingbot/core/market`, so the repository restates the three labels and a test pins them equal to `shock.LABELS`. No row stored yet ⇒ `current_label()` returns `"NORMAL"` under `shadow`/`live`, `None` under `off`.
- **The repository stores the full `ShockReading.as_row()` in each reading's `doc`** (and `{"state": ShockState.as_row()}` in the state row's `doc`), because a `None` promoted column would otherwise vanish on merge; promoted columns are copies for querying.
- **Reading rules (spec § The reading):** `breadth_frac` = share of contributing equities with `(last − prev_close) / atr14 ≤ −atr_k`, where a name is an equity **only if `swingbot/core/marketdata/asset_class.classify(ticker) == "equity"`** (ETFs, indices, futures, FX and crypto never count); `sectors_down` counts sectors with ≥ 2 contributing members whose median ratio ≤ −atr_k; `sectors_total` counts sectors with ≥ 2 contributing members; the depth clause needs `sectors_total ≥ 1` and `sectors_down ≥ ceil(sectors_frac × sectors_total)`; `breadth_speed` only within the same session, else `None`; names with < 15 completed bars or no fresh live quote are excluded; `n_names < min_names` ⇒ `insufficient=True` and `step` returns the state unchanged.
- **"Last" is the pass's live quote** (`live_prices`), never the frame's last bar. `live_prices` carry no timestamp, so the pass records `quotes_at` right after `fetch._fetch_live_prices` returns; when `now − quotes_at > SHOCK_QUOTE_MAX_AGE_S` every quote is treated as absent. `prev_close` is the close of the last **completed** session's bar (bar[-2] when bar[-1] is dated today in `US_MARKET_TZ`, else bar[-1]); `atr14` = `indicators.atr(completed_bars, 14)` last value.
- **Entry from NORMAL** needs the condition on **two consecutive** readings, and a reading with `minutes_since_open < SHOCK_OPEN_SETTLE_MIN` resets the streak to 0 and never counts. The open-settle rule also applies to RECOVERY → SHOCK re-entry; re-entry needs one qualifying reading, and "new SPY session low" needs an earlier reading in the same session.
- **VIX:** read from the tape's `^VIX` row via `read_tape` (never fetches); a row older than `SHOCK_VIX_MAX_AGE_S` or missing ⇒ `vix_*` fields `None`. Prior VIX close = `price / (1 + change_pct/100)`. Session high = running max of readings this session. Missing VIX never blocks entry into SHOCK; it leaves the RECOVERY VIX clause unmet.
- **RECOVERY → NORMAL** needs the RECOVERY conditions to hold on every reading for `RECOVERY_MIN_DWELL_MIN`; a reading where they fail resets the hold clock (`ShockState.hold_since = None`) without leaving RECOVERY unless a re-entry rule fires.
- **Notice copy, exact.** Footer line on entry into SHOCK and on a second leg: `The bot moved no stop and closed nothing. Stop move-up and long block are pending screen (v209 Track 2).` Through-stop marker: `THROUGH STOP`. Otherwise: `stop at broker untouched: <stop:.2f>`. Unknown last price: `last n/a` and `stop status unknown: <stop:.2f>`. Zero open longs: `No open longs.`
- **Rate limit:** at most one `market_shock` notice per `SHOCK_MIN_DWELL_MIN`, except any transition **into** SHOCK, which is always sent. Notices are routed to `config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID`, computed in the worker thread (never `bot.get_channel` there). A notice is a plain status embed, never an alert embed.
- **The two existing queue kinds are untouched** (`trade_closed`, `plan_transition`): their validators, renderers and tests do not change.
- **Revision id `v209_001`, `down_revision = "v197_001"`**, file `swingbot/core/db/migrations/versions/v209_001_market_shock.py`; working `downgrade()` dropping both tables; exactly one Alembic head. Neither table joins `TABLE_CHANNELS` (no SSE).
- **No screen-runner, idea-module, context-file or ledger change** in this plan: those are Track 2's plan. `PARITY_DIGESTS` and `test_long_byte_identical.py` are not touched.
- Every function written or changed < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py`); no legacy function's CC rises.
- Every UI change is checked at 390 px, 820 px and 1440 px; the badge never truncates the tape and wraps below it on narrow widths; badge copy `NORMAL` / `SHOCK` / `RECOVERY`, and `VIX missing` when `vix_level` is null.
- Narrow test runs only: backend `python scripts/dev/testrun.py file <test>`; frontend `node frontend/scripts/ng-test.mjs frontend --include <spec>`. **No task runs the full suite**; CI does after the push. A task whose tests reach Postgres runs `/replicate-prod-db` first (one shared `swing-db` container, port 56789, `.env` credentials never printed). Every new test file sits in an existing `tests/` directory, so `tests/suites.toml` is unchanged.
- `.env` values are read, never printed; production is reached only through `bash scripts/ops/ssh-hetzner.sh`.
- Commit steps run on the plan's worktree branch, never on `main`.

## Review Focus

1. **Stale bars outside regular hours.** A pass at 08:00 ET (inside `is_us_market_active()`), at 22:00 Berlin (inside `in_session()`), on an NYSE holiday or after a half-day close must not write a reading. Owner: V209-6 (gate), V209-6b (only `loops.py:252` steps).
2. **Overnight carry.** The first reading of a new session has `breadth_speed=None`, a new `vix_session_high`, a new SPY prior close; a gap-up repair reaches RECOVERY, a second leg down stays SHOCK. Owner: V209-4.
3. **Kill switch.** Under `off`, a plan built by each of the three lanes and both rebuild paths has no `shock_state` key and is byte-identical to the pre-v209 plan. Owner: V209-7, V209-8, V209-8b.
4. **Second leg notice.** RECOVERY → SHOCK inside the rate-limit window still enqueues. Owner: V209-10.
5. **One transaction.** Reading, state row and notice event commit together or not at all; a failing enqueue leaves no reading. Owner: V209-5b.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A config | V209-1 | `config.py`, `.env.example`, `tests/test_config_v209_keys.py` | none; may start at once |
| B detector | V209-2 → V209-2b → V209-3 → V209-4 | `swingbot/core/market/shock.py` + `tests/market/test_shock_*.py` | one module: 2b adds `measure` to 2's types, 3 adds `step` entry rules, 4 adds the exit/carry rules to 3's table |
| C storage | V209-5 → V209-5b | `schema.py`, migration, `repositories/market_shock.py`, `loops.py` (`daily_recap` prune), `tests/db/*` | 5b's repository reads 5's tables; may run beside A and B (contract in the ledger) |
| D wiring | V209-6 → V209-6a → V209-6b → V209-7 → V209-8 → V209-8b | `shock_scan.py`, `scan_run.py`, `loops.py:252`, `analyze.py`, `params.py`, `strategy_pass.py`, `qualify.py`, `short_run.py` | 6 needs A, B and 5b's repository; 6b edits `scan_run.py` and `loops.py` after 6 (and after 5b, which also edits `loops.py`); 7 edits `scan_run.py` after 6b and consumes its `shock_state` local; 8 consumes 6's `current_label` and 7's `stamp_entry_context` merge |
| E notices | V209-9 → V209-10 | `lifecycle_events.py`, `lifecycle_notifications.py`, `shock_notices.py` (9 creates, 10 extends), `shock_scan.py` (10) | 9 needs only B's `LABELS`; 10 needs 5b's `record(notice_event=)`, 6's `run_shock_pass` and 9's kind; 10 edits `shock_scan.py` so it runs after 6 (and never beside 6b–8 touching the same function) |
| F admin | V209-11 | `admin/api_v1/market.py`, `frontend/src/app/{api/models.ts,stores/tape-feed.ts,shell/tape/*}` | needs C's repository only; may run beside D/E |
| G replay | V209-12 | `scripts/data/build_shock_replay_fixture.py`, `tests/fixtures/shock_replay_2026_11_05.json`, `tests/market/test_shock_replay_2026_11_05.py`, `tests/scripts/test_build_shock_replay_fixture.py` | needs B complete; may run beside C–F |
| H release | V209-13 | `docs/deploy/DEPLOY_HETZNER.md`, `VERSION.json`, `swingbot/admin/version_history.json` | needs every task V209-1..V209-12 merged and CI green |
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
| V209-6a | `shock_scan.py`: `run_shock_pass`, `current_label` | 2 | opus | M `swingbot/core/scanning/shock_scan.py`; C `tests/scanning/test_shock_pass.py` | `run_shock_pass` and `current_label` with the signatures in Global Constraints (`current_label()` returns `None` when the store cannot be read, so that pass stamps no key); private `_stepped_pass(frames, live_prices, sector_of, quotes_at, spy_df, now, repo)` and `_load_prior(repo)` for V209-10 to extend |
| V209-6b | Scan wiring: `run_scan(step_shock=)`, `quotes_at`, `loops.py:252`, read-only callers | 3 | opus | M `swingbot/core/scanning/scan_run.py` (`run_scan`, `_run_scan_in_context`, `_sync_run_scan`: one `quotes_at` line + one `shock_state = shock_scan.run_shock_pass(...)` line); M `swingbot/commands/scanning/loops.py` (line 252 call adds `step_shock=True`); M `tests/scanning/test_run_scan_scan_id.py` (fake accepts `step_shock`); C `tests/commands/test_shock_step_gate.py` | `run_scan(..., *, step_shock: bool = False)`; `_sync_run_scan(..., step_shock: bool = False)` binds local `shock_state: str \| None` before the plan builders run; `!check`, recap and admin-UI scan pinned to `step_shock=False` |
| V209-7 | Stamp `shock_state` on confluence, requote and strategy plans | 3 | opus | M `swingbot/core/planning/params.py` (`stamp_entry_context` merge); M `swingbot/core/scanning/analyze.py` (`attach_plan_v2(..., shock_state=None)`); M `swingbot/core/scanning/scan_run.py` (`_attach_item_plan`, `_rebuild_item`, the `functools.partial`, `_maybe_run_strategy_pass` + its `asof_of`); C `tests/scanning/test_shock_state_stamp.py`; C `tests/planning/test_stamp_entry_context_shock.py` | `attach_plan_v2(..., shock_state: str \| None = None)` (adds `"shock_state"` to the asof dict only when not `None`); `_attach_item_plan(item, scenario, df, regimes, regime, shock_state=None)`; `_rebuild_item(..., shock_state=None)`; `_maybe_run_strategy_pass(..., shock_state: str \| None = None)`; `stamp_entry_context` writes `plan.entry_context["shock_state"]` when `asof.get("shock_state") is not None`, after the feature dict and after the failure fallback |
| V209-8 | SHORT lane reads the label via the lane dict | 3 | opus | M `swingbot/core/scanning/qualify.py` (`QualifyContext.shock_state`, `_attach_plan`); M `swingbot/core/scanning/short_run.py` (`_lane_state`, `_qualify_context`, `_bare_context`); C `tests/scanning/test_shock_short_lane.py` | `QualifyContext.shock_state: str \| None = None` (last field); `short_run._lane_state(reference, snapshot, regime)` dict gains `"shock_state": shock_scan.current_label()` (the only `current_label()` call per SHORT run); `_qualify_context(require_confirmation, frames, lane)` passes `lane.get("shock_state")`; `_bare_context(..., shock_state=None)` |
| V209-8b | Byte-identical long/short plan pins under `off` and `shadow` | 3 | opus | C `tests/scanning/test_shock_plans_byte_identical.py` | none (regression pins only; six lanes × no-arg/`off`/`shadow`) |
| V209-9 | `market_shock` notify-queue kind end to end | 4 | sonnet | M `swingbot/core/infra/lifecycle_events.py`; M `swingbot/core/scanning/lifecycle_notifications.py` (dispatch on kind); C `swingbot/core/scanning/shock_notices.py` (renderer half); C `tests/infra/test_lifecycle_events_market_shock.py`; C `tests/scanning/test_shock_notice_render.py` | `lifecycle_events.KINDS = ("trade_closed", "plan_transition", "market_shock")`; `_validate_shock_payload(payload)` requires `label` and `prior_label` in `shock.LABELS`, aware ISO `occurred_at`, dict `reading` (a `ShockReading.as_row()`), list `open_longs`, bool `entry_into_shock`; `shock_notices.build_shock_embed(event: dict) -> discord.Embed`; `shock_notices.long_line(row: dict) -> str` where `row = {"ticker", "entry", "stop", "last" (float \| None), "open_r" (float \| None), "age_min" (int), "through_stop" (bool)}`; `shock_notices.FOOTER` (exact copy in Global Constraints) |
| V209-10 | Notice payload, open longs, rate limit, enqueue in the stepped pass | 4 | sonnet | M `swingbot/core/scanning/shock_notices.py`; M `swingbot/core/scanning/shock_scan.py` (`run_shock_pass` builds and passes `notice_event`); C `tests/scanning/test_shock_notice_payload.py` | `open_long_rows(trades: list[dict], last_prices: Mapping[str, float], now: datetime) -> list[dict]` (open trades with `direction == "bullish"`, sorted by ticker); `should_notify(prior_label: str, new_label: str, last_notice_at: datetime \| None, now: datetime, min_dwell_min: int) -> bool`; `notice_payload(prior: ShockState, new: ShockState, reading: ShockReading, open_longs: list[dict], now: datetime) -> dict`; `notice_event(payload: dict, *, as_of: datetime) -> dict` (`make_event(transition_id=f"market_shock:{as_of.isoformat()}", kind="market_shock", target_channel_id=config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID, ...)`) |
| V209-11 | Admin tape `shock` object + SPA badge at three widths | 4 | sonnet | M `swingbot/admin/api_v1/market.py` (`_shock_block()`, both returns of `tape()`); C `tests/admin/test_api_v1_tape_shock.py`; M `frontend/src/app/api/models.ts`; M `frontend/src/app/stores/tape-feed.ts` (+ spec); M `frontend/src/app/shell/tape/tape.ts`, `tape.css`, `tape.spec.ts` | API: `"shock": null` under `off` or no state row, else `{"label", "since", "as_of", "breadth_pct", "sectors_down", "sectors_total", "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_missing": bool}`; TS `TapeShock` with those keys, `TapeResponse.shock?: TapeShock \| null`; `TapeFeed.shock: Signal<TapeShock \| null>`; badge element `.shock-badge[data-label]` |
| V209-12 | 2026-11-05 replay fixture (Alpaca, synthetic fallback) + replay test | 5 | sonnet | C `scripts/data/build_shock_replay_fixture.py`; C `tests/fixtures/shock_replay_2026_11_05.json`; C `tests/market/test_shock_replay_2026_11_05.py`; C `tests/scripts/test_build_shock_replay_fixture.py` | fixture JSON `{"source": "alpaca" \| "synthetic", "vix_interpolated": true, "note": str, "steps": [{"as_of", "minutes_since_open", "vix": {"level", "chg_pct"}, "spy": NameRow-dict, "qqq": NameRow-dict \| null, "names": [NameRow-dict]}]}`; replay asserts first SHOCK `as_of ≤ 2026-11-05T15:00:00Z` (earliest the settle + two-reading rules allow; reports how many of the 18 post-14:36 longs opened before it) |
| V209-13 | Release: prod checks, rollback line, bump, deploy in `shadow` | 5 | opus | M `docs/deploy/DEPLOY_HETZNER.md` (image-only rollback line + `### v209: market shock tables` section); M `VERSION.json`; M `swingbot/admin/version_history.json` | production `MARKET_SHOCK_MODE=shadow`; verified `TAPE_SHARED_ENABLED`, `MARKETDATA_LAYER`, `DAILY_DELTA_FETCH`, live-price path; release commit `release(bot): <version> -- v209 market-shock detector (shadow)` (+ the `ui` line per `Bump:`) and its `chore(...)` regeneration commit, which V209-14 detects to skip a second bump |
| V209-14 | `/panel` (staff-engineer, quant-researcher, veteran-trader) + `/close-out` without a second bump | 5 | sonnet | M (moved by `/close-out`) every v209 plan file (index + parts 1, 1b, 2, 3, 4, 5) `docs/superpowers/plans/2026-11-05-v209-market-shock-detector_*.md` → `docs/superpowers/plans/implemented/`; the spec stays in `specs/` (Track 2's plan is still live and closes it); `VERSION.json` and `version_history.json` **not** modified | none (last task). Double-bump guard: before `/close-out` Step 3, run `git log --oneline -- VERSION.json` and confirm the V209-13 `release(bot): ... -- v209` commit is present and `VERSION.json` still holds that version; if so, tell the close-out that the bump is already released (Steps 3–4 skipped, Step 5's prediction check still runs) and record `bump released in V209-13 (<sha>)` in the close-out commit message. If the release commit is missing, stop and report — never bump here |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-05-v209-market-shock-detector_1-detector-core.md` | V209-1, V209-2, V209-2b, V209-3 | config section; pure `shock.py` (types, `measure`, `step` entry rules) — written, committed |
| 1b | `2026-11-05-v209-market-shock-detector_1b-detector-exit.md` | V209-4 | `step` exit and carry rules (split from part 1 at the 1500-line cap) — written, committed |
| 2 | `2026-11-05-v209-market-shock-detector_2-storage-and-wiring.md` | V209-5, V209-5b, V209-6, V209-6a | `v209_001` tables + migration; repository + nightly prune; the `shock_scan.py` pass module |
| 3 | `2026-11-05-v209-market-shock-detector_3-scan-wiring-and-stamp.md` | V209-6b, V209-7, V209-8, V209-8b | `run_scan(step_shock=)` wiring; label threading through every lane; byte-identical pins |
| 4 | `2026-11-05-v209-market-shock-detector_4-notices-and-admin.md` | V209-9, V209-10, V209-11 | `market_shock` queue kind; notice content and rate limit; admin badge |
| 5 | `2026-11-05-v209-market-shock-detector_5-replay-release-closeout.md` | V209-12, V209-13, V209-14 | 2026-11-05 replay; release in `shadow`; `/panel` + `/close-out` |

17 ledger rows (`b` rows included); the 20-task cap leaves 3 spare slots for any `b` split a
part writer reports.

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
  excluded from the reading. The one SPY quote fetched on a stepped pass gets
  its own timestamp at fetch time.
- **`loops.py` is edited by V209-5b (prune) and V209-6b (line 252)**: the
  6b writer re-reads the line number after 5b's insertion rather than
  trusting `252`.
- **Open longs** (V209-10) come from `singletons.trade_log.get_trades(status="open", limit=None)`
  (rows with `entry`, `stop_loss`, `direction`, `opened_at`), last price from
  the pass's `live_prices`. `open_r = (last − entry) / (entry − stop)`;
  `through_stop = last <= stop`.
- **Notice line format** (V209-9), one per open long:
  `<TICKER> · entry <e:.2f> · stop <s:.2f> · last <l:.2f> · <r:+.2f>R · <age> · <marker>`,
  age as `<h>h<mm>m` (or `<m>m` under an hour); marker per Global Constraints.
  The transition headline: `Market state: <prior> → <new>` and a numbers
  line `breadth <pct>% · sectors <down>/<total> · speed <+pp> · SPY <x:+.2f> ATR · QQQ <x:+.2f> ATR · VIX <lvl:.2f> (<chg:+.1f>%)`,
  with `n/a` for any `None`.
- **The bump** is released in V209-13 (the deploy needs it); V209-14's
  `/close-out` reads `VERSION.json` and must not bump a second time — the
  task carries the guard in its ledger row.
