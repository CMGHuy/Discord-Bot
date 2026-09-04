# v68 — Dead-cat-bounce veto on the confluence scan

**Version:** ui 1.10.0 · bot 1.5.0
**Bump:** bot patch (1.5.0 → 1.5.1) — actual close-out bump is bot 1.6.0 →
1.6.1: a `main`-sync merge onto this branch (bringing in other plans' work,
predating D1) moved bot past 1.5.0 before this component's own code landed.
The bump TYPE prediction (patch, inert default-off code) held
**Edge:** expectancy — measured: none. VALIDATION FAILed (2 of 4 gates; ExpR
delta -0.0097R, opposite sign from TRAIN's +0.0104R) — see
`docs/superpowers/results/2026-08-30-v68-dcb-veto-validation.md`. Ships
merged and default-off, not as a demonstrated edge.

Introduce chart-pattern geometry to the bot for the first time, as a **veto**
on the confluence scan rather than as another confluence voter: block a bullish
support scenario when the frame shows a dead cat bounce — a violent decline,
a weak retracement, and no conviction behind the bounce.

## Why now, and why a veto rather than a signal

The obvious version of "add chart patterns" is to detect double tops, head and
shoulders and cup-and-handle, and feed them into `count_confirming_strategies`
as additional voters. **That is a measurably dead branch**, and this repo has
already closed it twice:

- **v49** measured cross-family redundancy across every confluence source over
  707,655 candidate prices: mean off-diagonal **0.628** (Bollinger/Donchian
  0.887, Fibonacci/Zigzag 0.838, EMA/VWAP/AVWAP 0.79–0.83). The participation
  ratio saturates at **N_eff ≤ 1.746** across all 4,095 non-empty family
  subsets. A twelfth correlated level-source adds no information.
- **v36** tested the primitive that sits underneath double top and double
  bottom — grading a level by its touch and rejection history. Win rate
  37.09% → 36.32%, expectancy 0.0670R → **0.0057R**, alert volume −62.9%.
  Filed under `no-lift/`.

Meanwhile the population those voters feed is the one losing money. Pooled
VALIDATION 2024–25 puts the confluence scan at **53.5% win rate, −0.171R over
4,641 trades** — the largest population in the book and the only negative one.
`backtest_scenarios.py`'s own docstring records that it already failed a
pre-registered TRAIN grid: *"failed at every one of the 6 (min_confluence,
min_risk_reward) grid points tested … every expectancy_r was negative."* The
80% win-rate bar in that rule was superseded by 50% in v31, so its best
observed 66.4% would clear today — but **the `expectancy_r > 0` gate is
unchanged, and every grid point failed it.**

So the question worth asking is not "which patterns can we add" but "does any
pattern geometry carry information about *why this population loses*".

One does. `levels.build_scenarios` (`levels.py:643`) gates a scenario on
**geometry alone** — reward distance, stop distance, risk:reward. There is no
trend filter, no momentum filter, and no measure of how violently price arrived
at the level. The scan will build "bullish toward resistance" in a stock that
fell 40% in three weeks, because `supports[0]` exists and the arithmetic
clears. The only falling-knife guard anywhere in the codebase is
`close > close.shift(3)` at `entry_filters.py:540` — a three-bar check, on the
strategy path, which never touches the confluence path at all.

**Decline magnitude is encoded nowhere.** That is the gap this spec fills, and
it is why this is a new hypothesis rather than v36 in new clothing: v36 graded
*a level* by its own history; this grades *the approach to it*.

## The honest alternative, recorded rather than buried

If the confluence population is negative and a TRAIN grid already found no
qualifying configuration, the highest-expectancy action may be to **gate
confluence alerts far harder, or off** — "removes a negative-expectancy
population" is an `Edge: expectancy` mechanism in its own right, and it is
cheaper than this spec.

This spec chooses the scalpel over the hammer on one argument: a blanket cut
removes good and bad setups indiscriminately, and if freefall names are a
*concentrated* slice of the loss, a targeted veto keeps the rest. That argument
is a hypothesis, not a finding. If TRAIN shows the veto's alert-volume cut
buying little expectancy, the hammer becomes the better next shot and this
result is what says so.

## Decisions taken

Settled during the brainstorm; recorded so the plan does not reopen them.

| Question | Decision |
|---|---|
| Role of pattern geometry | **Veto**, not a confluence voter and not a confidence factor |
| Which pattern | Full dead-cat-bounce structure (decline + gap + weak retracement + volume) |
| Direction | **Bullish scenarios only** |
| Enforcement | Hard block, not a confidence penalty |
| Hook point | `build_scenarios(..., block_bullish: bool)`; the frame stays out of it |
| Measurement harness | `backtest_scenarios.py` (confluence replay), **not** `run_backtest_range.py` |
| Default | `false` until VALIDATION passes |

**Hard block, not a confidence factor**, because v36's confidence-factor arm
degraded both win rate and expectancy when filtered at level ≥ 4. A binary
block has a cleaner kill criterion and cannot quietly reshape the grading of
trades it does not remove.

**Bullish only.** A dead cat bounce is definitionally a downside pattern; the
mirror ("shorting a weak pullback in a melt-up") is a different pattern under a
borrowed name. The v34 RS_GATE precedent supports one-sided gates directly —
its symmetric arm was dead at every threshold in the grid while a single arm
survived.

## The measurement path — the part that burns shots

`DATA_DRIVEN_STOPS_ENABLED` is this repo's cautionary tale: it *"scored 0.0000
and burned its shot — it reached `build_strategy_plan` but the backtest sized
through `_trade_plan_at`, so it was unmeasurable by construction."* A
pre-registration spent on something the harness cannot see produces nothing.

Both paths were traced before this design was written:

| Path | Driven by | Reaches `build_scenarios`? |
|---|---|---|
| Strategy | `backtest.py` → `entry_filters.entries_for` | **No** |
| Confluence | `backtest_scenarios.py` → `levels.build_scenarios` | **Yes** |

A veto hooked into `build_scenarios` is therefore visible to
`backtest_scenarios.replay_scenarios` and invisible to `run_backtest_range.py`.
That harness already exists, has six callers, rebuilds the level map per bar
and guarantees no lookahead (*"every computation sees `df.iloc[:i+1]` only"*).
**No new instrument is needed** — unlike v34's RS_GATE, which had to build
`measure_rs_gate_effect.py` because the replay harness could not see it.

## Architecture

One new module, `swingbot/core/market/chart_patterns.py`, with one public
function:

```python
def dead_cat_bounce(df: pd.DataFrame, params: dict) -> dict:
    """{"detected": bool, ...evidence} for the bar at df.index[-1]."""
```

Pure — frame in, verdict out, no I/O, no config reads. Testable in isolation
against the synthetic builders already in `tests/conftest.py` (`make_ohlcv`,
`make_trend_df`), which is why the frame is a parameter rather than something
the function fetches.

`levels.build_scenarios` gains exactly one keyword:

```python
def build_scenarios(current_price, supports, resistances, min_reward_pct, ...,
                    block_bullish: bool = False) -> list:
```

**`build_scenarios` does not take the frame.** Each call site computes the
verdict where the frame already is and passes the boolean down. That keeps the
function pure and keeps "what qualifies" in the one place whose docstring
already says *"A scenario failing ANY of these is simply not built."* The
existing `constraints` dict gains a `not_dead_cat_bounce` entry, matching the
shape downstream display code already reads.

Two call sites, one gate:

- `analyze.py:619` — live scan, frame in scope as `df`
- `backtest_scenarios.py:100` — replay, frame in scope as the no-lookahead
  `window`

Same function at both, so live and backtest cannot disagree — the discipline
`entry_filters.py` already enforces for the strategy path.

## Detection rule

For the bar at `df.index[-1]`, using **trailing windows and positive shifts
only** per the NO-LOOKAHEAD RULE:

1. **Trough** — index of the minimum close in the last `LOOKBACK` bars, which
   must be at least `BOUNCE_MIN_BARS` before the current bar.
2. **Peak** — maximum close strictly before the trough, inside the window. If
   the trough is the window's first bar there is no such peak, and the verdict
   is `False`: the decline began before the window, so its magnitude is not
   measurable from the data in hand and must not be guessed at.
3. **Decline** — `(peak − trough) / peak ≥ DECLINE_PCT`. **Evaluated before
   clause 5**, which divides by `peak − trough`; clause 3 passing is what
   guarantees that denominator is positive.
4. **Bouncing now** — `close > trough`.
5. **Bounce is weak** — `(close − trough) / (peak − trough) ≤ RETRACE_MAX`.
6. **Gap arm** (when `GAP_REQUIRED`) — some bar between peak and trough opened
   at least `GAP_PCT` below the prior close.
7. **Volume arm** (when `VOLUME_RATIO` is set) — mean volume over the bounce
   bars ÷ mean volume over the decline bars ≤ `VOLUME_RATIO`.

All seven must hold. A frame shorter than `LOOKBACK + BOUNCE_MIN_BARS` returns
`detected: False` — a rule that cannot be computed blocks nothing, matching
`entry_filters.py`'s convention that an uncomputable gate never passes a trade
it has not actually cleared.

### Parameters — most fixed on theory, not tuned

The overfit surface is the acknowledged cost of choosing the full structure
over a minimal magnitude test. It is mitigated by fixing four of the seven
parameters from reasoning rather than from the grid:

| Parameter | Value | Fixed or gridded | Why this value |
|---|---|---|---|
| `LOOKBACK` | 20 bars | **Fixed** | ~1 trading month, the span a sharp decline occupies |
| `RETRACE_MAX` | 0.50 | **Fixed** | Fibonacci midpoint; past half the decline it is not "dead" |
| `BOUNCE_MIN_BARS` | 2 | **Fixed** | A bounce, not one green candle |
| `GAP_PCT` | 5.0% | **Fixed** | A real breakaway gap; read only when the gap arm is on |
| `DECLINE_PCT` | 15 / 20 / 25 | Gridded | The one magnitude threshold worth learning |
| `GAP_REQUIRED` | on / off | Gridded | Fidelity to the pattern vs. population size |
| `VOLUME_RATIO` | 0.8 / off | Gridded | Conviction test vs. population size |

**12 TRAIN cells** — comparable to v34's threshold grid and the 6-point
confluence grid, not a fishing expedition.

## Scope limits, stated rather than discovered later

- **This does not catch every falling knife.** Requiring an actual bounce
  (clause 4) means a still-collapsing stock passes the veto. That is what the
  full dead-cat-bounce structure means; a broader freefall veto is a different
  hypothesis needing its own shot.
- **Bearish scenarios are untouched.** Nothing here blocks shorting into
  support.
- **The strategy path is untouched.** The eleven `STRATEGY_FUNCS` entries and
  their VALIDATED/WEAK badges are unaffected — this veto is invisible to
  `run_backtest_range.py` by construction.

## Measurement

**TRAIN 2020-01-01..2023-12-31** via `backtest_scenarios.py`, veto-off versus
veto-on for each of the 12 cells.

Pre-registered selection rule, quoted here so the plan cannot restate it
loosely: **the cell with the greatest pooled ExpR improvement over the veto-off
baseline, among cells with N ≥ 30 surviving trades and an alert-volume cut
≤ 30%.**

**If no cell clears that rule, the measurement is finished and VALIDATION is
not spent.** The empty table is the answer, and this spec closes under
`no-lift/` exactly as v36 and v49 did. A negative result closes a component; it
does not re-open it with looser thresholds.

**VALIDATION 2024-01-01..2025-12-31** is one shot on the single TRAIN winner.
Gates: `expectancy_r > 0`, `win_rate ≥ 50`, `N ≥ 15`, scratches+timeouts ≤ 50%
of closed trades. The default flips `false` → `true` only if all four hold.

### The main threat: population size

Gap **and** weak bounce **and** low volume together is a narrow filter. It
could plausibly produce fewer than 30 surviving TRAIN trades, which is how a
shot gets burned producing no data rather than a negative result.

The `off` arms on both `GAP_REQUIRED` and `VOLUME_RATIO` exist for this reason:
at least four of the twelve cells are permissive enough to generate population.
Cells that return `hard-gate:below-min-n` are recorded as such in the results
document, not quietly dropped — a cell with no data is a different fact from a
cell that measured badly.

## Testing

- **Unit** — `dead_cat_bounce` against synthetic frames from
  `tests/conftest.py`: a textbook DCB detects; a V-shaped recovery past 50%
  does not; a shallow decline does not; a still-falling frame does not (clause
  4); a short frame returns `False`; the gap and volume arms each flip a
  borderline case on and off.
- **No-lookahead** — a test asserting the verdict for bar `i` is unchanged when
  the frame is truncated at `i`, the same property `entry_filters.py` tests.
- **Integration** — `build_scenarios` with `block_bullish=True` builds no
  bullish scenario and leaves the bearish one untouched; the `constraints` dict
  records the veto.
- **Parity** — the live and replay call sites pass the same params, so one
  helper builds them and a test asserts both sites use it.

## Parallelisation

- **Sequential: the detector before the hook.** `build_scenarios` and both call
  sites consume `dead_cat_bounce`'s signature; writing them first would mean
  writing them twice.
- **Parallel: the unit tests and the no-lookahead test** — same module, but
  independent test files with no shared fixture state.
- **Sequential: the TRAIN grid after everything.** It is the deliverable, and
  it cannot run against a half-wired gate.
- **Sequential and absolute: VALIDATION after TRAIN, once, on one cell.** Not a
  parallelisation note but the methodology's hardest rule, repeated here
  because it is the one a concurrent session could most expensively break.

## Success criteria

1. `dead_cat_bounce` detects the textbook structure and rejects V-recoveries,
   shallow declines and still-falling frames, proven by unit tests.
2. The verdict is provably causal — truncating the frame at bar `i` does not
   change bar `i`'s answer.
3. The live scan and the replay harness produce identical veto decisions for
   the same frame and params.
4. A TRAIN grid over all 12 cells is recorded in
   `docs/superpowers/results/`, with the selection rule quoted and every
   `hard-gate:below-min-n` cell named.
5. Either one cell clears the pre-registered rule and earns a VALIDATION shot,
   **or** none does and this component closes without spending it.
6. `python scripts/dev/testrun.py full` is green — `0 failed`, `0 xfailed`.
