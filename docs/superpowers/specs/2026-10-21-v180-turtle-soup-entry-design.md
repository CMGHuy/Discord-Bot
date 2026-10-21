# v180 — Turtle Soup entry: the screened sweep-and-reclaim as a masked strategy, two exit arms

**Version:** ui 1.32.0 · bot 2.13.0 (at writing)
**Bump:** bot patch — a masked strategy and an inert research knob; no alert, plan or screen changes for anyone until an arm passes the one-shot VALIDATION, and promotion after that is its own change.
**Edge:** expectancy — adds a long entry whose screen measured +0.316R paired lift over matched random bars (9/9 years). Prediction: far smaller in the funnel (measured TRAIN→out-of-sample shrinkage has run 50–60%, and the screen's absolute event ExpR was only +0.07R); the base case is that one arm clears Stage 2 at a modest lift and the other does not.
**Screen:** screen-turtle_soup SCREEN-PASS
**Panel:** quant-researcher, veteran-trader, technical-analyst
**Status:** spec written 2026-10-21 from a chat with the partner. They shared six Daiken/BigWhale "6 steps to read a chart" pages and asked which lessons could find better trades. That led to two one-shot screens (commits c03b5143, dcec1f49): the pages' full chain (sweep → reclaim → BOS) failed, and the sweep-and-reclaim alone (Turtle Soup) passed. The partner chose to spec Turtle Soup and to test two stop/target shapes as separate arms.

## Why

The pages teach a six-step read: structure, trend, zone, liquidity, confirmation, then the plan. Their step 4 is the liquidity sweep: price trades under an old low, then closes back above it. Their step 5 says the sweep alone is not enough, and to wait for a break of structure.

The screens measured both claims on the point-in-time S&P 500, 2011–2019, after costs, each event paired against 20 random bars from the same ticker, month and trend state:

| Idea (frozen trigger) | N | Paired ΔExpR [95%] | Years positive | Verdict | Results doc |
|---|---|---|---|---|---|
| `turtle_soup`: low < prior 20-bar low, that low ≥ 4 bars old, close back above it | 10,438 | **+0.316R** [+0.254, +0.381] | 9/9 | SCREEN-PASS | `docs/superpowers/results/2026-10-21-screen-turtle_soup.md` |
| `sweep_reclaim_bos`: the same idea plus a close above the last swing high within 10 bars | 5,317 | −0.162R [−0.222, −0.099] | 0/9 | SCREEN-FAIL | `docs/superpowers/results/2026-10-21-screen-sweep_reclaim_bos.md` |

The sweep carries the edge. Waiting for the break of structure buys after most of the rebound and turns it negative. On daily swing bars, step 5 of the pages is backwards; this spec builds the step-4 entry and nothing from step 5.

Read the pass with care. The event book's absolute ExpR was +0.07R, and the matched null's was −0.25R. Most of the gap is the null losing, because these events cluster where the stock has been falling. That is still a real conditional edge: the alternative in that state is a losing bar. But it is a reason to expect a small number in the funnel, not +0.3R.

A pass buys a spec, not a verdict (`backtest-methodology.md` § Stage −2). Turtle Soup now runs the acceptance funnel unchanged.

## What gets built

### 1. The signal (frozen; parity with the screen is the contract)

A new entry function, `Turtle Soup`, registered in `ENTRY_FUNCS` (`swingbot/core/market/entry_filters.py`). It is bullish only; the bearish series is always False. Bar `t` is a signal when all three hold, reading bars `<= t` only:

- `Low[t] < L`, where `L` is the minimum Low of bars `t-20 .. t-1`;
- the latest bar in that window holding `L` is at least 4 bars before `t`;
- `Close[t] > L`.

These are `turtle_soup.PARAMS` (`channel = 20`, `min_age = 4`). The screen module `swingbot/core/backtesting/screen/ideas/turtle_soup.py` is frozen and is **not** edited or imported by live code. Live code must not depend on the backtesting package, so the live function is its own implementation.

**Parity test (required by the v140 spec):** on the screen tests' random-walk frames (`tests/backtesting/screen/helpers.random_walk`, several seeds and lengths) and on the turtle-soup screen fixture, the live bullish series equals `turtle_soup.events(df)` bar for bar. A test-only import of the screen module is fine. A prefix-stability test also pins no-lookahead on the live function (`no-lookahead` skill).

No trend filter, volume filter, zone requirement or short mirror is added. Each would be a changed trigger, which makes it a new idea that needs its own screen.

### 2. Masked by default

`STRATEGY_GATES["Turtle Soup"] = {"directions": ()}`: no live scan, shadow pass, alert or backtest default ever runs it. It stays out of `backtest.ALL_STRATEGIES`. It runs only inside a scoped research cell `("bullish", "2w")` while the research knob below is on, using the v119 pattern (`strategy_engine.RESEARCH_CELL`, a scoped `gate_override`).

Horizon `2w` (the "1-2 week swing" slot) because the screen's frozen time cap is 10 bars.

### 3. Two plan shapes, one research knob

New config field `TURTLE_SOUP_RESEARCH_MODE` ∈ `{off, screen, structural}`, default `off`. It is registered in the reachability registry (`arms/reachability.py`) and in `measure_arms.py` the way `COMPRESSION_SHORT_RESEARCH_MODE` is.

Both arms share:

- the signal;
- the entry reference: the next session's open, as in the screen race;
- a **single whole-position leg**: no TP1 scale-out, no breakeven move, no runner. The screen trade had none, and adding them would make the arms differ from the screen in more than the stop and target;
- a **10-session hold cap**, with the fill bar as session 1 (`exit_sim._hold_cap_bars` semantics);
- the live fill policy for gaps through a level.

They differ only in stop and target:

| Arm (knob value) | Stop | Target |
|---|---|---|
| A `screen` | entry − 1.5 × ATR14 at the signal bar | entry + 3.0 × ATR14 at the signal bar (R:R 2.0) |
| B `structural` | the sweep bar's Low − `STRUCTURE_BUFFER_ATR` (0.25) × ATR14, via `_bounded_stop` | `plan_engine.select_structural_target` from the level map, inside the frozen 1.5–2.5 R:R band; no plan when no level falls in the band |

ATR14 is the planning stack's Wilder ATR14 on bars `<= t`. The screen's own indicator is not imported; it is the same definition.

**The risk cap: drop, never squeeze.** Both arms treat Turtle Soup as in the structural-stop scope. A stop farther than the `2w` horizon's `max_risk_pct` (3.0%) from entry **drops the plan**; it is never pulled closer, because a moved stop is a different trade from the one tested. Dollar risk stays ≤ 2% through position sizing (`risk_sizing_ok`, the partner's rule that the 2% cap limits money at risk, not stop distance). In each arm, the dropped-plan count is reported in the results doc.

## The funnel (pre-registered here; nothing below changes once TRAIN is read)

- **Data source:** `--data-source alpaca`, named in the frozen block of the pre-registration results doc before any TRAIN bar is read (v162 rule).
- **Producer:** `scripts/backtest/measure_arms.py`, engine `strategy`, standard instrument (no bespoke instrument). Baseline arm: the knob `off` (every existing strategy, no Turtle Soup). Each component arm: the same rows plus Turtle Soup under that knob value. A fixture proves the baseline rows are a subset of the component rows: no other strategy's row moves.
- **Each arm is decided on its own.** No pooled result may admit, rescue or fail the other arm (v119 precedent).

| Stage | Applied per arm |
|---|---|
| −1 reachability | knob reachable, and nonzero changed outcomes on the pilot, else refused (budget intact) |
| 0 MDE | paired ticker-cluster MDE on fold-train; an effect below MDE refuses the shot (budget intact) |
| 1 selection | one cell per arm, no grid; `plateau_report()` runs over the single cell and must not flag it |
| 2 walk-forward | `gate_win_rate`: ≥ 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N ≥ 30 |
| 3 VALIDATION | **at most one arm, one shot**: all six acceptance clauses (`backtest-methodology.md` § Acceptance gate) |

**Which arm reaches VALIDATION:** only arms that pass Stage 2 qualify. If both do, the one with the higher pooled fold-test ΔExpR goes (expectancy first, `edge-priorities.md`); a tie goes to arm A, the screened shape. The other arm is recorded as "passed Stage 2, not validated" and is closed: it never gets a validation shot later. This keeps the two-arm search to one draw on the budget.

**Ledger:** one row per arm (`v180-turtle-soup-screen`, `v180-turtle-soup-structural`), written when its last stage is decided.

## If an arm passes VALIDATION

Nothing ships from this spec. A pass licenses a follow-on change that unmasks Turtle Soup in `STRATEGY_GATES` for `("bullish", "2w")` with the passing arm's plan shape, enters the v93 shadow soak (`STRATEGY_ALERTS_MODE=shadow`), and is promoted through `STRATEGY_ALERTS_LIVE_STRATEGIES` only after the soak. The badge comes from the validation registry as for every strategy.

## If no arm passes

The spec closes as `no-lift`. The screen pass stays in the ledger as measured. Turtle Soup never re-enters the funnel under either shape (one shot per component).

## Non-goals

- The `sweep_reclaim_bos` chain (closed SCREEN-FAIL).
- A short-side mirror (sweep of a swing high); it would need its own screen.
- The hourly entry trigger, which is parked: the cache holds hourly bars for 2 tickers from Dec 2023 only, so it cannot be screened.
- Partial exits, runners or trailing stops on Turtle Soup trades: a later `harvest` question, only after an arm is live.
- Any change to the frozen screen module or its ledger row.

## Anti-goals

- Tuning `channel`, `min_age`, the ATR multiples or the hold cap after any result is read. Each is a new idea.
- A validation run for the second arm "because it also passed Stage 2".
- Squeezing a wide stop to fit the cap.

## Left to the plan

- Where the live signal function lives and how it shares the sweep-low value with arm B's stop (the bar's own Low; no extra state needed).
- How the single-leg exit is expressed in `TradePlanV2` and `simulate_exit` (the compression short's single-leg path is the precedent).
- The fixture that proves baseline rows are untouched.
