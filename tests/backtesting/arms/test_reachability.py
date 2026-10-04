import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as r


CLASSES = {r.REACHABLE, r.LIVE_SCAN_ONLY, r.JOURNAL_DEPENDENT, r.OUTSIDE_REPLAY}


def test_every_searchable_knob_is_classified_exactly_once():
    assert set(r.REGISTRY) == set(config.searchable_attrs()), (
        "a searchable knob was added or removed -- classify it in reachability.py")


def test_entries_are_well_formed():
    for attr, reach in r.REGISTRY.items():
        assert reach.cls in CLASSES, attr
        assert reach.reason.strip(), attr
        if reach.cls == r.REACHABLE:
            assert reach.observed_by and reach.observed_by <= {"confluence", "strategy", "short_universe"}, attr
            assert not (reach.observed_by & r.POPULATION_ENGINES and reach.observed_by - r.POPULATION_ENGINES), (
                f"{attr}: a population engine cannot share a knob with a per-ticker engine")
        else:
            assert not reach.observed_by and not reach.fixture_observable, attr


def test_journal_knobs_are_refused():
    assert r.classify("STALL_EXIT_ENABLED") == r.JOURNAL_DEPENDENT
    assert r.classify("DATA_DRIVEN_STOPS_ENABLED") == r.JOURNAL_DEPENDENT


def test_unknown_knob_is_unclassified():
    assert r.classify("NOT_A_KNOB") == r.UNCLASSIFIED
    assert "not a searchable" in r.reason("NOT_A_KNOB")


DRYUP = ("PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_MAX_RATIO")


def test_dryup_knobs_are_searchable_and_reachable_by_both_engines():
    for attr in DRYUP:
        assert attr in config.searchable_attrs()
        assert r.classify(attr) == r.REACHABLE
        assert r.REGISTRY[attr].observed_by == r.CS
        assert r.REGISTRY[attr].fixture_observable is False
        assert "Stage -1" in r.reason(attr)


@pytest.mark.slow
def test_dryup_knobs_change_outcomes_together_on_the_fixture(monkeypatch):
    """Both scopes reach trades when the ratio is heavy on the fixed fixture."""
    from swingbot.core.backtesting.arms.engine import run_arm
    from swingbot.core.edge import gates
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    monkeypatch.setattr(gates, "pullback_vol_ratio", lambda df, direction: 5.0)
    frame, window = load_v74_fixture()["AAPL"], ("1900-01-01", "2100-12-31")
    for scope, engines in (("confluence", ("confluence",)), ("strategy", ("strategy",))):
        base = run_arm("AAPL", frame, engines, ("4w", "3m"), window, {})
        gated = run_arm("AAPL", frame, engines, ("4w", "3m"), window,
                        {"PULLBACK_DRYUP_SCOPE": scope, "PULLBACK_DRYUP_MAX_RATIO": 0.60})
        assert gated != base, scope
