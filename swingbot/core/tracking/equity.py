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
