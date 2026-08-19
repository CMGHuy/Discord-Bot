import pytest
from swingbot import config
from swingbot.core.edge.rs_gate import rs_verdict


@pytest.fixture(autouse=True)
def _thresholds(monkeypatch):
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 40.0)


def test_bullish_leader_passes():
    assert rs_verdict("AAPL", "bullish", 75.0, True)["status"] == "pass"


def test_bullish_laggard_blocked():
    assert rs_verdict("AAPL", "bullish", 25.0, True)["status"] == "block"


def test_bearish_laggard_passes():
    """Symmetric: shorting a weak name is the mirror of buying a strong one."""
    assert rs_verdict("AAPL", "bearish", 25.0, True)["status"] == "pass"


def test_bearish_leader_blocked():
    """Shorting a market leader is exactly as bad as buying a laggard."""
    assert rs_verdict("AAPL", "bearish", 75.0, True)["status"] == "block"


def test_middle_band_blocks_neither_direction():
    assert rs_verdict("AAPL", "bullish", 50.0, True)["status"] == "block"
    assert rs_verdict("AAPL", "bearish", 50.0, True)["status"] == "block"


def test_unknown_rs_is_exempt_not_blocked():
    """THE critical case. rs_percentile returns 50.0 when it cannot compute,
    which is indistinguishable from a real median reading. If unknown were
    treated as a value, every ticker with a failed RS fetch would be silently
    blocked in both directions by the middle-band rule above."""
    v = rs_verdict("AAPL", "bullish", 50.0, False)
    assert v["status"] == "exempt"
    assert "unavailable" in v["reason"]


@pytest.mark.parametrize("symbol", ["EURUSD=X", "GC=F", "^GSPC"])
def test_non_equities_exempt_regardless_of_value(symbol):
    v = rs_verdict(symbol, "bullish", 5.0, True)
    assert v["status"] == "exempt"


def test_exempt_reason_names_the_asset_class():
    assert "future" in rs_verdict("GC=F", "bullish", 5.0, True)["reason"]
