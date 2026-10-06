# v134 FVG context diagnostic, Part 2: script core, the two blocked tags, Table A collector (V134-6 .. V134-9)

> Header, "Dependencies: what is blocked on what", Global Constraints, the frozen readings (F1–F15), the spec gaps (G1–G3), the file map and `## Parallelisation` live in `2026-10-06-v134-fvg-context-diagnostic_0-index.md`. Every task here implicitly includes them. Work in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v134-fvg-context-diagnostic`; all paths below are relative to it.

# Phase 2 — The script, dependency-free core

### Task V134-6: Window guard, bucket arithmetic and the pre-registered verdict

**Files:**
- Create: `scripts/backtest/measure_fvg_context_diagnostic.py`
- Create: `tests/scripts/test_measure_fvg_context_diagnostic.py`

**Interfaces:**
- Consumes: `arms.windows.VALIDATION_START` (`"2024-01-01"`). Nothing from `fvg_context.py`: every function here takes plain row dicts.
- Produces (`measure_fvg_context_diagnostic`, importable with `scripts/backtest` on `sys.path`):
  - Constants `TRAIN_START`, `TRAIN_END`, `HOLDOUT_START`, `HALVES`, `MIN_N = 100`, `MIN_HALF_N = 50`, `THIN_N = 30`, `DIRECTIONS`, `SCORED`, `TAG_BUCKETS`, `CLAIMS`, `CENSUS_KEYS`, `EARNS = "earns a follow-on spec"`, `NO_LIFT = "no-lift"`, `LOG_DIR`.
  - `window_refusal(start, end) -> str | None`. Tokens: `refused:window-malformed`, `refused:window-touches-holdout`, `refused:window-outside-train`.
  - `train_frame(df, end=TRAIN_END) -> DataFrame`: `df` with every bar after `end` removed; raises `ValueError("holdout bar ...")` if a bar on or after 2024-01-01 would survive.
  - `bucket_stats(rows) -> dict` with keys `n, wins, losses, failed, hold_rate, mean_r, failed_share`.
  - `quintile_edges(values) -> list[float] | None`, `size_bucket(size_atr, edges) -> "q1".."q5" | None`, `with_size(rows, edges: dict) -> list[dict]` (adds the `"size"` key from per-direction edges).
  - `table_a(rows) -> {tag: {direction: {bucket: bucket_stats}}}`.
  - `claim_verdict(rows, claim) -> dict` with keys `claim, verdict, clauses, bullish, bearish, halves`; `verdicts(rows) -> {claim: claim_verdict}`.
- **Gap row contract** (what V134-9 will produce and every function here reads): `{"ticker", "direction": "bullish" | "bearish", "formed": "YYYY-MM-DD", "outcome": "win" | "loss" | "timeout" | "failed_on_touch", "r": float | None, "displacement", "structure", "confluence", "approach", "origin", "size_atr", "touch_close"}`.

**Blocked on:** nothing. Its tests build rows by hand. Frozen readings F6–F10 apply.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/test_measure_fvg_context_diagnostic.py
"""v134 diagnostic script: window guard, bucket arithmetic, verdict, collectors and report."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_fvg_context_diagnostic as mfc  # noqa: E402

TAG_DEFAULTS = {"displacement": "no", "structure": "none", "confluence": "0", "approach": "short",
                "origin": "intrabar", "size_atr": 0.25, "touch_close": "above"}


def _rows(count, outcome, r=None, *, direction="bullish", formed="2020-06-01", **tags):
    if r is None:
        r = {"win": 1.5, "loss": -1.0}.get(outcome)
    return [{**TAG_DEFAULTS, **tags, "direction": direction, "formed": formed, "outcome": outcome, "r": r}
            for _ in range(count)]


def _side(claim, bucket, wins, losses, failed=0, **kwargs):
    return (_rows(wins, "win", **{claim: bucket}, **kwargs) + _rows(losses, "loss", **{claim: bucket}, **kwargs)
            + _rows(failed, "failed_on_touch", **{claim: bucket}, **kwargs))


def _both_halves(claim, bucket, wins, losses, failed=0, **kwargs):
    return (_side(claim, bucket, wins, losses, failed, formed="2020-06-01", **kwargs)
            + _side(claim, bucket, wins, losses, failed, formed="2022-06-01", **kwargs))


def _earning(claim="displacement", fav="yes", against="no"):
    """Bullish: favourable 40W/20L/2 failed per half, against 25W/35L/5 failed per half. No bearish gaps."""
    return _both_halves(claim, fav, 40, 20, 2) + _both_halves(claim, against, 25, 35, 5)


# --- window guard -----------------------------------------------------------------

@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2025-12-31"),
                                       ("2024-01-01", "2024-06-30"), ("2023-06-01", "2024-01-02")])
def test_a_window_touching_2024_is_refused(start, end):
    assert mfc.window_refusal(start, end).startswith("refused:window-touches-holdout")


@pytest.mark.parametrize("start,end", [("2019-12-31", "2023-12-31"), ("2023-01-01", "2022-01-01")])
def test_a_window_outside_train_is_refused(start, end):
    assert mfc.window_refusal(start, end).startswith("refused:window-outside-train")


def test_a_malformed_window_is_refused():
    assert mfc.window_refusal("2020-13-01", "soon").startswith("refused:window-malformed")


@pytest.mark.parametrize("start,end", [("2020-01-01", "2023-12-31"), ("2021-01-01", "2022-12-31")])
def test_train_and_any_window_inside_it_are_allowed(start, end):
    assert mfc.window_refusal(start, end) is None


def test_train_frame_drops_every_bar_after_the_end():
    frame = pd.DataFrame({"Close": 1.0}, index=pd.bdate_range("2023-12-20", "2024-01-10"))
    cut = mfc.train_frame(frame)
    assert str(cut.index[-1].date()) == "2023-12-29" and len(cut) == 8


def test_train_frame_raises_rather_than_return_a_holdout_bar():
    frame = pd.DataFrame({"Close": 1.0}, index=pd.bdate_range("2023-12-20", "2024-01-10"))
    with pytest.raises(ValueError, match="holdout bar"):
        mfc.train_frame(frame, "2024-06-30")


# --- bucket arithmetic ------------------------------------------------------------

def test_bucket_stats_counts_hold_rate_mean_r_and_failed_share():
    rows = _rows(6, "win") + _rows(2, "loss") + _rows(2, "timeout", 0.5) + _rows(5, "failed_on_touch")
    stats = mfc.bucket_stats(rows)
    assert (stats["n"], stats["wins"], stats["losses"], stats["failed"]) == (10, 6, 2, 5)
    assert stats["hold_rate"] == pytest.approx(0.75)                  # 6 / (6 + 2): timeouts are not decided
    assert stats["mean_r"] == pytest.approx((6 * 1.5 - 2 + 2 * 0.5) / 10)
    assert stats["failed_share"] == pytest.approx(5 / 15)


def test_bucket_stats_of_nothing_is_all_none():
    stats = mfc.bucket_stats([])
    assert (stats["n"], stats["hold_rate"], stats["mean_r"], stats["failed_share"]) == (0, None, None, None)


def test_size_quintiles_from_edges():
    edges = mfc.quintile_edges([float(v) for v in range(1, 101)])
    assert edges == pytest.approx([20.8, 40.6, 60.4, 80.2])
    assert [mfc.size_bucket(v, edges) for v in (1.0, 20.8, 50.0, 80.2, 99.0)] == ["q1", "q2", "q3", "q5", "q5"]
    assert mfc.size_bucket(None, edges) is None and mfc.size_bucket(1.0, None) is None
    assert mfc.quintile_edges([1.0, 2.0, 3.0, None]) is None


def test_with_size_uses_the_edges_of_the_gaps_own_direction():
    rows = _rows(1, "win", size_atr=0.5) + _rows(1, "win", size_atr=0.5, direction="bearish")
    sized = mfc.with_size(rows, {"bullish": [0.1, 0.2, 0.3, 0.4], "bearish": [0.6, 0.7, 0.8, 0.9]})
    assert [row["size"] for row in sized] == ["q5", "q1"]


def test_table_a_is_tag_by_direction_by_bucket():
    rows = mfc.with_size(_rows(3, "win", approach="slowing") + _rows(1, "loss", approach="slowing", direction="bearish"),
                         {"bullish": None, "bearish": None})
    table = mfc.table_a(rows)
    assert set(table) == set(mfc.TAG_BUCKETS)
    assert table["approach"]["bullish"]["slowing"]["n"] == 3
    assert table["approach"]["bearish"]["slowing"]["losses"] == 1
    assert table["approach"]["bullish"]["not_slowing"]["n"] == 0


# --- pre-registered verdict -------------------------------------------------------

def test_a_claim_that_clears_all_six_clauses_earns_a_follow_on_spec():
    result = mfc.claim_verdict(_earning(), "displacement")
    assert result["verdict"] == mfc.EARNS and all(result["clauses"].values())
    assert (result["bullish"]["favourable"]["n"], result["bullish"]["against"]["n"]) == (120, 120)


def test_clause_1_needs_a_strictly_higher_hold_rate():
    rows = _both_halves("displacement", "yes", 30, 30) + _both_halves("displacement", "no", 30, 30)
    result = mfc.claim_verdict(rows, "displacement")
    assert result["clauses"]["1_hold_rate_higher"] is False and result["verdict"] == mfc.NO_LIFT


def test_clause_2_fails_when_timeouts_drag_the_favourable_mean_r_lower():
    rows = _earning() + _rows(60, "timeout", -0.9, displacement="yes", formed="2020-06-01") \
        + _rows(60, "timeout", -0.9, displacement="yes", formed="2022-06-01")
    result = mfc.claim_verdict(rows, "displacement")
    assert result["clauses"]["1_hold_rate_higher"] is True
    assert result["clauses"]["2_mean_r_no_lower"] is False and result["verdict"] == mfc.NO_LIFT


def test_clause_3_fails_when_the_favourable_bucket_fails_on_touch_more_often():
    rows = _both_halves("displacement", "yes", 40, 20, 30) + _both_halves("displacement", "no", 25, 35, 5)
    result = mfc.claim_verdict(rows, "displacement")
    assert result["clauses"]["3_failed_share_no_higher"] is False and result["verdict"] == mfc.NO_LIFT


def test_clause_4_needs_100_scored_gaps_on_both_sides():
    rows = _both_halves("displacement", "yes", 30, 15) + _both_halves("displacement", "no", 25, 35)
    result = mfc.claim_verdict(rows, "displacement")
    assert result["clauses"]["4_n_at_least_100"] is False and result["verdict"] == mfc.NO_LIFT


def test_clause_5_fails_when_one_half_reverses():
    rows = (_side("displacement", "yes", 55, 5, formed="2020-06-01") + _side("displacement", "no", 25, 35, formed="2020-06-01")
            + _side("displacement", "yes", 25, 35, formed="2022-06-01") + _side("displacement", "no", 30, 30, formed="2022-06-01"))
    result = mfc.claim_verdict(rows, "displacement")
    assert result["clauses"]["1_hold_rate_higher"] is True            # pooled 80/120 against 55/120
    assert result["halves"]["2020-21"]["ok"] is True and result["halves"]["2022-23"]["ok"] is False
    assert result["clauses"]["5_both_halves"] is False and result["verdict"] == mfc.NO_LIFT


def test_clause_5_needs_50_per_side_in_each_half():
    rows = (_side("displacement", "yes", 60, 30, formed="2020-06-01") + _side("displacement", "no", 50, 70, formed="2020-06-01")
            + _side("displacement", "yes", 20, 10, formed="2022-06-01") + _side("displacement", "no", 25, 35, formed="2022-06-01"))
    result = mfc.claim_verdict(rows, "displacement")
    assert result["clauses"]["4_n_at_least_100"] is True and result["clauses"]["5_both_halves"] is False


def test_the_halves_split_on_the_formation_date():
    result = mfc.claim_verdict(_earning(), "displacement")
    assert {label: half["favourable"]["n"] for label, half in result["halves"].items()} == {"2020-21": 60, "2022-23": 60}


def test_clause_6_fails_on_a_reversed_sign_in_bearish_gaps_with_enough_n():
    bearish = _side("displacement", "yes", 40, 80, direction="bearish") + _side("displacement", "no", 70, 50, direction="bearish")
    result = mfc.claim_verdict(_earning() + bearish, "displacement")
    assert result["clauses"]["6_bearish_same_sign_or_thin"] is False and result["verdict"] == mfc.NO_LIFT


def test_clause_6_passes_on_the_same_sign_or_a_thin_bearish_side():
    same = _side("displacement", "yes", 80, 40, direction="bearish") + _side("displacement", "no", 50, 70, direction="bearish")
    thin = _side("displacement", "yes", 10, 80, direction="bearish") + _side("displacement", "no", 70, 50, direction="bearish")
    assert mfc.claim_verdict(_earning() + same, "displacement")["verdict"] == mfc.EARNS
    assert mfc.claim_verdict(_earning() + thin, "displacement")["verdict"] == mfc.EARNS


def test_structure_pools_bos_and_choch_against_none():
    rows = (_both_halves("structure", "bos", 20, 10, 1) + _both_halves("structure", "choch", 20, 10, 1)
            + _both_halves("structure", "none", 25, 35, 5))
    result = mfc.claim_verdict(rows, "structure")
    assert result["bullish"]["favourable"]["n"] == 120 and result["verdict"] == mfc.EARNS


def test_confluence_pools_0_and_1_2_as_the_against_side():
    rows = (_both_halves("confluence", "3+", 40, 20, 2) + _both_halves("confluence", "0", 12, 18, 2)
            + _both_halves("confluence", "1-2", 13, 17, 3))
    result = mfc.claim_verdict(rows, "confluence")
    assert result["bullish"]["against"]["n"] == 120 and result["verdict"] == mfc.EARNS


def test_approach_leaves_the_short_bucket_out_of_both_sides():
    rows = _earning("approach", "slowing", "not_slowing") + _both_halves("approach", "short", 0, 200)
    result = mfc.claim_verdict(rows, "approach")
    assert result["bullish"]["against"]["n"] == 120 and result["verdict"] == mfc.EARNS


def test_verdicts_cover_exactly_the_four_declared_claims():
    assert list(mfc.verdicts(_earning())) == ["displacement", "structure", "confluence", "approach"]
    assert mfc.verdicts(_earning())["structure"]["verdict"] == mfc.NO_LIFT   # no favourable rows at all
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'measure_fvg_context_diagnostic'`.

- [ ] **Step 3: Implement**

Create `scripts/backtest/measure_fvg_context_diagnostic.py`:

```python
#!/usr/bin/env python3
"""v134 FVG context diagnostic: do structure, confluence, approach and displacement separate gap outcomes?

TRAIN only (2020-01-01..2023-12-31), read-only, gates nothing. Table A scores
every gap at its first touch (primary, carries the pre-registered verdict).
Table B slices baseline FVG-tagged confluence plans by the same tags
(secondary, confounded, no verdict). Gap statistics are not the bot's ExpR.

Spec: docs/superpowers/specs/2026-10-06-v134-fvg-context-diagnostic-design.md

Run: python scripts/backtest/measure_fvg_context_diagnostic.py \
       --preregistration docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md \
       --out-md docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md
"""
from __future__ import annotations

import sys
from bisect import bisect_right
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting.arms import windows  # noqa: E402

TRAIN_START, TRAIN_END = "2020-01-01", "2023-12-31"
HOLDOUT_START = windows.VALIDATION_START                  # 2024-01-01: v128's unspent VALIDATION window
HALVES = (("2020-21", "2020-01-01", "2021-12-31"), ("2022-23", "2022-01-01", "2023-12-31"))
MIN_N, MIN_HALF_N, THIN_N = 100, 50, 30
DIRECTIONS = ("bullish", "bearish")
SCORED = ("win", "loss", "timeout")
QUINTILES = (0.2, 0.4, 0.6, 0.8)
TAG_BUCKETS = {"displacement": ("yes", "no"), "structure": ("bos", "choch", "none"),
               "confluence": ("0", "1-2", "3+"), "approach": ("slowing", "not_slowing", "short"),
               "origin": ("intrabar", "partial", "true_gap"), "size": ("q1", "q2", "q3", "q4", "q5"),
               "touch_close": ("above", "inside", "below")}
#: claim -> (favourable buckets, against buckets). Fixed by the spec before any run.
CLAIMS = {"displacement": (("yes",), ("no",)), "structure": (("bos", "choch"), ("none",)),
          "confluence": (("3+",), ("0", "1-2")), "approach": (("slowing",), ("not_slowing",))}
CENSUS_KEYS = ("formed", "touched", "gapped_through", "untouched", "censored", "no_atr")
EARNS, NO_LIFT = "earns a follow-on spec", "no-lift"
LOG_DIR = ROOT / "logs"


# --- window guard -----------------------------------------------------------------

def window_refusal(start: str, end: str) -> str | None:
    """None, or why the window may not be measured. Anything touching 2024-01-01+ is refused."""
    try:
        date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return f"refused:window-malformed -- {start}..{end} is not a pair of ISO dates"
    if end >= HOLDOUT_START or start >= HOLDOUT_START:
        return f"refused:window-touches-holdout -- {start}..{end} reaches {HOLDOUT_START} or later"
    if start < TRAIN_START or start > end:
        return f"refused:window-outside-train -- {start}..{end} is not inside {TRAIN_START}..{TRAIN_END}"
    return None


def train_frame(df, end: str = TRAIN_END):
    """``df`` with every bar after ``end`` removed. Raises if a holdout bar survives."""
    out = df.loc[:end]
    if len(out) and str(out.index[-1].date()) >= HOLDOUT_START:
        raise ValueError(f"holdout bar {out.index[-1].date()} in a v134 frame")
    return out


# --- bucket arithmetic (Table A) --------------------------------------------------

def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def bucket_stats(rows) -> dict:
    """N (scored gaps), hold rate, mean R and failed-on-touch share for one bucket of gap rows."""
    count = Counter(row["outcome"] for row in rows)
    wins, losses, failed = count["win"], count["loss"], count["failed_on_touch"]
    scored = [row["r"] for row in rows if row["outcome"] in SCORED]
    return {"n": len(scored), "wins": wins, "losses": losses, "failed": failed,
            "hold_rate": _ratio(wins, wins + losses),
            "mean_r": float(np.mean(scored)) if scored else None,
            "failed_share": _ratio(failed, len(scored) + failed)}


def quintile_edges(values) -> list | None:
    values = [float(value) for value in values if value is not None]
    if len(values) < len(QUINTILES) + 1:
        return None
    return [round(float(edge), 6) for edge in np.quantile(values, QUINTILES)]


def size_bucket(size_atr, edges) -> str | None:
    if size_atr is None or edges is None:
        return None
    return f"q{bisect_right(edges, size_atr) + 1}"


def with_size(rows, edges: dict) -> list:
    """Rows with their ``size`` quintile, from per-direction edges."""
    return [{**row, "size": size_bucket(row["size_atr"], edges.get(row["direction"]))} for row in rows]


def table_a(rows) -> dict:
    """{tag: {direction: {bucket: bucket_stats}}} over touched-gap rows."""
    return {tag: {direction: {bucket: bucket_stats([row for row in rows if row["direction"] == direction
                                                    and row[tag] == bucket])
                              for bucket in buckets}
                  for direction in DIRECTIONS}
            for tag, buckets in TAG_BUCKETS.items()}


# --- pre-registered verdict -------------------------------------------------------

def _sides(rows, claim: str) -> tuple:
    favourable, against = CLAIMS[claim]
    return ([row for row in rows if row[claim] in favourable], [row for row in rows if row[claim] in against])


def _hold_gap(fav: dict, against: dict) -> float | None:
    if fav["hold_rate"] is None or against["hold_rate"] is None:
        return None
    return fav["hold_rate"] - against["hold_rate"]


def _mean_r_no_lower(fav: dict, against: dict) -> bool:
    return fav["mean_r"] is not None and against["mean_r"] is not None and fav["mean_r"] >= against["mean_r"]


def _failed_no_higher(fav: dict, against: dict) -> bool:
    return (fav["failed_share"] is not None and against["failed_share"] is not None
            and fav["failed_share"] <= against["failed_share"])


def _half(rows, claim: str, start: str, end: str) -> dict:
    fav, against = (bucket_stats(side) for side in
                    _sides([row for row in rows if start <= row["formed"] <= end], claim))
    gap = _hold_gap(fav, against)
    return {"favourable": fav, "against": against,
            "ok": (gap is not None and gap > 0 and _mean_r_no_lower(fav, against)
                   and min(fav["n"], against["n"]) >= MIN_HALF_N)}


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _bearish_ok(bull_gap, bear_fav: dict, bear_against: dict) -> bool:
    """Clause 6: same sign of the hold-rate gap on bearish gaps, or a bearish side under MIN_N."""
    if min(bear_fav["n"], bear_against["n"]) < MIN_N:
        return True
    bear_gap = _hold_gap(bear_fav, bear_against)
    return bull_gap is not None and bear_gap is not None and _sign(bull_gap) == _sign(bear_gap)


def _clauses(fav: dict, against: dict, halves: dict, bear_fav: dict, bear_against: dict) -> dict:
    gap = _hold_gap(fav, against)
    return {"1_hold_rate_higher": gap is not None and gap > 0,
            "2_mean_r_no_lower": _mean_r_no_lower(fav, against),
            "3_failed_share_no_higher": _failed_no_higher(fav, against),
            "4_n_at_least_100": min(fav["n"], against["n"]) >= MIN_N,
            "5_both_halves": all(half["ok"] for half in halves.values()),
            "6_bearish_same_sign_or_thin": _bearish_ok(gap, bear_fav, bear_against)}


def claim_verdict(rows, claim: str) -> dict:
    """The six frozen clauses for one claim. Bullish gaps decide; bearish gaps are clause 6 only."""
    bull = [row for row in rows if row["direction"] == "bullish"]
    bear = [row for row in rows if row["direction"] == "bearish"]
    fav, against = (bucket_stats(side) for side in _sides(bull, claim))
    bear_fav, bear_against = (bucket_stats(side) for side in _sides(bear, claim))
    halves = {label: _half(bull, claim, start, end) for label, start, end in HALVES}
    clauses = _clauses(fav, against, halves, bear_fav, bear_against)
    return {"claim": claim, "verdict": EARNS if all(clauses.values()) else NO_LIFT, "clauses": clauses,
            "bullish": {"favourable": fav, "against": against},
            "bearish": {"favourable": bear_fav, "against": bear_against}, "halves": halves}


def verdicts(rows) -> dict:
    return {claim: claim_verdict(rows, claim) for claim in CLAIMS}
```

- [ ] **Step 4: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: PASS, `0 failed`.
Run: `python -m radon cc -s -n C scripts/backtest/measure_fvg_context_diagnostic.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_fvg_context_diagnostic.py tests/scripts/test_measure_fvg_context_diagnostic.py
git commit -m "feat(v134): diagnostic script core -- window guard, bucket stats, six-clause verdict"
```

- [ ] **Step 6: Gate check before Phase 3**

Re-run V134-1 Step 2. If the state is not `ALL PRESENT`, **stop here**: report that V134-2 .. V134-6 are done and which dependency Phase 3 is waiting on. If v128 or v130 landed on `main` after the branch was created, merge `main` into the branch first (`worktree-lifecycle` skill), then run the five test files from V134-2 .. V134-6 once each to confirm the merge changed nothing.

# Phase 3 — The two blocked tags and the Table A collector

### Task V134-7: Displacement tag

**Files:**
- Modify: `swingbot/core/market/fvg_context.py`
- Test: `tests/market/test_fvg_context_displacement.py`

**Interfaces:**
- Consumes (v128, V128-1): `fvg.is_displacement_gap(df, gap: dict, k: float, atr_series=None) -> bool`. It reads the middle candle `m = bar_index − 1` and `indicators.atr(df.iloc[:m + 1], 14)`, so it is causal by construction. Test frames from v128's `tests/market/fvg_frames.py`: `STRONG_BULL`, `WEAK_BULL`, `MID_CLOSE_BULL`, `STRONG_BEAR`, `BULL_THIRD`, `BEAR_THIRD`, `gap_frame(middle, third, flat_bars=20)`.
- Produces: `formation_tags` gains `"displacement"` (`"yes" | "no"`), at the frozen `DISPLACEMENT_K = 1.5`.

**Blocked on: v128 (V128-1).** Do not start unless V134-1 Step 2 prints `v128 code: PRESENT`.

Do not call v128's `witness_frame`: as planned it passes a `zip` to `bar_frame` and raises `TypeError` (index, "Also found while verifying"). The random walk below is built with v134's own `bar_frame`.

- [ ] **Step 1: Invoke the `no-lookahead` skill.**

- [ ] **Step 2: Write the failing tests**

```python
# tests/market/test_fvg_context_displacement.py
"""v134: the displacement tag is v128's predicate at the frozen k = 1.5, read at formation."""
import numpy as np
import pytest

from swingbot.core.market import fvg
from swingbot.core.market import fvg_context as fc
from tests.market.fvg_context_frames import bar_frame, extend
from tests.market.fvg_frames import (BEAR_THIRD, BULL_THIRD, MID_CLOSE_BULL, STRONG_BEAR, STRONG_BULL, WEAK_BULL,
                                     gap_frame)

BETWEEN = (100.0, 102.6, 99.9, 102.5)      # body 2.5 against ATR14 2.05: displacement at k = 1.0, not at 1.5


def _walk(n=400, seed=134):
    """A seeded random walk with ~6% jump days, so it carries gaps of both kinds."""
    rng = np.random.default_rng(seed)
    jumps = np.where(rng.random(n) < 0.06, rng.choice([-0.04, 0.04], n), 0.0)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.012, n) + jumps))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0.0, 0.006, n)) * close
    return bar_frame(zip(open_, np.maximum(open_, close) + spread, np.minimum(open_, close) - spread, close))


def _tag(middle, third):
    frame = gap_frame(middle, third)
    (gap,) = fc.all_gaps(frame)
    return fc.formation_tags(frame, gap)["displacement"]


@pytest.mark.parametrize("middle,third,expected", [(STRONG_BULL, BULL_THIRD, "yes"), (WEAK_BULL, BULL_THIRD, "no"),
                                                   (MID_CLOSE_BULL, BULL_THIRD, "no"), (STRONG_BEAR, BEAR_THIRD, "yes")])
def test_displacement_follows_the_middle_candle(middle, third, expected):
    assert _tag(middle, third) == expected


def test_k_is_frozen_at_1_5():
    frame = gap_frame(BETWEEN, BULL_THIRD)
    (gap,) = fc.all_gaps(frame)
    assert fvg.is_displacement_gap(frame, gap, 1.0) is True
    assert fc.DISPLACEMENT_K == 1.5 and fc.formation_tags(frame, gap)["displacement"] == "no"


def test_the_tag_is_v128s_predicate_on_every_gap_of_a_random_walk():
    frame = _walk()
    gaps = fc.all_gaps(frame)
    tags = [fc.formation_tags(frame, gap)["displacement"] for gap in gaps]
    assert tags == ["yes" if fvg.is_displacement_gap(frame, gap, 1.5) else "no" for gap in gaps]
    assert {"yes", "no"} <= set(tags), "the walk must carry both kinds or this test proves nothing"


def test_appending_bars_never_changes_the_displacement_tag():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    (gap,) = fc.all_gaps(frame)
    violent = [(104.5, 130.0, 102.0, 128.0), (128.0, 129.0, 60.0, 61.0)] * 5
    assert fc.formation_tags(extend(frame, violent), gap) == fc.formation_tags(frame, gap)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_displacement.py`
Expected: FAIL with `KeyError: 'displacement'`.

- [ ] **Step 4: Implement**

In `swingbot/core/market/fvg_context.py`, change the first `swingbot` import line to:

```python
from swingbot.core.market import fvg, levels, structure
```

Replace the whole `formation_tags` function with:

```python
def formation_tags(df: pd.DataFrame, gap: dict) -> dict:
    """Tags known at the close of the gap's third candle ``i``. Reads rows <= i."""
    i = int(gap["bar_index"])
    window = df.iloc[:i + 1]
    atr_i = _atr_at(window, i)
    return {"origin": _origin(window, gap),
            "size_atr": None if atr_i is None else round((gap["top"] - gap["bottom"]) / atr_i, 6),
            "displacement": "yes" if fvg.is_displacement_gap(window, gap, DISPLACEMENT_K) else "no"}
```

`atr_series` is left at its default so the predicate computes ATR on `window` itself.

- [ ] **Step 5: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_displacement.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_tags.py`
Expected: PASS (the formation-tag causality tests now cover the new key too).
Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/fvg_context.py tests/market/test_fvg_context_displacement.py
git commit -m "feat(v134): fvg_context -- displacement tag from v128's predicate at k=1.5"
```

### Task V134-8: Structure tag

**Files:**
- Modify: `swingbot/core/market/fvg_context.py`
- Test: `tests/market/test_fvg_context_structure.py`

**Interfaces:**
- Consumes (v130, V130-3): `structure.major_structure_features(df, direction) -> dict`, which returns every `MAJOR_KEYS` value at `df`'s final bar for a trade in `direction`. This task reads two of them: `struct_event_last` (`"bos_with" | "bos_against" | "choch_with" | "choch_against" | None`, where "with" means the event's direction equals `direction`) and `struct_event_bars_ago` (`int | None`). A frame under `structure.MIN_BARS = 60` returns `None` for both and never raises. Test frames from v130's `tests/market/structure_tier_fixtures.py`: `DOWN`, `tier_frame(points, *, mirror=False)`.
- Produces: `formation_tags` gains `"structure"` (`"bos" | "choch" | "none"`). Its full key set is now `origin, size_atr, displacement, structure`.

**Blocked on: v130 (V130-3).** Do not start unless V134-1 Step 2 prints `v130 code: PRESENT`. Frozen reading F11 applies.

The fixture positions below are v130's own pinned expectations (V130-3's `test_choch_is_labelled_with_or_against_the_trade` and `test_bos_is_labelled_with_or_against_the_trade`): on `tier_frame(DOWN)` a CHoCH that is "with" a bullish trade fires at bar 94 and is still the latest event at bar 96; a BOS that is "with" a bearish trade fires at bar 70. `mirror=True` swaps the sides. If those two v130 tests were changed when v130 was implemented, read the new positions from them and use those; do not edit v130's fixture.

- [ ] **Step 1: Invoke the `no-lookahead` skill.** The tag must call v130 on the prefix ending at the third candle.

- [ ] **Step 2: Write the failing tests**

```python
# tests/market/test_fvg_context_structure.py
"""v134: the structure tag reads v130's event keys at the gap's third candle."""
import pytest

from swingbot.core.market import fvg_context as fc
from swingbot.core.market import structure
from tests.market.fvg_context_frames import ABOVE, GAP_I, gap_frame, mirror
from tests.market.structure_tier_fixtures import DOWN, tier_frame


def _base(frame):
    return next(g for g in fc.all_gaps(frame) if g["bar_index"] == GAP_I)


def _gap_at(frame, i, direction):
    """A stand-in gap at row i. The structure tag reads only bar_index and direction."""
    close = float(frame["Close"].iloc[i])
    return {"bottom": close - 0.5, "top": close + 0.5, "mid": close, "bar_index": i, "direction": direction}


@pytest.mark.parametrize("last,age,expected", [
    ("bos_with", 0, "bos"), ("bos_with", 1, "bos"), ("bos_with", 2, "none"),
    ("choch_with", 0, "choch"), ("choch_with", 1, "choch"), ("choch_with", 5, "none"),
    ("bos_against", 0, "none"), ("choch_against", 1, "none"), (None, None, "none")])
@pytest.mark.parametrize("flip", [False, True])
def test_the_bucket_follows_v130s_latest_event_and_its_age(monkeypatch, last, age, expected, flip):
    seen = {}

    def fake(df, direction):
        seen.update(bars=len(df), direction=direction)
        return {"struct_event_last": last, "struct_event_bars_ago": age, "structure_aligned_major": None}

    monkeypatch.setattr(structure, "major_structure_features", fake)
    frame = gap_frame([ABOVE] * 3)
    frame = mirror(frame) if flip else frame
    assert fc.formation_tags(frame, _base(frame))["structure"] == expected
    assert seen == {"bars": GAP_I + 1, "direction": "bearish" if flip else "bullish"}     # rows <= i, the gap's side


def test_a_frame_too_short_for_v130_is_none():
    frame = gap_frame()                                    # 22 bars, under structure.MIN_BARS
    assert fc.formation_tags(frame, _base(frame))["structure"] == "none"


@pytest.mark.parametrize("mirrored,with_side,against_side", [(False, "bullish", "bearish"), (True, "bearish", "bullish")])
def test_a_choch_on_the_middle_or_third_candle_tags_the_gap(mirrored, with_side, against_side):
    frame = tier_frame(DOWN, mirror=mirrored)              # v130's fixture: this CHoCH fires at bar 94
    assert fc.formation_tags(frame, _gap_at(frame, 94, with_side))["structure"] == "choch"      # on the third candle
    assert fc.formation_tags(frame, _gap_at(frame, 95, with_side))["structure"] == "choch"      # on the middle candle
    assert fc.formation_tags(frame, _gap_at(frame, 96, with_side))["structure"] == "none"       # two bars old
    assert fc.formation_tags(frame, _gap_at(frame, 94, against_side))["structure"] == "none"    # choch_against


@pytest.mark.parametrize("mirrored,with_side,against_side", [(False, "bearish", "bullish"), (True, "bullish", "bearish")])
def test_a_bos_on_the_third_candle_tags_the_gap(mirrored, with_side, against_side):
    frame = tier_frame(DOWN, mirror=mirrored)              # v130's fixture: this BOS fires at bar 70
    assert fc.formation_tags(frame, _gap_at(frame, 70, with_side))["structure"] == "bos"
    assert fc.formation_tags(frame, _gap_at(frame, 70, against_side))["structure"] == "none"    # bos_against


def test_bars_after_the_third_candle_never_change_the_structure_tag():
    frame = tier_frame(DOWN)
    gap = _gap_at(frame, 94, "bullish")
    assert fc.formation_tags(frame.iloc[:95], gap) == fc.formation_tags(frame, gap)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_structure.py`
Expected: FAIL with `KeyError: 'structure'`.

- [ ] **Step 4: Implement**

In `swingbot/core/market/fvg_context.py`, add below the `STRUCTURE_EVENT_MAX_AGE` line:

```python

_STRUCTURE_BUCKET = {"bos_with": "bos", "choch_with": "choch"}
```

Insert directly above `def formation_tags`:

```python
def _structure(window: pd.DataFrame, gap: dict) -> str:
    """bos / choch when v130's latest major-structure event is with the gap's
    direction and fired on the middle or third candle; otherwise none."""
    keys = structure.major_structure_features(window, gap["direction"])
    age = keys.get("struct_event_bars_ago")
    if age is None or age > STRUCTURE_EVENT_MAX_AGE:
        return "none"
    return _STRUCTURE_BUCKET.get(keys.get("struct_event_last"), "none")
```

Replace the whole `formation_tags` function with:

```python
def formation_tags(df: pd.DataFrame, gap: dict) -> dict:
    """Tags known at the close of the gap's third candle ``i``. Reads rows <= i."""
    i = int(gap["bar_index"])
    window = df.iloc[:i + 1]
    atr_i = _atr_at(window, i)
    return {"origin": _origin(window, gap),
            "size_atr": None if atr_i is None else round((gap["top"] - gap["bottom"]) / atr_i, 6),
            "displacement": "yes" if fvg.is_displacement_gap(window, gap, DISPLACEMENT_K) else "no",
            "structure": _structure(window, gap)}
```

- [ ] **Step 5: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_context_structure.py`
Expected: PASS, `0 failed`.
Run each: `python scripts/dev/testrun.py file tests/market/test_fvg_context_tags.py` and `python scripts/dev/testrun.py file tests/market/test_fvg_context_displacement.py`
Expected: PASS (their frames are under 60 bars or carry no event, so the new key is `none` and the equality asserts still hold).
Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/fvg_context.py tests/market/test_fvg_context_structure.py
git commit -m "feat(v134): fvg_context -- structure tag from v130's BOS/CHoCH event keys"
```

### Task V134-9: Table A collector: one row per touched gap, census and censoring

**Files:**
- Modify: `scripts/backtest/measure_fvg_context_diagnostic.py`
- Modify: `tests/scripts/test_measure_fvg_context_diagnostic.py` (append)

**Interfaces:**
- Consumes: `fc.all_gaps`, `fc.first_touch`, `fc.formation_tags` (keys `origin, size_atr, displacement, structure`), `fc.touch_tags` (keys `confluence, confluence_families, approach, approach_ratio, touch_close`), `fc.gap_outcome` (V134-2 .. V134-8); `train_frame`, `CENSUS_KEYS`, `DIRECTIONS`, `TRAIN_START` (V134-6).
- Produces:
  - `classify_gap(df, gap) -> tuple[str, float | None, dict | None]`: the census bucket (`touched | gapped_through | untouched | censored | no_atr`), the gap's `size_atr` when it is resolved and sized, and its row when touched.
  - `collect_gaps(ticker, df, start=TRAIN_START) -> dict`: `{"rows": [gap row, ...], "census": {"formed": n, <bucket>: n, ...}, "sizes": {"bullish": [...], "bearish": [...]}, "months": ["TICKER:YYYY-MM", ...]}`. `df` must already be truncated by `train_frame`. A census key is absent when its count is zero. Rows follow V134-6's gap row contract, without the `"size"` key (`with_size` adds it after pooling).

**Blocked on: v128 and v130**, through V134-7 and V134-8 (the rows carry both tags). Frozen readings F1, F2 and F6 apply.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_fvg_context_diagnostic.py`:

```python
from tests.market.fvg_context_frames import ABOVE, FLAT, MIDDLE, THIRD, TOUCH, bar_frame, gap_frame  # noqa: E402

QUIET = (102.0, 103.0, 101.0, 102.6)          # after TOUCH: reaches neither the stop 100.5 nor the target 104.25
JUMP = (100.0, 100.5, 98.0, 99.0)             # jumps the whole zone


def test_a_touched_gap_becomes_one_row_with_every_tag_and_its_outcome():
    out = mfc.collect_gaps("T", gap_frame([TOUCH] + [QUIET] * 20))
    assert out["census"] == {"formed": 1, "touched": 1}
    assert out["months"] == ["T:2021-02"] and out["sizes"] == {"bullish": [0.25], "bearish": []}
    (row,) = out["rows"]
    assert {"ticker", "direction", "formed", "outcome", "r", "size_atr", *(set(mfc.TAG_BUCKETS) - {"size"})} <= set(row)
    assert (row["ticker"], row["direction"], row["formed"], row["outcome"]) == ("T", "bullish", "2021-02-02", "timeout")
    assert row["r"] == pytest.approx(0.4) and row["origin"] == "intrabar" and row["touch_close"] == "above"


@pytest.mark.parametrize("after", [[ABOVE] * 10, [TOUCH] + [QUIET] * 5])
def test_a_gap_whose_touch_or_outcome_is_not_known_yet_is_censored(after):
    out = mfc.collect_gaps("T", gap_frame(after))
    assert out["census"] == {"formed": 1, "censored": 1}
    assert out["rows"] == [] and out["sizes"] == {"bullish": [], "bearish": []}


def test_a_gap_whose_outcome_would_need_a_2024_bar_is_censored():
    bars = [FLAT] * 20 + [MIDDLE, THIRD, TOUCH] + [QUIET] * 30
    frame = bar_frame(bars, start="2023-11-02")                 # touch on 2023-12-04; bar tau+20 is 2024-01-01
    assert str(frame.index[22].date()) == "2023-12-04" and str(frame.index[42].date()) == "2024-01-01"
    assert mfc.collect_gaps("T", frame)["census"] == {"formed": 1, "touched": 1}          # what a peek would score
    assert mfc.collect_gaps("T", mfc.train_frame(frame))["census"] == {"formed": 1, "censored": 1}


def test_gapped_through_and_untouched_are_counted_sized_and_not_scored():
    jumped = mfc.collect_gaps("T", gap_frame([ABOVE, JUMP]))
    assert jumped["census"]["gapped_through"] == 1 and jumped["sizes"]["bullish"] == [0.25]
    assert jumped["rows"] == []
    untouched = mfc.collect_gaps("T", gap_frame([ABOVE] * 60))
    assert untouched["census"] == {"formed": 1, "untouched": 1} and untouched["rows"] == []


def test_a_gap_formed_before_the_start_is_lookback_only():
    out = mfc.collect_gaps("T", gap_frame([TOUCH] + [QUIET] * 20), start="2021-03-01")
    assert out == {"rows": [], "census": {}, "sizes": {"bullish": [], "bearish": []}, "months": []}


def test_a_gap_without_atr14_is_counted_as_no_atr_and_dropped():
    frame = bar_frame([FLAT] * 5 + [MIDDLE, THIRD, TOUCH] + [QUIET] * 20)
    out = mfc.collect_gaps("T", frame)
    assert out["census"] == {"formed": 1, "no_atr": 1} and out["rows"] == []


def test_every_formed_gap_lands_in_exactly_one_census_bucket():
    out = mfc.collect_gaps("T", gap_frame([ABOVE, JUMP, TOUCH] + [QUIET] * 30))
    census = out["census"]
    assert census["formed"] == sum(census.get(key, 0) for key in mfc.CENSUS_KEYS[1:])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: the new tests FAIL with `AttributeError: module 'measure_fvg_context_diagnostic' has no attribute 'collect_gaps'`; every V134-6 test still passes.

- [ ] **Step 3: Implement**

In `scripts/backtest/measure_fvg_context_diagnostic.py`, add below the `windows` import:

```python
from swingbot.core.market import fvg_context as fc  # noqa: E402
```

Append at the end of the file:

```python
# --- Table A collector ------------------------------------------------------------

def classify_gap(df, gap: dict) -> tuple:
    """(census bucket, size_atr or None, touched-gap row or None) for one formed gap.
    ``pending`` from the instrument means a 2024 bar would be needed: censored."""
    touch = fc.first_touch(df, gap)
    if touch["status"] == "pending":
        return "censored", None, None
    formation = fc.formation_tags(df, gap)
    if formation["size_atr"] is None:
        return "no_atr", None, None
    if touch["status"] != "touch":
        return touch["status"], formation["size_atr"], None
    outcome = fc.gap_outcome(df, gap, touch)
    if outcome["status"] in ("pending", "no_atr"):
        return ("censored" if outcome["status"] == "pending" else "no_atr"), None, None
    row = {**formation, **fc.touch_tags(df, gap, touch), "direction": gap["direction"],
           "formed": str(df.index[gap["bar_index"]].date()), "outcome": outcome["status"], "r": outcome["r"]}
    return "touched", formation["size_atr"], row


def collect_gaps(ticker: str, df, start: str = TRAIN_START) -> dict:
    """Every gap of one ticker formed on or after ``start`` in an already-truncated frame."""
    census, rows, months = Counter(), [], set()
    sizes = {direction: [] for direction in DIRECTIONS}
    for gap in fc.all_gaps(df):
        formed = str(df.index[gap["bar_index"]].date())
        if formed < start:
            continue
        bucket, size_atr, row = classify_gap(df, gap)
        census["formed"] += 1
        census[bucket] += 1
        months.add(f"{ticker}:{formed[:7]}")
        if size_atr is not None:
            sizes[gap["direction"]].append(size_atr)
        if row is not None:
            rows.append({**row, "ticker": ticker})
    return {"rows": rows, "census": dict(census), "sizes": sizes, "months": sorted(months)}
```

`first_touch` runs before the tags on purpose: a censored gap costs no level collection and no structure scan.

- [ ] **Step 4: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: PASS, `0 failed`.
Run: `python -m radon cc -s -n C scripts/backtest/measure_fvg_context_diagnostic.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_fvg_context_diagnostic.py tests/scripts/test_measure_fvg_context_diagnostic.py
git commit -m "feat(v134): diagnostic script -- Table A collector with census and 2024 censoring"
```
