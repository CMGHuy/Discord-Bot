"""The Risk page's market payload: exposure, distribution metrics, correlation.

v204 moved this chain out of `swingbot/admin/api_v1/risk.py` unchanged, so
`GET /risk` and the refresher's snapshot both call `metrics_and_correlation`
and `market_body` -- one definition, never a forked copy of the risk maths.
The live controls (`killswitch`, `scan_health`) stay in the route.

Nothing is computed. `collect_portfolio_state` is the same collector behind
the `!portfolio` Discord command and today's Risk page, and per-position
risk comes from `heat.trade_risk_pct` -- the exact function `open_heat` sums.
A second definition of either would let this endpoint and the Jinja page
disagree about how exposed the account is for the whole migration.

`metrics_and_correlation(bars_reader, strict=...)` takes its daily bars from
the caller: the route passes its own reader, the snapshot a read-only one.
`strict=True` lets a bar-read or correlation failure raise instead of
degrading, so a snapshot is never written from a silently partial read.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import fx_convert
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable
from swingbot.core.marketdata.shared import admin_refresh

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskMetrics:
    metrics: dict
    correlation: dict
    availability: dict
    bars_as_of: dict[str, str]
    missing_bars: dict[str, str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _open_trades() -> list | None:
    from swingbot.core.tracking.performance import TradeLog
    try:
        return TradeLog().get_trades(status="open", limit=None)
    except Exception as exc:  # noqa: BLE001 - no open book reads as unavailable
        swallowed(log, "ops.risk_payload.open_trades", exc, level=logging.DEBUG)
        return None


def _position_risk(trade: dict, balance: float | None) -> float | None:
    from swingbot.core.edge.heat import trade_risk_pct
    if balance is None:
        return None
    try:
        value = float(trade_risk_pct(trade, balance))
        return round(value, 3) if math.isfinite(value) else None
    except Exception as exc:  # noqa: BLE001 - one unpriceable position reads as None
        swallowed(log, "ops.risk_payload.position_risk", exc, level=logging.DEBUG)
        return None


def _plans_or_none() -> dict | None:
    """Every stored plan by id, or None when the store cannot be read -- a
    row then shows no risk of loss rather than pricing a PENDING placeholder
    as held."""
    from swingbot.core.tracking.equity import load_plans_by_id

    try:
        return load_plans_by_id()
    except Exception as exc:
        swallowed(log, "ops.risk.plans_by_id", exc, level=logging.DEBUG)
        return None


def _risk_of_loss_fields(trade: dict, plans: dict | None, balance: float | None) -> dict:
    """v189 B4: the row's risk of loss beside its enforced `risk_pct`. Never
    summed into `risk_pct`: those rows still add up to `heat.open_pct`, and
    the utilisation gauge stays on enforced heat."""
    from swingbot.core.tracking.equity import position_risk_of_loss

    if plans is None:
        return {"risk_of_loss_amount": None, "risk_of_loss_pct": None}
    amount = position_risk_of_loss(trade, plans.get(trade.get("plan_id")))
    pct = (round(amount / balance * 100.0, 3)
           if amount is not None and balance is not None and balance > 0 else None)
    return {"risk_of_loss_amount": amount, "risk_of_loss_pct": pct}


def _positions(open_trades: list[dict] | None, balance: float | None) -> list[dict] | None:
    """One row per open trade, its enforced `risk_pct` from `trade_risk_pct`.
    Each row also carries its risk of loss to the working stop (v189 B4),
    shown beside risk_pct and never added to it."""
    if open_trades is None:
        return None
    plans = _plans_or_none()
    rows = [{"trade_id": t.get("id"), "ticker": t.get("ticker"),
             "strategy": t.get("strategy"), "shares": t.get("shares"),
             "entry": t.get("entry"), "stop_loss": t.get("stop_loss"),
             "risk_pct": _position_risk(t, balance),
             **_risk_of_loss_fields(t, plans, balance)} for t in open_trades]
    rows.sort(key=lambda row: row["risk_pct"] if row["risk_pct"] is not None else -math.inf,
              reverse=True)
    return rows


def _open_short_gap_risk(open_trades: list) -> dict:
    """v183: what the open shorts would lose on a gap the size of each ticker's
    p99 up-gap, summed -- shown beside heat, never added to it (heat stays on
    stop risk). A short without a figure is counted, never guessed at.
    Shorts only, as the risk page labels it; a stamped long's gap figure
    is on its order block (v191)."""
    from swingbot.core.planning.gap_sizing import gap_risk_amount_for

    total, known, unknown = 0.0, 0, 0
    for t in open_trades:
        if t.get("direction") != "bearish":
            continue
        amount = (gap_risk_amount_for(t["shares"], t.get("entry"), t.get("stop_loss"), t.get("gap_sizing"),
                                     direction="bearish")
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


def _metric(value: float | None, n: int) -> dict:
    return {"value": value, "n": n}


def _pnl_amounts(closed: list) -> list[float]:
    """Finite account-currency amounts in valid close order."""
    from swingbot.core.analytics.risk_read_model import chronological_records
    ordered, _ = chronological_records(closed)
    amounts = []
    for row in ordered:
        raw = row.get("realized_pnl_amount")
        if raw is None:
            continue
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("nonfinite realized amount")
        amounts.append(value)
    return amounts


def _money_metric(closed: list) -> tuple[dict, str | None]:
    """Money drawdown and coverage, converting only date-valid records."""
    from swingbot.core.analytics import risk_metrics as rm
    from swingbot.core.analytics.risk_read_model import chronological_records
    ordered, counts = chronological_records(closed)
    metric = {"value": None, "n": 0, "fx_missing_count": 0,
              "invalid_date_count": counts["invalid_date_count"]}
    try:
        converted = fx_convert.to_account_currency(ordered, fetch=not admin_refresh.refresher_on())
        metric["fx_missing_count"] = fx_convert.missing_count(converted)
        amounts = _pnl_amounts(converted)
        value = rm.max_drawdown_r(amounts)
        if amounts and value is None:
            raise ValueError("nonfinite cumulative amount")
        metric.update(value=None if value is None else round(value, 2), n=len(amounts))
    except Exception as exc:
        swallowed(log, "ops.risk.max_drawdown_amount", exc, level=logging.DEBUG)
        return metric, "money_conversion_unavailable"
    return metric, None


def _max_drawdown_amount(closed: list) -> dict:
    return _money_metric(closed)[0]


def _closed_history() -> list | None:
    from swingbot.core.tracking.performance import TradeLog
    try:
        rows = TradeLog().get_trades(status=None, limit=None, ledger="main")
        if not isinstance(rows, list):
            raise ValueError("invalid closed-history response")
        return [row for row in rows if not isinstance(row, dict)
                or row.get("status") in ("win", "loss", "closed")]
    except Exception as exc:
        swallowed(log, "ops.risk.closed_trades_unavailable", exc, level=logging.WARNING)
        return None


def _population_status(checked: str, count: int, total: int, excluded: int, reason: str) -> dict:
    state = "ok"
    if total and count == 0:
        state = "unavailable"
    elif excluded:
        state = "partial"
    return {"state": state, "checked_at": checked, "reason": None if state == "ok" else reason}


def _finite_metric(value) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def _r_metrics(closed: list, checked: str) -> tuple[dict, dict]:
    from swingbot.core.analytics import metrics as trade_metrics
    from swingbot.core.analytics import risk_metrics as rm
    from swingbot.core.analytics.risk_read_model import chronological_records
    ordered, counts = chronological_records(closed, outcome=trade_metrics.r_multiple)
    values = [float(trade_metrics.r_multiple(row)) for row in ordered]
    drawdown = rm.max_drawdown_r(values)
    status = _population_status(checked, len(values), len(closed), counts["excluded_count"],
                                "invalid_closed_records")
    if values and drawdown is None:
        status = {"state": "unavailable", "checked_at": checked, "reason": "invalid_closed_records"}
    return {
        "sharpe_r": {**_metric(_finite_metric(rm.sharpe_of(values)), len(values)), **counts},
        "max_drawdown_r": {**_metric(drawdown, len(values)), **counts},
    }, {"drawdown_r": status}


def _closed_metrics(closed: list | None, checked: str) -> tuple[dict, dict]:
    if closed is None:
        counts = {"excluded_count": 0, "invalid_date_count": 0, "invalid_outcome_count": 0}
        unavailable = {"state": "unavailable", "checked_at": checked, "reason": "closed_trades_unavailable"}
        return {
            "sharpe_r": {**_metric(None, 0), **counts},
            "max_drawdown_r": {**_metric(None, 0), **counts},
            "max_drawdown_amount": {"value": None, "n": 0, "fx_missing_count": 0, "invalid_date_count": 0},
        }, {"drawdown_r": dict(unavailable), "drawdown_amount": dict(unavailable)}
    metrics, availability = _r_metrics(closed, checked)
    money, failure = _money_metric(closed)
    reason = "missing_fx" if money["fx_missing_count"] else "incomplete_money_outcomes"
    if money["invalid_date_count"]:
        reason = "invalid_closed_records"
    money_status = _population_status(checked, money["n"], len(closed), len(closed) - money["n"], reason)
    if failure:
        money_status = {"state": "unavailable", "checked_at": checked, "reason": failure}
    return {**metrics, "max_drawdown_amount": money}, {**availability, "drawdown_amount": money_status}


_DISTRIBUTION_KEYS = ("var_95", "expected_shortfall_95", "annualised_vol", "beta_spy")


def _empty_distribution() -> dict:
    return {**{key: _metric(None, 0) for key in _DISTRIBUTION_KEYS}, "as_of": None}


def _distribution_status(checked: str, reason: str | None) -> dict:
    return {"distribution_metrics": {"state": "unavailable" if reason else "ok",
                                      "checked_at": checked, "reason": reason}}


def _asset_symbols(rows: list) -> list[str]:
    return sorted({str(row["ticker"]).strip().upper() for row in rows
                   if isinstance(row, dict) and isinstance(row.get("ticker"), str) and row["ticker"].strip()})


def _asset_correlation(symbols: list[str], bars: dict, *, strict: bool = False) -> dict:
    from swingbot.core.analytics import risk_metrics as rm
    try:
        labels, values = rm.correlation_matrix(symbols, bars)
        return {"labels": labels, "values": values}
    except Exception as exc:
        if strict:
            raise
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
    from swingbot.core.analytics.risk_read_model import complete_bars
    if not complete_bars(sorted(set(symbols) | {benchmark}), bars):
        return _empty_distribution(), _distribution_status(checked, "incomplete_bars")
    try:
        values = _market_values(weights, bars, benchmark)
    except Exception as exc:
        swallowed(log, "ops.risk.distribution_values", exc, level=logging.DEBUG)
        return _empty_distribution(), _distribution_status(checked, "market_data_unavailable")
    if any(values[key]["value"] is not None and not math.isfinite(values[key]["value"])
           for key in _DISTRIBUTION_KEYS):
        return _empty_distribution(), _distribution_status(checked, "market_data_unavailable")
    reason = None if values["as_of"] is not None else "incomplete_bars"
    return values, _distribution_status(checked, reason)


def _distribution_metrics(open_trades: list | None, benchmark: str, checked: str,
                          bars_reader: Callable[[list[str]], dict], *,
                          strict: bool = False) -> tuple[dict, dict, dict]:
    from swingbot.core.analytics.risk_read_model import signed_weights
    if open_trades is None:
        return _empty_distribution(), {"labels": [], "values": []}, _distribution_status(checked, "positions_unavailable")
    if not open_trades:
        return _empty_distribution(), {"labels": [], "values": []}, _distribution_status(checked, None)
    symbols = _asset_symbols(open_trades)
    weights, reason = signed_weights(open_trades, on=fx_convert.fx_day(checked))
    try:
        bars = bars_reader(sorted(set(symbols) | {benchmark}))
    except DailyCacheUnavailable:
        raise
    except Exception as exc:
        if strict:
            raise
        swallowed(log, "ops.risk.distribution_bars", exc, level=logging.DEBUG)
        return _empty_distribution(), {"labels": symbols, "values": []}, _distribution_status(checked, reason or "market_data_unavailable")
    correlation = _asset_correlation(symbols, bars, strict=strict)
    if reason:
        return _empty_distribution(), correlation, _distribution_status(checked, reason)
    values, availability = _covered_distribution(weights, symbols, bars, benchmark, checked)
    return values, correlation, availability


class _Recorder:
    """Wraps a bars reader; remembers the symbols asked for and the frames returned."""

    def __init__(self, bars_reader: Callable[[list[str]], dict]):
        self._reader = bars_reader
        self.asked: list[str] = []
        self.frames: dict = {}

    def __call__(self, symbols: list[str]) -> dict:
        self.asked.extend(symbols)
        bars = self._reader(symbols)
        if isinstance(bars, dict):
            self.frames.update(bars)
        return bars


def _last_bar_day(frame) -> str | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    last = frame.index[-1]
    return last.strftime("%Y-%m-%d") if hasattr(last, "strftime") else None


def _bar_coverage(recorder: _Recorder, bars_reader) -> tuple[dict, dict]:
    bars_as_of = {sym: day for sym, frame in recorder.frames.items()
                  if (day := _last_bar_day(frame)) is not None}
    seen = getattr(bars_reader, "seen", None)
    reasons = getattr(seen, "missing", None) or {}
    missing = {sym: reasons.get(sym, "no_bars") for sym in recorder.asked if sym not in bars_as_of}
    return bars_as_of, missing


def _overlap_checked(correlation: dict) -> dict:
    """A matrix where no pair reached `risk_metrics._MIN_BARS` says nothing:
    null values with a reason, not a grid of empty cells."""
    labels, values = correlation.get("labels") or [], correlation.get("values")
    if len(labels) < 2 or not isinstance(values, list) or len(values) != len(labels):
        return correlation
    off_diagonal = [cell for i, row in enumerate(values) for j, cell in enumerate(row) if i != j]
    if all(cell is None for cell in off_diagonal):
        return {"labels": labels, "values": None, "reason": "insufficient_overlap"}
    return correlation


def _zero_variance(frame) -> bool:
    if frame is None or "Close" not in getattr(frame, "columns", ()):
        return False
    returns = frame["Close"].pct_change().dropna()
    return len(returns) >= 2 and math.isclose(float(returns.var(ddof=1)), 0.0, abs_tol=1e-18)


def metrics_and_correlation(bars_reader: Callable[[list[str]], dict], *,
                            strict: bool = False) -> RiskMetrics:
    """Independently project closed-trade and signed market observations."""
    open_trades = _open_trades()
    checked = _now().isoformat()
    benchmark = getattr(config, "MARKET_REGIME_TICKER", "SPY") or "SPY"
    recorder = _Recorder(bars_reader)
    closed_metrics, closed_availability = _closed_metrics(_closed_history(), checked)
    market_metrics, correlation, market_availability = _distribution_metrics(
        open_trades, benchmark, checked, recorder, strict=strict)
    metrics = {**market_metrics, **closed_metrics, "benchmark_symbol": benchmark}
    availability = {**market_availability, **closed_availability}
    if metrics["beta_spy"]["value"] is None and _zero_variance(recorder.frames.get(benchmark)):
        availability["beta_spy"] = "zero_variance"
    bars_as_of, missing = _bar_coverage(recorder, bars_reader)
    return RiskMetrics(metrics, _overlap_checked(correlation), availability, bars_as_of, missing)


def market_body(state: dict, result: RiskMetrics) -> dict:
    """The market half of `GET /risk`; the route adds the live controls."""
    open_pct = state.get("open_heat")
    cap_pct = float(state.get("heat_cap") or getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0))
    # Utilisation is NOT clamped. The Jinja page clamps only the width of the
    # bar it paints, so a bar cannot overflow its track -- the number itself
    # stays truthful, and 130% is exactly the situation the reader must see.
    utilisation = (
        round(open_pct / cap_pct * 100.0, 1)
        if open_pct is not None and cap_pct else None
    )
    return {
        "heat": {
            "open_pct": open_pct,
            "cap_pct": cap_pct,
            "utilisation_pct": utilisation,
            **_heat_gap_block(state.get("open_trades")),
        },
        "availability": {**state.get("availability", {}), **result.availability},
        "positions": _positions(state.get("open_trades"), state.get("balance")),
        "sector_heat": _sector_rows(state.get("sector_heat")),
        "unmapped_count": int(state.get("unmapped_count") or 0),
        "clusters": state.get("clusters"),
        "throttle": {"multiplier": state.get("throttle_mult"), "paused": state.get("paused")},
        "metrics": result.metrics,
        "correlation": result.correlation,
    }


def empty_body() -> dict:
    """Every `market_body` key with no figures, for a page with nothing to show yet."""
    benchmark = getattr(config, "MARKET_REGIME_TICKER", "SPY") or "SPY"
    return {
        "heat": {"open_pct": None, "cap_pct": None, "utilisation_pct": None, **_heat_gap_block(None)},
        "availability": {},
        "positions": None,
        "sector_heat": None,
        "unmapped_count": 0,
        "clusters": None,
        "throttle": {"multiplier": None, "paused": None},
        "metrics": {**_empty_distribution(), **_closed_metrics(None, "")[0], "benchmark_symbol": benchmark},
        "correlation": {"labels": [], "values": []},
    }
