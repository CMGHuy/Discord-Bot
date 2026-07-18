from swingbot.core.analytics.calibration import score_deciles, tier_calibration


def _t(score, status, entry=100.0, stop_loss=95.0, exit_price=None):
    return {"quality_score": score, "status": status, "direction": "bullish",
            "entry": entry, "stop_loss": stop_loss,
            "exit_price": exit_price if exit_price is not None else (104.0 if status == "win" else 96.0)}


def test_score_deciles_groups_by_ten_and_omits_empty():
    closed = [_t(5, "loss"), _t(55, "win"), _t(57, "win"), _t(95, "win")]
    rows = score_deciles(closed)
    by_decile = {r["decile"]: r for r in rows}
    assert set(by_decile) == {"0-9", "50-59", "90-100"}
    assert by_decile["50-59"]["n"] == 2
    assert by_decile["50-59"]["win_rate"] == 100.0
    assert by_decile["0-9"]["win_rate"] == 0.0


def test_score_deciles_skips_missing_score():
    closed = [_t(None, "win"), _t(50, "win")]
    rows = score_deciles(closed)
    assert len(rows) == 1 and rows[0]["n"] == 1


def test_score_deciles_sorted_ascending():
    closed = [_t(95, "win"), _t(5, "loss")]
    rows = score_deciles(closed)
    assert [r["decile"] for r in rows] == ["0-9", "90-100"]


def _tier_t(tier, status):
    return {"tier": tier, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_tier_calibration_ok_true_and_none():
    closed = [_tier_t("A", "win") for _ in range(10)] + [_tier_t("A", "loss") for _ in range(2)]
    closed += [_tier_t("B", "win"), _tier_t("B", "loss"), _tier_t("B", "win")]
    rows = tier_calibration(closed)
    by_tier = {r["tier"]: r for r in rows}
    assert by_tier["A"]["n"] == 12
    assert round(by_tier["A"]["win_rate"], 1) == 83.3
    assert by_tier["A"]["expected_band"] == ">=80"
    assert by_tier["A"]["ok"] is True
    assert by_tier["B"]["n"] == 3 and by_tier["B"]["ok"] is None  # below the N=10 floor
    assert by_tier["C"]["n"] == 0 and by_tier["C"]["ok"] is None  # no data at all


def test_tier_calibration_ok_false_when_band_missed():
    closed = [_tier_t("C", "win") for _ in range(3)] + [_tier_t("C", "loss") for _ in range(9)]
    row = tier_calibration(closed)[2]
    assert row["tier"] == "C" and row["n"] == 12
    assert round(row["win_rate"], 1) == 25.0
    assert row["ok"] is True  # 25% IS < 70 -- band met


def test_tier_calibration_row_order_is_a_b_c():
    rows = tier_calibration([])
    assert [r["tier"] for r in rows] == ["A", "B", "C"]
