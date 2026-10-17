# v163 — Idea screen: a trailing-exit race shape for momentum ideas

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** none — backtesting instrument only (`swingbot/core/backtesting/screen/`, `scripts/backtest/screen_idea.py`); no running bot or UI code changes.
**Edge:** none (integrity) — an instrument, never a lift by itself. It lets the momentum class of entries be measured without a profit target clipping their right tail; any edge it finds still has to earn a `SCREEN-PASS` and then the unchanged funnel.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-10-15 from a brainstorm with the partner (research pass on famous swing and quant traders; trail rule chosen: chandelier 3 ATR); panel review applied (see the end).

## Why

The Stage −2 screen (`backtest-methodology.md` § Funnel stages) races every
event through one fixed trade: entry at the next open, stop 1.5 × ATR14, target
3 × ATR14, an idea-specific time cap (`swingbot/core/backtesting/screen/race.py`).
That shape suits mean reversion: many small wins, short holds. The one
`SCREEN-PASS` (`screen-uptrend_pullback`) is a mean-reversion idea.

Momentum and trend traders (Turtles, Minervini, Qullamaggie, Clenow) earn
the other way: a low win rate and a few very large winners, held for weeks.
A 3 ATR target clips exactly the right tail that carries that kind of
expectancy. This spec adds **a** trailing exit — one chosen, mechanical
shape — so breakout and momentum ideas can be raced without a target. It is
not any one trader's exit: Qullamaggie trails a 10/20-day average on a daily
close, Minervini raises a fixed stop then trails averages, Clenow rebalances
on a schedule. A chandelier stop is a neutral stand-in for "let winners run",
not a replica of theirs.

### What a verdict under this shape means — and does not

- **Biased against, not for, the ideas it serves.** ATR is frozen at the
  event bar. Breakouts leave low-volatility bases, so ATR14[t] understates
  the later range; a 3 ATR trail on it sits closer to noise than a live
  chandelier on current ATR would, and shakes out winners a trader would
  hold. A trail `SCREEN-FAIL` is "no edge under this exit", never "the
  idea has no edge" — but it is still closed, like every fail.
- **A pass is not tradeability.** The live bot places one fixed stop at
  alert time. A trail stop must be moved each evening; until a stop-update
  path exists (nightly, after the close of j−1 — exactly the one-bar lag the
  race uses), a trail `SCREEN-PASS` buys a spec, not alerts.
- **A pass is unlikely to reach Tier 1.** After a pass the idea runs the
  unchanged funnel, whose badge threshold needs WR ≥ 50% and scratches
  plus timeouts ≤ 50% of closed trades (`backtest-methodology.md` § Badge
  scoring). A low-win-rate, long-hold trend idea meets neither easily and
  reaches Tier 2 at best; v113 Part B failed all 22 cells on that floor.
  Win rate stays a constraint (root `CLAUDE.md` § Prioritise expectancy).

### Closed ideas stay closed, under either shape

The trigger of **any** idea with a `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`
ledger row — today `screen-high52w`, `screen-gap_volume`,
`screen-turn_of_month`, and every future one — never returns under the other
shape, renamed or not (`backtest-methodology.md` § Closed pre-registrations).
A closed fixed-shape fail is not evidence the shape was wrong.

## Design

### One shape per idea, frozen with the idea

An idea module gains an optional `RACE` constant: `"fixed"` (default) or
`"trail"`. `Idea` gains `race_shape: str = "fixed"`, validated against
`RACE_SHAPES = ("fixed", "trail")` in `__post_init__`; `_load` reads
`getattr(module, "RACE", "fixed")`. The six existing ideas declare nothing
and stay `fixed`.

An idea is raced under exactly one shape. Running both and keeping the
better verdict is a second look at one hypothesis, so:

- `tests/backtesting/screen/test_ideas_registry.py` pins every registered
  idea's `race_shape` beside its frozen parameters; flipping a shape means
  editing a pinned test in the same diff, visibly.
- The shape is part of the definition `/screen` Step 2 commits before any
  run; a changed shape is a new idea with a new name.
- A dry run is already limited by the guardrails hook (`_rule_screen_rerun`)
  to at most three tickers — far below N = 300, so it can never show a
  verdict to choose a shape from. That limit is now load-bearing for this
  rule too; `tests/hooks/test_guardrails.py` already pins it.

**A trail idea freezes `CAP` ≥ 60 bars.** With no target, the cap does the
job the 3 ATR target did: a short cap turns the trail back into a
fixed-horizon trade. 60 bars (about three months) matches `high52w`, the
longest existing cap. `_load` refuses a trail idea with `CAP < 60`.

### The trail race

Event on bar t, known at t's close. Long only, as today.

- **Entry:** open of t+1. **Risk:** 1R = 1.5 × ATR14[t]. **Initial stop:**
  entry − 1R. **No target.** `r` is always measured in that initial 1R,
  never in the current stop distance, so R means the same unit in both
  shapes; commission is `commission_r()` divided by the same 1R.
- **Trailing stop (chandelier, `TRAIL_ATR = 3.0`):** the stop in force on
  bar j (j ≥ t+1) is
  `stop_j = max(entry − 1R, max(High[t+1 .. j−1]) − 3 × ATR14[t])`.
  It reads only bars before j: a daily bar does not say whether its high
  came before its low, so bar j's own high never raises bar j's stop. The
  stop never moves down. ATR is frozen at t (see "Biased against" above).
- **Numerics:** the running maximum is computed over the event's high
  matrix shifted one column right, with column 0 filled with `-inf` (never
  NaN: a NaN would propagate through `np.maximum.accumulate`, make every
  comparison False and silently turn the stop off). `load_frame` already
  drops rows with any NaN OHLCV, and a test pins that a row is never left
  stop-less.
- **Exits, checked in order on each bar j**, with `raised_j = stop_j >
  entry − 1R` (strictly):
  1. open ≤ `stop_j` → exit at the open: `gap_stop` if not raised,
     `gap_trail` if raised (a gap through a raised stop can be a gain).
  2. else low ≤ `stop_j` → exit at `stop_j` — the per-event, per-bar
     level, indexed `[row, j]`, never the initial stop: `stop` if not
     raised, `trail` if raised.
  3. after bar t+cap with no exit → exit at its close: `timeout`.
  The trail race has its own exit function; it does not reuse
  `race._first_exit`, whose stop price is one scalar per row.
- **Costs:** identical to the fixed race — both fills worsened by
  `SLIPPAGE_BPS`, then commission. A touch fill at exactly `stop_j` is the
  fixed race's convention too; because a trail stop sits close to price
  after a rally, it matters more here, so the results doc also prints the
  trail book re-priced at 2 × `SLIPPAGE_BPS` (ΔExpR and its interval).
  That line is printed, never gating — like forward drift today.
- **Entry gaps:** breakout-day names often gap at the next open; entry at
  that open, with `SLIPPAGE_BPS`, is the stated assumption, unchanged.

`OUTCOMES` gains `"trail"` and `"gap_trail"`, appended, so existing outcome
codes keep their indices. A trail race never produces `gap_target` or
`target`; a fixed race never produces `trail` or `gap_trail`.

### What does not change

- The matched null (`null.matched_null`): same K = 20, same ticker, month and
  trend state, raced with **the idea's shape** — a trail idea's null is a
  trail null. `null.eligible_mask` already takes the idea's `cap` for its
  window test; a longer trail cap raises `dropped_window` for events and
  null alike.
- The one-open-race-per-ticker rule (`race.non_overlapping`), the warm-up
  mask, the window (2010–2019, events from 2011) and the PIT S&P 500
  universe.
- The four pass clauses (`verdict.py`): ΔExpR ≥ +0.10R, lower 95%
  week-clustered bound > 0, ≥ 7 of 9 years positive, N ≥ 300. The trail
  shape's fatter tail widens the bootstrap interval by itself; that is the
  price of measuring a fat-tailed trade, not grounds for a different
  threshold.

### Code shape

- New `swingbot/core/backtesting/screen/trail.py`: `race_trail(df,
  event_pos, cap, *, atr=None, slippage_bps=None, commission=None) ->
  RaceResult`, vectorised over events like `race.race`, with its own
  `_first_exit_trail`. Reuses `race.STOP_ATR`, `RaceResult`,
  `_check_positions` and the frictions.
- `race.py`: a dispatcher `race_for(shape)` returning `race` or
  `trail.race_trail`; `run_book` takes `shape` (default `"fixed"`) and
  calls through it.
- `null.py`: `matched_null` takes `shape` (default `"fixed"`) and races its
  bars through `race_for(shape)` (today `race_mod.race`, `null.py:89`).
- `scripts/backtest/screen_idea.py`: `screen_ticker` passes
  `idea.race_shape` to `run_book` and `matched_null`. Rendering is per
  shape: the trade line, and the event/null outcome-mix table, list only
  that shape's outcomes (fixed: the five it has today), so **a fixed idea's
  results doc and ledger row stay byte-identical to today's** (pinned by a
  test). A trail idea's doc also prints, next to N: the overlap-skip count,
  the timeout share and mean timeout R for event and null books, and the
  2 × slippage line. The ledger `hypothesis` text names the shape and cap
  (`chandelier 3.0 ATR trail race, initial stop 1.5 ATR, cap 60`).
- `docs/claude/backtest-methodology.md` § Funnel stages: the Stage −2
  bullet names both shapes, states one shape per idea, the trail cap floor
  and that the pass rule is the same for each. `AGENTS.md` mirrored.
- Every function stays under complexity 15.

## Testing

- **Trail fixtures:** a rise that ratchets the stop (asserting each
  `stop_j`, and that it never loosens); a reversal exiting as `trail` at
  the raised `stop_j`, not the initial stop; an initial-stop exit labelled
  `stop`; a gap through the initial stop (`gap_stop`) and through a raised
  stop above entry (`gap_trail`, positive R); a timeout at the cap's close;
  a bar whose own high would have raised the stop it is tested against
  (it must not); a first bar (empty high term) whose low touches the
  initial stop (exits — the `-inf` fill works).
- **No lookahead:** an event's result is unchanged by bars after its exit,
  on a fixture and a `random_walk`.
- **Fixed path unchanged:** the existing race, null and screen-script tests
  pass untouched; `run_book(..., shape="fixed")` equals the pre-change call
  on a random walk; a fixed idea's rendered results doc is byte-identical.
- **Registry:** `race_shape` pinned per idea (`"fixed"` for all six); an
  unknown shape raises `ValueError`; a trail idea with `CAP < 60` raises.
- **A/A calibration** (`scripts/backtest/screen_trail_calibration.py`, a
  results doc, not a unit test): 200 seeded replicates of a fat-tailed,
  volatility-clustered synthetic universe (Student-t innovations, df = 3,
  with a two-state volatility regime; seed and generator parameters
  recorded), random "events" with no planted effect, raced trail-vs-trail
  null through the real verdict. Reported: coverage of the 95% interval
  for ΔExpR = 0 and the full-verdict false-pass rate. Acceptance: false-pass
  rate ≤ 5% (a pass rule tighter than its interval should rarely pass
  noise); coverage is reported, not gated. One small replicate runs in the
  unit suite as a smoke test. It never touches the 2010–2019 cache.
- Tests stay in `tests/backtesting/screen/`, already in a suite.

## Out of scope

- **Freezing the first trail idea** (Qullamaggie's consolidation breakout is
  the candidate). A separate commit, under `/screen` Step 2, after this
  instrument ships.
- A live stop-update path (nightly trail edits for alerts). Needed before a
  trail idea can reach alerts; its own spec.
- Any change to the fixed shape, the null, the pass rule or the funnel
  beyond Stage −2.
- Short ideas (the screen stays long-only).
- Other trail rules (moving-average close, Donchian low) and trail-multiple
  sensitivity. One shape was chosen; another is a new spec.

## Parallelisation

Sequential: `trail.py` first (the race), then the dispatcher and
`null.py` (they call it), then `screen_idea.py` rendering and ledger text
(it reads the shape), then the calibration script (it drives the whole
screen), the methodology doc amendment, and the full suite. Each step
consumes the previous one's interface; only the doc amendment could run
beside the calibration script.

## Panel review

2026-10-15, on `192e26c6`.

- quant-researcher [BLOCKING]: only two closed ideas fenced off; `turn_of_month` and future fails were not — applied (general rule, § Closed ideas stay closed).
- quant-researcher [BLOCKING]: a dry run could pick the shape post hoc — applied (shape pinned in the registry test, committed with the definition; the three-ticker dry-run limit named as load-bearing).
- quant-engineer [BLOCKING]: trail exit must price at the per-bar raised `stop_j`, not the initial stop — applied (own `_first_exit_trail`, `[row, j]` indexing, fixture).
- quant-engineer [BLOCKING]: the empty high term on bar t+1 must be `-inf`, never NaN — applied (§ Numerics, fixture).
- veteran-trader [BLOCKING]: touch fill at `stop_j` is optimistic for a close-riding trail, and a moving stop has no live path — applied in part: the 2 × slippage line is printed, not gating (a gating clause would change the pass rule, which this spec does not touch); the live stop-update path is named out of scope, and a pass is stated as not tradeable until it exists.
- veteran-trader [BLOCKING]: "raced the way those traders manage winners" was overstated — applied (Why reworded: a trailing exit, not theirs).
- quant-researcher [ADVISORY]: the cap is the trail's main free parameter — applied (cap ≥ 60, timeout share and mean timeout R reported). veteran-trader [ADVISORY] on the cap merged here.
- quant-researcher / quant-engineer [ADVISORY]: a single A/A interval calibrates nothing; Gaussian walks lack fat tails — applied (200 seeded fat-tailed replicates, false-pass rate gated at ≤ 5%).
- quant-researcher [ADVISORY]: report overlap drops next to N — applied.
- quant-researcher [ADVISORY]: WR ≥ 50% Tier 1 floor makes Tier 2 the likely ceiling — applied (§ What a verdict means).
- quant-researcher [ADVISORY]: outcome mix per book — applied (per-shape event/null outcome table; the table already exists for fixed ideas).
- quant-researcher [ADVISORY]: methodology doc still describes one shape — applied (amendment in § Code shape).
- quant-engineer [ADVISORY]: `stop` vs `trail` label rule; profitable gap through a raised stop mislabelled — applied (`raised_j` strict, new `gap_trail` outcome).
- quant-engineer [ADVISORY]: byte-identical claim false because `OUTCOMES` grows — applied (rendering per shape, pinned by a test).
- quant-engineer [ADVISORY]: function names wrong (`null.draw`) — applied (`null.matched_null`, `screen_ticker`).
- quant-engineer [ADVISORY]: state R is per initial 1R — applied.
- quant-engineer [ADVISORY]: longer cap changes `dropped_window`; cap frozen with shape — applied.
- veteran-trader [ADVISORY]: one-bar lag matches a nightly stop update — applied (named in § A pass is not tradeability).
- veteran-trader [ADVISORY]: frozen ATR biases against breakouts from quiet bases — applied (§ Biased against).
- veteran-trader [ADVISORY]: report gap and trail exit shares — applied (outcome table per shape).
- veteran-trader [ADVISORY]: entry-gap assumption on breakout names unstated — applied (§ The trail race, Entry gaps).
- veteran-trader [ADVISORY]: confirms gap-through exit at the open — no change needed.
