# v184 — post-deploy verification on production

**Plan:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](../plans/2026-10-21-v184-stop-monitor-liveness_0-index.md) · Task V184-12

**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md) § Rollout
**Run:** 2026-10-24, read-only checks on the Hetzner VM, final bot 2.15.2, checkout `c8fb1be8`

## 1. Deployed

- Checkout: `c8fb1be8 merge(v184): surface swallowed plan step failures in monitor liveness`; `git merge-base --is-ancestor c8fb1be8 HEAD` succeeded and printed `checkout-has-v184-fix`.
- Bot container `VERSION.json`: `ui=1.35.1`, `bot=2.15.2`, `bot_updated=2026-10-24 19-50-43` UTC.
- Cron: `*/5 * * * * /usr/bin/env bash /opt/swing-bot/scripts/ops/heartbeat_watch.sh >/dev/null 2>> /opt/swing-bot/logs/heartbeat_watch.log`.
- The deploy workflow for `c8fb1be8` completed successfully (GitHub Actions run 40127322940), including its backend suites and deploy job. The initial `b37c6e44` / bot 2.15.1 deployment also succeeded (run 40105037919); the quant-engineer panel then found a swallowed plan-step error path, fixed in `b933e2f3` before bot 2.15.2 was released.

## 2. Dry runs, one per verdict

The watcher ran on the final 2.15.2 VM checkout with `HEARTBEAT_WATCH_ROOT=/tmp/v184-dry-b37c6e44`. The disposable root was removed after the checks. The listing contained only `heartbeat_watch.log`, so no state file was written. Its script was unchanged between the two deployments.

```text
== --monitor-age 30
2026-10-24T19:57:07Z monitor verdict=ok tick_age_s=30 priced_age_s=0 market_open=false positions=0 previous=none action=none dry_run=1
rc=0
== --monitor-age 301
2026-10-24T19:57:07Z monitor verdict=monitor_stale tick_age_s=301 priced_age_s=0 market_open=false positions=0 previous=none action=alert dry_run=1
rc=0
== --monitor-age absent
2026-10-24T19:57:07Z monitor verdict=not_deployed tick_age_s=absent priced_age_s=none market_open=none positions=none previous=none action=none dry_run=1
rc=0
== --monitor-age
2026-10-24T19:57:07Z monitor verdict=unreadable tick_age_s=none priced_age_s=0 market_open=false positions=0 previous=none action=alert dry_run=1
rc=0
== --monitor-age 30 --market-open true --positions 3 --priced-age 100000
2026-10-24T19:57:07Z monitor verdict=stops_unchecked tick_age_s=30 priced_age_s=100000 market_open=true positions=3 previous=none action=alert dry_run=1
rc=0
== --monitor-age 30 --market-open true --positions null --priced-age 100000
2026-10-24T19:57:08Z monitor verdict=stops_unchecked tick_age_s=30 priced_age_s=100000 market_open=true positions=null previous=none action=alert dry_run=1
rc=0
== --monitor-age 30 --market-open false --positions 3 --priced-age 100000
2026-10-24T19:57:08Z monitor verdict=ok tick_age_s=30 priced_age_s=100000 market_open=false positions=3 previous=none action=none dry_run=1
rc=0
== --monitor-age 301 --market-open true --positions 3 --priced-age 100000
2026-10-24T19:57:08Z monitor verdict=monitor_stale tick_age_s=301 priced_age_s=100000 market_open=true positions=3 previous=none action=alert dry_run=1
rc=0
== --age 30
2026-10-24T19:57:08Z verdict=ok age_s=30 threshold_s=900 previous=none action=none dry_run=1
rc=0
== --age 30 --monitor-age 30
2026-10-24T19:57:08Z verdict=ok age_s=30 threshold_s=900 previous=none action=none dry_run=1
2026-10-24T19:57:08Z monitor verdict=ok tick_age_s=30 priced_age_s=0 market_open=false positions=0 previous=none action=none dry_run=1
rc=0
== bare --dry-run
rc=2
heartbeat_watch.log
```

## 3. The cron's own runs

The last six monitor verdicts were all `ok`. The final three ran after the 2.15.2 deploy and had tick ages 30, 32 and 90 seconds: all below 120 seconds and the 300-second stale threshold. The three post-deploy heartbeat lines retained the previous format and were all `verdict=ok`, with ages 224, 225 and 225 seconds below the 900-second threshold. Both state files contained `ok`.

```text
2026-10-24T19:45:02Z monitor verdict=ok tick_age_s=52 priced_age_s=52 market_open=false positions=8 previous=ok action=none
2026-10-24T19:50:02Z monitor verdict=ok tick_age_s=51 priced_age_s=51 market_open=false positions=8 previous=ok action=none
2026-10-24T19:55:02Z monitor verdict=ok tick_age_s=52 priced_age_s=52 market_open=false positions=8 previous=ok action=none
2026-10-24T20:00:01Z monitor verdict=ok tick_age_s=30 priced_age_s=30 market_open=false positions=8 previous=ok action=none
2026-10-24T20:05:02Z monitor verdict=ok tick_age_s=32 priced_age_s=32 market_open=false positions=8 previous=ok action=none
2026-10-24T20:10:02Z monitor verdict=ok tick_age_s=90 priced_age_s=90 market_open=false positions=8 previous=ok action=none
2026-10-24T20:00:01Z verdict=ok age_s=224 threshold_s=900 previous=ok action=none
2026-10-24T20:05:02Z verdict=ok age_s=225 threshold_s=900 previous=ok action=none
2026-10-24T20:10:01Z verdict=ok age_s=225 threshold_s=900 previous=ok action=none
monitor_watch.state=ok
heartbeat_watch.state=ok
```

## 4. The monitor key

At 2026-10-24 19:58:33 UTC, the final 2.15.2 read showed `outcome=ok`, `started_at=2026-10-24T19:56:07+00:00`, `tick_at=2026-10-24T19:56:35+00:00`, and `priced_at=2026-10-24T19:56:35+00:00`. All required fields were present: `positions` listed ADBE, AMAT, ARM, GOOGL, INTC, JNJ, PANW and SPCX; `unquoted=[]`; `unquoted_count=0`; `fetch_failed=false`; `check_errors=[]`; `market_open=false`. The scan heartbeat's separate `timestamp` was `2026-10-24T19:56:17.351740+00:00`.

On 2.15.2, the scan heartbeat's separate `timestamp` advanced from `2026-10-24T19:56:17.351740+00:00` to `2026-10-24T20:01:16.883326+00:00` on a second read at 20:03:48 UTC; the monitor `tick_at` and `priced_at` then both read `2026-10-24T20:01:31+00:00`. The read was outside the NYSE regular session. The next in-session check is due on Monday 2026-10-26 after 13:30 UTC, before close-out; record its `market_open`, positions, unquoted names and count, and `priced_at` age here.

## 5. Test post

The partner approved one outward-facing ops Discord test post. The production command returned `2026-10-24T19:42:05Z test delivered=yes` and `rc=0`.

## 6. Pre-close-out panel

Staff-engineer: CLEAN. Quant-engineer: CLEAN on the final diff `b37c6e44^1...c8fb1be8` and both results documents. The earlier quant-engineer advisory about swallowed plan-step failures was applied in `b933e2f3` and verified by the focused task review. Both panel roles kept the Monday in-session production read as an open close-out gate.

## 7. Next-session read

Read the production `monitor` key on Monday 2026-10-26 at 13:45 UTC and record `market_open`, positions, unquoted names and count, `check_errors`, `outcome`, and `priced_at` age against `STOPS_UNCHECKED_S=600`. The VM clock reports UTC and the bot's NYSE session helper returns true for that time. The read must be through `scripts/ops/ssh-hetzner.sh`; no in-session result has been observed yet. A one-shot VM cron capture was proposed under the repository's far-off scheduling rule and awaits the partner's design approval. If declined, perform the read manually in the next session. Close-out follows only after the result is recorded.

## Verdict

The final 2.15.2 deployment, all dry-run verdicts, three post-deploy cron runs, the final monitor-key read, and the advancing scan heartbeat pass. The single approved test post delivered on 2.15.1; the watcher script did not change for 2.15.2. The Monday in-session monitor read remains open before close-out. The quant-engineer panel's plan-step finding was applied in `b933e2f3` and merged in `c8fb1be8`.
