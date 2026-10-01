"""export_json writes every Part 3 store back in its on-disk shape (v116).

The check is that the file export_json writes is read back by parity's own
loader (the one the importers and the running bot's JSON path agree with) as
exactly the rows the table holds: DB -> JSON is the inverse of JSON -> DB."""
import json
import os

import pytest

from scripts.db import export_json
from scripts.db.parity_report import STORES, parity
from swingbot.core.db.repositories.jobs import jobs_repo
from swingbot.core.db.repositories.killswitch import killswitch_repo
from swingbot.core.db.repositories.preferences import preferences_repo
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.db.repositories.settings_audit import settings_audit_repo
from swingbot.core.db.repositories.ticker_directory import ticker_directory_repo
from swingbot.core.db.repositories.tuning import proposals_repo, tuning_repo

TS = "2026-10-01T10:00:00+00:00"
PART3 = ["jobs", "scheduled_jobs", "preferences", "settings_audit", "killswitch",
         "ticker_directory", "tuning", "tuning_proposals"]


@pytest.fixture
def seeded(store_db):
    jobs_repo().put({"id": "J1", "kind": "tune", "state": "done", "started_at": TS,
                     "finished_at": TS, "progress": {"pct": 100}})
    scheduled_repo().mark("daily_recap", "2026-10-01")
    preferences_repo().save({"columns": {"trades": ["ticker", "r"]}})
    settings_audit_repo().append([{"key": "A", "old": "1", "new": "2"}], ts=TS)
    settings_audit_repo().append([{"key": "B", "old": "x", "new": "y"}], ts=TS)
    killswitch_repo().engage("drawdown")
    ticker_directory_repo().replace([{"symbol": "AAPL", "name": "Apple"},
                                     {"symbol": "MSFT", "name": "Microsoft"}])
    tuning_repo().save_result("J1", {"best": {"x": 1}})
    proposals_repo().save("2026-10-01_rsi.json", {"params": {"a": 1}}, created_at=TS)
    return store_db


@pytest.mark.parametrize("name", PART3)
def test_the_export_reads_back_through_parity_as_the_table(name, seeded, tmp_path):
    results = export_json.run_export([name], str(tmp_path), dry_run=False, force=False)
    assert results[0].status == "written"
    report = parity(name, source_path=str(tmp_path / STORES[name].filename))
    assert report.ok, report.render()


def test_on_disk_shapes_match_what_the_bot_reads(seeded, tmp_path):
    export_json.run_export(["all"], str(tmp_path), dry_run=False, force=False)
    assert isinstance(json.loads((tmp_path / "admin_jobs.json").read_text()), dict)
    assert json.loads((tmp_path / "scheduled_jobs.json").read_text()) == {"daily_recap": "2026-10-01"}
    lines = (tmp_path / "settings_audit.jsonl").read_text().splitlines()
    assert [json.loads(line)["changes"][0]["key"] for line in lines] == ["A", "B"]
    assert json.loads((tmp_path / "killswitch.json").read_text())["on"] is True
    directory = json.loads((tmp_path / "ticker_directory.json").read_text())
    assert [row["symbol"] for row in directory["rows"]] == ["AAPL", "MSFT"]
    assert directory["fetched_at"] > 0
    assert sorted(os.listdir(tmp_path / "tuning_results")) == ["J1.json"]
    assert sorted(os.listdir(tmp_path / "tuning_proposals")) == ["2026-10-01_rsi.json"]


def test_a_directory_export_removes_a_result_the_table_no_longer_has(seeded, tmp_path):
    stale = tmp_path / "tuning_results"
    stale.mkdir()
    export_json.run_export(["tuning"], str(tmp_path), dry_run=False, force=True)
    (stale / "GONE.json").write_text("{}")
    export_json.run_export(["tuning"], str(tmp_path), dry_run=False, force=True)
    assert sorted(os.listdir(stale)) == ["J1.json"]


def test_a_differing_jsonl_is_refused_without_force(seeded, tmp_path):
    (tmp_path / "settings_audit.jsonl").write_text('{"ts": "x", "changes": []}\n')
    result = export_json.run_export(["settings_audit"], str(tmp_path), dry_run=False, force=False)[0]
    assert result.status == "refused"
    assert (tmp_path / "settings_audit.exported.jsonl").exists()


def test_every_parity_store_is_exportable():
    assert set(STORES) <= set(export_json.exportable_names())
