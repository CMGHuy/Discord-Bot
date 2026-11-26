"""v239: the bear-regime pass -- every wiring decision of the daily trend engine.

Once per scan pass (V239-10): `off` reads nothing; else a stored row for D is
read back, or SPY and ^VIX are fetched here (truthful providers), cut to bars
<= s, classified and inserted once -- the notice only from the winning insert.
A stale-SPY UNKNOWN is stamped but never stored, so the next pass retries.

Spec: docs/superpowers/specs/implemented/2026-11-23-v239-bear-regime-engine-shadow-design.md
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

import pandas as pd

from swingbot import config
from swingbot.core.db.repositories.market_regime import market_regime_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.marketdata.data import get_daily_data
from swingbot.core.scanning import regime_calendar, regime_notices

log = logging.getLogger(__name__)

MODES = ("off", "shadow", "live")
FETCH_PERIOD = "2y"
#: Stored sessions read to find the prior confirmed episode (about three months).
PRIOR_SESSIONS = 60


def regime_mode() -> str:
    mode = str(getattr(config, "BEAR_REGIME_MODE", "off") or "off").strip().lower()
    return mode if mode in MODES else "off"


def _fetch(symbol: str) -> pd.DataFrame:
    return get_daily_data(symbol, period=FETCH_PERIOD)


def _frame(fetch: Callable[[str], pd.DataFrame], symbol: str,
           now: datetime) -> tuple[pd.DataFrame | None, str | None]:
    """Completed bars dated <= s and their provider; (None, None) when the fetch fails."""
    try:
        df = fetch(symbol)
    except Exception as exc:
        swallowed(log, "scan.regime.fetch", exc, "regime: %s daily fetch failed: %s",
                  symbol, exc)
        return None, None
    source = (getattr(df, "attrs", None) or {}).get("source")
    return regime_calendar.cut_completed(df, now), source


def _compute_day(now: datetime, fetch: Callable[[str], pd.DataFrame]) -> br.RegimeDay:
    last, target = regime_calendar.session_pair(now)
    spy, spy_source = _frame(fetch, br.SPY, now)
    vix, vix_source = _frame(fetch, br.VIX, now)
    return br.classify(spy, vix, last_session=last, session_date=target,
                       spy_provider=spy_source, vix_provider=vix_source)


def _open_longs(trades) -> int | None:
    try:
        if trades is None:
            from swingbot.core.scanning.singletons import trade_log
            trades = trade_log.get_trades(status="open", limit=None) or []
        return sum(1 for trade in trades if trade.get("direction") == "bullish")
    except Exception as exc:
        swallowed(log, "scan.regime.open_trades", exc, "regime: open trades unreadable: %s", exc)
        return None


def _unfilled(plans, new_state: str) -> list[dict] | None:
    try:
        if plans is None:
            from swingbot.core.planning.plan_store import PlanStore
            plans = PlanStore().open_plans()
        return regime_notices.unfilled_bullish_rows(plans, new_state=new_state)
    except Exception as exc:
        swallowed(log, "scan.regime.open_plans", exc, "regime: open plans unreadable: %s", exc)
        return None


def _transition(day: br.RegimeDay, prior: list[br.RegimeDay]) -> ep.Transition | None:
    keyed = [(p.session_date, ep.episode_key(p.state, p.stress)) for p in prior]
    return ep.confirmed_transition(
        keyed, (day.session_date, ep.episode_key(day.state, day.stress)))


def _notice_for(day: br.RegimeDay, now: datetime, repo, plans, trades) -> dict | None:
    prior = [br.RegimeDay.from_row(row) for row in repo.recent(PRIOR_SESSIONS)]
    transition = _transition(day, prior)
    if transition is None and not day.pullback_trigger:
        return None
    gap = (regime_calendar.sessions_between(prior[-1].session_date, day.session_date)
           if prior else None)
    payload = regime_notices.notice_payload(
        day, transition, open_longs=_open_longs(trades), unfilled=_unfilled(plans, day.state),
        gap_sessions=gap, now=now)
    return regime_notices.notice_event(payload, session_date=day.session_date)


def _safe_notice(day: br.RegimeDay, now: datetime, repo, plans, trades) -> dict | None:
    """A notice that cannot be built never costs the stored day."""
    try:
        return _notice_for(day, now, repo, plans, trades)
    except Exception as exc:
        swallowed(log, "scan.regime.notice", exc,
                  "regime: notice not built; the day is still stored: %s", exc, exc_info=True)
        return None


def _labelled(now: datetime, repo, fetch, plans, trades) -> br.RegimeDay:
    _, target = regime_calendar.session_pair(now)
    stored = repo.day(target)
    if stored is not None:
        return br.RegimeDay.from_row(stored)
    day = _compute_day(now, fetch)
    if day.unknown_reason == br.REASON_STALE:
        return day
    event = _safe_notice(day, now, repo, plans, trades)
    if repo.insert_once({**day.to_row(), "computed_at": now}, notice_event=event):
        return day
    winner = repo.day(target)
    return br.RegimeDay.from_row(winner) if winner is not None else day


def regime_for_pass(*, now: datetime | None = None, repo=None,
                    fetch: Callable[[str], pd.DataFrame] | None = None,
                    plans=None, trades=None) -> br.RegimeDay | None:
    """The day this pass stamps; None under `off` or on any failure."""
    if regime_mode() == "off":
        return None
    try:
        return _labelled(now or datetime.now(timezone.utc), repo or market_regime_repo(),
                         fetch or _fetch, plans, trades)
    except Exception as exc:
        swallowed(log, "scan.regime.pass", exc,
                  "regime pass failed; scanning without a label: %s", exc, exc_info=True)
        return None
