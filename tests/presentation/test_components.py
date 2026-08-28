from swingbot.core.presentation import components as c


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
