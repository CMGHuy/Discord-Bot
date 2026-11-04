# Admin read performance, Layer 1 -- Part 1: measurement and goldens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-d. Measurement stays in the product", "Testing", "Rollout and rollback".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract live there. Every task below implicitly includes the Global Constraints.

Tasks in this part: V205-1 (timing script and the production baseline), V205-2 (engine hook, SQL tally, suite `admin-perf`), V205-3 (`Server-Timing`, slow log, `ADMIN_SLOW_REQUEST_MS`), V205-4 (the golden book, frozen clock and endpoint fixtures). V205-4 passed 20 KB as first drafted and was split: V205-4b (money references, the recorder, the frozen goldens) sits in [`_1b-goldens.md`](2026-11-04-v205-admin-read-performance_1b-goldens.md) so neither file passes 1500 lines.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

# Phase 1 -- Measurement (L1-d)

### Task V205-1: Read-only production timing script; baseline run

**Model:** sonnet — a self-contained ops script with unit tests plus one scripted production read; no design judgement left.

**Files:**
- Create: `scripts/ops/admin_endpoint_timing.py`
- Create: `tests/scripts/test_admin_endpoint_timing.py` (suite `scripts`, `tests/scripts/`)
- Modify: `docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md` (`## Results`: add `### Before v205 (script)`)

**Interfaces:**
- Consumes: nothing from other tasks. The `Server-Timing` format it parses is fixed by the index ("Request timing"); V205-3 produces it. Before V205-3 ships the header is absent and the db columns print `-`.
- Produces (index "Timing script"): `endpoints(month: str, day: str) -> dict[str, str]` (the eight endpoint names every task uses, in this order), `parse_server_timing(header: str | None) -> dict[str, dict]`, `time_endpoints(client, headers: dict, paths: dict[str, str], *, runs: int = 2) -> list[dict]`, `format_table(rows: list[dict]) -> str`, `main(argv: list[str] | None = None) -> int`. V205-4 imports `endpoints`; V205-18 runs the script unchanged.

Facts the script relies on (verified): `swingbot/admin/api_v1/auth.py:44 require_auth` accepts HTTP Basic credentials (`request.authorization`, checked by `login_limiter.attempt`), so no `POST /api/v1/session` is needed. Importing `swingbot.admin.app` starts no thread: the SSE `DbEventListener` is built lazily by `swingbot/admin/events/broker.py:52` on the first subscriber, and `freshness.warm_quotes_background` runs only inside a request, exactly as a browser's page load triggers it. The sparklines route takes `?date=` (`calendar.py:114 _date_param`; `_FILTERS = {"month", "strategy", "horizon", "date"}`). `scripts/ops/` is not a package: tests import it by putting the directory on `sys.path` (precedent `tests/scripts/test_env_set.py:6-8`).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_admin_endpoint_timing.py`:

```python
"""scripts/ops/admin_endpoint_timing.py: read-only admin endpoint timing (v205 V205-1)."""
import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import admin_endpoint_timing as timing  # noqa: E402

NAMES = ["dashboard", "dashboard_today", "trades", "trades_open", "live",
         "calendar_month", "calendar_day", "calendar_sparklines"]


class _Response:
    def __init__(self, status=200, body=b"{}", header=None):
        self.status_code = status
        self._body = body
        self.headers = {} if header is None else {"Server-Timing": header}

    def get_data(self):
        return self._body


class _Client:
    """Answers every GET with a fixed response and records what was asked."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, path, headers=None):
        self.calls.append((path, dict(headers or {})))
        return self.response


def test_endpoints_are_the_eight_profiled_paths_in_order():
    paths = timing.endpoints("2026-11", "2026-11-03")
    assert list(paths) == NAMES
    assert paths["dashboard_today"] == "/api/v1/dashboard?mode=today"
    assert paths["trades_open"] == "/api/v1/trades?status=open"
    assert paths["calendar_month"] == "/api/v1/calendar/pnl?month=2026-11"
    assert paths["calendar_day"] == "/api/v1/calendar/pnl/day?date=2026-11-03"
    assert paths["calendar_sparklines"] == "/api/v1/calendar/pnl/day/sparklines?date=2026-11-03"


def test_parse_reads_total_db_and_the_statement_count():
    header = 'total;dur=1234.5, db;dur=12.3;desc="29 statements"'
    assert timing.parse_server_timing(header) == {
        "total": {"dur": 1234.5}, "db": {"dur": 12.3, "statements": 29}}


@pytest.mark.parametrize("header", [None, "", "cdn-cache;desc=HIT", "total;dur=abc",
                                    'db;dur=1.0;desc="many statements"'])
def test_a_missing_foreign_or_malformed_header_parses_to_what_it_can(header):
    parsed = timing.parse_server_timing(header)
    assert "total" not in parsed
    assert parsed.get("db", {}).get("statements") is None


def test_time_endpoints_makes_get_requests_only_and_measures_each_run():
    client = _Client(_Response(body=b"x" * 1400, header='total;dur=5.0, db;dur=1.5;desc="3 statements"'))
    rows = timing.time_endpoints(client, {"Authorization": "Basic abc"},
                                 {"dashboard": "/api/v1/dashboard"}, runs=2)
    assert [(r["name"], r["run"]) for r in rows] == [("dashboard", 1), ("dashboard", 2)]
    assert all(r["status"] == 200 and r["bytes"] == 1400 for r in rows)
    assert all(r["db_ms"] == 1.5 and r["statements"] == 3 and r["ms"] >= 0 for r in rows)
    assert [c[0] for c in client.calls] == ["/api/v1/dashboard"] * 2


def test_without_the_header_the_db_columns_are_none_and_print_a_dash():
    rows = timing.time_endpoints(_Client(_Response()), {}, {"live": "/api/v1/live"}, runs=1)
    assert rows[0]["db_ms"] is None and rows[0]["statements"] is None
    table = timing.format_table(rows)
    assert table.splitlines()[0].startswith("| Endpoint |")
    assert "| live | `/api/v1/live` | 1 | 200 |" in table
    assert table.rstrip().endswith("| - | - |")


def test_main_never_prints_the_password_and_fails_on_a_non_200(monkeypatch, capsys):
    client = _Client(_Response(status=500))
    monkeypatch.setattr(timing, "_client", lambda: client)
    monkeypatch.setenv("ADMIN_USERNAME", "partner")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret-v205")
    code = timing.main(["--month", "2026-11", "--date", "2026-11-03", "--runs", "1"])
    out = capsys.readouterr().out
    token = base64.b64encode(b"partner:s3cret-v205").decode("ascii")
    assert code == 1
    assert "s3cret-v205" not in out and token not in out
    assert client.calls[0][1]["Authorization"] == f"Basic {token}"
    assert len(client.calls) == 8


def test_main_without_credentials_exits_2_without_a_request(monkeypatch, capsys):
    monkeypatch.setattr(timing, "_client", lambda: pytest.fail("no request without credentials"))
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert timing.main([]) == 2
    assert "ADMIN_USERNAME" in capsys.readouterr().err


def test_defaults_are_the_berlin_month_and_date(monkeypatch):
    from datetime import datetime, timezone
    # 23:30 UTC on 31 Oct is 00:30 on 1 Nov in Berlin (CET, after the 25 Oct switch).
    monkeypatch.setattr(timing, "_now", lambda: datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc))
    args = timing._parse(["--runs", "3"])
    assert (args.month, args.date, args.runs) == ("2026-11", "2026-11-01", 3)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_admin_endpoint_timing.py`
Expected: collection error, `ModuleNotFoundError: No module named 'admin_endpoint_timing'`.

- [ ] **Step 3: Write the script**

Create `scripts/ops/admin_endpoint_timing.py`:

```python
"""Read-only timing of the admin's eight profiled endpoints (v205 V205-1).

Runs INSIDE the admin container, against the app in-process through Flask's
test client, so the number is the server's own work with no network or
gunicorn queueing in it:

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin \
        python - --month 2026-11 --date 2026-11-03 --runs 2" < scripts/ops/admin_endpoint_timing.py

(once deployed: ``docker compose exec -T admin python scripts/ops/admin_endpoint_timing.py``).

GET requests only, authenticated with HTTP Basic from the container's own
ADMIN_USERNAME/ADMIN_PASSWORD; neither is ever printed. Importing
swingbot.admin.app starts no thread (the SSE listener starts on the first
subscriber), and a GET does exactly what a browser's page load does.

The db columns come from the ``Server-Timing`` header v205 adds (V205-3):
``total;dur=<ms>, db;dur=<ms>;desc="<n> statements"``. Before that ships
they print ``-``.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
_HEADER = "| Endpoint | Path | Run | Status | ms | Bytes | db ms | Statements |"
_RULE = "|---|---|---|---|---|---|---|---|"


def endpoints(month: str, day: str) -> dict[str, str]:
    """Endpoint name -> path. These names are the ones every v205 task uses."""
    return {
        "dashboard": "/api/v1/dashboard",
        "dashboard_today": "/api/v1/dashboard?mode=today",
        "trades": "/api/v1/trades",
        "trades_open": "/api/v1/trades?status=open",
        "live": "/api/v1/live",
        "calendar_month": f"/api/v1/calendar/pnl?month={month}",
        "calendar_day": f"/api/v1/calendar/pnl/day?date={day}",
        "calendar_sparklines": f"/api/v1/calendar/pnl/day/sparklines?date={day}",
    }


def _metric(params: list[str]) -> dict:
    """``dur=<float>`` and ``desc="<n> statements"`` of one header entry."""
    entry: dict = {}
    for param in params:
        key, _, value = param.partition("=")
        try:
            if key == "dur":
                entry["dur"] = float(value)
            elif key == "desc":
                entry["statements"] = int(value.strip('"').split(" ")[0])
        except ValueError:
            continue
    return entry


def parse_server_timing(header: str | None) -> dict[str, dict]:
    """``{"total": {"dur"}, "db": {"dur", "statements"}}``; whatever is unreadable is left out."""
    parsed: dict[str, dict] = {}
    for part in (header or "").split(","):
        bits = [bit.strip() for bit in part.split(";")]
        if bits[0] in ("total", "db"):
            entry = _metric(bits[1:])
            if "dur" in entry:
                parsed[bits[0]] = entry
    return parsed


def time_endpoints(client, headers: dict, paths: dict[str, str], *, runs: int = 2) -> list[dict]:
    """Every path ``runs`` times, in order: wall ms, status, bytes, db ms, statements."""
    rows = []
    for run in range(1, runs + 1):
        for name, path in paths.items():
            started = time.perf_counter()
            response = client.get(path, headers=headers)
            elapsed_ms = (time.perf_counter() - started) * 1000
            db = parse_server_timing(response.headers.get("Server-Timing")).get("db", {})
            rows.append({"name": name, "path": path, "run": run,
                         "status": response.status_code, "ms": round(elapsed_ms, 1),
                         "bytes": len(response.get_data()),
                         "db_ms": db.get("dur"), "statements": db.get("statements")})
    return rows


def _cell(value) -> str:
    return "-" if value is None else str(value)


def format_table(rows: list[dict]) -> str:
    lines = [_HEADER, _RULE]
    for r in rows:
        lines.append(f"| {r['name']} | `{r['path']}` | {r['run']} | {r['status']} | {r['ms']} "
                     f"| {r['bytes']} | {_cell(r['db_ms'])} | {_cell(r['statements'])} |")
    return "\n".join(lines) + "\n"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    berlin = _now().astimezone(BERLIN)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--month", default=berlin.strftime("%Y-%m"), help="YYYY-MM (default: Berlin month)")
    parser.add_argument("--date", default=berlin.date().isoformat(), help="YYYY-MM-DD (default: Berlin date)")
    parser.add_argument("--runs", type=int, default=2)
    return parser.parse_args(argv)


def _ensure_repo_on_path() -> None:
    """``python scripts/ops/x.py`` puts scripts/ops on sys.path, not the repo root."""
    here = globals().get("__file__")
    if here:
        root = str(Path(here).resolve().parents[2])
        if root not in sys.path:
            sys.path.insert(0, root)


def _client():
    _ensure_repo_on_path()
    from swingbot.admin.app import app
    return app.test_client()


def _auth_headers(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    username, password = os.environ.get("ADMIN_USERNAME"), os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        print("ADMIN_USERNAME/ADMIN_PASSWORD are not set in this environment", file=sys.stderr)
        return 2
    rows = time_endpoints(_client(), _auth_headers(username, password),
                          endpoints(args.month, args.date), runs=args.runs)
    print(format_table(rows), end="")
    return 0 if all(r["status"] == 200 for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_admin_endpoint_timing.py`
Expected: `12 passed` (the malformed-header test has 5 cases), `0 failed`.

Then `python <wt>/scripts/dev/complexity_gate.py` -- expected clean (every function here is under 8).

- [ ] **Step 5: Commit the script**

```bash
git -C <wt> add scripts/ops/admin_endpoint_timing.py tests/scripts/test_admin_endpoint_timing.py
git -C <wt> commit -m "feat(ops): read-only admin endpoint timing script (v205 V205-1)"
```

- [ ] **Step 6: Baseline on production (read-only)**

Pick `D` = the most recent Berlin weekday with closed trades before today and `M` = today's Berlin month (the spec's own table used `2026-11` and `2026-11-03`). Write both down: V205-18 re-runs with the same arguments.

```bash
bash <wt>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python - --month M --date D --runs 2" \
  < <wt>/scripts/ops/admin_endpoint_timing.py > <scratchpad>/v205_before.md 2>&1
tail -n 20 <scratchpad>/v205_before.md
```

Substitute `M` and `D` literally. Put no command substitution in the remote command: the wrapper expands it locally. Expected: 16 rows, every status `200`, db columns `-` (no header yet), and nothing that looks like a credential. A non-200 row is recorded as measured, never retried into a 200.

- [ ] **Step 7: Record the baseline in the spec**

Append under the spec's `## Results` (below "Filled by each plan after its production measurement."):

```markdown
### Before v205 (script)

Measured <YYYY-MM-DD HH:MM> Berlin with `scripts/ops/admin_endpoint_timing.py --month M --date D --runs 2`
inside the `admin` container (image `sha-<12>` from `docker compose images admin`), script at commit <short sha of Step 5>.

<the 18-line table from v205_before.md, pasted unchanged>
```

```bash
git -C <wt> add docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md
git -C <wt> commit -m "docs(v205): baseline admin endpoint timings before Layer 1 (V205-1)"
```

### Task V205-2: Engine hook in `get_engine`; admin SQL tally; `admin-perf` suite

**Model:** sonnet — a small additive seam in `engine.py` and a leaf admin module with listener tests; the shape is fully specified.

**Files:**
- Modify: `swingbot/core/db/engine.py` (module state beside `_engine`, line 15; `get_engine`, lines 54-87)
- Create: `swingbot/admin/request_timing.py`
- Create: `tests/db/test_engine_hooks.py` (suite `storage`)
- Create: `tests/admin_perf/__init__.py` (empty)
- Create: `tests/admin_perf/conftest.py`
- Create: `tests/admin_perf/test_sql_tally.py`
- Modify: `tests/suites.toml` (new suite `admin-perf`, same commit as the directory)

**Interfaces:**
- Consumes: `engine.get_engine()`, `engine.reset_engine()` (exist, `engine.py:54`, `:90`); `swallowed(log, tag, exc, ...)` (`swingbot/core/infra/swallowed.py`).
- Produces (index "Engine hook", "Request timing"): `engine.add_engine_hook(hook: Callable[[Engine], None]) -> None`, `engine._ENGINE_HOOKS: list[Callable[[Engine], None]]`; `request_timing.SqlTally` (dataclass `statements: int = 0`, `db_s: float = 0.0`), `start_request() -> contextvars.Token`, `end_request(token) -> SqlTally`, `current() -> SqlTally | None`, `install_sql_counter() -> None`, `_attach(target) -> None` (idempotent listener attach; the `sql_counted` fixture calls it on the test engine). Fixture `sql_counted` in `tests/admin_perf/conftest.py` (V205-3, V205-5 use it). V205-3 extends `request_timing.py`; V205-4 extends the conftest.

Two facts shape the tests (verified):
- `tests/conftest.py:227 _store_database` (autouse) **replaces** `engine.get_engine` with a lazy fixture lookup that returns the session `db_engine`, so in an ordinary test the real `get_engine` (and so the hook loop) never runs. Tests of the hook itself carry `pytest.mark.real_engine` (`pytest.ini:25`; precedent `tests/db/test_engine.py:7`) and point `config.DATABASE_URL` at an unreachable URL: `create_engine` is lazy and opens no connection. Endpoint tests attach the listener to `db_engine` directly through the `sql_counted` fixture.
- `db_engine` is session-scoped and importable everywhere (`tests/conftest.py:14`). A listener attached to it stays for the worker's life; it counts only while `current()` is set, so it is inert for every other test.

- [ ] **Step 1: Write the failing engine-hook tests**

Create `tests/db/test_engine_hooks.py`:

```python
"""v205 V205-2: hooks get_engine runs on every engine it creates (index "Engine hook")."""
import pytest

from swingbot import config
from swingbot.core.db import engine

pytestmark = pytest.mark.real_engine

#: Never reached: create_engine opens no connection until first use.
URL = "postgresql+psycopg://v205:v205@127.0.0.1:1/v205_hooks"


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(engine, "_ENGINE_HOOKS", [])
    monkeypatch.setattr(engine, "_engine", None)
    monkeypatch.setattr(config, "DATABASE_URL", URL)
    yield
    if engine._engine is not None:
        engine._engine.dispose()


def test_a_hook_runs_on_the_engine_get_engine_creates(fresh):
    seen = []
    engine.add_engine_hook(seen.append)
    created = engine.get_engine()
    assert seen == [created]
    assert engine.get_engine() is created and seen == [created]   # the cached engine is not re-hooked


def test_a_hook_survives_reset_engine(fresh):
    seen = []
    engine.add_engine_hook(seen.append)
    first = engine.get_engine()
    engine.reset_engine()
    second = engine.get_engine()
    assert seen == [first, second] and first is not second


def test_adding_a_hook_applies_it_to_an_existing_engine_at_once(fresh):
    existing = engine.get_engine()
    seen = []
    engine.add_engine_hook(seen.append)
    assert seen == [existing]


def test_the_same_hook_is_added_once(fresh):
    calls = []

    def hook(created):
        calls.append(created)

    engine.add_engine_hook(hook)
    engine.add_engine_hook(hook)
    engine.get_engine()
    assert engine._ENGINE_HOOKS == [hook] and len(calls) == 1


def test_a_failing_hook_never_breaks_get_engine(fresh):
    from swingbot.core.infra import swallowed

    def broken(_created):
        raise RuntimeError("listener failed")

    seen = []
    engine.add_engine_hook(broken)
    engine.add_engine_hook(seen.append)
    created = engine.get_engine()
    assert seen == [created]                          # later hooks still run
    assert swallowed.snapshot()["ops.db_engine.apply_hooks"]["count"] >= 1
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_engine_hooks.py`
Expected: FAIL, `AttributeError: ... has no attribute '_ENGINE_HOOKS'` (monkeypatch `raising=True`).

- [ ] **Step 3: Add the hook list to `engine.py`**

In `swingbot/core/db/engine.py`, extend the imports and add the module state right under `_engine: Engine | None = None` (line 15):

```python
from typing import Callable

from swingbot.core.infra.swallowed import swallowed
```

```python
# v205 L1-d: callables run on every engine get_engine() creates, so a hook
# outlives reset_engine(). Only the admin registers one (its SQL counter,
# swingbot/admin/request_timing.py); the bot's and refresher's engines carry none.
_ENGINE_HOOKS: list[Callable[[Engine], None]] = []
```

Add these two functions directly above `get_engine`:

```python
def add_engine_hook(hook: Callable[[Engine], None]) -> None:
    """Run ``hook(engine)`` on every engine get_engine() creates from now on,
    and at once on the current one. The same hook object is added only once."""
    if any(existing is hook for existing in _ENGINE_HOOKS):
        return
    _ENGINE_HOOKS.append(hook)
    if _engine is not None:
        _apply_hooks(_engine, [hook])


def _apply_hooks(created: Engine, hooks: list[Callable[[Engine], None]]) -> None:
    """A failing hook is logged and skipped: instrumentation never takes the database down."""
    for hook in hooks:
        try:
            hook(created)
        except Exception as exc:
            swallowed(log, "ops.db_engine.apply_hooks", exc, "engine hook %r failed", hook)
```

In `get_engine`, between the `_engine = create_engine(...)` call and the `log.info(...)` line, add exactly one line (complexity stays A5):

```python
    _apply_hooks(_engine, list(_ENGINE_HOOKS))
```

Check the import is legal: `git -C <wt> grep -n "^from\|^import" swingbot/core/infra/swallowed.py` must show stdlib imports only (the module's docstring says it imports nothing from swingbot), so `engine.py -> infra.swallowed` adds no cycle. The tag must match `tests/infra/test_swallowed_ratchet.py:45 TAG_RE` (`^(scan|marketdata|earnings|runstate|ops)\.`), hence `ops.db_engine.apply_hooks`; run `python <wt>/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` in Step 4 too.

- [ ] **Step 4: Run the engine-hook tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_engine_hooks.py`
Expected: `5 passed`. Then the neighbour that covers `get_engine` itself: `python <wt>/scripts/dev/testrun.py file tests/db/test_engine.py` -- expected unchanged, `0 failed`.

- [ ] **Step 5: Write the failing SQL-tally tests and the new suite directory**

Create `tests/admin_perf/__init__.py` (empty file).

Create `tests/admin_perf/conftest.py`:

```python
"""Fixtures for the v205 admin read-performance tests (suite `admin-perf`).

The app, client, auth header and the admin suite's autouse pins are tests/admin's,
imported not copied (DATA_DIR isolation, module reloads, the seeded 10,000 account,
the refresher pinned off). The tests live here because the admin suite sits at its
max_tests cap (precedent: tests/live_api/conftest.py)."""
import pytest

from tests.admin.conftest import (  # noqa: F401
    _clear_login_limiter, _pin_admin_refresher_off, admin_app, auth, client)


@pytest.fixture
def sql_counted(db_engine):
    """The admin's statement counter on the test engine.

    In tests `engine.get_engine` is the autouse lazy lookup (tests/conftest.py
    `_store_database`), so the admin's engine hook never sees `db_engine`; attach
    the listener to it directly. Idempotent, and inert outside a request."""
    from swingbot.admin import request_timing
    request_timing._attach(db_engine)
    return db_engine
```

Create `tests/admin_perf/test_sql_tally.py`:

```python
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
```

Register the directory in `tests/suites.toml`, directly after the `[suites.admin]` block (line 65-67):

```toml
[suites.admin-perf]
description = "v205 admin read performance: SQL tally, Server-Timing, goldens and budgets of the profiled endpoints"
paths = ["tests/admin_perf/"]
```

- [ ] **Step 6: Run them and confirm they fail**

This step hits the database: run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db` container, port 56789).

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_sql_tally.py`
Expected: collection error, `ImportError: cannot import name 'request_timing' from 'swingbot.admin'`.

- [ ] **Step 7: Write `request_timing.py`**

Create `swingbot/admin/request_timing.py`:

```python
"""Per-request SQL tally for the admin (v205 L1-d).

``start_request()`` puts a fresh ``SqlTally`` in a contextvar; the cursor
listeners add each statement's count and duration to it while it is set and
do nothing otherwise. A contextvar, not a global: gunicorn runs one worker
with 16 threads, and each request thread sees only its own tally.

The listener reaches an engine only through ``engine.add_engine_hook``, which
only this module calls (``install_sql_counter``), and only the admin app
imports it. The bot's and the refresher's engines never carry it.
"""
from __future__ import annotations

import contextvars
import logging
import time
from dataclasses import dataclass

from sqlalchemy import event

from swingbot.core.db import engine as db_engine

log = logging.getLogger(__name__)

_T0_KEY = "v205_statement_t0"


@dataclass
class SqlTally:
    statements: int = 0
    db_s: float = 0.0


_TALLY: contextvars.ContextVar[SqlTally | None] = contextvars.ContextVar("v205_sql_tally", default=None)


def start_request() -> contextvars.Token:
    return _TALLY.set(SqlTally())


def end_request(token: contextvars.Token) -> SqlTally:
    """The finished tally; the contextvar is back to what it was before."""
    tally = _TALLY.get() or SqlTally()
    _TALLY.reset(token)
    return tally


def current() -> SqlTally | None:
    return _TALLY.get()


def _before(conn, cursor, statement, parameters, context, executemany) -> None:
    if _TALLY.get() is not None:
        conn.info[_T0_KEY] = time.perf_counter()


def _after(conn, cursor, statement, parameters, context, executemany) -> None:
    started = conn.info.pop(_T0_KEY, None)
    tally = _TALLY.get()
    if tally is None or started is None:
        return
    tally.statements += 1
    tally.db_s += time.perf_counter() - started


def _attach(target) -> None:
    """Install both cursor listeners on ``target`` once."""
    if event.contains(target, "before_cursor_execute", _before):
        return
    event.listen(target, "before_cursor_execute", _before)
    event.listen(target, "after_cursor_execute", _after)


def install_sql_counter() -> None:
    """Count statements on every engine the admin process creates."""
    db_engine.add_engine_hook(_attach)
```

`log` is unused until V205-3 adds the slow log; keep it (V205-3 needs it, and flake8 does not flag a module-level logger).

- [ ] **Step 8: Run the tally tests, the suite manifest test and the gate**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_sql_tally.py`
Expected: `6 passed`.

Run: `python <wt>/scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: `0 failed` (the new directory belongs to exactly one suite).

Run: `python <wt>/scripts/dev/complexity_gate.py` -- expected clean (`get_engine` stays A5; new functions A1-A3).

- [ ] **Step 9: Commit (two scoped commits)**

```bash
git -C <wt> add swingbot/core/db/engine.py tests/db/test_engine_hooks.py
git -C <wt> commit -m "feat(db): engine hooks that survive reset_engine (v205 V205-2)"
git -C <wt> add swingbot/admin/request_timing.py tests/admin_perf/__init__.py tests/admin_perf/conftest.py tests/admin_perf/test_sql_tally.py tests/suites.toml
git -C <wt> commit -m "feat(admin): per-request SQL tally; admin-perf test suite (v205 V205-2)"
```

### Task V205-3: `Server-Timing` on every `/api/v1` response; slow-request log; `ADMIN_SLOW_REQUEST_MS`

**Model:** sonnet — Flask request hooks and one config field, each following an existing precedent (`freshness.install`, the v201 config fields).

**Files:**
- Modify: `swingbot/admin/request_timing.py` (created by V205-2)
- Modify: `swingbot/admin/app.py` (import block near line 50; the call right after `freshness.install(app)`, line 222)
- Modify: `swingbot/config.py` (the "Admin UI" block, after `LOGS_REFRESH_SECONDS`, line ~965-968)
- Modify: `.env.example` (the `# --- Admin UI ---` block, after `LOGS_REFRESH_SECONDS=10`, line ~528)
- Create: `tests/admin_perf/test_server_timing.py`
- Create: `tests/test_config_v205_keys.py` (suite `config`)

**Interfaces:**
- Consumes (V205-2): `SqlTally`, `start_request`, `end_request`, `current`, `install_sql_counter`, `_TALLY`; fixtures `client`, `auth`, `sql_counted` from `tests/admin_perf/conftest.py`.
- Produces (index "Request timing", "Config field"): `request_timing.install(app: Flask) -> None`; `request_timing.server_timing(total_s: float, tally: SqlTally) -> str` returning exactly `total;dur=<total_ms:.1f>, db;dur=<db_ms:.1f>;desc="<n> statements"`; `request_timing.API_PREFIX = "/api/v1"`; the slow log line `slow request <path> total=<ms>ms db=<ms>ms statements=<n>` at WARNING on logger `swingbot.admin.request_timing`; `config.ADMIN_SLOW_REQUEST_MS` (int, default 2000). V205-1's parser and V205-5's budgets read this header.

Facts (verified): `app.py:201 @app.before_request _reload_env_if_changed` calls `config.auto_reload_if_changed()` on every request, so a knob read as `config.ADMIN_SLOW_REQUEST_MS` inside the request is hot-reloaded (the admin has no SIGHUP handler; `Field.hot_reloadable` defaults to `True`, `config.py:88`). `before_request` hooks run in registration order and `after_request` hooks in reverse, so hooks registered after `freshness.install(app)` time the request after the env reload and set the header before `_gzip_response` (`app.py:91`) runs. The api_v1 blueprint's `_no_store` (`api_v1/__init__.py:39`) runs before every app-level `after_request`. Error responses (`ApiError` 400, the v1 401) still pass through `after_request`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin_perf/test_server_timing.py`:

```python
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
```

Create `tests/test_config_v205_keys.py`:

```python
"""v205 V205-3: the slow-request threshold (index "Config field")."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "ADMIN_SLOW_REQUEST_MS"


def _field():
    return next(f for f in config.FIELDS if f.attr == ATTR)


def test_is_a_hot_reloadable_admin_ui_number():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (ATTR, "Admin UI", "number", "2000")
    assert (field.min, field.max, field.step) == (100, 60000, 100)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v205" in field.help


def test_sits_right_after_the_logs_refresh_knob():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index(ATTR) == attrs.index("LOGS_REFRESH_SECONDS") + 1


def test_default_casts_to_2000():
    assert config._cast(_field(), _field().default) == 2000


def test_env_example_lists_it_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}=2000\n" in text
```

- [ ] **Step 2: Run them and confirm they fail**

This step hits the database: run `/replicate-prod-db` first if this worktree has not yet.

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_server_timing.py`
Expected: FAIL -- `AttributeError: module 'swingbot.admin.request_timing' has no attribute 'server_timing'` and `KeyError: 'Server-Timing'`.

Run: `python <wt>/scripts/dev/testrun.py file tests/test_config_v205_keys.py`
Expected: FAIL -- `StopIteration` in `_field()`.

- [ ] **Step 3: Add the request hooks to `request_timing.py`**

Extend the imports of `swingbot/admin/request_timing.py`:

```python
from flask import Flask, g, request

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
```

Append to the module:

```python
API_PREFIX = "/api/v1"
_G_KEY = "_v205_request_timing"
_DEFAULT_SLOW_MS = 2000


def server_timing(total_s: float, tally: SqlTally) -> str:
    """The header value; V205-1's timing script parses exactly this."""
    return (f"total;dur={total_s * 1000:.1f}, "
            f'db;dur={tally.db_s * 1000:.1f};desc="{tally.statements} statements"')


def install(app: Flask) -> None:
    """Time every /api/v1 request of ``app``; count its SQL. Called once by app.py."""
    install_sql_counter()
    app.before_request(_begin)
    app.after_request(_finish)
    app.teardown_request(_teardown)


def _begin() -> None:
    if request.path.startswith(API_PREFIX):
        setattr(g, _G_KEY, (time.perf_counter(), start_request()))


def _finish(response):
    state = g.get(_G_KEY)
    if state is None:
        return response
    total_s = time.perf_counter() - state[0]
    tally = current() or SqlTally()
    response.headers["Server-Timing"] = server_timing(total_s, tally)
    _log_if_slow(request.path, total_s, tally)
    return response


def _log_if_slow(path: str, total_s: float, tally: SqlTally) -> None:
    """Read per request, so a saved .env applies on the next request."""
    total_ms = total_s * 1000
    if total_ms > float(getattr(config, "ADMIN_SLOW_REQUEST_MS", _DEFAULT_SLOW_MS)):
        log.warning("slow request %s total=%.0fms db=%.0fms statements=%d",
                    path, total_ms, tally.db_s * 1000, tally.statements)


def _teardown(_exc) -> None:
    state = g.pop(_G_KEY, None)
    if state is None:
        return
    try:
        end_request(state[1])
    except ValueError as exc:
        # A streamed response (the SSE route) can tear down in another
        # context, where the token is foreign: clear the var instead.
        swallowed(log, "ops.request_timing.end_request", exc, level=logging.DEBUG)
        _TALLY.set(None)
```

(`ValueError` is not `Exception`, so the ratchet does not require the tag; it is tagged anyway, and `ops.` matches `TAG_RE`.)

- [ ] **Step 4: Install it in `app.py`**

In `swingbot/admin/app.py`, next to `from . import freshness` (line 51) add:

```python
from . import request_timing
```

Directly after `freshness.install(app)` (line 222) add:

```python
# v205 L1-d: Server-Timing (total, db time, statement count) on every /api/v1
# response, the ADMIN_SLOW_REQUEST_MS log line, and the SQL counter on the
# admin's engines only -- the bot and the refresher never import this module.
request_timing.install(app)
```

- [ ] **Step 5: Declare the config field and the example line**

In `swingbot/config.py`, directly after the `LOGS_REFRESH_SECONDS` `Field(...)` (the last field of the "Admin UI" block, before `# --- Discord Alerts`), add:

```python
    Field("ADMIN_SLOW_REQUEST_MS", "ADMIN_SLOW_REQUEST_MS", "Admin UI", "Slow admin request log threshold (ms)",
          type="number", default="2000", min=100, max=60000, step=100,
          help="v205. An /api/v1 request slower than this logs one 'slow request' line in the admin log "
               "(path, total, db time, statement count). Read on every request: a saved .env applies "
               "on the next request, no restart."),
```

In `.env.example`, directly after `LOGS_REFRESH_SECONDS=10` in the `# --- Admin UI ---` block, add:

```
# v205: an /api/v1 request slower than this many ms logs one "slow request" line.
ADMIN_SLOW_REQUEST_MS=2000
```

- [ ] **Step 6: Run the tests and their neighbours**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_server_timing.py` -- expected `6 passed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/test_config_v205_keys.py` -- expected `4 passed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_env_example_sync.py` -- expected `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py suite config` -- expected `0 failed` (another config test may enumerate the "Admin UI" fields; if one fails because the section gained a field, update that test's expected list in this commit and name it in the commit body).
Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py` -- expected unchanged (`0 failed`): the hooks add a header and nothing else.
Run: `python <wt>/scripts/dev/complexity_gate.py` -- expected clean.

- [ ] **Step 7: Commit (two scoped commits)**

```bash
git -C <wt> add swingbot/config.py .env.example tests/test_config_v205_keys.py
git -C <wt> commit -m "feat(config): ADMIN_SLOW_REQUEST_MS slow-request threshold (v205 V205-3)"
git -C <wt> add swingbot/admin/request_timing.py swingbot/admin/app.py tests/admin_perf/test_server_timing.py
git -C <wt> commit -m "feat(admin): Server-Timing header and slow-request log on /api/v1 (v205 V205-3)"
```

### Task V205-4: Golden book, frozen clock and endpoint fixtures for the 8 profiled endpoints

**Model:** opus — pinning every outside read of eight whole endpoints (clock, prices, FX, stores) without changing what they compute needs judgement about the call path.

**Files:**
- Create: `tests/admin_perf/golden_book.py`
- Create: `tests/admin_perf/test_golden_endpoints.py` (V205-4b appends the golden and money tests to it)
- Modify: `tests/admin_perf/conftest.py` (V205-2's file: add `logged_in`, `frozen_clock`, `probe_clock`, `golden_seed`)

**Interfaces:**
- Consumes: `admin_endpoint_timing.endpoints` (V205-1); the conftest and its imported admin fixtures (V205-2); `tests.store_seed.seed_store`; `performance.expand_realized_legs` (`performance.py:542`).
- Produces (index "Golden book"): `golden_book.FROZEN_NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)`, `MONTH = "2026-11"`, `DAY = "2026-11-03"`, `ENDPOINTS` (imported from V205-1, never retyped), `CLOCK_MODULES: tuple[str, ...]`, `VOLATILE_KEYS: dict[str, str]` (key -> reason), `ACCOUNT_CODE`, `QUOTES`, `PRICES`, `FX_CLOSES`, `BARS`, `trades()`, `plans()`, `frame(closes)`, `fx_frames(scale=1.0)`, `bars()`, `FrozenDatetime`, `FrozenDate`, `freeze(monkeypatch, modules)`, `CALLERS: set[str]`, `golden_path(name) -> Path`, `resolve(payload, pointer)`, `mask(payload, pointers=()) -> payload`, `diff_pointers(a, b) -> set[str]`, `MASK = "<masked>"`. Fixtures `logged_in`, `frozen_clock`, `probe_clock`, `golden_seed` (yields an object with `set_fx(scale: float = 1.0)`: the one seam that pins FX rates; V205-15 extends it to seed `fx_daily_rates`). Helper `_get(client, name) -> dict` in `test_golden_endpoints.py`. V205-4b, V205-5 and V205-15/16 consume these.

`mask(payload)` with no pointers is the index contract's `mask(payload) -> payload`; the optional `pointers` argument is how V205-4b masks the money fields.

Facts (verified): no `freezegun`/`time-machine` is installed, so the clock is frozen by swapping module-level names (`git grep` of `.now(`/`.today(` seeded `CLOCK_MODULES`; `test_clock_modules_cover_every_clock_read` settles the rest). Prices: the Dashboard reads `swingbot.admin.dashboard.prefetch_prices`/`get_current_price` (bound names, `admin/dashboard.py:33`); the Trades list reads `data.prefetch_prices`/`data.get_current_price_detail` (`trades.py:1423`). `/live` must touch no market data (`tests/live_api/conftest.py:18-31`). The admin suite's `admin_app` pins every quote currency to the account currency (`tests/admin/conftest.py:125-129`); `golden_seed` re-pins it after.

The book is tabled in V205-4b, with its arithmetic: six trades (EUR and USD closes, a 23:30 UTC close, a two-leg scale-out, two open positions), two plans, a `USDEUR=X` frame with a 0.0 close and a weekend gap.

- [ ] **Step 1: Write `golden_book.py`**

Create `tests/admin_perf/golden_book.py`:

```python
"""v205 V205-4: the fixed book the admin goldens are recorded from -- stores, quote
currencies, FX closes, prices, bars and the wall clock. Goldens are never regenerated."""
from __future__ import annotations

import copy
import datetime as _dt
import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import admin_endpoint_timing  # noqa: E402

FROZEN_NOW = _dt.datetime(2026, 11, 4, 12, 0, tzinfo=_dt.timezone.utc)
MONTH = "2026-11"
DAY = "2026-11-03"
ENDPOINTS: dict[str, str] = admin_endpoint_timing.endpoints(MONTH, DAY)
GOLDEN_DIR = Path(__file__).with_name("golden")
MASK = "<masked>"

#: Modules whose module-level datetime/date/dt names the frozen clock replaces.
#: test_clock_modules_cover_every_clock_read fails when the call path reads the
#: clock from a module missing here. V205-16 appends swingbot.core.marketdata.fx_convert.
CLOCK_MODULES: tuple[str, ...] = (
    "swingbot.admin.api_v1.calendar",
    "swingbot.admin.api_v1.dashboard",
    "swingbot.admin.api_v1.live",
    "swingbot.admin.api_v1.live_events",
    "swingbot.admin.api_v1.trades",
    "swingbot.admin.dashboard",
    "swingbot.core.analytics.rank",
    "swingbot.core.planning.account",
    "swingbot.core.tracking.performance",
)

#: Keys still nondeterministic under the frozen clock, key -> why. Masked anywhere.
VOLATILE_KEYS: dict[str, str] = {}

ACCOUNT_CODE = "EUR"
QUOTES: dict[str, str] = {"AAPL": "USD", "SAP.DE": "EUR"}
PRICES: dict[str, float] = {"AAPL": 104.0, "SAP.DE": 212.0}
FX_CLOSES: dict[str, dict[str, float]] = {"USDEUR=X": {
    "2026-10-26": 0.8600, "2026-10-27": 0.8620, "2026-10-28": 0.0, "2026-10-29": 0.8650,
    "2026-10-30": 0.8640, "2026-11-02": 0.8680, "2026-11-03": 0.8700, "2026-11-04": 0.8720}}
BARS: dict[str, dict[str, float]] = {
    "AAPL": {"2026-10-28": 99.0, "2026-10-29": 101.0, "2026-10-30": 100.5,
             "2026-11-02": 102.0, "2026-11-03": 104.0},
    "SAP.DE": {"2026-10-28": 201.0, "2026-10-29": 203.0, "2026-10-30": 205.0,
               "2026-11-02": 208.0, "2026-11-03": 212.0}}
PLAN_ACTIVE = "11111111-1111-4111-8111-111111111111"
PLAN_PENDING = "22222222-2222-4222-8222-222222222222"


def frame(closes: dict[str, float]) -> pd.DataFrame:
    values = list(closes.values())
    return pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                         "Volume": [0] * len(values)}, index=pd.DatetimeIndex(list(closes)))


def fx_frames(scale: float = 1.0) -> dict[str, pd.DataFrame]:
    return {pair: frame({d: c * scale for d, c in closes.items()}) for pair, closes in FX_CLOSES.items()}


def bars() -> dict[str, pd.DataFrame]:
    return {ticker: frame(closes) for ticker, closes in BARS.items()}


def _plan(plan_id: str, ticker: str, status: str, entry: float) -> dict:
    return {"plan_id": plan_id, "ticker": ticker, "created_at": "2026-11-02T08:00:00+00:00",
            "source": "confluence", "strategy": "S/R Confluence", "horizon_key": "4w",
            "direction": "bullish", "entry_type": "stop_entry", "trigger_price": entry,
            "entry_price": entry, "expiry_bars": 5, "stop_loss": round(entry * 0.95, 2),
            "tp1": round(entry * 1.1, 2), "tp1_fraction": 0.5, "tp2": round(entry * 1.2, 2),
            "breakeven_trigger_fraction": 0.5, "trail_atr_mult": 1.5, "quality_score": 72,
            "quality_breakdown": [], "tier": "A", "badge": "VALIDATED", "badge_stats": {},
            "status": status, "status_history": [], "legs_realized": []}


def plans() -> list[dict]:
    return [_plan(PLAN_ACTIVE, "AAPL", "ACTIVE", 100.0), _plan(PLAN_PENDING, "SAP.DE", "PENDING", 215.0)]


def _trade(trade_id, ticker, *, status, entry, shares, closed_at=None, exit_price=None,
           pnl=None, plan_id=None, legs=()) -> dict:
    return {"id": trade_id, "plan_id": plan_id, "ticker": ticker, "strategy": "S/R Confluence",
            "horizon_key": "4w", "direction": "bullish", "confidence_level": 4,
            "confidence_label": "High", "confidence_score": 81.0, "entry": entry,
            "stop_loss": round(entry * 0.95, 2), "take_profit": round(entry * 1.2, 2),
            "target2": None, "risk_reward_ratio": 2.0, "badge": "VALIDATED", "quality_score": 72,
            "source": "confluence", "legs": list(legs), "opened_at": "2026-10-27T14:00:00+00:00",
            "status": status, "closed_at": closed_at, "exit_price": exit_price,
            "realized_pnl_amount": pnl, "shares": shares, "position_value": entry * shares,
            "target_sources": [], "stop_sources": [], "target2_sources": [], "confirmed_by": [],
            "explanation": None, "confidence_breakdown": None}


def trades() -> list[dict]:
    legs = [{"fraction": 0.5, "exit_price": 110.0, "closed_at": "2026-10-29T15:00:00+00:00", "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 104.0, "closed_at": "2026-11-02T15:00:00+00:00", "r": 0.8, "reason": "trail"}]
    return [
        _trade("golden-t1-sap-win", "SAP.DE", status="win", entry=200.0, shares=10,
               closed_at="2026-11-03T14:00:00+00:00", exit_price=212.0, pnl=120.0),
        _trade("golden-t2-usd-win", "AAPL", status="win", entry=100.0, shares=10,
               closed_at="2026-11-03T20:30:00+00:00", exit_price=105.0, pnl=50.0),
        _trade("golden-t3-usd-midnight", "AAPL", status="loss", entry=100.0, shares=10,
               closed_at="2026-11-02T23:30:00+00:00", exit_price=97.0, pnl=-30.0),
        _trade("golden-t4-usd-scaleout", "AAPL", status="win", entry=100.0, shares=10,
               closed_at="2026-11-02T15:00:00+00:00", exit_price=104.0, pnl=70.0, legs=legs),
        _trade("golden-t5-usd-open", "AAPL", status="open", entry=100.0, shares=10, plan_id=PLAN_ACTIVE),
        _trade("golden-t6-sap-open", "SAP.DE", status="open", entry=200.0, shares=5),
    ]


# --- the frozen clock ------------------------------------------------------

#: Modules that read the clock through a frozen class (probe_clock's evidence).
CALLERS: set[str] = set()


def _caller() -> str:
    return sys._getframe(2).f_globals.get("__name__", "?")


class _FrozenMeta(type):
    """isinstance/issubclass answer for the real class (a patched module still accepts real datetimes)."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls._real)


class FrozenDatetime(_dt.datetime, metaclass=_FrozenMeta):
    _real = _dt.datetime

    @classmethod
    def now(cls, tz=None):
        CALLERS.add(_caller())
        return FROZEN_NOW.astimezone(tz) if tz is not None else FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def utcnow(cls):
        CALLERS.add(_caller())
        return FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def today(cls):
        CALLERS.add(_caller())
        return FROZEN_NOW.replace(tzinfo=None)


class FrozenDate(_dt.date, metaclass=_FrozenMeta):
    _real = _dt.date

    @classmethod
    def today(cls):
        CALLERS.add(_caller())
        return FROZEN_NOW.date()


def freeze(monkeypatch, modules) -> None:
    """Replace every module-level alias of datetime.datetime, datetime.date and the
    datetime module itself in ``modules`` (``import datetime as dt`` included)."""
    proxy = types.ModuleType("datetime")
    proxy.__dict__.update(vars(_dt))
    proxy.datetime, proxy.date = FrozenDatetime, FrozenDate
    swaps = {id(_dt.datetime): FrozenDatetime, id(_dt.date): FrozenDate, id(_dt): proxy}
    for module in modules:
        for name, value in list(vars(module).items()):
            if id(value) in swaps:
                monkeypatch.setattr(module, name, swaps[id(value)])


# --- JSON pointers ---------------------------------------------------------

def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.json"


def resolve(payload, pointer: str):
    node = payload
    for part in pointer.split("/")[1:]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _set(payload, pointer: str, value) -> None:
    *parents, last = pointer.split("/")[1:]
    node = resolve(payload, "/" + "/".join(parents)) if parents else payload
    node[int(last) if isinstance(node, list) else last] = value


def _mask_keys(node) -> None:
    if isinstance(node, dict):
        for key in node:
            if key in VOLATILE_KEYS:
                node[key] = MASK
            else:
                _mask_keys(node[key])
    elif isinstance(node, list):
        for item in node:
            _mask_keys(item)


def mask(payload, pointers=()):
    """A deep copy with VOLATILE_KEYS and the given money pointers replaced by MASK."""
    out = copy.deepcopy(payload)
    _mask_keys(out)
    for pointer in pointers:
        _set(out, pointer, MASK)
    return out


def diff_pointers(a, b, prefix: str = "") -> set[str]:
    """Pointers of the leaves where ``a`` and ``b`` differ (a whole list if its length does)."""
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return set().union(*(diff_pointers(a[k], b[k], f"{prefix}/{k}") for k in a))
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return set().union(*(diff_pointers(x, y, f"{prefix}/{i}") for i, (x, y) in enumerate(zip(a, b))))
    return set() if a == b else {prefix}
```

- [ ] **Step 2: Add the fixtures to `tests/admin_perf/conftest.py`**

Append to V205-2's conftest (add `import importlib`, `import json`, `import sys`, `import types` at the top):

```python
from tests.store_seed import seed_store


@pytest.fixture
def logged_in(client):
    """Session login, as tests/admin/test_api_v1_dashboard.py:96-104."""
    from swingbot.admin import app as admin_module
    response = client.post("/api/v1/session", json={"username": admin_module.ADMIN_USERNAME,
                                                   "password": admin_module.ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


@pytest.fixture
def frozen_clock(admin_app, monkeypatch):
    """golden_book.CLOCK_MODULES read FROZEN_NOW (after admin_app's module reloads)."""
    from tests.admin_perf import golden_book as gb
    gb.freeze(monkeypatch, [importlib.import_module(name) for name in gb.CLOCK_MODULES])


@pytest.fixture
def probe_clock(admin_app, monkeypatch):
    """Every loaded swingbot module frozen, recording its clock reads in gb.CALLERS."""
    from tests.admin_perf import golden_book as gb
    gb.freeze(monkeypatch, [m for n, m in list(sys.modules.items()) if n.startswith("swingbot.") and m])
    gb.CALLERS.clear()


@pytest.fixture
def golden_seed(admin_app, tmp_path, monkeypatch):
    """The golden book in the stores, and every outside read pinned to it."""
    import swingbot.admin.dashboard as dash
    from swingbot.admin.api_v1 import risk
    from swingbot.core.analytics import snapshots
    from swingbot.core.marketdata import data, data_refresh, data_store, fx
    from tests.admin_perf import golden_book as gb

    snapshot = tmp_path / "analytics_snapshot.json"
    monkeypatch.setattr(snapshots, "DEFAULT_PATH", str(snapshot))
    snapshot.write_text(json.dumps(snapshots.build_snapshot([], 10000.0, [])), encoding="utf-8")
    seed_store("plans", gb.plans())
    seed_store("trades", gb.trades())
    monkeypatch.setattr(fx, "account_currency_code", lambda: gb.ACCOUNT_CODE)
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker, **_kw: gb.QUOTES.get(str(ticker).upper()))
    monkeypatch.setattr(fx, "_quote_codes", {})
    frames: dict = {}
    monkeypatch.setattr(data_refresh, "refresh_symbol", lambda *a, **k: {"status": "fresh"})
    monkeypatch.setattr(data_store, "load_normalized", lambda symbol, interval, *a, **k: frames.get(symbol))
    monkeypatch.setattr(dash, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(dash, "get_current_price", lambda ticker: gb.PRICES.get(ticker))
    monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
    monkeypatch.setattr(data, "get_current_price_detail",
                        lambda t: data.PriceQuote(gb.PRICES[t], False) if t in gb.PRICES else None)
    for name, value in (("get_daily_data", None), ("get_daily_data_batch", {}), ("get_quote_batch", {})):
        monkeypatch.setattr(data, name, lambda *a, _value=value, **k: _value, raising=False)

    def set_fx(scale: float = 1.0) -> None:
        """Pin every FX rate to FX_CLOSES x scale and drop the process caches holding the old ones."""
        frames.clear()
        frames.update(gb.bars())
        frames.update(gb.fx_frames(scale))
        monkeypatch.setattr(fx, "_frames", {})
        risk._invalidate_cache()

    set_fx(1.0)
    yield types.SimpleNamespace(set_fx=set_fx)
    risk._invalidate_cache()
```

- [ ] **Step 3: Write the failing tests**

Create `tests/admin_perf/test_golden_endpoints.py`:

```python
"""v205 V205-4/V205-4b: the eight profiled endpoints against goldens frozen from pre-v205 code.

V205-4 pins the book and the clock; V205-4b appends the golden and money tests.
Layer 1's refactors (V205-7..V205-10) must pass these unchanged."""
from datetime import date, datetime, timezone

import pytest

from tests.admin_perf import golden_book as gb

NAMES = list(gb.ENDPOINTS)


def _get(client, name):
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:300])
    return response.get_json()


@pytest.mark.parametrize("name", NAMES)
def test_every_endpoint_answers_on_the_golden_book(name, golden_seed, frozen_clock, logged_in):
    assert _get(logged_in, name) is not None


@pytest.mark.parametrize("name", NAMES)
def test_clock_modules_cover_every_clock_read(name, golden_seed, probe_clock, logged_in):
    gb.CALLERS.clear()                                  # the login above read the clock too
    _get(logged_in, name)
    readers = {caller for caller in gb.CALLERS if caller.startswith("swingbot.")}
    assert readers <= set(gb.CLOCK_MODULES), sorted(readers - set(gb.CLOCK_MODULES))


def test_the_frozen_clock_keeps_isinstance_working():
    assert isinstance(datetime(2026, 1, 1), gb.FrozenDatetime)
    assert isinstance(gb.FrozenDate.today(), date) and gb.FrozenDate.today() == date(2026, 11, 4)
    assert gb.FrozenDatetime.now(timezone.utc) == gb.FROZEN_NOW


def test_the_scale_out_trade_expands_into_two_dated_legs():
    from swingbot.core.tracking.performance import expand_realized_legs
    legs = expand_realized_legs(gb.trades()[3])
    assert [(r["closed_at"], r["realized_pnl_amount"]) for r in legs] == [
        ("2026-10-29T15:00:00+00:00", 50.0), ("2026-11-02T15:00:00+00:00", 20.0)]


def test_mask_and_diff_pointers():
    payload = {"items": [{"id": "x", "amount": 1.0}], "total": 2.0}
    assert gb.mask(payload, ["/items/0/amount"]) == {"items": [{"id": "x", "amount": gb.MASK}], "total": 2.0}
    assert gb.mask(payload) == payload and gb.mask(payload) is not payload
    assert gb.diff_pointers(payload, {"items": [{"id": "x", "amount": 3.0}], "total": 2.0}) == {"/items/0/amount"}
    assert gb.diff_pointers([1], [1, 2]) == {""}
```

- [ ] **Step 4: Run them and settle `CLOCK_MODULES`**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db`, port 56789).

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`

A failing `test_every_endpoint_answers_on_the_golden_book[<name>]` prints the body: a 500 from an unpinned outside read (a network fetch, a cache) is pinned in `golden_seed`, never by changing `swingbot/`. A failing `test_clock_modules_cover_every_clock_read[<name>]` names the missing modules: append each to `CLOCK_MODULES` (keep it sorted) and re-run. `swingbot.core.marketdata.fx_convert` must **not** appear today (every seeded close has a stamp; open amounts pass `date.today()` from `api_v1/dashboard.py:320`). If it does, stop and report: V205-16's contract assumes it is absent.

Expected finally: `19 passed` (8 + 8 + 3), `0 failed`. `git -C <wt> diff --stat -- swingbot/` must be empty for this task.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add tests/admin_perf/golden_book.py tests/admin_perf/conftest.py tests/admin_perf/test_golden_endpoints.py
git -C <wt> commit -m "test(admin): golden book, frozen clock and endpoint fixtures (v205 V205-4)"
```

