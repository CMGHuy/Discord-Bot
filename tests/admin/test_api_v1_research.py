"""GET /api/v1/research/ledger — the pre-registration ledger, read-only (v150).

The endpoint adds three derived fields to each validated ledger row and
ships the filter vocabularies, so the SPA hardcodes neither. It reuses
`stats.load_ledger`, which means an invalid line fails the whole request
rather than rendering a partial ledger.
"""
import json

import pytest

from swingbot.core.backtesting.instrument import stats
from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/research/ledger"

_ROW_SHAPE = {
    "id": str, "date": str, "hypothesis": str, "instrument": str,
    "n": (int, type(None)), "exp_r": NULLABLE_NUMBER, "p": NULLABLE_NUMBER,
    "verdict": str, "record": str,
    "q": NULLABLE_NUMBER, "record_exists": bool, "record_kind": str,
}


def _row(**over):
    row = {"id": "v999-demo", "date": "2026-10-06", "hypothesis": "Demo gate",
           "instrument": "v2", "n": 120, "exp_r": 0.12, "p": 0.03,
           "verdict": "FAIL", "record": "docs/superpowers/results/demo.md"}
    row.update(over)
    return row


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point the endpoint at a ledger inside a throwaway repo root.

    The path keeps the real layout (`<root>/docs/superpowers/results/`),
    because `record_exists` resolves record paths against that same root.
    """
    path = tmp_path / "docs" / "superpowers" / "results" / "preregistration-ledger.jsonl"
    path.parent.mkdir(parents=True)

    def write(rows, raw=None):
        text = raw if raw is not None else "".join(json.dumps(r) + "\n" for r in rows)
        path.write_text(text, encoding="utf-8")
        return tmp_path

    monkeypatch.setattr(stats, "LEDGER_PATH", path)
    return write


def test_requires_auth(client):
    assert client.get(_URL).status_code == 401


def test_shape_and_vocabularies(logged_in, ledger):
    ledger([_row()])
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, {"rows": list, "q_family_m": int, "verdicts": list,
                        "instruments": list})
    assert_shape(body["rows"][0], _ROW_SHAPE, where="rows[0]")
    assert body["verdicts"] == list(stats.VERDICTS)
    assert body["instruments"] == list(stats.INSTRUMENTS)


def test_rows_are_the_ledger_rows_in_file_order(logged_in, ledger):
    rows = [_row(id="a"), _row(id="b", date="2026-10-07"), _row(id="c", p=None)]
    ledger(rows)
    body = logged_in.get(_URL).get_json()
    assert [r["id"] for r in body["rows"]] == ["a", "b", "c"]
    for sent, source in zip(body["rows"], rows):
        assert {name: sent[name] for name in stats.LEDGER_FIELDS} == source


def test_q_matches_ledger_qvalues_and_the_family_size(logged_in, ledger):
    rows = [_row(id="a", p=0.01), _row(id="b", p=0.04), _row(id="c", p=None),
            _row(id="d", p=0.5)]
    ledger(rows)
    body = logged_in.get(_URL).get_json()
    expected = stats.ledger_qvalues(rows)
    assert {r["id"]: r["q"] for r in body["rows"]} == pytest.approx(expected)
    assert body["rows"][2]["q"] is None
    assert body["q_family_m"] == 3


def test_null_figures_pass_through_as_null(logged_in, ledger):
    ledger([_row(n=None, exp_r=None, p=None)])
    row = logged_in.get(_URL).get_json()["rows"][0]
    assert (row["n"], row["exp_r"], row["p"], row["q"]) == (None, None, None, None)


@pytest.mark.parametrize("record, kind", [
    ("docs/superpowers/results/demo.md", "results"),
    ("docs/superpowers/specs/2026-10-09-v150-x-design.md", "specs"),
    ("docs/superpowers/plans/implemented/v35-avwap-preregistration.md", "plans"),
    ("docs/strategy/notes.md", "other"),
    ("scripts/ops/notes", "other"),
])
def test_record_kind(logged_in, ledger, record, kind):
    ledger([_row(record=record)])
    assert logged_in.get(_URL).get_json()["rows"][0]["record_kind"] == kind


def test_record_exists_resolves_against_the_ledgers_repo_root(logged_in, ledger):
    root = ledger([_row(id="there", record="docs/superpowers/results/there.md"),
                   _row(id="gone", record="docs/superpowers/results/gone.md"),
                   _row(id="escape", record="../outside.md")])
    (root / "docs/superpowers/results/there.md").write_text("x", encoding="utf-8")
    (root.parent / "outside.md").write_text("x", encoding="utf-8")
    rows = {r["id"]: r["record_exists"] for r in logged_in.get(_URL).get_json()["rows"]}
    assert rows == {"there": True, "gone": False, "escape": False}


def test_empty_or_absent_ledger_is_an_empty_list(logged_in, ledger, monkeypatch, tmp_path):
    ledger([])
    assert logged_in.get(_URL).get_json()["rows"] == []
    monkeypatch.setattr(stats, "LEDGER_PATH", tmp_path / "nowhere" / "ledger.jsonl")
    body = logged_in.get(_URL).get_json()
    assert (body["rows"], body["q_family_m"]) == ([], 0)


def test_invalid_ledger_line_is_a_500_not_a_partial_ledger(logged_in, ledger):
    ledger([], raw=json.dumps(_row()) + "\n" + json.dumps(_row(id="b", verdict="MAYBE")) + "\n")
    resp = logged_in.get(_URL)
    assert resp.status_code == 500
    error = resp.get_json()["error"]
    assert error["code"] == "ledger_invalid"
    assert "ledger line 2" in error["message"]


def test_the_committed_ledger_loads_through_the_endpoint(logged_in):
    """A ledger the page cannot render must fail CI, not production."""
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["rows"]) == len(stats.load_ledger(stats.LEDGER_PATH))
    assert len(body["rows"]) > 0
    for row in body["rows"]:
        assert_shape(row, _ROW_SHAPE, where=f"row {row['id']}")
        assert row["record_kind"] in {"results", "specs", "plans", "other"}
    assert body["q_family_m"] == sum(1 for row in body["rows"] if row["p"] is not None)
