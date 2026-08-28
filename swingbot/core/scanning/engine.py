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
import os
import time
from collections import defaultdict
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
from . import fetch
from .dedup import dedup_scan_items, dedup_sector_items
from .fetch import (
    LRUFrames, _chunked, _run_bounded, _fetch_one_ticker, _fetch_cold_frames,
    _load_cached_daily, _crawl_latest_data, _fetch_live_prices,
    _etf_symbol_of_sector, _sector_etfs_for_tickers, _fetch_frames,
    _daily_frame_for, map_tickers,
)
from .telemetry import log_scan_telemetry, recent_telemetry, scan_slowdown
from .runstate import is_scan_running, request_stop
from swingbot.core.marketdata.data import get_currency_symbol
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

from . import analyze
from .analyze import (
    ScanItem, build_decision_context, _build_quality_inputs, attach_plan_v2,
    _check_near_close, _apply_sector_rs, _scan_one,
)
from . import scan_run
from .scan_run import (
    ScanProgress, get_regime, _logged_plan_fields, _sync_run_scan, run_scan,
    get_all_unrealized_pnl,
)
