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
    "6m": (26, 52, 9),
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
}

# Minimum bars of history required for each horizon's slowest calculation
MIN_BARS = {
    "2w": 20,
    "4w": 45,
    "2m": 75,
    "3m": 130,
    "6m": 260,
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

