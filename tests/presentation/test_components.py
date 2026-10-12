from swingbot.core.presentation import components as c
from swingbot.core.presentation import tokens as t
import re
import datetime
import json
import logging

import discord
import pytest


def test_plan_headline_is_a_fenced_ansi_block():
    out = c.plan_headline(direction="bullish", entry=197.15, target=220.81,
                          stop=185.32, target_pct=12.0, stop_pct=-6.0, r=2.4)
    assert out.startswith("```ansi\n") and out.endswith("\n```")
    assert "197.15" in out


def test_confidence_field_is_named_and_inline():
    assert c.confidence_field(5, 91) == ("Confidence", "Lv5 · 91", True)


def test_follow_field_appends_the_breakdown_on_its_own_line():
    assert c.follow_field(82.0, breakdown="badge +30 · regime +20").value == (
        "▰▰▰▰▱ 82\nbadge +30 · regime +20")


def test_follow_field_without_a_breakdown_is_just_the_meter():
    assert c.follow_field(82.0).value == "▰▰▰▰▱ 82"


def test_fields_are_a_named_tuple_so_they_unpack_into_add_field():
    name, value, inline = c.confidence_field(3, 50)
    assert (name, value, inline) == ("Confidence", "Lv3 · 50", True)


def test_blocked_by_lists_each_unmet_requirement_with_actual_and_required():
    field = c.blocked_by_field([("Reward", "3.1% — needs ≥ 5.0%"),
                                ("R:R", "1.4:1 — needs ≥ 2.0:1")])
    assert field.name == "⚠ Blocked by"
    assert field.value == ("Reward: 3.1% — needs ≥ 5.0%\n"
                           "R:R: 1.4:1 — needs ≥ 2.0:1")


def test_blocked_by_is_full_width_not_inline():
    assert c.blocked_by_field([("Reward", "x")]).inline is False


def test_blocked_by_is_none_when_everything_clears():
    assert c.blocked_by_field([]) is None


def test_apply_chrome_sets_accent_footer_and_timestamp():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, accent=t.accent_for_level(5), plan_id="a4f19c2233445566")
    assert embed.color.value == 0x17C98E
    assert embed.timestamp is not None
    assert t.DISCLAIMER in embed.footer.text and "plan a4f19c22" in embed.footer.text


def test_apply_chrome_without_a_plan_id_shows_the_disclaimer_alone():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, accent=t.accent_for_level(3))
    assert embed.footer.text == t.DISCLAIMER


def test_apply_chrome_truncates_the_plan_id_to_eight_chars():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, accent=t.accent_for_level(1), plan_id="0123456789abcdef")
    assert "plan 01234567" in embed.footer.text and "89abcdef" not in embed.footer.text


def test_apply_chrome_returns_none_so_call_sites_read_as_a_statement():
    assert c.apply_chrome(discord.Embed(title="x"), accent=t.accent_for_level(5)) is None


def test_section_order_is_a_fixed_tuple_with_blocked_before_the_chart_fold():
    assert t.SECTION_ORDER[:4] == ("headline", "plan", "blocked", "quality")
    assert isinstance(t.SECTION_ORDER, tuple)


def test_levels_block_is_a_fenced_ansi_block():
    out = c.levels_block(direction="bullish", entry=100.0, stop=95.0, tp1=110.0)
    assert out.startswith("```ansi\n") and out.endswith("\n```")
    assert "100.00" in out and "110.00" in out


def test_result_headline_is_a_fenced_ansi_block():
    out = c.result_headline(direction="bearish", entry=100.0, exit_price=94.0,
                            stop=105.0, pct=6.0, r=1.2)
    assert out.startswith("```ansi\n") and "94.00" in out


from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind


def test_apply_chrome_with_a_kind_takes_the_registry_stripe_and_footer():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.CLOSED_TRADE, r=2.5, plan_id="a4f19c2233445566")
    assert embed.color.value == kinds.RESULT_GREENS[2]
    assert embed.footer.text == "RESULT · plan a4f19c22"
    assert embed.timestamp is not None


def test_apply_chrome_new_setup_keeps_the_disclaimer():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=5, plan_id="a4f19c2233445566")
    assert embed.color.value == kinds.SETUP_RAMP[5]
    assert embed.footer.text == f"{t.DISCLAIMER} · plan a4f19c22"


def test_apply_chrome_blocked_setup_is_the_muted_grey_blue():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=5, blocked=True)
    assert embed.color.value == kinds.SETUP_BLOCKED


def test_apply_chrome_needs_a_kind_or_an_accent():
    with pytest.raises(ValueError):
        c.apply_chrome(discord.Embed(title="x"))


def test_push_embed_carries_title_and_push_line():
    embed = c.push_embed(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐", description="body")
    assert isinstance(embed, discord.Embed)
    assert embed.title == "🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert embed.push_text == "🆕 NEW SETUP · ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert embed.kind is Kind.SETUP_ALERT
    assert embed.description == "body"


def test_push_kwargs_adds_content_only_when_the_embed_has_a_push_line():
    pushed = c.push_embed(Kind.BOT_ONLINE)
    assert c.push_kwargs(pushed) == {"embed": pushed, "content": "🤖 SYSTEM · ONLINE"}
    plain = discord.Embed(title="x")
    assert c.push_kwargs(plain) == {"embed": plain}
    assert c.push_kwargs("EMBED") == {"embed": "EMBED"}


def test_the_package_exports_the_push_helpers():
    from swingbot.core import presentation as ui
    assert ui.push_embed is c.push_embed and ui.push_kwargs is c.push_kwargs
    assert ui.PushEmbed is c.PushEmbed


def test_result_headline_never_raises_on_six_digit_prices():
    text = c.result_headline(direction="bullish", entry=150000.0, exit_price=160000.0,
                                      stop=140000.0, pct=6.7, r=1.5)
    assert text.startswith("```ansi")
    plain = re.sub(r"\[[0-9;]*m", "", text)
    assert "150000" in plain and "160000" in plain
    assert all(len(line) <= 32 for line in plain.splitlines())


@pytest.mark.parametrize("base, expected", [
    ("https://example.com", "https://example.com/plans/abc123"),
    ("https://example.com///", "https://example.com/plans/abc123"),
    ("http://localhost:5000", "http://localhost:5000/plans/abc123"),
])
def test_plan_link_uses_the_full_id_and_normalizes_trailing_slashes(base, expected):
    assert c.plan_link("abc123", base) == expected


@pytest.mark.parametrize("plan_id, base", [
    (None, "https://example.com"), ("", "https://example.com"),
    ("abc123", None), ("abc123", ""),
])
def test_plan_link_omits_links_without_both_inputs(plan_id, base):
    assert c.plan_link(plan_id, base) is None


@pytest.mark.parametrize("base", [
    "ftp://x", "javascript:x", "https://", "example.com", "https://[broken",
    " https://example.com", "https://example.com/a b", "https://example.com\t",
    "https://example.com\n", "https://example.com/\u00a0",
])
def test_plan_link_rejects_malformed_or_whitespace_bases(base):
    assert c.plan_link("abc123", base) is None


def test_invalid_bases_warn_once_per_distinct_nonempty_value(monkeypatch, caplog):
    monkeypatch.setattr(c, "_WARNED_BASES", set())
    with caplog.at_level(logging.WARNING, logger=c.__name__):
        for base in (None, "", "ftp://first", "ftp://first", "https://[bad", "https://[bad"):
            assert c.plan_link("abc123", base) is None
    warnings = [record for record in caplog.records if record.name == c.__name__]
    assert len(warnings) == 2
    assert all(record.levelno == logging.WARNING for record in warnings)
    assert "ftp://first" in warnings[0].getMessage()
    assert "https://[bad" in warnings[1].getMessage()


@pytest.mark.parametrize("style, color", [
    ({"kind": Kind.SETUP_ALERT, "level": 5}, 0x0B44B0),
    ({"accent": t.accent_for_level(5)}, 0x17C98E),
])
def test_apply_chrome_adds_a_title_link_preserving_footer_and_color(style, color, monkeypatch):
    now = datetime.datetime(2026, 10, 11, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(discord.utils, "utcnow", lambda: now)
    before = discord.Embed(title="AAPL", description="Trade plan")
    after = discord.Embed(title="AAPL", description="Trade plan")
    c.apply_chrome(before, plan_id="a4f19c2233445566", **style)
    c.apply_chrome(after, plan_id="a4f19c2233445566", link_base="https://example.com/", **style)
    expected = before.to_dict()
    expected["url"] = "https://example.com/plans/a4f19c2233445566"
    assert after.to_dict() == expected
    assert after.color.value == color
    assert after.footer.text == f"{t.DISCLAIMER} · plan a4f19c22"


@pytest.mark.parametrize("base", [None, "", "ftp://bad", " https://example.com"])
def test_apply_chrome_without_valid_base_preserves_serialized_output(base, monkeypatch):
    now = datetime.datetime(2026, 10, 11, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(discord.utils, "utcnow", lambda: now)
    embed = discord.Embed(title="x", url="https://existing.example", description="body")
    c.apply_chrome(embed, accent=t.accent_for_level(5), plan_id="a4f19c2233445566", link_base=base)
    expected = {
        "title": "x", "url": "https://existing.example", "description": "body",
        "type": "rich", "flags": 0, "color": 0x17C98E,
        "timestamp": "2026-10-11T00:00:00+00:00",
        "footer": {"text": f"{t.DISCLAIMER} · plan a4f19c22"},
    }
    assert json.dumps(embed.to_dict(), sort_keys=True) == json.dumps(expected, sort_keys=True)


@pytest.mark.parametrize("plan_id", [None, ""])
def test_apply_chrome_without_plan_id_has_no_title_link(plan_id):
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=5, plan_id=plan_id,
                   link_base="https://example.com")
    assert embed.url is None
