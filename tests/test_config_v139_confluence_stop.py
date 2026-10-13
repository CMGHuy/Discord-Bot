"""v139: the confluence stop-geometry knobs -- schema, ScanParams, reachability."""
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.scan_params import ScanParams

KNOBS = ("CONFLUENCE_STRUCTURAL_STOP_PCT", "CONFLUENCE_STOP_DROP_PCT")


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", KNOBS)
def test_field_is_an_inert_searchable_float(attr):
    field = _field(attr)
    assert (field.type, field.default, field.search_class) == ("float", "0", "searchable")
    assert config._cast(field, field.default) == 0.0
    assert attr in config.searchable_attrs()


def test_scan_params_defaults_are_off():
    params = ScanParams.from_config()
    assert params.confluence_structural_stop_pct == 0.0
    assert params.confluence_stop_drop_pct == 0.0


@pytest.mark.parametrize("attr", KNOBS)
def test_scan_params_carries_the_knob(attr, monkeypatch):
    monkeypatch.setattr(config, attr, 4.0)
    assert getattr(ScanParams.from_config(), attr.lower()) == 4.0


@pytest.mark.parametrize("attr", KNOBS)
def test_reachability_row_is_confluence_only(attr):
    assert reach.classify(attr) == reach.REACHABLE
    assert reach.REGISTRY[attr].observed_by == reach.C


@pytest.mark.parametrize("attr", KNOBS)
def test_measure_arms_parses_the_knob(attr):
    assert parse_knob(f"{attr}=3.0") == (attr, 3.0)
