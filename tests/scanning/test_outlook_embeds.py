# tests/scanning/test_outlook_embeds.py
"""v144: the outlook's words -- digest, card decoration, wrap-up. Pure rendering."""
import datetime as dt

import discord
import pandas as pd

from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Family, Kind
from swingbot.core.scanning import outlook_context as ctx
from swingbot.core.scanning import outlook_embeds as oe
from swingbot.core.scanning.outlook_types import OutlookLine, OutlookResult
from tests.planning.test_plan_engine_model import _plan

SUNDAY, MONDAY = dt.date(2026, 10, 11), dt.date(2026, 10, 12)


def _line(ticker="AAPL", **kw):
    base = dict(ticker=ticker, direction="bullish", strategy="Break & Retest",
                entry=102.0, stop=100.5, target=106.0)
    base.update(kw)
    return OutlookLine(**base)


def test_the_two_kinds_are_system_notices():
    assert Kind.OUTLOOK.family is Family.SYSTEM and Kind.OUTLOOK_WRAPUP.family is Family.SYSTEM
    assert kinds.badge(Kind.OUTLOOK) == "🌙" and Kind.OUTLOOK_WRAPUP.label == "OUTLOOK WRAP-UP"


def test_no_session_tomorrow():
    text = oe.digest_text(OutlookResult(run_date=dt.date(2027, 3, 25), target=None))
    assert text == "No NYSE session tomorrow (Friday 2027-03-26) — no outlook issued."


def test_unavailable_says_why_and_nothing_else():
    text = oe.digest_text(OutlookResult(run_date=SUNDAY, target=MONDAY, unavailable="no closed SPY daily bar"))
    assert text == "**Outlook for Monday 2026-10-12**\nOutlook unavailable: no closed SPY daily bar"


def test_an_empty_run_is_one_line():
    text = oe.digest_text(OutlookResult(run_date=SUNDAY, target=MONDAY, regime_lines=["SPY: Bullish"]))
    assert text == "**Outlook for Monday 2026-10-12** — no plans, no watch names, no near-misses."


def test_a_full_digest_lists_every_section():
    result = OutlookResult(
        run_date=SUNDAY, target=MONDAY, regime_lines=["SPY: Bullish (SPY +4.1% vs rising 200EMA)"],
        plans=[_line(risk_dollars=120.0), _line("MSFT", risk_dollars=None)],
        watch=[_line("NVDA", strategy="RSI")],
        near_misses=[_line("AMD", reason="risk_cap (stop 2.6% from entry)")],
        skipped=["TSLA"])
    assert oe.digest_text(result).splitlines() == [
        "**Outlook for Monday 2026-10-12**",
        "SPY: Bullish (SPY +4.1% vs rising 200EMA)",
        "**Plans (2)**",
        "• AAPL LONG · Break & Retest · entry 102.00 stop 100.50 target 106.00 · risk $120",
        "• MSFT LONG · Break & Retest · entry 102.00 stop 100.50 target 106.00 · risk n/a",
        f"**Watch — {oe.WATCH_NOTE} (1)**",
        "• NVDA LONG · RSI · entry 102.00 stop 100.50 target 106.00",
        "**Near-misses (1)**",
        "• AMD LONG · Break & Retest · risk_cap (stop 2.6% from entry)",
        "**Skipped — outlook plan already open (1)**: TSLA",
    ]


def test_the_card_gets_its_badge_and_context():
    embed = discord.Embed(description="headline")
    oe.decorate_card(embed, valid_session=MONDAY, context_line="Weekly: above 20w MA, higher lows")
    assert embed.description == "🌙 **Outlook · valid Monday 2026-10-12 only**\nheadline"
    assert [(f.name, f.value) for f in embed.fields] == [
        (oe.CONTEXT_FIELD, "Weekly: above 20w MA, higher lows")]
    bare = discord.Embed(description="x")
    oe.decorate_card(bare, valid_session=MONDAY, context_line=None)
    assert bare.fields == []


def _outlook(plan_id, **kw):
    return _plan(plan_id=plan_id, entry_type="stop_entry", origin="next_session",
                 valid_session=MONDAY.isoformat(), **kw)


def test_the_wrapup_lists_fills_and_reasons_and_counts():
    filled = _outlook("o1", ticker="AAPL")
    filled.entry_price = 102.05
    record_transition(filled, PlanStatus.ACTIVE, reason="stop_entry_fill", at="t")
    missed = _outlook("o2", ticker="MSFT", direction="bearish")
    record_transition(missed, PlanStatus.CANCELLED, reason="never_triggered", at="t")
    missed.cancel_reason_message = "Low 98.60 stopped 0.6% (0.4 ATR) short of the 98.00 trigger"
    broke = _outlook("o3", ticker="NVDA")
    record_transition(broke, PlanStatus.CANCELLED, reason="never_triggered", at="t")
    broke.cancel_reason_message = "High 101.40 stopped 0.6% short of the 102.00 trigger"
    assert oe.wrapup_text(MONDAY, [filled, missed, broke]).splitlines() == [
        "**Outlook wrap-up · Monday 2026-10-12**",
        "• AAPL LONG — filled at 102.05",
        "• MSFT SHORT — cancelled (never_triggered): Low 98.60 stopped 0.6% (0.4 ATR) short of the 98.00 trigger",
        "• NVDA LONG — cancelled (never_triggered): High 101.40 stopped 0.6% short of the 102.00 trigger",
        "3 issued · 1 filled · 2 cancelled (never_triggered ×2)",
    ]


def test_count_line_with_nothing_cancelled():
    assert oe.count_line([]) == "0 issued · 0 filled · 0 cancelled"


def _daily(weeks=30, rising=True):
    days = pd.bdate_range(end=pd.Timestamp("2026-10-09"), periods=weeks * 5)
    step = 0.2 if rising else -0.2
    close = pd.Series([100 + step * i for i in range(len(days))], index=days)
    return pd.DataFrame({"Open": close, "High": close + 0.5, "Low": close - 0.5, "Close": close,
                         "Volume": 1e6})


def test_the_weekly_phrase_reads_the_20_week_ma_and_the_last_two_lows():
    assert ctx.weekly_phrase(_daily()) == "Weekly: above 20w MA, higher lows"
    assert ctx.weekly_phrase(_daily(rising=False)) == "Weekly: below 20w MA, lower lows"
    assert ctx.weekly_phrase(_daily(weeks=10)) is None


def test_the_hourly_phrase_and_the_joined_context_line():
    hourly = pd.DataFrame({"High": [101.0] * 7, "Low": [99.1] + [99.5] * 6, "Close": [100.0] * 7})
    assert ctx.hourly_phrase(hourly, "bullish") == "Hourly: holding 1h swing low 99.10"
    assert ctx.hourly_phrase(hourly, "bearish") == "Hourly: below 1h swing high 101.00"
    assert ctx.hourly_phrase(hourly.head(3), "bullish") is None
    assert ctx.context_line(_daily(), hourly, "bullish") == \
        "Weekly: above 20w MA, higher lows · Hourly: holding 1h swing low 99.10"
    assert ctx.context_line(None, None, "bullish") is None


def test_regime_lines_skip_a_symbol_without_enough_history():
    lines = ctx.regime_lines({"SPY": _daily(weeks=50), "QQQ": _daily(weeks=10)})
    assert len(lines) == 1 and lines[0].startswith("SPY: Bullish")
    assert lines[0].endswith("· Weekly: above 20w MA, higher lows")
