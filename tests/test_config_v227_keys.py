"""v227: FEED_POSTS_ENABLED -- the voice-notification recorder's kill switch."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_kill_switch_is_a_hot_reloadable_discord_alerts_checkbox_on_by_default():
    field = _field("FEED_POSTS_ENABLED")
    assert (field.key, field.section, field.type, field.default) == (
        "FEED_POSTS_ENABLED", "Discord Alerts", "checkbox", "true")
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v227" in field.help
    assert config._cast(field, "true") is True and config._cast(field, "false") is False


def test_it_sits_right_after_the_alert_cooldown():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs[attrs.index("ALERT_SYMBOL_COOLDOWN_HOURS") + 1] == "FEED_POSTS_ENABLED"


def test_env_example_lists_it_on():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "\nFEED_POSTS_ENABLED=true\n" in text


def test_the_test_suite_runs_with_recording_off():
    # tests/conftest.py pins it off so no test writes into the .env database
    # through the side engine; recorder tests switch it on themselves.
    assert config.FEED_POSTS_ENABLED is False
