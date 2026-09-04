"""NG16 — /api/v1/system/{logs,scan,bot} .

**`test_admin_and_bot_agree_on_the_flag_file_names` is the point of this
file.** Scan control is entirely file-based: the admin writes a flag and the
bot polls for it. The two sides define those paths as SEPARATE constants
(`app.py`'s TRIGGER_FILE/PAUSE_FILE vs `commands/scanning.py`'s
_TRIGGER_FILE/_PAUSE_FILE/_HEARTBEAT_FILE), and nothing but that test makes
them agree. A rename on one side raises nothing, logs nothing, and produces
a UI that cheerfully reports "not paused" forever while the bot stays
paused -- which is exactly the failure NG16 names.

`engine._STOP_FILE` and `engine._RUNNING_FILE` are baked from config.DATA_DIR
at import time and `swingbot.core.scanning.engine` is not in conftest's
reload list, so anything touching stop/running state patches them. Writing
through the real constant leaves a stop flag in the developer's data/
directory that the next real scan obeys.
"""
import os

import pytest

from tests.admin.api_v1_contract import (NULLABLE_STR, assert_error,
                                         assert_shape)

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def scan_files(admin_app, tmp_path, monkeypatch):
    """Every scan flag pointed at the test's own directory.

    admin_app's reload covers app.py's TRIGGER_FILE/PAUSE_FILE; engine's two
    are patched here because that module is deliberately not reloaded.
    """
    from swingbot.admin import app as admin_module
    from swingbot.core.scanning import engine
    from swingbot.core.scanning import runstate

    monkeypatch.setattr(runstate, "_STOP_FILE", str(tmp_path / "stop_scan.flag"))
    monkeypatch.setattr(runstate, "_RUNNING_FILE", str(tmp_path / "scan_running.flag"))
    assert admin_module.TRIGGER_FILE.startswith(str(tmp_path)), (
        "app.py's flag paths did not follow the test DATA_DIR"
    )
    return {
        "trigger": admin_module.TRIGGER_FILE,
        "pause": admin_module.PAUSE_FILE,
        "stop": runstate._STOP_FILE,
        "running": runstate._RUNNING_FILE,
    }


@pytest.fixture
def log_files(admin_app, tmp_path, monkeypatch):
    from swingbot import config

    bot_log, admin_log = tmp_path / "bot.log", tmp_path / "admin.log"
    monkeypatch.setattr(config, "LOG_FILE", str(bot_log))
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(admin_log))
    return {"bot": bot_log, "admin": admin_log}


# --- the flag-name contract --------------------------------------------

def test_admin_and_bot_agree_on_the_flag_file_names():
    """The one that matters. Scan control is a file the admin writes and the
    bot polls; the two define those paths independently, and a mismatch is
    silent on both sides -- no error, no log line, just a UI that reports
    "not paused" while the bot stays paused."""
    from swingbot.admin import app as admin_module
    from swingbot.commands import scanning as bot_module

    assert (os.path.basename(admin_module.TRIGGER_FILE)
            == os.path.basename(bot_module._TRIGGER_FILE))
    assert (os.path.basename(admin_module.PAUSE_FILE)
            == os.path.basename(bot_module._PAUSE_FILE))
    assert os.path.basename(bot_module._HEARTBEAT_FILE) == "bot_heartbeat.json", (
        "app.py's scan_status_payload reads this name literally"
    )


# --- scan status --------------------------------------------------------

def test_scan_requires_auth(client):
    assert_error(client.get("/api/v1/system/scan"), "auth", 401)


def test_scan_status_shape(logged_in, scan_files):
    assert_shape(logged_in.get("/api/v1/system/scan").get_json(), {
        "pending": bool, "triggered_at": NULLABLE_STR,
        "paused": bool, "paused_at": NULLABLE_STR,
        "running": bool, "bot_alive": bool, "bot_last_seen": NULLABLE_STR,
        "bot_session_active": (bool, type(None)),
        "bot_scan_paused": (bool, type(None)),
        "bot_healthy": (bool, type(None)),
        "bot_last_success": NULLABLE_STR,
        "bot_consecutive_failures": int,
    })


# --- scan commands ------------------------------------------------------

def test_pause_then_resume(logged_in, scan_files):
    body = logged_in.post("/api/v1/system/scan/pause").get_json()
    assert body["ok"] is True
    assert body["scan"]["paused"] is True
    assert os.path.exists(scan_files["pause"])

    body = logged_in.post("/api/v1/system/scan/resume").get_json()
    assert body["scan"]["paused"] is False
    assert not os.path.exists(scan_files["pause"])


def test_resume_when_not_paused_is_not_an_error(logged_in, scan_files):
    """Idempotent on purpose: the SPA may fire this from a stale view, and
    "already resumed" is the state the caller wanted either way."""
    assert logged_in.post("/api/v1/system/scan/resume").get_json()["ok"] is True


def test_trigger_writes_the_flag_the_bot_polls(logged_in, scan_files):
    body = logged_in.post("/api/v1/system/scan/trigger").get_json()
    assert body["scan"]["pending"] is True
    assert os.path.exists(scan_files["trigger"])


def test_stop_is_distinct_from_pause(logged_in, scan_files):
    """Stop cuts short a scan already running; pause stops future automatic
    ones. They write different files, and conflating them means "stop" would
    silently disable scheduled scanning."""
    logged_in.post("/api/v1/system/scan/stop")
    assert os.path.exists(scan_files["stop"])
    assert not os.path.exists(scan_files["pause"])


def test_commands_return_the_resulting_status(logged_in, scan_files):
    """Every command answers with the status, so the SPA needs no follow-up
    request to redraw."""
    body = logged_in.post("/api/v1/system/scan/pause").get_json()
    assert_shape(body, {"ok": bool, "message": str, "scan": dict})


def test_scan_commands_require_auth(client, scan_files):
    for verb in ("trigger", "stop", "pause", "resume"):
        assert_error(client.post(f"/api/v1/system/scan/{verb}"), "auth", 401)
    assert not os.path.exists(scan_files["pause"]), (
        "an unauthenticated call must not have written a flag"
    )


# --- logs ---------------------------------------------------------------

def test_logs_require_auth(client):
    assert_error(client.get("/api/v1/system/logs"), "auth", 401)


def test_get_logs_shape(logged_in, log_files):
    log_files["bot"].write_text("line one\nline two\n", encoding="utf-8")
    body = logged_in.get("/api/v1/system/logs").get_json()
    assert_shape(body, {"source": str, "lines": int, "path": str, "content": str})
    assert body["source"] == "bot"
    assert "line two" in body["content"]


def test_admin_source_reads_the_admin_log(logged_in, log_files):
    log_files["bot"].write_text("BOT LINE\n", encoding="utf-8")
    log_files["admin"].write_text("ADMIN LINE\n", encoding="utf-8")
    body = logged_in.get("/api/v1/system/logs?source=admin").get_json()
    assert "ADMIN LINE" in body["content"] and "BOT LINE" not in body["content"]


def test_an_unknown_source_is_rejected_not_defaulted(logged_in, log_files):
    """The Jinja route falls back to the bot log on anything unrecognised.
    Silently serving a different log than the one asked for is how someone
    concludes the bot is idle while reading the admin log."""
    assert_error(logged_in.get("/api/v1/system/logs?source=nonsense"), "invalid", 400)


def test_a_non_integer_line_count_is_rejected(logged_in, log_files):
    assert_error(logged_in.get("/api/v1/system/logs?lines=lots"), "invalid", 400)


def test_lines_limits_the_tail(logged_in, log_files):
    log_files["bot"].write_text("".join(f"line {i}\n" for i in range(50)), encoding="utf-8")
    body = logged_in.get("/api/v1/system/logs?lines=5").get_json()
    assert body["content"].count("\n") == 5
    assert "line 49" in body["content"] and "line 44" not in body["content"]


def test_an_excessive_line_count_is_clamped_not_rejected(logged_in, log_files):
    """A caller asking for more than the cap wants "as much as you have"."""
    assert logged_in.get("/api/v1/system/logs?lines=999999").get_json()["lines"] == 5000


def test_raw_logs_stay_text_plain(logged_in, log_files):
    """Spec v11. The SPA streams this into a <pre>; JSON would mean escaping
    every line to un-escape it on arrival."""
    log_files["bot"].write_text("raw line\n", encoding="utf-8")
    r = logged_in.get("/api/v1/system/logs/raw")
    assert r.mimetype == "text/plain"
    assert r.get_data(as_text=True) == "raw line\n"


def test_delete_clears_the_log(logged_in, log_files):
    log_files["bot"].write_text("noise\n", encoding="utf-8")
    body = logged_in.delete("/api/v1/system/logs").get_json()
    assert body["ok"] is True
    assert log_files["bot"].read_text() == ""


def test_delete_targets_the_named_source(logged_in, log_files):
    log_files["bot"].write_text("BOT\n", encoding="utf-8")
    log_files["admin"].write_text("ADMIN\n", encoding="utf-8")
    logged_in.delete("/api/v1/system/logs?source=admin")
    assert log_files["admin"].read_text() == ""
    assert log_files["bot"].read_text() == "BOT\n", "the wrong log was cleared"


def test_deleting_a_missing_log_is_reported_not_404(logged_in, log_files):
    """Nothing to delete and nothing wrong. The Jinja route already treats
    this as a message rather than a failure."""
    r = logged_in.delete("/api/v1/system/logs")
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


# --- bot restart --------------------------------------------------------

def test_restart_is_503_without_the_docker_socket(logged_in, monkeypatch):
    """Not a 200 carrying a failure message. Without the socket a restart is
    not something that failed -- it is something this deployment cannot do,
    and the SPA decides whether to offer the button at all on that
    distinction."""
    monkeypatch.setattr("swingbot.admin.helpers.docker_sdk", None)
    assert_error(logged_in.post("/api/v1/system/bot/restart"), "unavailable", 503)


def test_restart_succeeds_when_the_container_restarts(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.helpers.docker_sdk", object())
    monkeypatch.setattr("swingbot.admin.helpers._restart_bot_container",
                        lambda: (True, "Restarted container 'swing-bot'."))
    body = logged_in.post("/api/v1/system/bot/restart").get_json()
    assert body["ok"] is True


def test_a_failed_restart_is_503_with_the_reason(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.helpers.docker_sdk", object())
    monkeypatch.setattr("swingbot.admin.helpers._restart_bot_container",
                        lambda: (False, "container not found"))
    assert_error(logged_in.post("/api/v1/system/bot/restart"), "unavailable", 503)


def test_restart_requires_auth(client):
    assert_error(client.post("/api/v1/system/bot/restart"), "auth", 401)


# --- tick health -------------------------------------------------------

import json
from datetime import datetime, timedelta, timezone


def _write_heartbeat_file(tmp_path, **fields):
    path = os.path.join(str(tmp_path), "bot_heartbeat.json")
    with open(path, "w") as fh:
        json.dump(fields, fh)
    return path


def test_recent_success_is_healthy(tmp_path, monkeypatch):
    from swingbot.admin import app as admin_app

    monkeypatch.setattr(admin_app.config, "DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_heartbeat_file(tmp_path, timestamp=now.isoformat(),
                          last_success=now.isoformat(), consecutive_failures=0)

    payload = admin_app.scan_status_payload()

    assert payload["bot_alive"] is True
    assert payload["bot_healthy"] is True
    assert payload["bot_consecutive_failures"] == 0


def test_fresh_heartbeat_with_stale_success_is_alive_but_unhealthy(tmp_path, monkeypatch):
    """The exact blackout shape: the process is looping and stamping
    liveness, but no tick has completed for hours."""
    from swingbot.admin import app as admin_app

    monkeypatch.setattr(admin_app.config, "DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_heartbeat_file(tmp_path, timestamp=now.isoformat(),
                          last_success=(now - timedelta(hours=6)).isoformat(),
                          consecutive_failures=72)

    payload = admin_app.scan_status_payload()

    assert payload["bot_alive"] is True
    assert payload["bot_healthy"] is False
    assert payload["bot_consecutive_failures"] == 72


def test_never_reported_success_is_unknown_not_failing(tmp_path, monkeypatch):
    """A bot that has not restarted since the upgrade has no last_success.
    That is unknown, and must not render as failing."""
    from swingbot.admin import app as admin_app

    monkeypatch.setattr(admin_app.config, "DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_heartbeat_file(tmp_path, timestamp=now.isoformat())

    payload = admin_app.scan_status_payload()

    assert payload["bot_healthy"] is None
    assert payload["bot_last_success"] is None
