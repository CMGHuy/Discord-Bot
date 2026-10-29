# v202 UI shell cockpit, part 1: `/live` endpoint and routes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md)
**Index:** [`_0-index.md`](2026-10-29-v202-ui-shell-cockpit_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract (`open_heat_state`, the `/live` payload, the event row, the nav model) live there and bind every task below.

Part scope: V202-1 … V202-4. The server half of the dock (`GET /api/v1/live`, its activity feed, the shared heat function) and the route table (new section paths, redirects with query and fragment kept, the server allow-list). Nothing in this part touches the shell's markup; parts 2–5 do.

`<wt>` is the implementation worktree's absolute path. Every DB-backed test needs the shared `swing-db` replica (`/replicate-prod-db`) before its first run. The version bump is not a task of this part.

# Phase 1: The `/live` endpoint

### Task V202-1: `GET /api/v1/live` heat section; shared `open_heat_state`; `live-api` suite

**Model:** opus — the one heat definition two pages must share: a behaviour-preserving refactor of the Risk collector, plus a new DB-only endpoint whose failures must never read as zero exposure.

**Files:**
- Modify: `swingbot/core/edge/portfolio_state.py` (`collect_portfolio_state`, new `open_heat_state`, around lines 193-225)
- Create: `swingbot/admin/api_v1/live.py`
- Modify: `swingbot/admin/api_v1/__init__.py:208-210` (the `register()` import tuple)
- Modify: `tests/suites.toml` (new `[suites.live-api]`)
- Create: `tests/live_api/__init__.py`
- Create: `tests/live_api/conftest.py`
- Create: `tests/live_api/test_live_heat.py`
- Create: `tests/live_api/test_live_endpoint.py`

**Interfaces:**
- Consumes: `heat.open_heat(open_trades, balance)` (`swingbot/core/edge/heat.py:23`); the existing `portfolio_state._observed`, `_dependent`, `_balance`, `_trades`, `_finite_heat` and `account_module.load_account_config`; `api_v1`, `error`, `iso` (`swingbot/admin/api_v1/__init__.py`); `require_auth`.
- Produces: `portfolio_state.open_heat_state(checked_at: str | None = None) -> dict`. Its keys are `open_trades`, `balance`, `open_heat`, `heat_cap` and `availability` (the heat status `{"state", "checked_at", "reason"}`), plus `positions_availability`, `balance_availability` and `account_config`, which `collect_portfolio_state` needs to keep its output unchanged. Also `live.DEFAULT_LIMIT = 8`, `live.MAX_LIMIT = 50`, `live.parse_limit(raw) -> int | None`, `live._section(as_of, values, reason=None) -> dict`, `live._guarded(name, read, empty, now) -> dict`, `live.heat_section(now) -> dict`, the constants `_AWAITING_EMPTY` and `_KILLSWITCH_EMPTY`, and the route `GET /api/v1/live`. Until V202-1b, `awaiting` and `killswitch` are `unavailable` with `reason == "not wired"`. Until V202-3, `events == []` and `events_meta == {"availability": "unavailable", "as_of", "missing": [], "reason": "not wired"}`. Suite `[suites.live-api]` with `paths = ["tests/live_api/"]`.

Run `/replicate-prod-db` first (shared `swing-db` container): every test here hits Postgres.

- [ ] **Step 1: Register the suite and the test package**

Add to `tests/suites.toml`, directly after `[suites.admin]`:

```toml
[suites.live-api]
description = "v202 GET /api/v1/live: heat, plans awaiting order, killswitch, activity feed"
paths = ["tests/live_api/"]
```

Create `tests/live_api/__init__.py` (empty) and `tests/live_api/conftest.py`:

```python
"""v202 `/api/v1/live` fixtures. The app and client are tests/admin's, imported
not copied (DATA_DIR isolation, module reloads, account balance 10,000); the
tests live here because the admin suite sits near max_tests."""
import pytest

from tests.admin.conftest import _clear_login_limiter, admin_app, auth, client  # noqa: F401

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every market-data entry point answers empty and records the call.
    `/live` must make none of them; `/risk` (heat-equality test) makes several."""
    calls: list[str] = []

    def recorder(name, value):
        def fake(*args, **kwargs):
            calls.append(name)
            return value
        return fake

    for name, value in (("get_daily_data", None), ("get_daily_data_batch", {}),
                        ("get_quote_batch", {})):
        monkeypatch.setattr(f"swingbot.core.marketdata.data.{name}",
                            recorder(name, value), raising=False)
    return calls


@pytest.fixture
def fresh_risk_cache():
    """`GET /risk` caches its collector for a few seconds; never reuse it."""
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1 import risk
    risk._invalidate_cache()
    yield
    risk._invalidate_cache()
```

- [ ] **Step 2: Write the failing heat tests**

Create `tests/live_api/test_live_heat.py`:

```python
"""v202 V202-1: the dock's heat is the Risk page's heat, in dollars and percent."""
import pytest

from tests.store_seed import seed_store


def _trade(trade_id, ticker, entry, stop, shares, plan_id=None):
    return {"id": trade_id, "plan_id": plan_id, "ticker": ticker, "status": "open",
            "direction": "bullish", "strategy": "VWAP", "horizon_key": "1m",
            "entry": entry, "stop_loss": stop, "take_profit": entry * 1.2,
            "shares": shares, "opened_at": "2026-10-28T12:00:00+00:00"}


#: 200 at risk each on the conftest's 10,000 balance: 2% + 2% = 4% open heat.
#: t2 is a resting order: its plan is still PENDING, but the trade row exists
#: from alert time, so heat counts it (spec section 5, "incl. resting orders").
BOOK = [_trade("t1", "AAPL", 100.0, 95.0, 40),
        _trade("t2", "MSFT", 50.0, 48.0, 100, plan_id="p-resting")]
NULLED = ("open_pct", "cap_pct", "utilisation_pct", "open_amount", "cap_amount",
          "headroom_pct", "headroom_amount", "balance")


@pytest.fixture(autouse=True)
def cap_six(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)


def _live_heat(client):
    response = client.get("/api/v1/live")
    assert response.status_code == 200
    return response.get_json()["heat"]


def test_open_heat_state_is_the_collector_figure(admin_app):
    from swingbot.core.edge.portfolio_state import collect_portfolio_state, open_heat_state
    seed_store("trades", BOOK)
    shared, full = open_heat_state(), collect_portfolio_state()

    assert shared["open_heat"] == pytest.approx(4.0)
    assert shared["open_heat"] == full["open_heat"]
    assert shared["heat_cap"] == full["heat_cap"] == 6.0
    assert shared["balance"] == full["balance"] == 10000.0
    assert shared["availability"]["state"] == "ok"
    assert full["availability"]["heat"] == shared["availability"] | {
        "checked_at": full["availability"]["heat"]["checked_at"]}
    assert sorted(t["id"] for t in shared["open_trades"]) == ["t1", "t2"]


def test_heat_equals_risk_page_for_same_book(logged_in, fresh_risk_cache):
    seed_store("trades", BOOK)
    risk = logged_in.get("/api/v1/risk").get_json()["heat"]
    live = _live_heat(logged_in)
    for key in ("open_pct", "cap_pct", "utilisation_pct"):
        assert live[key] == risk[key], key


def test_heat_in_dollars_and_percent(logged_in):
    seed_store("trades", BOOK)
    heat = _live_heat(logged_in)

    assert (heat["availability"], heat["reason"]) == ("ok", None)
    assert heat["open_pct"] == pytest.approx(4.0)
    assert heat["cap_pct"] == 6.0
    assert heat["utilisation_pct"] == 66.7
    assert (heat["open_amount"], heat["cap_amount"]) == (400.0, 600.0)
    assert (heat["headroom_pct"], heat["headroom_amount"]) == (2.0, 200.0)
    assert heat["balance"] == 10000.0
    assert heat["includes_resting"] is True


def test_heat_is_not_clamped_over_the_cap(logged_in):
    seed_store("trades", [_trade("t9", "NVDA", 100.0, 90.0, 80)])   # 800 at risk: 8%
    heat = _live_heat(logged_in)
    assert heat["utilisation_pct"] == 133.3
    assert (heat["headroom_pct"], heat["headroom_amount"]) == (-2.0, -200.0)


def test_an_empty_book_is_zero_heat_not_unavailable(logged_in):
    heat = _live_heat(logged_in)
    assert heat["availability"] == "ok"
    assert heat["open_pct"] == heat["utilisation_pct"] == heat["open_amount"] == 0.0


def test_unavailable_heat_keeps_every_key_null(logged_in, monkeypatch):
    from swingbot.core.edge import portfolio_state

    def broken(cfg):
        raise ValueError("invalid balance")
    monkeypatch.setattr(portfolio_state, "_balance", broken)
    heat = _live_heat(logged_in)

    assert (heat["availability"], heat["reason"]) == ("unavailable", "invalid_balance")
    assert all(heat[key] is None for key in NULLED)
    assert heat["includes_resting"] is True
```

- [ ] **Step 3: Write the failing endpoint tests**

Create `tests/live_api/test_live_endpoint.py` (V202-1b and V202-3 append to it; V202-1b adds the DB-only pin):

```python
"""v202: GET /api/v1/live -- auth, shape, ?limit=, sections, DB-only."""
# V202-1b adds `from tests.store_seed import seed_store` with its section tests.
import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape
SECTION = {"availability": str, "as_of": str, "reason": NULLABLE_STR}
HEAT = {**SECTION, "open_pct": NULLABLE_NUMBER, "cap_pct": NULLABLE_NUMBER,
        "utilisation_pct": NULLABLE_NUMBER, "open_amount": NULLABLE_NUMBER,
        "cap_amount": NULLABLE_NUMBER, "headroom_pct": NULLABLE_NUMBER,
        "headroom_amount": NULLABLE_NUMBER, "balance": NULLABLE_NUMBER,
        "includes_resting": bool}


def _live(client, query=""):
    response = client.get(f"/api/v1/live{query}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_requires_auth(client):
    assert_error(client.get("/api/v1/live"), "auth", 401)


def test_live_top_level_and_heat_shape(logged_in):
    body = _live(logged_in)
    assert_shape(body, {"heat": dict, "awaiting": dict, "killswitch": dict,
                        "events": list, "events_meta": dict})
    assert_shape(body["heat"], HEAT, where="heat")


@pytest.mark.parametrize("raw, expected", [
    (None, 8), ("", 8), ("1", 1), ("8", 8), ("50", 50), ("51", 50), ("1000", 50),
    ("0", None), ("-3", None), ("abc", None), ("2.5", None),
])
def test_parse_limit(admin_app, raw, expected):
    from swingbot.admin.api_v1 import live
    assert live.parse_limit(raw) == expected


@pytest.mark.parametrize("query", ["?limit=0", "?limit=-1", "?limit=abc", "?limit=2.5"])
def test_a_bad_limit_is_a_400(logged_in, query):
    assert_error(logged_in.get(f"/api/v1/live{query}"), "invalid", 400)


def test_events_are_not_wired_until_v202_3(logged_in):
    body = _live(logged_in)
    assert body["events"] == []
    assert body["events_meta"]["availability"] == "unavailable"
    assert body["events_meta"]["reason"] == "not wired"

```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/`
Expected: FAIL with `ImportError: cannot import name 'open_heat_state'` and 404s on `/api/v1/live`.

- [ ] **Step 5: Extract `open_heat_state` from `collect_portfolio_state`**

In `swingbot/core/edge/portfolio_state.py`, add `open_heat_state` above `collect_portfolio_state` and rewrite the collector's first half. The reads run in the same order as today (account, balance, trades, heat, then the rest), so the collector's output does not change:

```python
def open_heat_state(checked_at: str | None = None) -> dict:
    """DB-only open heat: the one definition the Risk page and `/live` read (v202).

    Open trades (resting orders included: a PENDING plan's trade row exists
    from alert time), the account balance and `heat.open_heat` over them.
    No prices, no daily frames: sector heat and clusters stay in
    `collect_portfolio_state`, which builds on this. `availability` is the
    heat status; the other two statuses and the raw account config are
    returned for the collector's own blocks.
    """
    from swingbot.core.edge import heat
    checked = checked_at or datetime.now(timezone.utc).isoformat()
    cfg, cfg_status = _observed(account_module.load_account_config, checked, "account_unavailable")
    balance, balance_status = _dependent(
        lambda: _balance(cfg), checked, "invalid_balance", [cfg_status])
    trades, positions_status = _observed(_trades, checked, "positions_unavailable")
    open_heat, heat_status = _dependent(
        lambda: _finite_heat(lambda: heat.open_heat(trades, balance)),
        checked, "heat_unavailable", [positions_status, balance_status])
    return {
        "open_trades": trades, "balance": balance, "open_heat": open_heat,
        "heat_cap": getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0),
        "availability": heat_status, "positions_availability": positions_status,
        "balance_availability": balance_status, "account_config": cfg,
    }


def collect_portfolio_state() -> dict:
    checked = datetime.now(timezone.utc).isoformat()
    base = open_heat_state(checked)
    trades, balance = base["open_trades"], base["balance"]
    positions_status = base["positions_availability"]
    dependencies = [positions_status, base["balance_availability"]]
    sectors, map_status = _observed(_load_sector_map, checked, "sector_map_unavailable")
    sector_heat, sector_status = _sector_state(
        trades, balance, sectors, checked, dependencies + [map_status])
    clusters, cluster_status = _clusters_state(
        trades, balance, sectors, checked, dependencies + [map_status])
    control, throttle_status = _observed(_throttle_state, checked, "throttle_unavailable")
    mult, paused = control if control is not None else (None, None)
    kill, kill_status = _observed(_kill_state, checked, "killswitch_unavailable")
    return {
        "open_trades": trades, "balance": balance,
        "open_heat": base["open_heat"], "heat_cap": base["heat_cap"],
        "sector_heat": sector_heat,
        "unmapped_count": _unmapped_count(trades or [], sectors or {}),
        "clusters": clusters, "throttle_mult": mult, "paused": paused,
        "kill": kill if kill is not None else {"on": None, "reason": None, "at": None},
        "growth": _growth_state(base["account_config"] or {}),
        "availability": {"positions": positions_status, "heat": base["availability"],
                         "sector_heat": sector_status, "clusters": cluster_status,
                         "throttle": throttle_status, "killswitch": kill_status},
    }
```

- [ ] **Step 6: Create `swingbot/admin/api_v1/live.py`**

```python
"""GET /api/v1/live: the shell's Live dock in one DB-only read (v202).

Heat is the Risk page's own definition (`portfolio_state.open_heat_state`).
Postgres only: no market-data provider, no `collect_portfolio_state`. Each
section catches its own failure and answers `availability: "unavailable"`
with its keys kept as null, so a failed read never passes for zero heat.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import jsonify, request

from swingbot.core.infra.swallowed import swallowed

from . import api_v1, error, iso
from .auth import require_auth

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 8
MAX_LIMIT = 50

_HEAT_KEYS = ("open_pct", "cap_pct", "utilisation_pct", "open_amount", "cap_amount",
              "headroom_pct", "headroom_amount", "balance")
_HEAT_EMPTY = {**{key: None for key in _HEAT_KEYS}, "includes_resting": True}
_AWAITING_EMPTY = {"count": None, "next_expiry": None}
_KILLSWITCH_EMPTY = {"engaged": None, "since": None, "detail": None}


def parse_limit(raw: str | None) -> int | None:
    """`?limit=`: absent -> DEFAULT_LIMIT, clamped to MAX_LIMIT; None when invalid."""
    if raw is None or raw == "":
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return min(value, MAX_LIMIT) if value >= 1 else None


def _section(as_of: str, values: dict, reason: str | None = None) -> dict:
    state = "ok" if reason is None else "unavailable"
    return {"availability": state, "as_of": as_of, "reason": reason, **values}


def _guarded(name: str, read, empty: dict, now: datetime) -> dict:
    """`read()`'s values as an ok section, or `<name>_unavailable` with `empty`."""
    as_of = iso(now)
    try:
        return _section(as_of, read())
    except Exception as exc:
        swallowed(log, f"ops.live.{name}", exc, level=logging.WARNING)
        return _section(as_of, empty, f"{name}_unavailable")


def _heat_figures(open_pct: float, cap_pct: float, balance: float) -> dict:
    """Dollars beside percent; utilisation and headroom deliberately unclamped."""
    cap = float(cap_pct)
    open_amount = round(open_pct / 100.0 * balance, 2)
    cap_amount = round(cap / 100.0 * balance, 2)
    return {
        "open_pct": open_pct, "cap_pct": cap,
        "utilisation_pct": round(open_pct / cap * 100.0, 1) if cap else None,
        "open_amount": open_amount, "cap_amount": cap_amount,
        "headroom_pct": round(cap - open_pct, 2),
        "headroom_amount": round(cap_amount - open_amount, 2),
        "balance": round(balance, 2), "includes_resting": True,
    }


def heat_section(now: datetime) -> dict:
    from swingbot.core.edge.portfolio_state import open_heat_state
    as_of = iso(now)
    try:
        state = open_heat_state(as_of)
    except Exception as exc:
        swallowed(log, "ops.live.heat", exc, level=logging.WARNING)
        return _section(as_of, _HEAT_EMPTY, "heat_unavailable")
    status = state.get("availability") or {}
    if status.get("state") != "ok":
        return _section(as_of, _HEAT_EMPTY, status.get("reason") or "heat_unavailable")
    return _section(as_of, _heat_figures(state["open_heat"], state["heat_cap"], state["balance"]))


def _sections(now: datetime) -> dict:
    """V202-1b replaces the two placeholders with the real sections."""
    as_of = iso(now)
    return {"heat": heat_section(now),
            "awaiting": _section(as_of, _AWAITING_EMPTY, "not wired"),
            "killswitch": _section(as_of, _KILLSWITCH_EMPTY, "not wired")}


def _events(limit: int, now: datetime) -> tuple[list, dict]:
    """Placeholder until V202-3 wires `live_events.collect_events`."""
    return [], {"availability": "unavailable", "as_of": iso(now), "missing": [],
                "reason": "not wired"}


@api_v1.route("/live", methods=["GET"])
@require_auth
def get_live():
    """The Live dock in one read; the shape is `LiveSnapshot` in models.ts."""
    limit = parse_limit(request.args.get("limit"))
    if limit is None:
        return error("invalid", "limit must be a whole number of at least 1.", 400)
    now = datetime.now(timezone.utc)
    events, meta = _events(limit, now)
    return jsonify({**_sections(now), "events": events, "events_meta": meta})
```

- [ ] **Step 7: Register the module**

In `swingbot/admin/api_v1/__init__.py` `register()`, add `live` to the import tuple in alphabetical order:

```python
    from . import (analytics, calendar, cancel_precision, dashboard, equity,  # noqa: F401
                   jobs, live, market, ops_health, reports, research, risk, session,
                   system, trade_commands, trades, versions, watchlist)  # (register routes)
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/`
Expected: PASS, `0 failed`.

Then the collector's own pins (the refactor changes nothing) and the suite registry, each:
`python <wt>/scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py`, `... file tests/edge/test_portfolio_state_sectors.py`, `... file tests/admin/test_api_v1_risk.py`, `... file tests/dev/test_suites.py`.
Expected: PASS each.

Complexity: `python <wt>/scripts/dev/complexity_gate.py`. Expected: no new violation.

- [ ] **Step 9: Commit**

```bash
git -C <wt> add swingbot/core/edge/portfolio_state.py swingbot/admin/api_v1/live.py swingbot/admin/api_v1/__init__.py tests/suites.toml tests/live_api/__init__.py tests/live_api/conftest.py tests/live_api/test_live_heat.py tests/live_api/test_live_endpoint.py
git -C <wt> commit -m "feat(v202): GET /api/v1/live heat section on a shared open_heat_state

open_heat_state() is the one DB-only heat definition; collect_portfolio_state
now builds on it, so the dock and the Risk page cannot disagree. New
live-api suite in tests/live_api/.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-1b: `/live` awaiting and killswitch sections; the DB-only pin

**Model:** sonnet — two guarded DB reads over one existing repository each, on the section helpers V202-1 built; the exact-expiry rule is spelled out below.

**Files:**
- Modify: `swingbot/admin/api_v1/live.py` (new section functions; `_sections` loses its placeholders)
- Modify: `tests/live_api/test_live_endpoint.py` (append)

**Interfaces:**
- Consumes (V202-1): `live._section`, `live._guarded`, `_AWAITING_EMPTY`, `_KILLSWITCH_EMPTY`, `heat_section`, `_sections`. Existing: `plans_repo().list_all(where=...)` (`swingbot/core/db/repositories/plans.py`), the `plans` table (`swingbot/core/db/schema.py`), `killswitch_repo().state() -> {"on", "reason", "at", "manual_release"}` (`swingbot/core/db/repositories/killswitch.py`), `session_close(d: date) -> time` and `US_MARKET_TZ` (`swingbot/core/market/session.py:229,12`).
- Produces (index ledger): `live.awaiting_section(now: datetime) -> dict` with `count` (plans with `status == "PENDING"`) and `next_expiry` (the soonest future `session_close(valid_session)` among PENDING plans that carry `valid_session`, ISO UTC, or `null`). `live.killswitch_section(now: datetime) -> dict` with `engaged`, `since` (`state()["at"]` only while engaged, else `null`) and `detail` (`state()["reason"]`). `live._utc_text(value) -> str | None`: a datetime or ISO string as ISO-8601 UTC. V202-3 replaces it with `live_events.iso_at`.

Run `/replicate-prod-db` first (shared `swing-db` container).

- [ ] **Step 1: Write the failing tests**

In `tests/live_api/test_live_endpoint.py`, replace the comment line `# V202-1b adds ...` with `from tests.store_seed import seed_store`, and add these two lines below `HEAT = {...}`:

```python
AWAITING = {**SECTION, "count": (int, type(None)), "next_expiry": NULLABLE_STR}
KILLSWITCH = {**SECTION, "engaged": (bool, type(None)), "since": NULLABLE_STR,
              "detail": NULLABLE_STR}
```

Append to the file:

```python
OPEN_TRADE = {"id": "t1", "ticker": "AAPL", "status": "open", "direction": "bullish",
              "strategy": "VWAP", "horizon_key": "1m", "entry": 100.0, "stop_loss": 95.0,
              "take_profit": 120.0, "shares": 10, "opened_at": "2026-10-28T12:00:00+00:00"}


def _plan(plan_id, status, valid_session=None):
    return {"plan_id": plan_id, "ticker": "MSFT", "strategy": "VWAP", "horizon_key": "1m",
            "status": status, "created_at": "2026-10-28T13:00:00+00:00",
            "valid_session": valid_session, "direction": "bullish",
            "entry_price": 418.5, "status_history": []}


def _boom():
    raise RuntimeError("db down")


def test_awaiting_and_killswitch_shape(logged_in):
    body = _live(logged_in)
    assert_shape(body["awaiting"], AWAITING, where="awaiting")
    assert_shape(body["killswitch"], KILLSWITCH, where="killswitch")


def test_awaiting_counts_pending_plans_and_the_soonest_exact_expiry(logged_in):
    seed_store("plans", [
        _plan("p1", "PENDING", "2030-01-17"),
        _plan("p2", "PENDING", "2030-01-15"),
        _plan("p3", "PENDING"),                  # bar-count expiry: no exact time, no guess
        _plan("p4", "PENDING", "2020-01-02"),    # already past: not the "next" expiry
        _plan("p5", "ACTIVE", "2030-01-14"),     # filled: not awaiting an order
        _plan("p6", "CANCELLED", "2030-01-14"),
    ])
    awaiting = _live(logged_in)["awaiting"]

    assert awaiting["availability"] == "ok"
    assert awaiting["count"] == 4
    assert awaiting["next_expiry"] == "2030-01-15T21:00:00+00:00"   # 16:00 ET close, EST


def test_awaiting_without_session_plans_has_no_expiry(logged_in):
    seed_store("plans", [_plan("p3", "PENDING")])
    awaiting = _live(logged_in)["awaiting"]
    assert (awaiting["count"], awaiting["next_expiry"]) == (1, None)


def test_awaiting_with_nothing_pending_is_zero_not_unavailable(logged_in):
    awaiting = _live(logged_in)["awaiting"]
    assert (awaiting["availability"], awaiting["count"], awaiting["next_expiry"]) == ("ok", 0, None)


def test_a_failed_plans_read_is_unavailable_not_zero(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", _boom)
    body = _live(logged_in)

    assert body["awaiting"]["availability"] == "unavailable"
    assert body["awaiting"]["reason"] == "awaiting_unavailable"
    assert body["awaiting"]["count"] is None
    assert body["heat"]["availability"] == "ok"
    assert body["killswitch"]["availability"] == "ok"


def test_killswitch_engaged_reports_since_and_detail(logged_in):
    seed_store("killswitch", {"on": True, "reason": "daily loss",
                              "at": "2026-10-29T07:31:00+00:00"})
    kill = _live(logged_in)["killswitch"]
    assert kill["availability"] == "ok"
    assert kill["engaged"] is True
    assert kill["since"] == "2026-10-29T07:31:00+00:00"
    assert kill["detail"] == "daily loss"


def test_a_released_killswitch_has_no_since(logged_in):
    """release() overwrites engaged_at: that time is never an engagement."""
    seed_store("killswitch", {"on": False, "reason": None, "manual_release": True,
                              "at": "2026-10-29T09:00:00+00:00"})
    kill = _live(logged_in)["killswitch"]
    assert kill["engaged"] is False
    assert kill["since"] is None


def test_no_killswitch_row_reads_the_configured_default(logged_in):
    from swingbot import config
    kill = _live(logged_in)["killswitch"]
    assert kill["engaged"] is bool(config.KILLSWITCH_DEFAULT_ON)
    assert kill["since"] is None


def test_a_failed_killswitch_read_is_unavailable(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.killswitch.killswitch_repo", _boom)
    kill = _live(logged_in)["killswitch"]
    assert (kill["availability"], kill["reason"]) == ("unavailable", "killswitch_unavailable")
    assert kill["engaged"] is None


def test_utc_text_normalises_offsets(admin_app):
    from datetime import datetime, timezone
    from swingbot.admin.api_v1 import live
    assert live._utc_text(None) is None
    assert live._utc_text("2026-10-29T09:31:00+02:00") == "2026-10-29T07:31:00+00:00"
    assert live._utc_text(datetime(2026, 10, 29, 7, 31, tzinfo=timezone.utc)) \
        == "2026-10-29T07:31:00+00:00"


def test_live_is_postgres_only(logged_in, no_network, monkeypatch):
    """Never a provider, never the slow Risk collector (spec section 5)."""
    collector = []
    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state",
                        lambda *a, **k: collector.append(1) or {})
    seed_store("trades", [OPEN_TRADE])
    seed_store("plans", [_plan("p1", "PENDING", "2030-01-15")])
    body = _live(logged_in)

    assert {body[s]["availability"] for s in ("heat", "awaiting", "killswitch")} == {"ok"}
    assert no_network == []
    assert collector == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/test_live_endpoint.py`
Expected: FAIL. The awaiting and killswitch sections are still `unavailable` with reason `"not wired"`, and `live._utc_text` does not exist yet.

- [ ] **Step 3: Implement the two sections**

In `swingbot/admin/api_v1/live.py`, change the datetime import to `from datetime import date, datetime, timezone`. Add these functions below `heat_section`:

```python
def _session_expiry(valid_session) -> datetime | None:
    """The NYSE close of a plan's `valid_session` day, in UTC; None if unparseable."""
    from swingbot.core.market.session import US_MARKET_TZ, session_close
    try:
        day = date.fromisoformat(str(valid_session)[:10])
    except ValueError:
        return None
    return datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ).astimezone(timezone.utc)


def _next_expiry(pending: list[dict], now: datetime) -> str | None:
    """Soonest future close among session-window plans only. Bar-count plans
    expire by the on-disk daily cache, which a DB-only read cannot know, so
    they contribute no guess (spec section 4.2)."""
    closes = [_session_expiry(p["valid_session"]) for p in pending if p.get("valid_session")]
    future = [close for close in closes if close is not None and close >= now]
    return iso(min(future)) if future else None


def _awaiting_values(now: datetime) -> dict:
    """A state count, not a since-last-visit badge: it drops only when a plan
    fills, expires or is cancelled."""
    from swingbot.core.db.repositories.plans import plans_repo
    from swingbot.core.db.schema import plans
    pending = plans_repo().list_all(where=plans.c.status == "PENDING")
    return {"count": len(pending), "next_expiry": _next_expiry(pending, now)}


def awaiting_section(now: datetime) -> dict:
    return _guarded("awaiting", lambda: _awaiting_values(now), _AWAITING_EMPTY, now)


def _utc_text(value) -> str | None:
    """A datetime or ISO string as ISO-8601 UTC; None stays None."""
    if value is None:
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return iso(moment)


def _killswitch_values() -> dict:
    """Latest state only: `release()` overwrites `engaged_at`, so `since` is
    reported only while engaged and is never read as an engagement time."""
    from swingbot.core.db.repositories.killswitch import killswitch_repo
    state = killswitch_repo().state()
    engaged = bool(state.get("on"))
    return {"engaged": engaged, "since": _utc_text(state.get("at")) if engaged else None,
            "detail": state.get("reason")}


def killswitch_section(now: datetime) -> dict:
    return _guarded("killswitch", _killswitch_values, _KILLSWITCH_EMPTY, now)
```

Replace `_sections` (the placeholders go):

```python
def _sections(now: datetime) -> dict:
    return {"heat": heat_section(now), "awaiting": awaiting_section(now),
            "killswitch": killswitch_section(now)}
```

Update the module docstring's first paragraph so it names the three sections: "Heat is the Risk page's own definition (`portfolio_state.open_heat_state`); plans awaiting an order and the killswitch are one guarded read each."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/`
Expected: PASS, `0 failed`.

Complexity: `python <wt>/scripts/dev/complexity_gate.py`. Expected: no new violation.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/live.py tests/live_api/test_live_endpoint.py
git -C <wt> commit -m "feat(v202): /live plans-awaiting-order and killswitch sections

PENDING count with an exact expiry only for valid_session plans; the
killswitch's latest state, with since only while engaged. Pins /live as
Postgres-only.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-2: Activity row builders for plans: `plan_alerted`, `paper_filled`, `tp1_hit`

**Model:** sonnet — pure functions over documented plan-doc keys with a fixed row contract; the one trap (`opened_at` is never a fill) is pinned by a test below.

**Files:**
- Create: `swingbot/admin/api_v1/live_events.py`
- Create: `tests/live_api/test_live_events_plans.py`

**Interfaces:**
- Consumes: `iso(value: datetime | None) -> str | None` (`swingbot/admin/api_v1/__init__.py:109`, naive is UTC). It also reads these plan-record keys (a `plans_repo()` row: promoted columns merged over `doc`): `plan_id`, `ticker`, `direction` (`"bullish"`/`"bearish"`), `created_at` (aware `datetime` from the column, or an ISO string), `entry_price` (the fill price once ACTIVE), `trigger_price`, `status_history` (list of `{"status", "reason", "at", ...}`, appended by `record_transition`, `swingbot/core/planning/plan_types.py:252`), and `legs_realized` (TP1 leg `{"fraction", "exit_price", "r", "reason": "tp1", "closed_at"}`, `plan_manager.py:1113,1553`; stop and scratch legs carry no `closed_at`).
- Produces (index ledger, final): `live_events.event_row(at, kind, text, tone, ref, pnl=None) -> dict`; `live_events.direction_word(direction: str | None) -> str`; `live_events.iso_at(value) -> str | None`; `live_events.tone_for(r: float | None) -> str`; `live_events.plan_alerted_rows(plans: list[dict]) -> list[dict]`; `live_events.paper_filled_rows(plans) -> list[dict]`; `live_events.tp1_hit_rows(plans, shares_by_plan: Mapping[str, float]) -> list[dict]`. Row shape: `{"at": ISO UTC str, "kind", "text", "tone", "ref": str | None, "pnl": {"r": float, "amount": float | None} | None}`; `text` never carries the P&L figure.

Every test here is pure (no rows seeded); the suite's shared fixtures still expect the `swing-db` replica to be up.

- [ ] **Step 1: Write the failing tests**

Create `tests/live_api/test_live_events_plans.py`:

```python
"""v202 V202-2: activity rows from plans -- alert, paper fill, TP1."""
from datetime import datetime, timezone

import pytest

from swingbot.admin.api_v1 import live_events as ev

ALERTED = "2026-10-29T08:00:00+00:00"


def _plan(**over):
    plan = {"plan_id": "p1", "ticker": "MSFT", "direction": "bullish",
            "created_at": ALERTED, "entry_price": 418.5, "status_history": [],
            "legs_realized": []}
    return {**plan, **over}


@pytest.mark.parametrize("raw, word", [
    ("bullish", "long"), ("bearish", "short"), ("Long", "long"), ("short", "short"),
    (None, ""), ("sideways", ""),
])
def test_direction_word(raw, word):
    assert ev.direction_word(raw) == word


@pytest.mark.parametrize("raw, expected", [
    (datetime(2026, 10, 29, 7, 31, tzinfo=timezone.utc), "2026-10-29T07:31:00+00:00"),
    (datetime(2026, 10, 29, 7, 31), "2026-10-29T07:31:00+00:00"),        # naive is UTC
    ("2026-10-29T09:31:00+02:00", "2026-10-29T07:31:00+00:00"),
    ("2026-10-29T07:31:00Z", "2026-10-29T07:31:00+00:00"),
    ("not a time", None), ("", None), (None, None), (17, None),
])
def test_iso_at(raw, expected):
    assert ev.iso_at(raw) == expected


def test_event_row_shape():
    row = ev.event_row(ALERTED, "trade_closed", "NVDA closed · TP2", "positive", 812,
                       {"r": 2.1, "amount": 441.0})
    assert row == {"at": ALERTED, "kind": "trade_closed", "text": "NVDA closed · TP2",
                   "tone": "positive", "ref": "812", "pnl": {"r": 2.1, "amount": 441.0}}
    assert ev.event_row(ALERTED, "killswitch", "Killswitch released", "neutral", None)["ref"] is None
    assert ev.event_row(ALERTED, "killswitch", "x", "neutral", None)["pnl"] is None


@pytest.mark.parametrize("r, tone", [(1.0, "positive"), (-0.4, "negative"), (0.0, "neutral"),
                                     (None, "neutral")])
def test_tone_for(r, tone):
    assert ev.tone_for(r) == tone


def test_plan_alerted_row():
    [row] = ev.plan_alerted_rows([_plan()])
    assert row == {"at": ALERTED, "kind": "plan_alerted",
                   "text": "Alert · MSFT long · entry 418.50", "tone": "info",
                   "ref": "p1", "pnl": None}


def test_plan_alerted_prefers_the_trigger_and_reads_a_datetime_column():
    plan = _plan(trigger_price=420.0, created_at=datetime(2026, 10, 29, 8, tzinfo=timezone.utc))
    [row] = ev.plan_alerted_rows([plan])
    assert row["text"] == "Alert · MSFT long · entry 420.00"
    assert row["at"] == ALERTED


def test_plan_alerted_without_price_or_time():
    assert ev.plan_alerted_rows([_plan(entry_price=None)])[0]["text"] == "Alert · MSFT long"
    assert ev.plan_alerted_rows([_plan(created_at=None)]) == []
    assert ev.plan_alerted_rows([]) == []


def test_paper_fill_is_the_first_active_transition():
    plan = _plan(ticker="XLE", direction="bearish", entry_price=92.1, status_history=[
        {"status": "PENDING", "reason": "created", "at": ALERTED},
        {"status": "ACTIVE", "reason": "stop_entry_fill", "at": "2026-10-29T13:35:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1", "at": "2026-10-29T15:00:00+00:00"},
        {"status": "ACTIVE", "reason": "late", "at": "2026-10-29T16:00:00+00:00"},
    ])
    [row] = ev.paper_filled_rows([plan])
    assert row == {"at": "2026-10-29T13:35:00+00:00", "kind": "paper_filled",
                   "text": "Paper fill · XLE short at 92.10", "tone": "info",
                   "ref": "p1", "pnl": None}


def test_opened_at_never_yields_a_fill():
    """trades.opened_at (and any opened_at on a record) is the alert time."""
    plan = _plan(opened_at="2026-10-29T08:00:00+00:00", status="PENDING",
                 status_history=[{"status": "PENDING", "at": ALERTED}])
    assert ev.paper_filled_rows([plan]) == []


def test_a_fill_without_a_time_yields_no_row():
    plan = _plan(status_history=[{"status": "ACTIVE", "reason": "limit_fill"}])
    assert ev.paper_filled_rows([plan]) == []
    assert ev.paper_filled_rows([_plan(status_history=None)]) == []


def _tp1_plan(**leg_over):
    leg = {"fraction": 0.5, "exit_price": 110.0, "r": 1.0, "reason": "tp1",
           "closed_at": "2026-10-29T14:10:00+00:00", **leg_over}
    return _plan(ticker="NVDA", entry_price=100.0, legs_realized=[leg])


def test_tp1_row_with_r_and_amount():
    [row] = ev.tp1_hit_rows([_tp1_plan()], {"p1": 42})
    assert row == {"at": "2026-10-29T14:10:00+00:00", "kind": "tp1_hit", "text": "TP1 · NVDA",
                   "tone": "positive", "ref": "p1", "pnl": {"r": 1.0, "amount": 210.0}}


def test_tp1_amount_on_a_short():
    plan = _plan(ticker="XLE", direction="bearish", entry_price=92.1, legs_realized=[
        {"fraction": 0.5, "exit_price": 90.1, "r": 0.8, "reason": "tp1",
         "closed_at": "2026-10-29T14:10:00+00:00"}])
    [row] = ev.tp1_hit_rows([plan], {"p1": 10})
    assert row["pnl"] == {"r": 0.8, "amount": 10.0}


def test_tp1_without_shares_keeps_r_and_drops_the_amount():
    [row] = ev.tp1_hit_rows([_tp1_plan()], {})
    assert row["pnl"] == {"r": 1.0, "amount": None}


def test_tp1_tone_follows_r():
    assert ev.tp1_hit_rows([_tp1_plan(r=-0.2)], {})[0]["tone"] == "negative"
    [no_r] = ev.tp1_hit_rows([_tp1_plan(r=None)], {})
    assert (no_r["tone"], no_r["pnl"]) == ("neutral", None)


def test_no_tp1_row_without_its_time_or_for_other_legs():
    assert ev.tp1_hit_rows([_tp1_plan(closed_at=None)], {"p1": 1}) == []
    assert ev.tp1_hit_rows([_tp1_plan(reason="stop")], {"p1": 1}) == []
    assert ev.tp1_hit_rows([_plan(legs_realized=None)], {}) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/test_live_events_plans.py`
Expected: FAIL with `ImportError: cannot import name 'live_events'`.

- [ ] **Step 3: Create `swingbot/admin/api_v1/live_events.py`**

```python
"""Activity rows for the Live dock (v202): one pure builder per event kind.

Every row is `event_row(...)`: `{"at", "kind", "text", "tone", "ref", "pnl"}`,
with `at` ISO-8601 UTC and `text` the line WITHOUT its P&L figure -- the SPA's
`activityLine` appends "+1.0R ($210) (paper, pre-cost)" from `pnl`.

What the sources can say (spec section 5): `trades.opened_at` is the alert
time, never a fill, so no builder reads it. The only fill is `paper_filled`,
the plan's first `status_history` entry with status ACTIVE, which is the
bot's simulated fill. A TP1 leg without `closed_at` (older plans) yields no
row rather than a guessed time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from . import iso

_DIRECTION_WORDS = {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}


def direction_word(direction: str | None) -> str:
    return _DIRECTION_WORDS.get(str(direction or "").strip().lower(), "")


def iso_at(value: Any) -> str | None:
    """A datetime or ISO string as ISO-8601 UTC; anything else is None."""
    if isinstance(value, datetime):
        return iso(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return iso(datetime.fromisoformat(value.strip()))
    except ValueError:
        return None


def event_row(at: str, kind: str, text: str, tone: str, ref: Any,
              pnl: dict | None = None) -> dict:
    return {"at": at, "kind": kind, "text": text, "tone": tone,
            "ref": None if ref is None else str(ref), "pnl": pnl}


def tone_for(r: float | None) -> str:
    if not r:
        return "neutral"
    return "positive" if r > 0 else "negative"


def _number(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _price(value: Any) -> str | None:
    number = _number(value)
    return None if number is None else f"{number:.2f}"


def _who(plan: Mapping) -> str:
    parts = (str(plan.get("ticker") or "?"), direction_word(plan.get("direction")))
    return " ".join(part for part in parts if part)


def _alert_text(plan: Mapping) -> str:
    trigger = plan.get("trigger_price")
    price = _price(trigger if trigger is not None else plan.get("entry_price"))
    return f"Alert · {_who(plan)} · entry {price}" if price else f"Alert · {_who(plan)}"


def plan_alerted_rows(plans: list[dict]) -> list[dict]:
    rows = []
    for plan in plans:
        at = iso_at(plan.get("created_at"))
        if at is not None:
            rows.append(event_row(at, "plan_alerted", _alert_text(plan), "info",
                                  plan.get("plan_id")))
    return rows


def _first_fill(plan: Mapping) -> Mapping | None:
    history = plan.get("status_history") or []
    return next((entry for entry in history
                 if isinstance(entry, Mapping) and entry.get("status") == "ACTIVE"), None)


def paper_filled_rows(plans: list[dict]) -> list[dict]:
    rows = []
    for plan in plans:
        fill = _first_fill(plan)
        at = iso_at(fill.get("at")) if fill else None
        if at is None:
            continue
        price = _price(plan.get("entry_price"))
        text = f"Paper fill · {_who(plan)}" + (f" at {price}" if price else "")
        rows.append(event_row(at, "paper_filled", text, "info", plan.get("plan_id")))
    return rows


def _tp1_leg(plan: Mapping) -> Mapping | None:
    legs = plan.get("legs_realized") or []
    return next((leg for leg in legs if isinstance(leg, Mapping)
                 and leg.get("reason") == "tp1" and leg.get("closed_at")), None)


def _leg_amount(plan: Mapping, leg: Mapping, shares: Any) -> float | None:
    """Price move x shares x leg fraction, the same convention as
    `TradeLog._settle_account_balance` uses for `realized_pnl_amount`."""
    try:
        sign = -1.0 if direction_word(plan.get("direction")) == "short" else 1.0
        move = (float(leg["exit_price"]) - float(plan["entry_price"])) * sign
        return round(move * float(shares) * float(leg.get("fraction") or 0.0), 2)
    except (KeyError, TypeError, ValueError):
        return None


def tp1_hit_rows(plans: list[dict], shares_by_plan: Mapping[str, float]) -> list[dict]:
    rows = []
    for plan in plans:
        leg = _tp1_leg(plan)
        at = iso_at(leg.get("closed_at")) if leg else None
        if at is None:
            continue
        r = _number(leg.get("r"))
        shares = shares_by_plan.get(str(plan.get("plan_id")))
        pnl = None if r is None else {"r": r, "amount": _leg_amount(plan, leg, shares)
                                      if shares else None}
        rows.append(event_row(at, "tp1_hit", f"TP1 · {plan.get('ticker') or '?'}",
                              tone_for(r), plan.get("plan_id"), pnl))
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/test_live_events_plans.py`
Expected: PASS, `0 failed`.

Complexity: `python <wt>/scripts/dev/complexity_gate.py`. Expected: no new violation (each builder is one loop with one guard).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/live_events.py tests/live_api/test_live_events_plans.py
git -C <wt> commit -m "feat(v202): live activity rows for plan alerts, paper fills and TP1

One pure builder per kind; the only fill is the plan's first ACTIVE
transition, labelled a paper fill, and opened_at is never read as one.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V202-3: Activity: `trade_closed`, `killswitch` builders; table-driven `collect_events`; wired into `/live`

**Model:** sonnet — two more pure builders plus a table-driven merge whose failure accounting is fully specified; the trap (a failed source must never look like a quiet day) is pinned by tests.

**Files:**
- Modify: `swingbot/admin/api_v1/live_events.py` (append)
- Modify: `swingbot/admin/api_v1/live.py` (`_events` wired; `_utc_text` replaced by `live_events.iso_at`)
- Modify: `tests/live_api/test_live_endpoint.py` (two V202-1/1b tests retired, listed in Step 5)
- Create: `tests/live_api/test_live_events_trades.py`
- Create: `tests/live_api/test_live_events_collect.py`

**Interfaces:**
- Consumes (V202-2): `event_row`, `iso_at`, `tone_for`, `plan_alerted_rows`, `paper_filled_rows`, `tp1_hit_rows`. (V202-1/1b): `live._events`, `live._utc_text`, `live.MAX_LIMIT`. Existing: `closed_r_multiple(t) -> float | None` (`swingbot/core/tracking/performance.py:333`, fraction-weighted leg `r`); `_json_record(row)` (`performance.py:615`, repo row to TradeLog shape: `id`, ISO `closed_at`); `trades_repo().closed_trades(limit=)` and `.open_trades()`; `plans_repo().list_all(order_by=, limit=)`; `killswitch_repo().state()`; `swallowed`.
- Produces (index ledger, final): `trade_closed_rows(trades: list[dict]) -> list[dict]`, `killswitch_rows(state: Mapping) -> list[dict]`, `@dataclass(frozen=True) EventKind(kind: str, source: str, build: Callable[[dict], list[dict]])`, `EVENT_KINDS: tuple[EventKind, ...]` (order: `plan_alerted`, `paper_filled`, `tp1_hit`, `trade_closed`, `killswitch`), `SOURCE_LOADERS: dict[str, Callable[[], Any]]` with keys `"plans"`, `"trades"`, `"killswitch"` and `"shares"`, and `collect_events(limit: int, *, loaders: Mapping[str, Callable[[], Any]] | None = None, now: datetime | None = None) -> tuple[list[dict], dict]`. Meta is exactly `{"availability": "ok" | "partial" | "unavailable", "as_of", "missing": [kind, ...]}`. `"shares"` is auxiliary: its failure only drops TP1 amounts, never a kind. `/live` now answers real `events` (newest first, `?limit=` long) and this meta.

Run `/replicate-prod-db` first (shared `swing-db` container): the collect tests' endpoint half hits Postgres.

- [ ] **Step 1: Write the failing builder tests**

Create `tests/live_api/test_live_events_trades.py`:

```python
"""v202 V202-3: activity rows from closed trades and the killswitch."""
from swingbot.admin.api_v1 import live_events as ev

CLOSED = "2026-10-29T15:20:00+00:00"


def _trade(**over):
    trade = {"id": "812", "ticker": "NVDA", "direction": "bullish", "status": "win",
             "entry": 100.0, "stop_loss": 95.0, "opened_at": "2026-10-20T08:00:00+00:00",
             "closed_at": CLOSED, "realized_pnl_amount": 441.0,
             "legs": [{"fraction": 0.5, "exit_price": 105.0, "r": 1.0, "reason": "tp1"},
                      {"fraction": 0.5, "exit_price": 116.0, "r": 3.2,
                       "reason": "tp1_runner_tp2"}]}
    return {**trade, **over}


def test_a_scaled_out_win():
    [row] = ev.trade_closed_rows([_trade()])
    assert row == {"at": CLOSED, "kind": "trade_closed", "text": "NVDA closed · TP2",
                   "tone": "positive", "ref": "812", "pnl": {"r": 2.1, "amount": 441.0}}


def test_a_single_exit_loss_without_an_amount():
    trade = _trade(ticker="AAPL", status="loss", legs=None, exit_price=95.0,
                   realized_pnl_amount=None)
    [row] = ev.trade_closed_rows([trade])
    assert row["text"] == "AAPL closed · loss"
    assert row["tone"] == "negative"
    assert row["pnl"] == {"r": -1.0, "amount": None}


def test_a_manual_close_has_no_r():
    trade = _trade(ticker="AAPL", status="closed", legs=None, close_reason="manual",
                   realized_pnl_amount=None)
    [row] = ev.trade_closed_rows([trade])
    assert row["text"] == "AAPL closed · manual"
    assert (row["tone"], row["pnl"]) == ("neutral", None)


def test_outcome_labels_from_the_last_leg():
    for reason, label in (("tp1_runner_be", "runner at floor"), ("tp1_runner_trail", "trailed"),
                          ("time_exit", "time exit"), ("scratch", "scratch"), ("loss", "stop")):
        legs = [{"fraction": 1.0, "exit_price": 100.0, "r": 0.0, "reason": reason}]
        assert ev.trade_closed_rows([_trade(legs=legs)])[0]["text"] == f"NVDA closed · {label}"


def test_open_trades_and_missing_times_yield_nothing():
    """opened_at is the alert time: an open trade never becomes a row."""
    assert ev.trade_closed_rows([_trade(status="open", closed_at=None)]) == []
    assert ev.trade_closed_rows([_trade(closed_at=None)]) == []
    assert ev.trade_closed_rows([]) == []


def test_killswitch_engaged_and_released_wording():
    on = {"on": True, "reason": "daily loss", "at": "2026-10-29T07:31:00+00:00"}
    off = {"on": False, "reason": None, "at": "2026-10-29T09:00:00+00:00", "manual_release": True}
    assert ev.killswitch_rows(on) == [{"at": "2026-10-29T07:31:00+00:00", "kind": "killswitch",
                                       "text": "Killswitch engaged", "tone": "warning",
                                       "ref": None, "pnl": None}]
    [released] = ev.killswitch_rows(off)
    assert (released["text"], released["tone"]) == ("Killswitch released", "neutral")


def test_a_killswitch_with_no_transition_yields_nothing():
    assert ev.killswitch_rows({"on": False, "reason": None, "at": None}) == []
    assert ev.killswitch_rows(None) == []
```

- [ ] **Step 2: Write the failing collect tests**

Create `tests/live_api/test_live_events_collect.py`:

```python
"""v202 V202-3: merge, sort, limit, and per-source failure of the activity feed."""
from datetime import datetime, timezone

import pytest

from swingbot.admin.api_v1 import live_events as ev
from tests.store_seed import seed_store

NOW = datetime(2026, 10, 29, 16, 0, tzinfo=timezone.utc)
PLAN = {"plan_id": "p1", "ticker": "MSFT", "direction": "bullish", "strategy": "VWAP",
        "horizon_key": "1m", "status": "ACTIVE", "created_at": "2026-10-29T08:00:00+00:00",
        "entry_price": 418.5,
        "status_history": [{"status": "ACTIVE", "reason": "limit_fill",
                            "at": "2026-10-29T13:40:00+00:00"}], "legs_realized": []}
TRADE = {"id": "812", "ticker": "NVDA", "direction": "bullish", "status": "win",
         "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0,
         "closed_at": "2026-10-29T15:20:00+00:00", "realized_pnl_amount": 200.0}
KILL = {"on": True, "reason": "daily loss", "at": "2026-10-29T07:31:00+00:00"}


def _loaders(**over):
    base = {"plans": lambda: [PLAN], "trades": lambda: [TRADE],
            "killswitch": lambda: KILL, "shares": lambda: {}}
    return {**base, **over}


def _boom():
    raise RuntimeError("source down")


def test_rows_merge_newest_first():
    rows, meta = ev.collect_events(8, loaders=_loaders(), now=NOW)
    assert [r["kind"] for r in rows] == ["trade_closed", "paper_filled", "plan_alerted",
                                         "killswitch"]
    assert meta == {"availability": "ok", "as_of": "2026-10-29T16:00:00+00:00", "missing": []}


def test_limit_truncates_after_sorting():
    rows, _ = ev.collect_events(2, loaders=_loaders(), now=NOW)
    assert [r["kind"] for r in rows] == ["trade_closed", "paper_filled"]


def test_a_failed_plans_source_is_partial_and_named():
    rows, meta = ev.collect_events(8, loaders=_loaders(plans=_boom), now=NOW)
    assert [r["kind"] for r in rows] == ["trade_closed", "killswitch"]
    assert meta["availability"] == "partial"
    assert meta["missing"] == ["plan_alerted", "paper_filled", "tp1_hit"]


def test_every_source_failing_is_unavailable_not_empty():
    loaders = {name: _boom for name in ("plans", "trades", "killswitch", "shares")}
    rows, meta = ev.collect_events(8, loaders=loaders, now=NOW)
    assert rows == []
    assert meta["availability"] == "unavailable"
    assert meta["missing"] == [kind.kind for kind in ev.EVENT_KINDS]


def test_a_builder_failing_on_bad_data_drops_only_its_kinds():
    rows, meta = ev.collect_events(8, loaders=_loaders(trades=lambda: None), now=NOW)
    assert meta["missing"] == ["trade_closed"]
    assert "trade_closed" not in {r["kind"] for r in rows}


def test_a_failed_shares_source_drops_no_kind():
    _, meta = ev.collect_events(8, loaders=_loaders(shares=_boom), now=NOW)
    assert meta["availability"] == "ok"


def test_the_quiet_day_is_ok_and_empty():
    rows, meta = ev.collect_events(8, loaders=_loaders(
        plans=lambda: [], trades=lambda: [], killswitch=lambda: {"on": False, "at": None}),
        now=NOW)
    assert (rows, meta["availability"]) == ([], "ok")


def test_the_trade_window_covers_the_largest_limit(admin_app):
    from swingbot.admin.api_v1 import live
    assert ev.TRADE_WINDOW >= live.MAX_LIMIT


def test_live_serves_the_feed(logged_in):
    seed_store("plans", [PLAN])
    seed_store("killswitch", KILL)
    body = logged_in.get("/api/v1/live?limit=2").get_json()

    assert [r["kind"] for r in body["events"]] == ["paper_filled", "plan_alerted"]
    assert set(body["events_meta"]) == {"availability", "as_of", "missing"}
    assert body["events_meta"]["availability"] == "ok"


def test_live_answers_200_when_a_source_fails(logged_in, monkeypatch):
    monkeypatch.setitem(ev.SOURCE_LOADERS, "plans", _boom)
    response = logged_in.get("/api/v1/live")
    assert response.status_code == 200
    meta = response.get_json()["events_meta"]
    assert meta["availability"] == "partial"
    assert meta["missing"] == ["plan_alerted", "paper_filled", "tp1_hit"]


@pytest.mark.parametrize("limit", ["1", "50"])
def test_live_limit_bounds_the_feed(logged_in, limit):
    seed_store("plans", [PLAN])
    body = logged_in.get(f"/api/v1/live?limit={limit}").get_json()
    assert len(body["events"]) <= int(limit)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/test_live_events_trades.py`, then `... file tests/live_api/test_live_events_collect.py`
Expected: FAIL with `AttributeError: module ... has no attribute 'trade_closed_rows'` / `'collect_events'`.

- [ ] **Step 4: Append the builders and the dispatcher to `live_events.py`**

Add to the imports at the top: `import logging`, `from dataclasses import dataclass`, `from datetime import datetime, timezone` (replacing the bare `datetime` import), `from typing import Any, Callable, Mapping`, and `from swingbot.core.infra.swallowed import swallowed`; then `log = logging.getLogger(__name__)` below them. Append:

```python
#: Last leg's reason -> the outcome word on a closed-trade line.
_OUTCOMES = {
    "tp1_runner_tp2": "TP2", "tp1_runner_be": "runner at floor",
    "tp1_runner_trail": "trailed", "tp1_runner_progress_stall": "runner stalled",
    "time_exit": "time exit", "stall_exit": "stall exit", "scratch": "scratch",
    "loss": "stop", "tp1": "TP1",
}


def _outcome(trade: Mapping) -> str | None:
    legs = trade.get("legs") or []
    last = legs[-1] if legs and isinstance(legs[-1], Mapping) else {}
    label = _OUTCOMES.get(str(last.get("reason") or ""))
    return label or trade.get("close_reason") or trade.get("status")


def trade_closed_rows(trades: list[dict]) -> list[dict]:
    from swingbot.core.tracking.performance import closed_r_multiple
    rows = []
    for trade in trades:
        at = iso_at(trade.get("closed_at"))
        if at is None or trade.get("status") == "open":
            continue
        r = closed_r_multiple(trade)
        pnl = None if r is None else {"r": r, "amount": _number(trade.get("realized_pnl_amount"))}
        outcome = _outcome(trade)
        text = f"{trade.get('ticker') or '?'} closed" + (f" · {outcome}" if outcome else "")
        rows.append(event_row(at, "trade_closed", text, tone_for(r), trade.get("id"), pnl))
    return rows


def killswitch_rows(state: Mapping) -> list[dict]:
    """The latest transition only, worded by `on`: the table holds one row and
    `release()` overwrites its time, so no history and no engagement claimed
    at a release time."""
    at = iso_at(state.get("at")) if isinstance(state, Mapping) else None
    if at is None:
        return []
    engaged = bool(state.get("on"))
    text = "Killswitch engaged" if engaged else "Killswitch released"
    return [event_row(at, "killswitch", text, "warning" if engaged else "neutral", None)]


@dataclass(frozen=True)
class EventKind:
    kind: str
    source: str
    build: Callable[[dict], list[dict]]


EVENT_KINDS: tuple[EventKind, ...] = (
    EventKind("plan_alerted", "plans", lambda s: plan_alerted_rows(s["plans"])),
    EventKind("paper_filled", "plans", lambda s: paper_filled_rows(s["plans"])),
    EventKind("tp1_hit", "plans", lambda s: tp1_hit_rows(s["plans"], s.get("shares") or {})),
    EventKind("trade_closed", "trades", lambda s: trade_closed_rows(s["trades"])),
    EventKind("killswitch", "killswitch", lambda s: killswitch_rows(s["killswitch"])),
)

#: Most recently updated plans read per request. A fill or TP1 rewrites its
#: plan's row, so a recent event's plan is near the top of this window.
PLAN_WINDOW = 200
#: Closed trades read per request: no more than `live.MAX_LIMIT` can show.
TRADE_WINDOW = 50


def _load_plans() -> list[dict]:
    from swingbot.core.db.repositories.plans import plans_repo
    from swingbot.core.db.schema import plans
    return plans_repo().list_all(order_by=plans.c.updated_at.desc(), limit=PLAN_WINDOW)


def _load_trades() -> list[dict]:
    from swingbot.core.db.repositories.trades import trades_repo
    from swingbot.core.tracking.performance import _json_record
    return [_json_record(row) for row in trades_repo().closed_trades(limit=TRADE_WINDOW)]


def _load_killswitch() -> dict:
    from swingbot.core.db.repositories.killswitch import killswitch_repo
    return killswitch_repo().state()


def _load_shares() -> dict[str, float]:
    """plan_id -> shares, for TP1 amounts; open and recently closed trades."""
    from swingbot.core.db.repositories.trades import trades_repo
    repo = trades_repo()
    rows = repo.open_trades() + repo.closed_trades(limit=PLAN_WINDOW)
    return {str(row["plan_id"]): row["shares"] for row in rows
            if row.get("plan_id") and row.get("shares")}


SOURCE_LOADERS: dict[str, Callable[[], Any]] = {
    "plans": _load_plans, "trades": _load_trades,
    "killswitch": _load_killswitch, "shares": _load_shares,
}


def _load_sources(loaders: Mapping[str, Callable[[], Any]]) -> dict:
    sources = {}
    for name, load in loaders.items():
        try:
            sources[name] = load()
        except Exception as exc:
            swallowed(log, f"ops.live.events.{name}", exc, level=logging.WARNING)
    return sources


def _build(kind: EventKind, sources: dict) -> list[dict] | None:
    """The kind's rows, or None when its source failed or its data was bad."""
    if kind.source not in sources:
        return None
    try:
        return kind.build(sources)
    except Exception as exc:
        swallowed(log, f"ops.live.events.{kind.kind}", exc, level=logging.WARNING)
        return None


def _meta(missing: list[str], now: datetime) -> dict:
    if not missing:
        state = "ok"
    elif len(missing) == len(EVENT_KINDS):
        state = "unavailable"
    else:
        state = "partial"
    return {"availability": state, "as_of": iso(now), "missing": missing}


def collect_events(limit: int, *, loaders: Mapping[str, Callable[[], Any]] | None = None,
                   now: datetime | None = None) -> tuple[list[dict], dict]:
    """Every kind's rows merged newest first and cut to `limit`, plus the meta
    naming each kind whose source failed, so a gap never reads as a quiet day."""
    now = now or datetime.now(timezone.utc)
    sources = _load_sources(SOURCE_LOADERS if loaders is None else loaders)
    rows, missing = [], []
    for kind in EVENT_KINDS:
        built = _build(kind, sources)
        if built is None:
            missing.append(kind.kind)
        else:
            rows.extend(built)
    rows.sort(key=lambda row: datetime.fromisoformat(row["at"]), reverse=True)
    return rows[:limit], _meta(missing, now)
```

- [ ] **Step 5: Wire the feed into `/live` and retire the placeholders**

In `swingbot/admin/api_v1/live.py`, add `from .live_events import EVENT_KINDS, collect_events, iso_at` below the `.auth` import. Delete `_utc_text`, and in `_killswitch_values` call `iso_at(state.get("at"))` instead. Replace `_events`:

```python
def _events(limit: int, now: datetime) -> tuple[list, dict]:
    """The activity feed; a failure past the per-source guards is unavailable."""
    try:
        return collect_events(limit, now=now)
    except Exception as exc:
        swallowed(log, "ops.live.events", exc, level=logging.WARNING)
        return [], {"availability": "unavailable", "as_of": iso(now),
                    "missing": [kind.kind for kind in EVENT_KINDS]}
```

Add the activity feed to the module docstring's first paragraph.

In `tests/live_api/test_live_endpoint.py`, retire these two tests explicitly:
- **Retired** `test_events_are_not_wired_until_v202_3`: the placeholder it pinned is gone. `test_live_serves_the_feed` replaces it.
- **Retired** `test_utc_text_normalises_offsets`: `_utc_text` is gone. `test_live_events_plans.py::test_iso_at` covers the same cases.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/live_api/`
Expected: PASS, `0 failed` (including V202-1b's killswitch `since` tests, which now go through `iso_at`).

Complexity: `python <wt>/scripts/dev/complexity_gate.py`. Expected: no new violation.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/live_events.py swingbot/admin/api_v1/live.py tests/live_api/test_live_endpoint.py tests/live_api/test_live_events_trades.py tests/live_api/test_live_events_collect.py
git -C <wt> commit -m "feat(v202): /live activity feed from closed trades, killswitch and plans

Table-driven collect_events loads each source once; a failed source names
its kinds in events_meta.missing (partial/unavailable), never an empty day.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

