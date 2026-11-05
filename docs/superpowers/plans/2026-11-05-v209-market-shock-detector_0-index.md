# v209 — Market-shock detector (shadow) and shock-conditioned short screens (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot minor, ui patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (main @ 79325c50; the spec's closing *Plan-briefer reconciliation* paragraph overrides earlier spec text)
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` (code context for every part; §5 D1–D8 and §7 T1–T18 are the traps)

## Goal

On 2026-11-05 the live book closed 26 trades for −13.9R, its worst day of the
last 25: the market turned at about 14:36 UTC, the bot kept buying memory and
chip names (18 longs after the turn, MU five times), and most stops sat inside
normal price movement. The partner asked the bot to stop buying and start
shorting when the market turns sharply, and to watch price and VIX to know
when to switch back. The live-book counterfactuals that motivated it are
in-sample over about 84 effective days, so they justify a **measurement, not
a gate**: this plan builds the measurement and pre-registers the screens that
could later license a gate.

Once Track 1 ships, every scheduled scan pass in US regular hours takes one
**reading** of the watchlist (share of names down at least 1 ATR from the
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

Track 2 runs two one-shot Stage −2 idea screens on 2010–2019 point-in-time
S&P 500 members: `shock_support_break_short` (first 20-day-low close inside a
daily breadth-shock episode) and `shock_failed_bounce_short` (a failed bounce
below the bounce bar's low inside an episode), as one `shock_breakdown`
family. To run them, the screen runner gains a declared
`CONTEXT_KIND = "level"` path (no z-scoring), a precomputed `BREADTH_ATR1`
context series, a `^VIX` daily context file, and printed, never-gating
read-outs (shock-matched second null, unconditional control, outcome-blind
preflight, gap and episode-day splits, 3× friction stress, `skipped_overlap`).

What it leaves alone: every trade decision, sizing, stops, alert embeds, the
two existing notify-queue kinds, `edge/context.py:FEATURE_KEYS`, every
existing idea's screen output (the `PARITY_DIGESTS` and
`test_long_byte_identical.py` pins pass untouched; a changed digest is a
stop), the `COHORT_UNKNOWN` defect, and the closed pre-registrations (v17
P2a, v34, v191, v104 Part B, v182).

Success is measured by tests and by production, not by ExpR
(`Edge: none (integrity)`): the detector replayed over the frozen 2026-11-05
fixture reaches SHOCK no later than 14:36 UTC; every transition, hysteresis
band, dwell and carry case is pinned; long and short plans are byte-identical
under `off` and differ only by `entry_context.shock_state` under `shadow`;
`!check`, the recap, the admin-UI scan and the SHORT lane never write a
reading; after the deploy, `market_shock_readings` gains about 28 rows per
session on production. Track 2 succeeds when both screens have run exactly
once and their verdicts (whatever they are) are recorded in the ledger and
results docs.

## Architecture

- **Pure detector** (V209-2..V209-4): `swingbot/core/market/shock.py`, no I/O
  and no config import; frozen dataclasses in, frozen dataclasses out;
  `measure` builds a reading from a snapshot and the previous reading;
  `step` is table-driven, one rule function per transition, every function
  < 15.
- **Config** (V209-1): new "Market Shock" section in `swingbot/config.py`:
  `MARKET_SHOCK_MODE` (select `off|shadow|live`, default `shadow`) and 18
  numeric fields, all hot-reloadable.
- **Persistence** (V209-5): Alembic `v209_001` on `v197_001`; tables
  `market_shock_state` (single row) and `market_shock_readings`;
  `MarketShockRepository.record()` writes reading + state (+ optional notice
  event in the v197 queue) in one transaction; the nightly `daily_recap`
  prunes readings older than `SHOCK_READINGS_KEEP_DAYS`.
- **Scan wiring** (V209-6): new `swingbot/core/scanning/shock_scan.py` holds
  every wiring decision (gate, snapshot from frames + live quotes + sector
  map, VIX from the tape, measure/step/record, current label). `_sync_run_scan`
  gains one call line and one timestamp line, no branch. Only
  `loops.py:252` passes `step_shock=True`.
- **Plan stamp** (V209-7, V209-8): the label travels as an argument
  (`shock_state`) through `_attach_item_plan`, `_rebuild_item`,
  `_maybe_run_strategy_pass`'s `asof_of`, `attach_plan_v2`, and
  `QualifyContext`; `params.stamp_entry_context` merges it into
  `entry_context` after the feature dict. Never in `FEATURE_KEYS`.
- **Notices** (V209-9, V209-10): a third v197 queue kind `market_shock`
  (validator, renderer, delivery dispatch); payload, open-long lines and the
  rate limit in new `swingbot/core/scanning/shock_notices.py`.
- **Admin** (V209-11): `/api/v1/market/tape` gains a `shock` object; the SPA
  tape shows a badge.
- **Replay** (V209-12): a frozen 2026-11-05 fixture (Alpaca 15-minute bars,
  synthetic fallback recorded as such) replayed through `measure`/`step`.
- **Release** (V209-13): production checks, rollback doc line, bump, deploy
  in `shadow`.
- **Screen runner** (V209-14, V209-15): `scripts/backtest/screen_idea.py`
  gains the `level` context path and the printed read-outs, gated on
  `idea.context_kind == "level"` so every other idea's path is untouched.
- **Context data** (V209-16): `BREADTH_ATR1.csv` builder, `^VIX.csv` fetch,
  `listing()` exclusion, append-only context-hash pin.
- **Ideas** (V209-17, V209-18): `_shock_breakdown.py` family module + two
  idea modules, registered in `IDEA_MODULES`.
- **Runs + close-out** (V209-19): the two one-shot runs through
  `backtest-runner`, results docs and ledger rows, then `/panel` and
  `/close-out`.

**Tech stack:** Python 3.11, SQLAlchemy + psycopg 3, Alembic, discord.py,
Flask, pandas/numpy, pytest; Angular standalone components + signals,
Vitest via `frontend/scripts/ng-test.mjs`.

## Global Constraints

- **No trade changes.** `shadow` and `live` behave identically in this plan. No long is blocked, no short issued, no stop moved, no plan's levels, size or status altered by the detector.
- **`MARKET_SHOCK_MODE=off` is a byte-identical kill switch:** no reading, no state write, no notice, no `entry_context["shock_state"]` key (absent, not `None`). Unknown mode values fall back to `off`.
- **`shock_state` is never added to `swingbot/core/edge/context.py:FEATURE_KEYS`** and never stamped by `entry_context()` itself; it is merged into `plan.entry_context` by `params.stamp_entry_context` after the feature dict is built, and also after a feature-build failure (so `{"shock_state": ...}` survives T3's `entry_context = {}` fallback).
- **Only the scheduled `session_scan` steps the state** (`loops.py:252`, `step_shock=True` keyword), and only while `swingbot/core/market/session.py:is_regular_session(now)` is true. Never gate on `data.is_us_market_active()` or `in_session()`. `!check` (`commands.py:199`), the recap (`recap.py:104`), the admin-UI scan (`loops.py:489`) and the SHORT lane read the stored label and never write.
- **`run_scan` takes `step_shock: bool = False` by keyword only.** `_sync_run_scan` (CC 94) and `_session_scan_tick` (CC 15) gain **no branch**; all logic lives in `shock_scan.py`.
- **Planning never reads the shock repository.** The SHORT lane reads the stored label once per run at `short_run._sync_run_short_scan`'s entry, through `shock_scan.current_label()`.
- **Labels** are exactly `"NORMAL"`, `"SHOCK"`, `"RECOVERY"` (`shock.LABELS`). No row stored yet ⇒ `current_label()` returns `"NORMAL"` under `shadow`/`live`, `None` under `off`.
- **Reading rules (spec § The reading):** `breadth_frac` = share of contributing equities with `(last − prev_close) / atr14 ≤ −atr_k`; `sectors_down` counts sectors with ≥ 2 contributing members whose median ratio ≤ −atr_k; `sectors_total` counts sectors with ≥ 2 contributing members; the depth clause needs `sectors_total ≥ 1` and `sectors_down ≥ ceil(sectors_frac × sectors_total)`; `breadth_speed` only within the same session, else `None`; non-equities and names with < 15 completed bars or no fresh live quote are excluded; `n_names < min_names` ⇒ `insufficient=True` and `step` returns the state unchanged.
- **"Last" is the pass's live quote** (`live_prices`), never the frame's last bar. `live_prices` carry no timestamp, so the pass records `quotes_at` right after `fetch._fetch_live_prices` returns; when `now − quotes_at > SHOCK_QUOTE_MAX_AGE_S` every quote is treated as absent. `prev_close` is the close of the last **completed** session's bar (bar[-2] when bar[-1] is dated today in `US_MARKET_TZ`, else bar[-1]); `atr14` = `indicators.atr(completed_bars, 14)` last value.
- **Entry from NORMAL** needs the condition on **two consecutive** readings, and a reading with `minutes_since_open < SHOCK_OPEN_SETTLE_MIN` resets the streak to 0 and never counts. The open-settle rule also applies to RECOVERY → SHOCK re-entry; re-entry needs one qualifying reading, and "new SPY session low" needs an earlier reading in the same session.
- **VIX:** read from the tape's `^VIX` row via `read_tape` (never fetches); a row older than `SHOCK_VIX_MAX_AGE_S` or missing ⇒ `vix_*` fields `None`. Prior VIX close = `price / (1 + change_pct/100)`. Session high = running max of readings this session. Missing VIX never blocks entry into SHOCK; it leaves the RECOVERY VIX clause unmet.
- **RECOVERY → NORMAL** needs the RECOVERY conditions to hold on every reading for `RECOVERY_MIN_DWELL_MIN`; a reading where they fail resets the hold clock (`ShockState.hold_since = None`) without leaving RECOVERY unless a re-entry rule fires.
- **Notice copy, exact.** Footer line on entry into SHOCK and on a second leg: `The bot moved no stop and closed nothing. Stop move-up and long block are pending screen (v209 Track 2).` Through-stop marker: `THROUGH STOP`. Otherwise: `stop at broker untouched: <stop:.2f>`. Unknown last price: `last n/a` and `stop status unknown: <stop:.2f>`. Zero open longs: `No open longs.`
- **Rate limit:** at most one `market_shock` notice per `SHOCK_MIN_DWELL_MIN`, except any transition **into** SHOCK, which is always sent. Notices are routed to `config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID`, computed in the worker thread (never `bot.get_channel` there). A notice is a plain status embed, never an alert embed.
- **The two existing queue kinds are untouched** (`trade_closed`, `plan_transition`): their validators, renderers and tests do not change.
- **Revision id `v209_001`, `down_revision = "v197_001"`**, file `swingbot/core/db/migrations/versions/v209_001_market_shock.py`; working `downgrade()` dropping both tables; exactly one Alembic head. Neither table joins `TABLE_CHANNELS` (no SSE).
- **Screen-runner parity:** ideas without `CONTEXT_KIND` follow the existing path byte for byte. `tests/backtest_scripts/test_screen_context_runner.py::PARITY_DIGESTS` and `tests/backtesting/screen/test_long_byte_identical.py` must pass **unedited**; a changed digest is a stop and a `BLOCKED:` report, never a digest update.
- **Track 2 definitions are frozen at spec commit 79325c50** (spec § Track 2). A changed value is a new idea with a new name. `SHOCK_D` uses the frozen numbers (0.40 enter, 0.10 release breadth, VIX down day), never the Track 1 config fields.
- **One shot each.** No re-run, no `--tickers` real run, no window change; a `SCREEN-FAIL` / `SCREEN-UNDERPOWERED` is closed.
- **No file named `BREADTH_ATR1.csv` or `^VIX.csv` is ever seen by a ticker-listing script** (`cache_dir_source.listing()` skips `CONTEXT_ONLY_STEMS`); `SPY`, `TLT`, `UUP` stay listed.
- Every function written or changed < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py`); no legacy function's CC rises.
- Every UI change is checked at 390 px, 820 px and 1440 px; the badge never truncates the tape and wraps below it on narrow widths; badge copy `NORMAL` / `SHOCK` / `RECOVERY`, and `VIX missing` when `vix_level` is null.
- Narrow test runs only: backend `python scripts/dev/testrun.py file <test>`; frontend `node frontend/scripts/ng-test.mjs frontend --include <spec>`. **No task runs the full suite**; CI does after the push. A task whose tests reach Postgres runs `/replicate-prod-db` first (one shared `swing-db` container, port 56789, `.env` credentials never printed).
- `.env` values are read, never printed; production is reached only through `bash scripts/ops/ssh-hetzner.sh`.

## Review Focus

1. **Stale bars outside regular hours.** A pass at 08:00 ET (inside `is_us_market_active()`) or at 22:00 Berlin (inside `in_session()`) must not write a reading. Owner: V209-6.
2. **Overnight carry.** The first reading of a new session has `breadth_speed=None`, a new `vix_session_high`, a new SPY prior close; a gap-up repair reaches RECOVERY, a second leg down stays SHOCK. Owner: V209-4.
3. **Kill switch.** Under `off`, a plan built by each of the three lanes and both rebuild paths has no `shock_state` key and is byte-identical to the pre-v209 plan. Owner: V209-7, V209-8.
4. **Second leg notice.** RECOVERY → SHOCK inside the rate-limit window still enqueues. Owner: V209-10.
5. **Screen parity.** The `level` branch never runs for z-context or no-context ideas; digests unedited. Owner: V209-14, V209-15.
6. **No-lookahead in `BREADTH_ATR1`.** Truncating input at `t` leaves `d_breadth[t]` unchanged; ATR from bars ≤ `t−1`. Owner: V209-16.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A config | V209-1 | `config.py`, `.env.example`, `tests/test_config_v209_keys.py` | none; may start at once |
| B detector | V209-2 → V209-3 → V209-4 | `swingbot/core/market/shock.py` + `tests/market/test_shock_*.py` | one module: 3 adds `step` entry rules to 2's types, 4 adds the exit/carry rules to 3's table |
| C storage | V209-5 | `schema.py`, migration, `repositories/market_shock.py`, `loops.py` (`daily_recap` prune) | none; contract in the ledger, may run beside B |
| D wiring | V209-6 → V209-7 → V209-8 | `shock_scan.py`, `scan_run.py`, `loops.py:252`, `analyze.py`, `params.py`, `strategy_pass.py`, `qualify.py`, `short_run.py` | 6 needs A, B, C; 7 edits `scan_run.py` after 6 and consumes its `shock_state` local; 8 consumes 6's `current_label` and 7's `attach_plan_v2(shock_state=)` |
| E notices | V209-9 → V209-10 | `lifecycle_events.py`, `lifecycle_notifications.py`, `shock_notices.py` (9 creates, 10 extends), `shock_scan.py` (10) | 9 needs only B's `LABELS`; 10 needs 5's `record(notice_event=)`, 6's `run_shock_pass` and 9's kind |
| F admin | V209-11 | `admin/api_v1/market.py`, `frontend/src/app/{api/models.ts,stores/tape-feed.ts,shell/tape/*}` | needs C's repository only; may run beside D/E |
| G replay | V209-12 | `scripts/data/build_shock_replay_fixture.py`, `tests/fixtures/shock_replay_2026_11_05.json`, `tests/market/test_shock_replay_2026_11_05.py`, `tests/scripts/test_build_shock_replay_fixture.py` | needs B complete |
| H release | V209-13 | `docs/deploy/DEPLOY_HETZNER.md`, `VERSION.json`, `swingbot/admin/version_history.json` | needs every task V209-1..V209-12 merged and CI green |
| I runner | V209-14 → V209-15 | `scripts/backtest/screen_idea.py`, `screen/ideas/__init__.py`, `screen/diagnostics.py` | 15 extends 14's `level` branch in the same file |
| J context data | V209-16 | `scripts/data/build_breadth_context.py`, `scripts/data/fetch_vix_context.py`, `scripts/backtest/pin_context_hashes.py`, `cache_dir_source.py`, hash pin JSON | none against I (disjoint files); may run beside I |
| K ideas | V209-17 → V209-18 | `screen/ideas/_shock_breakdown.py`, two idea modules, `ideas/__init__.py` `IDEA_MODULES`, `test_ideas_registry.py` | 17 needs 14's `Idea.context_kind`/`state_mask`/`episode_phase`; 18 edits the same registry tuple and test after 17 |
| L runs + close-out | V209-19 | `docs/superpowers/results/`, ledger JSONL | needs I, J, K merged-ready and reviewed; the close-out half needs V209-13 deployed |

Track 1 (A–H) and Track 2 (I–L) share no file except
`swingbot/core/backtesting/screen/ideas/__init__.py` (Track 2 only), so the
two tracks may be implemented in either order on the same worktree branch.
Track 1 is merged and deployed at V209-13 without waiting for Track 2; the
shadow log starts accumulating while the screens are built.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V209-1 | "Market Shock" config section: `MARKET_SHOCK_MODE` + 18 thresholds | 1 | haiku | M `swingbot/config.py` (new section, `_MODE_VALUES` entry); M `.env.example`; C `tests/test_config_v209_keys.py` | `config.MARKET_SHOCK_MODE` (str, `off\|shadow\|live`, default `shadow`); floats `SHOCK_ATR_K` 1.0, `SHOCK_BREADTH_ENTER` 0.40, `SHOCK_SECTORS_FRAC` 0.6, `SHOCK_BREADTH_FAST` 0.25, `SHOCK_SPEED_ENTER` 0.10, `SHOCK_VIX_SPIKE_PCT` 15.0, `SHOCK_VIX_RELIEF` 0.05, `SHOCK_BREADTH_REENTER` 0.30, `SHOCK_BREADTH_EXIT` 0.20, `RECOVERY_VIX_OFF_HIGH_PCT` 5.0, `RECOVERY_SPY_RETRACE` 0.5; ints `SHOCK_MIN_DWELL_MIN` 45, `RECOVERY_MIN_DWELL_MIN` 30, `SHOCK_MIN_NAMES` 20, `SHOCK_VIX_MAX_AGE_S` 600, `SHOCK_OPEN_SETTLE_MIN` 15, `SHOCK_QUOTE_MAX_AGE_S` 300, `SHOCK_READINGS_KEEP_DAYS` 180; section `"Market Shock"`, all `hot_reloadable=True`, help text names `v209` |
| V209-2 | `shock.py`: types, thresholds, `measure` | 1 | sonnet | C `swingbot/core/market/shock.py`; C `tests/market/test_shock_measure.py` | `LABELS = ("NORMAL","SHOCK","RECOVERY")`; frozen `ShockThresholds(atr_k=1.0, breadth_enter=0.40, sectors_frac=0.6, breadth_fast=0.25, speed_enter=0.10, vix_spike_pct=15.0, vix_relief=0.05, breadth_reenter=0.30, breadth_exit=0.20, recovery_vix_off_high_pct=5.0, recovery_spy_retrace=0.5, min_dwell_min=45, recovery_min_dwell_min=30, min_names=20, vix_max_age_s=600, open_settle_min=15, quote_max_age_s=300)`; frozen `NameRow(ticker: str, sector: str \| None, last: float \| None, prev_close: float \| None, atr14: float \| None, is_equity: bool)`; frozen `VixTape(level: float \| None, chg_pct: float \| None, as_of: datetime \| None)`; frozen `ShockSnapshot(as_of: datetime, session_date: date, minutes_since_open: float, names: tuple[NameRow, ...], spy: NameRow \| None, qqq: NameRow \| None, vix: VixTape)`; frozen `ShockReading(as_of, session_date, minutes_since_open, breadth_frac: float \| None, sectors_down: int, sectors_total: int, breadth_speed: float \| None, spy_atr_move, qqq_atr_move, spy_last, spy_prev_close, spy_session_low: float \| None, spy_new_low: bool, spy_retrace: float \| None, vix_level, vix_chg_pct, vix_session_high, vix_off_high_pct: float \| None, n_names: int, insufficient: bool)` with `as_row() -> dict` (JSON-safe, ISO datetimes) and `classmethod from_row(row: dict) -> ShockReading`; `measure(snapshot, prev: ShockReading \| None, th: ShockThresholds = ShockThresholds()) -> ShockReading` (`spy_retrace` = 1.0 when the session low ≥ prior close, `None` without SPY) |
| V209-3 | `shock.py`: `ShockState` + `step` entry rules | 1 | sonnet | M `swingbot/core/market/shock.py`; C `tests/market/test_shock_step_entry.py` | frozen `ShockState(label="NORMAL", since: datetime \| None = None, session_date: date \| None = None, vix_session_high: float \| None = None, spy_prev_close: float \| None = None, entry_streak: int = 0, hold_since: datetime \| None = None, prev_breadth: float \| None = None)` with `as_row() -> dict`, `classmethod from_row(row: dict \| None) -> ShockState`; `step(state, reading, th) -> ShockState` (insufficient ⇒ state unchanged); `entry_condition(reading, th) -> bool`; `RULES: dict[str, Callable[[ShockState, ShockReading, ShockThresholds], ShockState]]` keyed by label |
| V209-4 | `shock.py`: SHOCK → RECOVERY → NORMAL, second leg, overnight carry | 1 | sonnet | M `swingbot/core/market/shock.py`; C `tests/market/test_shock_step_exit.py` | `recovery_condition(state, reading, th) -> bool`; `reentry_condition(state, reading, th) -> bool`; `RULES["SHOCK"]`, `RULES["RECOVERY"]` complete; `ShockState.session_date`/`vix_session_high`/`spy_prev_close`/`prev_breadth` carried as specified |
| V209-5 | `v209_001` tables + `MarketShockRepository` + nightly prune | 2 | opus | M `swingbot/core/db/schema.py`; C `swingbot/core/db/migrations/versions/v209_001_market_shock.py`; C `swingbot/core/db/repositories/market_shock.py`; M `swingbot/commands/scanning/loops.py` (`_prune_shock_readings`, called in `daily_recap` beside `_prune_alert_posts`); C `tests/db/test_v209_market_shock_schema.py`; C `tests/db/test_market_shock_repository.py`; M `tests/db/test_unknown_field_round_trip.py` if it enumerates tables | `schema.market_shock_state`: `id` SmallInteger PK (always 1), `label` Text NOT NULL, `since` TIMESTAMPTZ NULL, `session_date` Date NULL, `vix_session_high` Float(53) NULL, `last_reading_id` BigInteger NULL FK → `market_shock_readings.id` ON DELETE SET NULL, `last_notice_at` TIMESTAMPTZ NULL, + `doc` (`{"state": ShockState.as_row()}`), `updated_at`; `schema.market_shock_readings`: `id` BigInteger identity PK, `as_of` TIMESTAMPTZ NOT NULL (indexed), `session_date` Date NOT NULL, `state_after` Text NOT NULL, `breadth_frac`, `breadth_speed`, `spy_atr_move`, `qqq_atr_move`, `vix_level`, `vix_chg_pct`, `vix_off_high_pct` Float(53) NULL, `sectors_down`, `sectors_total`, `n_names` Integer NOT NULL, `insufficient` Boolean NOT NULL, + `doc` (`ShockReading.as_row()`), `updated_at`; `market_shock_repo() -> MarketShockRepository` with `record(reading: dict, state: dict, *, state_after: str, notice_event: dict \| None = None, conn=None) -> int` (one transaction: insert reading, upsert state row 1 with `last_reading_id`, enqueue `notice_event` via `NotifyQueueRepository().enqueue(event, conn=)` and set `last_notice_at` when given; returns reading id), `current_state(*, conn=None) -> dict \| None` (promoted columns + `doc`), `latest_reading(*, conn=None) -> dict \| None`, `prune_before(cutoff: datetime, *, conn=None) -> int`; `loops._prune_shock_readings() -> None` (async, never raises) |
| V209-6 | `shock_scan.py` wiring, `run_scan(step_shock=)`, regular-hours gate | 2 | opus | C `swingbot/core/scanning/shock_scan.py`; M `swingbot/core/scanning/scan_run.py` (`run_scan`, `_run_scan_in_context`, `_sync_run_scan`: one `quotes_at` line + one call line); M `swingbot/commands/scanning/loops.py` (line 252 call adds `step_shock=True`); M `tests/scanning/test_run_scan_scan_id.py` (fake accepts `step_shock`); C `tests/scanning/test_shock_scan.py`; C `tests/commands/test_shock_step_gate.py` | `shock_scan.shock_mode() -> str`; `thresholds_from_config() -> ShockThresholds`; `read_vix(now: datetime, th) -> VixTape`; `build_snapshot(frames: Mapping[str, pd.DataFrame], live_prices: Mapping[str, float], sector_of: Mapping[str, str], *, now: datetime, quotes_at: datetime \| None, vix: VixTape, th: ShockThresholds, spy_ticker: str, qqq_ticker: str = "QQQ") -> ShockSnapshot`; `should_step(step_shock: bool, now: datetime) -> bool`; `run_shock_pass(*, step_shock: bool, frames, live_prices, sector_of, quotes_at, now: datetime \| None = None, repo=None) -> str \| None` (the label planning stamps; `None` under `off`; failures through `swallowed(log, "scan.shock.pass", ...)` then fall back to `current_label()`); `current_label(*, repo=None) -> str \| None`; `_sync_run_scan(..., step_shock: bool = False)` binds local `shock_state`; `run_scan(..., *, step_shock: bool = False)` |
| V209-7 | Stamp `shock_state` on confluence, requote and strategy plans | 2 | opus | M `swingbot/core/planning/params.py` (`stamp_entry_context` merge); M `swingbot/core/scanning/analyze.py` (`attach_plan_v2(..., shock_state=None)`); M `swingbot/core/scanning/scan_run.py` (`_attach_item_plan`, `_rebuild_item`, the `functools.partial`, `_maybe_run_strategy_pass` + its `asof_of`); C `tests/scanning/test_shock_state_stamp.py`; C `tests/planning/test_stamp_entry_context_shock.py` | `attach_plan_v2(..., shock_state: str \| None = None)` (adds `"shock_state"` to the asof dict only when not `None`); `_attach_item_plan(item, scenario, df, regimes, regime, shock_state=None)`; `_rebuild_item(..., shock_state=None)`; `_maybe_run_strategy_pass(..., shock_state: str \| None = None)`; `stamp_entry_context` writes `plan.entry_context["shock_state"]` when `asof.get("shock_state") is not None`, after the feature dict and after the failure fallback |
| V209-8 | SHORT lane reads the label; byte-identical long/short pins | 2 | opus | M `swingbot/core/scanning/qualify.py` (`QualifyContext.shock_state`, `_attach_plan`); M `swingbot/core/scanning/short_run.py` (`_sync_run_short_scan`, `_qualify_context`, `_bare_context`); C `tests/scanning/test_shock_short_lane.py`; C `tests/scanning/test_shock_plans_byte_identical.py` | `QualifyContext.shock_state: str \| None = None` (last field); `short_run._qualify_context(require_confirmation, frames, lane, shock_state=None)`; `short_run._bare_context(..., shock_state=None)`; `_sync_run_short_scan` calls `shock_scan.current_label()` exactly once per run |
| V209-9 | `market_shock` notify-queue kind end to end | 3 | sonnet | M `swingbot/core/infra/lifecycle_events.py`; M `swingbot/core/scanning/lifecycle_notifications.py` (dispatch on kind); C `swingbot/core/scanning/shock_notices.py` (renderer half); C `tests/infra/test_lifecycle_events_market_shock.py`; C `tests/scanning/test_shock_notice_render.py` | `lifecycle_events.KINDS = ("trade_closed", "plan_transition", "market_shock")`; `_validate_shock_payload(payload)` requires `label` and `prior_label` in `shock.LABELS`, aware ISO `occurred_at`, dict `reading` (a `ShockReading.as_row()`), list `open_longs`, bool `entry_into_shock`; `shock_notices.build_shock_embed(event: dict) -> discord.Embed`; `shock_notices.long_line(row: dict) -> str` where `row = {"ticker", "entry", "stop", "last" (float \| None), "open_r" (float \| None), "age_min" (int), "through_stop" (bool)}`; `shock_notices.FOOTER` (exact copy in Global Constraints) |
| V209-10 | Notice payload, open longs, rate limit, enqueue in the stepped pass | 3 | sonnet | M `swingbot/core/scanning/shock_notices.py`; M `swingbot/core/scanning/shock_scan.py` (`run_shock_pass` builds and passes `notice_event`); C `tests/scanning/test_shock_notice_payload.py` | `open_long_rows(trades: list[dict], last_prices: Mapping[str, float], now: datetime) -> list[dict]` (open trades with `direction == "bullish"`, sorted by ticker); `should_notify(prior_label: str, new_label: str, last_notice_at: datetime \| None, now: datetime, min_dwell_min: int) -> bool`; `notice_payload(prior: ShockState, new: ShockState, reading: ShockReading, open_longs: list[dict], now: datetime) -> dict`; `notice_event(payload: dict, *, as_of: datetime) -> dict` (`make_event(transition_id=f"market_shock:{as_of.isoformat()}", kind="market_shock", target_channel_id=config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID, ...)`) |
| V209-11 | Admin tape `shock` object + SPA badge at three widths | 3 | sonnet | M `swingbot/admin/api_v1/market.py` (`_shock_block()`, both returns of `tape()`); C `tests/admin/test_api_v1_tape_shock.py`; M `frontend/src/app/api/models.ts`; M `frontend/src/app/stores/tape-feed.ts` (+ spec); M `frontend/src/app/shell/tape/tape.ts`, `tape.css`, `tape.spec.ts` | API: `"shock": null` under `off` or no state row, else `{"label", "since", "as_of", "breadth_pct", "sectors_down", "sectors_total", "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_missing": bool}`; TS `TapeShock` with those keys, `TapeResponse.shock?: TapeShock \| null`; `TapeFeed.shock: Signal<TapeShock \| null>`; badge element `.shock-badge[data-label]` |
| V209-12 | 2026-11-05 replay fixture (Alpaca, synthetic fallback) + replay test | 3 | sonnet | C `scripts/data/build_shock_replay_fixture.py`; C `tests/fixtures/shock_replay_2026_11_05.json`; C `tests/market/test_shock_replay_2026_11_05.py`; C `tests/scripts/test_build_shock_replay_fixture.py` | fixture JSON `{"source": "alpaca" \| "synthetic", "vix_interpolated": true, "note": str, "steps": [{"as_of", "minutes_since_open", "vix": {"level", "chg_pct"}, "spy": NameRow-dict, "qqq": NameRow-dict \| null, "names": [NameRow-dict]}]}`; replay asserts first SHOCK `as_of ≤ 2026-11-05T14:36:00Z` |
| V209-13 | Track 1 release: prod checks, rollback line, bump, deploy in `shadow` | 4 | opus | M `docs/deploy/DEPLOY_HETZNER.md` (image-only rollback line + `### v209: market shock tables` section); M `VERSION.json`; M `swingbot/admin/version_history.json` | production `MARKET_SHOCK_MODE=shadow`; verified `TAPE_SHARED_ENABLED`, `MARKETDATA_LAYER`, `DAILY_DELTA_FETCH`, live-price path; the bump is released here, so V209-19's `/close-out` finds it on disk |
| V209-14 | Screen runner `CONTEXT_KIND = "level"` path | 4 | opus | M `swingbot/core/backtesting/screen/ideas/__init__.py` (`Idea.context_kind`, `state_mask`, `episode_phase`; `_load`); M `scripts/backtest/screen_idea.py` (`_context_frame`, `load_context`, `_overlap`, `with_diagnostics`, `_render_context`, `hypothesis`); M `swingbot/core/backtesting/screen/diagnostics.py` (`scope_sentence` level branch); C `tests/backtest_scripts/test_screen_level_context.py` | `Idea.context_kind: str = "z"` (module attr `CONTEXT_KIND`); `Idea.state_mask: Callable[[pd.DataFrame, Mapping[str, pd.DataFrame]], pd.Series] \| None = None` (module attr `state_mask`); `Idea.episode_phase: Callable[[pd.DataFrame, Mapping[str, pd.DataFrame]], pd.Series] \| None = None` (values `"before_peak"`, `"day_after_peak"`, `"later"`, else NaN); `load_context(cache_dir, tickers, *, end, kinds: Mapping[str, str] \| None = None)`; level files: `check_raw_index` + `check_contiguous`, no `check_z_coverage`; `_overlap` passes the loaded context to a family partner; `diagnostics.scope_sentence` level branch reads `idea.params["scope"]` |
| V209-15 | Printed read-outs for level ideas | 4 | opus | M `scripts/backtest/screen_idea.py`; C `tests/backtest_scripts/test_screen_shock_readouts.py` | `SHOCK_STRESS_SLIPPAGE_FACTOR = 3`; `--preflight` CLI flag (prints and exits, no race, no write); `preflight(idea, data, frames) -> dict` (`shock_days_by_year`, `shock_weeks_by_year`, `events_by_year`); `shock_matched_null(...)` (K = 20 from the same ticker's state-mask days, via `_books(exclude=~mask)`); `gap_bucket(gap: float) -> str` (`"<=-1%"`, `"-1%..+1%"`, `">=+1%"`); results-doc section `## Shock read-outs (printed, never gating)` with second null, control, preflight, gap split, episode-day split, 3× stress, `skipped_overlap` |
| V209-16 | Context files: `BREADTH_ATR1`, `^VIX`, `listing()` exclusion, hash pin | 5 | opus | C `scripts/data/build_breadth_context.py`; C `scripts/data/fetch_vix_context.py`; C `scripts/backtest/pin_context_hashes.py`; M `scripts/backtest/cache_dir_source.py`; M `tests/history_store/test_cache_dir_scripts.py`; C `tests/backtest_scripts/test_shock_context_files.py`; M `docs/superpowers/results/2026-10-18-v174-context-hashes.json` (append two keys) | `breadth_series(frames: Mapping[str, pd.DataFrame], intervals, sessions: pd.DatetimeIndex, *, k: float = 1.0) -> pd.Series` (fraction per session, ATR14 shifted one bar; a session with no valid member raises); `write_context_csv(series, path)` (Date,Open,High,Low,Close,Volume; OHLC = value, Volume 0); `^VIX.csv` aligned to SPY sessions or `SystemExit` naming the first mismatched date; `cache_dir_source.CONTEXT_ONLY_STEMS = frozenset({"BREADTH_ATR1", "^VIX"})`; `pin_context_hashes.add_pins(cache_dir, path, tickers) -> dict` (append-only, refuses to change an existing SHA) |
| V209-17 | `_shock_breakdown` family + `shock_support_break_short` | 5 | opus | C `swingbot/core/backtesting/screen/ideas/_shock_breakdown.py`; C `swingbot/core/backtesting/screen/ideas/shock_support_break_short.py`; M `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES`); M `tests/backtesting/screen/test_ideas_registry.py`; C `tests/backtesting/screen/test_shock_breakdown_state.py`; C `tests/backtesting/screen/test_idea_shock_support_break_short.py`; M `tests/backtest_scripts/test_screen_context_runner.py` fixtures only if the new context stems must exist in `_ctx_cache` (digests unedited) | `_shock_breakdown.FAMILY = ("shock_support_break_short", "shock_failed_bounce_short")`; `CONTEXT = ("BREADTH_ATR1", "^VIX")`; `ENTER = 0.40`, `RELEASE = 0.10`; `daily_state(breadth: pd.Series, vix_close: pd.Series) -> pd.Series[bool]`; `episode_ids(state: pd.Series) -> pd.Series`; `state_on(df, context) -> pd.Series[bool]`; `episode_phase(df, context) -> pd.Series`; `break_20d(df) -> pd.Series[bool]`; idea module attrs `CONTEXT_KIND = "level"`, `RACE = "fixed"`, `CAP = 10`, `DIRECTION = "short"`, `control_events(df)` (shock ignored), `state_mask = _shock_breakdown.state_on` |
| V209-18 | `shock_failed_bounce_short` | 5 | opus | C `swingbot/core/backtesting/screen/ideas/shock_failed_bounce_short.py`; M `swingbot/core/backtesting/screen/ideas/__init__.py`; M `tests/backtesting/screen/test_ideas_registry.py`; C `tests/backtesting/screen/test_idea_shock_failed_bounce_short.py` | `_shock_breakdown.failed_bounce(df) -> pd.Series[bool]` (spec Idea 2 clauses 1–5, latest `b` wins) — added to `_shock_breakdown.py`; idea module with the same attrs as V209-17's idea |
| V209-19 | The two one-shot screens, results, ledger, then `/panel` + `/close-out` | 5 | opus | C `docs/superpowers/results/<run date>-screen-shock_support_break_short.md`; C `docs/superpowers/results/<run date>-screen-shock_failed_bounce_short.md`; M `docs/superpowers/results/preregistration-ledger.jsonl` (two rows, by `publish()`); M the plan files (moved by `/close-out`) | two ledger rows with verdicts; results docs citing `ledger_qvalues` across v104 Part B, v182 and both v209 ideas |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-05-v209-market-shock-detector_1-detector-core.md` | V209-1..V209-4 | config section; pure `shock.py` (`measure`, `step` entry and exit rules) |
| 2 | `2026-11-05-v209-market-shock-detector_2-storage-and-wiring.md` | V209-5..V209-8 | `v209_001` + repository + prune; scan wiring and gate; label threading through every lane; byte-identical pins |
| 3 | `2026-11-05-v209-market-shock-detector_3-notices-admin-replay.md` | V209-9..V209-12 | `market_shock` queue kind; notice content and rate limit; admin badge; 2026-11-05 replay |
| 4 | `2026-11-05-v209-market-shock-detector_4-release-and-runner.md` | V209-13..V209-15 | Track 1 release; screen runner `level` path and printed read-outs |
| 5 | `2026-11-05-v209-market-shock-detector_5-context-ideas-runs.md` | V209-16..V209-19 | `BREADTH_ATR1` / `^VIX` context files; the two ideas; the one-shot runs and close-out |

## Notes for part writers

- **The ShockState fields beyond the spec's list** (`entry_streak`,
  `hold_since`, `prev_breadth`) are the bookkeeping the two-consecutive rule,
  the RECOVERY hold and the "rising breadth" re-entry need; they live in
  `market_shock_state.doc["state"]`, not in promoted columns.
- **`measure` takes `th` as a defaulted third argument**: the spec writes
  `measure(snapshot, prev)`, and the call stays valid; `atr_k`, `min_names`
  and `vix_max_age_s` come from `th`.
- **Quote freshness** (V209-6): `live_prices` has no per-quote time, so the
  whole pass's quotes share `quotes_at`; a name absent from `live_prices` is
  excluded from the reading.
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
- **Hash pin** (V209-16): the existing pin
  `docs/superpowers/results/2026-10-18-v174-context-hashes.json` (TLT, UUP)
  would refuse every context run once `BREADTH_ATR1`/`^VIX` are registered
  (brief D6). `pin_context_hashes.py --add BREADTH_ATR1 ^VIX` appends their
  SHAs once, after the files are built, and the JSON is committed; the
  runner's `hash_refusal`/`write_hashes` are unchanged.
- **The cache dir** for the runs is the one the v182 screens used (read its
  results doc for the `--cache-dir` and `--membership` values); both new
  context files are written there.
- **Episode-day split** (V209-15/17) is an ex-post, printed-only
  classification (the episode's breadth peak is known only after the
  episode); it never feeds the events, the null or the verdict.
- **`scope_sentence` level branch** (V209-14) reads a `PARAMS["scope"]`
  string each level idea carries (V209-17/18 write it); level ideas'
  `PARAMS` hold their frozen numbers and that sentence, no `z`/`series`.
- **The bump** is released in V209-13 (deploy needs it); V209-19's
  `/close-out` reads `VERSION.json` and must not bump a second time; the
  task states this to the closer.
