# v226 — Stop-width attribution, part 2: the study (V226-5..V226-9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v226 — Stop-width attribution](../specs/2026-11-12-v226-stop-width-attribution-design.md) (§ The grouping, § Frozen bucket edges, § The pre-registered verdict, § Disclosures, § Code, § Tests)
**Index:** [`_0-index.md`](2026-11-12-v226-stop-width-attribution_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and its cross-task contracts. Every task below implicitly includes the index's Global Constraints.

This part builds the study inside `swingbot/core/analytics/expectancy_attribution.py`
without touching anything the v146 report reads. First a golden pin of the
default report and the script summary is recorded at the pre-change HEAD
(V226-5), so every later edit to the module is checked against it. Then, each
appended after `run` at the end of the module: the stop-width rows and their
two loaders (V226-6), TRAIN-frozen quartile edges and the two bucketed
populations (V226-7), the six-clause pre-registered verdict with its own BH
family (V226-8), and the printed-never-gating disclosures (V226-9). Part 3
turns these into the report, the `--study` flag and the run.

All work happens in worktree `.claude/worktrees/2026-11-12-v226-stop-width-attribution`
(branch of the same name). Run every command below from that worktree root.
V226-5..V226-9 edit or pin the same module: run them strictly in order.

**Accepted choices (controller, 2026-11-12):** `VETO-CANDIDATE` wins over
`UNDERPOWERED` when a bucket passes all six clauses; the clause-4 year of a
row is `row["week"][:4]`; `stop_width_row(base_row, source, *, live=False)`;
`n_needed` is 300.

# Phase 2 — The stop-width study

### Task V226-5: Golden pin of the default attribution report and summary

**Model:** sonnet — one test file copying an existing fixture pattern; the only judgement is recording the digests before any module edit.

**Files:**
- Create: `tests/analytics/test_expectancy_attribution_default_pin.py`

**Interfaces:**
- Consumes: `ea.build_report(live_rows, train_rows, *, seed, generated_at=None) -> dict` (`swingbot/core/analytics/expectancy_attribution.py:669`); `ea.N_RESAMPLES` (module global, monkeypatched); `summary(report) -> str` in `scripts/reports/expectancy_attribution.py` (loaded by file path, as `tests/analytics/test_expectancy_attribution_report.py::_script` does).
- Produces: `DEFAULT_REPORT_SHA256`, `DEFAULT_SUMMARY_SHA256` (module constants in the test; V226-11 re-runs this file unchanged).

**Order matters:** this task runs and commits **before** any edit to
`swingbot/core/analytics/expectancy_attribution.py` or
`scripts/reports/expectancy_attribution.py`. Check first:

```bash
git diff --stat main -- swingbot/core/analytics/expectancy_attribution.py scripts/reports/expectancy_attribution.py
```

Expected: no output. If either file already differs from `main`, stop and
report to the controller: the pin must be recorded at the pre-change state.

The digests below were computed by the plan writer at `main` e0739414 (the
pre-change module) with the exact fixture in Step 1, twice, with identical
results. The rows are copied (not imported) from `population()` in
`tests/analytics/test_expectancy_attribution_stats.py`, with three changes so
more of the report's branches carry data: a second regime label, some unknown
earnings rows, and a live population in another year. Copying keeps the pin
independent of edits to that helper.

- [ ] **Step 1: Write the pin test**

```python
"""v226 regression pin: the default v146 attribution report and the script's
printed summary stay byte-identical while the stop-width study is added to the
same module. The digests were recorded at the pre-change HEAD (main e0739414);
a change to them is a regression, never a re-record."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.market.strategy_types import HORIZONS

HK = next(iter(HORIZONS))
REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reports" / "expectancy_attribution.py"
GENERATED_AT = "2026-11-12T00:00:00+00:00"

DEFAULT_REPORT_SHA256 = "fcf56996cb2b053c50d0aa81f6a054be4f0fbd1b4c943d7b90a12170726dd9bb"
DEFAULT_SUMMARY_SHA256 = "647acb364f3ee70e5f1dc18bc360bf8bfe13b8707d0f2d0375666f33eb0960fa"


def _rows(slope: float, n: int, start: dt.date) -> list[dict]:
    """Deterministic attribution rows (ROW_KEYS), 30 entry weeks from ``start``."""
    out = []
    for i in range(n):
        r = slope * (i / (n - 1) - 0.5) + ((i * 37) % 11 - 5) / 10.0
        points = {"MACD momentum": 10 if i >= n // 2 else 0,
                  "ADX trend strength": 7 if i % 5 == 0 else (15 if i % 2 else 0)}
        if i % 3 == 0:
            points["Tight stop penalty"] = -5
        out.append({
            "r": r, "r_gross": r + 0.03,
            "week": (start + dt.timedelta(weeks=i % 30)).isoformat(),
            "confidence_score": i, "confidence_level": 3 + (3 * i) // n,
            "confidence_points": points,
            "confidence_unevaluated": ["ADX trend strength"] if i % 5 == 0 else [],
            "confluence_count": 2 + i % 3,
            "regime2_state": "bull_quiet" if i % 4 else "bear_volatile",
            "rs_pctile": float(i % 100),
            "direction": "bullish" if i % 3 else "bearish", "horizon": HK,
            "earnings_sessions": i % 40 if i % 7 else None,
            "earnings_status": "known" if i % 7 else "unknown",
            "risk_reward_ratio": 1.5 + (i % 4) / 4.0,
        })
    return out


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)


def _report() -> dict:
    live = _rows(0.0, 120, dt.date(2026, 3, 2))
    train = _rows(0.6, 240, dt.date(2021, 1, 4))
    return ea.build_report(live, train, seed=42, generated_at=GENERATED_AT)


def _script():
    spec = importlib.util.spec_from_file_location("v226_default_pin_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_default_report_is_byte_identical_to_the_pre_change_head():
    report = _report()
    assert report["verdict"] == "WEAK" and report["looks"] == 46     # sanity: the fixture is live
    assert _sha256(json.dumps(report, sort_keys=True, default=str)) == DEFAULT_REPORT_SHA256


def test_the_script_summary_is_byte_identical_to_the_pre_change_head():
    assert _sha256(_script().summary(_report())) == DEFAULT_SUMMARY_SHA256


def test_the_default_report_carries_no_stop_width_key():
    """The study writes its own report; the default one never grows a key."""
    report = _report()
    assert list(report) == ["generated_at", "verdict", "verdict_of_record", "looks",
                            "seed", "provenance", "populations"]
    assert "stop_atr" not in json.dumps(report)
```

- [ ] **Step 2: Run it at the pre-change HEAD**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: 3 passed.

If (and only if) the two digest tests fail **while the diff check above is
still empty**, the digests depend on this machine's numpy build: print the
observed values once —

```bash
python -m pytest tests/analytics/test_expectancy_attribution_default_pin.py -q 2>&1 | grep -E "assert '[0-9a-f]{64}'" | head -4
```

— write them into the two constants, re-run green, and say so in the task
report (the controller confirms CI agrees after the push). Never re-record
after any edit to the two pinned files.

- [ ] **Step 3: Commit (alone)**

```bash
git add tests/analytics/test_expectancy_attribution_default_pin.py
git commit -m "test(v226): golden pin of the default attribution report and summary, recorded before the study (V226-5)"
```

### Task V226-6: `stop_width_row` and the two stop-width loaders

**Model:** sonnet — additive helpers that wrap the existing v146 loaders; the pinned row contracts are the only trap and are tested here.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (add `import math` to the stdlib imports; append a new section after `run`, the last function in the file)
- Create: `tests/analytics/test_stop_width_rows.py`

**Interfaces:**
- Consumes: `_train_row(raw, source) -> dict | None` (:573), `live_row(trade) -> dict | None` (:509), `closed_only` (imported at :30), `earnings_calendar.CsvSource` (as `load_train_rows` uses it), `ROW_KEYS` (:49); `swingbot.core.tracking.performance.primary_strategy_label(t) -> str` (performance.py:315; lazy import, it pulls chart code).
- Produces (later tasks rely on these exact names):
  - `STOP_WIDTH_KEYS = ("stop_atr", "atr_pct", "stop_clamped")`
  - `STOP_WIDTH_LIVE_KEYS = ("opened_at", "closed_at", "strategy")`
  - `_positive_number(value) -> float | None`: None for bool, non-int/float, NaN, ±inf, ≤ 0
  - `stop_width_row(base_row: dict, source: dict, *, live: bool = False) -> dict`: a **new** dict with `base_row`'s keys in order, then `STOP_WIDTH_KEYS`, then (only when `live`) `STOP_WIDTH_LIVE_KEYS`; `base_row` is never mutated
  - `load_stop_width_train_rows(path, *, source=None) -> list[dict]`
  - `load_stop_width_live_rows() -> list[dict]`

**Design notes.**
- `stop_atr` = `_positive_number(entry_context["stop_atr"])`. An absent or
  non-dict `entry_context`, or a missing / non-numeric / bool / non-finite /
  ≤ 0 value, gives `None`, which V226-7 labels `unknown`.
- `atr_pct` = `stop_pct / stop_atr` (ATR14 as % of the signal close) only
  when both are positive numbers, else `None`. Disclosed only, never a look.
- `stop_clamped` keeps a real `bool`; anything else is `None` (V226-9 drops
  `None` from the clamped-share denominator and counts it).
- Live keys: `opened_at`/`closed_at` are `str(value)` when present, else
  `None`. `strategy` is the **family label** from
  `performance.primary_strategy_label(trade)` (the confirming method the
  admin UI shows: Fib, FVG, Trendline …), because a live confluence trade's
  raw `trade["strategy"]` is the constant `"S/R Confluence"` and would make
  the family share useless; its `"--"` fallback becomes `None`.
- `ROW_KEYS`, `live_row`, `_train_row`, `load_live_rows` and
  `load_train_rows` are not edited. The new loaders call the two row builders
  exactly as the v146 loaders do and wrap each kept row.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_stop_width_rows.py`:

```python
"""v226: stop-width rows wrap the v146 attribution rows without widening them,
and the two loaders reuse the v146 row builders."""
from __future__ import annotations

import math

import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from tests.analytics.test_expectancy_attribution_report import (
    StubSource, _replay_row, _trade, _write_jsonl)

CONTEXT = {"regime2_state": "bull_quiet", "rs_pctile": 55.0,
           "stop_atr": 0.4, "stop_pct": 2.0, "stop_clamped": True}


@pytest.mark.parametrize("value, expected", [
    (0.42, 0.42), (3, 3.0), (True, None), (False, None), ("1.2", None), (None, None),
    (0, None), (0.0, None), (-0.5, None), (math.nan, None), (math.inf, None),
    (-math.inf, None), ([1.0], None)])
def test_positive_number_accepts_only_finite_positive_numbers(value, expected):
    assert ea._positive_number(value) == expected


def test_a_train_stop_width_row_extends_the_attribution_row(tmp_path):
    path = _write_jsonl(tmp_path / "train.jsonl", [_replay_row(entry_context=dict(CONTEXT))])
    source = StubSource(["2024-02-01", "2024-05-02"])
    [row] = ea.load_stop_width_train_rows(path, source=source)
    [base] = ea.load_train_rows(path, source=source)
    assert tuple(row) == ea.ROW_KEYS + ea.STOP_WIDTH_KEYS
    assert {key: row[key] for key in ea.ROW_KEYS} == base
    assert row["stop_atr"] == 0.4 and row["stop_clamped"] is True
    assert row["atr_pct"] == pytest.approx(5.0)              # stop_pct / stop_atr


def test_the_train_loader_skips_untriggered_rows_like_the_v146_loader(tmp_path):
    path = _write_jsonl(tmp_path / "train.jsonl", [
        _replay_row(entry_context=dict(CONTEXT)),
        _replay_row(outcome="not_triggered", legs=[], r_total=0.0, entry_price=None)])
    assert len(ea.load_stop_width_train_rows(path, source=StubSource([]))) == 1


def test_the_train_loader_defaults_to_the_csv_source(tmp_path, monkeypatch):
    made = []

    class FakeCsv(StubSource):
        def __init__(self):
            super().__init__([])
            made.append(self)

    monkeypatch.setattr(ea.earnings_calendar, "CsvSource", FakeCsv)
    rows = ea.load_stop_width_train_rows(_write_jsonl(tmp_path / "t.jsonl", [_replay_row()]))
    assert len(made) == 1 and len(rows) == 1


@pytest.mark.parametrize("context", [
    None, "not a dict", {}, {"stop_atr": None}, {"stop_atr": "0.4"}, {"stop_atr": 0},
    {"stop_atr": -0.3}, {"stop_atr": True}, {"stop_atr": math.nan}],
    ids=["absent", "non-dict", "empty", "none", "string", "zero", "negative", "bool", "nan"])
def test_an_unusable_stop_atr_is_none_and_so_is_atr_pct(context):
    row = ea.stop_width_row({"r": 1.0}, {"entry_context": context})
    assert row["stop_atr"] is None and row["atr_pct"] is None


def test_atr_pct_needs_a_positive_stop_pct():
    assert ea.stop_width_row({}, {"entry_context": {"stop_atr": 0.5}})["atr_pct"] is None
    assert ea.stop_width_row({}, {"entry_context": {"stop_atr": 0.5, "stop_pct": 0}})["atr_pct"] is None


@pytest.mark.parametrize("flag, expected", [(True, True), (False, False), (None, None),
                                            ("yes", None), (1, None)])
def test_stop_clamped_keeps_only_a_real_bool(flag, expected):
    row = ea.stop_width_row({}, {"entry_context": {"stop_clamped": flag}})
    assert row["stop_clamped"] is expected


def test_stop_width_row_never_mutates_the_base_row():
    base = {"r": 1.0, "week": "2021-03-01"}
    row = ea.stop_width_row(base, {"entry_context": dict(CONTEXT)}, live=True)
    assert base == {"r": 1.0, "week": "2021-03-01"} and row is not base


def test_a_live_stop_width_row_adds_timestamps_and_the_family(monkeypatch):
    from swingbot.core.tracking.performance import primary_strategy_label
    trade = _trade(entry_context=dict(CONTEXT), closed_at="2026-03-11T19:00:00+00:00")
    seen = {}

    class FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return [trade, _trade(status="open", exit_price=None)]

    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog", FakeLog)
    [row] = ea.load_stop_width_live_rows()
    assert seen == {"status": None, "limit": None, "ledger": None}
    assert tuple(row) == ea.ROW_KEYS + ea.STOP_WIDTH_KEYS + ea.STOP_WIDTH_LIVE_KEYS
    assert {key: row[key] for key in ea.ROW_KEYS} == ea.live_row(trade)
    assert row["opened_at"] == "2026-03-11T14:30:00+00:00"
    assert row["closed_at"] == "2026-03-11T19:00:00+00:00"
    label = primary_strategy_label(trade)
    assert row["strategy"] == (None if label == "--" else label)
    assert row["stop_atr"] == 0.4


def test_live_keys_are_none_when_the_trade_lacks_them():
    row = ea.stop_width_row({}, {"entry_context": {}}, live=True)
    assert (row["opened_at"], row["closed_at"], row["strategy"]) == (None, None, None)


def test_the_v146_row_contracts_are_unchanged():
    assert tuple(ea.live_row(_trade())) == ea.ROW_KEYS
    assert "stop_atr" not in ea.ROW_KEYS and "strategy" not in ea.ROW_KEYS
    assert ea.STOP_WIDTH_KEYS == ("stop_atr", "atr_pct", "stop_clamped")
    assert ea.STOP_WIDTH_LIVE_KEYS == ("opened_at", "closed_at", "strategy")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_rows.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.analytics.expectancy_attribution' has no attribute '_positive_number'` (and the other new names).

- [ ] **Step 3: Implement**

In `swingbot/core/analytics/expectancy_attribution.py`, add `import math`
to the stdlib block (alphabetical, after `import logging`):

```python
import logging
import math
import sys
```

Append at the end of the file, after `run`:

```python


# --------------------------------------------------------------------------
# v226: stop-width attribution -- a study of its own. Nothing above this line
# reads anything below it; the v146 report stays byte-identical.
# --------------------------------------------------------------------------

#: A stop-width row is an attribution row (ROW_KEYS, unchanged) plus these.
#: ``stop_atr`` = |signal close - stop| / ATR14, both from the signal bar
#: (``entry_context["stop_atr"]``); ``atr_pct`` = ``stop_pct / stop_atr``
#: (disclosed only); ``stop_clamped`` is the identity-based clamp flag.
STOP_WIDTH_KEYS = ("stop_atr", "atr_pct", "stop_clamped")
#: Live rows only: the TRAIN scenario row carries neither timestamps nor a
#: strategy field, and its contract is not widened for them.
STOP_WIDTH_LIVE_KEYS = ("opened_at", "closed_at", "strategy")


def _positive_number(value) -> float | None:
    """``float(value)`` when it is a finite number > 0, else None. Bools are
    not numbers here, and neither are numeric strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _text_or_none(value) -> str | None:
    return None if value is None else str(value)


def _family(trade: dict) -> str | None:
    """The live trade's strategy family as the admin UI shows it (the raw
    ``strategy`` field is the constant "S/R Confluence"). Lazy import: the
    label pulls chart code."""
    from swingbot.core.tracking.performance import primary_strategy_label
    label = primary_strategy_label(trade)
    return None if label == "--" else label


def stop_width_row(base_row: dict, source: dict, *, live: bool = False) -> dict:
    """``base_row`` (an attribution row) plus STOP_WIDTH_KEYS read from
    ``source["entry_context"]``, plus STOP_WIDTH_LIVE_KEYS when ``live``.
    Returns a new dict; ``base_row`` is not touched."""
    context = source.get("entry_context")
    context = context if isinstance(context, dict) else {}
    stop_atr = _positive_number(context.get("stop_atr"))
    stop_pct = _positive_number(context.get("stop_pct"))
    clamped = context.get("stop_clamped")
    row = {**base_row,
           "stop_atr": stop_atr,
           "atr_pct": stop_pct / stop_atr if stop_atr and stop_pct else None,
           "stop_clamped": clamped if isinstance(clamped, bool) else None}
    if live:
        row["opened_at"] = _text_or_none(source.get("opened_at"))
        row["closed_at"] = _text_or_none(source.get("closed_at"))
        row["strategy"] = _family(source)
    return row


def load_stop_width_train_rows(path, *, source=None) -> list[dict]:
    """``load_train_rows`` again, each kept row wrapped by ``stop_width_row``."""
    source = source if source is not None else earnings_calendar.CsvSource()
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            base = _train_row(raw, source)
            if base is not None:
                rows.append(stop_width_row(base, raw))
    return rows


def load_stop_width_live_rows() -> list[dict]:
    """``load_live_rows`` again (every closed trade of both ledgers, read from
    the database ``DATABASE_URL`` names at call time), each kept row wrapped
    by ``stop_width_row(..., live=True)``."""
    from swingbot.core.tracking.performance import TradeLog
    closed = closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None) or [])
    rows = []
    for trade in closed:
        base = live_row(trade)
        if base is not None:
            rows.append(stop_width_row(base, trade, live=True))
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_rows.py`
Expected: all passed.

Then the v146 pins:
`python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
and `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_report.py`
Expected: all passed (the default report and the `tuple(row) == ROW_KEYS` pins hold).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function is far below 15).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_stop_width_rows.py
git commit -m "feat(v226): stop-width rows and loaders -- stop_atr, atr_pct, stop_clamped, live timestamps and family (V226-6)"
```

### Task V226-7: Frozen TRAIN edges, labels and the two bucketed populations

**Model:** opus — outcome-blind quantile edges with merge rules and a no-empty-bucket guarantee; an error here silently leaks the outcome into the buckets.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (add `import bisect` to the stdlib imports; append after V226-6's section)
- Create: `tests/analytics/test_stop_width_edges.py`

**Interfaces:**
- Consumes: `_positive_number(value) -> float | None` (V226-6); `np` (already imported).
- Produces (later tasks rely on these exact names):
  - `UNKNOWN = "unknown"`
  - `frozen_edges(rows: list[dict], key: str) -> list[float]`: strictly increasing, 0 to 3 floats
  - `edge_labels(edges: list[float]) -> list[str]`: `len(edges) + 1` labels; `["Q1 (all)"]` for `[]`
  - `edge_label(value, edges: list[float]) -> str`: a label from `edge_labels(edges)`, or `UNKNOWN`
  - `stop_width_groups(train_rows: list[dict], live_rows: list[dict]) -> dict` = `{"edges": list[float], "labels": list[str], "train": POP, "live": POP}` with `POP = {"buckets": {label: list[dict]}` (every label, in `labels` order, possibly empty for live)`, "known": list[dict]` (bucketed rows, input order)`, "unknown": int}`. Rows are the input dicts themselves (V226-8 tells rest from bucket by `id(row)`).

**Rules (spec § Frozen bucket edges, index Global Constraints).**
- Known values are `_positive_number(row.get(key))` that are not None.
  `frozen_edges` never reads `r` (pinned: rows without an `r` key work, and
  shuffling `r` leaves the edges identical).
- Fewer than 2 known values → `[]`. Otherwise the three cut points are
  `numpy.quantile(values, [0.25, 0.5, 0.75], method="linear")`.
- Merging, in order: an edge ≤ the minimum known value is dropped (its lower
  bucket would be empty); an edge ≤ the previous kept edge is dropped
  (coinciding edges merge); an edge whose bucket `[previous kept edge, edge)`
  holds no value is dropped (that bucket merges into the next one); finally
  the last edge is dropped while no value is ≥ it (cannot fire after the
  first rule, kept as a guard). Result: every TRAIN bucket is non-empty.
- A value equal to an edge goes to the **upper** bucket:
  `bisect.bisect_right(edges, value)` is the bucket index.
- Labels: `Q1 (<a)`, `Q2 (a–b)`, `Q3 (b–c)`, `Q4 (≥c)` with `:.2f` values,
  an en dash `–` and `≥`; with fewer edges the numbering stops earlier
  (`Q1 (<a)`, `Q2 (≥a)`); with none, `Q1 (all)`.
- `stop_width_groups` computes the edges from **TRAIN only** and buckets
  live rows with them. The live cut points 0.35 / 0.5 / 0.75 seen on
  2026-11-12 appear nowhere in the code.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_stop_width_edges.py`:

```python
"""v226: TRAIN-frozen stop_atr quartile edges -- outcome-blind, merged when
they coincide, never an empty bucket, edge values to the upper bucket, live
rows bucketed on the TRAIN edges."""
from __future__ import annotations

import random

import pytest

from swingbot.core.analytics import expectancy_attribution as ea


def _row(stop_atr, r=0.0, **over) -> dict:
    row = {"r": r, "r_gross": r, "week": "2021-03-01", "direction": "bullish",
           "horizon": "2w", "stop_atr": stop_atr, "atr_pct": None, "stop_clamped": None}
    row.update(over)
    return row


EIGHT = [_row(float(v), r=(v - 4) / 4) for v in range(1, 9)]          # stop_atr 1..8


def test_edges_are_the_linear_train_quartiles():
    assert ea.frozen_edges(EIGHT, "stop_atr") == pytest.approx([2.75, 4.5, 6.25])


def test_edges_are_outcome_blind():
    shuffled_r = [row["r"] for row in EIGHT]
    random.Random(7).shuffle(shuffled_r)
    shuffled = [dict(row, r=r) for row, r in zip(EIGHT, shuffled_r)]
    no_r = [{key: value for key, value in row.items() if key not in ("r", "r_gross")}
            for row in EIGHT]
    expected = ea.frozen_edges(EIGHT, "stop_atr")
    assert ea.frozen_edges(shuffled, "stop_atr") == expected
    assert ea.frozen_edges(no_r, "stop_atr") == expected     # never reads r at all


def test_unknown_values_are_left_out_of_the_quantiles():
    noisy = EIGHT + [_row(None), _row(0), _row(-1.0), _row("2.0"), _row(True),
                     {"r": 1.0}]
    assert ea.frozen_edges(noisy, "stop_atr") == ea.frozen_edges(EIGHT, "stop_atr")


@pytest.mark.parametrize("values, expected", [
    ([1.0] * 6 + [5.0] * 2, [2.0]),           # q25 = q50 = min: both dropped
    ([1.0, 1.0, 1.0, 5.0, 5.0, 5.0], [3.0]),  # [3, 5) would be empty: 5 dropped
    ([2.0] * 5, []),                          # one value: a single bucket
    ([3.0], []),                              # fewer than two known values
    ([], []),
], ids=["low-tie", "empty-middle", "constant", "one", "none"])
def test_coinciding_edges_merge(values, expected):
    assert ea.frozen_edges([_row(v) for v in values], "stop_atr") == pytest.approx(expected)


@pytest.mark.parametrize("values", [
    [float(v) for v in range(1, 9)],
    [1.0] * 6 + [5.0] * 2,
    [1.0, 1.0, 1.0, 5.0, 5.0, 5.0],
    [0.2, 0.2, 0.2, 0.2, 0.3, 0.9, 0.9, 0.9, 0.9, 0.9],
    [0.5 + (i % 7) * 0.05 for i in range(200)],
])
def test_no_train_bucket_is_ever_empty(values):
    rows = [_row(v) for v in values]
    groups = ea.stop_width_groups(rows, [])
    assert groups["edges"] == sorted(set(groups["edges"]))           # strictly increasing
    assert all(groups["train"]["buckets"][label] for label in groups["labels"])
    assert sum(len(b) for b in groups["train"]["buckets"].values()) == len(values)


def test_labels_name_the_edges():
    assert ea.edge_labels([2.75, 4.5, 6.25]) == [
        "Q1 (<2.75)", "Q2 (2.75–4.50)", "Q3 (4.50–6.25)", "Q4 (≥6.25)"]
    assert ea.edge_labels([0.4]) == ["Q1 (<0.40)", "Q2 (≥0.40)"]
    assert ea.edge_labels([]) == ["Q1 (all)"]


@pytest.mark.parametrize("value, label", [
    (1.0, "Q1 (<2.75)"), (2.75, "Q2 (2.75–4.50)"), (4.5, "Q3 (4.50–6.25)"),
    (6.25, "Q4 (≥6.25)"), (99.0, "Q4 (≥6.25)"), (None, "unknown"), (0, "unknown"),
    (-2.0, "unknown"), ("3.0", "unknown"), (True, "unknown")])
def test_a_value_on_an_edge_goes_to_the_upper_bucket(value, label):
    assert ea.edge_label(value, [2.75, 4.5, 6.25]) == label


def test_one_bucket_when_there_is_no_edge():
    assert ea.edge_label(0.3, []) == "Q1 (all)"
    assert ea.edge_label(None, []) == ea.UNKNOWN == "unknown"


def test_live_rows_use_the_train_edges_and_unknowns_are_counted_not_bucketed():
    train = EIGHT + [_row(None), _row(0)]
    live = [_row(0.35), _row(0.5), _row(0.75), _row(7.0), _row(None),
            {"r": -1.0}]                                             # live quartiles differ
    groups = ea.stop_width_groups(train, live)
    assert groups["edges"] == pytest.approx([2.75, 4.5, 6.25])
    assert groups["labels"] == ea.edge_labels(groups["edges"])
    assert groups["edges"] == ea.stop_width_groups(train, [])["edges"]   # live never moves them
    tr, lv = groups["train"], groups["live"]
    assert list(tr["buckets"]) == list(lv["buckets"]) == groups["labels"]
    assert tr["unknown"] == 2 and len(tr["known"]) == 8
    assert [len(tr["buckets"][label]) for label in groups["labels"]] == [2, 2, 2, 2]
    assert lv["unknown"] == 2 and len(lv["known"]) == 4
    assert [len(lv["buckets"][label]) for label in groups["labels"]] == [3, 0, 0, 1]
    assert all(row in lv["known"] for row in lv["buckets"]["Q1 (<2.75)"])
    assert tr["buckets"]["Q1 (<2.75)"][0] is train[0]               # the input dicts themselves


def test_empty_populations_give_one_empty_bucket():
    groups = ea.stop_width_groups([], [])
    assert groups["edges"] == [] and groups["labels"] == ["Q1 (all)"]
    assert groups["train"] == {"buckets": {"Q1 (all)": []}, "known": [], "unknown": 0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_edges.py`
Expected: FAIL with `AttributeError: ... has no attribute 'frozen_edges'`.

- [ ] **Step 3: Implement**

Add `import bisect` to the stdlib block of
`swingbot/core/analytics/expectancy_attribution.py` (first stdlib import,
before `import datetime as dt`):

```python
import bisect
import datetime as dt
```

Append after V226-6's `load_stop_width_live_rows`:

```python


#: The label of a row with no usable ``stop_atr``: counted, never bucketed,
#: never a look.
UNKNOWN = "unknown"
#: TRAIN quartile cut points (spec § Frozen bucket edges).
_QUARTILES = (0.25, 0.5, 0.75)


def _known_values(rows: list[dict], key: str) -> list[float]:
    return [value for value in (_positive_number(row.get(key)) for row in rows)
            if value is not None]


def _bucket_holds(values: list[float], low: float | None, high: float) -> bool:
    return any((low is None or value >= low) and value < high for value in values)


def frozen_edges(rows: list[dict], key: str) -> list[float]:
    """Quartile cut points of ``key`` over the rows' known values
    (``numpy.quantile``, linear), merged so that no bucket is empty. Reads
    nothing but ``key``: never ``r``. A value equal to an edge belongs to
    the bucket above it (``edge_label``)."""
    values = sorted(_known_values(rows, key))
    if len(values) < 2:
        return []
    edges: list[float] = []
    for edge in (float(cut) for cut in np.quantile(values, _QUARTILES, method="linear")):
        previous = edges[-1] if edges else None
        if edge <= values[0] or (previous is not None and edge <= previous):
            continue
        if _bucket_holds(values, previous, edge):
            edges.append(edge)
    while edges and values[-1] < edges[-1]:
        edges.pop()
    return edges


def edge_labels(edges: list[float]) -> list[str]:
    """``Q1 (<a)``, ``Q2 (a–b)``, ..., ``Qk (≥c)``; ``Q1 (all)`` with no edge."""
    if not edges:
        return ["Q1 (all)"]
    labels = [f"Q1 (<{edges[0]:.2f})"]
    labels += [f"Q{index + 2} ({low:.2f}–{high:.2f})"
               for index, (low, high) in enumerate(zip(edges, edges[1:]))]
    labels.append(f"Q{len(edges) + 1} (≥{edges[-1]:.2f})")
    return labels


def edge_label(value, edges: list[float]) -> str:
    """The bucket label of one value on frozen ``edges``; UNKNOWN when the
    value is not a finite positive number."""
    number = _positive_number(value)
    if number is None:
        return UNKNOWN
    return edge_labels(edges)[bisect.bisect_right(edges, number)]


def _bucketed(rows: list[dict], edges: list[float], labels: list[str]) -> dict:
    buckets: dict[str, list[dict]] = {label: [] for label in labels}
    known: list[dict] = []
    unknown = 0
    for row in rows:
        label = edge_label(row.get("stop_atr"), edges)
        if label == UNKNOWN:
            unknown += 1
            continue
        buckets[label].append(row)
        known.append(row)
    return {"buckets": buckets, "known": known, "unknown": unknown}


def stop_width_groups(train_rows: list[dict], live_rows: list[dict]) -> dict:
    """Both populations bucketed by ``stop_atr`` on edges frozen from TRAIN
    alone. The live book never moves an edge."""
    edges = frozen_edges(train_rows, "stop_atr")
    labels = edge_labels(edges)
    return {"edges": edges, "labels": labels,
            "train": _bucketed(train_rows, edges, labels),
            "live": _bucketed(live_rows, edges, labels)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_edges.py`
Expected: all passed.

Then: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: 3 passed (the default report is untouched).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`frozen_edges` is the largest new function, about 11).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_stop_width_edges.py
git commit -m "feat(v226): TRAIN-frozen stop_atr quartile edges, labels and bucketed populations (V226-7)"
```

### Task V226-8: Pre-registered verdict: six clauses, own BH family, study verdict

**Model:** opus — the pre-registered decision rule itself: six clause boundaries, a BH family that must not widen, and a three-way verdict that is computed once.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (append after V226-7's section)
- Create: `tests/analytics/test_stop_width_verdict.py`

**Interfaces:**
- Consumes: `_look(base_rows, comp_rows, seed) -> {"delta", "ci_low", "ci_high", "p"}` (:278; call shape `_look(rest, bucket, seed)`, delta = bucket − rest; an arm under `THIN_N` = 30 gets `delta` only); `_mean` (:131); `stats.bh_qvalues(pvalues) -> list` (`swingbot/core/backtesting/instrument/stats.py:86`; `None` passes through and is not counted in m); V226-7's `POP` shape (`groups["train"]`).
- Produces (part 3's report and Markdown read these exact names):
  - `VETO_DELTA = -0.10`, `VETO_MIN_N = 300`, `VETO_Q = 0.10`, `VETO_YEARS = ("2020", "2021", "2022", "2023")`, `VETO_MIN_YEARS = 3`
  - `STUDY_VERDICTS = ("VETO-CANDIDATE", "UNDERPOWERED", "NO CANDIDATE")`
  - `CLAUSE_KEYS = ("delta", "upper_bound", "negative_exp_r", "years", "n", "bh")` (spec clauses 1–6, in order)
  - `stop_width_verdict(train_groups: dict, *, seed: int) -> dict` = `{"verdict", "candidates": list[str], "family_size": int, "powered": int, "n_needed": 300, "looks": {label: LOOK}}` with `LOOK` keys in this order: `n, exp_r, delta, ci_low, ci_high, p, q, years ({year: float | None} over VETO_YEARS), years_negative, clauses ({CLAUSE_KEYS: bool}), candidate`

**The rule (spec § The pre-registered verdict, verbatim boundaries).** Per
TRAIN bucket, in label order, `rest` = every other known TRAIN row
(`id(row)` not in the bucket). A bucket is a candidate when all six hold:
1. `delta <= -0.10` (−0.10 passes, −0.099 fails); `None` fails;
2. `ci_high < 0` (exactly 0 fails); `None` fails;
3. bucket `exp_r < 0` (exactly 0 fails); `None` fails;
4. `years_negative >= 3`, where a year's Δ is mean(bucket `r` of that year) −
   mean(rest `r` of that year), the year of a row is `row["week"][:4]`
   (accepted choice), and a year where either side has no rows is `None`
   and counts against;
5. bucket `n >= 300`;
6. `q < 0.10` with `q` from `stats.bh_qvalues` over **this study's bucket
   looks only** (`family_size` = number of buckets, ≤ 4); `None` fails.
   `assign_qvalues` (v146's family) is never called.

Study verdict, in this precedence (accepted choice: a candidate wins over
too few powered buckets): any candidate → `VETO-CANDIDATE`; else fewer than
two buckets with `n >= 300` → `UNDERPOWERED`; else `NO CANDIDATE`.
`n_needed` is always `VETO_MIN_N` (300): the N per bucket an
`UNDERPOWERED` result names. The live book is never an input.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_stop_width_verdict.py`:

```python
"""v226: the pre-registered stop-width verdict -- every clause boundary, the
study's own BH family, and the three study verdicts. Clause boundaries are
driven through a stubbed ``_look`` so delta / bound / p are exact."""
from __future__ import annotations

import datetime as dt

import pytest

from swingbot.core.analytics import expectancy_attribution as ea

YEARS = ("2020", "2021", "2022", "2023")
NEG = {year: -0.5 for year in YEARS}
ZERO = {year: 0.0 for year in YEARS}
POS = {year: 0.2 for year in YEARS}
PASS = {"delta": -0.10, "ci_low": -0.2, "ci_high": -0.01, "p": 0.001}
FLAT = {"delta": 0.10, "ci_low": 0.0, "ci_high": 0.2, "p": 0.5}
LOOK_KEYS = ["n", "exp_r", "delta", "ci_low", "ci_high", "p", "q", "years",
             "years_negative", "clauses", "candidate"]


def _rows(n: int, tag: str, r_by_year: dict, years=YEARS) -> list[dict]:
    """``n`` rows tagged ``tag`` cycling over ``years``; r = r_by_year[year]."""
    out = []
    for i in range(n):
        year = years[i % len(years)]
        out.append({"r": r_by_year[year], "r_gross": r_by_year[year],
                    "week": f"{year}-03-02", "tag": tag, "stop_atr": 1.0})
    return out


def _groups(buckets: dict) -> dict:
    return {"buckets": dict(buckets),
            "known": [row for rows in buckets.values() for row in rows], "unknown": 0}


@pytest.fixture
def looks(monkeypatch):
    """tag -> the look ``_look`` returns for that bucket."""
    table = {}

    def fake_look(base, comp, seed):
        tag = comp[0]["tag"]
        assert all(row["tag"] != tag for row in base)        # rest never holds the bucket
        assert seed == 42
        return dict(table[tag])

    monkeypatch.setattr(ea, "_look", fake_look)
    return table


def _verdict(buckets: dict) -> dict:
    return ea.stop_width_verdict(_groups(buckets), seed=42)


def test_constants_are_the_pre_registered_values():
    assert (ea.VETO_DELTA, ea.VETO_MIN_N, ea.VETO_Q, ea.VETO_MIN_YEARS) == (-0.10, 300, 0.10, 3)
    assert ea.VETO_YEARS == YEARS
    assert ea.CLAUSE_KEYS == ("delta", "upper_bound", "negative_exp_r", "years", "n", "bh")
    assert ea.STUDY_VERDICTS == ("VETO-CANDIDATE", "UNDERPOWERED", "NO CANDIDATE")


def test_a_bucket_passing_all_six_clauses_is_a_candidate(looks):
    looks.update(A=PASS, B=FLAT)
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert list(out) == ["verdict", "candidates", "family_size", "powered", "n_needed", "looks"]
    assert out["verdict"] == "VETO-CANDIDATE" and out["candidates"] == ["A"]
    assert (out["family_size"], out["powered"], out["n_needed"]) == (2, 2, 300)
    look = out["looks"]["A"]
    assert list(look) == LOOK_KEYS
    assert look["clauses"] == dict.fromkeys(ea.CLAUSE_KEYS, True) and look["candidate"] is True
    assert look["n"] == 300 and look["exp_r"] == -0.5
    assert look["years"] == {year: -0.5 for year in YEARS} and look["years_negative"] == 4
    assert look["q"] == pytest.approx(0.002)
    assert out["looks"]["B"]["candidate"] is False


@pytest.mark.parametrize("delta, passes", [(-0.10, True), (-0.099, False), (-0.5, True),
                                           (None, False)])
def test_clause_1_delta_boundary(looks, delta, passes):
    looks.update(A=dict(PASS, delta=delta), B=FLAT)
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["clauses"]["delta"] is passes and look["candidate"] is passes


@pytest.mark.parametrize("ci_high, passes", [(-0.0001, True), (0.0, False), (0.01, False),
                                             (None, False)])
def test_clause_2_upper_bound_boundary(looks, ci_high, passes):
    looks.update(A=dict(PASS, ci_high=ci_high), B=FLAT)
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["clauses"]["upper_bound"] is passes


def test_clause_3_bucket_exp_r_exactly_zero_fails(looks):
    looks.update(A=PASS, B=FLAT)
    # 304 rows in blocks of four (one per year), blocks alternating +0.5 / -0.5:
    # every year's mean is exactly 0, so the bucket ExpR is exactly 0.0.
    zero_mean = [dict(row, r=0.5 if (i // 4) % 2 == 0 else -0.5)
                 for i, row in enumerate(_rows(304, "A", ZERO))]
    look = _verdict({"A": zero_mean, "B": _rows(300, "B", POS)})["looks"]["A"]
    assert look["exp_r"] == 0.0
    assert look["clauses"] == dict(dict.fromkeys(ea.CLAUSE_KEYS, True), negative_exp_r=False)
    assert look["candidate"] is False


def test_clause_4_three_of_four_years_passes(looks):
    looks.update(A=PASS, B=FLAT)
    mixed = dict(NEG, **{"2023": 0.5})
    look = _verdict({"A": _rows(300, "A", mixed), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["years_negative"] == 3 and look["years"]["2023"] == 0.5
    assert look["clauses"]["years"] is True and look["candidate"] is True


def test_clause_4_two_of_four_years_fails(looks):
    looks.update(A=PASS, B=FLAT)
    mixed = dict(NEG, **{"2022": 0.2, "2023": 0.2})
    look = _verdict({"A": _rows(300, "A", mixed), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["exp_r"] < 0 and look["years_negative"] == 2
    assert look["clauses"]["years"] is False and look["candidate"] is False


def test_clause_4_a_year_without_bucket_rows_counts_against(looks):
    looks.update(A=PASS, B=FLAT)
    two_years = _rows(300, "A", NEG, years=("2020", "2021"))
    look = _verdict({"A": two_years, "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["years"] == {"2020": -0.5, "2021": -0.5, "2022": None, "2023": None}
    assert look["years_negative"] == 2 and look["clauses"]["years"] is False


def test_clause_4_a_year_without_rest_rows_is_none_too(looks):
    looks.update(A=PASS, B=FLAT)
    rest_three = _rows(300, "B", ZERO, years=("2020", "2021", "2022"))
    look = _verdict({"A": _rows(300, "A", NEG), "B": rest_three})["looks"]["A"]
    assert look["years"]["2023"] is None and look["years_negative"] == 3
    assert look["clauses"]["years"] is True


def test_clause_5_n_299_fails_and_300_passes(looks):
    looks.update(A=PASS, B=FLAT)
    short = _verdict({"A": _rows(299, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert short["looks"]["A"]["clauses"]["n"] is False and short["candidates"] == []
    assert short["powered"] == 1 and short["verdict"] == "UNDERPOWERED"
    full = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert full["looks"]["A"]["clauses"]["n"] is True and full["verdict"] == "VETO-CANDIDATE"


def test_clause_6_q_exactly_0_10_fails(looks):
    looks.update(A=dict(PASS, p=0.05), B=FLAT)                # q_A = 0.05 * 2 / 1 = 0.10
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["q"] == pytest.approx(0.10)
    assert look["clauses"]["bh"] is False and look["candidate"] is False


def test_clause_6_a_thin_look_has_no_q_and_fails(looks):
    looks.update(A=dict(PASS, ci_low=None, ci_high=None, p=None), B=FLAT)
    look = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})["looks"]["A"]
    assert look["q"] is None and look["clauses"]["bh"] is False


def test_the_bh_family_is_this_studys_buckets_only(looks, monkeypatch):
    seen = []
    real = ea.stats.bh_qvalues

    def spy(pvalues):
        seen.append(list(pvalues))
        return real(pvalues)

    def refuse(*args, **kwargs):
        raise AssertionError("assign_qvalues is v146's family; the study never uses it")

    monkeypatch.setattr(ea.stats, "bh_qvalues", spy)
    monkeypatch.setattr(ea, "assign_qvalues", refuse)
    looks.update(A=dict(PASS, p=0.04), B=dict(FLAT, p=0.2), C=dict(FLAT, p=0.6))
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO),
                    "C": _rows(300, "C", ZERO)})
    assert seen == [[0.04, 0.2, 0.6]]                          # one family, label order
    assert out["family_size"] == 3
    assert out["looks"]["A"]["q"] == pytest.approx(0.12)       # 0.04 * 3 / 1: m is 3, not 2
    assert out["looks"]["A"]["candidate"] is False


def test_a_candidate_wins_over_too_few_powered_buckets(looks):
    looks.update(A=PASS, B=FLAT)
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(100, "B", ZERO)})
    assert out["powered"] == 1 and out["verdict"] == "VETO-CANDIDATE"


def test_no_candidate_with_two_powered_buckets_closes_the_question(looks):
    looks.update(A=dict(PASS, delta=-0.05), B=FLAT)
    out = _verdict({"A": _rows(300, "A", NEG), "B": _rows(300, "B", ZERO)})
    assert out["verdict"] == "NO CANDIDATE" and out["candidates"] == []


def test_fewer_than_two_powered_buckets_is_underpowered(looks):
    looks.update(A=dict(PASS, delta=-0.05), B=FLAT)
    out = _verdict({"A": _rows(120, "A", NEG), "B": _rows(100, "B", ZERO)})
    assert out["verdict"] == "UNDERPOWERED" and out["powered"] == 0 and out["n_needed"] == 300


def test_an_empty_train_population_is_underpowered():
    out = ea.stop_width_verdict(ea.stop_width_groups([], [])["train"], seed=42)
    assert out["verdict"] == "UNDERPOWERED" and out["family_size"] == 1
    assert out["looks"]["Q1 (all)"]["exp_r"] is None
    assert out["looks"]["Q1 (all)"]["candidate"] is False


def test_end_to_end_on_real_looks_flags_the_losing_tight_bucket(monkeypatch):
    """Real ``_look`` (few resamples): tight stops lose, the rest earn."""
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)
    rows = []
    for i in range(1600):
        stop_atr = 0.2 + (i % 8) * 0.1
        wobble = ((i * 37) % 11 - 5) / 50.0
        rows.append({"r": (-0.6 if stop_atr < 0.35 else 0.1) + wobble, "r_gross": 0.0,
                     "week": (dt.date(2020, 1, 6) + dt.timedelta(weeks=i % 200)).isoformat(),
                     "stop_atr": stop_atr})
    groups = ea.stop_width_groups(rows, [])
    out = ea.stop_width_verdict(groups["train"], seed=42)
    assert out["family_size"] == len(groups["labels"]) <= 4
    first = groups["labels"][0]
    assert out["looks"][first]["n"] == 400 and out["looks"][first]["delta"] < -0.5
    assert all(out["looks"][label]["p"] is not None for label in groups["labels"])
    assert out["candidates"] == [first] and out["verdict"] == "VETO-CANDIDATE"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_verdict.py`
Expected: FAIL with `AttributeError: ... has no attribute 'VETO_DELTA'` / `'stop_width_verdict'`.

- [ ] **Step 3: Implement**

Append after V226-7's `stop_width_groups`:

```python


#: Spec § The pre-registered verdict (TRAIN only, computed once).
VETO_DELTA = -0.10            # clause 1: delta <= -0.10R (exactly -0.10 passes)
VETO_MIN_N = 300              # clause 5, and the N per bucket "powered" means
VETO_Q = 0.10                 # clause 6: BH q < 0.10 over this study's own family
VETO_YEARS = ("2020", "2021", "2022", "2023")    # clause 4: the TRAIN calendar years
VETO_MIN_YEARS = 3            # clause 4: delta < 0 in at least 3 of them
STUDY_VERDICTS = ("VETO-CANDIDATE", "UNDERPOWERED", "NO CANDIDATE")
#: Clauses 1-6 in spec order.
CLAUSE_KEYS = ("delta", "upper_bound", "negative_exp_r", "years", "n", "bh")


def _rest_of(bucket: list[dict], known: list[dict]) -> list[dict]:
    ids = {id(row) for row in bucket}
    return [row for row in known if id(row) not in ids]


def _year_deltas(bucket: list[dict], rest: list[dict]) -> dict:
    """Per TRAIN year (``week[:4]``): bucket ExpR - rest ExpR, None when
    either side has no row that year (such a year counts against clause 4)."""
    out = {}
    for year in VETO_YEARS:
        mine = _mean([row["r"] for row in bucket if row["week"][:4] == year])
        other = _mean([row["r"] for row in rest if row["week"][:4] == year])
        out[year] = None if mine is None or other is None else mine - other
    return out


def _bucket_look(bucket: list[dict], known: list[dict], seed: int) -> dict:
    rest = _rest_of(bucket, known)
    look = _look(rest, bucket, seed)
    years = _year_deltas(bucket, rest)
    return {"n": len(bucket), "exp_r": _mean([row["r"] for row in bucket]),
            "delta": look["delta"], "ci_low": look["ci_low"], "ci_high": look["ci_high"],
            "p": look["p"], "q": None, "years": years,
            "years_negative": sum(1 for value in years.values()
                                  if value is not None and value < 0)}


def _clauses(look: dict) -> dict:
    """The six pre-registered clauses; a missing number fails its clause."""
    delta, high, exp_r, q = look["delta"], look["ci_high"], look["exp_r"], look["q"]
    return {"delta": delta is not None and delta <= VETO_DELTA,
            "upper_bound": high is not None and high < 0,
            "negative_exp_r": exp_r is not None and exp_r < 0,
            "years": look["years_negative"] >= VETO_MIN_YEARS,
            "n": look["n"] >= VETO_MIN_N,
            "bh": q is not None and q < VETO_Q}


def _study_verdict(candidates: list[str], powered: int) -> str:
    if candidates:
        return "VETO-CANDIDATE"
    if powered < 2:
        return "UNDERPOWERED"
    return "NO CANDIDATE"


def stop_width_verdict(train_groups: dict, *, seed: int) -> dict:
    """The pre-registered verdict over the TRAIN buckets of
    ``stop_width_groups(...)["train"]``: one look per bucket against every
    other known TRAIN row, BH over these looks only (never ``assign_qvalues``,
    never a live look), six clauses per bucket, one study verdict."""
    known = train_groups["known"]
    looks = {label: _bucket_look(bucket, known, seed)
             for label, bucket in train_groups["buckets"].items()}
    labels = list(looks)
    qvalues = stats.bh_qvalues([looks[label]["p"] for label in labels])
    for label, q in zip(labels, qvalues):
        look = looks[label]
        look["q"] = q
        look["clauses"] = _clauses(look)
        look["candidate"] = all(look["clauses"].values())
    candidates = [label for label in labels if looks[label]["candidate"]]
    powered = sum(1 for label in labels if looks[label]["n"] >= VETO_MIN_N)
    return {"verdict": _study_verdict(candidates, powered), "candidates": candidates,
            "family_size": len(labels), "powered": powered, "n_needed": VETO_MIN_N,
            "looks": looks}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_verdict.py`
Expected: all passed.

Then: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: 3 passed.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_year_deltas` and `stop_width_verdict` about 8, `_clauses` about 6).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_stop_width_verdict.py
git commit -m "feat(v226): pre-registered stop-width verdict -- six clauses, own BH family, three study verdicts (V226-8)"
```

### Task V226-9: Disclosures: bucket stats, mix, clamped share, live same-day losses, rho, overlap, removal arithmetic

**Model:** sonnet — descriptive statistics over the V226-7 groups with fixed definitions; nothing here gates.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (append after V226-8's section)
- Create: `tests/analytics/test_stop_width_disclosures.py`

**Interfaces:**
- Consumes: `bucket_stats(rows) -> {"n", "win_rate", "exp_r", "exp_r_gross", "thin"}` (:135), `_mean`, `_label` (:152, `None`/`""` → `"unknown"`), `_sort_key` (:156), `_spearman(xs, ys) -> float | None` (:312; None under 3 points or a constant side); V226-6 `_positive_number`; V226-7 `frozen_edges`, `stop_width_groups` output (`{"edges", "labels", "train": POP, "live": POP}`); V226-8 `_rest_of(bucket, known)`; `bisect` (imported in V226-7).
- Produces (part 3's report and Markdown read these exact names):
  - `VOLATILITY_RHO = 0.8`, `DIRECTION_MIN_N = 100`
  - `stop_width_disclosures(groups: dict) -> dict` = `{"train": DISC, "live": DISC}`, `DISC = {"unknown": int, "rho": float | None, "overlap": float | None, "buckets": {label: BUCKET}}` (every label, in order), `BUCKET` keys in this order: `n, win_rate, exp_r, exp_r_gross, median_rr, direction_share, horizon_share, delta_by_direction, clamped_share, clamped_none, removal` (`removal = {"pooled_exp_r", "without_exp_r", "delta_total_r", "n_removed"}`), then **live only** `family_share, same_day_loss_share`

**Definitions (spec § Disclosures; printed, never gating).** Per population
(TRAIN and live separately; live rows sit on the TRAIN edges already):
- `n`, `win_rate` (percent), `exp_r` (net), `exp_r_gross`: `bucket_stats`.
- `median_rr`: median of numeric `risk_reward_ratio` (bools and None skipped); None when none.
- `direction_share`, `horizon_share`, live `family_share` (from `strategy`): `{label: fraction of the bucket}`, labels through `_label` (None → `"unknown"`) and ordered by `_sort_key`; `{}` for an empty bucket.
- `delta_by_direction[d]` for `d` in `("bullish", "bearish")`: bucket ExpR − rest ExpR within `d`, only when the bucket has ≥ 100 rows of `d` and the rest has at least one; else None.
- `clamped_share` = True / (True + False) over the bucket, None when both are 0; `clamped_none` = rows whose flag is None (they leave the denominator). A **lower-bound provenance flag**: identity-based, read at run time.
- `removal`: `pooled_exp_r` over the population's known rows; `without_exp_r` = ExpR of the rest (equals the verdict's rest ExpR); `delta_total_r` = −(sum of the bucket's `r`); `n_removed` = bucket N.
- live `same_day_loss_share`: losses (`r < 0`) whose `opened_at[:10] == closed_at[:10]` (UTC ISO dates as stored), over all losses in the bucket (a loss missing a timestamp counts in the denominator only); None with no loss. **Never computed for TRAIN** (no timestamps on the TRAIN row).
- `rho`: `_spearman(stop_atr, atr_pct)` over the population's known rows that have a positive `atr_pct`. `overlap`: share of those rows whose `stop_atr` bucket index equals `len(atr_edges) − atr_pct bucket index`, with `atr_edges = frozen_edges(train known rows, "atr_pct")` (TRAIN, for both populations), indices by `bisect.bisect_right`. None when no row has `atr_pct`.
- `unknown`: the population's unknown count from the groups.

`VOLATILITY_RHO` is read by part 3 (`volatility_note = |TRAIN rho| ≥ 0.8`); this task only defines it.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_stop_width_disclosures.py`:

```python
"""v226: stop-width disclosures -- per-bucket stats and mix, the clamped
share with None rows out of its denominator, the live-only family and
same-day-loss shares, rho/overlap of stop_atr vs atr_pct, and the removal
arithmetic. Printed, never gating."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import expectancy_attribution as ea

TRAIN_KEYS = ["n", "win_rate", "exp_r", "exp_r_gross", "median_rr", "direction_share",
              "horizon_share", "delta_by_direction", "clamped_share", "clamped_none",
              "removal"]
LIVE_KEYS = TRAIN_KEYS + ["family_share", "same_day_loss_share"]


def _row(r=0.0, *, stop_atr=1.0, direction="bullish", horizon="2w", atr_pct=None,
         clamped=None, rr=2.0, **extra) -> dict:
    row = {"r": r, "r_gross": r + 0.05, "week": "2021-03-01", "direction": direction,
           "horizon": horizon, "risk_reward_ratio": rr, "stop_atr": stop_atr,
           "atr_pct": atr_pct, "stop_clamped": clamped}
    row.update(extra)
    return row


def _pop(buckets: dict, unknown: int = 0) -> dict:
    return {"buckets": dict(buckets),
            "known": [row for rows in buckets.values() for row in rows], "unknown": unknown}


def _groups(train: dict, live: dict | None = None, *, unknown=(0, 0)) -> dict:
    live = live if live is not None else {label: [] for label in train}
    return {"edges": [1.5], "labels": list(train),
            "train": _pop(train, unknown[0]), "live": _pop(live, unknown[1])}


def test_the_shape_is_per_population_and_live_has_two_more_keys():
    groups = _groups({"Q1": [_row(-1.0)], "Q2": [_row(1.0)]}, unknown=(3, 1))
    out = ea.stop_width_disclosures(groups)
    assert list(out) == ["train", "live"]
    for name in ("train", "live"):
        assert list(out[name]) == ["unknown", "rho", "overlap", "buckets"]
        assert list(out[name]["buckets"]) == ["Q1", "Q2"]
    assert list(out["train"]["buckets"]["Q1"]) == TRAIN_KEYS
    assert list(out["live"]["buckets"]["Q1"]) == LIVE_KEYS
    assert (out["train"]["unknown"], out["live"]["unknown"]) == (3, 1)
    assert ea.VOLATILITY_RHO == 0.8 and ea.DIRECTION_MIN_N == 100


def test_bucket_stats_median_rr_and_mix():
    bucket = [_row(1.0, rr=2.0), _row(-1.0, rr=3.0, direction="bearish"),
              _row(-1.0, rr=None, horizon="4w"), _row(0.5, rr=True)]
    disc = ea.stop_width_disclosures(_groups({"Q1": bucket}))["train"]["buckets"]["Q1"]
    assert (disc["n"], disc["win_rate"]) == (4, 50.0)
    assert disc["exp_r"] == pytest.approx(-0.125)
    assert disc["exp_r_gross"] == pytest.approx(-0.075)
    assert disc["median_rr"] == 2.5                           # None and the bool skipped
    assert disc["direction_share"] == {"bearish": 0.25, "bullish": 0.75}
    assert disc["horizon_share"] == {"2w": 0.75, "4w": 0.25}


def test_delta_within_a_direction_needs_100_bucket_rows_of_it():
    q1 = [_row(-1.0) for _ in range(100)] + [_row(-1.0, direction="bearish") for _ in range(99)]
    q2 = [_row(0.0) for _ in range(50)] + [_row(0.5, direction="bearish") for _ in range(50)]
    out = ea.stop_width_disclosures(_groups({"Q1": q1, "Q2": q2}))["train"]["buckets"]
    assert out["Q1"]["delta_by_direction"] == {"bullish": -1.0, "bearish": None}
    assert out["Q2"]["delta_by_direction"] == {"bullish": None, "bearish": None}


def test_delta_within_a_direction_needs_rest_rows_of_it():
    q1 = [_row(-1.0) for _ in range(100)]
    q2 = [_row(0.5, direction="bearish") for _ in range(10)]
    out = ea.stop_width_disclosures(_groups({"Q1": q1, "Q2": q2}))["train"]["buckets"]
    assert out["Q1"]["delta_by_direction"]["bullish"] is None


def test_clamped_share_leaves_none_rows_out_of_the_denominator():
    bucket = [_row(clamped=True), _row(clamped=True), _row(clamped=False),
              _row(clamped=None), _row(clamped=None)]
    unflagged = [_row(clamped=None), _row(clamped=None)]
    out = ea.stop_width_disclosures(_groups({"Q1": bucket, "Q2": unflagged}))["train"]["buckets"]
    assert out["Q1"]["clamped_share"] == pytest.approx(2 / 3) and out["Q1"]["clamped_none"] == 2
    assert out["Q2"]["clamped_share"] is None and out["Q2"]["clamped_none"] == 2


def test_removal_arithmetic_matches_the_rest_and_the_bucket_sum():
    q1 = [_row(-1.0), _row(-1.0), _row(0.5)]
    q2 = [_row(1.0), _row(0.5)]
    out = ea.stop_width_disclosures(_groups({"Q1": q1, "Q2": q2}))["train"]["buckets"]
    first = out["Q1"]["removal"]
    assert list(first) == ["pooled_exp_r", "without_exp_r", "delta_total_r", "n_removed"]
    assert first["pooled_exp_r"] == pytest.approx(0.0)
    assert first["without_exp_r"] == pytest.approx(0.75)      # = rest ExpR (Q2)
    assert first["delta_total_r"] == pytest.approx(1.5)       # -(-1 - 1 + 0.5)
    assert first["n_removed"] == 3
    second = out["Q2"]["removal"]
    assert second["without_exp_r"] == pytest.approx(-0.5)
    assert second["delta_total_r"] == pytest.approx(-1.5)
    total = sum(row["r"] for row in q1 + q2)
    assert total + first["delta_total_r"] == pytest.approx(sum(row["r"] for row in q2))


def test_an_empty_live_bucket_discloses_nothing_but_counts():
    groups = _groups({"Q1": [_row(-1.0)], "Q2": [_row(1.0)]},
                     {"Q1": [], "Q2": [_row(0.3, strategy="FVG")]})
    empty = ea.stop_width_disclosures(groups)["live"]["buckets"]["Q1"]
    assert (empty["n"], empty["exp_r"], empty["median_rr"]) == (0, None, None)
    assert empty["direction_share"] == {} and empty["family_share"] == {}
    assert (empty["clamped_share"], empty["clamped_none"]) == (None, 0)
    assert empty["same_day_loss_share"] is None
    assert empty["removal"] == {"pooled_exp_r": pytest.approx(0.3), "without_exp_r": pytest.approx(0.3),
                                "delta_total_r": 0.0, "n_removed": 0}


def test_live_family_and_same_day_loss_shares():
    live_q1 = [
        _row(-1.0, strategy="Fib 61.8%", opened_at="2026-11-03T14:31:00+00:00",
             closed_at="2026-11-03T19:02:00+00:00"),
        _row(-0.4, strategy="FVG", opened_at="2026-11-04T14:31:00+00:00",
             closed_at="2026-11-04T15:10:00+00:00"),
        _row(-1.0, strategy="FVG", opened_at="2026-11-04T14:31:00+00:00",
             closed_at="2026-11-06T15:10:00+00:00"),
        _row(-0.2, strategy=None, opened_at="2026-11-05T14:31:00+00:00", closed_at=None),
        _row(2.0, strategy="FVG", opened_at="2026-11-05T14:31:00+00:00",
             closed_at="2026-11-05T20:00:00+00:00"),                 # a same-day win: not a loss
    ]
    groups = _groups({"Q1": [_row(-1.0)]}, {"Q1": live_q1})
    out = ea.stop_width_disclosures(groups)
    live = out["live"]["buckets"]["Q1"]
    assert live["same_day_loss_share"] == pytest.approx(2 / 4)
    assert live["family_share"] == {"FVG": 0.6, "Fib 61.8%": 0.2, "unknown": 0.2}
    assert "same_day_loss_share" not in out["train"]["buckets"]["Q1"]
    assert "family_share" not in out["train"]["buckets"]["Q1"]


def test_a_live_bucket_without_losses_has_no_same_day_share():
    groups = _groups({"Q1": [_row(-1.0)]}, {"Q1": [_row(1.0, opened_at="2026-11-03",
                                                       closed_at="2026-11-03")]})
    assert ea.stop_width_disclosures(groups)["live"]["buckets"]["Q1"]["same_day_loss_share"] is None


def test_rho_and_overlap_of_mirrored_stop_atr_and_atr_pct():
    """atr_pct = 2 / stop_atr: perfectly inverse, so rho is -1 and every row
    lands in the mirrored quartile."""
    train = [_row(stop_atr=float(v), atr_pct=2.0 / v) for v in range(1, 9)]
    train += [_row(stop_atr=9.0, atr_pct=None)]               # no atr_pct: out of rho and overlap
    live = [_row(stop_atr=1.0, atr_pct=2.0), _row(stop_atr=8.0, atr_pct=0.25)]
    out = ea.stop_width_disclosures(ea.stop_width_groups(train, live))
    assert out["train"]["rho"] == pytest.approx(-1.0)
    assert out["train"]["overlap"] == pytest.approx(1.0)
    assert out["live"]["rho"] is None                         # under 3 points
    assert out["live"]["overlap"] == pytest.approx(1.0)       # on the TRAIN atr_pct edges


def test_no_atr_pct_gives_no_rho_and_no_overlap():
    out = ea.stop_width_disclosures(_groups({"Q1": [_row(-1.0)], "Q2": [_row(1.0)]}))
    assert (out["train"]["rho"], out["train"]["overlap"]) == (None, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_disclosures.py`
Expected: FAIL with `AttributeError: ... has no attribute 'stop_width_disclosures'`.

- [ ] **Step 3: Implement**

Append after V226-8's `stop_width_verdict`:

```python


#: |Spearman rho(stop_atr, atr_pct)| on TRAIN at or above this: the results
#: doc says the verdict is about ticker volatility, not stop placement.
VOLATILITY_RHO = 0.8
#: Delta within one direction is shown only from this many bucket rows of it.
DIRECTION_MIN_N = 100
_DIRECTIONS = ("bullish", "bearish")


def _shares(rows: list[dict], key: str) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        label = _label(row.get(key))
        counts[label] = counts.get(label, 0) + 1
    return {label: counts[label] / len(rows) for label in sorted(counts, key=_sort_key)}


def _median_rr(rows: list[dict]) -> float | None:
    values = [float(value) for value in (row.get("risk_reward_ratio") for row in rows)
              if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return float(np.median(values)) if values else None


def _direction_deltas(bucket: list[dict], rest: list[dict]) -> dict:
    out = {}
    for direction in _DIRECTIONS:
        mine = [row["r"] for row in bucket if row.get("direction") == direction]
        other = [row["r"] for row in rest if row.get("direction") == direction]
        out[direction] = (_mean(mine) - _mean(other)
                          if len(mine) >= DIRECTION_MIN_N and other else None)
    return out


def _clamped_share(rows: list[dict]) -> dict:
    """A lower-bound provenance flag: None rows leave the denominator and are
    counted on their own."""
    flags = [row.get("stop_clamped") for row in rows]
    yes = sum(1 for flag in flags if flag is True)
    no = sum(1 for flag in flags if flag is False)
    return {"clamped_share": yes / (yes + no) if yes + no else None,
            "clamped_none": len(flags) - yes - no}


def _removal(bucket: list[dict], rest: list[dict], known: list[dict]) -> dict:
    return {"pooled_exp_r": _mean([row["r"] for row in known]),
            "without_exp_r": _mean([row["r"] for row in rest]),
            "delta_total_r": 0.0 - sum(row["r"] for row in bucket),
            "n_removed": len(bucket)}


def _same_day(row: dict) -> bool:
    opened, closed = row.get("opened_at"), row.get("closed_at")
    return bool(opened and closed) and opened[:10] == closed[:10]


def _same_day_loss_share(rows: list[dict]) -> float | None:
    """Live only: losses closed on their entry day (UTC dates as stored)."""
    losses = [row for row in rows if row["r"] < 0]
    if not losses:
        return None
    return sum(1 for row in losses if _same_day(row)) / len(losses)


def _bucket_disclosure(bucket: list[dict], known: list[dict], *, live: bool) -> dict:
    rest = _rest_of(bucket, known)
    base = bucket_stats(bucket)
    out = {"n": base["n"], "win_rate": base["win_rate"], "exp_r": base["exp_r"],
           "exp_r_gross": base["exp_r_gross"], "median_rr": _median_rr(bucket),
           "direction_share": _shares(bucket, "direction"),
           "horizon_share": _shares(bucket, "horizon"),
           "delta_by_direction": _direction_deltas(bucket, rest),
           **_clamped_share(bucket),
           "removal": _removal(bucket, rest, known)}
    if live:
        out["family_share"] = _shares(bucket, "strategy")
        out["same_day_loss_share"] = _same_day_loss_share(bucket)
    return out


def _rho_and_overlap(known: list[dict], edges: list[float],
                     atr_edges: list[float]) -> tuple[float | None, float | None]:
    """Spearman rho of stop_atr vs atr_pct, and the share of rows whose
    stop_atr bucket mirrors their atr_pct bucket (atr_pct on TRAIN edges)."""
    pairs = [(row["stop_atr"], value) for row in known
             if (value := _positive_number(row.get("atr_pct"))) is not None]
    if not pairs:
        return None, None
    rho = _spearman([stop for stop, _ in pairs], [pct for _, pct in pairs])
    top = len(atr_edges)
    same = sum(1 for stop, pct in pairs
               if bisect.bisect_right(edges, stop) == top - bisect.bisect_right(atr_edges, pct))
    return rho, same / len(pairs)


def _population_disclosure(pop: dict, edges: list[float], atr_edges: list[float],
                           *, live: bool) -> dict:
    rho, overlap = _rho_and_overlap(pop["known"], edges, atr_edges)
    return {"unknown": pop["unknown"], "rho": rho, "overlap": overlap,
            "buckets": {label: _bucket_disclosure(rows, pop["known"], live=live)
                        for label, rows in pop["buckets"].items()}}


def stop_width_disclosures(groups: dict) -> dict:
    """Printed beside the verdict, never gating: per population (TRAIN and
    live, never pooled) and per bucket on the TRAIN edges."""
    atr_edges = frozen_edges(groups["train"]["known"], "atr_pct")
    return {name: _population_disclosure(groups[name], groups["edges"], atr_edges,
                                         live=name == "live")
            for name in ("train", "live")}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_disclosures.py`
Expected: all passed.

Then the earlier study files and the pin, all in this part:
`python scripts/dev/testrun.py file tests/analytics/test_stop_width_verdict.py`,
`python scripts/dev/testrun.py file tests/analytics/test_stop_width_edges.py`,
`python scripts/dev/testrun.py file tests/analytics/test_stop_width_rows.py`,
`python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: all passed.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function 8 or below).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_stop_width_disclosures.py
git commit -m "feat(v226): stop-width disclosures -- mix, clamped share, live same-day losses, rho/overlap, removal arithmetic (V226-9)"
```

