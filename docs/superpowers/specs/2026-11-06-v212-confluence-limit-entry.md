# v212 — Confluence limit entry at the level (pre-registration)

**Version:** ui 1.39.1 · bot 2.16.5
**Bump:** bot patch (ships inert behind a flag at 0; no observable difference until a pass and a partner decision)
**Edge:** expectancy — a better fill on the same signal: a confluence long buys at its support instead of at the market. The stop sits under the level and the target is unchanged, so R per winner rises and noise stop-outs fall. Prediction: ExpR up, at the cost of fewer fills.
**Screen:** exempt (post-signal)
**Panel:** quant-researcher, veteran-trader, risk-manager

## Why

On 2026-11-06 the partner asked what the live book's losses since September
teach. The export (`scripts/ops/export_book_rows.sh rows`, read-only, 392
closed trades opened 2026-09-01..2026-11-06; live book, in-sample,
exploratory) showed losses that are fast and noise-shaped:

- **Fast.** 200 losses. The median loss lives 2.2 hours, and 88% are
  stopped within one day.
- **Tight.** The stop is pinned at about 1.77% of price
  (`MIN_STOP_DISTANCE_PCT` 1.75 plus the v115 clamp to the 2% cap), while
  median ATR14 is about 4.7% of price. The stop sits 0.3–0.4 ATR away.
- **Right idea, wrong stop.** In 57% of stopped losses, price reached TP1
  within 10 sessions after the stop-out (daily bars, yfinance).

The reason is in the geometry. `levels.build_scenarios`
(`swingbot/core/market/levels.py`) builds a long at `entry = current_price`,
with the nearest support as its stop. When that support is more than 2%
below, the v115 clamp
(`builders._clamp_stop_to_hard_cap`) moves the stop to 1.75% under the
**market price**. That leaves it in empty air above the support the trade
leans on.

Moving the stop out is closed:

- **v139:** structural stop with dollar sizing, NO-LIFT.
- **v191:** ATR band, UNDERPOWERED. Reopening requires "a stop rule other
  than an ATR14 floor".

v131 (a resting limit on the **Fibonacci strategy**) is also closed, NO-LIFT.
This spec moves the **entry** instead, on **confluence** plans, which are
about 90% of the live book. That is a mechanism no closed row covers. The
partner chose it over a daily-close stop and over skipping the first hours
of the session.

## The screen exemption

The rule is decided entirely by price action **between the bot's alert and
its fill**, on the bot's own plans: whether price returns to the level
within N bars. That is the v192 post-signal exemption
(`document-conventions.md` § The header block). The Stage −2 screen races
events with no bot signal beneath them, so it cannot measure a fill rule on
the bot's plans. Per that exemption, the spec must clear **Stage −1
reachability on the bot's own replay** before any shot. The partner approved
this framing on 2026-11-06. The panel should challenge it if the rule reads
as a filter on anything known at the alert.

## The rule (frozen here)

New knob: `CONFLUENCE_LIMIT_ENTRY_BARS` (int, default 0 = off, today's
behaviour byte-identical).

When the knob is N > 0, a confluence plan whose `entry_type` today would be
`market` changes as follows. A `stop_entry` breakout plan is untouched.

1. **Entry.** The plan becomes `entry_type = "limit"`. The limit sits at the
   **level the trade leans on**: the scenario's pre-clamp `stop_loss`
   (`build_confluence_plan`'s `level`, v129). That is the support for a
   long, or the resistance for a short.
2. **Stop.** The stop uses the next level beyond the limit (`supports[1]`
   for a long, `resistances[1]` for a short, from the plan's level map).
   - If that level lies between `MIN_STOP_DISTANCE_PCT` and 2% from the
     limit, the stop goes there.
   - Otherwise the stop is the limit ∓ 1.75%. That covers no such level, a
     level too close, and a level too far.
   The 2% cap is measured from the limit price.
3. **Targets.** TP1 and TP2 keep today's prices. A plan whose TP1 fails
   `MIN_RISK_REWARD_RATIO` from the limit is dropped (not expected in
   practice: the entry only moves closer to the stop).
4. **Expiry.** The limit rests for N bars, then lapses unfilled. It also
   cancels if TP1 trades before the fill (the move left without us).
5. **Fill.** The existing limit fill model applies (`exit_sim_v2`
   `_limit_entry_v2` in replay, `plan_manager` limit handling (v187 D3)
   live). An open through the limit fills at the open.
6. **Direction.** Both directions are covered, longs and shorts mirrored. Results
   are reported per direction. The partner's rule that short work never
   downgrades longs holds trivially here: a long-only regression would fail
   the long clauses.

Grid (pre-registered, three cells): N ∈ {1, 3, 5}.

## Pass rule

The partner set the pass rule on 2026-11-06. The cells run the existing
funnel unchanged (`backtest-methodology.md` § Funnel stages) through
`scripts/backtest/measure_arms.py` (the standard arm producer) and
`validate_component.py`:

- **Stage −1:** reachability. A cell with zero changed outcomes is refused,
  budget intact.
- **Stage 0:** the MDE gate.
- **Stage 1:** selection on fold-train, with a plateau across N.
- **Stage 2:** walk-forward.
- **Stage 3:** one validation shot.

On top of the funnel's own clauses, the partner's three profit clauses apply
at Stage 1 and Stage 3, each cell scored against the reference arm
(today's market entry, same plans):

1. **ExpR** beats the reference.
2. **Fills:** the filled trade count is ≥ 50% of the reference count.
3. **Win rate** is no more than 2 pp below the reference.

There is no total-R clause. The partner rejected it for v131, and the same
reasoning holds here.

## Goals

- **G1.** Build the knob in the confluence constructor
  (`builders.build_confluence_plan` / `_plan_geometry`). Replay, live and
  the measurement read one rule. Knob 0 is byte-identical to today, pinned
  by a witness test over a fixture replay.
- **G2.** Register the knob in the reachability registry and the arm
  producer. Write a pre-registration record before any compute
  (`docs/superpowers/results/<date>-v212-preregistration.md`), freezing the
  rule, the grid, the clauses and the windows above.
- **G3.** Run Stages −1..3 through `backtest-runner`, chunked and
  checkpointed per unit. Record the result and one ledger row.
- **G4. Live path, inert.** A limit plan's Discord alert and the admin plan
  view say "Buy limit at X, valid N sessions" (sell for shorts). Expiry and
  TP1-before-fill cancellation reuse the existing pending-plan lifecycle.
  Nothing is switched on: `.env.example` documents the knob at 0.

## Non-goals

- No change to stop-distance floors, the 2% cap or the clamp for market
  plans.
- No strategy-source plans (v131 closed the Fibonacci form). No breakout
  `stop_entry` plans.
- No size change: sizing stays fixed dollar risk on the stop distance from
  the limit.
- No turning it on. A Stage 3 pass is reported to the partner, who decides.

## Anti-goals

- **Re-running a closed stop row.** Nothing here widens the stop in ATR
  terms or keeps a structural stop beyond 2%. If the panel finds the rule
  equivalent to v139 or v191, stop and redesign.
- **Shopping N after Stage 1.** If no cell passes, the rule is closed. A
  different limit placement, such as level ± offset or an ATR-based limit,
  is a new mechanism that needs its own reason.

## Constraints

- Every function stays under complexity 15. `build_confluence_plan` is
  already large, so new geometry goes in a named helper.
- No lookahead: the limit level and the stop level come only from bars
  ≤ t (the levels the scenario was built from).
- Tests ship with the work:
  - the geometry (stop at the structural level, at the 1.75% fallback, a
    level too close, a level too far, shorts mirrored);
  - expiry and TP1-before-fill cancellation;
  - knob 0 byte-identical;
  - alert and admin text;
  - empty cases (no `supports[1]`).

## Left to the builder

- Exact placement of the helper, and how the level map reaches it on the
  replay path.
- The results-doc layout. The per-direction table and the fill-rate table
  are required.

## What follows

- **Stage 3 pass:** the partner decides whether to set the knob live (via
  `mirror-prod`).
- **No pass:** closed row in `backtest-methodology.md`. The next stop-side
  idea from this review, a daily-close stop, stays available as a separate
  mechanism.
