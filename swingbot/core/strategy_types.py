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
    "2w": {
        "label": "1-2 week swing",
        "ema_fast": 8,
        "ema_slow": 13,
        "vwap_window": 10,        # ~2 trading weeks
        "fib_lookback": 15,       # ~3 trading weeks of range to draw levels from
        "sr_lookback": 10,        # ~2 trading weeks to establish a support/resistance level
        "atr_stop_multiple": 2.0,  # 2 ATR gives noise room without over-risking; max_risk_pct still caps it
        "reward_risk_ratio": 0.40, # 2w: tight target for high win rate (0.4R target vs 1R stop)
        "min_structure_rr": 0.35, # Fibonacci/Elliott: tight target → higher win rate
        "max_structure_rr": 0.40,
        "max_risk_pct": 3.0,       # stop-loss can't be more than this % away from entry
        "sr_stop_pct": 3.0,
        "sr_target_min_pct": 5.0,  # matches MIN_REWARD_PCT floor -- no point recommending a <5% swing
        "sr_target_max_pct": 8.0,
        "max_holding_days": 14,    # backtest gives up here -- matches the intended hold
    },
    "4w": {
        "label": "4-week swing",
        "ema_fast": 9,
        "ema_slow": 21,
        "vwap_window": 21,       # ~1 trading month
        "fib_lookback": 42,      # ~2 trading months of range to draw levels from
        "sr_lookback": 30,
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 0.50,  # 4w: moderate target, balances win rate vs profit
        "min_structure_rr": 0.40,
        "max_structure_rr": 0.50,
        "max_risk_pct": 7.0,        # O'Neil-style cut-loss ceiling
        "sr_stop_pct": 7.0,
        "sr_target_min_pct": 15.0,
        "sr_target_max_pct": 25.0,  # baseline "sell into strength" zone
        "max_holding_days": 28,
    },
    "2m": {
        "label": "2-month swing",
        "ema_fast": 14,
        "ema_slow": 35,
        "vwap_window": 42,       # ~2 trading months
        "fib_lookback": 84,      # ~4 trading months
        "sr_lookback": 60,
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 0.60, # 2m: moderate R:R
        "min_structure_rr": 0.45,
        "max_structure_rr": 0.60,
        "max_risk_pct": 8.0,
        "sr_stop_pct": 8.0,
        "sr_target_min_pct": 16.0,
        "sr_target_max_pct": 27.0,
        "max_holding_days": 60,
    },
    "3m": {
        "label": "3-month swing",
        "ema_fast": 20,
        "ema_slow": 50,
        "vwap_window": 63,       # ~3 trading months
        "fib_lookback": 126,     # ~6 trading months
        "sr_lookback": 90,
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 0.75,  # 3m: moderate R:R for medium-term holds
        "min_structure_rr": 0.55,
        "max_structure_rr": 0.75,
        "max_risk_pct": 9.0,
        "sr_stop_pct": 9.0,
        "sr_target_min_pct": 18.0,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 90,
    },
    "4m": {
        "label": "4-month swing",
        "ema_fast": 30,
        "ema_slow": 100,
        "vwap_window": 84,       # 21 * 4
        "fib_lookback": 168,     # 42 * 4
        "sr_lookback": 120,      # 30 * 4
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 0.83,  # interpolated between 3m and 6m
        "min_structure_rr": 0.60,
        "max_structure_rr": 0.83,
        "max_risk_pct": 9.3,
        "sr_stop_pct": 9.3,
        "sr_target_min_pct": 18.7,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 120,  # 30 * 4
    },
    "5m": {
        "label": "5-month swing",
        "ema_fast": 40,
        "ema_slow": 150,
        "vwap_window": 105,      # 21 * 5
        "fib_lookback": 210,     # 42 * 5
        "sr_lookback": 150,      # 30 * 5
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 0.92,  # interpolated between 3m and 6m
        "min_structure_rr": 0.65,
        "max_structure_rr": 0.92,
        "max_risk_pct": 9.7,
        "sr_stop_pct": 9.7,
        "sr_target_min_pct": 19.3,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 150,  # 30 * 5
    },
    "6m": {
        "label": "6-month swing",
        "ema_fast": 50,
        "ema_slow": 200,
        "vwap_window": 126,      # ~6 trading months
        "fib_lookback": 252,     # ~12 trading months
        "sr_lookback": 180,
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 1.00,  # 6m: wider target to capture the full multi-month move
        "min_structure_rr": 0.70,
        "max_structure_rr": 1.00,
        "max_risk_pct": 10.0,
        "sr_stop_pct": 10.0,
        "sr_target_min_pct": 20.0,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 180,
    },
    "7m": {
        "label": "7-month swing",
        "ema_fast": 60,
        "ema_slow": 250,
        "vwap_window": 147,      # 21 * 7
        "fib_lookback": 294,     # 42 * 7
        "sr_lookback": 210,      # 30 * 7
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 1.08,  # extrapolated past 6m at the same slope
        "min_structure_rr": 0.75,
        "max_structure_rr": 1.08,
        "max_risk_pct": 10.3,
        "sr_stop_pct": 10.3,
        "sr_target_min_pct": 20.7,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 210,  # 30 * 7
    },
    "8m": {
        "label": "8-month swing",
        "ema_fast": 70,
        "ema_slow": 300,
        "vwap_window": 168,      # 21 * 8
        "fib_lookback": 336,     # 42 * 8
        "sr_lookback": 240,      # 30 * 8
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 1.17,  # extrapolated past 6m at the same slope
        "min_structure_rr": 0.80,
        "max_structure_rr": 1.17,
        "max_risk_pct": 10.7,
        "sr_stop_pct": 10.7,
        "sr_target_min_pct": 21.3,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 240,  # 30 * 8
    },
    "9m": {
        "label": "9-month swing",
        "ema_fast": 80,
        "ema_slow": 350,
        "vwap_window": 189,      # 21 * 9
        "fib_lookback": 378,     # 42 * 9
        "sr_lookback": 270,      # 30 * 9
        "atr_stop_multiple": 2.0,
        "reward_risk_ratio": 1.25,  # extrapolated past 6m at the same slope
        "min_structure_rr": 0.85,
        "max_structure_rr": 1.25,
        "max_risk_pct": 11.0,
        "sr_stop_pct": 11.0,
        "sr_target_min_pct": 22.0,
        "sr_target_max_pct": 30.0,
        "max_holding_days": 270,  # 30 * 9
    },
}

# ---------------------------------------------------------------------------
# Reward:risk per strategy -- SINGLE SOURCE for backtest.py AND trade_plan.py.
# HARD FLOOR 0.30: break-even win rate at R:R=X is 1/(1+X); at 0.30 that is
# 76.9%, so an 80% win rate is profitable. Below 0.30 a strategy can clear
# 80% win rate and still lose money -- never tune below the floor.
# Mean-reversion-at-structure strategies get 0.40 (they enter at a level, so
# the bounce has room); trend/breakout strategies get 0.35.
# ---------------------------------------------------------------------------
STRATEGY_RR_OVERRIDE: dict[str, float] = {
    "EMA Crossover":      0.35,
    "VWAP":               0.35,
    "Fibonacci":          0.40,
    "Support/Resistance": 0.35,
    "RSI":                0.40,
    "MACD":               0.35,
    "Elliott Wave":       0.35,
    "MA Ribbon":          0.35,
    "Break & Retest":     0.35,
    "RSI Divergence":     0.40,
    "Volume Profile":     0.40,
}

# When a trade's favorable excursion covers this fraction of the distance to
# target, the stop moves to entry (subsequent bars only). Exits at the moved
# stop are "scratch" (~0R), not losses. See backtest.py exit engine.
BREAKEVEN_TRIGGER_FRACTION = 0.5

# Per-strategy gating decided by TRAIN-window tuning (Task 19, train window
# 2020-01-01..2023-12-31, docs/superpowers/results/2026-07-train-tuning.md).
# {"Strategy Name": {"directions": ("bullish",), "horizons": ("4w", "2m")}}
# A missing key means both directions, all horizons. entry_filters.entries_for
# applies the mask, so backtest and live signals both respect it.
#
# EMA Crossover and Elliott Wave could not be gated to a passing train config
# (best reachable subset: EMA Crossover bullish+4w only reaches N=28 < 30;
# Elliott Wave only fires on 4w and bullish-only there is WR=74.1 ExpR=-0.001)
# -- left ungated and documented as FAILING in the results doc.
STRATEGY_GATES: dict[str, dict] = {
    # bullish-only: N=286 WR=81.8 ExpR=+0.106 excl=27% (train)
    "Fibonacci": {"directions": ("bullish",)},
    # bullish-only: N=608 WR=85.2 ExpR=+0.140 excl=28% (train)
    "RSI": {"directions": ("bullish",)},
    # bullish-only: N=259 WR=81.1 ExpR=+0.071 excl=25% (train)
    "MA Ribbon": {"directions": ("bullish",)},
    # bullish + {4w,6m,7m,8m,9m}: N=139 WR=82.0 ExpR=+0.086 excl=20% (train)
    "VWAP": {"directions": ("bullish",), "horizons": ("4w", "6m", "7m", "8m", "9m")},
    # bullish + {2m,3m}: N=273 WR=80.6 ExpR=+0.060 excl=32% (train)
    "Support/Resistance": {"directions": ("bullish",), "horizons": ("2m", "3m")},
    # bullish + {3m,4m,7m,8m,9m}: N=145 WR=83.4 ExpR=+0.094 excl=26% (train)
    "MACD": {"directions": ("bullish",), "horizons": ("3m", "4m", "7m", "8m", "9m")},
    # bullish + {7m}: N=73 WR=82.2 ExpR=+0.106 excl=30% (train)
    "Volume Profile": {"directions": ("bullish",), "horizons": ("7m",)},
}

# Minimum bars of history required for each horizon's slowest calculation
MIN_BARS = {
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

