"""
Core scanning engine -- shared by the automatic session scan and the
manual !check command. Not Discord-command code itself; bot_core.py and
the cmd_*.py modules call into this.

Every scan runs in two clearly separated phases, in order:
  1. CRAWL -- fetch the latest daily OHLCV data (_crawl_latest_data()) and
     the whole watchlist's live price (_fetch_live_prices()) for every
     ticker, before any analysis touches a single price. This guarantees
     every scenario a scan produces was built from data fetched at the
     START of that scan, not a stale earlier fetch. Both are batched --
     one (or a few, chunked) yf.download() call covering many tickers,
     never several concurrent calls -- see _run_bounded()'s own docstring
     for why concurrent calls specifically (not batched ones) are unsafe:
     the pinned yfinance version isn't reentrant across threads.
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
import json as _json
import logging
import math
import multiprocessing
import os
import time
from collections import OrderedDict, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait as _futures_wait
from dataclasses import dataclass, field
from datetime import datetime, timezone

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core.market import levels
from swingbot.core.market import trendlines
from swingbot.core.planning import account as account_module
from swingbot.core.market import market_context
from swingbot.core.planning.account import compute_unrealized_pnl, load_account_config
from swingbot.core.edge import correlation as corr_mod
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import gates as gates_mod
from swingbot.core.edge import heat as heat_mod
from swingbot.core.edge import regime2
from swingbot.core.edge import throttle
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.infra.jsonio import read_json
from .confidence import score_confidence
from . import runstate
from . import telemetry
from . import dedup
from .dedup import dedup_scan_items, dedup_sector_items
from .telemetry import log_scan_telemetry, recent_telemetry, scan_slowdown
from .runstate import is_scan_running, request_stop
from swingbot.core.marketdata.data import (get_currency_symbol, get_current_price, get_daily_data,
                                   get_current_price_batch, get_daily_data_batch)
from swingbot.core.market.mtf import adjacent_aligned, macro_aligned
from swingbot.core.market.reversal import evaluate_reversal, reversals_for_ticker
from swingbot.core.market.events import earnings_within_window
from swingbot.core.market.explain import build_explanation
from swingbot.core.market.market_events import get_market_events
from swingbot.core.market import opex
from swingbot.core.infra.notifier import notify_secondary
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.planning.quality import atr_percentile as _atr_percentile
from swingbot.core.planning.plan_engine import (build_confluence_plan,
                                       primary_strategy_for)
from swingbot.core.planning.plan_store import PlanStore
from .regime import get_htf_bias, get_market_regime
from swingbot.core.infra.state import StateStore
from swingbot.core.market.strategy import HORIZONS, MIN_BARS
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.marketdata import universe
from swingbot.core.charts.decision_chart import render_decision_chart
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.charts.trendline_fit import fit_trendline
from swingbot.core.marketdata.watchlist import load_watchlist
# Several of these are unused HERE and re-exported on purpose: callers reach
# them via `from swingbot.core.scanning import engine as scan_engine` --
# the live equivalent of the old core/scan_engine.py `import *` shim,
# removed 2026-08-15 by the v27 repo restructure (admin/helpers.py imports
# CONFIDENCE_COLORS, commands/trades.py uses
# scan_engine.regenerate_chart_for_trade). Check for importers before
# deleting one. CONFIDENCE_EMOJI/CONFIDENCE_ANSI were removed from this
# re-export list 2026-08-21 -- zero external consumers via scan_engine.*
# (they're still used directly inside embeds.py itself).
from .embeds import (  # noqa: F401
    CONFIDENCE_COLORS,
    confidence_color, _build_requirement_checks, build_embed, build_simple_alert,
    plan_numbers_for_display,
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


class LRUFrames(OrderedDict):
    """Frame store with an explicit capacity for one complete scan.

    The crawl passes ``max_frames=len(tickers)``. A scan must retain every
    fetched frame: an eviction would otherwise look like a data failure to
    later analysis and open-trade monitoring.

    get() is overridden alongside __getitem__: CPython's dict.get() calls
    into the C-level hash table directly and does NOT dispatch through a
    subclass's __getitem__ override, and this module reads frames almost
    exclusively via `fresh_data.get(ticker)`, never `fresh_data[ticker]` --
    without this override, recency would only ever update on insert, and
    eviction would silently degrade to FIFO instead of LRU."""
    def __init__(self, max_frames: int = 200):
        super().__init__()
        self.max_frames = max_frames

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_frames:
            self.popitem(last=False)


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


def _chunked(items: list, size: int) -> list:
    """Splits `items` into consecutive slices of at most `size` each."""
    size = max(1, int(size))
    return [items[i:i + size] for i in range(0, len(items), size)]


# E47 follow-up, confirmed live on production 2026-08-25: the default
# ProcessPoolExecutor start method on Linux is 'fork', which clones the
# parent's entire memory -- including yfinance 0.2.66's process-wide
# singleton curl_cffi session (libcurl/OpenSSL handles, connection state,
# internal locks) the instant it has been touched even once by the parent
# (any earlier _fetch_one_ticker/get_current_price call, or the background
# market_data_refresh loop, all running in this same long-lived process).
# libcurl and OpenSSL are not fork-safe once used -- glibc's own malloc
# arena locks aren't guaranteed safe across fork() either when other
# threads are alive, and this process always has some (asyncio's default
# to_thread executor, map_tickers' ThreadPoolExecutor). Every worker forked
# after that point crashed on startup with a libc.so.6 segfault (`dmesg`:
# identical faulting address/instruction pointer every time), which
# concurrent.futures surfaces as BrokenProcessPool ("A process in the
# process pool was terminated abruptly") -- not the timeout-kill path
# below, a completely different failure that happened to look similar in
# the logs. With v55's batched fetch (one fork per whole chunk, not per
# ticker) a single crashed fork now fails 10-15+ tickers at once, which is
# what pushed E47's data_fail_frac over the 20% kill-switch threshold on
# every single scan. 'spawn' starts each worker as a brand-new interpreter
# with no inherited C-level state, eliminating the hazard at the root
# instead of chasing it fork-by-fork; the extra ~1-2s interpreter startup
# per chunk is cheap against COLD_FETCH_TIMEOUT_SECONDS' 180s budget. This
# is a no-op on Windows dev machines, which only ever had 'spawn' to begin
# with (no fork() at all) -- exactly why this never reproduced off Linux.
_SPAWN_CTX = multiprocessing.get_context("spawn")


def _run_bounded(fn, args: tuple, timeout_seconds: float, label: str):
    """Runs fn(*args) in a single-process pool with a hard wall-clock
    budget. Returns fn's result, or None if the budget is exceeded (or fn
    itself raised).

    A PROCESS, not a thread -- two independent reasons stacked on top of
    each other. First, the pinned yfinance 0.2.66 builds download() on a
    shared, non-reentrant module global (_DFS); a separate process has its
    own interpreter and memory, so nothing here can ever race a concurrent
    caller's _DFS the way a ThreadPoolExecutor once did (see this module's
    own docstring -- two real watchlist tickers once had their price data
    swapped this way). Second -- why the budget exists at all -- a stalled
    DNS lookup or a fork-inherited lock can wedge a worker past whatever
    timeout `fn` itself was given, with no exception and no CPU use; only a
    killed OS process is a reliable ceiling. Confirmed live on production
    2026-08-24: a single stuck cold fetch froze session_scan, and every
    tick behind it, for 2+ hours (d251cef fixed this for the per-ticker
    pool it used to bound; this helper generalizes that same wait-then-kill
    mechanism to one future per batched call instead of one per ticker).

    mp_context=_SPAWN_CTX (E47 follow-up, 2026-08-25): see that constant's
    own comment -- 'fork' (the Linux default) crashes on startup here.

    shutdown(wait=False) alone only cancels futures that never started --
    it does not stop one mid-flight, so a still-running worker is force-
    killed outright.
    """
    with ProcessPoolExecutor(max_workers=1, mp_context=_SPAWN_CTX) as pool:
        future = pool.submit(fn, *args)
        done, not_done = _futures_wait([future], timeout=timeout_seconds)
        if future in done:
            try:
                return future.result()
            except Exception as exc:
                log.error("%s failed: %s", label, exc)
                return None
        log.error(
            "%s did not finish within %ss -- killing the worker process and "
            "treating this as a failed fetch", label, timeout_seconds)
        for proc in pool._processes.values():
            proc.kill()
        # wait=True (v56, was False): confirmed live on production 2026-08-24
        # that wait=False lets this function return with the pool's manager
        # thread still alive in the background -- unjoined, since Executor's
        # own __exit__ shutdown(wait=True) call on the way out of the `with`
        # block is a no-op by then (this shutdown() already cleared
        # _executor_manager_thread/_processes to None, which is exactly what
        # that second call's own guards check). A NEW ProcessPoolExecutor
        # created by the very next _run_bounded call then fork()s while that
        # orphaned thread is still running -- and every subsequent call that
        # scan pass failed instantly with "process ... terminated abruptly"
        # (15 tickers' cold-fetch fallback, the live-price batch, and the
        # sector-ETF fetch all failed in the same few seconds). The worker
        # is already SIGKILLed above, so the manager thread notices via its
        # sentinel almost immediately -- wait=True here joins that thread
        # before returning, so it can no longer be alive at the next call's
        # fork() point. This is NOT the same risk shutdown()'s wait=True
        # normally carries (blocking on a live, possibly-still-hung worker):
        # that worker is already dead.
        pool.shutdown(wait=True, cancel_futures=True)
        return None


def _fetch_one_ticker(ticker: str) -> tuple:
    """Single-ticker fetch, module-level so it stays picklable for
    _run_bounded(). No longer the primary cold-fetch path (v55:
    _fetch_cold_frames batches instead) -- kept as the candidate_symbols()-
    aliasing fallback for a ticker whose batch slice came back empty, since
    a batched get_daily_data_batch() call only ever tries a ticker's
    literal symbol.

    Returns (ticker, DataFrame|None). Never raises -- a worker that raised
    would surface as a BrokenProcessPool and take down whatever else
    _run_bounded is protecting alongside it.
    """
    try:
        return ticker, get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
    except Exception as exc:
        log.error("Crawl: error fetching data for %s: %s", ticker, exc)
        return ticker, None


def _fetch_cold_frames(tickers: list, progress: "ScanProgress" = None) -> list:
    """v55: fetch the cache misses via batched, chunked, bounded calls.

    Every cold ticker -- any count -- goes through one or more batched
    get_daily_data_batch() calls (BATCH_FETCH_CHUNK_SIZE tickers per call,
    default covers today's whole watchlist in one chunk) instead of a
    per-ticker call. Each chunk runs through _run_bounded(), so a stalled
    chunk is killed and treated as a failed fetch for every ticker in it
    rather than wedging the crawl -- COLD_FETCH_TIMEOUT_SECONDS now bounds
    one batched chunk instead of one ticker's fetch.

    A ticker absent from its chunk's batch result (the whole chunk failed,
    or just that ticker's own slice was empty) falls back to the single-
    ticker _fetch_one_ticker(), which -- unlike the batch path -- also
    tries candidate_symbols() aliasing. In steady state this remainder is
    empty or near-empty.

    Returns order-preserving (ticker, DataFrame|None) pairs -- the same
    contract this function has always had.
    """
    if not tickers:
        return []

    period = config.DEFAULT_HISTORY_PERIOD
    chunk_size = int(getattr(config, "BATCH_FETCH_CHUNK_SIZE", 100))
    timeout = int(getattr(config, "COLD_FETCH_TIMEOUT_SECONDS", 180))
    resolved: dict = {}
    remainder: list = []

    for chunk in _chunked(tickers, chunk_size):
        if runstate.is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        result = _run_bounded(
            get_daily_data_batch, (chunk, period), timeout,
            label=f"Crawl: cold-fetch batch of {len(chunk)} ticker(s)") or {}
        for ticker in chunk:
            if ticker in result:
                resolved[ticker] = result[ticker]
            else:
                remainder.append(ticker)
        if progress is not None:
            progress.done += len(chunk)
            progress.current_ticker = chunk[-1]

    for ticker in remainder:
        if runstate.is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        _, df = _run_bounded(
            _fetch_one_ticker, (ticker,), timeout,
            label=f"Crawl: cold-fetch fallback for {ticker}") or (ticker, None)
        resolved[ticker] = df

    return [(t, resolved.get(t)) for t in tickers]


def _load_cached_daily(ticker: str):
    """v47: today's daily bar from market_data/daily/{TICKER}.csv, or None.

    None means "cold" -- missing, stale, or unreadable -- and the caller
    fetches it instead. `market_data_refresh` (commands/scanning.py) already
    keeps this cache warm for exactly load_watchlist(), so in steady state this
    is the path every ticker takes and the scan makes no network calls at all.

    Staleness reuses data_refresh.is_stale() rather than reimplementing it: it
    already handles "file missing" and takes an explicit max_age_hours, so the
    scan's freshness bar (SCAN_CACHE_MAX_AGE_HOURS, 6h) stays independent of
    the background loop's own 12h daily refetch cadence.
    """
    try:
        if data_refresh.is_stale(ticker, "daily",
                                 max_age_hours=config.SCAN_CACHE_MAX_AGE_HOURS):
            return None
        return data_store.load_normalized(ticker, "daily")
    except Exception as exc:
        log.debug("Crawl: cache lookup failed for %s (%s) -- treating as cold", ticker, exc)
        return None


def _crawl_latest_data(tickers: list, progress: "ScanProgress" = None) -> dict:
    """
    Phase 1 of every scan: fetches the latest daily OHLCV data for every
    ticker in `tickers` BEFORE any analysis runs. This is the only place
    a scan fetches price data from -- build_level_map(), build_scenarios(),
    confidence scoring, etc. downstream never fetch anything themselves,
    they only ever see what this function already pulled fresh.

    v47: cache-first. A ticker whose market_data/daily/{TICKER}.csv is
    present and fresher than SCAN_CACHE_MAX_AGE_HOURS is served from disk and
    never reaches the fetch path at all -- `market_data_refresh` already keeps
    that cache warm for exactly load_watchlist(), so in steady state the whole
    crawl costs no network. Only genuine misses (the "cold" list) are fetched,
    and everything below is about them.

    Cold tickers are fetched ONE AT A TIME, sequentially -- deliberately NOT a
    concurrent thread pool. This used to run through a bounded
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

    Checks runstate.is_stop_requested() once per ticker and ends the crawl early
    (returning whatever was fetched so far) if a stop was requested --
    see the module-level _STOP_FILE docstring above for why this is
    file-based and only checked at per-ticker checkpoints, not instant.
    """
    if progress is not None:
        progress.stage = "crawling data"
        progress.total = len(tickers)
        progress.done = 0
        progress.current_ticker = None

    results = LRUFrames(max_frames=len(tickers))
    started = time.monotonic()

    cold = []
    warm = 0
    for ticker in tickers:
        if runstate.is_stop_requested():
            log.info("Crawl: stop requested -- ending early (%d/%d ticker(s) resolved so far)",
                      len(results), len(tickers))
            if progress is not None:
                progress.stopped = True
            return results
        df = _load_cached_daily(ticker)
        if df is not None:
            results[ticker] = df
            warm += 1
            if progress is not None:
                progress.done += 1
                progress.current_ticker = ticker
            continue
        cold.append(ticker)

    for ticker, df in _fetch_cold_frames(cold, progress):
        if df is not None:
            results[ticker] = df

    elapsed = time.monotonic() - started
    log.info("Crawl complete in %.1fs: %d/%d ticker(s) resolved (%d from cache, %d fetched)",
              elapsed, len(results), len(tickers), warm, len(cold))
    return results


def _fetch_live_prices(tickers: list, progress: "ScanProgress" = None) -> dict:
    """v55: Phase 1b of every scan -- one batched live-price fetch (chunked)
    for the WHOLE watchlist, not just cold tickers: a warm daily-bar cache
    says nothing about today's live (incl. pre/post-market) price. Runs
    through the same bounded process pool as the cold OHLCV fetch
    (_run_bounded), so a stalled chunk can never hang the scan the way the
    old analyze-phase loop's unbounded per-ticker get_current_price() calls
    could -- LIVE_PRICE_TIMEOUT_SECONDS bounds one batched chunk.

    Returns {ticker: price} for tickers whose chunk resolved. A ticker
    absent from the result falls back to today's daily close in _scan_one,
    exactly as a live-price fetch failure has always degraded.
    """
    if not tickers:
        return {}
    chunk_size = int(getattr(config, "BATCH_FETCH_CHUNK_SIZE", 100))
    timeout = int(getattr(config, "LIVE_PRICE_TIMEOUT_SECONDS", 60))
    started = time.monotonic()
    prices: dict = {}
    for chunk in _chunked(tickers, chunk_size):
        if runstate.is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        result = _run_bounded(
            get_current_price_batch, (chunk,), timeout,
            label=f"Crawl: live-price batch of {len(chunk)} ticker(s)")
        if result:
            prices.update(result)
    log.info("Live-price fetch complete in %.1fs: %d/%d ticker(s) resolved",
              time.monotonic() - started, len(prices), len(tickers))
    return prices


def _etf_symbol_of_sector() -> dict:
    """v34 Task 5 fix: the sector-name -> SPDR ETF symbol resolution,
    factored out so both `_sector_etfs_for_tickers` (which ETFs does this
    watchlist need fetched) and `_apply_sector_rs` (was THIS ticker's own
    sector ETF actually among the frames fetched this scan) share one
    mapping instead of each inverting etfs.json's {symbol: sector} on its
    own.

    Static-file lookup only, no network -- sp500.json's `sector` strings
    and etfs.json's `sector` strings come from the same GICS-style
    vocabulary (e.g. "Information Technology", "Financials"), so inverting
    the ETF file's {symbol: sector} into {sector: symbol} is enough to
    translate a ticker's sector into the SPDR ETF that tracks it, with no
    separate translation table to maintain.
    """
    etf_of_symbol = universe.sector_map("etfs")          # {ETF symbol: sector}
    return {sector: sym for sym, sector in etf_of_symbol.items()}


def _sector_etfs_for_tickers(tickers: list) -> tuple:
    """v34 Task 5: which sector ETFs does this watchlist touch?

    Returns (sector_of_ticker, needed_etf_symbols):
      - sector_of_ticker: {ticker: sector} for every ticker sp500.json
        knows about (its own universe file, not the watchlist -- unrelated
        tickers just won't be looked up). A ticker sp500.json doesn't have
        (delisted, newly added, ETF-only watchlist, ...) is simply absent
        -- the caller's `.get()` treats that the same as "unknown sector".
      - needed_etf_symbols: the distinct, sorted list of ETF symbols to
        fetch -- sorted only for deterministic test/log output, order
        carries no meaning downstream.
    """
    sector_of_ticker = universe.sector_map("sp500")
    etf_symbol_of_sector = _etf_symbol_of_sector()
    needed = sorted({
        etf_symbol_of_sector[sector_of_ticker[t]]
        for t in tickers
        if sector_of_ticker.get(t) in etf_symbol_of_sector
    })
    return sector_of_ticker, needed


def _fetch_frames(symbols: list) -> dict:
    """Cache-first resolution for a small side-list of symbols (sector ETFs,
    currently at most the 11 SPDR sector funds in etfs.json).

    v47: warm symbols come from market_data/daily/*.csv and cost no network;
    the cold remainder goes through _fetch_cold_frames, which batches this
    small a list (11 symbols) into a single call (v55). A symbol whose
    fetch fails is simply absent from the result, exactly like
    _crawl_latest_data."""
    frames = {}
    cold = []
    for symbol in symbols:
        df = _load_cached_daily(symbol)
        if df is not None:
            frames[symbol] = df
        else:
            cold.append(symbol)
    for symbol, df in _fetch_cold_frames(cold):
        if df is not None:
            frames[symbol] = df
    return frames


def _daily_frame_for(symbol: str):
    """v47: cache-first single-symbol daily frame, for the regime benchmark.

    Returns None on a cache miss whose fetch also failed -- callers already
    treat that as "unavailable this scan"."""
    df = _load_cached_daily(symbol)
    if df is not None:
        return df
    try:
        return get_daily_data(symbol, period=config.DEFAULT_HISTORY_PERIOD)
    except Exception as exc:
        log.warning("Could not resolve daily frame for %s: %s", symbol, exc)
        return None


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


def map_tickers(fn, tickers: list, workers: int | None = None) -> list:
    """Order-preserving, error-isolated parallel map for the scan loop.
    The per-ticker work is pandas/numpy-heavy (releases the GIL in C) so
    threads give real speedup without multiprocessing's pickling pain.

    Unlike _crawl_latest_data (network-bound, kept strictly sequential --
    see that function's docstring for the yfinance thread-safety reason),
    this is for the ANALYZE phase only, which never touches yfinance --
    it's safe to parallelize.
    """
    n = workers if workers is not None else getattr(config, "SCAN_WORKERS", 4)

    def safe(t):
        try:
            return fn(t)
        except Exception:
            log.exception("scan worker failed for %s", t)
            return None

    if n <= 1 or len(tickers) <= 1:
        return [safe(t) for t in tickers]
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(safe, tickers))


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
                                            min_risk_reward=hard_filters["min_risk_reward_ratio"])
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
    fresh_data = _crawl_latest_data(tickers, progress)

    # Phase 1b: one batched live-price fetch for the whole watchlist (v55),
    # still inside the crawl phase so the ANALYZE phase below stays pure
    # dict lookups -- see _fetch_live_prices and _scan_one's use of it.
    live_prices = _fetch_live_prices(tickers, progress)

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
        spy_df = _daily_frame_for(config.MARKET_REGIME_TICKER)
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
        etf_symbol_of_sector = _etf_symbol_of_sector()
        sector_of_ticker, needed_sector_etfs = _sector_etfs_for_tickers(tickers)
        if needed_sector_etfs:
            sector_etf_frames = _fetch_frames(needed_sector_etfs)
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
    per_ticker_results = map_tickers(
        lambda t: _scan_one(t, fresh_data.get(t), horizons_to_scan, progress, regime, effective_min_confluence,
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
            _apply_sector_rs(item, item.result.ticker, sector_of_ticker,
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
                attach_plan_v2(item, item.plan, fresh_data.get(item.result.ticker),
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
                live_price = get_current_price(result.ticker)
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
                df = get_daily_data(result.ticker, period=config.DEFAULT_HISTORY_PERIOD)
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
                ctx = build_decision_context(item, fresh_data, spy_df)
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
