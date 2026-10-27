# v184 — Stop-monitor liveness: alert when open stops stop being checked

**Version:** ui 1.33.1 · bot 2.14.2 (at writing)
**Bump:** bot patch — one new heartbeat key (`monitor`) written by the trade monitor, and two new incident kinds in the out-of-process watch. No alert, plan, stop or fill behaviour changes. The partner gains an ops post when stops go unchecked.
**Edge:** none (integrity) — protects the R the book already books. In August, a stalled monitor turned four −1R stops into fills of −3.3R to −6.0R (§ Why). The prediction is that this changes nothing measurable in ExpR. Its value is the number of hours with stops unchecked and nobody told, which today goes uncounted.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer
**Status:** spec written 2026-10-21 after the partner chose, from the 2026-10-21 scout slate, to verify the stop-enforcement lead and then to spec the fix. Revised the same day after the panel (see `## Panel review`). Evidence, and the correction that the fetch is bounded: `docs/superpowers/results/2026-10-21-scout-slate.md` § Stop-enforcement check.

## Why

The production DB shows two stalls (read-only check, 2026-10-21):

- No trade or plan closed between `2026-08-03 16:18:02` UTC and `2026-08-04 18:55:15`. Then 25 trades and 33 plan status entries closed within 28 seconds, each at that moment's quote.
- On 2026-08-05 nothing closed for about 3.5 h, then 7 trades closed between 15:34:01 and 15:34:08.
- The VM had been up since 2026-07-31. This was not a reboot, and the August logs are gone.

The four worst fills in the 08-04 batch can be re-derived from the trades table, read with `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" < scripts/ops/export_book_rows.sh`, filtered to `closed_at` 2026-08-04 18:55. R is `(exit − entry) / (entry − stop)`, and all four were longs:

| ticker | entry | stop | exit | R |
|---|---|---|---|---|
| NBIS | 203.03 | 198.60 | 176.30 | −6.03 |
| DELL | 421.24 | 412.35 | 390.11 | −3.50 |
| GLW | 144.51 | 141.16 | 132.89 | −3.47 |
| MRNA | 57.29 | 55.88 | 52.70 | −3.26 |

These four trades describe the incident. They are not a pooled figure.

The likely hang causes were fixed afterwards. On 2026-08-24 the monitor skipped its tick while a scan ran. On 2026-09-17 a yfinance call was unbounded. Today's quote fetch is process-bounded (`plan_manager.monitor_quotes` → `fetch._run_bounded`).

What was never fixed is **visibility**. Nothing anywhere notices when the stops stop being evaluated:

1. `runstate._write_heartbeat` is the only liveness stamp. It is written by `session_scan` at the **start** of its tick (`swingbot/commands/scanning/loops.py:195`), never by `trade_monitor` (`loops.py:628`).
2. `scripts/ops/heartbeat_watch.sh` reads only that stamp. A wedged or dead `trade_monitor` leaves it fresh, and so does a monitor that ticks without pricing anything.
3. A failed or empty quote batch returns `{}`. The tick then checks no stop, logs a warning and carries on.
4. `@trade_monitor.error` restarts the loop only when an exception escapes. A hang never reaches it.
5. The plan manager's `poll()` is the only path that closes plan-linked trades (`plan_manager.py:622-660`), and the stops that stalled in August were plan stops. Any liveness signal has to cover open plans, not only open trade rows.

## What changes

### 1. The monitor stamps its own liveness (bot)

The trade monitor merges one key, `monitor`, into the heartbeat row. Only the monitor writes this key. The merge is `doc || fields` (`runstate._update_heartbeat`), which replaces the whole `monitor` value, so the monitor always writes the full object.

**Source of truth.** The monitor keeps `priced_at` and `started_at` in process memory (module state in `loops.py`) and never reads the row back. `started_at` is set once, when the process starts. `priced_at` starts as `null` and only ever moves forward. After a restart, `priced_at` is `null` until the first fully priced tick, and the watch then counts from `started_at` (§ 2). A wedge followed by a restart therefore never reads as fresh.

**Fields:**

| field | meaning |
|---|---|
| `started_at` | UTC ISO time this bot process started |
| `tick_at` | UTC ISO time the tick ended (see Stamp timing) |
| `outcome` | `ok`, or `raised` when anything in the tick raised before the stamp |
| `positions` | the set of stops the monitor is responsible for: the union of open-trade tickers and `plan_store.open_plans()` tickers. `null` when either read failed, meaning unknown rather than zero |
| `unquoted` | sorted tickers in `positions` with no usable price this tick, using exactly the filter that gates the close call: `ticker not in live_prices` for trade tickers, and for plan tickers the set `poll()` actually priced (below). Capped at 20 names, plus `unquoted_count` |
| `fetch_failed` | true when the shared quote batch returned nothing because it failed or timed out (`_run_bounded` returned `None`), as distinct from "no fresh print" |
| `check_errors` | tickers whose `close_if_live_price_hit` or `check_near_tp_timeout` raised this tick, plus `"<plan manager>"` when `run_manager_tick` raised. They count as not checked |
| `priced_at` | last time a tick ended with `outcome == ok`, `positions` known, `unquoted` empty and `check_errors` empty. A tick with `positions` known and empty also counts. A raised tick never advances it |
| `market_open` | NYSE regular session at `tick_at`: `d not in NYSE_HOLIDAYS and RTH_OPEN <= t < session_close(d)` on `now_et()` (`swingbot/core/market/session.py:19,126,229`). This deliberately differs from `is_regular_session`, which ignores holidays and half-days, and from `in_session()`, which is the Berlin scan window |

**Plan tickers without an extra fetch.** The plan manager exposes the tickers its last `poll()` priced and failed to price. The plan names the accessor, and the data comes from the same `monitor_quotes` call. The stamp must not add a second `monitor_quotes` call or any quote-cache read: the 15-second shared batch cache (`data.py:165`) must not be refreshed or evicted by the stamp.

**Stamp timing.** Every variable the stamp reads is set to "unknown" before the tick's work begins. The stamp is written in a `finally` at the end of the tick, after the closes, `run_manager_tick`, the equity sample and the Discord posts. The write goes through `asyncio.to_thread`, like the tick's other DB calls. Because it sits at the end, a tick that wedges anywhere leaves `tick_at` ageing. A slow Discord post can therefore age `tick_at` even when the stops were evaluated. This is accepted: `priced_at` separates "stops checked" from "tick complete", and 300 s is five times the loop interval. A failed stamp write is counted (`swallowed`) and never raises into the tick.

**Reader cost.** Every write to `bot_heartbeat` raises the `bot` SSE event (`swingbot/core/db/events.py:21`). The admin store refreshes on it (`frontend/src/app/stores/connection.store.ts:156-161`), and the System and Versions routes re-resolve. A stamp every 60 s raises that event about five times more often than the scan's stamp does today. The plan checks whether the handler debounces. If it does not, the stamp writes at most every 120 s, plus immediately whenever `outcome`, `unquoted`, `fetch_failed` or `check_errors` changes, which keeps `tick_at` well inside the 300 s threshold.

### 2. The watch gains two incident kinds (ops script)

`heartbeat_watch.sh` runs its existing heartbeat check first, unchanged, including its verdict line and state file, which `tests/scripts/test_heartbeat_watch.py` pins. The monitor check runs after it, in its own function. Nothing in the monitor check can change the heartbeat verdict line, its state or its exit path: a monitor-side failure is caught there and logged as its own verdict.

| verdict | condition |
|---|---|
| `monitor_stale` | `tick_at` older than **300 s**, at any hour. The loop runs every 60 s, 24/7 |
| `stops_unchecked` | the last tick's `market_open` is true, and either `positions` is `null` or non-empty, and the time since `max(priced_at or started_at, today's 09:30 ET)` exceeds the threshold (below) |
| `not_deployed` | the `monitor` key is absent. This logs a line and is silent: no post, no state change |
| `unreadable` | the query fails. It is suppressed (logged, not posted) when the heartbeat verdict in the same run is already `unreadable`, so one database outage posts once, not twice |
| `ok` | none of the above |

`monitor_stale` wins over `stops_unchecked`. Counting from the later of `priced_at` and today's open means the first ticks after 09:30 are never judged against the previous session's close.

**Threshold.** The `stops_unchecked` threshold starts at **600 s**. The plan's first measurement task reads a week of regular-session STOP_MONITOR counter rows on production, read-only. It measures how often a held ticker legitimately has no print in the window. If that base rate would make 600 s fire on a normal day, the threshold is set from the measurement and recorded in the plan before the alert code merges. Both thresholds are constants in the script, like `MIN_STALE_S`. There is no `.env` knob.

**Delivery** reuses `post`, `action_for` and the once-per-incident/once-on-recovery rule. The monitor verdict has its own state file, `logs/monitor_watch.state`, so the two incidents never mask each other. Messages:

- `[swingbot ops] Stop monitor STALE on <host>: last tick ended <age>s ago (threshold 300s). Open stops are not being checked.`
- `[swingbot ops] Stops UNCHECKED on <host>: <n> position(s) not checked for <age>s during the regular session (<tickers>; fetch_failed=<bool>; check_errors=<list>).`

**Dry run.** `--dry-run` accepts either `--age` (the heartbeat check, as today) or the monitor flags, or both: `--monitor-age`, `--priced-age`, `--market-open`, `--positions`. Each verdict is testable without psql. A dry run with only monitor flags is valid and skips the heartbeat check.

**Owner.** The script header's owner and removal lines (`heartbeat_watch.sh:14-15`) are extended to cover the monitor check and `monitor_watch.state`: the partner (ops) owns them, and they are removed together with the script.

### 3. Rollback

`scripts/ops/rollback_to.sh` swaps the image and restores Postgres to a point in time, but the host checkout keeps the new script. Two cases:

- **The database is restored to before v184 deployed.** The key is absent, the verdict is `not_deployed`, and nothing posts.
- **Only the image is rolled back, or the restore point is after v184.** A stale `monitor` key remains and would read `monitor_stale` for good. The rollback section of `docs/deploy/DEPLOY_HETZNER.md` gains one step: remove the key (`UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'`) when the target image predates v184. `rollback_to.sh` prints that reminder after a rollback.

## What does not change

- No stop, target, fill or close logic. The monitor still acts on fresh quotes only, and an unpriced ticker is still skipped. This spec makes the skip visible and leaves it in place.
- No extra quote fetch and no quote-cache read (live/replay parity).
- The existing heartbeat verdict, its threshold, its line format and its state file.
- The Discord trade channels. Ops alerts go only to `OPS_ALERT_WEBHOOK_URL`.

## Tests

- **Bot** (stubbed quote batch and stores):
  - `positions` is the union of trade and plan tickers, and `null` when a read failed.
  - `unquoted` matches `ticker not in live_prices`, plus the plan tickers `poll()` did not price.
  - `fetch_failed` is set when `_run_bounded` returns `None`.
  - `check_errors` lists a ticker whose close call raised.
  - `priced_at` advances only on a clean tick, and on a known-empty book. It never advances on a raised tick, and it is `null` after a restart.
  - `market_open` is false on an NYSE holiday and after 13:00 ET on a half-day.
  - A stamp write that raises is swallowed, and the closes and `run_manager_tick` run unchanged.
  - The stamp adds no `monitor_quotes` call and no quote-cache read.
- **Script** (`tests/scripts/test_heartbeat_watch.py`, dry-run only):
  - every verdict row above, including `not_deployed` staying silent;
  - `monitor_stale` beats `stops_unchecked`;
  - `stops_unchecked` counts from today's open, not yesterday's `priced_at`;
  - the `unreadable` double post is suppressed;
  - the existing heartbeat verdict line is byte-identical with and without the monitor check;
  - a monitor-only dry run is valid;
  - each incident posts once and recovers once, through its own state file.

## Rollout

The bot change ships with the image. `deploy/deploy.sh` resets the checkout to `origin/main`, so the cron (`install_heartbeat_watch_cron.sh`), whose line is unchanged, picks up the new script. Verification on production:

1. Run `heartbeat_watch.sh --dry-run` for each verdict.
2. Confirm one real run logs a monitor `verdict=ok` with a `tick_at` under 120 s old.
3. Send one `--test` post.

No live fault is injected on production.

## Out of scope (follow-ups, not this spec)

- A wall-clock bound around the whole `trade_monitor` tick, or a watchdog that restarts a wedged loop. With this spec the hang becomes visible. Self-healing is a separate design with its own risk of double closes.
- Alerting from outside the VM. The watch dies with the VM (`heartbeat_watch.sh` header).
- Extended-hours stop checks. `stops_unchecked` judges the regular session only, while the monitor also acts on extended-hours prints.
- Fill quality on stop-outs while the monitor is healthy (60-second polling of extended-hours prints).

## Panel review

Run 2026-10-21 over `ff6f4c5f`: staff-engineer (opus), then quant-engineer (sonnet).

- staff-engineer [BLOCKING]: a rollback leaves a stale or absent `monitor` key and the watch never recovers -- **applied**: § 3 Rollback; an absent key is `not_deployed` and silent; DEPLOY_HETZNER gains the key-removal step and `rollback_to.sh` prints it.
- quant-engineer [BLOCKING]: carrying `priced_at` forward under a no-read merge is unspecified, and its value after a restart is undefined -- **applied**: in-process state, `started_at`, `null` after a restart, and the watch counts from `started_at`.
- quant-engineer [BLOCKING], with staff-engineer [ADVISORY]: a `finally` stamp after a raised tick could advance `priced_at` or raise on unset variables -- **applied**: variables default to unknown, `outcome` is recorded, a raised tick never advances `priced_at`, and an unknown book is `null`, not 0.
- quant-engineer [BLOCKING], with staff-engineer [ADVISORY]: open plans with no trade rows read as checked -- **applied**: `positions` is the union with `open_plans()` tickers, and the plan side comes from what `poll()` priced, with no extra fetch.
- quant-engineer [BLOCKING], with staff-engineer [ADVISORY]: `is_regular_session` ignores holidays and half-days -- **applied**: the holiday- and half-day-aware composition is named.
- quant-engineer [ADVISORY], with staff-engineer [ADVISORY]: quoted is not checked, and a fetch failure looks like no prints -- **applied**: `check_errors` and `fetch_failed`.
- quant-engineer [ADVISORY]: "unquoted" must use the close call's own filter, and the threshold needs a base rate -- **applied**: the definition is pinned, and a measurement task sets the threshold before merge.
- quant-engineer [ADVISORY]: the end-of-tick stamp conflates checked with complete, and the inline DB write blocks the loop -- **partly applied**: the write goes through `asyncio.to_thread`. The conflation is accepted because `priced_at` carries "checked".
- quant-engineer [ADVISORY]: tests should pin parity: no extra fetch or cache read, and closes unchanged when the stamp raises -- **applied** in § Tests.
- quant-engineer [ADVISORY]: the R figures were not re-derivable -- **applied**: the four-trade table, with fields, formula and export command.
- quant-engineer [ADVISORY]: the check at the 09:30 open would judge against the previous close -- **applied**: the age counts from the later of `priced_at` and today's open.
- staff-engineer [ADVISORY]: SSE reader cost -- **applied**: named under Reader cost, with a 120 s throttle if the handler does not debounce.
- staff-engineer [ADVISORY]: a DB outage posts two `UNREADABLE` messages -- **applied**: the monitor-side post is suppressed when the heartbeat is already `unreadable`.
- staff-engineer [ADVISORY]: check order, isolation and the dry-run flag guard -- **applied**: the heartbeat check runs first and unchanged, the monitor check runs in its own function, and a monitor-only dry run is valid.
- staff-engineer [ADVISORY]: the Bump line said two keys -- **applied**: one key.
- staff-engineer [ADVISORY]: the new state file has no owner or removal condition -- **applied**: the script header is extended.
