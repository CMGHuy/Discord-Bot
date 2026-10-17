"""v147 V147-15: build_report -- cells, rows, the frozen verdict of record, the v150 shape."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from swingbot.core.analytics import gate_counterfactual_inputs as gci
from swingbot.core.analytics import gate_counterfactual_report as gcr
from swingbot.core.backtesting.blocked_recorder import gate_row
from swingbot.core.infra import gate_counterfactual_store as store
from swingbot.core.market.strategy_types import COMPRESSION_SHORT

CELL_KEYS = {"gate", "population", "verdict", "n", "verdict_of_record", "latest", "in_sample", "note"}
ROW_KEYS = {"gate", "reason", "population", "blocked_n", "no_plan_n", "fill_rate", "blocked_exp_r",
            "blocked_win_rate", "taken_exp_r", "taken_win_rate", "near_miss_n", "near_miss_exp_r",
            "rest_n", "rest_exp_r", "dollar_risk", "over_cap", "in_sample"}


@pytest.fixture(autouse=True)
def _fast_bootstrap(monkeypatch):
    monkeypatch.setattr(gcr, "BOOTSTRAP_RESAMPLES", 300)


def _row(arm="blocked", *, i=0, gate="rs", reason="rs_blocked", r=0.5, status="filled", population="live",
         source="strategy", direction="bearish", strategy="Fibonacci", margin=None, loss=None, start="2026-10-05"):
    day = (dt.date.fromisoformat(start) + dt.timedelta(weeks=i)).isoformat()
    filled = status == "filled"
    return gate_row(population=population, arm=arm, source=source, ticker=f"T{i}", strategy=strategy,
                    horizon="2w", direction=direction, signal_date=day, gate=gate,
                    reason=reason if arm == "blocked" else None, margin=margin, cf_status=status,
                    cf_r=r if filled else None, win=(r > 0) if filled else None,
                    planned_loss_pct=loss, expiry_bars=5, in_sample=gate == "compression" and population == "train")


def _arm(arm, rs, **kw):
    return [_row(arm, i=i, r=r, **kw) for i, r in enumerate(rs)]


def _cell(result, gate, population):
    (cell,) = [c for c in result["cells"] if (c["gate"], c["population"]) == (gate, population)]
    return cell


def _build(rows, **kw):
    return gcr.build_report(train_rows=[r for r in rows if r["population"] == "train"],
                            live_blocked=[r for r in rows if r["population"] == "live" and r["arm"] == "blocked"],
                            live_taken=[r for r in rows if r["population"] == "live" and r["arm"] == "taken"],
                            write=False, **kw)


def test_the_report_has_v150s_shape_and_is_json_serialisable():
    result = _build(_arm("blocked", [0.5, -1.0]) + _arm("taken", [1.0]))
    assert {"generated_at", "live_window", "cells", "rows"} <= set(result)
    assert all(CELL_KEYS <= set(cell) for cell in result["cells"])
    assert all(ROW_KEYS <= set(row) for row in result["rows"])
    json.dumps(result)


def test_five_verdict_cells_then_three_note_cells():
    result = _build([])
    assert [(c["gate"], c["population"]) for c in result["cells"]] == [
        ("rs", "live"), ("risk_cap", "live"), ("compression", "live"), ("risk_cap", "train"),
        ("compression", "train"), ("rs", "train"), ("no_qualifying_target", "live"),
        ("no_qualifying_target", "train")]
    notes = {(c["gate"], c["population"]): c["note"] for c in result["cells"][5:]}
    assert notes == {("rs", "train"): "no TRAIN population",
                     ("no_qualifying_target", "live"): "no verdict — no-plan",
                     ("no_qualifying_target", "train"): "no verdict — no-plan"}
    assert result["bh_family"] == 5 and result["seed"] == 42


def test_waiting_below_thirty_distinct_filled_blocked_setups():
    cell = _cell(_build(_arm("blocked", [-1.0] * 29) + _arm("taken", [1.0] * 40)), "rs", "live")
    assert (cell["verdict"], cell["n"], cell["latest"], cell["verdict_of_record"], cell["note"]) == \
        ("WAITING", 29, None, None, None)


def test_a_reading_at_the_floor_seeds_the_verdict_of_record():
    result = _build(_arm("blocked", [-1.0, -0.5] * 20) + _arm("taken", [1.0, 0.5] * 20), today="2026-12-04")
    cell = _cell(result, "rs", "live")
    assert cell["verdict"] == "GATE EARNS" and cell["n"] == 40 and cell["taken_n"] == 40
    assert cell["verdict_of_record"] == {"verdict": "GATE EARNS", "date": "2026-12-04", "n": 40}
    assert cell["latest"]["ci_high"] < 0 and cell["latest"]["q"] < 0.10


def test_the_first_reading_stays_the_verdict_of_record(tmp_path):
    path = tmp_path / "reports" / "gate-counterfactual.json"
    first = _arm("blocked", [-1.0, -0.5] * 20) + _arm("taken", [1.0, 0.5] * 20)
    gcr.build_report(train_rows=[], live_blocked=first[:40], live_taken=first[40:], today="2026-12-04",
                     path=path)
    later = _arm("blocked", [1.0, -1.0] * 30) + _arm("taken", [-1.0, 1.0] * 30)
    result = gcr.build_report(train_rows=[], live_blocked=later[:60], live_taken=later[60:],
                              today="2027-01-08", path=path)
    cell = _cell(result, "rs", "live")
    assert (cell["verdict"], cell["n"]) == ("INCONCLUSIVE", 60)
    assert cell["verdict_of_record"] == {"verdict": "GATE EARNS", "date": "2026-12-04", "n": 40}


def test_build_report_writes_the_file_load_report_reads_back_unchanged(tmp_path):
    path = tmp_path / "reports" / "gate-counterfactual.json"
    assert gcr.load_report(path) is None
    assert gcr.load_report is store.load_report                 # one loader, re-exported for v150
    rows = _arm("blocked", [0.5, -1.0]) + _arm("taken", [1.0])
    result = gcr.build_report(train_rows=[], live_blocked=rows[:2], live_taken=rows[2:], path=path)
    assert gcr.load_report(path) == result
    json.dumps(gcr.load_report(path))


def test_an_empty_taken_arm_gets_a_note_and_no_verdict():
    blocked = _arm("blocked", [1.0, -1.0, 0.5] * 14, gate="compression", reason="earnings_unknown",
                   population="train", strategy=COMPRESSION_SHORT)
    cell = _cell(_build(blocked), "compression", "train")
    assert cell["n"] == 42 and cell["taken_n"] == 0
    assert cell["note"] == "no TRAIN taken arm — no as-of earnings archive"
    assert (cell["verdict"], cell["latest"], cell["verdict_of_record"], cell["in_sample"]) == \
        ("WAITING", None, None, True)


def test_a_below_floor_taken_arm_gets_a_note_and_no_verdict():
    blocked = _arm("blocked", [-1.0] * 40, gate="plan_rejected", reason="risk_cap", population="train",
                   source="confluence", loss=2.5, margin=0.5)
    taken = _arm("taken", [1.0] * 10, gate="plan_rejected", population="train", source="confluence")
    cell = _cell(_build(blocked + taken), "risk_cap", "train")
    assert cell["note"] == "taken arm below the floor (10 distinct filled setups < 30)"
    assert (cell["verdict"], cell["latest"], cell["verdict_of_record"]) == ("WAITING", None, None)


def test_a_note_cell_enters_bh_as_p_one(monkeypatch):
    seen = {}
    real = gcr.family_qvalues

    def spy(pvalues):
        seen["p"] = list(pvalues)
        return real(pvalues)

    monkeypatch.setattr(gcr, "family_qvalues", spy)
    blocked = _arm("blocked", [1.0] * 40, gate="compression", reason="earnings_unknown",
                   population="train", strategy=COMPRESSION_SHORT)
    _build(blocked)
    assert seen["p"] == [None] * 5


def test_the_taken_arm_is_scoped_by_source_family_and_direction():
    blocked = _arm("blocked", [-1.0] * 3)                                  # rs, strategy, bearish
    taken = (_arm("taken", [1.0] * 2) + _arm("taken", [1.0], direction="bullish")
             + _arm("taken", [1.0], source="confluence"))
    (row,) = [r for r in _build(blocked + taken)["rows"] if r["gate"] == "rs"]
    assert row["taken_n"] == 2


def test_short_lane_blocks_are_scoped_against_confluence_taken_plans():
    blocked = _arm("blocked", [-1.0] * 2, gate="plan_rejected", reason="risk_cap", source="short_lane",
                   loss=2.4, margin=0.4)
    taken = _arm("taken", [1.0] * 3, gate="plan_rejected", source="confluence")
    (row,) = [r for r in _build(blocked + taken)["rows"] if r["gate"] == "risk_cap"]
    assert row["taken_n"] == 3


def test_the_compression_taken_arm_is_compression_short_only():
    blocked = _arm("blocked", [-1.0] * 2, gate="compression", reason="no_mode", strategy=COMPRESSION_SHORT)
    taken = (_arm("taken", [1.0] * 2, gate="compression", strategy=COMPRESSION_SHORT)
             + _arm("taken", [1.0] * 5, gate="compression", strategy="RSI"))
    (row,) = [r for r in _build(blocked + taken)["rows"] if r["gate"] == "compression"]
    assert row["taken_n"] == 2


def test_risk_cap_rows_are_over_cap_with_a_dollar_risk_column_and_a_near_miss_split():
    blocked = [_row(i=0, gate="plan_rejected", reason="risk_cap", source="confluence", r=-1.0, loss=2.4, margin=0.4),
               _row(i=1, gate="plan_rejected", reason="risk_cap", source="confluence", r=1.0, loss=3.0, margin=1.0),
               _row(i=2, gate="plan_rejected", reason="risk_cap", source="confluence", status="no-fill",
                    loss=2.2, margin=0.2)]
    (row,) = [r for r in _build(blocked)["rows"] if r["gate"] == "risk_cap"]
    assert row["over_cap"] is True and row["reason"] == "risk_cap"
    assert row["dollar_risk"] == pytest.approx((-1.0 * 2.4 / 2.0 + 1.0 * 3.0 / 2.0) / 2)
    assert (row["near_miss_n"], row["near_miss_exp_r"], row["rest_n"], row["rest_exp_r"]) == \
        (2, pytest.approx(-1.0), 1, pytest.approx(1.0))
    assert row["fill_rate"] == pytest.approx(2 / 3) and row["blocked_n"] == 3


def test_compression_rows_are_unsplit_one_per_reason_and_in_sample_on_train():
    blocked = (_arm("blocked", [1.0] * 2, gate="compression", reason="earnings_unknown",
                    population="train", strategy=COMPRESSION_SHORT)
               + [_row(i=9, gate="compression", reason="mode_not_allowed", population="train",
                       strategy=COMPRESSION_SHORT)])
    rows = [r for r in _build(blocked)["rows"] if r["gate"] == "compression"]
    assert [r["reason"] for r in rows] == ["earnings_unknown", "mode_not_allowed"]
    assert all(r["in_sample"] and r["near_miss_n"] is None and r["rest_exp_r"] is None for r in rows)
    assert all(r["over_cap"] is False and r["dollar_risk"] is None for r in rows)


def test_no_qualifying_target_rows_are_no_plan_counts_without_an_exp_r():
    blocked = _arm("blocked", [0.0] * 3, gate="plan_rejected", reason="no_qualifying_target",
                   source="confluence", status="no-plan")
    (row,) = [r for r in _build(blocked)["rows"] if r["gate"] == "no_qualifying_target"]
    assert (row["blocked_n"], row["no_plan_n"], row["blocked_exp_r"], row["fill_rate"]) == (3, 3, None, None)
    assert _cell(_build(blocked), "no_qualifying_target", "live")["note"] == "no verdict — no-plan"


def test_live_and_train_are_never_pooled():
    live = _arm("blocked", [1.0] * 3, gate="plan_rejected", reason="risk_cap", source="confluence", loss=2.5)
    train = _arm("blocked", [-1.0] * 5, gate="plan_rejected", reason="risk_cap", source="confluence",
                 loss=2.5, population="train")
    rows = {r["population"]: r for r in _build(live + train)["rows"] if r["gate"] == "risk_cap"}
    assert (rows["live"]["blocked_n"], rows["live"]["blocked_exp_r"]) == (3, pytest.approx(1.0))
    assert (rows["train"]["blocked_n"], rows["train"]["blocked_exp_r"]) == (5, pytest.approx(-1.0))


def test_realised_r_rides_beside_the_rewalk_and_is_never_the_taken_exp_r():
    taken = _arm("taken", [1.0, 1.0])
    for row, realised in zip(taken, (0.2, None)):
        row["realised_r"] = realised
    (row,) = [r for r in _build(_arm("blocked", [-1.0]) + taken)["rows"] if r["gate"] == "rs"]
    assert row["taken_exp_r"] == pytest.approx(1.0) and row["taken_realised_exp_r"] == pytest.approx(0.2)


def test_the_live_window_is_recorded_as_seen():
    assert _build([])["live_window"] is None
    train = _row(i=50, gate="plan_rejected", reason="risk_cap", source="confluence", population="train")
    result = _build(_arm("blocked", [1.0] * 3) + [train])
    assert result["live_window"] == "2026-10-05..2026-10-19"


def test_the_limitations_state_the_gap_floor_and_the_portfolio_state():
    text = " ".join(_build([])["limitations"])
    assert "-1.0R" in text and "understated" in text
    assert "heat" in text and "holdout" in text and "in-sample" in text


def test_defaults_load_the_train_files_and_the_live_table(monkeypatch):
    calls = []
    monkeypatch.setattr(gci, "default_train_paths", lambda: ["a.jsonl"])
    monkeypatch.setattr(gci, "load_train_rows", lambda paths: calls.append(("train", paths)) or [])
    monkeypatch.setattr(gci, "load_live", lambda **kw: calls.append(("live",)) or ([], []))
    gcr.build_report(write=False)
    assert calls == [("train", ["a.jsonl"]), ("live",)]
