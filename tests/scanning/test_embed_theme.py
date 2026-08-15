import discord
from swingbot.core.scanning import embed_theme as th


def test_plan_color_weak_is_amber_regardless_of_tier():
    assert th.plan_color("WEAK", "A").value == 0xE67E22
    assert th.plan_color("WEAK", "C").value == 0xE67E22
    assert th.plan_color("VALIDATED", "A").value == 0x2ECC71
    assert th.plan_color("VALIDATED", "B").value == 0xF1C40F
    assert th.plan_color("VALIDATED", "C").value == 0x95A5A6


def test_tier_and_badge_chips():
    assert th.tier_chip("A") == "🅰"
    assert th.tier_chip("B") == "🅱"
    assert th.tier_chip("C") == "🅲"
    assert th.badge_chip("VALIDATED") == "✅ VALIDATED"
    assert th.badge_chip("WEAK") == "⚠️ WEAK"


def test_follow_chip():
    assert th.follow_chip(82.0) == "▰▰▰▰▱ 82"
    assert th.follow_chip(0.0) == "▱▱▱▱▱ 0"
    assert th.follow_chip(100.0) == "▰▰▰▰▰ 100"
    assert th.follow_chip(49.9) == "▰▰▱▱▱ 50"   # round(49.9/20)=round(2.495)=2... see impl note


def test_fmt_price():
    assert th.fmt_price(1234.5, "€") == "€1234.50"
    assert th.fmt_price(0.4321, "$") == "$0.4321"
    assert th.fmt_price(1.0, "€") == "€1.00"
    assert th.fmt_price(0.9999, "€") == "€0.9999"


def test_section_order_is_the_documented_tuple():
    assert th.SECTION_ORDER == (
        "headline", "plan", "quality", "confluence",
        "changes", "branches", "track_record", "warnings",
    )
