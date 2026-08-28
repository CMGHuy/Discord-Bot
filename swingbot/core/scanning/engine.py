"""Facade for the scanning package.

Split from the 2347-line engine.py on 2026-08-25 (v61). The scan pipeline
now lives in runstate/telemetry/dedup/fetch/analyze/scan_run; this module
re-exports the external surface so existing call sites keep working unchanged.

`state` and `trade_log` deliberately live HERE, not in a submodule. They are
process-wide singletons whose identity the suite pins; this is the permitted
exception to the no-submodule-imports-the-facade rule.
"""
from swingbot.core.infra.state import StateStore
from swingbot.core.tracking.performance import TradeLog

state = StateStore()
trade_log = TradeLog()

from .runstate import is_scan_running, request_stop
from .telemetry import log_scan_telemetry, recent_telemetry, scan_slowdown
from .dedup import dedup_scan_items, dedup_sector_items
from .fetch import (LRUFrames, _chunked, _run_bounded, _fetch_one_ticker,
                    _fetch_cold_frames, _load_cached_daily, _crawl_latest_data,
                    _fetch_live_prices, _etf_symbol_of_sector,
                    _sector_etfs_for_tickers, _fetch_frames, _daily_frame_for,
                    map_tickers)
from .analyze import (ScanItem, build_decision_context, _build_quality_inputs,
                      attach_plan_v2, _check_near_close, _apply_sector_rs,
                      _scan_one)
from .scan_run import (ScanProgress, get_regime, _logged_plan_fields,
                       _sync_run_scan, run_scan, get_all_unrealized_pnl)
from .embeds import (_build_requirement_checks, build_embed, build_simple_alert,
                     plan_numbers_for_display, regenerate_chart_for_trade,
                     build_closed_trade_embed, notify_closed_trades,
                     build_near_close_embed, notify_near_close,
                     build_plan_event_embed, notify_plan_events)

__all__ = [
    "state", "trade_log", "is_scan_running", "request_stop",
    "log_scan_telemetry", "recent_telemetry", "scan_slowdown",
    "dedup_scan_items", "dedup_sector_items", "LRUFrames", "_chunked",
    "_run_bounded", "_fetch_one_ticker", "_fetch_cold_frames",
    "_load_cached_daily", "_crawl_latest_data", "_fetch_live_prices",
    "_etf_symbol_of_sector", "_sector_etfs_for_tickers", "_fetch_frames",
    "_daily_frame_for", "map_tickers", "ScanItem", "build_decision_context",
    "_build_quality_inputs", "attach_plan_v2", "_check_near_close",
    "_apply_sector_rs", "_scan_one", "ScanProgress", "get_regime",
    "_logged_plan_fields", "_sync_run_scan", "run_scan", "get_all_unrealized_pnl",
    "_build_requirement_checks",
    "build_embed", "build_simple_alert", "plan_numbers_for_display",
    "regenerate_chart_for_trade", "build_closed_trade_embed", "notify_closed_trades",
    "build_near_close_embed", "notify_near_close", "build_plan_event_embed",
    "notify_plan_events",
]
