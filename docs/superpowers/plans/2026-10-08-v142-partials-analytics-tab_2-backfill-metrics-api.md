# v142 — Partials analytics tab: Part 2 — backfill, metrics, API

> Part of [`2026-10-08-v142-partials-analytics-tab_0-index.md`](2026-10-08-v142-partials-analytics-tab_0-index.md). The index carries the header block, the spec resolutions, the Global Constraints, the Review Focus and the full `## Parallelisation`. Read it first. Phase 2 starts in Part 1 (`_1-contract-stamps.md`, V142-2 and V142-3). **Pull one task at a time:** `grep -n "^### Task V142-5" -A 600 <this file>`.

# Phase 2 — Group A, continued: backfill and metrics

## Parallelisation

Group A (parallel): V142-2, V142-3 (Part 1), V142-4 and V142-5 (here). Each touches only its own two files and consumes only V142-1's symbols. V142-4 and V142-5 may run beside V142-2 and V142-3. Name the worktree in every dispatch.

### Task V142-4: The runner_path backfill script

**Files:**
- Create: `scripts/data/backfill_runner_path.py`
- Test: `tests/scripts/test_backfill_runner_path.py` (create)

**Interfaces:**
- Consumes: `runner_path.compute_runner_path`, `runner_path.cached_daily_bars` (V142-1); `PlanStore.all()` / `PlanStore.update()`; test helpers `_closed`, `LONG_BARS`.
- Produces: `candidates(plans) -> list`, `backfill(store, bars_fn, *, apply: bool) -> dict` (`{"stamped", "skipped", "unavailable"}`), `main(argv=None, *, store=None, bars_fn=None) -> dict`. It prints `DRY RUN|APPLIED: stamped=N skipped=N unavailable=N`. V142-11 runs it on production.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_backfill_runner_path.py`:

```python
"""v142: the runner_path backfill -- dry run writes nothing, --apply is idempotent."""
from scripts.data import backfill_runner_path as brp
from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from tests.analytics.test_runner_path import LONG_BARS, _closed
from tests.planning.test_plan_engine_model import _plan


def _seed():
    store = PlanStore()
    covered = _closed("tp1_runner_tp2", 120.0)                       # p1, AAPL: bars cover it
    uncovered = _closed("tp1_runner_tp2", 120.0)
    uncovered.plan_id, uncovered.ticker = "p2", "MSFT"               # no cache file
    stamped = _closed("tp1_runner_tp2", 120.0)
    stamped.plan_id, stamped.runner_path = "p3", {"source": "live"}  # already stamped
    active = _plan(plan_id="p4", status=PlanStatus.ACTIVE)           # never a candidate
    for plan in (covered, uncovered, stamped, active):
        store.add(plan)
    return store


def _bars(ticker):
    return LONG_BARS if ticker == "AAPL" else None


def test_dry_run_counts_and_writes_nothing(capsys):
    store = _seed()
    assert brp.main([], bars_fn=_bars) == {"stamped": 1, "skipped": 1, "unavailable": 1}
    assert store.get("p1").runner_path is None
    assert "DRY RUN: stamped=1 skipped=1 unavailable=1" in capsys.readouterr().out


def test_apply_twice_stamps_once():
    store = _seed()
    assert brp.main(["--apply"], bars_fn=_bars)["stamped"] == 1
    path = store.get("p1").runner_path
    assert (path["source"], path["mfe_r"]) == ("backfill", 4.2)
    assert brp.main(["--apply"], bars_fn=_bars) == {"stamped": 0, "skipped": 2, "unavailable": 1}
    assert store.get("p3").runner_path == {"source": "live"}         # never overwritten


def test_the_default_bar_source_is_the_disk_cache(monkeypatch):
    _seed()
    seen = []
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: seen.append(ticker))
    brp.main([])
    assert sorted(seen) == ["AAPL", "MSFT"]                           # one read per ticker


def test_an_unreadable_cache_is_unavailable_not_a_crash():
    _seed()

    def boom(ticker):
        raise OSError("bad csv")

    assert brp.main([], bars_fn=boom)["unavailable"] == 2
```

- [ ] **Step 2: Run it to verify it fails**

`python scripts/dev/testrun.py file tests/scripts/test_backfill_runner_path.py`
Expected: FAIL with `ImportError: cannot import name 'backfill_runner_path' from 'scripts.data'`.

- [ ] **Step 3: Write the script**

Create `scripts/data/backfill_runner_path.py`:

```python
#!/usr/bin/env python3
"""v142: one-off backfill of `runner_path` onto closed partial plans.

Walks every CLOSED plan whose status_history holds PARTIAL, skips any already
stamped (idempotent), and computes the stamp from the live scan's daily disk
cache (`market_data/daily`, `runner_path.cached_daily_bars`) -- never a
network fetch: a cold fetch blocks for ~18.5s per batch and the stamp is not
worth one. Writes nothing unless --apply is passed.

    python scripts/data/backfill_runner_path.py            # dry run: counts only
    python scripts/data/backfill_runner_path.py --apply    # writes source="backfill"

Production (after the v142 deploy):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_runner_path.py"
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.analytics import runner_path as rp  # noqa: E402


def candidates(plans: list) -> list:
    """Closed plans that went through PARTIAL -- the only ones with a runner."""
    return [plan for plan in plans if plan.status == "CLOSED"
            and any(entry.get("status") == "PARTIAL" for entry in plan.status_history or [])]


def _bars_for(ticker: str, bars_fn, frames: dict):
    """One disk read per ticker; an unreadable cache is a miss, not a crash."""
    if ticker not in frames:
        try:
            frames[ticker] = bars_fn(ticker)
        except Exception as exc:
            print(f"  {ticker}: cache read failed ({exc})")
            frames[ticker] = None
    return frames[ticker]


def backfill(store, bars_fn, *, apply: bool) -> dict:
    """Stamp every unstamped candidate; returns stamped / skipped / unavailable."""
    counts = {"stamped": 0, "skipped": 0, "unavailable": 0}
    frames: dict = {}
    for plan in candidates(store.all()):
        if plan.runner_path is not None:
            counts["skipped"] += 1
            continue
        path = rp.compute_runner_path(plan, _bars_for(plan.ticker, bars_fn, frames),
                                      source="backfill")
        if path is None:
            counts["unavailable"] += 1
            print(f"  unavailable: {plan.plan_id} {plan.ticker}")
            continue
        counts["stamped"] += 1
        if apply:
            plan.runner_path = path
            store.update(plan)
    return counts


def main(argv=None, *, store=None, bars_fn=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Write the stamps. Default is a dry run that only counts.")
    args = parser.parse_args(argv)
    if store is None:
        from swingbot.core.planning.plan_store import PlanStore
        store = PlanStore()
    counts = backfill(store, bars_fn or rp.cached_daily_bars, apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"{mode}: stamped={counts['stamped']} skipped={counts['skipped']} "
          f"unavailable={counts['unavailable']}")
    if not args.apply:
        print("Dry run only -- pass --apply to write.")
    return counts


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/scripts/test_backfill_runner_path.py
python -m radon cc -s -n C scripts/data/backfill_runner_path.py
```

Expected: `VERDICT: PASS` (4 tests, none skipped). radon prints nothing.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/backfill_runner_path.py tests/scripts/test_backfill_runner_path.py
git commit -m "$(cat <<'EOF'
feat(v142): one-off runner_path backfill from the disk cache, dry run by default

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

### Task V142-5: partials.py — KPIs, buckets, counterfactuals, holds, breakdowns

**Files:**
- Create: `swingbot/core/analytics/partials.py`
- Test: `tests/analytics/test_partials.py` (create)

**Interfaces:**
- Consumes: `metrics.r_multiple`; `runner_path.LADDER_R`, `close_reason`, `runner_leg`, `session_span`, `tp1_leg`, `transition_day` (V142-1); `scope.BookScope` (fields `start`, `end`, `ledger`, `strategy`, `horizon`, `direction`).
- Produces (`swingbot/core/analytics/partials.py`):
  - constants `THIN_N = 10`, `SPLIT_FRACTIONS`, `OUTCOME_BUCKETS`, `BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "side", "month")`, `FUNNEL_STAGES = ("filled", "tp1", "runner_closed", "tp2")`
  - `select_plans(plans: list, scope: BookScope) -> list`: filled plans in scope, by fill date
  - `build_report(plans: list, manual_exits: dict | None = None) -> dict` with keys `kpis`, `funnel`, `outcomes`, `counterfactuals`, `holds`, `breakdowns`, `thin_n`, `population`
  - `partial_trade(plan, manual_exits=None) -> PartialTrade | None`, `outcomes(trades)`, `counterfactuals(trades)`, `kpis(trades, decided)`
  - Test helpers V142-6 imports: `_book()`, `_trade(...)`, `MANUAL`.

- [ ] **Step 1: Write the failing test**

Create `tests/analytics/test_partials.py`:

```python
"""v142: partials.py -- KPIs and counterfactuals over hand-built partial plans."""
import pytest

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics import partials as pa
from swingbot.core.analytics.scope import BookScope
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.test_plan_engine_model import _plan

FILL, TP1, EXIT = "2026-10-01T14:00:00+00:00", "2026-10-05T15:00:00+00:00", "2026-10-07T18:00:00+00:00"


def _path(mfe, top):
    """A runner_path whose ladder is touched up to and including `top` R."""
    return {"mfe_r": mfe, "mae_r": 1.5, "sessions_after_tp1": 2, "source": "live",
            "ladder": {key: ("2026-10-06" if float(key) <= top else None)
                       for key in ("1.5", "2.0", "2.5", "3.0", "4.0")}}


def _trade(plan_id, *, status=PlanStatus.CLOSED, reason=None, runner_r=None, tp2=120.0,
           strategy="RSI", direction="bullish", path=None, fill=FILL, tp1_hit=True,
           exit_at=EXIT, ledger="main"):
    """Entry 100, risk 5 (bullish: stop 95), TP1 leg at exactly 2.0R."""
    stop = 95.0 if direction == "bullish" else 105.0
    sign = 1 if direction == "bullish" else -1
    history = [{"status": "ACTIVE", "reason": "filled", "at": fill}]
    legs = []
    if tp1_hit:
        history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": TP1})
        legs.append({"fraction": 0.5, "exit_price": 100.0 + 10.0 * sign, "r": 2.0, "reason": "tp1"})
    if runner_r is not None:
        legs.append({"fraction": 0.5, "exit_price": 100.0 + 5.0 * runner_r * sign,
                     "r": runner_r, "reason": reason})
    if status == PlanStatus.CLOSED:
        history.append({"status": "CLOSED", "reason": reason, "at": exit_at})
    return _plan(plan_id=plan_id, strategy=strategy, direction=direction, entry_price=100.0,
                 stop_loss=stop, tp1=100.0 + 10.0 * sign, tp2=tp2, status=status,
                 status_history=history, legs_realized=legs, runner_path=path, ledger=ledger)


def _book():
    return [
        _trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0),
               exit_at="2026-10-09T18:00:00+00:00"),
        _trade("B", reason="tp1_runner_be", runner_r=1.34, path=_path(2.6, 2.5)),
        _trade("C", reason="tp1_runner_trail", runner_r=3.0, path=_path(3.6, 3.0), strategy="MACD"),
        _trade("D", reason="manual"),                                   # runner leg only on the trade
        _trade("E", status=PlanStatus.PARTIAL),                         # runner still open
        _trade("F", reason="tp1_runner_trail", runner_r=2.4, tp2=None, path=_path(2.8, 2.5),
               strategy="MACD"),
        _trade("G", status=PlanStatus.ACTIVE, tp1_hit=False),           # open pre-TP1
        _trade("H", reason="loss", tp1_hit=False, direction="bearish"),  # stopped pre-TP1
    ]


MANUAL = {"D": 112.5}        # the linked trade's manual exit -> 2.5R


@pytest.fixture
def report():
    return pa.build_report(_book(), manual_exits=MANUAL)


def test_funnel(report):
    assert report["funnel"] == [{"stage": "filled", "n": 8}, {"stage": "tp1", "n": 6},
                                {"stage": "runner_closed", "n": 5}, {"stage": "tp2", "n": 1}]


def test_kpis(report):
    k = report["kpis"]
    assert (k["tp1_rate"], k["tp1_rate_n"]) == (85.7, 7)         # 6 / 7, G excluded
    assert (k["tp1_tp2_rate"], k["tp1_tp2_n"]) == (25.0, 4)      # A of A,B,C,D; F is no_tp2
    assert (k["beat_all_out"], k["beat_all_out_n"]) == (80.0, 5)  # B lost to all-out
    assert k["mean_runner_delta_r"] == pytest.approx(0.324)
    assert (k["median_tp1_exit_sessions"], k["tp1_exit_n"]) == (2.0, 5)


def test_outcome_buckets_cover_every_partial_once(report):
    rows = {row["bucket"]: row for row in report["outcomes"]}
    assert list(rows) == list(pa.OUTCOME_BUCKETS)               # no "other" row when empty
    assert {b: rows[b]["n"] for b in rows} == {"tp2": 1, "trail": 1, "floor": 1, "stall": 0,
                                               "time": 0, "manual": 1, "no_tp2": 1, "open": 1}
    assert rows["floor"]["avg_runner_r"] == 1.34 and rows["open"]["avg_runner_r"] is None
    assert rows["manual"]["avg_runner_r"] == 2.5 and rows["tp2"]["share"] == 16.7


def test_an_unknown_close_reason_is_reported_not_dropped():
    rows = pa.outcomes([pa.partial_trade(_trade("X", reason="acceptance", runner_r=1.0))])
    assert rows[-1] == {"bucket": "other", "n": 1, "share": 100.0, "avg_runner_r": 1.0}


def test_actual_exp_r_ties_out_to_r_multiple(report):
    measured = [p for p in _book() if p.plan_id in "ABCF"]
    blended = [m.r_multiple({"entry": 100.0, "stop_loss": 95.0, "direction": "bullish",
                             "legs": p.legs_realized}) for p in measured]
    blended.append(m.r_multiple({"entry": 100.0, "stop_loss": 95.0, "direction": "bullish",
                                 "legs": [{"fraction": 0.5, "r": 2.0},
                                          {"fraction": 0.5, "exit_price": 112.5}]}))
    cf = report["counterfactuals"]
    assert cf["actual_exp_r"] == pytest.approx(sum(blended) / 5) == pytest.approx(2.324)
    assert cf["all_out_exp_r"] == 2.0


def test_ladder_uses_each_trades_own_path(report):
    ladder = {row["level_r"]: row for row in report["counterfactuals"]["ladder"]}
    assert [row["n"] for row in ladder.values()] == [4] * 5      # D has no path
    assert ladder[1.5]["touch_rate"] == 100.0 and ladder[1.5]["cf_exp_r"] == 1.75
    assert ladder[3.0]["touch_rate"] == 50.0
    assert ladder[3.0]["cf_exp_r"] == pytest.approx(2.2175)
    assert ladder[4.0]["touch_rate"] == 25.0
    assert ladder[4.0]["cf_exp_r"] == pytest.approx(2.3425)


def test_split_what_if(report):
    split = {row["fraction"]: row for row in report["counterfactuals"]["split"]}
    assert split[0.5]["exp_r"] == pytest.approx(2.324)
    assert split[0.33]["exp_r"] == pytest.approx(2.4342)
    assert split[0.67]["exp_r"] == pytest.approx(2.2138)
    assert {row["n"] for row in split.values()} == {5}


def test_giveback_and_visible_exclusions(report):
    cf = report["counterfactuals"]
    assert cf["giveback"] == pytest.approx([0.2, 1.26, 0.6, 0.4])
    assert cf["path_unavailable"] == 1 and cf["runner_r_unavailable"] == 0


def test_a_manual_close_without_a_trade_price_is_counted_not_dropped():
    report = pa.build_report(_book(), manual_exits={})
    cf = report["counterfactuals"]
    assert cf["runner_r_unavailable"] == 1
    assert report["kpis"]["beat_all_out_n"] == 4
    assert report["funnel"][2] == {"stage": "runner_closed", "n": 5}


def test_counterfactuals_use_the_trades_own_fraction():
    plan = _trade("Q", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.0, 4.0))
    plan.tp1_fraction = 0.25
    plan.legs_realized[0]["fraction"], plan.legs_realized[1]["fraction"] = 0.25, 0.75
    cf = pa.counterfactuals([pa.partial_trade(plan)])
    assert cf["actual_exp_r"] == pytest.approx(0.25 * 2.0 + 0.75 * 4.0)
    assert cf["ladder"][0]["cf_exp_r"] == pytest.approx(0.25 * 2.0 + 0.75 * 1.5)


def test_holds_in_trading_sessions(report):
    h = report["holds"]
    assert h["entry_tp1"]["points"] == [2] * 6                   # Thu -> Mon, open runner included
    assert h["tp1_exit"]["points"] == [2, 2, 2, 2, 4]            # A exits Fri; E is open
    assert h["entry_exit"]["median"] == 4.0


def test_breakdowns(report):
    by_strategy = {row["key"]: row for row in report["breakdowns"]["strategy"]}
    assert (by_strategy["RSI"]["n"], by_strategy["RSI"]["tp1_rate"]) == (4, 80.0)
    assert (by_strategy["MACD"]["n"], by_strategy["MACD"]["tp1_tp2_rate"]) == (2, 0.0)
    assert all(row["thin"] for row in by_strategy.values())
    by_side = {row["key"]: row for row in report["breakdowns"]["side"]}
    assert (by_side["bearish"]["n"], by_side["bearish"]["tp1_rate"]) == (0, 0.0)
    [month] = report["breakdowns"]["month"]
    assert (month["key"], month["n"], month["tp1_rate"]) == ("2026-10", 6, None)


def test_a_row_of_ten_is_not_thin():
    plans = [_trade(f"T{i}", reason="tp1_runner_tp2", runner_r=4.0) for i in range(10)]
    [row] = pa.build_report(plans)["breakdowns"]["strategy"]
    assert (row["n"], row["thin"]) == (10, False)


def test_empty_scope_is_all_zeros_and_nones():
    report = pa.build_report([])
    assert [row["n"] for row in report["funnel"]] == [0, 0, 0, 0]
    assert report["kpis"]["tp1_rate"] is None and report["kpis"]["beat_all_out"] is None
    assert report["counterfactuals"]["actual_exp_r"] is None
    assert report["holds"]["tp1_exit"] == {"p25": None, "median": None, "p75": None, "points": []}


def test_select_plans_filters_on_fill_date_and_plan_fields():
    plans = [_trade("early", reason="tp1_runner_tp2", runner_r=4.0, fill="2026-09-30T14:00:00+00:00"),
             _trade("late", reason="tp1_runner_tp2", runner_r=4.0),
             _trade("weak", reason="tp1_runner_tp2", runner_r=4.0, ledger="weak"),
             _trade("short", reason="loss", tp1_hit=False, direction="bearish"),
             _plan(plan_id="pending", status=PlanStatus.PENDING)]
    ids = lambda scope: [p.plan_id for p in pa.select_plans(plans, scope)]
    assert ids(BookScope()) == ["early", "late", "short"]
    assert ids(BookScope(start="2026-10-01")) == ["late", "short"]
    assert ids(BookScope(ledger="both", direction="bullish")) == ["early", "late", "weak"]
    assert ids(BookScope(strategy="MACD")) == []
```

(The expected numbers are worked by hand from `_book()`. All-out = 2.0R for every trade. Deltas at f = 0.5 are A +1.0, B −0.33, C +0.5, D +0.25, F +0.2, so the mean is 0.324 and 4 of 5 beat all-out. The blended Rs are 3.0, 1.67, 2.5, 2.25 and 2.2, so actual = 2.324. Ladder 3.0R: A and C touched, so the cf values are 2.5, 1.67, 2.5 and 2.2, mean 2.2175.)

- [ ] **Step 2: Run it to verify it fails**

`python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: FAIL with `ImportError: cannot import name 'partials' from 'swingbot.core.analytics'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/analytics/partials.py`:

```python
"""v142: the Partials tab -- TP1->TP2 conversion and runner counterfactuals.

Pure functions over TradePlanV2 records; no I/O. Every R goes through
`metrics.r_multiple` (initial-risk basis). The live book is a small,
non-pre-registered sample: nothing here is a gate.

Population: *filled* = plans that reached ACTIVE; *partial* = filled plans
whose status_history holds PARTIAL. A partial plan whose runner is still
open sits in the funnel and the `open` bucket only.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

import numpy as np

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics.runner_path import (LADDER_R, close_reason, runner_leg,
                                                 session_span, tp1_leg, transition_day)

THIN_N = 10
SPLIT_FRACTIONS = (0.33, 0.5, 0.67)
#: Every partial trade lands in exactly one; "other" (an unknown close
#: reason) is reported only when non-empty, never dropped.
OUTCOME_BUCKETS = ("tp2", "trail", "floor", "stall", "time", "manual", "no_tp2", "open")
BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "side", "month")
FUNNEL_STAGES = ("filled", "tp1", "runner_closed", "tp2")
_REASON_BUCKET = {
    "tp1_runner_tp2": "tp2", "tp1_runner_trail": "trail", "tp1_runner_be": "floor",
    "tp1_runner_progress_stall": "stall", "time_exit": "time", "manual": "manual",
}


@dataclass(frozen=True)
class PartialTrade:
    plan_id: str
    strategy: str
    horizon: str
    side: str
    month: str                  # YYYY-MM of the TP1 session
    fraction: float             # the plan's own tp1_fraction
    r_tp1: float
    r_runner: float | None      # None: runner open, or a manual close with no price
    blended_r: float | None     # metrics.r_multiple over both legs
    bucket: str
    runner_path: dict | None
    hold_entry_tp1: int | None
    hold_tp1_exit: int | None
    hold_entry_exit: int | None

    @property
    def closed(self) -> bool:
        return self.bucket != "open"

    @property
    def measured(self) -> bool:
        """A closed runner whose runner R is known."""
        return self.closed and self.r_runner is not None

    @property
    def delta_r(self) -> float | None:
        """Blended R minus all-out-at-TP1 R."""
        if not self.measured:
            return None
        return (1.0 - self.fraction) * (self.r_runner - self.r_tp1)


# -- population ----------------------------------------------------------------

def _has(plan, status: str) -> bool:
    return any(entry.get("status") == status for entry in plan.status_history or [])


def is_filled(plan) -> bool:
    return _has(plan, "ACTIVE")


def is_partial(plan) -> bool:
    return _has(plan, "PARTIAL")


def _in_range(day, scope) -> bool:
    if scope.start is None and scope.end is None:
        return True
    if day is None:
        return False
    text = day.isoformat()
    return (scope.start is None or text >= scope.start) and (scope.end is None or text <= scope.end)


def _matches(plan, scope) -> bool:
    if scope.ledger != "both" and (plan.ledger or "main") != scope.ledger:
        return False
    wanted = ((scope.strategy, plan.strategy), (scope.horizon, plan.horizon_key),
              (scope.direction, plan.direction))
    return all(want is None or want == have for want, have in wanted)


def select_plans(plans: list, scope) -> list:
    """Filled plans inside a BookScope. The date range filters on FILL date."""
    return [plan for plan in plans if is_filled(plan)
            and _in_range(transition_day(plan, "ACTIVE"), scope) and _matches(plan, scope)]


# -- one trade -----------------------------------------------------------------

def outcome_bucket(plan) -> str:
    if plan.status != "CLOSED":
        return "open"
    if plan.tp2 is None:
        return "no_tp2"
    return _REASON_BUCKET.get(close_reason(plan), "other")


def _view(plan) -> dict | None:
    if plan.entry_price is None or plan.stop_loss is None:
        return None
    return {"entry": plan.entry_price, "stop_loss": plan.stop_loss, "direction": plan.direction}


def _one_leg_r(view: dict, leg: dict) -> float | None:
    return m.r_multiple({**view, "legs": [{**leg, "fraction": 1.0}]})


def _runner_or_manual(plan, manual_exits: dict) -> dict | None:
    """The runner leg; for a manual close (which records none on the plan) a
    leg built from the linked trade's exit price, when the trade has one."""
    leg = runner_leg(plan)
    if leg is not None or plan.status != "CLOSED":
        return leg
    price = manual_exits.get(plan.plan_id)
    if price is None:
        return None
    return {"fraction": round(1.0 - plan.tp1_fraction, 6), "exit_price": float(price),
            "reason": "manual"}


def _span(start, end) -> int | None:
    return None if start is None or end is None else session_span(start, end)


def partial_trade(plan, manual_exits: dict | None = None) -> PartialTrade | None:
    """One partial plan as a PartialTrade; None when it cannot be read (no
    fill price, zero risk, no TP1 leg)."""
    view, leg1 = _view(plan), tp1_leg(plan)
    r_tp1 = _one_leg_r(view, leg1) if view is not None and leg1 is not None else None
    if r_tp1 is None:
        return None
    runner = _runner_or_manual(plan, manual_exits or {})
    r_runner = _one_leg_r(view, runner) if runner is not None else None
    blended = m.r_multiple({**view, "legs": [leg1, runner]}) if runner is not None else None
    fill, tp1, exit_ = (transition_day(plan, s) for s in ("ACTIVE", "PARTIAL", "CLOSED"))
    return PartialTrade(
        plan.plan_id, plan.strategy, plan.horizon_key, plan.direction,
        tp1.isoformat()[:7] if tp1 else "unknown", float(plan.tp1_fraction), r_tp1,
        r_runner, blended, outcome_bucket(plan), plan.runner_path,
        _span(fill, tp1), _span(tp1, exit_), _span(fill, exit_))


# -- aggregates ----------------------------------------------------------------

def _rate(hits: int, n: int | None) -> float | None:
    return None if not n else round(100.0 * hits / n, 1)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def _median(values) -> float | None:
    return float(np.median(values)) if values else None


def kpis(trades: list[PartialTrade], decided: int | None) -> dict:
    """The KPI set. `decided` = filled plans that are no longer open pre-TP1
    (the TP1-rate denominator); None where it has no meaning (month rows)."""
    closed = [t for t in trades if t.closed]
    convertible = [t for t in closed if t.bucket != "no_tp2"]
    deltas = [t.delta_r for t in closed if t.measured]
    tp1_exit = [t.hold_tp1_exit for t in closed if t.hold_tp1_exit is not None]
    return {
        "tp1_rate": None if decided is None else _rate(len(trades), decided),
        "tp1_rate_n": decided,
        "tp1_tp2_rate": _rate(sum(t.bucket == "tp2" for t in convertible), len(convertible)),
        "tp1_tp2_n": len(convertible),
        "beat_all_out": _rate(sum(d > 0 for d in deltas), len(deltas)),
        "beat_all_out_n": len(deltas),
        "mean_runner_delta_r": _mean(deltas),
        "median_tp1_exit_sessions": _median(tp1_exit),
        "tp1_exit_n": len(tp1_exit),
    }


def funnel(plans: list, trades: list[PartialTrade]) -> list[dict]:
    counts = (len(plans), len(trades), sum(t.closed for t in trades),
              sum(t.bucket == "tp2" for t in trades))
    return [{"stage": stage, "n": n} for stage, n in zip(FUNNEL_STAGES, counts)]


def outcomes(trades: list[PartialTrade]) -> list[dict]:
    rows = []
    for bucket in (*OUTCOME_BUCKETS, "other"):
        group = [t for t in trades if t.bucket == bucket]
        if bucket == "other" and not group:
            continue
        rows.append({"bucket": bucket, "n": len(group), "share": _rate(len(group), len(trades)),
                     "avg_runner_r": _mean(t.r_runner for t in group)})
    return rows


def _ladder_row(pathed: list[PartialTrade], level: float) -> dict:
    key = f"{level:.1f}"
    hits = [bool(t.runner_path["ladder"].get(key)) for t in pathed]
    cf = [t.fraction * t.r_tp1 + (1.0 - t.fraction) * (level if hit else t.r_runner)
          for t, hit in zip(pathed, hits)]
    return {"level_r": level, "touch_rate": _rate(sum(hits), len(pathed)),
            "cf_exp_r": _mean(cf), "n": len(pathed)}


def _split_row(measured: list[PartialTrade], fraction: float) -> dict:
    values = [fraction * t.r_tp1 + (1.0 - fraction) * t.r_runner for t in measured]
    return {"fraction": fraction, "exp_r": _mean(values), "n": len(measured)}


def _giveback(pathed: list[PartialTrade]) -> list[float]:
    """MFE R minus banked runner R, per trade with a stamped path."""
    return [round(t.runner_path["mfe_r"] - t.r_runner, 4) for t in pathed]


def _exclusions(closed: list[PartialTrade]) -> dict:
    """Closed runners left out of a figure, counted so none vanish silently."""
    return {"path_unavailable": sum(1 for t in closed if not t.runner_path),
            "runner_r_unavailable": sum(1 for t in closed if t.r_runner is None)}


def counterfactuals(trades: list[PartialTrade]) -> dict:
    """The four what-ifs, over closed runners with a known runner R; the
    ladder and giveback further need a stamped runner_path."""
    closed = [t for t in trades if t.closed]
    measured = [t for t in closed if t.measured]
    pathed = [t for t in measured if t.runner_path]
    return {
        "actual_exp_r": _mean(t.blended_r for t in measured),
        "all_out_exp_r": _mean(t.r_tp1 for t in measured),
        "giveback": _giveback(pathed),
        "ladder": [_ladder_row(pathed, level) for level in LADDER_R],
        "split": [_split_row(measured, fraction) for fraction in SPLIT_FRACTIONS],
        **_exclusions(closed),
    }


def _quantiles(points: list[int]) -> dict:
    if not points:
        return {"p25": None, "median": None, "p75": None, "points": []}
    p25, median, p75 = (float(v) for v in np.percentile(points, [25, 50, 75]))
    return {"p25": p25, "median": median, "p75": p75, "points": sorted(points)}


def holds(trades: list[PartialTrade]) -> dict:
    """Trading sessions per stage; open runners only in the entry->TP1 stage."""
    closed = [t for t in trades if t.closed]
    return {
        "entry_tp1": _quantiles([t.hold_entry_tp1 for t in trades if t.hold_entry_tp1 is not None]),
        "tp1_exit": _quantiles([t.hold_tp1_exit for t in closed if t.hold_tp1_exit is not None]),
        "entry_exit": _quantiles([t.hold_entry_exit for t in closed if t.hold_entry_exit is not None]),
    }


_TRADE_KEY = {"strategy": lambda t: t.strategy, "horizon": lambda t: t.horizon,
              "side": lambda t: t.side, "month": lambda t: t.month}
_PLAN_KEY = {"strategy": lambda p: p.strategy, "horizon": lambda p: p.horizon_key,
             "side": lambda p: p.direction}


def _decided_by(dimension: str, plans: list) -> dict:
    if dimension not in _PLAN_KEY:
        return {}
    counts: dict[str, int] = {}
    for plan in plans:
        if plan.status != "ACTIVE":
            key = _PLAN_KEY[dimension](plan)
            counts[key] = counts.get(key, 0) + 1
    return counts


def breakdown(dimension: str, trades: list[PartialTrade], plans: list) -> list[dict]:
    """KPI rows per key. Month is the month of the TP1 hit, so it has no
    TP1-rate denominator; a key with filled plans but no partial still shows."""
    groups: dict[str, list[PartialTrade]] = {}
    for trade in trades:
        groups.setdefault(_TRADE_KEY[dimension](trade), []).append(trade)
    decided = _decided_by(dimension, plans)
    rows = []
    for key in sorted(set(groups) | set(decided)):
        group = groups.get(key, [])
        denominator = decided.get(key, 0) if dimension in _PLAN_KEY else None
        rows.append({"key": key, "n": len(group), "thin": len(group) < THIN_N,
                     **kpis(group, denominator)})
    return rows


def build_report(plans: list, manual_exits: dict | None = None) -> dict:
    """Everything the Partials tab draws, over already-scoped filled plans."""
    partials = [plan for plan in plans if is_partial(plan)]
    trades = [t for plan in partials if (t := partial_trade(plan, manual_exits)) is not None]
    decided = sum(1 for plan in plans if plan.status != "ACTIVE")
    return {
        "kpis": kpis(trades, decided),
        "funnel": funnel(plans, trades),
        "outcomes": outcomes(trades),
        "counterfactuals": counterfactuals(trades),
        "holds": holds(trades),
        "breakdowns": {dim: breakdown(dim, trades, plans) for dim in BREAKDOWN_DIMENSIONS},
        "thin_n": THIN_N,
        "population": {"filled": len(plans), "partial": len(trades),
                       "unreadable": len(partials) - len(trades)},
    }
```

- [ ] **Step 4: Run the tests to verify they pass, and check complexity**

```bash
python scripts/dev/testrun.py file tests/analytics/test_partials.py
python -m radon cc -s -n C swingbot/core/analytics/partials.py
```

Expected: `VERDICT: PASS` (15). radon lists only `kpis` C (12) and `counterfactuals` C (11), both under 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/partials.py tests/analytics/test_partials.py
git commit -m "$(cat <<'EOF'
feat(v142): partials metrics -- TP1/TP2 rates, runner buckets, counterfactuals, holds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

# Phase 3 — API

## Parallelisation

Sequential: V142-6 after V142-5. It serialises `partials.build_report`, and its test reuses V142-5's `_book()`.

### Task V142-6: GET /api/v1/analytics/partials

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py`: insert directly above `@api_v1.route("/analytics/calibration", methods=["GET"])` (~:669)
- Test: `tests/admin/test_api_v1_analytics_partials.py` (create)

**Interfaces:**
- Consumes: `partials.select_plans`, `partials.build_report` (V142-5); `scope.echo`; the module's own `_scope()`, `_all_trades()`, `TradeLog`, `jsonify`, `require_auth`, `api_v1`.
- Produces: `GET /api/v1/analytics/partials` → `build_report(...)` merged with `{"scope": {...}, "n": <filled plans in scope>}`. It accepts the six scope parameters and nothing else (400 otherwise). V142-7 mirrors this shape in `models.ts`.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_api_v1_analytics_partials.py`:

```python
"""v142: GET /api/v1/analytics/partials -- scoped, echoed, plans-only."""
import pytest

from swingbot.core.planning.plan_engine import plan_to_dict
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _trade
from tests.analytics.test_partials import _book
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/partials"


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("plans", [plan_to_dict(plan) for plan in plans])
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _manual_trade():
    """D's linked trade: the admin close realised the runner at 112.5 (2.5R)."""
    trade = _trade("dddddddddddddddd", plan_id="D", status="closed")
    trade["exit_price"] = 112.5
    return trade


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def test_shape_and_echo(seed, logged_in):
    seed(plans=_book(), trades=[_manual_trade()])
    body = logged_in.get(_URL).get_json()
    assert set(body) == {"kpis", "funnel", "outcomes", "counterfactuals", "holds",
                         "breakdowns", "thin_n", "population", "scope", "n"}
    assert body["n"] == 8 and body["scope"]["ledger"] == "main"
    assert [row["n"] for row in body["funnel"]] == [8, 6, 5, 1]
    assert body["counterfactuals"]["runner_r_unavailable"] == 0     # D priced from its trade
    assert body["kpis"]["beat_all_out_n"] == 5
    assert set(body["breakdowns"]) == {"strategy", "horizon", "side", "month"}


def test_without_the_linked_trade_the_manual_runner_is_counted_unpriced(seed, logged_in):
    seed(plans=_book())
    body = logged_in.get(_URL).get_json()
    assert body["counterfactuals"]["runner_r_unavailable"] == 1


def test_scope_filters_on_fill_date_and_plan_fields(seed, logged_in):
    seed(plans=_book())
    assert logged_in.get(f"{_URL}?from=2026-10-02").get_json()["n"] == 0
    assert logged_in.get(f"{_URL}?strategy=MACD").get_json()["n"] == 2
    assert logged_in.get(f"{_URL}?direction=bearish").get_json()["n"] == 1


def test_an_empty_scope_answers_with_zeros(seed, logged_in):
    seed()
    body = logged_in.get(_URL).get_json()
    assert body["n"] == 0 and [row["n"] for row in body["funnel"]] == [0, 0, 0, 0]
    assert body["kpis"]["tp1_rate"] is None


def test_rejects_non_scope_parameters(logged_in):
    assert_error(logged_in.get(f"{_URL}?dim=strategy"), "invalid", 400)
```

- [ ] **Step 2: Run it to verify it fails**

`python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py`
Expected: FAIL. The route does not exist yet, so every test gets a 404 (`assert 404 == 401`, `'NoneType' object is not subscriptable`).

- [ ] **Step 3: Implement**

In `swingbot/admin/api_v1/analytics.py`, insert directly above `@api_v1.route("/analytics/calibration", methods=["GET"])`:

```python
def _manual_exit_prices() -> dict[str, float]:
    """plan_id -> the linked trade's exit price.

    A manual close realises the runner as a leg on the TRADE only
    (`TradeLog.close_trade_manual`); the plan records no leg. The Partials
    tab reads that price for a closed runner whose plan carries none.
    """
    return {trade["plan_id"]: float(trade["exit_price"]) for trade in _all_trades(TradeLog())
            if trade.get("plan_id") and trade.get("exit_price") is not None}


@api_v1.route("/analytics/partials", methods=["GET"])
@require_auth
def analytics_partials():
    """TP1->TP2 conversion and runner counterfactuals over the scoped live
    book (spec v142). Plans, not trades: the scope's date range filters on
    FILL date, and `n` is the filled plans in scope. Live book only -- a
    small, non-pre-registered sample, never a gate."""
    from swingbot.core.analytics import partials as pa
    from swingbot.core.analytics.scope import echo
    from swingbot.core.planning.plan_store import PlanStore

    scope = _scope()
    plans = pa.select_plans(PlanStore().all(), scope)
    report = pa.build_report(plans, manual_exits=_manual_exit_prices())
    return jsonify({**report, **echo(scope, len(plans))})
```

- [ ] **Step 4: Run the tests to verify they pass, plus the sibling analytics suite**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py
python -m radon cc -s -n C swingbot/admin/api_v1/analytics.py
```

Expected: `VERDICT: PASS` ×2 (6 in the new file). radon lists only the pre-existing `analytics_by_dimension`, `analytics_performance`, `analytics_heat_grid`, `analytics_strategies` and `analytics_equity_curve`. Neither `analytics_partials` nor `_manual_exit_prices` appears.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics_partials.py
git commit -m "$(cat <<'EOF'
feat(v142): GET /api/v1/analytics/partials, scoped on fill date

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```
