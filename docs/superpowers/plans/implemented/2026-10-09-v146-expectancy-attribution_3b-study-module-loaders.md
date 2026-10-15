# v146 Expectancy attribution: Implementation Plan, part 3b -- the study module: loaders, report, script

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: pull one task with `/task-brief V146-12` or `grep -n "^### Task V146-12:" -A 750 docs/superpowers/plans/2026-10-09-v146-expectancy-attribution_3b-study-module-loaders.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`](../specs/2026-10-09-v146-expectancy-attribution-design.md)
**Index:** [`2026-10-09-v146-expectancy-attribution_0-index.md`](2026-10-09-v146-expectancy-attribution_0-index.md) -- Global Constraints, Handoff decisions, Parallelisation and the task ledger live there and bind the task below.
**Part 3 header:** [`_3a-study-module`](2026-10-09-v146-expectancy-attribution_3a-study-module.md) -- the worktree rule, the order inside the part and the decisions this part takes (week, win rate, looks, the BH family, bootstrap p, live confluence count, live frictions) are stated there once and bind this file. The letter is a file boundary only.

**Tasks:** V146-12 (after V146-11; it also needs `write_latest` from V146-9).

---

# Phase 3 -- the study module (continued)

### Task V146-12: Population loaders, `build_report`, `run`, the script

**Model:** opus -- it decides what each population's R means (the live-frictions branch of Handoff 5), maps two record shapes onto one row, and assembles the report contract v150 and V146-14 read.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (V146-10, V146-11; this task appends and changes no earlier function)
- Create: `scripts/reports/expectancy_attribution.py`
- Create: `tests/analytics/test_expectancy_attribution_report.py`

**Interfaces:**
- Consumes: V146-10 `ROW_KEYS`, `net_r`, `population_buckets`, `_scored`, `_label`, `_sort_key`; V146-11 `monotonicity`, `factor_deltas`, `bucket_looks`, `assign_qvalues`, `verdict`, `N_RESAMPLES`, and the test builder `tests/analytics/test_expectancy_attribution_stats.py::population`; V146-9 `load_latest`, `write_latest` (`swingbot/core/infra/expectancy_attribution_store.py`); the TRAIN row keys of V146-7 (`ticker, horizon_key, signal_date, direction, entry, stop_loss, take_profit, risk_reward_ratio, outcome, runner_outcome, r_total, entry_price, legs, entry_context, confluence_count, confidence_score, confidence_level, confidence_points, confidence_unevaluated`); the trade record keys of V146-4 (`confidence_points`, `confidence_unevaluated`); existing `metrics.r_multiple(trade)` (`swingbot/core/analytics/metrics.py:173`), `scope.closed_only(trades)` (`swingbot/core/analytics/scope.py:81`), `TradeLog().get_trades(status=None, limit=None, ledger=None)` (`swingbot/core/tracking/performance.py:1109`), `earnings_calendar.sessions_to_reaction(ticker, asof, *, source, calendar=None)`, `earnings_calendar.CsvSource(directory=EARNINGS_CSV_DIR)`, `earnings_calendar.Report(date, timing)` (`swingbot/core/market/earnings_calendar.py`).
- Produces (index ledger):
  - `live_row(trade: dict) -> dict | None`; `load_live_rows() -> list[dict]`
  - `train_earnings(ticker: str, signal_date: dt.date, source, *, margin_days: int = 100) -> tuple[int | None, str]`
  - `load_train_rows(path, *, source=None) -> list[dict]` (`source` defaults to `CsvSource()` on the code-relative `market_data/earnings/`)
  - `earnings_provenance(directory=EARNINGS_CSV_DIR) -> dict`
  - `build_report(live_rows, train_rows, *, seed: int, generated_at: str | None = None) -> dict`
  - `run(train_jsonl, *, seed: int = WEEK_BOOTSTRAP_SEED, write: bool = True) -> dict`
  - the `load_latest` re-export; module constant `LIVE_FILLS_INCLUDE_FRICTIONS: bool` (V146-14 reads it)
  - CLI `python scripts/reports/expectancy_attribution.py --train-jsonl PATH [--seed N] [--no-write]`
- Report shape (index, **Report shape**): `{generated_at, verdict, verdict_of_record: {verdict, date, n}, looks, seed, provenance, populations: {live, train}}`; each population `{window, n, monotonicity, factors, buckets, splits: {direction: {<name>: monotonicity}, horizon: {<name>: monotonicity}}, notes}`; a population with no rows is `null`. `verdict_of_record.n` is live monotonicity `n` plus TRAIN monotonicity `n` (Handoff 9).
- The database is read through `swingbot.config.DATABASE_URL` at call time: `load_live_rows` builds `TradeLog()` inside the function and the engine reads `config.DATABASE_URL` when it connects (`swingbot/core/db/engine.py:35`). Nothing in this module may capture a URL, an engine or a `TradeLog` at import: V146-14 runs the study from a launcher that sets `config.DATABASE_URL` after import.

- [ ] **Step 1: Verify what live fills include, and take the Handoff 5 branch**

The spec: "Both populations' R must be net of frictions ... the plan verifies what live `r_multiple` includes and states it." Handoff 5 fixes the rule: **if live fill prices are not friction-adjusted, the study applies the same `apply_frictions` + `commission_r` model to live rows as to TRAIN rows; if they are, it uses `metrics.r_multiple` as is.** Verify, do not assume:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution grep -n "apply_frictions\|commission_r\|SLIPPAGE_BPS\|COMMISSION_PER_TRADE" -- swingbot bot.py admin_ui.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution grep -n "\"exit_price\": " -- swingbot/core/planning/plan_manager.py swingbot/core/tracking/performance.py
```

Expected (measured on `main`, 2026-10-10): the first command hits only `swingbot/core/edge/frictions.py` (the model), `swingbot/core/backtesting/` (`backtest.py:690-743`, `screen/race.py`), `swingbot/config.py` (the settings) and `swingbot/scan_params.py:141-143` (a settings snapshot). No hit under `swingbot/core/planning/`, `swingbot/core/tracking/` or `swingbot/core/scanning/`. The second command lists the leg bookings (`plan_manager.py:662, 863, 879, 907, 1075`): open each and confirm the `exit_price` it stores is the raw stop / target / trail / market price, and that `metrics.r_multiple` (`metrics.py:173-215`) derives R from those prices with no deduction.

Decision:

| What Step 1 finds | Branch | Constant written in Step 5 |
|---|---|---|
| No friction call on the live fill path (the expected result) | live rows are netted with `net_r`, exactly as TRAIN rows; `r_gross` keeps `metrics.r_multiple` | `LIVE_FILLS_INCLUDE_FRICTIONS = False` |
| A live fill or its R is already worsened by slippage or commission | live `r` is `metrics.r_multiple` as is; `r_gross` equals it | `LIVE_FILLS_INCLUDE_FRICTIONS = True` |

Record the branch in three places: the constant and the comment above it (Step 5; edit the comment to name the evidence if the branch is `True`), the commit message (Step 9), and the hand-back to the controller ("Handoff 5: live fills friction-adjusted = <True|False>, evidence: <files>"). The report carries it as `provenance.live_fills_include_frictions`, and V146-14 states it in the results document. If the evidence is mixed (some fills adjusted, some not), stop and report: that is the partner's call, not a third branch.

- [ ] **Step 2: Write the failing tests**

Create `tests/analytics/test_expectancy_attribution_report.py`:

```python
"""v146: the two population loaders, the report shape, the run and the thin
script. No database and no TRAIN replay: live trades, replay rows and the
earnings calendar are all hand-built."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.infra import expectancy_attribution_store as store
from swingbot.core.market.earnings_calendar import AFTER_CLOSE, Report
from swingbot.core.market.strategy_types import HORIZONS
from tests.analytics.test_expectancy_attribution_stats import population

HK = next(iter(HORIZONS))
REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reports" / "expectancy_attribution.py"


@pytest.fixture(autouse=True)
def cheap_and_costed(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 10.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


class StubSource:
    def __init__(self, dates):
        self._reports = [Report(dt.date.fromisoformat(day), AFTER_CLOSE) for day in dates]

    def reports(self, ticker):
        return list(self._reports)


def _trade(**over):
    trade = {
        "status": "win", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
        "exit_price": 110.0, "legs": [], "opened_at": "2026-03-11T14:30:00+00:00",
        "horizon_key": HK, "confidence_score": 71, "confidence_level": 4,
        "confidence_points": {"MACD momentum": 10},
        "confidence_unevaluated": ["ADX trend strength"],
        "target_sources": ["ema", "vwap", "fib", "pivot", "sma"],
        "risk_features": {"confluence_count": 3, "days_to_earnings": 7,
                          "regime2_state": "bull_quiet"},
        "entry_context": {"regime2_state": "bull_quiet", "rs_pctile": 81.0},
        "risk_reward_ratio": 2.0,
    }
    trade.update(over)
    return trade


def test_live_row_maps_a_closed_trade_onto_the_row_keys():
    row = ea.live_row(_trade())
    assert tuple(row) == ea.ROW_KEYS
    assert row["week"] == "2026-03-09"                      # the Monday of the entry week
    assert row["r_gross"] == pytest.approx(2.0)
    assert row["r"] == pytest.approx((109.89 - 100.1) / (100.1 - 95.0) - 0.02)
    assert row["confluence_count"] == 3                     # not len(target_sources)
    assert (row["earnings_sessions"], row["earnings_status"]) == (7, "known")
    assert (row["rs_pctile"], row["horizon"]) == (81.0, HK)


def test_live_row_before_the_earnings_stamp_reads_unknown():
    row = ea.live_row(_trade(risk_features={}, entry_context={}))
    assert (row["earnings_sessions"], row["earnings_status"]) == (None, "unknown")
    assert row["confluence_count"] is None and row["regime2_state"] is None


def test_live_row_nets_a_scaled_out_trade_leg_by_leg():
    legs = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
            {"fraction": 0.5, "exit_price": 100.0, "r": 0.0}]
    row = ea.live_row(_trade(legs=legs, exit_price=100.0))
    assert row["r_gross"] == pytest.approx(1.0)
    assert row["r"] < row["r_gross"]


def test_live_row_refuses_a_trade_without_r_or_an_entry_week():
    assert ea.live_row(_trade(exit_price=None)) is None
    assert ea.live_row(_trade(opened_at=None)) is None
    assert ea.live_row(_trade(legs=[{"fraction": 1.0, "r": 1.0}])) is None   # no fill to net


def test_live_row_uses_r_multiple_as_is_when_fills_already_carry_frictions(monkeypatch):
    monkeypatch.setattr(ea, "LIVE_FILLS_INCLUDE_FRICTIONS", True)
    row = ea.live_row(_trade())
    assert row["r"] == row["r_gross"] == pytest.approx(2.0)


def test_the_frictions_branch_of_record_is_a_bool():
    assert isinstance(ea.LIVE_FILLS_INCLUDE_FRICTIONS, bool)


def test_load_live_rows_reads_closed_trades_of_every_ledger(monkeypatch):
    seen = {}

    class FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return [_trade(), _trade(status="open", exit_price=None),
                    _trade(status="loss", exit_price=95.0), _trade(status="closed", exit_price=None)]

    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog", FakeLog)
    rows = ea.load_live_rows()
    assert seen == {"status": None, "limit": None, "ledger": None}
    assert len(rows) == 2 and rows[1]["r"] < -1.0


def test_train_earnings_statuses():
    source = StubSource(["2024-02-01", "2024-05-02"])
    sessions, status = ea.train_earnings("AAA", dt.date(2024, 4, 25), source)
    assert status == "known" and 0 < sessions <= 10
    assert ea.train_earnings("AAA", dt.date(2024, 6, 3), source) == (None, "none")
    assert ea.train_earnings("AAA", dt.date(2024, 8, 11), source) == (None, "unknown")
    assert ea.train_earnings("AAA", dt.date(2024, 6, 3), source, margin_days=10) == (None, "unknown")
    assert ea.train_earnings("AAA", dt.date(2024, 4, 25), StubSource([])) == (None, "unknown")


def _replay_row(**over):
    row = {
        "ticker": "AAA", "horizon_key": HK, "signal_date": "2024-04-25",
        "direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "risk_reward_ratio": 2.0, "outcome": "win", "runner_outcome": None,
        "r_total": 2.0, "entry_price": 100.0,
        "legs": [{"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}],
        "entry_context": {"regime2_state": "bull_quiet", "rs_pctile": 55.0},
        "confluence_count": 4, "confidence_score": 66, "confidence_level": 3,
        "confidence_points": {"MACD momentum": 15}, "confidence_unevaluated": [],
    }
    row.update(over)
    return row


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows) + "\n", encoding="utf-8")
    return path


def test_load_train_rows_nets_the_replay_rows_and_stamps_earnings(tmp_path):
    path = _write_jsonl(tmp_path / "train.jsonl", [
        _replay_row(),
        _replay_row(outcome="not_triggered", legs=[], r_total=0.0, entry_price=None),
        _replay_row(ticker="BBB", signal_date="2024-06-03", entry_price=None)])
    rows = ea.load_train_rows(path, source=StubSource(["2024-02-01", "2024-05-02"]))
    assert len(rows) == 2                                   # the untriggered row is not a trade
    first, second = rows
    assert tuple(first) == ea.ROW_KEYS
    assert first["week"] == "2024-04-22" and first["r_gross"] == 2.0
    assert first["r"] == pytest.approx((109.89 - 100.1) / (100.1 - 95.0) - 0.02)
    assert (first["confluence_count"], first["horizon"], first["rs_pctile"]) == (4, HK, 55.0)
    assert first["earnings_status"] == "known"
    assert second["earnings_status"] == "none"              # falls back to the planned entry


def test_load_train_rows_defaults_to_the_csv_source(tmp_path, monkeypatch):
    made = []

    class FakeCsv(StubSource):
        def __init__(self):
            super().__init__([])
            made.append(self)

    monkeypatch.setattr(ea.earnings_calendar, "CsvSource", FakeCsv)
    rows = ea.load_train_rows(_write_jsonl(tmp_path / "train.jsonl", [_replay_row()]))
    assert len(made) == 1 and rows[0]["earnings_status"] == "unknown"


def test_earnings_provenance_names_the_file_set(tmp_path):
    header = "report_date,timing,report_ts_et\n"
    (tmp_path / "AAA.csv").write_text(header + "2024-02-01,after_close,\n", encoding="utf-8")
    (tmp_path / "BBB.csv").write_text(header + "2025-07-30,before_open,\n", encoding="utf-8")
    first = ea.earnings_provenance(tmp_path)
    assert first["files"] == 2 and first["newest_report_date"] == "2025-07-30"
    assert len(first["sha256"]) == 64 and "sessions_to_reaction" in first["calendar"]
    (tmp_path / "BBB.csv").write_text(header + "2025-10-29,before_open,\n", encoding="utf-8")
    assert ea.earnings_provenance(tmp_path)["sha256"] != first["sha256"]
    missing = ea.earnings_provenance(tmp_path / "absent")
    assert (missing["files"], missing["sha256"], missing["newest_report_date"]) == (0, None, None)


def test_build_report_has_the_contract_shape_and_a_predictive_verdict():
    live, train = population("predictive"), population("predictive", n=240)
    report = ea.build_report(live, train, seed=42, generated_at="2026-10-12T08:00:00+00:00")
    assert list(report) == ["generated_at", "verdict", "verdict_of_record", "looks",
                            "seed", "provenance", "populations"]
    assert report["verdict"] == "PREDICTIVE" and report["seed"] == 42
    assert report["verdict_of_record"] == {"verdict": "PREDICTIVE", "date": "2026-10-12",
                                           "n": 180 + 240}
    assert report["looks"] > 10
    for name in ("live", "train"):
        pop = report["populations"][name]
        assert list(pop) == ["window", "n", "monotonicity", "factors", "buckets",
                             "splits", "notes"]
        assert set(pop["splits"]) == {"direction", "horizon"}
        assert set(pop["splits"]["direction"]) == {"bullish", "bearish"}
        assert pop["window"]["first_week"] == "2024-01-01" and pop["notes"]
        assert all(bucket["thin"] is (bucket["n"] < 30)
                   for grouping in pop["buckets"].values() for bucket in grouping)
        assert any(bucket["q"] is not None for bucket in pop["buckets"]["direction"])
    assert report["populations"]["live"]["n"] == 180       # never pooled with TRAIN's 240
    json.dumps(report)                                      # JSON-serialisable as is


def test_build_report_verdicts_follow_the_populations():
    good, flat = population("predictive"), population("flat")
    assert ea.build_report(flat, good, seed=42)["verdict"] == "WEAK"
    assert ea.build_report(flat, population("inverted"), seed=42)["verdict"] == "NOT PREDICTIVE"
    empty_live = ea.build_report([], good, seed=42)
    assert empty_live["populations"]["live"] is None and empty_live["verdict"] == "WEAK"
    assert empty_live["verdict_of_record"]["n"] == 180


def test_run_writes_the_latest_report_and_load_latest_round_trips(tmp_path, monkeypatch):
    train = _write_jsonl(tmp_path / "train.jsonl", [_replay_row()])
    monkeypatch.setattr(store, "REPORT_PATH", tmp_path / "reports" / "expectancy-attribution.json")
    monkeypatch.setattr(ea, "load_live_rows", lambda: population("flat"))
    monkeypatch.setattr(ea, "load_train_rows", lambda path: population("predictive"))
    monkeypatch.setattr(ea, "earnings_provenance", lambda: {"files": 0})
    written = ea.run(train, seed=7)
    assert written["verdict"] == "WEAK" and written["seed"] == 7
    assert written["provenance"]["train_rows"]["rows"] == 180
    assert len(written["provenance"]["train_rows"]["sha256"]) == 64
    assert written["provenance"]["live_fills_include_frictions"] is ea.LIVE_FILLS_INCLUDE_FRICTIONS
    assert ea.load_latest is store.load_latest
    assert ea.load_latest() == written

    monkeypatch.setattr(ea, "load_live_rows", lambda: population("predictive"))
    dry = ea.run(train, write=False)
    assert dry["verdict"] == "PREDICTIVE" and dry["seed"] == ea.WEEK_BOOTSTRAP_SEED
    assert ea.load_latest()["verdict"] == "WEAK"            # --no-write left the file alone
    later = ea.run(train)
    assert later["verdict"] == "PREDICTIVE"
    assert later["verdict_of_record"]["verdict"] == "WEAK"  # the verdict of record never moves


def _script():
    spec = importlib.util.spec_from_file_location("v146_expectancy_attribution_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_parses_calls_and_prints(monkeypatch, capsys):
    calls = []
    report = ea.build_report([], population("predictive"), seed=42,
                             generated_at="2026-10-12T08:00:00+00:00")

    def fake_run(train_jsonl, *, seed, write):
        calls.append((train_jsonl, seed, write))
        return report

    monkeypatch.setattr(ea, "run", fake_run)
    script = _script()
    assert script.main(["--train-jsonl", "rows.jsonl", "--no-write"]) == 0
    assert script.main(["--train-jsonl", "rows.jsonl", "--seed", "9"]) == 0
    assert calls == [("rows.jsonl", ea.WEEK_BOOTSTRAP_SEED, False), ("rows.jsonl", 9, True)]
    out = capsys.readouterr().out
    assert "Expectancy attribution" in out and "verdict of record: WEAK" in out
    assert "live  no rows" in out and "train n=180" in out
```

`test_live_row_maps_a_closed_trade_onto_the_row_keys`, `test_live_row_nets_a_scaled_out_trade_leg_by_leg` and the `rows[1]["r"] < -1.0` line of `test_load_live_rows_reads_closed_trades_of_every_ledger` assume the `False` branch. If Step 1 took the `True` branch, wrap those three in `monkeypatch.setattr(ea, "LIVE_FILLS_INCLUDE_FRICTIONS", False)` so they keep testing the netting path, and leave every other test as written.

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_report.py`
Expected: FAIL -- `AttributeError` on `live_row`, `train_earnings`, `load_train_rows`, `earnings_provenance`, `build_report`, `run`, and `FileNotFoundError` for the script.

- [ ] **Step 4: Extend the import block**

In `swingbot/core/analytics/expectancy_attribution.py`, replace the import block with:

```python
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

from swingbot import config
from swingbot.core.analytics import metrics
from swingbot.core.analytics.aggregate import rs_quintile_label
from swingbot.core.analytics.scope import closed_only
from swingbot.core.backtesting.instrument import stats
from swingbot.core.edge.frictions import apply_frictions, commission_r
from swingbot.core.infra.expectancy_attribution_store import load_latest, write_latest  # noqa: F401  (load_latest is re-exported for v150)
from swingbot.core.market import earnings_calendar
from swingbot.core.market.earnings_calendar import EARNINGS_CSV_DIR
from swingbot.core.market.strategy_types import HORIZONS
```

`TradeLog` is deliberately not imported here: `swingbot.core.tracking.performance` already imports `swingbot.core.analytics.metrics`, and `load_live_rows` imports it inside the function.

- [ ] **Step 5: Append the loaders, the report and the run**

Append to the end of `swingbot/core/analytics/expectancy_attribution.py` (set `LIVE_FILLS_INCLUDE_FRICTIONS` to the branch Step 1 took):

```python
# --------------------------------------------------------------------------
# Populations, the report and the run. Only ``load_live_rows`` touches the
# database and only ``run`` writes (through ``write_latest``).
# --------------------------------------------------------------------------

log = logging.getLogger(__name__)

#: Handoff 5, verified in V146-12 Step 1: live fills are booked at the exact
#: trigger / stop / target price (no slippage, no commission), so the study
#: nets live rows with the same model as TRAIN rows. True would mean "use
#: metrics.r_multiple as it is".
LIVE_FILLS_INCLUDE_FRICTIONS = False
WEEK_BOOTSTRAP_SEED = stats.WEEK_BOOTSTRAP_SEED
#: Spec: a TRAIN signal later than the last CSV report plus this margin has
#: unknown earnings (the CSV has gone stale), in calendar days.
TRAIN_EARNINGS_MARGIN_DAYS = 100

_NOTES = {
    "live": (
        "Closed trades from the trades table, both ledgers. Confidence analyses "
        "use rows with a non-null confidence_score.",
        "Range-restricted: only trades at or above MIN_ALERT_CONFIDENCE_LEVEL were "
        "ever paper-traded, which attenuates any score-R slope; a weaker live slope "
        "is the expected shape, not by itself a contradiction.",
        "confidence_score is level-major (the quality score is repositioned inside "
        "the final level's band), so deciles read close to level, then quality.",
        "Earnings: risk_features.days_to_earnings, a provider point-in-time estimate "
        "in NYSE sessions; unknown for every trade opened before v146 I2 shipped.",
    ),
    "train": (
        "TRAIN confluence replay (--scenarios --train --exit-model v2 --scale-out), "
        "not level-gated; VALIDATION is never read.",
        "The TRAIN score is computed with the expectancy level adjustment "
        "neutralised; the R:R distribution per tercile shows any residual effect.",
        "R net: the replay's exit_sim applies no frictions, so slippage and "
        "commission are re-applied here; exp_r_gross is the replay's own r_total.",
        "Earnings: actual report dates (CsvSource). Buckets >20 and none are "
        "ex-post, 11-20 partly; report timing is ex-post and can move a row across "
        "the 0-5 edge. Never merged with the live estimate.",
        "Backtest and live differ in their gap-fill model (exit_sim.py:541-548).",
    ),
}


def _progress(message: str) -> None:
    print(f"[expectancy-attribution] {message}", file=sys.stderr, flush=True)


def _week_of(value) -> str | None:
    """The Monday (ISO date) of the week holding an ISO date or timestamp."""
    try:
        day = dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def _live_net(trade: dict, gross: float) -> float | None:
    if LIVE_FILLS_INCLUDE_FRICTIONS:
        return gross
    legs = trade.get("legs") or [{"fraction": 1.0, "exit_price": trade.get("exit_price")}]
    if any(leg.get("exit_price") is None for leg in legs):
        return None
    try:
        return net_r(trade["entry"], trade["stop_loss"], trade["direction"], legs)
    except ValueError:
        return None


def live_row(trade: dict) -> dict | None:
    """One closed live trade as an attribution row, or None when it has no
    R (``metrics.r_multiple`` is None), no entry week, or a leg with no fill
    price to net."""
    gross = metrics.r_multiple(trade)
    week = _week_of(trade.get("opened_at"))
    if gross is None or week is None:
        return None
    net = _live_net(trade, gross)
    if net is None:
        return None
    features = trade.get("risk_features") or {}
    context = trade.get("entry_context") or {}
    sessions = features.get("days_to_earnings")
    known = isinstance(sessions, int) and not isinstance(sessions, bool)
    return {
        "r": net, "r_gross": gross, "week": week,
        "confidence_score": trade.get("confidence_score"),
        "confidence_level": trade.get("confidence_level"),
        "confidence_points": trade.get("confidence_points"),
        "confidence_unevaluated": trade.get("confidence_unevaluated") or [],
        # The count_confirming_strategies count, the definition TRAIN records;
        # never len(target_sources).
        "confluence_count": features.get("confluence_count"),
        "regime2_state": context.get("regime2_state") or features.get("regime2_state"),
        "rs_pctile": context.get("rs_pctile"),
        "direction": trade.get("direction"),
        "horizon": trade.get("horizon_key"),
        "earnings_sessions": sessions if known else None,
        "earnings_status": "known" if known else "unknown",
        "risk_reward_ratio": trade.get("risk_reward_ratio"),
    }


def load_live_rows() -> list[dict]:
    """Every closed trade of both ledgers, as attribution rows. The database
    is whatever ``swingbot.config.DATABASE_URL`` names when this is CALLED:
    nothing is captured at import."""
    from swingbot.core.tracking.performance import TradeLog
    closed = closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None) or [])
    rows = [row for row in map(live_row, closed) if row is not None]
    if len(rows) != len(closed):
        log.warning("expectancy attribution: %d of %d closed live trades have no "
                    "usable R and are left out", len(closed) - len(rows), len(closed))
    return rows


def train_earnings(ticker: str, signal_date: dt.date, source, *,
                   margin_days: int = 100) -> tuple[int | None, str]:
    """(sessions to the next earnings reaction, status) as of a TRAIN signal.

    "unknown": no earnings CSV rows for the ticker, or the signal is later
    than the last CSV report plus ``margin_days``. "none": coverage reaches
    the signal and holds no report at or after it. Otherwise "known"."""
    reports = source.reports(ticker)
    if not reports:
        return None, "unknown"
    last = max(report.date for report in reports)
    if signal_date > last + dt.timedelta(days=margin_days):
        return None, "unknown"
    sessions = earnings_calendar.sessions_to_reaction(ticker, signal_date, source=source)
    return (None, "none") if sessions is None else (int(sessions), "known")


def _train_row(raw: dict, source) -> dict | None:
    legs = raw.get("legs") or []
    week = _week_of(raw.get("signal_date"))
    entry = raw.get("entry_price") if raw.get("entry_price") is not None else raw.get("entry")
    if not legs or week is None or entry is None or raw.get("r_total") is None:
        return None
    try:
        net = net_r(entry, raw["stop_loss"], raw["direction"], legs)
    except (KeyError, TypeError, ValueError):
        return None
    context = raw.get("entry_context") or {}
    sessions, status = train_earnings(
        raw["ticker"], dt.date.fromisoformat(str(raw["signal_date"])[:10]), source,
        margin_days=TRAIN_EARNINGS_MARGIN_DAYS)
    return {
        "r": net, "r_gross": float(raw["r_total"]), "week": week,
        "confidence_score": raw.get("confidence_score"),
        "confidence_level": raw.get("confidence_level"),
        "confidence_points": raw.get("confidence_points"),
        "confidence_unevaluated": raw.get("confidence_unevaluated") or [],
        "confluence_count": raw.get("confluence_count"),
        "regime2_state": context.get("regime2_state"),
        "rs_pctile": context.get("rs_pctile"),
        "direction": raw.get("direction"),
        "horizon": raw.get("horizon_key"),
        "earnings_sessions": sessions, "earnings_status": status,
        "risk_reward_ratio": raw.get("risk_reward_ratio"),
    }


def load_train_rows(path, *, source=None) -> list[dict]:
    """The TRAIN replay's ``--trades-jsonl`` rows as attribution rows.
    ``source`` defaults to ``CsvSource()`` on the code-relative
    ``market_data/earnings/`` directory (actual report dates)."""
    source = source if source is not None else earnings_calendar.CsvSource()
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = _train_row(json.loads(line), source)
                if row is not None:
                    rows.append(row)
    return rows


def earnings_provenance(directory=EARNINGS_CSV_DIR) -> dict:
    """What the TRAIN earnings buckets were read from: the file set's count,
    one sha256 over every (file name, bytes) in name order, and the newest
    ``report_date`` in it."""
    folder = Path(directory)
    paths = sorted(folder.glob("*.csv")) if folder.is_dir() else []
    digest, dates = hashlib.sha256(), []
    for path in paths:
        data = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(data)
        dates.extend(line.split(",")[0] for line in data.decode("utf-8").splitlines()[1:]
                     if line.strip())
    return {"directory": str(folder), "files": len(paths),
            "sha256": digest.hexdigest() if paths else None,
            "newest_report_date": max(dates, default=None),
            "calendar": "v82 earnings_calendar.sessions_to_reaction (NYSE sessions "
                        "to the next earnings reaction session)"}


def _splits(rows: list[dict], seed: int) -> dict:
    """The verdict table again per direction and per horizon, so a lift that
    concentrates in one is visible."""
    out = {}
    for name in ("direction", "horizon"):
        labels = sorted({_label(row.get(name)) for row in _scored(rows)}, key=_sort_key)
        out[name] = {label: monotonicity([row for row in rows if _label(row.get(name)) == label],
                                         seed=seed)
                     for label in labels}
    return out


def _population(name: str, rows: list[dict], seed: int) -> dict | None:
    if not rows:
        return None
    _progress(f"{name}: {len(rows)} rows -- buckets and bucket looks")
    buckets = population_buckets(rows)
    bucket_looks(rows, buckets, seed=seed)
    _progress(f"{name}: monotonicity, splits and factor deltas")
    weeks = sorted(row["week"] for row in rows)
    return {
        "window": {"first_week": weeks[0], "last_week": weeks[-1]},
        "n": len(rows),
        "monotonicity": monotonicity(rows, seed=seed),
        "factors": factor_deltas(rows, seed=seed),
        "buckets": buckets,
        "splits": _splits(rows, seed),
        "notes": list(_NOTES[name]),
    }


def build_report(live_rows: list[dict], train_rows: list[dict], *, seed: int,
                 generated_at: str | None = None) -> dict:
    """The whole report, pure: the two populations side by side (never
    pooled), q-values over every look, and the verdict. ``provenance`` is
    filled by ``run``."""
    populations = {"live": _population("live", live_rows, seed),
                   "train": _population("train", train_rows, seed)}
    looks = assign_qvalues(populations)
    monos = [(populations[name] or {}).get("monotonicity") for name in ("live", "train")]
    outcome = verdict(*monos)
    stamp = generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "generated_at": stamp,
        "verdict": outcome,
        # Handoff 9: n is the rows that entered the verdict, live + TRAIN.
        # write_latest keeps an earlier record on disk in place of this one.
        "verdict_of_record": {"verdict": outcome, "date": stamp[:10],
                              "n": sum((mono or {}).get("n", 0) for mono in monos)},
        "looks": looks,
        "seed": seed,
        "provenance": {},
        "populations": populations,
    }


def _file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(train_jsonl, *, seed: int = WEEK_BOOTSTRAP_SEED, write: bool = True) -> dict:
    """Load both populations, build the report, persist it (unless
    ``write=False``) and return what was written."""
    train_rows = load_train_rows(train_jsonl)
    live_rows = load_live_rows()
    report = build_report(live_rows, train_rows, seed=seed)
    report["provenance"] = {
        "earnings": earnings_provenance(),
        "train_rows": {"path": str(train_jsonl), "rows": len(train_rows),
                       "sha256": _file_sha256(train_jsonl)},
        "live_fills_include_frictions": LIVE_FILLS_INCLUDE_FRICTIONS,
        "frictions": {"slippage_bps": getattr(config, "SLIPPAGE_BPS", 5.0),
                      "commission_r": commission_r()},
        "n_resamples": N_RESAMPLES,
    }
    return write_latest(report) if write else report
```

Notes for the implementer:

- `train_earnings` is the spec's TRAIN definition, in this order: no CSV rows, or a signal later than the last CSV report plus 100 calendar days -> `unknown`; coverage reaches the signal and holds no report at or after it -> `none`; otherwise the session count. `margin_days` defaults to the spec's 100.
- A TRAIN row is netted from `entry_price` (the replay's actual fill, which the legs' own `r` is measured from) and falls back to the planned `entry`.
- `run` loads the TRAIN file first so a wrong path fails before the database is touched, and `_progress` prints flushed stage lines on stderr: the verdict run bootstraps 10,000 resamples per look and takes minutes.
- `build_report` stays pure (`provenance` is `{}` until `run` fills it), which is what lets the tests and v150 build a report from rows alone.

- [ ] **Step 6: Write the script**

Create `scripts/reports/expectancy_attribution.py`:

```python
#!/usr/bin/env python3
"""Expectancy attribution (v146): does confidence predict R?

Thin wrapper: parse the arguments, call the study module, print a summary.
Reads the closed trades from the database ``DATABASE_URL`` names and the
TRAIN confluence-replay rows from --train-jsonl; writes the latest report to
data/reports/expectancy-attribution.json unless --no-write is given.

Run: python scripts/reports/expectancy_attribution.py \
         --train-jsonl data/reports/v146-train-scenarios.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _population_line(name: str, population: dict | None) -> str:
    if not population:
        return f"  {name:<5} no rows"
    mono = population["monotonicity"]
    return (f"  {name:<5} n={population['n']} scored={mono['n']} "
            f"terciles={mono['tercile_n']} spread={mono['tercile_spread']} "
            f"ci=[{mono['ci_low']}, {mono['ci_high']}] rho={mono['spearman_rho']} "
            f"inverted={mono['inverted']}")


def summary(report: dict) -> str:
    record = report["verdict_of_record"]
    lines = [
        "Expectancy attribution",
        f"  verdict of record: {record['verdict']} ({record['date']}, n={record['n']})",
        f"  this run: {report['verdict']} | looks={report['looks']} | seed={report['seed']}",
    ]
    lines += [_population_line(name, report["populations"].get(name))
              for name in ("live", "train")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--train-jsonl", required=True,
                        help="rows written by run_backtest_range.py --scenarios --train --trades-jsonl")
    parser.add_argument("--seed", type=int, default=None,
                        help="bootstrap seed (default: the instrument's WEEK_BOOTSTRAP_SEED)")
    parser.add_argument("--no-write", action="store_true",
                        help="do not replace data/reports/expectancy-attribution.json")
    args = parser.parse_args(argv)

    from swingbot.core.analytics import expectancy_attribution as study
    seed = study.WEEK_BOOTSTRAP_SEED if args.seed is None else args.seed
    report = study.run(args.train_jsonl, seed=seed, write=not args.no_write)
    print(summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_report.py`
Expected: PASS, 0 failed (15 tests).
Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_stats.py`
Expected: PASS, 0 failed.
Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_buckets.py`
Expected: PASS, 0 failed.
Run: `python scripts/dev/testrun.py file tests/infra/test_expectancy_attribution_store.py`
Expected: PASS, 0 failed (the store is still importable without pandas, numpy or `swingbot.core.backtesting`: the study imports the store, never the reverse).
Run: `python scripts/reports/expectancy_attribution.py --help`
Expected: the usage text naming `--train-jsonl`, `--seed`, `--no-write`; exit 0; no database connection.

- [ ] **Step 8: Complexity and the main-tree check**

Run: `python -m radon cc -s -n C swingbot/core/analytics/expectancy_attribution.py scripts/reports/expectancy_attribution.py`
Expected: at most `live_row - C (11)` (a flat field mapping, below the limit of 15); nothing at 15 or above. Any other line means a function grew a branch: split it.
Run: `git -C E:/Documents/Private/Projects/Discord-Bot status --short`
Expected: empty (the main tree is untouched; the tests write only under `tmp_path`).

- [ ] **Step 9: Commit**

Name the Step 1 branch in the message (the line below is the expected `False` branch; write `already friction-adjusted, r_multiple used as is` for `True`):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/analytics/expectancy_attribution.py scripts/reports/expectancy_attribution.py tests/analytics/test_expectancy_attribution_report.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): expectancy attribution loaders, report and script -- live fills not friction-adjusted, netted like TRAIN (Handoff 5)"
```
