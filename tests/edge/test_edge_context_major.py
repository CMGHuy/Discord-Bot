# tests/edge/test_edge_context_major.py
"""v130: entry_context carries the major-tier keys; everything older is untouched.

Run ``python -m tests.edge.test_edge_context_major`` on UNCHANGED code to
(re)capture the witness file. Never recapture after touching context.py."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
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


if __name__ == "__main__":
    WITNESS.parent.mkdir(parents=True, exist_ok=True)
    WITNESS.write_text(json.dumps(_snapshots(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {WITNESS}")

