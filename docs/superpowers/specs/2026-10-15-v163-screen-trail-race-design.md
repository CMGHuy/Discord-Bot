# v163 — Idea screen: a trailing-exit race shape for momentum ideas

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** none — backtesting instrument only (`swingbot/core/backtesting/screen/`, `scripts/backtest/screen_idea.py`); no running bot or UI code changes.
**Edge:** none (integrity) — an instrument, never a lift by itself. It lets the momentum class of entries be measured fairly; any edge it finds still has to earn a `SCREEN-PASS` and then the unchanged funnel.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-10-15 from a brainstorm with the partner (research pass on famous swing and quant traders; trail rule chosen: chandelier 3 ATR).

## Why

The Stage −2 screen (`backtest-methodology.md` § Funnel stages) races every
event through one fixed trade: entry at the next open, stop 1.5 × ATR14, target
3 × ATR14, an idea-specific time cap (`swingbot/core/backtesting/screen/race.py`).
That shape suits mean reversion: many small wins, short holds. The one
`SCREEN-PASS` (`screen-uptrend_pullback`) is a mean-reversion idea.

Momentum and trend traders (Turtles, Minervini, Qullamaggie, Clenow) earn
the other way: a low win rate and a few very large winners, held for weeks
with a trailing stop. A 3 ATR target clips exactly the right tail that
carries their expectancy, so the fixed race measures a different trade than
the one these setups take. Breakout and momentum ideas (Qullamaggie's
consolidation breakout, Clenow's regression-slope ranking, Minervini's trend
template) cannot get a fair verdict until the screen can race them with a
trailing exit.

This spec does **not** reopen anything. `screen-high52w` and
`screen-gap_volume` stay closed under the one-shot rule; neither returns
under the trail shape, renamed or not (`backtest-methodology.md` § Closed
pre-registrations).

## Design

### One shape per idea, declared when it is frozen

An idea module gains an optional `RACE` constant: `"fixed"` (default) or
`"trail"`. `Idea` gains `race_shape: str = "fixed"`, validated against
`RACE_SHAPES = ("fixed", "trail")` in `__post_init__`; `_load` reads
`getattr(module, "RACE", "fixed")`. The six existing ideas declare nothing
and stay `fixed`.

An idea is raced under exactly one shape, its own. Running both shapes on
one idea and keeping the better verdict is a second look at the same
hypothesis. The shape is part of the frozen definition: a changed shape is a
new idea with a new name, like a changed parameter.

### The trail race

Event on bar t, known at t's close. Long only, as today.

- **Entry:** open of t+1. **Risk:** 1R = 1.5 × ATR14[t], so R means the same
  unit in both shapes. **Initial stop:** entry − 1R. **No target.**
- **Trailing stop (chandelier, 3 ATR):** the stop in force on bar j
  (j ≥ t+1) is
  `stop_j = max(entry − 1R, max(High[t+1 .. j−1]) − 3 × ATR14[t])`;
  on j = t+1 the high term is empty and `stop_j` is the initial stop. It
  only reads bars before j: a daily bar does not say whether its high came
  before its low, so bar j's own high never raises bar j's stop. The stop
  never moves down. ATR is frozen at t.
- **Exits, checked in order on each bar j:** an open at or below `stop_j`
  exits at that open (`gap_stop`; can be worse than −1R); else a low at or
  below `stop_j` exits at `stop_j` — outcome `stop` when `stop_j` is still
  the initial stop, `trail` once it has been raised. After bar t+cap with
  no exit, exit at its close (`timeout`).
- **Costs:** identical to the fixed race — both fills worsened by
  `SLIPPAGE_BPS`, then `commission_r()` in R.

`OUTCOMES` gains `"trail"` (appended, so existing outcome codes keep their
indices). A trail race never produces `gap_target` or `target`.

### What does not change

- The matched null (`null.py`): same K = 20, same ticker, month and trend
  state. Null bars are raced with **the idea's shape** — a trail idea's null
  is a trail null.
- The one-open-race-per-ticker rule (`non_overlapping`), the drop counters,
  the warm-up mask, the window (2010–2019, events from 2011) and the PIT
  S&P 500 universe.
- The four pass clauses (`verdict.py`): ΔExpR ≥ +0.10R, lower 95%
  week-clustered bound > 0, ≥ 7 of 9 years positive, N ≥ 300. The trail
  shape's fatter tail widens the bootstrap interval by itself; that is the
  honest price of measuring a fat-tailed trade, not grounds for a different
  threshold.

### Code shape

- New `swingbot/core/backtesting/screen/trail.py`: `race_trail(df,
  event_pos, cap, *, atr=None, slippage_bps=None, commission=None) ->
  RaceResult`, vectorised over events like `race.race` (a running maximum
  of the high matrix, shifted one column, gives every `stop_j`).
  Constants `TRAIL_ATR = 3.0`; it reuses `race.STOP_ATR`, `RaceResult`,
  `_check_positions` and the frictions.
- `race.py`: one dispatcher `race_for(shape)` returning `race` or
  `trail.race_trail`; `run_book` and `null.draw` take a `shape` argument
  (default `"fixed"`) and call through it. The fixed path's arithmetic does
  not change.
- `scripts/backtest/screen_idea.py`: passes `idea.race_shape` down;
  `_render_head` prints the trail trade line for a trail idea; the ledger
  `hypothesis` text names the shape (`fixed 1.5/3.0 ATR race` or
  `chandelier 3.0 ATR trail race, initial stop 1.5 ATR`). A fixed idea's
  results doc and ledger row are byte-identical to today's.
- Every function stays under complexity 15.

## Testing

- **Trail fixtures:** a rise that ratchets the stop (asserting each
  `stop_j` and that it never loosens), a later reversal exiting as `trail`
  at the raised stop, an initial-stop exit labelled `stop`, a gap through
  the stop exiting at the open, a timeout at the cap's close, and a bar
  whose own high would have raised the stop it is tested against
  (it must not).
- **No lookahead:** `assert_prefix_stable`-style check that an event's
  result is unchanged by bars after its exit, on a fixture and a
  `random_walk`.
- **Fixed path unchanged:** the existing race, null and screen-script tests
  pass untouched; a test pins that `run_book(..., shape="fixed")` equals
  the pre-change call on a random walk.
- **Registry:** `race_shape` defaults to `"fixed"` for all six ideas; an
  unknown shape raises `ValueError`.
- **A/A calibration:** on synthetic random walks with no planted effect,
  "events" drawn at random and raced with the trail shape against the trail
  null give a ΔExpR whose 95% interval covers 0. This proves the instrument
  has no built-in bias between event and null, on synthetic data only —
  it never touches the 2010–2019 cache.
- Tests stay in `tests/backtesting/screen/`, already in a suite.

## Out of scope

- **Freezing the first trail idea** (Qullamaggie's consolidation breakout is
  the candidate). That is a separate commit, under `/screen`'s Step 2, after
  this instrument ships.
- Any change to the fixed shape, the null, the pass rule or the funnel
  beyond Stage −2.
- Short ideas (the screen stays long-only).
- Other trail rules (moving-average close, Donchian low). Chandelier 3 ATR
  was chosen as the one shape; a second trail rule would be a new spec.

## Parallelisation

Sequential: `trail.py` first (the race), then the dispatcher and `null.py`
(they call it), then `screen_idea.py` rendering and ledger text (it reads
the shape), then the full suite. Each step consumes the previous one's
interface.
