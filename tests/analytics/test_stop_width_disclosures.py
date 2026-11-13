"""v226: stop-width disclosures -- per-bucket stats and mix, the clamped
share with None rows out of its denominator, the live-only family and
same-day-loss shares, rho/overlap of stop_atr vs atr_pct, and the removal
arithmetic. Printed, never gating."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import expectancy_attribution as ea

TRAIN_KEYS = ["n", "win_rate", "exp_r", "exp_r_gross", "median_rr", "direction_share",
              "horizon_share", "delta_by_direction", "clamped_share", "clamped_none",
              "removal"]
LIVE_KEYS = TRAIN_KEYS + ["family_share", "same_day_loss_share"]


def _row(r=0.0, *, stop_atr=1.0, direction="bullish", horizon="2w", atr_pct=None,
         clamped=None, rr=2.0, **extra) -> dict:
    row = {"r": r, "r_gross": r + 0.05, "week": "2021-03-01", "direction": direction,
           "horizon": horizon, "risk_reward_ratio": rr, "stop_atr": stop_atr,
           "atr_pct": atr_pct, "stop_clamped": clamped}
    row.update(extra)
    return row


def _pop(buckets: dict, unknown: int = 0) -> dict:
    return {"buckets": dict(buckets),
            "known": [row for rows in buckets.values() for row in rows], "unknown": unknown}


def _groups(train: dict, live: dict | None = None, *, unknown=(0, 0)) -> dict:
    live = live if live is not None else {label: [] for label in train}
    return {"edges": [1.5], "labels": list(train),
            "train": _pop(train, unknown[0]), "live": _pop(live, unknown[1])}


def test_the_shape_is_per_population_and_live_has_two_more_keys():
    groups = _groups({"Q1": [_row(-1.0)], "Q2": [_row(1.0)]}, unknown=(3, 1))
    out = ea.stop_width_disclosures(groups)
    assert list(out) == ["train", "live"]
    for name in ("train", "live"):
        assert list(out[name]) == ["unknown", "rho", "overlap", "buckets"]
        assert list(out[name]["buckets"]) == ["Q1", "Q2"]
    assert list(out["train"]["buckets"]["Q1"]) == TRAIN_KEYS
    assert list(out["live"]["buckets"]["Q1"]) == LIVE_KEYS
    assert (out["train"]["unknown"], out["live"]["unknown"]) == (3, 1)
    assert ea.VOLATILITY_RHO == 0.8 and ea.DIRECTION_MIN_N == 100


def test_bucket_stats_median_rr_and_mix():
    bucket = [_row(1.0, rr=2.0), _row(-1.0, rr=3.0, direction="bearish"),
              _row(-1.0, rr=None, horizon="4w"), _row(0.5, rr=True)]
    disc = ea.stop_width_disclosures(_groups({"Q1": bucket}))["train"]["buckets"]["Q1"]
    assert (disc["n"], disc["win_rate"]) == (4, 50.0)
    assert disc["exp_r"] == pytest.approx(-0.125)
    assert disc["exp_r_gross"] == pytest.approx(-0.075)
    assert disc["median_rr"] == 2.5                           # None and the bool skipped
    assert disc["direction_share"] == {"bearish": 0.25, "bullish": 0.75}
    assert disc["horizon_share"] == {"2w": 0.75, "4w": 0.25}


def test_delta_within_a_direction_needs_100_bucket_rows_of_it():
    q1 = [_row(-1.0) for _ in range(100)] + [_row(-1.0, direction="bearish") for _ in range(99)]
    q2 = [_row(0.0) for _ in range(50)] + [_row(0.5, direction="bearish") for _ in range(50)]
    out = ea.stop_width_disclosures(_groups({"Q1": q1, "Q2": q2}))["train"]["buckets"]
    assert out["Q1"]["delta_by_direction"] == {"bullish": -1.0, "bearish": None}
    assert out["Q2"]["delta_by_direction"] == {"bullish": None, "bearish": None}


def test_delta_within_a_direction_needs_rest_rows_of_it():
    q1 = [_row(-1.0) for _ in range(100)]
    q2 = [_row(0.5, direction="bearish") for _ in range(10)]
    out = ea.stop_width_disclosures(_groups({"Q1": q1, "Q2": q2}))["train"]["buckets"]
    assert out["Q1"]["delta_by_direction"]["bullish"] is None


def test_clamped_share_leaves_none_rows_out_of_the_denominator():
    bucket = [_row(clamped=True), _row(clamped=True), _row(clamped=False),
              _row(clamped=None), _row(clamped=None)]
    unflagged = [_row(clamped=None), _row(clamped=None)]
    out = ea.stop_width_disclosures(_groups({"Q1": bucket, "Q2": unflagged}))["train"]["buckets"]
    assert out["Q1"]["clamped_share"] == pytest.approx(2 / 3) and out["Q1"]["clamped_none"] == 2
    assert out["Q2"]["clamped_share"] is None and out["Q2"]["clamped_none"] == 2


def test_removal_arithmetic_matches_the_rest_and_the_bucket_sum():
    q1 = [_row(-1.0), _row(-1.0), _row(0.5)]
    q2 = [_row(1.0), _row(0.5)]
    out = ea.stop_width_disclosures(_groups({"Q1": q1, "Q2": q2}))["train"]["buckets"]
    first = out["Q1"]["removal"]
    assert list(first) == ["pooled_exp_r", "without_exp_r", "delta_total_r", "n_removed"]
    assert first["pooled_exp_r"] == pytest.approx(0.0)
    assert first["without_exp_r"] == pytest.approx(0.75)      # = rest ExpR (Q2)
    assert first["delta_total_r"] == pytest.approx(1.5)       # -(-1 - 1 + 0.5)
    assert first["n_removed"] == 3
    second = out["Q2"]["removal"]
    assert second["without_exp_r"] == pytest.approx(-0.5)
    assert second["delta_total_r"] == pytest.approx(-1.5)
    total = sum(row["r"] for row in q1 + q2)
    assert total + first["delta_total_r"] == pytest.approx(sum(row["r"] for row in q2))


def test_an_empty_live_bucket_discloses_nothing_but_counts():
    groups = _groups({"Q1": [_row(-1.0)], "Q2": [_row(1.0)]},
                     {"Q1": [], "Q2": [_row(0.3, strategy="FVG")]})
    empty = ea.stop_width_disclosures(groups)["live"]["buckets"]["Q1"]
    assert (empty["n"], empty["exp_r"], empty["median_rr"]) == (0, None, None)
    assert empty["direction_share"] == {} and empty["family_share"] == {}
    assert (empty["clamped_share"], empty["clamped_none"]) == (None, 0)
    assert empty["same_day_loss_share"] is None
    assert empty["removal"] == {"pooled_exp_r": pytest.approx(0.3), "without_exp_r": pytest.approx(0.3),
                                "delta_total_r": 0.0, "n_removed": 0}


def test_live_family_and_same_day_loss_shares():
    live_q1 = [
        _row(-1.0, strategy="Fib 61.8%", opened_at="2026-11-03T14:31:00+00:00",
             closed_at="2026-11-03T19:02:00+00:00"),
        _row(-0.4, strategy="FVG", opened_at="2026-11-04T14:31:00+00:00",
             closed_at="2026-11-04T15:10:00+00:00"),
        _row(-1.0, strategy="FVG", opened_at="2026-11-04T14:31:00+00:00",
             closed_at="2026-11-06T15:10:00+00:00"),
        _row(-0.2, strategy=None, opened_at="2026-11-05T14:31:00+00:00", closed_at=None),
        _row(2.0, strategy="FVG", opened_at="2026-11-05T14:31:00+00:00",
             closed_at="2026-11-05T20:00:00+00:00"),                 # a same-day win: not a loss
    ]
    groups = _groups({"Q1": [_row(-1.0)]}, {"Q1": live_q1})
    out = ea.stop_width_disclosures(groups)
    live = out["live"]["buckets"]["Q1"]
    assert live["same_day_loss_share"] == pytest.approx(2 / 4)
    assert live["family_share"] == {"FVG": 0.6, "Fib 61.8%": 0.2, "unknown": 0.2}
    assert "same_day_loss_share" not in out["train"]["buckets"]["Q1"]
    assert "family_share" not in out["train"]["buckets"]["Q1"]


def test_a_live_bucket_without_losses_has_no_same_day_share():
    groups = _groups({"Q1": [_row(-1.0)]}, {"Q1": [_row(1.0, opened_at="2026-11-03",
                                                       closed_at="2026-11-03")]})
    assert ea.stop_width_disclosures(groups)["live"]["buckets"]["Q1"]["same_day_loss_share"] is None


def test_rho_and_overlap_of_mirrored_stop_atr_and_atr_pct():
    """atr_pct = 2 / stop_atr: perfectly inverse, so rho is -1 and every row
    lands in the mirrored quartile."""
    train = [_row(stop_atr=float(v), atr_pct=2.0 / v) for v in range(1, 9)]
    train += [_row(stop_atr=9.0, atr_pct=None)]               # no atr_pct: out of rho and overlap
    live = [_row(stop_atr=1.0, atr_pct=2.0), _row(stop_atr=8.0, atr_pct=0.25)]
    out = ea.stop_width_disclosures(ea.stop_width_groups(train, live))
    assert out["train"]["rho"] == pytest.approx(-1.0)
    assert out["train"]["overlap"] == pytest.approx(1.0)
    assert out["live"]["rho"] is None                         # under 3 points
    assert out["live"]["overlap"] == pytest.approx(1.0)       # on the TRAIN atr_pct edges


def test_no_atr_pct_gives_no_rho_and_no_overlap():
    out = ea.stop_width_disclosures(_groups({"Q1": [_row(-1.0)], "Q2": [_row(1.0)]}))
    assert (out["train"]["rho"], out["train"]["overlap"]) == (None, None)
