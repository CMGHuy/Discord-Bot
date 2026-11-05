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
from swingbot.core.analytics import risk_payload
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.shared import admin_refresh

from . import api_v1, error
from .auth import require_auth

log = logging.getLogger(__name__)


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


def _risk_bars(symbols: list[str]) -> dict:
    """Daily bars for the risk view: the shared layer's files when on, else today's batch."""
    from swingbot.admin import freshness
    from swingbot.core.marketdata.shared import admin_refresh
    if freshness.layer_on():
        return freshness.page_daily(symbols, read_only=admin_refresh.refresher_on())
    from swingbot.core.marketdata.data import get_daily_data_batch
    return get_daily_data_batch(symbols)


# v204: the risk maths lives in core (`risk_payload`); these names keep the
# route's tests and callers answering from here. `_risk_bars` is looked up
# at call time, so a patch of `risk._risk_bars` still reaches the payload.
_closed_metrics = risk_payload._closed_metrics
_closed_history = risk_payload._closed_history
_max_drawdown_amount = risk_payload._max_drawdown_amount
_pnl_amounts = risk_payload._pnl_amounts
_DISTRIBUTION_KEYS = risk_payload._DISTRIBUTION_KEYS


def _risk_metrics() -> risk_payload.RiskMetrics:
    return risk_payload.metrics_and_correlation(_risk_bars)


def _risk_metrics_and_correlation() -> tuple[dict, dict, dict]:
    result = _risk_metrics()
    return result.metrics, result.correlation, result.availability


def _distribution_metrics(open_trades: list | None, benchmark: str, checked: str) -> tuple[dict, dict, dict]:
    return risk_payload._distribution_metrics(open_trades, benchmark, checked, _risk_bars)


def _account_balance() -> float | None:
    """Today's account balance from Postgres (never the network); None when unknown."""
    try:
        from swingbot.core.planning import account
        cfg = account.load_account_config() or {}
        for key in ("balance", "base_balance"):
            value = cfg.get(key)
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and value > 0):
                return float(value)
    except Exception as exc:
        swallowed(log, "ops.risk.account_balance", exc)
    return None


def _upper_set(symbols) -> set[str]:
    return {str(s).upper() for s in (symbols or ())}


def _held_tickers(positions: list | None) -> set[str]:
    return _upper_set(p.get("ticker") for p in (positions or []) if p.get("ticker"))


def _closed_fx_missing(metrics: dict | None) -> int:
    drawdown = (metrics or {}).get("max_drawdown_amount") or {}
    return drawdown.get("fx_missing_count") or 0


def _lower_bound(doc: dict | None, missing: dict) -> list[str]:
    """The figures computed without at least one held position, in a fixed order.

    Only held tickers count: a missing benchmark or an unheld symbol never
    makes a figure a lower bound. Heat is trade-based and never one.
    """
    doc = doc or {}
    held = _held_tickers(doc.get("positions"))
    bars = held & _upper_set(missing.get("bars"))
    fx_missing = held & _upper_set(missing.get("fx"))
    out = []
    if _closed_fx_missing(doc.get("metrics")) > 0:
        out.append("metrics.closed")
    if bars or fx_missing:
        out.append("metrics.distribution")
    if bars:
        out += ["correlation", "clusters"]
    return out


def _bars_meta(inputs: dict, stale: bool) -> dict:
    block = inputs.get("bars_as_of") or {}
    missing = (inputs.get("missing") or {}).get("bars") or {}
    return {"per_symbol": dict(block.get("per_symbol") or {}),
            "oldest": block.get("oldest"), "newest": block.get("newest"),
            "stale_inputs": bool(stale),
            "missing": [{"symbol": s, "reason": missing[s]} for s in sorted(missing)]}


def _fx_meta(inputs: dict) -> dict:
    missing = (inputs.get("missing") or {}).get("fx") or ()
    return {"as_of": inputs.get("oldest_fx_as_of"), "missing": sorted(missing)}


def _meta_keys(snap: dict, *, balance: float | None, source: str = "snapshot") -> dict:
    """The six clock / completeness keys both paths of `GET /risk` add."""
    from swingbot.admin import market_values
    from swingbot.core.marketdata import fx

    inputs = snap.get("inputs") or {}
    return {
        "market_meta": {**market_values.snapshot_meta(snap), "source": source},
        "computed_at": snap["computed_at"],
        "bars_meta": _bars_meta(inputs, snap["stale_inputs"]),
        "fx_meta": _fx_meta(inputs),
        "lower_bound": _lower_bound(snap["doc"], inputs.get("missing") or {}),
        "account": {"balance": balance, "currency": fx.account_currency_code()},
    }


def _request_inputs(state: dict, result: risk_payload.RiskMetrics, body: dict) -> dict:
    """A snapshot-shaped dict from this request's own inputs; never fetches."""
    from swingbot.core.analytics import admin_snapshots

    now = datetime.now(timezone.utc)
    tickers = [t.get("ticker") for t in (state.get("open_trades") or [])]
    try:
        fx_map, missing_fx = admin_snapshots._fx_inputs(tickers, on=now.date())
    except Exception as exc:
        swallowed(log, "ops.risk.fx_inputs", exc)
        fx_map, missing_fx = {}, []
    fx_dates = [v.get("as_of") for v in fx_map.values() if v.get("as_of")]
    per_symbol = dict(result.bars_as_of)
    days = list(per_symbol.values())
    return {
        "key": "risk", "doc": body, "computed_at": now.isoformat(),
        "stale_inputs": admin_snapshots.stale_inputs_for(result.bars_as_of, now),
        "refreshing": False, "error": None,
        "inputs": {
            "oldest_quote_as_of": None, "fx": fx_map,
            "oldest_fx_as_of": min(fx_dates) if fx_dates else None,
            "bars_as_of": {"per_symbol": per_symbol, "oldest": min(days) if days else None,
                           "newest": max(days) if days else None},
            "missing": {"quotes": [], "fx": sorted(set(missing_fx)),
                        "bars": dict(result.missing_bars)},
        },
    }


def _risk_from_snapshot() -> dict:
    """Refresher on: the stored snapshot, with the kill switch and scan health live."""
    from swingbot.admin import market_values
    from swingbot.core.edge import throttle

    snap = market_values.read_snapshot(admin_refresh.SNAPSHOT_RISK)
    doc = snap["doc"] or risk_payload.empty_body()
    kill = _fresh_kill(throttle, {})
    return {
        **doc,
        "availability": {**doc["availability"], "killswitch": kill["availability"]},
        "killswitch": kill,
        "scan_health": _scan_health(),
        **_meta_keys(snap, balance=_account_balance()),
    }


def _risk_on_request() -> dict:
    """Refresher off (the kill-switch fallback): today's request-time compute."""
    from swingbot.core.edge.portfolio_state import collect_portfolio_state

    from swingbot.core.edge import throttle

    state = _cached("portfolio_state", collect_portfolio_state)
    result = _cached("metrics", _risk_metrics)
    kill = _fresh_kill(throttle, state)
    # Utilisation stays unclamped (now inside `market_body`): 130% is exactly
    # the situation the reader must see.
    body = risk_payload.market_body(state, result)
    snap = _request_inputs(state, result, body)
    return {
        **body,
        "availability": {**body["availability"], "killswitch": kill["availability"]},
        "killswitch": kill,
        "scan_health": _scan_health(),
        **_meta_keys(snap, balance=state.get("balance"), source="request"),
    }


@api_v1.route("/risk", methods=["GET"])
@require_auth
def get_risk():
    """The Risk page in one read; the shape is `Risk` in
    `frontend/src/app/api/models.ts`.

    Top-level keys: `heat`, `positions`, `sector_heat`, `unmapped_count`,
    `clusters`, `throttle`, `killswitch`, `scan_health`, `metrics`,
    `correlation`, and (v204) `market_meta`, `computed_at`, `bars_meta`,
    `fx_meta`, `lower_bound`, `account`.

    Two paths, one payload (v204). With the admin refresher on, the market
    half is the stored `risk` snapshot (`_risk_from_snapshot`): nothing is
    computed or fetched, `market_meta.source` is "snapshot" and
    `computed_at` is the snapshot's clock. With it off -- the kill-switch
    fallback -- today's request-time compute runs (`_risk_on_request`) and
    the same six keys describe the request's own inputs, `source` "request".
    The killswitch and scan health are read live on both paths.
    `lower_bound` names the figures computed without at least one held
    position; `account.balance` is null, never 0, when unknown.

    `unmapped_count` (v194 B6): open positions with no sector in the scan
    universe's sector map, and therefore absent from `sector_heat`. With it,
    an empty `sector_heat` over open positions reads as "no sector data for
    N of M positions", never as "no exposure". A response field, not a
    stored record; cached with the rest of `collect_portfolio_state`
    (`_cached`, `_RISK_TTL_S`); 0 when the collector produced none.
    """
    if admin_refresh.refresher_on():
        return jsonify(_risk_from_snapshot())
    return jsonify(_risk_on_request())


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
