"""v235 V235-3/V235-3b: the guide's risk placeholders, whitelist and resolver."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_risk

RISK_NAMES = {
    "MAX_STOP_LOSS_PCT", "MIN_STOP_DISTANCE_PCT", "CLAMP_STOP_TO_HARD_CAP",
    "RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE",
    "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT", "SECTOR_HEAT_CAP_PCT",
    "POSITION_SIZING_MODE", "correlation.threshold", "correlation.window",
    "correlation.sector_fallback", "sizing.kelly_cap", "sizing.risk_floor",
    "sizing.risk_ceiling", "sizing.gap", "version.bot",
}


def _risk(name: str) -> str:
    return live_risk.RISK_PLACEHOLDERS[name]()


# --- the table ---------------------------------------------------------------

def test_risk_table_has_exactly_the_planned_names():
    assert set(live_risk.RISK_PLACEHOLDERS) == RISK_NAMES


@pytest.mark.parametrize("name", sorted(RISK_NAMES))
def test_every_risk_placeholder_renders_plain_text(name):
    out = _risk(name)
    assert isinstance(out, str) and out.strip()
    assert "{{" not in out and "}}" not in out


# --- values ------------------------------------------------------------------

@pytest.mark.parametrize("attr, value, text", [
    ("MAX_STOP_LOSS_PCT", 2.0, "2%"),
    ("MAX_STOP_LOSS_PCT", 1.5, "1.5%"),
    ("MIN_STOP_DISTANCE_PCT", 1.75, "1.75%"),
    ("RISK_PER_TRADE_PCT", 1.0, "1%"),
    ("PORTFOLIO_HEAT_CAP_PCT", 6.0, "6%"),
    ("CORRELATED_HEAT_CAP_PCT", 3.0, "3%"),
    ("SECTOR_HEAT_CAP_PCT", 2.5, "2.5%"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", 100.0, "$100"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", 62.5, "$62.50"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", 1500.0, "$1,500"),
    ("CLAMP_STOP_TO_HARD_CAP", True, "on"),
    ("CLAMP_STOP_TO_HARD_CAP", False, "off"),
])
def test_config_values_are_read_at_call_time(monkeypatch, attr, value, text):
    monkeypatch.setattr(config, attr, value)
    assert _risk(attr) == text


def test_risk_per_trade_max_comes_from_the_field():
    field = next(f for f in config.FIELDS if f.attr == "RISK_PER_TRADE_PCT")
    assert _risk("RISK_PER_TRADE_PCT.max") == f"{float(field.max):g}%"


@pytest.mark.parametrize("mode, text", [
    ("risk_pct", "Fixed risk % per trade (`risk_pct`)"),
    ("vol_target", "Volatility-targeted (portfolio vol budget) (`vol_target`)"),
    ("unheard_of", "unheard_of (`unheard_of`)"),
])
def test_sizing_mode_uses_the_option_label(monkeypatch, mode, text):
    monkeypatch.setattr(config, "POSITION_SIZING_MODE", mode)
    assert _risk("POSITION_SIZING_MODE") == text


def test_correlation_values_come_from_the_module():
    from swingbot.core.edge import correlation
    assert _risk("correlation.threshold") == "0.75"
    assert _risk("correlation.window") == f"{correlation.DEFAULT_WINDOW} trading days"
    fallback = _risk("correlation.sector_fallback")
    assert str(correlation.MIN_OVERLAP_BARS) in fallback and "sector" in fallback


def test_correlation_window_follows_the_constant(monkeypatch):
    from swingbot.core.edge import correlation
    monkeypatch.setattr(correlation, "DEFAULT_WINDOW", 60)
    assert _risk("correlation.window") == "60 trading days"


def test_kelly_and_risk_bounds():
    assert _risk("sizing.kelly_cap") == "0.25 of full Kelly"
    assert _risk("sizing.risk_floor") == "0.25%"
    assert _risk("sizing.risk_ceiling") == "2%"


def test_gap_table_short_on_long_off(monkeypatch):
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    table = _risk("sizing.gap")
    assert table.splitlines()[0] == "| Side | Gap-aware sizing | Sized on |"
    assert "| Short | on | the larger of the stop distance and entry × the ticker's p99 up-gap" in table
    assert "over the last 250 completed bars (needs at least 60 up-gaps) |" in table
    assert "| Long | off | the stop distance only |" in table
    assert "sized on the stop" in table


def test_gap_table_follows_the_switches_and_constants(monkeypatch):
    from swingbot.core.planning import gap_sizing
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", False)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    monkeypatch.setattr(gap_sizing, "LOOKBACK", 120)
    table = _risk("sizing.gap")
    assert "| Short | off | the stop distance only |" in table
    assert "p99 down-gap over the last 120 completed bars (needs at least 60 down-gaps) |" in table


def test_version_bot(monkeypatch):
    from swingbot.admin import helpers
    monkeypatch.setattr(helpers, "get_versions", lambda: {"ui": "1.0.0", "bot": "9.8.7"})
    assert _risk("version.bot") == "9.8.7"


# --- secrets -----------------------------------------------------------------

def test_no_sensitive_field_value_reaches_a_risk_placeholder(monkeypatch):
    sensitive = [f for f in config.FIELDS if f.sensitive]
    assert sensitive, "config.FIELDS should mark at least one secret"
    for f in sensitive:
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
        assert f.attr not in live_risk.RISK_PLACEHOLDERS
    rendered = "\n".join(_risk(name) for name in sorted(RISK_NAMES))
    assert "SENTINEL-" not in rendered
