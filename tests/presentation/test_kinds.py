"""v110: the notification registry -- table-driven over every Kind."""
import pytest

from swingbot.core.presentation import kinds, tokens
from swingbot.core.presentation.kinds import Family, Kind

ALL_KINDS = list(Kind)
DIRECTIONS = (None, "bullish", "bearish")


def _family_colours(family):
    colours = set()
    for kind in (k for k in Kind if k.family is family):
        for level in (None, 1, 2, 3, 4, 5):
            for r in (None, -3.0, -1.5, -0.5, 0.0, 0.5, 1.5, 3.0):
                for blocked in (False, True):
                    colours.add(kinds.stripe(kind, level=level, r=r, blocked=blocked))
    return colours


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
def test_every_kind_has_a_family(kind):
    assert isinstance(kind.family, Family)


def test_every_family_is_used():
    assert {k.family for k in Kind} == set(Family)


def test_badge_and_label_pairs_are_unique():
    pairs = [(kinds.badge(k), k.label) for k in Kind]
    assert len(pairs) == len(set(pairs))


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
def test_only_new_setup_kinds_carry_the_disclaimer(kind):
    assert kind.disclaimer is (kind.family is Family.NEW_SETUP)


@pytest.mark.parametrize("level,expected", [
    (1, 0xA5CDFF), (2, 0x74AEFF), (3, 0x3D8BFF), (4, 0x1F66E0), (5, 0x0B44B0),
    (None, 0xA5CDFF), (0, 0xA5CDFF), (9, 0xA5CDFF),
])
def test_setup_stripe_follows_the_confidence_ramp(level, expected):
    assert kinds.stripe(Kind.SETUP_ALERT, level=level) == expected


def test_blocked_setup_and_do_not_place_are_the_muted_grey_blue():
    assert kinds.stripe(Kind.SETUP_ALERT, level=5, blocked=True) == kinds.SETUP_BLOCKED
    assert kinds.stripe(Kind.TICKET_DO_NOT_PLACE, level=5) == kinds.SETUP_BLOCKED


@pytest.mark.parametrize("r,expected", [
    (0.5, kinds.RESULT_GREENS[0]), (1.0, kinds.RESULT_GREENS[1]),
    (1.99, kinds.RESULT_GREENS[1]), (2.0, kinds.RESULT_GREENS[2]),
    (-0.5, kinds.RESULT_REDS[0]), (-1.5, kinds.RESULT_REDS[1]), (-2.5, kinds.RESULT_REDS[2]),
    (0.0, kinds.RESULT_GREY), (0.05, kinds.RESULT_GREY), (-0.04, kinds.RESULT_GREY),
    (None, kinds.RESULT_GREY),
])
def test_result_stripe_steps_by_abs_r(r, expected):
    assert kinds.stripe(Kind.EXITED, r=r) == expected


@pytest.mark.parametrize("kind,expected", [
    (Kind.SCRATCHED, kinds.RESULT_GREY), (Kind.EXPIRED, kinds.RESULT_GREY),
    (Kind.INVALIDATED, kinds.RESULT_GREY), (Kind.FILLED, kinds.ENTRY_TEAL),
    (Kind.ENTRY_TRIGGERED, kinds.ENTRY_TEAL), (Kind.MOVE_STOP, kinds.MANAGE_AMBER),
    (Kind.RISK_CAP, kinds.MANAGE_AMBER), (Kind.NEAR_STOP, kinds.WATCH_STOP_ORANGE),
    (Kind.NEAR_TP, kinds.WATCH_TP_LIME), (Kind.SCAN_SUMMARY, kinds.SYSTEM_SLATE),
    (Kind.HEALTH_ALERT, kinds.HEALTH_RED), (Kind.HEALTH_RECOVERED, kinds.HEALTH_GREEN),
])
def test_fixed_kinds_use_their_own_colour(kind, expected):
    assert kinds.stripe(kind, level=5, r=3.0) == expected


def test_no_stripe_colour_is_shared_across_families():
    seen = {}
    for family in Family:
        for colour in _family_colours(family):
            owner = seen.setdefault(colour, family)
            assert owner is family, f"{colour:#08x} used by {owner.name} and {family.name}"


def test_every_ramp_step_is_distinct():
    assert len(set(kinds.SETUP_RAMP.values()) | {kinds.SETUP_BLOCKED}) == 6
    assert len(set(kinds.RESULT_GREENS) | set(kinds.RESULT_REDS) | {kinds.RESULT_GREY}) == 7


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_content_line_starts_with_the_badge(kind, direction):
    assert kinds.content_line(kind, "AAPL", direction).startswith(kinds.badge(kind))


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_titles_never_carry_the_retired_circles(kind, direction):
    for text in (kinds.title(kind, "AAPL", direction), kinds.content_line(kind, "AAPL", direction)):
        assert "🟢" not in text and "🔴" not in text


def test_title_shapes():
    assert kinds.title(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐") == "🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert kinds.title(Kind.MOVE_STOP, "NVDA", "bearish") == "✂️ ▼ SHORT NVDA · MOVE STOP"
    assert kinds.title(Kind.BE_MOVED, "NVDA", "bullish") == "🛡️ ▲ LONG NVDA · BREAK-EVEN"
    assert (kinds.title(Kind.HEALTH_ALERT, "", detail="3 failed tick(s) in a row")
            == "🚨 HEALTH ALERT · 3 failed tick(s) in a row")
    assert kinds.title(Kind.NEAR_TP, "AAPL") == "👀 AAPL · NEARING TP"


def test_content_line_names_the_family():
    assert (kinds.content_line(Kind.CLOSED_TRADE, "AAPL", "bullish", kinds.outcome_detail("win", 1.8))
            == "🏁 RESULT · ▲ LONG AAPL · CLOSED · ✅ WIN +1.8R")
    assert (kinds.content_line(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐")
            == "🆕 NEW SETUP · ▲ LONG AAPL · ALERT · Lv4 ⭐")
    assert kinds.content_line(Kind.BOT_ONLINE, "") == "🤖 SYSTEM · ONLINE"


def test_footer_carries_the_disclaimer_only_on_new_setup():
    assert kinds.footer(Kind.SETUP_ALERT, "0123456789ab") == f"{tokens.DISCLAIMER} · plan 01234567"
    assert kinds.footer(Kind.TICKET_PLACE) == tokens.DISCLAIMER
    assert kinds.footer(Kind.CLOSED_TRADE, "0123456789ab") == "RESULT · plan 01234567"
    assert kinds.footer(Kind.BOT_ONLINE) == "SYSTEM"
    assert kinds.footer(Kind.NEAR_STOP, "p1") == "WATCH · plan p1"


def test_family_badges_never_double_as_outcome_or_direction_marks():
    badges = {f.badge for f in Family}
    assert not badges & (set(kinds.OUTCOME_MARKS.values()) | {"▲", "▼"})


@pytest.mark.parametrize("outcome,r,expected", [
    ("win", 1.8, "✅ WIN +1.8R"), ("loss", -1.0, "❌ LOSS −1.0R"),
    ("scratch", 0.0, "⚪ SCRATCH 0.0R"), ("manual", None, "🔒 MANUAL CLOSE"),
    ("expired", None, "⏹️ EXPIRED"), ("invalidated", None, "⏹️ INVALIDATED"),
])
def test_outcome_detail(outcome, r, expected):
    assert kinds.outcome_detail(outcome, r) == expected


@pytest.mark.parametrize("r,expected", [
    (0.5, "win"), (0.06, "win"), (0.05, "scratch"), (-0.05, "scratch"),
    (-0.2, "loss"), (None, "scratch"),
])
def test_outcome_for_r_uses_the_instruction_tone_band(r, expected):
    assert kinds.outcome_for_r(r) == expected


@pytest.mark.parametrize("outcome,r,expected", [
    ("win", -2.0, 2.0), ("loss", 2.0, -2.0), ("loss", -1.5, -1.5),
    ("manual", 2.0, None), ("scratch", 0.3, None), ("win", None, None),
])
def test_result_r_signs_the_stripe_by_outcome(outcome, r, expected):
    assert kinds.result_r(outcome, r) == expected


def test_plan_badge_text_keeps_the_check_mark_for_outcomes_only():
    assert kinds.plan_badge_text("VALIDATED") == "VALIDATED"
    assert kinds.plan_badge_text("WEAK") == "⚠️ WEAK"


def test_side_word():
    assert kinds.side_word("bullish") == "LONG"
    assert kinds.side_word("bearish") == "SHORT"
    assert kinds.side_word(None) == tokens.ABSENT
