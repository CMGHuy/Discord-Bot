# tests/scripts/test_structure_tier_report.py
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import structure_tier_report as tier  # noqa: E402
import volume_context_report as vcr  # noqa: E402

from tests.market.structure_tier_fixtures import DOWN, tier_frame  # noqa: E402


def _row(direction, r, *, source="confluence", **context):
    outcome = "win" if r > 0 else "loss"
    return vcr.ReportRow(source=source, direction=direction, outcome=outcome, r_multiple=r, context=context)


def _population(direction, n, *, k3, major, r, source="confluence"):
    return [_row(direction, r, source=source, structure_aligned=k3, structure_aligned_major=major)
            for _ in range(n)]


def _separating(direction="bullish", n=30):
    """Major alignment separates outcomes (+1R vs -1R); k=3 alignment does not."""
    return (_population(direction, n, k3=True, major=True, r=1.0)
            + _population(direction, n, k3=False, major=True, r=1.0)
            + _population(direction, n, k3=True, major=False, r=-1.0)
            + _population(direction, n, k3=False, major=False, r=-1.0))


def _swap_keys(row):
    """Exchange the k=3 and major alignment flags, so k=3 becomes the one that separates."""
    context = {"structure_aligned": row.context["structure_aligned_major"],
               "structure_aligned_major": row.context["structure_aligned"]}
    return vcr.ReportRow(row.source, row.direction, row.outcome, row.r_multiple, context)


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2025-06-30"),
                                       ("2019-06-01", "2023-12-31")])
def test_replay_refuses_any_window_outside_train(start, end, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert tier.main(["--source", "replay", "--start", start, "--end", end]) == 1
    assert "refused" in capsys.readouterr().out


@pytest.mark.parametrize("age,label", [(0, "0-5"), (5, "0-5"), (6, "6-20"), (20, "6-20"), (21, "21+"), (300, "21+")])
def test_event_bucket_uses_the_fixed_age_edges(age, label):
    context = {"struct_event_last": "choch_against", "struct_event_bars_ago": age}
    assert tier.event_bucket(context) == f"choch_against {label}"


def test_event_bucket_is_none_without_an_event_or_on_an_old_record():
    assert tier.event_bucket({"struct_event_last": None, "struct_event_bars_ago": None}) is None
    assert tier.event_bucket({"vol_ratio_20": 1.2}) is None


def test_reaction_uses_the_swing_low_for_longs_and_the_swing_high_for_shorts():
    rows = tier.derived([_row("bullish", 1.0, last_sl_reaction_atr=2.5, last_sh_reaction_atr=9.0),
                         _row("bearish", 1.0, last_sl_reaction_atr=9.0, last_sh_reaction_atr=1.5),
                         _row("unknown", 1.0, last_sl_reaction_atr=9.0)])
    assert [row.context["reaction_atr"] for row in rows] == [2.5, 1.5, None]


def test_reaction_edges_are_per_direction():
    rows = tier.derived([_row("bullish", 1.0, last_sl_reaction_atr=v) for v in (1, 2, 3, 4, 5)]
                        + [_row("bearish", 1.0, last_sh_reaction_atr=v) for v in (10, 20, 30, 40, 50)])
    assert tier.reaction_edges(rows) == {"bullish": [1.8, 2.6, 3.4, 4.2], "bearish": [18.0, 26.0, 34.0, 42.0]}


def test_a_bucket_under_thirty_prints_thin_and_no_expr():
    rows = _population("bullish", 29, k3=True, major=True, r=1.0)
    out = "\n".join(tier.table_lines(rows, "structure_aligned_major"))
    assert "N=   29  thin" in out and "ExpR" not in out
    full = "\n".join(tier.table_lines(rows + rows[:1], "structure_aligned_major"))
    assert "N=   30" in full and "ExpR +1.0000" in full


def test_spread_is_aligned_minus_not_aligned():
    result = tier.spread(_separating(), "structure_aligned_major")
    assert result == {"n_aligned": 60, "n_not_aligned": 60, "thin": False, "spread": 2.0}
    assert tier.spread(_separating(), "structure_aligned")["spread"] == 0.0


def test_verdict_more_informative_when_all_three_conditions_hold():
    result = tier.verdict(_separating("bullish") + _separating("bearish"))
    assert result["verdict"] == tier.MORE
    assert all(result["conditions"].values())


def test_verdict_passes_condition_three_when_the_bearish_side_is_thin():
    result = tier.verdict(_separating("bullish") + _separating("bearish", n=5))
    assert result["major_by_direction"]["bearish"]["thin"] is True
    assert result["verdict"] == tier.MORE


def test_verdict_fails_when_a_spread_bucket_is_thin():
    result = tier.verdict(_separating("bullish", n=14))            # 28 per alignment bucket
    assert result["conditions"]["all_four_buckets_n30"] is False
    assert result["verdict"] == tier.NOT_MORE


def test_verdict_fails_when_the_major_spread_is_not_larger():
    rows = [_swap_keys(row) for row in _separating("bullish") + _separating("bearish")]
    result = tier.verdict(rows)                                    # k=3 now separates, major does not
    assert result["conditions"]["major_spread_larger"] is False
    assert result["verdict"] == tier.NOT_MORE


def test_verdict_fails_when_the_directions_disagree_in_sign():
    flipped = [vcr.ReportRow(r.source, r.direction, "loss" if r.outcome == "win" else "win", -r.r_multiple,
                             r.context) for r in _separating("bearish", n=30)]
    result = tier.verdict(_separating("bullish", n=90) + flipped)
    assert result["conditions"]["major_spread_larger"] is True
    assert result["conditions"]["same_sign_both_directions"] is False
    assert result["verdict"] == tier.NOT_MORE


def test_verdict_ignores_strategy_sourced_rows():
    strategy = [vcr.ReportRow("strategy", r.direction, r.outcome, r.r_multiple, r.context)
                for r in _separating("bullish")]
    assert tier.verdict(strategy)["verdict"] == tier.NOT_MORE


def test_alignment_table_puts_k3_beside_major():
    lines = tier.alignment_lines(_separating("bullish"))
    true_line = next(line for line in lines if line.startswith("confluence bullish  True"))
    assert true_line.count("N=   60") == 2 and "k3" in true_line and "| major" in true_line
    assert "ExpR +0.0000" in true_line and "ExpR +1.0000" in true_line
    assert any(line.startswith("confluence bullish  None") and "thin" in line for line in lines)


def test_census_counts_pivots_and_bars_to_major():
    df = tier_frame(DOWN)                                          # dates start 2019-01-01
    pivots, lags = tier.census_of(df, ("2019-01-01", "2023-12-31"))
    assert (pivots, sorted(lags)) == (13, [5, 5, 5, 6, 6, 6, 6, 6, 6, 6])
    late, _ = tier.census_of(df, (str(df.index[50].date()), "2023-12-31"))
    assert late == 7                                               # only pivots formed inside the window
    cut, cut_lags = tier.census_of(df, ("2019-01-01", str(df.index[60].date())))
    assert (cut, len(cut_lags)) == (7, 4)                          # reads no bar after the window end


def test_census_all_pools_tickers_and_skips_missing_frames(monkeypatch):
    frames = {"AAA": tier_frame(DOWN), "BBB": tier_frame(DOWN, mirror=True), "CCC": None}
    monkeypatch.setattr(vcr, "load_frame", frames.get)
    census = tier.census_all(["AAA", "BBB", "CCC"], ("2019-01-01", "2023-12-31"))
    assert census == {"pivots": 26, "major": 20, "major_share_pct": 76.92, "median_bars_to_major": 6.0}
    assert tier.census_all(["CCC"], ("2019-01-01", "2023-12-31"))["major_share_pct"] is None


def test_replay_writes_edges_and_json_and_prints_the_verdict(tmp_path, monkeypatch, capsys):
    rows = _separating("bullish") + _separating("bearish")
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: rows)
    monkeypatch.setattr(tier, "census_all", lambda tickers, window: {"pivots": 0})
    edges, blob = tmp_path / "edges.json", tmp_path / "verdict.json"
    assert tier.main(["--source", "replay", "--tickers", "AAA", "--edges", str(edges), "--json", str(blob)]) == 0
    out = capsys.readouterr().out
    assert "DESCRIPTIVE ONLY" in out and f"VERDICT (confluence-sourced, pre-registered): {tier.MORE}" in out
    assert "Table 4" in out
    assert json.loads(edges.read_text(encoding="utf-8"))["window"] == ["2020-01-01", "2023-12-31"]
    saved = json.loads(blob.read_text(encoding="utf-8"))
    assert saved["verdict"] == tier.MORE and saved["closed"] == 240 and saved["census"] == {"pivots": 0}


def test_replay_refuses_to_overwrite_a_recorded_verdict(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    blob = tmp_path / "verdict.json"
    blob.write_text("{}", encoding="utf-8")
    assert tier.main(["--source", "replay", "--tickers", "AAA", "--json", str(blob)]) == 1
    assert "refused" in capsys.readouterr().out and blob.read_text(encoding="utf-8") == "{}"


def test_live_refuses_without_train_edges(tmp_path, capsys):
    assert tier.main(["--source", "live", "--edges", str(tmp_path / "missing.json")]) == 1
    assert "refused" in capsys.readouterr().out


def test_live_prints_the_holdout_warning_and_no_verdict(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2020-01-01", "2023-12-31"], "edges": {"bullish": null, "bearish": null}}',
                     encoding="utf-8")
    old = {"status": "win", "source": "confluence", "direction": "bullish", "entry": 100.0,
           "stop_loss": 95.0, "exit_price": 110.0, "entry_context": {"vol_ratio_20": 1.2}}
    monkeypatch.setattr(vcr, "load_live_trades", lambda: [old])
    assert tier.main(["--source", "live", "--edges", str(edges)]) == 0
    out = capsys.readouterr().out
    assert "holdout" in out and "VERDICT" not in out and "Table 4" not in out and "p=" not in out
    assert "confluence bullish  None" in out                       # an old record buckets as None, no KeyError

