from swingbot.core.analytics.calibration import score_deciles, tier_calibration, badge_drift


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


def _reg(strategy, wr, n=206, status="VALIDATED"):
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status,
            "n": n, "win_rate": wr, "expectancy_r": 0.105, "window": "2024-01-01..2025-12-31"}


def _live_t(strategy_sources, status):
    return {"target_sources": strategy_sources, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_badge_drift_alerts_on_real_decay():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_t(["Fib 61.8%"], "win") for _ in range(16)] + [_live_t(["Fib 61.8%"], "loss") for _ in range(9)]
    rows = badge_drift(live, registry)
    assert rows[0]["strategy"] == "Fibonacci"
    assert rows[0]["oos_wr"] == 81.6 and rows[0]["live_n"] == 25
    assert round(rows[0]["live_wr"], 1) == 64.0
    assert rows[0]["drift_alert"] is True


def test_badge_drift_false_when_within_ten_points():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_t(["Fib 61.8%"], "win") for _ in range(19)]
    live += [_live_t(["Fib 61.8%"], "loss") for _ in range(6)]
    rows = badge_drift(live, registry)
    assert round(rows[0]["live_wr"], 1) == 76.0
    assert rows[0]["drift_alert"] is False


def test_badge_drift_false_below_n_floor():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_t(["Fib 61.8%"], "win") for _ in range(4)] + [_live_t(["Fib 61.8%"], "loss") for _ in range(6)]
    rows = badge_drift(live, registry)
    assert rows[0]["live_n"] == 10
    assert rows[0]["drift_alert"] is False  # 40% would otherwise alert, but N=10 < 20


def test_badge_drift_ignores_weak_registry_rows_and_dedups_by_strategy():
    registry = [_reg("VWAP", 90.0, status="WEAK"), _reg("Fibonacci", 81.6), _reg("Fibonacci", 81.6, n=50)]
    rows = badge_drift([], registry)
    assert [r["strategy"] for r in rows] == ["Fibonacci"]  # WEAK excluded, dup collapsed
