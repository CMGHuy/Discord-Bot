"""v210: market_shock notices for the v197 notify queue.

Renderer half (V210-1): the event's payload becomes one plain status embed --
headline, trigger numbers and, on an entry into SHOCK, one line per open long
for someone with resting orders at a broker. Never an alert embed: no Kind, no
disclaimer. Pure: no database, no network.
"""
from datetime import datetime

import discord

from swingbot.core import presentation as ui
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
    embed = ui.PushEmbed(title=title, description=_body(payload),
                         colour=discord.Color(COLOURS[payload["label"]]))
    embed.push_text = title
    embed.kind = None
    embed.set_footer(text=f"Event {event['event_id']}")
    embed.timestamp = datetime.fromisoformat(payload["occurred_at"])
    return embed
