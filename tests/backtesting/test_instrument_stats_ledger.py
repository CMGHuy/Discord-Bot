"""v136 §4: the pre-registration ledger, a git-tracked JSONL record."""
import json

import pytest

from swingbot.core.backtesting.instrument import stats


def _row(**over):
    row = {"id": "v999-demo", "date": "2026-10-06", "hypothesis": "Demo gate",
           "instrument": "v2", "n": 120, "exp_r": 0.12, "p": 0.03,
           "verdict": "FAIL", "record": "docs/superpowers/results/demo.md"}
    row.update(over)
    return row


def test_fields_and_vocabularies_are_the_plan_set():
    assert stats.LEDGER_FIELDS == ("id", "date", "hypothesis", "instrument", "n",
                                   "exp_r", "p", "verdict", "record")
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN", "SCREEN-PASS", "SCREEN-FAIL",
                              "SCREEN-UNDERPOWERED")
    assert stats.INSTRUMENTS == ("v1", "v2", "screen-v1")


def test_ledger_path_is_the_committed_results_file():
    assert stats.LEDGER_PATH.as_posix().endswith(
        "docs/superpowers/results/preregistration-ledger.jsonl")


def test_a_complete_row_validates():
    stats.validate_ledger_row(_row())


def test_null_n_exp_r_and_p_are_allowed():
    stats.validate_ledger_row(_row(n=None, exp_r=None, p=None))


def test_an_integer_p_of_one_is_allowed():
    stats.validate_ledger_row(_row(p=1))


@pytest.mark.parametrize("field, value", [
    ("id", ""), ("date", "06/10/2026"), ("date", "20261006"), ("date", None),
    ("hypothesis", "  "), ("instrument", "v3"), ("n", -1), ("n", 1.5),
    ("n", True), ("exp_r", "0.1"), ("exp_r", float("inf")), ("p", 1.2),
    ("p", -0.01), ("verdict", "PASSED"), ("record", ""),
])
def test_an_invalid_field_is_refused(field, value):
    with pytest.raises(ValueError, match=f"'{field}'"):
        stats.validate_ledger_row(_row(**{field: value}))


def test_missing_or_extra_fields_are_refused():
    row = _row()
    del row["p"]
    with pytest.raises(ValueError, match=r"missing \['p'\]"):
        stats.validate_ledger_row(row)
    with pytest.raises(ValueError, match=r"extra \['note'\]"):
        stats.validate_ledger_row(_row(note="x"))


def test_a_non_object_row_is_refused():
    with pytest.raises(ValueError, match="JSON object"):
        stats.validate_ledger_row(["v999-demo"])


def test_load_of_a_missing_file_is_empty(tmp_path):
    assert stats.load_ledger(tmp_path / "none.jsonl") == []


def test_append_then_load_round_trips_in_field_order(tmp_path):
    path = tmp_path / "ledger.jsonl"
    rows = stats.append_ledger_row(_row(), path=path)
    assert rows == [_row()]
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and text.count("\n") == 1
    assert list(json.loads(text)) == list(stats.LEDGER_FIELDS)
    assert stats.load_ledger(path) == [_row()]


def test_append_writes_lf_line_endings(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_row(), path=path)
    assert b"\r\n" not in path.read_bytes()


def test_append_repairs_a_missing_trailing_newline(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(_row(id="a")), encoding="utf-8")
    stats.append_ledger_row(_row(id="b"), path=path)
    assert [r["id"] for r in stats.load_ledger(path)] == ["a", "b"]


def test_append_refuses_a_duplicate_id(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_row(), path=path)
    with pytest.raises(ValueError, match="duplicate"):
        stats.append_ledger_row(_row(verdict="PASS"), path=path)
    assert len(stats.load_ledger(path)) == 1


def test_append_refuses_an_invalid_row_without_touching_the_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with pytest.raises(ValueError):
        stats.append_ledger_row(_row(verdict="maybe"), path=path)
    assert not path.exists()


def test_load_names_the_bad_line(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(_row()) + "\n{not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ledger line 2"):
        stats.load_ledger(path)


def test_load_refuses_duplicate_ids(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text((json.dumps(_row()) + "\n") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="ledger line 2: duplicate"):
        stats.load_ledger(path)


def test_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n" + json.dumps(_row()) + "\n\n", encoding="utf-8")
    assert stats.load_ledger(path) == [_row()]


def test_ledger_qvalues_maps_ids_to_bh_q():
    rows = [_row(id="a", p=0.01), _row(id="b", p=None), _row(id="c", p=0.04)]
    assert stats.ledger_qvalues(rows) == {
        "a": pytest.approx(0.02), "b": None, "c": pytest.approx(0.04)}


@pytest.mark.parametrize("sep", ["\u2028", "\u0085", "\x0b", "\x0c"])
def test_unicode_line_separators_in_text_round_trip(tmp_path, sep):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_row(id="a", hypothesis=f"x{sep}y"), path=path)
    stats.append_ledger_row(_row(id="b"), path=path)
    rows = stats.load_ledger(path)
    assert [r["id"] for r in rows] == ["a", "b"]
    assert rows[0]["hypothesis"] == f"x{sep}y"


def test_iso_week_date_is_refused():
    with pytest.raises(ValueError, match="'date'"):
        stats.validate_ledger_row(_row(date="2026-W41-1"))


@pytest.mark.parametrize("verdict", ["SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED"])
def test_a_screen_row_validates(verdict):
    stats.validate_ledger_row(_row(id="screen-demo", instrument="screen-v1",
                                   verdict=verdict))


def test_the_committed_ledger_still_loads_unchanged():
    rows = stats.load_ledger()
    assert len(rows) >= 57
    assert all(row["verdict"] in stats.VERDICTS for row in rows)
