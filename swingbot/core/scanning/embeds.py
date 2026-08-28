"""Compatibility facade for scanning Discord presentation helpers.

Implementations are split by responsibility; this module intentionally preserves
the stable legacy import surface for commands, tests, and the scanning facade.
"""
from . import alert_embeds, lifecycle_embeds, plan_table, requirements, snapshots
from .alert_embeds import build_embed, build_simple_alert
from .lifecycle_embeds import (build_closed_trade_embed, build_near_close_embed,
                               build_plan_event_embed, notify_closed_trades,
                               notify_near_close, notify_plan_events,
                               regenerate_chart_for_trade)
from .plan_table import (badge_field_for, banked_leg_pct_and_amount, entry_line,
                         leg_rows, partial_position_line, plan_numbers_for_display,
                         quality_lines, signed_money)
from .requirements import RequirementCheck, _build_requirement_checks, _sources_str

__all__ = [
    "RequirementCheck", "_sources_str", "_build_requirement_checks",
    "plan_numbers_for_display", "badge_field_for", "quality_lines", "entry_line", "leg_rows",
    "banked_leg_pct_and_amount", "partial_position_line", "signed_money",
    "build_embed", "build_simple_alert", "regenerate_chart_for_trade",
    "build_closed_trade_embed", "notify_closed_trades", "build_near_close_embed",
    "notify_near_close", "build_plan_event_embed", "notify_plan_events",
]
