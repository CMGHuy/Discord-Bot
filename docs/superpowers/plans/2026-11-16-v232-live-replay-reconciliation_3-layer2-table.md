# v232 — Live versus replay reconciliation: Part 3, layer 2 and the table

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-11" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) (binding: `## Clarifications from the code brief`)
**Index:** [2026-11-16-v232-live-replay-reconciliation_0-index.md](2026-11-16-v232-live-replay-reconciliation_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below.

Tasks V232-10..V232-12: the layer 2 adapter, matching and selection counts (V232-10), the checkpointed runner over the unchanged `scan_replay` (V232-11), and the per-direction reconciliation table with its self-check (V232-12).

Consumed from earlier parts (ledger rows, created there): `records.Export`, `LiveRecord`, `era_of`, `rehydrate` (V232-6); `sessions.stamp_source`, `issue_session`, `issue_bucket`, `ny_time`, `sessions_apart`, `ISSUE_BUCKETS` (V232-5); `layer1_run.TradeRow` and its `.scored` (V232-9); the row's `values[model]` keys `r_as_backtest`, `backtest_no_fill` and `effects[model]` keys `exit`, `entry` (V232-7b, `layer1.effects` returns `{"exit": r_live - r_exit_only, "entry": None | r_exit_only - r_as_backtest}`).

Test imports, every task: `sys.path.insert(0, str(REPO / "scripts" / "reports"))`, then `from reconcile import <module>`, with `REPO = Path(__file__).resolve().parents[2]`.

## Review Focus

- **An outcome field reaching layer 2 storage.** `ReplaySignal` has no outcome field, `from_dict` refuses one, and the lane files are checked for the three keys; pinned in V232-10 (`test_from_dict_refuses_an_outcome_field`) and V232-11 (`test_lane_files_carry_no_outcome_key`).
- **A `created_at`-sourced plan counted as an outside-session issue** (Handoff). Its bucket is `created_at`, apart from the four issue buckets, and it never counts as unexplained; pinned in V232-10 (`test_each_issue_time_bucket`, `test_selection_counts_per_side_and_era_with_measured_zeros`).
- **A per-ticker layer 2 replay.** `scan_replay` is cross-sectional per decision date (Handoff); the runner checkpoints per lane, never per ticker; pinned in V232-11 (`test_a_finished_lane_is_read_back_not_replayed`).
- **A table line that is not a per-trade sum, or a plug.** Every line is summed from rows and `self_check` re-derives every line; pinned in V232-12 (`test_self_check_fails_on_a_tampered_effect`, `test_self_check_fails_on_a_tampered_live_net`).
- **Rows with no live R** (`no_journal`, `zero_risk`; Handoff). They enter the not-scoreable line's `N` and `book_net`'s `N` at 0R, both totals exclude them, and the label names the count; pinned in V232-12 (`test_rows_without_live_r_are_counted_not_summed`).

---

# Phase 3 — Layer 2 and the table

### Task V232-10: Layer 2 adapter, matching and selection counts

**Model:** sonnet — pure functions over fixed dataclasses; the match and the holdout rule are spelled out.

**Files:**
- Create: `scripts/reports/reconcile/layer2.py`
- Create: `tests/scout/test_reconcile_layer2.py`

**Interfaces:**
- Consumes: `records.Export`, `LiveRecord`, `era_of`, `rehydrate` and the test helper `tests.scout.test_reconcile_records._plan_doc` (V232-6; precedent for a sibling-test import: `test_autopsy_rows.py`); `sessions.*` (V232-5); `autopsy.eras.ERA_BOUNDARY_UTC`, `scan_replay.ReplayAlert` (exist). `rows_by_plan` values are `TradeRow`s (V232-9); only `.r_live_net` is read.
- Produces: every name in the ledger row, plus `CREATED_AT_BUCKET = "created_at"`, `LIVE_ONLY_BUCKETS = sessions.ISSUE_BUCKETS + ("created_at",)`, `SIDES = ("long", "short")`, `ERAS = ("headline", "earlier")`. `ReplaySignal.from_dict` raises `ValueError` naming any `OUTCOME_FIELDS` key. `MatchResult.matched` holds `(LivePlan, ReplaySignal)` pairs.
- `selection_counts(result, export)` returns `counts[side][era]` for every side and era, zeros included (measured zeros, known-traps T2); each cell has the shape of `_empty_cell()` below. The era level under each side is added because the table (V232-12) is per era (plans: `records.era_of`; signals: decision date vs the New York date of `ERA_BOUNDARY_UTC`). Level diffs stay float lists (levels only); V232-14 summarises them with `intervals.distribution`.

**Decisions** (match and replay-only rules: the docstrings of `match`, `replay_only_reason`):
- Live plans: every exported plan, at its issued levels (`records.rehydrate`; entry `entry_price` else `trigger_price`, as `scan_replay._alert`).
- **A `created_at`-sourced plan gets bucket `created_at`**, never `outside_session` (Handoff).
- **`unexplained` live-only = bucket `outside_session`:** that issue saw the close the replay decided on, so timing cannot explain the miss; in-session buckets carry intraday drift; `created_at` (unknown time) is never unexplained.

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-10: layer 2 adapter, matching and selection counts."""
import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pytest

from swingbot.core.scanning.scan_replay import ReplayAlert
from tests.scout.test_reconcile_records import _plan_doc

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer2, records  # noqa: E402

D6 = dt.date(2026, 10, 6)          # EDT: 15:00Z is 11:00 ET


def _signal(ticker="AAA", day="2026-10-06", direction="bullish", horizon="2w", **kw):
    base = dict(lane="base", ticker=ticker, direction=direction, source="confluence", mode=None,
                decision_date=day, horizon_key=horizon, strategy="RSI", entry=100.0, stop=98.0,
                target=104.0, planned_rr=2.0, outcome="win", r_multiple=2.0,
                exit_date="2026-10-09")
    base.update(kw)
    return layer2.adapt(ReplayAlert(**base))


def _doc(plan_id="P1", ticker="AAA", issued="2026-10-06T15:00:00+00:00", **kw):
    return _plan_doc(plan_id=plan_id, ticker=ticker, created_at="2026-10-06", issued_at=issued,
                     **kw)


def _rec(doc, opened=None, closed="2026-10-08T17:00:00+00:00"):
    trade = None if opened is None else {"id": "T-" + doc["plan_id"], "ticker": doc["ticker"],
                                         "opened_at": opened, "closed_at": closed}
    return records.LiveRecord(doc["plan_id"], doc["ticker"], doc["direction"], doc, trade, None)


def _export(*recs, rejections=()):
    return records.Export(tuple(recs), tuple(rejections), (), ())


def _plans(*recs, rows=None):
    return layer2.live_plans(_export(*recs), rows or {})


class _Row:
    def __init__(self, r_live_net):
        self.r_live_net = r_live_net


def test_adapt_keeps_levels_and_drops_every_outcome_field():
    signal = _signal(lane="short_universe", mode="isolated", direction="bearish")
    assert set(signal.to_dict()).isdisjoint(layer2.OUTCOME_FIELDS)
    assert (signal.decision_date, signal.entry, signal.stop, signal.target) == (
        "2026-10-06", 100.0, 98.0, 104.0)
    assert layer2.ReplaySignal.from_dict(signal.to_dict()) == signal


@pytest.mark.parametrize("field", ["outcome", "r_multiple", "exit_date"])
def test_from_dict_refuses_an_outcome_field(field):
    with pytest.raises(ValueError, match=field):
        layer2.ReplaySignal.from_dict({**_signal().to_dict(), field: "x"})


@pytest.mark.parametrize("name", ["ReplaySignal", "LivePlan", "MatchResult"])
def test_no_layer2_structure_has_an_outcome_field(name):
    fields = {f.name for f in dataclasses.fields(getattr(layer2, name))}
    assert fields.isdisjoint(layer2.OUTCOME_FIELDS)


def test_live_plans_carry_issued_levels_and_live_net():
    market, stop_entry = _plans(
        _rec(_doc()), _rec(_doc("P2", entry_type="stop_entry", trigger_price=101.0)),
        rows={"P1": _Row(1.25)})
    assert (market.session, market.entry, market.stop, market.target) == (D6, 100.0, 98.0, 104.0)
    assert market.r_live_net == 1.25 and stop_entry.r_live_net is None
    assert stop_entry.entry == 101.0      # the issued trigger, not the fill-written entry_price


@pytest.mark.parametrize("issued,bucket", [
    ("2026-10-06T14:00:00+00:00", "open_to_1030"),
    ("2026-10-06T16:00:00+00:00", "mid_day"),
    ("2026-10-06T19:30:00+00:00", "last_hour"),
    ("2026-10-06T21:00:00+00:00", "outside_session"),
    (None, "created_at")])
def test_each_issue_time_bucket(issued, bucket):
    (plan,) = _plans(_rec(_doc(issued=issued)))
    assert plan.bucket == bucket and plan.session == D6


@pytest.mark.parametrize("day,matched", [("2026-10-02", 0), ("2026-10-05", 1),
                                         ("2026-10-06", 1), ("2026-10-07", 1),
                                         ("2026-10-08", 0)])
def test_match_window_is_one_session_either_side(day, matched):
    result = layer2.match([_signal(day=day)], _plans(_rec(_doc())))
    assert len(result.matched) == matched
    assert len(result.live_only) == len(result.replay_only) == 1 - matched


def test_ticker_and_side_must_be_equal():
    result = layer2.match([_signal(direction="bearish"), _signal(ticker="BBB")],
                          _plans(_rec(_doc())))
    assert result.matched == [] and len(result.replay_only) == 2


def test_ties_go_to_the_same_horizon_then_the_nearest_date():
    exact_other, late_same, exact_same = (_signal(horizon="1m"), _signal(day="2026-10-07"),
                                          _signal())
    result = layer2.match([exact_other, late_same], _plans(_rec(_doc())))
    assert [s for _, s in result.matched] == [late_same]
    result = layer2.match([late_same, exact_same], _plans(_rec(_doc())))
    assert [s for _, s in result.matched] == [exact_same] and result.replay_only == [late_same]


def test_matching_is_one_to_one():
    plans = _plans(_rec(_doc("P1")), _rec(_doc("P2", issued="2026-10-07T15:00:00+00:00")))
    result = layer2.match([_signal()], plans)
    assert [p.plan_id for p, _ in result.matched] == ["P1"]
    assert [p.plan_id for p in result.live_only] == ["P2"]


def test_strategy_sourced_plans_sit_outside_the_replay():
    result = layer2.match([_signal()], _plans(_rec(_doc(source="strategy"))))
    assert [p.plan_id for p in result.outside_replay] == ["P1"]
    assert result.matched == [] and result.live_only == [] and len(result.replay_only) == 1


def test_each_replay_only_reason():
    held = _rec(_doc("P8", "OPN"), opened="2026-10-01T15:01:00+00:00", closed=None)
    gone = _rec(_doc("P9", "OLD"), opened="2026-10-01T15:01:00+00:00",
                closed="2026-10-02T15:00:00+00:00")
    rejection = {"ticker": "REJ", "gate": "rs_gate", "strategy": "RSI", "horizon": "2w",
                 "signal_date": "2026-10-06"}
    export = _export(held, gone, rejections=[rejection])
    reason = layer2.replay_only_reason
    assert reason(_signal(ticker="REJ"), export) == ("gate_rejection", "rs_gate")
    assert reason(_signal(ticker="OPN"), export) == ("open_position", None)
    assert reason(_signal(ticker="OLD"), export) == ("unexplained", None)


def test_level_diffs_are_entry_percent_and_distance_ratios():
    (plan,) = _plans(_rec(_doc()))
    diffs = layer2.level_diffs(plan, _signal(entry=101.0, stop=98.0, target=107.0))
    assert diffs["entry_pct"] == pytest.approx(1.0)
    assert diffs["stop_ratio"] == pytest.approx(1.5)       # 3 / 2
    assert diffs["target_ratio"] == pytest.approx(1.5)     # 6 / 4


def test_selection_counts_per_side_and_era_with_measured_zeros():
    rejection = {"ticker": "GGG", "gate": "earnings", "strategy": "RSI", "horizon": "2w",
                 "signal_date": "2026-10-06"}
    export = _export(_rec(_doc("P1"), opened="2026-10-06T15:01:00+00:00"),       # matched
                     _rec(_doc("P2", "BBB", issued="2026-10-06T21:00:00+00:00")),
                     _rec(_doc("P3", "CCC", issued=None)),
                     _rec(_doc("P4", "DDD", source="strategy")),
                     rejections=[rejection])
    plans = layer2.live_plans(export, {"P1": _Row(0.5), "P2": _Row(-1.0)})
    signals = [_signal(), _signal(ticker="EEE"), _signal(ticker="GGG"),
               _signal(ticker="ZZZ", day="2026-09-10")]
    counts = layer2.selection_counts(layer2.match(signals, plans), export)
    cell = counts["long"]["headline"]
    assert cell["matched"] == 1 and cell["outside_replay"] == 1
    assert cell["level_diffs"]["entry_pct"] == [0.0]
    live = cell["live_only"]
    assert (live["n"], live["unexplained"], live["live_r_n"], live["live_r_net"]) == (2, 1, 1, -1.0)
    assert live["by_bucket"]["created_at"] == 1 and live["by_bucket"]["outside_session"] == 1
    assert cell["replay_only"] == {"n": 2, "by_gate": {"earnings": 1}, "by_reason": {
        "gate_rejection": 1, "open_position": 0, "unexplained": 1}}
    assert counts["long"]["earlier"]["replay_only"]["n"] == 1
    assert counts["short"]["headline"]["matched"] == 0
    assert {side: set(eras) for side, eras in counts.items()} == {
        "long": {"headline", "earlier"}, "short": {"headline", "earlier"}}

```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer2.py`
Expected: FAIL — `ImportError: cannot import name 'layer2' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/layer2.py`**

```python
"""v232 layer 2 (spec ### Layer 2): replay signals, matching, selection counts.

Holdout (partner decision 4): no structure here carries a replay outcome, R or exit date.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from autopsy.eras import ERA_BOUNDARY_UTC

from . import records, sessions

OUTCOME_FIELDS = ("outcome", "r_multiple", "exit_date")
MATCH_SESSIONS = 1
REPLAY_ONLY_REASONS = ("gate_rejection", "open_position", "unexplained")
CREATED_AT_BUCKET = "created_at"
LIVE_ONLY_BUCKETS = sessions.ISSUE_BUCKETS + (CREATED_AT_BUCKET,)
UNEXPLAINED_BUCKET = "outside_session"
SIDES = ("long", "short")
ERAS = ("headline", "earlier")
_BOUNDARY_DAY = sessions.ny_time(ERA_BOUNDARY_UTC).date().isoformat()


def _side(direction: str) -> str:
    return "short" if direction in ("bearish", "short") else "long"


@dataclasses.dataclass(frozen=True)
class ReplaySignal:
    lane: str
    ticker: str
    direction: str
    source: str
    mode: str | None
    decision_date: str
    horizon_key: str
    strategy: str
    entry: float
    stop: float
    target: float

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReplaySignal":
        leaked = sorted(set(d) & set(OUTCOME_FIELDS))
        if leaked:
            raise ValueError(f"replay signal carries outcome field(s) {leaked}")
        return cls(**{f.name: d[f.name] for f in dataclasses.fields(cls)})


def adapt(alert) -> ReplaySignal:
    """A scan_replay.ReplayAlert reduced to levels and dates; outcome fields are dropped here."""
    kept = {f.name: getattr(alert, f.name) for f in dataclasses.fields(ReplaySignal)}
    for key in ("entry", "stop", "target"):
        kept[key] = float(kept[key])
    return ReplaySignal(**kept)


@dataclasses.dataclass(frozen=True)
class LivePlan:
    plan_id: str
    ticker: str
    direction: str
    source: str | None
    session: dt.date
    horizon_key: str | None
    bucket: str
    entry: float | None
    stop: float | None
    target: float | None
    r_live_net: float | None


def _num(value) -> float | None:
    return None if value is None else float(value)


def _live_plan(rec, row) -> LivePlan:
    stamp, source = sessions.stamp_source(rec.plan)
    bucket = CREATED_AT_BUCKET if source == "created_at" else sessions.issue_bucket(stamp)
    plan, _ = records.rehydrate(rec.plan)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return LivePlan(rec.plan_id, rec.ticker, rec.direction, rec.plan.get("source"),
                    sessions.issue_session(stamp), rec.plan.get("horizon_key"), bucket,
                    _num(entry), _num(plan.stop_loss), _num(plan.tp1),
                    None if row is None else row.r_live_net)


def live_plans(export, rows_by_plan: dict) -> list[LivePlan]:
    """Every exported plan (filled or not), in export order; live net R from its TradeRow."""
    return [_live_plan(rec, rows_by_plan.get(rec.plan_id)) for rec in export.records]


@dataclasses.dataclass
class MatchResult:
    matched: list          # [(LivePlan, ReplaySignal)]
    live_only: list
    replay_only: list
    outside_replay: list   # source "strategy"


def _candidate_pairs(signals, plans) -> list[tuple]:
    by_key: dict = {}
    for j, plan in enumerate(plans):
        by_key.setdefault((plan.ticker, _side(plan.direction)), []).append(j)
    pairs = []
    for i, signal in enumerate(signals):
        day = dt.date.fromisoformat(signal.decision_date)
        for j in by_key.get((signal.ticker, _side(signal.direction)), ()):
            apart = abs(sessions.sessions_apart(plans[j].session, day))
            if apart <= MATCH_SESSIONS:
                pairs.append((plans[j].horizon_key != signal.horizon_key, apart, j, i))
    return sorted(pairs)


def match(signals, plans) -> MatchResult:
    """One-to-one: same ticker and side within MATCH_SESSIONS of the issue session; ties go
    to the same horizon, then the nearest date, then plan and signal order."""
    outside = [p for p in plans if p.source == "strategy"]
    inside = [p for p in plans if p.source != "strategy"]
    used_plans: set = set()
    used_signals: set = set()
    pairs = []
    for _, _, j, i in _candidate_pairs(signals, inside):
        if j in used_plans or i in used_signals:
            continue
        used_plans.add(j)
        used_signals.add(i)
        pairs.append((j, i))
    pairs.sort()
    return MatchResult(matched=[(inside[j], signals[i]) for j, i in pairs],
                       live_only=[p for j, p in enumerate(inside) if j not in used_plans],
                       replay_only=[s for i, s in enumerate(signals) if i not in used_signals],
                       outside_replay=outside)


def _gate_on(signal, export) -> str | None:
    gates = sorted(str(r.get("gate")) for r in export.rejections
                   if r.get("ticker") == signal.ticker
                   and str(r.get("signal_date") or "")[:10] == signal.decision_date)
    return gates[0] if gates else None


def _held_on(rec, ticker: str, day: dt.date) -> bool:
    trade = rec.trade
    if trade is None or rec.ticker != ticker or not trade.get("opened_at"):
        return False
    closed = trade.get("closed_at")
    opened_ok = sessions.ny_time(trade["opened_at"]).date() <= day
    return opened_ok and (not closed or day <= sessions.ny_time(closed).date())


def replay_only_reason(signal, export) -> tuple[str, str | None]:
    """(reason, gate): a gate rejection for that ticker and day (first gate by name), else a
    live trade in the ticker (any direction) open that day, else unexplained."""
    gate = _gate_on(signal, export)
    if gate is not None:
        return "gate_rejection", gate
    day = dt.date.fromisoformat(signal.decision_date)
    if any(_held_on(rec, signal.ticker, day) for rec in export.records):
        return "open_position", None
    return "unexplained", None


def _ratio(num: float, den: float) -> float | None:
    return None if not den else num / den


def level_diffs(plan, signal) -> dict:
    """Levels only: entry in percent, stop and target distances as ratios (replay / live)."""
    if not plan.entry or plan.stop is None or plan.target is None:
        return {"entry_pct": None, "stop_ratio": None, "target_ratio": None}
    return {"entry_pct": (signal.entry / plan.entry - 1.0) * 100.0,
            "stop_ratio": _ratio(abs(signal.entry - signal.stop), abs(plan.entry - plan.stop)),
            "target_ratio": _ratio(abs(signal.target - signal.entry),
                                   abs(plan.target - plan.entry))}


def _empty_cell() -> dict:
    return {"matched": 0,
            "level_diffs": {"entry_pct": [], "stop_ratio": [], "target_ratio": []},
            "live_only": {"n": 0, "by_bucket": dict.fromkeys(LIVE_ONLY_BUCKETS, 0),
                          "unexplained": 0, "live_r_net": 0.0, "live_r_n": 0},
            "replay_only": {"n": 0, "by_reason": dict.fromkeys(REPLAY_ONLY_REASONS, 0),
                            "by_gate": {}},
            "outside_replay": 0}


def _signal_cell(counts: dict, signal) -> dict:
    era = "headline" if signal.decision_date >= _BOUNDARY_DAY else "earlier"
    return counts[_side(signal.direction)][era]


def _plan_cell(counts: dict, recs: dict, plan) -> dict:
    return counts[_side(plan.direction)][records.era_of(recs[plan.plan_id])]


def _add_matched(cell: dict, plan, signal) -> None:
    cell["matched"] += 1
    for key, value in level_diffs(plan, signal).items():
        if value is not None:
            cell["level_diffs"][key].append(value)


def _add_live_only(cell: dict, plan) -> None:
    live = cell["live_only"]
    live["n"] += 1
    live["by_bucket"][plan.bucket] += 1
    live["unexplained"] += int(plan.bucket == UNEXPLAINED_BUCKET)
    if plan.r_live_net is not None:
        live["live_r_net"] += plan.r_live_net
        live["live_r_n"] += 1


def _add_replay_only(cell: dict, signal, export) -> None:
    reason, gate = replay_only_reason(signal, export)
    replay = cell["replay_only"]
    replay["n"] += 1
    replay["by_reason"][reason] += 1
    if gate is not None:
        replay["by_gate"][gate] = replay["by_gate"].get(gate, 0) + 1


def selection_counts(result: MatchResult, export) -> dict:
    """counts[side][era]; every plan in `result` comes from live_plans(export, ...)."""
    counts = {side: {era: _empty_cell() for era in ERAS} for side in SIDES}
    recs = {rec.plan_id: rec for rec in export.records}
    for plan, signal in result.matched:
        _add_matched(_plan_cell(counts, recs, plan), plan, signal)
    for plan in result.live_only:
        _add_live_only(_plan_cell(counts, recs, plan), plan)
    for plan in result.outside_replay:
        _plan_cell(counts, recs, plan)["outside_replay"] += 1
    for signal in result.replay_only:
        _add_replay_only(_signal_cell(counts, signal), signal, export)
    return counts
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer2.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/layer2.py tests/scout/test_reconcile_layer2.py
git commit -m "feat(v232): layer 2 adapter, one-to-one matching and selection counts"
```

### Task V232-11: Layer 2 runner over `scan_replay`

**Model:** opus — drives the live scan through its replay seam; a wrong checkpoint unit or frame source changes the signals silently.

**Files:**
- Create: `scripts/reports/reconcile/layer2_run.py`
- Create: `tests/scout/test_reconcile_layer2_run.py`

**Interfaces:**
- Consumes: `layer2.adapt`, `layer2.ReplaySignal` (`to_dict`, `from_dict`, which refuses outcome fields) (V232-10); `records.Export` fields `records`, `rejections`, `watchlist` (V232-6).
- Existing, unchanged: `scan_replay.replay_base_scan`, `replay_extra_short_scan(..., allowed_modes)` (`.alerts`, `scan_replay.py:393`, `:399`), `ReplaySpec`, `decision_dates`; `short_candidates.admitted_short_modes(cfg)` (`:23`) and `extra_symbols`; `strategy_types.LEGACY_HORIZONS` (what the live scan walks, `scan_run.py:598`); `history_store.load` / `MissingStoreError`; `pit_membership.load_intervals`; `fetch._etf_symbol_of_sector()`; `config.MARKET_REGIME_TICKER`; `ScanParams` (frozen dataclass).
- Produces (consumed by V232-15): every name and signature in the ledger row (lane files `lane-base.jsonl`, `lane-extra.jsonl` in `checkpoint_dir`), plus `SNAPSHOT_FN`, the replay's own default snapshot function, for the CLI's `coverage` call.
- `coverage` returns `{"window": [start, end], "sessions": int, "spy_missing": bool, "base_missing_days": {ticker: int}, "panel_gaps": {day: [symbol]}, "snapshot_missing": [day], "extra_missing": {day: int}}` (no R anywhere).

**Decisions this task freezes (Handoff, spec `### Layer 2`):**
- **One checkpoint per lane, never per ticker.** `scan_replay` is cross-sectional per decision date (`_base_day` computes breadth, the RS cache and sector frames over all base tickers at once), so a per-ticker replay would change the signals. A lane file is written to `<name>.tmp`, fsynced and `os.replace`d when the lane finishes; it is valid only when its first line equals the run's meta line and its last line is `{"kind": "end", "n": <signal count>}`. Anything else (torn, stale window, other parameters, other tickers, other modes) is replayed.
- **Meta line** `{"kind": "meta", "lane", "window", "params_digest", "tickers_digest", "modes"}`; the run compares `params_digest` with production's (Handoff, V232-15/16).
- **Lanes as live has them:** the base lane always; the extra SHORT lane once with `allowed_modes = modes` when `modes` is non-empty (live admits both modes in one lane, `short_run.py:397`); horizons `LEGACY_HORIZONS`; no track record (the replay's default, listed as left out).
- **Holdout:** only `layer2.adapt` output is stored; signal lines are read back through `ReplaySignal.from_dict`, which raises on an outcome field.

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-11: the layer 2 runner over the unchanged scan replay."""
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.marketdata import history_store
from swingbot.core.marketdata.universe import ShortSnapshot
from swingbot.core.scanning import scan_replay
from swingbot.core.scanning.scan_replay import ReplayAlert
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer2, layer2_run, records  # noqa: E402

WINDOW = ("2026-10-05", "2026-10-09")
SPY = config.MARKET_REGIME_TICKER


def _alert(ticker="AAA", lane="base", mode=None, direction="bullish"):
    return ReplayAlert(lane=lane, ticker=ticker, direction=direction, source="confluence",
                       mode=mode, decision_date="2026-10-06", horizon_key="2w", strategy="RSI",
                       entry=100.0, stop=98.0, target=104.0, planned_rr=2.0, outcome="loss",
                       r_multiple=-1.0, exit_date="2026-10-08")


class _Replay:
    def __init__(self, alerts):
        self.alerts, self.calls = alerts, []

    def __call__(self, frames, window, params, *, spec, allowed_modes=None):
        self.calls.append({"window": window, "spec": spec, "allowed_modes": allowed_modes})
        return SimpleNamespace(alerts=list(self.alerts), excluded=[])


@pytest.fixture
def lanes(monkeypatch):
    base = _Replay([_alert(), _alert("BBB")])
    extra = _Replay([_alert("CCC", "short_universe", "isolated", "bearish")])
    monkeypatch.setattr(scan_replay, "replay_base_scan", base)
    monkeypatch.setattr(scan_replay, "replay_extra_short_scan", extra)
    return SimpleNamespace(base=base, extra=extra)


def _frames():
    return {SPY: make_ohlcv([100.0] * 5, start="2026-10-05"),
            "AAA": make_ohlcv([50.0] * 3, start="2026-10-05")}


def _run(tmp_path, params=None, modes=frozenset(), window=WINDOW, tickers=("AAA", "BBB")):
    out = []
    signals = layer2_run.run_layer2(_frames(), window, params or ScanParams.from_config(),
                                    base_tickers=tickers, modes=modes,
                                    checkpoint_dir=tmp_path, out=out.append)
    return signals, out


def test_replay_tickers_are_the_watchlist_plans_and_rejections():
    doc = {"plan_id": "P1", "ticker": "PPP", "direction": "bullish"}
    export = records.Export((records.LiveRecord("P1", "PPP", "bullish", doc, None, None),),
                            ({"ticker": "RRR", "gate": "rs_gate"},), ("WWW", "PPP"), ())
    assert layer2_run.replay_tickers(export) == ("PPP", "RRR", "WWW")


@pytest.mark.parametrize("enabled,broad,isolated,expected", [
    (False, True, True, frozenset()),
    (True, False, True, frozenset({"isolated"})),
    (True, True, True, frozenset({"broad", "isolated"}))])
def test_live_short_modes_follow_the_live_flags(monkeypatch, enabled, broad, isolated, expected):
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", enabled, raising=False)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_BROAD_ENABLED", broad, raising=False)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ISOLATED_ENABLED", isolated, raising=False)
    assert layer2_run.live_short_modes() == expected


def test_reference_symbols_add_pit_members_only_with_an_extra_lane(monkeypatch):
    monkeypatch.setattr(layer2_run, "_sector_etfs", lambda: ("XLK",))
    monkeypatch.setattr(layer2_run, "_pit_members", lambda: ("MMM", "ZZZ"))
    assert layer2_run.reference_symbols(frozenset()) == tuple(sorted({SPY, "XLK"}))
    assert layer2_run.reference_symbols({"isolated"}) == tuple(sorted({SPY, "XLK", "MMM", "ZZZ"}))


def test_load_frames_lists_what_the_store_lacks():
    frame = make_ohlcv([1.0, 2.0])

    def load(symbol, timeframe):
        assert timeframe == "daily"
        if symbol == "BAD":
            raise history_store.MissingStoreError("no store")
        return frame if symbol == "AAA" else None

    frames, missing = layer2_run.load_frames(["AAA", "NONE", "BAD"], load=load)
    assert list(frames) == ["AAA"] and missing == ["NONE", "BAD"]


def test_coverage_lists_sessions_without_inputs(monkeypatch):
    monkeypatch.setattr(layer2_run, "_sector_etfs", lambda: ("XLK",))
    xlk = make_ohlcv([10.0] * 5, start="2026-10-05")
    frames = {**_frames(), "XLK": xlk.drop(xlk.index[2])}                   # no 10-07 bar

    def snapshot(day):
        return None if day == "2026-10-06" else ShortSnapshot(("AAA", "PIT1"), day, {})

    cov = layer2_run.coverage(frames, WINDOW, base_tickers=("AAA",), modes={"broad"},
                              snapshot_fn=snapshot)
    assert (cov["sessions"], cov["spy_missing"]) == (5, False)
    assert cov["base_missing_days"] == {"AAA": 2}
    assert cov["panel_gaps"] == {"2026-10-07": ["XLK"]}
    assert cov["snapshot_missing"] == ["2026-10-06"]
    assert cov["extra_missing"] == {d: 1 for d in ("2026-10-05", "2026-10-07", "2026-10-08",
                                                   "2026-10-09")}


def test_coverage_without_an_extra_lane_never_asks_for_snapshots(monkeypatch):
    monkeypatch.setattr(layer2_run, "_sector_etfs", lambda: ())

    def snapshot(day):
        raise AssertionError("no snapshot without an extra lane")

    cov = layer2_run.coverage(_frames(), WINDOW, base_tickers=("AAA",), modes=frozenset(),
                              snapshot_fn=snapshot)
    assert cov["snapshot_missing"] == [] and cov["extra_missing"] == {}


def test_params_digest_is_stable_and_moves_with_a_parameter():
    params = ScanParams.from_config()
    assert layer2_run.params_digest(params) == layer2_run.params_digest(ScanParams.from_config())
    moved = dataclasses.replace(params, min_reward_pct=params.min_reward_pct + 1.0)
    assert layer2_run.params_digest(moved) != layer2_run.params_digest(params)


def test_the_base_lane_runs_with_live_horizons_and_no_extra_lane(tmp_path, lanes):
    signals, _ = _run(tmp_path)
    assert [s.ticker for s in signals] == ["AAA", "BBB"]
    assert all(isinstance(s, layer2.ReplaySignal) for s in signals)
    (call,) = lanes.base.calls
    assert call["spec"].base_tickers == ("AAA", "BBB") and lanes.extra.calls == []
    assert call["spec"].horizons == tuple(layer2_run.LEGACY_HORIZONS)
    assert not (tmp_path / "lane-extra.jsonl").exists()


def test_a_finished_lane_is_read_back_not_replayed(tmp_path, lanes):
    first, _ = _run(tmp_path, modes={"isolated"})
    again, out = _run(tmp_path, modes={"isolated"})
    assert again == first
    assert len(lanes.base.calls) == 1 and len(lanes.extra.calls) == 1
    assert [s.ticker for s in first] == ["AAA", "BBB", "CCC"]
    assert lanes.extra.calls[0]["allowed_modes"] == frozenset({"isolated"})
    assert any("from lane-base.jsonl" in line for line in out)


def test_lane_files_carry_no_outcome_key(tmp_path, lanes):
    _run(tmp_path, modes={"isolated"})
    for path in tmp_path.glob("lane-*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            keys = set(row) | set(row.get("signal", {}))
            assert keys.isdisjoint(layer2.OUTCOME_FIELDS), path.name


@pytest.mark.parametrize("change", ["params", "window", "tickers"])
def test_a_changed_input_replays_the_lane(tmp_path, lanes, change):
    _run(tmp_path)
    params = ScanParams.from_config()
    kwargs = {"params": dataclasses.replace(params, min_reward_pct=params.min_reward_pct + 1.0),
              "window": ("2026-10-05", "2026-10-08"), "tickers": ("AAA",)}
    _run(tmp_path, **{change: kwargs[change]})
    assert len(lanes.base.calls) == 2


def test_a_torn_lane_file_is_replayed(tmp_path, lanes):
    _run(tmp_path)
    path = tmp_path / "lane-base.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8", newline="\n")   # no end line
    signals, _ = _run(tmp_path)
    assert len(lanes.base.calls) == 2 and len(signals) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_a_lane_file_with_an_outcome_field_is_refused(tmp_path, lanes):
    _run(tmp_path)
    path = tmp_path / "lane-base.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    rows[1]["signal"]["r_multiple"] = 2.0
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="r_multiple"):
        _run(tmp_path)


def test_no_benchmark_frame_is_refused(tmp_path, lanes):
    with pytest.raises(ValueError, match="the replay has no dates"):
        layer2_run.run_layer2({}, WINDOW, ScanParams.from_config(), base_tickers=("AAA",),
                              modes=frozenset(), checkpoint_dir=tmp_path, out=lambda _: None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer2_run.py`
Expected: FAIL — `ImportError: cannot import name 'layer2_run' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/layer2_run.py`**

```python
"""v232 layer 2 runner: the unchanged live scan code over the window (spec ### Layer 2).

Cross-sectional per decision date, so one checkpoint per lane. Frames: the adjusted store,
the bars the live scan saw. Only layer2.adapt output is stored (partner decision 4).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from swingbot import config
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.marketdata import history_store, universe
from swingbot.core.marketdata.pit_membership import load_intervals
from swingbot.core.scanning import scan_replay
from swingbot.core.scanning.short_candidates import admitted_short_modes, extra_symbols

from . import layer2

SNAPSHOT_FN = scan_replay.ReplaySpec(base_tickers=(), horizons=()).snapshot_fn


def replay_tickers(export) -> tuple[str, ...]:
    """The current watchlist plus every ticker in a live plan or a gate rejection."""
    tickers = set(export.watchlist) | {rec.ticker for rec in export.records}
    tickers |= {r["ticker"] for r in export.rejections if r.get("ticker")}
    return tuple(sorted(tickers))


def live_short_modes() -> frozenset[str]:
    """The SHORT extra lane's modes as the live configuration has them today."""
    return frozenset(admitted_short_modes(config))


def _sector_etfs() -> tuple[str, ...]:
    from swingbot.core.scanning.fetch import _etf_symbol_of_sector
    return tuple(sorted(set(_etf_symbol_of_sector().values())))


def _pit_members() -> tuple[str, ...]:
    return tuple(sorted(load_intervals(os.path.join(universe.UNIVERSE_DIR,
                                                    "sp500_membership.csv"))))


def reference_symbols(modes) -> tuple[str, ...]:
    """The benchmark and sector ETFs; with an extra lane on, the point-in-time members too."""
    symbols = {config.MARKET_REGIME_TICKER, *_sector_etfs()}
    if modes:
        symbols.update(_pit_members())
    return tuple(sorted(symbols))


def load_frames(symbols, *, load=history_store.load) -> tuple[dict, list[str]]:
    """({symbol: daily frame}, [symbols the store lacks]), in the order given."""
    frames: dict = {}
    missing: list[str] = []
    for symbol in symbols:
        try:
            frame = load(symbol, "daily")
        except history_store.MissingStoreError:
            frame = None
        if frame is None:
            missing.append(symbol)
        else:
            frames[symbol] = frame
    return frames, missing


def _has_bar(frame, day: str) -> bool:
    return frame is not None and pd.Timestamp(day) in frame.index


def _missing_days(frames: dict, tickers, days) -> dict:
    counts = {t: sum(not _has_bar(frames.get(t), d) for d in days) for t in tickers}
    return {t: n for t, n in sorted(counts.items()) if n}


def _panel_gaps(frames: dict, days) -> dict:
    panel = (config.MARKET_REGIME_TICKER,) + _sector_etfs()
    gaps = {d: [s for s in panel if not _has_bar(frames.get(s), d)] for d in days}
    return {d: symbols for d, symbols in gaps.items() if symbols}


def _extra_gaps(frames: dict, days, base_tickers, snapshot_fn) -> tuple[list, dict]:
    no_snapshot: list = []
    missing: dict = {}
    for day in days:
        snapshot = snapshot_fn(day)
        if snapshot is None:
            no_snapshot.append(day)
            continue
        n = sum(not _has_bar(frames.get(s), day) for s in extra_symbols(snapshot, base_tickers))
        if n:
            missing[day] = n
    return no_snapshot, missing


def coverage(frames, window, *, base_tickers, modes, snapshot_fn) -> dict:
    """Which decision sessions lack an input: base bars, the panel, the snapshot, extra bars."""
    spy = frames.get(config.MARKET_REGIME_TICKER)
    days = scan_replay.decision_dates(spy, window) if spy is not None else []
    no_snapshot, extra_missing = ([], {})
    if modes:
        no_snapshot, extra_missing = _extra_gaps(frames, days, base_tickers, snapshot_fn)
    return {"window": list(window), "sessions": len(days), "spy_missing": spy is None,
            "base_missing_days": _missing_days(frames, base_tickers, days),
            "panel_gaps": _panel_gaps(frames, days), "snapshot_missing": no_snapshot,
            "extra_missing": extra_missing}


def params_digest(params) -> str:
    blob = json.dumps(dataclasses.asdict(params), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _meta(lane: str, window, params, base_tickers: tuple, modes) -> dict:
    tickers = hashlib.sha256("\n".join(base_tickers).encode("utf-8")).hexdigest()
    return {"kind": "meta", "lane": lane, "window": list(window),
            "params_digest": params_digest(params), "tickers_digest": tickers,
            "modes": sorted(modes)}


def _read_lane(path: Path, meta: dict) -> list | None:
    if not path.is_file():
        return None
    try:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except json.JSONDecodeError:
        return None
    if len(rows) < 2 or rows[0] != meta or rows[-1] != {"kind": "end", "n": len(rows) - 2}:
        return None
    return [layer2.ReplaySignal.from_dict(row["signal"]) for row in rows[1:-1]]


def _write_lane(path: Path, meta: dict, signals: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    body = ([meta] + [{"kind": "signal", "signal": s.to_dict()} for s in signals]
            + [{"kind": "end", "n": len(signals)}])
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for row in body:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _lane(name: str, replay, meta: dict, checkpoint_dir: Path, out) -> list:
    path = Path(checkpoint_dir) / f"lane-{name}.jsonl"
    cached = _read_lane(path, meta)
    if cached is not None:
        out(f"layer 2 lane {name}: {len(cached)} signals from {path.name}")
        return cached
    out(f"layer 2 lane {name}: replaying {meta['window'][0]}..{meta['window'][1]}")
    signals = [layer2.adapt(alert) for alert in replay().alerts]
    _write_lane(path, meta, signals)
    out(f"layer 2 lane {name}: {len(signals)} signals written to {path.name}")
    return signals


def run_layer2(frames, window: tuple[str, str], params, *, base_tickers, modes,
               checkpoint_dir: Path, out=print) -> list:
    """Base lane, then the extra SHORT lane when `modes` is non-empty; one checkpoint each."""
    if config.MARKET_REGIME_TICKER not in frames:
        raise ValueError(f"no {config.MARKET_REGIME_TICKER} frame: the replay has no dates")
    base = tuple(sorted(base_tickers))
    spec = scan_replay.ReplaySpec(base_tickers=base, horizons=tuple(LEGACY_HORIZONS))
    lanes = {"base": lambda: scan_replay.replay_base_scan(frames, window, params, spec=spec)}
    if modes:
        lanes["extra"] = lambda: scan_replay.replay_extra_short_scan(
            frames, window, params, spec=spec, allowed_modes=frozenset(modes))
    signals: list = []
    for name, replay in lanes.items():
        signals.extend(_lane(name, replay, _meta(name, window, params, base, modes),
                             checkpoint_dir, out))
    return signals
```

A lane over the ~45-session window takes minutes; the runner prints a line when a lane starts and when it is written (no percent: the replay has no per-day hook and is not edited).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_layer2_run.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/layer2_run.py tests/scout/test_reconcile_layer2_run.py
git commit -m "feat(v232): layer 2 runner over scan_replay, checkpointed per lane"
```

### Task V232-12: Reconciliation table and self-check

**Model:** sonnet — sums over finished rows with a fixed line order; the one judgement (rows without a live R) is decided below.

**Files:**
- Create: `scripts/reports/reconcile/table.py`
- Create: `tests/scout/test_reconcile_table.py`

**Interfaces:**
- Consumes: `layer1_run.TradeRow` (V232-9): `side`, `era`, `klass`, `refusal`, `.scored`, `r_live_gross`, `cost_r`, `r_live_net`, `values[model]["r_as_backtest"]`, `values[model]["backtest_no_fill"]`, `effects[model]["entry"]`, `effects[model]["exit"]` (`layer1.effects`, V232-7b: `exit = r_live_gross - r_exit_only`, `entry = r_exit_only - r_as_backtest`, gross against gross). `selection_counts` cells `counts[side][era]` with `matched`, `live_only["n"]`, `replay_only["n"]`, `outside_replay` (V232-10). Rows are `TradeRow` objects; the CLI (V232-15) passes `TradeRow.from_dict` of the checkpoint rows.
- Produces (ledger V232-12, final; consumed by V232-14, V232-15): `TOLERANCE_R = 0.01`; `class ReconcileError(RuntimeError)`; `LINE_KEYS = ("backtest", "entry", "exit", "live_gross", "costs", "live_net", "backtest_no_fill", "manual", "refused", "book_net")`; `@dataclass(frozen=True) Line(key: str, label: str, total_r: float, n: int)`; `build_table(rows, *, side, fill_model, era="headline") -> list[Line]` (in `LINE_KEYS` order); `book_total(rows, *, side, era) -> float`; `self_check(lines, rows, *, side, fill_model, era) -> None` (raises `ReconcileError`); `selection_line(counts: dict, rows, *, side, era) -> str`. Also `LABELS` (key → spec label) and `NO_LIVE_R = ("no_journal", "zero_risk")`.

**Lines (spec `### The reconciliation table`), over the rows of one side and era:**

| Key | Rows | Sum of |
|---|---|---|
| `backtest`, `entry`, `exit` | scored, backtest filled under `fill_model` | `r_as_backtest`; `effects.entry`; `effects.exit` |
| `live_gross`, `costs`, `live_net` | the same rows | `r_live_gross`; `cost_r` (positive, subtracted); `r_live_net` |
| `backtest_no_fill` | scored, `values[fill_model].backtest_no_fill` | `r_live_net` |
| `manual` | `klass == "manual"`, no refusal | `r_live_net` |
| `refused` | `klass` `closed` or `manual` with any refusal | `r_live_net`, `None` counted as 0R |
| `book_net` | every `closed` and `manual` row | `r_live_net`, `None` counted as 0R |

**Rows with no live R (Handoff, decided here).** `no_journal` and `zero_risk` rows have `r_live_net=None`: no journal means no R was booked, and a zero live risk unit leaves no R in live units. They are **counted, not summed**: they add to the `refused` line's `N` and to `book_net`'s `N` at 0R, and the `refused` label then reads `"+ not scoreable: bars refused (live net); k without live R (no journal or zero risk), counted at 0R"`. `book_total` (the live book, independently) also has nothing to add for them, so the chain still closes, and the count is printed where the reader sees the total.

**Self-check.** `self_check` raises `ReconcileError` listing every failure when:
1. a line's total differs from `build_table` of the same rows by more than `TOLERANCE_R`, its `N` differs, or the keys are not `LINE_KEYS` in order (a tampered table);
2. `backtest + entry + exit` differs from `live_gross`, `live_gross - costs` from `live_net`, or `live_net + backtest_no_fill + manual + refused` from `book_net` (a tampered row's effect or net);
3. `book_net`'s `N` is not the sum of the four `N`s above it;
4. `book_net` differs from `book_total`, which sums `r_live_gross - cost_r` over `closed` and `manual` rows that have them (independent of `r_live_net`).

- [ ] **Step 1: Write the failing tests**

```python
"""v232 V232-12: the reconciliation table and its self-check."""
import dataclasses
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer1_run, table  # noqa: E402

LIVE = ("closed", "manual")


def _values(bt, exit_only, no_fill):
    return {"fill_model": "v1", "r_exit_only": exit_only, "exit_only_outcome": "win",
            "exit_only_class": "win", "r_as_backtest": None if no_fill else bt,
            "r_rebased": None, "stop_shift_pct": None, "backtest_no_fill": no_fill}


def _row(i, klass="closed", side="long", era="headline", refusal=None, gross=1.0, cost=0.1,
         bt=0.4, exit_only=0.8, no_fill=False):
    scored = klass == "closed" and refusal is None
    live = klass in LIVE and refusal not in table.NO_LIVE_R
    values = {m: _values(bt, exit_only, no_fill) for m in ("v1", "v2")} if scored else {}
    effects = {m: {"exit": gross - exit_only, "entry": None if no_fill else exit_only - bt}
               for m in values}
    return layer1_run.TradeRow(
        trade_id=f"T{i}", plan_id=f"P{i}", ticker="AAA", strategy="RSI", horizon_key="2w",
        ledger="main", side=side, era=era, klass=klass, refusal=refusal,
        entry_date="2026-10-06", stamp_source="issued_at", issue_bucket="mid_day",
        r_live_gross=gross if live else None, cost_r=cost if live else None,
        r_live_net=gross - cost if live else None, values=values, effects=effects, tags=(),
        gap=None, entry_slip=None, poll_fill=None, live_class="win" if live else None,
        unfilled_reason=None, would_fill={})


BOOK = [_row(1, gross=1.0, cost=0.1, bt=0.4, exit_only=0.8),
        _row(2, gross=-1.0, cost=0.1, bt=-1.0, exit_only=-0.5),
        _row(3, gross=2.0, cost=0.2, bt=1.5, exit_only=2.5),
        _row(4, gross=0.5, cost=0.1, no_fill=True),
        _row(5, klass="manual", gross=-0.3, cost=0.05),
        _row(6, refusal="split_in_window", gross=0.7, cost=0.1),
        _row(7, refusal="no_journal"),
        _row(8, klass="manual", refusal="zero_risk"),
        _row(9, klass="still_open"),
        _row(10, klass="unfilled"),
        _row(11, side="short", gross=-2.0),
        _row(12, era="earlier", gross=-3.0)]


def _table(rows=BOOK, **kw):
    kw = {"side": "long", "fill_model": "v1", "era": "headline", **kw}
    return table.build_table(rows, **kw), kw


def test_every_line_is_a_per_trade_sum():
    lines, _ = _table()
    assert [line.key for line in lines] == list(table.LINE_KEYS)
    got = {line.key: (round(line.total_r, 6), line.n) for line in lines}
    assert got == {"backtest": (0.9, 3), "entry": (1.9, 3), "exit": (-0.8, 3),
                   "live_gross": (2.0, 3), "costs": (0.4, 3), "live_net": (1.6, 3),
                   "backtest_no_fill": (0.4, 1), "manual": (-0.35, 1), "refused": (0.6, 3),
                   "book_net": (2.25, 8)}
    assert table.book_total(BOOK, side="long", era="headline") == pytest.approx(2.25)


def test_the_self_check_passes_on_a_consistent_book():
    lines, kw = _table()
    table.self_check(lines, BOOK, **kw)


def test_rows_without_live_r_are_counted_not_summed():
    lines, _ = _table()
    refused = next(line for line in lines if line.key == "refused")
    assert (refused.n, round(refused.total_r, 6)) == (3, 0.6)
    assert "2 without live R" in refused.label
    clean, _ = _table([r for r in BOOK if r.refusal not in table.NO_LIVE_R])
    assert next(line for line in clean if line.key == "refused").label == table.LABELS["refused"]


def test_self_check_fails_on_a_tampered_effect():
    row = BOOK[0]
    effects = {**row.effects, "v1": {**row.effects["v1"], "exit": row.effects["v1"]["exit"] + 0.5}}
    rows = [dataclasses.replace(row, effects=effects)] + BOOK[1:]
    lines, kw = _table(rows)
    with pytest.raises(table.ReconcileError, match="live_gross"):
        table.self_check(lines, rows, **kw)


def test_self_check_fails_on_a_tampered_live_net():
    rows = [dataclasses.replace(BOOK[0], r_live_net=BOOK[0].r_live_net + 0.3)] + BOOK[1:]
    lines, kw = _table(rows)
    with pytest.raises(table.ReconcileError, match="live_net"):
        table.self_check(lines, rows, **kw)


def test_self_check_fails_on_a_tampered_line():
    lines, kw = _table()
    lines[0] = dataclasses.replace(lines[0], total_r=lines[0].total_r + 0.5)
    with pytest.raises(table.ReconcileError, match="line backtest"):
        table.self_check(lines, BOOK, **kw)


def test_a_mismatch_inside_the_tolerance_passes():
    lines, kw = _table()
    lines[-1] = dataclasses.replace(lines[-1], total_r=lines[-1].total_r + 0.004)
    table.self_check(lines, BOOK, **kw)


def test_an_empty_direction_gives_zero_lines_and_passes():
    lines, kw = _table(side="short", era="earlier")
    assert all(line.total_r == 0.0 and line.n == 0 for line in lines)
    table.self_check(lines, BOOK, **kw)


def test_the_fill_model_decides_backtest_no_fill():
    row = BOOK[0]
    v2 = {**row.values["v2"], "backtest_no_fill": True, "r_as_backtest": None}
    rows = [dataclasses.replace(row, values={**row.values, "v2": v2},
                                effects={**row.effects, "v2": {**row.effects["v2"],
                                                               "entry": None}})] + BOOK[1:]
    lines, kw = _table(rows, fill_model="v2")
    got = {line.key: line.n for line in lines}
    assert (got["backtest"], got["backtest_no_fill"], got["book_net"]) == (2, 2, 8)
    table.self_check(lines, rows, **kw)


def test_the_selection_line_reads_counts_and_rows():
    counts = {"long": {"headline": {"matched": 3, "live_only": {"n": 2},
                                    "replay_only": {"n": 4}, "outside_replay": 1}}}
    assert table.selection_line(counts, BOOK, side="long", era="headline") == (
        "Selection, counts only: matched 3 · live-only 2 · replay-only 4"
        " · outside the replay (strategy-sourced) 1 · still open 1 · unfilled 1")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_table.py`
Expected: FAIL — `ImportError: cannot import name 'table' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/table.py`**

```python
"""v232 reconciliation table (spec ### The reconciliation table), per side, fill model, era.

Every line is a sum of per-trade rows; there is no remainder line. self_check re-derives
each line from the rows and fails the run on a mismatch above TOLERANCE_R.
"""
from __future__ import annotations

import dataclasses

TOLERANCE_R = 0.01
NO_LIVE_R = ("no_journal", "zero_risk")
LINE_KEYS = ("backtest", "entry", "exit", "live_gross", "costs", "live_net",
             "backtest_no_fill", "manual", "refused", "book_net")
LABELS = {
    "backtest": "Backtest of the plans live traded (zero cost)",
    "entry": "+ entry effect (incl. intraday drift to the close)",
    "exit": "+ exit effect",
    "live_gross": "= Live, gross, scored trades",
    "costs": "- modelled costs",
    "live_net": "= Live, net, scored trades",
    "backtest_no_fill": "+ backtest would not have filled (live net)",
    "manual": "+ manual closes (live net)",
    "refused": "+ not scoreable: bars refused (live net)",
    "book_net": "= Live book, net",
}
_CHAINS = (("live_gross", ("backtest", "entry", "exit"), ()),
           ("live_net", ("live_gross",), ("costs",)),
           ("book_net", ("live_net", "backtest_no_fill", "manual", "refused"), ()))


class ReconcileError(RuntimeError):
    """The table does not reproduce the live book from its own rows."""


@dataclasses.dataclass(frozen=True)
class Line:
    key: str
    label: str
    total_r: float
    n: int


def _pick(rows, side: str, era: str) -> list:
    return [r for r in rows if r.side == side and r.era == era]


def _no_fill(row, fill_model: str) -> bool:
    return bool(row.values[fill_model]["backtest_no_fill"])


def _groups(rows, fill_model: str) -> dict:
    book = [r for r in rows if r.klass in ("closed", "manual")]
    scored = [r for r in book if r.scored]
    return {"filled": [r for r in scored if not _no_fill(r, fill_model)],
            "no_fill": [r for r in scored if _no_fill(r, fill_model)],
            "manual": [r for r in book if r.klass == "manual" and r.refusal is None],
            "refused": [r for r in book if r.refusal is not None],
            "book": book}


def _sum(values) -> float:
    return float(sum(v for v in values if v is not None))      # None: no live R, 0R


def _refused_label(refused: list) -> str:
    k = sum(r.refusal in NO_LIVE_R for r in refused)
    if not k:
        return LABELS["refused"]
    return f"{LABELS['refused']}; {k} without live R (no journal or zero risk), counted at 0R"


def build_table(rows, *, side: str, fill_model: str, era: str = "headline") -> list[Line]:
    """The ten lines for one side, fill model and era, each summed from the rows."""
    g = _groups(_pick(rows, side, era), fill_model)
    f = g["filled"]
    totals = {
        "backtest": _sum(r.values[fill_model]["r_as_backtest"] for r in f),
        "entry": _sum(r.effects[fill_model]["entry"] for r in f),
        "exit": _sum(r.effects[fill_model]["exit"] for r in f),
        "live_gross": _sum(r.r_live_gross for r in f),
        "costs": _sum(r.cost_r for r in f),
        "live_net": _sum(r.r_live_net for r in f),
        "backtest_no_fill": _sum(r.r_live_net for r in g["no_fill"]),
        "manual": _sum(r.r_live_net for r in g["manual"]),
        "refused": _sum(r.r_live_net for r in g["refused"]),
        "book_net": _sum(r.r_live_net for r in g["book"]),
    }
    sizes = {"backtest_no_fill": len(g["no_fill"]), "manual": len(g["manual"]),
             "refused": len(g["refused"]), "book_net": len(g["book"])}
    labels = {**LABELS, "refused": _refused_label(g["refused"])}
    return [Line(k, labels[k], totals[k], sizes.get(k, len(f))) for k in LINE_KEYS]


def book_total(rows, *, side: str, era: str) -> float:
    """The live book's net R from gross and cost (not from r_live_net), closed and manual."""
    return float(sum(r.r_live_gross - r.cost_r for r in _pick(rows, side, era)
                     if r.klass in ("closed", "manual") and r.r_live_gross is not None
                     and r.cost_r is not None))


def _line_errors(lines, expected) -> list[str]:
    if [line.key for line in lines] != list(LINE_KEYS):
        return [f"line keys {[line.key for line in lines]} are not LINE_KEYS"]
    return [f"line {got.key}: table {got.total_r:+.4f} (n {got.n}) vs rows "
            f"{want.total_r:+.4f} (n {want.n})"
            for got, want in zip(lines, expected)
            if abs(got.total_r - want.total_r) > TOLERANCE_R or got.n != want.n]


def _chain_errors(t: dict) -> list[str]:
    errors = []
    for result, plus, minus in _CHAINS:
        got = sum(t[k].total_r for k in plus) - sum(t[k].total_r for k in minus)
        if abs(got - t[result].total_r) > TOLERANCE_R:
            errors.append(f"{result}: lines above give {got:+.4f}, "
                          f"line is {t[result].total_r:+.4f}")
    parts = sum(t[k].n for k in ("live_net", "backtest_no_fill", "manual", "refused"))
    if parts != t["book_net"].n:
        errors.append(f"book_net n {t['book_net'].n} is not the sum of its parts {parts}")
    return errors


def self_check(lines, rows, *, side: str, fill_model: str, era: str) -> None:
    """Raise ReconcileError unless the table re-derives from the rows and closes on the book."""
    errors = _line_errors(lines, build_table(rows, side=side, fill_model=fill_model, era=era))
    if not errors or not errors[0].startswith("line keys"):
        t = {line.key: line for line in lines}
        errors += _chain_errors(t)
        book = book_total(rows, side=side, era=era)
        if abs(book - t["book_net"].total_r) > TOLERANCE_R:
            errors.append(f"book_net {t['book_net'].total_r:+.4f} vs live book {book:+.4f}")
    if errors:
        raise ReconcileError(f"{side} {fill_model} {era}: " + "; ".join(errors))


def selection_line(counts: dict, rows, *, side: str, era: str) -> str:
    """The selection counts under the table; still-open and unfilled come from the rows."""
    cell = counts[side][era]
    picked = _pick(rows, side, era)
    still_open = sum(r.klass == "still_open" for r in picked)
    unfilled = sum(r.klass == "unfilled" for r in picked)
    return (f"Selection, counts only: matched {cell['matched']}"
            f" · live-only {cell['live_only']['n']} · replay-only {cell['replay_only']['n']}"
            f" · outside the replay (strategy-sourced) {cell['outside_replay']}"
            f" · still open {still_open} · unfilled {unfilled}")
```

Why each tamper test fails where it does: a changed `exit` effect leaves `build_table` consistent with the rows but breaks the first chain (`live_gross`); a changed `r_live_net` breaks the second chain (`live_net`) and the book check; a changed line breaks the re-derivation (`line backtest`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_table.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/table.py tests/scout/test_reconcile_table.py
git commit -m "feat(v232): per-direction reconciliation table and its self-check"
```
