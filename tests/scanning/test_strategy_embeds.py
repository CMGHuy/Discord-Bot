"""v110: the strategy signal and its simple-channel mirror are NEW SETUP embeds."""
from types import SimpleNamespace

import discord

from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.scanning.alert_embeds import (build_strategy_alert_embed,
                                                 build_strategy_simple_embed,
                                                 strategy_plan_line)


def _plan(**kw):
    base = dict(plan_id="0123456789ab", ticker="AAPL", strategy="Fibonacci",
                direction="bullish", horizon_key="4w", trigger_price=100.0, stop_loss=94.0,
                tp1=110.0, tp2=None, badge="WEAK", ledger="weak", confidence_level=4)
    base.update(kw)
    return SimpleNamespace(**base)


def test_strategy_signal_title_push_line_stripe_and_footer():
    embed = build_strategy_alert_embed(_plan())
    assert embed.title == "🆕 ▲ LONG AAPL · STRATEGY · Fibonacci"
    assert embed.push_text == "🆕 NEW SETUP · ▲ LONG AAPL · STRATEGY · Fibonacci"
    assert embed.color.value == kinds.SETUP_RAMP[4]
    assert embed.footer.text == f"{tokens.DISCLAIMER} · plan 01234567"


def test_strategy_signal_leads_with_the_levels_block():
    embed = build_strategy_alert_embed(_plan())
    assert embed.description.startswith("```ansi\n")
    plain = ansi._ESCAPE_RE.sub("", embed.description)
    assert "entry 100.00" in plain and "stop  94.00" in plain and "TP1   110.00" in plain


def test_strategy_plan_line_names_the_side_and_has_no_check_mark():
    line = strategy_plan_line(_plan(badge="VALIDATED"))
    assert line == "Fibonacci · 4w · LONG · VALIDATED"
    assert "bullish" not in line and "✅" not in line
    assert strategy_plan_line(_plan()).endswith("⚠️ WEAK")


def test_strategy_simple_mirror_is_an_embed_with_the_same_identity():
    embed = build_strategy_simple_embed(_plan())
    assert isinstance(embed, discord.Embed)
    assert embed.title == build_strategy_alert_embed(_plan()).title
    assert embed.push_text.startswith("🆕 NEW SETUP · ▲ LONG AAPL")
    assert embed.description.startswith("```ansi\n")
    assert "ledger weak" in embed.description
    assert not embed.fields


def test_a_plan_without_a_confidence_level_takes_the_bottom_of_the_ramp():
    plan = _plan()
    del plan.confidence_level
    assert build_strategy_alert_embed(plan).color.value == kinds.SETUP_RAMP[1]
