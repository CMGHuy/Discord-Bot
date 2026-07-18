from swingbot.core.registry import get_badge, load_registry


def test_validated_strategy():
    b = get_badge("strategy", "Fibonacci")
    assert b.status == "VALIDATED"
    assert b.n == 206 and b.win_rate == 81.6


def test_rescued_rsi_validated():
    # RSI flipped WEAK -> VALIDATED by the Task 95-97 rescue (range-regime
    # gate, single OOS run 2026-07-18: N=30, WR=100.0, ExpR +0.304).
    b = get_badge("strategy", "RSI")
    assert b.status == "VALIDATED" and b.win_rate == 100.0 and b.n == 30


def test_weak_strategy():
    b = get_badge("strategy", "EMA Crossover")
    assert b.status == "WEAK"


def test_unknown_defaults_weak():
    # Task 42 only emits source="confluence" records for strategy="ALL"
    # (per-primary-strategy breakdown needs a re-replay that captures that
    # label) -- this key never exists, exercising the zero-sample default.
    b = get_badge("confluence", "Fibonacci", "4w")
    assert b.status == "WEAK" and b.n == 0


def test_confluence_all_registered():
    b = get_badge("confluence", "ALL", "4w")
    assert b.status == "WEAK"
    assert b.n == 336
    assert b.win_rate == 53.3


def test_confluence_pooled_registered():
    b = get_badge("confluence", "ALL", "some-unregistered-horizon")
    assert b.status == "WEAK"
    assert b.n == 4641
    assert b.win_rate == 53.5


def test_all_eleven_strategies_present():
    reg = load_registry()
    strategies = {r["strategy"] for r in reg if r["source"] == "strategy"}
    assert len(strategies) == 11
