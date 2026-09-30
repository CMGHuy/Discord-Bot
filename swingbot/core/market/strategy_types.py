"""
Shared types/constants between strategy.py (the strategy registry +
evaluate_all runner) and signals.py (the individual signal-detection
functions) -- SignalResult, the per-horizon settings (HORIZONS/MIN_BARS),
and a few small threshold constants both files need. Kept in its own
tiny module specifically to avoid a circular import: strategy.py imports
the signal functions FROM signals.py, and signals.py needs SignalResult/
HORIZONS FROM somewhere that isn't strategy.py itself.
"""
from dataclasses import dataclass, field

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
FIB_TOLERANCE_PCT = 2.0  # how close price must be to a fib level, as % of the swing range, to count as "testing" it
SR_VOLUME_MULTIPLE = 1.5  # breakout day volume must exceed this x the 20-day average to count

# v104 Part B: short-only strategies. Named here (market layer) so both
# market/short_entries.py and planning/stop_scope.py can import them without
# market ever importing planning.
V104_SHORTS = ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")
# v113 Part A: short-only and 1w only; masked until its 2026 holdout shot passes.
FADE_STRATEGY = "Downtrend Overbought Fade"
SHORT_STRATEGIES = V104_SHORTS + (FADE_STRATEGY,)

# MACD (fast, slow, signal) periods scaled by horizon -- module-level so
# trade_plan.py can recompute the same fast EMA of price as a pullback
# reference level without the two files drifting out of sync.
MACD_PERIODS_BY_HORIZON = {
    "2w": (8, 17, 9),
    "4w": (12, 26, 9),
    "2m": (12, 26, 9),
    "3m": (19, 39, 9),
    "4m": (21, 43, 9),   # interpolated between 3m and 6m
    "5m": (24, 48, 9),   # interpolated between 3m and 6m
    "6m": (26, 52, 9),
    "7m": (28, 56, 9),   # extrapolated past 6m at the same per-month slope
    "8m": (31, 61, 9),   # extrapolated past 6m at the same per-month slope
    "9m": (33, 65, 9),   # extrapolated past 6m at the same per-month slope
}

# ---------------------------------------------------------------------------
# Horizon definitions -- indicator settings AND risk sizing, per horizon
# ---------------------------------------------------------------------------
HORIZONS = {
    "1w": {
        # v113 §1: fixed by the spec and its pre-registration -- never grid-searched.
        # Masked for every strategy (MASKED_BY_DEFAULT_HORIZONS) until a
        # STRATEGY_GATES "cells" pair admits it; the confluence scan never runs it.
        "label": "3-7 day swing",
        "ema_fast": 5,
        "ema_slow": 8,
        "vwap_window": 5,
        "fib_lookback": 10,
        "sr_lookback": 5,
        "atr_stop_multiple": 1.5,
        "max_risk_pct": 2.0,
        "sr_stop_pct": 2.0,
        "sr_target_min_pct": 2.0,
        "sr_target_max_pct": 5.0,
        "max_holding_days": 7,
        "rs_window": 10,
        # v113 §1: the only horizon with a strategy-plan reward floor
        # (planning/reward_floor.py). Legacy horizons have none, as before v113.
        "min_reward_pct": 2.0,
    },
    "2w": {
        "label": "1-2 week swing",
        "ema_fast": 8,
        "ema_slow": 13,
        "vwap_window": 10,        # ~2 trading weeks
        "fib_lookback": 15,       # ~3 trading weeks of range to draw levels from
        "sr_lookback": 10,        # ~2 trading weeks to establish a support/resistance level
        "atr_stop_multiple": 2.0,  # 2 ATR gives noise room without over-risking; max_risk_pct still caps it
        "max_risk_pct": 3.0,       # stop-loss can't be more than this % away from entry
        "sr_stop_pct": 3.0,
        "sr_target_min_pct": 5.0,  # matches MIN_REWARD_PCT floor -- no point recommending a <5% swing
        "sr_target_max_pct": 8.0,
        "max_holding_days": 14,    # backtest gives up here -- matches the intended hold
        "rs_window": 21,           # ~1 trading month
    },
    "4w": {
        "label": "4-week swing",
        "ema_fast": 9,
        "ema_slow": 21,
        "vwap_window": 21,       # ~1 trading month
        "fib_lookback": 42,      # ~2 trading months of range to draw levels from
        "sr_lookback": 30,
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 7.0,        # O'Neil-style cut-loss ceiling
        "sr_stop_pct": 7.0,
        "sr_target_min_pct": 15.0,
        "sr_target_max_pct": 25.0,  # baseline "sell into strength" zone
        "max_holding_days": 28,
        "rs_window": 21,
    },
    "2m": {
        "label": "2-month swing",
        "ema_fast": 14,
        "ema_slow": 35,
        "vwap_window": 42,       # ~2 trading months
        "fib_lookback": 84,      # ~4 trading months
        "sr_lookback": 60,
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 8.0,
        "sr_stop_pct": 8.0,
        "sr_target_min_pct": 16.0,
        "sr_target_max_pct": 27.0,
        "max_holding_days": 60,
        "rs_window": 42,
    },
    "3m": {
        "label": "3-month swing",
        "ema_fast": 20,
        "ema_slow": 50,
        "vwap_window": 63,       # ~3 trading months
        "fib_lookback": 126,     # ~6 trading months
        "sr_lookback": 90,
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 9.0,
        "sr_stop_pct": 9.0,
        "sr_target_min_pct": 18.0,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 90,
        "rs_window": 63,
    },
    "4m": {
        "label": "4-month swing",
        "ema_fast": 30,
        "ema_slow": 100,
        "vwap_window": 84,       # 21 * 4
        "fib_lookback": 168,     # 42 * 4
        "sr_lookback": 120,      # 30 * 4
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 9.3,
        "sr_stop_pct": 9.3,
        "sr_target_min_pct": 18.7,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 120,  # 30 * 4
        "rs_window": 84,
    },
    "5m": {
        "label": "5-month swing",
        "ema_fast": 40,
        "ema_slow": 150,
        "vwap_window": 105,      # 21 * 5
        "fib_lookback": 210,     # 42 * 5
        "sr_lookback": 150,      # 30 * 5
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 9.7,
        "sr_stop_pct": 9.7,
        "sr_target_min_pct": 19.3,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 150,  # 30 * 5
        "rs_window": 105,
    },
    "6m": {
        "label": "6-month swing",
        "ema_fast": 50,
        "ema_slow": 200,
        "vwap_window": 126,      # ~6 trading months
        "fib_lookback": 252,     # ~12 trading months
        "sr_lookback": 180,
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 10.0,
        "sr_stop_pct": 10.0,
        "sr_target_min_pct": 20.0,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 180,
        "rs_window": 126,
    },
    "7m": {
        "label": "7-month swing",
        "ema_fast": 60,
        "ema_slow": 250,
        "vwap_window": 147,      # 21 * 7
        "fib_lookback": 294,     # 42 * 7
        "sr_lookback": 210,      # 30 * 7
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 10.3,
        "sr_stop_pct": 10.3,
        "sr_target_min_pct": 20.7,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 210,  # 30 * 7
        "rs_window": 147,
    },
    "8m": {
        "label": "8-month swing",
        "ema_fast": 70,
        "ema_slow": 300,
        "vwap_window": 168,      # 21 * 8
        "fib_lookback": 336,     # 42 * 8
        "sr_lookback": 240,      # 30 * 8
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 10.7,
        "sr_stop_pct": 10.7,
        "sr_target_min_pct": 21.3,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 240,  # 30 * 8
        "rs_window": 168,
    },
    "9m": {
        "label": "9-month swing",
        "ema_fast": 80,
        "ema_slow": 350,
        "vwap_window": 189,      # 21 * 9
        "fib_lookback": 378,     # 42 * 9
        "sr_lookback": 270,      # 30 * 9
        "atr_stop_multiple": 2.0,
        "max_risk_pct": 11.0,
        "sr_stop_pct": 11.0,
        "sr_target_min_pct": 22.0,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 270,  # 30 * 9
        "rs_window": 189,
    },
}

# v113 §1: horizons every strategy excludes -- and the confluence scan never
# runs -- until a STRATEGY_GATES "cells" pair admits them (see admits()).
MASKED_BY_DEFAULT_HORIZONS: tuple[str, ...] = ("1w",)
# The ten horizons that existed before v113, in HORIZONS order. Confluence
# scans, scenario replays and every measurement script iterate these, never
# HORIZONS itself (tests/horizon_iteration.py guards it).
LEGACY_HORIZONS: tuple[str, ...] = tuple(key for key in HORIZONS if key not in MASKED_BY_DEFAULT_HORIZONS)

# When a trade's favorable excursion covers this fraction of the distance to
# target, the stop moves to entry (subsequent bars only). Exits at the moved
# stop are "scratch" (~0R), not losses. See backtest.py exit engine.
BREAKEVEN_TRIGGER_FRACTION = 0.5

# Per-strategy gating decided by TRAIN-window tuning (Task 19, train window
# 2020-01-01..2023-12-31, docs/superpowers/results/2026-07-train-tuning.md).
# {"Strategy Name": {"directions": ("bullish",), "horizons": ("4w", "2m")}}
# A missing key means both directions, all LEGACY horizons. v113 §2: an optional
# "cells" set of (direction, horizon) pairs is admitted IN ADDITION to what the
# legacy axes admit; it is the only way to admit a MASKED_BY_DEFAULT horizon.
# admits() is the rule; entry_filters.entries_for is its reader, so backtest
# and live signals both respect it.
#
# EMA Crossover and Elliott Wave are left ungated deliberately. The pre-v31
# numbers that justified this (EMA Crossover bullish+4w reaching only N=28;
# Elliott Wave firing only on 4w at WR=74.1 ExpR=-0.001) were measured against
# the fixed per-strategy reward:risk table plan v31 deleted -- see v84
# (docs/superpowers/specs/implemented/2026-09-10-v84-strategy-rescue-v2-design.md). Under
# current arithmetic EMA Crossover's pooled TRAIN scores WR 61.8% ExpR +0.494
# ungated (N=55), but its per-fold-year stability check failed (1 of 3 years
# clears N>=15) -- CLOSED, stays WEAK, not gated here either
# (results/2026-09-10-v84-ema-crossover-preregistration.md). Elliott Wave's
# proposed v84 rescue was withdrawn -- both retracement-depth validation and
# volume confirmation already ship (spec 4.8).
# NOTE: every WR/ExpR figure in the per-key comments below is likewise pre-v31
# and stale. Only the "Break & Retest" entry was derived under current
# arithmetic.
STRATEGY_GATES: dict[str, dict] = {
    # bullish-only: N=286 WR=81.8 ExpR=+0.106 excl=27% (train, PRE-v31 -- stale)
    "Fibonacci": {"directions": ("bullish",)},
    # v103 C ships masked until a direction passes its pre-registered shot.
    "Fibonacci Continuation": {"directions": ()},
    # v104 Part B shorts ship masked until their 2026 holdout shot passes.
    "Bull Trap": {"directions": ()},
    "Vol Expansion Breakdown": {"directions": ()},
    "Earnings Gap Drift": {"directions": ()},
    # v113 Part A ships masked; a holdout pass would admit it as
    # "cells": {("bearish", "1w")} -- see the v113 plan's V113-24.
    "Downtrend Overbought Fade": {"directions": ()},
    # bullish-only: N=608 WR=85.2 ExpR=+0.140 excl=28% (train, PRE-v31 -- stale)
    "RSI": {"directions": ("bullish",)},
    # bullish-only: N=259 WR=81.1 ExpR=+0.071 excl=25% (train, PRE-v31 -- stale)
    "MA Ribbon": {"directions": ("bullish",)},
    # v84 R11, CURRENT arithmetic (v2 + scale-out): the pre-v31 five-horizon
    # mask was never re-derived after v31 replaced the fixed reward:risk table.
    # 4w alone: N=68 WR=52.9 ExpR=+0.335. The dropped horizons were 6m 35.7
    # (-0.078), 7m 40.0, 8m 38.5, 9m 11.1 (N=9, -0.519).
    "VWAP": {"directions": ("bullish",), "horizons": ("4w",)},
    # bullish + {2m,3m}: N=273 WR=80.6 ExpR=+0.060 excl=32% (train, PRE-v31 -- stale)
    "Support/Resistance": {"directions": ("bullish",), "horizons": ("2m", "3m")},
    # bullish + {3m,4m,7m,8m,9m}: N=145 WR=83.4 ExpR=+0.094 excl=26% (train, PRE-v31 -- stale)
    "MACD": {"directions": ("bullish",), "horizons": ("3m", "4m", "7m", "8m", "9m")},
    # bullish + {7m}: N=73 WR=82.2 ExpR=+0.106 excl=30% (train, PRE-v31 -- stale)
    "Volume Profile": {"directions": ("bullish",), "horizons": ("7m",)},
    # v84 R7, CURRENT arithmetic (v2 + scale-out): the pooled TRAIN row fails
    # (WR 48.0 N=298) but splits bimodally by horizon -- 2m/3m/4m clear the
    # floor (53.1/57.1/51.4) while 6m is the only negative-ExpR cell
    # (27.8, -0.157). Gated subset: N=105 WR=53.3 ExpR=+0.31, plateau-verified
    # against 4 neighbouring horizon subsets (all 4 also clear WR>=50, N>=30).
    # Both directions kept -- only the horizon axis was pre-registered.
    "Break & Retest": {"horizons": ("2m", "3m", "4m")},
}


def admits(strategy: str, direction: str, horizon_key: str) -> bool:
    """v113 §2: THE mask rule. A (direction, horizon) pair is admitted when it
    is in the strategy's "cells", or when the horizon is not masked by default
    and the legacy axes (directions, horizons, horizons_by_direction) admit it.
    With no "cells" anywhere this is exactly the pre-v113 rule on every legacy
    horizon (pinned by tests/market/test_v113_horizon.py)."""
    gates = STRATEGY_GATES.get(strategy) or {}
    if (direction, horizon_key) in gates.get("cells", ()):
        return True
    if horizon_key in MASKED_BY_DEFAULT_HORIZONS:
        return False
    directions = gates.get("directions")
    if directions is not None and direction not in directions:
        return False
    permitted = (gates.get("horizons_by_direction") or {}).get(direction, gates.get("horizons"))
    return permitted is None or horizon_key in permitted


def live_horizons() -> tuple[str, ...]:
    """The strategy vocabulary, in HORIZONS order: LEGACY_HORIZONS plus any
    masked-by-default horizon at least one "cells" pair admits. Read at call
    time, so a cell shipped in code (or a test's gate_override) shows up in
    commands, the admin UI and the live strategy pass without another edit."""
    admitted = {hk for gates in STRATEGY_GATES.values() for _direction, hk in gates.get("cells", ())}
    return tuple(key for key in HORIZONS if key not in MASKED_BY_DEFAULT_HORIZONS or key in admitted)

# Minimum bars of history required for each horizon's slowest calculation
MIN_BARS = {
    "1w": 20,   # v113: the 2w floor already covers every 1w lookback (<= 10) and the 20-bar volume mean
    "2w": 20,
    "4w": 45,
    "2m": 75,
    "3m": 130,
    "4m": 173,
    "5m": 217,
    "6m": 260,
    "7m": 303,
    "8m": 347,
    "9m": 390,
}


@dataclass
class SignalResult:
    ticker: str
    strategy: str          # "EMA Crossover" | "VWAP" | "Fibonacci"
    horizon_key: str        # "1m" | "3m" | "6m"
    horizon_label: str
    trend: str              # "bullish" | "bearish"
    triggered: bool          # True if this is a fresh, alert-worthy signal
    close: float
    details: dict = field(default_factory=dict)  # strategy-specific numbers for the embed

    @property
    def state_key(self) -> str:
        return f"{self.ticker}|{self.strategy}|{self.horizon_key}"

    @property
    def state_value(self) -> str:
        """
        Value compared against the last stored state to decide whether this
        is a "new" signal worth alerting on. For EMA/VWAP, the trend itself
        is enough (only alert on a flip). For Fibonacci, we also fold in
        which level is being tested, so a bounce off the 61.8% level still
        alerts even if the last alert was also bullish (e.g. off the 38.2%).
        """
        if self.strategy == "Fibonacci" and "Nearest level" in self.details:
            return f"{self.trend}:{self.details['Nearest level']}"
        return self.trend


# Per-strategy allowed regimes (E24 mechanism; E33's fold runs decide the
# actual sets). Missing key = allowed in every regime. Both the backtest
# and live signals flow through entry_filters.apply_regime_gate, so the
# gate can never diverge between them.
REGIME_ALLOW: dict[str, tuple] = {}

