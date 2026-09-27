import pytest

from swingbot.core.backtesting.arms import windows as w


def test_only_validation_touches_the_validation_window():
    for name, spec in w.STAGES.items():
        start, end = spec.signal_window
        if name == "validation":
            assert start == w.VALIDATION_START
        else:
            assert end < w.VALIDATION_START, name


def test_folds_sit_inside_their_stage_window():
    for spec in w.STAGES.values():
        for _label, start, end in spec.folds:
            assert spec.signal_window[0] <= start <= end <= spec.signal_window[1]


def test_walkforward_folds_are_the_three_documented_test_years():
    spec = w.STAGES["walkforward"]
    assert [fold[0] for fold in spec.folds] == ["2021", "2022", "2023"]
    assert spec.fold_key == "folds" and spec.fold_label_key == "test_year"


def test_pilot_is_narrow_and_everything_else_is_full():
    universe = [f"T{i:02d}" for i in range(30)]
    assert w.universe_for("pilot", universe) == sorted(universe)[:w.PILOT_TICKERS]
    for stage in ("selection", "walkforward", "validation"):
        assert w.universe_for(stage, universe) == sorted(universe)


def test_every_funnel_stage_maps_to_a_producer_stage():
    assert set(w.FUNNEL_TO_PRODUCER_STAGE.values()) <= set(w.STAGES)


def test_unknown_stage_is_an_error():
    with pytest.raises(ValueError):
        w.resolve("nonsense")
