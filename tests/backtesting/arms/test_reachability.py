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
            assert reach.observed_by and reach.observed_by <= {"confluence", "strategy"}, attr
        else:
            assert not reach.observed_by and not reach.fixture_observable, attr


def test_journal_knobs_are_refused():
    assert r.classify("STALL_EXIT_ENABLED") == r.JOURNAL_DEPENDENT
    assert r.classify("DATA_DRIVEN_STOPS_ENABLED") == r.JOURNAL_DEPENDENT


def test_unknown_knob_is_unclassified():
    assert r.classify("NOT_A_KNOB") == r.UNCLASSIFIED
    assert "not a searchable" in r.reason("NOT_A_KNOB")
