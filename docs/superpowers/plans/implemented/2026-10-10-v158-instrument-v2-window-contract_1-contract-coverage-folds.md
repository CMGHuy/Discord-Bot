# v158 Instrument v2, phase 3: window contract and folds. Implementation Plan, part 1 (contract, coverage, folds)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief WC4` or `grep -n "^### Task WC4" -A 400 docs/superpowers/plans/2026-10-10-v158-instrument-v2-window-contract_1-contract-coverage-folds.md`.

**Spec:** [`docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md`](../specs/2026-10-06-v136-backtest-instrument-v2-design.md) (section 1 "Window contract and folds": v2 spans, Folds, Data precondition; "Testing": purge/embargo boundary trades)
**Index:** [`2026-10-10-v158-instrument-v2-window-contract_0-index.md`](2026-10-10-v158-instrument-v2-window-contract_0-index.md): header block, `## Where to work`, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints; the ledger's names, signatures and paths are the contract with parts 2 and 3.

**Tasks in this part:** WC1, WC2, WC3, WC4. WC1 lands first (every later task imports its fields). WC2 → WC3 are serial (WC3 runs WC2's script). WC4 needs only WC1 and may run in parallel with WC2/WC3 and with part 2's WC5/WC6 (disjoint files), at most 2 implementers at once.

Conventions used in every task (from the index's `## Where to work`):

- `$R` = `/home/user/Discord-Bot` (main tree, never edited by a task). `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v158-instrument-v2-window-contract` (branch `2026-10-10-v158-instrument-v2-window-contract`).
- Never `cd`. Use `git -C $WT ...` and `python $WT/scripts/dev/testrun.py file tests/...` (test paths resolve against `$WT`).
- After every commit: `git -C $R status --short` must print nothing new (the main tree is unchanged).
- Every new or changed function stays < complexity 15: `python -m radon cc -s -n C <files>` prints nothing.

# Phase A: Contract fields and the cache-coverage precondition

### Task WC1: Contract span, universe, fold and floor fields

**Model:** sonnet — additive dataclass fields with pinned values and a test rewrite; one module, no cross-package design.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/contract.py`
- Modify: `tests/backtesting/instrument/test_contract.py`

**Why:** spec section 1 makes `contract.py` the only place an instrument's spans, universe, fold scheme, purge/embargo and (partner decision 1) liquidity floor are defined. The new fields are keyword-with-default and appended after `cost_model`, so the positional `InstrumentSpec("v1", V1_FILLS, ZERO_COSTS)` and `InstrumentSpec("v2", V1_FILLS, ZERO_COSTS)` lines stay exactly as they are (v157 owns the `"v2"` line). The defaults are v1's values; v2's values are applied by `dataclasses.replace` in a separate statement after the `_SPECS` dict. No consumer reads the new fields yet, so `run_backtest(instrument=...)` behaviour is unchanged and `test_v1_golden.py` stays green.

Field semantics (written into the dataclass as comments):

| Field | v1 (default) | v2 | Meaning |
|---|---|---|---|
| `universe` | `None` | `"sp500_pit"` | universe name a v2 run must use; `None` = caller's choice (v1 today) |
| `research_start` / `research_end` | `"2020-01-01"` / `"2023-12-31"` | `"2010-01-01"` / `"2025-12-31"` | every TRAIN run, grid and fold measurement lies inside |
| `holdout_start` | `"2024-01-01"` | `"2026-01-01"` | first sealed day (v1: its VALIDATION start) |
| `fold_scheme` | `"none"` | `"anchored_yearly"` | how `folds.anchored_folds` (WC4) splits the research span |
| `fold_test_years` | `()` | `2014..2025` (12) | yearly test folds |
| `purge` | `False` | `True` | drop train trades still open at the test fold's start |
| `embargo_days` | `0` | `270` | global max holding days; per-horizon value via `folds.embargo_days_for` (WC4) |
| `train_window` / `validation_window` | `("2020-01-01", "2023-12-31")` / `("2024-01-01", "2025-12-31")` | `None` / `None` | v1-only script windows (partner decision 4); WC7 aliases scripts to them |
| `warmup_start` | `None` | `"2009-06-01"` | first bar the cache must hold for indicator warm-up (WC2) |
| `liquidity_floor` | `None` | `V2_LIQUIDITY_FLOOR` | causal PIT floor applied on the signal date (WC5) |

`V2_LIQUIDITY_FLOOR = LiquidityFloor(20_000_000.0, 5.0, 20)` equals the live floor's code defaults (`swingbot/config.py:794-801`, `UNIVERSE_MIN_DOLLAR_VOL` default `"20000000"`, `UNIVERSE_MIN_PRICE` default `"5.0"`, 20-day average) but is a frozen literal, never read from config (partner decision 1): an `.env` change must not move a research instrument.

- [ ] **Step 0: Create the worktree (first task of the plan only)**

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C /home/user/Discord-Bot worktree list
git -C /home/user/Discord-Bot worktree add -b 2026-10-10-v158-instrument-v2-window-contract /home/user/Discord-Bot/.claude/worktrees/2026-10-10-v158-instrument-v2-window-contract main
```

If `git worktree list` already shows the worktree, reuse it and resume at the first uncommitted task (`git -C $WT log --oneline main..HEAD`).

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/backtesting/instrument/test_contract.py`:

1. Replace the module docstring line with:

```python
"""v136 instrument contract: fill/cost fields (phase 1) and the window,
universe, fold and liquidity-floor fields (phase 3, v158)."""
```

2. Change the import block to:

```python
import dataclasses

import pytest

from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.instrument.contract import (V2_LIQUIDITY_FLOOR, CostModel,
                                                           FillModel, InstrumentSpec,
                                                           LiquidityFloor, resolve)
```

3. Replace `test_phase_one_carries_no_span_fields` (the whole function) with:

```python
SPAN_FIELDS = ["universe", "research_start", "research_end", "holdout_start", "fold_scheme",
               "fold_test_years", "purge", "embargo_days", "train_window", "validation_window",
               "warmup_start", "liquidity_floor"]


def test_span_fields_are_appended_after_the_fill_and_cost_fields():
    """Keyword-with-default fields after cost_model: the positional _SPECS lines
    (and v157's rewrite of the v2 one) never have to change."""
    assert [f.name for f in dataclasses.fields(InstrumentSpec)] == [
        "version", "fill_model", "cost_model", *SPAN_FIELDS]
    defaulted = {f.name for f in dataclasses.fields(InstrumentSpec)
                 if f.default is not dataclasses.MISSING}
    assert defaulted == set(SPAN_FIELDS)
```

4. Append these tests at the end of the file:

```python
def test_v1_window_fields_are_todays_literal_windows():
    """Partner decision 4: v1's TRAIN/VALIDATION live in the contract, unchanged."""
    spec = resolve("v1")
    assert spec.train_window == ("2020-01-01", "2023-12-31")
    assert spec.validation_window == ("2024-01-01", "2025-12-31")
    assert spec.research_span == ("2020-01-01", "2023-12-31")
    assert spec.holdout_start == "2024-01-01"


def test_v1_carries_no_universe_folds_floor_or_warmup():
    spec = resolve("v1")
    assert spec.universe is None
    assert spec.fold_scheme == "none"
    assert spec.fold_test_years == ()
    assert spec.purge is False
    assert spec.embargo_days == 0
    assert spec.warmup_start is None
    assert spec.liquidity_floor is None


def test_v1_spec_equals_a_spec_built_from_defaults_only():
    """The v1 line passes no span argument: every v1 value is a field default."""
    v1 = resolve("v1")
    assert v1 == InstrumentSpec("v1", v1.fill_model, v1.cost_model)


def test_v2_spans_are_the_spec_section_one_values():
    spec = resolve("v2")
    assert spec.universe == "sp500_pit"
    assert spec.research_span == ("2010-01-01", "2025-12-31")
    assert spec.holdout_start == "2026-01-01"
    assert spec.warmup_start == "2009-06-01"
    assert spec.train_window is None
    assert spec.validation_window is None


def test_v2_folds_are_twelve_yearly_test_years_with_four_training_years_first():
    spec = resolve("v2")
    assert spec.fold_scheme == "anchored_yearly"
    assert spec.fold_test_years == tuple(range(2014, 2026))
    assert len(spec.fold_test_years) == 12
    first_research_year = int(spec.research_start[:4])
    assert spec.fold_test_years[0] - first_research_year >= 4
    assert spec.fold_test_years[-1] == int(spec.research_end[:4])


def test_v2_purges_and_embargoes_by_the_longest_horizon():
    """Partner decision 2: the field is the global maximum holding period."""
    from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS
    spec = resolve("v2")
    assert spec.purge is True
    assert spec.embargo_days == max(HORIZONS[hk]["max_holding_days"] for hk in LEGACY_HORIZONS)
    assert spec.embargo_days == 270


def test_v2_liquidity_floor_is_the_frozen_live_default():
    """Partner decision 1: $20M average dollar volume, $5 close, 20 bars, frozen."""
    assert resolve("v2").liquidity_floor is V2_LIQUIDITY_FLOOR
    assert V2_LIQUIDITY_FLOOR == LiquidityFloor(min_avg_dollar_vol=20_000_000.0, min_price=5.0,
                                                lookback_bars=20)
    with pytest.raises(dataclasses.FrozenInstanceError):
        V2_LIQUIDITY_FLOOR.min_price = 1.0


def test_v2_keeps_its_fill_cost_and_constructor_fields_through_the_replace():
    """The dataclasses.replace after _SPECS touches only the phase-3 fields."""
    spec = resolve("v2")
    assert spec.version == "v2"
    assert spec.live_constructor is True
    assert spec.fill_model == contract.V1_FILLS or spec.fill_model.market_entry == "next_open"


def test_research_span_ends_before_the_holdout_for_every_instrument():
    for version in contract.VERSIONS:
        spec = resolve(version)
        start, end = spec.research_span
        assert start < end < spec.holdout_start
```

(The last assertion of `test_v2_keeps_its_fill_cost_and_constructor_fields_through_the_replace` accepts both the phase-1 stub and v157's `next_open` value, so whichever plan merges second does not have to touch it.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py`
Expected: FAIL, collection error `ImportError: cannot import name 'V2_LIQUIDITY_FLOOR'`.

- [ ] **Step 3: Implement the fields**

In `$WT/swingbot/core/backtesting/instrument/contract.py`:

1. Replace the docstring sentence `phase 3 adds the span, universe and fold fields.` (end of the second paragraph) with:

```text
phase 3 (v158) appends the span, universe, fold and liquidity-floor fields
after ``cost_model`` as keyword fields whose defaults are v1's values, and
sets v2's with ``dataclasses.replace`` below ``_SPECS``, so neither positional
``_SPECS`` line changes.
```

2. Change `from dataclasses import dataclass` to `from dataclasses import dataclass, replace`.

3. Insert after the `CostModel` class (before `InstrumentSpec`):

```python
@dataclass(frozen=True)
class LiquidityFloor:
    """Causal point-in-time liquidity floor (v158 partner decision 1): the
    average Close*Volume over the `lookback_bars` bars ending AT the signal
    bar, and that bar's close. Frozen here; never read from config."""

    min_avg_dollar_vol: float
    min_price: float
    lookback_bars: int
```

4. Replace the whole `InstrumentSpec` class with:

```python
@dataclass(frozen=True)
class InstrumentSpec:
    """One backtest instrument: fills and costs (phases 1-2), then the window,
    universe, fold and floor fields (phase 3). Every phase-3 field defaults to
    v1's value, so v1's spec is built from its three positional fields alone."""

    version: str
    fill_model: FillModel
    cost_model: CostModel
    # --- phase 3 (v158); defaults are v1 -------------------------------------
    universe: str | None = None             # v2: "sp500_pit"; None = the caller's choice
    research_start: str = "2020-01-01"      # every TRAIN run, grid and fold lies inside
    research_end: str = "2023-12-31"
    holdout_start: str = "2024-01-01"       # first sealed day (v1: its VALIDATION start)
    fold_scheme: str = "none"               # "none" | "anchored_yearly" (folds.py)
    fold_test_years: tuple[int, ...] = ()
    purge: bool = False                     # drop train trades open at the test start
    embargo_days: int = 0                   # global max; folds.embargo_days_for(hk) per horizon
    train_window: tuple[str, str] | None = ("2020-01-01", "2023-12-31")        # v1 only
    validation_window: tuple[str, str] | None = ("2024-01-01", "2025-12-31")   # v1 only
    warmup_start: str | None = None         # first bar the cache must hold (coverage.py)
    liquidity_floor: LiquidityFloor | None = None   # v2: causal floor on the signal date

    @property
    def live_constructor(self) -> bool:
        """Every plan is built by builders.build_strategy_plan (v136 rule 3).
        False only for the frozen v1 instrument."""
        return self.version != "v1"

    @property
    def research_span(self) -> tuple[str, str]:
        """(research_start, research_end), both inclusive ISO dates."""
        return (self.research_start, self.research_end)
```

5. Insert directly after the closing `}` of `_SPECS` and before `VERSIONS = tuple(_SPECS)`:

```python
V2_LIQUIDITY_FLOOR = LiquidityFloor(min_avg_dollar_vol=20_000_000.0, min_price=5.0,
                                    lookback_bars=20)

# v2's window, universe, fold and floor values (spec section 1). Applied here,
# not on the "v2" line above, so phase 2 (v157) and phase 3 never edit one line.
_V2_WINDOW = {
    "universe": "sp500_pit",
    "research_start": "2010-01-01",
    "research_end": "2025-12-31",
    "holdout_start": "2026-01-01",
    "fold_scheme": "anchored_yearly",
    "fold_test_years": tuple(range(2014, 2026)),
    "purge": True,
    "embargo_days": 270,   # 9m max_holding_days, the longest LEGACY_HORIZONS hold
    "train_window": None,
    "validation_window": None,
    "warmup_start": "2009-06-01",
    "liquidity_floor": V2_LIQUIDITY_FLOOR,
}
_SPECS["v2"] = replace(_SPECS["v2"], **_V2_WINDOW)
```

Leave both `_SPECS` entry lines, `V1_FILLS`, `ZERO_COSTS`, `FillModel`, `CostModel` and `resolve` untouched.

- [ ] **Step 4: Run the contract tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Prove v1 and every instrument consumer are unchanged**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/`
Expected: PASS, `0 failed`, `0 xfailed` (includes `test_v1_golden.py`, `test_constructor_parity.py`, `test_live_constructor_replay.py`).

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/contract.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/backtesting/instrument/contract.py tests/backtesting/instrument/test_contract.py
git -C $WT commit -m "feat(instrument): v158 WC1 window, universe, fold and floor fields on the contract"
git -C /home/user/Discord-Bot status --short
```

Expected: the last command shows no change made by this task in the main tree.

### Task WC2: Cache-coverage check

**Model:** sonnet — a self-contained reader plus a thin CLI over synthetic CSVs; the only trap (two OHLCV caches) is named below.

**Files:**
- Create: `swingbot/core/backtesting/instrument/coverage.py`
- Create: `scripts/data/check_cache_coverage.py`
- Create: `tests/backtesting/instrument/test_window_coverage.py`

**Why:** spec section 1, "Data precondition": phase 3 verifies that the OHLCV cache covers 2009-06 onward (indicator warm-up) for every PIT member, and **lists gaps rather than silently shrinking the universe**. The existing `fetch_backtest_data.write_coverage` only records fetch failures, not first-bar dates, so a new reader is needed. It reads only the first dated row of each CSV (a ~850-file scan stays fast) and the **backtest** cache (`swingbot.core.marketdata.backtest_cache`, `data/backtest_cache[_ext]/`), never `market_data/` (`docs/claude/known-traps.md`, two caches). `BACKTEST_CACHE_DIR` is read once at import, so the module takes `cache_dir` explicitly and the CLI defaults it to `backtest_cache.CACHE_DIR` with a `--cache-dir` override. The cache filename comes from `backtest_cache.cache_path(sym).name`, so the safe-name rule (`=`, `^`, `/` → `_`) is never duplicated.

Contract (index ledger): `first_bar_date(path: Path) -> str | None`; `CoverageReport(required_start, covered, late, missing)` with property `gaps -> int`; `research_members(spec) -> list[str]`; `check_coverage(symbols, required_start: str, cache_dir: Path) -> CoverageReport`; `render_markdown(report, first_membership: dict[str, str]) -> str`. CLI: `python scripts/data/check_cache_coverage.py --instrument v2 [--out PATH]`, exit 1 when `gaps > 0`. This task also adds `first_membership(spec, symbols) -> dict[str, str]` (consumed only by the CLI here) and the CLI's `--cache-dir` (used by WC3's Hetzner path).

Classification rule: a symbol is **covered** when its first dated row is on or before `required_start` (`spec.warmup_start`, `"2009-06-01"` for v2), **late** when it starts after it, **missing** when the CSV is absent or holds no dated row. A late symbol is not necessarily a defect (a 2015 IPO cannot have 2009 bars); the report shows each gap's first PIT membership date next to it so the partner can judge, and the check never drops anything.

`scripts/data/` is outside the WC11 date-literal guard's scope (`scripts/backtest/`); this script still defines no date and reads every date from the contract.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/backtesting/instrument/test_window_coverage.py`:

```python
"""v158 WC2: the 2009-06 cache-coverage precondition (spec section 1)."""
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument import contract, coverage
from swingbot.core.backtesting.instrument.coverage import CoverageReport

HEADER = "Date,Open,High,Low,Close,Volume\n"
MEMBERSHIP = (
    "ticker,start_date,end_date\n"
    "AAA,2005-01-03,\n"            # member through the whole research span
    "BBB,2000-01-03,2009-12-31\n"  # left before the research span: not a research member
    "CCC,2012-03-01,2015-01-02\n"  # joined inside the span
    "BRK.B,2008-02-01,\n"          # normalised to BRK-B, the cache spelling
    "DDD,2026-02-02,\n"            # joined after research_end: not a research member
)


def _csv(cache: Path, name: str, first_day: str | None, extra_header: str = "") -> None:
    rows = "" if first_day is None else f"{first_day},1,1,1,1,100\n{first_day[:8]}28,1,1,1,1,100\n"
    (cache / f"{name}.csv").write_text(HEADER + extra_header + rows, encoding="utf-8")


@pytest.fixture
def universe_dir(tmp_path, monkeypatch):
    """A synthetic data/ dir: pit_membership reads config.DATA_DIR at call time."""
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    return data


# --- first_bar_date --------------------------------------------------------------

def test_first_bar_date_reads_the_first_dated_row(tmp_path):
    _csv(tmp_path, "AAA", "2009-06-01")
    assert coverage.first_bar_date(tmp_path / "AAA.csv") == "2009-06-01"


def test_first_bar_date_trims_a_timestamp_to_the_day(tmp_path):
    (tmp_path / "AAA.csv").write_text(HEADER + "2009-06-01 00:00:00,1,1,1,1,100\n",
                                      encoding="utf-8")
    assert coverage.first_bar_date(tmp_path / "AAA.csv") == "2009-06-01"


def test_first_bar_date_skips_undated_header_rows(tmp_path):
    """yfinance multi-index CSVs carry 'Ticker,...' and 'Date,,,' rows first."""
    _csv(tmp_path, "AAA", "2010-01-04", extra_header="Ticker,AAA,AAA,AAA,AAA,AAA\nDate,,,,,\n")
    assert coverage.first_bar_date(tmp_path / "AAA.csv") == "2010-01-04"


def test_first_bar_date_is_none_for_an_absent_or_empty_csv(tmp_path):
    _csv(tmp_path, "EMPTY", None)
    assert coverage.first_bar_date(tmp_path / "EMPTY.csv") is None
    assert coverage.first_bar_date(tmp_path / "NOPE.csv") is None


# --- check_coverage ----------------------------------------------------------------

def test_check_coverage_sorts_covered_late_and_missing(tmp_path):
    _csv(tmp_path, "AAA", "2009-06-01")   # exactly the required day: covered
    _csv(tmp_path, "OLD", "1999-11-18")   # earlier: covered
    _csv(tmp_path, "CCC", "2009-06-02")   # one day late
    _csv(tmp_path, "EMPTY", None)         # no dated row: missing
    report = coverage.check_coverage(["CCC", "AAA", "OLD", "EMPTY", "GONE", "AAA"],
                                     "2009-06-01", tmp_path)
    assert report == CoverageReport(required_start="2009-06-01", covered=("AAA", "OLD"),
                                    late=(("CCC", "2009-06-02"),), missing=("EMPTY", "GONE"))
    assert report.gaps == 3


def test_check_coverage_uses_the_backtest_cache_filename_rule(tmp_path):
    """'^VIX' is cached as _VIX.csv (backtest_cache.cache_path), never re-derived here."""
    _csv(tmp_path, "_VIX", "2009-01-02")
    report = coverage.check_coverage(["^VIX"], "2009-06-01", tmp_path)
    assert report.covered == ("^VIX",)
    assert report.gaps == 0


def test_check_coverage_never_reads_market_data(tmp_path, monkeypatch):
    """Two OHLCV caches (known-traps.md): only the cache_dir passed in is read."""
    seen = []
    real = coverage.first_bar_date
    monkeypatch.setattr(coverage, "first_bar_date", lambda p: seen.append(Path(p)) or real(p))
    coverage.check_coverage(["AAA"], "2009-06-01", tmp_path)
    assert seen == [tmp_path / "AAA.csv"]


# --- research members and their first membership -----------------------------------

def test_research_members_are_every_pit_member_inside_the_v2_research_span(universe_dir):
    assert coverage.research_members(contract.resolve("v2")) == ["AAA", "BRK-B", "CCC"]


def test_research_members_refuse_an_instrument_without_a_pit_universe(universe_dir):
    with pytest.raises(ValueError, match="no point-in-time universe"):
        coverage.research_members(contract.resolve("v1"))


def test_research_members_refuse_a_missing_membership_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="sp500_membership.csv"):
        coverage.research_members(contract.resolve("v2"))


def test_first_membership_is_the_earliest_span_start_touching_the_research_span(universe_dir):
    spec = contract.resolve("v2")
    assert coverage.first_membership(spec, ["AAA", "CCC", "BRK-B", "ZZZ"]) == {
        "AAA": "2005-01-03", "CCC": "2012-03-01", "BRK-B": "2008-02-01"}


# --- render_markdown -------------------------------------------------------------------

def test_render_markdown_lists_every_gap_with_its_first_membership():
    report = CoverageReport(required_start="2009-06-01", covered=("AAA",),
                            late=(("CCC", "2012-03-05"),), missing=("GONE",))
    text = coverage.render_markdown(report, {"CCC": "2012-03-01", "GONE": "2010-01-04"})
    assert "Required first bar: 2009-06-01" in text
    assert "| Covered | 1 |" in text
    assert "| Late | 1 |" in text
    assert "| Missing | 1 |" in text
    assert "| Gaps | 2 |" in text
    assert "| CCC | 2012-03-05 | 2012-03-01 |" in text
    assert "| GONE | 2010-01-04 |" in text


def test_render_markdown_says_so_when_there_is_no_gap():
    report = CoverageReport(required_start="2009-06-01", covered=("AAA",), late=(), missing=())
    text = coverage.render_markdown(report, {})
    assert "| Gaps | 0 |" in text
    assert "No gaps" in text


# --- CLI -------------------------------------------------------------------------------

def test_cli_writes_the_report_and_exits_one_on_gaps(universe_dir, tmp_path):
    from scripts.data import check_cache_coverage as cli
    cache = tmp_path / "cache"
    cache.mkdir()
    _csv(cache, "AAA", "2009-06-01")
    _csv(cache, "CCC", "2010-01-04")   # BRK-B has no CSV at all
    out = tmp_path / "coverage.md"
    code = cli.run(["--instrument", "v2", "--cache-dir", str(cache), "--out", str(out)])
    assert code == 1
    text = out.read_text(encoding="utf-8")
    assert f"Cache: `{cache}`" in text
    assert "Instrument: v2" in text
    assert "| CCC | 2010-01-04 | 2012-03-01 |" in text
    assert "| BRK-B | 2008-02-01 |" in text


def test_cli_exits_zero_when_every_member_is_covered(universe_dir, tmp_path):
    from scripts.data import check_cache_coverage as cli
    cache = tmp_path / "cache"
    cache.mkdir()
    for name in ("AAA", "BRK-B", "CCC"):
        _csv(cache, name, "2009-05-01")
    assert cli.run(["--instrument", "v2", "--cache-dir", str(cache)]) == 0


def test_cli_refuses_v1_which_defines_no_warmup(universe_dir, tmp_path, capsys):
    from scripts.data import check_cache_coverage as cli
    assert cli.run(["--instrument", "v1", "--cache-dir", str(tmp_path)]) == 2
    assert "nothing to check" in capsys.readouterr().err


def test_cli_defaults_to_the_backtest_cache_dir(universe_dir, tmp_path, monkeypatch):
    from scripts.data import check_cache_coverage as cli
    from swingbot.core.marketdata import backtest_cache
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    for name in ("AAA", "BRK-B", "CCC"):
        _csv(tmp_path, name, "2009-05-01")
    assert cli.run(["--instrument", "v2"]) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_window_coverage.py`
Expected: FAIL, collection error `ImportError: cannot import name 'coverage'`.

- [ ] **Step 3: Implement `coverage.py`**

Create `$WT/swingbot/core/backtesting/instrument/coverage.py`:

```python
"""Cache-coverage check: the v136 phase-3 data precondition (spec section 1).

Before any v2 run, every point-in-time member of the research span must have
cached history back to the instrument's ``warmup_start`` (2009-06-01: the
indicator warm-up before the 2010 research start). This module lists the
members that do not -- it never drops one -- so a gap is a visible decision,
not a silently shrunken universe.

It reads the BACKTEST cache only (``data/backtest_cache[_ext]/``, see
``swingbot.core.marketdata.backtest_cache``), never ``market_data/``, and only
the first dated row of each CSV. ``cache_dir`` is always passed in:
``BACKTEST_CACHE_DIR`` is read once at import, so callers decide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from swingbot.core.marketdata import backtest_cache, pit_membership

_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class CoverageReport:
    """Every checked symbol lands in exactly one of covered / late / missing."""

    required_start: str
    covered: tuple[str, ...]
    late: tuple[tuple[str, str], ...]   # (symbol, first cached bar)
    missing: tuple[str, ...]            # no CSV, or a CSV with no dated row

    @property
    def gaps(self) -> int:
        return len(self.late) + len(self.missing)


def first_bar_date(path: Path) -> str | None:
    """ISO day of the first dated row of a cache CSV (rows are ascending), or
    None when the file is absent or holds no dated row. Undated header rows
    (yfinance's 'Ticker,...' / 'Date,,,') are skipped."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                cell = line.split(",", 1)[0].strip()
                if _ISO_DAY.match(cell):
                    return cell[:10]
    except OSError:
        return None
    return None


def _intervals(spec) -> dict[str, list[tuple[str, str]]]:
    path = pit_membership.membership_file_for(spec.universe)
    if path is None:
        raise ValueError(f"instrument {spec.version!r} has no point-in-time universe "
                         f"(universe={spec.universe!r})")
    intervals = pit_membership.load_intervals(path)
    if not intervals:
        raise FileNotFoundError(f"membership file missing or empty: {path}")
    return intervals


def research_members(spec) -> list[str]:
    """Every symbol that was a member at any point in the research span, sorted."""
    return pit_membership.members_between(_intervals(spec), *spec.research_span)


def first_membership(spec, symbols) -> dict[str, str]:
    """{symbol: start of its earliest membership span touching the research
    span}; symbols with no such span are left out."""
    intervals = _intervals(spec)
    start, end = spec.research_span
    out = {}
    for sym in symbols:
        starts = [s for s, e in intervals.get(sym, []) if s <= end and e > start]
        if starts:
            out[sym] = min(starts)
    return out


def check_coverage(symbols, required_start: str, cache_dir: Path) -> CoverageReport:
    """Classify each distinct symbol by its cached first bar against `required_start`."""
    covered, late, missing = [], [], []
    for sym in sorted(set(symbols)):
        first = first_bar_date(Path(cache_dir) / backtest_cache.cache_path(sym).name)
        if first is None:
            missing.append(sym)
        elif first > required_start:
            late.append((sym, first))
        else:
            covered.append(sym)
    return CoverageReport(required_start, tuple(covered), tuple(late), tuple(missing))


def _summary_lines(report: CoverageReport) -> list[str]:
    return [
        f"Required first bar: {report.required_start}",
        "",
        "| Status | Symbols |",
        "|---|---|",
        f"| Covered | {len(report.covered)} |",
        f"| Late | {len(report.late)} |",
        f"| Missing | {len(report.missing)} |",
        f"| Gaps | {report.gaps} |",
    ]


def _gap_lines(report: CoverageReport, first_membership: dict[str, str]) -> list[str]:
    lines = []
    if report.late:
        lines += ["", "## Late (first cached bar after the required day)", "",
                  "| Symbol | First cached bar | First PIT membership |", "|---|---|---|"]
        lines += [f"| {sym} | {first} | {first_membership.get(sym, '?')} |"
                  for sym, first in report.late]
    if report.missing:
        lines += ["", "## Missing (no cached CSV or no dated row)", "",
                  "| Symbol | First PIT membership |", "|---|---|"]
        lines += [f"| {sym} | {first_membership.get(sym, '?')} |" for sym in report.missing]
    return lines


def render_markdown(report: CoverageReport, first_membership: dict[str, str]) -> str:
    """The summary table plus one row per gap, each with its first membership."""
    lines = _summary_lines(report)
    lines += _gap_lines(report, first_membership) or ["", "No gaps."]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Implement the CLI**

Create `$WT/scripts/data/check_cache_coverage.py`:

```python
#!/usr/bin/env python3
"""List every point-in-time member whose cached history misses the warm-up.

    BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/check_cache_coverage.py --instrument v2
    python scripts/data/check_cache_coverage.py --instrument v2 --cache-dir data/backtest_cache_ext --out report.md

v136 spec section 1, "Data precondition" (v158 WC2). Reads the research span,
universe and warm-up start from the instrument contract (this script defines
no date) and the BACKTEST cache (`--cache-dir`, default
`backtest_cache.CACHE_DIR`), never market_data/. Lists gaps, drops nothing.
Exit 0 = every member covered, 1 = gaps listed, 2 = nothing to check.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import contract, coverage  # noqa: E402
from swingbot.core.marketdata import backtest_cache  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--instrument", choices=contract.VERSIONS, default="v2",
                    help="instrument whose universe, research span and warm-up are checked")
    ap.add_argument("--cache-dir", default=None,
                    help="backtest cache to read (default: backtest_cache.CACHE_DIR)")
    ap.add_argument("--out", default=None, help="write the markdown report here, else stdout")
    return ap


def _gap_symbols(report) -> list[str]:
    return [sym for sym, _ in report.late] + list(report.missing)


def _report_text(spec, cache_dir: Path) -> tuple[str, int]:
    symbols = coverage.research_members(spec)
    report = coverage.check_coverage(symbols, spec.warmup_start, cache_dir)
    start, end = spec.research_span
    head = [f"Instrument: {spec.version} (universe {spec.universe}, research {start}..{end})",
            f"Cache: `{cache_dir}`", f"Members checked: {len(symbols)}", ""]
    firsts = coverage.first_membership(spec, _gap_symbols(report))
    body = coverage.render_markdown(report, firsts)
    return "\n".join(head) + body, report.gaps


def run(argv=None) -> int:
    args = _parser().parse_args(argv)
    spec = contract.resolve(args.instrument)
    if spec.warmup_start is None or spec.universe is None:
        print(f"instrument {spec.version} defines no warm-up start or point-in-time universe: "
              "nothing to check", file=sys.stderr)
        return 2
    cache_dir = Path(args.cache_dir) if args.cache_dir else backtest_cache.CACHE_DIR
    text, gaps = _report_text(spec, cache_dir)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    print(f"COVERAGE: {'GAPS' if gaps else 'OK'}  {gaps} gap(s), cache {cache_dir}", file=sys.stderr)
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_window_coverage.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/coverage.py $WT/scripts/data/check_cache_coverage.py`
Expected: no output.

- [ ] **Step 6: Smoke-run the CLI on this machine (no cache here)**

`config.DATA_DIR` is `<project root>/data`, and `data/` is gitignored, so the worktree has no membership file. Link the main tree's universe directory in (read-only use; it sits inside the ignored `data/` directory, so it can never be committed):

```bash
mkdir -p $WT/data
test -e $WT/data/universe || ln -s /home/user/Discord-Bot/data/universe $WT/data/universe
git -C $WT status --short
```

Expected: `git status` shows only this task's three new files (or nothing after the commit), never `data/`.

Run: `python $WT/scripts/data/check_cache_coverage.py --instrument v2 --cache-dir "$(mktemp -d)"; echo "exit=$?"`
Expected: a report whose `Missing` row equals `Members checked` (every member missing, nothing silently dropped), `COVERAGE: GAPS` on stderr, `exit=1`. This proves the real membership file is read; the real cache run is WC3.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/backtesting/instrument/coverage.py scripts/data/check_cache_coverage.py tests/backtesting/instrument/test_window_coverage.py
git -C $WT commit -m "feat(instrument): v158 WC2 cache-coverage check for the 2009-06 warm-up"
git -C /home/user/Discord-Bot status --short
```

### Task WC3: Run the coverage check on the real cache and record gaps

**Model:** sonnet — runs the coverage check where the cache lives, writes a results doc, and may start one detached refetch job on the VM through the ops wrapper; it must route through production safely.

**Files:**
- Create: `docs/superpowers/results/2026-10-10-v158-cache-coverage.md`
- Create: `scripts/ops/refetch_ext_cache_2009.sh` (only if Step 5 runs)

**Why:** spec section 1, "Data precondition" (partner decision 7): the real 2009-06 coverage run happens wherever `data/backtest_cache_ext/` exists and records its gap list, rather than shrinking the universe silently. **There is no backtest cache on the dev machine**, so this task may block: if neither the dev machine nor the Hetzner VM holds the extended cache, stop at Step 1 and return `BLOCKED:` asking the partner to run Step 2a's command on their laptop and paste the output. Every other task in the plan proceeds without this one (nothing consumes the gap list in code); WC12 does not wait on it.

**Steps 1–4 are read-only.** They never fetch, write or delete cache files, and never edit anything on production (a read-only `ls`/`exec` is not a production change, so `mirror-prod` does not apply). **The partner has already decided the refetch (2026-10-10): "Refetch from 2009-06".** If the report shows late rows that start on the first 2010 session, Step 5 refetches the extended cache from `warmup_start` (2009-06-01), as a one-time overnight job on the Hetzner VM, and Step 6 re-runs the check.

**Expected finding, stated in advance so nobody reads it as a bug:** the extended cache was fetched in v102 with `fetch_backtest_data.py --start 2010-01-01 ...`, so most members probably start on the first 2010 session and land in **Late**. That is exactly the gap the precondition exists to surface. Record it in Step 3, then refetch in Step 5.

- [ ] **Step 1: Find the extended cache**

```bash
ls -d /home/user/Discord-Bot/data/backtest_cache_ext 2>/dev/null && ls /home/user/Discord-Bot/data/backtest_cache_ext | grep -c '\.csv$'
bash /home/user/Discord-Bot/scripts/ops/ssh-hetzner.sh "ls /opt/swing-bot/data/backtest_cache_ext 2>/dev/null | grep -c '\.csv\$'"
```

- A local count > 0: go to Step 2a.
- Otherwise a Hetzner count > 0: go to Step 2b (the bot container mounts `./data` at `/app/data`).
- Both empty or absent: return `BLOCKED: no extended backtest cache on the dev machine or the VM; please run "BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/check_cache_coverage.py --instrument v2 --out coverage.md" on the v158 branch on your laptop and paste coverage.md`. When the partner pastes it, continue at Step 3 with that text.

Before 2a or 2b, make sure the worktree sees the membership file (WC2 Step 6 created the link; repeat if missing):

```bash
mkdir -p $WT/data
test -e $WT/data/universe || ln -s /home/user/Discord-Bot/data/universe $WT/data/universe
```

- [ ] **Step 2a: Run locally**

```bash
SCR=/tmp/claude-0/v158-wc3; mkdir -p $SCR
python $WT/scripts/data/check_cache_coverage.py --instrument v2 --cache-dir /home/user/Discord-Bot/data/backtest_cache_ext --out $SCR/coverage.md; echo "exit=$?"
```

Expected: `exit=0` (no gaps) or `exit=1` (gaps listed). `exit=2` or a traceback means the membership link is missing: fix Step 1's link and re-run. Go to Step 3.

- [ ] **Step 2b: Run against the VM's cache (read-only)**

The deployed image does not carry the v158 code, so list each cached CSV's first dated row on the VM with a stdlib-only snippet, rebuild a stub cache locally that holds exactly that first row per file, and run WC2's CLI on the stub. `coverage.first_bar_date` reads only the first dated row, so the stub gives the same verdict as the real files.

```bash
SCR=/tmp/claude-0/v158-wc3; mkdir -p $SCR/stub
cat > $SCR/first_bars.py <<'PY'
import os, re
d = "/app/data/backtest_cache_ext"
iso = re.compile(r"^\d{4}-\d{2}-\d{2}")
for name in sorted(os.listdir(d)):
    if not name.endswith(".csv"):
        continue
    first = ""
    with open(os.path.join(d, name), encoding="utf-8") as f:
        for line in f:
            cell = line.split(",", 1)[0].strip()
            if iso.match(cell):
                first = cell[:10]
                break
    print(f"{name},{first}")
PY
bash /home/user/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < $SCR/first_bars.py > $SCR/first_bars.csv
wc -l $SCR/first_bars.csv
python - "$SCR" <<'PY'
import sys
from pathlib import Path
scr = Path(sys.argv[1])
for line in (scr / "first_bars.csv").read_text(encoding="utf-8").splitlines():
    name, _, first = line.partition(",")
    rows = f"{first},0,0,0,0,0\n" if first else ""
    (scr / "stub" / name).write_text("Date,Open,High,Low,Close,Volume\n" + rows, encoding="utf-8")
PY
python $WT/scripts/data/check_cache_coverage.py --instrument v2 --cache-dir $SCR/stub --out $SCR/coverage.md; echo "exit=$?"
```

Expected: `wc -l` equals the Hetzner count from Step 1; `exit=0` or `exit=1`. In Step 3 record the cache as `Hetzner /opt/swing-bot/data/backtest_cache_ext (first-bar listing, <N> CSVs)`, not the stub path.

- [ ] **Step 3: Write the results doc**

Collect provenance:

```bash
git -C $WT rev-parse --short HEAD
sha256sum /home/user/Discord-Bot/data/universe/sp500_membership.csv
wc -l < /home/user/Discord-Bot/data/universe/sp500_membership.csv
```

Create `$WT/docs/superpowers/results/2026-10-10-v158-cache-coverage.md` with this skeleton, the placeholders in angle brackets filled from the outputs above, and the CLI's report pasted verbatim under `## Report`:

```markdown
# v158 cache coverage: the instrument v2 data precondition

**Run:** <YYYY-MM-DD>, `scripts/data/check_cache_coverage.py --instrument v2` at `<short sha>` (v158 branch). Read-only.
**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md`, section 1 "Data precondition"
**Cache:** <local path | Hetzner /opt/swing-bot/data/backtest_cache_ext (first-bar listing, N CSVs)>
**Membership file:** `data/universe/sp500_membership.csv`, <lines> lines, sha256 `<hash>`

**Verdict: <NO GAPS | N GAPS>.** <covered> of <members> research-span PIT members have cached history from 2009-06-01; <late> start later and <missing> have no cached CSV. Nothing was dropped from the universe.

## Reading

- Late members whose first PIT membership is after 2010 may simply not have existed in 2009 (IPO or spin-off); the table shows both dates side by side.
- <If most late rows start on the first 2010 session:> The extended cache was fetched from 2010-01-01 (v102), so it holds no 2009 warm-up. On 2026-10-10 the partner decided to refetch from the contract's `warmup_start`; see `## Refetch` (Step 6).
- Missing members are mostly delisted symbols Yahoo no longer serves (`pit_membership.py` module docstring: the residual survivorship bias of free data).

## Report

<CLI output, verbatim>
```

The `## Reading` bullets are written from what the report actually shows; delete any bullet the data does not support (for example the 2010 bullet when there are no late rows).

- [ ] **Step 4: Commit**

```bash
git -C $WT add docs/superpowers/results/2026-10-10-v158-cache-coverage.md
git -C $WT commit -m "docs(results): v158 WC3 cache coverage for the 2009-06 warm-up"
git -C /home/user/Discord-Bot status --short
```

If the report has no late rows that start on the first 2010 session, the task ends here: tell the controller the verdict line. Otherwise continue.

- [ ] **Step 5: Refetch the extended cache from 2009-06-01 on the Hetzner VM (partner decision, 2026-10-10)**

This step writes cache files only (`data/backtest_cache_ext/` is a gitignored research cache, not bot config), so no `.env` or code changes on production and nothing to mirror beyond the committed wrapper below. It is a long network job, so it runs **on the VM**, detached, never on the dev machine (`working-conventions.md` § Scheduling).

1. Commit a wrapper at `scripts/ops/refetch_ext_cache_2009.sh` that runs, inside the bot container, `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --start 2009-06-01 --end 2025-12-31 --force --training-universe <the PIT name WC2 reads>`. Use `--force` because cached tickers must be overwritten to gain the 2009 bars. The wrapper logs to `/opt/swing-bot/logs/refetch_ext_2009.log` with flushed progress and a final `DONE <n> tickers` line. Confirm the exact `--training-universe`/`--universe` name against `fetch_backtest_data.py --help` before committing.
2. Copy it to the VM through `scripts/ops/ssh-hetzner.sh` (stdin pipe) and start it detached (`nohup ... &`). The image on the VM already carries `fetch_backtest_data.py`; no v158 code is needed for this step.
3. Return to the controller with `WAITING: ext-cache refetch running on Hetzner, log /opt/swing-bot/logs/refetch_ext_2009.log`. The plan's other tasks proceed; WC12 does not wait on this.

- [ ] **Step 6: Re-check and record (next session, after the log shows `DONE`)**

Re-run Step 2b against the refetched VM cache. Append a `## Refetch` section to the results doc with the wrapper command, the log's final line, and the new verdict line and counts. Late rows that remain should be members whose first PIT membership is after 2009 (IPOs, spin-offs); list any that are not. Commit:

```bash
git -C $WT add docs/superpowers/results/2026-10-10-v158-cache-coverage.md scripts/ops/refetch_ext_cache_2009.sh
git -C $WT commit -m "docs(results): v158 WC3 coverage after the 2009-06 refetch"
```

# Phase B: Folds

### Task WC4: Purged, embargoed anchored folds

**Model:** opus — leakage-sensitive date logic (purge, embargo, out-of-fold selection) whose boundary errors silently inflate every v2 verdict.

**Files:**
- Create: `swingbot/core/backtesting/instrument/folds.py`
- Create: `tests/backtesting/instrument/test_folds.py`

**Why:** spec section 1, "Folds": anchored walk-forward with yearly test folds 2014..2025 (12 folds, at least 4 training years before the first). A trade belongs to a test fold by its **entry** date (index cross-plan contract: under v2 that is the fill date; folds never read `signal_date`). In the matching train fold:

- **Purge**: drop a train trade whose **exit** date is on or after the test fold's start. A trade with `exit_date is None` (still open at the end of data) is treated as never closed, so it is purged too (the conservative reading).
- **Embargo**: drop train trades entered within `embargo_days` after the test fold's end. `embargo_days` is the horizon's maximum holding period (`embargo_days_for(hk)`, partner decision 2); the contract field (270) is the global maximum for callers that pool horizons.

Anything tuned is selected on the fold's train data only, and the verdict statistic is pooled out-of-fold ExpR: each trade counts once, in its own test year (`out_of_fold`). WC9 is the consumer; this task builds and proves the unit alone.

**Embargo under anchored folds** (index Global Constraints): an anchored train fold ends the day before its test fold, so no train trade can enter after the test end and the embargo never fires. `split_fold` still implements it generically: train candidates are the trades entered inside `[train_start, train_end]` and **outside** `[test_start, test_end]`, so a `Fold` whose `train_end` lies past `test_end` exercises it. Purge applies to train trades entered **before** the test start (under anchored folds, all of them); a train trade entered after the test end is the embargo's business. The tests prove the boundary, the anchored no-op and the generic case.

**Guards:** `anchored_folds` refuses an unknown scheme, unsorted or duplicate years, fewer than `MIN_TRAIN_YEARS = 4` training years before the first test year, and a test year past `research_end` (that would read the sealed holdout). `out_of_fold` refuses overlapping test windows (a trade would count twice) and a `select` result that is not one of the configs. Dates are compared as ISO day strings (`str(value)[:10]`), the same convention as `pit_membership.is_member`, so `BacktestTrade` ISO strings and pandas `Timestamp`s both work.

Contract (index ledger): `Fold(test_year: int, train_start: str, train_end: str, test_start: str, test_end: str)` (frozen); `anchored_folds(spec) -> tuple[Fold, ...]` (empty when `fold_scheme == "none"`); `embargo_days_for(horizon_key: str) -> int`; `split_fold(trades, fold, *, embargo_days: int, purge: bool = True) -> tuple[list, list]` (train, test); `OutOfFold(choices: tuple[tuple[int, Any], ...], trades: list)`; `out_of_fold(trades_by_config: Mapping[Any, Sequence], folds, select: Callable[[Mapping[Any, list]], Any], *, embargo_days: int, purge: bool = True) -> OutOfFold`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/backtesting/instrument/test_folds.py`:

```python
"""v158 WC4: purged, embargoed anchored folds and out-of-fold pooling
(v136 spec section 1 "Folds"; "Testing": purge/embargo boundary trades)."""
import dataclasses
from datetime import date, timedelta

import pandas as pd
import pytest

from swingbot.core.backtesting.backtest import BacktestTrade
from swingbot.core.backtesting.instrument import folds
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.backtesting.instrument.folds import Fold, OutOfFold
from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS

V2 = resolve("v2")
FOLD_2014 = Fold(test_year=2014, train_start="2010-01-01", train_end="2013-12-31",
                 test_start="2014-01-01", test_end="2014-12-31")


def _t(entry, exit_, r=1.0):
    return BacktestTrade(entry_date=entry, exit_date=exit_, direction="long", entry=100.0,
                         stop_loss=95.0, take_profit=110.0,
                         outcome="win" if r > 0 else "loss", exit_price=100.0,
                         return_pct=0.0, r_multiple=r, holding_days=1)


def _days(trades):
    return [str(t.entry_date)[:10] for t in trades]


# --- anchored_folds -------------------------------------------------------------------

def test_v2_has_twelve_anchored_yearly_folds():
    got = folds.anchored_folds(V2)
    assert [f.test_year for f in got] == list(range(2014, 2026))
    assert got[0] == FOLD_2014
    assert got[-1] == Fold(test_year=2025, train_start="2010-01-01", train_end="2024-12-31",
                           test_start="2025-01-01", test_end="2025-12-31")


def test_every_v2_train_fold_is_anchored_and_ends_the_day_before_its_test_fold():
    for fold in folds.anchored_folds(V2):
        assert fold.train_start == V2.research_start
        day_before = date.fromisoformat(fold.test_start) - timedelta(days=1)
        assert fold.train_end == day_before.isoformat()
        assert fold.test_end <= V2.research_end


def test_v1_has_no_folds():
    assert folds.anchored_folds(resolve("v1")) == ()


def test_folds_refuse_fewer_than_four_training_years():
    spec = dataclasses.replace(V2, fold_test_years=(2013, 2014))
    with pytest.raises(ValueError, match="4 training years"):
        folds.anchored_folds(spec)


def test_folds_refuse_a_test_year_inside_the_sealed_holdout():
    spec = dataclasses.replace(V2, fold_test_years=tuple(range(2014, 2027)))
    with pytest.raises(ValueError, match="holdout"):
        folds.anchored_folds(spec)


def test_folds_refuse_unsorted_or_duplicate_years():
    for years in ((2015, 2014), (2014, 2014)):
        with pytest.raises(ValueError, match="strictly increasing"):
            folds.anchored_folds(dataclasses.replace(V2, fold_test_years=years))


def test_folds_refuse_an_unknown_scheme_or_an_empty_year_list():
    with pytest.raises(ValueError, match="unknown fold scheme"):
        folds.anchored_folds(dataclasses.replace(V2, fold_scheme="rolling"))
    with pytest.raises(ValueError, match="fold_test_years"):
        folds.anchored_folds(dataclasses.replace(V2, fold_test_years=()))


# --- split_fold: membership by entry date ------------------------------------------------

def test_a_trade_belongs_to_the_test_fold_by_its_entry_date():
    trades = [_t("2013-12-31", "2013-12-31"), _t("2014-01-01", "2014-01-09"),
              _t("2014-12-31", "2015-02-01"), _t("2015-01-01", "2015-01-05")]
    train, test = folds.split_fold(trades, FOLD_2014, embargo_days=0)
    assert _days(test) == ["2014-01-01", "2014-12-31"]
    assert _days(train) == ["2013-12-31"]


def test_a_trade_before_the_train_start_is_in_neither_side():
    train, test = folds.split_fold([_t("2009-12-31", "2010-01-05")], FOLD_2014, embargo_days=0)
    assert (train, test) == ([], [])


# --- purge ------------------------------------------------------------------------------

def test_purge_drops_a_train_trade_exiting_on_or_after_the_test_start():
    kept = _t("2013-12-20", "2013-12-31")
    on_start = _t("2013-12-20", "2014-01-01")
    after = _t("2013-11-01", "2014-02-14")
    train, _ = folds.split_fold([kept, on_start, after], FOLD_2014, embargo_days=0)
    assert train == [kept]


def test_purge_treats_a_never_closed_train_trade_as_open_into_the_test_fold():
    train, _ = folds.split_fold([_t("2013-06-03", None)], FOLD_2014, embargo_days=0)
    assert train == []


def test_purge_off_keeps_trades_that_straddle_the_test_start():
    straddle = _t("2013-12-20", "2014-01-01")
    train, _ = folds.split_fold([straddle], FOLD_2014, embargo_days=0, purge=False)
    assert train == [straddle]


def test_test_side_trades_are_never_purged():
    """Purge thins train only: a test trade still open at the test end stays."""
    late = _t("2014-12-30", "2015-03-01")
    _, test = folds.split_fold([late], FOLD_2014, embargo_days=270)
    assert test == [late]


# --- embargo ----------------------------------------------------------------------------

def test_embargo_never_fires_under_anchored_folds():
    trades = [_t(f"{y}-0{m}-02", f"{y}-0{m}-20") for y in range(2010, 2016) for m in (2, 6)]
    for fold in folds.anchored_folds(V2)[:2]:
        assert (folds.split_fold(trades, fold, embargo_days=0)
                == folds.split_fold(trades, fold, embargo_days=270))


def test_embargo_drops_train_trades_entered_within_the_window_after_the_test_end():
    """A generic fold whose train side continues past the test fold."""
    fold = Fold(test_year=2014, train_start="2010-01-01", train_end="2016-12-31",
                test_start="2014-01-01", test_end="2014-12-31")
    before = _t("2013-06-03", "2013-07-01")
    inside_test = _t("2014-06-02", "2014-06-20")
    on_edge = _t("2015-01-30", "2015-02-10")   # test_end + 30 days: embargoed
    first_free = _t("2015-01-31", "2015-02-10")
    train, test = folds.split_fold([before, inside_test, on_edge, first_free], fold,
                                   embargo_days=30)
    assert train == [before, first_free]
    assert test == [inside_test]


def test_a_post_test_train_trade_is_left_to_the_embargo_not_the_purge():
    fold = Fold(test_year=2014, train_start="2010-01-01", train_end="2016-12-31",
                test_start="2014-01-01", test_end="2014-12-31")
    post = _t("2016-03-01", "2016-03-20")
    train, _ = folds.split_fold([post], fold, embargo_days=0)
    assert train == [post]


def test_split_fold_refuses_a_negative_embargo():
    with pytest.raises(ValueError, match="embargo_days"):
        folds.split_fold([], FOLD_2014, embargo_days=-1)


def test_split_fold_reads_timestamp_dates_as_iso_days():
    trade = _t(pd.Timestamp("2014-01-01"), pd.Timestamp("2014-01-09"))
    _, test = folds.split_fold([trade], FOLD_2014, embargo_days=0)
    assert test == [trade]


# --- embargo_days_for -----------------------------------------------------------------------

def test_embargo_days_is_each_horizons_maximum_holding_period():
    assert folds.embargo_days_for("2w") == 14
    assert folds.embargo_days_for("9m") == 270
    for hk in LEGACY_HORIZONS:
        assert folds.embargo_days_for(hk) == HORIZONS[hk]["max_holding_days"]


def test_the_contract_field_is_the_largest_per_horizon_embargo():
    assert V2.embargo_days == max(folds.embargo_days_for(hk) for hk in LEGACY_HORIZONS)


def test_embargo_days_for_refuses_an_unknown_horizon():
    with pytest.raises(ValueError, match="unknown horizon"):
        folds.embargo_days_for("10y")


# --- out_of_fold ------------------------------------------------------------------------------

THREE = dataclasses.replace(V2, fold_test_years=(2014, 2015, 2016))


def _yearly(r_train, r_test):
    """One trade per year 2010..2016: r_train through 2013, r_test after."""
    return [_t(f"{y}-03-02", f"{y}-03-10", r_train if y <= 2013 else r_test)
            for y in range(2010, 2017)]


def _best_mean(train):
    return max(sorted(train), key=lambda c: sum(t.r_multiple for t in train[c])
               / max(len(train[c]), 1))


def test_out_of_fold_selects_on_train_data_only():
    """A shines in train and fails in test; B the reverse. Selection on train
    picks A every fold, so the pooled out-of-fold trades are A's losers."""
    by_config = {"A": _yearly(1.0, -1.0), "B": _yearly(-1.0, 2.0)}
    seen = []

    def select(train):
        seen.append(max(str(t.entry_date)[:10] for trades in train.values() for t in trades))
        return _best_mean(train)

    got = folds.out_of_fold(by_config, folds.anchored_folds(THREE), select, embargo_days=270)
    assert got.choices == ((2014, "A"), (2015, "A"), (2016, "A"))
    assert [t.r_multiple for t in got.trades] == [-1.0, -1.0, -1.0]
    assert seen == ["2013-03-02", "2014-03-02", "2015-03-02"]   # never a test-year trade


def test_out_of_fold_counts_each_trade_once_in_its_own_test_year():
    by_config = {"only": _yearly(1.0, 1.0)}
    got = folds.out_of_fold(by_config, folds.anchored_folds(THREE), _best_mean,
                            embargo_days=270)
    assert _days(got.trades) == ["2014-03-02", "2015-03-02", "2016-03-02"]
    assert len({id(t) for t in got.trades}) == len(got.trades)


def test_out_of_fold_selection_sees_purged_train_data():
    """A config's train trade still open at the test start is invisible to select."""
    straddle = _t("2013-12-20", "2014-01-15", 5.0)
    by_config = {"A": [straddle]}
    seen = []
    folds.out_of_fold(by_config, folds.anchored_folds(THREE)[:1],
                      lambda train: seen.append(train) or "A", embargo_days=270)
    assert seen == [{"A": []}]


def test_out_of_fold_with_no_folds_is_empty():
    assert folds.out_of_fold({"A": _yearly(1.0, 1.0)}, (), _best_mean,
                             embargo_days=0) == OutOfFold(choices=(), trades=[])


def test_out_of_fold_refuses_a_selection_outside_the_configs():
    with pytest.raises(ValueError, match="not one of the configs"):
        folds.out_of_fold({"A": []}, folds.anchored_folds(THREE)[:1], lambda train: "Z",
                          embargo_days=0)


def test_out_of_fold_refuses_overlapping_test_windows():
    overlap = (FOLD_2014, dataclasses.replace(FOLD_2014, test_year=2015,
                                              test_start="2014-12-01", test_end="2015-12-31"))
    with pytest.raises(ValueError, match="overlap"):
        folds.out_of_fold({"A": []}, overlap, lambda train: "A", embargo_days=0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_folds.py`
Expected: FAIL, collection error `ImportError: cannot import name 'folds'`.

- [ ] **Step 3: Implement `folds.py`**

Create `$WT/swingbot/core/backtesting/instrument/folds.py`:

```python
"""Purged, embargoed anchored walk-forward folds (v136 spec section 1, "Folds").

Anchored yearly folds over the instrument's research span: test year Y is
[Y-01-01, Y-12-31]; its train fold runs from ``research_start`` to the day
before. A trade belongs to a test fold by its ENTRY date (under v2 that is the
fill date; folds never read ``signal_date``). In the matching train fold:

* purge   -- a train trade entered before the test start whose exit is on or
             after it (or that never closed) is dropped: its outcome overlaps
             the test fold;
* embargo -- a train trade entered within ``embargo_days`` after the test end
             is dropped. Under anchored folds no train trade enters after the
             test end, so the embargo never fires there; it is implemented for
             any fold whose train side continues past the test fold.

``out_of_fold`` selects a config per fold on that fold's train trades only and
pools each selected config's test trades: every trade counts once, in its own
test year. The pooled out-of-fold ExpR is the v2 verdict statistic.

Dates compare as ISO day strings (``str(value)[:10]``), the convention of
``pit_membership.is_member``.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from swingbot.core.market.strategy_types import HORIZONS

#: Spec section 1: at least four training years before the first test fold.
MIN_TRAIN_YEARS = 4


@dataclass(frozen=True)
class Fold:
    """One anchored fold; every bound is an inclusive ISO day."""

    test_year: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass(frozen=True)
class OutOfFold:
    """Per-fold choices ((test_year, config), ...) and the pooled test trades."""

    choices: tuple[tuple[int, Any], ...]
    trades: list


def _check_years(spec) -> None:
    years = tuple(spec.fold_test_years)
    if not years:
        raise ValueError("fold_scheme 'anchored_yearly' needs fold_test_years")
    if list(years) != sorted(set(years)):
        raise ValueError(f"fold_test_years must be strictly increasing: {years}")
    if years[0] - int(spec.research_start[:4]) < MIN_TRAIN_YEARS:
        raise ValueError(f"first test year {years[0]} leaves fewer than "
                         f"{MIN_TRAIN_YEARS} training years after {spec.research_start}")
    if f"{years[-1]}-12-31" > spec.research_end:
        raise ValueError(f"test year {years[-1]} ends after research_end {spec.research_end}: "
                         "that is the sealed holdout")


def anchored_folds(spec) -> tuple[Fold, ...]:
    """The instrument's folds; () when its fold_scheme is 'none' (v1)."""
    if spec.fold_scheme == "none":
        return ()
    if spec.fold_scheme != "anchored_yearly":
        raise ValueError(f"unknown fold scheme {spec.fold_scheme!r}")
    _check_years(spec)
    return tuple(Fold(test_year=y, train_start=spec.research_start, train_end=f"{y - 1}-12-31",
                      test_start=f"{y}-01-01", test_end=f"{y}-12-31")
                 for y in spec.fold_test_years)


def embargo_days_for(horizon_key: str) -> int:
    """The horizon's maximum holding period (strategy_types.HORIZONS)."""
    try:
        return int(HORIZONS[horizon_key]["max_holding_days"])
    except KeyError:
        raise ValueError(f"unknown horizon {horizon_key!r}") from None


def _day(value) -> str:
    return str(value)[:10]


def _inside(day: str, start: str, end: str) -> bool:
    return start <= day <= end


def _purged(trade, fold: Fold) -> bool:
    """Entered before the test fold and still open on or after its first day."""
    if _day(trade.entry_date) >= fold.test_start:
        return False
    return trade.exit_date is None or _day(trade.exit_date) >= fold.test_start


def _train_keeps(trade, fold: Fold, embargo_end: str, purge: bool) -> bool:
    day = _day(trade.entry_date)
    if not _inside(day, fold.train_start, fold.train_end):
        return False
    if _inside(day, fold.test_start, fold.test_end):
        return False
    if purge and _purged(trade, fold):
        return False
    return not fold.test_end < day <= embargo_end


def split_fold(trades, fold: Fold, *, embargo_days: int,
               purge: bool = True) -> tuple[list, list]:
    """(train, test) for one fold. Test = entered inside the test window.
    Train = entered inside the train window and outside the test window,
    minus purged and embargoed trades. Input order is preserved."""
    if embargo_days < 0:
        raise ValueError(f"embargo_days must be >= 0, got {embargo_days}")
    embargo_end = (date.fromisoformat(fold.test_end) + timedelta(days=embargo_days)).isoformat()
    test = [t for t in trades if _inside(_day(t.entry_date), fold.test_start, fold.test_end)]
    train = [t for t in trades if _train_keeps(t, fold, embargo_end, purge)]
    return train, test


def _check_disjoint(folds) -> None:
    ordered = sorted(folds, key=lambda f: f.test_start)
    for a, b in zip(ordered, ordered[1:]):
        if b.test_start <= a.test_end:
            raise ValueError(f"test windows overlap: {a.test_year} and {b.test_year} "
                             "(a trade would count twice)")


def out_of_fold(trades_by_config: Mapping[Any, Sequence], folds,
                select: Callable[[Mapping[Any, list]], Any], *, embargo_days: int,
                purge: bool = True) -> OutOfFold:
    """Per fold: `select` sees {config: train trades} only and returns a config;
    that config's test trades join the pool. Each trade counts once."""
    _check_disjoint(folds)
    choices, pooled = [], []
    for fold in folds:
        train = {cfg: split_fold(trades, fold, embargo_days=embargo_days, purge=purge)[0]
                 for cfg, trades in trades_by_config.items()}
        choice = select(train)
        if choice not in trades_by_config:
            raise ValueError(f"select returned {choice!r}, not one of the configs")
        choices.append((fold.test_year, choice))
        pooled += split_fold(trades_by_config[choice], fold, embargo_days=embargo_days,
                             purge=purge)[1]
    return OutOfFold(choices=tuple(choices), trades=pooled)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_folds.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/folds.py`
Expected: no output.

- [ ] **Step 5: Re-run the instrument package (contract and golden untouched)**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/`
Expected: PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/backtesting/instrument/folds.py tests/backtesting/instrument/test_folds.py
git -C $WT commit -m "feat(instrument): v158 WC4 purged, embargoed anchored folds and out-of-fold pooling"
git -C /home/user/Discord-Bot status --short
```

