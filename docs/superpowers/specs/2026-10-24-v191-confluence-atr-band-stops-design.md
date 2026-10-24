# v191 — Confluence ATR-band stops: a volatility floor and ceiling in place of the 1.75–2% price band, sized to a gap-aware dollar loss

**Version:** ui 1.35.1 · bot 2.15.0 (at writing)
**Bump:** bot patch (new config fields visible in the admin settings; every knob ships inert at its default, so no plan, alert or size changes until the partner flips one)
**Edge:** expectancy — moves stop and target geometry on confluence plans and changes which scenarios are admitted. Prediction (falsifiable, per cell on the floor-moved stratum): decided win rate rises by at least +4pp; arm K's ΔExpR is positive; arm R's ΔExpR is negative (v139 arm S re-chose targets against a wider stop and lost 0.03R). A result contradicting any of the three is recorded as a missed prediction.
**Screen:** harvest-headroom docs/superpowers/results/2026-10-21-book-autopsy-sep-era.md
**Panel:** risk-manager, veteran-trader, quant-researcher
**Status:** spec written 2026-10-24 from a brainstorm with the partner the same day. The partner's answers are marked *(partner)*; Claude's calls are marked *(Claude's call)* and listed again at the end.

## Why

**Live stops sit inside one ordinary day's range.** The current exit-model
era of the live book (`2026-10-21-book-autopsy-sep-era.md`, 2026-09-02 to
2026-10-21, N = 221, exploratory because it overlaps the 2026 holdout) shows:

- median stop distance about **0.37 × ATR14**;
- 101 of 221 trades closed at the stop, and 94 stop exits were gap-through or at-stop;
- pooled decided win rate **31.2%**;
- 47 of 288 plans cancelled as `risk_cap` because the fill could not keep the stop inside 2%.

**Why: the band is in price percent, the universe is volatile.**
Confluence stops sit exactly on the nearest opposing level
(`levels.build_scenarios`), must be at least `MIN_STOP_DISTANCE_PCT` (1.75%)
away to be admitted (`levels.py`, `analyze._scan_one`), and are moved to
1.75% when they are beyond the 2% hard cap (`builders._clamp_stop_to_hard_cap`,
v115). On a watchlist whose ATR14 runs ~4.5–5.5% of price, nearly every stop
lands between 1.75% and 2% of price whatever the instrument's volatility.

**The ideas that screened positive were all raced with wide stops.** Both
`SCREEN-PASS` rows (`screen-uptrend_pullback` +0.37R, `screen-turtle_soup`
+0.32R) raced a 1.5 × ATR14 stop. v180 took Turtle Soup through the bot's
own plan geometry and booked a decided win rate of 27.1% with half of all
stop-outs inside two sessions (`2026-10-23-v180-turtle-soup-result.md`).
That does not prove the stop is the cause (v180 also changed universe and
data source), which is why this is a pre-registration and not a fix.

**The 2% rule is a dollar rule.** The partner settled on 2026-09-25 that the
2% planned-loss cap bounds dollars at risk, not price distance, and that a
wider stop with fewer shares is fine. On 2026-10-24 the partner added: the
preset maximum loss must **never** be exceeded *(partner)*. Part B serves
that.

**Prior looks, disclosed.** The autopsy cells quoted above are the
motivation, not a selection. What was seen before this pre-registration:
the sep-era autopsy prints the median stop distance in ATR per outcome cell
(stop exits 0.37, `runner_be` 0.39, scratch 0.42) and tested an
`atr_pct_bucket` family that came out thin ("never evidence"). No win rate
or ExpR was split by stop distance in ATR on any replay or training data.
The `Screen:` citation is the nearest headroom document that exists: its
headroom figure is target-side give-back, not stop-side reversal, and the
`near_stop_reversal` cells are thin. Stage −1 therefore measures
stop-then-reversal counts on the training data before any outcome is
scored (§ Stage −1).

## The partner's v114 rule, overridden for this test only

v114 (2026-09-30) settled that "stops stay at real support/resistance
levels; the scan never places a stop at an arbitrary distance to hit a
percentage". The ATR floor and ceiling below place stops at distances no
level chose. On 2026-10-24 the partner chose to allow that **for this
pre-registration only** *(partner)*. A pass does not override v114 for live
plans: the partner decides again before any knob goes live (§ On a pass).

## Not a re-run

Read against "Closed pre-registrations" in `docs/claude/backtest-methodology.md`.

- **v139 arm S** (keep the confluence level up to `c ∈ {3, 4, 5}%`, dollar
  sizing) closed NO_ELIGIBLE_CELL. Its reopen clause asks for "a stop rule
  other than the confluence level itself up to a ceiling c, sized to fixed
  dollar risk". This spec's mechanism is a **volatility floor**: a stop
  closer than `k × ATR14` moves *out* to `k × ATR14`, a price no level put
  there, and scenarios now refused by the 1.75% admission floor are
  admitted with that floor stop. The 2 × ATR ceiling overlaps arm S on
  plans whose level sits beyond 2%: arm S's range was `d ∈ (2%, 4.75%]`,
  and untouched plans above 4.75% are arm S re-gridded to a volatility
  ceiling. **Decision rule (frozen):** an arm passes only if the
  **floor-moved stratum on its own** clears every gate clause (§ Gate); the
  untouched and ceiling strata are reported, never counted towards a pass.
  A pooled pass that the floor-moved stratum does not carry is a fail.
- **v139 arm D** (drop beyond a ceiling): arm K below drops plans for
  reward:risk, not for structural distance.
- **v114** (scenario stop band, no-lift) moved `MIN_STOP_DISTANCE_PCT` in
  percent. This replaces the percent band with an ATR band; no percent value
  is re-tried.
- **v104 Part A** measured strategy-path structural stops; this touches
  confluence plans only.
- **v103 A** (Fibonacci level stop, `b` ATR past the level) is a
  Fibonacci-strategy population and a buffer past the level, not a floor.

## Pre-registered claim

On confluence plans whose stop the floor moves, replacing the 1.75%–2%
price band with an ATR band (floor `k × ATR14`, ceiling `2 × ATR14`) and
sizing every plan to fixed dollar risk raises expectancy under the v92
harvest gate (expectancy objective, win-rate floor −2.0pp, volume floor).
Two target arms, never pooled; arm K is the **primary** arm, and the two
arms' VALIDATION p-values are Holm-corrected as a family of two
(`ledger_qvalues` reported, never gating).

## Definitions (frozen at the plan's creating bar)

- **ATR:** raw Wilder ATR14 of completed bars up to and including the plan's
  creating bar, as a percent of `entry` (`a = ATR14 / entry × 100`). It is
  **not** `levels.atr_floor_pct` / `scenario.atr_floor_pct`: that value is
  already multiplied by the horizon's `atr_stop_multiple` (1.5 or 2.0) and
  would make every band 1.5–2× too wide. The builder computes raw ATR14%
  itself (or receives it); a test pins the difference. No bar after the
  creating bar is read (NO-LOOKAHEAD).
- **Level distance `d`:** `planned_loss_pct(entry, scenario.stop_loss)` —
  the stop the scenario was built with, before any clamp.
- **Floor grid:** `k ∈ {0.75, 1.0, 1.5}` *(partner)*.
- **Ceiling:** fixed at `2.0 × a`, not searched *(partner)*.
- **Band stop:** with `lo = k × a` and `hi = 2.0 × a`:
  - `d < lo` → stop at `entry ∓ lo` (floor);
  - `lo ≤ d ≤ hi` → stop at the level (untouched);
  - `d > hi` → stop at `entry ∓ hi` (ceiling).
  - `lo < hi` always holds (`k ≤ 1.5 < 2.0`); a test pins it.
- **Order prices:** a floor or ceiling stop is rounded **away from entry**
  to the instrument's tick ($0.01 for prices ≥ $1, $0.0001 below), so the
  stop is never tighter than the band. It is an absolute price fixed at
  alert time, shown as such in the alert, and replay applies the same
  rounding. It is derived from the trigger, never re-derived from a fill.
- **Computed once.** The band, stop, ceiling and size are set at creation;
  a SIGHUP reload or a knob flip never rewrites an open or pending plan.
- **Headroom:** the plan stores `stop_ceiling_pct = band distance +
  CLAMP_HEADROOM_PCT` (0.25), so a stop-entry fill a little past the trigger
  is not cancelled as `cancelled_risk_cap` *(Claude's call: reuses the v115/v139 headroom unchanged)*.
  **Shares are sized on the worst fill inside the headroom** (distance =
  band distance + 0.25 points, plus the gap allowance of Part B), so the
  dollar loss at the stop stays within budget for any fill the plan accepts,
  and the alert's shares equal the engine's. A stop-entry fill past the
  headroom is cancelled as today (`cancelled_risk_cap`), with a Discord
  follow-up naming the cancel; replay fills a stop entry at the worse of
  the open and the trigger (`exit_sim`), as today.
- **The band replaces the percent band entirely** when the floor is on
  *(partner)*: `_clamp_stop_to_hard_cap` does not run for that plan, and an
  untouched stop between 2% and `hi` stays at its level.
- **Admission:** with the knob on, a confluence scenario is no longer
  refused by the stop-distance gates in `levels.build_scenarios` (reached
  from `analyze._horizon_scenarios`): neither `MIN_STOP_DISTANCE_PCT` (live
  1.75%; replay's legacy `CONFLUENCE_GATES` use 2.0) nor the max-stop gate
  `max(MAX_STOP_LOSS_PCT, horizon max_risk_pct)` (2% on 2w, 3% on 4w, 7–8%
  longer). The band is the only stop-distance limit, on every horizon
  *(partner, 2026-10-24: the band overrides the horizon caps)*; dollar loss
  stays fixed by sizing. The scenario's own-target reward:risk check runs
  against the band stop, not the raw level. Min reward and the R:R band
  inside `select_structural_target` are unchanged. The `analyze` risk_cap
  check and `PlanManager` read the stored `stop_ceiling_pct`, so a band
  plan is not cancelled for exceeding the horizon or 2% cap.
- **Missing ATR** (warm-up, empty frame) with the floor on: today's
  geometry and today's admission, so a scenario with `d` under today's
  floor is refused as today, counted as `band_no_atr` *(Claude's call)*.

## Arm R — re-choose TP1 against the band stop

TP1 and TP2 are selected by `select_structural_target` / `select_tp2`
against the band stop's risk, from the same candidates and the same
`MIN/MAX_RISK_REWARD_RATIO` band — today's code path with a different stop.
No candidate clears the band → no plan (today's behaviour), counted as
`band_no_target`.

## Arm K — keep TP1, drop plans below the minimum reward:risk

TP1 is the target today's code would pick against today's stop: the level
clamped into today's 1.75%–2% band (for a newly admitted scenario with
`d` under 1.75%, that is the 1.75% stop today's rules would have required)
*(Claude's call: gives every arm-K plan one defined "today's TP1")*.
The stop moves to the band stop. If TP1's reward:risk against the band stop
is below `MIN_RISK_REWARD_RATIO`, no plan, counted as `band_rr_drop`. TP2
is today's TP2. *(partner: two arms, keep vs re-choose)* The alert and the
stored planned RR show TP1's real reward:risk against the band stop, never
today's.

## Part B — gap-aware dollar sizing for longs and shorts

v183 sizes a SHORT so stop distance plus its p99 up-gap fits the dollar
budget (`planning/gap_sizing.py`, `SHORT_GAP_SIZING`). Part B extends the
same rule to LONGS with the p99 **down**-gap, behind a new flag
`LONG_GAP_SIZING` (bool, default off) *(partner: size with a gap allowance; Claude's call: its own flag, so it can go live independently of the stop arms)*.

- The stamp, the `MIN_UP_GAPS`-style minimum count (60 down-gaps over the
  250-bar lookback) and the "sized on the stop when no usable p99" fallback
  mirror v183 exactly. A long's stamp is set once at live creation from
  completed bars.
- Sizing and display only. R stays defined on the stop, so Part B moves no
  win rate and no ExpR in R; it lowers dollar loss on a gap through a long's
  stop and lowers dollar profit by the same share cut.
- Reported with the v183 impact script's method (`scripts/reports/short_gap_sizing_impact.py`
  extended or mirrored for longs): dollar exceedance count and size cut, on
  the live book. Descriptive, never gating.
- The guarantee stated honestly in the alert text and docs: the planned loss
  never exceeds the preset maximum; a gap beyond the ticker's own p99 still
  can *(partner accepted this residual on 2026-10-24)*.
- **Coupling (partner, 2026-10-24):** config validation refuses a live
  `CONFLUENCE_ATR_STOP_FLOOR > 0` unless both `LONG_GAP_SIZING` and
  `SHORT_GAP_SIZING` are on; the admin settings page shows the refusal.
  Replay measures R and is not coupled. `LONG_GAP_SIZING` alone may go live
  without the floor.
- One sizing function serves the alert's shown shares, the engine and the
  replay's dollar view (`gap_sizing.size_for*`), pinned by a parity test for
  the long gap path.

## The dollar invariant (binding on every band plan)

The price caps the band bypasses (`MAX_STOP_LOSS_PCT`, horizon
`max_risk_pct`, the 2% clamp, the `analyze` risk_cap) are replaced by one
pre-trade rule: **if risk sizing cannot fit the planned loss (worst
accepted fill to the stop, plus the gap allowance when on) inside
`RISK_PER_TRADE_PCT` of the balance, the plan is refused and logged, never
issued.** That includes a size that rounds to zero whole shares
(`band_size_zero`); a 1-share plan that overshoots the budget is never
issued. Portfolio heat (`PORTFOLIO_HEAT_CAP_PCT`) and the correlated cap
(`CORRELATED_HEAT_CAP_PCT`) apply to band plans unchanged, counting each
plan's sized dollar risk (stop distance plus gap allowance), so wider
stops never buy extra heat. Each new rejection reason (`band_rr_drop`,
`band_no_target`, `band_no_atr`, `band_size_zero`) writes the existing
"plan rejected (" log line.

## Gate (both stop arms)

This pre-registration **does not use the v72 funnel's clause set**: its
clause 3 (geometry lock) rejects a stop/target change by construction
(`backtest-methodology.md` § Harvest gate). It uses the **v92 harvest gate**
(`acceptance_harvest.py`), frozen here before fold-train is read
*(Claude's call, after the quant-researcher panel)*:

| # | Clause | Threshold |
|---|---|---|
| 1 | `expectancy_gain` (objective) | ΔExpR lower 95% bound > 0, one-sided p < 0.05 |
| 2 | `win_rate_floor` | Δstandardised-WR lower 95% bound ≥ −2.0pp |
| 3 | `volume_floor` | closed-trade cut ≤ 25% (the floor adds plans; arm K drops some) |
| 4 | `not_luck` | permutation n = 200 on ΔExpR, p < 0.05, VALIDATION only |

Every clause is scored on the **floor-moved stratum** (§ Not a re-run).
No mechanism clause (v72 clause 6 does not apply: the component is not a
subset of the baseline). Funnel through `measure_arms.py` with `--gate harvest`:

- Stage −1 reachability.
- Stage 0: paired MDE on fold-train, statistic **ΔExpR**
  (`acceptance.mde_paired(..., statistic=delta_expectancy_r)`) over the
  paired rows; newly admitted rows have no pair and are disclosed with
  their count. A cell whose MDE exceeds +0.10R at power 0.80 is refused.
- Stage 1: fold-train selection over `k`. Winner rule (frozen): the cell
  with the highest ΔExpR whose clauses 1–3 pass on fold-train **and** whose
  existing neighbour(s) in `{0.75, 1.0, 1.5}` sit within 0.05R of its
  ΔExpR (`plateau_report()`). An edge cell (0.75 or 1.5) is adoptable with
  its one neighbour; a cell with no eligible neighbour is a spike and does
  not proceed. The uneven steps are the partner's grid and stay as they are.
- Stage 2: walk-forward folds 2021 / 2022 / 2023, ≥ 2 of 3 with positive
  ΔExpR, per-fold N ≥ 30.
- Stage 3: one VALIDATION shot per arm, all four clauses; arm K primary,
  Holm across the two arms.

Frozen block: instrument **v1**, `data_source` **`alpaca`** (the v162
training-data store), the watchlist-era universe v139 and v180 used,
fold-train 2018-06-01..2022-12-31, VALIDATION 2024-01-01..2025-12-31
*(Claude's call: v190's instrument v3 is refused by the funnel until mapped)*.
Frictions: `frictions.py` slippage and commission apply identically to the
baseline and both arms, and a gap through a stop fills at the open, as
everywhere else. Week-clustered bootstrap. One ledger row per arm.

## Stage −1 (no outcomes read)

Before any Stage 0, per horizon and direction:

- confluence plans today, and how many each `k` moves by the floor, by the ceiling, or leaves untouched;
- scenarios newly admitted by dropping the 1.75% floor;
- the overlap with v139 arm S's population (level between 2% and 2 × ATR);
- `a` distribution (ATR14 % of price) in 0.5-point buckets;
- arm K: `band_rr_drop` count; arm R: `band_no_target` count; `band_size_zero` count;
- stop-then-reversal counts on today's geometry: stop exits whose price
  later reached TP1 within the horizon without first breaching `k × ATR`
  (outcome-adjacent, read once, never selects `k`);
- concurrent open band plans per day (max, p95) under the heat caps.

Zero changed plans in a cell closes it `refused:zero-diff`.

## Config

New `Field`s in `swingbot/config.py`, each with a `ScanParams` slot so live and replay agree, and a reachability row:

- `CONFLUENCE_ATR_STOP_FLOOR` — float `k`, default `0` (off: today's band). Search class `searchable`.
- `CONFLUENCE_ATR_TARGET_MODE` — `rechoose` | `keep`, default `rechoose`; read only when the floor is on. Search class `searchable`.
- `LONG_GAP_SIZING` — bool, default `false`. Not searchable (sizing only).

With the floor at 0, every replay output and every live plan is byte-identical to today, pinned by a flag-off golden captured before any behaviour change. `CLAMP_STOP_TO_HARD_CAP`, `MIN_STOP_DISTANCE_PCT` and the v139 knobs keep their meaning; measurement never sets a v139 knob together with this one.

## Code changes (the plan pins file:line)

- **`planning/builders.py`:** a helper `confluence_atr_band_stop(entry, level, is_bull, atr_pct, params)` returning `(stop_loss, stop_ceiling_pct, moved_by)`; `confluence_stop_geometry` calls it first when the floor is on. Arm K's "today's TP1" is computed from today's clamped stop inside the helper path. `build_confluence_plan` is near complexity 14: the arm logic lives in helpers and the builder ends below 15.
- **Admission:** `levels.build_scenarios` (live via `analyze._horizon_scenarios`, replay via `backtest_scenarios`) skips its min- and max-stop-distance checks when the floor is on and evaluates its own-target R:R against the band stop. Live/replay parity pinned by a test that accounts for replay's 2.0% legacy floor. `scanning/requirements.py` (display table) shows the band when on.
- **ATR into the builder:** raw ATR14% of the creating bar reaches `build_confluence_plan` (the plan names the carrier: a scenario field or an argument), never `atr_floor_pct`.
- **`planning/stop_scope.py`:** unchanged logic; `plan_stop_ceiling` already returns a stored `stop_ceiling_pct`, and `_needs_risk_sizing` already forces risk sizing for such a plan.
- **`planning/plan_types.py`:** `TradePlanV2.stop_moved_by: str | None` (`floor` / `ceiling` / `untouched`, default `None`), riding in `plans.doc` JSONB on the add path (`schema-evolution.md`), round-trip test against the test DB.
- **`planning/gap_sizing.py`:** the long branch behind `LONG_GAP_SIZING`; the `gap_stats` down-gap p99 (add it if `gap_stats` returns only up-gaps).
- **`core/backtesting/arms/reachability.py`:** rows for the two searchable knobs.

- **Alert text:** a band plan shows the absolute rounded stop, the stop distance in percent, TP1's real RR against the band stop, the horizon and the expiry; Part B adds a gap line for longs mirroring v183's short line.

No other change to entries, strategy plans, the 2% constant, alert layout, charts or badges.

## Reporting (every stage, per arm and cell)

- N, ΔExpR with 95% interval, ΔWR, outcome flips both ways.
- Every figure split by `stop_moved_by` (floor / ceiling / untouched), by direction and by horizon, with the top-two-horizon share of N.
- Dollars at fixed risk: dollar P&L at a fixed budget, and dollar exceedance count (loss beyond budget) for longs and shorts, every stage.
- Stop distance in percent by horizon as well as in ATR; per-day alert count and dollar volume of newly admitted plans.
- Regime (`regime2`) cut, descriptive only.
- Exit mix; early stops (within 2 sessions); gap-through-stop count and mean overshoot in R.
- Median planned RR per arm (falls by construction; disclosed, not gated).
- Newly admitted count; `band_rr_drop` / `band_no_target`; volume change %.
- Median stop distance in ATR, before and after.

## On a pass

The arm's result is recorded and its knob default stays `0` **until the
partner decides**, and that decision also revisits v114 for live plans. A
live switch changes what the alert tells the partner: wider stops, fewer
shares. Part B's flag is the partner's call independently of the arms.

## On a fail

One row per arm in "Closed pre-registrations — do not re-run these", plus a
ledger row each. Reopen clause: "a stop rule other than an ATR14 floor
`k × ATR` with a `2 × ATR` ceiling on confluence plans". Another `k` grid,
ceiling multiple, window or MDE ceiling is not a new mechanism. Part B
ships regardless of the arms' verdicts (it is sizing only).

## Testing

- Flag-off golden first: floor 0 → replay byte-identical.
- `confluence_atr_band_stop`, bullish and bearish mirror of each: `d` below `lo`, exactly `lo`, inside, exactly `hi`, above `hi`; missing ATR → today's geometry (counted).
- Arm K: TP1 kept, RR exactly at the minimum kept, just below dropped. Arm R: re-selected TP1; no candidate → no plan.
- Admission: a scenario at `d` = 1.0% is refused with the floor off and admitted with it on, live and replay alike.
- Fill: a stop-entry fill inside the stored headroom is not cancelled; one past it is.
- Dollar invariant: a plan whose sizing cannot fit the budget is refused and logged; zero whole shares → `band_size_zero`, never a 1-share plan; a fill at the edge of the headroom keeps the dollar loss ≤ budget; heat counts the sized dollar risk.
- Coupling: config validation refuses a live floor with either gap-sizing flag off.
- Tick rounding away from entry, bullish and bearish; replay uses the same rounding.
- Reload: flipping the knob leaves open and pending plans' stop, ceiling and size untouched.
- Sizing: `risk_sizing_ok` holds dollar loss ≤ budget for band distances {1.5, 4.0, 9.0}%; with `LONG_GAP_SIZING` on, a long's shares satisfy `shares × (stop distance + p99 down-gap) ≤ budget`; fewer than 60 down-gaps → sized on the stop.
- No lookahead: the band uses ATR14 through the creating bar only (a test mutates the next bar and sees no change).
- `stop_moved_by` round-trip against the test DB (`docker compose --profile test up -d db-test`), never left skipped at close-out.
- Complexity < 15 on every function written or changed.

## Out of scope

- A stop buffer past the level (`level ∓ b·ATR`) — a separate hypothesis.
- Strategy-path stops and `STRUCTURAL_STOP_SCOPE`.
- Changing `CLAMP_HEADROOM_PCT`, the 2% constant, or any v139 knob.
- Re-measuring on instrument v3 (follows v190 if the partner asks).

## Left to the builder

- The ATR carrier into `build_confluence_plan` and the exact admission call site.
- Whether Part B extends `short_gap_sizing_impact.py` or adds a sibling script.
- Task split and `Model:` tiers.

## Claude's calls, for the partner to check

1. Confluence path only; strategy-path stops unchanged.
2. Both arms gated by the v92 harvest gate on the floor-moved stratum, arm K primary, Holm across arms (after the quant-researcher panel; first draft said v72).
3. Instrument v1 on the watchlist cache, as v139.
4. Headroom 0.25 reused for the stored ceiling.
5. Part B behind its own `LONG_GAP_SIZING` flag, shipping regardless of the arms.
6. Prediction: win rate up in every cell, ExpR sign unknown, arm R likelier to lose.
7. Arm K's "today's TP1" for a newly admitted scenario is picked against the 1.75% stop today's rules would require.
8. Missing ATR with the floor on falls back to today's geometry and admission (`band_no_atr`).

## Parallelisation

- **Group A (parallel):** flag-off golden; config `Field`s + `ScanParams` + reachability rows; `TradePlanV2.stop_moved_by` with its round-trip test; Part B long gap sizing. Disjoint files, none changes default behaviour.
- **Group B (after A), sequential:** `confluence_atr_band_stop` → arm K/R wiring in `confluence_stop_geometry` / `build_confluence_plan` → admission bypass (live and replay). All touch the confluence stop path.
- **Group C (after B):** Stage −1, one `backtest-runner`.
- **Group D (after C):** arm R chain and arm K chain (Stages 0 → 3), independent outputs, one `backtest-runner` at a time.
- **Sequential tail:** record results and ledger rows, Part B impact report, full suite once, close-out.

## Panel review

Spec review 2026-10-24 (risk-manager, veteran-trader, quant-researcher), run serially on `c856c9a8`.

- risk-manager: BLOCKING — no dollar invariant once the price caps are bypassed -- applied (§ The dollar invariant).
- risk-manager: BLOCKING — whole-share floor / account too small for one share -- applied (`band_size_zero`, refuse and log, never a 1-share overshoot).
- risk-manager: BLOCKING — headroom fill overshoots a planned-distance size -- applied (shares sized on the worst fill inside the headroom).
- risk-manager: BLOCKING — `LONG_GAP_SIZING` decoupled from wider stops breaks the hard rule -- applied (partner chose coupling: a live floor requires both gap-sizing flags; residual beyond p99 accepted by the partner).
- risk-manager: ADVISORY — no dollar-at-fixed-risk reporting -- applied.
- risk-manager: ADVISORY — heat and correlated caps, heat basis, concurrency -- applied (heat counts sized dollar risk; Stage −1 concurrency count).
- risk-manager: ADVISORY — rejection reasons need a log line -- applied.
- risk-manager: ADVISORY — hot reload must not rewrite open plans -- applied (computed once).
- risk-manager: ADVISORY — alert/engine/replay sizing parity for longs -- applied (parity test).
- veteran-trader: BLOCKING — fill rule past headroom and follow-up message -- applied (cancel as today with a Discord follow-up; replay fill rule stated).
- veteran-trader: BLOCKING — band stop must be a placeable, rounded absolute price -- applied (tick rounding away from entry, fixed at alert time, same in replay).
- veteran-trader: ADVISORY — frictions parity, gap fills at the open -- applied (frozen block).
- veteran-trader: ADVISORY — 2w/4w stops near 10% need horizon and expiry restated; percent-by-horizon reporting -- applied (reporting; the alert restates horizon and expiry for band plans, see Code changes).
- veteran-trader: ADVISORY — alert volume and liquidity of newly admitted plans -- applied (per-day alert count, dollar volume).
- veteran-trader: ADVISORY — arm K alert must show the real RR -- applied.
- veteran-trader: ADVISORY — regime cut -- applied (descriptive).
- quant-researcher: BLOCKING — winner rule and clause set not frozen; v72 clause 3 waived -- applied (v92 harvest gate frozen, Stage 0 statistic ΔExpR, winner rule frozen).
- quant-researcher: BLOCKING — arm R's untouched stratum is v139 arm S re-gridded -- applied (decision on the floor-moved stratum alone; overlap range corrected to (2%, 4.75%]).
- quant-researcher: ADVISORY — two shots at one hypothesis -- applied (arm K primary, Holm across two arms, `ledger_qvalues` reported).
- quant-researcher: ADVISORY — plateau with a 3-cell uneven grid -- applied (edge-cell rule and 0.05R tolerance frozen; grid kept as the partner's).
- quant-researcher: ADVISORY — prediction not falsifiable -- applied (+4pp ΔWR, arm K ΔExpR > 0, arm R ΔExpR < 0).
- quant-researcher: ADVISORY — prior looks understated -- applied (§ Why, prior looks).
- quant-researcher: ADVISORY — `Screen:` headroom is target-side -- applied as disclosure; the citation stays (no stop-side headroom doc exists) and Stage −1 measures stop-then-reversal counts.
- quant-researcher: ADVISORY — clause 6 cannot apply -- applied (harvest gate has no mechanism clause; stated).
- quant-researcher: ADVISORY — `data_source` missing -- applied (`alpaca`).
- quant-researcher: ADVISORY — per-horizon split -- applied.
