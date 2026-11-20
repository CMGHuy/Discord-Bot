"""v237 V237-2: plan, level and throttle rule placeholders."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_rules, placeholders as ph
from swingbot.core import risk_limits
from swingbot.core.edge import throttle
from swingbot.core.market import levels_lifecycle, strategy_types
from swingbot.core.planning import builders, params

RULE_NAMES = {
    "MIN_REWARD_PCT", "MIN_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO",
    "CONFLUENCE_DEVIATION_PCT", "MIN_TARGET_CONFLUENCE_COUNT", "DEDUP_TOLERANCE_PCT",
    "SIGNAL_CONFIRMATION_SCANS", "MIN_ALERT_CONFIDENCE_LEVEL",
    "stop.hard_cap", "stop.clamp_level",
    "plan.tp1_share", "plan.runner_floor", "plan.breakeven_trigger", "plan.trail_atr",
    "plan.expiry_bars", "levels.touch_atr", "levels.break_atr",
    "throttle.ladder", "throttle.resume", "throttle.streak",
    "DD_THROTTLE_ENABLED", "KILLSWITCH_DEFAULT_ON",
}


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


def test_rule_table_has_exactly_the_planned_names():
    assert set(live_rules.RULE_PLACEHOLDERS) == RULE_NAMES


@pytest.mark.parametrize("name", sorted(RULE_NAMES))
def test_every_rule_placeholder_is_registered_and_renders_plain_text(name):
    out = _render(name)
    assert out == live_rules.RULE_PLACEHOLDERS[name]()
    assert out.strip() and "{{" not in out


@pytest.mark.parametrize("attr, value, text", [
    ("MIN_REWARD_PCT", 3.0, "3%"),
    ("MIN_REWARD_PCT", 2.5, "2.5%"),
    ("MIN_RISK_REWARD_RATIO", 1.5, "1.5:1"),
    ("MAX_RISK_REWARD_RATIO", 2.5, "2.5:1"),
    ("MAX_RISK_REWARD_RATIO", 3.0, "3:1"),
    ("CONFLUENCE_DEVIATION_PCT", 5.0, "5%"),
    ("MIN_TARGET_CONFLUENCE_COUNT", 2, "2"),
    ("DEDUP_TOLERANCE_PCT", 2.0, "2%"),
    ("SIGNAL_CONFIRMATION_SCANS", 1, "1"),
    ("SIGNAL_CONFIRMATION_SCANS", 3, "3"),
    ("MIN_ALERT_CONFIDENCE_LEVEL", 4, "4"),
    ("MIN_ALERT_CONFIDENCE_LEVEL", "3", "3"),
    ("DD_THROTTLE_ENABLED", False, "off"),
    ("DD_THROTTLE_ENABLED", True, "on"),
    ("KILLSWITCH_DEFAULT_ON", False, "off"),
    ("KILLSWITCH_DEFAULT_ON", True, "on"),
])
def test_config_rules_are_read_at_call_time(monkeypatch, attr, value, text):
    monkeypatch.setattr(config, attr, value)
    assert _render(attr) == text


def test_stop_cap_and_clamp_level_follow_the_constants(monkeypatch):
    assert _render("stop.hard_cap") == f"{risk_limits.HARD_MAX_PLANNED_LOSS_PCT:g}%"
    assert _render("stop.clamp_level") == "1.75%"
    monkeypatch.setattr(builders, "CLAMP_HEADROOM_PCT", 0.5)
    assert _render("stop.clamp_level") == "1.5%"
    monkeypatch.setattr(risk_limits, "HARD_MAX_PLANNED_LOSS_PCT", 3.0)
    assert (_render("stop.hard_cap"), _render("stop.clamp_level")) == ("3%", "2.5%")


def test_plan_shape_values(monkeypatch):
    assert _render("plan.tp1_share") == "50%"
    assert _render("plan.runner_floor") == "67%"
    assert _render("plan.breakeven_trigger") == "50%"
    assert _render("plan.trail_atr") == "2.5 × ATR(14)"
    assert _render("plan.expiry_bars") == "5 bars"
    monkeypatch.setattr(params, "TP1_FRACTION", 0.4)
    monkeypatch.setattr(params, "TRAIL_ATR_MULT", 3.0)
    monkeypatch.setattr(params, "DEFAULT_EXPIRY_BARS", 7)
    monkeypatch.setattr(strategy_types, "BREAKEVEN_TRIGGER_FRACTION", 0.6)
    assert _render("plan.tp1_share") == "40%"
    assert _render("plan.trail_atr") == "3 × ATR(14)"
    assert _render("plan.expiry_bars") == "7 bars"
    assert _render("plan.breakeven_trigger") == "60%"


def test_level_lifecycle_multiples(monkeypatch):
    assert _render("levels.touch_atr") == "0.25 × ATR"
    assert _render("levels.break_atr") == "1 × ATR"
    monkeypatch.setattr(levels_lifecycle, "BREAK_ATR_MULT", 1.5)
    assert _render("levels.break_atr") == "1.5 × ATR"


def test_throttle_ladder_table():
    assert _render("throttle.ladder").splitlines() == [
        "| Drawdown from peak | New-entry size |",
        "|---|---|",
        "| up to 8% | full size |",
        "| more than 8% | 75% of normal |",
        "| more than 12% | 50% of normal |",
        "| more than 16% | 25% of normal |",
        "| more than 20% | paused |",
    ]


def test_throttle_ladder_follows_the_tuple(monkeypatch):
    monkeypatch.setattr(throttle, "DD_LADDER", ((5.0, 0.5), (10.0, 0.0)))
    assert _render("throttle.ladder").splitlines()[2:] == [
        "| up to 5% | full size |", "| more than 5% | 50% of normal |",
        "| more than 10% | paused |"]


def test_throttle_resume_and_streak(monkeypatch):
    assert _render("throttle.resume") == "15%"
    assert _render("throttle.streak") == (
        "after 4 losses in a row, new entries are sized at 0.5 × normal until 2 wins land")
    monkeypatch.setattr(throttle, "STREAK_TRIGGER", 3)
    assert _render("throttle.streak").startswith("after 3 losses in a row")


def test_no_sensitive_field_value_reaches_a_rule_placeholder(monkeypatch):
    for f in (f for f in config.FIELDS if f.sensitive):
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
        assert f.attr not in live_rules.RULE_PLACEHOLDERS
    rendered = "\n".join(_render(name) for name in sorted(RULE_NAMES))
    assert "SENTINEL-" not in rendered
