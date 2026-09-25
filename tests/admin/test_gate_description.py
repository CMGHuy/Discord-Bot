"""v103: a strategy gated to no direction must not render as 'no gate'."""
from swingbot.admin import queries


def test_empty_directions_reads_disabled(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": ()})
    assert queries._gate_description("Probe") == "disabled (no direction allowed)"


def test_single_direction_and_missing_gate_are_unchanged(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": ("bullish",)})
    assert queries._gate_description("Probe") == "bullish only"
    monkeypatch.delitem(queries.STRATEGY_GATES, "Probe")
    assert queries._gate_description("Probe") == "no gate (all directions, all horizons)"
