from swingbot.core.plan_engine import entry_type_for


def test_strategy_source_defaults_market():
    assert entry_type_for("Break & Retest", "strategy") == "market"
    assert entry_type_for("RSI", "strategy") == "market"


def test_confluence_source_stop_entry():
    assert entry_type_for("Support/Resistance", "confluence") == "stop_entry"
