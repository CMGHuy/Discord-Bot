"""GET /api/v1/risk and POST /api/v1/risk/killswitch.

Spec v14 Decision 7 asks for three things -- exposure breakdown, heat
against `PORTFOLIO_HEAT_CAP_PCT`, and the killswitch. **This endpoint ships
more than those three**, and deliberately so: today's Risk page also renders
sector heat, correlated clusters, the drawdown throttle and scan health, and
the specs are silent on all four. Silence is not a decision to drop them --
and NG18's audit classifies *routes*, so `GET /risk` -> `GET /api/v1/risk`
would look mapped while four panels quietly vanished. Everything the page
renders is therefore projected here; dropping a panel stays a decision
someone makes on purpose, in the SPA, where it is visible.

Nothing is computed. `collect_portfolio_state` is the same collector behind
the `!portfolio` Discord command and today's Risk page, and per-position
risk comes from `heat.trade_risk_pct` -- the exact function `open_heat` sums.
A second definition of either would let this endpoint and the Jinja page
disagree about how exposed the account is for the whole migration.

The collector preserves independently observed domains and their availability.
The projections keep unknown values nullable and obtain fresh control state
on every request.

`heat` also carries the open shorts' summed p99 gap risk (v183, display only).
"""
from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from flask import jsonify, request

from swingbot import config
from swingbot.core.infra.swallowed import swallowed

from . import api_v1, error
from .auth import require_auth

log = logging.getLogger(__name__)


def _position_risk(trade: dict, balance: float | None) -> float | None:
    from swingbot.core.edge.heat import trade_risk_pct
    if balance is None:
        return None
    try:
        value = float(trade_risk_pct(trade, balance))
        return round(value, 3) if math.isfinite(value) else None
    except Exception:
        return None


def _positions(open_trades: list[dict] | None, balance: float | None) -> list[dict] | None:
    if open_trades is None:
        return None
    rows = [{"trade_id": t.get("id"), "ticker": t.get("ticker"),
             "strategy": t.get("strategy"), "shares": t.get("shares"),
             "entry": t.get("entry"), "stop_loss": t.get("stop_loss"),
             "risk_pct": _position_risk(t, balance)} for t in open_trades]
    rows.sort(key=lambda row: row["risk_pct"] if row["risk_pct"] is not None else -math.inf,
              reverse=True)
    return rows


def _open_short_gap_risk(open_trades: list) -> dict:
    """v183: what the open shorts would lose on a gap the size of each ticker's
    p99 up-gap, summed -- shown beside heat, never added to it (heat stays on
    stop risk). A short without a figure is counted, never guessed at."""
    from swingbot.core.planning.gap_sizing import gap_risk_amount_for

    total, known, unknown = 0.0, 0, 0
    for t in open_trades:
        if t.get("direction") != "bearish":
            continue
        amount = (gap_risk_amount_for(t["shares"], t.get("entry"), t.get("stop_loss"), t.get("gap_sizing"))
                  if t.get("shares") else None)
        if amount is None:
            unknown += 1
        else:
            total, known = total + amount, known + 1
    return {"gap_risk_amount": round(total, 2) if known else None, "gap_risk_unknown": unknown}


def _heat_gap_block(open_trades: list[dict] | None) -> dict:
    if open_trades is None:
        return {"gap_risk_amount": None, "gap_risk_unknown": 0}
    try:
        return _open_short_gap_risk(open_trades)
    except Exception as exc:
        swallowed(log, "ops.risk.heat_gap_block", exc, level=logging.DEBUG)
        return {"gap_risk_amount": None, "gap_risk_unknown": 0}


def _sector_rows(values: dict | None) -> list[dict] | None:
    if values is None:
        return None
    return [{"sector": sector, "heat_pct": pct} for sector, pct in
            sorted(values.items(), key=lambda item: item[1] or 0.0, reverse=True)]


_DATA_SOURCE_WINDOW = 20


def _data_sources_summary(rows: list) -> dict:
    """v106: which provider is live and how often Alpaca misses. The rate is
    yfinance-fallback over everything Alpaca was asked for (hits + misses),
    daily frames and live-price answers pooled, across the last
    `_DATA_SOURCE_WINDOW` scans that logged `data_sources`;
    None when none of them asked Alpaca for anything. The formula is
    telemetry.fallback_rate, shared with each scan's provider_fallback_rate
    (v148 O4).

    `breaker_open` is this admin process's own router -- the bot's scans run
    their fetches in spawned children whose breaker never reaches here, so
    the fallback rate is the scan-side signal and the breaker the live-price
    one.
    """
    from swingbot.core.marketdata.providers import router
    from swingbot.core.scanning.telemetry import fallback_rate

    tagged = [r for r in rows if isinstance(r.get("data_sources"), dict)]
    tagged = tagged[-_DATA_SOURCE_WINDOW:]
    # Daily frames and live-price answers pooled: both are eligible
    # symbol-fetches Alpaca was asked for (clause (b) of the v106 soak).
    counts = [r["data_sources"] for r in tagged]
    counts += [r["price_sources"] for r in tagged if isinstance(r.get("price_sources"), dict)]
    rate = fallback_rate(counts)
    return {
        "enabled": bool(config.ALPACA_ENABLED),
        "feed": str(config.ALPACA_DATA_FEED_LIVE),
        "breaker_open": bool(router.stats()["breaker_open"]),
        "fallback_rate": None if rate is None else round(rate, 4),
        "scans": len(tagged),
    }


def _scan_health() -> dict:
    """Best-effort, matching how the Risk page already treats it.

    Durations ship as numbers. `helpers.scan_duration_sparkline()` returns
    rendered SVG for callers that want one; the SPA owns how a sparkline looks in
    the SPA, and a server shipping markup takes that decision away from it.
    """
    try:
        from swingbot.core.scanning.engine import recent_telemetry, scan_slowdown

        rows = recent_telemetry(50)
        durations = [r["duration_s"] for r in rows if "duration_s" in r]
        slowdown = scan_slowdown()
    except Exception:
        rows, durations, slowdown = [], [], False
    try:
        data_sources = _data_sources_summary(rows)
    except Exception:
        data_sources = None

    return {
        "durations_s": durations,
        "latest_s": durations[-1] if durations else None,
        "slowdown": bool(slowdown),
        "data_sources": data_sources,
    }


#: How long the two expensive halves of `GET /risk` are reused. Measured on
#: production (2026-10-15): `collect_portfolio_state` 4.1s and the metric /
#: correlation set 1.8s alone, but 15-52s under a scan, because the Risk page,
#: its live refreshes and other tabs asked for them concurrently on a 2-CPU
#: box. Fifteen seconds is shorter than any decision made off this page, and
#: the killswitch -- the one field that must never be stale -- is read fresh.
_RISK_TTL_S = 15.0

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}
_key_locks: dict[str, threading.Lock] = {}

_kill_observation_lock = threading.Lock()
_last_known_kill: dict = {}


def _kill_block(state: dict) -> dict:
    on = state.get("on")
    return {"on": on if isinstance(on, bool) else None,
            "reason": state.get("reason"), "at": state.get("at")}


def _kill_status(state: str, checked: str) -> dict:
    return {"state": state, "checked_at": checked,
            "reason": None if state == "ok" else "killswitch_unavailable"}


def _fresh_kill(throttle, state: dict) -> dict:
    # Retain the call signature while deliberately ignoring cached state.
    with _kill_observation_lock:
        checked = datetime.now(timezone.utc).isoformat()
        try:
            observed = _kill_block(throttle.kill_state())
            if observed["on"] is None:
                raise ValueError("invalid killswitch response")
        except Exception as exc:
            swallowed(log, "ops.risk.killswitch_unavailable", exc, level=logging.WARNING)
            block = {"on": None, "reason": None, "at": None,
                     "availability": _kill_status("unavailable", checked)}
            if _last_known_kill:
                block["last_known"] = dict(_last_known_kill)
            return block
        _last_known_kill.clear()
        _last_known_kill.update(observed, checked_at=checked)
        return {**observed, "availability": _kill_status("ok", checked)}


def _cached(key: str, compute: Callable[[], Any]) -> Any:
    """Reuse `compute()` for `_RISK_TTL_S`; concurrent callers share one run.

    Single-flight, not just a TTL: the slow case is several requests arriving
    together, and a plain TTL would let all of them miss and compute at once.
    """
    with _cache_lock:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < _RISK_TTL_S:
            return hit[1]
        value = compute()
        _cache[key] = (time.monotonic(), value)
        return value


def _invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()
    with _kill_observation_lock:
        _last_known_kill.clear()


def _metric(value: float | None, n: int) -> dict:
    return {"value": value, "n": n}


def _pnl_amounts(closed: list) -> list[float]:
    """Realised amounts of `closed`, oldest close first (no stamp sorts last),
    rows without an amount skipped -- the money walk behind
    `max_drawdown_amount`. `closed` is already in the account currency
    (`to_account_currency`), so a skipped row is either unsettled or had no
    FX rate; the caller counts the second kind."""
    ordered = sorted(closed, key=lambda trade: str(trade.get("closed_at") or "￿"))
    return [
        float(trade["realized_pnl_amount"])
        for trade in ordered
        if trade.get("realized_pnl_amount") is not None
    ]


def _max_drawdown_amount(closed: list) -> dict:
    """v194 B8: the money twin of `max_drawdown_r` -- the largest
    peak-to-trough fall of cumulative realised P&L over every closed trade,
    in the account currency, a positive magnitude. Converted read-side per
    trade at its exit date's rate (`money.to_account_currency`); a trade
    with no rate is left out and counted, never read at 1.0. Its own guard:
    a conversion failure blanks this figure, not the R metrics beside it."""
    from swingbot.core.analytics import risk_metrics as rm

    from . import money
    try:
        converted = money.to_account_currency(closed)
        amounts = _pnl_amounts(converted)
        value = rm.max_drawdown_r(amounts)   # unit-agnostic: a cumulative walk
    except Exception as exc:
        swallowed(log, "ops.risk.max_drawdown_amount", exc, level=logging.DEBUG)
        return {"value": None, "n": 0, "fx_missing_count": 0}
    return {
        "value": None if value is None else round(value, 2),
        "n": len(amounts),
        "fx_missing_count": money.missing_count(converted),
    }


def _risk_bars(symbols: list[str]) -> dict:
    """Daily bars for the risk view: the shared layer's files when on, else today's batch."""
    from swingbot.admin import freshness
    if freshness.layer_on():
        return freshness.page_daily(symbols)
    from swingbot.core.marketdata.data import get_daily_data_batch
    return get_daily_data_batch(symbols)


_DISTRIBUTION_KEYS = ("var_95", "expected_shortfall_95", "annualised_vol", "beta_spy")


def _empty_distribution() -> dict:
    return {**{key: _metric(None, 0) for key in _DISTRIBUTION_KEYS}, "as_of": None}


def _distribution_status(checked: str, reason: str | None) -> dict:
    return {"distribution_metrics": {"state": "unavailable" if reason else "ok",
                                      "checked_at": checked, "reason": reason}}


def _asset_symbols(rows: list) -> list[str]:
    return sorted({str(row["ticker"]).strip().upper() for row in rows
                   if isinstance(row, dict) and isinstance(row.get("ticker"), str) and row["ticker"].strip()})


def _asset_correlation(symbols: list[str], bars: dict) -> dict:
    from swingbot.core.analytics import risk_metrics as rm
    try:
        labels, values = rm.correlation_matrix(symbols, bars)
        return {"labels": labels, "values": values}
    except Exception as exc:
        swallowed(log, "ops.risk.asset_correlation", exc, level=logging.DEBUG)
        return {"labels": symbols, "values": []}


def _market_values(weights: dict, bars: dict, benchmark: str) -> dict:
    from swingbot.core.analytics import risk_metrics as rm
    returns = rm.portfolio_returns(weights, bars)
    benchmark_returns = rm.portfolio_returns({benchmark: 1.0}, bars)
    count = len(returns)
    volatility = rm.annualised_vol(returns)
    beta = rm.beta_vs(returns, benchmark_returns) if volatility is not None else None
    return {
        "var_95": _metric(rm.value_at_risk(returns), count),
        "expected_shortfall_95": _metric(rm.expected_shortfall(returns), count),
        "annualised_vol": _metric(volatility, count),
        "beta_spy": _metric(beta, len(returns.align(benchmark_returns, join="inner")[0])),
        "as_of": returns.index[-1].strftime("%Y-%m-%d") if count else None,
    }


def _covered_distribution(weights: dict, symbols: list, bars: dict,
                          benchmark: str, checked: str) -> tuple:
    from .risk_read_model import complete_bars
    if not complete_bars(sorted(set(symbols) | {benchmark}), bars):
        return _empty_distribution(), _distribution_status(checked, "incomplete_bars")
    try:
        values = _market_values(weights, bars, benchmark)
    except Exception as exc:
        swallowed(log, "ops.risk.distribution_values", exc, level=logging.DEBUG)
        return _empty_distribution(), _distribution_status(checked, "market_data_unavailable")
    reason = None if values["as_of"] is not None else "incomplete_bars"
    return values, _distribution_status(checked, reason)


def _distribution_metrics(open_trades: list | None, benchmark: str, checked: str) -> tuple[dict, dict, dict]:
    from .risk_read_model import signed_weights
    if open_trades is None:
        return _empty_distribution(), {"labels": [], "values": []}, _distribution_status(checked, "positions_unavailable")
    if not open_trades:
        return _empty_distribution(), {"labels": [], "values": []}, _distribution_status(checked, None)
    symbols = _asset_symbols(open_trades)
    weights, reason = signed_weights(open_trades, on=datetime.fromisoformat(checked).date())
    try:
        bars = _risk_bars(sorted(set(symbols) | {benchmark}))
    except Exception as exc:
        swallowed(log, "ops.risk.distribution_bars", exc, level=logging.DEBUG)
        return _empty_distribution(), {"labels": symbols, "values": []}, _distribution_status(checked, reason or "market_data_unavailable")
    correlation = _asset_correlation(symbols, bars)
    if reason:
        return _empty_distribution(), correlation, _distribution_status(checked, reason)
    values, availability = _covered_distribution(weights, symbols, bars, benchmark, checked)
    return values, correlation, availability


def _risk_metrics_and_correlation() -> tuple[dict, dict, dict]:
    """Independent trade metrics, signed market metrics and their availability.

    Open entry notionals are valued in account currency on one UTC date,
    signed by direction, and normalized by gross exposure before netting.
    Daily quote returns omit historical FX effects; correlation remains
    between underlying assets. These reads are cached independently of the
    collector snapshot used by the positions projection.
    """
    from swingbot.core.analytics import metrics as trade_metrics
    from swingbot.core.analytics import risk_metrics as rm
    from swingbot.core.tracking.performance import TradeLog

    try:
        open_trades = TradeLog().get_trades(status="open", limit=None)
    except Exception:
        open_trades = None

    try:
        closed = [
            t for t in TradeLog().get_trades(status=None, limit=None, ledger="main") or []
            if t.get("status") in ("win", "loss", "closed")
        ]
    except Exception:
        closed = []

    benchmark = getattr(config, "MARKET_REGIME_TICKER", "SPY") or "SPY"
    metric_keys = ("var_95", "expected_shortfall_95", "annualised_vol",
                   "beta_spy", "sharpe_r", "max_drawdown_r")

    # Trade-log-derived, with NO dependency on market/price data at all --
    # `closed` is already fetched above via its own guard, independent of
    # anything below. These must survive a market-data outage: an R-multiple
    # Sharpe/drawdown is real information the trade log already has, and
    # blanking it because a price fetch failed would discard data that was
    # never actually at risk from that failure.
    #
    # This is its OWN guard, independent of the market-data try/except below
    # -- a malformed closed-trade record (e.g. a string-typed `entry`, or a
    # non-dict/malformed leg) can raise from deep inside `r_multiple()`
    # (metrics.py), and that must degrade only these two trade-derived
    # metrics, not 500 the whole endpoint (including the killswitch block,
    # which has nothing to do with the trade log).
    try:
        r_series = trade_metrics.r_multiples(closed)
    except Exception:
        r_series = []
    sharpe_r = _metric(rm.sharpe_of(r_series), len(r_series))
    max_drawdown_r = _metric(rm.max_drawdown_r(r_series), len(r_series))
    max_drawdown_amount = _max_drawdown_amount(closed)

    null_metrics = {key: _metric(None, 0) for key in metric_keys}
    null_metrics["sharpe_r"] = sharpe_r
    null_metrics["max_drawdown_r"] = max_drawdown_r
    null_metrics["max_drawdown_amount"] = max_drawdown_amount
    null_metrics["as_of"] = None
    null_metrics["benchmark_symbol"] = benchmark

    checked = datetime.now(timezone.utc).isoformat()
    market, correlation, availability = _distribution_metrics(open_trades, benchmark, checked)
    return {**null_metrics, **market}, correlation, availability



@api_v1.route("/risk", methods=["GET"])
@require_auth
def get_risk():
    """The Risk page in one read; the shape is `Risk` in
    `frontend/src/app/api/models.ts`.

    Top-level keys: `heat`, `positions`, `sector_heat`, `unmapped_count`,
    `clusters`, `throttle`, `killswitch`, `scan_health`, `metrics`,
    `correlation`.

    `unmapped_count` (v194 B6): open positions with no sector in the scan
    universe's sector map, and therefore absent from `sector_heat`. With it,
    an empty `sector_heat` over open positions reads as "no sector data for
    N of M positions", never as "no exposure". A response field, not a
    stored record; cached with the rest of `collect_portfolio_state`
    (`_cached`, `_RISK_TTL_S`); 0 when the collector produced none.
    """
    from swingbot.core.edge.portfolio_state import collect_portfolio_state

    from swingbot.core.edge import throttle

    state = _cached("portfolio_state", collect_portfolio_state)

    balance = state.get("balance")

    open_pct = state.get("open_heat")
    cap_pct = float(state.get("heat_cap") or getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0))
    # Utilisation is NOT clamped. The Jinja page clamps only the width of the
    # bar it paints, so a bar cannot overflow its track -- the number itself
    # stays truthful, and 130% is exactly the situation the reader must see.
    utilisation = (
        round(open_pct / cap_pct * 100.0, 1)
        if open_pct is not None and cap_pct else None
    )

    metrics, correlation, metric_availability = _cached("metrics", _risk_metrics_and_correlation)
    kill = _fresh_kill(throttle, state)
    return jsonify({
        "heat": {
            "open_pct": open_pct,
            "cap_pct": cap_pct,
            "utilisation_pct": utilisation,
            **_heat_gap_block(state.get("open_trades")),
        },
        "availability": {**state.get("availability", {}), **metric_availability,
                         "killswitch": kill["availability"]},
        "positions": _positions(state.get("open_trades"), balance),
        "sector_heat": _sector_rows(state.get("sector_heat")),
        "unmapped_count": int(state.get("unmapped_count") or 0),
        "clusters": state.get("clusters"),
        "throttle": {"multiplier": state.get("throttle_mult"), "paused": state.get("paused")},
        "killswitch": kill,
        "scan_health": _scan_health(),
        "metrics": metrics,
        "correlation": correlation,
    })


@api_v1.route("/risk/killswitch", methods=["GET"])
@require_auth
def get_killswitch():
    """The killswitch alone, for the shell's banner on every page.

    The shell used to read it from `GET /risk`, which rebuilds the whole
    exposure picture (seconds of work) to answer one boolean.
    """
    from swingbot.core.edge import throttle

    return jsonify({"killswitch": _fresh_kill(throttle, {})})


@api_v1.route("/risk/killswitch", methods=["POST"])
@require_auth
def set_killswitch():
    """`{"on": bool}` -- required, and required to BE a bool.

    The Jinja form posts action=on|off, where anything that is not the
    string "on" means off. That is a safe default for a form with two
    buttons and a dangerous one for a JSON API: a client sending
    `{"on": "false"}` or misspelling the key would silently RELEASE the
    killswitch and be told it succeeded. Engaged-vs-clear decides whether
    the bot opens new positions at all, so an unclear request is refused
    rather than guessed at.

    Returns the killswitch state, not the whole risk resource: rebuilding
    that means re-clustering open positions, which fetches daily history per
    ticker -- a network round trip nobody asked for on a toggle.
    """
    from swingbot.core.edge import throttle

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("on"), bool):
        return error("invalid", "Body must contain 'on' as a boolean.", 400)
    reason = str(payload.get("reason") or "admin panel")
    try:
        throttle.set_kill(payload["on"], reason=reason)
    except Exception as exc:
        swallowed(log, "ops.risk.killswitch_write", exc, level=logging.WARNING)
        return error("unavailable", "Could not update the killswitch.", 503)
    # Clear portfolio data without discarding the last confirmed observation.
    with _cache_lock:
        _cache.clear()
    return jsonify({"killswitch": _fresh_kill(throttle, {})})
