import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import _scale_out_exit_walk
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.structure_fixtures import WARMUP, sawtooth, sawtooth_closes, stall_frame
from tests.planning.test_exit_sim_runner_structure import _runner_plan
from tests.planning.test_plan_manager_structure_exit import at, manager, partial_plan


def _live(df):
    view = [WARMUP + 2]
    store, mgr = manager(df, partial_plan(df), view)
    stops, exit_day = {}, None
    for k in range(WARMUP + 1, len(df) - 1):
        view[0] = k + 2
        day = df.index[k + 1].date()
        for n, col in enumerate(("Open", "Low", "Close")):
            mgr._step_partial(store.get("p1"), float(df[col].iloc[k + 1]), at(day, 15 + n))
            if n == 0:
                stops[k] = store.get("p1").working_stop
            if store.get("p1").status == PlanStatus.CLOSED:
                exit_day = day
                break
        if exit_day is not None:
            break
    return stops, exit_day


@pytest.mark.parametrize("mode,frame", [("hl_trail", "drop"), ("progress_stall", "stall")])
def test_replay_and_live_agree(monkeypatch, mode, frame):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", mode)
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.25)
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.70)
    df = stall_frame() if frame == "stall" else sawtooth(4, tail=(sawtooth_closes(4)[-1] - 6.0,))
    trace = []
    replay = _scale_out_exit_walk(df, WARMUP - 1, 100.0, _runner_plan(), 60, trace=trace)
    stops, exit_day = _live(df)
    for j, stop in trace:
        if j in stops:
            assert stops[j] == pytest.approx(stop), f"stop after bar {j}"
    assert exit_day == df.index[replay.exit_index].date()
