"""v148 O1: the admin's production server is chosen inside the image.

gunicorn itself is never imported here. It needs fcntl, which Windows lacks,
so the conf is loaded with runpy as the plain Python it is, and
`_maybe_exec_gunicorn` is driven with `find_spec`, `sys.platform` and
`os.execv` patched.
"""
import ast
import importlib
import importlib.util
import logging
import runpy
import sys
from pathlib import Path

import pytest

import admin_ui
from swingbot.admin.events import broker

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "deploy" / "gunicorn.conf.py"


@pytest.fixture
def restore_gunicorn_loggers():
    """setup_logging attaches handlers to gunicorn's loggers; put them back."""
    saved = {}
    for name in admin_ui.GUNICORN_LOGGERS:
        logger = logging.getLogger(name)
        saved[name] = (logger.handlers[:], logger.level, logger.propagate)
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate


def _conf(monkeypatch, **env) -> dict:
    for key in ("ADMIN_HOST", "ADMIN_PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(CONF))


# --- deploy/gunicorn.conf.py ----------------------------------------------

def test_conf_runs_one_gthread_worker_with_room_for_every_sse_stream(monkeypatch):
    conf = _conf(monkeypatch)
    assert conf["workers"] == 1
    assert conf["worker_class"] == "gthread"
    # The 8-stream SSE cap plus as many threads again for ordinary requests.
    assert conf["threads"] >= 2 * broker.MAX_CONNECTIONS
    # The broker's listener thread must start in the worker, not the master.
    assert conf["preload_app"] is False
    assert (conf["timeout"], conf["graceful_timeout"], conf["keepalive"]) == (60, 5, 5)
    assert conf["accesslog"] == "-"


def test_conf_binds_where_app_run_did(monkeypatch):
    assert _conf(monkeypatch)["bind"] == "0.0.0.0:1234"
    assert _conf(monkeypatch, ADMIN_HOST="127.0.0.1", ADMIN_PORT="8080")["bind"] == "127.0.0.1:8080"
    # An empty value in .env means "unset", as os.getenv(...) or default does in app.main().
    assert _conf(monkeypatch, ADMIN_HOST="", ADMIN_PORT="")["bind"] == "0.0.0.0:1234"


def test_conf_imports_nothing_but_os():
    tree = ast.parse(CONF.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0]
                for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {(node.module or "").split(".")[0]
                 for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported <= {"os"}


# --- admin_ui launcher ------------------------------------------------------

def test_gunicorn_argv_names_the_conf_and_the_wsgi_module(tmp_path):
    assert admin_ui._gunicorn_argv(tmp_path) == [
        sys.executable, "-m", "gunicorn",
        "-c", str(tmp_path / "deploy" / "gunicorn.conf.py"),
        "admin_wsgi:app",
    ]


def test_the_files_the_argv_names_ship_in_the_repo():
    argv = admin_ui._gunicorn_argv(ROOT)
    assert Path(argv[4]).is_file()
    assert (ROOT / "admin_wsgi.py").is_file()


def _patch_exec(monkeypatch, *, platform: str, installed: bool) -> list:
    calls = []
    monkeypatch.setattr(admin_ui.sys, "platform", platform)
    monkeypatch.setattr(admin_ui, "find_spec",
                        lambda name: object() if installed and name == "gunicorn" else None)
    monkeypatch.setattr(admin_ui.os, "execv", lambda path, argv: calls.append((path, list(argv))))
    return calls


def test_execs_gunicorn_when_the_image_has_it(monkeypatch):
    calls = _patch_exec(monkeypatch, platform="linux", installed=True)
    admin_ui._maybe_exec_gunicorn()
    argv = admin_ui._gunicorn_argv(Path(admin_ui.__file__).resolve().parent)
    assert calls == [(argv[0], argv)]


def test_falls_through_when_gunicorn_is_absent(monkeypatch):
    """A pre-v148 image, or a dev machine without it: today's app.run path."""
    calls = _patch_exec(monkeypatch, platform="linux", installed=False)
    admin_ui._maybe_exec_gunicorn()
    assert calls == []


def test_falls_through_on_windows_even_when_installed(monkeypatch):
    calls = _patch_exec(monkeypatch, platform="win32", installed=True)
    admin_ui._maybe_exec_gunicorn()
    assert calls == []


def test_main_block_without_gunicorn_boots_app_run_once(admin_app, tmp_path, monkeypatch,
                                                        restore_root_logging,
                                                        restore_gunicorn_loggers):
    from swingbot import config
    from swingbot.admin import app as app_mod
    from swingbot.core.infra import deploy_marker

    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(tmp_path / "admin.log"))
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "gunicorn" else real_find_spec(name, *a))
    events = []
    monkeypatch.setattr(admin_ui.os, "execv", lambda *a: events.append("execv"))
    monkeypatch.setattr(deploy_marker, "record_boot", lambda component: events.append(f"boot:{component}"))
    monkeypatch.setattr(app_mod, "main", lambda: events.append("main"))

    runpy.run_path(str(ROOT / "admin_ui.py"), run_name="__main__")

    assert events == ["boot:admin", "main"]


# --- admin_wsgi -------------------------------------------------------------

def test_admin_wsgi_logs_boots_and_bounds_the_yf_lock_before_exposing_the_app(admin_app, monkeypatch):
    from swingbot import config
    from swingbot.core.infra import deploy_marker
    from swingbot.core.marketdata import yf_safe

    events = []
    monkeypatch.setattr(admin_ui, "setup_logging", lambda: events.append("logging"))
    monkeypatch.setattr(deploy_marker, "record_boot", lambda component: events.append(f"boot:{component}"))
    monkeypatch.setattr(yf_safe, "set_default_lock_timeout", lambda s: events.append(f"lock:{s}"))
    monkeypatch.setattr(config, "ADMIN_YF_LOCK_TIMEOUT_SECONDS", 7)
    sys.modules.pop("admin_wsgi", None)
    try:
        wsgi = importlib.import_module("admin_wsgi")
        assert wsgi.app is sys.modules["swingbot.admin.app"].app
        assert events == ["logging", "boot:admin", "lock:7.0"]
    finally:
        sys.modules.pop("admin_wsgi", None)
