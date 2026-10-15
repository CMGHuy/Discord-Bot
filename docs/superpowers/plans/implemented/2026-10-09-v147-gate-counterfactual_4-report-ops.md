# v147 Gate counterfactual: Part 4, report statistics and inputs (V147-13..V147-14)

> V147-15..V147-18 (report assembly, progress cron, TRAIN runs, full suite) are in [`_4b-report-assembly-ops`](2026-10-09-v147-gate-counterfactual_4b-report-assembly-ops.md), split for the 1500-line cap; the decisions and v150 notes below apply to both files.

> Part of the v147 plan. Header, Global Constraints, deviations, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v147-gate-counterfactual_0-index.md). **Never read this file whole**: `/task-brief V147-13` or `grep -n "^### Task V147-13:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_4-report-ops.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md) § The report, § Pre-registered verdict, § Production progress cron, § TRAIN side (runs), § Testing.

All commands run inside the plan's worktree `.claude/worktrees/2026-10-09-v147-gate-counterfactual` (created by V147-1). Paths below are relative to it.

## Decisions this part carries (controller, 2026-10-10)

- **Fixed-dollar-risk column** (partner approved): `dollar_risk = cf_r * planned_loss_pct / HARD_MAX_PLANNED_LOSS_PCT`, already computed per row by `blocked_recorder.dollar_risk` (V147-4). A report row's `dollar_risk` is the mean over its filled `risk_cap` setups.
- **A cell whose taken arm is empty or below the floor gets no verdict.** TRAIN compression is the known case: `compression_research.offline_context()` has no as-of earnings archive, so every moded TRAIN candidate is rejected `earnings_unknown` and the TRAIN taken arm is expected to be empty. Such a cell is written with `verdict = "WAITING"`, `latest = None`, `verdict_of_record = None` and an explicit `note` (`"no TRAIN taken arm — no as-of earnings archive"`), which v150 renders as a note, never as a verdict. Its p enters BH as 1.0 (below).
- **BH family is fixed at the five cells.** A cell with no eligible reading (WAITING, or a note) contributes p = 1.0, so `m` stays 5 as pre-registered and an ineligible cell can only make the others' q larger, never smaller.
- **Gap-through-stop floors at −1R.** `simulate_exit` books a stop at the stop price (V147-2 pins it), so a gap through the stop reads exactly −1.0R. The report's `limitations` and the script's caption state that blocked-arm losses on gaps are understated.
- **Short-lane taken arm.** Live plans carry `source` `"strategy" | "confluence"` and no lane marker, so a `short_lane` blocked row is scoped against `confluence` taken plans of the same direction (both use `build_confluence_plan`). Stated in `limitations`.
- **Taken plans have no stored signal-day close**, so a live taken re-walk is never re-anchored; a split between issue and report would distort that row. Stated in `limitations`.

## Notes for v150 (do not edit v150 files)

- v150's gate step greps `os.replace` in the analytics module. In v147 the atomic write lives in `swingbot/core/infra/gate_counterfactual_store.py` (V147-8, through `jsonio.atomic_write_json`, which calls `os.replace`); `gate_counterfactual_report.py` only calls `store.write_report` and re-exports `load_report`. v150's grep should target the infra store.
- v147 persists `note` on every cell: `"no TRAIN population"` (`rs` × `train`), `"no verdict — no-plan"` (`no_qualifying_target` × both populations) and the empty/below-floor taken-arm notes. Verdict strings are `GATE EARNS`, `GATE COSTS`, `INCONCLUSIVE`, `WAITING`. Rows carry `gate` equal to the cell's `gate` (`rs`, `risk_cap`, `compression`, `no_qualifying_target`), so v150's `row.gate === cell.gate` filter matches.
- Additive keys beyond v150's assumed shape: report `limitations: list[str]`, `bh_family: 5`, `seed: 42`; cell `taken_n`, `latest.p`; row `taken_n`, `taken_realised_exp_r`.

---

# Phase 5: Report

### Task V147-13: Verdict statistics

**Model:** opus — the pre-registered verdict rule (paired week-cluster bootstrap, two-sided p, BH over a fixed family, distinct-setup N) decides every GATE EARNS / COSTS; a slip here mislabels a gate.

**Cross-plan (audit 2026-10-10):** v135 (`headroom`) and v139 (`stop_beyond_confluence_ceiling`, `risk_sizing`) add `plan_rejected` reasons that the live L4/L6 hooks may record. `cell_key` maps only v147's own reasons (`"risk_cap"`, the string V147-5 and V147-10 write, and `"no_qualifying_target"`; a taken row's `None` reason -> `risk_cap`) and sends every other `plan_rejected` reason to `"other"`, which is kept out of `CELLS` and `CELL_GATE`, so those rows never pool into `risk_cap` (Step 3 code and the `test_cell_key` cases below). The p formula: if v146's `2.0 * tail` copy exists, Step 0 moves it into `instrument/stats.py` as written (one copy only).

**Files:**
- Create: `swingbot/core/analytics/gate_counterfactual_report.py`
- Create: `tests/analytics/test_gate_counterfactual_stats.py`
- Modify (only if Step 0 finds v146's copy): `swingbot/core/backtesting/instrument/stats.py` and the v146 module that holds it

**Interfaces:**
- Consumes: `stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed)` (groups by `getattr(obj, "entry_date")`, same week draw for both arms, drops `None` draws) and `stats.bh_qvalues(pvalues)` (exist, `swingbot/core/backtesting/instrument/stats.py:57/86`); `session.nyse_calendar().sessions_between(asof, target)` (exists, `swingbot/core/market/session.py:192/220`); `params.DEFAULT_EXPIRY_BARS = 5` (exists, `swingbot/core/planning/params.py:21`); no V147-4 symbol (the tests build the index's shared row shape locally, so V147-13 stays parallel with V147-4 as the index schedules it).
- Produces (ledger): `VERDICT_FLOOR = 30`, `Q_MAX = 0.10`, `BOOTSTRAP_RESAMPLES = 10_000`, `BOOTSTRAP_SEED = 42`, `NEAR_MISS_BANDS = {"rs": 5.0, "risk_cap": 0.5}`, `CELLS` (the five verdict cells, in order), `two_sided_bootstrap_p(draws) -> float`, `distinct_setups(rows) -> list[dict]`, `arm_stats(rows) -> dict` (`n, filled_n, no_fill_n, no_plan_n, no_data_n, fill_rate, exp_r, win_rate`), `difference_reading(blocked, taken, *, seed=BOOTSTRAP_SEED) -> dict | None` (`difference, ci_low, ci_high, p`), `classify(reading, q, n) -> str`, `cell_key(row) -> str` (`"other"` for any `plan_rejected` reason that is not v147's; never a `CELLS` key). Additive, consumed by V147-15/-16: `EARNS = "GATE EARNS"`, `COSTS = "GATE COSTS"`, `INCONCLUSIVE`, `WAITING`, `VERDICTS`, `CELL_GATE` (cell key → the row `gate` field its taken arm carries), `family_qvalues(pvalues) -> list[float]` (BH over the fixed five-cell family, `None` → 1.0).

**Rules fixed here (spec § Pre-registered verdict, index § Global Constraints):**
- The statistic is blocked ExpR − taken ExpR over distinct **filled** setups. The bootstrap resamples ISO weeks of `entry_date` (`== signal_date`), both arms with the same week draw. Each arm is handed to `week_cluster_bootstrap` as one `(entry_date, total, n)` week-sum per ISO week (v146's recipe), which resamples exactly as per-trade rows would and is cheap at 10,000 draws.
- p is v146's two-sided +1-corrected formula; CI is the 2.5/97.5 percentile of the draws.
- `GATE EARNS`: CI entirely below 0 and q < 0.10; `GATE COSTS`: CI entirely above 0 and q < 0.10; `INCONCLUSIVE` otherwise; `WAITING` below 30 distinct filled blocked setups or with no reading.
- A setup is `(population, arm, cell_key, ticker, strategy, horizon, direction)`; rows of one setup whose signal dates are within the anchor row's pending window (`expiry_bars` NYSE sessions, `DEFAULT_EXPIRY_BARS` when unknown) collapse into the anchor, the earliest row. A row past the window starts a new setup.
- `BOOTSTRAP_RESAMPLES` is read at call time (tests monkeypatch it down); it is never a default-argument value.

- [ ] **Step 0: One copy of the p formula**

Run: `git grep -n "2.0 \* tail" -- swingbot`

- **No hit** (v146 not merged): define `two_sided_bootstrap_p` in `gate_counterfactual_report.py` exactly as in Step 3.
- **A hit in a v146 module** (v146 merged first): move the formula into `swingbot/core/backtesting/instrument/stats.py` as `two_sided_bootstrap_p(draws) -> float` (the body in Step 3), replace v146's inline lines with a call to it, and in Step 3 replace the local definition with `from swingbot.core.backtesting.instrument.stats import two_sided_bootstrap_p`. Run v146's own test file afterwards (`python scripts/dev/testrun.py file <its test>`); its numbers must not change. Either way `test_one_copy_of_the_p_formula` below must pass.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_gate_counterfactual_stats.py`:

```python
"""v147 V147-13: the gate-counterfactual verdict statistics."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from swingbot.core.analytics import gate_counterfactual_report as gcr

REPO = Path(__file__).resolve().parents[2]


def gate_row(**fields) -> dict:
    """The shared gate-row shape (index), built locally so V147-13 does not wait on V147-4."""
    row = {"planned_loss_pct": None, "dollar_risk": None, "in_sample": False, **fields}
    row["entry_date"] = row["signal_date"]
    return row


@pytest.fixture(autouse=True)
def _fast_bootstrap(monkeypatch):
    monkeypatch.setattr(gcr, "BOOTSTRAP_RESAMPLES", 600)


def _row(arm="blocked", *, gate="rs", reason="rs_blocked", ticker="AAPL", day="2024-01-08",
         status="filled", r=0.5, win=True, horizon="2w", population="live", margin=None,
         expiry_bars=5, strategy="Fibonacci", direction="bearish", source="strategy"):
    filled = status == "filled"
    return gate_row(population=population, arm=arm, source=source, ticker=ticker, strategy=strategy,
                    horizon=horizon, direction=direction, signal_date=day, gate=gate,
                    reason=reason if arm == "blocked" else None, margin=margin, cf_status=status,
                    cf_r=r if filled else None, win=win if filled else None, expiry_bars=expiry_bars)


def _weekly(arm, rs, *, start="2024-01-08"):
    """One filled row per ISO week (distinct tickers, so nothing collapses)."""
    first = dt.date.fromisoformat(start)
    return [_row(arm, ticker=f"T{i}", day=(first + dt.timedelta(weeks=i)).isoformat(), r=r, win=r > 0)
            for i, r in enumerate(rs)]


def test_frozen_constants():
    assert (gcr.VERDICT_FLOOR, gcr.Q_MAX, gcr.BOOTSTRAP_SEED) == (30, 0.10, 42)
    assert gcr.NEAR_MISS_BANDS == {"rs": 5.0, "risk_cap": 0.5}
    assert gcr.CELLS == (("rs", "live"), ("risk_cap", "live"), ("compression", "live"),
                         ("risk_cap", "train"), ("compression", "train"))
    assert gcr.VERDICTS == ("GATE EARNS", "GATE COSTS", "INCONCLUSIVE", "WAITING")


def test_the_pre_registered_resample_count_is_ten_thousand():
    # the autouse fixture patches the attribute down; the source keeps the frozen value
    import inspect
    assert "BOOTSTRAP_RESAMPLES = 10_000" in inspect.getsource(gcr)


@pytest.mark.parametrize("draws, expected", [
    ([-1.0, 1.0, 2.0, 3.0], 0.8),            # tail = min(1, 3) + 1 = 2 -> 2 * 2 / 5
    ([0.5] * 9, 0.2),                         # tail = 0 + 1 -> 2 / 10
    ([0.0, 0.0, 0.0], 1.0),                   # zeros count on both sides; capped at 1
])
def test_two_sided_p_is_v146s_plus_one_corrected_formula(draws, expected):
    assert gcr.two_sided_bootstrap_p(draws) == pytest.approx(expected)


def test_p_refuses_an_empty_draw_set():
    with pytest.raises(ValueError):
        gcr.two_sided_bootstrap_p([])


def test_one_copy_of_the_p_formula():
    hits = [p for p in (REPO / "swingbot").rglob("*.py") if "2.0 * tail" in p.read_text(encoding="utf-8")]
    assert len(hits) == 1, hits


@pytest.mark.parametrize("gate, reason, expected", [
    ("rs", "rs_blocked", "rs"), ("compression", "earnings_unknown", "compression"),
    ("plan_rejected", "risk_cap", "risk_cap"), ("plan_rejected", "no_qualifying_target", "no_qualifying_target"),
    ("plan_rejected", None, "risk_cap"),     # a taken confluence row belongs to the risk_cap cell
    ("plan_rejected", "headroom", "other"),  # v135's gate: never pooled into risk_cap
    ("plan_rejected", "stop_beyond_confluence_ceiling", "other"),   # v139
    ("plan_rejected", "risk_sizing", "other"),                      # v139
])
def test_cell_key(gate, reason, expected):
    assert gcr.cell_key({"gate": gate, "reason": reason}) == expected


def test_consecutive_day_blocks_of_one_setup_collapse_to_the_earliest_row():
    rows = [_row(day=d, r=r) for d, r in (("2024-01-10", -1.0), ("2024-01-08", 0.4), ("2024-01-09", 2.0))]
    (setup,) = gcr.distinct_setups(rows)
    assert setup["signal_date"] == "2024-01-08" and setup["cf_r"] == 0.4


def test_a_block_past_the_pending_window_is_a_new_setup():
    rows = [_row(day="2024-01-08", expiry_bars=3), _row(day="2024-01-11", expiry_bars=3),   # 3 sessions: same
            _row(day="2024-01-12", expiry_bars=3)]                                           # 4 sessions: new
    assert [r["signal_date"] for r in gcr.distinct_setups(rows)] == ["2024-01-08", "2024-01-12"]


def test_the_window_counts_nyse_sessions_not_calendar_days():
    # 2024-01-12 (Fri) -> 2024-01-19 (Fri) spans the MLK holiday: 4 sessions, inside a 5-bar window
    rows = [_row(day="2024-01-12"), _row(day="2024-01-19")]
    assert len(gcr.distinct_setups(rows)) == 1


def test_an_unknown_window_uses_the_default_expiry():
    rows = [_row(day="2024-02-05", expiry_bars=None), _row(day="2024-02-12", expiry_bars=None)]   # 5 sessions
    assert len(gcr.distinct_setups(rows)) == 1


@pytest.mark.parametrize("change", [{"horizon": "4w"}, {"ticker": "MSFT"}, {"strategy": "RSI"},
                                    {"population": "train", "gate": "plan_rejected", "reason": "risk_cap"},
                                    {"arm": "taken"}, {"direction": "bullish"}])
def test_different_setup_keys_never_collapse(change):
    assert len(gcr.distinct_setups([_row(), _row(**change)])) == 2


def test_arm_stats_apply_the_one_population_rule():
    rows = [_row(r=1.0, win=True), _row(r=-1.0, win=False), _row(status="no-fill"),
            _row(status="no-plan"), _row(status="no-data")]
    stats = gcr.arm_stats(rows)
    assert stats == {"n": 5, "filled_n": 2, "no_fill_n": 1, "no_plan_n": 1, "no_data_n": 1,
                     "fill_rate": pytest.approx(2 / 3), "exp_r": pytest.approx(0.0),
                     "win_rate": pytest.approx(0.5)}


def test_arm_stats_of_an_arm_with_nothing_filled():
    stats = gcr.arm_stats([_row(status="no-fill")])
    assert (stats["exp_r"], stats["win_rate"], stats["fill_rate"]) == (None, None, 0.0)
    assert gcr.arm_stats([])["fill_rate"] is None


def test_a_reading_needs_a_filled_row_in_both_arms():
    assert gcr.difference_reading(_weekly("blocked", [1.0] * 3), []) is None
    assert gcr.difference_reading([_row(status="no-fill")], _weekly("taken", [1.0])) is None


def test_the_reading_is_the_seeded_blocked_minus_taken_difference():
    blocked, taken = _weekly("blocked", [0.5, -0.2, 1.0, 0.1]), _weekly("taken", [0.1, 0.3, -0.4, 0.2])
    first = gcr.difference_reading(blocked, taken)
    assert first == gcr.difference_reading(blocked, taken)
    assert first["difference"] == pytest.approx(0.35 - 0.05)
    assert first["ci_low"] <= first["difference"] <= first["ci_high"]
    assert 0.0 < first["p"] <= 1.0


def test_no_fill_rows_never_reach_the_reading():
    blocked, taken = _weekly("blocked", [0.5, 0.7]), _weekly("taken", [0.1, 0.3])
    padded = blocked + [_row(status="no-fill", ticker="X", day="2024-01-08")]
    assert gcr.difference_reading(padded, taken) == gcr.difference_reading(blocked, taken)


def _verdict(blocked_rs, taken_rs, *, n=None):
    blocked, taken = _weekly("blocked", blocked_rs), _weekly("taken", taken_rs)
    reading = gcr.difference_reading(blocked, taken)
    return gcr.classify(reading, reading["p"], len(blocked) if n is None else n)


def test_gate_earns_when_blocked_setups_lose_against_taken():
    assert _verdict([-1.0, -0.5] * 20, [1.0, 0.5] * 20) == "GATE EARNS"


def test_gate_costs_when_blocked_setups_beat_taken():
    assert _verdict([1.0, 0.5] * 20, [-1.0, -0.5] * 20) == "GATE COSTS"


def test_inconclusive_when_the_interval_spans_zero():
    assert _verdict([1.0, -1.0] * 20, [-1.0, 1.0] * 20) == "INCONCLUSIVE"


def test_waiting_below_thirty_distinct_filled_setups():
    assert _verdict([-1.0, -0.5] * 20, [1.0, 0.5] * 20, n=29) == "WAITING"
    assert gcr.classify(None, None, 40) == "WAITING"


def test_an_interval_off_zero_still_needs_q_below_ten_percent():
    reading = {"difference": -0.5, "ci_low": -0.9, "ci_high": -0.1, "p": 0.04}
    assert gcr.classify(reading, 0.10, 40) == "INCONCLUSIVE"
    assert gcr.classify(reading, None, 40) == "INCONCLUSIVE"
    assert gcr.classify(reading, 0.0999, 40) == "GATE EARNS"


def test_bh_runs_over_the_fixed_five_cell_family():
    # m stays 5: a cell without a reading enters as p = 1.0, never drops out of the family
    q = gcr.family_qvalues([0.01, None, 0.04, None, None])
    assert q == pytest.approx([0.05, 1.0, 0.1, 1.0, 1.0])


def test_bh_family_refuses_a_family_of_the_wrong_size():
    with pytest.raises(ValueError):
        gcr.family_qvalues([0.01, 0.02])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_gate_counterfactual_stats.py`
Expected: FAIL — `ImportError: cannot import name 'gate_counterfactual_report'`.

- [ ] **Step 3: Write the statistics half of the module**

Create `swingbot/core/analytics/gate_counterfactual_report.py`:

```python
"""v147: the gate-counterfactual report -- what blocked candidates would have done.

V147-13 holds the pre-registered statistics (spec § Pre-registered verdict):
distinct setups, the one population rule, the blocked - taken difference with a
paired week-cluster bootstrap, v146's two-sided p, BH over the five verdict
cells, and the EARNS / COSTS / INCONCLUSIVE / WAITING rule. V147-15 adds
`build_report`. The file itself is written and read by the light
`swingbot.core.infra.gate_counterfactual_store` (this module imports numpy).
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict, namedtuple

import numpy as np

from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import nyse_calendar
from swingbot.core.planning.params import DEFAULT_EXPIRY_BARS

# Frozen by the spec before any row existed. Never tuned.
VERDICT_FLOOR = 30                       # distinct filled blocked setups per cell
Q_MAX = 0.10
BOOTSTRAP_RESAMPLES = 10_000             # read at call time
BOOTSTRAP_SEED = 42
NEAR_MISS_BANDS = {"rs": 5.0, "risk_cap": 0.5}   # absolute cut-offs; compression has no margin
CELLS = (("rs", "live"), ("risk_cap", "live"), ("compression", "live"),
         ("risk_cap", "train"), ("compression", "train"))

EARNS, COSTS, INCONCLUSIVE, WAITING = "GATE EARNS", "GATE COSTS", "INCONCLUSIVE", "WAITING"
VERDICTS = (EARNS, COSTS, INCONCLUSIVE, WAITING)
# cell key -> the `gate` field the cell's rows (blocked and taken) carry
CELL_GATE = {"rs": "rs", "risk_cap": "plan_rejected", "no_qualifying_target": "plan_rejected",
             "compression": "compression"}

_WeekSum = namedtuple("_WeekSum", "entry_date total n")


def two_sided_bootstrap_p(draws) -> float:
    """v146's two-sided, +1-corrected bootstrap p of a difference against 0."""
    values = np.asarray(draws, dtype=float)
    if values.size == 0:
        raise ValueError("two_sided_bootstrap_p needs at least one draw")
    tail = min(int((values <= 0).sum()), int((values >= 0).sum())) + 1
    return min(1.0, 2.0 * tail / (len(values) + 1))


def cell_key(row) -> str:
    """The report cell a row belongs to: rs, risk_cap, compression, no_qualifying_target or other.

    A taken confluence row (gate plan_rejected, reason None) is the risk_cap cell's taken arm.
    Any other plan_rejected reason (another plan's gate: v135 headroom, v139
    stop_beyond_confluence_ceiling / risk_sizing) is "other" -- in no verdict cell, never
    pooled into risk_cap."""
    gate = row["gate"]
    if gate != "plan_rejected":
        return gate
    return {"no_qualifying_target": "no_qualifying_target", "risk_cap": "risk_cap",
            None: "risk_cap"}.get(row.get("reason"), "other")


def _window(row) -> int:
    bars = row.get("expiry_bars")
    return int(bars) if bars is not None else DEFAULT_EXPIRY_BARS


def _sessions_apart(earlier: str, later: str) -> int:
    first, second = dt.date.fromisoformat(earlier[:10]), dt.date.fromisoformat(later[:10])
    span = nyse_calendar().sessions_between(first, second)
    return span if span is not None else (second - first).days


def _setup_key(row) -> tuple:
    return (row["population"], row["arm"], cell_key(row), row["ticker"], row["strategy"],
            row["horizon"], row["direction"])


def _collapse(members: list) -> list:
    """Members sorted by date; keep each anchor, drop rows inside the anchor's pending window."""
    kept, anchor = [], None
    for row in members:
        if anchor is None or _sessions_apart(anchor["signal_date"], row["signal_date"]) > _window(anchor):
            anchor = row
            kept.append(row)
    return kept


def distinct_setups(rows) -> list[dict]:
    """One row per distinct setup: the earliest row of each run of re-blocks (spec § Distinct setups)."""
    groups = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["signal_date"]):
        groups[_setup_key(row)].append(row)
    kept = [row for members in groups.values() for row in _collapse(members)]
    return sorted(kept, key=lambda r: (r["signal_date"], r["ticker"]))


def _mean(values) -> float | None:
    values = [float(v) for v in values]
    return sum(values) / len(values) if values else None


def _filled(rows) -> list:
    return [row for row in rows if row["cf_status"] == "filled"]


def arm_stats(rows) -> dict:
    """Counts, fill rate and the filled-only ExpR / win rate of one arm (the one population rule)."""
    counts = Counter(row["cf_status"] for row in rows)
    filled = _filled(rows)
    tried = counts["filled"] + counts["no-fill"]
    return {"n": len(rows), "filled_n": len(filled), "no_fill_n": counts["no-fill"],
            "no_plan_n": counts["no-plan"], "no_data_n": counts["no-data"],
            "fill_rate": counts["filled"] / tried if tried else None,
            "exp_r": _mean(row["cf_r"] for row in filled),
            "win_rate": _mean(1.0 if row["win"] else 0.0 for row in filled)}


def _week_sums(rows) -> list:
    """One (Monday ISO date, sum of R, count) per ISO week of entry."""
    totals = defaultdict(lambda: [0.0, 0])
    for row in rows:
        year, week, _ = dt.date.fromisoformat(str(row["entry_date"])[:10]).isocalendar()
        bucket = totals[(year, week)]
        bucket[0] += float(row["cf_r"])
        bucket[1] += 1
    return [_WeekSum(dt.date.fromisocalendar(year, week, 1).isoformat(), total, n)
            for (year, week), (total, n) in totals.items()]


def _mean_gap(blocked_draw, taken_draw) -> float | None:
    blocked_n, taken_n = sum(o.n for o in blocked_draw), sum(o.n for o in taken_draw)
    if not blocked_n or not taken_n:
        return None
    return (sum(o.total for o in blocked_draw) / blocked_n
            - sum(o.total for o in taken_draw) / taken_n)


def difference_reading(blocked, taken, *, seed: int = BOOTSTRAP_SEED) -> dict | None:
    """Blocked ExpR - taken ExpR over filled rows, its 95% week-cluster interval and two-sided p.

    None when either arm has no filled row or no bootstrap draw is defined."""
    blocked_filled, taken_filled = _filled(blocked), _filled(taken)
    if not blocked_filled or not taken_filled:
        return None
    draws = stats.week_cluster_bootstrap(_week_sums(blocked_filled), _week_sums(taken_filled),
                                         _mean_gap, n_resamples=BOOTSTRAP_RESAMPLES, seed=seed)
    if draws.size == 0:
        return None
    low, high = np.percentile(draws, [2.5, 97.5])
    point = _mean(r["cf_r"] for r in blocked_filled) - _mean(r["cf_r"] for r in taken_filled)
    return {"difference": float(point), "ci_low": float(low), "ci_high": float(high),
            "p": two_sided_bootstrap_p(draws)}


def family_qvalues(pvalues) -> list[float]:
    """BH q over the fixed five-cell family; a cell without an eligible reading enters as p = 1.0."""
    values = list(pvalues)
    if len(values) != len(CELLS):
        raise ValueError(f"the BH family is the {len(CELLS)} verdict cells, got {len(values)} p-values")
    return stats.bh_qvalues([1.0 if p is None else float(p) for p in values])


def classify(reading, q, n) -> str:
    """The pre-registered three-way verdict, or WAITING below the floor / without a reading."""
    if n < VERDICT_FLOOR or reading is None:
        return WAITING
    if q is None or q >= Q_MAX:
        return INCONCLUSIVE
    if reading["ci_high"] < 0:
        return EARNS
    if reading["ci_low"] > 0:
        return COSTS
    return INCONCLUSIVE
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/analytics/test_gate_counterfactual_stats.py`
Expected: PASS, `0 failed`. If `test_the_window_counts_nyse_sessions_not_calendar_days` fails, check `nyse_calendar()` still lists 2024-01-15 (MLK) as a holiday; do not switch to calendar days.

- [ ] **Step 5: Complexity and syntax**

Run: `python -m radon cc -s -n C swingbot/core/analytics/gate_counterfactual_report.py && python -m py_compile swingbot/core/analytics/gate_counterfactual_report.py`
Expected: no radon output, no error.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/gate_counterfactual_report.py tests/analytics/test_gate_counterfactual_stats.py
git commit -m "feat(v147): gate-counterfactual verdict statistics (V147-13)"
```

### Task V147-14: Report inputs: TRAIN JSONL, live table, live taken re-walk

**Model:** opus — both arms must reach the report through one instrument and one population rule; the live taken re-walk and the arm scoping are where a silent bias would enter.

**Files:**
- Create: `swingbot/core/analytics/gate_counterfactual_inputs.py`
- Create: `tests/analytics/test_gate_counterfactual_inputs.py`

**Interfaces:**
- Consumes: `blocked_recorder.gate_row(...)`, `write_gate_rows(rows, path)` (V147-4); `gate_counterfactual.BlockedCandidate`, `simulate_blocked(candidate, bars, *, last_session=None) -> CounterfactualResult` (V147-2; a stored plan is walked as stored, `pending` while the bars it can read are not all in); `GateRejectionRepository.list_since(since)` / `gate_rejections_repo()` (V147-7; flat records: promoted columns plus doc keys `reason, margin, direction, source, plan, cf_r, win, …`); `plan_types.plan_to_dict` (exists, `swingbot/core/planning/plan_types.py:185`); `PlanStore().all() -> list[TradePlanV2]` (exists, `swingbot/core/planning/plan_store.py:62`; `created_at` is the signal bar's ISO date, `builders.py:603`); `TradeLog().get_trades(status="all", limit=None)` (exists, `swingbot/core/tracking/performance.py:1109`); `metrics.r_multiple(trade)` (exists, `swingbot/core/analytics/metrics.py:173`); `data_store.load_normalized(ticker, "daily")` (exists, `swingbot/core/marketdata/data_store.py:285`); `risk_limits.planned_loss_pct` (exists, `swingbot/core/risk_limits.py:17`); `spot_metals.SPOT_PAIRS` (exists, `swingbot/core/marketdata/spot_metals.py:29`); `strategy_types.COMPRESSION_SHORT` (exists, `swingbot/core/market/strategy_types.py:26`); `session.now_et`, `nyse_calendar`, `session_close` (exist, `swingbot/core/market/session.py:30/220/214`).
- Produces (ledger): `load_train_rows(paths) -> list[dict]`; `live_blocked_rows(records) -> list[dict]`; `live_taken_rows(plans, load_bars, *, last_session=None, realised=None) -> list[dict]` (rows carry `realised_r`); `load_live(*, since="2026-10-01", now=None) -> tuple[list[dict], list[dict]]`. Additive, consumed by V147-15: `LIVE_SINCE = "2026-10-01"`, `default_train_paths() -> list[Path]` (`logs/v147-blocked-*.jsonl` in the repo and `<DATA_DIR>/reports/inputs/v147-blocked-*.jsonl` on the VM), `realised_r_by_plan(trades=None) -> dict[str, float]`, `last_completed_session(now=None) -> str`.

**Rules fixed here:**
- `load_train_rows` refuses (ValueError) any row whose `population` is not `train`, and any TRAIN `rs` row (the RS gate is live-only; v34 is closed). A missing path raises `FileNotFoundError`; defaults only list files that exist.
- `pending` live rows never become report rows. `risk_cap` live rows take `planned_loss_pct` from their stored plan (`trigger_price`, `stop_loss`), so `gate_row` fills `dollar_risk`; a non-finite planned loss is stored as `None`.
- A live taken row is one issued plan re-walked by `simulate_blocked` from the stored plan on the live `market_data/` cache, `last_session` = the last completed NYSE session. One walk per plan, copied once per gate the plan passed and could have been blocked by: always `rs`; `plan_rejected` when `source != "strategy"`; `compression` when `strategy == COMPRESSION_SHORT`. The report scopes each cell's taken arm further by `(source family, direction)` (V147-15). Outlook plans (`origin == "next_session"`) and spot metals are out (no blocked row is ever recorded from them). A `pending` walk is skipped until its bars are in.
- `realised_r` is the closed trade's realised R (context only, never compared); `None` when the plan never closed a trade.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_gate_counterfactual_inputs.py`:

```python
"""v147 V147-14: the report's inputs -- TRAIN JSONL, the live table, live taken re-walks."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from swingbot import config
from swingbot.core.analytics import gate_counterfactual_inputs as gci
from swingbot.core.backtesting.blocked_recorder import gate_row, write_gate_rows
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv

WARM = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (100.5, 103.0, 100.2, 102.5)
FLAT = (100.2, 100.6, 99.8, 100.3)


def _train(**kw):
    base = dict(population="train", arm="blocked", source="confluence", ticker="AAPL", strategy="Fibonacci",
                horizon="2w", direction="bullish", signal_date="2021-03-01", gate="plan_rejected",
                reason="risk_cap", margin=0.4, cf_status="filled", cf_r=-1.0, win=False,
                planned_loss_pct=2.4, expiry_bars=5)
    base.update(kw)
    return gate_row(**base)


def _plan(**kw) -> TradePlanV2:
    base = dict(plan_id="p1", ticker="AAPL", created_at="2024-01-04", source="confluence",
                strategy="Fibonacci", horizon_key="2w", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=102.0,
                tp1_fraction=0.5, tp2=105.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


def _bars(n_after=20):
    return make_ohlcv([WARM] * 3 + [TP1_BAR] + [FLAT] * (n_after - 1), start="2024-01-02")   # 01-04 = index 2


def _record(**kw):
    base = {"id": 1, "ticker": "AAPL", "gate": "rs", "strategy": "Fibonacci", "horizon": "2w",
            "signal_date": "2026-10-05", "cf_status": "filled", "reason": "rs_blocked", "margin": -3.0,
            "direction": "bearish", "source": "strategy", "plan": None, "cf_r": 0.8, "win": True,
            "created_at": dt.datetime(2026, 10, 5, 20, tzinfo=dt.timezone.utc), "resolved_at": None}
    base.update(kw)
    return base


# --- TRAIN -------------------------------------------------------------------

def test_train_rows_round_trip_from_every_file(tmp_path):
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_gate_rows([_train()], first)
    write_gate_rows([_train(gate="compression", reason="earnings_unknown", source="strategy",
                            margin=None, planned_loss_pct=None, in_sample=True)], second)
    with first.open("a", encoding="utf-8") as handle:
        handle.write("\n")                                   # a blank line is not a row
    rows = gci.load_train_rows([first, second])
    assert [r["gate"] for r in rows] == ["plan_rejected", "compression"]
    assert rows[0] == json.loads(json.dumps(_train()))


def test_a_train_rs_row_is_refused(tmp_path):
    path = tmp_path / "rs.jsonl"
    write_gate_rows([_train(gate="rs", reason="rs_blocked", source="strategy")], path)
    with pytest.raises(ValueError, match="live-only"):
        gci.load_train_rows([path])


def test_a_live_row_in_a_train_file_is_refused(tmp_path):
    path = tmp_path / "live.jsonl"
    write_gate_rows([_train(population="live")], path)
    with pytest.raises(ValueError, match="population"):
        gci.load_train_rows([path])


def test_a_missing_train_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        gci.load_train_rows([tmp_path / "nope.jsonl"])


def test_default_train_paths_cover_logs_and_the_vm_inputs_dir(monkeypatch, tmp_path):
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / "logs").mkdir(parents=True)
    (data / "reports" / "inputs").mkdir(parents=True)
    for path in (repo / "logs" / "v147-blocked-confluence.jsonl", repo / "logs" / "other.jsonl",
                 data / "reports" / "inputs" / "v147-blocked-compression.jsonl"):
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(gci, "REPO_ROOT", repo)
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    assert [p.name for p in gci.default_train_paths()] == ["v147-blocked-confluence.jsonl",
                                                           "v147-blocked-compression.jsonl"]


# --- live blocked --------------------------------------------------------------

def test_pending_records_never_become_rows():
    assert gci.live_blocked_rows([_record(cf_status="pending", cf_r=None, win=None)]) == []


def test_an_rs_record_maps_onto_the_shared_row_shape():
    (row,) = gci.live_blocked_rows([_record()])
    assert row == gate_row(population="live", arm="blocked", source="strategy", ticker="AAPL",
                           strategy="Fibonacci", horizon="2w", direction="bearish",
                           signal_date="2026-10-05", gate="rs", reason="rs_blocked", margin=-3.0,
                           cf_status="filled", cf_r=0.8, win=True)


def test_a_risk_cap_record_carries_planned_loss_and_dollar_risk_from_its_stored_plan():
    plan = {"trigger_price": 100.0, "stop_loss": 97.0, "expiry_bars": 4}
    (row,) = gci.live_blocked_rows([_record(gate="plan_rejected", reason="risk_cap", margin=1.0,
                                            source="short_lane", plan=plan, cf_r=-1.0, win=False)])
    assert row["planned_loss_pct"] == pytest.approx(3.0)
    assert row["dollar_risk"] == pytest.approx(-1.5)        # -1R at a 3% stop = 1.5 x the 2% cap
    assert row["expiry_bars"] == 4 and row["source"] == "short_lane"


def test_a_no_qualifying_target_record_is_a_no_plan_row():
    (row,) = gci.live_blocked_rows([_record(gate="plan_rejected", reason="no_qualifying_target",
                                            margin=None, cf_status="no-plan", cf_r=None, win=None)])
    assert (row["cf_status"], row["cf_r"], row["planned_loss_pct"], row["dollar_risk"]) == \
        ("no-plan", None, None, None)


# --- live taken -----------------------------------------------------------------

def test_a_taken_plan_is_walked_by_the_replays_exact_call_and_copied_per_gate():
    bars, plan = _bars(), _plan()
    rows = gci.live_taken_rows([plan], lambda ticker: bars, realised={"p1": 0.7})
    assert [r["gate"] for r in rows] == ["rs", "plan_rejected"]
    expected = simulate_exit(bars, 2, plan, scale_out=True)
    for row in rows:
        assert (row["arm"], row["population"], row["reason"]) == ("taken", "live", None)
        assert row["cf_status"] == "filled" and row["win"] is True
        assert row["cf_r"] == pytest.approx(expected.r_total)
        assert row["realised_r"] == 0.7 and row["signal_date"] == "2024-01-04"


def test_a_compression_plan_is_in_the_rs_and_compression_taken_arms():
    plan = _plan(source="strategy", strategy=COMPRESSION_SHORT, direction="bearish",
                 stop_loss=105.0, tp1=98.0, tp2=95.0)
    rows = gci.live_taken_rows([plan], lambda ticker: _bars())
    assert [r["gate"] for r in rows] == ["rs", "compression"]
    assert rows[0]["realised_r"] is None


@pytest.mark.parametrize("change", [{"origin": "next_session"}, {"ticker": "XAUUSD"}])
def test_outlook_plans_and_spot_metals_are_out(change):
    assert gci.live_taken_rows([_plan(**change)], lambda ticker: _bars()) == []


def test_a_walk_still_waiting_for_bars_is_skipped():
    assert gci.live_taken_rows([_plan()], lambda ticker: _bars(n_after=5)) == []


def test_missing_bars_are_a_no_data_row():
    rows = gci.live_taken_rows([_plan()], lambda ticker: None)
    assert {r["cf_status"] for r in rows} == {"no-data"}


def test_bars_are_loaded_once_per_ticker():
    calls = []

    def load(ticker):
        calls.append(ticker)
        return _bars()

    gci.live_taken_rows([_plan(plan_id="a"), _plan(plan_id="b")], load)
    assert calls == ["AAPL"]


def test_the_last_completed_session_bounds_the_walk():
    # the bar dated 2024-01-05 is the TP1 bar; a cut at 2024-01-04 leaves the walk pending
    assert gci.live_taken_rows([_plan()], lambda t: _bars(), last_session="2024-01-04") == []


def test_realised_r_comes_from_closed_trades_only():
    trades = [{"plan_id": "p1", "status": "closed", "entry": 100.0, "stop_loss": 95.0,
               "direction": "bullish", "exit_price": 105.0, "legs": []},
              {"plan_id": "p2", "status": "open", "entry": 100.0, "stop_loss": 95.0,
               "direction": "bullish", "exit_price": None, "legs": []},
              {"plan_id": None, "status": "closed", "entry": 100.0, "stop_loss": 95.0,
               "direction": "bullish", "exit_price": 90.0, "legs": []}]
    assert gci.realised_r_by_plan(trades) == {"p1": pytest.approx(1.0)}


@pytest.mark.parametrize("moment, expected", [
    (dt.datetime(2024, 1, 10, 15, 0), "2024-01-09"),     # Wednesday, session still open
    (dt.datetime(2024, 1, 10, 16, 30), "2024-01-10"),    # after the close
    (dt.datetime(2024, 1, 13, 12, 0), "2024-01-12"),     # Saturday
    (dt.datetime(2024, 1, 16, 10, 0), "2024-01-12"),     # Tuesday after the MLK holiday
])
def test_last_completed_session(moment, expected):
    assert gci.last_completed_session(moment.replace(tzinfo=US_MARKET_TZ)) == expected


def test_load_live_reads_the_table_and_the_plans_since_the_window(monkeypatch):
    from swingbot.core.db.repositories import gate_rejections
    from swingbot.core.marketdata import data_store
    from swingbot.core.planning import plan_store

    seen = {}

    class _Repo:
        def list_since(self, since=None, *, conn=None):
            seen["since"] = since
            return [_record()]

    class _Store:
        def all(self):
            return [_plan(plan_id="old", created_at="2026-09-30"), _plan(plan_id="new", created_at="2026-10-02")]

    def _load(ticker, interval):
        seen.setdefault("loads", []).append((ticker, interval))
        return None

    monkeypatch.setattr(gate_rejections, "gate_rejections_repo", lambda: _Repo())
    monkeypatch.setattr(plan_store, "PlanStore", _Store)
    monkeypatch.setattr(data_store, "load_normalized", _load)
    monkeypatch.setattr(gci, "realised_r_by_plan", lambda trades=None: {})
    blocked, taken = gci.load_live(now=dt.datetime(2026, 10, 9, 22, 0, tzinfo=dt.timezone.utc))
    assert seen["since"] == "2026-10-01" and seen["loads"] == [("AAPL", "daily")]
    assert len(blocked) == 1 and {r["signal_date"] for r in taken} == {"2026-10-02"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_gate_counterfactual_inputs.py`
Expected: FAIL — `ImportError: cannot import name 'gate_counterfactual_inputs'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/analytics/gate_counterfactual_inputs.py`:

```python
"""v147: the gate-counterfactual report's inputs.

TRAIN rows come from the `--record-blocked` JSONL files (V147-5/-6). Live
blocked rows come from the `gate_rejections` table once resolved (V147-11).
Live taken rows are the issued plans re-walked through `simulate_blocked` --
the same `simulate_exit(..., scale_out=True)` call the blocked arm uses -- on
the live `market_data/` cache, so both arms are read by one instrument. The
realised R of the closed trade rides along as context and is never compared.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path

from swingbot import config
from swingbot.core.analytics.metrics import r_multiple
from swingbot.core.backtesting.blocked_recorder import gate_row
from swingbot.core.backtesting.gate_counterfactual import BlockedCandidate, simulate_blocked
from swingbot.core.market import session
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.marketdata.spot_metals import SPOT_PAIRS
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.risk_limits import planned_loss_pct

log = logging.getLogger(__name__)

LIVE_SINCE = "2026-10-01"
TRAIN_GLOB = "v147-blocked-*.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[3]
OUTLOOK_ORIGIN = "next_session"


# --- TRAIN -------------------------------------------------------------------

def default_train_paths() -> list[Path]:
    """Every TRAIN gate-row file present: the repo's logs/ and, on the VM, <DATA_DIR>/reports/inputs/."""
    folders = (REPO_ROOT / "logs", Path(config.DATA_DIR) / "reports" / "inputs")
    return [path for folder in folders if folder.is_dir() for path in sorted(folder.glob(TRAIN_GLOB))]


def _check_train(row: dict, path) -> dict:
    if row.get("population") != "train":
        raise ValueError(f"{path}: row population {row.get('population')!r} is not 'train'")
    if row.get("gate") == "rs":
        raise ValueError(f"{path}: a TRAIN rs row -- the RS gate is live-only (v34 closed)")
    return row


def load_train_rows(paths) -> list[dict]:
    """Every row of every TRAIN JSONL file, in file order (a missing file raises)."""
    rows = []
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            rows.extend(_check_train(json.loads(line), path) for line in handle if line.strip())
    return rows


# --- live blocked ----------------------------------------------------------------

def _finite(value) -> float | None:
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _plan_fields(record: dict) -> dict:
    plan = record.get("plan") if isinstance(record.get("plan"), dict) else {}
    loss = None
    if record.get("reason") == "risk_cap" and plan:
        loss = _finite(planned_loss_pct(plan.get("trigger_price"), plan.get("stop_loss")))
    return {"planned_loss_pct": loss, "expiry_bars": plan.get("expiry_bars", record.get("expiry_bars"))}


def live_blocked_rows(records) -> list[dict]:
    """Resolved `gate_rejections` records as shared gate rows; `pending` records are skipped."""
    rows = []
    for record in records:
        if record.get("cf_status") == "pending":
            continue
        rows.append(gate_row(
            population="live", arm="blocked", source=record["source"], ticker=record["ticker"],
            strategy=record["strategy"], horizon=record["horizon"], direction=record["direction"],
            signal_date=record["signal_date"], gate=record["gate"], reason=record.get("reason"),
            margin=record.get("margin"), cf_status=record["cf_status"], cf_r=record.get("cf_r"),
            win=record.get("win"), in_sample=False, **_plan_fields(record)))
    return rows


# --- live taken --------------------------------------------------------------------

def _in_scope(plan) -> bool:
    return getattr(plan, "origin", None) != OUTLOOK_ORIGIN and plan.ticker not in SPOT_PAIRS


def _taken_gates(plan) -> tuple:
    """The gates this issued plan passed and could have been blocked by."""
    gates = ["rs"]
    if plan.source != "strategy":
        gates.append("plan_rejected")
    if plan.strategy == COMPRESSION_SHORT:
        gates.append("compression")
    return tuple(gates)


def _walk(plan, bars, last_session):
    candidate = BlockedCandidate(
        ticker=plan.ticker, gate="taken", reason=None, source=plan.source, strategy=plan.strategy,
        horizon=plan.horizon_key, direction=plan.direction, signal_date=str(plan.created_at)[:10],
        plan=plan_to_dict(plan))
    return simulate_blocked(candidate, bars, last_session=last_session)


def _taken_row(plan, result, gate: str, realised_r) -> dict:
    row = gate_row(
        population="live", arm="taken", source=plan.source, ticker=plan.ticker, strategy=plan.strategy,
        horizon=plan.horizon_key, direction=plan.direction, signal_date=str(plan.created_at)[:10],
        gate=gate, reason=None, margin=None, cf_status=result.cf_status, cf_r=result.cf_r,
        win=result.win, expiry_bars=plan.expiry_bars, in_sample=False)
    row["realised_r"] = realised_r
    return row


def _memo(load_bars):
    cache = {}

    def bars_of(ticker):
        if ticker not in cache:
            cache[ticker] = load_bars(ticker)
        return cache[ticker]
    return bars_of


def live_taken_rows(plans, load_bars, *, last_session: str | None = None,
                    realised: dict | None = None) -> list[dict]:
    """Issued plans re-walked from the stored plan; one row per gate the plan passed."""
    realised = realised or {}
    bars_of = _memo(load_bars)
    rows = []
    for plan in plans:
        if not _in_scope(plan):
            continue
        result = _walk(plan, bars_of(plan.ticker), last_session)
        if result.cf_status == "pending":
            continue
        rows.extend(_taken_row(plan, result, gate, realised.get(plan.plan_id)) for gate in _taken_gates(plan))
    return rows


def realised_r_by_plan(trades=None) -> dict[str, float]:
    """plan_id -> realised R of its closed paper trade (context beside the re-walk, never compared)."""
    if trades is None:
        from swingbot.core.tracking.performance import TradeLog
        trades = TradeLog().get_trades(status="all", limit=None)
    out = {}
    for trade in trades:
        r = r_multiple(trade) if trade.get("plan_id") and trade.get("status") != "open" else None
        if r is not None:
            out[trade["plan_id"]] = float(r)
    return out


def last_completed_session(now=None) -> str:
    """ISO date of the last NYSE session whose regular close has passed."""
    moment = session.now_et(now)
    today, calendar = moment.date(), session.nyse_calendar()
    closed_today = calendar.is_session(today) and moment.time() >= session.session_close(today)
    cutoff = today if closed_today else today - dt.timedelta(days=1)
    return calendar.sessions(cutoff - dt.timedelta(days=14), cutoff)[-1].isoformat()


def load_live(*, since: str = LIVE_SINCE, now=None) -> tuple[list[dict], list[dict]]:
    """(live blocked rows, live taken rows) for the live window starting `since`."""
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    from swingbot.core.marketdata import data_store
    from swingbot.core.planning.plan_store import PlanStore
    blocked = live_blocked_rows(gate_rejections_repo().list_since(since))
    plans = [plan for plan in PlanStore().all() if str(plan.created_at)[:10] >= since]
    taken = live_taken_rows(plans, lambda ticker: data_store.load_normalized(ticker, "daily"),
                            last_session=last_completed_session(now), realised=realised_r_by_plan())
    log.info("gate counterfactual live inputs: %d blocked rows, %d taken rows", len(blocked), len(taken))
    return blocked, taken
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/analytics/test_gate_counterfactual_inputs.py`
Expected: PASS, `0 failed`. If `test_a_taken_plan_is_walked_by_the_replays_exact_call_and_copied_per_gate` reports a `pending` skip, the 2w hold (14 bars) outgrew `_bars()`: raise `n_after`, never shorten the walk.

- [ ] **Step 5: Complexity and syntax**

Run: `python -m radon cc -s -n C swingbot/core/analytics/gate_counterfactual_inputs.py && python -m py_compile swingbot/core/analytics/gate_counterfactual_inputs.py`
Expected: no radon output, no error.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/gate_counterfactual_inputs.py tests/analytics/test_gate_counterfactual_inputs.py
git commit -m "feat(v147): gate-counterfactual report inputs -- TRAIN JSONL, live table, taken re-walk (V147-14)"
```
