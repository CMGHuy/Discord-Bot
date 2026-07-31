# Gatekeeper v7 — red-flag ablation (TRAIN folds)

Run: `python scripts/gate_fold_run.py --all --ablate` · 2026-07-31 ·
per strategy: annotate-only `run_folds`, then `ablate_flags` pooled + once
per fold (2021/2022/2023). Same 78-ticker/anchored-TRAIN/2w-horizon replay
as G97/G98.

**How to read `expectancy_delta`:** it is `expectancy_r(trades with the flag's
signals REMOVED) - expectancy_r(all trades, baseline)`. **Positive** =
removing what the flag catches improves expectancy (the flag is doing its
job — it earns its keep). **Negative** = removing those trades makes
expectancy *worse*, i.e. the flag is disproportionately firing on trades
that were actually fine — the flag is anti-predictive for this strategy/fold.
`n_kept`/`signals_removed_pct` describe the remaining pool after removal, not
the flagged trades themselves. A fold with no row for a given flag means the
flag never fired in that fold (nothing to ablate there) — that is different
from `expectancy_delta == 0.0`, which means it fired but changed nothing.

Only the flags this fixed-2w-horizon replay actually observes firing appear
below: `rf_stop_sweep` (applies to every strategy), `rf_fake_breakout`
(Break & Retest / Support/Resistance / Volume Profile — only Break & Retest
had trades), and `rf_divergence_trap` (RSI Divergence only). The other five
registered red flags (`rf_dead_cat`, `rf_extreme_fade`, `rf_news_whipsaw`,
`rf_thin_session`, `rf_beta_move`) never fired a single `fail` in this replay
— `rf_news_whipsaw`/`rf_thin_session`/`rf_beta_move` need macro/SPY context
this fold runner's `_default_replay` does not supply (see `folds.py`'s own
docstring), so they are structurally silent here, not evidence they never
fire live.

## rf_stop_sweep (all 6 strategies with any trades)

| Strategy | Pooled Δexp | 2021 Δexp | 2022 Δexp | 2023 Δexp |
|---|---|---|---|---|
| EMA Crossover | -0.005 | — (didn't fire) | — (didn't fire) | -0.11 |
| Fibonacci | -0.035 | -0.007 | — (didn't fire) | -0.056 |
| RSI | 0.0 | 0.0 | None (n_kept=0) | — (didn't fire) |
| MA Ribbon | -0.033 | -0.011 | — (didn't fire) | -0.051 |
| Break & Retest | +0.015 | -0.044 | None (n_kept=0) | +0.111 |
| RSI Divergence | -0.027 | -0.007 | -0.023 | -0.058 |

Fold-level tally (excluding "didn't fire" and `None`/undefined rows): **9
folds negative, 1 fold positive (Break & Retest 2023, n_kept=4 — thin), 1
fold flat (RSI, n_kept=1)**. Every strategy with a real pooled sample
(Fibonacci N=41, MA Ribbon N=69, RSI Divergence N=163) shows `rf_stop_sweep`
*hurting* expectancy in every fold where it had a non-trivial sample. This
clears the pre-registered bar (negative in ≥ 2 folds) by a wide margin —
9 negative fold-observations across 5 strategies, not a fluke in one
strategy's noise.

**Demotion: `rf_stop_sweep` registry weight set to 0 (info-only)** in
`swingbot/core/gate/redflags.py` — see the commit that pairs with this doc.
The check still runs and still reports on the checklist (so the operator
still sees "stop-sweep detected" as information), it simply no longer
contributes to the 0-100 score or tier assignment. Reading: this replay's
`rf_stop_sweep` detector disproportionately fires on trades that went on to
win, i.e. what it calls a "stop-sweep wick with no follow-through" is, in
this backtest population, more often a shakeout that resolves in the
signal's favor than a genuine failed setup. That is a property of *this*
detector's current thresholds against *this* strategy population, not a
claim that stop-sweeps are never real — G99 pins today's evidence, a future
task can retune `wick_body_mult`/`follow_atr` (both settings-page fields)
and re-run this ablation rather than reintroduce the weight blind.

## rf_fake_breakout (Break & Retest only — the only breakout-family strategy with trades)

| Fold | Δexp | signals_removed_pct | n_kept |
|---|---|---|---|
| Pooled | -0.005 | 26.3% | 14 |
| 2021 | -0.044 | 16.7% | 10 |
| 2022 | None (100% removed) | 100.0% | 0 |
| 2023 | +0.11 | 33.3% | 4 |

Only **1** fold shows a negative delta (2021); 2022 is undefined (every
signal that fold got flagged, leaving nothing to compare against) and 2023
is positive on N=4 — too thin to trust either way. **Does not clear the
≥ 2-fold bar — no demotion.** `rf_fake_breakout` is this strategy's own
namesake red flag (per the G97 baseline census) and the evidence here is
genuinely mixed/thin (Break & Retest pooled N=19 is itself below the
N≥30 floor), so "no demotion" is the honest reading, not a pass.

## rf_divergence_trap (RSI Divergence only)

| Fold | Δexp | signals_removed_pct | n_kept |
|---|---|---|---|
| Pooled | +0.006 | 0.6% | 162 |
| 2021 | — (didn't fire) | — | — |
| 2022 | +0.019 | 2.0% | 49 |
| 2023 | — (didn't fire) | — | — |

Fires almost never (0.6% of pooled signals) and is positive in the one fold
where it fires. No demotion — nothing here to act on either way; this flag
is nearly silent in-sample.

## Demotions applied

- **`rf_stop_sweep` → weight 0** (was 8.0): negative expectancy_delta in
  9 of 11 non-trivial fold observations across 5 different strategies —
  clears the pre-registered "≥ 2 folds hurt expectancy" bar decisively.
- No other flag observed firing in this replay clears the bar.
  `rf_fake_breakout` and `rf_divergence_trap` both stay at their registered
  weights (10.0 and 8.0 respectively) — the evidence for each is thin
  (N<30 samples) or one-sided in the flag's favor.

## Honest summary

Of the 8 registered red flags, only 3 ever fired in this fixed-2w-horizon
TRAIN replay. Of those 3, only `rf_stop_sweep` has enough cross-strategy,
cross-fold evidence to act on — and the evidence says its current
thresholds are net-harmful to expectancy, not net-helpful. This is exactly
the kind of result the ablation step exists to catch: a red flag's mere
presence in the checklist proves nothing about whether it earns its keep.
