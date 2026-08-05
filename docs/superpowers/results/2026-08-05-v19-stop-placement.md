# V19 — Stop-placement retune (plan v8, Phase V4)

**Status:** this is **not** a pre-registered experiment, and must not be cited
as one. V19 asks for a *retune*; what follows is the preflight measurement that
says the retune cannot be run as written, taken **before** the grid time was
spent rather than after. No config was tuned, adopted, or rejected. Harness:
`scripts/stop_cap_binding.py`.

## What V19 asked, and what landed underneath it

> **Step 1:** Only now, with the floor fixed, retune `atr_stop_multiple` —
> today a flat **2.0 across every horizon** while `max_risk_pct` scales 3%→11%.

That premise was written on 2026-07-31 and is accurate about the *shape* of the
config — `atr_stop_multiple` is still flat 2.0 across all ten horizons
(`strategy_types.py`). What it predates is **V51**, which on 2026-08-02 added a
hard `MAX_LOSS_PCT = 1.75%` cap under a human-partner directive. The cap sits
**downstream of the multiple**, and it changes what a retune can accomplish.

## The mechanism — everything upstream of the cap has to get past it

`plan_engine._atr_plan` (lines 251-260) prices every ATR-sized stop as:

```python
risk_distance = h["atr_stop_multiple"] * atr_val
if stop_mult is not None:                     # E31 MAE-informed factor, 0.8-1.3x
    risk_distance *= stop_mult
max_risk_amount = entry * (h["max_risk_pct"] / 100)
if risk_distance > max_risk_amount:
    risk_distance = max_risk_amount
risk_distance = cap_risk_distance(entry, risk_distance)   # MAX_LOSS_PCT, 1.75%
```

`max_risk_pct` runs 3-11% by horizon, so **the 1.75% cap is always the tighter
of the two percentage limits** and `max_risk_pct` never binds first. The stop
distance is therefore

```
min( atr_stop_multiple × stop_mult × ATR14 ,  1.75% × entry )
```

and the multiple moves the stop **only** where `mult × ATR14 < 1.75% × entry`.
Note this puts **both** V19 steps inside the same capped expression: Step 1
moves the first term, Step 2's MAE-informed `stop_mult` moves the second, and
the cap truncates their product.

## Measurement 1 — every TRAIN bar

`python scripts/stop_cap_binding.py --bars`. 289,278 ticker-bars over TRAIN,
universe screens applied (the same liquidity/data-quality screens every
backtest runs, so `GC=F`, `SI=F` and the eight bad-data tickers are out).
Median ATR14 = **2.716%** of close; deciles 1.50 1.81 2.10 2.40 2.72 3.08 3.57
4.28 5.63.

A 1.75% cap against a 2.7% median ATR is not a rare clamp — it is the norm:

| `atr_stop_multiple` | stop set by the cap | multiple actually binds |
|---|---:|---:|
| 1.5 | 97.9% | 2.1% |
| **2.0 (shipped)** | **99.9%** | **0.1%** |
| 2.5 | 100.0% | 0.0% |

`tune_sizing.py`'s grid for this axis is exactly `[1.5, 2.0, 2.5]`.

And the E31 `stop_mult` clamp from Step 2, applied at the shipped 2.0:

| `stop_mult` | effective multiple | binds |
|---|---:|---:|
| 0.8 | 1.60 | 1.2% |
| 0.9 | 1.80 | 0.4% |
| 1.0 | 2.00 | 0.1% |
| 1.1 – 1.3 | 2.20 – 2.60 | 0.0% |

**The entire widening half of that clamp is absorbed by the cap**, and the
narrowing half reaches 1.2% of bars at its extreme.

## Measurement 2 — real entries, which is the number that governs

Entries are strategy-selected, not random bars, so the bar pass only transfers
if entries aren't drawn from an unusually quiet subset. `--entries` runs the
real harness and reads the stop distance the plan builder actually produced,
`|entry − stop_loss| / entry`. 12 screened tickers × 10 horizons × 11
strategies, production config (exit v2 + scale-out, TP2 `levels`, frictions
on), gates live.

**3,701 TRAIN entries.** Stop distance percentiles: p10 = p25 = p50 = p75 =
p90 = **1.750**, max 1.770.

> **99.6% of real entries sit exactly at the cap.** The multiple set the stop
> on **0.4%** of them.

Per strategy, share of entries at the cap:

| Strategy | N | at cap |
|---|---:|---:|
| RSI Divergence | 1776 | 99.4% |
| Support/Resistance | 429 | 99.5% |
| Fibonacci | 329 | 100.0% |
| MA Ribbon | 302 | 100.0% |
| Break & Retest | 295 | 100.0% |
| MACD | 173 | 100.0% |
| VWAP | 140 | 100.0% |
| Elliott Wave | 125 | 99.2% |
| Volume Profile | 101 | 100.0% |
| EMA Crossover | 31 | 100.0% |

Entries are capped at very slightly **below** the bar-level rate (99.6% vs
99.9% at the same multiple), i.e. strategies do select marginally quieter bars
than average — but the selection effect is 0.4% vs 0.1% of the sample and
changes nothing. The bar pass is a sound proxy for the entry pass, and neither
number rescues the knob. RSI contributed zero entries in this 12-ticker sample
and is absent from the table.

This is an independent route to the same place V52 reached from the outcome
side: *"the 1.75% cap binds on essentially every loss (median realised loss
exactly 1.75%, 0.0% over cap)"*. V52 measured the consequence; this measures
the cause. The two are not independent evidence — they are the same fact seen
at entry and at exit.

## Reproduce

The host `python3` has no pandas; these run inside the `swing-bot:latest`
image, like every other harness here:

```bash
docker run --rm -v /root/Discord-Bot:/app -w /app swing-bot:latest \
  python scripts/stop_cap_binding.py --bars
docker run --rm -v /root/Discord-Bot:/app -w /app swing-bot:latest \
  python scripts/stop_cap_binding.py --entries --limit 12
```

Both tables above were produced by an ad-hoc script first and then reproduced
**field for field** by the committed harness — same 3,701 entries, same
percentiles, same per-strategy rows — so what is committed is what was
measured. One correction the screens forced, recorded because it moved a
number: an early pass globbed all 95 cached CSVs and got 98.4% capped at the
shipped 2.0. That figure was wrong for this purpose — it included `GC=F`,
`SI=F` and the eight bad-data tickers, none of which any backtest runs. With
the universe screens applied it is **99.9%**. The conclusion strengthened.

## Step 1 — closed as a measured null

**`atr_stop_multiple` cannot be meaningfully retuned under the shipped
config.** Every value in `tune_sizing.py`'s grid produces the same 1.75% stop
on 97.9-100% of bars and 99.6% of real entries. Running the grid would spend
hours to move a term that reaches the outcome on well under 1% of trades, and
would return three near-identical rows that an unwary reader could mistake for
"the multiple doesn't matter, so 2.0 is fine" — when the actual finding is
that the multiple is *disconnected*, not *optimal*.

The checkbox is ticked because the task's question is answered — with a null,
not a tune. **No value was changed.** The shipped flat 2.0 stays, and it stays
for the reason recorded here rather than because a grid endorsed it.

## Step 2 — left unticked, two independent blockers

`DATA_DRIVEN_STOPS_ENABLED` (`config.py:626`, default false):

1. **The inherited blocker still holds** — verified 2026-08-05, not assumed.
   `scripts/wf_components.py` still lists it under `INERT_COMPONENTS`: *"E31/E32
   reach `plan_engine.build_strategy_plan` only; the backtest sizes through
   `backtest._trade_plan_at`, which takes no `stop_mult`/`tp2_r`. Needs those
   threaded through `run_backtest` first."* It cannot be fold-validated, so the
   normal adoption gate is unavailable — exactly as `edge-engine-v4.md`
   recorded.
2. **New, and it survives closing the wiring gap:** the flag's own knob is
   inside the capped expression. Thread `stop_mult` through `run_backtest`
   tomorrow and its 0.8-1.3× clamp still maps to 1.6-2.6 effective ATR, which
   the cap truncates on 98.8-100% of bars. Its widening half is entirely inert.
   Per the flag's own help text, structure-derived stops (Fibonacci, Elliott
   Wave, Support/Resistance) are never scaled by it at all.

Per the plan's verification-debt rule, **the box stays unticked**: no evidence
exists that this flag helps or hurts, and closing the wiring gap would buy a
knob measured here as nearly inert. That is a reason to *deprioritize* the
wiring work, not a reason to claim the flag was evaluated.

## What would actually move stop placement

The knob that sets the stop on 99.6% of trades is **`MAX_LOSS_PCT` itself**.
Retuning stop placement now means retuning the cap — and the cap is not an
agent's to grid: it was set to 1.75% by an explicit human-partner directive on
2026-08-02, as the loss half of a payoff structure whose win half is
`MIN_TARGET_PCT = 2.5%`. Moving it changes the break-even win rate the whole
plan is organised around (V52 measured tightening 2.00%→1.75% as costing 3.2
points of win rate).

So the honest successor to V19 Step 1 is **a cap retune, pre-registered and
human-approved**, not an `atr_stop_multiple` grid. This file does not propose
one, and nothing here licenses moving the cap.

## Limits

- **Not pre-registered.** No decision rule was fixed in advance; the numbers
  are descriptive. Nothing is adopted or rejected on them.
- **12 tickers for the entry pass**, chosen as the first 12 that clear the
  screens (alphabetical), not sampled. 3,701 entries across 11 strategies is
  ample for a 99.6% vs 0.4% split, but the per-strategy rows with N ≈ 30-130
  are thin and only the aggregate should be read closely.
- **TRAIN only.** No validation budget spent.
- **This says nothing about whether 1.75% is the right cap.** It says the
  multiple can't move the stop while that cap is in force. Those are different
  questions and this file only answers the second.
