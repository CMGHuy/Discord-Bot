"""v144: the 23:30 next-session outlook -- the last closed bar, tomorrow's plans.

It runs the live scan's own pieces, never copies:
  * frames -- `closed_frames`, bars whose last row is the signal session's
    closed bar (a cache file written before that close is refetched);
  * scoring -- `analyze._scan_one` with OUTLOOK_IO (no open-trade monitoring, so
    23:30 closes nothing) and `live_prices={}`, as the replay does;
  * gates -- `qualify.qualify_short_item` with no confirmation store (a once-a-
    night run has no scan-to-scan debounce), then dedup and the live sort.

Each accepted item goes one of three ways. A `stop_entry` plan is issued as an
outlook plan (origin next_session, valid_session = the target session) with a
placeholder trade. A market-entry plan is a WATCH name only: it would be born
ACTIVE at a price nobody can trade at 23:30 (spec v144 amendment 1). A plan the
builder rejected is a near-miss. Issuance is the last step, after the whole scan
succeeded, so a failing scan issues nothing. Nothing here touches the regular
lane's confirmation store, plans or trades.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot import config
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import regime2
from swingbot.core.market import opex
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.session import US_MARKET_TZ, session_close
from swingbot.core.market.strategy import HORIZONS, LEGACY_HORIZONS
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.origin import NEXT_SESSION
from swingbot.scan_params import ScanParams

from . import (analyze, dedup, fetch, lane_overlap, outlook_context, outlook_embeds,
               outlook_session, qualify, scan_run, short_run)
from .embeds import build_embed, build_simple_alert
from .outlook_types import OutlookLine, OutlookResult
from .plan_table import plan_numbers_for_display
from .singletons import trade_log

log = logging.getLogger(__name__)

REGIME_SYMBOLS = ("SPY", "QQQ")
STOP_ENTRY = "stop_entry"
OUTLOOK_IO = analyze.ScanIO(stop_requested=analyze._live_stop_requested,
                            monitor_scan=lambda *a: ([], []), monitor_open=lambda *a: ([], []),
                            track_record=analyze._live_track_record)


# --- closed bars ------------------------------------------------------------------

def _hours_since_close(bar_date: dt.date, now: dt.datetime) -> float:
    closed_at = dt.datetime.combine(bar_date, session_close(bar_date), tzinfo=US_MARKET_TZ)
    return (now - closed_at).total_seconds() / 3600.0


def _cached_after_close(symbol: str, hours: float):
    """The cached daily frame only if the file was written after the close."""
    if hours <= 0:
        return None
    try:
        if data_refresh.is_stale(symbol, "daily", max_age_hours=hours):
            return None
        return data_store.load_normalized(symbol, "daily")
    except Exception:
        log.debug("outlook: cache read failed for %s -- fetching", symbol, exc_info=True)
        return None


def _ends_on(frame, day: dt.date) -> bool:
    return frame is not None and len(frame) > 0 and frame.index[-1].date() == day


def closed_frames(symbols, bar_date: dt.date, now: dt.datetime) -> dict:
    """{symbol: daily frame whose last bar is bar_date's closed bar}."""
    hours = _hours_since_close(bar_date, now)
    frames, cold = {}, []
    for symbol in dict.fromkeys(symbols):
        frame = _cached_after_close(symbol, hours)
        if frame is None:
            cold.append(symbol)
        else:
            frames[symbol] = frame
    for symbol, frame in fetch._fetch_cold_frames(cold, None):
        if frame is not None:
            frames[symbol] = frame
    return {symbol: frame for symbol, frame in frames.items() if _ends_on(frame, bar_date)}


# --- scoring and gates ------------------------------------------------------------

def _scored_items(frames: dict, spy) -> tuple[list, object, float | None]:
    tier = opex.current_tier()
    params = ScanParams.from_config()
    min_confluence = opex.effective_min_confluence(params.min_target_confluence_count, tier)
    min_level = opex.effective_min_confidence_level(tier)
    hard = scan_run._hard_filters_snapshot(params)
    rs_cache = rs_factors.refresh_rs_cache(frames, spy)
    breadth = rs_factors.breadth_pct_above_50ema(frames)
    regime = scan_run.get_regime(spy)
    per_ticker = fetch.map_tickers(
        lambda ticker: analyze._scan_one(
            ticker, frames[ticker], list(LEGACY_HORIZONS), None, regime, min_confluence, min_level,
            rs_cache=rs_cache, spy_df=spy, breadth=breadth, live_prices={}, hard_filters=hard,
            opex_tier_today=tier, io=OUTLOOK_IO),
        list(frames))
    items = [item for result in per_ticker if result is not None for item in result["items"]]
    return items, regime, breadth


def _sector_inputs(tickers: list) -> tuple[dict, dict, dict]:
    try:
        etf_of = fetch._etf_symbol_of_sector()
        sector_of, needed = fetch._sector_etfs_for_tickers(tickers)
        return sector_of, etf_of, (fetch._fetch_frames(needed) if needed else {})
    except Exception:
        log.warning("outlook: sector ETFs unavailable -- ticker-only RS", exc_info=True)
        return {}, {}, {}


def _regimes(spy):
    try:
        return regime2.regime_series(spy)
    except Exception:
        return None


def _context(frames: dict, spy, regime, breadth) -> qualify.QualifyContext:
    sector_of, etf_of, sector_frames = _sector_inputs(list(frames))
    return qualify.QualifyContext(
        frames=frames, spy=spy, sector_of=sector_of, etf_symbol_of=etf_of,
        sector_frames=sector_frames, regime=regime, regimes=_regimes(spy), breadth=breadth)


def _scenario_line(item, reason: str | None = None) -> OutlookLine:
    scenario = item.plan
    return OutlookLine(item.result.ticker, item.result.trend, item.result.strategy,
                       float(scenario.entry), float(scenario.stop_loss), float(scenario.take_profit),
                       reason=reason)


def _near_reason(item) -> str:
    stop_pct = getattr(item.plan, "stop_distance_pct", float("nan"))
    return f"{item.plan_v2_rejected} (stop {stop_pct:.1f}% from entry)"


def _verdicts(items: list, context) -> tuple[list, list[OutlookLine]]:
    """(accepted items, near-miss lines). Only a fully-qualifying item reaches
    the plan builder; a plan-stage rejection is a near-miss, the rest is silence."""
    accepted, near = [], []
    for item in items:
        if not item.all_requirements_met:
            continue
        verdict = qualify.qualify_short_item(None, item, context)
        if isinstance(verdict, qualify.Accepted):
            accepted.append(item)
        elif verdict.stage == "plan":
            near.append(_scenario_line(item, _near_reason(item)))
    return accepted, near


def _ordered(accepted: list) -> list:
    deduped = dedup.dedup_scan_items(accepted)
    deduped.sort(key=lambda item: (item.all_requirements_met, item.conf.score), reverse=True)
    return deduped


# --- routing and issuance ---------------------------------------------------------

def outlook_open_tickers() -> set[str]:
    """Tickers already holding an open outlook plan or trade. Regular plans and
    trades never count: the lanes are independent (spec v144 § Independence)."""
    plans = {plan.ticker for plan in PlanStore().open_plans() if plan.origin == NEXT_SESSION}
    trades = {trade["ticker"] for trade in trade_log.get_trades(status="open", limit=None) or []
              if trade.get("origin") == NEXT_SESSION}
    return plans | trades


def _plan_line(item, plan, risk: float | None = None) -> OutlookLine:
    return OutlookLine(item.result.ticker, plan.direction, plan.strategy, float(plan.trigger_price),
                       float(plan.stop_loss), float(plan.tp1), risk_dollars=risk)


def _risk_dollars(plan) -> float | None:
    try:
        sizing = account_module.compute_position_size(plan.trigger_price, plan.stop_loss)
    except Exception:
        return None
    if not sizing or not sizing.get("shares"):
        return None
    return round(float(sizing["shares"]) * abs(float(plan.trigger_price) - float(plan.stop_loss)), 2)


def _route(ordered: list, open_tickers: set, result: OutlookResult, frames: dict, spy) -> None:
    for item in ordered:
        plan, ticker = item.plan_v2, item.result.ticker
        if plan is None:
            continue
        if ticker in open_tickers:
            if ticker not in result.skipped:
                result.skipped.append(ticker)
        elif plan.entry_type != STOP_ENTRY:
            result.watch.append(_plan_line(item, plan))
        else:
            _issue(item, plan, result, frames, spy)
            open_tickers.add(ticker)


def _issue(item, plan, result: OutlookResult, frames: dict, spy) -> None:
    """Persist one outlook plan and its placeholder trade, then build its card."""
    ticker, horizon = item.result.ticker, HORIZONS[item.result.horizon_key]
    plan.origin, plan.valid_session = NEXT_SESSION, result.target.isoformat()
    scenario = item.plan
    explanation = build_explanation(
        item.result, earnings_info=scan_run._earnings_in_window(ticker, horizon["max_holding_days"]),
        target_confluence=item.target_confluence, stop_confluence=item.stop_confluence,
        confirmed_by=item.combined_from, plan=plan)
    nums = plan_numbers_for_display(plan, {"entry": scenario.entry, "stop_loss": scenario.stop_loss,
                                           "take_profit": scenario.take_profit,
                                           "target2": scenario.target2_price})
    item.paper_logged, item.not_logged_reason = True, None
    df = frames.get(ticker)
    fit = short_run._fit_trendline(df, scenario, horizon, item.result.trend)
    trade_id = short_run._log_trade(item, nums, explanation, fit, result.alerts, origin=NEXT_SESSION)
    result.alerts.append(_card(item, plan, result.target, explanation, nums, df, frames, spy, trade_id, fit))
    result.plans.append(_plan_line(item, plan, risk=_risk_dollars(plan)))


def _hourly(ticker: str):
    try:
        return data_store.load_from_disk(ticker, "hourly")
    except Exception:
        return None                    # display-only context; never fails a card


def _card(item, plan, target, explanation, nums, df, frames, spy, trade_id, fit) -> tuple:
    chart_path, chart_filename = short_run._render_chart(item, nums, df, frames, spy, trade_id, fit)
    embed = build_embed(item, explanation, trade_log.get_stats(item.conf.level), None, chart_filename,
                        htf_info=item.htf_info, layout=config.ALERT_EMBED_LAYOUT)
    outlook_embeds.decorate_card(
        embed, valid_session=target,
        context_line=outlook_context.context_line(df, _hourly(item.result.ticker), plan.direction))
    lane_overlap.append_overlap_field(embed, item.result.ticker, viewer_origin=NEXT_SESSION)
    return (embed, chart_path, plan, build_simple_alert(item))


# --- the run ----------------------------------------------------------------------

def _blocker(result: OutlookResult) -> str | None:
    if config.PLAN_ENGINE_V2 != "on":
        return "PLAN_ENGINE_V2 is not 'on', so no plan can be built"
    if result.bar_date is None:
        return "no NYSE session on or before the run date in the calendar"
    return None


def _fill(result: OutlookResult, now: dt.datetime) -> None:
    tickers = scan_run._scan_tickers()
    frames = closed_frames([*tickers, config.MARKET_REGIME_TICKER, *REGIME_SYMBOLS], result.bar_date, now)
    spy = frames.get(config.MARKET_REGIME_TICKER)
    if spy is None:
        result.unavailable = (f"no closed {config.MARKET_REGIME_TICKER} daily bar for "
                              f"{result.bar_date.isoformat()}")
        return
    result.regime_lines = outlook_context.regime_lines({s: frames.get(s) for s in REGIME_SYMBOLS})
    scan_frames = short_run._stamp_context({t: frames[t] for t in tickers if t in frames}, spy)
    items, regime, breadth = _scored_items(scan_frames, spy)
    accepted, result.near_misses = _verdicts(items, _context(scan_frames, spy, regime, breadth))
    _route(_ordered(accepted), outlook_open_tickers(), result, scan_frames, spy)


def run_outlook(run_date: dt.date, *, now: dt.datetime | None = None) -> OutlookResult:
    """The whole 23:30 run for one Berlin run date. Synchronous and heavy:
    call it through asyncio.to_thread."""
    now = now or dt.datetime.now(dt.timezone.utc)
    result = OutlookResult(run_date=run_date, target=outlook_session.target_session(run_date),
                           bar_date=outlook_session.signal_session(run_date))
    if result.target is None:
        return result
    result.unavailable = _blocker(result)
    if result.unavailable is None:
        _fill(result, now)
    return result
