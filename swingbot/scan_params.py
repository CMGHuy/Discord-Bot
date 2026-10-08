"""The trade-plan decision surface as one frozen, passable value.

Config is module globals that reload() mutates in place on SIGHUP. A grid
that varies a knob by mutating those globals lets workers fight over shared
state. ``ScanParams`` is the alternative: build it at the boundary with
``from_config()``, vary it with ``dataclasses.replace()``, and pass it down.

Frozen and tuple-only so it is hashable and picklable -- v75 scores grid cells
in a process pool and each cell is one of these.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from swingbot import config

#: Mirrors swingbot.core.market.fvg.FVG_MODES (pinned equal by
#: tests/test_config_fvg_mode.py); duplicated so this module stays import-light.
_FVG_MODES = ("all", "displacement", "off")


def _validate_fvg(mode, k) -> None:
    """A replace()d ScanParams must never carry an arm the config layer would refuse."""
    if mode not in _FVG_MODES:
        raise ValueError(f"fvg_levels_mode must be one of {_FVG_MODES}, got {mode!r}")
    if not isinstance(k, (int, float)) or not math.isfinite(k) or k <= 0:
        raise ValueError(f"fvg_displacement_atr_k must be a finite number > 0, got {k!r}")


@dataclass(frozen=True)
class ScanParams:
    """Every injectable trade-plan decision parameter."""

    min_reward_pct: float
    min_stop_distance_pct: float
    max_stop_loss_pct: float
    confluence_deviation_pct: float
    min_target_confluence_count: int
    min_alert_confidence_level: str
    unified_confidence: bool
    dedup_tolerance_pct: float
    max_alerts_per_scan: int
    earnings_blackout_sessions: int
    rs_gate: bool
    rs_leader_percentile: float
    rs_laggard_percentile: float
    htf_confluence_enabled: bool
    mtf_adjacent_gate: bool
    opex_caution_enabled: bool
    opex_monthly_confidence_bump: float
    opex_monthly_confluence_bump: float
    opex_weekly_confluence_bump: float
    opex_stop_widen_pct: float
    opex_size_reduction_pct: float
    avwap_levels_enabled: bool
    volume_profile_nodes_enabled: bool
    level_lifecycle_stops_enabled: bool
    data_driven_stops_enabled: bool
    adaptive_runner_trail_enabled: bool
    tighten_trigger_r: float
    tighten_atr_mult: float
    stall_exit_enabled: bool
    regime_gates_enabled: bool
    pyramiding_enabled: bool
    plan_engine_v2: bool
    scale_out_enabled: bool
    universe_min_dollar_vol: float
    universe_min_price: float
    dead_cat_bounce_veto: bool
    dcb_decline_pct: float
    dcb_gap_required: bool
    dcb_volume_ratio: float
    min_risk_reward_ratio: float
    max_risk_reward_ratio: float
    slippage_bps: float
    commission_per_trade: float
    commission_risk_basis: str
    rsi_div_min_consecutive_turn: int
    ma_ribbon_confirm_bars: int
    sr_min_level_touches: int
    fib_target_1_0_extension: bool
    runner_structure_exit: str
    runner_hl_trail_atr_buffer: float
    runner_stall_range_max: float
    pullback_dryup_scope: str
    pullback_dryup_max_ratio: float
    short_universe_research_mode: str = "off"   # v118 research replay only
    compression_short_research_mode: str = "off"   # v119 research replay only
    fvg_levels_mode: str = "all"            # v128: all | displacement | off
    fvg_displacement_atr_k: float = 1.5     # v128: read only in displacement mode

    def __post_init__(self):
        _validate_fvg(self.fvg_levels_mode, self.fvg_displacement_atr_k)

    @classmethod
    def from_config(cls) -> "ScanParams":
        """Build the live default, reading each config global once."""
        return cls(
            min_reward_pct=config.MIN_REWARD_PCT,
            min_stop_distance_pct=config.MIN_STOP_DISTANCE_PCT,
            max_stop_loss_pct=config.MAX_STOP_LOSS_PCT,
            confluence_deviation_pct=config.CONFLUENCE_DEVIATION_PCT,
            min_target_confluence_count=config.MIN_TARGET_CONFLUENCE_COUNT,
            min_alert_confidence_level=config.MIN_ALERT_CONFIDENCE_LEVEL,
            unified_confidence=config.UNIFIED_CONFIDENCE,
            dedup_tolerance_pct=config.DEDUP_TOLERANCE_PCT,
            max_alerts_per_scan=config.MAX_ALERTS_PER_SCAN,
            earnings_blackout_sessions=config.EARNINGS_BLACKOUT_SESSIONS,
            rs_gate=config.RS_GATE,
            rs_leader_percentile=config.RS_LEADER_PERCENTILE,
            rs_laggard_percentile=config.RS_LAGGARD_PERCENTILE,
            htf_confluence_enabled=config.HTF_CONFLUENCE_ENABLED,
            mtf_adjacent_gate=config.MTF_ADJACENT_GATE,
            opex_caution_enabled=config.OPEX_CAUTION_ENABLED,
            opex_monthly_confidence_bump=config.OPEX_MONTHLY_CONFIDENCE_BUMP,
            opex_monthly_confluence_bump=config.OPEX_MONTHLY_CONFLUENCE_BUMP,
            opex_weekly_confluence_bump=config.OPEX_WEEKLY_CONFLUENCE_BUMP,
            opex_stop_widen_pct=config.OPEX_STOP_WIDEN_PCT,
            opex_size_reduction_pct=config.OPEX_SIZE_REDUCTION_PCT,
            avwap_levels_enabled=config.AVWAP_LEVELS_ENABLED,
            volume_profile_nodes_enabled=config.VOLUME_PROFILE_NODES_ENABLED,
            level_lifecycle_stops_enabled=config.LEVEL_LIFECYCLE_STOPS_ENABLED,
            data_driven_stops_enabled=config.DATA_DRIVEN_STOPS_ENABLED,
            adaptive_runner_trail_enabled=config.ADAPTIVE_RUNNER_TRAIL_ENABLED,
            tighten_trigger_r=config.TIGHTEN_TRIGGER_R,
            tighten_atr_mult=config.TIGHTEN_ATR_MULT,
            stall_exit_enabled=config.STALL_EXIT_ENABLED,
            regime_gates_enabled=config.REGIME_GATES_ENABLED,
            pyramiding_enabled=config.PYRAMIDING_ENABLED,
            plan_engine_v2=config.PLAN_ENGINE_V2,
            scale_out_enabled=config.SCALE_OUT_ENABLED,
            universe_min_dollar_vol=config.UNIVERSE_MIN_DOLLAR_VOL,
            universe_min_price=config.UNIVERSE_MIN_PRICE,
            dead_cat_bounce_veto=config.DEAD_CAT_BOUNCE_VETO,
            dcb_decline_pct=config.DCB_DECLINE_PCT,
            dcb_gap_required=config.DCB_GAP_REQUIRED,
            dcb_volume_ratio=config.DCB_VOLUME_RATIO,
            min_risk_reward_ratio=config.MIN_RISK_REWARD_RATIO,
            max_risk_reward_ratio=config.MAX_RISK_REWARD_RATIO,
            slippage_bps=config.SLIPPAGE_BPS,
            commission_per_trade=config.COMMISSION_PER_TRADE,
            commission_risk_basis=config.COMMISSION_RISK_BASIS,
            rsi_div_min_consecutive_turn=config.RSI_DIV_MIN_CONSECUTIVE_TURN,
            ma_ribbon_confirm_bars=config.MA_RIBBON_CONFIRM_BARS,
            sr_min_level_touches=config.SR_MIN_LEVEL_TOUCHES,
            fib_target_1_0_extension=config.FIB_TARGET_1_0_EXTENSION,
            runner_structure_exit=config.RUNNER_STRUCTURE_EXIT,
            runner_hl_trail_atr_buffer=config.RUNNER_HL_TRAIL_ATR_BUFFER,
            runner_stall_range_max=config.RUNNER_STALL_RANGE_MAX,
            pullback_dryup_scope=config.PULLBACK_DRYUP_SCOPE,
            pullback_dryup_max_ratio=config.PULLBACK_DRYUP_MAX_RATIO,
            short_universe_research_mode=config.SHORT_UNIVERSE_RESEARCH_MODE,
            compression_short_research_mode=config.COMPRESSION_SHORT_RESEARCH_MODE,
            fvg_levels_mode=config.FVG_LEVELS_MODE,
            fvg_displacement_atr_k=config.FVG_DISPLACEMENT_ATR_K,
        )
