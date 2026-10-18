"""v148: the ops-alert settings (spec O4 "Config")."""
import re
from pathlib import Path

from swingbot import config

_KEYS = ("PROVIDER_FALLBACK_ALERT_PCT", "EMPTY_SYMBOLS_ALERT_PCT", "OPS_ALERT_WEBHOOK_URL")


def _fields() -> dict:
    return {f.key: f for f in config.FIELDS}


def test_declared_in_data_sources_under_their_own_names():
    fields = _fields()
    for key in _KEYS:
        assert fields[key].section == "Data Sources", key
        assert fields[key].attr == key


def test_thresholds_are_hot_whole_percentages():
    fields = _fields()
    for key, default in (("PROVIDER_FALLBACK_ALERT_PCT", "20"), ("EMPTY_SYMBOLS_ALERT_PCT", "5")):
        f = fields[key]
        assert (f.type, f.default, f.min, f.max) == ("number", default, 1, 100), key
        assert f.hot_reloadable is True and f.sensitive is False
        assert config._cast(f, "35") == 35


def test_threshold_defaults_are_live_ints():
    assert config.PROVIDER_FALLBACK_ALERT_PCT == 20
    assert config.EMPTY_SYMBOLS_ALERT_PCT == 5


def test_webhook_is_a_secret_that_only_the_cron_reads():
    f = _fields()["OPS_ALERT_WEBHOOK_URL"]
    assert (f.type, f.default, f.sensitive, f.hot_reloadable) == ("password", "", True, False)
    assert "scripts/ops/heartbeat_watch.sh" in f.help
    assert "not by the bot or the admin" in f.help


def test_listed_in_env_example():
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    for key in _KEYS:
        assert re.search(rf"^{key}=", text, re.MULTILINE), key
