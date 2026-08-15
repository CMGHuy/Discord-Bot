from swingbot.core.backtesting.registry import get_badge, load_registry


def test_validated_strategy():
    # Numbers from the exit-v2 validation single run (Task 32, 2026-07-18).
    b = get_badge("strategy", "Fibonacci")
    assert b.status == "VALIDATED"
    assert b.n == 203 and b.win_rate == 82.3


def test_rescued_rsi_validated():
    # RSI flipped WEAK -> VALIDATED by the Task 95-97 rescue (range-regime
    # gate, single OOS run 2026-07-18: N=30, WR=100.0, ExpR +0.304).
    b = get_badge("strategy", "RSI")
    assert b.status == "VALIDATED" and b.win_rate == 100.0 and b.n == 30


def test_weak_strategy():
    b = get_badge("strategy", "EMA Crossover")
    assert b.status == "WEAK"


def test_confluence_falls_back_to_strategy_badge():
    # Task 42 only emits source="confluence" records for strategy="ALL" --
    # per-primary-strategy confluence rows don't exist yet -- but every live
    # scan-loop plan is attributed source="confluence" + a real strategy name
    # (see primary_strategy_for/build_confluence_plan), so an exact
    # (confluence, Fibonacci, ...) match was ALWAYS missing and used to fall
    # straight through to a hardcoded WEAK/n=0 default -- silently forfeiting
    # the badge-quality points and the VALIDATED label for every live plan.
    # get_badge now falls back to the strategy-source badge for that same
    # strategy name before giving up, since that's real OOS evidence about
    # this plan's primary confirming method.
    b = get_badge("confluence", "Fibonacci", "4w")
    assert b.status == "VALIDATED" and b.n == 203 and b.win_rate == 82.3


def test_unknown_defaults_weak():
    # A source with no matching record at any fallback level (exact,
    # strategy-source, or pooled "ALL") still exercises the zero-sample
    # default.
    b = get_badge("nonexistent_source", "Nonexistent Strategy", "4w")
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
