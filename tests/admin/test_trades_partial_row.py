"""API plan rows preserve the projection's provenance."""
import swingbot.admin.app  # initializes API routes before importing one endpoint

from swingbot.admin.api_v1.trades import _expand_plan_row, _row_from_plan, _row_from_trade


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


def test_the_banked_tp1_leg_shows_tp1_and_the_runner_row_keeps_tp2():
    plan = partial_plan(tp2=140.0)
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "open"}, set())
    assert (rows[0]["target"], rows[0]["target_is_banked_tp1"]) == (120.0, False)
    assert rows[1]["target"] == 140.0
    assert [r["target1"] for r in rows] == [120.0, 120.0]
    assert [r["target2"] for r in rows] == [140.0, 140.0]


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


def test_a_closed_runner_leg_shows_tp2_not_the_closed_plans_tp1():
    plan = closed_scaled_out_plan(tp2=140.0)
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert [r["target"] for r in rows] == [120.0, 140.0]


def test_a_closed_runner_leg_without_tp2_has_no_target():
    rows = _expand_plan_row(closed_scaled_out_plan(), {"id": "t1", "shares": 10, "status": "win"}, set())
    assert [r["target"] for r in rows] == [120.0, None]


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


def test_risk_stop_is_the_plan_stop_while_stop_loss_is_the_working_stop():
    """v166: the row publishes the original stop beside the working one."""
    row = _row_from_plan(partial_plan(), None, set())
    assert row["risk_stop"] == 90.0
    assert round(row["stop_loss"], 4) == 113.3333
    assert "_risk_stop" not in row


# --- v177: the Plan cell's runner fields ----------------------------------

RUNNER_CELL_KEYS = ("tp1", "best_pnl_pct", "stop_pnl_pct",
                    "runner_exit_price", "runner_exit_reason")


def rklb_runner(**kw):
    """The live RKLB short that motivated v177: TP1 banked, no TP2, the stop
    trailing down behind a best price of 49.94."""
    fields = {"ticker": "RKLB", "direction": "bearish", "entry_price": 60.67,
              "trigger_price": 60.67, "stop_loss": 61.85, "tp1": 58.33,
              "working_stop": 52.437, "runner_high_close": 49.94,
              "legs_realized": [{"fraction": 0.5, "exit_price": 58.33, "r": 1.98,
                                 "reason": "tp1",
                                 "closed_at": "2026-10-10T14:00:00+00:00"}]}
    fields.update(kw)
    return partial_plan(**fields)


def manually_closed_partial(**kw):
    """A PARTIAL plan closed from the admin UI: `_close_plan` records the
    CLOSED transition with reason "manual" and appends NO runner leg."""
    plan = partial_plan(status="CLOSED", **kw)
    plan["legs_realized"] = [
        {"fraction": 0.5, "exit_price": 121.0, "r": 2.1, "reason": "tp1",
         "closed_at": "2026-09-02T14:00:00+00:00"},
    ]
    plan["status_history"] = [
        {"status": "PARTIAL", "reason": "tp1", "at": "2026-09-02T14:00:00+00:00"},
        {"status": "CLOSED", "reason": "manual", "at": "2026-09-04T16:00:00+00:00"},
    ]
    return plan


def _cell(row):
    return {key: row[key] for key in RUNNER_CELL_KEYS}


def test_rklb_short_runner_carries_tp1_and_both_signed_percentages():
    row = _row_from_plan(rklb_runner(), None, set())
    assert row["tp1"] == 58.33
    assert row["best_pnl_pct"] == 17.69
    assert row["stop_pnl_pct"] == 13.57
    assert (row["runner_exit_price"], row["runner_exit_reason"]) == (None, None)
    # The view fields every other surface agrees on are untouched (v73).
    assert row["stop_loss"] == 52.437
    assert row["target"] is None
    assert row["risk_stop"] == 61.85


def test_long_runner_percentages_are_signed_the_other_way():
    row = _row_from_plan(partial_plan(runner_high_close=130.0), None, set())
    assert row["tp1"] == 120.0
    assert row["best_pnl_pct"] == 30.0
    assert row["stop_pnl_pct"] == 13.33


def test_a_runner_with_no_best_price_yet_measures_from_the_tp1_fill():
    row = _row_from_plan(partial_plan(), None, set())       # runner_high_close absent
    assert row["runner_best"] is None
    assert row["best_pnl_pct"] == 21.0                       # the 121.0 TP1 fill
    assert row["stop_pnl_pct"] == 13.33


def test_a_derived_floor_keeps_both_percentages_and_its_stop_kind():
    row = _row_from_plan(partial_plan(working_stop=None, runner_high_close=130.0), None, set())
    assert row["stop_kind"] == "derived_floor"
    assert row["tp1"] == 120.0
    assert row["stop_pnl_pct"] == 13.33
    assert row["best_pnl_pct"] == 30.0


def test_a_runner_with_a_tp2_gets_none_of_the_runner_cell_fields():
    row = _row_from_plan(partial_plan(tp2=140.0, runner_high_close=130.0), None, set())
    assert _cell(row) == dict.fromkeys(RUNNER_CELL_KEYS)


def test_an_active_plan_gets_none_of_the_runner_cell_fields():
    row = _row_from_plan(partial_plan(status="ACTIVE", legs_realized=[]), None, set())
    assert _cell(row) == dict.fromkeys(RUNNER_CELL_KEYS)


def test_the_tp1_leg_row_of_a_still_partial_plan_clears_the_line_two_fields():
    trade = {"id": "t1", "shares": 10, "status": "open"}
    leg_row, runner_row = _expand_plan_row(rklb_runner(), trade, set())
    assert leg_row["status"] == "CLOSED"
    assert leg_row["bar_kind"] == "trailing"                 # the Trades page's leg icon
    assert _cell(leg_row) == dict.fromkeys(RUNNER_CELL_KEYS)
    assert runner_row["status"] == "PARTIAL"
    assert (runner_row["tp1"], runner_row["best_pnl_pct"], runner_row["stop_pnl_pct"]) == (
        58.33, 17.69, 13.57)


def test_both_rows_of_a_closed_partial_trade_carry_the_runner_exit():
    trade = {"id": "t1", "shares": 10, "status": "win", "exit_price": 130.0}
    rows = _expand_plan_row(closed_scaled_out_plan(), trade, set())
    assert [(r["runner_exit_price"], r["runner_exit_reason"]) for r in rows] == [
        (130.0, "tp1_runner_tp2"), (130.0, "tp1_runner_tp2")]
    assert [r["exit_price"] for r in rows] == [121.0, 130.0]  # each leg keeps its own fill
    for r in rows:
        assert (r["tp1"], r["best_pnl_pct"], r["stop_pnl_pct"]) == (None, None, None)


def test_a_give_back_close_reports_giveback_not_the_trail_reason():
    plan = closed_scaled_out_plan()
    plan["legs_realized"][1].update({"exit_price": 126.0, "reason": "tp1_runner_trail",
                                     "stop_source": "giveback", "giveback_pct": 5.0})
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert [(r["runner_exit_price"], r["runner_exit_reason"]) for r in rows] == [
        (126.0, "giveback"), (126.0, "giveback")]


def test_a_floor_stop_close_passes_its_leg_reason_through():
    plan = closed_scaled_out_plan()
    plan["legs_realized"][1].update({"exit_price": 113.5, "reason": "tp1_runner_be",
                                     "stop_source": "floor"})
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[1]["runner_exit_reason"] == "tp1_runner_be"


def test_an_active_stop_out_has_no_runner_exit():
    plan = partial_plan(status="CLOSED", legs_realized=[
        {"fraction": 1.0, "exit_price": 90.0, "r": -1.0, "reason": "loss"}])
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "loss"}, set())
    assert len(rows) == 1
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (None, None)


def test_a_manual_close_after_tp1_reads_the_trades_own_exit_price():
    trade = {"id": "t1", "shares": 10, "status": "win", "exit_price": 125.5}
    rows = _expand_plan_row(manually_closed_partial(), trade, set())
    assert len(rows) == 1                                     # no runner leg was written
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (125.5, "manual")
    assert rows[0]["exit_price"] == 121.0                     # the leg row keeps the TP1 fill


def test_a_manual_close_whose_price_fetch_failed_shows_no_runner_exit():
    trade = {"id": "t1", "shares": 10, "status": "closed", "exit_price": None}
    rows = _expand_plan_row(manually_closed_partial(), trade, set())
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (None, None)


def test_a_bulk_manual_close_reports_the_trades_exit_as_a_manual_runner_exit():
    plan = manually_closed_partial()
    plan["status_history"][-1]["reason"] = "manual_bulk"
    rows = _expand_plan_row(plan, {"exit_price": 130.0}, set())
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (130.0, "manual")


def test_a_legacy_tp1_leg_with_no_reason_still_reads_as_a_manual_close():
    plan = manually_closed_partial()
    del plan["legs_realized"][0]["reason"]
    rows = _expand_plan_row(plan, {"exit_price": 130.0}, set())
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (130.0, "manual")


def test_a_manual_close_with_no_linked_trade_shows_no_runner_exit():
    rows = _expand_plan_row(manually_closed_partial(), None, set())
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (None, None)


def test_a_legacy_trade_emits_every_runner_cell_key_as_none():
    trade = {"id": "L1", "ticker": "AAPL", "status": "win", "direction": "bullish",
             "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 110.0,
             "opened_at": "2026-09-01T09:00:00+00:00",
             "closed_at": "2026-09-03T15:00:00+00:00"}
    row = _row_from_trade(trade, set())
    assert _cell(row) == dict.fromkeys(RUNNER_CELL_KEYS)
