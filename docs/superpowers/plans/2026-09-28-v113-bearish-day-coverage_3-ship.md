# v113 Part 3 — Ship decisions (passes only), fade live parity, documentation, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, amendments, Review Focus and Parallelisation live in `2026-09-28-v113-bearish-day-coverage_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md` §5, §7, §8

Each of V113-18, V113-19 and V113-25 starts by reading `results/<date>-v113-holdout.md` and the holdout JSONs. **A block runs only for a candidate whose holdout JSON has `"status": "scored"` and `"passes": true`.** V113-20 … V113-24 run only when V113-19 finds the fade passed; otherwise V113-19 records each as skipped. With no pass anywhere, skip straight to V113-26.

Code changes (V113-18, V113-20 … V113-25) happen on one worktree branch named `2026-09-28-v113-bearish-day-coverage-wiring` (`worktree-lifecycle`), created by whichever runs first. Iterate with `testrun.py file`; run `testrun.py fast` once after the last of them (V113-25 Step 7), then merge.

---

# Phase C — Ship and close-out

### Task V113-18: Wire the Part B cells that passed

**Files (only if a Part B cell passed):**
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES`)
- Modify: `swingbot/core/backtesting/validation_registry.json` (via `emit-registry`)
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts:21`, `frontend/src/app/workspaces/trades/trades.ts:684` and every other hard-coded horizon list `git grep` finds
- Modify: `tests/market/test_v113_horizon.py`, `tests/market/test_v113_horizon_vocab.py` (the "no cell ships yet" assertions)
- Create: `tests/market/test_v113_shipped.py`

**Interfaces:**
- Consumes: `admits`/`cells` and `live_horizons()` (V113-2); `measure_v113 emit-registry` (V113-11); the passing `b-*` holdout JSONs (V113-17).
- Produces: live admission of exactly the passing `(strategy, direction, "1w")` pairs; one `(strategy, "1w")` registry row per strategy; the `no_cells` fixture and `tests/market/test_v113_shipped.py` that V113-24 extends.

- [ ] **Step 1: List the passes.**

```bash
python - <<'EOF'
import json, glob
for p in sorted(glob.glob("docs/superpowers/results/*-v113-holdout-b-*.json")):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("status") == "scored" and d.get("passes"):
        print(p, d["strategy"], d["direction"], d["stats"]["n"], d["stats"]["win_rate"], d["stats"]["expectancy_r"])
EOF
```

No line printed → this task is a no-op; go to V113-19.

- [ ] **Step 2: Admit each passing pair through `cells`.** In `STRATEGY_GATES`, for each passing strategy add (or extend) a `"cells"` key holding exactly its passing pairs, leaving every other key untouched. A strategy with no entry today (EMA Crossover, Elliott Wave, RSI Divergence) gets a new entry holding only `"cells"` — its legacy axes stay "all directions, all legacy horizons". Above each change add one comment line: `# v113 Part B (<date>): <direction> on 1w -- TRAIN N=<n> WR=<wr> ExpR=<e>; holdout N=<n> WR=<wr> ExpR=<e>, Tier 1 + lower bound.` Example shape:

```python
    "MACD": {"directions": ("bullish",), "horizons": ("3m", "4m", "7m", "8m", "9m"),
             "cells": {("bearish", "1w")}},
```

- [ ] **Step 3: Registry rows.** For each strategy, pass all of its passing Part B holdout JSONs together (the script refuses a set that differs from the shipped `cells`):

```bash
python scripts/backtest/measure_v113.py emit-registry --holdout-json <that strategy's passing b-* holdout JSONs> --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
```

- [ ] **Step 4: Tests that assumed nothing ships.** In `tests/market/test_v113_horizon.py`, add at the top:

```python
@pytest.fixture
def no_cells(monkeypatch):
    """The pre-ship world: STRATEGY_GATES without any v113 cells."""
    stripped = {name: {k: v for k, v in gates.items() if k != "cells"} for name, gates in st.STRATEGY_GATES.items()}
    monkeypatch.setattr(st, "STRATEGY_GATES", stripped)
```

and add `no_cells` as a parameter to `test_every_registered_strategy_is_masked_on_1w_by_default` and `test_live_horizons_is_legacy_until_a_cell_admits_1w` (they describe the rule, not today's gates). In `tests/market/test_v113_horizon_vocab.py`, change `test_slash_horizon_choices_are_the_live_vocabulary`'s expectation to `[*st.live_horizons(), "all"]` and `test_run_full_backtest_walks_the_live_vocabulary`'s to `sorted(st.live_horizons())`; add `assert st.live_horizons()[0] == "1w"` to the first.

Create `tests/market/test_v113_shipped.py`:

```python
"""v113: exactly the holdout-passing (strategy, direction) pairs are admitted on 1w."""
from swingbot.core.market import strategy_types as st

SHIPPED = {<("Strategy", "direction"), one per passing Part B cell>}


def test_v113_shipped_1w_cells():
    admitted = {(name, direction) for name, gates in st.STRATEGY_GATES.items()
                for direction, horizon in gates.get("cells", ()) if horizon == "1w"}
    assert admitted == SHIPPED
    for name, direction in SHIPPED:
        assert st.admits(name, direction, "1w")
    assert st.live_horizons()[0] == "1w"
```

- [ ] **Step 5: Frontend horizon lists.** Run `git grep -n "'2w', '4w', '2m', '3m'" -- frontend/src`. In every non-spec list (at least `analytics.ts` `FALLBACK_HORIZONS` and `trades.ts` `horizonOptions`) prepend `'1w'`, and update the adjacent comment that says "ten" to "eleven". Update any spec file that asserts one of those lists' contents. Run each touched spec: `npm --prefix frontend test -- --include <spec path>`.

- [ ] **Step 6: Soak, not alerts.** Leave `STRATEGY_ALERTS_MODE` and `STRATEGY_ALERTS_LIVE_STRATEGIES` alone (amendment 6).

- [ ] **Step 7: Run and commit**

Run: `python scripts/dev/testrun.py file tests/market/test_v113_shipped.py tests/market/test_v113_horizon.py tests/market/test_v113_horizon_vocab.py tests/market/test_v113_horizon_witness.py tests/backtesting/test_registry.py tests/admin/test_gate_description.py`
Expected: all PASS.

```bash
git add swingbot/core/market/strategy_types.py swingbot/core/backtesting/validation_registry.json tests/market/test_v113_shipped.py tests/market/test_v113_horizon.py tests/market/test_v113_horizon_vocab.py <each frontend file and spec touched in Step 5>
git commit -m "feat(v113): ship Part B 1w cells <list> -- Tier 1 + lower bound on the 2026 holdout; registry rows (strategy, 1w)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-19: Part A gate — does the fade go live?

**Files:** none.

**Interfaces:**
- Consumes: `results/<date>-v113-holdout-a-fade.json` if it exists; `results/<date>-v113-partA.md`.
- Produces: either "run V113-20 … V113-24" or one recorded outcome for V113-26 — `NO-LIFT at <stage> (<clause>)` or `SEALED-THIN (N=<n>, retry at HOLDOUT_END ≥ 2026-12-31)` — with V113-20 … V113-24 recorded as **skipped (fade did not pass)**.

Amendment 2 (partner decision, 2026-09-28): a fade pass ships, but only with live parity — the four live-support tasks V113-20 … V113-23, then the unmask in V113-24, all in this phase.

- [ ] **Step 1: Read the outcome.**

```bash
python - <<'EOF'
import json, glob
paths = sorted(glob.glob("docs/superpowers/results/*-v113-holdout-a-fade.json"))
if not paths:
    print("no holdout shot: ended on TRAIN (see partA.md)")
for p in paths:
    d = json.load(open(p, encoding="utf-8"))
    print(p, d["status"], d.get("passes"), d.get("stats") or d.get("n"), d.get("clauses"))
EOF
```

- [ ] **Step 2: Branch.**
  - `status == "scored"` and `passes == true` → continue with V113-20.
  - Anything else → write down for V113-26: the outcome line above, and "V113-20, V113-21, V113-22, V113-23, V113-24: skipped (fade did not pass)". Go to V113-25. **Change no code.**

---

### Task V113-20: Live-parity witness — existing plans through `PlanManager`, golden written before any live change

**Runs only if V113-19 said the fade passed.**

**Files:**
- Create: `tests/planning/test_v113_manager_witness.py`
- Create: `tests/fixtures/v113/manager_witness.json` (generated)

**Interfaces:**
- Consumes: `PlanManager`, `PlanStore`, `plan_to_dict`, `FakePriceFeed`, `tests.planning.test_plan_engine_model._plan` — all as they are before V113-22.
- Produces: `witness(tmp_dir) -> dict` and the golden. V113-21 … V113-24 must leave it byte-identical: no plan without a v113 field (`entry_type == "limit"`, `tp1_fraction == 1.0`, `time_stop_bars`) may behave differently.

- [ ] **Step 1: Confirm the manager is untouched.** `git diff main --stat -- swingbot/core/planning/plan_manager.py swingbot/core/planning/plan_types.py` must print nothing.

- [ ] **Step 2: Write the witness module.**

```python
"""v113 Phase C: the live PlanManager behaves byte-identically for every plan
that declares none of the v113 fields (entry_type "limit", tp1_fraction 1.0,
time_stop_bars). The golden was written by __main__ BEFORE V113-22 touched
plan_manager.py. Regenerate ONLY on that pre-change tree:
    python -m tests.planning.test_v113_manager_witness
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import tempfile
from pathlib import Path

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import plan_to_dict
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "v113" / "manager_witness.json"
NOW = dt.datetime(2026, 10, 6, 15, 0, tzinfo=dt.timezone.utc)      # Tue 11:00 ET, regular session
_VOLATILE = {"at", "closed_at"}                                      # wall-clock stamps
PINS = {"INTRADAY_RTH_ONLY": False, "PYRAMIDING_ENABLED": False,
        "STALL_EXIT_ENABLED": False, "TRAIL_NOTIFY_MIN_R": 0.25}
_MISSING = object()


def _active(**kw):
    base = dict(status=PlanStatus.ACTIVE, entry_price=100.0,
                status_history=[{"status": "ACTIVE", "reason": "market_entry", "at": "2026-10-05"}])
    base.update(kw)
    return _plan(**base)


def _stop_entry(**kw):
    base = dict(entry_type="stop_entry", trigger_price=105.0, stop_loss=104.0, tp1=110.0)
    base.update(kw)
    return _plan(**base)


SCENARIOS = {
    "bull_be_tp1_tp2": (lambda: _active(), [101.2, 102.5, 104.0, 105.2], None),
    "bull_loss": (lambda: _active(), [97.0, 94.0], None),
    "bear_be_tp1_runner_floor": (lambda: _active(direction="bearish", stop_loss=105.0, tp1=98.0, tp2=95.0),
                                 [98.9, 97.5, 99.9], None),
    "stop_entry_fill_then_tp1": (lambda: _stop_entry(), [104.5, 106.0, 110.5], None),
    "stop_entry_expired": (lambda: _stop_entry(), [104.0], lambda ticker, created_at: 6),
    "stop_entry_invalidated": (lambda: _stop_entry(stop_loss=95.0), [94.0], None),
    "stop_entry_risk_cap": (lambda: _stop_entry(stop_loss=95.0), [106.0], None),
}


@contextlib.contextmanager
def _pinned():
    saved = {key: getattr(config, key, _MISSING) for key in PINS}
    try:
        for key, value in PINS.items():
            setattr(config, key, value)
        yield
    finally:
        for key, value in saved.items():
            if value is _MISSING:
                delattr(config, key)
            else:
                setattr(config, key, value)


def _sanitize(value):
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in sorted(value.items()) if k not in _VOLATILE}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _run(tmp_dir, name) -> dict:
    make, prices, bars = SCENARIOS[name]
    feed = FakePriceFeed([("AAPL", price) for price in prices])
    store = PlanStore(path=str(Path(tmp_dir) / f"{name}.json"))
    store.add(make())
    manager = PlanManager(store, feed.get_price, bar_count_fn=bars)
    events = []
    for _ in prices:
        events.extend([event.transition, _sanitize(event.detail)] for event in manager.poll(now=NOW))
    plan = plan_to_dict(store.get("p1"))
    # V113-23 adds this always-None field to every existing plan; the golden
    # predates it, so it is checked here and kept out of the comparison.
    assert plan.pop("time_stop_bars", None) is None
    return {"events": events, "plan": _sanitize(plan)}


def witness(tmp_dir) -> dict:
    with _pinned():
        return {name: _run(tmp_dir, name) for name in SCENARIOS}


def test_existing_plans_are_byte_identical_to_the_pre_v113_golden(tmp_path):
    assert witness(tmp_path) == json.loads(GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(witness(tmp), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
```

- [ ] **Step 3: Generate and sanity-check.**

Run: `python -m tests.planning.test_v113_manager_witness`
Expected: `wrote .../tests/fixtures/v113/manager_witness.json`.

```bash
python -c "import json;d=json.load(open('tests/fixtures/v113/manager_witness.json'));[print(k, [e[0] for e in v['events']], v['plan']['status']) for k, v in d.items()]"
```

Required (the scenarios exercise what they name): `bull_be_tp1_tp2` shows `be_moved`, `tp1_partial`, `closed` and ends `CLOSED`; `bull_loss` ends `CLOSED`; `bear_be_tp1_runner_floor` shows `tp1_partial` then `closed`; `stop_entry_fill_then_tp1` shows `filled` then `tp1_partial`; the last three end `CANCELLED` with `cancelled_expired`, `cancelled_invalidated`, `cancelled_risk_cap`. Resent notices may repeat a transition; that is today's behaviour and stays in the golden. If a scenario does not reach its named state, fix the scenario's prices, not the golden.

- [ ] **Step 4: Run and commit**

Run: `python scripts/dev/testrun.py file tests/planning/test_v113_manager_witness.py`
Expected: 1 passed.

```bash
git add tests/planning/test_v113_manager_witness.py tests/fixtures/v113/manager_witness.json
git commit -m "test(v113): PlanManager golden for existing plans, written before the fade's live-parity changes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-21: Live strategy frames carry the earnings columns the fade reads

**Runs only if V113-19 said the fade passed.**

**Files:**
- Modify: `swingbot/core/market/short_entries.py` (one constant)
- Modify: `swingbot/core/scanning/strategy_pass.py` (imports; new `_earnings_needed`, `_with_earnings`; two lines in `run_strategy_pass`)
- Create: `tests/scanning/test_v113_live_earnings.py`

**Interfaces:**
- Consumes: `earnings_context.attach(df, ticker, *, source=None)`; `earnings_calendar.LiveSource`; `admits` (V113-2); `short_entries.FADE` (V113-7).
- Produces: `short_entries.EARNINGS_CONTEXT_STRATEGIES = (FADE,)`; `strategy_pass._earnings_needed(horizons) -> bool`; `strategy_pass._with_earnings(frame, ticker, needed) -> DataFrame`. Once the fade is admitted (V113-24), every live strategy frame carries `evt_reaction`/`evt_bars_to_next`, so `fade_frame` fires in the live scan exactly as it did in the backtest.

Load `no-lookahead` before starting. The backtest attached these columns from the CSV calendar (`market_data/earnings`); live reads the same schedule from `LiveSource` (the next **scheduled** report date — the documented v104 §3.4 exception; the report's content is never read).

- [ ] **Step 1: Write the failing tests** — `tests/scanning/test_v113_live_earnings.py`:

```python
"""v113 A live parity: strategy frames carry evt_* columns when the fade is admitted."""
import logging

import numpy as np
import pandas as pd

from swingbot.core.market.entry_filters import gate_override
from swingbot.core.market.short_entries import EARNINGS_CONTEXT_STRATEGIES, FADE
from swingbot.core.scanning import strategy_pass
from tests.helpers import make_ohlcv

UNMASKED = {"directions": (), "cells": {("bearish", "1w")}}


def test_the_fade_is_the_strategy_that_reads_earnings_context():
    assert EARNINGS_CONTEXT_STRATEGIES == (FADE,)


def test_needed_only_when_a_reading_strategy_is_admitted():
    assert not strategy_pass._earnings_needed(("2w", "4w"))
    with gate_override(FADE, UNMASKED):
        assert strategy_pass._earnings_needed(("1w", "2w"))
        assert not strategy_pass._earnings_needed(("2w",))


def test_attaches_live_calendar_columns_when_needed(monkeypatch):
    seen = {}

    def fake_attach(df, ticker, *, source=None):
        seen["ticker"], seen["source"] = ticker, type(source).__name__
        out = df.copy()
        out["evt_reaction"], out["evt_bars_to_next"] = 0.0, np.nan
        return out

    monkeypatch.setattr(strategy_pass.earnings_context, "attach", fake_attach)
    frame = make_ohlcv([100.0] * 30)
    out = strategy_pass._with_earnings(frame, "AAPL", True)
    assert {"evt_reaction", "evt_bars_to_next"} <= set(out.columns)
    assert seen == {"ticker": "AAPL", "source": "LiveSource"}
    assert strategy_pass._with_earnings(frame, "AAPL", False) is frame


def test_a_calendar_failure_leaves_the_frame_bare_and_logs(monkeypatch, caplog):
    def boom(df, ticker, *, source=None):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(strategy_pass.earnings_context, "attach", boom)
    frame = make_ohlcv([100.0] * 30)
    with caplog.at_level(logging.WARNING):
        assert strategy_pass._with_earnings(frame, "AAPL", True) is frame
    assert "earnings context unavailable" in caplog.text


def test_run_strategy_pass_hands_the_enriched_frame_to_the_signals(monkeypatch):
    captured = []
    monkeypatch.setattr(strategy_pass, "_with_earnings",
                        lambda frame, ticker, needed: frame.assign(evt_bars_to_next=np.nan) if needed else frame)
    monkeypatch.setattr(strategy_pass, "strategy_signals",
                        lambda frame, horizon, spy_df: captured.append(set(frame.columns)) or [])
    df = make_ohlcv([100.0] * 30, start="2026-09-01")
    with gate_override(FADE, UNMASKED):
        strategy_pass.run_strategy_pass(
            ["AAPL"], {"AAPL": df}, now=pd.Timestamp("2026-10-06T22:00:00Z").to_pydatetime(),
            horizons=["1w"], spy_df=df, regimes=None, rs_combined_of=lambda t: None, mode="shadow",
            live_allow=set(), trade_log=None, plan_store=None)
    assert captured and "evt_bars_to_next" in captured[0]
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v113_live_earnings.py`
Expected: `ImportError: cannot import name 'EARNINGS_CONTEXT_STRATEGIES'`.

- [ ] **Step 3: The constant.** In `swingbot/core/market/short_entries.py`, directly after the `FADE_*` constants, add:

```python
# v113 A live parity: strategies whose entry reads the evt_* earnings columns.
# The live strategy pass attaches them (live calendar) whenever one of these is
# admitted; the backtest attached the same columns from the CSV calendar.
EARNINGS_CONTEXT_STRATEGIES = (FADE,)
```

- [ ] **Step 4: The strategy pass.** In `swingbot/core/scanning/strategy_pass.py`:
  - Change `from swingbot.core.market import market_context` to `from swingbot.core.market import earnings_calendar, earnings_context, market_context`, and add `from swingbot.core.market.short_entries import EARNINGS_CONTEXT_STRATEGIES` and `from swingbot.core.market.strategy_types import admits` to the imports.
  - Directly above `def run_strategy_pass(` add:

```python
def _earnings_needed(horizons) -> bool:
    """True when a strategy that reads evt_* columns is admitted on a live horizon."""
    for strategy in EARNINGS_CONTEXT_STRATEGIES:
        for horizon in horizons:
            if admits(strategy, "bullish", horizon) or admits(strategy, "bearish", horizon):
                return True
    return False


def _with_earnings(frame, ticker, needed: bool):
    """v113 A live parity: attach evt_reaction / evt_bars_to_next from the live
    earnings calendar -- the columns the backtest attached from the CSV
    calendar -- when an admitted strategy reads them. A calendar failure leaves
    the frame without them, so those strategies stay silent (fail-closed)
    rather than firing blind into a report."""
    if not needed:
        return frame
    try:
        return earnings_context.attach(frame, ticker, source=earnings_calendar.LiveSource())
    except Exception:
        log.warning("strategy pass: earnings context unavailable for %s -- evt strategies silent",
                    ticker, exc_info=True)
        return frame
```

  - In `run_strategy_pass`, directly after `deps = _PassDeps(...)` add `needed = _earnings_needed(horizons)`, and directly after the `if frame is None or len(frame) == 0: continue` guard add `frame = _with_earnings(frame, ticker, needed)`. No other line changes.

- [ ] **Step 5: Run the tests and the neighbours**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v113_live_earnings.py tests/scanning/ tests/market/test_fade_entries.py tests/planning/test_v113_manager_witness.py`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/scanning/strategy_pass.py`
Expected: nothing listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/short_entries.py swingbot/core/scanning/strategy_pass.py tests/scanning/test_v113_live_earnings.py
git commit -m "feat(v113): live strategy frames carry evt_* earnings columns when the fade is admitted -- fail-closed on a calendar outage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-22: `PlanManager` fills a limit entry — next session only, else it expires unfilled

**Runs only if V113-19 said the fade passed.**

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (imports; new module helpers `sessions_since`, `_limit_session_live`; `__init__` one attribute; `_step` one branch; new `_step_pending_limit`, `_open_limit`)
- Create: `tests/planning/test_plan_manager_limit.py`

**Interfaces:**
- Consumes: `lifecycle.limit_hit`, `limit_fill_price`, `at_or_beyond_stop` (V113-6); `session.nyse_calendar`, `market_today`, `is_regular_session`, `session_date`; V113-20's witness.
- Produces: `sessions_since(date_iso, now=None) -> int | None` (NYSE sessions after that date through today; V113-23 reuses it); a PENDING plan with `entry_type == "limit"` is stepped by `_step_pending_limit`. Every other PENDING plan still goes through the untouched `_step_pending`.

Live twin of `exit_sim._limit_entry_exit` (bar *t+1* high ≥ limit, fill at `max(open, limit)`, gap-through-stop exits flat). Load `no-lookahead`: the live check sees only prices as they print.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_plan_manager_limit.py`:

```python
"""v113 A live parity: a resting sell limit, good for the session after the signal bar only."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager, sessions_since
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

UTC = dt.timezone.utc
SIGNAL_EVENING = dt.datetime(2026, 10, 5, 21, 0, tzinfo=UTC)    # Mon 17:00 ET: bar t is done
NEXT_OPEN = dt.datetime(2026, 10, 6, 13, 31, tzinfo=UTC)        # Tue 09:31 ET: session t+1
NEXT_MID = dt.datetime(2026, 10, 6, 17, 0, tzinfo=UTC)          # Tue 13:00 ET
NEXT_AFTER = dt.datetime(2026, 10, 6, 21, 0, tzinfo=UTC)        # Tue 17:00 ET: t+1 is over
DAY_AFTER = dt.datetime(2026, 10, 7, 14, 0, tzinfo=UTC)         # Wed: session t+2


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _limit(**kw):
    base = dict(strategy="Downtrend Overbought Fade", horizon_key="1w", direction="bearish",
                entry_type="limit", trigger_price=100.0, stop_loss=102.0, tp1=98.0, tp2=None,
                tp1_fraction=1.0, breakeven_trigger_fraction=1.0, expiry_bars=1,
                created_at="2026-10-05")
    base.update(kw)
    return _plan(**base)


def _run(tmp_path, ticks):
    """ticks: [(now, price)]; returns (all transitions, final plan)."""
    feed = FakePriceFeed([("AAPL", price) for _, price in ticks])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_limit())
    manager = PlanManager(store, feed.get_price)
    transitions = [e.transition for now, _ in ticks for e in manager.poll(now=now)
                   if e.transition in ("filled", "closed", "cancelled_expired")]
    return transitions, store.get("p1")


def test_sessions_since_counts_nyse_sessions():
    assert sessions_since("2026-10-05", NEXT_OPEN) == 1
    assert sessions_since("2026-10-05", SIGNAL_EVENING) == 0
    assert sessions_since("2026-10-02", NEXT_OPEN) == 2            # Fri -> Tue skips the weekend


def test_no_fill_on_the_signal_day_itself(tmp_path):
    transitions, plan = _run(tmp_path, [(SIGNAL_EVENING, 101.0)])
    assert transitions == [] and plan.status == PlanStatus.PENDING


def test_a_first_print_through_the_limit_fills_at_that_print(tmp_path):
    transitions, plan = _run(tmp_path, [(NEXT_OPEN, 100.8)])
    assert transitions == ["filled"] and plan.status == PlanStatus.ACTIVE and plan.entry_price == 100.8


def test_a_later_cross_fills_at_the_limit(tmp_path):
    transitions, plan = _run(tmp_path, [(NEXT_OPEN, 99.5), (NEXT_MID, 100.3)])
    assert transitions == ["filled"] and plan.entry_price == 100.0


def test_no_fill_after_the_session_and_expiry_the_day_after(tmp_path):
    transitions, plan = _run(tmp_path, [(NEXT_OPEN, 99.5), (NEXT_AFTER, 101.0), (DAY_AFTER, 101.0)])
    assert transitions == ["cancelled_expired"] and plan.status == PlanStatus.CANCELLED


def test_a_gap_through_the_stop_fills_and_exits_flat(tmp_path):
    transitions, plan = _run(tmp_path, [(NEXT_OPEN, 102.4)])
    assert transitions == ["filled", "closed"] and plan.status == PlanStatus.CLOSED
    assert plan.entry_price == 102.4


def test_a_stop_entry_plan_never_takes_the_limit_path(tmp_path, monkeypatch):
    from swingbot.core.planning import plan_manager as pm
    called = []
    monkeypatch.setattr(pm.PlanManager, "_step_pending_limit",
                        lambda self, plan, price, now=None: called.append(plan.plan_id) or [])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_plan(entry_type="stop_entry", trigger_price=105.0, stop_loss=104.0, tp1=110.0))
    PlanManager(store, FakePriceFeed([("AAPL", 104.0)]).get_price).poll(now=NEXT_MID)
    assert called == []
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_limit.py`
Expected: `ImportError: cannot import name 'sessions_since'`.

- [ ] **Step 3: Module helpers.** In `swingbot/core/planning/plan_manager.py`:
  - Change the session import to `from swingbot.core.market.session import (is_quiet_hours, is_regular_session, is_tape_open, market_today, nyse_calendar, session_date)` and add `from swingbot.core.planning.lifecycle import at_or_beyond_stop, limit_fill_price, limit_hit`.
  - Directly after `poll_stop_fill`, add:

```python
def sessions_since(date_iso: str, now=None) -> int | None:
    """NYSE sessions after the ET date that starts `date_iso` up to and
    including today's: 0 on that date, 1 on the next session. None outside the
    frozen calendar (the caller then does nothing -- fail-closed)."""
    return nyse_calendar().sessions_between(dt.date.fromisoformat(date_iso[:10]), market_today(now))


def _limit_session_live(plan, now=None) -> bool:
    """A limit entry trades only in the regular hours of a real session 1..expiry_bars
    after its signal bar -- exit_sim._limit_entry_exit's bars t+1..t+expiry."""
    age = sessions_since(plan.created_at, now)
    return (age is not None and 1 <= age <= plan.expiry_bars and is_regular_session(now)
            and nyse_calendar().is_session(market_today(now)))
```

  and add `import datetime as dt` to the imports (keep the existing `from datetime import ...` line).

- [ ] **Step 4: Dispatch and the limit step.** In `PlanManager.__init__` add `self._limit_opened: dict[str, str] = {}` after `self._risk_cap_warned`. In `_step`, replace

```python
        if plan.status == PlanStatus.PENDING:
            return self._step_pending(plan, price)
```

with

```python
        if plan.status == PlanStatus.PENDING:
            if plan.entry_type == "limit":
                return self._step_pending_limit(plan, price, now)
            return self._step_pending(plan, price)
```

Directly after `_step_pending` add:

```python
    def _step_pending_limit(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """v113 A: a resting LIMIT entry. Expires unfilled once the sessions it
        was good for are over. During them (regular hours only) it fills when
        the price trades through the limit: at the session's first observed
        print when that print already gapped through (the open, as
        limit_fill_price(plan, open) in the backtest), otherwise at the limit.
        No risk-cap check: a limit fill sits between the limit and the stop, so
        its planned loss never exceeds the plan's own."""
        age = sessions_since(plan.created_at, now)
        if age is not None and age > plan.expiry_bars:
            record_transition(plan, PlanStatus.CANCELLED, reason="expired", at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "cancelled_expired", {"bars_waited": age})]
        if not _limit_session_live(plan, now):
            return []
        opening = self._limit_opened.get(plan.plan_id) != session_date(now)
        self._limit_opened[plan.plan_id] = session_date(now)
        if not limit_hit(plan, price, price):
            return []
        return self._open_limit(plan, limit_fill_price(plan, price if opening else plan.trigger_price), price)

    def _open_limit(self, plan: TradePlanV2, fill: float, price: float) -> list[PlanEvent]:
        """Record the fill; a fill at or through the stop (a gap past it) exits
        flat at once, as exit_sim._fill_bar_exit scores it."""
        plan.entry_price = fill
        record_transition(plan, PlanStatus.ACTIVE, reason="limit_fill", at=self._now())
        filled = PlanEvent(plan.plan_id, "filled", {"entry_price": fill, "live_price": price})
        if not at_or_beyond_stop(plan, fill):
            self.store.update(plan)
            return [filled]
        record_transition(plan, PlanStatus.CLOSED, reason="scratch", at=self._now())
        leg = {"fraction": 1.0, "exit_price": fill, "r": 0.0, "reason": "gap_through_stop"}
        persisted = self._persist_terminal(plan, leg, "closed")
        return [filled, PlanEvent(plan.plan_id, "closed", {"reason": "scratch", "exit_price": fill,
                                                          "leg": leg, "_terminal_persisted": persisted})]
```

(A restart mid-session treats its first regular-hours print as the opening print; that is the only case where a later cross can fill above the limit. Say so in the V113-26 methodology row.)

- [ ] **Step 5: Run the tests and the manager neighbours**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_limit.py tests/planning/test_v113_manager_witness.py tests/planning/test_plan_manager_pending.py tests/planning/test_plan_manager_fills.py tests/planning/test_plan_manager_feed.py`
Expected: all PASS — the witness unchanged.

Run: `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py`
Expected: the same list and grades as before this task (`poll D (21)`, `_step_active D (21)`, `_step_partial C (19)`, `_on_event C (15)`, `_feed_bookkeeping C (12)`, `_check_bar_active C (11)`); no new entry.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_limit.py
git commit -m "feat(v113): PlanManager limit entries -- next session only, first-print gap fill else at the limit, expire unfilled, gap through the stop exits flat

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-23: Whole-position target and an enforced time stop, for plans that declare them

**Runs only if V113-19 said the fade passed.**

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (new field `time_stop_bars`)
- Modify: `swingbot/core/planning/params.py` (`PLAN_SHAPES["Downtrend Overbought Fade"]` gains `"time_stop_bars": 7`)
- Modify: `swingbot/core/planning/builders.py` (`build_strategy_plan` sets `plan.time_stop_bars`)
- Modify: `swingbot/core/planning/plan_manager.py` (constant `TIME_STOP_FROM`; `_step` → `_step_status` + time stop; new `_step_active_whole`, `_close_whole`, `_sessions_held`, `_time_stop`, `_close_time_stop`)
- Modify: `tests/planning/test_fade_builder.py` (the exact `PLAN_SHAPES` row)
- Create: `tests/planning/test_plan_manager_whole_and_time_stop.py`

**Interfaces:**
- Consumes: `sessions_since` (V113-22); `_persist_terminal`, `_close_runner`, `_continuous`, `poll_stop_fill` (existing); V113-20's witness.
- Produces: `TradePlanV2.time_stop_bars: int | None = None`; an ACTIVE plan with `tp1_fraction >= 1.0` is stepped by `_step_active_whole` (stop, then the whole position at the target; no break-even, no stall exit, no PARTIAL); any ACTIVE/PARTIAL plan with `time_stop_bars` set is closed at the close of the Nth session after its fill. Plans without those fields reach exactly the pre-v113 code; `recycle_candidates` (the advice-only notice) is not touched.

Parity: `exit_sim` timed the fade out at the close of bar `entry_index + 7` (`HORIZONS["1w"]["max_holding_days"]`); live closes at the live price from 15:45 ET on the 7th session after the fill session (≈ the close), or at the first live print after it if that window was missed.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_plan_manager_whole_and_time_stop.py`:

```python
"""v113 A live parity: whole-position target and the declared time stop."""
import datetime as dt
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market.session import nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager, recycle_candidates
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

UTC = dt.timezone.utc
FILLED_AT = "2026-10-06T14:00:00+00:00"                    # Tue, regular hours
SEVENTH = nyse_calendar().sessions(dt.date(2026, 10, 7), dt.date(2026, 10, 31))[6]
MIDDAY = dt.datetime(2026, 10, 7, 16, 0, tzinfo=UTC)


def _at(day, hh, mm):
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=UTC)   # UTC; ET = UTC-4 in October


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)


def _fade(**kw):
    base = dict(strategy="Downtrend Overbought Fade", horizon_key="1w", direction="bearish",
                entry_type="limit", trigger_price=100.0, entry_price=100.0, stop_loss=102.0, tp1=98.0,
                tp2=None, tp1_fraction=1.0, breakeven_trigger_fraction=1.0, expiry_bars=1,
                status=PlanStatus.ACTIVE, created_at="2026-10-05",
                status_history=[{"status": "ACTIVE", "reason": "limit_fill", "at": FILLED_AT}])
    base.update(kw)
    return _plan(**base)


def _poll(tmp_path, plan, ticks):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan)
    feed = FakePriceFeed([("AAPL", price) for _, price in ticks])
    manager = PlanManager(store, feed.get_price)
    events = [e for now, _ in ticks for e in manager.poll(now=now) if e.transition == "closed"]
    return events, store.get("p1")


def test_the_target_closes_the_whole_position(tmp_path):
    events, plan = _poll(tmp_path, _fade(), [(MIDDAY, 97.9)])
    assert plan.status == PlanStatus.CLOSED and events[0].detail["reason"] == "win"
    assert events[0].detail["leg"]["fraction"] == 1.0
    assert PlanStatus.PARTIAL not in [h["status"] for h in plan.status_history]


def test_no_break_even_move_before_the_target(tmp_path):
    events, plan = _poll(tmp_path, _fade(), [(MIDDAY, 98.2)])
    assert events == [] and plan.working_stop is None and plan.status == PlanStatus.ACTIVE


def test_the_stop_closes_it_as_a_loss(tmp_path):
    events, plan = _poll(tmp_path, _fade(), [(MIDDAY, 102.1)])
    assert plan.status == PlanStatus.CLOSED and events[0].detail["reason"] == "loss"


def test_the_time_stop_waits_for_the_close_of_the_seventh_session(tmp_path):
    events, plan = _poll(tmp_path, _fade(time_stop_bars=7),
                         [(_at(SEVENTH, 18, 0), 99.5), (_at(SEVENTH, 19, 50), 99.4)])
    assert len(events) == 1 and events[0].detail["reason"] == "time_stop"
    assert events[0].detail["exit_price"] == 99.4 and plan.status == PlanStatus.CLOSED


def test_a_missed_window_closes_at_the_next_live_print(tmp_path):
    day_after = nyse_calendar().next_session(SEVENTH)
    events, _ = _poll(tmp_path, _fade(time_stop_bars=7), [(_at(day_after, 13, 40), 99.0)])
    assert [e.detail["reason"] for e in events] == ["time_stop"]


def test_a_plan_without_time_stop_bars_is_never_timed_out(tmp_path):
    day_after = nyse_calendar().next_session(SEVENTH)
    events, plan = _poll(tmp_path, _fade(), [(_at(day_after, 19, 50), 99.0)])
    assert events == [] and plan.status == PlanStatus.ACTIVE


def test_a_partial_runner_with_a_time_stop_closes_its_remainder(tmp_path):
    plan = _fade(tp1_fraction=0.5, time_stop_bars=7, status=PlanStatus.PARTIAL, working_stop=99.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 98.0, "r": 1.0, "reason": "tp1"}],
                 status_history=[{"status": "ACTIVE", "reason": "limit_fill", "at": FILLED_AT},
                                 {"status": "PARTIAL", "reason": "tp1_partial", "at": FILLED_AT}])
    events, closed = _poll(tmp_path, plan, [(_at(SEVENTH, 19, 50), 98.5)])
    assert events[0].detail["reason"] == "time_stop" and events[0].detail["leg"]["fraction"] == 0.5
    assert closed.status == PlanStatus.CLOSED


def test_the_advice_only_recycle_notice_ignores_the_new_field():
    base = dict(plan_id="x", ticker="AAPL", status="ACTIVE", time_stop_days=5, direction="bullish",
                entry_price=100.0, risk_per_share=2.0, activated_at="2026-01-02T15:00:00")
    plain, declared = SimpleNamespace(**base), SimpleNamespace(**base, time_stop_bars=7)
    assert recycle_candidates([declared], {"AAPL": 100.1}) == recycle_candidates([plain], {"AAPL": 100.1})


def test_the_field_round_trips_and_defaults_to_none():
    plan = _fade(time_stop_bars=7)
    assert plan_from_dict(plan_to_dict(plan)).time_stop_bars == 7
    legacy = plan_to_dict(_fade())
    legacy.pop("time_stop_bars")
    assert plan_from_dict(legacy).time_stop_bars is None


def test_the_fade_declares_the_measured_hold():
    assert PLAN_SHAPES["Downtrend Overbought Fade"]["time_stop_bars"] == HORIZONS["1w"]["max_holding_days"] == 7
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_whole_and_time_stop.py`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'time_stop_bars'`; the target test sees `tp1_partial`.

- [ ] **Step 3: The field and the shape.**
  - `swingbot/core/planning/plan_types.py`: directly after `hold_cap_bars: int | None = None` add

```python
    # v113 A: an ENFORCED time stop -- PlanManager closes the position at the
    # close of the Nth session after its fill (exit_sim's max_holding_days
    # timeout, live). None = no enforced time stop (every plan before v113;
    # the advice-only recycle notice keys off time_stop_days, not this).
    time_stop_bars: int | None = None
```

  - `swingbot/core/planning/params.py`: in `PLAN_SHAPES["Downtrend Overbought Fade"]` add `"time_stop_bars": 7` (a comment: `# = HORIZONS["1w"]["max_holding_days"], the measured timeout`).
  - `swingbot/core/planning/builders.py` `build_strategy_plan`: directly after `plan.stall_exit_day = ...` add `plan.time_stop_bars = shape.get("time_stop_bars")`. (`backtest._bt_plan` reads only the four keys it passes to `TradePlanV2`; `exit_sim` keeps timing out at `max_holding_days`, which equals it.)
  - `tests/planning/test_fade_builder.py::test_exit_params_and_plan_shape_rows`: add `"time_stop_bars": 7` to the expected `PLAN_SHAPES` dict.

- [ ] **Step 4: The manager.** In `swingbot/core/planning/plan_manager.py`, after `NOTICE_RESEND_DAYS = 5` add:

```python
# v113 A: a declared time stop closes from this ET time on its last session --
# the final quarter-hour, standing in for exit_sim's exit at that bar's close.
TIME_STOP_FROM = dt.time(15, 45)
```

Replace `_step` with:

```python
    def _step(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        events = self._step_status(plan, price, now)
        if events or plan.time_stop_bars is None or plan.status not in (
                PlanStatus.ACTIVE, PlanStatus.PARTIAL):
            return events
        return self._time_stop(plan, price, now)

    def _step_status(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        if plan.status == PlanStatus.PENDING:
            if plan.entry_type == "limit":
                return self._step_pending_limit(plan, price, now)
            return self._step_pending(plan, price)
        if plan.status == PlanStatus.ACTIVE:
            if plan.tp1_fraction >= 1.0:
                return self._step_active_whole(plan, price, now)
            return self._step_active(plan, price, now)     # Tasks 61-63
        if plan.status == PlanStatus.PARTIAL:
            return self._step_partial(plan, price, now)    # Tasks 64-66
        return []
```

Directly after `_step_active` add:

```python
    def _step_active_whole(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """v113 A: TP1 closes the WHOLE position (tp1_fraction 1.0) -- the live
        twin of exit_sim's single-leg walk. Stop first, then the target; no
        break-even arming, no stall exit, no runner, no PARTIAL."""
        sign = 1 if plan.direction == "bullish" else -1
        risk = abs(plan.entry_price - plan.stop_loss)
        if (price - plan.stop_loss) * sign <= 0:
            fill = poll_stop_fill(price, plan.stop_loss, self._continuous(plan, plan.stop_loss, now))
            return self._close_whole(plan, fill, "loss", risk, sign)
        if (price - plan.tp1) * sign >= 0:
            return self._close_whole(plan, price, "win", risk, sign)
        return []

    def _close_whole(self, plan: TradePlanV2, fill: float, reason: str, risk: float,
                     sign: int) -> list[PlanEvent]:
        leg = {"fraction": 1.0, "exit_price": fill,
               "r": (fill - plan.entry_price) * sign / risk if risk > 0 else 0.0, "reason": reason}
        if reason == "win":
            plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
        # _on_event maps reason "win" -> win, "loss" -> loss, anything else ("time_stop") -> closed.
        persisted = self._persist_terminal(plan, leg, reason if reason in ("win", "loss") else "closed")
        return [PlanEvent(plan.plan_id, "closed", {"reason": reason, "exit_price": fill, "leg": leg,
                                                   "_terminal_persisted": persisted})]

    def _sessions_held(self, plan: TradePlanV2, now=None) -> int | None:
        """NYSE sessions since the fill session -- exit_sim's `j - entry_index`."""
        filled_at = next((h.get("at") for h in plan.status_history
                          if h.get("status") == PlanStatus.ACTIVE), None)
        return None if not filled_at else sessions_since(filled_at, now)

    def _time_stop(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """v113 A: the declared time stop. Due at the close of the Nth session
        after the fill (from TIME_STOP_FROM on it), or at the first live print
        after that session if the window was missed. Only plans with
        time_stop_bars reach here; the advice-only recycle notice is separate."""
        held = self._sessions_held(plan, now)
        if held is None or held < plan.time_stop_bars or not is_tape_open(now):
            return []
        if held == plan.time_stop_bars and now_et(now).time() < TIME_STOP_FROM:
            return []
        return self._close_time_stop(plan, price)

    def _close_time_stop(self, plan: TradePlanV2, price: float) -> list[PlanEvent]:
        sign = 1 if plan.direction == "bullish" else -1
        risk = abs(plan.entry_price - plan.stop_loss)
        if plan.status == PlanStatus.PARTIAL:
            return self._close_runner(plan, price, "time_stop", risk, sign)
        return self._close_whole(plan, price, "time_stop", risk, sign)
```

Add `now_et` to the session import.

- [ ] **Step 5: Run the tests, both witnesses and the manager neighbours**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_whole_and_time_stop.py tests/planning/test_plan_manager_limit.py tests/planning/test_v113_manager_witness.py tests/planning/test_fade_builder.py tests/planning/test_plan_serialization.py tests/planning/test_plan_manager_active.py tests/planning/test_plan_manager_partial.py tests/planning/test_plan_manager_feed.py tests/market/test_v113_horizon_witness.py`
Expected: all PASS — the manager witness unchanged. If `test_plan_serialization.py` pins the exact field list, add `time_stop_bars` to it.

Run: `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py`
Expected: the pre-task list and grades, unchanged; `_step`, `_step_status` and the new methods are not listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_types.py swingbot/core/planning/params.py swingbot/core/planning/builders.py swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_whole_and_time_stop.py tests/planning/test_fade_builder.py
git commit -m "feat(v113): PlanManager whole-position target (tp1_fraction 1.0) and enforced time stop (time_stop_bars) -- existing plans byte-identical

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Add `tests/planning/test_plan_serialization.py` if Step 5 changed it.)

---

### Task V113-24: Resting-order alert line, then unmask the fade on `1w`

**Runs only if V113-19 said the fade passed; after V113-20 … V113-23.**

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` (new `_resting_orders_text`; one field in `build_strategy_alert_embed`)
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES["Downtrend Overbought Fade"]`)
- Modify: `swingbot/core/backtesting/validation_registry.json` (via `emit-registry`)
- Modify: `tests/market/test_fade_entries.py`, `tests/market/test_short_entries.py` (masked-fade assertions)
- Modify: `tests/market/test_v113_horizon.py`, `tests/market/test_v113_horizon_vocab.py`, frontend horizon lists — only if V113-18 did not already
- Create or modify: `tests/market/test_v113_shipped.py`
- Create: `tests/scanning/test_v113_fade_live.py`

**Interfaces:**
- Consumes: everything V113-20 … V113-23 produced; the passing `a-fade` holdout JSON; `measure_v113 emit-registry`.
- Produces: the fade admitted on `(bearish, 1w)` only; a `(Downtrend Overbought Fade, 1w)` registry row; strategy alerts that state the resting orders.

- [ ] **Step 1: Production sizing precheck (read-only; real money).** The fade is always in structural-stop scope, so v104's fail-closed guard blocks every fade plan unless the account sizes by risk. Read the mode without changing anything: `bash scripts/ops/ssh-hetzner.sh "grep -o '\"sizing_mode\": *\"[a-z_]*\"' /opt/swing-bot/data/account.json"`. If it is `account_pct`, **stop and ask the partner** (`AskUserQuestion`) whether to switch to risk sizing before the fade ships; never change production from this task.

- [ ] **Step 2: Write the failing tests** — `tests/scanning/test_v113_fade_live.py`:

```python
"""v113 A shipped: the fade fires live as a limit plan with its resting orders spelled out."""
import pytest

from swingbot import config
from swingbot.core.market import strategy_types as st
from swingbot.core.market.short_entries import FADE
from swingbot.core.scanning import alert_embeds
from swingbot.core.scanning.strategy_pass import build_strategy_plan_at
from tests.market.test_fade_entries import HZ, fade_df


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)


def test_the_fade_is_admitted_on_bearish_1w_only():
    assert st.STRATEGY_GATES[FADE] == {"directions": (), "cells": {("bearish", "1w")}}
    assert st.admits(FADE, "bearish", "1w")
    assert not st.admits(FADE, "bullish", "1w") and not st.admits(FADE, "bearish", "2w")


def test_the_live_plan_is_the_measured_shape_and_the_alert_states_the_orders():
    df, t = fade_df()
    plan = build_strategy_plan_at(df.iloc[:t + 1], ticker="T", strategy=FADE, horizon_key=HZ,
                                  direction="bearish", regime2_state=None)
    close = float(df["Close"].iloc[t])
    assert (plan.entry_type, plan.expiry_bars, plan.tp1_fraction, plan.time_stop_bars) == ("limit", 1, 1.0, 7)
    text = alert_embeds._resting_orders_text(plan)
    assert f"SELL LIMIT {close:.2f}" in text and f"STOP {close * 1.02:.2f}" in text
    assert f"TARGET {plan.tp1:.2f}" in text and "7th session after the fill" in text
    fields = {f.name: f.value for f in alert_embeds.build_strategy_alert_embed(plan).fields}
    assert fields["Resting orders"] == text


def test_market_plans_get_no_resting_orders_line():
    from types import SimpleNamespace
    plan = SimpleNamespace(entry_type="market", direction="bullish")
    assert alert_embeds._resting_orders_text(plan) is None
```

Run: `python scripts/dev/testrun.py file tests/scanning/test_v113_fade_live.py`
Expected: FAIL — the gate is still `{"directions": ()}`; no `_resting_orders_text`.

- [ ] **Step 3: The alert line.** In `swingbot/core/scanning/alert_embeds.py`, directly above `build_strategy_alert_embed` add:

```python
def _resting_orders_text(plan) -> str | None:
    """v113 A: the orders a limit-entry plan is traded with, placed at alert time."""
    if getattr(plan, "entry_type", None) != "limit":
        return None
    side = "SELL" if plan.direction == "bearish" else "BUY"
    text = (f"{side} LIMIT {plan.trigger_price:.2f}, day order for the next session only · "
            f"STOP {plan.stop_loss:.2f} · TARGET {plan.tp1:.2f} (whole position)")
    bars = getattr(plan, "time_stop_bars", None)
    if bars is None:
        return text
    return f"{text} · time stop: exit at the close of the {bars}th session after the fill"
```

and inside `build_strategy_alert_embed`, directly after the `add_field(name="Plan (v2)", ...)` call:

```python
    orders = _resting_orders_text(plan)
    if orders:
        embed.add_field(name="Resting orders", value=orders, inline=False)
```

- [ ] **Step 4: Unmask.** In `STRATEGY_GATES` replace the fade's row and its comment with:

```python
    # v113 Part A (<date>): bearish on 1w only -- TRAIN m=<m> N=<n> WR=<wr> ExpR=<e>;
    # holdout N=<n> WR=<wr> ExpR=<e>, Tier <t>. Live parity: V113-20..V113-23.
    "Downtrend Overbought Fade": {"directions": (), "cells": {("bearish", "1w")}},
```

Set `DEFAULT_PARAMS[FADE]` in `short_entries.py` to the holdout cell's `m` (`{"m": <m>}`) if it is not `1.0`, and update `test_short_lists_and_defaults` in `tests/market/test_fade_entries.py` to match. Every test that asserts a `0.98` target was written for `m = 1.0`: find them with `git grep -n "0.98" -- tests/market/test_fade_entries.py tests/planning/test_fade_builder.py` and pin `monkeypatch.setitem(DEFAULT_PARAMS[FADE], "m", 1.0)` in each (add the `monkeypatch` parameter), rather than changing the expected numbers.

- [ ] **Step 5: Registry row.**

```bash
python scripts/backtest/measure_v113.py emit-registry --holdout-json docs/superpowers/results/<date>-v113-holdout-a-fade.json --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
```

- [ ] **Step 6: Tests that assumed the fade is masked, and the vocabulary.**
  - `tests/market/test_fade_entries.py::test_registered_short_only_and_masked_until_a_cell_admits_1w`: replace the `STRATEGY_GATES[se.FADE] == {"directions": ()}` assertion and the two "masked" lines with `assert STRATEGY_GATES[se.FADE] == UNMASKED` and an assertion that `ef.entries_for(se.FADE, df, HZ)` fires bearish at `t`; keep the `2w` assertion.
  - `tests/market/test_short_entries.py::test_registered_short_only_and_masked`: loop over `V104_SHORTS` (import it) instead of `SHORT_STRATEGIES`.
  - If V113-18 was a no-op, do its Step 4 edits now (the `no_cells` fixture in `tests/market/test_v113_horizon.py`, the two `test_v113_horizon_vocab.py` expectations) and its Step 5 frontend lists, and create `tests/market/test_v113_shipped.py` from its Step 4 code with `SHIPPED = {("Downtrend Overbought Fade", "bearish")}`. If V113-18 ran, add `("Downtrend Overbought Fade", "bearish")` to its `SHIPPED`.
  - Leave `STRATEGY_ALERTS_MODE` / `STRATEGY_ALERTS_LIVE_STRATEGIES` alone (amendment 6).

- [ ] **Step 7: Run and commit**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v113_fade_live.py tests/market/test_fade_entries.py tests/market/test_short_entries.py tests/market/test_v113_shipped.py tests/market/test_v113_horizon.py tests/market/test_v113_horizon_vocab.py tests/planning/test_v113_manager_witness.py tests/market/test_v113_horizon_witness.py tests/backtesting/test_registry.py`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/scanning/alert_embeds.py`
Expected: no new entry; `build_strategy_alert_embed` not listed.

```bash
git add swingbot/core/scanning/alert_embeds.py swingbot/core/market/strategy_types.py swingbot/core/market/short_entries.py swingbot/core/backtesting/validation_registry.json tests/scanning/test_v113_fade_live.py tests/market/test_fade_entries.py tests/market/test_short_entries.py tests/market/test_v113_shipped.py <test_v113_horizon.py, test_v113_horizon_vocab.py and frontend files if Step 6 touched them>
git commit -m "feat(v113): ship the Downtrend Overbought Fade on bearish 1w with live parity -- resting-order alert line, registry row

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-25: Wire Part D if it passed — inverse ETFs join the watchlist, tagged

**Files (only if `d-inverse-etfs` passed):**
- Modify: `swingbot/core/marketdata/universe.py` (`is_etf`; new `_inverse_rows`, `is_inverse`, `inverse_label`)
- Modify: `swingbot/core/edge/rs_gate.py` (`rs_verdict`)
- Modify: `swingbot/core/scanning/alert_embeds.py` (`build_strategy_alert_embed`) — after V113-24 if it ran (same file)
- Modify: `swingbot/core/scanning/scan_run.py` (new `_confluence_tickers`; two expressions in `_sync_run_scan`) — recommended option only
- Modify: `swingbot/core/scanning/strategy_pass.py` (new `_measured`; one loop header in `run_strategy_pass`) — recommended option only; after V113-21 if it ran (same file)
- Create: `tests/test_v113_inverse_etfs.py`

**Interfaces:**
- Consumes: `data/universe/inverse_etfs.json` (V113-12); the passing `d-inverse-etfs` holdout JSON (V113-17).
- Produces: `universe.is_inverse(symbol) -> bool`, `universe.inverse_label(symbol) -> str | None`; the RS leader gate never blocks an inverse ETF; the strategy alert labels it; (recommended) inverse tickers skip the confluence scan and bearish strategy signals. The watchlist change itself happens in V113-27 after deploy.

- [ ] **Step 1: Ask the partner about the unmeasured populations** (`AskUserQuestion`, one question, recommended first). Part D measured only the live **bullish strategy** masks. Adding the four ETFs to the watchlist would also feed them to the confluence scan and to bearish strategy signals — neither measured.
  - Question: "Part D passed (N=<n>, WR <wr>%, ExpR <e> on the 2026 holdout). On SH/PSQ/RWM/DOG, alert only through what was measured — bullish strategy signals — or through the full scan?"
  - Options: "Measured population only: skip the confluence scan and bearish signals on the four (recommended)", "Full scan, like any other ticker (unmeasured)".
  Do Step 5 only for the recommended answer; for the other, skip it and record in V113-26 that the confluence and bearish populations on inverse tickers ship unmeasured.

- [ ] **Step 2: Write the failing tests** — `tests/test_v113_inverse_etfs.py`:

```python
"""v113 §5: inverse ETFs are tagged, never RS-leader-gated, and labelled."""
import pytest

from swingbot import config
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.marketdata import universe


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    monkeypatch.setattr(universe, "_INVERSE_CACHE", None)
    monkeypatch.setattr(universe, "_ETF_CACHE", None)


def test_the_manifest_tags_the_four_inverse_etfs():
    assert all(universe.is_inverse(t) for t in ("SH", "psq", "RWM", "DOG"))
    assert not universe.is_inverse("SPY") and not universe.is_inverse("AAPL")
    assert universe.is_etf("SH")
    assert universe.inverse_label("SH") == "Long SH = short S&P 500"
    assert universe.inverse_label("SPY") is None


def test_the_bullish_rs_leader_gate_never_applies_to_an_inverse_etf(monkeypatch):
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0, raising=False)   # switch the (off) gate on
    assert rs_verdict("AAPL", "bullish", 10.0, rs_available=True)["status"] == "block"
    assert rs_verdict("SH", "bullish", 10.0, rs_available=True)["status"] == "exempt"


def test_the_bearish_laggard_rule_still_reads_an_inverse_etf(monkeypatch):
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 25.0, raising=False)
    assert rs_verdict("SH", "bearish", 90.0, rs_available=True)["status"] == "block"


def test_the_strategy_alert_labels_an_inverse_etf():
    from types import SimpleNamespace
    from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed
    plan = SimpleNamespace(ticker="SH", direction="bullish", strategy="RSI", horizon_key="4w",
                           badge="WEAK", trigger_price=40.0, stop_loss=39.2, tp1=41.5, tp2=None,
                           ledger="main", plan_id="p1", entry_type="market")
    fields = {f.name: f.value for f in build_strategy_alert_embed(plan).fields}
    assert fields["Inverse ETF"] == "Long SH = short S&P 500"
    plan.ticker = "AAPL"
    assert "Inverse ETF" not in {f.name for f in build_strategy_alert_embed(plan).fields}


def test_measured_population_only():
    from swingbot.core.scanning import scan_run, strategy_pass
    assert scan_run._confluence_tickers(["AAPL", "SH", "DOG", "MSFT"]) == ["AAPL", "MSFT"]
    fired = [("RSI", "bullish"), ("Break & Retest", "bearish")]
    assert strategy_pass._measured("SH", fired) == [("RSI", "bullish")]
    assert strategy_pass._measured("AAPL", fired) == fired
```

(If the partner chose the full scan, delete `test_measured_population_only`.)

Run: `python scripts/dev/testrun.py file tests/test_v113_inverse_etfs.py`
Expected: FAIL — `AttributeError: module ... has no attribute '_INVERSE_CACHE'`.

- [ ] **Step 3: Universe tags.** In `swingbot/core/marketdata/universe.py`, change `is_etf`'s loop to `for name in ("etfs", "sp500", "inverse_etfs"):` and add after `is_etf`:

```python
# --- Inverse-ETF tag (v113 Part D) -------------------------------------------
#
# Read raw from data/universe/inverse_etfs.json: load() keeps only the four
# required keys, and the label needs "tracks".

_INVERSE_CACHE: dict | None = None


def _inverse_rows() -> dict:
    global _INVERSE_CACHE
    if _INVERSE_CACHE is None:
        try:
            with open(os.path.join(UNIVERSE_DIR, "inverse_etfs.json"), "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw = []
        _INVERSE_CACHE = {str(row["symbol"]).upper(): row for row in raw
                          if isinstance(row, dict) and row.get("inverse")}
    return _INVERSE_CACHE


def is_inverse(symbol: str) -> bool:
    """True for a 1x inverse index ETF (v113 D): long it = short its index."""
    return str(symbol).upper() in _inverse_rows()


def inverse_label(symbol: str) -> str | None:
    """"Long SH = short S&P 500" for an inverse ETF, else None."""
    row = _inverse_rows().get(str(symbol).upper())
    return None if row is None else f"Long {row['symbol']} = short {row['tracks']}"
```

- [ ] **Step 4: RS exemption and the label.**
  - `swingbot/core/edge/rs_gate.py` `rs_verdict`: directly after the `is_rs_eligible` block add

```python
    if direction == "bullish":
        from swingbot.core.marketdata.universe import is_inverse
        if is_inverse(symbol):
            return {"status": "exempt",
                    "reason": f"{symbol} is an inverse ETF -- its RS vs SPY is structurally negative"}
```

  - `swingbot/core/scanning/alert_embeds.py` `build_strategy_alert_embed`: directly after the `add_field(name="Plan (v2)", ...)` call (and after V113-24's "Resting orders" field if present) add

```python
    from swingbot.core.marketdata.universe import inverse_label
    label = inverse_label(plan.ticker)
    if label:
        embed.add_field(name="Inverse ETF", value=label, inline=False)
```

- [ ] **Step 5 (recommended answer only): measured population only.**
  - `swingbot/core/scanning/scan_run.py`: add near the other module-level helpers

```python
def _confluence_tickers(tickers):
    """v113 D: inverse ETFs trade only through the population Part D measured
    (live bullish strategy masks) -- never the confluence scan."""
    from swingbot.core.marketdata.universe import is_inverse
    return [ticker for ticker in tickers if not is_inverse(ticker)]
```

  In `_sync_run_scan`, change `progress.total = len(tickers) * max(1, len(horizons_to_scan))` to `progress.total = len(_confluence_tickers(tickers)) * max(1, len(horizons_to_scan))`, and the `tickers,` argument that closes the `fetch.map_tickers(` call to `_confluence_tickers(tickers),`. Change nothing else in that function.
  - `swingbot/core/scanning/strategy_pass.py`: add above `run_strategy_pass`

```python
def _measured(ticker, fired):
    """v113 D: on an inverse ETF only bullish strategy signals were measured."""
    from swingbot.core.marketdata.universe import is_inverse
    if not is_inverse(ticker):
        return fired
    return [(strategy, direction) for strategy, direction in fired if direction == "bullish"]
```

  and in `run_strategy_pass` change `for strategy, direction in strategy_signals(frame, horizon, spy_df=spy_df):` to `for strategy, direction in _measured(ticker, strategy_signals(frame, horizon, spy_df=spy_df)):`.

- [ ] **Step 6: Run and commit**

Run: `python scripts/dev/testrun.py file tests/test_v113_inverse_etfs.py tests/scanning/test_rs_gate_wiring.py tests/scanning/ tests/edge/`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/edge/rs_gate.py swingbot/core/marketdata/universe.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/scan_run.py`
Expected: `_sync_run_scan` still `F (108)`; no new function listed; no function's grade worse.

```bash
git add swingbot/core/marketdata/universe.py swingbot/core/edge/rs_gate.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/strategy_pass.py tests/test_v113_inverse_etfs.py
git commit -m "feat(v113): inverse-ETF tag -- RS leader gate exempt, labelled alerts, measured population only; ETFs join the watchlist at release

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Drop `scan_run.py`/`strategy_pass.py` from the command if the partner chose the full scan.)

- [ ] **Step 7: Close the wiring branch.** After whichever of V113-18, V113-20 … V113-24 and V113-25 ran: `python scripts/dev/testrun.py fast` once (`0 failed`, `0 xfailed`), plus `python scripts/dev/testrun.py file tests/market/test_v113_horizon_witness.py tests/planning/test_v113_manager_witness.py` (the first is `slow`); if V113-18 or V113-24 touched `frontend/`, also `npm --prefix frontend test` once. Then merge the wiring branch into `main` per `worktree-lifecycle`, after checking `git log main` for other sessions' commits to the same files.

---

### Task V113-26: Methodology rows and strategy docs (every outcome)

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Modify: `docs/strategy-types/README.md`, `docs/strategy-types/shared-mechanics.md`, each Part B strategy page
- Create: `docs/strategy-types/downtrend-overbought-fade.md`

**Interfaces:**
- Consumes: every v113 results file; V113-18, V113-19 … V113-24 and V113-25 outcomes and the partner's answers.
- Produces: the permanent record — what died where and why, what shipped, and what reopening needs.

- [ ] **Step 1: Methodology rows.** Load `pooled-numbers`. Add three rows to the closed pre-registrations table, in the v104 rows' style, with no ALL-CAPS token in backticks unless it is a closed knob (`tests/hooks/test_guardrails.py` checks this):
  - **Part A — Downtrend Overbought Fade on 1w (v113):** the stage it ended at; per `m` the TRAIN N / WR / ExpR / lower bound; the plateau and winner; folds; the holdout outcome. If it shipped: the live-parity mechanics (limit entry next session only with first-print gap fill, whole-position target, time stop from 15:45 ET on the 7th session after the fill, live earnings calendar) and the one known live/backtest difference (a mid-session restart treats its first regular-hours print as the open). If V113-20 … V113-24 were skipped, say so. What reopening needs if it failed (a new mechanism, not another `m`).
  - **Part B — 22 legacy cells on 1w (v113):** how many cells ended at Stage 1, Stage 2, holdout pass / fail / sealed-thin; the passing pairs with TRAIN and holdout figures; which empty cells are arithmetic (cap-bind or floor-drop) rather than market verdicts.
  - **Part D — inverse-ETF longs (v113):** the pooled TRAIN and holdout figures; the survivors of the liquidity filter; whether shipped, sealed-thin (retry date) or failed; the partner's population choice if it shipped.

- [ ] **Step 2: Strategy docs.**
  - Create `docs/strategy-types/downtrend-overbought-fade.md` in the existing page format (idea, entry rule, plan, measured, pseudocode), sourced from `short_entries.py`, `short_builders.py` and the Part A results; if it shipped, a "Live" section with the resting orders and the live-parity mechanics.
  - `shared-mechanics.md`: a section "The 1w horizon and `cells` (v113)" — the horizon values, masked-by-default, `admits`, `live_horizons`, the strategy-plan reward floor, the limit entry type and its fill-bar rule, and (if V113-22/23 ran) the plan-level fields `entry_type "limit"`, `tp1_fraction 1.0` and `time_stop_bars` in `PlanManager`.
  - Each Part B strategy page: a `## Measured` line with its two 1w cells' TRAIN figures and outcome.
  - `README.md`: add the fade to the table.

- [ ] **Step 3: Commit on `main`**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py tests/hooks/test_codex_mirror.py`
Expected: PASS. If the Codex mirror test fails because of the methodology edit, mirror it into `AGENTS.md` per `docs/claude/working-conventions.md` § Codex mirror and stage `AGENTS.md` too.

```bash
git add docs/claude/backtest-methodology.md docs/strategy-types/
git commit -m "docs(v113): methodology rows and strategy-type pages -- A <outcome>, B <k>/22, D <outcome>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-27: Full-suite verification, release, production watchlist, close-out

**Files:**
- Modify (only if something shipped): `VERSION.json`, `swingbot/admin/version_history.json`, `data/watchlist.json` (mirror of production, D only)

**Interfaces:**
- Consumes: everything above, on `main`.
- Produces: a green suite; a `bot minor` release if V113-18, V113-24 or V113-25 shipped; the plan moved to `implemented/`.

- [ ] **Step 1: Full suite, once.** Dispatch `test-runner` for `python scripts/dev/testrun.py full` on `main`. Require `0 failed` and `0 xfailed`. If V113-18 or V113-24 touched `frontend/`, also run `npm --prefix frontend test` once. **If either is not green, fix forward from those failures** — they are this plan's regressions. A failure that passes in isolation and sits in code v113 never touched is reported with both outputs; the suite is not called green.

- [ ] **Step 2: Close out.** Invoke `/close-out v113`. It resolves the bump from the then-current `VERSION.json`: `bot minor` if V113-18, V113-24 or V113-25 shipped anything, otherwise no release commit (Phase A's code is on `main` but inert). It regenerates `version_history.json` with any bump, moves the spec and all six plan files (`_0-index`, `_1a-horizon`, `_1b-fade`, `_1c-measure-script`, `_2-measurement`, `_3-ship`) to `implemented/` (the code reached `main` either way), and removes the worktrees. Add the spec Status line: `**Status:** <Shipped <list> | Closed no-lift> <date>; holdout spent: <list>; sealed-thin: <list or none>; A: <outcome>.`

- [ ] **Step 3 (only if Part D shipped): the production watchlist.** Load `mirror-prod`. Deploy the release first (`deploy` skill) so the inverse tag, RS exemption and measured-population filter are live before any ETF is scanned. Then ask the partner (`AskUserQuestion`: "Add SH, PSQ, RWM and DOG to the production watchlist now? (recommended: yes — the tag and filters are deployed)") — real money trades from these alerts. On yes:

```bash
bash scripts/ops/ssh-hetzner.sh "test -f /opt/swing-bot/data/universe/inverse_etfs.json && echo manifest-ok"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot.core.marketdata.watchlist import add_ticker; [add_ticker(t) for t in (\"SH\", \"PSQ\", \"RWM\", \"DOG\")]; print(\"added\")'"
```

(`cd` here runs on the VM inside the quoted remote command, not in this shell.) If `manifest-ok` is missing, stop: the tag would be absent live. Then mirror: add the four tickers to `data/watchlist.json` in the repo (keep its sort order) and commit `chore(v113): mirror production watchlist -- SH, PSQ, RWM, DOG` with the trailer.

- [ ] **Step 4 (only if the fade shipped): deploy check.** If D did not already trigger a deploy in Step 3, deploy the release (`deploy` skill) so the fade's live parity code is running, then confirm read-only with `prod-inspector` that the bot log shows a strategy pass completing without `earnings context unavailable` warnings for the watchlist.

- [ ] **Step 5: Remember sealed-thin shots.** If any candidate is `sealed-thin`, write a project memory: the candidate list, "retry once when HOLDOUT_END ≥ 2026-12-31", and the V113-17 Step 2 command for each. Otherwise no session will remember the shot.
