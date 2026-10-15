"""v162: TRAINING_DATA_SOURCE, the training-data switch (spec §3)."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_training_data_source_is_a_data_sources_select_defaulting_to_alpaca():
    field = _field("TRAINING_DATA_SOURCE")
    assert (field.key, field.section, field.type, field.default) == (
        "TRAINING_DATA_SOURCE", "Data Sources", "select", "alpaca")
    assert [value for value, _label in field.options] == ["alpaca", "yfinance"]
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "TRAINING_DATA_SOURCE" not in config.searchable_attrs()
    assert "yfinance" in field.help and "data/market_data/" in field.help


def test_it_sits_after_the_alpaca_breaker_fields():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("TRAINING_DATA_SOURCE") == attrs.index("ALPACA_BREAKER_COOLDOWN_SECONDS") + 1


def test_values_are_lower_cased_and_a_typo_falls_back_to_alpaca():
    field = _field("TRAINING_DATA_SOURCE")
    assert config._cast(field, "YFinance") == "yfinance"
    assert config._cast(field, "alpaca") == "alpaca"
    assert config._cast(field, "polygon") == "alpaca"


def test_module_attribute_is_a_known_source():
    assert config.TRAINING_DATA_SOURCE in ("alpaca", "yfinance")


def test_alpaca_enabled_help_no_longer_says_backtests_never_use_alpaca():
    assert "Backtests never use Alpaca" not in _field("ALPACA_ENABLED").help


def test_env_example_lists_the_key_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "\nTRAINING_DATA_SOURCE=alpaca\n" in text
