# v238 — Replication ladder and additive gate: Part 4, ladder core (V238-9..V238-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V238-11" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (`### Part B — the replication ladder`, "What a ladder buys", `## Constraints`, `## Testing` "Ladder")
**Index:** [2026-11-19-v238-replication-ladder-additive-gate_0-index.md](2026-11-19-v238-replication-ladder-additive-gate_0-index.md) — Goal, `## Global Constraints`, `## Handoff` (rulings 1, 5, 7, 8 and the 2026-11-19 `INPUT_INSTRUMENTS` ruling), `## Decisions this index fixes` (rung shapes, one rung per invocation, ladder input, membership check) and `## Parallelisation` live there and bind every task below.

Lane B1: V238-9 → V238-10; V238-11 and V238-12 each need V238-10 and are parallel (disjoint files); V238-13 needs V238-12 (same file). Part 5 (`replicate_idea.py`) consumes every symbol below exactly as the ledger names it.

Conventions every task shares:

- **No ledger task may be split** (the plan is at the 20-task cap).
- Everything is pure research code under `swingbot/core/backtesting/screen/` (the screen package): no database, no network, no file but the ones a test writes in `tmp_path`. Nothing outside `swingbot/core/backtesting/` imports it (`tests/backtesting/screen/test_import_guard.py`); importing `swingbot/core/planning/` *from* the screen package is allowed.
- Directions are the screen's `"long"` / `"short"` (`screen/sides.py`); the planning adapters translate to `"bullish"` / `"bearish"` internally.
- Week clusters: `instrument/stats.week_cluster_bootstrap` over per-week sums (`screen/verdict.week_sums` / `pooled_mean`, as the screen's own bootstrap does), 10,000 resamples, seed 42; lower bound = 2.5th percentile, one-sided p = share of draws ≤ 0.
- New tests in `tests/backtesting/screen/` join suite `backtesting-arms` and the two ledger test files stay in their suites; after adding tests run `python -m pytest tests/dev/test_suites.py -q`; if `backtesting-arms` passes `max_tests` (1200), split it by feature in `tests/suites.toml` in the same commit (give `tests/backtesting/screen/` its own suite), never raise the limit.
- Every new function stays under complexity 15 (`python scripts/dev/complexity_gate.py`).

# Phase 4 — Ladder core

### Task V238-9: Ledger vocabulary: ladder-v1 and ladder verdicts

**Model:** sonnet — appends to two pinned tuples and updates their pinned tests; no logic changes.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/stats.py:113-126` (the `VERDICTS` comment block, `VERDICTS`, `INSTRUMENTS`)
- Modify: `tests/backtesting/test_instrument_stats_ledger.py:19-24` (pinned tuples) and `:158-164` (`test_the_avoid_label_is_appended_last_and_the_old_order_is_kept`); append the new tests at the end
- Modify: `tests/backtest_scripts/test_screen_avoid_mode.py:262` (pins `VERDICTS[-1]`)
- Modify: `tests/scripts/test_preregistration_ledger_cli.py` (append one test)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (index ledger, final): `"ladder-v1"` appended last to `stats.INSTRUMENTS`; `"LADDER-HOLD"`, `"LADDER-FAIL"`, `"LADDER-UNDERPOWERED"` appended, in that order, to `stats.VERDICTS`. V238-10 pins `ladder.LADDER_INSTRUMENT`, `ladder.HOLD`, `ladder.FAIL`, `ladder.UNDERPOWERED` against these strings. `LADDER-UNAVAILABLE` is **not** a ledger verdict: it is a refusal before any outcome is read and writes no row (index `## Handoff` ruling 8).

Why nothing else changes: `swingbot/admin/api_v1/research.py:78-79` serves `list(stats.VERDICTS)` / `list(stats.INSTRUMENTS)` and `tests/admin/test_api_v1_research.py:71-72` compares against the same tuples, so both follow automatically; `scripts/reports/preregistration_ledger.py:42,46` takes its `choices` from the tuples; the research page renders an unknown verdict `neutral` (`frontend/src/app/workspaces/research/research.ts:299`, `VERDICT_TONE[verdict] ?? 'neutral'`), so no frontend edit (index decision). `tests/analytics/test_override_verdict.py:91` pins `VERDICTS[9:12]`, which an append does not move. Ladder rows carry a `p` (the hold rule's one-sided p), so they join the one BH family `ledger_qvalues` already computes over every row with a p; no rule changes.

- [ ] **Step 1: Update the pinned tests and add the new ones (failing)**

In `tests/backtesting/test_instrument_stats_ledger.py`, replace the body of `test_fields_and_vocabularies_are_the_plan_set` with:

```python
def test_fields_and_vocabularies_are_the_plan_set():
    assert stats.LEDGER_FIELDS == ("id", "date", "hypothesis", "instrument", "n",
                                   "exp_r", "p", "verdict", "record")
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN", "SCREEN-PASS", "SCREEN-FAIL",
                              "SCREEN-UNDERPOWERED", "COST", "SAVED", "INCONCLUSIVE",
                              "DESCRIPTION", "SCREEN-AVOID-PASS",
                              "LADDER-HOLD", "LADDER-FAIL", "LADDER-UNDERPOWERED")
    assert stats.INSTRUMENTS == ("v1", "v2", "screen-v1", "v3", "screen-v2", "ladder-v1")
```

Replace `test_the_avoid_label_is_appended_last_and_the_old_order_is_kept` with (v214's label no longer sits last; what it pinned, an append that never reorders, still holds):

```python
def test_the_avoid_label_keeps_its_place_and_the_old_order_is_kept():
    """v214: an addition, never a reorder; the committed ledger is never edited.
    v238 appended the ladder verdicts after it."""
    assert stats.VERDICTS[13] == "SCREEN-AVOID-PASS"
    assert stats.VERDICTS.count("SCREEN-AVOID-PASS") == 1
    rows = stats.load_ledger()
    assert all(row["verdict"] in stats.VERDICTS for row in rows)
```

Append at the end of the file:

```python
# --- v238: the replication ladder's instrument and verdicts ----------------

LADDER_VERDICTS = ("LADDER-HOLD", "LADDER-FAIL", "LADDER-UNDERPOWERED")


def test_the_ladder_verdicts_are_appended_after_every_older_verdict():
    """An append, never a reorder: every row written before v238 keeps its
    verdict's position, and the three ladder labels sit last, in rule order."""
    assert stats.VERDICTS[:14][-1] == "SCREEN-AVOID-PASS"
    assert stats.VERDICTS[-3:] == LADDER_VERDICTS
    assert len(set(stats.VERDICTS)) == len(stats.VERDICTS)


def test_ladder_v1_is_the_last_instrument():
    assert stats.INSTRUMENTS[-1] == "ladder-v1"
    assert stats.INSTRUMENTS[:5] == ("v1", "v2", "screen-v1", "v3", "screen-v2")


def test_unavailable_is_a_refusal_not_a_ledger_verdict():
    """LADDER-UNAVAILABLE spends no shot and writes no row (index ruling 8)."""
    assert "LADDER-UNAVAILABLE" not in stats.VERDICTS
    with pytest.raises(ValueError, match="invalid field"):
        stats.validate_ledger_row(_row(id="ladder-demo-r1", instrument="ladder-v1",
                                       verdict="LADDER-UNAVAILABLE"))


@pytest.mark.parametrize("verdict", LADDER_VERDICTS)
def test_a_ladder_row_validates_with_its_data_source(verdict):
    stats.validate_ledger_row(_row(id="ladder-demo-r1", instrument="ladder-v1",
                                   verdict=verdict, data_source="alpaca"))


def test_a_ladder_row_enters_the_same_bh_family():
    rows = [_row(id="a", p=0.01),
            _row(id="ladder-demo-r1", instrument="ladder-v1", verdict="LADDER-HOLD",
                 p=0.04, data_source="alpaca")]
    for row in rows:
        stats.validate_ledger_row(row)
    assert stats.ledger_qvalues(rows) == {"a": pytest.approx(0.02),
                                          "ladder-demo-r1": pytest.approx(0.04)}


def test_a_ladder_row_appends_and_reloads(tmp_path):
    path = tmp_path / "ledger.jsonl"
    row = _row(id="ladder-demo-r1", instrument="ladder-v1", verdict="LADDER-FAIL",
               data_source="alpaca")
    stats.append_ledger_row(row, path)
    assert stats.load_ledger(path) == [row]
    with pytest.raises(ValueError, match="duplicate id"):
        stats.append_ledger_row(row, path)
```

In `tests/backtest_scripts/test_screen_avoid_mode.py`, replace line 262:

```python
    assert verdict.SCREEN_AVOID_PASS == stats.VERDICTS[13] == "SCREEN-AVOID-PASS"
```

Append to `tests/scripts/test_preregistration_ledger_cli.py`:

```python
# --- v238: the ladder's instrument and verdicts reach the CLI --------------------------

def test_a_ladder_row_is_accepted_by_the_cli(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    code = cli.main(_args(ledger, **{"--id": "ladder-demo-r1", "--instrument": "ladder-v1",
                                     "--verdict": "LADDER-HOLD", "--data-source": "alpaca"}))
    assert code == 0
    row = stats.load_ledger(ledger)[0]
    assert (row["instrument"], row["verdict"], row["data_source"]) == (
        "ladder-v1", "LADDER-HOLD", "alpaca")
```

Before relying on `--data-source`, confirm the flag name: `git grep -n "data-source" scripts/reports/preregistration_ledger.py` (the v162 tests at `:92-110` of the test file already use it; reuse their spelling if it differs).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py`
Expected: FAIL — `test_fields_and_vocabularies_are_the_plan_set`, the ladder-verdict and instrument tests and `test_a_ladder_row_*` fail (`invalid field(s) ['instrument', 'verdict']`).

- [ ] **Step 3: Append the vocabulary**

In `swingbot/core/backtesting/instrument/stats.py`, extend the comment above `VERDICTS` and the two tuples:

```python
#: v214 appends SCREEN-AVOID-PASS: an avoid-mode screen pass (six clauses
#: against the null and a control arm), which licenses a veto spec only; its
#: p (share of resamples >= 0) is in the same BH family.
#: v238 appends the replication ladder's three verdicts (instrument
#: ladder-v1): a rung holds when the week-clustered lower 95% bound of its net
#: mean R is above zero with N >= 300. LADDER-UNAVAILABLE is a refusal before
#: any outcome is read and is never written. Their p is in the same BH family.
VERDICTS = ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE", "WITHDRAWN", "OPEN",
            "SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED",
            "COST", "SAVED", "INCONCLUSIVE", "DESCRIPTION", "SCREEN-AVOID-PASS",
            "LADDER-HOLD", "LADDER-FAIL", "LADDER-UNDERPOWERED")
INSTRUMENTS = ("v1", "v2", "screen-v1", "v3", "screen-v2", "ladder-v1")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py`
Expected: PASS, `0 failed`, `0 xfailed` (`test_the_committed_ledger_still_loads_unchanged` still green: no committed row changes).

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/analytics/test_override_verdict.py` and `python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py`
Expected: both PASS untouched (both read the tuples, so the append flows through).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_ledger.py tests/backtest_scripts/test_screen_avoid_mode.py tests/scripts/test_preregistration_ledger_cli.py
git commit -m "feat(ledger): v238 ladder-v1 instrument and LADDER-HOLD/FAIL/UNDERPOWERED verdicts (appended)"
```

### Task V238-10: Ladder rules: ids, windows, hold rule, paired difference, refusals

**Model:** opus — fixes the ladder's verdict semantics (hold rule, rung order, next step) that every rung and ledger row depends on.

**Files:**
- Create: `swingbot/core/backtesting/screen/ladder.py`
- Test: `tests/backtesting/screen/test_ladder.py` (create; suite `backtesting-arms`)

**Interfaces:**
- Consumes: the V238-9 ledger strings; `stats.week_cluster_bootstrap` (`instrument/stats.py:57`); `screen/verdict.PairedEvent`, `week_sums`, `pooled_mean` (`screen/verdict.py:44, 88, 93`); `screen/ideas.IDEAS` (tests only).
- Produces: exactly the index ledger row V238-10. Beyond it: ISO-string dates; `LadderEvent.key -> (ticker, signal_date)` (a property, so `asdict` round-trips); the pure rule `hold_verdict(n, lo, *, rung, delta=None)`; `paired_difference` = lower rung minus the rung above on shared keys; `membership_coverage` keys `members`, `in_store`, `missing_count`, `missing`. Two extra exports for Part 5 (no ledger symbol changes): `input_row(name, rows) -> Mapping | None` and `BIASED_NULL_NOTE` (the 2026-11-19 ruling's disclosure for a `screen-v1` input).

Rules (spec `### Part B` hold rule and "What a ladder buys"; index decisions) are pinned by the tests below: strict `lo > 0`, rung 1's strict positive delta against the null, rung order, one shot per id, `screen2-` governing `screen-`, and the next-step table.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_ladder.py`:

```python
"""v238: the replication ladder's rules (v230 spec Part B)."""
from dataclasses import asdict
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import ladder
from swingbot.core.backtesting.screen.ideas import IDEAS

FAST = {"n_resamples": 300, "seed": 42}
H, F, U = ladder.HOLD, ladder.FAIL, ladder.UNDERPOWERED


def _events(rs, *, ticker="AAA", r_null=None):
    """One event per business day from 2017-03-01 (many ISO weeks)."""
    days = pd.bdate_range("2017-03-01", periods=len(rs) + 1).strftime("%Y-%m-%d")
    return [ladder.LadderEvent(ticker, days[i], days[i + 1], days[i + 1], float(r),
                               float(r), "target", r_null=r_null)
            for i, r in enumerate(rs)]


def _row(row_id, verdict, instrument="ladder-v1"):
    return {"id": row_id, "verdict": verdict, "instrument": instrument}


def test_vocabulary_windows_and_ids():
    assert ladder.LADDER_INSTRUMENT in stats.INSTRUMENTS
    assert all(label in stats.VERDICTS for label in (H, F, U))
    assert ladder.UNAVAILABLE == "LADDER-UNAVAILABLE" not in stats.VERDICTS
    assert ladder.INPUT_INSTRUMENTS == ("screen-v1", "screen-v2")
    assert ladder.NULL_VERSION == "v1" and "v230 placebo" in ladder.BIASED_NULL_NOTE
    assert (ladder.STORE_START, ladder.EVENT_START, ladder.READ_END) == (
        "2016-01-04", "2017-03-01", "2020-12-31")
    assert ladder.RUNGS == (1, 2, 3, 4) and set(ladder.RUNG_NAMES) == set(ladder.RUNGS)
    assert ladder.ladder_id("turtle_soup", 3) == "ladder-turtle_soup-r3"
    for bad in (("turtle_soup", 5), (" ", 1)):
        with pytest.raises(ValueError):
            ladder.ladder_id(*bad)
    event = _events([0.5])[0]
    assert ladder.LadderEvent(**asdict(event)) == event and event.key == ("AAA", event.signal_date)


@pytest.mark.parametrize("n, lo, rung, delta, expected", [
    (299, 0.5, 2, None, U), (300, 0.5, 2, None, H), (300, 0.0, 2, None, F),
    (300, 1e-12, 2, None, H), (300, None, 2, None, F), (300, 0.5, 1, 0.01, H),
    (300, 0.5, 1, 0.0, F), (300, 0.5, 1, None, F), (299, -1.0, 1, None, U),
])
def test_hold_verdict_boundaries(n, lo, rung, delta, expected):
    assert ladder.hold_verdict(n, lo, rung=rung, delta=delta) == expected


def test_hold_at_299_and_300_events():
    assert ladder.hold(_events([0.5] * 299), rung=2, **FAST).verdict == U
    result = ladder.hold(_events([0.5] * 300), rung=2, **FAST)
    assert (result.verdict, result.n, result.p, result.delta_null) == (H, 300, 0.0, None)
    assert result.mean == pytest.approx(0.5) and result.lo == pytest.approx(0.5)


def test_hold_fails_when_the_interval_straddles_zero_and_is_seeded():
    events = _events([1.0, -1.0] * 200)
    result = ladder.hold(events, rung=3, **FAST)
    assert result.verdict == F and result.lo < 0.0 < result.hi and 0.0 < result.p < 1.0
    assert ladder.hold(events, rung=3, **FAST) == result
    assert ladder.hold([], rung=2, **FAST) == ladder.HoldResult(U, 0, None, None, None, None, None)


def test_rung_one_needs_a_positive_delta_against_the_null():
    beats = ladder.hold(_events([0.5] * 300, r_null=0.2), rung=1, **FAST)
    assert beats.verdict == H and beats.delta_null == pytest.approx(0.3)
    loses = ladder.hold(_events([0.5] * 300, r_null=0.6), rung=1, **FAST)
    assert loses.verdict == F and loses.delta_null == pytest.approx(-0.1)
    missing = ladder.hold(_events([0.5] * 300), rung=1, **FAST)
    assert missing.verdict == F and missing.delta_null is None


def test_paired_difference_on_shared_events_only():
    upper = _events([0.5] * 50)
    lower = [ladder.LadderEvent(e.ticker, e.signal_date, e.entry_date, e.exit_date,
                                e.r - 0.2, e.gross_r, e.outcome) for e in upper[:40]]
    diff = ladder.paired_difference(upper, lower, **FAST)
    assert diff.n == 40 and diff.mean == pytest.approx(-0.2) and diff.wholly_below_zero
    same = ladder.paired_difference(upper, upper, **FAST)
    assert same.mean == 0.0 and not same.wholly_below_zero
    none = ladder.paired_difference(upper, _events([0.5], ticker="BBB"), **FAST)
    assert (none.n, none.mean, none.wholly_below_zero) == (0, None, False)
    with pytest.raises(ValueError, match="duplicate"):
        ladder.paired_difference(upper + upper, lower, **FAST)


def test_input_rows():
    v1 = [_row("screen-demo", "SCREEN-PASS", "screen-v1")]
    assert ladder.input_refusal("demo", v1) is None
    assert ladder.input_row("demo", v1)["instrument"] == "screen-v1"
    assert ladder.input_refusal("demo", [_row("screen2-demo", "SCREEN-PASS", "screen-v2")]) is None
    assert "no governing SCREEN-PASS" in ladder.input_refusal("demo", [])
    assert ladder.input_refusal("demo", [_row("screen-demo", "SCREEN-FAIL", "screen-v1")])
    assert ladder.input_refusal("demo", [_row("screen-demo", "SCREEN-PASS", "v1")])
    superseded = v1 + [_row("screen2-demo", "SCREEN-FAIL", "screen-v2")]
    assert ladder.input_row("demo", superseded) is None


def test_rung_order_and_one_shot_per_id():
    assert ladder.rung_refusal("demo", 1, []) is None
    assert "needs LADDER-HOLD" in ladder.rung_refusal("demo", 2, [])
    held = [_row("ladder-demo-r1", H)]
    assert ladder.rung_refusal("demo", 2, held) is None
    assert ladder.rung_refusal("demo", 3, held) is not None
    assert "LADDER-FAIL" in ladder.rung_refusal("demo", 2, [_row("ladder-demo-r1", F)])
    assert "one shot per id" in ladder.rung_refusal("demo", 1, held)
    assert "not one of" in ladder.rung_refusal("demo", 7, held)


def test_shape_refusal_for_rungs_two_to_four():
    assert all(ladder.shape_refusal(IDEAS["uptrend_pullback"], r) is None for r in ladder.RUNGS)
    level = IDEAS["range_breakdown_stop"]
    assert ladder.shape_refusal(level, 1) is None
    assert ladder.shape_refusal(level, 2).startswith(
        "LADDER-UNAVAILABLE: rung 2 needs the fixed next-open shape")
    assert ladder.shape_refusal(SimpleNamespace(name="t", race_shape="trail", entry="next_open"), 3)


def test_context_refusal_and_membership_coverage(tmp_path):
    for name in ("SPY", "TLT", "AAA"):
        (tmp_path / f"{name}.csv").write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")
    refusal = ladder.context_refusal(IDEAS["dollar_drop"], tmp_path)
    assert refusal.startswith("LADDER-UNAVAILABLE") and "UUP" in refusal
    assert ladder.context_refusal(IDEAS["bond_spike_rebound"], tmp_path) is None
    assert ladder.context_refusal(IDEAS["uptrend_pullback"], tmp_path) is None
    assert ladder.membership_coverage(["CCC", "AAA", "SPY", "AAA"], tmp_path) == {
        "members": 3, "in_store": 2, "missing_count": 1, "missing": ["CCC"]}


OK = ladder.PairedDiff(400, -0.05, -0.12, 0.02, False)
BAD = ladder.PairedDiff(400, -0.20, -0.30, -0.10, True)


@pytest.mark.parametrize("holds, diff, expected", [
    ({}, None, "pending"), ({1: F}, None, "non_replication"), ({1: U}, None, "non_replication"),
    ({1: H}, None, "pending"), ({1: H, 2: F}, None, "partner_open"),
    ({1: H, 2: H}, None, "pending"), ({1: H, 2: H, 3: F}, None, "orderable_shape"),
    ({1: H, 2: H, 3: H}, None, "pending"), ({1: H, 2: H, 3: H, 4: U}, None, "orderable_shape"),
    ({1: H, 2: H, 3: H, 4: H}, BAD, "orderable_shape"), ({1: H, 2: H, 3: H, 4: H}, OK, "bot_shape"),
])
def test_next_step_table(holds, diff, expected):
    assert ladder.next_step(holds, diff) == expected and expected in ladder.NEXT_STEPS


def test_next_step_needs_the_rung_four_difference_and_known_labels():
    with pytest.raises(ValueError, match="paired difference"):
        ladder.next_step({1: H, 2: H, 3: H, 4: H}, None)
    for bad in ({1: "SCREEN-PASS"}, {5: H}):
        with pytest.raises(ValueError):
            ladder.next_step(bad, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.screen.ladder'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/screen/ladder.py`:

```python
"""v238 replication ladder rules (v230 spec Part B): ids, windows, the hold
rule, the paired difference, refusals, next step. Races: ``ladder_race`` /
``ladder_bot``; CLI: scripts/backtest/replicate_idea.py. Rung 1 uses the v1
null (index ruling 1). The ladder never reads 2021+."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import verdict as screen_verdict

LADDER_INSTRUMENT = "ladder-v1"
RUNGS = (1, 2, 3, 4)
RUNG_NAMES = {1: "robustness", 2: "orderable", 3: "bot stop", 4: "bot target"}
STORE_START = "2016-01-04"
EVENT_START = "2017-03-01"
READ_END = "2020-12-31"
HOLD_N = 300
HOLD = "LADDER-HOLD"
FAIL = "LADDER-FAIL"
UNDERPOWERED = "LADDER-UNDERPOWERED"
UNAVAILABLE = "LADDER-UNAVAILABLE"   # a refusal before any outcome is read; never a row
_LABELS = (HOLD, FAIL, UNDERPOWERED)
INPUT_INSTRUMENTS = ("screen-v1", "screen-v2")
_INPUT_PREFIXES = ("screen2-", "screen-")   # a re-screen row governs the first screen
NULL_VERSION = "v1"
BIASED_NULL_NOTE = ("biased null (v230 placebo): the v1 null itself reads +0.27..+0.37R "
                    "on next-open longs, so rung 1's delta against it is not evidence "
                    "on its own; see docs/superpowers/results/2026-11-18-v230-null-placebo.md")
RESAMPLES = 10_000
SEED = 42
_NO_SHOT = "No row, no shot spent."
NEXT_STEPS = {
    "pending": "run the next rung",
    "non_replication": "idea closed as a non-replication; later rungs do not run",
    "partner_open": "rung 1 holds, rung 2 does not: the partner decides (v230 spec, Open)",
    "orderable_shape": ("a strategy spec in the orderable screened shape (rung 2), sized to "
                        "the 2% dollar-risk rule; the failed rung closes that bot stop or "
                        "target for this idea"),
    "bot_shape": "a strategy spec in the bot's shape",
}


def _check_rung(rung: int) -> None:
    if rung not in RUNGS:
        raise ValueError(f"rung {rung!r} is not one of {RUNGS}")


def ladder_id(name: str, rung: int) -> str:
    _check_rung(rung)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a ladder id needs an idea name")
    return f"ladder-{name}-r{rung}"


@dataclass(frozen=True)
class LadderEvent:
    ticker: str
    signal_date: str      # bar t, known at its close
    entry_date: str       # bar t+1, the open fill
    exit_date: str
    r: float              # net R against the planned risk
    gross_r: float
    outcome: str          # a race.OUTCOMES code
    r_null: float | None = None    # rung 1: the v1 null's mean net R for this event
    r_stress: float | None = None  # net R at 2 x slippage (printed, never gating)

    @property
    def key(self) -> tuple[str, str]:
        return (self.ticker, self.signal_date)


@dataclass(frozen=True)
class HoldResult:
    verdict: str
    n: int
    mean: float | None
    lo: float | None
    hi: float | None
    p: float | None
    delta_null: float | None


@dataclass(frozen=True)
class PairedDiff:
    n: int
    mean: float | None
    lo: float | None
    hi: float | None
    wholly_below_zero: bool


def _week_draws(pairs: Sequence[tuple[str, float]], *, n_resamples: int,
                seed: int) -> np.ndarray:
    """Week-clustered bootstrap of the pooled mean of ``(entry_date, value)``."""
    weeks = screen_verdict.week_sums([screen_verdict.PairedEvent(d, v) for d, v in pairs])
    return stats.week_cluster_bootstrap([], weeks, screen_verdict.pooled_mean,
                                        n_resamples=n_resamples, seed=seed)


def _interval(draws: np.ndarray) -> tuple[float | None, float | None, float | None]:
    """(2.5th percentile, 97.5th percentile, share of draws <= 0)."""
    if draws.size == 0:
        return None, None, None
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi), float(np.mean(draws <= 0.0))


def _delta_null(events: Sequence[LadderEvent]) -> float | None:
    if not events or any(e.r_null is None for e in events):
        return None
    return float(np.mean([e.r - e.r_null for e in events]))


def hold_verdict(n: int, lo: float | None, *, rung: int, delta: float | None = None) -> str:
    if n < HOLD_N:
        return UNDERPOWERED
    if lo is None or not lo > 0.0:
        return FAIL
    if rung == 1 and (delta is None or not delta > 0.0):
        return FAIL
    return HOLD


def hold(events: Iterable[LadderEvent], *, rung: int, n_resamples: int = RESAMPLES,
         seed: int = SEED) -> HoldResult:
    _check_rung(rung)
    events = list(events)
    if not events:
        return HoldResult(UNDERPOWERED, 0, None, None, None, None, None)
    lo, hi, p = _interval(_week_draws([(e.entry_date, e.r) for e in events],
                                      n_resamples=n_resamples, seed=seed))
    delta = _delta_null(events) if rung == 1 else None
    return HoldResult(hold_verdict(len(events), lo, rung=rung, delta=delta), len(events),
                      float(np.mean([e.r for e in events])), lo, hi, p, delta)


def _by_key(events: Iterable[LadderEvent]) -> dict:
    out: dict = {}
    for event in events:
        if event.key in out:
            raise ValueError(f"duplicate ladder event {event.key}")
        out[event.key] = event
    return out


def paired_difference(upper: Iterable[LadderEvent], lower: Iterable[LadderEvent], *,
                      n_resamples: int = RESAMPLES, seed: int = SEED) -> PairedDiff:
    """Lower rung minus the rung above, on the events both rungs traded."""
    above, below = _by_key(upper), _by_key(lower)
    pairs = [(e.entry_date, e.r - above[k].r) for k, e in below.items() if k in above]
    if not pairs:
        return PairedDiff(0, None, None, None, False)
    lo, hi, _ = _interval(_week_draws(pairs, n_resamples=n_resamples, seed=seed))
    return PairedDiff(len(pairs), float(np.mean([d for _, d in pairs])), lo, hi,
                      hi is not None and hi < 0.0)


def _row_of(rows: Iterable[Mapping], row_id: str) -> Mapping | None:
    return next((row for row in rows if row.get("id") == row_id), None)


def input_row(name: str, rows: Iterable[Mapping]) -> Mapping | None:
    """The governing screen row if it is a SCREEN-PASS on an input instrument."""
    rows = list(rows)
    for prefix in _INPUT_PREFIXES:
        row = _row_of(rows, prefix + name)
        if row is not None:
            ok = row.get("verdict") == "SCREEN-PASS" and row.get("instrument") in INPUT_INSTRUMENTS
            return row if ok else None
    return None


def input_refusal(name: str, rows: Iterable[Mapping]) -> str | None:
    if input_row(name, rows) is not None:
        return None
    return (f"refused: {name} has no governing SCREEN-PASS row (screen2-{name}, else "
            f"screen-{name}) on {' or '.join(INPUT_INSTRUMENTS)}. {_NO_SHOT}")


def rung_refusal(name: str, rung: int, rows: Iterable[Mapping]) -> str | None:
    if rung not in RUNGS:
        return f"refused: rung {rung!r} is not one of {RUNGS}. {_NO_SHOT}"
    rows = list(rows)
    own = ladder_id(name, rung)
    if _row_of(rows, own) is not None:
        return f"refused: {own} already has a ledger row (one shot per id). {_NO_SHOT}"
    if rung == 1:
        return None
    above_id = ladder_id(name, rung - 1)
    above = _row_of(rows, above_id)
    found = "no row" if above is None else above.get("verdict")
    if found == HOLD:
        return None
    return f"refused: rung {rung} needs {HOLD} on {above_id} (found {found}). {_NO_SHOT}"


def shape_refusal(idea, rung: int) -> str | None:
    if rung == 1 or (idea.race_shape == "fixed" and idea.entry == "next_open"):
        return None
    return (f"{UNAVAILABLE}: rung {rung} needs the fixed next-open shape "
            f"({idea.name} races {idea.race_shape} / {idea.entry}). {_NO_SHOT}")


def context_refusal(idea, store_dir) -> str | None:
    missing = [s for s in idea.context if not (Path(store_dir) / f"{s}.csv").is_file()]
    if not missing:
        return None
    return f"{UNAVAILABLE}: context series {', '.join(missing)} missing from {store_dir}. {_NO_SHOT}"


def membership_coverage(members: Iterable[str], store_dir) -> dict:
    """Printed and recorded before a run; never a refusal (index decision)."""
    names = sorted(set(members))
    missing = [t for t in names if not (Path(store_dir) / f"{t}.csv").is_file()]
    return {"members": len(names), "in_store": len(names) - len(missing),
            "missing_count": len(missing), "missing": missing}


def _check_holds(holds: Mapping[int, str]) -> None:
    bad = [r for r in holds if r not in RUNGS] + [v for v in holds.values() if v not in _LABELS]
    if bad:
        raise ValueError(f"next_step: unknown rung or verdict {bad!r}")


def _early_step(holds: Mapping[int, str]) -> str | None:
    if 1 not in holds:
        return "pending"
    if holds[1] != HOLD:
        return "non_replication"
    if 2 not in holds:
        return "pending"
    return None if holds[2] == HOLD else "partner_open"


def _late_step(holds: Mapping[int, str], diff: PairedDiff | None) -> str:
    for rung in (3, 4):
        if rung not in holds:
            return "pending"
        if holds[rung] != HOLD:
            return "orderable_shape"
    if diff is None:
        raise ValueError("rungs 1-4 hold: next_step needs rung 4's paired difference to rung 2")
    return "orderable_shape" if diff.wholly_below_zero else "bot_shape"


def next_step(holds: Mapping[int, str], diff_4_vs_2: PairedDiff | None) -> str:
    _check_holds(holds)
    return _early_step(holds) or _late_step(holds, diff_4_vs_2)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/complexity_gate.py` and `python -m pytest tests/dev/test_suites.py -q`
Expected: all green (split `backtesting-arms` by feature first if it is over `max_tests`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ladder.py tests/backtesting/screen/test_ladder.py
git commit -m "feat(screen): v238 ladder rules -- ids, windows, hold rule, paired difference, refusals, next step"
```

### Task V238-11: Orderable race: close-anchored levels and gap fills

**Model:** opus — new fill semantics (levels from the signal close, gap fills priced not dropped) that decide every rung 2–4 R.

**Files:**
- Create: `swingbot/core/backtesting/screen/ladder_race.py`
- Test: `tests/backtesting/screen/test_ladder_race.py` (create; suite `backtesting-arms`)

**Interfaces:**
- Consumes: `ladder.LadderEvent` (V238-10); `race.STOP_ATR`, `race.REWARD_RISK`, `race.OUTCOMES`, `race.RaceResult`, `race._first_exit`, `race._check_positions` (`screen/race.py:41-42, 45, 59, 96, 88`, same package); `sides.oriented`, `sides.holding_days`, `sides.net_r` (`screen/sides.py:25, 34, 39`, which charges `frictions.borrow_r` on shorts only); `indicators.atr` (`screen/indicators.py:37`).
- Produces (index ledger, final; Part 5 rungs 2–4 consume): `STRESS_FACTOR = 2`; `orderable_levels(df, signal_pos, *, atr, direction) -> (stop, target)` (arrays, real prices); `race_levels(df, signal_pos, cap, *, stop, target, direction="long", slippage_bps=None, commission=None) -> race.RaceResult`; `gap_through(result) -> (count, summed net R)`; `to_events(ticker, df, result, *, stress=None) -> list[LadderEvent]`. Also `GAP_OUTCOMES = ("gap_stop", "gap_target")`.

Semantics (index decision "Rung shapes"; spec "Fills, every rung"): `race_levels` takes per-event stop and target prices (rung 2 from `orderable_levels`, rungs 3–4 from `ladder_bot`), so one race serves rungs 2–4. Entry = `Open[t+1]`; planned risk = `|Close[t] - stop|` (the share count the alert sizes); bars t+1..t+cap race exactly as `race._first_exit` (open beyond the stop/target exits at that open, low/high touches next, stop first; after the cap, the close). On bar t+1 a gap beyond either level exits at the entry open: gross 0R, net R = the costs. Later gaps fill at the open at their realised R (a gap stop is worse than −1R). Nothing is dropped. `RaceResult.event_pos` holds the **signal** positions. Stress = the same call at `STRESS_FACTOR × base slippage` (slippage never moves an exit, so the events match); Part 5 makes that call and passes it to `to_events(stress=...)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_ladder_race.py`:

```python
"""v238 rung 2: close-anchored levels, open entry, gap fills priced, never dropped."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen import indicators, ladder_race as lr, race, sides
from swingbot.core.backtesting.screen.ladder import LadderEvent
from swingbot.core.edge import frictions
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)     # signal bar: close 100
FREE = {"slippage_bps": 0.0, "commission": 0.0}


def _frame(bars):
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*bars))
    return frame(c, start="2017-03-01", opens=o, highs=h, lows=l)


def _race(bars, cap=3, direction="long", **costs):
    """ATR 2.0 -> risk 3: long stop 97 / target 106; short stop 103 / target 94."""
    df = _frame(bars)
    atr = np.full(len(df), 2.0)
    stop, target = lr.orderable_levels(df, [0], atr=atr, direction=direction)
    return df, lr.race_levels(df, [0], cap, stop=stop, target=target,
                              direction=direction, **(costs or FREE))


def test_levels_are_anchored_on_the_signal_close():
    df = _frame([QUIET, QUIET])
    atr = np.full(2, 2.0)
    assert [a.tolist() for a in lr.orderable_levels(df, [0], atr=atr, direction="long")] == [[97.0], [106.0]]
    assert [a.tolist() for a in lr.orderable_levels(df, [0], atr=atr, direction="short")] == [[103.0], [94.0]]
    with pytest.raises(ValueError):
        lr.orderable_levels(df, [0], atr=atr, direction="up")


def test_target_is_measured_from_the_close_not_the_open():
    bars = [QUIET, (101.0, 102.0, 100.0, 101.0), (101.0, 106.5, 100.5, 106.0), QUIET]
    df, out = _race(bars)
    assert out.outcome.tolist() == ["target"]
    assert out.entry[0] == 101.0 and out.risk[0] == 3.0
    assert out.gross_r[0] == pytest.approx(5.0 / 3.0)
    screened = race.race(df, [0], 3, atr=np.full(len(df), 2.0), **FREE)
    assert screened.outcome.tolist() != ["target"]      # the open-anchored target sits at 107


def test_an_entry_open_below_the_stop_enters_and_exits_at_that_open():
    df, out = _race([QUIET, (95.0, 96.0, 94.0, 95.0), QUIET, QUIET],
                    slippage_bps=None, commission=None)
    assert out.outcome.tolist() == ["gap_stop"] and out.exit_pos.tolist() == [1]
    assert out.entry[0] == 95.0 and out.gross_r[0] == 0.0
    costs = (frictions.apply_frictions(95.0, "sell") - frictions.apply_frictions(95.0, "buy")) / 3.0
    assert out.r[0] == pytest.approx(costs - frictions.commission_r())
    assert out.r[0] < 0.0


def test_an_entry_open_above_the_target_exits_at_that_open():
    _, out = _race([QUIET, (108.0, 109.0, 107.0, 108.0), QUIET, QUIET])
    assert out.outcome.tolist() == ["gap_target"] and out.gross_r[0] == 0.0


def test_a_later_gap_through_the_stop_fills_at_the_open_below_minus_one_r():
    _, out = _race([QUIET, QUIET, (94.0, 95.0, 93.0, 94.0), QUIET])
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r[0] == pytest.approx(-2.0) and out.gross_r[0] < -1.0
    assert lr.gap_through(out) == (1, pytest.approx(-2.0))


def test_the_time_cap_exits_at_the_close_and_no_gap_is_counted():
    _, out = _race([QUIET, QUIET, (100.0, 101.0, 99.0, 102.0), QUIET], cap=2)
    assert out.outcome.tolist() == ["timeout"] and out.exit_pos.tolist() == [2]
    assert out.gross_r[0] == pytest.approx(2.0 / 3.0)
    assert lr.gap_through(out) == (0, 0.0)


def test_short_mirror_pays_borrow_through_sides_net_r():
    bars = [QUIET, (99.0, 100.0, 98.0, 99.0), (95.0, 96.0, 93.5, 94.0), QUIET]
    df, out = _race(bars, direction="short", slippage_bps=None, commission=None)
    assert out.outcome.tolist() == ["target"] and out.entry[0] == 99.0
    assert out.gross_r[0] == pytest.approx(5.0 / 3.0)
    days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
    expected = sides.net_r(np.array([99.0]), np.array([94.0]), np.array([3.0]),
                           direction="short", days=days)
    assert out.r[0] == pytest.approx(expected[0])


def test_bad_levels_and_short_frames_are_refused():
    df = _frame([QUIET, QUIET, QUIET])
    with pytest.raises(ValueError, match="stop"):
        lr.race_levels(df, [0], 1, stop=np.array([101.0]), target=np.array([106.0]))
    with pytest.raises(ValueError, match="stop"):
        lr.race_levels(df, [0], 1, stop=np.array([97.0]), target=np.array([99.0]))
    with pytest.raises(ValueError, match="past the frame"):
        lr.race_levels(df, [0], 5, stop=np.array([97.0]), target=np.array([106.0]))
    empty = lr.race_levels(df, [], 1, stop=np.array([]), target=np.array([]))
    assert len(empty) == 0


def test_levels_never_read_a_later_bar():
    df = random_walk(260, seed=11)

    def stops(d):
        return lr.orderable_levels(d, np.arange(len(d)), atr=indicators.atr(d), direction="long")[0]

    assert_prefix_stable(stops, df, [30, 120, 259])


def test_to_events_carries_dates_and_the_stress_book():
    bars = [QUIET, (101.0, 102.0, 100.0, 101.0), (101.0, 106.5, 100.5, 106.0), QUIET]
    df, out = _race(bars)
    _, stressed = _race(bars, slippage_bps=lr.STRESS_FACTOR * 5.0, commission=0.0)
    [event] = lr.to_events("AAA", df, out, stress=stressed)
    assert isinstance(event, LadderEvent)
    assert (event.signal_date, event.entry_date, event.exit_date) == (
        "2017-03-01", "2017-03-02", "2017-03-03")
    assert event.outcome == "target" and event.r == pytest.approx(5.0 / 3.0)
    assert event.r_stress == pytest.approx(float(stressed.r[0])) and event.r_stress < event.r
    assert event.r_null is None
    assert lr.to_events("AAA", df, out)[0].r_stress is None
    other = lr.race_levels(df, [1], 1, stop=np.array([98.0]), target=np.array([107.0]), **FREE)
    with pytest.raises(ValueError, match="same events"):
        lr.to_events("AAA", df, out, stress=other)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_race.py`
Expected: FAIL — `ImportError: cannot import name 'ladder_race'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/screen/ladder_race.py`:

```python
"""v238 rungs 2-4: the orderable race (v230 spec Part B, index "Rung shapes").

Stop and target are prices known at the signal close, so the alert can rest
them as orders; entry is the open of t+1 and R is measured against the
planned risk |Close[t] - stop|. Bars t+1..t+cap race as race._first_exit:
an open beyond the stop or target exits at that open (on bar t+1 that is
the entry price: gross 0R, net = the costs), then stop/target touches (stop
first), then the close of bar t+cap. No event is dropped for a gap."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import race, sides
from swingbot.core.backtesting.screen.ladder import LadderEvent

STRESS_FACTOR = 2      # the book re-priced at 2 x slippage; printed, never gating
GAP_OUTCOMES = ("gap_stop", "gap_target")
_OHLC = ("Open", "High", "Low", "Close")
_BAD_LEVELS = ("each stop must sit on the loss side of the signal close and each "
               "target beyond it on the profit side")


def _sign(direction: str) -> float:
    if direction == "long":
        return 1.0
    if direction == "short":
        return -1.0
    raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")


def orderable_levels(df: pd.DataFrame, signal_pos, *, atr, direction: str):
    """(stop, target) at race.STOP_ATR / REWARD_RISK x ATR14[t] from Close[t]."""
    pos = np.asarray(signal_pos, dtype=int)
    sign = _sign(direction)
    close = df["Close"].to_numpy(dtype=float)[pos]
    risk = race.STOP_ATR * pd.Series(atr).to_numpy(dtype=float)[pos]
    return close - sign * risk, close + sign * race.REWARD_RISK * risk


def _oriented_levels(close_o, stop, target, sign):
    stop_o = sign * np.asarray(stop, dtype=float)
    target_o = sign * np.asarray(target, dtype=float)
    risk = close_o - stop_o
    ok = np.isfinite(risk) & (risk > 0) & np.isfinite(target_o) & (target_o > close_o)
    if not ok.all():
        raise ValueError(_BAD_LEVELS)
    return stop_o, target_o, risk


def race_levels(df: pd.DataFrame, signal_pos, cap: int, *, stop, target,
                direction: str = "long", slippage_bps=None,
                commission=None) -> race.RaceResult:
    """Race each signal bar t from the open of t+1 to the given stop/target prices."""
    pos = np.asarray(signal_pos, dtype=int)
    race._check_positions(pos, cap, len(df))
    if pos.size == 0:
        return race.RaceResult.empty()
    sign = _sign(direction)
    o, h, l, c = sides.oriented(*(df[col].to_numpy(dtype=float) for col in _OHLC), direction)
    stop_o, target_o, risk = _oriented_levels(c[pos], stop, target, sign)
    bars = pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[pos + 1]
    price, code, offset = race._first_exit(o[bars], h[bars], l[bars], c[bars], stop_o, target_o)
    exit_pos = pos + 1 + offset
    gross = (price - entry) / risk
    entry, price = sign * entry, sign * price            # back to real prices; exact
    net = sides.net_r(entry, price, risk, direction=direction,
                      days=sides.holding_days(df.index, pos + 1, exit_pos),
                      slippage_bps=slippage_bps, commission=commission)
    return race.RaceResult(pos, exit_pos, entry, risk, gross, net,
                           np.asarray(race.OUTCOMES)[code])


def gap_through(result: race.RaceResult) -> tuple[int, float]:
    """Events that exited at a gapped open, and their summed net R."""
    mask = np.isin(result.outcome, GAP_OUTCOMES)
    return int(mask.sum()), float(result.r[mask].sum())


def _same_events(result: race.RaceResult, stress: race.RaceResult) -> None:
    if not (np.array_equal(result.event_pos, stress.event_pos)
            and np.array_equal(result.exit_pos, stress.exit_pos)):
        raise ValueError("the stress book must race the same events to the same exits")


def to_events(ticker: str, df: pd.DataFrame, result: race.RaceResult, *,
              stress: race.RaceResult | None = None) -> list[LadderEvent]:
    """One LadderEvent per raced signal; ``stress`` adds r_stress."""
    if stress is not None:
        _same_events(result, stress)
    day = lambda p: df.index[np.asarray(p, dtype=int)].strftime("%Y-%m-%d")  # noqa: E731
    signal, entry, exit_ = day(result.event_pos), day(result.event_pos + 1), day(result.exit_pos)
    r_stress = [None] * len(result) if stress is None else [float(x) for x in stress.r]
    return [LadderEvent(ticker, signal[i], entry[i], exit_[i], float(result.r[i]),
                        float(result.gross_r[i]), str(result.outcome[i]), r_stress=r_stress[i])
            for i in range(len(result))]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_race.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_race.py` and `python scripts/dev/complexity_gate.py`
Expected: both green (`race.py` is imported, not edited).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ladder_race.py tests/backtesting/screen/test_ladder_race.py
git commit -m "feat(screen): v238 orderable race -- close-anchored levels, open entry, gap fills priced"
```

### Task V238-12: Bot stop adapter (rung 3) with truncation test

**Model:** opus — names the live stop entry point the spec leaves to the builder and must prove no-lookahead on the event bar.

**Files:**
- Create: `swingbot/core/backtesting/screen/ladder_bot.py`
- Test: `tests/backtesting/screen/test_ladder_bot.py` (create; suite `backtesting-arms`)

**Interfaces:**
- Consumes: `ladder` constants (V238-10, for the module's place in the ladder only); `race.REWARD_RISK` (`screen/race.py:42`); live planning pieces, all existing: `swingbot.core.market.indicators.atr(df, period=14)` (`indicators.py:62`, the ATR `build_strategy_plan` uses), `planning.targets._safe_atr_value(entry, atr_val)` (`targets.py:134`), `planning.builders.strategy_entry_reference(df, index, strategy)` (`builders.py:120`), `HORIZONS` (`market/strategy_types.py`; `"2w"`: `atr_stop_multiple` 2.0, `max_risk_pct` 3.0), `risk_limits.HARD_MAX_PLANNED_LOSS_PCT = 2.0`, `risk_limits.planned_loss_pct(entry, stop)` (`risk_limits.py:9, 17`). Tests also use `builders._atr_plan` (`builders.py:48`), `builders._STRUCTURAL_BRANCHES` (`:303`), `targets.atr_target_candidates` (`:143`).
- Produces (index ledger, final; V238-13 extends the file, Part 5 consumes): `BOT_SHAPE: dict[str, str]` with keys `stop_entry_point`, `target_entry_point`, `strategy`, `horizon_key`, `why` (Part 5 prints it in every rung 3/4 results doc, index ruling 7); `bot_stop(df, signal_pos, *, direction) -> float | None`; `rung3_levels(df, signal_pos, *, direction) -> (stop, target)`; `clamp_would_drop(entry, stop, *, direction) -> bool`. Also `plan_direction(direction) -> str` (`"long"`→`"bullish"`, `"short"`→`"bearish"`) and `signal_frame(df, signal_pos)` for V238-13.

**The builder's call (spec `## Left to the builder`, index ruling 7), recorded in `BOT_SHAPE`.** An idea has no strategy or horizon, so the stand-in is the generic ATR branch every strategy without a structural branch sizes through (`builders._atr_branch` → `_atr_plan`): stop = signal close ∓ `HORIZONS["2w"]["atr_stop_multiple"]` × ATR14, with `"RSI"` as the stand-in strategy (an `_atr_branch` strategy, used only for `strategy_entry_reference`, which is the signal close) and `"2w"` as the horizon (14 holding days, nearest the screen's ~10-bar caps). The stop is taken **before** `_bounded_stop`: rung 3 sizes to fixed dollar risk, so a wider stop is a smaller position, never a capped or dropped trade (spec), and `clamp_would_drop` reports the events the 2% price-distance cap (`planned_loss_pct > HARD_MAX_PLANNED_LOSS_PCT`, the `risk_cap` guard's rule) would have dropped. The target keeps rung 2's distance in R: `close ± race.REWARD_RISK × |close − stop|`. Both levels read only `df.iloc[: signal_pos + 1]` (Global Constraints, no-lookahead). Alternatives not taken, for the results doc: a per-idea structural branch (`_sr_branch`, `_fib_branch`) would bind the ladder to one strategy's geometry; the confluence `confluence_stop_geometry` needs a level the idea does not name.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_ladder_bot.py`:

```python
"""v238 rung 3: the bot's stop on the event bar, sized not dropped, no lookahead."""
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.backtesting.screen import ladder_bot as lb
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import builders
from swingbot.core.planning.targets import _safe_atr_value, atr_target_candidates
from swingbot.core.risk_limits import planned_loss_pct
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

BAND = SimpleNamespace(min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _calm():
    """Price near 1000, High/Low +-1: ATR about 2, so 2 ATR is about 0.4%."""
    return frame(np.linspace(1000.0, 1010.0, 80), start="2017-03-01")


def test_bot_shape_names_its_stand_ins():
    assert set(lb.BOT_SHAPE) == {"stop_entry_point", "target_entry_point", "strategy",
                                 "horizon_key", "why"}
    assert lb.BOT_SHAPE["horizon_key"] in HORIZONS
    assert lb.BOT_SHAPE["strategy"] not in builders._STRUCTURAL_BRANCHES   # sizes via _atr_branch
    assert all(isinstance(v, str) and v.strip() for v in lb.BOT_SHAPE.values())


def test_bot_stop_is_the_live_atr_plan_stop_when_inside_the_cap():
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    atr_val = _safe_atr_value(close, float(atr_indicator(df.iloc[: t + 1], 14).iloc[t]))
    live = builders._atr_plan(close, atr_val, "bullish", "2w", "RSI",
                              candidate_levels=atr_target_candidates(close, atr_val, "bullish"),
                              params=BAND)
    assert lb.bot_stop(df, t, direction="long") == pytest.approx(live[0])


def test_a_wide_stop_is_kept_and_flagged_not_capped():
    df, t = random_walk(200, seed=3), 150
    close = float(df["Close"].iloc[t])
    stop = lb.bot_stop(df, t, direction="long")
    atr_val = float(atr_indicator(df.iloc[: t + 1], 14).iloc[t])
    assert stop == pytest.approx(close - HORIZONS["2w"]["atr_stop_multiple"] * atr_val)
    assert planned_loss_pct(close, stop) > 2.0          # ~1.5% daily vol: 2 ATR is ~4%
    assert lb.clamp_would_drop(close, stop, direction="long")


def test_short_stop_mirrors_the_long_stop():
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    long_stop = lb.bot_stop(df, t, direction="long")
    assert lb.bot_stop(df, t, direction="short") == pytest.approx(2 * close - long_stop)


def test_missing_atr_uses_the_live_two_percent_fallback():
    df = _calm()
    close = float(df["Close"].iloc[0])
    assert lb.bot_stop(df, 0, direction="long") == pytest.approx(close - 2.0 * 0.02 * close)


def test_rung3_target_keeps_two_r_from_the_signal_close():
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    for direction in ("long", "short"):
        stop, target = lb.rung3_levels(df, t, direction=direction)
        assert stop == pytest.approx(lb.bot_stop(df, t, direction=direction))
        assert abs(target - close) == pytest.approx(2.0 * abs(close - stop))
        assert (target > close) == (direction == "long")


@pytest.mark.parametrize("entry, stop, direction, dropped", [
    (100.0, 98.0, "long", False), (100.0, 97.99, "long", True),
    (100.0, 102.0, "short", False), (100.0, 102.01, "short", True),
])
def test_clamp_would_drop_at_the_two_percent_boundary(entry, stop, direction, dropped):
    assert lb.clamp_would_drop(entry, stop, direction=direction) is dropped


def test_bad_inputs_are_refused():
    df = _calm()
    with pytest.raises(ValueError):
        lb.bot_stop(df, 10, direction="bullish")
    with pytest.raises(ValueError):
        lb.clamp_would_drop(100.0, 98.0, direction="up")
    with pytest.raises(IndexError):
        lb.bot_stop(df, len(df), direction="long")


def test_stop_and_target_never_read_a_bar_after_the_signal():
    df = random_walk(260, seed=5)
    for t in (20, 120, 200):
        altered = df.copy()
        altered.iloc[t + 1:] = altered.iloc[t + 1:] * 3.0
        for direction in ("long", "short"):
            full = lb.rung3_levels(df, t, direction=direction)
            assert lb.rung3_levels(df.iloc[: t + 1], t, direction=direction) == full
            assert lb.rung3_levels(altered, t, direction=direction) == full

    def stops(d):
        return [lb.bot_stop(d, i, direction="long") for i in range(len(d))]

    assert_prefix_stable(stops, df, [30, 150])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_bot.py`
Expected: FAIL — `ImportError: cannot import name 'ladder_bot'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/screen/ladder_bot.py`:

```python
"""v238 rungs 3-4: the bot's stop and target on each event bar (v230 spec Part B).

Every level reads only ``df.iloc[: signal_pos + 1]``. The stand-ins the spec
leaves to the builder are recorded in BOT_SHAPE and printed in every rung 3/4
results doc (plan v238 index ruling 7)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import race
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.builders import strategy_entry_reference
from swingbot.core.planning.targets import _safe_atr_value
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

BOT_SHAPE = {
    "stop_entry_point": (
        "swingbot/core/planning/builders.py _atr_plan stop geometry (the _atr_branch "
        "every strategy without a structural branch sizes through): "
        "HORIZONS[horizon_key]['atr_stop_multiple'] x ATR14 "
        "(market.indicators.atr, targets._safe_atr_value) from "
        "builders.strategy_entry_reference (the signal close), taken before "
        "_bounded_stop: a wide stop is sized down, never capped or dropped"),
    "target_entry_point": (
        "swingbot/core/planning/targets.py select_structural_target over "
        "market.levels.target_candidates(*build_level_map(frame, HORIZONS[horizon_key], "
        "close), direction), band ScanParams.from_config() min/max_risk_reward_ratio"),
    "strategy": "RSI",
    "horizon_key": "2w",
    "why": (
        "an idea has no strategy or horizon of its own: RSI sizes through the generic "
        "ATR branch and 2w (14 holding days) is the horizon nearest the screen's caps; "
        "the confluence level map is the bot's nearest-real-level source, so rung 4's "
        "no-level attrition is real (the ATR-ladder candidates always qualify)"),
}
_PLAN_SIDE = {"long": "bullish", "short": "bearish"}


def plan_direction(direction: str) -> str:
    """The screen's long/short as the planning layer's bullish/bearish."""
    if direction not in _PLAN_SIDE:
        raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")
    return _PLAN_SIDE[direction]


def signal_frame(df: pd.DataFrame, signal_pos: int) -> pd.DataFrame:
    """The frame as it stood at the signal bar's close."""
    if not 0 <= signal_pos < len(df):
        raise IndexError(f"signal_pos {signal_pos} outside a {len(df)}-bar frame")
    return df.iloc[: signal_pos + 1]


def _close_and_atr(frame: pd.DataFrame, pos: int) -> tuple[float, float]:
    close = strategy_entry_reference(frame, pos, BOT_SHAPE["strategy"])
    return close, _safe_atr_value(close, float(atr_indicator(frame, 14).iloc[pos]))


def bot_stop(df: pd.DataFrame, signal_pos: int, *, direction: str) -> float | None:
    """The bot's ATR-branch stop from the signal close; None on an unusable close."""
    side = plan_direction(direction)
    close, atr_val = _close_and_atr(signal_frame(df, signal_pos), signal_pos)
    if not (np.isfinite(close) and close > 0):
        return None
    risk = HORIZONS[BOT_SHAPE["horizon_key"]]["atr_stop_multiple"] * atr_val
    return close - risk if side == "bullish" else close + risk


def clamp_would_drop(entry: float, stop: float, *, direction: str) -> bool:
    """True when the 2% price-distance cap would have refused this stop."""
    plan_direction(direction)
    return planned_loss_pct(entry, stop) > HARD_MAX_PLANNED_LOSS_PCT


def rung3_levels(df: pd.DataFrame, signal_pos: int, *,
                 direction: str) -> tuple[float | None, float | None]:
    """(bot stop, target at race.REWARD_RISK x the bot stop's risk), from the close."""
    stop = bot_stop(df, signal_pos, direction=direction)
    if stop is None:
        return None, None
    close = float(df["Close"].iloc[signal_pos])
    sign = 1.0 if direction == "long" else -1.0
    return stop, close + sign * race.REWARD_RISK * abs(close - stop)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_bot.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py` and `python scripts/dev/complexity_gate.py`
Expected: both green (the screen package may import `planning`; nothing outside `backtesting/` imports the screen).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ladder_bot.py tests/backtesting/screen/test_ladder_bot.py
git commit -m "feat(screen): v238 bot stop adapter for rung 3 -- ATR-branch stop from the close, sized not dropped"
```

### Task V238-13: Bot target adapter (rung 4), attrition and book survival

**Model:** opus — wires the live target selector and level map into the ladder under no-lookahead and defines the never-gating book-survival read-out.

**Files:**
- Modify: `swingbot/core/backtesting/screen/ladder_bot.py` (append below `rung3_levels`; extend the imports)
- Test: `tests/backtesting/screen/test_ladder_bot_target.py` (create; suite `backtesting-arms`)

**Interfaces:**
- Consumes: in-file `BOT_SHAPE`, `bot_stop`, `clamp_would_drop`, `plan_direction`, `signal_frame` (V238-12); `ladder.LadderEvent` (V238-10); live, existing: `planning.targets.select_structural_target(entry, stop_loss, is_bull, candidate_levels, min_rr, max_rr)` (`targets.py:10`), `market.levels.build_level_map(df, h, current_price, candidates=None, params=None) -> (supports, resistances)` (`levels.py:579`), `market.levels.target_candidates(supports, resistances, direction)` (`levels.py:595`), `swingbot.scan_params.ScanParams.from_config()` (`min_risk_reward_ratio`, `max_risk_reward_ratio`; `scan_params.py:74-75, 107`).
- Produces (index ledger, final; Part 5 rung 4 and its results doc consume): `ATTRITION = ("no_level_in_band", "risk_cap")`; `rung4_levels(df, signal_pos, *, direction) -> (stop, target, reason)` (`reason` is `None` when the event trades, else an `ATTRITION` entry, and `target` is then `None`); `book_survival(events, *, max_open) -> dict` with keys `one_per_ticker_share`, `concurrent_share`, `signals_per_day_p95`, `signals_per_day_max`. Part 5 passes `max_open=config.MAX_OPEN_POSITIONS` (the account default, 30).

Semantics (spec `### Part B` rung 4 and its reporting bullet; `BOT_SHAPE["target_entry_point"]`):
- `rung4_levels` keeps rung 3's stop. A stop the 2% cap refuses (`clamp_would_drop`, or no usable stop: `planned_loss_pct` is infinite) is attrition `risk_cap`, and the level map is not built. Otherwise the target is `select_structural_target` over the confluence level map built from `signal_frame(df, signal_pos)` with the horizon `BOT_SHAPE["horizon_key"]`, in the `ScanParams` band (1.5–2.5 R:R by default; nearest qualifying level; beyond the cap the synthetic price at the cap). No qualifying level is attrition `no_level_in_band`: no trade.
- `book_survival` is reported, never gating. One position per ticker: in `(signal_date, ticker)` order an event is kept when its signal date is on or after the ticker's previous kept exit date (the date form of `race.non_overlapping`). Concurrent limit: the one-per-ticker survivors in `(entry_date, ticker)` order, kept while fewer than `max_open` positions are open (a position counts as open through its exit date). Both shares are over **all** events; `concurrent_share` is the share surviving both rules. Signals per day count every event by `signal_date` over days with at least one signal. No events: shares and p95 `None`, max `0`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_ladder_bot_target.py`:

```python
"""v238 rung 4: the bot's target band on the event bar, attrition, book survival."""
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.backtesting.screen import ladder_bot as lb
from swingbot.core.backtesting.screen.ladder import LadderEvent
from tests.backtesting.screen.helpers import frame, random_walk

BAND = SimpleNamespace(min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _calm():
    return frame(np.linspace(1000.0, 1010.0, 80), start="2017-03-01")


def _quiet_walk(n=300, seed=9):
    """A random walk squeezed to ~0.3% daily moves, so 2 ATR stays inside 2%."""
    df = random_walk(n, seed=seed, start="2016-01-04")
    for col in ("Open", "High", "Low", "Close"):
        df[col] = 100.0 + (df[col] - 100.0) * 0.2
    return df


@pytest.fixture
def band(monkeypatch):
    monkeypatch.setattr(lb, "_scan_params", lambda: BAND)

    def use(levels):
        monkeypatch.setattr(lb, "_target_candidates",
                            lambda frame_, close, side: [close + d for d in levels])
    return use


@pytest.mark.parametrize("offsets, expected_r, reason", [
    ([5.0], None, "no_level_in_band"),            # 1.25 R: below the 1.5 floor
    ([], None, "no_level_in_band"),
    ([7.0, 9.0], 1.75, None),                      # nearest qualifying level
    ([20.0], 2.5, None),                           # beyond the cap: synthetic price at 2.5 R
])
def test_rung4_target_band(band, offsets, expected_r, reason):
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    band(offsets)
    stop, target, why = lb.rung4_levels(df, t, direction="long")
    assert stop == pytest.approx(lb.bot_stop(df, t, direction="long"))
    assert why == reason
    if expected_r is None:
        assert target is None
    else:
        assert (target - close) / (close - stop) == pytest.approx(expected_r, rel=1e-3)


def test_a_stop_past_the_cap_is_risk_cap_attrition_before_any_level_is_built(monkeypatch):
    monkeypatch.setattr(lb, "_target_candidates",
                        lambda *a: pytest.fail("the level map must not be built"))
    df, t = random_walk(200, seed=3), 150
    stop, target, why = lb.rung4_levels(df, t, direction="long")
    assert (target, why) == (None, "risk_cap")
    assert stop == pytest.approx(lb.bot_stop(df, t, direction="long"))
    assert set(lb.ATTRITION) == {"no_level_in_band", "risk_cap"}


def test_the_live_level_map_lands_inside_the_band():
    df = _quiet_walk()
    params = lb._scan_params()
    seen = set()
    for t in range(120, 300, 30):
        for direction in ("long", "short"):
            stop, target, why = lb.rung4_levels(df, t, direction=direction)
            seen.add(why)
            assert why in (None, *lb.ATTRITION)
            if why is None:
                close = float(df["Close"].iloc[t])
                rr = abs(target - close) / abs(close - stop)
                assert params.min_risk_reward_ratio - 1e-6 <= rr <= params.max_risk_reward_ratio + 1e-6
                assert (target > close) == (direction == "long")
    assert "risk_cap" not in seen


def test_rung4_levels_never_read_a_bar_after_the_signal():
    df = _quiet_walk()
    for t in (150, 250):
        altered = df.copy()
        altered.iloc[t + 1:] = altered.iloc[t + 1:] * 3.0
        for direction in ("long", "short"):
            full = lb.rung4_levels(df, t, direction=direction)
            assert lb.rung4_levels(df.iloc[: t + 1], t, direction=direction) == full
            assert lb.rung4_levels(altered, t, direction=direction) == full


def _e(ticker, signal, entry, exit_):
    return LadderEvent(ticker, signal, entry, exit_, 0.1, 0.1, "target")


EVENTS = [
    _e("AAA", "2017-03-01", "2017-03-02", "2017-03-08"),
    _e("AAA", "2017-03-03", "2017-03-06", "2017-03-10"),   # inside AAA's open trade: dropped
    _e("AAA", "2017-03-08", "2017-03-09", "2017-03-15"),   # signal on the exit date: kept
    _e("BBB", "2017-03-03", "2017-03-06", "2017-03-07"),
]


def test_book_survival_one_per_ticker_and_concurrent_limit():
    wide = lb.book_survival(EVENTS, max_open=30)
    assert wide["one_per_ticker_share"] == pytest.approx(0.75)
    assert wide["concurrent_share"] == pytest.approx(0.75)
    tight = lb.book_survival(list(reversed(EVENTS)), max_open=1)
    assert tight["one_per_ticker_share"] == pytest.approx(0.75)
    assert tight["concurrent_share"] == pytest.approx(0.5)    # BBB waits on AAA's 03-08 exit


def test_book_survival_signals_per_day():
    out = lb.book_survival(EVENTS, max_open=30)
    assert out["signals_per_day_max"] == 2
    assert out["signals_per_day_p95"] == pytest.approx(float(np.percentile([1, 2, 1], 95)))


def test_book_survival_empty_and_bad_limit():
    assert lb.book_survival([], max_open=30) == {
        "one_per_ticker_share": None, "concurrent_share": None,
        "signals_per_day_p95": None, "signals_per_day_max": 0}
    with pytest.raises(ValueError):
        lb.book_survival(EVENTS, max_open=0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_bot_target.py`
Expected: FAIL — `AttributeError: module ... ladder_bot has no attribute '_scan_params'` (and `rung4_levels`, `book_survival`).

- [ ] **Step 3: Extend the module**

In `swingbot/core/backtesting/screen/ladder_bot.py`, add to the imports:

```python
from collections import Counter
from collections.abc import Iterable

from swingbot.core.backtesting.screen.ladder import LadderEvent
from swingbot.core.market import levels as market_levels
from swingbot.core.planning.targets import select_structural_target
```

(merge `select_structural_target` into the existing `from swingbot.core.planning.targets import _safe_atr_value` line). Append below `rung3_levels`:

```python
ATTRITION = ("no_level_in_band", "risk_cap")


def _scan_params():
    """The live reward:risk band (a seam the tests replace)."""
    from swingbot.scan_params import ScanParams
    return ScanParams.from_config()


def _target_candidates(frame: pd.DataFrame, close: float, side: str) -> list[float]:
    """The confluence level map's trade-side prices, nearest first."""
    supports, resistances = market_levels.build_level_map(
        frame, HORIZONS[BOT_SHAPE["horizon_key"]], close)
    return market_levels.target_candidates(supports, resistances, side)


def rung4_levels(df: pd.DataFrame, signal_pos: int, *,
                 direction: str) -> tuple[float | None, float | None, str | None]:
    """(rung 3's stop, the bot's band target, attrition reason or None)."""
    side = plan_direction(direction)
    stop = bot_stop(df, signal_pos, direction=direction)
    close = float(df["Close"].iloc[signal_pos])
    if stop is None or clamp_would_drop(close, stop, direction=direction):
        return stop, None, "risk_cap"
    params = _scan_params()
    target = select_structural_target(
        close, stop, side == "bullish",
        _target_candidates(signal_frame(df, signal_pos), close, side),
        params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    if target is None:
        return stop, None, "no_level_in_band"
    return stop, float(target), None


def _one_per_ticker(events: list[LadderEvent]) -> list[LadderEvent]:
    kept, busy = [], {}
    for event in sorted(events, key=lambda e: (e.signal_date, e.ticker)):
        if event.signal_date >= busy.get(event.ticker, ""):
            kept.append(event)
            busy[event.ticker] = event.exit_date
    return kept


def _concurrent(events: list[LadderEvent], max_open: int) -> list[LadderEvent]:
    kept, open_exits = [], []
    for event in sorted(events, key=lambda e: (e.entry_date, e.ticker)):
        open_exits = [x for x in open_exits if x >= event.entry_date]
        if len(open_exits) < max_open:
            kept.append(event)
            open_exits.append(event.exit_date)
    return kept


def book_survival(events: Iterable[LadderEvent], *, max_open: int) -> dict:
    """Shares of all events that survive one position per ticker, and that
    plus the concurrent-position limit; signals per day. Never gating."""
    if max_open < 1:
        raise ValueError("max_open must be at least 1")
    events = list(events)
    if not events:
        return {"one_per_ticker_share": None, "concurrent_share": None,
                "signals_per_day_p95": None, "signals_per_day_max": 0}
    single = _one_per_ticker(events)
    both = _concurrent(single, max_open)
    per_day = np.array(list(Counter(e.signal_date for e in events).values()), dtype=float)
    return {"one_per_ticker_share": len(single) / len(events),
            "concurrent_share": len(both) / len(events),
            "signals_per_day_p95": float(np.percentile(per_day, 95)),
            "signals_per_day_max": int(per_day.max())}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_bot_target.py`
Expected: PASS, `0 failed`, `0 xfailed`. If `test_the_live_level_map_lands_inside_the_band` reports `risk_cap` in `seen`, the squeeze factor left 2 ATR above 2%: lower `0.2` to `0.1` in `_quiet_walk` (a fixture choice, not a rule change).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ladder_bot.py`, `python scripts/dev/complexity_gate.py` and `python -m pytest tests/dev/test_suites.py -q`
Expected: all green (V238-12's tests untouched; split `backtesting-arms` by feature first if it is over `max_tests`).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ladder_bot.py tests/backtesting/screen/test_ladder_bot_target.py
git commit -m "feat(screen): v238 bot target adapter for rung 4 -- level-map band target, attrition, book survival"
```

