"""!check, !session, !status, and the automatic background session-scan loop."""
import asyncio
import datetime as dt
import json
import os
import random
import time

import discord
from discord.ext import tasks

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.analytics.rank import rank_plans
from swingbot.bot_core import bot, in_session, log, SESSION_TZ, install_reload_signal_handler, on_config_reload
from swingbot.core.marketdata.data import get_current_price
from swingbot.core.infra.silent_channel import silence
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.marketdata.watchlist import load_watchlist
from . import runstate
from . import loops
from . import alerts
from . import commands
from . import presence
from . import recap
from .alerts import _ordered_alerts, _send_alerts, cap_alerts, deep_scan_report, digest_payload, route_channel_id
from .commands import check_cmd
from .recap import weekend_deep_scan
from .runstate import _HEARTBEAT_FILE, _MANUAL_CLOSE_QUEUE, _PAUSE_FILE, _TRIGGER_FILE
from .loops import _apply_scan_interval_change, _apply_market_data_refresh_config, _session_scan_tick, config_watcher, daily_recap, heartbeat, market_data_refresh, on_ready, session_scan, trade_monitor, weekend_deep_scan_task

# Historical !check results are summaries, not an export. Keep enough for a
# useful review while avoiding a burst of Discord sends for broad date ranges.
_HISTORICAL_CHECK_MAX_RESULTS = 90
_DISCORD_MESSAGE_LIMIT = 1900





