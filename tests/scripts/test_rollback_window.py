"""v220 V220-7: rollback-window doc-key snapshot and release report."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_window as rw  # noqa: E402


class FakeRun:
    def __init__(self, stdout: str = "", code: int = 0):
        self.stdout, self.code, self.calls = stdout, code, []

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        if self.code:
            raise subprocess.CalledProcessError(self.code, cmd, "", "psql: down")
        return subprocess.CompletedProcess(cmd, 0, self.stdout, "")


ROWS = ("plans\tP1\tentry_context,legs_realized,status_history\n"
        "plans\tP2\t\n"
        "journal_entries\tT1\tlesson,note,tags\n"
        "bogus\tX\ta\n")


def test_keys_sql_reads_both_tables_and_never_writes():
    sql = " ".join(rw.KEYS_SQL.split())
    assert "FROM plans" in sql and "FROM journal_entries" in sql and "jsonb_object_keys(doc)" in sql
    for verb in ("INSERT", "UPDATE ", "DELETE", "DROP", "ALTER", "TRUNCATE"):
        assert verb not in sql.upper()


def test_keys_snapshot_parses_rows_read_only(tmp_path):
    run = FakeRun(ROWS)
    snap = rw.keys_snapshot(app_dir=tmp_path, run=run)
    assert snap["plans"] == {"P1": ["entry_context", "legs_realized", "status_history"], "P2": []}
    assert snap["journal_entries"] == {"T1": ["lesson", "note", "tags"]}
    assert snap["at"].endswith("Z") and len(snap["at"]) == 20
    cmd, kw = run.calls[0]
    assert "PGOPTIONS=-c default_transaction_read_only=on" in cmd and cmd[-1] == rw.KEYS_SQL
    assert kw["cwd"] == str(tmp_path)


def test_updated_sql_embeds_only_well_formed_timestamps():
    sql = rw.updated_sql("2026-11-08T10:00:00Z", "2026-11-09T12:30:00Z")
    assert "updated_at >= '2026-11-08T10:00:00Z'" in sql and "updated_at <= '2026-11-09T12:30:00Z'" in sql
    for bad in ("2026-11-08", "2026-11-08T10:00:00Z'; DROP TABLE plans; --", ""):
        with pytest.raises(ValueError):
            rw.updated_sql(bad, "2026-11-09T12:30:00Z")


def test_window_report_counts_updated_new_and_dropped_keys():
    snapshot = {"at": "x", "plans": {"P1": ["a", "b", "c"], "P2": ["a"]}, "journal_entries": {"T1": ["n"]}}
    current = {"plans": {"P1": ["a"], "P2": ["a", "z"], "P9": ["a"]}, "journal_entries": {}}
    updated = {"plans": ["P2", "P1", "P9"]}
    report = rw.window_report(snapshot, current, updated)
    assert report["tables"]["plans"] == {
        "updated": 3, "new": 1,
        "fewer_keys": [{"id": "P1", "before": 3, "after": 1, "dropped": ["b", "c"]}]}
    assert report["tables"]["journal_entries"] == {"updated": 0, "new": 0, "fewer_keys": []}


def test_cli_snapshot_writes_the_file_atomically(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rw, "_RUN", FakeRun(ROWS))
    out = tmp_path / "keys.json"
    assert rw.main(["snapshot", "--out", str(out), "--app-dir", str(tmp_path)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["plans"]["P2"] == []
    assert not (tmp_path / "keys.json.tmp").exists()
    assert str(out) in capsys.readouterr().out


def test_cli_report_prints_the_window_report(tmp_path, monkeypatch, capsys):
    snap = tmp_path / "keys.json"
    snap.write_text(json.dumps({"at": "x", "plans": {"P1": ["a", "b"]}, "journal_entries": {}}), encoding="utf-8")
    run = FakeRun("plans\tP1\ta\n")
    monkeypatch.setattr(rw, "_RUN", run)
    assert rw.main(["report", "--snapshot", str(snap), "--since", "2026-11-08T10:00:00Z",
                    "--until", "2026-11-09T10:00:00Z", "--app-dir", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tables"]["plans"]["fewer_keys"][0]["dropped"] == ["b"]
    assert "2026-11-08T10:00:00Z" in run.calls[0][0][-1]


@pytest.mark.parametrize("args", [
    ["report", "--snapshot", "MISSING", "--since", "2026-11-08T10:00:00Z", "--until", "2026-11-09T10:00:00Z"],
    ["report", "--snapshot", "SNAP", "--since", "yesterday", "--until", "2026-11-09T10:00:00Z"],
])
def test_cli_report_failures_exit_1(tmp_path, monkeypatch, capsys, args):
    snap = tmp_path / "keys.json"
    snap.write_text('{"plans": {}, "journal_entries": {}}', encoding="utf-8")
    monkeypatch.setattr(rw, "_RUN", FakeRun())
    args = [str(tmp_path / "nope.json") if a == "MISSING" else str(snap) if a == "SNAP" else a for a in args]
    assert rw.main([*args, "--app-dir", str(tmp_path)]) == 1
    assert "window report failed" in capsys.readouterr().err


def test_cli_snapshot_psql_failure_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rw, "_RUN", FakeRun(code=2))
    assert rw.main(["snapshot", "--out", str(tmp_path / "k.json"), "--app-dir", str(tmp_path)]) == 1
    assert not (tmp_path / "k.json").exists()
