"""v208 benchmark chart and exposure view with no I/O or clock reads.

Inputs supply the current time. Returns stay fractional until serialization
through pct(). Provisional bars and today's partial candle stay out of the
completed chart days.
"""

from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from typing import Sequence

from swingbot.core.analytics import benchmark as bm
from swingbot.core.analytics import benchmark_series as bs
from swingbot.core.analytics.benchmark_series import AlignedDay, Deployed, Exposure
from swingbot.core.market.session import (
    US_MARKET_TZ, is_nyse_regular_session, now_et, nyse_calendar, session_close,
)
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


def _complete_session_rows(rows: list[dict], sessions: Sequence[date]) -> list[dict]:
    """A session with partially priced points cannot supply complete returns or exposure."""
    points = bs.rows_by_session(rows, sessions)
    incomplete = {day for day, group in points.items() if any(row.get('skipped_n', 0) for row in group)}
    return [row for row in rows if row['at'].astimezone(US_MARKET_TZ).date() not in incomplete]


def build_frame(inputs: BenchmarkInputs, rng: RangeSpec) -> Frame:
    today = _today(inputs.now)
    live_since = rng.live_since
    upto = [day for day in inputs.sessions if live_since <= day <= today] if live_since is not None else []
    rows = _complete_session_rows(inputs.rows, upto)
    closes = bs.bot_session_closes(rows, upto)
    by_day = bs.rows_by_session(rows, upto)
    deployed = bs.deployed_returns(by_day, inputs.legs, upto)
    exposure = bs.exposure_by_session(by_day)
    indexed = index_pct(inputs.bars)
    if not rng.sessions:
        return Frame(rng, [], None, closes, deployed, exposure, indexed)

    through = [day for day in upto if day <= rng.sessions[-1]]
    breaks = bs.base_balance_breaks(rows, inputs.legs, through)
    in_range = set(rng.sessions)
    days = [day for day in bs.align(through, closes, indexed, breaks) if day.session in in_range]
    base_close = closes.get(rng.base) if rng.base is not None else None
    return Frame(rng, _trim_first_span(days), base_close, closes, deployed, exposure, indexed)


def deployed_counts(day: AlignedDay, dep: Deployed | None) -> bool:
    return day.span == 1 and not day.missing and not day.base_break and day.bot_ret is not None and dep is not None and dep.ret is not None


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
            "open_n": None if day.missing else exposure.open_n, "approx": exposure.approx,
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


def stat(value: float | None, n: int, reason: str | None = None) -> dict:
    return {'value': value, 'n': n, 'reason': reason}


def _r4(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _account_returns(frame: Frame) -> list[tuple[AlignedDay, float]]:
    return [(day, day.bot_ret) for day in frame.days if day.bot_ret is not None and not day.base_break]


def _deployed_in_range(frame: Frame) -> list[tuple[AlignedDay, Deployed]]:
    return [(day, frame.deployed[day.session]) for day in frame.days
            if deployed_counts(day, frame.deployed.get(day.session))]


def _index_returns(frame: Frame, sym: str) -> list[float]:
    sessions = frame.rng.sessions if frame.rng.base is not None else frame.rng.sessions[1:]
    returns = [frame.pct[sym].get(session, (None, False))[0] for session in sessions]
    return [ret for ret in returns if ret is not None]


def _estimate(est: bm.Estimate) -> dict:
    return stat(_r4(est.value), est.n, est.reason)


def _line_stats(r: list[float], one: list[float]) -> dict:
    return {
        'total_pct': stat(pct(bm.total_return(r)), len(r)),
        'max_dd_pct': stat(pct(bm.max_drawdown(r)), len(r)),
        'sharpe': _estimate(bm.sharpe(one)),
    }


def _account_stats(frame: Frame) -> dict:
    counted = _account_returns(frame)
    returns = [ret for _, ret in counted]
    result = _line_stats(returns, [ret for day, ret in counted if day.one_session])
    anchor = frame.base_close
    if anchor is None:
        anchor = next((day.bot_close for day in frame.days if day.bot_close is not None), None)
    money_dd = None
    if anchor is not None:
        closes = [anchor * (1 + cumulative) for cumulative in [0.0] + bm.cumulative(returns)]
        money_dd = round(bm.money_drawdown(closes), 2)
    result.update(money_dd=stat(money_dd, len(returns)),
                  losing_streak=bm.losing_streak(returns), approx_share=None)
    return result


def _deployed_stats(frame: Frame) -> dict:
    counted = _deployed_in_range(frame)
    returns = [dep.ret for _, dep in counted]
    result = _line_stats(returns, [dep.ret for day, dep in counted if day.span == 1])
    approx_n = sum(frame.deployed[session].approx for session in frame.rng.sessions
                   if session in frame.deployed)
    share = pct(approx_n / len(frame.rng.sessions)) if frame.rng.sessions else None
    result.update(money_dd=stat(None, len(returns), 'account line only'),
                  losing_streak=bm.losing_streak(returns), approx_share=share)
    return result


def build_stats(frame: Frame) -> dict:
    result = {'bot_account': _account_stats(frame), 'bot_deployed': _deployed_stats(frame)}
    for symbol in BENCHMARK_SYMBOLS:
        returns = _index_returns(frame, symbol)
        result[symbol] = _line_stats(returns, returns)
    return result


def _pairs(frame: Frame, sym: str) -> tuple[list[float], list[float]]:
    paired = [day for day in frame.days if day.one_session and day.index_ret.get(sym) is not None]
    return [day.bot_ret for day in paired], [day.index_ret[sym] for day in paired]


def build_vs(frame: Frame) -> dict:
    returns = [ret for _, ret in _account_returns(frame)]
    bot_total = pct(bm.total_return(returns))
    result = {}
    for symbol in BENCHMARK_SYMBOLS:
        bot, index = _pairs(frame, symbol)
        beta, alpha = bm.beta(bot, index), bm.alpha(bot, index)
        idx_total = pct(bm.total_return(_index_returns(frame, symbol)))
        lead = None if bot_total is None or idx_total is None else _r4(bot_total - idx_total)
        result[symbol] = {
            'lead_pp': stat(lead, len(returns)),
            'beta': {**_estimate(beta), 'se': _r4(beta.se)},
            'alpha': {**stat(pct(alpha.value), alpha.n, alpha.reason), 't': _r4(alpha.t),
                      'headline': frame.rng.is_all and symbol == 'SPY'},
        }
    return result


def build_capture(frame: Frame, capture: str) -> dict:
    bot, index = _pairs(frame, capture)
    estimate = bm.capture(bot, index)
    return {
        'index': capture,
        'up_pct': stat(pct(estimate.up), estimate.up_n, estimate.reason),
        'down_pct': stat(pct(estimate.down), estimate.down_n, estimate.reason),
        'ratio': stat(_r4(estimate.ratio), estimate.up_n + estimate.down_n, estimate.reason),
        'up_n': estimate.up_n, 'down_n': estimate.down_n,
        'beat': asdict(bm.beat_count(bot, index)),
    }


def _daily_row(frame: Frame, day: AlignedDay, capture: str) -> dict:
    dep = frame.deployed.get(day.session)
    exposure = frame.exposure.get(day.session, Exposure(None, 0, False))
    lines = {
        'bot_account': pct(day.bot_ret) if not day.base_break else None,
        'bot_deployed': pct(dep.ret) if deployed_counts(day, dep) else None,
    }
    lines.update({sym: pct(frame.pct[sym].get(day.session, (None, False))[0] if day.missing
                           else day.index_ret.get(sym)) for sym in BENCHMARK_SYMBOLS})
    beat = None
    if day.one_session and day.index_ret.get(capture) is not None:
        beat = day.bot_ret > day.index_ret[capture]
    return {
        'date': day.session.isoformat(), 'lines': lines, 'exposure_pct': pct(exposure.pct),
        'open_n': None if day.missing else exposure.open_n, 'beat': beat, 'span': day.span, 'missing': day.missing,
    }


def build_daily(frame: Frame, capture: str) -> list[dict]:
    return [_daily_row(frame, day, capture) for day in reversed(frame.days)]


def _card_session(inputs: BenchmarkInputs, state: str, completed: list[date]) -> date | None:
    today = _today(inputs.now)
    if state != 'pre' and today in inputs.sessions:
        return today
    return completed[-1] if completed else None


def _card_account_return(frame: Frame, session: date, prior: date | None) -> float | None:
    close = frame.closes.get(session)
    prior_close = frame.closes.get(prior)
    if close is None or prior_close in (None, 0.0):
        return None
    return close / prior_close - 1


def _card_as_of(inputs: BenchmarkInputs, session: date, lines: dict, bars: dict) -> str | None:
    """Oldest timestamp among the values displayed, or unknown if any lacks one."""
    times = []
    if any(lines[key]['pct'] is not None for key in ('bot_account', 'bot_deployed')):
        points = bs.rows_by_session(inputs.rows, [session]).get(session, [])
        if not points:
            return None
        times.append(points[-1]['at'])
    for symbol in BENCHMARK_SYMBOLS:
        if lines[symbol]['pct'] is not None:
            stamp = bars[symbol].get('as_of')
            if stamp is None or stamp > inputs.now:
                return None
            times.append(stamp)
    return min(times).isoformat() if times else None


def _card_lines(inputs: BenchmarkInputs, frame: Frame, session: date, final: bool) -> tuple[dict, dict]:
    prior = max((day for day in inputs.sessions if day < session), default=None)
    breaks = bs.base_balance_breaks(inputs.rows, inputs.legs, [day for day in inputs.sessions if day <= session])
    comparable = prior in frame.closes and session not in breaks
    dep = frame.deployed.get(session)
    lines = {
        'bot_account': {'pct': pct(_card_account_return(frame, session, prior)) if comparable else None, 'final': final},
        'bot_deployed': {'pct': pct(dep.ret) if comparable and dep is not None else None, 'final': final},
    }
    bars = {bar['symbol']: bar for bar in inputs.bars if bar['session'] == session}
    for symbol in BENCHMARK_SYMBOLS:
        bar = bars.get(symbol)
        lines[symbol] = {'pct': pct(bar['day_pct']), 'final': bar['final']} if bar else {'pct': None, 'final': False}
    return lines, bars


def build_today(inputs: BenchmarkInputs, frame: Frame, state: str, completed: list[date]) -> dict:
    session = _card_session(inputs, state, completed)
    if session is None:
        return {'session': None, 'final': False, 'as_of': None, 'lines': {}}
    final = session in completed and _final_today(inputs.bars, session)
    lines, bars = _card_lines(inputs, frame, session, final)
    return {'session': session.isoformat(), 'final': final, 'as_of': _card_as_of(inputs, session, lines, bars), 'lines': lines}


def last_closed_session(sessions: Sequence[date], now: datetime) -> date | None:
    return max((day for day in sessions
                if datetime.combine(day, session_close(day), US_MARKET_TZ) <= now), default=None)


def benchmarks_status(bars: list[dict], last_closed: date | None, refresher_on: bool) -> tuple[str, date | None]:
    if not bars:
        return 'empty', None
    latest = {symbol: max((bar['session'] for bar in bars
                           if bar['symbol'] == symbol and bar['final']), default=None)
              for symbol in BENCHMARK_SYMBOLS}
    last = min(latest.values()) if all(latest.values()) else None
    behind = last is None or (last_closed is not None and last < last_closed)
    return ('stale' if not refresher_on and behind else 'ok'), last


def _range(rng: RangeSpec) -> dict:
    return {
        'from': rng.sessions[0].isoformat() if rng.sessions else None,
        'to': rng.sessions[-1].isoformat() if rng.sessions else None,
        'live_since': rng.live_since.isoformat() if rng.live_since is not None else None,
        'sessions_n': len(rng.sessions), 'clamped': rng.clamped, 'is_all': rng.is_all,
    }


def _available_inputs(inputs: BenchmarkInputs) -> BenchmarkInputs:
    """Ignore marks and account samples recorded after the request time."""
    rows = [row for row in inputs.rows if row['at'] <= inputs.now]
    bars = [bar for bar in inputs.bars
            if bar.get('as_of') is not None and bar['as_of'] <= inputs.now
            and (bar.get('updated_at') is None or bar['updated_at'] <= inputs.now)]
    return replace(inputs, rows=rows, bars=bars)


def build_benchmark(inputs: BenchmarkInputs, *, start: date | None, end: date | None, capture: str) -> dict:
    """Assemble the complete benchmark response; paging belongs to the route."""
    if capture not in BENCHMARK_SYMBOLS:
        raise ValueError(f"capture must be one of {', '.join(BENCHMARK_SYMBOLS)}")
    inputs = _available_inputs(inputs)
    state = view_session_state(inputs.now)
    completed = completed_sessions(inputs, state)
    rng = clamp_range(completed, live_since_of(inputs.rows), start, end)
    frame = build_frame(inputs, rng)
    series, markers, exposure = build_series(frame)
    status, last = benchmarks_status(
        inputs.bars, last_closed_session(inputs.sessions, inputs.now), inputs.refresher_on,
    )
    return {
        'range': _range(rng), 'as_of': inputs.now.isoformat(), 'session_state': state,
        'account_currency': inputs.account_currency, 'mixed_tickers': list(inputs.mixed_tickers),
        'benchmarks_status': status, 'benchmarks_last_session': last.isoformat() if last is not None else None,
        'today': build_today(inputs, frame, state, completed),
        'series': series, 'markers': markers, 'exposure': exposure, 'stats': build_stats(frame),
        'vs': build_vs(frame), 'capture': build_capture(frame, capture), 'daily': build_daily(frame, capture),
    }
