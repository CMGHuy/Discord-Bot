# v81 — Execution Feed, part 1: foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-09-10-v81-execution-feed_0-index.md` — its Global Constraints
apply to every task here.

---

### Task F1: Plan delivery ledger, `breakeven_trigger`, `TRAIL_NOTIFY_MIN_R`

**Files:**
- Modify: `swingbot/core/planning/plan_types.py:79-86` (two fields after
  `runner_floor_session`; one function after `effective_stop`)
- Modify: `swingbot/config.py:565-569` (one Field after `EXTENDED_HOURS_DEBOUNCE_TICKS`)
- Create: `tests/planning/test_plan_feed_ledger.py`
- Modify: `tests/test_config_flags.py` (append one test)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `TradePlanV2.notified_stop: float | None = None` — the stop last delivered
    to the reader; `None` reads as `stop_loss`.
  - `TradePlanV2.pending_notice: dict | None = None` — shape
    `{"transition": str, "detail": dict, "at": str}`, `at` ISO-8601 with offset.
  - `swingbot.core.planning.plan_types.breakeven_trigger(plan, entry: float) -> float`
  - `config.TRAIL_NOTIFY_MIN_R: float`, default `0.25`

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_feed_ledger.py`:

```python
"""v81: the execution feed's delivery ledger on TradePlanV2, and the one
break-even formula the manager and the order ticket share."""
from swingbot.core.planning.plan_types import (breakeven_trigger, plan_from_dict,
                                               plan_to_dict)
from tests.planning.test_plan_engine_model import _plan


def test_a_new_plan_owes_the_reader_nothing():
    plan = _plan()
    assert plan.notified_stop is None
    assert plan.pending_notice is None


def test_a_row_persisted_before_v81_loads_with_an_empty_ledger():
    row = plan_to_dict(_plan())
    del row["notified_stop"], row["pending_notice"]
    plan = plan_from_dict(row)
    assert plan.notified_stop is None
    assert plan.pending_notice is None


def test_the_ledger_round_trips_through_the_persisted_dict():
    plan = _plan(notified_stop=101.5, pending_notice={
        "transition": "closed",
        "detail": {"reason": "loss", "exit_price": 94.5, "session": "regular"},
        "at": "2026-09-10T15:00:00+00:00",
    })
    assert plan_from_dict(plan_to_dict(plan)) == plan


def test_breakeven_trigger_is_the_fraction_of_the_way_to_tp1():
    plan = _plan(direction="bullish", tp1=110.0, breakeven_trigger_fraction=0.5)
    assert breakeven_trigger(plan, 100.0) == 105.0


def test_breakeven_trigger_mirrors_for_a_short():
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0,
                 breakeven_trigger_fraction=0.5)
    assert breakeven_trigger(plan, 100.0) == 95.0
```

Append to `tests/test_config_flags.py`:

```python
def test_v81_trail_notify_min_r_field_exists_with_documented_default():
    """v81: the execution feed pings MOVE STOP once the resting stop has moved
    this many R from the stop last delivered."""
    by_key = {f.key: f for f in config.FIELDS}
    field = by_key["TRAIL_NOTIFY_MIN_R"]

    assert field.default == "0.25"
    assert field.type == "float"
    assert (field.min, field.max) == (0.01, 1.0)
    assert field.section == "Plan Engine v2"
    assert isinstance(config.TRAIL_NOTIFY_MIN_R, float)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_feed_ledger.py`
Expected: FAIL — `ImportError: cannot import name 'breakeven_trigger'`.

Run: `python scripts/dev/testrun.py file tests/test_config_flags.py`
Expected: FAIL — `KeyError: 'TRAIL_NOTIFY_MIN_R'`.

- [ ] **Step 3: Add the fields and the helper**

In `swingbot/core/planning/plan_types.py`, after the line
`    runner_floor_session: str | None = None` (the last field of `TradePlanV2`), add:

```python
    # v81 execution feed: what the reader has actually been TOLD. Written only
    # by plan_manager (poll's feed bookkeeping and ack_notified) and read by no
    # exit path -- tests/planning/test_plan_manager_feed.py pins that.
    # notified_stop: the stop last delivered; None reads as stop_loss, which
    # the alert's order ticket delivered. pending_notice: the latest FILLED /
    # CANCEL / EXIT instruction not yet delivered, as {"transition", "detail",
    # "at"}; None when nothing is owed, including every plan persisted before
    # v81, which is therefore never resent.
    notified_stop: float | None = None
    pending_notice: dict | None = None
```

After `effective_stop`, add:

```python
def breakeven_trigger(plan: TradePlanV2, entry: float) -> float:
    """The price at which break-even arms: breakeven_trigger_fraction of the
    way from `entry` to tp1. plan_manager._step_active and the v81 order
    ticket both read this one formula."""
    sign = 1 if plan.direction == "bullish" else -1
    return entry + sign * plan.breakeven_trigger_fraction * abs(plan.tp1 - entry)
```

- [ ] **Step 4: Add the config Field**

In `swingbot/config.py`, directly after the `EXTENDED_HOURS_DEBOUNCE_TICKS`
Field (it ends `...a liquid market never would have."),`), add:

```python
    Field("TRAIL_NOTIFY_MIN_R", "TRAIL_NOTIFY_MIN_R", "Plan Engine v2",
          "Stop-move ping threshold (R)", type="float", default="0.25",
          min=0.01, max=1.0, step=0.05,
          help="The execution feed (simple-alerts channel) sends MOVE STOP once a plan's "
               "resting stop has moved at least this many R -- of the plan's initial risk -- "
               "from the stop last delivered. Values outside 0.01-1 are clamped: break-even "
               "is a 1R move, so a threshold above 1 would stop a failed break-even ping "
               "from ever being re-sent."),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_feed_ledger.py`
Expected: PASS (5 tests).

Run: `python scripts/dev/testrun.py file tests/test_config_flags.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_types.py swingbot/config.py tests/planning/test_plan_feed_ledger.py tests/test_config_flags.py
git commit -m "feat(v81): plan delivery ledger, breakeven_trigger and TRAIL_NOTIFY_MIN_R"
```

---

### Task F2: `instructions.py` — the execution feed as pure data

**Files:**
- Create: `swingbot/core/presentation/instructions.py`
- Create: `tests/presentation/test_instructions.py`

Do **not** add the module to `swingbot/core/presentation/__init__.py`: it
imports `swingbot.core.planning`, and the package `__init__` is imported by
modules that `planning` itself imports.

**Interfaces:**
- Consumes: `plan_types.breakeven_trigger` (F1); existing `plan_view.plan_view`,
  `exit_sim.runner_floor`, `tokens.fmt_price`, `tokens.fmt_r`, `tokens.ABSENT`.
- Produces (all in `swingbot.core.presentation.instructions`):
  - Verb constants `PLACE`, `DO_NOT_PLACE`, `FILLED`, `MOVE_STOP`, `CANCEL`,
    `EXITED`, `CLOSE_AT_MARKET`.
  - `Instruction` — frozen dataclass: `verb: str`, `ticker: str`,
    `direction: str`, `headline: str`, `lines: tuple[str, ...] = ()`,
    `warnings: tuple[str, ...] = ()`, `tone: str = "neutral"` (`"level"`,
    `"good"`, `"bad"`, `"neutral"`, `"inert"`), `level: int | None = None`,
    `plan_id: str | None = None`.
  - `ticket_for(plan, *, logged: bool, not_logged_reason: str | None, sizing: dict | None, currency: str = "", warnings: tuple[str, ...] = (), level: int | None = None) -> Instruction`
  - `instruction_for(plan, event, *, sizing: dict | None = None) -> Instruction`
    — handles `filled`, `be_moved`, `tp1_partial`, `stop_moved`,
    `cancelled_expired`, `cancelled_invalidated`, `closed`; raises `ValueError`
    for anything else.
  - `block_warnings(*, heat: dict | None, cluster: dict | None, kill: dict | None) -> tuple[str, ...]`
  - `approx_last_trigger_session(created_at: str, expiry_bars: int) -> datetime.date`
  - `signed_r(x: float) -> str`, `total_r(plan, exit_price: float | None) -> float`
- Event `detail` keys it reads (F3 stamps the ones marked ★): `filled` —
  `entry_price`; `be_moved` — `working_stop`; `tp1_partial` — `fraction`,
  `exit_price`, `r`, `working_stop`★; `stop_moved`★ — `old`, `new`, `r_moved`,
  `effective` (`"now"`/`"next_session"`); `closed` — `reason`, `exit_price`,
  `session`★, `notified_stop`★, `bot_stop`★.

- [ ] **Step 1: Write the failing tests**

Create `tests/presentation/test_instructions.py`:

```python
"""v81: the execution feed's instructions, as pure data. Every string a reader
places an order from is pinned here."""
import datetime as dt

import pytest

from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from tests.planning.test_plan_engine_model import _plan

SIZING = {"shares": 2439.02, "risk_amount": 10000.0}


def _long_pending(**kw):
    base = dict(entry_type="stop_entry", direction="bullish", trigger_price=102.5,
                entry_price=None, stop_loss=98.4, tp1=106.0, tp1_fraction=0.5,
                tp2=110.0, trail_atr_mult=3.0, breakeven_trigger_fraction=0.5,
                created_at="2026-09-10", expiry_bars=5, status="PENDING")
    base.update(kw)
    return _plan(**base)


def _short_pending(**kw):
    base = dict(entry_type="stop_entry", direction="bearish", trigger_price=97.5,
                entry_price=None, stop_loss=101.6, tp1=94.0, tp1_fraction=0.5,
                tp2=None, trail_atr_mult=2.5, breakeven_trigger_fraction=0.5,
                created_at="2026-09-11", expiry_bars=3, status="PENDING")
    base.update(kw)
    return _plan(**base)


def _event(transition, **detail):
    return PlanEvent("p1", transition, detail)


# --- the order ticket --------------------------------------------------------

def test_a_long_stop_entry_ticket_is_a_complete_bracket():
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       sizing=SIZING, currency="$", level=5)
    assert (t.verb, t.tone, t.level, t.ticker, t.plan_id) == (ins.PLACE, "level", 5, "AAPL", "p1")
    assert t.headline == "BUY STOP 102.50 · 2,439 sh (risk $10,000)"
    assert t.lines == (
        "SELL STOP 98.40",
        "TP1 SELL LIMIT 106.00 · 1,219 sh (50%)",
        "RUNNER 1,220 sh → TP2 110.00 / trail 3×ATR — stop moves are pinged here",
        "Stop → entry once price reaches 104.25",
        "Cancel if: not triggered by the close of ≈ Thu 17 Sep (5 sessions), "
        "or price reaches 98.40 first",
    )
    assert t.warnings == ()


def test_a_short_ticket_swaps_every_side_and_survives_missing_sizing():
    t = ins.ticket_for(_short_pending(), logged=True, not_logged_reason=None,
                       sizing=None, level=4)
    assert t.headline == "SELL STOP 97.50 · size n/a"
    assert t.lines == (
        "BUY STOP 101.60",
        "TP1 BUY LIMIT 94.00 · 50%",
        "RUNNER 50% → trail 2.5×ATR — stop moves are pinged here",
        "Stop → entry once price reaches 95.75",
        "Cancel if: not triggered by the close of ≈ Wed 16 Sep (3 sessions), "
        "or price reaches 101.60 first",
    )


def test_a_market_entry_ticket_has_no_cancel_clause():
    t = ins.ticket_for(_long_pending(entry_type="market", trigger_price=100.0,
                                     stop_loss=95.0, tp1=110.0),
                       logged=True, not_logged_reason=None, sizing=None)
    assert t.headline == "BUY AT MARKET ~100.00 · size n/a"
    assert not any(line.startswith("Cancel if") for line in t.lines)


def test_a_short_market_entry_says_sell_short():
    t = ins.ticket_for(_short_pending(entry_type="market"), logged=True,
                       not_logged_reason=None, sizing=None)
    assert t.headline.startswith("SELL SHORT AT MARKET ~97.50")


def test_an_unlogged_alert_says_do_not_place_and_why():
    t = ins.ticket_for(_long_pending(), logged=False, not_logged_reason="already open",
                       sizing=SIZING, currency="$")
    assert (t.verb, t.tone) == (ins.DO_NOT_PLACE, "inert")
    assert t.headline == "DO NOT PLACE — already open"
    assert t.lines == ("levels: entry 102.50 · stop 98.40 · TP1 106.00",)


def test_cap_blocks_keep_place_and_are_named_above_the_orders():
    warnings = ins.block_warnings(
        heat={"allowed": False, "open_heat": 6.2, "cap": 6.0},
        cluster={"allowed": False, "cluster": ["AMD", "NVDA"],
                 "correlated_heat": 4.1, "cap": 3.0},
        kill={"on": True, "reason": "3 consecutive losses"},
    )
    assert warnings == (
        "⚠ over portfolio heat cap — open 6.2% / cap 6.0%; the bot tracks this at full size",
        "⚠ over correlated-cluster cap — AMD, NVDA at 4.1% / cap 3.0%; "
        "the bot tracks this at full size",
        "⚠ kill switch on (3 consecutive losses) — the bot tracks this at full size",
    )
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       sizing=SIZING, warnings=warnings)
    assert t.verb == ins.PLACE
    assert t.warnings == warnings


def test_no_blocks_means_no_warnings():
    assert ins.block_warnings(heat=None, cluster=None, kill=None) == ()


@pytest.mark.parametrize("created_at,bars,expected", [
    ("2026-09-10", 5, dt.date(2026, 9, 17)),            # Thursday + 5 weekdays
    ("2026-09-11", 1, dt.date(2026, 9, 14)),            # Friday -> Monday
    ("2026-09-12T14:00:00", 1, dt.date(2026, 9, 14)),   # a Saturday stamp still counts weekdays
])
def test_approx_last_trigger_session_counts_weekdays(created_at, bars, expected):
    assert ins.approx_last_trigger_session(created_at, bars) == expected


@pytest.mark.parametrize("value,expected", [(0.8, "+0.8R"), (-1.1, "−1.1R"), (0.0, "0.0R")])
def test_signed_r(value, expected):
    assert ins.signed_r(value) == expected


# --- lifecycle instructions --------------------------------------------------

def test_filled():
    plan = _long_pending(status="ACTIVE", entry_price=102.61)
    i = ins.instruction_for(plan, _event("filled", entry_price=102.61))
    assert (i.verb, i.headline) == (ins.FILLED, "FILLED @ 102.61 (bot)")
    assert i.lines == (
        "Confirm your broker filled; the bot's R is measured from 102.61",
        "Resting: SELL STOP 98.40 · TP1 SELL LIMIT 106.00",
    )


def test_break_even_waits_for_the_close():
    plan = _long_pending(status="ACTIVE", entry_price=102.61, working_stop=102.61)
    i = ins.instruction_for(plan, _event("be_moved", working_stop=102.61))
    assert (i.verb, i.headline) == (ins.MOVE_STOP, "MOVE STOP → 102.61 after today's close")
    assert i.lines == ("break-even; keep 98.40 until then",)


def test_tp1_partial_names_the_filled_shares_and_the_runner_stop():
    plan = _long_pending(status="PARTIAL", entry_price=102.61, working_stop=104.87)
    i = ins.instruction_for(plan, _event("tp1_partial", fraction=0.5, exit_price=106.0,
                                         r=0.8052, working_stop=104.87), sizing=SIZING)
    assert (i.verb, i.tone) == (ins.MOVE_STOP, "good")
    assert i.headline == "TP1 FILLED 1,219 sh @ 106.00 (+0.8R)"
    assert i.lines == ("MOVE STOP on the runner → 104.87 now (runner floor)",)


def test_a_trail_move():
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=106.67, new=115.0,
                                         r_moved=1.666, effective="now"))
    assert i.headline == "MOVE STOP → 115.00 now"
    assert i.lines == ("trail; +1.7R since the last ping",)


def test_a_resent_runner_floor_is_labelled_as_the_floor():
    floor = runner_floor(100.0, 110.0)
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=floor)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=floor,
                                         r_moved=2.333, effective="now"))
    assert i.headline == "MOVE STOP → 106.67 now"
    assert i.lines == ("runner floor; +2.3R since the last ping",)


def test_a_resent_break_even_keeps_its_next_session_timing():
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=100.0,
                                         r_moved=1.0, effective="next_session"))
    assert i.headline == "MOVE STOP → 100.00 after today's close"
    assert i.lines == ("break-even; +1.0R since the last ping",)


def test_cancellations_name_the_order_to_cancel():
    expired = ins.instruction_for(_long_pending(), _event("cancelled_expired", bars_waited=6))
    assert (expired.verb, expired.tone) == (ins.CANCEL, "inert")
    assert expired.headline == "CANCEL BUY STOP 102.50"
    assert expired.lines == ("not triggered within 5 sessions",)

    invalidated = ins.instruction_for(_short_pending(),
                                      _event("cancelled_invalidated", live_price=101.7))
    assert invalidated.headline == "CANCEL SELL STOP 97.50"
    assert invalidated.lines == ("price reached the stop 101.60 before triggering",)


def test_a_regular_session_stop_out():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=94.5,
                                         session="regular", notified_stop=95.0,
                                         bot_stop=95.0))
    assert (i.verb, i.tone) == (ins.EXITED, "bad")
    assert i.headline == "EXITED @ 94.50 — stop · −1.1R total"
    assert i.lines == ("If your broker order did not fill: SELL AT MARKET",)


def test_an_extended_hours_exit_says_close_at_market():
    plan = _plan(direction="bearish", status="CLOSED", entry_price=100.0,
                 stop_loss=105.0, tp1=90.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=105.5,
                                         session="extended", notified_stop=105.0,
                                         bot_stop=105.0))
    assert (i.verb, i.headline) == (ins.CLOSE_AT_MARKET, "CLOSE AT MARKET now")
    assert i.lines == (
        "BUY TO COVER AT MARKET: the bot exited on an extended-hours print @ 105.50; "
        "resting stop orders do not fire outside regular hours",
        "−1.1R total",
    )


def test_a_trail_exit_warns_when_the_readers_stop_lagged():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 115.0, "r": 3.0,
                                 "reason": "tp1_runner_trail"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_trail", exit_price=115.0,
                                         session="regular", notified_stop=113.9,
                                         bot_stop=115.0))
    assert (i.verb, i.tone) == (ins.EXITED, "good")
    assert i.headline == "EXITED @ 115.00 — trail · +2.5R total"
    assert i.lines == (
        "If your broker order did not fill: SELL AT MARKET",
        "your last pinged stop was 113.90 — that order may still be open",
    )


def test_an_unknown_transition_is_refused():
    with pytest.raises(ValueError):
        ins.instruction_for(_long_pending(), _event("pyramid_add"))
```

The `−` in `"−1.1R"` is U+2212, the character `tokens.fmt_r` renders.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_instructions.py`
Expected: FAIL — `ImportError: cannot import name 'instructions'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/presentation/instructions.py`:

```python
"""v81: the execution feed's broker instructions, as pure data.

Every message the simple-alerts channel sends -- an alert's order ticket and
each plan lifecycle event -- is projected here into the verb and the order
lines a reader places at a broker. No discord import, no I/O, no clock:
sizing, block annotations and every live stop arrive as arguments or in the
event's detail, which plan_manager stamps. core/scanning/execution_embeds.py
is the only thing that turns an Instruction into a Discord embed.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_types import breakeven_trigger
from swingbot.core.presentation import tokens
from swingbot.core.presentation.plan_view import plan_view

PLACE = "PLACE"
DO_NOT_PLACE = "DO NOT PLACE"
FILLED = "FILLED"
MOVE_STOP = "MOVE STOP"
CANCEL = "CANCEL"
EXITED = "EXITED"
CLOSE_AT_MARKET = "CLOSE AT MARKET"

#: plan_manager close reasons, in the words a reader recognises.
_EXIT_WORDS = {
    "loss": "stop",
    "scratch": "break-even",
    "win": "target",
    "tp1_runner_be": "runner floor",
    "tp1_runner_trail": "trail",
    "tp1_runner_tp2": "TP2",
}


@dataclass(frozen=True)
class Instruction:
    """One execution-feed message.

    ``headline`` is the bold action line; ``warnings`` render above it and
    ``lines`` below. ``tone`` picks the accent: ``"level"`` (the confidence
    ramp, order tickets only), ``"good"``, ``"bad"``, ``"neutral"`` or
    ``"inert"``."""

    verb: str
    ticker: str
    direction: str
    headline: str
    lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    tone: str = "neutral"
    level: int | None = None
    plan_id: str | None = None


def _sides(direction: str) -> dict[str, str]:
    if direction == "bullish":
        return {"entry_stop": "BUY STOP", "entry_market": "BUY AT MARKET",
                "stop": "SELL STOP", "limit": "SELL LIMIT", "exit": "SELL AT MARKET"}
    return {"entry_stop": "SELL STOP", "entry_market": "SELL SHORT AT MARKET",
            "stop": "BUY STOP", "limit": "BUY LIMIT", "exit": "BUY TO COVER AT MARKET"}


def _price(x: float | None) -> str:
    return tokens.fmt_price(x)


def _whole_shares(sizing: dict | None) -> int | None:
    """compute_position_size returns fractional shares (2dp); a broker order
    is whole shares, so the ticket rounds down. None when unsized."""
    if not sizing or not sizing.get("shares"):
        return None
    return math.floor(sizing["shares"]) or None


def signed_r(x: float) -> str:
    """``+0.8R`` / ``−1.1R`` / ``0.0R`` -- the feed signs every non-zero R."""
    text = tokens.fmt_r(x)
    return text if x < 0 or text == "0.0R" else f"+{text}"


def approx_last_trigger_session(created_at: str, expiry_bars: int) -> dt.date:
    """The last session a pending plan can still trigger in: ``created_at``
    plus ``expiry_bars`` weekdays (lifecycle.pending_expired is strictly
    greater-than; plan_manager._bars_since counts rows dated after
    created_at). Approximate by construction -- there is no holiday calendar
    in this repo, and every holiday moves the real date one session later."""
    day = dt.date.fromisoformat(created_at[:10])
    added = 0
    while added < expiry_bars:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day


def block_warnings(*, heat: dict | None, cluster: dict | None,
                   kill: dict | None) -> tuple[str, ...]:
    """Heat, cluster and kill-switch blocks only label an alert: scan_run sets
    them after the paper trade is logged at full size, so the ticket still
    says PLACE and names each block above the orders (v81 D1)."""
    warnings = []
    if heat is not None:
        warnings.append(f"⚠ over portfolio heat cap — open {heat['open_heat']}% / "
                        f"cap {heat['cap']}%; the bot tracks this at full size")
    if cluster is not None:
        names = ", ".join(cluster.get("cluster", [])) or tokens.ABSENT
        warnings.append(f"⚠ over correlated-cluster cap — {names} at "
                        f"{cluster['correlated_heat']}% / cap {cluster['cap']}%; "
                        "the bot tracks this at full size")
    if kill is not None:
        warnings.append(f"⚠ kill switch on ({kill.get('reason')}) — "
                        "the bot tracks this at full size")
    return tuple(warnings)


def ticket_for(plan, *, logged: bool, not_logged_reason: str | None,
               sizing: dict | None, currency: str = "",
               warnings: tuple[str, ...] = (), level: int | None = None) -> Instruction:
    """The order ticket for a new alert (v81 D1, D2, D4). ``logged`` is
    scan_run's own paper-trade decision; the verb mirrors it."""
    side = _sides(plan.direction)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    common = dict(ticker=plan.ticker, direction=plan.direction,
                  plan_id=plan.plan_id, level=level)
    if not logged:
        reason = not_logged_reason or "the bot is not tracking this setup"
        return Instruction(
            verb=DO_NOT_PLACE, headline=f"{DO_NOT_PLACE} — {reason}",
            lines=(f"levels: entry {_price(entry)} · stop {_price(plan.stop_loss)} · "
                   f"TP1 {_price(plan.tp1)}",),
            tone="inert", **common)

    whole = _whole_shares(sizing)
    if whole is None:
        size = "size n/a"
        tp1_qty = f"{plan.tp1_fraction:.0%}"
        runner_qty = f"{1 - plan.tp1_fraction:.0%}"
    else:
        tp1_shares = math.floor(whole * plan.tp1_fraction)
        size = f"{whole:,} sh (risk {currency}{sizing['risk_amount']:,.0f})"
        tp1_qty = f"{tp1_shares:,} sh ({plan.tp1_fraction:.0%})"
        runner_qty = f"{whole - tp1_shares:,} sh"

    if plan.entry_type == "stop_entry":
        headline = f"{side['entry_stop']} {_price(plan.trigger_price)} · {size}"
    else:
        headline = f"{side['entry_market']} ~{_price(plan.trigger_price)} · {size}"
    trail = f"trail {plan.trail_atr_mult:g}×ATR"
    runner_to = f"TP2 {_price(plan.tp2)} / {trail}" if plan.tp2 is not None else trail
    lines = [
        f"{side['stop']} {_price(plan.stop_loss)}",
        f"TP1 {side['limit']} {_price(plan.tp1)} · {tp1_qty}",
        f"RUNNER {runner_qty} → {runner_to} — stop moves are pinged here",
        f"Stop → entry once price reaches {_price(breakeven_trigger(plan, entry))}",
    ]
    if plan.entry_type == "stop_entry":
        sessions = plan_view(plan, bars_since_created=0).bars_to_expiry
        if sessions is None:
            sessions = plan.expiry_bars
        last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
        lines.append(f"Cancel if: not triggered by the close of ≈ {last:%a %d %b} "
                     f"({sessions} sessions), or price reaches "
                     f"{_price(plan.stop_loss)} first")
    return Instruction(verb=PLACE, headline=headline, lines=tuple(lines),
                       warnings=tuple(warnings), tone="level", **common)


def total_r(plan, exit_price: float | None) -> float:
    """Fraction-weighted R over ``legs_realized``, or the single position's R
    for a close that realized no leg: a pre-TP1 stop or scratch and a v70
    extended-hours exit append nothing to the plan (plan_manager._on_event
    synthesizes that leg for the trade log only)."""
    if plan.legs_realized:
        return sum(leg["fraction"] * leg["r"] for leg in plan.legs_realized)
    if plan.entry_price is None or exit_price is None:
        return 0.0
    risk = abs(plan.entry_price - plan.stop_loss)
    if not risk:
        return 0.0
    sign = 1 if plan.direction == "bullish" else -1
    return (exit_price - plan.entry_price) * sign / risk


def _stop_kind(plan, new_stop: float) -> str:
    if plan.status != "PARTIAL":
        return "break-even"
    floor = runner_floor(plan.entry_price, plan.tp1)
    return "runner floor" if math.isclose(new_stop, floor, abs_tol=1e-6) else "trail"


def _closed(plan, detail: dict, side: dict, common: dict) -> Instruction:
    exit_price = detail.get("exit_price")
    r = total_r(plan, exit_price)
    tone = "good" if r > 0.05 else "bad" if r < -0.05 else "neutral"
    if detail.get("session") == "extended":
        verb, headline = CLOSE_AT_MARKET, "CLOSE AT MARKET now"
        lines = [f"{side['exit']}: the bot exited on an extended-hours print @ "
                 f"{_price(exit_price)}; resting stop orders do not fire outside "
                 "regular hours",
                 f"{signed_r(r)} total"]
    else:
        word = _EXIT_WORDS.get(detail.get("reason"), detail.get("reason") or "closed")
        verb = EXITED
        headline = f"EXITED @ {_price(exit_price)} — {word} · {signed_r(r)} total"
        lines = [f"If your broker order did not fill: {side['exit']}"]
    told, held = detail.get("notified_stop"), detail.get("bot_stop")
    if told is not None and held is not None and not math.isclose(told, held, abs_tol=1e-6):
        lines.append(f"your last pinged stop was {_price(told)} — that order may still be open")
    return Instruction(verb=verb, headline=headline, lines=tuple(lines), tone=tone, **common)


def instruction_for(plan, event, *, sizing: dict | None = None) -> Instruction:
    """The execution-feed instruction for one plan_manager PlanEvent (v81 D2,
    D3). Every live stop is read from ``event.detail``, which plan_manager
    stamps -- never recomputed here, so the feed cannot quote a stop the
    manager is not holding."""
    side = _sides(plan.direction)
    detail = event.detail
    common = dict(ticker=plan.ticker, direction=plan.direction, plan_id=plan.plan_id)
    transition = event.transition
    if transition == "filled":
        fill = _price(detail["entry_price"])
        return Instruction(
            verb=FILLED, headline=f"FILLED @ {fill} (bot)",
            lines=(f"Confirm your broker filled; the bot's R is measured from {fill}",
                   f"Resting: {side['stop']} {_price(plan.stop_loss)} · "
                   f"TP1 {side['limit']} {_price(plan.tp1)}"),
            **common)
    if transition == "be_moved":
        return Instruction(
            verb=MOVE_STOP,
            headline=f"MOVE STOP → {_price(detail['working_stop'])} after today's close",
            lines=(f"break-even; keep {_price(plan.stop_loss)} until then",), **common)
    if transition == "tp1_partial":
        whole = _whole_shares(sizing)
        qty = (f"{math.floor(whole * detail['fraction']):,} sh" if whole is not None
               else f"{detail['fraction']:.0%}")
        return Instruction(
            verb=MOVE_STOP,
            headline=(f"TP1 FILLED {qty} @ {_price(detail['exit_price'])} "
                      f"({signed_r(detail['r'])})"),
            lines=(f"MOVE STOP on the runner → {_price(detail['working_stop'])} now "
                   "(runner floor)",),
            tone="good", **common)
    if transition == "stop_moved":
        timing = "after today's close" if detail["effective"] == "next_session" else "now"
        return Instruction(
            verb=MOVE_STOP, headline=f"MOVE STOP → {_price(detail['new'])} {timing}",
            lines=(f"{_stop_kind(plan, detail['new'])}; {signed_r(detail['r_moved'])} "
                   "since the last ping",),
            **common)
    if transition in ("cancelled_expired", "cancelled_invalidated"):
        why = (f"not triggered within {plan.expiry_bars} sessions"
               if transition == "cancelled_expired"
               else f"price reached the stop {_price(plan.stop_loss)} before triggering")
        return Instruction(
            verb=CANCEL, headline=f"CANCEL {side['entry_stop']} {_price(plan.trigger_price)}",
            lines=(why,), tone="inert", **common)
    if transition == "closed":
        return _closed(plan, detail, side, common)
    raise ValueError(f"no execution-feed instruction for {transition!r}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_instructions.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/presentation/test_no_adhoc_color.py`
Expected: PASS (the new module sits inside the presentation package, which the
guard skips; this proves the import graph still loads).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/instructions.py tests/presentation/test_instructions.py
git commit -m "feat(v81): execution-feed instruction projection"
```
