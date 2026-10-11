"""v152: DISCORD_CHANNEL_NOTIFY_ID (D1 notify channel) and ALERT_SYMBOL_COOLDOWN_HOURS (D3)."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_notify_channel_is_an_empty_hot_reloadable_connection_key():
    field = _field("DISCORD_CHANNEL_NOTIFY_ID")
    assert (field.key, field.section, field.type, field.default) == (
        "DISCORD_CHANNEL_NOTIFY_ID", "Discord Connection", "text", "")
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "not silent" in field.help.lower()


def test_notify_channel_sits_right_after_the_ops_channel():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("DISCORD_CHANNEL_NOTIFY_ID") == attrs.index("DISCORD_CHANNEL_OPS_ID") + 1


def test_cooldown_is_a_live_only_float_defaulting_to_24_hours():
    field = _field("ALERT_SYMBOL_COOLDOWN_HOURS")
    assert (field.section, field.type, field.default, field.min) == (
        "Discord Alerts", "float", "24", 0)
    assert field.hot_reloadable is True
    assert field.search_class == "live_only"
    assert config._cast(field, field.default) == 24.0
    assert config._cast(field, "0") == 0.0
    assert "ALERT_SYMBOL_COOLDOWN_HOURS" not in config.searchable_attrs()


def test_both_keys_are_module_attributes_of_the_right_type():
    assert isinstance(config.DISCORD_CHANNEL_NOTIFY_ID, str)
    assert isinstance(config.ALERT_SYMBOL_COOLDOWN_HOURS, float)


def test_env_example_lists_both_keys():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "\nDISCORD_CHANNEL_NOTIFY_ID=\n" in text
    assert "\nALERT_SYMBOL_COOLDOWN_HOURS=24\n" in text
