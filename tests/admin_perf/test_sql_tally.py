"""v205 V205-2: the admin's per-request SQL tally (index "Request timing")."""
import re
import threading
from pathlib import Path

import sqlalchemy as sa

from swingbot.admin import request_timing
from swingbot.core.db import engine

REPO = Path(__file__).resolve().parents[2]


def _run(db_engine, count):
    with db_engine.connect() as conn:
        for _ in range(count):
            conn.execute(sa.text("select 1"))


def test_outside_a_request_nothing_is_counted(sql_counted):
    _run(sql_counted, 2)
    assert request_timing.current() is None


def test_inside_a_request_each_statement_counts(sql_counted):
    token = request_timing.start_request()
    _run(sql_counted, 3)
    tally = request_timing.end_request(token)
    assert tally.statements == 3
    assert tally.db_s > 0
    assert request_timing.current() is None


def test_attach_twice_still_counts_each_statement_once(sql_counted):
    request_timing._attach(sql_counted)
    token = request_timing.start_request()
    _run(sql_counted, 2)
    assert request_timing.end_request(token).statements == 2


def test_a_tally_is_invisible_to_another_thread(sql_counted):
    token = request_timing.start_request()
    seen = []
    worker = threading.Thread(target=lambda: seen.append(request_timing.current()))
    worker.start()
    worker.join()
    request_timing.end_request(token)
    assert seen == [None]


def test_install_registers_the_hook_once(monkeypatch):
    monkeypatch.setattr(engine, "_ENGINE_HOOKS", [])
    request_timing.install_sql_counter()
    request_timing.install_sql_counter()
    assert engine._ENGINE_HOOKS == [request_timing._attach]


def test_only_the_admin_registers_an_engine_hook():
    """The bot and the refresher never carry the counting listener."""
    callers = sorted(
        str(path.relative_to(REPO)).replace("\\", "/")
        for path in (REPO / "swingbot").rglob("*.py")
        if re.search(r"\badd_engine_hook\(", path.read_text(encoding="utf-8")))
    assert callers == ["swingbot/admin/request_timing.py", "swingbot/core/db/engine.py"]
