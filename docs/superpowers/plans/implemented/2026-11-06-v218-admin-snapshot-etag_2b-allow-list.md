# v218 — Part 2b: the allow-list and the ETag behaviour tests (V218-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 3 (P3-c), § Error handling, § Testing.
**Index:** [`2026-11-06-v218-admin-snapshot-etag_0-index.md`](2026-11-06-v218-admin-snapshot-etag_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, `## Task ledger` and `## Handoff` live there and bind every task below.

Split from Part 2 (`2026-11-06-v218-admin-snapshot-etag_2-conditional.md`) at the 1500-line cap. Worktree for every task: `.claude/worktrees/2026-11-06-v218-admin-snapshot-etag` (branch of the same name). Paths below are relative to it.

Symbols this part consumes, created earlier (verify with `git grep -n` before starting):
`conditional.CONDITIONAL_ATTR / CACHE_CONTROL` (V218-8), `build_identity.build_version()` (V218-7),
`store_generation.bump() / generation() / set_connected()` (V218-2), the settings bump inside `config.reload()` (V218-2),
fixture `snapshot_on` (V218-5), `trades.closed_only_query` and the `"trades"` route key (V218-10b),
`CLOSED`, `UTC` and fixtures `refresher_on`, `closed_page` in `tests/admin_perf/test_trades_conditional_audit.py` (V218-10),
the drop verdicts for `/calendar/pnl`, `/calendar/pnl/day` and the sparklines route (V218-11, V218-12).

# Phase P3-c — the allow-list, pinned

### Task V218-13: Allow-list exact-set test and the ETag behaviour tests

**Model:** sonnet — test-only work on a pinned pattern (`test_read_scope_routes.py`), with every case and its fixtures given.

**Files:**
- Create: `tests/admin_perf/test_conditional_routes.py`

**Interfaces:**
- Consumes: `conditional.CONDITIONAL_ATTR`, `conditional.CACHE_CONTROL` (V218-8); `build_identity.build_version` (V218-7, patched); `store_generation.bump(concern)`, `generation(concern)`, `set_connected(flag)` (V218-2); the `settings` bump inside `config.reload()` when `_apply_env()` reports a change (V218-2); `CLOSED`, `UTC`, fixtures `refresher_on` and `closed_page` (V218-10); route key `"trades"` on `api_v1.list_trades` (V218-10b); the verdicts of V218-11 and V218-12 (both calendar routes and the sparklines route dropped). Existing: `_api_rules()` and `_WRITES` (`tests/admin_perf/test_read_scope_routes.py:20-28`), `READ_SCOPE_ATTR`, `seed_store` (`tests/store_seed.py`), `gb._trade(...)` and `gb.FROZEN_NOW` (`tests/admin_perf/golden_book.py`), `VIEWER_USERNAME` / `VIEWER_PASSWORD` (`tests/admin/conftest.py:198-199`), `admin_users_repo().create_user` and `principals.hash_password` (as `viewer_client` uses them), `config._env_signature`, `config._load_dotenv_file`, `config._apply_env`, `config._DOTENV_LOADED`, `config._DOTENV_FROM_CANONICAL_PATH` (`swingbot/config.py:1828-1862`).
- Produces: `CONDITIONAL = {"api_v1.list_trades"}` and `ROUTE_KEYS = {"api_v1.list_trades": "trades"}`. This is the union of the audits: V218-11 and V218-12 dropped their routes. If either was admitted after all, add its endpoint and route key here, as its task report states.

What the behaviour tests prove, all on `/api/v1/trades?status=CLOSED` with the golden book, the snapshot vouched for, the refresher on and the frozen clock at 12:00 UTC on 4 November (06:00 Berlin has passed, so the ET and Berlin dates agree and the shape is admitted):
- a repeat with the tag gets a bodiless 304 carrying the same `ETag`, `Cache-Control: private, no-cache`, and `snap;desc=hit` (a request that only read versions reports hit; index Handoff note);
- a trade write, a journal write, a NOTIFY-only generation bump (the stamp-gap case: versions unchanged), a Berlin-midnight crossing, the next admitted Berlin day, a new build, and a `.env` change picked up by `auto_reload_if_changed` each give a 200;
- the switch off, a disconnected listener and `X-Swingbot-Fresh: 1` each give a 200 with no `ETag`, even against `If-None-Match: *`;
- an unauthenticated request (401), unfiltered `/trades`, `status=open` and `/dashboard` carry no `ETag`;
- a viewer and the admin get different tags.

Midnight: the golden book closed `golden-t1`, `golden-t2` and `golden-t3` on Berlin 3 November (V218-5's note), so the crossing is 2026-11-03 22:30 UTC (23:30 Berlin, 17:30 ET) → 23:30 UTC (00:30 Berlin 4 Nov, 18:30 ET 3 Nov). After the crossing the ET date is still 3 November, so V218-10b's shape is not admitted: the response is a 200 **without** a tag, with `today` recomputed. A second test covers a crossing where both sides are admitted: 2026-11-04 22:30 UTC (23:30 Berlin, 17:30 ET 4 Nov) → 2026-11-05 05:30 UTC (06:30 Berlin, 00:30 ET 5 Nov). The Berlin date in the tag moves, so the tag does too.

- [ ] **Step 1: Write the tests**

Tests reach Postgres: run `/replicate-prod-db` once per session first, unless a sibling task in this session already did.

Create `tests/admin_perf/test_conditional_routes.py`:

```python
"""v218 V218-13: exactly the audited views answer 304, and how their ETag behaves (v206 P3-c).

The allow-list is the union of the route audits (V218-10..12, v206
`### Plan 3 route audits (V218-10..12)`): /trades in its closed-only shape.
Every other view keeps Cache-Control: no-store. The behaviour tests run the
admitted shape on the golden book, snapshot vouched for, refresher on."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.admin import build_identity
from swingbot.admin.api_v1 import conditional as cond
from swingbot.admin.api_v1.read_scope import READ_SCOPE_ATTR
from swingbot.core.infra import store_generation
from tests.admin_perf import golden_book as gb
from tests.admin_perf.test_read_scope_routes import _WRITES, _api_rules
from tests.admin_perf.test_trades_conditional_audit import (  # noqa: F401  (fixtures)
    CLOSED, UTC, closed_page, refresher_on)
from tests.store_seed import seed_store

CONDITIONAL = {"api_v1.list_trades"}
ROUTE_KEYS = {"api_v1.list_trades": "trades"}
EXCLUDED = ("api_v1.dashboard", "api_v1.get_live", "api_v1.calendar_pnl", "api_v1.calendar_pnl_day",
            "api_v1.calendar_pnl_day_sparklines")
_REAL_AUTO_RELOAD = config.auto_reload_if_changed


def _tag(response) -> str:
    assert response.status_code == 200, response.get_data(as_text=True)
    tag = response.headers.get("ETag")
    assert tag and tag.startswith('W/"'), dict(response.headers)
    return tag


def _again(client, tag: str, path: str = CLOSED, **headers):
    return client.get(path, headers={"If-None-Match": tag, **headers})


# --- which views carry it ----------------------------------------------------

def test_exactly_the_audited_views_are_conditional(admin_app):
    marked = {rule.endpoint: getattr(view, cond.CONDITIONAL_ATTR)
              for rule, view in _api_rules() if hasattr(view, cond.CONDITIONAL_ATTR)}
    assert marked == ROUTE_KEYS
    assert set(marked) == CONDITIONAL
    assert len(set(marked.values())) == len(marked), "two views share a route key"


def test_a_conditional_view_is_a_read_scoped_get(admin_app):
    for rule, view in _api_rules():
        if rule.endpoint in CONDITIONAL:
            assert not (rule.methods & _WRITES), (rule.rule, rule.methods)
            assert getattr(view, READ_SCOPE_ATTR, False) is True, rule.rule


@pytest.mark.parametrize("endpoint", EXCLUDED)
def test_the_spec_and_audit_exclusions_stay_off(admin_app, endpoint):
    assert not hasattr(admin_app.view_functions[endpoint], cond.CONDITIONAL_ATTR)


# --- the admitted shape: 304 only while nothing changed ----------------------

def test_a_repeat_is_a_bodiless_304(closed_page):
    tag = _tag(closed_page.get(CLOSED))
    response = _again(closed_page, tag)
    assert response.status_code == 304 and response.get_data() == b""
    assert response.headers["ETag"] == tag
    assert response.headers["Cache-Control"] == cond.CACHE_CONTROL
    assert response.headers["Server-Timing"].endswith("snap;desc=hit")


def test_a_trade_write_gives_a_200_with_the_new_row(closed_page):
    tag = _tag(closed_page.get(CLOSED))
    seed_store("trades", [gb._trade("golden-t7-v218", "AAPL", status="win", entry=100.0, shares=1,
                                    closed_at="2026-11-04T10:00:00+00:00", exit_price=101.0, pnl=1.0)])
    response = _again(closed_page, tag)
    assert _tag(response) != tag
    assert "golden-t7-v218" in {row["id"] for row in response.get_json()["items"]}


def test_a_journal_note_gives_a_200_with_has_note(closed_page):
    tag = _tag(closed_page.get(CLOSED))
    seed_store("journal", [{"created_at": "2026-11-04T10:00:00+00:00", "trade_id": "golden-t1-sap-win",
                            "ticker": "SAP.DE", "strategy": "S/R Confluence", "outcome": "win",
                            "note": "v218 lesson", "tags": []}])
    response = _again(closed_page, tag)
    assert _tag(response) != tag
    rows = {row["id"]: row for row in response.get_json()["items"]}
    assert rows["golden-t1-sap-win"]["has_note"] is True


@pytest.mark.parametrize("concern", ["trades", "journal"])
def test_a_notify_with_unchanged_versions_still_gives_a_200(closed_page, concern):
    tag = _tag(closed_page.get(CLOSED))
    store_generation.bump(concern)                 # what the snapshot listener does on a NOTIFY
    assert _tag(_again(closed_page, tag)) != tag


def test_a_berlin_midnight_crossing_gives_a_200_with_today_recomputed(closed_page, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 3, 22, 30, tzinfo=UTC))
    before = closed_page.get(CLOSED)
    tag = _tag(before)
    assert {r["id"] for r in before.get_json()["items"] if r["today"]} == {
        "golden-t1-sap-win", "golden-t2-usd-win", "golden-t3-usd-midnight"}
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 3, 23, 30, tzinfo=UTC))
    after = _again(closed_page, tag)
    assert after.status_code == 200
    assert "ETag" not in after.headers             # 00:30 Berlin, still 3 Nov in ET: not admitted
    assert not any(row["today"] for row in after.get_json()["items"])


def test_the_next_admitted_berlin_day_gets_a_new_tag(closed_page, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 4, 22, 30, tzinfo=UTC))
    tag = _tag(closed_page.get(CLOSED))
    monkeypatch.setattr(gb, "FROZEN_NOW", dt.datetime(2026, 11, 5, 5, 30, tzinfo=UTC))
    assert _tag(_again(closed_page, tag)) != tag


def test_a_new_build_gives_a_200(closed_page, monkeypatch):
    tag = _tag(closed_page.get(CLOSED))
    monkeypatch.setattr(build_identity, "build_version", lambda: "ffffffffffffffff|swing-bot:next")
    assert _tag(_again(closed_page, tag)) != tag


def test_an_env_change_picked_up_by_auto_reload_gives_a_200(closed_page, monkeypatch):
    tag = _tag(closed_page.get(CLOSED))
    # reload() reassigns these module globals with `global`; register them for restore.
    for name in ("_DOTENV_LOADED", "_DOTENV_FROM_CANONICAL_PATH", "_ENV_MTIME"):
        monkeypatch.setattr(config, name, getattr(config, name))
    monkeypatch.setattr(config, "auto_reload_if_changed", _REAL_AUTO_RELOAD)  # undo refresher_on's no-op
    monkeypatch.setattr(config, "_env_signature", lambda: ("v218-edited", 1))
    monkeypatch.setattr(config, "_load_dotenv_file", lambda: (True, False))
    monkeypatch.setattr(config, "_apply_env", lambda: {"ADMIN_SLOW_REQUEST_MS": (2000, 2500)})
    settings_before = store_generation.generation("settings")
    response = _again(closed_page, tag)
    assert store_generation.generation("settings") == settings_before + 1
    assert _tag(response) != tag


# --- no tag at all --------------------------------------------------------------

@pytest.mark.parametrize("setup", ["switch_off", "disconnected", "fresh"])
def test_a_bypassed_request_carries_no_tag(closed_page, monkeypatch, setup):
    headers = {"If-None-Match": "*"}
    if setup == "switch_off":
        monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off")
    elif setup == "disconnected":
        store_generation.set_connected(False)
    else:
        headers["X-Swingbot-Fresh"] = "1"
    response = closed_page.get(CLOSED, headers=headers)
    assert response.status_code == 200             # '*' would have been a 304 had a tag been computed
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_an_unauthenticated_request_gets_a_401_without_a_tag(closed_page, admin_app):
    response = admin_app.test_client().get(CLOSED, headers={"If-None-Match": "*"})
    assert response.status_code == 401
    assert "ETag" not in response.headers


@pytest.mark.parametrize("path", ["/api/v1/trades", "/api/v1/trades?status=open", "/api/v1/dashboard"])
def test_excluded_shapes_and_routes_carry_no_tag(closed_page, path):
    response = closed_page.get(path, headers={"If-None-Match": "*"})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_a_viewer_and_the_admin_get_different_tags(closed_page):
    from swingbot.admin import principals
    from swingbot.core.db.repositories.admin_users import admin_users_repo
    from tests.admin.conftest import VIEWER_PASSWORD, VIEWER_USERNAME
    admin_tag = _tag(closed_page.get(CLOSED))
    admin_users_repo().create_user(VIEWER_USERNAME, principals.hash_password(VIEWER_PASSWORD))
    login = closed_page.post("/api/v1/session",
                             json={"username": VIEWER_USERNAME, "password": VIEWER_PASSWORD})
    assert login.status_code == 200, login.get_json()
    viewer = _again(closed_page, admin_tag)
    assert _tag(viewer) != admin_tag               # the admin's tag never answers a viewer with 304
```

Notes for the implementer:
- `seed_store` upserts, so seeding one new trade or one journal entry leaves the golden book in place and moves `TradeRepository.version()` / `JournalRepository.version()`. The NOTIFY-only test moves the generation alone, which is the stamp-gap case V218-1 recorded.
- In tests the snapshot listener is never started (`current_app.testing`), so `closed_page`'s `snapshot_on` is what sets `connected()`. The disconnected case clears it directly.
- `_REAL_AUTO_RELOAD` is captured at import, before any fixture patches `config.auto_reload_if_changed`. The `.env` test patches only the seams `reload()` reads (`_env_signature`, `_load_dotenv_file`, `_apply_env`), so the real `auto_reload_if_changed` → `reload()` → settings bump path runs inside the admin's `before_request`, before the tag is computed.
- `admin_app` already restores `_ENV_MTIME`. The loop re-registers it together with the two dotenv flags that `reload()` also reassigns, so no later test in the worker inherits them.

- [ ] **Step 2: Run the tests**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_conditional_routes.py`
Expected: PASS. Every piece of production code exists (V218-2..V218-10b), so there is no red phase. This task pins the allow-list and the behaviour end to end.

If a test fails, debug it with `python -m pytest tests/admin_perf/test_conditional_routes.py::<test> -v` and decide which side is wrong:
- `test_exactly_the_audited_views_are_conditional` failing means a view carries the decorator without an audit, or an admitted view is missing. The fix is the decorator, never the expected set, unless an audit task admitted the route.
- A behaviour test getting a 304 where it expects a 200 is a stale-body bug in `conditional.py` or `closed_only_query`. Fix the code, re-run the file, and name the fix in the task report.
- `test_excluded_shapes_and_routes_carry_no_tag` failing on a non-200 for `/api/v1/dashboard` or unfiltered `/trades` with the refresher on is a fixture gap, not an ETag bug. Report it with the response body rather than dropping the case.

Then confirm the neighbours still pass:
- `python scripts/dev/testrun.py file tests/admin_perf/test_read_scope_routes.py` (expected PASS)
- `python scripts/dev/testrun.py file tests/admin_perf/test_trades_conditional_audit.py` (expected PASS)
- `python scripts/dev/testrun.py suite admin-perf` (expected `0 failed`, `0 xfailed`: the whole suite this plan grew, still a narrow run)

- [ ] **Step 3: Commit**

```bash
git add tests/admin_perf/test_conditional_routes.py
git commit -m "test(admin): conditional allow-list pinned to /trades closed-only, ETag behaviour end to end"
```
