# Features — the growth playbook

How the account is meant to compound, and the rules that govern sizing as it does.

Part of the features documentation — index at [features.md](features.md).

## The growth playbook

Written for future-you, reading this in a drawdown, wondering if any of it
still works.

**The equation.** Every closed trade multiplies equity by
`1 + risk_pct/100 * expectancy_r` (`swingbot/core/edge/growth.py`). Risk 1%
per trade at +0.10R expectancy and equity grows ~0.1% per trade —
compounding to 10x takes `ln(10) / ln(1.001)` ≈ 2303 closed trades. There is
no shortcut past this arithmetic. `!growth` (`growth_report()`) prints it
straight from your actual closed-trade history: current expectancy, trades
per month, current multiple, and the ETA to your target at the pace you're
actually trading at — never a projection dressed up as a promise.

**The three honest levers**, and which feature moves which:
- **Expectancy** — the strategy/entry-filter layer (`entry_filters.py`,
  `strategy_types.py`'s `STRATEGY_GATES`), every plan's target-selection band
  (`config.MIN_RISK_REWARD_RATIO`/`MAX_RISK_REWARD_RATIO`, the nearest real
  level a plan's target may land on — see Plan Engine v2 below), the
  quality scoring in `quality.py` that scores every plan 0-100, and the validation
  registry (`swingbot/core/backtesting/registry.py`) that badges which strategies have
  actually earned trust out-of-sample. Nothing here can invent edge that
  isn't real — E33's component-adoption process ran, found zero components
  that cleared the pre-registered fold gate, and adopted zero. That's not a
  failure of the process; it's the process refusing to fabricate edge.
- **Frequency** — the universe you scan (`SCAN_UNIVERSE`, `scripts/
  build_universe.py`), alert-flood control (`cap_alerts`/
  `MAX_ALERTS_PER_SCAN`) so a wider universe doesn't drown you, and the
  weekend deep scan (`weekend_deep_scan`) surfacing forming setups for
  Monday. More valid signals per month directly shortens the ETA above —
  but only if expectancy holds up at the wider scope (see E80's honest
  finding: Support/Resistance's edge carried over to an ETF-only universe,
  Break & Retest's didn't).
- **Survival** — heat/sector/correlation caps (`edge/heat.py`,
  `edge/correlation.py`), the drawdown throttle and kill switch below, and
  per-horizon capacity budgeting (`horizon_check`). A 10x path that gets
  wiped out at 3x isn't a 10x path. This lever doesn't make you money; it's
  what lets the other two levers keep compounding instead of restarting
  from zero.

**The drawdown throttle ladder** (`edge/throttle.py`'s `DD_LADDER`, frozen
constants) exists so a losing streak's math doesn't get compounded by a
tilted operator's judgment on top of it:

| Current drawdown | Position size multiplier |
|---|---|
| < 8% | 1.00x (normal) |
| > 8% | 0.75x |
| > 12% | 0.50x |
| > 16% | 0.25x |
| > 20% | 0.00x (paused — no new entries) |

Once paused, entries don't resume at the first green day — drawdown has to
recover back *below 15%* first (`RESUME_DD_PCT`, hysteresis against
whipsawing the throttle on/off around the 20% line). **Do not override
this by hand.** A drawdown is exactly the moment every cognitive bias
pushes toward "one more trade to get it back" — the ladder is code
specifically so that decision never has to be made under pressure. If you
genuinely believe a rung is wrong, that's a deliberate `.env` edit to
`DD_LADDER`'s constants (a code change, reviewed sober, not a live
override), never a one-off bypass during an actual drawdown. The weekly
risk report calls out any operator override, on purpose.

**The quarterly re-validation ritual** (`scripts/backtest/quarterly_revalidation.py`,
Task E96): the first weekend of January, April, July, and October, run it,
read every line it prints, and prune anything it flags DEGRADED. It's
deliberately a human-run script, not a cron job — a re-validation result
that nobody reads is worse than not re-validating at all. Put a real
calendar reminder on those four weekends; this system's edge is measured
against 2018-2023 data; it will not stay valid forever without someone
periodically checking that it still is.

**Reading the Monte Carlo fan** (`!portfolio`'s fan chart,
`edge/ruin.simulate` over your real closed-trade R-multiples): the shaded
band is P25–P75 of simulated equity paths, the dotted outer lines are
P5/P95, and the solid line is the median. The chart title gives you
`p(10x)`, `P95 max drawdown`, and `p(halve)` (probability equity ever
drops below 0.5x — `RUIN_THRESHOLD`) in one line. **The P5 path is a real
future too** — not a scare tactic, not a worst-case decoration. It's drawn
from the same distribution as the median path, just less likely. If you
wouldn't be able to stay in the system through the P5 path, you're sized
too aggressively for your own actual risk tolerance, regardless of what
the median promises.

**Why this will never promise 100% win rate, and what it promises
instead.** No strategy in the validation registry clears 100% WR, and one
that claimed to would be reporting on too small a sample to trust (see
`docs/superpowers/results/2026-07-validation.md`'s honest note that three
strategies which passed TRAIN flipped to FAIL on out-of-sample data). The
actual promise this system makes is narrower and more defensible:
pre-registered evidence (a strategy is trusted only after clearing gates
it didn't know about in advance, on data it hadn't seen), a visible ETA
(`!growth` never hides the sample size or dresses up a small-N result as
confident), and bounded ruin (the heat caps and throttle ladder mean a bad
month costs you a throttled month, not the account). That's the whole
deal: an honest number and a system that can't quietly become a bigger bet
than you agreed to.
