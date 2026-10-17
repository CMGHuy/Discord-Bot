# v164 Live loss watch. Implementation Plan, part 3: admin surface and full suite (LW5, LW6, LW7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task LW6" -A 400 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v164-live-loss-watch-design.md`](../specs/2026-10-15-v164-live-loss-watch-design.md) (D4, Testing, Parallelisation "Final")
**Bump:** bot minor; ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)

Global Constraints, Deviations, `## Parallelisation`, `## Where to work` (`$WT`, `$R`, never `cd`) and the task ledger live in the index: [`2026-10-15-v164-live-loss-watch_0-index.md`](2026-10-15-v164-live-loss-watch_0-index.md). Every task here obeys them. LW5 then LW6 (chain D4, may run beside part 2's chain D3); LW7 runs last, after every other task is committed.

# Phase 3: D4, admin surface

### Task LW5: Snapshot key + calibration API field

**Model:** sonnet — one dict key and one response field, contract tests updated

**Files:**
- Modify: `swingbot/core/analytics/snapshots.py` (`calibration_block`, `:57-62`, inside the legacy radon-C `build_snapshot`; exactly one dict key added, nothing else in the function changes)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_calibration`, `:716-725`)
- Modify: `tests/analytics/test_snapshots.py` (exact-key assert at `:26`; append two tests)
- Modify: `tests/admin/test_api_v1_analytics.py` (import line `:13`; `test_calibration_shape` at `:206-209`; append two tests)

**Interfaces:**
- Consumes (LW1, LW2 in part 1, all in `swingbot/core/analytics/calibration.py`): `live_loss_watch(trades: list[dict], registry_entries: list[dict], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict` returning `{"rows": list[dict], "counts": dict[str, int]}`; each row has exactly the keys `source, strategy, horizon, live_n, live_wr, live_expr, bound_upper, alert, registry_status, registry_window_kind, registry_run_date, registry_expr`; `counts` has exactly `WATCH_COUNT_KEYS = ("no_source", "unknown_strategy", "no_r", "manual_close", "no_entry_date")`. Existing: `build_snapshot(closed, starting_balance, registry_entries, *, weak_closed=())` (`snapshots.py:25`), `refresh_snapshot()` (`snapshots.py:~101`, already passes `weak_closed=weak_closed`, the only production caller), `_snapshot(fresh=False) -> dict` (`analytics.py:31`, module-level, looked up by name inside the route, so tests monkeypatch it), `assert_shape`, `NULLABLE_NUMBER`, `NULLABLE_STR` (`tests/admin/api_v1_contract.py`).
- Produces (LW6 relies on this exact shape):
  - snapshot `calibration["live_loss_watch"]` = `calibration.live_loss_watch([*closed, *weak_closed], registry_entries)` — both ledgers, production resample count.
  - `GET /api/v1/analytics/calibration` body = `{"deciles": list, "levels": list, "drift": list, "live_loss_watch": {"rows": list, "counts": dict}, "scope": "all-time"}`. A snapshot cached before deploy has no key: the API serves `{"rows": [], "counts": {}}` (index Deviation 1).

**Rules this task implements (spec D4; index Global Constraints, Deviation 1):**
- `build_snapshot` gains exactly one dict key (`build_snapshot` stays `C (20)` in radon). `drift` is unchanged and still computed from `closed` only (`badge_drift` is untouched).
- The watch population is `closed + weak_closed`. `build_snapshot` already turned `weak_closed` into a list (`weak_closed = list(weak_closed)`, before `calibration_block`), so `[*closed, *weak_closed]` is safe. `split_by_ledger` (in `refresh_snapshot`) already drops non-regular origins from both halves; the matcher filters again (`origin.is_regular`), harmlessly.
- No schema change: `live_loss_watch` is a key inside the JSON snapshot blob (`save_snapshot` writes JSON through `jsonio`).
- Report-only: neither file writes the registry or touches a badge.
- The cost: `build_snapshot` now runs one 10,000-resample week-cluster bootstrap per registry row that has at least one live trade (at most 22). Step 6 measures it; it is not tuned here (the constants are pre-registered).

- [ ] **Step 1: Write the failing snapshot tests**

In `$WT/tests/analytics/test_snapshots.py`, change the exact-key assert at `:26` from

```python
    assert set(snap["calibration"]) == {"deciles", "levels", "drift"}
```

to

```python
    assert set(snap["calibration"]) == {"deciles", "levels", "drift", "live_loss_watch"}
```

Then append at the end of the file:

```python
# ---------------------------------------------------------------------------
# v164 LW5: calibration.live_loss_watch, computed from BOTH ledgers
# ---------------------------------------------------------------------------
from swingbot.core.analytics import calibration as calibration_mod


def _watch_registry():
    """A confluence 4w row, the confluence pooled row, and one strategy row."""
    def row(source, strategy, horizon):
        return {"source": source, "strategy": strategy, "horizon": horizon, "status": "WEAK",
                "n": 300, "win_rate": 52.0, "expectancy_r": -0.05,
                "window": "2024-01-01..2025-12-31", "run_date": "2026-05-01"}
    return [row("confluence", "ALL", "4w"), row("confluence", "ALL", None),
            row("strategy", "RSI", None)]


def _watch_trade(i, status="loss", **over):
    """A closed trade inside the live-loss-watch population (opened after
    calibration.EXPR_WATCH_START = 2026-10-16, Berlin date)."""
    trade = _t(1, status)
    trade.update({"id": f"w{i}", "opened_at": f"2026-10-{19 + i:02d}T10:00:00+00:00",
                  "closed_at": f"2026-10-{20 + i:02d}T10:00:00+00:00"})
    trade.update(over)
    return trade


def _rows_by_key(watch):
    return {(r["source"], r["strategy"], r["horizon"]): r for r in watch["rows"]}


def test_snapshot_live_loss_watch_pools_both_ledgers():
    registry = _watch_registry()
    closed = [_t(1), _watch_trade(1), _watch_trade(2, "win")]   # _t(1) opened 2026-03: before the start
    weak_closed = [_watch_trade(3, source="strategy", strategy="RSI", horizon_key=None, ledger="weak")]

    snap = build_snapshot(closed, 10_000.0, registry, weak_closed=weak_closed)

    watch = snap["calibration"]["live_loss_watch"]
    assert watch == calibration_mod.live_loss_watch([*closed, *weak_closed], registry)
    rows = _rows_by_key(watch)
    assert rows[("confluence", "ALL", "4w")]["live_n"] == 2
    assert rows[("confluence", "ALL", None)]["live_n"] == 2
    assert rows[("strategy", "RSI", None)]["live_n"] == 1      # the weak-ledger trade counts
    assert set(watch["counts"]) == set(calibration_mod.WATCH_COUNT_KEYS)
    # badge_drift is unchanged: still the main ledger only, same call as before.
    assert snap["calibration"]["drift"] == calibration_mod.badge_drift(closed, registry)


def test_refresh_snapshot_threads_the_weak_ledger_into_the_watch(tmp_path, monkeypatch):
    snap_path = str(tmp_path / "analytics_snapshot.json")
    monkeypatch.setattr("swingbot.core.analytics.snapshots.DEFAULT_PATH", snap_path)
    trades = [_watch_trade(1), _watch_trade(2, "open"),
              _watch_trade(3, source="strategy", strategy="RSI", horizon_key=None, ledger="weak")]

    with patch("swingbot.core.tracking.performance.TradeLog") as MockLog, \
         patch("swingbot.core.planning.account.load_account_config", return_value={"base_balance": 10_000.0}), \
         patch("swingbot.core.backtesting.registry.load_registry", return_value=_watch_registry()):
        MockLog.return_value.get_trades.return_value = trades
        refresh_snapshot()

    rows = _rows_by_key(load_snapshot(path=snap_path)["calibration"]["live_loss_watch"])
    assert rows[("confluence", "ALL", "4w")]["live_n"] == 1     # the open trade is not in the population
    assert rows[("strategy", "RSI", None)]["live_n"] == 1       # weak ledger reached the watch
```

(`patch`, `refresh_snapshot` and `load_snapshot` are already imported further up this file; the new block sits below those imports.)

- [ ] **Step 2: Write the failing API tests**

In `$WT/tests/admin/test_api_v1_analytics.py`, change the contract import at `:13` from

```python
from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_error, assert_shape
```

to

```python
from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape
```

Replace `test_calibration_shape` (`:206-209`) with:

```python
def test_calibration_shape(seed, logged_in):
    seed()
    body = logged_in.get("/api/v1/analytics/calibration").get_json()
    assert_shape(body, {"deciles": list, "levels": list, "drift": list,
                        "live_loss_watch": dict, "scope": str})
    assert_shape(body["live_loss_watch"], {"rows": list, "counts": dict}, where="live_loss_watch")
```

Append at the end of the file:

```python
# ---------------------------------------------------------------------------
# v164 LW5: the live loss watch on /analytics/calibration
# ---------------------------------------------------------------------------
_LIVE_LOSS_ROW = {
    "source": str, "strategy": str, "horizon": NULLABLE_STR,
    "live_n": int, "live_wr": NULLABLE_NUMBER, "live_expr": NULLABLE_NUMBER,
    "bound_upper": NULLABLE_NUMBER, "alert": bool,
    "registry_status": NULLABLE_STR, "registry_window_kind": NULLABLE_STR,
    "registry_run_date": NULLABLE_STR, "registry_expr": NULLABLE_NUMBER,
}


def _served_watch():
    """A real watch from the real producer, so the contract is pinned on what
    calibration.live_loss_watch emits rather than on a hand-made dict."""
    from swingbot.core.analytics import calibration

    def row(horizon):
        return {"source": "confluence", "strategy": "ALL", "horizon": horizon, "status": "WEAK",
                "n": 300, "win_rate": 52.0, "expectancy_r": -0.05,
                "window": "2024-01-01..2025-12-31", "run_date": "2026-05-01"}
    trade = {"status": "loss", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
             "exit_price": 95.0, "opened_at": "2026-10-20T10:00:00+00:00",
             "source": "confluence", "strategy": "S/R Confluence", "horizon_key": "4w"}
    return calibration.live_loss_watch([trade], [row("4w"), row(None)], n_resamples=200)


def test_calibration_serves_the_live_loss_watch(seed, logged_in, monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api
    from swingbot.core.analytics import calibration

    seed()
    watch = _served_watch()
    snapshot = {"calibration": {"deciles": [], "levels": [], "drift": [], "live_loss_watch": watch}}
    monkeypatch.setattr(analytics_api, "_snapshot", lambda fresh=False: snapshot)

    body = logged_in.get("/api/v1/analytics/calibration").get_json()

    assert body["live_loss_watch"] == watch
    rows = body["live_loss_watch"]["rows"]
    assert [r["horizon"] for r in rows] == ["4w", None]       # Deviation 5: pooled row last
    for i, row in enumerate(rows):
        assert_shape(row, _LIVE_LOSS_ROW, where=f"live_loss_watch.rows[{i}]")
    assert set(body["live_loss_watch"]["counts"]) == set(calibration.WATCH_COUNT_KEYS)


def test_calibration_serves_an_empty_watch_from_a_pre_deploy_snapshot(seed, logged_in, monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api

    seed()
    snapshot = {"calibration": {"deciles": [], "levels": [], "drift": []}}   # cached before v164
    monkeypatch.setattr(analytics_api, "_snapshot", lambda fresh=False: snapshot)

    body = logged_in.get("/api/v1/analytics/calibration").get_json()

    assert body["live_loss_watch"] == {"rows": [], "counts": {}}
    assert body["drift"] == [] and body["scope"] == "all-time"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_snapshots.py`
Expected: FAIL — `test_build_snapshot_has_every_documented_key` (missing `live_loss_watch`) and the two new tests (`KeyError: 'live_loss_watch'`).

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: FAIL — `test_calibration_shape` (missing key `live_loss_watch`) and the two new tests (`KeyError: 'live_loss_watch'`).

- [ ] **Step 4: Add the snapshot key**

In `$WT/swingbot/core/analytics/snapshots.py`, replace the `calibration_block` literal (`:57-61`) with:

```python
    calibration_block = {
        "deciles": calibration.score_deciles(closed),
        "levels": calibration.level_calibration(closed),
        "drift": calibration.badge_drift(closed, registry_entries),
        # v164 D4: the pre-registered live loss watch, over BOTH ledgers
        # (spec D1); report-only, never feeds a badge. A JSON key, no schema.
        "live_loss_watch": calibration.live_loss_watch([*closed, *weak_closed], registry_entries),
    }
```

Nothing else in `build_snapshot` changes.

- [ ] **Step 5: Serve the field from the API**

In `$WT/swingbot/admin/api_v1/analytics.py`, replace `analytics_calibration` (`:716-725`) with:

```python
@api_v1.route("/analytics/calibration", methods=["GET"])
@require_auth
def analytics_calibration():
    calibration = _snapshot().get("calibration", {})
    return jsonify({
        "deciles": calibration.get("deciles", []),
        "levels": calibration.get("levels", []),
        "drift": calibration.get("drift", []),
        # v164 D4: {"rows": [...], "counts": {...}}. A snapshot cached before
        # the deploy has no key; serve the empty shape, never a 500.
        "live_loss_watch": calibration.get("live_loss_watch") or {"rows": [], "counts": {}},
        "scope": "all-time",
    })
```

- [ ] **Step 6: Run the tests to verify they pass, and measure the snapshot cost**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_snapshots.py`
Expected: all passed, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: all passed, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_analytics_perf.py`
Expected: passed (its registry is empty, so the watch adds nothing there).

Measure the realistic cost with the real 22-row registry and 300 live trades spread over 25 weeks (record the figure in the task report; it is not a gate):

```bash
PYTHONPATH=$WT python - <<'PY'
import datetime as dt, time
from swingbot.core.analytics.snapshots import build_snapshot
from swingbot.core.backtesting import registry

horizons = ["2w", "4w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m"]
trades = []
for i in range(300):
    day = dt.date(2026, 10, 19) + dt.timedelta(days=(i * 7 * 25) // 300)
    win = i % 3 == 0
    trades.append({"id": f"p{i}", "status": "win" if win else "loss", "direction": "bullish",
                   "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0 if win else 95.0,
                   "opened_at": f"{day.isoformat()}T10:00:00+00:00",
                   "closed_at": f"{day.isoformat()}T15:00:00+00:00",
                   "source": "confluence", "strategy": "S/R Confluence",
                   "horizon_key": horizons[i % len(horizons)]})
entries = registry.load_registry()
start = time.perf_counter()
snap = build_snapshot(trades, 10_000.0, entries)
print(f"build_snapshot with the watch: {time.perf_counter() - start:.2f}s, "
      f"{len(snap['calibration']['live_loss_watch']['rows'])} rows")
PY
```

Expected: a line `build_snapshot with the watch: <seconds>s, 22 rows`. If the figure is above 5 s, stop and report it to the controller (the resample count is pre-registered and is not lowered here; the remedy is the controller's call).

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/analytics/snapshots.py $WT/swingbot/admin/api_v1/analytics.py`
Expected: the `build_snapshot - C (20)` line is unchanged (still 20); `analytics_calibration` does not appear (rank A); no other new line compared with the same command on `main`.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/analytics/snapshots.py swingbot/admin/api_v1/analytics.py tests/analytics/test_snapshots.py tests/admin/test_api_v1_analytics.py
git -C $WT commit -m "feat(analytics): v164 LW5 live loss watch in the snapshot and on /analytics/calibration -- both ledgers, empty shape for a pre-deploy snapshot"
```

`git -C E:/Documents/Private/Projects/Discord-Bot status --short` must show the main tree unchanged by this task.

### Task LW6: Frontend: model, store computeds, columns, Edge tab renders live-loss-watch and drift tables

**Model:** sonnet — store/columns/tab inside one workspace, shapes fixed by LW5

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`AnalyticsCalibration`, `:615-620`; two new interfaces above it)
- Modify: `frontend/src/app/stores/analytics.store.ts` (models import block `:15-28`; calibration computeds `:591-593`)
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts` (imports `:1-12`; `DRIFT_COLUMNS` `:174-182`; new block after it)
- Modify: `frontend/src/app/workspaces/analytics/tabs/edge.ts` (whole file replaced; every existing panel and member kept)
- Modify: `frontend/src/app/stores/analytics.store.spec.ts` (two tests inserted)
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.spec.ts` (imports; one `describe` appended)
- Modify: `frontend/src/app/workspaces/analytics/tabs/edge.spec.ts` (whole file replaced; both existing tests kept, stubs widened)

**Interfaces:**
- Consumes (LW5): `GET /api/v1/analytics/calibration` → `{deciles, levels, drift, live_loss_watch: {rows, counts}, scope}`; each row `{source: str, strategy: str, horizon: str | null, live_n: int, live_wr: number | null (0–100), live_expr: number | null, bound_upper: number | null, alert: bool, registry_status: str | null, registry_window_kind: "TRAIN" | "VALIDATION" | null, registry_run_date: str | null, registry_expr: number | null}`; `counts` keys `no_source, unknown_strategy, no_r, manual_close, no_entry_date`. Rows arrive already ordered (index Deviation 5); the UI never re-sorts them. Existing: `ColumnDef<T>`, `EmptyState` (`ui/data-table/data-table.types.ts`), `DataTable` (`ui/data-table/data-table.ts`, selector `sb-data-table`, required inputs `rows`, `columns`, `visible`, `rowKey`; optional `emptyState`), `allKeys`, `count`, `rate`, `expectancy`, `delta` (`analytics.columns.ts`), `ABSENT`, `date` (`ui/format.ts`), `DriftRow` and `store.drift()` (`analytics.store.ts:87,593`, defined but rendered by no component before this task).
- Produces (nothing later consumes them; LW7 only runs the suites):
  - `models.ts`: `LiveLossRow`, `LiveLossWatch { rows: LiveLossRow[]; counts: Record<string, number> }`, `AnalyticsCalibration.live_loss_watch?: LiveLossWatch`
  - `analytics.store.ts`: `liveLossWatch: Signal<LiveLossRow[]>`, `liveLossCounts: Signal<Record<string, number>>`
  - `analytics.columns.ts`: `LIVE_LOSS_COLUMNS: ColumnDef<LiveLossRow>[]`, `liveLossLabel(row: LiveLossRow): string`, `liveLossCountsLine(counts: Record<string, number>): string`, `LIVE_LOSS_MEANING`, `LIVE_LOSS_LOOKS_CAVEAT`, `REGISTRY_CONTEXT_LABEL` (text identical to the Python constants in `calibration.py`)

**Rules this task implements (spec D4, Global Constraints "Meaning text"):**
- Host: the Analytics **Edge** tab (partner's choice). Two new full-width panels under the existing four: the live loss watch table, and under it the existing win-rate drift table (`DRIFT_COLUMNS` / `store.drift()`), both through `sb-data-table`.
- The meaning text `live ExpR for this row is below zero with ~90% one-sided confidence — not "the edge decayed versus its backtest"` is shown on the panel; the registry columns are headed `Registry …` and the panel states `Registry columns: backtest context — not comparable.`; the caveat `11 correlated looks per week; flags are prompts to investigate, not verdicts` is shown; the counts are shown (manual closes as included, the rest as excluded and counted).
- A calibration body without `live_loss_watch` (snapshot cached before deploy) yields an empty table with an empty state, never an error.
- Empty rows with `live_n` 0 are measured answers and are shown, never filtered (`known-traps.md`).
- `DRIFT_COLUMNS`' `drift_alert` column, declared without a `value` because nothing rendered it, gains a plain-text value (`DECAY` or `ABSENT`) so the table needs no cell template.

- [ ] **Step 1: Write the failing column tests**

In `$WT/frontend/src/app/workspaces/analytics/analytics.columns.spec.ts`, replace the two import lines at `:3-4` with:

```ts
import { LiveLossRow } from '../../api/models';
import { DecileRow, DriftRow, StrategyRow, TierRow } from '../../stores/analytics.store';
import { ABSENT } from '../../ui/format';
import {
  DECILE_COLUMNS,
  DRIFT_COLUMNS,
  LIVE_LOSS_COLUMNS,
  LIVE_LOSS_LOOKS_CAVEAT,
  LIVE_LOSS_MEANING,
  liveLossCountsLine,
  liveLossLabel,
  REGISTRY_CONTEXT_LABEL,
  soakLabel,
  STRATEGY_COLUMNS,
  TIER_COLUMNS,
} from './analytics.columns';
```

Append at the end of the file:

```ts
describe('live loss watch columns (v164)', () => {
  const row: LiveLossRow = {
    source: 'confluence', strategy: 'ALL', horizon: null, live_n: 24, live_wr: 41.7,
    live_expr: -0.25, bound_upper: -0.04, alert: true, registry_status: 'WEAK',
    registry_window_kind: 'VALIDATION', registry_run_date: '2026-05-01', registry_expr: -0.05,
  };
  const value = (key: string, r: LiveLossRow = row) =>
    LIVE_LOSS_COLUMNS.find((column) => column.key === key)?.value?.(r);

  it('labels a row by source, strategy and horizon, pooled when the horizon is null', () => {
    expect(liveLossLabel(row)).toBe('confluence / ALL / pooled');
    expect(liveLossLabel({ ...row, horizon: '4w' })).toBe('confluence / ALL / 4w');
    expect(value('row')).toBe('confluence / ALL / pooled');
  });

  it('formats the live figures and flags only an alert row', () => {
    expect(value('live_n')).toBe('24');
    expect(value('live_wr')).toBe('41.7%');
    expect(String(value('live_expr')).startsWith('\u2212')).toBe(true);
    expect(String(value('bound_upper'))).toContain('0.040');
    expect(value('alert')).toBe('BELOW ZERO');
    expect(value('alert', { ...row, alert: false })).toBe(ABSENT);
    expect(value('live_wr', { ...row, live_wr: null })).toBe(ABSENT);
    expect(value('bound_upper', { ...row, bound_upper: null })).toBe(ABSENT);
  });

  it('heads every registry column as registry context', () => {
    const registry = LIVE_LOSS_COLUMNS.filter((column) => column.key.startsWith('registry_'));
    expect(registry.map((column) => column.key)).toEqual(
      ['registry_status', 'registry_window_kind', 'registry_run_date', 'registry_expr']);
    expect(registry.every((column) => column.header.startsWith('Registry'))).toBe(true);
    expect(value('registry_window_kind')).toBe('VALIDATION');
    expect(value('registry_window_kind', { ...row, registry_window_kind: null })).toBe(ABSENT);
  });

  it('carries the pre-registered wording verbatim', () => {
    expect(LIVE_LOSS_MEANING).toBe(
      'live ExpR for this row is below zero with ~90% one-sided confidence — not "the edge decayed versus its backtest"');
    expect(LIVE_LOSS_LOOKS_CAVEAT).toBe(
      '11 correlated looks per week; flags are prompts to investigate, not verdicts');
    expect(REGISTRY_CONTEXT_LABEL).toBe('backtest context — not comparable');
  });

  it('states every exclusion count, zeros included, and manual closes as included', () => {
    expect(liveLossCountsLine({ no_source: 2, unknown_strategy: 0, no_r: 1, manual_close: 3, no_entry_date: 0 }))
      .toBe('Excluded, counted: no source 2 · unknown strategy 0 · no R 1 · no entry date 0. Manual closes included: 3.');
    expect(liveLossCountsLine({}))
      .toBe('Excluded, counted: no source 0 · unknown strategy 0 · no R 0 · no entry date 0. Manual closes included: 0.');
  });

  it('gives the drift decay column a plain-text value now that a table renders it', () => {
    const drift: DriftRow = { strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8, live_wr: 40, delta_wr: -25, drift_alert: true };
    const decay = DRIFT_COLUMNS.find((column) => column.key === 'drift_alert');
    expect(decay?.value?.(drift)).toBe('DECAY');
    expect(decay?.value?.({ ...drift, drift_alert: false })).toBe(ABSENT);
  });
});
```

- [ ] **Step 2: Write the failing store tests**

In `$WT/frontend/src/app/stores/analytics.store.spec.ts`, insert directly before the test `it('exposes deciles as a fixed-0-100 histogram', () => {` (same `describe`, so `tick`, `respondOverview`, `respondEdge` and `store` are in scope):

```ts
  it('exposes the live loss watch rows and counts, in the order the server sent them (v164)', () => {
    const rows = [
      { source: 'confluence', strategy: 'ALL', horizon: '4w', live_n: 24, live_wr: 41.7, live_expr: -0.25,
        bound_upper: -0.04, alert: true, registry_status: 'WEAK', registry_window_kind: 'VALIDATION',
        registry_run_date: '2026-05-01', registry_expr: -0.05 },
      { source: 'confluence', strategy: 'ALL', horizon: '2w', live_n: 3, live_wr: null, live_expr: 0.1,
        bound_upper: 0.6, alert: false, registry_status: 'WEAK', registry_window_kind: 'VALIDATION',
        registry_run_date: '2026-05-01', registry_expr: -0.02 },
    ];
    tick();
    respondOverview();
    store.setTab('edge');
    tick();
    respondEdge({ live_loss_watch: { rows, counts: { no_source: 2, manual_close: 1 } } });

    expect(store.liveLossWatch().map((row) => row.horizon)).toEqual(['4w', '2w']);
    expect(store.liveLossWatch()[0].alert).toBe(true);
    expect(store.liveLossCounts()).toEqual({ no_source: 2, manual_close: 1 });
  });

  it('reads a calibration body cached before v164 as an empty live loss watch', () => {
    tick();
    respondOverview();
    store.setTab('edge');
    tick();
    respondEdge();   // CALIBRATION carries no live_loss_watch key

    expect(store.liveLossWatch()).toEqual([]);
    expect(store.liveLossCounts()).toEqual({});
  });

```

- [ ] **Step 3: Replace the Edge tab spec with the widened stubs and the new tests**

Replace `$WT/frontend/src/app/workspaces/analytics/tabs/edge.spec.ts` with (the two existing `EdgeTab` tests and the breakpoint test are kept, same assertions; their stubs gain the three signals the tab now reads):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { LIVE_LOSS_LOOKS_CAVEAT, LIVE_LOSS_MEANING } from '../analytics.columns';
import { EdgeTab } from './edge';

const LOSS_ROW = {
  source: 'confluence', strategy: 'ALL', horizon: '4w', live_n: 24, live_wr: 41.7, live_expr: -0.25,
  bound_upper: -0.04, alert: true, registry_status: 'WEAK', registry_window_kind: 'VALIDATION',
  registry_run_date: '2026-05-01', registry_expr: -0.05,
};
const DRIFT_ROW = { strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8, live_wr: 40, delta_wr: -25, drift_alert: true };

function stub(overrides: Record<string, unknown> = {}) {
  return {
    scopeN: signal(30),
    performance: signal({ win_rate: 55, rolling_wr: [], rolling_exp_r: [] }),
    strategies: signal({ cumulative: {} }),
    calibration: signal({ deciles: [] }),
    liveLossWatch: signal([]),
    liveLossCounts: signal({}),
    drift: signal([]),
    ...overrides,
  };
}

function render(store: Record<string, unknown>) {
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: AnalyticsStore, useValue: store }],
  });
  const fixture = TestBed.createComponent(EdgeTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('EdgeTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('shows scoped rolling measures and all-time calibration', () => {
    const { el } = render(stub({
      performance: signal({ win_rate: 55, rolling_wr: [{ date: '2026-08-01', win_rate: 55 }], rolling_exp_r: [{ date: '2026-08-01', exp_r: .2 }] }),
      strategies: signal({ cumulative: { RSI: [{ date: '2026-08-01', cum_r: 1 }] } }),
      calibration: signal({ deciles: [{ decile: '80-89', win_rate: 83 }] }),
    }));
    expect(el.querySelectorAll('sb-line-chart').length).toBeGreaterThanOrEqual(2);
    expect(el.querySelector('sb-small-multiples')).not.toBeNull();
    expect(el.textContent).toContain('all-time');
  });

  // A screenshot pass (v94 V2) once caught 2/3 * 100 = 66.66666... rendered
  // raw in the Calibration deciles panel, overflowing its container -- the
  // fix rounds a decile's win rate to one decimal before it reaches the bar.
  it('rounds a decile win rate instead of overflowing the panel with a raw float', () => {
    const { fixture, el } = render(stub({ calibration: signal({ deciles: [{ decile: '60-69', win_rate: 200 / 3 }] }) }));
    expect(fixture.componentInstance.decileBins()).toEqual([{ label: '60-69', count: 66.7 }]);
    expect(el.textContent).not.toContain('66.66666');
  });

  // v164 D4: the live loss watch, with its meaning, the registry-context
  // label, the counts and the correlated-looks caveat, on the Edge tab.
  it('renders the live loss watch with its meaning, registry label, counts and caveat', () => {
    const { el } = render(stub({
      liveLossWatch: signal([LOSS_ROW]),
      liveLossCounts: signal({ no_source: 2, unknown_strategy: 0, no_r: 1, manual_close: 3, no_entry_date: 0 }),
    }));
    const text = el.textContent ?? '';
    expect(text).toContain('Live loss watch');
    expect(text).toContain(LIVE_LOSS_MEANING);
    expect(text).toContain('Registry columns: backtest context — not comparable.');
    expect(text).toContain(LIVE_LOSS_LOOKS_CAVEAT);
    expect(text).toContain('confluence / ALL / 4w');
    expect(text).toContain('BELOW ZERO');
    expect(text).toContain('no source 2');
    expect(text).toContain('Manual closes included: 3.');
  });

  // DRIFT_COLUMNS and store.drift() existed for a long time with no
  // component rendering them; v164 puts the table under the live loss watch.
  it('renders the win-rate drift table under the live loss watch', () => {
    const { el } = render(stub({ liveLossWatch: signal([LOSS_ROW]), drift: signal([DRIFT_ROW]) }));
    const text = el.textContent ?? '';
    expect(el.querySelectorAll('sb-data-table').length).toBe(2);
    expect(text).toContain('Win-rate drift');
    expect(text).toContain('MACD');
    expect(text).toContain('DECAY');
    expect(text.indexOf('Live loss watch')).toBeLessThan(text.indexOf('Win-rate drift'));
  });

  it('shows an empty state, and no counts line, when the snapshot predates the watch', () => {
    const { el } = render(stub());
    const text = el.textContent ?? '';
    expect(text).toContain('No live loss watch rows yet');
    expect(text).not.toContain('Manual closes included');
    expect(text).toContain(LIVE_LOSS_MEANING);
  });
});

describe('edge.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/edge.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

- [ ] **Step 4: Run the specs to verify they fail**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include src/app/workspaces/analytics/analytics.columns.spec.ts`
Expected: FAIL — the build cannot resolve `LIVE_LOSS_COLUMNS`, `liveLossLabel`, `LiveLossRow`, ….

Run: `npm --prefix $WT/frontend run test -- --watch=false --include src/app/stores/analytics.store.spec.ts`
Expected: FAIL — `store.liveLossWatch is not a function`.

Run: `npm --prefix $WT/frontend run test -- --watch=false --include src/app/workspaces/analytics/tabs/edge.spec.ts`
Expected: FAIL — the new three tests (`Live loss watch` not in the text); the two kept tests pass.

(If a run ends after exactly 60 s with `Timeout waiting for worker to respond` and `no tests`, that is the known load flake, `docs/claude/testing-cost.md` § Frontend: re-run once the machine is quiet.)

- [ ] **Step 5: Add the API model**

In `$WT/frontend/src/app/api/models.ts`, replace `AnalyticsCalibration` (`:615-620`) with:

```ts
/** v164: one row of the pre-registered live loss watch (spec D2), as
 *  `calibration.live_loss_watch` emits it. `alert` means live ExpR for this
 *  row is below zero with ~90% one-sided confidence; the `registry_*` fields
 *  are backtest context only, never comparable with the live figures. */
export interface LiveLossRow {
  source: string;
  strategy: string;
  /** `null` is the pooled row of its `(source, strategy)`. */
  horizon: string | null;
  live_n: number;
  /** 0–100 over wins and losses only; `null` when there is neither. */
  live_wr: number | null;
  live_expr: number | null;
  /** 90th percentile of the week-clustered bootstrap of mean R. */
  bound_upper: number | null;
  alert: boolean;
  registry_status: string | null;
  registry_window_kind: 'TRAIN' | 'VALIDATION' | null;
  registry_run_date: string | null;
  registry_expr: number | null;
}

/** Rows already ordered by the server (alerts first, then confluence by
 *  horizon with the pooled row last, then strategies by name). */
export interface LiveLossWatch {
  rows: LiveLossRow[];
  counts: Record<string, number>;
}

export interface AnalyticsCalibration {
  deciles: unknown[];
  levels: unknown[];
  drift: unknown[];
  /** Absent on a snapshot cached before v164; the API then sends the empty
   *  shape, but the client tolerates the key missing as well. */
  live_loss_watch?: LiveLossWatch;
  scope: 'all-time';
}
```

- [ ] **Step 6: Add the store computeds**

In `$WT/frontend/src/app/stores/analytics.store.ts`, add `LiveLossRow,` and `LiveLossWatch,` to the `import { … } from '../api/models';` block (`:15-28`, keep it alphabetical: after `BookScope`). Then, directly under the `drift:` computed (`:593`), add:

```ts
    /** v164 D4: the live loss watch, in the server's order. A body cached
     *  before the deploy has no key, which reads as an empty watch. */
    liveLossWatch: computed<LiveLossRow[]>(() => calibration()?.live_loss_watch?.rows ?? []),
    liveLossCounts: computed<LiveLossWatch['counts']>(() => calibration()?.live_loss_watch?.counts ?? {}),
```

- [ ] **Step 7: Add the columns, labels and wording**

In `$WT/frontend/src/app/workspaces/analytics/analytics.columns.ts`, change the first import line (`:1`) to:

```ts
import { AnalyticsByDimensionRow, AnalyticsUnit, LiveLossRow } from '../../api/models';
```

Replace the `drift_alert` entry inside `DRIFT_COLUMNS` (`:181`):

```ts
  { key: 'drift_alert', header: 'Decay' },
```

with:

```ts
  // v164: the Edge tab renders this table now; a plain value, no cell slot.
  { key: 'drift_alert', header: 'Decay', value: (r) => (r.drift_alert ? 'DECAY' : ABSENT) },
```

Then insert directly after the closing `];` of `DRIFT_COLUMNS`:

```ts
/* -- live loss watch (v164) ------------------------------------------------
 *
 * The wording below is pre-registered with the rule (spec v164 D2) and is the
 * same text the Discord digest and the ops-channel flag carry
 * (`swingbot/core/analytics/calibration.py`). Change one, change all three.
 */

export const LIVE_LOSS_MEANING =
  'live ExpR for this row is below zero with ~90% one-sided confidence — not "the edge decayed versus its backtest"';
export const LIVE_LOSS_LOOKS_CAVEAT =
  '11 correlated looks per week; flags are prompts to investigate, not verdicts';
export const REGISTRY_CONTEXT_LABEL = 'backtest context — not comparable';

/** `confluence / ALL / 4w`; the `horizon: null` row is the pooled one. */
export function liveLossLabel(row: LiveLossRow): string {
  return `${row.source} / ${row.strategy} / ${row.horizon ?? 'pooled'}`;
}

/** Every exclusion is counted, never dropped (spec D1); a zero is shown as
 *  a zero. Manual closes are in the population, so they read as included. */
const EXCLUDED_COUNTS: readonly (readonly [string, string])[] = [
  ['no_source', 'no source'],
  ['unknown_strategy', 'unknown strategy'],
  ['no_r', 'no R'],
  ['no_entry_date', 'no entry date'],
];

export function liveLossCountsLine(counts: Record<string, number>): string {
  const excluded = EXCLUDED_COUNTS.map(([key, label]) => `${label} ${counts[key] ?? 0}`).join(' · ');
  return `Excluded, counted: ${excluded}. Manual closes included: ${counts['manual_close'] ?? 0}.`;
}

/** Live figures first, then the registry's, each headed "Registry …": the
 *  panel states once that those are backtest context, not comparable. */
export const LIVE_LOSS_COLUMNS: ColumnDef<LiveLossRow>[] = [
  { key: 'row', header: 'Row', value: (r) => liveLossLabel(r) },
  { key: 'live_n', header: 'Live N', numeric: true, value: (r) => count(r.live_n) },
  { key: 'live_wr', header: 'Live WR', numeric: true, value: (r) => rate(r.live_wr) },
  { key: 'live_expr', header: 'Live ExpR', numeric: true, value: (r) => expectancy(r.live_expr) },
  { key: 'bound_upper', header: 'ExpR 90% upper', numeric: true, value: (r) => expectancy(r.bound_upper) },
  { key: 'alert', header: 'Alert', value: (r) => (r.alert ? 'BELOW ZERO' : ABSENT) },
  { key: 'registry_status', header: 'Registry badge', value: (r) => r.registry_status ?? ABSENT },
  { key: 'registry_window_kind', header: 'Registry window', value: (r) => r.registry_window_kind ?? ABSENT },
  { key: 'registry_run_date', header: 'Registry run', value: (r) => (r.registry_run_date ? date(r.registry_run_date) : ABSENT) },
  { key: 'registry_expr', header: 'Registry ExpR', numeric: true, value: (r) => expectancy(r.registry_expr) },
];
```

(`ABSENT`, `date`, `count`, `rate`, `expectancy` and `ColumnDef` are already imported or defined in this file.)

- [ ] **Step 8: Render both tables on the Edge tab**

Replace `$WT/frontend/src/app/workspaces/analytics/tabs/edge.ts` with (the four existing panels, their members and the `639px` media query are unchanged; two full-width panels are added under them):

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { LiveLossRow } from '../../../api/models';
import { AnalyticsStore, DriftRow } from '../../../stores/analytics.store';
import { DataTable } from '../../../ui/data-table/data-table';
import { EmptyState } from '../../../ui/data-table/data-table.types';
import { Histogram } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelHeader } from '../../../ui/panel-header';
import { MultiplePane, SmallMultiples } from '../../../ui/small-multiples';
import {
  allKeys,
  DRIFT_COLUMNS,
  LIVE_LOSS_COLUMNS,
  LIVE_LOSS_LOOKS_CAVEAT,
  LIVE_LOSS_MEANING,
  liveLossCountsLine,
  liveLossLabel,
  REGISTRY_CONTEXT_LABEL,
} from '../analytics.columns';

/** Scoped edge monitoring above all-time validation evidence; under it, the
 *  v164 live loss watch and the win-rate drift table it sits beside. */
@Component({
  selector: 'sb-edge-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, LineChart, SmallMultiples, Histogram, DataTable],
  template: `<div class="panels">
    <sb-panel><sb-panel-header title="Rolling win rate" [n]="store.scopeN()"/><sb-line-chart [series]="rollingWr()" [referenceLine]="performance()?.win_rate ?? null" [valueFormat]="pct"/></sb-panel>
    <sb-panel><sb-panel-header title="Rolling ExpR" [n]="store.scopeN()"/><sb-line-chart [series]="rollingExpR()" [referenceLine]="0" [valueFormat]="r"/></sb-panel>
    <sb-panel><sb-panel-header title="Strategy cumulative R" [n]="store.scopeN()"/><sb-small-multiples [panes]="strategyPanes()" [valueFormat]="r"/></sb-panel>
    <sb-panel><sb-panel-header title="Calibration deciles" [allTime]="true"/><sb-histogram [bins]="decileBins()"/></sb-panel>
    <sb-panel class="wide">
      <sb-panel-header title="Live loss watch" [hint]="liveLossHint"/>
      <p class="note">An alert means: {{ meaning }}.</p>
      <sb-data-table [rows]="store.liveLossWatch()" [columns]="liveLossColumns" [visible]="liveLossVisible" [rowKey]="liveLossKey" [emptyState]="liveLossEmpty"/>
      <p class="note">Registry columns: {{ contextLabel }}.</p>
      @if (store.liveLossWatch().length) { <p class="note">{{ countsLine() }}</p> }
      <p class="note">{{ caveat }}.</p>
    </sb-panel>
    <sb-panel class="wide">
      <sb-panel-header title="Win-rate drift" [allTime]="true" [hint]="driftHint"/>
      <sb-data-table [rows]="store.drift()" [columns]="driftColumns" [visible]="driftVisible" [rowKey]="driftKey" [emptyState]="driftEmpty"/>
    </sb-panel>
  </div>`,
  styles: `.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}.wide{grid-column:1/-1}.note{margin:var(--space-6) 0 0;color:var(--text-muted);font-size:var(--text-table)}@media(max-width:639px){.panels{grid-template-columns:1fr}}`,
})
export class EdgeTab {
  readonly store = inject(AnalyticsStore);
  readonly performance = computed(() => this.store.performance());
  readonly pct = (value: number) => `${value.toFixed(1)}%`;
  readonly r = (value: number) => `${value.toFixed(2)}R`;
  readonly rollingWr = computed<LineChartSeries[]>(() => [{ name: 'Win rate', points: (this.performance()?.rolling_wr ?? []).map((point) => ({ date: point.date, value: point.win_rate })) }]);
  readonly rollingExpR = computed<LineChartSeries[]>(() => [{ name: 'ExpR', points: (this.performance()?.rolling_exp_r ?? []).map((point) => ({ date: point.date, value: point.exp_r })) }]);
  readonly strategyPanes = computed<MultiplePane[]>(() =>
    Object.entries(this.store.strategies()?.cumulative ?? {}).map(([title, rows]) => ({
      title, series: [{ name: title, points: rows.map((point) => ({ date: point.date, value: point.cum_r })) }],
    })));
  // HistogramBin.count is otherwise always an integer observation count; a
  // calibration decile's win rate is a percentage borrowing that same bar,
  // so it must be rounded before display -- a screenshot pass once caught
  // an unrounded division (2/3 -> 66.66666...) overflowing the panel.
  readonly decileBins = computed(() => ((this.store.calibration()?.deciles ?? []) as { decile: string; win_rate: number | null }[])
    .filter((row) => row.win_rate !== null).map((row) => ({ label: row.decile, count: Math.round(row.win_rate! * 10) / 10 })));

  /* -- v164 D4: live loss watch ------------------------------------------ */
  readonly meaning = LIVE_LOSS_MEANING;
  readonly caveat = LIVE_LOSS_LOOKS_CAVEAT;
  readonly contextLabel = REGISTRY_CONTEXT_LABEL;
  readonly liveLossHint = 'Live trades opened on or after 2026-10-16 (Berlin date), both ledgers, manual closes included. Ignores the scope filter. Rows keep the server order: alerts first.';
  readonly liveLossColumns = LIVE_LOSS_COLUMNS;
  readonly liveLossVisible = allKeys(LIVE_LOSS_COLUMNS);
  readonly liveLossKey = (row: LiveLossRow) => liveLossLabel(row);
  readonly liveLossEmpty: EmptyState = {
    title: 'No live loss watch rows yet',
    hint: 'The analytics snapshot predates this table; a snapshot older than an hour is rebuilt on the next request.',
  };
  readonly countsLine = computed(() => liveLossCountsLine(this.store.liveLossCounts()));

  /* -- win-rate drift (badge_drift, unchanged; first rendered in v164) ---- */
  readonly driftHint = 'Live win rate against the out-of-sample win rate of validated registry rows (badge_drift).';
  readonly driftColumns = DRIFT_COLUMNS;
  readonly driftVisible = allKeys(DRIFT_COLUMNS);
  readonly driftKey = (row: DriftRow) => row.strategy;
  readonly driftEmpty: EmptyState = {
    title: 'No drift rows',
    hint: 'badge_drift reports only validated registry rows.',
  };
}
```

- [ ] **Step 9: Run the specs to verify they pass**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include src/app/workspaces/analytics/analytics.columns.spec.ts`
Expected: all passed.

Run: `npm --prefix $WT/frontend run test -- --watch=false --include src/app/stores/analytics.store.spec.ts`
Expected: all passed.

Run: `npm --prefix $WT/frontend run test -- --watch=false --include src/app/workspaces/analytics/tabs/edge.spec.ts`
Expected: all passed (5 `EdgeTab` tests + the breakpoint test).

Neighbours (the workspace renders the tab through the real store):
Run: `npm --prefix $WT/frontend run test -- --watch=false --include "src/app/workspaces/analytics/**/*.spec.ts"`
Expected: all passed.

If the "renders the win-rate drift table" test finds the text but not two `sb-data-table` hosts, the table is rendering its card layout at the test viewport; the host element is still present, so look for a template typo rather than loosening the assertion.

- [ ] **Step 10: Type-check the templates**

Run: `npm --prefix $WT/frontend run build`
Expected: build succeeds with no new errors or warnings (the strict template checker validates the `sb-data-table` generic inputs and `[hint]`).

- [ ] **Step 11: Commit**

```bash
git -C $WT add frontend/src/app/api/models.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/workspaces/analytics/analytics.columns.ts frontend/src/app/workspaces/analytics/tabs/edge.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/analytics.columns.spec.ts frontend/src/app/workspaces/analytics/tabs/edge.spec.ts
git -C $WT commit -m "feat(ui): v164 LW6 live loss watch and win-rate drift tables on the Analytics Edge tab -- meaning text, registry-context label, counts, caveat"
```

`git -C E:/Documents/Private/Projects/Discord-Bot status --short` must show the main tree unchanged by this task.

# Phase 4: final gate

### Task LW7: Full suite, once

**Model:** haiku — runs one command, no code

**Files:** none (verification only; a fix, if one is needed, belongs to the task that owns the failing file and is committed under that task's scope).

**Interfaces:**
- Consumes: every commit of LW1..LW6 on branch `2026-10-15-v164-live-loss-watch` in `$WT`.
- Produces: the green full-suite record `/close-out` needs (bot minor, ui minor per the `**Bump:**` header; no task edits `VERSION.json`).

**Rules (CLAUDE.md "Commands", index Global Constraints):** green means `0 failed` and `0 xfailed`; a changed pass count is not a failure. A failed test is fixed and re-run alone (`testrun.py file …`), never by re-running the whole suite. The full suite runs once for this plan, here, through the `test-runner` subagent so its output stays out of the controller's context. No full suite after merging to `main`.

- [ ] **Step 1: Confirm every task is committed**

Run: `git -C $WT log --oneline main..HEAD`
Expected: six commits, one per task; their subjects name `LW1` .. `LW6` (`feat(analytics): v164 LW1 …`, `… LW2 …`, `feat(v164): … (LW3)`, `feat(v164): … (LW4)`, `feat(analytics): v164 LW5 …`, `feat(ui): v164 LW6 …`), plus any scoped fix commits; LW3/LW4 may interleave with LW5/LW6 (they ran in parallel).

Run: `git -C $WT status --short`
Expected: empty.

Run: `git -C $WT diff --stat main...HEAD`
Expected: only the files named in the index task ledger (no `VERSION.json`, no `validation_registry.json`, no `tests/suites.toml`, no `docs/superpowers/plans/` file, nothing from v162).

- [ ] **Step 2: Full Python suite (dispatch the `test-runner` subagent)**

Run: `python $WT/scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. Report the pass/skip counts and the elapsed time.

On a failure: read the failing test from the parked log the runner names, fix it in the owning task's files, re-run only it (`python $WT/scripts/dev/testrun.py file <test path>`), and commit the fix scoped to that task (`fix(<area>): v164 LW<n> …`). Do not re-run the full suite.

- [ ] **Step 3: Full frontend suite**

Run: `npm --prefix $WT/frontend run test -- --watch=false`
Expected: every spec file passed, `0 failed`. (A run that ends after exactly 60 s with `Timeout waiting for worker to respond` and `no tests` is the known load flake, `docs/claude/testing-cost.md` § Frontend: wait for the Python run to finish and re-run once.)

Run: `npm --prefix $WT/frontend run build`
Expected: build succeeds.

- [ ] **Step 4: Complexity, once over every touched Python file**

Run (worktree):

```bash
python -m radon cc -s -n C $WT/swingbot/core/analytics/calibration.py $WT/swingbot/core/analytics/snapshots.py $WT/swingbot/admin/api_v1/analytics.py $WT/swingbot/core/tracking/live_loss_watch.py $WT/swingbot/core/tracking/retrospective.py $WT/swingbot/commands/scanning/loops.py $WT/swingbot/commands/scanning/notices.py
```

Run (main, for the baseline; `live_loss_watch.py` does not exist there):

```bash
python -m radon cc -s -n C $R/swingbot/core/analytics/calibration.py $R/swingbot/core/analytics/snapshots.py $R/swingbot/admin/api_v1/analytics.py $R/swingbot/core/tracking/retrospective.py $R/swingbot/commands/scanning/loops.py $R/swingbot/commands/scanning/notices.py
```

Expected: the worktree output lists exactly the functions the main output lists, each with the same score (`build_daily_retrospective - F (106)` and `build_snapshot - C (20)` unchanged; `badge_drift - C (13)` unchanged); no function from `live_loss_watch.py` and no new v164 helper appears. Any new line or higher score is a failure of the owning task: split the function there, re-run that task's narrow tests, commit scoped.

- [ ] **Step 5: Report and hand back**

Report to the controller: the Python counts (`passed / skipped / 0 failed / 0 xfailed`, elapsed), the frontend spec count, the build result, the radon comparison, and the Step 6 snapshot timing LW5 recorded. Then the controller runs `/close-out` (bump bot minor, ui minor; move the spec and the plan files to `implemented/`; remove the worktree after the merge).

- [ ] **Step 6: Commit**

Nothing to commit when Steps 2-4 are green on the first run. If a fix was needed, it was committed in Step 2 or Step 4 under the owning task's scope; confirm with `git -C $WT status --short` (expected: empty).

`git -C E:/Documents/Private/Projects/Discord-Bot status --short` must show the main tree unchanged by this plan.
