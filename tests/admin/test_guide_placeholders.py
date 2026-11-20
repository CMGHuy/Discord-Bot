"""v235 V235-3/V235-3b: the guide's risk placeholders, whitelist and resolver."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_risk, placeholders as ph

RISK_NAMES = {
    "MAX_STOP_LOSS_PCT", "MIN_STOP_DISTANCE_PCT", "CLAMP_STOP_TO_HARD_CAP",
    "RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE",
    "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT", "SECTOR_HEAT_CAP_PCT",
    "POSITION_SIZING_MODE", "correlation.threshold", "correlation.window",
    "correlation.sector_fallback", "sizing.kelly_cap", "sizing.risk_floor",
    "sizing.risk_ceiling", "sizing.gap", "version.bot",
    "MAX_POSITION_SIZE_PCT", "MAX_POSITION_VALUE_ABSOLUTE", "MAX_OPEN_POSITIONS",
}

#: The stored account row the sizer reads (account.load_account_config()).
_ACCOUNT_ROW = {
    "risk_pct": 1.0, "max_risk_amount_absolute": 100.0, "sizing_mode": "risk_pct",
    "max_position_pct": 10.0, "max_position_value_absolute": 1000.0, "max_open_positions": 30,
}


@pytest.fixture(autouse=True)
def _stored_account(monkeypatch):
    """live_risk._load_account would read the database."""
    monkeypatch.setattr(live_risk, "_load_account", lambda: dict(_ACCOUNT_ROW))


def _row_with(monkeypatch, **values):
    monkeypatch.setattr(live_risk, "_load_account", lambda: {**_ACCOUNT_ROW, **values})


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
    ("PORTFOLIO_HEAT_CAP_PCT", 6.0, "6%"),
    ("CORRELATED_HEAT_CAP_PCT", 3.0, "3%"),
    ("SECTOR_HEAT_CAP_PCT", 2.5, "2.5%"),
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
    _row_with(monkeypatch, sizing_mode=mode)
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


# --- the stored account row ----------------------------------------------------

@pytest.mark.parametrize("name, key, value, text", [
    ("RISK_PER_TRADE_PCT", "risk_pct", 1.0, "1%"),
    ("RISK_PER_TRADE_PCT", "risk_pct", 0.5, "0.5%"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", 100.0, "$100"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", 62.5, "$62.50"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", 1500.0, "$1,500"),
    ("MAX_POSITION_SIZE_PCT", "max_position_pct", 10.0, "10%"),
    ("MAX_POSITION_SIZE_PCT", "max_position_pct", 0.1, "0.1%"),
    ("MAX_POSITION_VALUE_ABSOLUTE", "max_position_value_absolute", 1000.0, "$1,000"),
    ("MAX_OPEN_POSITIONS", "max_open_positions", 30, "30"),
    ("MAX_OPEN_POSITIONS", "max_open_positions", 5, "5"),
])
def test_account_values_come_from_the_stored_row(monkeypatch, name, key, value, text):
    _row_with(monkeypatch, **{key: value})
    assert _risk(name) == text


@pytest.mark.parametrize("name", [
    "RISK_PER_TRADE_PCT", "MAX_RISK_AMOUNT_ABSOLUTE", "MAX_POSITION_SIZE_PCT",
    "MAX_POSITION_VALUE_ABSOLUTE", "MAX_OPEN_POSITIONS"])
def test_the_env_seed_is_not_what_renders(monkeypatch, name):
    before = _risk(name)
    monkeypatch.setattr(config, name, 1.99)
    assert _risk(name) == before


def test_sizing_mode_ignores_the_env_seed(monkeypatch):
    monkeypatch.setattr(config, "POSITION_SIZING_MODE", "kelly")
    assert _risk("POSITION_SIZING_MODE") == "Fixed risk % per trade (`risk_pct`)"


def test_the_row_is_read_on_every_render(monkeypatch):
    calls = []
    monkeypatch.setattr(live_risk, "_load_account",
                        lambda: calls.append(1) or dict(_ACCOUNT_ROW))
    _risk("RISK_PER_TRADE_PCT")
    _risk("RISK_PER_TRADE_PCT")
    assert len(calls) == 2


ACCOUNT_NAMES = ["RISK_PER_TRADE_PCT", "MAX_RISK_AMOUNT_ABSOLUTE", "POSITION_SIZING_MODE",
                 "MAX_POSITION_SIZE_PCT", "MAX_POSITION_VALUE_ABSOLUTE", "MAX_OPEN_POSITIONS"]


@pytest.mark.parametrize("name", ACCOUNT_NAMES)
def test_an_unreadable_row_renders_not_available(monkeypatch, caplog, name):
    def boom():
        raise RuntimeError("database down")
    monkeypatch.setattr(live_risk, "_load_account", boom)
    assert _risk(name) == live_risk.UNAVAILABLE == "not available right now"
    assert "database down" in caplog.text


@pytest.mark.parametrize("name", ACCOUNT_NAMES)
def test_a_row_without_the_key_renders_not_available(monkeypatch, name):
    monkeypatch.setattr(live_risk, "_load_account", lambda: {})
    assert _risk(name) == live_risk.UNAVAILABLE


def test_heat_caps_and_the_risk_maximum_still_read_config(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 7.0)
    assert _risk("PORTFOLIO_HEAT_CAP_PCT") == "7%"
    field = next(f for f in config.FIELDS if f.attr == "RISK_PER_TRADE_PCT")
    assert _risk("RISK_PER_TRADE_PCT.max") == f"{float(field.max):g}%"


# --- secrets -----------------------------------------------------------------

def test_no_sensitive_field_value_reaches_a_risk_placeholder(monkeypatch):
    sensitive = [f for f in config.FIELDS if f.sensitive]
    assert sensitive, "config.FIELDS should mark at least one secret"
    for f in sensitive:
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
        assert f.attr not in live_risk.RISK_PLACEHOLDERS
    rendered = "\n".join(_risk(name) for name in sorted(RISK_NAMES))
    assert "SENTINEL-" not in rendered


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


# --- the registry ------------------------------------------------------------

def test_every_risk_name_is_registered():
    assert RISK_NAMES <= set(ph.PLACEHOLDERS)


@pytest.mark.parametrize("name", sorted(RISK_NAMES))
def test_resolve_renders_each_risk_name_like_the_table(name):
    assert _render(name) == _risk(name)


def test_registry_is_read_only():
    with pytest.raises(TypeError):
        ph.PLACEHOLDERS["DISCORD_TOKEN"] = lambda: "x"


def test_merge_refuses_a_name_defined_twice():
    with pytest.raises(ValueError, match="defined twice"):
        ph._merge({"a": lambda: "1"}, {"a": lambda: "2"})


# --- resolve -----------------------------------------------------------------

def test_resolve_substitutes_every_occurrence(monkeypatch):
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)
    _row_with(monkeypatch, risk_pct=1.0)
    text = "Stop {{MAX_STOP_LOSS_PCT}}, risk {{ RISK_PER_TRADE_PCT }}, again {{MAX_STOP_LOSS_PCT}}."
    assert ph.resolve(text) == "Stop 2%, risk 1%, again 2%."


def test_resolve_reads_live_values_on_each_call(monkeypatch):
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)
    assert ph.resolve("{{MAX_STOP_LOSS_PCT}}") == "2%"
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 1.5)
    assert ph.resolve("{{MAX_STOP_LOSS_PCT}}") == "1.5%"


def test_resolve_leaves_text_without_placeholders_alone():
    assert ph.resolve("Plain {braces} and } stay.") == "Plain {braces} and } stay."
    assert ph.resolve("") == ""


def test_names_in_lists_well_formed_names_in_order():
    assert ph.names_in("{{a.b}} x {{ C_D }} {{a.b}} {{bad name}}") == ["a.b", "C_D", "a.b"]


@pytest.mark.parametrize("text, name", [
    ("{{NOPE}}", "NOPE"),
    ("ok {{MAX_STOP_LOSS_PCT}} then {{ nope.too }}", "nope.too"),
    ("{{ MAX_STOP_LOSS_PCT + 1 }}", "MAX_STOP_LOSS_PCT + 1"),
    ("{{config.MAX_STOP_LOSS_PCT}}", "config.MAX_STOP_LOSS_PCT"),
    ("{{\nNOPE\n}}", "NOPE"),
])
def test_unknown_or_malformed_placeholder_raises(text, name):
    with pytest.raises(ph.UnknownPlaceholder) as info:
        ph.resolve(text)
    assert info.value.name == name
    assert str(info.value) == f"unknown guide placeholder: {name}"
    assert isinstance(info.value, KeyError)


def test_nothing_is_substituted_when_any_name_is_unknown(monkeypatch):
    calls = []
    monkeypatch.setitem(live_risk.RISK_PLACEHOLDERS, "MAX_STOP_LOSS_PCT",
                        lambda: calls.append(1) or "2%")
    monkeypatch.setattr(ph, "PLACEHOLDERS", ph._merge(live_risk.RISK_PLACEHOLDERS))
    with pytest.raises(ph.UnknownPlaceholder):
        ph.resolve("{{MAX_STOP_LOSS_PCT}} {{NOPE}}")
    assert calls == []


# --- secrets can never be reached --------------------------------------------

@pytest.mark.parametrize("name", [
    "DISCORD_TOKEN", "config.DISCORD_TOKEN", "ETORO_API_KEY", "ETORO_USER_KEY",
    "ADMIN_PASSWORD", "DATABASE_URL", "config.ETORO_API_KEY", "__class__",
])
def test_secret_names_are_not_placeholders(name):
    with pytest.raises(ph.UnknownPlaceholder):
        ph.resolve("{{" + name + "}}")


def test_no_sensitive_field_is_a_registered_name():
    sensitive = {f.attr for f in config.FIELDS if f.sensitive} | {
        f.key for f in config.FIELDS if f.sensitive}
    assert sensitive
    assert not sensitive & set(ph.PLACEHOLDERS)


# --- provenance --------------------------------------------------------------

def test_provenance_label_names_every_part_and_ends_before_tax():
    label = ph.provenance_label(source="live paper book", n=12, run_date="2026-11-18",
                                costs_included=False)
    assert label == ("Source: live paper book; N = 12; as of 2026-11-18; "
                     "costs not included; before tax")
    with_costs = ph.provenance_label(source="backtest TRAIN 2015-2022", n=300,
                                     run_date="2026-09-10", costs_included=True)
    assert "costs included" in with_costs and with_costs.endswith("before tax")


# --- per-call memo (final review) --------------------------------------------

def _counting(monkeypatch):
    calls = []
    table = dict(ph.PLACEHOLDERS)
    table["version.bot"] = lambda: calls.append(1) or "9.9"
    monkeypatch.setattr(ph, "PLACEHOLDERS", table)
    return calls


def test_resolve_memo_calls_each_provider_once(monkeypatch):
    calls = _counting(monkeypatch)
    memo: dict[str, str] = {}
    assert ph.resolve("a {{version.bot}} b {{version.bot}}", memo) == "a 9.9 b 9.9"
    assert ph.resolve("{{version.bot}}", memo) == "9.9"
    assert len(calls) == 1 and memo == {"version.bot": "9.9"}


def test_resolve_without_a_memo_stays_live(monkeypatch):
    calls = _counting(monkeypatch)
    ph.resolve("{{version.bot}}")
    ph.resolve("{{version.bot}}")
    assert len(calls) == 2


def test_resolve_memo_still_rejects_unknown_names_first(monkeypatch):
    _counting(monkeypatch)
    memo: dict[str, str] = {}
    with pytest.raises(ph.UnknownPlaceholder):
        ph.resolve("{{version.bot}} {{DISCORD_TOKEN}}", memo)
    assert memo == {}
