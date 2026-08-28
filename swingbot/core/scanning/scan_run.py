"""Scan orchestration and async notification delivery."""
import asyncio
import json as _json
import logging
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core.charts.decision_chart import render_decision_chart
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.charts.trendline_fit import fit_trendline
from swingbot.core.edge import correlation as corr_mod
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import heat as heat_mod
from swingbot.core.edge import throttle
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.infra.notifier import notify_secondary
from swingbot.core.market import market_context, opex
from swingbot.core.market.events import earnings_within_window
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.market_events import get_market_events
from swingbot.core.market.reversal import evaluate_reversal, reversals_for_ticker
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.marketdata.data import get_currency_symbol
from swingbot.core.marketdata import universe
from swingbot.core.marketdata.watchlist import load_watchlist
from swingbot.core.planning import account as account_module
from swingbot.core.planning.account import compute_unrealized_pnl, load_account_config
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog

from . import analyze, dedup, fetch, runstate, telemetry
from .embeds import (
    build_embed, build_simple_alert, notify_closed_trades, notify_near_close,
    plan_numbers_for_display,
)
from .engine import state, trade_log
from .regime import get_market_regime


log = logging.getLogger("swing-bot.scan_engine")

# Ensures only one scan (automatic or !check) runs its heavy work at a time --
# without this, an automatic scan and a manual !check could both write to
# trades.json/state.json from different threads simultaneously.
_scan_lock = asyncio.Lock()
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
        regime_df = fetch.get_daily_data(ticker)
        return get_market_regime(regime_df, ticker)
    except Exception as e:
        log.warning("Could not fetch market regime: %s", e)
        return None

def _logged_plan_fields(plan_v2, scenario, level_map, direction: str) -> tuple[list, float]:
    """Attribution and R:R for the exact prices persisted to a trade row."""
    if plan_v2 is None:
        return list(dict.fromkeys(scenario.target_sources)), scenario.risk_reward_ratio

    target_levels = []
    if level_map is not None:
        supports, resistances = level_map
        target_levels = resistances if direction == "bullish" else supports
    sources = []
    for level in target_levels:
        if math.isclose(float(level.price), float(plan_v2.tp1), rel_tol=0.0, abs_tol=1e-8):
            sources.extend(level.sources)
    if not sources:
        sources = ["V2 structural target"]
    risk = abs(float(plan_v2.trigger_price) - float(plan_v2.stop_loss))
    rr = abs(float(plan_v2.tp1) - float(plan_v2.trigger_price)) / risk if risk else 0.0
    return list(dict.fromkeys(sources)), rr


def _hard_filters_snapshot() -> dict:
    """Capture every per-ticker hard filter before worker threads start."""
    return {
        "min_reward_pct": config.MIN_REWARD_PCT,
        "max_stop_loss_pct": config.MAX_STOP_LOSS_PCT,
        "min_stop_distance_pct": config.MIN_STOP_DISTANCE_PCT,
        "min_risk_reward_ratio": config.MIN_RISK_REWARD_RATIO,
        "mtf_adjacent_gate": config.MTF_ADJACENT_GATE,
        "confluence_deviation_pct": config.CONFLUENCE_DEVIATION_PCT,
    }


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
    _scan_started = time.monotonic()   # Task E82: feeds log_scan_telemetry's duration_s

    # Auto-reload config if .env was changed on disk since last load
    # (e.g. via the admin UI). This works even without Docker socket /
    # SIGHUP -- settings saved in the UI take effect on the next scan.
    changed = auto_reload_if_changed()
    if changed:
        log.info("Config auto-reloaded: %s", ", ".join(
            f"{k}={v[1]!r}" for k, v in changed.items()
        ))

    tickers = load_watchlist()
    if config.SCAN_UNIVERSE != "watchlist":
        extra = [s for s in universe.universe_symbols(config.SCAN_UNIVERSE)
                 if s not in set(tickers)]
        tickers = tickers + extra
    # One calendar lookup per scan, passed down rather than re-derived per
    # ticker per horizon. `None` off an opex day (and whenever the feature is
    # off) leaves both thresholds exactly as configured.
    opex_tier_today = opex.current_tier()
    effective_min_confluence = config.MIN_TARGET_CONFLUENCE_COUNT if min_confluence is None else min_confluence
    effective_min_confluence = opex.effective_min_confluence(
        effective_min_confluence, opex_tier_today)
    effective_min_confidence = opex.effective_min_confidence_level(opex_tier_today)
    hard_filters = _hard_filters_snapshot()
    log.info("Scan starting: horizon_filter=%s require_confirmation=%s watchlist=%d ticker(s) min_confluence=%d",
              horizon_filter, require_confirmation, len(tickers), effective_min_confluence)

    # Phase 1: crawl -- fetch every ticker's latest data up front,
    # sequentially, before any analysis runs. See _crawl_latest_data()
    # and the module docstring for why this is a separate phase (and why
    # it's sequential, not concurrent).
    fresh_data = fetch._crawl_latest_data(tickers, progress)

    # Phase 1b: one batched live-price fetch for the whole watchlist (v55),
    # still inside the crawl phase so the ANALYZE phase below stays pure
    # dict lookups -- see _fetch_live_prices and _scan_one's use of it.
    live_prices = fetch._fetch_live_prices(tickers, progress)

    # Market breadth (Task E28): % of the just-crawled universe trading above
    # its own 50-EMA, computed once per scan from data already in hand -- no
    # extra fetch. Pure pandas math over local frames, so no try/except
    # needed (unlike the network-bound regime/RS lookups below); returns
    # None on a too-small universe and every downstream consumer treats
    # None as "no reading" already.
    breadth = rs_factors.breadth_pct_above_50ema(fresh_data)

    # Progress is tracked per (ticker, horizon) pair, not per ticker --
    # analyzing a single ticker means scoring it across up to 10 horizons
    # (2w through 9m), each running ~10 strategies' confluence counts plus
    # the full confidence quality/expectancy scoring (ADX/MACD/RSI/squeeze/
    # candlestick checks, HTF bias, track-record lookups). That's genuinely
    # slow per ticker, so counting progress.done only once per ticker left
    # the %/Discord message pinned at "0%" for however long the very FIRST
    # ticker took to finish ALL its horizons -- which could be a long,
    # visually-stuck stretch on a big watchlist. Counting each horizon as
    # its own unit makes the % actually move within a single ticker.
    horizons_to_scan = [hk for hk in HORIZONS if horizon_filter == "all" or hk == horizon_filter]
    if progress is not None:
        progress.stage = "analyzing"
        progress.total = len(tickers) * max(1, len(horizons_to_scan))
        progress.done = 0
        progress.current_ticker = None

    regime = get_regime()
    if regime:
        log.info("Market regime: %s (%s vs 200EMA %+.1f%%)", regime.label, regime.ticker, regime.pct_above_ema)

    # Relative-strength factor (Task E25): fetch the benchmark once per scan
    # (same try/except pattern as get_regime() above -- an RS failure must
    # never break the scan) and build the whole universe's relative-return
    # cache once, so every item's rs_percentile below is a cheap lookup
    # against `rs_cache["rels"].values()` instead of a per-ticker refetch.
    spy_df = None
    rs_cache = None
    try:
        spy_df = fetch._daily_frame_for(config.MARKET_REGIME_TICKER)
        if spy_df is not None:
            rs_cache = rs_factors.refresh_rs_cache(fresh_data, spy_df)
    except Exception as e:
        log.warning("Could not compute relative-strength cache: %s", e)
        spy_df = None
        rs_cache = None

    # Sector-relative RS (v34 Task 5): fetch the distinct sector ETFs this
    # watchlist touches alongside SPY -- first live activation of
    # sector_rs_percentile()/rs_score() (edge/factors.py), dormant with
    # zero callers since E26. Same try/except-must-never-break-the-scan
    # pattern as the RS cache just above; a fetch failure leaves
    # sector_etf_frames empty, which _apply_sector_rs below treats as
    # "unavailable this scan" and falls back to the ticker-only RS.
    sector_of_ticker: dict = {}
    etf_symbol_of_sector: dict = {}
    sector_etf_frames: dict = {}
    try:
        etf_symbol_of_sector = fetch._etf_symbol_of_sector()
        sector_of_ticker, needed_sector_etfs = fetch._sector_etfs_for_tickers(tickers)
        if needed_sector_etfs:
            sector_etf_frames = fetch._fetch_frames(needed_sector_etfs)
    except Exception as e:
        log.warning("Could not fetch sector ETFs for relative-strength: %s", e)
        sector_of_ticker = {}
        etf_symbol_of_sector = {}
        sector_etf_frames = {}

    # Market context (P0): stamp every crawled frame with the ctx_* block so
    # entry_filters.entries_for() can read the regime straight off `df`. This
    # is the live half of the channel that leaves apply_regime_gate inert
    # otherwise -- see swingbot/core/market/market_context.py's module docstring.
    #
    # Reuses the spy_df already fetched above; adds no network call. With
    # REGIME_GATES_ENABLED off this is inert decoration, so a failure here
    # must not break a scan that wasn't going to gate anything anyway --
    # but with the flag ON, leaving frames unstamped would make every
    # entries_for() call raise MissingContextError, which is the intended
    # fail-closed behaviour and is logged loudly rather than swallowed.
    if spy_df is not None:
        stamped = 0
        for _t, _df in list(fresh_data.items()):
            if _df is None or getattr(_df, "empty", True):
                continue
            try:
                fresh_data[_t] = market_context.attach(_df, spy_df=spy_df)
                stamped += 1
            except Exception:
                log.exception("market_context.attach failed for %s", _t)
        log.info("Market context attached to %d/%d frames", stamped, len(fresh_data))
    elif getattr(config, "REGIME_GATES_ENABLED", False):
        log.error(
            "REGIME_GATES_ENABLED is on but %s could not be fetched -- no market "
            "context this scan, so every entry will be blocked (fail-closed).",
            config.MARKET_REGIME_TICKER,
        )

    account_cfg = load_account_config()

    scan_items = []
    all_newly_closed = []
    all_near_close_warnings = []
    checked_count = 0
    no_entry_point = 0
    scenarios_found_count = 0
    fully_qualifying_count = 0
    mtf_misaligned = 0   # v33 Task 4: dropped by the adjacent-horizon hard gate
    rs_blocked = 0   # v34 Task 6: dropped by the relative-strength gate
    data_quality_failed_count = 0   # E47: feeds check_kill_triggers' data_fail_frac
    failed_counts = {
        "min_reward": 0, "min_stop_distance": 0, "max_stop_distance": 0,
        "min_risk_reward": 0, "min_confluence": 0, "min_confidence": 0, "opex_close_window": 0,
    }
    conf_level_counts: dict = {}   # {1..5: number of scenarios scored at that level}
    filtered_by_confirmation = 0
    filtered_by_rr = 0  # v31 Task 6: no level cleared MIN_RISK_REWARD_RATIO (plan_v2_rejected)

    # ANALYZE phase (Task E20): the per-ticker candidate-building work
    # (_scan_one) runs in a bounded thread pool via map_tickers() -- it's
    # pandas/numpy-heavy and releases the GIL in C, so real tickers see
    # real speedup. Two things stay strictly serial, in the main thread,
    # AFTER the join below, on purpose:
    #   1. state.confirm_or_update() -- the debounce counter's scan-to-
    #      scan transitions need a fixed, thread-scheduling-independent
    #      order (see _scan_one's own docstring for the full rationale;
    #      StateStore's lock makes this safe from corruption but not
    #      deterministic).
    #   2. the funnel counters (checked_count, no_entry_point, ...,
    #      conf_level_counts, failed_counts) -- bare ints/dicts with no
    #      lock, so concurrent in-place mutation from worker threads would
    #      be a real race; _scan_one returns its own per-ticker stats
    #      instead, summed here.
    #   3. attach_plan_v2() itself -- deferred here too (Task E20 fix), for
    #      the same reason it must happen only once confirmation is known:
    #      calling it inside _scan_one built a full v2 plan (sizing, badge
    #      stamping, quality scoring) for every all_ok scenario on every
    #      scan pass, even ones still debouncing under require_confirmation.
    #      _scan_one only stages the level map (item.level_map); the actual
    #      attach_plan_v2 call lives in the merge loop below, gated on the
    #      same all_requirements_met check that decides whether an item
    #      reaches scan_items.append(item) -- do not move it back into
    #      _scan_one.
    # _scan_one always builds and returns every scenario it finds,
    # qualifying or not -- the require_confirmation gate below is applied
    # uniformly to the aggregated candidates, not decided per-ticker.
    per_ticker_results = fetch.map_tickers(
        lambda t: analyze._scan_one(t, fresh_data.get(t), horizons_to_scan, progress, regime, effective_min_confluence,
                            effective_min_confidence,
                            rs_cache=rs_cache, spy_df=spy_df, breadth=breadth, live_prices=live_prices,
                            hard_filters=hard_filters, opex_tier_today=opex_tier_today),
        tickers,
    )

    for per_ticker in per_ticker_results:
        if per_ticker is None:
            # map_tickers()'s own error-isolation contract: an exception
            # inside _scan_one for this ticker was already logged there
            # (log.exception, inside map_tickers' safe() wrapper) --
            # treat it exactly like "this ticker contributed nothing",
            # never let one bad ticker's None slot crash the merge.
            continue

        all_newly_closed.extend(per_ticker["newly_closed"])
        all_near_close_warnings.extend(per_ticker["near_close_warnings"])
        checked_count += per_ticker["checked"]
        no_entry_point += per_ticker["no_entry_point"]
        scenarios_found_count += per_ticker["scenarios_found"]
        fully_qualifying_count += per_ticker["fully_qualifying"]
        mtf_misaligned += per_ticker["mtf_misaligned"]
        if per_ticker.get("data_quality_failed"):
            data_quality_failed_count += 1
        for key, count in per_ticker["failed_counts"].items():
            failed_counts[key] += count
        for level, count in per_ticker["conf_level_counts"].items():
            conf_level_counts[level] = conf_level_counts.get(level, 0) + count

        for item in per_ticker["items"]:
            if require_confirmation:
                # Automatic background scan: only debounce-track (and
                # eventually post) a scenario once EVERY requirement is
                # met -- `!check` (require_confirmation=False) also only
                # POSTS fully-qualifying scenarios (see the alert-
                # building loop below), it just skips the confirmation
                # debounce below since it's a one-off on-demand look,
                # not a repeating alert. A scenario that isn't all_ok
                # never reaches state.confirm_or_update at all -- same as
                # the old inline loop, which never even built it.
                if not item.all_requirements_met:
                    continue
                confirmed = state.confirm_or_update(
                    item.result.state_key, item.result.state_value,
                    required_confirmations=config.SIGNAL_CONFIRMATION_SCANS,
                )
                if not confirmed:
                    filtered_by_confirmation += 1
                    log.debug("%s (%s, %s): awaiting confirmation (needs %d consecutive scans)",
                               item.result.ticker, item.result.horizon_key, item.result.trend,
                               config.SIGNAL_CONFIRMATION_SCANS)
                    continue
            # item.rs_percentile is already set (Task E37 wiring fix requires
            # it be available before attach_plan_v2 below, for quality
            # scoring) -- _scan_one computed it once per ticker (rs_pctile,
            # the same rs_cache/spy_df, identical for every item from that
            # ticker regardless of horizon/scenario) and stamped it onto
            # every ScanItem it built, so recomputing rs_percentile() here --
            # an O(universe size) pass over rs_cache["rels"] -- for every
            # surviving item was pure redundant work (v56).
            # Sector RS (v34 Task 5): combine into item.rs_combined right
            # after rs_percentile above, same "before attach_plan_v2" timing
            # for the same reason -- so quality scoring/plan building could
            # see it if a later task wires it in. Never blocks: an unknown
            # sector or missing ETF frame falls back to rs_percentile alone.
            analyze._apply_sector_rs(item, item.result.ticker, sector_of_ticker,
                             etf_symbol_of_sector, sector_etf_frames, spy_df)
            item.breadth = breadth  # Task E28: one scan-wide reading, same for every item

            # Relative-strength gate (v34 Task 6): drop this scenario before
            # confidence scoring (attach_plan_v2 below) if the ticker isn't a
            # relative laggard for a bearish setup, using item.rs_combined
            # (the 70% ticker / 30% sector blend from _apply_sector_rs just
            # above) -- NOT the bare ticker-only rs_percentile. In practice
            # only bearish setups are gated: RS_LEADER_PERCENTILE ships at 0
            # and a percentile is never negative, so rs_verdict()'s bullish
            # branch always passes (v34 Task 7 measured a bullish gate
            # NEGATIVE at every threshold). rs_verdict() already returns
            # "exempt" (never "block") for RS-ineligible symbols (FX, futures,
            # indices, crypto) and when the RS benchmark itself failed to
            # compute this scan (rs_combined is None, a scan-wide SPY/RS-cache
            # failure); only a genuine "block" verdict drops the scenario here.
            # Known gap (final-review Finding 2): this rs_available signal is
            # structurally blind to the PER-TICKER case -- a ticker with too
            # little history gets rs_percentile()'s synthetic 50.0 sentinel
            # (edge/factors.py), which reaches here as an *available* reading
            # indistinguishable from a genuine median, so it's judged as one.
            # See docs/strategy/strategy-gates.md's RS gate section for the full writeup; not
            # fixed here because it's a decision-making behavior change the
            # v34 VALIDATION run never measured. Default ON (config.RS_GATE)
            # since v34 Task 8's one-shot VALIDATION PASS -- 48.50% -> 49.66%
            # win rate for a 4.07% alert-volume cut, on OVERLAPPING intervals,
            # so this is a measured small improvement and not a demonstrated
            # edge (docs/superpowers/plans/implemented/v34-train-preregistration.md).
            if config.RS_GATE:
                rs_result = rs_verdict(
                    item.result.ticker, item.result.trend,
                    item.rs_combined if item.rs_combined is not None else 50.0,
                    rs_available=item.rs_combined is not None,
                )
                if rs_result["status"] == "block":
                    log.debug("%s %s dropped by RS gate: %s", item.result.ticker,
                              item.result.trend, rs_result["reason"])
                    rs_blocked += 1
                    continue

            if item.all_requirements_met:
                # Deferred from _scan_one (fix for a task-review finding): only
                # build the v2 plan for a scenario that actually survives the
                # confirmation gate above, matching the pre-parallelization
                # timing exactly -- a still-debouncing scenario no longer pays
                # for plan construction on every scan pass.
                analyze.attach_plan_v2(item, item.plan, fresh_data.get(item.result.ticker),
                                item.result.ticker, item.result.horizon_key,
                                level_map=item.level_map, regime=regime,
                                rs_percentile=item.rs_percentile, breadth=item.breadth)
                if item.plan_v2 is not None:
                    item.plan_v2.regime_aligned = not (
                        item.htf_info and item.htf_info.get("counter_trend", False)
                    )
                if (config.PLAN_ENGINE_V2 == "on"
                        and getattr(item, "plan_v2_rejected", None)):
                    filtered_by_rr += 1
                    log.debug("%s (%s, %s): no level clears %.1f:1 reward:risk -- skipped",
                              item.result.ticker, item.result.horizon_key,
                              item.result.trend, config.MIN_RISK_REWARD_RATIO)
                    continue          # never reaches scan_items -> never alerts
            scan_items.append(item)

    # Kill switch (E47): computed once per scan, right here -- AFTER the
    # merge loop above (data_quality_failed_count only exists once every
    # per_ticker result has been folded in) and BEFORE the alert-building
    # loop below (never inside it; this is a scan-wide reading, not a
    # per-alert one). A firing trigger only *engages* the switch --
    # release is manual-only (`!killswitch off`), see throttle.py's
    # module docstring for why.
    data_fail_frac = data_quality_failed_count / len(tickers) if tickers else 0.0
    spy_move_pct = 0.0
    if spy_df is not None and len(spy_df) >= 2:
        spy_move_pct = (float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-2]) - 1.0) * 100.0
    equity_points = [bal for _, bal in account_module.get_balance_history_points()]
    dd_pct = throttle.drawdown_pct(equity_points) if equity_points else 0.0
    kill_reason = throttle.check_kill_triggers(dd_pct, spy_move_pct, data_fail_frac)
    if kill_reason:
        throttle.set_kill(True, kill_reason)
        log.warning("Kill switch engaged: %s (dd=%.1f%% spy_move=%.1f%% data_fail=%.0f%%)",
                     kill_reason, dd_pct, spy_move_pct, data_fail_frac * 100.0)

    if progress is not None:
        # Replaces the old live "progress.qualifying_found = len(scan_items)"
        # update that used to fire after every scenario appended inside the
        # (now-parallel) per-ticker loop -- scan_items isn't assembled until
        # after the join above, so there's no equivalent mid-scan running
        # count to update from in-thread anymore. Set once, to the final
        # count, after the confirmation gate above has decided what's
        # actually in scan_items -- cosmetic (progress UI granularity)
        # only, not a correctness concern.
        progress.qualifying_found = len(scan_items)
        if progress.stopped:
            log.info("Analyze: stop requested -- scan ended early (%d ticker/horizon combo(s) "
                      "checked, %d scenario(s) found before the stop)", checked_count, len(scan_items))

    log.info(
        "Signal funnel: %d ticker/horizon combo(s) checked -> %d had no qualifying entry point (no real "
        "support/resistance, or didn't meet min reward/stop/risk-reward requirements) -> %d scenario(s) found, "
        "%d fully qualifying (min strategies confirmed failed %d, min confidence failed %d) -> "
        "%d still awaiting confirmation (automatic scan only) -> %d filtered by structural reward:risk -> "
        "%d shown/posted",
        checked_count, no_entry_point, scenarios_found_count, fully_qualifying_count,
        failed_counts["min_confluence"], failed_counts["min_confidence"],
        filtered_by_confirmation, filtered_by_rr, len(scan_items),
    )

    deduped = dedup.dedup_scan_items(scan_items)
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
            "failed_opex_close_window": failed_counts["opex_close_window"],
            "awaiting_confirmation": filtered_by_confirmation,
            "mtf_misaligned": mtf_misaligned,
            "rs_blocked": rs_blocked,
            "shown": len(deduped),
            "min_confidence_level": config.MIN_ALERT_CONFIDENCE_LEVEL,
            "conf_level_counts": conf_level_counts,  # {1..5: count} across ALL found scenarios
            "breadth": breadth,  # % of universe above its own 50-EMA at scan time (Task E28)
        }

    alerts = []
    skipped_already_open = 0
    reversed_count = 0
    log.info("Scan pass: %d ticker(s) evaluated, %d scenario(s) shown, %d after dedup",
              len(tickers), len(scan_items), len(deduped))
    for item in deduped:
        if runstate.is_stop_requested():
            log.info("Alert building: stop requested -- ending early (%d/%d alert(s) built so far)",
                      len(alerts), len(deduped))
            if progress is not None:
                progress.stopped = True
            break
        result, plan, conf = item.result, item.plan, item.conf

        # ONE open trade per ticker, full stop -- no matter the strategy,
        # horizon, entry price or direction. The old guard was scoped to a
        # matching direction plus near-identical levels, so a different
        # strategy/horizon or a far enough entry still logged a second
        # position, and an opposite-direction trade was never blocked at all
        # (one ticker could carry a long AND a short).
        existing_trade = trade_log.open_trade_for_ticker(result.ticker)
        already_open = existing_trade is not None

        # ...unless the opposite setup has taken over. Then close the old
        # trade early at the live price rather than let it ride to its stop,
        # and let the inverse through the normal opening path below. Guarded
        # by cooldown / minimum hold / confidence margin / daily cap --
        # see core/reversal.py. Automatic scans only: `!check` is an
        # on-demand snapshot and must never mutate positions.
        if already_open and require_confirmation and result.trend != existing_trade["direction"]:
            decision = evaluate_reversal(
                existing_trade, result.trend, conf.score,
                now=datetime.now(timezone.utc),
                recent_flips=reversals_for_ticker(
                    trade_log.get_trades(status=None, limit=None), result.ticker),
                enabled=config.REVERSAL_ENABLED,
                min_hold_hours=config.REVERSAL_MIN_HOLD_HOURS,
                cooldown_hours=config.REVERSAL_COOLDOWN_HOURS,
                min_conf_margin=config.REVERSAL_MIN_CONF_MARGIN,
                max_per_day=config.REVERSAL_MAX_PER_DAY,
            )
            if decision.allowed and item.all_requirements_met:
                # No df in scope this deep in the alert loop; this is the same
                # live-quote call the scan already uses for SL/TP checks. Only
                # runs when a flip is otherwise approved, so it costs one quote
                # on a genuinely rare path, not one per scanned ticker.
                live_price = fetch.get_current_price(result.ticker)
                if live_price and live_price > 0:
                    closed = trade_log.close_trade_reversed(existing_trade["id"], live_price)
                    if closed is not None:
                        reversed_count += 1
                        already_open = False
                        log.info("%s: reversed %s -> %s at %.2f (%s)",
                                 result.ticker, existing_trade["direction"],
                                 result.trend, live_price, decision.reason)
            else:
                log.debug("%s: opposite %s setup not reversing -- %s",
                          result.ticker, result.trend, decision.reason)
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

        if not item.all_requirements_met:
            # `!check`/"Run !check now" (require_confirmation=False) never
            # filtered scan_items by all_ok the way the automatic scan does
            # (see the require_confirmation branch above, in the loop that
            # builds scan_items) -- so without this check, EVERY scenario
            # with a real entry point, including ones below
            # MIN_ALERT_CONFIDENCE_LEVEL or failing any other requirement,
            # got a full embed built and POSTED to the real alerts channel
            # here, indistinguishable at a glance from a genuine qualifying
            # alert. That's the bug: a manual check could post a trade
            # "below the min confidence to alert" setting straight into the
            # shared channel. The funnel summary line built at the end of
            # this scan already reports how many scenarios were found vs.
            # fully qualifying, so "why didn't X show up" is still
            # answerable without spamming the channel with a full alert
            # for every non-qualifying scenario too.
            log.debug("%s (%s, %s): found but doesn't meet every requirement -- not posted (see funnel summary for counts)",
                       result.ticker, result.horizon_key, result.trend)
            continue

        # Reuse the frame this scan already crawled. A cache miss here is
        # advisory (it only costs the alert its chart), so a transient fetch
        # failure must not discard alerts that are otherwise ready to post.
        df = fresh_data.get(result.ticker)
        if df is None:
            try:
                df = fetch.get_daily_data(result.ticker, period=config.DEFAULT_HISTORY_PERIOD)
            except Exception as exc:
                log.warning("Could not fetch chart data for %s; posting without chart: %s",
                            result.ticker, exc)

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
            # Same cutover gate as plan_numbers_for_display/v2_priced elsewhere:
            # in "shadow" mode item.plan_v2 exists but isn't the priced plan,
            # so the wording must not describe it either.
            plan=item.plan_v2 if config.PLAN_ENGINE_V2 == "on" else None,
        )

        # By this point item.all_requirements_met is always True -- the
        # continue above already filtered out anything that doesn't meet
        # every requirement, for BOTH scan modes -- so this is really just
        # "not already_open", kept explicit as a safety net in case that
        # invariant ever changes upstream.
        # The cutover funnel (Task 89): every consumer below -- trade log,
        # chart, embed table -- shows the same numbers, legacy or v2,
        # decided in exactly one place.
        nums = plan_numbers_for_display(getattr(item, "plan_v2", None), {
            "entry": plan.entry, "stop_loss": plan.stop_loss,
            "take_profit": plan.take_profit, "target2": plan.target2_price})

        trade_id = None
        # Bound out here, not inside the branch below, because the chart is
        # rendered further down for EVERY alert -- including the snapshot
        # ones that log no trade. Left inside, those alerts would raise
        # NameError into the chart try/except and silently lose their PNG.
        trendline_fit = None
        if item.all_requirements_met and not already_open:
            # v2 plan pedigree (tier/badge/quality/source) rides along with
            # plan_id -- same cutover guard: only a live "on" plan is real
            # pedigree, "shadow"/"off" trades log as legacy (None) rows.
            plan_v2 = (item.plan_v2
                       if config.PLAN_ENGINE_V2 == "on" and item.plan_v2 is not None
                       else None)
            logged_target_sources, logged_rr = _logged_plan_fields(
                plan_v2, plan, item.level_map, result.trend)

            # Fit the trendline ONCE, here, against the frame the decision was
            # made on, and store it on the trade. The PNG and the chart
            # endpoint both read this; neither fits again.
            #
            # The two arguments match generate_trade_chart()'s own call
            # (trade_chart.py:268) exactly -- the horizon's fib_lookback, and
            # the ENTRY price rather than the last close. A fit taken with
            # different arguments would be a different line from the one the
            # PNG draws, which is the whole failure this consolidation exists
            # to end.
            if df is not None:
                try:
                    trendline_fit = fit_trendline(
                        df,
                        lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                        current_price=plan.entry,
                        is_bull=result.trend == "bullish",
                    )
                except Exception:
                    log.warning("Trendline fit failed for %s (%s) -- trade stores no fit",
                                result.ticker, result.horizon_key, exc_info=True)

            trade_id = trade_log.log_trade(
                ticker=result.ticker, strategy=result.strategy, horizon_key=result.horizon_key,
                direction=result.trend, confidence_level=conf.level, confidence_label=conf.label,
                entry=nums["entry"], stop_loss=nums["stop_loss"], take_profit=nums["take_profit"],
                target2=nums["target2"],
                confidence_score=conf.score, confidence_breakdown=conf.breakdown,
                target_sources=logged_target_sources,
                stop_sources=list(dict.fromkeys(plan.stop_sources)),
                target2_sources=list(dict.fromkeys(plan.target2_sources)) if plan.target2_sources else [],
                risk_reward_ratio=logged_rr,
                explanation=explanation,
                confirmed_by=item.combined_from,
                plan_id=plan_v2.plan_id if plan_v2 is not None else None,
                badge=plan_v2.badge if plan_v2 is not None else None,
                quality_score=plan_v2.quality_score if plan_v2 is not None else None,
                source=plan_v2.source if plan_v2 is not None else None,
                trendline_fit=trendline_fit,
            )
            log.info("Logged new paper trade %s for %s", trade_id, result.ticker)
            if plan_v2 is not None:
                # Task-review fix: attach_plan_v2() builds the plan and the
                # scanning loop uses it for the alert/chart/trade-log row above,
                # but nothing previously persisted it into PlanStore -- the one
                # store the admin Plans page and the intraday PlanManager
                # (INTRADAY_MANAGER_V2) both read from. Without this, plans.json
                # never gained an entry: the Plans page stayed at 0/0/0 forever
                # and the intraday manager's poll() had nothing to ever act on.
                try:
                    PlanStore().add(plan_v2)
                except Exception:
                    log.warning("Failed to persist plan_v2 %s to PlanStore",
                                plan_v2.plan_id, exc_info=True)
        else:
            log.info("%s (%s) already has an open trade -- not logging a duplicate", result.ticker, result.horizon_key)

        perf_stats = trade_log.get_stats(conf.level)

        open_count = trade_log.get_stats()["open"]
        max_open = account_cfg.get("max_open_positions", 5)
        warning = None
        if open_count >= max_open:
            warning = f"{open_count} paper trades already open (limit {max_open}) — consider skipping new size here."

        chart_filename = f"{result.ticker}_{trade_id or 'snapshot'}.png"
        log.debug("%s: generating trade chart (%s)", result.ticker, chart_filename)
        try:
            if df is None:
                chart_path, chart_filename = None, None
            elif config.DECISION_CHART_ENABLED and item.plan_v2 is not None:
                # One-pager decision chart (Task E67): only when a v2 plan
                # exists -- render_decision_chart reads TradePlanV2's own
                # field names (trigger_price/tp1/tp2/...), which the legacy
                # `plan` object here does not share. Flag off, or no v2
                # plan yet, leaves the legacy path below byte-for-byte
                # unchanged.
                ctx = analyze.build_decision_context(item, fresh_data, spy_df)
                chart_path = render_decision_chart(result.ticker, df, item.plan_v2, ctx,
                                                   config.TRADE_CHART_DIR)
            else:
                chart_path = generate_trade_chart(
                    result.ticker, df, nums["entry"], nums["stop_loss"], nums["take_profit"], result.trend,
                    result.strategy, result.horizon_label, config.TRADE_CHART_DIR, filename=chart_filename,
                    currency_symbol=get_currency_symbol(result.ticker, config.CURRENCY_SYMBOL), target2=nums["target2"],
                    trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                    target_sources=list(dict.fromkeys(plan.target_sources)),
                    stop_sources=list(dict.fromkeys(plan.stop_sources)),
                    horizon=h,
                    market_price=plan.market_price,
                    # The fit taken above, drawn rather than recomputed. This
                    # is the point of storing it: the PNG and the chart
                    # endpoint now read the same numbers. None here (fit
                    # failed, or no line exists) simply restores the old
                    # behaviour of fitting inline.
                    trendline_fit=trendline_fit,
                )
            log.info("Chart generated for %s -> %s", result.ticker, chart_filename)
        except Exception as e:
            log.warning("Could not generate trade chart for %s: %s", result.ticker, e, exc_info=True)
            chart_path, chart_filename = None, None

        # Portfolio heat cap (Edge plan E7): flagged, never hidden -- the
        # alert still posts, labeled, with build_embed showing suggested
        # size 0, so the operator always sees what the cap cost them.
        # open_trades re-read per item (not once per scan) so heat from
        # trades logged earlier in THIS same scan pass is accounted for.
        open_trades = trade_log.get_trades(status="open", limit=None)
        heat_chk = heat_mod.heat_check(open_trades, account_cfg.get("balance", 0.0),
                                       candidate_risk_pct=account_cfg.get("risk_pct", 1.0))
        if not heat_chk["allowed"]:
            item.heat_blocked = heat_chk

        # Correlation-aware cluster cap (Edge plan E8): same flagged-not-
        # hidden pattern as E7. `dfs` reuses `fresh_data` -- every ticker's
        # OHLCV was already crawled once at the top of this scan pass (see
        # _crawl_latest_data's docstring: analysis code never re-fetches
        # its own data) -- so this costs zero extra network calls.
        # `sectors` stays None until the universe file (E13) lands with
        # sector tags; until then this only ever uses price correlation.
        cluster_exp = corr_mod.cluster_exposure(open_trades, result.ticker, fresh_data,
                                                account_cfg.get("balance", 0.0))
        cluster_chk = corr_mod.cluster_check(cluster_exp, account_cfg.get("risk_pct", 1.0))
        if not cluster_chk["allowed"]:
            item.cluster_blocked = cluster_chk

        # Kill switch (E47): same flagged-not-hidden pattern as E7/E8 above,
        # but ENTRIES-WIDE rather than per-ticker -- re-read per item (cheap
        # file read) so a switch engaged mid-scan (right after the merge
        # loop, above) still labels every alert built afterward this pass.
        kill_st = throttle.kill_state()
        if kill_st.get("on"):
            item.kill_switch_blocked = kill_st

        # Intraday entry-timing annotation (Edge plan E29). Live-only and
        # advisory: it never gates, resizes, or reprices anything -- the
        # plan's daily stop-entry trigger is untouched. Computed here, in
        # the alert loop, so it costs one lookup per POSTED alert (a
        # handful per scan) rather than one per scanned ticker; the E19
        # cache makes repeats free for 4h. Any failure leaves it None,
        # which renders as no field at all -- an annotation must never be
        # able to take down an alert.
        try:
            item.intraday = rs_factors.intraday_confirms(result.ticker, result.trend)
        except Exception as e:
            log.debug("Intraday confirmation unavailable for %s: %s", result.ticker, e)
            item.intraday = None

        embed = build_embed(item, explanation, perf_stats, warning, chart_filename,
                            htf_info=item.htf_info, layout=config.ALERT_EMBED_LAYOUT)
        # 4th element: the stripped-down text mirror for
        # DISCORD_CHANNEL_TRADES_SIMPLE_ID. Built here, alongside the embed,
        # because this is the only frame where the full `item` (result, conf,
        # legacy plan AND plan_v2) is in scope -- the alert tuple itself only
        # carries plan_v2. Rendered unconditionally and cheaply (string
        # formatting, no chart); _send_alerts decides whether a simple channel
        # is configured to receive it.
        alerts.append((embed, chart_path, item.plan_v2, build_simple_alert(item)))

        # Secondary alerting (email / push) -- fires only for high-confidence,
        # fully-qualifying alerts when enabled. Blocking I/O but we're already
        # in the background thread (_sync_run_scan), so it won't block Discord.
        notify_secondary(item, plan, conf)

        if progress is not None:
            progress.alerts_done += 1

    log.info("Scan pass complete: %d alert(s) built, %d skipped (already open), %d reversed",
              len(alerts), skipped_already_open, reversed_count)

    # Filled in only now that the alert-building loop (which is what actually
    # computes it) has finished -- lets callers explain gaps like "2
    # qualifying -> 1 alert posted" (a dedup merge, an already-open skip, or
    # both) instead of just the pre-dedup fully_qualifying count vs. the
    # final alerts count with nothing in between. See dedup_scan_items() for
    # why 2 fully-qualifying scenarios can legitimately become 1 alert: they
    # were for the same ticker+trend with a near-identical entry/stop/target,
    # so they're the same real setup surfaced by more than one
    # strategy/horizon, not two independent trade ideas.
    if progress is not None and progress.funnel is not None:
        progress.funnel["deduped"] = len(deduped)
        progress.funnel["skipped_already_open"] = skipped_already_open
        progress.funnel["reversed"] = reversed_count

    # Scan health telemetry (Task E82): logged unconditionally, wrapped so a
    # telemetry failure (disk full, bad path, whatever) never takes down the
    # scan return it's observing. open_trades/balance re-fetched fresh here
    # rather than reusing the alert-loop's per-item `open_trades` (that
    # variable is only assigned when `deduped` is non-empty -- a quiet scan
    # with zero alerts must not NameError here).
    try:
        scan_stats = {
            "duration_s": round(time.monotonic() - _scan_started, 1),
            "tickers": len(tickers),
            "errors": len(tickers) - len(fresh_data),
            "data_skips": data_quality_failed_count,
            "signals": scenarios_found_count,
            "alerts": len(alerts),
            "open_heat": heat_mod.open_heat(TradeLog().get_trades(status="open", limit=None),
                                            account_cfg.get("balance", 0.0)),
        }
        telemetry.log_scan_telemetry(scan_stats)
        if telemetry.scan_slowdown():
            log.warning("Scan health: latest scan took %.1fs, more than 2x the median of "
                        "the prior 20 -- possible slowdown (network, cache, or universe "
                        "size growth).", scan_stats["duration_s"])
    except Exception:
        log.exception("Scan health telemetry failed -- not blocking the scan result")

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
        runstate._clear_stop()
        runstate._mark_running(True)
        try:
            alerts, newly_closed, near_close_warnings = await asyncio.to_thread(
                _sync_run_scan, horizon_filter, require_confirmation, progress, min_confluence
            )
        finally:
            runstate._mark_running(False)
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
            live = fetch.get_current_price(ticker)
            if live and live > 0:
                price_cache[ticker] = live
            else:
                try:
                    df = fetch.get_daily_data(ticker, period="5d")
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

