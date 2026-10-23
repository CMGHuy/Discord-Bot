# v188 — Cancelled-plan precision: Part 3, admin route (V188-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at the task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-23-v188-cancelled-plan-precision-design.md](../specs/2026-10-23-v188-cancelled-plan-precision-design.md)
**Index:** [2026-10-23-v188-cancelled-plan-precision_0-index.md](2026-10-23-v188-cancelled-plan-precision_0-index.md) — Goal, Global Constraints, Spec clarifications, Contracts, Review Focus and Parallelisation live there and bind this task. This part never changes a contract the index fixes.

**Scope:** the one admin route that serves part 1's `precision_payload` to part 2's screen. Split out of part 1 (`_1-backend.md`, V188-1..V188-4) to keep every file under the 1500-line cap; V188-5 runs after V188-4 and before V188-6.

**Working directory:** every path and command below is relative to the worktree root `.claude/worktrees/2026-10-23-v188-cancelled-plan-precision`, created in V188-1 Step 1. Never edit the main tree from a task.
# Phase 3 — The admin route

### Task V188-5: Admin route `GET /api/v1/cancel-precision`
**Model:** sonnet — a thin Flask route on an established pattern (auth, unknown-param 400, injected loaders); the only judgement is the memo key.

**Files:**
- Create: `swingbot/admin/api_v1/cancel_precision.py`
- Create: `tests/admin/test_api_v1_cancel_precision.py` (suite `admin`)
- Modify: `swingbot/admin/api_v1/__init__.py` (the endpoint import tuple inside `register()`, today lines 208-210)

**Interfaces:**
- Consumes: V188-4 `precision_payload(plans, loader, *, generated_at) -> dict`; `PlanStore().records() -> list[dict]` (`plan_store.py:43`); `plans_repo().version() -> tuple[int, str | None]` (`repositories/plans.py:34`, moves on any write); `daily_delta.read_daily(ticker) -> pd.DataFrame | None` (`daily_delta.py:130`, follows the scan's Alpaca/yfinance basis routing); `spot_metals.is_spot_metal(symbol)` (`spot_metals.py:56`); `api_v1` blueprint, `ApiError(code, message, status)`, `auth.require_auth`.
- Produces: `GET /api/v1/cancel-precision` → 200 with the Payload JSON (index § Contracts), 401 without a session, 400 `invalid` for any query parameter. Module helpers `_load_plans() -> list[dict]`, `_bar_loader(ticker: str) -> pd.DataFrame | None`, `_memo_key() -> tuple`, `_MEMO: dict`, `reset_memo() -> None`. Part 2 (V188-6) fetches this endpoint.

**Decisions:** price source is `market_data/` through `daily_delta.read_daily` (never `data/backtest_cache/`, never `load_normalized`, which misses `daily_alpaca/`); spot metals get `None` (no cache, so their rows show `no_bars`). The memo key is `(plans_repo().version(), UTC "%Y-%m-%dT%H")`: a plan write or a new hour recomputes, nothing else does; the memo holds one entry. Every import of `swingbot.core` happens inside a function (the `calendar.py` rule: nothing binds a data path at import time).

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_cancel_precision.py`:

```python
"""GET /api/v1/cancel-precision (v188): auth, params, the empty book, a scored
plan, the memo, and the price source."""
import pytest

from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_store_records import FakePlansRepo

URL = "/api/v1/cancel-precision"
_LOGIN = {"username": "admin", "password": "admin"}
_PAYLOAD = {"generated_at": str, "data_as_of": NULLABLE_STR, "caption": str,
            "risk_cap_label": str, "tp1_note": str, "small_n_threshold": int,
            "window": dict, "rule_changes": list, "out_of_scope": dict, "headline": dict,
            "baseline": dict, "cards": dict, "splits": dict, "rows": list}
FLAT = (100.0, 100.5, 99.5, 100.0)
STOP_HIT = (100.0, 101.0, 94.0, 95.0)


def _cancelled_dict(plan_id="p1"):
    plan = _plan(plan_id=plan_id, entry_type="stop_entry", trigger_price=105.0,
                 stop_loss=95.0, tp1=120.0, horizon_key="2w", stop_ceiling_pct=2.0)
    record_transition(plan, PlanStatus.CANCELLED, reason="invalidated",
                      at="2026-08-03T15:00:00+00:00")
    return plan_to_dict(plan)


@pytest.fixture
def module(client):
    # `client` first: it loads swingbot.admin.app, which registers the endpoints.
    from swingbot.admin.api_v1 import cancel_precision as mod
    mod.reset_memo()
    yield mod
    mod.reset_memo()


@pytest.fixture
def repo(monkeypatch):
    fake = FakePlansRepo()
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: fake)
    return fake


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_an_unknown_parameter_is_a_400(logged_in, module, repo):
    assert_error(logged_in.get(URL + "?reason=risk_cap"), "invalid", 400)


def test_an_empty_book_is_a_200_with_n_zero(logged_in, module, repo, monkeypatch):
    """Review Focus 4."""
    monkeypatch.setattr(module, "_bar_loader", lambda _t: None)
    resp = logged_in.get(URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, _PAYLOAD)
    head = body["headline"]["all"]
    assert (head["n"], head["precision"], head["precision_ci"], head["small_n"]) == \
        (0, None, None, True)
    assert body["rows"] == [] and body["data_as_of"] is None


def test_a_cancelled_plan_is_scored(logged_in, module, repo, monkeypatch):
    repo.records["p1"] = _cancelled_dict()
    frame = make_ohlcv([FLAT, FLAT, FLAT, (104, 106, 104, 105), STOP_HIT] + [FLAT] * 9,
                       start="2026-07-30")
    monkeypatch.setattr(module, "_bar_loader", lambda _t: frame)
    body = logged_in.get(URL).get_json()
    assert body["headline"]["all"]["counts"]["right"] == 1
    assert [(r["plan_id"], r["outcome"]) for r in body["rows"]] == [("p1", "right")]
    assert body["caption"] == "Hypothetical replay, before commissions, slippage and tax"


def test_the_memo_recomputes_only_on_a_plan_write(logged_in, module, repo, monkeypatch):
    calls = []
    monkeypatch.setattr(module, "_load_plans", lambda: calls.append(1) or [])
    monkeypatch.setattr(module, "_bar_loader", lambda _t: None)
    logged_in.get(URL)
    logged_in.get(URL)
    assert len(calls) == 1
    repo.records["p1"] = _cancelled_dict()          # FakePlansRepo.version() moves
    logged_in.get(URL)
    assert len(calls) == 2


def test_the_memo_key_carries_the_utc_hour(module, repo):
    version, hour = module._memo_key()
    assert version == repo.version()
    assert len(hour) == 13 and hour[10] == "T"      # "YYYY-MM-DDTHH"


def test_spot_metals_have_no_bars(module, monkeypatch):
    from swingbot.core.marketdata import daily_delta
    monkeypatch.setattr(daily_delta, "read_daily",
                        lambda _t: pytest.fail("a spot metal must never be read"))
    assert module._bar_loader("XAUUSD") is None


def test_the_price_source_is_read_daily(module, monkeypatch):
    from swingbot.core.marketdata import daily_delta
    sentinel = make_ohlcv([FLAT])
    monkeypatch.setattr(daily_delta, "read_daily", lambda ticker: sentinel)
    assert module._bar_loader("AAPL") is sentinel


def test_load_plans_reads_the_plan_store(module, repo):
    repo.records["p1"] = _cancelled_dict()
    assert [r["plan_id"] for r in module._load_plans()] == ["p1"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_cancel_precision.py`
Expected: FAIL — `test_requires_auth` gets 404, the others `ImportError: cannot import name 'cancel_precision'`.

- [ ] **Step 3: Implement the route**

Create `swingbot/admin/api_v1/cancel_precision.py`:

```python
"""GET /api/v1/cancel-precision -- v188 cancelled-plan precision.

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
"UI renders, analytics computes": every figure comes from
`swingbot.core.analytics.cancel_precision`; this route loads, memoises and
forwards. Bars come from `market_data/` through `daily_delta.read_daily`, which
follows the scan's Alpaca/yfinance basis routing and is kept fresh by the
bot's MARKET_DATA_AUTO_REFRESH; `data/backtest_cache/` is never read (nothing
refreshes it on the VM). Cost per recompute: one PlanStore scan, one
process-cached frame per ticker, the week bootstraps. The memo recomputes at
most hourly or on any plan write. Runs only in the admin process; a failure
is a 500 on this one screen.
"""
from __future__ import annotations

import datetime as dt

from flask import jsonify, request

from . import ApiError, api_v1
from .auth import require_auth

_MEMO: dict = {}


def _load_plans() -> list[dict]:
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().records()


def _bar_loader(ticker: str):
    from swingbot.core.marketdata import daily_delta, spot_metals
    if spot_metals.is_spot_metal(ticker):
        return None
    return daily_delta.read_daily(ticker)


def _memo_key() -> tuple:
    from swingbot.core.db.repositories.plans import plans_repo
    hour = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H")
    return (plans_repo().version(), hour)


def reset_memo() -> None:
    _MEMO.clear()


@api_v1.route("/cancel-precision", methods=["GET"])
@require_auth
def cancel_precision():
    if request.args:
        raise ApiError("invalid",
                       f"unknown parameter {sorted(request.args)[0]!r}; this route takes none",
                       400)
    from swingbot.core.analytics.cancel_precision import precision_payload
    key = _memo_key()
    if key not in _MEMO:
        payload = precision_payload(
            _load_plans(), _bar_loader,
            generated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        _MEMO.clear()
        _MEMO[key] = payload
    return jsonify(_MEMO[key])
```

In `swingbot/admin/api_v1/__init__.py:register()`, add `cancel_precision` to the import tuple in alphabetical position:

```python
    from . import (analytics, calendar, cancel_precision, dashboard, equity,  # noqa: F401
                   jobs, market, ops_health, reports, research, risk, session,
                   system, trade_commands, trades, versions, watchlist)  # (register routes)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_cancel_precision.py`
Expected: 9 passed.

Run: `git grep -ln "trade_commands, trades, versions\|ops_health, reports" -- tests` and run each hit with `testrun.py file` (a test that pins the endpoint module list must still pass, or gains `cancel_precision`).
Expected: green.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/cancel_precision.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_v1_cancel_precision.py
git commit -m "feat(admin): GET /api/v1/cancel-precision serves the v188 payload

market_data via daily_delta.read_daily, spot metals skipped, memoised on the
plans version and the UTC hour, any query parameter a 400.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
