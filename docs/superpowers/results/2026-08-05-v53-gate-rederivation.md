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

> 1. **UNGATED** — if **both** direction arms *independently* have `ExpR > 0`
>    at `N ≥ 30`, ship **no mask at all**. *(Amended 2026-08-05 — see below.)*
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

## Amendment to rule 1, made 2026-08-05 before the grid's numbers existed

**Rule 1 originally read the *pooled* both-direction sample.** It now requires
each arm to clear `ExpR > 0` at `N ≥ 30` **independently**. Rules 2-4 are
unchanged. Recorded here in full, because amending a pre-registered rule is
the thing this file exists to make hard.

**Why it was wrong.** Longs outnumber shorts about 3.4:1 (V21 measured 37,395
vs 10,860 over TRAIN). With long at +0.196R and short at −0.041R, the pooled
average lands near +0.14R — positive. Rule 1 would have fired, the mask would
have been **deleted**, and that would have *enabled* a short arm which the rule
never tested on its own. A direction gate exists precisely to stop a direction
with no edge from trading; a first rung that can remove it on the strength of
the other direction cannot do that job.

**How it got in.** The ladder's shape was inherited from the original
derivation (`2026-07-train-tuning.md` Step 4), whose first rung was a pooled
`WR ≥ 80` bar. Under a win-rate bar, a bad arm *drags the pool down* and the
rung correctly fails. Under an expectancy bar, the bigger arm's mass *carries
the pool up* and the rung silently passes. Swapping the bar — which V6 forced,
since the WR bar is void — turned pooling from an exposer of bad arms into a
concealer of them. The shape was reused without re-checking that its first
rung still did its job underneath a different bar.

**Why amending now is legitimate, and what was already known.** V20 set the
precedent that a pre-registered rule may be touched **only** before its numbers
exist; the grid was killed at ticker 14 of 67 and restarted from scratch under
the amended rule, so no result influenced this. Full disclosure of what *was*
known: a 2-ticker smoke test run before the real grid had sent all five
strategies to rule 1, which is what prompted the re-reading of the rule. That
is a hint about the outcome, so the amendment is not made in perfect ignorance.

Two things make it safe anyway, and both were checkable in advance:

1. **The amendment is strictly conservative.** Requiring each arm to pass
   independently can only ever produce *more* gating, never less — it cannot
   manufacture an adoption, loosen a restriction, or flatter any strategy. An
   amendment that can only tighten the outcome cannot be self-serving.
2. **It restores the original rung's behaviour** rather than inventing a new
   one. Under the old `WR ≥ 80` bar a negative arm failed the pooled test; this
   makes it fail again under the expectancy bar. The correction moves the rule
   back toward what it did before V6 voided the bar, not toward a preferred
   answer.

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

Grid completed **2026-08-05**: 67 tickers × 10 horizons × 5 strategies,
`--gates off`, one pass, ~45 min. Raw output:
`2026-08-05-v53-gate-rederivation.json`.

**The rule ran clean and produced five masks. NOTHING WAS ADOPTED.** The
`STRATEGY_GATES` in `strategy_types.py` are unchanged. Why is in
"The adoption decision" below, and it is a human-partner directive, not a
rule failure — the distinction matters and this file must not blur it.

## Harness verification — a different one than pre-registered

The pre-registration promised a run with the proposed masks written into
`STRATEGY_GATES`, reproducing the pooled figures the rule selected on. **That
run was not made, and its box stays unticked.** With nothing adopted it would
verify numbers that inform no shipped config, at ~45 min of compute.

What was done instead, at zero compute and recorded *as* a substitute:
V53 and V21 are independent harnesses that ran the same config (gates off,
exit v2 + scale-out, TP2 levels, frictions on) over the same screened
universe. Pooling V53's seven per-regime slices must therefore reproduce V21's
Test A arms exactly. It does — **all 10 arms, exact on N, wins and expectancy
to 1e-9**:

| | V53 pooled from regimes | V21 Test A |
|---|---|---|
| Fibonacci bullish / bearish | 218/75/−0.23742 · 276/110/+0.36899 | identical |
| MA Ribbon bullish / bearish | 212/64/−0.31043 · 146/66/+0.83442 | identical |
| MACD bullish / bearish | 582/201/−0.14967 · 776/355/+0.11625 | identical |
| VWAP bullish / bearish | 238/76/−0.17161 · 209/87/+0.09442 | identical |
| Volume Profile bullish / bearish | 1502/552/−0.14192 · 1197/483/+0.05619 | identical |

This establishes that V53's slicing agrees with an independently written
harness. It does **not** establish what the pre-registered check would have —
that a mask written into `STRATEGY_GATES` reproduces the slice it was chosen
on. That remains unverified, and is named here as the weaker evidence it is.

## The five proposals

| Strategy | Current mask | Rule | Proposed | bullish ExpR (N) | bearish ExpR (N) |
|---|---|---|:-:|---|---|
| Fibonacci | bullish | **1** | **no mask** | +0.173 (1407) | **+0.090 (707)** |
| MA Ribbon | bullish | **1** | **no mask** | +0.275 (1435) | **+0.190 (374)** |
| MACD | bullish + {3m,4m,7m,8m,9m} | **1** | **no mask** | +0.152 (3693) | **+0.017 (1476)** |
| VWAP | bullish + {4w,6m,7m,8m,9m} | 2 | bullish | +0.293 (1911) | −0.094 (570) |
| Volume Profile | bullish + {7m} | 2 | bullish | +0.249 (11349) | −0.079 (3619) |

No strategy reached rule 4. **Three of five clear rule 1** — their bearish arms
each cleared `ExpR > 0` at `N ≥ 30` independently, which is what the amended
rule demands.

**Every proposal is looser than what it replaces**, on TRAIN signal count:

| Strategy | current → proposed | |
|---|---|---|
| Fibonacci | 1,407 → 2,114 | ×1.5 |
| MA Ribbon | 1,435 → 1,809 | ×1.3 |
| VWAP | 791 → 1,911 | ×2.4 |
| MACD | 864 → 5,169 | **×6.0** |
| Volume Profile | 504 → 11,349 | **×22.5** |

Volume Profile deserves a second look: it stays bullish-only, so it reads as
unchanged, but dropping `{7m}` opens nine more horizons and multiplies its
alerts ~22×.

## The mandatory disclosure, which does not flatter the result

Per-regime ExpR for each **selected** mask (blank = under N=30):

| Strategy | dotcom | 2002 | GFC | 2011 | 2015-16 | 2022 |
|---|---|---|---|---|---|---|
| Fibonacci | +0.398 | +0.768 | −0.197 | −0.124 | −0.239 | +0.206 |
| MA Ribbon | +0.628 | +0.288 | +0.144 | −0.404 | −0.234 | +0.429 |
| MACD | −0.222 | +0.013 | +0.135 | −0.138 | −0.072 | −0.014 |
| VWAP | −0.274 | — | −0.097 | — | −0.311 | — |
| Volume Profile | −0.044 | −0.128 | −0.080 | −0.322 | −0.148 | −0.172 |

**VWAP and Volume Profile are negative in every sufficient drawdown window.**
The two strategies that stayed bullish-only are exactly the two that remain
bull-majority artifacts — the failure mode this file pre-registered as "the
single most likely way this task fails quietly", and it happened.

The three that gained a short arm behave differently, and the bearish arm on
its own shows why:

| bearish only | dotcom | 2002 | GFC | 2011 | 2015-16 | 2022 |
|---|---|---|---|---|---|---|
| Fibonacci | — | **+1.049** | +0.012 | — | −0.397 | **+0.488** |
| MA Ribbon | — | — | **+0.498** | — | — | **+0.900** |
| MACD | −0.069 | −0.056 | **+0.197** | — | +0.092 | **+0.242** |

The short side earns its keep precisely where the long side collapses. That is
V21's regime-conditional finding appearing constructively: **ungating direction
is the closest a static mask can get to being regime-aware** without the regime
mechanism the codebase does not have. A partial structural compensation, not a
fix.

## The adoption decision: NOTHING ADOPTED

**Human-partner directive, 2026-08-05, after seeing the table above:** the
objective is to *strengthen* signal generation, not loosen it; a change that
makes it worse is skipped. Every one of the five proposals loosens — ×1.3 to
×22.5 more signals — so none was applied.

**This is a post-hoc filter and is recorded as one.** It was not
pre-registered. The pre-registered rule *passed* and produced five masks; the
decision not to ship them is a separate judgement layered on top, made by the
human partner whose call adoption is. Anyone reading this later must not
restate it as "the rule rejected them" — it did not.

Two measured facts support the directive, and they were in the pre-registration
rather than invented afterwards:

1. **Every expectancy here is inside V51's error bar.** The measured daily-bar
   overstatement is **+0.318R** and the largest number in the whole result is
   +0.293. Applying that correction in the direction V51 measured puts **every
   arm negative**. The rule reads the sign of expectancy, and the sign is
   exactly what the one quantifiable correction removes. The pre-registration
   said a mask under +0.318R should be read as "not distinguishable from zero";
   all ten arms are.
2. **MACD's rule-1 pass is +0.017R** at N=1476 — arithmetically positive and
   nothing more, ~19× smaller than the known bias. It clears by a hair and is
   not evidence that MACD shorts work.

## What this leaves open — stated plainly, not buried

**V21's obligation is NOT discharged.** The five gates it condemned are still
in place, still fitted on 2020-2023, still contradicted in all seven
drawdowns. V53 asked whether a better *static* mask exists on the full 25
years; the answer is that the candidates are all looser and all inside the
error bar. So the debt stands, and the next reader should not mistake "V53 ran"
for "the gates are fixed".

Three things fell out that a successor should carry:

- **Mildest-gate-first drops horizon masks without testing them.** VWAP and
  Volume Profile land on rule 2, so the ladder never reaches rule 3 and their
  horizon restrictions vanish unexamined. That is a faithful consequence of the
  pre-registered ladder — flagged, deliberately **not** amended, because
  results now exist and amending after seeing them is what pre-registration
  forbids. Re-deriving the horizon halves needs its own pre-registered task.
- **A tightening ladder was never tried.** This one is ordered
  mildest-gate-first, inherited from the original derivation, so it structurally
  cannot return anything stricter than the status quo. A strictest-gate-first
  ladder would be the tool for the stated objective — but selecting horizons
  after seeing this file's tables is precisely the multiple-comparisons trap
  that produced the current masks, so it must be pre-registered on its own and
  ideally read on a held-out split.
- **The real answer remains regime-conditional gating**, which needs
  `REGIME_GATES_ENABLED` wired (one of the four flags `wf_components.py` lists
  as permanently inert to the fold harness) and `REGIME_ALLOW` populated.
  Nothing in V53 changes that conclusion from V21.

No validation budget was spent; V24's shot stays held. No file under
`swingbot/` was modified by this task.
