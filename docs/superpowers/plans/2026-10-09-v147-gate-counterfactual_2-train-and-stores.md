# v147 Gate counterfactual: Part 2, TRAIN recorders and the live store (V147-5..V147-7)

> Part of the v147 plan. Header, Global Constraints, deviations, the block-point table, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v147-gate-counterfactual_0-index.md). **Never read this file whole**: `/task-brief V147-6` or `grep -n "^### Task V147-6:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_2-train-and-stores.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md) § TRAIN side, § Live side / Store, § The report (persistence contract), § Testing.

All commands run inside the plan's worktree `.claude/worktrees/2026-10-09-v147-gate-counterfactual` (created by V147-1). Paths below are relative to it.

Order inside this part: V147-5 and V147-6 need V147-4 (and V147-2/-3 through it) and may run in parallel with each other; V147-7 needs nothing from this part and may start as soon as Group A opens (index § Parallelisation). V147-8 (the light report store) lives in [`_2b-report-store`](2026-10-09-v147-gate-counterfactual_2b-report-store.md), split off for the 1500-line cap.

**Consumed from Part 1 (ledger contracts, final):**
- `gate_counterfactual.BlockedCandidate(ticker, gate, reason, source, strategy, horizon, direction, signal_date, plan=None, scenario=None, scan_params=None, signal_close=None, margin=None)`, `CounterfactualResult(cf_status, cf_r, win, exit_index, last_bar_date, bars_sha256, reanchored, plan)`, `CF_STATUSES`, `simulate_blocked(candidate, bars, *, last_session=None)`.
- `blocked_recorder.TRAIN_WINDOW`, `require_train_window(date_from, date_to, *, validation=False)` (raises `SystemExit(2)`), `over_cap(plan)`, `risk_cap_margin(plan)`, `gate_row(*, population, arm, source, ticker, strategy, horizon, direction, signal_date, gate, reason, margin, cf_status, cf_r, win, planned_loss_pct=None, expiry_bars=None, in_sample=False)`, `row_from_exit(exit_result, plan, **row_fields)`, `write_gate_rows(rows, path) -> int`.
- Checked against Part 1 as written: `row_from_exit` fills `cf_status`, `cf_r`, `win` (through `result_from_exit`) and defaults `ticker`, `strategy`, `horizon`, `direction`, `expiry_bars` from the plan, with `**row_fields` overriding; `gate_row` validates `population`/`arm`/`source`/`gate`/`cf_status` (no `pending`), derives `entry_date` and `dollar_risk`. V147-3 also adds `PIN_KEYS` and the `scan_params` shape `{"stop_mult", "tp2_r", "time_stop_days", "params"}` (V147-6 uses it). If V147-4 landed differently, adapt the call sites here to it — never change V147-4.

**TRAIN hooks fail loud, live hooks fail open.** The TRAIN recorders below are record-only (the replay's trades, stats and printed table never change, proved by an on/off test per hook) but do not swallow their own errors: a silently dropped row would bias an arm. Only the live helper (V147-9) is fail-open.

---

### Task V147-5: Confluence replay hooks + `run_backtest_range.py --record-blocked`

**Model:** opus — record-only hooks inside a parallel replay with legacy C(15)/F(65) functions that must not gain a branch, plus a shadow of the live plan-time cap that must agree with `analyze.attach_plan_v2` exactly.

**Cross-plan (audit 2026-10-10):** v146 (V146-7/V146-8) edits the same two files. Read them as they stand in the worktree first.
- **Task-tuple slots are fixed:** `args[10]` is `spy_df` (v146; `None` when absent) and `args[11]` is `record_blocked`. This task always writes `None` into slot 10 when it appends slot 11, and never reads slot 10.
- **Pool entry point name:** v147's row-recording worker is `_replay_ticker_gate_rows` (v146 owns `_replay_ticker_rows`). Never rename or reshape a v146 function.
- **Step 4, if `replay_scenarios_detailed` exists (V146-7 merged):** `replay_scenarios`' body now lives in `_accept_scenario`. Add `blocked: list | None = None` to both `replay_scenarios` and `replay_scenarios_detailed`, pass it through, thread it into `_accept_scenario(..., blocked)`, and put `_note_blocked(blocked, i, sc)` in `_accept_scenario`'s `if plan is None:` branch (before its `return None`). The `_note_blocked` helper is as in Step 4.
- **Steps 5-6, if `_replay_ticker_rows` or `_replay_exits` exists (V146-8 merged):** keep `_replay_ticker`, `_replay_exits`, `_replay_ticker_rows`, `_run_replay_tasks`, `_drain` and `_replay_with_rows` exactly as v146 left them. Add `_replay_ticker_gate_rows` (Step 5 body) and its helpers beside them instead of rewriting `_replay_ticker`. In `run_scenario_backtest`, keep v146's `collect_rows` arm; the plain arm uses `_replay_ticker_gate_rows` over `[t + (None, True) for t in tasks]` when `record_blocked` (through `_run_replay_tasks`, so no new pool code) and merges through `_scenario_result`; `collect_rows` and `record_blocked` are never both true (Step 8 refuses it), so keep the extra branch inside a helper to hold `run_scenario_backtest` below 15.
- **Step 8, if `_scenario_stats` exists in `run_backtest_range.py` (V146-8 merged):** keep it; pass `record_blocked` through `_scenario_stats(..., record_blocked=bool(record_blocked))` into `run_scenario_backtest`, and call `_write_blocked(stats, record_blocked)` right after it. The dispatch becomes `run_scenario_mode(date_from, date_to, min_n, label, scale_out=args.scale_out, universe=args.universe, trades_jsonl=args.trades_jsonl, record_blocked=args.record_blocked)`.
- **`--trades-jsonl` with `--record-blocked` is refused (exit 2)** whatever merged: `_check_record_blocked` refuses it (Step 8), and the Step 2 refusal matrix carries the case.

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`replay_scenarios` lines 81-165, `_replay_ticker` 192-215, `run_scenario_backtest` 241-290)
- Modify: `scripts/backtest/run_backtest_range.py` (module docstring 1-11, imports 26-34, `run_scenario_mode` 166-191, `main` 366-433)
- Create: `tests/backtesting/test_scenario_gate_rows.py`
- Create: `tests/scripts/test_range_record_blocked.py`

**Interfaces:**
- Consumes: `blocked_recorder.over_cap`, `risk_cap_margin`, `gate_row`, `row_from_exit`, `require_train_window`, `write_gate_rows` (V147-4); `risk_limits.planned_loss_pct(entry_price, stop_loss)` and `HARD_MAX_PLANNED_LOSS_PCT` (exist, `swingbot/core/risk_limits.py:9/17`); `primary_strategy_for` (exists, imported in `backtest_scenarios` already); `exit_sim._not_triggered`, `ExitResult` (exist).
- Produces (ledger): `replay_scenarios(..., blocked: list | None = None)` — appends `(signal_index, scenario)` for every scenario whose `build_confluence_plan` returned `None`, output unchanged; `run_scenario_backtest(..., record_blocked: bool = False)` — adds key `"gate_rows": list[dict]` only when True, `pooled`/`by_horizon` identical either way; `run_scenario_mode(..., record_blocked: str | None = None)`; CLI `--record-blocked PATH`. Private helpers: `_note_blocked`, `_replay_ticker_gate_rows(args) -> tuple[dict, list[dict]]` (task tuple: `args[10]` = `spy_df` slot, `None` here; `args[11]` = record flag), `_horizon_gate_rows`, `_no_target_row`, `_plan_gate_row`, `_scenario_result`, `_bar_date`; script helpers `_check_record_blocked(args, date_from, date_to)`, `_write_blocked(stats, path)`.

**What the rows are.** For every in-scope signal of every horizon: a scenario with no qualifying target is one `blocked` row (`gate="plan_rejected"`, `reason="no_qualifying_target"`, `cf_status="no-plan"`, margin `None`); every simulated plan is one row with its outcome already simulated by the replay itself — `blocked` with `reason="risk_cap"` (margin, `planned_loss_pct`, `dollar_risk`) when `over_cap(plan)`, otherwise `taken` (`reason=None`). No `rs` row and no `compression` row is ever written here. `in_sample=False` (the cap was never fitted on TRAIN). The replay's own `ExitResult` list is untouched, so `pooled`/`by_horizon` and the printed table are byte-identical with and without the flag.

- [ ] **Step 1: Write the failing library tests**

Create `tests/backtesting/test_scenario_gate_rows.py`:

```python
"""v147 T2/T3: the confluence replay's record-only gate rows.

T2 -- `no_qualifying_target`: a scenario whose plan build returned None is a
`blocked`/`no-plan` row. T3 -- `risk_cap`: a record-only shadow of
`analyze.attach_plan_v2`'s plan-time 2% check on every replayed plan; an
over-cap plan's already-simulated outcome moves from `taken` to `blocked`.
The replay's own results never change.
"""
from __future__ import annotations

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.planning.exit_sim import ExitResult, _not_triggered
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.helpers import make_ohlcv

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box: the fixture tests/backtesting/test_backtest_scenarios.py
    uses (local copy, same reason as there: fixtures stay uncoupled)."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def _plan(stop_loss: float, *, direction: str = "bullish") -> TradePlanV2:
    return TradePlanV2(
        plan_id="p1", ticker="AAPL", created_at="2024-01-02", source="confluence",
        strategy="S/R Confluence", horizon_key="4w", direction=direction, entry_type="stop_entry",
        trigger_price=100.0, entry_price=None, expiry_bars=3, stop_loss=stop_loss, tp1=104.0,
        tp1_fraction=0.5, tp2=108.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, status_history=[])


def _filled(r_total: float) -> ExitResult:
    return ExitResult(outcome="win" if r_total > 0 else "loss", runner_outcome=None, entry_index=3,
                      exit_index=6, entry_price=100.0, r_total=r_total,
                      legs=[{"fraction": 1.0, "exit_price": 101.0, "r": r_total, "reason": "tp1"}])


def _analyze_rejects(plan) -> bool:
    """analyze.attach_plan_v2's plan-time check, verbatim (swingbot/core/scanning/analyze.py)."""
    return planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9


DF = make_ohlcv([100.0 + 0.1 * i for i in range(12)])


# -- T3: the risk_cap shadow on fixed plans ----------------------------------------------------------

@pytest.mark.parametrize("stop", [98.5, 98.0, 97.99, 97.0, 95.0, 90.0])
def test_risk_cap_shadow_agrees_with_the_live_plan_time_check(stop):
    plan = _plan(stop)
    row = bs._plan_gate_row("AAPL", DF, "4w", 5, plan, _filled(0.8))
    assert (row["arm"] == "blocked") is _analyze_rejects(plan)
    assert row["gate"] == "plan_rejected" and row["population"] == "train"
    assert row["source"] == "confluence" and row["in_sample"] is False
    assert row["signal_date"] == str(DF.index[5].date()) == row["entry_date"]


def test_an_over_cap_plan_is_a_blocked_risk_cap_row_with_margin_and_dollar_risk():
    plan = _plan(97.0)                                  # 3% planned loss
    row = bs._plan_gate_row("AAPL", DF, "4w", 5, plan, _filled(1.2))
    loss = planned_loss_pct(plan.trigger_price, plan.stop_loss)
    assert (row["arm"], row["reason"]) == ("blocked", "risk_cap")
    assert row["margin"] == pytest.approx(loss - HARD_MAX_PLANNED_LOSS_PCT)
    assert row["planned_loss_pct"] == pytest.approx(loss)
    assert row["cf_status"] == "filled" and row["cf_r"] == pytest.approx(1.2)
    assert row["dollar_risk"] == pytest.approx(1.2 * loss / HARD_MAX_PLANNED_LOSS_PCT)
    assert row["expiry_bars"] == 3


def test_an_in_cap_plan_is_a_taken_row_without_cap_fields():
    row = bs._plan_gate_row("AAPL", DF, "4w", 5, _plan(98.5), _filled(-1.0))
    assert (row["arm"], row["reason"], row["margin"]) == ("taken", None, None)
    assert row["planned_loss_pct"] is None and row["dollar_risk"] is None
    assert row["cf_status"] == "filled" and row["cf_r"] == pytest.approx(-1.0)


def test_a_never_triggered_plan_is_no_fill_with_no_r_in_either_arm():
    for stop in (98.5, 97.0):
        row = bs._plan_gate_row("AAPL", DF, "4w", 5, _plan(stop), _not_triggered("expired"))
        assert row["cf_status"] == "no-fill"
        assert row["cf_r"] is None and row["win"] is None


# -- T2: no_qualifying_target through the real replay ------------------------------------------------

@pytest.mark.slow
def test_replay_records_no_target_scenarios_and_still_returns_nothing(monkeypatch):
    df = _structured_df()
    monkeypatch.setattr(bs, "build_confluence_plan", lambda *a, **k: None)
    blocked: list = []
    assert bs.replay_scenarios("AAPL", df, "4w", gates=GATES, blocked=blocked) == []
    assert bs.replay_scenarios("AAPL", df, "4w", gates=GATES) == []       # default: no sink
    assert blocked, "fixture must produce scenarios"
    assert all(0 <= i < len(df) and sc.direction in ("bullish", "bearish") for i, sc in blocked)


@pytest.mark.slow
def test_no_target_rows_are_blocked_no_plan_rows(monkeypatch):
    df = _structured_df()
    monkeypatch.setattr(bs, "build_confluence_plan", lambda *a, **k: None)
    out, rows = bs._replay_ticker_gate_rows(("AAPL", df, ["4w"], None, None, GATES, True, None, None, None, None, True))
    assert out == {"4w": []}
    assert rows
    for row in rows:
        assert (row["arm"], row["gate"], row["reason"]) == ("blocked", "plan_rejected", "no_qualifying_target")
        assert row["cf_status"] == "no-plan" and row["cf_r"] is None and row["margin"] is None
        assert row["source"] == "confluence" and row["horizon"] == "4w"
        assert row["strategy"]                                           # primary_strategy_for label


@pytest.mark.slow
def test_recording_leaves_the_replay_stats_identical_and_writes_no_rs_row():
    df = _structured_df()
    kwargs = dict(gates=GATES, scale_out=True, horizons=["4w"], workers=1)
    plain = bs.run_scenario_backtest({"AAPL": df}, None, None, **kwargs)
    recorded = bs.run_scenario_backtest({"AAPL": df}, None, None, record_blocked=True, **kwargs)
    assert "gate_rows" not in plain
    assert {k: recorded[k] for k in ("pooled", "by_horizon")} == plain
    rows = recorded["gate_rows"]
    assert rows and {row["gate"] for row in rows} == {"plan_rejected"}
    assert {row["population"] for row in rows} == {"train"}
    out, _ = bs._replay_ticker_gate_rows(("AAPL", df, ["4w"], None, None, GATES, True, None, None, None, None, True))
    simulated = [row for row in rows if row["reason"] != "no_qualifying_target"]
    assert len(simulated) == len(out["4w"])                              # one row per replayed plan


@pytest.mark.slow
def test_rows_respect_the_signal_window():
    df = _structured_df()
    start, end = str(df.index[100].date()), str(df.index[150].date())
    _, rows = bs._replay_ticker_gate_rows(("AAPL", df, ["4w"], start, end, GATES, True, None, None, None, None, True))
    assert rows and all(start <= row["signal_date"] <= end for row in rows)


def test_the_legacy_tuples_still_return_a_horizon_dict(monkeypatch):
    monkeypatch.setattr(bs, "replay_scenarios", lambda *a, **k: [(0, "p0")])
    monkeypatch.setattr(bs, "simulate_exit", lambda df, i, plan, scale_out: plan)
    df = make_ohlcv([1.0, 2.0])
    base = ("T", df, ["2w"], None, None, {}, True, None, None)
    assert bs._replay_ticker(base) == {"2w": ["p0"]}
    assert bs._replay_ticker_gate_rows(base + (None, None, None)) == ({"2w": ["p0"]}, [])   # record flag (args[11]) None: no rows
```

- [ ] **Step 2: Write the failing script tests**

Create `tests/scripts/test_range_record_blocked.py`:

```python
"""v147: `run_backtest_range.py --record-blocked` -- TRAIN-only, confluence scenarios only."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import run_backtest_range as rr  # noqa: E402

from swingbot.core.backtesting.blocked_recorder import gate_row  # noqa: E402


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", *argv])
    return rr.main()


@pytest.fixture
def replay_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(rr, "run_scenario_mode", lambda *a, **k: calls.append((a, k)))
    return calls


@pytest.mark.parametrize("argv", [
    ("--validation", "--scenarios", "--scale-out"),
    ("--from", "2019-06-01", "--to", "2021-12-31", "--scenarios", "--scale-out"),
    ("--from", "2022-01-01", "--to", "2024-03-31", "--scenarios", "--scale-out"),
    ("--train", "--scale-out"),          # no --scenarios: compression rows come from measure_arms.py
    ("--train", "--scenarios"),          # no --scale-out: the counterfactual walk is scale_out=True
    ("--train", "--scenarios", "--scale-out", "--trades-jsonl", "rows-v146.jsonl"),   # exclusive with v146's rows
])
def test_record_blocked_refuses_before_any_replay(monkeypatch, replay_calls, tmp_path, argv):
    out = tmp_path / "rows.jsonl"
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, *argv, "--record-blocked", str(out))
    assert exc.value.code == 2
    assert replay_calls == [] and not out.exists()


def test_train_scenarios_pass_the_path_to_scenario_mode(monkeypatch, replay_calls, tmp_path):
    out = tmp_path / "rows.jsonl"
    _main(monkeypatch, "--train", "--scenarios", "--scale-out", "--record-blocked", str(out))
    ((args, kwargs),) = replay_calls
    assert args[:2] == ("2020-01-01", "2023-12-31")
    assert kwargs["record_blocked"] == str(out) and kwargs["scale_out"] is True


def test_a_custom_train_slice_is_accepted(monkeypatch, replay_calls, tmp_path):
    _main(monkeypatch, "--from", "2021-01-01", "--to", "2021-06-30", "--scenarios", "--scale-out",
          "--record-blocked", str(tmp_path / "rows.jsonl"))
    assert len(replay_calls) == 1


def test_without_the_flag_nothing_is_refused_and_none_is_passed(monkeypatch, replay_calls):
    _main(monkeypatch, "--from", "2024-01-01", "--to", "2024-06-30", "--scenarios")
    assert replay_calls[0][1]["record_blocked"] is None


def test_write_blocked_writes_the_gate_rows_and_skips_without_a_path(tmp_path):
    row = gate_row(population="train", arm="blocked", source="confluence", ticker="AAPL",
                   strategy="S/R Confluence", horizon="4w", direction="bullish", signal_date="2021-03-01",
                   gate="plan_rejected", reason="no_qualifying_target", margin=None, cf_status="no-plan",
                   cf_r=None, win=None)
    out = tmp_path / "rows.jsonl"
    rr._write_blocked({"pooled": {}, "gate_rows": [row]}, str(out))
    assert [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] == [row]
    rr._write_blocked({"pooled": {}}, None)                          # no flag: nothing to do, no error
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_gate_rows.py tests/scripts/test_range_record_blocked.py`
Expected: FAIL — `AttributeError: module ... has no attribute '_plan_gate_row'` / `'_replay_ticker_gate_rows'`, `replay_scenarios() got an unexpected keyword argument 'blocked'`, and the script tests fail on `unrecognized arguments: --record-blocked`.

- [ ] **Step 4: Hook `replay_scenarios` (no new branch)**

In `swingbot/core/backtesting/backtest_scenarios.py`, add above `replay_scenarios`:

```python
def _note_blocked(blocked: list | None, index: int, scenario) -> None:
    """v147 record-only: remember a scenario whose plan build found no qualifying target.
    A helper so `replay_scenarios` (C 15, legacy) gains no branch."""
    if blocked is not None:
        blocked.append((index, scenario))
```

Change the signature (add the keyword after `asof=None`):

```python
def replay_scenarios(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                     gates: dict | None = None,
                     dcb_params: dict | None = None, asof=None,
                     blocked: list | None = None) -> list:
```

Append to its docstring:

```python
    `blocked` (v147, record-only): when a list, every scenario whose
    `build_confluence_plan` returned None is appended as `(signal_index,
    scenario)` -- the confluence `no_qualifying_target` block. The return
    value, the cooldown state and every plan are unchanged.
```

and replace the `plan is None` branch body:

```python
            if plan is None:
                _note_blocked(blocked, i, sc)
                continue          # no qualifying target -> no trade, same as live
```

- [ ] **Step 5: Split `_replay_ticker` into a row-recording core**

Replace the whole `_replay_ticker` function (keep its docstring text, moved onto `_replay_ticker_gate_rows`) with (if V146-8 merged, see the Cross-plan block: keep v146's `_replay_ticker` and add only `_replay_ticker_gate_rows` and the helpers below):

```python
def _replay_ticker(args) -> dict:
    """All horizons for ONE ticker: {horizon_key: [exit_result, ...]} (see `_replay_ticker_gate_rows`)."""
    return _replay_ticker_gate_rows(args)[0]


def _replay_ticker_gate_rows(args) -> tuple[dict, list]:
    """All horizons for ONE ticker -- the process-pool entry point, so it must
    be module-level and take a single picklable argument.

    Grouped per ticker rather than per (ticker, horizon) pair on purpose: the
    OHLCV frame is the expensive thing to move across a process boundary (~2MB
    for a ten-year daily history), and a per-pair split would ship the same
    frame once per horizon -- ten times the IPC for parallelism a 2-4 core box
    cannot use anyway. At 300-500 tickers there are already far more tasks
    than cores.

    Returns ({horizon_key: [exit_result, ...]}, gate_rows). The horizon travels
    in the RESULT rather than being inferred from completion order, which is what
    makes the pooled path order-independent. `args[11]` (v147, optional) asks for
    the record-only gate rows; without it the row list is always empty. `args[10]`
    is v146's SPY slot and is not read here.
    """
    ticker, df, horizons, start, end, gates, scale_out, dcb_params = args[:8]
    asof_df = args[8] if len(args) > 8 else None
    member_spans = args[9] if len(args) > 9 else None
    record = bool(args[11]) if len(args) > 11 else False
    out = {hk: [] for hk in horizons}
    rows: list = []
    for hk in horizons:
        blocked = [] if record else None
        taken = []
        for i, plan in replay_scenarios(ticker, df, hk, gates=gates, dcb_params=dcb_params,
                                        asof=asof_df, blocked=blocked):
            if not _signal_in_scope(_bar_date(df, i), start, end, member_spans):
                continue
            result = simulate_exit(df, i, plan, scale_out=scale_out)
            out[hk].append(result)
            taken.append((i, plan, result))
        if record:
            rows.extend(_horizon_gate_rows(ticker, df, hk, taken, blocked, (start, end, member_spans)))
    return out, rows


def _bar_date(df, index: int) -> str:
    return str(df.index[index].date())


def _horizon_gate_rows(ticker, df, horizon_key, taken, blocked, scope) -> list[dict]:
    """v147 T2 + T3 for one (ticker, horizon): in-scope no-target scenarios, then every replayed plan."""
    start, end, member_spans = scope
    rows = [_no_target_row(ticker, df, horizon_key, i, sc) for i, sc in blocked
            if _signal_in_scope(_bar_date(df, i), start, end, member_spans)]
    rows.extend(_plan_gate_row(ticker, df, horizon_key, i, plan, result) for i, plan, result in taken)
    return rows


def _no_target_row(ticker, df, horizon_key, index, scenario) -> dict:
    """T2: `build_confluence_plan` returned None -- nothing to simulate, so `no-plan`."""
    from swingbot.core.backtesting import blocked_recorder
    return blocked_recorder.gate_row(
        population="train", arm="blocked", source="confluence", ticker=ticker,
        strategy=primary_strategy_for(scenario), horizon=horizon_key, direction=scenario.direction,
        signal_date=_bar_date(df, index), gate="plan_rejected", reason="no_qualifying_target",
        margin=None, cf_status="no-plan", cf_r=None, win=None)


def _plan_gate_row(ticker, df, horizon_key, index, plan, result) -> dict:
    """T3: the record-only shadow of attach_plan_v2's plan-time 2% check on one replayed plan.
    Over the cap -> `blocked`/`risk_cap` (an over-cap counterfactual, never tradable); else `taken`.
    The outcome is the replay's own ExitResult -- nothing is re-simulated."""
    from swingbot.core.backtesting import blocked_recorder
    from swingbot.core.risk_limits import planned_loss_pct
    capped = blocked_recorder.over_cap(plan)
    return blocked_recorder.row_from_exit(
        result, plan, population="train", arm="blocked" if capped else "taken", source="confluence",
        ticker=ticker, strategy=plan.strategy, horizon=horizon_key, direction=plan.direction,
        signal_date=_bar_date(df, index), gate="plan_rejected",
        reason="risk_cap" if capped else None,
        margin=blocked_recorder.risk_cap_margin(plan) if capped else None,
        planned_loss_pct=planned_loss_pct(plan.trigger_price, plan.stop_loss) if capped else None,
        in_sample=False)
```

The imports of `blocked_recorder` are lazy on purpose: they keep `backtest_scenarios`' import graph (used by every replay script) unchanged and rule out an import cycle through `swingbot.core.backtesting`.

- [ ] **Step 6: `run_scenario_backtest(record_blocked=...)` through one aggregation helper**

`run_scenario_backtest` is C(14); its two merge loops move into `_scenario_result` so the new key costs it no branch. Replace the function's signature line and everything from `horizons = horizons or ...` to the final `return`:

```python
def run_scenario_backtest(frames: dict, start, end, *, gates,
                          scale_out=True, horizons=None, workers=None,
                          dcb_params: dict | None = None, asof_map: dict | None = None,
                          membership: dict | None = None, record_blocked: bool = False) -> dict:
```

(append to the docstring: ``` `record_blocked` (v147): also return "gate_rows", the record-only TRAIN gate rows (`_horizon_gate_rows`); "pooled"/"by_horizon" are identical either way. ```), then the body:

```python
    horizons = horizons or list(LEGACY_HORIZONS)

    tasks = [
        (ticker, df, horizons, start, end, gates, scale_out, dcb_params,
         asof_map.get(ticker) if asof_map else None,
         membership.get(ticker, []) if membership is not None else None,
         None,              # args[10]: v146's spy_df slot, unused here
         record_blocked)    # args[11]: v147 record flag
        for ticker, df in frames.items()
    ]

    n = _resolve_replay_workers(workers)
    if n <= 1 or len(tasks) <= 1:
        per_ticker_results = [_replay_ticker_gate_rows(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=n) as pool:
            per_ticker_results = list(pool.map(_replay_ticker_gate_rows, tasks))
    return _scenario_result(per_ticker_results, horizons, record_blocked)


def _scenario_result(per_ticker_results, horizons, record_blocked: bool) -> dict:
    """Merge the per-ticker (results, rows) pairs strictly after every task returned."""
    results_by_hz: dict = {hk: [] for hk in horizons}
    gate_rows: list = []
    for per_ticker, rows in per_ticker_results:
        gate_rows.extend(rows)
        for hk, results in per_ticker.items():
            results_by_hz[hk].extend(results)
    all_results = [r for rs in results_by_hz.values() for r in rs]
    out = {"pooled": _aggregate(all_results),
           "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}
    if record_blocked:
        out["gate_rows"] = gate_rows
    return out
```

- [ ] **Step 7: Run the library tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_gate_rows.py tests/backtesting/test_backtest_scenarios.py tests/backtesting/test_scenario_parallel.py tests/scripts/test_training_universe.py tests/scripts/test_fvg_attribution.py`
Expected: PASS (the last four pin the unchanged replay: stats shape, sequential == parallel, the 9/10-tuple `_replay_ticker`, the source substrings the FVG recorder patches).

- [ ] **Step 8: Add the CLI flag to `run_backtest_range.py`**

Module docstring, after the `--from ... --strategy "RSI"` usage line:

```
    python scripts/backtest/run_backtest_range.py --train --scenarios --scale-out --record-blocked logs/v147-blocked-confluence.jsonl   # v147 TRAIN gate rows
```

Imports, after the `backtest_scenarios` import:

```python
from swingbot.core.backtesting.blocked_recorder import require_train_window, write_gate_rows
```

Add two helpers above `run_scenario_mode`:

```python
def _check_record_blocked(args, date_from, date_to) -> None:
    """v147: `--record-blocked` is TRAIN-only, confluence-scenarios-only and needs the scale-out walk.

    Compression blocks are recorded by `measure_arms.py --record-blocked` (StrategyEngine), because
    `run_backtest` refuses the compression short; RS is never recorded on TRAIN (v34 closed).
    Exits 2 before any data is loaded."""
    if not args.record_blocked:
        return
    if getattr(args, "trades_jsonl", None):
        print("refused: --record-blocked and --trades-jsonl are exclusive (run them as two replays)",
              file=sys.stderr)
        raise SystemExit(2)
    if not args.scenarios:
        print("refused: --record-blocked needs --scenarios (confluence no_qualifying_target + risk_cap shadow); "
              "compression rows come from scripts/backtest/measure_arms.py --record-blocked", file=sys.stderr)
        raise SystemExit(2)
    if not args.scale_out:
        print("refused: --record-blocked needs --scale-out (the counterfactual walk is scale_out=True)",
              file=sys.stderr)
        raise SystemExit(2)
    require_train_window(date_from, date_to, validation=args.validation)


def _write_blocked(stats: dict, path) -> None:
    """v147: write the replay's record-only gate rows when --record-blocked asked for them."""
    if not path:
        return
    count = write_gate_rows(stats.get("gate_rows", []), path)
    print(f"Wrote {count} gate rows to {path}", flush=True)
```

`run_scenario_mode` (C 19 — one keyword, one argument, one helper call, no branch). Signature:

```python
def run_scenario_mode(date_from, date_to, min_n, label, *, scale_out, universe=None, record_blocked=None):
```

the replay call:

```python
    stats = run_scenario_backtest(frames, date_from, date_to,
                                  gates=CONFLUENCE_GATES, scale_out=scale_out,
                                  horizons=list(LEGACY_HORIZONS), membership=membership,
                                  record_blocked=bool(record_blocked))
    _write_blocked(stats, record_blocked)
```

`main` (F 65 — one `add_argument`, one helper call, one keyword; no branch). After the `--trades-jsonl` argument:

```python
    ap.add_argument("--record-blocked", dest="record_blocked", default=None,
                    help="v147: write one JSONL gate row per blocked/taken confluence candidate "
                         "(TRAIN window only; needs --scenarios --scale-out)")
```

directly after the `if args.train: ... else: ... label = ..., "CUSTOM"` window block:

```python
    _check_record_blocked(args, date_from, date_to)
```

and the scenarios dispatch (with V146-8 merged, add `trades_jsonl=args.trades_jsonl,` before `record_blocked=` -- see the Cross-plan block):

```python
    if args.scenarios:
        run_scenario_mode(date_from, date_to, min_n, label, scale_out=args.scale_out,
                          universe=args.universe, record_blocked=args.record_blocked)
        return
```

- [ ] **Step 9: Run the script tests and the existing script test**

Run: `python scripts/dev/testrun.py file tests/scripts/test_range_record_blocked.py tests/scripts/test_range_trades_jsonl.py`
Expected: PASS.

- [ ] **Step 10: Complexity gate**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/backtest_scenarios.py scripts/backtest/run_backtest_range.py`
Expected: exactly the legacy lines and no new one — `_aggregate C (18)`, `replay_scenarios C (15)` (unchanged), `main F (65)`, `run_scenario_mode C (19)`, `pool C (15)`. `run_scenario_backtest` must no longer be listed (it drops below C), and no new helper appears.

- [ ] **Step 11: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py scripts/backtest/run_backtest_range.py tests/backtesting/test_scenario_gate_rows.py tests/scripts/test_range_record_blocked.py
git commit -m "feat(v147): confluence replay gate rows + run_backtest_range --record-blocked (V147-5)"
```

### Task V147-6: StrategyEngine compression rows + `measure_arms.py --record-blocked`

**Model:** opus — a record-only sink threaded through the research engine's decision path (its `iter_trades` is already C 14 and cannot take a branch), with a parity test that the rebuilt blocked plan and the engine's own taken plan walk to the same outcome.

**Cross-plan (audit 2026-10-10):**
- **v157 (`instrument` on `StrategyEngine`).** If `instrument` is already a parameter of `StrategyEngine.__init__` (v157 merged), the signature is `(self, strategies=None, compression_context=None, instrument=None, *, blocked_sink=None, compression_allowlist=None)`, keeping both groups of `self.` assignments (v157's and the two below). Without v157 it is the Step 4 signature (no `instrument`). Either way the keyword-only group is exactly `blocked_sink`, `compression_allowlist`.
- **v158 (`--instrument` CLI).** If `swingbot/core/backtesting/instrument/cli.py` exists (v158 merged), `record_blocked_main` calls `instrument_cli.add_instrument_arg(parser)` after the `--validation` argument and, right after `parse_args`, `instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_arms.py --record-blocked", "v147")` (import `from swingbot.core.backtesting.instrument import cli as instrument_cli` inside the function); `test_measure_arms_record_blocked.py` then also passes `--instrument v1` in one case and asserts a `--instrument v2` refusal exits non-zero. Check v158's WC6 task for the exact names before writing; otherwise write Step 7 as shown.

**Files:**
- Modify: `swingbot/core/backtesting/arms/strategy_engine.py` (constants 37-43, `StrategyEngine.__init__` 85-94, `_compression_stamp` 147-162, `_candidate_plan` 218-243)
- Modify: `swingbot/core/backtesting/arms/compression_research.py` (after `sidecar_record`, ~line 116)
- Modify: `scripts/backtest/measure_arms.py` (new `record_blocked_main` and `cli` after `main`; the `__main__` block)
- Create: `tests/backtesting/arms/test_strategy_engine_gate_rows.py`
- Create: `tests/scripts/test_measure_arms_record_blocked.py`

**Interfaces:**
- Consumes: `gate_counterfactual.BlockedCandidate`, `simulate_blocked`, `CounterfactualResult` (V147-2), `PIN_KEYS` (V147-3, additive; the `scan_params` shape `{"stop_mult", "tp2_r", "time_stop_days", "params"}`); `blocked_recorder.gate_row`, `TRAIN_WINDOW`, `require_train_window`, `write_gate_rows` (V147-4); `plan_types.plan_to_dict` (exists, `swingbot/core/planning/plan_types.py:185`); `compression_context.COMPRESSION_MODES` (exists, `swingbot/core/scanning/compression_context.py:90`); `compression_research.offline_context()` (exists); `measure_arms.cached_universe()`, `load_frame()` (exist).
- Produces (ledger): `StrategyEngine.__init__(self, strategies=None, compression_context=None, *, blocked_sink: list | None = None, compression_allowlist: tuple | None = None)` (with `instrument=None` as the third positional only if v157 merged); `compression_research.record_blocked_compression(frames, window, *, context, horizons=("2w",)) -> list[dict]`; CLI `measure_arms.py --record-blocked PATH [--from --to]` through `measure_arms.cli(argv=None) -> int` (early dispatch; `main` untouched) and `measure_arms.record_blocked_main(argv) -> int` (own parser).
- Sink protocol (private to this task): `blocked_sink` receives `(arm, BlockedCandidate)` tuples, `arm` in `("blocked", "taken")`. A `blocked` candidate carries `reason` (the `decide_compression_entry` reason) and `plan=None` — `simulate_blocked` builds it on the truncated window. A `taken` candidate carries `reason=None` and `plan=plan_to_dict(plan)` of the plan the engine itself built (stamp merged) — `simulate_blocked` walks it as stored. One instrument, both arms.

**What is and is not a row.** Every *counted* (`signal_date >= window start`) compression candidate that reaches the decision is one row: rejected by `decide_compression_entry` → `blocked` (reasons `no_mode`, `mode_not_allowed`, `earnings_*`, …); passed → `taken` (its walk may be `no-fill`). `not_pit_member` is the research universe mask, not the gate: never a row (index T1). Plan-construction failures after a pass (`plan is None`, O8) and non-compression strategies write nothing. Every row is `population="train"`, `gate="compression"`, `source="strategy"`, `margin=None`, `in_sample=True` (v119 fitted the gate on TRAIN). The decision uses the live allowlist (`COMPRESSION_MODES`, as `strategy_pass._compression_context` does), whatever the research knob says. A `pending` simulator status (too few bars after the signal; no TRAIN resolver exists) is written as `no-data`.

- [ ] **Step 1: Write the failing engine and recorder tests**

Create `tests/backtesting/arms/test_strategy_engine_gate_rows.py`:

```python
"""v147 T1: TRAIN compression gate rows through StrategyEngine (in-sample).

The world is v119's compression-short fixture (tests/backtesting/test_measure_compression_short.py):
one bearish 2w candidate on SIGNAL_DAY whose resting sell-stop fills next bar and time-exits on the
tenth session. A clear earnings snapshot admits it (taken); no snapshot rejects it as
earnings_unknown (blocked). The sink is record-only: trades and counters never change.
"""
from __future__ import annotations

import dataclasses

import pytest

from swingbot.core.backtesting import gate_counterfactual
from swingbot.core.backtesting.arms import compression_research as cr
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.scan_params import ScanParams
from tests.backtesting.test_measure_compression_short import (  # noqa: F401  (pins: autouse fixture)
    FULL_PATH, SIGNAL_DAY, SIGNAL_POS, WINDOW, _context, pins)


def _unknown(ticker, decided_at):
    return None                                       # no as-of archive -> earnings_unknown


def _run(context, *, sink=None, allowlist=None):
    engine = StrategyEngine((COMPRESSION_SHORT,), compression_context=context,
                            blocked_sink=sink, compression_allowlist=allowlist)
    trades = engine.run_ticker("ABC", FULL_PATH, ("2w",), WINDOW, ScanParams.from_config())
    return engine, trades


@pytest.mark.parametrize("snapshot_of", [None, _unknown])
def test_the_sink_is_record_only(snapshot_of):
    context = _context() if snapshot_of is None else _context(snapshot_of=snapshot_of)
    plain_engine, plain = _run(context)
    sunk_engine, sunk = _run(context, sink=[])
    assert [dataclasses.asdict(t) for t in sunk] == [dataclasses.asdict(t) for t in plain]
    assert sunk_engine.compression_reasons == plain_engine.compression_reasons
    assert sunk_engine.compression_excluded == plain_engine.compression_excluded


def test_a_rejected_candidate_is_a_blocked_candidate_without_a_plan():
    sink: list = []
    _, trades = _run(_context(snapshot_of=_unknown), sink=sink)
    assert trades == []
    ((arm, candidate),) = sink
    assert arm == "blocked"
    assert (candidate.gate, candidate.reason, candidate.source) == ("compression", "earnings_unknown", "strategy")
    assert (candidate.strategy, candidate.horizon, candidate.direction) == (COMPRESSION_SHORT, "2w", "bearish")
    assert candidate.signal_date == SIGNAL_DAY.isoformat()
    assert candidate.plan is None and candidate.margin is None
    assert candidate.scan_params["stop_mult"] is None and candidate.scan_params["params"]   # the engine's call
    assert candidate.signal_close == pytest.approx(float(FULL_PATH["Close"].iloc[SIGNAL_POS]))


def test_a_passed_candidate_is_a_taken_candidate_carrying_the_engines_plan():
    sink: list = []
    _, trades = _run(_context(), sink=sink)
    assert len(trades) == 1
    ((arm, candidate),) = sink
    assert arm == "taken" and candidate.reason is None
    assert candidate.plan["strategy"] == COMPRESSION_SHORT
    assert candidate.plan["entry_context"]["compression_mode"] == "broad"


def test_the_research_membership_mask_is_never_a_row():
    sink: list = []
    engine, _ = _run(_context(member_on=lambda ticker, day: False), sink=sink)
    assert sink == [] and engine.compression_reasons == {"not_pit_member": 1}


def test_the_allowlist_override_decides_instead_of_the_research_knob():
    sink: list = []
    _run(_context(), sink=sink, allowlist=("isolated",))       # falling SPY: a broad candidate
    ((arm, candidate),) = sink
    assert (arm, candidate.reason) == ("blocked", "mode_not_allowed")


def test_record_blocked_compression_walks_both_arms_through_one_instrument():
    taken_rows = cr.record_blocked_compression({"ABC": FULL_PATH}, WINDOW, context=_context())
    blocked_rows = cr.record_blocked_compression({"ABC": FULL_PATH}, WINDOW,
                                                 context=_context(snapshot_of=_unknown))
    (taken,) = taken_rows
    (blocked,) = blocked_rows
    for row in (taken, blocked):
        assert (row["population"], row["gate"], row["source"]) == ("train", "compression", "strategy")
        assert row["in_sample"] is True and row["margin"] is None
        assert row["signal_date"] == SIGNAL_DAY.isoformat() and row["horizon"] == "2w"
        assert row["cf_status"] == "filled"
    assert (taken["arm"], taken["reason"]) == ("taken", None)
    assert (blocked["arm"], blocked["reason"]) == ("blocked", "earnings_unknown")
    _, (trade,) = _run(_context())
    assert taken["cf_r"] == pytest.approx(trade.r_multiple)
    # The truncated rebuild of the rejected candidate is the same constructor on the same bars:
    # a mismatch here is a real divergence between simulate_blocked and the engine -- stop and
    # report it, never loosen the assertion.
    assert blocked["cf_r"] == pytest.approx(taken["cf_r"])


def test_a_pending_simulation_is_written_as_no_data(monkeypatch):
    pending = gate_counterfactual.CounterfactualResult(
        cf_status="pending", cf_r=None, win=None, exit_index=None, last_bar_date=None,
        bars_sha256=None, reanchored=False, plan=None)
    monkeypatch.setattr(gate_counterfactual, "simulate_blocked", lambda candidate, bars, **kw: pending)
    (row,) = cr.record_blocked_compression({"ABC": FULL_PATH}, WINDOW, context=_context(snapshot_of=_unknown))
    assert row["cf_status"] == "no-data" and row["cf_r"] is None and row["win"] is None


def test_a_signal_before_the_window_start_is_never_a_row():
    late_window = ("2019-03-04", "2020-12-31")                # SIGNAL_DAY (2019-03-01) is warm-up
    assert cr.record_blocked_compression({"ABC": FULL_PATH}, late_window, context=_context()) == []
```

- [ ] **Step 2: Write the failing CLI tests**

Create `tests/scripts/test_measure_arms_record_blocked.py`:

```python
"""v147: `measure_arms.py --record-blocked` -- TRAIN compression gate rows, own parser, early dispatch."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot.core.backtesting.arms import compression_research as cr  # noqa: E402
from swingbot.core.backtesting.blocked_recorder import gate_row  # noqa: E402


def _row(ticker):
    return gate_row(population="train", arm="blocked", source="strategy", ticker=ticker,
                    strategy="Compression Short", horizon="2w", direction="bearish",
                    signal_date="2021-03-01", gate="compression", reason="earnings_unknown", margin=None,
                    cf_status="filled", cf_r=-0.4, win=False, expiry_bars=3, in_sample=True)


@pytest.mark.parametrize("extra", [["--validation"], ["--from", "2019-01-01"], ["--to", "2024-01-31"]])
def test_refuses_outside_train_before_loading_anything(monkeypatch, tmp_path, extra):
    monkeypatch.setattr(ma, "cached_universe", lambda: pytest.fail("loaded the universe"))
    monkeypatch.setattr(cr, "offline_context", lambda: pytest.fail("built the context"))
    out = tmp_path / "rows.jsonl"
    with pytest.raises(SystemExit) as exc:
        ma.cli(["--record-blocked", str(out), *extra])
    assert exc.value.code == 2 and not out.exists()


def test_writes_one_jsonl_file_from_the_backtest_cache_frames(monkeypatch, tmp_path, capsys):
    frames = {"AAA": "frame-a", "BBB": None, "CCC": "frame-c"}
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(ma, "load_frame", lambda ticker: frames[ticker])
    monkeypatch.setattr(cr, "offline_context", lambda: "ctx")
    calls = []

    def fake(frames_, window, *, context, horizons=("2w",)):
        calls.append((dict(frames_), window, context))
        return [_row(ticker) for ticker in frames_]

    monkeypatch.setattr(cr, "record_blocked_compression", fake)
    out = tmp_path / "nested" / "rows.jsonl"
    assert ma.cli(["--record-blocked", str(out)]) == 0
    assert calls == [({"AAA": "frame-a"}, ("2020-01-01", "2023-12-31"), "ctx"),
                     ({"CCC": "frame-c"}, ("2020-01-01", "2023-12-31"), "ctx")]
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["ticker"] for row in rows] == ["AAA", "CCC"]
    assert "3/3" in capsys.readouterr().out                    # flushed per-ticker progress


def test_cli_without_the_flag_is_main_unchanged(monkeypatch):
    monkeypatch.setattr(ma, "main", lambda argv: ("main", argv))
    assert ma.cli(["--knob", "X=1", "--stage", "pilot"]) == ("main", ["--knob", "X=1", "--stage", "pilot"])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_strategy_engine_gate_rows.py tests/scripts/test_measure_arms_record_blocked.py`
Expected: FAIL — `StrategyEngine.__init__() got an unexpected keyword argument 'blocked_sink'`, `module ... has no attribute 'record_blocked_compression'`, `module 'measure_arms' has no attribute 'cli'`.

- [ ] **Step 4: The engine sink**

In `swingbot/core/backtesting/arms/strategy_engine.py`, add `import dataclasses` to the stdlib imports (the module imports only `from dataclasses import dataclass` today), then after `RESEARCH_KNOB = ...`:

```python
#: v147: decide reasons that are research-universe masks, not the compression gate -- never a gate row.
_NOT_A_GATE_REASONS = frozenset({"not_pit_member"})


def _sink_candidate(ticker, window, strategy, horizon_key, direction, params, *, reason=None, plan=None):
    """v147: one compression candidate as a BlockedCandidate, from the signal-bar window only.

    `scan_params` mirrors the engine's own build call exactly: no override pinned (the engine passes
    none either) and the run's ScanParams, so a rebuilt blocked plan uses the constructor the taken
    arm used. With DATA_DRIVEN_STOPS_ENABLED on, V147-3 refuses the rebuild (no-data), as the
    replays refuse live-state flags."""
    from swingbot.core.backtesting.gate_counterfactual import PIN_KEYS, BlockedCandidate
    from swingbot.core.planning.plan_types import plan_to_dict
    scan_params = {**dict.fromkeys(PIN_KEYS), "params": dataclasses.asdict(params) if params is not None else None}
    return BlockedCandidate(
        ticker=ticker, gate="compression", reason=reason, source="strategy", strategy=strategy,
        horizon=horizon_key, direction=direction, signal_date=str(window.index[-1].date()),
        plan=plan_to_dict(plan) if plan is not None else None, scan_params=scan_params,
        signal_close=float(window["Close"].iloc[-1]))
```

`__init__`:

```python
    def __init__(self, strategies=None, compression_context: CompressionResearchContext | None = None, *,
                 blocked_sink: list | None = None, compression_allowlist: tuple | None = None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)
        self.compression_context = compression_context
        # v147, record-only: (arm, BlockedCandidate) per counted compression decision; None = off.
        self.blocked_sink = blocked_sink
        # v147: the decision's mode allowlist; None keeps the research-knob derivation below.
        self.compression_allowlist = compression_allowlist
        self.compression_reasons: Counter = Counter()
```

(the remaining lines of `__init__` stay as they are).

In `_compression_stamp`, replace

```python
        knob = research_mode()
        allowlist = (knob,) if knob in cc.COMPRESSION_MODES else cc.COMPRESSION_MODES
```

with

```python
        allowlist = self._allowlist(cc)
```

and add the method after `_compression_stamp`:

```python
    def _allowlist(self, cc) -> tuple:
        """The explicit allowlist when one was given (v147 records under the live one); otherwise one
        research mode under the knob, every mode when it is off."""
        if self.compression_allowlist is not None:
            return tuple(self.compression_allowlist)
        knob = research_mode()
        return (knob,) if knob in cc.COMPRESSION_MODES else cc.COMPRESSION_MODES
```

In `_candidate_plan`, two helper calls and no new branch:

```python
        if strategy == COMPRESSION_SHORT:
            self._candidate = (ticker, str(window.index[-1].date()))
            stamp, reason = self._compression_stamp(ticker, window)
            if reason is not None:
                self._note_blocked(ticker, window, strategy, horizon_key, direction, params, reason, counted)
                if counted:
                    self._count(stamp, reason)
                return None, stamp
```

and at its end:

```python
        if stamp:
            plan.entry_context = {**(plan.entry_context or {}), **stamp}
        self._note_taken(ticker, window, strategy, horizon_key, direction, params, plan, counted)
        return plan, stamp
```

Add the two methods after `_candidate_plan`:

```python
    def _note_blocked(self, ticker, window, strategy, horizon_key, direction, params, reason, counted) -> None:
        """v147 record-only: a counted compression reject to the sink (research masks skipped)."""
        if self.blocked_sink is None or not counted or reason in _NOT_A_GATE_REASONS:
            return
        self.blocked_sink.append(
            ("blocked", _sink_candidate(ticker, window, strategy, horizon_key, direction, params, reason=reason)))

    def _note_taken(self, ticker, window, strategy, horizon_key, direction, params, plan, counted) -> None:
        """v147 record-only: a counted compression plan that passed the decision, as the engine built it."""
        if self.blocked_sink is None or not counted or strategy != COMPRESSION_SHORT:
            return
        self.blocked_sink.append(
            ("taken", _sink_candidate(ticker, window, strategy, horizon_key, direction, params, plan=plan)))
```

Add one sentence to the module docstring: ``` v147: an optional `blocked_sink` records every counted compression decision (rejected -> "blocked", passed -> "taken") for the gate counterfactual; it never changes a trade or a counter. ```

- [ ] **Step 5: `record_blocked_compression`**

In `swingbot/core/backtesting/arms/compression_research.py`, after `sidecar_record`:

```python
def record_blocked_compression(frames: dict, window: tuple[str, str], *, context: CompressionResearchContext,
                               horizons=("2w",)) -> list[dict]:
    """v147 TRAIN compression gate rows (in-sample: v119 fitted the gate on TRAIN).

    Every counted compression decision over `frames` (backtest-cache frames) under the LIVE mode
    allowlist: a reject is a `blocked` row simulated from the signal bar by `simulate_blocked` (plan
    rebuilt on the truncated window), a pass is a `taken` row walking the engine's own plan through
    the same call. The research knob is not read for the decision; the replay's trades are untouched."""
    from swingbot.core.scanning.compression_context import COMPRESSION_MODES
    from swingbot.scan_params import ScanParams
    sink: list = []
    engine = StrategyEngine((COMPRESSION_SHORT,), compression_context=context, blocked_sink=sink,
                            compression_allowlist=COMPRESSION_MODES)
    params = ScanParams.from_config()
    for ticker in sorted(frames):
        engine.run_ticker(ticker, frames[ticker], horizons, window, params)
    return [_compression_gate_row(arm, candidate, frames[candidate.ticker]) for arm, candidate in sink]


def _compression_gate_row(arm: str, candidate, frame) -> dict:
    """One sink entry walked through the shared simulator; TRAIN has no resolver, so pending -> no-data."""
    from swingbot.core.backtesting import gate_counterfactual
    from swingbot.core.backtesting.blocked_recorder import gate_row
    result = gate_counterfactual.simulate_blocked(candidate, frame)
    status = "no-data" if result.cf_status == "pending" else result.cf_status
    filled = status == "filled"
    return gate_row(
        population="train", arm=arm, source="strategy", ticker=candidate.ticker,
        strategy=candidate.strategy, horizon=candidate.horizon, direction=candidate.direction,
        signal_date=candidate.signal_date, gate="compression", reason=candidate.reason, margin=None,
        cf_status=status, cf_r=result.cf_r if filled else None, win=result.win if filled else None,
        expiry_bars=(result.plan or {}).get("expiry_bars"), in_sample=True)
```

(`simulate_blocked` is looked up on the module at call time, so the test's monkeypatch reaches it.)

- [ ] **Step 6: Run the engine tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_strategy_engine_gate_rows.py tests/backtesting/arms/test_strategy_engine.py tests/backtesting/test_measure_compression_short.py tests/backtesting/test_compression_reachability.py`
Expected: PASS. If only `test_record_blocked_compression_walks_both_arms_through_one_instrument`'s last assertion fails, the rebuilt plan differs from the engine's (for example `simulate_blocked`'s rebuild omits the engine's `level_map` or `scan_params`): stop and report the two plans' differing fields to the controller; do not change V147-3 or loosen the assertion inside this task.

- [ ] **Step 7: The CLI entry**

In `scripts/backtest/measure_arms.py`, after `main` (which stays byte-identical: it is C 14):

```python
def record_blocked_main(argv) -> int:
    """v147: TRAIN compression gate rows (blocked + taken) through StrategyEngine, one JSONL file.

    TRAIN window only (2020-01-01..2023-12-31); bars come from the backtest cache via `load_frame`.
    Flushed per-ticker progress; refusals exit 2 before any data is read."""
    from swingbot.core.backtesting.arms import compression_research as cr
    from swingbot.core.backtesting.blocked_recorder import TRAIN_WINDOW, require_train_window, write_gate_rows
    parser = argparse.ArgumentParser(description="v147: TRAIN compression gate rows through StrategyEngine")
    parser.add_argument("--record-blocked", dest="record_blocked", required=True, type=Path)
    parser.add_argument("--from", dest="date_from", default=TRAIN_WINDOW[0])
    parser.add_argument("--to", dest="date_to", default=TRAIN_WINDOW[1])
    parser.add_argument("--validation", action="store_true", help="refused: --record-blocked is TRAIN-only")
    args = parser.parse_args(argv)
    require_train_window(args.date_from, args.date_to, validation=args.validation)
    context = cr.offline_context()
    universe = cached_universe()
    rows: list = []
    for done, ticker in enumerate(universe, 1):
        frame = load_frame(ticker)
        if frame is not None:
            rows.extend(cr.record_blocked_compression({ticker: frame}, (args.date_from, args.date_to),
                                                      context=context))
        print(f"  [record-blocked] {done}/{len(universe)} ({done * 100 // len(universe)}%) {ticker}: "
              f"{len(rows)} rows", flush=True)
    args.record_blocked.parent.mkdir(parents=True, exist_ok=True)
    count = write_gate_rows(rows, args.record_blocked)
    print(f"Wrote {count} compression gate rows to {args.record_blocked}", flush=True)
    return 0


def cli(argv=None) -> int:
    """Script entry: `--record-blocked` dispatches before `main` parses its required arm flags."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg.split("=", 1)[0] == "--record-blocked" for arg in argv):
        return record_blocked_main(argv)
    return main(argv)
```

and the `__main__` block:

```python
if __name__ == "__main__":
    sys.exit(cli())
```

Add one line to the module docstring: ``` v147: `--record-blocked PATH [--from --to]` writes TRAIN compression gate rows instead (see `record_blocked_main`). ```

- [ ] **Step 8: Run the CLI tests and the existing measure_arms tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_arms_record_blocked.py tests/scripts/test_measure_arms.py tests/scripts/test_measure_bearish_arms.py`
Expected: PASS.

- [ ] **Step 9: Complexity gate**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/arms/compression_research.py scripts/backtest/measure_arms.py`
Expected: `StrategyEngine.iter_trades - C (14)` and `main - C (14)` only (both unchanged); no new function at C.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/arms/compression_research.py scripts/backtest/measure_arms.py tests/backtesting/arms/test_strategy_engine_gate_rows.py tests/scripts/test_measure_arms_record_blocked.py
git commit -m "feat(v147): StrategyEngine compression gate rows + measure_arms --record-blocked (V147-6)"
```

### Task V147-7: `gate_rejections` table, Alembic `v147_001`, repository

**Model:** opus — a new Postgres table whose migration must match `schema.py` exactly, a conflict-ignoring insert the base repository lacks, and a resolve-once update guarded in SQL.

**Cross-plan (audit 2026-10-10):** other plans add tables at the same three anchors. If another plan's table already follows `dropped_doc_fields` in `schema.py`, insert `gate_rejections` after the last such table; if `PROMOTION_REASONS` already ends with another plan's entry (after `"dropped_doc_fields"`), append after it; if another plan's `CASES` entry already follows `"market_data_state"` in `tests/db/test_unknown_field_round_trip.py`, insert after it. Never reorder or drop another plan's entries. `down_revision` stays whatever `python -m alembic heads` prints (Global Constraints).

**Files:**
- Modify: `swingbot/core/db/schema.py` (new table after `dropped_doc_fields`, ~line 208; `PROMOTION_REASONS` entry at its end, ~line 290)
- Create: `swingbot/core/db/migrations/versions/v147_001_gate_rejections.py`
- Create: `swingbot/core/db/repositories/gate_rejections.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (imports 7-25, `CASES` 35-60)
- Create: `tests/db/test_gate_rejections_repository.py`

**Interfaces:**
- Consumes: `schema.register`, `standard_columns`, `PROMOTION_REASONS` (exist); `repositories.base.Repository` (`_tx`, `_values`, `_record`, `get`, `count`); `codec.split_doc` (exists); `gate_counterfactual.CF_STATUSES` (V147-2; test-only, the db layer never imports backtesting).
- Produces (ledger): table `gate_rejections` (`id BIGINT PK`, `ticker`, `gate`, `strategy`, `horizon`, `signal_date TEXT`, `cf_status TEXT` — all `NOT NULL` — `created_at TIMESTAMPTZ NOT NULL`, `resolved_at TIMESTAMPTZ NULL`, `doc`, `updated_at`; `UNIQUE(ticker, gate, strategy, horizon, signal_date)` named `gate_rejections_key_uq`; index `gate_rejections_status_idx` on `cf_status`); `GateRejectionRepository(Repository)` with key `"id"` and `insert_ignore(record, *, conn=None) -> bool`, `pending(*, limit: int, conn=None) -> list[dict]`, `resolve(row_id, *, cf_status, resolved_at, outcome: dict, conn=None) -> bool`, `list_since(since: str | None = None, *, conn=None) -> list[dict]`; `gate_rejections_repo()` lazy singleton; module constants `CF_STATUSES`, `KEY_CONSTRAINT`.
- Record shape: the index's "`gate_rejections` record" — promoted `ticker, gate, strategy, horizon, signal_date, cf_status, created_at, resolved_at`, everything else in `doc`. `pending()` and `list_since()` records also carry `"id"` (the resolver's handle for `resolve`); never write a record carrying `id` back through `insert_ignore` (`split_doc` rejects the reserved key).
- `resolve` with `cf_status="pending"`, `resolved_at=None`, `outcome={"pending_checks": n}` is the resolver's grace-counter bump (V147-11): the row stays pending.
- **Not** added to `events.TABLE_CHANNELS`: no admin surface reads the table and it raises no SSE event (index Global Constraints).

- [ ] **Step 1: Read the Alembic head**

Run: `python -m alembic heads`
Expected: one line, e.g. `v144_001 (head)` (or `v146_001 (head)` if v146 merged first). Call the printed id HEAD; it is this revision's `down_revision`. Two heads printed means another plan's revision is mid-merge: stop and ask the controller.

- [ ] **Step 2: Write the failing repository tests**

Create `tests/db/test_gate_rejections_repository.py`:

```python
"""v147: the append-only live gate-counterfactual store."""
import datetime as dt

import pytest

from swingbot.core.db import events
from swingbot.core.db.repositories import gate_rejections as store
from swingbot.core.db.repositories.gate_rejections import GateRejectionRepository

CREATED = "2026-10-05T20:00:00+00:00"


def _record(**over):
    base = {"ticker": "AAPL", "gate": "rs", "strategy": "RSI", "horizon": "2w",
            "signal_date": "2026-10-05", "cf_status": "pending", "created_at": CREATED,
            "reason": "rs_blocked", "margin": -3.5, "direction": "bearish", "source": "strategy",
            "plan": None, "scenario": None, "scan_params": {"stop_mult": 1.5}, "signal_close": 101.25,
            "entry_context": {}, "heat_before": None, "heat_cap": None}
    return {**base, **over}


@pytest.fixture
def repo():
    return GateRejectionRepository()


def test_a_second_insert_of_the_same_key_is_a_no_op(repo, db_conn):
    assert repo.insert_ignore(_record(), conn=db_conn) is True
    assert repo.insert_ignore(_record(margin=-1.0), conn=db_conn) is False
    (row,) = repo.list_since(conn=db_conn)
    assert row["margin"] == -3.5                                   # the first write wins


def test_one_ticker_gate_strategy_and_day_on_two_horizons_is_two_rows(repo, db_conn):
    assert repo.insert_ignore(_record(horizon="2w"), conn=db_conn)
    assert repo.insert_ignore(_record(horizon="4w"), conn=db_conn)
    assert repo.count(conn=db_conn) == 2


def test_doc_fields_round_trip_and_null_heat_keys_stay_present(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.list_since(conn=db_conn)
    assert isinstance(row["id"], int)
    assert row["scan_params"] == {"stop_mult": 1.5} and row["signal_close"] == 101.25
    assert "heat_before" in row and row["heat_before"] is None
    assert "heat_cap" in row and row["heat_cap"] is None


def test_pending_is_oldest_first_limited_and_carries_ids(repo, db_conn):
    for day, ticker in ((7, "C"), (5, "A"), (6, "B")):
        repo.insert_ignore(_record(ticker=ticker, signal_date=f"2026-10-0{day}",
                                   created_at=f"2026-10-0{day}T20:00:00+00:00"), conn=db_conn)
    repo.insert_ignore(_record(ticker="D", cf_status="no-plan"), conn=db_conn)
    rows = repo.pending(limit=2, conn=db_conn)
    assert [row["ticker"] for row in rows] == ["A", "B"]
    assert all(isinstance(row["id"], int) for row in rows)


def test_resolve_fills_the_outcome_once(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.pending(limit=10, conn=db_conn)
    outcome = {"cf_r": 1.25, "win": True, "exit_index": 9, "last_bar_date": "2026-10-20",
               "bars_sha256": "ab" * 32, "reanchored": False}
    resolved_at = dt.datetime(2026, 10, 21, 20, 45, tzinfo=dt.timezone.utc)
    assert repo.resolve(row["id"], cf_status="filled", resolved_at=resolved_at, outcome=outcome, conn=db_conn)
    assert repo.resolve(row["id"], cf_status="no-data", resolved_at=resolved_at,
                        outcome={"cf_r": None}, conn=db_conn) is False          # never re-resolved
    stored = repo.get(row["id"], conn=db_conn)
    assert stored["cf_status"] == "filled" and stored["resolved_at"] == resolved_at
    assert {key: stored[key] for key in outcome} == outcome
    assert stored["reason"] == "rs_blocked"                                      # the snapshot survives
    assert repo.pending(limit=10, conn=db_conn) == []


def test_a_grace_bump_keeps_the_row_pending(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.pending(limit=10, conn=db_conn)
    assert repo.resolve(row["id"], cf_status="pending", resolved_at=None,
                        outcome={"pending_checks": 1}, conn=db_conn)
    (still,) = repo.pending(limit=10, conn=db_conn)
    assert still["pending_checks"] == 1 and "resolved_at" not in still


def test_resolve_refuses_promoted_keys_and_unknown_statuses(repo, db_conn):
    repo.insert_ignore(_record(), conn=db_conn)
    (row,) = repo.pending(limit=10, conn=db_conn)
    with pytest.raises(ValueError):
        repo.resolve(row["id"], cf_status="filled", resolved_at=CREATED, outcome={"ticker": "X"}, conn=db_conn)
    with pytest.raises(ValueError):
        repo.resolve(row["id"], cf_status="won", resolved_at=CREATED, outcome={}, conn=db_conn)
    with pytest.raises(ValueError):
        repo.insert_ignore(_record(cf_status="done"), conn=db_conn)


def test_list_since_filters_on_created_at(repo, db_conn):
    repo.insert_ignore(_record(ticker="OLD", created_at="2026-09-30T20:00:00+00:00"), conn=db_conn)
    repo.insert_ignore(_record(ticker="NEW", created_at="2026-10-01T20:00:00+00:00"), conn=db_conn)
    assert [row["ticker"] for row in repo.list_since("2026-10-01", conn=db_conn)] == ["NEW"]
    assert [row["ticker"] for row in repo.list_since(conn=db_conn)] == ["OLD", "NEW"]


def test_statuses_mirror_the_simulator_and_the_table_raises_no_event():
    from swingbot.core.backtesting.gate_counterfactual import CF_STATUSES
    assert store.CF_STATUSES == CF_STATUSES
    assert "gate_rejections" not in events.TABLE_CHANNELS


def test_the_singleton_is_lazy_and_shared():
    assert store.gate_rejections_repo() is store.gate_rejections_repo()
```

- [ ] **Step 3: Add the round-trip case**

In `tests/db/test_unknown_field_round_trip.py`, import (alphabetical, after `flags`):

```python
from swingbot.core.db.repositories.gate_rejections import GateRejectionRepository
```

and add to `CASES` after `"market_data_state"`:

```python
    "gate_rejections": (GateRejectionRepository, {"ticker": "AAPL", "gate": "rs", "strategy": "RSI",
                                                  "horizon": "2w", "signal_date": "2026-10-01",
                                                  "cf_status": "pending", "created_at": TS}),
```

(`_write` already inserts for a surrogate-keyed repository: `repo.key == "id"`.)

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_gate_rejections_repository.py tests/db/test_unknown_field_round_trip.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.gate_rejections'`.

- [ ] **Step 5: Declare the table**

In `swingbot/core/db/schema.py`, after the `dropped_doc_fields` table:

```python
# v147: one row per candidate a live gate (RS, plan rejection, compression) threw away, resolved once
# by the nightly counterfactual resolver. Append-only: only cf_status/resolved_at and the outcome doc
# fields are ever updated, by that resolver; rows are never deleted. No SSE event (not in TABLE_CHANNELS).
gate_rejections = register(sa.Table("gate_rejections", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("ticker", sa.Text, nullable=False),
    sa.Column("gate", sa.Text, nullable=False),
    sa.Column("strategy", sa.Text, nullable=False),
    sa.Column("horizon", sa.Text, nullable=False),
    sa.Column("signal_date", sa.Text, nullable=False),
    sa.Column("cf_status", sa.Text, nullable=False),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.UniqueConstraint("ticker", "gate", "strategy", "horizon", "signal_date",
                        name="gate_rejections_key_uq"),
    sa.Index("gate_rejections_status_idx", "cf_status")),
    ("ticker", "gate", "strategy", "horizon", "signal_date", "cf_status", "created_at", "resolved_at"))
```

and at the end of `PROMOTION_REASONS` (after `"dropped_doc_fields"`):

```python
    "gate_rejections": {
        "ticker": "gate_rejections_key_uq; the ON CONFLICT DO NOTHING dedupe key",
        "gate": "gate_rejections_key_uq; the report's per-gate cells",
        "strategy": "gate_rejections_key_uq; scopes the taken arm per strategy",
        "horizon": "gate_rejections_key_uq; one setup on two horizons is two rows",
        "signal_date": "gate_rejections_key_uq; the exact-date signal bar the resolver walks from",
        "cf_status": "gate_rejections_status_idx; the resolver's WHERE cf_status = 'pending'",
        "created_at": "NOT NULL write time; resolver due order and the report's live window",
        "resolved_at": "when the outcome was filled once; NULL while pending",
    },
```

- [ ] **Step 6: Write the revision**

Create `swingbot/core/db/migrations/versions/v147_001_gate_rejections.py`, putting Step 1's HEAD id into both the docstring's `Revises:` line and `down_revision` (shown here with `v144_001`, the head on 2026-10-10; use what Step 1 printed):

```python
"""gate_rejections: the v147 live gate-counterfactual store

One row per candidate the RS, plan-rejection or compression gate threw away on
the live scan; the nightly resolver fills its outcome once. A new table, so the
downgrade drops it whole (no doc field to preserve elsewhere).

Revision ID: v147_001
Revises: v144_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v147_001"
down_revision = "v144_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gate_rejections",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("gate", sa.Text, nullable=False),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("signal_date", sa.Text, nullable=False),
        sa.Column("cf_status", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("ticker", "gate", "strategy", "horizon", "signal_date",
                            name="gate_rejections_key_uq"),
    )
    op.create_index("gate_rejections_status_idx", "gate_rejections", ["cf_status"])


def downgrade() -> None:
    op.drop_index("gate_rejections_status_idx", table_name="gate_rejections")
    op.drop_table("gate_rejections")
```

- [ ] **Step 7: Write the repository**

Create `swingbot/core/db/repositories/gate_rejections.py`:

```python
"""v147: the append-only live gate-counterfactual store (`gate_rejections`).

Writer: `scanning.rejection_recorder.record_rejection` (`insert_ignore`; fail-open there).
Resolver: `backtesting.gate_resolver.resolve_due` (`pending` -> `resolve`, once).
Report and progress cron: `list_since`. The table raises no SSE event.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert

from swingbot.core.db.codec import split_doc
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import gate_rejections

#: gate_counterfactual.CF_STATUSES, restated so the db layer never imports backtesting (pinned by a test).
CF_STATUSES = ("pending", "filled", "no-fill", "no-plan", "no-data")
KEY_CONSTRAINT = "gate_rejections_key_uq"


def _check_status(status) -> None:
    if status not in CF_STATUSES:
        raise ValueError(f"cf_status {status!r} is not one of {CF_STATUSES}")


def _as_utc(value) -> dt.datetime | None:
    """A timestamptz bound from a datetime or ISO string; a naive value is taken as UTC."""
    if value is None:
        return None
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=dt.timezone.utc)


class GateRejectionRepository(Repository):
    def __init__(self):
        super().__init__(gate_rejections, key="id")

    def _with_id(self, row) -> dict:
        return {**self._record(row), "id": row.id}

    def insert_ignore(self, record: dict, *, conn=None) -> bool:
        """Insert one rejection; False, and nothing written, when its dedupe key already exists."""
        _check_status(record.get("cf_status"))
        statement = (pg_insert(self.table).values(**self._values(record))
                     .on_conflict_do_nothing(constraint=KEY_CONSTRAINT)
                     .returning(self.table.c.id))
        with self._tx(conn) as connection:
            return connection.execute(statement).first() is not None

    def pending(self, *, limit: int, conn=None) -> list[dict]:
        """Up to `limit` pending rows, oldest first, each with its `id`."""
        statement = (sa.select(self.table).where(self.table.c.cf_status == "pending")
                     .order_by(self.table.c.created_at, self.table.c.id).limit(limit))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._with_id(row) for row in rows]

    def resolve(self, row_id: int, *, cf_status: str, resolved_at, outcome: dict, conn=None) -> bool:
        """Write one pending row's status and merge `outcome` into its doc -- only while it is pending,
        so a resolved row is never resolved again (False). `cf_status="pending"` with
        `resolved_at=None` is the grace-counter bump. `outcome` may not name a promoted column."""
        _check_status(cf_status)
        columns, document = split_doc(outcome, self.promoted)
        if columns:
            raise ValueError(f"outcome may not set promoted columns: {sorted(columns)}")
        values = {"cf_status": cf_status, "resolved_at": _as_utc(resolved_at),
                  "updated_at": sa.func.clock_timestamp()}
        if document:
            values["doc"] = self.table.c.doc.op("||")(sa.cast(sa.literal(document, type_=sa.JSON), JSONB))
        statement = (sa.update(self.table)
                     .where(self.table.c.id == row_id, self.table.c.cf_status == "pending")
                     .values(**values))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0

    def list_since(self, since: str | None = None, *, conn=None) -> list[dict]:
        """Every row created at or after `since` (ISO date or timestamp; None = all), oldest first."""
        statement = sa.select(self.table).order_by(self.table.c.created_at, self.table.c.id)
        if since is not None:
            statement = statement.where(self.table.c.created_at >= _as_utc(since))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._with_id(row) for row in rows]


_repo: GateRejectionRepository | None = None


def gate_rejections_repo() -> GateRejectionRepository:
    global _repo
    if _repo is None:
        _repo = GateRejectionRepository()
    return _repo
```

- [ ] **Step 8: Run the store tests and every schema/migration contract**

Run: `python scripts/dev/testrun.py file tests/db/test_gate_rejections_repository.py tests/db/test_unknown_field_round_trip.py tests/db/test_schema_contract.py tests/db/test_migrations.py tests/db/test_trigger_coverage.py`
Expected: PASS — including `test_exactly_one_head`, `test_migrations_produce_exactly_the_declared_schema` (schema.py and the revision agree on columns, constraint and index names) and `test_every_promoted_column_has_exactly_one_one_line_reason`.

- [ ] **Step 9: Migration round trip**

Run: `python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head` against the disposable test database only (`TEST_DATABASE_URL`, default `127.0.0.1:55432`, the URL `tests/db/conftest.py` uses — never production).
Expected: three clean runs; `python -m alembic heads` prints `v147_001 (head)`. If the local alembic env cannot target the test database, `test_migrations_produce_exactly_the_declared_schema` (Step 8) already ran the upgrade; record that in the commit message instead.

- [ ] **Step 10: Complexity gate**

Run: `python -m radon cc -s -n C swingbot/core/db/repositories/gate_rejections.py`
Expected: no output.

- [ ] **Step 11: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v147_001_gate_rejections.py swingbot/core/db/repositories/gate_rejections.py tests/db/test_unknown_field_round_trip.py tests/db/test_gate_rejections_repository.py
git commit -m "feat(v147): gate_rejections table, v147_001 revision and repository (V147-7)"
```

