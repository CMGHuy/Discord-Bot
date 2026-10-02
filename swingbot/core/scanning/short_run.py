"""V118-4: the SHORT extra-universe scan, run AFTER the base alerts were sent.

Why a separate pass and not a phase of `_sync_run_scan`: the extra crawl can be
cold (network), so it must never delay, reorder or be counted in the base
scan's phases or telemetry. The callers (`commands/scanning`) await the base
`run_scan()`, post its alerts, and only then call `run_short_universe_scan()`.

Isolation: extra symbols are scanned bearish-only (`analyze.scan_extra_candidate`),
never enter the base `tickers`/`fresh_data`, base breadth, `rs_cache.json` or
the strategy pass, and use an in-memory reference RS cache. Nothing here places
an order or claims a borrow is available.
"""
import asyncio
import logging

from swingbot import config
from swingbot.core.charts.decision_chart import render_decision_chart
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.charts.trendline_fit import fit_trendline
from swingbot.core.db import write_failure
from swingbot.core.edge import correlation as corr_mod
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import heat as heat_mod
from swingbot.core.edge import regime2
from swingbot.core.edge import throttle
from swingbot.core.infra.logsetup import new_scan_id, scan_context
from swingbot.core.infra.notifier import notify_secondary
from swingbot.core.market import market_context, opex
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.session import session_date
from swingbot.core.market.strategy import HORIZONS, LEGACY_HORIZONS
from swingbot.core.marketdata import universe
from swingbot.core.marketdata.data import get_currency_symbol
from swingbot.core.planning.account import load_account_config
from swingbot.scan_params import ScanParams

from . import analyze, dedup, fetch, qualify, runstate, scan_run, short_funnel, telemetry
from .embeds import (build_embed, build_simple_alert, notify_closed_trades,
                     notify_near_close, plan_numbers_for_display)
from .short_candidates import extra_symbols
from .short_funnel import ShortFunnel
from .singletons import state, trade_log

log = logging.getLogger(__name__)


# --- inputs ---------------------------------------------------------------------

def _stamp_context(frames: dict, spy_df) -> dict:
    """Frames with the ctx_* block the base lane stamps; a failure keeps the raw frame."""
    stamped = {}
    for ticker, df in frames.items():
        try:
            stamped[ticker] = market_context.attach(df, spy_df=spy_df)
        except Exception:
            log.exception("market_context.attach failed for %s", ticker)
            stamped[ticker] = df
    return stamped


def _open_extra_tickers(base_tickers) -> list:
    """Symbols with an open paper trade that the base lane does not scan."""
    open_trades = trade_log.get_trades(status="open", limit=None)
    return sorted({t["ticker"] for t in open_trades if t.get("ticker")} - set(base_tickers))


def _scan_context(reference, params, live_prices, regime) -> "analyze.ExtraScanContext":
    tier = opex.current_tier()
    return analyze.ExtraScanContext(
        regime=regime,
        min_confluence=opex.effective_min_confluence(params.min_target_confluence_count, tier),
        min_confidence=opex.effective_min_confidence_level(tier),
        rs_cache={"rels": dict(enumerate(reference.reference_rels))},
        spy_df=reference.spy, live_prices=live_prices,
        hard_filters=scan_run._hard_filters_snapshot(params), opex_tier=tier, now=reference.now)


def _spy_frame(base_frames: dict):
    spy = base_frames.get(config.MARKET_REGIME_TICKER)
    return spy if spy is not None else fetch._daily_frame_for(config.MARKET_REGIME_TICKER)


def _note(funnel, direction, stage, reason=None, mode=short_funnel.UNSELECTED, symbol=None) -> None:
    """Record a lane-level (no ScanItem yet) funnel fact; no-op without a funnel."""
    if funnel is not None:
        funnel.record(direction, short_funnel.EXTRA_SOURCE, mode, stage, reason)
        if symbol is not None and stage == "candidate":
            funnel.candidate_symbols.add(symbol)


def _note_unresolved(funnel, queue, frames, reason) -> None:
    """Every queued symbol with no frame, under its crawl stop reason (budget/stale/missing)."""
    cap = config.SHORT_UNIVERSE_MAX_SYMBOLS
    for position, symbol in enumerate(queue):
        if symbol not in frames:
            _note(funnel, short_funnel.BEARISH, "candidate",
                  reason or ("symbol_cap" if position >= cap else "missing_frame"), symbol=symbol)


def _crawl_extra(snapshot, base_tickers, funnel=None) -> dict:
    queue = [] if snapshot is None else list(extra_symbols(snapshot, base_tickers))
    frames, reason = fetch._crawl_bounded(
        queue, max_symbols=config.SHORT_UNIVERSE_MAX_SYMBOLS,
        budget_s=config.SHORT_UNIVERSE_FETCH_BUDGET_SECONDS)
    _note_unresolved(funnel, queue, frames, reason)
    if reason is not None:
        log.warning("SHORT extra lane: crawl ended early (%s) -- %d/%d symbol(s) resolved",
                    reason, len(frames), len(queue))
    elif len(queue) > config.SHORT_UNIVERSE_MAX_SYMBOLS:
        log.info("SHORT extra lane: queue capped at %d of %d symbol(s)",
                 config.SHORT_UNIVERSE_MAX_SYMBOLS, len(queue))
    return frames


def _monitor_stranded(base_tickers, candidate_tickers, extra_frames, live_prices, ctx, funnel=None) -> None:
    """Monitor every outstanding extra-lane trade the scan below will not touch.

    A symbol that is not a candidate today (or whose fetch fell outside the
    symbol cap/budget) must not strand its open plan: it is crawled
    separately and monitored for SL/TP exactly as a candidate would be.
    """
    stranded = [t for t in _open_extra_tickers(base_tickers) if t not in candidate_tickers]
    missing = [t for t in stranded if t not in extra_frames]
    frames = {**extra_frames, **(fetch._crawl_latest_data(missing, None) if missing else {})}
    for ticker in stranded:
        if funnel is None or ticker not in funnel.candidate_symbols:   # one candidate-stage row per symbol
            _note(funnel, short_funnel.BEARISH, "candidate", "not_selected", symbol=ticker)
        # no new entry for it; it is still monitored below
        closed, near = analyze.monitor_open_only(ticker, frames.get(ticker), live_prices.get(ticker))
        ctx.newly_closed.extend(closed)
        ctx.near_close.extend(near)


# --- confirmation / gates / plan -----------------------------------------------------

def _qualify_context(require_confirmation, frames, lane) -> qualify.QualifyContext:
    """The live inputs to `qualify_short_item`: today's store, wall clock, no prior-open
    set (the one-open-trade rule runs after dedup, in `_build_alerts`)."""
    return qualify.QualifyContext(
        frames=frames, spy=lane["spy"], sector_of=lane["sector_of"],
        etf_symbol_of=lane["etf_symbol_of"], sector_frames=lane["sector_frames"],
        regime=lane["regime"], regimes=lane["regimes"],
        confirmations=state if require_confirmation else None,
        required_confirmations=config.SIGNAL_CONFIRMATION_SCANS)


def _qualified_items(items, require_confirmation, frames, lane) -> list:
    """Confirmation, sector RS, RS gate and plan build -- the base merge, serial."""
    context = _qualify_context(require_confirmation, frames, lane)
    kept = []
    for item in items:
        verdict = qualify.qualify_short_item(item.candidate_context, item, context)
        qualify.record_verdict(lane.get("funnel"), verdict)
        if isinstance(verdict, qualify.Accepted):
            kept.append(item)
    return kept


# --- alerts -----------------------------------------------------------------------

def _fit_trendline(df, plan, h, trend):
    if df is None:
        return None
    try:
        return fit_trendline(df, lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                             current_price=plan.entry, is_bull=trend == "bullish")
    except Exception:
        log.warning("Trendline fit failed for %s", plan, exc_info=True)
        return None


def _log_trade(item, nums, explanation, fit, alerts):
    """Persist the plan, then the paper trade (v116 order); returns the trade id."""
    result, plan, conf = item.result, item.plan, item.conf
    plan_v2 = item.plan_v2 if config.PLAN_ENGINE_V2 == "on" and item.plan_v2 is not None else None
    sources, rr = scan_run._logged_plan_fields(plan_v2, plan, item.level_map, result.trend)
    if plan_v2 is not None:
        scan_run._persist_plan_v2(plan_v2, alerts)
    return trade_log.log_trade(
        ticker=result.ticker, strategy=result.strategy, horizon_key=result.horizon_key,
        direction=result.trend, confidence_level=conf.level, confidence_label=conf.label,
        entry=nums["entry"], stop_loss=nums["stop_loss"], take_profit=nums["take_profit"],
        target2=nums["target2"], confidence_score=conf.score, confidence_breakdown=conf.breakdown,
        target_sources=sources, stop_sources=list(dict.fromkeys(plan.stop_sources)),
        target2_sources=list(dict.fromkeys(plan.target2_sources)) if plan.target2_sources else [],
        risk_reward_ratio=rr, explanation=explanation, confirmed_by=item.combined_from,
        plan_id=plan_v2.plan_id if plan_v2 is not None else None,
        badge=plan_v2.badge if plan_v2 is not None else None,
        quality_score=plan_v2.quality_score if plan_v2 is not None else None,
        source=plan_v2.source if plan_v2 is not None else None, trendline_fit=fit,
        cohort_label=plan_v2.cohort_label if plan_v2 is not None else None,
        cohort_stats=plan_v2.cohort_stats if plan_v2 is not None else None,
        risk_features=plan_v2.risk_features if plan_v2 is not None else None,
        entry_context=plan_v2.entry_context if plan_v2 is not None else None)


def _render_chart(item, nums, df, frames, spy_df, trade_id, fit):
    """(chart_path, chart_filename); a failed render only costs the chart."""
    result, plan = item.result, item.plan
    filename = f"{result.ticker}_{trade_id or 'snapshot'}.png"
    if df is None:
        return None, None
    h = HORIZONS[result.horizon_key]
    try:
        if config.DECISION_CHART_ENABLED and item.plan_v2 is not None:
            ctx = analyze.build_decision_context(item, frames, spy_df)
            return render_decision_chart(result.ticker, df, item.plan_v2, ctx, config.TRADE_CHART_DIR), filename
        path = generate_trade_chart(
            result.ticker, df, nums["entry"], nums["stop_loss"], nums["take_profit"], result.trend,
            result.strategy, result.horizon_label, config.TRADE_CHART_DIR, filename=filename,
            currency_symbol=get_currency_symbol(result.ticker, config.CURRENCY_SYMBOL),
            target2=nums["target2"],
            trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
            target_sources=list(dict.fromkeys(plan.target_sources)),
            stop_sources=list(dict.fromkeys(plan.stop_sources)), horizon=h,
            market_price=plan.market_price, trendline_fit=fit)
        return path, filename
    except Exception as exc:
        log.warning("Could not generate trade chart for %s: %s", result.ticker, exc, exc_info=True)
        return None, None


def _stamp_risk_flags(item, frames, account_cfg) -> None:
    """Heat / cluster / kill-switch labels: flagged, never hidden (E7/E8/E47)."""
    balance = account_cfg.get("balance", 0.0)
    open_trades = trade_log.get_trades(status="open", limit=None)
    heat = heat_mod.heat_check(open_trades, balance, candidate_risk_pct=account_cfg.get("risk_pct", 1.0))
    if not heat["allowed"]:
        item.heat_blocked = heat
    cluster = corr_mod.cluster_check(
        corr_mod.cluster_exposure(open_trades, item.result.ticker, frames, balance),
        account_cfg.get("risk_pct", 1.0))
    if not cluster["allowed"]:
        item.cluster_blocked = cluster
    kill = throttle.kill_state()
    if kill.get("on"):
        item.kill_switch_blocked = kill


def _post_block(item, require_confirmation) -> str | None:
    """Why this item must not post: one open trade per ticker, or a failed requirement."""
    if require_confirmation and trade_log.open_trade_for_ticker(item.result.ticker) is not None:
        return "existing_trade"
    return None if item.all_requirements_met else "unmet"


def _should_post(item, require_confirmation) -> bool:
    return _post_block(item, require_confirmation) is None


def _open_positions_warning(account_cfg) -> str | None:
    """The base lane's "N paper trades already open" warning, same wording and limit."""
    open_count = trade_log.get_stats()["open"]
    max_open = account_cfg.get("max_open_positions", 5)
    if open_count >= max_open:
        return f"{open_count} paper trades already open (limit {max_open}) — consider skipping new size here."
    return None


def _stamp_intraday(item) -> None:
    """Advisory 1h-VWAP confirmation, as in the base lane; a failure renders nothing."""
    try:
        item.intraday = rs_factors.intraday_confirms(item.result.ticker, item.result.trend)
    except Exception as exc:
        log.debug("Intraday confirmation unavailable for %s: %s", item.result.ticker, exc)
        item.intraday = None


def _alert_for(item, frames, spy_df, account_cfg, alerts, funnel=None):
    result, plan, conf = item.result, item.plan, item.conf
    h = HORIZONS[result.horizon_key]
    df = frames.get(result.ticker)
    explanation = build_explanation(
        result, earnings_info=scan_run._earnings_in_window(result.ticker, h["max_holding_days"]),
        target_confluence=item.target_confluence, stop_confluence=item.stop_confluence,
        confirmed_by=item.combined_from,
        plan=item.plan_v2 if config.PLAN_ENGINE_V2 == "on" else None)
    nums = plan_numbers_for_display(getattr(item, "plan_v2", None), {
        "entry": plan.entry, "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit, "target2": plan.target2_price})
    already_open = trade_log.open_trade_for_ticker(result.ticker) is not None
    item.paper_logged, item.not_logged_reason = analyze.paper_trade_decision(item, already_open)
    if funnel is not None:
        funnel.record_decision(item)
    fit = _fit_trendline(df, plan, h, result.trend) if item.paper_logged else None
    trade_id = _log_trade(item, nums, explanation, fit, alerts) if item.paper_logged else None
    chart_path, chart_filename = _render_chart(item, nums, df, frames, spy_df, trade_id, fit)
    _stamp_risk_flags(item, frames, account_cfg)
    warning = _open_positions_warning(account_cfg)
    _stamp_intraday(item)
    embed = build_embed(item, explanation, trade_log.get_stats(conf.level),
                        warning, chart_filename, htf_info=item.htf_info, layout=config.ALERT_EMBED_LAYOUT)
    alerts.append((embed, chart_path, item.plan_v2, build_simple_alert(item)))
    if funnel is not None:
        funnel.record_item(item, "send")
    notify_secondary(item, plan, conf)


def _build_alerts(deduped, require_confirmation, frames, spy_df, funnel=None) -> list:
    account_cfg = load_account_config()
    alerts: list = []
    for item in deduped:
        if runstate.is_stop_requested():
            log.info("SHORT alert building: stop requested -- %d/%d built", len(alerts), len(deduped))
            break
        blocked = _post_block(item, require_confirmation)
        if blocked is None:
            _alert_for(item, frames, spy_df, account_cfg, alerts, funnel)
        elif funnel is not None and blocked == "existing_trade":   # unmet is already a scenario_events rejection
            funnel.record_item(item, "trade_decision", blocked)
    return alerts


# --- the pass ---------------------------------------------------------------------

def _lane_inputs(base_tickers, now, funnel=None):
    """(candidates, reference, extra_frames, snapshot) for today's session."""
    day = session_date(now)
    snapshot = universe.short_snapshot(day, live=True)
    extra_frames = _crawl_extra(snapshot, base_tickers, funnel)
    base_frames = fetch._crawl_latest_data(list(base_tickers), None)   # cache-first: warm after the base scan
    spy_df = _spy_frame(base_frames)
    reference = None if spy_df is None or snapshot is None else scan_run._short_reference(
        day, snapshot, extra_frames, base_frames, spy_df, now)
    rejected: list = []
    candidates = scan_run.build_extra_candidates(
        base_tickers, decision_date=day, snapshot=snapshot, reference=reference, rejected=rejected)
    for symbol, reason in rejected:
        _note(funnel, short_funnel.BEARISH, "candidate", reason, symbol=symbol)
    if reference is None:
        _note(funnel, short_funnel.BEARISH, "candidate", "no_snapshot" if snapshot is None else "no_reference")
    return candidates, reference, extra_frames, snapshot


def _lane_state(reference, snapshot, regime) -> dict:
    regimes = None
    try:
        regimes = regime2.regime_series(reference.spy)
    except Exception:
        log.debug("regime_series computation failed", exc_info=True)
    return {"sector_of": snapshot.sector_of, "etf_symbol_of": fetch._etf_symbol_of_sector(),
            "sector_frames": dict(reference.sector_frames), "spy": reference.spy,
            "regime": regime, "regimes": regimes}


def _analyze_candidates(candidates, frames, ctx, progress) -> list:
    horizons = [hk for hk in LEGACY_HORIZONS]
    items: list = []
    for done, candidate in enumerate(candidates, 1):
        if runstate.is_stop_requested():
            break
        items.extend(analyze.scan_extra_candidate(candidate, frames.get(candidate.ticker), ctx, horizons))
        if progress is not None:
            progress.done, progress.current_ticker = done, candidate.ticker
    return items


def _log_funnel(funnel: ShortFunnel, alerts: int) -> None:
    """One telemetry row keyed direction/source/mode/stage/reason; never blocks the lane."""
    try:
        telemetry.log_scan_telemetry({"type": "short_funnel", "alerts": alerts,
                                      "short_funnel": funnel.snapshot()})
    except Exception:
        log.exception("SHORT funnel telemetry failed -- not blocking the lane")


def _sync_run_short_scan(require_confirmation: bool, progress=None) -> tuple:
    """(alerts, newly_closed, near_close_warnings) for the extra lane."""
    base_tickers = tuple(scan_run._scan_tickers())
    funnel = ShortFunnel()
    candidates, reference, extra_frames, snapshot = _lane_inputs(
        base_tickers, scan_run._short_now(), funnel)
    params = ScanParams.from_config()
    if progress is not None:
        progress.stage, progress.total, progress.done = "short universe", len(candidates), 0
    if reference is None:
        ctx = analyze.ExtraScanContext(None, 1, 1, None, None, {}, None, None)
        _monitor_stranded(base_tickers, set(), extra_frames, {}, ctx, funnel)
        _log_funnel(funnel, 0)
        return [], ctx.newly_closed, ctx.near_close
    regime = scan_run.get_regime(reference.spy)
    frames = _stamp_context(extra_frames, reference.spy)
    symbols = sorted({c.ticker for c in candidates} | set(_open_extra_tickers(base_tickers)))
    live_prices = fetch._fetch_live_prices(symbols, None) if symbols else {}
    ctx = _scan_context(reference, params, live_prices, regime)
    _monitor_stranded(base_tickers, {c.ticker for c in candidates}, extra_frames, live_prices, ctx, funnel)
    items = _analyze_candidates(candidates, frames, ctx, progress)
    funnel.merge(ctx.funnel_events)
    lane = {**_lane_state(reference, snapshot, regime), "funnel": funnel}
    qualified = _qualified_items(items, require_confirmation, frames, lane)
    deduped = dedup.dedup_scan_items(qualified)
    funnel.record_dedup(qualified, deduped)
    deduped.sort(key=lambda item: (item.all_requirements_met, item.conf.score), reverse=True)
    alerts = _build_alerts(deduped, require_confirmation, frames, reference.spy, funnel)
    _log_funnel(funnel, len(alerts))
    log.info("SHORT extra lane: %d candidate(s), %d scenario(s), %d alert(s)",
             len(candidates), len(items), len(alerts))
    return alerts, ctx.newly_closed, ctx.near_close


async def run_short_universe_scan(require_confirmation: bool = True, bot=None, progress=None) -> list:
    """The extra lane's scan; call it only after the base alerts were sent.

    Returns the lane's alert tuples ([] when the flag is off or the lane failed
    -- a failure here is logged and never reaches the base scan, but a store
    write halt still propagates exactly as it does for the base scan).
    """
    if not config.SHORT_UNIVERSE_ENABLED:
        return []
    with scan_context(new_scan_id()):
        async with scan_run._scan_lock:
            runstate._mark_running(True)
            try:
                alerts, closed, near = await asyncio.to_thread(
                    _sync_run_short_scan, require_confirmation, progress)
            except write_failure.StoreWriteHalt:
                raise
            except Exception:
                log.warning("SHORT extra lane failed -- base scan unaffected", exc_info=True)
                return []
            finally:
                runstate._mark_running(False)
    if bot is not None:
        if closed:
            await notify_closed_trades(bot, closed)
        if near:
            await notify_near_close(bot, near)
    return alerts
