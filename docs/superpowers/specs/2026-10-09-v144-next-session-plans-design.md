# v144 — Next-session plans: a 23:30 outlook scan whose plans live for one session

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot minor (a new scheduled job, a new plan origin and a new Discord surface; regular plans unchanged)
**Edge:** none (integrity) — a pre-session planning view for the partner's resting orders. Phase 1 issues no new signal: it re-times the existing strategies' plans onto a one-session validity window, and every such plan is a segregated cohort excluded from pooled ExpR, win rate and badge scoring. Any claim that the cohort adds volume or expectancy is deferred to a later, measured spec.
**Screen:** exempt (integrity)
**Status:** spec written 2026-10-09; no plan yet.

## Why

The partner places resting orders from alerts (see the memory note on real-money
trading). Today plans appear during the session, so the partner sees the day's
setups only once it is underway. The ask: at 23:30 Berlin, Sunday to Thursday,
scan the watchlist and issue the plans for **tomorrow's session** in advance,
so the partner starts the day knowing which tickers can trigger, at what
levels, and why.

These plans differ from regular pending plans in one way: **they are valid for
tomorrow's session only.** If one is not an open trade by that session's close,
it is cancelled, and the cancellation states a specific reason.

**Regular pending plans must be unaffected.** This is an extension that adds a
parallel lane and never changes the existing one.

## Scope: two phases, this spec is Phase 1

- **Phase 1 (this spec).** Plans come from the **existing** strategies and the
  confluence scan, run on today's closed daily bar. Weekly and hourly price
  action are shown as context on each card and are **display-only**: using them
  as a gate would be a new filter, and a new filter needs a `SCREEN-PASS`.
- **Phase 2 (not specced).** A new multi-timeframe chart-pattern method
  (hourly/daily/weekly structure against chart patterns). It is a new entry
  strategy, so it first runs the Stage −2 idea screen
  (`scripts/backtest/screen_idea.py`, one shot) and gets a spec only on
  `SCREEN-PASS`. It plugs into the lane built here as one more signal source.

## Decisions settled with the partner (2026-10-09)

| Question | Decision |
|---|---|
| Signal source | Both, phased: existing strategies now, new multi-TF method screened later |
| Book | Full paper trades tagged `origin="next_session"`; reported as their own cohort; **excluded** from pooled ExpR, win rate and badge scoring |
| Overlap with regular plans | **Fully independent.** Both may exist on one ticker; neither creates, blocks, cancels or modifies the other |
| Delivery | 23:30 digest + one plan card per plan (with chart); a wrap-up after the session close |

## Session arithmetic (Berlin vs NYSE)

`SESSION_START_HOUR`–`SESSION_END_HOUR` (08:00–23:00 Berlin) is 02:00–17:00 ET.
The plan manager never fills on a pre-open print (`plan_manager.py`, the
`RTH_OPEN` check), so an evening plan can **fill only during the regular NYSE
session**, 09:30–16:00 ET (15:30–22:00 Berlin, 14:30–21:00 in the DST-mismatch
weeks; always computed in ET, never as a hard-coded Berlin hour). "Valid for the
whole session" therefore means the plan is open for fills from the RTH open of
session D to D's official close (13:00 ET on a half-day, `session_close`).

The target session D is **the first NYSE session after the run date**, taken
from the session calendar. Sunday 23:30 targets Monday; Thursday 23:30 targets
Friday. If the run date's next calendar day is not a session (for example
Thursday before Good Friday), the job posts "No NYSE session tomorrow" and
issues nothing. It never skips ahead to a later session, because the partner
asked for a view of *tomorrow*.

## Flow

1. **Trigger.** A new `next_session_scan` loop with the same shape as
   `weekend_deep_scan_task`: a minute-resolution poll, fires at 23:30 Berlin on
   Sunday–Thursday, guarded against firing twice by
   `_scheduled_job_already_fired('next_session_scan', today)`. It runs off the
   event loop (`asyncio.to_thread`), like every other heavy scan. Two new
   `.env` fields in `swingbot/config.py`: `NEXT_SESSION_SCAN_ENABLED`
   (default `false`, so the feature ships inert) and `NEXT_SESSION_SCAN_TIME`
   (default `23:30`).
2. **Scan.** The existing confluence scan and plan builder run over the whole
   watchlist on the closed daily bar of the run date. The same gates apply
   unchanged: 2% dollar-risk cap, earnings blackout, regime, strategy masks.
   NO-LOOKAHEAD holds trivially: the run sits after the daily close and uses
   only bars that are closed.
3. **Issue.** Each candidate that passes becomes a `TradePlanV2` in `PENDING`
   with `origin="next_session"` and `valid_session=<D as ISO date>`. Each plan
   keeps its strategy's own entry type (stop entry or limit). Its levels are
   frozen at issue.
4. **Near-misses.** Candidates that reach the plan builder but fail a gate are
   kept in the digest with their reason (for example `risk 2.6% > 2% cap`,
   `earnings in 2 sessions`, `no qualifying target`), reusing the existing
   `plan_v2_rejected` / `not_logged_reason` strings. Near-misses are not plans
   and never enter the book.
5. **Session D.** The normal live loop advances evening plans exactly as it
   advances regular ones: fill, `risk_cap` at fill, invalidation, then
   active/partial management until an exit. Once filled, an evening plan is an
   ordinary open trade; the one-session window applies only to the pending
   state.
6. **Close of D.** Every evening plan still `PENDING` at D's official close is
   cancelled with a reason from the catalogue below. The wrap-up then posts.

## The one-session window: reuse, not a new mechanism

v119 already ships this behaviour for the compression short:
`PlanManager._compression_window` with `_eligible_session` (a calendar-counted
session, half-day aware, at-least-once expiry delivery, `expires_at` records
the real close). Phase 1 **generalises the trigger condition** from
"`plan.strategy == COMPRESSION_SHORT`" to "the plan has an eligible session",
where `_eligible_session` returns `plan.valid_session` when it is set and the
compression rule otherwise.

- Regular plans never carry `valid_session`. Their path through `_step_pending`
  (bar-count expiry, fill, risk cap, invalidation) is unchanged, and a test pins
  it unchanged.
- The compression short's behaviour is unchanged, and its existing tests stay
  green untouched.
- `valid_session` and `origin` are new fields on the stored plan record. That
  is a shape change, so it follows `schema-evolution.md`: an Alembic revision,
  nullable columns, no upcasting at read time. Existing rows read as
  `origin=NULL` (meaning regular) and `valid_session=NULL`.

## Independence from regular plans

- **The "already open" guard ignores evening plans.** `analyze.py:_decision_for`
  receives `already_open`, and that predicate must count regular plans only.
  Otherwise an evening plan would block tomorrow's regular plan on the same
  ticker, which would change the existing lane. Symmetrically, the 23:30 run's
  own "already open" check counts only `next_session` plans, so a ticker with a
  regular plan can still get an evening one.
- **No cross-cancellation.** Neither lane ever cancels or supersedes the other.
- **Risk is surfaced, not prevented.** When a regular plan is open or pending
  on the same ticker, the evening card says
  `⚠ regular plan also open on <TICKER> (<direction>, risk $X)`, and the
  regular alert says the reverse. The partner sees the combined dollar risk
  before placing a second order. This is display only and gates nothing.

## Cancellation-reason catalogue

The reason is computed from session D's own price data (hourly bars from the
`market_data/` cache, falling back to the daily bar) once D has closed. Each
reason has a code (stored in `status_history` as `reason=`) and a one-line
message (in the wrap-up and the cancellation notice).

| Code | When | Message (example) |
|---|---|---|
| `never_triggered` | Trigger never reached in RTH | `High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger` |
| `invalidated` | Closed through the stop before the trigger (existing rule) | `Closed 95.80 through the 96.00 stop before triggering; the setup broke` |
| `risk_cap` | Triggered, but the fill would have breached the 2% cap (existing rule) | `Gapped to 104.10 at the open; the stop distance (3.1%) is over the 2% cap` |
| `no_session_data` | No quote for D reached the bot | `No price data for <D>; plan expired unevaluated` |

`never_triggered` is the expected common case, so its message carries the
distance (percent and ATR multiples) between D's extreme and the trigger. That
makes a run of near-misses legible over time. Limit plans read the same way
with "low" in place of "high" for a bullish buy limit, and the limit's cancel
level (v131) when it fired first: `Leg ran past the 98.50 cancel level; limit
withdrawn`.

## Discord surface

- **23:30 digest, "Outlook for <weekday D>":**
  - SPY/QQQ regime line: daily trend plus weekly trend.
  - The plans issued: ticker, direction, strategy, entry/stop/target, dollar
    risk.
  - The near-misses with reasons.
  - Tickers skipped because a `next_session` plan already exists.
  - An empty run still posts a one-line digest, so silence never means failure.
- **Per-plan cards:** the existing trade-plan embed and chart, plus:
  - an `Outlook · valid <D> only` badge;
  - a context line, for example `Weekly: above 20w MA, higher lows · Hourly:
    holding 1h swing low 99.10`;
  - the ⚠ overlap line when it applies.

  The context line uses the existing hourly/weekly frames and is display only.
- **Wrap-up at D's close + 15 min** (the `daily_recap` trigger shape), one
  message: filled (with entry), cancelled (with the catalogue message), and a
  count line, for example `3 issued · 1 filled · 2 cancelled (never_triggered ×2)`.

## Analytics

Evening plans flow into the journal like any paper trade, carrying `origin`.
Every pooled figure (ExpR, win rate, badge tiers, edge priorities) filters to
`origin IS NULL`, so today's numbers are byte-identical before and after this
ships. A test pins that against a fixture book holding one evening trade. The
admin analytics gain a cohort filter (`origin = next_session`) showing N,
fill rate (issued → filled), win rate and ExpR of the filled trades, and the
cancellation-reason histogram. Deciding whether the cohort ever pools is a
later, measured decision and is out of scope here.

## Error handling

- The scan fails or data is stale (the daily bar for the run date is missing):
  post the digest with `Outlook unavailable: <reason>` and issue nothing. No
  partial plan set.
- The bot is down at 23:30: the scheduled-job guard lets the poll fire late,
  but only before the RTH open of D (15:30 Berlin). After that the run is
  skipped and logged; it never issues plans into a session already underway.
- The bot is down at D's close: the at-least-once expiry delivery from v119
  cancels on the next poll. `expires_at` still records the real close, and
  the wrap-up posts once all of D's evening plans are terminal.

## Testing

- Calendar: Sunday→Monday, Thursday→Friday, Thursday before a holiday (no
  session, no plans), half-day close, DST-mismatch week (fill window in ET).
- Lifecycle: evening plan fills inside RTH; never fills pre-open; cancelled at
  close with each catalogue reason; once filled it is managed like a regular
  plan and is not cancelled at close.
- Independence: the regular `already_open` check ignores evening plans and
  the evening check ignores regular plans; a regular plan's `_step_pending`
  output is identical with and without an evening plan on the same ticker;
  the compression short's tests are unchanged.
- Analytics: pooled ExpR, win rate and badges are identical on a fixture book
  with and without an evening trade.
- Scheduler: fires once at 23:30 Sunday–Thursday, never Friday or Saturday;
  a late fire is suppressed after the RTH open of D.
- Every new or changed function stays below complexity 15.

## What this does not do

- No new signal, filter or threshold (Phase 2 owns any new method, behind its
  screen).
- No change to regular plans, their expiry, their dedup or their alerts beyond
  the display-only ⚠ overlap line.
- No orders: paper trades only, as everywhere in this bot.
- No pooling of the cohort into headline statistics.

## Open point for the plan

Whether hourly bars for D are fresh in `market_data/1h` by D's close + 15 min
(the refresh has a 4h staleness window), or whether the wrap-up has to fetch
D's hourly bars itself. The plan should check `market_data_refresh` and pick
one.
