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
- so today's stop was moved by the v115 clamp. That is read from
  `builders.clamped_distance` (`builders.py:588`), not `stop_moved_by`:
  only v191's ATR band sets `stop_moved_by`, so on the clamp path it is
  `None`.

The existing scenario gates (`MIN_STOP_DISTANCE_PCT` and the max-stop gate
in `levels.build_scenarios`) still run on the pre-clamp level before any
plan exists. They therefore bound each cell's D range. The results doc
prints the D range actually reached.

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
5. **Expiry.** The limit is valid through the close of the 3rd full
   session after the alert session, frozen. In replay that is bars t+1 to
   t+3. The plan also cancels if TP1 trades before the fill.
6. **Fill: one rule that mirrors a broker's resting order,** shared by
   replay (`exit_sim_v2._limit_entry_v2`), live (`plan_manager` limit
   handling, v187 D3) and the measurement.
   - **Primary rule: trade-through.** The bar's low must trade at least one
     tick under L (`limit_strict_fill`). A bar that only touches L counts
     as a fill only in a disclosed sensitivity.
   - **Gap through L.** An open at or under L fills **at the open**.
   - **Gap through the stop.** An open at or under the stop fills at the
     open and is stopped at the open in the same bar, a realised loss of
     more than 1R. It is **never** cancelled as a 0R scratch, because a
     resting broker order would have filled. Today's live
     `at_or_beyond_stop` cancel and fill-at-`trigger_price`
     (`plan_manager.py:1232-1249`) are changed **for this arm only**, so
     live, replay and the measurement agree. Out-of-scope plans keep
     today's live path.
   - **Price already at or under L when the alert is sent.** The order is
     marketable and fills at the quoted price. Replay starts at t+1 and
     cannot see this case, so live counts it and the shadow report
     discloses it.
   - **Frictions.** `swingbot/core/edge/frictions.py` applies, non-zero,
     to both arms on every trade.
7. **Sizing.** Fixed dollar risk on `|L − stop|`, with no change to the
   risk-per-trade setting. The notional caps
   `MAX_POSITION_SIZE_PCT` (`config.py:572`) and
   `MAX_POSITION_VALUE_ABSOLUTE` (`config.py:650`) **still bind** in replay,
   the measurement and live alike. A fill whose size a notional cap cut
   carries less than the fixed dollar risk, and its R is still scored on
   the plan's stop. The share of such fills is disclosed.
   - Every kept plan satisfies `|L − stop| / L ≤ 2%`, asserted in replay
     and live (`known-traps.md` § Stop floor and 2% cap).
   - The alert's suggested size equals the engine's size. An alert blocked
     by a heat, sector or cluster cap is still flagged with size 0, as
     today.
8. **Heat is re-checked at fill** *(author's call among the options the
   panel offered)*. Today's heat, sector, cluster and `MAX_OPEN_POSITIONS`
   checks (`scan_run.py:1210-1229`, `heat.py`) run at alert time against
   open trades only, so a pending limit reserves nothing. When a limit
   fills, the same checks run again against the then-open book, using the
   fill's actual risk.
   - If any cap would be breached, the fill is cancelled. The plan is then
     `cancelled_limit` with the reason `heat_at_fill`, and live posts a
     follow-up.
   - Replay applies the identical rule, so the scored portfolio is one that
     could exist. On a sell-off day this stops resting limits stacking risk
     past the caps.
   - Pending limits do not reserve heat, because that would block other
     alerts on orders that mostly never fill.
9. **Drops are logged** through the existing `plan rejected (` lines,
   with reasons `limit_scope`, `limit_stop_beyond_cap` and
   `limit_rr_fail`. A quiet day caused by this arm can then be diagnosed.

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
- the scope and drop counts;
- the touch-fill sensitivity, scored with the same clauses;
- the count of gap-through-stop fills, and their mean R;
- the share of stops that were wick-throughs closing back above the stop
  (stop-run diagnostic; never grounds to widen the buffer);
- fills and ExpR by ATR14% bucket;
- fills and ExpR on SPY down days (close < prior close − 1%) against
  other days, and the number of distinct fill days;
- the share of fills with an earnings date inside the 3-bar window;
- dollar P&L at fixed risk per cell, on filled trades only;
- the share of fills whose size a notional cap cut;
- fills cancelled by `heat_at_fill`;
- risk and ruin (`edge/ruin.py`, `analytics/risk_metrics.py`), for the arm
  against the reference:
  - the worst single-day sum of R;
  - the maximum simultaneous open risk at one open;
  - the maximum drawdown;
  - the worst gap-through-stop R, and its per-day clustering.

## Goals

- **G1.** Build the knob in the confluence constructor
  (`builders.build_confluence_plan` / `_plan_geometry`) as a named helper.
  Replay, live and the measurement read one rule. With the knob at 0, the
  output is byte-identical to today, pinned by a witness test over a
  fixture replay.
- **G2. A dedicated replay module and measure script,** following the
  v139, v191 and v131 precedent: `confluence_stop_replay.py` with
  `measure_confluence_stop.py`, `atr_band_replay.py` with
  `measure_atr_band_stop.py`, and `measure_fib_limit.py`. The generic
  `measure_arms.py` is not used. Rule 6 (fill semantics and frictions),
  rule 7 (notional caps) and rule 8 (heat at fill) are new replay code:
  - **Frictions:** the v2 exit sim is frictionless today, so frictions are
    applied at scoring to both arms.
  - **The portfolio pass:** heat at fill, sector caps, cluster caps,
    `MAX_OPEN_POSITIONS` and the notional caps run in one portfolio pass.
    It extends `backtest_wf.portfolio_replay`, which gains notional caps.
    The clauses score that pass's kept trades, in both arms.

  Register the knob in the reachability registry. Write the
  pre-registration record
  (`docs/superpowers/results/<date>-v212-preregistration.md`) before any
  compute, freezing the rule, the grid, the clauses, the gate family, the
  windows and `observed_n`.

  **Three tie and cooldown rules, frozen here** *(author's calls, made after
  the briefing)*:
  - **TP1 cancel is inclusive.** A bar whose high reaches TP1 before a fill
    cancels the limit (`≥`; a short uses `≤`). Today's `limit_cancelled`
    is strict and is not reused unchanged for this arm.
  - **Same-bar conflict.** A bar that trades both L and TP1 counts as
    cancelled, not filled. This is the conservative choice.
  - **Cooldown.** `_REPLAY_COOLDOWN_BARS` stays set at plan acceptance, as
    today. An unfilled or dropped limit consumes it exactly as the
    reference arm's plan does, so both arms see the same plan stream.
- **G3.** Run Stages −1..3 through `backtest-runner`, chunked and
  checkpointed per unit, with a flushed percent print. Record the result
  and one ledger row per look.
- **G4. Live path, inert.** The alert and the admin plan view must work
  for someone resting orders before the open. Each limit alert states all
  of these, as prices rounded to the tick:
  - "Buy limit L" ("sell" for shorts);
  - "on fill: stop S′, TP1 T1 (TP2 T2)" (bracket/OCO wording);
  - "cancel the order if price trades at T1 before it fills";
  - "valid through the close of <date>".

  The bot then posts a **follow-up for every state change**:
  - filled, with "place the stop at S′ now";
  - expired;
  - cancelled because TP1 traded first;
  - filled-and-stopped on a gap.

  The existing `cancelled_limit` event already reaches Discord: it is in
  `PENDING_CANCEL_EVENTS` and `NOTICE_EVENTS`, with execution-feed,
  lifecycle-embed and follow_notify mappings. Two events are new: the
  `heat_at_fill` cancel and a filled-and-stopped-on-gap event.
  - **Registration.** Each joins every event table that `cancelled_limit`
    is in. The brief lists about 8 tables.
  - **A test enforces it:** every cancel or close event appears in each
    table, so a placeholder paper trade is never left open (the 2026-09-11
    incident).
  - **Alert text is new code.** Today a limit plan prints "BUY AT MARKET" /
    "Entry: market ~X" (`presentation/instructions.py:ticket_for`,
    `scanning/plan_table.py:entry_line`), so those gain limit wording. The
    admin SPA already prints "Buy limit" (`trade-figures.ts:51`), and
    `why/levels-block.ts` gains the limit mapping.
  - **Live fill price.** For this arm only, `_fill_pending`'s `risk_cap`
    check reads the planned `|L − stop|`, not the gap fill price. A long
    fill below L only shrinks the loss; a gap below the stop takes the
    filled-and-stopped path.

  The extra alert volume is reported: limit alerts plus follow-ups per
  day, estimated from replay. Nothing is switched on: `.env.example`
  documents the knob at 0.

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

- Where the helper sits, and how `clamped_distance` and the level reach it
  on the replay path.
- Keeping `build_confluence_plan` (12), `attach_plan_v2` (12) and
  `_step_pending` (11) under 15: new branches go into named helpers.
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

**veteran-trader** (on a31e8a45):

1. BLOCKING: the alert gives no way to place the stop or the TP1 cancel as
   orders before the open -- applied: G4 order wording and a follow-up on
   every state change.
2. BLOCKING: live and replay disagree on a gap through the limit, and the
   live cancel on a gap beyond the stop flatters the arm -- applied: rule
   6, resting-order semantics in all three paths, gap-through-stop scored
   as realised.
3. BLOCKING: frictions not stated; touch versus trade-through -- applied:
   frictions on both arms, trade-through as the primary rule, touch as a
   disclosure.
4. A 0.25% buffer is about 0.05 ATR (stop-run risk) -- applied: a
   wick-through disclosure, and the buffer stays frozen.
5. Fills at high f are dominated by high-ATR names -- applied: ATR-bucket
   disclosure.
6. Earnings inside the 3-bar window -- applied: disclosure.
7. Sell-off days carry the fills -- applied: SPY down-day and distinct-day
   disclosures.
8. Alert timing, a marketable limit at alert, alert volume -- applied:
   rule 6 and G4.
9. Bigger share counts on a tighter stop -- deferred to risk-manager.

**risk-manager** (on 6f2801be; the first run was stopped and rerun):

1. BLOCKING: no notional bound on larger share counts -- applied: rule 7,
   the caps bind in all paths and capped fills are disclosed.
2. BLOCKING: pending limits reserve no heat; a sell-off day can stack fills
   past the caps -- applied: rule 8, caps re-checked at fill in live and
   replay, cancel with a follow-up. The author chose re-check at fill over
   reserving heat while pending, which would block other alerts on orders
   that mostly never fill.
3. BLOCKING: no portfolio-level bound for a gap morning -- applied:
   worst-day R, maximum simultaneous risk, drawdown and gap clustering
   disclosed.
4. Assert `|L − stop| / L ≤ 2%` in replay and live -- applied: rule 7.
5. Dollar P&L at fixed risk on filled trades -- applied (disclosure).
6. Alert size equals engine size; a blocked alert shows size 0 -- applied:
   rule 7.
7. Drop reasons logged; admin risk view -- applied: rule 9. The admin view
   is unaffected, because nothing reserves pending heat.
8. Veteran-trader item 9 covered -- applied.
