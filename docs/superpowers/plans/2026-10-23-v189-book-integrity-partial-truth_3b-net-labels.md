# v189 — Book integrity and partial-trade truth: Implementation Plan, part 3b — net-R labels on plan-manager closes (V189-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D2 ("The status of a close with realized legs follows the net R sign": the `_close_runner` and time-exit callers) and § Testing (golden cases, the D2 label table).
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — Goal, Global Constraints, Contracts, Parallelisation and the task ledger bind this task.

**Why a separate file.** Part 3 ([`_3-plan-manager-transactions.md`](2026-10-23-v189-book-integrity-partial-truth_3-plan-manager-transactions.md), V189-8 and V189-9) reached the 1500-line cap with two tasks; V189-10 is the third task of the same part and the same file chain, split here rather than compressed. It runs **after V189-9** (same file `plan_manager.py`), and after V189-2 (`metrics.net_outcome`, the golden fixture) and V189-7 (`close_plan_trade(close_reason=)`).

**Worktree.** Every command runs from the worktree root `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth`. The autouse Postgres fixture makes every write below real.

---

# Phase C — Plan-manager transactions (continued)

### Task V189-10: Runner and time-exit closes labelled by net R

**Model:** opus — changes the recorded label of live closes (the measured win rate) and must keep single-leg labels byte-for-byte while proving the golden figures end to end.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (imports; new `_plan_outcome` before `_close_runner` `:1255`; `_close_runner` `:1255-1268`; `_close_time_exit` docstring `:1352-1354`)
- Modify: `tests/planning/test_plan_manager_poll_window.py` (docstring of `test_a_terminal_target_close_reaches_the_trade_log_as_a_win` only; its assertion still holds)
- Create: `tests/planning/test_plan_manager_net_labels.py`

**Interfaces:**
- Consumes: `swingbot.core.analytics.metrics.net_outcome(trade: dict) -> tuple[str, str | None]` (V189-2; reads `entry`, `stop_loss`, `direction`, `legs`, and `id` or `plan_id` for its warning), `SCRATCH_EPS_R`; the golden fixture `tests/analytics/golden_partial_trade.json` (V189-2, shape in the index § Contracts); `PlanManager._persist_terminal(plan, leg, status, close_reason=None)` (V189-8/9); `TradeLog.close_plan_trade(..., close_reason=)` (V189-7).
- Produces (index § Contracts "Plan manager"): `PlanManager._plan_outcome(self, plan) -> tuple[str, str | None]`; `_close_runner` persists `status, close_reason = self._plan_outcome(plan)`; `_close_time_exit`'s scaled-out branch inherits it (it already routes through `_close_runner`), its single-leg branch is unchanged.

**Why.** Spec D2. `_close_runner` labels every close after TP1 `win` when the reason starts with `tp1_` and `closed` otherwise, so a runner that gapped through the original stop (net < 0) is a `win`, and a time-exit runner close (reason `time_exit`) is `closed` and falls out of `win_rate` whatever it netted. The label now follows the unrounded net R: `> +0.01` win, `< −0.01` loss, inside the band `closed`/`scratch`, not computable or not finite `closed`/`unscored`. Single-leg closes (pre-TP1 stop, break-even scratch, stall exit, single-leg time exit) keep today's labels exactly. The backtest (`exit_sim_v2.py`) is not touched (Global Constraints); V189-2 pins the divergence.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_net_labels.py`:

```python
"""V189-10: a runner or time-exit close after TP1 is labelled by the sign of
its unrounded net R (metrics.net_outcome) -- the golden partial trade end to
end, and the D2 label table on both plan-manager close paths. Single-leg
closes keep their labels."""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.analytics import metrics
from swingbot.core.planning import time_exit as te
from swingbot.core.planning.plan_engine import PlanStatus, record_transition, runner_floor
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
AUCTION_ASOF = "2026-10-16T20:00:05+00:00"
GOLDEN = json.loads((Path(__file__).resolve().parents[1] / "analytics"
                     / "golden_partial_trade.json").read_text(encoding="utf-8"))
G = GOLDEN["trade"]
CASES = {case["name"]: case for case in GOLDEN["closed_cases"]}
LABELS = [(row["net_r"], row["status"], row["close_reason"]) for row in GOLDEN["label_table"]]


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    log = TradeLog()
    log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction=G["direction"],
        confidence_level=None, confidence_label=None, entry=G["entry"],
        stop_loss=G["stop_loss"], take_profit=G["tp1"], target2=G["tp2"], plan_id="p1")
    return log


def _golden_plan():
    plan = _plan(entry_type="market", direction=G["direction"], trigger_price=G["entry"],
                 entry_price=G["entry"], stop_loss=G["stop_loss"], tp1=G["tp1"],
                 tp2=G["tp2"], tp1_fraction=G["tp1_fraction"])
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return plan


def _manager(trade_log, prices):
    store = PlanStore()
    store.add(_golden_plan())
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _after_tp1(trade_log, runner_prices):
    """TP1 banked at exactly 110 (+2R on half), then ``runner_prices`` queued."""
    store, mgr = _manager(trade_log, [G["tp1"], *runner_prices])
    assert [e.transition for e in mgr.poll(now=SATURDAY)] == ["tp1_partial"]
    return store, mgr


def _runner_close(trade_log, exit_price) -> dict:
    """The live poll path: the runner's stop is hit and fills at the print."""
    store, mgr = _after_tp1(trade_log, [exit_price])
    closed = [e for e in mgr.poll(now=SATURDAY) if e.transition == "closed"]
    assert len(closed) == 1
    assert store.get("p1").status == PlanStatus.CLOSED
    return trade_log.trade_for_plan("p1")


def _time_exit_close(trade_log, exit_price) -> dict:
    """The time-exit path on a scaled-out plan, at the official auction price."""
    store, mgr = _after_tp1(trade_log, [])
    auction = te.AuctionClose(exit_price, te.OFFICIAL_BASIS, AUCTION_ASOF)
    events = mgr._close_time_exit(store.get("p1"), auction)
    assert [e.transition for e in events] == ["closed"]
    return trade_log.trade_for_plan("p1")


def _runner_exit_for(net_r: float) -> float:
    """The runner exit that nets ``net_r`` after the golden TP1 leg."""
    fraction, r1 = G["tp1_fraction"], G["tp1_leg"]["r"]
    runner_r = (net_r - fraction * r1) / (1 - fraction)
    return G["entry"] + runner_r * G["risk_per_share"]


def _assert_golden(record: dict, case: dict) -> None:
    assert (record["status"], record.get("close_reason")) == (case["status"], case["close_reason"])
    assert len(record["legs"]) == 2
    assert metrics.r_multiple(record) == pytest.approx(case["net_r"], abs=GOLDEN["tolerance"])
    per_share = case["realized_pnl_amount"] / G["shares"]
    assert record["realized_pnl_amount"] == pytest.approx(record["shares"] * per_share, abs=0.02)


# --- the golden partial trade ---------------------------------------------------------

def test_golden_floor_close_is_a_win(trade_log):
    floor = runner_floor(G["entry"], G["tp1"])
    assert floor == pytest.approx(CASES["floor"]["runner_exit"])
    record = _runner_close(trade_log, floor)
    assert record["legs"][-1]["reason"] == "tp1_runner_be"
    _assert_golden(record, CASES["floor"])


def test_golden_gap_below_the_original_stop_is_a_loss(trade_log):
    record = _runner_close(trade_log, CASES["gap"]["runner_exit"])
    _assert_golden(record, CASES["gap"])          # TP1 was touched; the net is -0.20R


def test_golden_time_exit_after_tp1_is_a_win(trade_log):
    record = _time_exit_close(trade_log, CASES["time_exit"]["runner_exit"])
    assert record["legs"][-1]["reason"] == te.TIME_EXIT_REASON
    _assert_golden(record, CASES["time_exit"])    # was "closed" before v189


# --- the D2 label table on both plan-manager close paths --------------------------------

@pytest.mark.parametrize("close", [_runner_close, _time_exit_close], ids=["runner", "time_exit"])
@pytest.mark.parametrize("net_r, status, close_reason", LABELS,
                         ids=[f"net{row[0]:+}" for row in LABELS])
def test_the_label_follows_the_net_r_sign(trade_log, close, net_r, status, close_reason):
    record = close(trade_log, _runner_exit_for(net_r))
    assert (record["status"], record.get("close_reason")) == (status, close_reason)
    assert metrics.r_multiple(record) == pytest.approx(net_r, abs=GOLDEN["tolerance"])


# --- single-leg closes keep today's labels ----------------------------------------------

def test_a_pre_tp1_stop_is_still_a_loss(trade_log):
    store, mgr = _manager(trade_log, [94.0])
    assert [e.transition for e in mgr.poll(now=SATURDAY)] == ["closed"]
    record = trade_log.trade_for_plan("p1")
    assert (record["status"], record.get("close_reason")) == ("loss", None)


def test_a_single_leg_time_exit_keeps_its_closed_label(trade_log):
    store, mgr = _manager(trade_log, [])
    auction = te.AuctionClose(101.0, te.OFFICIAL_BASIS, AUCTION_ASOF)
    events = mgr._close_time_exit(store.get("p1"), auction)
    assert [e.transition for e in events] == ["closed"]
    record = trade_log.trade_for_plan("p1")
    assert (record["status"], record.get("close_reason")) == ("closed", None)


# --- the outcome helper -------------------------------------------------------------------

def _scaled_out(**kw):
    plan = _golden_plan()
    plan.legs_realized = [dict(G["tp1_leg"]), {"fraction": 0.5, "exit_price": 115.0,
                                               "r": 3.0, "reason": "manual"}]
    for key, value in kw.items():
        setattr(plan, key, value)
    return plan


def test_plan_outcome_labels_a_scaled_out_plan_by_net_r():
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    assert mgr._plan_outcome(_scaled_out()) == ("win", None)          # net +2.5R


def test_a_nan_leg_is_unscored_with_a_warning(caplog):
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    plan = _scaled_out()
    plan.legs_realized[1] = {"fraction": 0.5, "exit_price": math.nan, "r": math.nan,
                             "reason": "manual"}
    caplog.set_level(logging.WARNING)
    assert mgr._plan_outcome(plan) == ("closed", "unscored")
    assert "p1" in caplog.text


def test_a_plan_with_no_risk_basis_is_unscored():
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    assert mgr._plan_outcome(_scaled_out(stop_loss=G["entry"])) == ("closed", "unscored")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_net_labels.py`
Expected: FAIL — `test_golden_gap_below_the_original_stop_is_a_loss` gets `("win", None)`, `test_golden_time_exit_after_tp1_is_a_win` gets `("closed", None)`, the scratch rows of the label table get `win`/`closed` without `scratch`, and the three helper tests fail with `AttributeError: 'PlanManager' object has no attribute '_plan_outcome'`. The two single-leg tests already PASS (they pin what must not change).

- [ ] **Step 3: `_plan_outcome` and the runner close**

In `swingbot/core/planning/plan_manager.py`, add to the imports (beside `from swingbot.core.analytics import runner_path as rp`):

```python
from swingbot.core.analytics.metrics import net_outcome
```

(`metrics` imports only the standard library and numpy, so this adds no cycle; confirm with `python -c "import swingbot.core.planning.plan_manager"`.)

Directly above `_close_runner` add:

```python
    def _plan_outcome(self, plan: TradePlanV2) -> tuple[str, str | None]:
        """The trade status and close_reason of a close with two or more
        realized legs (v189 D2): the sign of the unrounded blended net R via
        metrics.net_outcome -- win above +SCRATCH_EPS_R, loss below its
        negative, closed/scratch inside, closed/unscored when the net cannot
        be computed. Never "TP1 was touched, so win". Live only: the backtest
        keeps its event labels (exit_sim_v2)."""
        return net_outcome({"plan_id": plan.plan_id, "entry": plan.entry_price,
                            "stop_loss": plan.stop_loss, "direction": plan.direction,
                            "legs": [dict(leg) for leg in plan.legs_realized]})
```

In `_close_runner` replace

```python
        persisted = self._persist_terminal(plan, leg, "win" if reason.startswith("tp1_") else "closed")
```

with

```python
        # v189 D2: labelled by the net of every realized leg (the runner leg
        # was appended above), not by the reason's "tp1_" prefix.
        status, close_reason = self._plan_outcome(plan)
        persisted = self._persist_terminal(plan, leg, status, close_reason)
```

- [ ] **Step 4: Document the time-exit path**

`_close_time_exit` needs no code change: its scaled-out branch (`if plan.legs_realized:`) already calls `_close_runner`, and its single-leg branch keeps `"loss" if r < 0 else "closed"` (spec D2: single-leg trades are unchanged). Replace its docstring with:

```python
        """Persist the paper close of whatever is still open at the official
        auction price, through the one terminal path. A scaled-out plan closes
        its runner through _close_runner and is labelled by net R (v189 D2);
        a plan with no realized leg keeps the single-leg label."""
```

In `tests/planning/test_plan_manager_poll_window.py`, replace the last sentence of `test_a_terminal_target_close_reaches_the_trade_log_as_a_win`'s docstring, `The runner then closes on its own floor like any other runner, and still reaches the trade log as a win (close_plan_trade's reason -> status mapping treats every "tp1_..." reason as a win).`, with `The runner then closes on its own floor like any other runner, and still reaches the trade log as a win: since v189 the label is the net R of both legs (+2.2R on half, +1.2R on half, net +1.7R), not the "tp1_" reason.`

- [ ] **Step 5: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_net_labels.py`
Expected: PASS (18 tests, 0 failed, 0 xfailed).

- [ ] **Step 6: Run what the diff reaches**

Run each (all must PASS unchanged):
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_poll_window.py`
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`
`python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py`
`python scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py`
`python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`
`python scripts/dev/testrun.py file tests/analytics/test_net_outcome.py`
`python scripts/dev/testrun.py file tests/analytics/test_golden_partial_trade_metrics.py`

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed. A test that pins `win` for a runner close with a **negative** net R, or `closed` for a positive time-exit runner close, pins the D2 bug: report it to the controller with the test name rather than changing `_plan_outcome`. The `_on_event` fallback mapping for non-persisted closes is deliberately unchanged (index clarification 11).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_close_runner` drops by one (the inline `if/else` is gone); `_plan_outcome` is 2.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_net_labels.py tests/planning/test_plan_manager_poll_window.py
git commit -m "feat(planning): runner and time-exit closes after TP1 are labelled by net R (v189 V189-10)"
```
