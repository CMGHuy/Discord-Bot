"""v237 V237-3/V237-3b: gate switches and single-flag placeholders."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_switches as ls, placeholders as ph
from swingbot.core.market import strategy_types

SWITCH_NAMES = {"gates.switches"}
LABELS = [
    "Market regime gate", "Adjacent-horizon alignment", "Relative strength, long arm",
    "Relative strength, short arm", "Dead-cat bounce veto", "Earnings blackout",
    "Pullback volume dry-up", "Headroom to the first target", "S/R minimum level touches",
    "MA Ribbon confirm bars", "RSI Divergence turn confirmation", "FVG level mode",
    "Next-open market entry and gap reclaim", "Data-driven stops", "Stall exit",
    "Runner structure exit",
]
#: Every setting at its schema default (swingbot/config.py), so tests never see a local .env.
DEFAULTS = {
    "REGIME_GATES_ENABLED": False, "MTF_ADJACENT_GATE": False, "RS_GATE": True,
    "RS_LEADER_PERCENTILE": 0.0, "RS_LAGGARD_PERCENTILE": 25.0, "DEAD_CAT_BOUNCE_VETO": False,
    "EARNINGS_BLACKOUT_SESSIONS": 0, "PULLBACK_DRYUP_SCOPE": "off", "PULLBACK_DRYUP_MAX_RATIO": 0.0,
    "HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 0.0, "SR_MIN_LEVEL_TOUCHES": 0,
    "MA_RIBBON_CONFIRM_BARS": 1, "RSI_DIV_MIN_CONSECUTIVE_TURN": 1, "FVG_LEVELS_MODE": "all",
    "MARKET_ENTRY_NEXT_OPEN": False, "GAP_RECLAIM_ATR": 0.0, "DATA_DRIVEN_STOPS_ENABLED": False,
    "STALL_EXIT_ENABLED": False, "RUNNER_STRUCTURE_EXIT": "off", "STRATEGY_ALERTS_MODE": "off",
    "STRATEGY_ALERTS_LIVE_STRATEGIES": "", "HTF_CONFLUENCE_ENABLED": True,
    "AVWAP_LEVELS_ENABLED": True, "LEVEL_LIFECYCLE_STOPS_ENABLED": True,
    "SCALE_OUT_ENABLED": True, "PLAN_ENGINE_V2": "on",
}


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    for attr, value in DEFAULTS.items():
        monkeypatch.setattr(config, attr, value)
    monkeypatch.setattr(strategy_types, "REGIME_ALLOW", {})


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


def _row(label: str) -> str:
    rows = [line for line in _render("gates.switches").splitlines()
            if line.startswith(f"| {label} |")]
    assert len(rows) == 1, label
    return rows[0]


def test_switch_table_has_exactly_the_planned_names():
    assert set(ls.SWITCH_PLACEHOLDERS) == SWITCH_NAMES


@pytest.mark.parametrize("name", sorted(SWITCH_NAMES))
def test_every_switch_placeholder_is_registered_and_renders(name):
    out = _render(name)
    assert out == ls.SWITCH_PLACEHOLDERS[name]() and out.strip() and "{{" not in out


def test_rows_in_order_and_every_setting_is_a_config_field():
    assert [row.label for row in ls.SWITCH_ROWS] == LABELS
    fields = {f.attr for f in config.FIELDS}
    for row in ls.SWITCH_ROWS:
        assert row.settings and set(row.settings) <= fields, row.label
    lines = _render("gates.switches").splitlines()
    assert lines[0] == "| Gate | Setting | Now | In the live scan |"
    assert lines[1] == "|---|---|---|---|"
    assert len(lines) == 2 + len(LABELS)


def test_at_schema_defaults_only_the_rs_short_arm_is_applied():
    applied = [label for label in LABELS if _row(label).endswith(f"| {ls.APPLIED} |")]
    assert applied == ["Relative strength, short arm"]
    assert _row("Dead-cat bounce veto") == (
        "| Dead-cat bounce veto | `DEAD_CAT_BOUNCE_VETO` | off | measured, not used |")
    assert _row("Headroom to the first target") == (
        "| Headroom to the first target | `HEADROOM_SCOPE`, `HEADROOM_MIN_R` | `off`, 0 "
        "| measured, not used |")
    assert _row("Relative strength, short arm") == (
        "| Relative strength, short arm | `RS_GATE`, `RS_LAGGARD_PERCENTILE` | on, 25 | applied |")


def test_earnings_blackout_is_never_applied(monkeypatch):
    monkeypatch.setattr(config, "EARNINGS_BLACKOUT_SESSIONS", 2)
    assert _row("Earnings blackout").endswith(f"| {ls.NOT_USED} |")


@pytest.mark.parametrize("label, changes", [
    ("Market regime gate", {"REGIME_GATES_ENABLED": True}),
    ("Adjacent-horizon alignment", {"MTF_ADJACENT_GATE": True}),
    ("Relative strength, long arm", {"RS_LEADER_PERCENTILE": 80.0}),
    ("Dead-cat bounce veto", {"DEAD_CAT_BOUNCE_VETO": True}),
    ("Pullback volume dry-up", {"PULLBACK_DRYUP_SCOPE": "strategy", "PULLBACK_DRYUP_MAX_RATIO": 0.6}),
    ("Headroom to the first target", {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 1.0}),
    ("S/R minimum level touches", {"SR_MIN_LEVEL_TOUCHES": 2}),
    ("MA Ribbon confirm bars", {"MA_RIBBON_CONFIRM_BARS": 3}),
    ("RSI Divergence turn confirmation", {"RSI_DIV_MIN_CONSECUTIVE_TURN": 2}),
    ("FVG level mode", {"FVG_LEVELS_MODE": "displacement"}),
    ("Next-open market entry and gap reclaim", {"MARKET_ENTRY_NEXT_OPEN": True}),
    ("Data-driven stops", {"DATA_DRIVEN_STOPS_ENABLED": True}),
    ("Stall exit", {"STALL_EXIT_ENABLED": True}),
    ("Runner structure exit", {"RUNNER_STRUCTURE_EXIT": "hl_trail"}),
])
def test_each_gate_flips_to_applied_with_its_settings(monkeypatch, label, changes):
    assert _row(label).endswith(f"| {ls.NOT_USED} |")
    for attr, value in changes.items():
        monkeypatch.setattr(config, attr, value)
    if label == "Market regime gate":
        assert _row(label).endswith(f"| {ls.NOT_USED} |")   # flag alone: REGIME_ALLOW is empty
        monkeypatch.setattr(strategy_types, "REGIME_ALLOW", {"RSI": ("bull",)})
    assert _row(label).endswith(f"| {ls.APPLIED} |")


@pytest.mark.parametrize("label, changes", [
    ("Pullback volume dry-up", {"PULLBACK_DRYUP_SCOPE": "strategy"}),
    ("Pullback volume dry-up", {"PULLBACK_DRYUP_MAX_RATIO": 0.6}),
    ("Headroom to the first target", {"HEADROOM_SCOPE": "strategy"}),
    ("Headroom to the first target", {"HEADROOM_MIN_R": 1.0}),
    ("Relative strength, short arm", {"RS_GATE": False}),
    ("Next-open market entry and gap reclaim", {"GAP_RECLAIM_ATR": 0.5}),
])
def test_half_a_coupled_switch_is_not_applied(monkeypatch, label, changes):
    for attr, value in changes.items():
        monkeypatch.setattr(config, attr, value)
    assert _row(label).endswith(f"| {ls.NOT_USED} |")


def test_empty_string_setting_renders_as_empty(monkeypatch):
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "")
    assert "| `FVG_LEVELS_MODE` | (empty) |" in _row("FVG level mode")


def test_no_sensitive_setting_is_a_switch():
    sensitive = {f.attr for f in config.FIELDS if f.sensitive}
    assert not sensitive & {s for row in ls.SWITCH_ROWS for s in row.settings}
    assert not sensitive & set(ls.SWITCH_PLACEHOLDERS)
