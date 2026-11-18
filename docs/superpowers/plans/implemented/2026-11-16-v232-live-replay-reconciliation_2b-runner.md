# v232 — Live versus replay reconciliation: Part 2b, layer 1 runner

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-9" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) (binding: `## Clarifications from the code brief`)
**Index:** [2026-11-16-v232-live-replay-reconciliation_0-index.md](2026-11-16-v232-live-replay-reconciliation_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below. Part 2b continues [Part 2](2026-11-16-v232-live-replay-reconciliation_2-layer1.md) (moved out for the 1500-line cap; its Review Focus covers these tasks too).

Tasks V232-9 and V232-9b: the per-trade row (`TradeRow`) built from one live record and its raw bars, then the checkpointed runner over the whole export.

Consumed from earlier tasks: `records` (V232-6), `layer1` (V232-7, V232-7b), `tags` (V232-8, V232-8b), `raw_bars.refusal` / `REFUSALS` (V232-4b), `sessions` (V232-5).

Test imports, every task: `sys.path.insert(0, str(REPO / "scripts" / "reports"))`, then `from reconcile import <module>`, with `REPO = Path(__file__).resolve().parents[2]`.

---

# Phase 2 — Layer 1 (continued)

### Task V232-9: The per-trade row

**Model:** sonnet — assembly of finished parts into one row per plan, with the holdout boundary spelled out below.

**Files:**
- Create: `scripts/reports/reconcile/layer1_run.py`
- Create: `tests/scout/test_reconcile_layer1_run.py`

**Interfaces:**
- Consumes: `records.LiveRecord`, `Export`, `class_of`, `era_of`, `ledger_of`, `unfilled_reason` (V232-6); `layer1.FILL_MODELS`, `live_risk`, `r_live`, `live_cost_r`, `outcome_class`, `bar_position` (V232-7), `layer1.score`, `effects`, `would_fill` (V232-7b); `tags.TagInput`, `tags_for` (V232-8), `gap_detail`, `entry_slip`, `poll_fill` (V232-8b); `raw_bars.refusal(raw, split, *, start, last_exit)`, `raw_bars.REFUSALS` (V232-4b); `sessions.stamp_source`, `issue_session`, `issue_bucket`, `ny_time` (V232-5).
- Produces (ledger V232-9, final; consumed by V232-9b, V232-12, V232-13, V232-14, V232-15):
  - `layer1_run.REFUSALS = raw_bars.REFUSALS + ("no_journal", "zero_risk", "no_fill_bar")`.
  - `@dataclass(frozen=True) TradeRow(trade_id, plan_id, ticker, strategy, horizon_key, ledger, side, era, klass, refusal, entry_date, stamp_source, issue_bucket, r_live_gross, cost_r, r_live_net, values: dict, effects: dict, tags: tuple, gap: dict | None, entry_slip: tuple | None, poll_fill: tuple | None, live_class, unfilled_reason, would_fill: dict)` with `to_dict()`, `TradeRow.from_dict(d)` and property `.scored` (`klass == "closed"` and `refusal is None`).
  - `row_for(rec, bars, *, frictions, start: dt.date | None = None, last_exit: dt.date | None = None) -> TradeRow` — `bars(ticker) -> tuple[raw_df | None, split_df | None]`. The two defaulted keywords extend the ledger signature compatibly: `run_layer1` (V232-9b) passes the window start and the ticker's last live exit, so the refusal is per ticker as the spec says; without them the trade's own first session and exit date are used.
- V232-9b adds `checkpoint.JsonlCheckpoint` and `run_layer1` (split out for the 20 KB task cap; the ledger row's signatures are unchanged).
- Test helpers V232-9b reuses: `_rec`, `_bars`, `BARS`, `FRICTIONS`, `START`, `WIN`, `_frame`.

**Rules this task freezes (spec `### Populations`, `### Holdout discipline`):**

| Row class (`records.class_of`) | What the row carries |
|---|---|
| every row | `trade_id` (trade doc `id`, else None), `plan_id`, `ticker`, `strategy`, `horizon_key` (plan doc), `ledger`, `side`, `era`, `klass`, `entry_date` (New York date of `opened_at`, else the issue session; ISO), `stamp_source` and `issue_bucket` (from `stamp_source(plan)`). |
| `unfilled` | `unfilled_reason`; `would_fill = {model: bool \| None}` for both fill models (`None` for every model when the ticker's bars are refused, `refusal` set). Nothing else. |
| `still_open` | Nothing beyond the common fields: no live R, no backtest field. |
| `closed` / `manual` without a journal doc | `refusal = "no_journal"`; no live R. |
| `closed` / `manual` with `live_risk == 0` | `refusal = "zero_risk"`; no live R. |
| `manual` | `r_live_gross`, `cost_r`, `r_live_net = gross - cost`, `live_class`; no backtest field and no bar refusal (manual closes are their own live-net line). |
| `closed`, bars refused | live R and `live_class`; `refusal` = `raw_bars.refusal(raw, split, start=start or the trade's first session, last_exit=last_exit or the trade's exit date)`. |
| `closed`, a signal or fill bar missing | live R; `refusal = "no_fill_bar"` (`layer1.score` raised `ValueError`). |
| `closed`, scored | live R, `live_class = outcome_class(journal.outcome, r_live_gross)`; `values = {model: asdict(layer1.score(...))}`; `effects = {model: layer1.effects(r_live_gross, values)}` (gross against gross); `tags`, `gap`, `entry_slip`, `poll_fill` from one `TagInput` built on the **v1** values (`exit_pos` = bar of `issue_session(closed_at)`). |

Holdout: only a `closed` scored row ever carries a backtest R, an outcome label or a tag; `TradeRow` has no `outcome`, `r_multiple` or `exit_date` field.

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-9 / V232-9b: per-trade rows, the checkpoint and the layer 1 runner."""
import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer1_run, records  # noqa: E402

FRICTIONS = {"slippage_bps": 5.0, "commission_per_trade": 1.0,
             "commission_risk_basis": 100.0, "min_risk_fraction": 0.0}
START = dt.date(2026, 10, 5)
F = (100.0, 100.6, 99.6, 100.0)
WIN = [F, (100.0, 100.8, 99.6, 100.5), (100.5, 101.0, 100.0, 100.8),
       (100.8, 104.5, 100.5, 104.0)] + [(104.0, 104.4, 103.6, 104.0)] * 6


def _frame(rows, start="2026-10-05"):
    return make_ohlcv(rows, start=start)


def _mirror(rows):
    return [(200 - o, 200 - lo, 200 - hi, 200 - c) for o, hi, lo, c in rows]


def _split_frame():
    split = _frame(WIN)
    split.iloc[5:, :4] = split.iloc[5:, :4] * 0.5          # a 2:1 split inside the window
    return split


BARS = {"AAA": (_frame(WIN), _frame(WIN)),
        "BBB": (_frame(_mirror(WIN)), _frame(_mirror(WIN))),
        "CCC": (_frame(WIN), _split_frame()),
        "DDD": (_frame(WIN[:2]), _frame(WIN[:2])),                          # ends 10-06
        "EEE": (_frame(WIN[2:], start="2026-10-07"), _frame(WIN[2:], start="2026-10-07"))}


def _bars(ticker):
    return BARS.get(ticker, (None, None))


def _rec(plan_id="P1", ticker="AAA", direction="bullish", klass="closed", **plan_kw):
    long = direction == "bullish"
    plan = dict(plan_id=plan_id, ticker=ticker, created_at="2026-10-06T15:00:00+00:00",
                source="confluence", strategy="RSI", horizon_key="2w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
                stop_loss=98.0 if long else 102.0, tp1=104.0 if long else 96.0,
                tp1_fraction=1.0, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=[],
                issued_at="2026-10-06T15:00:00+00:00")
    plan.update(plan_kw)
    doc = plan_to_dict(TradePlanV2(**plan))
    trade = {"id": f"T-{plan_id}", "plan_id": plan_id, "ticker": ticker, "direction": direction,
             "entry": 100.2 if long else 99.8, "stop_loss": doc["stop_loss"],
             "take_profit": doc["tp1"], "opened_at": "2026-10-06T15:01:00+00:00",
             "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0 if long else 96.0,
             "close_reason": "tp1", "legs": [], "ledger": "weak"}
    journal = {"trade_id": trade["id"], "outcome": "win", "r_realized": 1.727}
    if klass == "manual":
        trade["close_reason"] = "manual"
    if klass == "still_open":
        trade, journal = {**trade, "closed_at": None, "exit_price": None}, None
    if klass == "unfilled":
        trade = journal = None
    if klass == "no_journal":
        journal = None
    return records.LiveRecord(plan_id, ticker, direction, doc, trade, journal)


def _row(rec, **kw):
    return layer1_run.row_for(rec, _bars, frictions=FRICTIONS, **kw)


OUTCOME_KEYS = {"values", "effects", "gap", "entry_slip", "poll_fill", "live_class"}


def test_a_scored_row_carries_both_fill_models_and_telescopes():
    row = _row(_rec())
    assert row.scored and row.refusal is None and row.klass == "closed"
    assert set(row.values) == set(row.effects) == {"v1", "v2"}
    assert row.r_live_net == pytest.approx(row.r_live_gross - row.cost_r)
    for model, v in row.values.items():
        eff = row.effects[model]
        assert row.r_live_gross - v["r_as_backtest"] == pytest.approx(eff["exit"] + eff["entry"])
    assert row.live_class == "win" and row.entry_date == "2026-10-06"
    assert (row.ledger, row.side, row.era, row.stamp_source) == ("weak", "long", "headline",
                                                                 "issued_at")
    assert row.entry_slip is not None and row.poll_fill is not None


def test_a_short_is_scored_on_its_mirrored_bars():
    row = _row(_rec("P2", "BBB", "bearish"))
    assert row.scored and row.side == "short" and row.values["v1"]["exit_only_outcome"] == "win"


@pytest.mark.parametrize("klass", ["still_open", "unfilled"])
def test_unscored_rows_carry_no_backtest_outcome(klass):
    row = _row(_rec(klass=klass, status=PlanStatus.CANCELLED,
                    status_history=[{"status": "CANCELLED", "reason": "expired", "at": "x"}]))
    assert not row.scored
    assert (row.values, row.effects, row.tags) == ({}, {}, ())
    assert all(getattr(row, k) in (None, {}, ()) for k in OUTCOME_KEYS)
    assert (row.r_live_gross, row.r_live_net) == (None, None)
    names = {f.name for f in dataclasses.fields(layer1_run.TradeRow)}
    assert not names & {"outcome", "r_multiple", "exit_date"}
    if klass == "unfilled":
        assert row.unfilled_reason == "expired"
        assert set(row.would_fill) == {"v1", "v2"}
        assert all(v in (True, False, None) for v in row.would_fill.values())
    else:
        assert row.would_fill == {} and row.unfilled_reason is None


def test_an_unfilled_plan_on_refused_bars_has_no_would_fill():
    row = _row(_rec("P5", "CCC", klass="unfilled"), start=START)
    assert row.refusal == "split_in_window"
    assert row.would_fill == {"v1": None, "v2": None}


def test_a_manual_close_keeps_live_r_only():
    row = _row(_rec(klass="manual"))
    assert row.klass == "manual" and not row.scored and row.refusal is None
    assert row.r_live_net is not None and row.values == {} and row.tags == ()


@pytest.mark.parametrize("ticker,kw,klass,expected", [
    ("CCC", {"start": START}, "closed", "split_in_window"),
    ("DDD", {}, "closed", "bars_end_early"),
    ("ZZZ", {}, "closed", "no_bars"),
    ("EEE", {"start": START}, "closed", "no_fill_bar"),
    ("AAA", {}, "no_journal", "no_journal"),
])
def test_refusals_keep_the_live_net_where_it_exists(ticker, kw, klass, expected):
    row = _row(_rec("PX", ticker, klass=klass), **kw)
    assert row.refusal == expected and expected in layer1_run.REFUSALS
    assert not row.scored and row.values == {}
    assert (row.r_live_net is None) == (expected == "no_journal")


def test_a_fill_on_the_issued_stop_is_refused_zero_risk():
    rec = _rec()
    rec = dataclasses.replace(rec, trade={**rec.trade, "entry": 98.0})
    row = _row(rec)
    assert row.refusal == "zero_risk" and row.r_live_net is None


def test_a_row_survives_a_json_round_trip():
    row = _row(_rec())
    again = layer1_run.TradeRow.from_dict(json.loads(json.dumps(row.to_dict())))
    assert again == row and isinstance(again.tags, tuple)

```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1_run.py`
Expected: FAIL — `ImportError: cannot import name 'layer1_run' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/layer1_run.py`**

```python
"""v232 layer 1 runner: one TradeRow per exported plan (spec ### Populations, ### Layer 1).

Only a closed, scored row carries backtest values, effects and tags. Unfilled rows keep
would_fill booleans; still-open rows keep nothing from the backtest (holdout).
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from . import layer1, raw_bars, records, sessions, tags

REFUSALS = raw_bars.REFUSALS + ("no_journal", "zero_risk", "no_fill_bar")


@dataclasses.dataclass(frozen=True)
class TradeRow:
    trade_id: str | None
    plan_id: str
    ticker: str
    strategy: str | None
    horizon_key: str | None
    ledger: str
    side: str
    era: str
    klass: str
    refusal: str | None
    entry_date: str
    stamp_source: str
    issue_bucket: str
    r_live_gross: float | None
    cost_r: float | None
    r_live_net: float | None
    values: dict
    effects: dict
    tags: tuple
    gap: dict | None
    entry_slip: tuple | None
    poll_fill: tuple | None
    live_class: str | None
    unfilled_reason: str | None
    would_fill: dict

    @property
    def scored(self) -> bool:
        return self.klass == "closed" and self.refusal is None

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        for key in ("tags", "entry_slip", "poll_fill"):
            out[key] = None if out[key] is None else list(out[key])
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "TradeRow":
        data = {f.name: d.get(f.name) for f in dataclasses.fields(cls)}
        data["tags"] = tuple(data["tags"] or ())
        for key in ("entry_slip", "poll_fill"):
            data[key] = None if data[key] is None else tuple(data[key])
        for key in ("values", "effects", "would_fill"):
            data[key] = data[key] or {}
        return cls(**data)


def _common(rec) -> dict:
    stamp, source = sessions.stamp_source(rec.plan)
    trade = rec.trade
    entry_day = (sessions.ny_time(trade["opened_at"]).date() if trade
                 else sessions.issue_session(stamp))
    return dict(trade_id=trade.get("id") if trade else None, plan_id=rec.plan_id,
                ticker=rec.ticker, strategy=rec.plan.get("strategy"),
                horizon_key=rec.plan.get("horizon_key"), ledger=records.ledger_of(rec),
                side=rec.side, era=records.era_of(rec), klass=records.class_of(rec),
                refusal=None, entry_date=entry_day.isoformat(), stamp_source=source,
                issue_bucket=sessions.issue_bucket(stamp), r_live_gross=None, cost_r=None,
                r_live_net=None, values={}, effects={}, tags=(), gap=None, entry_slip=None,
                poll_fill=None, live_class=None, unfilled_reason=None, would_fill={})


def _first_day(rec) -> dt.date:
    signal = sessions.issue_session(sessions.stamp_source(rec.plan)[0])
    if rec.trade is None:
        return signal
    return min(signal, sessions.issue_session(rec.trade["opened_at"]))


def _exit_day(rec) -> dt.date | None:
    closed = (rec.trade or {}).get("closed_at")
    return sessions.ny_time(closed).date() if closed else None


def _unfilled(rec, bars, row: dict, start) -> dict:
    raw, split = bars(rec.ticker)
    refused = raw_bars.refusal(raw, split, start=start or _first_day(rec), last_exit=None)
    fills = {m: None if refused else layer1.would_fill(rec, raw, m) for m in layer1.FILL_MODELS}
    return {**row, "refusal": refused, "unfilled_reason": records.unfilled_reason(rec),
            "would_fill": fills}


def _live(rec, row: dict, frictions: dict) -> dict:
    gross = layer1.r_live(rec)
    cost = layer1.live_cost_r(rec, frictions)
    return {**row, "r_live_gross": gross, "cost_r": cost, "r_live_net": gross - cost,
            "live_class": layer1.outcome_class(rec.journal.get("outcome"), gross)}


def _scored(rec, raw, row: dict) -> dict:
    values = {m: layer1.score(rec, raw, m) for m in layer1.FILL_MODELS}
    gross, v1 = row["r_live_gross"], values["v1"]
    fill_pos = layer1.bar_position(raw, sessions.issue_session(rec.trade["opened_at"]))
    exit_pos = layer1.bar_position(raw, sessions.issue_session(rec.trade["closed_at"]))
    t = tags.TagInput(rec, raw, fill_pos, exit_pos, layer1.live_risk(rec), gross,
                      v1.r_exit_only, row["live_class"], v1.exit_only_class)
    return {**row, "values": {m: dataclasses.asdict(v) for m, v in values.items()},
            "effects": {m: layer1.effects(gross, v) for m, v in values.items()},
            "tags": tags.tags_for(t), "gap": tags.gap_detail(t),
            "entry_slip": tags.entry_slip(t), "poll_fill": tags.poll_fill(t)}


def _closed(rec, bars, row: dict, frictions: dict, start, last_exit) -> dict:
    if rec.journal is None:
        return {**row, "refusal": "no_journal"}
    try:
        layer1.live_risk(rec)
    except ValueError:
        return {**row, "refusal": "zero_risk"}
    row = _live(rec, row, frictions)
    if row["klass"] == "manual":
        return row
    raw, split = bars(rec.ticker)
    refused = raw_bars.refusal(raw, split, start=start or _first_day(rec),
                               last_exit=last_exit or _exit_day(rec))
    if refused:
        return {**row, "refusal": refused}
    try:
        return _scored(rec, raw, row)
    except ValueError:
        return {**row, "refusal": "no_fill_bar"}


def row_for(rec, bars, *, frictions: dict, start: dt.date | None = None,
            last_exit: dt.date | None = None) -> TradeRow:
    """One plan's row; `bars(ticker)` returns (raw frame, split-adjusted frame)."""
    row = _common(rec)
    if row["klass"] == "unfilled":
        return TradeRow(**_unfilled(rec, bars, row, start))
    if row["klass"] == "still_open":
        return TradeRow(**row)
    return TradeRow(**_closed(rec, bars, row, frictions, start, last_exit))
```

`layer1.score` raises `ValueError` for a missing signal or fill bar (V232-7b); the `try` around `_scored` turns exactly that into `no_fill_bar`. A `ValueError` from anywhere else inside `_scored` is a bug, and it would be mislabelled the same way: keep the `try` body to the one `_scored` call, as written.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1_run.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/layer1_run.py tests/scout/test_reconcile_layer1_run.py
git commit -m "feat(v232): per-trade layer 1 rows with refusals and the holdout boundary"
```

### Task V232-9b: The JSONL checkpoint and the layer 1 runner

**Model:** sonnet — an append-only checkpoint and a resumable loop, the repo's long-run rule applied as written.

**Files:**
- Create: `scripts/reports/reconcile/checkpoint.py`
- Modify: `scripts/reports/reconcile/layer1_run.py` (created by V232-9)
- Modify: `tests/scout/test_reconcile_layer1_run.py` (created by V232-9)

**Interfaces:**
- Consumes: V232-9's `TradeRow`, `row_for`, `_exit_day` and test helpers `_rec`, `_bars`, `FRICTIONS`, `START`; `records.Export` (V232-6).
- Produces (ledger V232-9, final; consumed by V232-11, which may checkpoint with it, and V232-15, the CLI):
  - `checkpoint.JsonlCheckpoint(path: Path)`: `done() -> set[str]`, `append(key: str, row: dict) -> None`, `rows() -> list[dict]`, `.path`.
  - `layer1_run.PROGRESS_EVERY = 25`; `run_layer1(export, bars, checkpoint, *, frictions, start: dt.date, out=print) -> list[TradeRow]` (key = `plan_id`; rows returned in export order).

**Rules this task freezes (working-conventions.md, Long runs must checkpoint; Global Constraints "Long run"):**

The checkpoint writes `{"key": key, "row": row}` per line with `sort_keys=True` and `allow_nan=False` (a NaN R fails the run instead of poisoning a sum), flushes and `os.fsync`s each line; on open it truncates a torn last line (no trailing newline); a malformed line anywhere else raises `ValueError` naming its line number; `rows()` keeps the last row per key in first-seen order.

`run_layer1` loads each ticker's bars lazily and once (a ticker whose plans are all done is never loaded) and passes `start` and the ticker's **latest** live exit date (over all its records) to `row_for`, so a bar refusal applies to the whole ticker as the spec says. Each finished row is appended before the next plan starts. It prints one line before the loop (`already scored`, `to go`) and one every `PROGRESS_EVERY` rows and at the last, with the percent of the export done. It returns `TradeRow.from_dict` of the checkpoint's rows in export order, so a resumed run and a fresh one return equal lists.

- [ ] **Step 1: Write the failing tests** — append to `tests/scout/test_reconcile_layer1_run.py`:

```python

from reconcile import checkpoint  # noqa: E402

def test_the_checkpoint_appends_and_reads_back(tmp_path):
    ck = checkpoint.JsonlCheckpoint(tmp_path / "sub" / "rows.jsonl")
    assert ck.done() == set() and ck.rows() == []
    ck.append("P1", {"a": 1})
    ck.append("P2", {"a": 2})
    ck.append("P1", {"a": 3})
    assert ck.done() == {"P1", "P2"} and ck.rows() == [{"a": 3}, {"a": 2}]
    assert ck.path.read_bytes().endswith(b"\n")


def test_the_checkpoint_drops_a_torn_last_line_on_open(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"key": "P1", "row": {"a": 1}}\n{"key": "P2", "ro', encoding="utf-8")
    ck = checkpoint.JsonlCheckpoint(path)
    assert ck.done() == {"P1"}
    ck.append("P2", {"a": 2})
    assert [json.loads(x)["key"] for x in path.read_text(encoding="utf-8").splitlines()] == [
        "P1", "P2"]


def test_a_malformed_middle_line_raises(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"key": "P1", "row": {}}\nnot json\n{"key": "P2", "row": {}}\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        checkpoint.JsonlCheckpoint(path).done()


def test_the_checkpoint_refuses_nan(tmp_path):
    with pytest.raises(ValueError):
        checkpoint.JsonlCheckpoint(tmp_path / "rows.jsonl").append("P1", {"r": float("nan")})


def _export(*recs):
    return records.Export(records=tuple(recs), rejections=(), watchlist=(), deploys=())


def _book():
    return _export(_rec("P1", "AAA"), _rec("P2", "BBB", "bearish"),
                   _rec("P3", "AAA", klass="unfilled"), _rec("P4", "CCC"))


class Counting:
    def __init__(self):
        self.calls = []

    def __call__(self, ticker):
        self.calls.append(ticker)
        return _bars(ticker)


def _run(path, export=None, bars=None, out=None):
    return layer1_run.run_layer1(export or _book(), bars or _bars,
                                 checkpoint.JsonlCheckpoint(path), frictions=FRICTIONS,
                                 start=START, out=(out.append if out is not None else print))


def test_run_layer1_returns_rows_in_export_order_and_checkpoints_each(tmp_path):
    path = tmp_path / "trade-rows.jsonl"
    rows = _run(path)
    assert [r.plan_id for r in rows] == ["P1", "P2", "P3", "P4"]
    assert checkpoint.JsonlCheckpoint(path).done() == {"P1", "P2", "P3", "P4"}
    assert [r.scored for r in rows] == [True, True, False, False]
    assert rows[3].refusal == "split_in_window"


def test_bars_load_once_per_ticker(tmp_path):
    bars = Counting()
    _run(tmp_path / "rows.jsonl", bars=bars)
    assert sorted(bars.calls) == ["AAA", "BBB", "CCC"]


def test_a_restart_skips_finished_trades_and_returns_equal_rows(tmp_path):
    path = tmp_path / "rows.jsonl"
    first = _run(path)
    bars = Counting()
    assert _run(path, bars=bars) == first
    assert bars.calls == []


def test_a_torn_last_line_is_rescored(tmp_path):
    path = tmp_path / "rows.jsonl"
    first = _run(path)
    data = path.read_bytes()
    last = data.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    path.write_bytes(data[:len(data) - 1 - len(last) // 2])          # killed mid-line
    bars = Counting()
    assert _run(path, bars=bars) == first
    assert bars.calls == ["CCC"]                                      # only P4 again
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and all(json.loads(line) for line in lines)


def test_a_refusal_follows_the_tickers_latest_exit(tmp_path):
    early = _rec("Q1", "DDD")
    early = dataclasses.replace(early, trade={**early.trade,
                                              "closed_at": "2026-10-06T19:00:00+00:00"})
    rows = _run(tmp_path / "rows.jsonl", export=_export(early, _rec("Q2", "DDD")))
    assert [r.refusal for r in rows] == ["bars_end_early", "bars_end_early"]


def test_progress_reports_the_percent_done(tmp_path):
    out = []
    _run(tmp_path / "rows.jsonl", out=out)
    assert "4 to go" in out[0] and out[-1].endswith("4/4 trades (100%)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1_run.py`
Expected: FAIL — `ImportError: cannot import name 'checkpoint' from 'reconcile'` (collection error).

- [ ] **Step 3a: Implement `scripts/reports/reconcile/checkpoint.py`**

```python
"""v232: an append-only JSONL checkpoint, one fsynced line per finished unit.

working-conventions.md, Long runs must checkpoint: a restart reads done() and skips
those units. A torn last line (the run was killed mid-write) is dropped on open.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class JsonlCheckpoint:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._repair()

    def _repair(self) -> None:
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        if data and not data.endswith(b"\n"):
            with open(self.path, "r+b") as fh:
                fh.truncate(data.rfind(b"\n") + 1)

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{self.path}: line {number} is not JSON") from exc
            entries.append(entry)
        return entries

    def done(self) -> set[str]:
        return {entry["key"] for entry in self._entries()}

    def append(self, key: str, row: dict) -> None:
        line = json.dumps({"key": key, "row": row}, sort_keys=True, allow_nan=False) + "\n"
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def rows(self) -> list[dict]:
        latest: dict[str, dict] = {}
        for entry in self._entries():
            latest[entry["key"]] = entry["row"]
        return list(latest.values())
```

`rows()` keeps first-seen order: re-assigning an existing dict key keeps its position.

- [ ] **Step 3b: Add the runner** — append to `scripts/reports/reconcile/layer1_run.py`:

```python
PROGRESS_EVERY = 25


def _last_exits(export) -> dict[str, dt.date]:
    latest: dict[str, dt.date] = {}
    for rec in export.records:
        day = _exit_day(rec)
        if day is not None and (rec.ticker not in latest or day > latest[rec.ticker]):
            latest[rec.ticker] = day
    return latest


def _memo(bars):
    cache: dict = {}

    def get(ticker: str):
        if ticker not in cache:
            cache[ticker] = bars(ticker)
        return cache[ticker]
    return get


def run_layer1(export, bars, checkpoint, *, frictions: dict, start: dt.date,
               out=print) -> list[TradeRow]:
    """Score every exported plan once, appending each row; a restart skips finished plans."""
    cached, last_exits = _memo(bars), _last_exits(export)
    total = len(export.records)
    done = checkpoint.done()
    todo = [rec for rec in export.records if rec.plan_id not in done]
    out(f"layer 1: {total - len(todo)}/{total} trades already scored, {len(todo)} to go")
    for n, rec in enumerate(todo, 1):
        row = row_for(rec, cached, frictions=frictions, start=start,
                      last_exit=last_exits.get(rec.ticker))
        checkpoint.append(rec.plan_id, row.to_dict())
        if n % PROGRESS_EVERY == 0 or n == len(todo):
            finished = total - len(todo) + n
            out(f"layer 1: {finished}/{total} trades ({100.0 * finished / total:.0f}%)")
    by_plan = {d["plan_id"]: TradeRow.from_dict(d) for d in checkpoint.rows()}
    return [by_plan[rec.plan_id] for rec in export.records if rec.plan_id in by_plan]
```

`layer1_run` never imports the `checkpoint` module, so the parameter of that name shadows nothing; the caller builds the `JsonlCheckpoint`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer1_run.py`
Expected: PASS, `0 failed` (V232-9's tests included).
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/checkpoint.py scripts/reports/reconcile/layer1_run.py tests/scout/test_reconcile_layer1_run.py
git commit -m "feat(v232): JSONL checkpoint and the resumable layer 1 runner"
```
