"""v151: the admin UI's public base URL, read by the bot to link plan embeds."""
import pytest

from swingbot import config


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


@pytest.fixture
def restore_config():
    """_apply_env() rewrites every FIELDS global; put them all back afterwards."""
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_field_sits_in_the_bot_side_discord_alerts_group():
    field = _field("ADMIN_PUBLIC_URL")
    assert field.attr == "ADMIN_PUBLIC_URL"
    assert field.section == "Discord Alerts"
    assert field.type == "text"
    assert field.default == ""
    assert field.hot_reloadable is True
    assert not field.sensitive


def test_help_says_the_bot_reads_it_at_embed_build_time():
    help_text = _field("ADMIN_PUBLIC_URL").help
    assert "Read by the bot each time it builds an alert embed" in help_text
    assert "empty = no link" in help_text


def test_default_is_empty_meaning_no_link(monkeypatch, restore_config):
    monkeypatch.delenv("ADMIN_PUBLIC_URL", raising=False)
    config._apply_env()
    assert config.ADMIN_PUBLIC_URL == ""


def test_a_reload_picks_up_a_new_value(monkeypatch, restore_config):
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://swingbot.example.com")
    changed = config._apply_env()
    assert config.ADMIN_PUBLIC_URL == "https://swingbot.example.com"
    assert "ADMIN_PUBLIC_URL" in changed
