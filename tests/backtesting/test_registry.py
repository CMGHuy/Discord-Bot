from swingbot.core.backtesting.registry import get_badge, load_registry

from tests.helpers import registry_strategy_row


def test_validated_strategy():
    row = registry_strategy_row("VALIDATED")
    b = get_badge("strategy", row["strategy"])
    assert b.status == "VALIDATED"
    assert b.n == row["n"] and b.win_rate == row["win_rate"]


def test_weak_strategy():
    row = registry_strategy_row("WEAK")
    assert get_badge("strategy", row["strategy"]).status == "WEAK"


def test_confluence_falls_back_to_strategy_badge():
    # Task 42 only emits source="confluence" records for strategy="ALL" --
    # per-primary-strategy confluence rows don't exist yet -- but every live
    # scan-loop plan is attributed source="confluence" + a real strategy name
    # (see primary_strategy_for/build_confluence_plan), so an exact
    # (confluence, <strategy>, ...) match was ALWAYS missing and used to fall
    # straight through to a hardcoded WEAK/n=0 default -- silently forfeiting
    # the badge-quality points and the VALIDATED label for every live plan.
    # get_badge now falls back to the strategy-source badge for that same
    # strategy name before giving up, since that's real OOS evidence about
    # this plan's primary confirming method.
    row = registry_strategy_row("VALIDATED")
    b = get_badge("confluence", row["strategy"], "4w")
    assert b.status == "VALIDATED" and b.n == row["n"] and b.win_rate == row["win_rate"]


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
