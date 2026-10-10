# v151 Plan detail page and the shared "Why" panel: Part 1, API and Discord link

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V151-3:" -A 400 docs/superpowers/plans/2026-10-10-v151-plan-detail-why-panel_1-api-and-discord-link.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v151-plan-detail-why-panel-design.md`](../specs/2026-10-09-v151-plan-detail-why-panel-design.md)

Global constraints, the decisions this part relies on (1-7 and 12), the wire contract, the task ledger and `## Parallelisation` live in the index: [`2026-10-10-v151-plan-detail-why-panel_0-index.md`](2026-10-10-v151-plan-detail-why-panel_0-index.md). Every task below implicitly includes those constraints (no `swingbot.config` import under `core/presentation`; v146 keys passed through; never `cd`; stage by name; no `VERSION.json` bump; complexity < 15).

## Parallelisation

See the index. Within this part: V151-1 ∥ V151-2 ∥ V151-4 ∥ V151-5 ∥ V151-7 (disjoint files). V151-3 needs V151-1 and V151-2. V151-6 needs V151-4 and V151-5. After V151-5 lands, re-run V151-2's test file (its no-config test reads `components.py`).

# Phase 1: API

### Task V151-1: `SessionCalendar.session_after`

**Model:** haiku — one small pure method with a fully specified contract and tests given verbatim.

**Files:**
- Modify: `swingbot/core/market/session.py` (class `SessionCalendar`, after `sessions_between` at ~:192)
- Modify: `tests/market/test_session_calendar.py` (append tests)

**Interfaces:**
- Consumes: nothing new. Uses the existing `SessionCalendar.position_on_or_before`, `first`, `last`.
- Produces: `SessionCalendar.session_after(self, d: dt.date, n: int) -> dt.date | None`. It returns the session `n` sessions after the session on or before `d`, so `n = 0` is that session itself. It returns `None` when `n < 0`, when `d` is before `first` or after `last`, or when the result runs past `last`. V151-3 calls it as `expires_on = session_after(created_day, expiry_bars)` and `time_exit_on = session_after(fill_day, hold_cap_bars - 1)` (index decision 1).

- [ ] **Step 1: Write the failing tests**

Append to `tests/market/test_session_calendar.py`. The file already imports `dt`, `pytest`, `SessionCalendar`, `nyse_calendar`, and defines `D = dt.date.fromisoformat`.

```python
# --- v151: session_after -------------------------------------------------

def test_session_after_zero_is_the_session_itself_or_the_one_before():
    cal = nyse_calendar()
    assert cal.session_after(D("2026-09-14"), 0) == D("2026-09-14")   # a Monday session
    assert cal.session_after(D("2026-09-12"), 0) == D("2026-09-11")   # Saturday rolls back to Friday


def test_session_after_counts_sessions_not_calendar_days():
    cal = nyse_calendar()
    # Mon 14 Sep + 5 sessions: 15, 16, 17, 18, 21.
    assert cal.session_after(D("2026-09-14"), 5) == D("2026-09-21")
    # Thanksgiving (Thu 26 Nov 2026) is skipped.
    assert cal.session_after(D("2026-11-25"), 1) == D("2026-11-27")


def test_session_after_matches_the_time_exit_tenth_session():
    from swingbot.core.planning.time_exit import tenth_session
    cal = nyse_calendar()
    fill = D("2026-09-15")
    assert cal.session_after(fill, 9) == tenth_session(fill, cal) == D("2026-09-28")


@pytest.mark.parametrize("day, n", [
    (D("2026-09-14"), -1),          # negative count
    (D("2017-12-29"), 0),           # before the calendar's first session
    (D("2031-01-02"), 0),           # after the calendar's last session
    (D("2030-12-30"), 5),           # result runs past coverage
])
def test_session_after_is_none_outside_coverage(day, n):
    assert nyse_calendar().session_after(day, n) is None


def test_session_after_on_a_small_calendar():
    cal = SessionCalendar([D("2026-01-05"), D("2026-01-06"), D("2026-01-08")])
    assert cal.session_after(D("2026-01-07"), 1) == D("2026-01-08")
    assert cal.session_after(D("2026-01-05"), 2) == D("2026-01-08")
    assert cal.session_after(D("2026-01-05"), 3) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_session_calendar.py`
Expected: FAIL with `AttributeError: 'SessionCalendar' object has no attribute 'session_after'`.

- [ ] **Step 3: Implement the method**

In `swingbot/core/market/session.py`, inside `class SessionCalendar`, directly after `sessions_between`:

```python
    def session_after(self, d: dt.date, n: int) -> dt.date | None:
        """The session ``n`` sessions after the session on or before ``d``.

        ``n = 0`` is that session itself. None when ``n`` is negative, when
        ``d`` lies outside the calendar, or when the result runs past it.
        v151: a plan's expiry day and time-exit day are bar counts from a
        session, read here as dates.
        """
        if n < 0 or d < self.first or d > self.last:
            return None
        i = self.position_on_or_before(d)
        if i is None or i + n >= len(self._sessions):
            return None
        return self._sessions[i + n]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_session_calendar.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/market/session.py`
Expected: no line for `session_after` (it is rank A or B).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/session.py tests/market/test_session_calendar.py
git commit -m "feat(session): SessionCalendar.session_after for bar-count dates (v151)"
```

### Task V151-2: `why_view.py`: `GateThresholds`, `gate_rows`, `calendar_rows`

**Model:** sonnet — new pure module with table-driven builders and a semantics table to follow exactly.

**Files:**
- Create: `swingbot/core/presentation/why_view.py`
- Create: `tests/presentation/test_why_view.py`

**Interfaces:**
- Consumes: `swingbot.core.market.opex.monthly_expiration(year: int, month: int) -> dt.date` and `opex.LAST_YEAR_COVERED` (both exist, `opex.py:73-84`; pure calendar, no config).
- Produces (V151-3 consumes):
  - `@dataclass(frozen=True) class GateThresholds: rs_gate: bool; rs_laggard_pct: float; rs_leader_pct: float; regime_gates: bool`
  - `gate_rows(direction: str | None, entry_context: dict | None, risk_features: dict | None, cohort_label: str | None, thresholds: GateThresholds) -> list[dict]`. It always returns three rows, in the order `rs`, `regime`, `earnings`. Each row has the keys `key, label, value, threshold, margin, applies, parts, note`.
  - `calendar_rows(start: dt.date, end: dt.date) -> list[dict]`. It returns `{"date": "<ISO>", "kind": "opex_monthly", "label": "Monthly OPEX"}` for every monthly expiration in `[start, end]` whose year is `<= opex.LAST_YEAR_COVERED`, in date order. It returns `[]` when `start > end`.

**Row semantics** (index decision 12 and § Wire contract, verbatim):

| key | label | value | threshold | margin | applies | parts | note |
|---|---|---|---|---|---|---|---|
| `rs` | `Relative strength` | `rs_combined`, else `rs_pctile` | bearish: `rs_laggard_pct`; otherwise `rs_leader_pct` | bearish: `threshold - value`; otherwise `value - threshold`; `None` whenever `applies` is false | `True` only when value is not None, `rs_gate` is on, and the arm is live (bearish always live; bullish live only when `rs_leader_pct > 0`) | `Ticker RS pctile` = `rs_pctile`, `Sector RS pctile` = `sector_pctile` | first match: value None → `exempt`; `rs_gate` off → `RS gate off`; bullish arm with `rs_leader_pct <= 0` → `bullish arm disabled`; else `None` |
| `regime` | `Regime` | `regime2_state` | `None` | `None` | `regime_gates` | `[]` | `cohort_label` |
| `earnings` | `Days to earnings` | `risk_features["days_to_earnings"]` | `None` | `None` | value is not None | `[]` | `not recorded on this plan` when value is None, else `None` |

- [ ] **Step 1: Write the failing tests**

Create `tests/presentation/test_why_view.py`:

```python
"""v151: the Why panel's pure gate and calendar rows.

Thresholds are passed in (GateThresholds), never read from config, so this
file patches nothing.
"""
import ast
import datetime as dt
import pathlib

import pytest

from swingbot.core.presentation.why_view import GateThresholds, calendar_rows, gate_rows

D = dt.date.fromisoformat
LIVE = GateThresholds(rs_gate=True, rs_laggard_pct=25.0, rs_leader_pct=0.0, regime_gates=False)


def _row(rows, key):
    return next(r for r in rows if r["key"] == key)


def test_rows_come_in_a_fixed_order_with_the_full_shape():
    rows = gate_rows("bearish", {}, {}, None, LIVE)
    assert [r["key"] for r in rows] == ["rs", "regime", "earnings"]
    for row in rows:
        assert set(row) == {"key", "label", "value", "threshold", "margin", "applies", "parts", "note"}


def test_rs_bearish_cleared_is_a_positive_margin():
    ctx = {"rs_combined": 18.0, "rs_pctile": 20.0, "sector_pctile": 30.0}
    rs = _row(gate_rows("bearish", ctx, {}, None, LIVE), "rs")
    assert rs["label"] == "Relative strength"
    assert rs["value"] == 18.0
    assert rs["threshold"] == 25.0
    assert rs["margin"] == pytest.approx(7.0)
    assert rs["applies"] is True
    assert rs["note"] is None
    assert rs["parts"] == [{"label": "Ticker RS pctile", "value": 20.0},
                           {"label": "Sector RS pctile", "value": 30.0}]


def test_rs_bearish_failed_is_a_negative_margin():
    rs = _row(gate_rows("bearish", {"rs_combined": 40.0}, {}, None, LIVE), "rs")
    assert rs["margin"] == pytest.approx(-15.0)
    assert rs["applies"] is True


def test_rs_bullish_arm_disabled_at_zero():
    rs = _row(gate_rows("bullish", {"rs_combined": 70.0}, {}, None, LIVE), "rs")
    assert rs["threshold"] == 0.0
    assert rs["applies"] is False
    assert rs["margin"] is None
    assert rs["note"] == "bullish arm disabled"


def test_rs_bullish_arm_live_measures_value_minus_threshold():
    leader = GateThresholds(rs_gate=True, rs_laggard_pct=25.0, rs_leader_pct=60.0, regime_gates=False)
    rs = _row(gate_rows("bullish", {"rs_combined": 70.0}, {}, None, leader), "rs")
    assert rs["applies"] is True
    assert rs["margin"] == pytest.approx(10.0)


def test_rs_gate_off_keeps_the_row_but_does_not_apply():
    off = GateThresholds(rs_gate=False, rs_laggard_pct=25.0, rs_leader_pct=0.0, regime_gates=False)
    rs = _row(gate_rows("bearish", {"rs_combined": 18.0}, {}, None, off), "rs")
    assert rs["value"] == 18.0
    assert rs["threshold"] == 25.0
    assert rs["applies"] is False
    assert rs["margin"] is None
    assert rs["note"] == "RS gate off"


def test_rs_falls_back_to_the_ticker_pctile():
    rs = _row(gate_rows("bearish", {"rs_pctile": 22.0}, {}, None, LIVE), "rs")
    assert rs["value"] == 22.0
    assert rs["margin"] == pytest.approx(3.0)


def test_all_missing_values_are_none_never_a_sentinel():
    rows = gate_rows("bearish", None, None, None, LIVE)
    rs, regime, earnings = (_row(rows, k) for k in ("rs", "regime", "earnings"))
    assert rs["value"] is None and rs["margin"] is None and rs["applies"] is False
    assert rs["note"] == "exempt"
    assert rs["parts"] == [{"label": "Ticker RS pctile", "value": None},
                           {"label": "Sector RS pctile", "value": None}]
    assert regime["value"] is None
    assert earnings["value"] is None


def test_regime_row_carries_the_cohort_note_and_the_switch():
    ctx = {"regime2_state": "BULL_QUIET"}
    regime = _row(gate_rows("bullish", ctx, {}, "BULL_QUIET-LONG", LIVE), "regime")
    assert regime["label"] == "Regime"
    assert regime["value"] == "BULL_QUIET"
    assert regime["threshold"] is None and regime["margin"] is None
    assert regime["applies"] is False
    assert regime["note"] == "BULL_QUIET-LONG"
    on = GateThresholds(rs_gate=True, rs_laggard_pct=25.0, rs_leader_pct=0.0, regime_gates=True)
    assert _row(gate_rows("bullish", ctx, {}, None, on), "regime")["applies"] is True


def test_earnings_none_does_not_apply_and_says_so():
    earnings = _row(gate_rows("bullish", {}, {"days_to_earnings": None}, None, LIVE), "earnings")
    assert earnings["label"] == "Days to earnings"
    assert earnings["applies"] is False
    assert earnings["note"] == "not recorded on this plan"


def test_earnings_recorded_applies_with_no_note():
    earnings = _row(gate_rows("bullish", {}, {"days_to_earnings": 12}, None, LIVE), "earnings")
    assert earnings["value"] == 12
    assert earnings["applies"] is True
    assert earnings["note"] is None


# --- calendar_rows -------------------------------------------------------

def test_a_window_spanning_one_monthly_opex():
    assert calendar_rows(D("2026-10-01"), D("2026-10-31")) == [
        {"date": "2026-10-16", "kind": "opex_monthly", "label": "Monthly OPEX"}]


def test_a_holiday_shifted_thursday():
    # 19 Apr 2030 is Good Friday and the third Friday: the expiration moves to Thursday.
    assert calendar_rows(D("2030-04-01"), D("2030-04-30")) == [
        {"date": "2030-04-18", "kind": "opex_monthly", "label": "Monthly OPEX"}]


def test_window_edges_are_inclusive_and_span_months():
    rows = calendar_rows(D("2026-09-18"), D("2026-10-16"))
    assert [r["date"] for r in rows] == ["2026-09-18", "2026-10-16"]


def test_an_empty_window():
    assert calendar_rows(D("2026-10-19"), D("2026-11-10")) == []
    assert calendar_rows(D("2026-10-31"), D("2026-10-01")) == []


def test_dates_past_coverage_return_no_row():
    assert calendar_rows(D("2031-01-01"), D("2031-03-31")) == []
    assert [r["date"] for r in calendar_rows(D("2030-12-01"), D("2031-01-31"))] == ["2030-12-20"]


# --- the no-config property ------------------------------------------------

@pytest.mark.parametrize("module", ["why_view.py", "components.py"])
def test_presentation_module_imports_no_config(module):
    path = pathlib.Path("swingbot/core/presentation") / module
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.startswith("swingbot.config")]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("swingbot.config"):
                offenders.append(node.module)
            if node.module == "swingbot" and any(a.name == "config" for a in node.names):
                offenders.append("swingbot.config")
    assert not offenders, f"{module} imports {offenders}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_why_view.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.presentation.why_view'`.

- [ ] **Step 3: Implement the module**

Create `swingbot/core/presentation/why_view.py`:

```python
"""v151: the Why panel's gate margins and holding-window calendar -- pure.

No I/O and no ``swingbot.config`` import: the admin layer builds
``GateThresholds`` from config per request and passes it in, so this package
keeps its no-config property and the tests pass thresholds directly.
Thresholds are TODAY's configuration, never the values in force when the plan
was issued -- the UI says so beside every margin.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from swingbot.core.market import opex

RS_LABEL = "Relative strength"
REGIME_LABEL = "Regime"
EARNINGS_LABEL = "Days to earnings"
EARNINGS_NOT_RECORDED = "not recorded on this plan"
OPEX_KIND = "opex_monthly"
OPEX_LABEL = "Monthly OPEX"


@dataclass(frozen=True)
class GateThresholds:
    """Today's gate configuration, as the admin layer read it."""

    rs_gate: bool
    rs_laggard_pct: float
    rs_leader_pct: float
    regime_gates: bool


def _row(key: str, label: str, value, *, applies: bool, threshold=None, margin=None,
         parts: list | None = None, note: str | None = None) -> dict:
    return {"key": key, "label": label, "value": value, "threshold": threshold,
            "margin": margin, "applies": applies, "parts": parts or [], "note": note}


def _rs_note(value, bearish: bool, t: GateThresholds) -> str | None:
    """Why the RS row does not apply, first reason wins; None when it does."""
    if value is None:
        return "exempt"
    if not t.rs_gate:
        return "RS gate off"
    if not bearish and t.rs_leader_pct <= 0:
        return "bullish arm disabled"
    return None


def _rs_row(direction, ctx: dict, risk: dict, cohort, t: GateThresholds) -> dict:
    value = ctx.get("rs_combined")
    if value is None:
        value = ctx.get("rs_pctile")
    bearish = direction == "bearish"
    threshold = t.rs_laggard_pct if bearish else t.rs_leader_pct
    note = _rs_note(value, bearish, t)
    applies = note is None
    margin = None
    if applies:
        margin = threshold - value if bearish else value - threshold
    parts = [{"label": "Ticker RS pctile", "value": ctx.get("rs_pctile")},
             {"label": "Sector RS pctile", "value": ctx.get("sector_pctile")}]
    return _row("rs", RS_LABEL, value, applies=applies, threshold=threshold,
                margin=margin, parts=parts, note=note)


def _regime_row(direction, ctx: dict, risk: dict, cohort, t: GateThresholds) -> dict:
    return _row("regime", REGIME_LABEL, ctx.get("regime2_state"),
                applies=bool(t.regime_gates), note=cohort)


def _earnings_row(direction, ctx: dict, risk: dict, cohort, t: GateThresholds) -> dict:
    value = risk.get("days_to_earnings")
    return _row("earnings", EARNINGS_LABEL, value, applies=value is not None,
                note=EARNINGS_NOT_RECORDED if value is None else None)


#: One builder per gate, in display order. Add a gate by adding a builder.
_BUILDERS = (_rs_row, _regime_row, _earnings_row)


def gate_rows(direction: str | None, entry_context: dict | None, risk_features: dict | None,
              cohort_label: str | None, thresholds: GateThresholds) -> list[dict]:
    """One row per gate, never hidden: a missing value is ``None`` and shows "—"."""
    ctx = entry_context or {}
    risk = risk_features or {}
    return [build(direction, ctx, risk, cohort_label, thresholds) for build in _BUILDERS]


def _months(start: dt.date, end: dt.date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def calendar_rows(start: dt.date, end: dt.date) -> list[dict]:
    """Monthly OPEX dates inside ``[start, end]``, within opex.py's coverage.

    Weekly OPEX is left out (every Friday -- noise). Earnings and macro dates
    are out of scope (they need I/O this module must not do).
    """
    rows = []
    for year, month in _months(start, end):
        if year > opex.LAST_YEAR_COVERED:
            break
        day = opex.monthly_expiration(year, month)
        if start <= day <= end:
            rows.append({"date": day.isoformat(), "kind": OPEX_KIND, "label": OPEX_LABEL})
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_why_view.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/presentation/why_view.py`
Expected: no output (every function is below rank C).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/why_view.py tests/presentation/test_why_view.py
git commit -m "feat(presentation): why_view gate rows and OPEX calendar rows (v151)"
```

### Task V151-3: Detail endpoint: the new `detail` keys

**Model:** sonnet — new admin helper over several existing modules, date edge cases, and a complexity budget on existing builders.

**Files:**
- Create: `swingbot/admin/trade_why.py`
- Modify: `swingbot/admin/api_v1/trades.py` (imports at ~:40-46; `_plan_detail` at ~:660; `_legacy_detail` at ~:698)
- Modify: `tests/admin/test_api_v1_trade_detail.py` (append tests)

**Interfaces:**
- Consumes:
  - V151-1: `nyse_calendar().session_after(d: dt.date, n: int) -> dt.date | None`.
  - V151-2: `GateThresholds(rs_gate, rs_laggard_pct, rs_leader_pct, regime_gates)`, `gate_rows(direction, entry_context, risk_features, cohort_label, thresholds) -> list[dict]`, `calendar_rows(start, end) -> list[dict]` from `swingbot.core.presentation.why_view`.
  - Existing: `nyse_calendar().sessions_between(asof, target) -> int | None` (`session.py:192`), `US_MARKET_TZ` (`session.py:12`), `fill_day_from_history(history) -> dt.date` (raises `ValueError` when not filled, `time_exit.py:62`), `HORIZONS[key]["max_holding_days"]` (`strategy_types.py:48`), `config.RS_GATE` (bool), `config.RS_LAGGARD_PERCENTILE` (float), `config.RS_LEADER_PERCENTILE` (float), `config.REGIME_GATES_ENABLED` (bool).
- Produces (V151-8 mirrors the wire shape):
  - `WIRE_CONTEXT_KEYS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined", "htf_aligned", "gap_p90_pct", "gap_fragile")`
  - `gate_thresholds() -> GateThresholds`
  - `plan_why_fields(plan: dict, trade: dict | None, today: dt.date | None = None) -> dict`
  - `legacy_why_fields(trade: dict, today: dt.date | None = None) -> dict`
  - `_session_day(stamp) -> dt.date | None` and `_today() -> dt.date` (ET; tests monkeypatch it)
  - Twelve new `detail` keys on both origins: `entry_context`, `risk_features`, `cohort_label`, `confidence_points`, `confidence_unevaluated`, `gates`, `sessions_since_created`, `expires_on`, `time_exit_on`, `calendar`, `hold_cap_bars`, `acceptance_level` (index § Wire contract).

**Rules, exactly** (spec § API and index decisions 1-5). Dates go on the wire as ISO strings or `None`.

| Key | Plan-backed | Legacy |
|---|---|---|
| `entry_context` | plan's if non-empty, else trade's, filtered to `WIRE_CONTEXT_KEYS` | trade's, filtered, else `{}` |
| `risk_features` | plan's if non-empty, else trade's, else `{}` | trade's, else `{}` |
| `cohort_label` | `plan["cohort_label"]` | `None` |
| `confidence_points` | first not-None of trade's, plan's; else `None` | trade's, else `None` |
| `confidence_unevaluated` | first not-None of trade's, plan's; else `[]` | trade's, else `[]` |
| `gates` | `gate_rows(plan direction, the unfiltered context, risk, cohort, gate_thresholds())` | same with the trade's fields and `cohort_label=None` |
| `sessions_since_created` | `sessions_between(session_day(created_at), today)` | same from `opened_at` |
| `expires_on` | `session_after(created_day, expiry_bars)` when status is `PENDING`, else `None` | `None` |
| `time_exit_on` | `session_after(fill_day, hold_cap_bars - 1)` when `hold_cap_bars` is an int ≥ 1 and the plan has filled, else `None` | `None` |
| `calendar` | `calendar_rows(created_day, end)` where `end` = `time_exit_on`, else `expires_on`, else `created_day + max_holding_days` (calendar days) of the plan's `horizon_key`; `[]` when there is no start or no end | `[]` |
| `hold_cap_bars` | `plan["hold_cap_bars"]` | `None` |
| `acceptance_level` | `plan["acceptance_level"]` | `None` |

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_v1_trade_detail.py`. The file already has `pytest`, `_plan`, `_trade`, `_PLAN_ID`, `_TRADE_ID`, and the `seed` / `logged_in` fixtures.

```python
# --- v151: the Why panel's detail keys ------------------------------------

import datetime as dt  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.admin import trade_why  # noqa: E402

WHY_KEYS = {
    "entry_context", "risk_features", "cohort_label", "confidence_points",
    "confidence_unevaluated", "gates", "sessions_since_created", "expires_on",
    "time_exit_on", "calendar", "hold_cap_bars", "acceptance_level",
}
_MONDAY = "2026-09-14T14:00:00+00:00"      # 10:00 ET, Monday 14 Sep 2026
_TODAY = dt.date(2026, 9, 21)               # five sessions later


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(trade_why, "_today", lambda: _TODAY)
    return _TODAY


def _why_plan(**overrides):
    plan = {**_plan(_PLAN_ID, status="PENDING"), "created_at": _MONDAY, "horizon_key": "2w",
            "direction": "bearish", "cohort_label": "BEAR_VOL-SHORT",
            "entry_context": {"rs_combined": 18.0, "rs_pctile": 20.0, "sector_pctile": 30.0,
                              "regime2_state": "BEAR_VOL", "gap_p90_pct": 2.4,
                              "gap_fragile": True, "htf_aligned": True, "atr_pct": 3.1},
            "risk_features": {"days_to_earnings": None, "atr_pct": 3.1},
            "hold_cap_bars": None, "acceptance_level": 99.5}
    plan.update(overrides)
    return plan


def _detail(client, ident):
    response = client.get(f"/api/v1/trades/{ident}")
    assert response.status_code == 200
    return response.get_json()["detail"]


def test_plan_backed_detail_carries_every_why_key(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert WHY_KEYS <= set(detail)
    assert detail["cohort_label"] == "BEAR_VOL-SHORT"
    assert detail["acceptance_level"] == 99.5
    assert detail["hold_cap_bars"] is None


def test_plan_entry_context_wins_and_is_filtered_to_the_wire_keys(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=_PLAN_ID), "entry_context": {"rs_combined": 90.0}}
    seed(plans=[_why_plan()], trades=[trade])
    ctx = _detail(logged_in, _PLAN_ID)["entry_context"]
    assert ctx["rs_combined"] == 18.0
    assert "atr_pct" not in ctx
    assert set(ctx) <= set(trade_why.WIRE_CONTEXT_KEYS)


def test_an_empty_plan_context_falls_back_to_the_trades(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=_PLAN_ID), "entry_context": {"rs_combined": 90.0},
             "risk_features": {"days_to_earnings": 4}}
    seed(plans=[_why_plan(entry_context={}, risk_features={})], trades=[trade])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["entry_context"] == {"rs_combined": 90.0}
    assert detail["risk_features"] == {"days_to_earnings": 4}


def test_confidence_keys_absent_are_none_and_empty(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["confidence_points"] is None
    assert detail["confidence_unevaluated"] == []


def test_confidence_keys_present_pass_through_untouched(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=_PLAN_ID),
             "confidence_points": {"trend": 15, "regime": 7},
             "confidence_unevaluated": ["regime"]}
    seed(plans=[_why_plan()], trades=[trade])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["confidence_points"] == {"trend": 15, "regime": 7}
    assert detail["confidence_unevaluated"] == ["regime"]


def test_pending_plan_timing_and_calendar(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()])            # expiry_bars=5 from _plan()
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["sessions_since_created"] == 5
    assert detail["expires_on"] == "2026-09-21"
    assert detail["time_exit_on"] is None
    assert detail["calendar"] == [{"date": "2026-09-18", "kind": "opex_monthly", "label": "Monthly OPEX"}]


def test_filled_plan_with_a_hold_cap_has_a_time_exit_day(seed, logged_in, fixed_today):
    history = [{"status": "PENDING", "reason": None, "at": _MONDAY},
               {"status": "ACTIVE", "reason": "trigger_hit", "at": "2026-09-15T14:00:00+00:00"}]
    seed(plans=[_why_plan(status="ACTIVE", status_history=history, hold_cap_bars=10)],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["expires_on"] is None                 # not PENDING
    assert detail["time_exit_on"] == "2026-09-28"       # fill 15 Sep is session 1 of 10
    assert detail["hold_cap_bars"] == 10
    assert [r["date"] for r in detail["calendar"]] == ["2026-09-18"]


def test_active_plan_without_a_hold_cap_uses_the_horizon_window(seed, logged_in, fixed_today):
    # 2w: max_holding_days 14 -> 14 Sep .. 28 Sep.
    seed(plans=[_why_plan(status="ACTIVE")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["time_exit_on"] is None
    assert [r["date"] for r in detail["calendar"]] == ["2026-09-18"]


def test_gates_present_on_a_plan_backed_row(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()])
    gates = _detail(logged_in, _PLAN_ID)["gates"]
    assert [g["key"] for g in gates] == ["rs", "regime", "earnings"]
    rs = gates[0]
    assert rs["value"] == 18.0
    assert rs["threshold"] == config.RS_LAGGARD_PERCENTILE
    assert gates[1]["note"] == "BEAR_VOL-SHORT"


def test_legacy_row_has_the_same_keys_with_plan_only_fields_empty(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=None, status="win"), "opened_at": _MONDAY,
             "entry_context": {"rs_pctile": 22.0, "atr_pct": 1.0},
             "confidence_points": {"trend": 15}}
    seed(trades=[trade])
    detail = _detail(logged_in, _TRADE_ID)
    assert WHY_KEYS <= set(detail)
    assert detail["cohort_label"] is None
    assert detail["calendar"] == []
    assert detail["expires_on"] is None and detail["time_exit_on"] is None
    assert detail["hold_cap_bars"] is None and detail["acceptance_level"] is None
    assert detail["entry_context"] == {"rs_pctile": 22.0}
    assert detail["confidence_points"] == {"trend": 15}
    assert detail["confidence_unevaluated"] == []
    assert detail["sessions_since_created"] == 5
    assert [g["key"] for g in detail["gates"]] == ["rs", "regime", "earnings"]


def test_a_minimal_legacy_trade_still_gets_every_key(seed, logged_in, fixed_today):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    detail = _detail(logged_in, _TRADE_ID)
    assert WHY_KEYS <= set(detail)
    assert detail["entry_context"] == {} and detail["risk_features"] == {}
    assert detail["gates"][0]["note"] == "exempt"


# --- trade_why helpers, no HTTP --------------------------------------------

@pytest.mark.parametrize("stamp, expected", [
    ("2026-09-14", dt.date(2026, 9, 14)),
    ("2026-09-14T14:00:00+00:00", dt.date(2026, 9, 14)),
    ("2026-09-15T02:00:00+00:00", dt.date(2026, 9, 14)),   # 22:00 ET the evening before
    ("not a date", None),
    (None, None),
    ("", None),
])
def test_session_day_parses_dates_and_aware_datetimes(stamp, expected):
    assert trade_why._session_day(stamp) == expected


def test_gate_thresholds_read_todays_config(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", False)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 30.0)
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 55.0)
    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", True)
    t = trade_why.gate_thresholds()
    assert (t.rs_gate, t.rs_laggard_pct, t.rs_leader_pct, t.regime_gates) == (False, 30.0, 55.0, True)


def test_plan_why_fields_without_a_created_at_degrades_to_none():
    fields = trade_why.plan_why_fields({"status": "PENDING", "expiry_bars": 5}, None,
                                       today=dt.date(2026, 9, 21))
    assert fields["sessions_since_created"] is None
    assert fields["expires_on"] is None
    assert fields["calendar"] == []
    assert fields["entry_context"] == {} and fields["risk_features"] == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`
Expected: FAIL with `ImportError: cannot import name 'trade_why' from 'swingbot.admin'` (the whole module fails to collect).

- [ ] **Step 3: Create the helper module**

Create `swingbot/admin/trade_why.py`:

```python
"""v151: the Why panel's keys on GET /api/v1/trades/<id> `detail`.

Kept out of api_v1/trades.py so `_plan_detail` / `_legacy_detail` gain one
`**` merge each and no branch. Everything here is read-only and API-only:
stored plans and trades are never rewritten (schema-evolution.md -- no
read-time upcasting). v146's `confidence_points` / `confidence_unevaluated`
are passed through, never computed; a record written before v146 has
neither and gets None / [].
"""
from __future__ import annotations

import datetime as dt

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.time_exit import fill_day_from_history
from swingbot.core.presentation.why_view import GateThresholds, calendar_rows, gate_rows

#: Only these entry_context keys go on the wire, not the full feature dict.
WIRE_CONTEXT_KEYS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined",
                     "htf_aligned", "gap_p90_pct", "gap_fragile")


def gate_thresholds() -> GateThresholds:
    """Today's gate configuration -- the UI labels margins 'vs today's thresholds'."""
    return GateThresholds(
        rs_gate=bool(config.RS_GATE),
        rs_laggard_pct=float(config.RS_LAGGARD_PERCENTILE),
        rs_leader_pct=float(config.RS_LEADER_PERCENTILE),
        regime_gates=bool(config.REGIME_GATES_ENABLED),
    )


def _today() -> dt.date:
    """The ET session date now. Tests monkeypatch this."""
    return dt.datetime.now(US_MARKET_TZ).date()


def _session_day(stamp) -> dt.date | None:
    """An ISO date or datetime string as its ET calendar date; None on garbage."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(US_MARKET_TZ).date()


def _iso(day: dt.date | None) -> str | None:
    return day.isoformat() if day else None


def _as_dict(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _wire_context(ctx: dict) -> dict:
    return {key: ctx[key] for key in WIRE_CONTEXT_KEYS if key in ctx}


def _first_set(*values):
    """The first value that is not None -- an empty {} or [] is a real answer."""
    return next((v for v in values if v is not None), None)


def _sessions_since(created: dt.date | None, today: dt.date) -> int | None:
    return None if created is None else nyse_calendar().sessions_between(created, today)


def _expires_on(plan: dict, created: dt.date | None) -> dt.date | None:
    """Last live bar of a PENDING plan: `pending_expired` fires past expiry_bars."""
    bars = plan.get("expiry_bars")
    if plan.get("status") != "PENDING" or created is None or not isinstance(bars, int):
        return None
    return nyse_calendar().session_after(created, bars)


def _time_exit_on(plan: dict) -> dt.date | None:
    """The fill session is session 1, so the cap-th session is cap - 1 after it."""
    cap = plan.get("hold_cap_bars")
    if not isinstance(cap, int) or cap < 1:
        return None
    try:
        fill = fill_day_from_history(plan.get("status_history") or [])
    except ValueError:
        return None
    return nyse_calendar().session_after(fill, cap - 1)


def _window_end(plan: dict, created: dt.date, expires, time_exit) -> dt.date | None:
    if time_exit is not None:
        return time_exit
    if expires is not None:
        return expires
    hold = (HORIZONS.get(plan.get("horizon_key")) or {}).get("max_holding_days")
    return created + dt.timedelta(days=hold) if hold else None


def _calendar(plan: dict, created: dt.date | None, expires, time_exit) -> list[dict]:
    if created is None:
        return []
    end = _window_end(plan, created, expires, time_exit)
    return calendar_rows(created, end) if end is not None else []


def plan_why_fields(plan: dict, trade: dict | None, today: dt.date | None = None) -> dict:
    """The new detail keys for a plan-backed row. The plan's frozen copy of
    entry_context / risk_features wins; the trade's logged copy is the
    fallback for an older plan."""
    t = trade or {}
    today = today or _today()
    created = _session_day(plan.get("created_at"))
    expires = _expires_on(plan, created)
    time_exit = _time_exit_on(plan)
    ctx = _as_dict(plan.get("entry_context") or t.get("entry_context"))
    risk = _as_dict(plan.get("risk_features") or t.get("risk_features"))
    cohort = plan.get("cohort_label")
    return {
        "entry_context": _wire_context(ctx),
        "risk_features": risk,
        "cohort_label": cohort,
        "confidence_points": _first_set(t.get("confidence_points"), plan.get("confidence_points")),
        "confidence_unevaluated": _first_set(t.get("confidence_unevaluated"),
                                             plan.get("confidence_unevaluated")) or [],
        "gates": gate_rows(plan.get("direction"), ctx, risk, cohort, gate_thresholds()),
        "sessions_since_created": _sessions_since(created, today),
        "expires_on": _iso(expires),
        "time_exit_on": _iso(time_exit),
        "calendar": _calendar(plan, created, expires, time_exit),
        "hold_cap_bars": plan.get("hold_cap_bars"),
        "acceptance_level": plan.get("acceptance_level"),
    }


def legacy_why_fields(trade: dict, today: dt.date | None = None) -> dict:
    """Same keys for a legacy trade; plan-only ones are None / []."""
    today = today or _today()
    ctx = _as_dict(trade.get("entry_context"))
    risk = _as_dict(trade.get("risk_features"))
    return {
        "entry_context": _wire_context(ctx),
        "risk_features": risk,
        "cohort_label": None,
        "confidence_points": trade.get("confidence_points"),
        "confidence_unevaluated": trade.get("confidence_unevaluated") or [],
        "gates": gate_rows(trade.get("direction"), ctx, risk, None, gate_thresholds()),
        "sessions_since_created": _sessions_since(_session_day(trade.get("opened_at")), today),
        "expires_on": None,
        "time_exit_on": None,
        "calendar": [],
        "hold_cap_bars": None,
        "acceptance_level": None,
    }
```

- [ ] **Step 4: Merge the keys into both detail builders**

In `swingbot/admin/api_v1/trades.py`, add the import beside the existing `from swingbot.core.presentation.plan_view import plan_view` (~:43):

```python
from swingbot.admin.trade_why import legacy_why_fields, plan_why_fields
```

In `_plan_detail`, the returned dict ends with `"account_balance_after": t.get("account_balance_after"),`. Add one line after it, inside the dict:

```python
        "account_balance_after": t.get("account_balance_after"),
        **plan_why_fields(plan, trade),
    }
```

In `_legacy_detail`, the same last line gets one line after it:

```python
        "account_balance_after": t.get("account_balance_after"),
        **legacy_why_fields(t),
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py tests/admin/test_api_v1_trades.py`
Expected: PASS, `0 failed`, including the existing `test_detail_row_fields_match_the_list_exactly` (the new keys sit inside `detail` only).

Run: `python -m radon cc -s -n C swingbot/admin/trade_why.py swingbot/admin/api_v1/trades.py`
Expected: no line for any function in `trade_why.py`. `_plan_detail`, `_legacy_detail` and `get_trade` show the same rank as before, or no line (a `**` merge adds no branch).

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/trade_why.py swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trade_detail.py
git commit -m "feat(api): Why panel keys on the trade detail endpoint (v151)"
```

# Phase 2: Discord link

### Task V151-4: `ADMIN_PUBLIC_URL` config field

**Model:** haiku — one schema field and one `.env.example` entry, copying a neighbouring field's pattern.

**Files:**
- Modify: `swingbot/config.py` (Discord Alerts group: directly after the `ALERT_EMBED_LAYOUT` `Field(...)`, ~:757-762)
- Modify: `.env.example` (Discord Alerts block: directly after `ALERT_EMBED_LAYOUT=detailed`, ~:461)
- Create: `tests/test_config_admin_public_url.py`

**Interfaces:**
- Consumes: the existing `Field` dataclass (`config.py:74`), `config.FIELDS`, `config._apply_env()` (`config.py:1340`, what `reload()` runs on SIGHUP).
- Produces: `config.ADMIN_PUBLIC_URL: str`, default `""`, `type="text"`, `hot_reloadable=True`, group `"Discord Alerts"`. V151-6 reads it at every embed build.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_admin_public_url.py`:

```python
"""v151: the admin UI's public base URL, read by the bot to link plan embeds."""
import pytest

from swingbot import config


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


@pytest.fixture
def restore_config():
    """_apply_env() rewrites every FIELDS global; put them all back afterwards."""
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_field_sits_in_the_bot_side_discord_alerts_group():
    field = _field("ADMIN_PUBLIC_URL")
    assert field.attr == "ADMIN_PUBLIC_URL"
    assert field.section == "Discord Alerts"
    assert field.type == "text"
    assert field.default == ""
    assert field.hot_reloadable is True
    assert not field.sensitive


def test_help_says_the_bot_reads_it_at_embed_build_time():
    help_text = _field("ADMIN_PUBLIC_URL").help
    assert "Read by the bot each time it builds an alert embed" in help_text
    assert "empty = no link" in help_text


def test_default_is_empty_meaning_no_link(monkeypatch, restore_config):
    monkeypatch.delenv("ADMIN_PUBLIC_URL", raising=False)
    config._apply_env()
    assert config.ADMIN_PUBLIC_URL == ""


def test_a_reload_picks_up_a_new_value(monkeypatch, restore_config):
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://swingbot.example.com")
    changed = config._apply_env()
    assert config.ADMIN_PUBLIC_URL == "https://swingbot.example.com"
    assert "ADMIN_PUBLIC_URL" in changed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_config_admin_public_url.py`
Expected: FAIL with `StopIteration` (no field `ADMIN_PUBLIC_URL`).

- [ ] **Step 3: Add the field**

In `swingbot/config.py`, directly after the `Field("ALERT_EMBED_LAYOUT", ...)` entry (it ends `"Purely a rendering choice; no scoring or filtering changes."),`), insert:

```python
    # v151: the plan-detail link on every plan-carrying embed. Bot-side on
    # purpose -- the Admin UI group configures the admin container, while this
    # one is read by the bot at embed-build time (apply_chrome's link_base).
    Field("ADMIN_PUBLIC_URL", "ADMIN_PUBLIC_URL", "Discord Alerts", "Admin UI public URL (plan links)",
          type="text", default="", hot_reloadable=True,
          help="Read by the bot each time it builds an alert embed — SIGHUP applies a change, no "
               "restart. The admin UI's base URL as reached from the device you open Discord on "
               "(e.g. the Cloudflare tunnel hostname); empty = no link."),
```

- [ ] **Step 4: Add it to `.env.example`**

In `.env.example`, directly after the line `ALERT_EMBED_LAYOUT=detailed`, insert (keep one blank line before and after, like its neighbours):

```
# The admin UI's base URL as reached from the device you open Discord on
# (e.g. the Cloudflare tunnel hostname). Every plan-carrying embed's title
# links to <this>/plans/<plan id>. Must be http(s)://host; anything else
# logs one warning and the embeds carry no link. Empty = no link.
ADMIN_PUBLIC_URL=
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_config_admin_public_url.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: PASS. This existing test is what covers the `.env.example` half: it fails for a schema key missing there.

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_admin_public_url.py
git commit -m "feat(config): ADMIN_PUBLIC_URL for plan links in Discord embeds (v151)"
```

### Task V151-5: `plan_link` + `apply_chrome(link_base=)`

**Model:** sonnet — URL validation on the one choke point every plan-carrying embed passes through; a malformed URL makes Discord reject the whole message.

**Files:**
- Modify: `swingbot/core/presentation/components.py` (imports at the top; new `plan_link` before `apply_chrome` at ~:64; `apply_chrome` signature and body)
- Modify: `tests/presentation/test_components.py` (append tests)

**Interfaces:**
- Consumes: nothing from earlier tasks. Standard library `logging` and `urllib.parse.urlsplit` only. No `swingbot.config` import (V151-2's `test_presentation_module_imports_no_config` checks this file).
- Produces (V151-6 consumes):
  - `plan_link(plan_id: str | None, base: str | None) -> str | None`. It returns `f"{base.rstrip('/')}/plans/{plan_id}"` when `plan_id` and `base` are both non-empty and `base` is valid. Otherwise it returns `None`. Valid means: no whitespace character anywhere, `urlsplit(base).scheme` is `http` or `https`, and `urlsplit(base).netloc` is non-empty. A `ValueError` from `urlsplit` counts as invalid. A non-empty invalid base logs one WARNING per distinct value per process.
  - `_WARNED_BASES: set[str]`, module-level. It holds the bad values already warned about.
  - `apply_chrome(embed, *, accent=None, plan_id=None, kind=None, level=None, r=None, blocked=False, link_base: str | None = None) -> None`. When `plan_link(plan_id, link_base)` returns a URL, it sets `embed.url`. Otherwise the embed is byte-identical to today's.

- [ ] **Step 1: Write the failing tests**

Append to `tests/presentation/test_components.py`. The file already imports `c` (components), `t` (tokens), `discord` and `pytest`.

```python
# --- v151: the plan link on the embed title ---------------------------------

import logging  # noqa: E402

PLAN = "44444444-4444-4444-8444-444444444444"


@pytest.fixture
def fresh_warnings(monkeypatch):
    monkeypatch.setattr(c, "_WARNED_BASES", set())


def test_apply_chrome_with_a_valid_base_links_the_title(fresh_warnings):
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, accent=t.accent_for_level(5), plan_id=PLAN,
                   link_base="https://swingbot.example.com")
    assert embed.url == f"https://swingbot.example.com/plans/{PLAN}"


def test_a_trailing_slash_is_handled(fresh_warnings):
    assert c.plan_link(PLAN, "https://swingbot.example.com/") == \
        f"https://swingbot.example.com/plans/{PLAN}"
    assert c.plan_link(PLAN, "http://10.0.0.5:5000") == f"http://10.0.0.5:5000/plans/{PLAN}"


def test_the_link_leaves_the_footer_unchanged(fresh_warnings):
    linked, plain = discord.Embed(title="x"), discord.Embed(title="x")
    c.apply_chrome(linked, accent=t.accent_for_level(5), plan_id=PLAN, link_base="https://a.example")
    c.apply_chrome(plain, accent=t.accent_for_level(5), plan_id=PLAN)
    assert linked.footer.text == plain.footer.text
    assert linked.color == plain.color


def test_a_kind_embed_gets_the_link_too(fresh_warnings):
    from swingbot.core.presentation.kinds import Kind
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=5, plan_id=PLAN, link_base="https://a.example")
    assert embed.url == f"https://a.example/plans/{PLAN}"


@pytest.mark.parametrize("base", [None, ""])
def test_no_base_means_no_link_and_no_warning(base, fresh_warnings, caplog):
    embed = discord.Embed(title="x")
    with caplog.at_level(logging.WARNING, logger=c.__name__):
        c.apply_chrome(embed, accent=t.accent_for_level(5), plan_id=PLAN, link_base=base)
    assert embed.url is None
    assert not caplog.records


def test_no_plan_id_means_no_link(fresh_warnings):
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, accent=t.accent_for_level(5), link_base="https://a.example")
    assert embed.url is None


@pytest.mark.parametrize("base", [
    "ftp://x",                       # scheme not http(s)
    "javascript:x",                  # scheme not http(s), no netloc
    "https://",                      # no netloc
    "https://swing bot.example",     # whitespace inside
    " https://a.example",            # leading whitespace
    "swingbot.example.com",          # no scheme at all
    "http://[::1",                   # urlsplit raises ValueError
])
def test_a_malformed_base_yields_no_link(base, fresh_warnings):
    assert c.plan_link(PLAN, base) is None
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, accent=t.accent_for_level(5), plan_id=PLAN, link_base=base)
    assert embed.url is None


def test_one_warning_per_distinct_bad_value(fresh_warnings, caplog):
    with caplog.at_level(logging.WARNING, logger=c.__name__):
        for _ in range(2):
            c.apply_chrome(discord.Embed(title="x"), accent=t.accent_for_level(5),
                           plan_id=PLAN, link_base="ftp://x")
        c.apply_chrome(discord.Embed(title="x"), accent=t.accent_for_level(5),
                       plan_id=PLAN, link_base="https://")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "ftp://x" in warnings[0].getMessage()


def test_without_link_base_the_embed_is_byte_identical_to_before(fresh_warnings):
    before = discord.Embed(title="x")
    c.apply_chrome(before, accent=t.accent_for_level(5), plan_id=PLAN)
    after = discord.Embed(title="x")
    c.apply_chrome(after, accent=t.accent_for_level(5), plan_id=PLAN, link_base=None)
    before.timestamp = after.timestamp = None
    assert before.to_dict() == after.to_dict()
    assert "url" not in after.to_dict()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: FAIL. `AttributeError: ... has no attribute '_WARNED_BASES'` from the fixture, and `TypeError: apply_chrome() got an unexpected keyword argument 'link_base'`.

- [ ] **Step 3: Implement `plan_link` and the keyword**

In `swingbot/core/presentation/components.py`, change the imports at the top to:

```python
"""Whole reusable Discord embed parts rather than presentation tokens."""

import logging
from typing import NamedTuple
from urllib.parse import urlsplit

import discord

from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.presentation.kinds import Kind

log = logging.getLogger(__name__)

#: Bad ADMIN_PUBLIC_URL values already warned about -- one WARNING per value
#: per process, never one per embed.
_WARNED_BASES: set[str] = set()
```

Directly above `def apply_chrome`, add:

```python
def _valid_base(base: str) -> bool:
    """http(s), a host, no whitespace. Discord 400s the WHOLE message on a
    malformed embed url, so anything doubtful is rejected."""
    if any(ch.isspace() for ch in base):
        return False
    try:
        parts = urlsplit(base)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def plan_link(plan_id: str | None, base: str | None) -> str | None:
    """The plan page URL for an embed title, or None.

    Pure apart from one log line: the caller passes the base
    (config.ADMIN_PUBLIC_URL) so this package never imports config.
    """
    if not plan_id or not base:
        return None
    if not _valid_base(base):
        if base not in _WARNED_BASES:
            _WARNED_BASES.add(base)
            log.warning("ADMIN_PUBLIC_URL %r is not an http(s) URL with a host -- "
                        "embeds carry no plan link until it is fixed", base)
        return None
    return f"{base.rstrip('/')}/plans/{plan_id}"
```

Replace `apply_chrome` with:

```python
def apply_chrome(embed: discord.Embed, *, accent: discord.Color | None = None,
                 plan_id: str | None = None, kind: Kind | None = None,
                 level: int | None = None, r: float | None = None,
                 blocked: bool = False, link_base: str | None = None) -> None:
    """Apply the stripe, footer, timestamp and (v151) title link in place.

    Pushed builders pass ``kind`` (v110): the stripe and footer come from the
    registry. Command replies keep passing ``accent`` and the disclaimer
    footer, so their look is unchanged. ``link_base`` is the admin UI's public
    URL; with a plan id it becomes ``embed.url``, and with None / empty /
    malformed the embed is exactly what it was before v151."""
    if kind is not None:
        embed.color = discord.Color(kinds.stripe(kind, level=level, r=r, blocked=blocked))
        text = kinds.footer(kind, plan_id)
    elif accent is None:
        raise ValueError("apply_chrome needs a kind (pushed message) or an accent (command reply)")
    else:
        embed.color = accent
        text = f"{tokens.DISCLAIMER} · plan {plan_id[:8]}" if plan_id else tokens.DISCLAIMER
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text=text)
    url = plan_link(plan_id, link_base)
    if url:
        embed.url = url
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py tests/presentation/test_why_view.py`
Expected: PASS, `0 failed`; the existing `apply_chrome` tests pass unchanged. (Drop the second path if V151-2 has not landed; its no-config test reads `components.py`.)

Run: `python -m radon cc -s -n C swingbot/core/presentation/components.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/components.py tests/presentation/test_components.py
git commit -m "feat(presentation): validated plan link on apply_chrome (v151)"
```

### Task V151-6: Embed callers pass `link_base=config.ADMIN_PUBLIC_URL`

**Model:** sonnet — ten mechanical keyword edits across five modules, plus one behavioural test per module and a source-scan guard.

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` (`apply_chrome` calls at ~:32, ~:52, ~:298, ~:381)
- Modify: `swingbot/core/scanning/execution_embeds.py` (~:48)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (~:130, ~:253, ~:407)
- Modify: `swingbot/commands/views.py` (~:170)
- Modify: `swingbot/commands/trades.py` (~:307)
- Create: `tests/scanning/test_embed_plan_link.py`

**Interfaces:**
- Consumes: V151-4 `config.ADMIN_PUBLIC_URL: str`. V151-5 `apply_chrome(..., link_base: str | None = None)` and `components._WARNED_BASES`. All five modules already do `from swingbot import config` (`alert_embeds.py:7`, `execution_embeds.py:10`, `lifecycle_embeds.py:9`, `views.py:18`, `commands/trades.py:8`), so no import changes.
- Produces: nothing new. Every `apply_chrome` call that passes `plan_id=` also passes `link_base=config.ADMIN_PUBLIC_URL`. The command reply at `commands/trades.py:556` passes no `plan_id` and stays untouched.

Read `config.ADMIN_PUBLIC_URL` at the call, never into a module constant. The field is hot-reloadable, and a SIGHUP must change the next embed.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_embed_plan_link.py`:

```python
"""v151: every plan-carrying embed links its title to the plan page.

One behavioural test per embed module, plus a source scan so a future
apply_chrome(plan_id=...) call cannot forget the link.
"""
import ast
import pathlib

import pytest

from swingbot import config
from swingbot.commands.trades import _build_trade_detail_embed
from swingbot.commands.views import breakdown_embed
from swingbot.core.presentation import components
from swingbot.core.presentation.instructions import Instruction
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds
from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed, build_strategy_simple_embed
from swingbot.core.scanning.lifecycle_embeds import build_near_close_embed
from tests.commands.test_trades_display import _winning_trade
from tests.commands.test_views import _fixture_plan
from tests.scanning.test_strategy_embeds import _plan as _strategy_plan
from tests.tracking.test_near_tp_bypass import _near_tp_trade

BASE = "https://swingbot.example.com"
PLAN = "44444444-4444-4444-8444-444444444444"

MODULES = {
    "swingbot/core/scanning/alert_embeds.py": 4,
    "swingbot/core/scanning/execution_embeds.py": 1,
    "swingbot/core/scanning/lifecycle_embeds.py": 3,
    "swingbot/commands/views.py": 1,
    "swingbot/commands/trades.py": 1,
}


@pytest.fixture
def linked(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", BASE)
    monkeypatch.setattr(components, "_WARNED_BASES", set())


@pytest.fixture
def restore_config():
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_strategy_alert_and_its_mirror_link_the_plan(linked):
    plan = _strategy_plan()
    assert build_strategy_alert_embed(plan).url == f"{BASE}/plans/0123456789ab"
    assert build_strategy_simple_embed(plan).url == f"{BASE}/plans/0123456789ab"


def test_execution_ticket_links_the_plan(linked):
    instruction = Instruction(verb="MOVE STOP", ticker="NVDA", direction="bullish",
                              headline="MOVE STOP → 107.30 now", lines=("trail; +0.6R",),
                              plan_id=PLAN)
    assert execution_embeds.render(instruction, Kind.MOVE_STOP).url == f"{BASE}/plans/{PLAN}"


def test_lifecycle_near_close_links_the_plan(linked):
    warning = {"trade": _near_tp_trade(plan_id=PLAN), "near_which": "stop-loss",
               "sl_dist_pct": 1.0, "tp_dist_pct": 1.0, "current_price": 105.0}
    assert build_near_close_embed(warning).url == f"{BASE}/plans/{PLAN}"


def test_breakdown_reply_links_the_plan(linked):
    assert breakdown_embed(_fixture_plan()).url == f"{BASE}/plans/abcd1234-plan"


def test_trade_command_links_a_plan_backed_trade(linked):
    embed = _build_trade_detail_embed({**_winning_trade(), "plan_id": PLAN})
    assert embed.url == f"{BASE}/plans/{PLAN}"


def test_trade_command_on_a_legacy_trade_has_no_link(linked):
    assert _build_trade_detail_embed(_winning_trade()).url is None


def test_unset_base_means_no_link(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "")
    assert build_strategy_alert_embed(_strategy_plan()).url is None


def test_a_reload_changes_the_built_url(monkeypatch, restore_config):
    """SIGHUP runs config.reload() -> _apply_env(); the next embed reads the new value."""
    monkeypatch.setattr(components, "_WARNED_BASES", set())
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://one.example")
    config._apply_env()
    assert build_strategy_alert_embed(_strategy_plan()).url == "https://one.example/plans/0123456789ab"
    monkeypatch.setenv("ADMIN_PUBLIC_URL", "https://two.example")
    config._apply_env()
    assert build_strategy_alert_embed(_strategy_plan()).url == "https://two.example/plans/0123456789ab"


def _passes_the_link(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "link_base":
            v = kw.value
            return (isinstance(v, ast.Attribute) and v.attr == "ADMIN_PUBLIC_URL"
                    and isinstance(v.value, ast.Name) and v.value.id == "config")
    return False


@pytest.mark.parametrize("path, expected", sorted(MODULES.items()))
def test_every_plan_carrying_apply_chrome_call_passes_the_link(path, expected):
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "apply_chrome"
             and any(kw.arg == "plan_id" for kw in node.keywords)]
    assert len(calls) == expected, f"{path}: expected {expected} plan-carrying calls, found {len(calls)}"
    missing = [c.lineno for c in calls if not _passes_the_link(c)]
    assert not missing, f"{path}: apply_chrome(plan_id=...) without link_base at lines {missing}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embed_plan_link.py`
Expected: FAIL. The behavioural tests fail with `assert None == 'https://swingbot.example.com/plans/...'`, and the source scan fails with `apply_chrome(plan_id=...) without link_base at lines [...]`. `test_unset_base_means_no_link` and `test_trade_command_on_a_legacy_trade_has_no_link` already pass.

- [ ] **Step 3: Add the keyword at all ten call sites**

`swingbot/core/scanning/alert_embeds.py`. In `build_strategy_alert_embed` and in `build_strategy_simple_embed` (the two calls are identical):

```python
    ui.apply_chrome(embed, kind=Kind.STRATEGY_SIGNAL,
                    level=getattr(plan, "confidence_level", None), plan_id=plan.plan_id,
                    link_base=config.ADMIN_PUBLIC_URL)
```

At the end of `build_embed` (~:298):

```python
    ui.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=conf.level, blocked=blocked is not None,
                    plan_id=plan_v2.plan_id if plan_v2 else None,
                    link_base=config.ADMIN_PUBLIC_URL)
```

At the end of `_legacy_simple_alert` (~:381):

```python
    ui.apply_chrome(embed, kind=Kind.SETUP_SIMPLE, level=conf.level,
                    plan_id=plan_v2.plan_id if plan_v2 else None,
                    link_base=config.ADMIN_PUBLIC_URL)
```

`swingbot/core/scanning/execution_embeds.py`, in `render` (~:48):

```python
    ui.apply_chrome(embed, kind=kind, level=instruction.level, r=r, plan_id=instruction.plan_id,
                    link_base=config.ADMIN_PUBLIC_URL)
```

`swingbot/core/scanning/lifecycle_embeds.py`. In `build_closed_trade_embed` (~:130):

```python
    ui.apply_chrome(embed, kind=Kind.CLOSED_TRADE, r=kinds.result_r(outcome, r),
                    plan_id=trade.get("plan_id"), link_base=config.ADMIN_PUBLIC_URL)
```

In `build_near_close_embed` (~:253):

```python
    ui.apply_chrome(embed, kind=kind, plan_id=t.get("plan_id"), link_base=config.ADMIN_PUBLIC_URL)
```

In `build_plan_event_embed` (~:407):

```python
    ui.apply_chrome(embed, kind=kind, r=stripe_r, plan_id=plan.plan_id,
                    link_base=config.ADMIN_PUBLIC_URL)
```

`swingbot/commands/views.py`, at the end of `breakdown_embed` (~:170):

```python
    ui.apply_chrome(embed, accent=ui.accent_for_level(plan.confidence_level),
                    plan_id=plan.plan_id, link_base=config.ADMIN_PUBLIC_URL)
```

`swingbot/commands/trades.py`, at the end of `_build_trade_detail_embed` (~:307):

```python
    ui.apply_chrome(embed, accent=accent, plan_id=match.get("plan_id"),
                    link_base=config.ADMIN_PUBLIC_URL)
```

Leave `summary_cmd`'s `ui.apply_chrome(embed, accent=ui.accent_for_outcome(outcome))` (~:556) alone. It carries no plan.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embed_plan_link.py`
Expected: PASS, `0 failed`.

Run the existing embed suites (`ADMIN_PUBLIC_URL` is empty by default, so their output is unchanged): `python scripts/dev/testrun.py file tests/scanning/test_strategy_embeds.py tests/scanning/test_execution_embeds.py tests/scanning/test_embeds_v3.py tests/scanning/test_lifecycle_push.py tests/commands/test_views.py tests/commands/test_trades_display.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/lifecycle_embeds.py swingbot/commands/views.py swingbot/commands/trades.py`
Expected: the same ranks as before the edit. A keyword argument adds no branch.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/lifecycle_embeds.py swingbot/commands/views.py swingbot/commands/trades.py tests/scanning/test_embed_plan_link.py
git commit -m "feat(embeds): plan-carrying embeds link to the plan page (v151)"
```

### Task V151-7: SPA serves `/plans/<id>` on reload

**Model:** haiku — one tuple entry and two test parametrizations.

**Files:**
- Modify: `swingbot/admin/spa.py` (`WORKSPACES`, ~:47-51)
- Modify: `tests/admin/test_spa_serving.py` (`SPA_WORKSPACES` at ~:34; the `test_a_detail_url_reloads_into_the_spa` parametrization at ~:80)

**Interfaces:**
- Consumes: nothing. `register()` (`spa.py:166`) already adds `/<workspace>` and `/<workspace>/<path:_rest>` for every entry, and no `/plans` Flask rule exists to collide with.
- Produces: `"plans"` in `spa.WORKSPACES`. A Discord link to `/plans/<uuid>` reloads into the SPA instead of 404ing. `test_every_angular_route_is_served_on_reload` stays green when V151-16 adds `plans/:id` to `app.routes.ts`.

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_spa_serving.py`, extend the workspace list:

```python
SPA_WORKSPACES = ("cockpit", "trades", "analytics", "universe", "system", "plans")
```

and the detail-URL parametrization:

```python
@pytest.mark.parametrize("path", ["/universe/AAPL", "/plans/44444444-4444-4444-8444-444444444444"])
def test_a_detail_url_reloads_into_the_spa(client, path, built):
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_spa_serving.py`
Expected: FAIL. `test_each_workspace_serves_the_spa[plans]` and `test_a_detail_url_reloads_into_the_spa[/plans/...]` get 404.

- [ ] **Step 3: Add the workspace**

In `swingbot/admin/spa.py`:

```python
WORKSPACES = (
    "dashboard", "trades", "analytics", "calendar", "watchlist", "risk",
    "system", "versions", "research", "reports", "ui",
    "cockpit", "universe",
    # v151: the plan page, reached from Discord embed links -- a reload or a
    # tapped link must get the shell, not a 404.
    "plans",
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_spa_serving.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/spa.py tests/admin/test_spa_serving.py
git commit -m "feat(admin): serve /plans/<id> into the SPA on reload (v151)"
```
