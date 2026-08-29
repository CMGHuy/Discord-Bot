# Live exit parity — design

**Version:** ui 1.9.2 · bot 1.4.5
**Bump:** bot minor (1.4.x → 1.5.0) · ui none
**Edge:** none (integrity)

The RTH gate (§4.2) does incidentally stop the bot booking exits a real
broker could never have filled, which should raise realised expectancy. **No
measurement backs that and none is claimed here** — this document ships a
correctness fix, and the `Edge:` line says so rather than borrowing the
language of a profit improvement it has not demonstrated.

---

## 1. The problem

`docs/claude/architecture.md` states the invariant this repo's validation
badges rest on:

> `run_backtest(..., exit_model="v2", scale_out=True)` uses the same
> simulator, so **live behavior equals backtested behavior by construction**.

That sentence is currently false. The live 60s manager
(`swingbot/core/planning/plan_manager.py`) and the backtest exit simulator
(`swingbot/core/planning/plan_engine.py`) implement three materially
different rules around the break-even stop move. Every `✅ VALIDATED` badge
in `validation_registry.json` therefore describes a rule the bot does not
run.

The user-visible symptom that surfaced this: **the bot moves the stop to
break-even frequently, and those trades book a small loss rather than the
0.000R a break-even exit is supposed to produce.**

### 1.1 Divergence A — the scratch fill

| | Fill on a break-even stop-out | Recorded R |
|---|---|---|
| Backtest (`plan_engine.py:1161,1177`) | `cur_stop`, i.e. **exactly `entry`** | hardcoded `0.0` |
| Live poll (`plan_manager.py:262-268`) | the **observed 60s poll price** | `(price − entry)/risk`, computed in `_on_event` at `plan_manager.py:204` |

The poll price is by construction at or beyond the stop — that is what
triggered the branch. So every live scratch books a small negative, while
its backtested twin books zero.

The live number is not "more realistic". During continuous regular-hours
trading a resting stop at `entry` fills **at** `entry`; the worse price is
an artifact of sampling the tape once every 60 seconds, not something the
market did to the order. The genuinely worse fill belongs to the *gap* case
— and the code that models gaps correctly (`gap_stop_fill`, and the whole
`_check_bar_active`/`_check_bar_partial` pair) **is never called from
production code**. `git grep check_bar` returns `plan_manager.py` and two
test files, nothing else. So the live path currently applies a
gap-magnitude penalty to every exit including the ones that were not gaps,
and applies no gap model at all to the ones that were.

### 1.2 Divergence B — extended-hours prints

`get_current_price` (`swingbot/core/marketdata/data.py:317`) fetches
1-minute history with `prepost=True`. `trade_monitor`
(`swingbot/commands/scanning/loops.py:449`) runs every 60 seconds with no
market-hours gate.

Consequences, all of them wrong against both the backtest and reality:

- A single thin premarket print **arms the break-even move permanently.**
  The move is one-way and never disarms.
- A single thin after-hours print **closes the position.** A regular stop
  order does not execute outside regular trading hours; no broker would
  have filled this.
- The backtest reads yfinance daily bars, which are regular-hours only. It
  cannot see any of these prints, so it never scores them.

### 1.3 Divergence C — same-session firing

`plan_engine.py:1156-1166`, in both exit walks:

```python
# Conservative ordering: stop first (original stop still governs the
# bar that first reaches the trigger), then target. The moved stop
# only protects bars AFTER the trigger bar.
```

The backtest arms break-even at the end of a bar and lets it govern only
from the *next* bar. The live poller arms it and can fire it **60 seconds
later, the same session.** An intraday round trip through +0.75R and back
to entry — an extremely common daily path — is a continuing trade in the
backtest and a scratch live.

The same divergence applies to the post-TP1 runner floor:
`_scale_out_exit_walk`'s phase-2 loop starts at `tp1_index + 1`, so the
runner floor never governs the TP1 bar. `_step_partial`
(`plan_manager.py:307`) can fire it on the very next poll.

### 1.4 Scale

Descriptive diagnostic, TRAIN window only (2020-01-01..2023-12-31), 89
cached symbols, generic proxy plan (entry at close, stop = 2.0×ATR14,
tp1 = rr×risk), gap-aware fills, N=16,416 paired observations per cell.
**This is hypothesis generation, not a pre-registered selection run, and
nothing in this document changes a threshold or a frozen constant.**

- Scratches are **19–23%** of all closed trades at the horizons the bot
  actually trades.
- **5–20% of them are same-session** (Divergence C) — and that is a floor,
  because daily bars contain no extended-hours prints at all (Divergence B
  is invisible to this measurement entirely).
- Of trades that scratch, only ~55% would have become full losses without
  the break-even stop; **~33% went on to reach TP1.**

The purpose of quoting these is to size the population the three fixes
touch. **They are not an argument for changing the break-even rule** — that
is separate work needing its own pre-registration (§6).

---

## 2. Goal

Make the live exit path implement the rule the backtest measures, so
`architecture.md`'s invariant becomes true again and the registry badges
describe the running bot.

Explicitly **not** a goal: making the break-even rule better. Every
threshold, fraction and frozen constant is unchanged —
`BREAKEVEN_TRIGGER_FRACTION = 0.5`, `RUNNER_FLOOR_FRACTION = 2/3`,
`tp1_fraction = 0.50`, the R:R band. This document changes *when the
existing rule is allowed to act*, never *what it is*.

---

## 3. Non-goals

- **Changing the break-even rule itself.** Trigger fraction, buffer, arming
  on a close rather than a wick, direction-awareness — all separate work,
  all needing a pre-registered TRAIN grid and a VALIDATION shot.
- **Wiring `check_bar()`.** It stays dead. Once the poll path handles gaps
  correctly (§4.3) there is no second consumer to build, and wiring a
  parallel exit authority would create two writers for one transition.
  It gets a docstring saying so and a `known-traps.md` entry, nothing more.
- **Re-measuring the registry.** The badges will describe the corrected
  rule once this ships, but re-running `--emit-registry` is its own task
  with its own cost and is not part of this document.
- **Gating TP1 target fills to regular hours.** §4.2 gates the whole poll
  tick, which covers TP1 as a side effect. That is deliberate and
  consistent — but note the asymmetry it resolves: an extended-hours print
  currently both closes losers *and* banks winners, and fixing only the
  loser half would bias the book the other way.

---

## 4. Design

### 4.1 New module: `swingbot/core/market/session.py`

Stdlib only, no pandas, no network — the same shape as
`swingbot/core/market/opex.py`, which already owns
`ZoneInfo("America/New_York")` and a 16:00 close anchor for a different
policy.

```python
US_MARKET_TZ = ZoneInfo("America/New_York")
RTH_OPEN  = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)

def now_et(now: dt.datetime | None = None) -> dt.datetime
def is_regular_session(now: dt.datetime | None = None) -> bool
def session_date(now: dt.datetime | None = None) -> str   # "YYYY-MM-DD" in ET
```

`is_regular_session` is `Mon-Fri and RTH_OPEN <= t < RTH_CLOSE` in ET.
Every function takes an optional `now` so tests inject a clock rather than
patching `datetime`.

`opex.py` re-imports `US_MARKET_TZ` from here rather than keeping its own
`ZoneInfo` call, so the timezone has one definition. Its `US_CLOSE_TIME`
stays where it is — that constant anchors an opex policy, not a session
boundary, and moving it would ripple into flag-gated behaviour this
document has no business touching.

**Accepted limitation, stated rather than solved.** No holiday or half-day
calendar. On a market holiday `is_regular_session` returns `True` and
`get_current_price` returns the previous session's close — a stale price
that either already armed break-even or already did not, so the gate is
idempotent on that value and the failure is benign. A 13:00 half-day close
has the same shape. Building a holiday calendar to close a benign gap is
not worth the dependency; if it ever stops being benign, that is a new
observation and its own change.

### 4.2 Fix 2 — gate the poll tick to regular hours

`PlanManager.poll()` returns `[]` immediately when
`is_regular_session()` is `False`, behind a new config flag
`INTRADAY_RTH_ONLY`, **default `true`**.

The gate goes on the whole tick, not on the break-even arm alone. Gating
only the arm would leave a state machine that fills entries and closes
positions on prints it refuses to arm break-even on — three rules for one
price feed. One gate, one price universe, matching the regular-hours daily
bars the backtest reads.

**This is the observable change** that makes the bump a `bot minor`: no
plan transitions and therefore no Discord lifecycle alerts fire outside
09:30–16:00 ET. Overnight moves are realised on the first regular-hours
poll instead, which is also where §4.3 prices them correctly as gaps.

The flag exists because this is the one change here a user would notice as
a product difference, and a one-line rollback is cheap insurance on a
change that touches every live position. The other two fixes get no flag —
they correct recorded numbers, and a flag on a wrong number is just a
switch for staying wrong.

### 4.3 Fix 1 — realistic poll fills

`PlanManager` keeps an in-memory per-plan record of the previous
observation:

```python
self._last_seen: dict[str, tuple[str, float]] = {}   # plan_id -> (session_date, price)
```

On a stop breach the fill is chosen by whether the manager watched the
price cross the level:

- **Continuous** — `_last_seen` holds an observation from the **same** ET
  session date, on the safe side of the stop. The market traded through
  the level while the manager was watching, so a resting stop filled **at
  the level**. Fill = `stop`.
- **Discontinuous** — no prior observation this session (first poll after
  the open, or after a restart). This is the gap case: the observed price
  **is** the fill, exactly as `gap_stop_fill` already models it.

In-memory rather than persisted on the plan, deliberately: writing
last-seen to `plans.json` would turn every 60s poll of every open plan into
an atomic file write, where today `store.update()` fires only on a
transition. The cost of the in-memory choice is that a bot restart empties
the map, so the first poll after a restart is treated as discontinuous and
falls back to the observed price — **the conservative direction**, and the
same answer the code gives today.

`gap_stop_fill` is unchanged and keeps its meaning. The new helper is its
poll-path sibling:

```python
def poll_stop_fill(price: float, stop: float, continuous: bool) -> float:
    """Fill for a stop breach seen by the 60s poller.

    `continuous`: a previous poll THIS regular session saw the price on the
    safe side of `stop`, so the tape crossed the level while we were
    watching and a resting stop filled AT it -- the worse price this poll
    happened to sample is a 60-second sampling artifact, not a real fill.
    Otherwise this is the first look since a gap and the observed price IS
    the fill, the same convention gap_stop_fill applies to a bar's open.
    """
    return stop if continuous else price
```

Direction-free by construction: clamping to `stop` is the better price for
a long and for a short alike.

### 4.4 Fix 3 — the moved stop protects later sessions only

Two new `TradePlanV2` fields, both `str | None = None`, both ET session
dates:

- `be_armed_session` — set when the break-even move arms.
- `runner_floor_session` — set when TP1 fires and the runner floor is
  written.

`plan_from_dict` (`plan_engine.py:157-162`) filters to known field names and
relies on dataclass defaults for the rest, so **plans already persisted in
`data/plans.json` load unchanged with both fields `None`.** No migration.

A `None` on a plan that armed before this ships means "armed on an unknown
session", which reads as "not this session" and lets the stop govern
immediately — the pre-existing behaviour, which is the right answer for a
plan already carrying a moved stop.

**ACTIVE.** The break-even stop governs only when
`plan.be_armed_session != session_date()`. While it does not govern, the
original `stop_loss` still does — exactly `plan_engine.py:1156`'s "original
stop still governs the bar that first reaches the trigger".

**This changes an outcome label, and the label matters.** Today
`plan_manager.py:263` reads `reason = "scratch" if plan.working_stop is not
None else "loss"`. Under §4.4 a plan can hold a `working_stop` that is not
yet governing; if price reaches the *original* stop that same session the
exit is a full −1R **loss**, and calling it a scratch would file a −1R
outcome under the label the analytics treat as ~0R. The reason must key off
*which stop was breached*, not off whether `working_stop` is populated.

**PARTIAL.** The runner floor is not checked at all while
`plan.runner_floor_session == session_date()`, matching phase 2's
`range(tp1_index + 1, ...)`. The chandelier ratchet still runs that session
— the backtest also seeds `extreme_close` from the TP1 bar's close — so
only the stop *check* is suppressed, never the trail's bookkeeping.

### 4.5 What is deliberately left alone

`_check_bar_active` and `_check_bar_partial` get none of the above. They
are unreachable from production code and applying three fixes to a dead
path would be three untested behaviours pretending to be tested ones. They
get a docstring naming them unwired and a `known-traps.md` row, so the next
session finds out before spending an hour on them rather than after.

---

## 5. Verification

Unit tests only; every fix is deterministic given an injected clock and the
existing `FakePriceFeed`. No backtest run is needed or appropriate — this
document changes no threshold and makes no expectancy claim, so there is
nothing here for a pre-registration to test.

The behaviours that must be pinned:

1. `is_regular_session` at each boundary — 09:29, 09:30, 15:59, 16:00,
   Saturday, Sunday — and `session_date` across a UTC-vs-ET date boundary
   (22:00 ET is the *next* day in UTC and must still report today's ET
   session).
2. `poll()` outside regular hours returns `[]` and writes nothing; with
   `INTRADAY_RTH_ONLY=false` it behaves exactly as today.
3. A continuous same-session stop breach fills at the stop, not at the poll
   price — the direct regression test for the reported symptom.
4. The first poll of a session fills at the observed price (gap preserved).
5. Break-even armed this session does not fire this session; it does fire
   the next session.
6. Original stop breached in the same session the break-even armed reports
   `reason == "loss"` with `r == -1.0`, not `"scratch"`.
7. The runner floor armed this session does not fire this session.
8. A `plans.json` record written before this change loads with both new
   fields `None` and its moved stop governing immediately.

---

## 6. What this unblocks, and does not authorise

Once live and backtest agree, the Tier 2 questions from the investigation
become measurable against a harness that means something:

- arming break-even on a close rather than a wick,
- `BREAKEVEN_TRIGGER_FRACTION` 0.5 → 0.75,
- a partial floor (−0.5R) instead of full break-even, mirroring what v39
  already gave the runner leg,
- direction-aware break-even.

**Each is a new pre-registered hypothesis with its own TRAIN grid and its
own one-shot VALIDATION.** Nothing in this document is evidence for any of
them, and the §1.4 diagnostic is explicitly not a substitute for that
budget — it was run to size a bug, on a proxy plan with no entry edge, and
it selects nothing.

---

## Parallelisation

- **Group 1 (parallel):** the `session.py` module and the `TradePlanV2`
  field additions — different files (`core/market/session.py` +
  `core/market/opex.py` vs `core/planning/plan_engine.py`), and neither
  consumes a symbol the other introduces.
- **Sequential after Group 1:** every `plan_manager.py` change. All four
  fixes edit the same two methods (`_step_active`, `_step_partial`) and
  each consumes what the previous one wrote; concurrent sessions share this
  working tree, so two agents on `plan_manager.py` silently overwrite each
  other.
- **Sequential last:** the docs task (it describes the finished behaviour)
  and the full-suite verification.
