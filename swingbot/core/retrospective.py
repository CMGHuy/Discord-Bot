"""
Daily end-of-session retrospective builder.

Compiles everything that happened during a trading day (Berlin time) into:
  - per-trade table (opened today, closed today, still open)
  - win/loss/P&L stats for the day
  - strategy & horizon breakdown
  - confidence-level breakdown
  - data-driven lessons derived from the day's patterns
  - concrete parameter-tuning suggestions

Designed to be channel-agnostic: build_daily_retrospective() returns a list
of plain strings and discord.Embed-compatible dicts; the caller posts them
wherever it wants (DISCORD_CHANNEL_RETROSPECTIVE_ID, DISCORD_CHANNEL_TRADES_HISTORY_ID, etc.).
"""
import datetime as dt
import logging
from collections import defaultdict

try:
    from zoneinfo import ZoneInfo
    _BERLIN_TZ = ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None

log = logging.getLogger("swing-bot.retrospective")

_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_berlin(iso_str: str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        d = dt.datetime.fromisoformat(iso_str)
        if d.tzinfo is None:
            import datetime as _dt
            d = d.replace(tzinfo=_dt.timezone.utc)
        if _BERLIN_TZ:
            d = d.astimezone(_BERLIN_TZ)
        return d
    except Exception:
        return None


def _berlin_hm(iso_str: str) -> str:
    """Return HH:MM in Berlin time, or '—'."""
    d = _to_berlin(iso_str)
    return d.strftime("%H:%M") if d else "—"


def _berlin_date(iso_str: str) -> dt.date | None:
    d = _to_berlin(iso_str)
    return d.date() if d else None


def _pnl_pct(trade: dict) -> float | None:
    entry = trade.get("entry")
    exit_ = trade.get("exit_price")
    if not entry or not exit_:
        return None
    pnl = (exit_ - entry) / entry * 100
    if trade.get("direction") == "bearish":
        pnl = -pnl
    return round(pnl, 2)


def _r_multiple(trade: dict) -> float | None:
    entry = trade.get("entry")
    sl    = trade.get("stop_loss")
    exit_ = trade.get("exit_price")
    if not entry or not sl or not exit_:
        return None
    risk = abs(entry - sl)
    if risk == 0:
        return None
    pnl_abs = (exit_ - entry) if trade.get("direction") == "bullish" else (entry - exit_)
    return round(pnl_abs / risk, 2)


def _days_held(trade: dict) -> int | None:
    opened = _to_berlin(trade.get("opened_at", ""))
    closed = _to_berlin(trade.get("closed_at", ""))
    if not opened or not closed:
        return None
    return (closed.date() - opened.date()).days


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_daily_retrospective(all_trades: list, today: dt.date | None = None) -> list[str]:
    """
    Returns a list of strings to post to Discord in order.
    Each string is a ready-to-send Discord message (plain text or markdown).
    Pass `today` to override the date (useful for testing); defaults to
    today in Europe/Berlin time.
    """
    if today is None:
        if _BERLIN_TZ:
            today = dt.datetime.now(_BERLIN_TZ).date()
        else:
            today = dt.date.today()

    date_label = today.strftime("%A, %-d %B %Y") if hasattr(today, "strftime") else str(today)

    # ── Partition trades ──────────────────────────────────────────────────
    opened_today    = []   # opened today (any status)
    closed_today    = []   # closed today (win/loss/manually closed)
    still_open      = []   # opened any day, still open right now

    for t in all_trades:
        o_date = _berlin_date(t.get("opened_at", ""))
        c_date = _berlin_date(t.get("closed_at", ""))
        status = t.get("status", "open")

        if status == "open":
            still_open.append(t)
        if o_date == today:
            opened_today.append(t)
        if c_date == today and status != "open":
            closed_today.append(t)

    wins   = [t for t in closed_today if t["status"] == "win"]
    losses = [t for t in closed_today if t["status"] == "loss"]
    manual = [t for t in closed_today if t["status"] not in ("win", "loss")]

    n_closed  = len(closed_today)
    n_wins    = len(wins)
    n_losses  = len(losses)
    win_rate  = round(n_wins / n_closed * 100) if n_closed else None

    pnls      = [p for t in closed_today if (p := _pnl_pct(t)) is not None]
    avg_pnl   = round(sum(pnls) / len(pnls), 2) if pnls else None
    total_pnl = round(sum(pnls), 2) if pnls else None

    r_mults   = [r for t in closed_today if (r := _r_multiple(t)) is not None]
    avg_r     = round(sum(r_mults) / len(r_mults), 2) if r_mults else None

    messages: list[str] = []

    # ── Part 1: Header + at-a-glance ─────────────────────────────────────
    wr_emoji  = "🟢" if (win_rate or 0) >= 60 else ("🟡" if (win_rate or 0) >= 40 else "🔴")
    pnl_emoji = "📈" if (avg_pnl or 0) >= 0 else "📉"

    header = (
        f"## 📊 Daily Retrospective — {date_label}\n"
        f"─────────────────────────────\n"
        f"**Trades opened today:** {len(opened_today)}\n"
        f"**Trades closed today:** {n_closed}  "
        f"({n_wins} WIN · {n_losses} LOSS{(' · ' + str(len(manual)) + ' manual') if manual else ''})\n"
    )
    if win_rate is not None:
        header += f"**Day win rate:** {wr_emoji} {win_rate}%\n"
    if avg_pnl is not None:
        header += f"**Avg P&L per trade:** {pnl_emoji} {avg_pnl:+.2f}%\n"
    if total_pnl is not None:
        header += f"**Sum P&L (paper):** {total_pnl:+.2f}%\n"
    if avg_r is not None:
        header += f"**Avg R-multiple:** {avg_r:+.2f}R\n"
    if still_open:
        header += f"**Still open:** {len(still_open)} trade(s)\n"

    if n_closed == 0 and not opened_today:
        header += "\n_No trading activity today._"
    messages.append(header)

    # ── Part 2: Closed-today trade table ─────────────────────────────────
    if closed_today:
        lines = ["**Closed today:**",
                 "```",
                 f"{'Ticker':<7} {'Dir':<5} {'Strategy':<18} {'Conf':<5} {'Open':<6} {'Close':<6} {'P&L%':>6} {'R':>5} {'Days':>4} {'Out':<6}",
                 "─" * 75]
        for t in sorted(closed_today, key=lambda x: x.get("closed_at", "")):
            pnl = _pnl_pct(t)
            r   = _r_multiple(t)
            days = _days_held(t)
            strategy = t.get("strategy", "?")[:17]
            direction = "▲ Long" if t["direction"] == "bullish" else "▼ Short"
            out = {"win": "WIN ✓", "loss": "LOSS ✗"}.get(t["status"], "CLSD")
            lines.append(
                f"{t['ticker']:<7} {direction:<5} {strategy:<18} Lv{t.get('confidence_level','-'):<3} "
                f"{_berlin_hm(t.get('opened_at','')):<6} {_berlin_hm(t.get('closed_at','')):<6} "
                f"{(f'{pnl:+.2f}%' if pnl is not None else '—'):>6} "
                f"{(f'{r:+.2f}' if r is not None else '—'):>5} "
                f"{(str(days) if days is not None else '—'):>4} "
                f"{out:<6}"
            )
        lines.append("```")
        messages.append("\n".join(lines))

    # ── Part 3: Still-open positions ─────────────────────────────────────
    if still_open:
        lines = ["**Still open (all active positions):**", "```",
                 f"{'Ticker':<7} {'Dir':<5} {'Strategy':<18} {'Conf':<5} {'Opened':<17} {'Entry':>7} {'SL':>7} {'TP':>7}",
                 "─" * 75]
        for t in still_open:
            direction = "▲ Long" if t["direction"] == "bullish" else "▼ Short"
            opened_str = _berlin_hm(t.get("opened_at", ""))
            opened_date = _berlin_date(t.get("opened_at", ""))
            date_pfx = opened_date.strftime("%-d %b") if opened_date else "?"
            lines.append(
                f"{t['ticker']:<7} {direction:<5} {t.get('strategy','?')[:17]:<18} Lv{t.get('confidence_level','-'):<3} "
                f"{date_pfx + ' ' + opened_str:<17} "
                f"{t.get('entry',0):>7.2f} {t.get('stop_loss',0):>7.2f} {t.get('take_profit',0):>7.2f}"
            )
        lines.append("```")
        messages.append("\n".join(lines))

    # ── Part 4: Breakdown tables ──────────────────────────────────────────
    if closed_today:
        breakdown_msg = _build_breakdown(closed_today)
        if breakdown_msg:
            messages.append(breakdown_msg)

    # ── Part 5: Lessons learned + tuning suggestions ──────────────────────
    lessons, suggestions = _analyse(closed_today, opened_today, still_open)
    if lessons or suggestions:
        insight_lines = ["**🔍 Lessons & Tuning Suggestions**"]
        if lessons:
            insight_lines.append("\n**Observations:**")
            for l in lessons:
                insight_lines.append(f"• {l}")
        if suggestions:
            insight_lines.append("\n**Parameter / algorithm improvements:**")
            for s in suggestions:
                insight_lines.append(f"→ {s}")
        messages.append("\n".join(insight_lines))

    return messages


# ---------------------------------------------------------------------------
# Breakdown tables
# ---------------------------------------------------------------------------

def _build_breakdown(closed: list) -> str:
    by_strategy: dict[str, list] = defaultdict(list)
    by_horizon:  dict[str, list] = defaultdict(list)
    by_conf:     dict[int, list] = defaultdict(list)

    for t in closed:
        by_strategy[t.get("strategy", "Unknown")].append(t)
        by_horizon[t.get("horizon_key", "?")].append(t)
        by_conf[t.get("confidence_level", 0)].append(t)

    def _row(name, trades):
        w = sum(1 for t in trades if t["status"] == "win")
        l = sum(1 for t in trades if t["status"] == "loss")
        wr = round(w / len(trades) * 100) if trades else None
        pnls = [p for t in trades if (p := _pnl_pct(t)) is not None]
        ap = round(sum(pnls) / len(pnls), 2) if pnls else None
        wr_str = f"{wr}%" if wr is not None else "—"
        ap_str = f"{ap:+.2f}%" if ap is not None else "—"
        return f"  {name:<22} {len(trades):>3}   {w:>3}W  {l:>3}L   {wr_str:>6}   {ap_str:>7}"

    lines = ["**Breakdown:**", "```"]
    hdr = f"  {'Name':<22} {'#':>3}   {'W':>3}   {'L':>3}   {'WR%':>6}   {'Avg P&L':>7}"
    sep = "─" * 55

    if by_strategy:
        lines += [f"  BY STRATEGY", hdr, sep]
        for strat, trades in sorted(by_strategy.items(), key=lambda kv: -len(kv[1])):
            lines.append(_row(strat[:22], trades))

    if by_horizon:
        lines += ["", f"  BY HORIZON", hdr, sep]
        for hz, trades in sorted(by_horizon.items(), key=lambda kv: -len(kv[1])):
            lines.append(_row(hz[:22], trades))

    if by_conf:
        lines += ["", f"  BY CONFIDENCE LEVEL", hdr, sep]
        for lv in sorted(by_conf.keys()):
            lines.append(_row(f"Level {lv}", by_conf[lv]))

    lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pattern analysis → lessons + suggestions
# ---------------------------------------------------------------------------

def _analyse(closed: list, opened_today: list, still_open: list) -> tuple[list[str], list[str]]:
    lessons:     list[str] = []
    suggestions: list[str] = []

    if not closed and not opened_today:
        return lessons, suggestions

    wins   = [t for t in closed if t["status"] == "win"]
    losses = [t for t in closed if t["status"] == "loss"]
    n      = len(closed)

    if n == 0:
        if opened_today:
            lessons.append(f"{len(opened_today)} trade(s) were opened today but none closed yet — check back tomorrow.")
        return lessons, suggestions

    win_rate = len(wins) / n * 100

    # --- Confidence level analysis ---
    conf_wins:   dict[int, int] = defaultdict(int)
    conf_totals: dict[int, int] = defaultdict(int)
    for t in closed:
        lv = t.get("confidence_level", 0)
        conf_totals[lv] += 1
        if t["status"] == "win":
            conf_wins[lv] += 1

    for lv in sorted(conf_totals):
        total = conf_totals[lv]
        wins_lv = conf_wins[lv]
        wr = round(wins_lv / total * 100)
        if total >= 2 and wr == 0:
            lessons.append(f"Lv{lv} trades had 0% win rate today ({total} trades, all losses).")
            suggestions.append(f"Consider raising `MIN_ALERT_CONFIDENCE_LEVEL` to {lv + 1} to skip Lv{lv} signals.")
        elif total >= 2 and wr == 100:
            lessons.append(f"Lv{lv} trades were perfect today ({total} trades, all wins).")

    # --- Strategy analysis ---
    by_strat: dict[str, list] = defaultdict(list)
    for t in closed:
        by_strat[t.get("strategy", "Unknown")].append(t)

    for strat, trades in by_strat.items():
        if len(trades) < 2:
            continue
        strat_wr = sum(1 for t in trades if t["status"] == "win") / len(trades) * 100
        if strat_wr == 0:
            lessons.append(f"'{strat}' had 0% win rate today ({len(trades)} trades).")
            suggestions.append(f"Review setup rules for '{strat}' — may need stricter confluence requirements.")
        elif strat_wr == 100:
            lessons.append(f"'{strat}' was flawless today ({len(trades)} trades, all wins).")

    # --- Direction (counter-trend) analysis ---
    bull_wins = sum(1 for t in wins if t["direction"] == "bullish")
    bull_all  = sum(1 for t in closed if t["direction"] == "bullish")
    bear_wins = sum(1 for t in wins if t["direction"] == "bearish")
    bear_all  = sum(1 for t in closed if t["direction"] == "bearish")

    if bull_all >= 2 and bear_all >= 2:
        bull_wr = round(bull_wins / bull_all * 100)
        bear_wr = round(bear_wins / bear_all * 100)
        if abs(bull_wr - bear_wr) >= 40:
            better  = "Long" if bull_wr > bear_wr else "Short"
            worse   = "Short" if bull_wr > bear_wr else "Long"
            worse_wr = bear_wr if bull_wr > bear_wr else bull_wr
            lessons.append(f"{better} trades strongly outperformed {worse} trades today ({max(bull_wr,bear_wr)}% vs {worse_wr}%).")
            suggestions.append(f"Check market regime: if the broader trend is against {worse} trades, raise `HTF_COUNTER_TREND_PENALTY`.")

    # --- R-multiple and risk/reward ---
    r_mults = [r for t in losses if (r := _r_multiple(t)) is not None]
    if r_mults:
        avg_loss_r = round(sum(r_mults) / len(r_mults), 2)
        if avg_loss_r < -1.5:
            lessons.append(f"Losses averaged {avg_loss_r:.2f}R — stops may be too far from entry on losing trades.")
            suggestions.append("Consider tightening `MAX_STOP_LOSS_PCT` to reduce loss magnitude per trade.")

    win_rs = [r for t in wins if (r := _r_multiple(t)) is not None]
    loss_rs = [r for t in losses if (r := _r_multiple(t)) is not None]
    if win_rs and loss_rs:
        avg_win_r  = round(sum(win_rs)  / len(win_rs),  2)
        avg_loss_r = round(sum(loss_rs) / len(loss_rs), 2)
        rr = round(abs(avg_win_r / avg_loss_r), 2) if avg_loss_r else None
        if rr is not None:
            lessons.append(f"Average win: {avg_win_r:+.2f}R  |  Average loss: {avg_loss_r:+.2f}R  |  Actual RR ratio: {rr:.2f}:1")
            if rr < 1.2:
                suggestions.append(
                    f"Actual RR {rr:.2f}:1 is below 1.2 — raise `MIN_RISK_REWARD_RATIO` to filter out low-reward setups."
                )

    # --- Horizon analysis ---
    by_hz: dict[str, list] = defaultdict(list)
    for t in closed:
        by_hz[t.get("horizon_key", "?")].append(t)

    for hz, trades in by_hz.items():
        if len(trades) < 2:
            continue
        hz_wr = sum(1 for t in trades if t["status"] == "win") / len(trades) * 100
        if hz_wr == 0:
            lessons.append(f"All '{hz}' horizon trades closed as losses today ({len(trades)} trades).")
            suggestions.append(f"Consider whether '{hz}' horizon is suitable for current market conditions.")

    # --- Trade duration analysis ---
    same_day = [t for t in closed
                if _berlin_date(t.get("opened_at","")) == _berlin_date(t.get("closed_at",""))]
    if same_day:
        sd_losses = [t for t in same_day if t["status"] == "loss"]
        if sd_losses:
            lessons.append(
                f"{len(sd_losses)} of {len(same_day)} same-day-close trade(s) were losses — "
                f"rapid SL hits may indicate entries at wrong price levels or stops too tight."
            )
            suggestions.append(
                "Review same-day closures: if SL was hit within hours, the entry timing or stop placement needs work."
            )

    # --- Still-open trade risk reminder ---
    if still_open:
        near_sl = []
        for t in still_open:
            entry = t.get("entry")
            sl    = t.get("stop_loss")
            if entry and sl:
                dist_pct = abs(entry - sl) / entry * 100
                if dist_pct < 1.5:
                    near_sl.append(t["ticker"])
        if near_sl:
            lessons.append(f"Open positions with SL < 1.5% from entry: {', '.join(near_sl)} — watch these closely.")

    # --- Overall day summary lesson ---
    if win_rate >= 70:
        lessons.append(f"Strong day: {win_rate:.0f}% win rate. Today's setup quality and market conditions aligned well.")
    elif win_rate < 40 and n >= 3:
        lessons.append(f"Difficult day: {win_rate:.0f}% win rate on {n} trades. Review whether market conditions match the bot's assumptions (trending vs choppy).")
        suggestions.append("If multiple consecutive bad days: check ADX filter thresholds — the bot may be firing in low-trend, choppy tape.")

    return lessons, suggestions
