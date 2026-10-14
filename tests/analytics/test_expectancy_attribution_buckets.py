"""v146 study core: attribution rows, tie-safe quantile bins, earnings
buckets, the friction model and the per-population bucket tables."""
from __future__ import annotations

import json

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.market.strategy_types import HORIZONS

HK = next(iter(HORIZONS))
HOLD = HORIZONS[HK]["max_holding_days"]


def _row(r=0.5, score=60, **over):
    row = {
        "r": r, "r_gross": r + 0.05, "week": "2025-01-06",
        "confidence_score": score, "confidence_level": 4,
        "confidence_points": {"MACD momentum": 10}, "confidence_unevaluated": [],
        "confluence_count": 3, "regime2_state": "bull_quiet", "rs_pctile": 72.0,
        "direction": "bullish", "horizon": HK,
        "earnings_sessions": 12, "earnings_status": "known",
        "risk_reward_ratio": 2.0,
    }
    row.update(over)
    return row


@pytest.fixture
def no_frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 0.0, raising=False)


@pytest.fixture
def frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 10.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def test_constants_are_the_specs():
    assert ea.THIN_N == 30
    assert ea.EARNINGS_BUCKETS == ("0-5", "6-10", "11-20", ">20", "none", "unknown")
    assert tuple(_row()) == ea.ROW_KEYS


def test_quantile_bins_splits_distinct_values_evenly():
    assert ea.quantile_bins(list(range(10)), 5) == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_quantile_bins_is_aligned_with_the_input_order():
    assert ea.quantile_bins([3.0, 1.0, 2.0], 3) == [2, 0, 1]


def test_quantile_bins_never_splits_a_tied_block():
    # ranks 0-3 tie: median rank 1.5 -> bin 0; the block is not cut at rank 2.
    assert ea.quantile_bins([1, 1, 1, 1, 2, 3], 3) == [0, 0, 0, 0, 2, 2]


def test_a_straddling_tied_block_goes_to_its_median_ranks_bin():
    # the 5s hold ranks 2-5 of 8: median rank 3.5 -> the lower half.
    assert ea.quantile_bins([1, 2, 5, 5, 5, 5, 9, 10], 2) == [0, 0, 0, 0, 0, 0, 1, 1]


def test_an_all_tied_sample_lands_in_the_middle_bin():
    assert ea.quantile_bins([7] * 9, 3) == [1] * 9


def test_quantile_bins_of_nothing_is_nothing():
    assert ea.quantile_bins([], 10) == []


@pytest.mark.parametrize("sessions, expected", [
    (0, "0-5"), (5, "0-5"), (6, "6-10"), (10, "6-10"),
    (11, "11-20"), (20, "11-20"), (21, ">20"), (400, ">20"),
])
def test_earnings_bucket_edges(sessions, expected):
    assert ea.earnings_bucket(_row(earnings_sessions=sessions)) == expected
    assert expected in ea.EARNINGS_BUCKETS


def test_earnings_bucket_none_and_unknown():
    assert ea.earnings_bucket(_row(earnings_sessions=None, earnings_status="none")) == "none"
    assert ea.earnings_bucket(_row(earnings_sessions=None, earnings_status="unknown")) == "unknown"
    assert ea.earnings_bucket(_row(earnings_sessions=None, earnings_status="known")) == "unknown"
    assert ea.earnings_bucket(_row(earnings_sessions=-2)) == "unknown"


def test_earnings_in_hold_uses_the_horizons_max_holding_days():
    assert ea.earnings_in_hold(_row(earnings_sessions=HOLD)) == "yes"
    assert ea.earnings_in_hold(_row(earnings_sessions=HOLD + 1)) == "no"
    assert ea.earnings_in_hold(_row(earnings_sessions=None, earnings_status="none")) == "no"
    assert ea.earnings_in_hold(_row(earnings_sessions=None, earnings_status="unknown")) == "unknown"
    assert ea.earnings_in_hold(_row(horizon="no-such-horizon")) == "unknown"


def test_net_r_without_frictions_is_the_plain_r(no_frictions):
    legs = [{"fraction": 1.0, "exit_price": 110.0}]
    assert ea.net_r(100.0, 95.0, "bullish", legs) == pytest.approx(2.0)
    short = [{"fraction": 1.0, "exit_price": 90.0}]
    assert ea.net_r(100.0, 105.0, "bearish", short) == pytest.approx(2.0)


def test_net_r_blends_legs_by_fraction(no_frictions):
    legs = [{"fraction": 0.5, "exit_price": 110.0, "r": 99.0},   # a recorded r is ignored
            {"fraction": 0.5, "exit_price": 100.0}]
    assert ea.net_r(100.0, 95.0, "bullish", legs) == pytest.approx(1.0)


def test_net_r_applies_slippage_both_sides_and_commission(frictions):
    bull = ea.net_r(100.0, 95.0, "bullish", [{"fraction": 1.0, "exit_price": 110.0}])
    assert bull == pytest.approx((109.89 - 100.1) / (100.1 - 95.0) - 0.02)
    bear = ea.net_r(100.0, 105.0, "bearish", [{"fraction": 1.0, "exit_price": 90.0}])
    assert bear == pytest.approx((99.9 - 90.09) / (105.0 - 99.9) - 0.02)


def test_a_full_stop_out_costs_more_than_one_r_net(frictions):
    assert ea.net_r(100.0, 95.0, "bullish", [{"fraction": 1.0, "exit_price": 95.0}]) < -1.0


def test_net_r_refuses_no_legs_and_zero_risk(no_frictions):
    with pytest.raises(ValueError):
        ea.net_r(100.0, 95.0, "bullish", [])
    with pytest.raises(ValueError):
        ea.net_r(100.0, 100.0, "bullish", [{"fraction": 1.0, "exit_price": 101.0}])


def test_bucket_stats_counts_net_wins_and_flags_thin():
    stats = ea.bucket_stats([_row(r=1.0), _row(r=-1.0), _row(r=0.5)])
    assert stats["n"] == 3 and stats["thin"] is True
    assert stats["win_rate"] == pytest.approx(200.0 / 3)
    assert stats["exp_r"] == pytest.approx(0.5 / 3)
    assert stats["exp_r_gross"] == pytest.approx(0.5 / 3 + 0.05)
    assert list(stats) == ["n", "win_rate", "exp_r", "exp_r_gross", "thin"]


def test_bucket_stats_at_the_floor_is_not_thin_and_empty_is_null():
    assert ea.bucket_stats([_row()] * 30)["thin"] is False
    assert ea.bucket_stats([_row()] * 29)["thin"] is True
    assert ea.bucket_stats([]) == {"n": 0, "win_rate": None, "exp_r": None,
                                   "exp_r_gross": None, "thin": True}


def _population():
    rows = []
    for i in range(100):
        rows.append(_row(
            r=(i % 7 - 3) / 4.0, score=i + 1,
            confidence_unevaluated=["ADX trend strength"] if i < 4 else [],
            risk_reward_ratio=1.0 + (i % 10) / 10.0,
            direction="bullish" if i % 4 else "bearish",
            rs_pctile=float(i), confluence_count=2 + i % 3,
            earnings_sessions=i % 30))
    rows.append(_row(score=None, confidence_level=None, confidence_points=None,
                     direction="bearish", rs_pctile=None, confluence_count=None,
                     earnings_sessions=None, earnings_status="unknown"))
    return rows


def test_population_buckets_has_every_grouping():
    buckets = ea.population_buckets(_population())
    assert list(buckets) == ["confidence_decile", "confidence_level", "confluence",
                             "regime2_state", "rs_quintile", "direction", "horizon",
                             "earnings", "earnings_in_hold"]
    for grouping in buckets.values():
        for bucket in grouping:
            assert list(bucket)[:7] == ["label", "n", "win_rate", "exp_r",
                                        "exp_r_gross", "thin", "q"]
            assert bucket["q"] is None
    json.dumps(buckets)   # JSON-serialisable as is


def test_deciles_are_population_quantiles_of_the_scored_rows():
    deciles = ea.population_buckets(_population())["confidence_decile"]
    assert [bucket["n"] for bucket in deciles] == [10] * 10       # the unscored row is out
    assert deciles[0]["label"] == "D1 (1-10)" and deciles[-1]["label"] == "D10 (91-100)"
    assert all(bucket["thin"] for bucket in deciles)
    assert deciles[0]["unevaluated_n"] == 4 and deciles[1]["unevaluated_n"] == 0
    assert deciles[0]["rr"] == {"p25": pytest.approx(1.225), "median": pytest.approx(1.45),
                                "p75": pytest.approx(1.675)}


def test_tied_scores_share_a_decile():
    rows = [_row(score=50) for _ in range(40)] + [_row(score=90) for _ in range(10)]
    deciles = ea.population_buckets(rows)["confidence_decile"]
    assert [(bucket["label"], bucket["n"]) for bucket in deciles] == [
        ("D4 (50-50)", 40), ("D9 (90-90)", 10)]


def test_non_confidence_groupings_keep_unscored_rows_and_order_labels():
    buckets = ea.population_buckets(_population())
    assert sum(bucket["n"] for bucket in buckets["direction"]) == 101
    assert sum(bucket["n"] for bucket in buckets["confidence_level"]) == 100
    assert [bucket["label"] for bucket in buckets["rs_quintile"]] == [
        "Q1", "Q2", "Q3", "Q4", "Q5", "unknown"]
    assert [bucket["label"] for bucket in buckets["confluence"]] == ["2", "3", "4", "unknown"]
    assert [bucket["label"] for bucket in buckets["earnings"]] == [
        "0-5", "6-10", "11-20", ">20", "unknown"]
    assert {bucket["label"] for bucket in buckets["earnings_in_hold"]} <= {"yes", "no", "unknown"}
