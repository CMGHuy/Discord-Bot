"""v204: the snapshot worker's cadence, budget and staleness knobs (index "Config fields")."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (default, min, max). Dict order is the FIELDS order.
V204_FIELDS = {
    "ADMIN_SNAPSHOT_REGULAR_S": ("300", 60, 3600),
    "ADMIN_SNAPSHOT_EXTENDED_S": ("900", 60, 7200),
    "ADMIN_SNAPSHOT_CLOSED_S": ("3600", 300, 21600),
    "ADMIN_SNAPSHOT_BUDGET_S": ("90", 10, 600),
    "ADMIN_STALE_SNAPSHOT_REGULAR_S": ("600", 60, 3600),
    "ADMIN_STALE_SNAPSHOT_EXTENDED_S": ("1800", 300, 7200),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(V204_FIELDS))
def test_field_is_a_hot_reloadable_data_sources_number(attr):
    field = _field(attr)
    default, low, high = V204_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Data Sources", "number", default)
    assert (field.min, field.max, field.step) == (low, high, 1)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert field.help.startswith("v204. ")


def test_fields_sit_together_after_the_v201_price_knobs():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("ADMIN_STALE_PRICE_EXTENDED_S") + 1
    assert attrs[start:start + len(V204_FIELDS)] == list(V204_FIELDS)


@pytest.mark.parametrize("attr", sorted(V204_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    assert config._cast(_field(attr), _field(attr).default) == int(V204_FIELDS[attr][0])


@pytest.mark.parametrize("attr", sorted(V204_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V204_FIELDS[attr][0]}\n" in text
