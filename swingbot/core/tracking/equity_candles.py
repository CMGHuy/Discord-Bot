"""v172 § 4: equity candles, built on request from raw samples or realized legs.

Pure functions, no I/O. Buckets follow the New York wall clock: 1H = clock
hours; 4H starts at 00/04/08/12/16/20 (3 or 5 real hours on DST days); 1D =
the New York calendar day; 1W starts Monday. A bucket with nothing in it
produces no candle.

- **mtm:** `o`/`c` = the earliest/latest `point` row's `equity`; `h`/`l`
  over every row (backfill `day_high`/`day_low` included); `skipped` = the
  max `skipped_n`; `approx` = any backfill row. 1H/4H read `live` rows only.
- **realized:** each leg is a step; `o` = the balance before the bucket's
  first leg, `h`/`l` across the steps (and `o`), `c` = after the last.
- `change` is against the previous candle's `c` (the first against its own
  `o`); `change_pct` is that over the base x 100, 2 dp, None on a 0 base.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.tracking.equity import CENT, RealizedLeg, to_decimal

TIMEFRAMES = ("1H", "4H", "1D", "1W")
_INTRADAY = ("1H", "4H")


def _floor_hour(local: datetime) -> datetime:
    # replace() keeps `fold`, so the repeated 01:00 on fall-back day stays two hours.
    return local.replace(minute=0, second=0, microsecond=0)


def _floor_4h(local: datetime) -> datetime:
    return local.replace(hour=local.hour - local.hour % 4, minute=0, second=0, microsecond=0,
                         fold=0)


def _floor_day(local: datetime) -> datetime:
    return local.replace(hour=0, minute=0, second=0, microsecond=0, fold=0)


def _floor_week(local: datetime) -> datetime:
    monday = local.date() - timedelta(days=local.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=US_MARKET_TZ)


_FLOORS = {"1H": _floor_hour, "4H": _floor_4h, "1D": _floor_day, "1W": _floor_week}


def bucket_start(at: datetime, tf: str) -> datetime:
    """The New York-aware start of the `tf` bucket holding instant `at`."""
    floor = _FLOORS.get(tf)
    if floor is None:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    return floor(at.astimezone(US_MARKET_TZ))


def bucket_label(start: datetime, tf: str) -> str:
    """`t` of a candle: ISO date for 1D/1W, ISO datetime with offset for 1H/4H."""
    if tf in _INTRADAY:
        return start.isoformat(timespec="seconds")
    return start.date().isoformat()


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _pct(change: Decimal, base: Decimal) -> float | None:
    if base == 0:
        return None
    return float((change / base * 100).quantize(CENT, rounding=ROUND_HALF_UP))


def add_change(candles: list[dict]) -> list[dict]:
    """The final candle dicts, in order, with `change`/`change_pct` against
    the previous candle's close (the first against its own open)."""
    out, previous = [], None
    for candle in candles:
        o, h, l, c = (to_decimal(candle[key]) for key in ("o", "h", "l", "c"))
        base = o if previous is None else previous
        change = c - base
        out.append({"t": candle["t"], "o": _money(o), "h": _money(h), "l": _money(l),
                    "c": _money(c), "change": _money(change), "change_pct": _pct(change, base),
                    "samples": candle["samples"], "skipped": candle["skipped"],
                    "approx": candle["approx"]})
        previous = c
    return out


def _group(items: list, at_of, tf: str) -> dict[str, list]:
    """Items grouped by bucket label, buckets in time order (items sorted first)."""
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(bucket_label(bucket_start(at_of(item), tf), tf), []).append(item)
    return groups


def _mtm_candle(label: str, rows: list[dict]) -> dict | None:
    points = [row for row in rows if row["kind"] == "point"]
    if not points:
        return None
    values = [to_decimal(row["equity"]) for row in rows]
    return {"t": label, "o": to_decimal(points[0]["equity"]), "h": max(values), "l": min(values),
            "c": to_decimal(points[-1]["equity"]), "samples": len(rows),
            "skipped": max(int(row.get("skipped_n") or 0) for row in rows),
            "approx": any(row["source"] == "backfill" for row in rows)}


def mtm_candles(rows: list[dict], tf: str) -> list[dict]:
    """Mark-to-market candles from `equity_samples` rows."""
    if tf not in TIMEFRAMES:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    usable = [row for row in rows if tf not in _INTRADAY or row["source"] == "live"]
    usable.sort(key=lambda row: (row["at"], row.get("id") or 0))
    candles = (_mtm_candle(label, bucket) for label, bucket in
               _group(usable, lambda row: row["at"], tf).items())
    return add_change([candle for candle in candles if candle is not None])


def realized_candles(legs: Sequence[RealizedLeg], start: Decimal, tf: str) -> list[dict]:
    """Closed-trades-only candles: one step per realized leg."""
    if tf not in TIMEFRAMES:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    balance = to_decimal(start)
    candles = []
    for label, bucket in _group(sorted(legs, key=lambda leg: leg.at), lambda leg: leg.at, tf).items():
        opening, steps = balance, []
        for leg in bucket:
            balance += leg.amount
            steps.append(balance)
        candles.append({"t": label, "o": opening, "h": max([opening, *steps]),
                        "l": min([opening, *steps]), "c": steps[-1], "samples": len(steps),
                        "skipped": 0, "approx": False})
    return add_change(candles)
