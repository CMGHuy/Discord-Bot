# v188 — Cancelled-plan precision

**Version:** ui 1.35.0 · bot 2.14.4
**Bump:** ui patch, bot patch
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

## Method additions from the panel review (frozen before any row is scored)

These bind the builder and are fixed here so no threshold is chosen after the
numbers are seen.

**Reasons and origin.**
- The reason set is a closed allowlist: `risk_cap`, `invalidated`, `expired`. Any
  other cancel reason found at build time (for example the `session_expiry` codes
  written by `plan_manager._expire_window`, `session_expiry.py:27-28`) lands in a
  visible `other` bucket with its own N; it is never dropped or merged silently.
- For outlook/NEXT_SESSION plans `invalidated` and `risk_cap` are classified after
  the fact from the session's bars, while live plans write them from the live
  price (`plan_manager.py:886-890` vs `:941,958`). Each row records `plan.origin`
  and the screen can filter by it. Cards pool both by default and say so.
- The outcome for a plan whose trigger is not reached after the cancel is named
  `untriggered_after_cancel`, not `never_triggered`, so it cannot collide with the
  existing `session_expiry` reason code of that name.
- Each row also carries long/short and horizon, and the results can be split by
  each. The count figures (76 / 49 / 22 / 5) were read at spec time and must be
  re-queried at build time, never carried forward.

**The `risk_cap` entry.** `risk_cap` fires only after price has crossed the
trigger (`fill = max(price, trigger)`, `plan_manager.py:934-949`), so replaying
from the bare trigger uses a narrower risk than was ever on offer. The
`cancelled_risk_cap` event detail stores the live `entry_price`. For `risk_cap`
the screen therefore shows **both** entry models side by side (planned trigger,
and the event's crossing price) and never one without the other. The pooled
headline is shown **with and without** `risk_cap`.

**What `risk_cap` precision means.** The cap limits dollar risk, so a TP1 hit does
not make that cancel a mistake. On the screen the `risk_cap` verdict is labelled
"outcome of the skipped setup, unaffordable at the cap", never "wrong cancel", and
the table carries the cap-implied position size.

**Frozen definitions.**
- `untriggered_after_cancel` means the daily bars never trade through the trigger
  level inside the window (high >= trigger for a long, low <= trigger for a short).
  A touch counts. For `risk_cap`, whose fill happened on the cancel day, the
  re-touch rule applies the same way.
- R for a TP1 hit is the full target R, `|tp1 - entry| / |entry - stop|`, with no
  partial exit. The screen says so, because the bot does not bank winners in full.
- A plan with no stop or TP1 hit inside the window is `unresolved` and is also
  marked to the window-end close, with its R shown, so the drift is visible. It
  stays out of precision. The screen shows how many of the plans survive into the
  precision N, next to the headline.
- A same-bar double touch counts as the stop, which leans toward "right cancel".
  The screen shows how many verdicts were decided by such a tie.
- Small-N marker: any figure with **N < 10** is marked, including the headline of
  a filtered view and the `risk_cap` secondary row. N is printed on every figure.

**Baseline and uncertainty.**
- The same stop-before-TP1 replay runs on the **filled** plans from the same
  window, strategy and horizon, and the screen shows cancelled-plan precision next
  to that baseline loss rate. Without it, a high "right cancel" rate may just be the
  base rate of a book that loses most of its plans.
- Each headline and card carries an interval from `week_cluster_bootstrap`
  (`swingbot/core/backtesting/instrument/stats.py`), because one gap day can trip
  `risk_cap` on many tickers together.
- The window may span rule or config changes (`plan_stop_ceiling`, v183 sizing).
  The results record the config in force where it is recorded and the screen lists
  the known rule-change dates in the window, so a pooled figure is not read as one
  rule.

**Honest labelling (the financial-advisor blockers).**
- Headline and cards carry a visible caption: "hypothetical replay, before
  commissions, slippage and tax".
- The headline pairs **net R** (R avoided minus R missed) with precision at the
  same prominence, N beside both. Precision alone can sit above 50% while net R is
  negative, because TP1 wins and stop losses differ in size. Precision stays in the
  headline because the partner asked for that number.
- The table carries a strategy badge-tier column, and the screen shows a "data as
  of" stamp for the bars used.

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
- **Bump `ui patch, bot patch`:** per `working-conventions.md` § The three levels,
  minor is reserved for a component that is materially different to its users; a
  new screen is a patch. (Changed from `ui minor` by the panel.)

## Architecture constraints from the panel review

- **Price source.** `scripts/reports/autopsy/bars.py` reads `backtest_cache`-format
  CSVs from a directory it is given; nothing on the VM refreshes
  `data/backtest_cache/` (no cron row, `docs/deploy/DEPLOY_HETZNER.md:344-353`). The
  admin precedent reads `market_data/` through `data_store.load_normalized`
  (`swingbot/core/analytics/day_sparklines.py:5-9`). The builder picks the source
  production actually keeps fresh, states which, and confirms it is split-adjusted
  and lookahead-safe with the `quant-engineer` and `no-lookahead` checks. The
  screen shows the data-as-of date.
- **Imports.** The verdict module is pure, with injected bar and plan loaders, as
  `day_sparklines.py` is. If it needs the stop-before-TP1 rule from the
  simulators, the spec's builder names that import direction and justifies it
  against `docs/claude/architecture.md`.
- **Cost.** Computing on request replays every cancelled plan inside the admin
  container, which shares a host with the bot (`docker-compose.yml:111-118`). A
  per-plan cache is a new store, so an Alembic revision with an owner and a rule
  that a verdict is final once its window closes. The builder chooses and states
  the cost.
- **Blast radius.** The route lives only in `admin_ui.py`'s process, never in the
  bot loop. A failure shows an error on this one screen and nothing else. Rollback
  is the normal image rollback with no data step.

## Left to the builder

Module and route names, the table pager size, the card styling, and the cache
choice above.

## Panel review

- staff-engineer: reason set omits `session_expiry` codes (`never_triggered`,
  `no_session_data`) -- applied (closed allowlist plus visible `other` bucket)
- staff-engineer: outlook plans classify `invalidated`/`risk_cap` after the fact,
  live plans from live price -- applied (`plan.origin` recorded and filterable)
- staff-engineer: outcome name `never_triggered` collides with an existing reason
  code -- applied (renamed `untriggered_after_cancel`)
- staff-engineer: no production source of fresh bars for the cache -- applied
  (price-source constraint)
- staff-engineer: package import directions unnamed -- applied
- staff-engineer: request-time compute versus a cache store costs -- applied (builder
  states cost)
- staff-engineer: blast radius and rollback unwritten -- applied
- staff-engineer: `ui minor` does not fit the three levels -- applied (`ui patch`)
- staff-engineer: precision built on mixed small-N buckets (handed on) -- applied via
  the quant and advisor items
- quant-researcher: no base rate beside precision -- applied (baseline loss rate on
  filled plans)
- quant-researcher: `risk_cap` trigger entry is untradeable and inflates R missed --
  applied in part: both entry models shown side by side and the headline shown
  with and without `risk_cap`; the partner's trigger-entry decision stays as the
  primary replay for the other reasons
- quant-researcher: `risk_cap` verdict measures the setup, not the decision --
  applied (relabelled, cap-implied size)
- quant-researcher: `untriggered_after_cancel` undefined for `risk_cap` -- applied
  (frozen touch rule)
- quant-researcher: dropping unresolved plans biases precision -- applied (marked to
  market, surviving N shown)
- quant-researcher: same-bar tie leans toward "right" -- applied (tie count shown)
- quant-researcher: no interval -- applied (`week_cluster_bootstrap`)
- quant-researcher: small-N threshold unset -- applied (N < 10, frozen)
- quant-researcher: results split only by reason -- applied (long/short, horizon)
- quant-researcher: pooling across rule changes -- applied (rule-change dates listed)
- quant-researcher: counts not re-derived -- applied (re-query at build)
- quant-researcher: OHLCV cache choice (handed to quant-engineer) -- applied via the
  price-source constraint
- financial-advisor BLOCKING: figures not marked hypothetical and pre-cost -- applied
  (caption)
- financial-advisor BLOCKING: precision leads, net R secondary -- applied in part:
  net R now has equal prominence beside precision; precision stays in the headline
  because the partner explicitly asked for that figure. Raise with the partner if
  they want net R to lead.
- financial-advisor: `risk_cap` read as "loosen the cap" -- applied (relabel,
  position size)
- financial-advisor: R for a TP1 hit undefined, excluded share hidden -- applied
- financial-advisor: no badge tier or data-as-of -- applied
- financial-advisor: small-N marker only on `expired` -- applied (N < 10 everywhere)
