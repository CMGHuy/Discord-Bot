"""
Account config storage (balance / risk % / max open positions, editable
via `!account`) and unrealized P/L tracking for `!pnl`.

Position sizing is computed by compute_position_size() using the classic
fixed-fractional formula:

    risk_amount = balance x risk_pct / 100
    shares      = risk_amount / abs(entry - stop_loss)

A MAX_POSITION_SIZE_PCT cap prevents the position from consuming too
large a fraction of the account (e.g. a tiny stop on a cheap stock
could otherwise suggest a very large share count). The result is shown
in every Discord alert embed as "Suggested size" -- informational, not
executed automatically. Actual trade sizing is always the trader's call.
"""
import json
import os
from dataclasses import dataclass

from swingbot import config as app_config

CONFIG_PATH = os.path.join(app_config.DATA_DIR, "account.json")


def load_account_config(path: str = CONFIG_PATH) -> dict:
    # Canonical defaults -- every key that exists in the account config schema.
    # Used both as the seed for a brand-new account.json AND as a fallback for
    # keys that were added after an existing file was first created (so loading
    # an old file never returns a dict that's missing a key downstream code
    # assumes will be there).
    defaults = {
        "balance":            app_config.ACCOUNT_BALANCE,
        "risk_pct":           app_config.RISK_PER_TRADE_PCT,
        "max_open_positions": app_config.MAX_OPEN_POSITIONS,
        "max_position_pct":   app_config.MAX_POSITION_SIZE_PCT,
    }
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                stored = json.load(f)
                # Merge: stored values win over defaults, but any key that
                # doesn't exist in the stored file gets the default value.
                return {**defaults, **stored}
            except json.JSONDecodeError:
                pass
    save_account_config(defaults, path)
    return dict(defaults)


def save_account_config(config: dict, path: str = CONFIG_PATH):
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def set_balance(balance: float, path: str = CONFIG_PATH) -> dict:
    config = load_account_config(path)
    config["balance"] = balance
    save_account_config(config, path)
    return config


def set_risk_pct(risk_pct: float, path: str = CONFIG_PATH) -> dict:
    config = load_account_config(path)
    config["risk_pct"] = risk_pct
    save_account_config(config, path)
    return config


def set_max_open_positions(max_open: int, path: str = CONFIG_PATH) -> dict:
    config = load_account_config(path)
    config["max_open_positions"] = max_open
    save_account_config(config, path)
    return config


def set_max_position_pct(max_pct: float, path: str = CONFIG_PATH) -> dict:
    config = load_account_config(path)
    config["max_position_pct"] = max_pct
    save_account_config(config, path)
    return config


def compute_position_size(entry: float, stop_loss: float, account_cfg: dict = None) -> dict | None:
    """
    Fixed-fractional position sizing: risk a fixed % of account balance
    per trade, sized so a full stop-out costs exactly that amount.

    Formula:
        risk_amount    = balance x risk_pct / 100
        raw_shares     = risk_amount / abs(entry - stop_loss)
        position_value = raw_shares x entry

    If position_value would exceed balance x max_position_pct/100, shares
    are capped at that maximum and `capped` is True in the result.

    Returns None when balance <= 0, entry <= 0, or stop distance is zero.

    Return dict keys:
        shares          -- suggested whole/fractional share count
        risk_amount     -- currency at risk if stop-loss is hit
        position_value  -- total capital deployed (shares x entry)
        capped          -- True if position_value was capped
        balance         -- account balance used in calculation
        risk_pct        -- risk % used
        max_position_pct -- position size cap % used
    """
    if account_cfg is None:
        account_cfg = load_account_config()

    balance = float(account_cfg.get("balance", 0))
    risk_pct = float(account_cfg.get("risk_pct", 1.0))
    max_position_pct = float(account_cfg.get("max_position_pct", app_config.MAX_POSITION_SIZE_PCT))

    if balance <= 0 or entry <= 0:
        return None

    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return None

    risk_amount = balance * risk_pct / 100.0
    raw_shares = risk_amount / stop_distance
    position_value = raw_shares * entry
    max_position_value = balance * max_position_pct / 100.0

    capped = False
    if position_value > max_position_value:
        raw_shares = max_position_value / entry
        position_value = max_position_value
        capped = True

    return {
        "shares":           round(raw_shares, 2),
        "risk_amount":      round(risk_amount, 2),
        "position_value":   round(position_value, 2),
        "capped":           capped,
        "balance":          balance,
        "risk_pct":         risk_pct,
        "max_position_pct": max_position_pct,
    }


@dataclass
class UnrealizedPnL:
    current_price: float
    pct_change: float           # positive = in profit, negative = in loss, relative to entry
    distance_to_sl_pct: float   # how close (in %) current price is to the stop-loss
    distance_to_tp_pct: float   # how close (in %) current price is to the recommended TP


def compute_unrealized_pnl(entry: float, stop_loss: float, take_profit: float, direction: str,
                            current_price: float) -> UnrealizedPnL:
    """Mark-to-market % P/L for a still-open paper trade, given the current market price."""
    if entry <= 0:
        return UnrealizedPnL(current_price=current_price, pct_change=0.0,
                             distance_to_sl_pct=0.0, distance_to_tp_pct=0.0)

    is_bull = direction == "bullish"
    sign = 1 if is_bull else -1
    pct_change = (current_price - entry) / entry * sign * 100

    distance_to_sl_pct = abs(current_price - stop_loss) / current_price * 100 if current_price else 0.0
    distance_to_tp_pct = abs(take_profit - current_price) / current_price * 100 if current_price else 0.0

    return UnrealizedPnL(
        current_price=round(current_price, 4),
        pct_change=round(pct_change, 2),
        distance_to_sl_pct=round(distance_to_sl_pct, 2),
        distance_to_tp_pct=round(distance_to_tp_pct, 2),
    )
