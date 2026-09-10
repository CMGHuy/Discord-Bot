# v78 — Part 1: Backend (tasks A1…A4)

> Part of `2026-09-10-v78-exit-quality-analytics_0-index.md`. **Read the
> index's Global Constraints before starting any task here.**

**Spec:** `docs/superpowers/specs/2026-09-10-v78-exit-quality-analytics-design.md`

## Part 1 exit criteria

1. `MIN_CELL_N` exists in exactly one place and a test pins it to
   `DRIFT_LIVE_N_FLOOR` so the two cannot drift apart.
2. `StatRow.total_r` is in R, never currency, asserted by a test that would
   fail if it were wired to `realized_pnl_amount`.
3. `exit_quality.py` loads nothing — asserted by a test that passes it a list
   and monkeypatches `JournalStore` to explode if constructed.
4. `GET /api/v1/analytics/exit-quality` returns the documented payload and
   `400`s on any query parameter.
5. `python scripts/dev/testrun.py file tests/analytics/test_exit_quality.py`
   and `... file tests/analytics/test_aggregate.py` are both green.

---

# Phase A — Backend

### Task A1: MIN_CELL_N and StatRow.total_r

**Files:**
- Modify: `swingbot/core/analytics/aggregate.py:47-69` (the `StatRow` dataclass
  and `_row_for`)
- Test: `tests/analytics/test_aggregate.py`

**Interfaces:**
- Consumes: `metrics.r_multiples` (already imported at `aggregate.py:18`),
  `calibration.DRIFT_LIVE_N_FLOOR` (`calibration.py:79`, in the test only).
- Produces: `aggregate.MIN_CELL_N: int` and `StatRow.total_r: float | None`.
  A4, C5, D1 and D2 all consume one or both.

`total_pnl` is currency — `sum(realized_pnl_amount)` at `aggregate.py:64` — and
no per-group total in R exists anywhere. That is what this task adds. It is
deliberately `None` rather than `0.0` for a group with no computable R, per the
index's `None`-is-never-`0` constraint.

`MIN_CELL_N` is defined here rather than imported from `calibration.py` to
avoid an import cycle; Step 1's test is what stops the duplicate drifting.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_aggregate.py`:

```python
def _trade(status, entry, stop, exit_price, pnl, **kw):
    t = {"status": status, "entry": entry, "stop_loss": stop,
         "exit_price": exit_price, "realized_pnl_amount": pnl,
         "ticker": "AAPL", "horizon_key": "4w", "closed_at": "2026-08-03T15:00:00+00:00"}
    t.update(kw)
    return t


def test_min_cell_n_matches_the_drift_floor_it_was_seeded_from():
    """One floor, two homes. If someone retunes DRIFT_LIVE_N_FLOOR without
    touching MIN_CELL_N, the suppression floor silently disagrees with the
    badge-drift floor it was justified by -- this test is the only thing
    that notices."""
    from swingbot.core.analytics import aggregate, calibration
    assert aggregate.MIN_CELL_N == calibration.DRIFT_LIVE_N_FLOOR


def test_total_r_is_in_r_not_currency():
    """A 1R winner and a 1R loser net 0R, whatever the dollar amounts were.
    Wiring total_r to realized_pnl_amount would make this +900."""
    from swingbot.core.analytics.aggregate import stats_by
    closed = [_trade("win", 100.0, 90.0, 110.0, 1000.0),
              _trade("loss", 100.0, 90.0, 90.0, -100.0)]
    row = stats_by(closed, "horizon")[0]
    assert row.total_r == pytest.approx(0.0, abs=0.01)
    assert row.total_pnl == pytest.approx(900.0)


def test_total_r_is_none_when_no_trade_has_computable_r():
    from swingbot.core.analytics.aggregate import stats_by
    closed = [{"status": "closed", "horizon_key": "4w",
               "closed_at": "2026-08-03T15:00:00+00:00"}]
    assert stats_by(closed, "horizon")[0].total_r is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/analytics/test_aggregate.py -k "min_cell_n or total_r" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'MIN_CELL_N'`, and
`TypeError` / `AttributeError` on `total_r`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/analytics/aggregate.py`, add above the `StatRow` dataclass:

```python
#: Below this many trades in a cell, a rate is noise and must not be quoted.
#: Seeded from calibration.DRIFT_LIVE_N_FLOOR (the floor badge drift already
#: refuses to call decay under) rather than a fresh guess. Not imported from
#: there to keep aggregate.py free of a calibration import;
#: test_min_cell_n_matches_the_drift_floor_it_was_seeded_from pins them.
MIN_CELL_N = 20
```

Add the field to `StatRow` (after `total_pnl`, so positional construction
elsewhere keeps working):

```python
    total_pnl: float
    total_r: float | None = None
```

And in `_row_for`, between `total_pnl` and the `return`:

```python
    rs = metrics.r_multiples(trades)
    total_r = round(float(sum(rs)), 4) if rs else None
```

then pass `total_r=total_r` in the `StatRow(...)` call.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`
Expected: PASS. Also run `... file tests/analytics/test_snapshots.py` — `by.*`
rows gain a key, and that file asserts snapshot shape.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/aggregate.py tests/analytics/test_aggregate.py
git commit -m "feat(v78): MIN_CELL_N and a per-group total in R"
```

---

### Task A2: exit_quality histograms (winners-only)

**Files:**
- Create: `swingbot/core/analytics/exit_quality.py`
- Test: `tests/analytics/test_exit_quality.py`

**Interfaces:**
- Consumes: `metrics.histogram(values, bins)` → `[{lo, hi, count}]`.
- Produces: `efficiency_histogram(entries, bins=10) -> dict` and
  `mae_histogram(entries, bins=10) -> dict`, each
  `{"bins": [...], "n": int, "median": float | None}`. A3 adds to this module;
  A4 serves it.

Winners-only is doctrine, quoted in the module docstring from
`core/edge/stops.py:19-29`. `exit_efficiency` is `r_real / mfe_r` clamped to
`[-5, 1]` and `None` when `mfe_r <= 0` (`mfe_mae.py`), so restricting to
winners lands it in `(0, 1]` with no clamping needed here.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_exit_quality.py`:

```python
import pytest

from swingbot.core.analytics import exit_quality as eq


def _entry(outcome, **kw):
    e = {"outcome": outcome, "mfe_r": 2.0, "mae_r": 0.4,
         "exit_efficiency": 0.5, "r_realized": 1.0}
    e.update(kw)
    return e


def test_efficiency_histogram_counts_winners_only():
    entries = [_entry("win", exit_efficiency=0.2), _entry("win", exit_efficiency=0.8),
               _entry("loss", exit_efficiency=-4.0)]
    out = eq.efficiency_histogram(entries, bins=2)
    assert out["n"] == 2
    assert sum(b["count"] for b in out["bins"]) == 2


def test_mae_histogram_excludes_losers_by_doctrine():
    """stops.py:19-29 -- a loser's MAE is at least the stop it hit, so
    including losers would ratchet stops wider on the trades that should
    have been cut."""
    entries = [_entry("win", mae_r=0.3), _entry("loss", mae_r=1.0)]
    out = eq.mae_histogram(entries, bins=2)
    assert out["n"] == 1


def test_null_fields_are_skipped_not_zeroed():
    entries = [_entry("win", exit_efficiency=None), _entry("win", exit_efficiency=0.6)]
    out = eq.efficiency_histogram(entries, bins=2)
    assert out["n"] == 1
    assert out["median"] == pytest.approx(0.6)


def test_empty_input_yields_no_rows_and_a_null_median():
    out = eq.efficiency_histogram([], bins=4)
    assert out == {"bins": [], "n": 0, "median": None}


def test_module_never_loads_the_journal(monkeypatch):
    """Every function takes entries in. Constructing a JournalStore here
    would make these pure functions I/O-bound and untestable offline."""
    import swingbot.core.analytics.journal as journal

    def explode(*a, **k):
        raise AssertionError("exit_quality must not load the journal")

    monkeypatch.setattr(journal, "JournalStore", explode)
    assert eq.efficiency_histogram([_entry("win")], bins=2)["n"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/analytics/test_exit_quality.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'swingbot.core.analytics.exit_quality'`.

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/analytics/exit_quality.py`:

```python
"""Aggregates over the exit-quality fields journal.py already writes onto
every closed trade -- mfe_r, mae_r and exit_efficiency (journal.py:199-201).

Every function takes `entries` as a parameter and loads nothing, matching
core/edge/stops.py's mae_informed_stop_mult / mfe_informed_tp2_r. The caller
loads, via JournalStore().entries() (journal.py:51).

The aggregates are WINNERS-ONLY, and that is doctrine rather than
convenience -- stops.py:19-29: "a LOSER's MAE is by definition at least the
stop it hit, so feeding losers in would ratchet stops wider on exactly the
trades that should have been cut." mfe_mae_points (Task A3) is the one
deliberate exception: plotting losers beside winners is its whole
diagnostic, and it sets no stop.
"""
from __future__ import annotations

from swingbot.core.analytics import metrics

_FIELDS = ("mfe_r", "mae_r", "exit_efficiency")


def _wins(entries: list[dict]) -> list[dict]:
    return [e for e in entries if str(e.get("outcome") or "").lower() == "win"]


def _values(entries: list[dict], field: str) -> list[float]:
    """Non-null values only. A null is missing data, not a zero -- see the
    coverage block in Task A3 for how the gap is reported instead."""
    out = []
    for e in entries:
        v = e.get(field)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:
            out.append(f)
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def _distribution(entries: list[dict], field: str, bins: int) -> dict:
    values = _values(_wins(entries), field)
    if not values:
        return {"bins": [], "n": 0, "median": None}
    return {"bins": metrics.histogram(values, bins),
            "n": len(values),
            "median": _median(values)}


def efficiency_histogram(entries: list[dict], bins: int = 10) -> dict:
    """Share of the favourable move actually banked, winners only.

    Winners-only gives a (0, 1] domain for free: exit_efficiency is
    r_real / mfe_r (mfe_mae.py), so on a winner both terms are positive.
    Negative efficiency arises only on losses, which this excludes."""
    return _distribution(entries, "exit_efficiency", bins)


def mae_histogram(entries: list[dict], bins: int = 10) -> dict:
    """Heat taken before the trade worked, winners only -- see the module
    docstring for why losers are excluded rather than filtered later."""
    return _distribution(entries, "mae_r", bins)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_exit_quality.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/exit_quality.py tests/analytics/test_exit_quality.py
git commit -m "feat(v78): winners-only exit-efficiency and MAE distributions"
```

---

### Task A3: exit_quality scatter points and coverage

**Files:**
- Modify: `swingbot/core/analytics/exit_quality.py` (append)
- Test: `tests/analytics/test_exit_quality.py` (append)

**Interfaces:**
- Consumes: `_values`, `_wins` from A2.
- Produces: `mfe_mae_points(entries) -> list[dict]` and
  `coverage(entries) -> dict`. A4 serves both; C4 plots the points and C3
  captions the coverage.

`coverage` exists because `exit_efficiency` is null on ~12% of production
journal rows and `mae_r` on ~5.6%. A chart that silently drops an eighth of the
book is the same defect as a rate quoted on `n=3`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_exit_quality.py`:

```python
def test_scatter_includes_losers_because_separation_is_the_point():
    pts = eq.mfe_mae_points([_entry("win"), _entry("loss")])
    assert {p["outcome"] for p in pts} == {"win", "loss"}


def test_scatter_skips_entries_missing_either_axis():
    pts = eq.mfe_mae_points([_entry("win", mae_r=None), _entry("win", mfe_r=None),
                             _entry("win")])
    assert len(pts) == 1
    assert set(pts[0]) == {"mae_r", "mfe_r", "r_realized", "outcome", "ticker", "strategy"}


def test_coverage_reports_the_gap_rather_than_hiding_it():
    entries = [_entry("win"), _entry("win", exit_efficiency=None)]
    cov = eq.coverage(entries)
    assert cov["exit_efficiency"] == {"non_null": 1, "total": 2, "pct": 50.0}
    assert cov["mfe_r"]["pct"] == 100.0


def test_coverage_of_nothing_is_zero_not_a_division_error():
    assert eq.coverage([])["mae_r"] == {"non_null": 0, "total": 0, "pct": 0.0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/analytics/test_exit_quality.py -k "scatter or coverage" -v`
Expected: FAIL — `AttributeError: module 'swingbot.core.analytics.exit_quality'
has no attribute 'mfe_mae_points'`.

- [ ] **Step 3: Write the implementation**

Append to `swingbot/core/analytics/exit_quality.py`:

```python
def mfe_mae_points(entries: list[dict]) -> list[dict]:
    """One point per closed trade for the MAE-vs-MFE scatter.

    All outcomes, deliberately -- the separation between winners and losers
    IS the diagnostic here, and unlike the histograms above this feeds no
    stop or target. An entry missing either axis is skipped rather than
    plotted at zero, which would invent a trade that took no heat.
    """
    points = []
    for e in entries:
        mae, mfe = e.get("mae_r"), e.get("mfe_r")
        if mae is None or mfe is None:
            continue
        try:
            mae_f, mfe_f = float(mae), float(mfe)
        except (TypeError, ValueError):
            continue
        if mae_f != mae_f or mfe_f != mfe_f:
            continue
        r = e.get("r_realized")
        points.append({
            "mae_r": round(mae_f, 4),
            "mfe_r": round(mfe_f, 4),
            "r_realized": round(float(r), 4) if r is not None else None,
            "outcome": str(e.get("outcome") or "unknown").lower(),
            "ticker": e.get("ticker") or "",
            "strategy": e.get("strategy") or "",
        })
    return points


def coverage(entries: list[dict]) -> dict:
    """How much of the book each exit-quality field actually covers.

    Rendered as a caption under every chart fed by one of these fields. In
    production exit_efficiency is null on ~12% of rows; a chart that drops
    those without saying so is lying by omission.
    """
    total = len(entries)
    out = {}
    for field in _FIELDS:
        non_null = len(_values(entries, field))
        out[field] = {"non_null": non_null, "total": total,
                      "pct": round(non_null / total * 100.0, 1) if total else 0.0}
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_exit_quality.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/exit_quality.py tests/analytics/test_exit_quality.py
git commit -m "feat(v78): MFE-vs-MAE points and exit-quality field coverage"
```

---

### Task A4: GET /analytics/exit-quality

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (new route, after
  `analytics_strategies` at `:247`)
- Test: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: `exit_quality.efficiency_histogram`, `mae_histogram`,
  `mfe_mae_points`, `coverage` (A2, A3); `aggregate.MIN_CELL_N` (A1);
  `metrics.exit_reason_split`, `metrics.hold_by_outcome`;
  `JournalStore().entries()`; `TradeLog`.
- Produces: `GET /api/v1/analytics/exit-quality` →
  `{exit_reasons, hold_by_outcome, efficiency, mae, scatter, coverage, min_cell_n}`.
  C1 fetches it.

A separate route rather than more keys on `/analytics/performance`: the page
already runs independent fetches per section, and a ~555-point scatter has no
business on the main performance call. The route selects and assembles; it
derives nothing, per the module docstring's *"UI renders, analytics computes."*

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_v1_analytics.py`, following the auth/client
fixtures already used in that file:

```python
def test_exit_quality_payload_shape(client, auth_headers):
    r = client.get("/api/v1/analytics/exit-quality", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == {"exit_reasons", "hold_by_outcome", "efficiency",
                         "mae", "scatter", "coverage", "min_cell_n"}
    assert body["min_cell_n"] == 20


def test_exit_quality_emits_all_nine_exit_reasons(client, auth_headers):
    """exit_reason_split returns a fixed 9-tuple with every reason present
    even at n=0 -- the route must not filter the empty ones out."""
    from swingbot.core.analytics.metrics import EXIT_REASONS
    body = client.get("/api/v1/analytics/exit-quality", headers=auth_headers).get_json()
    assert [row["reason"] for row in body["exit_reasons"]] == list(EXIT_REASONS)


def test_exit_quality_rejects_any_query_parameter(client, auth_headers):
    r = client.get("/api/v1/analytics/exit-quality?from=2026-01-01",
                   headers=auth_headers)
    assert r.status_code == 400


def test_exit_quality_serialises_none_as_null_not_zero(client, auth_headers):
    """An empty exit-reason bucket must arrive as null. Zero would read as
    'they all lost'."""
    body = client.get("/api/v1/analytics/exit-quality", headers=auth_headers).get_json()
    empty = [row for row in body["exit_reasons"] if row["n"] == 0]
    assert all(row["avg_r"] is None and row["win_rate"] is None for row in empty)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/admin/test_api_v1_analytics.py -k exit_quality -v`
Expected: FAIL — 404 on the route.

- [ ] **Step 3: Write the implementation**

Add to `swingbot/admin/api_v1/analytics.py`:

```python
@api_v1.route("/analytics/exit-quality", methods=["GET"])
@require_auth
def analytics_exit_quality():
    """Exit quality: what closed the trade, how much of the move was banked,
    how much heat it took, and whether losers are held longer than winners.

    Its own route rather than more keys on /performance: the scatter is one
    point per closed trade, and the Analytics workspace already fetches each
    section independently. All-time only -- range scoping is a v78 non-goal,
    so the guard below rejects every parameter rather than ignoring it.

    Selects and assembles. Every figure comes from core.analytics.
    """
    if request.args:
        raise ApiError("invalid",
                       f"unknown parameter {sorted(request.args)[0]!r}; "
                       "this route takes none", 400)

    from swingbot.core.analytics import exit_quality as eq
    from swingbot.core.analytics import metrics as m
    from swingbot.core.analytics.aggregate import MIN_CELL_N
    from swingbot.core.analytics.journal import JournalStore

    closed = [
        t for t in TradeLog().get_trades(status=None, limit=None) or []
        if t.get("status") in ("win", "loss", "closed")
    ]
    entries = JournalStore().entries()

    return jsonify({
        "exit_reasons": m.exit_reason_split(closed),
        "hold_by_outcome": m.hold_by_outcome(closed),
        "efficiency": eq.efficiency_histogram(entries),
        "mae": eq.mae_histogram(entries),
        "scatter": eq.mfe_mae_points(entries),
        "coverage": eq.coverage(entries),
        "min_cell_n": MIN_CELL_N,
    })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v78): GET /analytics/exit-quality"
```
