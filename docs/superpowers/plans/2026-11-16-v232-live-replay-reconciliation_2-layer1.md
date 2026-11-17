# v232 — Live versus replay reconciliation: Part 2, layer 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-7" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) (binding: `## Clarifications from the code brief`)
**Index:** [2026-11-16-v232-live-replay-reconciliation_0-index.md](2026-11-16-v232-live-replay-reconciliation_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below.

Tasks V232-6..V232-8b: the export records and populations, the layer 1 values in the live R unit (V232-7, V232-7b), and the mechanism tags with their distributions (V232-8, V232-8b). The checkpointed per-trade runner (V232-9, V232-9b) is in [Part 2b](2026-11-16-v232-live-replay-reconciliation_2b-runner.md) for the 1500-line cap.

Consumed from Part 1 (ledger rows V232-2..V232-5, created there):
`exit_sim.simulate_exit_from_fill`, `exit_sim_v2.simulate_exit_v2_from_fill`,
`raw_bars.load_bars` / `refusal`, `sessions.to_utc` / `ny_time` /
`issue_session` / `stamp_source` / `issue_bucket` / `in_regular_session` /
`minutes_after_open`, the package `scripts/reports/reconcile/__init__.py`.

Test imports, every task: `sys.path.insert(0, str(REPO / "scripts" / "reports"))`, then `from reconcile import <module>`, with `REPO = Path(__file__).resolve().parents[2]`.

## Review Focus

- **A plan doc whose fill overwrote `entry_price`** (stop-entry, limit, v180 next-open, v192 waiting). Rehydration must give the engine the issued state; pinned in V232-6 (`test_rehydrate_clears_a_fill_written_entry_price`).
- **A journal outcome that is not one of win/loss/scratch/timeout** (the generic `closed`). Only then does the `|R| <= 0.05` scratch rule apply; pinned in V232-7 (`test_outcome_class_keeps_engine_and_journal_labels`).
- **v2 fills booking costs inside `r_total`.** Every layer 1 value is gross: v2 runs with `V2_FILLS` and `ZERO_COSTS`; pinned in V232-7b (`test_v2_values_are_gross`).
- **A run killed mid-line.** The checkpoint ignores a torn last line and the restart re-scores only that trade; pinned in V232-9b, Part 2b (`test_a_torn_last_line_is_rescored`).
- **Holdout leak through an unfilled or still-open row.** Such rows carry no `values`, `effects`, tags or classes; pinned in V232-9, Part 2b (`test_unscored_rows_carry_no_backtest_outcome`).

---

# Phase 2 — Layer 1

### Task V232-6: Export records, populations and rehydration

**Model:** sonnet — a new self-contained loader over a fixed JSONL contract, no engine judgement.

**Files:**
- Create: `scripts/reports/reconcile/records.py`
- Test: `tests/scout/test_reconcile_records.py`

**Interfaces:**
- Consumes: the JSONL shapes of V232-1 (ledger row); `sessions.to_utc`, `sessions.issue_session`, `sessions.stamp_source` (V232-5); `autopsy.rows.read_input(path, input_fingerprints)` (exists, `scripts/reports/autopsy/rows.py:223`); `autopsy.eras.ERA_BOUNDARY_UTC` (exists, `eras.py:21`); `swingbot.core.analytics.override_fidelity.MANUAL_REASONS` (exists, `override_fidelity.py:38`, value `("manual", "manual_bulk")`); `swingbot.core.analytics.metrics.close_reason_text(trade)` (exists); `plan_types.plan_from_dict`, `PlanStatus` (exist).
- Produces (ledger V232-6, final):
  - `KINDS = ("plan", "rejection", "watchlist", "deploy")`; `MANUAL_REASONS` (re-exported, not redefined); `CLASSES = ("closed", "manual", "still_open", "unfilled")`.
  - `@dataclass(frozen=True) LiveRecord(plan_id: str, ticker: str, direction: str, plan: dict, trade: dict | None, journal: dict | None)` with property `side -> "long" | "short"` (`"short"` when `direction` is `bearish` or `short`).
  - `@dataclass(frozen=True) Export(records: tuple[LiveRecord, ...], rejections: tuple[dict, ...], watchlist: tuple[str, ...], deploys: tuple[dict, ...])`.
  - `load_export(path, *, input_fingerprints: dict | None = None, until: dt.date | None = None) -> Export`
  - `class_of(rec) -> str`, `era_of(rec, boundary=ERA_BOUNDARY_UTC) -> str`, `ledger_of(rec) -> str`, `unfilled_reason(rec) -> str`, `rehydrate(plan_doc: dict) -> tuple[TradePlanV2, bool]`, `deploys_between(export, start: dt.date, end: dt.date) -> list[dict]`.

**Rules this task fixes (from the spec's `### Populations` and `### Layer 1` rehydration):**

| Function | Rule |
|---|---|
| `load_export` | Read the bytes through `rows.read_input` (records the SHA-256 when `input_fingerprints` is given). One JSON object per non-blank line; a `kind` outside `KINDS` raises `ValueError` naming the 1-based line number. `plan` lines become `LiveRecord`s (`plan_id`, `ticker`, `direction` from the plan doc); `rejection` lines keep their five fields as a dict; `watchlist` lines give a **sorted, de-duplicated** tuple of tickers; `deploy` lines keep `entry` as a dict. With `until`, drop plan records whose `issue_session(stamp_source(plan)[0]) > until` and rejections whose `signal_date > until.isoformat()`. Zero rejection or deploy lines give empty tuples (measured zeros, known-traps T2). |
| `class_of` | `trade is None` → `"unfilled"`. `trade` present and `trade.get("closed_at")` empty → `"still_open"`. Otherwise `"manual"` when the plan's last `status_history` entry has `reason in MANUAL_REASONS` **or** `metrics.close_reason_text(trade) in MANUAL_REASONS`, else `"closed"`. A closed trade without a journal doc is still `"closed"`; V232-9 refuses it (`no_journal`). |
| `era_of` | Stamp = `trade["opened_at"]` when a trade exists, else the plan stamp from `stamp_source`. `"headline"` when `to_utc(stamp) >= boundary`, else `"earlier"`. |
| `ledger_of` | `trade["ledger"]`, else `plan.get("ledger")`, else `"main"`. |
| `unfilled_reason` | The last `status_history` entry with `status == "CANCELLED"` → its `reason` (or `"cancelled"` when that is empty); plan `status == "PENDING"` → `"pending"`; anything else → `"unknown"`. |
| `rehydrate` | `copy.deepcopy(plan_doc)` (never mutate the export), `plan_from_dict`, then `working_stop=None`, `legs_realized=[]`, `status_history=[]`, `status=PlanStatus.PENDING`, `runner_high_close=None`, `be_armed_session=None`, `runner_floor_session=None`. `entry_price` is reset to `None` unless `entry_type == "market"` and `waits_next_open is not True` (the plan manager writes the fill into `entry_price` at `plan_manager.py:1267`, `:1324`, `:1391`; the builder issues non-market and waiting plans with `None`, `builders.py:494`, `gap_reclaim.py:109`; the engine never reads `entry_price` for a market fill). `stop_loss`, `tp1`, `tp2`, `hold_cap_bars`, `issued_at` stay. Returns `(plan, plan.tp1_fraction < 1.0)`. |
| `deploys_between` | Entries whose `to_utc(entry["ts"])` falls on a New York date in `[start, end]`, sorted by `ts`. An entry without `ts` is skipped. |

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-6: export records, populations and rehydration."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import records  # noqa: E402


def _plan_doc(**kw):
    base = dict(plan_id="P1", ticker="AAA", created_at="2026-10-06T15:00:00+00:00",
                source="confluence", strategy="RSI", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
                stop_loss=98.0, tp1=104.0, tp1_fraction=1.0, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.CLOSED,
                status_history=[{"status": "ACTIVE", "reason": "filled", "at": "x"}],
                issued_at="2026-10-06T15:00:00+00:00")
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


TRADE = {"id": "T1", "plan_id": "P1", "ticker": "AAA", "direction": "bullish", "entry": 100.2,
         "stop_loss": 98.0, "take_profit": 104.0, "opened_at": "2026-10-06T15:01:00+00:00",
         "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0, "status": "win",
         "close_reason": "tp1", "ledger": "weak", "legs": []}
JOURNAL = {"trade_id": "T1", "outcome": "win", "r_realized": 1.73}


def _write(tmp_path, lines):
    path = tmp_path / "export.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _rec(plan=None, trade=TRADE, journal=JOURNAL):
    plan = plan or _plan_doc()
    return records.LiveRecord(plan["plan_id"], plan["ticker"], plan["direction"], plan, trade, journal)


def test_load_export_reads_every_kind_and_fingerprints(tmp_path):
    path = _write(tmp_path, [
        {"kind": "plan", "plan": _plan_doc(), "trade": TRADE, "journal": JOURNAL},
        {"kind": "rejection", "ticker": "BBB", "gate": "rs", "strategy": "RSI", "horizon": "2w",
         "signal_date": "2026-10-07"},
        {"kind": "watchlist", "ticker": "ZZZ", "added_at": "2026-01-01"},
        {"kind": "watchlist", "ticker": "AAA", "added_at": "2026-01-01"},
        {"kind": "deploy", "entry": {"ts": "2026-10-01T10:00:00Z", "git_sha": "abc"}},
    ])
    prints = {}
    export = records.load_export(path, input_fingerprints=prints)
    assert [r.plan_id for r in export.records] == ["P1"]
    assert export.records[0].side == "long"
    assert export.rejections[0]["gate"] == "rs"
    assert export.watchlist == ("AAA", "ZZZ")
    assert export.deploys[0]["git_sha"] == "abc"
    assert [len(v) for v in prints.values()] == [64]


def test_an_unknown_kind_names_its_line(tmp_path):
    path = _write(tmp_path, [{"kind": "watchlist", "ticker": "A", "added_at": "x"}, {"kind": "row"}])
    with pytest.raises(ValueError, match="line 2"):
        records.load_export(path)


def test_empty_rejections_and_deploys_are_measured_zeros(tmp_path):
    export = records.load_export(_write(tmp_path, [{"kind": "plan", "plan": _plan_doc(),
                                                    "trade": None, "journal": None}]))
    assert export.rejections == () and export.deploys == () and export.watchlist == ()


def test_until_drops_later_plans_and_rejections(tmp_path):
    late = _plan_doc(plan_id="P2", issued_at="2026-10-20T15:00:00+00:00")
    path = _write(tmp_path, [
        {"kind": "plan", "plan": _plan_doc(), "trade": None, "journal": None},
        {"kind": "plan", "plan": late, "trade": None, "journal": None},
        {"kind": "rejection", "ticker": "B", "gate": "g", "strategy": "s", "horizon": "2w",
         "signal_date": "2026-10-21"},
    ])
    export = records.load_export(path, until=dt.date(2026, 10, 9))
    assert [r.plan_id for r in export.records] == ["P1"] and export.rejections == ()


def test_short_side_for_bearish():
    assert _rec(plan=_plan_doc(direction="bearish")).side == "short"


@pytest.mark.parametrize("trade,journal,plan_kw,expected", [
    (None, None, {}, "unfilled"),
    ({**TRADE, "closed_at": None}, None, {}, "still_open"),
    (TRADE, JOURNAL, {}, "closed"),
    ({**TRADE, "close_reason": "manual"}, JOURNAL, {}, "manual"),
    (TRADE, JOURNAL, {"status_history": [{"status": "ACTIVE", "reason": "filled", "at": "a"},
                                         {"status": "CLOSED", "reason": "manual_bulk", "at": "b"}]},
     "manual"),
    (TRADE, None, {}, "closed"),
])
def test_class_of(trade, journal, plan_kw, expected):
    assert records.class_of(_rec(plan=_plan_doc(**plan_kw), trade=trade, journal=journal)) == expected


def test_era_boundary_is_inclusive():
    at = {**TRADE, "opened_at": "2026-09-15T08:54:50+00:00"}
    before = {**TRADE, "opened_at": "2026-09-15T08:54:49+00:00"}
    assert records.era_of(_rec(trade=at)) == "headline"
    assert records.era_of(_rec(trade=before)) == "earlier"


def test_era_of_an_unfilled_plan_uses_the_plan_stamp():
    plan = _plan_doc(issued_at="2026-09-01T15:00:00+00:00")
    assert records.era_of(_rec(plan=plan, trade=None, journal=None)) == "earlier"


def test_ledger_of_defaults_to_main():
    assert records.ledger_of(_rec()) == "weak"
    assert records.ledger_of(_rec(trade=None, journal=None)) == "main"


@pytest.mark.parametrize("plan_kw,expected", [
    ({"status": PlanStatus.CANCELLED,
      "status_history": [{"status": "CANCELLED", "reason": "expired", "at": "a"}]}, "expired"),
    ({"status": PlanStatus.PENDING, "status_history": []}, "pending"),
    ({"status": PlanStatus.CLOSED}, "unknown"),
])
def test_unfilled_reason(plan_kw, expected):
    rec = _rec(plan=_plan_doc(**plan_kw), trade=None, journal=None)
    assert records.unfilled_reason(rec) == expected


def test_rehydrate_resets_to_issued_state_and_keeps_the_issued_stop():
    doc = _plan_doc(entry_type="stop_entry", entry_price=100.4, working_stop=100.4,
                    tp1_fraction=0.5, tp2=108.0, legs_realized=[{"fraction": 0.5}],
                    runner_high_close=105.0)
    plan, scale_out = records.rehydrate(doc)
    assert plan.status == PlanStatus.PENDING and plan.status_history == []
    assert plan.working_stop is None and plan.legs_realized == [] and plan.runner_high_close is None
    assert plan.stop_loss == 98.0 and plan.tp1 == 104.0 and plan.tp2 == 108.0
    assert scale_out is True
    assert doc["working_stop"] == 100.4 and doc["status_history"]   # export untouched


def test_rehydrate_clears_a_fill_written_entry_price():
    assert records.rehydrate(_plan_doc(entry_type="limit", entry_price=99.5))[0].entry_price is None
    waiting = _plan_doc(entry_type="market", entry_price=101.0, waits_next_open=True)
    assert records.rehydrate(waiting)[0].entry_price is None
    assert records.rehydrate(_plan_doc())[0].entry_price == 100.0


def test_rehydrate_scale_out_follows_tp1_fraction():
    assert records.rehydrate(_plan_doc(tp1_fraction=1.0))[1] is False


def test_deploys_between_filters_by_new_york_date():
    export = records.Export((), (), (), (
        {"ts": "2026-10-10T03:00:00Z", "git_sha": "late"},     # 2026-10-09 in New York
        {"ts": "2026-09-14T12:00:00Z", "git_sha": "early"},
        {"git_sha": "no_ts"},
    ))
    got = records.deploys_between(export, dt.date(2026, 9, 15), dt.date(2026, 10, 9))
    assert [d["git_sha"] for d in got] == ["late"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_records.py`
Expected: FAIL — `ImportError: cannot import name 'records' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/records.py`**

Module docstring names the spec's `### Populations`. Imports: `copy`, `dataclasses`, `datetime as dt`, `json`, `pathlib.Path`; `from autopsy.eras import ERA_BOUNDARY_UTC`; `from autopsy.rows import read_input`; `from . import sessions`; `from swingbot.core.analytics.metrics import close_reason_text`; `from swingbot.core.analytics.override_fidelity import MANUAL_REASONS`; `from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict`. `load_export` dispatches each line through a `{kind: handler}` table (complexity < 15). Write every function exactly per the rules table above; nothing else.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_records.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/records.py tests/scout/test_reconcile_records.py
git commit -m "feat(v232): reconcile export records, populations and plan rehydration"
```


### Task V232-7: Layer 1: the live R unit, live costs and outcome classes

**Model:** opus — the one-R-unit conversion and the cost model decide every number the report prints.

**Files:**
- Create: `scripts/reports/reconcile/layer1.py`
- Create: `tests/scout/test_reconcile_layer1.py`

**Interfaces:**
- Consumes: `records.LiveRecord` (V232-6; `.side`, `.plan`, `.trade`, `.journal`); `sessions.ny_time` (V232-5); existing `frictions.apply_frictions` / `commission_r` / `borrow_r` (`swingbot/core/edge/frictions.py:15/:22/:36`). The `frictions` dict is `autopsy.rows.friction_settings()` (keys `slippage_bps`, `commission_per_trade`, `commission_risk_basis`, `min_risk_fraction`).
- Produces (ledger V232-7, final; consumed by V232-7b and V232-9):
  - `FILL_MODELS = ("v1", "v2")`; `SCRATCH_R = 0.05`; `OUTCOME_CLASSES = ("win", "loss", "scratch", "timeout")`.
  - `live_risk(rec) -> float`; `r_live(rec) -> float`; `live_cost_r(rec, frictions: dict) -> float`; `bar_position(df, day: dt.date) -> int | None`; `outcome_class(outcome: str | None, r: float) -> str`.
  - Test helpers V232-7b appends to: `_plan_doc(direction="bullish", **kw) -> dict`, `_rec(direction="bullish", trade_kw=None, journal_kw=None, **plan_kw) -> LiveRecord`, `START`, `FRICTIONS`.
- V232-7b adds `GROSS_V2`, `Values`, `score`, `effects`, `would_fill` to the same module (split out for the 20 KB task cap; the ledger row's signatures are unchanged).

**Rules this task freezes (spec `### Layer 1`, Global Constraints "One R unit"):**

| Name | Rule |
|---|---|
| `live_risk` | absolute distance from `trade.entry` to `plan.stop_loss` (the **issued** stop); zero raises `ValueError`. |
| `r_live` | `journal.r_realized` times the trade's own risk (`trade.entry` to `trade.stop_loss`) divided by `live_risk`. Gross: `r_realized` is gross (`analytics/journal.py`, `metrics.r_multiple`). |
| `live_cost_r` | Positive. Slippage on the entry (`buy` for a long, `sell` for a short) and on each exit leg weighted by its `fraction` (the trade's `exit_price` when it has no legs; the entry when it has neither), divided by `live_risk`; plus `commission_r(risk_dollars=commission_risk_basis, commission=commission_per_trade)`; plus, for a short only, `borrow_r(entry, live_risk, days)` with `days` = New York calendar days from `opened_at` to `closed_at` (a same-day short pays none). Each side is priced with the same calls the autopsy's `modelled_net_r` uses (spec `### Inputs`, Costs). |
| `bar_position` | The integer position of the bar dated `day` in a daily frame (naive New York index, as `history_store.load` returns it); `None` when absent or the frame is empty. |
| `outcome_class` | An engine or journal label in `OUTCOME_CLASSES` is kept as is; anything else (the generic `closed`, `None`, `no_trade`) is `scratch` when `abs(r) <= SCRATCH_R`, else `win`/`loss` by sign. |

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-7 / V232-7b: layer 1 values in the live trade's risk unit."""
import datetime as dt
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer1, records  # noqa: E402

START = "2026-10-05"            # Monday; 2026-10-05..10-16 are all NYSE sessions
FRICTIONS = {"slippage_bps": 5.0, "commission_per_trade": 1.0,
             "commission_risk_basis": 100.0, "min_risk_fraction": 0.0}


def _plan_doc(direction="bullish", **kw):
    long = direction == "bullish"
    base = dict(plan_id="P1", ticker="AAA", created_at="2026-10-06T15:00:00+00:00",
                source="confluence", strategy="RSI", horizon_key="2w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
                stop_loss=98.0 if long else 102.0, tp1=104.0 if long else 96.0,
                tp1_fraction=1.0, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=[],
                issued_at="2026-10-06T15:00:00+00:00")
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


def _rec(direction="bullish", trade_kw=None, journal_kw=None, **plan_kw):
    long = direction == "bullish"
    plan = _plan_doc(direction, **plan_kw)
    trade = {"id": "T1", "plan_id": "P1", "ticker": "AAA", "direction": direction,
             "entry": 100.2 if long else 99.8, "stop_loss": plan["stop_loss"],
             "take_profit": plan["tp1"], "opened_at": "2026-10-06T15:01:00+00:00",
             "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0 if long else 96.0,
             "close_reason": "tp1", "legs": []}
    trade.update(trade_kw or {})
    journal = {"trade_id": "T1", "outcome": "win", "r_realized": 0.5, **(journal_kw or {})}
    return records.LiveRecord("P1", "AAA", direction, plan, trade, journal)


def _slip(*prices):
    return sum(prices) * 5.0 / 10_000.0


def test_live_risk_and_r_live_use_the_live_fill_and_the_issued_stop():
    rec = _rec(trade_kw={"stop_loss": 97.8}, journal_kw={"r_realized": 1.0})
    assert layer1.live_risk(rec) == pytest.approx(2.2)
    assert layer1.r_live(rec) == pytest.approx(2.4 / 2.2)


def test_r_live_is_unchanged_when_the_trade_keeps_the_issued_stop():
    assert layer1.r_live(_rec(journal_kw={"r_realized": -1.0})) == pytest.approx(-1.0)


def test_a_fill_on_the_issued_stop_raises():
    with pytest.raises(ValueError, match="issued stop"):
        layer1.live_risk(_rec(trade_kw={"entry": 98.0}))


def test_costs_a_short_pays_borrow_a_long_does_not():
    assert layer1.live_cost_r(_rec(), FRICTIONS) == pytest.approx(_slip(100.2, 104.0) / 2.2 + 0.02)
    borrow = 99.8 * 0.005 / 365.0 * 2 / 2.2                     # 10-06 -> 10-08, two days
    assert layer1.live_cost_r(_rec("bearish"), FRICTIONS) == pytest.approx(
        _slip(99.8, 96.0) / 2.2 + 0.02 + borrow)


def test_a_same_day_short_pays_no_borrow():
    rec = _rec("bearish", trade_kw={"closed_at": "2026-10-06T19:00:00+00:00"})
    assert layer1.live_cost_r(rec, FRICTIONS) == pytest.approx(_slip(99.8, 96.0) / 2.2 + 0.02)


def test_costs_weight_each_exit_leg_by_its_fraction():
    legs = [{"fraction": 0.5, "exit_price": 104.0, "r": 1.7, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 100.2, "r": 0.0, "reason": "runner_be"}]
    cost = layer1.live_cost_r(_rec(trade_kw={"legs": legs}), FRICTIONS)
    assert cost == pytest.approx(_slip(100.2, 0.5 * 104.0, 0.5 * 100.2) / 2.2 + 0.02)


def test_a_trade_without_exit_price_or_legs_prices_its_exit_at_the_entry():
    cost = layer1.live_cost_r(_rec(trade_kw={"exit_price": None}), FRICTIONS)
    assert cost == pytest.approx(_slip(100.2, 100.2) / 2.2 + 0.02)


def test_zero_frictions_cost_nothing_on_a_long():
    zero = {**FRICTIONS, "slippage_bps": 0.0, "commission_per_trade": 0.0}
    assert layer1.live_cost_r(_rec(), zero) == 0.0


def test_bar_position():
    df = make_ohlcv([100.0] * 5, start=START)
    assert layer1.bar_position(df, dt.date(2026, 10, 6)) == 1
    assert layer1.bar_position(df, dt.date(2026, 10, 3)) is None
    assert layer1.bar_position(df.iloc[0:0], dt.date(2026, 10, 6)) is None
    assert layer1.bar_position(None, dt.date(2026, 10, 6)) is None


@pytest.mark.parametrize("outcome,r,expected", [
    ("win", -0.3, "win"), ("timeout", 0.8, "timeout"), ("scratch", 0.4, "scratch"),
    ("closed", 0.05, "scratch"), ("closed", -0.05, "scratch"), ("closed", 0.2, "win"),
    ("closed", -0.2, "loss"), (None, 0.5, "win"), ("no_trade", 0.0, "scratch"),
])
def test_outcome_class_keeps_engine_and_journal_labels(outcome, r, expected):
    assert layer1.outcome_class(outcome, r) == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1.py`
Expected: FAIL — `ImportError: cannot import name 'layer1' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/layer1.py`**

```python
"""v232 layer 1: the same plan, backtest outcome against live outcome (spec ### Layer 1).

Every value is gross and in the live trade's risk unit, |live fill - issued stop|.
Nothing here stores or returns an outcome of a plan live did not fill.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r

from . import sessions

FILL_MODELS = ("v1", "v2")
SCRATCH_R = 0.05
OUTCOME_CLASSES = ("win", "loss", "scratch", "timeout")


def live_risk(rec) -> float:
    risk = abs(float(rec.trade["entry"]) - float(rec.plan["stop_loss"]))
    if risk <= 0:
        raise ValueError(f"plan {rec.plan_id}: the live fill sits on the issued stop")
    return risk


def r_live(rec) -> float:
    """Journal R (gross, the trade's own unit) re-expressed in the live unit."""
    own = abs(float(rec.trade["entry"]) - float(rec.trade["stop_loss"]))
    return float(rec.journal["r_realized"]) * own / live_risk(rec)


def _slip(price: float, side: str, bps: float) -> float:
    return abs(apply_frictions(price, side, slippage_bps=bps) - price)


def _exit_fills(trade: dict) -> list[tuple[float, float]]:
    legs = [leg for leg in trade.get("legs") or [] if leg.get("exit_price") is not None]
    if legs:
        return [(float(leg.get("fraction", 1.0)), float(leg["exit_price"])) for leg in legs]
    price = trade.get("exit_price")
    return [(1.0, float(price if price is not None else trade["entry"]))]


def _days_held(trade: dict) -> int:
    opened = sessions.ny_time(trade["opened_at"]).date()
    closed = sessions.ny_time(trade["closed_at"]).date()
    return max(0, (closed - opened).days)


def live_cost_r(rec, frictions: dict) -> float:
    """Modelled costs of the live trade, positive, in live R (borrow on shorts only)."""
    trade, risk = rec.trade, live_risk(rec)
    short = rec.side == "short"
    side_in, side_out = ("sell", "buy") if short else ("buy", "sell")
    bps = frictions["slippage_bps"]
    slip = _slip(float(trade["entry"]), side_in, bps)
    slip += sum(frac * _slip(price, side_out, bps) for frac, price in _exit_fills(trade))
    cost = slip / risk + commission_r(risk_dollars=frictions["commission_risk_basis"],
                                      commission=frictions["commission_per_trade"])
    if short:
        cost += borrow_r(float(trade["entry"]), risk, _days_held(trade))
    return cost


def bar_position(df, day: dt.date) -> int | None:
    if df is None or len(df) == 0:
        return None
    hits = np.flatnonzero(pd.DatetimeIndex(df.index).normalize() == pd.Timestamp(day))
    return int(hits[0]) if len(hits) else None


def outcome_class(outcome: str | None, r: float) -> str:
    """Engine and journal labels kept; a generic close is scratch within SCRATCH_R."""
    if outcome in OUTCOME_CLASSES:
        return outcome
    if abs(r) <= SCRATCH_R:
        return "scratch"
    return "win" if r > 0 else "loss"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/layer1.py tests/scout/test_reconcile_layer1.py
git commit -m "feat(v232): layer 1 live R unit, live costs and outcome classes"
```

### Task V232-7b: Layer 1: engine values under both fill models

**Model:** opus — engine routing per fill model, the no-fill rule and the holdout boundary of `would_fill`.

**Files:**
- Modify: `scripts/reports/reconcile/layer1.py` (created by V232-7)
- Modify: `tests/scout/test_reconcile_layer1.py` (created by V232-7)

**Interfaces:**
- Consumes: V232-7's `live_risk`, `bar_position`, `outcome_class`, `FILL_MODELS` and test helpers `_plan_doc`, `_rec`, `START`; `records.rehydrate` (V232-6); `sessions.issue_session`, `sessions.stamp_source` (V232-5); `exit_sim.simulate_exit_from_fill` (V232-2); `exit_sim_v2.simulate_exit_v2_from_fill` (V232-3); existing `exit_sim.simulate_exit` (:864), `exit_sim_v2.simulate_exit_v2` (:437), `exit_sim.ExitResult` (:63), `contract.resolve`, `contract.ZERO_COSTS` (:107), `contract.V2_FILLS` (:112).
- Produces (ledger V232-7, final; consumed by V232-9):
  - `GROSS_V2 = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)` (the `confluence_limit_replay.py:37` precedent).
  - `@dataclass(frozen=True) Values(fill_model: str, r_exit_only: float, exit_only_outcome: str, exit_only_class: str, r_as_backtest: float | None, r_rebased: float | None, stop_shift_pct: float | None, backtest_no_fill: bool)`.
  - `score(rec, df, fill_model) -> Values`; `effects(r_live: float, v: Values) -> dict` (`{"exit": float, "entry": float | None}`); `would_fill(rec, df, fill_model) -> bool | None`.

**Rules this task freezes (spec `### Layer 1`, clarifications 1 and 2):**

| Name | Rule |
|---|---|
| `score` | Signal bar = `issue_session(stamp_source(plan)[0])`; fill bar = `issue_session(trade.opened_at)`; either missing from `df` raises `ValueError` naming `signal` or `fill` (V232-9 refuses the trade `no_fill_bar`). `R_exit_only` = the from-fill wrapper at the fill bar and `trade.entry`, `fill_bar_check=False` (the walk starts the bar after the fill); its `r_total` is already in the live unit, its risk being live fill to issued stop. `R_as_backtest` = the public engine from the signal bar, converted `r_total * abs(result.entry_price - stop) / live_risk`; `r_rebased = r_total`; `stop_shift_pct = (abs(result.entry_price - stop) / live_risk - 1) * 100`. Each engine call gets a fresh `rehydrate`. v1 = `simulate_exit` / `simulate_exit_from_fill`; v2 = `simulate_exit_v2` / `simulate_exit_v2_from_fill` with `GROSS_V2`. An unknown fill model raises `ValueError`. |
| backtest no fill | `entry_index is None`, or outcome `not_triggered` / `no_trade`, or any leg with reason `gap_through_stop` (v1's fill-bar gap scratch; the spec lists `gap_through_stop` as not filled). Then `r_as_backtest`, `r_rebased`, `stop_shift_pct` are `None` and `backtest_no_fill` is `True`. |
| `effects` | `exit = r_live - r_exit_only`; `entry = r_exit_only - r_as_backtest`, or `None` on a backtest no-fill. They telescope: `r_live - r_as_backtest = exit + entry`. |
| `would_fill` | For unfilled plans (V232-9 calls it for them only): the engine from the signal bar, reduced to `not no_fill`; `None` when the signal bar is not in `df`. Nothing else of the result leaves the function (holdout). |

- [ ] **Step 1: Write the failing tests** — append to `tests/scout/test_reconcile_layer1.py`:

```python

from swingbot.core.backtesting.instrument.contract import V2_FILLS, ZERO_COSTS, resolve  # noqa: E402
from swingbot.core.planning import exit_sim, exit_sim_v2  # noqa: E402
from swingbot.core.planning.exit_sim import ExitResult  # noqa: E402

F = (100.0, 100.6, 99.6, 100.0)
D1 = (100.0, 100.8, 99.6, 100.5)            # 2026-10-06: issue and live fill session
LONG_ROWS = {
    "win": [F, D1, (100.5, 101.0, 100.0, 100.8), (100.8, 104.5, 100.5, 104.0)]
           + [(104.0, 104.4, 103.6, 104.0)] * 6,
    "loss": [F, D1, (100.5, 100.9, 99.9, 100.2), (100.0, 100.3, 97.5, 97.8)]
            + [(97.8, 98.2, 97.4, 97.8)] * 6,
    "scratch": [F, D1, (100.5, 102.5, 100.4, 102.0), (101.5, 101.8, 100.0, 100.5)]
               + [(100.5, 100.9, 100.1, 100.5)] * 6,
    "timeout": [F, (100.0, 100.5, 99.9, 100.2)] + [(100.2, 100.5, 99.9, 100.2)] * 8,
}


def _mirror(rows):
    """A long fixture reflected around 100: a short with the same path."""
    return [(200 - o, 200 - lo, 200 - hi, 200 - c) for o, hi, lo, c in rows]


def _bars(outcome, direction="bullish"):
    rows = LONG_ROWS[outcome]
    return make_ohlcv(rows if direction == "bullish" else _mirror(rows), start=START)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("outcome", ["win", "loss", "scratch", "timeout"])
def test_each_outcome_long_and_short_telescopes(direction, outcome):
    rec = _rec(direction, **({"hold_cap_bars": 3} if outcome == "timeout" else {}))
    live = layer1.r_live(rec)
    for model in layer1.FILL_MODELS:
        v = layer1.score(rec, _bars(outcome, direction), model)
        if model == "v1":
            assert v.exit_only_outcome == outcome and v.exit_only_class == outcome
        eff = layer1.effects(live, v)
        assert live - v.r_as_backtest == pytest.approx(eff["exit"] + eff["entry"])


def test_as_backtest_is_converted_to_the_live_unit_with_the_rebased_figure_beside_it():
    v = layer1.score(_rec(), _bars("win"), "v1")
    assert v.r_exit_only == pytest.approx(3.8 / 2.2, abs=1e-3)
    assert v.r_rebased == pytest.approx(1.4, abs=1e-3)            # entry at the 10-06 close, 100.5
    assert v.r_as_backtest == pytest.approx(1.4 * 2.5 / 2.2, abs=1e-3)
    assert v.stop_shift_pct == pytest.approx((2.5 / 2.2 - 1) * 100)
    assert v.backtest_no_fill is False


def test_the_rebased_figure_equals_the_live_unit_when_the_entries_match():
    v = layer1.score(_rec(trade_kw={"entry": 100.5}), _bars("win"), "v1")
    assert v.r_as_backtest == pytest.approx(v.r_rebased)
    assert v.stop_shift_pct == pytest.approx(0.0)


def test_v1_values_match_the_engines():
    rec, df = _rec(), _bars("loss")
    v = layer1.score(rec, df, "v1")
    plan, _ = records.rehydrate(rec.plan)
    assert v.r_rebased == exit_sim.simulate_exit(df, 1, plan, scale_out=False).r_total
    plan, _ = records.rehydrate(rec.plan)
    assert v.r_exit_only == exit_sim.simulate_exit_from_fill(
        df, 1, 100.2, plan, scale_out=False, fill_bar_check=False).r_total


def test_exit_only_starts_the_bar_after_the_fill():
    rows = list(LONG_ROWS["win"])
    rows[1] = (100.0, 100.8, 97.0, 100.5)          # the fill day's wick runs through the stop
    v = layer1.score(_rec(), make_ohlcv(rows, start=START), "v1")
    assert v.exit_only_outcome == "win"


def test_v2_values_are_gross():
    assert layer1.GROSS_V2.cost_model == ZERO_COSTS
    assert layer1.GROSS_V2.fill_model == V2_FILLS
    rec, df = _rec(), _bars("win")
    v = layer1.score(rec, df, "v2")
    plan, _ = records.rehydrate(rec.plan)
    gross = exit_sim_v2.simulate_exit_v2_from_fill(df, 1, 100.2, plan, layer1.GROSS_V2,
                                                   scale_out=False, fill_bar_check=False)
    plan, _ = records.rehydrate(rec.plan)
    costed = exit_sim_v2.simulate_exit_v2_from_fill(df, 1, 100.2, plan, resolve("v2"),
                                                    scale_out=False, fill_bar_check=False)
    assert v.r_exit_only == gross.r_total
    assert costed.r_total < gross.r_total
    plan, _ = records.rehydrate(rec.plan)
    assert v.r_rebased == exit_sim_v2.simulate_exit_v2(
        df, 1, plan, layer1.GROSS_V2, scale_out=False).r_total


def test_scale_out_follows_tp1_fraction():
    rec, df = _rec(tp1_fraction=0.5, tp2=108.0), _bars("win")
    plan, _ = records.rehydrate(rec.plan)
    expected = exit_sim.simulate_exit(df, 1, plan, scale_out=True).r_total
    assert layer1.score(rec, df, "v1").r_rebased == expected


def test_a_trigger_the_backtest_never_reaches_is_a_backtest_no_fill():
    rec = _rec(entry_type="stop_entry", trigger_price=106.0, entry_price=None)
    v = layer1.score(rec, _bars("win"), "v1")
    assert v.backtest_no_fill is True
    assert (v.r_as_backtest, v.r_rebased, v.stop_shift_pct) == (None, None, None)
    eff = layer1.effects(0.3, v)
    assert eff["entry"] is None and eff["exit"] == pytest.approx(0.3 - v.r_exit_only)


def test_a_gap_through_stop_scratch_counts_as_no_fill():
    gap = ExitResult(outcome="scratch", runner_outcome=None, entry_index=2, exit_index=2,
                     entry_price=97.0, r_total=0.0,
                     legs=[{"fraction": 1.0, "exit_price": 97.0, "r": 0.0,
                            "reason": "gap_through_stop"}])
    assert layer1._no_fill(gap) is True
    clean = ExitResult(outcome="scratch", runner_outcome=None, entry_index=2, exit_index=4,
                       entry_price=100.0, r_total=0.0,
                       legs=[{"fraction": 1.0, "exit_price": 100.0, "r": 0.0,
                              "reason": "breakeven_stop"}])
    assert layer1._no_fill(clean) is False


@pytest.mark.parametrize("trade_kw,plan_kw,what", [
    ({"opened_at": "2026-10-20T15:00:00+00:00"}, {}, "fill"),
    ({}, {"issued_at": "2026-09-28T15:00:00+00:00"}, "signal"),
])
def test_a_missing_bar_raises(trade_kw, plan_kw, what):
    with pytest.raises(ValueError, match=what):
        layer1.score(_rec(trade_kw=trade_kw, **plan_kw), _bars("win"), "v1")


def test_an_unknown_fill_model_raises():
    with pytest.raises(ValueError, match="fill model"):
        layer1.score(_rec(), _bars("win"), "v3")


def test_score_never_mutates_the_exported_plan_doc():
    rec = _rec(tp1_fraction=0.5, tp2=108.0)
    before = dict(rec.plan)
    layer1.score(rec, _bars("win"), "v1")
    layer1.score(rec, _bars("win"), "v2")
    assert rec.plan == before


def test_would_fill_is_a_bare_boolean():
    df = _bars("win")
    never = _rec(entry_type="stop_entry", trigger_price=106.0, entry_price=None)
    assert layer1.would_fill(never, df, "v1") is False
    assert layer1.would_fill(_rec(), df, "v1") is True
    assert layer1.would_fill(_rec(issued_at="2026-09-28T15:00:00+00:00"), df, "v2") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1.py`
Expected: FAIL — `AttributeError: module 'reconcile.layer1' has no attribute 'score'` (and `GROSS_V2`, `_no_fill`, `would_fill`); V232-7's tests still pass.

- [ ] **Step 3: Implement** — in `scripts/reports/reconcile/layer1.py`, extend the imports and constants at the top:

```python
import dataclasses

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim, exit_sim_v2

from . import records, sessions          # replaces `from . import sessions`

NO_FILL_OUTCOMES = ("not_triggered", "no_trade")
GAP_REASON = "gap_through_stop"
#: v2 fills, zero costs (the confluence_limit_replay.py precedent): every value is gross.
GROSS_V2 = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
```

then append to the end of the module:

```python
@dataclasses.dataclass(frozen=True)
class Values:
    fill_model: str
    r_exit_only: float
    exit_only_outcome: str
    exit_only_class: str
    r_as_backtest: float | None
    r_rebased: float | None
    stop_shift_pct: float | None
    backtest_no_fill: bool


def _v1_engine(df, index, plan, scale_out):
    return exit_sim.simulate_exit(df, index, plan, scale_out=scale_out)


def _v2_engine(df, index, plan, scale_out):
    return exit_sim_v2.simulate_exit_v2(df, index, plan, GROSS_V2, scale_out=scale_out)


def _v1_from_fill(df, index, price, plan, scale_out):
    return exit_sim.simulate_exit_from_fill(df, index, price, plan, scale_out=scale_out,
                                            fill_bar_check=False)


def _v2_from_fill(df, index, price, plan, scale_out):
    return exit_sim_v2.simulate_exit_v2_from_fill(df, index, price, plan, GROSS_V2,
                                                  scale_out=scale_out, fill_bar_check=False)


_ENGINES = {"v1": (_v1_engine, _v1_from_fill), "v2": (_v2_engine, _v2_from_fill)}


def _engines(fill_model: str):
    if fill_model not in _ENGINES:
        raise ValueError(f"unknown fill model {fill_model!r}; known: {FILL_MODELS}")
    return _ENGINES[fill_model]


def _no_fill(result) -> bool:
    if result.entry_index is None or result.outcome in NO_FILL_OUTCOMES:
        return True
    return any(leg.get("reason") == GAP_REASON for leg in result.legs or [])


def _signal_day(rec) -> dt.date:
    return sessions.issue_session(sessions.stamp_source(rec.plan)[0])


def _position(df, day: dt.date, what: str, rec) -> int:
    pos = bar_position(df, day)
    if pos is None:
        raise ValueError(f"plan {rec.plan_id}: no {what} bar on {day}")
    return pos


def score(rec, df, fill_model: str) -> Values:
    """R_exit_only and R_as_backtest of one scored trade under one fill model."""
    engine, from_fill = _engines(fill_model)
    risk, stop = live_risk(rec), float(rec.plan["stop_loss"])
    fill_pos = _position(df, sessions.issue_session(rec.trade["opened_at"]), "fill", rec)
    signal_pos = _position(df, _signal_day(rec), "signal", rec)
    plan, scale_out = records.rehydrate(rec.plan)
    exit_only = from_fill(df, fill_pos, float(rec.trade["entry"]), plan, scale_out)
    r_exit = float(exit_only.r_total)          # its risk is |live fill - issued stop|
    common = dict(fill_model=fill_model, r_exit_only=r_exit,
                  exit_only_outcome=exit_only.outcome,
                  exit_only_class=outcome_class(exit_only.outcome, r_exit))
    plan, scale_out = records.rehydrate(rec.plan)
    backtest = engine(df, signal_pos, plan, scale_out)
    if _no_fill(backtest):
        return Values(**common, r_as_backtest=None, r_rebased=None, stop_shift_pct=None,
                      backtest_no_fill=True)
    distance = abs(float(backtest.entry_price) - stop)
    return Values(**common, r_as_backtest=float(backtest.r_total) * distance / risk,
                  r_rebased=float(backtest.r_total),
                  stop_shift_pct=(distance / risk - 1.0) * 100.0, backtest_no_fill=False)


def effects(r_live: float, v: Values) -> dict:
    """Exit and entry effects in live R; they telescope to r_live - r_as_backtest."""
    entry = None if v.r_as_backtest is None else v.r_exit_only - v.r_as_backtest
    return {"exit": r_live - v.r_exit_only, "entry": entry}


def would_fill(rec, df, fill_model: str) -> bool | None:
    """Whether the backtest entry rule fills an unfilled plan: yes / no only."""
    engine, _ = _engines(fill_model)
    pos = bar_position(df, _signal_day(rec))
    if pos is None:
        return None
    plan, scale_out = records.rehydrate(rec.plan)
    return not _no_fill(engine(df, pos, plan, scale_out))
```

The parameter name `r_live` in `effects` shadows the module function inside that one body only; keep it (the ledger names it).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1.py`
Expected: PASS, `0 failed`. If a hand-computed value or a fixture outcome differs, print the engine's `legs` for that fixture before touching `layer1`: the v1 walker books `tp1` at exactly 104.0, rounds R to 3 places and moves the stop to break-even only on bars after the trigger bar; a different number means the fixture bars need fixing, never the module.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/layer1.py tests/scout/test_reconcile_layer1.py
git commit -m "feat(v232): layer 1 engine values, gross under both fill models"
```

### Task V232-8: Mechanism tags

**Model:** sonnet — a table-driven classifier over bars and stored docs, every rule frozen below.

**Files:**
- Create: `scripts/reports/reconcile/tags.py`
- Create: `tests/scout/test_reconcile_tags.py`

**Interfaces:**
- Consumes: `records.LiveRecord` (`.side`, `.plan`, `.trade`, `.journal`) (V232-6); `sessions.ny_time`, `sessions.issue_session`, `sessions.in_regular_session`, `sessions.minutes_after_open`, `sessions.sessions_apart` (V232-5); existing `swingbot.core.analytics.metrics.close_reason_text(trade)` (`metrics.py:98`; the last leg's reason, else `close_reason`, lowercased). It takes `r_exit_only` and both classes as plain values, so it needs nothing from V232-7.
- Produces (ledger V232-8; consumed by V232-8b, V232-9 and V232-13):
  - `TAGS` — the first 15 names below, in this order (V232-8b appends `entry_slip`, `poll_fill`: the ledger's 17); `SLIP_TAG_R = 0.05`; `SHORT_GAP_PCT = 0.03`; `FIRST_MINUTES = 15`; `LEVEL_TOLERANCE = 0.005`.
  - `@dataclass(frozen=True) TagInput(rec, df, fill_pos: int, exit_pos: int | None, live_risk: float, r_live: float, r_exit_only: float, live_class: str, exit_only_class: str)` — `df` is the raw bar frame, `fill_pos` / `exit_pos` the bar positions of the live fill and exit sessions (`exit_pos=None`: no exit bar in the frame).
  - `RULES: dict[str, Callable[[TagInput], bool]]` (one entry per name in `TAGS`); `tags_for(t) -> tuple[str, ...]` (in `TAGS` order).
  - Module helpers V232-8b reuses: `_sign(t)`, `_bar(t, k)`, `_gap_bar(t)`; test helpers `_t(...)`, `POSITIVE`, `LEGS`.
- V232-8b adds `gap_detail`, `entry_slip`, `poll_fill` and their two tags (split out for the 20 KB task cap; the ledger row's signatures are unchanged).

**Rules this task freezes (spec `### Layer 1`, Mechanism tags; "How `levels_edited` is told apart" is the builder's call, fixed here):**

`sign` = +1 long, -1 short. "After the fill" = bars `fill_pos + 1 .. exit bar` (the exit bar is `exit_pos`, or the frame's last bar when `None`). "Held through" = bars `fill_pos + 1 .. exit_pos - 1` (every bar after the fill when `exit_pos` is `None`). Level comparisons use `LEVEL_TOLERANCE = 0.005` (half a cent: the alert path stores rounded levels).

| Tag | Rule |
|---|---|
| `same_day_exit` | New York date of `opened_at` equals that of `closed_at`. |
| `wick_missed` | On a held-through bar, the range touches the **stop in force** (long `Low <= stop`, short `High >= stop`). Stop in force = the plan's final `working_stop` on bars dated after the earliest of `be_armed_session` / `runner_floor_session`, else the issued `stop_loss` (the poll's intermediate trail steps are not stored; this under-counts trails, never over-counts). |
| `both_levels_bar` | A bar after the fill holds the issued stop and `tp1` or `tp2` (long `Low <= stop` and `High >= target`; short mirrored). |
| `gap_through` | A bar after the fill (position >= 1) opens beyond the issued stop (`sign * (Open - stop) <= 0`) or beyond `tp1`/`tp2` (`sign * (Open - target) >= 0`). |
| `exit_outside_rth` / `entry_outside_rth` | `not sessions.in_regular_session(closed_at)` / `(opened_at)`. |
| `first_15min` | `minutes_after_open` of `opened_at` or of `closed_at` is below `FIRST_MINUTES`. |
| `live_stop_moved` | The plan's `working_stop` is set and differs from `stop_loss` by more than `LEVEL_TOLERANCE`, or `be_armed_session` / `runner_floor_session` is set. |
| `levels_edited` | The trade's `stop_loss` differs from the plan's issued `stop_loss`, or the trade's `take_profit` from the plan's `tp1`, by more than `LEVEL_TOLERANCE`. The engine's own moves live in `working_stop`, never in the trade's levels (no code path rewrites `trades.stop_loss` after `log_trade`), so any difference is an edit. |
| `scaled_out` | A leg with `fraction < 1`, or a `status_history` entry with reason `tp1_partial`. |
| `time_stop` | `close_reason_text(trade)` contains one of `TIME_REASONS = ("timeout", "time_exit", "stall", "hold")`. |
| `earnings_in_window` | `days_to_earnings` (trade `risk_features`, else journal `risk_features`) is recorded and `0 <= d <= sessions_apart(issue_session(opened_at), issue_session(closed_at))`. |
| `short_gap_against` | A short, and a bar after the fill opens more than `SHORT_GAP_PCT` above the prior bar's close. |
| `outcome_flip_live_better` / `_worse` | `live_class == "win"` and `exit_only_class == "loss"` / the reverse. |

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-8 / V232-8b: mechanism tags and the slip distributions."""
import dataclasses
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import records, tags  # noqa: E402

CALM = (100.5, 101.0, 100.0, 100.5)
ROWS = [CALM, CALM, CALM, (100.8, 104.5, 100.5, 104.0)] + [(104.0, 104.4, 103.6, 104.0)] * 4


def _mirror(row):
    o, hi, lo, c = row
    return (200 - o, 200 - lo, 200 - hi, 200 - c)


def _t(direction="bullish", plan=None, trade=None, rows=None, live_class="win",
       exit_only_class="win", exit_pos=3):
    long = direction == "bullish"
    doc = dict(plan_id="P1", ticker="AAA", created_at="2026-10-06T15:00:00+00:00",
               source="confluence", strategy="RSI", horizon_key="2w", direction=direction,
               entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
               stop_loss=98.0 if long else 102.0, tp1=104.0 if long else 96.0,
               tp1_fraction=1.0, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
               quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
               status=PlanStatus.CLOSED, status_history=[],
               issued_at="2026-10-06T15:00:00+00:00")
    doc.update(plan or {})
    plan_doc = plan_to_dict(TradePlanV2(**doc))
    trade_doc = {"id": "T1", "plan_id": "P1", "entry": 100.05 if long else 99.95,
                 "stop_loss": plan_doc["stop_loss"], "take_profit": plan_doc["tp1"],
                 "opened_at": "2026-10-06T15:01:00+00:00",       # 11:01 ET
                 "closed_at": "2026-10-08T17:00:00+00:00",       # 13:00 ET
                 "exit_price": 104.0 if long else 96.0, "close_reason": "tp1", "legs": []}
    trade_doc.update(trade or {})
    bars = [r if long else _mirror(r) for r in ROWS]
    for k, row in (rows or {}).items():
        bars[k] = row
    rec = records.LiveRecord("P1", "AAA", direction, plan_doc, trade_doc,
                             {"outcome": live_class, "r_realized": 1.9})
    risk = abs(trade_doc["entry"] - plan_doc["stop_loss"])
    return tags.TagInput(rec, make_ohlcv(bars, start="2026-10-05"), 1, exit_pos, risk, 1.9,
                         1.9, live_class, exit_only_class)


LEGS = [{"fraction": 0.5, "exit_price": 104.0, "r": 1.9, "reason": "tp1_partial"},
        {"fraction": 0.5, "exit_price": 100.05, "r": 0.0, "reason": "tp1_runner_be"}]
POSITIVE = {
    "same_day_exit": dict(trade={"closed_at": "2026-10-06T19:00:00+00:00"}),
    "wick_missed": dict(rows={2: (100.5, 101.0, 97.9, 100.5)}),
    "both_levels_bar": dict(rows={2: (100.5, 104.2, 97.9, 100.5)}),
    "gap_through": dict(rows={3: (104.6, 104.8, 104.0, 104.2)}),
    "exit_outside_rth": dict(trade={"closed_at": "2026-10-08T21:30:00+00:00"}),
    "entry_outside_rth": dict(trade={"opened_at": "2026-10-06T13:00:00+00:00"}),
    "first_15min": dict(trade={"opened_at": "2026-10-06T13:40:00+00:00"}),
    "live_stop_moved": dict(plan={"working_stop": 100.05, "be_armed_session": "2026-10-07"}),
    "levels_edited": dict(trade={"stop_loss": 97.0}),
    "scaled_out": dict(trade={"legs": LEGS}),
    "time_stop": dict(trade={"close_reason": "time_exit"}),
    "earnings_in_window": dict(trade={"risk_features": {"days_to_earnings": 1}}),
    "short_gap_against": dict(direction="bearish", rows={2: (103.8, 104.0, 103.0, 103.5)}),
    "outcome_flip_live_better": dict(live_class="win", exit_only_class="loss"),
    "outcome_flip_live_worse": dict(live_class="loss", exit_only_class="win"),
}


def test_every_tag_has_a_rule_and_a_positive_fixture():
    assert set(tags.RULES) == set(tags.TAGS)
    assert set(POSITIVE) <= set(tags.TAGS) and len(tags.TAGS) >= 15


def test_the_base_fixture_carries_no_tag():
    assert tags.tags_for(_t()) == ()
    assert tags.tags_for(_t("bearish")) == ()


@pytest.mark.parametrize("tag", list(POSITIVE))
def test_each_tag_fires_on_its_positive_case(tag):
    assert tag in tags.tags_for(_t(**POSITIVE[tag]))


@pytest.mark.parametrize("tag,case", [
    ("wick_missed", dict(rows={3: (100.8, 104.5, 97.9, 104.0)})),     # the exit day itself
    ("wick_missed", dict(plan={"working_stop": 100.4, "be_armed_session": "2026-10-07"},
                         rows={2: (100.5, 101.0, 100.3, 100.5)})),   # stop moved only after 10-07
    ("short_gap_against", dict(rows={2: (103.8, 104.0, 103.0, 103.5)})),   # a long
    ("earnings_in_window", dict(trade={"risk_features": {"days_to_earnings": 5}})),
    ("earnings_in_window", dict(trade={"risk_features": {"days_to_earnings": None}})),
    ("levels_edited", dict(trade={"stop_loss": 98.004})),              # rounding, not an edit
    ("first_15min", dict(trade={"opened_at": "2026-10-06T13:45:00+00:00"})),   # 09:45 ET
    ("outcome_flip_live_better", dict(live_class="win", exit_only_class="scratch")),
])
def test_near_misses_do_not_fire(tag, case):
    assert tag not in tags.tags_for(_t(**case))


def test_wick_missed_uses_the_moved_stop_after_its_session():
    case = dict(plan={"working_stop": 100.4, "be_armed_session": "2026-10-06"},
                rows={2: (100.5, 101.0, 100.3, 100.5)})
    assert "wick_missed" in tags.tags_for(_t(**case))


def test_earnings_falls_back_to_the_journal_features():
    t = _t()
    rec = records.LiveRecord("P1", "AAA", "bullish", t.rec.plan, t.rec.trade,
                             {**t.rec.journal, "risk_features": {"days_to_earnings": 0}})
    assert "earnings_in_window" in tags.tags_for(dataclasses.replace(t, rec=rec))

```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_tags.py`
Expected: FAIL — `ImportError: cannot import name 'tags' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/tags.py`**

```python
"""v232 mechanism tags (spec ### Layer 1, Mechanism tags).

Descriptive cut-offs, frozen by the spec (Claude's call 9). Every rule is one entry
of RULES, so the classifier stays table-driven (complexity < 15 per function).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Callable

from swingbot.core.analytics.metrics import close_reason_text

from . import sessions

TAGS = ("same_day_exit", "wick_missed", "both_levels_bar", "gap_through",
        "exit_outside_rth", "entry_outside_rth", "first_15min", "live_stop_moved",
        "levels_edited", "scaled_out", "time_stop", "earnings_in_window",
        "short_gap_against", "outcome_flip_live_better", "outcome_flip_live_worse")
SLIP_TAG_R = 0.05
SHORT_GAP_PCT = 0.03
FIRST_MINUTES = 15
LEVEL_TOLERANCE = 0.005
TIME_REASONS = ("timeout", "time_exit", "stall", "hold")
STOP_MARKERS = ("be_armed_session", "runner_floor_session")


@dataclasses.dataclass(frozen=True)
class TagInput:
    rec: object
    df: object
    fill_pos: int
    exit_pos: int | None
    live_risk: float
    r_live: float
    r_exit_only: float
    live_class: str
    exit_only_class: str


def _sign(t) -> int:
    return -1 if t.rec.side == "short" else 1


def _last(t) -> int:
    return len(t.df) - 1 if t.exit_pos is None else t.exit_pos


def _after_fill(t) -> range:
    return range(max(t.fill_pos + 1, 1), _last(t) + 1)


def _held_through(t) -> range:
    end = len(t.df) if t.exit_pos is None else t.exit_pos
    return range(t.fill_pos + 1, end)


def _bar(t, k: int) -> tuple[float, float, float, float]:
    row = t.df.iloc[k]
    return float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])


def _targets(plan: dict) -> list[float]:
    return [float(plan[key]) for key in ("tp1", "tp2") if plan.get(key) is not None]


def _differs(a, b) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) > LEVEL_TOLERANCE


def _marker(plan: dict) -> dt.date | None:
    days = [dt.date.fromisoformat(str(plan[k])[:10]) for k in STOP_MARKERS if plan.get(k)]
    return min(days) if days else None


def _stop_on(t, k: int) -> float:
    plan, marker = t.rec.plan, _marker(t.rec.plan)
    moved = plan.get("working_stop")
    if moved is not None and marker is not None and t.df.index[k].date() > marker:
        return float(moved)
    return float(plan["stop_loss"])


def _touches_stop(t, k: int, stop: float) -> bool:
    _, high, low, _ = _bar(t, k)
    return low <= stop if _sign(t) > 0 else high >= stop


def _holds_both(t, k: int) -> bool:
    _, high, low, _ = _bar(t, k)
    stop, sign = float(t.rec.plan["stop_loss"]), _sign(t)
    if not _touches_stop(t, k, stop):
        return False
    return any((high >= x) if sign > 0 else (low <= x) for x in _targets(t.rec.plan))


def _opens_beyond(t, k: int) -> bool:
    opened, sign = _bar(t, k)[0], _sign(t)
    if sign * (opened - float(t.rec.plan["stop_loss"])) <= 0:
        return True
    return any(sign * (opened - x) >= 0 for x in _targets(t.rec.plan))


def _gap_bar(t) -> int | None:
    return next((k for k in _after_fill(t) if _opens_beyond(t, k)), None)


def _short_gap(t) -> bool:
    if t.rec.side != "short":
        return False
    return any(_bar(t, k)[0] > _bar(t, k - 1)[3] * (1 + SHORT_GAP_PCT) for k in _after_fill(t))


def _same_day(t) -> bool:
    trade = t.rec.trade
    return sessions.ny_time(trade["opened_at"]).date() == sessions.ny_time(trade["closed_at"]).date()


def _early(t) -> bool:
    stamps = (t.rec.trade["opened_at"], t.rec.trade["closed_at"])
    minutes = [sessions.minutes_after_open(s) for s in stamps]
    return any(m is not None and m < FIRST_MINUTES for m in minutes)


def _stop_moved(t) -> bool:
    plan = t.rec.plan
    return _differs(plan.get("working_stop"), plan["stop_loss"]) or _marker(plan) is not None


def _edited(t) -> bool:
    plan, trade = t.rec.plan, t.rec.trade
    return (_differs(trade.get("stop_loss"), plan["stop_loss"])
            or _differs(trade.get("take_profit"), plan.get("tp1")))


def _scaled(t) -> bool:
    if any(float(leg.get("fraction", 1.0)) < 1.0 for leg in t.rec.trade.get("legs") or []):
        return True
    return any(h.get("reason") == "tp1_partial" for h in t.rec.plan.get("status_history") or [])


def _days_to_earnings(rec):
    for doc in (rec.trade, rec.journal or {}):
        value = (doc.get("risk_features") or {}).get("days_to_earnings")
        if value is not None:
            return value
    return None


def _earnings(t) -> bool:
    days = _days_to_earnings(t.rec)
    if days is None:
        return False
    trade = t.rec.trade
    held = sessions.sessions_apart(sessions.issue_session(trade["opened_at"]),
                                   sessions.issue_session(trade["closed_at"]))
    return 0 <= float(days) <= held


RULES: dict[str, Callable[[TagInput], bool]] = {
    "same_day_exit": _same_day,
    "wick_missed": lambda t: any(_touches_stop(t, k, _stop_on(t, k)) for k in _held_through(t)),
    "both_levels_bar": lambda t: any(_holds_both(t, k) for k in _after_fill(t)),
    "gap_through": lambda t: _gap_bar(t) is not None,
    "exit_outside_rth": lambda t: not sessions.in_regular_session(t.rec.trade["closed_at"]),
    "entry_outside_rth": lambda t: not sessions.in_regular_session(t.rec.trade["opened_at"]),
    "first_15min": _early,
    "live_stop_moved": _stop_moved,
    "levels_edited": _edited,
    "scaled_out": _scaled,
    "time_stop": lambda t: any(s in close_reason_text(t.rec.trade) for s in TIME_REASONS),
    "earnings_in_window": _earnings,
    "short_gap_against": _short_gap,
    "outcome_flip_live_better": lambda t: (t.live_class, t.exit_only_class) == ("win", "loss"),
    "outcome_flip_live_worse": lambda t: (t.live_class, t.exit_only_class) == ("loss", "win"),
}


def tags_for(t: TagInput) -> tuple[str, ...]:
    return tuple(name for name in TAGS if RULES[name](t))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_tags.py`
Expected: PASS, `0 failed`. If `test_the_base_fixture_carries_no_tag` names a tag, the fixture (not the rule) is wrong only when the rule table above says so; fix whichever disagrees with the table.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/tags.py tests/scout/test_reconcile_tags.py
git commit -m "feat(v232): table-driven mechanism tags"
```

### Task V232-8b: Slip distributions, gap detail and their tags

**Model:** sonnet — three small measurements over stored levels and bars, every rule frozen below.

**Files:**
- Modify: `scripts/reports/reconcile/tags.py` (created by V232-8)
- Modify: `tests/scout/test_reconcile_tags.py` (created by V232-8)

**Interfaces:**
- Consumes: V232-8's `TAGS`, `RULES`, `SLIP_TAG_R`, `TagInput`, `_sign`, `_bar`, `_gap_bar` and test helpers `_t`, `POSITIVE`, `LEGS`; `records.rehydrate` (V232-6); existing `metrics.close_reason_text` (already imported by V232-8).
- Produces (ledger V232-8, final; consumed by V232-9 and V232-13):
  - `TAGS` ends with `"entry_slip", "poll_fill"` (17 names, the ledger's order); `RULES` gains both.
  - `gap_detail(t) -> dict | None` (`gap_r`, `gap_pct`, `exit_vs_open_r`, `exit_vs_stop_r`); `entry_slip(t) -> tuple[float, float]` (bps, R; adverse positive); `poll_fill(t) -> tuple[float, float] | None` (bps, R; adverse positive).

**Rules this task freezes (spec `### Layer 1`: "`entry_slip` and `poll_fill` are distributions, not only tags"; `gap_through` "with the gap size in R and percent and the live exit price relative to that open and to the stop"):**

The exit price is the last leg's `exit_price`, else the trade's `exit_price`. `sign` = +1 long, -1 short.

| Tag | Rule |
|---|---|
| `entry_slip` | `abs(entry_slip(t)[1]) > SLIP_TAG_R`. |
| `poll_fill` | `poll_fill(t)` is not `None` and its R part's absolute value exceeds `SLIP_TAG_R`. |

| Distribution | Rule |
|---|---|
| `gap_detail` | The first `gap_through` bar `k`: `gap_r = sign * (Open[k] - Close[k-1]) / live_risk`, `gap_pct = (Open[k] / Close[k-1] - 1) * 100`, `exit_vs_open_r = sign * (exit - Open[k]) / live_risk`, `exit_vs_stop_r = sign * (exit - issued stop) / live_risk`; `None` without such a bar. |
| `entry_slip` | Planned entry = the rehydrated plan's `entry_price`, else its `trigger_price` (the `scan_replay._alert` convention). `adverse = sign * (fill - planned)`; returns `(adverse / planned * 1e4, adverse / live_risk)`. |
| `poll_fill` | The level the exit hit, from the close reason through `_LEVELS` (first match wins): `runner_be`, `trail` -> the final `working_stop`; `tp2` -> `tp2`; `tp1`, `target` -> `tp1`; `stop`, `loss` -> `working_stop` when set, else `stop_loss`. `adverse = sign * (level - exit)`; returns `(adverse / level * 1e4, adverse / live_risk)`; `None` for any other reason (manual, timeout) or a missing level or exit price. |

- [ ] **Step 1: Write the failing tests** — append to `tests/scout/test_reconcile_tags.py`:

```python

POSITIVE.update({
    "entry_slip": dict(trade={"entry": 100.3}),
    "poll_fill": dict(trade={"exit_price": 103.7}),
})


def test_all_seventeen_tags_have_a_rule_and_a_positive_fixture():
    assert len(tags.TAGS) == 17 and tags.TAGS[-2:] == ("entry_slip", "poll_fill")
    assert set(tags.RULES) == set(tags.TAGS) == set(POSITIVE)


@pytest.mark.parametrize("tag", ["entry_slip", "poll_fill"])
def test_the_slip_tags_fire_past_the_cut_off_only(tag):
    assert tag in tags.tags_for(_t(**POSITIVE[tag]))
    assert tag not in tags.tags_for(_t())        # 0.05 / 2.05 = 0.024R slip, 0R poll


def test_gap_detail_sizes_a_long_gap():
    gap = tags.gap_detail(_t(rows={3: (104.6, 104.8, 104.0, 104.2)}))
    risk = 2.05
    assert gap["gap_r"] == pytest.approx(4.1 / risk)
    assert gap["gap_pct"] == pytest.approx((104.6 / 100.5 - 1) * 100)
    assert gap["exit_vs_open_r"] == pytest.approx(-0.6 / risk)
    assert gap["exit_vs_stop_r"] == pytest.approx(6.0 / risk)
    assert tags.gap_detail(_t()) is None


def test_gap_detail_signs_a_short_gap_against_the_position():
    gap = tags.gap_detail(_t("bearish", rows={2: (102.5, 103.0, 102.0, 102.6)},
                             trade={"exit_price": 102.5}))
    assert gap["gap_r"] == pytest.approx(-(102.5 - 99.5) / 2.05)
    assert gap["exit_vs_stop_r"] == pytest.approx(-(102.5 - 102.0) / 2.05)


@pytest.mark.parametrize("direction,plan,fill,expected_bps,risk", [
    ("bullish", {}, 100.3, 30.0, 2.3),
    ("bearish", {}, 99.7, 30.0, 2.3),
    ("bullish", {"entry_type": "stop_entry", "entry_price": 101.4, "trigger_price": 101.0},
     101.2, 0.2 / 101.0 * 1e4, 3.2),
])
def test_entry_slip_is_adverse_positive_against_the_planned_entry(direction, plan, fill,
                                                                  expected_bps, risk):
    bps, r = tags.entry_slip(_t(direction, plan=plan, trade={"entry": fill}))
    assert bps == pytest.approx(expected_bps)
    assert r == pytest.approx(expected_bps / 1e4 * (101.0 if plan else 100.0) / risk)


@pytest.mark.parametrize("plan,trade,expected", [
    ({}, {"exit_price": 103.7}, (0.3 / 104.0 * 1e4, 0.3 / 2.05)),
    ({"working_stop": 100.05}, {"close_reason": "stop", "exit_price": 99.95},
     (0.1 / 100.05 * 1e4, 0.1 / 2.05)),
    ({"working_stop": 100.05}, {"legs": LEGS[:1] + [{**LEGS[1], "exit_price": 100.0}]},
     (0.05 / 100.05 * 1e4, 0.05 / 2.05)),
    ({}, {"close_reason": "manual", "exit_price": 101.0}, None),
    ({}, {"close_reason": "timeout", "exit_price": 101.0}, None),
])
def test_poll_fill_measures_the_exit_against_the_level_it_hit(plan, trade, expected):
    got = tags.poll_fill(_t(plan=plan, trade=trade))
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)
```

`test_each_tag_fires_on_its_positive_case` (V232-8) is parametrized over `POSITIVE` at collection time, before this block's `update` runs, so the two new tags get their own positive test above.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_tags.py`
Expected: FAIL — `AttributeError: module 'reconcile.tags' has no attribute 'gap_detail'` (and `entry_slip`, `poll_fill`); `test_all_seventeen_tags_have_a_rule_and_a_positive_fixture` fails on `len(tags.TAGS) == 15`.

- [ ] **Step 3: Implement** — in `scripts/reports/reconcile/tags.py`:

1. Import `records`: `from . import records, sessions` (replaces `from . import sessions`); docstring first line becomes `"""v232 mechanism tags and slip distributions (spec ### Layer 1, Mechanism tags).`.
2. Append the two names to `TAGS`, after `"outcome_flip_live_worse"`: `"entry_slip", "poll_fill")`.
3. Add the level table under `STOP_MARKERS`:

```python
_LEVELS = (("runner_be", "working_stop"), ("trail", "working_stop"), ("tp2", "tp2"),
           ("tp1", "tp1"), ("target", "tp1"), ("stop", "stop"), ("loss", "stop"))
```

4. Add two entries at the end of `RULES` (lambdas, so the functions below may follow the dict):

```python
    "entry_slip": lambda t: abs(entry_slip(t)[1]) > SLIP_TAG_R,
    "poll_fill": lambda t: _poll_tag(t),
```

5. Append to the end of the module:

```python
def _exit_price(trade: dict) -> float | None:
    legs = [leg for leg in trade.get("legs") or [] if leg.get("exit_price") is not None]
    price = legs[-1]["exit_price"] if legs else trade.get("exit_price")
    return None if price is None else float(price)


def _poll_tag(t) -> bool:
    measured = poll_fill(t)
    return measured is not None and abs(measured[1]) > SLIP_TAG_R


def gap_detail(t: TagInput) -> dict | None:
    k = _gap_bar(t)
    exit_price = _exit_price(t.rec.trade)
    if k is None or exit_price is None:
        return None
    sign, opened, prior = _sign(t), _bar(t, k)[0], _bar(t, k - 1)[3]
    stop = float(t.rec.plan["stop_loss"])
    return {"gap_r": sign * (opened - prior) / t.live_risk,
            "gap_pct": (opened / prior - 1.0) * 100.0,
            "exit_vs_open_r": sign * (exit_price - opened) / t.live_risk,
            "exit_vs_stop_r": sign * (exit_price - stop) / t.live_risk}


def entry_slip(t: TagInput) -> tuple[float, float]:
    plan, _ = records.rehydrate(t.rec.plan)
    planned = float(plan.entry_price if plan.entry_price is not None else plan.trigger_price)
    adverse = _sign(t) * (float(t.rec.trade["entry"]) - planned)
    return adverse / planned * 1e4, adverse / t.live_risk


def _level(reason: str, plan: dict) -> float | None:
    key = next((level for word, level in _LEVELS if word in reason), None)
    if key == "stop":
        key = "working_stop" if plan.get("working_stop") is not None else "stop_loss"
    value = plan.get(key) if key else None
    return None if value is None else float(value)


def poll_fill(t: TagInput) -> tuple[float, float] | None:
    level = _level(close_reason_text(t.rec.trade), t.rec.plan)
    exit_price = _exit_price(t.rec.trade)
    if level is None or exit_price is None:
        return None
    adverse = _sign(t) * (level - exit_price)
    return adverse / level * 1e4, adverse / t.live_risk
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_tags.py`
Expected: PASS, `0 failed` (V232-8's tests included: the base fixture still carries no tag).
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/tags.py tests/scout/test_reconcile_tags.py
git commit -m "feat(v232): entry slip, poll fill and gap detail distributions with their tags"
```
