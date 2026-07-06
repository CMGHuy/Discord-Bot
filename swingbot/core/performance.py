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
from datetime import datetime, timezone
from threading import Lock

from swingbot import config

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
_PROXIMITY_STOP_COLOR   = (0xda, 0x6d, 0x6d)   # red   -- same as .stat-value loss color
_PROXIMITY_NEUTRAL_COLOR = (0x5a, 0x62, 0x75)  # grey  -- same as .muted text color
_PROXIMITY_TARGET_COLOR = (0x6d, 0xda, 0x9e)   # green -- same as .stat-value win color


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
        }
        with _LOCK:
            self._trades.append(record)
            self._save()
        return trade_id

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
                newly_closed.append(t)
            if newly_closed:
                self._save()
        return newly_closed

    def get_stats(self, confidence_level: int = None) -> dict:
        self.refresh()
        trades = self._trades if confidence_level is None else [
            t for t in self._trades if t["confidence_level"] == confidence_level
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

    def get_extended_stats(self, confidence_level: int = None) -> dict:
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
        trades = self._trades if confidence_level is None else [
            t for t in self._trades if t["confidence_level"] == confidence_level
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
