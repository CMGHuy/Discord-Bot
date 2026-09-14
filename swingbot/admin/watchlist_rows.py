"""Market and signal columns for the Watchlist, built in one batch each.

Spec v85 D33 (market) / D34 (signal). The rule that shapes this module: **one
batch call for the whole watchlist, never one call per row.** A ninety-symbol
watchlist rendered with a per-row fetch is ninety network round trips on
every page view, and the cache (D33) / the plan store (D34) already holds
every number this page needs.

`as_of` is the date of the bar the figures came from, not the time the request
was served. A page that prints "as of now" over Friday's close on a Sunday is
the failure this field exists to prevent.

**The Signal column is the bot's own opinion, not a price derivative.** The
bot does not persist a per-symbol score -- its opinion IS the live plan set.
A PENDING plan is a setup the scanner found and is waiting to trigger; an
ACTIVE/PARTIAL plan is one it is already working. `build_signals` does not
run a scan (minutes of work) -- it reads the plan set PlanStore already holds
(a dictionary lookup), the same source `/analytics/plans` reads.
"""

from __future__ import annotations

import pandas as pd

from swingbot import config
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.marketdata.data import (
    get_current_price_batch,
    get_daily_data_batch,
    is_us_market_active,
)
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore

#: ACTIVE-family beats PENDING regardless of score; within a tier, the
#: highest quality_score wins. CLOSED/CANCELLED plans are not "live" and are
#: absent from this map entirely, so they never enter the comparison.
_TIER = {PlanStatus.PENDING: 0, PlanStatus.ACTIVE: 1, PlanStatus.PARTIAL: 1}

#: Trading-day offsets for the three change columns. 5 and 21 are a week and a
#: month of *business* days, which is what the cache is indexed by -- calendar
#: arithmetic here would silently straddle holidays.
_WINDOWS = {"change_1d_pct": 1, "change_1w_pct": 5, "change_1m_pct": 21}

_SPARK_BARS = 30


def _pct_change(closes: pd.Series, back: int) -> float | None:
    """Percentage change over `back` bars, or None when history is too short.

    None, never 0.0: a symbol listed three days ago has no one-month change,
    and 0.0 would claim it was flat.
    """
    if len(closes) <= back:
        return None
    prev = float(closes.iloc[-1 - back])
    if prev == 0:
        return None
    return round((float(closes.iloc[-1]) / prev - 1.0) * 100.0, 2)


def _empty_row() -> dict:
    return {
        "price": None,
        "as_of": None,
        "change_1d_pct": None,
        "change_1w_pct": None,
        "change_1m_pct": None,
        "spark": [],
    }


def _cached_daily(ticker: str) -> pd.DataFrame | None:
    """The same market_data/daily/{TICKER}.csv cache scanning/fetch.py's
    _crawl_latest_data already reads (same is_stale/load_normalized pair,
    same SCAN_CACHE_MAX_AGE_HOURS freshness bar) -- not reimplemented
    independently, just read from here too. `market_data_refresh`
    (commands/scanning.py) already keeps this warm for exactly
    load_watchlist()'s tickers, so in steady state this function costs no
    network at all. None means cold (missing, stale, or unreadable); the
    caller batch-fetches only the tickers this returns None for.

    Added 2026-09-14: build_market_rows used to call get_daily_data_batch
    for the WHOLE watchlist on every single page view -- a live 6-month
    download for ~75 tickers, unconditionally, which was the watchlist's
    reported slow-load cause. Checking the warm cache first turns most
    page views into zero network calls instead of one large one.
    """
    try:
        if data_refresh.is_stale(ticker, "daily", max_age_hours=config.SCAN_CACHE_MAX_AGE_HOURS):
            return None
        return data_store.load_normalized(ticker, "daily")
    except Exception:
        return None


def build_market_rows(tickers: list[str]) -> dict[str, dict]:
    """Price, changes and a 30-bar sparkline for every ticker, keyed by symbol.

    Every requested symbol gets a row. A symbol the cache has nothing for gets
    a row of nulls rather than being dropped -- the Watchlist must still list
    it, and an omitted row would read as "removed from the watchlist".
    """
    if not tickers:
        return {}

    cached = {t: _cached_daily(t) for t in tickers}
    cold = [t for t, df in cached.items() if df is None]
    # Still one batch call, never one per row -- just for whichever subset
    # (often none, in steady state) the warm cache didn't already cover.
    fetched = get_daily_data_batch(cold, period="6mo") if cold else {}
    frames = {**{t: df for t, df in cached.items() if df is not None}, **fetched}

    live: dict[str, float] = {}
    if is_us_market_active():
        try:
            live = get_current_price_batch(list(tickers)) or {}
        except Exception:
            # An intraday overlay is a nicety. Losing it must not lose the
            # closes, which are the page's actual content.
            live = {}

    rows: dict[str, dict] = {}
    for symbol in tickers:
        frame = frames.get(symbol)
        if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
            rows[symbol] = _empty_row()
            continue

        closes = frame["Close"].dropna()
        if closes.empty:
            rows[symbol] = _empty_row()
            continue

        row = _empty_row()
        row["price"] = round(float(live.get(symbol) or closes.iloc[-1]), 4)
        row["as_of"] = str(pd.Timestamp(closes.index[-1]).date())
        for field, back in _WINDOWS.items():
            row[field] = _pct_change(closes, back)
        row["spark"] = [round(float(v), 4) for v in closes.iloc[-_SPARK_BARS:]]
        rows[symbol] = row

    return rows


def _empty_signal() -> dict:
    # score is None, never 0 -- 0 would read as "confirmed low-quality setup"
    # rather than "the scanner has no opinion on this symbol at all".
    return {"state": "none", "score": None, "horizon": None, "strategy": None}


def build_signals(tickers: list[str]) -> dict[str, dict]:
    """The bot's own verdict for every ticker, keyed by symbol.

    Reads the whole live plan set with one `PlanStore().all()` call, never
    one per symbol. Per ticker: an ACTIVE-family plan (ACTIVE or PARTIAL)
    always outranks a PENDING one regardless of score; among same-tier
    candidates the highest `quality_score` wins. A ticker with only a
    CLOSED/CANCELLED plan, or no plan at all, reads as `state: "none"`,
    `score: None`.
    """
    if not tickers:
        return {}

    wanted = set(tickers)
    best: dict[str, object] = {}
    for plan in PlanStore().all():
        if plan.ticker not in wanted or plan.status not in _TIER:
            continue
        current = best.get(plan.ticker)
        if current is None or (
            (_TIER[plan.status], plan.quality_score)
            > (_TIER[current.status], current.quality_score)
        ):
            best[plan.ticker] = plan

    signals: dict[str, dict] = {t: _empty_signal() for t in tickers}
    for ticker, plan in best.items():
        signals[ticker] = {
            "state": "active" if plan.status in (PlanStatus.ACTIVE, PlanStatus.PARTIAL) else "pending",
            "score": plan.quality_score,
            "horizon": plan.horizon_key,
            "strategy": plan.strategy,
        }

    return signals
