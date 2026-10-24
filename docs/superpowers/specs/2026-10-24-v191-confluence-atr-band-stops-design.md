# v191 — Confluence ATR-band stops: a volatility floor and ceiling in place of the 1.75–2% price band, sized to a gap-aware dollar loss

**Version:** ui 1.35.1 · bot 2.15.0 (at writing)
**Bump:** bot patch (new config fields visible in the admin settings; every knob ships inert at its default, so no plan, alert or size changes until the partner flips one)
**Edge:** expectancy — moves stop and target geometry on confluence plans and changes which scenarios are admitted. Prediction: decided win rate rises by several points in every `k` cell; the ExpR change has unknown sign, and arm R is the likelier arm to lose (v139 arm S re-chose targets against a wider stop and lost 0.03R).
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

**No outcome was read to design this.** The autopsy cells quoted above are
the motivation, not a selection: no win rate or ExpR was split by stop
distance in ATR before this pre-registration.

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
  plans whose level sits between 2% and 2 × ATR; Stage −1 counts that
  overlap separately and the reporting splits every cell by which rule
  moved the stop (floor / ceiling / untouched), so the result never rests on
  the closed arm-S population alone.
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

On confluence plans, replacing the 1.75%–2% price band with an ATR band
(floor `k × ATR14`, ceiling `2 × ATR14`) and sizing every plan to fixed
dollar risk raises pooled expectancy without breaking the v72 funnel's
win-rate floor and volume clauses. Two target arms, each its own budget,
never pooled.

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
- **Headroom:** the plan stores `stop_ceiling_pct = band distance +
  CLAMP_HEADROOM_PCT` (0.25), so a stop-entry fill a little past the trigger
  is not cancelled as `cancelled_risk_cap` *(Claude's call: reuses the v115/v139 headroom unchanged)*.
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
is today's TP2. *(partner: two arms, keep vs re-choose)*

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
  can.

## Gate (both stop arms)

Both arms change admission (the floor admits new scenarios; arm K drops
plans), so both run the standard v72 funnel through `measure_arms.py`, not
the paired harvest gate *(Claude's call)*:

- Stage −1 reachability.
- Stage 0 paired MDE on fold-train.
- Stage 1 fold-train selection over `k` with `plateau_report()` (neighbours ±1 step).
- Stage 2 walk-forward folds 2021 / 2022 / 2023.
- Stage 3 one VALIDATION shot, all six clauses.

Instrument v1 on the watchlist cache, the same population v139 used
*(Claude's call: v190's instrument v3 is refused by the funnel until mapped)*.
Week-clustered bootstrap. One ledger row per arm.

## Stage −1 (no outcomes read)

Before any Stage 0, per horizon and direction:

- confluence plans today, and how many each `k` moves by the floor, by the ceiling, or leaves untouched;
- scenarios newly admitted by dropping the 1.75% floor;
- the overlap with v139 arm S's population (level between 2% and 2 × ATR);
- `a` distribution (ATR14 % of price) in 0.5-point buckets;
- arm K: `band_rr_drop` count; arm R: `band_no_target` count.

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

No change to entries, strategy plans, the 2% constant, alert layout (beyond Part B's gap line for longs mirroring v183's short line), charts or badges.

## Reporting (every stage, per arm and cell)

- N, ΔExpR with 95% interval, ΔWR, outcome flips both ways.
- Every figure split by `stop_moved_by` (floor / ceiling / untouched) and by direction.
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
2. Both arms gated by the v72 funnel (admission changes), not the paired harvest gate.
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
