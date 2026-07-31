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
import json as _json
import logging
import os
import time
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core import levels
from swingbot.core import account as account_module
from swingbot.core.account import compute_unrealized_pnl, load_account_config
from swingbot.core.edge import correlation as corr_mod
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import gates as gates_mod
from swingbot.core.edge import heat as heat_mod
from swingbot.core.edge import regime2
from swingbot.core.edge import throttle
from swingbot.core.jsonio import read_json
from .confidence import ConfidenceResult, score_confidence
from swingbot.core.data import get_currency_symbol, get_current_price, get_daily_data
from swingbot.core.events import earnings_within_window
from swingbot.core.explain import build_explanation
from swingbot.core.market_events import get_market_events
from swingbot.core.notifier import notify_secondary
from swingbot.core.performance import TradeLog
from swingbot.core.quality import atr_percentile as _atr_percentile
from swingbot.core.plan_engine import (build_confluence_plan,
                                       primary_strategy_for, select_tp2)
from swingbot.core.plan_store import PlanStore
from .regime import get_htf_bias, get_market_regime
from swingbot.core.state import StateStore
from swingbot.core.strategy import HORIZONS, MIN_BARS
from swingbot.core import universe
from swingbot.core.charts.decision_chart import render_decision_chart
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.watchlist import load_watchlist
from .embeds import (
    CONFIDENCE_COLORS, CONFIDENCE_EMOJI, CONFIDENCE_ANSI,
    confidence_color, _build_requirement_checks, build_embed,
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
    plan_v2: object = None            # TradePlanV2 | None
    level_map: tuple = None           # (supports, resistances); staged in _scan_one for attach_plan_v2, called later in _sync_run_scan once confirmation is decided (Task E20 fix)
    rs_percentile: float | None = None  # percentile (0-100) of relative return vs the scanned universe; None when the RS benchmark fetch fails (Task E25)
    breadth: float | None = None      # % of scanned universe above its own 50-EMA at scan time; None on a too-small universe (Task E28)
    intraday: bool | None = None      # 1h close vs today's VWAP on this plan's side; None = no reading = neutral, never blocks (Task E29)
    gate: object = None                # GateResult | None from _gate_evaluate; None when GATE_ENABLED=false or no v2 plan (G103)

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
    "rs": 10, "mtf": 10, "breadth": 5, "candle": 5,
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
        ctx["avwaps"] = [{"series": rs_factors.anchored_vwap(df, a), "anchor_label": f"⚓{a}"}
                          for a in rs_factors.avwap_anchors(df)[:3]]
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
            "advisor": None,        # no LLM-advisor module in this codebase yet (llm-advisor-v5 plan, not built)
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

    return dedup_sector_items(deduped)


def dedup_sector_items(items: list) -> list:
    """Portfolio-level dedup (Task E78): multiple same-sector signals in one
    scan collapse to the highest-follow-score one, gaining `also_qualifying`
    -- the correlation/sector caps would block the extras anyway, so don't
    tease untakeable trades. Items without a `sector` attribute (every real
    ScanItem today -- sector stamping from universe.sector_map is not wired
    up anywhere yet) pass through untouched, making this a documented no-op
    live until that lands, same as this plan's other pre-registered-but-
    unwired factors (E33's REGIME_ALLOW, E40's blocked sub-step)."""
    by_sector: dict = {}
    passthrough = []
    for it in items:
        sec = getattr(it, "sector", None)
        (by_sector.setdefault(sec, []) if sec else passthrough).append(it)
    out = list(passthrough)
    for sec, group in by_sector.items():
        group.sort(key=lambda i: getattr(i, "follow_score", 0) or 0, reverse=True)
        best = group[0]
        best.also_qualifying = [g.ticker for g in group[1:]]
        out.append(best)
    out.sort(key=lambda i: getattr(i, "follow_score", 0) or 0, reverse=True)
    return out


TELEMETRY_PATH = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")


def log_scan_telemetry(stats: dict, path: str | None = None) -> None:
    """Task E82: one JSON line per scan (at, duration_s, tickers, errors,
    data_skips, signals, alerts, open_heat) appended to scan_telemetry.jsonl
    -- cheap append-only history for scan_slowdown()'s alarm and the admin
    risk page's duration sparkline."""
    import datetime as dt
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), **stats}
    with open(path or TELEMETRY_PATH, "a", encoding="utf-8") as f:
        f.write(_json.dumps(row) + "\n")


def recent_telemetry(n: int = 50, path: str | None = None) -> list:
    try:
        with open(path or TELEMETRY_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [_json.loads(l) for l in lines if l.strip()]
    except OSError:
        return []


def scan_slowdown(path: str | None = None) -> bool:
    """True when the latest logged scan took more than 2x the median of
    the prior 20 -- a real slowdown, not noise from a single slow ticker."""
    rows = recent_telemetry(21, path=path)
    if len(rows) < 6:
        return False
    import statistics
    prior = [r["duration_s"] for r in rows[:-1]]
    return rows[-1]["duration_s"] > 2 * statistics.median(prior)


class LRUFrames(OrderedDict):
    """Bounded frame store for universe-scale scans on an 8GB box (Task
    E83): CX23 has 8GB, and 500 tickers x ~2MB frames uncapped would eat
    1GB+ alongside pandas temporaries. Evicted frames simply come back as
    a cache miss (`.get(ticker)` -> None) to every consumer in this module
    -- every real call site already treats a missing frame as "no data for
    this ticker this scan" (the same as a failed fetch), so there is no
    separate reload path to wire.

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
    live v2 plan permanently quality_score=0/tier="C" -- scoring never ran,
    not "scored low". direction/badge_status are NOT included here: plan_
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
    htf = get_htf_bias(df, horizon_key)
    target_confluence = getattr(item, "target_confluence", None)
    confluence_count = target_confluence[0] if target_confluence else 0
    return {
        "regime": regime.trend if regime else None,
        "htf_bias": htf["bias"] if htf else None,
        "confluence_count": confluence_count,
        "volume_ratio": volume_ratio,
        "atr_pct": _atr_percentile(df),
        "trigger_distance_pct": abs(scenario.entry - current_price) / current_price * 100,
        "rs_percentile": rs_percentile,
        "mtf": rs_factors.mtf_alignment(df, scenario.direction),
        "breadth": breadth,
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
            quality_inputs=quality_inputs)
        if plan.tp2 is None and level_map is not None:
            supports, resistances = level_map
            plan.tp2 = select_tp2([lv.price for lv in resistances],
                                  [lv.price for lv in supports],
                                  plan.direction, plan.trigger_price, plan.tp1)
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

    results = LRUFrames()   # Task E83: bounded, evicts oldest frames past 200 tickers
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
              regime, effective_min_confluence: int) -> dict:
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
    stats = {
        "items": [],
        "newly_closed": [],
        "near_close_warnings": [],
        "checked": 0,
        "no_entry_point": 0,
        "scenarios_found": 0,
        "fully_qualifying": 0,
        "failed_counts": {
            "min_reward": 0, "min_stop_distance": 0, "max_stop_distance": 0,
            "min_risk_reward": 0, "min_confluence": 0, "min_confidence": 0,
        },
        "conf_level_counts": {},   # {1..5: number of scenarios scored at that level}
        "data_quality_failed": False,   # E47: this ticker tripped the E16 data-quality gate
    }

    if is_stop_requested():
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

    # Fetch live price (incl. premarket/aftermarket) once per ticker and use
    # it both for SL/TP hit detection and as the current_price for new plans.
    live = get_current_price(ticker)
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

    for horizon_key in horizons_to_scan:
        h = HORIZONS[horizon_key]
        if bars_available < MIN_BARS[horizon_key]:
            if progress is not None:
                progress.done += 1
            continue

        log.debug("%s (%s): building levels (price=%.2f, bars=%d)", ticker, horizon_key, current_price, bars_available)
        supports, resistances = levels.build_level_map(df, h, current_price)
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
        effective_min_reward = max(config.MIN_REWARD_PCT, h.get("sr_target_min_pct", config.MIN_REWARD_PCT) * 0.15)
        effective_max_stop = max(config.MAX_STOP_LOSS_PCT, h.get("max_risk_pct", config.MAX_STOP_LOSS_PCT))
        scenarios = levels.build_scenarios(current_price, supports, resistances, effective_min_reward,
                                            atr_floor=floor_pct, min_stop_distance_pct=config.MIN_STOP_DISTANCE_PCT,
                                            max_stop_distance_pct=effective_max_stop,
                                            min_risk_reward=config.MIN_RISK_REWARD_RATIO)
        stats["checked"] += 1
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

            stats["conf_level_counts"][conf.level] = stats["conf_level_counts"].get(conf.level, 0) + 1

            # Every requirement is checked and kept, always -- see
            # _build_requirement_checks. A scenario with a real entry
            # point never disappears here just because one number
            # falls short; it's tallied below and shown (marked) by
            # the caller instead of silently dropped.
            requirements = _build_requirement_checks(scenario, target_confluence, conf, effective_min_confluence)
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
    effective_min_confluence = config.MIN_TARGET_CONFLUENCE_COUNT if min_confluence is None else min_confluence
    log.info("Scan starting: horizon_filter=%s require_confirmation=%s watchlist=%d ticker(s) min_confluence=%d",
              horizon_filter, require_confirmation, len(tickers), effective_min_confluence)

    # Phase 1: crawl -- fetch every ticker's latest data up front,
    # sequentially, before any analysis runs. See _crawl_latest_data()
    # and the module docstring for why this is a separate phase (and why
    # it's sequential, not concurrent).
    fresh_data = _crawl_latest_data(tickers, progress)

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
        spy_df = get_daily_data(config.MARKET_REGIME_TICKER)
        if spy_df is not None:
            rs_cache = rs_factors.refresh_rs_cache(fresh_data, spy_df)
    except Exception as e:
        log.warning("Could not compute relative-strength cache: %s", e)
        spy_df = None
        rs_cache = None

    account_cfg = load_account_config()

    scan_items = []
    all_newly_closed = []
    all_near_close_warnings = []
    checked_count = 0
    no_entry_point = 0
    scenarios_found_count = 0
    fully_qualifying_count = 0
    data_quality_failed_count = 0   # E47: feeds check_kill_triggers' data_fail_frac
    failed_counts = {
        "min_reward": 0, "min_stop_distance": 0, "max_stop_distance": 0,
        "min_risk_reward": 0, "min_confluence": 0, "min_confidence": 0,
    }
    conf_level_counts: dict = {}   # {1..5: number of scenarios scored at that level}
    filtered_by_confirmation = 0

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
        lambda t: _scan_one(t, fresh_data.get(t), horizons_to_scan, progress, regime, effective_min_confluence),
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
            # rs_percentile/breadth computed BEFORE attach_plan_v2 below (Task
            # E37 wiring fix) specifically so quality scoring can see them --
            # they used to be set after attach_plan_v2 ran, so every live
            # plan's quality_inputs saw them as unset regardless of data
            # availability. Unconditional for every item, same as before.
            if rs_cache is not None:
                item.rs_percentile = rs_factors.rs_percentile(
                    fresh_data.get(item.result.ticker), spy_df,
                    universe_rels=list(rs_cache["rels"].values()),
                )
            item.breadth = breadth  # Task E28: one scan-wide reading, same for every item
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
            "breadth": breadth,  # % of universe above its own 50-EMA at scan time (Task E28)
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

        # Broader than an exact (strategy, horizon_key) repeat: also catches
        # a near-identical plan surfaced under a DIFFERENT strategy/horizon
        # (e.g. running !check repeatedly finds essentially the same S/R
        # levels under 3m/5m/7m/9m, each a technically distinct horizon_key)
        # -- see has_similar_open_trade()'s own docstring. Without this,
        # has_open_trade()'s exact-key match let repeated !check runs log a
        # fresh "new" open trade every time for what was really the same
        # setup, one per horizon that happened to qualify that scan.
        already_open = (
            trade_log.has_open_trade(result.ticker, result.strategy, result.horizon_key, result.trend)
            or trade_log.has_similar_open_trade(
                result.ticker, result.trend, plan.entry, plan.stop_loss, plan.take_profit,
                tol_pct=config.DEDUP_TOLERANCE_PCT,
            )
        )
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
        if item.all_requirements_met and not already_open:
            # v2 plan pedigree (tier/badge/quality/source) rides along with
            # plan_id -- same cutover guard: only a live "on" plan is real
            # pedigree, "shadow"/"off" trades log as legacy (None) rows.
            plan_v2 = (item.plan_v2
                       if config.PLAN_ENGINE_V2 == "on" and item.plan_v2 is not None
                       else None)
            trade_id = trade_log.log_trade(
                ticker=result.ticker, strategy=result.strategy, horizon_key=result.horizon_key,
                direction=result.trend, confidence_level=conf.level, confidence_label=conf.label,
                entry=nums["entry"], stop_loss=nums["stop_loss"], take_profit=nums["take_profit"],
                target2=nums["target2"],
                confidence_score=conf.score, confidence_breakdown=conf.breakdown,
                target_sources=list(dict.fromkeys(plan.target_sources)),
                stop_sources=list(dict.fromkeys(plan.stop_sources)),
                target2_sources=list(dict.fromkeys(plan.target2_sources)) if plan.target2_sources else [],
                risk_reward_ratio=plan.risk_reward_ratio,
                explanation=explanation,
                confirmed_by=item.combined_from,
                plan_id=plan_v2.plan_id if plan_v2 is not None else None,
                tier=plan_v2.tier if plan_v2 is not None else None,
                badge=plan_v2.badge if plan_v2 is not None else None,
                quality_score=plan_v2.quality_score if plan_v2 is not None else None,
                source=plan_v2.source if plan_v2 is not None else None,
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
            if config.DECISION_CHART_ENABLED and item.plan_v2 is not None:
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

        # Gatekeeper live wiring (G103): evaluated in ALL modes when
        # GATE_ENABLED -- the shadow log is the evidence stream regardless
        # of mode. Only meaningful for a v2 plan: the checklist reads
        # TradePlanV2's own field names (trigger_price/tp1/tp2/direction),
        # which the legacy `plan` object here does not share (same
        # constraint as the decision chart above). _gate_evaluate lives in
        # swingbot.commands.scanning (imported lazily -- that module
        # imports swingbot.core.scan_engine at load time, so a top-level
        # import here would cycle). item.gate carries the raw GateResult
        # (or None); build_embed does not accept it yet -- the render
        # matrix and its `gate=` kwarg land in G123, so until then this is
        # evaluated + logged (shadow_log) + attached to the plan, but never
        # rendered, which is exactly shadow behavior -- alert embeds stay
        # byte-for-byte unchanged in every mode today.
        if item.plan_v2 is not None:
            import types as _types
            from swingbot.commands.scanning import _gate_evaluate

            macro_snap = None
            if config.MACRO_ENABLED:
                try:
                    from swingbot.core.macro import snapshot as macro_snapshot
                    macro_snap = macro_snapshot.load_snapshot()
                except Exception:
                    log.debug("macro snapshot unavailable for gate eval on %s", result.ticker)
            gate_candidate = _types.SimpleNamespace(
                ticker=result.ticker, strategy=result.strategy,
                plan=item.plan_v2, df_daily=df)
            _gate_decision, item.gate = _gate_evaluate(gate_candidate, PlanStore(), macro_snap)

        embed = build_embed(item, explanation, perf_stats, warning, chart_filename,
                            htf_info=item.htf_info, layout=config.ALERT_EMBED_LAYOUT)
        alerts.append((embed, chart_path, item.plan_v2))

        # Secondary alerting (email / push) -- fires only for high-confidence,
        # fully-qualifying alerts when enabled. Blocking I/O but we're already
        # in the background thread (_sync_run_scan), so it won't block Discord.
        notify_secondary(item, plan, conf)

        if progress is not None:
            progress.alerts_done += 1

    log.info("Scan pass complete: %d alert(s) built, %d skipped (already open)", len(alerts), skipped_already_open)

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
        log_scan_telemetry(scan_stats)
        if scan_slowdown():
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
