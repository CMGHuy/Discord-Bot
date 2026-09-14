# v86 — Part 1: the cohort registry (C1–C3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-14-v86-cohort-risk-label-design.md` (§3)
**Index (read its Global Constraints first):** `2026-09-14-v86-cohort-risk-label_0-index.md`

---

### Task C1: The cohort registry module

Pure arithmetic plus a loader that mirrors `validation_registry.py`'s contract.
No I/O beyond reading the committed JSON; no scan, plan or backtest code is
touched by this task.

**Files:**
- Create: `swingbot/core/backtesting/cohort_registry.py`
- Create: `tests/test_cohort_registry.py`

**Interfaces:**
- Consumes: `swingbot.core.edge.regime2.REGIMES` (the four state strings).
- Produces:
  - `K = 100`, `N_FLOOR = 50`, `BAND_R = 0.15` — module constants.
  - `cohort_key(direction: str, regime2_state: str) -> str` → `"bullish|bull_quiet"`.
  - `blend(p_live: float | None, n_live: int, p_backtest: float, K: int = K) -> float`.
  - `@dataclass Cohort`: `label: str`, `n_live: int`, `n_backtest: int`,
    `win_rate: float`, `expectancy_r: float`, `window: str`, `run_date: str`.
  - `band(expectancy_r: float, pool_mean_r: float) -> str` → one of
    `COHORT_POOR` / `COHORT_TYPICAL` / `COHORT_STRONG`.
  - `load_registry(path: Path | None = None) -> dict`, `reload_registry() -> None`.
  - `get_cohort(direction: str, regime2_state: str | None) -> Cohort`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cohort_registry.py`:

```python
import json
import pytest

from swingbot.core.backtesting import cohort_registry as cr


def test_blend_with_no_live_data_is_the_backtest_prior():
    assert cr.blend(None, 0, 0.40) == pytest.approx(0.40)


def test_blend_at_k_live_trades_is_the_midpoint():
    # n_live == K -> exactly half live, half prior
    assert cr.blend(0.60, cr.K, 0.40) == pytest.approx(0.50)


def test_blend_far_past_k_is_dominated_by_live():
    assert cr.blend(0.60, cr.K * 99, 0.40) == pytest.approx(0.598, abs=1e-3)


def test_band_poor_typical_strong_at_the_boundaries():
    pool = -0.136
    assert cr.band(pool - cr.BAND_R, pool) == "COHORT_POOR"
    assert cr.band(pool - cr.BAND_R + 1e-9, pool) == "COHORT_TYPICAL"
    assert cr.band(pool, pool) == "COHORT_TYPICAL"
    assert cr.band(pool + cr.BAND_R, pool) == "COHORT_STRONG"


def test_cohort_key_shape():
    assert cr.cohort_key("bullish", "bear_volatile") == "bullish|bear_volatile"


def _write_registry(tmp_path, cells, pool_mean_r=-0.136):
    path = tmp_path / "cohort_registry.json"
    path.write_text(json.dumps({
        "run_date": "2026-09-14", "window": "TRAIN+LIVE",
        "pool_mean_r": pool_mean_r, "cells": cells,
    }), encoding="utf-8")
    return path


def test_thin_cell_resolves_to_unknown(tmp_path):
    path = _write_registry(tmp_path, {
        "bullish|bull_quiet": {"n_live": 10, "n_backtest": 20,
                               "win_rate_live": 50.0, "win_rate_backtest": 50.0,
                               "expectancy_r_live": 0.0, "expectancy_r_backtest": 0.0},
    })
    cr.load_registry(path)
    c = cr.get_cohort("bullish", "bull_quiet")
    assert c.label == "COHORT_UNKNOWN"


def test_fat_poor_cell_is_labelled_poor(tmp_path):
    path = _write_registry(tmp_path, {
        "bearish|bear_volatile": {"n_live": 100, "n_backtest": 500,
                                  "win_rate_live": 41.0, "win_rate_backtest": 41.4,
                                  "expectancy_r_live": -0.38, "expectancy_r_backtest": -0.38},
    })
    cr.load_registry(path)
    c = cr.get_cohort("bearish", "bear_volatile")
    assert c.label == "COHORT_POOR"
    assert c.n_live == 100 and c.n_backtest == 500
    assert c.expectancy_r == pytest.approx(-0.38, abs=1e-6)
    assert c.run_date == "2026-09-14"


def test_missing_cell_resolves_to_unknown(tmp_path):
    cr.load_registry(_write_registry(tmp_path, {}))
    assert cr.get_cohort("bullish", "bull_quiet").label == "COHORT_UNKNOWN"


def test_none_regime_resolves_to_unknown(tmp_path):
    cr.load_registry(_write_registry(tmp_path, {}))
    assert cr.get_cohort("bullish", None).label == "COHORT_UNKNOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_cohort_registry.py`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.backtesting.cohort_registry`

- [ ] **Step 3: Write minimal implementation**

Create `swingbot/core/backtesting/cohort_registry.py`:

```python
"""Cohort registry: how trades under given conditions have ACTUALLY closed.

Sibling of validation_registry.py, and deliberately a different question.
That one answers "has this strategy passed a pre-registration?" (a badge).
This one answers "what is the measured base rate for a setup shaped like
this one?" -- a LOOKUP, not a score. That distinction is load-bearing:
v32 and v33 both regressed trying to fold signals into one confidence
number, so nothing here reweights anything.

The JSON is GENERATED by scripts/backtest/emit_cohort_registry.py and
committed. It is FROZEN at run_date: plans persist what they were told,
and the spec's §6 verification reads only plans created after that date.
Re-deriving the table on the fly would score trades against a table those
same trades built.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

K = 100            # Beta-binomial pseudo-count. Frozen, never grid-tuned:
                   # a tuned K is a fitted parameter wearing a prior's coat.
N_FLOOR = 50       # below this combined sample a cell says "unknown", never "safe"
BAND_R = 0.15      # +-R against the pool mean; frozen (spec §3.3)

_PATH = Path(__file__).with_name("cohort_registry.json")
_CACHE: dict | None = None


@dataclass
class Cohort:
    label: str
    n_live: int = 0
    n_backtest: int = 0
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    window: str = ""
    run_date: str = ""


def cohort_key(direction: str, regime2_state: str) -> str:
    return f"{direction}|{regime2_state}"


def blend(p_live: float | None, n_live: int, p_backtest: float, k: int = K) -> float:
    """Backtest is the prior, live is the update. n_live=0 -> pure prior;
    n_live=k -> midpoint; n_live>>k -> live. Same arithmetic for win rate
    and for ExpR, so the two can never tell different stories."""
    if p_live is None or n_live <= 0:
        return float(p_backtest)
    return (n_live * float(p_live) + k * float(p_backtest)) / (n_live + k)


def band(expectancy_r: float, pool_mean_r: float) -> str:
    """Relative, not absolute. The whole confluence pool is negative, so an
    absolute threshold would fire on nearly every alert and teach the
    reader to ignore the line."""
    if expectancy_r <= pool_mean_r - BAND_R:
        return "COHORT_POOR"
    if expectancy_r >= pool_mean_r + BAND_R:
        return "COHORT_STRONG"
    return "COHORT_TYPICAL"


def load_registry(path: Path | None = None) -> dict:
    global _CACHE
    if _CACHE is None or path is not None:
        src = path or _PATH
        _CACHE = json.loads(src.read_text(encoding="utf-8")) if src.exists() else {
            "run_date": "", "window": "", "pool_mean_r": 0.0, "cells": {},
        }
    return _CACHE


def reload_registry() -> None:
    global _CACHE
    _CACHE = None


def get_cohort(direction: str, regime2_state: str | None) -> Cohort:
    """Most-specific match, else COHORT_UNKNOWN. An absent registry file, an
    absent cell and a thin cell all land on UNKNOWN by design -- there is no
    path through this function that reports "safe" without the sample to
    back it."""
    if not regime2_state:
        return Cohort(label="COHORT_UNKNOWN")
    reg = load_registry()
    cell = (reg.get("cells") or {}).get(cohort_key(direction, regime2_state))
    if not cell:
        return Cohort(label="COHORT_UNKNOWN")

    n_live = int(cell.get("n_live", 0))
    n_backtest = int(cell.get("n_backtest", 0))
    win_rate = blend(cell.get("win_rate_live"), n_live, cell.get("win_rate_backtest", 0.0))
    expectancy_r = blend(cell.get("expectancy_r_live"), n_live,
                         cell.get("expectancy_r_backtest", 0.0))

    if n_live + n_backtest < N_FLOOR:
        label = "COHORT_UNKNOWN"
    else:
        label = band(expectancy_r, float(reg.get("pool_mean_r", 0.0)))

    return Cohort(label=label, n_live=n_live, n_backtest=n_backtest,
                  win_rate=win_rate, expectancy_r=expectancy_r,
                  window=reg.get("window", ""), run_date=reg.get("run_date", ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_cohort_registry.py`
Expected: PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/cohort_registry.py tests/test_cohort_registry.py
git commit -m "feat(v86): cohort registry module with shrinkage blend and banding"
```

---

### Task C2: The registry generator

Builds `cohort_registry.json` from both sources and commits it frozen. This is
the only task that reads the live book.

**Files:**
- Create: `scripts/backtest/emit_cohort_registry.py`
- Create: `swingbot/core/backtesting/cohort_registry.json` (generated output, committed)
- Create: `tests/test_emit_cohort_registry.py`

**Interfaces:**
- Consumes: `cohort_registry.cohort_key` (C1); `swingbot.core.edge.regime2.regime_series`;
  `swingbot.core.backtesting.backtest_scenarios.run_scenario_backtest`.
- Produces: `aggregate_cells(trades: list[dict], regimes) -> dict` — the pure
  function the test drives; the script's `main()` is a thin wrapper around it.

**Note for the implementer:** `backtest_scenarios.py` is a real historical
replay and takes tens of minutes. Per CLAUDE.md, dispatch the actual generation
run to the `backtest-runner` subagent and print flushed per-ticker progress.
The unit test below must NOT run a backtest — it drives `aggregate_cells` on a
fixture list.

- [ ] **Step 1: Write the failing test**

Create `tests/test_emit_cohort_registry.py`:

```python
import pandas as pd

from scripts.backtest.emit_cohort_registry import aggregate_cells


def _regimes():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    return pd.Series(["bull_quiet", "bear_volatile", "bear_volatile"], index=idx)


def test_aggregate_buckets_by_direction_and_regime():
    trades = [
        {"created_at": "2026-01-02", "direction": "bullish", "r_realized": 1.0},
        {"created_at": "2026-01-05", "direction": "bearish", "r_realized": -1.0},
        {"created_at": "2026-01-06", "direction": "bearish", "r_realized": -1.0},
    ]
    cells = aggregate_cells(trades, _regimes())
    assert cells["bullish|bull_quiet"]["n"] == 1
    assert cells["bearish|bear_volatile"]["n"] == 2
    assert cells["bearish|bear_volatile"]["win_rate"] == 0.0
    assert cells["bearish|bear_volatile"]["expectancy_r"] == -1.0


def test_trade_with_no_regime_for_its_date_is_dropped_not_guessed():
    trades = [{"created_at": "2019-01-01", "direction": "bullish", "r_realized": 1.0}]
    assert aggregate_cells(trades, _regimes()) == {}


def test_trade_missing_r_realized_is_dropped():
    trades = [{"created_at": "2026-01-02", "direction": "bullish", "r_realized": None}]
    assert aggregate_cells(trades, _regimes()) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_emit_cohort_registry.py`
Expected: FAIL — `ModuleNotFoundError: scripts.backtest.emit_cohort_registry`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/backtest/emit_cohort_registry.py`:

```python
#!/usr/bin/env python3
"""Emit swingbot/core/backtesting/cohort_registry.json (v86 spec §3).

Two sources, blended at READ time by cohort_registry.get_cohort -- this
script only writes each source's raw numbers, never the blend, so the
shrinkage constant stays in one place.

  backtest  confluence scenario replay (the prior; large N, wide regimes)
  live      data/trades.json closed paper trades (the update; real fills)

NO-LOOKAHEAD: a trade is bucketed by the regime label of ITS OWN creation
date, taken from a regime series computed over SPY history. regime_series
is causal at every bar (rolling windows only), so a 2024 trade can never
be labelled with 2025 volatility.

The output is FROZEN once committed. Regenerating it invalidates the
spec §6 pre-registration for every plan stamped from the old table --
if you regenerate, the verification window restarts at the new run_date.

Run: python scripts/backtest/emit_cohort_registry.py --live data/trades.json \
         --backtest data/confluence_replay.json --out swingbot/core/backtesting/cohort_registry.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from swingbot.core.backtesting.cohort_registry import cohort_key  # noqa: E402


def aggregate_cells(trades: list[dict], regimes: pd.Series) -> dict:
    """{cell_key: {n, win_rate, expectancy_r}} over one source's trades.

    A trade whose creation date has no regime label is DROPPED, not
    guessed -- the regime series needs 252 bars of history before it says
    anything, and inventing a label for the warm-up period would put
    fabricated rows in a table the reader is asked to trust.
    """
    buckets: dict[str, list[float]] = {}
    for t in trades:
        r = t.get("r_realized")
        if r is None:
            continue
        try:
            day = pd.Timestamp(t["created_at"]).normalize()
        except (KeyError, ValueError):
            continue
        idx = regimes.index.normalize()
        match = regimes[idx == day]
        if match.empty:
            continue
        buckets.setdefault(cohort_key(t["direction"], str(match.iloc[0])), []).append(float(r))

    cells = {}
    for key, rs in buckets.items():
        wins = sum(1 for r in rs if r > 0)
        cells[key] = {
            "n": len(rs),
            "win_rate": round(100.0 * wins / len(rs), 4),
            "expectancy_r": round(sum(rs) / len(rs), 6),
        }
    return cells


def _merge(live_cells: dict, backtest_cells: dict) -> dict:
    out = {}
    for key in set(live_cells) | set(backtest_cells):
        lv, bt = live_cells.get(key, {}), backtest_cells.get(key, {})
        out[key] = {
            "n_live": lv.get("n", 0),
            "win_rate_live": lv.get("win_rate"),
            "expectancy_r_live": lv.get("expectancy_r"),
            "n_backtest": bt.get("n", 0),
            "win_rate_backtest": bt.get("win_rate", 0.0),
            "expectancy_r_backtest": bt.get("expectancy_r", 0.0),
        }
    return out


def _pool_mean_r(live: list[dict], backtest: list[dict]) -> float:
    rs = [float(t["r_realized"]) for t in (live + backtest) if t.get("r_realized") is not None]
    return round(sum(rs) / len(rs), 6) if rs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True, help="data/trades.json")
    ap.add_argument("--backtest", required=True, help="confluence replay trades JSON")
    ap.add_argument("--spy", default="market_data/SPY.csv")
    ap.add_argument("--out", default="swingbot/core/backtesting/cohort_registry.json")
    args = ap.parse_args()

    from swingbot.core.edge.regime2 import regime_series

    spy = pd.read_csv(args.spy, index_col=0, parse_dates=True)
    regimes = regime_series(spy)

    live = [t for t in json.loads(Path(args.live).read_text(encoding="utf-8"))
            if t.get("source") == "confluence" and t.get("status") == "CLOSED"]
    backtest = json.loads(Path(args.backtest).read_text(encoding="utf-8"))
    print(f"live closed confluence trades: {len(live)}", flush=True)
    print(f"backtest replay trades: {len(backtest)}", flush=True)

    payload = {
        "run_date": dt.date.today().isoformat(),
        "window": "backtest TRAIN+VALIDATION replay, live book to run_date",
        "pool_mean_r": _pool_mean_r(live, backtest),
        "cells": _merge(aggregate_cells(live, regimes), aggregate_cells(backtest, regimes)),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(payload['cells'])} cells, "
          f"pool_mean_r={payload['pool_mean_r']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_emit_cohort_registry.py`
Expected: PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Generate the real registry**

Dispatch to the `backtest-runner` subagent (the replay is tens of minutes):

```bash
python scripts/data/fetch_backtest_data.py          # once, if the CSV cache is cold
python scripts/backtest/emit_cohort_registry.py \
    --live data/trades.json \
    --backtest data/confluence_replay.json \
    --out swingbot/core/backtesting/cohort_registry.json
```

Sanity-check the output before committing: 8 cells or fewer, `pool_mean_r`
within a few hundredths of −0.136 (the 2026-09-10 measurement), and every
`n_backtest` in the hundreds. A `pool_mean_r` far from that figure means the
backtest input is not the confluence pool — stop and re-derive rather than
committing a table the reader would trust.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/emit_cohort_registry.py tests/test_emit_cohort_registry.py \
        swingbot/core/backtesting/cohort_registry.json
git commit -m "feat(v86): emit the frozen cohort registry from backtest + live book"
```

---

### Task C3: Stamp the cohort onto every plan

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (new dataclass fields)
- Modify: `swingbot/core/planning/params.py` (add `stamp_cohort`)
- Modify: `swingbot/core/planning/builders.py:257-320` (`build_confluence_plan`)
- Modify: `swingbot/core/planning/plan_engine.py` (re-export)
- Create: `tests/test_cohort_stamp.py`

**Interfaces:**
- Consumes: `cohort_registry.get_cohort` (C1).
- Produces:
  - `TradePlanV2.cohort_label: str = "COHORT_UNKNOWN"`,
    `TradePlanV2.cohort_stats: dict = field(default_factory=dict)`.
  - `params.stamp_cohort(plan: TradePlanV2, regime2_state: str | None) -> None`.
  - `build_confluence_plan(..., regime2_state: str | None = None)` — new
    keyword-only argument, defaulting to `None` so every existing caller keeps
    working and lands on `COHORT_UNKNOWN`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cohort_stamp.py`:

```python
import json

import pytest

from swingbot.core.backtesting import cohort_registry as cr
from swingbot.core.planning.plan_types import (TradePlanV2, PlanStatus,
                                               plan_to_dict, plan_from_dict)
from swingbot.core.planning.params import stamp_cohort


@pytest.fixture
def poor_registry(tmp_path):
    path = tmp_path / "cohort_registry.json"
    path.write_text(json.dumps({
        "run_date": "2026-09-14", "window": "TRAIN+LIVE", "pool_mean_r": -0.136,
        "cells": {"bearish|bear_volatile": {
            "n_live": 100, "n_backtest": 500,
            "win_rate_live": 41.0, "win_rate_backtest": 41.4,
            "expectancy_r_live": -0.38, "expectancy_r_backtest": -0.38}},
    }), encoding="utf-8")
    cr.load_registry(path)
    yield
    cr.reload_registry()


def _plan(direction="bearish"):
    return TradePlanV2(
        plan_id="p1", ticker="AAPL", created_at="2026-09-14", source="confluence",
        strategy="RSI", horizon_key="2w", direction=direction, entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=98.0,
        tp1=104.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
        trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK",
        badge_stats={}, status=PlanStatus.PENDING,
    )


def test_plan_defaults_to_unknown_before_stamping():
    assert _plan().cohort_label == "COHORT_UNKNOWN"
    assert _plan().cohort_stats == {}


def test_stamp_marks_a_poor_cohort_and_records_what_it_was_told(poor_registry):
    plan = _plan()
    stamp_cohort(plan, "bear_volatile")
    assert plan.cohort_label == "COHORT_POOR"
    assert plan.cohort_stats["run_date"] == "2026-09-14"
    assert plan.cohort_stats["n_live"] == 100
    assert plan.cohort_stats["n_backtest"] == 500
    assert plan.cohort_stats["expectancy_r"] == pytest.approx(-0.38, abs=1e-6)
    assert plan.cohort_stats["regime2_state"] == "bear_volatile"


def test_stamp_without_a_regime_is_unknown_not_a_guess(poor_registry):
    plan = _plan()
    stamp_cohort(plan, None)
    assert plan.cohort_label == "COHORT_UNKNOWN"


def test_cohort_survives_a_json_round_trip(poor_registry):
    plan = _plan()
    stamp_cohort(plan, "bear_volatile")
    back = plan_from_dict(json.loads(json.dumps(plan_to_dict(plan))))
    assert back.cohort_label == "COHORT_POOR"
    assert back.cohort_stats["n_backtest"] == 500


def test_a_plan_persisted_before_v86_still_loads():
    # plan_from_dict drops unknown keys and defaults missing ones -- an old
    # plans.json row has no cohort_* fields at all and must not raise.
    d = plan_to_dict(_plan())
    d.pop("cohort_label")
    d.pop("cohort_stats")
    assert plan_from_dict(d).cohort_label == "COHORT_UNKNOWN"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_cohort_stamp.py`
Expected: FAIL — `ImportError: cannot import name 'stamp_cohort'`

- [ ] **Step 3a: Add the plan fields**

In `swingbot/core/planning/plan_types.py`, inside the `TradePlanV2` dataclass,
after the `stop_mult_applied` field (all new fields need defaults — they follow
fields that already have them):

```python
    # v86: the frozen cohort verdict this plan was stamped with at issuance,
    # and the numbers behind it. Persisted like badge_stats so the spec's §6
    # verification can read what each plan was TOLD, not what the registry
    # says today -- the registry may be regenerated; this row may not.
    cohort_label: str = "COHORT_UNKNOWN"
    cohort_stats: dict = field(default_factory=dict)
```

- [ ] **Step 3b: Add `stamp_cohort`**

In `swingbot/core/planning/params.py`, beside `stamp_badge`:

```python
def stamp_cohort(plan: TradePlanV2, regime2_state: str | None) -> None:
    """Set cohort_label + cohort_stats from the committed cohort registry.

    Mirrors stamp_badge, with one deliberate difference: regime2_state is
    passed in rather than derived here. The regime belongs to the BAR that
    created the plan (scanning/analyze.py owns that context); deriving it
    at stamp time would read today's SPY for a plan built on an older bar
    -- a lookahead bug in the backtest replay and simply wrong in a
    catch-up scan.
    """
    from swingbot.core.backtesting.cohort_registry import get_cohort
    c = get_cohort(plan.direction, regime2_state)
    plan.cohort_label = c.label
    plan.cohort_stats = {
        "label": c.label, "regime2_state": regime2_state,
        "n_live": c.n_live, "n_backtest": c.n_backtest,
        "win_rate": c.win_rate, "expectancy_r": c.expectancy_r,
        "window": c.window, "run_date": c.run_date,
    }
```

- [ ] **Step 3c: Wire it into the confluence constructor**

In `swingbot/core/planning/builders.py`, add the keyword-only argument to
`build_confluence_plan`'s signature:

```python
def build_confluence_plan(scenario, df, *, ticker, horizon_key,
                          primary_strategy, level_map=None,
                          quality_inputs=None, params=None,
                          regime2_state=None) -> TradePlanV2 | None:
```

and stamp immediately after the badge, before `_apply_quality`:

```python
    plan_params.stamp_badge(plan)
    plan_params.stamp_cohort(plan, regime2_state)
    plan_params._apply_quality(plan, quality_inputs)
```

- [ ] **Step 3d: Re-export**

In `swingbot/core/planning/plan_engine.py`, add `stamp_cohort` to the
`from .params import (...)` list and to `__all__`, next to `stamp_badge`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_cohort_stamp.py`
Then confirm nothing that builds plans regressed:
Run: `python scripts/dev/testrun.py file tests/test_plan_engine.py`
Expected: both PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_types.py swingbot/core/planning/params.py \
        swingbot/core/planning/builders.py swingbot/core/planning/plan_engine.py \
        tests/test_cohort_stamp.py
git commit -m "feat(v86): stamp the frozen cohort verdict onto every confluence plan"
```
