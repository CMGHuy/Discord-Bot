# V53 — Re-deriving the five failed direction gates (plan v8, V21 follow-up)

**Status:** pre-registration written 2026-08-05 **before the grid was run** —
everything below the "Result" heading was empty when this file was first
committed. Harness: `scripts/rederive_direction_gates.py`.

## Why this exists

V21 (`2026-08-05-v21-direction-survivorship.md`) failed five gated strategies:
**Fibonacci, MA Ribbon, MACD, VWAP, Volume Profile**. Their bullish-only masks
are contradicted in all seven drawdown windows at N ≥ 30 per arm, with margins
of −0.198R to −1.145R. V21's rule obliges a re-derivation; this is it.

Not in scope: **RSI** (V21 INSUFFICIENT, N=20/10) and **Support/Resistance**
(V21 SURVIVES on +0.014R). V21's rule did not condemn them, and re-deriving a
gate the audit did not fail would be scope creep dressed as diligence.

## The bar the original derivation used is void, and that is the whole problem

The current masks come from `2026-07-train-tuning.md` Step 4, fitted on the
**2020-2023** window under a mildest-gate-first policy accepted at
**`WR ≥ 80`, `ExpR > 0`, `N ≥ 30`**. Plan v8 Task V6 **voided that WR bar**:

> the old `win_rate >= 80` bar is VOID. It was set when a "win" meant touching
> a ~0.85% target; under a 2.5% floor it is measuring a different event and
> cannot carry over.

So the masks cannot be re-fitted by re-running the old rule on a wider window.
A replacement bar has to be chosen, and choosing it after seeing the numbers
is exactly the failure mode this repo pre-registers against. Hence this file.

**Do not compare the new numbers to the old gate comments in
`strategy_types.py`** (`N=286 WR=81.8 ExpR=+0.106` and friends). Those were
measured under the pre-V51 geometry — a ~0.85% median target against a 2.19%
median stop — where a "win" was a far easier event. V21 measured the same
strategies at 31-47% WR under the shipped 2.5% floor and 1.75% cap. The two
sets of win rates are not commensurable and putting them in one table would
manufacture a collapse that is really a definitional change.

## What the new rule reads: expectancy, not win rate

V6 Step 3b (human-partner directive, 2026-08-02) made **expectancy the
objective** with win rate a hard constraint reached in stages 60% → 70% → 80%.
V52's ladder then found **not one cell, in any strategy, at any cut-flag
combination, clearing Stage 1's Wilson LB > 60%**.

That has a consequence this file must state plainly rather than route around:
**no direction mask can clear the shipped acceptance ladder, and this task
cannot produce a shippable-by-V6 configuration.** A gate selects *which* of a
strategy's signals fire; it cannot lift a 45% win rate to 60%.

So V53 is deliberately **not** an adoption gate. It answers the narrower
question the code actually poses — *given that the bot ships some mask, which
mask is best supported by the full 25 years?* — and it is scoped to replacing a
mask fitted on a discredited window with one fitted on the whole history.
Nothing here licenses shipping these strategies, and V52's empty adopted set is
unchanged by whatever this returns.

## Config under test — production, pinned

Identical to V20's and V21's, so all three are comparable:

| Setting | Value |
|---|---|
| `MIN_TARGET_PCT` / `TARGET_FLOOR_ENABLED` | 2.5% / true |
| `MAX_LOSS_PCT` / `MAX_LOSS_CAP_ENABLED` | 1.75% / true |
| Exit model | **v2 + scale-out**, TP2 `levels`, frictions **on** |
| `STRATEGY_GATES` | **OFF during the run** (a masked strategy cannot show the arm it masks) |
| Window | TRAIN `1999-01-01 .. 2023-12-31` |

No validation budget is spent: the whole run sits inside TRAIN, and V24's one
validation shot stays held.

## The decision rule, fixed before the grid ran

Sufficiency bar `MIN_N = 30` (imported from `regime_slices`, same constant V20
and V21 used). Wilson lower bounds reported everywhere per V6 Step 5; point
estimates are never read alone.

Applied per strategy, **mildest-gate-first** — the same ladder shape as the
original derivation, with the voided WR bar replaced by expectancy:

> 1. **UNGATED** — if pooled over both directions and all horizons
>    `ExpR > 0` at `N ≥ 30`, ship **no mask at all**.
> 2. **DIRECTION** — else, if exactly one direction arm has `ExpR > 0` at
>    `N ≥ 30`, mask to that direction.
> 3. **DIR+HORIZON** — else, within the better-ExpR direction, keep the
>    horizons with `ExpR > 0` at `N ≥ 30` each, **and only if** the pooled
>    subset itself clears `ExpR > 0` at `N ≥ 30`.
> 4. **FAILING** — else, **remove the gate** and record the strategy as
>    failing.

Two choices in there that are not the original's, both made in advance:

- **Rule 4 removes the mask rather than keeping it.** The original policy left
  its two failures (EMA Crossover, Elliott Wave) ungated and documented as
  FAILING, so this matches its precedent. A mask with no evidence behind it is
  not made safer by being left in place, and keeping it would preserve the
  2020-2023 fit this task exists to retire.
- **Rule 3's per-horizon floor is `N ≥ 30`, not the original's `N ≥ 10`.**
  Selecting across 10 horizons × 2 directions off N=10 cells is how the current
  masks were overfitted; V6's sample-size clause calls a rate on a sample that
  thin "a hypothesis, not a finding". This will select fewer horizons than the
  original did, and that is intended.

## Mandatory disclosure: the selected mask, re-read in V20's seven drawdowns

For whichever mask each strategy lands on, its expectancy in each of V20's
seven regimes is reported beside it.

**This is a disclosure, not a rejection rule.** Selecting a mask on TRAIN and
then rejecting it on the drawdown windows that motivated the task would be
double-dipping: those windows are inside TRAIN and already drove the failure
that created this task. It is reported so the next reader can see whether the
replacement mask is *once again* a bull-majority artifact — the single most
likely way this task fails quietly.

## What this cannot fix, stated before the numbers exist

- **A static mask remains the wrong shape, and this task ships a static mask.**
  V21's core finding is that direction edge is *regime-conditional*: long wins
  by +0.237R across full TRAIN and loses in all seven drawdowns. Re-fitting a
  static mask on 25 years will, by construction, mostly re-select whatever wins
  across the bull majority of those 25 years. **A rule-1 or rule-2 result here
  is therefore the expected outcome, not a vindication**, and it does not
  answer V21. The real answer is a regime-conditional or
  volatility-conditional gate, which needs a mechanism the codebase does not
  have (`REGIME_GATES_ENABLED` is one of the four flags `wf_components.py`
  lists as permanently inert to the fold harness, and `REGIME_ALLOW` is empty).
- **Survivorship runs the same direction as in V21.** The universe is 78
  tickers that all survived to 2026, and V21's Test B could not clear that. Any
  long-side mask selected here inherits the bias undiminished.
- **Every absolute ExpR inherits V51's +0.318R daily-bar overstatement.** The
  rule reads the *sign* of expectancy, which is precisely the quantity that
  bias can flip. A rule-1/2/3 mask whose ExpR is under +0.318R is inside the
  known error bar, and the honest reading of one is "not distinguishable from
  zero", not "positive".
- **No validation.** These masks are TRAIN-selected and unvalidated, like the
  ones they replace.

## Harness

`scripts/rederive_direction_gates.py`. One pass over the ticker × horizon ×
strategy grid, every slice taken off it — the V50/V20 recomputation trap.
`pool`, `pooled_max_dd_pct`, `wilson_lower_bound` and `window_trades` are
imported from `run_backtest_range`, and `REGIMES`/`MIN_N` from `regime_slices`,
so these numbers cannot drift from the harnesses that produced V16/V17/V20/V21.

The ladder in `derive()` is the rule above, in code, applied mechanically —
no post-hoc judgement between running the grid and reading the verdict.

**To be verified before the numbers are trusted**, per V20/V21 precedent: a
run with the proposed masks written into `STRATEGY_GATES` must reproduce the
pooled figures the rule selected on, rather than those being hand-summed from
slices. Recorded under Result.

---

# Result

*(empty at pre-registration time — filled in after the grid finished)*
