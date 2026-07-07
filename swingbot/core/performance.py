"""
Trade log & performance tracker.

Every alert that fires gets logged as a trade (entry/stop/target/confidence).
On each subsequent scan, open trades are checked against new price bars:
if the high reaches the take-profit before the low reaches the stop-loss
(for a bullish trade -- mirrored for bearish), it's marked a WIN; if the
stop is hit first, a LOSS. This produces a real, growing track record you
can check per confidence level with `!performance`.

Conservative assumption: if a single day's bar range covers BOTH the stop
and the target, the stop is assumed to have been hit first (worst case),
since daily bars don't tell us the actual intraday order of events.

This is a paper-trade tracker -- it does not know about slippage, fees,
partial fills, or gaps beyond what the daily bar shows.
"""
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from threading import Lock

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BERLIN_TZ = _ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None

from swingbot import config
from swingbot.core import account as account_module

_LOCK = Lock()


# ---------------------------------------------------------------------------
# Trade-health status (admin dashboard) -- how close an OPEN trade's live
# price is to hitting its stop-loss vs. its target, as a single -1..+1
# number and a color to match: red approaching the stop, green
# approaching the target, grey while it's still sitting near entry.
# Pure/no I/O so it's trivial to unit-test and safe to call on every
# dashboard render -- the admin UI supplies the live price (see
# swingbot.core.data.get_current_price, which does its own caching).
# ---------------------------------------------------------------------------

# Endpoint colors the proximity score is interpolated between. Reusing
# the same red/grey/green already used elsewhere in the admin UI
# (win/loss stat cards, direction column) so this new indicator reads as
# part of the same color language instead of introducing a new palette.
_PROXIMITY_STOP_COLOR   = (0xff, 0x44, 0x44)   # bright red
_PROXIMITY_NEUTRAL_COLOR = (0x6e, 0x77, 0x8c)  # mid grey
_PROXIMITY_TARGET_COLOR = (0x44, 0xff, 0x88)   # bright green


def _lerp_color(c1: tuple, c2: tuple, t: float) -> str:
    """Linear-interpolates between two (r,g,b) tuples at t in [0,1], returns '#rrggbb'."""
    t = max(0.0, min(1.0, t))
    r = round(c1[0] + (c2[0] - c1[0]) * t)
    g = round(c1[1] + (c2[1] - c1[1]) * t)
    b = round(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def trade_proximity(direction: str, entry: float, stop_loss: float, take_profit: float,
                     current_price: float) -> dict:
    """
    Where a trade's current price sits between its stop-loss and its
    target, as a single normalized score:
      -1.0 = at or past the stop-loss (worst case)
       0.0 = sitting right at entry (neutral)
      +1.0 = at or past the target (best case)
    with everything in between scaled linearly against however far away
    the stop/target actually are (a trade with a tight 2% stop reaches
    -1.0 much sooner, in price terms, than one with a wide 10% stop).

    Returns a dict with:
      - "proximity": the -1..+1 float above
      - "color": a '#rrggbb' string interpolated red (stop) -> grey
        (entry) -> green (target)
      - "blink_seconds": how fast the dashboard's pulse animation should
        run for this trade -- faster as it gets closer to EITHER end,
        so a trade about to hit its stop or target visibly demands more
        attention than one sitting quietly near entry.
      - "label": short human-readable description for a tooltip.

    Direction-aware: for a bearish (short) trade, a FALLING price is the
    good direction and a RISING one is bad -- the mirror image of a
    bullish trade -- so this isn't just "higher price = greener".
    """
    is_bull = direction == "bullish"
    risk = abs(entry - stop_loss) or 1e-9      # guard div-by-zero on a malformed record
    reward = abs(take_profit - entry) or 1e-9

    if is_bull:
        delta = current_price - entry
    else:
        delta = entry - current_price   # mirrored: falling price is progress for a short

    if delta >= 0:
        proximity = delta / reward          # moving toward target
    else:
        proximity = delta / risk            # moving toward stop (delta already negative)
    proximity = max(-1.0, min(1.0, proximity))

    if proximity >= 0:
        color = _lerp_color(_PROXIMITY_NEUTRAL_COLOR, _PROXIMITY_TARGET_COLOR, proximity)
        label = "Near target" if proximity > 0.66 else ("Trending toward target" if proximity > 0.15 else "Near entry")
    else:
        color = _lerp_color(_PROXIMITY_NEUTRAL_COLOR, _PROXIMITY_STOP_COLOR, -proximity)
        label = "Near stop-loss" if proximity < -0.66 else ("Trending toward stop" if proximity < -0.15 else "Near entry")

    # 2.2s at rest (proximity 0) down to 0.6s right at either extreme --
    # urgency speeds the pulse up rather than just changing its color.
    urgency = abs(proximity)
    blink_seconds = round(2.2 - (1.6 * urgency), 2)

    return {"proximity": round(proximity, 4), "color": color, "blink_seconds": blink_seconds, "label": label}


def primary_strategy_label(t: dict) -> str:
    """
    The real per-trade "strategy" label to SHOW, as opposed to
    t["strategy"] itself -- which, for every trade produced by the live
    confluence engine, is just ScenarioSignal's hardcoded default
    ("S/R Confluence", see levels.ScenarioSignal) and is never actually
    overridden per-trade. Every trade in trades.json ends up with that
    exact same literal string, which is why any view that reads
    t["strategy"] directly (the admin Performance page's Trade Log table
    and By-Strategy breakdown, before this function existed) showed the
    same strategy for every single row.

    The real per-trade signal instead lives in target_sources /
    stop_sources: the independent methods (EMA20, VWAP, Fib 61.8%, Volume
    Profile, a diagonal trendline, ...) that a real confluence pass found
    agreeing on this trade's levels (see levels.count_confirming_strategies()).
    This reuses chart_drawing._pick_primary_source -- the same ranking
    (METHOD_PRIORITY) already used to choose which single confirming
    method gets drawn on that trade's own chart, and that the dashboard's
    open-trades table already uses for its Strategy column -- so every
    place in the admin UI that shows a trade's strategy now agrees,
    instead of three different labels for the same trade.

    Falls back to t["strategy"] (or "--") for older trades logged before
    target_sources/stop_sources existed, or if neither list has anything
    _pick_primary_source recognizes.

    Imported lazily to avoid pulling matplotlib/mplfinance (chart_style.py's
    import chain) into every process that imports performance.py just to
    read a trade log -- only paid for by the callers (admin UI page
    renders) that actually need this label.
    """
    from swingbot.core.charts.chart_drawing import _pick_primary_source
    sources = t.get("target_sources") or t.get("stop_sources") or []
    return _pick_primary_source(sources) or t.get("strategy") or "--"


class TradeLog:
    def __init__(self, path: str = None):
        self.path = path or os.path.join(config.DATA_DIR, "trades.json")
        self._trades = self._load()

    def _load(self) -> list:
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._trades, f, indent=2)

    def log_trade(self, ticker, strategy, horizon_key, direction, confidence_level,
                  confidence_label, entry, stop_loss, take_profit, target2=None,
                  confidence_score=None, confidence_breakdown=None, target_sources=None,
                  stop_sources=None, target2_sources=None, risk_reward_ratio=None,
                  explanation=None, confirmed_by=None) -> str:
        """
        The extra keyword args (confidence_score/breakdown, target/stop
        sources, explanation, confirmed_by) are optional and purely for
        the admin UI's trade-detail page -- they capture the same
        information the Discord alert showed at the moment it fired, so
        clicking a trade later shows exactly what you saw then, not a
        best-effort reconstruction from today's (possibly since-moved)
        levels. Trades logged before this field existed simply won't
        have it; the detail page handles that gracefully.
        """
        trade_id = str(uuid.uuid4())[:8]
        record = {
            "id": trade_id,
            "ticker": ticker,
            "strategy": strategy,
            "horizon_key": horizon_key,
            "direction": direction,
            "confidence_level": confidence_level,
            "confidence_label": confidence_label,
            "confidence_score": confidence_score,
            "confidence_breakdown": confidence_breakdown,     # dict: factor -> explanation string, from confidence.py
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "target2": target2,     # stretch target beyond take_profit, if a second level was found -- may be None
            "target_sources": target_sources or [],            # independent methods confirming target 1 (EMA/VWAP/Fib/etc.)
            "stop_sources": stop_sources or [],                 # independent methods confirming the stop level
            "target2_sources": target2_sources or [],
            "risk_reward_ratio": risk_reward_ratio,
            "explanation": explanation,                          # the "why this trade" text shown in the original alert
            "confirmed_by": confirmed_by or [],                  # strategy/horizon combos that agreed on this exact plan
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "status": "open",       # open | win | loss
            "closed_at": None,
            "exit_price": None,
            "near_close_alerted": False,  # tracks whether we've already warned this trade is close to SL/TP
            "near_tp_since": None,        # ISO timestamp of when price FIRST reached the near-TP timeout
                                           # threshold and hasn't dropped back below it since -- see
                                           # check_near_tp_timeout(). None while price isn't in that zone.
            "near_tp_snapshots": [],       # [iso_ts, price] pairs used for the near-TP stall check -- see
                                           # check_near_tp_timeout(). Reset whenever near_tp_since resets.
        }

        # Snapshot position sizing NOW, at the moment the trade is opened --
        # not recomputed later from whatever the account balance happens to
        # be when it closes. Without this, a trade opened when the account
        # was €1,000,000 (sized at €1,000 on a 0.1% account_pct allocation)
        # would settle its P&L using a completely different share count if
        # the balance had since moved. See account.py's docstring for the
        # two sizing modes. `shares` is None (and no P&L is ever settled to
        # the account) if sizing can't be computed at all -- e.g. account
        # balance is 0/unset, or (risk_pct mode) stop distance is zero.
        try:
            sizing = account_module.compute_position_size(entry, stop_loss)
        except Exception:
            sizing = None
        record["shares"] = sizing["shares"] if sizing else None
        record["position_value"] = sizing["position_value"] if sizing else None
        record["sizing_mode"] = sizing["mode"] if sizing else None
        record["realized_pnl_amount"] = None      # filled in on close by _settle_account_balance
        record["account_balance_after"] = None    # filled in on close by _settle_account_balance

        with _LOCK:
            self._trades.append(record)
            self._save()
        return trade_id

    def _settle_account_balance(self, t: dict) -> None:
        """
        Computes this trade's realized currency P&L -- using the share
        count SNAPSHOTTED at log_trade() time, not today's account
        balance/sizing settings -- and applies it to the account balance
        via account.apply_realized_pnl(), which also appends a
        balance_history entry the admin Performance page charts.

        Mutates `t` in place (realized_pnl_amount, account_balance_after)
        so the trade record itself carries a permanent record of what it
        actually did to the account, alongside its %-based pnl_pct.

        No-op (never touches the account) for:
          - a trade logged before this feature existed / that never got a
            valid `shares` snapshot (e.g. account balance was 0 at open time)
          - anything other than an actual win/loss close -- a manual
            "closed" (no real exit price) has no real P&L to realize.

        Call this BEFORE saving `t` to disk (inside the same lock the
        caller already holds) so realized_pnl_amount/account_balance_after
        land in the same write instead of needing a second save.
        """
        shares = t.get("shares")
        exit_price = t.get("exit_price")
        entry = t.get("entry")
        if not shares or exit_price is None or entry is None or t.get("status") not in ("win", "loss"):
            return
        is_bull = t.get("direction") == "bullish"
        pnl_amount = shares * (exit_price - entry) if is_bull else shares * (entry - exit_price)
        pnl_amount = round(pnl_amount, 2)
        try:
            updated_cfg = account_module.apply_realized_pnl(
                pnl_amount, {"trade_id": t.get("id"), "ticker": t.get("ticker"), "status": t.get("status")},
            )
            t["realized_pnl_amount"] = pnl_amount
            t["account_balance_after"] = updated_cfg.get("balance")
        except Exception:
            # Account bookkeeping must never prevent the trade itself from
            # closing -- worst case the account balance simply doesn't
            # reflect this one trade yet.
            pass

    def update_open_trades(self, ticker: str, df, live_price: float | None = None) -> list:
        """
        Check this ticker's open trades against bars since they were opened.
        `df` must be indexed by date with High/Low columns, most recent last.
        `live_price` is the current quote including premarket/aftermarket -- when
        provided it is checked as a "virtual" final bar so intraday SL/TP hits
        (including extended-hours moves not yet in the daily df) are caught
        immediately rather than waiting for the next completed daily bar.
        Returns the list of trades that were newly closed this call.
        """
        # Compute outcomes WITHOUT the lock first (pure pandas work, no writes).
        # Re-acquire it to actually apply the mutations and save, so a concurrent
        # refresh() between the computation and the write can't cause us to save
        # stale data or lose the status updates.
        open_trades = [t for t in self._trades if t["ticker"] == ticker and t["status"] == "open"]
        if not open_trades:
            return []

        updates = []   # [(trade_id, new_status, exit_price)]
        already_closed_ids: set = set()
        for trade in open_trades:
            opened_at = datetime.fromisoformat(trade["opened_at"])
            bars_since = (
                df[df.index.tz_localize(None) > opened_at.replace(tzinfo=None)]
                if df.index.tz is not None
                else df[df.index > opened_at.replace(tzinfo=None)]
            )

            is_bull = trade["direction"] == "bullish"
            hit = False
            for _, bar in bars_since.iterrows():
                hi, lo = float(bar["High"]), float(bar["Low"])
                if is_bull:
                    hit_stop   = lo <= trade["stop_loss"]
                    hit_target = hi >= trade["take_profit"]
                else:
                    hit_stop   = hi >= trade["stop_loss"]
                    hit_target = lo <= trade["take_profit"]

                if hit_stop:
                    updates.append((trade["id"], "loss", trade["stop_loss"]))
                    already_closed_ids.add(trade["id"])
                    hit = True
                    break
                elif hit_target:
                    updates.append((trade["id"], "win", trade["take_profit"]))
                    already_closed_ids.add(trade["id"])
                    hit = True
                    break

            # Check live price (premarket/aftermarket) if the bar scan didn't
            # already close this trade and we have a live quote to work with.
            if not hit and live_price and live_price > 0 and trade["id"] not in already_closed_ids:
                if is_bull:
                    if live_price <= trade["stop_loss"]:
                        updates.append((trade["id"], "loss", trade["stop_loss"]))
                    elif live_price >= trade["take_profit"]:
                        updates.append((trade["id"], "win", trade["take_profit"]))
                else:
                    if live_price >= trade["stop_loss"]:
                        updates.append((trade["id"], "loss", trade["stop_loss"]))
                    elif live_price <= trade["take_profit"]:
                        updates.append((trade["id"], "win", trade["take_profit"]))

        if not updates:
            return []

        # Apply mutations and save atomically under the lock so no concurrent
        # refresh() can race between the dict mutation and self._save().
        newly_closed = []
        closed_at = datetime.now(timezone.utc).isoformat()
        with _LOCK:
            id_to_trade = {t["id"]: t for t in self._trades}
            for trade_id, new_status, exit_price in updates:
                t = id_to_trade.get(trade_id)
                if t is None or t["status"] != "open":
                    continue   # already closed by a parallel call
                t["status"] = new_status
                t["exit_price"] = exit_price
                t["closed_at"] = closed_at
                self._settle_account_balance(t)
                newly_closed.append(t)
            if newly_closed:
                self._save()
        return newly_closed

    def get_stats(self, confidence_level: int = None, trades: list | None = None) -> dict:
        """
        `trades`, if given, overrides the base trade set the stats are
        computed over (e.g. the dashboard's "Today" mode passing in just
        today's opened/closed trades instead of the whole history). Defaults
        to every trade on record, same as before this parameter existed.
        """
        self.refresh()
        base = self._trades if trades is None else trades
        trades = base if confidence_level is None else [
            t for t in base if t["confidence_level"] == confidence_level
        ]
        # "closed" = manually closed from admin UI (no SL/TP hit recorded);
        # counted as closed for total/win-rate denominator but not as win or loss.
        closed = [t for t in trades if t["status"] in ("win", "loss", "closed")]
        wins = [t for t in closed if t["status"] == "win"]
        open_trades = [t for t in trades if t["status"] == "open"]

        win_rate = (len(wins) / len(closed) * 100) if closed else None
        return {
            "total": len(trades),
            "open": len(open_trades),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(closed) - len(wins),
            "win_rate": win_rate,
        }

    def get_stats_by_confidence(self) -> dict:
        return {level: self.get_stats(level) for level in range(1, 6)}

    def get_extended_stats(self, confidence_level: int = None, trades: list | None = None) -> dict:
        """
        Additional performance metrics beyond get_stats()'s win/loss counts,
        for the admin dashboard's stat cards:

          - expectancy_r: average realized R-multiple across trades that
            actually hit their stop or target (status win/loss) -- R =
            (exit - entry) / (entry - stop_loss), sign-adjusted for
            direction, i.e. how many "risk units" this trade made or lost.
            A single number summarizing the whole track record's edge per
            trade, the standard way trading systems are compared. None if
            there are no win/loss trades yet.
          - avg_holding_days: average calendar days between opened_at and
            closed_at across every closed trade (win/loss/manually-closed).
          - avg_open_confidence: average confidence_level (1-5) across
            currently OPEN trades -- a quick read on how strong the setups
            sitting in the book right now are, independent of past results.

        Manually-closed trades (status == "closed", no stop/target hit)
        count toward avg_holding_days but not expectancy_r -- there's no
        real R to compute without a stop or target actually being reached.
        """
        self.refresh()
        base = self._trades if trades is None else trades
        trades = base if confidence_level is None else [
            t for t in base if t["confidence_level"] == confidence_level
        ]
        closed = [t for t in trades if t["status"] in ("win", "loss", "closed")]
        open_trades = [t for t in trades if t["status"] == "open"]

        r_multiples = []
        for t in closed:
            if t["status"] not in ("win", "loss"):
                continue
            risk = abs(t["entry"] - t["stop_loss"])
            exit_price = t.get("exit_price")
            if not risk or exit_price is None:
                continue
            is_bull = t["direction"] == "bullish"
            realized = (exit_price - t["entry"]) if is_bull else (t["entry"] - exit_price)
            r_multiples.append(realized / risk)

        holding_days = []
        for t in closed:
            if not t.get("closed_at") or not t.get("opened_at"):
                continue
            try:
                opened = datetime.fromisoformat(t["opened_at"])
                closed_dt = datetime.fromisoformat(t["closed_at"])
                holding_days.append((closed_dt - opened).total_seconds() / 86400.0)
            except (ValueError, TypeError):
                continue

        open_confidences = [
            t["confidence_level"] for t in open_trades if t.get("confidence_level") is not None
        ]

        return {
            "expectancy_r": (sum(r_multiples) / len(r_multiples)) if r_multiples else None,
            "r_multiples_count": len(r_multiples),
            "avg_holding_days": (sum(holding_days) / len(holding_days)) if holding_days else None,
            "avg_open_confidence": (sum(open_confidences) / len(open_confidences)) if open_confidences else None,
        }

    def refresh(self):
        """Re-read trades from disk.  Called automatically by get_trades() /
        get_stats() / has_open_trade() so the bot always reflects the latest
        state even when a separate process (the admin UI) has modified the file
        since this instance was constructed."""
        with _LOCK:
            self._trades = self._load()

    def get_trades(self, status: str = None, ticker: str = None, limit: int | None = 20,
                    sort_by: str = "opened_at") -> list:
        """
        Filtered list of trade records. `sort_by`:
          - "opened_at" (default): most-recent-first.
          - "confidence": highest confidence LEVEL first, ties broken by
            highest confidence SCORE (0-100) -- i.e. within the same
            level (e.g. two Lv4 trades), the one with the stronger
            underlying score sorts first, not just whichever is newer.
            Trades missing a confidence_score (older records predating
            that field) sort after ones that have it, at the same level.
        `limit=None` returns every matching trade (used for pagination,
        where the caller slices pages out of the full sorted list).

        Always re-reads from disk so the bot reflects changes made by the
        admin UI (or any other process that writes trades.json).
        """
        self.refresh()
        trades = list(self._trades)
        if status and status != "all":
            trades = [t for t in trades if t["status"] == status]
        if ticker:
            trades = [t for t in trades if t["ticker"] == ticker.upper()]

        if sort_by == "confidence":
            trades.sort(key=lambda t: (t.get("confidence_level", 0), t.get("confidence_score", 0)), reverse=True)
        else:
            trades.sort(key=lambda t: t["opened_at"], reverse=True)

        return trades[:limit] if limit is not None else trades

    def get_trade_by_id(self, trade_id: str) -> dict | None:
        self.refresh()   # always read fresh — admin UI may have modified the file
        return next((t for t in self._trades if t["id"] == trade_id), None)

    def has_open_trade(self, ticker: str, strategy: str, horizon_key: str, direction: str) -> bool:
        """True if this exact setup is already being tracked as an open trade --
        used to avoid logging duplicate positions when a snapshot scan re-surfaces
        a still-active signal that was already recommended."""
        self.refresh()
        return any(
            t["ticker"] == ticker and t["strategy"] == strategy and t["horizon_key"] == horizon_key
            and t["direction"] == direction and t["status"] == "open"
            for t in self._trades
        )

    def mark_near_close(self, trade_id: str, alerted: bool):
        """Sets/clears the near_close_alerted flag so we warn once per approach,
        not every single check while price lingers near the level."""
        with _LOCK:
            for t in self._trades:
                if t["id"] == trade_id:
                    t["near_close_alerted"] = alerted
                    self._save()
                    return

    def close_trade_manual(self, trade_id: str, reason: str = "manual") -> bool:
        """
        Marks an open trade as closed without an exit price (used by the
        admin UI's "Close" button -- a human override, not a stop/target
        hit). Locked the same way as every other mutator here so a
        concurrent write from the bot's own scan loop (a different
        process, same trades.json) can't race with it and corrupt or lose
        data. Returns True if a matching OPEN trade was found and closed.
        """
        with _LOCK:
            for t in self._trades:
                if t["id"] == trade_id and t["status"] == "open":
                    t["status"] = "closed"
                    t["closed_at"] = datetime.now(timezone.utc).isoformat()
                    t["close_reason"] = reason
                    self._save()
                    return True
        return False

    def delete_trade(self, trade_id: str) -> bool:
        """Remove a single trade record by id. Returns True if something was deleted."""
        before = len(self._trades)
        with _LOCK:
            self._trades = [t for t in self._trades if t["id"] != trade_id]
            deleted = len(self._trades) != before
            if deleted:
                self._save()
        return deleted

    def clear_history(self) -> int:
        """Delete all closed (win/loss/manually-closed) trade records, leaving open trades untouched."""
        with _LOCK:
            before = len(self._trades)
            self._trades = [t for t in self._trades if t["status"] == "open"]
            removed = before - len(self._trades)
            if removed:
                self._save()
        return removed

    def clear_open(self) -> int:
        """Delete every trade currently in status='open', leaving closed win/loss history untouched."""
        with _LOCK:
            before = len(self._trades)
            self._trades = [t for t in self._trades if t["status"] != "open"]
            removed = before - len(self._trades)
            if removed:
                self._save()
        return removed

    def clear_all(self) -> int:
        """Delete every trade record. Returns how many were removed."""
        with _LOCK:
            count = len(self._trades)
            self._trades = []
            self._save()
        return count

    def close_if_live_price_hit(self, ticker: str, live_price: float) -> list:
        """
        Fast SL/TP check using only a live price quote -- no DataFrame needed.
        Called by the trade_monitor background task (60s interval) to catch
        hits immediately between full scan cycles.
        Returns the list of newly-closed trade records (already saved to disk).
        """
        self.refresh()
        open_trades = [t for t in self._trades
                       if t["ticker"] == ticker and t["status"] == "open"]
        if not open_trades:
            return []

        updates = []
        for trade in open_trades:
            is_bull = trade["direction"] == "bullish"
            if is_bull:
                if live_price <= trade["stop_loss"]:
                    updates.append((trade["id"], "loss", trade["stop_loss"]))
                elif live_price >= trade["take_profit"]:
                    updates.append((trade["id"], "win", trade["take_profit"]))
            else:
                if live_price >= trade["stop_loss"]:
                    updates.append((trade["id"], "loss", trade["stop_loss"]))
                elif live_price <= trade["take_profit"]:
                    updates.append((trade["id"], "win", trade["take_profit"]))

        if not updates:
            return []

        newly_closed = []
        closed_at = datetime.now(timezone.utc).isoformat()
        with _LOCK:
            id_map = {t["id"]: t for t in self._trades}
            for trade_id, new_status, exit_price in updates:
                t = id_map.get(trade_id)
                if t is None or t["status"] != "open":
                    continue
                t["status"] = new_status
                t["exit_price"] = exit_price
                t["closed_at"] = closed_at
                t["close_reason"] = "auto (price monitor)"
                self._settle_account_balance(t)
                newly_closed.append(dict(t))
            if newly_closed:
                self._save()
        return newly_closed

    def check_near_tp_timeout(self, ticker: str, live_price: float) -> list:
        """
        Closes an open trade early, locking in the profit already made, if
        price has gotten most of the way to the target and then gone
        sideways there instead of actually tapping it -- see
        config.NEAR_TP_TIMEOUT_ENABLED / _THRESHOLD_PCT / _MINUTES, plus
        the faster "stall" exit below (_STALL_CHECK_MINUTES / _STALL_MAX_
        FLUCTUATION_PCT).

        Called by the trade_monitor background task (60s interval) on
        whatever's still open AFTER close_if_live_price_hit's exact SL/TP
        check has already run for this tick -- a trade that just hit its
        real target or stop this same call is already closed by the time
        this runs and won't show up in the `open_trades` query below.

        Progress toward the target is measured as a % of the entry ->
        target-1 distance (mirrored for a short: falling price is
        progress). Reaching config.NEAR_TP_TIMEOUT_THRESHOLD_PCT starts a
        per-trade clock (persisted as "near_tp_since" so it survives a
        bot restart between checks); dropping back below the threshold
        resets it to None rather than accumulating partial credit across
        separate approaches.

        Two ways the trade can then close early, at the current live
        price, marked a win:
          1. "timeout" -- price has stayed AT OR ABOVE the threshold
             continuously for config.NEAR_TP_TIMEOUT_MINUTES.
          2. "stall" -- a faster check: once price has been in the near-TP
             zone for at least config.NEAR_TP_STALL_CHECK_MINUTES (which
             must be shorter than the full timeout), if price hasn't moved
             by more than config.NEAR_TP_STALL_MAX_FLUCTUATION_PCT (as a %
             of entry) over that trailing window, it's basically gone flat
             right at the target -- no reason to keep waiting out the full
             timeout, so it closes now. Price snapshots for this check are
             persisted as "near_tp_snapshots" (list of [iso_ts, price]) and
             reset whenever the clock resets.

        Returns the list of newly-closed trade records (already saved to
        disk), same shape as close_if_live_price_hit.
        """
        if not config.NEAR_TP_TIMEOUT_ENABLED:
            return []

        self.refresh()
        open_trades = [t for t in self._trades
                       if t["ticker"] == ticker and t["status"] == "open"]
        if not open_trades:
            return []

        now = datetime.now(timezone.utc)
        threshold = config.NEAR_TP_TIMEOUT_THRESHOLD_PCT / 100.0
        timeout = config.NEAR_TP_TIMEOUT_MINUTES
        stall_minutes = getattr(config, "NEAR_TP_STALL_CHECK_MINUTES", 0) or 0
        # Stall window must be strictly shorter than the full timeout, or it's
        # meaningless as an "early" check -- clamp defensively in case of a
        # misconfigured .env rather than trusting the raw value.
        if stall_minutes >= timeout:
            stall_minutes = 0
        stall_max_fluct = (getattr(config, "NEAR_TP_STALL_MAX_FLUCTUATION_PCT", 0) or 0) / 100.0

        def _parse_ts(iso_ts):
            ts = datetime.fromisoformat(iso_ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts

        # (trade_id, action, reason, snapshots) where action is "start" (set
        # the clock to now), "reset" (clear it), "snapshot" (update the
        # trailing price-history list), or "close" (timeout or stall).
        actions = []
        for trade in open_trades:
            entry = trade.get("entry")
            target = trade.get("take_profit")
            if not entry or not target or entry == target:
                continue   # malformed record -- nothing sane to measure progress against
            is_bull = trade["direction"] == "bullish"
            reward = (target - entry) if is_bull else (entry - target)
            if reward <= 0:
                continue   # target isn't actually beyond entry in the trade's own direction
            progress = ((live_price - entry) if is_bull else (entry - live_price)) / reward

            near_tp_since = trade.get("near_tp_since")
            if progress >= threshold:
                if near_tp_since is None:
                    actions.append((trade["id"], "start", None, None))
                    continue

                started = _parse_ts(near_tp_since)
                elapsed_minutes = (now - started).total_seconds() / 60.0
                if elapsed_minutes >= timeout:
                    actions.append((trade["id"], "close", "timeout", None))
                    continue

                if stall_minutes <= 0:
                    continue  # stall check disabled/misconfigured -- only the full timeout applies

                snapshots = list(trade.get("near_tp_snapshots") or [])
                snapshots.append([now.isoformat(), live_price])
                cutoff = now - timedelta(minutes=stall_minutes)
                trimmed = [[iso_ts, px] for iso_ts, px in snapshots if _parse_ts(iso_ts) >= cutoff]

                # Only judge "stalled" once we actually have a full stall
                # window's worth of history -- i.e. the oldest snapshot we
                # kept is at (or older than) the cutoff, not just the first
                # reading since the clock started.
                have_full_window = elapsed_minutes >= stall_minutes and trimmed and _parse_ts(trimmed[0][0]) <= cutoff + timedelta(seconds=61)
                if have_full_window:
                    prices_in_window = [px for _, px in trimmed]
                    fluct_pct = (max(prices_in_window) - min(prices_in_window)) / entry
                    if fluct_pct <= stall_max_fluct:
                        actions.append((trade["id"], "close", "stall", None))
                        continue

                actions.append((trade["id"], "snapshot", None, trimmed))
            elif near_tp_since is not None:
                actions.append((trade["id"], "reset", None, None))

        if not actions:
            return []

        newly_closed = []
        now_iso = now.isoformat()
        with _LOCK:
            id_map = {t["id"]: t for t in self._trades}
            for trade_id, action, reason, snapshots in actions:
                t = id_map.get(trade_id)
                if t is None or t["status"] != "open":
                    continue   # already closed by a parallel call this tick
                if action == "start":
                    t["near_tp_since"] = now_iso
                    t["near_tp_snapshots"] = [[now_iso, live_price]]
                elif action == "reset":
                    t["near_tp_since"] = None
                    t["near_tp_snapshots"] = []
                elif action == "snapshot":
                    t["near_tp_snapshots"] = snapshots
                elif action == "close":
                    t["status"] = "win"
                    t["exit_price"] = live_price
                    t["closed_at"] = now_iso
                    t["close_reason"] = (
                        "auto (near-TP stall)" if reason == "stall" else "auto (near-TP timeout)"
                    )
                    t["near_tp_since"] = None
                    t["near_tp_snapshots"] = []
                    self._settle_account_balance(t)
                    newly_closed.append(dict(t))
            self._save()
        return newly_closed

    def get_detailed_stats(self) -> dict:
        """
        Performance breakdowns by ticker, strategy, and day-of-week (Berlin time).
        Only win/loss trades (SL or TP actually hit) are included.
        """
        self.refresh()
        closed = [t for t in self._trades if t["status"] in ("win", "loss")]

        def _pnl_pct(t):
            try:
                entry = float(t["entry"])
                exit_p = float(t["exit_price"])
                if entry <= 0:
                    return None
                is_bull = t["direction"] == "bullish"
                return ((exit_p - entry) / entry * 100) if is_bull else ((entry - exit_p) / entry * 100)
            except (TypeError, KeyError, ZeroDivisionError):
                return None

        def _closed_dow(t):
            _DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            try:
                dt = datetime.fromisoformat(t.get("closed_at", ""))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if _BERLIN_TZ:
                    dt = dt.astimezone(_BERLIN_TZ)
                return _DOW[dt.weekday()]
            except Exception:
                return None

        def _build(grouped):
            rows = []
            for key, trades in grouped.items():
                wins = [t for t in trades if t["status"] == "win"]
                pnls = [p for t in trades if (p := _pnl_pct(t)) is not None]
                rows.append({
                    "key": key,
                    "total": len(trades),
                    "wins": len(wins),
                    "losses": len(trades) - len(wins),
                    "win_rate": round(len(wins) / len(trades) * 100) if trades else None,
                    "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
                })
            return rows

        by_ticker = defaultdict(list)
        by_strategy = defaultdict(list)
        by_dow_raw = defaultdict(list)
        _DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for t in closed:
            by_ticker[t["ticker"]].append(t)
            # See primary_strategy_label's docstring: t["strategy"] itself is
            # a fixed placeholder on every trade the live engine logs, so
            # grouping by it directly would put every closed trade in one
            # bucket instead of breaking down by what actually confirmed it.
            by_strategy[primary_strategy_label(t)].append(t)
            dow = _closed_dow(t)
            if dow:
                by_dow_raw[dow].append(t)

        ticker_rows = sorted(_build(by_ticker), key=lambda r: r["total"], reverse=True)
        strategy_rows = sorted(_build(by_strategy), key=lambda r: r["total"], reverse=True)
        dow_rows = sorted(_build(by_dow_raw), key=lambda r: _DOW_ORDER.index(r["key"]))

        total_wins = len([t for t in closed if t["status"] == "win"])
        all_pnls = [p for t in closed if (p := _pnl_pct(t)) is not None]
        return {
            "total_closed": len(closed),
            "total_wins": total_wins,
            "total_losses": len(closed) - total_wins,
            "overall_win_rate": round(total_wins / len(closed) * 100) if closed else None,
            "overall_avg_pnl": round(sum(all_pnls) / len(all_pnls), 2) if all_pnls else None,
            "by_ticker": ticker_rows,
            "by_strategy": strategy_rows,
            "by_dow": dow_rows,
        }

    def get_chart_data(self) -> dict:
        """
        Returns per-trade data for the JS-rendered performance analytics page.

        Includes:
          - trades: list of closed trades with pnl_pct, holding_days, opened_at, etc.
          - spy_cum: {date_str: cumulative_%_return} from first trade's open date,
                     for benchmark overlay. Empty dict if yfinance is unavailable.
        """
        self.refresh()
        closed = sorted(
            [t for t in self._trades if t["status"] in ("win", "loss")],
            key=lambda t: t.get("closed_at") or "",
        )

        trades_out = []
        for t in closed:
            try:
                entry = float(t.get("entry") or 0)
            except (TypeError, ValueError):
                entry = 0.0
            try:
                exit_p = float(t.get("exit_price") or 0)
            except (TypeError, ValueError):
                exit_p = 0.0

            is_bull = t.get("direction") == "bullish"
            pnl_pct = None
            if entry > 0 and exit_p > 0:
                pnl_pct = round(
                    ((exit_p - entry) / entry * 100) if is_bull
                    else ((entry - exit_p) / entry * 100),
                    3,
                )

            opened_at = t.get("opened_at") or ""
            closed_at = t.get("closed_at") or ""
            holding_days = None
            try:
                if opened_at and closed_at:
                    oa = datetime.fromisoformat(opened_at)
                    ca = datetime.fromisoformat(closed_at)
                    holding_days = round((ca - oa).total_seconds() / 86400, 2)
            except Exception:
                pass

            # R-multiple = actual P&L / originally-planned risk (entry -> stop
            # loss), so a "+2.4R" win reads as "2.4x what I was risking" --
            # comparable across trades with very different stop distances,
            # unlike raw pnl_pct alone.
            try:
                stop_loss = float(t.get("stop_loss") or 0)
            except (TypeError, ValueError):
                stop_loss = 0.0
            r_multiple = None
            if entry > 0 and stop_loss > 0 and pnl_pct is not None:
                risk_pct = abs(entry - stop_loss) / entry * 100
                if risk_pct > 0:
                    r_multiple = round(pnl_pct / risk_pct, 3)

            trades_out.append({
                "id":           t.get("id"),
                "ticker":       t.get("ticker", ""),
                "direction":    t.get("direction", ""),
                "horizon_key":  t.get("horizon_key") or "",
                "entry":        entry,
                "exit_price":   exit_p,
                "stop_loss":    stop_loss or None,
                "pnl_pct":      pnl_pct,
                "r_multiple":   r_multiple,
                "status":       t.get("status", ""),
                "opened_at":    opened_at,
                "closed_at":    closed_at,
                "holding_days": holding_days,
                # The REAL confirming method (see primary_strategy_label), not
                # the raw t["strategy"] field -- which is the same hardcoded
                # "S/R Confluence" default on every trade the live engine
                # logs and would otherwise make every row here look identical.
                "strategy":     primary_strategy_label(t),
                # Bug fix: this used to read t.get("confidence"), a key that
                # doesn't exist on a trade record (the real field is
                # "confidence_level") -- every trade silently fell back to 0
                # and showed as "Lv0" everywhere on this page.
                "confidence":   int(t.get("confidence_level") or 0),
                # Position-size snapshot (see account.py) and this trade's
                # real currency effect on the account -- None for anything
                # closed before this feature existed, or that never got a
                # valid sizing snapshot at open time.
                "shares":               t.get("shares"),
                "position_value":       t.get("position_value"),
                "sizing_mode":          t.get("sizing_mode"),
                "realized_pnl_amount":  t.get("realized_pnl_amount"),
                "account_balance_after": t.get("account_balance_after"),
            })

        # SPY benchmark: cumulative % return from the first trade's open date.
        # Silently skipped if yfinance is unavailable or there are no trades.
        spy_cum: dict = {}
        if trades_out:
            try:
                import yfinance as yf  # already in requirements.txt
                start_date = min(
                    t["opened_at"][:10] for t in trades_out if t["opened_at"]
                )
                spy_df = yf.download(
                    "SPY", start=start_date, progress=False, auto_adjust=True
                )
                if spy_df is not None and not spy_df.empty:
                    closes = spy_df["Close"].dropna()
                    base = float(closes.iloc[0])
                    if base > 0:
                        spy_cum = {
                            str(idx.date()): round((float(val) - base) / base * 100, 3)
                            for idx, val in closes.items()
                        }
            except Exception:
                pass

        # Real account balance over time -- the currency-based counterpart
        # to the %-based equity curve above, built from the actual
        # settlements applied by _settle_account_balance() (plus any manual
        # `!account balance` overrides), not re-derived from trades_out --
        # it's the account's own ground truth, including anything that
        # happened outside the trade log (a manual override, a trade closed
        # before this feature existed and so never settled anything).
        account_cfg = account_module.load_account_config()

        return {
            "trades":  trades_out,
            "spy_cum": spy_cum,
            "account_balance": account_cfg.get("balance"),
            "balance_history": account_cfg.get("balance_history", []),
            "sizing_mode": account_cfg.get("sizing_mode"),
            "position_pct": account_cfg.get("position_pct"),
            "risk_pct": account_cfg.get("risk_pct"),
        }
