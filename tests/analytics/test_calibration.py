from swingbot.core.analytics.calibration import score_deciles, level_calibration, badge_drift


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


def _level_t(level, status):
    return {"confidence_level": level, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_level_calibration_reports_n_and_win_rate():
    closed = [_level_t(5, "win") for _ in range(10)] + [_level_t(5, "loss") for _ in range(2)]
    closed += [_level_t(3, "win"), _level_t(3, "loss"), _level_t(3, "win")]
    rows = level_calibration(closed)
    by_level = {r["level"]: r for r in rows}
    assert by_level[5]["n"] == 12
    assert round(by_level[5]["win_rate"], 1) == 83.3
    assert by_level[3]["n"] == 3
    assert round(by_level[3]["win_rate"], 1) == 66.7
    assert by_level[1]["n"] == 0   # no data at all


def test_level_calibration_row_order_is_one_through_five():
    rows = level_calibration([])
    assert [r["level"] for r in rows] == [1, 2, 3, 4, 5]
    assert all(r["n"] == 0 for r in rows)


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


def _live_direct_t(strategy, status):
    return {"strategy": strategy, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_badge_drift_matches_direct_strategy_field():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_direct_t("Fibonacci", "win") for _ in range(16)]
    live += [_live_direct_t("Fibonacci", "loss") for _ in range(9)]
    rows = badge_drift(live, registry)
    assert rows[0]["live_n"] == 25
    assert round(rows[0]["live_wr"], 1) == 64.0
    assert rows[0]["drift_alert"] is True
