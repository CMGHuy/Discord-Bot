# v180 — Turtle Soup entry: the screened sweep-and-reclaim as a masked strategy with a structural stop

**Version:** ui 1.32.0 · bot 2.13.0 (at writing)
**Bump:** bot patch — a masked strategy, an inert research knob and an acceptance-instrument statistic; no alert, plan or screen changes for anyone until the arm passes the one-shot VALIDATION, and promotion after that is its own change.
**Edge:** expectancy — adds a long entry on a trigger that passed the idea screen. The screen measured paired ΔExpR +0.316R [+0.254, +0.381], N = 10,438, PIT S&P 500 2011–2019, yfinance bars, fixed 1.5/3 ATR race. That evidence covers the **trigger only**: the structural plan shape tested here was never screened. Prediction: the arm's added rows show a positive but small ExpR and a win rate below the book's; the base case is a fail on the win-rate clause, and a pass is the upside case.
**Screen:** screen-turtle_soup SCREEN-PASS
**Panel:** quant-researcher, veteran-trader, technical-analyst
**Status:** spec written 2026-10-21 from a chat with the partner. They shared six Daiken/BigWhale "6 steps to read a chart" pages and asked which lessons could find better trades, which led to two one-shot screens (commits c03b5143, dcec1f49). The partner chose to spec Turtle Soup with two arms. After the panel showed the screened shape cannot meet the win-rate gate, the partner chose to keep only the structural arm (revised the same day; see Panel review).

## Why

The pages teach a six-step read: structure, trend, zone, liquidity, confirmation, then the plan. Step 4 is the liquidity sweep: price trades under an old low, then closes back above it. Step 5 says the sweep alone is not enough, and to wait for a break of structure.

The screens measured both claims on the point-in-time S&P 500, 2011–2019, yfinance bars, after costs. Each event was paired against 20 random bars from the same ticker, month and trend state:

| Idea (frozen trigger) | N | Paired ΔExpR [95%] | Years positive | Verdict | Results doc |
|---|---|---|---|---|---|
| `turtle_soup`: low < prior 20-bar low, that low ≥ 4 bars old, close back above it | 10,438 | **+0.316R** [+0.254, +0.381] | 9/9 | SCREEN-PASS | `docs/superpowers/results/2026-10-21-screen-turtle_soup.md` |
| `sweep_reclaim_bos`: the same idea plus a close above the last swing high within 10 bars | 5,317 | −0.162R [−0.222, −0.099] | 0/9 | SCREEN-FAIL | `docs/superpowers/results/2026-10-21-screen-sweep_reclaim_bos.md` |

The sweep carries the edge. Waiting for the break of structure buys after most of the rebound and turns the trade negative. On daily swing bars, step 5 of the pages is backwards, so this spec builds the step-4 entry and nothing from step 5.

Read the pass with care:

- **The absolute ExpR is small.** The event book's absolute ExpR was +0.07R against a null of −0.25R. Most of the gap is the null losing, because these events cluster where the stock has been falling.
- **The screened shape has a low win rate.** Under the screen's own exits, decided trades (target or stop) won 1,842 / 6,346 = **29.0%**, below the 33.3% break-even at R:R 2.0. 39.2% of trades timed out, and those timeouts carry the result.

A pass buys a spec, not a verdict (`backtest-methodology.md` § Stage −2).

### Why only one arm

The partner first asked for two arms: A, the screened 1.5/3 ATR shape, and B, a structural stop with a level-map target. Arm A is **closed without a run**. Its 29% decided win rate cannot clear the acceptance gate's win-rate clause or the strategy badge's `win_rate >= 50` floor, and running it would spend effort on a known answer. No ledger row is written for arm A, because nothing was measured beyond the screen.

## What gets built

### 1. The signal (frozen; parity with the screen is the contract)

A new entry function, `Turtle Soup`, is registered in `ENTRY_FUNCS` (`swingbot/core/market/entry_filters.py`). It is bullish only, and its bearish series is always False. Bar `t` is a signal when all three conditions hold, reading bars `<= t` only:

- `Low[t] < L`, where `L` is the minimum Low of bars `t-20 .. t-1`.
- The **latest** bar in that window holding `L` is at least 4 bars before `t`.
- `Close[t] > L`.

These are `turtle_soup.PARAMS` (`channel = 20`, `min_age = 4`). The screen module `swingbot/core/backtesting/screen/ideas/turtle_soup.py` is frozen; it is never edited, and live code never imports it. Live code must not depend on the backtesting package, so the live function is its own implementation.

**Parity tests (required by the v140 spec):**

- **Bar-for-bar equality.** The live bullish series equals `turtle_soup.events(df)` bar for bar on:
  - the screen tests' random-walk frames (`tests/backtesting/screen/helpers.random_walk`, several seeds and lengths);
  - the turtle-soup screen fixture;
  - **an explicit equal-lows fixture**: an old `L` repeated at `t-3`, so the latest-bar tie rule decides the event.

  A test-only import of the screen module is fine.
- **No lookahead.** A prefix-stability test pins it on the live function (`no-lookahead` skill).

No trend filter, volume filter, zone requirement or short mirror is added. Each would change the trigger, which makes it a new idea that needs its own screen.

### 2. Masked by default

`STRATEGY_GATES["Turtle Soup"] = {"directions": ()}`: no live scan, shadow pass, alert or backtest default ever runs it. It stays out of `backtest.ALL_STRATEGIES`. It runs only inside a scoped research cell `("bullish", "2w")` while the research knob is on, using the v119 pattern (`strategy_engine.RESEARCH_CELL`, a scoped `gate_override`).

The horizon is `2w` (the "1-2 week swing" slot), because the screen's frozen time cap is 10 bars. The plan confirms that `2w`'s `max_holding_days` admits a 10-session hold.

### 3. The plan shape (research knob `TURTLE_SOUP_RESEARCH_MODE` ∈ `{off, structural}`, default `off`)

The knob is registered in the reachability registry (`arms/reachability.py`) and in `measure_arms.py` the way `COMPRESSION_SHORT_RESEARCH_MODE` is.

Every level is an **absolute price known at the signal close**, so the alert can be entered as orders before the open:

| Leg | Rule |
|---|---|
| Entry | market-on-open, the next session |
| Stop | `Low[t] − STRUCTURE_BUFFER_ATR (0.25) × ATR14[t]`, via `_bounded_stop` |
| Target | `plan_engine.select_structural_target` from the level map, inside the frozen 1.5–2.5 R:R band (measured from the signal close as the planning reference). **No plan** when no level falls in the band. |
| Exit | a **single whole-position leg**: no TP1 scale-out, no breakeven move, no runner. A **10-session hold cap**, with the fill bar as session 1 (`exit_sim._hold_cap_bars` semantics); the cap closes at that session's close. |
| Gaps | the live fill policy for a gap through stop or target. |

ATR14 is the planning stack's Wilder ATR14 on bars `<= t`.

Entry-side rules, applied at the fill:

- **Open at or below the stop:** no trade. The plan is cancelled and counted (`cancelled_open_through_stop`).
- **Risk cap: drop, never squeeze.** Turtle Soup is in the structural-stop scope. A stop farther than the `2w` horizon's `max_risk_pct` (3.0%) from the **fill price** drops the plan. It is never pulled closer, because a moved stop is a different trade. Dollar risk stays ≤ 2% through position sizing (`risk_sizing_ok`; the partner's rule is that the 2% cap limits money at risk, not stop distance).
- R is measured from the fill price to the stop.

**Frictions:** the funnel prices trades with the live `swingbot/core/edge/frictions.py`, unchanged. The screen's 5 bps a side plus 0.02R commission is the reference.

### 4. The acceptance amendment (adopted from v119 before any outcome exists; it relaxes no threshold)

The standard v72 instrument cannot see an additive new strategy:

- `delta_standardised_win_rate` weights strata by the baseline's `(strategy, horizon)` mix and drops strata the baseline lacks (`swingbot/core/backtesting/acceptance.py:129-154`). Turtle Soup's `("Turtle Soup", "2w")` stratum is therefore weightless, and ΔWR is exactly 0 in every draw.
- Clause 5 and the Stage 0 MDE inherit that zero.

v119 found the same defect and wrote this amendment (`docs/superpowers/results/2026-10-01-v119-compression-short-preregistration.md`, A1–A4), but it was never implemented. v180 adopts it verbatim and builds it:

- **A1, clause 1 instrument.** Pooled (unstandardised) ΔWR over decided trades, `WR(component) − WR(baseline)`.
  - Bootstrap: the same ticker-cluster bootstrap, 10,000 resamples, seed 42.
  - Pass: point > 0 **and** one-sided p < 0.05.
- **A2, clause 5 instrument.** `permutation_test.py`'s circular entry shift, n = 200, seed 42, with the A1 statistic. Pass: p < 0.05 at VALIDATION. A missing p is a FAIL.
- **A3, Stage 0 MDE statistic.** `mde_paired` with the A1 statistic. The TRAIN effect compared against it is the A1 point estimate on fold-train.
- **A4, no other change.** Thresholds, windows, the bootstrap, and clauses 2, 3, 4 and 6 are as written in `backtest-methodology.md` § Acceptance gate. Clause 3 is applied, and a geometry failure is not waived because the plan shape differs. Clause 6 is `SKIPPED` (not a subset feature).

The instrument code is a selectable statistic in `validate_component.py`, `backtest_wf.gate_win_rate` and the permutation harness. It is built as its own reviewed task, with tests. **Until it is committed, no MDE, selection, fold or VALIDATION run may start.**

## The funnel (pre-registered here; nothing below changes once TRAIN is read)

- **Data source:** `--data-source alpaca`, named in the frozen block of the pre-registration results doc before any TRAIN bar is read (v162 rule). The screen ran on yfinance bars. The source change is disclosed, and it decides nothing.
- **Producer:** `scripts/backtest/measure_arms.py`, engine `strategy`, the standard instrument plus the A1–A3 statistic (no bespoke instrument).
  - Baseline arm: knob `off` (every existing strategy, no Turtle Soup).
  - Component arm: knob `structural` (the same rows plus Turtle Soup).
  - A fixture proves that the baseline rows are a subset of the component rows, so no other strategy's row moves.
- **Universe:** the producer's standard cached universe with PIT membership per signal date. Any name outside the S&P 500 is an unscreened universe; it is reported as a share of added rows, never excluded after the fact.

| Stage | Rule |
|---|---|
| −1 reachability | knob reachable and nonzero changed outcomes on the pilot, else refused (budget intact) |
| 0 MDE | A3: paired ticker-cluster MDE of the A1 pooled ΔWR on fold-train. A TRAIN A1 point estimate below MDE refuses the shot (budget intact) |
| 1 selection | **tests nothing.** One cell, no grid; `plateau_report()` on a one-element grid always returns a plateau. It is stated, not counted as evidence |
| 2 walk-forward | `gate_win_rate` with the A1 statistic: ≥ 2 of 3 folds improving, no fold worse than −1.0pp. Per-fold N ≥ 30 counts **added Turtle Soup trades**, not the pooled book |
| 3 VALIDATION | one shot: all six clauses with A1/A2, **and** the strategy badge check on the added rows (`win_rate >= 50` over win+loss, `expectancy_r > 0`, VALIDATION N ≥ 15, scratches + timeouts ≤ 50%; `backtest-methodology.md` § Badge scoring). The time-cap exits count as timeouts |

**Reported at every stage that runs** (descriptive, never gating):

- **Drop and cancel counts by reason, as shares of signals:**
  - risk cap;
  - no level in band;
  - open through the stop;
  - each excluded population's screen-style outcome, so a filtered population can be read against the screen pass.
- **Sweep depth** `(L − Low[t]) / ATR14[t]` per signal, plus its distribution for kept and dropped plans.
- **Early stops:** the share of trades stopped within 2 sessions.
- **Exit mix:** target / stop / gap / time-cap shares, and the decided win rate.
- **Regime:** ExpR and win rate split by SPY above/below its 200-day SMA.
- **Signal clustering:** maximum and p95 Turtle Soup signals per day.
- **Universe:** the added-row share outside the S&P 500.

**Ledger:** one row, `v180-turtle-soup-structural`, written when its last stage is decided.

## If the arm passes VALIDATION

Nothing ships from this spec. A pass licenses a follow-on change that:

- unmasks Turtle Soup in `STRATEGY_GATES` for `("bullish", "2w")` with this plan shape;
- enters the v93 shadow soak (`STRATEGY_ALERTS_MODE=shadow`), and is promoted through `STRATEGY_ALERTS_LIVE_STRATEGIES` only after the soak;
- defines the day-10 **time-exit alert** (`swingbot/core/planning/time_exit.py`), so no position is left unattended;
- writes the **explain text and chart overlay**:
  - The explain text says it plainly: "closed back above the 20-bar low set N bars ago; enter at the open". This is the close-confirmed reading, not Connors and Raschke's intraday buy stop.
  - The overlay draws `L` and the sweep bar's Low.
- keeps Turtle Soup **out of the confluence count** next to an S/R-support signal off the same low, because they are not independent evidence;
- gets a fundamental-analyst review of earnings and OPEX inside the 10-session hold (`swingbot/core/market/events.py`), and a risk-manager review of correlated exposure on clustered signal days;
- bounds the live scope to the watchlist's liquidity floor.

The badge comes from the validation registry, as for every strategy.

## If the arm fails

The spec closes as `no-lift`. The screen pass stays in the ledger as measured. Turtle Soup never re-enters the funnel under this shape, and the screened shape is closed above (one shot per component).

## Non-goals

- Arm A, the screened 1.5/3 ATR shape: closed without a run (above).
- The `sweep_reclaim_bos` chain: closed SCREEN-FAIL.
- A short-side mirror (a sweep of a swing high). It would need its own screen.
- The hourly entry trigger, which is parked. The cache holds hourly bars for only 2 tickers, starting Dec 2023, so it cannot be screened.
- Partial exits, runners or trailing stops on Turtle Soup trades. That is a later `harvest` question, only after the arm is live.
- Any change to the frozen screen module or its ledger row.
- Any change to an acceptance threshold. The amendment changes only which statistic sees an additive arm.

## Anti-goals

- Tuning `channel`, `min_age`, the stop buffer, the R:R band or the hold cap after any result is read. Each one is a new idea.
- Reviving arm A after arm B's result is known.
- Squeezing a wide stop to fit the cap.
- Starting any MDE, fold or VALIDATION run before the A1–A3 instrument is committed.

## Left to the plan

- Where the live signal function lives, and how arm B's stop reads the sweep bar's Low (the signal bar's own Low, so no extra state is needed).
- How the single-leg plan is expressed in `TradePlanV2` and `simulate_exit`. The compression short's single-leg path is the precedent.
- Whether the screen's "time cap 10 bars" and `_hold_cap_bars` count sessions the same way (a quant-engineer check). If they differ, the plan follows `_hold_cap_bars`, and the results doc says so.
- The fixture that proves the baseline rows are untouched.

## Panel review

Spec review on 2026-10-21 by quant-researcher (opus), veteran-trader (sonnet) and technical-analyst (sonnet), against c9da779b. Two findings were BLOCKING; the rest were ADVISORY. Findings shared between roles are merged, citing every source.

- quant-researcher (BLOCKING): the standardised ΔWR is blind to an additive new strategy, so clauses 1 and 5 and the MDE fail by construction — **applied**: the v119 A1–A4 amendment is adopted and built before any run (§ 4).
- quant-researcher (BLOCKING): the MDE statistic and the per-fold N population were unstated — **applied**: the MDE uses the A1 statistic, and per-fold N counts added Turtle Soup trades.
- quant-researcher: arm A's decided win rate is 29% under the screen's exits, below break-even, and cannot reach the badge floor — **applied**: the partner dropped arm A; the Edge prediction now names the win-rate risk.
- quant-researcher + veteran-trader + technical-analyst: the 3% cap and arm B's level requirement filter events the screen never filtered — **applied**: drop shares by reason are reported, with each excluded population's screen-style outcome.
- quant-researcher: the screen evidence does not cover the structural shape — **applied**: stated in Edge and Why.
- quant-researcher: Stage 1 on a one-cell grid tests nothing — **applied**: stated in the stage table.
- quant-researcher: +0.316R was quoted without window, N and source, and the yfinance → Alpaca change was undisclosed — **applied**: Edge line and data source.
- quant-researcher: the rule for picking between two arms was unspecified — **applied (moot)**: one arm.
- quant-researcher: the multiple-comparison count was not stated — **applied**: two ideas were screened on 2026-10-21 (BH q in each results doc), and one arm enters the funnel.
- quant-researcher: hold-cap parity — **applied**: left to the plan as a quant-engineer check.
- veteran-trader: stop and target written as "entry ± k ATR" cannot be placed before the open — **applied**: arm B's levels are absolute at the signal close; entry is market-on-open.
- veteran-trader: entry-side gap through the stop, and the risk-cap reference — **applied**: an open at or below the stop cancels the plan; the cap is measured from the fill.
- veteran-trader: frictions — **applied**: the live `frictions.py`.
- veteran-trader: arm B whipsaw and no-level filter — **applied**: early-stop share and no-level share are reported. This is a prediction, not a change.
- veteran-trader: time-exit alert — **applied**: a follow-on obligation.
- veteran-trader: regime split and signals per day — **applied**: reported.
- veteran-trader: earnings and OPEX in the hold — **applied**: a follow-on fundamental-analyst review.
- veteran-trader: liquidity and live universe — **applied**: the unscreened-universe share is reported; the live scope is a follow-on.
- technical-analyst: log sweep depth in ATR — **applied**.
- technical-analyst: say "close-confirmed, enter at open" in the explain text and overlay — **applied**: a follow-on obligation.
- technical-analyst: equal-lows tie fixture for parity — **applied**.
- technical-analyst: confirm `2w` admits a 10-session hold — **applied**: a plan check.
- technical-analyst: no double counting with an S/R-support signal in confluence — **applied**: a follow-on obligation.
- technical-analyst: no closed pre-registration covers this mechanism — confirmation, no change.
