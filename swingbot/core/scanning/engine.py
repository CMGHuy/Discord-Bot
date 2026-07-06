"""
Core scanning engine -- shared by the automatic session scan and the
manual !check command. Not Discord-command code itself; bot_core.py and
the cmd_*.py modules call into this.

Every scan runs in two clearly separated phases, in order:
  1. CRAWL -- fetch the latest daily OHLCV data for every watchlist
     ticker, one at a time (see _crawl_latest_data()), before any
     analysis touches a single price. This guarantees every scenario a
     scan produces was built from data fetched at the START of that
     scan, not a stale earlier fetch. Deliberately sequential, not a
     thread pool, even though each fetch is network-bound and would
     otherwise be a good concurrency candidate -- see
     _crawl_latest_data()'s own docstring for why: the pinned yfinance
     version isn't safe to call from multiple threads at once.
  2. ANALYZE -- levels, scenarios, confidence scoring, chart
     generation, dedup -- entirely from what the crawl phase already
     fetched. Nothing in this phase ever fetches anything itself.

Two scan modes:
  - require_confirmation=True (automatic background scan): a scenario
    only alerts once its target has been the same for
    SIGNAL_CONFIRMATION_SCANS consecutive scans, to filter intraday
    flicker.
  - require_confirmation=False (manual !check): a snapshot of every
    currently-qualifying scenario right now -- no debounce delay, since
    this is an on-demand look, not something that could spam a channel
    repeatedly.

Both modes:
  - only surface scenarios at or above MIN_ALERT_CONFIDENCE_LEVEL
  - only surface scenarios whose target sits at least MIN_REWARD_PCT
    away from TODAY'S CURRENT PRICE, in either direction (see levels.py)
  - deduplicate near-identical scenarios on the same ticker/direction
    into one combined alert
  - never log more than one open trade for the same exact
    ticker+horizon+direction combo at a time

This bot trades the underlying STOCK/ETF directly (LONG for bullish,
SHORT for bearish) -- no options are involved. There is no euro-based
position sizing: the focus is entirely on finding a real, multi-method-
confirmed support/resistance setup (see levels.py) with a genuine
MIN_REWARD_PCT+ move available, not on how much money to put behind it.
"""
import asyncio
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core import levels
from swingbot.core.account import compute_unrealized_pnl, load_account_config
from .confidence import ConfidenceResult, score_confidence
from swingbot.core.data import get_currency_symbol, get_current_price, get_daily_data
from swingbot.core.events import earnings_within_window
from swingbot.core.explain import build_explanation
from swingbot.core.market_events import get_market_events
from swingbot.core.notifier import notify_secondary
from swingbot.core.performance import TradeLog
from .regime import get_htf_bias, get_market_regime
from swingbot.core.state import StateStore
from swingbot.core.strategy import HORIZONS, MIN_BARS
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.watchlist import load_watchlist
from .embeds import (
    CONFIDENCE_COLORS, CONFIDENCE_EMOJI, CONFIDENCE_ANSI,
    confidence_color, _build_requirement_checks, build_embed,
    regenerate_chart_for_trade, build_closed_trade_embed, notify_closed_trades,
    build_near_close_embed, notify_near_close,
)

log = logging.getLogger("swing-bot.scan_engine")

state = StateStore()
trade_log = TradeLog()

# Ensures only one scan (automatic or !check) runs its heavy work at a time --
# without this, an automatic scan and a manual !check could both write to
# trades.json/state.json from different threads simultaneously.
_scan_lock = asyncio.Lock()

# Cooperative stop/running signaling for the currently in-progress scan.
# File-based (same pattern as commands/scanning.py's pause flag and the
# admin UI's scan-trigger flag) rather than an in-memory flag, because the
# admin UI (Flask) and the bot are separate processes sharing only the
# data/ directory on disk -- an in-memory Event in this process would be
# invisible to the admin UI's "Stop scan" button. Checked cooperatively
# (once per ticker) inside the crawl/analyze/alert-building loops below;
# there's no way to forcibly kill a Python thread mid-fetch, so a scan
# stops at the next checkpoint, not instantly.
_STOP_FILE = os.path.join(config.DATA_DIR, "stop_scan.flag")
_RUNNING_FILE = os.path.join(config.DATA_DIR, "scan_running.flag")


def is_stop_requested() -> bool:
    return os.path.exists(_STOP_FILE)


def request_stop() -> None:
    """Ask whatever scan is currently running to stop at its next checkpoint."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(_STOP_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def _clear_stop() -> None:
    try:
        os.remove(_STOP_FILE)
    except OSError:
        pass  # already clear


def is_scan_running() -> bool:
    """Whether a scan (manual !check/`/check`, admin-UI-triggered, or the
    automatic session scan) is currently executing. Used by the admin UI
    to enable/disable its "Stop scan" button."""
    return os.path.exists(_RUNNING_FILE)


def _mark_running(running: bool) -> None:
    if running:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_RUNNING_FILE, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    else:
        try:
            os.remove(_RUNNING_FILE)
        except OSError:
            pass  # already clear


@dataclass
class ScanItem:
    result: object
    plan: object
    conf: object
    requirements: list = field(default_factory=list)
    target_confluence: tuple = None   # (count, family_names) from levels.count_confirming_strategies
    stop_confluence: tuple = None
    combined_from: list = field(default_factory=list)
    htf_info: dict = None             # from get_htf_bias() -- None when HTF check is off or inconclusive

    @property
    def all_requirements_met(self) -> bool:
        """True if every requirement was checked and passed. True (not False) when there's nothing to check,
        so older/lightweight ScanItems built without requirements don't get treated as failing by default."""
        return all(r.passed for r in self.requirements) if self.requirements else True


class ScanProgress:
    """
    Thread-safe-enough (simple attribute writes under the GIL) progress
    tracker shared between the background scan thread and the async
    Discord layer, so commands like `!check` can show a live % complete
    -- and what's actually happening -- instead of going silent or
    sitting on one static message until the whole scan finishes.
    """
    def __init__(self):
        self.total = 0
        self.done = 0
        self.current_ticker = None
        self.stage = "starting"
        self.qualifying_found = 0     # scenarios that passed every filter so far, pre-dedup
        self.alerts_total = 0          # set once dedup is known, for the "building alerts" phase
        self.alerts_done = 0
        self.funnel = None             # filled in at the very end with the full funnel summary dict
        self.stopped = False           # True if a stop request cut this scan short (see request_stop())

    @property
    def pct(self) -> int:
        return round(self.done / self.total * 100) if self.total else 0


def get_regime():
    ticker = config.MARKET_REGIME_TICKER
    try:
        regime_df = get_daily_data(ticker)
        return get_market_regime(regime_df, ticker)
    except Exception as e:
        log.warning("Could not fetch market regime: %s", e)
        return None


def _plans_similar(plan_a, plan_b, tol_pct: float = config.DEDUP_TOLERANCE_PCT) -> bool:
    def close(a, b):
        ref = max(abs(a), abs(b))
        if ref == 0:
            return True
        return abs(a - b) / ref * 100 <= tol_pct

    return close(plan_a.entry, plan_b.entry) and close(plan_a.take_profit, plan_b.take_profit) and close(plan_a.stop_loss, plan_b.stop_loss)


def dedup_scan_items(items: list) -> list:
    groups = defaultdict(list)
    for item in items:
        groups[(item.result.ticker, item.result.trend)].append(item)

    deduped = []
    for _, group_items in groups.items():
        clusters = []
        for item in group_items:
            placed = False
            for cluster in clusters:
                if _plans_similar(cluster[0].plan, item.plan):
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])

        for cluster in clusters:
            cluster.sort(key=lambda it: it.conf.score, reverse=True)
            rep = cluster[0]
            rep.combined_from = [
                {"strategy": it.result.strategy, "horizon_key": it.result.horizon_key, "level": it.conf.level}
                for it in cluster
            ]
            deduped.append(rep)

    return deduped


def _check_near_close(ticker: str, df) -> list:
    """
    For every open trade on this ticker, checks how close today's price is
    to the stop-loss or take-profit. Returns a list of warning dicts for
    trades that just crossed into the near-close zone (alerts once per
    approach -- the flag resets if price moves back away, so a later
    approach can warn again).

    Gated entirely on config.NEAR_CLOSE_ALERTS_ENABLED (Settings ->
    Trade Filters & Risk) so it can be temporarily switched off without
    losing NEAR_CLOSE_THRESHOLD_PCT -- this only silences the early
    warning; SL/TP hits themselves (and the trade actually closing) go
    through update_open_trades/close_if_live_price_hit and are completely
    unaffected either way.
    """
    if not config.NEAR_CLOSE_ALERTS_ENABLED:
        return []

    warnings = []
    current_price = float(df["Close"].iloc[-1])
    open_trades = [t for t in trade_log.get_trades(status="open", limit=200) if t["ticker"] == ticker]

    for t in open_trades:
        if current_price <= 0:
            continue
        sl_dist_pct = abs(current_price - t["stop_loss"]) / current_price * 100
        tp_dist_pct = abs(t["take_profit"] - current_price) / current_price * 100
        near = sl_dist_pct <= config.NEAR_CLOSE_THRESHOLD_PCT or tp_dist_pct <= config.NEAR_CLOSE_THRESHOLD_PCT
        already_alerted = t.get("near_close_alerted", False)

        if near and not already_alerted:
            trade_log.mark_near_close(t["id"], True)
            near_which = "stop-loss" if sl_dist_pct <= tp_dist_pct else "take-profit"
            warnings.append({
                "trade": t, "current_price": current_price,
                "sl_dist_pct": sl_dist_pct, "tp_dist_pct": tp_dist_pct, "near_which": near_which,
            })
        elif not near and already_alerted:
            trade_log.mark_near_close(t["id"], False)

    return warnings


def _crawl_latest_data(tickers: list, progress: "ScanProgress" = None) -> dict:
    """
    Phase 1 of every scan: fetches the latest daily OHLCV data for every
    ticker in `tickers` BEFORE any analysis runs. This is the only place
    a scan fetches price data from -- build_level_map(), build_scenarios(),
    confidence scoring, etc. downstream never fetch anything themselves,
    they only ever see what this function already pulled fresh.

    Fetched ONE TICKER AT A TIME, sequentially -- deliberately NOT a
    concurrent thread pool anymore. This used to run through a bounded
    ThreadPoolExecutor for speed, but yfinance's `download()` (which
    get_daily_data() calls) is built on a shared module-level global
    (`_DFS`) that earlier yfinance releases -- including 0.2.66, the
    version this project is pinned to -- write to non-reentrantly; the
    upstream fix ("Make yf.download() reentrant by removing shared
    module globals", yfinance changelog 1.4.0) only landed in the 1.x
    line, a major-version jump this project deliberately hasn't taken
    (see requirements.txt's pinning rationale). Calling it from several
    threads at once let two different tickers' downloads clobber each
    other's data mid-flight: two real watchlist tickers scanned 2 seconds
    apart in the same concurrent batch were once logged as open trades
    with byte-identical entry/stop/target/confidence values -- one
    ticker's real price data got attributed to the other. Sequential
    fetching is slower for a large watchlist, but for a paper-trading
    bot that posts real alerts and logs real trade records, correctness
    beats speed here -- this can be revisited if/when yfinance is
    upgraded past 1.4.0 and re-verified thread-safe.

    Returns {ticker: DataFrame} for tickers that fetched successfully.
    A ticker whose fetch failed is simply absent from the result (the
    caller logs and skips it downstream) -- one bad ticker never aborts
    the crawl for the rest of the watchlist.

    Checks is_stop_requested() once per ticker and ends the crawl early
    (returning whatever was fetched so far) if a stop was requested --
    see the module-level _STOP_FILE docstring above for why this is
    file-based and only checked at per-ticker checkpoints, not instant.
    """
    if progress is not None:
        progress.stage = "crawling data"
        progress.total = len(tickers)
        progress.done = 0
        progress.current_ticker = None

    results = {}
    started = time.monotonic()

    for ticker in tickers:
        if is_stop_requested():
            log.info("Crawl: stop requested -- ending early (%d/%d ticker(s) fetched so far)",
                      len(results), len(tickers))
            if progress is not None:
                progress.stopped = True
            break
        try:
            df = get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
        except Exception as e:
            log.error("Crawl: error fetching data for %s: %s", ticker, e)
            df = None
        if df is not None:
            results[ticker] = df
        if progress is not None:
            progress.done += 1
            progress.current_ticker = ticker

    elapsed = time.monotonic() - started
    log.info("Crawl complete in %.1fs: %d/%d ticker(s) fetched successfully", elapsed, len(results), len(tickers))
    return results


def _sync_run_scan(horizon_filter: str, require_confirmation: bool, progress: "ScanProgress" = None,
                    min_confluence: int = None) -> tuple:
    """
    All the heavy synchronous work -- network fetches, pandas computation,
    matplotlib chart rendering -- lives here with NO async/await, so it can
    run in a background thread via asyncio.to_thread() and never block the
    Discord event loop's heartbeat.
    Returns (alerts, newly_closed_trades) -- notification sending happens
    back in the async caller, since that's real async I/O to Discord.

    `min_confluence` overrides config.MIN_TARGET_CONFLUENCE_COUNT for this
    run only (used by `!check`'s optional argument); pass None (the
    default) to just use whatever's currently configured.
    """
    # Auto-reload config if .env was changed on disk since last load
    # (e.g. via the admin UI). This works even without Docker socket /
    # SIGHUP -- settings saved in the UI take effect on the next scan.
    changed = auto_reload_if_changed()
    if changed:
        log.info("Config auto-reloaded: %s", ", ".join(
            f"{k}={v[1]!r}" for k, v in changed.items()
        ))

    tickers = load_watchlist()
    effective_min_confluence = config.MIN_TARGET_CONFLUENCE_COUNT if min_confluence is None else min_confluence
    log.info("Scan starting: horizon_filter=%s require_confirmation=%s watchlist=%d ticker(s) min_confluence=%d",
              horizon_filter, require_confirmation, len(tickers), effective_min_confluence)

    # Phase 1: crawl -- fetch every ticker's latest data up front,
    # sequentially, before any analysis runs. See _crawl_latest_data()
    # and the module docstring for why this is a separate phase (and why
    # it's sequential, not concurrent).
    fresh_data = _crawl_latest_data(tickers, progress)

    if progress is not None:
        progress.stage = "analyzing"
        progress.total = len(tickers)
        progress.done = 0
        progress.current_ticker = None

    regime = get_regime()
    if regime:
        log.info("Market regime: %s (%s vs 200EMA %+.1f%%)", regime.label, regime.ticker, regime.pct_above_ema)
    account_cfg = load_account_config()

    scan_items = []
    all_newly_closed = []
    all_near_close_warnings = []
    checked_count = 0
    no_entry_point = 0
    scenarios_found_count = 0
    fully_qualifying_count = 0
    failed_counts = {
        "min_reward": 0, "min_stop_distance": 0, "max_stop_distance": 0,
        "min_risk_reward": 0, "min_confluence": 0, "min_confidence": 0,
    }
    conf_level_counts: dict = {}   # {1..5: number of scenarios scored at that level}
    filtered_by_confirmation = 0

    for ticker in tickers:
        if is_stop_requested():
            log.info("Analyze: stop requested -- ending early (%d/%d ticker(s) reached, %d scenario(s) already found)",
                      progress.done if progress is not None else 0, len(tickers), len(scan_items))
            if progress is not None:
                progress.stopped = True
            break
        if progress is not None:
            progress.current_ticker = ticker
        df = fresh_data.get(ticker)
        if df is None:
            # Already logged by _crawl_latest_data -- this ticker's
            # fetch failed during the crawl phase, so there's nothing
            # to analyze it with. Skip, same as the old inline error
            # handling did.
            if progress is not None:
                progress.done += 1
            continue
        log.debug("Fetched %d bars for %s (close=%.2f)", len(df), ticker, float(df["Close"].iloc[-1]))

        # Fetch live price (incl. premarket/aftermarket) once per ticker and use
        # it both for SL/TP hit detection and as the current_price for new plans.
        live = get_current_price(ticker)
        current_price = live if (live and live > 0) else float(df["Close"].iloc[-1])

        newly_closed = trade_log.update_open_trades(ticker, df, live_price=current_price)
        if newly_closed:
            log.info("%s: %d open trade(s) closed this scan (%s)", ticker, len(newly_closed),
                      ", ".join(f"{t['id']}={t['status']}" for t in newly_closed))
        all_newly_closed.extend(newly_closed)

        # Check remaining open trades (that didn't just close) for near-close proximity,
        # reusing this same already-fetched df -- no extra API calls.
        near_close = _check_near_close(ticker, df)
        if near_close:
            log.info("%s: %d trade(s) newly near their stop-loss/take-profit", ticker, len(near_close))
        all_near_close_warnings.extend(near_close)

        bars_available = len(df)

        for horizon_key, h in HORIZONS.items():
            if horizon_filter != "all" and horizon_key != horizon_filter:
                continue
            if bars_available < MIN_BARS[horizon_key]:
                continue

            log.debug("%s (%s): building levels (price=%.2f, bars=%d)", ticker, horizon_key, current_price, bars_available)
            supports, resistances = levels.build_level_map(df, h, current_price)
            log.debug("%s (%s): %d support level(s), %d resistance level(s) found",
                       ticker, horizon_key, len(supports), len(resistances))
            floor_pct = levels.atr_floor_pct(df, current_price, h)
            scenarios = levels.build_scenarios(current_price, supports, resistances, config.MIN_REWARD_PCT,
                                                atr_floor=floor_pct, min_stop_distance_pct=config.MIN_STOP_DISTANCE_PCT,
                                                max_stop_distance_pct=config.MAX_STOP_LOSS_PCT,
                                                min_risk_reward=config.MIN_RISK_REWARD_RATIO)
            checked_count += 1
            if not scenarios:
                # Either no genuine support AND resistance both exist
                # (no strategy found a real entry point at all), or a
                # real entry point exists but doesn't clear one of the
                # hard requirements (min reward %, stop distance bounds,
                # min reward:risk) -- those are enforced exactly as
                # configured, no exceptions, so a scenario failing any
                # of them is never built in the first place. Either way,
                # nothing to show for this ticker/horizon right now.
                no_entry_point += 1
                log.debug("%s (%s): no qualifying entry point (either no genuine support/resistance on both "
                           "sides, or the reward/stop/risk-reward requirements weren't met)", ticker, horizon_key)

            for scenario in scenarios:
                scenarios_found_count += 1
                if scenario.tight_stop:
                    log.info("%s (%s, %s): tight stop -- %.1f%% away, below this horizon's normal ATR cushion (%.1f%%)",
                              ticker, horizon_key, scenario.direction, scenario.stop_distance_pct, scenario.atr_floor_pct)

                # Simulate EVERY supported strategy independently against
                # this ticker (see levels.count_confirming_strategies) and
                # count how many land within CONFLUENCE_DEVIATION_PCT of
                # this scenario's target/stop -- feeds BOTH the "min
                # strategies confirmed" requirement below AND confidence
                # scoring's target/stop confluence factors, so the two
                # can never disagree about what "N strategies agree" means.
                target_confluence = levels.count_confirming_strategies(
                    df, h, current_price, scenario.take_profit, tolerance_pct=config.CONFLUENCE_DEVIATION_PCT,
                )
                stop_confluence = levels.count_confirming_strategies(
                    df, h, current_price, scenario.stop_loss, tolerance_pct=config.CONFLUENCE_DEVIATION_PCT,
                )

                # Empirical win rate of previously-closed trades that
                # reached this scenario's own base level (strategy count
                # alone, before quality/expectancy adjust it further) --
                # confidence.py's expectancy factor (see confidence.py's
                # docstring, Step 4) uses this plus the scenario's own
                # reward:risk to answer "does this payoff/win-rate combo
                # actually make money", not just "does it look clean".
                base_level_preview = max(1, min(5, target_confluence[0]))
                base_level_stats = trade_log.get_stats(base_level_preview)
                track_record = (base_level_stats["win_rate"], base_level_stats["closed"])

                conf = score_confidence(scenario, regime_trend=(regime.trend if regime else None), df=df,
                                         target_confluence=target_confluence, stop_confluence=stop_confluence,
                                         track_record=track_record)

                # Multi-timeframe confluence: check this ticker's own
                # higher-timeframe EMA bias (50-day for short horizons,
                # 200-day for longer ones) using the already-fetched daily
                # df -- no extra API call. A counter-trend signal gets a
                # configurable penalty subtracted from its raw score, which
                # can drop it one level and thus below MIN_ALERT_CONFIDENCE_LEVEL.
                htf_result = get_htf_bias(df, horizon_key)
                htf_counter_trend = (
                    htf_result is not None
                    and htf_result["bias"] != scenario.direction
                )
                if htf_counter_trend and config.HTF_COUNTER_TREND_PENALTY > 0:
                    penalty = config.HTF_COUNTER_TREND_PENALTY
                    new_score = max(0, conf.score - penalty)
                    # Re-bucket the level from the adjusted score using the
                    # same 20-point band boundaries as confidence.py uses.
                    new_level = max(1, min(5, 1 + new_score // 20))
                    from .confidence import LEVELS as _CONF_LEVELS
                    new_label = next(
                        (lbl for lvl, lbl, _lo, _hi in _CONF_LEVELS if lvl == new_level),
                        conf.label,
                    )
                    conf = ConfidenceResult(
                        level=new_level, score=new_score, label=new_label,
                        breakdown={**conf.breakdown, "htf_counter_trend_penalty": -penalty},
                    )
                    log.info(
                        "%s (%s, %s): HTF counter-trend (signal=%s, %d-day EMA=%s) -- "
                        "confidence reduced by %d pts to Lv%d(%d/100)",
                        ticker, horizon_key, scenario.direction,
                        scenario.direction, htf_result["ema_period"], htf_result["bias"],
                        penalty, new_level, new_score,
                    )

                log.debug(
                    "%s %s (%s): target_confluence=%d(%s) stop_confluence=%d(%s) confidence=Lv%d(%d/100)%s",
                    ticker, scenario.direction, horizon_key,
                    target_confluence[0], ",".join(target_confluence[1][:3]),
                    stop_confluence[0], ",".join(stop_confluence[1][:3]),
                    conf.level, conf.score,
                    " [HTF counter-trend]" if htf_counter_trend else "",
                )

                conf_level_counts[conf.level] = conf_level_counts.get(conf.level, 0) + 1

                # Every requirement is checked and kept, always -- see
                # _build_requirement_checks. A scenario with a real entry
                # point never disappears here just because one number
                # falls short; it's tallied below and shown (marked) by
                # the caller instead of silently dropped.
                requirements = _build_requirement_checks(scenario, target_confluence, conf, effective_min_confluence)
                all_ok = True
                for r in requirements:
                    if not r.passed:
                        failed_counts[r.key] += 1
                        all_ok = False
                if all_ok:
                    fully_qualifying_count += 1

                result = levels.ScenarioSignal(
                    ticker=ticker, horizon_key=horizon_key, horizon_label=h["label"],
                    trend=scenario.direction, close=current_price, scenario=scenario,
                )

                if require_confirmation:
                    # Automatic background scan: still only debounce-track
                    # and (eventually) post a scenario once EVERY
                    # requirement is met, to keep the alerts channel free
                    # of noise -- `!check` (require_confirmation=False)
                    # shows every scenario with a real entry point
                    # regardless, with unmet requirements marked, so
                    # "why didn't this alert?" is always answerable there.
                    if not all_ok:
                        continue
                    confirmed = state.confirm_or_update(
                        result.state_key, result.state_value, required_confirmations=config.SIGNAL_CONFIRMATION_SCANS
                    )
                    if not confirmed:
                        filtered_by_confirmation += 1
                        log.debug("%s (%s, %s): awaiting confirmation (needs %d consecutive scans)",
                                   ticker, horizon_key, scenario.direction, config.SIGNAL_CONFIRMATION_SCANS)
                        continue

                # Build htf_info dict for the embed only when counter-trend
                # (so the embed knows to show the warning field); otherwise None.
                htf_info_for_item = None
                if htf_counter_trend and htf_result is not None:
                    htf_info_for_item = {
                        "htf_bias": htf_result["bias"],
                        "counter_trend": True,
                        "ema_period": htf_result["ema_period"],
                        "horizon_key": horizon_key,
                        "pct_above_ema": htf_result["pct_above_ema"],
                    }

                scan_items.append(ScanItem(
                    result=result, plan=scenario, conf=conf, requirements=requirements,
                    target_confluence=target_confluence, stop_confluence=stop_confluence,
                    htf_info=htf_info_for_item,
                ))
                if progress is not None:
                    progress.qualifying_found = len(scan_items)

        if progress is not None:
            progress.done += 1

    log.info(
        "Signal funnel: %d ticker/horizon combo(s) checked -> %d had no qualifying entry point (no real "
        "support/resistance, or didn't meet min reward/stop/risk-reward requirements) -> %d scenario(s) found, "
        "%d fully qualifying (min strategies confirmed failed %d, min confidence failed %d) -> "
        "%d still awaiting confirmation (automatic scan only) -> %d shown/posted",
        checked_count, no_entry_point, scenarios_found_count, fully_qualifying_count,
        failed_counts["min_confluence"], failed_counts["min_confidence"],
        filtered_by_confirmation, len(scan_items),
    )

    deduped = dedup_scan_items(scan_items)
    deduped.sort(key=lambda item: (item.all_requirements_met, item.conf.score), reverse=True)

    if progress is not None:
        progress.stage = "building alerts"
        progress.current_ticker = None
        progress.alerts_total = len(deduped)
        progress.alerts_done = 0
        progress.funnel = {
            "tickers": len(tickers),
            "checked": checked_count,
            "no_entry_point": no_entry_point,
            "scenarios_found": scenarios_found_count,
            "fully_qualifying": fully_qualifying_count,
            "failed_min_reward": failed_counts["min_reward"],
            "failed_min_stop_distance": failed_counts["min_stop_distance"],
            "failed_max_stop_distance": failed_counts["max_stop_distance"],
            "failed_min_risk_reward": failed_counts["min_risk_reward"],
            "failed_min_confluence": failed_counts["min_confluence"],
            "failed_min_confidence": failed_counts["min_confidence"],
            "awaiting_confirmation": filtered_by_confirmation,
            "shown": len(deduped),
            "min_confidence_level": config.MIN_ALERT_CONFIDENCE_LEVEL,
            "conf_level_counts": conf_level_counts,  # {1..5: count} across ALL found scenarios
        }

    alerts = []
    skipped_already_open = 0
    log.info("Scan pass: %d ticker(s) evaluated, %d scenario(s) shown, %d after dedup",
              len(tickers), len(scan_items), len(deduped))
    for item in deduped:
        if is_stop_requested():
            log.info("Alert building: stop requested -- ending early (%d/%d alert(s) built so far)",
                      len(alerts), len(deduped))
            if progress is not None:
                progress.stopped = True
            break
        result, plan, conf = item.result, item.plan, item.conf

        already_open = trade_log.has_open_trade(result.ticker, result.strategy, result.horizon_key, result.trend)
        if already_open and require_confirmation:
            # Automatic/scheduled scan: this exact setup is already being
            # tracked as an open paper trade -- don't re-fire an alert for
            # it every 5 minutes just because it's still qualifying. Only
            # genuinely new trades get posted here; `!check` (require_
            # confirmation=False) still shows it, since that's an
            # on-demand snapshot request, not a repeating alert.
            skipped_already_open += 1
            log.debug("%s (%s, %s): already has an open trade -- skipping re-alert (use !check to see current state)",
                       result.ticker, result.horizon_key, result.trend)
            continue

        df = get_daily_data(result.ticker, period=config.DEFAULT_HISTORY_PERIOD)

        log.info(
            "%s %s (%s): entry=%.2f stop=%.2f target1=%.2f (+%.1f%%)%s conf=Lv%d(%d/100) all_requirements_met=%s",
            result.ticker, result.strategy, result.horizon_key,
            plan.entry, plan.stop_loss, plan.take_profit, plan.target_distance_pct,
            f" target2={plan.target2_price:.2f}(+{plan.target2_distance_pct:.1f}%%)" if plan.target2_price else "",
            conf.level, conf.score, item.all_requirements_met,
        )

        h = HORIZONS[result.horizon_key]

        earnings_info = None
        try:
            earnings_info = earnings_within_window(result.ticker, h["max_holding_days"])
            if earnings_info:
                log.warning("%s has earnings %s (%dd away) inside this trade's holding window -- "
                             "volatility spike risk, will flag in explanation", result.ticker, *earnings_info)
            else:
                log.debug("%s: no earnings inside the %dd holding window", result.ticker, h["max_holding_days"])
        except Exception as e:
            log.debug("Earnings check failed for %s: %s", result.ticker, e)

        macro_events = get_market_events(h["max_holding_days"])
        if macro_events:
            preview = ", ".join(f"{e.name} {e.date}" for e in macro_events[:4])
            more = f" (+{len(macro_events)-4} more)" if len(macro_events) > 4 else ""
            log.info("%d macro event(s) inside %s's holding window: %s%s",
                      len(macro_events), result.ticker, preview, more)

        explanation = build_explanation(
            result, earnings_info=earnings_info,
            target_confluence=item.target_confluence, stop_confluence=item.stop_confluence,
            confirmed_by=item.combined_from,
        )

        # Only a scenario that meets EVERY requirement gets logged as a
        # paper trade -- `!check` still BUILDS and shows a full embed for
        # one that doesn't (with the failing parameter(s) marked), but it
        # was never actually a "trade this bot took", so it shouldn't
        # pollute open-trade tracking or the performance stats either.
        trade_id = None
        if item.all_requirements_met and not already_open:
            trade_id = trade_log.log_trade(
                ticker=result.ticker, strategy=result.strategy, horizon_key=result.horizon_key,
                direction=result.trend, confidence_level=conf.level, confidence_label=conf.label,
                entry=plan.entry, stop_loss=plan.stop_loss, take_profit=plan.take_profit,
                target2=plan.target2_price,
                confidence_score=conf.score, confidence_breakdown=conf.breakdown,
                target_sources=list(dict.fromkeys(plan.target_sources)),
                stop_sources=list(dict.fromkeys(plan.stop_sources)),
                target2_sources=list(dict.fromkeys(plan.target2_sources)) if plan.target2_sources else [],
                risk_reward_ratio=plan.risk_reward_ratio,
                explanation=explanation,
                confirmed_by=item.combined_from,
            )
            log.info("Logged new paper trade %s for %s", trade_id, result.ticker)
        elif already_open:
            log.info("%s (%s) already has an open trade -- not logging a duplicate", result.ticker, result.horizon_key)
        else:
            log.info("%s (%s, %s): shown but not logged as a paper trade -- doesn't yet meet every requirement",
                       result.ticker, result.horizon_key, result.trend)

        perf_stats = trade_log.get_stats(conf.level)

        open_count = trade_log.get_stats()["open"]
        max_open = account_cfg.get("max_open_positions", 5)
        warning = None
        if open_count >= max_open:
            warning = f"{open_count} paper trades already open (limit {max_open}) — consider skipping new size here."

        chart_filename = f"{result.ticker}_{trade_id or 'snapshot'}.png"
        log.debug("%s: generating trade chart (%s)", result.ticker, chart_filename)
        try:
            chart_path = generate_trade_chart(
                result.ticker, df, plan.entry, plan.stop_loss, plan.take_profit, result.trend,
                result.strategy, result.horizon_label, config.TRADE_CHART_DIR, filename=chart_filename,
                currency_symbol=get_currency_symbol(result.ticker, config.CURRENCY_SYMBOL), target2=plan.target2_price,
                trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                target_sources=list(dict.fromkeys(plan.target_sources)),
                stop_sources=list(dict.fromkeys(plan.stop_sources)),
                horizon=h,
                market_price=plan.market_price,
            )
            log.info("Chart generated for %s -> %s", result.ticker, chart_filename)
        except Exception as e:
            log.warning("Could not generate trade chart for %s: %s", result.ticker, e, exc_info=True)
            chart_path, chart_filename = None, None

        embed = build_embed(item, explanation, perf_stats, warning, chart_filename,
                            htf_info=item.htf_info)
        alerts.append((embed, chart_path))

        # Secondary alerting (email / push) -- fires only for high-confidence,
        # fully-qualifying alerts when enabled. Blocking I/O but we're already
        # in the background thread (_sync_run_scan), so it won't block Discord.
        notify_secondary(item, plan, conf)

        if progress is not None:
            progress.alerts_done += 1

    log.info("Scan pass complete: %d alert(s) built, %d skipped (already open)", len(alerts), skipped_already_open)

    return alerts, all_newly_closed, all_near_close_warnings


async def run_scan(horizon_filter: str = "all", require_confirmation: bool = True, bot=None, progress: "ScanProgress" = None,
                    min_confluence: int = None) -> list:
    """
    Thin async wrapper: runs the entire synchronous scan pipeline in a
    background thread (so it never blocks the gateway heartbeat), then
    handles the genuinely-async parts -- sending Discord notifications for
    any trades that closed, and warnings for any trades nearing their
    stop-loss or take-profit, during this scan.

    `min_confluence` is an optional per-run override (see _sync_run_scan)
    -- None means "use whatever's currently configured".

    Also owns the stop/running flags used by request_stop()/is_scan_running():
    cleared and set right after acquiring _scan_lock (i.e. once this call has
    exclusive ownership of the scan, so it can't stomp on a still-running
    previous scan's own pending stop request), and always cleared again in a
    finally block so a scan that errors out doesn't leave "running" stuck on.
    """
    started = time.monotonic()
    async with _scan_lock:
        _clear_stop()
        _mark_running(True)
        try:
            alerts, newly_closed, near_close_warnings = await asyncio.to_thread(
                _sync_run_scan, horizon_filter, require_confirmation, progress, min_confluence
            )
        finally:
            _mark_running(False)
    elapsed = time.monotonic() - started
    stopped_bit = " (stopped early by request)" if (progress is not None and progress.stopped) else ""
    log.info("Scan finished in %.1fs%s: %d alert(s), %d newly-closed trade(s), %d near-close warning(s)",
              elapsed, stopped_bit, len(alerts), len(newly_closed), len(near_close_warnings))

    if bot is not None:
        if newly_closed:
            await notify_closed_trades(bot, newly_closed)
        if near_close_warnings:
            await notify_near_close(bot, near_close_warnings)

    return alerts


def get_all_unrealized_pnl() -> list:
    open_trades = trade_log.get_trades(status="open", limit=100)
    log.info("Computing unrealized P/L for %d open trade(s)", len(open_trades))
    results = []
    price_cache = {}
    for t in open_trades:
        ticker = t["ticker"]
        if ticker not in price_cache:
            # Prefer live price (incl. premarket/aftermarket); fall back to last daily close
            live = get_current_price(ticker)
            if live and live > 0:
                price_cache[ticker] = live
            else:
                try:
                    df = get_daily_data(ticker, period="5d")
                    price_cache[ticker] = float(df["Close"].iloc[-1]) if df is not None and not df.empty else None
                except Exception as exc:
                    log.warning("get_all_unrealized_pnl: could not fetch price for %s: %s", ticker, exc)
                    price_cache[ticker] = None
        current_price = price_cache[ticker]
        if current_price is None:
            continue
        pnl = compute_unrealized_pnl(
            entry=t["entry"],
            stop_loss=t["stop_loss"],
            take_profit=t["take_profit"],
            direction=t["direction"],
            current_price=current_price,
        )
        results.append({"trade": t, "pnl": pnl})
    return results
