"""v200 dry run: recover plan issue times from the alerts channel's own history.

READ ONLY. Nothing is written to Discord, the database, or any file; the CSV goes
to stdout and a summary to stderr.

What it reads
  * Discord: ``config.DISCORD_CHANNEL_TRADES_ID`` only (never the ``..._SIMPLE_ID``
    mirror). Bot-authored messages from 2026-07-01 to 2026-09-16 Eastern inclusive.
  * Postgres: plans whose ``created_at`` falls in that range and that carry no
    ``issued_at`` (a read-only transaction).

How
  ``Client.login`` without the gateway, so the live bot's session is untouched.
  The token comes from the container environment and is never printed.

Embed layouts
  * Aug-Sep 2026 full alert: title ``"<chips> · 🟢 BULLISH — AAPL"``; field ``Setup``
    (``"<strategy>"`` or ``"<strategy>  +N more horizon(s)"``); field ``Swing type``
    (the horizon label). No plan id.
  * July 2026 (V200-6 sample): title ``"<chips> 🟢 LONG (buy) — AAPL"`` (``SHORT (sell)``
    for bearish), the same ``Setup`` / ``Swing type`` fields; from 2026-07-19 the
    footer carries ``plan <8 chars>`` (title ``"🅲 ⚠️ WEAK · ⭐ 🟢 LONG (buy) — GOOGL"``).
  * From 2026-09-30: title ``"🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐"``; footer
    ``"... · plan abcd1234"`` (8-char prefix); ``url`` = ``<base>/plans/<full plan_id>``.

Match rules
  1. Exact first: an alert with a plan id resolves to the plans whose id equals it
     (or starts with it, when 8 characters). It is an exact candidate only when it
     resolves to exactly one plan. A plan with exactly one exact candidate is
     ``exact``; with two or more it is ``none``. Plans with an exact candidate leave
     the key pool, and every alert carrying a plan id stays out of the key pool.
  2. Key: a remaining plan's candidates are the remaining alerts with equal ticker,
     direction, strategy and horizon key, posted (Eastern date) on the plan's
     ``created_date`` or the next NYSE session.
  3. One-to-one: a plan is ``key``-matched when it has exactly one candidate and
     that message is a candidate for exactly one plan. Otherwise every plan
     involved is ``none``.

Run
  bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot \
      python - [--sample N]" < scripts/ops/backfill_issued_at_discord.py > out.csv

Exit codes: 0 done, 1 Discord login/HTTP error, 2 token or channel unset.
"""
import argparse
import asyncio
import csv
import datetime as dt
import os
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass

from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS

HORIZON_LABEL_TO_KEY: dict[str, str] = {spec["label"]: key for key, spec in HORIZONS.items()}
CSV_COLUMNS = ("plan_id", "plan_candidates", "message_candidates", "message_id",
               "issued_at", "lag_hours", "method")
WINDOW_FIRST = dt.date(2026, 7, 1)
WINDOW_LAST = dt.date(2026, 9, 16)

_SIDE_RE = re.compile(r"(?i:\b(LONG|SHORT|BULLISH|BEARISH)\b)(?:\s+\((?:buy|sell)\))?\s+(?:—\s+)?([A-Z0-9][A-Z0-9.^=\-]*)")
_MORE_RE = re.compile(r"\s+\+\d+ more horizon\(s\)$")
_URL_ID_RE = re.compile(r"/plans/([0-9a-f-]{8,})")
_FOOTER_ID_RE = re.compile(r"\bplan ([0-9a-f]{8})\b")
_SIDE_NAMES = {"long": "bullish", "bullish": "bullish", "short": "bearish", "bearish": "bearish"}
_CALENDAR = None


@dataclass(frozen=True)
class PlanKey:
    plan_id: str
    ticker: str
    direction: str
    strategy: str
    horizon_key: str
    created_date: dt.date


@dataclass(frozen=True)
class AlertKey:
    message_id: str
    posted_at: dt.datetime
    plan_id: str | None
    ticker: str | None
    direction: str | None
    strategy: str | None
    horizon_key: str | None


@dataclass(frozen=True)
class MatchRow:
    plan_id: str
    plan_candidates: int
    message_candidates: int
    message_id: str | None
    issued_at: str | None
    lag_hours: float | None
    method: str


# --------------------------------------------------------------------------- parsing


def _norm_side(value: str | None) -> str:
    text = (value or "").lower()
    return _SIDE_NAMES.get(text, text)


def _field(embed: dict, name: str) -> str | None:
    for item in embed.get("fields") or ():
        if item.get("name") == name:
            return item.get("value")
    return None


def _plan_id(embed: dict) -> str | None:
    found = _URL_ID_RE.search(embed.get("url") or "")
    if found:
        return found.group(1)
    found = _FOOTER_ID_RE.search((embed.get("footer") or {}).get("text") or "")
    return found.group(1) if found else None


def _strategy(embed: dict) -> str | None:
    value = _field(embed, "Setup")
    return _MORE_RE.sub("", value).strip() if value else None


def _horizon_key(embed: dict) -> str | None:
    value = _field(embed, "Swing type")
    return HORIZON_LABEL_TO_KEY.get(value.strip()) if value else None


def alert_key(message: dict) -> AlertKey | None:
    """Parse one bot message into its match key; None when it is not a plan alert."""
    embed = next((e for e in message.get("embeds") or () if e.get("title")), None)
    if embed is None:
        return None
    side = _SIDE_RE.search(embed["title"])
    plan_id = _plan_id(embed)
    if side is None and plan_id is None:
        return None
    return AlertKey(
        message_id=str(message["id"]),
        posted_at=dt.datetime.fromisoformat(message["created_at"]),
        plan_id=plan_id,
        ticker=side.group(2).upper() if side else None,
        direction=_norm_side(side.group(1)) if side else None,
        strategy=_strategy(embed),
        horizon_key=_horizon_key(embed))


# --------------------------------------------------------------------------- matching


def _eastern_date(ts: dt.datetime) -> dt.date:
    return ts.astimezone(US_MARKET_TZ).date()


def _calendar():
    global _CALENDAR
    if _CALENDAR is None:
        _CALENDAR = nyse_calendar()
    return _CALENDAR


def _key_matches(plan: PlanKey, alert: AlertKey) -> bool:
    fields = (alert.ticker, alert.direction, alert.strategy, alert.horizon_key)
    if None in fields:
        return False
    if fields != (plan.ticker, plan.direction, plan.strategy, plan.horizon_key):
        return False
    return _eastern_date(alert.posted_at) in (plan.created_date,
                                              _calendar().next_session(plan.created_date))


def _resolves_to(alert_id: str, plans: list[PlanKey]) -> list[PlanKey]:
    if len(alert_id) == 8:
        return [p for p in plans if p.plan_id.startswith(alert_id)]
    return [p for p in plans if p.plan_id == alert_id]


def _exact_candidates(plans: list[PlanKey], alerts: list[AlertKey]) -> dict[str, list[AlertKey]]:
    exact: dict[str, list[AlertKey]] = {}
    for alert in alerts:
        if not alert.plan_id:
            continue
        resolved = _resolves_to(alert.plan_id, plans)
        if len(resolved) == 1:
            exact.setdefault(resolved[0].plan_id, []).append(alert)
    return exact


def _lag_hours(plan: PlanKey, alert: AlertKey) -> float:
    start = dt.datetime.combine(plan.created_date, dt.time(0), tzinfo=US_MARKET_TZ)
    return round((alert.posted_at - start).total_seconds() / 3600, 2)


def _none_row(plan: PlanKey, plan_candidates: int, message_candidates: int) -> MatchRow:
    return MatchRow(plan.plan_id, plan_candidates, message_candidates, None, None, None, "none")


def _row_for(plan: PlanKey, alert: AlertKey, method: str) -> MatchRow:
    issued = alert.posted_at.astimezone(dt.timezone.utc).isoformat()
    return MatchRow(plan.plan_id, 1, 1, alert.message_id, issued, _lag_hours(plan, alert), method)


def _exact_row(plan: PlanKey, candidates: list[AlertKey]) -> MatchRow:
    if len(candidates) == 1:
        return _row_for(plan, candidates[0], "exact")
    return _none_row(plan, 1, len(candidates))


def _key_row(plan: PlanKey, candidates: list[AlertKey], plans_per_message: Counter) -> MatchRow:
    most = max((plans_per_message[a.message_id] for a in candidates), default=0)
    if len(candidates) == 1 and most == 1:
        return _row_for(plan, candidates[0], "key")
    return _none_row(plan, most, len(candidates))


def match(plans: list[PlanKey], alerts: list[AlertKey]) -> list[MatchRow]:
    """One row per plan, input order: exact plan id first, then the one-to-one key."""
    exact = _exact_candidates(plans, alerts)
    pool_plans = [p for p in plans if p.plan_id not in exact]
    pool_alerts = [a for a in alerts if not a.plan_id]
    keyed = {p.plan_id: [a for a in pool_alerts if _key_matches(p, a)] for p in pool_plans}
    plans_per_message = Counter(a.message_id for cands in keyed.values() for a in cands)
    return [_exact_row(p, exact[p.plan_id]) if p.plan_id in exact
            else _key_row(p, keyed[p.plan_id], plans_per_message) for p in plans]


# --------------------------------------------------------------------------- output


def _lag_line(lags: list[float]) -> str:
    if not lags:
        return "lag hours: n/a"
    if len(lags) < 2:
        return f"lag hours: min {lags[0]:.2f}, median {lags[0]:.2f}, max {lags[0]:.2f}"
    p25, med, p75 = statistics.quantiles(lags, n=4)
    return (f"lag hours: min {min(lags):.2f}, p25 {p25:.2f}, median {med:.2f}, "
            f"p75 {p75:.2f}, max {max(lags):.2f}")


def summary_lines(rows: list[MatchRow], *, messages_read: int = 0,
                  messages_parsed: int = 0) -> list[str]:
    matched = [r for r in rows if r.method != "none"]
    unmatched = [r for r in rows if r.method == "none"]
    ambiguous = sum(1 for r in unmatched if r.message_candidates > 0 or r.plan_candidates > 1)
    rate = 100 * len(matched) / len(rows) if rows else 0.0
    methods = Counter(r.method for r in matched)
    return [f"matched {len(matched)} of {len(rows)} plans ({rate:.1f}%)",
            f"exact {methods['exact']}, key {methods['key']}",
            f"ambiguous {ambiguous}, no candidate {len(unmatched) - ambiguous}",
            f"messages read {messages_read}, parsed as alerts {messages_parsed}",
            _lag_line([r.lag_hours for r in matched if r.lag_hours is not None])]


def write_csv(rows: list[MatchRow], fh) -> None:
    writer = csv.writer(fh, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(["" if getattr(row, c) is None else getattr(row, c) for c in CSV_COLUMNS])


# --------------------------------------------------------------------------- I/O

_PLANS_SQL = ("SELECT plan_id, ticker, doc->>'direction', strategy, horizon_key, "
              "(created_at AT TIME ZONE 'UTC')::date::text FROM plans "
              "WHERE doc->>'issued_at' IS NULL "
              "AND (created_at AT TIME ZONE 'UTC')::date BETWEEN CAST(:first AS date) "
              "AND CAST(:last AS date) ORDER BY plan_id")


def load_plans() -> list[PlanKey]:
    import sqlalchemy as sa
    from swingbot.core.db.engine import get_engine
    with get_engine().connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = conn.execute(sa.text(_PLANS_SQL), {"first": WINDOW_FIRST.isoformat(),
                                                  "last": WINDOW_LAST.isoformat()}).fetchall()
        conn.rollback()
    return [PlanKey(r[0], (r[1] or "").upper(), _norm_side(r[2]), r[3] or "", r[4] or "",
                    dt.date.fromisoformat(r[5])) for r in rows if r[5]]


async def read_messages(token: str, channel_id: int) -> list[dict]:
    import discord
    client = discord.Client(intents=discord.Intents.none())
    after = dt.datetime.combine(WINDOW_FIRST, dt.time(0), tzinfo=US_MARKET_TZ) - dt.timedelta(seconds=1)
    before = dt.datetime.combine(WINDOW_LAST + dt.timedelta(days=1), dt.time(0), tzinfo=US_MARKET_TZ)
    out = []
    async with client:
        await client.login(token)        # HTTP only: no gateway session beside the live bot
        channel = await client.fetch_channel(channel_id)
        async for msg in channel.history(limit=None, after=after, before=before, oldest_first=True):
            if msg.author.id == client.user.id:
                out.append({"id": str(msg.id), "created_at": msg.created_at.isoformat(),
                            "embeds": [e.to_dict() for e in msg.embeds]})
    return out


def _describe(message: dict) -> list[str]:
    lines = [f"message {message['id']} at {message['created_at']}"]
    for embed in message.get("embeds") or ():
        lines.append(f"  title: {embed.get('title')}")
        lines.append(f"  url: {embed.get('url')}")
        lines.append(f"  footer: {(embed.get('footer') or {}).get('text')}")
        lines += [f"  field {f.get('name')}: {f.get('value')}" for f in embed.get("fields") or ()]
    lines.append(f"  parsed: {alert_key(message)}")
    return lines


def _sample_report(messages: list[dict], n: int) -> None:
    parsed = [m for m in messages if alert_key(m)][:n]
    unparsed = [m for m in messages if not alert_key(m)][:n]
    for label, group in (("PARSED", parsed), ("UNPARSED", unparsed)):
        print(f"== {label} ==", file=sys.stderr)
        for message in group:
            print("\n".join(_describe(message)), file=sys.stderr)


def _run(plans: list[PlanKey], messages: list[dict]) -> None:
    alerts = [k for k in (alert_key(m) for m in messages) if k]
    rows = match(plans, alerts)
    write_csv(rows, sys.stdout)
    print("\n".join(summary_lines(rows, messages_read=len(messages),
                                  messages_parsed=len(alerts))), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=0,
                        help="print N parsed and N unparsed messages to stderr; no CSV")
    args = parser.parse_args(argv)
    sys.path.insert(0, os.getcwd())
    from swingbot import config
    if not config.TOKEN or not config.DISCORD_CHANNEL_TRADES_ID:
        print("Discord token or alerts channel id is not set", file=sys.stderr)
        return 2
    import discord
    try:
        messages = asyncio.run(read_messages(config.TOKEN, int(config.DISCORD_CHANNEL_TRADES_ID)))
    except (discord.LoginFailure, discord.HTTPException) as exc:
        print(f"Discord read failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if args.sample:
        _sample_report(messages, args.sample)
        return 0
    _run(load_plans(), messages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
