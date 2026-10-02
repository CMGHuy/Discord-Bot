# v118 — SHORT candidate universe for existing swing horizons

**Version:** ui 1.21.0 · bot 1.12.1 (at writing)
**Bump:** bot patch (only if qualified alerts ship)
**Edge:** volume

## Decision and purpose

The partner wants more actionable share-SHORT alerts when the broad market is
weak and when an individual stock or sector is weak inside a stronger market.
The ten live swing horizons and their current confluence, reward, stop,
confidence, relative-strength, open-trade and deduplication rules remain the
baseline. This work expands where qualifying bearish setups can be found; it
does not promise a balanced LONG/SHORT count or lower the admission bar.

The partner will short shares directly. The bot cannot verify stock borrow at
the broker. Every new-lane alert must say **CHECK BORROW AVAILABILITY** and show
the completed-bar date used for selection. A manual broker check is part of
executing the alert, not a claimed machine-verified property.

This spec covers one capability: an optional, separately scored SHORT
candidate lane feeding the existing confluence scan on the existing horizons.
The separate 3–10-session strategy is v119 and has its own entry, exit and
measurement record. v118's candidate context may be consumed by v119 later,
but v118's result cannot validate v119's signal.

## Current behavior and hypothesis

- `scan_run.py` loads the watchlist and may append one named universe through
  `SCAN_UNIVERSE`. That option expands **both** directions. The watchlist is
  always included.
- The confluence path already creates bearish scenarios. It scores the nearest
  support target and resistance stop, then applies shared geometry, quality,
  relative-strength and open-trade rules. The enabled bearish RS gate uses a
  laggard percentile; the corresponding bullish threshold is inactive.
- Scan-wide breadth and RS percentiles use every fetched frame. Appending
  symbols and discarding their LONG alerts later would still change scores for
  existing LONGs. A separate reference context is required.
- Existing scan funnel counters aggregate directions. No measured stage count
  identifies whether the current shortage begins at candidate selection,
  levels, plan geometry, quality, RS or an already-open LONG.
- The current named S&P 500 file is a manually refreshed live list. Historical
  testing must use point-in-time membership rather than today's constituents
  on earlier bars.
- Historical isolated-weakness tests also require sector classification as
  known on each signal date. Today's `sp500.json` sector field cannot be
  projected backward; an unavailable dated mapping excludes that candidate
  with a count.

**Hypothesis:** a liquid, point-in-time S&P 500 candidate pool, restricted to
weak stocks and bearish scenarios, adds qualified SHORT opportunities during
the two specified weakness conditions while preserving the per-trade edge and
every existing LONG result. This is a hypothesis to measure, not a measured
cause of today's LONG-heavy alerts.

## Candidate and reference contract

The base lane is today's watchlist plus the configured `SCAN_UNIVERSE`. It
retains its ticker set, breadth reference, RS percentile reference, strategy
pass inputs and LONG/SHORT outputs byte-for-byte when the new flag is off.

The optional extra lane has a distinct set of candidate symbols and a distinct
reference panel. Its input membership is S&P 500 constituents as of the signal
date, excluding symbols already in the base lane. A ticker in both lanes runs
only through the base lane. The extra lane can yield **bearish confluence
scenarios only**; filtering occurs after scenario construction, without
repurposing the existing `block_bullish` argument (which means the dead-cat
bounce veto). It does not feed the strategy-sourced pass in this spec.

Each candidate carries at least `ticker`, `source=short_universe`, `mode`,
`decision_bar_date`, `membership_asof`, and the reference-panel identity.
These are immutable issuance/audit facts, not a new persisted trading-store
schema. A candidate is in exactly one mode:

1. **Broad weakness.** The existing SPY trend result is bearish on the same
   completed bar date. The candidate is in the laggard part of the separate
   reference panel; the existing RS gate still makes the final decision.
2. **Isolated weakness.** SPY trend is not bearish. The stock's trailing
   63-session return is below its mapped sector ETF's return on aligned,
   completed bars; it must still clear the existing bearish RS gate.

The stock-versus-sector comparison is a candidate selector, not an additional
independent confirmation point. Existing stock RS and sector RS both derive
from trailing returns versus SPY and must not be double-counted as separate
evidence. The same `get_market_regime` result supplies the SPY trend used by
the current scan; v118 does not add another market-regime model or enable
`REGIME_GATES_ENABLED`.

Selection, breadth and RS calculations use one common completed exchange date
for ticker, SPY and sector ETF. No forming daily bar enters this lane. A
missing, stale or mismatched frame skips that extra candidate with an explicit
reason. Missing SPY skips the whole extra lane; missing sector mapping or ETF
skips only the isolated-weakness candidate. The base lane continues normally.
The live S&P membership snapshot must carry an as-of/freshness date; a stale or
missing snapshot disables extra candidates and is visible in scan telemetry.

The current liquidity and data-quality checks remain. Additional symbols are
fetched in bounded batches with cache prefetch and a scan-time budget so the
watchlist's cadence does not depend on hundreds of cold network fetches. The
budget never changes base-lane ordering or discards a base symbol.

## Alert and observability contract

For each direction, mode, and source, record counts at: candidate membership,
usable aligned bars, scenario built, geometry accepted, confidence accepted,
RS accepted, plan built, existing-trade/reversal decision, deduplication and
send. Rejections use stable reason names. Counts are telemetry, not a new
quality score. Include base-lane counts in the same report so the additional
SHORTs can be distinguished from a market-wide rise in bearish setups.

A new-lane alert identifies broad or isolated weakness, the decision-bar date,
the planned entry/stop/target and expiry, and **CHECK BORROW AVAILABILITY**.
Discord and every simple/email/push mirror must agree on the trade numbers and
borrow-check text. A stale selection date is shown as stale, never silently
presented as current. Pending-plan cancellation and reversal messages retain
their existing semantics; a new SHORT must not silently displace an open LONG.

## Measurement and release rule

Pre-register the membership source/date, reference panel, selector definitions,
two mode cohorts, time windows, costs, deduplication and success rule before
looking at outcome data. A scan-level replay must actually execute the
candidate selector, bearish scenario construction and all downstream gates;
the strategy-only backtest cannot measure this lane. Use the standard
`measure_arms.py`/`validate_component.py` route if Stage −1 proves it can
observe the additive arm. If that instrument cannot represent the additive
population or its mode split, stop at reachability and write a separate,
pre-registered instrument/acceptance amendment before any selection run.

The baseline is the same scan and same time-indexed universe with the extra
lane disabled. Report every added alert and its result separately from base
alerts. The primary work-ranking objective is pooled expectancy, with win
rate and alert volume reported alongside. The feature's default-on decision
uses all applicable clauses of the current component gate and the frozen
pre-registration; a larger SHORT count alone is not a pass. Report sensitivity
to plausible borrow fees as a break-even fee rather than claiming historical
borrow availability that this repo does not possess.

Run reachability, MDE, TRAIN plateau and fold walk-forward before the single
VALIDATION shot. A closed pre-registration is never rerun to rescue a result.
The broad and isolated mode results are shown separately; one good mode may
not hide a losing other mode. Preserve the existing bearish RS gate and LONG
scoring unless a separate, later hypothesis measures a change to them.

The implementation is inert by default. After a passing measurement, enable
only the admitted mode(s) behind an explicit config flag, shadow/soak them,
and verify live alert numbers and timing before any production change. This
spec does not authorize production SSH, deploy or config changes.

## Boundaries and failure cases

- No broker connection, locate claim, short-sale execution or share order is
  added. The bot remains a paper-trade alert system.
- No new SHORT signal, stop clamp, target rule, quality threshold, RS threshold,
  or 1w horizon is introduced here.
- Missing point-in-time membership, sector mapping, benchmark bars, earnings
  data, or borrow data never passes through a fabricated value. Earnings and
  borrow remain disclosed rather than newly scored by this volume feature.
- A stale/unavailable extra-universe feed affects only extra candidates; the
  base scan still runs and its score inputs remain unchanged.
- If expanded symbols overwhelm the fetch/cache budget, reduce the batch or
  fail closed for extra symbols. Do not silently delay the watchlist scan.
- If the measured additional cohort has no acceptable edge, keep the lane
  off. Telemetry may remain if it does not change behavior.

## Parallelisation

The contract and reference split precede candidate selection and replay.
Tests for immutable base-lane scoring and point-in-time membership can be
written in parallel if they own disjoint files. Scan orchestration, candidate
selection, telemetry and live alert rendering are sequential because they
share the candidate context and `scan_run.py`/`analyze.py` call chain. The
measurement stages run serially in the fixed funnel. No parallel validation
shots are permitted.
