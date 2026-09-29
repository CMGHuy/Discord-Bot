"""Every Part 3 store that holds data worth keeping has an importer."""
import importlib
import json
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[2]

# Flags are deliberately absent: a flag's entire state is whether it exists
# right now, and the cutover happens with the bot stopped.
EXPECTED = ["jobs", "scheduled", "preferences", "settings_audit",
            "killswitch", "ticker_directory", "tuning"]

TABLES = ["admin_jobs", "scheduled_jobs", "ui_preferences", "settings_audit",
          "killswitch", "ticker_directory", "tuning_results", "tuning_proposals"]


@pytest.fixture
def env(tmp_path, monkeypatch, db_committed):
    """A scratch DATA_DIR and the test Postgres wired in as the app engine."""
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield tmp_path
    reset_engine()


def _counts(conn):
    import sqlalchemy as sa
    return {t: conn.execute(sa.text(f"SELECT count(*) FROM {t}")).scalar_one()
            for t in TABLES}


def _run(name, argv=()):
    return importlib.import_module(f"scripts.db.import_{name}").main(list(argv))


def _write_json(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.mark.parametrize("name", EXPECTED)
def test_the_importer_exists_and_imports(name):
    assert (REPO / "scripts" / "db" / f"import_{name}.py").exists()
    mod = importlib.import_module(f"scripts.db.import_{name}")
    assert callable(getattr(mod, "main", None))


@pytest.mark.parametrize("name", EXPECTED)
def test_dry_run_writes_nothing(name, env, db_committed):
    _write_json(env / "admin_jobs.json", {"J1": {"id": "J1", "kind": "tune", "state": "done",
                                               "started_at": "2026-01-02T15:00:00+00:00"}})
    _write_json(env / "scheduled_jobs.json", {"daily_recap": "2026-01-02"})
    _write_json(env / "ui_preferences.json", {"columns": ["a"]})
    _write_json(env / "killswitch.json", {"on": True, "reason": "x", "at": None,
                                          "manual_release": False})
    assert _run(name, ["--dry-run"]) == 0
    assert set(_counts(db_committed).values()) == {0}


def test_jobs_round_trip_with_null_finish_and_records_lacking_job_id(env, db_committed):
    """A live job record carries `id`, never `job_id`: the importer must cope."""
    _write_json(env / "admin_jobs.json", {
        "J1": {"id": "J1", "kind": "tune", "args": ["--strategy", "RSI"], "state": "done",
               "started_at": "2026-01-02T15:00:00.123456+00:00",
               "finished_at": "2026-01-02T15:05:00+00:00", "returncode": 0,
               "log_path": "logs/J1.log", "pid": 123, "result_path": None},
        "J2": {"id": "J2", "kind": "test", "args": [], "state": "running",
               "started_at": "2026-01-03T09:00:00+00:00", "finished_at": None,
               "returncode": None, "log_path": "logs/J2.log", "pid": 7, "result_path": None},
    })
    assert _run("jobs") == 0
    assert _counts(db_committed)["admin_jobs"] == 2
    assert _run("jobs") == 0  # rerunnable


def test_scheduled_round_trip(env, db_committed):
    _write_json(env / "scheduled_jobs.json",
                {"daily_recap": "2026-01-02", "weekend_scan": "2026-01-03"})
    assert _run("scheduled") == 0
    assert _counts(db_committed)["scheduled_jobs"] == 2


def test_preferences_round_trip_lands_as_one_admin_row(env, db_committed):
    _write_json(env / "ui_preferences.json",
                {"columns": ["ticker", "r"], "minSampleN": 30, "nested": {"a": [1, 2.5]}})
    assert _run("preferences") == 0
    from swingbot.core.db.repositories.preferences import PreferencesRepository
    assert PreferencesRepository().load(conn=db_committed)["minSampleN"] == 30
    assert _counts(db_committed)["ui_preferences"] == 1


def test_preferences_without_a_file_imports_nothing(env, db_committed):
    assert _run("preferences") == 0
    assert _counts(db_committed)["ui_preferences"] == 0


def test_settings_audit_skips_a_torn_trailing_line(env, db_committed):
    lines = [json.dumps({"ts": "2026-01-02T15:00:00+00:00",
                         "changes": [{"key": "A", "old": "1", "new": "2"}]}),
             json.dumps({"ts": "2026-01-02T15:00:00+00:00",
                         "changes": [{"key": "A", "old": "1", "new": "2"}]}),
             '{"ts": "2026-01-03T10:00:00+00:00", "chang']
    (env / "settings_audit.jsonl").write_text("\n".join(lines), encoding="utf-8")
    assert _run("settings_audit") == 0
    # Two identical entries stay two entries: the log has no natural key.
    assert _counts(db_committed)["settings_audit"] == 2


def test_settings_audit_rerun_does_not_duplicate(env, db_committed):
    (env / "settings_audit.jsonl").write_text(json.dumps(
        {"ts": "2026-01-02T15:00:00+00:00", "changes": []}) + "\n", encoding="utf-8")
    assert _run("settings_audit") == 0
    assert _run("settings_audit") == 0
    assert _counts(db_committed)["settings_audit"] == 1


@pytest.mark.parametrize("state", [
    {"on": True, "reason": "drawdown >20%", "at": "2026-01-02T15:00:00+00:00",
     "manual_release": False},
    {"on": False, "reason": None, "at": "2026-01-02T16:00:00+00:00",
     "manual_release": True},
])
def test_killswitch_maps_on_to_engaged(state, env, db_committed):
    _write_json(env / "killswitch.json", state)
    assert _run("killswitch") == 0
    from swingbot.core.db.repositories.killswitch import KillswitchRepository
    assert KillswitchRepository().state(conn=db_committed) == state


def test_ticker_directory_round_trip(env, db_committed, capsys):
    rows = [{"symbol": f"S{i:04d}", "name": f"Company {i}"} for i in range(1200)]
    _write_json(env / "ticker_directory.json", {"fetched_at": 1.0, "rows": rows})
    assert _run("ticker_directory") == 0
    assert _counts(db_committed)["ticker_directory"] == 1200
    out = capsys.readouterr().out
    assert "500/1200" in out and "1000/1200" in out


def test_tuning_imports_results_and_proposals(env, db_committed):
    (env / "tuning_results").mkdir()
    (env / "tuning_proposals").mkdir()
    _write_json(env / "tuning_results" / "abc123.json", {
        "strategy": "RSI", "gate": {"headline": "no pass"},
        "grid": [{"params": {"p": 1}, "n_eval": 40, "win_rate": 81.5, "expectancy_r": 0.0}],
        "best": None})
    _write_json(env / "tuning_proposals" / "p1.json", {
        "strategy": "RSI", "params": {"p": 1},
        "created_at": "2026-01-02T15:00:00.500000+00:00"})
    assert _run("tuning") == 0
    counts = _counts(db_committed)
    assert counts["tuning_results"] == 1 and counts["tuning_proposals"] == 1


def test_the_jobs_repository_stores_a_live_record_that_has_no_job_id(env, db_committed):
    """The dual-write hands put() the live shape (`id`, never `job_id`)."""
    from swingbot.core.db.repositories.jobs import JobRepository
    JobRepository().put({"id": "LIVE1", "kind": "tune", "state": "running",
                         "started_at": "2026-01-02T15:00:00+00:00"}, conn=db_committed)
    assert JobRepository().get_job("LIVE1", conn=db_committed)["state"] == "running"
