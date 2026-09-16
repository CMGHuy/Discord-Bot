# v87 — The intraday bar archive: keeping the 15m and 5m tape before Yahoo forgets it

**Version:** ui 1.18.2 · bot 1.9.0
**Bump:** bot patch
**Edge:** none (integrity) — see §6
**Date:** 2026-09-15

## 1. Why this exists

The human partner wants the bot to identify trade plans better, and one of the
three places a better signal can act is **entry timing**: triggering on a 1h
close instead of the first tick through a level, skipping the opening 30
minutes, waiting for a 15m higher low or a VWAP reclaim. None of that can be
measured today.

- TRAIN is 2020–2023 and VALIDATION 2024–2025. Yahoo serves 1h bars for ~730
  trading days, and **15m/5m bars for only the trailing ~60 days, 1m for ~30**
  (`docs/claude/known-traps.md`). A sub-hourly entry rule has no history to be
  backtested on, from this source, at any tier.
- Production runs `MARKET_DATA_TIMEFRAMES=monthly,weekly,daily,hourly`. Every
  day that passes, one more session of 15m/5m tape falls out of Yahoo's
  window unrecorded, and it cannot be recovered later.
- The E29 intraday annotation ("⏱ Intraday timing") is live-only and **not
  journaled onto the plan**, and `TradePlanV2.created_at` is a date, not a
  time. Even the plans the bot already issues cannot be lined up against the
  intraday tape they were issued into.

This spec starts the clock. It changes no trigger, no alert and no decision.

## 2. What already exists (verified 2026-09-15)

The archiver is already built; it has just never been pointed at sub-hourly
frames.

- `swingbot/core/marketdata/data_store.py:TIMEFRAMES` defines `15min` (`15m`,
  `max_days` 60) and `5min` (`5m`, `max_days` 60) alongside the four training
  frames.
- `commands/scanning/loops.py` `market_data_refresh` reads
  `config.MARKET_DATA_TIMEFRAMES` on every wake and calls
  `data_refresh.refresh_all` over the watchlist.
- `data_refresh.refresh_symbol` **only ever adds bars**: a cold pull fetches
  full depth, a warm pull fetches bars newer than the last cached one, and both
  go through `_merge_save`. `_record` tracks each pair's earliest bar
  specifically to catch an archive that shrinks.
- `refresh_all` honours `MARKET_DATA_REFRESH_BUDGET_SECONDS` (default 120) so a
  large backlog spreads across wakes instead of starving the Discord gateway
  heartbeat (production incident 2026-08-24).
- `market_data/` stays as files under v67; it is on that plan's explicit
  do-not-migrate list (`2026-08-29-v67-json-to-postgres_0-index.md:56`).

## 3. Design

### 3.1 Archive 15m and 5m bars

Add `15min,5min` to `MARKET_DATA_TIMEFRAMES`: in production's `.env`, and
mirrored into the repo as the `config.py` Field default and `.env.example`
(`working-conventions.md`: a production config change is mirrored and
committed before the task is done). The Field's help text currently says
sub-hourly frames "cannot support training — leave them out unless you want
live entry timing"; it is rewritten to say they are archived forward for a
future entry-timing measurement, and that the archive is only as deep as the
day it started.

`1min` is **excluded**: ~390 bars a session is ~600 MB a year across the
watchlist and a 7-day request chunk, for a resolution that swing horizons of
2w–9m do not need. 15m and 5m together are ~150 MB a year.

### 3.2 Refresh cadence

`REFRESH_HOURS` has no entry for sub-hourly frames, so they fall back to
`DEFAULT_REFRESH_HOURS = 24`. That is kept: a 24h staleness window against a
60-day provider window leaves ~59 days of slack before a missed refresh loses
data. `REFRESH_HOURS` gains explicit `15min: 24.0` and `5min: 24.0` entries so
the value is stated, not inherited.

`loops.py` sorts timeframes by `REFRESH_HOURS` before the sweep, so sub-hourly
frames refresh after hourly. When the budget binds, they are the ones deferred
to the next wake — the right priority, since hourly feeds live E29 context and
sub-hourly feeds nothing live.

The cold pull for ~85 symbols × 2 frames is the one heavy moment. It is
verified on production after rollout (§4), not assumed to fit.

### 3.3 `issued_at` on every live plan

`TradePlanV2` gains one field, `issued_at: str | None = None` — the UTC ISO
timestamp at which the live scan attached the plan. Set on the live path only,
in `analyze.attach_plan_v2` — the single constructor every plan the live scan
persists goes through; the backtest leaves it `None`, because a replayed plan
has no wall-clock issuance. Old records load with
`None`: `plan_from_dict` already filters to known fields, and the field takes a
default, so it goes at the end of the dataclass.

Deliberately **not** stored: the E29 reading itself. It is a pure function of
the 1h tape and the issuance time, both of which are now archived, so storing
it would be a second copy that can disagree with the first.

### 3.4 Coverage report

`scripts/ops/intraday_archive_coverage.py` prints, per timeframe, the symbol
count, the earliest and latest bar across the archive, the median depth in
sessions, and the symbols whose latest bar is more than 3 sessions old. Run on
production, it answers "is the archive growing" in one screen. It reads
`market_data/` through `data_store.load_from_disk`, never a hand-built path
(`known-traps.md`).

## 4. Rollout

1. Merge the code (§3.2–3.4) and the mirrored defaults (§3.1).
2. Deploy to production; set `MARKET_DATA_TIMEFRAMES` in `/opt/swing-bot/.env`;
   hot-reload via SIGHUP.
3. After the first two wakes, check the bot log (`/opt/swing-bot/logs/*.log`,
   not `docker logs`) for the refresh summary line and for any gateway
   disconnects, and run the coverage script. Both `15min` and `5min` must show
   the full watchlist with ~60 days of depth within 24 hours.
4. One week later, run the coverage script again: earliest bar unchanged,
   latest bar current. That is the task's done condition.

## 5. v67 coordination

`issued_at` lives inside the plan's `doc` JSONB; no column is added. v67 task
**P2-07** (`2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md`) gets a
note in the same commit that adds the field, matching the one v81 left there
for `notified_stop`/`pending_notice`, and its round-trip fixture carries
`issued_at` so an importer that drops unknown keys fails the test.

## 6. Edge

**`none (integrity)`.** On its own this buys nothing and says so. The yield
argument: it is the only route by which an entry-timing hypothesis can ever
be measured on this repo's data, and it preserves raw bars rather than a few
trigger variants chosen today, so the eventual measurement can test rules no
one has proposed yet. Each week it does not run is a week of tape that no
later measurement can recover.

## 7. Testing

- `issued_at` is set on a live-attached plan, survives `plan_to_dict` →
  `plan_from_dict`, and a pre-v87 record without the key loads as `None`.
- A replayed plan (`backtest_scenarios.replay_scenarios`) carries
  `issued_at is None`.
- `REFRESH_HOURS` resolves `15min`/`5min` to 24h, and a sweep with the budget
  binding defers sub-hourly frames after hourly.
- The config Field default parses to six timeframe names, each resolvable by
  `data_store.timeframe_name`.
- The coverage script runs against a `tmp_path` archive built with
  `make_ohlcv`-style intraday frames and reports a stale symbol correctly.
- One full-suite run, as the plan's final task.

## 8. Out of scope

- Any entry-timing rule, trigger variant or alert change. The measurement that
  uses this archive is a separate, later spec, and it cannot be written until
  the archive holds enough sessions to power it.
- Pre-market and after-hours bars (`prepost`). Leading-signal work was parked
  in the 2026-09-15 brainstorm.
- Backfilling sub-hourly history from a paid or alternative provider.
- Moving `market_data/` into Postgres.

## Parallelisation

- **Group 1 (parallel):** the refresh-cadence change (`data_refresh.py`), the
  coverage script (`scripts/ops/`), and the `issued_at` field
  (`plan_types.py`, the live attach site, its tests) — disjoint files, no
  shared symbol.
- **Sequential:** the v67 P2-07 note lands in the same commit as `issued_at`.
  The config default and `.env.example` mirror after Group 1 (the Field help
  text describes the cadence Group 1 sets). Production rollout after merge.
  The full-suite run last.
