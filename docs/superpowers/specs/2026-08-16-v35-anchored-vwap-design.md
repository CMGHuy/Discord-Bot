# v35 — Anchored VWAP levels

Version: ui 1.7.0 · bot 1.1.4
Bump: bot patch — a level source gains anchors and becomes visible by name in
alerts. More confirming methods means marginally different confidence, but no
gate changes and no alert population is removed by design. `ui` none.

## The problem, stated once

Anchored VWAP **already exists and is already contributing levels.**
`edge/factors.py::anchored_vwap(df, anchor_idx)` and `avwap_anchors()` are
called from `swingbot/core/market/levels.py:346`, which folds their values into
the candidate level pool, and from `scanning/engine.py:216` for decision
context.

What is unknown — and Task 1 of the plan is to establish it — is **which anchors
`avwap_anchors()` actually picks**, whether they are the meaningful ones, and
whether the resulting levels are visible to the user as a named method or
silently merged into a cluster label.

This is a spec about auditing and extending working code, not building a
feature. The scope may shrink substantially after Task 1, and that is a
legitimate outcome.

## Goal

Anchors chosen deliberately, contributing on both target and stop side, and
surfaced by name in alerts the way "Bollinger Squeeze Breakout" already is.

## Design

### Anchors

Two anchor families for v1:

1. **Last significant swing pivot** — reuses the zigzag pivot detection already
   computed for the existing level methods. This is the classic "anchor from the
   last major high/low" that makes AVWAP meaningful rather than an arbitrary
   rolling window.
2. **52-week high / low** — trivial from the fetched daily history, and a
   genuinely meaningful reference for the longer horizons where a rolling VWAP
   window is essentially arbitrary.

**Earnings-gap anchoring is deferred.** It needs precise alignment with
`events.py`'s earnings-date logic, and getting the anchor bar wrong produces a
confidently-drawn wrong level. It becomes its own follow-up once the two cheap
anchors are proven.

Anchor selection must respect the **NO-LOOKAHEAD rule**
(`docs/claude/architecture.md`): an anchor is only valid if it is in the past
relative to the bar being evaluated. This is the single most likely way this
spec silently inflates backtest results.

### Both sides

AVWAP levels are treated identically to the existing eight methods: they can
confirm a **target** above or a **stop/invalidation** level below. Stop
confluence is already a scored factor, so this needs no new scoring machinery.

### Surfacing

An AVWAP-confirmed level names its anchor in the alert — "Anchored VWAP (52w
high)", not a bare "⚓" marker (`engine.py:216` currently builds
`f"⚓{a}"`, an anchor *index*, which is not a human-readable label). The explain
text mentions it as a confirming method.

This is the visible half of the change and the reason it is worth doing at all:
a level confirmed by a meaningfully-anchored VWAP is a stronger claim than one
confirmed by a rolling window, and today the user cannot tell them apart.

### Confluence-inflation guard

Multiple anchors produce multiple AVWAP lines. If each counted as an
independent confirming method, a cluster could reach Level 5 on **one** method
wearing three hats — precisely what the honesty gate exists to prevent.

**All AVWAP anchors collapse to a single "Anchored VWAP" method** for
method-counting purposes, regardless of how many anchors land in the cluster.
The individual anchors are named in the display text; they do not multiply the
count.

## Validation

New pre-registration, but a lighter one than v33/v34 — this spec adds no gate.
Acceptance: no win-rate regression, and confluence counts do not inflate (a
distribution check on method counts before and after, which is the real risk
here).

Ships **default-OFF** behind a flag for consistency with v32's rollout rule,
even though it removes no alerts.

## What this deliberately does NOT change

- **No gating.** AVWAP contributes levels and confidence, never a veto.
- **No earnings-gap anchor** in v1.
- **The clustering tolerance** (`CLUSTER_TOLERANCE_PCT`) is untouched.
- **Method count cannot be inflated by anchor count.**

## Risks

- **Lookahead in anchor selection** — the highest-severity risk, because it
  makes the backtest look better while making live results worse. Mitigation:
  an explicit no-lookahead test in the plan, not just a code review.
- **Scope may collapse after Task 1.** If `avwap_anchors()` already picks swing
  pivots and 52w extremes, this spec reduces to the surfacing work and the
  inflation guard. That is a fine outcome and should be recorded, not padded.
- **Confluence inflation** — mitigated by the single-method collapse above.

## Parallelisation

- **Sequential: Task 1 (audit what `avwap_anchors()` does today) before
  everything.** The rest of the spec's scope is not known until it completes.
- **Group A (parallel, after Task 1):** anchor selection
  (`swingbot/core/edge/factors.py`) and the display/label work
  (`swingbot/core/scanning/embeds.py` / `swingbot/core/market/explain.py`) —
  disjoint files; the label work consumes only the anchor *name* contract, which
  Task 1 fixes.
- **Sequential:** the confluence-inflation guard in `levels.py` after anchor
  selection, since it counts what that produces.
- **Sequential at the end:** no-lookahead test, then the measurement run.

## Depends on

**v32 must land first** — AVWAP-confirmed levels feed stop/target confluence
factors whose weights v32 establishes.
