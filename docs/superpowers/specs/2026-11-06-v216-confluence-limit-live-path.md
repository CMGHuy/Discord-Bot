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
    `at_or_beyond_stop` cancel);
  - `_fill_pending`'s `risk_cap` check reads the planned `|L − stop|`, not
    the gap fill price;
  - a price already at or under L when the alert is sent is marketable and
    fills at the quoted price; the count is disclosed in the shadow report.
  Out-of-scope plans keep today's path byte for byte.
- **G2. Heat at fill (v212 rule 8).** When a limit fills, the heat, sector,
  cluster and `MAX_OPEN_POSITIONS` checks rerun against the then-open book
  with the fill's actual risk, through the same pure check replay uses. A
  breach cancels the fill as `cancelled_limit` with reason `heat_at_fill`
  (event `cancelled_heat_at_fill`) and posts a follow-up. Pending limits
  reserve no heat.
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
  it fills"; "Valid through the close of <date>". The bot posts a follow-up
  for every state change: filled ("place the stop at S′ now"), expired,
  cancelled because TP1 traded first, cancelled for heat at fill, and
  filled-and-stopped on a gap. `instructions.ticket_for`,
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
- Tests ship with the work: each new event in each table; gap-through-stop,
  gap-through-L, trade-through, touch-only and marketable-at-alert fills;
  heat-at-fill cancel and pass; every alert and follow-up line for longs
  and shorts; the admin render.

## Plan

The tasks were already written as v212 plan part 2 (V212-6..V212-10 with
V212-9b) before the cut; the plan for this spec carries them over
renumbered, dependent on v212's V212-2 and V212-4 being on `main`.

## What follows

- **v212 Stage 3 PASS:** implement this plan, then the partner decides the
  knob.
- **Any other v212 verdict:** move this spec and its plan to `no-lift/`
  unimplemented.

## Panel review

*In progress (2026-11-06). The findings below are recorded but **not yet applied**. senior-engineer has not run yet. Resume: apply or reject each finding, run senior-engineer, then mark each line `-- applied` / `-- rejected: <why>`.*

BLOCKING
- veteran-trader 1: plan V216-3 L735/737 heat-at-fill cancel text "no position, no P&L" is false, because the broker's resting limit has already filled. The follow-up must tell the user to close at market or keep the position and place the stop, or the spec must make heat-at-fill a bot-book-only rule and disclose it up front. -- pending
- veteran-trader 2 + risk-manager 2: `filled_stopped_gap` (plan L38-41, L733 reuses `_stopped_copy`) gives no "exit at the open" instruction and no note on how a bracket stop fills on a gap. `_fill_and_stop_gap` (plan L549) runs the heat guard first, so a breach books `cancelled_heat_at_fill` instead of the gap loss and biases ExpR upward. Skip the guard on that path. -- pending
- risk-manager 1: spec G2 (L38-44) pending limits reserve no heat. State whether the alert-time gate counts pending limits, the maximum simultaneous fill risk, and that the cancel follow-up tells the partner to cancel or flatten at the broker. -- pending

ADVISORY
- veteran-trader 3: one-print polls (plan L31-41) miss intraday wick fills and TP1 trades between polls, and live uses `touch=False` where replay fills on touch. Name the divergence, and consider reconciling with today's daily Low/High. -- pending
- veteran-trader 4: alert text (spec G4 L51-57) never says GTC, and a DAY order lapses before the 3-session validity ends. -- pending
- veteran-trader 5: the manual T1 cancel (spec G4 L53-54) should recommend OCO/bracket, and the cancel follow-up should be urgent. -- pending
- veteran-trader 6: RTH-only stepping means "first tick stands in for the open". Disclose it in the shadow report. -- pending
- risk-manager 3: a gap-stop's realised loss can exceed the 2% dollar cap. Report the gap-loss distribution in R and dollars, plus a worst case. -- pending
- risk-manager 4: `make_fill_guard` (plan L431-453) re-sizes at fill instead of using the alert's stored size/risk_pct. Pin it to the alert's size or disclose the divergence. -- pending
- risk-manager 5: spec Constraints (L79-86) do not cover `edge/throttle.py`/`risk_limits.py` on the limit-alert and fill paths, and name no "plan rejected (...)" log for `heat_at_fill`. -- pending
