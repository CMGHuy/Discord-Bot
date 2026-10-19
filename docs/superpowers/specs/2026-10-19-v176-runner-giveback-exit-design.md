# v176 — Runner give-back exit: close the runner 5% off its best price

**Version:** ui 1.30.0 · bot 2.11.0 (at writing)
**Bump:** bot minor — every open runner gains a new, usually tighter stop, and runners already open move to it on the first tick after deploy.
**Edge:** harvest — locks in more of a runner's favourable run before a reversal takes it back. Prediction: higher runner capture; the effect on pooled `ExpR` is unknown in sign until measured (it also cuts runners that would have resumed).
**Screen:** harvest-headroom docs/superpowers/results/2026-10-02-v123-runner-headroom.md
**Panel:** risk-manager, veteran-trader, quant-researcher
**Status:** spec written 2026-10-19 from a chat with the partner. Rule, scope (runners after TP1 only) and "apply to open trades now" were all decided by the partner in chat.

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

v123 measured this headroom. Pooled TRAIN runner capture is 70.4% of MFE (mean
runner 2.43R against mean MFE 3.77R, n = 3127), which is below the 75%
no-headroom line.

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

Because the floor is always on the profit side of entry and the give-back term
only binds when it is tighter than the floor, a give-back exit is always a
win.

**Out of scope:** plans before TP1 (`ACTIVE`), legacy trades without a
`plan_id`, TP2 handling, the structure exit and the adaptive trail (both off
in production). All behave exactly as today.

## Config

There are two new `.env` fields in `swingbot/config.py`. Both are hot-reloaded
via SIGHUP and read at call time, never cached:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `RUNNER_GIVEBACK_ENABLED` | bool | `true` | Off restores today's behaviour exactly. |
| `RUNNER_GIVEBACK_PCT` | float | `5.0` | Percent of the best price; valid `0 < pct < 50`, else rejected by the schema. |

The default is **on** by partner decision ("apply to open trades now"). This
spec records that the default was not chosen by a backtest; the measurement
below reports what it costs or gains.

## Where it changes

All the arithmetic lives in one pure helper, next to `chandelier_stop` in
`swingbot/core/planning/exit_sim.py`:
`giveback_stop(extreme, pct, direction) -> float`. Every path below calls it,
so live and backtest cannot drift on the formula.

1. **Live tick path**, `PlanManager._step_partial`
   (`swingbot/core/planning/plan_manager.py:1031`). Before the stop is read,
   a new `_apply_giveback(plan)` tightens `plan.working_stop` against
   `giveback_stop(plan.runner_high_close, …)`. It persists and logs a
   `_plan_line("giveback stop", …)` only when the stop actually moves.
   - This runs on **every** tick, not only on a new extreme. That is what
     makes it reach plans already open at deploy: RKLB's extreme does not
     change, so `_ratchet_chandelier`'s early return at `:1099` would never
     reach it.
   - `_ratchet_chandelier` (`:1092`) also applies the term when it records a
     new extreme, so the stop moves on the same tick as the new best price.
2. **Bar catch-up path**, `PlanManager._check_bar_partial` (`:1323`). It
   tightens the stop the same way before its bar test. It uses the stored
   extreme, never the checked bar's own high or low (no intrabar lookahead),
   so the bar path keeps its current semantics.
3. **Backtest**, `exit_sim._chandelier_ratchet` (`exit_sim.py:424`) and its
   `exit_sim_v2` counterpart (`exit_sim_v2.py:~166-181`). They apply the term
   from the extreme **close**, effective the next bar, the same way the
   chandelier is applied there. Gated by the same flag.
   - **Known asymmetry:** live uses the extreme tick, the backtest uses the
     extreme close, so live is slightly tighter. That asymmetry already
     exists for the chandelier and is accepted here for the same reason: bars
     carry no intraday sequence.

## Exit reason: no new string

The exit reason stays `tp1_runner_trail` live (`runner_trail` in the
simulator). The comment at `exit_sim.py:415-416` records that about 30 files
pattern-match these strings. They include `_STOPPED_REASONS`,
`analytics/partials.py`, `analytics/runner_path.py`, `instructions.py`,
`lifecycle_embeds.py` and `follow_notify.py`. A new reason would need every
one of those tables changed, and missing one fails silently. The give-back is
a trailing stop, so the label is honest.

To keep the rule measurable, the live runner leg carries
`"stop_source": "giveback"` through `_close_runner`'s existing `extra`
argument when the stop that fired equals the give-back level. Otherwise it
carries `"trail"` or `"floor"`. Nothing reads the field yet. It exists for the
post-ship measurement and for the book autopsy.

## Open trades at deploy

No migration. The first tick after deploy tightens every open runner's
`working_stop`.

Expected: RKLB short, `E = 49.94`, gives `giveback = 52.44`. The last price
was about 52.30 (2026-10-19), so the RKLB runner will most likely close on its
first tick above 52.44, or stay open with a 52.44 stop if it falls again.
Before deploy, the plan lists every open `PARTIAL` plan on production with its
current stop and its computed give-back stop, so the partner sees what will
move.

## Risks (stated, accepted by the partner's decision)

- **5% sits inside one day's normal range on volatile names.** RKLB's daily
  ATR is about 8% of price. Such a runner will be shaken out by ordinary
  noise more often than by a real reversal. This is the main way the rule can
  lower `ExpR`, and the measurement below reports it per horizon. A follow-up
  could scale `p` by ATR. That is not part of this spec.
- **Real-money resting orders.** The partner trades from alerts with resting
  broker orders. The bot moves only its paper stop. Moving the broker stop is
  manual, and the Discord close notice arrives after the fact. No stop-moved
  notice is added here.
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
  - flag off is byte-identical to today;
  - an existing plan whose extreme does not change still tightens (the RKLB
    case, as a fixture with its real numbers);
  - the closing leg carries the right `stop_source`.
- Bar path: tightens before the bar test and does not use the bar's own
  extreme.
- Simulator: flag off gives an identical trade list on an existing fixture;
  flag on gives a give-back exit on a constructed run-up-and-reversal frame.
- Config: defaults, range validation, SIGHUP reload picks up a changed percent.

## Measurement (after ship, reported, not a gate)

Run TRAIN through `backtest-runner` with the flag off, then on (5%). Report
the following, pooled and per horizon, to the partner:

- pooled `ExpR`;
- win rate;
- runner capture (the v123 instrument);
- the runner exit mix.

Changing the 5% or turning the flag off is the partner's call. It is not
automatic.
