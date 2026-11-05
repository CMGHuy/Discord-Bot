"""v190 V190-11: validate_component --instrument (spec §4: the funnel does not
accept v3 until a methodology spec maps Stage 2/3 to five folds)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import validate_component as vc  # noqa: E402

BASE = ["--stage", "mde", "--arms", "arms.json", "--title", "t", "--window", "w",
        "--bespoke-instrument", "test fixture"]


@pytest.fixture
def funnel(monkeypatch):
    """Stubs the data selection and the mde stage; records what ran."""
    seen = {"resolved": 0, "stages": []}

    def resolve(args):
        seen["resolved"] += 1

    def stage_mde(args):
        seen["stages"].append(args.instrument)
        return 0

    monkeypatch.setattr(vc.cache_dir_source, "resolve", resolve)
    monkeypatch.setattr(vc, "stage_mde", stage_mde)
    return seen


def test_the_default_instrument_is_v1_and_runs_as_before(funnel):
    assert vc.main(BASE) == 0
    assert funnel == {"resolved": 1, "stages": ["v1"]}


def test_explicit_v1_is_identical_to_the_default(funnel):
    assert vc.main([*BASE, "--instrument", "v1"]) == 0
    assert funnel == {"resolved": 1, "stages": ["v1"]}


def test_v3_is_refused_before_any_data_is_selected(funnel):
    with pytest.raises(SystemExit) as exc:
        vc.main([*BASE, "--instrument", "v3"])
    assert str(exc.value) == vc.V3_FUNNEL_REFUSAL
    assert funnel == {"resolved": 0, "stages": []}


def test_v3_is_refused_on_the_selection_stage_too(funnel, monkeypatch):
    monkeypatch.setattr(vc, "stage_selection", lambda args: pytest.fail("selection ran"))
    with pytest.raises(SystemExit) as exc:
        vc.main(["--stage", "selection", "--title", "t", "--window", "w", "--instrument", "v3"])
    assert str(exc.value) == vc.V3_FUNNEL_REFUSAL
    assert funnel["resolved"] == 0


def test_the_v3_refusal_names_what_is_missing_and_who_maps_it():
    for needle in ("--instrument v3", "Stage 2", "Stage 3", "three folds",
                   "GATE_MIN_IMPROVING_FOLDS = 2", "five folds", "2021-2025",
                   "methodology spec", "--instrument v1"):
        assert needle in vc.V3_FUNNEL_REFUSAL, needle


def test_v2_exits_through_require_v1(funnel):
    with pytest.raises(SystemExit,
                       match="validate_component.py: --instrument v2 is not wired yet"):
        vc.main([*BASE, "--instrument", "v2"])
    assert funnel == {"resolved": 0, "stages": []}


def test_an_unknown_instrument_is_an_argparse_error(funnel):
    with pytest.raises(SystemExit) as exc:
        vc.main([*BASE, "--instrument", "v9"])
    assert exc.value.code == 2
