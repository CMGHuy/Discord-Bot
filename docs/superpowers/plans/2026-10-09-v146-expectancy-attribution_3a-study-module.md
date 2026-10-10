# v146 Expectancy attribution: Implementation Plan, part 3a -- the study module

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V146-10:" -A 400 docs/superpowers/plans/2026-10-09-v146-expectancy-attribution_3a-study-module.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`](../specs/2026-10-09-v146-expectancy-attribution-design.md)
**Index:** [`2026-10-09-v146-expectancy-attribution_0-index.md`](2026-10-09-v146-expectancy-attribution_0-index.md) -- Global Constraints, Handoff decisions, Parallelisation and the task ledger live there and bind every task below.

**Tasks:** V146-9 .. V146-11 here; V146-12 is in [`_3b-study-module-loaders`](2026-10-09-v146-expectancy-attribution_3b-study-module-loaders.md) (a file boundary only, same part). **Where:** every command runs from the worktree root
`E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution`
(never `cd` in Bash: pass the worktree path to `git -C` and run Python with the worktree as the session root).

**Order inside this part.** V146-9 is independent. V146-10 needs `aggregate.rs_quintile_label` (V146-6). V146-10 -> V146-11 -> V146-12 share `swingbot/core/analytics/expectancy_attribution.py` and run in that order. V146-12 also needs `write_latest` (V146-9). None of them needs a TRAIN replay or a database: every test runs on synthetic rows.

**Decisions this part takes (inside the ledger contract):**

- **A row's `week` is the Monday (ISO date) of its entry week.** `stats.week_cluster_bootstrap` groups by `getattr(trade, "entry_date")`, so the study hands it one small `_Obs(entry_date, total, n)` named tuple per arm and week (that week's summed R and row count: resampling whole weeks of sums is the same resample, far cheaper); a Monday date maps back to the right ISO week through `stats.iso_week_key`. Live: the week of `opened_at`. TRAIN: the week of `signal_date` (the replay row carries no entry date).
- **Win rate is `r > 0` on net R** in both populations, so live and TRAIN use one definition.
- **A bucket look** is the bucket's ExpR minus the ExpR of the rest of its grouping (same population, same grouping), week-clustered. **A factor look** is ExpR(points != 0) minus ExpR(points == 0), unevaluated rows excluded; for every non-negative factor this is exactly the spec's "> 0 minus 0", and it lets the negative `"Tight stop penalty"` (present only when applied) read "applied vs not applied". A look on fewer than `THIN_N` rows in either arm gets no interval and no p.
- **The BH family (`looks`)** is every non-null p in both populations: monotonicity (main and every direction/horizon split), factor deltas and buckets. q-values are written onto buckets and factors only (the monotonicity dict keeps its ledger shape); the verdict reads the CI, never a q.
- **Bootstrap p** is two-sided with the +1 correction: `min(1, 2 * min((#draws <= 0) + 1, (#draws >= 0) + 1) / (draws + 1))`. `N_RESAMPLES` is a module constant (`WEEK_BOOTSTRAP_RESAMPLES`, 10,000); tests monkeypatch it down.
- **Live confluence count** is `risk_features.confluence_count` (`target_confluence[0]`, the same `count_confirming_strategies` count TRAIN records as `n_confl`); a trade without it reads `unknown`, never `len(target_sources)`, so one population never mixes two definitions.
- **Live frictions:** `git grep` finds `apply_frictions` only under `swingbot/core/backtesting/`, so live fills are not friction-adjusted. V146-12 Step 1 re-verifies; `LIVE_FILLS_INCLUDE_FRICTIONS = False` then applies the TRAIN friction model to live rows too (Handoff 5).

# Phase 3 -- the study module

### Task V146-9: Light report store: atomic write and `load_latest()`

**Model:** sonnet -- one small new module with a fully specified contract and stdlib-only code.

**Files:**
- Create: `swingbot/core/infra/expectancy_attribution_store.py`
- Create: `tests/infra/test_expectancy_attribution_store.py`

**Interfaces:**
- Consumes: `swingbot.config.DATA_DIR` (str, `config.py:64`); `swingbot.core.infra.jsonio.atomic_write_json(path: str, obj) -> None` and `jsonio.read_json(path: str, default)` (both exist, `jsonio.py:52`, `:80`).
- Produces (index ledger):
  - `REPORT_PATH: Path` = `Path(config.DATA_DIR) / "reports" / "expectancy-attribution.json"`.
  - `load_latest(path: Path | None = None) -> dict | None` -- the parsed file, or `None` when it is missing, empty, corrupt or not a JSON object.
  - `write_latest(result: dict, path: Path | None = None) -> dict` -- writes atomically (overwrite-latest: one file, no history) and returns what it wrote. `verdict_of_record` is carried forward unchanged from the file already on disk when that file has a complete one (`verdict`, `date`, `n`); otherwise it is the result's own `verdict_of_record` when complete, else `{verdict: result["verdict"], date: result["generated_at"][:10], n: sum of the populations' monotonicity n}`.
- v150 imports `load_latest` from this module (Handoff 6); it must import without `pandas`, `numpy` or `swingbot.core.backtesting` in `sys.modules`.

- [ ] **Step 1: Write the failing tests**

Create `tests/infra/test_expectancy_attribution_store.py`:

```python
"""v146: the Expectancy attribution report store -- atomic overwrite-latest
file, the verdict of record carried forward, and a loader cheap enough for
the v150 Reports page to import."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.infra import expectancy_attribution_store as store
from swingbot.core.infra import jsonio

REPO = Path(__file__).resolve().parents[2]


def _result(verdict="WEAK", generated_at="2026-10-10T12:00:00+00:00",
            live_n=120, train_n=300, **over):
    result = {
        "generated_at": generated_at,
        "verdict": verdict,
        "looks": 41,
        "seed": 42,
        "provenance": {},
        "populations": {
            "live": {"n": live_n, "monotonicity": {"n": live_n}},
            "train": {"n": train_n, "monotonicity": {"n": train_n}},
        },
    }
    result.update(over)
    return result


def test_report_path_is_under_data_reports():
    assert store.REPORT_PATH == (Path(config.DATA_DIR) / "reports"
                                 / "expectancy-attribution.json")


def test_load_latest_returns_none_when_missing(tmp_path):
    assert store.load_latest(tmp_path / "absent.json") is None


def test_load_latest_returns_none_for_a_corrupt_file(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    path.write_text("{not json", encoding="utf-8")
    assert store.load_latest(path) is None


def test_load_latest_returns_none_for_a_non_object(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert store.load_latest(path) is None


def test_load_latest_defaults_to_report_path(tmp_path, monkeypatch):
    path = tmp_path / "reports" / "expectancy-attribution.json"
    monkeypatch.setattr(store, "REPORT_PATH", path)
    store.write_latest(_result())
    assert store.load_latest()["verdict"] == "WEAK"


def test_write_creates_the_reports_directory_and_round_trips(tmp_path):
    path = tmp_path / "reports" / "expectancy-attribution.json"
    written = store.write_latest(_result(), path)
    assert path.exists()
    assert store.load_latest(path) == written
    assert json.loads(path.read_text(encoding="utf-8")) == written


def test_first_write_derives_the_verdict_of_record_from_the_result(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    written = store.write_latest(_result(verdict="WEAK"), path)
    assert written["verdict_of_record"] == {"verdict": "WEAK",
                                            "date": "2026-10-10", "n": 420}
    assert written["looks"] == 41


def test_first_write_keeps_a_complete_record_the_result_carries(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    record = {"verdict": "NOT PREDICTIVE", "date": "2026-10-11", "n": 77}
    written = store.write_latest(_result(verdict_of_record=record), path)
    assert written["verdict_of_record"] == record


def test_later_write_carries_the_verdict_of_record_forward(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    store.write_latest(_result(verdict="WEAK"), path)
    later = _result(verdict="PREDICTIVE", generated_at="2026-12-01T09:00:00+00:00",
                    live_n=400,
                    verdict_of_record={"verdict": "PREDICTIVE",
                                       "date": "2026-12-01", "n": 700})
    written = store.write_latest(later, path)
    assert written["verdict_of_record"] == {"verdict": "WEAK",
                                            "date": "2026-10-10", "n": 420}
    assert written["verdict"] == "PREDICTIVE"   # the later run's reading, descriptive
    assert store.load_latest(path)["verdict_of_record"]["verdict"] == "WEAK"


def test_an_incomplete_record_on_disk_is_not_carried(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    jsonio.atomic_write_json(str(path), {"verdict_of_record": {"verdict": "WEAK"}})
    written = store.write_latest(_result(verdict="PREDICTIVE"), path)
    assert written["verdict_of_record"]["verdict"] == "PREDICTIVE"


def test_overwrite_latest_leaves_one_file_and_no_temp(tmp_path):
    path = tmp_path / "expectancy-attribution.json"
    store.write_latest(_result(), path)
    store.write_latest(_result(verdict="PREDICTIVE"), path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["expectancy-attribution.json"]


def test_write_goes_through_the_atomic_writer(tmp_path, monkeypatch):
    calls = []
    real = jsonio.atomic_write_json

    def spy(path, obj):
        calls.append(path)
        real(path, obj)

    monkeypatch.setattr(jsonio, "atomic_write_json", spy)
    path = tmp_path / "expectancy-attribution.json"
    store.write_latest(_result(), path)
    assert calls == [str(path)]


def test_write_latest_does_not_mutate_its_input(tmp_path):
    result = _result()
    store.write_latest(result, tmp_path / "expectancy-attribution.json")
    assert "verdict_of_record" not in result


@pytest.mark.parametrize("heavy", ["pandas", "numpy", "swingbot.core.backtesting"])
def test_loader_imports_without_heavy_modules(heavy):
    code = ("import sys\n"
            "from swingbot.core.infra.expectancy_attribution_store import load_latest\n"
            f"loaded = sorted(m for m in sys.modules if m.startswith({heavy!r}))\n"
            "assert not loaded, loaded\n"
            "print('light')\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "light"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_expectancy_attribution_store.py`
Expected: FAIL -- `ModuleNotFoundError: No module named 'swingbot.core.infra.expectancy_attribution_store'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/infra/expectancy_attribution_store.py`:

```python
"""Expectancy attribution (v146): the latest report on disk and its loader.

LIGHT BY CONTRACT: stdlib, ``swingbot.config`` and ``swingbot.core.infra.jsonio``
only. The v150 Reports page imports ``load_latest`` from here, so this module
must never pull in pandas, numpy or ``swingbot.core.backtesting`` (v150 spec,
"Cross-spec requirements on the v146 and v147 plans"). The study itself lives
in ``swingbot/core/analytics/expectancy_attribution.py``, which re-exports
``load_latest``.

Retention is overwrite-latest: one file, replaced atomically on every run
(temp file + ``os.replace`` via ``jsonio.atomic_write_json``). The verdict is
pre-registered and computed once; ``verdict_of_record`` is therefore carried
forward unchanged by every later write, and a later run's ``verdict`` is a
descriptive reading only (spec, "The verdict").
"""
from __future__ import annotations

from pathlib import Path

from swingbot import config
from swingbot.core.infra import jsonio

REPORT_PATH = Path(config.DATA_DIR) / "reports" / "expectancy-attribution.json"
_RECORD_KEYS = ("verdict", "date", "n")


def _target(path: Path | str | None) -> Path:
    return Path(path) if path is not None else REPORT_PATH


def load_latest(path: Path | None = None) -> dict | None:
    """The latest Expectancy attribution report, or None when there is none
    (missing, empty, corrupt, or not a JSON object)."""
    data = jsonio.read_json(str(_target(path)), None)
    return data if isinstance(data, dict) else None


def _complete(record) -> bool:
    return (isinstance(record, dict) and all(key in record for key in _RECORD_KEYS)
            and bool(record.get("verdict")))


def _monotonicity_n(result: dict) -> int:
    total = 0
    for population in (result.get("populations") or {}).values():
        monotonicity = (population or {}).get("monotonicity") or {}
        total += int(monotonicity.get("n") or 0)
    return total


def _record_from(result: dict) -> dict:
    record = result.get("verdict_of_record")
    if _complete(record):
        return {key: record[key] for key in _RECORD_KEYS}
    return {"verdict": result.get("verdict"),
            "date": str(result.get("generated_at") or "")[:10] or None,
            "n": _monotonicity_n(result)}


def write_latest(result: dict, path: Path | None = None) -> dict:
    """Atomically replace the report with ``result`` and return what was
    written. A complete ``verdict_of_record`` already on disk wins."""
    target = _target(path)
    previous = (load_latest(target) or {}).get("verdict_of_record")
    out = dict(result)
    out["verdict_of_record"] = (
        {key: previous[key] for key in _RECORD_KEYS} if _complete(previous)
        else _record_from(result))
    jsonio.atomic_write_json(str(target), out)
    return out
```

`write_latest` calls `jsonio.atomic_write_json` through the module attribute (not a `from ... import`), so the spy test sees the call.

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/infra/test_expectancy_attribution_store.py`
Expected: PASS, 0 failed. If a cheap-import case fails, the stderr names the heavy module and its importer: remove that import from the store (never from `swingbot.config`); do not weaken the test.

- [ ] **Step 5: Complexity and the main-tree check**

Run: `python -m radon cc -s -n C swingbot/core/infra/expectancy_attribution_store.py`
Expected: no output (every function below C).
Run: `git -C E:/Documents/Private/Projects/Discord-Bot status --short`
Expected: empty (the main tree is untouched).

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/infra/expectancy_attribution_store.py tests/infra/test_expectancy_attribution_store.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): expectancy attribution report store -- atomic write, cheap load_latest"
```

---

### Task V146-10: Study core: rows, bins, buckets, frictions

**Model:** opus -- the tie-break, the thin-bucket rule and the friction model are pre-registered measurement semantics; a silent slip here moves the verdict.

**Files:**
- Create: `swingbot/core/analytics/expectancy_attribution.py`
- Create: `tests/analytics/test_expectancy_attribution_buckets.py`

**Interfaces:**
- Consumes: `aggregate.rs_quintile_label(value: float | None) -> str` (V146-6; `"Q1"`..`"Q5"`, `"unknown"`); `frictions.apply_frictions(fill_price, side, slippage_bps=None)` and `frictions.commission_r(risk_dollars=None, commission=None)` (`swingbot/core/edge/frictions.py:15`, `:22`); `HORIZONS[<key>]["max_holding_days"]` (`swingbot/core/market/strategy_types.py:48`).
- Produces (index ledger):
  - `THIN_N = 30`; `EARNINGS_BUCKETS = ("0-5", "6-10", "11-20", ">20", "none", "unknown")`; `ROW_KEYS`, the attribution row keys `r, r_gross, week, confidence_score, confidence_level, confidence_points, confidence_unevaluated, confluence_count, regime2_state, rs_pctile, direction, horizon, earnings_sessions, earnings_status, risk_reward_ratio`. `earnings_status` is `"known"` (then `earnings_sessions` is an int), `"none"` or `"unknown"`. V146-12's two loaders build these rows; this task and V146-11 only read them.
  - `quantile_bins(values: list[float], k: int) -> list[int]`
  - `earnings_bucket(row) -> str`; `earnings_in_hold(row) -> str` (`"yes"` / `"no"` / `"unknown"`)
  - `net_r(entry: float, stop_loss: float, direction: str, legs: list[dict]) -> float`
  - `bucket_stats(rows: list[dict]) -> dict` (`n, win_rate, exp_r, exp_r_gross, thin`)
  - `population_buckets(rows: list[dict]) -> dict[str, list[dict]]`: groupings `confidence_decile`, `confidence_level`, `confluence`, `regime2_state`, `rs_quintile`, `direction`, `horizon`, `earnings`, `earnings_in_hold`; each bucket `{label, n, win_rate, exp_r, exp_r_gross, thin, q: None}`; decile buckets also `unevaluated_n`, `rr: {p25, median, p75}`.
  - Private helpers V146-11 and V146-12 reuse by name: `_scored(rows)`, `_label(value)`, `_sort_key(label)`, `_grouped_rows(rows)`, `_quartiles(values)`, `_mean(values)`.
- Spec rules this task fixes in code: "Tied scores are never split. A tied block goes wholly to the tercile (decile) containing its median rank"; "Buckets with N < 30 are shown greyed and enter no verdict"; the confidence analyses use rows with a non-null `confidence_score`, every other grouping uses every row; R is net of frictions and gross ExpR is reported beside it.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_expectancy_attribution_buckets.py`:

```python
"""v146 study core: attribution rows, tie-safe quantile bins, earnings
buckets, the friction model and the per-population bucket tables."""
from __future__ import annotations

import json

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.market.strategy_types import HORIZONS

HK = next(iter(HORIZONS))
HOLD = HORIZONS[HK]["max_holding_days"]


def _row(r=0.5, score=60, **over):
    row = {
        "r": r, "r_gross": r + 0.05, "week": "2025-01-06",
        "confidence_score": score, "confidence_level": 4,
        "confidence_points": {"MACD momentum": 10}, "confidence_unevaluated": [],
        "confluence_count": 3, "regime2_state": "bull_quiet", "rs_pctile": 72.0,
        "direction": "bullish", "horizon": HK,
        "earnings_sessions": 12, "earnings_status": "known",
        "risk_reward_ratio": 2.0,
    }
    row.update(over)
    return row


@pytest.fixture
def no_frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 0.0, raising=False)


@pytest.fixture
def frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 10.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def test_constants_are_the_specs():
    assert ea.THIN_N == 30
    assert ea.EARNINGS_BUCKETS == ("0-5", "6-10", "11-20", ">20", "none", "unknown")
    assert tuple(_row()) == ea.ROW_KEYS


def test_quantile_bins_splits_distinct_values_evenly():
    assert ea.quantile_bins(list(range(10)), 5) == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_quantile_bins_is_aligned_with_the_input_order():
    assert ea.quantile_bins([3.0, 1.0, 2.0], 3) == [2, 0, 1]


def test_quantile_bins_never_splits_a_tied_block():
    # ranks 0-3 tie: median rank 1.5 -> bin 0; the block is not cut at rank 2.
    assert ea.quantile_bins([1, 1, 1, 1, 2, 3], 3) == [0, 0, 0, 0, 2, 2]


def test_a_straddling_tied_block_goes_to_its_median_ranks_bin():
    # the 5s hold ranks 2-5 of 8: median rank 3.5 -> the lower half.
    assert ea.quantile_bins([1, 2, 5, 5, 5, 5, 9, 10], 2) == [0, 0, 0, 0, 0, 0, 1, 1]


def test_an_all_tied_sample_lands_in_the_middle_bin():
    assert ea.quantile_bins([7] * 9, 3) == [1] * 9


def test_quantile_bins_of_nothing_is_nothing():
    assert ea.quantile_bins([], 10) == []


@pytest.mark.parametrize("sessions, expected", [
    (0, "0-5"), (5, "0-5"), (6, "6-10"), (10, "6-10"),
    (11, "11-20"), (20, "11-20"), (21, ">20"), (400, ">20"),
])
def test_earnings_bucket_edges(sessions, expected):
    assert ea.earnings_bucket(_row(earnings_sessions=sessions)) == expected
    assert expected in ea.EARNINGS_BUCKETS


def test_earnings_bucket_none_and_unknown():
    assert ea.earnings_bucket(_row(earnings_sessions=None, earnings_status="none")) == "none"
    assert ea.earnings_bucket(_row(earnings_sessions=None, earnings_status="unknown")) == "unknown"
    assert ea.earnings_bucket(_row(earnings_sessions=None, earnings_status="known")) == "unknown"
    assert ea.earnings_bucket(_row(earnings_sessions=-2)) == "unknown"


def test_earnings_in_hold_uses_the_horizons_max_holding_days():
    assert ea.earnings_in_hold(_row(earnings_sessions=HOLD)) == "yes"
    assert ea.earnings_in_hold(_row(earnings_sessions=HOLD + 1)) == "no"
    assert ea.earnings_in_hold(_row(earnings_sessions=None, earnings_status="none")) == "no"
    assert ea.earnings_in_hold(_row(earnings_sessions=None, earnings_status="unknown")) == "unknown"
    assert ea.earnings_in_hold(_row(horizon="no-such-horizon")) == "unknown"


def test_net_r_without_frictions_is_the_plain_r(no_frictions):
    legs = [{"fraction": 1.0, "exit_price": 110.0}]
    assert ea.net_r(100.0, 95.0, "bullish", legs) == pytest.approx(2.0)
    short = [{"fraction": 1.0, "exit_price": 90.0}]
    assert ea.net_r(100.0, 105.0, "bearish", short) == pytest.approx(2.0)


def test_net_r_blends_legs_by_fraction(no_frictions):
    legs = [{"fraction": 0.5, "exit_price": 110.0, "r": 99.0},   # a recorded r is ignored
            {"fraction": 0.5, "exit_price": 100.0}]
    assert ea.net_r(100.0, 95.0, "bullish", legs) == pytest.approx(1.0)


def test_net_r_applies_slippage_both_sides_and_commission(frictions):
    bull = ea.net_r(100.0, 95.0, "bullish", [{"fraction": 1.0, "exit_price": 110.0}])
    assert bull == pytest.approx((109.89 - 100.1) / (100.1 - 95.0) - 0.02)
    bear = ea.net_r(100.0, 105.0, "bearish", [{"fraction": 1.0, "exit_price": 90.0}])
    assert bear == pytest.approx((99.9 - 90.09) / (105.0 - 99.9) - 0.02)


def test_a_full_stop_out_costs_more_than_one_r_net(frictions):
    assert ea.net_r(100.0, 95.0, "bullish", [{"fraction": 1.0, "exit_price": 95.0}]) < -1.0


def test_net_r_refuses_no_legs_and_zero_risk(no_frictions):
    with pytest.raises(ValueError):
        ea.net_r(100.0, 95.0, "bullish", [])
    with pytest.raises(ValueError):
        ea.net_r(100.0, 100.0, "bullish", [{"fraction": 1.0, "exit_price": 101.0}])


def test_bucket_stats_counts_net_wins_and_flags_thin():
    stats = ea.bucket_stats([_row(r=1.0), _row(r=-1.0), _row(r=0.5)])
    assert stats["n"] == 3 and stats["thin"] is True
    assert stats["win_rate"] == pytest.approx(200.0 / 3)
    assert stats["exp_r"] == pytest.approx(0.5 / 3)
    assert stats["exp_r_gross"] == pytest.approx(0.5 / 3 + 0.05)
    assert list(stats) == ["n", "win_rate", "exp_r", "exp_r_gross", "thin"]


def test_bucket_stats_at_the_floor_is_not_thin_and_empty_is_null():
    assert ea.bucket_stats([_row()] * 30)["thin"] is False
    assert ea.bucket_stats([_row()] * 29)["thin"] is True
    assert ea.bucket_stats([]) == {"n": 0, "win_rate": None, "exp_r": None,
                                   "exp_r_gross": None, "thin": True}


def _population():
    rows = []
    for i in range(100):
        rows.append(_row(
            r=(i % 7 - 3) / 4.0, score=i + 1,
            confidence_unevaluated=["ADX trend strength"] if i < 4 else [],
            risk_reward_ratio=1.0 + (i % 10) / 10.0,
            direction="bullish" if i % 4 else "bearish",
            rs_pctile=float(i), confluence_count=2 + i % 3,
            earnings_sessions=i % 30))
    rows.append(_row(score=None, confidence_level=None, confidence_points=None,
                     direction="bearish", rs_pctile=None, confluence_count=None,
                     earnings_sessions=None, earnings_status="unknown"))
    return rows


def test_population_buckets_has_every_grouping():
    buckets = ea.population_buckets(_population())
    assert list(buckets) == ["confidence_decile", "confidence_level", "confluence",
                             "regime2_state", "rs_quintile", "direction", "horizon",
                             "earnings", "earnings_in_hold"]
    for grouping in buckets.values():
        for bucket in grouping:
            assert list(bucket)[:7] == ["label", "n", "win_rate", "exp_r",
                                        "exp_r_gross", "thin", "q"]
            assert bucket["q"] is None
    json.dumps(buckets)   # JSON-serialisable as is


def test_deciles_are_population_quantiles_of_the_scored_rows():
    deciles = ea.population_buckets(_population())["confidence_decile"]
    assert [bucket["n"] for bucket in deciles] == [10] * 10       # the unscored row is out
    assert deciles[0]["label"] == "D1 (1-10)" and deciles[-1]["label"] == "D10 (91-100)"
    assert all(bucket["thin"] for bucket in deciles)
    assert deciles[0]["unevaluated_n"] == 4 and deciles[1]["unevaluated_n"] == 0
    assert deciles[0]["rr"] == {"p25": pytest.approx(1.225), "median": pytest.approx(1.45),
                                "p75": pytest.approx(1.675)}


def test_tied_scores_share_a_decile():
    rows = [_row(score=50) for _ in range(40)] + [_row(score=90) for _ in range(10)]
    deciles = ea.population_buckets(rows)["confidence_decile"]
    assert [(bucket["label"], bucket["n"]) for bucket in deciles] == [
        ("D4 (50-50)", 40), ("D9 (90-90)", 10)]


def test_non_confidence_groupings_keep_unscored_rows_and_order_labels():
    buckets = ea.population_buckets(_population())
    assert sum(bucket["n"] for bucket in buckets["direction"]) == 101
    assert sum(bucket["n"] for bucket in buckets["confidence_level"]) == 100
    assert [bucket["label"] for bucket in buckets["rs_quintile"]] == [
        "Q1", "Q2", "Q3", "Q4", "Q5", "unknown"]
    assert [bucket["label"] for bucket in buckets["confluence"]] == ["2", "3", "4", "unknown"]
    assert [bucket["label"] for bucket in buckets["earnings"]] == [
        "0-5", "6-10", "11-20", ">20", "unknown"]
    assert {bucket["label"] for bucket in buckets["earnings_in_hold"]} <= {"yes", "no", "unknown"}
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_buckets.py`
Expected: FAIL -- `ImportError: cannot import name 'expectancy_attribution' from 'swingbot.core.analytics'`. If it fails instead on `rs_quintile_label`, V146-6 has not landed in the worktree: stop, this task waits for it.

- [ ] **Step 3: Write the module**

Create `swingbot/core/analytics/expectancy_attribution.py`:

```python
"""Expectancy attribution (v146): does today's confidence score, or any factor
inside it, rank trades by realised R?

Measurement only -- nothing here changes an alert, a gate, a level, a size or
an exit. Two populations, NEVER pooled: the live book (closed trades) and the
TRAIN confluence replay. Each becomes a list of *attribution rows* (ROW_KEYS)
and is bucketed, tested and reported on its own.

Pure apart from one loader (``load_live_rows``) and one writer
(``write_latest``, in ``swingbot.core.infra.expectancy_attribution_store``).
Numbers are stored unrounded; the results document rounds for display, so the
pre-registered verdict always compares exact values.
"""
from __future__ import annotations

import numpy as np

from swingbot.core.analytics.aggregate import rs_quintile_label
from swingbot.core.edge.frictions import apply_frictions, commission_r
from swingbot.core.market.strategy_types import HORIZONS

#: Spec: a bucket with N < 30 is shown greyed (``thin``) and enters no verdict.
#: This is the methodology's TRAIN floor; ``aggregate.MIN_CELL_N`` is untouched.
THIN_N = 30
DECILES = 10
#: Spec: sessions to the next earnings reaction session, in this order.
EARNINGS_BUCKETS = ("0-5", "6-10", "11-20", ">20", "none", "unknown")
_EARNINGS_EDGES = ((5, "0-5"), (10, "6-10"), (20, "11-20"))

#: One attribution row. ``r`` is net of frictions, ``r_gross`` is not; ``week``
#: is the Monday (ISO date) of the entry week; ``earnings_status`` is one of
#: "known" (``earnings_sessions`` is an int), "none", "unknown".
ROW_KEYS = ("r", "r_gross", "week", "confidence_score", "confidence_level",
            "confidence_points", "confidence_unevaluated", "confluence_count",
            "regime2_state", "rs_pctile", "direction", "horizon",
            "earnings_sessions", "earnings_status", "risk_reward_ratio")

#: Labels with a fixed display order; digits sort numerically after them,
#: other labels alphabetically, "unknown" last.
_ORDER = ("Q1", "Q2", "Q3", "Q4", "Q5", "0-5", "6-10", "11-20", ">20", "none",
          "yes", "no")


def quantile_bins(values: list[float], k: int) -> list[int]:
    """Bin index (0..k-1) per value, aligned with the input.

    Tied values are never split: a tied block goes wholly to the bin that
    contains its median rank. Deterministic -- no randomness, no jitter. With
    0-based sorted ranks ``a..b`` for a block of ``n`` values, the bin is
    ``floor(((a + b) / 2) * k / n)``, in integer arithmetic."""
    n = len(values)
    bins = [0] * n
    order = sorted(range(n), key=lambda index: values[index])
    start = 0
    while start < n:
        end = start
        while end + 1 < n and values[order[end + 1]] == values[order[start]]:
            end += 1
        block = min(k - 1, ((start + end) * k) // (2 * n))
        for position in range(start, end + 1):
            bins[order[position]] = block
        start = end + 1
    return bins


def earnings_bucket(row: dict) -> str:
    """One of EARNINGS_BUCKETS for a row's sessions-to-earnings reading."""
    status, sessions = row.get("earnings_status"), row.get("earnings_sessions")
    if status == "none":
        return "none"
    if status != "known" or sessions is None or sessions < 0:
        return "unknown"
    for edge, label in _EARNINGS_EDGES:
        if sessions <= edge:
            return label
    return ">20"


def earnings_in_hold(row: dict) -> str:
    """"yes" when the next earnings reaction falls inside the horizon's
    ``max_holding_days`` (sessions <= max_holding_days), "no" when it does not
    or there is provably none, "unknown" when either input is missing."""
    bucket = earnings_bucket(row)
    if bucket == "unknown":
        return "unknown"
    if bucket == "none":
        return "no"
    hold = (HORIZONS.get(row.get("horizon")) or {}).get("max_holding_days")
    if hold is None:
        return "unknown"
    return "yes" if row["earnings_sessions"] <= hold else "no"


def net_r(entry: float, stop_loss: float, direction: str, legs: list[dict]) -> float:
    """R net of frictions, recomputed from the fills leg by leg with the
    named-strategy backtest's model (``backtest.py:688-743``): the entry fill
    is worsened by slippage and re-bases the risk, every exit fill is worsened
    on the opposite side, and one round-trip commission comes off in R.

    ``legs`` is ``[{"fraction", "exit_price", ...}]``; a recorded leg ``r`` is
    ignored. Raises ValueError without legs or with a zero stop distance."""
    bullish = direction == "bullish"
    sign = 1.0 if bullish else -1.0
    entry_fill = apply_frictions(float(entry), "buy" if bullish else "sell")
    risk = abs(entry_fill - float(stop_loss))
    if not legs or risk == 0:
        raise ValueError("net_r needs at least one leg and a non-zero stop distance")
    total = 0.0
    for leg in legs:
        exit_fill = apply_frictions(float(leg["exit_price"]), "sell" if bullish else "buy")
        total += float(leg.get("fraction", 0)) * (exit_fill - entry_fill) * sign / risk
    return total - commission_r()


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def bucket_stats(rows: list[dict]) -> dict:
    """N / win rate (percent; a win is net ``r > 0``) / net and gross ExpR."""
    n = len(rows)
    return {
        "n": n,
        "win_rate": 100.0 * sum(1 for row in rows if row["r"] > 0) / n if n else None,
        "exp_r": _mean([row["r"] for row in rows]),
        "exp_r_gross": _mean([row["r_gross"] for row in rows]),
        "thin": n < THIN_N,
    }


def _scored(rows: list[dict]) -> list[dict]:
    """The confidence analyses' rows: those with a non-null score."""
    return [row for row in rows if row.get("confidence_score") is not None]


def _label(value) -> str:
    return "unknown" if value is None or value == "" else str(value)


def _sort_key(label: str) -> tuple:
    if label in _ORDER:
        return (0, _ORDER.index(label), "")
    if label.isdigit():
        return (1, int(label), "")
    return (3, 0, "") if label == "unknown" else (2, 0, label)


#: (grouping name, row -> label, confidence analysis (scored rows only)?)
_PLAIN_GROUPINGS = (
    ("confidence_level", lambda row: _label(row.get("confidence_level")), True),
    ("confluence", lambda row: _label(row.get("confluence_count")), False),
    ("regime2_state", lambda row: _label(row.get("regime2_state")), False),
    ("rs_quintile", lambda row: rs_quintile_label(row.get("rs_pctile")), False),
    ("direction", lambda row: _label(row.get("direction")), False),
    ("horizon", lambda row: _label(row.get("horizon")), False),
    ("earnings", earnings_bucket, False),
    ("earnings_in_hold", earnings_in_hold, False),
)


def _decile_groups(rows: list[dict]) -> dict[str, list[dict]]:
    """Population-quantile deciles of ``confidence_score``; a decile emptied
    by ties is simply absent. Label: ``D<k> (<lowest>-<highest> score)``."""
    scored = _scored(rows)
    bins = quantile_bins([row["confidence_score"] for row in scored], DECILES)
    groups: dict[int, list[dict]] = {}
    for row, index in zip(scored, bins):
        groups.setdefault(index, []).append(row)
    out = {}
    for index in sorted(groups):
        scores = [row["confidence_score"] for row in groups[index]]
        out[f"D{index + 1} ({min(scores):g}-{max(scores):g})"] = groups[index]
    return out


def _grouped_rows(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """grouping -> label -> member rows, in display order. The one place
    membership is decided: buckets and their looks both read it."""
    out = {"confidence_decile": _decile_groups(rows)}
    for name, label_of, scored_only in _PLAIN_GROUPINGS:
        groups: dict[str, list[dict]] = {}
        for row in (_scored(rows) if scored_only else rows):
            groups.setdefault(label_of(row), []).append(row)
        out[name] = {label: groups[label] for label in sorted(groups, key=_sort_key)}
    return out


def _quartiles(values) -> dict:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"p25": None, "median": None, "p75": None}
    p25, median, p75 = (float(x) for x in np.percentile(clean, [25, 50, 75]))
    return {"p25": p25, "median": median, "p75": p75}


def _decile_extras(rows: list[dict]) -> dict:
    return {
        "unevaluated_n": sum(1 for row in rows if row.get("confidence_unevaluated")),
        "rr": _quartiles([row.get("risk_reward_ratio") for row in rows]),
    }


def population_buckets(rows: list[dict]) -> dict[str, list[dict]]:
    """One N / WR / ExpR bucket list per grouping of ONE population.

    Groupings: confidence_decile, confidence_level (both on scored rows only),
    confluence, regime2_state, rs_quintile, direction, horizon, earnings,
    earnings_in_hold (every row). ``q`` is None until ``assign_qvalues``."""
    out: dict[str, list[dict]] = {}
    for name, groups in _grouped_rows(rows).items():
        out[name] = [{"label": label, **bucket_stats(members), "q": None}
                     for label, members in groups.items()]
        if name == "confidence_decile":
            for bucket, members in zip(out[name], groups.values()):
                bucket.update(_decile_extras(members))
    return out
```

Do not add the module to `swingbot/core/analytics/__init__.py`: every consumer imports it by its full path, and the package `__init__` stays as it is.

`net_r` recomputes R from the fill prices on purpose. The gross figure a row carries (`r_gross`) is the recorded one (`r_total` on TRAIN, `metrics.r_multiple` live); with zero slippage and zero commission `net_r` returns the plain price-derived R, which the first `net_r` test pins.

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_buckets.py`
Expected: PASS, 0 failed (28 tests).

- [ ] **Step 5: Complexity and the main-tree check**

Run: `python -m radon cc -s -n C swingbot/core/analytics/expectancy_attribution.py`
Expected: no output (every function below C).
Run: `git -C E:/Documents/Private/Projects/Discord-Bot status --short`
Expected: empty (the main tree is untouched).

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_expectancy_attribution_buckets.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): expectancy attribution study core -- tie-safe bins, buckets, net R"
```

---

### Task V146-11: Study statistics: monotonicity, factor deltas, BH, verdict

**Model:** opus -- this is the pre-registered verdict rule and its interval; every threshold and comparison operator is fixed by the spec and must be reproduced exactly.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (created by V146-10; this task appends, it changes no V146-10 function)
- Create: `tests/analytics/test_expectancy_attribution_stats.py`

**Interfaces:**
- Consumes: V146-10's `THIN_N`, `quantile_bins`, `population_buckets`, `_scored`, `_grouped_rows`, `_quartiles`, `_mean`; `stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray` (`swingbot/core/backtesting/instrument/stats.py:57`; groups by `getattr(trade, "entry_date")`, calls `statistic(b_draw, c_draw)`, drops a `None` draw); `stats.bh_qvalues(pvalues) -> list` (`:86`; `None` passes through and does not count toward the family); `stats.WEEK_BOOTSTRAP_RESAMPLES` (10,000).
- Produces (index ledger):
  - `monotonicity(rows, *, seed: int) -> dict` (`n, spearman_rho, tercile_spread, ci_low, ci_high, p, inverted, tercile_n, rr_by_tercile`); `tercile_n` and `rr_by_tercile` are `[bottom, middle, top]`.
  - `factor_deltas(rows, *, seed: int) -> list[dict]` (`key, n, n_pos, n_zero, delta, ci_low, ci_high, p, q`)
  - `bucket_looks(rows, buckets, *, seed: int) -> None` (fills `ci_low, ci_high, p` on non-thin buckets; it also writes `delta`, the point estimate those three describe, and leaves all four `None` where there is no look)
  - `assign_qvalues(populations: dict) -> int` (returns `looks`)
  - `population_passes(mono: dict) -> bool`; `verdict(live_mono: dict | None, train_mono: dict | None) -> str`
  - Module constants `N_RESAMPLES`, `MIN_SPREAD_R = 0.10`, `VERDICTS`, `ABSENT_IS_ZERO`.
  - `tests/analytics/test_expectancy_attribution_stats.py::population(kind, n=180)` -- the synthetic population builder V146-12's test file imports.
- The verdict rule, verbatim from the spec ("The verdict (pre-registered here)"), on the top-minus-bottom tercile ExpR CI:
  - **PREDICTIVE** -- lower bound > 0 **and** point estimate >= +0.10R in **both** populations.
  - **WEAK** -- that holds in exactly one.
  - **NOT PREDICTIVE** -- otherwise. A CI wholly below zero is reported as "inverted" inside this verdict, not as a fourth one.
  - A tercile whose N < 30 makes its population's clause fail. No threshold is chosen from these tables.
- Other spec rules fixed here: the CI is a 95% bootstrap via `week_cluster_bootstrap` with the seed recorded; "Tercile cut points are fixed once on the full sample, not recomputed per resample"; the per-factor delta excludes rows where the factor is in `confidence_unevaluated`; a bucket or factor is a screen candidate only if its BH q over **all** looks is < 0.10 (this task computes q; nothing in code acts on the 0.10).

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_expectancy_attribution_stats.py`:

```python
"""v146 study statistics: the week-clustered tercile spread, per-factor
deltas, bucket looks, BH over every look and the pre-registered verdict, on
synthetic populations built to be predictive, flat and inverted."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.market.strategy_types import HORIZONS

HK = next(iter(HORIZONS))
SEED = 42
MONO_KEYS = ["n", "spearman_rho", "tercile_spread", "ci_low", "ci_high", "p",
             "inverted", "tercile_n", "rr_by_tercile"]


def population(kind: str, n: int = 180) -> list[dict]:
    """Deterministic rows: score i (distinct), R = slope * (rank - 0.5) plus a
    fixed zero-mean wobble, spread over 30 entry weeks. ``predictive`` has a
    +0.4R top-minus-bottom tercile spread, ``inverted`` -0.4R, ``flat`` none."""
    slope = {"predictive": 0.6, "flat": 0.0, "inverted": -0.6}[kind]
    rows = []
    for i in range(n):
        r = slope * (i / (n - 1) - 0.5) + ((i * 37) % 11 - 5) / 10.0
        points = {"MACD momentum": 10 if i >= n // 2 else 0,
                  "ADX trend strength": 7 if i % 5 == 0 else (15 if i % 2 else 0)}
        if i % 3 == 0:
            points["Tight stop penalty"] = -5
        rows.append({
            "r": r, "r_gross": r + 0.03,
            "week": (dt.date(2024, 1, 1) + dt.timedelta(weeks=i % 30)).isoformat(),
            "confidence_score": i, "confidence_level": 3 + (3 * i) // n,
            "confidence_points": points,
            "confidence_unevaluated": ["ADX trend strength"] if i % 5 == 0 else [],
            "confluence_count": 2 + i % 3, "regime2_state": "bull_quiet",
            "rs_pctile": float(i % 100),
            "direction": "bullish" if i % 3 else "bearish", "horizon": HK,
            "earnings_sessions": i % 40, "earnings_status": "known",
            "risk_reward_ratio": 1.5 + (i % 4) / 4.0,
        })
    return rows


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 300)


def test_a_predictive_population_passes_its_clause():
    mono = ea.monotonicity(population("predictive"), seed=SEED)
    assert list(mono) == MONO_KEYS
    assert mono["n"] == 180 and mono["tercile_n"] == [60, 60, 60]
    assert mono["tercile_spread"] == pytest.approx(0.4, abs=0.05)
    assert 0 < mono["ci_low"] < mono["tercile_spread"] < mono["ci_high"]
    assert mono["spearman_rho"] > 0.2 and mono["p"] < 0.05
    assert mono["inverted"] is False
    assert len(mono["rr_by_tercile"]) == 3 and set(mono["rr_by_tercile"][0]) == {"p25", "median", "p75"}
    assert ea.population_passes(mono) is True


def test_a_flat_population_fails_its_clause():
    mono = ea.monotonicity(population("flat"), seed=SEED)
    assert abs(mono["tercile_spread"]) < 0.10
    assert mono["inverted"] is False
    assert ea.population_passes(mono) is False


def test_an_inverted_population_is_flagged_and_fails():
    mono = ea.monotonicity(population("inverted"), seed=SEED)
    assert mono["ci_high"] < 0 and mono["inverted"] is True
    assert mono["spearman_rho"] < 0
    assert ea.population_passes(mono) is False


def test_the_same_seed_reproduces_the_interval():
    rows = population("predictive")
    first, second = ea.monotonicity(rows, seed=7), ea.monotonicity(rows, seed=7)
    assert (first["ci_low"], first["ci_high"], first["p"]) == (
        second["ci_low"], second["ci_high"], second["p"])


def test_tercile_cuts_are_fixed_once_on_the_full_sample(monkeypatch):
    calls = []
    real = ea.quantile_bins

    def counting(values, k):
        calls.append((len(values), k))
        return real(values, k)

    monkeypatch.setattr(ea, "quantile_bins", counting)
    ea.monotonicity(population("predictive"), seed=SEED)
    assert calls == [(180, 3)]          # never once per bootstrap resample


def test_unscored_rows_stay_out_of_the_confidence_analysis():
    rows = population("predictive")
    extra = [dict(row, confidence_score=None, r=-5.0) for row in rows[:50]]
    assert ea.monotonicity(rows + extra, seed=SEED) == ea.monotonicity(rows, seed=SEED)


def test_a_thin_tercile_gets_no_interval_and_fails_the_clause():
    mono = ea.monotonicity(population("predictive", n=60), seed=SEED)
    assert mono["tercile_n"] == [20, 20, 20]
    assert mono["tercile_spread"] > 0.3            # the point estimate is still shown
    assert mono["ci_low"] is None and mono["ci_high"] is None and mono["p"] is None
    assert ea.population_passes(mono) is False


def test_whole_weeks_are_resampled():
    # One entry week: every resample is the same week repeated, so the
    # interval collapses onto the point estimate. Row-level resampling would not.
    rows = [dict(row, week="2024-03-04") for row in population("predictive")]
    mono = ea.monotonicity(rows, seed=SEED)
    assert mono["ci_low"] == pytest.approx(mono["tercile_spread"])
    assert mono["ci_high"] == pytest.approx(mono["tercile_spread"])


def test_bootstrap_p_is_two_sided_with_the_plus_one_correction(monkeypatch):
    monkeypatch.setattr(ea.stats, "week_cluster_bootstrap",
                        lambda *args, **kwargs: np.array([1.0, 1.0, 1.0, -1.0]))
    mono = ea.monotonicity(population("predictive"), seed=SEED)
    assert mono["p"] == pytest.approx(2 * (1 + 1) / (4 + 1))   # one draw <= 0, of four


def test_factor_deltas_cover_every_key_and_skip_unevaluated_rows():
    factors = {item["key"]: item for item in ea.factor_deltas(population("predictive"), seed=SEED)}
    assert list(factors) == ["ADX trend strength", "MACD momentum", "Tight stop penalty"]
    assert list(factors["MACD momentum"]) == ["key", "n", "n_pos", "n_zero", "delta",
                                              "ci_low", "ci_high", "p", "q"]
    adx = factors["ADX trend strength"]
    assert adx["n"] == 144                              # 36 fallback rows left out
    assert adx["n_pos"] + adx["n_zero"] == 144
    macd = factors["MACD momentum"]
    assert (macd["n_pos"], macd["n_zero"]) == (90, 90)
    assert macd["delta"] == pytest.approx(0.3, abs=0.05) and macd["ci_low"] > 0
    assert macd["q"] is None                            # assign_qvalues fills it


def test_a_penalty_key_reads_zero_when_absent_but_other_keys_do_not():
    rows = population("predictive")
    other_scorer = [dict(row, confidence_points={"gap": 0}) for row in rows[:30]]
    factors = {item["key"]: item for item in ea.factor_deltas(rows + other_scorer, seed=SEED)}
    penalty = factors["Tight stop penalty"]
    assert (penalty["n_pos"], penalty["n_zero"]) == (60, 150)   # absent = not applied
    assert factors["MACD momentum"]["n"] == 180                 # the other scorer's rows are out
    assert factors["gap"]["n_pos"] == 0 and factors["gap"]["p"] is None


def test_bucket_looks_fill_the_interval_on_non_thin_buckets_only():
    rows = population("predictive")
    buckets = ea.population_buckets(rows)
    ea.bucket_looks(rows, buckets, seed=SEED)
    bearish, bullish = buckets["direction"]
    assert (bearish["label"], bullish["label"]) == ("bearish", "bullish")
    assert bearish["delta"] == pytest.approx(bearish["exp_r"] - bullish["exp_r"])
    assert bearish["ci_low"] <= bearish["delta"] <= bearish["ci_high"]
    assert 0 < bearish["p"] <= 1
    for decile in buckets["confidence_decile"]:               # 18 rows each: thin
        assert decile["thin"] and decile["p"] is None and decile["ci_low"] is None
    lone = buckets["regime2_state"][0]                        # nothing to compare against
    assert lone["delta"] is None and lone["p"] is None


def _population_dict(rows):
    buckets = ea.population_buckets(rows)
    ea.bucket_looks(rows, buckets, seed=SEED)
    return {"monotonicity": ea.monotonicity(rows, seed=SEED),
            "factors": ea.factor_deltas(rows, seed=SEED), "buckets": buckets,
            "splits": {"direction": {"bullish": ea.monotonicity(
                [row for row in rows if row["direction"] == "bullish"], seed=SEED)}}}


def test_assign_qvalues_runs_bh_over_every_look_of_both_populations():
    populations = {"live": _population_dict(population("flat")),
                   "train": _population_dict(population("predictive"))}
    holders = [holder for name in ("live", "train")
               for holder, _ in ea._look_holders(populations[name])]
    expected = sum(1 for holder in holders if holder.get("p") is not None)
    looks = ea.assign_qvalues(populations)
    assert looks == expected and looks > 10
    for name in ("live", "train"):
        assert "q" not in populations[name]["monotonicity"]
        takers = populations[name]["factors"] + [
            bucket for grouping in populations[name]["buckets"].values() for bucket in grouping]
        for item in takers:
            assert (item["q"] is None) == (item["p"] is None)
            if item["p"] is not None:
                assert item["p"] <= item["q"] <= 1.0


def test_assign_qvalues_accepts_a_missing_population():
    populations = {"live": None, "train": _population_dict(population("predictive"))}
    assert ea.assign_qvalues(populations) > 0


@pytest.mark.parametrize("spread, low, tercile_n, expected", [
    (0.10, 0.01, [30, 30, 30], True),      # exactly at both floors
    (0.0999, 0.01, [30, 30, 30], False),   # point estimate under +0.10R
    (0.25, 0.0, [30, 30, 30], False),      # lower bound must be > 0, not >= 0
    (0.25, 0.05, [30, 29, 30], False),     # any tercile under 30
    (0.25, None, [60, 60, 60], False),     # no interval
])
def test_population_passes_is_the_pre_registered_clause(spread, low, tercile_n, expected):
    mono = {"tercile_spread": spread, "ci_low": low, "ci_high": 1.0, "tercile_n": tercile_n}
    assert ea.population_passes(mono) is expected


def test_population_passes_refuses_a_missing_population():
    assert ea.population_passes(None) is False
    assert ea.population_passes({}) is False


def test_verdict_counts_the_populations_that_pass():
    good = ea.monotonicity(population("predictive"), seed=SEED)
    flat = ea.monotonicity(population("flat"), seed=SEED)
    inverted = ea.monotonicity(population("inverted"), seed=SEED)
    assert ea.verdict(good, good) == "PREDICTIVE"
    assert ea.verdict(good, flat) == "WEAK"
    assert ea.verdict(inverted, good) == "WEAK"
    assert ea.verdict(flat, inverted) == "NOT PREDICTIVE"
    assert ea.verdict(None, good) == "WEAK"
    assert ea.verdict(None, None) == "NOT PREDICTIVE"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_stats.py`
Expected: FAIL -- an `AttributeError` ending `has no attribute 'N_RESAMPLES'` (raised by the autouse fixture), on every test.

- [ ] **Step 3: Extend the import block**

In `swingbot/core/analytics/expectancy_attribution.py`, add `from typing import NamedTuple` above `import numpy as np`, and add the `stats` import after the `aggregate` one, so the block reads:

```python
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from swingbot.core.analytics.aggregate import rs_quintile_label
from swingbot.core.backtesting.instrument import stats
from swingbot.core.edge.frictions import apply_frictions, commission_r
from swingbot.core.market.strategy_types import HORIZONS
```

`swingbot.core.backtesting.instrument.stats` imports numpy and the stdlib only, and both package `__init__` files on the way are empty, so this adds no import cycle (`swingbot/core/analytics/insights.py:142` already imports from `swingbot.core.backtesting`).

- [ ] **Step 4: Append the statistics**

Append to the end of `swingbot/core/analytics/expectancy_attribution.py`:

```python
# --------------------------------------------------------------------------
# Statistics: week-clustered looks, monotonicity, factor deltas, BH, verdict.
# --------------------------------------------------------------------------

#: Bootstrap replicates per look (pre-registered default, 10,000).
N_RESAMPLES = stats.WEEK_BOOTSTRAP_RESAMPLES
TERCILES = 3
#: Spec, "The verdict": point estimate >= +0.10R (and CI lower bound > 0).
MIN_SPREAD_R = 0.10
VERDICTS = ("PREDICTIVE", "WEAK", "NOT PREDICTIVE")
#: Factor keys that exist on a row only when they fired: their absence is a
#: reading of 0. Any other key absent from a row means another scorer wrote
#: that row, and the row is left out of that factor's look.
ABSENT_IS_ZERO = frozenset({"Tight stop penalty"})


class _Obs(NamedTuple):
    """One arm's rows of one entry week, summed. ``entry_date`` is the week's
    Monday, which is what ``stats.group_by_week`` keys on."""
    entry_date: str
    total: float
    n: int


def _week_sums(rows: list[dict]) -> list[_Obs]:
    sums: dict[str, tuple[float, int]] = {}
    for row in rows:
        total, n = sums.get(row["week"], (0.0, 0))
        sums[row["week"]] = (total + row["r"], n + 1)
    return [_Obs(week, total, n) for week, (total, n) in sorted(sums.items())]


def _mean_gap(base: list[_Obs], comp: list[_Obs]) -> float | None:
    """ExpR(comp) - ExpR(base) for one resample; None when an arm is empty
    (the bootstrap drops that draw, it never zero-fills it)."""
    base_n, comp_n = sum(obs.n for obs in base), sum(obs.n for obs in comp)
    if not base_n or not comp_n:
        return None
    return sum(obs.total for obs in comp) / comp_n - sum(obs.total for obs in base) / base_n


def _look(base_rows: list[dict], comp_rows: list[dict], seed: int) -> dict:
    """One look: ExpR(comp) - ExpR(base), its 95% week-clustered bootstrap CI
    and a two-sided bootstrap p. An arm under THIN_N rows gets the point
    estimate only -- no interval, no p, so it never enters the BH family."""
    out = {"delta": None, "ci_low": None, "ci_high": None, "p": None}
    if base_rows and comp_rows:
        out["delta"] = _mean([row["r"] for row in comp_rows]) - _mean([row["r"] for row in base_rows])
    if min(len(base_rows), len(comp_rows)) < THIN_N:
        return out
    draws = stats.week_cluster_bootstrap(_week_sums(base_rows), _week_sums(comp_rows),
                                         _mean_gap, n_resamples=N_RESAMPLES, seed=seed)
    if not len(draws):
        return out
    low, high = np.percentile(draws, [2.5, 97.5])
    tail = min(int((draws <= 0).sum()), int((draws >= 0).sum())) + 1
    out.update(ci_low=float(low), ci_high=float(high),
               p=min(1.0, 2.0 * tail / (len(draws) + 1)))
    return out


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks, ties sharing their mean rank."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2.0 + 1.0
        start = end + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho (Pearson on mean ranks); None under 3 points or when one
    side is constant. numpy only: scipy is not a dependency."""
    if len(xs) < 3:
        return None
    rank_x, rank_y = np.asarray(_ranks(xs)), np.asarray(_ranks(ys))
    if rank_x.std() == 0 or rank_y.std() == 0:
        return None
    return float(np.corrcoef(rank_x, rank_y)[0, 1])


def _terciles(scored: list[dict]) -> list[list[dict]]:
    """[bottom, middle, top] by ``confidence_score``; ties never split."""
    bins = quantile_bins([row["confidence_score"] for row in scored], TERCILES)
    return [[row for row, index in zip(scored, bins) if index == third]
            for third in range(TERCILES)]


def monotonicity(rows: list[dict], *, seed: int) -> dict:
    """Does ``confidence_score`` rank R? Spearman rho and the top-minus-bottom
    tercile ExpR with its week-clustered CI, on the scored rows.

    The tercile of every row is fixed ONCE here, on the full sample; the
    bootstrap resamples weeks of rows that keep their tercile."""
    scored = _scored(rows)
    thirds = _terciles(scored)
    look = _look(thirds[0], thirds[-1], seed)
    return {
        "n": len(scored),
        "spearman_rho": _spearman([row["confidence_score"] for row in scored],
                                  [row["r"] for row in scored]),
        "tercile_spread": look["delta"],
        "ci_low": look["ci_low"],
        "ci_high": look["ci_high"],
        "p": look["p"],
        "inverted": look["ci_high"] is not None and look["ci_high"] < 0,
        "tercile_n": [len(third) for third in thirds],
        "rr_by_tercile": [_quartiles([row.get("risk_reward_ratio") for row in third])
                          for third in thirds],
    }


def _factor_arms(rows: list[dict], key: str) -> tuple[list[dict], list[dict]]:
    """(rows where the factor scored, rows where it scored 0). A row that
    lists the factor in ``confidence_unevaluated`` is in neither arm: "no
    data" is never a positive reading."""
    scored_rows, zero_rows = [], []
    for row in rows:
        points = row.get("confidence_points")
        if not isinstance(points, dict) or key in (row.get("confidence_unevaluated") or ()):
            continue
        if key not in points and key not in ABSENT_IS_ZERO:
            continue
        (scored_rows if points.get(key, 0) != 0 else zero_rows).append(row)
    return scored_rows, zero_rows


def factor_deltas(rows: list[dict], *, seed: int) -> list[dict]:
    """Per factor key: ExpR where it scored minus ExpR where it scored 0."""
    keys = sorted({key for row in rows for key in (row.get("confidence_points") or {})})
    out = []
    for key in keys:
        scored_rows, zero_rows = _factor_arms(rows, key)
        look = _look(zero_rows, scored_rows, seed)
        out.append({"key": key, "n": len(scored_rows) + len(zero_rows),
                    "n_pos": len(scored_rows), "n_zero": len(zero_rows),
                    "delta": look["delta"], "ci_low": look["ci_low"],
                    "ci_high": look["ci_high"], "p": look["p"], "q": None})
    return out


def bucket_looks(rows: list[dict], buckets: dict[str, list[dict]], *, seed: int) -> None:
    """Fill ``delta, ci_low, ci_high, p`` on every bucket, in place: the
    bucket's ExpR minus the ExpR of the rest of its own grouping. A thin
    bucket (or a thin rest) keeps None for the interval and the p."""
    for name, groups in _grouped_rows(rows).items():
        for bucket in buckets.get(name, ()):
            inside = groups.get(bucket["label"], [])
            members = {id(row) for row in inside}
            rest = [row for group in groups.values() for row in group
                    if id(row) not in members]
            bucket.update(_look(rest, inside, seed))


def _look_holders(population: dict | None) -> list[tuple[dict, bool]]:
    """Every dict of one population that carries a ``p``, with whether it
    takes a ``q`` (buckets and factors do; monotonicity keeps its shape)."""
    if not population:
        return []
    holders = [(population["monotonicity"], False)]
    for split in (population.get("splits") or {}).values():
        holders.extend((mono, False) for mono in split.values())
    holders.extend((factor, True) for factor in population.get("factors") or ())
    for grouping in (population.get("buckets") or {}).values():
        holders.extend((bucket, True) for bucket in grouping)
    return holders


def assign_qvalues(populations: dict) -> int:
    """Benjamini-Hochberg over EVERY look of both populations (one family).
    Writes ``q`` on buckets and factors and returns ``looks``, the family
    size (the number of non-null p-values)."""
    holders = [holder for name in ("live", "train")
               for holder in _look_holders(populations.get(name))]
    qvalues = stats.bh_qvalues([holder.get("p") for holder, _ in holders])
    for (holder, takes_q), q in zip(holders, qvalues):
        if takes_q:
            holder["q"] = q
    return sum(1 for q in qvalues if q is not None)


def population_passes(mono: dict) -> bool:
    """One population's clause of the pre-registered verdict: CI lower bound
    > 0 AND point estimate >= +0.10R; any tercile with N < 30 fails it."""
    if not mono or min(mono.get("tercile_n") or [0]) < THIN_N:
        return False
    low, spread = mono.get("ci_low"), mono.get("tercile_spread")
    return low is not None and spread is not None and low > 0 and spread >= MIN_SPREAD_R


def verdict(live_mono: dict | None, train_mono: dict | None) -> str:
    """PREDICTIVE when the clause holds in both populations, WEAK in exactly
    one, NOT PREDICTIVE otherwise. An inverted CI is reported through the
    monotonicity dict's ``inverted`` flag, inside NOT PREDICTIVE or WEAK."""
    passed = sum(1 for mono in (live_mono, train_mono) if population_passes(mono))
    return VERDICTS[2 - passed]
```

Three things an implementer must not "tidy":

- `_Obs` holds a *week's sum* for one arm, not one trade. Resampling whole weeks of sums is the same resample as whole weeks of trades (the statistic is a ratio of sums), and it keeps a 10,000-replicate look to seconds on the TRAIN population.
- `_look` is called through `stats.week_cluster_bootstrap` and reads `N_RESAMPLES` at call time (never as a default argument), so the tests can patch both.
- `population_passes` compares the unrounded numbers with `>` for the bound and `>=` for the point estimate. Do not round before comparing and do not swap either operator.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_stats.py`
Expected: PASS, 0 failed (21 tests).
Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_buckets.py`
Expected: PASS, 0 failed (V146-10's tests still hold; `bucket_looks` only adds keys after the first seven).

- [ ] **Step 6: Complexity and the main-tree check**

Run: `python -m radon cc -s -n C swingbot/core/analytics/expectancy_attribution.py`
Expected: no output (every function below C).
Run: `git -C E:/Documents/Private/Projects/Discord-Bot status --short`
Expected: empty (the main tree is untouched).

- [ ] **Step 7: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_expectancy_attribution_stats.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): expectancy attribution statistics -- week-clustered spread, BH over every look, the pre-registered verdict"
```

---
