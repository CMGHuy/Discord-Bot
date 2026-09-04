# v73 — Plan-view projection, Part 2: the surfaces

> Part of the v73 plan. Header block, global constraints and the parallelisation
> map live in `_0-index`. **Read that first.** Every task here consumes
> `plan_view`, `PlanView`, `BarSpec` and `BankedLeg` from Part 1.

# Phase B — the Python surfaces

B1, B2 and B3 are **parallel** — disjoint files, no shared symbol beyond the
projection each imports. B4 needs all three.

### Task B1: The admin API renders from the projection

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py:190-239` (`_row_from_plan`), `:686-748` (`_status_fields`, `_attach_status_fields`)
- Test: `tests/admin/test_trades_partial_row.py`

**Interfaces:**
- Consumes: `plan_view(plan, *, price=None, now=None, bars_since_created=None) -> PlanView` from A1; `PlanView` fields `entry`, `stop`, `target`, `target_is_banked_tp1`, `stop_kind`, `bar_kind`, `bar`, `banked`, `distance_to_trigger_r`, `bars_to_expiry`, `floor_r`, `price_r`, `headroom_r`.
- Produces: row keys `target_is_banked_tp1: bool`, `stop_kind: str`, `bar_kind: str`, `distance_to_trigger_r`, `bars_to_expiry`, `floor_r`, `price_r`, `headroom_r` on every plan row; `target` now `null` for a no-TP2 runner.

`_row_from_plan` takes a `dict`, not a `TradePlanV2`, so it needs a tiny
attribute adapter — `plan_view` reads attributes. Keep the adapter local to
this file; it is a shim over one call site, not a new public type.

- [ ] **Step 1: Write the failing test**

```python
# tests/admin/test_trades_partial_row.py
"""The API row must carry the projection's provenance, not just numbers.

The bug this replaces: `current_target = (tp2 if is_partial else None) or
tp1` shipped a banked level as a live target, and `_status_fields` then
drew a progress bar toward a level the position had already passed.
"""
from swingbot.admin.api_v1.trades import _row_from_plan


def partial_plan(**kw):
    base = {
        "plan_id": "p1", "ticker": "AAPL", "status": "PARTIAL",
        "direction": "bullish", "strategy": "MACD", "horizon_key": "3m",
        "entry_price": 100.0, "trigger_price": 100.0, "stop_loss": 90.0,
        "tp1": 120.0, "tp2": None, "working_stop": 113.3333333,
        "legs_realized": [{"fraction": 0.5, "exit_price": 121.0, "r": 2.1,
                           "reason": "tp1"}],
        "tp1_fraction": 0.5, "expiry_bars": 5, "created_at": "2026-09-01",
        "badge": "WEAK", "quality_score": 3,
    }
    base.update(kw)
    return base


def test_no_tp2_runner_ships_a_null_target_and_the_flag():
    row = _row_from_plan(partial_plan(), None, set())
    assert row["target"] is None
    assert row["target_is_banked_tp1"] is True
    assert row["bar_kind"] == "trailing"


def test_no_tp2_runner_ships_the_r_readouts():
    row = _row_from_plan(partial_plan(), None, set())
    assert round(row["floor_r"], 4) == 1.3333


def test_stop_is_the_runner_floor_never_the_original_risk_stop():
    """The old code fell back to plan.stop_loss (90.0, BELOW entry).
    runner_floor is 113.33, ABOVE entry -- opposite sides."""
    row = _row_from_plan(partial_plan(working_stop=None), None, set())
    assert round(row["stop_loss"], 4) == 113.3333
    assert row["stop_loss"] != 90.0
    assert row["stop_kind"] == "derived_floor"


def test_a_tp2_runner_keeps_a_real_target_and_bar():
    row = _row_from_plan(partial_plan(tp2=140.0), None, set())
    assert row["target"] == 140.0
    assert row["target_is_banked_tp1"] is False
    assert row["bar_kind"] == "progress"


def test_banked_leg_fields_survive_the_move():
    row = _row_from_plan(partial_plan(), None, set())
    assert row["banked_fraction"] == 0.5
    assert row["banked_exit_price"] == 121.0
    assert row["banked_r"] == 2.1


def test_pending_row_carries_the_expiry_and_no_bar():
    row = _row_from_plan(
        partial_plan(status="PENDING", entry_price=None, working_stop=None,
                     legs_realized=[]), None, set())
    assert row["bar_kind"] in ("approach", "none")
    assert row["target_is_banked_tp1"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/admin/test_trades_partial_row.py -v`
Expected: FAIL — `KeyError: 'target_is_banked_tp1'`

- [ ] **Step 3: Write minimal implementation**

Replace the derivation block at `trades.py:199-216` (the comment block, `is_partial`, `legs_realized`, `banked_leg`, `current_stop`, `current_target`) with:

```python
    # v73: one projection, shared with commands/plans.py and
    # core/scanning/plan_table.py. The three used to disagree about what a
    # PARTIAL runner's stop and target are; this file was the one that got
    # BOTH wrong (a banked tp1 as a live target, and the original risk stop
    # -- below entry -- where the runner floor is above it) and the only one
    # that then drew a progress bar between them.
    view = plan_view(_AttrPlan(plan), price=None)
```

Add the adapter and the import at the top of the file:

```python
from swingbot.core.presentation.plan_view import plan_view


class _AttrPlan:
    """`_row_from_plan` receives plans as dicts; `plan_view` reads
    attributes. A local shim over one call site rather than a new public
    type -- returns None for anything absent, which is what a dict-shaped
    legacy row does anyway."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name):
        return self._data.get(name)
```

Then replace the row's four affected keys and add the new ones:

```python
        "entry": plan.get("entry_price"),
        "stop_loss": view.stop,
        "target": view.target,
        "target2": plan.get("tp2"),
        "target_is_banked_tp1": view.target_is_banked_tp1,
        "stop_kind": view.stop_kind,
        "bar_kind": view.bar_kind,
        "distance_to_trigger_r": view.distance_to_trigger_r,
        "bars_to_expiry": view.bars_to_expiry,
        "floor_r": view.floor_r,
        "price_r": view.price_r,
        "headroom_r": view.headroom_r,
        "banked_fraction": view.banked.fraction if view.banked else None,
        "banked_exit_price": view.banked.exit_price if view.banked else None,
        "banked_r": view.banked.r if view.banked else None,
```

Finally, make `_attach_status_fields` respect `bar_kind` — replace its loop
body at `trades.py:739-748`:

```python
    for row in rows:
        # `trailing` is a real, live position that simply has no destination
        # to draw a bar toward -- it is NOT terminal, and its R readouts are
        # already on the row. Terminal and PENDING rows keep the label-only
        # treatment they had.
        if (row["status"] in _TERMINAL or row["status"] == "PENDING"
                or row.get("bar_kind") == "trailing"):
            row.update({"progress_pct": None, "entry_pct": None,
                        "progress_band": None, "blink_seconds": None,
                        "status_label": row["status"]})
        else:
            row.update(_status_fields(row, row.get("current_price")))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py`
Expected: `0 failed`, 6 passed

Then check the file's existing suite, which contains the test this task
changes the behaviour of:

Run: `python -m pytest tests/admin -k partial -v`
Expected: `test_partial_plan_falls_back_when_the_runner_fields_are_unset`
**fails** — it asserts the `tp1` target fallback this task deletes. Update it
to assert `target is None` and `target_is_banked_tp1 is True`, and add a
comment: *"v73: the fallback this asserted is gone -- a runner with no tp2 has
no target, and shipping tp1 here pinned the progress bar at 100%."* Do not
delete the test.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_trades_partial_row.py
git commit -m "feat(v73): admin API renders plan rows from the projection"
```

---

### Task B2: The Discord plan board renders from the projection

**Files:**
- Modify: `swingbot/commands/plans.py:25-77` (`_partial_tail`, `_plan_line`)
- Test: `tests/commands/test_plan_board_lines.py`

**Interfaces:**
- Consumes: `plan_view` from A1; `ui.fmt_price`, `ui.fmt_r`, `ui.fmt_pct`, `banked_leg_pct_and_amount`, `signed_money` already imported by this module.
- Produces: no new public symbols — `_partial_tail(plan)` and `_plan_line(plan)` keep their signatures.

- [ ] **Step 1: Write the failing test**

```python
# tests/commands/test_plan_board_lines.py
"""The Discord board line, rendered from the shared projection.

It was already the most honest of the three renderers -- it labelled the
no-tp2 case. What it lacked was a stop for a legacy runner (it omitted one
entirely) and any pending numbers.
"""
from swingbot.commands.plans import _partial_tail, _plan_line


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(
            plan_id="p1", ticker="AAPL", status="PARTIAL",
            direction="bullish", strategy="MACD", horizon_key="3m",
            entry_price=100.0, trigger_price=100.0, stop_loss=90.0,
            tp1=120.0, tp2=None, working_stop=113.3333333,
            legs_realized=[{"fraction": 0.5, "exit_price": 121.0, "r": 2.1,
                            "reason": "tp1"}],
            tp1_fraction=0.5, expiry_bars=5, created_at="2026-09-01",
            badge="WEAK", confidence_level=3, quality_score=3,
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_no_tp2_runner_says_trailing_not_a_target():
    tail = _partial_tail(FakePlan())
    assert "trailing" in tail.lower()
    assert "TP2" not in tail


def test_no_tp2_runner_names_tp1_as_banked_history():
    tail = _partial_tail(FakePlan())
    assert "banked" in tail.lower()


def test_legacy_runner_still_shows_a_stop():
    """The old _partial_tail omitted the stop entirely when working_stop
    was unset, so a legacy runner showed no protection at all."""
    tail = _partial_tail(FakePlan(working_stop=None))
    assert "113.33" in tail


def test_tp2_runner_shows_the_real_target():
    tail = _partial_tail(FakePlan(tp2=140.0))
    assert "140.00" in tail


def test_pending_line_shows_distance_and_expiry():
    plan = FakePlan(status="PENDING", entry_price=None, working_stop=None,
                    legs_realized=[])
    line = _plan_line(plan, price=95.0, bars_since_created=2)
    assert "0.5R" in line          # (100 - 95) / 10
    assert "3" in line             # 5 - 2 bars left


def test_pending_line_omits_the_numbers_when_there_is_no_price():
    plan = FakePlan(status="PENDING", entry_price=None, working_stop=None,
                    legs_realized=[])
    line = _plan_line(plan, price=None, bars_since_created=None)
    assert "R away" not in line
    assert "AAPL" in line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/commands/test_plan_board_lines.py -v`
Expected: FAIL — `test_no_tp2_runner_says_trailing_not_a_target`; the current tail renders `TP1 (no TP2) 120.00`.

- [ ] **Step 3: Write minimal implementation**

Replace `_partial_tail` and extend `_plan_line` in `swingbot/commands/plans.py`:

```python
def _partial_tail(plan) -> str:
    """The tail of a PARTIAL plan's board row: what was banked, then the
    runner as a position of its own.

    v73: the levels come from plan_view so this line, the admin row and
    plan_table.partial_position_line cannot disagree again. The no-tp2 case
    now says "trailing" instead of naming tp1 as a target -- tp1 is where
    the banked leg came from, not somewhere the runner is going.
    """
    view = plan_view(plan)
    bits = []
    if view.banked:
        pct, amount = banked_leg_pct_and_amount(
            plan, view.banked.exit_price, view.banked.fraction)
        banked = f"banked {ui.fmt_r(view.banked.r)}"
        if pct is not None:
            banked += f"/{ui.fmt_pct(pct)}"
        if amount is not None:
            banked += f"/{signed_money(amount, config.CURRENCY_SYMBOL)}"
        bits.append(f"{banked} on {view.banked.fraction:.0%}")

    runner = f"runner entry {ui.fmt_price(view.entry)}"
    if view.stop is not None:
        word = "trailing" if view.stop_kind == "trailing" else "floor"
        runner += f" {word} {ui.fmt_price(view.stop)}"
    if view.target is not None:
        runner += f" TP2 {ui.fmt_price(view.target)}"
    bits.append(runner)
    return " · ".join(bits)


def _plan_line(plan, *, price: float | None = None,
               bars_since_created: int | None = None) -> str:
    from swingbot.core.analytics.rank import follow_score
    import datetime as dt

    star = "⭐" if plan.plan_id in starred_ids() else ""
    score = follow_score(plan, today=dt.date.today())
    direction_word = "LONG" if plan.direction == "bullish" else "SHORT"
    if plan.status == "PARTIAL":
        tail = _partial_tail(plan)
    else:
        tp2_bit = f" TP2 {ui.fmt_price(plan.tp2)}" if plan.tp2 is not None else ""
        tail = (f"entry {ui.fmt_price(plan.trigger_price)} SL {ui.fmt_price(plan.stop_loss)} "
                f"TP1 {ui.fmt_price(plan.tp1)}{tp2_bit}")
        if plan.status == "PENDING":
            # v73: a pending plan's two questions -- will it trigger, and
            # when does it die. Omitted rather than faked when unknown.
            view = plan_view(plan, price=price,
                             bars_since_created=bars_since_created)
            if view.distance_to_trigger_r is not None:
                tail += f" · {view.distance_to_trigger_r:.1f}R away"
            if view.bars_to_expiry is not None:
                tail += f" · {view.bars_to_expiry} bars left"
    return (
        f"{star}{ui.direction_glyph(plan.direction)} {plan.ticker} {direction_word} · "
        f"{plan.status} · follow {score:.0f} · {tail}"
    )
```

Add `from swingbot.core.presentation.plan_view import plan_view` to the
imports. `render_board` calls `_plan_line(p)`; leave that call as-is — the two
new parameters are keyword-only with defaults, so the board keeps working and
gains the numbers when a caller has a price to pass.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/commands/test_plan_board_lines.py`
Expected: `0 failed`, 6 passed

Then the module's existing suite:

Run: `python -m pytest tests/commands -k plan -v`
Expected: `0 failed`. If a test asserts the old `TP1 (no TP2)` wording, update
it to the new wording with a comment saying v73 replaced it.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/plans.py tests/commands/test_plan_board_lines.py
git commit -m "feat(v73): Discord plan board renders from the projection"
```

---

### Task B3: The scan/lifecycle embed renders from the projection

**Files:**
- Modify: `swingbot/core/scanning/plan_table.py:142-166` (`partial_position_line`)
- Test: `tests/scanning/test_partial_position_line.py`

**Interfaces:**
- Consumes: `plan_view` from A1.
- Produces: `partial_position_line(plan) -> str`, unchanged signature. Called by `core/scanning/lifecycle_embeds.py:335` and re-exported by `core/scanning/embeds.py:20`.

**Do not** add embed fields with a raw `embed.add_field()` — the caller at
`lifecycle_embeds.py:335` already does its own field wiring and is not being
changed here.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_partial_position_line.py
"""The lifecycle embed's partial line, from the shared projection."""
from swingbot.core.scanning.plan_table import partial_position_line


class FakePlan:
    def __init__(self, **kw):
        defaults = dict(
            status="PARTIAL", direction="bullish", entry_price=100.0,
            trigger_price=100.0, stop_loss=90.0, tp1=120.0, tp2=None,
            working_stop=113.3333333,
            legs_realized=[{"fraction": 0.5, "exit_price": 121.0, "r": 2.1,
                            "reason": "tp1"}],
            tp1_fraction=0.5, expiry_bars=5, created_at="2026-09-01",
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def test_no_tp2_line_names_the_trail_not_a_target():
    line = partial_position_line(FakePlan())
    assert "121.00" in line            # runner entry = the TP1 fill
    assert "113.33" in line            # the trail
    assert "no tp2" not in line.lower()  # v73: no longer names tp1 at all


def test_tp2_line_keeps_the_entry_target_stop_shape():
    line = partial_position_line(FakePlan(tp2=140.0))
    assert "121.00" in line and "140.00" in line and "113.33" in line


def test_legacy_runner_uses_the_floor_not_the_original_stop():
    line = partial_position_line(FakePlan(working_stop=None))
    assert "113.33" in line
    assert "90.00" not in line


def test_bearish_runner_floor_is_below_entry_and_that_is_correct():
    plan = FakePlan(direction="bearish", entry_price=100.0, stop_loss=110.0,
                    tp1=80.0, working_stop=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 79.0,
                                    "r": 2.1, "reason": "tp1"}])
    line = partial_position_line(plan)
    assert "86.67" in line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scanning/test_partial_position_line.py -v`
Expected: FAIL — `test_no_tp2_line_names_the_trail_not_a_target`; the current
line contains `(tp1, no tp2)`.

- [ ] **Step 3: Write minimal implementation**

```python
def partial_position_line(plan) -> str:
    """The runner half of a PARTIAL plan, as a position of its own.

    v73: levels come from plan_view, shared with commands/plans.py and
    admin/api_v1/trades.py. The old "(tp1, no tp2)" note is gone -- naming
    tp1 as a target, however carefully footnoted, described a level the
    runner had already passed through. A runner without tp2 is a trailing
    position and now says so.
    """
    from swingbot.core.presentation.plan_view import plan_view

    view = plan_view(plan)
    if view.target is not None:
        return (f"entry {view.entry:.2f} → target {view.target:.2f} "
                f"/ stop {view.stop:.2f}")
    return f"entry {view.entry:.2f} → trailing stop {view.stop:.2f}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_partial_position_line.py`
Expected: `0 failed`, 4 passed

Run: `python -m pytest tests/scanning -k partial -v`
Expected: `0 failed`. Update any test asserting the old `(tp1, no tp2)` string,
with a comment naming v73 as the reason.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/plan_table.py tests/scanning/test_partial_position_line.py
git commit -m "feat(v73): lifecycle embed partial line renders from the projection"
```

---

### Task B4: The cross-surface guard

**Files:**
- Create: `tests/presentation/test_surface_agreement.py`

**Interfaces:**
- Consumes: `plan_view`, `_row_from_plan`, `_partial_tail`, `partial_position_line`.
- Produces: nothing — this is spec acceptance criterion 5.

One plan, built once, driven through all three surfaces. **This is the test
that keeps the surfaces from drifting apart again**, and it is the reason the
whole spec exists rather than three separate bug fixes.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_surface_agreement.py
"""Spec acceptance criterion 5: one plan, three surfaces, one answer.

Before v73 these three disagreed about a PARTIAL runner's stop and target,
which is how the admin API came to draw a progress bar from the original
risk stop toward an already-banked target. A test that only checked one
surface would have passed throughout.
"""
import pytest

from swingbot.admin.api_v1.trades import _row_from_plan
from swingbot.commands.plans import _partial_tail
from swingbot.core.presentation.plan_view import plan_view
from swingbot.core.scanning.plan_table import partial_position_line

PLAN = {
    "plan_id": "p1", "ticker": "AAPL", "status": "PARTIAL",
    "direction": "bullish", "strategy": "MACD", "horizon_key": "3m",
    "entry_price": 100.0, "trigger_price": 100.0, "stop_loss": 90.0,
    "tp1": 120.0, "tp2": None, "working_stop": None,
    "legs_realized": [{"fraction": 0.5, "exit_price": 121.0, "r": 2.1,
                       "reason": "tp1"}],
    "tp1_fraction": 0.5, "expiry_bars": 5, "created_at": "2026-09-01",
    "badge": "WEAK", "quality_score": 3,
}


class _Attr:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        return self._data.get(name)


@pytest.fixture
def view():
    return plan_view(_Attr(PLAN))


def test_the_projection_is_the_reference(view):
    """runner_floor(100, 120) = 113.33 -- in profit, above entry. The
    original risk stop is 90.00, below it."""
    assert view.entry == 121.0
    assert round(view.stop, 2) == 113.33
    assert view.target is None


def test_the_admin_row_agrees_with_the_projection(view):
    row = _row_from_plan(dict(PLAN), None, set())
    assert row["stop_loss"] == view.stop
    assert row["target"] == view.target
    assert row["banked_exit_price"] == view.entry


def test_the_discord_board_agrees_with_the_projection(view):
    tail = _partial_tail(_Attr(PLAN))
    assert f"{view.entry:.2f}" in tail
    assert f"{view.stop:.2f}" in tail
    assert "TP2" not in tail          # target is None on every surface


def test_the_lifecycle_embed_agrees_with_the_projection(view):
    line = partial_position_line(_Attr(PLAN))
    assert f"{view.entry:.2f}" in line
    assert f"{view.stop:.2f}" in line


def test_no_surface_shows_the_original_risk_stop():
    """The single assertion that would have caught the original bug."""
    row = _row_from_plan(dict(PLAN), None, set())
    tail = _partial_tail(_Attr(PLAN))
    line = partial_position_line(_Attr(PLAN))
    assert row["stop_loss"] != 90.0
    assert "90.00" not in tail
    assert "90.00" not in line


def test_no_surface_shows_tp1_as_a_live_target():
    row = _row_from_plan(dict(PLAN), None, set())
    tail = _partial_tail(_Attr(PLAN))
    line = partial_position_line(_Attr(PLAN))
    assert row["target"] is None
    assert "target 120.00" not in line
    assert "TP2 120.00" not in tail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/presentation/test_surface_agreement.py -v`
Expected: PASS if B1–B3 all landed. If any assertion fails, that surface did
not adopt the projection — fix the surface, **never** this test.

- [ ] **Step 3: No implementation**

This task writes no production code. It is the guard, not a feature.

- [ ] **Step 4: Confirm**

Run: `python scripts/dev/testrun.py file tests/presentation/test_surface_agreement.py`
Expected: `0 failed`, 6 passed

- [ ] **Step 5: Commit**

```bash
git add tests/presentation/test_surface_agreement.py
git commit -m "test(v73): one plan, three surfaces, one answer"
```

---

# Phase C — the SPA and verification

### Task C1: `PlanCell` labels instead of guessing

**Files:**
- Modify: `frontend/src/app/api/models.ts:117-126`, `frontend/src/app/ui/plan-cell.ts:86,121`
- Test: `frontend/src/app/ui/plan-cell.spec.ts`

**Interfaces:**
- Consumes: the row keys B1 produces — `target_is_banked_tp1`, `stop_kind`, `bar_kind`, `floor_r`, `price_r`, `headroom_r`, `distance_to_trigger_r`, `bars_to_expiry`.
- Produces: `PlanCell` inputs `stopKind`, `targetIsBankedTp1`, `floorR`, `priceR`, `headroomR`, replacing the `trailing` boolean.

`plan-cell.ts:121` already renders `'Trailing stop'` vs `'Stop'` off a boolean.
`stop_kind` is that boolean with a third state, so this is an extension of an
existing decision rather than a new one.

- [ ] **Step 1: Write the failing test**

First **update the existing trailing-stop test** at
`plan-cell.spec.ts:98-110`, which currently drives the boolean. Change its one
input line and add a note:

```typescript
    // v73: `trailing` became `stopKind` -- the boolean could not express
    // the legacy derived-floor case, where a plan predating working_stop
    // falls back to runner_floor().
    f.componentRef.setInput('stopKind', 'trailing');
```

Its expected tooltip is unchanged: `'Entry 71.64 · Target — · Trailing stop 69.85'`.
The `says plain "Stop" when not trailing (the default)` test at `:112` needs no
change — `stopKind` defaults to `'risk'`, which still renders `Stop`.

Then append the new cases, in the same style as the file (no new helpers —
this spec builds components with `TestBed.createComponent` directly):

```typescript
// append to frontend/src/app/ui/plan-cell.spec.ts
  /* -- v73: stop provenance and the runner with no target ---------------- */

  it('says "Locked-in floor" for a derived_floor stop', () => {
    // A legacy runner with no working_stop, standing on runner_floor().
    // It is protection in PROFIT, not the original risk stop, and calling
    // it plain "Stop" reads as the latter.
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', 140.0);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'derived_floor');
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toBe('Entry 121.00 · Target 140.00 · Locked-in floor 113.33');
  });

  it('reports the trail instead of "Target —" when TP1 is banked', () => {
    // The v73 case: no TP2, so there is no destination to name. Before
    // this, the tooltip said "Target —" and the row's bar was drawn
    // toward the already-banked TP1.
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('targetIsBankedTp1', true);
    f.componentRef.setInput('floorR', 1.33);
    f.componentRef.setInput('priceR', 2.5);
    f.componentRef.setInput('headroomR', 1.17);
    f.detectChanges();
    const tip = f.nativeElement.querySelector('[title]').getAttribute('title');
    expect(tip).toBe(
      'Entry 121.00 · TP1 banked · floor 1.3R · price 2.5R · headroom 1.2R'
      + ' · Trailing stop 113.33');
    expect(tip).not.toContain('Target —');
  });

  it('shows an em dash for an R value it does not have', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('targetIsBankedTp1', true);
    f.componentRef.setInput('floorR', 1.33);
    f.detectChanges();
    expect(f.nativeElement.querySelector('[title]').getAttribute('title'))
      .toContain('floor 1.3R · price — · headroom —');
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/plan-cell.spec.ts`
Expected: FAIL — `stopKind` is not an input on `PlanCell`.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/app/api/models.ts`, add to the open-position interface
alongside the existing SR7 status-bar block:

```typescript
  /* v73 — provenance, so the cell labels rather than guesses. `target` is
     null for a runner whose TP1 is banked and which has no TP2: it has no
     destination, only a trail. */
  target_is_banked_tp1: boolean;
  stop_kind: 'risk' | 'trailing' | 'derived_floor';
  bar_kind: 'progress' | 'approach' | 'trailing' | 'none';
  floor_r: number | null;
  price_r: number | null;
  headroom_r: number | null;
  distance_to_trigger_r: number | null;
  bars_to_expiry: number | null;
```

In `frontend/src/app/ui/plan-cell.ts`, replace the `trailing` input at line 86:

```typescript
  /**
   * How to name `stop`. 'risk' is the original stop; 'trailing' is the
   * runner's working_stop; 'derived_floor' is runner_floor() standing in
   * for a legacy plan that predates working_stop. The last two sit in
   * PROFIT, which for a short means below entry -- that reads as backwards
   * unless the label says what it is.
   */
  readonly stopKind = input<'risk' | 'trailing' | 'derived_floor'>('risk');

  /** True when TP1 is banked and there is no TP2 -- the position has a
   *  trail, not a target, and `target` is null. */
  readonly targetIsBankedTp1 = input<boolean>(false);
  /** R of the locked-in floor, the live price, and the gap between them. */
  readonly floorR = input<number | null>(null);
  readonly priceR = input<number | null>(null);
  readonly headroomR = input<number | null>(null);
```

and replace the tooltip's stop/target composition at line 121:

```typescript
    const stopWord = { risk: 'Stop', trailing: 'Trailing stop',
                       derived_floor: 'Locked-in floor' }[this.stopKind()];
    const targetPart = this.targetIsBankedTp1()
      ? `TP1 banked · floor ${r(this.floorR())} · price ${r(this.priceR())} · headroom ${r(this.headroomR())}`
      : `Target ${this.fmt(this.target())}`;
    let out = `${lead} · ${targetPart} · ${stopWord} ${this.fmt(this.stop())}`;
```

Add the R formatter beside the existing `pct` helper in the same file:

```typescript
const r = (value: number | null): string =>
  value === null ? '—' : `${value.toFixed(1)}R`;
```

Then grep for any remaining consumer of the renamed input — the cell is used
by the trades table and the trade-detail view, and both pass it today:

```bash
grep -rn "trailing" frontend/src/app --include=*.ts --include=*.html
```

Every `[trailing]="…"` binding and `setInput('trailing', …)` call becomes
`stopKind`, taking its value from the row's `stop_kind` rather than a derived
boolean. A binding left behind is a silent no-op — Angular ignores an unknown
input on a signal-input component, so the cell would quietly render `Stop` for
every trailing runner.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/plan-cell.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/plan-cell.spec.ts
git commit -m "feat(v73): PlanCell labels stop provenance and the banked-TP1 runner"
```

---

### Task C2: Lock the null-sort behaviour

**Files:**
- Create: `tests/admin/test_trades_null_sort.py`

**Interfaces:**
- Consumes: `_sorted_rows` from `swingbot/admin/api_v1/trades.py:583`.
- Produces: nothing — a regression test.

**This is a verification task, not a change.** The spec anticipated needing a
null-ordering fix, but `_sorted_rows:593-594` already partitions
`present`/`missing` and appends missing last regardless of direction. Nothing
to fix — but `target` becoming null for every no-TP2 runner makes that
behaviour newly load-bearing, so it gets a test that fails if anyone
"simplifies" the partition away.

- [ ] **Step 1: Write the failing test**

```python
# tests/admin/test_trades_null_sort.py
"""v73 made `target` null for every no-TP2 runner -- the common case.

_sorted_rows already put nulls last in both directions; this locks that in
before a future refactor collapses the present/missing partition into a
plain sorted(key=...), which would float every trailing runner to the top
of a descending sort.
"""
from swingbot.admin.api_v1.trades import _sorted_rows


def rows():
    return [{"id": "a", "target": 140.0}, {"id": "b", "target": None},
            {"id": "c", "target": 120.0}]


def test_nulls_sort_last_ascending():
    assert [r["id"] for r in _sorted_rows(rows(), "target", False)] == \
        ["c", "a", "b"]


def test_nulls_sort_last_descending_too():
    """Not merely reversed -- the null stays at the bottom both ways."""
    assert [r["id"] for r in _sorted_rows(rows(), "target", True)] == \
        ["a", "c", "b"]


def test_all_null_column_does_not_raise():
    only_nulls = [{"id": "a", "target": None}, {"id": "b", "target": None}]
    assert len(_sorted_rows(only_nulls, "target", True)) == 2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/admin/test_trades_null_sort.py -v`
Expected: PASS, 3 passed — **immediately**, with no production change. If any
of these fails, the spec's assumption was wrong and `_sorted_rows` does need
the fix; implement it there and say so in the commit message.

- [ ] **Step 3: No implementation**

- [ ] **Step 4: Confirm**

Run: `python scripts/dev/testrun.py file tests/admin/test_trades_null_sort.py`
Expected: `0 failed`

- [ ] **Step 5: Commit**

```bash
git add tests/admin/test_trades_null_sort.py
git commit -m "test(v73): lock nulls-last sorting now that target can be null"
```

---

### Task C3: Full verification

**Files:** none — this task runs the plan's one full verification of each suite.

- [ ] **Step 1: Run the Python suite once**

Dispatch the `test-runner` subagent, or run:

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed`. A *changed* pass count is not a failure —
this plan adds roughly 45 tests.

- [ ] **Step 2: Run the frontend suite once**

```bash
cd frontend && npm test
```

Expected: green.

- [ ] **Step 3: Fix forward from any failure**

These are this plan's regressions. The likely candidates and what each means:

- Anything asserting the string `(tp1, no tp2)` or `TP1 (no TP2)` — B2/B3
  replaced that wording; update the assertion, don't restore the wording.
- Anything reading `row["target"]` on a PARTIAL fixture — it is `None` now by
  design; the test should assert that.
- `plan-cell.spec.ts` cases still calling `setInput('trailing', …)` — C1
  renamed the input.
- A test asserting the old `plan.stop_loss` fallback — that fallback was the
  bug. Update it to `runner_floor` and note v73 in a comment.

- [ ] **Step 4: Syntax pass**

```bash
python -m py_compile bot.py admin_ui.py swingbot/core/presentation/plan_view.py swingbot/admin/api_v1/trades.py swingbot/commands/plans.py swingbot/core/scanning/plan_table.py
```

Expected: no output.

- [ ] **Step 5: Confirm nothing outside presentation moved**

```bash
git diff main --stat -- swingbot/core/planning/plan_manager.py swingbot/core/planning/exit_sim.py swingbot/core/planning/lifecycle.py swingbot/config.py
```

Expected: **empty.** This plan is presentation-only. If any of those moved, a
task overstepped the global constraints — the exit engine is untouched, and
the RTH/extended divergence the spec documents is deliberately left for its own
spec.

- [ ] **Step 6: Commit and close out**

```bash
git add -A
git commit -m "chore(v73): full-suite verification"
```

Then close the plan out per `docs/claude/document-lifecycle.md`: move the spec
and all three plan parts to `implemented/`, and bump `VERSION.json` — `ui` to
1.12.0 and `bot` to 1.6.2, two independent release commits per
`docs/claude/working-conventions.md` — **and regenerate `version_history.json`
in the same commit**, since the local gate runs before the bump and
structurally cannot catch a missed regeneration.
