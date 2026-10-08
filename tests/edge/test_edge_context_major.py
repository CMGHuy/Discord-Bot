# tests/edge/test_edge_context_major.py
"""v130: entry_context carries the major-tier keys; everything older is untouched.

Run ``python -m tests.edge.test_edge_context_major`` on UNCHANGED code to
(re)capture the witness file. Never recapture after touching context.py."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from swingbot.core.market.structure import MAJOR_KEYS, major_structure_features   # top of file
from tests.market.structure_fixtures import wavy_frame
from tests.market.structure_tier_fixtures import DOWN, tier_frame

WITNESS = Path(__file__).resolve().parents[1] / "fixtures" / "v130" / "entry_context_witness.json"
MAJOR_NEW = ("structure_state_major", "structure_aligned_major", "major_sh_atr", "major_sl_atr",
             "struct_event_last", "struct_event_bars_ago", "last_sl_reaction_atr", "last_sh_reaction_atr")
ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
FRAMES = {"wavy": wavy_frame, "down": lambda: tier_frame(DOWN), "up": lambda: tier_frame(DOWN, mirror=True)}


def _context(df, direction):
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w",
                         stop=close - sign * 6.0, target=close + sign * 12.0, asof=ASOF)


def _snapshots():
    return {f"{name}/{direction}": _context(build(), direction)
            for name, build in FRAMES.items() for direction in ("bullish", "bearish")}


def test_every_older_key_is_byte_identical_to_the_witness():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    now = json.loads(json.dumps(_snapshots()))
    assert set(witness) == set(now)
    for case, before in witness.items():
        assert len(before) == 43, case                      # 20 pre-v121 keys + v121's 14
        assert {key: now[case][key] for key in before} == before, case


def test_feature_keys_append_the_major_keys_last():
    assert len(FEATURE_KEYS) == 51
    assert FEATURE_KEYS[43:] == MAJOR_NEW == MAJOR_KEYS
    assert FEATURE_KEYS[20] == "structure_state" and FEATURE_KEYS[33] == "impulse_range_decay"


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_carries_the_major_features(name, direction):
    df = FRAMES[name]()
    out = _context(df, direction)
    assert set(out) == set(FEATURE_KEYS)
    assert {key: out[key] for key in MAJOR_KEYS} == major_structure_features(df, direction)


def test_the_fixture_snapshot_is_not_vacuous():
    out = _context(tier_frame(DOWN).iloc[:97], "bullish")       # two bars after the bullish CHoCH at bar 94
    assert (out["struct_event_last"], out["struct_event_bars_ago"]) == ("choch_with", 2)
    assert out["structure_state_major"] == "down" and out["structure_aligned_major"] is False
    assert out["structure_state"] is not None                   # v121's k=3 state sits beside it


@pytest.mark.parametrize("bars", [10, 40, 59])
def test_short_frames_leave_every_major_key_none(bars):
    out = _context(wavy_frame().iloc[:bars], "bullish")
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in MAJOR_NEW)


def test_live_stamp_carries_the_major_keys():
    from swingbot.core.planning.params import stamp_entry_context
    df = tier_frame(DOWN).iloc[:97]
    close = float(df["Close"].iloc[-1])
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=close + 6.0,
                           tp1=close - 12.0, entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["struct_event_last"] == "choch_against"

if __name__ == "__main__":
    WITNESS.parent.mkdir(parents=True, exist_ok=True)
    WITNESS.write_text(json.dumps(_snapshots(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {WITNESS}")

