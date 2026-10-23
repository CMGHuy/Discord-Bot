# v187 — Safety hardening, part 2: live limit entries

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-23-v187-safety-hardening-design.md](../specs/2026-10-23-v187-safety-hardening-design.md) — § D3, § Testing (D3), § Blast radius
**Index:** [2026-10-23-v187-safety-hardening_0-index.md](2026-10-23-v187-safety-hardening_0-index.md) — Goal, Global Constraints, Contracts, Parallelisation and the task ledger live there. Tasks V187-8..V187-13.

## Parallelisation

See the index's `## Parallelisation`. Within this part: V187-9 follows V187-8 (same file, consumes `PENDING_CANCEL_EVENTS`); V187-10, V187-11 and V187-12 touch disjoint files and may run alongside anything before V187-13; V187-13 runs last.

## Part-2 decisions on the index contracts (writer, 2026-10-23)

Two rows of the index's vocabulary table cannot be applied as written without breaking a test that pins an existing rule. Both deviations are local to this part (no part-1 task reads them):

1. **`instructions._CANCEL_LEADS` uses `""` for both new events, not `"limit"` / `"gap"`.** `_cancelled` renders `_S[key]` with `_S = tokens.FEED_SYMBOLS`, which has no `limit` or `gap` key (a `KeyError`), and `tests/presentation/test_feed_symbols.py:33-34` pins that table exactly. `""` is the existing "no glyph" lead the risk-cap cancel already uses (v170 Decision 4). No new glyph is added.
2. **`follow_notify._CLOSED_OTHER_KIND` maps both new events to `Kind.INVALIDATED`, not `Kind.CANCEL`.** The follow channel is factual by policy and `tests/commands/test_follow_notify_policy.py:62-64` (`test_imperative_kinds_are_never_used`) fails if `Kind.CANCEL` appears in the module. `INVALIDATED` is the factual RESULT kind for a plan withdrawn before entry; the copy line ("cancelled: limit cancelled before fill." / "cancelled: gapped through the stop before fill.") names the reason. The execution feed and the history embeds still use `Kind.CANCEL` (clarification 7).

Also added inside V187-12's own file: `session_expiry.in_session_message` gets wording for both events. Without it `PlanManager._annotate_outlook` skips them (it acts only when a message exists), and the two new codes would never reach an outlook plan.

---

# Phase D3 — Live limit entries

### Task V187-8: One pending-cancel event set drives the placeholder discard and notices

**Model:** opus — edits `PlanManager._on_event` (complexity baseline 15) on the path of the 2026-09-11 stuck-placeholder incident.

**Spec:** § D3 "Wiring the two new cancel events" (first three bullets and the last one).

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (PlanEvent comment `:61-66`; `NOTICE_EVENTS` `:120-121`; `_TRANSITION_LOG` `:140-150`; `_on_event` discard branch `:771-779`)
- Create: `tests/tracking/test_pending_cancel_discard.py`

**Interfaces:**
- Consumes: `TradeLog.log_trade(...)`, `TradeLog.discard_plan_placeholder(plan_id) -> bool`, `TradeLog.get_trades(status=None, limit=None)` (exist, `swingbot/core/tracking/performance.py`); `log_plan_event(plan, event)` (exists, `plan_manager.py:163`).
- Produces (index § Contracts, final):
  ```python
  PENDING_CANCEL_EVENTS = frozenset({
      "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
      "cancelled_limit", "cancelled_gap_through_stop",
  })
  NOTICE_EVENTS = frozenset({"filled", "closed"}) | PENDING_CANCEL_EVENTS
  _TRANSITION_LOG["cancelled_limit"] == ("limit cancelled", "live_price")
  _TRANSITION_LOG["cancelled_gap_through_stop"] == ("gap through stop", "live_price")
  ```
  `_on_event` discards the placeholder for every member of `PENDING_CANCEL_EVENTS`. V187-9 emits the two new events; V187-11 reads `NOTICE_EVENTS` by import (`lifecycle_embeds.py:530`).

Nothing emits `cancelled_limit` or `cancelled_gap_through_stop` yet (V187-9 does). This task only wires the receiving side, so the emitter can never land half-wired.

- [ ] **Step 0: Database replica**

The tests below hit Postgres (`PlanStore`, `TradeLog`). If `/replicate-prod-db` has not run in this session yet, run it once now (CLAUDE.md). Work in the worktree `.claude/worktrees/2026-10-23-v187-safety-hardening`; every path below is relative to it.

- [ ] **Step 1: Write the failing test**

Create `tests/tracking/test_pending_cancel_discard.py`:

```python
"""v187 D3: one PENDING_CANCEL_EVENTS set drives the placeholder discard and
the notice queue, so no pending-cancel event can be added half-wired.

Production incident, 2026-09-11: _on_event discarded the scan's placeholder
trade only for a hand-listed set of cancel events; a cancel event missing
from that list left the placeholder "open" forever. Every member of the set
must discard it."""
import logging

import pytest

from swingbot import config
from swingbot.core.planning.plan_manager import (NOTICE_EVENTS, PENDING_CANCEL_EVENTS,
                                                 PlanEvent, PlanManager, _TRANSITION_LOG,
                                                 log_plan_event)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def _placeholder(tlog):
    return tlog.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=100.0, stop_loss=98.5, take_profit=102.0, plan_id="p1")


def _trades_for(tlog, plan_id):
    return [t for t in tlog.get_trades(status=None, limit=None) if t.get("plan_id") == plan_id]


def test_the_set_holds_exactly_the_five_pending_cancel_events():
    assert PENDING_CANCEL_EVENTS == frozenset({
        "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
        "cancelled_limit", "cancelled_gap_through_stop",
    })


def test_notice_events_derive_from_the_cancel_set():
    assert NOTICE_EVENTS == frozenset({"filled", "closed"}) | PENDING_CANCEL_EVENTS


@pytest.mark.parametrize("transition", sorted(PENDING_CANCEL_EVENTS))
def test_every_pending_cancel_discards_the_placeholder(tlog, transition):
    _placeholder(tlog)
    assert len(_trades_for(tlog, "p1")) == 1

    mgr = PlanManager(PlanStore(), lambda ticker: 100.0, trade_log=tlog)
    mgr._on_event(_plan(), PlanEvent("p1", transition, {}))

    assert _trades_for(tlog, "p1") == []


@pytest.mark.parametrize("transition", sorted(PENDING_CANCEL_EVENTS))
def test_every_pending_cancel_writes_a_transition_line(transition):
    assert transition in _TRANSITION_LOG


@pytest.mark.parametrize("transition, label", [
    ("cancelled_limit", "limit cancelled"),
    ("cancelled_gap_through_stop", "gap through stop"),
])
def test_the_new_cancels_log_their_label_and_the_live_price(caplog, transition, label):
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.plan_manager"):
        log_plan_event(_plan(), PlanEvent("p1", transition, {"live_price": 101.2}))
    assert f"Plan {label}: AAPL" in caplog.text
    assert "price=101.20" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/tracking/test_pending_cancel_discard.py`
Expected: FAIL — collection error, `ImportError: cannot import name 'PENDING_CANCEL_EVENTS' from 'swingbot.core.planning.plan_manager'`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/planning/plan_manager.py`:

(a) Replace the `PlanEvent.transition` comment (`:61-66`) so it names the new events:

```python
@dataclass
class PlanEvent:
    plan_id: str
    transition: str      # "filled"|"be_moved"|"tp1_partial"|"closed"|
                         # "pyramid_add"|any PENDING_CANCEL_EVENTS member;
                         # close reasons include "tp1_runner_progress_stall"
                         # (v123 structure exit)
    detail: dict = field(default_factory=dict)
```

(b) Replace the `NOTICE_EVENTS` definition (`:120-121`) with the set and its derivation; keep the comment block above `STOP_EVENTS` as it is:

```python
STOP_EVENTS = frozenset({"be_moved", "tp1_partial", "stop_moved"})
# v187 D3: every way a PENDING plan ends without a position. The placeholder
# discard in PlanManager._on_event and NOTICE_EVENTS both derive from this one
# set, so a new cancel event cannot be wired into one and missed by the other
# (a missed discard left placeholder trades "open" forever: 2026-09-11).
PENDING_CANCEL_EVENTS = frozenset({
    "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
    "cancelled_limit", "cancelled_gap_through_stop",
})
NOTICE_EVENTS = frozenset({"filled", "closed"}) | PENDING_CANCEL_EVENTS
NOTICE_RESEND_DAYS = 5
```

(c) Add two rows at the end of `_TRANSITION_LOG` (after `"cancelled_risk_cap"`):

```python
    "cancelled_risk_cap": ("risk cap hit", "entry_price"),
    "cancelled_limit": ("limit cancelled", "live_price"),
    "cancelled_gap_through_stop": ("gap through stop", "live_price"),
}
```

(d) In `PlanManager._on_event`, replace the hand-listed tuple (`:771-772`) with the set. The branch body and its incident comment stay; add one line to the comment:

```python
            elif event.transition in PENDING_CANCEL_EVENTS:
                # A PENDING plan never filled -- scan_run.py's placeholder
                # trade for it (still open, sized against the trigger price)
                # has no real position behind it. Left unhandled, it sat
                # "open" in the dashboard/risk numbers forever: production
                # incident, 2026-09-11 (INTU, META among 10 stuck trades
                # found via a dashboard mismatch -- the other 8 were the
                # separate double-logging bug 5d72c1ab already fixed).
                # v187: the set, not a hand list, so no cancel is missed.
                self.trade_log.discard_plan_placeholder(plan.plan_id)
```

This swaps a tuple membership test for a set membership test: no branch is added, so `_on_event` stays at 15.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/tracking/test_pending_cancel_discard.py`
Expected: PASS (14 tests).

Then the neighbours that read these names:

Run: `python scripts/dev/testrun.py file tests/tracking/test_discard_plan_placeholder.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_near_stop_event.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py`
Expected: all PASS, unchanged.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: no finding for `swingbot.core.planning.plan_manager:PlanManager._on_event` (still 15). A finding in a file another in-flight task is changing belongs to that task.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/tracking/test_pending_cancel_discard.py
git commit -m "fix(plans): one PENDING_CANCEL_EVENTS set drives placeholder discard and notices (v187 D3)"
```

### Task V187-9: Live limit entries fill at the limit, cancel beyond the level, refuse a gap through the stop

**Model:** opus — changes the live money-path state machine against a backtest-parity contract, with `_step_pending` held under complexity 15.

**Spec:** § D3 steps 1–4, "The fill check runs before the cancel check", the transition-reason bullet of "Known live/backtest differences", § Testing (D3). Index clarification 1 (the gap-through-stop check reads the **tick** price).

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (imports `:30-37`; `_step_pending` `:918-969`; `_days_since_entry` docstring `:970-980`; new methods `_step_limit`, `_fill_pending` right after `_step_pending`)
- Create: `tests/planning/test_plan_manager_limit_entry.py`

**Interfaces:**
- Consumes: `PENDING_CANCEL_EVENTS`, `NOTICE_EVENTS`, `_TRANSITION_LOG` rows for the two new events (V187-8); `limit_hit(plan, bar_high, bar_low) -> bool`, `limit_cancelled(plan, bar_high, bar_low) -> bool`, `at_or_beyond_stop(plan, price) -> bool` (exist, `swingbot/core/planning/lifecycle.py:155-204`); `_limit_entry_exit(df, signal_index, plan, scale_out, max_holding_days) -> ExitResult` (exists, `swingbot/core/planning/exit_sim.py:797`, test only); `make_ohlcv` (exists, `tests/helpers.py:10`).
- Produces (index § Contracts, final):
  ```python
  class PlanManager:
      def _fill_pending(self, plan: TradePlanV2, fill: float, price: float, reason: str) -> list[PlanEvent]
      def _step_limit(self, plan: TradePlanV2, price: float) -> list[PlanEvent] | None
  ```

  | Event | Transition reason | `detail` keys |
  |---|---|---|
  | `filled` (limit) | `limit_fill` | `entry_price` (= `plan.trigger_price`), `live_price` |
  | `cancelled_limit` | `limit_cancelled` | `live_price`, `limit_cancel_level` |
  | `cancelled_gap_through_stop` | `gap_through_stop` | `entry_price` (= `plan.trigger_price`), `live_price`, `stop_loss` |
  | `cancelled_risk_cap` (limit fill) | `risk_cap` | unchanged: `entry_price`, `stop_loss`, `planned_loss_pct`, `max_planned_loss_pct` |

**Rules, in order, for a PENDING plan with `entry_type == "limit"`** (after the session-window / bar-count expiry checks, which are unchanged and still come first):

1. `limit_hit(plan, price, price)` — a tick is a one-print bar, so `limit_strict_fill` keeps its meaning.
   - `at_or_beyond_stop(plan, price)` → CANCELLED, reason `gap_through_stop`, event `cancelled_gap_through_stop`. No trade: `_on_event` discards the placeholder (V187-8). Checked before the risk cap because `planned_loss_pct` takes `abs()` and would score a stop on the wrong side as a small risk.
   - otherwise `_fill_pending(plan, plan.trigger_price, price, "limit_fill")` — fill **at the limit**, never the better tick.
2. else `limit_cancelled(plan, price, price)` → CANCELLED, reason `limit_cancelled`, event `cancelled_limit`.
3. else `None`: the caller falls through to the unchanged `pending_invalidated` check.

Every other `entry_type` keeps the stop-entry branch byte-for-byte in behaviour; only its risk-cap/fill tail moves into `_fill_pending` (reason `stop_entry_fill`).

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_limit_entry.py`:

```python
"""v187 D3: live limit entries fill like the backtest.

A buy limit fills when a tick trades at or below it, a sell limit at or
above it, always AT the limit (the conservative twin of exit_sim's non-gap
limit fill). Beyond limit_cancel_level the order is cancelled; a tick
already at or through the stop opens nothing (the live twin of the
backtest's 0R gap_through_stop scratch). Every other entry type keeps the
stop-entry branch unchanged."""
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import _limit_entry_exit
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

DIRECTIONS = ("bullish", "bearish")

#: Levels per side. The stop sits 1.5% from the 100.00 limit, inside the
#: default 2% stop ceiling, so a clean fill is never risk-capped.
_LEVELS = {
    "bullish": dict(trigger_price=100.0, stop_loss=98.5, tp1=102.0, tp2=104.0,
                    limit_cancel_level=101.0),
    "bearish": dict(trigger_price=100.0, stop_loss=101.5, tp1=98.0, tp2=96.0,
                    limit_cancel_level=99.0),
}

#: Ticks per side, named by what they do to a resting 100.00 limit.
_TICKS = {
    "bullish": dict(touch=100.0, through=99.4, short_of=100.5, beyond_cancel=101.2,
                    through_stop=98.4, at_stop=98.5),
    "bearish": dict(touch=100.0, through=100.6, short_of=99.5, beyond_cancel=98.8,
                    through_stop=101.6, at_stop=101.5),
}


@pytest.fixture(autouse=True)
def _plain_ceiling_and_clock(monkeypatch):
    # Out-of-scope plans keep the 2% stop ceiling; poll() reads the wall
    # clock, and the Berlin quiet window (23:00-08:00) would return [].
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _limit(direction="bullish", **kw):
    base = dict(entry_type="limit", direction=direction, expiry_bars=5, **_LEVELS[direction])
    base.update(kw)
    return _plan(**base)


def _step(plan, price, **mgr_kw):
    """One _step_pending tick at `price`; returns (stored plan, events)."""
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, lambda ticker: price, **mgr_kw)
    events = mgr._step_pending(plan, price)
    return store.get(plan.plan_id), events


def _reason(plan):
    return plan.status_history[-1]["reason"]


# --- fills ---------------------------------------------------------------------

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_touch_fills_at_the_limit(direction):
    plan, events = _step(_limit(direction), _TICKS[direction]["touch"])
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": 100.0}
    assert plan.status == PlanStatus.ACTIVE
    assert plan.entry_price == 100.0
    assert _reason(plan) == "limit_fill"


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_tick_through_the_limit_fills_at_the_limit_not_at_the_tick(direction):
    tick = _TICKS[direction]["through"]
    plan, events = _step(_limit(direction), tick)
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": tick}
    assert plan.entry_price == 100.0


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_strict_fill_refuses_an_exact_touch(direction):
    plan, events = _step(_limit(direction, limit_strict_fill=True), _TICKS[direction]["touch"])
    assert events == []
    assert plan.status == PlanStatus.PENDING


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_strict_fill_takes_a_trade_through(direction):
    plan, events = _step(_limit(direction, limit_strict_fill=True),
                         _TICKS[direction]["through"])
    assert [e.transition for e in events] == ["filled"]
    assert plan.entry_price == 100.0


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_tick_short_of_the_limit_does_nothing(direction):
    plan, events = _step(_limit(direction), _TICKS[direction]["short_of"])
    assert events == []
    assert plan.status == PlanStatus.PENDING


# --- cancel level --------------------------------------------------------------

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_beyond_the_cancel_level_cancels(direction):
    tick = _TICKS[direction]["beyond_cancel"]
    plan, events = _step(_limit(direction), tick)
    assert [e.transition for e in events] == ["cancelled_limit"]
    assert events[0].detail == {"live_price": tick,
                                "limit_cancel_level": _LEVELS[direction]["limit_cancel_level"]}
    assert plan.status == PlanStatus.CANCELLED
    assert _reason(plan) == "limit_cancelled"
    assert plan.entry_price is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_an_equal_print_at_the_cancel_level_does_not_cancel(direction):
    level = _LEVELS[direction]["limit_cancel_level"]
    plan, events = _step(_limit(direction), level)
    assert events == []
    assert plan.status == PlanStatus.PENDING


def test_a_limit_without_a_cancel_level_never_cancels():
    plan, events = _step(_limit("bullish", limit_cancel_level=None), 150.0)
    assert events == []
    assert plan.status == PlanStatus.PENDING


@pytest.mark.parametrize("direction, cancel_level, tick", [
    ("bullish", 99.0, 99.5),      # fills (<= 100) and is above the 99.0 level
    ("bearish", 101.0, 100.5),    # fills (>= 100) and is below the 101.0 level
])
def test_a_tick_that_fills_and_is_beyond_the_cancel_level_fills(direction, cancel_level, tick):
    plan, events = _step(_limit(direction, limit_cancel_level=cancel_level), tick)
    assert [e.transition for e in events] == ["filled"]
    assert plan.entry_price == 100.0


# --- the stop ------------------------------------------------------------------

@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("which", ["through_stop", "at_stop"])
def test_a_fill_at_or_through_the_stop_opens_nothing(direction, which):
    tick = _TICKS[direction][which]
    plan, events = _step(_limit(direction), tick)
    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": tick,
                                "stop_loss": _LEVELS[direction]["stop_loss"]}
    assert plan.status == PlanStatus.CANCELLED
    assert _reason(plan) == "gap_through_stop"
    assert plan.entry_price is None


def test_a_stop_on_the_wrong_side_of_the_limit_is_a_gap_not_a_small_risk():
    # planned_loss_pct(100.0, 100.5) is 0.5% by abs() -- under the cap -- yet a
    # long filled at 100 with its stop at 100.5 is already stopped out.
    plan, events = _step(_limit("bullish", stop_loss=100.5), 99.8)
    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]
    assert plan.status == PlanStatus.CANCELLED


@pytest.mark.parametrize("direction, stop", [("bullish", 97.0), ("bearish", 103.0)])
def test_a_limit_fill_over_the_risk_cap_is_cancelled(direction, stop):
    plan, events = _step(_limit(direction, stop_loss=stop), _TICKS[direction]["touch"])
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail == {"entry_price": 100.0, "stop_loss": stop,
                                "planned_loss_pct": pytest.approx(3.0),
                                "max_planned_loss_pct": pytest.approx(2.0)}
    assert plan.status == PlanStatus.CANCELLED
    assert _reason(plan) == "risk_cap"


# --- what stays as it was ------------------------------------------------------

def test_a_limit_plan_still_expires_on_its_bar_count_first():
    plan, events = _step(_limit("bullish"), 100.0, bar_count_fn=lambda ticker, created: 6)
    assert [e.transition for e in events] == ["cancelled_expired"]
    assert plan.status == PlanStatus.CANCELLED


def test_a_stop_entry_plan_keeps_its_fill_price_and_reason():
    plan, events = _step(_plan(entry_type="stop_entry", trigger_price=105.0,
                               stop_loss=104.0, tp1=110.0), 106.0)
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": 106.0, "live_price": 106.0}
    assert _reason(plan) == "stop_entry_fill"


# --- parity with the backtest --------------------------------------------------

#: (signal bar, non-gap fill bar, quiet bars): the fill bar opens on the far side
#: of the limit and trades back through it, so the backtest fills AT the limit.
_PARITY_BARS = {
    "bullish": [(100.5, 101.0, 99.5, 100.0), (100.6, 100.8, 99.7, 100.2),
                (100.2, 100.6, 99.9, 100.3), (100.3, 100.6, 99.9, 100.2)],
    "bearish": [(99.5, 100.5, 99.0, 100.0), (99.4, 100.3, 99.2, 99.8),
                (99.8, 100.1, 99.4, 99.7), (99.7, 100.1, 99.4, 99.8)],
}
#: The live tick is the fill bar's extreme print through the limit.
_PARITY_TICK = {"bullish": 99.7, "bearish": 100.3}


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_live_limit_fill_matches_the_backtest_on_a_non_gap_bar(direction):
    backtest = _limit_entry_exit(make_ohlcv(_PARITY_BARS[direction]), 0,
                                 _limit(direction, plan_id="bt"), False, 10)
    _, events = _step(_limit(direction), _PARITY_TICK[direction])
    assert backtest.entry_index == 1
    assert events[0].transition == "filled"
    assert events[0].detail["entry_price"] == backtest.entry_price == 100.0


# --- end to end through poll(): no trade behind a gap --------------------------

@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def test_a_gap_through_the_stop_leaves_no_trade_behind(tlog):
    tlog.log_trade(ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
                   direction="bullish", confidence_level=4, confidence_label="High",
                   entry=100.0, stop_loss=98.5, take_profit=102.0, plan_id="p1")
    store = PlanStore()
    store.add(_limit("bullish"))
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 98.4)]).get_price, trade_log=tlog)

    events = mgr.poll()

    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]
    assert store.get("p1").status == PlanStatus.CANCELLED
    assert [t for t in tlog.get_trades(status=None, limit=None)
            if t.get("plan_id") == "p1"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_limit_entry.py`
Expected: FAIL. Today every pending plan takes the stop-entry branch, so: a bullish touch at 100.0 fills with reason `stop_entry_fill` (want `limit_fill`); a bullish tick at 99.4 returns `[]` (want `["filled"]` at 100.0); the strict-touch, short-of-the-limit and no-cancel-level cases fill (want `[]`); `cancelled_limit` and `cancelled_gap_through_stop` never appear. Only `test_a_limit_plan_still_expires_on_its_bar_count_first`, `test_a_stop_entry_plan_keeps_its_fill_price_and_reason` and the two risk-cap cases may already pass.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/planning/plan_manager.py`:

(a) Add the lifecycle import next to the other planning imports (after the `plan_engine` import block, `:30-35`):

```python
from swingbot.core.planning.lifecycle import at_or_beyond_stop, limit_cancelled, limit_hit
```

(b) Replace `_step_pending` (`:918-969`) and add the two helpers right after it:

```python
    def _step_pending(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """One tick for a PENDING plan: expiry first, then the entry rule for
        its entry_type (v187 D3: a limit rests and fills at its own price;
        every other type is a stop entry), then pre-entry invalidation."""
        is_bull = plan.direction == "bullish"

        if _has_session_window(plan):
            window = self._session_window(plan, now)
            if window is not None:
                return window
        elif self.bar_count_fn is not None:
            bars = self.bar_count_fn(plan.ticker, plan.created_at)
            if pending_expired(plan, bars):
                record_transition(plan, PlanStatus.CANCELLED, reason="expired",
                                  at=self._now())
                self.store.update(plan)
                return [PlanEvent(plan.plan_id, "cancelled_expired",
                                  {"bars_waited": bars})]

        if plan.entry_type == "limit":
            limit_events = self._step_limit(plan, price)
            if limit_events is not None:
                return limit_events
        else:
            crossed = price >= plan.trigger_price if is_bull else price <= plan.trigger_price
            if crossed:
                fill = max(price, plan.trigger_price) if is_bull \
                    else min(price, plan.trigger_price)
                return self._fill_pending(plan, fill, price, "stop_entry_fill")

        if pending_invalidated(plan, price):
            record_transition(plan, PlanStatus.CANCELLED, reason="invalidated",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "cancelled_invalidated",
                              {"live_price": price})]
        return []

    def _step_limit(self, plan: TradePlanV2, price: float) -> list[PlanEvent] | None:
        """v187 D3: a resting limit on one tick, the live twin of
        exit_sim._limit_entry_exit. A tick is a one-print bar (High = Low =
        price), so limit_strict_fill keeps its meaning. The fill is checked
        before the cancel level, as in the backtest.

        Fills AT the limit, never at the better tick: a 60s poll that first
        sees price through the limit usually missed the print at the limit,
        and booking the tick would beat the backtest's non-gap fill.
        A tick at or through the stop opens nothing (the backtest's 0R
        gap_through_stop scratch); checked on the tick, before the risk cap,
        because planned_loss_pct takes abs() and would pass a stop on the
        wrong side. None when nothing happened this tick."""
        if limit_hit(plan, price, price):
            if at_or_beyond_stop(plan, price):
                record_transition(plan, PlanStatus.CANCELLED, reason="gap_through_stop",
                                  at=self._now())
                self.store.update(plan)
                return [PlanEvent(plan.plan_id, "cancelled_gap_through_stop", {
                    "entry_price": plan.trigger_price,
                    "live_price": price,
                    "stop_loss": plan.stop_loss,
                })]
            return self._fill_pending(plan, plan.trigger_price, price, "limit_fill")
        if limit_cancelled(plan, price, price):
            record_transition(plan, PlanStatus.CANCELLED, reason="limit_cancelled",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "cancelled_limit", {
                "live_price": price,
                "limit_cancel_level": plan.limit_cancel_level,
            })]
        return None

    def _fill_pending(self, plan: TradePlanV2, fill: float, price: float,
                      reason: str) -> list[PlanEvent]:
        """Fill a PENDING plan at `fill` (tick `price`), or cancel it when the
        planned loss from that fill is over the plan's stop ceiling. Shared by
        the stop-entry and limit branches; only the ACTIVE reason differs."""
        risk_pct = planned_loss_pct(fill, plan.stop_loss)
        ceiling_pct = plan_stop_ceiling(plan)
        if risk_pct > ceiling_pct:
            record_transition(plan, PlanStatus.CANCELLED, reason="risk_cap",
                              at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "cancelled_risk_cap", {
                "entry_price": fill,
                "stop_loss": plan.stop_loss,
                "planned_loss_pct": round(risk_pct, 4),
                "max_planned_loss_pct": ceiling_pct,
            })]
        plan.entry_price = fill
        record_transition(plan, PlanStatus.ACTIVE, reason=reason, at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "filled",
                          {"entry_price": fill, "live_price": price})]
```

(c) In the `_days_since_entry` docstring, replace `(recorded once, by the stop_entry_fill transition)` with `(recorded once, by the fill transition: stop_entry_fill or limit_fill)`. `_entered_at` reads the ACTIVE entry whatever its reason, so no code changes there.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_limit_entry.py`
Expected: PASS (29 tests).

Every existing stop-entry test must pass **unchanged**:

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_stop_ceiling.py`
Run: `python scripts/dev/testrun.py file tests/tracking/test_pending_cancel_discard.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_limit_entry.py`
Expected: all PASS with no edit to any of them. Then the wider net:

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s swingbot/core/planning/plan_manager.py | grep -E "_step_pending|_step_limit|_fill_pending|_on_event"`
Expected: `_step_pending` at 11 or below, `_step_limit` and `_fill_pending` well under 15, `_on_event` 15 (unchanged).

Run: `python scripts/dev/complexity_gate.py`
Expected: no finding in `plan_manager.py`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_limit_entry.py
git commit -m "fix(plans): live limit entries fill at the limit, cancel beyond the level, refuse a gap through the stop (v187 D3)"
```

### Task V187-10: Instruction wording for the two new cancel events

**Model:** sonnet — two table rows and one wording helper in a pure presentation module, with its tests.

**Spec:** § D3 "Wiring the two new cancel events", `instructions.py` bullet: `_cancel_why` gets its own wording for both events (without it they fall through to the risk-cap sentence and raise `KeyError` on `detail['planned_loss_pct']`).

**Files:**
- Modify: `swingbot/core/presentation/instructions.py` (`_CANCEL_LEADS` `:542-544`; `_cancel_why` `:547-559`; `_BUILDERS` `:571-583`)
- Create: `tests/presentation/test_instructions_limit_cancels.py`

**Interfaces:**
- Consumes: event names and `detail` keys from index § Contracts — `cancelled_limit` {`live_price`, `limit_cancel_level`}, `cancelled_gap_through_stop` {`entry_price`, `live_price`, `stop_loss`}. The test builds `PlanEvent` objects by hand, so this task does not need V187-8 or V187-9 merged first.
- Produces: `_CANCEL_LEADS["cancelled_limit"] == ""`, `_CANCEL_LEADS["cancelled_gap_through_stop"] == ""` (part-2 decision 1: `FEED_SYMBOLS` has no `limit`/`gap` key and is pinned); `_BUILDERS[...] is _cancelled` for both; `_CANCEL_WHY: dict[str, Callable[[dict], str]]` with the two contract sentences.

**Decisions written down (spec: "confirm and write the choice"):**
- Lead glyph: none (`""`), as the risk-cap cancel. Adding a glyph would change `FEED_SYMBOLS`, the `!help` legend and `test_feed_symbols.py`; out of scope.
- Headline: unchanged `_cancelled` (`CANCEL <entry_stop side> <trigger>`). `tests/presentation/test_feed_guards.py::test_every_cancel_says_cancel_and_names_the_entry_order` pins that every cancel names `_sides()["entry_stop"]`. A limit-specific entry verb for all limit messages (filled, expired, cancelled) is a separate presentation change, flagged to the controller rather than made here.
- Order inside `_cancel_why`: a stated outlook `reason_message` still wins (v144); the two new events are looked up next, **before** the compression branch, so `short_notice.compression_cancel_why` never receives a transition it does not know.

- [ ] **Step 1: Write the failing test**

Create `tests/presentation/test_instructions_limit_cancels.py`:

```python
"""v187 D3: the execution feed words the two new pending cancels -- a limit
cancelled beyond its cancel level, and a limit that touched at or through its
stop -- instead of falling through to the risk-cap sentence (KeyError)."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from tests.planning.test_plan_engine_model import _plan

NEW_CANCELS = ("cancelled_limit", "cancelled_gap_through_stop")


def _limit(direction="bullish", **kw):
    levels = (dict(trigger_price=100.0, stop_loss=98.5, tp1=102.0, limit_cancel_level=101.0)
              if direction == "bullish" else
              dict(trigger_price=100.0, stop_loss=101.5, tp1=98.0, limit_cancel_level=99.0))
    base = dict(entry_type="limit", direction=direction, entry_price=None,
                status="PENDING", **levels)
    base.update(kw)
    return _plan(**base)


def _event(transition, **detail):
    return PlanEvent("p1", transition, detail)


def test_a_limit_cancel_explains_the_cancel_level():
    instruction = ins.instruction_for(
        _limit(), _event("cancelled_limit", live_price=101.2, limit_cancel_level=101.0))
    assert (instruction.verb, instruction.tone) == (ins.CANCEL, "inert")
    assert instruction.headline == "CANCEL BUY STOP 100.00"
    assert instruction.lines == (
        "Price ran past the limit's cancel level 101.00 at 101.20 before the order "
        "filled. Nothing was opened.",)


def test_a_gap_through_the_stop_explains_why_nothing_opened():
    instruction = ins.instruction_for(
        _limit("bearish"),
        _event("cancelled_gap_through_stop", entry_price=100.0, live_price=101.6,
               stop_loss=101.5))
    assert (instruction.verb, instruction.tone) == (ins.CANCEL, "inert")
    assert instruction.headline == "CANCEL SELL STOP 100.00"
    assert instruction.lines == (
        "Price touched the limit at 101.60, already at or through the stop 101.50. "
        "The order is cancelled, nothing was opened.",)


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_new_cancels_carry_no_lead_glyph(transition):
    assert ins._CANCEL_LEADS[transition] == ""
    assert ins._BUILDERS[transition] is ins._cancelled


def test_every_cancel_lead_is_empty_or_a_feed_symbol():
    assert all(key == "" or key in tokens.FEED_SYMBOLS for key in ins._CANCEL_LEADS.values())


def test_a_stated_outlook_reason_still_wins():
    instruction = ins.instruction_for(
        _limit(), _event("cancelled_limit", live_price=101.2, limit_cancel_level=101.0,
                         reason_message="Ran past the cancel level"))
    assert instruction.lines == ("Ran past the cancel level",)


def test_every_pending_cancel_event_has_a_builder_and_a_lead():
    from swingbot.core.planning import plan_manager
    cancels = getattr(plan_manager, "PENDING_CANCEL_EVENTS", None)
    if cancels is None:              # V187-8 not merged into this branch yet
        cancels = frozenset({"cancelled_expired", "cancelled_invalidated",
                             "cancelled_risk_cap", *NEW_CANCELS})
    assert cancels <= set(ins._BUILDERS)
    assert cancels <= set(ins._CANCEL_LEADS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/presentation/test_instructions_limit_cancels.py`
Expected: FAIL — `instruction_for` raises `ValueError: no execution-feed instruction for 'cancelled_limit'`, and `_CANCEL_LEADS["cancelled_limit"]` raises `KeyError`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/presentation/instructions.py`:

(a) Extend `_CANCEL_LEADS` (`:542-544`) and add the wording table right after it:

```python
#: cancel transition -> its headline's FEED_SYMBOLS key ('' = no glyph, v170 Decision 4).
_CANCEL_LEADS = {"cancelled_expired": "expiry", "cancelled_invalidated": "invalid",
                 "cancelled_risk_cap": "", "cancelled_limit": "",
                 "cancelled_gap_through_stop": ""}


def _limit_cancel_why(detail: dict) -> str:
    return (f"Price ran past the limit's cancel level {_price(detail['limit_cancel_level'])} "
            f"at {_price(detail['live_price'])} before the order filled. Nothing was opened.")


def _gap_through_stop_why(detail: dict) -> str:
    return (f"Price touched the limit at {_price(detail['live_price'])}, already at or "
            f"through the stop {_price(detail['stop_loss'])}. The order is cancelled, "
            "nothing was opened.")


#: v187 D3: the limit-entry cancels, each worded from its own detail keys.
_CANCEL_WHY = {
    "cancelled_limit": _limit_cancel_why,
    "cancelled_gap_through_stop": _gap_through_stop_why,
}
```

(b) In `_cancel_why`, add the lookup right after the `reason_message` check:

```python
def _cancel_why(plan, transition: str, detail: dict) -> str:
    if detail.get("reason_message"):
        return detail["reason_message"]             # v144: an outlook plan states its reason
    why = _CANCEL_WHY.get(transition)
    if why is not None:
        return why(detail)                          # v187: limit-entry cancels
    if short_notice.is_compression(plan) and transition != "cancelled_invalidated":
        return short_notice.compression_cancel_why(plan, transition, detail)
    if transition == "cancelled_expired":
        return f"not triggered within {plan.expiry_bars} sessions"
    if transition == "cancelled_invalidated":
        return f"price reached the stop {_price(plan.stop_loss)} before triggering"
    return (f"triggered at {_price(detail['entry_price'])} but risked "
            f"{detail['planned_loss_pct']:.1f}% against stop "
            f"{_price(detail['stop_loss'])} -- above the "
            f"{detail['max_planned_loss_pct']:.1f}% cap; never filled")
```

(c) Add both events to `_BUILDERS` (after `"cancelled_risk_cap": _cancelled,`):

```python
    "cancelled_risk_cap": _cancelled,
    "cancelled_limit": _cancelled,
    "cancelled_gap_through_stop": _cancelled,
```

No glyph literal is written (`test_feed_guards.py::test_instructions_py_writes_no_glyph_literal`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_instructions_limit_cancels.py`
Expected: PASS (7 tests).

Run: `python scripts/dev/testrun.py file tests/presentation/test_instructions.py`
Run: `python scripts/dev/testrun.py file tests/presentation/test_feed_guards.py`
Run: `python scripts/dev/testrun.py file tests/presentation/test_feed_symbols.py`
Expected: all PASS, unchanged.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s swingbot/core/presentation/instructions.py | grep -E "_cancel_why|_limit_cancel_why|_gap_through_stop_why"`
Expected: `_cancel_why` at 7 (was 6); both helpers at 1.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/presentation/instructions.py tests/presentation/test_instructions_limit_cancels.py
git commit -m "feat(feed): word the limit-cancel and gap-through-stop cancels (v187 D3)"
```

### Task V187-11: Lifecycle and execution embeds for the two new cancel events

**Model:** sonnet — table rows and two field builders following the existing `_risk_cap_fields` pattern.

**Spec:** § D3 "Wiring the two new cancel events": `core/scanning/execution_embeds.py:33` and `core/scanning/lifecycle_embeds.py` (`_EVENT_KINDS` / `PLAN_EVENT_KINDS`, `_EVENT_FIELDS`). Index clarification 7: both render as `Kind.CANCEL`.

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`PLAN_EVENT_KINDS` `:302-309`; new field builders after `_risk_cap_fields` `:399-404`; `_EVENT_FIELDS` `:413-421`)
- Modify: `swingbot/core/scanning/execution_embeds.py` (`_EVENT_KINDS` `:27-34`)
- Create: `tests/scanning/test_lifecycle_embeds_limit_cancels.py`

**Interfaces:**
- Consumes: event names and `detail` keys from index § Contracts (the test builds `PlanEvent`s by hand, so V187-8/9 need not be merged first); `Kind.CANCEL` (exists, `swingbot/core/presentation/kinds.py:122`, MANAGE family, 🚫); `plan_levels_block(plan, price)` (exists, imported in `lifecycle_embeds.py:22`).
- Produces: `PLAN_EVENT_KINDS` and `execution_embeds._EVENT_KINDS` rows `cancelled_limit` / `cancelled_gap_through_stop` → `Kind.CANCEL`; `_limit_cancelled_fields(embed, plan, d) -> None`, `_gap_through_stop_fields(embed, plan, d) -> None`.

**Decisions written down (spec: "confirm and write the choice"):**
- `lifecycle_embeds.PLAN_EVENT_KINDS` (the module has one transition→kind table; the brief's `_EVENT_KINDS` there is this same table): both → `Kind.CANCEL`. `_ENDED_OUTCOME` keys on EXPIRED/INVALIDATED only, so the title carries no outcome mark, like the risk-cap cancel.
- `execution_embeds._EVENT_KINDS`: both → `Kind.CANCEL`. `_event_style` reads this table for every event other than `filled` / `closed`; without the rows both events would render as the history-only `PLAN UPDATE` kind.
- `lifecycle_embeds.notify_plan_events` (`:530`, `:546`): needs no edit. It reads `NOTICE_EVENTS` by import, and V187-8 puts both events in it, so they reach the execution feed through `build_instruction_embed` (wording: V187-10).
- `_fields_for` keeps letting a stated outlook `reason_message` win (v144), so an outlook limit plan shows the catalogue wording from V187-12.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_lifecycle_embeds_limit_cancels.py`:

```python
"""v187 D3: the two new pending cancels render as CANCEL in the history
embeds and the execution feed, each with a Why field from its own detail."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

NEW_CANCELS = ("cancelled_limit", "cancelled_gap_through_stop")


def _limit(**kw):
    base = dict(entry_type="limit", direction="bullish", trigger_price=100.0,
                entry_price=None, stop_loss=98.5, tp1=102.0, tp2=104.0,
                limit_cancel_level=101.0, status="CANCELLED")
    base.update(kw)
    return _plan(**base)


def _why(embed) -> str:
    return next(f.value for f in embed.fields if f.name == "Why")


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_both_tables_map_the_new_cancels_to_cancel(transition):
    assert lifecycle_embeds.PLAN_EVENT_KINDS[transition] is Kind.CANCEL
    assert execution_embeds._EVENT_KINDS[transition] is Kind.CANCEL


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_feed_styles_the_new_cancels_as_cancel(transition):
    event = PlanEvent("p1", transition, {})
    assert execution_embeds._event_style(_limit(), event, None) == (Kind.CANCEL, None, None)


def test_a_limit_cancel_embed_names_the_level_and_the_price():
    embed = build_plan_event_embed(_limit(), PlanEvent(
        "p1", "cancelled_limit", {"live_price": 101.2, "limit_cancel_level": 101.0}))
    assert embed.title == "🚫 ▲ LONG AAPL · CANCEL"
    assert embed.color.value == kinds.MANAGE_AMBER
    assert _why(embed) == (
        "Price ran to 101.20, past the limit's cancel level 101.00, before the "
        "100.00 limit filled. Never opened; no position, no P&L.")


def test_a_gap_through_stop_embed_names_the_limit_the_price_and_the_stop():
    embed = build_plan_event_embed(_limit(), PlanEvent(
        "p1", "cancelled_gap_through_stop",
        {"entry_price": 100.0, "live_price": 98.4, "stop_loss": 98.5}))
    assert embed.title == "🚫 ▲ LONG AAPL · CANCEL"
    assert _why(embed) == (
        "Touched the 100.00 limit at 98.40, already at or through the stop 98.50. "
        "Never opened; no position, no P&L.")


def test_a_stated_outlook_reason_still_wins():
    embed = build_plan_event_embed(_limit(), PlanEvent(
        "p1", "cancelled_limit", {"live_price": 101.2, "limit_cancel_level": 101.0,
                                  "reason_message": "Ran past the cancel level",
                                  "reason_code": "limit_cancelled"}))
    assert _why(embed) == "Ran past the cancel level (limit_cancelled)"


def test_every_pending_cancel_event_has_a_kind_and_fields():
    from swingbot.core.planning import plan_manager
    cancels = getattr(plan_manager, "PENDING_CANCEL_EVENTS", None)
    if cancels is None:              # V187-8 not merged into this branch yet
        cancels = frozenset({"cancelled_expired", "cancelled_invalidated",
                             "cancelled_risk_cap", *NEW_CANCELS})
    assert cancels <= set(lifecycle_embeds.PLAN_EVENT_KINDS)
    assert cancels <= set(lifecycle_embeds._EVENT_FIELDS)
    assert cancels <= set(execution_embeds._EVENT_KINDS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_limit_cancels.py`
Expected: FAIL — `KeyError: 'cancelled_limit'` on both tables; `_event_style` returns `Kind.PLAN_UPDATE`; the embed titles read `PLAN UPDATE` and carry no `Why` field (`StopIteration`).

- [ ] **Step 3: Write the implementation**

(a) `swingbot/core/scanning/lifecycle_embeds.py` — extend `PLAN_EVENT_KINDS`:

```python
#: v2 plan transition -> registry kind (v110 §2). "closed" is keyed by reason below.
PLAN_EVENT_KINDS = {
    "filled": Kind.ENTRY_TRIGGERED,
    "cancelled_expired": Kind.EXPIRED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
    "cancelled_limit": Kind.CANCEL,                  # v187 D3
    "cancelled_gap_through_stop": Kind.CANCEL,       # v187 D3
    "be_moved": Kind.BE_MOVED,
    "tp1_partial": Kind.TP1_HIT,
}
```

(b) Same file — add the two field builders right after `_risk_cap_fields`:

```python
def _limit_cancelled_fields(embed, plan, d) -> None:
    """v187 D3: a resting limit cancelled beyond its cancel level."""
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"Price ran to {d['live_price']:.2f}, past the limit's cancel level "
        f"{d['limit_cancel_level']:.2f}, before the {plan.trigger_price:.2f} limit filled. "
        "Never opened; no position, no P&L."), inline=False)


def _gap_through_stop_fields(embed, plan, d) -> None:
    """v187 D3: a limit touched at or through its stop opens nothing."""
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"Touched the {d['entry_price']:.2f} limit at {d['live_price']:.2f}, already at "
        f"or through the stop {d['stop_loss']:.2f}. Never opened; no position, no P&L."),
        inline=False)
```

(c) Same file — extend `_EVENT_FIELDS`:

```python
_EVENT_FIELDS = {
    "filled": _filled_fields,
    "be_moved": _be_moved_fields,
    "tp1_partial": _tp1_partial_fields,
    "closed": _closed_fields,
    "cancelled_expired": _expired_fields,
    "cancelled_invalidated": _invalidated_fields,
    "cancelled_risk_cap": _risk_cap_fields,
    "cancelled_limit": _limit_cancelled_fields,
    "cancelled_gap_through_stop": _gap_through_stop_fields,
}
```

(d) `swingbot/core/scanning/execution_embeds.py` — extend `_EVENT_KINDS`:

```python
#: feed transition -> registry kind; "filled" and "closed" are styled in _event_style.
_EVENT_KINDS = {
    "be_moved": Kind.BE_MOVED,
    "tp1_partial": Kind.TP1_HIT,
    "stop_moved": Kind.MOVE_STOP,
    "cancelled_expired": Kind.EXPIRED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
    "cancelled_limit": Kind.CANCEL,                  # v187 D3
    "cancelled_gap_through_stop": Kind.CANCEL,       # v187 D3
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_limit_cancels.py`
Expected: PASS (8 tests).

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py`
Expected: both PASS, unchanged.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/lifecycle_embeds.py swingbot/core/scanning/execution_embeds.py tests/scanning/test_lifecycle_embeds_limit_cancels.py
git commit -m "feat(embeds): render the limit-cancel and gap-through-stop cancels as CANCEL (v187 D3)"
```

### Task V187-12: Session-expiry codes and follow notices for the two new cancel events

**Model:** sonnet — table rows and two message helpers in two policy modules, with their tests.

**Spec:** § D3 "Wiring the two new cancel events": `commands/scanning/follow_notify.py:54,68,140` and `session_expiry.py:35`. Index: `session_expiry` codes `LIMIT_CANCELLED` / `GAP_THROUGH_STOP` (controller-accepted clarification 3); part-2 decision 2 for the follow-channel kind.

**Files:**
- Modify: `swingbot/core/planning/session_expiry.py` (module docstring `:1-16`; constants `:26-35`; `in_session_message` `:126-133`)
- Modify: `swingbot/commands/scanning/follow_notify.py` (`_BY_TRANSITION` `:50-57`; `_CLOSED_OTHER_KIND` `:65-69`; `_CANCEL_LABELS` `:139-142`)
- Create: `tests/commands/test_follow_notify_limit_cancels.py`

**Interfaces:**
- Consumes: event names and `detail` keys from index § Contracts (hand-built `PlanEvent`s; V187-8/9 need not be merged first).
- Produces:
  ```python
  # swingbot/core/planning/session_expiry.py
  LIMIT_CANCELLED = "limit_cancelled"
  GAP_THROUGH_STOP = "gap_through_stop"
  _IN_SESSION_CODES = {"cancelled_invalidated": INVALIDATED, "cancelled_risk_cap": RISK_CAP,
                       "cancelled_limit": LIMIT_CANCELLED,
                       "cancelled_gap_through_stop": GAP_THROUGH_STOP}
  ```
  `in_session_message(plan, "cancelled_limit" | "cancelled_gap_through_stop", detail) -> str`; follow-notify rows `_BY_TRANSITION[...] == "closed_other"`, `_CLOSED_OTHER_KIND[...] is Kind.INVALIDATED`, `_CANCEL_LABELS` per index § Contracts.

**Decisions written down (spec: "confirm and write the choice"):**
- `session_expiry`: codes **and** words. `PlanManager._annotate_outlook` stamps a code only when `in_session_message` returns a message, so codes alone would never reach an outlook plan. The messages follow the module's style (one clause, no trailing period).
- `follow_notify._BY_TRANSITION`: both → `"closed_other"`. The plan was withdrawn before entry, like an invalidated or risk-capped plan, and is posted for Following followers only.
- `follow_notify._CLOSED_OTHER_KIND`: both → `Kind.INVALIDATED` (part-2 decision 2: `test_follow_notify_policy.py::test_imperative_kinds_are_never_used` bans `Kind.CANCEL` from this factual channel). The copy line names the actual reason.
- `follow_notify._CANCEL_LABELS`: `"limit cancelled before fill"`, `"gapped through the stop before fill"` (index § Contracts).

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_follow_notify_limit_cancels.py`:

```python
"""v187 D3: the two new pending cancels in the follow channel (factual, never
an imperative kind) and in an outlook plan's catalogue (code + message)."""
import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning import session_expiry as se
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation.kinds import Kind
from tests.planning.test_plan_engine_model import _plan

NEW_CANCELS = ("cancelled_limit", "cancelled_gap_through_stop")

_DETAIL = {
    "cancelled_limit": {"live_price": 101.2, "limit_cancel_level": 101.0},
    "cancelled_gap_through_stop": {"entry_price": 100.0, "live_price": 98.4, "stop_loss": 98.5},
}


def _limit(**kw):
    base = dict(entry_type="limit", direction="bullish", trigger_price=100.0,
                entry_price=None, stop_loss=98.5, tp1=102.0, tp2=104.0,
                limit_cancel_level=101.0, status="CANCELLED")
    base.update(kw)
    return _plan(**base)


# --- follow channel ------------------------------------------------------------

@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_new_cancels_are_closed_other_and_render_invalidated(transition):
    event = PlanEvent("p1", transition, _DETAIL[transition])
    assert fn.notify_event_for(event) == "closed_other"
    assert fn.kind_for(event, "closed_other") is Kind.INVALIDATED


@pytest.mark.parametrize("transition, line", [
    ("cancelled_limit", "Paper plan update: AAPL long cancelled: limit cancelled before fill."),
    ("cancelled_gap_through_stop",
     "Paper plan update: AAPL long cancelled: gapped through the stop before fill."),
])
def test_the_follow_copy_names_the_reason(transition, line):
    assert fn.message_line(_limit(), "closed_other", transition, _DETAIL[transition]) == line


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_follow_copy_is_factual(transition):
    line = fn.message_line(_limit(), "closed_other", transition, _DETAIL[transition]).lower()
    assert not [phrase for phrase in fn.FORBIDDEN_PHRASES if phrase in line]


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_follow_embed_builds(transition):
    embed = fn.build_notify_embed(_limit(), "closed_other", transition, _DETAIL[transition])
    assert "INVALIDATED" in embed.title
    assert "cancelled:" in embed.push_text


def test_every_pending_cancel_event_announces_something():
    from swingbot.core.planning import plan_manager
    cancels = getattr(plan_manager, "PENDING_CANCEL_EVENTS", None)
    if cancels is None:              # V187-8 not merged into this branch yet
        cancels = frozenset({"cancelled_expired", "cancelled_invalidated",
                             "cancelled_risk_cap", *NEW_CANCELS})
    assert all(fn.notify_event_for(PlanEvent("p1", t, {})) is not None for t in cancels)


# --- outlook catalogue ---------------------------------------------------------

def test_the_new_codes():
    assert (se.LIMIT_CANCELLED, se.GAP_THROUGH_STOP) == ("limit_cancelled", "gap_through_stop")
    assert se.code_for("cancelled_limit") == se.LIMIT_CANCELLED
    assert se.code_for("cancelled_gap_through_stop") == se.GAP_THROUGH_STOP


def test_the_limit_cancel_message():
    assert se.in_session_message(_limit(), "cancelled_limit", _DETAIL["cancelled_limit"]) == (
        "Ran to 101.20, past the 101.00 cancel level, before the 100.00 limit filled")


def test_the_gap_through_stop_message():
    assert se.in_session_message(
        _limit(), "cancelled_gap_through_stop", _DETAIL["cancelled_gap_through_stop"]) == (
        "Touched the 100.00 limit at 98.40, already at or through the 98.50 stop; "
        "nothing opened")


def test_other_transitions_still_have_no_message():
    assert se.in_session_message(_limit(), "filled", {}) is None
    assert se.in_session_message(_limit(), "cancelled_expired", {}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_limit_cancels.py`
Expected: FAIL — `notify_event_for` returns `None` for both new events; `AttributeError: module 'swingbot.core.planning.session_expiry' has no attribute 'LIMIT_CANCELLED'`; `in_session_message` returns `None`.

- [ ] **Step 3: Write the implementation**

(a) `swingbot/core/planning/session_expiry.py` — in the module docstring, replace the first paragraph's first sentence:

```
Four cancellations happen DURING session D through the existing live transitions
(cancelled_invalidated, cancelled_risk_cap, and v187's cancelled_limit and
cancelled_gap_through_stop for a limit entry); `in_session_message` only words
them.
```

Then the constants (`:26-35`):

```python
NEVER_TRIGGERED = "never_triggered"
NO_SESSION_DATA = "no_session_data"
INVALIDATED = "invalidated"
RISK_CAP = "risk_cap"
LIMIT_CANCELLED = "limit_cancelled"        # v187 D3
GAP_THROUGH_STOP = "gap_through_stop"      # v187 D3

REASON_CODE = "reason_code"
REASON_MESSAGE = "reason_message"

_IN_SESSION_CODES = {"cancelled_invalidated": INVALIDATED, "cancelled_risk_cap": RISK_CAP,
                     "cancelled_limit": LIMIT_CANCELLED,
                     "cancelled_gap_through_stop": GAP_THROUGH_STOP}
```

Then replace `in_session_message` (`:126-133`) and add its two helpers above it:

```python
def _limit_cancelled_message(plan, detail: dict) -> str:
    return (f"Ran to {float(detail['live_price']):.2f}, past the "
            f"{float(detail['limit_cancel_level']):.2f} cancel level, before the "
            f"{float(plan.trigger_price):.2f} limit filled")


def _gap_through_stop_message(plan, detail: dict) -> str:
    return (f"Touched the {float(plan.trigger_price):.2f} limit at "
            f"{float(detail['live_price']):.2f}, already at or through the "
            f"{float(plan.stop_loss):.2f} stop; nothing opened")


#: v187 D3: the limit-entry cancellations, worded from their own detail keys.
_LIMIT_MESSAGES = {
    "cancelled_limit": _limit_cancelled_message,
    "cancelled_gap_through_stop": _gap_through_stop_message,
}


def in_session_message(plan, transition: str, detail: dict) -> str | None:
    """Words for the in-session cancellations; None for anything else."""
    if transition == "cancelled_invalidated":
        return (f"Traded {float(detail['live_price']):.2f} through the {float(plan.stop_loss):.2f} "
                "stop before triggering; the setup broke")
    if transition == "cancelled_risk_cap":
        return _risk_cap_message(plan, detail)
    builder = _LIMIT_MESSAGES.get(transition)
    return builder(plan, detail) if builder is not None else None
```

(b) `swingbot/commands/scanning/follow_notify.py` — three tables:

```python
_BY_TRANSITION: dict[str, str] = {
    "near_stop": "near_stop",
    "tp1_partial": "tp1",
    "cancelled_expired": "expired",
    "cancelled_invalidated": "closed_other",
    "cancelled_risk_cap": "closed_other",
    "cancelled_limit": "closed_other",               # v187 D3
    "cancelled_gap_through_stop": "closed_other",    # v187 D3
    "closed": "closed_other",
}
```

```python
# v187: the limit cancels are withdrawn before entry, like an invalidation;
# this channel is factual, so never the imperative CANCEL kind.
_CLOSED_OTHER_KIND = {
    "closed": Kind.EXITED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
    "cancelled_limit": Kind.INVALIDATED,
    "cancelled_gap_through_stop": Kind.INVALIDATED,
}
```

```python
_CANCEL_LABELS = {
    "cancelled_invalidated": "invalidated before entry",
    "cancelled_risk_cap": "risk cap reached",
    "cancelled_limit": "limit cancelled before fill",
    "cancelled_gap_through_stop": "gapped through the stop before fill",
}
```

The new comment above `_CLOSED_OTHER_KIND` must not contain the text `Kind.CANCEL` (the policy test greps the module source for it).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_limit_cancels.py`
Expected: PASS (13 tests).

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_session_expiry.py`
Expected: both PASS, unchanged (including `test_imperative_kinds_are_never_used` and `test_the_six_events_share_one_table`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/session_expiry.py swingbot/commands/scanning/follow_notify.py tests/commands/test_follow_notify_limit_cancels.py
git commit -m "feat(notify): follow notices and outlook codes for the limit cancels (v187 D3)"
```

### Task V187-13: Full suite, complexity gate, merge

**Model:** sonnet — runs the plan's one full suite, the gate and an end-to-end render check, then merges; no new logic.

**Spec:** § Testing ("The full suite runs once, as the plan's final task"); § Blast radius and rollback.

**Files:**
- none (no file is created or edited; the merge commit lands on `main`. `/close-out` bumps the bot patch and regenerates `version_history.json` afterwards).

**Interfaces:**
- Consumes: every task V187-1..V187-12, committed on branch `2026-10-23-v187-safety-hardening` in `.claude/worktrees/2026-10-23-v187-safety-hardening`.
- Produces: the merged branch on `main`.

- [ ] **Step 1: Every task is committed**

Run (in the worktree): `git status --short` and `git log --oneline main..HEAD`
Expected: a clean tree, and one or more scoped commits per task V187-1..V187-12. A missing task is implemented first; this task never covers for one.

- [ ] **Step 2: End-to-end render of the two new cancels**

The unit tests in V187-10 and V187-11 render each piece separately, so they can run in parallel. This one-off check (no file written) runs both new events through the real execution-feed path. A half-wired event fails here:

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
from unittest.mock import patch

from swingbot.core.planning.plan_manager import NOTICE_EVENTS, PENDING_CANCEL_EVENTS, PlanEvent
from swingbot.core.scanning import execution_embeds
from tests.planning.test_plan_engine_model import _plan

plan = _plan(entry_type="limit", trigger_price=100.0, stop_loss=98.5, tp1=102.0,
             limit_cancel_level=101.0, status="CANCELLED")
events = {
    "cancelled_limit": {"live_price": 101.2, "limit_cancel_level": 101.0},
    "cancelled_gap_through_stop": {"entry_price": 100.0, "live_price": 98.4, "stop_loss": 98.5},
}
with patch.object(execution_embeds, "_linked_trade", lambda plan_id: None), \
        patch.object(execution_embeds, "_sizing_snapshot", lambda entry, plan: None):
    for transition, detail in events.items():
        assert transition in PENDING_CANCEL_EVENTS and transition in NOTICE_EVENTS, transition
        embed = execution_embeds.build_instruction_embed(plan, PlanEvent("p1", transition, detail))
        assert embed.title == "🚫 ▲ LONG AAPL · CANCEL", embed.title
        print(transition, "|", embed.title, "|", embed.description.replace("\n", " / "))
print("OK")
PY
```

Expected: two lines, each with the title `🚫 ▲ LONG AAPL · CANCEL` and the V187-10 sentence ("Price ran past the limit's cancel level 101.00 at 101.20 …" and "Price touched the limit at 98.40, already at or through the stop 98.50 …"), then `OK`.

- [ ] **Step 3: The plan's one full-suite run**

If `/replicate-prod-db` has not run in this session, run it first (the suite hits Postgres). Then dispatch the `test-runner` subagent in the worktree with:

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed` and `0 xfailed`. The complexity gate runs inside `full`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

A failure is fixed in the task it belongs to (a scoped `fix:` commit) and re-run alone with `python scripts/dev/testrun.py file <test>`. The full suite is **not** re-run for it.

- [ ] **Step 4: The complexity gate on its own**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS. Two baseline entries are watched: `swingbot.core.planning.account:compute_position_size` (18, may only fall) and `swingbot.core.planning.plan_manager:PlanManager._on_event` (15, unchanged).

If the gate reports a function **below** its baseline, the part-1 refactor shrank it. Lock the gain in with `python scripts/dev/complexity_gate.py --update`, then commit it as `git add scripts/dev/complexity_baseline.json && git commit -m "chore(complexity): lock in v187 gains"`. A function **above** baseline is a defect in its task: fix it there.

- [ ] **Step 5: Merge to `main`**

Follow the `worktree-lifecycle` skill: another session may be on `main`. From the main tree:

```bash
git -C "E:/Documents/Private/Projects/Discord-Bot" status --short
git -C "E:/Documents/Private/Projects/Discord-Bot" merge --no-ff 2026-10-23-v187-safety-hardening -m "Merge v187: safety hardening (admin-only state commands, validated account settings, live limit entries)"
git -C "E:/Documents/Private/Projects/Discord-Bot" log --oneline -3
```

Expected: a clean `main` before the merge, then the merge commit at the top. No full suite after the merge (CLAUDE.md: it ran once, before the merge).

- [ ] **Step 6: Panel, then close-out**

On `main`, run `/panel risk-manager,staff-engineer,quant-engineer` over the merged diff (the spec's `Panel:` line), and apply or record its findings. Then run `/close-out` yourself (standing permission). It resolves the bot **patch** bump in `VERSION.json`, regenerates `version_history.json`, moves the spec and the plan's files to `implemented/`, and removes the worktree.

Deployment is outside this plan. Rollback is a plain redeploy of the previous image (spec § Blast radius), with one hazard: **no limit strategy may be unmasked before v187 is deployed, and none may stay unmasked across a rollback past v187**. Put that sentence in the close-out summary.
