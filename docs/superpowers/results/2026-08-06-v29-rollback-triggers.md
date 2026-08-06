# V29 — monitoring + pre-registered rollback triggers

**Date:** 2026-08-06
**Task:** plan v8 V29 (Phase V5, Rollout)
**Harness:** `scripts/live_cohort_report.py` (V8), run against `/opt/swing-bot/data`
**Status:** Step 1 armed. Step 2 pre-registered here — **two legs armed, one
explicitly unarmed.** The expectancy leg **reads as FIRING on today's data**;
what to do about that is a human-partner decision, not an agent's (see §5).

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

### Leg 3 — survival rate — **UNARMED, and must stay that way until V12 Step 2**
- The plan names "the V12 floor". V12 Step 2 is open and needs a live week of
  `data/scan_telemetry.jsonl` to produce one.
- **No provisional number is registered in its place.** Inventing a floor here
  and calling it pre-registered is precisely the move V6 Step 4 and V52's
  premise-correction exist to forbid. This leg is unarmed and V29 is not
  complete until V12 Step 2 closes it.

## 4. Step 1 — the weekly report

`python scripts/live_cohort_report.py --data /opt/swing-bot/data --baseline
/opt/swing-bot/archive/2026-07-31-pre-v8/trades.json --json <dated>.json`

First run recorded 2026-08-06: **558 records, 557 closed, 1 open**, ALL CLOSED
WR 53.41% / expR −0.192 / total −261.8%. Cohort detail — the tier ladder is
**non-monotonic** (C −0.183, B −0.151, A −0.239) and `VALIDATED` is the only
badge with positive expectancy (+0.781R, n=14, and n=14 proves little).

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
