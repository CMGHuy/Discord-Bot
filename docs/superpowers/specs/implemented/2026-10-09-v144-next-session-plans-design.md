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
- **Phase 2's first screen (decided 2026-10-09):** `next_session_stop` — a
  market-entry candidate re-expressed as a buy stop above the signal-day high
  (sell stop below the low for shorts), valid for the next session only. If it
  passes, a later spec lets market candidates enter this lane through it. If
  it fails, it is closed and they stay watch-only.

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
3. **Issue: stop-entry candidates only.** A candidate the builder makes as a
   `stop_entry` (today, only confluence breakouts: `builders.py`,
   `scenario_is_breakout`) becomes a `TradePlanV2` in `PENDING` with
   `origin="next_session"` and `valid_session=<D as ISO date>`. Its levels are
   frozen at issue.
   **Market-entry candidates are never issued** (decided 2026-10-09). A market
   plan is born ACTIVE at the signal close (`record_transition(...,
   reason="market_entry")`), and that price cannot be traded at 23:30.
   `STRATEGY_ENTRY_TYPE` is `{}`, so every strategy-source plan is a market
   entry. Converting them to a resting order would be a new entry rule, and a
   new entry rule needs a screen first (see Phase 2 below). They appear in the
   digest as **watch** names with their levels and the line `market entry:
   fills at the signal close, no resting order for tomorrow`.
   No live limit plan exists in Phase 1: `STRATEGY_GATES` masks both limit
   strategies with `directions: ()`.
4. **Near-misses.** Candidates that reach the plan builder but fail a gate are
   kept in the digest with their reason (for example `risk 2.6% > 2% cap`,
   `earnings in 2 sessions`, `no qualifying target`), reusing the existing
   `plan_v2_rejected` / `not_logged_reason` strings. Near-misses and watch
   names are not plans and never enter the book. Expect early outlooks to hold
   few plans and several watch names.
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
- `valid_session` and `origin` are new fields on the stored plan record, and
  `origin` on the trade record too (see Independence). Under
  `schema-evolution.md`, adding a field needs no migration: it lands in `doc`,
  and records without it read as regular. Promotion to a real column is
  justified only by a real SQL use. One qualifies: a `PlanRepository` query by
  `valid_session` (wrap-up and duplicate check), indexed. That promotion is an
  Alembic revision `v144_001` (`down_revision = "v116_002"`) with a
  `PROMOTION_REASONS` line.

## Independence from regular plans

- **The "already open" guard ignores evening trades.** `already_open` is a
  trade check, not a plan check: `trade_log.open_trade_for_ticker(ticker) is
  not None` (`scan_run.py` ~800, `short_run.py:281`). The trade record
  therefore carries `origin`, and `open_trade_for_ticker` gains an origin
  filter defaulting to regular-only. Otherwise a filled evening trade would
  block tomorrow's regular plan, and steer the reversal path, on that ticker.
  Symmetrically, the 23:30 run's duplicate check counts only `next_session`
  plans and trades, so a ticker with a regular plan can still get an evening
  one.
- **No cross-cancellation.** Neither lane ever cancels or supersedes the other.
- **Risk is surfaced, not prevented.** When a regular plan is open or pending
  on the same ticker, the evening card says
  `⚠ regular plan also open on <TICKER> (<direction>, risk $X)`, and the
  regular alert says the reverse. The partner sees the combined dollar risk
  before placing a second order. This is display only and gates nothing.

## Cancellation-reason catalogue

Two cancellations happen **during** session D, through the existing live
transitions, and only gain a readable message here. Two more are decided **at
D's close** by the new expiry classifier. Each reason has a code (stored in
`status_history` as `reason=`) and a one-line message (in the wrap-up and the
cancellation notice).

| Code | Decided | When | Message (example) |
|---|---|---|---|
| `invalidated` | in session (existing `cancelled_invalidated`) | Price through the stop before the trigger | `Traded 95.80 through the 96.00 stop before triggering; the setup broke` |
| `risk_cap` | in session (existing `cancelled_risk_cap`) | Triggered, but the fill breaches the 2% cap | `Gapped to 104.10 at the open; the stop distance (3.1%) is over the 2% cap` |
| `never_triggered` | at close | Trigger never reached in RTH | `High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger` |
| `no_session_data` | at close | Neither an hourly nor a daily bar for D | `No price data for <D>; plan expired unevaluated` |

**Data source at close.** The hourly cache cannot be trusted to be fresh at
D's close: `market_data_refresh` wakes every `MARKET_DATA_REFRESH_MINUTES`
(60), and `data_refresh.is_stale` uses the file mtime with
`REFRESH_HOURS["hourly"] = 4.0`, so the CSV can miss D's last 4–5 RTH bars.
The classifier uses the hourly cache only when it covers D's last RTH hour;
otherwise it uses D's daily bar via the existing `PlanManager.daily_frame_fn`
(daily bars are RTH-only, so its high/low is exactly what `never_triggered`
needs). The classifier runs on the first poll after the close and never
fetches. The wrap-up does not fetch either.

`never_triggered` is the expected common case, so its message carries the
distance (percent and ATR multiples) between D's extreme and the trigger. That
makes a run of near-misses legible over time.

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
- **Wrap-up at D's close + 15 min**, with the time taken from
  `session_close(D)` in ET (not `daily_recap`'s `SESSION_END_HOUR:15` Berlin;
  only its minute poll and fired-once guard are reused). It posts once all of
  D's evening plans are terminal, as one message: filled (with entry), cancelled (with the catalogue message), and a
  count line, for example `3 issued · 1 filled · 2 cancelled (never_triggered ×2)`.

## Analytics

Evening plans flow into the journal like any paper trade, carrying `origin`.
Every pooled figure filters to `origin is None`, so today's numbers are
byte-identical before and after this ships. A test pins that against a fixture
book holding one evening trade. Where the filter goes:

- **The v93 ledger rule** (`swingbot/core/tracking/ledger.py`): `is_main` and
  `is_weak` also require `origin is None`. This covers `get_stats` (feeding
  `track_record` in `analyze.py`), every `get_trades(ledger="main")` caller,
  and the dashboard main-ledger stats. The dashboard's weak panel, which tests
  `not is_main`, becomes `is_weak`.
- **Readers the ledger rule misses**, each filtered explicitly:
  `analytics/scope.select` (raw `ledger` compare; the admin cohort filter also
  lives here), `JournalStore.entries()` → `params._journal_entries` (E31/E32
  overrides), the soak verdict's `PlanStore().all()` (`stats.py`,
  `admin/api_v1/analytics.py`), `pnl_calendar` and `snapshots`.
- **Badges** come from the backtest registry (`registry.get_badge`), so
  evening trades cannot move a badge tier. The
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

## Amendments (2026-10-09, before the plan)

Plan-writing checked the spec against the code and found six errors, now fixed
above:

1. Market entries, the dominant type, were not covered. They are excluded and
   shown as watch names, and Phase 2 screens `next_session_stop` (partner
   decision).
2. `already_open` is a trade check, so `origin` also goes on the trade record.
3. No live limit plan exists, so the limit wording was dropped.
4. `invalidated` and `risk_cap` are decided in session, not at close.
5. The wrap-up time comes from the NYSE close, not `SESSION_END_HOUR:15`.
6. A new field needs no migration. Only the `valid_session` promotion takes
   one.

The open point (is the hourly cache fresh at close?) is resolved: it is not,
so the classifier falls back to the daily bar.
