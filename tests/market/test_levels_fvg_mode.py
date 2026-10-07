"""v128: the FVG mode reaches collect_candidate_levels and count_confirming_strategies."""
import dataclasses
import json
import types
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.market import fvg, levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.scan_params import ScanParams
from tests.market.fvg_frames import BULL_THIRD, STRONG_BULL, WEAK_BULL, gap_frame, witness_frame

WITNESS = Path(__file__).resolve().parents[1] / "fixtures" / "v128" / "levels_all_witness.json"
H = HORIZONS["3m"]


def _params(**changes):
    pinned = {"avwap_levels_enabled": True, "volume_profile_nodes_enabled": False,
              "fvg_levels_mode": "all", "fvg_displacement_atr_k": 1.5}
    return dataclasses.replace(ScanParams.from_config(), **{**pinned, **changes})


def _collect(frame, params):
    return levels.collect_candidate_levels(frame, H, float(frame["Close"].iloc[-1]), params=params)


def _split(candidates):
    return ([c for c in candidates if c[1].startswith("FVG")],
            [c for c in candidates if not c[1].startswith("FVG")])


def _families(frame, params, target=101.25):
    price = float(frame["Close"].iloc[-1])
    candidates = levels.collect_candidate_levels(frame, H, price, params=params)
    return levels.count_confirming_strategies(frame, H, price, target, tolerance_pct=0.1,
                                              candidates=candidates)[1]


def test_default_mode_matches_the_pre_change_witness():
    expected = [tuple(row) for row in json.loads(WITNESS.read_text(encoding="utf-8"))]
    assert _collect(witness_frame(), _params()) == expected


def test_off_emits_no_fvg_candidate_and_leaves_every_other_source_alone():
    frame = witness_frame()
    off_fvg, off_rest = _split(_collect(frame, _params(fvg_levels_mode="off")))
    _, all_rest = _split(_collect(frame, _params()))
    assert off_fvg == [] and off_rest == all_rest


@pytest.mark.parametrize("k", [1.0, 1.5, 2.0])
def test_displacement_emits_exactly_the_filtered_gaps(k):
    frame = witness_frame()
    disp_fvg, disp_rest = _split(_collect(frame, _params(fvg_levels_mode="displacement",
                                                         fvg_displacement_atr_k=k)))
    _, all_rest = _split(_collect(frame, _params()))
    assert disp_fvg == fvg.find_fair_value_gaps(frame, mode="displacement", k=k)
    assert disp_rest == all_rest


def test_fvg_family_follows_the_mode():
    strong, weak = gap_frame(STRONG_BULL, BULL_THIRD), gap_frame(WEAK_BULL, BULL_THIRD)
    assert "FVG" in _families(strong, _params())
    assert "FVG" not in _families(strong, _params(fvg_levels_mode="off"))
    assert "FVG" in _families(strong, _params(fvg_levels_mode="displacement"))
    assert "FVG" in _families(weak, _params())
    assert "FVG" not in _families(weak, _params(fvg_levels_mode="displacement"))


def test_the_config_driven_replay_path_honours_the_mode(monkeypatch):
    """Replay passes no params: collect_candidate_levels builds them from config,
    which is exactly what measure_arms' apply_knobs mutates."""
    strong = gap_frame(STRONG_BULL, BULL_THIRD)
    price = float(strong["Close"].iloc[-1])
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "off")
    assert "FVG" not in levels.count_confirming_strategies(strong, H, price, 101.25, tolerance_pct=0.1)[1]
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "all")
    assert "FVG" in levels.count_confirming_strategies(strong, H, price, 101.25, tolerance_pct=0.1)[1]


def test_a_renamed_field_fails_loudly():
    fields = {k: v for k, v in dataclasses.asdict(_params()).items() if k != "fvg_levels_mode"}
    with pytest.raises(AttributeError):
        levels.collect_candidate_levels(witness_frame(), H, 100.0, params=types.SimpleNamespace(**fields))
