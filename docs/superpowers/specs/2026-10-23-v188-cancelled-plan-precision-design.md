# v188 — Cancelled-plan precision

**Version:** ui 1.35.0 · bot 2.14.4
**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-researcher, financial-advisor

## Why

The bot withdraws pending trade plans on its own: `risk_cap`, `invalidated` and
`expired` (`swingbot/core/planning/plan_manager.py:926-958`). Production holds
76 such cancelled plans (2026-07-27 to 2026-10-22: 49 `risk_cap`, 22
`invalidated`, 5 `expired`, no manual cancels). Nobody has measured whether those
calls were right. If a large share of cancelled plans would have reached TP1,
the cancel rules are throwing away winners, and that is worth knowing before
anyone touches a rule.

This spec builds the measurement and keeps it visible. It changes **no cancel
rule** and buys no edge itself (`Edge: none (integrity)`). Any later change to a
cancel rule is its own spec and needs its own screen evidence.

## Goals

- For every bot-cancelled plan, replay the price after the cancel and say
  whether the plan would have lost (cancel was right) or reached TP1 (cancel was
  wrong).
- Report **precision = right cancels / (right + wrong)**, overall and per cancel
  reason, with N on every figure.
- Report the R the cancels avoided and the R they missed.
- Keep it as a permanent admin screen that updates as new plans cancel.

## Non-goals and anti-goals

- No change to `plan_manager` cancel behaviour, risk caps or gates.
- No order placement (paper only; eToro stays demo-only).
- Not a fill-realism study. The replay uses the plan as written (see Decisions).
- Manual and linked-trade-closed cancels are your decisions, not the bot's, and
  stay out of the number. A precision figure that quietly mixes them would
  mislead.
- A precision number must never be shown without its N. 5 `expired` plans is not
  a rate.

## What the partner decided

1. **Scope:** bot-cancelled pending plans only; `invalidated`, `risk_cap` and
   `expired` (the last two are reported but flagged when N is small).
2. **Right cancel:** the replayed plan would have lost (stop hit first). **Wrong
   cancel:** TP1 hit first.
3. **Entry model:** the plan's own `trigger_price` as the entry, with its original
   stop and targets. `risk_cap` also gets a secondary row using the gap-open fill
   that caused the cancel.
4. **Watch window:** the plan's own horizon length, counted in trading days after
   the cancel. A plan with neither stop nor TP1 hit inside the window is
   **unresolved** and excluded from precision, shown separately.
5. **Deliverable:** a read-only analysis plus a permanent admin screen, layout A
   combined with B: a headline precision figure with R avoided / R missed,
   per-reason cards, right/wrong/unresolved counts with R, and a plan table that
   filters when a count or card is clicked.

## Method (the contract)

Source: Postgres `plans` where `status = 'CANCELLED'`; reason is
`doc.status_history[-1].reason`, cancel time is its `at`. Direction, trigger,
stop, TP1 and horizon come from the plan doc.

- The replay starts strictly **after** the cancel day's bar, never on it. This
  matches the no-lookahead convention in the plan manager and
  `scripts/reports/autopsy/bars.py` (`bisect_right` past the cancel day).
- Per bar: the stop is checked before TP1, and a same-bar touch of both counts as
  the stop (the conservative convention already used by the simulators).
- Long and short are mirrored. R for a hit is measured against the plan's own
  risk, `|trigger − stop|`.
- Outcomes per plan: `right` (stop first), `wrong` (TP1 first), `unresolved`
  (neither inside the window, or the window has not yet elapsed), `never_triggered`
  (price never traded through the trigger inside the window).
- Precision uses only `right` and `wrong`. All four counts are always shown.
- Price data: the split-adjusted daily OHLCV cache
  (`swingbot/core/marketdata/backtest_cache.py`). The alert-surface skill warns
  there are two OHLCV caches; the builder must pick the one the autopsy loader
  uses and say which.

## Screen

Layout A+B, designed for mobile, tablet and desktop together
(`docs/claude/ui-design.md`):

- Top: headline precision (`xx% of N`) and R avoided / R missed.
- Three reason cards (`risk_cap`, `invalidated`, `expired`), each with precision
  and N, and a small-N marker.
- Right / wrong / unresolved / never-triggered counts with R; clicking a count or
  a card filters the table below.
- Table: ticker, strategy, horizon, reason, cancel date, verdict, R. A pager and
  wrapping rules per the UI doc. Mobile is one column; tablet two.
- Mockup: `.superpowers/brainstorm/39359-1792764433/content/cancel-screen-layout.html`
  (gitignored).

## Constraints

- Read-only against production data; no schema change expected (all inputs are in
  the existing `plans.doc`). If a table or column turns out to be needed, that is
  a Postgres-only Alembic revision per `docs/claude/schema-evolution.md`.
- New functions stay under cyclomatic complexity 15.
- Ships its own tests: backend (verdict logic, long/short, same-bar tie, window
  edges, empty and all-unresolved cases) and frontend (screen, filters, small-N
  marker). Local tests run `/replicate-prod-db` first.
- The verdict logic lives in `swingbot/core/analytics/`, and the screen reads it
  through an admin API route.

## Calls I made (the builder should check these)

- **never_triggered is its own bucket.** Replaying at the trigger price means a
  plan whose trigger is never reached after the cancel is neither right nor wrong.
- **The cancel-day bar is excluded**, including for `risk_cap`, whose gap fill
  happened on that very day. The gap-open secondary row exists to cover it.
- **Unresolved includes windows that have not elapsed**, so recent cancels do not
  pull precision around.
- **`Edge: none (integrity)`** because this measures and changes nothing. Argue it
  differently if a panel reviewer disagrees.
- **Bump `ui minor, bot patch`:** a new screen is something you see, and a new
  read-only route is internal.

## Left to the builder

Module and route names, the table pager size, the card styling, and whether the
replay is computed on request or cached per plan (a cancelled plan's verdict only
changes until its window closes).
