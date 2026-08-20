# v39 — Runner floor protection at TP1

Version: ui 1.7.13 · bot 1.3.0
Bump: bot patch — a tuning change to an existing mechanism (the runner's
starting stop after TP1), not a new capability or an architecture someone
has to relearn. `ui` none — the admin already displays `working_stop` for a
PARTIAL row (Task fixing the trades-list display gap); this only changes
what value plan_manager computes into it.

## The problem, stated once

`swingbot/core/planning/plan_engine.py` and `plan_manager.py` implement the
scale-out exit model (spec `2026-07-11-v2-unified-plan-engine-design.md`
§5): TP1 banks `tp1_fraction` (50%) of the position, and the remainder — the
**runner** — rides toward TP2 behind a trailing stop.

That trailing stop starts at pure breakeven (`working_stop = entry`) the
instant TP1 fires, and only then begins ratcheting up via an ATR chandelier
trail (`chandelier_stop`: extreme close since TP1, minus `trail_atr_mult`
(2.5) × ATR(14)) as price makes new highs/lows.

Between TP1 and however many bars it takes the chandelier trail to ratchet
meaningfully above entry, the runner is protected by nothing but breakeven.
A pullback in that window gives back the *entire* TP1→now move on the
remaining half of the position — the exact complaint that prompted this
spec: a partial trade "erasing all the gain it is having."

## Goal

Give the runner an initial stop floor, set the moment TP1 fires, that
locks in **2/3 of the entry→TP1 move** instead of 0% — so a reversal right
after TP1 closes the runner fast, with most of that leg's gain intact,
while a continuation still gets the full existing chandelier trail and TP2
target untouched.

## Design

### The formula

```
runner_floor = entry + (2/3) * (tp1 - entry)
```

One formula, both directions — `tp1 - entry` is already signed correctly
per direction (positive for a bullish plan, negative for a bearish one), so
no `is_bull` branch is needed at the call site. This becomes the runner's
stop **the instant TP1 fires**, replacing the current `entry`.

Everything downstream of that moment is unchanged: `chandelier_stop` still
ratchets the floor *up* (bullish)/*down* (bearish) as price extends, using
`max`/`min` so it never moves back toward the floor once ahead of it, and
the runner still exits at whichever of {stop, TP2, timeout} comes first.
This is strictly more protective than today's model, never less — nothing
about the win/target side of the runner's behavior changes.

`RUNNER_FLOOR_FRACTION = 2.0 / 3.0`, defined once in `plan_engine.py`
alongside `TRAIL_ATR_MULT`/`TP1_FRACTION`, imported by `plan_manager.py`
rather than re-declared (matches how `chandelier_stop` itself is already
shared between the two).

### Where it changes

Backtest and live intentionally mirror each other here (`_scale_out_exit_walk`'s
own docstring: "byte-identical" through phase 1); all three call sites move
together in one commit:

1. `plan_manager.py::_step_active` — live poll path, on the TP1 fill branch
   (`plan.working_stop = entry` → `runner_floor(...)`).
2. `plan_manager.py::_check_bar_active` — overnight bar-check path, same
   branch.
3. `plan_engine.py::_scale_out_exit_walk` — backtest exit walk, phase-2 setup
   (`runner_stop = entry_price` → `runner_floor(...)`).

A shared helper (`plan_engine.runner_floor(entry, tp1) -> float`, next to
`chandelier_stop`) is the single source both live call sites and the
backtest walk import, so the formula can never drift between the two the
way a copy-pasted expression could.

### Reason labels: string unchanged, boundary moves

Three places currently label a runner close as breakeven vs. trail by
comparing the exit stop to `entry` exactly:

- `plan_manager.py::_step_partial`: `"tp1_runner_be" if stop == entry else "tp1_runner_trail"`
- `plan_manager.py::_check_bar_partial`: same, against `plan.entry_price`
- `plan_engine.py::_scale_out_exit_walk`: `"runner_be" if runner_stop == entry_price else "runner_trail"`

The **string values stay exactly as they are** — `"tp1_runner_be"` /
`"runner_be"` are pattern-matched in ~30 files, including frozen historical
result JSONs (`docs/superpowers/results/*.json`, never rewritten
retroactively) and the win/loss classifier's `reason.startswith("tp1_")`
check (`performance.py::_on_event`) — a rename is out of scope and buys
nothing. Only the **comparison** changes, from `stop == entry` to
`stop == runner_floor(entry, tp1)`, so the tag now means "closed at its
initial post-TP1 floor" rather than literally at entry price. A one-line
comment at each site notes the shift so a future reader isn't confused by
the name.

### Discord text: the one place silence would mislead

`swingbot/core/scanning/embeds.py` has two literal "break-even" strings that
become false once the floor moves:

```python
"tp1_partial" event, "Runner" field:
    value="runner active, stop at break-even"

_CLOSE_STYLE["tp1_runner_be"]:
    ("🟢 Win — runner closed at break-even — {ticker}", ...)
```

Both get reworded to describe the real floor rather than claim breakeven —
e.g. "runner active, stop protecting 2/3 of the TP1 move" and "runner
closed — gave back to its floor". Exact wording is copy, not a design
decision; finalized during implementation.

### Docs: the exit model's validated numbers go stale

`config.py`'s `SCALE_OUT_ENABLED` help text currently reads: "Backtested
under this exact exit model (see README's Plan Engine v2 section for the
validated win-rate/expectancy numbers behind it)." That claim describes the
breakeven-floor model this spec replaces.

Per the rollout decision below (ship now, no pre-registered re-validation
gate), both `SCALE_OUT_ENABLED`'s help string and the Plan Engine v2 section
in `docs/features.md` get a note: the cited win-rate/expectancy numbers
describe the pre-v39 breakeven-floor model and are stale until a fresh
TRAIN/VALIDATION backtest is run against the new floor. This is a
documentation change only — it does not touch
`docs/claude/backtest-methodology.md`'s closed-pre-registrations table,
because no new pre-registered run is being claimed here.

### Rollout: ship live now

Unlike every entry in `backtest-methodology.md`'s closed-pre-registrations
table, this does **not** go through a TRAIN/VALIDATION pre-registration
before shipping default-on. Rationale (confirmed with the requester): this
is a paper-trading bot, the change is strictly more protective of realized
gains than today's model (never less), and waiting on a full backtest cycle
would delay protecting trades that are live right now for a formula tweak
whose direction of effect is not in question. The staleness note above is
the honesty mechanism in place of a validation gate — a future backtest run
against the new floor is future work, not a blocker for this spec.

### Out of scope

- TP2 selection itself (`select_tp2`, the 3x-leg1 cap, MFE-informed
  `_tp2_from_r`) — confirmed as already reasonable; untouched.
- `BREAKEVEN_TRIGGER_FRACTION` (0.5) — the *pre*-TP1 breakeven trigger is a
  frozen, separately-validated constant and is not this spec's concern.
- Pyramiding (`maybe_pyramid`) — reads `plan.working_stop`/`plan.entry_price`
  for its own risk bound but does not assume the floor equals entry
  specifically; unaffected, not re-derived here.

## Testing

- `plan_engine.runner_floor(entry, tp1)`: correct value for both directions,
  and the `risk <= 0`/degenerate-input behavior already guarded upstream.
- `plan_manager._step_active`/`_check_bar_active`: `working_stop` is set to
  the floor (not `entry`) on the TP1 transition, both directions.
- `plan_manager._step_partial`/`_check_bar_partial`: a price pullback to
  exactly the floor closes the runner with reason `"tp1_runner_be"`; a
  price pullback to old-style breakeven (`entry`) does *not* close it
  (regression guard against the old boundary silently surviving).
- Continuation case: price extends well past TP1, chandelier trail ratchets
  the stop above the floor, confirming the floor is a starting point, not a
  ceiling.
- `plan_engine._scale_out_exit_walk`: mirrors the same three cases so
  backtest and live cannot silently diverge.
- Existing tests asserting `working_stop == entry`/`runner_stop == entry_price`
  immediately after TP1 (`tests/planning/test_plan_manager_partial.py`,
  `tests/planning/test_exit_sim_scaleout.py`, and any others the symbol-verifier
  turns up) get their expected values updated to the new floor formula.

## Parallelisation

- **Sequential, single unit of work.** The formula, its three call sites,
  and the reason-label comparisons are one coupled change — splitting them
  across tasks would leave live and backtest disagreeing mid-implementation,
  which is exactly the drift this spec's "byte-identical" design goal
  exists to prevent.
- **Group 2 (parallel with each other, after Group 1 lands):** the
  `embeds.py` wording fix and the docs staleness note touch disjoint files
  with no contract dependency on one another.
