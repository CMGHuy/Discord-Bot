# Analytics Workspace Redesign (v94) — Part 1: Backend scope and routes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, global constraints, prerequisite (v93 merged) and the whole-plan parallelisation live in `_0-index.md`. **Spec:** `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md` §3.5, §4.

# Phase 1 — Backend: one scope, every route

## Parallelisation (this phase)

- **Sequential:** B1 first — every other task imports `parse_scope`, `select`, `echo`, `closed_only`, `ScopeError` from it and the `_scope()` helper it adds to `analytics.py`.
- **Group A (parallel after B1):** B2, B3, B4, B5, B6, B7, B8 — each edits one route function in `swingbot/admin/api_v1/analytics.py` and appends to `tests/admin/test_api_v1_analytics.py`. One agent per task, **commit before the next starts** (shared test file).
- **Sequential last:** B9 (its consistency test calls every route above).

## Exit criteria

Every `/analytics/*` payload carries either `scope`+`n` (scoped) or `"scope": "all-time"`. The same query string yields the same `n` on performance, by-dimension, heat-grid, exit-quality and journal. No rate field is non-null for `n < MIN_CELL_N`. `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` and `... tests/analytics/test_scope.py` green.

---

### Task B1: `scope.py` — `BookScope`, `parse_scope`, `select`, `echo`, `closed_only`

**Files:**
- Create: `swingbot/core/analytics/scope.py`
- Create: `tests/analytics/test_scope.py`
- Modify: `swingbot/admin/api_v1/analytics.py` (add `_scope()` helper after `_iso_day`, ~L54–68; keep `_iso_day` for now — B2 removes its last caller)

**Interfaces:**
- Consumes: `metrics.in_date_range`, `tracking.performance.primary_strategy_label`, `market.strategy_types.HORIZONS`.
- Produces:
  - `SCOPE_PARAMS = ("from", "to", "ledger", "strategy", "horizon", "direction")`
  - `class ScopeError(ValueError)`
  - `@dataclass(frozen=True) class BookScope(start, end, ledger="main", strategy=None, horizon=None, direction=None)`
  - `parse_scope(args: Mapping[str, str]) -> BookScope` (raises `ScopeError`)
  - `reject_unknown(args: Mapping[str, str], extra: tuple[str, ...] = ()) -> None` (raises `ScopeError`)
  - `closed_only(trades: list[dict]) -> list[dict]`
  - `select(closed: list[dict], scope: BookScope) -> list[dict]`
  - `echo(scope: BookScope, n: int) -> dict` → `{"scope": {"from","to","ledger","strategy","horizon","direction"}, "n": n}`
  - In `analytics.py`: `_scope(extra: tuple[str, ...] = ()) -> BookScope` (converts `ScopeError` → `ApiError("invalid", msg, 400)`).

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_scope.py`:

```python
import pytest

from swingbot.core.analytics.scope import (
    BookScope, ScopeError, closed_only, echo, parse_scope, reject_unknown, select,
)


def _t(status="win", closed_at="2026-08-04T15:00:00+00:00", ledger=None, strategy="MACD",
       horizon="1m", direction="bullish", source="strategy"):
    t = {"id": f"{strategy}-{horizon}-{closed_at}", "status": status, "closed_at": closed_at,
         "strategy": strategy, "horizon_key": horizon, "direction": direction, "source": source,
         "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0, "target_sources": [strategy]}
    if ledger is not None:
        t["ledger"] = ledger
    return t


def test_parse_defaults_to_main_ledger_and_open_bounds():
    s = parse_scope({})
    assert s == BookScope(start=None, end=None, ledger="main", strategy=None, horizon=None, direction=None)


def test_parse_reads_every_param():
    s = parse_scope({"from": "2026-08-01", "to": "2026-08-31", "ledger": "both",
                     "strategy": "MACD", "horizon": "1m", "direction": "bearish"})
    assert (s.start, s.end, s.ledger, s.strategy, s.horizon, s.direction) == \
        ("2026-08-01", "2026-08-31", "both", "MACD", "1m", "bearish")


@pytest.mark.parametrize("args,fragment", [
    ({"from": "last-tuesday"}, "from must be a YYYY-MM-DD date"),
    ({"from": "2026-09-01", "to": "2026-08-01"}, "from must not be after to"),
    ({"ledger": "shadow"}, "ledger must be one of"),
    ({"direction": "long"}, "direction must be one of"),
    ({"horizon": "3y"}, "horizon must be one of"),
])
def test_parse_rejects_bad_values(args, fragment):
    with pytest.raises(ScopeError, match=fragment):
        parse_scope(args)


def test_reject_unknown_names_the_first_offender_and_allows_extras():
    reject_unknown({"from": "2026-08-01", "dim": "strategy"}, extra=("dim",))
    with pytest.raises(ScopeError, match="unknown parameter 'zzz'"):
        reject_unknown({"zzz": "1"})


def test_closed_only_keeps_win_loss_closed():
    trades = [_t("win"), _t("loss"), _t("closed"), _t("open", closed_at=None)]
    assert [t["status"] for t in closed_only(trades)] == ["win", "loss", "closed"]


def test_select_applies_every_field():
    closed = [
        _t(closed_at="2026-07-30T10:00:00+00:00"),                  # out of range
        _t(ledger="weak"),                                           # wrong ledger
        _t(strategy="Volume Profile"),                               # wrong strategy
        _t(horizon="2w"),                                            # wrong horizon
        _t(direction="bearish"),                                     # wrong direction
        _t(),                                                        # the one survivor
    ]
    scope = parse_scope({"from": "2026-08-01", "to": "2026-08-31", "strategy": "MACD",
                         "horizon": "1m", "direction": "bullish"})
    assert len(select(closed, scope)) == 1


def test_select_ledger_missing_means_main_and_both_keeps_all():
    closed = [_t(), _t(ledger="main"), _t(ledger="weak")]
    assert len(select(closed, parse_scope({}))) == 2
    assert len(select(closed, parse_scope({"ledger": "weak"}))) == 1
    assert len(select(closed, parse_scope({"ledger": "both"}))) == 3


def test_echo_shape():
    body = echo(parse_scope({"strategy": "MACD"}), 7)
    assert body == {"scope": {"from": None, "to": None, "ledger": "main", "strategy": "MACD",
                              "horizon": None, "direction": None}, "n": 7}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/analytics/test_scope.py -v`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.analytics.scope`.

- [ ] **Step 3: Implement `scope.py`**

```python
"""One scope for every analytics route (spec v94 D2/D5).

Parsed once per request, applied by every `/analytics/*` route, echoed in
every scoped payload -- so the frontend sends one query string everywhere and
can prove which population each panel shows. Pure: no Flask here; the route
layer converts `ScopeError` into its 400.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from swingbot.core.analytics import metrics as m
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.tracking.performance import primary_strategy_label

SCOPE_PARAMS = ("from", "to", "ledger", "strategy", "horizon", "direction")
LEDGERS = ("main", "weak", "both")
DIRECTIONS = ("bullish", "bearish")
CLOSED_STATUSES = ("win", "loss", "closed")


class ScopeError(ValueError):
    """A malformed scope parameter. Never a silently-dropped filter."""


@dataclass(frozen=True)
class BookScope:
    start: str | None = None
    end: str | None = None
    ledger: str = "main"
    strategy: str | None = None
    horizon: str | None = None
    direction: str | None = None


def _day(args: Mapping[str, str], name: str) -> str | None:
    raw = (args.get(name) or "").strip()
    if not raw:
        return None
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ScopeError(f"{name} must be a YYYY-MM-DD date")
    return raw


def _choice(args: Mapping[str, str], name: str, allowed: tuple[str, ...], default: str | None) -> str | None:
    raw = (args.get(name) or "").strip()
    if not raw:
        return default
    if raw not in allowed:
        raise ScopeError(f"{name} must be one of {list(allowed)}, got {raw!r}")
    return raw


def parse_scope(args: Mapping[str, str]) -> BookScope:
    start, end = _day(args, "from"), _day(args, "to")
    if start and end and start > end:
        raise ScopeError("from must not be after to")
    return BookScope(
        start=start, end=end,
        ledger=_choice(args, "ledger", LEDGERS, "main") or "main",
        strategy=(args.get("strategy") or "").strip() or None,
        horizon=_choice(args, "horizon", tuple(HORIZONS), None),
        direction=_choice(args, "direction", DIRECTIONS, None),
    )


def reject_unknown(args: Mapping[str, str], extra: tuple[str, ...] = ()) -> None:
    allowed = set(SCOPE_PARAMS) | set(extra)
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ScopeError(f"unknown parameter {unknown[0]!r}; allowed: {sorted(allowed)}")


def closed_only(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("status") in CLOSED_STATUSES]


def select(closed: list[dict], scope: BookScope) -> list[dict]:
    out = m.in_date_range(closed, start=scope.start, end=scope.end)
    if scope.ledger != "both":
        out = [t for t in out if (t.get("ledger") or "main") == scope.ledger]
    if scope.strategy:
        out = [t for t in out if primary_strategy_label(t) == scope.strategy]
    if scope.horizon:
        out = [t for t in out if t.get("horizon_key") == scope.horizon]
    if scope.direction:
        out = [t for t in out if t.get("direction") == scope.direction]
    return out


def echo(scope: BookScope, n: int) -> dict:
    return {"scope": {"from": scope.start, "to": scope.end, "ledger": scope.ledger,
                      "strategy": scope.strategy, "horizon": scope.horizon,
                      "direction": scope.direction}, "n": n}
```

- [ ] **Step 4: Add `_scope()` to `analytics.py`** (after `_iso_day`):

```python
def _scope(extra: tuple[str, ...] = ()):
    """Parse the request's BookScope or 400 (spec v94 D5). `extra` names
    route-specific parameters (e.g. `dim`) that are not scope fields."""
    from swingbot.core.analytics.scope import ScopeError, parse_scope, reject_unknown

    try:
        reject_unknown(request.args, extra)
        return parse_scope(request.args)
    except ScopeError as exc:
        raise ApiError("invalid", str(exc), 400)
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/analytics/test_scope.py -v` → all PASS. Then `python -m py_compile swingbot/admin/api_v1/analytics.py`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/scope.py tests/analytics/test_scope.py swingbot/admin/api_v1/analytics.py
git commit -m "feat(v94): BookScope -- one parsed scope for every analytics route"
```

---

### Task B2: `/analytics/performance` scoped; `rolling_wr`, `rolling_exp_r`

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (add `rolling_expectancy_r` after `rolling_win_rate`, ~L376)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_performance`, ~L72–178)
- Create: `tests/analytics/test_metrics_rolling.py`
- Modify: `tests/admin/test_api_v1_analytics.py`, `tests/admin/test_api_analytics.py` (any test asserting top-level `win_rate`/`expectancy_r` are all-time)

**Interfaces:**
- Consumes: B1's `_scope`, `select`, `echo`, `closed_only`; v93's `weak` block (keep as is).
- Produces: payload keeps every existing key; **every block is now computed over the scoped list** (top-level `win_rate`/`expectancy_r` included); adds `rolling_wr: [{date, win_rate}]`, `rolling_exp_r: [{date, exp_r}]`, and `scope`/`n` from `echo`. `metrics.rolling_expectancy_r(closed, window=50) -> list[dict]`.

- [ ] **Step 1: Failing metric test** — `tests/analytics/test_metrics_rolling.py`:

```python
from swingbot.core.analytics.metrics import rolling_expectancy_r


def _t(i, r):
    entry, stop = 100.0, 95.0                      # risk = 5 -> exit = entry + 5r
    return {"status": "win" if r > 0 else "loss", "direction": "bullish", "entry": entry,
            "stop_loss": stop, "exit_price": entry + 5 * r,
            "closed_at": f"2026-08-{i + 1:02d}T15:00:00+00:00"}


def test_rolling_expectancy_starts_at_five_trades_and_averages_the_window():
    closed = [_t(i, r) for i, r in enumerate([1, -1, 2, -1, 1, 3])]
    pts = rolling_expectancy_r(closed, window=3)
    assert [p["date"] for p in pts] == ["2026-08-05", "2026-08-06"]
    assert pts[0]["exp_r"] == round((2 - 1 + 1) / 3, 4)
    assert pts[1]["exp_r"] == round((-1 + 1 + 3) / 3, 4)


def test_rolling_expectancy_skips_uncomputable_and_undated():
    closed = [_t(i, 1) for i in range(5)] + [{"status": "win", "entry": 1, "stop_loss": 1}]
    assert len(rolling_expectancy_r(closed, window=50)) == 1
```

- [ ] **Step 2: Failing route test** — append to `tests/admin/test_api_v1_analytics.py`:

```python
def _closed(trade_id, *, status="win", closed_at="2026-08-04T15:00:00+00:00", **over):
    t = _trade(trade_id, plan_id=None, status=status)
    t["closed_at"] = closed_at
    t.update(over)
    return t


def test_performance_is_scoped_and_echoes_scope(seed, logged_in):
    seed(trades=[
        _closed("a" * 16, closed_at="2026-07-10T15:00:00+00:00"),
        _closed("b" * 16, status="loss"),
        _closed("c" * 16, horizon_key="2w"),
    ])
    body = logged_in.get("/api/v1/analytics/performance?from=2026-08-01&horizon=1m").get_json()
    assert body["scope"] == {"from": "2026-08-01", "to": None, "ledger": "main",
                             "strategy": None, "horizon": "1m", "direction": None}
    assert body["n"] == 1
    assert body["win_rate_n"] == 1 and body["win_rate"] == 0.0
    assert body["rolling_wr"] == [] and body["rolling_exp_r"] == []
    assert body["totals"]["closed"] == 1


def test_performance_rejects_bad_scope(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/performance?ledger=shadow"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/analytics/performance?bogus=1"), "invalid", 400)
```

Run: `python -m pytest tests/analytics/test_metrics_rolling.py tests/admin/test_api_v1_analytics.py -k "rolling or scoped_and_echoes or bad_scope" -v` → FAIL (`ImportError`, `KeyError: 'scope'`).

- [ ] **Step 3: Implement `rolling_expectancy_r`** in `metrics.py`:

```python
def rolling_expectancy_r(closed: list[dict], window: int = 50) -> list[dict]:
    """Trailing mean R over the last `window` computable closes, one point per
    close, emitted only once 5 have accumulated -- the same floor
    `rolling_win_rate` uses and for the same reason (spec v94 D9)."""
    dated = sorted((t for t in closed if t.get("closed_at") and r_multiple(t) is not None),
                   key=lambda t: t["closed_at"])
    rs = [r_multiple(t) for t in dated]
    points = []
    for i in range(len(dated)):
        if i + 1 < 5:
            continue
        window_slice = rs[max(0, i + 1 - window):i + 1]
        points.append({"date": dated[i]["closed_at"][:10],
                       "exp_r": round(sum(window_slice) / len(window_slice), 4)})
    return points
```

- [ ] **Step 4: Rewrite `analytics_performance`'s population** — replace the block from `unknown = set(request.args) - {"from", "to"}` through `scoped = m.in_date_range(closed, start=start, end=end)` with:

```python
    from swingbot.admin.dashboard import closed_pnl
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope()
    tl = TradeLog()
    all_raw = _all_trades(tl)
    closed = select(closed_only(all_raw), scope)     # every block below reads THIS list
    scoped = closed
    start, end = scope.start, scope.end
    stats = tl.get_stats(trades=all_raw)             # totals.total/open stay book-wide
    stats.update(tl.get_extended_stats(trades=all_raw))
    realized = [p for p in (closed_pnl(t) for t in closed) if p is not None]
```

and add the module helper (after `_scope`) — **after v93**, `get_trades` takes `ledger=`; read its signature (`grep -n "def get_trades" -A 4 swingbot/core/tracking/performance.py`) and pass whichever value returns *both* ledgers (v93 documents it; if `ledger=None` means "all", use that). The scope, not the loader, decides the ledger:

```python
def _all_trades(tl: TradeLog) -> list[dict]:
    """Every trade in every ledger; `scope.select` applies the ledger filter."""
    return tl.get_trades(status=None, limit=None, ledger=None) or []   # adjust per v93's signature
```

Then in the returned dict: set `"totals": {"total": stats.get("total"), "open": stats.get("open"), "closed": len(closed)}`, keep every other key, add after `"benchmark"`:

```python
        "rolling_wr": m.rolling_win_rate(scoped, window=50),
        "rolling_exp_r": m.rolling_expectancy_r(scoped, window=50),
        **echo(scope, len(scoped)),
```

Update the docstring's "What `?from=`/`?to=` scopes" paragraph to: "Every block is computed over the `BookScope` population (spec v94 D5); `totals.total/open` alone stay book-wide because open trades have no close to scope on." Keep v93's `"weak": tl.weak_summary()` line untouched.

- [ ] **Step 5: Fix the tests that pinned all-time top-level figures**

`grep -n "all-time\|all_time" tests/admin/test_api_analytics.py tests/admin/test_api_v1_analytics.py` — for each test asserting `win_rate`/`expectancy_r` ignore `from`/`to`, invert the assertion (they now follow the range) and update its docstring to cite spec v94 D5. Update `test_performance_top_level_shape` to add `"rolling_wr": list, "rolling_exp_r": list, "scope": dict, "n": int` (and v93's `"weak": dict`).

- [ ] **Step 6: Verify**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_rolling.py` and `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` and `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py` → each `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/admin/api_v1/analytics.py tests/analytics/test_metrics_rolling.py tests/admin/test_api_v1_analytics.py tests/admin/test_api_analytics.py
git commit -m "feat(v94): /analytics/performance obeys BookScope; rolling win rate and ExpR series"
```

---

### Task B3: `/analytics/equity-curve` scoped; `cum_pnl`, `cum_pct`, indexed SPY

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_equity_curve`, ~L180–248)
- Modify: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: B1; `metrics.balance_at`, `account.load_account_config`.
- Produces: `points[{date, cum_r, drawdown_r, cum_pnl, cum_pct}]`, `benchmark: {"spy_indexed": [{date, pct}]}`, `n`, `as_of`, `scope`, plus module helper `_index_benchmark(spy_cum, start: str | None) -> list[dict]`.

- [ ] **Step 1: Failing tests** — append:

```python
def test_equity_curve_carries_currency_and_percent_and_scope(seed, logged_in):
    seed(trades=[
        _closed("a" * 16, closed_at="2026-08-02T15:00:00+00:00", realized_pnl_amount=70.0),
        _closed("b" * 16, status="loss", closed_at="2026-08-03T15:00:00+00:00",
                exit_price=98.0, realized_pnl_amount=-30.0),
    ])
    body = logged_in.get("/api/v1/analytics/equity-curve?ledger=both").get_json()
    assert [p["cum_pnl"] for p in body["points"]] == [70.0, 40.0]
    assert all(isinstance(p["cum_pct"], (int, float)) or p["cum_pct"] is None for p in body["points"])
    assert body["scope"]["ledger"] == "both" and body["n"] == 2
    assert "spy_indexed" in body["benchmark"]


def test_index_benchmark_rebases_to_first_point_in_range():
    from swingbot.admin.api_v1.analytics import _index_benchmark
    out = _index_benchmark({"2026-08-01": 100.0, "2026-08-02": 102.0, "2026-08-03": 99.0}, "2026-08-02")
    assert out == [{"date": "2026-08-02", "pct": 0.0}, {"date": "2026-08-03", "pct": round((99 / 102 - 1) * 100, 4)}]
    assert _index_benchmark({}, None) == []
```

Run: `python -m pytest tests/admin/test_api_v1_analytics.py -k "equity_curve_carries or index_benchmark" -v` → FAIL.

- [ ] **Step 2: Learn `spy_cum`'s real shape** — `grep -n "spy_cum" -B 3 -A 12 swingbot/core/tracking/performance.py`. It is either a `{date: cumulative_value}` mapping or a list of `{date, <value key>}` rows. Write `_index_benchmark` to accept both (the test above covers the mapping form; add a second assertion for the list form using the real key name you find).

- [ ] **Step 3: Implement**

Module helper (after `_all_trades`):

```python
def _index_benchmark(spy_cum, start: str | None) -> list[dict]:
    """SPY as a percent series indexed to the first point at/after `start`
    (spec v94 D6/H5: one axis -- SPY is only ever drawn in % mode)."""
    if isinstance(spy_cum, dict):
        rows = sorted((str(d)[:10], float(v)) for d, v in spy_cum.items() if v is not None)
    else:
        rows = sorted((str(r.get("date"))[:10], float(r.get("value") if "value" in r else r.get("cum_pct")))
                      for r in (spy_cum or []) if r.get("date"))
    rows = [(d, v) for d, v in rows if not start or d >= start]
    if not rows:
        return []
    base = rows[0][1]
    if not base:
        return []
    return [{"date": d, "pct": round((v / base - 1) * 100, 4)} for d, v in rows]
```

Route body — replace from `unknown = set(request.args) - {...}` through the `if strategy:` filter with:

```python
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.planning import account as account_module

    scope = _scope()
    tl = TradeLog()
    all_raw = _all_trades(tl)
    closed = closed_only(all_raw)
    scoped = select(closed, scope)
    base_balance = float(account_module.load_account_config().get("base_balance") or 0.0)
    window_balance = m.balance_at(closed, scope.start, base_balance)
    spy_cum = (tl.get_extended_stats(trades=all_raw) or {}).get("spy_cum") or {}
```

In the loop add `cum_pnl += float(t.get("realized_pnl_amount") or 0.0)` (initialise `cum_pnl = 0.0` before the loop) and extend each point with `"cum_pnl": round(cum_pnl, 2), "cum_pct": round(cum_pnl / window_balance * 100, 4) if window_balance else None`. Return:

```python
    return jsonify({"points": points, "n": len(points),
                    "as_of": points[-1]["date"] if points else None,
                    "benchmark": {"spy_indexed": _index_benchmark(spy_cum, scope.start)},
                    **echo(scope, len(scoped))})
```

Note `n` (computable-R points) and `echo`'s `n` (scoped trades) can differ; the echo wins the `n` key — so rename the existing one to `"points_n"` and update `frontend` consumers in S1/S4 accordingly.

- [ ] **Step 4: Verify** — `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): equity curve obeys BookScope; currency and percent series, SPY indexed to range start"
```

---

### Task B4: `/analytics/by-dimension` — every dimension, floor-nulled rates, `avg_win_r`/`avg_loss_r`

**Files:**
- Modify: `swingbot/core/analytics/aggregate.py` (make `group_by` and `row_for` public, ~L61–110)
- Modify: `swingbot/core/analytics/metrics.py` (add `avg_win_r`, `avg_loss_r` after `payoff_ratio`, ~L300)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_by_dimension`, ~L250–345)
- Modify: `tests/analytics/test_aggregate.py`, `tests/analytics/test_metrics_ratios.py`, `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: B1; `aggregate.DIMENSIONS` (includes `ledger` after v93), `MIN_CELL_N`; v93's `soak` attachment on strategy rows (keep).
- Produces: `aggregate.group_by(closed, dim) -> dict[str, list[dict]]`; `aggregate.row_for(key, trades) -> StatRow`; `metrics.avg_win_r(closed) -> float | None`; `metrics.avg_loss_r(closed) -> float | None`. Route rows: `{key, n, wins, losses, exp_r, total_r, win_rate, profit_factor, avg_win_r, avg_loss_r, total_pnl, max_drawdown_r, badge?, soak?}` with `exp_r, win_rate, profit_factor, avg_win_r, avg_loss_r` **null when `n < MIN_CELL_N`**; payload `{rows, as_of, min_cell_n, scope, n}`.

- [ ] **Step 1: Failing tests**

`tests/analytics/test_aggregate.py` append:

```python
def test_group_by_is_public_and_row_for_matches_stats_by():
    from swingbot.core.analytics.aggregate import group_by, row_for
    closed = [_t(["EMA20"], "win", 80.0), _t(["EMA20"], "loss", -40.0)]
    groups = group_by(closed, "strategy")
    assert set(groups) == {"EMA20"} and len(groups["EMA20"]) == 2
    assert row_for("EMA20", groups["EMA20"]) == stats_by(closed, "strategy")[0]
```

`tests/analytics/test_metrics_ratios.py` append:

```python
def test_avg_win_and_loss_r():
    from swingbot.core.analytics.metrics import avg_loss_r, avg_win_r
    def t(exit_price, status):
        return {"status": status, "direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "exit_price": exit_price}
    closed = [t(110.0, "win"), t(105.0, "win"), t(97.5, "loss")]
    assert avg_win_r(closed) == 1.5 and avg_loss_r(closed) == -0.5
    assert avg_win_r([t(97.5, "loss")]) is None
```

`tests/admin/test_api_v1_analytics.py` append:

```python
def test_by_dimension_accepts_every_dimension_and_nulls_thin_rates(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16, status="loss", direction="bearish")])
    for dim in ("strategy", "horizon", "badge", "confidence", "direction", "dow", "month", "ticker", "source"):
        body = logged_in.get(f"/api/v1/analytics/by-dimension?dim={dim}").get_json()
        assert body["min_cell_n"] == 20 and body["n"] == 2, dim
        for row in body["rows"]:
            assert row["n"] < 20
            assert row["win_rate"] is None and row["exp_r"] is None and row["avg_win_r"] is None, (dim, row)
            assert isinstance(row["total_pnl"], (int, float))


def test_by_dimension_is_scoped(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16, direction="bearish")])
    body = logged_in.get("/api/v1/analytics/by-dimension?dim=direction&direction=bearish").get_json()
    assert [r["key"] for r in body["rows"]] == ["bearish"] and body["n"] == 1


def test_by_dimension_rejects_unknown_dim(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/by-dimension?dim=tier"), "invalid", 400)
```

Run the three files with `-k "group_by or avg_win or by_dimension"` → FAIL.

- [ ] **Step 2: `aggregate.py`** — rename `_row_for` → `row_for` (keep `_row_for = row_for` alias for any importer; `git grep -n "_row_for"` to check), and add:

```python
def group_by(closed: list[dict], dimension: str) -> dict[str, list[dict]]:
    """The grouping `stats_by` does, exposed so a route can attach per-group
    extras (badge, soak) before summarising (spec v94 D7)."""
    if dimension not in _EXTRACTORS:
        raise ValueError(f"Unknown aggregation dimension: {dimension!r}")
    groups: dict[str, list[dict]] = defaultdict(list)
    extractor = _EXTRACTORS[dimension]
    for t in closed:
        groups[extractor(t)].append(t)
    return dict(groups)
```

and make `stats_by` call `group_by`.

- [ ] **Step 3: `metrics.py`** — after `payoff_ratio`:

```python
def avg_win_r(closed: list[dict]) -> float | None:
    """Mean R of the positive computable R-multiples; None with none."""
    wins = [r for r in r_multiples(closed) if r > 0]
    return round(sum(wins) / len(wins), 4) if wins else None


def avg_loss_r(closed: list[dict]) -> float | None:
    """Mean R of the negative computable R-multiples (a negative number); None with none."""
    losses = [r for r in r_multiples(closed) if r < 0]
    return round(sum(losses) / len(losses), 4) if losses else None
```

- [ ] **Step 4: Rewrite `analytics_by_dimension`** (whole body after the docstring; extend the docstring with "spec v94 D7/H1: every `aggregate.DIMENSIONS` value; rate fields are null under `MIN_CELL_N`"):

```python
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import DIMENSIONS, MIN_CELL_N, group_by
    from swingbot.core.analytics.risk_metrics import max_drawdown_r
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.tracking.performance import primary_strategy_label

    scope = _scope(extra=("dim",))
    dim = (request.args.get("dim") or "").strip()
    if dim not in DIMENSIONS:
        raise ApiError("invalid", f"dim must be one of {list(DIMENSIONS)}, got {dim!r}", 400)

    scoped = select(closed_only(_all_trades(TradeLog())), scope)

    if dim == "strategy":            # the real per-trade label, as before
        groups: dict[str, list[dict]] = {}
        for t in scoped:
            groups.setdefault(primary_strategy_label(t), []).append(t)
    elif dim == "horizon":
        groups = {k: v for k, v in group_by(scoped, dim).items() if k in HORIZONS}
    else:
        groups = group_by(scoped, dim)

    if dim == "horizon":
        order = {h: i for i, h in enumerate(HORIZONS)}
        keys = sorted(groups, key=lambda k: order.get(k, len(order)))
    elif dim == "month":
        keys = sorted(groups)
    else:
        keys = sorted(groups, key=lambda k: (-len(groups[k]), str(k)))

    rows = []
    for key in keys:
        trades = groups[key]
        ordered = sorted(trades, key=lambda t: t.get("closed_at") or "")
        rs = [r for t in ordered if (r := m.r_multiple(t)) is not None]
        thin = len(trades) < MIN_CELL_N
        row = {
            "key": str(key), "n": len(trades),
            "wins": sum(1 for t in trades if t.get("status") == "win"),
            "losses": sum(1 for t in trades if t.get("status") == "loss"),
            "exp_r": None if thin else m.expectancy_r(trades),
            "win_rate": None if thin else m.win_rate(trades),
            "profit_factor": None if thin else m.profit_factor(trades),
            "avg_win_r": None if thin else m.avg_win_r(trades),
            "avg_loss_r": None if thin else m.avg_loss_r(trades),
            "total_r": (round(sum(rs), 4) if rs else None),
            "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in trades), 2),
            "max_drawdown_r": max_drawdown_r(rs),
        }
        if dim == "strategy":
            row["badge"] = get_badge("strategy", key).status
            # v93 Task 13 attaches `soak` here -- keep that code exactly as merged.
        rows.append(row)

    dated = [t["closed_at"][:10] for trades in groups.values() for t in trades if t.get("closed_at")]
    return jsonify({"rows": rows, "as_of": max(dated) if dated else None,
                    "min_cell_n": MIN_CELL_N, **echo(scope, len(scoped))})
```

If v93's `soak` code was inside the old loop, move it into the `if dim == "strategy":` branch unchanged, and keep v93's `test_by_dimension_strategy_rows_carry_soak` (or its actual name) green.

- [ ] **Step 5: Verify** — `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`, `... tests/analytics/test_metrics_ratios.py`, `... tests/admin/test_api_v1_analytics.py` → `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/aggregate.py swingbot/core/analytics/metrics.py swingbot/admin/api_v1/analytics.py tests/analytics/test_aggregate.py tests/analytics/test_metrics_ratios.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): by-dimension over every dimension, scoped, rates nulled under the floor"
```

---

### Task B5: `/analytics/heat-grid` (new) — fat strategies × horizons, folded `Other`

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (new route after `analytics_by_dimension`)
- Modify: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: B1; `MIN_CELL_N`, `HORIZONS`, `primary_strategy_label`.
- Produces: `GET /analytics/heat-grid` → `{rows: [strategy…], cols: [horizon…], cells: [{r, c, n, exp_r, win_rate}], folded: {n_strategies, cells: [{c, n, exp_r, win_rate}]}, min_cell_n, scope, n}`. `rows` = strategies whose scoped total `n >= MIN_CELL_N`, sorted by n desc; each cell's rates null when the cell's `n < MIN_CELL_N`.

- [ ] **Step 1: Failing test**

```python
def test_heat_grid_folds_thin_strategies_and_nulls_thin_cells(seed, logged_in):
    fat = [_closed(f"{i:016d}", strategy="MACD", closed_at=f"2026-08-{(i % 28) + 1:02d}T15:00:00+00:00")
           for i in range(21)]
    thin = [_closed("z" * 16, strategy="Volume Profile")]
    seed(trades=fat + thin)
    body = logged_in.get("/api/v1/analytics/heat-grid").get_json()
    assert body["rows"] == ["MACD"] and body["cols"][0] == "2w"
    macd_1m = next(c for c in body["cells"] if c["r"] == 0 and body["cols"][c["c"]] == "1m")
    assert macd_1m["n"] == 21 and macd_1m["win_rate"] == 100.0
    assert body["folded"]["n_strategies"] == 1
    other_1m = next(c for c in body["folded"]["cells"] if body["cols"][c["c"]] == "1m")
    assert other_1m["n"] == 1 and other_1m["win_rate"] is None
    assert body["n"] == 22 and body["min_cell_n"] == 20
```

Run: `python -m pytest tests/admin/test_api_v1_analytics.py -k heat_grid -v` → FAIL 404. (If `_trade`'s `source="strategy"` does not make `primary_strategy_label` return the `strategy` field, read `primary_strategy_label`'s docstring at `swingbot/core/tracking/performance.py:181` and set the field it reads in `_closed(...)` instead.)

- [ ] **Step 2: Implement**

```python
@api_v1.route("/analytics/heat-grid", methods=["GET"])
@require_auth
def analytics_heat_grid():
    """Strategy x horizon grid over the scoped book (spec v94 D7/H1).

    Only strategies whose scoped total clears `MIN_CELL_N` get a row; the
    rest fold into one `Other` row so 46 strategies over a few hundred
    trades do not render as 460 cells of noise. Every cell under the floor
    carries `n` and null rates -- the client draws it blank, never coloured.
    """
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import MIN_CELL_N
    from swingbot.core.analytics.scope import closed_only, echo, select
    from swingbot.core.market.strategy_types import HORIZONS
    from swingbot.core.tracking.performance import primary_strategy_label

    scope = _scope()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    cols = list(HORIZONS)
    by_strategy: dict[str, list[dict]] = {}
    for t in scoped:
        if t.get("horizon_key") in HORIZONS:
            by_strategy.setdefault(primary_strategy_label(t), []).append(t)

    def cell(trades: list[dict]) -> dict:
        thin = len(trades) < MIN_CELL_N
        return {"n": len(trades),
                "exp_r": None if thin else m.expectancy_r(trades),
                "win_rate": None if thin else m.win_rate(trades)}

    fat = sorted((s for s, ts in by_strategy.items() if len(ts) >= MIN_CELL_N),
                 key=lambda s: (-len(by_strategy[s]), s))
    cells = []
    for r, s in enumerate(fat):
        for c, h in enumerate(cols):
            cells.append({"r": r, "c": c, **cell([t for t in by_strategy[s] if t.get("horizon_key") == h])})
    folded_names = [s for s in by_strategy if s not in fat]
    folded_trades = [t for s in folded_names for t in by_strategy[s]]
    folded = {"n_strategies": len(folded_names),
              "cells": [{"c": c, **cell([t for t in folded_trades if t.get("horizon_key") == h])}
                        for c, h in enumerate(cols)]}
    return jsonify({"rows": fat, "cols": cols, "cells": cells, "folded": folded,
                    "min_cell_n": MIN_CELL_N, **echo(scope, len(scoped))})
```

Add `"/api/v1/analytics/heat-grid"` to `_PATHS` at the top of the test file (auth + empty-store coverage).

- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → `0 failed`.

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): /analytics/heat-grid -- fat strategies x horizons, thin cells blank, rest folded"
```

---

### Task B6: `/analytics/exit-quality` scoped via journal `trade_id` join

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_exit_quality`)
- Modify: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: B1; `JournalStore().entries()` rows carry `trade_id`.
- Produces: same keys as today plus `scope`, `n`; every block computed over `scoped` closed trades and over journal entries whose `trade_id` is in the scoped set.

- [ ] **Step 1: Failing test**

```python
def test_exit_quality_is_scoped_and_echoes(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16, closed_at="2026-07-01T15:00:00+00:00")])
    body = logged_in.get("/api/v1/analytics/exit-quality?from=2026-08-01").get_json()
    assert body["n"] == 1 and body["scope"]["from"] == "2026-08-01"
    assert body["hold_by_outcome"]["n_winners"] == 1
    assert body["min_cell_n"] == 20
```

Also **delete** `test_exit_quality_rejects_unknown_parameters` (it asserted `?from=` is rejected) and replace with:

```python
def test_exit_quality_rejects_non_scope_parameters(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/exit-quality?bins=3"), "invalid", 400)
```

Run: `-k exit_quality` → FAIL.

- [ ] **Step 2: Implement** — replace the body after the docstring (rewrite the docstring: "Exit-quality aggregates over the scoped book (spec v94 D8). Journal-derived blocks join on `trade_id` so the winners-only histograms describe the same population as the strip above them."):

```python
    from swingbot.core.analytics import exit_quality as eq
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import MIN_CELL_N
    from swingbot.core.analytics.journal import JournalStore
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope()
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    ids = {t.get("id") for t in scoped}
    entries = [e for e in JournalStore().entries() if e.get("trade_id") in ids]
    return jsonify({"exit_reasons": m.exit_reason_split(scoped),
                    "unmapped_reasons": m.unmapped_exit_reasons(scoped),
                    "hold_by_outcome": m.hold_by_outcome(scoped),
                    "efficiency": eq.efficiency_histogram(entries),
                    "mae": eq.mae_histogram(entries),
                    "scatter": eq.mfe_mae_points(entries),
                    "coverage": eq.coverage(entries),
                    "min_cell_n": MIN_CELL_N,
                    **echo(scope, len(scoped))})
```

- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → `0 failed`. Also `python scripts/dev/testrun.py file tests/analytics/test_exit_quality.py` (unchanged module; confirms nothing upstream moved).

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): exit-quality obeys BookScope via journal trade_id join"
```

---

### Task B7: `/analytics/journal` scoped

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_journal`)
- Modify: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: B1. Produces: `{digest, lessons, entries_n, scope, n}`; `digest` over scoped closed trades and scoped entries; `lessons` over scoped entries; `entries_n` = scoped entry count. `lessons` remains an allowed extra parameter.

- [ ] **Step 1: Failing test**

```python
def test_journal_is_scoped_and_keeps_lessons_param(seed, logged_in):
    seed(trades=[_closed("a" * 16)])
    body = logged_in.get("/api/v1/analytics/journal?lessons=2&direction=bearish").get_json()
    assert body["n"] == 0 and body["entries_n"] == 0 and body["scope"]["direction"] == "bearish"
    assert_error(logged_in.get("/api/v1/analytics/journal?lessons=0"), "invalid", 400)
```

- [ ] **Step 2: Implement** — after the `lessons_n` line insert:

```python
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope(extra=("lessons",))
```

(move the `_scope` call **above** the `lessons` parsing so an unknown parameter 400s before anything else), replace the `closed = [...]` block with `scoped = select(closed_only(_all_trades(TradeLog())), scope)`, filter `entries = [e for e in entries if e.get("trade_id") in {t.get("id") for t in scoped}]` after the `try/except`, pass `scoped` to `weekly_digest`, and return `{"digest": ..., "lessons": ..., "entries_n": len(entries), **echo(scope, len(scoped))}`.

- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → `0 failed`.

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): journal digest and lessons obey BookScope"
```

---

### Task B8: `/analytics/strategies` — scoped contribution and cumulative R; registry all-time; drop `heatmap`

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_strategies`, `_json_heatmap`)
- Modify: `tests/admin/test_api_v1_analytics.py`
- Check: `frontend/src/app/stores/trade-detail.store.ts:523` reads only `.strategies` (`grep -n "analyticsStrategies" -A 6 frontend/src/app/stores/trade-detail.store.ts`) — if it reads `heatmap`, stop and report; it does not, per the 2026-09-17 inventory.

**Interfaces:**
- Consumes: B1; `queries._registry_rows`, `_rolling_win_rate_series`.
- Produces: `{strategies: [...all-time registry rows, each with win_rate_series over the SCOPED trades], registry_scope: "all-time", contribution: [{strategy, total_r, n}], cumulative: {strategy: [{date, cum_r}]}, scope, n}`. `heatmap` removed (B5 owns it); `_json_heatmap` deleted.

- [ ] **Step 1: Failing test**

```python
def test_strategies_carries_scoped_contribution_and_cumulative_and_no_heatmap(seed, logged_in):
    seed(trades=[_closed("a" * 16, strategy="MACD"),
                 _closed("b" * 16, strategy="MACD", status="loss", exit_price=98.0,
                         closed_at="2026-08-05T15:00:00+00:00")])
    body = logged_in.get("/api/v1/analytics/strategies").get_json()
    assert "heatmap" not in body and body["registry_scope"] == "all-time"
    macd = next(c for c in body["contribution"] if c["strategy"] == "MACD")
    assert macd["n"] == 2
    assert [p["date"] for p in body["cumulative"]["MACD"]] == ["2026-08-04", "2026-08-05"]
    assert body["n"] == 2
```

Update `test_strategies_ships_series_not_svg` if it asserts `heatmap`.

- [ ] **Step 2: Implement** — replace the body after the imports with:

```python
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.scope import closed_only, echo, select

    scope = _scope()
    rows = _registry_rows()                                   # all-time by design (spec D5)
    scoped = select(closed_only(_all_trades(TradeLog())), scope)
    labeled = [{**t, "strategy": primary_strategy_label(t)} for t in scoped]
    for row in rows:
        strat = [t for t in labeled if t["strategy"] == row["strategy"]]
        row["win_rate_series"] = _rolling_win_rate_series(strat, window=10)

    by_strategy: dict[str, list[dict]] = {}
    for t in labeled:
        by_strategy.setdefault(t["strategy"], []).append(t)
    contribution, cumulative = [], {}
    for name, trades in by_strategy.items():
        ordered = sorted(trades, key=lambda t: t.get("closed_at") or "")
        rs = [(t, r) for t in ordered if (r := m.r_multiple(t)) is not None]
        contribution.append({"strategy": name, "total_r": round(sum(r for _, r in rs), 4) if rs else None,
                             "n": len(trades)})
        running, series = 0.0, []
        for t, r in rs:
            running += r
            series.append({"date": (t.get("closed_at") or "")[:10], "cum_r": round(running, 4)})
        cumulative[name] = series
    contribution.sort(key=lambda c: (-(abs(c["total_r"]) if c["total_r"] is not None else -1), c["strategy"]))
    return jsonify({"strategies": rows, "registry_scope": "all-time",
                    "contribution": contribution, "cumulative": cumulative,
                    **echo(scope, len(scoped))})
```

Delete `_json_heatmap` and the `_strategy_horizon_heatmap` import. Update the docstring: "Registry rows are all-time (a badge is a methodology verdict, not a slice); contribution, cumulative R and the sparkline series obey the BookScope (spec v94 D5/D9)."

- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → `0 failed`; `python -m py_compile swingbot/admin/api_v1/analytics.py`.

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): strategies route -- scoped contribution and cumulative R, registry all-time, heatmap retired"
```

---

### Task B9: `scope: "all-time"` on calibration and plans; cross-route consistency test

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_calibration`, `analytics_plans`)
- Modify: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Produces: both payloads gain `"scope": "all-time"` (H2). Consistency test pins that one query string yields one `n` everywhere.

- [ ] **Step 1: Failing tests**

```python
def test_all_time_routes_say_so(seed, logged_in):
    seed()
    assert logged_in.get("/api/v1/analytics/calibration").get_json()["scope"] == "all-time"
    assert logged_in.get("/api/v1/analytics/plans").get_json()["scope"] == "all-time"


def test_one_query_string_one_population(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16, direction="bearish"),
                 _closed("c" * 16, closed_at="2026-07-01T15:00:00+00:00")])
    q = "?from=2026-08-01&direction=bullish"
    ns = {path: logged_in.get(f"/api/v1/analytics/{path}{q}").get_json()["n"]
          for path in ("performance", "equity-curve", "by-dimension?dim=horizon&", "heat-grid",
                       "exit-quality", "journal", "strategies")}
    assert set(ns.values()) == {1}, ns
```

(For `by-dimension` the path already carries `?dim=horizon&`, so build that URL as `f"/api/v1/analytics/by-dimension?dim=horizon&{q[1:]}"` — adjust the comprehension accordingly.)

Update `test_calibration_shape` and `test_plans_shape` specs to include `"scope": str`.

- [ ] **Step 2: Implement** — add `"scope": "all-time"` to `analytics_calibration`'s dict, and change `analytics_plans` to `return jsonify({**_plan_lifecycle(PlanStore().all()), "scope": "all-time"})`.

- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py` → `0 failed`; `python scripts/dev/testrun.py file tests/analytics/test_scope.py` → `0 failed`.

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): all-time routes declare it; one query string, one population across analytics routes"
```
