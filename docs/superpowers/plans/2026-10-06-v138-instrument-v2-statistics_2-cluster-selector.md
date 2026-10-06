# v138 Instrument v2, phase 4: Statistics. Part 2: Phase B, IS4-IS7

> Part of `2026-10-06-v138-instrument-v2-statistics_0-index.md` (header, where to work, global constraints, file map, review focus and `## Parallelisation` live there). Read that index's Global Constraints with every task. Steps use `- [ ]` for tracking. All paths are relative to the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v138-instrument-v2-statistics` unless a command names an absolute path.

# Phase B: the `cluster` selector on every verdict path

### Task IS4: Pin the ticker-cluster verdict paths (v1 golden digests)

A characterization test: it passes on unmodified code by design. Its job is to fail if IS5–IS7 move the v1 path by one bit.

**Files:**
- Create: `tests/backtesting/_cluster_fixture.py`
- Create: `tests/backtesting/test_ticker_cluster_pin.py`

**Interfaces:**
- Consumes: `acceptance.cluster_bootstrap`, `acceptance.evaluate`, `acceptance.render_json`, `acceptance.mde_paired`, `acceptance.delta_standardised_win_rate`, `acceptance.delta_expectancy_r`, `acceptance_harvest.evaluate_harvest`, `funnel.score_cell`, `selection.evaluate_cell`, `harvest_select._row` (all exist at `6485b8bb`).
- Produces: `tests.backtesting._cluster_fixture.pinned_arms() -> tuple[list[ArmTrade], list[ArmTrade]]` (180 baseline trades over 12 tickers and 14 ISO weeks; a component that drops some and flips some), and `FAST = dict(n_resamples=300, seed=42)`. IS5, IS6 and IS7 import both.

- [ ] **Step 1: Confirm the code under pin is unmodified**

Run: `git log --oneline 6485b8bb..HEAD -- swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/acceptance_harvest.py swingbot/core/backtesting/arms/selection.py scripts/backtest/funnel.py scripts/backtest/harvest_select.py`
Expected: no output. If a commit is listed, someone changed a pinned file after this plan was written. Do **not** paste the digests below; instead run Step 3's test once, read each failing digest's actual value from the assertion message, replace the `PINNED` values with them, and state in the commit message the HEAD they were taken at. That is still a pin of unmodified v1, because IS5 has not run yet. Never do this after IS5.

- [ ] **Step 2: Write the fixture**

Create `tests/backtesting/_cluster_fixture.py`:

```python
"""Shared pinned arms for the v138 cluster-unit tests (not a test module).

12 tickers x 15 trades over 120 calendar days (14 ISO weeks), win R varying
by ticker so neither clustering unit is degenerate. The component drops the
trades where (t * k) % 7 == 0 and flips some losses to wins."""
from datetime import date, timedelta

from swingbot.core.backtesting.acceptance import ArmTrade

FAST = dict(n_resamples=300, seed=42)


def _arm(t, day, win):
    entry = date(2021, 1, 4) + timedelta(days=day)
    return ArmTrade(ticker=f"T{t}", strategy="MACD", horizon_key="3m",
                    entry_date=entry.isoformat(), outcome="win" if win else "loss",
                    r_multiple=(1.0 + 0.5 * (t % 4)) if win else -1.0,
                    planned_rr=2.0, direction="bullish")


def pinned_arms():
    base, comp = [], []
    for t in range(12):
        for k in range(15):
            day = (t * 5 + k * 3) % 120
            base.append(_arm(t, day, (t + k) % 3 == 0))
            if (t * k) % 7 != 0:
                comp.append(_arm(t, day, (t + k) % 3 == 0 or k % 5 == 1))
    return base, comp
```

- [ ] **Step 3: Write the pin test**

Create `tests/backtesting/test_ticker_cluster_pin.py`:

```python
"""Instrument v1 stays byte-identical (v136 cross-cutting rule 1).

sha256 digests of every ticker-cluster verdict path, taken on main at
6485b8bb (2026-10-06), BEFORE the v138 cluster selector existed. The
selector's default (cluster="ticker") must reproduce them exactly. Never
re-pin to make a failure go away: a mismatch means v1 moved."""
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

import funnel  # noqa: E402
import harvest_select  # noqa: E402

from swingbot.core.backtesting import acceptance, acceptance_harvest  # noqa: E402
from swingbot.core.backtesting.arms import selection  # noqa: E402
from tests.backtesting._cluster_fixture import FAST, pinned_arms  # noqa: E402

PINNED = {
    "cluster_bootstrap": "5a65607553c5f4d9faf84fe9e2fb104c4f295e3dc0dabc7c83c173c1d25894bc",
    "evaluate": "4e6900f17ad39f1487623dd0873dba87506f1c844fe62a61030e8582ea33681c",
    "evaluate_harvest": "1f40f41dc0b2a71b327f7b6e8c7fb4f8b336efb4d9e559b4d5d8b8e0f27e0c2f",
    "mde_paired": "0.036552475366009286",
    "score_cell": "04018d1c1d19213593ef440edb989f046764ca0047550cc17fd0d0227d68f27d",
    "evaluate_cell": "588d69e2a1a5bbc5911cc1c5c9113f1973de29d0cda23cda9e15d31a04c6c915",
    "harvest_row": "d760a4d98d502f492e272895b6584f57a9c569611fb1fa4ba21e2b594534aa22",
}


def _digest(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def test_cluster_bootstrap_draws():
    b, c = pinned_arms()
    draws = acceptance.cluster_bootstrap(b, c, acceptance.delta_standardised_win_rate,
                                         **FAST)
    assert hashlib.sha256(draws.tobytes()).hexdigest() == PINNED["cluster_bootstrap"]


def test_evaluate_rendering():
    b, c = pinned_arms()
    result = acceptance.evaluate(b, c, stage="walkforward", **FAST)
    assert _digest(acceptance.render_json(result)) == PINNED["evaluate"]


def test_evaluate_harvest_rendering():
    b, c = pinned_arms()
    result = acceptance_harvest.evaluate_harvest(b, c, stage="walkforward", **FAST)
    assert _digest(acceptance.render_json(result)) == PINNED["evaluate_harvest"]


def test_mde_paired_value():
    b, c = pinned_arms()
    value = acceptance.mde_paired(b, c, acceptance.delta_expectancy_r,
                                  observed_n=len(c), target_n=1000, **FAST)
    assert repr(value) == PINNED["mde_paired"]


def test_funnel_score_cell():
    _, c = pinned_arms()
    rows = [dataclasses.asdict(t) for t in c]
    assert _digest(funnel.score_cell(rows, 30, **FAST)) == PINNED["score_cell"]


def test_selection_evaluate_cell():
    b, c = pinned_arms()
    cell = selection.evaluate_cell(0.1, b, c, resolvable=True, **FAST)
    assert _digest(dataclasses.asdict(cell)) == PINNED["evaluate_cell"]


def test_harvest_select_row():
    b, c = pinned_arms()
    assert _digest(harvest_select._row(0.1, b, c, set())) == PINNED["harvest_row"]
```

- [ ] **Step 4: Run it on unmodified code**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_ticker_cluster_pin.py`
Expected: PASS, 7 passed. (It takes a few seconds: `harvest_select._row` runs the default 10,000 resamples.)

- [ ] **Step 5: Commit**

```bash
git add tests/backtesting/_cluster_fixture.py tests/backtesting/test_ticker_cluster_pin.py
git commit -m "test(v138): pin every ticker-cluster verdict path before the cluster selector"
```

---

### Task IS5: `cluster` selector in `acceptance.py`

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py` (around `BootstrapResult`, `cluster_bootstrap`, `bootstrap_delta`, `mde_paired`, `AcceptanceResult`, `_clause_win_rate`, `_clause_profit_floor`, `evaluate`, `render_json`, `render_markdown`)
- Test: `tests/backtesting/test_acceptance_cluster_unit.py`

**Interfaces:**
- Consumes: `stats.week_cluster_bootstrap` (IS1), `pinned_arms`/`FAST` (IS4).
- Produces (later tasks pass `cluster=` by keyword):
  - `CLUSTER_UNITS = ("ticker", "week")`; `_check_cluster(cluster: str) -> None` raises `ValueError` naming `cluster`.
  - `cluster_bootstrap(baseline, component, statistic, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42, cluster: str = "ticker") -> np.ndarray`
  - `bootstrap_delta(..., *, n_resamples=..., seed=42, cluster: str = "ticker") -> BootstrapResult`
  - `mde_paired(..., seed=42, cluster: str = "ticker") -> float | None`
  - `evaluate(baseline, component, *, stage, permutation_p=None, n_resamples=..., seed=42, cluster: str = "ticker") -> AcceptanceResult`
  - `AcceptanceResult.cluster: str = "ticker"` (last field).
  - `render_json(result)` adds `"cluster": result.cluster` **only** when it is not `"ticker"`; `render_markdown` adds `", clustered by ISO week of entry date"` after the seed **only** for `"week"`.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_acceptance_cluster_unit.py`:

```python
"""v136 §4: every v2 verdict resamples ISO entry weeks; v1 keeps tickers.
The unit is a plain parameter; phase 6 maps --instrument v2 to it."""
import numpy as np
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.instrument import stats
from tests.backtesting._cluster_fixture import FAST, pinned_arms


def test_cluster_units_are_ticker_and_week():
    assert acceptance.CLUSTER_UNITS == ("ticker", "week")


def test_week_unit_delegates_to_the_instrument_stats_bootstrap():
    b, c = pinned_arms()
    via_gate = acceptance.cluster_bootstrap(
        b, c, acceptance.delta_standardised_win_rate, cluster="week", **FAST)
    direct = stats.week_cluster_bootstrap(
        b, c, acceptance.delta_standardised_win_rate, **FAST)
    assert np.array_equal(via_gate, direct)


def test_week_and_ticker_units_draw_differently():
    b, c = pinned_arms()
    by_ticker = acceptance.cluster_bootstrap(b, c, acceptance.delta_expectancy_r, **FAST)
    by_week = acceptance.cluster_bootstrap(b, c, acceptance.delta_expectancy_r,
                                           cluster="week", **FAST)
    assert not np.array_equal(by_ticker, by_week)


@pytest.mark.parametrize("bad", ["Ticker", "day", ""])
def test_an_unknown_unit_is_refused(bad):
    b, c = pinned_arms()
    with pytest.raises(ValueError, match="cluster"):
        acceptance.cluster_bootstrap(b, c, acceptance.delta_expectancy_r,
                                     cluster=bad, **FAST)


def test_bootstrap_delta_threads_the_unit():
    b, c = pinned_arms()
    by_ticker = acceptance.bootstrap_delta(b, c, acceptance.delta_expectancy_r, **FAST)
    by_week = acceptance.bootstrap_delta(b, c, acceptance.delta_expectancy_r,
                                         cluster="week", **FAST)
    assert by_ticker.point == by_week.point   # the point estimate is unit-free
    assert (by_ticker.lo, by_ticker.hi) != (by_week.lo, by_week.hi)


def test_mde_paired_threads_the_unit():
    b, c = pinned_arms()
    kw = dict(observed_n=len(c), target_n=1000, **FAST)
    by_ticker = acceptance.mde_paired(b, c, acceptance.delta_expectancy_r, **kw)
    by_week = acceptance.mde_paired(b, c, acceptance.delta_expectancy_r,
                                    cluster="week", **kw)
    assert by_ticker != by_week


def test_evaluate_records_and_renders_the_week_unit():
    b, c = pinned_arms()
    result = acceptance.evaluate(b, c, stage="walkforward", cluster="week", **FAST)
    assert result.cluster == "week"
    assert acceptance.render_json(result)["cluster"] == "week"
    text = acceptance.render_markdown(result, title="t", window="w")
    assert "bootstrap seed 42, clustered by ISO week of entry date." in text


def test_evaluate_refuses_an_unknown_unit_before_scoring():
    b, c = pinned_arms()
    with pytest.raises(ValueError, match="cluster"):
        acceptance.evaluate(b, c, stage="walkforward", cluster="weekly", **FAST)


def test_ticker_default_keeps_the_v1_rendering():
    b, c = pinned_arms()
    result = acceptance.evaluate(b, c, stage="walkforward", **FAST)
    assert result.cluster == "ticker"
    assert "cluster" not in acceptance.render_json(result)
    text = acceptance.render_markdown(result, title="t", window="w")
    assert "bootstrap seed 42." in text
    assert "clustered by" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_cluster_unit.py`
Expected: FAIL, `AttributeError: module ... has no attribute 'CLUSTER_UNITS'`.

- [ ] **Step 3: Add the unit constants**

In `swingbot/core/backtesting/acceptance.py`, directly after

```python
BOOTSTRAP_RESAMPLES = 10_000
ALPHA = 0.05
```

insert:

```python

#: Resampling units the cluster bootstrap accepts (v136 §4). "ticker" is
#: instrument v1 and stays the default, byte-identical; "week" is the v2 unit
#: (ISO week of entry date, across every ticker). This module never reads the
#: instrument contract: phase 6 maps --instrument v2 to cluster="week".
CLUSTER_UNITS = ("ticker", "week")

#: The results-doc wording per unit; empty for ticker so v1 docs never change.
_CLUSTER_NOTES = {"ticker": "", "week": ", clustered by ISO week of entry date"}


def _check_cluster(cluster: str) -> None:
    if cluster not in CLUSTER_UNITS:
        raise ValueError(f"cluster must be one of {CLUSTER_UNITS}, got {cluster!r}")
```

- [ ] **Step 4: Branch `cluster_bootstrap` without touching its ticker body**

Replace the signature and the docstring's closing lines

```python
def cluster_bootstrap(baseline, component, statistic, *,
                      n_resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = 42) -> np.ndarray:
```

with

```python
def cluster_bootstrap(baseline, component, statistic, *,
                      n_resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = 42, cluster: str = "ticker") -> np.ndarray:
```

and, inside the same function, replace

```python
    zero is a specific, wrong claim about it.
    """
    b_by, c_by = _group_by_ticker(baseline), _group_by_ticker(component)
```

with

```python
    zero is a specific, wrong claim about it.

    ``cluster="week"`` resamples ISO weeks of entry date instead (v136 §4,
    instrument v2) through ``instrument.stats.week_cluster_bootstrap``, with
    the same pairing and draw-dropping contract. The ticker body below is
    instrument v1 and must stay byte-identical.
    """
    _check_cluster(cluster)
    if cluster == "week":
        from .instrument.stats import week_cluster_bootstrap  # lazy: no cycle
        return week_cluster_bootstrap(baseline, component, statistic,
                                      n_resamples=n_resamples, seed=seed)
    b_by, c_by = _group_by_ticker(baseline), _group_by_ticker(component)
```

Everything after that line in `cluster_bootstrap` stays exactly as it is.

- [ ] **Step 5: Thread `cluster` through `bootstrap_delta` and `mde_paired`**

Replace

```python
def bootstrap_delta(baseline, component, statistic, *,
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> BootstrapResult:
```

with

```python
def bootstrap_delta(baseline, component, statistic, *,
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42, cluster: str = "ticker") -> BootstrapResult:
```

and inside it replace

```python
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed)
    if point is None or draws.size == 0:
```

with

```python
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed, cluster=cluster)
    if point is None or draws.size == 0:
```

In `mde_paired`, replace

```python
               n_resamples: int = BOOTSTRAP_RESAMPLES,
               seed: int = 42) -> float | None:
```

with

```python
               n_resamples: int = BOOTSTRAP_RESAMPLES,
               seed: int = 42, cluster: str = "ticker") -> float | None:
```

and inside it replace

```python
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed)
    if draws.size < 2:
```

with

```python
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed, cluster=cluster)
    if draws.size < 2:
```

- [ ] **Step 6: Record the unit on the result**

In `class AcceptanceResult`, replace

```python
    seed: int = 42          # recorded so a results doc is reproducible
    version: int = VERSION
```

with

```python
    seed: int = 42          # recorded so a results doc is reproducible
    version: int = VERSION
    cluster: str = "ticker"  # bootstrap resampling unit (v136 §4)
```

- [ ] **Step 7: Thread `cluster` through the two bootstrap clauses and `evaluate`**

Replace

```python
def _clause_win_rate(baseline, component, n_resamples, seed) -> ClauseResult:
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed)
```

with

```python
def _clause_win_rate(baseline, component, n_resamples, seed,
                     cluster: str = "ticker") -> ClauseResult:
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed, cluster=cluster)
```

Replace

```python
def _clause_profit_floor(baseline, component, n_resamples, seed) -> ClauseResult:
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed)
```

with

```python
def _clause_profit_floor(baseline, component, n_resamples, seed,
                         cluster: str = "ticker") -> ClauseResult:
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed, cluster=cluster)
```

In `evaluate`, replace

```python
             n_resamples: int = BOOTSTRAP_RESAMPLES,
             seed: int = 42) -> AcceptanceResult:
```

with

```python
             n_resamples: int = BOOTSTRAP_RESAMPLES,
             seed: int = 42, cluster: str = "ticker") -> AcceptanceResult:
```

then replace

```python
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    split = population_split(baseline, component)
    clauses = (
        _clause_win_rate(baseline, component, n_resamples, seed),
        _clause_profit_floor(baseline, component, n_resamples, seed),
```

with

```python
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    _check_cluster(cluster)
    split = population_split(baseline, component)
    clauses = (
        _clause_win_rate(baseline, component, n_resamples, seed, cluster),
        _clause_profit_floor(baseline, component, n_resamples, seed, cluster),
```

(`evaluate_harvest` has the same `if stage not in STAGES` lines; this replacement is in `acceptance.py` only, where the clause lines that follow make it unique.) Then, at the end of `evaluate`, replace

```python
                            split={k: len(v) if isinstance(v, list) else v
                                   for k, v in split.items()},
                            seed=seed)
```

with

```python
                            split={k: len(v) if isinstance(v, list) else v
                                   for k, v in split.items()},
                            seed=seed, cluster=cluster)
```

- [ ] **Step 8: Render the unit only when it is not v1's**

Replace the start of `render_json`

```python
def render_json(result: AcceptanceResult) -> dict:
    return {
        "acceptance_version": result.version,
```

with

```python
def render_json(result: AcceptanceResult) -> dict:
    out = {
        "acceptance_version": result.version,
```

and its end

```python
        "strata": [{**r, "stratum": list(r["stratum"])} for r in result.strata],
        "split": result.split,
    }
```

with

```python
        "strata": [{**r, "stratum": list(r["stratum"])} for r in result.strata],
        "split": result.split,
    }
    if result.cluster != "ticker":   # v1 output stays key-for-key identical
        out["cluster"] = result.cluster
    return out
```

In `render_markdown`, replace

```python
        f"bootstrap seed {result.seed}.",
```

with

```python
        f"bootstrap seed {result.seed}{_CLUSTER_NOTES[result.cluster]}.",
```

- [ ] **Step 9: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_cluster_unit.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_ticker_cluster_pin.py`
Expected: PASS, 7 passed (v1 unmoved).

Run each of these existing files: `tests/backtesting/test_acceptance_bootstrap.py`, `tests/backtesting/test_acceptance_gate.py`, `tests/backtesting/test_acceptance_render.py`, `tests/backtesting/test_acceptance_mde.py`, `tests/backtesting/test_acceptance_records.py`, `tests/backtesting/test_acceptance_v68_regression.py` with `python scripts/dev/testrun.py file <path>`.
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/backtesting/acceptance.py`
Expected: no output.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_cluster_unit.py
git commit -m "feat(v138): acceptance cluster unit -- ticker (v1 default) or ISO entry week (v2)"
```

---

### Task IS6: `cluster` selector in `acceptance_harvest.py`

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_harvest.py` (`_clause_expectancy_gain`, `_clause_win_rate_floor`, `evaluate_harvest`)
- Test: `tests/backtesting/test_acceptance_harvest_cluster_unit.py`

**Interfaces:**
- Consumes: `bootstrap_delta(..., cluster=)` and `AcceptanceResult.cluster` (IS5), `pinned_arms`/`FAST` (IS4).
- Produces: `evaluate_harvest(baseline, component, *, stage, structurally_immune_to_wr=False, permutation_p=None, n_resamples=..., seed=42, cluster: str = "ticker") -> AcceptanceResult` with `.cluster` set.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_acceptance_harvest_cluster_unit.py`:

```python
"""v136 §4: the harvest gate resamples ISO entry weeks under v2."""
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance_harvest import evaluate_harvest
from tests.backtesting._cluster_fixture import FAST, pinned_arms


def test_evaluate_harvest_records_and_uses_the_week_unit():
    b, c = pinned_arms()
    by_ticker = evaluate_harvest(b, c, stage="walkforward", **FAST)
    by_week = evaluate_harvest(b, c, stage="walkforward", cluster="week", **FAST)
    assert (by_ticker.cluster, by_week.cluster) == ("ticker", "week")
    assert (by_ticker.clause("expectancy_gain").detail
            != by_week.clause("expectancy_gain").detail)
    assert acceptance.render_json(by_week)["cluster"] == "week"
    assert "cluster" not in acceptance.render_json(by_ticker)


def test_win_rate_floor_threads_the_unit():
    b, c = pinned_arms()
    by_ticker = evaluate_harvest(b, c, stage="walkforward", **FAST)
    by_week = evaluate_harvest(b, c, stage="walkforward", cluster="week", **FAST)
    assert (by_ticker.clause("win_rate_floor").value
            != by_week.clause("win_rate_floor").value)


def test_an_unknown_unit_is_refused():
    b, c = pinned_arms()
    with pytest.raises(ValueError, match="cluster"):
        evaluate_harvest(b, c, stage="walkforward", cluster="day", **FAST)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_harvest_cluster_unit.py`
Expected: FAIL, `TypeError: evaluate_harvest() got an unexpected keyword argument 'cluster'`.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/acceptance_harvest.py`, replace

```python
def _clause_expectancy_gain(baseline, component, n_resamples, seed) -> ClauseResult:
```

with

```python
def _clause_expectancy_gain(baseline, component, n_resamples, seed,
                            cluster: str = "ticker") -> ClauseResult:
```

and inside it replace

```python
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.p_greater_than_zero is None:
        return ClauseResult("expectancy_gain", "FAIL",
```

with

```python
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed, cluster=cluster)
    if res.point is None or res.p_greater_than_zero is None:
        return ClauseResult("expectancy_gain", "FAIL",
```

Replace

```python
def _clause_win_rate_floor(baseline, component, n_resamples, seed, *,
                          structurally_immune: bool = False,
                          split: dict | None = None) -> ClauseResult:
```

with

```python
def _clause_win_rate_floor(baseline, component, n_resamples, seed, *,
                          structurally_immune: bool = False,
                          split: dict | None = None,
                          cluster: str = "ticker") -> ClauseResult:
```

and inside it replace

```python
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.lo is None:
        return ClauseResult("win_rate_floor", "FAIL",
```

with

```python
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed, cluster=cluster)
    if res.point is None or res.lo is None:
        return ClauseResult("win_rate_floor", "FAIL",
```

In `evaluate_harvest`, replace

```python
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> AcceptanceResult:
```

with

```python
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42, cluster: str = "ticker") -> AcceptanceResult:
```

then replace

```python
        _clause_expectancy_gain(baseline, component, n_resamples, seed),
        _clause_win_rate_floor(baseline, component, n_resamples, seed,
                              structurally_immune=structurally_immune_to_wr,
                              split=split),
```

with

```python
        _clause_expectancy_gain(baseline, component, n_resamples, seed, cluster),
        _clause_win_rate_floor(baseline, component, n_resamples, seed,
                              structurally_immune=structurally_immune_to_wr,
                              split=split, cluster=cluster),
```

and replace

```python
                            seed=seed, version=HARVEST_VERSION)
```

with

```python
                            seed=seed, version=HARVEST_VERSION, cluster=cluster)
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_harvest_cluster_unit.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_ticker_cluster_pin.py`, then `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_harvest.py`, then `python scripts/dev/testrun.py file tests/backtesting/test_harvest_stage_gates.py`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/backtesting/acceptance_harvest.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_harvest.py tests/backtesting/test_acceptance_harvest_cluster_unit.py
git commit -m "feat(v138): harvest gate takes the bootstrap cluster unit"
```

---

### Task IS7: `cluster` selector in the selection, funnel and harvest-select helpers

**Files:**
- Modify: `swingbot/core/backtesting/arms/selection.py` (`evaluate_cell`)
- Modify: `scripts/backtest/funnel.py` (`expr_lower_bound`, `score_cell`, `stage1`)
- Modify: `scripts/backtest/harvest_select.py` (`_row`, `select`)
- Test: `tests/backtesting/test_verdict_helpers_cluster_unit.py`

**Interfaces:**
- Consumes: `acceptance.evaluate(..., cluster=)`, `acceptance.cluster_bootstrap(..., cluster=)`, `acceptance.bootstrap_delta(..., cluster=)` (IS5); `stats.week_cluster_bootstrap` (IS1); `pinned_arms`/`FAST` (IS4).
- Produces:
  - `selection.evaluate_cell(value, baseline, component, *, resolvable, n_resamples, seed, mechanism=None, cluster: str = "ticker") -> CellEval`
  - `funnel.expr_lower_bound(rows, *, n_resamples=..., seed=BOOTSTRAP_SEED, cluster="ticker")`, `funnel.score_cell(rows, min_n, *, n_resamples=..., seed=..., cluster="ticker")`, `funnel.stage1(rows_by_cell, direction, grid, *, n_resamples=..., seed=..., cluster="ticker")`
  - `harvest_select._row(value, baseline, component, refused, cluster="ticker")`, `harvest_select.select(cells, *, param, less_aggressive, refused=(), cluster="ticker")`

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_verdict_helpers_cluster_unit.py`:

```python
"""v136 §4: every bootstrap-reading verdict helper takes the cluster unit."""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

import funnel  # noqa: E402
import harvest_select  # noqa: E402

from swingbot.core.backtesting import acceptance  # noqa: E402
from swingbot.core.backtesting.arms import selection  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from tests.backtesting._cluster_fixture import FAST, pinned_arms  # noqa: E402


def _rows():
    _, c = pinned_arms()
    return [dataclasses.asdict(t) for t in c]


def test_expr_lower_bound_uses_the_week_bootstrap():
    rows = _rows()
    trades = [SimpleNamespace(**row) for row in rows]
    draws = stats.week_cluster_bootstrap(
        [], trades, lambda _b, comp: acceptance.expectancy_r(comp), **FAST)
    expected = float(np.percentile(draws, 100 * acceptance.ALPHA / 2))
    assert funnel.expr_lower_bound(rows, cluster="week", **FAST) == expected
    assert funnel.expr_lower_bound(rows, **FAST) != expected


def test_score_cell_threads_the_unit():
    rows = _rows()
    scored = funnel.score_cell(rows, funnel.MIN_N_TRAIN, cluster="week", **FAST)
    assert scored["lower_bound"] == funnel.expr_lower_bound(rows, cluster="week", **FAST)


def test_stage1_threads_the_unit():
    rows = _rows()
    grid = (0.1, 0.25, 0.5)
    rows_by_cell = {funnel.cell_key(value): rows for value in grid}
    out = funnel.stage1(rows_by_cell, "bullish", grid, cluster="week", **FAST)
    expected = funnel.score_cell(funnel.dir_rows(rows, "bullish"), funnel.MIN_N_TRAIN,
                                 cluster="week", **FAST)["lower_bound"]
    assert out["cells"]["0.1"]["lower_bound"] == expected


def test_evaluate_cell_passes_the_unit_to_the_gate(monkeypatch):
    seen = []
    real = acceptance.evaluate

    def spy(*args, **kwargs):
        seen.append(kwargs.get("cluster"))
        return real(*args, **kwargs)

    monkeypatch.setattr(selection.acceptance, "evaluate", spy)
    b, c = pinned_arms()
    selection.evaluate_cell(0.1, b, c, resolvable=True, **FAST)
    selection.evaluate_cell(0.1, b, c, resolvable=True, cluster="week", **FAST)
    assert seen == ["ticker", "week"]


def test_harvest_select_passes_the_unit_to_the_bootstrap(monkeypatch):
    seen = []

    def fake_delta(_baseline, _component, _statistic, **kwargs):
        seen.append(kwargs.get("cluster"))
        return acceptance.BootstrapResult(0.1, 0.05, 0.2, 0.01, 1, 42)

    monkeypatch.setattr(harvest_select, "bootstrap_delta", fake_delta)
    b, c = pinned_arms()
    harvest_select._row(0.1, b, c, set())
    harvest_select.select([(0.1, b, c), (0.25, b, c)], param="b",
                          less_aggressive="larger", cluster="week")
    assert seen == ["ticker", "week", "week"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_verdict_helpers_cluster_unit.py`
Expected: FAIL, `TypeError: expr_lower_bound() got an unexpected keyword argument 'cluster'`.

- [ ] **Step 3: `arms/selection.py`**

Replace

```python
def evaluate_cell(value, baseline, component, *, resolvable, n_resamples, seed,
                  mechanism=None):
    """Score only clauses 2–4 and 6 plus the preceding MDE refusal."""
    result = acceptance.evaluate(baseline, component, stage='walkforward',
                                 n_resamples=n_resamples, seed=seed)
```

with

```python
def evaluate_cell(value, baseline, component, *, resolvable, n_resamples, seed,
                  mechanism=None, cluster='ticker'):
    """Score only clauses 2–4 and 6 plus the preceding MDE refusal.

    ``cluster`` is the bootstrap unit (v136 §4): 'ticker' for instrument v1,
    'week' for v2."""
    result = acceptance.evaluate(baseline, component, stage='walkforward',
                                 n_resamples=n_resamples, seed=seed, cluster=cluster)
```

- [ ] **Step 4: `scripts/backtest/funnel.py`**

Replace

```python
def expr_lower_bound(rows, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    trades = [SimpleNamespace(**row) for row in rows]
    draws = acceptance.cluster_bootstrap(
        [], trades, lambda _baseline, component: acceptance.expectancy_r(component),
        n_resamples=n_resamples, seed=seed,
    )
```

with

```python
def expr_lower_bound(rows, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
                     cluster="ticker"):
    trades = [SimpleNamespace(**row) for row in rows]
    draws = acceptance.cluster_bootstrap(
        [], trades, lambda _baseline, component: acceptance.expectancy_r(component),
        n_resamples=n_resamples, seed=seed, cluster=cluster,
    )
```

Replace

```python
def score_cell(rows, min_n, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    stats = pooled(rows)
    lower_bound = expr_lower_bound(rows, n_resamples=n_resamples, seed=seed) if rows else None
```

with

```python
def score_cell(rows, min_n, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
               cluster="ticker"):
    stats = pooled(rows)
    lower_bound = (expr_lower_bound(rows, n_resamples=n_resamples, seed=seed, cluster=cluster)
                   if rows else None)
```

Replace

```python
def stage1(rows_by_cell, direction, grid, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES,
           seed=BOOTSTRAP_SEED):
    cells = {
        value: score_cell(dir_rows(rows_by_cell[cell_key(value)], direction), MIN_N_TRAIN,
                          n_resamples=n_resamples, seed=seed)
        for value in grid
    }
```

with

```python
def stage1(rows_by_cell, direction, grid, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES,
           seed=BOOTSTRAP_SEED, cluster="ticker"):
    cells = {
        value: score_cell(dir_rows(rows_by_cell[cell_key(value)], direction), MIN_N_TRAIN,
                          n_resamples=n_resamples, seed=seed, cluster=cluster)
        for value in grid
    }
```

- [ ] **Step 5: `scripts/backtest/harvest_select.py`**

Replace

```python
def _row(value, baseline, component, refused):
    res = bootstrap_delta(baseline, component, delta_expectancy_r)
```

with

```python
def _row(value, baseline, component, refused, cluster="ticker"):
    res = bootstrap_delta(baseline, component, delta_expectancy_r, cluster=cluster)
```

Replace

```python
def select(cells, *, param, less_aggressive, refused=()) -> dict:
    rows = [_row(v, b, c, set(refused)) for v, b, c in cells]
```

with

```python
def select(cells, *, param, less_aggressive, refused=(), cluster="ticker") -> dict:
    rows = [_row(v, b, c, set(refused), cluster) for v, b, c in cells]
```

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_verdict_helpers_cluster_unit.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_ticker_cluster_pin.py`
Expected: PASS, 7 passed.

Run each with `python scripts/dev/testrun.py file <path>`: `tests/scripts/test_funnel.py`, `tests/scripts/test_harvest_select.py`, `tests/scripts/test_measure_v104.py`, `tests/scripts/test_measure_v113.py`, `tests/scripts/test_measure_fib_v103.py`, and every file under `tests/backtesting/arms/` that `git grep -l "evaluate_cell\|select_cell" -- tests/backtesting/arms` lists.
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/backtesting/arms/selection.py scripts/backtest/funnel.py scripts/backtest/harvest_select.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/arms/selection.py scripts/backtest/funnel.py scripts/backtest/harvest_select.py tests/backtesting/test_verdict_helpers_cluster_unit.py
git commit -m "feat(v138): selection, funnel and harvest_select take the bootstrap cluster unit"
```
