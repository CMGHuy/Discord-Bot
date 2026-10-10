# v146 Expectancy attribution: Implementation Plan, part 2a -- instruments I2, I4, I3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: pull one task with `/task-brief V146-7` or `grep -n "^### Task V146-7:" -A 400 docs/superpowers/plans/2026-10-09-v146-expectancy-attribution_2a-instruments.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`](../specs/2026-10-09-v146-expectancy-attribution-design.md)
**Index:** [`2026-10-09-v146-expectancy-attribution_0-index.md`](2026-10-09-v146-expectancy-attribution_0-index.md) -- Global Constraints, Handoff decisions, `## Parallelisation` and the task ledger live there and bind every task below.

**Scope of this part:** V146-5 (I2: `days_to_earnings` populated on live plans), V146-6 (I4: the `confluence` and `rs_quintile` Analytics dimensions), V146-7 (I3: replay hits, the TRAIN-only `neutral_expectancy` switch and the TRAIN per-trade row), V146-8 (I3: `--trades-jsonl` with `--scenarios`, the as-of map and SPY plumbing) is in [`_2b-instruments-trades-jsonl`](2026-10-09-v146-expectancy-attribution_2b-instruments-trades-jsonl.md): a file boundary only, same part.

**Working directory:** every path below is relative to the v146 worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution` (created in V146-1 Step 0). Never `cd` in Bash; run commands with absolute paths or from the worktree root the session already sits in. After each task, `git -C E:/Documents/Private/Projects/Discord-Bot status --short` must show the main tree unchanged.

**Part-2 decisions (final; each stays inside the ledger contracts):**

1. **I2 stamps only on the live wall clock.** `attach_plan_v2` stamps `days_to_earnings` only when `issued_at is None` (the `QualifyContext.issued_at` docstring: "None = wall clock (live only)"). A historical replay (`scan_replay.py`, which supplies `issued_at`) gets `None`: `LiveSource` answers with *today's* Yahoo calendar, which is lookahead for a past decision date. This keeps the spec's "historical rows stay None; live, the as-of answer is today's calendar".
2. **Hermetic tests for I2.** `LiveSource` reaches Yahoo. `tests/scanning/conftest.py` gains one autouse fixture that points `analyze._earnings_source` at an empty source, so the existing `attach_plan_v2` tests never touch the network; the new tests override it with their own stub.
3. **`_replay_ticker` keeps calling `replay_scenarios` by name.** `tests/scripts/test_training_universe.py` monkeypatches `bs.replay_scenarios` and `bs.simulate_exit` (returning strings) and pins `_replay_ticker`'s dict. V146-8's shared loop indexes hits as `hit[0]`, `hit[1]` (a `ReplayHit` is a `NamedTuple` whose first two fields are `i`, `plan`), so the plain `(i, plan)` tuples and the detailed hits go through the same code.
4. **SPY is shipped to workers only when rows are collected.** `run_scenario_backtest` appends `spy_df` as `args[10]` only when `collect_rows=True`; the aggregate-only path keeps today's 10-tuple and IPC volume.
5. **The TRAIN score is computed on a copy of the scenario.** The legacy scorer appends to `scenario.target_sources` (squeeze / candlestick lines); scoring a `dataclasses.replace` copy with copied lists leaves the replay's scenario and plan untouched.
6. **Stop confluence for the TRAIN score** uses the replay's own tolerance, `REPLAY_CONFLUENCE_TOLERANCE_PCT = 5.0` (the literal the replay already passes for target confluence; `CONFLUENCE_DEVIATION_PCT`'s shipped default is also 5.0).
7. **Rows are written only for closed exits** (`outcome != "not_triggered"`, the same definition `_aggregate` uses for `closed`).

---

# Phase 2 -- I2 and I4: earnings stamp and analytics dimensions

### Task V146-5: `days_to_earnings` populated on live plans

**Model:** sonnet -- two small helpers and one keyword argument in a known function, with a stubbed-source test; no statistics and no shared contract beyond the ledger names.

**Cross-plan (audit 2026-10-10):** swallowed-error ratchet (owner v148; full rule in the v148 index, cited in this plan's index). If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), `_days_to_earnings`' handler is written `except Exception as exc:` and its first statement is `swallowed(log, "scan._days_to_earnings", exc, level=logging.DEBUG)` (import `swallowed` from `swingbot.core.infra.swallowed`, and `logging` if `analyze.py` lacks it); the existing `log.debug(...)` line stays after it. Step 5 then also runs `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` (expected PASS; never raise its `BASELINE`). If v148 is not merged, write the handler as below.

**Depends on:** V146-4 (shared file `swingbot/core/scanning/analyze.py`). Run after V146-4 is committed.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (imports near lines 9-30; new helpers above `attach_plan_v2`, which starts near line 349; the `risk_features.build(...)` call near lines 403-422)
- Modify: `swingbot/core/scanning/risk_features.py` (the comment above `"days_to_earnings"`, lines 63-64)
- Modify: `tests/scanning/conftest.py` (one autouse fixture; part-2 decision 2)
- Create: `tests/scanning/test_days_to_earnings_stamp.py`

**Interfaces:**
- Consumes: `earnings_calendar.sessions_to_reaction(ticker, asof: dt.date, *, source: EarningsSource, calendar=None) -> int | None` (`swingbot/core/market/earnings_calendar.py:116`); `earnings_calendar.LiveSource` (`:96`); `earnings_calendar.Report(date, timing)` (`:24`); `risk_features.build(..., days_to_earnings=None)` (`swingbot/core/scanning/risk_features.py:48`).
- Produces: `analyze._earnings_source() -> EarningsSource` (returns `earnings_calendar.LiveSource()`; the seam tests patch); `analyze._days_to_earnings(ticker: str, df) -> int | None`; `analyze._decision_session_date(df) -> datetime.date` (internal). `plan.risk_features["days_to_earnings"]` now carries NYSE sessions to the next earnings reaction session on live plans; `None` on a historical replay (`issued_at` supplied), a failed or empty fetch, a fund, or any exception.

- [ ] **Step 1: Make the existing `attach_plan_v2` tests hermetic**

`LiveSource` calls Yahoo. Add this fixture at the end of `tests/scanning/conftest.py` (the module already imports `pytest` and `swingbot.core.scanning.engine`, so `analyze` is loaded):

```python
class _NoEarnings:
    """An earnings source with no reports -- what a fund looks like."""

    def reports(self, ticker):
        return []


@pytest.fixture(autouse=True)
def _no_live_earnings(monkeypatch):
    """v146 I2: attach_plan_v2 now asks the live earnings calendar (Yahoo)
    for days_to_earnings. No scanning test may reach the network, so every
    test here sees an empty calendar; a test that needs real readings
    patches analyze._earnings_source with its own stub."""
    from swingbot.core.scanning import analyze
    monkeypatch.setattr(analyze, "_earnings_source", lambda: _NoEarnings())
```

This fixture references `analyze._earnings_source`, which does not exist yet, so every test in `tests/scanning/` errors until Step 4. That is expected; Step 2 writes the failing tests first.

- [ ] **Step 2: Write the failing tests**

Create `tests/scanning/test_days_to_earnings_stamp.py`:

```python
"""v146 I2: attach_plan_v2 stamps risk_features.days_to_earnings from the
live earnings calendar, as of the decision bar, and never blocks a plan."""
import datetime as dt
from types import SimpleNamespace

import pandas as pd

from swingbot.core.market import earnings_calendar
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import analyze
from tests.helpers import make_ohlcv


class _StubSource:
    def __init__(self, reports):
        self._reports = list(reports)
        self.calls = []

    def reports(self, ticker):
        self.calls.append(ticker)
        return list(self._reports)


class _RaisingSource:
    def reports(self, ticker):
        raise RuntimeError("earnings fetch failed")


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-09-16", source="confluence",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=98.0, tp1=110.0,
                       tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
                       quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                       status=PlanStatus.PENDING)


def _attach(monkeypatch, source, *, issued_at=None):
    import swingbot.config as config
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: None)
    monkeypatch.setattr(analyze, "_earnings_source", lambda: source)
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    item = SimpleNamespace(rs_combined=None, sector_rs_percentile=None, conf=None,
                           htf_bias=None, target_confluence=None)
    scenario = SimpleNamespace(direction="bullish", entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "AAPL", "3m", rs_percentile=50.0,
                           regime2_state="bull_quiet", issued_at=issued_at)
    return item, df


def test_stamp_equals_sessions_to_reaction_as_of_the_decision_bar(monkeypatch):
    last = make_ohlcv([100.0] * 300, start="2025-06-02").index[-1].date()
    source = _StubSource([earnings_calendar.Report(last + dt.timedelta(days=14), "after_close")])
    item, _ = _attach(monkeypatch, source)
    expected = earnings_calendar.sessions_to_reaction("AAPL", last, source=source)
    assert expected is not None and expected > 0
    assert item.plan_v2.risk_features["days_to_earnings"] == expected
    assert source.calls and set(source.calls) == {"AAPL"}


def test_a_raising_source_stamps_none_and_the_plan_still_posts(monkeypatch):
    item, _ = _attach(monkeypatch, _RaisingSource())
    assert item.plan_v2 is not None
    rf = item.plan_v2.risk_features
    assert rf["days_to_earnings"] is None
    assert rf["regime2_state"] == "bull_quiet"     # the rest of the stamp survived


def test_an_empty_calendar_stamps_none(monkeypatch):
    item, _ = _attach(monkeypatch, _StubSource([]))
    assert item.plan_v2.risk_features["days_to_earnings"] is None


def test_a_historical_replay_never_asks_the_live_calendar(monkeypatch):
    source = _StubSource([earnings_calendar.Report(dt.date(2026, 7, 30), "after_close")])
    item, _ = _attach(monkeypatch, source, issued_at="2025-01-02T21:00:00+00:00")
    assert item.plan_v2.risk_features["days_to_earnings"] is None
    assert source.calls == []


def test_decision_session_date_is_the_et_date_of_the_last_bar():
    naive = make_ohlcv([100.0] * 3, start="2026-07-20")
    assert analyze._decision_session_date(naive) == dt.date(2026, 7, 22)
    aware = pd.DataFrame({"Close": [1.0]},
                         index=pd.DatetimeIndex([pd.Timestamp("2026-07-24 03:00", tz="UTC")]))
    assert analyze._decision_session_date(aware) == dt.date(2026, 7, 23)   # 23:00 ET the day before


def test_days_to_earnings_swallows_a_bad_frame(monkeypatch):
    monkeypatch.setattr(analyze, "_earnings_source", lambda: _StubSource([]))
    assert analyze._days_to_earnings("AAPL", pd.DataFrame()) is None
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_days_to_earnings_stamp.py`
Expected: FAIL / ERROR -- `AttributeError: <module 'swingbot.core.scanning.analyze'> has no attribute '_earnings_source'` (raised by the conftest fixture's `monkeypatch.setattr`).

- [ ] **Step 4: Implement the helpers and the stamp**

In `swingbot/core/scanning/analyze.py`:

1. Change the datetime import (near line 11) from `from datetime import datetime, timezone` to:

```python
from datetime import date, datetime, timezone
```

2. Beside the existing `from swingbot.core.market import levels, trendlines` import add:

```python
from swingbot.core.market import earnings_calendar
```

3. Directly above `def attach_plan_v2(` add:

```python
def _earnings_source():
    """The live earnings calendar (events.get_earnings_datetimes, 6-hour
    cached). A function rather than a module constant so tests swap it
    without touching the network (tests/scanning/conftest.py)."""
    return earnings_calendar.LiveSource()


def _decision_session_date(df) -> date:
    """ET session date of the decision bar -- the frame's last row. A
    tz-aware index is converted to America/New_York first; a naive daily
    index already is the session date."""
    import pandas as pd
    ts = pd.Timestamp(df.index[-1])
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/New_York")
    return ts.date()


def _days_to_earnings(ticker: str, df) -> int | None:
    """v146 I2: NYSE sessions from the decision bar to the next earnings
    reaction session (earnings_calendar's own unit, the one v82's exposure
    rule uses). None -- never an exception -- on a failed or empty fetch, a
    fund, a bad frame or anything else: a recorded field must never block a
    plan. NO-LOOKAHEAD: live only; the as-of answer IS today's calendar."""
    try:
        return earnings_calendar.sessions_to_reaction(
            ticker, _decision_session_date(df), source=_earnings_source())
    except Exception:
        log.debug("days_to_earnings unavailable for %s", ticker, exc_info=True)
        return None
```

4. In `attach_plan_v2`, inside the `plan.risk_features = risk_features.build(` call, add one keyword argument after `rs_percentile=rs_percentile,`:

```python
                # v146 I2: live wall clock only. A historical replay supplies
                # issued_at, and the live calendar would answer for TODAY,
                # not for its decision date -- that replay records None.
                days_to_earnings=(_days_to_earnings(ticker, df) if issued_at is None else None),
```

In `swingbot/core/scanning/risk_features.py`, replace the two comment lines above `"days_to_earnings": days_to_earnings,` (`# Opportunistic: null unless v82's calendar is merged and wired. This` / `# plan does not depend on v82 and must never block on it.`) with:

```python
        # v146 I2: NYSE sessions from the decision bar to the next earnings
        # reaction session (earnings_calendar.sessions_to_reaction, v82's
        # unit), from the live calendar. None on a historical replay, a
        # failed or empty fetch, or a fund -- it never blocks a plan.
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_days_to_earnings_stamp.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: PASS (its `"days_to_earnings" in rf` assertion still holds; the autouse fixture keeps it off the network).

Run: `python scripts/dev/testrun.py file tests/scanning/test_live_context_stamp.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/scanning/test_risk_features.py`
Expected: PASS (the `build()` key set is unchanged).

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s swingbot/core/scanning/analyze.py | grep -E "attach_plan_v2|_days_to_earnings|_decision_session_date|_earnings_source"`
Expected: `attach_plan_v2` at B (10) (was B 9; the one conditional expression), every new helper at A. Nothing at C or worse among these.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/analyze.py swingbot/core/scanning/risk_features.py tests/scanning/conftest.py tests/scanning/test_days_to_earnings_stamp.py
git commit -m "feat(v146): stamp days_to_earnings on live plans from the earnings calendar (V146-5)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

### Task V146-6: Confluence and RS-quintile analytics dimensions

**Model:** sonnet -- two table-driven extractors, one public helper and one hard-coded frontend list, each pinned by an existing test; the contract (`rs_quintile_label`) is fully specified in the ledger.

**Cross-plan (audit 2026-10-10):** v152 adds a `taken` dimension (after `ledger`) to the same four lists. Every list edit below is an **insertion into the list as it stands in the worktree**, never a replacement from this plan's text: add `"confluence"` and `"rs_quintile"` to the current `DIMENSIONS` tuple, the current dimension-set test, the current `BREAKDOWN_DIMENSIONS` block and the current `analytics.store.spec.ts` `toEqual` list, keeping every entry already there. If v152 merged (`"taken"` is in `DIMENSIONS`), keep `taken` where it is; the dimension count is then 13 instead of 12. The literals quoted below show the no-v152 shape for orientation only.

**Depends on:** nothing. Independent of every other task (disjoint files); it must land before V146-10, which imports `aggregate.rs_quintile_label`.

**Files:**
- Modify: `swingbot/core/analytics/aggregate.py` (imports at lines 6-14; `DIMENSIONS` / `_EXTRACTORS` at lines 107-123)
- Modify: `tests/analytics/test_aggregate.py` (`test_all_ten_dimensions_present` at line 50; new tests appended)
- Modify: `tests/admin/test_api_v1_analytics.py` (`test_by_dimension_accepts_every_dimension_and_nulls_thin_rates` at line 361)
- Modify: `frontend/src/app/stores/analytics.store.ts` (`BREAKDOWN_DIMENSIONS` at lines 273-286)
- Modify: `frontend/src/app/stores/analytics.store.spec.ts` (the pinned array at lines 738-741)

**Interfaces:**
- Consumes: trade records as `TradeLog` stores them -- `target_sources: list[str]` (always written, `performance.py:619`) and `entry_context: dict | None` carrying `rs_pctile` on a 0-100 scale (`swingbot/core/edge/context.py:108-109`).
- Produces: `aggregate.DIMENSIONS` gains `"confluence"` and `"rs_quintile"` (12 total; 13 if v152's `taken` is present); `aggregate.rs_quintile_label(value: float | None) -> str` returning `"Q1"` .. `"Q5"` at 20-point cuts (`[0, 20)` -> `Q1`, `[20, 40)` -> `Q2`, `[40, 60)` -> `Q3`, `[60, 80)` -> `Q4`, `[80, 100]` -> `Q5`; below 0 clamps to `Q1`, above 100 to `Q5`) and `"unknown"` for `None`, NaN or a non-number. V146-10 imports it so the study buckets RS exactly as Analytics does. `GET /api/v1/analytics/by-dimension?dim=confluence|rs_quintile` is served unchanged by the existing endpoint (it validates against `DIMENSIONS`). Frontend `BREAKDOWN_DIMENSIONS` gains `{ value: 'confluence', label: 'Confluence' }` and `{ value: 'rs_quintile', label: 'RS quintile' }`.

- [ ] **Step 1: Write the failing backend tests**

In `tests/analytics/test_aggregate.py`, change the import on line 3 to:

```python
from swingbot.core.analytics.aggregate import DIMENSIONS, StatRow, rs_quintile_label, stats_by
```

Rename the current dimension-set test (today `test_all_ten_dimensions_present`, lines 50-55; v152 may have renamed it) to `test_all_dimensions_present`, add `"confluence"` and `"rs_quintile"` to its expected set **keeping every name already there** (including v152's `"taken"` if present), and extend its docstring with the v146 sentence and the resulting count. Without v152 the result reads:

```python
def test_all_dimensions_present():
    """v32 Task 11: "tier" (A/B/C) retired -- "confidence" already covered
    the same role, so DIMENSIONS dropped from 10 to 9. v93 then added
    "ledger" (main/weak) as its own grouping dimension, back to 10. v146 I4
    added "confluence" (target-source count) and "rs_quintile" (entry RS
    percentile in 20-point bands): 12."""
    assert set(DIMENSIONS) == {"strategy", "horizon", "badge", "confidence",
                               "direction", "dow", "month", "ticker", "source", "ledger",
                               "confluence", "rs_quintile"}
```

With v152's `taken` present the set also holds `"taken"` and the docstring's count is 13 (state v152's sentence before v146's).

Append at the end of the file:

```python
# --- v146 I4: confluence and rs_quintile ---------------------------------

def test_confluence_counts_target_sources():
    two = dict(_full_trade(), target_sources=["EMA20", "Fib 61.8%"])
    assert stats_by([two], "confluence")[0].key == "2"
    assert stats_by([_full_trade()], "confluence")[0].key == "1"


def test_confluence_empty_list_reads_zero_and_missing_reads_unknown():
    empty = dict(_full_trade(), target_sources=[])
    assert stats_by([empty], "confluence")[0].key == "0"
    missing = {k: v for k, v in _full_trade().items() if k != "target_sources"}
    assert stats_by([missing], "confluence")[0].key == "unknown"


def test_rs_quintile_reads_entry_context():
    trade = dict(_full_trade(), entry_context={"rs_pctile": 64.0})
    assert stats_by([trade], "rs_quintile")[0].key == "Q4"


def test_rs_quintile_unknown_without_entry_context():
    assert stats_by([_full_trade()], "rs_quintile")[0].key == "unknown"
    assert stats_by([dict(_full_trade(), entry_context=None)], "rs_quintile")[0].key == "unknown"
    assert stats_by([dict(_full_trade(), entry_context={})], "rs_quintile")[0].key == "unknown"
    assert stats_by([dict(_full_trade(), entry_context="garbage")], "rs_quintile")[0].key == "unknown"


@pytest.mark.parametrize("value, label", [
    (0.0, "Q1"), (19.999, "Q1"), (20.0, "Q2"), (39.9, "Q2"), (40.0, "Q3"),
    (59.9, "Q3"), (60.0, "Q4"), (79.9, "Q4"), (80.0, "Q5"), (100.0, "Q5"),
    (-3.0, "Q1"), (104.0, "Q5"),
    (None, "unknown"), (float("nan"), "unknown"), ("n/a", "unknown"),
])
def test_rs_quintile_label_edges(value, label):
    assert rs_quintile_label(value) == label
```

(`pytest` is already imported in this file -- `test_stats_by_raises_on_unknown_dimension` uses it. If the import is missing, add `import pytest` at the top.)

In `tests/admin/test_api_v1_analytics.py`, in `test_by_dimension_accepts_every_dimension_and_nulls_thin_rates`, append `"confluence", "rs_quintile"` to the loop's tuple as it stands, keeping every entry already there. Today's header

```python
    for dim in ("strategy", "horizon", "badge", "confidence", "direction", "dow", "month", "ticker", "source"):
```

with

```python
    for dim in ("strategy", "horizon", "badge", "confidence", "direction", "dow", "month", "ticker", "source",
                "confluence", "rs_quintile"):
```

- [ ] **Step 2: Run the backend tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`
Expected: FAIL / ERROR -- `ImportError: cannot import name 'rs_quintile_label'`.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: FAIL -- `test_by_dimension_accepts_every_dimension_and_nulls_thin_rates` gets a 400 for `dim=confluence` (`body["min_cell_n"]` raises `KeyError`).

- [ ] **Step 3: Implement the extractors**

In `swingbot/core/analytics/aggregate.py`, add `import math` to the imports (after `import datetime as dt`):

```python
import datetime as dt
import math
from collections import defaultdict
```

Add these helpers directly above the `# v32 Task 11: "tier" ...` comment that precedes `DIMENSIONS`:

```python
#: RS percentile band width for the rs_quintile dimension (v146 I4).
_RS_BAND = 20.0


def rs_quintile_label(value) -> str:
    """'Q1'..'Q5' for an entry RS percentile (0-100) at 20-point cuts --
    [0,20) Q1 ... [80,100] Q5, out-of-range values clamped -- or 'unknown'
    when there is no usable reading. Public: the v146 expectancy study
    buckets RS with this exact function so both views agree."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if math.isnan(number):
        return "unknown"
    band = min(4, max(0, int(number // _RS_BAND)))
    return f"Q{band + 1}"


def _confluence_key(t: dict) -> str:
    """How many target sources confirmed the trade (len(target_sources));
    an empty list is '0', a record without the field 'unknown'."""
    sources = t.get("target_sources")
    return "unknown" if sources is None else str(len(sources))


def _rs_quintile_key(t: dict) -> str:
    context = t.get("entry_context")
    return rs_quintile_label(context.get("rs_pctile") if isinstance(context, dict) else None)
```

Append `"confluence", "rs_quintile"` to the current `DIMENSIONS` tuple, keeping every entry already there (v152's `"taken"` after `"ledger"` included). Without v152 the tuple reads:

```python
DIMENSIONS = ("strategy", "horizon", "badge", "confidence",
             "direction", "dow", "month", "ticker", "source", "ledger",
             "confluence", "rs_quintile")
```

and add two entries at the end of `_EXTRACTORS` as it stands (today after `"month": _month_key,`):

```python
    "confluence": _confluence_key,
    "rs_quintile": _rs_quintile_key,
```

`rs_quintile_label(None)` takes the `TypeError` branch (`float(None)`), so `None` needs no special case.

- [ ] **Step 4: Run the backend tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_aggregate.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Write the failing frontend test**

In `frontend/src/app/stores/analytics.store.spec.ts`, insert `'confluence', 'rs_quintile'` right after `'confidence'` in the current pinned `toEqual` array (lines 738-741 today), keeping every entry already there (v152's `'taken'` included), and add the two label assertions after it. Today's array:

```typescript
      expect(BREAKDOWN_DIMENSIONS.map((dimension) => dimension.value)).toEqual([
        'strategy', 'horizon', 'direction', 'dow', 'month', 'badge',
        'confidence', 'source', 'ledger', 'ticker',
      ]);
```

becomes (no-v152 shape):

```typescript
      expect(BREAKDOWN_DIMENSIONS.map((dimension) => dimension.value)).toEqual([
        'strategy', 'horizon', 'direction', 'dow', 'month', 'badge',
        'confidence', 'confluence', 'rs_quintile', 'source', 'ledger', 'ticker',
      ]);
      expect(BREAKDOWN_DIMENSIONS.find((d) => d.value === 'confluence')?.label).toBe('Confluence');
      expect(BREAKDOWN_DIMENSIONS.find((d) => d.value === 'rs_quintile')?.label).toBe('RS quintile');
```

Run: `npm --prefix frontend test -- --include src/app/stores/analytics.store.spec.ts --watch=false`
Expected: FAIL -- the `toEqual` diff shows `confluence` and `rs_quintile` missing.

- [ ] **Step 6: Add the two dropdown entries**

In `frontend/src/app/stores/analytics.store.ts`, insert `{ value: 'confluence', label: 'Confluence' }` and `{ value: 'rs_quintile', label: 'RS quintile' }` after `{ value: 'confidence', … }` in `BREAKDOWN_DIMENSIONS` (lines 273-286 today), keeping every entry already there (v152's `taken` included), and add v146's clause to the doc comment. Without v152 the block reads:

```typescript
/** Every dimension `aggregate.DIMENSIONS` serves, including v93's ledger and
 *  v146's confluence (target-source count) and RS quintile. `tier` stays
 *  retired -- it would 400. */
export const BREAKDOWN_DIMENSIONS = [
  { value: 'strategy', label: 'Strategy' },
  { value: 'horizon', label: 'Horizon' },
  { value: 'direction', label: 'Direction' },
  { value: 'dow', label: 'Day of week' },
  { value: 'month', label: 'Month' },
  { value: 'badge', label: 'Badge' },
  { value: 'confidence', label: 'Confidence' },
  { value: 'confluence', label: 'Confluence' },
  { value: 'rs_quintile', label: 'RS quintile' },
  { value: 'source', label: 'Source' },
  { value: 'ledger', label: 'Ledger' },
  { value: 'ticker', label: 'Ticker' },
] as const;
```

`BreakdownDimension` derives from this list, and the Attribution tab (`frontend/src/app/workspaces/analytics/tabs/attribution.ts:161`) maps it, so no other file changes.

- [ ] **Step 7: Run the frontend test to see it pass**

Run: `npm --prefix frontend test -- --include src/app/stores/analytics.store.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s -n B swingbot/core/analytics/aggregate.py`
Expected: no output for `rs_quintile_label`, `_confluence_key` or `_rs_quintile_key` (all A).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/analytics/aggregate.py tests/analytics/test_aggregate.py tests/admin/test_api_v1_analytics.py frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts
git commit -m "feat(v146): confluence and RS-quintile analytics breakdown dimensions (V146-6)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

# Phase 3 -- I3: TRAIN per-trade rows for the confluence replay

### Task V146-7: Replay hits and the TRAIN per-trade row

**Model:** opus -- a behaviour-preserving split of a C15 replay loop that twenty callers depend on, a scorer switch that must leave every live call byte-identical, and a no-lookahead contract on every new field.

**Cross-plan (audit 2026-10-10):** v135 (V135-5/8), v147 (V147-5) and v133 (V133-6) carry conditional instructions targeting the helpers this task creates -- keep the names `_replay_params`, `_bar_scenarios`, `_accept_scenario`, `replay_scenarios_detailed` and the field `ReplayHit.target_confluence` exactly as written below. Before replacing `replay_scenarios`' body, read it as it stands in the worktree and carry every gate another plan has added:
- If v135 merged (`_headroom_kept` exists in `backtest_scenarios.py`), `_bar_scenarios` keeps calling the headroom gate: its return ends `_headroom_kept(_dryup_kept(scenarios, window), supports, resistances)` (match the argument order of the merged `_headroom_kept`).
- If v147 merged (`replay_scenarios` has a `blocked=` parameter), add `blocked: list | None = None` to both `replay_scenarios` and `replay_scenarios_detailed`, pass it through, and thread it into `_accept_scenario(..., blocked)`, keeping v147's `_note_blocked(blocked, i, sc)` call in `_accept_scenario`'s `if plan is None:` branch.
- `tests/scripts/test_fvg_attribution.py::test_replay_still_has_the_shape_the_recorder_patches` is updated in Step 5 below; if v135 already updated it to the whole-module shape, keep v135's version.
- Complexity gate (GENERIC, owner v149): this task splits the legacy C15 `replay_scenarios`. If `scripts/dev/complexity_gate.py` exists (v149 merged), Step 8 also runs `python scripts/dev/complexity_gate.py` (expect `improved`/`gone` for `replay_scenarios`, never `new`/`risen`), then `python scripts/dev/complexity_gate.py --update`, and Step 9 adds `scripts/dev/complexity_baseline.json` to the commit.

**Depends on:** V146-2 (shared file `swingbot/core/scanning/confidence.py`; this task reads `ConfidenceResult.points` / `.unevaluated`, which V146-1 adds and V146-2 fills on the legacy path). Read the `no-lookahead` skill before starting.

**Files:**
- Modify: `swingbot/core/scanning/confidence.py` (`ConfidenceResult` near line 232; the legacy scorer's Step 4 `_expectancy_adjustment(scenario.risk_reward_ratio, track_record)` call, near line 565 before V146-2; `score_confidence` near line 593)
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (imports lines 6-24; `replay_scenarios` lines 81-165)
- Modify: `tests/scripts/test_fvg_attribution.py` (`test_replay_still_has_the_shape_the_recorder_patches` at line 109)
- Create: `swingbot/core/backtesting/scenario_rows.py`
- Create: `tests/backtesting/test_scenario_rows.py`

**Interfaces:**
- Consumes: `ConfidenceResult.points: dict[str, int]`, `ConfidenceResult.unevaluated: list[str]` (V146-1, filled by V146-2); `levels.count_confirming_strategies(df, h, current_price, target_price, tolerance_pct, candidates=None) -> (count, families)` (`swingbot/core/market/levels.py:498`); `regime.get_market_regime(df, ticker=None) -> RegimeResult` (raises `ValueError` under 220 bars; `swingbot/core/scanning/regime.py:88`); `ExitResult` (`outcome, runner_outcome, entry_index, exit_index, entry_price, r_total, legs`; `swingbot/core/planning/exit_sim.py:61`).
- Produces (ledger contracts V146-8 and V146-12 consume):
  - `score_confidence(scenario, regime_trend=None, df=None, target_confluence=None, stop_confluence=None, track_record=None, neutral_expectancy: bool = False, **kwargs) -> ConfidenceResult`; `confidence.NEUTRAL_EXPECTANCY_DETAIL: str`. Default `False` keeps every live call byte for byte.
  - `backtest_scenarios.ReplayHit(NamedTuple)`: `i: int, plan, scenario, target_confluence: tuple` (first two fields are the legacy pair, so `hit[0]`, `hit[1]` work on both shapes).
  - `backtest_scenarios.replay_scenarios_detailed(ticker, df, horizon_key, *, params=None, gates=None, dcb_params=None, asof=None) -> list[ReplayHit]`; `replay_scenarios` keeps its `list[(i, plan)]` return as a projection.
  - `backtest_scenarios.REPLAY_CONFLUENCE_TOLERANCE_PCT = 5.0`.
  - `scenario_rows.TRAIN_NEUTRAL_EXPECTANCY = True`; `scenario_rows.ROW_KEYS: tuple[str, ...]`; `scenario_rows.signal_fields(horizon_key: str, df, hit: ReplayHit, spy_df) -> dict`; `scenario_rows.scenario_trade_row(ticker: str, horizon_key: str, df, hit: ReplayHit, result: ExitResult, spy_df) -> dict` with keys, in order, `ticker, horizon_key, signal_date, direction, entry, stop_loss, take_profit, risk_reward_ratio, outcome, runner_outcome, r_total, entry_price, legs, entry_context, confluence_count, confidence_score, confidence_level, confidence_points, confidence_unevaluated`. `entry` / `stop_loss` / `take_profit` are the plan's `trigger_price` / `stop_loss` / `tp1`; `entry_price` is the simulated fill; `risk_reward_ratio` is the plan's planned `|tp1 - trigger| / |trigger - stop|` rounded to 2 (None at zero risk); `legs` is `ExitResult.legs` (`[{fraction, exit_price, r, reason}]`), gross of frictions.

- [ ] **Step 1: Record the replay baseline before touching it**

The split of `replay_scenarios` must not change one plan. Capture today's output first (`data/` is gitignored):

```bash
python - <<'PY'
import json
import numpy as np
from swingbot.core.backtesting import backtest_scenarios as bs
from tests.helpers import make_ohlcv

rng = np.random.RandomState(7)
trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
df = make_ohlcv(trend + box)
GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5, "max_stop_distance_pct": 15.0,
         "min_risk_reward": 0.0, "min_confluence": 1, "cooldown_bars": 5}
out = {}
for label, kwargs in (("gates", {"gates": GATES}), ("params", {}), ("dcb", {"gates": GATES, "dcb_params": {}})):
    for hk in ("4w", "2m"):
        try:
            hits = bs.replay_scenarios("AAPL", df, hk, **kwargs)
        except Exception as exc:          # an arm the fixture cannot run is recorded, not fatal
            out[f"{label}/{hk}"] = f"error: {type(exc).__name__}"
            continue
        out[f"{label}/{hk}"] = [[i, p.direction, p.trigger_price, p.stop_loss, p.tp1, p.tp2,
                                 repr(sorted((p.entry_context or {}).items(), key=str))] for i, p in hits]
open("data/v146-replay-baseline.json", "w", encoding="utf-8").write(json.dumps(out, default=str, sort_keys=True))
print({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()})
PY
```

Expected: a dict of counts printed, with at least `gates/4w` non-zero. Keep the file for Step 7.

- [ ] **Step 2: Write the failing tests**

Create `tests/backtesting/test_scenario_rows.py`:

```python
"""v146 I3: the confluence replay's detailed hits, the TRAIN-only
neutral-expectancy switch, and the per-trade TRAIN row with a confidence
score computed exactly as the live scan computes it -- on the as-of window."""
import copy
import json

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting import scenario_rows
from swingbot.core.market import levels
from swingbot.core.market.levels import Scenario
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import confidence
from swingbot.core.scanning.confidence import score_confidence
from swingbot.core.scanning.regime import get_market_regime
from tests.helpers import make_ohlcv

# The replay is the slow part (same tier as test_backtest_scenarios.py).
pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box -- the fixture family of
    tests/backtesting/test_backtest_scenarios.py, copied so the files stay
    independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.fixture(autouse=True)
def _legacy_scorer(monkeypatch):
    # Production runs the legacy scorer (UNIFIED_CONFIDENCE defaults false).
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)


@pytest.fixture(scope="module")
def df():
    return _structured_df()


@pytest.fixture(scope="module")
def spy():
    # Starts a year before the stock frame, so every signal bar has 220+
    # SPY bars behind it and get_market_regime returns a trend.
    return make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")


@pytest.fixture(scope="module")
def hits(df):
    out = bs.replay_scenarios_detailed("AAPL", df, "4w", gates=GATES)
    assert out, "fixture must produce at least one hit"
    return out


def _fingerprint(i, plan):
    return (i, plan.direction, plan.trigger_price, plan.stop_loss, plan.tp1, plan.tp2)


# --- replay_scenarios_detailed ----------------------------------------------

def test_replay_scenarios_is_the_projection_of_the_detailed_hits(df, hits):
    legacy = bs.replay_scenarios("AAPL", df, "4w", gates=GATES)
    assert [_fingerprint(i, p) for i, p in legacy] == [_fingerprint(h.i, h.plan) for h in hits]


def test_a_hit_reads_like_the_legacy_pair_and_carries_its_scenario(df, hits):
    for hit in hits:
        assert (hit[0], hit[1]) == (hit.i, hit.plan)
        assert hit.scenario.direction == hit.plan.direction
        window = df.iloc[:hit.i + 1]
        price = float(window["Close"].iloc[-1])
        assert hit.target_confluence == levels.count_confirming_strategies(
            window, HORIZONS["4w"], price, hit.scenario.take_profit,
            tolerance_pct=bs.REPLAY_CONFLUENCE_TOLERANCE_PCT)
        assert hit.target_confluence[0] >= GATES["min_confluence"]


# --- neutral_expectancy -------------------------------------------------------

def _scenario():
    return Scenario(direction="bullish", entry=100.0, market_price=100.0, stop_loss=98.0,
                    stop_sources=["EMA", "VWAP"], stop_distance_pct=2.0, tight_stop=False,
                    atr_floor_pct=1.5, take_profit=110.0, target_distance_pct=10.0,
                    target_sources=["EMA", "VWAP"], target2_price=None,
                    target2_distance_pct=None, target2_sources=None)


def test_neutral_expectancy_never_runs_the_track_record_step(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("_expectancy_adjustment must not run when neutralised")
    monkeypatch.setattr(confidence, "_expectancy_adjustment", boom)
    result = score_confidence(_scenario(), target_confluence=(2, ["EMA", "VWAP"]),
                              neutral_expectancy=True)
    assert result.breakdown["Track record (expectancy)"] == confidence.NEUTRAL_EXPECTANCY_DETAIL


def test_the_default_keeps_the_live_expectancy_step(monkeypatch):
    monkeypatch.setattr(confidence, "_expectancy_adjustment", lambda rr, record: (1, "forced +1"))
    live = score_confidence(_scenario(), target_confluence=(2, ["EMA", "VWAP"]))
    neutral = score_confidence(_scenario(), target_confluence=(2, ["EMA", "VWAP"]),
                               neutral_expectancy=True)
    assert live.breakdown["Track record (expectancy)"] == "forced +1"
    # base Level 2, quality nudges -1..+1, so neither side clamps at 1 or 5
    assert live.level == neutral.level + 1


# --- signal_fields / scenario_trade_row --------------------------------------

def _late_hit(df, hits):
    return next(h for h in hits if h.i < len(df) - 5)


def test_the_score_is_the_live_scorer_on_the_as_of_window(df, hits, spy):
    hit = _late_hit(df, hits)
    window = df.iloc[:hit.i + 1]
    price = float(window["Close"].iloc[-1])
    stop_confluence = levels.count_confirming_strategies(
        window, HORIZONS["4w"], price, hit.scenario.stop_loss,
        tolerance_pct=bs.REPLAY_CONFLUENCE_TOLERANCE_PCT)
    trend = get_market_regime(spy[spy.index <= window.index[-1]]).trend
    expected = score_confidence(copy.deepcopy(hit.scenario), regime_trend=trend, df=window,
                                target_confluence=hit.target_confluence,
                                stop_confluence=stop_confluence, track_record=None,
                                neutral_expectancy=True)
    fields = scenario_rows.signal_fields("4w", df, hit, spy)
    assert scenario_rows.TRAIN_NEUTRAL_EXPECTANCY is True
    assert fields["confidence_score"] == expected.score
    assert fields["confidence_level"] == expected.level
    assert fields["confidence_points"] == expected.points
    assert fields["confidence_unevaluated"] == expected.unevaluated
    assert fields["confidence_points"], "the legacy scorer stamps points (V146-2)"


def test_signal_fields_ignore_every_bar_after_the_signal(df, hits, spy):
    hit = _late_hit(df, hits)
    signal_ts = df.index[hit.i]
    full = scenario_rows.signal_fields("4w", df, hit, spy)
    truncated = scenario_rows.signal_fields("4w", df.iloc[:hit.i + 1], hit, spy[spy.index <= signal_ts])
    assert truncated == full
    spiked, spy_spiked = df.copy(), spy.copy()
    prices = ["Open", "High", "Low", "Close"]
    spiked.loc[spiked.index > signal_ts, prices] *= 3.0
    spy_spiked.loc[spy_spiked.index > signal_ts, prices] *= 0.2
    assert scenario_rows.signal_fields("4w", spiked, hit, spy_spiked) == full


def test_no_spy_or_short_spy_scores_without_a_regime(df, hits, spy):
    hit = _late_hit(df, hits)
    window = df.iloc[:hit.i + 1]
    price = float(window["Close"].iloc[-1])
    stop_confluence = levels.count_confirming_strategies(
        window, HORIZONS["4w"], price, hit.scenario.stop_loss,
        tolerance_pct=bs.REPLAY_CONFLUENCE_TOLERANCE_PCT)
    expected = score_confidence(copy.deepcopy(hit.scenario), regime_trend=None, df=window,
                                target_confluence=hit.target_confluence,
                                stop_confluence=stop_confluence, track_record=None,
                                neutral_expectancy=True)
    for spy_df in (None, spy.iloc[:100]):
        fields = scenario_rows.signal_fields("4w", df, hit, spy_df)
        assert (fields["confidence_score"], fields["confidence_level"]) == (expected.score, expected.level)


def test_scoring_never_mutates_the_replayed_scenario(df, hits, spy):
    hit = _late_hit(df, hits)
    before = (list(hit.scenario.target_sources), list(hit.scenario.stop_sources))
    scenario_rows.signal_fields("4w", df, hit, spy)
    assert (list(hit.scenario.target_sources), list(hit.scenario.stop_sources)) == before


def test_the_row_carries_every_documented_key(df, hits, spy):
    hit = _late_hit(df, hits)
    result = bs.simulate_exit(df, hit.i, hit.plan, scale_out=True)
    row = scenario_rows.scenario_trade_row("AAPL", "4w", df, hit, result, spy)
    assert tuple(row) == scenario_rows.ROW_KEYS
    assert row["ticker"] == "AAPL" and row["horizon_key"] == "4w"
    assert row["signal_date"] == str(df.index[hit.i].date())
    assert row["direction"] == hit.plan.direction
    assert (row["entry"], row["stop_loss"], row["take_profit"]) == (
        hit.plan.trigger_price, hit.plan.stop_loss, hit.plan.tp1)
    risk = abs(hit.plan.trigger_price - hit.plan.stop_loss)
    assert row["risk_reward_ratio"] == round(abs(hit.plan.tp1 - hit.plan.trigger_price) / risk, 2)
    assert (row["outcome"], row["runner_outcome"], row["r_total"]) == (
        result.outcome, result.runner_outcome, result.r_total)
    assert row["legs"] == result.legs
    assert row["entry_context"] == (hit.plan.entry_context or {})
    assert row["confluence_count"] == hit.target_confluence[0]
    json.loads(json.dumps(row, default=str))      # JSON-able with the writer's fallback
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_rows.py`
Expected: ERROR at collection -- `ImportError: cannot import name 'scenario_rows' from 'swingbot.core.backtesting'`.

- [ ] **Step 4: Add the TRAIN-only switch to the scorer**

In `swingbot/core/scanning/confidence.py`, directly below `_expectancy_adjustment` (ends near line 276) add:

```python
#: Step 4's breakdown line when the expectancy step is neutralised (v146).
NEUTRAL_EXPECTANCY_DETAIL = "neutralised for the TRAIN replay (no live track record) -> 0 levels"


def _expectancy_step(risk_reward_ratio: float, track_record: tuple, neutral: bool) -> tuple:
    """Step 4 of the legacy scorer. `neutral` (v146, the TRAIN replay only)
    skips _expectancy_adjustment: at track_record=None that step is NOT
    neutral -- it assumes a 50% win rate and moves the level +-1 by
    reward:risk. Every live caller leaves it False."""
    if neutral:
        return 0, NEUTRAL_EXPECTANCY_DETAIL
    return _expectancy_adjustment(risk_reward_ratio, track_record)
```

Find the Step 4 call (V146-2 may have moved it into a helper):

Run: `git grep -n "_expectancy_adjustment(scenario.risk_reward_ratio" swingbot/core/scanning/confidence.py`

Replace that one call with `_expectancy_step(scenario.risk_reward_ratio, track_record, neutral_expectancy)`, so the line reads:

```python
    expectancy_adjustment, expectancy_detail = _expectancy_step(
        scenario.risk_reward_ratio, track_record, neutral_expectancy)
```

and thread a `neutral_expectancy: bool = False` keyword parameter from `_score_confidence_legacy`'s signature (after `track_record: tuple = None`) down to that line (through any helper V146-2 extracted, as a keyword argument with the same default).

Then change `score_confidence`'s signature and its legacy dispatch:

```python
def score_confidence(scenario, regime_trend: str = None, df=None,
                     target_confluence: tuple = None, stop_confluence: tuple = None,
                     track_record: tuple = None, neutral_expectancy: bool = False,
                     **kwargs) -> ConfidenceResult:
```

append one sentence to its docstring:

```python
    `neutral_expectancy` (v146) zeroes the legacy scorer's track-record
    step for the TRAIN replay, which has no live track record; the
    unified path has no such step and ignores it. Live callers never pass it.
```

and pass it in the legacy branch:

```python
        return _score_confidence_legacy(
            scenario, regime_trend=regime_trend, df=df,
            target_confluence=target_confluence,
            stop_confluence=stop_confluence, track_record=track_record,
            neutral_expectancy=neutral_expectancy)
```

- [ ] **Step 5: Split the replay loop and add `ReplayHit`**

In `swingbot/core/backtesting/backtest_scenarios.py`, add `from typing import NamedTuple` after `from concurrent.futures import ProcessPoolExecutor`. Below `CONFLUENCE_GATES` (after line 60) add:

```python
#: Tolerance the replay counts confirming strategies with (the live default,
#: CONFLUENCE_DEVIATION_PCT, is also 5.0). Named in v146 so the TRAIN
#: score's stop confluence (scenario_rows) uses the same one.
REPLAY_CONFLUENCE_TOLERANCE_PCT = 5.0
_REPLAY_COOLDOWN_BARS = 5


class ReplayHit(NamedTuple):
    """One accepted replay signal. The first two fields are the legacy
    (signal_index, plan) pair, so hit[0] / hit[1] read like the old tuples;
    scenario and target_confluence are what v146's TRAIN row needs."""
    i: int
    plan: object
    scenario: object
    target_confluence: tuple


@dataclasses.dataclass
class _ReplayScope:
    """Per-call constants of one replay, so the helpers stay small."""
    ticker: str
    horizon_key: str
    h: dict
    params: ScanParams
    legacy_gates: bool
    asof: object
```

Replace the whole of `replay_scenarios` (lines 81-165) with:

```python
def _replay_params(params: ScanParams | None, gates: dict | None) -> tuple:
    """(params, legacy_gates): a legacy gates dict overrides the admission
    fields of ScanParams, exactly as before the v146 split."""
    if params is None:
        params = ScanParams.from_config()
    if gates is None:
        return params, False
    return dataclasses.replace(
        params,
        min_reward_pct=gates.get("min_reward_pct", params.min_reward_pct),
        min_stop_distance_pct=gates.get("min_stop_distance_pct", params.min_stop_distance_pct),
        max_stop_loss_pct=gates.get("max_stop_distance_pct", params.max_stop_loss_pct),
        min_risk_reward_ratio=gates.get("min_risk_reward", params.min_risk_reward_ratio),
        min_target_confluence_count=gates.get("min_confluence", params.min_target_confluence_count),
    ), True


def _bar_scenarios(scope: _ReplayScope, df, i: int, cache: dict, dcb_params: dict | None) -> tuple:
    """(window, price, level_map, scenarios) for bar i -- every computation
    on window = df.iloc[:i+1] (levels_asof enforces the same slice)."""
    window = df.iloc[:i + 1]
    price = float(window["Close"].iloc[-1])
    supports, resistances = levels_asof(scope.ticker, df, i, scope.horizon_key, cache)
    # drop levels the later bars created is already impossible (as-of map);
    # but the map's supports/resistances were split against ITS OWN price --
    # re-split against this bar's price when the cache bucket lags:
    all_levels = sorted(supports + resistances, key=lambda lv: lv.price)
    supports = [lv for lv in all_levels if lv.price < price][::-1]
    resistances = [lv for lv in all_levels if lv.price > price]

    floor_pct = levels.atr_floor_pct(window, price, scope.h)
    gates = scenario_gate_inputs(scope.params, scope.h)
    # v68. `window` is the harness's no-lookahead slice -- the same frame
    # the live scan hands to veto_bullish_for. dcb_params=None is the
    # baseline arm and must not pay for the detector at all.
    block_bullish = False
    if dcb_params is not None:
        block_bullish = bool(dead_cat_bounce(window, dcb_params)["detected"])
    scenarios = levels.build_scenarios(
        price, supports, resistances, gates["min_reward_pct"],
        atr_floor=floor_pct,
        min_stop_distance_pct=gates["min_stop_distance_pct"],
        max_stop_distance_pct=gates["max_stop_distance_pct"],
        min_risk_reward=gates["min_risk_reward"],
        block_bullish=block_bullish)
    return window, price, (supports, resistances), _dryup_kept(scenarios, window)


def _accept_scenario(scope: _ReplayScope, i: int, window, price: float, level_map: tuple,
                     sc, last_accepted: dict) -> ReplayHit | None:
    """The confluence gate, the per-direction cooldown and the plan build
    for one scenario; None when any of them says no."""
    n_confl, families = levels.count_confirming_strategies(
        window, scope.h, price, sc.take_profit, tolerance_pct=REPLAY_CONFLUENCE_TOLERANCE_PCT)
    if not passes_confluence(n_confl, scope.params):
        return None
    last = last_accepted.get(sc.direction)
    if last is not None and i - last < _REPLAY_COOLDOWN_BARS:
        return None
    plan = build_confluence_plan(
        sc, window, ticker=scope.ticker, horizon_key=scope.horizon_key,
        primary_strategy=primary_strategy_for(sc),
        level_map=level_map,
        # Legacy callers historically used their dict only for
        # scenario admission; target construction still read config.
        # Keep that compatibility while callers migrate to params.
        params=ScanParams.from_config() if scope.legacy_gates else scope.params)
    if plan is None:
        return None          # no qualifying target -> no trade, same as live
    stamp_entry_context(plan, window, asof_row(scope.asof, window.index[-1]))
    return ReplayHit(i, plan, sc, (n_confl, families))


def replay_scenarios_detailed(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                              gates: dict | None = None, dcb_params: dict | None = None,
                              asof=None) -> list[ReplayHit]:
    """A ReplayHit for every bar where the confluence scan WOULD have emitted
    a plan, under `gates`, with a per-direction cooldown.

    No lookahead: every computation is scoped to `window = df.iloc[:i+1]`
    (or `levels_asof`, which enforces the same slice internally) -- never
    `df.iloc[-1]` or any index beyond `i`.

    `dcb_params`: v68's dead-cat-bounce veto params. Taken directly rather
    than read from config -- the TRAIN grid runs twelve different parameter
    sets in one process, and a config read would make them a global the
    workers fight over. `None` is the baseline arm and must not pay for the
    detector at all.
    """
    params, legacy_gates = _replay_params(params, gates)
    scope = _ReplayScope(ticker, horizon_key, HORIZONS[horizon_key], params, legacy_gates, asof)
    cache: dict = {}
    out: list[ReplayHit] = []
    last_accepted: dict = {}   # direction -> bar index
    for i in range(MIN_BARS[horizon_key], len(df)):
        window, price, level_map, scenarios = _bar_scenarios(scope, df, i, cache, dcb_params)
        for sc in scenarios:
            hit = _accept_scenario(scope, i, window, price, level_map, sc, last_accepted)
            if hit is not None:
                last_accepted[sc.direction] = i
                out.append(hit)
    return out


def replay_scenarios(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                     gates: dict | None = None,
                     dcb_params: dict | None = None, asof=None) -> list:
    """(signal_index, TradePlanV2) for every bar where the confluence scan
    WOULD have emitted a plan -- the projection of replay_scenarios_detailed
    that every pre-v146 caller unpacks. Same arguments, same no-lookahead
    contract."""
    return [(hit.i, hit.plan) for hit in replay_scenarios_detailed(
        ticker, df, horizon_key, params=params, gates=gates, dcb_params=dcb_params, asof=asof)]
```

The split moves `levels_asof(...)`, `build_confluence_plan(...)` and the `5.0` tolerance out of `replay_scenarios`' own source, so `tests/scripts/test_fvg_attribution.py::test_replay_still_has_the_shape_the_recorder_patches` (line 109, which reads `inspect.getsource(bs.replay_scenarios)`) would fail. Replace its body to read the whole module (unless v135 already made this change -- then keep v135's version):

```python
def test_replay_still_has_the_shape_the_recorder_patches():
    src = inspect.getsource(bs)
    assert "levels_asof(" in src
    assert "build_confluence_plan(" in src
    assert getattr(bs, "REPLAY_CONFLUENCE_TOLERANCE_PCT", 5.0) == 5.0 == fa.VOTE_TOLERANCE_PCT
```

- [ ] **Step 6: Create the TRAIN row module**

Create `swingbot/core/backtesting/scenario_rows.py`:

```python
"""v146 I3: one TRAIN per-trade row for a confluence-replay hit, carrying a
confidence score computed exactly as the live scan computes it
(analyze.py: score_confidence with the SPY regime trend, target and stop
confluence, on the decision frame).

NO-LOOKAHEAD: every as-of field (signal_fields) is computed on
window = df.iloc[:i+1] and on SPY sliced to the signal bar's timestamp.
Only the exit fields -- outcome, runner_outcome, r_total, entry_price,
legs -- come from the ExitResult, which walked the later bars by design.

Production runs the legacy scorer (UNIFIED_CONFIDENCE defaults false), so
the unified-only inputs (htf_bias, rs_percentile, breadth, macro_verdict)
are not supplied here.
"""
from __future__ import annotations

import dataclasses

from swingbot.core.backtesting.backtest_scenarios import REPLAY_CONFLUENCE_TOLERANCE_PCT
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning.confidence import score_confidence
from swingbot.core.scanning.regime import get_market_regime

#: Frozen before the v146 TRAIN run (spec I3). A replayed trade has no live
#: track record, and the legacy scorer's expectancy step at
#: track_record=None is NOT neutral (assumed 50% win rate, +-1 level by
#: reward:risk), so the TRAIN score neutralises it. Never flip after the run.
TRAIN_NEUTRAL_EXPECTANCY = True

#: The row's keys, in order (the ledger contract V146-12 reads).
ROW_KEYS = ("ticker", "horizon_key", "signal_date", "direction", "entry", "stop_loss",
            "take_profit", "risk_reward_ratio", "outcome", "runner_outcome", "r_total",
            "entry_price", "legs", "entry_context", "confluence_count", "confidence_score",
            "confidence_level", "confidence_points", "confidence_unevaluated")


def _regime_trend(spy_df, signal_ts) -> str | None:
    """Live passes get_market_regime(SPY).trend; None when SPY is absent or
    too short (< 220 bars) -- the live scan's 'regime unavailable'."""
    if spy_df is None:
        return None
    try:
        return get_market_regime(spy_df[spy_df.index <= signal_ts]).trend
    except ValueError:
        return None


def _scoring_copy(scenario):
    """The legacy scorer appends to target_sources (squeeze / candlestick
    lines); scoring a copy leaves the replay's scenario and plan untouched."""
    return dataclasses.replace(
        scenario,
        target_sources=list(scenario.target_sources),
        stop_sources=list(scenario.stop_sources),
        target2_sources=(list(scenario.target2_sources)
                         if scenario.target2_sources is not None else None),
        constraints=dict(scenario.constraints))


def signal_fields(horizon_key: str, df, hit, spy_df) -> dict:
    """The as-of half of the row: signal date, confluence count and the
    confidence score, from df.iloc[:hit.i+1] and SPY up to that bar only."""
    window = df.iloc[:hit.i + 1]
    price = float(window["Close"].iloc[-1])
    scenario = hit.scenario
    stop_confluence = levels.count_confirming_strategies(
        window, HORIZONS[horizon_key], price, scenario.stop_loss,
        tolerance_pct=REPLAY_CONFLUENCE_TOLERANCE_PCT)
    conf = score_confidence(
        _scoring_copy(scenario), regime_trend=_regime_trend(spy_df, window.index[-1]), df=window,
        target_confluence=hit.target_confluence, stop_confluence=stop_confluence,
        track_record=None, neutral_expectancy=TRAIN_NEUTRAL_EXPECTANCY)
    return {
        "signal_date": str(window.index[-1].date()),
        "confluence_count": int(hit.target_confluence[0]),
        "confidence_score": int(conf.score),
        "confidence_level": int(conf.level),
        "confidence_points": dict(conf.points),
        "confidence_unevaluated": list(conf.unevaluated),
    }


def _planned_rr(plan) -> float | None:
    risk = abs(plan.trigger_price - plan.stop_loss)
    return round(abs(plan.tp1 - plan.trigger_price) / risk, 2) if risk else None


def scenario_trade_row(ticker: str, horizon_key: str, df, hit, result, spy_df) -> dict:
    """One self-contained TRAIN row (keys: ROW_KEYS). R is gross: the
    replay's exit_sim applies no frictions; the v146 study nets them."""
    plan = hit.plan
    row = {
        "ticker": ticker,
        "horizon_key": horizon_key,
        "signal_date": None,                       # set by signal_fields below
        "direction": plan.direction,
        "entry": float(plan.trigger_price),
        "stop_loss": float(plan.stop_loss),
        "take_profit": float(plan.tp1),
        "risk_reward_ratio": _planned_rr(plan),
        "outcome": result.outcome,
        "runner_outcome": result.runner_outcome,
        "r_total": float(result.r_total),
        "entry_price": None if result.entry_price is None else float(result.entry_price),
        "legs": [dict(leg) for leg in (result.legs or [])],
        "entry_context": dict(getattr(plan, "entry_context", None) or {}),
    }
    row.update(signal_fields(horizon_key, df, hit, spy_df))
    return row
```

`row.update` keeps `signal_date` in its original (third) position, so `tuple(row) == ROW_KEYS`.

- [ ] **Step 7: Run the tests and the replay baseline**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_rows.py`
Expected: PASS, `0 failed`.

Re-run the Step 1 script with the output path changed to `data/v146-replay-after.json`, then:

```bash
python -c "import json; a=json.load(open('data/v146-replay-baseline.json')); b=json.load(open('data/v146-replay-after.json')); print('IDENTICAL' if a == b else 'DIFFERENT'); assert a == b"
```

Expected: `IDENTICAL`. Anything else means the split changed behaviour: fix the split, never the baseline. Then delete both files: `python -c "import pathlib; [pathlib.Path(p).unlink() for p in ('data/v146-replay-baseline.json', 'data/v146-replay-after.json')]"`.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py`
Expected: PASS (cooldown, warmup, issued_at and stats-shape tests unchanged).

Run: `python scripts/dev/testrun.py file tests/scripts/test_training_universe.py`
Expected: PASS (it monkeypatches `bs.replay_scenarios`, which `_replay_ticker` still calls).

Run: `python scripts/dev/testrun.py file tests/scripts/test_fvg_attribution.py`
Expected: PASS (the Step 5 whole-module shape test).

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_points.py`
Expected: PASS (V146-1/V146-2's scorer tests; the default path is unchanged).

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: PASS.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s swingbot/core/backtesting/backtest_scenarios.py swingbot/core/backtesting/scenario_rows.py swingbot/core/scanning/confidence.py | grep -E "replay|_bar_scenarios|_accept_scenario|_replay_params|signal_fields|scenario_trade_row|_regime_trend|_scoring_copy|_planned_rr|_expectancy_step|score_confidence"`
Expected: `replay_scenarios_detailed`, `_bar_scenarios`, `_accept_scenario`, `_replay_params`, `replay_scenarios` and every `scenario_rows` function below 15 (A or B; the old `replay_scenarios` C15 is gone); `_expectancy_step` A; `score_confidence` unchanged from its pre-task grade; `_score_confidence_legacy` no higher than its grade after V146-2 (E40 or lower -- the edit swaps one call for another and adds a defaulted parameter, no branch).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/scanning/confidence.py swingbot/core/backtesting/backtest_scenarios.py swingbot/core/backtesting/scenario_rows.py tests/backtesting/test_scenario_rows.py tests/scripts/test_fvg_attribution.py
git commit -m "feat(v146): replay hits and the TRAIN per-trade row with a live-identical confidence score (V146-7)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

---
