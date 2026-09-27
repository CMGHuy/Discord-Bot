import pytest

from swingbot.core.backtesting.arms import provenance as pv
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS

UNIVERSE = ["AAA", "BBB", "CCC"]


def stamp(**over):
    kw = dict(stage="selection", signal_window=("2018-06-01", "2022-12-31"),
              universe=UNIVERSE, horizons=ALL_HORIZONS, engines=("confluence", "strategy"),
              knob_delta={"MIN_REWARD_PCT": 4.0}, engine_hash_baseline="h",
              engine_hash_component="h", changed_outcomes=12)
    kw.update(over)
    return {"provenance": pv.build_stamp(**kw)}


def test_good_stamp_passes():
    assert pv.check_stamp(stamp(), funnel_stage="mde", full_universe=UNIVERSE) is None


@pytest.mark.parametrize("blob,funnel_stage,token", [
    ({"baseline": []}, "mde", "refused:unstamped"),
    (stamp(stage="pilot"), "mde", "refused:stage-mismatch"),
    (stamp(engine_hash_component="other"), "mde", "refused:engine-mismatch"),
    (stamp(signal_window=("2018-06-01", "2024-03-01")), "mde", "refused:window-contact"),
    (stamp(universe=UNIVERSE[:2]), "mde", "refused:narrow-universe"),
    (stamp(horizons=ALL_HORIZONS[:3]), "mde", "refused:narrow-universe"),
])
def test_each_refusal_token(blob, funnel_stage, token):
    assert pv.check_stamp(blob, funnel_stage=funnel_stage, full_universe=UNIVERSE) == token
    assert token in pv.REFUSAL_TOKENS


def test_pilot_may_be_narrow():
    blob = stamp(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["AAA"])
    assert pv.check_stamp(blob, funnel_stage="reachability", full_universe=UNIVERSE) is None


def test_validation_may_touch_the_validation_window():
    blob = stamp(stage="validation", signal_window=("2024-01-01", "2025-12-31"))
    assert pv.check_stamp(blob, funnel_stage="validation", full_universe=UNIVERSE) is None


def test_code_hash_tracks_file_content(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = pv.code_hash(tmp_path)
    assert pv.code_hash(tmp_path) == first
    (tmp_path / "a.py").write_text("x = 2\n")
    assert pv.code_hash(tmp_path) != first
