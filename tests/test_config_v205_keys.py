"""v205 V205-3: the slow-request threshold (index "Config field")."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "ADMIN_SLOW_REQUEST_MS"


def _field():
    return next(f for f in config.FIELDS if f.attr == ATTR)


def test_is_a_hot_reloadable_admin_ui_number():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (ATTR, "Admin UI", "number", "2000")
    assert (field.min, field.max, field.step) == (100, 60000, 100)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v205" in field.help


def test_sits_right_after_the_logs_refresh_knob():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index(ATTR) == attrs.index("LOGS_REFRESH_SECONDS") + 1


def test_default_casts_to_2000():
    assert config._cast(_field(), _field().default) == 2000


def test_env_example_lists_it_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}=2000\n" in text
