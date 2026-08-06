# V39 — exercising the promotion mechanism (E40's shadow forward-gate)

**Date:** 2026-08-06
**Task:** plan v8 V39 — *"real, tested code with zero live mileage… Exercise it
deliberately before trusting it."*
**Verdict: do not trust it as written.** Two independent defects, one of which
means it can never fire at all.

---

## 1. Its input can never exist — the gate is structurally dead

`shadow_component_report.py` reads `data/shadow_plans.jsonl` and counts rows
tagged `component` + `variant` with a resolved `fwd_return_10d`.

**Nothing in production writes that file.** `swingbot/core/shadow_log.py`'s
`append()` — the only writer — is called from **tests only**
(`test_shadow_log.py`, `test_wf_engine.py`). A tree scan of `swingbot/` and
`scripts/` finds zero production callers, now pinned by
`test_shadow_log_append_has_no_production_caller`.

The `shadow_log` name that *does* appear in the scan loop
(`commands/scanning.py:296`, `engine.py:1723`) is a **different function** —
`gate/persistence.shadow_log`, which writes `data/gate/shadow.jsonl` for the
gatekeeper. Same name, unrelated file.

**Consequences, in order of how badly they mislead:**

1. **`config.py` documented a file nothing writes.** The `PLAN_ENGINE_V2` help
   text read *"shadow = v2 plans are computed and logged to
   data/shadow_plans.jsonl during scans"*. Selecting `shadow` in the admin
   Settings page produces **no parity evidence at all**, silently. Corrected.
2. **V31 Step 2's diagnosis was incomplete.** It attributed the missing file to
   the deploy having skipped shadow mode and gone straight `off→on`. True, but
   not the reason: even *with* shadow mode selected the file would never have
   been written. That step is therefore not merely unstarted — it cannot be
   started without first wiring the writer.
3. **V27 would have produced nothing.** Closed earlier today as SUPERSEDED and
   never run; it is now clear that running it as written would have yielded an
   empty file and a vacuous comparison.
4. **E40's own gate could never have returned anything but HOLD** — which is
   the exact failure edge-engine-v4's E40 notes say they fixed for the
   *forward-return backfill*, reappearing one layer up in the writer.

## 2. Its promotion bar is a coin flip under the null

The arithmetic is sound. Fed a realistic 140-line log (100 resolved tagged
rows, 20 unresolved, 20 untagged) it excluded the unresolved rows, ignored the
untagged ones, paired the cohorts correctly and printed the human-decision
caveat. **The logic is not the problem.**

The **decision rule** is. `promotable` is `on_mean >= off_mean` at
`n >= MIN_ON_COHORT_N`, with no variance test. Measured against two cohorts
drawn from the *same* distribution, 400 trials each:

| n per cohort | PROMOTE rate under the null |
|---|---|
| 20 | **50.7%** |
| 50 | 48.5% |
| 200 | 48.2% |
| 1000 | **50.5%** |

**A coin flip at every sample size.** More data cannot help: it narrows the two
estimates without narrowing the decision, because the comparison has no notion
of uncertainty. `MIN_ON_COHORT_N` gates sample **size**, not significance, so
it provides no protection either — at n=1000 the rate is still 50%.

This sits far below the standard the rest of the repo holds itself to: G100's
permutation tests, V49's Wilson lower bounds, V54's pre-registered ladders.
A `PROMOTE` from this gate means *"the on-cohort's sample mean landed higher"*,
which under no effect happens half the time.

## 3. What changed here, and what deliberately did not

**Changed:**
- `config.py` `PLAN_ENGINE_V2` help no longer promises a file nothing writes.
- `shadow_component_report.py` prints the measured false-positive rate
  **beside every PROMOTE verdict**, at the moment a human reads it, rather
  than leaving it in a source comment.
- Two tests pin both findings (`tests/test_shadow_log.py`).

**Not changed, deliberately:**
- **The writer was not wired.** That is a behaviour change to a mode nobody
  runs, and E40's cohort tagging additionally needs the scan double-evaluation
  that edge-engine-v4 recorded as resolved-by-emptiness ("the fold-passing list
  is empty, so there's nothing left to build"). Wiring it without a component
  to shadow would build plumbing for no traffic.
- **The promotion bar was not tightened.** `MIN_ON_COHORT_N` and the `>=` are
  a *pre-registered* bar; replacing them with a significance test is a new
  pre-registration, not an edit. Recorded for the human partner.

## 4. V39's question, answered

> Any component v8 proposes adopting is the first thing this mechanism will
> ever see. Exercise it deliberately before trusting it.

Exercised. It cannot see anything (§1), and if it could, its verdict would
carry no evidential weight (§2). **v8 proposes adopting nothing** — V17, V52,
V53 and V54 all ended with empty adopted sets — so nothing is blocked by this
today. But had a component been adopted, this mechanism would have waved it
through on a coin flip, after a shadow window that silently logged nothing.
