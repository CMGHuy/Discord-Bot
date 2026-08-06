# V29 — monitoring + pre-registered rollback triggers

**Date:** 2026-08-06
**Task:** plan v8 V29 (Phase V5, Rollout)
**Harness:** `scripts/live_cohort_report.py` (V8), run against `/opt/swing-bot/data`
**Status:** Step 1 armed. Step 2 pre-registered here — **all four legs armed**
(Leg 3 was retired as written and replaced by 3a/3b; see §3). The expectancy
leg **reads as FIRING on today's data** and **Leg 3a reads as firing too**;
what to do about either is a human-partner decision, not an agent's (§5).

---

## 1. Why this document exists before the numbers

V29 Step 2 as the plan wrote it: *"Roll back on any of: 5-day expectancy <
baseline − 0.05R; any crash attributable to the gate; survival rate below the
V12 floor."* Three clauses, none of which could be evaluated as written:

- **"5-day expectancy"** over *which* closes? The live book contains closes
  that were never live decisions (§2). Pooled, they dominate the window.
- **"baseline"** — the frozen V7 baseline is the whole book, 32% of which is
  the legacy cohort V13 has since cut. Comparing a now-100%-v2 window against
  a 68%-v2 baseline measures the cut, not the change under test.
- **"the V12 floor"** does not exist. V12 Step 2 is still open and needs a
  live week to produce one.

This file fixes all three *before* reading the current window, per the plan's
own pre-registration discipline.

## 2. The finding that forced the amendment

A close booked by `scripts/reconcile_open_plans.py` is not a live decision.
Reconcile replays the bars missed during downtime and **resolves a bar
spanning both levels as the stop** (`reconcile_open_plans.py:23`), so its loss
is the full gap move rather than a managed `MAX_LOSS_PCT` stop-out. The live
book, closes on/after 2026-08-03, canonical metrics:

| cohort | n | WR | expR |
|---|---|---|---|
| reconcile-booked | 32 | 35.71% | **−1.041** |
| live-polled | 30 | 39.29% | **−0.342** |

A 3× difference, and it is an artifact of the 2026-08-04 outage, not of
strategy quality. 25 of those 32 closed in the **same minute** (18:55). 35 of
53 recent losers are worse than the 1.75% cap, which live stop management
cannot produce.

**So the trigger as written fires on operational incidents.** Any outage would
trip it, and it would roll back whatever change happened to be in flight —
punishing the change for the outage's damage.

**Fixed at the source, not by inference.** `close_source` is now stamped by
the writer that knows: `performance.close_attribution()` labels every close,
`reconcile_open_plans.py` wraps its entry point in it, and
`live_cohort_report.py` slices on it. Timestamp clustering was rejected as
the mechanism — a genuine market break also closes many trades in one minute.

Trades closed before 2026-08-06 carry **no stamp** and report as `unstamped`,
never as `live`. Deliberate: defaulting them to `live` would put the outage's
32 reconciled closes straight into the cohort the trigger watches.

## 3. The armed triggers

**Denominator, for all legs:** closed trades with `close_source == "live"`.
Excludes `reconcile` (not a live decision) and `manual` (a human override with
no exit price — evidence about neither the strategy nor the change).

### Leg 1 — expectancy decay — ARMED
- **Baseline: −0.082R**, the frozen 2026-07-31 book's **v2 cohort** (n=337,
  WR 68.58%). The v2 cohort, not the whole book, because V13 cut the legacy
  path and the post-change window is 100% v2 — the whole-book baseline
  (−0.127R) would credit the change with the cut.
- **Fires when:** trailing 5-trading-day live-polled expectancy `< −0.132R`
  (baseline − 0.05R) **at n ≥ 30**.
- **The n ≥ 30 floor is part of the trigger, not a caveat.** At the ~131
  trades/week V27 assumes, five days is ~95 closes; the last five days
  produced 30 live-polled. Below 30 the window cannot distinguish −0.13R from
  −0.40R and the leg reports `INSUFFICIENT`, never `PASS`.

### Leg 2 — gate crash — ARMED
- **Fires when:** the string `ships ungated` appears in `logs/bot.log`, or any
  `gate evaluation failed` warning is logged.
- That signature is the broad `except` in `engine.py` that exists so a gate
  bug never costs an alert. It is exactly the failure mode V14 Step 2 found
  running silently in production for as long as `GATE_ENABLED` had been true,
  so it is the right thing to watch and it is free to watch.

### Leg 3 — survival rate — **RETIRED as written, replaced (amended 2026-08-06)**

**Correction to this document's own first draft.** It said Leg 3 must stay
unarmed until V12 Step 2 supplies a floor. That was wrong, and V12 Step 2
already said so on 2026-08-05: **the survival metric is structurally pinned at
1.0 and cannot move.** `wall` is unreachable by construction — every scenario
that exists has already passed `build_scenarios`' `min_reward` filter (≥3.0% at
every horizon), which is a strictly stronger form of the same test the 2.5%
reachability screen applies, on the same level; `no_levels` is unreachable
because `build_scenarios` requires both sides non-empty. Confirmed live over
**2,763 verdicts across 242 clean scan rows: wall=0, no_levels=0, survival =
1.0000 exactly.** No floor below 1.0 can ever fire. Waiting for V12 Step 2 to
supply one would have waited forever.

**What Leg 3 was actually protecting** (plan text): *"if survival is so low
that V36's forward gate cannot reach N, drop the V14 tier floor to C rather
than abandon the gate."* The risk is **the screens starving the pipeline**.
Survival was only ever a proxy for it, and it is a dead one. Replaced with two
legs that measure the risk directly.

#### Leg 3a — A+ production — ARMED
- **Fires when:** fewer than **10 A+ gate evaluations in a trailing
  10-trading-day window**.
- **Nothing invented:** this is V36 Step 1's own criterion (**≥10 A+
  signals**) over V36 Step 2's own window (~2 weeks), read forward instead of
  discovered at the end.
- **Current reading: 0 A+ in 16 live evaluations. Highest score ever recorded
  is 81.33, against `GATE_TIER_APLUS_CUT=90`** — the best live candidate to
  date is 8.7 points short of the tier V36 needs ten of. Tiers so far: C=14,
  B=1, A=1.

#### Leg 3b — book throughput — ARMED
- **Fires when:** the trailing 5-trading-day median of plans reaching the book
  (created, minus gate-rolled-back) falls below **6/day**.
- **Where 6 comes from, registered as a choice:** V27's power calculations
  assume ~131 trades/week ≈ 26/trading day, and the measured pre-gate median
  is **18/day** (range 14–45 over seven sessions). 6 is one third of the
  pre-gate median — low enough not to trip on ordinary quiet days, high enough
  that every downstream power calculation in this plan still works. It is a
  judgement, and it is written down before it is read.
- **Current reading: INSUFFICIENT.** Exactly one gate-on session exists
  (2026-08-05: 19 created, 12 rolled back, **7 survived**) and it was the
  session the RTH blackout ran in, so it measures the bug, not the gate.

#### The plan's pre-registered remedy does not fit Leg 3a — flagged
V12 Step 2 and the plan both say the response to this leg is *"drop the V14
tier floor to C"*. That fixes **3b** and **cannot** fix **3a**:
`GATE_MIN_TIER` selects which tiers are allowed through, it does not change
scoring, so lowering it produces **zero** additional A+ signals. If A+
production is the binding constraint on V36, the levers are the A+ cut itself
(`GATE_TIER_APLUS_CUT=90`) or the checklist weights — both of which move what
a tier *means*, and neither of which an agent should touch unilaterally.
Recorded for the human partner; no threshold was changed.

## 4. Step 1 — the weekly report

`python scripts/live_cohort_report.py --data /opt/swing-bot/data --baseline
/opt/swing-bot/archive/2026-07-31-pre-v8/trades.json --json <dated>.json`

First run recorded 2026-08-06: **558 records, 557 closed, 1 open**, ALL CLOSED
WR 53.41% / expR −0.192 / total −261.8%. Cohort detail — the tier ladder is
**non-monotonic** (C −0.183, B −0.151, A −0.239) and `VALIDATED` is the only
badge with positive expectancy (+0.781R, n=14, and n=14 proves little).

> **Correction, same day — that tier ladder is NOT the gatekeeper's.** This
> section first read the non-monotonic ladder "beside V14's tier-B floor",
> which conflates two different tiers computed by different code. The `tier`
> on a trade record is `plan.tier`, assigned by
> `plan_engine._apply_quality` → `core/quality.score_plan` — the **plan
> quality** tier. `GATE_MIN_TIER=B` acts on the **gatekeeper checklist** tier
> from `gate/score.assign_tier`. The two share a letter scale and nothing
> else. The non-monotonicity is real and worth investigating, but it says
> **nothing** about whether the gate's tier floor is set correctly, and must
> not be cited as if it did. The gate's own live tier distribution is the one
> in Leg 3a: C=14, B=1, A=1, A+=0 over 16 evaluations.
>
> **A second consequence, for anyone comparing this table across dates:** V25
> re-emitted the badge registry on 2026-08-06, making every registered
> strategy VALIDATED. `quality.component_badge` is 20 of the quality score, so
> from that date every live plan gains 20 points and the quality tier shifts
> **up** for plans that were previously WEAK. The `Tier` and `Badge` cohorts
> are therefore **not comparable across the 2026-08-06 boundary**. Neither
> field gates anything live — both are display and record-keeping
> (`embeds.py`, `log_trade`) — so nothing else moves.

## 5. Reading the armed triggers against today's book — the trigger FIRES

Since the frozen baseline (closes on/after 2026-07-31), split by the
timestamp heuristic because these predate the stamp:

| cohort | n | WR | expR |
|---|---|---|---|
| all closes since baseline | 93 | 42.86% | −0.577 |
| reconcile-booked | 32 | 35.71% | −1.041 |
| **live-polled** | **61** | **46.43%** | **−0.333** |

**Leg 1 fires.** −0.333R against a −0.132R threshold, at n=61 (above the 30
floor). Removing every reconciled close does **not** rescue it: the clean
cohort is still 0.251R below baseline, 5× the trigger's margin, and 22 points
of win rate below the baseline v2 cohort's 68.58%.

**Leg 2 does not fire.** No `ships ungated` and no `gate evaluation failed` in
`logs/bot.log` since V14 Step 2's fix.

**Leg 3a fires; Leg 3b is INSUFFICIENT.** 0 A+ in 16 live evaluations against
a requirement of 10 per 10 sessions, with the best score ever recorded 8.7
points short of the cut. Leg 3b has exactly one gate-on session and it is the
one the RTH blackout ran in. Both are read against tiny samples — 3a's value
is that it starts accumulating now rather than being discovered when V36 runs
and finds no cohort to test.

**Three things this does NOT establish, and they matter:**

1. **It does not identify a culprit.** V13 (legacy cut, Aug 2), V14 (gate
   enforce, Aug 5) and the 2.5% floor are all in flight in this window, plus
   two outages and several restarts. The trigger is deliberately a
   *detector*, not an attribution.
2. **n=61 over six days is thin**, and those six days are not a normal six
   days. The pre-registered response to a firing trigger is to roll back — but
   what to roll back is not derivable from this number.
3. **The window predates the stamp**, so its split rests on the timestamp
   heuristic this document rejected for future use. The first
   stamp-authoritative reading is available five trading days after
   2026-08-06.

**Escalated, not acted on.** Rolling back a live config change is a
human-partner decision — the same standing rule that governs `MAX_LOSS_PCT`
(V19 Step 1). Recorded here; no live setting was changed by this task.
