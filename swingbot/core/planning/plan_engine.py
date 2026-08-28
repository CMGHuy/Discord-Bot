"""Unified trade-plan engine v2.

Single authority for plan construction and exit policy (spec:
docs/superpowers/specs/implemented/2026-07-11-v2-unified-plan-engine-design.md).
Everything that emits a trade plan — scan alerts, strategy signals,
backtests, the live plan manager — builds and prices it here.
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from dataclasses import dataclass, field

import numpy as np

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market import opex
from swingbot.core.market.levels import MAX_TARGET2_LEG_MULTIPLE
from swingbot.core.backtesting.registry import Badge, decay_note, get_badge
from swingbot.core.market.strategy_types import (
    BREAKEVEN_TRIGGER_FRACTION,
    HORIZONS,
)
from .plan_types import (PlanStatus, TradePlanV2, effective_stop, plan_to_dict,
                         plan_from_dict, record_transition)
from . import params
from . import targets
from . import lifecycle
from . import exit_sim
from . import builders
from .builders import (_atr_plan, _fibonacci_plan, _sr_plan, _elliott_plan,
                       build_strategy_plan, scenario_is_breakout,
                       primary_strategy_for, build_confluence_plan,
                       entry_type_for)
from .exit_sim import (ExitResult, _not_triggered, _single_leg_exit_walk,
                       chandelier_stop, runner_floor, _scale_out_exit_walk,
                       simulate_exit)
from .lifecycle import (_lifecycle_levels, apply_level_lifecycle, trigger_hit,
                        fill_price, pending_expired, pending_invalidated)
from .targets import (select_structural_target, _safe_atr_value,
                      atr_target_candidates, fib_target_candidates,
                      sr_target_candidates, elliott_target_candidates,
                      select_tp2, _tp2_from_r)
from .params import (EXIT_V2_PARAMS, STRUCTURE_BUFFER_ATR, SR_VOLUME_STRENGTH_CEILING,
                     TRAIL_ATR_MULT, TP1_FRACTION, RUNNER_FLOOR_FRACTION,
                     DEFAULT_EXPIRY_BARS, exit_params_for,
                     _journal_entries, _resolve_stop_mult, _resolve_tp2_r,
                     _resolve_time_stop_days, _apply_quality, stamp_badge,
                     badge_stats_line)
