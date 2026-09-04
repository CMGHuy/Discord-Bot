# v73 — Plan-view projection, Part 1: the projection

> Part of the v73 plan. Header block, global constraints and the parallelisation
> map live in `_0-index`. **Read that first** — two constraints there are the
> ones a task here is most likely to violate without noticing: `plan_view()`
> must stay pure, and `runner_floor` is the only legacy stop fallback.

# Phase A — the projection

### Task A1: `PlanView` shapes and the PENDING branch

**Files:**
- Create: `swingbot/core/presentation/plan_view.py`
- Test: `tests/presentation/test_plan_view_pending.py`

**Interfaces:**
- Consumes: `swingbot.core.planning.plan_types.TradePlanV2` (fields `status`, `direction`, `trigger_price`, `entry_price`, `stop_loss`, `tp1`, `tp2`, `expiry_bars`, `created_at`, `working_stop`, `legs_realized`, `tp1_fraction`).
- Produces: `BarSpec`, `BankedLeg`, `PlanView`, `plan_view(plan, *, price=None, now=None, bars_since_created=None) -> PlanView`, `_risk(plan) -> float | None`.

A pending plan's two questions are *will it trigger* and *when does it die*.
Neither surface answers either today. Distance is expressed in **risk units**
rather than percent so the number is comparable across tickers.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_plan_view_pending.py
"""PENDING: distance to trigger in R, an approach bar, and an expiry count.

Risk units, not percent: 'AAPL is 0.4R from triggering' compares across
tickers in a way '0.8% away' does not.
"""
import pytest

from swingbot.core.presentation.plan_view import plan_view


class FakePlan:
    """A v2-shaped stand-in. The projection reads attributes only, so a
    stand-in is enough and keeps these tests independent of the store."""

    def __init__(self, **kw):
        defaults = dict(
            status="PENDING", direction="bullish", trigger_price=100.0,
            entry_price=None, stop_loss=90.0, tp1=120.0, tp2=None,
            expiry_bars=5, created_at="2026-09-01", working_stop=None,
            legs_realized=[], tp1_fraction=0.5,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_phase_is_the_plans_status():
    assert plan_view(FakePlan()).phase == "PENDING"


def test_at_the_trigger_the_distance_is_zero_and_the_bar_is_full():
    v = plan_view(FakePlan(), price=100.0)
    assert v.distance_to_trigger_r == pytest.approx(0.0)
    assert v.bar_kind == "approach"
    assert v.bar.pos == pytest.approx(100.0)


def test_one_r_below_the_trigger_empties_the_bar():
    # risk = |100 - 90| = 10, so 1R below the trigger is price 90.
    v = plan_view(FakePlan(), price=90.0)
    assert v.distance_to_trigger_r == pytest.approx(1.0)
    assert v.bar.pos == pytest.approx(0.0)


def test_half_an_r_away_fills_the_bar_halfway():
    v = plan_view(FakePlan(), price=95.0)
    assert v.distance_to_trigger_r == pytest.approx(0.5)
    assert v.bar.pos == pytest.approx(50.0)


def test_past_the_trigger_clamps_the_bar_but_not_the_number():
    """A pending plan can sit above its trigger for a tick before the
    fill lands. The bar is 0..100 by definition; the distance is not, and
    flattening it would hide that price has already crossed."""
    v = plan_view(FakePlan(), price=105.0)
    assert v.distance_to_trigger_r == pytest.approx(-0.5)
    assert v.bar.pos == pytest.approx(100.0)


def test_bearish_distance_is_signed_the_same_way():
    """Bearish: trigger BELOW price means 'not there yet', same as bullish
    means 'not up there yet'. Positive = still to travel, both ways."""
    plan = FakePlan(direction="bearish", trigger_price=100.0, stop_loss=110.0,
                    tp1=80.0)
    v = plan_view(plan, price=110.0)
    assert v.distance_to_trigger_r == pytest.approx(1.0)
    assert v.bar.pos == pytest.approx(0.0)


def test_no_price_means_no_bar_but_still_an_expiry():
    v = plan_view(FakePlan(), price=None, bars_since_created=2)
    assert v.bar_kind == "none"
    assert v.bar is None
    assert v.distance_to_trigger_r is None
    assert v.bars_to_expiry == 3


def test_bars_to_expiry_counts_down_and_floors_at_zero():
    assert plan_view(FakePlan(), bars_since_created=0).bars_to_expiry == 5
    assert plan_view(FakePlan(), bars_since_created=5).bars_to_expiry == 0
    # lifecycle.pending_expired uses `>`, so the 5th bar is still alive;
    # past it the count does not go negative.
    assert plan_view(FakePlan(), bars_since_created=9).bars_to_expiry == 0


def test_bars_to_expiry_is_none_when_the_caller_does_not_know():
    """The projection is pure -- it cannot count bars itself. A caller
    with no bar count gets None, not a guess."""
    assert plan_view(FakePlan()).bars_to_expiry is None


def test_zero_risk_plan_degrades_rather_than_dividing_by_zero():
    v = plan_view(FakePlan(trigger_price=100.0, stop_loss=100.0), price=99.0)
    assert v.distance_to_trigger_r is None
    assert v.bar_kind == "none"


def test_pending_reports_no_banked_leg_and_no_partial_readouts():
    v = plan_view(FakePlan(), price=95.0)
    assert v.banked is None
    assert v.target_is_banked_tp1 is False
    assert (v.floor_r, v.price_r, v.headroom_r) == (None, None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/presentation/test_plan_view_pending.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.presentation.plan_view'`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/presentation/plan_view.py
"""One derivation of what a plan looks like, for every surface.

Three renderers used to answer this independently -- admin/api_v1/trades.py,
commands/plans.py and core/scanning/plan_table.py -- and they disagreed on
what a PARTIAL runner's stop and target are. That is not a cosmetic split:
the API's fallbacks put the stop on the WRONG SIDE OF ENTRY and the target on
a level the position had already banked, then drew a progress bar between
them.

This module is the single answer. It is PURE: a plan and an optional price
in, a dataclass out. No store, no clock, no I/O -- a caller that knows the
bar count or the time passes them in. That is what lets all three surfaces
share it and what lets the correctness cases be unit tests instead of
fixtures.

It derives; it never stores. Writing any of this back onto plans.json would
create a second authority for plan state -- see docs/claude/known-traps.md on
PlanManager.check_bar().
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.planning.exit_sim import runner_floor


@dataclass(frozen=True)
class BarSpec:
    """A bar the surface draws rather than calculates.

    `lo`/`hi` are the price endpoints; `pos` and `entry_pos` are already
    percentages along them, clamped to 0..100 -- price runs past a stop or
    target all the time and a bar is 0..100 by definition. The unclamped
    truth stays on the PlanView's own numeric fields.
    """
    lo: float
    hi: float
    pos: float
    entry_pos: float | None = None


@dataclass(frozen=True)
class BankedLeg:
    fraction: float
    exit_price: float
    r: float


@dataclass(frozen=True)
class PlanView:
    """The display facts AND their provenance.

    The provenance is the half that matters. A surface handed a bare
    `target` has to guess whether it is a live level or a banked one, and
    the three surfaces guessed differently. `target_is_banked_tp1`,
    `stop_kind` and `bar_kind` remove the guess.
    """
    phase: str                     # PENDING | ACTIVE | PARTIAL | other
    entry: float | None
    stop: float | None
    target: float | None
    target_is_banked_tp1: bool = False
    stop_kind: str = "risk"        # risk | trailing | derived_floor
    bar_kind: str = "none"         # progress | approach | trailing | none
    bar: BarSpec | None = None
    banked: BankedLeg | None = None
    # PENDING only
    distance_to_trigger_r: float | None = None
    bars_to_expiry: int | None = None
    # PARTIAL-trailing only
    floor_r: float | None = None
    price_r: float | None = None
    headroom_r: float | None = None


def _risk(plan) -> float | None:
    """The plan's own risk, |entry-or-trigger - stop|. None when zero: a
    plan that cannot lose cannot be priced in R, and dividing by it would
    turn a malformed record into an exception at render time."""
    ref = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    if ref is None or plan.stop_loss is None:
        return None
    risk = abs(ref - plan.stop_loss)
    return risk or None


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def _pending_view(plan, price, bars_since_created) -> PlanView:
    """Approach bar: full at the trigger, empty 1R away.

    1R is a natural, bounded reference the plan already carries, so the bar
    needs no stored 'price when created' and means the same thing on every
    ticker.
    """
    bars_left = None
    if bars_since_created is not None and plan.expiry_bars is not None:
        # lifecycle.pending_expired uses `>`, so the expiry_bars-th bar is
        # still alive; the count floors at 0 rather than going negative.
        bars_left = max(0, plan.expiry_bars - bars_since_created)

    risk = _risk(plan)
    if price is None or risk is None or plan.trigger_price is None:
        return PlanView(phase=plan.status, entry=None, stop=plan.stop_loss,
                        target=plan.tp1, bar_kind="none",
                        bars_to_expiry=bars_left)

    sign = 1 if plan.direction == "bullish" else -1
    # Positive = still to travel, both directions.
    distance_r = (plan.trigger_price - price) * sign / risk
    lo = plan.trigger_price - sign * risk
    return PlanView(
        phase=plan.status, entry=None, stop=plan.stop_loss, target=plan.tp1,
        bar_kind="approach",
        bar=BarSpec(lo=lo, hi=plan.trigger_price,
                    pos=_clamp_pct((1.0 - distance_r) * 100.0)),
        distance_to_trigger_r=distance_r, bars_to_expiry=bars_left)


def plan_view(plan, *, price: float | None = None, now=None,
              bars_since_created: int | None = None) -> PlanView:
    """Project `plan` into the facts a surface renders.

    `now` is accepted for callers that have it and reserved for phases that
    need a clock; the PENDING branch counts bars, not time, so it takes
    `bars_since_created` instead. Both are passed in rather than read here:
    this function is pure.
    """
    status = getattr(plan, "status", None)
    if status == "PENDING":
        return _pending_view(plan, price, bars_since_created)
    return PlanView(phase=status, entry=plan.entry_price, stop=plan.stop_loss,
                    target=plan.tp1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/presentation/test_plan_view_pending.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/plan_view.py tests/presentation/test_plan_view_pending.py
git commit -m "feat(v73): PlanView shapes and the PENDING approach bar"
```

---

### Task A2: The ACTIVE branch

**Files:**
- Modify: `swingbot/core/presentation/plan_view.py`
- Test: `tests/presentation/test_plan_view_active.py`

**Interfaces:**
- Consumes: `BarSpec`, `PlanView`, `_risk`, `_clamp_pct` from A1.
- Produces: `_active_view(plan, price) -> PlanView`, and a `plan_view` dispatch that routes `"ACTIVE"` to it.

An ACTIVE plan is the case today's bar already gets right: a progress bar from
stop to target with entry marked. This task reproduces that arithmetic inside
the projection so the API can stop computing its own, and adds the one guard
`_status_fields:711` already has — a malformed record degrades to no bar rather
than one drawn confidently backwards.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_plan_view_active.py
"""ACTIVE: the progress bar today's API already draws correctly, moved
into the projection so there is one implementation instead of two.
"""
import pytest

from swingbot.core.presentation.plan_view import plan_view


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(
            status="ACTIVE", direction="bullish", trigger_price=100.0,
            entry_price=100.0, stop_loss=90.0, tp1=120.0, tp2=None,
            expiry_bars=5, created_at="2026-09-01", working_stop=None,
            legs_realized=[], tp1_fraction=0.5,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_active_uses_the_original_levels():
    v = plan_view(FakePlan(), price=110.0)
    assert (v.entry, v.stop, v.target) == (100.0, 90.0, 120.0)
    assert v.stop_kind == "risk"
    assert v.target_is_banked_tp1 is False


def test_bar_spans_stop_to_target_with_entry_marked():
    v = plan_view(FakePlan(), price=105.0)
    assert v.bar_kind == "progress"
    assert (v.bar.lo, v.bar.hi) == (90.0, 120.0)
    # price 105 is 15 of the 30-wide span above the stop
    assert v.bar.pos == pytest.approx(50.0)
    assert v.bar.entry_pos == pytest.approx(100 / 3, abs=0.1)


def test_bearish_bar_runs_the_other_way():
    plan = FakePlan(direction="bearish", entry_price=100.0, stop_loss=110.0,
                    tp1=80.0)
    v = plan_view(plan, price=95.0)
    assert v.bar_kind == "progress"
    # 95 is 15 of the 30-wide span below the stop, moving toward target
    assert v.bar.pos == pytest.approx(50.0)


def test_price_past_the_target_clamps_the_bar():
    v = plan_view(FakePlan(), price=130.0)
    assert v.bar.pos == pytest.approx(100.0)


def test_a_working_stop_on_an_active_plan_is_the_breakeven_stop():
    """_step_active arms working_stop at breakeven BEFORE TP1. That is a
    real, live stop and the bar must use it -- but it is not a trailing
    runner stop, so it is still stop_kind 'risk'."""
    v = plan_view(FakePlan(working_stop=100.0), price=110.0)
    assert v.stop == 100.0
    assert v.stop_kind == "risk"
    assert v.bar.lo == 100.0


def test_no_price_means_no_bar():
    v = plan_view(FakePlan(), price=None)
    assert v.bar_kind == "none"
    assert v.bar is None


def test_malformed_record_degrades_instead_of_drawing_backwards():
    """Stop on the wrong side of the target. api_v1/trades.py:711 already
    refuses to draw this; the projection keeps that refusal so the guard
    does not get lost in the move."""
    v = plan_view(FakePlan(stop_loss=130.0, tp1=120.0), price=125.0)
    assert v.bar_kind == "none"
    assert v.bar is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/presentation/test_plan_view_active.py -v`
Expected: FAIL — `test_bar_spans_stop_to_target_with_entry_marked` fails; `bar_kind` is `"none"` because A1's fallthrough returns a bare view.

- [ ] **Step 3: Write minimal implementation**

Add to `swingbot/core/presentation/plan_view.py`, above `plan_view`:

```python
def _progress_bar(lo: float, hi: float, price: float, entry: float | None,
                  is_bull: bool) -> BarSpec | None:
    """Stop -> target, with entry marked. None when the span is
    non-positive, i.e. the stop sits on the wrong side of the target.

    Degrading is deliberate: a malformed record should render no bar
    rather than one that is confidently backwards. This is the same guard
    admin/api_v1/trades.py:711 already applied.
    """
    span = (hi - lo) if is_bull else (lo - hi)
    if span <= 0:
        return None
    pos = ((price - lo) if is_bull else (lo - price)) / span * 100.0
    entry_pos = None
    if entry is not None:
        entry_pos = _clamp_pct(((entry - lo) if is_bull else (lo - entry))
                               / span * 100.0)
    return BarSpec(lo=lo, hi=hi, pos=_clamp_pct(pos), entry_pos=entry_pos)


def _active_view(plan, price) -> PlanView:
    """The original levels, with the break-even stop when one is armed.

    `working_stop` before TP1 is the break-even stop `_step_active` arms at
    breakeven_trigger_fraction -- a real live stop the bar must use, but
    NOT a trailing runner stop, so stop_kind stays 'risk'. Only a PARTIAL
    plan has a trailing one.
    """
    stop = plan.working_stop if plan.working_stop is not None else plan.stop_loss
    is_bull = plan.direction == "bullish"
    bar = (_progress_bar(stop, plan.tp1, price, plan.entry_price, is_bull)
           if price is not None and stop is not None and plan.tp1 is not None
           else None)
    return PlanView(phase=plan.status, entry=plan.entry_price, stop=stop,
                    target=plan.tp1, stop_kind="risk",
                    bar_kind="progress" if bar else "none", bar=bar)
```

and route to it in `plan_view`, replacing the bare fallthrough:

```python
    status = getattr(plan, "status", None)
    if status == "PENDING":
        return _pending_view(plan, price, bars_since_created)
    if status == "ACTIVE":
        return _active_view(plan, price)
    return PlanView(phase=status, entry=plan.entry_price, stop=plan.stop_loss,
                    target=plan.tp1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/presentation/test_plan_view_active.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/plan_view.py tests/presentation/test_plan_view_active.py
git commit -m "feat(v73): ACTIVE progress bar in the projection"
```

---

### Task A3: The PARTIAL branch

**Files:**
- Modify: `swingbot/core/presentation/plan_view.py`
- Test: `tests/presentation/test_plan_view_partial.py`

**Interfaces:**
- Consumes: everything from A1–A2, plus `runner_floor` from `swingbot.core.planning.exit_sim`.
- Produces: `_partial_view(plan, price) -> PlanView`, and a `plan_view` dispatch routing `"PARTIAL"` to it.

The task the whole spec exists for. Three rules, each replacing a different
wrong answer:

1. **Entry** is the TP1 leg's own fill, not the `tp1` level — they differ on a
   gap-through.
2. **Stop** is `working_stop` (`trailing`), falling back to
   `runner_floor(entry, tp1)` (`derived_floor`) — **never** `plan.stop_loss`,
   which sits on the opposite side of entry.
3. **Target** is `tp2` or `None`. The `tp1` fallback is deleted; a no-TP2
   runner has no destination, so it gets R readouts and no bar.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_plan_view_partial.py
"""PARTIAL: the runner's own numbers, never the original leg's.

PARTIAL-without-tp2 is the NORMAL in-session outcome, not an edge case --
_step_active:320 transitions on a TP1 touch with no tp2 check at all, and
_scale_out_exit_walk does the same in every backtest. So the no-tp2 cases
below are the common path, not the exotic one.
"""
import pytest

from swingbot.core.presentation.plan_view import plan_view


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(
            status="PARTIAL", direction="bullish", trigger_price=100.0,
            entry_price=100.0, stop_loss=90.0, tp1=120.0, tp2=None,
            expiry_bars=5, created_at="2026-09-01",
            # runner_floor(100, 120) = 100 + 2/3*20 = 113.333...
            working_stop=113.3333333,
            legs_realized=[{"fraction": 0.5, "exit_price": 121.0, "r": 2.1,
                            "reason": "tp1"}],
            tp1_fraction=0.5,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_entry_is_the_tp1_legs_actual_fill_not_the_tp1_level():
    """They differ on a gap-through: the leg filled at 121 on a level of
    120, and 121 is what the runner actually started from."""
    v = plan_view(FakePlan(), price=125.0)
    assert v.entry == 121.0


def test_entry_falls_back_to_tp1_when_no_leg_was_recorded():
    v = plan_view(FakePlan(legs_realized=[]), price=125.0)
    assert v.entry == 120.0


def test_stop_is_the_working_stop_and_is_labelled_trailing():
    v = plan_view(FakePlan(), price=125.0)
    assert v.stop == pytest.approx(113.3333333)
    assert v.stop_kind == "trailing"


def test_missing_working_stop_falls_back_to_runner_floor_never_stop_loss():
    """THE regression test for the API's wrong fallback.

    runner_floor(100, 120) = 113.33 -- a floor in PROFIT, above entry.
    plan.stop_loss is 90 -- the original risk stop, BELOW entry. The old
    API code used the second one and fed it to a progress bar.
    """
    v = plan_view(FakePlan(working_stop=None), price=125.0)
    assert v.stop == pytest.approx(113.3333333)
    assert v.stop != 90.0
    assert v.stop_kind == "derived_floor"


def test_no_tp2_reports_no_target_and_flags_the_banked_tp1():
    v = plan_view(FakePlan(tp2=None), price=125.0)
    assert v.target is None
    assert v.target_is_banked_tp1 is True


def test_no_tp2_draws_no_bar_and_reports_r_instead():
    """A runner with no tp2 has no destination -- it runs until the trail
    takes it. R readouts state that mechanism; a bar would imply a
    target that does not exist."""
    v = plan_view(FakePlan(tp2=None), price=125.0)
    assert v.bar_kind == "trailing"
    assert v.bar is None
    # risk = |100 - 90| = 10
    assert v.floor_r == pytest.approx(1.3333333)   # (113.33 - 100) / 10
    assert v.price_r == pytest.approx(2.5)         # (125 - 100) / 10
    assert v.headroom_r == pytest.approx(1.1666667)


def test_with_tp2_a_real_progress_bar_returns():
    v = plan_view(FakePlan(tp2=140.0), price=125.0)
    assert v.target == 140.0
    assert v.target_is_banked_tp1 is False
    assert v.bar_kind == "progress"
    assert (v.bar.lo, v.bar.hi) == (pytest.approx(113.3333333), 140.0)
    assert v.floor_r is None


def test_banked_leg_is_reported():
    v = plan_view(FakePlan(), price=125.0)
    assert v.banked.fraction == 0.5
    assert v.banked.exit_price == 121.0
    assert v.banked.r == 2.1


def test_banked_is_none_when_no_leg_was_recorded():
    assert plan_view(FakePlan(legs_realized=[]), price=125.0).banked is None


def test_bearish_partial_gets_the_same_treatment():
    """A bearish runner's floor sits BELOW entry, which reads as backwards
    unless the surface labels it -- which is exactly what stop_kind is
    for. runner_floor(100, 80) = 100 + 2/3*(-20) = 86.67."""
    plan = FakePlan(direction="bearish", entry_price=100.0, stop_loss=110.0,
                    tp1=80.0, tp2=None, working_stop=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 79.0,
                                    "r": 2.1, "reason": "tp1"}])
    v = plan_view(plan, price=75.0)
    assert v.stop == pytest.approx(86.6666667)
    assert v.stop_kind == "derived_floor"
    assert v.entry == 79.0
    assert v.target is None
    assert v.bar_kind == "trailing"
    # risk = |100 - 110| = 10; price 75 is 2.5R in profit for a short
    assert v.price_r == pytest.approx(2.5)
    assert v.floor_r == pytest.approx(1.3333333)


def test_no_price_on_a_no_tp2_runner_still_reports_the_floor():
    """The floor is a property of the plan, not of the tape. Losing it
    when the price feed is down would hide how much is locked in."""
    v = plan_view(FakePlan(tp2=None), price=None)
    assert v.floor_r == pytest.approx(1.3333333)
    assert v.price_r is None
    assert v.headroom_r is None
    assert v.bar_kind == "trailing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/presentation/test_plan_view_partial.py -v`
Expected: FAIL — the fallthrough returns `entry=100.0`, so `test_entry_is_the_tp1_legs_actual_fill_not_the_tp1_level` fails first.

- [ ] **Step 3: Write minimal implementation**

Add to `swingbot/core/presentation/plan_view.py`:

```python
def _partial_view(plan, price) -> PlanView:
    """The runner leg as a position of its own.

    Once TP1 fires, the plan's original trigger/stop/tp1 are history. The
    money questions are what is in the bank and where the remaining leg
    lives, so this reports the runner's numbers and never the original
    ones.

    The `tp1` target fallback the three old renderers each invented is
    GONE. A runner with no tp2 has no destination -- it runs until the
    chandelier trail takes it -- so it reports R readouts and no bar. A bar
    toward tp1 was the original defect: the position had already passed
    that level, so the bar sat pinned at 100% for the rest of its life.
    """
    leg = plan.legs_realized[0] if plan.legs_realized else None
    banked = (BankedLeg(fraction=leg["fraction"], exit_price=leg["exit_price"],
                        r=leg["r"]) if leg else None)
    runner_entry = leg["exit_price"] if leg else plan.tp1

    orig_entry = (plan.entry_price if plan.entry_price is not None
                  else plan.trigger_price)
    if plan.working_stop is not None:
        stop, stop_kind = plan.working_stop, "trailing"
    else:
        # Legacy rows only -- _step_active writes working_stop at the
        # transition. NEVER plan.stop_loss: runner_floor is above entry
        # (in profit), the original risk stop is below it.
        stop, stop_kind = runner_floor(orig_entry, plan.tp1), "derived_floor"

    is_bull = plan.direction == "bullish"
    if plan.tp2 is not None:
        bar = (_progress_bar(stop, plan.tp2, price, runner_entry, is_bull)
               if price is not None else None)
        return PlanView(phase=plan.status, entry=runner_entry, stop=stop,
                        target=plan.tp2, stop_kind=stop_kind,
                        bar_kind="progress" if bar else "none", bar=bar,
                        banked=banked)

    risk = _risk(plan)
    sign = 1 if is_bull else -1
    floor_r = price_r = headroom_r = None
    if risk:
        floor_r = (stop - orig_entry) * sign / risk
        if price is not None:
            price_r = (price - orig_entry) * sign / risk
            headroom_r = price_r - floor_r
    return PlanView(phase=plan.status, entry=runner_entry, stop=stop,
                    target=None, target_is_banked_tp1=True,
                    stop_kind=stop_kind, bar_kind="trailing", bar=None,
                    banked=banked, floor_r=floor_r, price_r=price_r,
                    headroom_r=headroom_r)
```

and add the dispatch line in `plan_view`, before the fallthrough:

```python
    if status == "PARTIAL":
        return _partial_view(plan, price)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/presentation/test_plan_view_partial.py`
Expected: `0 failed`, 11 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/plan_view.py tests/presentation/test_plan_view_partial.py
git commit -m "feat(v73): PARTIAL runner projection -- no more tp1 target fallback"
```
