# v212 — Confluence limit entry partway to the support (pre-registration)

**Version:** ui 1.39.1 · bot 2.16.5
**Bump:** bot patch (ships inert behind a flag at 0; no observable difference until a pass and a partner decision)
**Edge:** expectancy — on confluence plans whose stop today is clamped into empty air above the support, the long rests a limit partway down towards the support with its stop just under the support. A dip fills at a better price under real structure; a straight runner is missed. Prediction: ExpR up on the filled trades, fewer trades, and noise stop-outs down.
**Screen:** exempt (post-signal)
**Panel:** quant-researcher, veteran-trader, risk-manager

## Why

On 2026-11-06 the partner asked what the live book's losses since September
teach. The numbers are in
`docs/superpowers/results/2026-11-06-loss-review-sep-nov.md`. They are
live-book, in-sample and exploratory.

- **Fast.** The median loss lives 2.2 h, and 88% are stopped within a day.
- **Tight.** The stop sits about 1.77% from price, against a median ATR14
  of about 4.7%.
- **Recovers.** In 57% of stopped losses, price reached TP1 within 10
  sessions after the stop.

The geometry explains it. `levels.build_scenarios`
(`swingbot/core/market/levels.py:750`) builds a long at
`entry = current_price` with the nearest support (`supports[0]`) as its
stop. When that support is more than 2% below, the v115 clamp
(`builders._clamp_stop_to_hard_cap`) moves the stop to market −1.75%. That
is **above the support**, in empty air.

Moving the stop out is closed:

- **v139** (structural stop with dollar sizing): NO-LIFT.
- **v191** (ATR band): UNDERPOWERED.
- **v131** (a resting limit on the Fibonacci strategy): NO-LIFT.

This spec moves the **entry** on **confluence** plans. That is a mechanism
no closed row covers.

**How the placement was chosen.** The first draft put the limit **at** the
support. The panel showed that this limit fills only after today's stop has
already traded, so it never holds one of today's winners. The partner
compared three versions and chose this one on 2026-11-06:

- the limit at the support;
- partway down (chosen);
- today's entry plus a re-entry after a stop-out.

Partway down keeps winners that dip, puts the stop under real structure, and
avoids the re-entry version's doubled risk. The live book also argues
against re-entry: same-day re-entry after a stop-out made +0.027R over 76
trades, against +0.050R for first-of-day trades.

## The screen exemption

Whether the limit fills, expires or cancels is decided purely by price
action between the bot's alert and its fill, on the bot's own plans. That
is the v192 post-signal class (`document-conventions.md` § The header
block). The panel (quant-researcher) read it the same way. The spec must
clear Stage −1 reachability on the bot's own replay before any shot.

Two parts are decided at the alert, not after it:

- **The scope:** clamped plans only.
- **The drop:** a plan is dropped when the stop under the support is
  beyond 2% of the limit.

Those are filters outside the exemption. Their counts are reported per
cell. The spec claims no edge from them, and the reference arm is scored
on the **same in-scope plans**, so neither filter can manufacture a
difference between arms.

## The rule (frozen here)

New knob: `CONFLUENCE_LIMIT_ENTRY_F` (float). The default 0 means off, and
today's behaviour stays byte-identical.

**Scope.** A confluence plan is in scope when all three hold:
- its `entry_type` today would be `market`;
- its `level` (the pre-clamp `scenario.stop_loss`: `supports[0]` for a
  long, `resistances[0]` for a short) lies more than 2% from the market
  price M;
- so today's stop was moved by the clamp (`stop_moved_by` records it).

Breakout `stop_entry` plans and plans whose level is within 2% (their stop
already sits on structure) are untouched.

**For an in-scope long** (shorts mirrored), with S the level:

1. **Limit.** `L = M − f × (M − S)`, rounded to the tick toward M.
2. **Stop.** `S × (1 − 0.0025)`, 0.25% under the support, rounded to the
   tick away from L.
3. **Drop.** If `(L − stop) / L > 2%`, the plan is dropped. It is never
   clamped, so the stop always sits under structure. `MIN_STOP_DISTANCE_PCT`
   does not apply to these plans, because the stop is structural by
   construction. The count of fills with a stop under 1.75% is reported.
4. **Targets.** TP1 and TP2 keep today's prices. A plan whose TP1 fails
   `MIN_RISK_REWARD_RATIO` from L is dropped. That should not happen,
   because the entry only moves away from the target's opposite side. The
   drop count is reported.
5. **Expiry.** 3 bars, frozen. The plan also cancels if TP1 trades before
   the fill.
6. **Fill.** The existing limit fill model: `exit_sim_v2._limit_entry_v2`
   in replay, `plan_manager` limit handling (v187 D3) live. An open through
   L fills at the open.
7. **Sizing.** Fixed dollar risk on `|L − stop|`. The share count follows,
   with no change to the risk-per-trade setting.

Grid (pre-registered, three cells): f ∈ {⅓, ½, ⅔}. **Looks: 3.** The
verdict unit is pooled over both directions. Per-direction results are
disclosed. A pass ships both directions or neither.

Each cell reaches its own slice of support distance: the drop rule admits
`D = (M − S)/M` up to about 1.75% / (1 − f). That is about 2.6% at ⅓, 3.5%
at ½ and 5.25% at ⅔. Each cell's reference arm is that cell's own in-scope
plans. The results doc prints each cell's D range and N.

## Pass rule

The partner's three clauses were set on 2026-11-06, as with v131. All are
point estimates, scored per cell. The comparison is **the arm's filled
trades** against **the reference arm's trades on the same in-scope
plans**: today's market entry and clamped stop.

1. **ExpR:** the arm's ExpR is greater than the reference's.
2. **Fills:** the arm's filled trades number at least 50% of the
   reference's trades, pooled over both directions.
3. **Win rate:** the arm's win rate is no more than 2 pp below the
   reference's.

How these sit inside the funnel (`backtest-methodology.md` § Acceptance
gate, § Funnel stages):

- **Gate family:** `validate_component.py --gate harvest`. Stage 2 uses
  `gate_expectancy_harvest` (`backtest_wf.py:278`). The win-rate gate
  family is not used, because ExpR is the objective.
- **Clause 2 replaces the funnel's volume clause** (`VOLUME_MAX_CUT_PCT`
  25%) for this pre-registration, as v131's own gate did. A limit that
  forgoes runners cannot meet a 25% cut by construction. Every other funnel
  clause applies unchanged.
- **Stage 0 MDE.** It uses the paired design over alert keys present in
  both arms (a filled arm trade and its reference trade). `observed_n` is
  the number of filled keys, stated in the pre-registration record. If
  Stage 0 is underpowered, the result is recorded as UNDERPOWERED, budget
  intact, as v191 was.
- **Stage 1 plateau.** The winner is the cell with the highest ExpR among
  those clearing all clauses. It must have each grid neighbour clear
  clauses 1–3 as well; ⅓ and ⅔ have one neighbour each. No plateau means
  no proceed.
- **Stage 3 thin seal.** Fewer than 30 filled trades per direction in the
  validation window is reported as THIN, never as a pass.
- **Multiple comparisons.** The 3 looks enter the ledger's
  `ledger_qvalues` BH family.

**Disclosures** (printed, never gating):

- the paired per-alert ΔR over every in-scope alert, with an unfilled
  limit scored 0R;
- dollar P&L per alert;
- each cell's D range;
- the effective stop distance from M on fills;
- fills stopped within 3 bars, and how often the expiry cap or the TP1
  cancel binds (v131's adverse-selection diagnostics);
- the scope and drop counts.

## Goals

- **G1.** Build the knob in the confluence constructor
  (`builders.build_confluence_plan` / `_plan_geometry`) as a named helper.
  Replay, live and the measurement read one rule. With the knob at 0, the
  output is byte-identical to today, pinned by a witness test over a
  fixture replay.
- **G2.** Register the knob in the reachability registry and in the arm
  producer (`scripts/backtest/measure_arms.py`). Write the pre-registration
  record (`docs/superpowers/results/<date>-v212-preregistration.md`) before
  any compute, freezing the rule, the grid, the clauses, the gate family,
  the windows and `observed_n`.
- **G3.** Run Stages −1..3 through `backtest-runner`, chunked and
  checkpointed per unit, with a flushed percent print. Record the result
  and one ledger row per look.
- **G4. Live path, inert.** A limit plan's Discord alert and the admin plan
  view say "Buy limit at L (stop S′), valid 3 sessions". Shorts say "sell".
  Expiry and the TP1-before-fill cancel reuse the existing pending-plan
  lifecycle. Nothing is switched on: `.env.example` documents the knob at 0.

## Non-goals

- No change for out-of-scope plans, the 2% cap, the clamp itself or the
  floors on market plans.
- No strategy-source plans (v131 closed the Fibonacci form). No breakout
  plans.
- No re-entry after a stop-out. The partner considered it and set it
  aside.
- No turning it on. A Stage 3 pass is reported to the partner, who
  decides.

## Anti-goals

- **Re-running a closed stop row.** Out-of-scope plans keep today's stop.
  In-scope stops sit 0.25% under the support, from a better entry, and are
  never widened in ATR terms. If the panel finds this equivalent to v139 or
  v191, stop and redesign.
- **Shopping after Stage 1.** If no cell passes, the rule is closed. None
  of these is a retry: a different f, buffer, expiry, or a placement of the
  limit at the support.

## Constraints

- Every function stays under complexity 15. `build_confluence_plan` is
  already large, so new geometry goes in a named helper.
- No lookahead: M, S, the targets and ATR come only from bars ≤ t, the
  levels the scenario was built from.
- Tests ship with the work:
  - the geometry for each f (in scope, out of scope, the 2% drop, tick
    rounding, shorts mirrored);
  - expiry and the TP1-before-fill cancel;
  - knob 0 byte-identical;
  - alert and admin text;
  - empty and edge cases: level at exactly 2%, a missing level, a TP1
    whose R:R fails.

## Left to the builder

- Where the helper sits, and how `stop_moved_by` and the level reach it on
  the replay path.
- The results-doc layout. The per-direction table, the per-cell D range and
  the disclosures above are required.

## What follows

- **Stage 3 pass:** the partner decides whether to set the knob live (via
  `mirror-prod`).
- **No pass:** a closed row in `backtest-methodology.md`. The daily-close
  stop from the same review stays available as a separate mechanism.

## Panel review

**quant-researcher** (on 41a16218; all ADVISORY, three marked must-fix
before compute):

1. The limit at the level fills only after today's stop, so the arm holds
   no reference winner -- applied: the partner re-chose the placement
   (partway, f grid) and the Edge line is restated.
2. The funnel's 25% volume clause makes the pass rule impossible --
   applied: the partner's fills clause replaces it, stated.
3. No gate family named -- applied: harvest gate,
   `gate_expectancy_harvest`, point-estimate clauses.
4. Comparison population and denominators undefined -- applied: filled
   trades against the same in-scope plans' reference, pooled directions,
   paired per-alert ΔR disclosed, `observed_n` stated.
5. Multiple comparisons -- applied: 3 looks, pooled verdict unit, BH
   family.
6. Plateau undefined on a 1-D grid -- applied: winner plus neighbours,
   tie-break.
7. The R:R drop is an at-alert filter -- applied: counts reported, the
   reference is scored on the same in-scope plans.
8. Distinct from closed rows; add v131's adverse diagnostics and the
   effective stop distance -- applied (disclosures).
9. No thin seal -- applied: fewer than 30 fills per direction is THIN.
10. R re-priced at the limit -- applied: dollar P&L per alert disclosed.
11. Stop survival is out of scope (risk-manager) -- deferred to that seat.

**veteran-trader**, **risk-manager**: pending (run on the revised spec).
