"""Flask app/client fixtures for the admin UI test suite.

Every admin route test in tests/admin/*.py depends on `client` (a Flask
test client, no live server, no Discord, no yfinance) and `auth` (a Basic
Auth header matching the module's ADMIN_USERNAME/ADMIN_PASSWORD env-var
defaults, both "admin"). `admin_app` does the actual isolation: it points
swingbot.config.DATA_DIR at a fresh tmp_path and reloads every admin module
that bakes a data-dir-derived path into a module-level constant at import
time, so no test run ever touches the real project's data/ directory.
"""
import base64
import importlib
import json

import pytest

# Modules (in dependency order) that compute a path from config.DATA_DIR at
# import time and therefore must be reloaded AFTER config.DATA_DIR is
# monkeypatched, or their already-bound constants would still point at
# whatever DATA_DIR was when they were first imported (which may be the
# real project's data/ directory, from some earlier, unrelated test run).
# Tasks C4 (api.py), C5 (pages.py), and C29 (jobs.py) each append their new
# module's dotted path here as those modules are created.
_RELOAD_MODULES = [
    "swingbot.admin.helpers",
    "swingbot.admin.app",
    "swingbot.admin.api",
    "swingbot.admin.pages",
    "swingbot.admin.jobs",
]


@pytest.fixture
def admin_app(tmp_path, monkeypatch):
    from swingbot import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    # helpers.py does `ENV_PATH = config.ENV_PATH` at ITS OWN import time --
    # a module-level alias, not a live read of config.ENV_PATH on every
    # call. Patching config.ENV_PATH alone would do nothing once helpers.py
    # has already been imported once (e.g. by an earlier test); the reload
    # loop below re-executes that alias assignment against the patched
    # value. Without this, Settings-page tests (Tasks C38-C41) that save/
    # export/import would read and WRITE THE REAL PROJECT'S .env FILE --
    # caught by re-reading helpers.py closely rather than assuming
    # DATA_DIR alone was enough isolation.
    monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / ".env"))

    # Seed the three JSON files every admin route touches at least
    # indirectly (TradeLog(), load_account_config(), and — from Task C7
    # onward — PlanStore()) so a fresh empty tmp_path never trips a
    # FileNotFoundError deep inside core code that assumes the file exists.
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")
    (tmp_path / "account.json").write_text(json.dumps({
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    (tmp_path / "plans.json").write_text("[]", encoding="utf-8")

    mod = None
    for name in _RELOAD_MODULES:
        mod = importlib.reload(importlib.import_module(name))

    app = mod.app if hasattr(mod, "app") else importlib.import_module("swingbot.admin.app").app
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def client(admin_app):
    return admin_app.test_client()


@pytest.fixture
def auth():
    token = base64.b64encode(b"admin:admin").decode("ascii")
    return {"Authorization": f"Basic {token}"}
