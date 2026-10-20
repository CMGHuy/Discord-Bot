# v172 Equity candlestick chart, part 1: core (equity definition, storage)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V172-2:" -A 400 docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_1-core.md`.

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md) (its `## Corrections from the code brief` and the § 3 raw-bar decision win over earlier wording)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md) — **Global Constraints, Parallelisation, the task ledger and `$WT`/`$R` are defined there; every task below implicitly includes the Global Constraints.** V172-3 (candle bucketing) is in `_1b-candles.md`, split off to keep each file under 1500 lines.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-17-v172-equity-candlestick-chart`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths and `git -C $WT`.

# Phase 1 — Core

### Task V172-1: Worktree; one equity definition in core; move `unrealized_pnl_amount` and `_open_shares`

**Model:** opus — crosses `core/tracking`, `core/planning` and the admin; the money definition every later task builds on

**Files:**
- Create: `swingbot/core/tracking/equity.py`
- Modify: `swingbot/admin/dashboard.py:165-175` (the `unrealized_pnl_amount` def becomes a re-import)
- Modify: `swingbot/admin/api_v1/trades.py:188-205` (the `_open_shares` def becomes a re-import)
- Modify: `swingbot/admin/api_v1/dashboard.py:206-230` (`_live_positions` delegates to core)
- Modify: `docs/claude/architecture.md` (the `core/tracking/` file list, line ~25)
- Test: `tests/tracking/test_equity_definition.py` (suite `storage`)

**Interfaces:**
- Consumes (existing): `expand_realized_legs(trade: dict) -> list[dict]` (`swingbot/core/tracking/performance.py:484`), `split_by_ledger(trades) -> tuple[list, list]` (`swingbot/core/tracking/ledger.py:32`), `load_account_config() -> dict` (`swingbot/core/planning/account.py:105`), `PlanStore().records() -> list[dict]` (`swingbot/core/planning/plan_store.py:43`), `metrics.equity_curve(closed, starting_balance) -> dict` (`swingbot/core/analytics/metrics.py:95`, test parity only).
- Produces (ledger contract, consumed by V172-3..V172-7):
  - `CENT = Decimal("0.01")`
  - `parse_ts(value: str | datetime | None) -> datetime | None` — tz-aware UTC; a naive value is UTC; an unparsable string is `None`.
  - `to_decimal(value) -> Decimal | None` — `Decimal(str(x))`; `None` stays `None`.
  - `open_shares(shares: float | None, legs_realized: list) -> float | None` — moved body of `_open_shares`.
  - `unrealized_pnl_amount(entry, direction: str, open_shares, price) -> float | None` — moved, body unchanged.
  - `unrealized_decimal(entry, direction: str, open_shares, price) -> Decimal | None` — unrounded Decimal of the same formula.
  - `main_book(trades: list[dict]) -> list[dict]` — `split_by_ledger(trades)[0]`.
  - `class RealizedLeg(NamedTuple): at: datetime; amount: Decimal; trade_id: object`
  - `realized_legs(trades: list[dict]) -> list[RealizedLeg]` — main book applied inside, sorted by `at`.
  - `realized_balance_at(start: Decimal, legs: Sequence[RealizedLeg], at: datetime) -> Decimal`
  - `starting_balance() -> Decimal`
  - `load_plans_by_id() -> dict`
  - `held_now(open_trades: list[dict], plans_by_id: dict) -> list[dict]` — the `_live_positions` plan filter with no ledger or status filter (used by `api_v1/dashboard.py` and `live_open_positions`; not consumed by later tasks).
  - `live_open_positions(trades: list[dict], plans_by_id: dict) -> list[dict]` — main book, `status == "open"`, then `held_now`.
  - `@dataclass(frozen=True) class EquitySnapshot: realized_balance: Decimal; unrealized_pnl: Decimal; equity: Decimal; open_n: int; skipped_n: int`
  - `snapshot_at(trades: list[dict], plans_by_id: dict, prices: dict[str, float], at: datetime, start: Decimal) -> EquitySnapshot`
  - `swingbot.admin.dashboard.unrealized_pnl_amount` and `swingbot.admin.api_v1.trades._open_shares` stay importable (the same objects as the core ones).

- [ ] **Step 1: Create or reuse the worktree**

Invoke the `worktree-lifecycle` skill. Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
```

If `.claude/worktrees/2026-10-17-v172-equity-candlestick-chart` is listed, reuse it (resume at its first uncommitted task). Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-17-v172-equity-candlestick-chart -b 2026-10-17-v172-equity-candlestick-chart main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-17-v172-equity-candlestick-chart log --oneline -1
```

Expected: the worktree exists on branch `2026-10-17-v172-equity-candlestick-chart`, at `main`'s HEAD.

- [ ] **Step 2: Confirm the symbols this task moves and reads**

```bash
git -C $WT grep -n "def unrealized_pnl_amount\|def _open_shares\|def _live_positions\|def expand_realized_legs\|def split_by_ledger\|def load_account_config\|def records" -- swingbot
git -C $WT grep -n "unrealized_pnl_amount\|_open_shares" -- swingbot tests
```

Expected: `swingbot/admin/dashboard.py:165`, `swingbot/admin/api_v1/trades.py:188`, `swingbot/admin/api_v1/dashboard.py:206`, `performance.py:484`, `ledger.py:32`, `account.py:105`, `plan_store.py:43`. Callers: `trades.py:308` (`_open_shares`), `trades.py:1061` (`dash.unrealized_pnl_amount`), `dashboard.py:349` (`_append_amount`), `api_v1/dashboard.py:216,226`. A caller outside this list must keep working through the re-import; name it in the task report.

- [ ] **Step 3: Write the failing tests**

Create `$WT/tests/tracking/test_equity_definition.py`:

```python
"""v172 § 0: one equity definition, `swingbot/core/tracking/equity.py`.

Hand-computed throughout. The PARTIAL fixture is 10 shares bought at 100;
TP1 banks half (5 shares) at 110 = +50, leaving 5 shares open.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.tracking import equity

UTC = timezone.utc
TP1_AT = "2026-08-03T15:00:00+00:00"
TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1", "closed_at": TP1_AT}


def _trade(trade_id="t1", *, ticker="AAPL", status="open", legs=(), pnl=None, closed_at=None,
           exit_price=None, shares=10, entry=100.0, direction="bullish", plan_id=None,
           ledger="main", opened_at="2026-08-01T14:00:00+00:00", origin=None):
    trade = {"id": trade_id, "ticker": ticker, "direction": direction, "status": status,
             "entry": entry, "stop_loss": 95.0, "exit_price": exit_price, "shares": shares,
             "realized_pnl_amount": pnl, "opened_at": opened_at, "closed_at": closed_at,
             "legs": list(legs), "plan_id": plan_id, "ledger": ledger}
    if origin is not None:
        trade["origin"] = origin
    return trade


def _closed(trade_id, pnl, closed_at, **kw):
    return _trade(trade_id, status="win" if pnl >= 0 else "loss", pnl=pnl, closed_at=closed_at,
                  exit_price=100.0 + pnl / 10, **kw)


def _at(text):
    return datetime.fromisoformat(text)


# --- moved helpers: same behaviour, same objects in the admin ---------------

def test_open_shares_is_the_remaining_fraction_of_the_original_size():
    assert equity.open_shares(10, []) == 10.0
    assert equity.open_shares(10, [{"fraction": 0.5}]) == 5.0
    assert equity.open_shares(10, [{"fraction": 0.7}, {"fraction": 0.6}]) == 0.0
    assert equity.open_shares(None, [{"fraction": 0.5}]) is None


def test_unrealized_pnl_amount_keeps_its_formula():
    assert equity.unrealized_pnl_amount(100.0, "bullish", 5, 110.0) == 50.0
    assert equity.unrealized_pnl_amount(100.0, "bearish", 5, 110.0) == -50.0
    assert equity.unrealized_pnl_amount(100.0, "bullish", 0, 110.0) is None
    assert equity.unrealized_pnl_amount(None, "bullish", 5, 110.0) is None
    assert equity.unrealized_pnl_amount(100.0, "bullish", 5, None) is None


def test_the_admin_re_imports_the_core_helpers():
    from swingbot.admin import dashboard as dash
    from swingbot.admin.api_v1 import trades

    assert dash.unrealized_pnl_amount is equity.unrealized_pnl_amount
    assert trades._open_shares is equity.open_shares


def test_unrealized_decimal_is_exact_to_the_cent():
    # 3 x (100.35 - 100.1) is 0.7499999... in floats, exactly 0.75 in Decimal.
    assert equity.unrealized_decimal(100.1, "bullish", 3, 100.35) == Decimal("0.75")
    assert equity.unrealized_decimal(100.1, "bearish", 3, 100.35) == Decimal("-0.75")
    assert equity.unrealized_decimal(100.0, "bullish", None, 101.0) is None


def test_unrealized_decimal_rounds_to_the_admin_amount():
    exact = equity.unrealized_decimal(101.37, "bullish", 7.5, 104.91)
    assert float(exact.quantize(equity.CENT)) == equity.unrealized_pnl_amount(
        101.37, "bullish", 7.5, 104.91)


# --- parsing ------------------------------------------------------------------

def test_parse_ts_returns_tz_aware_utc():
    assert equity.parse_ts("2026-08-03T15:00:00+00:00") == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts("2026-08-03T11:00:00-04:00") == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts("2026-08-03T15:00:00") == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts(datetime(2026, 8, 3, 15)) == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts(None) is None
    assert equity.parse_ts("not a time") is None


def test_to_decimal_goes_through_str():
    assert equity.to_decimal(0.1) == Decimal("0.1")
    assert equity.to_decimal(None) is None
    assert equity.to_decimal(Decimal("2.50")) == Decimal("2.50")


# --- realized walk ------------------------------------------------------------

def test_a_partial_trades_banked_tp1_leg_is_realized_at_its_own_time():
    legs = equity.realized_legs([_trade(legs=[TP1], plan_id="P1")])
    assert legs == [equity.RealizedLeg(at=_at(TP1_AT), amount=Decimal("50.0"), trade_id="t1")]


def test_legs_are_sorted_by_time_across_trades():
    trades = [_closed("late", 20.0, "2026-08-05T19:00:00+00:00"),
              _closed("early", -30.0, "2026-08-02T19:00:00+00:00")]
    assert [leg.trade_id for leg in equity.realized_legs(trades)] == ["early", "late"]


def test_weak_and_outlook_trades_never_enter_the_realized_walk():
    trades = [_closed("main", 10.0, "2026-08-02T19:00:00+00:00"),
              _closed("weak", 99.0, "2026-08-02T19:00:00+00:00", ledger="weak"),
              _closed("outlook", 77.0, "2026-08-02T19:00:00+00:00", origin="next_session")]
    assert [leg.trade_id for leg in equity.realized_legs(trades)] == ["main"]


def test_a_leg_with_no_amount_or_no_close_time_is_skipped():
    unsized = _trade("unsized", status="win", pnl=None, closed_at="2026-08-02T19:00:00+00:00",
                     exit_price=105.0, shares=None)
    undated = _closed("undated", 10.0, None)
    assert equity.realized_legs([unsized, undated]) == []


def test_realized_balance_counts_legs_at_or_before_t():
    legs = equity.realized_legs([_closed("a", 10.0, "2026-08-02T19:00:00+00:00"),
                                 _closed("b", -4.0, "2026-08-03T19:00:00+00:00")])
    start = Decimal("1000")
    assert equity.realized_balance_at(start, legs, _at("2026-08-02T18:59:59+00:00")) == Decimal("1000")
    assert equity.realized_balance_at(start, legs, _at("2026-08-02T19:00:00+00:00")) == Decimal("1010.0")
    assert equity.realized_balance_at(start, legs, _at("2026-08-09T00:00:00+00:00")) == Decimal("1006.0")


def test_decimal_sums_match_to_the_cent():
    trades = [_closed("a", 0.1, "2026-08-02T19:00:00+00:00"),
              _closed("b", 0.2, "2026-08-02T20:00:00+00:00")]
    total = equity.realized_balance_at(Decimal("0"), equity.realized_legs(trades),
                                       _at("2026-08-03T00:00:00+00:00"))
    assert total == Decimal("0.3")


def test_the_walk_ends_where_the_existing_equity_curve_ends():
    closed = [_closed("a", 12.5, "2026-08-02T19:00:00+00:00"),
              _closed("b", -7.25, "2026-08-04T19:00:00+00:00"),
              _closed("c", 30.0, "2026-08-06T19:00:00+00:00")]
    curve = metrics.equity_curve(closed, 1000.0)
    walk = equity.realized_balance_at(Decimal("1000"), equity.realized_legs(closed),
                                      _at("2026-09-01T00:00:00+00:00"))
    assert float(walk) == pytest.approx(curve["points"][-1]["balance"])


# --- open positions -----------------------------------------------------------

def test_open_positions_follow_the_dashboard_plan_filter():
    trades = [_trade("legacy"),                                     # no plan -> kept as is
              _trade("pending", plan_id="PP"),                      # PENDING placeholder -> dropped
              _trade("partial", plan_id="PA", legs=[TP1]),          # PARTIAL -> remaining shares
              _trade("weak", ledger="weak"),                        # weak ledger -> dropped
              _closed("closed", 5.0, "2026-08-02T19:00:00+00:00")]  # not open -> dropped
    plans = {"PP": {"plan_id": "PP", "status": "PENDING"},
             "PA": {"plan_id": "PA", "status": "PARTIAL", "legs_realized": [TP1]}}
    live = equity.live_open_positions(trades, plans)
    assert [(p["id"], p["shares"]) for p in live] == [("legacy", 10), ("partial", 5.0)]


def test_held_now_is_the_plan_filter_alone():
    trades = [_trade("weak", ledger="weak", plan_id="PA")]
    plans = {"PA": {"plan_id": "PA", "status": "ACTIVE", "legs_realized": []}}
    assert [p["id"] for p in equity.held_now(trades, plans)] == ["weak"]


# --- snapshot -----------------------------------------------------------------

def _partial_book():
    trade = _trade("partial", plan_id="PA", legs=[TP1])
    plans = {"PA": {"plan_id": "PA", "status": "PARTIAL", "legs_realized": [TP1]}}
    return [trade], plans


def test_snapshot_realizes_the_tp1_leg_and_prices_only_the_runner():
    trades, plans = _partial_book()
    snap = equity.snapshot_at(trades, plans, {"AAPL": 112.0}, _at("2026-08-03T16:00:00+00:00"),
                              Decimal("1000"))
    assert snap == equity.EquitySnapshot(realized_balance=Decimal("1050.0"),
                                         unrealized_pnl=Decimal("60.00"),
                                         equity=Decimal("1110.00"), open_n=1, skipped_n=0)


def test_mark_to_market_does_not_dip_at_tp1():
    before_trade = _trade("partial", plan_id="PA")
    before_plans = {"PA": {"plan_id": "PA", "status": "ACTIVE", "legs_realized": []}}
    before = equity.snapshot_at([before_trade], before_plans, {"AAPL": 110.0},
                                _at("2026-08-03T14:59:00+00:00"), Decimal("1000"))
    trades, plans = _partial_book()
    after = equity.snapshot_at(trades, plans, {"AAPL": 110.0},
                               _at("2026-08-03T15:01:00+00:00"), Decimal("1000"))
    assert before.equity == after.equity == Decimal("1100.00")


def test_unpriced_and_unsized_positions_are_skipped_never_priced_at_zero():
    trades = [_trade("priced", ticker="AAPL"),
              _trade("unpriced", ticker="MSFT"),
              _trade("unsized", ticker="NVDA", shares=None)]
    snap = equity.snapshot_at(trades, {}, {"AAPL": 101.0, "NVDA": 120.0, "MSFT": 0.0},
                              _at("2026-08-03T16:00:00+00:00"), Decimal("1000"))
    assert (snap.unrealized_pnl, snap.open_n, snap.skipped_n) == (Decimal("10.00"), 1, 2)
    assert snap.equity == Decimal("1010.00")


def test_a_weak_open_position_is_never_summed_with_the_main_book():
    trades = [_trade("main"), _trade("weak", ticker="MSFT", ledger="weak")]
    snap = equity.snapshot_at(trades, {}, {"AAPL": 101.0, "MSFT": 200.0},
                              _at("2026-08-03T16:00:00+00:00"), Decimal("0"))
    assert (snap.unrealized_pnl, snap.open_n, snap.skipped_n) == (Decimal("10.00"), 1, 0)


# --- I/O seams ----------------------------------------------------------------

def test_starting_balance_is_the_account_base_balance(monkeypatch):
    monkeypatch.setattr("swingbot.core.planning.account.load_account_config",
                        lambda: {"base_balance": 2500.5})
    assert equity.starting_balance() == Decimal("2500.5")


def test_starting_balance_defaults_to_zero(monkeypatch):
    monkeypatch.setattr("swingbot.core.planning.account.load_account_config", lambda: {})
    assert equity.starting_balance() == Decimal("0.0")


def test_plans_are_keyed_by_plan_id(monkeypatch):
    from swingbot.core.planning.plan_store import PlanStore

    monkeypatch.setattr(PlanStore, "records", lambda self: [{"plan_id": "P1", "status": "ACTIVE"}])
    assert equity.load_plans_by_id() == {"P1": {"plan_id": "P1", "status": "ACTIVE"}}
```

- [ ] **Step 4: Run the tests to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/tracking/test_equity_definition.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.tracking.equity'`.

- [ ] **Step 5: Create the core module**

Create `$WT/swingbot/core/tracking/equity.py`:

```python
"""v172 § 0: the one equity definition.

Every writer and reader of account equity goes through here: the live
recorder (`commands/scanning/equity_recorder.py`), the backfill
(`scripts/data/backfill_equity_samples.py`) and the admin's candle endpoint
(`admin/api_v1/equity.py`). Nothing here imports `swingbot.admin`; the admin
re-imports `unrealized_pnl_amount` and `open_shares` from this module, so the
chart and the Trades page cannot disagree.

- **Book:** the main ledger only (`split_by_ledger(trades)[0]`), for opens
  and closes alike. Weak and outlook trades never enter equity.
- **Realized balance at t:** the account's `base_balance` plus every realized
  leg closed at or before `t`, legs from `expand_realized_legs`, so a PARTIAL
  trade's banked TP1 leg is realized at its own time.
- **Unrealized:** `open_shares x (price - entry) x sign` per held position;
  a position with no size or no price is skipped and counted, never priced
  at 0.
- **Money:** `Decimal` throughout (`Decimal(str(x))`). Rounding to 2 dp
  happens once, in the repository write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import NamedTuple, Sequence

from swingbot.core.tracking.ledger import split_by_ledger
from swingbot.core.tracking.performance import expand_realized_legs

CENT = Decimal("0.01")
_LIVE_PLAN_STATUSES = ("ACTIVE", "PARTIAL")
_ZERO = Decimal("0")


def parse_ts(value: str | datetime | None) -> datetime | None:
    """A tz-aware UTC datetime from an ISO string or datetime; naive is taken
    as UTC (as `api_v1.iso()` does); None or an unparsable string is None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def to_decimal(value) -> Decimal | None:
    """`Decimal(str(x))`, so 0.1 is 0.1 and not its binary neighbour."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def open_shares(shares: float | None, legs_realized: list) -> float | None:
    """The share count still exposed to price movement right now.

    `shares` alone is the ORIGINAL size at open, and stays that number even
    after a TP1 partial has already closed part of the position -- it is a
    snapshot of what was bought, not what is still held. Unrealized P&L on
    the remaining position needs the remainder: a plan that closed half at
    TP1 has half the shares left to move, so its live dollar P&L is half
    what the same price move would be on the original size, even though the
    live PERCENTAGE (which is priced off one share, not the count) is
    unaffected. `legs_realized` is `plan.legs_realized` -- each leg's
    `fraction` is the share of the ORIGINAL position that leg closed (see
    `plan_manager.py`'s `_step_active`/`_close_runner`), so summing them is
    the total fraction gone and `1 -` that is what remains.

    v172: moved here from `admin/api_v1/trades.py` (`_open_shares`), which
    re-imports it under its old name.
    """
    if shares is None:
        return None
    closed_fraction = sum(leg.get("fraction", 0) for leg in legs_realized)
    return round(shares * max(0.0, 1.0 - closed_fraction), 4)


def unrealized_pnl_amount(entry, direction: str, open_shares, price) -> float | None:
    """Live $ P&L on the shares still held, priced at the live quote.

    Deliberately excludes any leg a TP1 partial already banked: since v79
    the Trades table shows that leg as its own CLOSED row with its own
    realized amount, so blending it in here too counted the same profit
    twice -- once on the leg row, again on the PARTIAL runner row.

    v172: moved here unchanged from `admin/dashboard.py`, which re-imports it.
    """
    if not open_shares or entry is None or price is None:
        return None
    sign = 1 if direction == "bullish" else -1
    return round(open_shares * (price - entry) * sign, 2)


def unrealized_decimal(entry, direction: str, open_shares, price) -> Decimal | None:
    """`unrealized_pnl_amount`'s formula in `Decimal`, unrounded."""
    if not open_shares or entry is None or price is None:
        return None
    sign = 1 if direction == "bullish" else -1
    return to_decimal(open_shares) * (to_decimal(price) - to_decimal(entry)) * sign


def main_book(trades: list[dict]) -> list[dict]:
    """The main ledger: weak and outlook trades dropped (v93, v144)."""
    return split_by_ledger(trades)[0]


class RealizedLeg(NamedTuple):
    at: datetime
    amount: Decimal
    trade_id: object


def _leg_of(row: dict) -> RealizedLeg | None:
    """One expanded leg row as a RealizedLeg; None when it has no amount
    (unsized) or no close time, as `equity_curve` skips them."""
    at = parse_ts(row.get("closed_at"))
    amount = row.get("realized_pnl_amount")
    if at is None or amount is None:
        return None
    return RealizedLeg(at=at, amount=to_decimal(amount), trade_id=row.get("id"))


def realized_legs(trades: list[dict]) -> list[RealizedLeg]:
    """Every realized leg of every main-book trade, open PARTIAL trades
    included (their banked TP1 legs), oldest first."""
    legs = []
    for trade in main_book(trades):
        for row in expand_realized_legs(trade):
            leg = _leg_of(row)
            if leg is not None:
                legs.append(leg)
    legs.sort(key=lambda leg: leg.at)
    return legs


def realized_balance_at(start: Decimal, legs: Sequence[RealizedLeg], at: datetime) -> Decimal:
    """`start` plus every leg closed at or before `at`."""
    return start + sum((leg.amount for leg in legs if leg.at <= at), _ZERO)


def starting_balance() -> Decimal:
    """The account's `base_balance` -- `balance` is derived from it."""
    from swingbot.core.planning.account import load_account_config

    return to_decimal(load_account_config().get("base_balance", 0.0)) or Decimal("0.0")


def load_plans_by_id() -> dict:
    """Every stored plan, keyed by `plan_id`."""
    from swingbot.core.planning.plan_store import PlanStore

    return {plan.get("plan_id"): plan for plan in PlanStore().records()}


def held_now(open_trades: list[dict], plans_by_id: dict) -> list[dict]:
    """The open trades that are actually held, sized as they are held now.

    The trade log says "open" for a trade whose plan is still PENDING (not
    filled), and keeps the ORIGINAL share count after a TP1 partial: PENDING
    plans are dropped and a partial runner is sized at its remaining shares.
    A trade with no plan (legacy) is kept as-is. No ledger or status filter:
    the Dashboard card passes its own scoped open trades.
    """
    live = []
    for trade in open_trades:
        plan = plans_by_id.get(trade.get("plan_id"))
        if plan is None:
            live.append(trade)
        elif plan.get("status") in _LIVE_PLAN_STATUSES:
            remaining = open_shares(trade.get("shares"), plan.get("legs_realized") or [])
            live.append({**trade, "shares": remaining})
    return live


def live_open_positions(trades: list[dict], plans_by_id: dict) -> list[dict]:
    """Main-book trades with status `open`, through `held_now`."""
    opened = [trade for trade in main_book(trades) if trade.get("status") == "open"]
    return held_now(opened, plans_by_id)


@dataclass(frozen=True)
class EquitySnapshot:
    realized_balance: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    open_n: int
    skipped_n: int


def _price_of(prices: dict[str, float], ticker) -> float | None:
    """The tick's price for `ticker`; a missing or non-positive quote is None."""
    price = prices.get(ticker)
    return price if price and price > 0 else None


def _unrealized_total(positions: list[dict], prices: dict[str, float]) -> tuple[Decimal, int, int]:
    """(sum, counted, skipped) over `positions` at `prices`."""
    total, counted, skipped = _ZERO, 0, 0
    for position in positions:
        amount = unrealized_decimal(position.get("entry"), position.get("direction"),
                                    position.get("shares"), _price_of(prices, position.get("ticker")))
        if amount is None:
            skipped += 1
            continue
        total += amount
        counted += 1
    return total, counted, skipped


def snapshot_at(trades: list[dict], plans_by_id: dict, prices: dict[str, float],
                at: datetime, start: Decimal) -> EquitySnapshot:
    """Equity at `at`: the realized walk to `at` plus every held position
    priced at `prices` (ticker -> price). Unrounded."""
    realized = realized_balance_at(start, realized_legs(trades), at)
    unrealized, counted, skipped = _unrealized_total(
        live_open_positions(trades, plans_by_id), prices)
    return EquitySnapshot(realized_balance=realized, unrealized_pnl=unrealized,
                          equity=realized + unrealized, open_n=counted, skipped_n=skipped)
```

- [ ] **Step 6: Run the new tests**

```bash
python $WT/scripts/dev/testrun.py file tests/tracking/test_equity_definition.py
```

Expected: every test passes except `test_the_admin_re_imports_the_core_helpers` (the admin still has its own copies).

- [ ] **Step 7: Make the admin re-import the moved helpers**

In `$WT/swingbot/admin/dashboard.py`, delete the whole `def unrealized_pnl_amount(...)` function (lines 165-175, docstring included) and put this in its place:

```python
# v172: moved to swingbot/core/tracking/equity.py (the one equity definition);
# re-imported so `dash.unrealized_pnl_amount` and `_append_amount` below keep working.
from swingbot.core.tracking.equity import unrealized_pnl_amount  # noqa: E402,F401
```

In `$WT/swingbot/admin/api_v1/trades.py`, delete the whole `def _open_shares(...)` function (lines 188-205, docstring included) and add to the import block at the top, right after `from swingbot.core.tracking.performance import TradeLog` (line 42):

```python
from swingbot.core.tracking.equity import open_shares as _open_shares  # v172: moved to core
```

In `$WT/swingbot/admin/api_v1/dashboard.py`, replace `_live_positions` (lines 206-230) with:

```python
def _live_positions(open_trades: list[dict]) -> list[dict]:
    """The open trades that are actually held, sized as they are held now.

    The trade log says "open" for a trade whose plan is still PENDING (not
    filled), and keeps the ORIGINAL share count after a TP1 partial. The
    Positions table keys off the plan, so the card has to as well or its
    figures describe a different book than the table under it: PENDING
    plans are dropped and a partial runner is sized at its remaining shares.
    A trade with no plan (legacy) is kept as-is.

    v172: the filter lives in `core/tracking/equity.held_now`, shared with
    the equity recorder.
    """
    from swingbot.core.tracking.equity import held_now, load_plans_by_id

    return held_now(open_trades, load_plans_by_id())
```

- [ ] **Step 8: Run the new tests and the callers' tests**

```bash
python $WT/scripts/dev/testrun.py file tests/tracking/test_equity_definition.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
git -C $WT grep -ln "unrealized_pnl_amount\|build_open_trade_views\|_live_positions" -- tests
```

Expected: the three files pass with `0 failed`. Run every extra file the last command lists the same way (`testrun.py file <path>`); all pass.

- [ ] **Step 9: Check the import boundary and complexity**

```bash
git -C $WT grep -n "swingbot.admin" -- swingbot/core swingbot/commands
git -C $R grep -n "swingbot.admin" -- swingbot/core swingbot/commands
python -m radon cc -s -n C $WT/swingbot/core/tracking/equity.py $WT/swingbot/admin/api_v1/dashboard.py $WT/swingbot/admin/api_v1/trades.py $WT/swingbot/admin/dashboard.py
```

Expected: the two greps print the same lines (none added by this task). Radon lists no function from `equity.py` and none this task changed; the pre-existing `dashboard()` (21) may appear and is untouched.

- [ ] **Step 10: Record the module in the architecture map**

In `$WT/docs/claude/architecture.md`, the module-map sentence names `` `core/tracking/` (the trade log's write path — `performance.py`, `retrospective.py`, `risk_metrics.py`) ``. Change only that parenthesis to:

```markdown
`core/tracking/` (the trade log's write path — `performance.py`,
  `retrospective.py`, `risk_metrics.py`; v172 `equity.py`, the one equity
  definition — main-book realized legs walk plus open-position unrealized —
  shared by the equity recorder, the backfill and the admin)
```

Re-wrap the surrounding lines to the file's width; nothing else in the sentence changes.

- [ ] **Step 11: Commit on the branch**

```bash
git -C $WT add swingbot/core/tracking/equity.py swingbot/admin/dashboard.py swingbot/admin/api_v1/trades.py swingbot/admin/api_v1/dashboard.py tests/tracking/test_equity_definition.py
git -C $WT commit -m "feat(tracking): one equity definition in core; admin re-imports unrealized_pnl_amount and open_shares (v172)"
git -C $WT add docs/claude/architecture.md
git -C $WT commit -m "docs(architecture): core/tracking/equity.py in the module map (v172)"
git -C $R status --short
```

End each commit message with the attribution line from the session's system reminder. Expected: two commits on `2026-10-17-v172-equity-candlestick-chart`; `$R`'s status shows no change from this task.

### Task V172-2: `equity_samples` table, Alembic `v172_001`, repository

**Model:** opus — schema migration (hybrid-schema contract, single Alembic head, round-trip coverage)

**Files:**
- Modify: `swingbot/core/db/schema.py` (new table after `gate_rejections`, ~line 273; new `PROMOTION_REASONS` entry at the end of the dict, ~line 379)
- Create: `swingbot/core/db/migrations/versions/v172_001_equity_samples.py`
- Create: `swingbot/core/db/repositories/equity_samples.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (import + one `CASES` entry)
- Test: `tests/db/test_equity_samples_repository.py`, `tests/db/test_v172_tables.py` (suite `storage`)

**Interfaces:**
- Consumes (existing): `register`, `standard_columns`, `METADATA`, `PROMOTION_REASONS`, `promoted_for`, `contract_violations` (`swingbot/core/db/schema.py`); `Repository` (`swingbot/core/db/repositories/base.py`: `_tx`, `_record`, `_values`, `insert`, `list_all`); fixtures `db_conn`, `db_engine_empty` (`tests/db/conftest.py`). Nothing from V172-1 (this task runs in parallel with it, so it defines its own `_CENT`).
- Produces (ledger contract, consumed by V172-4, V172-5, V172-7):
  - `schema.equity_samples` (Table)
  - `round_money(value: Decimal | float) -> float` — 2 dp `ROUND_HALF_UP` via `Decimal(str(value))`
  - `class EquitySampleRepository(Repository)`:
    - `insert_sample(row: dict, conn=None) -> int` — new row id; `0` when `(at, source, kind)` already exists (nothing written)
    - `upsert_many(rows: list[dict], conn=None) -> int` — rows written (insert or update on the unique key)
    - `replace_backfill(rows: list[dict], conn=None) -> int` — deletes every `backfill` row and inserts `rows`, one transaction; rows inserted
    - `latest_at(source: str, conn=None) -> datetime | None`, `earliest_at(source: str, conn=None) -> datetime | None`
    - `list_rows(*, sources: tuple[str, ...] = ("live", "backfill"), since: datetime | None = None, conn=None) -> list[dict]` — ordered by `at`, then `id`; each row has `id`; `at` tz-aware UTC
    - `backfill_session_dates(conn=None) -> set[date]` — America/New_York dates of `backfill` rows
    - `update_realized(sample_id: int, realized_balance: Decimal, equity: Decimal, conn=None) -> None`
  - singleton `equity_samples_repo() -> EquitySampleRepository`
  - Row dict keys `at, realized_balance, unrealized_pnl, equity, open_n, skipped_n, source, kind, backfill_run`; money may be `Decimal` or float, rounded by `round_money` on every write; `source` ∈ `SOURCES = ("live", "backfill")`, `kind` ∈ `KINDS = ("point", "day_high", "day_low")`, anything else raises `ValueError`.

- [ ] **Step 1: Confirm the current Alembic head and the template**

```bash
python -m alembic -c $WT/alembic.ini heads
git -C $WT grep -n "^revision\|^down_revision" -- swingbot/core/db/migrations/versions/v147_001_gate_rejections.py swingbot/core/db/migrations/versions/v146_001_confidence_points.py
git -C $WT grep -n "equity_samples" -- swingbot tests
```

Expected: one head, `v146_001` when this plan was written. If the head differs, use that id as `down_revision` in Step 5 and in the test's comment, and say so in the task report. The last grep prints nothing (the table is new).

- [ ] **Step 2: Write the failing schema and migration tests**

Create `$WT/tests/db/test_v172_tables.py`:

```python
"""v172: equity_samples, revision v172_001 -- raw equity samples for the
Dashboard candle chart (live recorder rows and backfill rows)."""
import pathlib

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import schema

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTED = ("at", "realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n",
            "source", "kind", "backfill_run")


def test_the_table_is_registered_with_its_promoted_columns_and_reasons():
    table = schema.METADATA.tables["equity_samples"]
    assert schema.promoted_for("equity_samples") == PROMOTED
    assert set(schema.PROMOTION_REASONS["equity_samples"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    for column in PROMOTED[:-1]:
        assert table.c[column].nullable is False, column
    assert table.c.backfill_run.nullable is True


def test_money_is_double_precision_and_at_is_timestamptz():
    table = schema.equity_samples
    for column in ("realized_balance", "unrealized_pnl", "equity"):
        assert isinstance(table.c[column].type, sa.Float), column
        assert table.c[column].type.precision == 53, column
    assert table.c.at.type.timezone is True
    assert isinstance(table.c.id.type, sa.BigInteger)


def test_the_unique_key_and_the_range_index_are_declared():
    table = schema.equity_samples
    uniques = {c.name: [col.name for col in c.columns] for c in table.constraints
               if isinstance(c, sa.UniqueConstraint)}
    assert uniques["equity_samples_at_source_kind_uq"] == ["at", "source", "kind"]
    indexes = {i.name: [col.name for col in i.columns] for i in table.indexes}
    assert indexes == {"equity_samples_source_at_idx": ["source", "at"]}


def test_v172_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v172_001")
    assert scripts.get_revision(revision.down_revision) is not None
    assert len(scripts.get_heads()) == 1


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_v172_001_downgrade_drops_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "equity_samples" in _tables(connection)
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v172_001").down_revision)
        remaining = _tables(connection)
        assert "equity_samples" not in remaining
        assert "trades" in remaining and "gate_rejections" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "equity_samples" in _tables(connection)
```

- [ ] **Step 3: Write the failing repository tests**

Create `$WT/tests/db/test_equity_samples_repository.py`:

```python
"""v172: EquitySampleRepository -- money rounded once at the write, the
(at, source, kind) key, backfill replace in one transaction, NY session dates."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from swingbot.core.db.repositories.equity_samples import (
    EquitySampleRepository, equity_samples_repo, round_money)

UTC = timezone.utc
OPEN = datetime(2026, 10, 15, 13, 30, tzinfo=UTC)     # 09:30 New York (EDT)
CLOSE = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)     # 16:00 New York


@pytest.fixture
def repo():
    return EquitySampleRepository()


def _row(at, *, source="live", kind="point", equity=Decimal("10100.005"), run=None, skipped=0):
    return {"at": at, "realized_balance": Decimal("10000"), "unrealized_pnl": equity - 10000,
            "equity": equity, "open_n": 2, "skipped_n": skipped, "source": source, "kind": kind,
            "backfill_run": run}


def test_round_money_is_half_up_from_the_decimal_string():
    assert round_money(Decimal("1.005")) == 1.01
    assert round_money(2.675) == 2.68          # float round() would give 2.67
    assert round_money(Decimal("-1.005")) == -1.01
    assert isinstance(round_money(Decimal("3")), float)


def test_insert_sample_rounds_money_once_and_returns_the_id(repo, db_conn):
    sample_id = repo.insert_sample(_row(OPEN), conn=db_conn)
    assert sample_id > 0
    (row,) = repo.list_rows(conn=db_conn)
    assert row["id"] == sample_id
    assert (row["equity"], row["unrealized_pnl"], row["realized_balance"]) == (10100.01, 100.01, 10000.0)
    assert row["at"] == OPEN and row["at"].utcoffset() == timedelta(0)
    assert (row["open_n"], row["skipped_n"], row["source"], row["kind"]) == (2, 0, "live", "point")


def test_a_second_sample_on_the_same_key_writes_nothing(repo, db_conn):
    assert repo.insert_sample(_row(OPEN), conn=db_conn) > 0
    assert repo.insert_sample(_row(OPEN, equity=Decimal("1")), conn=db_conn) == 0
    (row,) = repo.list_rows(conn=db_conn)
    assert row["equity"] == 10100.01


@pytest.mark.parametrize("field, value", [("source", "guess"), ("kind", "close")])
def test_an_unknown_source_or_kind_is_refused(repo, db_conn, field, value):
    with pytest.raises(ValueError):
        repo.insert_sample({**_row(OPEN), field: value}, conn=db_conn)


def test_upsert_many_updates_on_the_unique_key(repo, db_conn):
    first = [_row(OPEN, source="backfill", run="r1"),
             _row(OPEN, source="backfill", kind="day_high", equity=Decimal("10300"), run="r1")]
    assert repo.upsert_many(first, conn=db_conn) == 2
    assert repo.upsert_many([_row(OPEN, source="backfill", equity=Decimal("9990"), run="r2")],
                            conn=db_conn) == 1
    rows = {row["kind"]: row for row in repo.list_rows(conn=db_conn)}
    assert (rows["point"]["equity"], rows["point"]["backfill_run"]) == (9990.0, "r2")
    assert rows["day_high"]["backfill_run"] == "r1"
    assert repo.upsert_many([], conn=db_conn) == 0


def test_replace_backfill_drops_every_backfill_row_and_keeps_live(repo, db_conn):
    repo.insert_sample(_row(CLOSE + timedelta(days=1)), conn=db_conn)
    repo.upsert_many([_row(OPEN, source="backfill", run="old"),
                      _row(CLOSE, source="backfill", run="old")], conn=db_conn)
    assert repo.replace_backfill([_row(CLOSE, source="backfill", run="new")], conn=db_conn) == 1
    rows = repo.list_rows(conn=db_conn)
    assert [(r["source"], r.get("backfill_run")) for r in rows] == [("backfill", "new"), ("live", None)]   # a NULL column reads back absent


def test_replace_backfill_refuses_a_live_row(repo, db_conn):
    with pytest.raises(ValueError):
        repo.replace_backfill([_row(OPEN)], conn=db_conn)


def test_latest_and_earliest_are_per_source(repo, db_conn):
    assert repo.latest_at("live", conn=db_conn) is None
    assert repo.earliest_at("live", conn=db_conn) is None
    repo.insert_sample(_row(OPEN), conn=db_conn)
    repo.insert_sample(_row(CLOSE), conn=db_conn)
    repo.upsert_many([_row(OPEN - timedelta(days=3), source="backfill")], conn=db_conn)
    assert repo.earliest_at("live", conn=db_conn) == OPEN
    assert repo.latest_at("live", conn=db_conn) == CLOSE
    assert repo.earliest_at("backfill", conn=db_conn) == OPEN - timedelta(days=3)


def test_list_rows_filters_by_source_and_since_in_time_order(repo, db_conn):
    repo.insert_sample(_row(CLOSE), conn=db_conn)
    repo.insert_sample(_row(OPEN), conn=db_conn)
    repo.upsert_many([_row(OPEN - timedelta(days=1), source="backfill")], conn=db_conn)
    assert [r["at"] for r in repo.list_rows(conn=db_conn)] == [OPEN - timedelta(days=1), OPEN, CLOSE]
    assert [r["at"] for r in repo.list_rows(sources=("live",), conn=db_conn)] == [OPEN, CLOSE]
    assert [r["at"] for r in repo.list_rows(since=CLOSE, conn=db_conn)] == [CLOSE]


def test_backfill_session_dates_are_new_york_dates(repo, db_conn):
    late = datetime(2026, 10, 17, 2, 0, tzinfo=UTC)          # 22:00 New York on the 16th
    repo.upsert_many([_row(OPEN, source="backfill"), _row(late, source="backfill")], conn=db_conn)
    repo.insert_sample(_row(datetime(2026, 10, 20, 14, 0, tzinfo=UTC)), conn=db_conn)
    assert repo.backfill_session_dates(conn=db_conn) == {date(2026, 10, 15), date(2026, 10, 16)}


def test_update_realized_rewrites_only_the_realized_columns(repo, db_conn):
    sample_id = repo.insert_sample(_row(OPEN), conn=db_conn)
    repo.update_realized(sample_id, Decimal("9000.004"), Decimal("9100.015"), conn=db_conn)
    (row,) = repo.list_rows(conn=db_conn)
    assert (row["realized_balance"], row["equity"], row["unrealized_pnl"]) == (9000.0, 9100.02, 100.01)


def test_the_accessor_is_a_singleton():
    assert equity_samples_repo() is equity_samples_repo()
```

Add the round-trip case. In `$WT/tests/db/test_unknown_field_round_trip.py`, add the import in alphabetical place (after `from swingbot.core.db.repositories.base import Repository`):

```python
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
```

and add this entry to `CASES`, after the `"gate_rejections"` entry:

```python
    "equity_samples": (EquitySampleRepository, {"at": TS, "realized_balance": 0.0, "unrealized_pnl": 0.0,
                                                "equity": 0.0, "open_n": 0, "skipped_n": 0,
                                                "source": "live", "kind": "point"}),
```

- [ ] **Step 4: Run the tests to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/db/test_v172_tables.py
python $WT/scripts/dev/testrun.py file tests/db/test_equity_samples_repository.py
```

Expected: `KeyError: 'equity_samples'` / `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.equity_samples'`. (If the run says the test database is down, start it with the command it prints and re-run.)

- [ ] **Step 5: Declare the table and its promotion reasons**

In `$WT/swingbot/core/db/schema.py`, after the `gate_rejections = register(...)` statement (ends ~line 272), add:

```python
# v172: raw equity samples behind the Dashboard candle chart. `live` rows are written by the
# trade monitor's recorder (one `point` per 5 minutes in regular hours); `backfill` rows by
# scripts/data/backfill_equity_samples.py (four per session day). Candles are built on request
# (admin/api_v1/equity.py); nothing is pre-aggregated. No SSE event (not in TABLE_CHANNELS).
equity_samples = register(sa.Table("equity_samples", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("realized_balance", sa.Float(53), nullable=False),
    sa.Column("unrealized_pnl", sa.Float(53), nullable=False),
    sa.Column("equity", sa.Float(53), nullable=False),
    sa.Column("open_n", sa.Integer, nullable=False),
    sa.Column("skipped_n", sa.Integer, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("backfill_run", sa.Text),
    *standard_columns(),
    sa.UniqueConstraint("at", "source", "kind", name="equity_samples_at_source_kind_uq"),
    sa.Index("equity_samples_source_at_idx", "source", "at")),
    ("at", "realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n", "source", "kind",
     "backfill_run"))
```

At the end of the `PROMOTION_REASONS` dict, after the `"gate_rejections": {...},` entry, add:

```python
    "equity_samples": {
        "at": "equity_samples_at_source_kind_uq and equity_samples_source_at_idx; the bucket time",
        "realized_balance": "NOT NULL money the realized basis and --recompute-realized rewrite",
        "unrealized_pnl": "NOT NULL measured money; kept when --recompute-realized rewrites the rest",
        "equity": "NOT NULL money every mark-to-market candle's O/H/L/C is read from",
        "open_n": "NOT NULL count of positions priced into the sample",
        "skipped_n": "NOT NULL count of positions left out; the candle's skipped note",
        "source": "equity_samples_at_source_kind_uq and the range index; live vs backfill filter",
        "kind": "equity_samples_at_source_kind_uq; point vs day_high/day_low, o/c read points only",
        "backfill_run": "names the run and bar date a backfill row was built from; NULL on live rows",
    },
```

- [ ] **Step 6: Write the migration**

Create `$WT/swingbot/core/db/migrations/versions/v172_001_equity_samples.py`:

```python
"""equity_samples: raw equity samples for the Dashboard candle chart (v172).

Additive: rollback is this revision's downgrade (drop the table); leaving
the table in place after a code rollback is also safe.

Revision ID: v172_001
Revises: v146_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v172_001"
down_revision = "v146_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equity_samples",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("realized_balance", sa.Float(53), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(53), nullable=False),
        sa.Column("equity", sa.Float(53), nullable=False),
        sa.Column("open_n", sa.Integer, nullable=False),
        sa.Column("skipped_n", sa.Integer, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("backfill_run", sa.Text),
        sa.Column("doc", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("at", "source", "kind", name="equity_samples_at_source_kind_uq"),
    )
    op.create_index("equity_samples_source_at_idx", "equity_samples", ["source", "at"])


def downgrade() -> None:
    op.drop_index("equity_samples_source_at_idx", table_name="equity_samples")
    op.drop_table("equity_samples")
```

If Step 1 found a head other than `v146_001`, write that id in `down_revision` and in the `Revises:` line.

- [ ] **Step 7: Write the repository**

Create `$WT/swingbot/core/db/repositories/equity_samples.py`:

```python
"""v172: raw equity samples (`equity_samples`) behind the Dashboard candle chart.

Writers: the trade monitor's recorder (`commands/scanning/equity_recorder.py`,
`insert_sample`) and `scripts/data/backfill_equity_samples.py` (`upsert_many`,
`replace_backfill`, `update_realized`). Reader: `admin/api_v1/equity.py`
(`list_rows`, `earliest_at`). Money arrives as `Decimal` (or float) and is
rounded to 2 dp ROUND_HALF_UP exactly once, here, on every write. The table
raises no SSE event.
"""
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import equity_samples

SOURCES = ("live", "backfill")
KINDS = ("point", "day_high", "day_low")
KEY_CONSTRAINT = "equity_samples_at_source_kind_uq"
MONEY_FIELDS = ("realized_balance", "unrealized_pnl", "equity")
_CENT = Decimal("0.01")
#: The NYSE clock, restated so the db layer imports nothing from core/market.
_NEW_YORK = ZoneInfo("America/New_York")


def round_money(value: Decimal | float) -> float:
    """2 dp, ROUND_HALF_UP, via `Decimal(str(value))` -- the one rounding."""
    return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP))


def _as_utc(value) -> dt.datetime:
    """A tz-aware UTC datetime from a datetime or ISO string; naive is UTC."""
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _prepared(row: dict) -> dict:
    """`row` checked and normalised for a write: known source/kind, UTC `at`,
    money rounded once, counts as ints."""
    if row.get("source") not in SOURCES:
        raise ValueError(f"source {row.get('source')!r} is not one of {SOURCES}")
    if row.get("kind") not in KINDS:
        raise ValueError(f"kind {row.get('kind')!r} is not one of {KINDS}")
    prepared = {**row, "at": _as_utc(row["at"]),
                "open_n": int(row["open_n"]), "skipped_n": int(row["skipped_n"])}
    for field in MONEY_FIELDS:
        prepared[field] = round_money(row[field])
    return prepared


class EquitySampleRepository(Repository):
    def __init__(self):
        super().__init__(equity_samples, key="id")

    def _with_id(self, row) -> dict:
        record = {**self._record(row), "id": row.id}
        record["at"] = _as_utc(record["at"])
        return record

    def insert_sample(self, row: dict, conn=None) -> int:
        """Insert one sample; its id, or 0 (nothing written) when its
        (at, source, kind) already exists."""
        statement = (pg_insert(self.table).values(**self._values(_prepared(row)))
                     .on_conflict_do_nothing(constraint=KEY_CONSTRAINT)
                     .returning(self.table.c.id))
        with self._tx(conn) as connection:
            inserted = connection.execute(statement).first()
        return 0 if inserted is None else int(inserted.id)

    def upsert_many(self, rows: list[dict], conn=None) -> int:
        """Insert `rows`, updating any whose (at, source, kind) exists; the count written."""
        if not rows:
            return 0
        values = [self._values(_prepared(row)) for row in rows]
        statement = pg_insert(self.table).values(values)
        updates = {name: statement.excluded[name] for name in values[0] if name != "id"}
        updates["updated_at"] = sa.func.clock_timestamp()
        statement = statement.on_conflict_do_update(constraint=KEY_CONSTRAINT, set_=updates)
        with self._tx(conn) as connection:
            connection.execute(statement)
        return len(rows)

    def replace_backfill(self, rows: list[dict], conn=None) -> int:
        """Delete every backfill row and insert `rows`, in one transaction."""
        if any(row.get("source") != "backfill" for row in rows):
            raise ValueError("replace_backfill writes backfill rows only")
        values = [self._values(_prepared(row)) for row in rows]
        with self._tx(conn) as connection:
            connection.execute(sa.delete(self.table).where(self.table.c.source == "backfill"))
            if values:
                connection.execute(sa.insert(self.table).values(values))
        return len(values)

    def _edge_at(self, func, source: str, conn) -> dt.datetime | None:
        statement = sa.select(func(self.table.c.at)).where(self.table.c.source == source)
        with self._tx(conn) as connection:
            value = connection.execute(statement).scalar_one()
        return None if value is None else _as_utc(value)

    def latest_at(self, source: str, conn=None) -> dt.datetime | None:
        """The newest sample time of `source`, or None when it has none."""
        return self._edge_at(sa.func.max, source, conn)

    def earliest_at(self, source: str, conn=None) -> dt.datetime | None:
        """The oldest sample time of `source`, or None when it has none."""
        return self._edge_at(sa.func.min, source, conn)

    def list_rows(self, *, sources: tuple[str, ...] = SOURCES, since: dt.datetime | None = None,
                  conn=None) -> list[dict]:
        """Rows of `sources` at or after `since`, ordered by `at` then `id`."""
        statement = (sa.select(self.table).where(self.table.c.source.in_(sources))
                     .order_by(self.table.c.at, self.table.c.id))
        if since is not None:
            statement = statement.where(self.table.c.at >= _as_utc(since))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._with_id(row) for row in rows]

    def backfill_session_dates(self, conn=None) -> set[dt.date]:
        """New York calendar dates that already hold backfill rows."""
        statement = (sa.select(self.table.c.at).distinct()
                     .where(self.table.c.source == "backfill"))
        with self._tx(conn) as connection:
            stamps = connection.execute(statement).scalars().all()
        return {_as_utc(stamp).astimezone(_NEW_YORK).date() for stamp in stamps}

    def update_realized(self, sample_id: int, realized_balance: Decimal, equity: Decimal,
                        conn=None) -> None:
        """Rewrite one row's realized balance and equity; `unrealized_pnl` is kept."""
        statement = (sa.update(self.table).where(self.table.c.id == sample_id)
                     .values(realized_balance=round_money(realized_balance),
                             equity=round_money(equity),
                             updated_at=sa.func.clock_timestamp()))
        with self._tx(conn) as connection:
            connection.execute(statement)


_repo: EquitySampleRepository | None = None


def equity_samples_repo() -> EquitySampleRepository:
    global _repo
    if _repo is None:
        _repo = EquitySampleRepository()
    return _repo
```

Note on `upsert_many`: `values[0]` keys are the promoted columns plus `doc` (from `Repository._values`), so the update set is every column the row carries; `id` never appears (it is a reserved key). Rows passed to one call must have distinct `(at, source, kind)` keys (Postgres refuses to update the same row twice in one statement); the backfill builds one row per key.

- [ ] **Step 8: Run the tests to see them pass**

```bash
python $WT/scripts/dev/testrun.py file tests/db/test_v172_tables.py
python $WT/scripts/dev/testrun.py file tests/db/test_equity_samples_repository.py
python $WT/scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py
python $WT/scripts/dev/testrun.py file tests/db/test_migrations.py
python $WT/scripts/dev/testrun.py file tests/db/test_schema_contract.py
python $WT/scripts/dev/testrun.py file tests/db/test_schema.py
python $WT/scripts/dev/testrun.py file tests/db/test_db_diff.py
python $WT/scripts/dev/testrun.py file tests/db/test_trigger_coverage.py
```

Expected: every file passes with `0 failed` and `0 xfailed`. `test_db_diff.py` compares the migrated schema with `METADATA`: a failure there means Step 5 and Step 6 disagree (column type, nullability, default, constraint or index name) — make them identical, never relax the test.

- [ ] **Step 9: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/core/db/repositories/equity_samples.py
```

Expected: no output (every function below C).

- [ ] **Step 10: Commit on the branch**

```bash
git -C $WT add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v172_001_equity_samples.py tests/db/test_v172_tables.py
git -C $WT commit -m "feat(db): equity_samples table, Alembic v172_001 (v172)"
git -C $WT add swingbot/core/db/repositories/equity_samples.py tests/db/test_equity_samples_repository.py tests/db/test_unknown_field_round_trip.py
git -C $WT commit -m "feat(db): EquitySampleRepository -- money rounded once, backfill replace in one transaction (v172)"
git -C $R status --short
```

End each commit message with the attribution line from the session's system reminder. Expected: two commits on the branch; `$R`'s status shows no change from this task.

