"""v144: the 23:30 next-session outlook -- the last closed bar, tomorrow's plans.

It runs the live scan's own pieces, never copies:
  * frames -- `closed_frames`, always refetched after the close and cut to the
    signal session's closed bar (a cache file's mtime proves nothing: a failed
    refresh re-stamps a CSV that still holds a partial bar);
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
from swingbot.core.db import write_failure
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import regime2
from swingbot.core.market import opex
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.session import US_MARKET_TZ, session_close
from swingbot.core.market.strategy import HORIZONS, LEGACY_HORIZONS
from swingbot.core.marketdata import data_store
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


def _cut_to(frame, day: dt.date):
    """The frame up to and including `day`; None when it is empty or does not end on `day`."""
    if frame is None or len(frame) == 0:
        return None
    cut = frame[frame.index.date <= day]
    return cut if len(cut) > 0 and cut.index[-1].date() == day else None


def closed_frames(symbols, bar_date: dt.date, now: dt.datetime) -> dict:
    """{symbol: daily frame whose last bar is bar_date's closed bar}.

    The cache is never read: one batched refetch a night, then each frame is cut
    at bar_date so a later bar can never reach the scan. Before the close nothing
    is trusted at all (the last bar would be partial). Dropped symbols are logged.
    """
    if _hours_since_close(bar_date, now) <= 0:
        log.warning("outlook: %s has not closed yet -- no frame is trustworthy", bar_date)
        return {}
    wanted = list(dict.fromkeys(symbols))
    frames = {symbol: _cut_to(frame, bar_date) for symbol, frame in fetch._fetch_cold_frames(wanted, None)}
    kept = {symbol: frame for symbol, frame in frames.items() if frame is not None}
    dropped = [symbol for symbol in wanted if symbol not in kept]
    if dropped:
        log.warning("outlook: no closed %s bar for %d symbol(s): %s", bar_date, len(dropped), ", ".join(dropped))
    return kept


# --- scoring and gates ------------------------------------------------------------

def _target_tier(target: dt.date) -> str | None:
    """The expiration tier of the session the plans trade (None when the flag is off).
    `current_tier` is flag-guarded and takes its date in US market time."""
    return opex.current_tier(dt.datetime.combine(target, dt.time(12), tzinfo=US_MARKET_TZ))


def _rs_cache(frames: dict, spy) -> dict:
    """In memory, as the replay does -- never data/universe/rs_cache.json, which the
    regular base scan and the retrospective read."""
    return {"rels": {ticker: rs_factors.relative_return(frame, spy) for ticker, frame in frames.items()}}


def _scored_items(frames: dict, spy, tier: str | None) -> tuple[list, object, float | None]:
    params = ScanParams.from_config()
    min_confluence = opex.effective_min_confluence(params.min_target_confluence_count, tier)
    min_level = opex.effective_min_confidence_level(tier)
    hard = scan_run._hard_filters_snapshot(params)
    rs_cache = _rs_cache(frames, spy)
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


def _sector_inputs(tickers: list, bar_date: dt.date, now: dt.datetime) -> tuple[dict, dict, dict]:
    """Sector ETFs go through `closed_frames` too: the live `_fetch_frames` is cache-first
    and would hand a mid-session partial bar to the sector RS."""
    try:
        etf_of = fetch._etf_symbol_of_sector()
        sector_of, needed = fetch._sector_etfs_for_tickers(tickers)
        return sector_of, etf_of, (closed_frames(needed, bar_date, now) if needed else {})
    except Exception:
        log.warning("outlook: sector ETFs unavailable -- ticker-only RS", exc_info=True)
        return {}, {}, {}


def _regimes(spy):
    try:
        return regime2.regime_series(spy)
    except Exception:
        return None


def _context(frames: dict, spy, regime, breadth, bar_date: dt.date, now: dt.datetime) -> qualify.QualifyContext:
    sector_of, etf_of, sector_frames = _sector_inputs(list(frames), bar_date, now)
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
    """`skipped` lists only tickers that were open BEFORE this run; one issued here
    and met again as a second item is dropped silently."""
    issued: set = set()
    for item in ordered:
        plan, ticker = item.plan_v2, item.result.ticker
        if plan is None or ticker in issued:
            continue
        if ticker in open_tickers:
            if ticker not in result.skipped:
                result.skipped.append(ticker)
        elif plan.entry_type != STOP_ENTRY:
            result.watch.append(_plan_line(item, plan))
        else:
            _issue(item, plan, result, frames, spy)
            issued.add(ticker)


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
    result.plans.append(_plan_line(item, plan, risk=_risk_dollars(plan)))   # persisted: counted before the card
    result.alerts.append(_card(item, plan, result.target, explanation, nums, df, frames, spy, trade_id, fit))


def _hourly(ticker: str):
    try:
        return data_store.load_from_disk(ticker, "hourly")
    except Exception:
        return None                    # display-only context; never fails a card


def _card(item, plan, target, explanation, nums, df, frames, spy, trade_id, fit) -> tuple:
    chart_path, chart_filename = short_run._render_chart(item, nums, df, frames, spy, trade_id, fit)
    short_run._stamp_risk_flags(item, frames, account_module.load_account_config())
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
    items, regime, breadth = _scored_items(scan_frames, spy, _target_tier(result.target))
    context = _context(scan_frames, spy, regime, breadth, result.bar_date, now)
    accepted, result.near_misses = _verdicts(items, context)
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
        _fill_keeping_issued(result, now)
    return result


def _fill_keeping_issued(result: OutlookResult, now: dt.datetime) -> None:
    """A failure partway keeps what was already issued: those plans and trades are
    stored, so their cards must still post. A store-write halt propagates (it
    carries the cards); any other failure is recorded on the result."""
    try:
        _fill(result, now)
    except Exception as exc:
        halt = as_halt(exc, result.alerts)
        if halt is exc:
            raise
        if halt is not None:
            raise halt from exc
        if not result.plans:
            raise
        log.exception("outlook run failed after %d plan(s) were logged", len(result.plans))
        tickers = ", ".join(line.ticker for line in result.plans)
        result.unavailable = (f"scan failed after {len(result.plans)} plan(s) already issued and logged "
                              f"({tickers}); {type(exc).__name__}: {exc}")[:300]


def as_halt(exc: BaseException, alerts) -> write_failure.StoreWriteHalt | None:
    """The base-lane rule: any database failure halts issuance. Returns `exc`
    itself when it already is a halt, a new halt carrying the built cards when it
    is another database failure, None when it is not a store failure."""
    if isinstance(exc, write_failure.StoreWriteHalt):
        return exc
    if write_failure.halts_issuance(exc):
        return write_failure.StoreWriteHalt(f"outlook store write failed: {type(exc).__name__}: {exc}"[:300],
                                            alerts=list(alerts))
    return None
