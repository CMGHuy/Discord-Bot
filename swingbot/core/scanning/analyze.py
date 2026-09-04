"""Pure analysis-phase helpers for scanning.

This module only reads frames fetched during the preceding crawl phase.
The named singleton import is intentional: engine owns their process-wide
identity while analysis consumes them for trade state and monitoring.
"""
import logging
import os
from dataclasses import dataclass, field

from swingbot import config
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS
from swingbot.core.edge import correlation as corr_mod
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import gates as gates_mod
from swingbot.core.edge import heat as heat_mod
from swingbot.core.edge import regime2, throttle
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.infra.jsonio import read_json
from swingbot.core.market import levels, trendlines, opex
from swingbot.core.market.mtf import adjacent_aligned, macro_aligned
from swingbot.core.market.reversal import evaluate_reversal, reversals_for_ticker
from swingbot.core.market.events import earnings_within_window
from swingbot.core.market.chart_patterns import dead_cat_bounce, params_from_config
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.strategy import HORIZONS, MIN_BARS
from swingbot.core.marketdata import universe
from swingbot.core.planning import account as account_module
from swingbot.core.planning.account import load_account_config
from swingbot.core.planning.plan_engine import build_confluence_plan, primary_strategy_for
from swingbot.core.planning.quality import atr_percentile as _atr_percentile

from . import runstate
from .confidence import score_confidence
from .embeds import _build_requirement_checks
from .regime import get_htf_bias
from .engine import state, trade_log


log = logging.getLogger("swing-bot.scan_engine")


def veto_bullish_for(df) -> bool:
    """Should bullish scenarios be blocked for this frame? (v68)

    A named function rather than an inline expression, for two reasons: the
    test above can monkeypatch the detector through it, and the short-circuit
    when the flag is off is visible in one place rather than implied.

    Never raises. A detector fault degrades to "no veto" -- the pattern check
    is an accelerator, and losing a whole ticker's scan to a malformed frame
    would be a far worse failure than missing one block.
    """
    if not getattr(config, "DEAD_CAT_BOUNCE_VETO", False):
        return False
    try:
        return bool(dead_cat_bounce(df, params_from_config())["detected"])
    except Exception:
        log.debug("dead-cat-bounce check failed; not vetoing", exc_info=True)
        return False


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
    htf_bias: str | None = None       # "bullish"/"bearish" from the same get_htf_bias() call, always stored (not just on counter-trend like htf_info) so attach_plan_v2/_build_quality_inputs can reuse it instead of recomputing
    plan_v2: object = None            # TradePlanV2 | None
    plan_v2_rejected: str | None = None  # e.g. "no_qualifying_target" (v31 Task 6) -- distinguishes a real "no trade here" from a builder exception
    level_map: tuple = None           # (supports, resistances); staged in _scan_one for attach_plan_v2, called later in _sync_run_scan once confirmation is decided (Task E20 fix)
    rs_percentile: float | None = None  # percentile (0-100) of relative return vs the scanned universe; None when the RS benchmark fetch fails (Task E25)
    sector_rs_percentile: float | None = None  # percentile (0-100) of this ticker's sector ETF vs SPY; None when the sector is unknown or its ETF frame wasn't fetched this scan (v34 Task 5)
    rs_combined: float | None = None  # rs_score(rs_percentile, sector_rs_percentile) -- 70/30 ticker/sector blend; falls back to rs_percentile alone when sector_rs_percentile is unavailable (v34 Task 5)
    breadth: float | None = None      # % of scanned universe above its own 50-EMA at scan time; None on a too-small universe (Task E28)
    intraday: bool | None = None      # 1h close vs today's VWAP on this plan's side; None = no reading = neutral, never blocks (Task E29)

    @property
    def all_requirements_met(self) -> bool:
        """True if every requirement was checked and passed. True (not False) when there's nothing to check,
        so older/lightweight ScanItems built without requirements don't get treated as failing by default."""
        return all(r.passed for r in self.requirements) if self.requirements else True


# Points-per-component ceiling for the decision chart's quality box (E66),
# read off each component_* function's own max return in quality.py --
# quality_breakdown itself only carries (name, points) pairs, no max, so
# this is derived once here rather than plumbed through score_plan's
# return type just for a display bar. "gap" is a penalty-only row (always
# <= 0) and deliberately excluded: the bar math assumes 0 <= points <= max.
_QUALITY_COMPONENT_MAX = {
    "regime": 15, "htf": 15, "confluence": 20, "volume": 10,
    "atr_percentile": 10, "trigger_distance": 10, "badge": 20,
    "rs": 10, "breadth": 5, "candle": 5,
}


def build_decision_context(item: "ScanItem", dfs: dict, spy_df) -> dict:
    """Assembles every swingbot.core.charts.decision_chart context key this
    scan pass can honestly supply. Each block is independently try/excepted
    to an absent key -- render_decision_chart's panels already degrade to a
    placeholder on a missing key, so a bad reading here must never be able
    to cost the alert itself (Task E67)."""
    ctx: dict = {}
    plan = getattr(item, "plan_v2", None) or getattr(item, "plan", None)
    ticker = getattr(getattr(item, "result", None), "ticker", None) or getattr(item, "ticker", None)
    df = dfs.get(ticker) if ticker else None

    try:
        pivots = [p for p in (plan.stop_loss, plan.trigger_price, plan.tp1) if p]
        ctx["weekly"] = {"df": rs_factors.weekly_frame(df), "pivots": pivots}
    except Exception:
        pass

    try:
        # Cap at 3 overlay lines -- v35 Task 2 added 52-week extreme anchors
        # to avwap_anchors, so an uncapped chart can now draw up to 7 lines
        # instead of the pre-v35 3 this cap originally held it to.
        #
        # avwap_anchors() returns anchors sorted ASCENDING by bar index, and
        # the 52-week extremes draw from a 252-bar window vs. 120 for swing
        # pivots -- so slicing [:3] (oldest-first) systematically favours
        # the 52-week anchors and can crowd out the volume spike and every
        # swing pivot, none of which was the intent of the original cap.
        # [-3:] keeps the most recent 3 events instead, which is the more
        # useful default for a chart meant to show current structure.
        ctx["avwaps"] = [{"series": rs_factors.anchored_vwap(df, idx),
                          "anchor_label": label}
                         for idx, label in rs_factors.avwap_anchors(df)[-3:]]
    except Exception:
        pass

    try:
        rel = (df["Close"].pct_change(rs_factors.RS_WINDOW)
               - spy_df["Close"].pct_change(rs_factors.RS_WINDOW)).dropna()
        ctx["rs"] = {"rel_series": rel, "percentile": getattr(item, "rs_percentile", None)}
    except Exception:
        pass

    try:
        ctx["regimes"] = regime2.regime_series(spy_df)
    except Exception:
        pass

    try:
        gstats = gates_mod.gap_stats(df)
        entry_px = plan.trigger_price or plan.entry_price
        stop_distance_pct = abs(entry_px - plan.stop_loss) / entry_px * 100.0
        fragile = not gates_mod.stop_beyond_gap_noise(stop_distance_pct, gstats["p90_gap_pct"])
        ctx["gap"] = {"p90_gap_pct": gstats["p90_gap_pct"], "gap_fragile": fragile}
    except Exception:
        pass

    try:
        # E39's fold-trade cache -- doesn't exist yet for any strategy as of
        # this task, so this is a real (documented) no-op until that lands,
        # not a fabricated reading. read_json's own default handles the
        # missing-file case without raising.
        fold_path = os.path.join(config.DATA_DIR, "fold_trades", f"{plan.strategy}.json")
        outcomes = read_json(fold_path, {}).get("outcomes")
        if outcomes:
            ctx["outcomes"] = outcomes
    except Exception:
        pass

    # ev_cone (E32 per-day MFE/MAE trajectory percentiles) has no producer
    # anywhere in this codebase -- E32 only ever shipped single-value
    # percentiles (mae_informed_stop_mult, mfe_informed_tp2_r), never a
    # day-by-day path distribution. Left absent rather than fabricated.

    try:
        account_cfg = load_account_config()
        balance = account_cfg.get("balance", 0.0)
        candidate_risk_pct = account_cfg.get("risk_pct", 1.0)
        open_trades = trade_log.get_trades(status="open", limit=None)
        heat_before = heat_mod.open_heat(open_trades, balance)
        cap = getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)
        sizing = account_module.compute_position_size(
            plan.trigger_price or plan.entry_price, plan.stop_loss, account_cfg)
        cluster_note = None
        if ticker:
            cluster_exp = corr_mod.cluster_exposure(open_trades, ticker, dfs, balance)
            if cluster_exp["cluster"]:
                cluster_note = (f"corr {cluster_exp['max_corr']:.2f} with "
                                f"{', '.join(cluster_exp['cluster'])}")
        ctx["sizing"] = {
            "risk_pct": sizing["risk_pct"] if sizing else candidate_risk_pct,
            "risk_source": "config",  # live sizing chain (kelly/vol_target/throttle) not yet wired to this call site
            "shares": sizing["shares"] if sizing else 0,
            "heat_before": heat_before,
            "heat_after": heat_before + candidate_risk_pct,
            "cap": cap,
            "cluster_note": cluster_note,
        }
    except Exception:
        pass

    try:
        components = [(name, pts, _QUALITY_COMPONENT_MAX[name])
                      for name, pts in getattr(plan, "quality_breakdown", [])
                      if name in _QUALITY_COMPONENT_MAX]
        ctx["quality"] = {
            "score": plan.quality_score,
            "components": components,
            "follow_score": None,   # no follow-score producer in this codebase yet
            "badge": plan.badge,
            "badge_stats": (f"N={plan.badge_stats['n']} · {plan.badge_stats['win_rate']:.1f}% OOS"
                            if getattr(plan, "badge_stats", None) else ""),
            "advisor": None,        # no advisory-annotation producer in this codebase
        }
    except Exception:
        pass

    return ctx

def _build_quality_inputs(item, scenario, df, horizon_key, *, regime=None,
                          rs_percentile=None, breadth=None) -> dict:
    """Real inputs for quality.score_plan (Task E37 wiring fix). Before this,
    attach_plan_v2 called build_confluence_plan with no quality_inputs at
    all, so _apply_quality's `if quality_inputs is None: return` made every
    live v2 plan permanently quality_score=0 -- scoring never ran, not
    "scored low". direction/badge_status are NOT included here: plan_
    engine._apply_quality supplies those itself from the plan it just built
    (plan.direction/plan.badge), so putting them in this dict too raises a
    duplicate-keyword TypeError.

    confluence_count/trigger_distance_pct are always real numbers (their
    quality.py components do `int(count)`/`<= 0.5` with no None-guard) --
    everything else degrades to None-safe component defaults on missing data.

    candle_quality and gap_fragile are deliberately left out, not
    fabricated: candle_quality needs a specific touch-bar+level the scan
    loop doesn't track per plan, and gap_fragile has no wired gate anywhere
    in this codebase yet (config.py's own comment confirms
    edge.gates.in_earnings_blackout is defined but never called). Revisit
    both as their own task rather than inventing a value here."""
    current_price = float(df["Close"].iloc[-1])
    volume_ratio = None
    if len(df) >= 20:
        avg_vol = df["Volume"].rolling(20).mean().iloc[-1]
        if avg_vol:
            volume_ratio = float(df["Volume"].iloc[-1] / avg_vol)
    target_confluence = getattr(item, "target_confluence", None)
    confluence_count = target_confluence[0] if target_confluence else 0
    return {
        "regime": regime.trend if regime else None,
        # item.htf_bias was already computed once by _scan_one's own
        # get_htf_bias(df, horizon_key) call for this exact ticker/horizon --
        # same pattern as target_confluence/confidence_level just below,
        # reused off the item instead of calling get_htf_bias a 3rd time.
        "htf_bias": getattr(item, "htf_bias", None),
        "confluence_count": confluence_count,
        "volume_ratio": volume_ratio,
        "atr_pct": _atr_percentile(df),
        "trigger_distance_pct": abs(scenario.entry - current_price) / current_price * 100,
        "rs_percentile": rs_percentile,
        "breadth": breadth,
        # v32 Task 11: rides along to _apply_quality, which pops it before
        # forwarding the rest to score_plan() -- see that function's own
        # comment. item.conf is set in _scan_one, well before attach_plan_v2
        # (and this function) run in _sync_run_scan's later merge loop.
        "confidence_level": item.conf.level if getattr(item, "conf", None) else None,
    }


def attach_plan_v2(item, scenario, df, ticker, horizon_key, level_map=None,
                    regime=None, rs_percentile=None, breadth=None):
    """Construct the v2 plan for a qualifying scan item, flag-gated.
    A v2 construction failure must NEVER break the legacy scan -- log and
    move on (shadow mode exists precisely to surface such failures safely).

    regime/rs_percentile/breadth are scan-wide/per-item readings the caller
    already has in scope (Task E37 wiring) -- see _build_quality_inputs."""
    if config.PLAN_ENGINE_V2 == "off":
        return
    try:
        quality_inputs = _build_quality_inputs(
            item, scenario, df, horizon_key, regime=regime,
            rs_percentile=rs_percentile, breadth=breadth)
        plan = build_confluence_plan(
            scenario, df, ticker=ticker, horizon_key=horizon_key,
            primary_strategy=primary_strategy_for(scenario),
            level_map=level_map, quality_inputs=quality_inputs)
        if plan is None:
            # No level beyond entry pays MIN_RISK_REWARD_RATIO against this
            # scenario's own risk. That is a real answer -- "no trade here" --
            # not a failure, so it is recorded rather than logged as a warning,
            # and _sync_run_scan drops the item instead of falling through to
            # the legacy scenario numbers (which is what plan_numbers_for_display
            # does for plan=None, and would silently re-post the very prices
            # this change exists to stop posting).
            item.plan_v2_rejected = "no_qualifying_target"
            return
        item.plan_v2 = plan
    except Exception:
        log.warning("plan_v2 construction failed for %s/%s", ticker,
                    horizon_key, exc_info=True)


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


def _apply_sector_rs(item: "ScanItem", ticker: str, sector_of_ticker: dict,
                      etf_symbol_of_sector: dict, sector_etf_frames: dict,
                      spy_df) -> None:
    """v34 Task 5: sets item.sector_rs_percentile and item.rs_combined in
    place -- the first live caller of sector_rs_percentile()/rs_score()
    (edge/factors.py, dormant with zero callers since E26/rs_score's
    introduction).

    Must never raise or block an item: an unknown/reclassified ticker (not
    in sp500.json's static sector map) or a sector whose ETF frame wasn't
    fetched this scan (network miss, or simply not in etfs.json) both fall
    back to the ticker-only rs_percentile, logged at debug level rather
    than treated as an error -- this is an expected, routine condition
    (new tickers, a bad sector-ETF fetch), not a bug.

    Task-review fix: the guard used to be `if sector and sector_etf_frames`
    -- true as soon as ANY sector ETF frame was fetched this scan, not
    necessarily THIS ticker's own sector's ETF. With 11 sequential,
    independently try/excepted network fetches, a realistic partial
    failure (most sector ETFs fetched, one missing) let a ticker in the
    failed sector fall through to sector_rs_percentile() anyway, which
    can't tell "this sector's ETF wasn't fetched" from "it was fetched and
    genuinely sits at the median" -- both return its 50.0 sentinel. That
    synthetic 50.0 would then corrupt item.rs_combined instead of falling
    back to item.rs_percentile alone. Resolving the ticker's sector to its
    specific ETF symbol first, and checking THAT symbol's presence in
    sector_etf_frames, makes the guard ticker-specific instead of
    scan-wide.

    Final-review fix (Finding 3): that guard still missed a second sentinel
    trigger inside sector_rs_percentile() itself (edge/factors.py, not
    modified here) -- it also returns the synthetic 50.0 when fewer than 2
    sector ETFs *overall* produced a computable relative-return this scan
    (`mine is None or len(rels) < 2`), even when THIS ticker's own sector
    ETF frame is present. A heavy partial fetch failure (most sector ETFs
    missing, but this ticker's happens to be one of the one or two that
    made it) used to reach sector_rs_percentile() anyway and get its 50.0
    sentinel back, corrupting rs_combined the same way. Requiring at least
    2 sector ETF frames overall closes that second path to the same bug."""
    sector = sector_of_ticker.get(ticker)
    etf_symbol = etf_symbol_of_sector.get(sector) if sector else None
    sector_pctile = None
    if sector and etf_symbol and etf_symbol in sector_etf_frames and len(sector_etf_frames) >= 2:
        sector_pctile = rs_factors.sector_rs_percentile(sector, sector_etf_frames, spy_df)
    elif sector:
        log.debug("Sector RS: this ticker's sector ETF frame wasn't fetched "
                  "this scan (or too few sector ETF frames were fetched overall) "
                  "-- %s (%s) falls back to ticker-only RS", ticker, sector)
    else:
        log.debug("Sector RS: %s has no known sector (unmapped or "
                  "reclassified ticker) -- falls back to ticker-only RS", ticker)
    item.sector_rs_percentile = sector_pctile
    item.rs_combined = (
        rs_factors.rs_score(item.rs_percentile, sector_pctile)
        if sector_pctile is not None and item.rs_percentile is not None
        else item.rs_percentile
    )


def _scan_one(ticker: str, df, horizons_to_scan: list, progress: "ScanProgress",
              regime, effective_min_confluence: int, effective_min_confidence: int,
              rs_cache: dict = None, spy_df=None, breadth: float = None,
              live_prices: dict = None, hard_filters: dict = None,
              opex_tier_today=None) -> dict:
    """
    Per-ticker analysis body of _sync_run_scan's ANALYZE phase, extracted
    so it can run inside a map_tickers() worker thread (Task E20). Handles
    everything the old inline per-ticker loop did EXCEPT the confirmation
    debounce: existing-trade monitoring (update_open_trades/
    _check_near_close), the E12 liquidity screen, the E16 data-quality
    screen, and -- if the ticker clears both screens -- the full
    per-horizon levels/scenarios/confidence/requirements/ScanItem build.
    plan_v2 construction itself is NOT part of what this function does
    (Task E20 fix): it only stages the level map on the ScanItem
    (`item.level_map`) for the caller to attach v2 plans after the
    confirmation gate, matching pre-parallelization timing.

    Deliberately never calls state.confirm_or_update(): even though
    StateStore's own lock makes that call safe to run concurrently (no
    data corruption), the debounce counter's scan-to-scan transitions need
    a fixed, predictable, serial order across tickers -- not one that
    depends on thread-scheduling. So this function always builds and
    returns EVERY scenario it finds as a ScanItem, qualifying or not --
    exactly like the require_confirmation=False (`!check`) code path used
    to do inline -- and leaves the require_confirmation gate entirely to
    the caller, applied serially after map_tickers()'s join (see
    _sync_run_scan).

    Similarly never mutates the shared funnel counters (checked_count,
    no_entry_point, etc.) or conf_level_counts/failed_counts directly --
    unlike StateStore/TradeLog those are bare ints/dicts with no lock, so
    concurrent in-place mutation from multiple worker threads would be a
    real race. Instead every count this ticker contributes is accumulated
    into the `stats` dict returned below, for the caller to sum/merge
    after the join into the exact same variables the old serial loop used
    to mutate live.

    progress.done/progress.current_ticker writes DO stay as direct
    attribute writes here (worker threads) -- ScanProgress's own docstring
    already documents plain attribute writes as GIL-safe, unlike the bare
    counter mutation above.

    Returns a dict: {"items": [ScanItem, ...], "newly_closed": [...],
    "near_close_warnings": [...], "checked": int, "no_entry_point": int,
    "scenarios_found": int, "fully_qualifying": int,
    "failed_counts": {...}, "conf_level_counts": {...}}.
    """
    hard_filters = hard_filters or {
        'min_reward_pct': config.MIN_REWARD_PCT,
        'max_stop_loss_pct': config.MAX_STOP_LOSS_PCT,
        'min_stop_distance_pct': config.MIN_STOP_DISTANCE_PCT,
        'min_risk_reward_ratio': config.MIN_RISK_REWARD_RATIO,
        'mtf_adjacent_gate': config.MTF_ADJACENT_GATE,
        'confluence_deviation_pct': config.CONFLUENCE_DEVIATION_PCT,
    }

    stats = {
        "items": [],
        "newly_closed": [],
        "near_close_warnings": [],
        "checked": 0,
        "no_entry_point": 0,
        "scenarios_found": 0,
        "fully_qualifying": 0,
        "mtf_misaligned": 0,
        "failed_counts": {
            "min_reward": 0, "min_stop_distance": 0, "max_stop_distance": 0,
            "min_risk_reward": 0, "min_confluence": 0, "min_confidence": 0, "opex_close_window": 0,
        },
        "conf_level_counts": {},   # {1..5: number of scenarios scored at that level}
        "data_quality_failed": False,   # E47: this ticker tripped the E16 data-quality gate
    }

    if runstate.is_stop_requested():
        # Cooperative, checked once per ticker just like the old serial
        # loop did -- see the module-level _STOP_FILE docstring for why
        # this is file-based and only checked at per-ticker checkpoints.
        # Under map_tickers() this only stops tickers that haven't started
        # yet (a worker already mid-flight on another ticker still
        # finishes it); see _sync_run_scan for the post-join summary log.
        if progress is not None:
            progress.stopped = True
        log.debug("Analyze: stop requested -- skipping %s", ticker)
        return stats

    if progress is not None:
        progress.current_ticker = ticker

    if df is None:
        # Already logged by _crawl_latest_data -- this ticker's fetch
        # failed during the crawl phase, so there's nothing to analyze it
        # with. Counts as every one of its horizons at once (none of them
        # can run either) so progress.total still adds up correctly
        # against horizons_to_scan-per-ticker.
        # E47 fix (task-review finding 1): a total fetch failure is the
        # worst case data_fail_frac exists to catch (a broken feed), so it
        # must feed the same flag/denominator as the E16 quality-issues
        # path below -- otherwise a mass outage where most tickers return
        # df=None never raises data_fail_frac at all.
        if progress is not None:
            progress.done += max(1, len(horizons_to_scan))
        stats["data_quality_failed"] = True
        return stats
    log.debug("Fetched %d bars for %s (close=%.2f)", len(df), ticker, float(df["Close"].iloc[-1]))

    # v55: live price (incl. premarket/aftermarket) was fetched for the whole
    # watchlist in ONE batched call back in the crawl phase (_fetch_live_prices)
    # -- this is a dict lookup, not a network call, so the "analyze phase never
    # touches yfinance" invariant this module's docstring claims is actually
    # true now, not aspirational. Used both for SL/TP hit detection and as the
    # current_price for new plans; falls back to today's daily close exactly
    # as a live-price fetch failure always has.
    live = (live_prices or {}).get(ticker)
    current_price = live if (live and live > 0) else float(df["Close"].iloc[-1])

    newly_closed = trade_log.update_open_trades(ticker, df, live_price=current_price)
    if newly_closed:
        log.info("%s: %d open trade(s) closed this scan (%s)", ticker, len(newly_closed),
                  ", ".join(f"{t['id']}={t['status']}" for t in newly_closed))
    stats["newly_closed"].extend(newly_closed)

    # Check remaining open trades (that didn't just close) for near-close proximity,
    # reusing this same already-fetched df -- no extra API calls.
    near_close = _check_near_close(ticker, df)
    if near_close:
        log.info("%s: %d trade(s) newly near their stop-loss/take-profit", ticker, len(near_close))
    stats["near_close_warnings"].extend(near_close)

    bars_available = len(df)

    # E12 liquidity screen: gates NEW-SIGNAL scanning only (level maps,
    # confluence, plan building for this ticker/scan) -- deliberately
    # placed AFTER update_open_trades/_check_near_close above, not
    # right after the df fetch. An already-open paper trade must keep
    # being monitored for its own SL/TP every scan regardless of
    # today's liquidity reading; it doesn't stop existing just because
    # dollar volume dipped today. `return` here only skips the
    # horizon loop below (levels/scenarios/confidence/plan-v2), which
    # is the only thing left in this per-ticker analysis.
    illiquid_reason = universe.liquidity_reason(df)
    if illiquid_reason is not None:
        log.info("%s: skipping new-signal scan -- %s", ticker, illiquid_reason)
        if progress is not None:
            progress.done += max(1, len(horizons_to_scan))
        return stats

    # E16 data-quality screen: same placement/rationale as the E12
    # liquidity check just above -- gates new-signal scanning only, on
    # the same already-fetched df, so an open paper trade still gets
    # monitored every scan regardless of today's data quality reading.
    quality_issues = universe.data_quality_issues(df, ticker)
    if quality_issues:
        log.info("%s: skipping new-signal scan -- data quality: %s",
                  ticker, "; ".join(quality_issues))
        if progress is not None:
            progress.done += max(1, len(horizons_to_scan))
        stats["data_quality_failed"] = True
        return stats

    # RS percentile (v32 Task 7) depends only on this ticker's df/spy_df/the
    # scan-wide universe cache -- not on horizon or direction -- so it's
    # computed once per ticker here rather than once per horizon-scenario
    # inside the loop below. rs_cache is None when the network-bound SPY/RS
    # lookup failed for this scan (see _sync_run_scan); None propagates
    # through cleanly (factor_rs treats it as absent, not a real reading).
    rs_pctile = None
    if rs_cache is not None:
        rs_pctile = rs_factors.rs_percentile(
            df, spy_df, universe_rels=list(rs_cache["rels"].values()))

    # Trendline candidates (v56) depend only on this ticker's df/current_price
    # -- not on horizon -- so they're computed once per ticker here rather
    # than once per horizon inside collect_candidate_levels() below.
    # _find_best_trendline's pairwise pivot scan is O(pivots^3); measured
    # live against production's actual cache (tickers with 10+ years of
    # history), a single call ran 6-9 SECONDS, and it was being repeated
    # once per horizon (10x, identical result every time) -- the dominant
    # cost of the whole scan and the direct cause of the CPU pegged at
    # 100% incident this fix responds to. See trendlines.py's
    # MAX_PIVOT_SCAN_BARS and custom_scanner_levels() docstrings.
    trendline_candidates = trendlines.custom_scanner_levels(df, current_price)

    for horizon_key in horizons_to_scan:
        h = HORIZONS[horizon_key]
        if bars_available < MIN_BARS[horizon_key]:
            if progress is not None:
                progress.done += 1
            continue

        log.debug("%s (%s): building levels (price=%.2f, bars=%d)", ticker, horizon_key, current_price, bars_available)
        # Computed once here and threaded through to build_level_map() and
        # every count_confirming_strategies() call below (up to 2 scenarios x
        # 2 calls each) -- all of them run against this exact same
        # (df, h, current_price), so recomputing per call was pure redundant
        # work (every S/R method rerun from scratch each time): up to 5x the
        # necessary CPU per ticker/horizon, the dominant cost of a scan over
        # a large universe. See levels.count_confirming_strategies's docstring.
        candidates = levels.collect_candidate_levels(df, h, current_price,
                                                       trendline_candidates=trendline_candidates)
        supports, resistances = levels.build_level_map(df, h, current_price, candidates=candidates)
        log.debug("%s (%s): %d support level(s), %d resistance level(s) found",
                   ticker, horizon_key, len(supports), len(resistances))
        floor_pct = levels.atr_floor_pct(df, current_price, h)
        # Reward/stop bounds are widened toward this horizon's OWN scale
        # (h["sr_target_min_pct"] / h["max_risk_pct"], defined per-horizon
        # in strategy_types.py -- up to 22%/11% for a 9-month swing)
        # rather than the flat, horizon-blind config.MIN_REWARD_PCT/
        # MAX_STOP_LOSS_PCT (3%/7%) that used to be applied identically to
        # every horizon from 2 weeks to 9 months. That flat floor let a
        # "9-month swing" scenario qualify with just a 3% target and sit
        # inside a 2-7% stop -- small enough for a couple of ordinary
        # trading days' volatility to fully traverse, which is why trades
        # meant to run for weeks/months were actually closing within
        # hours/days.
        #
        # Progressively loosened after each round came back too strict:
        # full sr_target_min_pct (100%) -> too strict (15-22% targets are
        # rare) -> half (50%) -> still too strict -> 30% -> still not
        # enough trade plans. Now at 15% of the horizon's own target-min,
        # e.g. 9m needs only ~3.3% instead of ~6.6%/11%/22%. This is only
        # barely above config.MIN_REWARD_PCT (3%) for most horizons now --
        # still SOME horizon-awareness (longer horizons ask for a little
        # more room than shorter ones) rather than being fully flat again,
        # but the floor itself is no longer doing much of the "stop
        # trades from closing too fast" work on its own. If trades are
        # still closing too quickly after this, the near-TP timeout
        # scaling (performance.py's check_near_tp_timeout) and the
        # confidence/expectancy gate are the other levers actually worth
        # revisiting -- this min-reward floor is close to its practical
        # floor already. The max stop widening (the ceiling, not a floor)
        # is left at the horizon's full max_risk_pct -- widening a
        # ceiling can only let MORE scenarios qualify, never fewer.
        effective_min_reward = max(hard_filters["min_reward_pct"], h.get("sr_target_min_pct", hard_filters["min_reward_pct"]) * 0.15)
        effective_max_stop = max(hard_filters["max_stop_loss_pct"], h.get("max_risk_pct", hard_filters["max_stop_loss_pct"]))
        scenarios = levels.build_scenarios(current_price, supports, resistances, effective_min_reward,
                                            atr_floor=floor_pct, min_stop_distance_pct=hard_filters["min_stop_distance_pct"],
                                            max_stop_distance_pct=effective_max_stop,
                                            min_risk_reward=hard_filters["min_risk_reward_ratio"],
                                            block_bullish=veto_bullish_for(df))
        stats["checked"] += 1
        # Depends only on df/horizon_key, not scenario.direction -- hoisted
        # above the scenario loop (v56) so a horizon with both a bullish and
        # a bearish scenario computes this once instead of twice, instead of
        # once per scenario for no reason. Guarded on `scenarios` itself (not
        # computed unconditionally) so the far more common no-entry-point
        # horizon -- most ticker/horizon pairs never build a scenario at all
        # -- doesn't pay for a call the old per-scenario placement would
        # never have made either.
        htf_result = get_htf_bias(df, horizon_key) if scenarios else None
        if not scenarios:
            # Either no genuine support AND resistance both exist
            # (no strategy found a real entry point at all), or a
            # real entry point exists but doesn't clear one of the
            # hard requirements (min reward %, stop distance bounds,
            # min reward:risk) -- those are enforced exactly as
            # configured, no exceptions, so a scenario failing any
            # of them is never built in the first place. Either way,
            # nothing to show for this ticker/horizon right now.
            stats["no_entry_point"] += 1
            log.debug("%s (%s): no qualifying entry point (either no genuine support/resistance on both "
                       "sides, or the reward/stop/risk-reward requirements weren't met)", ticker, horizon_key)

        for scenario in scenarios:
            stats["scenarios_found"] += 1
            if scenario.tight_stop:
                log.info("%s (%s, %s): tight stop -- %.1f%% away, below this horizon's normal ATR cushion (%.1f%%)",
                          ticker, horizon_key, scenario.direction, scenario.stop_distance_pct, scenario.atr_floor_pct)

            # v33 Task 4: adjacent-horizon hard gate. Drop this scenario
            # before any scoring work happens for it if the NEXT horizon up
            # trends against it -- e.g. a 2w bullish setup while the 4w
            # trend is bearish. adjacent_aligned() already returns "exempt"
            # (never "opposed") for the longest horizon (no horizon above
            # it) and for an unknowable next-horizon trend, so only a
            # genuine "opposed" verdict drops the scenario here; "exempt"
            # and "aligned" both fall through unchanged. Default OFF
            # (config.MTF_ADJACENT_GATE) -- flips on only after VALIDATION.
            if hard_filters["mtf_adjacent_gate"]:
                mtf_verdict = adjacent_aligned(df, horizon_key, scenario.direction)
                if mtf_verdict["status"] == "opposed":
                    log.debug("%s/%s %s dropped: %s", ticker, horizon_key,
                              scenario.direction, mtf_verdict["reason"])
                    stats["mtf_misaligned"] += 1
                    continue

            # Simulate EVERY supported strategy independently against
            # this ticker (see levels.count_confirming_strategies) and
            # count how many land within CONFLUENCE_DEVIATION_PCT of
            # this scenario's target/stop -- feeds BOTH the "min
            # strategies confirmed" requirement below AND confidence
            # scoring's target/stop confluence factors, so the two
            # can never disagree about what "N strategies agree" means.
            target_confluence = levels.count_confirming_strategies(
                df, h, current_price, scenario.take_profit, tolerance_pct=hard_filters["confluence_deviation_pct"],
                candidates=candidates,
            )
            stop_confluence = levels.count_confirming_strategies(
                df, h, current_price, scenario.stop_loss, tolerance_pct=hard_filters["confluence_deviation_pct"],
                candidates=candidates,
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

            # htf_result computed once above the scenario loop (v56) --
            # score_confidence's htf_bias input and the htf_counter_trend
            # boolean below both reuse it rather than fetching it again.
            macro_verdict = macro_aligned(df, horizon_key, scenario.direction)

            conf = score_confidence(scenario, regime_trend=(regime.trend if regime else None), df=df,
                                     target_confluence=target_confluence, stop_confluence=stop_confluence,
                                     track_record=track_record,
                                     htf_bias=(htf_result["bias"] if htf_result else None),
                                     rs_percentile=rs_pctile, breadth=breadth,
                                     macro_verdict=macro_verdict)

            # Multi-timeframe confluence: check this ticker's own
            # higher-timeframe EMA bias (50-day for short horizons,
            # 200-day for longer ones) using the already-fetched daily
            # df -- no extra API call. Purely informational: it flags the
            # embed warning and plan_v2.regime_aligned below, but no longer
            # reduces the confidence score (v33: the penalty was an exact
            # duplicate of this boolean, Cramer's V = 1.0 -- see
            # docs/superpowers/plans/implemented/v33-trend-signal-reconciliation.md).
            htf_counter_trend = (
                htf_result is not None
                and htf_result["bias"] != scenario.direction
            )

            log.debug(
                "%s %s (%s): target_confluence=%d(%s) stop_confluence=%d(%s) confidence=Lv%d(%d/100)%s",
                ticker, scenario.direction, horizon_key,
                target_confluence[0], ",".join(target_confluence[1][:3]),
                stop_confluence[0], ",".join(stop_confluence[1][:3]),
                conf.level, conf.score,
                " [HTF counter-trend]" if htf_counter_trend else "",
            )

            stats["conf_level_counts"][conf.level] = stats["conf_level_counts"].get(conf.level, 0) + 1

            # Every requirement is checked and kept, always -- see
            # _build_requirement_checks. A scenario with a real entry
            # point never disappears here just because one number
            # falls short; it's tallied below and shown (marked) by
            # the caller instead of silently dropped.
            requirements = _build_requirement_checks(
                scenario, target_confluence, conf,
                effective_min_confluence, effective_min_confidence,
                opex_tier=opex_tier_today)
            all_ok = True
            for r in requirements:
                if not r.passed:
                    stats["failed_counts"][r.key] += 1
                    all_ok = False
            if all_ok:
                stats["fully_qualifying"] += 1

            result = levels.ScenarioSignal(
                ticker=ticker, horizon_key=horizon_key, horizon_label=h["label"],
                trend=scenario.direction, close=current_price, scenario=scenario,
                strategy=primary_strategy_for(scenario),
            )

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

            # Confirmation debounce (require_confirmation) and the final
            # all_ok gate for POSTING an alert are both applied by the
            # caller after the join -- see this function's own docstring.
            # Every scenario, qualifying or not, is built and returned
            # here (mirrors the require_confirmation=False/`!check` path
            # the old inline loop already used unconditionally).
            item = ScanItem(
                result=result, plan=scenario, conf=conf, requirements=requirements,
                target_confluence=target_confluence, stop_confluence=stop_confluence,
                htf_info=htf_info_for_item,
                htf_bias=htf_result["bias"] if htf_result else None,
                rs_percentile=rs_pctile,
            )
            if all_ok:
                item.level_map = (supports, resistances)
            stats["items"].append(item)

        # One unit of progress per (ticker, horizon) pair -- see the
        # horizons_to_scan comment above for why this moved from once
        # per ticker to once per horizon.
        if progress is not None:
            progress.done += 1

    return stats



