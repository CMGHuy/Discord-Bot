"""
Discord embed/table rendering for scan_engine.py's alert pipeline -- turns
a ScanItem (or a stored trade dict) into the actual discord.Embed objects
posted to a channel, plus the two "post this to Discord" notifiers for
closed trades and near-stop/target warnings. Split out of scan_engine.py
because this is pure presentation logic (dict/object in, Embed out) with
no dependency on the scan loop's own crawl/analyze/dedup machinery --
scan_engine.py imports everything here back and calls it exactly as
before, so nothing about `!check`, the automatic scan, or the trade-detail
chart regeneration used by the admin UI changes.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from swingbot.core.market import opex
from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size, load_account_config
from swingbot.core.analytics.rank import follow_breakdown, follow_score
from swingbot.core.marketdata.data import get_currency_symbol, get_daily_data
from swingbot.core.tracking.performance import closed_pnl_pct, closed_r_multiple
from swingbot.core.backtesting.registry import decay_for
from swingbot.core.planning.plan_engine import WEAK_CAUTION_TEXT, badge_stats_line, runner_floor
from swingbot.core.backtesting.registry import Badge
from swingbot.core.scanning import embed_theme as theme
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from . import snapshots
from .snapshots import (_load_scan_snapshots, _save_scan_snapshots,
                        _format_duration_hms, _snapshot_and_diff)
from . import requirements
from .requirements import (RequirementCheck, CONFIDENCE_COLORS,
                           CONFIDENCE_EMOJI, CONFIDENCE_ANSI, confidence_color,
                           _sources_str, _build_requirement_checks, _confidence_block)
from . import plan_table
from .plan_table import (plan_numbers_for_display, _ansi_bad,
                         _build_trade_plan_table, badge_field_for, quality_lines,
                         entry_line, leg_rows, banked_leg_pct_and_amount,
                         partial_position_line, signed_money, _v2_plan)
from . import alert_embeds
from .alert_embeds import build_embed, build_simple_alert
from . import lifecycle_embeds
from .lifecycle_embeds import (regenerate_chart_for_trade, build_closed_trade_embed,
                               notify_closed_trades, build_near_close_embed,
                               notify_near_close, build_plan_event_embed,
                               notify_plan_events)
