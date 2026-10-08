# tests/scripts/test_fvg_attribution.py
"""v128 attribution helper: provenance, buckets, frozen clause 6, context slice."""
import inspect
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import fvg_attribution as fa  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.backtesting.arms.engine import run_arm  # noqa: E402
from swingbot.core.backtesting.arms.provenance import build_stamp  # noqa: E402
from swingbot.core.market import fvg, levels  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402
from tests.market.fvg_frames import BULL_THIRD, STRONG_BULL, WEAK_BULL, gap_frame, witness_frame  # noqa: E402


def _trade(ticker, outcome, *, source="confluence", day=1, horizon="3m", direction="bullish"):
    r = 2.0 if outcome == "win" else -1.0
    return ArmTrade(ticker, "S/R Confluence", horizon, f"2019-03-{day:02d}", outcome, r, 2.0, source, direction)


def _prov(trades, cid, vote=False, price=False, fvg_family=False):
    return {t.key: {"fvg_family": fvg_family, "candidates": {cid: {"vote": vote, "price": price}}} for t in trades}


def test_cluster_members_matches_levels_cluster_levels():
    frame = witness_frame()
    candidates = levels.collect_candidate_levels(frame, HORIZONS["3m"], float(frame["Close"].iloc[-1]))
    mine = fa.cluster_members(candidates)
    theirs = levels._cluster_levels(candidates)
    assert [mean for mean, _ in mine] == [level.price for level in theirs]
    assert [[label for _, label in members] for _, members in mine] == [level.sources for level in theirs]


def test_filtered_mids_follow_the_mode():
    strong, weak = gap_frame(STRONG_BULL, BULL_THIRD), gap_frame(WEAK_BULL, BULL_THIRD)
    strong_gaps, weak_gaps = fvg.find_fair_value_gaps_detailed(strong), fvg.find_fair_value_gaps_detailed(weak)
    assert fa.filtered_mids(strong, strong_gaps, "all", 1.5) == []
    assert fa.filtered_mids(strong, strong_gaps, "off", 1.5) == [101.25]
    assert fa.filtered_mids(strong, strong_gaps, "displacement", 1.5) == []
    assert fa.filtered_mids(weak, weak_gaps, "displacement", 1.5) == [101.25]


def test_vote_is_lost_only_when_no_kept_fvg_still_votes():
    candidates = [(101.25, "FVG (bullish)"), (150.0, "EMA20")]
    assert fa.vote_lost(candidates, 101.25, [101.25]) is True
    assert fa.vote_lost(candidates + [(101.30, "FVG (bullish)")], 101.25, [101.25]) is False
    assert fa.vote_lost(candidates, 101.25, []) is False
    assert fa.vote_lost([(150.0, "EMA20")], 101.25, [101.25]) is False


def test_buckets_cover_vote_price_both_and_unaffected():
    trades = [_trade("A", "loss", day=d) for d in range(1, 5)]
    prov = {}
    for trade, (vote, price) in zip(trades, [(True, False), (False, True), (True, True), (False, False)]):
        prov.update(_prov([trade], "off", vote, price))
    assert fa.buckets_for(trades, prov, "off", trades) == ["vote_only", "price_only", "both", "unaffected"]


def test_strategy_rows_use_the_pairing_proxy():
    kept, gone, moved = (_trade("S", "win", source="strategy", day=d) for d in (1, 2, 3))
    component = [kept, ArmTrade(**{**asdict(moved), "r_multiple": 1.5})]
    assert fa.buckets_for([kept, gone, moved], {}, "off", component) == ["unaffected", "price_only", "price_only"]


def test_a_baseline_confluence_trade_without_provenance_raises():
    with pytest.raises(KeyError, match="no provenance"):
        fa.buckets_for([_trade("A", "loss")], {}, "off", [])


def test_mechanism_passes_when_the_removed_trades_are_the_bad_ones():
    removed = [_trade(f"T{t}", "loss", day=d) for t in range(5) for d in (1, 2)]
    retained = [_trade(f"T{t}", o, day=d) for t in range(5) for d, o in ((3, "win"), (4, "loss"))]
    baseline = removed + retained
    buckets = ["vote_only"] * len(removed) + ["unaffected"] * len(retained)
    clause = fa.mechanism_clause(baseline, buckets)
    assert clause.name == "mechanism" and clause.verdict == "PASS"


def test_mechanism_fails_when_winners_are_removed_or_a_population_is_empty():
    winners = [_trade(f"T{t}", "win", day=1) for t in range(5)]
    losers = [_trade(f"T{t}", "loss", day=2) for t in range(5)]
    assert fa.mechanism_clause(winners + losers, ["price_only"] * 5 + ["unaffected"] * 5).verdict == "FAIL"
    assert fa.mechanism_clause(losers, ["unaffected"] * 5).verdict == "FAIL"


def test_attribution_reports_direction_and_flags_horizon_concentration():
    baseline = [_trade("A", "loss", day=d, horizon="3m") for d in (1, 2, 3)] + [_trade("A", "win", day=4, horizon="6m", direction="bearish")]
    info = fa.attribution(baseline, ["vote_only", "vote_only", "both", "unaffected"], baseline[:2])
    assert info["removed"]["n"] == 3 and info["top2_horizon_share"] == 1.0
    assert set(info["per_direction"]) == {"bullish", "bearish"}
    assert "OVER 80%" in fa.render_attribution("off", info)


def test_context_slice_splits_on_fvg_in_families():
    tagged, untagged = _trade("A", "win", day=1), _trade("A", "loss", day=2)
    prov = {**_prov([tagged], "off", fvg_family=True), **_prov([untagged], "off", fvg_family=False)}
    info = fa.context_slice([tagged, untagged, _trade("S", "win", source="strategy", day=3)], prov)
    assert (info["fvg_in_families"]["n"], info["fvg_not_in_families"]["n"], info["strategy_rows_excluded"]) == (1, 1, 1)


def test_replay_still_has_the_shape_the_recorder_patches():
    source = inspect.getsource(bs.replay_scenarios)
    assert "levels_asof(ticker, df, i, horizon_key, cache)" in source
    assert "build_confluence_plan(" in source and "tolerance_pct=5.0" in source
    assert fa.VOTE_TOLERANCE_PCT == 5.0


def _write_arms(tmp_path, knobs, baseline, component, engine_hash):
    stamp = build_stamp(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["A"],
                        horizons=("3m",), engines=("confluence",), knob_delta=knobs,
                        engine_hash_baseline=engine_hash, engine_hash_component=engine_hash, changed_outcomes=1)
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"provenance": stamp, "baseline": [asdict(t) for t in baseline],
                                "component": [asdict(t) for t in component]}), encoding="utf-8")
    return path


def test_report_refuses_a_code_mismatch(tmp_path, capsys):
    trades = [_trade("A", "loss")]
    arms = _write_arms(tmp_path, {"FVG_LEVELS_MODE": "off"}, trades, [], "h")
    provenance = tmp_path / "prov.json"
    provenance.write_text(json.dumps({"engine_hash": "other", "signal_window": ["2018-06-01", "2020-12-31"],
                                      "rows": []}), encoding="utf-8")
    assert fa.main(["report", "--arms", str(arms), "--provenance", str(provenance), "--candidate", "off"]) == 1
    assert "refused:code-mismatch" in capsys.readouterr().err


def test_report_refuses_a_candidate_whose_knobs_differ(tmp_path, capsys):
    arms = _write_arms(tmp_path, {"FVG_LEVELS_MODE": "displacement", "FVG_DISPLACEMENT_ATR_K": 2.0}, [], [], "h")
    provenance = tmp_path / "prov.json"
    provenance.write_text(json.dumps({"engine_hash": "h", "signal_window": ["2018-06-01", "2020-12-31"],
                                      "rows": []}), encoding="utf-8")
    assert fa.main(["report", "--arms", str(arms), "--provenance", str(provenance), "--candidate", "disp-1.0"]) == 1
    assert "refused:candidate-mismatch" in capsys.readouterr().err


@pytest.mark.slow
def test_recorder_sees_every_baseline_confluence_trade_and_off_voids_every_fvg_vote():
    ticker, frame = sorted(load_v74_fixture().items())[0]
    window = ("1900-01-01", "2100-12-31")
    rows = fa.record_ticker(ticker, frame, ("3m",), window)
    arm = run_arm(ticker, frame, ("confluence",), ("3m",), window, {})
    assert arm, "fixture must produce confluence trades or this test proves nothing"
    assert {t.key for t in arm} <= {tuple(row["key"]) for row in rows}
    assert all(row["candidates"]["off"]["vote"] == row["fvg_family"] for row in rows)
