# v138 Instrument v2, phase 4: Statistics. Part 1: Phase A, IS1-IS3

> Part of `2026-10-06-v138-instrument-v2-statistics_0-index.md` (header, where to work, global constraints, file map, review focus and `## Parallelisation` live there). Read that index's Global Constraints with every task. Steps use `- [ ]` for tracking. All paths are relative to the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v138-instrument-v2-statistics` unless a command names an absolute path.

# Phase A: `stats.py`

### Task IS1: Worktree, package, and the week-clustered bootstrap

**Files:**
- Create: `swingbot/core/backtesting/instrument/__init__.py` (only if absent)
- Create: `swingbot/core/backtesting/instrument/stats.py`
- Test: `tests/backtesting/test_instrument_stats_bootstrap.py`

**Interfaces:**
- Consumes: `swingbot.core.backtesting.acceptance.ArmTrade`, `expectancy_r`, `delta_expectancy_r`, `cluster_bootstrap` (tests only; `stats.py` itself imports none of them).
- Produces:
  - `WEEK_BOOTSTRAP_RESAMPLES: int = 10_000`, `WEEK_BOOTSTRAP_SEED: int = 42`
  - `iso_week_key(entry_date) -> str` — `"YYYY-Www"`; accepts `str` (first 10 chars, so `str(pandas.Timestamp)` works) or `datetime.date`; raises `ValueError` mentioning `entry_date` on `None`/blank.
  - `group_by_week(trades) -> dict[str, list]` — reads `trade.entry_date` by attribute (works for `ArmTrade` and `SimpleNamespace` rows).
  - `week_cluster_bootstrap(baseline, component, statistic, *, n_resamples: int = WEEK_BOOTSTRAP_RESAMPLES, seed: int = WEEK_BOOTSTRAP_SEED) -> np.ndarray` — same contract as `acceptance.cluster_bootstrap`: `statistic(baseline_draw, component_draw)`, one shared week draw for both arms, `None` results dropped, empty input returns `np.array([])`.

- [ ] **Step 0: Create the worktree**

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-06-v138-instrument-v2-statistics -b 2026-10-06-v138-instrument-v2-statistics main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v138-instrument-v2-statistics log --oneline -1
```

Expected: the worktree's HEAD is `main`'s HEAD. Every later command in this plan runs inside that worktree.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_instrument_stats_bootstrap.py`:

```python
"""v136 §4: the week-clustered bootstrap resamples whole ISO weeks of entry
date, across every ticker, so a market-wide move is one resampling unit
instead of N correlated 'independent' tickers."""
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.instrument import stats

FAST = dict(n_resamples=300, seed=42)


def _expectancy(_baseline, component):
    return acceptance.expectancy_r(component)


def _trade(ticker, entry_date, win, r_win=2.0):
    return ArmTrade(ticker=ticker, strategy="MACD", horizon_key="3m",
                    entry_date=entry_date, outcome="win" if win else "loss",
                    r_multiple=r_win if win else -1.0, planned_rr=2.0)


def market_wide(n_tickers=20, n_weeks=20):
    """Every ticker shares its week's outcome: a market-wide move. Each
    ticker carries the identical sequence, so resampling tickers returns the
    same population on every draw; only resampling weeks sees the dependence."""
    monday = date(2021, 1, 4)
    out = []
    for w in range(n_weeks):
        win = w % 3 != 0
        for t in range(n_tickers):
            day = monday + timedelta(weeks=w, days=t % 5)
            out.append(_trade(f"T{t}", day.isoformat(), win,
                              r_win=1.0 + 0.25 * (w % 5)))
    return out


@pytest.mark.parametrize("entry_date, key", [
    ("2020-12-31", "2020-W53"),            # Thursday
    ("2021-01-03", "2020-W53"),            # Sunday still in the ISO year before
    ("2021-01-04", "2021-W01"),            # Monday starts ISO week 1
    ("2021-01-10", "2021-W01"),
    ("2021-01-11", "2021-W02"),
    ("2024-12-30", "2025-W01"),            # calendar 2024, ISO year 2025
    ("2021-01-04 00:00:00", "2021-W01"),   # str(pandas.Timestamp)
])
def test_iso_week_key_follows_the_iso_calendar(entry_date, key):
    assert stats.iso_week_key(entry_date) == key


def test_iso_week_key_accepts_a_date_object():
    assert stats.iso_week_key(date(2021, 1, 4)) == "2021-W01"


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_a_trade_without_an_entry_date_cannot_be_clustered(missing):
    with pytest.raises(ValueError, match="entry_date"):
        stats.iso_week_key(missing)


def test_group_by_week_pools_every_ticker_in_one_week():
    trades = [_trade("AAA", "2021-01-04", True), _trade("BBB", "2021-01-08", False),
              _trade("AAA", "2021-01-11", True)]
    grouped = stats.group_by_week(trades)
    assert sorted(grouped) == ["2021-W01", "2021-W02"]
    assert [t.ticker for t in grouped["2021-W01"]] == ["AAA", "BBB"]


def test_group_by_week_reads_row_namespaces_too():
    rows = [SimpleNamespace(ticker="AAA", entry_date="2021-01-04")]
    assert list(stats.group_by_week(rows)) == ["2021-W01"]


def test_defaults_are_the_spec_values():
    assert stats.WEEK_BOOTSTRAP_RESAMPLES == 10_000
    assert stats.WEEK_BOOTSTRAP_SEED == 42


def test_week_bootstrap_is_deterministic_under_a_fixed_seed():
    pop = market_wide()
    a = stats.week_cluster_bootstrap([], pop, _expectancy, **FAST)
    b = stats.week_cluster_bootstrap([], pop, _expectancy, **FAST)
    assert np.array_equal(a, b)


def test_a_different_seed_gives_a_different_draw():
    pop = market_wide()
    a = stats.week_cluster_bootstrap([], pop, _expectancy, n_resamples=300, seed=42)
    b = stats.week_cluster_bootstrap([], pop, _expectancy, n_resamples=300, seed=7)
    assert not np.array_equal(a, b)


def test_week_clustering_sees_a_market_wide_move_ticker_clustering_misses():
    pop = market_wide()
    by_ticker = acceptance.cluster_bootstrap([], pop, _expectancy, **FAST)
    by_week = stats.week_cluster_bootstrap([], pop, _expectancy, **FAST)
    assert np.ptp(by_ticker) == pytest.approx(0.0, abs=1e-12)
    assert np.ptp(by_week) > 0.5


def test_both_arms_share_one_week_draw():
    """Pairing survives: identical arms give a delta of exactly 0 on every draw."""
    pop = market_wide()
    draws = stats.week_cluster_bootstrap(pop, list(pop), acceptance.delta_expectancy_r,
                                         **FAST)
    assert draws.size == 300
    assert np.allclose(draws, 0.0)


def test_undefined_draws_are_dropped_not_zero_filled():
    pop = market_wide(n_tickers=2, n_weeks=6)
    calls = []

    def every_other(_baseline, component):
        calls.append(1)
        return None if len(calls) % 2 else acceptance.expectancy_r(component)

    draws = stats.week_cluster_bootstrap([], pop, every_other, n_resamples=100, seed=42)
    assert draws.size == 50


def test_no_trades_gives_an_empty_array():
    assert stats.week_cluster_bootstrap([], [], _expectancy, **FAST).size == 0


def test_one_resample_draws_as_many_weeks_as_exist():
    pop = market_wide(n_tickers=3, n_weeks=4)
    sizes = []

    def size(_baseline, component):
        sizes.append(len(component))
        return 0.0

    stats.week_cluster_bootstrap([], pop, size, n_resamples=50, seed=42)
    assert set(sizes) == {12}   # 4 weeks drawn x 3 trades per week, whichever weeks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_bootstrap.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.instrument'`.

- [ ] **Step 3: Create the package marker, only if absent**

Run: `test -f swingbot/core/backtesting/instrument/__init__.py && echo EXISTS || echo ABSENT`

If `EXISTS` (phase 1, v137, already merged and created it): leave it untouched and skip to Step 4. If `ABSENT`, create `swingbot/core/backtesting/instrument/__init__.py` with exactly this content (a docstring, no imports, so a concurrent v137 file can replace it without loss):

```python
"""Backtest instrument v2 (v136 spec). One unit per module; see the spec's Architecture table."""
```

- [ ] **Step 4: Write `stats.py`**

Create `swingbot/core/backtesting/instrument/stats.py`:

```python
"""Instrument v2 statistics (v136 spec §4).

The week-clustered bootstrap: trades are grouped by the ISO week of their
entry date across every ticker and whole weeks are resampled. Trades on one
symbol share a price path (why v1 clusters by ticker), but trades on
different symbols in one week share the market's move, which the ticker
bootstrap counts as independent. The week is the unit that prices both.

numpy only: scipy is NOT in requirements.txt. This module imports nothing
from ``acceptance``, so ``acceptance.cluster_bootstrap`` can import it lazily
for ``cluster="week"`` without an import cycle.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np

#: Pre-registered (spec §4): 10,000 replicates, seeded.
WEEK_BOOTSTRAP_RESAMPLES = 10_000
WEEK_BOOTSTRAP_SEED = 42


def iso_week_key(entry_date) -> str:
    """``"YYYY-Www"`` for an entry date (str, ``str(Timestamp)`` or date).

    A trade with no entry date cannot be placed in a week; refusing is the
    only honest answer, since a catch-all week would invent a cluster."""
    if entry_date is None or not str(entry_date).strip():
        raise ValueError("trade has no entry_date; it cannot be assigned an "
                         "ISO-week cluster")
    year, week, _ = date.fromisoformat(str(entry_date)[:10]).isocalendar()
    return f"{year}-W{week:02d}"


def group_by_week(trades) -> dict:
    """Trades keyed by ISO week of entry, pooled across every ticker."""
    out = defaultdict(list)
    for trade in trades:
        out[iso_week_key(getattr(trade, "entry_date", None))].append(trade)
    return out


def _draw(b_by, c_by, weeks, row):
    """Both arms' populations for one resample row of week indices."""
    b_draw, c_draw = [], []
    for j in row:
        b_draw.extend(b_by.get(weeks[j], ()))
        c_draw.extend(c_by.get(weeks[j], ()))
    return b_draw, c_draw


def week_cluster_bootstrap(baseline, component, statistic, *,
                           n_resamples: int = WEEK_BOOTSTRAP_RESAMPLES,
                           seed: int = WEEK_BOOTSTRAP_SEED) -> np.ndarray:
    """Resample WEEKS with replacement, recomputing ``statistic`` per draw.

    Same contract as ``acceptance.cluster_bootstrap``: both arms are
    resampled with the SAME week draw, so pairing survives; a draw where the
    statistic is undefined is dropped, never zero-filled."""
    b_by, c_by = group_by_week(baseline), group_by_week(component)
    weeks = sorted(set(b_by) | set(c_by))
    if not weeks:
        return np.array([])
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(weeks), size=(n_resamples, len(weeks)))
    out = []
    for row in picks:
        value = statistic(*_draw(b_by, c_by, weeks, row))
        if value is not None:
            out.append(value)
    return np.asarray(out, dtype=float)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_bootstrap.py`
Expected: PASS, 0 failed.

Run: `python -m radon cc -s -n C swingbot/core/backtesting/instrument/stats.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/instrument/__init__.py swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_bootstrap.py
git commit -m "feat(v138): instrument.stats week-clustered bootstrap (ISO entry week, seeded)"
```

(If Step 3 found `__init__.py` already present, drop it from `git add`.)

---

### Task IS2: Benjamini–Hochberg q-values

**Files:**
- Modify: `swingbot/core/backtesting/instrument/stats.py` (append)
- Test: `tests/backtesting/test_instrument_stats_bh.py`

**Interfaces:**
- Consumes: nothing beyond IS1's module.
- Produces: `bh_qvalues(pvalues: Iterable[float | None]) -> list[float | None]` — aligned with the input; `None` passes through and does not count toward `m`; raises `ValueError` mentioning `p-value` for a value outside [0, 1] or NaN.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_instrument_stats_bh.py`:

```python
"""v136 §4: BH q-values across the pre-registration ledger. Reported, never gating."""
import pytest

from swingbot.core.backtesting.instrument import stats


def test_textbook_example():
    # sorted .005 .01 .03 .04, m=4: raw .02 .02 .04 .04
    assert stats.bh_qvalues([0.01, 0.04, 0.03, 0.005]) == pytest.approx(
        [0.02, 0.04, 0.04, 0.02])


def test_step_up_takes_the_running_minimum_from_the_top():
    # the smaller p's raw value is 0.04 * 2 / 1 = 0.08; the larger p's 0.041 caps it
    assert stats.bh_qvalues([0.04, 0.041]) == pytest.approx([0.041, 0.041])


def test_ties_share_one_q():
    assert stats.bh_qvalues([0.02, 0.02, 0.5]) == pytest.approx([0.03, 0.03, 0.5])


def test_q_never_falls_below_p_and_never_exceeds_one():
    ps = [0.001, 0.2, 0.5, 0.9, 1.0, 0.03]
    qs = stats.bh_qvalues(ps)
    assert all(p <= q <= 1.0 for p, q in zip(ps, qs))


def test_q_is_monotone_in_p():
    ps = [0.3, 0.001, 0.02, 0.02, 0.6]
    qs = stats.bh_qvalues(ps)
    order = sorted(range(len(ps)), key=ps.__getitem__)
    assert [qs[i] for i in order] == sorted(qs)


def test_null_p_values_pass_through_and_do_not_count_toward_m():
    assert stats.bh_qvalues([None, 0.01, None, 0.04]) == [
        None, pytest.approx(0.02), None, pytest.approx(0.04)]


def test_a_single_p_value_is_its_own_q():
    assert stats.bh_qvalues([0.7]) == pytest.approx([0.7])


def test_empty_input():
    assert stats.bh_qvalues([]) == []


def test_accepts_any_iterable():
    assert stats.bh_qvalues(p for p in (0.01, 0.04)) == pytest.approx([0.02, 0.04])


@pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan")])
def test_an_out_of_range_p_is_refused(bad):
    with pytest.raises(ValueError, match="p-value"):
        stats.bh_qvalues([0.01, bad])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_bh.py`
Expected: FAIL, `AttributeError: module ... has no attribute 'bh_qvalues'`.

- [ ] **Step 3: Implement**

Append to `swingbot/core/backtesting/instrument/stats.py`:

```python


def _checked_p(value) -> float:
    p = float(value)
    if not 0.0 <= p <= 1.0:   # also refuses NaN: every comparison is False
        raise ValueError(f"p-value must lie in [0, 1], got {value!r}")
    return p


def bh_qvalues(pvalues) -> list:
    """Benjamini-Hochberg step-up q-values, aligned with the input.

    ``q_(k) = min over j >= k of (m * p_(j) / j)``, capped at 1. ``None``
    (a pre-registration with no recorded p) passes through as ``None`` and
    does not count toward ``m``. Reported, never gating (v136 §4)."""
    values = list(pvalues)
    present = sorted(((i, _checked_p(p)) for i, p in enumerate(values)
                      if p is not None), key=lambda item: item[1])
    out = [None] * len(values)
    m = len(present)
    running = 1.0
    for rank in range(m, 0, -1):
        index, p = present[rank - 1]
        running = min(running, p * m / rank)
        out[index] = running
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_bh.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_bh.py
git commit -m "feat(v138): instrument.stats Benjamini-Hochberg q-values"
```

---

### Task IS3: Ledger rows: validate, load, append, q-values

**Files:**
- Modify: `swingbot/core/backtesting/instrument/stats.py` (imports + append)
- Test: `tests/backtesting/test_instrument_stats_ledger.py`

**Interfaces:**
- Consumes: `bh_qvalues` (IS2).
- Produces:
  - `LEDGER_PATH: Path` — `<repo>/docs/superpowers/results/preregistration-ledger.jsonl`
  - `LEDGER_FIELDS = ("id", "date", "hypothesis", "instrument", "n", "exp_r", "p", "verdict", "record")`
  - `VERDICTS = ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE", "WITHDRAWN", "OPEN")`
  - `INSTRUMENTS = ("v1", "v2")`
  - `validate_ledger_row(row) -> None` — raises `ValueError`; message contains `missing [...]`/`extra [...]` or `invalid field(s) ['<name>', ...]`.
  - `load_ledger(path=LEDGER_PATH) -> list[dict]` — `[]` when the file is absent; blank lines skipped; raises `ValueError` naming `ledger line <n>` on bad JSON, an invalid row, or a duplicate id.
  - `append_ledger_row(row, path=LEDGER_PATH) -> list[dict]` — validates first (file untouched on refusal), refuses a duplicate id (message contains `duplicate`), writes one LF-terminated line in `LEDGER_FIELDS` order, returns all rows including the new one.
  - `ledger_qvalues(rows) -> dict[str, float | None]` — `id -> BH q` across every row's `p`.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_instrument_stats_ledger.py`:

```python
"""v136 §4: the pre-registration ledger, a git-tracked JSONL record."""
import json

import pytest

from swingbot.core.backtesting.instrument import stats


def _row(**over):
    row = {"id": "v999-demo", "date": "2026-10-06", "hypothesis": "Demo gate",
           "instrument": "v2", "n": 120, "exp_r": 0.12, "p": 0.03,
           "verdict": "FAIL", "record": "docs/superpowers/results/demo.md"}
    row.update(over)
    return row


def test_fields_and_vocabularies_are_the_plan_set():
    assert stats.LEDGER_FIELDS == ("id", "date", "hypothesis", "instrument", "n",
                                   "exp_r", "p", "verdict", "record")
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN")
    assert stats.INSTRUMENTS == ("v1", "v2")


def test_ledger_path_is_the_committed_results_file():
    assert stats.LEDGER_PATH.as_posix().endswith(
        "docs/superpowers/results/preregistration-ledger.jsonl")


def test_a_complete_row_validates():
    stats.validate_ledger_row(_row())


def test_null_n_exp_r_and_p_are_allowed():
    stats.validate_ledger_row(_row(n=None, exp_r=None, p=None))


def test_an_integer_p_of_one_is_allowed():
    stats.validate_ledger_row(_row(p=1))


@pytest.mark.parametrize("field, value", [
    ("id", ""), ("date", "06/10/2026"), ("date", "20261006"), ("date", None),
    ("hypothesis", "  "), ("instrument", "v3"), ("n", -1), ("n", 1.5),
    ("n", True), ("exp_r", "0.1"), ("exp_r", float("inf")), ("p", 1.2),
    ("p", -0.01), ("verdict", "PASSED"), ("record", ""),
])
def test_an_invalid_field_is_refused(field, value):
    with pytest.raises(ValueError, match=f"'{field}'"):
        stats.validate_ledger_row(_row(**{field: value}))


def test_missing_or_extra_fields_are_refused():
    row = _row()
    del row["p"]
    with pytest.raises(ValueError, match=r"missing \['p'\]"):
        stats.validate_ledger_row(row)
    with pytest.raises(ValueError, match=r"extra \['note'\]"):
        stats.validate_ledger_row(_row(note="x"))


def test_a_non_object_row_is_refused():
    with pytest.raises(ValueError, match="JSON object"):
        stats.validate_ledger_row(["v999-demo"])


def test_load_of_a_missing_file_is_empty(tmp_path):
    assert stats.load_ledger(tmp_path / "none.jsonl") == []


def test_append_then_load_round_trips_in_field_order(tmp_path):
    path = tmp_path / "ledger.jsonl"
    rows = stats.append_ledger_row(_row(), path=path)
    assert rows == [_row()]
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and text.count("\n") == 1
    assert list(json.loads(text)) == list(stats.LEDGER_FIELDS)
    assert stats.load_ledger(path) == [_row()]


def test_append_writes_lf_line_endings(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_row(), path=path)
    assert b"\r\n" not in path.read_bytes()


def test_append_repairs_a_missing_trailing_newline(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(_row(id="a")), encoding="utf-8")
    stats.append_ledger_row(_row(id="b"), path=path)
    assert [r["id"] for r in stats.load_ledger(path)] == ["a", "b"]


def test_append_refuses_a_duplicate_id(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_row(), path=path)
    with pytest.raises(ValueError, match="duplicate"):
        stats.append_ledger_row(_row(verdict="PASS"), path=path)
    assert len(stats.load_ledger(path)) == 1


def test_append_refuses_an_invalid_row_without_touching_the_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with pytest.raises(ValueError):
        stats.append_ledger_row(_row(verdict="maybe"), path=path)
    assert not path.exists()


def test_load_names_the_bad_line(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(_row()) + "\n{not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ledger line 2"):
        stats.load_ledger(path)


def test_load_refuses_duplicate_ids(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text((json.dumps(_row()) + "\n") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="ledger line 2: duplicate"):
        stats.load_ledger(path)


def test_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n" + json.dumps(_row()) + "\n\n", encoding="utf-8")
    assert stats.load_ledger(path) == [_row()]


def test_ledger_qvalues_maps_ids_to_bh_q():
    rows = [_row(id="a", p=0.01), _row(id="b", p=None), _row(id="c", p=0.04)]
    assert stats.ledger_qvalues(rows) == {
        "a": pytest.approx(0.02), "b": None, "c": pytest.approx(0.04)}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py`
Expected: FAIL, `AttributeError: module ... has no attribute 'LEDGER_FIELDS'`.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/instrument/stats.py`, replace the import block

```python
from collections import defaultdict
from datetime import date

import numpy as np
```

with

```python
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
```

Then append to the end of the file:

```python


# --------------------------------------------------------------------------
# Pre-registration ledger (v136 §4). A git-tracked record, not a runtime
# store: no Postgres, no Alembic. One row per pre-registration.
# --------------------------------------------------------------------------

LEDGER_PATH = (Path(__file__).resolve().parents[4] / "docs" / "superpowers"
               / "results" / "preregistration-ledger.jsonl")
LEDGER_FIELDS = ("id", "date", "hypothesis", "instrument", "n", "exp_r", "p",
                 "verdict", "record")
VERDICTS = ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE", "WITHDRAWN", "OPEN")
INSTRUMENTS = ("v1", "v2")


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_date(value) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _count(value) -> bool:
    return value is None or (type(value) is int and value >= 0)


def _real(value) -> bool:
    return value is None or (type(value) in (int, float) and math.isfinite(value))


def _probability(value) -> bool:
    return value is None or (_real(value) and 0.0 <= value <= 1.0)


_FIELD_CHECKS = {
    "id": _text, "date": _iso_date, "hypothesis": _text,
    "instrument": INSTRUMENTS.__contains__, "n": _count, "exp_r": _real,
    "p": _probability, "verdict": VERDICTS.__contains__, "record": _text,
}


def validate_ledger_row(row) -> None:
    """Raise ValueError unless ``row`` has exactly LEDGER_FIELDS, each valid."""
    if not isinstance(row, dict):
        raise ValueError("a ledger row must be a JSON object")
    missing = sorted(set(LEDGER_FIELDS) - set(row))
    extra = sorted(set(row) - set(LEDGER_FIELDS))
    if missing or extra:
        raise ValueError(f"ledger row {row.get('id')!r}: missing {missing}, "
                         f"extra {extra}")
    bad = [name for name in LEDGER_FIELDS if not _FIELD_CHECKS[name](row[name])]
    if bad:
        raise ValueError(f"ledger row {row.get('id')!r}: invalid field(s) {bad}")


def _parse_line(text: str, lineno: int, seen: set) -> dict:
    try:
        row = json.loads(text)
        validate_ledger_row(row)
    except ValueError as exc:   # json.JSONDecodeError is a ValueError
        raise ValueError(f"ledger line {lineno}: {exc}") from exc
    if row["id"] in seen:
        raise ValueError(f"ledger line {lineno}: duplicate id {row['id']!r}")
    seen.add(row["id"])
    return row


def load_ledger(path=LEDGER_PATH) -> list:
    """Every row, validated, in file order. An absent file is an empty ledger."""
    path = Path(path)
    if not path.exists():
        return []
    seen: set = set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_parse_line(line, n, seen) for n, line in enumerate(lines, start=1)
            if line.strip()]


def append_ledger_row(row: dict, path=LEDGER_PATH) -> list:
    """Validate, refuse a duplicate id, append one LF line. Returns every row.

    A row is never edited in place: a re-measurement is a new
    pre-registration with a new id."""
    validate_ledger_row(row)
    path = Path(path)
    rows = load_ledger(path)
    if any(existing["id"] == row["id"] for existing in rows):
        raise ValueError(f"duplicate id {row['id']!r}: the ledger already "
                         "holds this pre-registration")
    ordered = {name: row[name] for name in LEDGER_FIELDS}
    lead = "\n" if path.exists() and path.read_bytes()[-1:] not in (b"", b"\n") else ""
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(lead + json.dumps(ordered, ensure_ascii=False) + "\n")
    return rows + [ordered]


def ledger_qvalues(rows) -> dict:
    """``id -> BH q-value`` across every row's p (None where p is null)."""
    rows = list(rows)
    return dict(zip((row["id"] for row in rows),
                    bh_qvalues(row["p"] for row in rows)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_bootstrap.py` and `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_bh.py`
Expected: both PASS (the import change touched the shared module).

Run: `python -m radon cc -s -n C swingbot/core/backtesting/instrument/stats.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_ledger.py
git commit -m "feat(v138): pre-registration ledger rows -- validate, load, append, BH q per id"
```
