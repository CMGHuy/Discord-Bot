# v183 — Part 2: paper-book sizing, invariants, the gap-risk line and the risk view

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md](../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md)
**Index:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md](2026-10-21-v183-short-gap-sizing-and-squeeze-notice_0-index.md). Goal, architecture, `## Global Constraints`, `## Contracts`, `## Review Focus` and `## Parallelisation` live there and bind every task below.
**Tasks:** V183-6..V183-9. Every command runs from the worktree root `.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice` (created in V183-1).

Part 1 (V183-1..V183-5) has shipped when this part starts. These tasks use, exactly as the index's Contracts state them: `swingbot.core.planning.gap_sizing` (`RULE_GAP`, `RULE_STOP`, `size_for`, `size_for_plan`, `size_for_trade`, `gap_risk_amount_for`), `TradePlanV2.gap_sizing`, `compute_position_size(..., gap_floor_pct=None)` with its keys `gap_risk_amount` / `gap_sized` / `gap_floor_pct`, and `plan_table._sizing_snapshot(entry, plan)`, which now sizes through `size_for_plan`.

**Database:** the tests here use the per-checkout test database (`tests/store_seed.seed_store`). If this session has not yet run `/replicate-prod-db`, run it before the first test run (CLAUDE.md).

**Fixed numbers used throughout.** Account: balance 10,000, `risk_pct` 1.0, `max_position_pct` 100 (so no position cap interferes), both absolute caps 0, opex multiplier pinned to 1.0. A short with entry 100 and stop 102 has a stop distance of 2. Stop-sized, that is 100 / 2 = **50 shares**. With stamp `{"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}` the sizing distance is max(2, 100 × 4 / 100) = 4, which gives **25 shares**, `risk_amount` 25 × 2 = **50.0** and `gap_risk_amount` 25 × 4 = **100.0**, with `gap_sized` true.

---

# Phase 1 — The paper book trades the alert's size

### Task V183-6: Paper book sizes through size_for, logged fallback, alert/paper parity

**Model:** opus — it touches the legacy `log_trade` (CC 15) and four lanes' call sites, and a mistake here silently desyncs the alert from the paper book.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (module helpers above `class TradeLog`; `TradeLog.log_trade` :679-791, sizing block :766-783; `TradeLog.record_plan_fill` :804-835)
- Modify: `swingbot/core/scanning/scan_run.py:1085-1109` (the `trade_log.log_trade(` call)
- Modify: `swingbot/core/scanning/short_run.py:180-201` (`_log_trade`)
- Modify: `swingbot/core/scanning/strategy_pass.py:135-143` (`_open_trade`)
- Modify: `swingbot/core/planning/plan_manager.py:753-766` (the no-placeholder fallback `log_trade` in `_on_event`)
- Modify (only if the gate asks): `scripts/dev/complexity_baseline.json`
- Create: `tests/tracking/test_gap_sized_paper_book.py`

**Interfaces:**
- Consumes (V183-4): `gap_sizing.size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label="") -> dict | None`, `gap_sizing.size_for_trade(trade, entry=None, account_cfg=None)`, `TradePlanV2.gap_sizing`. Consumes (V183-5): `plan_table._sizing_snapshot(entry, plan)` sizing through `size_for_plan`.
- Produces: `TradeLog.log_trade(..., quote=None, gap_sizing: dict | None = None) -> str`; the trade record key `gap_sizing` (a copy of the stamp), written **only** when the stamp is not `None`; `_paper_sizing(entry, stop_loss, direction, gap_sizing, label) -> dict | None` in `performance.py`. `record_plan_fill(plan_id, fill_price)` keeps its signature and re-sizes through `_paper_sizing(fill_price, t["stop_loss"], t.get("direction"), t.get("gap_sizing"), t.get("ticker", ""))`, which is `size_for_trade(t, fill_price)` plus the logged fallback. V183-14 (part 3) adds `risk_notice=None` beside `gap_sizing` the same way, so keep the `_gap_sizing_field` helper pattern for it to copy.

- [ ] **Step 1: Write the failing tests**

Create `tests/tracking/test_gap_sized_paper_book.py`:

```python
"""V183-6: the paper book sizes a short through the alert's one sizing path.

Alert share count == paper-book share count for a gap-sized short, a switch-off
stamp sizes exactly as before v183, a long record is byte-identical, and a
failure in the gap path falls back to stop-only sizing with one log line --
never to an unsized trade."""
import ast
import logging
import pathlib
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gap_sizing_mod
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.scanning import execution_embeds, plan_table, scan_run, short_run, strategy_pass
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
STOP_STAMP = {"rule": "stop", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "MAX_RISK_AMOUNT_ABSOLUTE", 0.0)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 100.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _short(**kw):
    base = dict(plan_id="s1", ticker="TSLA", direction="bearish", trigger_price=100.0,
                entry_price=None, stop_loss=102.0, tp1=96.0, tp2=92.0, gap_sizing=STAMP)
    base.update(kw)
    return _plan(**base)


def _log(tlog, plan):
    tlog.log_trade(
        ticker=plan.ticker, strategy="Bear Flag", horizon_key="4w", direction=plan.direction,
        confidence_level=3, confidence_label="Medium", entry=plan.trigger_price,
        stop_loss=plan.stop_loss, take_profit=plan.tp1, plan_id=plan.plan_id,
        gap_sizing=plan.gap_sizing)
    return tlog.trade_for_plan(plan.plan_id)


def test_a_gap_stamped_short_logs_the_gap_cut_share_count(tlog):
    record = _log(tlog, _short())
    assert record["shares"] == 25.0
    assert record["position_value"] == 2500.0
    assert record["sizing_mode"] == "risk_pct"
    assert record["gap_sizing"] == STAMP


def test_alert_and_paper_book_agree_on_shares(tlog):
    plan = _short()
    record = _log(tlog, plan)
    assert plan_table._sizing_snapshot(plan.trigger_price, plan)["shares"] == record["shares"]
    assert execution_embeds._ticket_money(plan).record_shares == record["shares"]


def test_record_plan_fill_resizes_through_the_stamp(tlog):
    plan = _short()
    _log(tlog, plan)
    tlog.record_plan_fill("s1", 100.5)
    record = tlog.trade_for_plan("s1")
    assert record["shares"] == gap_sizing_mod.size_for_trade(record, 100.5)["shares"]
    assert record["shares"] == plan_table._sizing_snapshot(100.5, plan)["shares"]
    assert record["shares"] < account.compute_position_size(100.5, 102.0)["shares"]
    assert record["gap_sizing"] == STAMP


def test_a_switch_off_stamp_sizes_on_the_stop_exactly(tlog):
    record = _log(tlog, _short(gap_sizing=STOP_STAMP))
    assert record["shares"] == account.compute_position_size(100.0, 102.0)["shares"] == 50.0
    assert record["gap_sizing"] == STOP_STAMP


def test_a_short_without_a_usable_p99_sizes_on_the_stop(tlog):
    stamp = {"rule": "gap_p99", "up_gap_p99_pct": None, "n_up_gaps": 12}
    record = _log(tlog, _short(gap_sizing=stamp))
    assert record["shares"] == 50.0
    assert record["gap_sizing"] == stamp


def test_a_long_record_carries_no_gap_key_and_todays_shares(tlog):
    long_plan = _plan(plan_id="l1", ticker="AAPL", direction="bullish", trigger_price=100.0,
                      stop_loss=95.0)
    record = _log(tlog, long_plan)
    assert "gap_sizing" not in record
    assert record["shares"] == account.compute_position_size(100.0, 95.0)["shares"] == 20.0


def test_a_gap_path_failure_falls_back_to_stop_sizing_with_one_log_line(tlog, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(gap_sizing_mod, "size_for", boom)
    with caplog.at_level(logging.INFO, logger="swingbot.core.tracking.performance"):
        record = _log(tlog, _short())
        tlog.record_plan_fill("s1", 100.5)
    lines = [r.getMessage() for r in caplog.records if "gap sizing fell back to stop" in r.getMessage()]
    assert lines == ["TSLA: gap sizing fell back to stop (boom)"] * 2
    assert record["shares"] == 50.0
    assert tlog.trade_for_plan("s1")["shares"] == account.compute_position_size(100.5, 102.0)["shares"]


def test_a_stop_sizing_failure_still_leaves_a_long_unsized_as_before(tlog, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("no balance")
    monkeypatch.setattr(account, "compute_position_size", boom)
    with caplog.at_level(logging.INFO):
        record = _log(tlog, _plan(plan_id="l1", direction="bullish"))
    assert record["shares"] is None and record["sizing_mode"] is None
    assert not [r for r in caplog.records if "fell back" in r.getMessage()]


class _Capture:
    def __init__(self):
        self.kw = None

    def log_trade(self, **kw):
        self.kw = kw
        return "t1"


def test_short_lane_log_trade_passes_the_plan_stamp(monkeypatch):
    capture = _Capture()
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(short_run, "trade_log", capture)
    monkeypatch.setattr(scan_run, "_logged_plan_fields", lambda *a: ([], None))
    monkeypatch.setattr(scan_run, "_persist_plan_v2", lambda *a: None)
    monkeypatch.setattr(scan_run, "_trade_quote", lambda *a: None)
    monkeypatch.setattr(scan_run, "_confidence_point_kwargs", lambda conf: {})
    item = SimpleNamespace(
        result=SimpleNamespace(ticker="TSLA", strategy="Bear Flag", horizon_key="4w", trend="bearish"),
        plan=SimpleNamespace(stop_sources=["swing"], target2_sources=[]),
        conf=SimpleNamespace(level=3, label="Medium", score=60, breakdown={}),
        plan_v2=_short(), level_map={}, combined_from=[])
    nums = {"entry": 100.0, "stop_loss": 102.0, "take_profit": 96.0, "target2": 92.0}
    short_run._log_trade(item, nums, "why", None, [])
    assert capture.kw["gap_sizing"] == STAMP
    item.plan_v2 = None
    short_run._log_trade(item, nums, "why", None, [])
    assert capture.kw["gap_sizing"] is None


def test_strategy_lane_open_trade_passes_the_plan_stamp():
    capture = _Capture()
    strategy_pass._open_trade(SimpleNamespace(trade_log=capture), _short(), ticker="TSLA",
                              strategy="Bear Flag", horizon="4w", direction="bearish")
    assert capture.kw["gap_sizing"] == STAMP


def test_plan_manager_fallback_fill_sizes_like_the_alert(tlog):
    """Review Focus 2: a fill with no placeholder logs the trade itself."""
    plan = _short(entry_price=100.0, status=PlanStatus.ACTIVE)
    mgr = PlanManager(PlanStore(), lambda *a, **k: None, trade_log=tlog)
    mgr._on_event(plan, PlanEvent(plan.plan_id, "filled", {}))
    record = tlog.trade_for_plan(plan.plan_id)
    assert record["shares"] == 25.0
    assert record["gap_sizing"] == STAMP


@pytest.mark.parametrize("path", [
    "swingbot/core/scanning/scan_run.py", "swingbot/core/scanning/short_run.py",
    "swingbot/core/scanning/strategy_pass.py", "swingbot/core/planning/plan_manager.py",
])
def test_every_log_trade_call_site_passes_gap_sizing(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "log_trade"]
    assert calls, path
    for call in calls:
        assert "gap_sizing" in {kw.arg for kw in call.keywords}, (path, call.lineno)
```

`_ticket_money(plan).record_shares` is the unrounded share count of the ticket's `Money` (`instructions.money_from`), so it compares like for like with the record.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_gap_sized_paper_book.py`
Expected: FAIL. `log_trade()` raises `TypeError: ... unexpected keyword argument 'gap_sizing'`, and the AST test fails on all four files.

- [ ] **Step 3: Add the three module helpers in `swingbot/core/tracking/performance.py`**

Import the module, not the function, so tests can patch `gap_sizing_mod.size_for`: `from swingbot.core.planning import gap_sizing as gap_sizing_mod` beside the existing `account as account_module` import. If that creates an import cycle, import it inside `_paper_sizing` instead, still as a module.

```python
def _stop_only_sizing(entry, stop_loss) -> dict | None:
    """Today's sizing: the stop distance alone. None when it cannot be computed
    (balance 0, zero stop distance) -- the pre-v183 behaviour, kept."""
    try:
        return account_module.compute_position_size(entry, stop_loss)
    except Exception:
        return None


def _paper_sizing(entry, stop_loss, direction, gap_sizing, label) -> dict | None:
    """The paper book's share count, from the alert's one sizing path (v183).

    A failure in the gap path logs one line and sizes on the stop, never
    leaving the trade unsized; a long never logs and never leaves today's path."""
    try:
        return gap_sizing_mod.size_for(entry, stop_loss, direction=direction,
                                       gap_sizing=gap_sizing, label=label)
    except Exception as exc:
        if direction == "bearish" and gap_sizing:
            log.info("%s: gap sizing fell back to stop (%s)", label, exc)
        return _stop_only_sizing(entry, stop_loss)


def _gap_sizing_field(gap_sizing: dict | None) -> dict:
    """{"gap_sizing": stamp} for a stamped short, else {} -- the key stays absent
    on longs and pre-v183 plans so their records are byte-identical."""
    return {"gap_sizing": dict(gap_sizing)} if gap_sizing is not None else {}
```

- [ ] **Step 4: Thread the stamp through `log_trade` and `record_plan_fill`**

- `log_trade`: add `gap_sizing=None` as the last keyword (after `quote=None`), and add a docstring sentence: "`gap_sizing` is the plan's v183 sizing stamp; the share count comes from the same `size_for` the alert used."
- Replace the `try: sizing = account_module.compute_position_size(entry, stop_loss) except Exception: sizing = None` block with `sizing = _paper_sizing(entry, stop_loss, direction, gap_sizing, ticker)`.
- Directly after `record.update(_quote_field(quote))`, add `record.update(_gap_sizing_field(gap_sizing))`.
- `record_plan_fill`: replace its `try/except` the same way with `sizing = _paper_sizing(fill_price, t["stop_loss"], t.get("direction"), t.get("gap_sizing"), t.get("ticker", ""))`. The `if sizing is not None:` update stays as it is. Rewrite the docstring sentence "this is the same compute_position_size() call log_trade() made" to "this is the same `_paper_sizing` call `log_trade()` made (the stamp is read back from the record)".

Do not add any branch to `log_trade`: both new lines are plain calls, and removing the `try/except` lowers its score.

- [ ] **Step 5: Pass the stamp at all four call sites**

- `scan_run.py` `trade_log.log_trade(` call: add `gap_sizing=getattr(plan_v2, "gap_sizing", None),` after `entry_context=...`. `getattr` on `None` gives `None`, so no new branch is added to the legacy function.
- `short_run._log_trade`: add `gap_sizing=getattr(plan_v2, "gap_sizing", None),` after `entry_context=..., origin=origin,`.
- `strategy_pass._open_trade`: add `gap_sizing=plan.gap_sizing` after `entry_context=plan.entry_context`.
- `plan_manager._on_event` fallback `log_trade(`: add `gap_sizing=plan.gap_sizing` after `origin=plan.origin`.

The v144 outlook lane logs through `short_run._log_trade`, so it is covered.

- [ ] **Step 6: Run the new tests and the neighbouring suites**

Run: `python scripts/dev/testrun.py file tests/tracking/test_gap_sized_paper_book.py`
Expected: PASS (15 tests).

Run, one at a time: `python scripts/dev/testrun.py file tests/tracking/test_record_plan_fill.py`, `... file tests/edge/test_edge_sizing.py`, `... file tests/scanning/test_feed_close_routes.py`, `... file tests/scanning/test_short_lane_scan.py`, `... file tests/scanning/test_outlook_run.py`
Expected: every one PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. If its only finding is `swingbot.core.tracking.performance:TradeLog.log_trade` scoring below its baseline 15 (an improvement), run `python scripts/dev/complexity_gate.py --update` and re-run the check to exit 0. Any finding that a function *rose* means a new branch slipped in, so move it into a helper.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/tracking/performance.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py swingbot/core/scanning/strategy_pass.py swingbot/core/planning/plan_manager.py tests/tracking/test_gap_sized_paper_book.py scripts/dev/complexity_baseline.json
git commit -m "feat(v183): paper book sizes shorts through the alert's gap-aware path (V183-6)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V183-7: Invariants: caps per lane, gap-fill real R, longs byte-identical

**Model:** sonnet — tests only, but they encode the spec's risk invariants, and their fixtures must reach the real sizer and paper book.

**Files:**
- Create: `tests/scanning/test_gap_sizing_cap_invariants.py`
- Create: `tests/tracking/test_gap_fill_real_r.py`
- Create: `tests/planning/test_long_sizing_regression.py`

**Interfaces:**
- Consumes: `compute_position_size(..., gap_floor_pct=None)` (V183-3); `gap_sizing.size_for`, `size_for_plan` (V183-4); `TradeLog.log_trade(..., gap_sizing=None)` (V183-6); existing `heat.open_heat`, `heat.heat_check`, `correlation.cluster_exposure`, `correlation.cluster_check`, `stop_scope.risk_sizing_ok(plan, sizing_fn=None)`, `short_run._stamp_risk_flags(item, frames, account_cfg)`, `metrics.r_multiple(trade)`, `performance.settle_legs(t)`, `TradeLog.update_open_trades(ticker, df, live_price=None)`.
- Produces: nothing. These tests only pin behaviour that V183-3..V183-6 built. **A failure here is a defect in the owning task's file: fix it there, in this task's commit, and never by loosening an assertion.**

What "caps hold on the cut size" means per lane (spec § Requirements added by the panel review, as corrected in the post-panel note). The candidate's heat and cluster checks read the configured `risk_pct`, never the final share count. That holds in the confluence lane (`scan_run.py`) and in the v118/v119/v144 lanes (`short_run._stamp_risk_flags`, which the outlook lane reuses). So a gap cut cannot raise them. What it does change is the *open* book: open heat and correlated heat sum `trade_risk_pct` over the stored shares, so they may only fall. The stop cap is a stop-distance check and does not move. `risk_sizing_ok`, the seventh sizing site, stays true. The strategy lane (`strategy_pass._open_trade`, v93/v104) has no heat or cluster check today. That is an older gap, recorded in the spec and not fixed here, so it gets no lane test.

- [ ] **Step 1: Write the cap-invariant tests**

Create `tests/scanning/test_gap_sizing_cap_invariants.py`:

```python
"""V183-7: the gap floor only ever shrinks what the caps measure.

Per lane: the candidate's heat/cluster inputs are the configured risk_pct (never
shares), open heat and correlated heat over gap-sized trades never exceed the
stop-sized ones, and the v139 risk-sizing check still passes."""
import ast
import pathlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.edge import correlation, heat
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size
from swingbot.core.planning.gap_sizing import size_for
from swingbot.core.planning.stop_scope import risk_sizing_ok
from swingbot.core.scanning import short_run
from tests.planning.test_plan_engine_model import _plan

REPO = pathlib.Path(__file__).resolve().parents[2]
BALANCE = 10_000.0
STATS = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
SHORTS = [(100.0, 102.0), (50.0, 50.5), (250.0, 256.0), (10.0, 10.4), (174.5, 178.0)]
P99S = [0.5, 2.0, 4.0, 9.0]
MODES = ["risk_pct", "kelly", "vol_target", "min_of_all", "account_pct"]


@pytest.fixture(autouse=True)
def _no_opex(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)


def _cfg(mode, *, abs_caps=False):
    return {"balance": BALANCE, "risk_pct": 1.0, "position_pct": 10.0, "max_position_pct": 20.0,
            "sizing_mode": mode,
            "max_position_value_absolute": 1500.0 if abs_caps else 0.0,
            "max_risk_amount_absolute": 60.0 if abs_caps else 0.0}


def _stamp(p99):
    return {"rule": "gap_p99", "up_gap_p99_pct": p99, "n_up_gaps": 120}


@pytest.mark.parametrize("abs_caps", [False, True])
@pytest.mark.parametrize("mode", MODES)
def test_the_gap_floor_never_raises_any_sized_quantity(mode, abs_caps):
    cfg = _cfg(mode, abs_caps=abs_caps)
    for entry, stop in SHORTS:
        plain = compute_position_size(entry, stop, cfg, strategy_stats=STATS, ticker_atr_pct=3.0)
        for p99 in P99S:
            gap = compute_position_size(entry, stop, cfg, strategy_stats=STATS,
                                        ticker_atr_pct=3.0, gap_floor_pct=p99)
            case = (mode, abs_caps, entry, stop, p99)
            assert gap["shares"] <= plain["shares"], case
            assert gap["risk_amount"] <= plain["risk_amount"] + 0.01, case
            assert gap["position_value"] <= plain["position_value"] + 0.01, case
            assert gap["mode"] == plain["mode"], case
            assert gap["gap_risk_amount"] >= gap["risk_amount"] - 0.01, case


@pytest.mark.parametrize("mode", ["risk_pct", "kelly", "vol_target", "min_of_all"])
def test_a_p99_gap_stays_inside_the_dollar_risk_in_every_risk_mode(mode):
    cfg = _cfg(mode)
    for entry, stop in SHORTS:
        for p99 in P99S:
            gap = compute_position_size(entry, stop, cfg, strategy_stats=STATS,
                                        ticker_atr_pct=3.0, gap_floor_pct=p99)
            assert gap["gap_risk_amount"] <= BALANCE * cfg["risk_pct"] / 100 + 0.01, (mode, entry, p99)


def test_account_pct_is_cut_only_through_the_absolute_risk_cap():
    for entry, stop in SHORTS:
        for p99 in P99S:
            free = compute_position_size(entry, stop, _cfg("account_pct"), gap_floor_pct=p99)
            assert free["shares"] == compute_position_size(entry, stop, _cfg("account_pct"))["shares"]
            capped = compute_position_size(entry, stop, _cfg("account_pct", abs_caps=True),
                                           gap_floor_pct=p99)
            assert capped["gap_risk_amount"] <= 60.0 + 0.01, (entry, p99)


def _book(p99):
    cfg = _cfg("risk_pct")
    rows = []
    for i, (entry, stop) in enumerate(SHORTS):
        stamp = _stamp(p99) if p99 is not None else None
        sizing = size_for(entry, stop, direction="bearish", gap_sizing=stamp, account_cfg=cfg)
        rows.append({"ticker": f"T{i}", "direction": "bearish", "entry": entry,
                     "stop_loss": stop, "shares": sizing["shares"]})
    return rows


@pytest.mark.parametrize("p99", P99S)
def test_open_heat_over_gap_sized_shorts_never_exceeds_stop_sized(p99):
    gap_book, stop_book = _book(p99), _book(None)
    assert heat.open_heat(gap_book, BALANCE) <= heat.open_heat(stop_book, BALANCE) + 1e-9
    gap_chk = heat.heat_check(gap_book, BALANCE, candidate_risk_pct=1.0)
    stop_chk = heat.heat_check(stop_book, BALANCE, candidate_risk_pct=1.0)
    assert gap_chk["remaining"] >= stop_chk["remaining"]
    assert gap_chk["allowed"] or not stop_chk["allowed"]


@pytest.mark.parametrize("p99", P99S)
def test_correlated_heat_over_gap_sized_shorts_never_exceeds_stop_sized(p99):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame({"Close": 100 * np.cumprod(1 + rng.normal(0, 0.01, 150))},
                         index=pd.bdate_range("2026-01-01", periods=150))
    dfs = {f"T{i}": frame for i in range(len(SHORTS))} | {"CAND": frame}
    gap = correlation.cluster_exposure(_book(p99), "CAND", dfs, BALANCE)
    stop = correlation.cluster_exposure(_book(None), "CAND", dfs, BALANCE)
    assert len(stop["cluster"]) == len(SHORTS)          # every name correlates: the check is live
    assert gap["correlated_heat"] <= stop["correlated_heat"] + 1e-9
    assert (correlation.cluster_check(gap, 1.0)["allowed"]
            or not correlation.cluster_check(stop, 1.0)["allowed"])


def test_short_lane_flags_ignore_the_gap_stamp(monkeypatch):
    """v118/v119/v144: _stamp_risk_flags reads config risk_pct, so a stamped and
    an unstamped candidate get the same heat and cluster verdicts."""
    open_book = [{"ticker": "AAA", "direction": "bearish", "entry": 100.0, "stop_loss": 102.0,
                  "shares": 290.0}]                     # 5.8% open heat: the next 1% breaches 6%
    monkeypatch.setattr(short_run, "trade_log", SimpleNamespace(get_trades=lambda **k: open_book))
    monkeypatch.setattr(short_run.throttle, "kill_state", lambda: {"on": False})
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)
    monkeypatch.setattr(config, "CORRELATED_HEAT_CAP_PCT", 3.0)
    cfg = _cfg("risk_pct")
    verdicts = []
    for stamp in (_stamp(4.0), None):
        item = SimpleNamespace(result=SimpleNamespace(ticker="TSLA"),
                               plan_v2=_plan(direction="bearish", stop_loss=102.0, gap_sizing=stamp),
                               heat_blocked=None, cluster_blocked=None, kill_switch_blocked=None)
        short_run._stamp_risk_flags(item, {}, cfg)
        verdicts.append((item.heat_blocked, item.cluster_blocked))
    assert verdicts[0] == verdicts[1]
    assert verdicts[0][0] is not None                   # the heat check did fire


@pytest.mark.parametrize("path", ["swingbot/core/scanning/scan_run.py",
                                  "swingbot/core/scanning/short_run.py"])
def test_candidate_heat_and_cluster_inputs_are_the_configured_risk_pct(path):
    """The confluence lane's checks are inline in run_scan; pin their inputs."""
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    seen = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr == "heat_check":
            arg = next(kw.value for kw in node.keywords if kw.arg == "candidate_risk_pct")
        elif node.func.attr == "cluster_check":
            arg = node.args[1]
        else:
            continue
        seen += 1
        assert ast.unparse(arg) == "account_cfg.get('risk_pct', 1.0)", (path, node.lineno)
    assert seen == 2, path


def test_the_seventh_sizing_site_still_passes_on_a_gap_cut_size():
    cfg = _cfg("risk_pct")
    for entry, stop in SHORTS:
        plan = _plan(direction="bearish", trigger_price=entry, stop_loss=stop, stop_ceiling_pct=3.0)
        stop_only = risk_sizing_ok(plan, sizing_fn=lambda e, s: compute_position_size(e, s, cfg))
        for p99 in P99S:
            gap_fn = (lambda e, s, p=p99: size_for(e, s, direction="bearish",
                                                  gap_sizing=_stamp(p), account_cfg=cfg))
            assert risk_sizing_ok(plan, sizing_fn=gap_fn) or not stop_only, (entry, p99)
```

- [ ] **Step 2: Write the gap-fill real-R tests**

Create `tests/tracking/test_gap_fill_real_r.py`:

```python
"""V183-7: a paper short gapped through its stop books the R of its real fill
(-2.4R here), never a clamped -1R; the gap cut halves the dollars, not the R."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.analytics.metrics import r_multiple
from swingbot.core.planning import account
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.tracking.performance import TradeLog, settle_legs
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
STOP_STAMP = {"rule": "stop", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "MAX_RISK_AMOUNT_ABSOLUTE", 0.0)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 100.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _gap_bar():
    """Tomorrow's bar (after the trade's opened_at), opening 104.80 over a 102 stop."""
    day = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return pd.DataFrame({"Open": [104.8], "High": [105.5], "Low": [104.0], "Close": [105.0]},
                        index=pd.DatetimeIndex([day]))


def _log_short(tlog, ticker, stamp, plan_id=None):
    trade_id = tlog.log_trade(
        ticker=ticker, strategy="Bear Flag", horizon_key="4w", direction="bearish",
        confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=102.0,
        take_profit=96.0, plan_id=plan_id, gap_sizing=stamp)
    return trade_id


def _closed(tlog, trade_id):
    return next(t for t in tlog.get_trades(status=None, limit=None) if t["id"] == trade_id)


def test_a_short_gapped_through_its_stop_books_its_real_r(tlog):
    trade_id = _log_short(tlog, "TSLA", STAMP)
    tlog.update_open_trades("TSLA", _gap_bar(), live_price=None)
    record = _closed(tlog, trade_id)
    assert record["status"] == "loss"
    assert record["exit_price"] == pytest.approx(104.8)
    assert r_multiple(record) == pytest.approx(-2.4)
    assert record["shares"] == 25.0
    assert record["realized_pnl_amount"] == pytest.approx(-120.0, abs=0.01)


def test_the_gap_cut_halves_the_dollar_loss_not_the_r(tlog):
    cut = _log_short(tlog, "TSLA", STAMP)
    plain = _log_short(tlog, "NIO", STOP_STAMP)
    tlog.update_open_trades("TSLA", _gap_bar(), live_price=None)
    tlog.update_open_trades("NIO", _gap_bar(), live_price=None)
    cut_rec, plain_rec = _closed(tlog, cut), _closed(tlog, plain)
    assert r_multiple(cut_rec) == pytest.approx(r_multiple(plain_rec)) == pytest.approx(-2.4)
    assert plain_rec["realized_pnl_amount"] == pytest.approx(-240.0, abs=0.01)
    assert cut_rec["realized_pnl_amount"] == pytest.approx(-120.0, abs=0.01)


def test_a_plan_linked_short_closed_past_its_stop_books_its_real_r(tlog):
    plan = _plan(plan_id="s1", ticker="TSLA", direction="bearish", trigger_price=100.0,
                 entry_price=100.0, stop_loss=102.0, tp1=96.0, tp2=92.0,
                 status=PlanStatus.ACTIVE, gap_sizing=STAMP)
    _log_short(tlog, "TSLA", STAMP, plan_id="s1")
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, lambda *a, **k: None, trade_log=tlog)
    mgr._on_event(store.get("s1"), PlanEvent("s1", "closed", {
        "reason": "loss", "exit_price": 104.8, "session": "regular", "_terminal_persisted": False}))
    record = tlog.trade_for_plan("s1")
    assert record["status"] == "loss"
    assert r_multiple(record) == pytest.approx(-2.4)
    assert record["realized_pnl_amount"] == settle_legs(record)
    assert record["realized_pnl_amount"] == pytest.approx(-120.0, abs=0.01)
```

- [ ] **Step 3: Write the long regression tests**

Create `tests/planning/test_long_sizing_regression.py`. The golden dicts below were captured from `compute_position_size` on `main` at `7ac5e4ea`, before v183, with opex pinned to 1.0 and the config shown:

```python
"""V183-7: long sizing is byte-identical to pre-v183 main (golden values captured
at 7ac5e4ea), whatever a long is handed: no stamp, a gap stamp, a stop stamp."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size
from swingbot.core.planning.gap_sizing import size_for, size_for_plan
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

BASE = {"balance": 10000.0, "risk_pct": 1.0, "position_pct": 10.0, "max_position_pct": 20.0,
        "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0}
RISK_ROWS = [((100.0, 95.0), 20.0, 100.0, 2000.0, False), ((50.0, 49.0), 40.0, 40.0, 2000.0, True),
             ((250.0, 240.0), 8.0, 80.0, 2000.0, True), ((10.0, 9.5), 200.0, 100.0, 2000.0, False),
             ((174.5, 170.96), 11.46, 40.57, 2000.0, True)]
ACCOUNT_ROWS = [((100.0, 95.0), 10.0, 50.0, 1000.0, False), ((50.0, 49.0), 20.0, 20.0, 1000.0, False),
                ((250.0, 240.0), 4.0, 40.0, 1000.0, False), ((10.0, 9.5), 100.0, 50.0, 1000.0, False),
                ((174.5, 170.96), 5.73, 20.29, 1000.0, False)]
GOLDEN = ([("risk_pct", *row, "risk_pct") for row in RISK_ROWS]
          + [("min_of_all", *row, "risk_pct") for row in RISK_ROWS]
          + [("account_pct", *row, "account_pct") for row in ACCOUNT_ROWS])
STAMPS = [None, {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120},
          {"rule": "stop", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}]


@pytest.fixture(autouse=True)
def _no_opex(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)


def _expected(shares, risk_amount, position_value, capped, mode):
    return dict(BASE, shares=shares, risk_amount=risk_amount, position_value=position_value,
                capped=capped, mode=mode)


@pytest.mark.parametrize("mode,levels,shares,risk,value,capped,out_mode", GOLDEN)
def test_long_sizing_matches_pre_v183_main(mode, levels, shares, risk, value, capped, out_mode):
    cfg = dict(BASE, sizing_mode=mode)
    entry, stop = levels
    expected = _expected(shares, risk, value, capped, out_mode)
    assert compute_position_size(entry, stop, cfg) == expected
    assert compute_position_size(entry, stop, cfg, gap_floor_pct=None) == expected
    for stamp in STAMPS:
        assert size_for(entry, stop, direction="bullish", gap_sizing=stamp, account_cfg=cfg) == expected
    plan = _plan(direction="bullish", trigger_price=entry, stop_loss=stop)
    assert size_for_plan(plan, account_cfg=cfg) == expected


def test_a_long_trade_record_is_unchanged_by_the_new_keyword(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", dict(BASE, sizing_mode="risk_pct", balance_history=[]))
    tlog = TradeLog()
    common = dict(ticker="AAPL", strategy="VWAP", horizon_key="4w", direction="bullish",
                  confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=95.0,
                  take_profit=110.0)
    tlog.log_trade(**common, plan_id="a")
    tlog.log_trade(**common, plan_id="b", gap_sizing=None)
    without, with_none = tlog.trade_for_plan("a"), tlog.trade_for_plan("b")
    volatile = {"id", "plan_id", "opened_at"}
    assert {k: v for k, v in without.items() if k not in volatile} == \
           {k: v for k, v in with_none.items() if k not in volatile}
    assert "gap_sizing" not in without and "risk_notice" not in without
    assert without["shares"] == 20.0
```

- [ ] **Step 4: Run all three files**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_cap_invariants.py`
Expected: PASS (27 tests).

Run: `python scripts/dev/testrun.py file tests/tracking/test_gap_fill_real_r.py`
Expected: PASS (3 tests).

Run: `python scripts/dev/testrun.py file tests/planning/test_long_sizing_regression.py`
Expected: PASS (16 tests).

If any assertion fails, find the defect in the V183-3/-4/-6 code it exercises and fix it there. Re-run that one test (`python -m pytest <file>::<test> -v`), then the owning task's own test file.

- [ ] **Step 5: Commit**

```bash
git add tests/scanning/test_gap_sizing_cap_invariants.py tests/tracking/test_gap_fill_real_r.py tests/planning/test_long_sizing_regression.py
git commit -m "test(v183): cap, real-R and long byte-identity invariants for gap sizing (V183-7)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(If a fix was needed, also stage the fixed source file and name it in the commit body.)

# Phase 2 — Showing the gap risk

### Task V183-8: Order-block gap-risk line on every alert channel

**Model:** sonnet — one pure wording function plus three thin call sites, with exact copy fixed by the spec.

**Files:**
- Create: `swingbot/core/presentation/gap_risk.py`
- Modify: `swingbot/core/scanning/execution_embeds.py` (new `ticket_gap_line`, `_with_gap_line`; `build_ticket_embed` :89-100)
- Modify: `swingbot/core/scanning/alert_embeds.py` (import; new `GAP_RISK_FIELD`, `_gap_risk_fields`; one `extend` line in `build_embed` beside :194)
- Modify: `swingbot/core/infra/notifier.py` (new `_gap_risk_lines`; one splice in `_build_alert_texts`)
- Create: `tests/presentation/test_gap_risk_line.py`

**Interfaces:**
- Consumes (V183-5): `plan_table._sizing_snapshot(entry, plan)`, which for a stamped short returns the `compute_position_size` dict plus `gap_risk_amount`, `gap_sized`, `gap_floor_pct`, and for a long, a rule-`stop` short or a pre-v183 plan returns a dict **without** those keys.
- Produces: `gap_risk.GAP_CUT_TEXT = "size cut for gap risk"`, `gap_risk.GAP_NA_TEXT = "gap risk n/a"`, `gap_risk.gap_risk_line(sizing: dict | None, *, currency: str = "$") -> str | None`; `execution_embeds.ticket_gap_line(plan) -> str | None` (the one place a channel turns a plan into the line); `alert_embeds.GAP_RISK_FIELD = "Position risk"`. V183-14 (part 3) builds the plan-page `gap_sizing.line` with `gap_risk_line` too.

The wording (spec § Part A, "Shown where the order is"; index Contracts):

| Sizing dict | Line |
|---|---|
| `None`, or no `gap_sized` key (long, rule `stop`, pre-v183) | `None`, so nothing is printed |
| `gap_sized` true | `Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk` |
| `gap_sized` false, p99 present | `Risk $200 at stop · $200 on a p99 gap (1.1%)` |
| `gap_floor_pct` or `gap_risk_amount` `None` | `Risk $200 at stop · gap risk n/a` |

Money is whole currency units with thousands separators (`f"{currency}{amount:,.0f}"`; `None` prints `n/a`); the percent has one decimal.

- [ ] **Step 1: Write the failing tests**

Create `tests/presentation/test_gap_risk_line.py`:

```python
"""V183-8: the order block's gap-risk line -- one wording function, and the same
text on the full Discord alert, the simple mirror, the v81 ticket and the
email/push body. Longs, switch-off shorts and pre-v183 plans print nothing new."""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.infra import notifier
from swingbot.core.presentation import short_notice
from swingbot.core.presentation.gap_risk import GAP_CUT_TEXT, GAP_NA_TEXT, gap_risk_line
from swingbot.core.scanning import execution_embeds
from swingbot.core.scanning.alert_embeds import GAP_RISK_FIELD, build_embed, build_simple_alert
from tests.scanning.test_embeds_v3 import (PERF_STATS_EMPTY, make_item, make_plan_v2,
                                           _isolated_scan_snapshots)  # noqa: F401

CUT = {"shares": 25.0, "risk_amount": 50.0, "gap_risk_amount": 100.0,
       "gap_sized": True, "gap_floor_pct": 4.0}
NOT_CUT = {"shares": 50.0, "risk_amount": 200.0, "gap_risk_amount": 200.0,
           "gap_sized": False, "gap_floor_pct": 1.1}
NO_P99 = {"shares": 50.0, "risk_amount": 200.0, "gap_risk_amount": None,
          "gap_sized": False, "gap_floor_pct": None}
PLAIN = {"shares": 20.0, "risk_amount": 100.0, "position_value": 2000.0, "mode": "risk_pct"}
CUT_LINE = "Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk"


def test_the_copy_constants():
    assert GAP_CUT_TEXT == "size cut for gap risk"
    assert GAP_NA_TEXT == "gap risk n/a"


@pytest.mark.parametrize("sizing,expected", [
    (CUT, CUT_LINE),
    (NOT_CUT, "Risk $200 at stop · $200 on a p99 gap (1.1%)"),
    (NO_P99, "Risk $200 at stop · gap risk n/a"),
    (dict(NO_P99, gap_floor_pct=3.0), "Risk $200 at stop · gap risk n/a"),
    (dict(NO_P99, risk_amount=None), "Risk n/a at stop · gap risk n/a"),
    (PLAIN, None),
    (None, None),
    ({}, None),
])
def test_gap_risk_line_wording(sizing, expected):
    assert gap_risk_line(sizing) == expected


def test_currency_and_thousands():
    sizing = {"risk_amount": 1234.4, "gap_risk_amount": 2468.8, "gap_sized": True, "gap_floor_pct": 2.76}
    assert gap_risk_line(sizing, currency="€") == (
        "Risk €1,234 at stop · €2,469 on a p99 gap (2.8%) · size cut for gap risk")


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(short_notice, "completed_session_date", lambda: "2026-10-01")


def _embed_text(embed):
    return "\n".join([embed.description or "", *(f.name + "\n" + f.value for f in embed.fields)])


def _item(monkeypatch, sizing, direction="bearish"):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: sizing)
    stop = 102.0 if direction == "bearish" else 95.0
    item = make_item(plan_v2=dataclasses.replace(make_plan_v2(direction=direction), stop_loss=stop))
    item.result.trend = direction
    item.paper_logged = True
    return item


def _renderings(item):
    return {
        "discord": _embed_text(build_embed(item, "x", PERF_STATS_EMPTY, None, None)),
        "simple": _embed_text(build_simple_alert(item)),
        "ticket": _embed_text(execution_embeds.build_ticket_embed(item, item.plan_v2)),
        "email/push": notifier._build_alert_texts(item, item.plan, item.conf)[1],
    }


def test_every_alert_channel_shows_the_line_for_a_cut_short(monkeypatch):
    for name, text in _renderings(_item(monkeypatch, CUT)).items():
        assert CUT_LINE in text, name


def test_a_short_without_p99_says_gap_risk_n_a_on_every_channel(monkeypatch):
    for name, text in _renderings(_item(monkeypatch, NO_P99)).items():
        assert "Risk $200 at stop · gap risk n/a" in text, name


def test_the_line_sits_in_the_order_block(monkeypatch):
    item = _item(monkeypatch, CUT)
    ticket = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert CUT_LINE in ticket.description               # with the stop/TP lines, not a stray field
    full = build_embed(item, "x", PERF_STATS_EMPTY, None, None)
    assert [f.value for f in full.fields if f.name == GAP_RISK_FIELD] == [CUT_LINE]
    body = notifier._build_alert_texts(item, item.plan, item.conf)[1].splitlines()
    rr = next(i for i, line in enumerate(body) if line.startswith("R:R"))
    assert body[rr + 1] == CUT_LINE


@pytest.mark.parametrize("sizing", [PLAIN, None])
def test_a_long_or_unstamped_plan_prints_nothing_new(monkeypatch, sizing):
    for direction in ("bullish", "bearish"):
        item = _item(monkeypatch, sizing, direction)
        for name, text in _renderings(item).items():
            assert "p99" not in text and GAP_NA_TEXT not in text, (direction, name)
        full = build_embed(item, "x", PERF_STATS_EMPTY, None, None)
        assert GAP_RISK_FIELD not in [f.name for f in full.fields]


def test_a_long_ticket_and_email_are_byte_identical_without_the_hook(monkeypatch):
    item = _item(monkeypatch, PLAIN, "bullish")
    before = (execution_embeds.build_ticket_embed(item, item.plan_v2).description,
              notifier._build_alert_texts(item, item.plan, item.conf))
    monkeypatch.setattr(execution_embeds, "ticket_gap_line", lambda plan: None)
    after = (execution_embeds.build_ticket_embed(item, item.plan_v2).description,
             notifier._build_alert_texts(item, item.plan, item.conf))
    assert before == after
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_gap_risk_line.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'swingbot.core.presentation.gap_risk'`.

- [ ] **Step 3: Create `swingbot/core/presentation/gap_risk.py`**

A module docstring stating that this is the one wording of the v183 gap-risk line, and that every alert channel and the plan page take it from here (index § Channel parity). It holds `GAP_CUT_TEXT`, `GAP_NA_TEXT`, a `_money(amount, currency) -> str` helper (`"n/a"` for `None`, else `f"{currency}{amount:,.0f}"`) and `gap_risk_line(sizing, *, currency="$") -> str | None` per the wording table above. Return `None` when `not sizing or "gap_sized" not in sizing`. Keep every function under complexity 15. The module imports nothing from `scanning`.

- [ ] **Step 4: Wire the three channels**

- `execution_embeds.py`: `import dataclasses` and `from swingbot.core.presentation.gap_risk import gap_risk_line`. Add:

  ```python
  def ticket_gap_line(plan) -> str | None:
      """The order block's v183 gap-risk line for a v2 plan, from the same sizing
      snapshot the ticket's share count uses; None for longs, rule-stop and
      pre-v183 plans, so their alerts are unchanged."""
      if plan is None:
          return None
      return gap_risk_line(_sizing_snapshot(_entry(plan), plan), currency=config.CURRENCY_SYMBOL)


  def _with_gap_line(instruction: Instruction, plan) -> Instruction:
      line = ticket_gap_line(plan)
      return dataclasses.replace(instruction, lines=(*instruction.lines, line)) if line else instruction
  ```

  In `build_ticket_embed`, wrap the `ticket_for(...)` result: `instruction = _with_gap_line(ticket_for(...), plan)`. The line is the last order line, under stop/TP1/runner/breakeven. Because `build_simple_alert` renders this ticket while the v2 engine is on, this one change also covers the simple mirror.
- `alert_embeds.py`: import `ticket_gap_line` from `.execution_embeds` (beside `build_ticket_embed`), add `GAP_RISK_FIELD = "Position risk"` and

  ```python
  def _gap_risk_fields(item) -> list:
      line = ticket_gap_line(_v2_plan(item))
      return [(GAP_RISK_FIELD, line, False)] if line else []
  ```

  and in `build_embed`, directly after `sections["plan"].extend(_quote_fields(item))`, add `sections["plan"].extend(_gap_risk_fields(item))`. That is a call with no branch, so `build_embed` stays at its baseline of 33.
- `notifier.py`: add

  ```python
  def _gap_risk_lines(item) -> list:
      """[the v183 gap-risk line] for the email/push body, [] when there is none."""
      from swingbot.core.scanning.execution_embeds import ticket_gap_line
      line = ticket_gap_line(getattr(item, "plan_v2", None))
      return [line] if line else []
  ```

  and in `_build_alert_texts`, after `body_lines` is built and before the notice splice, insert `body_lines[8:8] = _gap_risk_lines(item)`. Index 8 is the blank line after `R:R      : …`, so the line lands directly under `R:R`. Add a one-line comment naming that.

- [ ] **Step 5: Run the new tests and the alert suites they touch**

Run: `python scripts/dev/testrun.py file tests/presentation/test_gap_risk_line.py`
Expected: PASS (16 tests).

Run, one at a time: `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`, `... file tests/scanning/test_embeds_v3.py`, `... file tests/scanning/test_embeds_badges.py`, `... file tests/scanning/test_compression_instructions.py`, `... file tests/commands/test_plans_board.py`
Expected: every one PASS (the existing fixtures patch `_sizing_snapshot` to `None` or to dicts without gap keys, so no new line appears in them).

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0, with `alert_embeds.build_embed` still at 33 and nothing new at or above 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/presentation/gap_risk.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/alert_embeds.py swingbot/core/infra/notifier.py tests/presentation/test_gap_risk_line.py
git commit -m "feat(v183): stop and p99-gap risk line in every alert's order block (V183-8)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V183-9: Risk view: summed gap risk of open shorts

**Model:** sonnet — one display-only API figure and one line on an existing panel, across Python and Angular, checked at three widths.

**Files:**
- Modify: `swingbot/admin/api_v1/risk.py` (new `_open_short_gap_risk`, `_heat_gap_block`; the `"heat"` dict in `get_risk` :356-360)
- Modify: `tests/admin/test_api_v1_risk.py` (`test_risk_shape` heat block :133-136; new tests)
- Modify: `frontend/src/app/api/models.ts` (`RiskHeat` :1323-1327). This file is not in the ledger row. It is the hand-written `/api/v1` contract, and the new keys must be declared there. Part 3's V183-14/15 may edit `TradeDetail` in the same file later, so the two tasks run in order and never in parallel.
- Modify: `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/stores/risk.store.spec.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (Portfolio heat panel :211-246; styles :491-515; component class), `frontend/src/app/workspaces/risk/risk.spec.ts`

**Interfaces:**
- Consumes (V183-4): `gap_sizing.gap_risk_amount_for(shares, entry, stop_loss, gap_sizing) -> float | None` (None without a usable p99 or for rule `stop`). Consumes (V183-6): open trade records carrying `gap_sizing`.
- Produces: `GET /api/v1/risk` → `body["heat"]` gains `"gap_risk_amount": number | null` (sum over open `"bearish"` trades with a figure, rounded to 2 dp; `null` when no open short has one) and `"gap_risk_unknown": int` (open `"bearish"` trades without one: no stamp, rule `stop`, no p99, or no shares). `_open_short_gap_risk(open_trades: list) -> dict` returns exactly those two keys. `RiskStore.gapRiskAmount(): number | null`, `RiskStore.gapRiskUnknown(): number`.

Heat itself is untouched. `open_pct`, `positions` and their sum stay on stop risk (spec, my call: "heat stays comparable with history; `gap_risk_amount` is displayed, not summed into heat").

- [ ] **Step 1: Write the failing API tests**

In `tests/admin/test_api_v1_risk.py`, extend the heat block of `test_risk_shape`:

```python
    assert_shape(body["heat"], {
        "open_pct": NULLABLE_NUMBER, "cap_pct": NULLABLE_NUMBER,
        "utilisation_pct": NULLABLE_NUMBER,
        "gap_risk_amount": NULLABLE_NUMBER, "gap_risk_unknown": int,
    }, where="heat")
```

and add, after `test_positions_are_ordered_by_risk`:

```python
GAP_STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}


def _short_trade(trade_id, ticker, *, shares=25, gap_sizing=None):
    trade = dict(_open_trade(trade_id, ticker, entry=100.0, stop=102.0, shares=shares),
                 direction="bearish", take_profit=96.0)
    if gap_sizing is not None:
        trade["gap_sizing"] = gap_sizing
    return trade


def test_heat_carries_the_summed_gap_risk_of_open_shorts(logged_in):
    """v183: 25 sh x max(2, 100 x 4%) = 100.0 for the stamped short; the unstamped
    and the switch-off short are counted, not guessed; the long is not a short."""
    seed_store("trades", [
        _short_trade("a" * 16, "TSLA", gap_sizing=GAP_STAMP),
        _short_trade("b" * 16, "NIO"),
        _short_trade("c" * 16, "RIVN", gap_sizing=dict(GAP_STAMP, rule="stop")),
        _open_trade("d" * 16, "AAPL"),
    ])
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["heat"]["gap_risk_amount"] == pytest.approx(100.0)
    assert body["heat"]["gap_risk_unknown"] == 2
    total = sum(p["risk_pct"] for p in body["positions"])
    assert total == pytest.approx(body["heat"]["open_pct"], abs=0.01)    # heat stays on stop risk


def test_no_open_short_means_no_gap_figure(logged_in):
    seed_store("trades", [_open_trade("a" * 16, "AAPL")])
    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["gap_risk_amount"] is None
    assert heat["gap_risk_unknown"] == 0


def test_only_unknown_shorts_give_null_not_zero(logged_in):
    seed_store("trades", [_short_trade("a" * 16, "NIO"), _short_trade("b" * 16, "RIVN", shares=None)])
    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["gap_risk_amount"] is None
    assert heat["gap_risk_unknown"] == 2


def test_a_failing_trade_read_degrades_the_gap_figure_not_the_page(logged_in, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog.get_trades", boom)
    response = logged_in.get("/api/v1/risk")
    assert response.status_code == 200
    assert response.get_json()["heat"]["gap_risk_amount"] is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: FAIL. `test_risk_shape` reports the missing `heat.gap_risk_amount`, and the three gap tests raise `KeyError: 'gap_risk_amount'`.

- [ ] **Step 3: Implement the figure in `swingbot/admin/api_v1/risk.py`**

Add, after `_positions`:

```python
def _open_short_gap_risk(open_trades: list) -> dict:
    """v183: what the open shorts would lose on a gap the size of each ticker's
    p99 up-gap, summed -- shown beside heat, never added to it (heat stays on
    stop risk). A short without a figure is counted, never guessed at."""
    from swingbot.core.planning.gap_sizing import gap_risk_amount_for

    total, known, unknown = 0.0, 0, 0
    for t in open_trades:
        if t.get("direction") != "bearish":
            continue
        amount = (gap_risk_amount_for(t["shares"], t.get("entry"), t.get("stop_loss"), t.get("gap_sizing"))
                  if t.get("shares") else None)
        if amount is None:
            unknown += 1
        else:
            total, known = total + amount, known + 1
    return {"gap_risk_amount": round(total, 2) if known else None, "gap_risk_unknown": unknown}


def _heat_gap_block() -> dict:
    """The two gap keys for `heat`; a failed trade read degrades to null, like `_positions`."""
    from swingbot.core.tracking.performance import TradeLog

    try:
        return _open_short_gap_risk(TradeLog().get_trades(status="open", limit=None) or [])
    except Exception:
        return {"gap_risk_amount": None, "gap_risk_unknown": 0}
```

In `get_risk`, make the heat dict `{"open_pct": ..., "cap_pct": ..., "utilisation_pct": ..., **_heat_gap_block()}`. Add one line to the module docstring's list of what the endpoint projects: "the open shorts' summed p99 gap risk (v183, display only)". A failed read empties `positions` too, so the page shows its "No open risk" state and never a false "no open shorts".

- [ ] **Step 4: Run the API tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Write the failing frontend specs**

`frontend/src/app/stores/risk.store.spec.ts`, after `'distinguishes zero heat from unknown heat'`:

```ts
  it('exposes the open shorts\' summed gap risk beside heat', () => {
    tick();
    respond({ heat: { open_pct: 3, cap_pct: 6, utilisation_pct: 50,
                      gap_risk_amount: 340, gap_risk_unknown: 1 } });
    expect(store.gapRiskAmount()).toBe(340);
    expect(store.gapRiskUnknown()).toBe(1);
  });

  it('reads an absent gap figure as unknown, never as zero risk', () => {
    tick();
    respond();
    expect(store.gapRiskAmount()).toBeNull();
    expect(store.gapRiskUnknown()).toBe(0);
  });
```

`frontend/src/app/workspaces/risk/risk.spec.ts`, inside `describe('Risk gauge, budget and correlation matrix', ...)`:

```ts
  const gapText = (fixture: ComponentFixture<Risk>) =>
    (fixture.nativeElement as HTMLElement).querySelector('[data-testid="gap-risk"]')!.textContent ?? '';

  it('shows the summed short gap risk inside the heat panel', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: 1234.4, gap_risk_unknown: 0 } });
    const el = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="gap-risk"]')!;
    expect(el.closest('sb-panel')!.getAttribute('heading')).toBe('Portfolio heat');
    expect(gapText(fixture)).toContain('1,234');
    expect(gapText(fixture)).toContain('p99');
    expect(gapText(fixture)).not.toContain('without a gap figure');
  });

  it('counts shorts without a gap figure instead of hiding them', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: null, gap_risk_unknown: 2 } });
    expect(gapText(fixture)).toContain('n/a');
    expect(gapText(fixture)).toContain('2 shorts without a gap figure');
  });

  it('says so when no short is open', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: null, gap_risk_unknown: 0 } });
    expect(gapText(fixture)).toContain('no open shorts');
  });

  it('keeps the heat figure on stop risk', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: 900, gap_risk_unknown: 0 } });
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.heat-figure')!.textContent).toContain('3.10');
    expect(el.querySelector('.heat-note')!.textContent).toContain('52% of the risk budget is used');
  });
```

Run: `cd frontend && npx ng test --watch=false --include=src/app/stores/risk.store.spec.ts --include=src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL. `store.gapRiskAmount is not a function`, and `[data-testid="gap-risk"]` is not found.

- [ ] **Step 6: Implement the store, the model and the panel line**

- `models.ts` `RiskHeat`: add `gap_risk_amount?: number | null;` and `gap_risk_unknown?: number;`, with a comment: "v183. The server always sends both. They are optional here only so pre-v183 fixtures stay valid. Null = no open short has a figure; `gap_risk_unknown` counts the shorts without one."
- `risk.store.ts`, in the `-- heat --` block: `gapRiskAmount: computed(() => data()?.heat?.gap_risk_amount ?? null)` and `gapRiskUnknown: computed(() => data()?.heat?.gap_risk_unknown ?? 0)`, each with a one-line doc comment ("display only; heat stays on stop risk" / "shorts the figure cannot cover, shown, never hidden").
- `risk.ts`:
  - Inject `private readonly connection = inject(ConnectionStore);` (`../../stores/connection.store`) and import `amount` from `../../ui/format`.
  - Add `protected readonly gapRiskNote = computed(() => ...)` returning exactly:
    - amount present: `` `${amount(x, this.connection.currency(), 0)} if every open short gaps by its p99` `` plus the suffix below when `unknown > 0`
    - amount null, `unknown > 0`: `` `n/a` `` plus the suffix
    - amount null, `unknown === 0`: `'no open shorts'`
    - suffix: `` ` · ${unknown} short${unknown === 1 ? '' : 's'} without a gap figure` ``
  - In the Portfolio heat panel, directly after the `heat-note` paragraph and before `<div class="states">`:

    ```html
    <!-- v183: display only. Heat above stays on stop risk; this is what the
         open shorts would lose on a gap the size of each ticker's p99 up-gap. -->
    <p class="gap-risk" data-testid="gap-risk">
      <span class="gap-risk-label">Short gap risk</span>
      <span class="num">{{ gapRiskNote() }}</span>
    </p>
    ```

  - Styles, beside `.heat-note`: `.gap-risk { display: flex; flex-wrap: wrap; gap: var(--space-4) var(--space-8); margin-top: var(--space-6); font-size: var(--text-table); color: var(--text-secondary); overflow-wrap: anywhere; }` and `.gap-risk-label { color: var(--text-muted); }`. It has no control, so it needs no touch target. It wraps onto two lines on a phone and sits on one line on tablet and desktop.

Run: `cd frontend && npx ng test --watch=false --include=src/app/stores/risk.store.spec.ts --include=src/app/workspaces/risk/risk.spec.ts`
Expected: PASS, including the existing `'never declares a fixed px floor a 320px phone cannot meet'`.

- [ ] **Step 7: Check phone, tablet and desktop with Playwright**

Start a local instance built from `.env`'s own values (`docs/claude/skills-tools.md`): `python admin_ui.py` (port 1234), and `cd frontend && npx ng serve --port 4123` in a second background shell. Then:

```bash
node frontend/scripts/browse.mjs shots --base http://localhost:4123 --path "app/dashboard" --click 'a[href*="risk"]' --widths 1280,768,375 --out "<session scratchpad>/v183-risk"
```

`browse.mjs` signs in with `ADMIN_USERNAME`/`ADMIN_PASSWORD`, which it loads from `.env` inside its own process. Never print, echo or pass them. Expected: each `<slug>@<width>.txt` starts with `page-scroll-x: 0`. Each text contains `Short gap risk`; with the replica's book, which has no stamps yet, it reads `no open shorts` or `n/a · N shorts without a gap figure`. In each PNG, the line sits under the heat note inside the Portfolio heat panel. It wraps cleanly at 375 and is on one line at 768 and 1280. If the replica has no open positions the panel shows "No open risk": then say so in the task report and rely on the specs for the line itself. Stop both servers afterwards.

- [ ] **Step 8: Commit**

```bash
git add swingbot/admin/api_v1/risk.py tests/admin/test_api_v1_risk.py frontend/src/app/api/models.ts frontend/src/app/stores/risk.store.ts frontend/src/app/stores/risk.store.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts
git commit -m "feat(v183): risk page shows open shorts' summed p99 gap risk beside heat (V183-9)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

