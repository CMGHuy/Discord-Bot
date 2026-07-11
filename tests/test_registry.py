from swingbot.core.registry import get_badge, load_registry


def test_validated_strategy():
    b = get_badge("strategy", "Fibonacci")
    assert b.status == "VALIDATED"
    assert b.n == 206 and b.win_rate == 81.6


def test_weak_strategy():
    b = get_badge("strategy", "RSI")
    assert b.status == "WEAK" and b.win_rate == 68.4


def test_unknown_defaults_weak():
    b = get_badge("confluence", "ALL", "4w")
    assert b.status == "WEAK" and b.n == 0


def test_all_eleven_strategies_present():
    reg = load_registry()
    strategies = {r["strategy"] for r in reg if r["source"] == "strategy"}
    assert len(strategies) == 11
