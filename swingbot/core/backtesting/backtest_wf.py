"""Anchored walk-forward harness -- the gatekeeper for every Edge component.

Folds are FROZEN (pre-registered before any data contact, per the plan's
Global Constraints). Train windows exist for parameter *fitting* inside
components that need it; the judgment numbers come only from the test
years. The 2024-2025 window does not appear here at all -- it is spent
exactly once, at the end of the plan.
"""
from __future__ import annotations

import logging

from swingbot import config

log = logging.getLogger("swing-bot.backtest_wf")

ANCHORED_FOLDS = (
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
)

# Pre-registered gate constants -- do not touch without a new pre-registration.
GATE_MIN_IMPROVING_FOLDS = 2
GATE_MAX_DEGRADATION_R = 0.05
GATE_MIN_N_PER_FOLD = 30

PLATEAU_TOLERANCE_R = 0.03


def plateau_report(param_name: str, grid: list, expectancies: list,
                   adopted_value) -> dict:
    """Adopted values must sit on plateaus, never spikes: if moving one
    grid step changes expectancy by more than PLATEAU_TOLERANCE_R, the
    'optimum' is noise you happened to sample."""
    i = grid.index(adopted_value)
    neighbors = [j for j in (i - 1, i + 1) if 0 <= j < len(grid)]
    is_plateau = all(abs(expectancies[j] - expectancies[i]) <= PLATEAU_TOLERANCE_R
                     for j in neighbors)
    return {"param": param_name, "grid": grid, "expectancies": expectancies,
            "adopted": adopted_value,
            "neighbors": {grid[j]: expectancies[j] for j in neighbors},
            "is_plateau": is_plateau}


def _apply_overrides(overrides: dict) -> dict:
    old = {}
    for key, value in overrides.items():
        old[key] = getattr(config, key, None)
        setattr(config, key, value)
    return old


def _guarded(run_fn):
    """Wrap a run function so config overrides are applied and restored
    around it, whatever happens inside. Split out of `_default_run` so an
    injected `run_fn` gets the same protection: a component run that
    raises must never leave config mutated, or the next component's folds
    silently inherit it."""
    def wrapped(start: str, end: str, overrides: dict) -> dict:
        old = _apply_overrides(overrides or {})
        try:
            return run_fn(start, end, overrides)
        finally:
            _apply_overrides(old)
    return wrapped


def _symbols_for_folds() -> list:
    """The symbol set folds run over. Separate seam so tests never touch
    the universe files or the OHLCV cache."""
    from swingbot.core.marketdata.universe import universe_symbols
    from swingbot.core.marketdata.watchlist import load_watchlist

    symbols = universe_symbols(getattr(config, "SCAN_UNIVERSE", "watchlist")) or []
    return symbols or load_watchlist()


def _frame_for(symbol: str):
    """Daily bars for one symbol, or None.

    Reads `data/backtest_cache/` -- NOT `market_data/`. This repo has two
    parallel OHLCV caches and they are not interchangeable. The choice
    matters twice over here:

      * COMPARABILITY. Every number these folds are judged against (the
        E22 friction-adjusted baseline) came from scripts/run_backtest_
        range.py, which reads this cache. Folds measured on the other one
        would be comparing against a different dataset.
      * WARM-UP DEPTH. market_data/ starts 2018-06 (measured), i.e. right
        at the folds' own anchor, leaving indicators no warm-up before
        the first train window. backtest_cache goes back to 2000. On AAPL
        the same strategies produce 13 trades from backtest_cache vs 1
        from market_data over identical windows -- the fold N would have
        been starved by the data source alone.
    """
    from swingbot.core.marketdata.backtest_cache import CACHE_DIR
    import pandas as pd

    path = CACHE_DIR / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception as exc:
        log.warning("fold frame unreadable for %s: %s", symbol, exc)
        return None


def _default_run(start: str, end: str, overrides: dict,
                 strategies=None, horizons=None, tickers=None) -> dict:
    """Pooled expectancy over the cached universe for one window.

    Overrides are NOT applied here -- `run_folds` wraps every run function
    in `_guarded`, so applying them twice would double-restore.

    `tickers`, when given, replaces `_symbols_for_folds()`'s SCAN_UNIVERSE
    lookup entirely -- an explicit scope for one-off runs (e.g. an ETF-only
    fold sweep) that doesn't require flipping the account's live SCAN_UNIVERSE
    setting just to run a backtest.
    """
    import numpy as np
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest_daterange
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.marketdata.universe import liquidity_ok

    strategies = ALL_STRATEGIES if strategies is None else strategies
    horizons = list(HORIZONS) if horizons is None else horizons

    rs = []
    for sym in (tickers if tickers is not None else _symbols_for_folds()):
        df = _frame_for(sym)
        if df is None or not liquidity_ok(df):
            continue
        for strat in strategies:
            for hk in horizons:
                # The plan's own snippet omitted horizon_key entirely and
                # was never callable: run_backtest_daterange is
                # (ticker, df, strategy, horizon_key, date_from, date_to).
                # exit_model/scale_out/tp2_mode match what the E22
                # friction-adjusted baseline was measured with
                # (run_backtest_range.py defaults --tp2 levels), or fold
                # deltas would be comparing against a different exit model.
                #
                # tp2_mode="levels" is also what makes level-sourced
                # components VISIBLE here at all: with "none" the backtest
                # never calls build_level_map, so AVWAP and HVN/LVN change
                # nothing and their folds would score a meaningless 0.0000.
                s = run_backtest_daterange(sym, df, strat, hk, start, end,
                                           frictions=True, exit_model="v2",
                                           scale_out=True, tp2_mode="levels")
                rs.extend(t.r_multiple for t in (s.trades or [])
                          if t.r_multiple is not None)
    return {"expectancy_r": float(np.mean(rs)) if rs else None, "n": len(rs)}


def run_folds(overrides: dict, folds=ANCHORED_FOLDS, tickers=None,
              run_fn=None) -> dict:
    if run_fn is None:
        def _scoped_default_run(start, end, ov):
            return _default_run(start, end, ov, tickers=tickers)
        run = _guarded(_scoped_default_run)
    else:
        run = run_fn
    fold_rows = []
    for train_start, train_end, test_start, test_end in folds:
        base = run(test_start, test_end, {})
        comp = run(test_start, test_end, dict(overrides))
        delta = None
        if base["expectancy_r"] is not None and comp["expectancy_r"] is not None:
            delta = comp["expectancy_r"] - base["expectancy_r"]
        fold_rows.append({"test_years": test_start[:4],
                          "baseline": base, "component": comp,
                          "delta_expectancy_r": delta,
                          "n": min(base["n"], comp["n"])})
    deltas = [f["delta_expectancy_r"] for f in fold_rows if f["delta_expectancy_r"] is not None]
    pooled = sum(deltas) / len(deltas) if deltas else None
    return {"folds": fold_rows, "pooled_delta_expectancy_r": pooled}


def gate(result: dict) -> str:
    """The PRE-REGISTERED pass rule. A component that fails is dropped and
    documented -- no second grid on the same hypothesis."""
    folds = result["folds"]
    deltas = [f["delta_expectancy_r"] for f in folds]
    if any(d is None for d in deltas):
        return "FAIL"
    if any(f["n"] < GATE_MIN_N_PER_FOLD for f in folds):
        return "FAIL"
    if sum(d > 0 for d in deltas) < GATE_MIN_IMPROVING_FOLDS:
        return "FAIL"
    if any(d < -GATE_MAX_DEGRADATION_R for d in deltas):
        return "FAIL"
    return "PASS"


def _early_exit_r(pos: dict, exit_price: float) -> float:
    """R of a position cut short at `exit_price` instead of run to its stop or
    target. Same direction-adjusted formula get_stats/_closed_r use live."""
    risk = abs(pos["entry"] - pos["stop_loss"])
    if not risk:
        return 0.0
    realized = ((exit_price - pos["entry"]) if pos["direction"] == "bullish"
                else (pos["entry"] - exit_price))
    return realized / risk


def _days_between(a: str, b: str) -> float:
    """Whole days between two ISO date strings, b - a. Signals carry dates
    (not timestamps), so reversal guards are expressed in days here where the
    live ones are in hours."""
    from datetime import date
    try:
        da = date.fromisoformat(str(a)[:10])
        db = date.fromisoformat(str(b)[:10])
    except ValueError:
        return 0.0
    return (db - da).days


def portfolio_replay(signals: list, *, start_balance: float = 10_000.0,
                     risk_pct: float = 1.0, heat_cap_pct: float = 6.0,
                     sector_cap_pct: float = 3.0, max_open: int | None = None,
                     sectors: dict | None = None, throttles: bool = True,
                     one_per_ticker: bool = False, reversals: bool = False,
                     rev_min_hold_days: float = 1.0,
                     rev_cooldown_days: float = 2.0,
                     rev_max_per_day: int = 1) -> dict:
    """Chronological replay under real capital constraints. Per-signal
    expectancy answers 'is the edge real'; THIS answers 'what does the
    account actually do'. The difference is skipped signals.

    `one_per_ticker` mirrors the live rule that the account holds at most one
    position per ticker, whatever strategy/horizon/direction produced it.

    `reversals` additionally models cutting a position short when the opposite
    side signals: the open position exits at the incoming signal's entry price
    (the best proxy available for "the live price when the flip fired"), its R
    is recomputed from that exit, and the new position opens normally.

    Two deliberate fidelity gaps versus live, both making this a PESSIMISTIC
    read of how often flips happen -- i.e. the backtest flips at least as
    freely as production would:

      * No confidence-margin guard. BacktestTrade carries no confidence
        score, so the live REVERSAL_MIN_CONF_MARGIN check cannot be applied
        and every opposite signal is a candidate.
      * Guards are in DAYS, not hours -- signals are dated, not timestamped.

    Both flags default False so existing callers replay exactly as before.
    """
    from swingbot.core.edge.throttle import current_throttle

    events = sorted(signals, key=lambda s: (s["date"], s["ticker"]))
    balance = start_balance
    curve = [(events[0]["date"] if events else "start", balance)]
    open_pos: list[dict] = []      # {"exit_date", "ticker", "sector", "risk_pct", "r"}
    taken = skipped = 0
    paused = False
    # Reversal bookkeeping: last flip date per ticker (cooldown), flips per
    # ticker per day (daily cap), and how much R the flips gained or gave up
    # versus letting those positions run to their original exits.
    last_flip: dict = {}
    flips_on_day: dict = {}
    reversed_n = 0
    reversal_r_delta = 0.0
    # R-multiples for trades actually opened, in the order this loop takes
    # them (chronological by entry date) -- the fixed distribution ruin.
    # simulate() bootstraps from. Recorded at open time, not close time, so
    # it excludes every signal this replay's heat/sector caps skipped.
    r_multiples_taken: list[float] = []
    # (strategy, outcome) for every trade actually opened -- recorded here
    # rather than read back off open_pos at the end, since open_pos entries
    # for trades that have already closed are removed from that list as
    # they exit (see step 1 above), same reasoning as r_multiples_taken.
    taken_strategy_outcomes: list[tuple[str, str | None]] = []

    for sig in events:
        # 1) close everything that exited before this signal's date
        due = [p for p in open_pos if p["exit_date"] <= sig["date"]]
        for p in sorted(due, key=lambda p: p["exit_date"]):
            balance *= 1 + (p["risk_pct"] / 100.0) * p["r"]
            curve.append((p["exit_date"], balance))
            open_pos.remove(p)

        # 2) throttle from the equity curve so far
        mult = 1.0
        if throttles:
            mult, paused = current_throttle([b for _, b in curve], was_paused=paused)
        eff_risk = risk_pct * mult
        if eff_risk <= 0:
            skipped += 1
            continue

        # 2b) one position per ticker -- and, optionally, flip it
        if one_per_ticker or reversals:
            held = next((p for p in open_pos if p["ticker"] == sig["ticker"]), None)
            if held is not None:
                flipped = False
                if (reversals
                        and sig.get("direction")
                        and held.get("direction")
                        and sig["direction"] != held["direction"]
                        and held.get("entry") is not None):
                    last = last_flip.get(sig["ticker"])
                    today_n = flips_on_day.get((sig["ticker"], sig["date"]), 0)
                    if (_days_between(held["entry_date"], sig["date"]) >= rev_min_hold_days
                            and (last is None
                                 or _days_between(last, sig["date"]) >= rev_cooldown_days)
                            and today_n < rev_max_per_day):
                        # Cut the old position at this signal's entry price and
                        # bank the recomputed R instead of the one it would have
                        # earned running to its stop or target.
                        r_early = _early_exit_r(held, sig["entry"])
                        balance *= 1 + (held["risk_pct"] / 100.0) * r_early
                        curve.append((sig["date"], balance))
                        open_pos.remove(held)
                        reversed_n += 1
                        reversal_r_delta += r_early - held["r"]
                        last_flip[sig["ticker"]] = sig["date"]
                        flips_on_day[(sig["ticker"], sig["date"])] = today_n + 1
                        flipped = True
                if not flipped:
                    skipped += 1
                    continue

        # 3) capacity checks
        heat = sum(p["risk_pct"] for p in open_pos)
        sec = (sectors or {}).get(sig["ticker"], sig.get("sector"))
        sec_heat = sum(p["risk_pct"] for p in open_pos if p["sector"] == sec)
        if (heat + eff_risk > heat_cap_pct + 1e-9
                or (sec and sec_heat + eff_risk > sector_cap_pct + 1e-9)
                or (max_open is not None and len(open_pos) >= max_open)):
            skipped += 1
            continue

        open_pos.append({"exit_date": sig["exit_date"], "ticker": sig["ticker"],
                         "sector": sec, "risk_pct": eff_risk, "r": sig["r_multiple"],
                         "direction": sig.get("direction"), "entry": sig.get("entry"),
                         "stop_loss": sig.get("stop_loss"), "entry_date": sig["date"]})
        taken += 1
        r_multiples_taken.append(sig["r_multiple"])
        taken_strategy_outcomes.append((sig.get("strategy", "UNKNOWN"), sig.get("outcome")))

    for p in sorted(open_pos, key=lambda p: p["exit_date"]):
        balance *= 1 + (p["risk_pct"] / 100.0) * p["r"]
        curve.append((p["exit_date"], balance))

    values = [b for _, b in curve]
    peak, max_dd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak * 100.0)

    months = 1.0
    if taken and len(curve) > 1:
        import datetime as dt
        d0 = dt.date.fromisoformat(str(curve[0][0])[:10]) if curve[0][0] != "start" else None
        d1 = dt.date.fromisoformat(str(curve[-1][0])[:10])
        months = max(((d1 - d0).days / 30.44) if d0 else 1.0, 1.0)

    # Per-strategy win rate of trades ACTUALLY TAKEN (post heat/sector/dedup
    # caps) -- the portfolio-level counterpart to run_backtest_range.py's
    # pool()'s win_rate, same "win"/"loss" outcome convention (scratch/
    # timeout excluded from both the numerator and denominator) so this is
    # directly comparable to validation_registry.json's per-strategy figures
    # (Task E92's per-strategy-WR-within-10-points gate).
    per_strategy_counts: dict[str, dict[str, int]] = {}
    for strat, outcome in taken_strategy_outcomes:
        c = per_strategy_counts.setdefault(strat, {"wins": 0, "losses": 0})
        if outcome == "win":
            c["wins"] += 1
        elif outcome == "loss":
            c["losses"] += 1
    per_strategy_wr = {
        strat: {
            "n": c["wins"] + c["losses"],
            "win_rate": round(c["wins"] / (c["wins"] + c["losses"]) * 100, 1)
                        if (c["wins"] + c["losses"]) else None,
        }
        for strat, c in per_strategy_counts.items()
    }

    return {"equity_curve": curve, "final_multiple": balance / start_balance,
            "max_dd_pct": round(max_dd, 2), "trades_taken": taken,
            "trades_skipped": skipped, "trades_per_month": round(taken / months, 1),
            "r_multiples_taken": r_multiples_taken,
            "per_strategy_wr": per_strategy_wr,
            # reversals_r_delta is the R actually banked by cutting positions
            # short MINUS the R those same positions would have earned running
            # to their original exits. Negative means the flips cost money.
            "reversals": reversed_n,
            "reversals_r_delta": round(reversal_r_delta, 4)}


def _trades_similar(a, b, tol_pct: float) -> bool:
    """Same test `has_similar_open_trade` (performance.py) applies live: same
    direction, entry/stop/target all within `tol_pct` of each other --
    regardless of which strategy/horizon produced either trade."""
    def _close(x, y):
        ref = max(abs(x), abs(y))
        if ref == 0:
            return True
        return abs(x - y) / ref * 100 <= tol_pct

    return (a.direction == b.direction
            and _close(a.entry, b.entry)
            and _close(a.stop_loss, b.stop_loss)
            and _close(a.take_profit, b.take_profit))


def collect_portfolio_signals(start: str, end: str, strategies=None, horizons=None) -> list:
    """Build a chronological signal list for `portfolio_replay` from real
    fold-run trades. Mirrors `_default_run`'s iteration structure (same
    symbol universe, same liquidity screen, same frictions/exit_model/
    scale_out/tp2_mode) so the portfolio numbers stay comparable to the
    E22 friction-adjusted baseline -- see `_frame_for` and `_default_run`
    docstrings for why those specific arguments are frozen.

    Only trades with both an `r_multiple` and an `exit_date` become
    signals -- open/unresolved trades can't be replayed under capital
    constraints because `portfolio_replay` needs a known exit to free
    heat.

    Dedup mirrors the live scanner's own same-ticker guard (`has_open_trade`
    / `has_similar_open_trade` in performance.py, enforced from
    scanning/engine.py ~1025-1039): the live account never opens a second
    position on a ticker while a near-identical one (same direction,
    entry/stop/target within `config.DEDUP_TOLERANCE_PCT`) is already open,
    no matter which strategy/horizon found either one. Naively pooling every
    (strategy, horizon) combo's trades here would let `portfolio_replay`
    model several such "concurrent" near-duplicate positions on one ticker
    stacking against the heat/sector caps -- capital the live account
    structurally could never have committed twice. So per symbol, trades
    are walked in entry-date order and a candidate is dropped (never becomes
    a signal) if a still-open similar trade -- one whose exit_date is later
    than this candidate's entry_date -- was already kept. This mirrors
    `require_confirmation=True` (the automatic/scheduled scan path engine.py
    actually applies the guard on), since a walk-forward replay models
    repeated automatic scanning over time, not a one-off `!check`.
    """
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest_daterange
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.marketdata.universe import liquidity_ok, sector_map

    strategies = ALL_STRATEGIES if strategies is None else strategies
    horizons = list(HORIZONS) if horizons is None else horizons
    sectors = sector_map(getattr(config, "SCAN_UNIVERSE", "watchlist") or "watchlist")
    tol_pct = getattr(config, "DEDUP_TOLERANCE_PCT", 2.0)

    signals = []
    # One flushed line per symbol. This loop is minutes-long (every symbol x
    # strategy x horizon), and CLAUDE.md's rule is that a long run must never
    # go silent -- wf_run.py --full already cost a monitoring session that way.
    all_syms = _symbols_for_folds()
    for si, sym in enumerate(all_syms, 1):
        df = _frame_for(sym)
        if df is None or not liquidity_ok(df):
            print(f"[{si}/{len(all_syms)}] {sym}: skipped (no frame / illiquid)", flush=True)
            continue
        print(f"[{si}/{len(all_syms)}] {sym}", flush=True)

        # (strategy, trade) pairs -- BacktestTrade itself carries no strategy
        # field (only the per-call BacktestSummary wrapper does), so the
        # strategy name has to be tagged on here, before pooling across
        # strategies erases which one produced each trade.
        candidates = []
        for strat in strategies:
            for hk in horizons:
                s = run_backtest_daterange(sym, df, strat, hk, start, end,
                                           frictions=True, exit_model="v2",
                                           scale_out=True, tp2_mode="levels")
                for t in (s.trades or []):
                    if t.r_multiple is not None and t.exit_date is not None:
                        candidates.append((strat, t))

        candidates.sort(key=lambda pair: pair[1].entry_date)
        open_similar: list = []
        for strat, t in candidates:
            open_similar = [o for o in open_similar if o[1].exit_date > t.entry_date]
            if any(_trades_similar(o[1], t, tol_pct) for o in open_similar):
                continue
            open_similar.append((strat, t))
            signals.append({"date": t.entry_date, "ticker": sym,
                            "sector": sectors.get(sym),
                            "r_multiple": t.r_multiple,
                            "exit_date": t.exit_date,
                            "strategy": strat,
                            "outcome": t.outcome,
                            # direction/entry/stop_loss are carried so
                            # portfolio_replay(reversals=True) can recognise an
                            # opposite-side signal and recompute the R of the
                            # position it cuts short. Ignored otherwise.
                            "direction": t.direction,
                            "entry": t.entry,
                            "stop_loss": t.stop_loss})
    return signals
