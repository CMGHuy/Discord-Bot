# v184 — stops_unchecked threshold measurement

**Plan:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](../plans/2026-10-21-v184-stop-monitor-liveness_0-index.md) · Task V184-1
**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md) § 2 Threshold
**Run:** 2026-10-24, read-only on production (Hetzner VM)

## Question

During the NYSE regular session, how often does the stop monitor go through a
stretch of consecutive 60 s ticks without pricing its book, for ordinary reasons?
A 600 s `stops_unchecked` threshold fires after ten such ticks in a row.

## Decision rule (written before the data was read)

Sources:
- (A) hourly `market_fetch_counts` rows with `asker = 'stop_monitor'` and
  `kind = 'quote'`, NYSE sessions only, ET hour buckets 09:00-15:59, over the last
  8 calendar days.
- (B) the bot's log lines for a failed or timed-out monitor quote batch, over the
  same 8 days (or the retained part of them), regular session only.

Definitions:
- `U` is the largest per-hour `failed / (all outcomes)` share in (A).
- A *run* is a sequence of monitor-batch failure lines in (B) that are at most
  90 s apart. Its length is `last - first + 60` seconds. A run of 1800 s or more
  is an *incident*, which is exactly what the alert is for: incidents are listed,
  not counted in `L`.
- `L` is the longest non-incident run, in seconds.

Verdict:
1. If `L < 300` and `U < 0.5`, keep `STOPS_UNCHECKED_S = 600`.
2. Otherwise let `T` be the smallest multiple of 300 that is `>= 2 * L`, raised to
   at least 900 when `U >= 0.5`. If `T <= 1800`, set `STOPS_UNCHECKED_S = T`.
3. If `T > 1800`, do not pick a value. Report to the controller, who asks the partner.
4. If either source covers fewer than 3 regular sessions, keep 600, mark the
   measurement *insufficient*, and name V184-12 (post-deploy) as the recheck. Once
   the `unquoted` field ships, it gives the per-tick answer directly.

Limits: (A) is hourly and does not say which ticker went unpriced, and a ticker
with no fresh print may not count as `failed`. (B) sees only whole-batch
failures. Neither source sees a single illiquid ticker that keeps the book
unclean on its own. The post-deploy check in V184-12 is where that becomes
visible.

## Data

Measured on 2026-10-24 at approximately 08:23 UTC. The query window was the
preceding 8 calendar days, approximately 2026-10-16 08:23 UTC through
2026-10-24 08:23 UTC. Production was read only throughout; every remote command
used the existing approved `scripts/ops/ssh-hetzner.sh` wrapper from the main
checkout, because the uncommitted helper was absent from this isolated worktree.

**Source A:** 21 hourly rows across **3 regular sessions**, 2026-10-21,
2026-10-22 and 2026-10-23. No returned date was an NYSE holiday.
The combined outcome count was **0 failed / 19,065 total**, with no
budget-deferred outcomes. SQL NULL failed/deferred aggregates mean no matching
outcomes and were treated as zero. **U = 0.0000**, tied across all 21 hours;
the first maximum was 2026-10-21 09:00 ET. Each session had all seven
09:00–15:00 ET buckets. The 09:00 bucket includes the pre-open half hour.
Although the query requested eight days, this source supplied only three
sessions; it satisfies the frozen minimum and does not establish a full week
of counter history.

**Source B:** inspected the retained bind-mounted
`/opt/swing-bot/logs/bot.log*`, including rotations `.1`, `.2` and `.3`,
instead of container logs, following the canonical production investigation
guidance. The oldest retained timestamp was **2026-10-09 06:21:10,115**;
the newest observed timestamp was **2026-10-24 08:07:42,274**. The retained
window spans the entire requested eight days. Log entries during regular
trading hours were explicitly verified for **6 sessions** in that window:
2026-10-16, 2026-10-19, 2026-10-20, 2026-10-21, 2026-10-22 and 2026-10-23.
There were **zero matching batch-failure lines** in any retained rotation,
so both current and historical matching failure counts were zero.
Zero dates with failures is distinct from six dates with retained session logs.

The scratch run calculator reported `runs=0 incidents=0 rth_dates_with_failures=0`
and `L=0`. There are no incident dates or lengths to list.

The read-only heartbeat query at **2026-10-24 08:23:05.091768 UTC** returned
`swallowed = {"since": "2026-10-23T16:37:21.997818+00:00", "counts": {}}`.
Neither `scan.run_bounded` nor `scan.loops.monitor_prices` was present in the
counts map (zero recorded for this process lifetime). This counter window is
shorter than the retained log window and is corroborating evidence only.

Verification: the supplied run calculator returned the output above;
independent CSV aggregation confirmed the 21 rows, three dates, zero failed
outcomes and 19,065 total outcomes. Radon printed nothing for the scratch
calculator. No production writes, tests against the database, or application
code changes were involved.

## Verdict

**Case 1 applies:** `L=0 < 300` and `U=0.0000 < 0.5`, with source A covering
3 sessions and source B covering 6 sessions (both meet the minimum of 3).
Keep **`STOPS_UNCHECKED_S=600`**. No incident runs were observed.
V184-12 must recheck actual per-tick `unquoted` and check-error evidence after
deployment, including isolated illiquid tickers that these aggregate sources miss.
