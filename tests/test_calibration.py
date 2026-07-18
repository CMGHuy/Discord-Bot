from swingbot.core.analytics.calibration import score_deciles


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
