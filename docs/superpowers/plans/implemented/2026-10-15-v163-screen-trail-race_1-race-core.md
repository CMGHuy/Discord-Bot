# v163 Idea screen trailing-exit race, part 1: race core (V163-1..V163-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V163-3" -A 300 docs/superpowers/plans/2026-10-15-v163-screen-trail-race_1-race-core.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-10-15-v163-screen-trail-race-design.md`](../../specs/implemented/2026-10-15-v163-screen-trail-race-design.md)
**Index:** [`2026-10-15-v163-screen-trail-race_0-index.md`](2026-10-15-v163-screen-trail-race_0-index.md) carries the header, `## Global Constraints`, the binding deviations, `## Parallelisation` and the task ledger. Every task below implicitly includes those constraints.

**Scope of this part:** `Idea.race_shape` and the trail cap floor (V163-1); the two appended outcome codes, the per-shape outcome table and the fixed-doc byte-identity pins (V163-2); the trail race itself (V163-3); the `race_for` dispatcher through `run_book` and `null.matched_null` (V163-4).

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree, never edited by these tasks). `$WT` = `$R/.claude/worktrees/2026-10-15-v163-screen-trail-race` (branch `2026-10-15-v163-screen-trail-race`). Never `cd`; use absolute paths and `git -C $WT`. Every edit below is to the file under `$WT`.

# Phase 1: race core

### Task V163-1: `Idea.race_shape`, `RACE_SHAPES`, trail cap floor, `_load` reads `RACE`; registry pins

**Model:** sonnet — a small dataclass field plus validation with fully specified tests; no numerics.

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (docstring lines 1-6, `Idea` lines 22-37, `_load` lines 40-44)
- Modify: `tests/backtesting/screen/test_ideas_registry.py` (additions only)

**Interfaces:**
- Consumes: nothing from earlier tasks. Existing: `Idea(name, events, time_cap_bars, direction="long", params, summary, source)` with `__post_init__` raising `ValueError` (`ideas/__init__.py:32-37`); `_load(name)` (`:40-44`); `IDEAS` (`:47`).
- Produces (ledger contract, final):
  - `ideas.RACE_SHAPES = ("fixed", "trail")`
  - `ideas.TRAIL_MIN_CAP = 60`
  - `Idea.race_shape: str = "fixed"` — the **last** field, after `source`.
  - `Idea.__post_init__` raises `ValueError` when `race_shape not in RACE_SHAPES`, and when `race_shape == "trail"` and `time_cap_bars < TRAIL_MIN_CAP`.
  - `_load(name)` passes `race_shape=getattr(module, "RACE", "fixed")`.
  - V163-2 reads `idea.race_shape` to pick `race.SHAPE_OUTCOMES[idea.race_shape]`; V163-5 passes it to `run_book` / `matched_null`.

- [ ] **Step 0: Create (or reuse) the worktree**

Use the `worktree-lifecycle` skill. If `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `.claude/worktrees/2026-10-15-v163-screen-trail-race`, reuse it and resume at its first uncommitted task. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race -b 2026-10-15-v163-screen-trail-race main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race log --oneline -1
```

Expected: the branch head equals `main`'s head. Confirm the screen code is the one this plan was written against (expected: empty output):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race diff --stat 316c57e9 HEAD -- swingbot/core/backtesting/screen scripts/backtest/screen_idea.py tests/scripts/test_screen_idea.py tests/backtesting/screen
```

If it prints anything, stop and report: V163-2's pinned literals were captured against `316c57e9`.

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/backtesting/screen/test_ideas_registry.py`, add `import sys` and `import types` to the import block at the top, beside `import dataclasses`. Nothing else above changes. Append:

```python
def test_every_registered_idea_is_raced_under_one_pinned_shape():
    """One shape per idea, frozen with the idea (v163 spec § One shape per
    idea). Flipping a shape means editing this pin in the same diff."""
    assert ideas.RACE_SHAPES == ("fixed", "trail")
    assert {n: i.race_shape for n, i in IDEAS.items()} == {
        "high52w": "fixed", "uptrend_pullback": "fixed", "gap_volume": "fixed",
        "turn_of_month": "fixed", "turtle_soup": "fixed", "quiet_pullback": "fixed"}


def _events(df):
    return df["Close"] > 0


def test_an_idea_defaults_to_the_fixed_shape():
    assert Idea(name="x", events=_events, time_cap_bars=5).race_shape == "fixed"


def test_an_unknown_race_shape_is_refused():
    with pytest.raises(ValueError, match="race shape"):
        Idea(name="x", events=_events, time_cap_bars=60, race_shape="donchian")


def test_a_trail_idea_needs_a_cap_of_at_least_sixty_bars():
    assert ideas.TRAIL_MIN_CAP == 60
    with pytest.raises(ValueError, match="at least 60"):
        Idea(name="x", events=_events, time_cap_bars=59, race_shape="trail")
    assert Idea(name="x", events=_events, time_cap_bars=60,
                race_shape="trail").race_shape == "trail"


def test_a_fixed_idea_keeps_any_cap_of_one_bar_or_more():
    assert Idea(name="x", events=_events, time_cap_bars=4).time_cap_bars == 4


def _fake_module(monkeypatch, name, **attrs):
    module = types.ModuleType(f"{ideas.__name__}.{name}")
    module.CAP, module.PARAMS = attrs.pop("CAP"), {"k": 1}
    module.SUMMARY, module.SOURCE, module.events = "s", "src", _events
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return name


def test_load_reads_the_race_constant_and_defaults_to_fixed(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_plain", CAP=10)
    trail = _fake_module(monkeypatch, "fake_trail", CAP=60, RACE="trail")
    assert ideas._load(plain).race_shape == "fixed"
    assert ideas._load(trail).race_shape == "trail"


def test_load_refuses_a_trail_module_with_a_short_cap(monkeypatch):
    short = _fake_module(monkeypatch, "fake_short_trail", CAP=20, RACE="trail")
    with pytest.raises(ValueError, match="at least 60"):
        ideas._load(short)
```

(`importlib.import_module` returns a module already in `sys.modules`, so the fakes need no file on disk; `monkeypatch.setitem` removes them after each test.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'RACE_SHAPES'`, `AttributeError: 'Idea' object has no attribute 'race_shape'`, `TypeError: ... unexpected keyword argument 'race_shape'`. The six pre-existing tests still pass.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/backtesting/screen/ideas/__init__.py`, replace the module docstring (lines 1-6) with:

```python
"""The v140 idea registry: one frozen trigger per published effect.

A trigger module exports CAP, PARAMS, SUMMARY, SOURCE and events(df), and
optionally RACE: "fixed" (the default: entry next open, 1.5/3 ATR stop and
target) or "trail" (v163: chandelier 3 ATR trail, no target, CAP >= 60). A
changed parameter or a changed race shape is a new idea with a new name (and
a new ledger row), never an edit here: each idea is screened once, under one
shape.
"""
```

After `IDEA_MODULES` (ends line 19), add:

```python

#: The race shapes an idea may declare (v163 spec § One shape per idea).
RACE_SHAPES = ("fixed", "trail")
#: With no target, the cap does the target's job: a trail idea freezes at
#: least this many bars (the longest fixed cap, high52w).
TRAIL_MIN_CAP = 60
```

Replace the `Idea` class (lines 22-37) with:

```python
@dataclass(frozen=True)
class Idea:
    name: str
    events: Callable[[pd.DataFrame], pd.Series]
    time_cap_bars: int
    direction: str = "long"
    params: Mapping = field(default_factory=dict)
    summary: str = ""
    source: str = ""
    race_shape: str = "fixed"

    def __post_init__(self):
        if self.direction != "long":
            raise ValueError(f"{self.name}: v140 screens long ideas only")
        if self.time_cap_bars < 1:
            raise ValueError(f"{self.name}: time cap must be at least one bar")
        if self.race_shape not in RACE_SHAPES:
            raise ValueError(f"{self.name}: race shape {self.race_shape!r} is not "
                             f"one of {RACE_SHAPES}")
        if self.race_shape == "trail" and self.time_cap_bars < TRAIL_MIN_CAP:
            raise ValueError(f"{self.name}: a trail idea freezes a time cap of at "
                             f"least {TRAIL_MIN_CAP} bars, not {self.time_cap_bars}")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
```

Replace `_load` (lines 40-44) with:

```python
def _load(name: str) -> Idea:
    module = importlib.import_module(f"{__name__}.{name}")
    return Idea(name=name, events=module.events, time_cap_bars=module.CAP,
                params=module.PARAMS, summary=module.SUMMARY,
                source=module.SOURCE,
                race_shape=getattr(module, "RACE", "fixed"))
```

No trigger module under `ideas/` changes: the six declare no `RACE` and stay `fixed`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS, 0 failed, 0 xfailed.

Then the screen-script tests, which build `Idea`s through the registry (unchanged behaviour for fixed ideas):

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: PASS.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/swingbot/core/backtesting/screen/ideas/__init__.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_ideas_registry.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): Idea.race_shape, RACE_SHAPES and the trail cap floor; pin every idea's shape" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged by this task.

### Task V163-2: Append trail outcome codes, per-shape outcome table, per-shape arms rendering; fixed doc + ledger byte-identity pins

**Model:** sonnet — a characterization pin captured verbatim below plus a two-function signature change; no new logic.

**Files:**
- Modify: `swingbot/core/backtesting/screen/race.py` (docstring lines 1-10, `OUTCOMES` line 23)
- Modify: `scripts/backtest/screen_idea.py` (`_mix` lines 302-305, `_render_arms` lines 308-315, `render_results` lines 346-351)
- Modify: `tests/backtesting/screen/test_race.py` (additions only)
- Modify: `tests/scripts/test_screen_idea.py` (additions only)

**Interfaces:**
- Consumes: `Idea.race_shape` (V163-1).
- Produces (ledger contract, final):
  - `race.OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout", "trail", "gap_trail")` — `trail` is code 5, `gap_trail` code 6. V163-3's `_first_exit_trail` emits them.
  - `race.SHAPE_OUTCOMES: dict[str, tuple[str, ...]] = {"fixed": OUTCOMES[:5], "trail": ("gap_stop", "stop", "gap_trail", "trail", "timeout")}` — the outcomes each shape can produce, in table order.
  - `screen_idea._mix(outcomes: Counter, names: tuple) -> list`
  - `screen_idea._render_arms(summary: dict, names: tuple) -> list`
  - `render_results` passes `race.SHAPE_OUTCOMES[idea.race_shape]` to `_render_arms`.
  - In `tests/scripts/test_screen_idea.py`: helper `_fixed_doc_inputs() -> tuple[Idea, dict, Universe, dict]` and literals `FIXED_DOC: str`, `FIXED_HYPOTHESIS: str`. V163-6 re-runs these pins after it rewrites the trade line and the ledger hypothesis; they must never be edited by a later task.

**Why the pin comes first.** `_mix` and `_render_arms` iterate the global `race.OUTCOMES`. Appending two codes would silently add two `0` rows to every fixed idea's "Both arms" table. The literals below were rendered from `render_results` / `ledger_row` on `main` at `7fcccfed` (screen code identical to `316c57e9`: `git diff --stat 316c57e9 7fcccfed -- swingbot/core/backtesting/screen scripts/backtest/screen_idea.py` is empty), before any change. Paste them exactly; do not regenerate them from the changed code.

- [ ] **Step 1: Write the byte-identity pins (characterization, expected to pass on unchanged code)**

In `$WT/tests/scripts/test_screen_idea.py`, append at the end of the file (the existing `stats` import at line 142 is reused):

```python
# --- v163: a fixed idea's results doc and ledger row stay byte-identical ---

from swingbot.core.backtesting.screen import race  # noqa: E402


def _fixed_doc_inputs():
    """A hand-built fixed-idea summary: every section of the doc renders and
    nothing depends on a bootstrap or a cache."""
    idea = IDEAS["gap_volume"]
    per_year = {year: (40 + year - 2011, 0.01 * (year - 2015)) for year in verdict.YEARS}
    v = verdict.Verdict("SCREEN-FAIL", 412, 0.031234567, -0.01, 0.07, 0.2345678, 4,
                        per_year, {"exp_r": False, "ci": False, "years": False, "n": True})
    summary = {
        "verdict": v,
        "counters": Counter(dropped_nonmember=7, dropped_warmup=11, dropped_window=2,
                            skipped_overlap=5, dropped_no_match=1),
        "skipped": Counter(empty_frame=1),
        "event_outcomes": Counter(gap_stop=12, stop=200, target=150, timeout=50),
        "null_outcomes": Counter(gap_stop=200, gap_target=40, stop=4000, target=2900,
                                 timeout=1100),
        "mean_r_event": 0.1234567, "mean_r_null": 0.0921,
        "drift": {5: (412, 0.05), 10: (412, -0.02), 20: (410, None), 60: (0, None)},
        "rank": {5: {2011: 0.01, 2012: -0.03}, 10: {2011: None, 2012: 0.02}},
    }
    universe = screen_idea.Universe(intervals={}, members=["AAA", "BBB", "ZZZ"],
                                    cached=["AAA", "BBB"], missing=["ZZZ"])
    run = {"ledger_id": "screen-gap_volume", "q": 0.1234, "date": "2026-10-09",
           "start": "2010-01-01", "end": "2019-12-31", "slippage_bps": 5.0,
           "commission": 0.02}
    return idea, summary, universe, run


# Rendered on main @ 7fcccfed (screen code == 316c57e9), before v163. Never edit.
FIXED_DOC = (
    '# v140 screen: `gap_volume` -> SCREEN-FAIL\n'
    '\n'
    '**Ledger id:** `screen-gap_volume` (instrument `screen-v1`); BH q = 0.1234 across the ledger (reported, never gating).\n'
    '\n'
    '**Run:** 2026-10-09; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea gap_volume`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.\n'
    '\n'
    '**Trigger:** open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar mean volume ending the prior bar, close >= open (earnings/news gap drift; volume as the news proxy); params gap_atr=1.0, atr_n=14, volume_mult=2.0, volume_window=50; time cap 20 bars; long only.\n'
    '\n'
    '**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.\n'
    '\n'
    '**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`\n'
    '\n'
    '## Universe and counters\n'
    '\n'
    '| | count |\n'
    '|---|---|\n'
    '| point-in-time S&P 500 members in the window | 3 |\n'
    '| cached and screened | 2 |\n'
    '| missing from the cache (survivorship that remains) | 1 |\n'
    '| cached but empty inside the window | 1 |\n'
    '| raw events | 438 |\n'
    '| `dropped_nonmember` | 7 |\n'
    '| `dropped_warmup` | 11 |\n'
    '| `dropped_window` | 2 |\n'
    '| `skipped_overlap` | 5 |\n'
    '| `dropped_no_match` | 1 |\n'
    '| **kept events (N)** | **412** |\n'
    '\n'
    'PIT members missing from the cache: ZZZ.\n'
    '\n'
    '## Verdict: SCREEN-FAIL\n'
    '\n'
    '| Clause | Measured | Rule | Holds |\n'
    '|---|---|---|---|\n'
    '| ΔExpR = mean(R_event − mean R_null) | +0.0312R | ≥ +0.10R | **no** |\n'
    '| lower 95% bound, week-clustered bootstrap | -0.0100R (upper +0.0700R) | > 0 | **no** |\n'
    '| years with mean(d) > 0 | 4 of 9 | ≥ 7 | **no** |\n'
    '| kept events N | 412 | ≥ 300 | yes |\n'
    '\n'
    'One-sided bootstrap p (share of resamples ≤ 0): 0.2346. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.\n'
    '\n'
    '## Both arms\n'
    '\n'
    "Mean R_event +0.1235R; mean R_null (each event's null mean, averaged) +0.0921R. Both after costs.\n"
    '\n'
    '| Exit | event arm | null arm |\n'
    '|---|---|---|\n'
    '| gap_stop | 12 (2.9%) | 200 (2.4%) |\n'
    '| gap_target | 0 (0.0%) | 40 (0.5%) |\n'
    '| stop | 200 (48.5%) | 4000 (48.5%) |\n'
    '| target | 150 (36.4%) | 2900 (35.2%) |\n'
    '| timeout | 50 (12.1%) | 1100 (13.3%) |\n'
    '\n'
    '## Per year\n'
    '\n'
    '| Year | N | mean(d) |\n'
    '|---|---|---|\n'
    '| 2011 | 40 | -0.0400R |\n'
    '| 2012 | 41 | -0.0300R |\n'
    '| 2013 | 42 | -0.0200R |\n'
    '| 2014 | 43 | -0.0100R |\n'
    '| 2015 | 44 | +0.0000R |\n'
    '| 2016 | 45 | +0.0100R |\n'
    '| 2017 | 46 | +0.0200R |\n'
    '| 2018 | 47 | +0.0300R |\n'
    '| 2019 | 48 | +0.0400R |\n'
    '\n'
    '## Forward drift (reported, never gating)\n'
    '\n'
    'Mean excess forward return in ATR14 units from the signal close, event minus its matched null.\n'
    '\n'
    '| h (bars) | events | mean excess (ATR) |\n'
    '|---|---|---|\n'
    '| 5 | 412 | +0.0500 |\n'
    '| 10 | 412 | -0.0200 |\n'
    '| 20 | 410 | n/a |\n'
    '| 60 | 0 | n/a |\n'
    '\n'
    'Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:\n'
    '\n'
    '| Year | h=5 | h=10 |\n'
    '|---|---|---|\n'
    '| 2011 | +0.0100 | n/a |\n'
    '| 2012 | -0.0300 | +0.0200 |\n'
)

FIXED_HYPOTHESIS = (
    'gap_volume: open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar mean volume ending the prior bar'
    ', close >= open; fixed 1.5/3.0 ATR race vs K=20 matched null, cap 20, PIT S&P 500 2010-2019, after costs (v140 screen)')


def test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140():
    idea, summary, universe, run = _fixed_doc_inputs()
    assert idea.race_shape == "fixed"
    assert screen_idea.render_results(idea, summary, universe, run) == FIXED_DOC


def test_a_fixed_idea_ledger_row_is_unchanged():
    idea, summary, _, _ = _fixed_doc_inputs()
    row = screen_idea.ledger_row(idea, summary["verdict"], "docs/x.md", "2026-10-09")
    stats.validate_ledger_row(row)
    assert row == {"id": "screen-gap_volume", "date": "2026-10-09",
                   "hypothesis": FIXED_HYPOTHESIS, "instrument": "screen-v1",
                   "n": 412, "exp_r": 0.0312, "p": 0.2346,
                   "verdict": "SCREEN-FAIL", "record": "docs/x.md"}
```

The file is UTF-8 already (it is read by pytest as UTF-8); the `Δ`, `−`, `≥`, `≤` characters in `FIXED_DOC` are the ones `_render_verdict` writes.

- [ ] **Step 2: Run the pins on unchanged code**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: PASS, including both new tests. A failure here means the literal was mistyped or the code is not the one it was captured from: fix the paste against this plan, never by regenerating the literal.

- [ ] **Step 3: Write the failing tests for the codes and the per-shape table**

Append to `$WT/tests/backtesting/screen/test_race.py`:

```python
from tests.backtesting.screen.helpers import random_walk  # noqa: E402


def test_trail_codes_are_appended_so_fixed_codes_keep_their_indices():
    assert race_mod.OUTCOMES[:5] == ("gap_stop", "gap_target", "stop", "target", "timeout")
    assert race_mod.OUTCOMES.index("trail") == 5
    assert race_mod.OUTCOMES.index("gap_trail") == 6
    assert race_mod.SHAPE_OUTCOMES == {
        "fixed": ("gap_stop", "gap_target", "stop", "target", "timeout"),
        "trail": ("gap_stop", "stop", "gap_trail", "trail", "timeout")}


def test_a_fixed_race_never_produces_a_trail_outcome():
    df = random_walk(400)
    out = race_mod.race(df, np.arange(20, 380, 7), 10)
    assert len(out) and set(out.outcome.tolist()) <= set(race_mod.SHAPE_OUTCOMES["fixed"])


def test_an_empty_result_still_has_string_outcomes():
    assert race_mod.RaceResult.empty().outcome.dtype.kind == "U"
```

Append to `$WT/tests/scripts/test_screen_idea.py` (below the Step 1 block):

```python
def test_mix_lists_one_cell_per_outcome_of_the_shape():
    fixed = screen_idea._mix(Counter(stop=3, target=1), race.SHAPE_OUTCOMES["fixed"])
    assert fixed == ["0 (0.0%)", "0 (0.0%)", "3 (75.0%)", "1 (25.0%)", "0 (0.0%)"]
    assert screen_idea._mix(Counter(), race.SHAPE_OUTCOMES["trail"]) == ["0"] * 5


def test_render_arms_lists_only_the_shape_outcomes():
    summary = {"mean_r_event": 0.5, "mean_r_null": 0.1,
               "event_outcomes": Counter(trail=2, gap_trail=1, stop=1),
               "null_outcomes": Counter(timeout=4)}
    rows = [line for line in screen_idea._render_arms(summary, race.SHAPE_OUTCOMES["trail"])
            if line.startswith("| ") and not line.startswith("| Exit")]
    assert [row.split(" | ")[0][2:] for row in rows] == [
        "gap_stop", "stop", "gap_trail", "trail", "timeout"]
    fixed = screen_idea._render_arms(summary, race.SHAPE_OUTCOMES["fixed"])
    assert not any("trail" in line for line in fixed)
```

- [ ] **Step 4: Run them to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_race.py`
Expected: FAIL — `ValueError: tuple.index(x): x not in tuple` and `AttributeError: module ... has no attribute 'SHAPE_OUTCOMES'`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: FAIL — `AttributeError: ... 'SHAPE_OUTCOMES'` (and `_mix() takes 1 positional argument but 2 were given`).

- [ ] **Step 5: Implement**

In `$WT/swingbot/core/backtesting/screen/race.py`, add one paragraph at the end of the module docstring (before the closing `"""` on line 10):

```python

Outcome codes index OUTCOMES. v163 appended ``trail`` (5) and ``gap_trail``
(6) for the trail race (``trail.py``); a fixed race never produces them, a
trail race never produces ``gap_target`` or ``target``. SHAPE_OUTCOMES is
each shape's own list, in table order, so a fixed idea's results doc keeps
its five rows.
```

Replace line 23 (`OUTCOMES = (...)`) with:

```python
OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout",
            "trail", "gap_trail")
SHAPE_OUTCOMES: dict[str, tuple[str, ...]] = {
    "fixed": OUTCOMES[:5],
    "trail": ("gap_stop", "stop", "gap_trail", "trail", "timeout"),
}
```

`RaceResult.empty()`, `_first_exit` (codes 0-4) and `race` are untouched.

In `$WT/scripts/backtest/screen_idea.py`, replace `_mix` and `_render_arms` (lines 302-315) with:

```python
def _mix(outcomes: Counter, names: tuple) -> list:
    total = sum(outcomes.values())
    return [f"{outcomes.get(name, 0)} ({100.0 * outcomes.get(name, 0) / total:.1f}%)"
            if total else "0" for name in names]


def _render_arms(summary, names: tuple) -> list:
    """``names``: the idea's own outcomes (race.SHAPE_OUTCOMES[shape])."""
    lines = ["## Both arms", "",
             f"Mean R_event {_fmt(summary['mean_r_event'])}R; mean R_null (each event's "
             f"null mean, averaged) {_fmt(summary['mean_r_null'])}R. Both after costs.", "",
             "| Exit | event arm | null arm |", "|---|---|---|"]
    lines += [f"| {name} | {e} | {n} |" for name, e, n in
              zip(names, _mix(summary["event_outcomes"], names),
                  _mix(summary["null_outcomes"], names))]
    return lines
```

and in `render_results` (lines 346-351) change only the `_render_arms(summary)` call:

```python
def render_results(idea, summary, universe, run) -> str:
    v = summary["verdict"]
    sections = [_render_head(idea, v, run), _render_universe(universe, summary),
                _render_verdict(v), _render_arms(summary, race.SHAPE_OUTCOMES[idea.race_shape]),
                _render_years(v), _render_drift(summary)]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"
```

`git -C $WT grep -n "_mix(\|_render_arms(" -- scripts tests` must show no other caller.

- [ ] **Step 6: Run the tests to verify they pass**

Run each (all must PASS, 0 failed, 0 xfailed):

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_race.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py
```

`test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140` passing **after** the `OUTCOMES` change is the point of this task.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/swingbot/core/backtesting/screen/race.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_idea.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add swingbot/core/backtesting/screen/race.py scripts/backtest/screen_idea.py tests/backtesting/screen/test_race.py tests/scripts/test_screen_idea.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): append trail outcome codes; render each shape's own outcomes; pin a fixed idea's doc and ledger row" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree unchanged by this task.

### Task V163-3: Trail race: `trail.py` with `race_trail`, `trail_stops`, `_first_exit_trail`

**Model:** opus — new vectorised numerics with a lookahead hazard (per-row, per-bar stop matrix, `-inf` fill, strict `raised_j`); `no-lookahead` skill territory.

**Files:**
- Create: `swingbot/core/backtesting/screen/trail.py`
- Create: `tests/backtesting/screen/test_trail.py`

**Interfaces:**
- Consumes: `race.OUTCOMES` with `trail` at index 5 and `gap_trail` at 6, and `race.SHAPE_OUTCOMES` (V163-2); existing `race.STOP_ATR = 1.5`, `race.RaceResult` (+ `.empty()`, `.take()`), `race._check_positions(event_pos, cap, n)`, `indicators.atr(df)`, `frictions.apply_frictions(fill_price, side, slippage_bps=None)`, `frictions.commission_r()`.
- Produces (ledger contract, final):
  - `trail.TRAIL_ATR = 3.0`
  - `trail.trail_stops(h: np.ndarray, entry: np.ndarray, risk: np.ndarray) -> np.ndarray` — `h` is rows × cap (column 0 = bar t+1); returns the same shape, `stop[:, j]` = the stop in force on bar column j.
  - `trail._first_exit_trail(O, H, L, C, stops, initial) -> tuple[np.ndarray, np.ndarray, np.ndarray]` — exit price, code into `race.OUTCOMES`, bar column j.
  - `trail.race_trail(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None) -> race.RaceResult` — same signature and result shape as `race.race`. V163-4's `race.race_for("trail")` returns it.

**Rule being implemented (spec § The trail race, verbatim in the index's Global Constraints).** Entry open of t+1; 1R = 1.5 × ATR14[t]; initial stop entry − 1R; no target; `stop_j = max(entry − 1R, max(High[t+1 .. j−1]) − 3 × ATR14[t])`. The trail distance is written `TRAIL_ATR / STOP_ATR × risk` (= 2 × 1R = 3 × ATR14[t]) because `risk` is what the race carries. Exits on bar j in order, `raised_j = stop_j > entry − 1R` strictly: open ≤ `stop_j` → open, `gap_stop`/`gap_trail`; else low ≤ `stop_j` → `stop_j[row, j]`, `stop`/`trail`; none by t+cap → close of t+cap, `timeout`. `r` always over the initial 1R. **Import direction:** `trail` imports `race`; `race` must never import `trail` at module level (V163-4 imports it lazily).

**Fixture arithmetic** (ATR 2.0 everywhere, so 1R = 3.0, initial stop 97, trail 6.0 below the highest prior high): after `UP1` (high 104) the next stop is 98, after `UP2` (108) 102, after `UP3` (110) 104. These numbers are asserted below.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/backtesting/screen/test_trail.py`:

```python
"""v163 trail race: chandelier 3 ATR trailing stop, no target, gaps at the open."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.backtesting.screen import trail
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)     # high 101 - 6 = 95 never lifts the stop off 97
UP1 = (100.0, 104.0, 99.5, 103.0)       # stop on the next bar: 104 - 6 = 98
UP2 = (103.0, 108.0, 102.5, 107.0)      # next: 108 - 6 = 102
UP3 = (107.0, 110.0, 105.0, 106.0)      # next: 110 - 6 = 104


def _frame(bars):
    """Bar 0 is the signal bar; ``bars`` are (O, H, L, C) for bars 1.."""
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)   # 1R = 3.0: initial stop 97, trail 6.0 below the high


def _one(bars, cap, **costs):
    df = _frame(bars)
    costs.setdefault("slippage_bps", 0.0)
    costs.setdefault("commission", 0.0)
    return trail.race_trail(df, [0], cap, atr=_atr(df), **costs)


def _stops(highs, entry=100.0, risk=3.0):
    return trail.trail_stops(np.array([highs], dtype=float), np.array([entry]),
                             np.array([risk]))[0]


def test_the_stop_ratchets_on_prior_highs_only():
    assert trail.TRAIL_ATR == 3.0
    assert _stops([104.0, 108.0, 110.0, 109.0]).tolist() == [97.0, 98.0, 102.0, 104.0]


def test_the_stop_never_moves_down():
    stops = _stops([104.0, 108.0, 103.0, 101.0, 99.0])
    assert stops.tolist() == [97.0, 98.0, 102.0, 102.0, 102.0]
    assert (np.diff(stops) >= 0).all()


def test_the_first_bar_carries_the_initial_stop_not_nan():
    stops = _stops([150.0, 100.0])
    assert np.isfinite(stops).all()
    assert stops.tolist() == [97.0, 144.0]


def test_a_later_high_never_changes_an_earlier_stop():
    """No lookahead: column j reads columns 0..j-1 only."""
    highs = np.array([104.0, 108.0, 110.0, 109.0, 111.0])
    base = _stops(highs)
    for j in range(len(highs)):
        bumped = highs.copy()
        bumped[j:] += 50.0
        assert _stops(bumped)[: j + 1].tolist() == base[: j + 1].tolist()


def test_a_reversal_exits_as_trail_at_the_raised_stop():
    out = _one([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET], cap=5)
    assert out.outcome.tolist() == ["trail"]
    assert out.exit_pos.tolist() == [4]
    assert out.gross_r.tolist() == [pytest.approx((104.0 - 100.0) / 3.0)]
    assert out.risk.tolist() == [3.0]        # r stays in the initial 1R


def test_an_exit_at_the_unraised_stop_is_labelled_stop():
    out = _one([QUIET, (99.0, 99.5, 96.5, 97.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["stop"]
    assert out.exit_pos.tolist() == [2]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]


def test_the_first_bar_touching_the_initial_stop_exits():
    out = _one([(100.0, 100.5, 96.5, 98.0), QUIET], cap=2)
    assert out.outcome.tolist() == ["stop"]
    assert out.exit_pos.tolist() == [1]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]


def test_a_gap_through_the_initial_stop_exits_at_the_open():
    out = _one([QUIET, (95.0, 96.0, 94.0, 95.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r.tolist() == [pytest.approx(-5.0 / 3.0)]


def test_a_gap_through_a_raised_stop_is_gap_trail_and_can_be_a_gain():
    out = _one([UP1, UP2, UP3, (103.0, 103.5, 101.0, 102.0), QUIET], cap=5)
    assert out.outcome.tolist() == ["gap_trail"]
    assert out.exit_pos.tolist() == [4]
    assert out.gross_r.tolist() == [pytest.approx(1.0)]       # open 103, entry 100


def test_a_stop_equal_to_the_initial_stop_is_not_raised():
    """raised_j is strict: a high exactly 1R above entry (103 - 6 = 97)
    leaves the stop where it was, so the exit is still a plain stop."""
    out = _one([(100.0, 103.0, 99.0, 100.0), (100.0, 100.0, 96.0, 97.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["stop"]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]


def test_no_exit_by_the_cap_is_a_timeout_at_the_cap_close():
    out = _one([QUIET, QUIET, (100.0, 101.0, 99.0, 100.5), QUIET], cap=3)
    assert out.outcome.tolist() == ["timeout"]
    assert out.exit_pos.tolist() == [3]
    assert out.gross_r.tolist() == [pytest.approx(0.5 / 3.0)]


def test_a_bar_own_high_never_raises_its_own_stop():
    """Bar 2's high 112 would put its stop at 106, above its low 101: it
    must not. Bar 3 is the first bar that stop is in force on."""
    out = _one([QUIET, (100.0, 112.0, 101.0, 111.0), (111.0, 111.5, 105.5, 110.0),
                (110.0, 111.0, 109.0, 110.0)], cap=4)
    assert out.outcome.tolist() == ["trail"]
    assert out.exit_pos.tolist() == [3]
    assert out.gross_r.tolist() == [pytest.approx(2.0)]       # stop 106, entry 100


def test_costs_are_slippage_on_both_fills_plus_commission_in_r():
    out = _one([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET], cap=5,
               slippage_bps=5.0, commission=0.02)
    entry_fill, exit_fill = 100.0 * 1.0005, 104.0 * 0.9995
    assert out.r[0] == pytest.approx((exit_fill - entry_fill) / 3.0 - 0.02)


def test_default_costs_come_from_config(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    df = _frame([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET])
    out = trail.race_trail(df, [0], 5, atr=_atr(df))
    assert out.r[0] == pytest.approx(4.0 / 3.0 - 0.02)


def test_a_race_that_would_read_past_the_frame_is_refused():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError):
        trail.race_trail(df, [0], 3, atr=_atr(df))


def test_no_events_is_an_empty_result():
    df = _frame([QUIET, QUIET])
    out = trail.race_trail(df, [], 2, atr=_atr(df))
    assert len(out) == 0 and out.r.size == 0


def test_several_events_race_independently_at_once():
    df = _frame([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET, QUIET, QUIET])
    both = trail.race_trail(df, [0, 2], 5, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    for k, pos in enumerate([0, 2]):
        alone = trail.race_trail(df, [pos], 5, atr=_atr(df), slippage_bps=0.0,
                                 commission=0.0)
        assert both.take(np.array([k])).r.tolist() == alone.r.tolist()
        assert both.exit_pos[k] == alone.exit_pos[0]


def _perturb_after(df, pos):
    out = df.copy()
    rng = np.random.default_rng(99)
    scale = rng.uniform(0.5, 1.5, len(out) - pos - 1)
    for col in ("Open", "High", "Low", "Close"):
        out.iloc[pos + 1:, out.columns.get_loc(col)] *= scale
    return out


def test_a_bar_after_the_exit_does_not_change_the_race():
    """No lookahead on a fixture: rewrite every bar after the exit."""
    df = _frame([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET, QUIET])
    a = trail.race_trail(df, [0], 6, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    changed = _perturb_after(df, int(a.exit_pos[0]))
    b = trail.race_trail(changed, [0], 6, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    assert (a.r.tolist(), a.exit_pos.tolist(), a.outcome.tolist()) == (
        b.r.tolist(), b.exit_pos.tolist(), b.outcome.tolist())


def test_no_lookahead_on_a_random_walk():
    df = random_walk(900)
    atr = indicators.atr(df)
    events = np.arange(30, 820, 37)
    full = trail.race_trail(df, events, 60, atr=atr, slippage_bps=0.0, commission=0.0)
    for k, pos in enumerate(events):
        changed = _perturb_after(df, int(full.exit_pos[k]))
        one = trail.race_trail(changed, [pos], 60, atr=atr, slippage_bps=0.0,
                               commission=0.0)
        assert one.r[0] == pytest.approx(full.r[k], abs=1e-12)
        assert (one.exit_pos[0], one.outcome[0]) == (full.exit_pos[k], full.outcome[k])


def test_a_random_walk_race_is_never_stop_less_and_never_fixed_only():
    df = random_walk(900)
    atr = indicators.atr(df)
    events = np.arange(30, 820, 11)
    o, h = df["Open"].to_numpy(), df["High"].to_numpy()
    bars = events[:, None] + 1 + np.arange(60)[None, :]
    entry, risk = o[events + 1], race_mod.STOP_ATR * atr.to_numpy()[events]
    stops = trail.trail_stops(h[bars], entry, risk)
    assert np.isfinite(stops).all() and (stops >= (entry - risk)[:, None]).all()
    out = trail.race_trail(df, events, 60, atr=atr, slippage_bps=0.0, commission=0.0)
    assert set(out.outcome.tolist()) <= set(race_mod.SHAPE_OUTCOMES["trail"])
    assert {"trail", "timeout"} & set(out.outcome.tolist())
    assert (out.risk == risk).all()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_trail.py`
Expected: FAIL — `ImportError: cannot import name 'trail' from 'swingbot.core.backtesting.screen'`.

- [ ] **Step 3: Implement**

Create `$WT/swingbot/core/backtesting/screen/trail.py`:

```python
"""The v163 trail race: a chandelier 3 ATR trailing stop, no target. Long only.

Event on bar t (known at t's close). Entry = open of t+1; 1R = 1.5 x
ATR14[t]; initial stop = entry - 1R; no target. The stop in force on bar j
(j >= t+1) is

    stop_j = max(entry - 1R, max(High[t+1 .. j-1]) - 3 x ATR14[t])

so bar j's own high never raises bar j's stop (a daily bar does not say
whether its high came before its low), the stop never moves down, and ATR is
frozen at t. On each bar, in order, with raised_j = stop_j > entry - 1R
(strictly): an open at/below stop_j exits at the open (gap_stop, or
gap_trail when raised: a gap through a raised stop can be a gain); else a
low at/below stop_j exits at stop_j (stop, or trail when raised). After bar
t+cap, exit at its close (timeout). r is always in the initial 1R. Costs as
the fixed race: both fills worsened by SLIPPAGE_BPS, then commission_r().
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.edge.frictions import apply_frictions, commission_r

TRAIL_ATR = 3.0
_GAP_STOP, _STOP, _TIMEOUT, _TRAIL, _GAP_TRAIL = (
    race_mod.OUTCOMES.index(name)
    for name in ("gap_stop", "stop", "timeout", "trail", "gap_trail"))


def trail_stops(h: np.ndarray, entry: np.ndarray, risk: np.ndarray) -> np.ndarray:
    """The stop in force on every bar column: ``h`` is rows x cap (column 0 is
    bar t+1). Column j reads the highs of columns 0..j-1 only; column 0's
    high term is -inf (never NaN, which would switch the stop off)."""
    prior = np.empty_like(h, dtype=float)
    prior[:, 0] = -np.inf
    prior[:, 1:] = h[:, :-1]
    running = np.maximum.accumulate(prior, axis=1)
    trail = running - (TRAIL_ATR / race_mod.STOP_ATR * risk)[:, None]
    return np.maximum((entry - risk)[:, None], trail)


def _first_exit_trail(O, H, L, C, stops, initial):
    """Exit price, outcome code (index into race.OUTCOMES) and bar column.
    ``stops`` is per row and per bar; the exit prices at ``stops[row, j]``."""
    del H  # the bar's own high never decides its exit (see trail_stops)
    gap = O <= stops
    hit = gap | (L <= stops)
    any_hit = hit.any(axis=1)
    rows = np.arange(len(O))
    j = np.where(any_hit, hit.argmax(axis=1), O.shape[1] - 1)
    gapped = gap[rows, j]
    raised = stops[rows, j] > initial
    code = np.where(gapped, np.where(raised, _GAP_TRAIL, _GAP_STOP),
                    np.where(raised, _TRAIL, _STOP))
    code = np.where(any_hit, code, _TIMEOUT)
    price = np.where(gapped, O[rows, j], stops[rows, j])
    price = np.where(any_hit, price, C[rows, j])
    return price, code, j


def race_trail(df: pd.DataFrame, event_pos, cap: int, *, atr=None,
               slippage_bps=None, commission=None) -> race_mod.RaceResult:
    """Race every event in ``event_pos`` (bar positions) at once."""
    event_pos = np.asarray(event_pos, dtype=int)
    race_mod._check_positions(event_pos, cap, len(df))
    if event_pos.size == 0:
        return race_mod.RaceResult.empty()
    atr_v = (indicators.atr(df) if atr is None else pd.Series(atr)).to_numpy(dtype=float)
    o, h, l, c = (df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low", "Close"))
    bars = event_pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[event_pos + 1]
    risk = race_mod.STOP_ATR * atr_v[event_pos]
    stops = trail_stops(h[bars], entry, risk)
    price, code, offset = _first_exit_trail(o[bars], h[bars], l[bars], c[bars],
                                            stops, entry - risk)
    cost = commission_r() if commission is None else commission
    net = (apply_frictions(price, "sell", slippage_bps)
           - apply_frictions(entry, "buy", slippage_bps)) / risk - cost
    return race_mod.RaceResult(event_pos, event_pos + 1 + offset, entry, risk,
                               (price - entry) / risk, net,
                               np.asarray(race_mod.OUTCOMES)[code])
```

Notes for the implementer:
- `_first_exit_trail` takes `H` so its signature mirrors `race._first_exit`, and drops it on purpose: the bar's own high has already been excluded by `trail_stops`. Do not use it.
- `code` values are looked up from `race.OUTCOMES` by name at import, never hard-coded, so the module cannot drift from V163-2's table.
- `price` at a touch is `stops[rows, j]` (the per-row, per-bar level), never `entry - risk`: `test_a_reversal_exits_as_trail_at_the_raised_stop` fails if it is.
- Do **not** touch `race.py` in this task.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_trail.py`
Expected: PASS, 20 passed, 0 failed, 0 xfailed.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (`trail.py` lives inside `screen/`; nothing outside `core/backtesting` imports it).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_race.py`
Expected: PASS, untouched by this task.

- [ ] **Step 5: Lookahead review**

Invoke the `no-lookahead` skill on `swingbot/core/backtesting/screen/trail.py`. The two facts it must confirm: `trail_stops` column j reads `h[:, :j]` only (`test_a_later_high_never_changes_an_earlier_stop`), and ATR is read at `event_pos` only (frozen at t). Record its conclusion in the commit body.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/swingbot/core/backtesting/screen/trail.py`
Expected: no output (`race_trail` A(5), `trail_stops` A(1), `_first_exit_trail` A(1)).

- [ ] **Step 7: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add swingbot/core/backtesting/screen/trail.py tests/backtesting/screen/test_trail.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): chandelier 3 ATR trail race with a per-bar stop matrix" -m "no-lookahead: stop_j reads highs of t+1..j-1 only; ATR frozen at t." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree unchanged by this task.

### Task V163-4: `race.race_for` dispatcher; `run_book` and `null.matched_null` take `shape`

**Model:** sonnet — a dispatcher and two keyword pass-throughs, fully specified; the only trap (an import cycle) is spelled out.

**Files:**
- Modify: `swingbot/core/backtesting/screen/race.py` (imports; new `race_for` after `non_overlapping`; `run_book`)
- Modify: `swingbot/core/backtesting/screen/null.py` (`matched_null`, lines 75-93 on `main`)
- Modify: `tests/backtesting/screen/test_race.py` (additions only)
- Modify: `tests/backtesting/screen/test_null.py` (additions only)

**Interfaces:**
- Consumes: `trail.race_trail` (V163-3); `race.SHAPE_OUTCOMES` (V163-2); `random_walk` already imported at the bottom of `test_race.py` by V163-2.
- Produces (ledger contract, final):
  - `race.race_for(shape: str) -> Callable[..., RaceResult]` — `"fixed"` → `race.race`, `"trail"` → `trail.race_trail`, anything else → `ValueError` whose message contains `race shape`.
  - `race.run_book(df, events, cap: int, *, member, warm, atr, slippage_bps=None, commission=None, shape: str = "fixed")` — returns `(RaceResult, counts)` as today.
  - `null.matched_null(df, event_pos, eligible, k: int, seed, *, cap: int, atr, trend, slippage_bps=None, commission=None, shape: str = "fixed") -> NullDraw` — the draw (`groups`, `event_pos`, `dropped_no_match`) does not depend on `shape`; only the race of the drawn bars does.
  - V163-5 calls both with `shape=idea.race_shape` from `scripts/backtest/screen_idea.py:screen_ticker`.

**Import cycle.** `trail.py` imports `race` at module level (V163-3). `race.py` must therefore import `trail` **inside** `race_for`, never at the top of the module (index deviation 3). Both functions resolve the shape **before** any work, so an unknown shape raises even when there is nothing to race.

**Fixed path unchanged.** With the default `shape="fixed"`, `run_book` and `matched_null` call exactly the function they call today (`race.race`); the new tests compare against the pre-v163 `run_book` body spelled out by hand. Existing tests in both files stay untouched and must pass.

- [ ] **Step 1: Write the failing tests**

Append to `$WT/tests/backtesting/screen/test_race.py` (after V163-2's additions; `_book_frame` and `_atr` are the existing helpers in this file):

```python
from swingbot.core.backtesting.screen import indicators  # noqa: E402
from swingbot.core.backtesting.screen import trail  # noqa: E402


def test_race_for_returns_each_shape_race_function():
    assert race_mod.race_for("fixed") is race_mod.race
    assert race_mod.race_for("trail") is trail.race_trail
    with pytest.raises(ValueError, match="race shape"):
        race_mod.race_for("donchian")


def _walk_book_inputs():
    df = random_walk(900)
    atr = indicators.atr(df)
    events = np.random.default_rng(5).random(len(df)) < 0.05
    member = np.ones(len(df), dtype=bool)
    warm = race_mod.warm_mask(atr, indicators.sma(df["Close"], 200))
    return df, events, member, warm, atr


def _book_by_hand(race_fn, df, events, cap, member, warm, atr):
    """The pre-v163 run_book body, spelled out with an explicit race function."""
    cand, counts = race_mod.candidate_events(events, member, warm, cap)
    raced = race_fn(df, cand, cap, atr=atr, slippage_bps=0.0, commission=0.0)
    keep = race_mod.non_overlapping(raced.event_pos, raced.exit_pos)
    counts["skipped_overlap"] = int((~keep).sum())
    return raced.take(keep), counts


def _same(a, b):
    return all(np.array_equal(getattr(a, name), getattr(b, name))
               for name in race_mod._FIELDS)


@pytest.mark.parametrize("shape", ["fixed", "trail"])
def test_run_book_races_through_the_shape_race(shape):
    df, events, member, warm, atr = _walk_book_inputs()
    race_fn = {"fixed": race_mod.race, "trail": trail.race_trail}[shape]
    got, counts = race_mod.run_book(df, events, 60, member=member, warm=warm, atr=atr,
                                    slippage_bps=0.0, commission=0.0, shape=shape)
    want, want_counts = _book_by_hand(race_fn, df, events, 60, member, warm, atr)
    assert len(got) > 5 and _same(got, want) and counts == want_counts


def test_run_book_without_a_shape_is_the_fixed_book():
    df, events, member, warm, atr = _walk_book_inputs()
    a, a_counts = race_mod.run_book(df, events, 10, member=member, warm=warm, atr=atr,
                                    slippage_bps=0.0, commission=0.0)
    b, b_counts = race_mod.run_book(df, events, 10, member=member, warm=warm, atr=atr,
                                    slippage_bps=0.0, commission=0.0, shape="fixed")
    assert _same(a, b) and a_counts == b_counts


def test_a_trail_book_counts_every_drop_and_skip_like_a_fixed_one():
    df = _book_frame()
    events = np.zeros(len(df), dtype=bool)
    events[[2, 4, 7, 9, 20, 27]] = True
    member = np.ones(len(df), dtype=bool)
    member[9] = False
    warm = np.ones(len(df), dtype=bool)
    warm[20] = False
    booked, counts = race_mod.run_book(
        df, events, 5, member=member, warm=warm, atr=_atr(df),
        slippage_bps=0.0, commission=0.0, shape="trail")
    assert booked.event_pos.tolist() == [2, 7]           # quiet bars: both time out
    assert booked.outcome.tolist() == ["timeout", "timeout"]
    assert counts == {"dropped_nonmember": 1, "dropped_warmup": 1,
                      "dropped_window": 1, "skipped_overlap": 1}


def test_run_book_refuses_an_unknown_shape_even_with_no_events():
    df = _book_frame()
    none = np.zeros(len(df), dtype=bool)
    with pytest.raises(ValueError, match="race shape"):
        race_mod.run_book(df, none, 5, member=~none, warm=~none, atr=_atr(df),
                          shape="donchian")
```

Append to `$WT/tests/backtesting/screen/test_null.py` (`_atr`, `_all`, `random_walk`, `race_mod` and `null` are already imported or defined in this file):

```python
from swingbot.core.backtesting.screen import trail  # noqa: E402


def _walk_null(shape=None):
    df = random_walk(400, start="2019-01-01")
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=60)
    shape_kw = {} if shape is None else {"shape": shape}
    draw = null.matched_null(df, [5, 30], eligible, 20, 3, cap=60, atr=_atr(df),
                             trend=_all(df), slippage_bps=0.0, commission=0.0, **shape_kw)
    return df, draw


def test_a_trail_null_races_the_same_draw_through_the_trail_race():
    _, fixed = _walk_null("fixed")
    df, drawn = _walk_null("trail")
    assert [g.tolist() for g in drawn.groups] == [g.tolist() for g in fixed.groups]
    for k, group in enumerate(drawn.groups):
        expected = trail.race_trail(df, group, 60, atr=_atr(df), slippage_bps=0.0,
                                    commission=0.0)
        assert drawn.null_mean_r[k] == pytest.approx(expected.r.mean())
    assert set(drawn.null_race.outcome.tolist()) <= set(race_mod.SHAPE_OUTCOMES["trail"])
    assert drawn.null_race.r.tolist() != fixed.null_race.r.tolist()


def test_matched_null_without_a_shape_is_the_fixed_null():
    _, default = _walk_null()
    _, fixed = _walk_null("fixed")
    assert default.null_mean_r.tolist() == fixed.null_mean_r.tolist()
    assert default.null_race.outcome.tolist() == fixed.null_race.outcome.tolist()


def test_matched_null_refuses_an_unknown_shape():
    with pytest.raises(ValueError, match="race shape"):
        _walk_null("donchian")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_race.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.backtesting.screen.race' has no attribute 'race_for'` and `TypeError: run_book() got an unexpected keyword argument 'shape'`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_null.py`
Expected: FAIL — `TypeError: matched_null() got an unexpected keyword argument 'shape'`.

- [ ] **Step 3: Implement `race_for` and `run_book(shape=)`**

In `$WT/swingbot/core/backtesting/screen/race.py`, add to the imports, after `from dataclasses import dataclass`:

```python
from typing import Callable
```

Insert, between `non_overlapping` and `run_book`:

```python
def race_for(shape: str) -> Callable[..., RaceResult]:
    """The race function of one shape: ``race`` (fixed) or
    ``trail.race_trail`` (v163). ``trail`` imports this module, so it is
    imported here, on first use, never at module level."""
    if shape == "fixed":
        return race
    if shape == "trail":
        from swingbot.core.backtesting.screen import trail
        return trail.race_trail
    raise ValueError(f"unknown race shape {shape!r}; expected one of "
                     f"{tuple(SHAPE_OUTCOMES)}")
```

Replace `run_book` (the last function in the file) with:

```python
def run_book(df, events, cap: int, *, member, warm, atr, slippage_bps=None,
             commission=None, shape: str = "fixed"):
    """Race the eligible events under ``shape``, then keep one open race at a
    time."""
    race_fn = race_for(shape)
    cand, counts = candidate_events(events, member, warm, cap)
    raced = race_fn(df, cand, cap, atr=atr, slippage_bps=slippage_bps,
                    commission=commission)
    keep = non_overlapping(raced.event_pos, raced.exit_pos)
    counts["skipped_overlap"] = int((~keep).sum())
    return raced.take(keep), counts
```

`race`, `_first_exit`, `candidate_events` and `non_overlapping` are untouched.

- [ ] **Step 4: Implement `matched_null(shape=)`**

In `$WT/swingbot/core/backtesting/screen/null.py`, replace `matched_null` (lines 75-93) with:

```python
def matched_null(df, event_pos, eligible, k: int, seed, *, cap: int, atr,
                 trend, slippage_bps=None, commission=None,
                 shape: str = "fixed") -> NullDraw:
    """``shape`` is the idea's race shape: a trail idea's null is a trail
    null (v163). The draw itself does not depend on it."""
    race_fn = race_mod.race_for(shape)
    rng = np.random.default_rng(seed)
    months = month_key(df.index)
    kept, groups, dropped = [], [], 0
    for pos in np.asarray(event_pos, dtype=int):
        pool = candidates(pos, eligible, months, trend)
        if len(pool) < MIN_CANDIDATES:
            dropped += 1
            continue
        kept.append(pos)
        groups.append(np.sort(rng.choice(pool, size=min(k, len(pool)), replace=False)))
    if not kept:
        return _empty(dropped)
    raced = race_fn(df, np.concatenate(groups), cap, atr=atr,
                    slippage_bps=slippage_bps, commission=commission)
    bounds = np.cumsum([len(g) for g in groups])[:-1]
    means = np.array([part.mean() for part in np.split(raced.r, bounds)])
    return NullDraw(np.asarray(kept, dtype=int), tuple(groups), means, raced, dropped)
```

The only changes against `main` are the `shape` keyword, the docstring, `race_fn = race_mod.race_for(shape)` as the first statement, and `race_fn(...)` in place of `race_mod.race(...)`. The rng is created after `race_for`, and `race_for` draws nothing from it, so a fixed null's draw is the same sequence as before.

- [ ] **Step 5: Run the tests to verify they pass**

Run each (all must PASS, 0 failed, 0 xfailed):

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_race.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_trail.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py
```

The last one proves the screen script (still calling without `shape=`) is unchanged, including V163-2's byte-identity pin.

Check there is no module-level import of `trail` in `race.py` (expected: one hit, indented, inside `race_for`):

Run: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race grep -n "import trail" -- swingbot/core/backtesting/screen/race.py`

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/swingbot/core/backtesting/screen/race.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/swingbot/core/backtesting/screen/null.py`
Expected: no output (`matched_null` stays B(6), `race_for` A(3)).

- [ ] **Step 7: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add swingbot/core/backtesting/screen/race.py swingbot/core/backtesting/screen/null.py tests/backtesting/screen/test_race.py tests/backtesting/screen/test_null.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): race_for dispatcher; run_book and matched_null race the idea's shape" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree unchanged by this task.

