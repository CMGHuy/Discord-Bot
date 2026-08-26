Version: ui 1.8.4 · bot 1.4.3
Bump: ui patch · bot patch
Edge: none (integrity)

# Reframe the PARTIAL plan display as a mini-position

## Problem

Once a plan's TP1 fires, `PlanManager` flips it to `PlanStatus.PARTIAL`: 50%
of the position is banked, and the remaining 50% (the "runner") gets a new
stop (`runner_floor`, v39: `entry + 2/3 × (tp1 - entry)`) and, when the
strategy has one, a TP2 target. All of that math is correct and already
validated (v39 backtest) — this spec changes **none of it**.

What's wrong is what gets *displayed*. Across every surface that shows a
PARTIAL plan, the runner's own numbers are either missing, incomplete, or
buried in prose instead of stated as a position:

- The Discord "TP1 banked" alert (`embeds.py::build_plan_event_embed`)
  shows the banked R-multiple but the runner gets only static text —
  `"runner active, stop protecting 2/3 of the TP1 move"` — no actual
  entry/target/stop numbers, and no %/$ for the banked leg.
- The `!liveplans` board (`commands/plans.py::format_plans_board`) shows
  banked R and the trail stop, but never TP2 — someone reading the board
  can't see where the runner is headed.
- The admin dashboard's compact `PlanCell` already shows the *correct*
  runner target/stop (v39/9e50431 wired `target`/`stop_loss` to
  `tp2`/`working_stop` once PARTIAL, and the tooltip already says
  "Trailing stop"), but says nothing about the banked leg at all.
- The admin trade-detail page has no dedicated view of the runner as its
  own position — the original plan's entry/TP1/stop is still shown, but
  there's nothing that says "here's what's actually still open, and here's
  what you already banked."

The result: someone looking at a PARTIAL plan on any of these surfaces has
to do the "half the position already booked profit, the rest is now a
smaller position with its own entry/target/stop" arithmetic in their head.

## Design

### Principle

**Presentation only.** No change to `runner_floor`, the chandelier trail,
TP1_FRACTION, or TP2 selection. TP2 stays exactly as picked at plan-creation
time — it is not re-derived when TP1 fires (considered and explicitly
rejected: that would be a real logic change needing its own backtest
validation, not a display fix).

Every surface gains the same reframing: state the runner as its own
position —

- **Entry** = the actual TP1 fill price, i.e. `legs_realized[0]['exit_price']`
  — not the plan's `tp1` target level. They're usually equal but the fill
  can differ on a gap-through, and the fill is the number that actually
  happened.
- **Target** = `tp2` (unchanged from today, where it's already shown/wired
  in the surfaces that already reframe target/stop).
- **Stop** = `working_stop` (unchanged — already the current floor/trail
  value everywhere it's read).

— and state what's already banked, in **R, %, and $** together (not R
alone, which is all today's surfaces show): the fraction closed, its
R-multiple, its %-gain, and its dollar amount.

This is additive everywhere, per the "alongside, don't replace" decision:
the original plan's entry/TP1/stop keeps being shown wherever it already
is; the reframed runner view and the banked-profit line are new content
next to it, not a replacement.

### No-TP2 fallback

Most strategies run without a TP2 (`select_tp2` returns `None` for them).
The two existing surfaces that already handle this disagree with each
other: `embeds.py::leg_rows()` drops the target entirely (`"50% → trail"`);
the admin API falls back to showing the original `tp1` level as `target`
(`current_target = plan.get("tp2") or plan.get("tp1")`, already covered by
`test_partial_plan_falls_back_when_the_runner_fields_are_unset`).

This spec's new content standardizes on the **admin API's existing
precedent** (fall back to `tp1`) everywhere it adds a target, since that
precedent already has test coverage and "show the last known level" reads
better than silently dropping the number: `"Partial position: entry 102.00
→ target 130.00 (tp1, no tp2) / stop 118.67"` in the Discord alert and
`!liveplans` line, and the trade-detail panel's `PlanCell` `target` input
falls back the same way the admin API's `current_target` already does.

### No backend schema change

Every field this needs already exists in what's persisted and already
exposed by the admin API:

- `legs_realized[0]['exit_price']`, `['fraction']`, `['r']` — the TP1
  leg's actual fill, size, and R-multiple.
- `plan.tp2`, `plan.working_stop` — the runner's live target/stop.
- `plan.entry_price`, `t['shares']` — enough to derive the banked leg's %
  and $ (`(exit_price - entry_price) / entry_price` signed by direction
  for %; `shares × leg_fraction × (exit_price - entry_price)` signed by
  direction for $).

So this is four formatting changes, not a data-model change.

### The four surfaces

**1. Discord TP1-hit alert** — `embeds.py::build_plan_event_embed`,
`tp1_partial` branch. Today:

```
Banked: 50% @ 102.00 (+0.85R)
Runner: runner active, stop protecting 2/3 of the TP1 move
```

Becomes:

```
Banked:  50% @ 102.00  (+0.85R · +4.1% · +$42)
Partial position:  entry 102.00 → target 150.00 / stop 118.67
```

The "Partial position" line reuses the `entry → target / stop` shape
already used everywhere else in the bot's embeds, so it reads as familiar
rather than a new format. The %/$ figures use the same
`account.compute_position_size`-at-render-time snapshot `leg_rows()`
already uses, including its existing fallback: when sizing/account data
isn't available, the %/$ clause is omitted rather than shown as zero or
crashing (mirrors `leg_rows()`'s current `sizing is None` handling).

**2. `!liveplans` board** — `commands/plans.py::format_plans_board`,
PARTIAL branch. Today:

```
✅ `AAPL` bullish — banked +0.85R on 50%, trail 118.67
```

Becomes:

```
✅ `AAPL` bullish — banked +0.85R/+4.1%/+$42 on 50%, entry 102.00 → TP2 150.00 / trail 118.67
```

**3. Admin dashboard trade card** — `plan-cell.ts`. The compact one-line
cell itself is unchanged (it already correctly shows the runner's
target/stop). The tooltip's existing `computed()` gains one more clause,
only when the plan is PARTIAL (`trailing()` is already true and new
banked-profit inputs are provided):

```
Entry 51.00 · Target 150.00 · Trailing stop 118.67 · 50% banked +0.85R (+4.1%, +$42) @ 102.00
```

New optional inputs on `PlanCell`: `bankedFraction`, `bankedR`,
`bankedPct`, `bankedAmount`, `bankedEntry` — all `| null`, tooltip clause
only renders when they're present.

**4. Admin trade-detail page** — `trade-detail.ts`. New "Partial position"
panel, shown only for a PARTIAL trade, alongside the existing plan panel
(which is untouched — still shows the original entry/TP1/stop). The new
panel reuses `PlanCell` itself (`trailing=true`, `entry` =
`_legs[0].exit_price`, `target` = `target2`, `stop` = `stop_loss`) plus a
"Banked" line with the same R/%/$ figures, computed client-side from
fields already in the existing API payload (`entry`, `_legs[0]`, `shares`)
— no API response shape change.

### Testing

- Python: unit tests for the new %/$ helper, including the no-sizing-data
  fallback (mirrors existing `leg_rows()` coverage); updated tests for the
  `tp1_partial` embed and the `!liveplans` PARTIAL board line.
- Frontend: `plan-cell.spec.ts` gets cases for the new tooltip clause
  (present/absent); `trade-detail.spec.ts` gets cases for the new panel.
- No backtest/validation run — nothing about the stop, target, or R
  changes. `Edge: none (integrity)`, per `docs/claude/edge-priorities.md`'s
  taxonomy — this buys clarity, not expectancy.

### Out of scope

- Changing `RUNNER_FLOOR_FRACTION` (2/3) or any other v39-validated
  constant.
- Re-deriving TP2 at TP1-fire time instead of at plan creation.
- Any change to R-multiple bookkeeping (`closed_r_multiple`,
  `legs_realized` accounting) — those stay anchored to the original
  entry/risk, unchanged.
