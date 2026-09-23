"""v92 Hypothesis 2: the STALL_EXIT_ENABLED resolver in params.py.

Deliberately its own test file rather than tests/edge/test_edge_stops.py --
that file's resolver tests are all gated on DATA_DRIVEN_STOPS_ENABLED, an
older, closed pre-registration this task's flag must stay independent of
(see the spec's provenance note). tests/planning/ had no dedicated resolver
test file yet, so this is the new home for params.py's own resolvers.
"""
from swingbot import config
from swingbot.core.planning import params as plan_params


def test_resolve_stall_exit_day_none_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    assert plan_params._resolve_stall_exit_day("RSI") is None


def test_resolve_stall_exit_day_none_on_lookup_failure(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    monkeypatch.setattr(plan_params, "_journal_entries",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert plan_params._resolve_stall_exit_day("RSI") is None


def test_resolve_stall_exit_day_calls_optimal_time_stop_days(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    monkeypatch.setattr(plan_params, "_journal_entries", lambda: ["entry"])
    import swingbot.core.edge.stops as stops_mod
    monkeypatch.setattr(stops_mod, "optimal_time_stop_days",
                        lambda entries, strategy: 7)
    assert plan_params._resolve_stall_exit_day("RSI") == 7
