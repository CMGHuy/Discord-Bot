"""Portfolio survival state behind `!portfolio` and GET /api/v1/risk.

Open heat against its cap, sector heat, the drawdown throttle, the kill
switch, the growth path and correlated clusters over the open trades. Every
sub-collector degrades to a safe default on its own.

Moved unchanged out of `swingbot.commands.growth` by v153 (task P), so the
admin process reads it without importing a Discord command module.
"""
import logging

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.edge.growth import growth_path
from swingbot.core.planning import account as account_module
from swingbot.core.tracking.performance import TradeLog

log = logging.getLogger(__name__)


def _load_sector_map() -> dict:
    """v194 B6: the scan universe's ticker -> sector map, or {} when it
    cannot be read. A failure logs at warning with the exception text; an
    empty map, raised or not, shows up as `unmapped_count`.

    Read side only: `universe.sector_map` and the files behind it also feed
    the walk-forward replay's sector cap and the weekly risk report, so they
    are not this module's to change."""
    from swingbot.core.marketdata import universe

    name = getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist"
    try:
        return universe.sector_map(name)
    except Exception as exc:
        swallowed(log, "ops.portfolio_state.sector_map", exc,
                  "sector map for SCAN_UNIVERSE=%r unavailable: %s", name, exc,
                  exc_info=True)
        return {}


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


def _cluster_state(open_trades: list, balance, sectors: dict) -> list:
    from swingbot.core.marketdata.data import get_daily_data

    try:
        tickers = sorted({t.get("ticker") for t in open_trades if t.get("ticker")})
        dfs = {}
        for ticker in tickers:
            try:
                dfs[ticker] = get_daily_data(ticker)
            except Exception:
                continue
        return _cluster_groups(open_trades, balance, sectors, dfs)
    except Exception:
        return []


def collect_portfolio_state() -> dict:
    """Assemble the !portfolio survival-dashboard state from the E7/E8/E45/
    E47/E9 accessors over the open-trade list. Mirrors _collect_stats's
    soft-import style: every sub-collector try/excepted to a safe default
    so a missing/broken piece never kills the whole command."""
    from swingbot.core.edge import heat, throttle
    state: dict = {}

    try:
        cfg = account_module.load_account_config()
        balance = cfg.get("balance", cfg.get("base_balance", 0.0))
    except Exception:
        cfg = {}
        balance = 0.0

    open_trades: list = []
    try:
        open_trades = TradeLog().get_trades(status="open", limit=None)
    except Exception:
        open_trades = []

    try:
        state["open_heat"] = heat.open_heat(open_trades, balance)
    except Exception:
        state["open_heat"] = 0.0
    state["heat_cap"] = getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)

    sectors = _load_sector_map()

    try:
        state["sector_heat"] = heat.sector_heat(open_trades, balance, sectors)
    except Exception as exc:
        swallowed(log, "ops.portfolio_state.sector_heat", exc,
                  "sector heat unavailable: %s", exc, exc_info=True)
        state["sector_heat"] = {}
    # v194 B6: with this, `sector_heat == {}` over open positions reads as
    # "no sector data", never as "no exposure".
    state["unmapped_count"] = _unmapped_count(open_trades, sectors)

    try:
        equity_points = [bal for _, bal in account_module.get_balance_history_points()]
        mult, paused = throttle.current_throttle(equity_points, was_paused=False)
        state["throttle_mult"] = mult
        state["paused"] = paused
    except Exception:
        state["throttle_mult"] = 1.0
        state["paused"] = False

    try:
        state["kill"] = throttle.kill_state()
    except Exception:
        state["kill"] = {"on": False, "reason": None}

    try:
        base = cfg.get("base_balance")
        if base:
            state["growth"] = growth_path(
                account_module.get_balance_history_points(), base, target_multiple=10.0)
        else:
            state["growth"] = {}
    except Exception:
        state["growth"] = {}

    state["clusters"] = _cluster_state(open_trades, balance, sectors)

    return state
