from swingbot.core.backtesting.arms import reachability as reach

# v74 fixture: measured 2026-10-05, hl_trail (b=0.0) and progress_stall (c=1.0)
# each changed 0 outcomes or R versus off, so no replay-changes test lives here;
# coverage is V123-5's exit_sim tests (fixture_observable stays False).


def test_registered_reachable():
    for attr in ("RUNNER_STRUCTURE_EXIT", "RUNNER_HL_TRAIL_ATR_BUFFER", "RUNNER_STALL_RANGE_MAX"):
        assert reach.classify(attr) == reach.REACHABLE
        assert not reach.REGISTRY[attr].fixture_observable
