"""v210: market_shock notices for the v197 notify queue.

Renderer half (V210-1): the event's payload becomes one plain status embed --
headline, trigger numbers and, on an entry into SHOCK, one line per open long
for someone with resting orders at a broker. Never an alert embed: no Kind, no
disclaimer. Pure: no database, no network.

Payload half (V210-2): open-long rows, the rate limit and the queue event; config is
read only for the target channel.
"""
import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.market import shock
from swingbot.core.presentation import kinds

FOOTER = ("The bot moved no stop and closed nothing. "
          "Stop move-up and long block are pending screen (v209 Track 2).")
THROUGH_STOP = "THROUGH STOP"
NA = "n/a"
NO_LONGS = "No open longs."
LONGS_UNAVAILABLE = "Open longs unavailable: the trade log could not be read."
#: Discord caps a description at 4096 characters; the rest of the body fits in 596.
LONGS_BUDGET = 3500
COLOURS = {shock.SHOCK: kinds.HEALTH_RED, shock.RECOVERY: kinds.WATCH_STOP_ORANGE,
           shock.NORMAL: kinds.HEALTH_GREEN}


def _fmt(value, spec: str, suffix: str = "") -> str:
    return NA if value is None else f"{value:{spec}}{suffix}"


def _age(minutes: int) -> str:
    hours, mins = divmod(max(int(minutes), 0), 60)
    return f"{mins}m" if hours == 0 else f"{hours}h{mins:02d}m"


def _marker(row: dict) -> str:
    if row.get("last") is None:
        return f"stop status unknown: {row['stop']:.2f}"
    if row.get("through_stop"):
        return THROUGH_STOP
    return f"stop at broker untouched: {row['stop']:.2f}"


def long_line(row: dict) -> str:
    r = row.get("open_r")
    r_text = f"{NA} R" if r is None else f"{r:+.2f}R"
    return " · ".join((row["ticker"], f"entry {row['entry']:.2f}", f"stop {row['stop']:.2f}",
                       f"last {_fmt(row.get('last'), '.2f')}", r_text,
                       _age(row.get("age_min", 0)), _marker(row)))


def _vix(reading: dict) -> str:
    level, chg = reading.get("vix_level"), reading.get("vix_chg_pct")
    if level is None:
        return f"VIX {NA}"
    return f"VIX {level:.2f} ({_fmt(chg, '+.1f', '%')})"


def numbers_line(reading: dict) -> str:
    frac, speed = reading.get("breadth_frac"), reading.get("breadth_speed")
    return " · ".join((
        f"breadth {NA if frac is None else f'{frac * 100:.0f}%'}",
        f"sectors {reading.get('sectors_down', 0)}/{reading.get('sectors_total', 0)}",
        f"speed {NA if speed is None else f'{speed * 100:+.0f}pp'}",
        f"SPY {_fmt(reading.get('spy_atr_move'), '+.2f', ' ATR')}",
        f"QQQ {_fmt(reading.get('qqq_atr_move'), '+.2f', ' ATR')}",
        _vix(reading)))


def headline(payload: dict) -> str:
    return f"Market state: {payload['prior_label']} → {payload['label']}"


def _long_block(payload: dict) -> list[str]:
    if payload.get("open_longs_unavailable"):
        return [LONGS_UNAVAILABLE]
    rows = payload["open_longs"]
    if not rows:
        return [NO_LONGS]
    lines, used = [f"Open longs ({len(rows)}):"], 0
    for row in rows:
        line = long_line(row)
        if used + len(line) + 1 > LONGS_BUDGET:
            break
        lines.append(line)
        used += len(line) + 1
    shown = len(lines) - 1
    if shown < len(rows):
        lines.append(f"+{len(rows) - shown} more open longs")
    return lines


def _body(payload: dict) -> str:
    lines = [numbers_line(payload["reading"])]
    if payload["entry_into_shock"]:
        lines += ["", *_long_block(payload), "", FOOTER]
    return "\n".join(lines)


def build_shock_embed(event: dict) -> discord.Embed:
    """The status embed for one validated market_shock event."""
    payload = event["payload"]
    title = headline(payload)
    embed = ui.status_embed(title, _body(payload), COLOURS[payload["label"]])
    embed.set_footer(text=f"Event {event['event_id']}")
    embed.timestamp = datetime.fromisoformat(payload["occurred_at"])
    return embed


KIND = "market_shock"


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _age_min(opened_at, now: datetime) -> int:
    try:
        opened = datetime.fromisoformat(str(opened_at))
    except ValueError:
        return 0
    opened = opened if opened.tzinfo else opened.replace(tzinfo=timezone.utc)
    return max(int((now - opened).total_seconds() // 60), 0)


def _long_row(trade: dict, last_prices: Mapping[str, float], now: datetime) -> dict | None:
    entry, stop = _positive(trade.get("entry")), _positive(trade.get("stop_loss"))
    if entry is None or stop is None:
        return None
    last = _positive(last_prices.get(trade["ticker"]))
    risk = entry - stop
    open_r = None if last is None or risk <= 0 else (last - entry) / risk
    return {"ticker": str(trade["ticker"]), "entry": entry, "stop": stop, "last": last,
            "open_r": open_r, "age_min": _age_min(trade.get("opened_at"), now),
            "through_stop": last is not None and last <= stop}


def open_long_rows(trades: list[dict], last_prices: Mapping[str, float],
                   now: datetime) -> list[dict]:
    """One row per open long, by ticker; shorts and rows without entry/stop are skipped."""
    rows = (_long_row(t, last_prices, now) for t in trades
            if t.get("direction") == "bullish" and t.get("ticker"))
    return sorted((row for row in rows if row is not None), key=lambda row: row["ticker"])


def should_notify(prior_label: str, new_label: str, last_notice_at: datetime | None,
                  now: datetime, min_dwell_min: int) -> bool:
    """One notice per SHOCK_MIN_DWELL_MIN, except a transition into SHOCK."""
    if prior_label == new_label:
        return False
    if new_label == shock.SHOCK or last_notice_at is None:
        return True
    return now - last_notice_at >= timedelta(minutes=min_dwell_min)


def notice_payload(prior: shock.ShockState, new: shock.ShockState,
                   reading: shock.ShockReading, open_longs: list[dict], now: datetime) -> dict:
    return {"label": new.label, "prior_label": prior.label, "occurred_at": now.isoformat(),
            "reading": reading.as_row(), "open_longs": list(open_longs),
            "entry_into_shock": new.label == shock.SHOCK and prior.label != shock.SHOCK}


def notice_event(payload: dict, *, as_of: datetime) -> dict:
    """The queue event; the channel id is computed here, never via bot.get_channel."""
    channel = config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None
    return make_event(transition_id=f"{KIND}:{as_of.isoformat()}", kind=KIND,
                      target_channel_id=channel, occurred_at=payload["occurred_at"],
                      payload=payload)
