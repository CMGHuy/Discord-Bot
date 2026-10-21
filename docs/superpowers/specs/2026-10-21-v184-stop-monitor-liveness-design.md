# v184 — Stop-monitor liveness: alert when open stops stop being checked

**Version:** ui 1.33.1 · bot 2.14.2 (at writing)
**Bump:** bot patch — two new heartbeat keys, written by the trade monitor, and two new incident kinds in the out-of-process watch. No alert, plan, stop or fill behaviour changes. The partner gains an ops post when stops go unchecked.
**Edge:** none (integrity) — protects the R the book already books. In August a stalled monitor turned stops of about −1R into fills of up to −6R. The prediction is that this measures nothing in ExpR terms. Its value is the number of hours with stops unchecked and nobody told, which today goes uncounted.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer
**Status:** spec written 2026-10-21 after the partner chose, from the 2026-10-21 scout slate, to verify the stop-enforcement lead, then to spec the fix. Evidence and the correction about the bounded fetch: `docs/superpowers/results/2026-10-21-scout-slate.md` § Stop-enforcement check.

## Why

The production DB shows two stalls (read-only check, 2026-10-21):

- No trade or plan closed between `2026-08-03 16:18:02` UTC and `2026-08-04 18:55:15`. Then 25 trades and 33 plan status entries closed within 28 seconds, each at that moment's quote. NBIS closed at −6.0R against a −1R stop, and DELL, GLW and MRNA at about −3.3 to −3.5R each.
- On 2026-08-05 nothing closed for about 3.5 h, then 7 trades closed between 15:34:01 and 15:34:08.
- The VM had been up since 2026-07-31. This was not a reboot, and the August logs are gone.

The likely hang causes were fixed afterwards. On 2026-08-24 the monitor skipped its tick while a scan ran. On 2026-09-17 a yfinance call was unbounded. Today's quote fetch is process-bounded (`plan_manager.monitor_quotes` → `fetch._run_bounded`).

What was never fixed is **visibility**. Nothing anywhere notices when the stops stop being evaluated:

1. `runstate._write_heartbeat` is the only liveness stamp. It is written by `session_scan` at the **start** of its tick (`swingbot/commands/scanning/loops.py:195`), never by `trade_monitor` (`loops.py:628`).
2. `scripts/ops/heartbeat_watch.sh` reads only that stamp. A wedged or dead `trade_monitor` leaves it fresh, and so does a monitor that ticks without pricing anything.
3. A failed or empty quote batch returns `{}`. The tick then checks no stop, logs a warning and carries on. If that repeats every minute for a day, the result is August again.
4. `@trade_monitor.error` restarts the loop only when an exception escapes. A hang never reaches it, and the rest of the tick (`run_manager_tick`, the Discord posts) has no wall-clock bound.

## What changes

### 1. The monitor stamps its own liveness (bot)

At the **end** of every `trade_monitor` tick, whether it closed anything or not, the monitor merges one key, `monitor`, into the heartbeat row through the existing `runstate._update_heartbeat`. That merge is `doc || fields`, and only the monitor writes this key, so no other writer is disturbed. The key holds:

| field | meaning |
|---|---|
| `tick_at` | UTC ISO time the tick finished |
| `open` | number of distinct open-trade tickers the tick tried to price |
| `unquoted` | sorted list of those tickers that got no fresh quote this tick (cap 20 names, plus `unquoted_count`) |
| `priced_at` | UTC ISO time of the last tick where `unquoted` was empty, i.e. every open stop was checked. A tick with `open == 0` counts as priced. |
| `market_open` | whether the NYSE regular session was open at `tick_at`, from the repo's existing exchange-hours helper (the plan names it). This is never `in_session()`, which is the configurable Berlin scan window. |

Stamping at the end, not the start, is the point. A tick that wedges anywhere (quote fetch, `run_manager_tick`, Discord) leaves `tick_at` ageing. A stamp written at the start is the blind spot that point 1 above describes. The stamp write is wrapped like `_update_heartbeat` already is, so a failed write is counted (`swallowed`) and never raises into the tick.

Plans that are open with no open trade row (the `!trades clear` case in the monitor's docstring) are outside `open` here. The plan manager prices them through the same shared quote cache. Folding them in is a follow-up only if the panel judges the gap material.

### 2. The watch gains two incident kinds (ops script)

`heartbeat_watch.sh` keeps its current check and verdict line unchanged. It adds one more query per run, reading `doc->'monitor'`, and derives a second verdict:

| verdict | condition | why |
|---|---|---|
| `monitor_stale` | `tick_at` older than **300 s**, at any hour | the loop is every 60 s and runs 24/7, so five missed ticks means it is dead or wedged |
| `stops_unchecked` | `market_open` is true, `open > 0`, and `priced_at` older than **600 s** | the monitor is ticking but has priced no full book for 10 minutes during the regular session |
| `ok` | neither of the above | |
| `unreadable` | the key is absent, or the query fails | the same treatment as today's heartbeat `unreadable` |

`monitor_stale` wins over `stops_unchecked`. A key that is absent right after deploy, before the first monitor tick, counts as `unreadable` and goes through the same once-per-incident state machine, so a deploy posts once and recovers once. The two thresholds are constants in the script, like `MIN_STALE_S`. There is no new `.env` knob.

Delivery reuses `post`, `action_for` and the once-per-incident/once-on-recovery rule. The monitor verdict keeps its own state file (`logs/monitor_watch.state`), so a monitor incident and a heartbeat incident never mask each other. Messages name the failing case and the unquoted tickers, as today's messages do:

- `[swingbot ops] Stop monitor STALE on <host>: last tick finished <age>s ago (threshold 300s). Open stops are not being checked.`
- `[swingbot ops] Stops UNCHECKED on <host>: <n> open ticker(s) unpriced for <age>s during the regular session (<tickers>).`

`--dry-run` gains `--monitor-age`, `--priced-age`, `--market-open` and `--open` so every verdict is testable without psql, like `--age` today.

## What does not change

- No stop, target, fill or close logic. The monitor still acts on fresh quotes only, and an unpriced ticker is still skipped. This spec makes the skip visible and leaves it in place.
- The existing heartbeat verdict, its threshold and its state file.
- The Discord trade channels. Ops alerts go only to `OPS_ALERT_WEBHOOK_URL`.

## Tests

- **Bot:**
  - A monitor tick with a stubbed quote batch writes `monitor` with the right `open`, `unquoted` and `market_open`.
  - `priced_at` advances only when `unquoted` is empty, and on an empty book.
  - A failed stamp write is swallowed, and the tick still posts its closes.
  - The stamp is written after the closes and the plan-manager tick, so a raise in either still ends in a stamp (the stamp sits in a `finally`).
- **Script** (`tests/scripts/test_heartbeat_watch.py`, dry-run only):
  - every verdict row of the table above;
  - `monitor_stale` beats `stops_unchecked`;
  - an absent key gives `unreadable`;
  - the state machine posts once per incident and once on recovery, with a separate state file from the heartbeat.

## Rollout

The bot change ships with the image. The script change reaches the VM with the repo checkout the cron already runs from (`install_heartbeat_watch_cron.sh`), and the cron line is unchanged. Verification on production:

1. Run `heartbeat_watch.sh --dry-run` for each verdict.
2. Confirm one real run logs `monitor verdict=ok` with a `tick_at` under 60 s old.
3. Send one `--test` post.

No live fault is injected on production.

## Out of scope (follow-ups, not this spec)

- A wall-clock bound around the whole `trade_monitor` tick, or a watchdog that restarts a wedged loop. With this spec the hang becomes visible. Self-healing is a separate design with its own risk of double closes.
- Alerting from outside the VM. The watch dies with the VM (`heartbeat_watch.sh` header).
- Fill quality on stop-outs while the monitor is healthy (60-second polling of extended-hours prints). That is an exit/fill question for the book, not liveness.
