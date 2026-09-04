# v73 — One projection for pending and partial plan display

**Version:** ui 1.11.0 · bot 1.6.1
**Bump:** ui minor (1.11.0 → 1.12.0) · bot patch (1.6.1 → 1.6.2) — two
components, separately graded. A partial position stops showing a target it
already hit and a pending one gains numbers it never had: the user is handed a
different product, which is a `ui` minor. The Discord board and the lifecycle
embed change their wording and their legacy stop fallback — real but small,
which is a `bot` patch.
**Edge:** none (integrity) — display correctness buys no trading edge. No exit
rule, no gate, no alert threshold changes. It makes the screens tell the truth
about positions the bot already holds.

## Goal

Give pending and partial plans one derivation, shared by every surface, so a
plan reads the same in Discord and in the admin SPA — and so neither shows a
number that is no longer true.

## Why — three renderers, three answers

`PARTIAL`-without-`tp2` is **the normal in-session outcome**, not an edge case:
`plan_manager._step_active:320-335` transitions to `PARTIAL` on a TP1 touch
with no `tp2` check at all, banks `tp1_fraction`, sets
`working_stop = runner_floor(entry, tp1)` and runs the remainder on the
chandelier trail. `exit_sim._scale_out_exit_walk:235-259` does the same in
every backtest. Only `_extended_candidate_active:462` closes at TP1 without a
`tp2`, and `known-traps.md` records why that branch is deliberately narrow.

So three renderers each invented a fallback for the common case, and they
disagree on two axes:

| | Target when `tp2` is None | Stop when `working_stop` is None |
|---|---|---|
| `core/scanning/plan_table.py:159` | `tp1` + `" (tp1, no tp2)"` | `runner_floor(entry, tp1)` — in profit |
| `commands/plans.py:56` | `tp1` + `" TP1 (no TP2)"` | omitted entirely |
| `admin/api_v1/trades.py:216` | `tp1`, **unlabelled** | `plan.stop_loss` — **the original risk stop** |

The API is wrong on both axes, and it is the only one that then **draws a bar**
from those two endpoints (`_status_fields:700-729`, `span = tp - sl`):

- **The target fallback is the everyday bug.** A runner whose `target` is the
  already-banked `tp1` sits pinned at or past 100% on the progress bar for the
  rest of its life, and nothing on the wire says the number is historical.
- **The stop fallback is a latent one.** `runner_floor(entry, tp1)` is
  `entry + 2/3 × (tp1 − entry)` — a floor **in profit, above entry**.
  `plan.stop_loss` is the original risk stop, **below entry**. Opposite sides
  of entry, feeding the same `span`. It only fires on plans persisted before
  `working_stop` existed, since `_step_active` sets it at the transition — so
  this is legacy-row damage, not everyday damage, and the spec fixes it by
  making one fallback correct everywhere rather than by migrating data.

Pending is a different failure: nothing is *wrong*, but both surfaces answer
neither of a pending plan's two questions — *will it trigger* and *when does it
die*. The API explicitly nulls the bar and sets `status_label` to `"PENDING"`
(`trades.py:740`).

## The projection

A new pure module, `swingbot/core/presentation/plan_view.py`:

```python
plan_view(plan, *, price: float | None = None, now=None) -> PlanView
```

Plan in, dataclass out. No I/O, no store access, no config reads beyond the
frozen constants it already imports. `PlanView` carries the derived display
facts **with their provenance** — the provenance is the half that fixes the
disagreement, because a surface that receives a bare number has to guess what
it means and each one guessed differently.

| Field | Meaning |
|---|---|
| `phase` | `PENDING` / `ACTIVE` / `PARTIAL` |
| `entry`, `stop`, `target` | What is currently true for the leg being displayed |
| `target_is_banked_tp1: bool` | The flag whose absence is today's bug |
| `stop_kind` | `'risk'` / `'trailing'` / `'derived_floor'` |
| `bar_kind` | `'progress'` / `'approach'` / `'trailing'` / `'none'` |
| `bar` | `BarSpec \| None` — `lo`, `hi`, `pos`, `entry_pos` |

`bar_kind='none'` covers the two cases where no bar can be drawn for reasons
that are not about the plan's phase: **no live price** (today's
`"No live price"` label) and a **malformed record** where the stop sits on the
wrong side of the target (`_status_fields:711` already degrades to a label
rather than rendering a bar that is confidently backwards — that behaviour is
preserved, not replaced). `bar` is `None` whenever `bar_kind` is `'none'` or
`'trailing'`.
| `banked` | `BankedLeg \| None` — fraction, fill price, R |
| `distance_to_trigger_r` | PENDING only, signed |
| `bars_to_expiry` | PENDING only |
| `floor_r`, `price_r`, `headroom_r` | PARTIAL-trailing only |

### What a PARTIAL shows

The runner's own numbers, never the original leg's:

- **Entry** — the TP1 leg's actual fill (`legs_realized[0]["exit_price"]`),
  which differs from the `tp1` level on a gap-through. Falls back to `tp1` when
  `legs_realized` is empty.
- **Stop** — `working_stop`, `stop_kind='trailing'`. When absent (legacy rows
  only), `runner_floor(entry, tp1)` with `stop_kind='derived_floor'` —
  `plan_table.py`'s answer, adopted as the single one. **Never `plan.stop_loss`.**
- **Target** — `tp2`, or `None`. **The `tp1` fallback is deleted.**
  `target_is_banked_tp1` is set so a surface can render "TP1 banked at 105.00"
  as history instead of as an open target.

**A no-TP2 runner gets no progress bar** (`bar_kind='trailing'`, `bar=None`).
A bar implies a destination and that position has none — it runs until the
trail takes it. Drawing one toward `tp1` is precisely today's defect, and
drawing one toward a moving endpoint gives a bar whose maximum keeps sliding.
In its place, three numbers in R: `floor_r`, `price_r`, `headroom_r`, rendered
as *floor +1.8R · price +2.4R · headroom 0.6R*. It states the mechanism that
actually governs the position.

A runner **with** `tp2` keeps a real progress bar, `runner_entry → tp2`, with
the trailing stop marked — the same instrument as today, with endpoints that
are finally correct.

### What a PENDING shows

Both new, both computed from fields the plan already carries:

- **`distance_to_trigger_r`** — `(trigger_price − price)` signed by direction,
  over the plan's own risk `|trigger_price − stop_loss|`. Risk units rather
  than percent, so the number is comparable across tickers.
- **`bar_kind='approach'`** — full at the trigger, empty 1R away, clamped.
  Bounded and meaningful without inventing a stored reference price.
- **`bars_to_expiry`** — from `expiry_bars` and the plan's age, reusing
  `lifecycle.py:137`'s own rule (`bars_since_created > expiry_bars`) rather
  than restating it. `plan_table.py:56` already prints *(expires in N bars)*;
  this makes the same fact available to every surface.

## Wiring

Three call sites become thin renderers over the projection:

| Site | Change |
|---|---|
| `admin/api_v1/trades.py` | `_row_from_plan` reads `plan_view`; the flags go on the wire; `_status_fields` consumes `BarSpec` instead of recomputing `span` |
| `commands/plans.py` | `_partial_tail` formats a `PlanView`; `_plan_line` gains the pending numbers |
| `core/scanning/plan_table.py` | `partial_position_line` formats a `PlanView` |

The SPA has the precedent to extend rather than invent: `ui/plan-cell.ts:86`
already takes a `trailing` input and `:121` already renders *"Trailing stop"*
vs *"Stop"*. `stop_kind` replaces the boolean; `target_is_banked_tp1` and
`bar_kind` are new inputs on the same component.

**One wire-shape consequence, named deliberately:** `target` becomes `null` for
a no-TP2 runner instead of silently carrying `tp1`. Trade History sorts on that
column through `query_closed_trades()` (server-side — see `known-traps.md`'s
"filtering, sorting and paging must stay on the SAME side"), so the sort must
place nulls deliberately rather than inherit whatever it does today. Nulls sort
last in both directions.

## Testing

`plan_view` is pure, so the correctness cases are unit tests on constructed
plans rather than through any surface: no-TP2 runner; missing `working_stop`;
gap-through fill where `legs_realized[0]["exit_price"] != tp1`; pending inside
and past expiry; price on either side of the trigger; **and every one of those
in both directions**, since `runner_floor` is direction-agnostic by formula
(`exit_sim.py:146-148`) and a bearish regression would be invisible in a
bullish-only suite.

Each of the three call sites keeps a test asserting it renders the facts the
projection reports, so the surfaces cannot drift apart again without a test
going red — which is the property this whole spec buys.

Two existing tests pin the behaviour being changed and are updated
deliberately, each with a note saying why:
`test_partial_plan_falls_back_when_the_runner_fields_are_unset` (asserts the
`tp1` target fallback) and `frontend/src/app/ui/plan-cell.spec.ts`'s
trailing-stop cases (gain `stop_kind`).

## Scope

**Non-goals.** No change to the exit state machine — `_step_active`,
`_step_partial` and `_step_extended` are untouched, and this spec deliberately
does **not** resolve the RTH/extended divergence it documents above (the same
TP1 touch closes a no-TP2 plan outside RTH and scales it out inside). That is a
real inconsistency and its own correctness spec; changing it would alter
exits, which changes expectancy, which needs measurement rather than a
decision. No new stored fields on `plans.json` — deriving keeps one authority
for plan state, per `known-traps.md`'s `check_bar` warning. No change to what
triggers a Discord alert.

## Parallelisation

- **Sequential:** `plan_view.py` and its unit tests before every call site —
  all three consume `PlanView`, and there is nothing to render against until
  the shape exists.
- **Group 1 (parallel), after the projection:** the three Python call sites —
  `admin/api_v1/trades.py`, `commands/plans.py`, `core/scanning/plan_table.py`.
  Disjoint files, no shared symbol beyond the projection each imports.
- **Sequential after Group 1:** the SPA changes (`plan-cell.ts`, the models,
  the Trade History null-sort). They consume the wire shape `trades.py`
  produces, so they cannot be written against a contract that does not exist
  yet.
- **Sequential last:** the null-sort change in `query_closed_trades()` —
  it is the one edit outside the display path and wants its own review.

## Acceptance criteria

1. A PARTIAL plan with no `tp2` reports `target=None`,
   `target_is_banked_tp1=True`, `bar_kind='trailing'`, `bar=None`, and the
   three R readouts — and its API row carries `target: null`.
2. A PARTIAL plan with no `working_stop` reports the `runner_floor` value with
   `stop_kind='derived_floor'`, **on every surface**, and never `plan.stop_loss`.
3. A PARTIAL plan with `tp2` still renders a progress bar, `runner_entry → tp2`.
4. A PENDING plan reports `distance_to_trigger_r` and `bars_to_expiry`, and its
   approach bar is full at the trigger and empty 1R away.
5. The same plan rendered through all three surfaces reports the same entry,
   stop, target and provenance flags — asserted by a test that builds one plan
   and drives all three.
6. `python scripts/dev/testrun.py full` and `cd frontend && npm test` are both
   green, once, as the plan's final task.
