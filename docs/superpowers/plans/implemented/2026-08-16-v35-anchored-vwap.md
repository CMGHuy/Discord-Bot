# Anchored VWAP Levels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.7.0 · bot 1.1.4
Bump: bot patch

**Goal:** Add a 52-week high/low anchor, name each anchor in alerts, verify the
confluence-inflation guard, and — the real deliverable — **turn anchored VWAP
on**, since it is currently built and disabled.

**Architecture:** Almost everything exists. `anchored_vwap()` and
`avwap_anchors()` are implemented with no-lookahead already handled;
`levels.py:345` consumes them behind `AVWAP_LEVELS_ENABLED`. This plan adds one
anchor family, replaces an unreadable label, and runs the measurement that the
flag's own help text says has never been done.

**Tech Stack:** Python 3.11+, pandas, pytest. No new dependencies.

## What the spec assumed vs. what the code does

The spec said Task 1 might collapse this plan's scope. It did.

| Spec assumption | Reality |
|---|---|
| "extend to swing-pivot anchors" | **Already done.** `avwap_anchors():183-187` takes the last 2 confirmed pivot lows and 2 pivot highs, `span=5` confirmed both sides. |
| "respect NO-LOOKAHEAD" | **Already done and documented** (`factors.py:172-177`): the pivot scan stops `span` bars short of the end precisely so an unconfirmed pivot cannot be used. |
| "guard against confluence inflation" | **Already handled.** Every anchor appends the same `"AVWAP"` source label (`levels.py:348`), and `confidence.py:243` dedups with `dict.fromkeys(...)`. Task 2 verifies rather than builds. |
| "add 52w high/low anchor" | **Genuinely missing.** Current anchors are pivots + highest-volume bar. |
| "surface by name" | **Genuinely missing.** All anchors collapse to the bare label `"AVWAP"`; the anchor is never named. |

**And the thing the spec did not know:** `AVWAP_LEVELS_ENABLED` **defaults to
`false`** (`config.py:592`). Its help text says the flag exists because the
source "SHIFTS" the level map and had not been judged "until the E33
walk-forward folds and the E40 shadow forward-gate have actually judged it".

So anchored VWAP contributes **nothing today**. The largest win available here
is not a new anchor — it is running the measurement and turning it on.

## Global Constraints

- **No gating.** AVWAP contributes levels and confidence, never a veto.
- **No earnings-gap anchor** in v1.
- **`CLUSTER_TOLERANCE_PCT` is untouched.**
- **Method count must not inflate with anchor count.**
- **NO-LOOKAHEAD** applies to any new anchor.
- **DEPENDS ON v32** — AVWAP-confirmed levels feed confluence factors v32 weights.

## v32 landed, but not as this plan assumed

`docs/superpowers/plans/implemented/2026-08-16-v32-unified-confidence-score.md`
merged to `main` on 2026-08-17 -- `_resolve_confluence`/`FactorContext`/
`FACTORS` are real, live code (this plan's line 131-132 note about
asserting against `dict.fromkeys` at `confidence.py:243` if v32 hadn't
landed no longer applies -- it has). But `UNIFIED_CONFIDENCE` stays
default-off: v32's TRAIN measurement found `factor_target_confluence_quality`
and `factor_stop_confluence` (the confluence factors this plan's
AVWAP-confirmed levels would feed) both Wilson-overlapping -- no measured
weight for AVWAP-derived confluence to inherit -- and the one-shot
VALIDATION run then FAILed regardless. Full result:
`docs/superpowers/plans/implemented/v32-train-preregistration.md`.

## File Structure

| File | Responsibility |
|---|---|
| `swingbot/core/edge/factors.py` | `avwap_anchors()` gains 52w extremes and returns labelled anchors. |
| `swingbot/core/market/levels.py:345-351` | Consumes labelled anchors; emits per-anchor source labels. |
| `tests/edge/test_avwap.py` | **NEW.** |

---

# Phase 1 — Verify what exists

### Task 1: Characterize current anchor behavior and the inflation guard

**Files:**
- Create: `tests/edge/test_avwap.py`

**Interfaces:**
- Produces: characterization tests pinning today's behavior before it changes.

- [ ] **Step 1: Write characterization tests**

```python
# tests/edge/test_avwap.py
import pandas as pd
import pytest

from swingbot.core.edge.factors import anchored_vwap, avwap_anchors


def _frame(n=200):
    closes = [100 + (i % 20) - 10 for i in range(n)]
    return pd.DataFrame({
        "Open": closes,
        "High": [c + 2 for c in closes],
        "Low": [c - 2 for c in closes],
        "Close": closes,
        "Volume": [1_000_000 + (i % 7) * 100_000 for i in range(n)],
    })


def test_anchors_are_all_within_the_frame():
    df = _frame()
    for a in avwap_anchors(df):
        assert 0 <= a < len(df)


def test_no_anchor_within_span_of_the_last_bar():
    """NO-LOOKAHEAD: a pivot needs span=5 bars of confirmation on both sides,
    so an anchor closer than that to the end would be a pivot only because
    the data ran out. factors.py:172-177 documents this; this test enforces it
    against future edits."""
    df = _frame()
    pivots = [a for a in avwap_anchors(df) if a != df["Volume"].values.argmax()]
    assert all(a <= len(df) - 6 for a in pivots)


def test_anchored_vwap_starts_at_the_anchor_bar_price():
    df = _frame()
    series = anchored_vwap(df, 100)
    assert len(series) == len(df) - 100
    bar = df.iloc[100]
    expected = (bar["High"] + bar["Low"] + bar["Close"]) / 3.0
    assert series.iloc[0] == pytest.approx(expected)


def test_multiple_avwap_anchors_count_as_one_confirming_method():
    """The inflation guard, verified not assumed: several anchors landing in
    one cluster must not let a single method reach Lv5 wearing three hats."""
    from swingbot.core.scanning.confidence import _resolve_confluence
    count, families = _resolve_confluence(None, ["AVWAP", "AVWAP", "EMA"])
    assert count == 2
    assert families == ["AVWAP", "EMA"]
```

- [ ] **Step 2: Run the tests**

Run: `python scripts/dev/testrun.py file tests/edge/test_avwap.py`
Expected: PASS — these describe existing behavior.

If `test_multiple_avwap_anchors_count_as_one_confirming_method` **fails**, the
inflation guard does not hold and becomes a real implementation task; fix it
here before continuing. (`_resolve_confluence` was introduced by v32 Task 6
and has landed -- assert against it directly, not the pre-v32
`dict.fromkeys` fallback this note used to require.)

- [ ] **Step 3: Commit**

```bash
git add tests/edge/test_avwap.py
git commit -m "test(v35): characterize AVWAP anchors, no-lookahead and the inflation guard"
```

---

# Phase 2 — Add the 52-week anchor and name the anchors

### Task 2: Labelled anchors, including 52-week extremes

**Files:**
- Modify: `swingbot/core/edge/factors.py:168-191`
- Test: `tests/edge/test_avwap.py`

**Interfaces:**
- Produces: `avwap_anchors(df, lookback=120) -> list[tuple[int, str]]` — a
  **breaking return-type change** from `list[int]`. The only caller is
  `levels.py:347` (Task 3); `engine.py:216` also references anchors and must be
  checked.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/edge/test_avwap.py
def test_anchors_are_labelled_tuples():
    for anchor in avwap_anchors(_frame()):
        assert isinstance(anchor, tuple)
        idx, label = anchor
        assert isinstance(idx, int) and isinstance(label, str)


def test_labels_are_human_readable_not_bar_indices():
    """engine.py:216 built 'AVWAP{index}' -- a bar number means nothing to a
    reader. A label must name the event the anchor represents."""
    labels = {label for _idx, label in avwap_anchors(_frame())}
    assert any("swing" in l.lower() for l in labels)
    assert not any(l.strip().isdigit() for l in labels)


def test_fifty_two_week_high_and_low_are_anchored():
    """A frame with an unmistakable 52w high and low must anchor both."""
    closes = [100] * 300
    closes[50] = 250      # 52w high
    closes[120] = 20      # 52w low
    df = pd.DataFrame({
        "Open": closes, "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes], "Close": closes,
        "Volume": [1_000_000] * len(closes),
    })
    anchors = avwap_anchors(df)
    indices = {idx for idx, _label in anchors}
    labels = {label for _idx, label in anchors}
    assert 50 in indices and 120 in indices
    assert "52w high" in labels and "52w low" in labels


def test_fifty_two_week_window_is_bounded_to_252_bars():
    """An extreme older than a year is not a 52-week extreme."""
    closes = [100] * 400
    closes[10] = 999      # far older than 252 bars
    df = pd.DataFrame({
        "Open": closes, "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes], "Close": closes,
        "Volume": [1_000_000] * len(closes),
    })
    assert 10 not in {idx for idx, _l in avwap_anchors(df)}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_avwap.py`
Expected: FAIL — anchors are bare ints

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/edge/factors.py -- replace avwap_anchors
_FIFTY_TWO_WEEK_BARS = 252


def avwap_anchors(df: pd.DataFrame, lookback: int = 120) -> list:
    """Anchor bars that mean something, each with a human-readable label:
    recent swing pivots, the highest-volume day (a capitulation/breakout bar
    everyone remembers), and the 52-week extremes.

    Pivots need `span` bars of confirmation on BOTH sides, so the scan stops
    `span` bars short of the end -- an unconfirmed low that is only a low
    because the data ran out is not a swing low. That also keeps this side of
    the no-lookahead rule: every bar this reads is at or before the frame's
    last bar, and no anchor depends on a bar that hadn't printed yet when the
    anchor formed. The 52-week extremes are backward-looking for the same
    reason.

    Returns [(bar_index, label)], sorted by index. Labels are rendered to the
    user, so they name the event, never the bar number.
    """
    n = len(df)
    start = max(0, n - lookback)
    lows, highs = df["Low"].values, df["High"].values
    span = 5
    anchors: dict[int, str] = {}

    pivots_lo = [i for i in range(max(start, span), n - span)
                 if lows[i] == min(lows[i - span:i + span + 1])]
    pivots_hi = [i for i in range(max(start, span), n - span)
                 if highs[i] == max(highs[i - span:i + span + 1])]
    for i in pivots_lo[-2:]:
        anchors[i] = "swing low"
    for i in pivots_hi[-2:]:
        anchors[i] = "swing high"

    anchors[start + int(df["Volume"].values[start:].argmax())] = "volume spike"

    yr_start = max(0, n - _FIFTY_TWO_WEEK_BARS)
    anchors[yr_start + int(highs[yr_start:].argmax())] = "52w high"
    anchors[yr_start + int(lows[yr_start:].argmin())] = "52w low"

    return sorted(anchors.items())
```

A bar that is both (say) a swing low and the 52-week low keeps one label — the
dict makes the collision deterministic rather than emitting a duplicate anchor.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/edge/test_avwap.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/factors.py tests/edge/test_avwap.py
git commit -m "feat(v35): labelled AVWAP anchors with 52-week extremes"
```

---

### Task 3: Consume labelled anchors in the level map and name them in alerts

**Files:**
- Modify: `swingbot/core/market/levels.py:345-351`
- Modify: `swingbot/core/scanning/engine.py:216`
- Test: `tests/market/test_levels_avwap.py`

**Interfaces:**
- Consumes: `avwap_anchors` (Task 2).
- Produces: source labels of the form `"Anchored VWAP (52w high)"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_levels_avwap.py
from swingbot import config
from swingbot.core.market.levels import _cluster_levels


def test_avwap_sources_name_their_anchor(monkeypatch):
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", True)
    levels = _build_level_map(_frame_with_clear_52w_high())
    labels = {s for lv in levels for s in lv.sources}
    assert any(l.startswith("Anchored VWAP (") for l in labels)


def test_avwap_family_still_counts_once_for_confluence():
    """Per-anchor labels must NOT multiply the method count. Display detail
    and confluence weight are deliberately different things."""
    from swingbot.core.scanning.confidence import _resolve_confluence
    count, families = _resolve_confluence(
        None, ["Anchored VWAP (52w high)", "Anchored VWAP (swing low)", "EMA"])
    assert count == 2
    assert families == ["Anchored VWAP", "EMA"]


def test_avwap_disabled_produces_no_avwap_levels(monkeypatch):
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", False)
    levels = _build_level_map(_frame_with_clear_52w_high())
    assert not any("VWAP" in s for lv in levels for s in lv.sources)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_levels_avwap.py`
Expected: FAIL — sources are the bare string `"AVWAP"`

- [ ] **Step 3: Emit labelled sources**

```python
# swingbot/core/market/levels.py:345-351
    if config.AVWAP_LEVELS_ENABLED:
        try:
            from swingbot.core.edge.factors import anchored_vwap, avwap_anchors
            for anchor_idx, anchor_label in avwap_anchors(df):
                v = float(anchored_vwap(df, anchor_idx).iloc[-1])
                if v > 0:
                    candidates.append((v, f"Anchored VWAP ({anchor_label})"))
        except Exception:
            pass
```

- [ ] **Step 4: Collapse the family for confluence counting**

Per-anchor labels would otherwise inflate the count. Normalize in
`_resolve_confluence` (v32 Task 6) — everything matching
`^Anchored VWAP \(` folds to the family name `"Anchored VWAP"` before the
dedup, while the full label is kept for display.

- [ ] **Step 5: Fix `engine.py:216`'s anchor label**

It builds `f"⚓{a}"` from a bar index. Use the anchor's label:

```python
ctx["avwaps"] = [{"series": rs_factors.anchored_vwap(df, idx),
                  "anchor_label": label}
                 for idx, label in rs_factors.avwap_anchors(df)]
```

- [ ] **Step 6: Run tests and the fast tier**

Run: `python scripts/dev/testrun.py file tests/market/test_levels_avwap.py`
Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/levels.py swingbot/core/scanning/engine.py tests/market/test_levels_avwap.py
git commit -m "feat(v35): name the anchor in AVWAP level sources"
```

---

# Phase 3 — Judge the flag that was never judged

### Task 4: Measure AVWAP's effect and decide the default

**Files:**
- Create: `docs/superpowers/plans/v35-avwap-preregistration.md`
- Modify: `swingbot/config.py:590`

This is the task with the actual value in it. `AVWAP_LEVELS_ENABLED` has been
`false` since it was written, waiting on a measurement.

- [ ] **Step 1: Confirm the flag's stated precondition**

Its help text defers to "the E33 walk-forward folds and the E40 shadow
forward-gate". Establish whether those ran and what they concluded:

Run: `git log --oneline --all --grep="E33\|E40" | head -20`
Run: `git grep -rn "E33\|E40" -- docs/ | head -20`

If they concluded something, honour it. If they never ran, this task is the
judgement they were waiting for — say so in the pre-registration.

- [ ] **Step 2: Run the TRAIN comparison**

Dispatch via `backtest-runner`. AVWAP off vs. on, same window. Because AVWAP
**shifts the level map**, report target-price drift, not only win rate:
what fraction of scenarios get a different TP1, and by how much.

Run: `python scripts/backtest/run_backtest_range.py --train --json data/v35_train_avwap.json`

- [ ] **Step 3: Check the confluence-count distribution**

The real risk here is inflation, not regression. Compare the distribution of
method counts with AVWAP off vs. on. A rightward shift concentrated in
scenarios where AVWAP was the *only* added family means the guard is leaking.

- [ ] **Step 4: Write the pre-registration**

```markdown
## v35 VALIDATION pre-registration
- Primary: win rate at MIN_ALERT_CONFIDENCE_LEVEL=4 with AVWAP_LEVELS_ENABLED=on.
- PASS: no win-rate regression versus AVWAP off, AND the mean confluence count
  rises by less than 0.5 methods per scenario.
- This spec adds no gate, so alert volume is expected to be roughly flat; a
  swing beyond +-10% means the level map moved more than intended -- investigate
  before shipping.
- One shot. FAIL means AVWAP_LEVELS_ENABLED stays default-off, and that is a
  completed result, not a failure to retry.
```

- [ ] **Step 5: Run VALIDATION once**

Run: `python scripts/backtest/run_backtest_range.py --validation --json data/v35_validation.json`

- [ ] **Step 6: Record the result and set the default**

On PASS, `default="true"` at `config.py:592` and update the help text to cite
this measurement instead of the pending E33/E40 gates. On FAIL, leave it off and
update the help text to say it was judged and declined, with the date — so the
next session does not re-run a closed question.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py docs/superpowers/plans/v35-avwap-preregistration.md data/v35_validation.json
git commit -m "feat(v35): judge AVWAP_LEVELS_ENABLED and set its default"
```

---

### Task 5: Docs and close-out

**Files:**
- Modify: `docs/strategy.md`, `VERSION.json`

- [ ] **Step 1: Update `docs/strategy.md`**

Its level-methods list has eight entries and no anchored VWAP. Add it with its
anchors named, and state that all anchors count as one confirming family.

- [ ] **Step 2: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 3: Bump and close**

`bot` patch on PASS; on FAIL the labelled-anchor work still shipped, so still a
patch. Amend the spec's `Bump:` line if it came out differently, with one clause
on why.

```bash
git mv docs/superpowers/specs/2026-08-16-v35-anchored-vwap-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-16-v35-anchored-vwap.md docs/superpowers/plans/implemented/
git add -A
git commit -m "docs(v35): document anchored VWAP, bump version, close the spec"
```

---

## Parallelisation

- **Sequential: Task 1 before Task 2.** Task 1's characterization tests are the
  safety net for Task 2's breaking return-type change.
- **Sequential: Task 2 → Task 3.** Task 3 consumes the labelled-tuple contract.
- **Sequential: Task 3 → Task 4.** Measuring before the level labels are final
  measures the wrong thing.
- **Sequential: Task 4 → Task 5.**
- **No parallel groups.** This plan is a genuine chain — each task consumes the
  previous task's contract. Stating that is worth as much as a wide group: it
  stops the next session re-deriving the dependency graph.

## Progress

- [x] Task 1 — Characterize anchors, no-lookahead, inflation guard
- [x] Task 2 — Labelled anchors + 52-week extremes
- [x] Task 3 — Named sources in the level map
- [x] Task 4 — Measure and decide `AVWAP_LEVELS_ENABLED`
- [x] Task 5 — Docs and close-out
