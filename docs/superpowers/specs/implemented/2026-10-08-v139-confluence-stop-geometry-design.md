# v139 — Confluence stop geometry: a structural stop sized to dollar risk, or no plan

**Version:** ui 1.21.1 · bot 2.2.2 (at writing)
**Bump:** none (both knobs ship inert at default 0; amended at close-out if an arm passes VALIDATION)
**Edge:** expectancy — arm D removes trades (v72 funnel); arm S keeps the entries and moves stop and target geometry, so it is gated as harvest (v92)
**Status:** spec written 2026-10-08; no plan yet.

## Why

**The live confluence path contradicts the partner's own stop rule.** On
2026-09-30 (v114) the partner settled that "stops stay at real
support/resistance levels; the scan never places a stop at an arbitrary
distance to hit a percentage". `builders._clamp_stop_to_hard_cap` (v115,
`CLAMP_STOP_TO_HARD_CAP`, default on) does exactly that. A confluence stop
further than 2% from the trigger is moved to `entry ∓ 1.75%`, a price no
level put there. TP1 is then picked against that clamped risk
(`build_confluence_plan`, `select_structural_target(entry, stop_loss, ...)`).

**How much of the book this is.** In v129's TRAIN replay (2020–2023, 73
tickers, all legacy horizons), 5,275 of 8,090 confluence entries (65%) were
"not eligible" for arm Z. That set is mostly plans whose level sits beyond the
2% cap. It also counts levels on the profit side of entry, so the exact
clamped share is measured at Stage −1 (below), not assumed.

**Why the clamped stop is a poor stop.** v129 recorded that ATR14 runs at
roughly 2–6% of price on this universe. A 1.75% stop therefore sits inside
one ordinary daily range, below the level the trade leans on. It is hit by
noise that never tests the thesis. v129's acceptance exit fired twice in 2,815
eligible trades for the same reason: the bar that reaches the level usually
trades through the 2% cap first.

**The 2% rule is a dollar rule.** The partner stated on 2026-09-25 that the 2%
planned-loss rule bounds **dollar risk per trade**, not price distance, and
that a wider structural stop is acceptable if share count keeps the dollar
loss fixed. With risk-based sizing, a result measured in R is a result in
dollars. One R is the same dollar amount whatever the stop distance, so
ExpR compares the arms directly.

**Two honest fixes, opposite directions.** Put the stop back at the level and
size down (arm S, a widening), or decline to issue a plan whose level is too
far away (arm D, a tightening). The partner chose to test both, each on its
own budget (2026-10-08). That pairs a widening with a tightening, so the work
has a path to more good plans and not only fewer bad ones.

**No outcome was read to design this.** v129's saved rows were used for
counts only (eligibility, exit mix). No win rate or ExpR was split by
clamped vs unclamped before this pre-registration.

## Not a re-run

Read against "Closed pre-registrations" in `docs/claude/backtest-methodology.md`.

- **v104 Part A (structural stops + fixed-dollar sizing)** is the same
  mechanism on a **different population**. It measured 15 strategy ×
  direction cells through `STRUCTURAL_STOP_SCOPE`, which only reaches
  `build_strategy_plan`. Confluence plans (`build_confluence_plan`, ~80% of
  the live book) were never in it. Its reopen clause names the strategy
  cells it failed. This spec reopens none of them and adds no strategy pair.
  The partner authorised measuring the confluence population on 2026-10-08,
  knowing the v104 overlap.
- **v129 arm Z** kept the 2% cap on its disaster stop, and `m` never bound
  because of it. It also added a close exit. Arm S has no cap below the
  ceiling `c` and no close exit. Its reopen clause names "exit on a daily close
  beyond the plan's own level", which is not this.
- **v103 A** (Fibonacci level stop, drop-don't-cap) and **v101** (Fibonacci
  structural-stop filter) are Fibonacci-only strategy populations.
- **v114** (scenario stop band, no-lift) moved the admission **floor**
  (`MIN_STOP_DISTANCE_PCT`), not the clamp.

## Pre-registered claim

On confluence plans whose structural stop is beyond the 2% cap:

- **Arm S:** keeping the structural stop up to a ceiling `c`, with the
  target re-selected against that risk and the position sized to fixed dollar
  risk, raises per-trade expectancy under the v92 harvest gate, on the same
  entries.
- **Arm D:** issuing no plan when the structural stop is beyond `c` raises
  pooled expectancy without breaking the v72 funnel's win-rate and volume
  clauses.

Two arms, two populations, two budgets. A pass in one never carries the other,
and the two are never pooled.

## Definitions (frozen at the plan's creating bar)

- **Clamped plan:** `source == "confluence"`, the scenario stop is on the stop
  side of entry, and `planned_loss_pct(entry, scenario.stop_loss) >
  HARD_MAX_PLANNED_LOSS_PCT`. That is exactly the set
  `_clamp_stop_to_hard_cap` moves today. Every other plan is untouched in
  both arms.
- **Structural distance `d`:** `planned_loss_pct(entry, scenario.stop_loss)`
  — the stop the scenario was built with, before the clamp.
- **Ceiling grid:** `c ∈ {3.0, 4.0, 5.0}` percent, shared by both arms. Scenario
  admission (`analyze._scan_one`) already bounds `d` by the horizon's
  `max_risk_pct`, so `c` never exceeds what is admitted today.
- **Headroom:** `CLAMP_HEADROOM_PCT` (0.25), as v115 uses it. A plan is placed
  only when `d ≤ c − 0.25`, so a fill slightly past the trigger stays inside
  the stored ceiling `c` and is not cancelled as `cancelled_risk_cap`.

## Arm S — structural stop, dollar sizing

For a clamped plan:

- `d ≤ c − 0.25`: `stop_loss = scenario.stop_loss`. TP1 and TP2 are
  re-selected with `select_structural_target` against the structural risk,
  from the same candidates and the same `MIN/MAX_RISK_REWARD_RATIO` band.
  The plan stores `stop_ceiling_pct = c`.
- Same, but **no candidate clears the RR band** at the structural risk: the
  plan reverts to today's clamped plan. This is the level-lifecycle rollback
  precedent (`config.py`, "rolling the widening back entirely"). Counted and
  disclosed, never dropped.
- `d > c − 0.25`: today's clamped plan.

1R is entry → structural stop. Sizing is `account.compute_position_size` in
`risk_pct` mode, so the dollar loss at the stop equals `RISK_PER_TRADE_PCT`
of the balance whatever `d` is. `stop_scope.risk_sizing_ok` must pass for an
arm-S plan, as it does for v104 scope pairs. A gap through the stop books
its real loss beyond −1R, as everywhere else, and the gap-through count is
disclosed.

**Gate:** the v92 harvest gate, paired (same entries, two stop/target
geometries), as v129 ran it.

- Stage 0: paired MDE ceiling +0.10R at power 0.80. Any cell over the
  ceiling closes the arm.
- Stage 1: TRAIN plateau selection over `c`. A cell is eligible when
  `expectancy_gain`, `win_rate_floor` (−2.0pp) and `volume` pass. The
  neighbours are ±1 step in `c`.
- Stage 2: four calendar-year TRAIN folds.
- Stage 3: one VALIDATION shot with all four clauses, `not_luck` n=200.

The bootstrap clusters by ISO week (instrument v2, `cluster="week"`,
`instrument.stats`), and the ledger row records `--instrument v2`.

## Arm D — no plan beyond the ceiling

For a clamped plan:

- `d > c`: no plan. The scenario is rejected at build time with the reason
  `stop_beyond_confluence_ceiling`, counted in the funnel.
- `d ≤ c`: today's clamped plan, unchanged.

This is a subset feature (`Edge: expectancy`). It runs the standard v72
funnel through `measure_arms.py` with the knob delta
`CONFLUENCE_STOP_DROP_PCT=c`:

- Stage −1 reachability.
- Stage 0 paired MDE.
- Stage 1 fold-train selection with `plateau_report()`.
- Stage 2 walk-forward folds.
- Stage 3 one VALIDATION shot with all six clauses.

A `c` whose volume cut exceeds `VOLUME_MAX_CUT_PCT` (25%) fails clause 3. That
is an expected possible outcome, recorded and not rescued.

## Stage −1 for both arms (no outcomes read)

Before any Stage 0, the plan records per horizon and direction:

- the number of confluence plans and how many are clamped;
- the distribution of `d` on the clamped set (counts in 0.5% buckets up to the
  admission ceiling);
- for arm S, how many clamped plans fall at each `c`, and how many of those
  roll back for lack of an RR-band target.

If no cell changes any plan, the arm closes `refused:zero-diff`, as v123
`progress_stall` did. This replaces the 65% estimate above with a measured
count.

## Config

Two new `Field`s in `swingbot/config.py`. Both are `float`, default `0`
(off), and search class `searchable`. Each gets a reachability row so
`measure_arms.py` accepts the knob delta.

- `CONFLUENCE_STRUCTURAL_STOP_PCT`: the arm S ceiling `c`. `0` means today's
  clamp.
- `CONFLUENCE_STOP_DROP_PCT`: the arm D ceiling `c`. `0` means no drop.

With both set, arm S applies first, for `d ≤ c_S − 0.25`. Arm D then drops
what is beyond `c_D`. Measurement never sets both. `CLAMP_STOP_TO_HARD_CAP`
keeps its meaning and default.

## Code changes (the plan pins file:line)

- **`planning/builders.py`:** one new helper,
  `confluence_stop_geometry(entry, level, is_bull, params)`. It returns
  `(stop_loss, stop_ceiling_pct)` or a drop sentinel, and replaces the bare
  `_clamp_stop_to_hard_cap` call in `build_confluence_plan`.
  `build_confluence_plan` is at cyclomatic complexity 14, so the arm logic
  and the arm-S target re-selection and rollback live in the helper. The call
  site may add at most one branch (the drop), and the function must still
  end below 15.
- **`planning/plan_types.py`:** a `TradePlanV2.stop_ceiling_pct: float | None`
  field (default `None`). It is not a key, an index or NOT NULL, so it rides
  in `plans.doc` JSONB on the "add" path (`schema-evolution.md`) with no
  Alembic revision. A repository round-trip test pins that.
- **`planning/stop_scope.py`:** `plan_stop_ceiling` returns
  `plan.stop_ceiling_pct` when it is set. This is the ceiling
  `exit_sim.py` (fill check) and `plan_manager` (`_step_pending`, active
  checks) read, so an arm-S plan is not cancelled at fill for exceeding 2%.
  `risk_sizing_ok` also applies to a plan with `stop_ceiling_pct` set.
- **`scan_params.py`:** carries both knobs, so live and replay agree.
- **`core/backtesting/arms/reachability.py`:** rows for both knobs.

No change to entries, the unclamped plans, strategy plans, the 2% cap
constant, `MIN_STOP_DISTANCE_PCT`, alert text structure, charts or badges.
With both knobs at 0, every replay output is byte-identical to today, pinned
by a flag-off golden captured before any behaviour change.

## Reporting (every stage, per arm and cell)

- N per arm, ΔExpR with its 95% interval, and ΔWR.
- Outcome flips in both directions.
- Exit mix by reason.
- Median planned RR per arm. Arm S lowers RR by construction, and that is
  disclosed, not gated.
- Arm S: rollback count and gap-through count. Median `d` of the plans that
  changed.
- Arm D: dropped count and volume cut %.
- Per-horizon N. Entries only one side triggered (a wider stop changes
  stop-entry invalidation, as in v129).

## On a pass

The arm's result is recorded and its float default is set to the selected
`c`, still inert behind a 0 default **until the partner decides**. Arm S
changes what the alert tells the partner to do: a wider stop and fewer
shares on resting broker orders. Nothing goes live without that answer.

## On a fail

One row per arm in "Closed pre-registrations — do not re-run these", plus a
ledger row each. The reopen clause: arm S needs "a stop rule other than the
confluence level itself up to a ceiling `c`, sized to fixed dollar risk".
Arm D needs "a drop rule other than structural distance beyond `c`". Another
grid, window or MDE ceiling is not a new mechanism.

## Testing

- Flag-off golden captured first. With both knobs at 0, replay is
  byte-identical.
- `confluence_stop_geometry` for each case:
  - unclamped plan, both arms → unchanged;
  - `d` exactly at `c − 0.25` → arm S applies;
  - just above → clamped;
  - arm S with no RR-band target → rollback to the clamped plan;
  - arm D `d` exactly at `c` → kept;
  - just above → dropped;
  - bearish mirror of each.
- `plan_stop_ceiling` returns the stored `c`. A fill past the trigger inside
  the headroom is not cancelled; one past `c` is.
- `risk_sizing_ok` holds the dollar loss at `RISK_PER_TRADE_PCT` for `d` in
  {2.5, 4.0, 4.75}.
- The `stop_ceiling_pct` repository round-trip runs against the test DB
  (`docker compose --profile test up -d db-test`). It must not be left
  skipped at close-out.
- Complexity: every function written or changed ends below 15.

## Out of scope

- Any stop buffer beyond the level, such as `level ∓ k·ATR`. That would be a
  second axis and a separate hypothesis.
- Strategy plans and `STRUCTURAL_STOP_SCOPE` pairs (v104).
- Changing the 1.75% clamp itself, or `CLAMP_HEADROOM_PCT`.
- Live wiring beyond `plan_stop_ceiling`, which the fill and active checks
  already route through.

## Parallelisation

- **Group A (parallel):**
  - the flag-off golden;
  - the `TradePlanV2.stop_ceiling_pct` field with its serialization and
    repository tests;
  - the two config `Field`s with `ScanParams` and the reachability rows.

  Their files are disjoint, and none changes behaviour.
- **Group B (after A), sequential:** `confluence_stop_geometry` with its
  tests, then the `build_confluence_plan` call site, then the
  `stop_scope.plan_stop_ceiling` / `risk_sizing_ok` change. All three touch
  the plan's stop path.
- **Group C (after B):** Stage −1 for both arms, one `backtest-runner` at a
  time.
- **Group D (after C):** the arm S chain (Stages 0 → 1 → 2 → 3) and the arm D
  chain. The chains are independent, with disjoint outputs, and run one
  `backtest-runner` at a time. Each stage consumes the previous verdict.
- **Sequential tail:** record both arms, then the full suite once, then the
  close-out.
