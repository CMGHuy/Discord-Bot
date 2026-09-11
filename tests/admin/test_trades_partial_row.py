"""API plan rows preserve the projection's provenance."""
import swingbot.admin.app  # initializes API routes before importing one endpoint

from swingbot.admin.api_v1.trades import _row_from_plan, _expand_plan_row


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


# --- v79: one row per realized leg ---------------------------------------

def closed_scaled_out_plan(**kw):
    base = partial_plan(status="CLOSED", **kw)
    base["legs_realized"] = [
        {"fraction": 0.5, "exit_price": 121.0, "r": 2.1, "reason": "tp1",
         "closed_at": "2026-09-02T14:00:00+00:00"},
        {"fraction": 0.5, "exit_price": 130.0, "r": 3.0, "reason": "tp1_runner_tp2",
         "closed_at": "2026-09-05T15:00:00+00:00"},
    ]
    return base


def test_a_plan_with_no_realized_legs_expands_to_its_one_existing_row():
    plan = partial_plan(status="ACTIVE", legs_realized=[])
    rows = _expand_plan_row(plan, None, set())
    assert len(rows) == 1
    assert rows[0]["leg_index"] == 0 and rows[0]["leg_total"] == 1


def test_a_partial_plan_expands_to_a_closed_leg_and_an_open_remainder():
    plan = partial_plan()  # status PARTIAL, one realized leg per the fixture
    trade = {"id": "t1", "shares": 10, "status": "open"}
    rows = _expand_plan_row(plan, trade, set())
    assert len(rows) == 2
    assert rows[0]["status"] == "CLOSED" and rows[0]["outcome"] == "win"
    assert rows[0]["shares"] == 5.0
    assert rows[0]["exit_price"] == 121.0
    assert rows[1]["status"] == "PARTIAL"
    assert rows[1]["leg_index"] == 1 and rows[1]["leg_total"] == 2


def test_a_fully_closed_scaled_out_plan_expands_to_two_closed_rows():
    plan = closed_scaled_out_plan()
    trade = {"id": "t1", "shares": 10, "status": "win"}
    rows = _expand_plan_row(plan, trade, set())
    assert len(rows) == 2
    assert [r["status"] for r in rows] == ["CLOSED", "CLOSED"]
    assert [r["shares"] for r in rows] == [5.0, 5.0]
    assert [r["exit_price"] for r in rows] == [121.0, 130.0]
    assert rows[0]["closed_at"] == "2026-09-02T14:00:00+00:00"
    assert rows[1]["closed_at"] == "2026-09-05T15:00:00+00:00"


def test_a_negative_r_leg_is_a_loss_not_a_win():
    plan = closed_scaled_out_plan()
    plan["legs_realized"][1]["r"] = -0.4
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[1]["outcome"] == "loss"


def test_a_leg_with_no_stamped_closed_at_falls_back_to_status_history():
    plan = closed_scaled_out_plan()
    del plan["legs_realized"][0]["closed_at"]
    plan["status_history"] = [
        {"status": "ACTIVE", "reason": "market_entry", "at": "2026-09-01T09:00:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1_partial", "at": "2026-09-02T14:00:00+00:00"},
        {"status": "CLOSED", "reason": "tp1_runner_tp2", "at": "2026-09-05T15:00:00+00:00"},
    ]
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[0]["closed_at"] == "2026-09-02T14:00:00+00:00"


# --- fix round: r_multiple, outcome-with-missing-r, held_hours -----------

def test_a_leg_rows_r_multiple_is_the_legs_own_r_not_a_recomputation():
    """dash.closed_r needs a stop_loss the synthetic leg_trade dict never
    carried, so recomputing through it silently returned None for every
    scaled-out leg. The leg's own `r` is the source of truth."""
    plan = closed_scaled_out_plan()
    trade = {"id": "t1", "shares": 10, "status": "win", "opened_at": "2026-09-01T09:00:00+00:00"}
    rows = _expand_plan_row(plan, trade, set())
    assert rows[0]["r_multiple"] == 2.1
    assert rows[1]["r_multiple"] == 3.0


def test_a_leg_with_no_r_falls_back_to_price_sign_not_a_default_win():
    """A leg appended with no `r` key (the stop-out mirror path) must not
    read as a win just because `leg.get("r") or 0` folds a missing r to 0."""
    plan = closed_scaled_out_plan()
    del plan["legs_realized"][1]["r"]
    # entry_price is 100.0 (partial_plan fixture), direction bullish --
    # an exit below entry is a real loss, not a win-by-default.
    plan["legs_realized"][1]["exit_price"] = 95.0
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[1]["outcome"] == "loss"
    assert rows[1]["r_multiple"] is None


def test_a_leg_with_neither_closed_at_nor_a_history_entry_uses_the_trades_close():
    """Last resort for a leg's close time must be when the position actually
    reached its terminal state (`_terminal_at`), never the plan's CREATION
    time -- `created_at` predates every fill, so a row stamped with it is
    scored against the wrong day and silently drops out of the Dashboard's
    Today/CLOSED scope."""
    plan = closed_scaled_out_plan()
    del plan["legs_realized"][0]["closed_at"]
    plan["status_history"] = []  # nothing to match positionally
    trade = {"id": "t1", "shares": 10, "status": "win",
             "opened_at": "2026-09-01T09:00:00+00:00",
             "closed_at": "2026-09-05T15:00:00+00:00"}
    rows = _expand_plan_row(plan, trade, set())
    assert rows[0]["closed_at"] == "2026-09-05T15:00:00+00:00"
    assert rows[0]["closed_at"] != plan["created_at"]


def test_a_leg_falls_all_the_way_back_to_created_at_only_when_nothing_else_exists():
    """With no leg stamp, no history and no trade close, `created_at` is
    still the only date the row has."""
    plan = closed_scaled_out_plan()
    del plan["legs_realized"][0]["closed_at"]
    plan["status_history"] = []
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[0]["closed_at"] == "2026-09-01"


def test_a_leg_rows_held_hours_is_its_own_span_not_the_whole_positions():
    """held_hours must be measured against the LEG's own closed_at, not
    inherited from the trade's overall opened_at -> closed_at span -- and
    must not keep growing against wall-clock `now` for an already-closed
    leg on a still-open PARTIAL plan."""
    plan = closed_scaled_out_plan()
    trade = {"id": "t1", "shares": 10, "status": "win", "opened_at": "2026-09-01T09:00:00+00:00"}
    rows = _expand_plan_row(plan, trade, set())
    # leg 0 closed 2026-09-02T14:00 -- 29 hours after open
    assert rows[0]["held_hours"] == 29.0
    # leg 1 closed 2026-09-05T15:00 -- 102 hours after open
    assert rows[1]["held_hours"] == 102.0
