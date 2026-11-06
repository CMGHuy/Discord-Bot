"""v208 account and index session series, with no I/O, clock or config.

Returns are fractions. Rows belong to their New York calendar date, and the
account close comes from the same daily candles as the Dashboard.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from swingbot.core.market.session import US_MARKET_TZ, session_close
from swingbot.core.tracking.equity import RealizedLeg, session_trade_pnl, to_decimal
from swingbot.core.tracking.equity_candles import mtm_candles

BREAK_TOLERANCE = Decimal("0.01")
DEPLOYED_MIN_SHARE = 0.05
_IndexDay = dict[str, tuple[float | None, bool]]


@dataclass(frozen=True)
class AlignedDay:
    session: date
    bot_close: float | None
    bot_ret: float | None
    span: int
    index_ret: dict[str, float | None]
    index_proxy: dict[str, bool]
    missing: bool
    base_break: bool

    @property
    def one_session(self) -> bool:
        return self.span == 1 and not self.missing and not self.base_break and self.bot_ret is not None


@dataclass(frozen=True)
class Exposure:
    pct: float | None
    open_n: int
    approx: bool


@dataclass(frozen=True)
class Deployed:
    ret: float | None
    clipped: bool
    approx: bool
    reason: str | None


_MISSING_DEPLOYED = Deployed(None, False, False, "missing")


def _ny_day(at: datetime) -> date:
    return at.astimezone(US_MARKET_TZ).date()


def _session_points(rows: list[dict], sessions: Sequence[date]) -> dict[date, list[dict]]:
    session_set = set(sessions)
    points = defaultdict(list)
    for row in rows:
        if row["kind"] != "point":
            continue
        day = _ny_day(row["at"])
        if day in session_set:
            points[day].append(row)
    for group in points.values():
        group.sort(key=lambda row: (row["at"], row.get("id") or 0))
    return dict(points)


def rows_by_session(rows: list[dict], sessions: Sequence[date]) -> dict[date, list[dict]]:
    """Group point rows by New York session in timestamp and ID order."""
    return _session_points(rows, sessions)


def _close_at(day: date) -> datetime:
    """Return the official session close as a UTC instant, including half days."""
    return datetime.combine(day, session_close(day), US_MARKET_TZ).astimezone(timezone.utc)


def _weights(points: list[dict], day: date) -> list[float]:
    """Weight usable samples until the next sample or the official close."""
    stamps = [row["at"] for row in points]
    stamps.append(_close_at(day))
    return [max(0.0, (end - start).total_seconds()) for start, end in zip(stamps, stamps[1:])]


def _usable(points: list[dict]) -> list[dict]:
    """Use only samples with recorded notional and positive equity."""
    return [row for row in points if row.get("open_notional") is not None and row["equity"] > 0]


def _approx(rows: list[dict]) -> bool:
    """Carry the approximation flag from any contributing row."""
    return any(row.get("open_notional_approx") for row in rows)


def _exposure_day(day: date, points: list[dict]) -> Exposure:
    samples = _usable(points)
    open_n = max((row["open_n"] for row in points), default=0)
    if not samples:
        return Exposure(None, open_n, False)

    shares = [row["open_notional"] / row["equity"] for row in samples]
    weights = _weights(samples, day)
    total = sum(weights)
    weighted_sum = sum(share * weight for share, weight in zip(shares, weights))
    pct = weighted_sum / total if total else sum(shares) / len(shares)
    return Exposure(pct, open_n, _approx(samples))


def exposure_by_session(by_day: dict[date, list[dict]]) -> dict[date, Exposure]:
    """Measure time-weighted exposure, using the plain mean at zero duration."""
    return {day: _exposure_day(day, points) for day, points in by_day.items()}


def _peak_notional(rows: list[dict]) -> float | None:
    """Use peak notional so brief intraday positions receive their full denominator."""
    notionals = (row.get("open_notional") for row in rows)
    return max((notional for notional in notionals if notional is not None), default=None)


def _deployed_day(points: list[dict], prev: dict, legs: list[RealizedLeg]) -> Deployed:
    """Divide trade P&L by peak notional. Base balance and cash are excluded from P&L."""
    rows = [prev, *points]
    approx = _approx(rows)
    peak = _peak_notional(rows)
    close = points[-1]
    if peak is None:
        return Deployed(None, False, approx, "missing")
    if peak <= 0:
        return Deployed(None, False, approx, "no_exposure")
    # Compare the decimal amounts so an exact 5% position passes the floor.
    minimum = to_decimal(DEPLOYED_MIN_SHARE) * to_decimal(close["equity"])
    if to_decimal(peak) < minimum:
        return Deployed(None, False, approx, "below_min")

    pnl = session_trade_pnl(
        legs, prev["at"], close["at"],
        to_decimal(prev["unrealized_pnl"]), to_decimal(close["unrealized_pnl"]),
    )
    ret = float(pnl) / peak
    if ret < -1.0:
        return Deployed(-1.0, True, approx, None)
    return Deployed(ret, False, approx, None)


def deployed_returns(
    by_day: dict[date, list[dict]], legs: list[RealizedLeg], sessions: Sequence[date],
) -> dict[date, Deployed]:
    """Measure each requested session against the last earlier session with rows."""
    requested = set(sessions)
    out = {}
    prev = None
    for day in sorted(requested | by_day.keys()):
        points = by_day.get(day)
        if day in requested:
            out[day] = _deployed_day(points, prev, legs) if points and prev is not None else _MISSING_DEPLOYED
        if points:
            prev = points[-1]
    return out


def bot_session_closes(rows: list[dict], sessions: Sequence[date]) -> dict[date, float]:
    session_set = set(sessions)
    closes = {}
    for candle in mtm_candles(rows, "1D"):
        day = date.fromisoformat(candle["t"])
        if day in session_set:
            closes[day] = candle["c"]
    return closes


def _legs_between(legs: list[RealizedLeg], start: datetime, end: datetime) -> Decimal:
    return sum((leg.amount for leg in legs if start < leg.at <= end), Decimal(0))


def base_balance_breaks(rows: list[dict], legs: list[RealizedLeg], sessions: Sequence[date]) -> set[date]:
    """Flag closing realized balance changes unexplained by realized legs."""
    points = _session_points(rows, sessions)
    breaks = set()
    previous = None
    for session in sessions:
        if session not in points:
            continue
        last = points[session][-1]
        if previous is not None:
            realized = to_decimal(last["realized_balance"]) - to_decimal(previous["realized_balance"])
            explained = _legs_between(legs, previous["at"], last["at"])
            if abs(realized - explained) > BREAK_TOLERANCE:
                breaks.add(session)
        previous = last
    return breaks


def _missing_day(session: date, own: _IndexDay, base_break: bool) -> AlignedDay:
    return AlignedDay(
        session, None, None, 1, dict.fromkeys(own),
        {symbol: proxy for symbol, (_, proxy) in own.items()}, True, base_break,
    )


def _compound_return(symbol: str, span_days: list[_IndexDay]) -> float | None:
    growth = 1.0
    for day in span_days:
        pct, _ = day[symbol]
        if pct is None:
            return None
        growth *= 1 + pct
    return growth - 1


def _compound(span_days: list[_IndexDay]) -> dict[str, float | None]:
    if len(span_days) == 1:
        return {symbol: pct for symbol, (pct, _) in span_days[0].items()}
    return {symbol: _compound_return(symbol, span_days) for symbol in span_days[0]}


def _any_proxy(span_days: list[_IndexDay]) -> dict[str, bool]:
    return {symbol: any(day[symbol][1] for day in span_days) for symbol in span_days[0]}


def align(
    sessions: Sequence[date],
    closes: dict[date, float],
    index_pct: dict[str, dict[date, tuple[float | None, bool]]],
    breaks: set[date],
) -> list[AlignedDay]:
    """Pair each account return with index returns covering the same sessions."""
    days = []
    previous_close = None
    pending = []
    for session in sessions:
        own = {symbol: by_day.get(session, (None, False)) for symbol, by_day in index_pct.items()}
        close = closes.get(session)
        base_break = session in breaks
        if close is None:
            days.append(_missing_day(session, own, base_break))
            if previous_close is not None:
                pending.append(own)
            continue
        span_days = pending + [own]
        bot_ret = None if previous_close in (None, 0.0) else close / previous_close - 1
        days.append(AlignedDay(
            session, close, bot_ret, len(span_days), _compound(span_days),
            _any_proxy(span_days), False, base_break,
        ))
        previous_close = close
        pending = []
    return days
