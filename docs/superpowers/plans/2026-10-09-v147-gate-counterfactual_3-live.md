# v147 Gate counterfactual: Part 3, live recording and the resolver core (V147-9..V147-11)

> Part of the v147 plan. Header, Global Constraints, deviations, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v147-gate-counterfactual_0-index.md). **Never read this file whole**: `/task-brief V147-10` or `grep -n "^### Task V147-10:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_3-live.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md) § Live side (Store, Write path, Nightly resolver), § The counterfactual simulator / Price basis, § Gates covered and their margin, § Testing (block points, resolver bullets).

All commands run inside the plan's worktree `.claude/worktrees/2026-10-09-v147-gate-counterfactual` (created by V147-1). Paths below are relative to it.

Order (index § Parallelisation): V147-9 needs V147-3 (`pinned_scan_params`, `scenario_to_dict`) and V147-7 (`gate_rejections_repo`); V147-10 needs V147-9; V147-11 needs V147-3 + V147-7 and may run beside V147-9/-10. V147-12 (the loop that schedules V147-11) is in [`_3b-resolver-loop`](2026-10-09-v147-gate-counterfactual_3b-resolver-loop.md), split off for the 1500-line cap.

**Two decisions this part makes, both inside the ledger's contracts:**

1. **Intraday price basis.** The confluence and short-lane scans run during the session, so the frame the gate saw usually ends in today's *forming* bar. Its close is not the close the cache will hold, so storing it as `signal_close` would make the resolver "re-anchor" on ordinary intraday drift. The recorder therefore keeps `signal_date` = the frame's last bar date (the live constructor's own `plan.created_at`, so the blocked and taken arms start their walks on the same bar) and stores `signal_close` only when that bar is completed (`strategy_pass.completed_frame` keeps it). For a forming bar it stores `signal_close = None` plus `basis_date` / `basis_close`, the last completed bar the scan saw. The resolver (V147-11) turns those into the implied write-basis signal close (`cache_close(signal_date) / (cache_close(basis_date) / basis_close)`), so `simulate_blocked`'s unchanged re-anchor test fires exactly when the basis bar was adjusted after the write.
2. **Additive doc keys** (no shared signature changes): `basis_date`, `basis_close` (above); `pending_checked_on` (the session a grace bump counted, so a second run on one day never double-counts) and `cf_plan` (the plan the walk used, stored or rebuilt) written by the resolver. V147-14 may read `cf_plan` for `expiry_bars` / `planned_loss_pct` of rebuilt rows. `record_strategy_block` gains one optional keyword, `entry_context=None`, so a compression row keeps its `compression_mode` stamp.

---

# Phase 3: Live recording

### Task V147-9: Fail-open `record_rejection` helper + snapshot adapters

**Model:** opus — the write path sits inside the live scan's serial merge; a raise here, or a swallowed DB error leaking into `write_failure`, would halt issuance, and the price-basis snapshot decides whether the resolver re-anchors correctly.

**Files:**
- Create: `swingbot/core/scanning/rejection_recorder.py`
- Modify: `swingbot/core/edge/rs_gate.py` (append `rs_margin`)
- Create: `tests/scanning/test_rejection_recorder.py`

**Interfaces (ledger):**
- `rs_gate.rs_margin(rs_value: float) -> float`: `rs_value − RS_LAGGARD_PERCENTILE` read at call time (the spec's margin; positive = the blocked side of the bearish line). The only live RS arm is bearish (`rs_gate` module docstring).
- `record_rejection(*, ticker, gate, reason, source, strategy, horizon, direction, signal_date, frame, margin=None, plan=None, scenario=None, scan_params=None, entry_context=None) -> bool`: True when a new row was written; never raises.
- `record_strategy_block(deps, frame, *, ticker, strategy, horizon, direction, gate, reason, entry_context=None) -> bool` (`entry_context` is the additive keyword, part header).
- `record_item_block(item, frames: dict, gate: str, reason: str, *, source: str) -> bool`.
- `record_short_verdict(verdict, frames: dict) -> bool`.
- Module-level `_repo()` factory (tests monkeypatch it) and `_utc_now()`.

Consumes: `gate_counterfactual.pinned_scan_params`, `scenario_to_dict` (V147-3); `gate_rejections.gate_rejections_repo` and its `insert_ignore(record) -> bool` (V147-7). Verified at HEAD: `strategy_pass.completed_frame` (`swingbot/core/scanning/strategy_pass.py:24`), `builders.primary_strategy_for` (`swingbot/core/planning/builders.py:518`), `plan_types.plan_to_dict` / `plan_from_dict` (`swingbot/core/planning/plan_types.py:185/192`), `spot_metals.is_spot_metal` (`swingbot/core/marketdata/spot_metals.py:53`), `ScanParams.from_config` (`swingbot/scan_params.py:97`), `qualify.Accepted` / `Rejected(item, stage, reason)` (`swingbot/core/scanning/qualify.py`).

The record it builds is the index's "`gate_rejections` record": promoted `ticker, gate, strategy, horizon, signal_date, cf_status, created_at, resolved_at`; in `doc` `reason, margin, direction, source, plan, scenario, scan_params, signal_close, entry_context, heat_before (None), heat_cap (None)`, plus `basis_date` / `basis_close` when the signal bar was forming (part header, decision 1). `reason == "no_qualifying_target"` rows are written `cf_status = "no-plan"` with `resolved_at = created_at` (index deviation). `created_at` / `resolved_at` are tz-aware `datetime`s (the repository binds them to `TIMESTAMPTZ`).

`scan_params` is `pinned_scan_params(strategy, plan=<the stored plan or None>, params=ScanParams.from_config())`: the live constructors are called without `scan_params`, so they read `ScanParams.from_config()` at build time; pinning it here, at block time, is that same value.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_rejection_recorder.py`:

```python
"""v147 V147-9: the fail-open live gate-rejection recorder."""
import datetime as dt
import logging
from types import SimpleNamespace

import pytest

from swingbot.core.edge import rs_gate
from swingbot.core.market.levels import Scenario
from swingbot.core.planning.builders import primary_strategy_for
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.scanning import qualify
from swingbot.core.scanning import rejection_recorder as rr
from tests.helpers import make_ohlcv

UTC = dt.timezone.utc
AFTER_CLOSE = dt.datetime(2024, 2, 26, 22, 0, tzinfo=UTC)   # 17:00 ET: the 2024-02-26 bar is complete
INTRADAY = dt.datetime(2024, 2, 26, 15, 0, tzinfo=UTC)      # 10:00 ET: the 2024-02-26 bar is forming


class FakeRepo:
    def __init__(self, fail=False):
        self.records, self.fail = [], fail

    def insert_ignore(self, record):
        if self.fail:
            raise RuntimeError("database down")
        self.records.append(record)
        return True


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(rr, "_repo", lambda: fake)
    monkeypatch.setattr(rr, "_utc_now", lambda: AFTER_CLOSE)
    return fake


def _frame():
    frame = make_ohlcv([100.0 + 0.1 * i for i in range(40)], start="2024-01-02")
    assert frame.index[-1].date().isoformat() == "2024-02-26"      # close 103.9; 2024-02-23 close 103.8
    return frame


def _scenario():
    return Scenario(direction="bearish", entry=103.9, market_price=103.9, stop_loss=106.0,
                    stop_sources=["Rolling resistance"], stop_distance_pct=2.02, tight_stop=False,
                    atr_floor_pct=1.5, take_profit=98.0, target_distance_pct=5.7,
                    target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
                    target2_sources=None)


def _plan():
    return TradePlanV2(plan_id="p1", ticker="AAPL", created_at="2024-02-26", source="confluence",
                       strategy="Fibonacci", horizon_key="4w", direction="bearish",
                       entry_type="stop_entry", trigger_price=103.9, entry_price=None, expiry_bars=5,
                       stop_loss=106.5, tp1=98.0, tp1_fraction=0.5, tp2=95.0,
                       breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                       quality_breakdown=[], badge="WEAK", badge_stats={},
                       status=PlanStatus.PENDING, status_history=[])


def _item(**over):
    base = dict(result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend="bearish"),
                plan=_scenario(), rs_combined=40.0, plan_v2_rejected_plan=None,
                plan_v2_rejected_margin=None)
    base.update(over)
    return SimpleNamespace(**base)


def _kwargs(**over):
    base = dict(ticker="AAPL", gate="rs", reason="rs_blocked", source="confluence",
                strategy="Fibonacci", horizon="4w", direction="bearish", signal_date="2024-02-26",
                frame=_frame(), margin=15.0, scenario=_scenario())
    base.update(over)
    return base


@pytest.mark.parametrize("value", [5.0, 24.9, 25.0, 25.1, 40.0, 90.0])
def test_rs_margin_is_positive_exactly_where_the_bearish_gate_blocks(value):
    blocked = rs_gate.rs_verdict("AAPL", "bearish", value, rs_available=True)["status"] == "block"
    assert (rs_gate.rs_margin(value) > 0) == blocked
    assert rs_gate.rs_margin(value + 1.0) - rs_gate.rs_margin(value) == pytest.approx(1.0)


def test_a_completed_signal_bar_is_stored_as_the_price_basis(repo):
    assert rr.record_rejection(**_kwargs()) is True
    (row,) = repo.records
    assert row["signal_date"] == "2024-02-26" and row["signal_close"] == pytest.approx(103.9)
    assert "basis_date" not in row
    assert row["cf_status"] == "pending" and row["resolved_at"] is None
    assert row["created_at"] == AFTER_CLOSE
    assert "heat_before" in row and row["heat_before"] is None
    assert "heat_cap" in row and row["heat_cap"] is None
    assert row["scenario"]["entry"] == 103.9 and row["plan"] is None
    assert row["margin"] == 15.0 and row["source"] == "confluence"


def test_a_forming_signal_bar_stores_the_last_completed_bar_as_the_basis(repo, monkeypatch):
    monkeypatch.setattr(rr, "_utc_now", lambda: INTRADAY)
    rr.record_rejection(**_kwargs())
    (row,) = repo.records
    assert row["signal_date"] == "2024-02-26"            # the live constructor's created_at
    assert row["signal_close"] is None
    assert row["basis_date"] == "2024-02-23" and row["basis_close"] == pytest.approx(103.8)


def test_no_qualifying_target_is_inserted_already_no_plan(repo):
    rr.record_rejection(**_kwargs(gate="plan_rejected", reason="no_qualifying_target", margin=None))
    (row,) = repo.records
    assert row["cf_status"] == "no-plan" and row["resolved_at"] == row["created_at"] == AFTER_CLOSE


def test_a_plan_object_is_stored_as_its_dict(repo):
    plan = _plan()
    rr.record_rejection(**_kwargs(gate="plan_rejected", reason="risk_cap", plan=plan))
    assert repo.records[0]["plan"] == plan_to_dict(plan)


def test_spot_metals_are_never_stored(repo):
    assert rr.record_rejection(**_kwargs(ticker="XAUUSD")) is False
    assert repo.records == []


def test_a_failing_write_returns_false_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(rr, "_repo", lambda: FakeRepo(fail=True))
    monkeypatch.setattr(rr, "_last_warning", None)
    with caplog.at_level(logging.DEBUG, logger=rr.__name__):
        assert rr.record_rejection(**_kwargs()) is False
        assert rr.record_rejection(**_kwargs()) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "scan unaffected" in warnings[0].getMessage()


def test_a_snapshot_that_cannot_be_built_never_raises(repo):
    assert rr.record_rejection(**_kwargs(frame=None)) is False
    assert rr.record_item_block(_item(), {}, "rs", "rs_blocked", source="confluence") is False
    assert repo.records == []


def test_strategy_rs_block_carries_the_margin_and_the_pins(repo):
    deps = SimpleNamespace(rs_combined_of=lambda ticker: 40.0)
    assert rr.record_strategy_block(deps, _frame(), ticker="AAPL", strategy="RSI", horizon="2w",
                                    direction="bearish", gate="rs", reason="rs_blocked") is True
    (row,) = repo.records
    assert row["source"] == "strategy" and row["strategy"] == "RSI" and row["horizon"] == "2w"
    assert row["margin"] == pytest.approx(rs_gate.rs_margin(40.0))
    assert row["plan"] is None and row["scenario"] is None
    assert {"stop_mult", "tp2_r", "time_stop_days", "params"} <= set(row["scan_params"])
    assert row["scan_params"]["params"]                        # ScanParams pinned at block time


def test_strategy_compression_block_keeps_its_stamp_and_has_no_margin(repo):
    deps = SimpleNamespace(rs_combined_of=lambda ticker: None)
    rr.record_strategy_block(deps, _frame(), ticker="AAPL", strategy="Compression Short",
                             horizon="2w", direction="bearish", gate="compression",
                             reason="earnings_blackout", entry_context={"compression_mode": "broad"})
    (row,) = repo.records
    assert row["gate"] == "compression" and row["reason"] == "earnings_blackout"
    assert row["margin"] is None and row["entry_context"] == {"compression_mode": "broad"}


def test_confluence_rs_block_is_labelled_with_the_primary_strategy(repo):
    item = _item()
    assert rr.record_item_block(item, {"AAPL": _frame()}, "rs", "rs_blocked", source="confluence")
    (row,) = repo.records
    assert row["strategy"] == primary_strategy_for(item.plan)
    assert row["margin"] == pytest.approx(rs_gate.rs_margin(40.0))
    assert row["scenario"]["stop_loss"] == 106.0 and row["direction"] == "bearish"


def test_risk_cap_block_uses_the_stamped_plan_and_margin(repo):
    plan = plan_to_dict(_plan())
    item = _item(plan_v2_rejected_plan=plan, plan_v2_rejected_margin=0.5)
    rr.record_item_block(item, {"AAPL": _frame()}, "plan_rejected", "risk_cap", source="confluence")
    (row,) = repo.records
    assert row["plan"] == plan and row["margin"] == 0.5 and row["cf_status"] == "pending"


def test_an_rs_row_never_carries_a_rejected_plan(repo):
    item = _item(plan_v2_rejected_plan=plan_to_dict(_plan()), plan_v2_rejected_margin=0.5)
    rr.record_item_block(item, {"AAPL": _frame()}, "rs", "rs_blocked", source="confluence")
    assert repo.records[0]["plan"] is None


def test_short_verdicts_map_rs_and_plan_stages_only(repo):
    frames = {"AAPL": _frame()}
    assert rr.record_short_verdict(qualify.Rejected(_item(), "rs", "rs_blocked"), frames)
    assert rr.record_short_verdict(qualify.Rejected(_item(), "plan", "no_qualifying_target"), frames)
    assert not rr.record_short_verdict(qualify.Rejected(_item(), "confirmation", "unmet"), frames)
    assert not rr.record_short_verdict(qualify.Rejected(_item(), "trade_decision", "existing_trade"),
                                       frames)
    assert not rr.record_short_verdict(qualify.Accepted(_item()), frames)
    assert [(r["gate"], r["source"], r["cf_status"]) for r in repo.records] == [
        ("rs", "short_lane", "pending"), ("plan_rejected", "short_lane", "no-plan")]


def test_the_default_repo_is_the_lazy_singleton():
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    assert rr._repo() is gate_rejections_repo()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_rejection_recorder.py`
Expected: FAIL, collection error `ImportError: cannot import name 'rejection_recorder'`.

- [ ] **Step 3: Add `rs_margin` to `swingbot/core/edge/rs_gate.py`**

Append at the end of the file:

```python


def rs_margin(rs_value: float) -> float:
    """v147: signed distance of an RS reading past the bearish laggard line.

    Positive = the blocked side. The only live arm of this gate is bearish
    (module docstring), so the margin is measured against the laggard
    threshold, read at call time like rs_verdict reads it. Measurement only:
    nothing decides on this value."""
    return float(rs_value) - float(config.RS_LAGGARD_PERCENTILE)
```

- [ ] **Step 4: Write the recorder**

Create `swingbot/core/scanning/rejection_recorder.py`:

```python
"""v147: fail-open recording of live gate rejections into `gate_rejections`.

Called once at each live block point -- the strategy pass loop
(`strategy_pass._emit_signal`), `_sync_run_scan`'s serial merge and
`short_run._qualified_items` -- never from a `map_tickers` worker and never
from `qualify.py` (shared with the outlook and the replays). Every entry point
catches `Exception`, logs at most one warning per WARN_INTERVAL_S and returns
False: the gate's own decision never depends on the write, and a swallowed
database error must never reach `write_failure.is_store_write_failure`, which
would halt issuance.

Price basis (spec § Price basis). `signal_date` is the last bar of the frame
the gate saw -- the live constructor's own `created_at`. Its close is stored as
`signal_close` only when that bar is completed; an intraday scan's forming bar
stores `basis_date`/`basis_close` (the last completed bar) instead, which the
resolver (`backtesting/gate_resolver.py`) turns into the implied write-basis
close.

Heat at block time is stored as None (`heat_before`, `heat_cap`): heat is
computed in `analyze.build_decision_context` after a plan exists, which no
reject site reaches.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from swingbot.core.edge.rs_gate import rs_margin
from swingbot.core.marketdata.spot_metals import is_spot_metal

log = logging.getLogger(__name__)

WARN_INTERVAL_S = 600.0
NO_PLAN_REASONS = frozenset({"no_qualifying_target"})
_SHORT_GATES = {"rs": "rs", "plan": "plan_rejected"}   # qualify.Rejected.stage -> gate
_last_warning: float | None = None


def _repo():
    """The live store; tests monkeypatch this factory."""
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    return gate_rejections_repo()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _warn(what: str) -> None:
    """One warning per WARN_INTERVAL_S, the rest at DEBUG: a down database must not flood the log."""
    global _last_warning
    now = time.monotonic()
    if _last_warning is None or now - _last_warning >= WARN_INTERVAL_S:
        _last_warning = now
        log.warning("gate rejection not recorded (%s) -- scan unaffected", what, exc_info=True)
        return
    log.debug("gate rejection not recorded (%s)", what, exc_info=True)


def _bar_date(frame) -> str:
    return frame.index[-1].date().isoformat()


def _basis(frame, now: dt.datetime) -> dict:
    """`signal_close` when the signal bar is completed; else the last completed bar as the basis."""
    from swingbot.core.scanning.strategy_pass import completed_frame
    done = completed_frame(frame, now)
    if len(done) == len(frame):
        return {"signal_close": float(frame["Close"].iloc[-1])}
    if len(done) == 0:
        return {"signal_close": None, "basis_date": None, "basis_close": None}
    return {"signal_close": None, "basis_date": _bar_date(done),
            "basis_close": float(done["Close"].iloc[-1])}


def _as_dict(value, to_dict):
    if value is None or isinstance(value, dict):
        return value
    return to_dict(value)


def _snapshot(fields: dict, frame, now: dt.datetime) -> dict:
    """The flat `gate_rejections` record; the repository splits promoted columns from `doc`."""
    from swingbot.core.backtesting.gate_counterfactual import scenario_to_dict
    from swingbot.core.planning.plan_types import plan_to_dict
    no_plan = fields["reason"] in NO_PLAN_REASONS
    margin = fields["margin"]
    return {**fields,
            "margin": None if margin is None else float(margin),
            "plan": _as_dict(fields["plan"], plan_to_dict),
            "scenario": _as_dict(fields["scenario"], scenario_to_dict),
            "entry_context": dict(fields["entry_context"] or {}),
            "cf_status": "no-plan" if no_plan else "pending",
            "created_at": now,
            "resolved_at": now if no_plan else None,
            "heat_before": None, "heat_cap": None,
            **_basis(frame, now)}


def record_rejection(*, ticker, gate, reason, source, strategy, horizon, direction, signal_date,
                     frame, margin=None, plan=None, scenario=None, scan_params=None,
                     entry_context=None) -> bool:
    """Insert one blocked candidate. True when a new row was written; never raises."""
    if is_spot_metal(ticker):
        return False
    fields = {"ticker": ticker, "gate": gate, "reason": reason, "source": source,
              "strategy": strategy, "horizon": horizon, "direction": direction,
              "signal_date": signal_date, "margin": margin, "plan": plan, "scenario": scenario,
              "scan_params": scan_params, "entry_context": entry_context}
    try:
        return bool(_repo().insert_ignore(_snapshot(fields, frame, _utc_now())))
    except Exception:   # noqa: BLE001 -- fail-open: a recording failure never touches the scan
        _warn(f"{ticker} {gate} {strategy} {horizon}")
        return False


def _record_built(label: str, build) -> bool:
    """record_rejection(**build()), with a failure while building the arguments swallowed too."""
    try:
        kwargs = build()
    except Exception:   # noqa: BLE001 -- fail-open
        _warn(label)
        return False
    return record_rejection(**kwargs)


def _scan_params(strategy: str, plan: dict | None) -> dict:
    """The pinned overrides and ScanParams as they stood at the block (V147-3)."""
    from swingbot.core.backtesting.gate_counterfactual import pinned_scan_params
    from swingbot.core.planning.plan_types import plan_from_dict
    from swingbot.scan_params import ScanParams
    return pinned_scan_params(strategy, plan=plan_from_dict(plan) if plan else None,
                              params=ScanParams.from_config())


def _strategy_margin(deps, ticker: str, gate: str) -> float | None:
    if gate != "rs":
        return None
    value = deps.rs_combined_of(ticker)
    return None if value is None else rs_margin(float(value))


def record_strategy_block(deps, frame, *, ticker, strategy, horizon, direction, gate, reason,
                          entry_context=None) -> bool:
    """L1 (rs) / L2 (compression) in `strategy_pass._emit_signal`; `frame` is the completed frame."""
    def build() -> dict:
        return dict(ticker=ticker, gate=gate, reason=reason, source="strategy", strategy=strategy,
                    horizon=horizon, direction=direction, signal_date=_bar_date(frame),
                    frame=frame, margin=_strategy_margin(deps, ticker, gate),
                    scan_params=_scan_params(strategy, None), entry_context=entry_context)
    return _record_built(f"{ticker} {gate} {strategy} {horizon}", build)


def _item_margin(item, gate: str) -> float | None:
    if gate == "rs":
        value = getattr(item, "rs_combined", None)
        return None if value is None else rs_margin(float(value))
    return getattr(item, "plan_v2_rejected_margin", None)


def _item_fields(item, frames, gate: str, reason: str, source: str) -> dict:
    from swingbot.core.planning.builders import primary_strategy_for
    result, scenario = item.result, item.plan
    frame = frames.get(result.ticker)
    strategy = primary_strategy_for(scenario)
    plan = getattr(item, "plan_v2_rejected_plan", None) if gate == "plan_rejected" else None
    return dict(ticker=result.ticker, gate=gate, reason=reason, source=source, strategy=strategy,
                horizon=result.horizon_key, direction=result.trend, signal_date=_bar_date(frame),
                frame=frame, margin=_item_margin(item, gate), plan=plan, scenario=scenario,
                scan_params=_scan_params(strategy, plan))


def record_item_block(item, frames: dict, gate: str, reason: str, *, source: str) -> bool:
    """L3/L4 (`_sync_run_scan` merge, source "confluence") and L5/L6 (source "short_lane")."""
    ticker = getattr(getattr(item, "result", None), "ticker", "?")
    return _record_built(f"{ticker} {gate} {reason}",
                         lambda: _item_fields(item, frames, gate, reason, source))


def record_short_verdict(verdict, frames: dict) -> bool:
    """One `qualify_short_item` verdict from the live short lane: rs and plan stages only."""
    gate = _SHORT_GATES.get(getattr(verdict, "stage", None))
    if gate is None:
        return False
    return record_item_block(verdict.item, frames, gate, verdict.reason, source="short_lane")
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_rejection_recorder.py`
Expected: PASS, `20 passed`, `0 failed`.

If `test_a_forming_signal_bar_...` fails because `completed_frame` kept the bar, check `session.is_regular_session(INTRADAY)` is True (2024-02-26 is a Monday session, 10:00 ET); never move the clock outside RTH to make it pass.

- [ ] **Step 6: Neighbouring suites, complexity, syntax**

Run: `python scripts/dev/testrun.py file tests/scanning/test_rs_gate_wiring.py`
Expected: PASS, `0 failed` (`rs_gate` gained a function only).

Run: `python -m radon cc -s -n C swingbot/core/scanning/rejection_recorder.py swingbot/core/edge/rs_gate.py && python -m py_compile swingbot/core/scanning/rejection_recorder.py swingbot/core/edge/rs_gate.py`
Expected: no radon output, no error.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/rejection_recorder.py swingbot/core/edge/rs_gate.py tests/scanning/test_rejection_recorder.py
git commit -m "feat(v147): fail-open live gate-rejection recorder and rs_margin (V147-9)"
```

### Task V147-10: Live hooks at L1–L6

**Model:** opus — four live-scan files, one of them the F(100) `_sync_run_scan`; each hook must be one call with no new branch, and the end-to-end tests must prove the scan result is unchanged with the store down.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (`ScanItem` gains two fields; `_reject_plan` gains `plan=`/`margin=`; `attach_plan_v2` passes them on `risk_cap`)
- Modify: `swingbot/core/scanning/strategy_pass.py` (`_emit_signal`: L1, L2)
- Modify: `swingbot/core/scanning/scan_run.py` (`_sync_run_scan` merge loop: L3, L4)
- Modify: `swingbot/core/scanning/short_run.py` (`_qualified_items`: L5, L6)
- Create: `tests/scanning/test_gate_rejection_hooks.py`

**Interfaces:**
- Creates (ledger): `analyze._reject_plan(item, reason, ticker, horizon_key, *, plan=None, margin=None)` stamping `item.plan_v2_rejected_plan: dict | None` (`plan_to_dict`, `None` when no plan or the snapshot fails) and `item.plan_v2_rejected_margin: float | None` (`planned_loss_pct − HARD_MAX_PLANNED_LOSS_PCT` for `risk_cap`, else `None`). Both are also declared on `ScanItem` with default `None`.
- Consumes (V147-9): `rejection_recorder.record_strategy_block`, `record_item_block`, `record_short_verdict`.

The hook sites, verified at HEAD (index § Block-point enumeration; V147-1's results doc is the authority if it moved anything):

| # | Site | Added call |
|---|---|---|
| L1 | `strategy_pass._emit_signal`, after `result.rs_blocked += 1` | `record_strategy_block(..., gate="rs", reason="rs_blocked")` |
| L2 | `strategy_pass._emit_signal`, after `_count_compression_reject(...)` | `record_strategy_block(..., gate="compression", reason=reject_reason, entry_context=stamp)` |
| L3 | `scan_run._sync_run_scan`, after `funnel.record_item(item, "rs", "rs_blocked")` | `record_item_block(item, fresh_data, "rs", "rs_blocked", source="confluence")` |
| L4 | `scan_run._sync_run_scan`, after `_skip_rejected_plan(item, require_confirmation)` (inside the existing `PLAN_ENGINE_V2 == "on"` branch, so `shadow` records nothing: it drops nothing) | `record_item_block(item, fresh_data, "plan_rejected", item.plan_v2_rejected, source="confluence")` |
| L5/L6 | `short_run._qualified_items`, after `qualify.record_verdict(...)` | `record_short_verdict(verdict, frames)` |

Never touched: `analyze._scan_one` (runs in `map_tickers` workers), `analyze.build_decision_context`, `qualify.py` (shared with `outlook_run` and `scan_replay`).

- [ ] **Step 1: Record the complexity baseline**

Run: `python -m radon cc -s swingbot/core/scanning/scan_run.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/short_run.py swingbot/core/scanning/analyze.py | grep -E "_sync_run_scan|_emit_signal|_qualified_items|_reject_plan|attach_plan_v2"`
Expected: `_sync_run_scan` F (100), `_emit_signal` C (11), `attach_plan_v2` B (9), the other two A. Write the five numbers down; Step 9 compares against them.

- [ ] **Step 2: Write the failing tests**

Create `tests/scanning/test_gate_rejection_hooks.py`:

```python
"""v147 V147-10: each live block point (L1-L6) writes exactly one gate_rejections row with the
right gate/reason/margin, and a failing write leaves the scan result identical."""
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge import rs_gate
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.core.scanning import (analyze, dedup, engine, qualify, rejection_recorder, scan_run,
                                    short_run)
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv
from tests.scanning import test_engine_v2_plans as v2
from tests.scanning import test_rs_gate_wiring as rsw
from tests.scanning.test_rejection_recorder import _scenario
from tests.store_seed import seed_store

FRAME = make_ohlcv([100.0 + 0.1 * i for i in range(40)], start="2024-01-02")
BAR_DATE = FRAME.index[-1].date().isoformat()
HIGH_RS = 99.0          # above any laggard line: a bearish setup here is blocked


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """Same isolation as test_engine_v2_plans.py: _sync_run_scan reads the account and
    writes telemetry, neither of which may touch the real data/."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


class FakeRepo:
    def __init__(self, fail=False):
        self.records, self.fail, self.attempts = [], fail, 0

    def insert_ignore(self, record):
        self.attempts += 1
        if self.fail:
            raise RuntimeError("database down")
        self.records.append(record)
        return True


def _use(monkeypatch, fake):
    monkeypatch.setattr(rejection_recorder, "_repo", lambda: fake)
    return fake


@pytest.fixture
def repo(monkeypatch):
    return _use(monkeypatch, FakeRepo())


# --- L1 / L2: the strategy pass ---------------------------------------------------------

class _Store:
    def all(self):
        return []

    def add(self, plan):
        raise AssertionError("a blocked signal must never be stored")


class _Log:
    def open_trade_for_ticker(self, ticker):
        return None


def _deps(rs=None):
    return sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="live", live_allow=set(),
                        rs_combined_of=lambda ticker: rs, asof_of=None)


def _emit(deps, *, strategy="RSI", direction="bearish"):
    result = sp.PassResult()
    sp._emit_signal(result, FRAME, ticker="AAPL", strategy=strategy, direction=direction,
                    horizon="2w", bar_date=BAR_DATE, regime=None, deps=deps)
    return result


def test_strategy_rs_block_writes_one_row(repo):
    assert sp._rs_blocked("AAPL", "bearish", lambda ticker: HIGH_RS)
    result = _emit(_deps(rs=HIGH_RS))
    assert result.rs_blocked == 1
    (row,) = repo.records
    assert (row["gate"], row["reason"], row["source"]) == ("rs", "rs_blocked", "strategy")
    assert row["margin"] == pytest.approx(rs_gate.rs_margin(HIGH_RS))
    assert row["signal_date"] == BAR_DATE and row["strategy"] == "RSI" and row["horizon"] == "2w"


def test_strategy_compression_block_writes_one_row(repo, monkeypatch):
    monkeypatch.setattr(sp, "_dryup_blocked", lambda *a, **k: False)
    monkeypatch.setattr(sp, "_compression_context",
                        lambda *a, **k: ({"compression_mode": "isolated"}, "earnings_blackout"))
    result = _emit(_deps(), strategy=COMPRESSION_SHORT)
    assert result.compression_rejected == 1
    (row,) = repo.records
    assert (row["gate"], row["reason"], row["margin"]) == ("compression", "earnings_blackout", None)
    assert row["entry_context"] == {"compression_mode": "isolated"}


def test_an_unblocked_signal_with_no_plan_writes_nothing(repo, monkeypatch):
    monkeypatch.setattr(sp, "_dryup_blocked", lambda *a, **k: False)
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: None)
    _emit(_deps(), direction="bullish")                 # O1: no geometry, not one of the gates
    assert repo.records == []


def test_a_failing_write_leaves_the_strategy_pass_identical(monkeypatch):
    ok = _use(monkeypatch, FakeRepo())
    expected = vars(_emit(_deps(rs=HIGH_RS)))
    down = _use(monkeypatch, FakeRepo(fail=True))
    assert vars(_emit(_deps(rs=HIGH_RS))) == expected
    assert ok.records and down.attempts == 1


# --- L3 / L4: the confluence merge in _sync_run_scan ------------------------------------

def _count_rs_blocks(monkeypatch) -> list:
    blocks, real = [], scan_run.rs_verdict

    def spy(*args, **kwargs):
        verdict = real(*args, **kwargs)
        if verdict["status"] == "block":
            blocks.append(args[0])
        return verdict
    monkeypatch.setattr(scan_run, "rs_verdict", spy)
    return blocks


def test_confluence_rs_block_writes_one_row_per_blocked_scenario(repo, monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    blocks = _count_rs_blocks(monkeypatch)
    items, _funnel = rsw._scan_with_funnel(ticker="AAPL", direction="bearish", rs=HIGH_RS)
    rows = [r for r in repo.records if r["source"] == "confluence"]
    assert items == [] and blocks, "fixture must block at least one bearish scenario"
    assert len(rows) == len(blocks)
    signal_date = rsw._structured_df().index[-1].date().isoformat()
    for row in rows:
        assert (row["gate"], row["reason"], row["direction"]) == ("rs", "rs_blocked", "bearish")
        assert row["margin"] == pytest.approx(rs_gate.rs_margin(HIGH_RS))
        assert row["signal_date"] == signal_date and row["signal_close"] is not None
        assert row["scenario"] is not None and row["plan"] is None


def _keys(items):
    return sorted((i.result.ticker, i.result.horizon_key, i.result.trend) for i in items)


def test_a_failing_write_leaves_the_confluence_scan_identical(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", True)
    ok = _use(monkeypatch, FakeRepo())
    items_ok, funnel_ok = rsw._scan_with_funnel(ticker="AAPL", direction="bullish", rs=HIGH_RS)
    down = _use(monkeypatch, FakeRepo(fail=True))
    items_down, funnel_down = rsw._scan_with_funnel(ticker="AAPL", direction="bullish", rs=HIGH_RS)
    assert ok.records and down.attempts == ok.attempts
    assert _keys(items_down) == _keys(items_ok) and funnel_down == funnel_ok


def test_confluence_plan_rejection_writes_one_no_plan_row(repo, monkeypatch, tmp_path,
                                                          stub_batch_fetch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "RS_GATE", False)        # every scenario must reach the plan stage
    v2._setup_minimal_scan(monkeypatch, tmp_path)
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    skipped, real_skip = [], scan_run._skip_rejected_plan
    monkeypatch.setattr(scan_run, "_skip_rejected_plan",
                        lambda item, rc: skipped.append(item) or real_skip(item, rc))
    monkeypatch.setattr(dedup, "dedup_scan_items", lambda items: [])
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)
    rows = [r for r in repo.records if r["gate"] == "plan_rejected"]
    assert skipped, "fixture must reject at least one plan"
    assert len(rows) == len(skipped)
    for row in rows:
        assert row["reason"] == "no_qualifying_target" and row["cf_status"] == "no-plan"
        assert row["resolved_at"] == row["created_at"] and row["plan"] is None
        assert row["margin"] is None and row["source"] == "confluence"


# --- analyze: the stamps the L4/L6 rows read --------------------------------------------

def test_risk_cap_rejection_stamps_the_plan_and_its_margin(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    item = SimpleNamespace(plan_v2=None)
    analyze.attach_plan_v2(item, v2._gc_scenario(), make_ohlcv([4194.30] * 60), "GC=F", "4w",
                           level_map=None)
    assert item.plan_v2_rejected == "risk_cap"
    plan = item.plan_v2_rejected_plan
    loss = planned_loss_pct(plan["trigger_price"], plan["stop_loss"])
    assert item.plan_v2_rejected_margin == pytest.approx(loss - HARD_MAX_PLANNED_LOSS_PCT)
    assert item.plan_v2_rejected_margin > 0


def test_no_qualifying_target_clears_any_earlier_stamp(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    item = SimpleNamespace(plan_v2=None, plan_v2_rejected_plan={"stale": 1},
                           plan_v2_rejected_margin=9.9)
    analyze.attach_plan_v2(item, v2._scenario(), make_ohlcv([100.0] * 60), "AAPL", "4w",
                           level_map=None)
    assert item.plan_v2_rejected == "no_qualifying_target"
    assert item.plan_v2_rejected_plan is None and item.plan_v2_rejected_margin is None


def test_scan_items_default_to_no_rejected_plan():
    item = analyze.ScanItem(result=None, plan=None, conf=None)
    assert item.plan_v2_rejected_plan is None and item.plan_v2_rejected_margin is None


# --- L5 / L6: the short lane ------------------------------------------------------------

def _short_item(ticker):
    return SimpleNamespace(result=SimpleNamespace(ticker=ticker, horizon_key="4w", trend="bearish"),
                           plan=_scenario(), rs_combined=HIGH_RS, plan_v2_rejected_plan=None,
                           plan_v2_rejected_margin=0.4, candidate_context={"source": "short_universe"})


_VERDICTS = {"AAA": lambda i: qualify.Rejected(i, "rs", "rs_blocked"),
             "BBB": lambda i: qualify.Rejected(i, "plan", "risk_cap"),
             "CCC": lambda i: qualify.Rejected(i, "confirmation", "awaiting_confirmation"),
             "DDD": lambda i: qualify.Accepted(i)}


def _run_short_lane(monkeypatch):
    monkeypatch.setattr(qualify, "qualify_short_item",
                        lambda candidate, item, context: _VERDICTS[item.result.ticker](item))
    lane = {"spy": None, "sector_of": {}, "etf_symbol_of": {}, "sector_frames": {},
            "regime": None, "regimes": None, "funnel": None}
    items = [_short_item(t) for t in _VERDICTS]
    kept = short_run._qualified_items(items, False, {t: FRAME for t in _VERDICTS}, lane)
    return [i.result.ticker for i in kept]


def test_short_lane_records_rs_and_plan_rejections_once(repo, monkeypatch):
    assert _run_short_lane(monkeypatch) == ["DDD"]
    assert [(r["ticker"], r["gate"], r["reason"], r["source"]) for r in repo.records] == [
        ("AAA", "rs", "rs_blocked", "short_lane"), ("BBB", "plan_rejected", "risk_cap", "short_lane")]
    assert repo.records[1]["margin"] == 0.4


def test_a_failing_write_leaves_the_short_lane_identical(monkeypatch):
    _use(monkeypatch, FakeRepo(fail=True))
    assert _run_short_lane(monkeypatch) == ["DDD"]


# --- where the hooks may not live -------------------------------------------------------

def test_no_hook_in_shared_or_worker_code():
    from swingbot.core.scanning import outlook_run, scan_replay
    for module in (qualify, outlook_run, scan_replay, analyze):
        assert "rejection_recorder" not in inspect.getsource(module), module.__name__
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gate_rejection_hooks.py`
Expected: FAIL. The strategy, confluence and short-lane tests find `repo.records == []` (no hook yet); the analyze tests fail with `AttributeError: ... 'plan_v2_rejected_plan'`; `test_no_hook_in_shared_or_worker_code` passes already.

- [ ] **Step 4: `analyze.py`: the two `ScanItem` fields, `_reject_plan`, `attach_plan_v2`**

In `class ScanItem`, directly under the `plan_v2_rejected: str | None = None ...` line, add:

```python
    plan_v2_rejected_plan: dict | None = None     # v147: plan_to_dict of a risk_cap-rejected plan, for gate_rejections
    plan_v2_rejected_margin: float | None = None  # v147: planned loss % past HARD_MAX_PLANNED_LOSS_PCT (risk_cap only)
```

Replace the whole `_reject_plan` function with:

```python
def _plan_snapshot(plan) -> dict | None:
    """v147: plan_to_dict for the gate-rejection record; a failure costs the snapshot only."""
    try:
        from swingbot.core.planning.plan_types import plan_to_dict
        return plan_to_dict(plan)
    except Exception:   # noqa: BLE001 -- measurement only, never the rejection itself
        log.debug("gate: plan snapshot failed", exc_info=True)
        return None


def _reject_plan(item, reason: str, ticker: str, horizon_key: str, *, plan=None,
                 margin: float | None = None) -> None:
    """Record why no v2 plan was attached; say so at DEBUG (per symbol, per scan).

    v147: also stamp the rejected plan (when one was built) and its margin past
    the gate, which the v147 gate-rejection recorder stores. Both are reset
    on every rejection, so no stale stamp survives."""
    item.plan_v2_rejected = reason
    item.plan_v2_rejected_plan = _plan_snapshot(plan) if plan is not None else None
    item.plan_v2_rejected_margin = margin
    log.debug("gate: %s (%s) plan rejected -- %s", ticker, horizon_key, reason)
```

In `attach_plan_v2`, replace

```python
        if planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9:
```

with

```python
        loss_pct = planned_loss_pct(plan.trigger_price, plan.stop_loss)
        if loss_pct > HARD_MAX_PLANNED_LOSS_PCT + 1e-9:
```

and, inside that branch (keep its comment block unchanged), replace

```python
            _reject_plan(item, "risk_cap", ticker, horizon_key)
```

with

```python
            _reject_plan(item, "risk_cap", ticker, horizon_key, plan=plan,
                         margin=loss_pct - HARD_MAX_PLANNED_LOSS_PCT)
```

The `no_qualifying_target` call stays as it is (no plan, no margin). Confirm no other caller exists: `git grep -n "_reject_plan(" -- swingbot` must list only the definition and the two calls in `attach_plan_v2`.

- [ ] **Step 5: `strategy_pass.py`: L1 and L2**

Add to the imports (after the `alert_embeds` import):

```python
from swingbot.core.scanning import rejection_recorder
```

In `_emit_signal`, replace

```python
    if _rs_blocked(ticker, direction, deps.rs_combined_of):
        result.rs_blocked += 1
        return
```

with

```python
    if _rs_blocked(ticker, direction, deps.rs_combined_of):
        result.rs_blocked += 1
        rejection_recorder.record_strategy_block(
            deps, frame, ticker=ticker, strategy=strategy, horizon=horizon, direction=direction,
            gate="rs", reason="rs_blocked")
        return
```

and replace

```python
    if reject_reason:
        _count_compression_reject(result, stamp, reject_reason)
        return
```

with

```python
    if reject_reason:
        _count_compression_reject(result, stamp, reject_reason)
        rejection_recorder.record_strategy_block(
            deps, frame, ticker=ticker, strategy=strategy, horizon=horizon, direction=direction,
            gate="compression", reason=reject_reason, entry_context=stamp)
        return
```

- [ ] **Step 6: `scan_run.py`: L3 and L4**

Change the package import line

```python
from . import analyze, dedup, fetch, lane_overlap, progress_store, runstate, short_funnel, strategy_pass, telemetry
```

to

```python
from . import (analyze, dedup, fetch, lane_overlap, progress_store, rejection_recorder, runstate,
               short_funnel, strategy_pass, telemetry)
```

In `_sync_run_scan`'s merge loop, replace

```python
                    rs_blocked += 1
                    funnel.record_item(item, "rs", "rs_blocked")
                    continue
```

with

```python
                    rs_blocked += 1
                    funnel.record_item(item, "rs", "rs_blocked")
                    rejection_recorder.record_item_block(item, fresh_data, "rs", "rs_blocked",
                                                         source="confluence")
                    continue
```

and replace

```python
                    funnel.record_item(item, "plan", item.plan_v2_rejected)
                    _skip_rejected_plan(item, require_confirmation)
                    continue          # never reaches scan_items -> never alerts
```

with

```python
                    funnel.record_item(item, "plan", item.plan_v2_rejected)
                    _skip_rejected_plan(item, require_confirmation)
                    rejection_recorder.record_item_block(item, fresh_data, "plan_rejected",
                                                         item.plan_v2_rejected, source="confluence")
                    continue          # never reaches scan_items -> never alerts
```

- [ ] **Step 7: `short_run.py`: L5 and L6**

Change

```python
from . import analyze, dedup, fetch, lane_overlap, qualify, runstate, scan_run, short_funnel, telemetry
```

to

```python
from . import (analyze, dedup, fetch, lane_overlap, qualify, rejection_recorder, runstate, scan_run,
               short_funnel, telemetry)
```

In `_qualified_items`, replace

```python
        qualify.record_verdict(lane.get("funnel"), verdict)
```

with

```python
        qualify.record_verdict(lane.get("funnel"), verdict)
        rejection_recorder.record_short_verdict(verdict, frames)
```

- [ ] **Step 8: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gate_rejection_hooks.py`
Expected: PASS, `13 passed`, `0 failed`.

Then the suites that drive the same code:

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_rs_gate_wiring.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_emit.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_short_qualify.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py`
Expected: each `0 failed`. These now write real `gate_rejections` rows into the per-worker test database (the autouse `_store_database` fixture truncates them); a failure here is a real regression, never a reason to stub the recorder in those files.

Run: `python scripts/dev/testrun.py changed`
Expected: `0 failed`.

- [ ] **Step 9: Complexity gate (no new branch in any hot path)**

Run: `python -m radon cc -s swingbot/core/scanning/scan_run.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/short_run.py swingbot/core/scanning/analyze.py | grep -E "_sync_run_scan|_emit_signal|_qualified_items|_reject_plan|_plan_snapshot|attach_plan_v2"`
Expected: `_sync_run_scan` F (100), `_emit_signal` C (11), `_qualified_items` and `_reject_plan` unchanged from Step 1, `attach_plan_v2` B (9), `_plan_snapshot` A. Any number above its Step 1 value means a branch slipped in: move it into `rejection_recorder`.

Run: `python -m py_compile swingbot/core/scanning/analyze.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py`
Expected: no error.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/scanning/analyze.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py tests/scanning/test_gate_rejection_hooks.py
git commit -m "feat(v147): record live RS, plan-rejected and compression blocks at L1-L6 (V147-10)"
```

# Phase 4: Nightly resolver

### Task V147-11: Resolver core

**Model:** opus — due-date arithmetic over the NYSE calendar, the grace counter, the intraday price-basis bridge and the read-only-from-the-live-cache rule together decide whether every live blocked row is resolved once and reproducibly.

**Files:**
- Create: `swingbot/core/backtesting/gate_resolver.py`
- Create: `tests/backtesting/test_gate_resolver.py`

**Interfaces (ledger):** `RESOLVE_BATCH_CAP = 200`; `GRACE_SESSIONS = 5`; `due_bars(horizon: str, expiry_bars: int | None) -> int`; `resolve_due(today: str, *, limit: int = RESOLVE_BATCH_CAP, repo=None, load_bars=None) -> dict[str, int]` (counts per resulting `cf_status`, plus `"error"` for a row that raised and stays pending; default `load_bars = lambda t: data_store.load_normalized(t, "daily")`). Module helpers `_utc_now()` (tests pin it) and `_last_session_before(today) -> dt.date`.

Consumes: `gate_counterfactual.BlockedCandidate`, `CounterfactualResult`, `simulate_blocked(candidate, bars, *, last_session)`, `bars_needed(plan)`, `bars_sha256(frame)` (V147-2/-3); `GateRejectionRepository.pending(*, limit)` / `resolve(row_id, *, cf_status, resolved_at, outcome)` and `gate_rejections_repo()` (V147-7; `pending()` records carry `"id"`). Verified at HEAD: `data_store.load_normalized(ticker, interval, base_dir=...)` (`swingbot/core/marketdata/data_store.py:285`), `session.nyse_calendar()` / `SessionCalendar.is_session`, `.sessions_between(asof, target)`, `.first` (`swingbot/core/market/session.py:145-220`), `strategy_types.HORIZONS[h]["max_holding_days"]`, `data.get_daily_data_batch` (`swingbot/core/marketdata/data.py:85`, must never be called).

Rules this task fixes:
- **Bars stop at the last NYSE session strictly before `today`** (`_last_session_before`), passed to `simulate_blocked(..., last_session=...)`. The loop fires after the close, but a strict cut means a forming bar is never read whatever the clock or DST offset.
- **Due:** `sessions_between(signal_date, last_session) >= need`, where `need = bars_needed(stored plan)` when the row has one, else `due_bars(horizon, None)` (the hold alone: a lower bound, so a row is never checked late). Rows are scanned oldest first from `pending(limit=PENDING_SCAN_CAP)` (5000) and at most `limit` due rows are simulated, so a long-horizon row at the head never starves due rows behind it.
- **Grace:** a due row the simulator still calls `pending` (cache short) or whose cache file is missing is re-checked once per session (`pending_checked_on`), `pending_checks` counting up; on the check after the fifth it becomes `no-data`. A rebuilt plan whose own window (`bars_needed(result.plan)`) is still open is left untouched, not counted.
- **Price basis:** a row with `signal_close` uses it; an intraday row (`signal_close = None`, `basis_date`, `basis_close`, V147-9) gets the implied write-basis close `cache_close(signal_date) * basis_close / cache_close(basis_date)`, so `simulate_blocked`'s re-anchor test fires exactly when the basis bar was adjusted.
- **Outcome written once** through `resolve(..., outcome={cf_r, win, exit_index, last_bar_date, bars_sha256, reanchored, cf_plan})`; the repository's `WHERE cf_status = 'pending'` makes a second resolution a no-op.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_gate_resolver.py`:

```python
"""v147 V147-11: the nightly gate-rejection resolver core."""
import datetime as dt

import pytest

from swingbot.core.backtesting import gate_counterfactual as gc
from swingbot.core.backtesting import gate_resolver as gr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from tests.helpers import make_ohlcv

HOLD = int(HORIZONS["2w"]["max_holding_days"])
SIGNAL_DATE = "2024-01-04"              # index 2 of a frame starting 2024-01-02
LATE = "2024-12-31"                     # every walk window below has closed
RESOLVED_AT = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
FLAT = (100.2, 100.6, 99.8, 100.3)      # no stop, no TP1
WIN = (100.5, 103.0, 100.4, 102.5)      # TP1 (102) touched


def _plan(**kw):
    base = dict(plan_id="p1", ticker="AAPL", created_at=SIGNAL_DATE, source="confluence",
                strategy="Fibonacci", horizon_key="2w", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=102.0,
                tp1_fraction=0.5, tp2=105.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


def _frame(after=(WIN,), *, n_after=HOLD + 5, scale=1.0, start="2024-01-02"):
    rows = [(100.0, 100.5, 99.5, 100.0)] * 3 + list(after)
    rows += [FLAT] * max(0, n_after - len(after))
    return make_ohlcv([tuple(x * scale for x in r) for r in rows], start=start)


def _row(row_id=1, **over):
    base = {"id": row_id, "ticker": "AAPL", "gate": "plan_rejected", "reason": "risk_cap",
            "source": "confluence", "strategy": "Fibonacci", "horizon": "2w",
            "direction": "bullish", "signal_date": SIGNAL_DATE, "cf_status": "pending",
            "plan": _plan(), "scenario": None, "scan_params": None, "signal_close": 100.0,
            "margin": 0.3}
    base.update(over)
    return base


class FakeRepo:
    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}
        self.calls = []

    def pending(self, *, limit):
        return [dict(r) for r in self.rows.values() if r["cf_status"] == "pending"][:limit]

    def resolve(self, row_id, *, cf_status, resolved_at, outcome):
        row = self.rows[row_id]
        if row["cf_status"] != "pending":
            return False
        self.calls.append((row_id, cf_status))
        row.update(outcome, cf_status=cf_status, resolved_at=resolved_at)
        return True


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(gr, "_utc_now", lambda: RESOLVED_AT)


def _bars(frame, seen=None):
    def load(ticker):
        if seen is not None:
            seen.append(ticker)
        return frame
    return load


def test_frozen_constants():
    assert gr.RESOLVE_BATCH_CAP == 200 and gr.GRACE_SESSIONS == 5


def test_due_bars_is_the_pending_window_plus_the_hold():
    assert gr.due_bars("2w", None) == HOLD
    assert gr.due_bars("2w", 3) == HOLD + 3


def test_last_session_is_strictly_before_today():
    assert gr._last_session_before("2024-12-30") == dt.date(2024, 12, 27)    # Monday -> Friday
    assert gr._last_session_before("2024-12-26") == dt.date(2024, 12, 24)    # skips Christmas


def test_a_row_whose_window_is_open_is_untouched():
    seen, repo = [], FakeRepo([_row()])
    assert gr.resolve_due("2024-01-09", repo=repo, load_bars=_bars(_frame(), seen)) == {}
    assert repo.calls == [] and seen == []


def test_an_expired_row_resolves_once_with_a_reproducible_hash():
    frame, repo = _frame(), FakeRepo([_row()])
    assert gr.resolve_due(LATE, repo=repo, load_bars=_bars(frame)) == {"filled": 1}
    row = repo.rows[1]
    used = frame.iloc[:2 + gc.bars_needed(plan_from_dict(_plan())) + 1]
    assert row["cf_status"] == "filled" and row["win"] is True and row["cf_r"] > 0
    assert row["resolved_at"] == RESOLVED_AT and row["reanchored"] is False
    assert row["bars_sha256"] == gc.bars_sha256(used)
    assert row["last_bar_date"] == used.index[-1].date().isoformat()
    assert row["cf_plan"]["tp1"] == 102.0
    assert gr.resolve_due(LATE, repo=repo, load_bars=_bars(frame)) == {}     # never re-resolved
    assert repo.calls == [(1, "filled")]


def test_it_reads_the_live_cache_and_never_a_cold_fetch(monkeypatch):
    from swingbot.core.marketdata import data, data_store
    seen = []
    monkeypatch.setattr(data_store, "load_normalized",
                        lambda ticker, interval, **kw: seen.append((ticker, interval)) or _frame())
    monkeypatch.setattr(data, "get_daily_data_batch",
                        lambda *a, **k: pytest.fail("the resolver must never cold-fetch"))
    assert gr.resolve_due(LATE, repo=FakeRepo([_row()])) == {"filled": 1}
    assert seen == [("AAPL", "daily")]


SESSIONS = ["2024-12-03", "2024-12-04", "2024-12-05", "2024-12-06", "2024-12-09", "2024-12-10"]


def test_a_short_cache_stays_pending_through_the_grace_window_then_no_data():
    short, repo = _frame(after=(), n_after=3), FakeRepo([_row()])
    counts = [gr.resolve_due(today, repo=repo, load_bars=_bars(short)) for today in SESSIONS]
    assert counts == [{"pending": 1}] * 5 + [{"no-data": 1}]
    row = repo.rows[1]
    assert row["cf_status"] == "no-data" and row["pending_checks"] == 6
    assert row["resolved_at"] == RESOLVED_AT


def test_a_second_run_on_the_same_session_counts_no_extra_grace():
    short, repo = _frame(after=(), n_after=3), FakeRepo([_row()])
    assert gr.resolve_due(SESSIONS[0], repo=repo, load_bars=_bars(short)) == {"pending": 1}
    assert gr.resolve_due(SESSIONS[0], repo=repo, load_bars=_bars(short)) == {}
    assert repo.rows[1]["pending_checks"] == 1
    assert repo.rows[1]["pending_checked_on"] == "2024-12-02"


def test_a_missing_cache_file_waits_like_a_short_cache():
    repo = FakeRepo([_row()])
    assert gr.resolve_due(LATE, repo=repo, load_bars=lambda ticker: None) == {"pending": 1}
    assert repo.rows[1]["cf_status"] == "pending" and repo.rows[1]["pending_checks"] == 1


def test_a_missing_signal_bar_is_no_data_at_once():
    no_signal_bar = _frame(start="2024-01-05")
    assert gr.resolve_due(LATE, repo=FakeRepo([_row()]), load_bars=_bars(no_signal_bar)) == {
        "no-data": 1}


def test_the_batch_cap_bounds_one_night():
    repo = FakeRepo([_row(1), _row(2, ticker="MSFT"), _row(3, ticker="NVDA")])
    assert gr.resolve_due(LATE, limit=2, repo=repo, load_bars=_bars(_frame())) == {"filled": 2}
    assert [row_id for row_id, _ in repo.calls] == [1, 2]
    assert gr.resolve_due(LATE, limit=2, repo=repo, load_bars=_bars(_frame())) == {"filled": 1}


def test_one_failing_row_never_stops_the_batch():
    def load(ticker):
        if ticker == "BAD":
            raise OSError("unreadable cache file")
        return _frame()
    repo = FakeRepo([_row(1, ticker="BAD"), _row(2)])
    assert gr.resolve_due(LATE, repo=repo, load_bars=load) == {"error": 1, "filled": 1}
    assert repo.rows[1]["cf_status"] == "pending"


@pytest.mark.parametrize("scale, reanchored", [(0.5, True), (1.0, False)])
def test_an_intraday_write_is_reanchored_from_its_basis_bar(scale, reanchored):
    row = _row(signal_close=None, basis_date="2024-01-03", basis_close=100.0)
    repo = FakeRepo([row])
    assert gr.resolve_due(LATE, repo=repo, load_bars=_bars(_frame(scale=scale))) == {"filled": 1}
    resolved = repo.rows[1]
    assert resolved["reanchored"] is reanchored and resolved["win"] is True
    assert resolved["cf_plan"]["tp1"] == pytest.approx(102.0 * scale)


def test_against_the_real_repository():
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    repo = gate_rejections_repo()
    record = {k: v for k, v in _row().items() if k != "id"}
    record.update(created_at=dt.datetime(2024, 1, 4, 21, 0, tzinfo=dt.timezone.utc),
                  resolved_at=None, entry_context={}, heat_before=None, heat_cap=None)
    assert repo.insert_ignore(record)
    assert gr.resolve_due(LATE, load_bars=_bars(_frame())) == {"filled": 1}
    (stored,) = repo.list_since()
    assert stored["cf_status"] == "filled" and stored["win"] is True
    assert stored["resolved_at"] == RESOLVED_AT
    assert gr.resolve_due(LATE, load_bars=_bars(_frame())) == {}
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_gate_resolver.py`
Expected: FAIL, collection error `ImportError: cannot import name 'gate_resolver'`.

- [ ] **Step 3: Write the resolver**

Create `swingbot/core/backtesting/gate_resolver.py`:

```python
"""v147: the nightly resolver for live `gate_rejections` rows.

Selects pending rows whose walk window has closed, loads daily bars from the
live `market_data/` cache through `data_store.load_normalized` -- never a
`get_daily_data_batch` cold fetch (known-traps § two OHLCV caches) -- runs
`gate_counterfactual.simulate_blocked` and writes the outcome once.

Bars stop at the last NYSE session strictly before `today`, so a bar still
forming when the resolver runs is never read. A due row the simulator still
calls `pending` (the cache is short or missing) is re-checked once per session,
up to GRACE_SESSIONS times, then `no-data`. A resolved row is never resolved
again: the repository only updates rows whose `cf_status` is still `pending`.
Runs off the event loop (`loops.gate_counterfactual_resolve`, `asyncio.to_thread`).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from collections import Counter

import pandas as pd

from swingbot.core.backtesting import gate_counterfactual as gc
from swingbot.core.market.session import nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.plan_types import plan_from_dict

log = logging.getLogger(__name__)

RESOLVE_BATCH_CAP = 200
GRACE_SESSIONS = 5
PENDING_SCAN_CAP = 5000
_CANDIDATE_FIELDS = tuple(f.name for f in dataclasses.fields(gc.BlockedCandidate))
_UNREAD = gc.CounterfactualResult("pending", None, None, None, None, None, False, None)


def due_bars(horizon: str, expiry_bars: int | None) -> int:
    """Sessions after the signal bar before a row can resolve: pending window + horizon hold.
    With no plan the pending window is unknown, so 0 -- a lower bound, never late."""
    return int(expiry_bars or 0) + int(HORIZONS[horizon]["max_holding_days"])


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _load_daily(ticker: str):
    from swingbot.core.marketdata import data_store
    return data_store.load_normalized(ticker, "daily")


def _default_repo():
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    return gate_rejections_repo()


def _last_session_before(today: str) -> dt.date:
    calendar = nyse_calendar()
    day = dt.date.fromisoformat(today) - dt.timedelta(days=1)
    while day > calendar.first and not calendar.is_session(day):
        day -= dt.timedelta(days=1)
    return day


def _elapsed(row: dict, last_session: dt.date) -> int:
    signal = dt.date.fromisoformat(row["signal_date"])
    return nyse_calendar().sessions_between(signal, last_session) or 0


def _need(plan: dict | None, horizon: str) -> int:
    """Bars the walk reads after the signal: the plan's own window, else the lower bound."""
    if plan:
        return gc.bars_needed(plan_from_dict(plan))
    return due_bars(horizon, None)


def _due(rows: list, last_session: dt.date, limit: int) -> list[tuple[dict, int]]:
    """Up to `limit` (row, elapsed) pairs whose window has closed and not checked this session."""
    checked_on = last_session.isoformat()
    due = []
    for row in rows:
        elapsed = _elapsed(row, last_session)
        if elapsed >= _need(row.get("plan"), row["horizon"]) and row.get("pending_checked_on") != checked_on:
            due.append((row, elapsed))
        if len(due) >= limit:
            break
    return due


def _closes(bars) -> dict:
    index = pd.DatetimeIndex(bars.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    return dict(zip(index.strftime("%Y-%m-%d"), bars["Close"].astype(float)))


def _signal_close(row: dict, bars) -> float | None:
    """The stored close; for an intraday write, the close implied by its completed basis bar."""
    if row.get("signal_close") is not None:
        return float(row["signal_close"])
    basis_date, basis_close = row.get("basis_date"), row.get("basis_close")
    if bars is None or not basis_date or not basis_close:
        return None
    closes = _closes(bars)
    if basis_date not in closes or row["signal_date"] not in closes:
        return None
    return closes[row["signal_date"]] * float(basis_close) / closes[basis_date]


def _candidate(row: dict, bars) -> gc.BlockedCandidate:
    fields = {name: row.get(name) for name in _CANDIDATE_FIELDS}
    fields["signal_close"] = _signal_close(row, bars)
    return gc.BlockedCandidate(**fields)


def _simulate(row: dict, bars, last_session: dt.date) -> gc.CounterfactualResult:
    if bars is None or len(bars) == 0:
        return _UNREAD                    # a missing cache file waits like a short one
    return gc.simulate_blocked(_candidate(row, bars), bars, last_session=last_session.isoformat())


def _outcome(result: gc.CounterfactualResult) -> dict:
    return {"cf_r": result.cf_r, "win": result.win, "exit_index": result.exit_index,
            "last_bar_date": result.last_bar_date, "bars_sha256": result.bars_sha256,
            "reanchored": result.reanchored, "cf_plan": result.plan}


def _hold_or_expire(row: dict, result, elapsed: int, last_session: dt.date, repo) -> str | None:
    """A due row the simulator still calls pending: count one grace session, or give up."""
    if elapsed < _need(result.plan, row["horizon"]):
        return None                       # the rebuilt plan's own window is still open
    checks = int(row.get("pending_checks") or 0) + 1
    if checks > GRACE_SESSIONS:
        done = repo.resolve(row["id"], cf_status="no-data", resolved_at=_utc_now(),
                            outcome={**_outcome(result), "pending_checks": checks})
        return "no-data" if done else None
    repo.resolve(row["id"], cf_status="pending", resolved_at=None,
                 outcome={"pending_checks": checks, "pending_checked_on": last_session.isoformat()})
    return "pending"


def _resolve_row(row: dict, elapsed: int, last_session: dt.date, repo, load_bars) -> str | None:
    result = _simulate(row, load_bars(row["ticker"]), last_session)
    if result.cf_status == "pending":
        return _hold_or_expire(row, result, elapsed, last_session, repo)
    done = repo.resolve(row["id"], cf_status=result.cf_status, resolved_at=_utc_now(),
                        outcome=_outcome(result))
    return result.cf_status if done else None


def _safe_resolve(row: dict, elapsed: int, last_session: dt.date, repo, load_bars) -> str | None:
    try:
        return _resolve_row(row, elapsed, last_session, repo, load_bars)
    except Exception:   # noqa: BLE001 -- one bad row never costs the night's batch
        log.warning("gate resolver: row %s (%s %s) failed -- left pending", row.get("id"),
                    row.get("ticker"), row.get("signal_date"), exc_info=True)
        return "error"


def resolve_due(today: str, *, limit: int = RESOLVE_BATCH_CAP, repo=None,
                load_bars=None) -> dict[str, int]:
    """Resolve up to `limit` due pending rows as of `today` (ISO date, the ET session date).

    Returns counts per resulting cf_status ("pending" = a grace session counted,
    "error" = the row raised and stays pending). Rows not yet due are untouched."""
    repo = repo if repo is not None else _default_repo()
    load_bars = load_bars if load_bars is not None else _load_daily
    last_session = _last_session_before(today)
    counts: Counter = Counter()
    for row, elapsed in _due(repo.pending(limit=PENDING_SCAN_CAP), last_session, limit):
        status = _safe_resolve(row, elapsed, last_session, repo, load_bars)
        if status is not None:
            counts[status] += 1
    return dict(counts)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_gate_resolver.py`
Expected: PASS, `15 passed`, `0 failed` (`test_against_the_real_repository` skips with the db-test start command if the test database is down; start it, never mark the test skipped).

If `test_an_expired_row_...` reports `pending`, `_frame()`'s `HOLD + 5` bars after the signal no longer cover `bars_needed`: read `gc.bars_needed` for a market plan and widen `n_after`, never shorten the hold.

- [ ] **Step 5: Complexity and syntax**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/gate_resolver.py && python -m py_compile swingbot/core/backtesting/gate_resolver.py`
Expected: no radon output, no error.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/gate_resolver.py tests/backtesting/test_gate_resolver.py
git commit -m "feat(v147): gate-rejection resolver core -- due rows, grace, price basis (V147-11)"
```

