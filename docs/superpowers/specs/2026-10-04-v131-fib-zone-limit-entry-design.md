# v131 — Fibonacci resting limit entry inside the retracement zone

**Version:** ui 1.21.1 · bot 2.0.1 (at writing)
**Bump:** none (measurement plus a plan-shape field and a masked strategy entry that no live path reaches; live wiring is a follow-on spec)
**Edge:** expectancy — a better entry price on the same stop raises R per win; the measurement decides whether adverse selection eats it. Prediction did not hold: adverse selection ate the price improvement -- no cell beat the reference ExpR on TRAIN (best +0.229 vs +0.259), closed NO-LIFT at Stage 1.

## Why

Fibonacci has been `WEAK` since the 2026-09-10 badge refresh. Under today's
arithmetic it is profitable but loses too often. The bullish TRAIN_EXT
reference (v102/v103) is N=815, WR 36.81%, ExpR +0.2219. It fails the badge on
`win_rate >= 50` alone.

Every closed Fibonacci pre-registration changed a stop, a target, a filter or
a horizon. None of them changed the entry mechanics:

| Closed row | What it changed |
|---|---|
| v84 | 1.0 extension target |
| v101 | stop variants, reclaim entry (a later *market* entry) |
| v102 | Rolling S/R confluence filter |
| v103 A / C | level stop / continuation through the swing extreme |
| v104 | structural stop |
| v113 B | the `1w` horizon |

v124, which has not run yet, measures *which leg* the levels are drawn on.

Today's entry is a market order on the close of the bounce bar
(`fibonacci_entries`: a pullback, then a bounce bar closing in its upper
half). By then price has already left the level. The 2% stop cap binds on
every plan, so the stop sits a fixed distance below the close. Buying *at*
the zone instead, with a resting limit order placed while price is still
pulling back, buys the same structure at a lower price. If the stop
structure is held, each win banks more R and the cap binds less often.

The risk is adverse selection. A resting buy limit fills most reliably on the
pullbacks that keep falling. Whether that cost exceeds the price improvement
is an empirical question, and this spec pre-registers the measurement.

**Partner decisions (2026-10-04):**
- Profit comes first. `VALIDATED` follows only if the win rate clears 50% on
  its own, and the mechanism is never bent to reach it.
- The order is armed *ahead* of the zone, not on a retest after today's signal.
- Today's rolling anchors are used, not v124's impulse leg.
- Stage 1 uses ExpR plus a volume floor, not total R.
- A Fibonacci meta-label spec (B) is queued behind this one and reads the
  features this run records.

## Scope

In:
- a setup function and a masked strategy entry, `Fibonacci Limit`
- an optional `limit_price` plan-shape field honoured by both plan
  constructors
- pre-fill cancel support in the limit simulator
- a measurement script
- the pre-registration, the results documents and the closed-pre-registrations
  row

Out:
- any live resting order, `PlanManager` change or Discord alert line
- bearish Fibonacci
- v124's impulse leg
- any change to today's `Fibonacci` entry, plan or exits
- any feature split or mining of the recorded features (B's job)

## The mechanism

Bullish only. Everything is computed at the close of the arming bar `t` from
`df.iloc[:t+1]`.

### Arming condition (`fibonacci_limit_setups`)

All of these must hold at `t`:

1. **Valid up-leg on today's rolling anchors.** `swing_high`/`swing_low` are the
   rolling `fib_lookback` max High / min Low that `fibonacci_entries` uses. The
   low precedes the high, the same `argmax_pos > argmin_pos` test.
2. **Pullback underway.** The swing-high bar is at least 3 bars old (`t − 3` or
   earlier).
3. **Still above the order.** The close's retracement
   `(swing_high − close) / (swing_high − swing_low)` is ≥ 0.236 and < `L`.
4. **Trend and volatility filters, kept from `fibonacci_entries`:**
   - MA200 above and rising over 20 bars
   - close > MA50
   - ATR ≥ 0.7% of the close
   - ATR ≤ 1.4× its 60-bar mean
5. **No live order** on this ticker and horizon, and this leg has not already
   armed. A leg is identified by its swing-high bar. An expired or cancelled
   order never re-arms on the same leg, so the arm cannot chase a leg bar by
   bar.

Dropped from `fibonacci_entries`: the RSI band, the volume ≥ 0.9× gate, the
5-bar pullback test and the bounce-bar shape. Each one judges the bounce bar,
and at arming that bar does not exist yet. The partner approved dropping them.

The function returns, per bar, the arming mask plus the frozen `swing_high`,
`swing_low`, `swing_high_idx` and `limit_price = swing_high − L × (swing_high −
swing_low)`.

### The order and the plan

The plan is priced entirely at `t`, from the limit price:

- **Entry:** `limit_price`.
- **Stop:** `swing_low − 0.25 × ATR14[t]` through today's `_bounded_stop` and
  `stop_ceiling`, measured from the limit price: capped at 2% below it, or
  dropped if `Fibonacci Limit` is ever placed in `STRUCTURAL_STOP_SCOPE` (it
  is not here).
- **TP1:** `select_structural_target` over `fib_target_candidates`, with R
  measured from the limit price, inside the frozen 1.5–2.5R band. If no
  candidate reaches 1.5R, no order is placed.
- **Exits:** today's Fibonacci shape, unchanged: v2, scale-out,
  `trail_atr_mult` 3.0, no TP2.
- **Level lifecycle:** `LEVEL_LIFECYCLE_STOPS_ENABLED` is on by default, so
  it applies to both the cells and the reference arm. That keeps the two
  sides comparable.
- **Arms without a plan:** an arm whose plan is rejected (no TP1 at ≥ 1.5R)
  still uses up its leg and its N-bar slot, because the setup function cannot
  see the planner. This is conservative, and the rejected count is disclosed.
- **Order life:** `N` bars, `t+1 .. t+N`.

### Fill and cancel (`exit_sim._limit_entry_exit`)

- **Fill:** on the first bar in `t+1 .. t+N` with `Low < limit_price`, strictly.
  An exact touch does not fill. This is a frictionless simulator, and a touch
  fill is the most optimistic assumption available.
- **Fill price:** `min(Open, limit_price)`. A gap down fills at the open.
- **Pre-fill cancel:** on the first bar whose `High > swing_high` (frozen),
  before any fill. The leg extended and the setup is stale. If one bar both
  makes a new high and trades through the limit, the fill takes precedence
  and the fill-bar stop rule applies. The count of such bars is disclosed.
- **Fill bar:** today's `_fill_bar_exit`:
  - a fill at or beyond the stop scores as a scratch
  - otherwise the stop is checked on the fill bar
  - the target is not checked until the next bar
- **R:** measured from the fill price.
- **Unfilled:** expired and cancelled orders are counted per cell (they feed
  the fill-rate disclosure) and produce no trade.

### Plan-shape field

`PLAN_SHAPES` gains an optional `limit_price` entry: the name of a registered
limit-price function, `(df, idx, horizon, direction) -> float | None`.
`backtest._bt_plan` and `builders.build_strategy_plan` both honour it. When it
is present, entry is the returned price and stop and targets are priced from
it. When it is absent, every existing strategy builds byte-identical plans,
and a witness test pins that.

`Fibonacci Limit` is registered with `{"directions": ()}` in `STRATEGY_GATES`,
out of the backtest strategy list. The script unmasks it through
`entry_filters.gate_override`, the v103 C pattern.

## The measurement (`scripts/backtest/measure_fib_limit.py`)

The pre-registration document
(`docs/superpowers/results/YYYY-MM-DD-v131-preregistration.md`) quotes this
section, is committed before Stage 0 runs, and the script refuses to run
without it (the v103 `require_committed` pattern).

- **Data:** TRAIN 2010-01-01..2025-12-31, extended cache
  `data/backtest_cache_ext`, universe 74, bullish, all ten horizons.
- **Holdout:** 2026-01-01 to the cache end at the time of the shot. It is
  read only by the Stage 3 call, guarded by the v113 one-shot ledger pattern
  (`check_shot_allowed`).
- **Grid:** six cells, `L ∈ {0.5, 0.618}` × `N ∈ {3, 5, 10}`. Neighbours are
  adjacent values on one axis.
- **Reference arm:** today's `Fibonacci` (market entry on the bounce bar), same
  window and universe, v2 + scale-out. It is reported and never selected.
  Before any cell is read, its TRAIN 2010-01-01..2023-12-31 slice must
  reproduce v103's reference (N=815, WR 36.81%, ExpR +0.2219, universe 73).
  Any difference is explained in a committed note first.

### Stages

| Stage | Window | Rule |
|---|---|---|
| 0 volume (free) | TRAIN | The loosest cell `L=0.5, N=10` needs ≥ 30 fills. Otherwise the mechanism closes as volume-dead, budget intact. |
| 1 selection | TRAIN | Each cell is scored on `funnel.py`'s Tier 1 (WR ≥ 50, ExpR > 0, N ≥ 30, scratch+timeout share ≤ 0.5) and Tier 2 (ExpR > 0, ticker-cluster bootstrap lower bound > 0). The plateau rule applies: a cell and every grid neighbour clear the same tier, Tier 1 tried first, and the winner is the highest ExpR inside the plateau. **Profit clauses, all required of the winner:** (a) ExpR > the reference arm's ExpR; (b) fills ≥ 50% of the reference arm's trade count; (c) WR ≥ the reference arm's WR − 2.0pp. No winner closes the mechanism, budget intact. |
| 2 folds (free) | TRAIN, 13 anchored fold years 2013–2025 | `funnel.py`'s rule: `fold_pick` re-selects on `2010..year−1` with N ≥ 30, a fold qualifies at N ≥ 15, and the stage clears with ≥ 3 qualifying folds and ≥ ⅔ of them positive. Fail closes the mechanism, budget intact. |
| 3 holdout (one shot) | 2026-01-01..cache end | Only the winner, scored at the tier it held on TRAIN, plus profit clause (a) against the reference arm on the same holdout. **Sealed-thin** if fills < 15: the shot is unspent, with one retry once the cache reaches 2026-12-31 (the v104/v113 precedent). |

Total R (`N × ExpR`) is reported for every cell and the reference. It never
gates; the partner chose ExpR plus a volume floor.

**Badge.** Computed alongside and never gating. The `Fibonacci Limit` row
becomes `VALIDATED` only if the winner holds Tier 1 on the holdout. A Tier 2
pass ships the mechanism and leaves the badge `WEAK`. Today's `Fibonacci` row
is not touched.

### Disclosures (never select anything)

- Fill rate per cell, and the split between expired and cancelled unfilled
  orders.
- **Adverse-selection signature:** the share of fills stopped out within 3
  bars of the fill, per cell and for the reference arm.
- How often the 2% cap binds, priced from the limit versus from the reference
  arm's close.
- Same-bar new-high-and-fill count.
- Horizon concentration: the top-2 horizon share against the 80% disclosure
  line.
- Total R per cell.

### Features recorded for B

Each fill's `entry_context` (`edge/context.py` `FEATURE_KEYS`, computed at the
arming bar) is written into the results JSON with the fill bar index, fill
price and outcome. `stop_pct`, `stop_atr` and `planned_rr` are recomputed
from the limit price, not the close, so B reads the geometry the trade
actually had.

**This spec's results document reports no split on any recorded feature.**
B mines them under its own pre-registration. Reporting them here would let
them steer A's verdict.

### Outputs

- `docs/superpowers/results/YYYY-MM-DD-v131-preregistration.md`, committed
  before Stage 0.
- `docs/superpowers/results/YYYY-MM-DD-v131-train.md` (Stages 0–2), plus raw JSON.
- `docs/superpowers/results/YYYY-MM-DD-v131-holdout.md`, only if Stage 3 runs.
- One closed-pre-registrations row in `docs/claude/backtest-methodology.md`
  whatever the outcome.

Runs go to `backtest-runner`, chunked per horizon, with flushed per-ticker
progress and a percent figure past 15 minutes.

## Testing

- **Truncation:** `fibonacci_limit_setups(df.iloc[:t+1])`'s last row equals
  row `t` of the full-frame result, for every cut.
- **Known answers on hand-built frames:**
  - arms at 0.3 retracement
  - does not arm at a retracement ≥ `L` or < 0.236
  - does not arm when the swing high is under 3 bars old
  - does not re-arm the same leg after expiry
  - re-arms on a new leg
- **Simulator cases:**
  - strict trade-through (a touch at the limit does not fill)
  - gap fill at the open
  - new-high cancel before fill
  - same-bar new high plus fill (fill wins)
  - expiry without fill
  - fill at or beyond the stop scores as a scratch
  - fill-bar stop
  - R measured from the fill price
- **Byte-identity witness:** every existing strategy's plans and backtest
  trades are unchanged with the `limit_price` field absent.
- **Script:**
  - refuses to run without the committed pre-registration
  - refuses a holdout read outside Stage 3 or a second shot
  - checks the profit-clause arithmetic against a hand-labelled fixture
- `no-lookahead` skill review of the setup function, the limit-price function
  and the script's feature code.
- Every new or changed function stays under cyclomatic complexity 15.
- One full suite run, as the plan's final task.

## What follows

- **On a holdout pass:** a live-wiring spec covering `PlanManager` limit fills
  and cancels, the resting-order alert line (`instructions.py` already carries
  "BUY LIMIT"), and v93 shadow soak for `Fibonacci Limit`.
- **B, a Fibonacci meta-label rule:** mined offline from the features recorded
  here and frozen as a readable config rule, never a model in the live path.
  It gets its own spec and pre-registration, whatever A's verdict.
- **Limit on the anchored leg:** only if v124 arm 1 passes. The same mechanism,
  drawn on `fib_leg.impulse_leg`.

## Non-goals

- No change to today's `Fibonacci` signal, plan, badge row or alerts.
- No re-run of any closed Fibonacci row. This is a new mechanism (entry
  mechanics), not a retune of v84/v101–v104/v113.
- No bearish arm.
- No friction model. The strict trade-through fill is the only conservatism,
  and that is disclosed as a limitation in the results.
- No selection from disclosure columns or recorded features.

## Parallelisation

- **Group 1 (parallel):** two tasks with disjoint files and no shared
  contract.
  - the setup function and its tests (`entry_filters.py`, new test file)
  - the simulator pre-fill cancel and strict fill (`exit_sim.py`,
    `lifecycle.py`, the simulator test file)
- **Sequential:**
  - The `limit_price` plan-shape field (`params.py`, `builders.py`,
    `backtest.py`) comes after Group 1. It consumes both the setup function's
    frozen prices and the simulator's cancel input.
  - The masked `Fibonacci Limit` registration (`strategy_types.py`,
    `entry_filters.py`) comes after the shape field, because it registers into it.
  - The measurement script comes after the registration.
  - The pre-registration commit comes before any Stage 0 run.
  - The Stage 0–2 runs, the Stage 3 shot and the results rows are a chain, each
    gated on the previous verdict.
  - The full suite runs last.
