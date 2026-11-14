"""v218 V218-2: the ADMIN_STORE_SNAPSHOT switch and the settings generation (index Handoff 3)."""
import pathlib

from swingbot import config
from swingbot.core.infra import store_generation

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "ADMIN_STORE_SNAPSHOT"


def _field():
    return next(f for f in config.FIELDS if f.attr == ATTR)


def test_is_a_hot_reloadable_admin_ui_on_off_select():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (ATTR, "Admin UI", "select", "on")
    assert [o[0] if isinstance(o, (tuple, list)) else o for o in field.options] == ["on", "off"]
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert field.help.startswith("v218. ")


def test_sits_right_after_the_slow_request_threshold():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index(ATTR) == attrs.index("ADMIN_SLOW_REQUEST_MS") + 1


def test_default_is_on_and_off_is_accepted_in_any_case():
    assert config._cast(_field(), _field().default) == "on"
    assert config._cast(_field(), "OFF") == "off"
    assert config._cast(_field(), "on") == "on"


def test_an_invalid_value_falls_back_to_on():
    assert config._cast(_field(), "maybe") == "on"


def test_env_example_lists_it_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}=on\n" in text


def test_reload_bumps_the_settings_generation_only_when_a_value_changed(monkeypatch):
    store_generation.reset()
    monkeypatch.setattr(config, "_load_dotenv_file", lambda: (True, True))
    monkeypatch.setattr(config, "_ENV_MTIME", config._ENV_MTIME)    # restored after reload()
    monkeypatch.setattr(config, "_apply_env", lambda: {})
    config.reload()
    assert store_generation.generation("settings") == 0
    monkeypatch.setattr(config, "_apply_env", lambda: {"LOGS_REFRESH_SECONDS": (10, 11)})
    config.reload()
    assert store_generation.generation("settings") == 1
    store_generation.reset()


def test_an_unchanged_env_file_does_not_bump(monkeypatch):
    store_generation.reset()
    monkeypatch.setattr(config, "_ENV_MTIME", config._env_signature())
    monkeypatch.setattr(config, "reload", lambda: (_ for _ in ()).throw(AssertionError("no reload")))
    assert config.auto_reload_if_changed() == {}
    assert store_generation.generation("settings") == 0
