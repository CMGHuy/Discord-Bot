"""v125: the volume-context report buckets the nine new keys and renders the provenance cross-table."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import volume_context_report as vcr  # noqa: E402

V125_CATEGORICAL = ("target_capped", "stop_clamped", "leg_phase", "zone_state")
V125_CONTINUOUS = ("zone_dist_atr", "room_atr", "range_pos", "zone_touches", "zone_departure_atr")


def _row(source, direction, outcome, r, **context):
    return vcr.ReportRow(source=source, direction=direction, outcome=outcome, r_multiple=r, context=context)


def test_the_nine_keys_are_bucketed_and_v121_keys_are_kept():
    assert vcr.CATEGORICAL[-4:] == V125_CATEGORICAL
    assert vcr.CONTINUOUS[-5:] == V125_CONTINUOUS
    assert vcr.CATEGORICAL[:6] == ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
                                   "absorption_bar", "absorption_count_10")
    assert not set(vcr.CATEGORICAL) & set(vcr.CONTINUOUS)


def test_provenance_cross_table_splits_source_direction_and_cell():
    rows = [_row("confluence", "bullish", "win", 1.5, target_capped=True, stop_clamped=False),
            _row("confluence", "bullish", "loss", -1.0, target_capped=True, stop_clamped=False),
            _row("confluence", "bullish", "timeout", 0.25, target_capped=True, stop_clamped=False),
            _row("confluence", "bearish", "loss", -1.0, target_capped=True, stop_clamped=True),
            _row("strategy", "bullish", "win", 2.0, target_capped=False, stop_clamped=False),
            _row("strategy", "bullish", "loss", -1.0)]                       # an old record
    table = {(line["source"], line["direction"], line["target_capped"], line["stop_clamped"]): line
             for line in vcr.provenance_table(rows)}
    capped = table[("confluence", "bullish", "True", "False")]
    assert (capped["n"], capped["win_rate"], capped["sum_r"]) == (3, 50.0, 0.75)
    assert capped["expectancy_r"] == pytest.approx(0.25)
    assert table[("confluence", "bearish", "True", "True")]["sum_r"] == -1.0
    assert table[("strategy", "bullish", "False", "False")]["win_rate"] == 100.0
    assert table[("strategy", "bullish", "None", "None")]["n"] == 1
    assert len(table) == 4


def test_sum_r_skips_rows_without_an_r():
    rows = [_row("strategy", "bullish", "win", None, target_capped=True, stop_clamped=False)]
    assert vcr.provenance_table(rows)[0]["sum_r"] is None


def test_render_carries_the_cross_table_and_the_grid_warning():
    rows = [_row("confluence", "bullish", "win", 1.0, target_capped=True, stop_clamped=False,
                 leg_phase="pullback", range_pos=0.4)]
    out = vcr.render(rows, {"range_pos": [0.1, 0.2, 0.3, 0.5]}, source="replay")
    assert "== target_capped x stop_clamped ==" in out
    assert "structure-break entry spec" in out and "p=" not in out
    assert "== leg_phase ==" in out and "== range_pos ==" in out
    assert "capped=True  clamped=False" in out


def test_replay_writes_train_edges_for_the_v125_continuous_keys(tmp_path, monkeypatch):
    rows = [_row("confluence", "bullish", "win", 1.0, range_pos=v, zone_touches=n)
            for v, n in ((0.2, 1), (0.4, 2), (0.6, 3), (0.8, 4), (1.0, 5))]
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: rows)
    out_path = tmp_path / "edges.json"
    assert vcr.main(["--source", "replay", "--tickers", "AAA", "--edges", str(out_path)]) == 0
    edges = json.loads(out_path.read_text(encoding="utf-8"))["edges"]
    assert edges["range_pos"] == [0.36, 0.52, 0.68, 0.84]
    assert edges["zone_touches"] == [1.8, 2.6, 3.4, 4.2]
    assert edges["zone_dist_atr"] is None                          # no values -> no edges


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2026-10-02")])
def test_replay_refusal_is_inherited(start, end, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert vcr.main(["--source", "replay", "--start", start, "--end", end]) == 1
    assert "refused" in capsys.readouterr().out
