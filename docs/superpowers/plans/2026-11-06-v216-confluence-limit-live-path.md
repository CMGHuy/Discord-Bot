# v216 — Confluence limit entry: live path (carried over from v212 part 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch (arm branch inert while `CONFLUENCE_LIMIT_ENTRY_F = 0`)
**Edge:** expectancy — the live half of v212's limit entry; no lift of its own.
**Screen:** exempt (post-signal) — inherited from v212
**Spec:** [v216 — Confluence limit entry: live path](../specs/2026-11-06-v216-confluence-limit-live-path.md)
**Gate:** implement **only after v212 records a Stage 3 PASS**; on any other v212 verdict this plan moves to `no-lift/` unimplemented.
**Depends on:** v212's V212-2 (`limit_entry_f`, `to_limit_plan`) and V212-4 (`limit_entry_rule.bar_outcome`, `is_arm_limit`) on `main`. Global Constraints: v212 index [`2026-11-06-v212-confluence-limit-entry_0-index.md`](2026-11-06-v212-confluence-limit-entry_0-index.md) § Global Constraints apply to every task here.
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md` (§3e live limit step, §3f heat, §3h alert text)
**Worktree:** `.claude/worktrees/2026-11-06-v216-confluence-limit-live-path` (create it from `main` before V216-1; `docs/claude/document-lifecycle.md`).

Written as v212 plan part 2 (V212-6..V212-10 with V212-9b) and carried over
renumbered when v212 was cut at the 20-task cap: V212-6→V216-1, 7→2, 8→3,
9→4, 9b→5, 10→6. Tasks: the live arm branch of the resting limit (shared
fill rule, gap-through-stop filled and stopped in one step, planned risk
cap, marketable at alert), the heat re-check at fill, registration of the
two new events in every routing table, the alert and follow-up text, and the
admin Levels mapping. Live code reads the root `market_data/` cache through
`plan_manager`'s existing `daily_frame_fn`; nothing here reads
`data/backtest_cache*`. Tasks that touch the plan store or the trade log run
`/replicate-prod-db` first (shared `swing-db`, port 56789). Every task's
verification is the narrow run; no task runs the full suite.

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| C live | V216-1 → V216-2 → V216-3 → V216-4 → V216-5; V216-6 any time | `plan_manager.py` (1, 2), C `edge/fill_heat.py` (2), event tables (3), `instructions.py`/`session_expiry.py` (4), `plan_table.py`/`lifecycle_embeds.py` (5), `levels-block.ts` (6) | 1 needs v212's V212-4 on `main`; 2 edits `plan_manager.py` after 1; 3 registers the events 1 and 2 emit; 4 writes their text and the tables 3 lists; 6 is frontend-only, no contract |

**Live semantics fixed here (spec rule 6, live column).** A poll is a
one-print bar (`high = low = price`) handed to `limit_entry_rule.bar_outcome`
with `open_` chosen by `PlanManager._arm_open`:

| Situation | `open_` passed | Outcome |
|---|---|---|
| A session after the alert session, today's daily bar in hand | that bar's `Open` | open at/through stop → fill at the open and close at the open (`filled_stopped_gap`); open at/through L → fill at the open; else the tick decides |
| Open unknown (alert session, or no bar for today) and the tick at/through the stop | the tick | the first quote at or beyond the stop stands in for the open: fill and close at that price in one step |
| Alert session, first poll (`plan.first_seen_price is None`), tick at/through L | the tick | marketable at alert: fill at the quote, `"marketable_at_alert": True` |
| Anything else | `None` | trade-through (`price <= L − tick`) fills at L; TP1 printed (inclusive) cancels |

With `INTRADAY_RTH_ONLY` on, an arm limit is stepped only inside the regular
session (a broker's resting DAY/GTC limit does not fill pre-market); outside
it the step returns `[]` (it rests, and is never `cancelled_invalidated`).
Expiry stays the existing `bar_count_fn` + `pending_expired` path:
`expiry_bars = 3` keeps the plan through the close of the 3rd session after
the alert session.

# Phase C — live path

### Task V216-1: Live: arm branch in `_step_limit` (shared rule, `filled_stopped_gap`, planned risk-cap, marketable at alert)

**Model:** opus — rewires the live resting-order step under the incident-hardened fill/persist path; a slip silently cancels realised losses or double-books a trade.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (import; `_arm_regular`, `_through_limit`, `_risk_basis` module helpers near `_opens_beyond_tp1` ~line 232; `_step_pending` passes `now` to `_step_limit` ~line 1209; `_step_limit` ~1226 gains `now=None`, the arm dispatch and an extracted `_cancel_limit`; new `_step_arm_limit`, `_arm_open`, `_marketable_at_alert`, `_session_open_for`, `_fill_and_stop_gap` after `_step_limit`; `_fill_pending` ~1260)
- Create: `tests/planning/test_plan_manager_arm_limit.py`

**Interfaces:**
- Consumes: V212-4 `limit_entry_rule.is_arm_limit(plan) -> bool`, `bar_outcome(plan, *, open_, high, low, touch=False) -> BarOutcome(kind, fill, gap_stopped)`; V212-2 `TradePlanV2.limit_entry_f`; existing `lifecycle.at_or_beyond_stop`, `PlanManager._persist_fill`, `_persist_terminal`, `_cancel_risk_cap`, `_frame_or_none`, `plan_stop_ceiling`, `session_date`, `is_regular_session`, `US_MARKET_TZ`.
- Produces (consumed by V216-2, V216-3, V216-4):
  - event `"filled_stopped_gap"`, detail `{"entry_price": fill, "exit_price": fill, "live_price": price, "stop_loss": plan.stop_loss, "reason": "filled_stopped_gap", "leg": {"fraction": 1.0, "exit_price": fill, "r": 0.0, "reason": "loss"}}` plus `"trade_id"` when a placeholder was moved. (`reason` is one key beyond the ledger's list, additive, so follow_notify's `_stopped_copy` can word it in V216-3.) The plan ends `CLOSED`, history `[..., ACTIVE "limit_fill", CLOSED "loss" with extra {"exit": "filled_stopped_gap"}]`; the trade closes with status `"loss"`.
  - `"filled"` detail gains `"marketable_at_alert": True` only on the marketable-at-alert fill.
  - `PlanManager._fill_pending(self, plan, fill, price, reason, *, extra: dict | None = None)` — `extra` merges into the `filled` detail; the risk cap reads `_risk_basis(plan, fill)` (`plan.trigger_price` for an arm limit, else `fill`, so every other plan is byte-identical).
  - `PlanManager._fill_and_stop_gap(self, plan, fill: float, price: float) -> list[PlanEvent]` and `_fill_pending` are the two places V216-2 inserts the heat guard.
  - `PlanManager._session_open_for(self, plan, now) -> float | None`.

- [ ] **Step 0: Sync the replica**

Run `/replicate-prod-db` (shared `swing-db`, port 56789; `.env` credentials never printed). The tests below write through `PlanStore` and `TradeLog`.

- [ ] **Step 1: Write the failing test** `tests/planning/test_plan_manager_arm_limit.py`

```python
"""v212 rule 6, live: an arm limit (limit_entry_f set) steps through the shared
bar_outcome rule. A gap through the stop fills and closes at the open in one
step (filled_stopped_gap, a realised ~0R loss), never cancelled_gap_through_stop;
the first quote at or beyond the stop stands in for an unknown open; TP1 cancel
is inclusive; a marketable order at alert fills at the quote; the risk cap
reads the planned |L - stop|. Out-of-scope limits keep today's path."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

ET = ZoneInfo("America/New_York")
ALERT = datetime(2026, 11, 6, 11, 0, tzinfo=ET)       # Fri, the alert session
NEXT = datetime(2026, 11, 9, 10, 0, tzinfo=ET)        # Mon, first session after it
PRE = datetime(2026, 11, 9, 8, 0, tzinfo=ET)          # Mon, before the open

LEVELS = {
    "bullish": dict(trigger_price=98.5, stop_loss=96.75, tp1=104.0, limit_cancel_level=104.0),
    "bearish": dict(trigger_price=101.5, stop_loss=103.26, tp1=96.0, limit_cancel_level=96.0),
}
#: ticks / opens per side, named by what they do to the resting limit
PX = {
    "bullish": dict(through=98.4, touch=98.5, above=99.0, gap_l=98.0, gap_stop=96.0,
                    under_stop=96.5, tp1=104.0),
    "bearish": dict(through=101.6, touch=101.5, above=101.0, gap_l=102.0, gap_stop=104.0,
                    under_stop=103.5, tp1=96.0),
}
SIDES = pytest.mark.parametrize("side", ["bullish", "bearish"])


@pytest.fixture(autouse=True)
def _plain(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _arm(side="bullish", **kw):
    base = dict(source="confluence", strategy="S/R Confluence", entry_type="limit",
                direction=side, expiry_bars=3, tp2=None, created_at="2026-11-06",
                limit_strict_fill=True, limit_entry_f=0.5, **LEVELS[side])
    base.update(kw)
    return _plan(**base)


def _bars(open_today, day="2026-11-09"):
    """Closed bars, then the session bar for `day` whose Open is `open_today`."""
    idx = pd.to_datetime(["2026-11-05", "2026-11-06", day]).unique()
    n = len(idx)
    return pd.DataFrame({"Open": [100.0] * (n - 1) + [open_today], "High": [100.0] * n,
                         "Low": [100.0] * n, "Close": [100.0] * n, "Volume": [1e6] * n},
                        index=idx)


def _step(plan, price, now, **mgr_kw):
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, lambda ticker: price, **mgr_kw)
    events = mgr._step_pending(plan, price, now)
    return store.get(plan.plan_id), events


def _reasons(plan):
    return [h.get("reason") for h in plan.status_history]


@SIDES
def test_a_trade_through_fills_at_the_limit(side):
    plan, events = _step(_arm(side), PX[side]["through"], NEXT)
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": LEVELS[side]["trigger_price"],
                                "live_price": PX[side]["through"]}
    assert plan.status == PlanStatus.ACTIVE and _reasons(plan)[-1] == "limit_fill"


@SIDES
def test_a_bare_touch_does_not_fill(side):
    plan, events = _step(_arm(side), PX[side]["touch"], NEXT)
    assert events == [] and plan.status == PlanStatus.PENDING


@SIDES
def test_an_open_through_the_limit_fills_at_the_open(side):
    frame = _bars(PX[side]["gap_l"])
    plan, events = _step(_arm(side), PX[side]["above"], NEXT, daily_frame_fn=lambda t: frame)
    assert [e.transition for e in events] == ["filled"]
    assert plan.entry_price == PX[side]["gap_l"]


@SIDES
def test_an_open_through_the_stop_fills_and_stops_at_the_open(side):
    frame = _bars(PX[side]["gap_stop"])
    plan, events = _step(_arm(side), PX[side]["above"], NEXT, daily_frame_fn=lambda t: frame)
    fill = PX[side]["gap_stop"]
    assert [e.transition for e in events] == ["filled_stopped_gap"]
    d = events[0].detail
    assert (d["entry_price"], d["exit_price"], d["stop_loss"]) == (fill, fill, LEVELS[side]["stop_loss"])
    assert d["reason"] == "filled_stopped_gap"
    assert d["leg"] == {"fraction": 1.0, "exit_price": fill, "r": 0.0, "reason": "loss"}
    assert plan.status == PlanStatus.CLOSED and plan.entry_price == fill
    assert _reasons(plan)[-2:] == ["limit_fill", "loss"]
    assert "gap_through_stop" not in _reasons(plan)


@SIDES
def test_the_first_quote_through_the_stop_stands_in_for_an_unknown_open(side):
    plan, events = _step(_arm(side), PX[side]["under_stop"], NEXT)      # no daily_frame_fn
    assert [e.transition for e in events] == ["filled_stopped_gap"]
    assert events[0].detail["exit_price"] == PX[side]["under_stop"]
    assert plan.status == PlanStatus.CLOSED


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def test_the_gap_stop_moves_and_closes_the_placeholder_as_a_loss(tlog):
    plan = _arm()
    trade_id = tlog.log_trade(ticker=plan.ticker, strategy=plan.strategy, horizon_key="4w",
                              direction="bullish", confidence_level=None, confidence_label=None,
                              entry=98.5, stop_loss=96.75, take_profit=104.0,
                              plan_id=plan.plan_id)
    frame = _bars(96.0)
    _, events = _step(plan, 97.0, NEXT, daily_frame_fn=lambda t: frame, trade_log=tlog)
    trades = [t for t in tlog.get_trades(status=None, limit=None)
              if t.get("plan_id") == plan.plan_id]
    assert len(trades) == 1
    assert (trades[0]["status"], trades[0]["entry"], trades[0]["exit_price"]) == ("loss", 96.0, 96.0)
    assert events[0].detail["trade_id"] == trade_id


@SIDES
def test_a_tp1_print_cancels_inclusively(side):
    plan, events = _step(_arm(side), PX[side]["tp1"], NEXT)
    assert [e.transition for e in events] == ["cancelled_limit"]
    assert events[0].detail == {"live_price": PX[side]["tp1"],
                                "limit_cancel_level": LEVELS[side]["tp1"]}
    assert _reasons(plan)[-1] == "limit_cancelled"


@SIDES
def test_a_marketable_order_at_alert_fills_at_the_quote(side):
    plan, events = _step(_arm(side), PX[side]["gap_l"], ALERT)
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": PX[side]["gap_l"],
                                "live_price": PX[side]["gap_l"], "marketable_at_alert": True}


def test_a_later_poll_in_the_alert_session_fills_at_the_limit():
    plan, events = _step(_arm(first_seen_price=99.5), 98.0, ALERT)
    assert events[0].detail == {"entry_price": 98.5, "live_price": 98.0}


def test_the_alert_sessions_own_open_is_never_used():
    frame = _bars(98.0, day="2026-11-06")
    plan, events = _step(_arm(first_seen_price=99.5), 99.0, ALERT,
                         daily_frame_fn=lambda t: frame)
    assert events == [] and plan.status == PlanStatus.PENDING


def test_outside_the_regular_session_an_arm_limit_rests(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    plan, events = _step(_arm(), 96.0, PRE)                     # through the stop, pre-market
    assert events == [] and plan.status == PlanStatus.PENDING


def test_the_risk_cap_reads_the_planned_distance_not_the_gap_fill():
    # L - stop = 2.5% (past the 2% ceiling); from the 97.6 open it would read 0.1%
    plan, events = _step(_arm(trigger_price=100.0, stop_loss=97.5), 99.0, NEXT,
                         daily_frame_fn=lambda t: _bars(97.6))
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail["entry_price"] == 100.0


def test_an_out_of_scope_limit_keeps_the_gap_through_stop_cancel():
    plan, events = _step(_arm(limit_entry_f=None), 96.0, NEXT)
    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]


@pytest.mark.parametrize("bars,expected", [(3, []), (4, ["cancelled_expired"])])
def test_the_limit_lives_through_the_third_session(bars, expected):
    plan, events = _step(_arm(), 99.0, NEXT, bar_count_fn=lambda t, c: bars)
    assert [e.transition for e in events] == expected
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_arm_limit.py`
Expected: FAIL — arm plans still take the v187 branch (`cancelled_gap_through_stop` where `filled_stopped_gap` is expected), the open, marketable and risk-basis tests fail, and `_step_pending` passes no `now` to the limit step.

- [ ] **Step 3: Implement in `swingbot/core/planning/plan_manager.py`**

Import `from swingbot.core.planning.limit_entry_rule import bar_outcome, is_arm_limit`.

Module helpers (a few lines each):
- `_arm_regular(now) -> bool` — `is_regular_session(now) if config.INTRADAY_RTH_ONLY else True` (the switch `poll()` uses for `regular`).
- `_through_limit(plan, price) -> bool` — long `price <= plan.trigger_price`, short `price >= plan.trigger_price`.
- `_risk_basis(plan, fill) -> float` — `plan.trigger_price if is_arm_limit(plan) else fill`.

`_step_pending`: the one call becomes `self._step_limit(plan, price, now)` (no new branch; complexity unchanged).

`_step_limit(self, plan, price, now=None)`: first statement `if is_arm_limit(plan): return self._step_arm_limit(plan, price, now)`. The existing `limit_cancelled` block moves verbatim into `_cancel_limit(self, plan, price) -> list[PlanEvent]` (same transition, reason, event and detail), called from both branches. The docstring gains one sentence: v212 arm limits take the shared `bar_outcome` rule instead.

`_step_arm_limit(self, plan, price, now) -> list[PlanEvent]` — never returns `None`, so `pending_invalidated` never runs for an arm limit:

```python
if not _arm_regular(now):
    return []                                   # a resting order does not fill pre/post-market
open_, marketable = self._arm_open(plan, price, now)
outcome = bar_outcome(plan, open_=open_, high=price, low=price)
if outcome.kind == "cancel":
    return self._cancel_limit(plan, price)
if outcome.kind == "none":
    return []
if outcome.gap_stopped:
    return self._fill_and_stop_gap(plan, outcome.fill, price)
return self._fill_pending(plan, outcome.fill, price, "limit_fill",
                          extra={"marketable_at_alert": True} if marketable else None)
```

`_arm_open(self, plan, price, now) -> tuple[float | None, bool]` — the table in this part's header, in order: `_session_open_for(plan, now)` not None → `(open, False)`; `at_or_beyond_stop(plan, price)` → `(price, False)`; `_marketable_at_alert(plan, price, now)` → `(price, True)`; else `(None, False)`.

`_marketable_at_alert(self, plan, price, now) -> bool` — `session_date(now) == str(plan.created_at)[:10] and plan.first_seen_price is None and _through_limit(plan, price)`.

`_session_open_for(self, plan, now) -> float | None` — None when `session_date(now) <= str(plan.created_at)[:10]` (the alert session's open came before the alert), when `self._frame_or_none(self.daily_frame_fn, plan.ticker)` is None or empty, when the frame's last index date (tz-aware: `tz_convert(US_MARKET_TZ)` first) is not `session_date(now)`, or when that bar's `Open` is not finite and positive; else that `Open` as a float. Docstring: reads root `market_data/` through `daily_frame_fn`; NO-LOOKAHEAD, only today's opening print.

`_fill_and_stop_gap(self, plan, fill, price) -> list[PlanEvent]` — first the planned risk check (`planned_loss_pct(plan.trigger_price, plan.stop_loss) > plan_stop_ceiling(plan)` → `return self._cancel_risk_cap(plan, plan.trigger_price)`); then `plan.entry_price = fill`, `record_transition(plan, ACTIVE, reason="limit_fill", at=self._now())`, `trade_id = self._persist_fill(plan, fill)`, `record_transition(plan, CLOSED, reason="loss", at=self._now(), extra={"exit": "filled_stopped_gap"})`, `self._persist_terminal(plan, leg, "loss")`, and the one event from the Interfaces block. Docstring: spec rule 6 as corrected 2026-11-06; fill and close are two transactions in one step; if the close write fails twice (`PlanPersistFailed`) the stored plan is ACTIVE at the open and the next poll's `_step_active` stops it, so the loss is never dropped. `_on_event` has no branch for this transition (the step already wrote both), so the placeholder is moved, then closed, never discarded.

`_fill_pending(..., *, extra=None)`: `basis = _risk_basis(plan, fill)`; the cap check and `_cancel_risk_cap` take `basis`; `detail.update(extra)` when given. For every non-arm plan `basis == fill`: byte-identical.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_arm_limit.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_limit_entry.py
python scripts/dev/testrun.py file tests/planning/test_limit_entry.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS (the v187 file proves out-of-scope limits unchanged); no complexity violation (`_step_pending` stays 11; `_step_limit`, `_fill_pending`, `_step_arm_limit` stay single digits).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_arm_limit.py
git commit -m "feat(v216): live arm limit -- shared fill rule, gap-through-stop filled and stopped, planned risk cap (V216-1)"
```

### Task V216-2: Heat at fill: pure check, `fill_guard`, `cancelled_heat_at_fill`

**Model:** opus — a new risk gate on the live fill path (spec rule 8): wrong book, wrong risk or a guard that fails closed would cancel real fills or let stacked limits breach the caps.

**Files:**
- Create: `swingbot/core/edge/fill_heat.py`
- Modify: `swingbot/core/planning/plan_manager.py` (`__init__(..., fill_guard=None)`; `_heat_cap`, `_cancel_heat_at_fill` beside `_cancel_risk_cap` ~line 1275; the guard call in `_fill_pending` and `_fill_and_stop_gap` from V216-1; `_fill_frames` module helper and `_manager()` wiring ~line 2117)
- Create: `tests/edge/test_fill_heat.py`
- Create: `tests/planning/test_plan_manager_heat_at_fill.py`

**Interfaces:**
- Consumes: V212-4 `is_arm_limit`; V216-1 `PlanManager._fill_pending(..., *, extra=None)`, `_fill_and_stop_gap(plan, fill, price)`; existing `heat.heat_check(open_trades, balance, candidate_risk_pct, cap_pct=None)`, `heat.sector_check(open_trades, balance, candidate_ticker, candidate_risk_pct, sectors, cap_pct=None)`, `correlation.cluster_exposure(open_trades, candidate_ticker, dfs, balance, *, ...)`, `correlation.cluster_check(exposure, candidate_risk_pct, cap_pct=None)`, `account.compute_position_size(entry, stop_loss, account_cfg, *, ticker=None, ...) -> dict | None` (keys `risk_amount`, `capped`), `account.load_account_config()` (keys `balance`, `risk_pct`, `max_open_positions`), `universe.sector_map(name) -> dict`, `TradeLog.get_trades(status="open", limit=None)`.
- Produces:
  - `fill_heat.heat_at_fill_reason(*, open_trades: list, balance: float, risk_pct: float, ticker: str, sectors: dict | None, cluster_chk: dict | None, max_open: int | None) -> str | None` — the first breached cap in the order `"heat"`, `"sector"` (only with a non-empty `sectors`), `"cluster"` (only with a `cluster_chk` whose `allowed` is False), `"max_open"` (only with `max_open` not None and `len(open_trades) >= max_open`); None when all clear.
  - `fill_heat.CAP_WORDS = {"heat": "portfolio heat", "sector": "sector heat", "cluster": "correlated heat", "max_open": "max open positions"}` — the one wording of each reason, read by the V216-3 text rows.
  - `fill_heat.make_fill_guard(trade_log, account_cfg_fn, frames_fn, *, sectors_fn=None) -> Callable[[TradePlanV2, float], str | None]` — `frames_fn(tickers: list[str]) -> dict[str, DataFrame]`; `sectors_fn() -> dict` defaults to the scan universe's `sector_map`.
  - `PlanManager.fill_guard` attribute; event `"cancelled_heat_at_fill"`, detail `{"entry_price": fill, "live_price": price, "cap": <reason>}`; status `CANCELLED`, reason `"heat_at_fill"`, extra `{"entry_price": fill, "cap": <reason>}`.

**Rule (spec rule 8, "the same checks again").** The book is the open trades exactly as the alert-time check reads them (`scan_run.py` ~1210: `trade_log.get_trades(status="open", limit=None)`) minus this plan's own placeholder (`plan_id == plan.plan_id`), so a pending limit reserves nothing beyond what the alert-time check already counts. The candidate's risk is the fill's actual risk: `compute_position_size(fill, plan.stop_loss, cfg, ticker=plan.ticker)["risk_amount"] / balance * 100` (notional caps applied), falling back to `cfg["risk_pct"]` when sizing returns None or the balance is not positive. The cluster check passes no `sectors` (as at alert time); the sector check uses the universe map. A guard that raises fails **open** (the fill stands), logged through `swallowed` — a data read failure must not cancel a broker fill. Arm limits only: every other plan never calls the guard.

- [ ] **Step 0: Sync the replica**

Run `/replicate-prod-db` (the plan-manager test writes through `PlanStore`).

- [ ] **Step 1: Write the failing tests**

`tests/edge/test_fill_heat.py`:

```python
"""v212 rule 8: heat, sector, cluster and max-open re-checked at fill."""
import pytest

from swingbot import config
from swingbot.core.edge import fill_heat
from swingbot.core.edge.fill_heat import heat_at_fill_reason, make_fill_guard
from tests.planning.test_plan_engine_model import _plan


@pytest.fixture(autouse=True)
def _caps(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0, raising=False)
    monkeypatch.setattr(config, "SECTOR_HEAT_CAP_PCT", 3.0, raising=False)


def _trade(ticker, risk_pct, plan_id=None):
    return {"ticker": ticker, "risk_pct": risk_pct, "plan_id": plan_id, "horizon_key": "4w"}


def _reason(book, **kw):
    base = dict(open_trades=book, balance=10_000.0, risk_pct=1.0, ticker="XYZ",
                sectors=None, cluster_chk=None, max_open=None)
    base.update(kw)
    return heat_at_fill_reason(**base)


def test_an_empty_book_clears_every_cap():
    assert _reason([], max_open=30, sectors={"XYZ": "Tech"},
                   cluster_chk={"allowed": True}) is None


def test_heat_breaches_first():
    book = [_trade("A", 2.5), _trade("B", 2.8)]                     # 5.3 open, cap 6.0
    assert _reason(book) == "heat"
    assert _reason(book, risk_pct=0.7) is None                      # exactly at the cap passes


def test_sector_only_with_a_map():
    book = [_trade("A", 2.5)]
    assert _reason(book, sectors={"A": "Tech", "XYZ": "Tech"}) == "sector"
    assert _reason(book, sectors=None) is None
    assert _reason(book, sectors={"A": "Tech", "XYZ": "Energy"}) is None


def test_cluster_reads_the_given_check():
    assert _reason([], cluster_chk={"allowed": False}) == "cluster"


def test_every_reason_has_its_words():
    assert set(fill_heat.CAP_WORDS) == {"heat", "sector", "cluster", "max_open"}


@pytest.mark.parametrize("n,expected", [(2, None), (3, "max_open")])
def test_max_open_counts_the_book(n, expected):
    assert _reason([_trade(f"T{i}", 0.1) for i in range(n)], max_open=3) == expected


class _Log:
    def __init__(self, trades):
        self.trades = trades

    def get_trades(self, status=None, limit=None):
        assert (status, limit) == ("open", None)
        return list(self.trades)


def _guard(trades, monkeypatch, risk_amount=100.0, sectors=None):
    """A guard over `trades` on a 10k book; sizing pinned to `risk_amount`
    dollars (None = no size) so opex/edge multipliers cannot move the test."""
    sized = None if risk_amount is None else {"risk_amount": risk_amount, "capped": False}
    monkeypatch.setattr(fill_heat.account, "compute_position_size", lambda *a, **k: sized)
    cfg = {"balance": 10_000.0, "risk_pct": 1.0, "max_open_positions": 30}
    return make_fill_guard(_Log(trades), lambda: cfg, lambda tickers: {},
                           sectors_fn=lambda: sectors or {})


PLAN = dict(plan_id="p1", ticker="XYZ", trigger_price=98.5, stop_loss=96.75)


def test_the_guard_drops_the_plans_own_placeholder(monkeypatch):
    book = [_trade("XYZ", 1.0, plan_id="p1"), _trade("A", 4.5)]     # 5.5 with own, 4.5 without
    assert _guard(book, monkeypatch)(_plan(**PLAN), 98.5) is None


def test_the_guard_reads_the_fills_actual_risk(monkeypatch):
    book = [_trade("A", 5.5)]                                        # 0.5% left under the cap
    assert _guard(book, monkeypatch, risk_amount=100.0)(_plan(**PLAN), 98.5) == "heat"
    # a notional cap cut the size to 0.3% of the book: the fill fits
    assert _guard(book, monkeypatch, risk_amount=30.0)(_plan(**PLAN), 98.5) is None


def test_the_guard_falls_back_to_risk_pct_without_a_size(monkeypatch):
    assert _guard([_trade("A", 5.5)], monkeypatch, risk_amount=None)(_plan(**PLAN), 98.5) == "heat"
    assert _guard([_trade("A", 4.0)], monkeypatch, risk_amount=None)(_plan(**PLAN), 98.5) is None


def test_the_guard_checks_sectors_from_the_map(monkeypatch):
    guard = _guard([_trade("A", 2.5)], monkeypatch, sectors={"A": "Tech", "XYZ": "Tech"})
    assert guard(_plan(**PLAN), 98.5) == "sector"
```

`tests/planning/test_plan_manager_heat_at_fill.py`:

```python
"""v212 rule 8 in the manager: an arm fill whose caps would breach is cancelled
(cancelled_heat_at_fill); out-of-scope fills never call the guard; a failing
guard leaves the fill standing."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_manager_arm_limit import NEXT, _arm, _bars
from tests.planning.test_plan_manager_limit_entry import _limit


@pytest.fixture(autouse=True)
def _plain(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _run(plan, price, guard, **kw):
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, lambda t: price, fill_guard=guard, **kw)
    events = mgr._step_pending(plan, price, NEXT)
    return store.get(plan.plan_id), events


def test_a_breach_cancels_the_fill():
    seen = []
    plan, events = _run(_arm(), 98.4, lambda p, fill: seen.append(fill) or "heat")
    assert seen == [98.5]                                    # called with the fill price
    assert [e.transition for e in events] == ["cancelled_heat_at_fill"]
    assert events[0].detail == {"entry_price": 98.5, "live_price": 98.4, "cap": "heat"}
    assert plan.status == PlanStatus.CANCELLED
    assert plan.status_history[-1]["reason"] == "heat_at_fill"


def test_a_breach_on_a_gap_stop_cancels_before_anything_opens():
    plan, events = _run(_arm(), 99.0, lambda p, fill: "cluster",
                        daily_frame_fn=lambda t: _bars(96.0))
    assert [e.transition for e in events] == ["cancelled_heat_at_fill"]
    assert plan.entry_price is None


def test_a_clear_guard_fills():
    plan, events = _run(_arm(), 98.4, lambda p, fill: None)
    assert [e.transition for e in events] == ["filled"]


def test_a_raising_guard_fails_open():
    def boom(plan, fill):
        raise RuntimeError("trade log down")
    plan, events = _run(_arm(), 98.4, boom)
    assert [e.transition for e in events] == ["filled"]


def test_out_of_scope_fills_never_call_the_guard():
    def never(plan, fill):
        raise AssertionError("guard called for a non-arm plan")
    plan, events = _run(_limit("bullish"), 99.4, never)
    assert [e.transition for e in events] == ["filled"]
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/edge/test_fill_heat.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_heat_at_fill.py
```

Expected: FAIL — `ModuleNotFoundError: swingbot.core.edge.fill_heat`; `PlanManager.__init__() got an unexpected keyword argument 'fill_guard'`.

- [ ] **Step 3: Implement**

`swingbot/core/edge/fill_heat.py` — module docstring cites spec rule 8 and the "Rule" paragraph above. Imports `heat`, `correlation as corr`, `swingbot.core.planning.account` (module, so tests can patch `fill_heat.account.compute_position_size`), `config`, `swallowed`. Functions: `heat_at_fill_reason` (as Interfaces; one `if` per cap, early returns), `_fill_risk_pct(fill, stop, cfg, ticker, balance) -> float`, `_scan_sectors() -> dict` (`universe.sector_map(getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist")`; on any exception `swallowed(log, "edge.fill_heat_sectors", exc, ...)` and `{}`), and `make_fill_guard` returning a closure that builds the book (drops `plan_id == plan.plan_id`), the risk, `cluster_check(cluster_exposure(book, plan.ticker, frames_fn([plan.ticker, *tickers_of_book]), balance), risk_pct)` and returns `heat_at_fill_reason(...)` with `max_open=cfg.get("max_open_positions")`.

`plan_manager.py`:
- `__init__` gains the keyword `fill_guard=None` (last), stored as `self.fill_guard` with a one-line comment (v212 rule 8; None = no re-check).
- `_heat_cap(self, plan, fill) -> str | None` — None unless `self.fill_guard is not None and is_arm_limit(plan)`; calls the guard inside `try`; on `Exception` → `swallowed(log, "scan.plan_manager.fill_guard", exc, "plan %s (%s): heat-at-fill check failed, the fill stands: %s", ...)` and None.
- `_cancel_heat_at_fill(self, plan, fill, price, cap) -> list[PlanEvent]` — `record_transition(plan, CANCELLED, reason="heat_at_fill", at=self._now(), extra={"entry_price": fill, "cap": cap})`, `self._save(plan)`, the event from Interfaces.
- `_fill_pending`: after the risk-cap check, `cap = self._heat_cap(plan, fill)`; when not None `return self._cancel_heat_at_fill(plan, fill, price, cap)`. `_fill_and_stop_gap`: the same two lines after its risk check, before `plan.entry_price` is set.
- Module `_fill_frames(tickers) -> dict` — `{t: f for t in dict.fromkeys(tickers) if (f := PlanManager._frame_or_none(_manager_daily, t)) is not None}`.
- `_manager()`: build one `TradeLog()` and pass it as both `trade_log=` and to `fill_heat.make_fill_guard(trade_log, load_account_config, _fill_frames)` as `fill_guard=` (import `make_fill_guard` and `load_account_config` inside `_manager()`, like `TradeLog`).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/edge/test_fill_heat.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_heat_at_fill.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_arm_limit.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS (the ratchet sees two new tagged handlers, no untagged one); no complexity violation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/fill_heat.py swingbot/core/planning/plan_manager.py tests/edge/test_fill_heat.py tests/planning/test_plan_manager_heat_at_fill.py
git commit -m "feat(v216): heat, sector, cluster and max-open re-checked at an arm limit's fill (V216-2)"
```

### Task V216-3: Register both new events in every routing table; enforcement test

**Model:** sonnet — table registration against an explicit list, pinned by an enforcement test; the judgement (which table holds which event) is fixed below.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (`PENDING_CANCEL_EVENTS` ~line 160; `NOTICE_EVENTS` ~173; `_TRANSITION_LOG` ~186)
- Modify: `swingbot/commands/scanning/follow_notify.py` (`_BY_TRANSITION` ~51; `_CLOSED_OTHER_KIND` ~73; `_STOP_LABELS` ~149; `_CANCEL_LABELS` ~160)
- Modify: `swingbot/core/scanning/execution_embeds.py` (`_EVENT_KINDS` ~29)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`PLAN_EVENT_KINDS` ~302; `_heat_at_fill_fields` beside `_risk_cap_fields` ~405; `_EVENT_FIELDS` ~460, heat cancel only)
- Modify: `swingbot/core/planning/session_expiry.py` (codes ~31; `_IN_SESSION_CODES` ~41; two message builders and `_LIMIT_MESSAGES` ~150; module docstring)
- Modify: `swingbot/core/presentation/instructions.py` (heat cancel only: `_heat_at_fill_why`, `_CANCEL_WHY`, `_CANCEL_LEADS`, `_BUILDERS`) — beyond the ledger's file list, because the existing coverage tests (`tests/presentation/test_trade_deleted_cancel_vocab.py::test_every_pending_cancel_event_has_every_row`, `tests/presentation/test_instructions_limit_cancels.py`, `tests/scanning/test_lifecycle_embeds_limit_cancels.py`) require every `PENDING_CANCEL_EVENTS` member in `_BUILDERS`, `_CANCEL_LEADS` and `_EVENT_FIELDS` the moment it joins the set. V216-4 still owns every `filled_stopped_gap` text row and all arm-limit wording.
- Modify: `tests/tracking/test_pending_cancel_discard.py` (the exact-set and notice-set assertions gain the new members)
- Create: `tests/planning/test_v212_event_tables.py`

**Interfaces:**
- Consumes: V216-1 event `filled_stopped_gap` (detail keys incl. `reason`, `exit_price`, `stop_loss`); V216-2 event `cancelled_heat_at_fill` (detail `entry_price`, `live_price`, `cap`), `fill_heat.CAP_WORDS`.
- Produces: `tests/planning/test_v212_event_tables.py::ROUTING_TABLES` (`dict[str, Collection]`, name → table), `FEED_EVENTS`, `NEW_EVENTS`; V216-4 adds `TEXT_TABLES` and its test to the same file.

**Which table holds which event (fixed here):**

| Table | `cancelled_heat_at_fill` | `filled_stopped_gap` |
|---|---|---|
| `plan_manager.PENDING_CANCEL_EVENTS` (→ `PLACEHOLDER_DISCARD_EVENTS`) | yes | **no** — its placeholder is moved by the fill and closed by the stop; a discard would erase the realised loss |
| `plan_manager.NOTICE_EVENTS` | yes (via the cancel set) | yes, added to the literal: `frozenset({"filled", "closed", "gap_reclaim_order", "filled_stopped_gap"}) \| PENDING_CANCEL_EVENTS` |
| `plan_manager._TRANSITION_LOG` | `("heat cap at fill", "entry_price")` | `("filled and stopped on a gap", "exit_price")` |
| `follow_notify._BY_TRANSITION` | `"closed_other"` | `"stopped"` |
| `follow_notify._CLOSED_OTHER_KIND` | `Kind.RISK_CAP` | — (not closed_other) |
| `follow_notify._CANCEL_LABELS` | `"heat cap reached at fill"` | — |
| `follow_notify._STOP_LABELS` | — | `"filled_stopped_gap": "on a gap through its stop, filled and stopped at"` (keyed by the event's `reason`) |
| `execution_embeds._EVENT_KINDS` | `Kind.RISK_CAP` | `Kind.STOPPED` |
| `lifecycle_embeds.PLAN_EVENT_KINDS` | `Kind.RISK_CAP` | `Kind.STOPPED` |
| `lifecycle_embeds._EVENT_FIELDS` | `_heat_at_fill_fields` | V216-4 |
| `session_expiry._IN_SESSION_CODES` | `HEAT_AT_FILL = "heat_at_fill"` | `FILLED_STOPPED_GAP = "filled_stopped_gap"` |
| `session_expiry._LIMIT_MESSAGES` | `_heat_at_fill_message` | `_filled_stopped_gap_message` |
| `instructions._BUILDERS` / `_CANCEL_LEADS` / `_CANCEL_WHY` | `_cancelled` / `""` / `_heat_at_fill_why` | V216-4 |

- [ ] **Step 1: Write the failing test** `tests/planning/test_v212_event_tables.py`

```python
"""v212 G4: both new events reach every routing table (the 2026-09-11 incident:
a cancel missing from one table left a placeholder trade open). Every pending
cancel and filled_stopped_gap appear in each feed table; the limit-family tables
(those holding cancelled_limit) hold both new events; the heat cancel discards
the placeholder, the gap stop never does."""
import logging

import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning import session_expiry as se
from swingbot.core.planning.plan_manager import PlanEvent, log_plan_event
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds as ee
from swingbot.core.scanning import lifecycle_embeds as le
from tests.planning.test_plan_engine_model import _plan

NEW_EVENTS = ("cancelled_heat_at_fill", "filled_stopped_gap")
FEED_EVENTS = sorted(pm.PENDING_CANCEL_EVENTS | {"filled_stopped_gap"})

#: name -> collection; every FEED_EVENTS member must be in each
ROUTING_TABLES = {
    "plan_manager._TRANSITION_LOG": pm._TRANSITION_LOG,
    "plan_manager.NOTICE_EVENTS": pm.NOTICE_EVENTS,
    "follow_notify._BY_TRANSITION": fn._BY_TRANSITION,
    "execution_embeds._EVENT_KINDS": ee._EVENT_KINDS,
    "lifecycle_embeds.PLAN_EVENT_KINDS": le.PLAN_EVENT_KINDS,
}
#: tables that hold cancelled_limit: both new events must be there too
LIMIT_TABLES = {
    "session_expiry._IN_SESSION_CODES": se._IN_SESSION_CODES,
    "session_expiry._LIMIT_MESSAGES": se._LIMIT_MESSAGES,
}


@pytest.mark.parametrize("name", sorted(ROUTING_TABLES))
@pytest.mark.parametrize("event", FEED_EVENTS)
def test_every_cancel_and_the_gap_stop_reach_every_feed_table(name, event):
    assert event in ROUTING_TABLES[name], f"{event} missing from {name}"


@pytest.mark.parametrize("name", sorted(LIMIT_TABLES))
@pytest.mark.parametrize("event", NEW_EVENTS)
def test_the_limit_family_tables_hold_both_new_events(name, event):
    assert "cancelled_limit" in LIMIT_TABLES[name]
    assert event in LIMIT_TABLES[name]


def test_only_the_heat_cancel_discards_the_placeholder():
    assert "cancelled_heat_at_fill" in pm.PLACEHOLDER_DISCARD_EVENTS
    assert "filled_stopped_gap" not in pm.PLACEHOLDER_DISCARD_EVENTS


def test_kinds():
    assert ee._EVENT_KINDS["cancelled_heat_at_fill"] is Kind.RISK_CAP
    assert le.PLAN_EVENT_KINDS["cancelled_heat_at_fill"] is Kind.RISK_CAP
    assert fn._CLOSED_OTHER_KIND["cancelled_heat_at_fill"] is Kind.RISK_CAP
    assert ee._EVENT_KINDS["filled_stopped_gap"] is Kind.STOPPED
    assert le.PLAN_EVENT_KINDS["filled_stopped_gap"] is Kind.STOPPED


GAP = {"entry_price": 96.0, "exit_price": 96.0, "live_price": 97.0, "stop_loss": 96.75,
       "reason": "filled_stopped_gap",
       "leg": {"fraction": 1.0, "exit_price": 96.0, "r": 0.0, "reason": "loss"}}
HEAT = {"entry_price": 98.5, "live_price": 98.4, "cap": "sector"}


def _arm(**kw):
    return _plan(entry_type="limit", trigger_price=98.5, stop_loss=96.75, tp1=104.0,
                 tp2=None, limit_entry_f=0.5, **kw)


def test_follow_notify_words_both_events():
    gap = PlanEvent("p1", "filled_stopped_gap", GAP)
    assert fn.notify_event_for(gap) == "stopped"
    plan = _arm(entry_price=96.0, status="CLOSED")
    line = fn.message_line(plan, "stopped", "filled_stopped_gap", GAP)
    assert line == ("Paper plan update: AAPL long closed on a gap through its stop, "
                    "filled and stopped at 96.00: 0.0R.")
    heat = PlanEvent("p1", "cancelled_heat_at_fill", HEAT)
    assert fn.notify_event_for(heat) == "closed_other"
    assert fn.message_line(_arm(status="CANCELLED"), "closed_other", "cancelled_heat_at_fill",
                           HEAT) == "Paper plan update: AAPL long cancelled: heat cap reached at fill."


def test_session_expiry_messages():
    assert se.code_for("cancelled_heat_at_fill") == "heat_at_fill"
    assert se.in_session_message(_arm(), "cancelled_heat_at_fill", HEAT) == (
        "The 98.50 limit filled, but sector heat was already at its cap; "
        "cancelled at the fill, nothing opened")
    assert se.in_session_message(_arm(), "filled_stopped_gap", GAP) == (
        "Opened at 96.00, at or through the 96.75 stop: the 98.50 limit filled "
        "at that open and was stopped there")


def test_the_heat_cancel_reads_as_a_cancel_in_the_feed():
    inst = ins.instruction_for(_arm(status="CANCELLED"),
                               PlanEvent("p1", "cancelled_heat_at_fill", HEAT))
    assert inst.lines == ("The limit filled at 98.50, but sector heat was already at its "
                          "cap. The fill is cancelled, nothing was opened.",)


@pytest.mark.parametrize("event,detail,label", [
    ("cancelled_heat_at_fill", HEAT, "heat cap at fill"),
    ("filled_stopped_gap", GAP, "filled and stopped on a gap"),
])
def test_both_events_write_a_transition_line(caplog, event, detail, label):
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.plan_manager"):
        log_plan_event(_arm(), PlanEvent("p1", event, detail))
    assert label in caplog.text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_v212_event_tables.py`
Expected: FAIL — `cancelled_heat_at_fill` / `filled_stopped_gap` missing from every table.

- [ ] **Step 3: Register, per the table above**

- `plan_manager.py`: the two sets and the two `_TRANSITION_LOG` rows, each with a `# v212` comment; the comment above `PENDING_CANCEL_EVENTS` gains one sentence on why `filled_stopped_gap` is not a member.
- `follow_notify.py`: the four rows. `_stopped_copy` already reads `_STOP_LABELS[detail["reason"]]`, so the gap stop needs no new copy function.
- `execution_embeds.py`, `lifecycle_embeds.py` `PLAN_EVENT_KINDS`: the kind rows.
- `lifecycle_embeds._heat_at_fill_fields(embed, plan, d) -> None` — `embed.description = plan_levels_block(plan, plan.trigger_price)`; one "Why" field: `f"The {plan.trigger_price:.2f} limit filled at {d['entry_price']:.2f}, but {CAP_WORDS[d['cap']]} was already at its cap with this fill's risk. Cancelled at the fill; no position, no P&L."`; one `_EVENT_FIELDS` row.
- `session_expiry.py`: constants `HEAT_AT_FILL`, `FILLED_STOPPED_GAP`; `_heat_at_fill_message(plan, detail)` → `f"The {trigger:.2f} limit filled, but {CAP_WORDS[detail['cap']]} was already at its cap; cancelled at the fill, nothing opened"`; `_filled_stopped_gap_message(plan, detail)` → `f"Opened at {exit:.2f}, at or through the {stop:.2f} stop: the {trigger:.2f} limit filled at that open and was stopped there"`; both in `_LIMIT_MESSAGES`; the docstring's list of in-session transitions names both (v212). Import `CAP_WORDS` from `swingbot.core.edge.fill_heat` (a leaf: `fill_heat` imports nothing from `planning.session_expiry`).
- `instructions.py`: `_heat_at_fill_why(detail) -> str` → `f"The limit filled at {_price(detail['entry_price'])}, but {CAP_WORDS[detail['cap']]} was already at its cap. The fill is cancelled, nothing was opened."`; rows `_CANCEL_WHY["cancelled_heat_at_fill"]`, `_CANCEL_LEADS["cancelled_heat_at_fill"] = ""`, `_BUILDERS["cancelled_heat_at_fill"] = _cancelled`.
- `tests/tracking/test_pending_cancel_discard.py`: `test_the_set_holds_exactly_the_eight_pending_cancel_events` → `..._nine_...` with `"cancelled_heat_at_fill",  # v212` added; `test_notice_events_derive_from_the_cancel_set` adds `"filled_stopped_gap"` to the literal. Its parametrized discard test then covers the heat cancel against a real `TradeLog` (the "never left open" check for it; V216-1's placeholder test is the check for the gap stop).

- [ ] **Step 4: Run the tests to verify they pass**

Run `/replicate-prod-db` first (the discard test writes a real trade), then:

```bash
python scripts/dev/testrun.py file tests/planning/test_v212_event_tables.py
python scripts/dev/testrun.py file tests/tracking/test_pending_cancel_discard.py
python scripts/dev/testrun.py file tests/presentation/test_trade_deleted_cancel_vocab.py
python scripts/dev/testrun.py file tests/presentation/test_instructions_limit_cancels.py
python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_limit_cancels.py
python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py
python scripts/dev/testrun.py file tests/commands/test_follow_notify_limit_cancels.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS; no complexity violation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_manager.py swingbot/commands/scanning/follow_notify.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/lifecycle_embeds.py swingbot/core/planning/session_expiry.py swingbot/core/presentation/instructions.py tests/tracking/test_pending_cancel_discard.py tests/planning/test_v212_event_tables.py
git commit -m "feat(v216): register cancelled_heat_at_fill and filled_stopped_gap in every event table (V216-3)"
```


### Task V216-4: Alert and follow-up text: limit ticket, entry line, fill/cancel/gap/heat copy

**Model:** sonnet — wording through existing dispatch tables, every string pinned by a test; the only judgement (arm-only, other plans byte-identical) is fixed below.

Split at the 20 KB cap: this task is the execution feed (`presentation/instructions.py`, the alert ticket and every follow-up instruction); V216-5 is the plan table's entry line and the lifecycle embeds.

**Files:**
- Modify: `swingbot/core/presentation/instructions.py` (import `is_arm_limit`; `_sides` gains `"entry_limit"`; new `limit_order_lines`, `_entry_order`, `_ticket_tail` used by `ticket_for` ~287; `_arm_fill_lines` used by `_filled` ~537; new `_filled_stopped_gap` + `_BUILDERS` row; `_ARM_CANCEL_WHY`/`_arm_cancel_why` read first in `_cancel_why`; `_cancel_order` arm branch)
- Modify: `tests/planning/test_v212_event_tables.py` (`TEXT_TABLES` and its test)
- Create: `tests/presentation/test_instructions_arm_limit.py`

**Interfaces:**
- Consumes: V212-4 `limit_entry_rule.is_arm_limit(plan) -> bool`; V212-2 plan shape (`entry_type="limit"`, `trigger_price=L`, `entry_price=None`, `expiry_bars=3`, `limit_cancel_level=tp1`, `limit_entry_f`); V216-1 events `filled` (detail may carry `"marketable_at_alert": True`), `cancelled_limit` (detail `live_price`, `limit_cancel_level`), `filled_stopped_gap` (detail `entry_price`, `exit_price`, `live_price`, `stop_loss`, `reason`, `leg`); V216-3 `FEED_EVENTS` in `tests/planning/test_v212_event_tables.py`; existing `approx_last_trigger_session`, `total_r`, `outcome_key`, `pnl_line`.
- Produces: `instructions.limit_order_lines(plan) -> list[str]` — exactly `["BUY LIMIT 98.50", "On fill: stop 96.75, TP1 104.00 (TP2 108.00)", "Cancel the order if price trades at 104.00 before it fills", "Valid through the close of Wed 11 Nov"]` for the long fixture below (`"SELL LIMIT"` for shorts; the `(TP2 …)` clause only when `tp2` is set; the date is `approx_last_trigger_session(created_at, expiry_bars)` as `%a %d %b`). `tests/planning/test_v212_event_tables.py::TEXT_TABLES` (name → table), extended by V216-5.

**Scope rule.** Every new wording is gated on `is_arm_limit(plan)`. A v113/v131 limit plan (`limit_entry_f is None`) keeps today's text byte for byte, including its `CANCEL BUY STOP 100.00` cancel headline pinned by `tests/presentation/test_instructions_limit_cancels.py`, which stays green untouched. No test here touches the database.

- [ ] **Step 1: Write the failing tests**

`tests/presentation/test_instructions_arm_limit.py`:

```python
"""v212 G4: an arm limit's ticket reads as a resting limit order (BUY LIMIT L,
the bracket on fill, the TP1 cancel, the expiry date) and every follow-up says
what to do at the broker. Other limit plans keep today's words."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from tests.planning.test_plan_engine_model import _plan

S = tokens.FEED_SYMBOLS
LONG = dict(direction="bullish", trigger_price=98.5, stop_loss=96.75, tp1=104.0,
            tp2=108.0, limit_cancel_level=104.0)
SHORT = dict(direction="bearish", trigger_price=101.5, stop_loss=103.25, tp1=96.0,
             tp2=None, limit_cancel_level=96.0)


def _arm(levels=LONG, **kw):
    base = dict(entry_type="limit", entry_price=None, expiry_bars=3, status="PENDING",
                created_at="2026-11-06T15:30:00", limit_strict_fill=True,
                limit_entry_f=0.5, **levels)
    base.update(kw)
    return _plan(**base)


def _event(transition, **detail):
    return PlanEvent("p1", transition, detail)


@pytest.mark.parametrize("levels,expected", [
    (LONG, ["BUY LIMIT 98.50", "On fill: stop 96.75, TP1 104.00 (TP2 108.00)",
            "Cancel the order if price trades at 104.00 before it fills",
            "Valid through the close of Wed 11 Nov"]),
    (SHORT, ["SELL LIMIT 101.50", "On fill: stop 103.25, TP1 96.00",
             "Cancel the order if price trades at 96.00 before it fills",
             "Valid through the close of Wed 11 Nov"]),
])
def test_limit_order_lines(levels, expected):
    assert ins.limit_order_lines(_arm(levels)) == expected


@pytest.mark.parametrize("levels", [LONG, SHORT])
def test_the_ticket_is_a_resting_limit_never_at_market(levels):
    plan = _arm(levels)
    inst = ins.ticket_for(plan, logged=True, not_logged_reason=None)
    lines = ins.limit_order_lines(plan)
    assert inst.verb == ins.PLACE
    assert inst.headline == f"{S['entry']} {lines[0]} · size n/a"
    assert inst.lines[-3:] == tuple(lines[1:])
    text = " ".join((inst.headline, *inst.lines))
    assert "AT MARKET" not in text and "CANCEL after" not in text


def test_an_out_of_scope_limit_ticket_is_unchanged():
    inst = ins.ticket_for(_arm(limit_entry_f=None), logged=True, not_logged_reason=None)
    assert inst.headline == f"{S['entry']} BUY AT MARKET ~98.50 · size n/a"
    assert not any(line.startswith("On fill") for line in inst.lines)


def test_a_fill_says_place_the_stop_now():
    inst = ins.instruction_for(_arm(entry_price=98.5, status="ACTIVE"),
                               _event("filled", entry_price=98.5, live_price=98.4))
    assert inst.lines[-1] == "The limit filled: place the stop at 96.75 now (SELL STOP)"
    assert len(inst.lines) == 3


def test_a_marketable_fill_at_alert_says_so():
    inst = ins.instruction_for(
        _arm(entry_price=98.2, status="ACTIVE"),
        _event("filled", entry_price=98.2, live_price=98.2, marketable_at_alert=True))
    assert inst.lines[-1] == ("Price was already through the 98.50 limit when the alert "
                              "went out; filled at the quote 98.20")


def test_an_out_of_scope_fill_is_unchanged():
    inst = ins.instruction_for(_arm(limit_entry_f=None, entry_price=98.5, status="ACTIVE"),
                               _event("filled", entry_price=98.5, live_price=98.4))
    assert len(inst.lines) == 2


def test_the_tp1_cancel_names_tp1():
    inst = ins.instruction_for(_arm(status="CANCELLED"),
                               _event("cancelled_limit", live_price=104.0,
                                      limit_cancel_level=104.0))
    assert inst.headline == "CANCEL BUY LIMIT 98.50"
    assert inst.lines == ("TP1 104.00 traded at 104.00 before the 98.50 limit filled. "
                          "Cancel the order; nothing was opened.",)


def test_expiry_names_the_last_session():
    inst = ins.instruction_for(_arm(levels=SHORT, status="CANCELLED"),
                               _event("cancelled_expired", bars_waited=4))
    assert inst.headline == f"{S['expiry']} CANCEL SELL LIMIT 101.50"
    assert inst.lines == ("The 101.50 limit did not fill by the close of Wed 11 Nov. "
                          "Cancel the order; nothing was opened.",)


@pytest.mark.parametrize("levels,gap", [(LONG, 96.0), (SHORT, 104.0)])
def test_filled_and_stopped_on_a_gap(levels, gap):
    plan = _arm(levels, entry_price=gap, status="CLOSED")
    beyond = "below" if levels is LONG else "above"
    inst = ins.instruction_for(plan, _event(
        "filled_stopped_gap", entry_price=gap, exit_price=gap, live_price=gap,
        stop_loss=levels["stop_loss"], reason="filled_stopped_gap",
        leg={"fraction": 1.0, "exit_price": gap, "r": 0.0, "reason": "loss"}))
    assert (inst.verb, inst.tone) == (ins.EXITED, "neutral")
    assert inst.headline == f"{S['flat']} FILLED AND STOPPED @ {gap:.2f} · gap through the stop"
    assert inst.lines[0] == (
        f"Opened at {gap:.2f}, at or {beyond} the stop {levels['stop_loss']:.2f}: the "
        f"{levels['trigger_price']:.2f} limit filled at that open and the stop closed it "
        "at the same price.")
    assert inst.lines[1] == ins.pnl_line(0.0, None)
```

Append to `tests/planning/test_v212_event_tables.py`:

```python
#: V216-4: every feed event has its words in each text table (V216-5 adds the embeds)
TEXT_TABLES = {
    "instructions._BUILDERS": ins._BUILDERS,
}


@pytest.mark.parametrize("name", sorted(TEXT_TABLES))
@pytest.mark.parametrize("event", FEED_EVENTS)
def test_every_feed_event_has_its_words(name, event):
    assert event in TEXT_TABLES[name], f"{event} has no text in {name}"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/presentation/test_instructions_arm_limit.py
python scripts/dev/testrun.py file tests/planning/test_v212_event_tables.py
```

Expected: FAIL — `limit_order_lines` missing, tickets read `BUY AT MARKET`, `filled_stopped_gap` missing from `_BUILDERS`. The out-of-scope tests already pass.

- [ ] **Step 3: Implement `instructions.py`**

Import `from swingbot.core.planning.limit_entry_rule import is_arm_limit`. `_sides` gains `"entry_limit": "BUY LIMIT"` (bullish dict) and `"entry_limit": "SELL LIMIT"` (bearish dict); no other key changes. Add after `market_on_open_lines`:

```python
def limit_order_lines(plan) -> list[str]:
    """v212 G4: an arm limit's four order lines -- the limit, its bracket on
    fill, its TP1 cancel and its last session. Prices are already on the tick
    (builders.confluence_limit_geometry rounds L and the stop)."""
    side = _sides(plan.direction)
    tp2 = f" (TP2 {_price(plan.tp2)})" if plan.tp2 is not None else ""
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    return [f"{side['entry_limit']} {_price(plan.trigger_price)}",
            f"On fill: stop {_price(plan.stop_loss)}, TP1 {_price(plan.tp1)}{tp2}",
            f"Cancel the order if price trades at {_price(plan.tp1)} before it fills",
            f"Valid through the close of {last:%a %d %b}"]


def _entry_order(plan, side: dict) -> str:
    """The ticket headline's order: v212's arm limit first, then today's three cases."""
    if is_arm_limit(plan):
        return limit_order_lines(plan)[0]
    if plan.entry_type == "stop_entry":
        return f"{side['entry_stop']} {_price(plan.trigger_price)}"
    if waits_for_open(plan):
        return f"{side['entry_market']} ON OPEN ~{_price(plan.trigger_price)}"   # v192
    return f"{side['entry_market']} ~{_price(plan.trigger_price)}"


def _ticket_tail(plan) -> list[str]:
    """The lines after the bracket: an arm limit's terms, a stop entry's cancels."""
    if is_arm_limit(plan):
        return limit_order_lines(plan)[1:]
    if plan.entry_type == "stop_entry":
        return [_cancel_line(plan)]
    return []
```

In `ticket_for`, replace the `if/elif/else` that builds `order` with `order = _entry_order(plan, side)`, and the trailing `if plan.entry_type == "stop_entry": lines.append(_cancel_line(plan))` with `lines.extend(_ticket_tail(plan))`. Every non-arm ticket keeps the same branches in the same order.

`_filled` gains the arm lines; its `lines=` tuple becomes `(<the two existing lines>, *_arm_fill_lines(plan, event.detail, side))`:

```python
def _arm_fill_lines(plan, detail: dict, side: dict) -> tuple[str, ...]:
    """v212 G4: an arm limit's fill tells the reader to place the stop now."""
    if not is_arm_limit(plan):
        return ()
    lines = (f"The limit filled: place the stop at {_price(plan.stop_loss)} now "
             f"({side['stop']})",)
    if detail.get("marketable_at_alert"):
        lines += (f"Price was already through the {_price(plan.trigger_price)} limit when "
                  f"the alert went out; filled at the quote {_price(detail['entry_price'])}",)
    return lines
```

The gap-stop builder (after `_filled`), plus one `_BUILDERS` row `"filled_stopped_gap": _filled_stopped_gap,     # v212`:

```python
def _filled_stopped_gap(plan, event, side: dict, common: dict,
                        money: Money | None) -> Instruction:
    """v212 rule 6: the session opened at or through the stop while the limit
    rested; the limit filled at that open and the stop closed it there."""
    d = event.detail
    exit_price = d["exit_price"]
    r = total_r(plan, exit_price)
    outcome = outcome_key(r)
    return Instruction(
        verb=EXITED,
        headline=f"{_S[outcome]} FILLED AND STOPPED @ {_price(exit_price)} · gap through the stop",
        lines=(f"Opened at {_price(exit_price)}, at or {_BEYOND[plan.direction]} the stop "
               f"{_price(d['stop_loss'])}: the {_price(plan.trigger_price)} limit filled at "
               "that open and the stop closed it at the same price.",
               pnl_line(r, money),
               f"If your broker's stop did not fire: {side['exit']}"),
        tone=_OUTCOME_TONES[outcome], **common)
```

The arm cancels (after `_CANCEL_WHY`):

```python
def _arm_tp1_cancel_why(plan, detail: dict) -> str:
    return (f"TP1 {_price(plan.tp1)} traded at {_price(detail['live_price'])} before the "
            f"{_price(plan.trigger_price)} limit filled. Cancel the order; nothing was opened.")


def _arm_expired_why(plan, detail: dict) -> str:
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    return (f"The {_price(plan.trigger_price)} limit did not fill by the close of "
            f"{last:%a %d %b}. Cancel the order; nothing was opened.")


#: v212 G4: an arm limit's own cancels, worded for the resting order.
_ARM_CANCEL_WHY = {"cancelled_limit": _arm_tp1_cancel_why,
                   "cancelled_expired": _arm_expired_why}


def _arm_cancel_why(plan, transition: str, detail: dict) -> str | None:
    why = _ARM_CANCEL_WHY.get(transition) if is_arm_limit(plan) else None
    return why(plan, detail) if why is not None else None
```

In `_cancel_why`, right after the `reason_message` return: `arm = _arm_cancel_why(plan, transition, detail)` then `if arm is not None: return arm  # v212: arm limit cancels`. In `_cancel_order`, first statement: `if is_arm_limit(plan): return f"{side['entry_limit']} {_price(plan.trigger_price)}"` (V216-3's heat cancel then also heads `CANCEL BUY LIMIT L`; its test asserts only the lines). `_CANCEL_LEADS` needs no row: `filled_stopped_gap` is a close, not a cancel.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/presentation/test_instructions_arm_limit.py
python scripts/dev/testrun.py file tests/planning/test_v212_event_tables.py
python scripts/dev/testrun.py file tests/presentation/test_instructions_limit_cancels.py
python scripts/dev/testrun.py file tests/presentation/test_trade_deleted_cancel_vocab.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS (the last two test files are untouched: other plans keep their words); no complexity violation (`ticket_for` hands two branches to its helpers).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/instructions.py tests/planning/test_v212_event_tables.py tests/presentation/test_instructions_arm_limit.py
git commit -m "feat(v216): limit ticket and follow-up instructions for arm limits (V216-4)"
```

### Task V216-5: Alert and follow-up text, part b: plan-table entry line and lifecycle embeds

**Model:** sonnet — two field-builder tables and one entry line, every string pinned by a test; arm-only gating as in V216-4.

Second half of V216-4 (split at the 20 KB cap). Runs after V216-4: it imports `approx_last_trigger_session` alongside V216-4's text and extends V216-4's `TEXT_TABLES`.

**Files:**
- Modify: `swingbot/core/scanning/plan_table.py` (`entry_line` ~116 arm branch via `_limit_entry_line`)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`_filled_stopped_gap_fields` + `_EVENT_FIELDS` row; `_ARM_EVENT_FIELDS` for `filled` / `cancelled_limit` / `cancelled_expired`; `_fields_for(plan, event)`)
- Modify: `tests/planning/test_v212_event_tables.py` (one `TEXT_TABLES` row)
- Create: `tests/scanning/test_plan_table_arm_limit.py`, `tests/scanning/test_lifecycle_embeds_arm_limit.py`

**Interfaces:**
- Consumes: V212-4 `is_arm_limit`; V212-2 plan shape; V216-1 event details (`filled` with optional `marketable_at_alert`, `cancelled_limit`, `cancelled_expired`, `filled_stopped_gap`); V216-3 `PLAN_EVENT_KINDS["filled_stopped_gap"] = Kind.STOPPED` (the embed's title); V216-4 `TEXT_TABLES`; existing `approx_last_trigger_session`, `total_r`, `plan_levels_block`, `plan_result_block`, `_filled_fields`.
- Produces: nothing later tasks consume.

**Scope rule.** As V216-4: gated on `is_arm_limit(plan)`; `tests/scanning/test_lifecycle_embeds_limit_cancels.py` and `tests/scanning/test_embeds_badges.py` (today's entry lines) stay green untouched. No test here touches the database.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_plan_table_arm_limit.py`:

```python
"""v212 G4: the plan table's entry line for an arm limit names the order,
its last session and its TP1 cancel; other plans keep today's line."""
from swingbot.core.scanning.plan_table import entry_line
from tests.planning.test_plan_engine_model import _plan


def _arm(**kw):
    base = dict(entry_type="limit", trigger_price=98.5, stop_loss=96.75, tp1=104.0,
                expiry_bars=3, created_at="2026-11-06T15:30:00", limit_entry_f=0.5)
    base.update(kw)
    return _plan(**base)


def test_long_arm_limit():
    assert entry_line(_arm()) == ("Entry: BUY LIMIT 98.50 (valid through the close of "
                                  "Wed 11 Nov; cancel if TP1 104.00 trades first)")


def test_short_arm_limit():
    plan = _arm(direction="bearish", trigger_price=101.5, stop_loss=103.25, tp1=96.0)
    assert entry_line(plan) == ("Entry: SELL LIMIT 101.50 (valid through the close of "
                                "Wed 11 Nov; cancel if TP1 96.00 trades first)")


def test_an_out_of_scope_limit_keeps_todays_line():
    assert entry_line(_arm(limit_entry_f=None)) == "Entry: market ~98.50"
```

`tests/scanning/test_lifecycle_embeds_arm_limit.py`:

```python
"""v212 G4: the lifecycle embeds of an arm limit: fill (place the stop now),
TP1 cancel, expiry and filled-and-stopped on a gap. A v131 limit keeps today's."""
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.scanning.lifecycle_embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan


def _arm(**kw):
    base = dict(entry_type="limit", trigger_price=98.5, stop_loss=96.75, tp1=104.0,
                tp2=108.0, expiry_bars=3, created_at="2026-11-06T15:30:00",
                limit_cancel_level=104.0, limit_entry_f=0.5, entry_price=None)
    base.update(kw)
    return _plan(**base)


def _field(embed, name):
    return next(f.value for f in embed.fields if f.name == name)


def test_fill_says_place_the_stop_now():
    embed = build_plan_event_embed(_arm(entry_price=98.5, status="ACTIVE"),
                                   PlanEvent("p1", "filled", {"entry_price": 98.5,
                                                              "live_price": 98.4}))
    assert _field(embed, "Entry") == "98.50"
    assert _field(embed, "Place now") == "Stop 96.75: the limit filled, place the stop now"
    assert all(f.name != "Filled at alert" for f in embed.fields)


def test_a_marketable_fill_says_so():
    embed = build_plan_event_embed(_arm(entry_price=98.2, status="ACTIVE"), PlanEvent(
        "p1", "filled", {"entry_price": 98.2, "live_price": 98.2, "marketable_at_alert": True}))
    assert _field(embed, "Filled at alert") == (
        "Price was already through the 98.50 limit when the alert went out; "
        "filled at the quote 98.20")


def test_tp1_cancel():
    embed = build_plan_event_embed(_arm(status="CANCELLED"), PlanEvent(
        "p1", "cancelled_limit", {"live_price": 104.1, "limit_cancel_level": 104.0}))
    assert _field(embed, "Why") == ("TP1 104.00 traded at 104.10 before the 98.50 limit "
                                    "filled. Cancel the order. Never opened; no position, no P&L.")


def test_expiry():
    embed = build_plan_event_embed(_arm(status="CANCELLED"), PlanEvent(
        "p1", "cancelled_expired", {"bars_waited": 4}))
    assert _field(embed, "Why") == ("The 98.50 limit did not fill by the close of Wed 11 Nov. "
                                    "Cancel the order. Never opened; no position, no P&L.")


def test_filled_and_stopped_on_a_gap():
    embed = build_plan_event_embed(_arm(entry_price=96.0, status="CLOSED"), PlanEvent(
        "p1", "filled_stopped_gap", {"entry_price": 96.0, "exit_price": 96.0,
                                     "live_price": 96.0, "stop_loss": 96.75,
                                     "reason": "filled_stopped_gap"}))
    assert _field(embed, "Exit") == "96.00"
    assert _field(embed, "Why") == (
        "Opened at 96.00, at or through the stop 96.75: the 98.50 limit filled at that open "
        "and the stop closed it at the same price. A realised loss of about 0R before "
        "frictions, never a cancel.")


def test_an_out_of_scope_limit_cancel_is_unchanged():
    embed = build_plan_event_embed(_arm(limit_entry_f=None, status="CANCELLED"), PlanEvent(
        "p1", "cancelled_limit", {"live_price": 104.1, "limit_cancel_level": 104.0}))
    assert _field(embed, "Why").startswith("Price ran to 104.10, past the limit's cancel level")
```

In `tests/planning/test_v212_event_tables.py`, `TEXT_TABLES` gains its second row:

```python
TEXT_TABLES = {
    "instructions._BUILDERS": ins._BUILDERS,
    "lifecycle_embeds._EVENT_FIELDS": le._EVENT_FIELDS,
}
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/scanning/test_plan_table_arm_limit.py
python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_arm_limit.py
python scripts/dev/testrun.py file tests/planning/test_v212_event_tables.py
```

Expected: FAIL — the entry line reads `Entry: market ~98.50`, the arm fields are missing, `filled_stopped_gap` is missing from `_EVENT_FIELDS`. The out-of-scope tests already pass.

- [ ] **Step 3: Implement `plan_table.py` and `lifecycle_embeds.py`**

`plan_table.py` — imports `from swingbot.core.planning.limit_entry_rule import is_arm_limit` and `from swingbot.core.presentation.instructions import approx_last_trigger_session` (no cycle: `instructions` imports nothing from `core.scanning`; `lifecycle_embeds` already imports it). `entry_line` gains a first branch `if is_arm_limit(plan): return _limit_entry_line(plan)`:

```python
def _limit_entry_line(plan) -> str:
    """v212 G4: an arm limit's entry line -- the order, its last session, its TP1 cancel."""
    side = "BUY LIMIT" if plan.direction == "bullish" else "SELL LIMIT"
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    return (f"Entry: {side} {plan.trigger_price:.2f} (valid through the close of "
            f"{last:%a %d %b}; cancel if TP1 {plan.tp1:.2f} trades first)")
```

`lifecycle_embeds.py` — extend the instructions import to `approx_last_trigger_session, total_r`; import `is_arm_limit`; add after `_outlook_cancel_fields`:

```python
def _filled_stopped_gap_fields(embed, plan, d) -> None:
    """v212 rule 6: the limit filled at a gap open through its stop and closed there."""
    exit_price = d["exit_price"]
    embed.description = plan_result_block(plan, exit_price, total_r(plan, exit_price))
    embed.add_field(name="Exit", value=f"{exit_price:.2f}")
    embed.add_field(name="Why", value=(
        f"Opened at {exit_price:.2f}, at or through the stop {d['stop_loss']:.2f}: the "
        f"{plan.trigger_price:.2f} limit filled at that open and the stop closed it at the "
        "same price. A realised loss of about 0R before frictions, never a cancel."),
        inline=False)


def _arm_filled_fields(embed, plan, d) -> None:
    """v212 G4: today's fill fields plus the stop to place now."""
    _filled_fields(embed, plan, d)
    embed.add_field(name="Place now",
                    value=f"Stop {plan.stop_loss:.2f}: the limit filled, place the stop now",
                    inline=False)
    if d.get("marketable_at_alert"):
        embed.add_field(name="Filled at alert", value=(
            f"Price was already through the {plan.trigger_price:.2f} limit when the alert "
            f"went out; filled at the quote {d['entry_price']:.2f}"), inline=False)


def _arm_tp1_cancel_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"TP1 {plan.tp1:.2f} traded at {d['live_price']:.2f} before the "
        f"{plan.trigger_price:.2f} limit filled. Cancel the order. "
        "Never opened; no position, no P&L."), inline=False)


def _arm_expired_fields(embed, plan, d) -> None:
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"The {plan.trigger_price:.2f} limit did not fill by the close of {last:%a %d %b}. "
        "Cancel the order. Never opened; no position, no P&L."), inline=False)


#: v212 G4: an arm limit's own field builders, read before _EVENT_FIELDS.
_ARM_EVENT_FIELDS = {
    "filled": _arm_filled_fields,
    "cancelled_limit": _arm_tp1_cancel_fields,
    "cancelled_expired": _arm_expired_fields,
}
```

`_EVENT_FIELDS` gains `"filled_stopped_gap": _filled_stopped_gap_fields,   # v212`. `_fields_for` becomes (its only caller is `build_plan_event_embed`, which now passes `plan`; `git grep -n "_fields_for("` confirms):

```python
def _fields_for(plan, event):
    """The field builder for one event: a stated reason (v144) wins, then an
    arm limit's own builder (v212), then the transition's."""
    if event.detail.get("reason_message"):
        return _outlook_cancel_fields
    if is_arm_limit(plan) and event.transition in _ARM_EVENT_FIELDS:
        return _ARM_EVENT_FIELDS[event.transition]
    return _EVENT_FIELDS.get(event.transition)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/scanning/test_plan_table_arm_limit.py
python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_arm_limit.py
python scripts/dev/testrun.py file tests/planning/test_v212_event_tables.py
python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_limit_cancels.py
python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS; no complexity violation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/plan_table.py swingbot/core/scanning/lifecycle_embeds.py tests/planning/test_v212_event_tables.py tests/scanning/test_plan_table_arm_limit.py tests/scanning/test_lifecycle_embeds_arm_limit.py
git commit -m "feat(v216): arm limit entry line and lifecycle embed text (V216-5)"
```

### Task V216-6: Admin: `levels-block` limit mapping

**Model:** haiku — one spec file gains a render test; the mapping it pins is a three-word table row.

**Finding (writer, verified on `main`):** the ledger's mapping already exists. `entryTypeWord` in `frontend/src/app/workspaces/trades/why/levels-block.ts` carries `limit: { bullish: 'Buy limit', bearish: 'Sell limit', fallback: 'Limit entry' }` since V151-10 (`359825d4`), and `levels-block.spec.ts` already tests the word table (`['limit', 'bullish', 'Buy limit']` …). The spec's G4 premise ("`why/levels-block.ts` gains the limit mapping") is stale. What is left is the spec's actual requirement: the admin plan view of a **pending v212 limit plan** reads as a resting order. This task pins that render; `levels-block.ts` changes only if the test shows the mapping missing on the worktree's base.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/why/levels-block.spec.ts` (two `it` cases in `describe('LevelsBlock', …)`)
- Modify (only if Step 2 fails): `frontend/src/app/workspaces/trades/why/levels-block.ts` (`entryTypeWord`'s `words` table)

**Interfaces:**
- Consumes: the plan detail page's inputs as `plan-detail.ts` (~192) binds them: `entryType` = the plan's `entry_type` (`"limit"`), `trigger` = `trigger_price` (L), `entry` = `trade.entry` (`null` while pending), `stop` = the plan's stop S′.
- Produces: `entryTypeWord` keeps `limit: { bullish: 'Buy limit', bearish: 'Sell limit', fallback: 'Limit entry' }` (no other task consumes it).

No layout, breakpoint or control changes: the block's rows are the same at mobile, tablet and desktop, so no three-width check is owed (`ui-design.md` § UI tasks applies to layout changes).

- [ ] **Step 1: Write the test**

Add to `describe('LevelsBlock', …)` in `levels-block.spec.ts`, after `'orders populated rows, …'`:

```ts
  it('reads a pending v212 limit plan as a resting order: Buy limit at its trigger, entry not yet filled', () => {
    const f = mount({ direction: 'bullish', entryType: 'limit', trigger: 98.5,
      entry: null, stop: 96.75, target1: 104, target2: 108, riskReward: 3.14 });
    expect(rows(f)).toEqual([
      ['Order', 'Buy limit'], ['Trigger', '98.50'], ['Entry', '—'], ['Stop', '96.75'],
      ['Target 1', '104.00'], ['Target 2', '108.00'], ['R:R', '3.14'],
    ]);
  });

  it('reads a short v212 limit plan as a Sell limit', () => {
    const f = mount({ direction: 'bearish', entryType: 'limit', trigger: 101.5,
      entry: null, stop: 103.25, target1: 96, target2: null, riskReward: 2.57 });
    expect(rows(f).slice(0, 4)).toEqual([
      ['Order', 'Sell limit'], ['Trigger', '101.50'], ['Entry', '—'], ['Stop', '103.25'],
    ]);
  });
```

- [ ] **Step 2: Run it**

```bash
(cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/why/levels-block.spec.ts)
```

Expected: PASS on a base that holds `359825d4` (the mapping exists). If it FAILs with `'limit'` rendered raw, do Step 3; otherwise skip it.

- [ ] **Step 3: The mapping (only if Step 2 failed)**

In `entryTypeWord`, the `words` table holds exactly:

```ts
  const words: Record<string, Record<string, string>> = {
    stop_entry: { bullish: 'Buy stop', bearish: 'Sell stop', fallback: 'Stop entry' },
    limit: { bullish: 'Buy limit', bearish: 'Sell limit', fallback: 'Limit entry' },
  };
```

Re-run Step 2's command; expected PASS, including the existing `entryTypeWord` table cases.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/levels-block.spec.ts
git commit -m "test(v216): admin Levels block reads a pending limit plan as a resting order (V216-6)"
```

(Add `frontend/src/app/workspaces/trades/why/levels-block.ts` to the `git add` only if Step 3 changed it.)
