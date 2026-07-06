"""
Account config storage (balance / risk % / max open positions, editable
via `!account`) and unrealized P/L tracking for `!pnl`.

Position sizing is computed by compute_position_size(), in one of two
modes (account_cfg["sizing_mode"], set via `!account sizing`):

  - "risk_pct" (the original, and still the default, model): risk a fixed
    % of account balance per trade, sized so a full stop-out costs
    exactly that amount --
        risk_amount = balance x risk_pct / 100
        shares      = risk_amount / abs(entry - stop_loss)
    Position size varies with how tight the stop is.

  - "account_pct": a fixed CAPITAL ALLOCATION per trade instead -- the
    position itself is always exactly account_pct% of the account
    balance, regardless of stop distance --
        position_value = balance x position_pct / 100
        shares         = position_value / entry
    e.g. a €1,000,000 account at 0.1% always opens a €1,000 position.

A MAX_POSITION_SIZE_PCT cap prevents the position from consuming too
large a fraction of the account (e.g. a tiny stop on a cheap stock
could otherwise suggest a very large share count in risk_pct mode). The
result is shown in every Discord alert embed as "Suggested size" and is
now also SNAPSHOTTED onto the trade record at the moment it's logged
(see performance.py's log_trade) -- so a later change to the account
balance or sizing mode never retroactively changes what an already-open
trade is considered to be sized at.

Realized P&L bookkeeping: apply_realized_pnl() is called by
performance.py the instant a trade actually closes (SL/TP hit, or the
near-TP timeout exit) -- using the shares snapshotted at open time -- to
add/subtract that trade's real currency gain/loss to/from the account
balance, and appends one entry to balance_history so the admin
Performance page can chart the account balance over time, not just the
%-based equity curve it already had.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot import config as app_config

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BERLIN_TZ = _ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None

CONFIG_PATH = os.path.join(app_config.DATA_DIR, "account.json")

# balance_history is append-only and grows one entry per closed trade (plus
# manual balance overrides) -- cheap to keep a very long tail of, but capped
# so a years-old, extremely active account doesn't grow account.json without
# bound. Far more than enough for any chart resolution the admin UI needs.
_MAX_BALANCE_HISTORY = 5000


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
        "sizing_mode":        app_config.POSITION_SIZING_MODE,
        "position_pct":       app_config.POSITION_SIZE_PCT_OF_ACCOUNT,
        "balance_history":    [],
    }
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                stored = json.load(f)
                # Merge: stored values win over defaults, but any key that
                # doesn't exist in the stored file gets the default value.
                merged = {**defaults, **stored}
                return merged
            except json.JSONDecodeError:
                pass
    # Brand-new account -- seed balance_history with a starting point so the
    # "balance over time" chart has something to plot from before the first
    # trade ever closes, instead of an empty series until then.
    defaults["balance_history"] = [{
        "ts": datetime.now(timezone.utc).isoformat(),
        "balance": defaults["balance"],
        "pnl_amount": None,
        "reason": "account created",
    }]
    save_account_config(defaults, path)
    return dict(defaults)


def save_account_config(config: dict, path: str = CONFIG_PATH):
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def _append_balance_history(cfg: dict, entry: dict) -> dict:
    history = cfg.setdefault("balance_history", [])
    history.append(entry)
    if len(history) > _MAX_BALANCE_HISTORY:
        cfg["balance_history"] = history[-_MAX_BALANCE_HISTORY:]
    return cfg


def set_balance(balance: float, path: str = CONFIG_PATH) -> dict:
    config = load_account_config(path)
    config["balance"] = balance
    # A manual override is a real, visible jump in the balance-over-time
    # chart -- record it as its own history entry (pnl_amount=None
    # distinguishes it from a real trade settlement) rather than silently
    # losing that point between two trade-driven entries.
    _append_balance_history(config, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "balance": balance,
        "pnl_amount": None,
        "reason": "manual override",
    })
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


def set_sizing_mode(mode: str, path: str = CONFIG_PATH) -> dict:
    mode = mode.strip().lower()
    if mode in ("account", "account_pct", "alloc", "allocation"):
        mode = "account_pct"
    elif mode in ("risk", "risk_pct"):
        mode = "risk_pct"
    else:
        raise ValueError(f"Unknown sizing mode {mode!r} -- use 'risk' or 'account'.")
    config = load_account_config(path)
    config["sizing_mode"] = mode
    save_account_config(config, path)
    return config


def set_position_pct(pct: float, path: str = CONFIG_PATH) -> dict:
    config = load_account_config(path)
    config["position_pct"] = pct
    save_account_config(config, path)
    return config


def get_balance_history(path: str = CONFIG_PATH) -> list:
    """Chronological list of {ts, balance, pnl_amount, reason/trade_id/ticker}
    entries -- one per closed trade settlement plus any manual `!account
    balance` overrides -- for the admin Performance page's balance-over-time
    chart."""
    return load_account_config(path).get("balance_history", [])


def _to_berlin(ts_iso: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts_iso)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BERLIN_TZ) if _BERLIN_TZ else dt


def get_daily_summary(path: str = CONFIG_PATH) -> dict:
    """
    Today's account-balance movement (Europe/Berlin calendar day, matching
    the same day boundary performance.py's by-day-of-week breakdown
    already uses), for the dashboard's Account Balance stat card:

      - balance: current account balance (right now)
      - balance_start_of_day: balance as of the last event BEFORE today
        started -- i.e. what the balance was at midnight -- or None if
        there's no history from before today (a brand-new account whose
        very first entry IS today).
      - pct_change_today: (balance - balance_start_of_day) / balance_start_of_day
        x 100 -- reflects EVERYTHING that moved the balance today,
        including a manual `!account balance` override, since that's a
        real change to the balance regardless of cause.
      - pnl_today: sum of pnl_amount across today's entries that came from
        an actual trade settlement (pnl_amount is not None) -- i.e.
        EXCLUDING manual overrides, since "today's win/loss" should mean
        "what today's trades actually made or lost", not an unrelated
        manual balance correction.
      - wins_amount_today / losses_amount_today: pnl_today split into its
        positive and negative (shown as a positive magnitude) parts, for a
        two-color "+X won / -Y lost" display if wanted.
      - trades_closed_today: count of trade-settlement entries today.

    All currency fields are None if there's no balance_history at all
    (shouldn't normally happen -- load_account_config always seeds at
    least one entry -- but guards against a hand-edited account.json).
    """
    cfg = load_account_config(path)
    balance = float(cfg.get("balance", 0))
    history = cfg.get("balance_history", [])
    if not history:
        return {
            "balance": balance, "balance_start_of_day": None, "pct_change_today": None,
            "pnl_today": None, "wins_amount_today": None, "losses_amount_today": None,
            "trades_closed_today": 0,
        }

    now_berlin = datetime.now(_BERLIN_TZ) if _BERLIN_TZ else datetime.now(timezone.utc)
    today = now_berlin.date()

    before_today = None    # most recent entry strictly before today
    today_trade_pnls = []  # pnl_amount for today's real trade settlements only
    for entry in history:
        dt = _to_berlin(entry.get("ts", ""))
        if dt is None:
            continue
        if dt.date() < today:
            if before_today is None or dt > _to_berlin(before_today.get("ts", "")):
                before_today = entry
        elif dt.date() == today and entry.get("pnl_amount") is not None:
            today_trade_pnls.append(float(entry["pnl_amount"]))

    balance_start_of_day = float(before_today["balance"]) if before_today else None
    pct_change_today = (
        round((balance - balance_start_of_day) / balance_start_of_day * 100, 3)
        if balance_start_of_day else None
    )

    wins_amount_today   = round(sum(p for p in today_trade_pnls if p > 0), 2)
    losses_amount_today = round(-sum(p for p in today_trade_pnls if p < 0), 2)   # positive magnitude
    pnl_today = round(sum(today_trade_pnls), 2) if today_trade_pnls else 0.0

    return {
        "balance": balance,
        "balance_start_of_day": balance_start_of_day,
        "pct_change_today": pct_change_today,
        "pnl_today": pnl_today,
        "wins_amount_today": wins_amount_today,
        "losses_amount_today": losses_amount_today,
        "trades_closed_today": len(today_trade_pnls),
    }


def apply_realized_pnl(pnl_amount: float, meta: dict = None, path: str = CONFIG_PATH) -> dict:
    """
    Adds (or subtracts, if negative) a trade's realized currency P&L to the
    account balance and appends one entry to balance_history recording the
    new balance. Called once, right when a trade actually closes (see
    performance.py's TradeLog._settle_account_balance) -- NOT on every
    price tick, so a trade that's merely unrealized-in-profit never moves
    the real account balance, only its own eventual close does.

    `meta` (e.g. {"trade_id":..., "ticker":..., "status":...}) is merged
    into the history entry so it's traceable back to the trade that caused
    it. Returns the updated account config dict (already saved to disk).
    """
    config = load_account_config(path)
    old_balance = float(config.get("balance", 0))
    new_balance = round(old_balance + pnl_amount, 2)
    config["balance"] = new_balance
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "balance": new_balance,
        "pnl_amount": round(pnl_amount, 2),
    }
    if meta:
        entry.update(meta)
    _append_balance_history(config, entry)
    save_account_config(config, path)
    return config


def compute_position_size(entry: float, stop_loss: float, account_cfg: dict = None) -> dict | None:
    """
    Position sizing -- see this module's docstring for the two modes
    (account_cfg["sizing_mode"]: "risk_pct" or "account_pct").

    If position_value would exceed balance x max_position_pct/100, shares
    are capped at that maximum and `capped` is True in the result -- in
    "account_pct" mode this is normally a no-op (position_pct is expected
    to already sit well under the cap) but stays as a safety net in case
    position_pct itself is ever set above max_position_pct.

    Returns None when balance <= 0, entry <= 0, or (risk_pct mode only)
    stop distance is zero.

    Return dict keys:
        shares          -- suggested whole/fractional share count
        risk_amount     -- currency at risk if stop-loss is hit
        position_value  -- total capital deployed (shares x entry)
        capped          -- True if position_value was capped
        balance         -- account balance used in calculation
        risk_pct        -- risk % used (risk_pct mode)
        position_pct    -- account allocation % used (account_pct mode)
        max_position_pct -- position size cap % used
        mode            -- "risk_pct" or "account_pct", whichever was used
    """
    if account_cfg is None:
        account_cfg = load_account_config()

    balance = float(account_cfg.get("balance", 0))
    risk_pct = float(account_cfg.get("risk_pct", 1.0))
    position_pct = float(account_cfg.get("position_pct", app_config.POSITION_SIZE_PCT_OF_ACCOUNT))
    max_position_pct = float(account_cfg.get("max_position_pct", app_config.MAX_POSITION_SIZE_PCT))
    mode = account_cfg.get("sizing_mode", "risk_pct")

    if balance <= 0 or entry <= 0:
        return None

    stop_distance = abs(entry - stop_loss)

    if mode == "account_pct":
        # Fixed allocation: the position is always exactly position_pct% of
        # the account, independent of how far away the stop sits.
        position_value = balance * position_pct / 100.0
        raw_shares = position_value / entry
        risk_amount = raw_shares * stop_distance   # informational only -- not what sized this trade
    else:
        mode = "risk_pct"   # normalize anything unrecognized to the documented default
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
        # risk_pct mode preserves the ORIGINAL behavior here: risk_amount
        # stays the intended pre-cap risk (balance x risk_pct/100), not
        # recomputed from the now-capped share count -- that's how this
        # already worked before account_pct mode existed, and changing it
        # would silently change what every existing risk_pct trade/alert
        # reports. account_pct mode has no such pre-existing meaning for
        # risk_amount (it was never the sizing input in that mode to begin
        # with), so there it's fine -- and more useful -- to reflect the
        # actual capped position's real risk instead of an uncapped one.
        if mode == "account_pct":
            risk_amount = raw_shares * stop_distance

    return {
        "shares":           round(raw_shares, 2),
        "risk_amount":      round(risk_amount, 2),
        "position_value":   round(position_value, 2),
        "capped":           capped,
        "balance":          balance,
        "risk_pct":         risk_pct,
        "position_pct":     position_pct,
        "max_position_pct": max_position_pct,
        "mode":             mode,
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
