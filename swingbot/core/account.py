"""
Account config storage (balance / risk % / max open positions, editable
via `!account`) and unrealized P/L tracking for `!pnl`.

There is no euro-based position sizing anymore -- no flat stake, no
fixed max-loss band. The bot's focus is finding a qualifying
support/resistance setup (see levels.py); how many shares/how much
capital to actually put behind it is left entirely up to the person
placing the trade. `!account` settings are kept around only in case a
future feature wants them again -- nothing in the live alert pipeline
reads risk_pct/balance right now.
"""
import json
import os
from dataclasses import dataclass

from swingbot import config as app_config

CONFIG_PATH = os.path.join(app_config.DATA_DIR, "account.json")


def load_account_config(path: str = CONFIG_PATH) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    # Read live from app_config (not frozen module-level constants) so a
    # config.reload() is reflected the first time account.json gets seeded.
    config = {
        "balance": app_config.ACCOUNT_BALANCE,
        "risk_pct": app_config.RISK_PER_TRADE_PCT,
        "max_open_positions": app_config.MAX_OPEN_POSITIONS,
    }
    save_account_config(config, path)
    return config


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


@dataclass
class UnrealizedPnL:
    current_price: float
    pct_change: float           # positive = in profit, negative = in loss, relative to entry
    distance_to_sl_pct: float    # how close (in %) current price is to the stop-loss
    distance_to_tp_pct: float    # how close (in %) current price is to the recommended TP


def compute_unrealized_pnl(entry: float, stop_loss: float, take_profit: float, direction: str,
                            current_price: float) -> UnrealizedPnL:
    """Mark-to-market % P/L for a still-open paper trade, given the current market price."""
    if entry <= 0:
        return UnrealizedPnL(current_price=current_price, pct_change=0.0, distance_to_sl_pct=0.0, distance_to_tp_pct=0.0)

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
