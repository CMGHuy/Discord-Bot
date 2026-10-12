"""Portfolio survival state behind `!portfolio` and GET /api/v1/risk.

Open heat against its cap, sector heat, the drawdown throttle, the kill
switch, the growth path and correlated clusters over the open trades. Every
sub-collector degrades to a safe default on its own.

Moved unchanged out of `swingbot.commands.growth` by v153 (task P), so the
admin process reads it without importing a Discord command module.
"""
from swingbot import config
from swingbot.core.edge.growth import growth_path
from swingbot.core.planning import account as account_module
from swingbot.core.tracking.performance import TradeLog


def collect_portfolio_state() -> dict:
    """Assemble the !portfolio survival-dashboard state from the E7/E8/E45/
    E47/E9 accessors over the open-trade list. Mirrors _collect_stats's
    soft-import style: every sub-collector try/excepted to a safe default
    so a missing/broken piece never kills the whole command."""
    from swingbot.core.edge import correlation, heat, throttle
    from swingbot.core.marketdata.data import get_daily_data
    from swingbot.core.marketdata import universe

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

    sectors: dict = {}
    try:
        sectors = universe.sector_map(getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist")
    except Exception:
        sectors = {}

    try:
        state["sector_heat"] = heat.sector_heat(open_trades, balance, sectors)
    except Exception:
        state["sector_heat"] = {}

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

    try:
        clusters: list = []
        tickers = sorted({t.get("ticker") for t in open_trades if t.get("ticker")})
        dfs: dict = {}
        for ticker in tickers:
            try:
                dfs[ticker] = get_daily_data(ticker)
            except Exception:
                continue
        seen: set = set()
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
        state["clusters"] = clusters
    except Exception:
        state["clusters"] = []

    return state
