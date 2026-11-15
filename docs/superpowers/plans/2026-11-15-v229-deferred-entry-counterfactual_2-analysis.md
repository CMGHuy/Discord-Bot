# v229 — Deferred-entry counterfactual: Part 2 — analysis (V229-6..V229-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V229-7" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-14-v229-deferred-entry-counterfactual-design.md](../specs/2026-11-14-v229-deferred-entry-counterfactual-design.md)
**Index:** [2026-11-15-v229-deferred-entry-counterfactual_0-index.md](2026-11-15-v229-deferred-entry-counterfactual_0-index.md) — Global Constraints, Parallelisation, the task ledger, the shared shapes (PAIR, DELTA, CALIBRATION, FROZEN) and the Handoff resolutions all live there and bind every task below.

Scope: the append-once pair log, the statistics and calibration, the frozen rule with its window and verdict guard, the results Markdown and JSON, and the CLI that wires part 1's modules to these.

Conventions for every task in this part:

- Modules live in `scripts/reports/deferred_entry/` and import their siblings relatively (`from . import bars`), the `scripts/reports/autopsy/` precedent. Tests put `scripts/reports` on `sys.path` and import `from deferred_entry import <module>`.
- Tests build PAIR dicts by hand through a small local `_pair(...)` helper, so V229-6..V229-9 depend on part 1 only through the PAIR shape in the index.
- Every function stays below cyclomatic complexity 15 (`python scripts/dev/complexity_gate.py` scans `scripts/` and `tests/`). Verification is the narrow run only; no task runs the full suite.
- Work in the plan's worktree; never `cd` in Bash (use absolute paths or `git -C <worktree>`).

# Phase 2 — analysis

### Task V229-6: Append-once pair log

**Model:** sonnet — one self-contained file-format module with a precise contract; no trading judgement.

**Files:**
- Create: `scripts/reports/deferred_entry/pairlog.py`
- Test: `tests/scripts/test_deferred_entry_pairlog.py`

**Interfaces:**
- Consumes: nothing from earlier tasks except the package `scripts/reports/deferred_entry/__init__.py` (V229-1). A pair is any JSON-serialisable dict with a non-empty `trade_id` (the PAIR shape in the index).
- Produces (index ledger, plus one additive keyword):
  - `DEFAULT_LOG = "data/v229/pairs.jsonl"` (relative; the container's cwd is `/app`, so it resolves to the host mount `/opt/swing-bot/data/v229/pairs.jsonl`).
  - `class PairLogError(ValueError)`.
  - `read_pairs(path) -> dict[str, dict]`: `trade_id -> pair` in file order. Missing file -> `{}`. A last line without its trailing newline is a torn write: the file is truncated to the last complete line and the torn row is dropped (so the next append redoes that trade). A malformed complete line, a line that is not an object with a non-empty `trade_id`, or a duplicate `trade_id` -> `PairLogError` naming the line number. Blank lines are skipped.
  - `append_pair(path, pair, *, known: set[str] | None = None) -> None`: refuses a pair without `trade_id` and a duplicate `trade_id` (`PairLogError`, file untouched); writes exactly one line (`json.dumps(pair, sort_keys=True, allow_nan=False) + "\n"`), flushes and fsyncs; creates parent directories. `known`, when given, is the caller's set of ids already in the log (from `read_pairs`) and is updated in place, so a run appending hundreds of pairs does not re-read the file per append; without it the file is re-read.

Why fsync and torn-tail recovery: the log is the long run's checkpoint (`working-conventions.md` § Long runs must checkpoint). A cron run killed mid-write leaves at most one partial last line; refusing it would wedge every later weekly run, so it is dropped and redone (spec § 2), while a malformed line *inside* the file means something else wrote to it and is refused.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_pairlog.py`:

```python
"""v229 pair log: append once per trade id, never rewritten, torn tail redone."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import pairlog  # noqa: E402


def _pair(trade_id, **extra):
    return {"trade_id": trade_id, "entry_date": "2026-11-03", "rule_hash": "0123abcd4567ef89", **extra}


def test_default_log_is_the_relative_data_path():
    assert pairlog.DEFAULT_LOG == "data/v229/pairs.jsonl"


def test_a_missing_log_reads_as_empty(tmp_path):
    assert pairlog.read_pairs(tmp_path / "nope.jsonl") == {}


def test_append_then_read_round_trips_in_file_order(tmp_path):
    path = tmp_path / "v229" / "pairs.jsonl"          # parent does not exist yet
    for tid in ("t-2", "t-1", "t-3"):
        pairlog.append_pair(path, _pair(tid, arms={"C": {"r_net": -1.02}}))
    pairs = pairlog.read_pairs(path)
    assert list(pairs) == ["t-2", "t-1", "t-3"]
    assert pairs["t-1"]["arms"]["C"]["r_net"] == pytest.approx(-1.02)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n") and text.count("\n") == 3


def test_a_duplicate_trade_id_is_refused_and_the_file_is_untouched(tmp_path):
    path = tmp_path / "pairs.jsonl"
    pairlog.append_pair(path, _pair("t-1"))
    before = path.read_bytes()
    with pytest.raises(pairlog.PairLogError, match="t-1"):
        pairlog.append_pair(path, _pair("t-1", note="again"))
    assert path.read_bytes() == before


def test_known_ids_skip_the_reread_and_are_updated(tmp_path, monkeypatch):
    path = tmp_path / "pairs.jsonl"
    known = set(pairlog.read_pairs(path))
    monkeypatch.setattr(pairlog, "read_pairs", lambda _p: pytest.fail("re-read despite known"))
    pairlog.append_pair(path, _pair("t-1"), known=known)
    pairlog.append_pair(path, _pair("t-2"), known=known)
    assert known == {"t-1", "t-2"}
    with pytest.raises(pairlog.PairLogError):
        pairlog.append_pair(path, _pair("t-2"), known=known)


def test_a_pair_without_trade_id_is_refused(tmp_path):
    with pytest.raises(pairlog.PairLogError, match="trade_id"):
        pairlog.append_pair(tmp_path / "pairs.jsonl", {"entry_date": "2026-11-03"})
    assert not (tmp_path / "pairs.jsonl").exists()


def test_nan_is_refused_rather_than_written_as_invalid_json(tmp_path):
    with pytest.raises(pairlog.PairLogError, match="serialis"):
        pairlog.append_pair(tmp_path / "pairs.jsonl", _pair("t-1", r=float("nan")))


def test_every_append_is_fsynced(tmp_path, monkeypatch):
    calls = []
    real = pairlog.os.fsync
    monkeypatch.setattr(pairlog.os, "fsync", lambda fd: (calls.append(fd), real(fd)))
    pairlog.append_pair(tmp_path / "pairs.jsonl", _pair("t-1"))
    assert len(calls) == 1


def test_a_torn_last_line_is_dropped_truncated_and_redone(tmp_path):
    path = tmp_path / "pairs.jsonl"
    pairlog.append_pair(path, _pair("t-1"))
    pairlog.append_pair(path, _pair("t-2"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"trade_id": "t-3", "arms": {"C"')          # killed mid-write
    assert list(pairlog.read_pairs(path)) == ["t-1", "t-2"]
    assert path.read_text(encoding="utf-8").count("\n") == 2
    pairlog.append_pair(path, _pair("t-3"))
    assert list(pairlog.read_pairs(path)) == ["t-1", "t-2", "t-3"]


def test_a_complete_json_tail_without_newline_is_still_torn(tmp_path):
    """append_pair writes line+newline in one call, so a line without its
    newline was never finished, even when the bytes happen to parse."""
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\n" + json.dumps(_pair("t-2")), encoding="utf-8")
    assert list(pairlog.read_pairs(path)) == ["t-1"]


def test_a_malformed_line_inside_the_file_is_refused(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\nnot json\n" + json.dumps(_pair("t-3")) + "\n",
                    encoding="utf-8")
    with pytest.raises(pairlog.PairLogError, match="line 2"):
        pairlog.read_pairs(path)


@pytest.mark.parametrize("line", ['["t-1"]', '{"entry_date": "2026-11-03"}', '{"trade_id": ""}'])
def test_a_line_that_is_not_a_pair_is_refused(tmp_path, line):
    path = tmp_path / "pairs.jsonl"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(pairlog.PairLogError, match="line 1"):
        pairlog.read_pairs(path)


def test_a_duplicate_id_already_in_the_file_is_refused(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\n" + json.dumps(_pair("t-1")) + "\n", encoding="utf-8")
    with pytest.raises(pairlog.PairLogError, match="duplicate"):
        pairlog.read_pairs(path)


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps(_pair("t-1")) + "\n\n" + json.dumps(_pair("t-2")) + "\n", encoding="utf-8")
    assert list(pairlog.read_pairs(path)) == ["t-1", "t-2"]


def test_an_empty_file_reads_as_empty(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_bytes(b"")
    assert pairlog.read_pairs(path) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_pairlog.py`
Expected: FAIL at collection with `ImportError: cannot import name 'pairlog'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/deferred_entry/pairlog.py`:

```python
"""v229 pair log: one JSON line per eligible plan, appended once, never rewritten.

``data/v229/pairs.jsonl`` is the long run's checkpoint (spec section 2): each
finished trade is one line, flushed and fsynced, so a verdict never
re-derives twelve weeks and a restart skips trade ids already present. A
killed run leaves at most one line without its newline; that torn tail is
dropped and the trade redone. A malformed line inside the file is refused:
something other than ``append_pair`` wrote it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_LOG = "data/v229/pairs.jsonl"


class PairLogError(ValueError):
    """A log line that is not a pair, or a duplicate trade id."""


def _parse(line: str, lineno: int) -> dict:
    try:
        row = json.loads(line)
    except ValueError as exc:
        raise PairLogError(f"pair log line {lineno} is not JSON: {exc}") from exc
    if not isinstance(row, dict) or not row.get("trade_id"):
        raise PairLogError(f"pair log line {lineno} is not a pair (no trade_id)")
    return row


def _drop_torn_tail(path: Path, data: bytes) -> bytes:
    """Truncate a last line that never got its newline; return the kept bytes."""
    if not data or data.endswith(b"\n"):
        return data
    keep = data.rfind(b"\n") + 1
    with path.open("r+b") as handle:
        handle.truncate(keep)
        handle.flush()
        os.fsync(handle.fileno())
    return data[:keep]


def read_pairs(path) -> dict[str, dict]:
    """``trade_id -> pair`` in file order; a missing file is an empty log."""
    path = Path(path)
    if not path.exists():
        return {}
    data = _drop_torn_tail(path, path.read_bytes())
    out: dict[str, dict] = {}
    for lineno, line in enumerate(data.decode("utf-8").split("\n"), start=1):
        if not line.strip():
            continue
        row = _parse(line, lineno)
        if row["trade_id"] in out:
            raise PairLogError(f"pair log line {lineno}: duplicate trade_id {row['trade_id']!r}")
        out[row["trade_id"]] = row
    return out


def _line(pair: dict) -> str:
    try:
        return json.dumps(pair, sort_keys=True, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise PairLogError(f"pair {pair.get('trade_id')!r} is not JSON-serialisable: {exc}") from exc


def append_pair(path, pair: dict, *, known: set[str] | None = None) -> None:
    """Append one pair; refuse a missing or duplicate ``trade_id``.

    ``known`` is the caller's set of ids already logged (from ``read_pairs``);
    it is updated in place. Without it the log is re-read."""
    trade_id = pair.get("trade_id") if isinstance(pair, dict) else None
    if not trade_id:
        raise PairLogError("a pair needs a non-empty trade_id")
    path = Path(path)
    ids = known if known is not None else set(read_pairs(path))
    if trade_id in ids:
        raise PairLogError(f"trade_id {trade_id!r} is already in the pair log")
    line = _line(pair)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    ids.add(trade_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_pairlog.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function well under 15).

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry/pairlog.py tests/scripts/test_deferred_entry_pairlog.py
git commit -m "feat(v229): append-once pair log with torn-tail recovery (V229-6)"
```

### Task V229-7: Arm summaries and week-clustered deltas

**Model:** opus — the verdict's statistics: bootstrap call shape, one-sided bound and skip accounting must match the spec exactly.

Split from the ledger's V229-7 (past 20 KB): this task creates `analysis.py` with the path classes, the arm summaries and the deltas; **V229-7b** appends calibration, per-week, split and skip summaries to the same module.

**Files:**
- Create: `scripts/reports/deferred_entry/analysis.py`
- Create: `tests/scripts/test_deferred_entry_analysis.py`

**Interfaces:**
- Consumes: the PAIR shape (index § Shared shapes): `pair["entry_date"]` (ISO ET date), `pair["arms"][arm]` with `taken`, `outcome`, `r_net`, `r_gross`. From `swingbot/core/backtesting/instrument/stats.py`: `week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray` (:57), `iso_week_key(entry_date) -> "YYYY-Www"` (:28), `WEEK_BOOTSTRAP_RESAMPLES = 10_000` (:23), `WEEK_BOOTSTRAP_SEED = 42` (:25). No code from V229-2..V229-6.
- Produces (index ledger; DELTA shape exactly as in the index):
  - `LOWER_PCT = 2.5`, `CALIBRATION_MIN = 0.80`, `CLASSES = ("loss", "scratch", "win")` (V229-10's test pins the first two against `verdict.FROZEN`).
  - `live_class(reason) -> str | None`; `sim_class(outcome) -> str | None`.
  - `arm_r(pair, arm, field="r_net") -> float` (a leg not taken scores 0.0) — additive helper, used by V229-7b and V229-9.
  - `week_count(pairs) -> int` (distinct ISO weeks of `entry_date`) — additive helper, used by V229-10.
  - `arm_summary(pairs, arm) -> dict` keys `n, taken, wins, win_rate, exp_r, total_r, exp_r_gross`.
  - `delta_stats(pairs, arm, *, n_resamples=10_000, seed=WEEK_BOOTSTRAP_SEED) -> dict` (DELTA).
  - `delta_over_taken(pairs, arm) -> dict` keys `n, mean`.
  - private helpers V229-7b reuses: `_mean(values) -> float | None`, `_deltas(pairs, arm) -> list[float]`.

Rules this module carries (spec § Statistic; index Handoff 4 and 9):

- ExpR per alert: every eligible plan counts, a skipped arm-B plan at 0R. Win rate is wins over trades **taken**.
- `week_cluster_bootstrap` clusters on `item.entry_date` of **objects**, so items are `SimpleNamespace(entry_date=<ET date>, r=<arm net R>)`; `baseline` is arm C, `component` is A (then B), the statistic is `mean(component.r) - mean(baseline.r)`. Both lists hold the same plans, so each draw's statistic equals the mean per-plan delta over the drawn weeks.
- The bootstrap does not refuse a one-week book: with fewer than 2 distinct ISO weeks `lower` and `p` are `None` and the bootstrap is never called. An empty draw array gives `None` too.
- One-sided 97.5% lower bound `np.percentile(draws, 2.5)`; one-sided `p = (draws <= 0).mean()`.
- Live path class (Handoff 9, live writer `swingbot/core/planning/plan_manager.py`, reasons `loss`, `scratch`, `win`, `tp1_partial`, `tp1_runner_*`): starts with `tp1` or equals `win` -> `win`; `scratch` -> `scratch`; `loss` or `stop` -> `loss`; anything else (`manual`, `reversed`, `stall_exit`, `time_exit`, empty) -> `None`. A simulated `timeout`, `no_bars` or skipped outcome -> `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_analysis.py`:

```python
"""v229 statistics: per-alert ExpR, week-clustered deltas, path-class calibration."""
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import analysis  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

FAST = dict(n_resamples=300, seed=42)
WEEKS = ("2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23")   # W45..W48, Mondays


def _leg(arm, r, *, taken=True, outcome="loss"):
    return {"arm": arm, "taken": taken, "fill": 100.0, "stop": 98.0, "tp1": 104.0,
            "outcome": outcome if taken else "skipped", "r_net": r if taken else 0.0,
            "r_gross": r + 0.05 if taken else 0.0, "exit_ts": None, "gap_stop": False}


def _pair(tid, entry_date, c, a, b, *, b_taken=True, c_outcome="loss", a_outcome="win",
          live_reason="loss", live_r=-1.0, above=True, event=False):
    return {"trade_id": tid, "entry_date": entry_date,
            "arms": {"C": _leg("C", c, outcome=c_outcome), "A": _leg("A", a, outcome=a_outcome),
                     "B": _leg("B", b, taken=b_taken, outcome=a_outcome)},
            "live": {"reason": live_reason, "outcome": live_reason, "r_realized": live_r},
            "tradeability": {"fill_above_entry": above, "event_day": event}}


@pytest.mark.parametrize("reason, expected", [
    ("tp1_partial", "win"), ("TP1_runner_be", "win"), ("tp1_runner_tp2", "win"), ("win", "win"),
    ("scratch", "scratch"), ("loss", "loss"), ("stop", "loss"), (" Loss ", "loss"),
    ("manual", None), ("reversed", None), ("stall_exit", None), ("time_exit", None), ("", None), (None, None),
])
def test_live_class_follows_the_live_writer(reason, expected):
    assert analysis.live_class(reason) == expected


@pytest.mark.parametrize("outcome, expected", [
    ("win", "win"), ("loss", "loss"), ("scratch", "scratch"),
    ("timeout", None), ("no_bars", None), ("skipped", None), (None, None),
])
def test_sim_class_maps_the_race_outcomes(outcome, expected):
    assert analysis.sim_class(outcome) == expected


def test_arm_summary_counts_a_skipped_plan_at_zero_r():
    pairs = [_pair("t-1", WEEKS[0], -1.0, 2.0, 2.0),
             _pair("t-2", WEEKS[0], -1.0, -1.0, 0.0, b_taken=False)]
    out = analysis.arm_summary(pairs, "B")
    assert out["n"] == 2 and out["taken"] == 1 and out["wins"] == 1
    assert out["win_rate"] == pytest.approx(1.0)             # over trades taken
    assert out["exp_r"] == pytest.approx(1.0)                # (2 + 0) / 2, per alert
    assert out["total_r"] == pytest.approx(2.0)
    assert out["exp_r_gross"] == pytest.approx(2.05 / 2)


def test_arm_summary_on_no_pairs_is_empty_not_zero():
    assert analysis.arm_summary([], "C") == {"n": 0, "taken": 0, "wins": 0, "win_rate": None,
                                             "exp_r": None, "total_r": 0.0, "exp_r_gross": None}


def test_delta_stats_defaults_are_the_pre_registered_ones():
    params = inspect.signature(analysis.delta_stats).parameters
    assert params["n_resamples"].default == 10_000
    assert params["seed"].default == stats.WEEK_BOOTSTRAP_SEED == 42


def test_a_uniform_lift_has_its_bound_at_the_lift_and_p_zero():
    pairs = [_pair(f"t-{i}", d, -1.0, 0.0, 0.0) for i, d in enumerate(WEEKS * 3)]
    out = analysis.delta_stats(pairs, "A", **FAST)
    assert out == {"arm": "A", "n": 12, "weeks": 4, "mean": pytest.approx(1.0),
                   "lower": pytest.approx(1.0), "p": 0.0}


def test_a_uniform_loss_has_p_one():
    pairs = [_pair(f"t-{i}", d, 1.0, 0.5, 0.5) for i, d in enumerate(WEEKS)]
    out = analysis.delta_stats(pairs, "B", **FAST)
    assert out["mean"] == pytest.approx(-0.5) and out["p"] == 1.0


def test_delta_stats_is_deterministic_under_the_seed_and_brackets_the_mean():
    pairs = [_pair(f"t-{i}", d, -1.0, r, r) for i, (d, r) in
             enumerate(zip(WEEKS * 2, (2.0, -1.0, 0.5, 3.0, -1.0, 1.0, 0.0, 2.0)))]
    first = analysis.delta_stats(pairs, "A", **FAST)
    assert first == analysis.delta_stats(pairs, "A", **FAST)
    assert first["lower"] < first["mean"] and 0.0 <= first["p"] <= 1.0


def test_a_skipped_b_plan_enters_the_delta_at_zero_r():
    pairs = [_pair("t-1", WEEKS[0], -1.0, -1.0, 0.0, b_taken=False),
             _pair("t-2", WEEKS[1], -1.0, -1.0, 0.0, b_taken=False)]
    assert analysis.delta_stats(pairs, "B", **FAST)["mean"] == pytest.approx(1.0)


def test_a_single_week_book_returns_no_interval(monkeypatch):
    monkeypatch.setattr(analysis, "week_cluster_bootstrap",
                        lambda *a, **k: pytest.fail("bootstrap called on one week"))
    pairs = [_pair("t-1", "2026-11-02", -1.0, 1.0, 1.0), _pair("t-2", "2026-11-06", -1.0, 0.0, 0.0)]
    out = analysis.delta_stats(pairs, "A", **FAST)
    assert out["weeks"] == 1 and out["mean"] == pytest.approx(1.5)
    assert out["lower"] is None and out["p"] is None


def test_no_pairs_returns_no_mean_and_no_interval():
    assert analysis.delta_stats([], "A", **FAST) == {"arm": "A", "n": 0, "weeks": 0,
                                                    "mean": None, "lower": None, "p": None}


def test_the_bootstrap_gets_objects_keyed_by_entry_date(monkeypatch):
    seen = {}

    def fake(baseline, component, statistic, *, n_resamples, seed):
        seen.update(b=baseline, c=component, n=n_resamples, seed=seed)
        return stats.week_cluster_bootstrap(baseline, component, statistic, n_resamples=n_resamples, seed=seed)

    monkeypatch.setattr(analysis, "week_cluster_bootstrap", fake)
    analysis.delta_stats([_pair("t-1", WEEKS[0], -1.0, 2.0, 0.0), _pair("t-2", WEEKS[1], 0.0, 1.0, 0.0)],
                         "A", **FAST)
    assert [item.entry_date for item in seen["b"]] == [WEEKS[0], WEEKS[1]]
    assert [item.r for item in seen["b"]] == [-1.0, 0.0] and [item.r for item in seen["c"]] == [2.0, 1.0]
    assert (seen["n"], seen["seed"]) == (300, 42)


def test_delta_over_taken_leaves_out_the_skipped_plans():
    pairs = [_pair("t-1", WEEKS[0], -1.0, 0.0, 0.0, b_taken=False), _pair("t-2", WEEKS[0], 1.0, 0.5, 0.5)]
    assert analysis.delta_over_taken(pairs, "B") == {"n": 1, "mean": pytest.approx(-0.5)}
    assert analysis.delta_over_taken([], "B") == {"n": 0, "mean": None}


def test_week_count_counts_distinct_iso_weeks():
    pairs = [_pair("t-1", "2026-11-02", 0, 0, 0), _pair("t-2", "2026-11-06", 0, 0, 0),
             _pair("t-3", "2026-11-09", 0, 0, 0)]
    assert analysis.week_count(pairs) == 2 and analysis.week_count([]) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_analysis.py`
Expected: FAIL at collection with `ImportError: cannot import name 'analysis'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/deferred_entry/analysis.py`:

```python
"""v229 statistics: per-alert ExpR, week-clustered paired deltas, calibration.

Spec sections "Statistic" and "Calibration clause". ExpR is per alert: a
skipped arm-B plan scores 0R. Deltas are bootstrapped by ISO week of the
ET entry date (trades are held up to five sessions, so neighbouring dates
share bars). Calibration compares path classes, never R: the simulator races
to TP1 only and cannot reproduce the live scale-out's R.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from swingbot.core.backtesting.instrument.stats import (
    WEEK_BOOTSTRAP_RESAMPLES,
    WEEK_BOOTSTRAP_SEED,
    iso_week_key,
    week_cluster_bootstrap,
)

LOWER_PCT = 2.5           # one-sided 97.5% bound: Bonferroni split of the gate's 95% over two arms
CALIBRATION_MIN = 0.80
CLASSES = ("loss", "scratch", "win")
_SIM_CLASS = {"win": "win", "loss": "loss", "scratch": "scratch"}
_LIVE_EXACT = {"win": "win", "scratch": "scratch", "loss": "loss", "stop": "loss"}


def live_class(reason) -> str | None:
    """Path class of a live close reason; None when it is not a stop/scratch/TP1 path."""
    text = (reason or "").strip().lower()
    if text.startswith("tp1"):
        return "win"
    return _LIVE_EXACT.get(text)


def sim_class(outcome) -> str | None:
    """Path class of a simulated outcome; timeout, no_bars and skipped have none."""
    return _SIM_CLASS.get(outcome or "")


def arm_r(pair: dict, arm: str, field: str = "r_net") -> float:
    """The arm's R for this plan; a leg not taken scores 0R."""
    leg = pair["arms"][arm]
    return float(leg[field]) if leg["taken"] else 0.0


def _mean(values) -> float | None:
    values = list(values)
    return float(np.mean(values)) if values else None


def _deltas(pairs, arm: str) -> list[float]:
    return [arm_r(p, arm) - arm_r(p, "C") for p in pairs]


def week_count(pairs) -> int:
    return len({iso_week_key(p["entry_date"]) for p in pairs})


def arm_summary(pairs, arm: str) -> dict:
    pairs = list(pairs)
    taken = [p["arms"][arm] for p in pairs if p["arms"][arm]["taken"]]
    wins = sum(1 for leg in taken if leg["outcome"] == "win")
    rs = [arm_r(p, arm) for p in pairs]
    return {"n": len(pairs), "taken": len(taken), "wins": wins,
            "win_rate": wins / len(taken) if taken else None,
            "exp_r": _mean(rs), "total_r": float(sum(rs)),
            "exp_r_gross": _mean(arm_r(p, arm, "r_gross") for p in pairs)}


def _items(pairs, arm: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(entry_date=p["entry_date"], r=arm_r(p, arm)) for p in pairs]


def _mean_difference(baseline, component) -> float | None:
    if not baseline:
        return None
    return float(np.mean([c.r for c in component]) - np.mean([b.r for b in baseline]))


def delta_stats(pairs, arm: str, *, n_resamples: int = WEEK_BOOTSTRAP_RESAMPLES,
                seed: int = WEEK_BOOTSTRAP_SEED) -> dict:
    """Mean per-plan delta of ``arm`` over C, with the week-clustered bound and p."""
    pairs = list(pairs)
    weeks = week_count(pairs)
    out = {"arm": arm, "n": len(pairs), "weeks": weeks,
           "mean": _mean(_deltas(pairs, arm)), "lower": None, "p": None}
    if weeks < 2:              # the bootstrap would return a zero-width interval
        return out
    draws = week_cluster_bootstrap(_items(pairs, "C"), _items(pairs, arm), _mean_difference,
                                   n_resamples=n_resamples, seed=seed)
    if draws.size:
        out["lower"] = float(np.percentile(draws, LOWER_PCT))
        out["p"] = float((draws <= 0).mean())
    return out


def delta_over_taken(pairs, arm: str) -> dict:
    taken = [p for p in pairs if p["arms"][arm]["taken"]]
    return {"n": len(taken), "mean": _mean(_deltas(taken, arm))}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_analysis.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry/analysis.py tests/scripts/test_deferred_entry_analysis.py
git commit -m "feat(v229): arm summaries and week-clustered deltas (V229-7)"
```

### Task V229-7b: Calibration, per-week, split and skip summaries

**Model:** opus — the calibration clause decides whether any verdict is issued; its table orientation and exclusions must match the spec.

Second half of the ledger's V229-7 (split past 20 KB). Needs V229-7 (it appends to `analysis.py` and its test file and reuses `arm_r`, `_mean`, `_deltas`, `CLASSES`, `CALIBRATION_MIN`, `live_class`, `sim_class`).

**Files:**
- Modify: `scripts/reports/deferred_entry/analysis.py` (imports block; append functions at the end)
- Modify: `tests/scripts/test_deferred_entry_analysis.py` (append tests; reuses its `_pair`, `WEEKS`)

**Interfaces:**
- Consumes: V229-7's `analysis` helpers above; PAIR fields `pair["arms"]["C"]["outcome"]`, `pair["live"]["reason"]`, `pair["live"]["r_realized"]` (float or None), `pair["tradeability"]["fill_above_entry"]` and `["event_day"]` (bool or None).
- Produces (index ledger; CALIBRATION shape exactly as in the index):
  - `calibration(pairs) -> dict` keys `table{sim{live:int}}, n, agreement, calibrated, excluded, mean_r_c, mean_live_r, spearman` (outer key simulated class, inner live class).
  - `weekly_deltas(pairs) -> list[dict]` keys `week, n, d_a, d_b`, sorted by week.
  - `split_deltas(pairs) -> dict` keys `fill_above, fill_below, with_events, without_events`, each `{n, d_a, d_b}`; a pair whose flag is `None` sits in neither side.
  - `skip_summary(pairs) -> dict` keys `skipped, control_r_of_skipped` (mean control net R of the plans B skipped; `None` when none).

Rules (spec § Calibration clause): agreement is the diagonal share of the 3x3 table; `calibrated` is `agreement >= 0.80`; no classifiable pair means `agreement None`, `calibrated False`. Pairs whose simulated or live class is `None` are counted in `excluded`, never in the table. `mean_r_c` (all pairs), `mean_live_r` and the Spearman rank correlation (pairs with a live `r_realized`) are information only. Spearman is computed locally on average ranks (`pd.Series.rank`) and `np.corrcoef`: never `Series.corr(method="spearman")`, which imports scipy (not a dependency), and never the private `expectancy_attribution._spearman`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_deferred_entry_analysis.py`:

```python
def _calibration_book(agree, disagree):
    pairs = [_pair(f"a-{i}", WEEKS[0], -1.0, 0.0, 0.0) for i in range(agree)]          # loss / loss
    pairs += [_pair(f"d-{i}", WEEKS[0], -1.0, 0.0, 0.0, live_reason="tp1_partial") for i in range(disagree)]
    return pairs


def test_calibration_at_exactly_80_percent_is_calibrated():
    out = analysis.calibration(_calibration_book(8, 2))
    assert out["table"]["loss"] == {"loss": 8, "scratch": 0, "win": 2}     # outer = simulated
    assert out["table"]["win"] == {"loss": 0, "scratch": 0, "win": 0}
    assert out["n"] == 10 and out["agreement"] == pytest.approx(0.8) and out["calibrated"] is True


def test_calibration_below_80_percent_is_not_calibrated():
    out = analysis.calibration(_calibration_book(7, 3))
    assert out["agreement"] == pytest.approx(0.7) and out["calibrated"] is False


def test_unclassifiable_pairs_are_excluded_and_counted():
    pairs = [_pair("t-1", WEEKS[0], 0.3, 0.0, 0.0, c_outcome="timeout"),
             _pair("t-2", WEEKS[0], -1.0, 0.0, 0.0, live_reason="manual"),
             _pair("t-3", WEEKS[0], 1.9, 0.0, 0.0, c_outcome="win", live_reason="tp1_runner_be"),
             _pair("t-4", WEEKS[0], -0.02, 0.0, 0.0, c_outcome="scratch", live_reason="scratch")]
    out = analysis.calibration(pairs)
    assert out["excluded"] == 2 and out["n"] == 2 and out["agreement"] == pytest.approx(1.0)
    assert out["table"]["win"]["win"] == 1 and out["table"]["scratch"]["scratch"] == 1


def test_calibration_on_no_pairs_is_uncalibrated_with_no_agreement():
    out = analysis.calibration([])
    assert out["n"] == 0 and out["agreement"] is None and out["calibrated"] is False
    assert out["excluded"] == 0
    assert out["mean_r_c"] is None and out["mean_live_r"] is None and out["spearman"] is None


def test_calibration_prints_means_and_rank_correlation_for_information():
    pairs = [_pair(f"t-{i}", WEEKS[0], r, 0.0, 0.0, live_r=r * 2) for i, r in enumerate((-1.0, 0.0, 1.0, 2.0))]
    pairs.append(_pair("t-x", WEEKS[0], 5.0, 0.0, 0.0, live_r=None))
    out = analysis.calibration(pairs)
    assert out["mean_r_c"] == pytest.approx(7.0 / 5)          # every pair
    assert out["mean_live_r"] == pytest.approx(1.0)           # (-2 + 0 + 2 + 4) / 4, live R present
    assert out["spearman"] == pytest.approx(1.0)


def test_spearman_needs_three_points_and_variation():
    two = [_pair(f"t-{i}", WEEKS[0], float(i), 0.0, 0.0, live_r=float(i)) for i in range(2)]
    flat = [_pair(f"t-{i}", WEEKS[0], float(i), 0.0, 0.0, live_r=1.0) for i in range(4)]
    assert analysis.calibration(two)["spearman"] is None
    assert analysis.calibration(flat)["spearman"] is None


def test_spearman_does_not_import_scipy(monkeypatch):
    monkeypatch.setitem(sys.modules, "scipy", None)            # any scipy import now raises
    pairs = [_pair(f"t-{i}", WEEKS[0], r, 0.0, 0.0, live_r=-r) for i, r in enumerate((0.0, 1.0, 2.0))]
    assert analysis.calibration(pairs)["spearman"] == pytest.approx(-1.0)


def test_weekly_deltas_are_sorted_by_week():
    pairs = [_pair("t-1", WEEKS[1], -1.0, 1.0, 0.0), _pair("t-2", WEEKS[0], 0.0, 1.0, -1.0),
             _pair("t-3", WEEKS[1], -1.0, -1.0, 0.0, b_taken=False)]
    assert analysis.weekly_deltas(pairs) == [
        {"week": "2026-W45", "n": 1, "d_a": pytest.approx(1.0), "d_b": pytest.approx(-1.0)},
        {"week": "2026-W46", "n": 2, "d_a": pytest.approx(1.0), "d_b": pytest.approx(1.0)},
    ]
    assert analysis.weekly_deltas([]) == []


def test_split_deltas_by_fill_side_and_event_day():
    pairs = [_pair("t-1", WEEKS[0], -1.0, 1.0, 1.0, above=True),
             _pair("t-2", WEEKS[0], 0.0, -1.0, -1.0, above=False, event=True),
             _pair("t-3", WEEKS[0], 0.0, 0.0, 0.0, above=None)]
    out = analysis.split_deltas(pairs)
    assert out["fill_above"] == {"n": 1, "d_a": pytest.approx(2.0), "d_b": pytest.approx(2.0)}
    assert out["fill_below"]["n"] == 1 and out["fill_below"]["d_a"] == pytest.approx(-1.0)
    assert out["with_events"]["n"] == 1 and out["without_events"]["n"] == 2
    assert analysis.split_deltas([])["fill_above"] == {"n": 0, "d_a": None, "d_b": None}


def test_skip_summary_reports_the_control_result_of_skipped_plans():
    pairs = [_pair("t-1", WEEKS[0], -1.0, 0.0, 0.0, b_taken=False),
             _pair("t-2", WEEKS[0], 0.0, 0.0, 0.0, b_taken=False),
             _pair("t-3", WEEKS[0], 2.0, 0.0, 1.0)]
    assert analysis.skip_summary(pairs) == {"skipped": 2, "control_r_of_skipped": pytest.approx(-0.5)}
    assert analysis.skip_summary([]) == {"skipped": 0, "control_r_of_skipped": None}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_analysis.py`
Expected: FAIL with `AttributeError: module 'deferred_entry.analysis' has no attribute 'calibration'` (V229-7's tests still pass).

- [ ] **Step 3: Write the implementation**

In `scripts/reports/deferred_entry/analysis.py`, extend the imports block to:

```python
from collections import defaultdict
from types import SimpleNamespace

import numpy as np
import pandas as pd
```

add this constant below `_LIVE_EXACT`:

```python
_SPLITS = (("fill_above", "fill_above_entry", True), ("fill_below", "fill_above_entry", False),
           ("with_events", "event_day", True), ("without_events", "event_day", False))
```

and append at the end of the module:

```python
def _live_r(pair: dict) -> float | None:
    value = pair["live"].get("r_realized")
    return None if value is None else float(value)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Pearson on average ranks; None under 3 points or with a constant side."""
    if len(xs) < 3:
        return None
    rx = pd.Series(xs, dtype=float).rank().to_numpy()
    ry = pd.Series(ys, dtype=float).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _information(pairs: list[dict]) -> dict:
    both = [(arm_r(p, "C"), _live_r(p)) for p in pairs if _live_r(p) is not None]
    return {"mean_r_c": _mean(arm_r(p, "C") for p in pairs),
            "mean_live_r": _mean(live for _, live in both),
            "spearman": _spearman([sim for sim, _ in both], [live for _, live in both])}


def calibration(pairs) -> dict:
    """3x3 path-class table of simulated control (outer) against live (inner)."""
    pairs = list(pairs)
    table = {sim: {live: 0 for live in CLASSES} for sim in CLASSES}
    excluded = 0
    for pair in pairs:
        sim, live = sim_class(pair["arms"]["C"]["outcome"]), live_class(pair["live"].get("reason"))
        if sim is None or live is None:
            excluded += 1
            continue
        table[sim][live] += 1
    n = sum(sum(row.values()) for row in table.values())
    agreement = sum(table[c][c] for c in CLASSES) / n if n else None
    return {"table": table, "n": n, "agreement": agreement,
            "calibrated": agreement is not None and agreement >= CALIBRATION_MIN,
            "excluded": excluded, **_information(pairs)}


def _cell(group: list[dict]) -> dict:
    return {"n": len(group), "d_a": _mean(_deltas(group, "A")), "d_b": _mean(_deltas(group, "B"))}


def weekly_deltas(pairs) -> list[dict]:
    by_week: dict[str, list[dict]] = defaultdict(list)
    for pair in pairs:
        by_week[iso_week_key(pair["entry_date"])].append(pair)
    return [{"week": week, **_cell(group)} for week, group in sorted(by_week.items())]


def split_deltas(pairs) -> dict:
    """d_A and d_B by fill side of the plan's entry and by event day (None in neither)."""
    pairs = list(pairs)
    return {name: _cell([p for p in pairs if p["tradeability"].get(key) is value])
            for name, key, value in _SPLITS}


def skip_summary(pairs) -> dict:
    skipped = [p for p in pairs if not p["arms"]["B"]["taken"]]
    return {"skipped": len(skipped), "control_r_of_skipped": _mean(arm_r(p, "C") for p in skipped)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_analysis.py`
Expected: PASS, `0 failed` (V229-7's tests included).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`calibration` is the largest function, well under 15).

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry/analysis.py tests/scripts/test_deferred_entry_analysis.py
git commit -m "feat(v229): path-class calibration, per-week, split and skip summaries (V229-7b)"
```

### Task V229-8: Frozen rule, window and verdict guard

**Model:** opus — encodes the pre-registration: the frozen constants, the forward window, the refusal rules and the study-to-ledger mapping are the whole study's integrity.

**Files:**
- Create: `scripts/reports/deferred_entry/verdict.py`
- Test: `tests/scripts/test_deferred_entry_verdict.py`

**Interfaces:**
- Consumes: DELTA and CALIBRATION shapes (index § Shared shapes) as plain dicts — no code from V229-7. `swingbot/core/market/session.py`: `US_MARKET_TZ` (:12), `nyse_calendar()` (:275; `session_after(d, n)` with `n=0` = the session on or before `d`). `swingbot.core.backtesting.instrument.stats.validate_ledger_row` (tests only).
- Produces (index ledger; FROZEN exactly as in the index):
  - `FROZEN: dict`; `LEDGER_ID = "v229-deferred-entry"`; `STUDY_TO_LEDGER = {"PASS": "PASS", "NO-LIFT": "NO-LIFT", "UNDERPOWERED": "NO-LIFT", "UNCALIBRATED": "INCONCLUSIVE"}` (Handoff 2).
  - `rule_hash() -> str`: first 16 hex chars of `sha256(json.dumps(FROZEN, sort_keys=True))` (Handoff 3).
  - `class VerdictRefused(RuntimeError)`.
  - `forward_window(t0) -> (start, end)`: `start` = the Monday after T0's ET date (T0's own week is never complete), `end` = `start + 83 days` (a Sunday): twelve complete ISO weeks. A naive `t0` raises `ValueError`.
  - `phase(entry_date, t0) -> str`: `"exploratory"` when `entry_date` is before T0's ET date; `"forward"` inside the window; `"after"` otherwise (T0's own date, the rest of T0's week, past the window — in neither read).
  - `verdict_open_date(t0) -> dt.date`: the day after the fifth NYSE session following the last session on or before `end`.
  - `assert_one_rule(pairs) -> None` (additive): `VerdictRefused` when any pair's `rule_hash` differs from `rule_hash()`; used by `guard` and by V229-10's exploratory mode.
  - `guard(*, today, t0, ledger_rows, pairs) -> None`: `VerdictRefused` when the ledger already holds `LEDGER_ID`, when `today < verdict_open_date(t0)`, or via `assert_one_rule`.
  - `arm_verdict(delta, calibrated) -> str`: `UNCALIBRATED` | `PASS` (mean >= `floor_r` and lower > 0) | `NO-LIFT`.
  - `study_verdict(*, deltas, calibration, n_pairs, weeks) -> dict` keys `study, arms{A,B}, ledger{verdict, n, exp_r, p}`.
  - `exploratory_close(calibration, n_pairs) -> dict | None`: `None` when calibrated, else `{"study": "UNCALIBRATED", "arms": {"A": "UNCALIBRATED", "B": "UNCALIBRATED"}, "ledger": {"verdict": "INCONCLUSIVE", "n": n_pairs, "exp_r": None, "p": None}}`.

Study precedence: `UNDERPOWERED` (fewer than 300 pairs or 10 weeks: a count, closed like a fail) is decided first, then `UNCALIBRATED`, then `PASS` when either arm passes, else `NO-LIFT`. Ledger `p = min(1.0, 2 * min(p_A, p_B))` over the arms with a p (`None` when neither has one); `exp_r` is the mean delta of the arm with the smaller p; both rounded to 4 places; `UNCALIBRATED` carries `exp_r = p = None`. The CLI never writes the ledger: V229-13/V229-15 append the row with `scripts/reports/preregistration_ledger.py`, which refuses a duplicate id as the second line of defence.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_verdict.py`:

```python
"""v229 frozen rule, forward window and verdict guard."""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import verdict  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

T0 = pd.Timestamp("2026-11-19T15:00:00+00:00")             # a Thursday
CAL = {"calibrated": True}
UNCAL = {"calibrated": False}


def _delta(arm, mean, lower, p):
    return {"arm": arm, "n": 400, "weeks": 12, "mean": mean, "lower": lower, "p": p}


def test_frozen_is_the_pre_registered_rule():
    assert verdict.FROZEN == {"defer_et": "15:30", "hold_sessions": 5, "window_weeks": 12,
                              "floor_r": 0.10, "lower_pct": 2.5, "calibration_min": 0.80,
                              "min_pairs": 300, "min_weeks": 10, "resamples": 10000, "seed": 42,
                              "be_fraction": 0.5, "deferred_entry_bps_mult": 2}
    assert verdict.LEDGER_ID == "v229-deferred-entry"


def test_rule_hash_is_sha256_of_the_sorted_rule(monkeypatch):
    expected = hashlib.sha256(json.dumps(verdict.FROZEN, sort_keys=True).encode()).hexdigest()[:16]
    assert verdict.rule_hash() == expected and len(expected) == 16
    monkeypatch.setitem(verdict.FROZEN, "floor_r", 0.2)
    assert verdict.rule_hash() != expected


@pytest.mark.parametrize("t0, start", [
    ("2026-11-19T15:00:00+00:00", dt.date(2026, 11, 23)),   # Thursday -> next Monday
    ("2026-11-23T14:00:00+00:00", dt.date(2026, 11, 30)),   # Monday 09:00 ET: its week is not complete
    ("2026-11-23T03:00:00+00:00", dt.date(2026, 11, 23)),   # Sunday 22:00 ET: ET date decides
])
def test_forward_window_is_twelve_complete_iso_weeks(t0, start):
    first, last = verdict.forward_window(pd.Timestamp(t0))
    assert first == start and first.weekday() == 0
    assert last == start + dt.timedelta(days=83) and last.weekday() == 6


def test_a_naive_t0_is_refused():
    with pytest.raises(ValueError, match="UTC"):
        verdict.forward_window(pd.Timestamp("2026-11-19T15:00:00"))


@pytest.mark.parametrize("day, expected", [
    (dt.date(2026, 11, 18), "exploratory"), (dt.date(2026, 11, 19), "after"),
    (dt.date(2026, 11, 20), "after"), (dt.date(2026, 11, 23), "forward"),
    (dt.date(2027, 2, 14), "forward"), (dt.date(2027, 2, 15), "after"),
])
def test_phase_by_entry_date(day, expected):
    assert verdict.phase(day, T0) == expected


def test_verdict_opens_the_day_after_the_fifth_session_past_the_window():
    # window ends Sun 2027-02-14; last session Fri 02-12; 02-15 is Presidents' Day;
    # sessions 02-16, 17, 18, 19, 22 -> the fifth is 02-22
    assert verdict.verdict_open_date(T0) == dt.date(2027, 2, 23)


def _pair(h=None):
    return {"trade_id": "t-1", "rule_hash": h or verdict.rule_hash()}


def test_guard_refuses_before_the_open_date_and_passes_on_it():
    with pytest.raises(verdict.VerdictRefused, match="2027-02-23"):
        verdict.guard(today=dt.date(2027, 2, 22), t0=T0, ledger_rows=[], pairs=[_pair()])
    verdict.guard(today=dt.date(2027, 2, 23), t0=T0, ledger_rows=[], pairs=[_pair()])


def test_guard_refuses_a_second_verdict():
    rows = [{"id": "v226-stop-width"}, {"id": verdict.LEDGER_ID}]
    with pytest.raises(verdict.VerdictRefused, match="already"):
        verdict.guard(today=dt.date(2027, 3, 1), t0=T0, ledger_rows=rows, pairs=[])


def test_guard_refuses_a_log_written_under_another_rule():
    with pytest.raises(verdict.VerdictRefused, match="rule"):
        verdict.guard(today=dt.date(2027, 3, 1), t0=T0, ledger_rows=[],
                      pairs=[_pair(), _pair("ffffffffffffffff")])
    verdict.assert_one_rule([])                              # an empty log carries no other rule


@pytest.mark.parametrize("mean, lower, calibrated, expected", [
    (0.10, 0.01, True, "PASS"), (0.0999, 0.01, True, "NO-LIFT"), (0.30, 0.0, True, "NO-LIFT"),
    (0.30, None, True, "NO-LIFT"), (None, None, True, "NO-LIFT"), (0.50, 0.20, False, "UNCALIBRATED"),
])
def test_arm_verdict(mean, lower, calibrated, expected):
    assert verdict.arm_verdict(_delta("A", mean, lower, 0.01), calibrated) == expected


def test_one_passing_arm_passes_the_study_with_a_doubled_p():
    out = verdict.study_verdict(deltas={"A": _delta("A", 0.31234, 0.05, 0.004),
                                        "B": _delta("B", 0.08, -0.02, 0.2)},
                                calibration=CAL, n_pairs=812, weeks=12)
    assert out == {"study": "PASS", "arms": {"A": "PASS", "B": "NO-LIFT"},
                   "ledger": {"verdict": "PASS", "n": 812, "exp_r": 0.3123, "p": 0.008}}


def test_the_doubled_p_is_capped_at_one():
    out = verdict.study_verdict(deltas={"A": _delta("A", -0.1, -0.3, 0.7), "B": _delta("B", -0.2, -0.4, 0.9)},
                                calibration=CAL, n_pairs=400, weeks=12)
    assert out["study"] == "NO-LIFT" and out["ledger"]["p"] == 1.0 and out["ledger"]["exp_r"] == -0.1


@pytest.mark.parametrize("n_pairs, weeks", [(299, 12), (400, 9)])
def test_underpowered_closes_like_a_fail_and_precedes_calibration(n_pairs, weeks):
    deltas = {"A": _delta("A", 0.5, 0.2, 0.001), "B": _delta("B", 0.4, 0.1, 0.01)}
    out = verdict.study_verdict(deltas=deltas, calibration=UNCAL, n_pairs=n_pairs, weeks=weeks)
    assert out["study"] == "UNDERPOWERED" and out["arms"] == {"A": "UNDERPOWERED", "B": "UNDERPOWERED"}
    assert out["ledger"]["verdict"] == "NO-LIFT" and out["ledger"]["p"] == 0.002


def test_uncalibrated_is_inconclusive_with_no_estimate():
    deltas = {"A": _delta("A", 0.5, 0.2, 0.001), "B": _delta("B", 0.4, 0.1, 0.01)}
    out = verdict.study_verdict(deltas=deltas, calibration=UNCAL, n_pairs=400, weeks=12)
    assert out == {"study": "UNCALIBRATED", "arms": {"A": "UNCALIBRATED", "B": "UNCALIBRATED"},
                   "ledger": {"verdict": "INCONCLUSIVE", "n": 400, "exp_r": None, "p": None}}


def test_no_p_on_either_arm_leaves_the_ledger_p_null():
    deltas = {"A": _delta("A", None, None, None), "B": _delta("B", None, None, None)}
    out = verdict.study_verdict(deltas=deltas, calibration=CAL, n_pairs=0, weeks=0)
    assert out["ledger"] == {"verdict": "NO-LIFT", "n": 0, "exp_r": None, "p": None}


def test_exploratory_close_only_when_uncalibrated():
    assert verdict.exploratory_close(CAL, 350) is None
    assert verdict.exploratory_close(UNCAL, 350) == {
        "study": "UNCALIBRATED", "arms": {"A": "UNCALIBRATED", "B": "UNCALIBRATED"},
        "ledger": {"verdict": "INCONCLUSIVE", "n": 350, "exp_r": None, "p": None}}


@pytest.mark.parametrize("ledger", [
    {"verdict": "PASS", "n": 812, "exp_r": 0.3123, "p": 0.008},
    {"verdict": "NO-LIFT", "n": 0, "exp_r": None, "p": None},
    {"verdict": "INCONCLUSIVE", "n": 350, "exp_r": None, "p": None},
])
def test_every_ledger_mapping_is_a_valid_ledger_row(ledger):
    stats.validate_ledger_row({"id": verdict.LEDGER_ID, "date": "2027-02-23", "hypothesis": "h",
                               "instrument": "v1", "record": "docs/x.md", **ledger})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_verdict.py`
Expected: FAIL at collection with `ImportError: cannot import name 'verdict'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/deferred_entry/verdict.py`:

```python
"""v229 frozen rule, forward window and verdict guard (spec section 3).

The forward rule is frozen before either read: every pair row carries
``rule_hash()``, and a verdict over a log written under another rule is
refused. The verdict is computed once, after the twelve complete ISO weeks
following T0 have passed their five-session mark, and never again once the
ledger holds ``LEDGER_ID``. The study words have no ledger tokens of their
own: UNCALIBRATED -> INCONCLUSIVE, UNDERPOWERED -> NO-LIFT (index Handoff 2).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import pandas as pd

from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar

FROZEN = {"defer_et": "15:30", "hold_sessions": 5, "window_weeks": 12, "floor_r": 0.10,
          "lower_pct": 2.5, "calibration_min": 0.80, "min_pairs": 300, "min_weeks": 10,
          "resamples": 10000, "seed": 42, "be_fraction": 0.5, "deferred_entry_bps_mult": 2}
LEDGER_ID = "v229-deferred-entry"
STUDY_TO_LEDGER = {"PASS": "PASS", "NO-LIFT": "NO-LIFT", "UNDERPOWERED": "NO-LIFT",
                   "UNCALIBRATED": "INCONCLUSIVE"}
ARMS = ("A", "B")


class VerdictRefused(RuntimeError):
    """The verdict cannot be computed now, or has been computed already."""


def rule_hash() -> str:
    return hashlib.sha256(json.dumps(FROZEN, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _t0_date(t0) -> dt.date:
    ts = pd.Timestamp(t0)
    if ts.tzinfo is None:
        raise ValueError("T0 must be a timezone-aware UTC timestamp")
    return ts.tz_convert(US_MARKET_TZ).date()


def forward_window(t0) -> tuple[dt.date, dt.date]:
    """Monday after T0's ET date through the Sunday twelve weeks later."""
    day = _t0_date(t0)
    start = day + dt.timedelta(days=7 - day.weekday())
    return start, start + dt.timedelta(days=7 * FROZEN["window_weeks"] - 1)


def phase(entry_date: dt.date, t0) -> str:
    start, end = forward_window(t0)
    if entry_date < _t0_date(t0):
        return "exploratory"
    return "forward" if start <= entry_date <= end else "after"


def verdict_open_date(t0) -> dt.date:
    calendar = nyse_calendar()
    last = calendar.session_after(forward_window(t0)[1], 0)
    fifth = calendar.session_after(last, FROZEN["hold_sessions"]) if last else None
    if fifth is None:
        raise ValueError("the forward window runs past the NYSE calendar")
    return fifth + dt.timedelta(days=1)


def assert_one_rule(pairs) -> None:
    other = sorted({str(p.get("rule_hash")) for p in pairs} - {rule_hash()})
    if other:
        raise VerdictRefused(f"pair log carries rows written under another rule ({other}); "
                             f"the frozen rule is {rule_hash()}")


def guard(*, today: dt.date, t0, ledger_rows, pairs) -> None:
    if any(row.get("id") == LEDGER_ID for row in ledger_rows):
        raise VerdictRefused(f"the ledger already holds {LEDGER_ID}: the verdict is computed once")
    opens = verdict_open_date(t0)
    if today < opens:
        raise VerdictRefused(f"the verdict opens on {opens.isoformat()} (today {today.isoformat()})")
    assert_one_rule(pairs)


def arm_verdict(delta: dict, calibrated: bool) -> str:
    if not calibrated:
        return "UNCALIBRATED"
    mean, lower = delta.get("mean"), delta.get("lower")
    if mean is not None and lower is not None and mean >= FROZEN["floor_r"] and lower > 0:
        return "PASS"
    return "NO-LIFT"


def _study_word(arms: dict, calibrated: bool, n_pairs: int, weeks: int) -> str:
    if n_pairs < FROZEN["min_pairs"] or weeks < FROZEN["min_weeks"]:
        return "UNDERPOWERED"
    if not calibrated:
        return "UNCALIBRATED"
    return "PASS" if "PASS" in arms.values() else "NO-LIFT"


def _estimate(deltas: dict) -> tuple[float | None, float | None]:
    """(exp_r of the arm with the smaller p, min(1, 2 x that p))."""
    with_p = sorted((d["p"], arm) for arm, d in deltas.items() if d.get("p") is not None)
    if not with_p:
        return None, None
    p, arm = with_p[0]
    mean = deltas[arm].get("mean")
    return (None if mean is None else round(mean, 4)), round(min(1.0, 2 * p), 4)


def study_verdict(*, deltas: dict, calibration: dict, n_pairs: int, weeks: int) -> dict:
    arms = {arm: arm_verdict(deltas[arm], calibration["calibrated"]) for arm in ARMS}
    study = _study_word(arms, calibration["calibrated"], n_pairs, weeks)
    if study == "UNDERPOWERED":
        arms = {arm: "UNDERPOWERED" for arm in ARMS}
    exp_r, p = (None, None) if study == "UNCALIBRATED" else _estimate(deltas)
    return {"study": study, "arms": arms,
            "ledger": {"verdict": STUDY_TO_LEDGER[study], "n": n_pairs, "exp_r": exp_r, "p": p}}


def exploratory_close(calibration: dict, n_pairs: int) -> dict | None:
    """The study's close when the exploratory read is UNCALIBRATED; else None."""
    if calibration["calibrated"]:
        return None
    return {"study": "UNCALIBRATED", "arms": {arm: "UNCALIBRATED" for arm in ARMS},
            "ledger": {"verdict": "INCONCLUSIVE", "n": n_pairs, "exp_r": None, "p": None}}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_verdict.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry/verdict.py tests/scripts/test_deferred_entry_verdict.py
git commit -m "feat(v229): frozen rule, forward window and verdict guard (V229-8)"
```

### Task V229-9: Results Markdown and JSON

**Model:** sonnet — rendering of dicts whose shapes are fixed by V229-7, V229-7b and V229-8; no statistics decided here.

**Files:**
- Create: `scripts/reports/deferred_entry/report.py`
- Test: `tests/scripts/test_deferred_entry_report.py`

**Interfaces:**
- Consumes: V229-7/7b `analysis.arm_summary`, `delta_stats`, `delta_over_taken`, `calibration`, `weekly_deltas`, `split_deltas`, `skip_summary`, `arm_r`; V229-8 `verdict.FROZEN`, `verdict.rule_hash()`; the PAIR shape, with `pair["tradeability"]` keys per the ledger's V229-4 row (`fill_vs_entry_r`, `shifted_stop_above_day_low`, `day_low_vs_stop_r`, `price_1530_vs_entry_r`, `first_gap_r{C,A,B}`, `bar_1530{volume, range_r, open_vs_last_close_r}`, `plan_expired`, `entry_bar_stopout`, `earnings_after_close`, `monthly_opex`, `fomc`, `event_day`) and `pair["arms"][arm]["gap_stop"]`.
- Produces (index ledger, plus two additive public helpers):
  - `build_payload(*, phase, t0, pairs, bearish, funnel, close_bucket, archive_last_bar, git_sha, verdict=None) -> dict` — JSON-serialisable. `pairs` are the phase's LONG pairs; `bearish` the phase's bearish pairs (disclosure); `funnel` a `{reason: count}` mapping; `close_bucket` `{"n": int, "exp_r": float | None}` (the live result of LONG trades opened at or after 15:30 ET, for context). Keys: `study, phase, t0, rule_hash, frozen, archive_last_bar, git_sha, disclosures, funnel, buckets, arms{C,A,B}, deltas{A,B}, b_over_taken, calibration, weekly, splits, skips, tradeability, close_bucket, bearish, verdict`. V229-10 sets `payload["verdict"]` from `payload["deltas"]` and `payload["calibration"]`, so the 10,000-resample bootstrap runs once.
  - `label(payload) -> str` (additive): `EXPLORATORY (no verdict)` (plus ` -- UNCALIBRATED: the forward read is not started` when uncalibrated); `VERDICT: <study>` when a verdict is set; `UNCALIBRATED (no verdict)`; else `FORWARD (no verdict yet)`.
  - `tradeability_summary(pairs) -> dict` (additive).
  - `render_markdown(payload) -> str`.

Every output carries the disclosures (spec: the missing runner "is disclosed in every output"; the entry-bar bias direction; Handoff 9's single-leg export; the open-trade gap from the index's OPEN list; net frictions; arm B's wick-touch skip).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_report.py`:

```python
"""v229 results doc and JSON payload."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

from deferred_entry import report, verdict  # noqa: E402


def _leg(arm, r, *, taken=True, outcome="loss", gap=False):
    return {"arm": arm, "taken": taken, "fill": 100.0, "stop": 98.0, "tp1": 104.0, "outcome": outcome,
            "r_net": r, "r_gross": r + 0.05, "exit_ts": None, "gap_stop": gap}


def _pair(tid, day, *, c=-1.0, a=1.0, b_taken=True, bucket="open", expired=False, event=False):
    return {"trade_id": tid, "entry_date": day, "bucket": bucket, "direction": "bullish",
            "arms": {"C": _leg("C", c), "A": _leg("A", a, outcome="win", gap=True),
                     "B": _leg("B", a if b_taken else 0.0, taken=b_taken, outcome="win")},
            "live": {"reason": "loss", "outcome": "loss", "r_realized": -1.0},
            "tradeability": {"fill_vs_entry_r": 0.5, "fill_above_entry": True, "shifted_stop_above_day_low": True,
                             "day_low": 98.5, "day_low_vs_stop_r": 0.25, "price_1530_vs_entry_r": 0.5,
                             "first_gap_r": {"C": -0.2, "A": 0.1, "B": None},
                             "bar_1530": {"volume": 1000.0, "range_r": 0.3, "open_vs_last_close_r": 0.0},
                             "plan_expired": expired, "sessions_since_plan": 1, "entry_bar_stopout": False,
                             "earnings_after_close": None, "monthly_opex": False, "fomc": event, "event_day": event}}


def _payload(pairs, phase="exploratory", **kw):
    args = dict(phase=phase, t0="2026-11-19T15:00:00+00:00", pairs=pairs,
                bearish=[_pair("s-1", "2026-11-03")], funnel={"eligible": len(pairs), "no_coverage": 0},
                close_bucket={"n": 35, "exp_r": 0.672}, archive_last_bar="2026-11-18T20:55:00+00:00",
                git_sha="abc1234")
    args.update(kw)
    return report.build_payload(**args)


PAIRS = [_pair("t-1", "2026-11-02"), _pair("t-2", "2026-11-09", b_taken=False, bucket="midday", expired=True),
         _pair("t-3", "2026-11-10", c=0.5, a=-1.0, event=True)]


def test_payload_is_json_serialisable_and_records_its_provenance():
    payload = _payload(PAIRS)
    json.dumps(payload, allow_nan=False)
    assert payload["rule_hash"] == verdict.rule_hash() and payload["frozen"] == verdict.FROZEN
    assert payload["archive_last_bar"] == "2026-11-18T20:55:00+00:00" and payload["git_sha"] == "abc1234"
    assert payload["buckets"] == {"open": 2, "midday": 1} and payload["verdict"] is None
    assert payload["arms"]["B"]["taken"] == 2 and payload["skips"]["skipped"] == 1
    assert payload["deltas"]["A"]["weeks"] == 2 and payload["b_over_taken"]["n"] == 2
    assert payload["close_bucket"] == {"n": 35, "exp_r": 0.672}
    assert any("no runner" in line for line in payload["disclosures"])


def test_a_missing_git_sha_is_recorded_as_unknown():
    assert _payload(PAIRS, git_sha=None)["git_sha"] == "unknown"


def test_tradeability_summary_counts_and_means():
    out = report.tradeability_summary(PAIRS)
    assert out["count_plan_expired"] == 1 and out["count_event_day"] == 1
    assert out["count_shifted_stop_above_day_low"] == 3 and out["count_earnings_after_close"] == 0
    assert out["mean_fill_vs_entry_r"] == pytest.approx(0.5)
    assert out["first_gap_r"] == {"C": pytest.approx(-0.2), "A": pytest.approx(0.1), "B": None}
    assert out["gap_through_stop"] == {"C": 0, "A": 3, "B": 0}
    assert out["bar_1530_median"]["volume"] == pytest.approx(1000.0)


def test_bearish_pairs_are_a_disclosure_with_their_own_summary():
    bearish = _payload(PAIRS)["bearish"]
    assert bearish["n"] == 1 and bearish["d_a"] == pytest.approx(2.0)
    assert bearish["arms"]["C"]["n"] == 1


@pytest.mark.parametrize("phase, calibrated, study, expected", [
    ("exploratory", True, None, "EXPLORATORY (no verdict)"),
    ("exploratory", False, None, "EXPLORATORY (no verdict) -- UNCALIBRATED: the forward read is not started"),
    ("forward", True, "PASS", "VERDICT: PASS"),
    ("forward", False, "UNDERPOWERED", "VERDICT: UNDERPOWERED"),
    ("forward", False, None, "UNCALIBRATED (no verdict)"),
    ("forward", True, None, "FORWARD (no verdict yet)"),
])
def test_label(phase, calibrated, study, expected):
    payload = {"phase": phase, "calibration": {"calibrated": calibrated},
               "verdict": {"study": study} if study else None}
    assert report.label(payload) == expected


def test_markdown_carries_every_section_and_the_disclosures():
    text = report.render_markdown(_payload(PAIRS))
    for needle in ("# v229 deferred-entry counterfactual: exploratory read", "EXPLORATORY (no verdict)",
                   "abc1234", verdict.rule_hash(), "no runner", "## Population funnel", "## Arms",
                   "| C |", "## Deltas", "d_B over the plans B took", "## Calibration",
                   "| sim \\ live | loss | scratch | win |", "## Per week", "2026-W45", "## Splits",
                   "## Arm B skips", "## Tradeability", "## Context", "+0.672", "## Bearish disclosure"):
        assert needle in text, needle


def test_markdown_renders_a_verdict_and_missing_values():
    payload = _payload(PAIRS[:1], phase="forward")
    payload["verdict"] = {"study": "UNDERPOWERED", "arms": {"A": "UNDERPOWERED", "B": "UNDERPOWERED"},
                          "ledger": {"verdict": "NO-LIFT", "n": 1, "exp_r": None, "p": None}}
    text = report.render_markdown(payload)
    assert "VERDICT: UNDERPOWERED" in text and "## Verdict" in text and "NO-LIFT" in text
    assert "n/a" in text                                   # one week: no bound, no p


def test_an_empty_read_still_renders():
    text = report.render_markdown(_payload([], bearish=[]))
    assert "## Arms" in text and "n/a" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_report.py`
Expected: FAIL at collection with `ImportError: cannot import name 'report'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/deferred_entry/report.py`:

```python
"""v229 results: one Markdown doc and one JSON payload (spec section "Outputs").

Everything is disclosure except the verdict block, which V229-10 fills from
``verdict.study_verdict``. Each output records the archive's last bar, the
script's git SHA and the frozen rule's hash, so a run can be reproduced.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from . import analysis
from .verdict import FROZEN, rule_hash

ARMS = ("C", "A", "B")
DISCLOSURES = (
    "Single leg to TP1: no runner, no TP2; the live scale-out is not reproduced.",
    "The control starts at the first bar at or after opened_at, so a stop-out inside the entry bar is "
    "missed: this flatters the control and biases d_A downward on exactly the noise stops tested.",
    "The live path class comes from the export's last leg only: a TP1 partial whose runner leg is "
    "labelled scratch classes as scratch.",
    "Trades still open at the read date are not in the export and are absent from the population.",
    "All R is net of frictions; arms A and B pay twice the entry slippage (a market order in the last "
    "half hour). Gross R is printed beside and gates nothing.",
    "Arm B's skip is a mechanical wick touch, not a trader's judgement that the level held.",
)
_MEANS = ("fill_vs_entry_r", "day_low_vs_stop_r", "price_1530_vs_entry_r")
_COUNTS = ("shifted_stop_above_day_low", "plan_expired", "entry_bar_stopout",
           "earnings_after_close", "monthly_opex", "fomc", "event_day")
_BAR_KEYS = ("volume", "range_r", "open_vs_last_close_r")


def _present(values) -> list[float]:
    return [float(v) for v in values if v is not None]


def _mean(values) -> float | None:
    vals = _present(values)
    return float(np.mean(vals)) if vals else None


def _median(values) -> float | None:
    vals = _present(values)
    return float(np.median(vals)) if vals else None


def tradeability_summary(pairs) -> dict:
    recs = [p["tradeability"] for p in pairs]
    out = {f"mean_{key}": _mean(r.get(key) for r in recs) for key in _MEANS}
    out.update({f"count_{key}": sum(1 for r in recs if r.get(key) is True) for key in _COUNTS})
    out["first_gap_r"] = {arm: _mean((r.get("first_gap_r") or {}).get(arm) for r in recs) for arm in ARMS}
    out["gap_through_stop"] = {arm: sum(1 for p in pairs if p["arms"][arm]["gap_stop"]) for arm in ARMS}
    out["bar_1530_median"] = {key: _median((r.get("bar_1530") or {}).get(key) for r in recs)
                              for key in _BAR_KEYS}
    return out


def _bearish_summary(pairs: list[dict]) -> dict:
    def delta(arm):
        return _mean(analysis.arm_r(p, arm) - analysis.arm_r(p, "C") for p in pairs)
    return {"n": len(pairs), "arms": {arm: analysis.arm_summary(pairs, arm) for arm in ARMS},
            "d_a": delta("A"), "d_b": delta("B")}


def build_payload(*, phase, t0, pairs, bearish, funnel, close_bucket, archive_last_bar,
                  git_sha, verdict=None) -> dict:
    pairs, bearish = list(pairs), list(bearish)
    return {"study": "v229-deferred-entry", "phase": phase, "t0": str(t0), "rule_hash": rule_hash(),
            "frozen": dict(FROZEN), "archive_last_bar": archive_last_bar, "git_sha": git_sha or "unknown",
            "disclosures": list(DISCLOSURES), "funnel": dict(funnel),
            "buckets": dict(Counter(p["bucket"] for p in pairs)),
            "arms": {arm: analysis.arm_summary(pairs, arm) for arm in ARMS},
            "deltas": {arm: analysis.delta_stats(pairs, arm) for arm in ("A", "B")},
            "b_over_taken": analysis.delta_over_taken(pairs, "B"),
            "calibration": analysis.calibration(pairs), "weekly": analysis.weekly_deltas(pairs),
            "splits": analysis.split_deltas(pairs), "skips": analysis.skip_summary(pairs),
            "tradeability": tradeability_summary(pairs), "close_bucket": dict(close_bucket),
            "bearish": _bearish_summary(bearish), "verdict": verdict}


def label(payload: dict) -> str:
    calibrated = payload["calibration"]["calibrated"]
    if payload["phase"] == "exploratory":
        tail = "" if calibrated else " -- UNCALIBRATED: the forward read is not started"
        return "EXPLORATORY (no verdict)" + tail
    if payload.get("verdict"):
        return f"VERDICT: {payload['verdict']['study']}"
    return "UNCALIBRATED (no verdict)" if not calibrated else "FORWARD (no verdict yet)"


def _r(value) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _num(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _table(headers, rows) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows] + [""]


def _header(p: dict) -> list[str]:
    return [f"# v229 deferred-entry counterfactual: {p['phase']} read", "", f"**{label(p)}**", "",
            f"- T0: {p['t0']}", f"- Archive last bar: {p['archive_last_bar'] or 'n/a'}",
            f"- Script git SHA: {p['git_sha']}", f"- Frozen rule hash: {p['rule_hash']}", "",
            "Disclosures:", "", *[f"- {line}" for line in p["disclosures"]], ""]


def _population(p: dict) -> list[str]:
    rows = list(p["funnel"].items()) + [(f"bucket {k}", v) for k, v in sorted(p["buckets"].items())]
    return ["## Population funnel", "", *_table(("reason", "count"), rows)]


def _arms(p: dict) -> list[str]:
    rows = [(arm, s["n"], s["taken"], s["wins"], _num(s["win_rate"]), _r(s["exp_r"]), _r(s["total_r"]),
             _r(s["exp_r_gross"])) for arm, s in p["arms"].items()]
    return ["## Arms", "", *_table(("arm", "N", "taken", "wins", "win rate", "ExpR net",
                                    "total R", "ExpR gross"), rows)]


def _deltas(p: dict) -> list[str]:
    rows = [(f"d_{arm}", d["n"], d["weeks"], _r(d["mean"]), _r(d["lower"]), _num(d["p"]))
            for arm, d in p["deltas"].items()]
    taken = p["b_over_taken"]
    return ["## Deltas", "", *_table(("delta", "N", "weeks", "mean", "97.5% lower", "one-sided p"), rows),
            f"d_B over the plans B took (disclosure): n={taken['n']}, mean {_r(taken['mean'])}", ""]


def _calibration(p: dict) -> list[str]:
    cal = p["calibration"]
    rows = [(sim, *(cal["table"][sim][live] for live in analysis.CLASSES)) for sim in analysis.CLASSES]
    return ["## Calibration", "", *_table(("sim \\ live", *analysis.CLASSES), rows),
            f"- Agreement: {_num(cal['agreement'])} over n={cal['n']} (threshold "
            f"{FROZEN['calibration_min']:.2f}); excluded {cal['excluded']}",
            f"- Mean R_C {_r(cal['mean_r_c'])}, mean live R {_r(cal['mean_live_r'])}, "
            f"Spearman {_num(cal['spearman'])} (information only)", ""]


def _weekly_and_splits(p: dict) -> list[str]:
    weeks = [(w["week"], w["n"], _r(w["d_a"]), _r(w["d_b"])) for w in p["weekly"]]
    splits = [(name, c["n"], _r(c["d_a"]), _r(c["d_b"])) for name, c in p["splits"].items()]
    return ["## Per week", "", *_table(("week", "N", "d_A", "d_B"), weeks),
            "## Splits", "", *_table(("cell", "N", "d_A", "d_B"), splits)]


def _tradeability(p: dict) -> list[str]:
    t, skips = p["tradeability"], p["skips"]
    lines = [f"- {key}: {_r(value) if key.startswith('mean_') else value}"
             for key, value in t.items() if not isinstance(value, dict)]
    lines += [f"- {key}: " + ", ".join(f"{k} {_r(v) if isinstance(v, float) or v is None else v}"
                                       for k, v in value.items())
              for key, value in t.items() if isinstance(value, dict)]
    return ["## Arm B skips", "", f"- Skipped: {skips['skipped']}; control R of the skipped plans "
            f"{_r(skips['control_r_of_skipped'])}", "", "## Tradeability", "", *lines, ""]


def _context(p: dict) -> list[str]:
    close, bear = p["close_bucket"], p["bearish"]
    rows = [(arm, s["n"], s["taken"], _r(s["exp_r"])) for arm, s in bear["arms"].items()]
    return ["## Context", "", f"- Live LONG trades opened at or after 15:30 ET: n={close['n']}, "
            f"ExpR {_r(close['exp_r'])}", "", "## Bearish disclosure", "",
            f"Never enters the verdict. n={bear['n']}, d_A {_r(bear['d_a'])}, d_B {_r(bear['d_b'])}", "",
            *_table(("arm", "N", "taken", "ExpR net"), rows)]


def _verdict(p: dict) -> list[str]:
    v = p.get("verdict")
    if not v:
        return []
    ledger = v["ledger"]
    return ["## Verdict", "", f"- Study: {v['study']}",
            *[f"- Arm {arm}: {word}" for arm, word in v["arms"].items()],
            f"- Ledger row: verdict {ledger['verdict']}, n={ledger['n']}, exp_r {_r(ledger['exp_r'])}, "
            f"p {_num(ledger['p'])}", ""]


_SECTIONS = (_header, _population, _arms, _deltas, _calibration, _weekly_and_splits,
             _tradeability, _context, _verdict)


def render_markdown(payload: dict) -> str:
    return "\n".join(line for section in _SECTIONS for line in section(payload)).rstrip() + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_report.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/deferred_entry/report.py tests/scripts/test_deferred_entry_report.py
git commit -m "feat(v229): results Markdown and JSON payload (V229-9)"
```

