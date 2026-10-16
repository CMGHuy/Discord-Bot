# v171 — Shared market-data fetch: one call, every consumer, fresh plans

**Version:** ui 1.26.0 · bot 2.6.0 (at writing)
**Bump:** bot minor — every posted plan is rebuilt from a last-second quote, so alert prices change for every reader; ui patch — the admin tape shows labelled ETF proxies when Yahoo is blank and prices carry their age, otherwise the same screens.
**Edge:** none (integrity) — fewer redundant Alpaca/yfinance calls and fresher plan prices. It changes no signal, gate threshold, stop rule, size or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, veteran-trader
**Status:** spec written 2026-10-16 from a brainstorm with the partner (scope, approach, freshness clause, rebuild rule, priority order, index tape and success criteria approved in chat).

## Why

The partner has seen three live symptoms: missed or late alerts, a blank
index tape in the admin, and Discord 429s. The last has its own cause
(Discord message-delete limits) and is out of scope here. Growth is coming
on every axis at once: a bigger watchlist, faster refresh, and new consumers
(eToro demo trade management, an execution mirror, more admin pages).

Recon on 2026-10-16 (prod logs 10-08..10-16, scan telemetry 10-02..10-16,
and a code read of every call site) found:

- **No provider rate limits are hit today.** Zero Alpaca 429s. The one
  Alpaca incident was a timeout (2026-10-15 13:19 UTC): 13 symbols fell
  back to yfinance and the breaker opened for 5 minutes. Scan
  `yfinance-fallback` was 0 every day except 37 on 10-07.
- **The admin's yfinance index downloads fail in bursts**: about 1,255
  `YFPricesMissingError('possibly delisted')` lines on `^GSPC ^NDX ^DJI
  ^VIX SI=F`, clustered with admin dashboard polling. This is likely Yahoo
  soft-throttling by IP, though no 429 proves it.
- **Most traffic is redundant.** The same data is fetched several times by
  different consumers:
  1. `trade_monitor` (`swingbot/commands/scanning/loops.py:590`, every 60 s,
     around the clock) and the plan manager in the same tick
     (`plan_manager.py:1363`) each run their **own** fresh-only price batch
     for the same book. The plan manager then pulls **uncached 2y daily
     bars per open plan** (`_bars_since`, `_daily_frame`, `_live_atr`).
     That is about 120 snapshots plus about 60×P bar requests an hour.
  2. **About half of in-session scans are fully cold.** The scan treats the
     daily CSV as stale after `SCAN_CACHE_MAX_AGE_HOURS`=6 h, the refresh
     loop rewrites it only every 12 h, and cold frames are never written
     back. A cold scan costs about 31 Alpaca requests at 10y depth
     (3 symbols per request).
  3. **The admin container fetches on its own** (charts uncached, risk page
     uncached, watchlist warm-ups not de-duplicated, earnings warm-up pool).
     It shares nothing with the bot except the disk CSVs and
     `ticker_meta_cache.json`.
  4. **Per-symbol uncached yfinance calls**: `Ticker.calendar` per posted
     alert (`events.py:62`), `earnings_snapshot` (`events.py:266`), and
     `data_refresh.refresh_symbol` running one symbol × 6 timeframes at a
     time.
  5. **Every guard is per process.** The router's 150/min bucket and its
     breaker live inside spawned workers that exit after one call. Bot,
     workers and admin each have their own, and nothing counts traffic
     against the one Alpaca account or the one egress IP that bot and admin
     share (one VM, same Docker network, no proxy).
- **Plan prices lag.** Live prices are fetched early in the scan; analysis
  then runs 70-100 s and a scan takes 110-150 s in session. A posted plan's
  price can already be 1.5-2.5 minutes old.

Estimated today: about 1,100-1,200 provider calls an hour in session
(scan about 190, 60 s loops about 720 at 10 open plans, admin about 240,
refresh about 37). Target after this spec: about 150-350. These are
estimates from the code read, not measurements. Measuring them is
deliverable D9.

## Goals

1. **One fetch, many consumers (the partner's central requirement).** When
   any part of the bot, its worker processes or the admin container asks
   for the same data (same symbol, same kind, still within that kind's
   freshness window), exactly one network call is made and every asker
   gets its result. This holds across processes and across the two
   containers. No service gets worse data or later data because of the
   sharing.
2. **Plans reflect current price action.** Every plan is rebuilt from a
   last-second quote right before it posts (D5).
3. **Fewer calls.** Cut redundant demand at the sources listed in Why.
4. **Headroom.** One account- and IP-wide budget with a priority order, so
   growth or a burst degrades the least important consumer first.
5. **A tape that never goes blank.**

## Non-goals

- Discord rate limits (429s on message deletes): a separate small fix.
- Any paid data feed or Alpaca tier upgrade (CLAUDE.md § Paid usage).
- Any `account: real` path, or anything that places an order.
- Changing any signal, gate threshold, stop rule, sizing or badge.
- Replacing yfinance where Alpaca cannot serve the symbol.

## Anti-goals (a failure even if call counts drop)

- **Any plan, alert or exit decision built on a price older than its own
  run's fetch.** Sharing a result is allowed only if that result was fetched
  within the asker's freshness window (D2). A cached result is never
  "close enough".
- **A delta-fetched frame that differs from a full fresh download.**
  Wrong-adjusted history means wrong levels, stops and alerts.
- **Silent depth loss.** The existing splice path refuses on an
  adjustment-basis mismatch and then quietly drops history
  (`history_splice.py`, `adjustments.py`). A refusal must trigger a full
  refetch, never a shallower frame.
- **The budget blocking money paths.** If the shared budget's store
  (Postgres) is unavailable, calls go through (fail open), logged.
- **Lookahead.** Nothing here may place a bar after the frame's last live
  bar (`no-lookahead` skill; `history_splice.py`'s NO-LOOKAHEAD rule).

## Decisions

### D1 — One shared fetch layer every consumer goes through

Every Alpaca and yfinance request in `swingbot/` (bot, worker processes,
admin) goes through one shared layer keyed by **(data kind, symbol,
parameters)**. The kinds are live quote, daily bars, intraday bars, index
quote, earnings and metadata. The layer:

- **Serves from the shared cache** when an entry for that key is within the
  asker's freshness window (D2).
- **Single-flights across processes.** If another process is already
  fetching that key, the asker waits for that fetch (bounded by its own
  deadline) instead of fetching too. Today's `tape_cache.SingleFlightCache`
  does this inside one process only.
- **Batches.** Concurrent askers for different symbols of the same kind are
  merged into one batched provider call where the provider batches (Alpaca
  snapshot, Alpaca bars, yfinance download).
- **Is the only door.** A test (D8) fails any new direct import or call of
  alpaca-py clients or `yfinance` outside the layer, its providers and
  `scripts/`.

*Storage, my call (partner may override):* the bot and admin already share
Postgres and the disk CSV cache. Short-lived entries (quotes, index quotes,
earnings, metadata) and the cross-process single-flight lock and budget live
in Postgres. Bars stay in the existing on-disk daily cache, with write-back
(D3) and a Postgres lock per key. A new table follows
`docs/claude/schema-evolution.md` as an Alembic revision (`schema-change`
skill). The builder picks the exact table shape and lock mechanism (advisory
locks are one option). It must stay cheap: one round trip per cache hit.

Failure behaviour (panel, staff-engineer):

- **Every Postgres touch fails open**, not only the budget: the cache read,
  the single-flight lock and the budget. Each has a short per-call timeout
  (well under the asker's deadline). On error or timeout the asker fetches
  directly and logs it. A hung database never stalls stop monitoring or the
  re-quote.
- **A dead lock holder never strands waiters.** The lock is released when
  its holder's connection dies (session-scoped) or expires on a lease. The
  builder picks which.
- **When a waiter's deadline passes:** priority 1-2 askers (D6) fetch for
  themselves. Correct, fresh data beats "exactly one call". Priority 3-5
  askers get the last cached value with its age, or fail as they do today.
- **Connections:** each spawned worker uses at most one Postgres
  connection, opened lazily. The plan states the per-scan connection count
  and checks it against the 1 vCPU cap.
- **CSV writes** (D3 write-back, D4 refetch, the refresh loop) go through
  one writer that holds the key's lock and writes to a unique temp name
  before the atomic rename. Today's fixed `path + ".tmp"`
  (`data_store.py:419-421`) is replaced, so a lock that failed open cannot
  make two writers share one temp file.

### D2 — Freshness windows per data kind (the clause the partner added)

Each asker states how fresh it needs the data; a cached result older than
that is refetched, never served. Defaults:

| Kind | Asker | Max age |
|---|---|---|
| Live quote | pre-post re-quote (D5) | **≤ 5 s** |
| Live quote | trade monitor / plan manager (stops, fills) | ≤ 15 s |
| Live quote | scan live-prices phase | ≤ 15 s |
| Live quote | admin **Dashboard** | ≤ 15 s: the page that always shows the latest price (partner) |
| Live quote | every other admin page (Watchlist, Trades, Risk, Charts…) | **≤ 60 s** (partner), shown with its age: served from whatever any page or service already fetched, so moving Dashboard → Watchlist makes no new call |
| Today's daily bar (forming) | scan, plan manager | refetched once per scan / per 60 s tick |
| Closed daily bars | everyone | cached until a new session close, or until D4 sees an adjustment change |
| Index quote (tape) | admin | ≤ 60 s |
| Earnings dates | alert path, admin | ≤ 6 h |
| Ticker metadata | everyone | persistent (as today) |

Every plan, alert and exit record stores the **timestamp of the quote** it
was built from, plus the quote's kind (trade, bid/ask mid or scan price)
and its last-trade or quote age. These are stored-record shape changes and
follow `docs/claude/schema-evolution.md` (added fields, an Alembic revision
where a table changes, no read-time upcasting). Rows written before v171
carry no value, and readers show "n/a".

### D3 — Daily bars: cache closed history, refresh only today

- Frames fetched cold by the scan are **written back** to the daily cache,
  so the next scan is warm.
- The 6 h / 12 h mismatch goes away. Closed bars stay valid until a new
  session close. Each scan fetches only the **recent window** (today's
  forming bar plus a short overlap) for the watchlist in one batched call,
  and splices it onto cached history.
- Scope (my call): only the scan's daily cache (`market_data/daily`). The
  v162 training store (`data/market_data`, `history_store.py`) and
  `backtest_cache` are untouched; backtests are out of scope.
- The plan manager reads its daily frames through the layer, so closed bars
  come from cache and today's bar from the shared fetch. It stops making
  per-plan 2y downloads every 60 s.

### D4 — The delta splice is proven or replaced by a full refetch

Revised after the panel (quant-engineer). Today's 1 % tolerance
(`adjustments.py:8`, duplicated at `data_refresh.py:152`) cannot see an
ordinary dividend re-adjustment: a quarterly dividend scales older history
by about 0.25-0.5 %. And an overlap-only check cannot see a re-adjustment
whose ex-date is older than the overlap window. So:

- **Event trigger (primary).** Per symbol, the cache stores the date of its
  last full fetch and an adjustment-basis fingerprint (for example a fixed
  old anchor bar's adjusted close). Each delta fetch compares the
  fingerprint against fresh data for that anchor bar, or against the
  provider's split/dividend actions. Any split or ex-dividend date after the
  last full fetch, or a fingerprint change of any size, forces a **full
  refetch** for that symbol, written back.
- **Overlap check (secondary).** At least 3 overlap bars must match the
  cache within a tight, spec-owned tolerance of about 1e-4 relative per
  close. That is rounding noise, since real end-of-day closes agree exactly.
  Fewer than 3 overlap bars, or any mismatch, means full refetch. It never
  means "no mismatch".
- **One constant.** The tolerance lives in one place and the existing
  copies import it. They do not become three coupled copies. Changing the
  existing 1 % callers' behaviour is out of scope; they only import.
- **A refusal never goes shallow.** A mismatch always ends in a full
  refetch. It never falls back to `history_splice.py`'s live-only path
  (lines 55-65), which drops depth. The frame never comes out shallower
  than before.
- **The cache's adjustment basis is stated in the plan** (the same basis
  the scan reads today), and the fingerprint is stored beside it.
- **Weekly full re-anchor** per symbol, outside session, as a backstop
  only. It runs as a bot loop task on the VM.
- **Parity test** (`testrun.py file`): fixtures with (a) a sub-1 % dividend
  whose ex-date is older than the overlap window, the case today's check
  misses; (b) a dividend inside the window; (c) a split; (d) an overlap of
  fewer than 3 bars. Each asserts cache plus delta equals a full fresh
  download bar for bar, including Volume (`adjustments.py:66` rescales it).

### D5 — Always rebuild before posting (partner's choice)

Right before alerts post, the scan makes **one** batched quote fetch
(≤ 5 s, D2) for just the symbols about to alert. Every such plan is then
**always rebuilt** from that quote, whatever the move: entry, stop,
targets, size, R and the dollar figures are recomputed, and the plan's gates
re-run. A plan that no longer qualifies is not posted, and that is logged
with the reason. The posted plan carries the quote's timestamp. The rebuild
reuses the scan's existing plan builder and gates; it never forks a second
copy of that logic.

Settled after the builder check:

- **Where (my call):** inside the scan, after analysis and **before**
  `_persist_plan_v2` / `trade_log.log_trade` / chart rendering
  (`scan_run.py` ~980-992). So there is one record per plan and no
  rewrite-after-post. The scan's frames and level maps are still in memory
  there.
- **Which paths (my call):** every path that posts a plan from a live
  price: the main scan, the SHORT lane (`short_run.py`) and strategy alerts
  (`strategy_pass.py`, shadow soak included, so shadow and live stay
  comparable). **Not** the next-session outlook (`outlook_run.py`): it is
  built from the last closed bar by design. Pre- and after-market scans
  rebuild too, from the freshest quote available.
- **Which gates re-run (my call):** only the price-dependent ones (R:R,
  entry distance, 2 % dollar-risk sizing, any gate reading `current_price`).
  Stateful gates (dedup, cooldown, heat, lane overlap, caps) are not
  re-run. A plan dropped by the rebuild does not consume cooldown or dedup.
- **What the quote replaces (my call):** the quote replaces `current_price`
  exactly as the live-prices phase does today (`analyze.py:876`). It is
  **not** spliced into today's forming bar, so levels and indicators come
  from the same bars as before (the "no signal change" non-goal; no
  lookahead question).
- **Stale feeds (partner's choice, revised after the veteran-trader
  panel):** the rebuild price is chosen in this order: (1) a last trade
  under 60 s old; (2) the live **bid/ask midpoint**, if that quote is under
  60 s old (a quote updates even when nothing trades); (3) otherwise the
  scan's own price is kept, the alert is flagged **"price not confirmed
  live"**, and the plan is never rebuilt from an older print. A delayed
  yfinance value counts only if its own timestamp passes the 60 s rule.
  Thin names still post. The record stores which kind was used and its age
  (D2).
- **The 5 s clock** starts when that symbol's quote fetch completes and ends
  when the plan is persisted. A plan that misses 5 s is re-quoted once. If
  it misses again it posts with its true age recorded, and that counts as
  a miss in the success table.
- **The re-run list includes the stop checks:** the stop floor and the 2 %
  dollar-cap band (`known-traps.md` § Stop floor and 2 % cap), the
  horizon-noise stop check, and gap/expiry validity. Together with R:R,
  entry distance and sizing, these are the price-dependent gates. ATR and
  stop distance come from the same frame the scan analysed; the rebuild
  changes only the price input.
- **One entry point (panel, staff-engineer):** the rebuild is one function
  in `swingbot/core/planning/`, called by all three lanes. It never becomes
  three call-site copies.
- **What the user sees matches (panel, veteran-trader):** the embed, the
  chart and the persisted record are all rendered from the rebuilt plan.
  None of them uses the pre-rebuild levels.
- **Posted plans are never altered by a rebuild.** The rebuild runs only
  before a plan's first post. Follow-up messages after posting are out of
  scope.
- **Pre- and after-market:** same price order, and the alert shows the
  session label (pre-market / after-hours) beside the price kind.

### D6 — One budget, money first (partner's choice)

One budget per provider (Alpaca account; yfinance per egress IP) is shared
by every process. The default Alpaca ceiling stays at today's 150/min. The
yfinance pacing default is the builder's call, stated in the plan. When the
budget is short, askers are served in this order:

1. open-trade / stop monitoring (real money in an open position);
2. pre-post re-quote (D5), since an unposted alert can wait one more scan;
3. the live scan;
4. background: hourly refresh, earnings, history update;
5. admin pages, which are served the cached value with its age instead of
   waiting. The Dashboard keeps its 15 s window only while budget allows.

The circuit breaker state is shared the same way, so a breaker opened by one
process holds for all. If the budget store is unavailable, calls go through
and the event is logged (fail open).

### D7 — Index tape: shared real indices, ETF proxies when blank (partner's choice)

The bot fetches `^GSPC ^NDX ^DJI ^VIX` and `SI=F` once a minute in session
into the shared cache, through the layer. Admin tabs read only that copy
and never call Yahoo for the tape themselves. When Yahoo comes back blank
for a symbol, the tape shows the Alpaca proxy instead (SPY, QQQ, DIA, a VIX
ETF the builder names, and SLV for `SI=F`, my call), **clearly labelled as
a proxy**. A proxy shows only its **change %**, never a level, so an ETF
price is never read as an index level (panel, veteran-trader). If the
bot's shared entry is older than 3 minutes (bot down or restarting), the
admin fetches the tape itself through the layer at priority 5 and keeps
showing the last good value with its age meanwhile (panel, staff-engineer).
The tape's full symbol list is whatever `market.py` / 
`tape_cache.py` show today; every Yahoo-only entry gets a proxy or is named
in the plan as having none. A blank reply
never overwrites the last good value. The tape shows each value's age.

### D8 — Remaining demand cuts

- `trade_monitor` and the plan manager share one quote fetch per tick (D1
  makes this automatic; the plan should verify it lands as one call).
- `Ticker.calendar` and `earnings_snapshot` go through the layer with the
  6 h window.
- The admin chart, risk page, watchlist warm-up and earnings warm-up go
  through the layer, so concurrent tabs collapse onto one call.
- `data_refresh.refresh_all` batches symbols per timeframe where yfinance
  allows it, and uses Alpaca for the timeframes Alpaca serves.
- The guard test from D1.

### D9 — Measurement

Every call through the layer is counted by (provider, kind, asker, outcome:
`hit` / `shared-wait` / `fetched` / `budget-deferred` / `failed`) and
written to scan telemetry, or a sibling record, per hour. Before the switch
is enabled, **five in-session trading days** of counts are recorded as the
baseline week (my call, so the success table compares a week with a week).
The baseline is taken with the layer in pass-through/count-only mode.

## Success (partner-approved), judged after one week in production

| Check | Threshold |
|---|---|
| Posted plans whose quote age at post (fetch completed → plan persisted, D5) exceeds 5 s | 0 |
| Blank tape minutes in session | 0 |
| Alpaca or yfinance 429s | 0 |
| Scan errors + data skips per ticker | not above the D9 baseline week |
| Provider calls per hour in session (all processes) | at most half the D9 baseline |
| Cache+delta vs full download parity (D4) | bar-for-bar equal, every check |

The thresholds are fixed now and never retuned after the fact. A miss is
recorded as such.

## Constraints

- Bot runs on a 2 vCPU VM; the bot container is capped at 1 vCPU. The layer
  must not add measurable CPU per scan.
- Alpaca free tier: SIP bars end at now − 16 min (`alpaca_provider._bars`).
  The live snapshot uses IEX, whose last trade is rejected after 300 s in
  regular hours and then falls back to yfinance. The ≤ 5 s re-quote must
  name which feed answers when IEX is stale.
- Worker processes are spawned per scan phase (`_run_bounded`). The layer's
  shared state must live outside them.
- Every function written or changed stays below cyclomatic complexity 15.
- `.env` is the config source. New knobs (windows, budget, proxy symbols)
  are `swingbot/config.py` fields with today's behaviour as the fallback
  where sensible.
- Production rollout follows `mirror-prod`.

## Rollout and rollback (panel, staff-engineer)

- **One flag per part**, each in `swingbot/config.py`: the layer (off /
  count-only / on), D3+D4 write-back and delta fetch, the D5 rebuild, and
  the D7 tape move. Each flag-off restores today's code path.
- The layer ships in **count-only** mode and is switched on only after the
  **five-trading-day baseline** (D9).
- **CSV safety:** write-back writes the same file format the scan already
  reads, so files rewritten while a flag was on stay valid with it off.
  Flag-off never needs a cache wipe.
- **Migrations are additive** (a new table plus new nullable fields). On
  rollback they stay in place and are never downgraded. The code rollback
  is `scripts/ops/rollback_to.sh` per `docs/deploy/DEPLOY_HETZNER.md`.
- **Removal:** the count-only mode and the per-part flags are removed by a
  follow-up once the success week passes. The plan records that as
  "What follows". The weekly re-anchor task (D4) stays; it is owned by the
  bot's loop module.

## Left to the builder

- Table shape, lock mechanism and the module's home under
  `swingbot/core/marketdata/`.
- How askers declare their freshness and priority (decorator, argument,
  context).
- The exact recent-window size for D3, and the weekly refetch slot.
- The yfinance pacing default, the VIX proxy symbol and the IEX-stale
  fallback for D5.
- Plan task order and parallelisation.

## What follows

- Discord message-delete pacing (the 347 Discord 429s), as its own small fix.
- The v106 soak's unexplained in-session cold-fetch slowdown
  (`docs/superpowers/results/2026-10-11-v106-soak-attempt-3.md`) should be
  re-measured once D3 removes the cold scans.

## Panel review

Spec review on 8685bfe6, run serially: staff-engineer (opus), quant-engineer (sonnet), veteran-trader (sonnet). No seat returned CLEAN. Every BLOCKING finding was applied.

- staff-engineer [BLOCKING]: fail-open only on the budget, not on the lock or cache, and no rule for a dead lock holder or a hung query -- applied (D1 Failure behaviour)
- staff-engineer [BLOCKING]: quote timestamp and age are stored-record shape changes outside schema-evolution -- applied (D2)
- staff-engineer [BLOCKING]: rollback is only "behind a flag" -- applied (## Rollout and rollback: one flag per part, CSV format unchanged, additive migrations, rollback_to.sh)
- staff-engineer: baseline day vs baseline week inconsistent -- applied (five trading days)
- staff-engineer: fixed `.tmp` name with concurrent CSV writers -- applied (single writer under lock, unique temp names)
- staff-engineer: waiter-deadline outcome undefined -- applied (priority 1-2 fetch themselves; 3-5 get cached or fail)
- staff-engineer: admin tape depends on the bot being up -- applied (admin self-fetches after 3 min stale)
- staff-engineer: worker Postgres connection count unbounded -- applied (one lazy connection per worker; plan states the count)
- staff-engineer: no owner or removal for flags and the re-anchor job -- applied (follow-up removes the flags; re-anchor is a bot loop task)
- staff-engineer: rebuild spread over three lanes -- applied (one entry point in `planning/`)
- staff-engineer, quant-engineer [BLOCKING, merged]: the 1 % tolerance is blind to ordinary dividends -- applied (D4 event trigger + fingerprint, 1e-4 overlap tolerance, one constant)
- quant-engineer [BLOCKING]: an overlap-only check cannot see an ex-date older than the window; fewer than 3 common bars returns None -- applied (event trigger primary; under 3 bars means refetch)
- quant-engineer [BLOCKING]: parity fixture does not discriminate -- applied (four named fixtures, Volume included)
- quant-engineer: state the cache's adjustment basis; a refusal must not take the shallow live-only path -- applied (D4)
- quant-engineer: rebuild must not mix a fresh-basis price with mis-adjusted history -- applied (follows from D4)
- veteran-trader [BLOCKING]: chart and embed must use the rebuilt levels -- applied (D5)
- veteran-trader [BLOCKING]: rebuilding from a stale print on thin names -- applied after asking the partner (trade < 60 s, then bid/ask mid < 60 s, else keep scan price flagged "price not confirmed live")
- veteran-trader [BLOCKING]: stop floor, 2 % cap band and horizon-noise checks not in the re-run list -- applied (D5)
- veteran-trader: extended-hours quotes should anchor to the last regular close -- rejected: the partner asked for plans to reflect current price action; mitigated by the same 60 s price order plus a session label
- veteran-trader: 5 s clock start and miss handling undefined -- applied (per-symbol quote completion; one re-quote, then post with true age, counted as a miss)
- veteran-trader: a rebuild must not alter posted plans -- applied (D5)
- veteran-trader: stop monitoring should rank above the re-quote -- applied (D6 now has five tiers)
- veteran-trader: ATR/stop consistency under the rebuild -- applied (same frame; only the price input changes)
- veteran-trader: ETF proxies misread as index levels -- applied (proxies show change % only)

Added after the panel, from the partner: admin Dashboard ≤ 15 s; every other admin page reuses any cached price ≤ 60 s old (D2).
