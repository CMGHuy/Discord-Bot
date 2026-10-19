# v176 — Runner give-back exit: close the runner 5% off its best price

**Version:** ui 1.30.0 · bot 2.11.0 (at writing)
**Bump:** bot minor — every open runner gains a new, usually tighter stop, and runners already open move to it on the first tick after deploy.
**Edge:** harvest — locks in more of a runner's favourable run before a reversal takes it back. Prediction: pooled paired runner-leg ΔR of unknown sign, with |Δ pooled ExpR| under 0.05R (two earlier runner-tightening rules on the same headroom both closed near 0.01R); not a capture-ratio claim (see `## Measurement`).
**Screen:** harvest-headroom docs/superpowers/results/2026-10-02-v123-runner-headroom.md
**Panel:** risk-manager, veteran-trader, quant-researcher
**Status:** spec written 2026-10-19 from a chat with the partner. Rule, scope (runners after TP1 only) and "apply to open trades now" were all decided by the partner in chat. Revised the same day after the panel (see `## Panel review`). Approved by the partner 2026-10-19, as written: `E` keeps taking extended-hours ticks.

## Why

The RKLB short (plan `47f7fd16-…-376c85`) hit TP1 on 2026-10-15. Its runner
then ran to a low of 49.94 and bounced to about 52.30, giving back about 5%
from its best price. The working stop is still 59.11. That level is the runner
floor (`entry + 2/3 × (TP1 − entry)`). The ATR chandelier trail does not
tighten past it because RKLB's daily ATR is about 4.16, so
`49.94 + 2.5 × 4.16 = 60.35`. On a high-volatility name the trail stays wider
than the floor for the whole run. A runner can then give back most of a large
move before it exits.

The partner's rule: once a trailing runner reverses more than 5% from its best
price, exit and take the profit. Example: long at 50, TP1 75, stop 25. The
price runs to 100, so the give-back stop sits at 95. A fall to 95 closes the
runner.

**The headroom, and the prior.** v123 measured pooled TRAIN runner capture at
70.4% of MFE (mean runner 2.43R against mean MFE 3.77R, n = 3127). That figure
was v123's description of its own baseline, not evidence that the gap can be
captured.

This is the **third** rule aimed at that headroom. Both earlier ones closed
near zero:
- v92 `ADAPTIVE_RUNNER_TRAIL`: ΔExpR between +0.0091R and −0.0045R across 9
  cells;
- v123 `hl_trail`: ΔExpR ≤ +0.0012R, with 29–57 of 8737 trades changing
  outcome (`backtest-methodology.md` § Closed pre-registrations).

The prior is therefore a pooled effect on the order of 0.01R. This rule ships
on the partner's decision, not on a predicted lift.

It is a different mechanism from both: a percent off the post-TP1 extreme,
against v92's ATR tightening and v123's swing-low trail. It reopens no closed
pre-registration.

## The rule

For a plan in `PARTIAL` (TP1 banked, runner open), with `E` the runner's best
price since TP1 (`plan.runner_high_close`: the highest tick for a long, the
lowest for a short) and `p = RUNNER_GIVEBACK_PCT / 100`:

- long: `giveback = E × (1 − p)`
- short: `giveback = E × (1 + p)`

The effective runner stop is the **tightest** of the existing terms and the
give-back level:

- long: `max(working_stop, giveback)`
- short: `min(working_stop, giveback)`

It only ever tightens. The floor and the chandelier keep working unchanged.
When `E` is `None` (no tick seen since TP1), there is no give-back term.

**The level is always a win; the fill is not guaranteed to be.** The
give-back term binds only when it is tighter than the floor, and the floor is
on the profit side of entry, so the stop **level** always locks a profit. The
**fill** can still be worse. The bar path fills with `gap_stop_fill` at the
open (`plan_manager.py:1333`), and a real broker stop can gap the same way,
through the level or past entry. The measurement reports give-back exits whose
fill is worse than the level.

**Out of scope:** plans before TP1 (`ACTIVE`), legacy trades without a
`plan_id`, TP2 handling, and the adaptive trail (off in production). All
behave exactly as today. The structure exit is also off in production. Its
interaction with this rule is fixed in `## Where it changes` so that enabling
it later cannot silently drop the give-back.

## Config

There are two new `.env` fields in `swingbot/config.py`. Both are hot-reloaded
via SIGHUP and read at call time, never cached:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `RUNNER_GIVEBACK_ENABLED` | bool | `true` | Off stops **new** give-back tightening. |
| `RUNNER_GIVEBACK_PCT` | float | `5.0` | Percent of the best price. Read through a clamp helper to `[0.5, 49]`, like `trail_notify_min_r()` (`plan_manager.py:132`), because `_cast` enforces no range (`config.py:1427`); the admin save path carries the same min/max. |

**Off does not loosen.** `working_stop` is persisted and a runner stop never
widens. A runner already tightened by the give-back keeps that stop after the
flag is turned off or the percent is raised. Restoring the old stop on a given
plan is a manual `working_stop` reset on production, done only when the
partner asks for it. No automatic revert is built.

The default is **on** by partner decision ("apply to open trades now"). This
spec records that the default was not chosen by a backtest; the measurement
below reports what it costs or gains.

## Where it changes

All the arithmetic lives in one pure helper, next to `chandelier_stop` in
`swingbot/core/planning/exit_sim.py`:
`giveback_stop(extreme, pct, direction) -> float`. Every path below calls it,
so live and backtest cannot drift on the formula.

1. **Live tick path**, `PlanManager._step_partial`
   (`swingbot/core/planning/plan_manager.py:1031`).
   - **Extreme tracking moves out of `_ratchet_chandelier`.** Today
     `runner_high_close` is updated only after the `atr_fn is None` early
     return (`:1094`). A manager without `atr_fn` would leave `E` stale, and
     the give-back would silently do nothing.
   - A new `_track_extreme(plan, price, is_bull)` updates and persists the
     extreme on every tick, before anything else in the step. The chandelier
     reads that extreme. Production has `atr_fn` wired (`:1430`), so the
     chandelier's own behaviour is unchanged.
   - A new `_apply_giveback(plan)` then tightens `plan.working_stop` against
     `giveback_stop(plan.runner_high_close, …)`. It persists and logs a
     `_plan_line("giveback stop", …)` only when the stop actually moves.
   - Both run **before** `_structure_runner_step` (`:1036`). A structure exit
     can then never pre-empt the give-back on a tick that should have closed
     on it.
   - It runs on **every** tick, not only on a new extreme. That is what makes
     it reach plans already open at deploy: RKLB's extreme does not change.
2. **Bar catch-up path**, `PlanManager._check_bar_partial` (`:1323`). It
   tightens the stop the same way before its bar test. It uses the stored
   extreme, never the checked bar's own high or low (no intrabar lookahead),
   so the bar path keeps its current semantics.
3. **Backtest**, `exit_sim._chandelier_ratchet` (`exit_sim.py:424`) and its
   `exit_sim_v2` counterpart (`exit_sim_v2.py:~166-181`). They apply the term
   from the extreme **close**, effective the next bar, the same way the
   chandelier is applied there. Gated by the same flag.
   - The runner-phase result gains an internal `stop_source`
     (`floor`/`trail`/`giveback`) beside the unchanged `runner_trail` reason
     string. The measurement reads it.
   - **Known asymmetry:** live uses the extreme tick, the backtest uses the
     extreme close, so live is tighter. On a flat 5% band the tick/close gap
     is a large share of the band on high-ATR names. The backtest therefore
     measures a **looser** rule than the live one and can flatter it. The
     measurement reports this gap rather than assuming it away
     (`## Measurement`).

**When it runs.** `poll` runs the full state machine every 60s outside the
operator's quiet window (`INTRADAY_RTH_ONLY` + `is_quiet_hours`,
`plan_manager.py:494-517`). That includes pre- and after-hours ticks, by the
operator's 2026-09-14 choice recorded there. A breach during the quiet window
exits on the first tick after it reopens, at that tick's price, not at the
level.

## Exit reason: no new string

The exit reason stays `tp1_runner_trail` live (`runner_trail` in the
simulator). The comment at `exit_sim.py:415-416` records that about 30 files
pattern-match these strings. They include `_STOPPED_REASONS`,
`analytics/partials.py`, `analytics/runner_path.py`, `instructions.py`,
`lifecycle_embeds.py` and `follow_notify.py`. A new reason would need every
one of those tables changed, and missing one fails silently. The give-back is
a trailing stop, so the label is honest.

The live runner leg carries `"stop_source": "giveback"` through
`_close_runner`'s existing `extra` argument when the stop that fired equals
the give-back level, otherwise `"trail"` or `"floor"`. The close embed
(`lifecycle_embeds.py`) reads it: a give-back close adds one line naming the
level and the best price it came from, for example "5% give-back from the low
of 49.94: stop 52.44". The reason string is unchanged.

## Telling the reader

A stop moved by the give-back reaches the reader through the existing
execution-feed `stop_moved` notice. In the regular session, `_feed_bookkeeping`
posts it whenever the resting stop has moved by at least `TRAIL_NOTIFY_MIN_R`
from the last stop told (`plan_manager.py:465-469`, `stop_move_event` `:171`).
`resting_stop` reads `working_stop`, so give-back moves are covered with no new
plumbing.

**The gap that remains:** a runner whose stop moves and is hit on the **same
tick** gets only the close notice. That happens on deploy day for a runner
already past its give-back level, and after a gap. The close event already
carries `notified_stop` and `bot_stop` (`:456-457`), and the embed line above
names the give-back. The deploy gate below covers deploy day.

## Open trades at deploy: a hard gate

No migration. The first tick after deploy tightens every open runner's
`working_stop`.

**Before the deploy step runs**, the plan's deploy task lists every open
`PARTIAL` plan on production with:
- its current `working_stop`;
- `E`;
- its computed give-back stop;
- whether the last price is already past that stop, meaning it closes on the
  first tick.

That list is shown to the partner and recorded in the plan's results before
the image is restarted. The reason: the partner holds real broker stops at
the old levels (RKLB: 59.11), and the paper close will not move them.

Expected: RKLB short, `E = 49.94`, gives `giveback = 52.44`. The last price
was about 52.30 (2026-10-19).

## Risks (stated, accepted by the partner's decision)

- **5% sits inside one day's normal range on volatile names.** RKLB's daily
  ATR is about 8% of price, so 5% is about 0.6 ATR, and the rule can act like
  "exit on the first bounce". This is the main way it can lower `ExpR`. A
  follow-up could scale `p` by ATR. That is a new pre-registration, not a tweak
  (`## Measurement`).
- **Extended-hours prints set `E` for good.** By the operator's 2026-09-14
  choice, the full machine runs on pre- and after-hours ticks. One thin print
  can set an extreme the regular session never traded, and the give-back
  tightens off it permanently. This rule inherits that choice rather than
  overriding it. The measurement and the live tag let it be revisited.
- **Real-money resting orders.** The partner trades from alerts with resting
  broker orders. The bot moves only its paper stop. The `stop_moved` notice
  (`## Telling the reader`) tells the reader to move the broker stop. Doing so
  is manual.
- **Pinned backtest numbers.** Default-on changes simulator output.
  - A test that pins a simulator figure is either re-pinned to the new
    measured value or pinned flag-off, decided per test and recorded in the
    plan's ledger.
  - Closed pre-registrations are not re-run because of this. Their recorded
    results stand as of their own run date.

## Testing

- `giveback_stop`: long, short, percent bounds.
- Live tick path:
  - long and short tighten;
  - never loosens when the floor or trail is already tighter;
  - `E is None` gives no term;
  - flag off is byte-identical to today on a plan never tightened;
  - an existing plan whose extreme does not change still tightens (the RKLB
    case, as a fixture with its real numbers);
  - the first post-deploy tick is already past the give-back level, so the
    stop moves and the runner closes on one tick;
  - an isolated spike print sets `E` (documents the accepted behaviour);
  - a manager with `atr_fn=None` still tracks `E` and applies the give-back;
  - with the structure exit enabled, the give-back still applies before it;
  - the closing leg carries the right `stop_source`, and the close embed shows
    the give-back line only for `giveback`.
- Bar path: tightens before the bar test and does not use the bar's own
  extreme.
- Simulator: flag off gives an identical trade list on an existing fixture;
  flag on gives a give-back exit tagged `stop_source = giveback` on a
  constructed run-up-and-reversal frame.
- Config: defaults, range validation, SIGHUP reload picks up a changed percent.

## Measurement (after ship, reported, not a gate)

**Frozen before TRAIN is read.** These match the v123 instrument, so the
result is comparable to the headroom cited:
- window: TRAIN 2020-01-01..2023-12-31 only. **VALIDATION is neither run nor
  read**, so a future pre-registered give-back hypothesis keeps its one shot;
- data source: the 75-ticker local backtest cache;
- engines: `StrategyEngine.iter_trades` and `replay_scenarios`;
- horizons: all ten;
- `scale_out=True`;
- non-zero frictions from `swingbot/core/edge/frictions.py` in both arms;
- arms: the flag off, then on at 5%, on the same entries.

This run counts as **one look**, and a ledger row is appended to
`preregistration-ledger.jsonl` so `ledger_qvalues` counts it.

**Primary reading (one):** pooled paired per-trade runner-leg ΔR (on minus
off), with a ticker-cluster bootstrap interval
(`acceptance.cluster_bootstrap` / `bootstrap_delta`,
`swingbot/core/backtesting/acceptance.py:239,280`) and `acceptance.mde_paired`
(`:372`), on the paired-measurement template
`scripts/backtest/measure_acceptance_exits.py` (`paired_r_deltas`), which
carries frictions where `runner_headroom.py` does not.
Reported with the count of trades whose outcome changed.

**Descriptive only.** None of these is an effect claim. With 10 horizons and
several metrics, one or two horizon "effects" at 5% are expected by chance,
and the report says how many cells were looked at.
- per-horizon paired ΔR, beside the distribution of `p × E / risk` per
  horizon. 5% of price is more than 1R on short horizons and a fraction of 1R
  on long ones;
- the runner-leg R distribution and the floor-exit share;
- runner capture against a **fixed** MFE window: the flag-off arm's own
  window, so an earlier exit cannot shrink the denominator;
- the exit mix by `stop_source`, including give-back exits with a fill worse
  than the level;
- dollars at fixed risk and max drawdown, off against on;
- days from TP1 to exit, and how often a give-back exit is followed by a new
  extreme within 10 bars (a shake-out, not a reversal);
- a tick-versus-close sensitivity: the same run with `E` taken from bar
  highs/lows instead of closes, as a bound on the live/backtest asymmetry.

Win rate (TP1 touched) is **not** reported as a result. A post-TP1 rule cannot
move it (`backtest-methodology.md` § Harvest gate, `win_rate_floor` SKIPPED;
v92 recorded the same immunity).

**Re-tuning is a new pre-registration.** If the partner wants a different
percent, or an ATR-scaled `p`, after reading this report, that is a new
hypothesis. Its grid is frozen before fold-train is read, and it passes Stage 1
`plateau_report()` and then the harvest gate's one-shot VALIDATION. The best
cell is not read off this report.

**Live book.** Live give-back exits carry `stop_source`. A small offline
script computes each one's counterfactual flag-off exit from daily bars. No
live conclusion is drawn below 30 give-back exits.

Changing the 5% or turning the flag off is the partner's call. It is not
automatic.

## Panel review

Spec review, 2026-10-19 (risk-manager, veteran-trader, quant-researcher).

- risk-manager 1: "always a win" overstated; gap fills can lose; measure fills worse than the level -- applied (§ The rule, § Measurement).
- risk-manager 2: flag-off does not loosen persisted stops -- applied (§ Config).
- risk-manager 3: extreme tracking sits behind the `atr_fn is None` return -- applied (`_track_extreme`, § Where it changes; test added).
- risk-manager 4: deploy needs a hard gate listing old/new stops -- applied (§ Open trades at deploy).
- risk-manager 5: backtest measures a looser rule than live -- applied (tick/close sensitivity in § Measurement).
- risk-manager 6: simulator cannot isolate give-back exits -- applied (internal `stop_source` in the sim result).
- risk-manager 7: dollars at fixed risk and drawdown missing -- applied (§ Measurement).
- risk-manager 8: structure step can pre-empt the give-back -- applied (give-back runs before `_structure_runner_step`; test added).
- veteran-trader 1 [BLOCKING]: no stop-moved notice after the alert -- rejected as stated: `stop_moved` already posts on any resting-stop move of at least `TRAIL_NOTIFY_MIN_R` in the regular session (`plan_manager.py:465-469`), and `resting_stop` reads `working_stop`. The real residual, a move and hit on the same tick, is applied: documented in § Telling the reader, covered on deploy day by the hard gate, and named in the close embed.
- veteran-trader 2: close notice cannot show a give-back -- applied (close embed line from `stop_source`).
- veteran-trader 3: extended-hours prints set `E` permanently -- rejected: the full machine on extended-hours ticks is the operator's 2026-09-14 decision (`plan_manager.py:494-512`); this spec inherits it, states the risk, and adds a test documenting it. Raised to the partner.
- veteran-trader 4: polling and quiet-hours behaviour unstated -- applied (§ Where it changes, "When it runs").
- veteran-trader 5: report timing since TP1 and shake-out rate -- applied (§ Measurement).
- veteran-trader 6: non-zero frictions in both arms -- applied (§ Measurement).
- veteran-trader 7: fixtures for a spike print and a first tick already past the level -- applied (§ Testing).
- quant-researcher 1: capture prediction cannot fail because the MFE window shrinks -- applied (prediction is paired ΔR; capture uses a fixed window).
- quant-researcher 2: third attempt on the same headroom; prior near 0.01R -- applied (§ Why).
- quant-researcher 3: no magnitude in the prediction -- applied (`Edge:` bound under 0.05R).
- quant-researcher 4: no paired statistic or interval -- applied (paired ΔR, cluster bootstrap, `mde_paired`).
- quant-researcher 5: one primary reading, cells descriptive, ledger row -- applied.
- quant-researcher 6: win rate cannot move -- applied (not reported as a result).
- quant-researcher 7: a re-tuned percent is a new pre-registration -- applied.
- quant-researcher 8: VALIDATION untouched -- applied.
- quant-researcher 9: freeze data source, universe and engines -- applied (v123's setup).
- quant-researcher 10: 5% is a different R on each horizon -- applied (`p × E / risk` per horizon).
- quant-researcher 11: live tag needs a counterfactual and a minimum N -- applied (offline counterfactual, no conclusion below 30).
