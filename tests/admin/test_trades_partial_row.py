"""API plan rows preserve the projection's provenance."""
import swingbot.admin.app  # initializes API routes before importing one endpoint

from swingbot.admin.api_v1.trades import _row_from_plan


def partial_plan(**kw):
    base = {"plan_id": "p1", "ticker": "AAPL", "status": "PARTIAL",
            "direction": "bullish", "strategy": "MACD", "horizon_key": "3m",
            "entry_price": 100.0, "trigger_price": 100.0, "stop_loss": 90.0,
            "tp1": 120.0, "tp2": None, "working_stop": 113.3333333,
            "legs_realized": [{"fraction": 0.5, "exit_price": 121.0, "r": 2.1}],
            "tp1_fraction": 0.5, "expiry_bars": 5, "created_at": "2026-09-01",
            "badge": "WEAK", "quality_score": 3}
    base.update(kw)
    return base


def test_no_tp2_runner_ships_null_target_flag_and_trailing_kind():
    row = _row_from_plan(partial_plan(), None, set())
    assert (row["target"], row["target_is_banked_tp1"], row["bar_kind"]) == (None, True, "trailing")


def test_no_tp2_runner_ships_r_readouts():
    assert round(_row_from_plan(partial_plan(), None, set())["floor_r"], 4) == 1.3333


def test_missing_working_stop_uses_runner_floor():
    row = _row_from_plan(partial_plan(working_stop=None), None, set())
    assert round(row["stop_loss"], 4) == 113.3333
    assert row["stop_kind"] == "derived_floor"


def test_tp2_runner_keeps_target_and_progress_bar():
    row = _row_from_plan(partial_plan(tp2=140.0), None, set())
    assert (row["target"], row["target_is_banked_tp1"], row["bar_kind"]) == (140.0, False, "none")


def test_banked_leg_fields_survive_projection():
    row = _row_from_plan(partial_plan(), None, set())
    assert (row["banked_fraction"], row["banked_exit_price"], row["banked_r"]) == (0.5, 121.0, 2.1)


def test_pending_row_carries_no_banked_target():
    row = _row_from_plan(partial_plan(status="PENDING", entry_price=None,
                                      working_stop=None, legs_realized=[]), None, set())
    assert row["bar_kind"] in ("approach", "none")
    assert row["target_is_banked_tp1"] is False
