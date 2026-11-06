"""v208 benchmark chart and exposure view with no I/O or clock reads.

Inputs supply the current time. Returns stay fractional until serialization
through pct(). Provisional bars and today's partial candle stay out of the
completed chart days.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from datetime import date, datetime

from swingbot.core.analytics import benchmark_series as bs
from swingbot.core.analytics.benchmark_series import AlignedDay, Deployed, Exposure
from swingbot.core.market.session import is_nyse_regular_session, now_et, nyse_calendar, session_close
from swingbot.core.marketdata.benchmarks import BENCHMARK_SYMBOLS, TOTAL_RETURN
from swingbot.core.tracking.equity import RealizedLeg

SERIES_KEYS = ("bot_account", "bot_deployed", *BENCHMARK_SYMBOLS)
LABELS = {
    "bot_account": "Bot · account",
    "bot_deployed": "Bot · deployed",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "^IXIC": "Nasdaq Comp. (price)",
    "^DJI": "Dow (price)",
}


def pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100, 4)


@dataclass(frozen=True)
class BenchmarkInputs:
    """Data loaded by the benchmark route.

    Rows come from equity_samples_repo().list_rows(), and legs come from
    equity.realized_legs(equity.main_book(trades)). Sessions come from
    nyse_calendar().sessions(live_since, market_today(now)), or are empty
    when there are no rows. Bars come from benchmark_bars_repo().list_range(
    BENCHMARK_SYMBOLS, sessions[0], sessions[-1]) when there are sessions.
    Now is an aware UTC timestamp.
    """

    rows: list[dict]
    legs: list[RealizedLeg]
    bars: list[dict]
    sessions: list[date]
    now: datetime
    account_currency: str
    mixed_tickers: list[str]
    refresher_on: bool


def _today(now: datetime) -> date:
    return now_et(now).date()


def view_session_state(now: datetime) -> str:
    if is_nyse_regular_session(now):
        return "open"
    et = now_et(now)
    today = et.date()
    if nyse_calendar().is_session(today) and et.time() >= session_close(today):
        return "closed"
    return "pre"


def live_since_of(rows: list[dict]) -> date | None:
    earliest = min((row["at"] for row in rows), default=None)
    return _today(earliest) if earliest is not None else None


def _final_today(bars: list[dict], today: date) -> bool:
    final_symbols = {bar["symbol"] for bar in bars if bar["final"] and bar["session"] == today}
    return final_symbols.issuperset(BENCHMARK_SYMBOLS)


def completed_sessions(inputs: BenchmarkInputs, state: str) -> list[date]:
    today = _today(inputs.now)
    include_today = state == "closed" and _final_today(inputs.bars, today)
    return [day for day in inputs.sessions if day < today or (day == today and include_today)]


@dataclass(frozen=True)
class RangeSpec:
    sessions: list[date]
    base: date | None
    live_since: date | None
    clamped: bool
    is_all: bool


def clamp_range(
    completed: list[date], live_since: date | None, start: date | None, end: date | None,
) -> RangeSpec:
    eligible = completed[bisect_left(completed, live_since):] if live_since is not None else []
    first = bisect_left(eligible, start) if start is not None else 0
    stop = bisect_right(eligible, end) if end is not None else len(eligible)
    if first >= stop:
        return RangeSpec([], None, live_since, False, start is None and end is None)
    base = eligible[first - 1] if first else None
    clamped = start is not None and start < eligible[0]
    return RangeSpec(eligible[first:stop], base, live_since, clamped, first == 0 and stop == len(eligible))


def index_pct(
    bars: list[dict], *, final_only: bool = True,
) -> dict[str, dict[date, tuple[float | None, bool]]]:
    indexed: dict[str, dict[date, tuple[float | None, bool]]] = {
        symbol: {} for symbol in BENCHMARK_SYMBOLS
    }
    for bar in bars:
        symbol = bar["symbol"]
        if symbol in indexed and (bar["final"] or not final_only):
            indexed[symbol][bar["session"]] = (bar["day_pct"], bar["source_symbol"] != symbol)
    return indexed


@dataclass(frozen=True)
class Frame:
    """Completed chart days and session values through today."""

    rng: RangeSpec
    days: list[AlignedDay]
    base_close: float | None
    closes: dict[date, float]
    deployed: dict[date, Deployed]
    exposure: dict[date, Exposure]
    pct: dict[str, dict[date, tuple[float | None, bool]]]


def _trim_first_span(days: list[AlignedDay]) -> list[AlignedDay]:
    for position, day in enumerate(days):
        if not day.missing:
            if day.span > position + 1:
                days[position] = replace(day, bot_ret=None)
            break
    return days


def build_frame(inputs: BenchmarkInputs, rng: RangeSpec) -> Frame:
    today = _today(inputs.now)
    live_since = rng.live_since
    upto = [day for day in inputs.sessions if live_since <= day <= today] if live_since is not None else []
    closes = bs.bot_session_closes(inputs.rows, upto)
    by_day = bs.rows_by_session(inputs.rows, upto)
    deployed = bs.deployed_returns(by_day, inputs.legs, upto)
    exposure = bs.exposure_by_session(by_day)
    indexed = index_pct(inputs.bars)
    if not rng.sessions:
        return Frame(rng, [], None, closes, deployed, exposure, indexed)

    through = [day for day in upto if day <= rng.sessions[-1]]
    breaks = bs.base_balance_breaks(inputs.rows, inputs.legs, through)
    in_range = set(rng.sessions)
    days = [day for day in bs.align(through, closes, indexed, breaks) if day.session in in_range]
    base_close = closes.get(rng.base) if rng.base is not None else None
    return Frame(rng, _trim_first_span(days), base_close, closes, deployed, exposure, indexed)


def deployed_counts(day: AlignedDay, dep: Deployed | None) -> bool:
    return not day.missing and day.bot_ret is not None and dep is not None and dep.ret is not None


def _point(
    date: date, cum: float | None, day: float | None, *, span: int = 1,
    missing: bool = False, proxy: bool = False, approx: bool = False, clipped: bool = False,
) -> dict:
    return {
        "date": date.isoformat(), "cum_pct": pct(cum), "day_pct": pct(day),
        "span": span, "missing": missing, "proxy": proxy, "approx": approx, "clipped": clipped,
    }


def _base_point(frame: Frame, *, bot: bool) -> list[dict]:
    if frame.rng.base is None:
        return []
    missing = bot and frame.base_close is None
    return [_point(frame.rng.base, None if missing else 0.0, None, missing=missing)]


def _chain(cum: float, r: float) -> float:
    return (1 + cum) * (1 + r) - 1


def _bot_points(frame: Frame) -> list[dict]:
    points = _base_point(frame, bot=True)
    cum = 0.0
    for day in frame.days:
        if day.missing:
            points.append(_point(day.session, None, None, span=day.span, missing=True))
            continue
        ret = None if day.base_break else day.bot_ret
        if ret is not None:
            cum = _chain(cum, ret)
        points.append(_point(day.session, cum, ret, span=day.span))
    return points


def _deployed_points(frame: Frame) -> list[dict]:
    points = _base_point(frame, bot=True)
    cum = 0.0
    for day in frame.days:
        if day.missing:
            points.append(_point(day.session, None, None, span=day.span, missing=True))
            continue
        dep = frame.deployed.get(day.session)
        ret = dep.ret if dep is not None and deployed_counts(day, dep) else None
        if ret is not None:
            cum = _chain(cum, ret)
        points.append(_point(
            day.session, cum, ret, span=day.span,
            approx=dep.approx if dep is not None else False,
            clipped=dep.clipped if dep is not None and ret is not None else False,
        ))
    return points


def _index_points(frame: Frame, sym: str) -> list[dict]:
    points = _base_point(frame, bot=False)
    cum = 0.0
    for session in frame.rng.sessions:
        ret, proxy = frame.pct[sym].get(session, (None, False))
        if ret is None:
            points.append(_point(session, None, None, missing=True, proxy=proxy))
            continue
        if not points:
            ret = None
        else:
            cum = _chain(cum, ret)
        points.append(_point(session, cum, ret, proxy=proxy))
    return points


def _markers(frame: Frame) -> list[dict]:
    return [{"date": day.session.isoformat(), "kind": "base_balance"} for day in frame.days if day.base_break]


def _exposure_rows(frame: Frame) -> list[dict]:
    rows = []
    for day in frame.days:
        exposure = frame.exposure.get(day.session, Exposure(None, 0, False))
        rows.append({
            "date": day.session.isoformat(), "pct": pct(exposure.pct),
            "open_n": exposure.open_n, "approx": exposure.approx,
        })
    return rows


def build_series(frame: Frame) -> tuple[list[dict], list[dict], list[dict]]:
    series = [
        {"key": key, "label": LABELS[key], "kind": "bot", "total_return": True, "points": points}
        for key, points in (
            ("bot_account", _bot_points(frame)),
            ("bot_deployed", _deployed_points(frame)),
        )
    ]
    series.extend(
        {"key": sym, "label": LABELS[sym], "kind": "index", "total_return": sym in TOTAL_RETURN,
         "points": _index_points(frame, sym)}
        for sym in BENCHMARK_SYMBOLS
    )
    return series, _markers(frame), _exposure_rows(frame)
