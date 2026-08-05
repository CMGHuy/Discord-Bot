# V54 — Strictest-gate-first re-derivation, held out (plan v8, V53 successor)

**Status:** pre-registration written 2026-08-05 **before the grid was run** —
everything below the "Result" heading was empty when this file was first
committed. Harness: `scripts/strictest_gate_ladder.py`.

## Why this exists

V53 re-derived five direction gates under a **mildest-gate-first** ladder
inherited from the original 2026-07 derivation. It ran clean and returned five
masks — every one *looser* than what it replaced (×1.3 to ×22.5 more TRAIN
signals). None was adopted, on the human-partner directive that the objective
is to **strengthen** signal generation, not loosen it.

That outcome was structural, not bad luck: **a mildest-first ladder cannot
return anything stricter than the status quo.** Its first rung is the loosest
possible mask and it stops at the first rung that passes. To ask "can these
gates be *tightened*?" the ladder has to be inverted, and the non-loosening
requirement has to be part of the rule rather than a judgement applied
afterwards — V53's was applied afterwards, and this file exists so that does
not happen twice.

## Disclosure: this pre-registration is not written in ignorance

The multiple-comparisons trap is the whole risk here — selecting among 20
(direction × horizon) cells per strategy on the same data that judges them is
how the *current* masks were overfitted, and V53's tables are already
committed and readable. So what the author had seen when this rule was written
is stated exactly, rather than implied:

- **Seen:** V53's per-strategy per-*direction* TRAIN aggregates, its
  signal-volume table, and its per-regime disclosure (all in
  `2026-08-05-v53-gate-rederivation.md`); V21's Test A arms; and a 2-ticker
  smoke test's per-horizon rows for one strategy.
- **Not seen:** the full 67-ticker **per-horizon cells** — the exact quantity
  this task selects on. They exist in V53's committed JSON under
  `by_direction_horizon` and were deliberately not read before this rule was
  fixed. A reader can verify the rule below names no horizon.

That is a mitigation, not a guarantee, so the structural guard below does the
real work.

## The structural guard: a held-out half of the universe

Selection happens on **FIT**; the selected mask must then survive on
**CONFIRM**, which no selection step ever reads.

**Split by ticker, not by time**, and the reason matters: V21 established that
direction edge here is *regime-conditional*. A time split would put different
regimes in the two halves, so a mask failing CONFIRM would be ambiguous
between "the selection was noise" and "the regime changed" — and only the
first is what this guard is for. A ticker split gives both halves the same
25 years and the same seven drawdowns, isolating selection noise.

Deterministic: the 67 screened tickers sorted alphabetically, even indices to
FIT, odd to CONFIRM. **Published here so it cannot be re-cut after the fact**
(the V21 precedent for its tercile membership):

**FIT (34):** AAPL ADBE AMD ARM AVGO BA CRM CVX DELL EA FTNT GEV GM GS HPQ
ILMN INTU ISRG JPM MRNA MSFT MU NFLX NOW ORCL PEP PLTR QCOM SBUX SNOW STX
UBER V WMT

**CONFIRM (33):** ABNB AMAT AMZN ASML AXON CEG CRWD DDOG DOCU EBAY GD GLW
GOOGL HD IBM INTC IREN JNJ META MRVL MSTR NBIS NKE NVDA PANW PFE PYPL RKLB
SNDK SNPS TSLA UNH WDC

Both halves are survivor-selected in exactly the way V21 could not correct, so
CONFIRM is **not** an out-of-sample window in the survivorship sense. It tests
one thing only: whether a cell selection generalises past the tickers it was
chosen on.

## Scope: all eleven strategies

Wider than V53's five, and safe to widen precisely because the ladder below
**cannot loosen anything**. The four currently-ungated strategies have the most
room to tighten — two of them (EMA Crossover, Elliott Wave) are ungated only
because the original derivation could not find a passing mask and left them
documented as FAILING, which is not the same as "they should trade everything".

## Config under test — production, pinned

Identical to V20/V21/V53, so all four are comparable:

| Setting | Value |
|---|---|
| `MIN_TARGET_PCT` / `TARGET_FLOOR_ENABLED` | 2.5% / true |
| `MAX_LOSS_PCT` / `MAX_LOSS_CAP_ENABLED` | 1.75% / true |
| Exit model | **v2 + scale-out**, TP2 `levels`, frictions **on** |
| `STRATEGY_GATES` | **OFF during the run** (a masked strategy cannot show the arm it masks) |
| Window | TRAIN `1999-01-01 .. 2023-12-31`, split FIT / CONFIRM by ticker |

No validation budget is spent. V24's one shot stays held.

## The rule, fixed before the grid ran

`MIN_N = 30` throughout (imported from `regime_slices`, the same constant V20,
V21 and V53 used). Wilson lower bounds reported everywhere; point estimates
never read alone.

Per strategy, **strictest-first** — the inverse of V53's ladder:

> **Step A — admissible cells.** Of the (direction × horizon) cells **the
> current mask already admits**, a cell is *admissible* iff `ExpR > 0` at
> `N ≥ 30` **on FIT**. Drawing only from currently-admitted cells is what
> makes the candidate a **subset** of what ships.
>
> **Step B — tightest expressible mask.** `STRATEGY_GATES` masks are a
> cross-product (`directions × horizons`), so the candidate is the closure of
> the admissible cells: `directions` = the directions appearing among them,
> `horizons` = the horizons appearing among them. The closure may re-admit
> cells that were not admissible; the candidate must therefore *itself* clear
> `ExpR > 0` at `N ≥ 30` on FIT. If it does not, the strategy fails here.
>
> **Step C — the non-loosening constraint.** The candidate's TRAIN signal
> count over the **whole** universe must be `<=` the current mask's. Given
> step A, the candidate is a subset of the current mask and this holds **by
> construction**; C stays in the rule as a defensive assertion, and a
> violation is reported as a bug rather than a verdict.
>
> **Step D — held-out confirmation.** The candidate must clear `ExpR > 0` at
> `N ≥ 30` on **CONFIRM**, which nothing above has read.
>
> **ADOPT** iff B, C and D all pass. **Otherwise KEEP THE CURRENT MASK.**

**One correction made to this rule before it was committed.** Step A first read
all 20 cells rather than only the currently-admitted ones. A 6-ticker smoke
test showed why that fails: the closure in step B spans every admissible
horizon, so for an already-tight mask it *loosens* (Volume Profile's
`bullish + {7m}` produced a candidate admitting 1,370 signals against the
current 44) and step C then rejects it. The ladder could only ever return KEEP
— never the tightening it exists to find. Restricting step A to currently
admitted cells fixes it and makes non-loosening structural. Recorded because
the fix landed before the pre-registration was committed and before any
67-ticker number existed, which is the only time a rule may be touched.

A consequence worth stating: this ladder can **shrink** a mask but never
**move** one. If `bullish + {2m,3m}` were better than the shipped
`bullish + {7m}`, V54 cannot find it — that would mean admitting cells the
current mask excludes, i.e. loosening along one axis to tighten along another.
Under a strengthen-only directive that trade is not available, and pretending
otherwise would smuggle a loosening in through the back door.

Three further properties, all deliberate and all fixed in advance:

1. **Failure keeps the current mask; it never removes one.** This is the exact
   inversion of V53's rule 4, and it is what makes the ladder
   non-loosening *by construction* rather than by post-hoc filtering. Removing
   a mask is a loosening, so a failed re-derivation must not be able to cause
   one.
2. **Step C is a hard constraint, not a tie-break.** It is checked on the whole
   universe rather than FIT, because signal volume is a property of what
   ships, not of the fitting half.
3. **A strategy with zero admissible cells is reported, not auto-disabled.**
   "No (direction, horizon) cell in 25 years has positive expectancy at N≥30"
   is a strong statement and the honest response is to surface it for a human
   decision about dropping the strategy — there is no "disable strategy"
   primitive in `STRATEGY_GATES`, and inventing one inside a tuning task would
   be scope creep.

## Mandatory disclosure, unchanged from V53

Every adopted mask gets its expectancy reported across V20's seven drawdown
windows, and both direction arms are stored per regime. **Disclosure, never a
rejection rule** — those windows sit inside FIT and CONFIRM both, and reading
them as a gate would be double-dipping. It exists so the next reader can see
whether a tightened mask is *still* a bull-majority artifact, which is how
V53's two rule-2 masks failed on inspection.

## What this still cannot do, stated before the numbers exist

- **It cannot make a losing strategy profitable.** A gate selects which signals
  fire. V52 found nothing anywhere clearing Stage 1's Wilson LB > 60%, and
  nothing here changes that. The reachable outcome is *fewer, better-supported*
  signals — not a passing configuration.
- **Every expectancy inherits V51's +0.318R daily-bar overstatement.** The rule
  reads the sign of expectancy, which is exactly what that correction can flip.
  **Any adopted cell whose ExpR is under +0.318R must be read as "not
  distinguishable from zero"**, and V53's entire result sat under it. If that
  happens again, say so rather than adopting on a sign the known bias erases.
- **A static mask is still the wrong shape.** V21's finding stands: direction
  edge is regime-conditional, and no static cross-product mask encodes that.
  Tightening reduces exposure to the problem; it does not solve it. The real
  answer needs `REGIME_GATES_ENABLED` wired and `REGIME_ALLOW` populated.
- **Survivorship runs the same direction in both halves** and is uncorrected,
  per V21 Test B's one-directional limitation.
- **No validation.** Adopted masks would be TRAIN-selected and
  CONFIRM-checked, which is a within-TRAIN generalisation test, not a
  validation shot.

## Harness

`scripts/strictest_gate_ladder.py`. One pass over the ticker × horizon ×
strategy grid, every slice taken off it — the V50/V20/V53 recomputation trap.
`pool`, `pooled_max_dd_pct`, `wilson_lower_bound` and `window_trades` come from
`run_backtest_range`, `REGIMES`/`MIN_N` from `regime_slices`, so the numbers
cannot drift from the harnesses behind V16/V17/V20/V21/V53. The ladder is
applied mechanically in `derive()` — no judgement between running the grid and
reading the verdict.

**To be verified before the numbers are trusted:** pooling the per-regime
slices must reproduce an independent harness's figures for the same strategy
and arm, as V53's cross-check did against V21 (exact on all 10 arms). Recorded
under Result.

---

# Result

Grid completed **2026-08-05**, 12:29→14:37 (~2h08m): 67 tickers × 10 horizons
× 11 strategies, gates off, one pass. Raw output:
`2026-08-05-v54-strictest-gate-ladder.json`. Screened out: 2 illiquid, 8
bad-data, 1 no-data. ARM and SNDK are screened *in* but contributed 0 TRAIN
trades (listed after the window), so the effective universe is smaller than 67
on both halves.

**The ladder ran clean and returned 9 ADOPT / 2 KEEP. Nothing has been adopted
yet — the decision is routed to the human partner, for the reasons below, and
`STRATEGY_GATES` in `strategy_types.py` is unchanged.**

## Harness verification — PASS, and stronger than V53's

V53 could only offer a substitute for its pre-registered check. V54 gets the
real thing at zero compute: V53 and V54 are independently written harnesses
that ran the same config over the same screened universe, so their slices must
agree.

- **All 70 per-regime × per-direction slices** for V53's five strategies are
  **bit-identical** between the two runs (N, wins, expectancy to 1e-9).
- Pooling V54's seven regime slices reproduces V53's published table **exactly
  on all 10 arms** — and V53's table matched V21's Test A exactly, so V54
  reproduces V21 by transitivity.

Both checks agree with the harnesses behind V16/V17/V20/V21/V53. The caveat
V53 named still applies and is not weakened: these scripts share `pool`,
`window_trades` and `run_backtest`, so this verifies the *slicing* agrees, not
that the core is correct. The pre-registered check — a run with the proposed
masks written into `STRATEGY_GATES` reproducing the slice they were chosen on
— remains unmade, and stays unmade while nothing is adopted.

**Trap for the next reader, found doing this check:** `pool()` computes
`expectancy_r` as the mean over **all** trades (scratches and timeouts
included) while `n_eval` counts only wins and losses. Pooling per-slice
expectancies must therefore weight by `closed`, **not** by `n_eval`. Weighting
by `n_eval` produces a plausible-looking 0.001–0.03R error on every arm — it
reported 10/10 spurious mismatches here before the formula was fixed.

## Verdicts

| Strategy | Verdict | Current → Proposed | FIT ExpR (N) | CONFIRM ExpR (N) | Signals |
|---|:-:|---|---|---|---|
| VWAP | ADOPT | *unchanged* | +0.307 (450) | +0.321 (341) | 1027 → 1027 |
| Support/Resistance | ADOPT | *unchanged* | +0.138 (953) | +0.127 (845) | 2245 → 2245 |
| MACD | ADOPT | *unchanged* | +0.187 (455) | +0.069 (409) | 1130 → 1130 |
| Volume Profile | ADOPT | *unchanged* | +0.218 (278) | +0.333 (226) | 639 → 639 |
| RSI Divergence | ADOPT | *unchanged* | +0.142 (4281) | +0.129 (3864) | 9980 → 9980 |
| Fibonacci | ADOPT | bullish → bullish + {2w,4w,2m,4m,6m} | +0.176 (561) | +0.197 (520) | 1757 → 1384 |
| Elliott Wave | ADOPT | *ungated* → bullish + {4w} | +0.073 (201) | +0.196 (159) | 628 → 445 |
| MA Ribbon | ADOPT | bullish → bullish + {2w,4w,2m,3m,4m,5m} | +0.335 (710) | +0.230 (615) | 1836 → 1696 |
| Break & Retest | ADOPT | *ungated* → bullish + {4w,2m…9m} | +0.263 (851) | +0.248 (620) | 2405 → 1934 |
| EMA Crossover | KEEP | fails CONFIRM | +0.100 (34) | **−0.098 (28)** | — |
| RSI | KEEP | no admissible cell | — | — | — |

**Step C never fired.** Every candidate's whole-universe signal count is ≤ the
current mask's, as step A's restriction guarantees. The defensive assertion
held; no bug.

## Five of the nine "ADOPT"s are no-ops

Read the mask column, not the verdict count. Five strategies proposed a mask
**identical to what already ships**, so adopting them changes nothing:

- VWAP, Support/Resistance, MACD and Volume Profile re-proposed their exact
  current masks.
- RSI Divergence proposed `{directions: [bullish, bearish]}` with no horizon
  key — both directions, all ten horizons, which is *the same thing as
  ungated*. Its signal count is unchanged at 9980, which is the proof.

That is a real finding, not an artifact: for these five, the tightest
expressible subset of the current mask that clears the bar **is** the current
mask. The ladder found no room to tighten. **Only four masks would actually
change.**

## The four real tightenings all fail the pre-registered bias disclosure

Signal reductions are material — Fibonacci −21%, Elliott Wave −29%,
Break & Retest −20%, MA Ribbon −8%. But this pre-registration fixed the rule
for reading them, and it is unambiguous:

> Any adopted cell whose ExpR is under +0.318R must be read as "not
> distinguishable from zero" … say so rather than adopting on a sign the known
> bias erases.

**All four sit under V51's +0.318R daily-bar overstatement on CONFIRM**, and
three of four on FIT as well. MA Ribbon's FIT +0.335 is the only figure that
clears it, by 0.017R, and its own CONFIRM half (+0.230) does not. Every one of
these four adoptions therefore rests entirely on a positive sign that the known
bias erases. V53's whole result sat under this same floor; so does V54's.

## Mandatory per-regime disclosure — and it is damning

Expectancy of each *proposed* mask across V20's seven drawdown windows.
Disclosure, never a rejection rule — but it is what the next reader needs:

| Proposed mask | dotcom | 2002 | GFC | 2011 | 2015-16 | COVID | 2022 |
|---|---|---|---|---|---|---|---|
| Fibonacci | −0.225 | +0.214 | −0.509 | −0.176 | −0.090 | n/a | −0.376 |
| Elliott Wave | −0.711 | −0.486 | −0.265 | +0.024 | −1.000 | n/a | −0.500 |
| MA Ribbon | +0.129 | −0.169 | −0.222 | −0.557 | −0.428 | n/a | −0.440 |
| Break & Retest | −0.152 | −0.357 | −0.254 | −0.471 | −0.279 | −1.000 | −0.555 |

All four are bullish-only masks that lose money in **almost every drawdown
window**: Break & Retest is negative in all seven, Elliott Wave in six of six
with data, MA Ribbon in six of seven, Fibonacci in five of six. Several slices
are at or below `MIN_N` and should not be read alone, but the direction is
consistent and the pooled picture is not ambiguous.

This is exactly the pattern that killed V53's two rule-2 masks on inspection:
**tightening the mask did not remove the bull-majority artifact, it
concentrated it.** V21's finding stands — direction edge here is
regime-conditional, and no static cross-product mask encodes that.

## The two KEEPs

- **EMA Crossover** fails CONFIRM twice over: the FIT selection
  (`bullish + {2w}`, the single admissible cell out of 20) flips to
  **−0.098** on the held-out half, at N=28, which is itself below `MIN_N`.
  This is the guard doing precisely its job — a one-cell selection on FIT that
  does not survive the tickers it was not chosen on. It stays ungated.
- **RSI** has **zero admissible cells**: no (direction, horizon) cell its
  current `bullish` mask admits clears `ExpR > 0` at `N ≥ 30` on FIT in 25
  years. Per rule 3 this is **reported, not auto-disabled** — there is no
  "disable strategy" primitive in `STRATEGY_GATES` and inventing one here
  would be scope creep. It is a strong enough statement to deserve a human
  decision about dropping the strategy outright.

## The adoption decision — NOTHING ADOPTED, by human-partner directive

**Decided 2026-08-05: all eleven masks stay unchanged.** `STRATEGY_GATES` in
`strategy_types.py` is untouched.

The mechanical ladder says ADOPT for nine. Five are no-ops. The remaining four
are genuine, strictly non-loosening tightenings whose **entire justification is
an expectancy the +0.318R bias cannot distinguish from zero**, and whose
per-regime tables show the retained cells are still bull-market artifacts.

Adopting them on *risk-reduction* grounds ("fewer signals in cells with no
demonstrable edge") was considered and **declined**. It is a defensible
position, but it is **not the justification the ladder used**, and swapping in
a post-hoc rationale after seeing the numbers is the exact failure mode this
pre-registration was written to prevent.

The one argument that would have rescued it — that the +0.318R bias is a level
shift, so the *relative* ordering the ladder selects on survives even though
the absolute sign does not — **does not hold here**. V51's bias is a daily-bar
resolution artifact that varies with horizon and stop distance, and these masks
select *on horizon*, so the assumption is weakest exactly where it would have
to be strongest.

As with V53, this is a **human-partner directive, not a rule failure**, and
the distinction must not be blurred: the ladder ran clean and its verdicts
stand as recorded. Note the asymmetry from V53 that makes this the *second*
non-adoption for a different reason — V53's masks were rejected for
**loosening**, V54's for resting on a **null**. A third re-derivation should
expect to be told something new before it is worth the compute.

**RSI:** decided 2026-08-05 to **record and change nothing**, per rule 3. The
zero-admissible-cell result stands as a documented finding; RSI keeps its
current `bullish` mask. Dropping the strategy would be a code change, not a
mask edit, and would need its own task.

## What a successor would have to do differently

V53 (mildest-first) and V54 (strictest-first) have now bracketed the static
cross-product mask space from both ends and returned nothing adoptable. The
remaining moves are **not** a third ladder over the same space:

1. **Fix the measurement, not the mask.** Every verdict here was decided by
   the +0.318R bias. Until V51's daily-bar overstatement is reduced — hourly
   fidelity, i.e. V23 — no expectancy-sign rule over this data can adopt
   anything, because the discriminating threshold sits above nearly every
   cell.
2. **Change the mask's shape.** V21's regime-conditionality finding is now
   confirmed from a third direction: these tightenings concentrated the bull
   artifact instead of removing it. That is a property of static masks, not of
   the ladder. `REGIME_GATES_ENABLED` + `REGIME_ALLOW` is the structural fix.

## What this run did *not* establish

- **No validation budget was spent.** V24's one shot stays held. These are
  TRAIN-selected, CONFIRM-checked figures — a within-TRAIN generalisation
  test, not a validation shot.
- **It did not find a passing configuration**, and could not. V52's Stage 1
  bar (Wilson LB > 60%) is cleared nowhere here.
- **Survivorship runs the same direction in both halves** and is uncorrected,
  per V21 Test B.
- **The ladder could not move a mask, only shrink one** — stated in advance.
  A better mask reachable only by loosening one axis to tighten another was
  out of scope by construction.
