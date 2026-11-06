# v216 — Confluence limit entry: live path (split from v212)

**Version:** ui 1.40.0 · bot 2.17.0
**Bump:** bot patch (inert: every branch sits behind `CONFLUENCE_LIMIT_ENTRY_F`, which stays 0 until the partner switches it on)
**Edge:** expectancy — the live half of v212's limit entry. It adds no lift of its own; it lets a v212 Stage 3 pass reach the live book with the same fill rule the measurement scored.
**Screen:** exempt (post-signal) — inherited from v212
**Panel:** veteran-trader, risk-manager, senior-engineer
**Split from:** [v212](2026-11-06-v212-confluence-limit-entry.md) G4. On 2026-11-06 the v212 plan came to 22 tasks against the 20-task cap; the partner cut the live path out so v212 holds the rule, replay, measurement and verdict.
**Gate:** implement **only after v212 records a Stage 3 PASS**. On any other v212 verdict this spec moves to `no-lift/` unimplemented.

## Why

v212 measures a confluence long that rests a limit partway down to the
support, stop just under it (rules 1–9 of v212's "The rule (frozen here)",
referenced here by number, never restated). The measurement needs only
the knob, the geometry helper, the shared fill rule `bar_outcome` and the
replay. Building the live path before the measurement answers would ship
code for an edge that may be NO-LIFT, so it waits here.

If v212 passes, the partner decides whether to set the knob live. Before
that can happen, someone resting orders before the open must get an alert
they can place as a bracket order, and the bot must follow the order
through every state change exactly as replay scored it.

## Goals

- **G1. Live fill, same rule as replay (v212 rule 6).** `plan_manager`'s
  pending-limit step gains an arm branch that calls v212's
  `limit_entry_rule.bar_outcome`. For this arm only:
  - a gap through the stop fills at the open and closes at that open with
    the new `filled_stopped_gap` event (never today's silent
    `at_or_beyond_stop` cancel). The loss is always booked: the heat guard
    (G2) does not run on this path, because a trade opened and closed in one
    step carries no ongoing heat, and when no placeholder trade exists the
    step logs the trade itself (`log_trade`). The test cases cover both
    with and without a placeholder;
  - `_fill_pending`'s `risk_cap` check reads the planned `|L − stop|`, not
    the gap fill price;
  - a price already at or under L when the alert is sent is marketable and
    fills at the quoted price, **only inside the regular session**
    (`_arm_regular`); an extended-hours print never fills as marketable.
    The count is disclosed in the shadow report;
  - **shadow-report disclosures:** the marketable-at-alert count; the
    gap-stop losses as a distribution in R and in dollars at the alert's
    size, with the worst case (a gap loss can exceed the planned 2% dollar
    risk); and how many fills used the first RTH tick as a stand-in for an
    unknown open.
  - **Named live-vs-replay gap:** replay scores daily bars (a wick to
    `L - tick` fills); live sees one-print polls, so an intraday wick
    between polls can fill a real broker order while the bot still shows
    PENDING (and a T1 print between polls can be missed). This is not
    assumed away. The alert's bracket wording (G4) attaches the stop at the
    broker, so a fill the bot missed still carries its stop.
    Reconciling missed fills from the day's bar is listed under What
    follows.
  Out-of-scope plans keep today's path byte for byte.
- **G2. Heat reserved at alert, re-checked at fill.** *(Revised by the
  2026-11-06 panel and the partner's call: resting limits reserve risk.)*
  - **At alert:** a pending arm limit counts its planned risk (alert size x
    `|L - stop|`) against `PORTFOLIO_HEAT_CAP_PCT`, the sector cap, the
    cluster cap and `MAX_OPEN_POSITIONS` from the moment it is alerted
    until it fills, expires or is cancelled. A new alert that would breach
    a cap counting open positions *plus* reserved pending limits is not
    sent, and it is logged `plan rejected (heat_reserved ...)`. The worst case is
    that every pending limit fills on one gap day, and it is bounded by the
    caps.
  - **Divergence from v212, disclosed:** v212's portfolio pass reserved no
    heat (v212 rule 8). Live is therefore stricter: when a cap binds it
    alerts fewer limit plans than replay scored. The shadow report counts
    the alerts the reservation suppressed.
  - **At fill (backstop):** the heat, sector, cluster and
    `MAX_OPEN_POSITIONS` checks rerun against the then-open book, through
    the same pure check replay uses. They use the **alert's stored size
    and risk**, never a size recomputed at fill, because the broker order
    rests at the alerted size. A breach cancels the plan as
    `cancelled_limit` with reason `heat_at_fill` (event
    `cancelled_heat_at_fill`), logs `plan rejected (heat_at_fill ...)` and
    posts an urgent follow-up. Because the broker order may already have
    filled, the follow-up says: "If your order filled, close it at market
    or keep it and place the stop at S' now; otherwise cancel it." It never
    says "no position".
  - The guard's daily frames come from a cached-only reader
    (`runner_path.cached_daily_bars`), never a blocking download inside the
    poll lock.
  - **Throttles:** the drawdown and daily-loss throttles
    (`edge/throttle.py`, `risk_limits.py`) apply on the limit-alert path
    exactly as on every other alert path, and the plan pins this with a test.
- **G3. Event registration.** `cancelled_heat_at_fill` and
  `filled_stopped_gap` join every routing table `cancelled_limit` is in
  (`PENDING_CANCEL_EVENTS`/`NOTICE_EVENTS`, `_TRANSITION_LOG`,
  follow_notify, execution-feed `_EVENT_KINDS`, `PLAN_EVENT_KINDS`,
  session expiry). A test enforces that every cancel or close event appears
  in each table, so a placeholder paper trade is never left open (the
  2026-09-11 incident).
- **G4. Alert and follow-up text.** Each v212 limit alert states, as prices
  rounded to the tick: "Buy limit L" ("Sell limit" for shorts); "On fill:
  stop S′, TP1 T1 (TP2 T2)"; "Cancel the order if price trades at T1 before
  it fills"; "GTC: cancel it if still unfilled after 3 sessions (about
  the close of <date>)". The order is placed as a bracket/OCO with the
  stop and TP1 attached, where the broker supports it, so a fill the bot
  misses still carries its stop. The date is approximate because the bot
  has no holiday calendar (`approx_last_trigger_session`); the bot itself
  expires on real bars. The bot posts a follow-up for every state change:
  filled ("place the stop at S′ now"), expired ("cancel your order"),
  cancelled because TP1 traded first (urgent: "cancel now; if it already
  filled, close it"), cancelled for heat at fill (wording in G2), and
  filled-and-stopped on a gap ("if your order filled at the open, exit at
  market now unless your bracket stop already closed it"). `total_r` in
  these follow-ups is derived from the leg, never a literal. The
  gap-stop's 0R in the tests is the scored convention, and a comment says so. `instructions.ticket_for`,
  `plan_table.entry_line` and the lifecycle embed fields gain the limit
  wording for `is_arm_limit` plans only.
- **G5. Admin view.** The `why/levels-block` limit mapping ("Buy limit" /
  "Sell limit" at the trigger) is already on `main` since V151-10; this
  spec pins the pending-limit render with a test and edits it only if the
  test fails.

The extra alert volume (limit alerts plus follow-ups per day) comes from
v212's replay disclosures; this spec only ships the text.

## Non-goals

- Switching the knob on. That is the partner's call after reading v212's
  result, through `mirror-prod`.
- Rewording v113/v131 limit plans. Their "BUY AT MARKET" ticket and
  "CANCEL BUY STOP" cancel headline are pinned by existing tests and stay
  byte for byte; fixing them is a separate decision.
- Any change to the rule, grid or fill semantics: v212 froze them.

## Constraints

- Every function stays under complexity 15; `_step_limit`, `_fill_pending`
  and `_step_pending` gain branches only through named helpers.
- Knob 0 is byte-identical: alerts, follow-ups and the plan lifecycle of
  every out-of-scope plan are pinned.
- Tests ship with the work: each new event in each table; gap-through-stop
  (with and without a placeholder trade), gap-through-L, trade-through,
  touch-only and marketable-at-alert fills (inside and outside RTH); a
  first alert-session poll at or through the stop; every
  `_session_open_for` fallback (alert-session date, empty frame, stale
  last bar, tz-aware index, NaN or non-positive Open); the
  `PlanPersistFailed` retry; a short through-stop inside RTH; heat
  reserved at alert (suppress and pass); heat-at-fill cancel and pass at
  the alert's size, with the cluster branch on real frames; throttles on
  the limit-alert path; every alert and follow-up line for longs and
  shorts; the admin render.
- Shared arm-plan test builders live in `tests/planning/conftest.py` (or
  a helper module), never imported from a sibling test module.

## Plan

The tasks were already written as v212 plan part 2 (V212-6..V212-10 with
V212-9b) before the cut; the plan for this spec carries them over
renumbered, dependent on v212's V212-2 and V212-4 being on `main`.

## What follows

- **v212 Stage 3 PASS:** implement this plan, then the partner decides the
  knob.
- **Any other v212 verdict:** move this spec and its plan to `no-lift/`
  unimplemented.
- **Missed-fill reconciliation (follow-on idea, no spec):** when a
  session's daily bar lands, check whether its Low or High crossed
  `L - tick` or T1 while the bot showed PENDING, and post a late follow-up.

## Panel review

*2026-11-06: all three roles returned. Every finding is applied to this spec (G1, G2, G4, Constraints, What follows). For risk-manager 1, the partner chose to reserve heat at alert. The plan amendments follow in the plan's own commit. Veteran-trader 3's daily-bar reconciliation is applied as a disclosure plus the bracket wording, and the reconciliation itself is listed as a follow-on.*

BLOCKING
- veteran-trader 1: plan V216-3 L735/737 heat-at-fill cancel text "no position, no P&L" is false, because the broker's resting limit has already filled. The follow-up must tell the user to close at market or keep the position and place the stop, or the spec must make heat-at-fill a bot-book-only rule and disclose it up front. -- applied
- veteran-trader 2 + risk-manager 2: `filled_stopped_gap` (plan L38-41, L733 reuses `_stopped_copy`) gives no "exit at the open" instruction and no note on how a bracket stop fills on a gap. `_fill_and_stop_gap` (plan L549) runs the heat guard first, so a breach books `cancelled_heat_at_fill` instead of the gap loss and biases ExpR upward. Skip the guard on that path. -- applied
- risk-manager 1: spec G2 (L38-44) pending limits reserve no heat. State whether the alert-time gate counts pending limits, the maximum simultaneous fill risk, and that the cancel follow-up tells the partner to cancel or flatten at the broker. -- applied

ADVISORY
- veteran-trader 3: one-print polls (plan L31-41) miss intraday wick fills and TP1 trades between polls, and live uses `touch=False` where replay fills on touch. Name the divergence, and consider reconciling with today's daily Low/High. -- applied
- veteran-trader 4: alert text (spec G4 L51-57) never says GTC, and a DAY order lapses before the 3-session validity ends. -- applied
- veteran-trader 5: the manual T1 cancel (spec G4 L53-54) should recommend OCO/bracket, and the cancel follow-up should be urgent. -- applied
- veteran-trader 6: RTH-only stepping means "first tick stands in for the open". Disclose it in the shadow report. -- applied
- risk-manager 3: a gap-stop's realised loss can exceed the 2% dollar cap. Report the gap-loss distribution in R and dollars, plus a worst case. -- applied
- risk-manager 4: `make_fill_guard` (plan L431-453) re-sizes at fill instead of using the alert's stored size/risk_pct. Pin it to the alert's size or disclose the divergence. -- applied
- risk-manager 5: spec Constraints (L79-86) do not cover `edge/throttle.py`/`risk_limits.py` on the limit-alert and fill paths, and name no "plan rejected (...)" log for `heat_at_fill`. -- applied
- senior-engineer 1: no placeholder trade on an arm gap-stop (plan L314 vs `plan_manager.py:895-935`) means `_on_event` never calls `log_trade`, so the loss goes unlogged. Log it when `_persist_fill` returns None, and add a test. -- applied
- senior-engineer 2: "marketable at alert" can fire on an extended-hours print when `INTRADAY_RTH_ONLY` is off (plan L310/L40 vs `plan_manager.py:816`). Gate it on `_arm_regular` and add a test. -- applied
- senior-engineer 3: untested branches: `_session_open_for`'s five fallbacks, a first poll at or through the stop, the `PlanPersistFailed` retry, and a short through-stop inside RTH (plan L129-271). -- applied
- senior-engineer 4: the fill guard's `_manager_daily` can do a blocking 2-year download per ticker inside the poll lock (plan V216-2 L550). Use the cached-only `rp.cached_daily_bars`, and test the cluster branch with real frames. -- applied
- senior-engineer 5: "Valid through the close of <date>" uses `approx_last_trigger_session`, which has no holiday calendar (plan L936-940 vs `instructions.py:199-205`). Use a holiday-aware helper or soften the wording. -- applied
- senior-engineer 6: gap-stop `r: 0.0` is a hard-coded literal in tests (plan L63/182/215). Derive `total_r` (V216-4 L989) from the leg, and comment that 0R is the scored convention. -- applied
- senior-engineer 7: new tests import private helpers from sibling test modules (plan L93, L478). Move them to `tests/planning/conftest.py`. -- applied
