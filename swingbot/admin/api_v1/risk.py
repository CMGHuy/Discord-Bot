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

Nothing is computed. `_collect_portfolio_state` is the same collector behind
the `!portfolio` Discord command and today's Risk page, and per-position
risk comes from `heat.trade_risk_pct` -- the exact function `open_heat` sums.
A second definition of either would let this endpoint and the Jinja page
disagree about how exposed the account is for the whole migration.

That collector try/excepts every sub-collector to a safe default, so any
value may legitimately be missing. The projections below keep that property
rather than assuming a key is present.
"""
from __future__ import annotations

from flask import jsonify, request

from swingbot import config

from . import api_v1, error
from .auth import require_auth


def _kill_block(state: dict) -> dict:
    """Normalised to exactly three keys.

    `kill_state()` reads a JSON file, so it can carry whatever an older
    build wrote. The contract tests assert an exact key set, and a stray key
    reaching the SPA is an undeclared field it can grow a dependency on.
    """
    return {
        "on": bool(state.get("on")),
        "reason": state.get("reason"),
        "at": state.get("at"),
    }


def _positions(balance: float) -> list[dict]:
    """The exposure breakdown, one row per open position.

    `trade_risk_pct` is what `open_heat` sums, so these rows always add up to
    the `heat.open_pct` figure beside them. Recomputing risk from entry and
    stop here would be a second definition, and the two would drift the
    moment either changed.
    """
    from swingbot.core.edge.heat import trade_risk_pct
    from swingbot.core.tracking.performance import TradeLog

    try:
        open_trades = TradeLog().get_trades(status="open", limit=None) or []
    except Exception:
        return []

    rows = [
        {
            "trade_id": t.get("id"),
            "ticker": t.get("ticker"),
            "strategy": t.get("strategy"),
            "shares": t.get("shares"),
            "entry": t.get("entry"),
            "stop_loss": t.get("stop_loss"),
            "risk_pct": round(trade_risk_pct(t, balance), 3),
        }
        for t in open_trades
    ]
    rows.sort(key=lambda r: r["risk_pct"], reverse=True)
    return rows


def _scan_health() -> dict:
    """Best-effort, matching how the Risk page already treats it.

    Durations ship as numbers. `helpers.scan_duration_sparkline()` returns
    rendered SVG for callers that want one; the SPA owns how a sparkline looks in
    the SPA, and a server shipping markup takes that decision away from it.
    """
    try:
        from swingbot.core.scanning.engine import recent_telemetry, scan_slowdown

        durations = [r["duration_s"] for r in recent_telemetry(50) if "duration_s" in r]
        slowdown = scan_slowdown()
    except Exception:
        durations, slowdown = [], False

    return {
        "durations_s": durations,
        "latest_s": durations[-1] if durations else None,
        "slowdown": bool(slowdown),
    }


def _metric(value: float | None, n: int) -> dict:
    return {"value": value, "n": n}


def _risk_metrics_and_correlation() -> tuple[dict, dict]:
    """The institutional metric set (v85 D37) and the correlation matrix
    (D38), both over the open book's notional weights and cached daily
    bars.

    Weight is each ticker's share of total open notional (`entry * shares`
    summed per ticker) -- the same "how big is this position" figure
    `_positions` already reports per row, just aggregated. Reads
    `TradeLog` directly rather than through `state`, matching
    `_positions`' own precedent of not going through the `!portfolio`
    collector for this.
    """
    from swingbot.core.analytics import metrics as trade_metrics
    from swingbot.core.analytics import risk_metrics as rm
    from swingbot.core.marketdata.data import get_daily_data_batch
    from swingbot.core.tracking.performance import TradeLog

    try:
        open_trades = TradeLog().get_trades(status="open", limit=None) or []
    except Exception:
        open_trades = []

    try:
        closed = [
            t for t in TradeLog().get_trades(status=None, limit=None) or []
            if t.get("status") in ("win", "loss", "closed")
        ]
    except Exception:
        closed = []

    benchmark = getattr(config, "MARKET_REGIME_TICKER", "SPY") or "SPY"
    metric_keys = ("var_95", "expected_shortfall_95", "annualised_vol",
                   "beta_spy", "sharpe_r", "max_drawdown_r")
    null_metrics = {key: _metric(None, 0) for key in metric_keys}
    null_metrics["as_of"] = None
    null_metrics["benchmark_symbol"] = benchmark
    empty_correlation = {"labels": [], "values": []}

    # Everything below reads market data: fetched bars, per-pair alignment,
    # correlations. A bad cache entry, a string-typed JSON field on a trade,
    # or a network hiccup can raise from any of `get_daily_data_batch`,
    # `portfolio_returns` (`frame["Close"]`), `.align()`/`.strftime()`, or
    # `correlation_matrix` -- and this whole tuple feeds one endpoint whose
    # killswitch must keep rendering regardless. One guard around the whole
    # section degrades to null metrics + an empty correlation matrix rather
    # than 500ing the page over a single missing bar.
    try:
        notional: dict[str, float] = {}
        for trade in open_trades:
            ticker = trade.get("ticker")
            entry = trade.get("entry")
            shares = trade.get("shares")
            if not ticker or entry is None or shares is None:
                continue
            notional[ticker] = notional.get(ticker, 0.0) + abs(entry * shares)
        total_notional = sum(notional.values())
        weights = (
            {ticker: value / total_notional for ticker, value in notional.items()}
            if total_notional else {}
        )
        symbols = sorted(weights)

        bars = get_daily_data_batch(sorted(set(symbols) | {benchmark})) if symbols else {}

        returns = rm.portfolio_returns(weights, bars)
        # The benchmark's own daily returns, gotten by asking portfolio_returns
        # for a one-symbol "portfolio" that IS the benchmark -- reuses the same
        # pct_change/notional-drop logic rather than a second copy of it.
        benchmark_returns = rm.portfolio_returns({benchmark: 1.0}, bars)

        r_series = trade_metrics.r_multiples(closed)

        n_returns = len(returns)
        metrics = {
            "var_95": _metric(rm.value_at_risk(returns), n_returns),
            "expected_shortfall_95": _metric(rm.expected_shortfall(returns), n_returns),
            "annualised_vol": _metric(rm.annualised_vol(returns), n_returns),
            "beta_spy": _metric(
                rm.beta_vs(returns, benchmark_returns),
                len(returns.align(benchmark_returns, join="inner")[0]),
            ),
            "sharpe_r": _metric(rm.sharpe_of(r_series), len(r_series)),
            "max_drawdown_r": _metric(rm.max_drawdown_r(r_series), len(r_series)),
            "as_of": (returns.index[-1].strftime("%Y-%m-%d") if not returns.empty else None),
            # v85 R8 fix (I4): the tile label must name the ACTUAL configured
            # benchmark, not a hardcoded "SPY" -- `beta_spy` keeps its key
            # (a bigger rename is a separate decision) but the symbol behind
            # it now rides along so the frontend can label it correctly.
            "benchmark_symbol": benchmark,
        }

        labels, values = rm.correlation_matrix(symbols, bars)
        correlation = {"labels": labels, "values": values}
        return metrics, correlation
    except Exception:
        return null_metrics, empty_correlation


@api_v1.route("/risk", methods=["GET"])
@require_auth
def get_risk():
    from swingbot.admin import dashboard as dash
    from swingbot.commands.growth import _collect_portfolio_state

    state = _collect_portfolio_state()

    try:
        account_cfg = dash.load_account_config()
        balance = float(account_cfg.get("balance", account_cfg.get("base_balance", 0.0)) or 0.0)
    except Exception:
        balance = 0.0

    open_pct = state.get("open_heat")
    cap_pct = float(state.get("heat_cap") or getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0))
    # Utilisation is NOT clamped. The Jinja page clamps only the width of the
    # bar it paints, so a bar cannot overflow its track -- the number itself
    # stays truthful, and 130% is exactly the situation the reader must see.
    utilisation = (
        round(open_pct / cap_pct * 100.0, 1)
        if open_pct is not None and cap_pct else None
    )

    throttle_mult = state.get("throttle_mult")
    metrics, correlation = _risk_metrics_and_correlation()
    return jsonify({
        "heat": {
            "open_pct": open_pct,
            "cap_pct": cap_pct,
            "utilisation_pct": utilisation,
        },
        "positions": _positions(balance),
        "sector_heat": [
            {"sector": sector, "heat_pct": pct}
            for sector, pct in sorted(
                (state.get("sector_heat") or {}).items(),
                key=lambda kv: kv[1] or 0.0, reverse=True,
            )
        ],
        # A list of ticker lists, as the collector produces them. The page
        # numbers them 1..n for display; that numbering is presentation.
        "clusters": state.get("clusters") or [],
        "throttle": {
            "multiplier": 1.0 if throttle_mult is None else throttle_mult,
            "paused": bool(state.get("paused")),
        },
        "killswitch": _kill_block(state.get("kill") or {}),
        "scan_health": _scan_health(),
        "metrics": metrics,
        "correlation": correlation,
    })


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

    payload = request.get_json(silent=True) or {}
    on = payload.get("on")
    if not isinstance(on, bool):
        return error("invalid", "Body must contain 'on' as a boolean.", 400)

    reason = str(payload.get("reason") or "admin panel")
    return jsonify({"killswitch": _kill_block(throttle.set_kill(on, reason=reason))})
