# v164 Live loss watch. Implementation Plan, part 1: matcher and loss rule (LW1, LW2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task LW2" -A 400 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v164-live-loss-watch-design.md`](../specs/2026-10-15-v164-live-loss-watch-design.md) (D1, D2, Testing)
**Bump:** bot minor; ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)

Global Constraints, Deviations, `## Parallelisation`, `## Where to work` (`$WT`, `$R`, never `cd`) and the task ledger live in the index: [`2026-10-15-v164-live-loss-watch_0-index.md`](2026-10-15-v164-live-loss-watch_0-index.md). Every task here obeys them. LW1 then LW2, sequential (same two files).

# Phase 1: D1 and D2, pure analytics

### Task LW1: Population matcher: `match_live_rows`, Berlin entry date, count buckets

**Model:** sonnet — one module, behaviour fixed by spec D1

**Files:**
- Modify: `swingbot/core/analytics/calibration.py` (imports at `:19-23`; append after `badge_drift`, which ends at `:138`; `badge_drift` itself is not touched)
- Create: `tests/analytics/test_live_loss_watch.py`

**Interfaces:**
- Consumes: `metrics.r_multiple(trade: dict) -> float | None` (`swingbot/core/analytics/metrics.py:173`); `origin.is_regular(record) -> bool` (`swingbot/core/tracking/origin.py:24`, pure module, no imports); `BERLIN_TZ` (`swingbot/core/market/session.py:16`).
- Produces (LW2, LW3, LW5 rely on these exact names):
  - `EXPR_WATCH_START = dt.date(2026, 10, 16)`
  - `WATCH_STATUSES = ("win", "loss", "closed")`
  - `WATCH_COUNT_KEYS = ("no_source", "unknown_strategy", "no_r", "manual_close", "no_entry_date")`
  - `LiveTrade = namedtuple("LiveTrade", "entry_date r status")` — `entry_date` is the Berlin-date ISO string `"YYYY-MM-DD"` (what `stats.iso_week_key` slices), `r` is `metrics.r_multiple(trade)` unchanged, `status` the trade status.
  - `@dataclass(frozen=True) class MatchResult: buckets: dict[tuple[str, str, str | None], list[LiveTrade]]; counts: dict[str, int]` — one bucket per registry row key (empty list when nothing matched), `counts` has exactly the `WATCH_COUNT_KEYS`.
  - `row_key(entry: dict) -> tuple[str, str, str | None]` — `(source, strategy, horizon)` of a registry row.
  - `berlin_entry_date(trade: dict) -> str | None` — Berlin date of `opened_at` (naive timestamps read as UTC, same as `retrospective._to_berlin`), `None` when missing or unparseable.
  - `match_live_rows(trades: list[dict], registry_entries: list[dict]) -> MatchResult`

**Rules this task implements (spec D1, index Global Constraints):**
- Population: `status in WATCH_STATUSES`, `origin.is_regular(trade)`, Berlin date of `opened_at` `>= EXPR_WATCH_START`. Both ledgers: the `ledger` key is never read.
- A trade outside the population by status, origin or start date is not counted anywhere (it is not part of the pre-registered population). A trade whose entry date cannot be read is counted in `no_entry_date` (it cannot be placed before or after the start, so it is reported, not silently dropped).
- Key `(source, strategy', horizon_key)`, `strategy' = "ALL"` when `source == "confluence"`, else `trade["strategy"]`. Matched on `source`, so a confluence trade carrying its primary strategy name (`builders.py:687` path) and an old `"S/R Confluence"` trade both land on `confluence / ALL`.
- Exclusion order, first hit wins, each counted: `no_source` (no `source` key or a falsy value), `unknown_strategy` (no pooled row `(source, strategy', None)` in the registry), `no_r` (`r_multiple` is `None`).
- A kept trade goes to its exact-horizon row when that row exists, and always to its pooled row; exact == pooled (no `horizon_key`) means one append, never two. A `1w` confluence trade (no `1w` row) feeds the pooled row only and is **not** counted as unmatched.
- `manual_close` counts kept trades with `status == "closed"`: they are included in the buckets **and** counted.
- `calibration.py` must not import `swingbot.core.tracking.retrospective` (it imports `calibration`, `retrospective.py:29`).

- [ ] **Step 0: Worktree**

Use the `worktree-lifecycle` skill. If `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `.claude/worktrees/2026-10-15-v164-live-loss-watch`, reuse it; otherwise create it from `main`:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v164-live-loss-watch -b 2026-10-15-v164-live-loss-watch main
```

`$WT` below is that path. Never `cd`; never touch the main tree's v162 files.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/analytics/test_live_loss_watch.py`:

```python
"""v164 live loss watch: the D1 matcher (LW1) and the D2 loss rule (LW2).

Pure functions, plain dict fixtures, no DB. Trade timestamps are UTC ISO like
`performance.log_trade` writes them; every day boundary is a Berlin date."""
import datetime as dt

import pytest

from swingbot.core.analytics import calibration
from swingbot.core.analytics.calibration import (
    EXPR_WATCH_START,
    WATCH_COUNT_KEYS,
    LiveTrade,
    MatchResult,
    berlin_entry_date,
    match_live_rows,
    row_key,
)

CONF_HORIZONS = ("2w", "4w", "2m")


def _reg(source, strategy, horizon, status="WEAK", expr=-0.2,
         window="2024-01-01..2025-12-31", run_date="2026-07-17"):
    return {"source": source, "strategy": strategy, "horizon": horizon, "status": status,
            "n": 400, "win_rate": 48.8, "expectancy_r": expr, "window": window,
            "run_date": run_date}


def _registry():
    rows = [_reg("confluence", "ALL", h) for h in CONF_HORIZONS]
    rows.append(_reg("confluence", "ALL", None))
    rows.append(_reg("strategy", "Fibonacci", None, status="VALIDATED", expr=0.105))
    return rows


def _trade(**over):
    """A closed, regular-lane, post-start confluence 4w win of +2R."""
    base = {"status": "win", "source": "confluence", "strategy": "S/R Confluence",
            "horizon_key": "4w", "opened_at": "2026-10-19T14:00:00+00:00",
            "closed_at": "2026-10-23T14:00:00+00:00", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0, "legs": [],
            "ledger": "main"}
    base.update(over)
    return base


CONF_4W = ("confluence", "ALL", "4w")
CONF_POOLED = ("confluence", "ALL", None)
FIB_POOLED = ("strategy", "Fibonacci", None)


def _sizes(result: MatchResult) -> dict:
    return {key: len(bucket) for key, bucket in result.buckets.items()}


def _zero_counts() -> dict:
    return dict.fromkeys(WATCH_COUNT_KEYS, 0)


def test_start_date_is_the_pre_registered_constant():
    assert EXPR_WATCH_START == dt.date(2026, 10, 16)
    assert WATCH_COUNT_KEYS == ("no_source", "unknown_strategy", "no_r",
                                "manual_close", "no_entry_date")


def test_every_registry_row_gets_a_bucket_even_when_empty():
    result = match_live_rows([], _registry())
    assert set(result.buckets) == {row_key(e) for e in _registry()}
    assert all(bucket == [] for bucket in result.buckets.values())
    assert result.counts == _zero_counts()


def test_row_key_reads_source_strategy_horizon():
    assert row_key(_reg("confluence", "ALL", "4w")) == CONF_4W
    assert row_key(_reg("strategy", "Fibonacci", None)) == FIB_POOLED


def test_confluence_trade_feeds_its_horizon_row_and_the_pooled_row():
    result = match_live_rows([_trade()], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_4W] == 1
    assert sizes[CONF_POOLED] == 1
    assert sizes[("confluence", "ALL", "2w")] == 0
    assert result.counts == _zero_counts()


def test_confluence_is_matched_on_source_not_on_strategy_name():
    # builders.py:687 path: a confluence plan carries its primary strategy.
    result = match_live_rows([_trade(strategy="Fibonacci")], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_4W] == 1 and sizes[CONF_POOLED] == 1
    assert sizes[FIB_POOLED] == 0


def test_strategy_trade_feeds_the_pooled_row_only():
    result = match_live_rows([_trade(source="strategy", strategy="Fibonacci")], _registry())
    sizes = _sizes(result)
    assert sizes[FIB_POOLED] == 1
    assert sizes[CONF_4W] == 0 and sizes[CONF_POOLED] == 0


def test_one_week_confluence_trade_feeds_pooled_only_and_is_not_unmatched():
    result = match_live_rows([_trade(horizon_key="1w")], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_POOLED] == 1
    assert sum(sizes.values()) == 1
    assert result.counts == _zero_counts()


def test_trade_without_horizon_key_is_appended_once():
    result = match_live_rows([_trade(horizon_key=None)], _registry())
    assert _sizes(result)[CONF_POOLED] == 1
    assert sum(_sizes(result).values()) == 1


def test_trade_entered_before_start_is_excluded_and_not_counted():
    # 21:00 UTC on 15 Oct is 23:00 Berlin on 15 Oct: before the start.
    result = match_live_rows([_trade(opened_at="2026-10-15T21:00:00+00:00")], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


def test_start_boundary_is_the_berlin_date_not_the_utc_date():
    # 22:30 UTC on 15 Oct is 00:30 Berlin on 16 Oct: on the start date.
    result = match_live_rows([_trade(opened_at="2026-10-15T22:30:00+00:00")], _registry())
    assert _sizes(result)[CONF_POOLED] == 1
    assert result.buckets[CONF_POOLED][0].entry_date == "2026-10-16"


def test_cohort_trade_is_excluded():
    result = match_live_rows([_trade(origin="next_session")], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


def test_weak_ledger_trade_is_included():
    result = match_live_rows([_trade(ledger="weak")], _registry())
    assert _sizes(result)[CONF_4W] == 1


def test_open_trade_is_not_in_the_population():
    result = match_live_rows([_trade(status="open", exit_price=None)], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


@pytest.mark.parametrize("over, reason", [
    ({"source": None}, "no_source"),
    ({"source": ""}, "no_source"),
    ({"source": "strategy", "strategy": "Not In Registry"}, "unknown_strategy"),
    ({"source": "mystery"}, "unknown_strategy"),
    ({"exit_price": None}, "no_r"),
    ({"opened_at": None}, "no_entry_date"),
    ({"opened_at": "not a timestamp"}, "no_entry_date"),
])
def test_each_exclusion_is_counted_and_never_bucketed(over, reason):
    result = match_live_rows([_trade(**over)], _registry())
    assert sum(_sizes(result).values()) == 0
    expected = _zero_counts()
    expected[reason] = 1
    assert result.counts == expected


def test_missing_source_key_counts_as_no_source():
    trade = _trade()
    del trade["source"]
    result = match_live_rows([trade], _registry())
    assert result.counts["no_source"] == 1


def test_manual_close_is_included_and_counted():
    result = match_live_rows([_trade(status="closed", exit_price=101.0)], _registry())
    assert _sizes(result)[CONF_4W] == 1
    assert result.counts["manual_close"] == 1


def test_live_trade_carries_berlin_date_r_and_status():
    result = match_live_rows([_trade(status="loss", exit_price=96.0)], _registry())
    live = result.buckets[CONF_4W][0]
    assert isinstance(live, LiveTrade)
    assert live == LiveTrade("2026-10-19", -0.8, "loss")


def test_berlin_entry_date_handles_naive_z_and_garbage():
    assert berlin_entry_date({"opened_at": "2026-10-15T23:30:00"}) == "2026-10-16"  # naive = UTC
    assert berlin_entry_date({"opened_at": "2026-10-19T10:00:00Z"}) == "2026-10-19"
    assert berlin_entry_date({"opened_at": ""}) is None
    assert berlin_entry_date({}) is None
    assert berlin_entry_date({"opened_at": "garbage"}) is None


def test_calibration_does_not_import_the_retrospective():
    # retrospective.py:29 imports calibration; the reverse would be a cycle.
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(calibration))
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names]
    assert not any("retrospective" in name for name in imported)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_live_loss_watch.py`
Expected: collection ERROR, `ImportError: cannot import name 'EXPR_WATCH_START' from 'swingbot.core.analytics.calibration'`.

- [ ] **Step 3: Implement the matcher**

In `$WT/swingbot/core/analytics/calibration.py`, add to the end of the module docstring (before its closing `"""`, after `without a pass/fail column.`):

```text

v164: match_live_rows() buckets the live population of every registry row
(both ledgers, regular lane, entered on or after EXPR_WATCH_START) for the
pre-registered live loss watch; LW2's live_loss_watch() turns the buckets
into rows. Day boundaries are Berlin dates read from BERLIN_TZ directly:
this module must never import tracking.retrospective (it imports us).
```

Replace the import block (`:19-23`) with:

```python
from __future__ import annotations

import datetime as dt
from collections import defaultdict, namedtuple
from dataclasses import dataclass

from swingbot.core.analytics import metrics
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.tracking import origin
```

Append to the end of the file (after `badge_drift`, unchanged):

```python
# ---------------------------------------------------------------------------
# v164 live loss watch, D1: population and matching (pre-registered)
# ---------------------------------------------------------------------------

EXPR_WATCH_START = dt.date(2026, 10, 16)   # Berlin date of opened_at, on or after
WATCH_STATUSES = ("win", "loss", "closed")
WATCH_COUNT_KEYS = ("no_source", "unknown_strategy", "no_r", "manual_close", "no_entry_date")

#: The bootstrap adapter: stats.group_by_week reads `entry_date` with getattr,
#: so a plain trade dict cannot be passed. entry_date is the Berlin-date ISO
#: string, never the UTC timestamp (iso_week_key slices [:10]).
LiveTrade = namedtuple("LiveTrade", "entry_date r status")

RowKey = tuple  # (source, strategy, horizon | None)


@dataclass(frozen=True)
class MatchResult:
    """One bucket per registry row key (empty when nothing matched) plus the
    per-reason counts of trades that were reported rather than bucketed."""
    buckets: dict
    counts: dict


def row_key(entry: dict) -> RowKey:
    """(source, strategy, horizon) of a registry row; horizon None = pooled."""
    return (entry.get("source"), entry.get("strategy"), entry.get("horizon"))


def berlin_entry_date(trade: dict) -> str | None:
    """Berlin date of `opened_at` as "YYYY-MM-DD"; naive reads as UTC (as
    retrospective._to_berlin does). None when missing or unparseable."""
    raw = trade.get("opened_at")
    if not raw:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(BERLIN_TZ).date().isoformat()


def _pooled_key(trade: dict) -> RowKey:
    source = trade.get("source")
    strategy = "ALL" if source == "confluence" else trade.get("strategy")
    return (source, strategy, None)


def _target_keys(trade: dict, buckets: dict) -> list:
    """The exact-horizon row when it exists, and always the pooled row."""
    pooled = _pooled_key(trade)
    exact = (pooled[0], pooled[1], trade.get("horizon_key"))
    if exact == pooled or exact not in buckets:
        return [pooled]
    return [exact, pooled]


def _in_population(trade: dict) -> bool:
    return trade.get("status") in WATCH_STATUSES and origin.is_regular(trade)


def _exclusion(trade: dict, buckets: dict, r: float | None) -> str | None:
    """The count key a population trade is reported under instead of being
    bucketed, first hit wins; None = keep it."""
    if not trade.get("source"):
        return "no_source"
    if _pooled_key(trade) not in buckets:
        return "unknown_strategy"
    if r is None:
        return "no_r"
    return None


def match_live_rows(trades: list[dict], registry_entries: list[dict]) -> MatchResult:
    """Bucket the pre-registered live population (spec D1) per registry row.

    A trade counts toward its exact-horizon row and the pooled row of its
    (source, strategy'); two aggregation levels, never two strategies.
    Status/origin/start-date filtering defines the population and is not
    counted; every other exclusion is counted by reason, never dropped."""
    buckets = {row_key(entry): [] for entry in registry_entries}
    counts = dict.fromkeys(WATCH_COUNT_KEYS, 0)
    for trade in trades:
        if not _in_population(trade):
            continue
        entry_date = berlin_entry_date(trade)
        if entry_date is None:
            counts["no_entry_date"] += 1
            continue
        if dt.date.fromisoformat(entry_date) < EXPR_WATCH_START:
            continue
        r = metrics.r_multiple(trade)
        reason = _exclusion(trade, buckets, r)
        if reason is not None:
            counts[reason] += 1
            continue
        if trade["status"] == "closed":
            counts["manual_close"] += 1
        live = LiveTrade(entry_date, r, trade["status"])
        for key in _target_keys(trade, buckets):
            buckets[key].append(live)
    return MatchResult(buckets=buckets, counts=counts)
```

`defaultdict` stays imported (used by `score_deciles`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_live_loss_watch.py`
Expected: all passed, `0 failed`.

Then the neighbours, unchanged behaviour:
Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_calibration.py`
Expected: all passed.

- [ ] **Step 5: Complexity and import check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/analytics/calibration.py`
Expected: exactly one line, the legacy `F 83:0 badge_drift - C (13)` (line number shifted by the new imports), unchanged; no new function listed (`match_live_rows` is B, about 7).

Run: `python -c "import swingbot.core.tracking.retrospective, swingbot.core.analytics.calibration as c; print(c.EXPR_WATCH_START)"` with `$WT` as the import root (`PYTHONPATH=$WT`).
Expected: `2026-10-16` (no circular-import error).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/analytics/calibration.py tests/analytics/test_live_loss_watch.py
git -C $WT commit -m "feat(analytics): v164 LW1 live loss watch matcher -- both ledgers, regular lane, Berlin start date, counted exclusions"
```

`git -C E:/Documents/Private/Projects/Discord-Bot status --short` must show the main tree unchanged by this task.

### Task LW2: Loss rule: week-cluster bound, rows, ordering; null operating-characteristic simulation; `badge_drift` and `r_multiple` goldens

**Model:** opus — statistical code that feeds the alert, crosses `analytics` and `backtesting`

**Files:**
- Modify: `swingbot/core/analytics/calibration.py` (imports from LW1; append after LW1's `match_live_rows`)
- Modify: `tests/analytics/test_live_loss_watch.py` (created by LW1; append)

**Interfaces:**
- Consumes (LW1): `LiveTrade(entry_date, r, status)`, `MatchResult(buckets, counts)`, `row_key(entry)`, `match_live_rows(trades, registry_entries)`, `WATCH_COUNT_KEYS`. Existing: `stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray` and `stats.WEEK_BOOTSTRAP_SEED = 42` (`swingbot/core/backtesting/instrument/stats.py:57,25`; the statistic is called `statistic(baseline_draw, component_draw)`, a `None` return is dropped, no weeks at all returns `np.array([])`); `metrics.win_rate(closed) -> float | None` (`metrics.py:221`); `strategy_types.HORIZONS` (dict, keys in order `1w, 2w, 4w, 2m, 3m, 4m, 5m, 6m, 7m, 8m, 9m`).
- Produces (LW3, LW4, LW5, LW6 rely on these exact names and shapes):
  - `EXPR_WATCH_LIVE_N_FLOOR = 20`, `EXPR_WATCH_CONFIDENCE = 0.90`, `EXPR_WATCH_RESAMPLES = 10_000`
  - `LIVE_LOSS_MEANING = 'live ExpR for this row is below zero with ~90% one-sided confidence — not "the edge decayed versus its backtest"'`
  - `LIVE_LOSS_LOOKS_CAVEAT = "11 correlated looks per week; flags are prompts to investigate, not verdicts"`
  - `REGISTRY_CONTEXT_LABEL = "backtest context — not comparable"`
  - `registry_window_kind(window: str | None) -> str | None` — `"TRAIN"` for exactly `"2020-01-01..2023-12-31"`, `"VALIDATION"` for exactly `"2024-01-01..2025-12-31"` (`docs/claude/backtest-methodology.md:8`), anything else `None` (never guessed).
  - `live_expr_bound(live: list[LiveTrade], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> float | None`
  - `loss_rule_trips(live_n: int, bound_upper: float | None) -> bool` (used by tests only; public so the boundary is pinned on the rule itself)
  - `live_loss_row(entry: dict, live: list[LiveTrade], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict` with exactly the keys `source, strategy, horizon, live_n, live_wr, live_expr, bound_upper, alert, registry_status, registry_window_kind, registry_run_date, registry_expr`
  - `order_live_loss_rows(rows: list[dict]) -> list[dict]` (index Deviation 5: alert rows first; then confluence rows in `HORIZONS` order with the pooled row last; then strategy rows by name)
  - `live_loss_watch(trades: list[dict], registry_entries: list[dict], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict` returning `{"rows": list[dict], "counts": dict[str, int]}`; one row per distinct registry row key (first occurrence wins), `counts` = LW1's counts.

**Rules this task implements (spec D2, PRE-REGISTERED; index Global Constraints):**
- Statistic: mean of `metrics.r_multiple` exactly as LW1 stored it in `LiveTrade.r`; never re-rounded.
- Bound: `week_cluster_bootstrap(live_sorted, (), _mean_r, n_resamples=n_resamples, seed=stats.WEEK_BOOTSTRAP_SEED)`, `bound_upper = np.percentile(draws, 90.0)`. The live list is sorted by `(entry_date, r, status)` first, so the bound (and `live_expr`) is bit-identical whatever order the trades arrive in. The helper builds a fresh generator per call, so a row's bound never depends on row order. Empty live or empty draws: `None`, and the row cannot trip.
- Trips when `live_n >= 20` **and** `bound_upper < 0`. A bound of exactly `0.0` does not trip.
- The percentile is `round(EXPR_WATCH_CONFIDENCE * 100, 6)` (= `90.0`): `0.90 * 100` is `90.00000000000001` in floating point.
- The bound is computed for every row with at least one trade (the UI and digest show it below the floor too); only the alert needs the floor.
- `live_wr` = `metrics.win_rate` over the bucket (wins / (wins + losses), manual closes excluded, `None` when no win/loss); `live_expr` = mean R, `None` for an empty bucket.
- **Operating characteristic** (spec D2, Testing): a seeded simulation of null populations (true mean R exactly 0, scale-out-shaped R: a −1 R mass, BE scratches, a right tail to +3 R) measures the per-look false-flag rate at N = 20, 50, 100 and pins it. Measured while writing this plan (prototype of exactly this code, 400 populations per N, 500 resamples per bound, 4 trades per ISO week): **N=20: 0.165, N=50: 0.1175, N=100: 0.135** — above the nominal 0.10, as the panel predicted for a percentile bootstrap at small skewed N. These are documented behaviour, not a target: if the test fails, something in the bound changed; do not edit the pinned numbers to make it pass without the controller's sign-off. The simulation uses 500 resamples to stay test-sized; the production constant `EXPR_WATCH_RESAMPLES = 10_000` is unchanged. It runs about 10 s, so it carries `@pytest.mark.slow` (excluded from `testrun.py fast`, included in `file` and `full`).
- `badge_drift` untouched: a golden test pins its full output on a fixed input.

- [ ] **Step 1: Write the failing tests**

Append to `$WT/tests/analytics/test_live_loss_watch.py`, then move the three import statements at the top of this block (`import numpy as np`, `from swingbot.core.analytics import metrics`, the `calibration` names) into the file's top import block so the module has one import section. The whole file (LW1 + LW2 tests) was run against a prototype of exactly the Step 3 code while writing this plan: 57 passed in about 11 s.

```python
# ---------------------------------------------------------------------------
# LW2: the D2 loss rule (pre-registered), ordering, goldens, null simulation
# ---------------------------------------------------------------------------
import numpy as np

from swingbot.core.analytics import metrics
from swingbot.core.analytics.calibration import (
    EXPR_WATCH_CONFIDENCE,
    EXPR_WATCH_LIVE_N_FLOOR,
    EXPR_WATCH_RESAMPLES,
    LIVE_LOSS_LOOKS_CAVEAT,
    LIVE_LOSS_MEANING,
    REGISTRY_CONTEXT_LABEL,
    badge_drift,
    live_expr_bound,
    live_loss_row,
    live_loss_watch,
    loss_rule_trips,
    order_live_loss_rows,
    registry_window_kind,
)

FAST = 500   # test-sized resamples; production stays EXPR_WATCH_RESAMPLES
ROW_KEYS = {"source", "strategy", "horizon", "live_n", "live_wr", "live_expr",
            "bound_upper", "alert", "registry_status", "registry_window_kind",
            "registry_run_date", "registry_expr"}
FIRST_MONDAY = dt.date(2026, 10, 19)


def _week(i: int) -> str:
    """Monday of the i-th ISO week from the first Monday after the start."""
    return (FIRST_MONDAY + dt.timedelta(weeks=i)).isoformat()


def _live(n, r, status=None, per_week=4):
    status = status or ("win" if r > 0 else "loss")
    return [LiveTrade(_week(i // per_week), r, status) for i in range(n)]


def test_rule_constants_are_the_pre_registered_values():
    assert EXPR_WATCH_LIVE_N_FLOOR == 20
    assert EXPR_WATCH_CONFIDENCE == 0.90
    assert EXPR_WATCH_RESAMPLES == 10_000
    assert LIVE_LOSS_MEANING == ('live ExpR for this row is below zero with ~90% one-sided '
                                 'confidence — not "the edge decayed versus its backtest"')
    assert LIVE_LOSS_LOOKS_CAVEAT == ("11 correlated looks per week; flags are prompts to "
                                      "investigate, not verdicts")
    assert REGISTRY_CONTEXT_LABEL == "backtest context — not comparable"


@pytest.mark.parametrize("window, kind", [
    ("2020-01-01..2023-12-31", "TRAIN"),
    ("2024-01-01..2025-12-31", "VALIDATION"),
    ("2019-01-01..2025-12-31", None),
    ("", None),
    (None, None),
])
def test_registry_window_kind_maps_exact_windows_only(window, kind):
    assert registry_window_kind(window) == kind


def test_bound_is_none_for_an_empty_population():
    assert live_expr_bound([], n_resamples=FAST) is None


def test_bound_is_identical_across_runs_and_input_order():
    rs = [-1.0, 0.0, 0.5, -1.0, 2.0, -1.0, 0.0, 1.0, -1.0, 3.0]
    live = [LiveTrade(_week(i % 6), r, "win" if r > 0 else "loss")
            for i, r in enumerate(rs * 3)]
    first = live_expr_bound(live, n_resamples=FAST)
    assert first is not None
    assert live_expr_bound(live, n_resamples=FAST) == first
    assert live_expr_bound(list(reversed(live)), n_resamples=FAST) == first
    assert live_expr_bound(sorted(live, key=lambda t: -t.r), n_resamples=FAST) == first


def test_same_week_trades_move_together():
    # Week A: five +1R, week B: five -1R. Whole weeks are resampled, so every
    # draw's mean is +1 (AA), 0 (AB) or -1 (BB); P(+1) = 0.25 puts the 90th
    # percentile at exactly +1. A per-trade bootstrap would land near +0.4.
    live = ([LiveTrade("2026-10-19", 1.0, "win")] * 5
            + [LiveTrade("2026-10-26", -1.0, "loss")] * 5)
    assert live_expr_bound(live, n_resamples=2000) == 1.0


@pytest.mark.parametrize("live_n, bound, trips", [
    (19, -0.5, False),
    (20, -0.5, True),
    (20, -1e-9, True),
    (20, 0.0, False),
    (20, 0.3, False),
    (100, None, False),
])
def test_rule_boundaries(live_n, bound, trips):
    assert loss_rule_trips(live_n, bound) is trips


def test_row_below_the_floor_never_alerts_even_when_every_trade_lost():
    row = live_loss_row(_reg("confluence", "ALL", "4w"), _live(19, -0.8), n_resamples=FAST)
    assert row["live_n"] == 19
    assert row["bound_upper"] == pytest.approx(-0.8)
    assert row["alert"] is False


def test_row_at_the_floor_alerts_when_bound_is_below_zero():
    row = live_loss_row(_reg("confluence", "ALL", "4w"), _live(20, -0.8), n_resamples=FAST)
    assert row["live_n"] == 20
    assert row["alert"] is True


def test_row_with_bound_exactly_zero_does_not_alert():
    row = live_loss_row(_reg("confluence", "ALL", "4w"), _live(40, 0.0, status="closed"),
                        n_resamples=FAST)
    assert row["bound_upper"] == 0.0
    assert row["alert"] is False


def test_row_shape_and_registry_context_columns():
    entry = _reg("strategy", "Fibonacci", None, status="VALIDATED", expr=0.105,
                 window="2020-01-01..2023-12-31", run_date="2026-05-01")
    live = _live(3, 2.0) + _live(1, -1.0)
    row = live_loss_row(entry, live, n_resamples=FAST)
    assert set(row) == ROW_KEYS
    assert (row["source"], row["strategy"], row["horizon"]) == ("strategy", "Fibonacci", None)
    assert row["live_n"] == 4
    assert row["live_wr"] == 75.0
    assert row["live_expr"] == pytest.approx(1.25)
    assert row["registry_status"] == "VALIDATED"
    assert row["registry_window_kind"] == "TRAIN"
    assert row["registry_run_date"] == "2026-05-01"
    assert row["registry_expr"] == 0.105


def test_empty_row_reports_n_zero_and_no_numbers():
    row = live_loss_row(_reg("strategy", "Fibonacci", None), [], n_resamples=FAST)
    assert row["live_n"] == 0
    assert row["live_wr"] is None and row["live_expr"] is None
    assert row["bound_upper"] is None and row["alert"] is False


def test_manual_closes_count_in_n_and_expr_but_not_in_win_rate():
    live = _live(2, 1.0) + _live(1, -1.0) + [LiveTrade(_week(0), 0.25, "closed")]
    row = live_loss_row(_reg("confluence", "ALL", None), live, n_resamples=FAST)
    assert row["live_n"] == 4
    assert row["live_wr"] == pytest.approx(200 / 3)
    assert row["live_expr"] == pytest.approx(1.25 / 4)


def _losing_trades(n, horizon_key):
    return [_trade(status="loss", exit_price=96.0, horizon_key=horizon_key,
                   opened_at=f"{_week(i // 4)}T14:00:00+00:00") for i in range(n)]


def test_watch_orders_alerts_then_confluence_by_horizon_then_strategies():
    registry = [_reg("confluence", "ALL", None), _reg("strategy", "RSI", None),
                _reg("confluence", "ALL", "2m"), _reg("strategy", "Fibonacci", None),
                _reg("confluence", "ALL", "4w"), _reg("confluence", "ALL", "2w")]
    watch = live_loss_watch(_losing_trades(20, "2m"), registry, n_resamples=FAST)
    keys = [(r["source"], r["strategy"], r["horizon"]) for r in watch["rows"]]
    assert keys == [
        ("confluence", "ALL", "2m"), ("confluence", "ALL", None),   # alerts
        ("confluence", "ALL", "2w"), ("confluence", "ALL", "4w"),
        ("strategy", "Fibonacci", None), ("strategy", "RSI", None),
    ]
    assert [r["alert"] for r in watch["rows"]] == [True, True, False, False, False, False]


def test_order_without_alerts_puts_pooled_last_among_confluence_rows():
    rows = [{"source": "confluence", "strategy": "ALL", "horizon": h, "alert": False}
            for h in (None, "9m", "1w", "2m")]
    ordered = order_live_loss_rows(rows)
    assert [r["horizon"] for r in ordered] == ["1w", "2m", "9m", None]


def test_watch_passes_counts_through_and_dedupes_registry_keys():
    registry = _registry() + [_reg("confluence", "ALL", "4w", status="VALIDATED")]
    trades = [_trade(), _trade(source=None), _trade(status="closed", exit_price=101.0)]
    watch = live_loss_watch(trades, registry, n_resamples=FAST)
    assert set(watch) == {"rows", "counts"}
    assert len(watch["rows"]) == len({row_key(e) for e in registry})
    four_week = next(r for r in watch["rows"] if r["horizon"] == "4w")
    assert four_week["registry_status"] == "WEAK"   # first occurrence wins
    assert four_week["live_n"] == 2
    assert watch["counts"] == {"no_source": 1, "unknown_strategy": 0, "no_r": 0,
                               "manual_close": 1, "no_entry_date": 0}


def test_watch_covers_every_row_of_the_committed_registry():
    from swingbot.core.backtesting.registry import load_registry
    entries = load_registry()
    watch = live_loss_watch([], entries, n_resamples=FAST)
    assert len(watch["rows"]) == len({row_key(e) for e in entries})
    assert all(r["live_n"] == 0 and r["alert"] is False for r in watch["rows"])
    confluence = [r for r in watch["rows"] if r["source"] == "confluence"]
    assert confluence and confluence[-1]["horizon"] is None


# --- goldens -----------------------------------------------------------------

def test_r_multiple_golden_with_legs():
    # Legged R is rounded to 2 dp by r_multiple; single-exit R is not.
    legged = {"entry": 100.0, "stop_loss": 97.0, "direction": "bullish",
              "legs": [{"fraction": 0.5, "r": 1.0}, {"fraction": 0.5, "exit_price": 101.0}]}
    single = {"entry": 100.0, "stop_loss": 97.0, "direction": "bullish", "exit_price": 101.0}
    bear = {"entry": 50.0, "stop_loss": 53.0, "direction": "bearish",
            "legs": [{"fraction": 0.5, "exit_price": 47.0}, {"fraction": 0.5, "exit_price": 52.0}]}
    assert metrics.r_multiple(legged) == 0.67
    assert metrics.r_multiple(single) == 0.3333333333333333
    assert metrics.r_multiple(bear) == 0.17


def test_watch_uses_r_multiple_exactly_as_written():
    legged = _trade(entry=100.0, stop_loss=97.0, exit_price=None,
                    legs=[{"fraction": 0.5, "r": 1.0}, {"fraction": 0.5, "exit_price": 101.0}])
    single = _trade(entry=100.0, stop_loss=97.0, exit_price=101.0)
    watch = live_loss_watch([legged, single], _registry(), n_resamples=FAST)
    pooled = next(r for r in watch["rows"] if r["horizon"] is None and r["source"] == "confluence")
    assert pooled["live_expr"] == (0.3333333333333333 + 0.67) / 2


def _drift_reg(strategy, wr, n=206, status="VALIDATED", run_date="2026-07-17"):
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status,
            "n": n, "win_rate": wr, "expectancy_r": 0.105,
            "window": "2024-01-01..2025-12-31", "run_date": run_date}


def _drift_t(strategy, sources, status):
    return {"strategy": strategy, "target_sources": sources, "status": status,
            "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0}


def test_badge_drift_golden_is_unchanged():
    registry = [_drift_reg("Fibonacci", 81.6), _drift_reg("Fibonacci", 70.0),
                _drift_reg("RSI", 60.0, status="WEAK"),
                _drift_reg("Volume Profile", 55.0, n=88, run_date="2026-08-01")]
    closed = ([_drift_t("S/R Confluence", ["Fib 61.8%"], "win") for _ in range(16)]
              + [_drift_t("S/R Confluence", ["Fib 61.8%"], "loss") for _ in range(9)]
              + [_drift_t("Volume Profile", [], "win") for _ in range(3)]
              + [_drift_t("Volume Profile", [], "loss")])
    assert badge_drift(closed, registry) == [
        {"strategy": "Fibonacci", "oos_n": 206, "oos_wr": 81.6, "oos_run_date": "2026-07-17",
         "live_n": 25, "live_wr": 64.0, "delta_wr": 64.0 - 81.6, "drift_alert": True},
        {"strategy": "Volume Profile", "oos_n": 88, "oos_wr": 55.0,
         "oos_run_date": "2026-08-01", "live_n": 4, "live_wr": 75.0, "delta_wr": 20.0,
         "drift_alert": False},
    ]


# --- operating characteristic (spec D2): null populations, true mean R 0 ------

NULL_R_VALUES = (-1.0, 0.0, 0.5, 1.0, 2.0, 3.0)        # -1R mass, BE scratch, right tail
NULL_R_PROBS = (0.43, 0.27, 0.10, 0.08, 0.06, 0.06)    # mean exactly 0
SIM_POPULATIONS = 400
SIM_RESAMPLES = 500        # test-sized; production stays EXPR_WATCH_RESAMPLES = 10_000
SIM_TRADES_PER_WEEK = 4
SIM_SEED = 164
#: Measured per-look false-flag rates (documented behaviour, spec D2). Above the
#: nominal 0.10: the percentile bootstrap under-covers at small skewed N. A
#: change here means the bound changed; it is not a number to tune.
NULL_FALSE_FLAG_RATES = {20: 0.165, 50: 0.1175, 100: 0.135}


def _null_population(rng, n):
    rs = rng.choice(NULL_R_VALUES, size=n, p=NULL_R_PROBS)
    return [LiveTrade(_week(i // SIM_TRADES_PER_WEEK), float(r), "win" if r > 0 else "loss")
            for i, r in enumerate(rs)]


def _false_flag_rate(n: int) -> float:
    rng = np.random.default_rng(SIM_SEED)
    flags = 0
    for _ in range(SIM_POPULATIONS):
        bound = live_expr_bound(_null_population(rng, n), n_resamples=SIM_RESAMPLES)
        flags += loss_rule_trips(n, bound)
    return flags / SIM_POPULATIONS


def test_null_distribution_has_mean_zero():
    assert sum(v * p for v, p in zip(NULL_R_VALUES, NULL_R_PROBS)) == pytest.approx(0.0, abs=1e-12)
    assert sum(NULL_R_PROBS) == pytest.approx(1.0)


@pytest.mark.slow
@pytest.mark.parametrize("n", [20, 50, 100])
def test_null_false_flag_rate_is_the_documented_behaviour(n):
    assert _false_flag_rate(n) == pytest.approx(NULL_FALSE_FLAG_RATES[n], abs=1e-9)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_live_loss_watch.py`
Expected: collection ERROR, `ImportError: cannot import name 'EXPR_WATCH_CONFIDENCE' from 'swingbot.core.analytics.calibration'`.

- [ ] **Step 3: Implement the rule, rows and ordering**

In `$WT/swingbot/core/analytics/calibration.py`, extend LW1's import block to:

```python
from __future__ import annotations

import datetime as dt
from collections import defaultdict, namedtuple
from dataclasses import dataclass

import numpy as np

from swingbot.core.analytics import metrics
from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.tracking import origin
```

(`backtesting/__init__.py` and `backtesting/instrument/__init__.py` import nothing; `stats.py` imports only stdlib and numpy; `strategy_types.py` imports only `dataclasses`. No cycle.)

Append to the end of the file, after `match_live_rows`:

```python
# ---------------------------------------------------------------------------
# v164 live loss watch, D2: the loss rule (PRE-REGISTERED)
# ---------------------------------------------------------------------------
# Fixed in spec v164 before any trade it judges existed (EXPR_WATCH_START is
# the day after the spec's commit). Never loosened or tightened after seeing
# what it flags; a change is a new spec written before looking. The baseline
# is zero, not the registry: registry rows carry no exit-model, scale-out or
# friction provenance, so they are shown as labelled context only.

EXPR_WATCH_LIVE_N_FLOOR = 20
EXPR_WATCH_CONFIDENCE = 0.90      # one-sided
EXPR_WATCH_RESAMPLES = 10_000

LIVE_LOSS_MEANING = ('live ExpR for this row is below zero with ~90% one-sided '
                     'confidence — not "the edge decayed versus its backtest"')
LIVE_LOSS_LOOKS_CAVEAT = ("11 correlated looks per week; flags are prompts to "
                          "investigate, not verdicts")
REGISTRY_CONTEXT_LABEL = "backtest context — not comparable"

#: backtest-methodology.md windows, matched by exact string; never guessed.
_WINDOW_KINDS = {
    "2020-01-01..2023-12-31": "TRAIN",
    "2024-01-01..2025-12-31": "VALIDATION",
}
_BOUND_PERCENTILE = round(EXPR_WATCH_CONFIDENCE * 100, 6)   # 90.0, not 90.00000000000001


def registry_window_kind(window: str | None) -> str | None:
    """TRAIN / VALIDATION for the two methodology windows, else None."""
    return _WINDOW_KINDS.get(window) if window else None


def _canonical(live: list) -> list:
    """Input-order-free ordering, so float sums and the bootstrap are
    bit-identical however the trades arrive."""
    return sorted(live, key=lambda t: (t.entry_date, t.r, t.status))


def _mean_r(draw: list, _component=()) -> float | None:
    """Bootstrap statistic: mean R of one week draw; None (dropped) when empty."""
    if not draw:
        return None
    return sum(t.r for t in draw) / len(draw)


def live_expr_bound(live: list, *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> float | None:
    """One-sided upper bound on live ExpR: the 90th percentile of the
    week-clustered bootstrap of mean R (stats.week_cluster_bootstrap, its
    named seed, a fresh generator per call). None when there is nothing to
    resample, and a row without a bound cannot trip."""
    if not live:
        return None
    draws = stats.week_cluster_bootstrap(_canonical(live), (), _mean_r,
                                         n_resamples=n_resamples,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    if draws.size == 0:
        return None
    return float(np.percentile(draws, _BOUND_PERCENTILE))


def loss_rule_trips(live_n: int, bound_upper: float | None) -> bool:
    """The pre-registered rule: live_n >= 20 and bound_upper < 0."""
    return (bound_upper is not None and live_n >= EXPR_WATCH_LIVE_N_FLOOR
            and bound_upper < 0)


def _live_stats(live: list) -> tuple:
    """(live_n, live_wr, live_expr) of one bucket; WR over win/loss only."""
    live_n = len(live)
    live_wr = metrics.win_rate([{"status": t.status} for t in live])
    live_expr = (sum(t.r for t in _canonical(live)) / live_n) if live_n else None
    return live_n, live_wr, live_expr


def live_loss_row(entry: dict, live: list, *,
                  n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict:
    """One output row (spec D2). The registry_* columns are backtest context
    (REGISTRY_CONTEXT_LABEL), never an input to `alert`."""
    live_n, live_wr, live_expr = _live_stats(live)
    bound = live_expr_bound(live, n_resamples=n_resamples)
    return {
        "source": entry.get("source"),
        "strategy": entry.get("strategy"),
        "horizon": entry.get("horizon"),
        "live_n": live_n,
        "live_wr": live_wr,
        "live_expr": live_expr,
        "bound_upper": bound,
        "alert": loss_rule_trips(live_n, bound),
        "registry_status": entry.get("status"),
        "registry_window_kind": registry_window_kind(entry.get("window")),
        "registry_run_date": entry.get("run_date"),
        "registry_expr": entry.get("expectancy_r"),
    }


def _row_rank(row: dict, horizons: list) -> tuple:
    first = 0 if row.get("alert") else 1
    if row.get("source") == "confluence":
        horizon = row.get("horizon")
        position = horizons.index(horizon) if horizon in horizons else len(horizons)
        return (first, 0, position, "")
    return (first, 1, 0, str(row.get("strategy")))


def order_live_loss_rows(rows: list[dict]) -> list[dict]:
    """Alert rows first; then confluence rows in HORIZONS order, pooled last;
    then strategy rows by name. The digest and the UI share this order."""
    horizons = list(HORIZONS)
    return sorted(rows, key=lambda row: _row_rank(row, horizons))


def _unique_entries(registry_entries: list[dict]) -> list[dict]:
    """First registry row per (source, strategy, horizon) key."""
    seen: dict = {}
    for entry in registry_entries:
        seen.setdefault(row_key(entry), entry)
    return list(seen.values())


def live_loss_watch(trades: list[dict], registry_entries: list[dict], *,
                    n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict:
    """D1 + D2: {"rows": ordered rows, one per registry row key, "counts":
    the matcher's exclusion counts}. Pure; report-only."""
    match = match_live_rows(trades, registry_entries)
    rows = [live_loss_row(entry, match.buckets[row_key(entry)], n_resamples=n_resamples)
            for entry in _unique_entries(registry_entries)]
    return {"rows": order_live_loss_rows(rows), "counts": dict(match.counts)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_live_loss_watch.py`
Expected: all passed, `0 failed` (the three `slow` simulation cases included; about 10 s for them).

If `test_null_false_flag_rate_is_the_documented_behaviour` fails, the bound is not the one specified (check the `_canonical` sort key, `_BOUND_PERCENTILE`, the seed, and that `_mean_r` drops empty draws). Do not change `NULL_FALSE_FLAG_RATES`; escalate to the controller.

Then the neighbours:
Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_calibration.py`
Expected: all passed (`badge_drift` behaviour unchanged).

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_snapshots.py`
Expected: all passed (the snapshot does not call the watch until LW5).

- [ ] **Step 5: Complexity and import check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/analytics/calibration.py`
Expected: exactly one line, the legacy `badge_drift - C (13)`, unchanged; no new function listed.

Run (with `PYTHONPATH=$WT`): `python -c "import swingbot.core.tracking.retrospective, swingbot.core.analytics.snapshots, swingbot.core.analytics.calibration as c; print(c.EXPR_WATCH_RESAMPLES)"`
Expected: `10000` (no circular-import error).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/analytics/calibration.py tests/analytics/test_live_loss_watch.py
git -C $WT commit -m "feat(analytics): v164 LW2 pre-registered live loss rule -- week-cluster bound below zero, rows, null false-flag rates pinned, badge_drift golden"
```

`git -C E:/Documents/Private/Projects/Discord-Bot status --short` must show the main tree unchanged by this task.

