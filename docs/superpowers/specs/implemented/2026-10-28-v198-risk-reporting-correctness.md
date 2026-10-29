# Risk reporting correctness

**Version:** ui 1.36.1 · bot 2.15.4
**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-engineer
**Plan:** [Implementation plan](../../plans/implemented/2026-10-28-v198-risk-reporting-correctness_0-index.md)

## Goal

Make the Risk API report what is known, preserve position direction in portfolio return calculations and measure drawdown from the initial baseline in chronological close order. This addresses three independently reproduced code defects. Reporting changes must not alter scan acceptance, sizing, stops, throttle decisions or kill-switch enforcement.

## Evidence

`swingbot/core/edge/portfolio_state.py:collect_portfolio_state` replaces failed trade reads with an empty list and failed throttle/kill reads with reassuring values. An isolated dependency-failure probe returned open_heat=0, throttle_mult=1, paused=False and kill.on=False.

`swingbot/admin/api_v1/risk.py:_risk_metrics_and_correlation` constructs positive weights with abs(entry*shares), losing direction. With synthetic underlying returns, a short-only book reports beta approximately +1 instead of -1. This is a numerical example, not a live-book statistic.

`swingbot/core/analytics/risk_metrics.py:max_drawdown_r` starts its peak at the first cumulative outcome. Synthetic money outcomes [-100] report zero; [-100,-50] report 50 rather than 150. Risk also passes R outcomes in TradeLog.get_trades default opening-time order, not close-time order. Synthetic permutations show a reported drawdown of 100 versus 200 for the same outcomes when loss adjacency changes.

## Prerequisites and boundaries

Implement after v194 merges so its account-currency display seam, max-drawdown money field and sector-unavailable presentation are retained rather than reimplemented. Re-read current main and v194 deliverables before writing the implementation plan. v195 is a concurrent UI redesign: integrate status fields into its final Risk page instead of duplicating shell or panel architecture.

No production access, backtest, validation-budget use or live-book performance claim is necessary for these corrections. Audit callers of the shared helper before changing it; any backtest consumer requires backtest-gate before changing that consumer's behavior. Account-balance FX conversion is a separately documented display-only exclusion in v194 and is outside this scope.

## Unknown-data contract

Represent each independently collected Risk domain with an availability state: ok, unavailable or partial; include checked_at UTC and a sanitized reason code. Cache status with the value, never cache a fallback as a successful observation. Domains cover open positions/heat, sector mapping, clusters, throttle and killswitch. Successful empty reads remain ok with zero exposure. A failed read is unavailable, never a successfully empty book.

On failed open-position reads, positions and heat are unknown and render an unavailable state. A failed account-configuration read or a nonfinite/nonpositive balance denominator also makes heat unavailable, even if the heat helper would return zero. On failed heat calculation, retain valid position identities but mark heat unavailable. Sector-map gaps remain partial with v194 unmapped_count; a failed sector calculation is unavailable. Correlation data failure remains independent of trade-derived performance metrics. Explicitly represent incomplete coverage in the API, not only in logs.

Risk-owned projection fields become nullable where required: heat.open_pct/utilisation_pct, throttle.multiplier/paused, killswitch.on and unavailable positions. Add domain availability metadata. Update TypeScript models, stores, templates and fixtures together. UI displays unavailable rather than zero/off; it must not claim the account has no exposure. Preserve known positions when only analytics fails.

Killswitch mutation remains strict boolean input. Separate the last observed state from the current state: an optional last_known block carries its timestamp and is visibly stale, never serialized as current. The shell's dedicated killswitch endpoint must use the same unknown contract; preserve the toggle's ability to attempt an authenticated explicit action even when reading state fails. An unknown response must never issue an off mutation or imply scanning resumed. Other consumers of collect_portfolio_state, including Discord portfolio output, must handle domain status without crashing or changing execution policy. Do not globally change heat.open_heat([]) semantics.

## Signed portfolio returns

Compute each position's nonnegative notional in one common account currency at a single valuation date using v194's FX provider. Use its recorded entry*shares as the notional basis to preserve the existing Risk metric's basis; the FX rate date is the valuation date. Numerator aggregates bullish notionals positively and bearish notionals negatively by ticker. Denominator is total gross notional before netting. Weights therefore sum by signed exposure, not by renormalizing net exposure to one.

Use actual direction vocabulary from stored records. An unknown direction or invalid/nonfinite entry/share/FX value makes portfolio-distribution metrics unavailable with an explicit coverage reason; never guess long, silently omit exposure, or substitute FX 1.0. Require complete bar coverage and retain the existing overlapping-date policy. An empty book yields existing null distribution metrics. A perfectly offsetting book can have zero return variance; existing no-variance guards yield null rather than fabricated risk estimates.

Correlation matrix remains the underlying-assets correlation, explicitly labelled as such; do not flip its signs merely because positions are short. Label return-derived metrics as a quote-return model weighted in account currency; historical FX returns are not modeled. This fixes weight comparability and position direction without claiming a full cross-currency return model. Preserve the configured benchmark label and its existing basis.

## Drawdown definition

For finite ordered outcomes x, calculate cumulative outcomes starting with an explicit zero point; drawdown is the greatest running peak minus cumulative outcome, a nonnegative magnitude. Empty input remains None. All winners return zero; an initial loss is fully counted. Reject nonfinite outcomes to unavailable at the read-model boundary rather than generating NaN JSON or dropping individual bad rows silently.

For Risk's all-closed R walk, order valid closed records by parsed closed_at ascending with trade ID as a stable tie-breaker, then compute outcomes. Records without a valid close timestamp or computable finite R outcome are excluded and counted in a dedicated excluded_count field, with separate invalid_date_count and invalid_outcome_count reason counts. Apply non-overlapping reasons in date-then-outcome order so totals reconcile; missing fields and zero-risk outcomes are invalid_outcome, never zero-filled. Money drawdown retains v194's per-exit-date conversion and fx_missing_count, sorts by the same close chronology, and separately counts invalid dates. Do not reinterpret R as currency, percent of account or annualized performance. Preserve each metric's population label. Do not reorder the general-purpose r_multiples helper for unrelated consumers.

Keep the metric module pure. Introduce a small Risk read-model helper for chronological selection, weights/coverage and status projection when necessary; do not add more branches to the large existing endpoint. Every changed/new function stays below cyclomatic complexity 15.

## Success

- Simulated read and calculation failures produce explicit unknown/partial states; a genuinely empty book remains known-empty.
- A fresh failed killswitch read never renders off, including after a cached successful read; mutation tests prove no implicit release.
- Long-only regression, short-only negative beta, mixed long/short netting, same-ticker hedges, cross-currency notional weights, missing FX and invalid direction have isolated synthetic tests.
- Baseline drawdown cases include initial/all losses, all wins, recovery, empty input and nonfinite values. Closing-order tests use overlapping holding periods and shuffled input; invalid dates and equal-time ties are covered.
- Market-data failure preserves trade-derived metrics; malformed trade data cannot turn into valid zero risk or blank unrelated controls.
- UI unavailable/partial/stale states are checked at phone, tablet and desktop widths and with screen-reader labels. Run the mandatory layout audit before merging.
- Per-task backend/frontend tests run narrowly. Before database tests run replicate-prod-db into shared swing-db. One final task runs the full backend suite and full frontend suite once. New test directories join exactly one suite. Documentation authoring does not run those suites or touch production.

## Parallelisation

Unknown-state projection and signed-weight corrections share risk.py and must be sequential. Pure drawdown helper tests can be developed independently only with disjoint files and no shared-contract dependency, but default execution remains serial. UI consumers follow the finalized API contract; final verification follows all work.

## Handoff

Partner approved this written design for implementation planning on 2026-10-28, after panel findings were resolved. The associated 10-task plan now has all three parts written and full plan lint passes. The final independent authoring check covered both backend packages: 64 Python examples and 18 TypeScript examples parse in their intended contexts; all checked proposed Python functions/methods/closures have complexity below 15. Implementation is unstarted. V198-6 owns the sole full backend/frontend verification and three-width layout audit after implementation. No runtime test or production result is claimed by these document checks.

## Panel review

- Controller review: the Discord portfolio consumer also gains truthful unknown states, so include bot patch alongside ui patch.

- quant-engineer: failed account reads and invalid balance can yield false zero heat without a heat exception — applied: mark the heat domain unavailable for these dependencies.
- quant-engineer: uncomputable R outcomes need explicit population exclusions — applied: excluded_count and mutually exclusive date/outcome reason counts.
- No BLOCKING findings.
