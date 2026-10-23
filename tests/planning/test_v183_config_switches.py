"""v183: the gap-sizing and short-notice switches and squeeze thresholds."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[2]

EXPECTED = {
    # attr: (section, type, default, cast default, min, max, step)
    "SHORT_GAP_SIZING": ("Account Defaults", "checkbox", "true", True, None, None, None),
    "SHORT_RISK_NOTICE": ("Universe & Scanning", "checkbox", "true", True, None, None, None),
    "SHORT_SQUEEZE_SI_PCT": ("Universe & Scanning", "float", "10.0", 10.0, 1, 100, 0.5),
    "SHORT_SQUEEZE_DTC": ("Universe & Scanning", "float", "5.0", 5.0, 0.5, 30, 0.5),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(EXPECTED))
def test_field_schema(attr):
    section, ftype, default, cast, lo, hi, step = EXPECTED[attr]
    field = _field(attr)
    assert field.key == attr
    assert (field.section, field.type, field.default) == (section, ftype, default)
    assert (field.min, field.max, field.step) == (lo, hi, step)
    assert config._cast(field, field.default) == cast
    assert field.hot_reloadable is True
    assert field.search_class == "live_only"
    assert attr not in config.searchable_attrs()


@pytest.mark.parametrize("attr", sorted(EXPECTED))
def test_module_attribute_defaults(attr):
    assert getattr(config, attr) == EXPECTED[attr][3]
    assert type(getattr(config, attr)) is type(EXPECTED[attr][3])


def test_gap_switch_sits_with_the_heat_caps():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("SHORT_GAP_SIZING") == attrs.index("SECTOR_HEAT_CAP_PCT") + 1


def test_notice_fields_follow_the_short_lane_safeguards():
    attrs = [f.attr for f in config.FIELDS]
    base = attrs.index("SHORT_UNIVERSE_FETCH_BUDGET_SECONDS")
    assert attrs[base + 1:base + 4] == ["SHORT_RISK_NOTICE", "SHORT_SQUEEZE_SI_PCT", "SHORT_SQUEEZE_DTC"]


def test_help_names_the_revert_path_and_the_no_filter_rule():
    assert "byte-for-byte" in _field("SHORT_GAP_SIZING").help
    assert "never a filter" in _field("SHORT_RISK_NOTICE").help.lower()


def test_env_example_lists_all_four():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for line in ("SHORT_GAP_SIZING=true", "SHORT_RISK_NOTICE=true",
                 "SHORT_SQUEEZE_SI_PCT=10.0", "SHORT_SQUEEZE_DTC=5.0"):
        assert f"\n{line}\n" in text, line
