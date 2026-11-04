"""v205 V205-3: Server-Timing on every /api/v1 response and the slow-request log."""
import logging
import re

from swingbot import config
from swingbot.admin import request_timing

HEADER_RE = re.compile(r'^total;dur=\d+\.\d, db;dur=\d+\.\d;desc="(\d+) statements"$')
LOGGER = "swingbot.admin.request_timing"


def _slow_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING]


def test_the_header_has_exactly_the_documented_format():
    tally = request_timing.SqlTally(statements=3, db_s=0.01234)
    assert request_timing.server_timing(1.23456, tally) == 'total;dur=1234.6, db;dur=12.3;desc="3 statements"'


def test_an_api_v1_response_carries_its_statement_count(client, auth, sql_counted):
    response = client.get("/api/v1/trades", headers=auth)
    assert response.status_code == 200
    match = HEADER_RE.match(response.headers["Server-Timing"])
    assert match, response.headers["Server-Timing"]
    assert int(match.group(1)) >= 1                        # at least the trades read


def test_a_401_and_a_400_carry_it_too(client, auth, sql_counted):
    unauthorised = client.get("/api/v1/trades")
    rejected = client.get("/api/v1/calendar/pnl?bogus=1", headers=auth)
    assert (unauthorised.status_code, rejected.status_code) == (401, 400)
    assert HEADER_RE.match(unauthorised.headers["Server-Timing"])
    assert HEADER_RE.match(rejected.headers["Server-Timing"])


def test_a_path_outside_api_v1_has_no_header(client):
    assert "Server-Timing" not in client.get("/no-such-page-v205").headers


def test_the_tally_is_cleared_after_each_request(client, auth, sql_counted):
    client.get("/api/v1/trades", headers=auth)
    assert request_timing.current() is None


def test_the_threshold_is_read_per_request_and_logs_one_line(client, auth, sql_counted, monkeypatch, caplog):
    monkeypatch.setattr(config, "auto_reload_if_changed", lambda *a, **k: None)
    caplog.set_level(logging.WARNING, logger=LOGGER)
    monkeypatch.setattr(config, "ADMIN_SLOW_REQUEST_MS", 60000)
    client.get("/api/v1/trades?status=open", headers=auth)
    assert _slow_lines(caplog) == []
    monkeypatch.setattr(config, "ADMIN_SLOW_REQUEST_MS", 0)
    client.get("/api/v1/trades?status=open", headers=auth)
    [line] = _slow_lines(caplog)
    # path only: never the query string, never a header or a credential
    assert re.fullmatch(r"slow request /api/v1/trades total=\d+ms db=\d+ms statements=\d+", line), line
