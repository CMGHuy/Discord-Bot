# v105 — PENDING daily range continuation with directional pressure

**Version:** ui 1.21.0 · bot 1.10.3 (at writing)
**Bump:** none until a source ships; bot minor if PENDING range alerts ship
**Edge:** expectancy

## Goal and decision record

Find repeatable LONG and SHORT swing setups before a daily range breaks, and
issue an actionable PENDING plan while the stop-market entry can still be
placed. A screenshot is a hypothesis source, not evidence of profit. Rank
work by expected R per unit of risk first and win rate second; the user also
cares about same-day failed breakouts and alerts that arrive after the entry.

Decisions from the 2026-09-25 conversation:

| Topic | Decision |
|---|---|
| First setup | Daily range continuation: LONG after uptrend, SHORT after downtrend |
| Search | Current watchlist for live alerts; full cached universe and all ten horizons for measurement |
| Alert | Existing PENDING plan before break, when live price is near the trigger |
| Broker workflow | Resting stop-market entry, working overnight for up to five trading sessions |
| Stop and target | Beyond a confirmed swing inside the range; existing structural target required |
| Expiry | Cancel unfilled plan after its fifth eligible session; issue again only for a new range |
| Same-sector candidates | Present the strongest measured plan and alternatives as one correlated idea |
| First feature | Directional pressure before the break; hold the exit model fixed |
| Failure diagnostic | Entry trigger touched, then same day's close back inside the range |
| Context only | Weekly Stage 3, relative strength, squeeze, volume profile, fundamentals |

The TrendSpider examples motivating this are MU/AMD/HOOD breakouts, the GS/MS/JPM
group breakdown, and the SNDK horizontal resistance. MSFT's five-minute ORB,
GOOG's long-term investing rule, and SOFI's monthly cup use different time
frames and are outside this test. The bank group is one sector event, not three
independent pieces of evidence.

## Boundary with active and closed work

- v104 B1 tests a SHORT **after** a failed upside breakout; B2 tests a SHORT
  **after** a high-volume downside break. This spec tests a plan available
  **before** either price break. Do not reuse v104's holdout, claim its B1/B2
  effect, or create another bank-reversal validation shot. Report overlap by
  ticker/date and compare entry timing descriptively when v104 results exist.
- v88/v90 armed confluence entries already closed. This is a distinct source:
  a bounded multi-day range, a fixed boundary stop entry, one plan per range,
  and a pre-break pressure feature. Do not re-run those grids or call the same
  repeated-arm rule a new strategy.
- v69 double-pattern and its volume filter closed on sparse pivot geometry.
  A rolling horizontal range with an advance PENDING order is a different
  geometry and workflow. Do not remeasure the old double-pattern rule.
- The BE/ONDS bullish reversal after a decline is a later, separate hypothesis.
  Weekly context remains recorded, not a filter. No strategy claim is made
  for either here.
- v100's standard arm producer is the preferred measuring interface. If it is
  unfinished when this plan executes, use a separately stamped arm producer
  through the same acceptance contract, record the reason, and do not bypass
  reachability or sample-width checks. v104 structural-stop/sizing work may
  change the baseline; freeze the exact code and sizing model for both arms.

## Strategy contract

### Clock and source

At decision time on session `t`, range geometry, trend, pressure, swing stop,
ATR and structural targets may read only daily bars completed through `t-1`.
The live quote on `t` is used only for proximity and whether a trigger has
already crossed. A partial daily bar never edits the range. Replay builds the
same plan from a truncated frame and examines bars `t..t+4` for fill/expiry.

Keep this a new source ID and one shared pure candidate function consumed by
live scan and replay. Do not change the semantics of existing confluence
`stop_entry` plans, whose current trigger is their scenario/current entry.

### Range and direction

The baseline is a horizontal range over `N` completed sessions, with `N` in
the predeclared TRAIN set `{10, 15, 20}`. Its upper/lower bounds are the
maximum high and minimum low in that window. Require at least two separated
visits (at least two sessions apart) to the trigger-side boundary within
`0.25 × ATR(14)`, width between `2 × ATR` and `8 × ATR`, and no completed close
outside the boundary before issuance. These constants are feasibility rules,
not axes to loosen after seeing a result. ATR uses completed bars only.

LONG needs the 30-session SMA rising over its previous five completed bars
and the pre-range close above that SMA; SHORT is mirrored. The trend must
exist before the range, so price action in the range cannot create its own
trend label. Missing warm-up bars means no candidate. One ticker can have at
most one live PENDING range plan; no simultaneous opposite orders.

The LONG trigger is upper bound + `0.10 × ATR`; SHORT is lower bound - the
same buffer, rounded outward to the tradable tick. The order is stop-market.
The plan is eligible for alert only while a fresh live price remains inside
the range and within `d × ATR` of the trigger, for TRAIN-selected
`d ∈ {0.25, 0.50, 0.75}`. Measure candidate density and alerts missed before
selecting `d`; a larger `d` widens timely lead but may increase stale plans.
Select one `N,d` pair on TRAIN before any holdout run.

The only first discriminator is **pre-break directional pressure**: in the
latest three completed bars, at least two closes are in the direction-side
quarter of the fixed range, and the latest two completed lows rise for LONG
(highs fall for SHORT). Compare otherwise identical baseline range plans with
pressure off versus on. Pressure may reject trades; the wider range-source
candidate search is the paired widening. Do not add volume, squeeze, weekly
stage, relative strength or volume-profile filters to rescue a weak result.

### Plan arithmetic and lifecycle

Initial LONG stop is beyond the latest confirmed three-bar pivot low inside
the range; SHORT uses the pivot high. A pivot is confirmed only when its
right-hand comparison bar has completed by `t-1`. Add a `0.10 × ATR` cushion
outward; use the current risk ceiling and dollar-risk sizing model on both
arms. If no confirmed internal pivot, the stop exceeds the applicable risk
ceiling, a gap fill would violate the ceiling, or structural TP1 cannot clear
the current 1.5R–2.5R band, do not issue a plan. A real target comes from the
existing structural-target selector, with no projected fallback.

Freeze stop, target and exit rules before comparing pressure. Trigger touch
fills at the worse of trigger and session open in daily replay. A gap through
the stop-market trigger may fill far beyond its advertised price; show the
observed fill and any risk-cap cancellation explicitly. The paper manager
cannot cancel a user's broker order: every invalidation, fill, expiry or
manual stop change must produce a reliable, actionable notification, and
the UI must show the original trigger, current plan state and timestamp.
The live quote path must reject stale cached prices.

Expiry gives the order five full eligible trading sessions. At expiry, publish
the cancellation and suppress rearming from overlapping rolling windows. A
new range requires a window whose first bar is after the prior plan's
creation session. This conservative identity rule is fixed for the first
measurement, not tuned on the outcome.

### Correlation and presentation

Candidates in the same sector on the same session form one cluster. The
highest TRAIN-calibrated expected R among plans that independently clear all
rules is primary; list remaining tickers as alternatives with their own
trigger, stop and expiry. If no defensible calibrated ranking is available,
use a deterministic ticker order and label the group unranked. Never sum
same-sector plans as independent evidence, and never imply that one broker
order cancels the others automatically.

## Evidence and acceptance

### Frozen comparison

First measure the range source's feasibility, then compare pressure-off and
pressure-on on the exact same code, target and exit model. Keep LONG and SHORT
arms separate, including sample counts and outcomes. The headline result is
paired ΔExpR, with Δwin rate, planned RR, mean winning R, alert-volume change
and removed-population outcomes beside it. Use the repo's six-clause v72
feature gate and its MDE → TRAIN plateau → walk-forward sequence where
applicable. A source/badge claim also needs the distinct strategy-badge gate.
Only a passing direction ships; do not hide a losing SHORT arm in a LONG pool.

Selection uses TRAIN only. The already-used 2024–25 validation window and
v104's 2026 holdout are unavailable for a new selection choice. Pre-register
a fresh, untouched **prospective** holdout beginning with the first complete
session after the holdout pre-registration is committed. Freeze its end,
universe, code hash and one-shot decision rule before examining it. If the holdout is
too short or underpowered, keep the shot unspent and remain shadow-only. No
backtest or live deployment is authorized by this document alone.

Daily OHLC can count a trigger touched and same-day close back inside the
range. It cannot reliably order trigger, stop and target touches within that
day. Report that same-day close-back rate as a diagnostic, not an entry-day
loss estimate. Existing next-bar-only exit replay must not be presented as
evidence that entry-day stops are rare. Capture timestamped prospective
quote/order-state shadow events for order lead time, gaps, missed poll spikes,
same-day stopouts, cancellations and alert delivery. Record source data age.

Primary practical checks: fraction of PENDING notices sent before a crossed
trigger, median and lower-tail lead minutes, share filled through a gap,
share of trigger-cross days closing back inside the frozen range, and alert
delivery/cancellation parity. Do not claim a profitable strategy from chart
examples or a small TRAIN win-rate increase.

## Stop conditions and dependencies

- Stage −1 must prove that the live scan and replay can reach the new source
  and that the full cached universe across all ten horizons has enough
  candidate and filled trades for a meaningful MDE. If not, record an
  underpowered finding without changing the predeclared geometry to force N.
- Reconcile v104's stop ceiling, sizing and shared plan arithmetic before
  scoring; both arms must use the same version. Never compare against a
  pre-v104 pooled figure copied from a document.
- Never run the one-shot holdout merely to make a report. Its prospective
  sample and analysis plan must be frozen and sufficiently powered first.
- Live enablement requires the evidence gate, no-lookahead test, notification
  and order-lifecycle parity, and an explicit release decision. Until then
  shadow candidates are visible as research, not trade alerts.

## Parallelisation

The first work is sequential: source contract → live/replay parity → frozen
arms → TRAIN feasibility/selection → forward holdout. Shadow instrumentation
can follow source parity while TRAIN measurement runs, but it cannot justify
alert enablement by itself. v104 and v100 are external dependencies; this
plan should inspect their landed code at execution rather than assume they
have finished.
