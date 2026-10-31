"""Portfolio survival state behind `!portfolio` and GET /api/v1/risk.

Open heat against its cap, sector heat, the drawdown throttle, the kill
switch, the growth path and correlated clusters over the open trades. Every
sub-collector exposes its own availability without blanking independent values.

Moved unchanged out of `swingbot.commands.growth` by v153 (task P), so the
admin process reads it without importing a Discord command module.
"""
import logging
import math
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.edge.growth import growth_path
from swingbot.core.planning import account as account_module
from swingbot.core.tracking.performance import TradeLog

log = logging.getLogger(__name__)


def _load_sector_map() -> dict:
    """Read the scan universe sector map, preserving observable failures."""
    from swingbot.core.marketdata import universe

    name = getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist"
    try:
        result = universe.sector_map(name)
        if not isinstance(result, dict):
            raise ValueError("invalid sector map")
        return result
    except Exception as exc:
        swallowed(log, "ops.portfolio_state.sector_map", exc,
                  "sector map for SCAN_UNIVERSE=%r unavailable: %s", name, exc,
                  exc_info=True)
        raise


def _unmapped_count(open_trades: list, sectors: dict) -> int:
    """v194 B6: open positions `heat.sector_heat` leaves out for want of a
    sector. The same test it applies (`sectors.get(ticker)` falsy), so the
    count and the heat never disagree about which positions were skipped."""
    return sum(1 for trade in open_trades if not sectors.get(trade.get("ticker")))


def _cluster_groups(open_trades: list, balance, sectors: dict, dfs: dict) -> list:
    from swingbot.core.edge import correlation

    clusters = []
    seen = set()
    tickers = sorted({t.get("ticker") for t in open_trades if t.get("ticker")})
    for ticker in tickers:
        result = correlation.cluster_exposure(
            open_trades, ticker, dfs, balance, sectors=sectors)
        cluster = result.get("cluster") or []
        if not cluster:
            continue
        group = frozenset({ticker}) | frozenset(cluster)
        if len(group) < 2 or group in seen:
            continue
        seen.add(group)
        clusters.append(sorted(group))
    return clusters


def _availability(state: str, checked_at: str, reason=None) -> dict:
    return {"state": state, "checked_at": checked_at, "reason": reason}


def _observed(read, checked_at: str, reason: str) -> tuple:
    try:
        return read(), _availability("ok", checked_at)
    except Exception as exc:
        if reason == "sector_heat_unavailable":
            swallowed(log, "ops.portfolio_state.sector_heat", exc, level=logging.WARNING)
        else:
            swallowed(log, "ops.portfolio_state.observe", exc, level=logging.WARNING)
        return None, _availability("unavailable", checked_at, reason)


def _dependent(read, checked_at: str, reason: str, dependencies: list) -> tuple:
    failed = next((s for s in dependencies if s["state"] == "unavailable"), None)
    if failed is not None:
        return None, _availability("unavailable", checked_at, failed["reason"])
    return _observed(read, checked_at, reason)


def _balance(cfg: dict) -> float:
    value = float(cfg.get("balance", cfg.get("base_balance", 0)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid balance")
    return value


def _valid_trade(row) -> bool:
    return isinstance(row, dict) and isinstance(row.get("ticker"), str) and bool(row["ticker"].strip())


def _trades() -> list:
    rows = TradeLog().get_trades(status="open", limit=None)
    if not isinstance(rows, list) or any(not _valid_trade(t) for t in rows):
        raise ValueError("invalid open-trade response")
    return rows


def _finite_heat(read):
    value = float(read())
    if not math.isfinite(value):
        raise ValueError("nonfinite heat")
    return value


def _sector_values(trades: list, balance: float, sectors: dict) -> dict:
    from swingbot.core.edge import heat
    result = heat.sector_heat(trades, balance, sectors)
    if any(not math.isfinite(float(value)) for value in result.values()):
        raise ValueError("nonfinite sector heat")
    return result


def _sector_state(trades, balance, sectors, checked_at, dependencies) -> tuple:
    values, status = _dependent(
        lambda: _sector_values(trades, balance, sectors),
        checked_at, "sector_heat_unavailable", dependencies)
    if status["state"] == "ok" and _unmapped_count(trades, sectors):
        status = _availability("partial", checked_at, "sector_mapping_incomplete")
    return values, status


def _daily_frames(trades: list) -> tuple[dict, int]:
    from swingbot.core.marketdata.data import get_daily_data
    tickers = sorted({t.get("ticker") for t in trades if t.get("ticker")})
    frames = {}
    for ticker in tickers:
        try:
            frame = get_daily_data(ticker)
            if frame is not None and not frame.empty:
                frames[ticker] = frame
        except Exception as exc:
            swallowed(log, "ops.portfolio_state.cluster_bars", exc, level=logging.DEBUG)
    return frames, len(tickers) - len(frames)


def _clusters_state(trades, balance, sectors, checked_at, dependencies) -> tuple:
    failed = next((s for s in dependencies if s["state"] == "unavailable"), None)
    if failed is not None:
        return None, _availability("unavailable", checked_at, failed["reason"])
    if not trades:
        return [], _availability("ok", checked_at)
    collected, status = _observed(lambda: _daily_frames(trades), checked_at, "clusters_unavailable")
    if collected is None:
        return None, status
    frames, missing = collected
    if not frames:
        return None, _availability("unavailable", checked_at, "clusters_unavailable")
    groups, status = _observed(
        lambda: _cluster_groups(trades, balance, sectors, frames),
        checked_at, "clusters_unavailable")
    if status["state"] == "ok" and missing:
        status = _availability("partial", checked_at, "clusters_incomplete")
    return groups, status


def _throttle_state() -> tuple:
    from swingbot.core.edge import throttle
    points = [bal for _, bal in account_module.get_balance_history_points()]
    mult, paused = throttle.current_throttle(points, was_paused=False)
    if not math.isfinite(float(mult)) or not isinstance(paused, bool):
        raise ValueError("invalid throttle")
    return mult, paused


def _kill_state() -> dict:
    from swingbot.core.edge import throttle
    result = throttle.kill_state()
    if not isinstance(result, dict) or not isinstance(result.get("on"), bool):
        raise ValueError("invalid killswitch")
    return result


def _growth_state(cfg: dict) -> dict:
    try:
        base = cfg.get("base_balance")
        if base:
            return growth_path(account_module.get_balance_history_points(), base,
                               target_multiple=10.0)
    except Exception:
        pass
    return {}


def collect_portfolio_state() -> dict:
    from swingbot.core.edge import heat
    checked = datetime.now(timezone.utc).isoformat()
    cfg, cfg_status = _observed(account_module.load_account_config, checked, "account_unavailable")
    balance, balance_status = _dependent(
        lambda: _balance(cfg), checked, "invalid_balance", [cfg_status])
    trades, positions_status = _observed(_trades, checked, "positions_unavailable")
    dependencies = [positions_status, balance_status]
    open_heat, heat_status = _dependent(
        lambda: _finite_heat(lambda: heat.open_heat(trades, balance)),
        checked, "heat_unavailable", dependencies)
    sectors, map_status = _observed(_load_sector_map, checked, "sector_map_unavailable")
    sector_heat, sector_status = _sector_state(
        trades, balance, sectors, checked, dependencies + [map_status])
    clusters, cluster_status = _clusters_state(
        trades, balance, sectors, checked, dependencies + [map_status])
    control, throttle_status = _observed(_throttle_state, checked, "throttle_unavailable")
    mult, paused = control if control is not None else (None, None)
    kill, kill_status = _observed(_kill_state, checked, "killswitch_unavailable")
    return {
        "open_trades": trades, "balance": balance,
        "open_heat": open_heat, "heat_cap": getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0),
        "sector_heat": sector_heat,
        "unmapped_count": _unmapped_count(trades or [], sectors or {}),
        "clusters": clusters, "throttle_mult": mult, "paused": paused,
        "kill": kill if kill is not None else {"on": None, "reason": None, "at": None},
        "growth": _growth_state(cfg or {}),
        "availability": {"positions": positions_status, "heat": heat_status,
                         "sector_heat": sector_status, "clusters": cluster_status,
                         "throttle": throttle_status, "killswitch": kill_status},
    }
