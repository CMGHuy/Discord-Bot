# v245 — Exact analysis caching — Part 1: characterisation goldens and profile

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-2" -A 400 <this file>`).

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Index:** [2026-11-23-v245-exact-analysis-cache_0-index.md](2026-11-23-v245-exact-analysis-cache_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the decisions this part relies on (Decision 1 golden clock, Decision 2 golden floats) live there.

This part covers spec § Task 0 steps 1–3 and § Testing "Characterisation":
V245-1 pins `_scan_one`'s output before anything changes, V245-2 builds the
profiler, V245-3 runs it and writes the results doc that ranks what Part 2
fixes. V245-1 and V245-2 may run in parallel (index § Parallelisation);
V245-3 needs both.

# Phase A — Characterise and profile

### Task V245-1: Golden harness for `_scan_one` (cases, hermetic run, exact snapshot)

**Model:** sonnet — new test helper over a known call, with exact and fully specified behaviour.

First half of spec § Testing, Characterisation: the harness that runs
`_scan_one` hermetically over fixture frames under a frozen clock and
projects the result to an exact JSON snapshot. V245-1b generates and pins
the golden with it. (V245-1 was split at the 20 KB cap; the ledger row
`V245-1b` sits directly below this one.)

**Files:**
- Create: `tests/scanning/v245_golden_cases.py` (helper module, not collected: no `test_` prefix)
- Create: `tests/scanning/test_v245_scan_one_golden.py` (harness tests now; V245-1b appends the golden tests)

**Interfaces:**
- Consumes: `analyze._scan_one` (analyze.py:941, today's signature, no `now`/`structure`), `analyze.ScanIO` (analyze.py:764), `strategy_types.LEGACY_HORIZONS` (strategy_types.py:236, the ten scanned horizons 2w..9m), `config.FIELDS` / `config._cast` (config.py:1824).
- Produces (ledger contract, consumed by V245-1b, V245-9, V245-10, V245-13, V245-14): `GOLDEN_NOW`, `HERMETIC_IO`, `GoldenCase`, `CASES`, `frozen_clock(monkeypatch, now=GOLDEN_NOW)`, `run_case(case, *, structure=None) -> dict`, `snapshot(stats) -> dict`, `GOLDEN_PATH`, `REGEN_ENV = "V245_REGEN_GOLDEN"`. Extra helpers: `CASE_BY_NAME`, `first_diff(a, b) -> str | None`, `load_golden() -> dict`, `write_golden(doc) -> None`.
- `GoldenCase` has one field more than the ledger row, appended with a default so a ledger-shaped construction still works: `atr_stop_floor: float = 0.0` (the `confluence_atr_stop_floor` hard filter; above 0 it routes through `_band_live`, the second wall-clock reader).

Facts the code relies on (checked at eec00b44):
- The only wall-clock reads on `_scan_one`'s path are `analyze.py:836` (`_apply_pullback_dryup`) and `analyze.py:873` (`_band_live`), both `datetime.now(timezone.utc)` through the module name `analyze.datetime`. Confirm with `git grep -n "datetime.now" swingbot/core/scanning/analyze.py` (lines 476/489/517/589/626 are plan-building code outside `_scan_one`). `_build_requirement_checks` gets `opex_tier=None` explicitly, so `opex.suppress_new_entries` never reads the clock.
- `GOLDEN_NOW = 2024-03-15 19:00 UTC` is 15:00 New York (EDT since 2024-03-10), in the regular session, so `strategy_pass.completed_frame` drops a last row dated 2024-03-15 (index Decision 1).
- `config` loads the checkout's `.env`; `tests/conftest.py:100` pins only seven knobs. `run_case` pins every non-sensitive `config.FIELDS` entry to its shipped default during the call, so the golden is the same on a dev machine and on CI.
- The custom trendline scanner needs volume spikes at the turns or finds nothing (`tests/charts/test_trendline_fit.py`): the builder puts 2.5x volume on every ±5-bar extreme. `universe.liquidity_reason` floors at $20M dollar volume and $5 (universe.py:66-69); the frames trade about 100 x 1e6.

- [ ] **Step 1: Write the harness tests**

Create `tests/scanning/test_v245_scan_one_golden.py`:

```python
"""v245 V245-1/V245-1b: `_scan_one` output pinned byte for byte (spec § Testing).

A golden failure after a v245 change is a behaviour change: stop and report,
never regenerate (index § Global Constraints)."""
from datetime import timezone

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.scanning import analyze
from tests.scanning.v245_golden_cases import (CASE_BY_NAME, CASES, GOLDEN_NOW, first_diff,
                                              frozen_clock, run_case, snapshot)


def test_clock_is_frozen_for_analyze(monkeypatch):
    frozen_clock(monkeypatch)
    assert analyze.datetime.now(timezone.utc) == GOLDEN_NOW
    assert analyze.datetime.now() == GOLDEN_NOW


def test_case_names_are_unique():
    assert len(CASE_BY_NAME) == len(CASES)


def test_forming_frame_is_the_completed_frame_plus_one_row():
    forming = CASE_BY_NAME["wave_forming"].frame()
    completed = CASE_BY_NAME["wave_completed"].frame()
    assert forming.index[-1].date().isoformat() == "2024-03-15"
    assert completed.index[-1].date().isoformat() == "2024-03-14"
    pd.testing.assert_frame_equal(forming.iloc[:-1], completed)
    assert len(CASE_BY_NAME["long_completed"].frame()) > 1500


def test_frames_are_rebuilt_per_call():
    case = CASE_BY_NAME["wave_completed"]
    first = case.frame()
    first.iloc[-1, 0] = -1.0
    assert case.frame().iloc[-1, 0] != -1.0


def test_run_case_is_deterministic(monkeypatch):
    frozen_clock(monkeypatch)
    case = CASE_BY_NAME["wave_forming"]
    assert run_case(case) == run_case(case)


def test_run_case_ignores_dotenv_tuning(monkeypatch):
    frozen_clock(monkeypatch)
    case = CASE_BY_NAME["wave_completed"]
    before = run_case(case)
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", not config.AVWAP_LEVELS_ENABLED)
    assert run_case(case) == before


def test_no_frame_snapshot():
    doc = run_case(CASE_BY_NAME["no_frame"])
    assert doc["data_quality_failed"] is True
    assert doc["items"] == [] and doc["checked"] == 0


def test_snapshot_is_exact_and_json_shaped():
    stats = {"checked": 1, "no_entry_point": 0, "scenarios_found": 0, "fully_qualifying": 0,
             "mtf_misaligned": 0, "failed_counts": {"b": 1, "a": 2}, "conf_level_counts": {3: 1},
             "data_quality_failed": np.bool_(False), "funnel_events": [("bullish", "base", None, "s", "r")],
             "newly_closed": [], "near_close_warnings": [{}], "items": []}
    doc = snapshot(stats)
    assert list(doc["failed_counts"]) == ["a", "b"]
    assert doc["conf_level_counts"] == {"3": 1}
    assert doc["data_quality_failed"] is False
    assert doc["funnel_events"] == [["bullish", "base", None, "s", "r"]]
    assert doc["near_close_warnings"] == 1


def test_snapshot_rejects_types_without_an_exact_form():
    stats = dict.fromkeys(("checked", "no_entry_point", "scenarios_found", "fully_qualifying",
                           "mtf_misaligned", "failed_counts", "conf_level_counts",
                           "data_quality_failed"), 0)
    stats.update(funnel_events=[object()], newly_closed=[], near_close_warnings=[], items=[])
    with pytest.raises(TypeError):
        snapshot(stats)


def test_first_diff_names_the_path():
    assert first_diff({"a": [1, 2]}, {"a": [1, 2]}) is None
    assert first_diff({"a": [1, 2]}, {"a": [1, 3]}) == "$.a[1]: 2 != 3"
    assert first_diff({"a": 1}, {"b": 1}) == "$.a: present on one side only"
    assert first_diff([1], [1, 2]) == "$: length 1 != 2"
```

`float.hex` is exercised end to end by `test_run_case_is_deterministic`
(every price in an item is a float); `test_snapshot_is_exact_and_json_shaped`
pins the container rules.

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py`
Expected: FAIL — collection error `ModuleNotFoundError: No module named 'tests.scanning.v245_golden_cases'`.

- [ ] **Step 3: Write the helper module**

Create `tests/scanning/v245_golden_cases.py`:


```python
"""v245 characterisation goldens for analyze._scan_one (spec § Testing).

Pins today's per-ticker analysis output byte for byte before any v245
change. Every later v245 task that touches analysis keeps
tests/fixtures/scanning/v245_scan_one_golden.json unchanged: a task that
needs to regenerate it has found a behaviour change and stops.

Regenerate only on unchanged analysis code (index Decision 2, a platform
float difference), never to absorb a refactor:
    V245_REGEN_GOLDEN=1 python -m pytest tests/scanning/test_v245_scan_one_golden.py -p no:xdist -q
"""
from __future__ import annotations

import dataclasses
import functools
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.scanning import analyze

GOLDEN_NOW = datetime(2024, 3, 15, 19, 0, tzinfo=timezone.utc)   # 15:00 New York, regular session
GOLDEN_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "scanning" / "v245_scan_one_golden.json"
REGEN_ENV = "V245_REGEN_GOLDEN"
TICKER = "GOLD"
FORMING_DAY = "2024-03-15"     # a forming frame's last row; its completed twin ends 2024-03-14
MIN_CONFLUENCE = 2             # mid thresholds: some requirements pass, some fail
MIN_CONFIDENCE = 2
# Loose enough that most horizons build a scenario, so confluence,
# confidence and requirements are all exercised (pattern: test_rescenario.HF).
GOLDEN_HARD_FILTERS = {
    "min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
    "min_risk_reward_ratio": 0.01, "confluence_deviation_pct": 1.0,
}
# Config fields run_case leaves alone: secrets and connection strings.
_UNPINNED = frozenset({"DATABASE_URL"})

HERMETIC_IO = analyze.ScanIO(
    stop_requested=lambda: False,
    monitor_scan=lambda ticker, df, current_price: ([], []),
    monitor_open=lambda ticker, df, live_price=None: ([], []),
    track_record=lambda base_level: (None, 0),
)

# ScanItem fields the snapshot reads, named so that a field added later
# (V245-9's prefix_results) never changes the golden.
ITEM_FIELDS = (
    "result", "plan", "conf", "requirements", "target_confluence", "stop_confluence",
    "combined_from", "htf_info", "previous_confirmed", "htf_bias", "level_map",
    "rs_percentile", "trendline_candidates", "scan_price", "hard_filters", "candidate_context",
)
STAT_KEYS = (
    "checked", "no_entry_point", "scenarios_found", "fully_qualifying", "mtf_misaligned",
    "failed_counts", "conf_level_counts", "data_quality_failed", "funnel_events",
)


@dataclass(frozen=True)
class GoldenCase:
    name: str
    frame: Callable[[], pd.DataFrame | None]
    horizons: tuple[str, ...]
    allowed_directions: object
    mtf_adjacent_gate: bool
    live_price: Callable[[pd.DataFrame], float | None]
    atr_stop_floor: float = 0.0


def _wave_frame(n: int, *, seed: int, drift: float, end: str) -> pd.DataFrame:
    """Random walk times a 37-bar wave, 2.5x volume on every ±5-bar extreme."""
    rng = np.random.RandomState(seed)
    base = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.012, n)))
    close = np.round(base * (1.0 + 0.06 * np.sin(2 * np.pi * np.arange(n) / 37.0)), 4)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.round(np.maximum(open_, close) * 1.01, 4)
    low = np.round(np.minimum(open_, close) * 0.99, 4)
    volume = np.full(n, 1_000_000.0)
    for i in range(n):
        window = close[max(0, i - 5): i + 6]
        if close[i] in (window.max(), window.min()):
            volume[i] = 2_500_000.0
    index = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": volume}, index=index)


def _forming(n: int, seed: int, drift: float) -> Callable[[], pd.DataFrame]:
    """n completed bars plus a forming row dated FORMING_DAY at 40% volume."""
    def build() -> pd.DataFrame:
        df = _wave_frame(n + 1, seed=seed, drift=drift, end=FORMING_DAY)
        df.iloc[-1, df.columns.get_loc("Volume")] = round(float(df["Volume"].iloc[-2]) * 0.4)
        return df
    return build


def _completed(n: int, seed: int, drift: float) -> Callable[[], pd.DataFrame]:
    """The forming frame minus its forming row: ends 2024-03-14."""
    forming = _forming(n, seed, drift)
    return lambda: forming().iloc[:-1].copy()


def _at_close(df: pd.DataFrame) -> float | None:
    return None                       # no live print: _scan_one falls back to the last close


def _times(mult: float) -> Callable[[pd.DataFrame], float]:
    return lambda df: round(float(df["Close"].iloc[-1]) * mult, 4)


def _case(name, frame, *, live=_at_close, directions=None, gate=False,
          horizons=LEGACY_HORIZONS, floor=0.0) -> GoldenCase:
    return GoldenCase(name, frame, tuple(horizons), directions, gate, live, floor)


_WAVE = dict(n=420, seed=11, drift=0.0004)    # 420 >= MIN_BARS["9m"] (390)
_DOWN = dict(n=420, seed=23, drift=-0.0006)
_LONG = dict(n=1560, seed=37, drift=0.0003)   # longer than MAX_PIVOT_SCAN_BARS: the 1500-bar trim runs
_SHORT = dict(n=150, seed=11, drift=0.0004)   # passes 2w..3m, below MIN_BARS for 4m..9m

CASES: tuple[GoldenCase, ...] = (
    _case("wave_completed", _completed(**_WAVE)),
    _case("wave_completed_gate", _completed(**_WAVE), gate=True),
    _case("wave_forming", _forming(**_WAVE), live=_times(1.0)),
    _case("wave_forming_gate", _forming(**_WAVE), live=_times(1.0), gate=True),
    _case("wave_bullish_only", _completed(**_WAVE), directions=frozenset({"bullish"})),
    _case("wave_bearish_only", _completed(**_WAVE), directions=frozenset({"bearish"})),
    # Live prices relative to the close: +-1.2% gaps through a near entry,
    # +-4% and +-8% through the nearer and farther stop/target levels.
    _case("wave_forming_gap_up_1", _forming(**_WAVE), live=_times(1.012)),
    _case("wave_forming_gap_dn_1", _forming(**_WAVE), live=_times(0.988)),
    _case("wave_forming_gap_up_4", _forming(**_WAVE), live=_times(1.04)),
    _case("wave_forming_gap_dn_4", _forming(**_WAVE), live=_times(0.96)),
    _case("wave_forming_gap_up_8", _forming(**_WAVE), live=_times(1.08)),
    _case("wave_forming_gap_dn_8", _forming(**_WAVE), live=_times(0.92)),
    _case("wave_completed_stale_print", _completed(**_WAVE), live=_times(0.70)),
    _case("wave_completed_band", _completed(**_WAVE), floor=1.0),
    _case("wave_forming_band", _forming(**_WAVE), live=_times(1.0), floor=1.0),
    _case("down_completed", _completed(**_DOWN)),
    _case("down_forming", _forming(**_DOWN), live=_times(1.0)),
    _case("long_completed", _completed(**_LONG)),
    _case("long_forming", _forming(**_LONG), live=_times(1.0)),
    _case("short_history_completed", _completed(**_SHORT)),
    _case("short_history_forming", _forming(**_SHORT), live=_times(1.0)),
    _case("no_frame", lambda: None),
)
CASE_BY_NAME = {case.name: case for case in CASES}


class _FrozenDatetime(datetime):
    frozen = GOLDEN_NOW

    @classmethod
    def now(cls, tz=None):
        return cls.frozen if tz is None else cls.frozen.astimezone(tz)


def frozen_clock(monkeypatch, now: datetime = GOLDEN_NOW) -> None:
    """Every datetime.now() analyze makes returns `now` (index Decision 1)."""
    monkeypatch.setattr(analyze, "datetime", type("_Frozen", (_FrozenDatetime,), {"frozen": now}))


def _pin_config_defaults(mp) -> None:
    for f in config.FIELDS:
        if f.sensitive or f.attr in _UNPINNED or not hasattr(config, f.attr):
            continue
        mp.setattr(config, f.attr, config._cast(f, f.default))


def run_case(case: GoldenCase, *, structure=None) -> dict:
    """Run `_scan_one` on the case, hermetically, and return its snapshot."""
    df = case.frame()
    live = case.live_price(df) if df is not None else None
    hard_filters = {**GOLDEN_HARD_FILTERS, "mtf_adjacent_gate": case.mtf_adjacent_gate,
                    "confluence_atr_stop_floor": case.atr_stop_floor}
    extra = {} if structure is None else {"structure": structure}
    with pytest.MonkeyPatch.context() as mp:
        _pin_config_defaults(mp)
        stats = analyze._scan_one(
            TICKER, df, list(case.horizons), None, None, MIN_CONFLUENCE, MIN_CONFIDENCE,
            live_prices={TICKER: live} if live else None, hard_filters=hard_filters,
            allowed_directions=case.allowed_directions, io=HERMETIC_IO, **extra)
    return snapshot(stats)


def _canon(obj):
    """JSON-able, exact: floats as float.hex, containers recursed, keys sorted."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, np.generic):
        return _canon(obj.item())
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return float.hex(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _canon(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _canon(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    raise TypeError(f"v245 golden: no exact form for {type(obj).__name__}")


def _item(item) -> dict:
    doc = {name: _canon(getattr(item, name)) for name in ITEM_FIELDS}
    doc["all_requirements_met"] = item.all_requirements_met
    doc["risk_reward_ratio"] = _canon(item.plan.risk_reward_ratio)
    return doc


def snapshot(stats: dict) -> dict:
    """The exact, JSON-able projection of one `_scan_one` stats dict."""
    out = {key: _canon(stats[key]) for key in STAT_KEYS}
    out["newly_closed"] = len(stats["newly_closed"])
    out["near_close_warnings"] = len(stats["near_close_warnings"])
    out["items"] = [_item(item) for item in stats["items"]]
    return out


def first_diff(a, b, path: str = "$") -> str | None:
    """Path of the first difference between two snapshots, or None."""
    if type(a) is not type(b):
        return f"{path}: {a!r} != {b!r}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}: present on one side only"
            found = first_diff(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        return next((d for i, (x, y) in enumerate(zip(a, b))
                     if (d := first_diff(x, y, f"{path}[{i}]"))), None)
    return None if a == b else f"{path}: {a!r} != {b!r}"


@functools.lru_cache(maxsize=1)
def _golden_text() -> str:
    return GOLDEN_PATH.read_text(encoding="utf-8")


def load_golden() -> dict:
    """A fresh dict per call (the parsed text is cached, never the dict)."""
    return json.loads(_golden_text())


def write_golden(doc: dict) -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _golden_text.cache_clear()
```

If `_pin_config_defaults` raises on a field whose default does not cast
(a dynamic select), add that field's attr to `_UNPINNED` with a one-line
comment naming why; never wrap the loop in a bare `try`. If `_canon` raises
`TypeError` on a type `_scan_one` really returns, add an exact branch for it
(never the `repr` of an object that carries an id).

- [ ] **Step 4: Run it to see it pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py`
Expected: PASS, `0 failed` (10 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/scanning/v245_golden_cases.py tests/scanning/test_v245_scan_one_golden.py
git commit -m "test(v245): hermetic _scan_one golden harness with exact snapshots (V245-1)"
```

### Task V245-1b: Generate and pin the `_scan_one` golden

**Model:** sonnet — runs V245-1's harness, tunes fixture seeds until a fixed coverage test passes, commits the result.

Second half of spec § Testing, Characterisation: every case of V245-1's
harness is run once and stored; from here on every v245 task that touches
analysis keeps this file byte-identical (index § Global Constraints).

**Files:**
- Modify: `tests/scanning/test_v245_scan_one_golden.py` (created by V245-1)
- Modify: `tests/scanning/v245_golden_cases.py` (created by V245-1; only the `_WAVE`/`_DOWN` seeds or wave amplitude, and only if Step 4 asks for it)
- Create: `tests/fixtures/scanning/v245_scan_one_golden.json` (generated in Step 3)

**Interfaces:**
- Consumes: from V245-1 `CASES`, `CASE_BY_NAME`, `GOLDEN_PATH`, `REGEN_ENV`, `frozen_clock`, `run_case`, `first_diff`, `load_golden`, `write_golden`.
- Produces: the committed golden `tests/fixtures/scanning/v245_scan_one_golden.json` (one key per case name) and the test `test_scan_one_matches_golden[<case>]` that every later analysis task runs.

- [ ] **Step 1: Append the golden tests**

Append to `tests/scanning/test_v245_scan_one_golden.py` (and extend its
imports as shown: add `import os` at the top, and add `GOLDEN_PATH`,
`REGEN_ENV`, `load_golden`, `write_golden` to the `v245_golden_cases` import):

```python
import os

from tests.scanning.v245_golden_cases import (GOLDEN_PATH, REGEN_ENV, load_golden,
                                              write_golden)

REGEN = os.environ.get(REGEN_ENV) == "1"
LONG_HORIZONS = {"4m", "5m", "6m", "7m", "8m", "9m"}


@pytest.mark.skipif(not REGEN, reason=f"set {REGEN_ENV}=1 to rewrite the golden")
def test_regenerate_golden(monkeypatch):
    frozen_clock(monkeypatch)
    write_golden({case.name: run_case(case) for case in CASES})


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_scan_one_matches_golden(case, monkeypatch):
    frozen_clock(monkeypatch)
    golden = load_golden()
    assert case.name in golden, f"{case.name} missing from {GOLDEN_PATH.name}"
    got = run_case(case)
    assert got == golden[case.name], first_diff(got, golden[case.name])


def test_golden_holds_exactly_the_cases():
    assert sorted(load_golden()) == sorted(case.name for case in CASES)


def test_golden_exercises_the_analysis():
    """The fixture frames reach every stage the v245 refactors touch."""
    golden = load_golden()
    items = [item for doc in golden.values() for item in doc["items"]]
    assert len(items) >= 10
    assert {item["plan"]["direction"] for item in items} == {"bullish", "bearish"}
    assert {item["all_requirements_met"] for item in items} == {True, False}
    assert len({item["result"]["horizon_key"] for item in items}) >= 3
    assert any(item["trendline_candidates"] for item in items), "custom trendline scanner never fired"
    assert any(item["level_map"] for item in items), "no fully qualifying item staged a level map"
    assert golden["long_completed"]["checked"] == 10
    short = {item["result"]["horizon_key"] for item in golden["short_history_completed"]["items"]}
    assert not short & LONG_HORIZONS
    assert golden["short_history_completed"]["checked"] <= 4
```

Merge the imports into the file's existing import block (one
`from tests.scanning.v245_golden_cases import (...)` statement, `import os`
with the other stdlib imports); the module-level constants go below the
imports.

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py`
Expected: FAIL — `FileNotFoundError` on `v245_scan_one_golden.json` in `test_scan_one_matches_golden[...]`, `test_golden_holds_exactly_the_cases` and `test_golden_exercises_the_analysis`; V245-1's ten tests PASS; `test_regenerate_golden` SKIPPED.

- [ ] **Step 3: Generate the golden**

Run: `V245_REGEN_GOLDEN=1 python -m pytest tests/scanning/test_v245_scan_one_golden.py -p no:xdist -q`
Expected: `test_regenerate_golden` PASSES and writes `tests/fixtures/scanning/v245_scan_one_golden.json`; the tests after it pass. (`-p no:xdist` keeps the file's order, so the regeneration runs before the comparisons.)

- [ ] **Step 4: Make sure the frames exercise the analysis**

If `test_golden_exercises_the_analysis` fails, the frames are too flat:
change the `_WAVE`/`_DOWN` seeds, or the wave amplitude `0.06` in
`_wave_frame`, then rerun Step 3, until it passes. This tuning happens only
now, before the golden is committed, and never touches a case's name or the
harness logic.

Check the size: `wc -c tests/fixtures/scanning/v245_scan_one_golden.json`
should stay under 3 MB; if larger, remove the cases
`wave_forming_gap_up_8` and `wave_forming_gap_dn_8` from `CASES` and
regenerate.

- [ ] **Step 5: Run it green, twice**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py` (two times in a row)
Expected: PASS both times, `0 failed`, `test_regenerate_golden` skipped.

Then check the suite budget: `python scripts/dev/testrun.py suites`. The
`scanning` suite must stay under its `max_tests` (1200). If this file pushes
it over, stop and report (suites are split by feature, never raised).

- [ ] **Step 6: Commit**

```bash
git add tests/scanning/test_v245_scan_one_golden.py tests/scanning/v245_golden_cases.py tests/fixtures/scanning/v245_scan_one_golden.json
git commit -m "test(v245): pin the _scan_one golden before the analysis cache (V245-1b)"
```

After the push, CI (Linux) runs the same test. If it fails on unchanged
code with float-hex differences only, regenerate the golden under WSL (or
from CI's output) and commit it as
`test(v245): regenerate _scan_one golden on Linux floats (V245-1b)`, naming
the platform in the message (index Decision 2). Never loosen a comparison to
a rounding tolerance.

### Task V245-2: Analysis profiler core: candidates, forming bar, cProfile shares

**Model:** sonnet — a new standalone script with fully specified behaviour and its tests; no production code changes.

Spec § Task 0 step 1, time half: replay one scan's frames through
`_scan_one` under `cProfile`, once as stored and once with a synthesised
forming bar, and report each candidate's share. V245-2b adds the memory
passes and the command line. Shares only: the 0.7 s target is judged from
production `phases_s`, never from this output. (V245-2 was split at the
20 KB cap; the ledger row `V245-2b` sits directly below this one.)

**Files:**
- Create: `scripts/perf/__init__.py`
- Create: `scripts/perf/profile_analysis.py`
- Create: `tests/scripts/test_profile_analysis.py`

**Interfaces:**
- Consumes: `analyze._scan_one`, `analyze.ScanIO`, `analyze._live_track_record` (analyze.py:799, read-only journal stats), `indicators.atr` (indicators.py:62), `training_data.load_daily(ticker)` (training_data.py:251, the local Alpaca history store under `data/market_data/daily/`). It does **not** import V245-1's golden helper (index § Parallelisation).
- Produces (ledger): `CANDIDATES: tuple[tuple[str, str], ...]`, `synth_forming_bar(df, atr_mult=0.5) -> DataFrame`, `load_frames(tickers) -> dict[str, DataFrame]`, `profile_scan(frames, horizons, *, forming, io=QUIET_IO) -> tuple[pstats.Stats, float]`, `candidate_shares(stats, total_s) -> list[dict]` (`label, target, calls, cum_s, share`, sorted by `cum_s` descending). Also `resolve(target)`, `QUIET_IO`, `JOURNAL_IO`, `PROD_BARS`, `ROOT`, `DEFAULT_OUT`, consumed by V245-2b.

Design notes:
- The forming bar follows spec § Task 0 step 1: next business day, `Open = Close = last close`, `High/Low = last close ± 0.5 × ATR14`, `Volume` = the last row's; the live price is that close.
- `QUIET_IO` monitors nothing and answers `(None, 0)` for the track record. `JOURNAL_IO` (used by V245-2b's `--journal`) keeps the real read-only `_live_track_record`, because production pays that journal read once per scenario inside the analysis phase. Neither runs `update_open_trades` (it writes); V245-3 records that monitoring cost as unmeasured.
- `PROD_BARS = 2515`: production's `DEFAULT_HISTORY_PERIOD=10y` at about 252 sessions a year, so the trendline's 1500-bar trim and indicator lengths match production.
- Candidates are matched by code object (`co_filename`, `co_firstlineno`, `co_name`), so a function imported into `analyze` (e.g. `score_confidence`) is counted once, at its definition.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_profile_analysis.py`:

```python
"""v245 V245-2/V245-2b: the analysis profiler (spec § Task 0 step 1)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.perf import profile_analysis as pa  # noqa: E402
from swingbot.core.market.indicators import atr  # noqa: E402


def _frame(n: int = 260, seed: int = 5) -> pd.DataFrame:
    """A wave with 2.5x volume on every ±5-bar extreme (the trendline scanner needs it)."""
    rng = np.random.RandomState(seed)
    base = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, n)))
    close = np.round(base * (1.0 + 0.06 * np.sin(2 * np.pi * np.arange(n) / 37.0)), 4)
    volume = np.full(n, 1_000_000.0)
    for i in range(n):
        window = close[max(0, i - 5): i + 6]
        if close[i] in (window.max(), window.min()):
            volume[i] = 2_500_000.0
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": volume},
                        index=pd.bdate_range("2023-01-02", periods=n))


def test_every_candidate_resolves_to_a_function():
    labels = [label for label, _ in pa.CANDIDATES]
    assert len(labels) == len(set(labels))
    for label, target in pa.CANDIDATES:
        assert hasattr(pa.resolve(target), "__code__"), label


def test_synth_forming_bar_appends_one_bar_half_an_atr_wide():
    df = _frame()
    out = pa.synth_forming_bar(df)
    assert len(df) == 260 and len(out) == 261
    assert out.index[-1] == df.index[-1] + pd.offsets.BDay(1)
    close, half = float(df["Close"].iloc[-1]), 0.5 * float(atr(df, 14).iloc[-1])
    row = out.iloc[-1]
    assert row["Open"] == row["Close"] == close
    assert row["High"] == pytest.approx(close + half)
    assert row["Low"] == pytest.approx(close - half)
    assert row["Volume"] == df["Volume"].iloc[-1]
    pd.testing.assert_frame_equal(out.iloc[:-1], df)


def test_synth_forming_bar_scales_with_atr_mult():
    df = _frame()
    narrow, wide = pa.synth_forming_bar(df, 0.5).iloc[-1], pa.synth_forming_bar(df, 1.0).iloc[-1]
    assert wide["High"] - wide["Close"] == pytest.approx(2 * (narrow["High"] - narrow["Close"]))


def test_profile_scan_counts_one_scan_per_ticker():
    stats, total_s = pa.profile_scan({"T0": _frame(), "T1": _frame(seed=6)}, ["4w"], forming=False)
    rows = {row["label"]: row for row in pa.candidate_shares(stats, total_s)}
    assert rows["_scan_one"]["calls"] == 2
    assert rows["custom_scanner_levels"]["calls"] == 2
    assert rows["_horizon_scenarios"]["calls"] == 2
    assert rows["track_record (journal)"]["calls"] == 0     # QUIET_IO never reads the journal
    assert 0.5 < rows["_scan_one"]["share"] <= 1.05
    assert all(0.0 <= row["share"] <= 1.05 for row in rows.values())


def test_candidate_shares_are_sorted_by_time():
    stats, total_s = pa.profile_scan({"T0": _frame()}, ["4w"], forming=False)
    times = [row["cum_s"] for row in pa.candidate_shares(stats, total_s)]
    assert times == sorted(times, reverse=True)


def test_profile_scan_forming_feeds_the_synthesised_close(monkeypatch):
    seen = []

    def fake(ticker, df, horizons, *args, live_prices=None, io=None, **kwargs):
        seen.append((ticker, len(df), live_prices, io))
        return {}

    monkeypatch.setattr(pa.analyze, "_scan_one", fake)
    df = _frame()
    pa.profile_scan({"T0": df}, ["4w"], forming=True)
    pa.profile_scan({"T0": df}, ["4w"], forming=False, io=pa.JOURNAL_IO)
    assert seen == [("T0", len(df) + 1, {"T0": float(df["Close"].iloc[-1])}, pa.QUIET_IO),
                    ("T0", len(df), None, pa.JOURNAL_IO)]


def test_load_frames_skips_missing_and_empty(monkeypatch):
    from swingbot.core.marketdata import training_data
    frames = {"A": _frame(), "B": None, "C": _frame().iloc[:0]}
    monkeypatch.setattr(training_data, "load_daily", lambda ticker: frames[ticker])
    assert list(pa.load_frames(["A", "B", "C"])) == ["A"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_profile_analysis.py`
Expected: FAIL — collection error `ModuleNotFoundError: No module named 'scripts.perf'`.

- [ ] **Step 3: Write the profiler core**

Create `scripts/perf/__init__.py`:

```python
"""v245 performance tooling: analysis profiling and telemetry reports."""
```

Create `scripts/perf/profile_analysis.py` (V245-2b appends the memory
passes, `main` and the `__main__` guard):

```python
#!/usr/bin/env python3
"""v245 Task 0: where one scan's analysis time goes (spec § Task 0 step 1).

Replays local daily frames through analyze._scan_one under cProfile, twice:
as stored (no forming bar) and with a forming bar synthesised from the last
row (OHLC = last close +/- 0.5 ATR14, live price = that close). Separate
tracemalloc passes give the analysis peak and the bytes of the object the
trendline prefix cache would hold. Shares only: the laptop is not the VM
under cpus: 1.0, so the 0.7 s target is judged from production phases_s.

    python scripts/perf/profile_analysis.py [--tickers AAPL,MSFT] [--horizons 2w,4w]
        [--max-bars 2515] [--journal] [--out logs/v245-profile/profile.json]

Tickers default to the local replica's watchlist (run /replicate-prod-db
first); frames come from training_data.load_daily (data/market_data/daily).
"""
from __future__ import annotations

import cProfile
import importlib
import inspect
import os
import pstats
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from swingbot.core.scanning import analyze  # noqa: E402

PROD_BARS = 2515      # DEFAULT_HISTORY_PERIOD=10y at about 252 sessions a year
DEFAULT_OUT = os.path.join(ROOT, "logs", "v245-profile", "profile.json")
_SC, _MK, _MD = "swingbot.core.scanning.", "swingbot.core.market.", "swingbot.core.marketdata."

# (label, "module:function") -- spec § Task 0 step 2's candidates and the
# indicator functions under them.
CANDIDATES: tuple[tuple[str, str], ...] = (
    ("_scan_one", _SC + "analyze:_scan_one"),
    ("custom_scanner_levels", _MK + "trendlines:custom_scanner_levels"),
    ("_find_best_trendline", _MK + "trendlines:_find_best_trendline"),
    ("_volume_confirmed_pivots", _MK + "trendlines:_volume_confirmed_pivots"),
    ("zigzag_pivots", _MK + "indicators:zigzag_pivots"),
    ("_score_candidate", _MK + "trendlines:_score_candidate"),
    ("trendline_levels", _MK + "trendlines:trendline_levels"),
    ("_trendln_fallback_levels", _MK + "trendlines:_trendln_fallback_levels"),
    ("_horizon_scenarios", _SC + "analyze:_horizon_scenarios"),
    ("collect_candidate_levels", _MK + "levels:collect_candidate_levels"),
    ("_fvg_candidates", _MK + "levels:_fvg_candidates"),
    ("build_level_map", _MK + "levels:build_level_map"),
    ("_cluster_levels", _MK + "levels:_cluster_levels"),
    ("build_scenarios", _MK + "levels:build_scenarios"),
    ("atr_floor_pct", _MK + "levels:atr_floor_pct"),
    ("count_confirming_strategies", _MK + "levels:count_confirming_strategies"),
    ("score_confidence", _SC + "confidence:score_confidence"),
    ("_build_requirement_checks", _SC + "requirements:_build_requirement_checks"),
    ("get_htf_bias", _SC + "regime:get_htf_bias"),
    ("macro_aligned", _MK + "mtf:macro_aligned"),
    ("adjacent_aligned", _MK + "mtf:adjacent_aligned"),
    ("_rs_pctile", _SC + "analyze:_rs_pctile"),
    ("liquidity_reason (E12)", _MD + "universe:liquidity_reason"),
    ("data_quality_issues (E16)", _MD + "universe:data_quality_issues"),
    ("_apply_pullback_dryup", _SC + "analyze:_apply_pullback_dryup"),
    ("_apply_headroom", _SC + "analyze:_apply_headroom"),
    ("_band_live", _SC + "analyze:_band_live"),
    ("veto_bullish_for", _SC + "analyze:veto_bullish_for"),
    ("track_record (journal)", _SC + "analyze:_live_track_record"),
    ("ema", _MK + "indicators:ema"),
    ("atr", _MK + "indicators:atr"),
    ("rolling_vwap", _MK + "indicators:rolling_vwap"),
    ("fibonacci_levels", _MK + "indicators:fibonacci_levels"),
    ("bollinger_bands", _MK + "volatility:bollinger_bands"),
)


def _no_monitor(ticker, df, price=None):
    return [], []


QUIET_IO = analyze.ScanIO(lambda: False, _no_monitor, _no_monitor, lambda base_level: (None, 0))
JOURNAL_IO = analyze.ScanIO(lambda: False, _no_monitor, _no_monitor, analyze._live_track_record)


def resolve(target: str):
    module, _, name = target.partition(":")
    return inspect.unwrap(getattr(importlib.import_module(module), name))


def _code_key(fn) -> tuple:
    code = fn.__code__
    return os.path.normcase(code.co_filename), code.co_firstlineno, code.co_name


def synth_forming_bar(df: pd.DataFrame, atr_mult: float = 0.5) -> pd.DataFrame:
    """`df` plus one forming bar: next business day, last close +/- atr_mult x ATR14."""
    from swingbot.core.market.indicators import atr
    close = float(df["Close"].iloc[-1])
    half = float(atr(df, 14).iloc[-1]) * atr_mult
    half = 0.0 if half != half else half          # NaN ATR on a short frame: a flat bar
    row = df.iloc[[-1]].copy()
    row.index = pd.DatetimeIndex([df.index[-1] + pd.offsets.BDay(1)], name=df.index.name)
    row["Open"], row["High"], row["Low"], row["Close"] = close, close + half, close - half, close
    return pd.concat([df, row])


def load_frames(tickers: list[str]) -> dict[str, pd.DataFrame]:
    from swingbot.core.marketdata import training_data
    frames = {}
    for ticker in tickers:
        df = training_data.load_daily(ticker)
        if df is not None and len(df):
            frames[ticker] = df
    return frames


def profile_scan(frames: dict, horizons: list[str], *, forming: bool,
                 io=QUIET_IO) -> tuple[pstats.Stats, float]:
    inputs = {t: synth_forming_bar(df) if forming else df for t, df in frames.items()}
    live = {t: float(df["Close"].iloc[-1]) for t, df in inputs.items()} if forming else None
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    try:
        for ticker, df in inputs.items():
            analyze._scan_one(ticker, df, list(horizons), None, None, 0, 0,
                              live_prices=live, io=io)
    finally:
        profiler.disable()
    return pstats.Stats(profiler), time.perf_counter() - started


def candidate_shares(stats: pstats.Stats, total_s: float) -> list[dict]:
    index = {(os.path.normcase(f), line, name): row for (f, line, name), row in stats.stats.items()}
    out = []
    for label, target in CANDIDATES:
        row = index.get(_code_key(resolve(target)))
        calls, cum_s = (row[1], row[3]) if row else (0, 0.0)
        out.append({"label": label, "target": target, "calls": calls, "cum_s": round(cum_s, 4),
                    "share": round(cum_s / total_s, 4) if total_s > 0 else 0.0})
    return sorted(out, key=lambda r: r["cum_s"], reverse=True)
```

- [ ] **Step 4: Run them to see them pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_profile_analysis.py`
Expected: PASS, `0 failed` (7 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/perf/__init__.py scripts/perf/profile_analysis.py tests/scripts/test_profile_analysis.py
git commit -m "feat(v245): analysis profiler core with forming-bar replay and candidate shares (V245-2)"
```

### Task V245-2b: Profiler memory passes and command line

**Model:** sonnet — appends fully specified functions and a CLI to V245-2's script, with tests.

Spec § Task 0 steps 1 and 3, memory half: the analysis peak under
`tracemalloc` and the bytes of the object the trendline prefix cache would
hold per ticker (spec § Storage: "a memory figure, not just an entry
count"), plus `main`, which writes the report V245-3 reads.

**Files:**
- Modify: `scripts/perf/profile_analysis.py` (created by V245-2)
- Modify: `tests/scripts/test_profile_analysis.py` (created by V245-2)

**Interfaces:**
- Consumes: from V245-2 `CANDIDATES`, `profile_scan`, `candidate_shares`, `load_frames`, `synth_forming_bar`, `QUIET_IO`, `JOURNAL_IO`, `PROD_BARS`, `DEFAULT_OUT`, `analyze`; `trendlines._volume_confirmed_pivots` (trendlines.py:142), `trendlines.MAX_PIVOT_SCAN_BARS` (1500), `trendlines.TOUCH_TOLERANCE_PCT` (2.0), `strategy_types.LEGACY_HORIZONS`, `watchlist.load_watchlist()` (watchlist.py:4, Postgres).
- Produces (ledger): `object_bytes(obj) -> int` (pickled size), `main(argv=None) -> int`. Also `traced_build(build) -> tuple[object, int]`, `trendline_prefix_estimate(df, side) -> tuple` (`(side, m, confirmed pivots, pairs)`, `pairs[i][j - i - 1]` = `None` or `(slope, intercept, touches)`).
- Output: `logs/v245-profile/profile.json` with keys `generated_at, tickers, missing, bars, horizons, journal, runs.completed, runs.forming` (each `total_s, per_ticker_s, candidates`), `memory.analysis_peak_mb`, `memory.trendline_bytes_per_ticker.{pickled,retained}.{median,p95,max}`, `memory.per_ticker.<T>.{pickled,retained,pivots}`; plus `<stem>-completed.prof` and `<stem>-forming.prof` beside it. `logs/` is git-ignored.

`trendline_prefix_estimate` mirrors the shape index Decision 4 fixes for
V245-8's `TrendlinePrefix`: confirmed pivots of the trimmed frame minus its
last row (`TRENDLINE_PREFIX_TAIL_BARS = 1`), and for every `i<j` pair its
geometry and its touches against those pivots. It is a size estimate only
(it keeps the last two pivots that V245-8 will leave to the tail, so it
errs high), never imported by production code. A ticker holds two such
entries (`trendline:support`, `trendline:resistance`), so the per-ticker
figure is the sum of both sides.

- [ ] **Step 1: Append the failing tests**

Append to `tests/scripts/test_profile_analysis.py` (add `import json` and
`import pickle` to its stdlib imports):

```python
def test_object_bytes_is_the_pickled_size():
    obj = ("support", 10, ((1, 2.0, 1.1),), ((None,),))
    assert pa.object_bytes(obj) == len(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def test_traced_build_returns_the_object_and_its_bytes():
    obj, retained = pa.traced_build(lambda: [0.5 + i for i in range(10_000)])
    assert len(obj) == 10_000 and retained >= 10_000 * 8


def test_trendline_prefix_estimate_holds_every_pair():
    df = _frame()
    side, m, pivots, pairs = pa.trendline_prefix_estimate(df, "support")
    assert side == "support" and m == len(df) - 1
    assert len(pivots) >= 2
    assert len(pairs) == len(pivots)
    assert all(len(row) == len(pivots) - i - 1 for i, row in enumerate(pairs))
    assert all(cell is None or len(cell) == 3 for row in pairs for cell in row)


def test_trendline_prefix_estimate_trims_like_the_scanner():
    long = _frame(n=1700)
    _, m, _, _ = pa.trendline_prefix_estimate(long, "resistance")
    assert m == 1500 - 1


def test_main_writes_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "load_frames", lambda tickers: {"T0": _frame()})
    out = tmp_path / "p.json"
    assert pa.main(["--tickers", "t0,MISSING", "--horizons", "4w", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["tickers"] == 1 and doc["missing"] == ["MISSING"]
    assert doc["horizons"] == ["4w"] and doc["journal"] is False
    assert set(doc["runs"]) == {"completed", "forming"}
    assert doc["runs"]["forming"]["candidates"][0]["label"]
    assert doc["memory"]["analysis_peak_mb"] > 0
    assert doc["memory"]["trendline_bytes_per_ticker"]["pickled"]["max"] > 0
    assert doc["memory"]["per_ticker"]["T0"]["pivots"]["support"] >= 2
    assert (tmp_path / "p-completed.prof").exists() and (tmp_path / "p-forming.prof").exists()


def test_main_trims_frames_to_max_bars(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "load_frames", lambda tickers: {"T0": _frame(n=300)})
    out = tmp_path / "p.json"
    assert pa.main(["--tickers", "T0", "--horizons", "4w", "--max-bars", "200",
                    "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["bars"]["max"] == 200


def test_main_fails_without_frames(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pa, "load_frames", lambda tickers: {})
    assert pa.main(["--tickers", "T0", "--out", str(tmp_path / "p.json")]) == 1
    assert "no local frames" in capsys.readouterr().err
```

`test_main_writes_the_report` passes `t0` lower-case: the ticker parser
upper-cases it and the patched `load_frames` returns `T0`, so `missing` is
exactly `["MISSING"]`.

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_profile_analysis.py`
Expected: FAIL — the seven new tests with `AttributeError: module 'scripts.perf.profile_analysis' has no attribute 'object_bytes'` (and `traced_build`, `trendline_prefix_estimate`, `main`); V245-2's seven tests PASS.

- [ ] **Step 3: Append the memory passes and the command line**

Add to the imports of `scripts/perf/profile_analysis.py` (stdlib block):
`argparse`, `functools`, `json`, `pickle`, `statistics`, `tracemalloc`,
`from datetime import datetime, timezone`; and below the `analyze` import:

```python
from swingbot.core.market import trendlines as tl  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402
```

Append to the end of the file:

```python
def object_bytes(obj) -> int:
    return len(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def traced_build(build) -> tuple[object, int]:
    """`build()` and the bytes it allocated that are still alive afterwards."""
    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        obj = build()
        retained = tracemalloc.get_traced_memory()[0] - base
    finally:
        tracemalloc.stop()
    return obj, retained


def _touches(slope: float, intercept: float, pivots: tuple) -> tuple:
    out = []
    for bar, price, vol in pivots:
        line = slope * bar + intercept
        if line > 0 and abs(price - line) / line * 100 <= tl.TOUCH_TOLERANCE_PCT:
            out.append((bar, price, vol))
    return tuple(out)


def trendline_prefix_estimate(df: pd.DataFrame, side: str) -> tuple:
    """(side, m, confirmed pivots, pairs): the shape V245-8's TrendlinePrefix holds."""
    trimmed = df.tail(tl.MAX_PIVOT_SCAN_BARS).iloc[:-1]
    pivots = tuple(tl._volume_confirmed_pivots(trimmed, "low" if side == "support" else "high"))
    pairs = []
    for i, (x0, y0, _) in enumerate(pivots):
        row = []
        for x1, y1, _ in pivots[i + 1:]:
            if x1 == x0 or y0 <= 0 or y1 <= 0:
                row.append(None)
                continue
            slope = (y1 - y0) / (x1 - x0)
            intercept = y0 - slope * x0
            row.append((slope, intercept, _touches(slope, intercept, pivots)))
        pairs.append(tuple(row))
    return side, len(trimmed), pivots, tuple(pairs)


def _dist(values: list) -> dict:
    if not values:
        return {"median": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {"median": statistics.median(ordered), "p95": p95, "max": ordered[-1]}


def _per_ticker_bytes(frames: dict) -> dict:
    per_ticker = {}
    for ticker, df in frames.items():
        row = {"pickled": 0, "retained": 0, "pivots": {}}
        for side in ("support", "resistance"):
            obj, retained = traced_build(functools.partial(trendline_prefix_estimate, df, side))
            row["pickled"] += object_bytes(obj)
            row["retained"] += retained
            row["pivots"][side] = len(obj[2])
        per_ticker[ticker] = row
    return per_ticker


def _analysis_peak_mb(frames: dict, horizons: list[str], io) -> float:
    tracemalloc.start()
    try:
        for ticker, df in frames.items():
            analyze._scan_one(ticker, df, list(horizons), None, None, 0, 0, io=io)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return round(peak / 1e6, 2)


def _run(frames: dict, horizons: list[str], *, forming: bool, io, prof_stem: str) -> dict:
    stats, total_s = profile_scan(frames, horizons, forming=forming, io=io)
    stats.dump_stats(f"{prof_stem}-{'forming' if forming else 'completed'}.prof")
    return {"total_s": round(total_s, 3), "per_ticker_s": round(total_s / max(len(frames), 1), 4),
            "candidates": candidate_shares(stats, total_s)}


def _parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v245 analysis profiler (shares only)")
    parser.add_argument("--tickers", help="comma-separated; default: the local replica's watchlist")
    parser.add_argument("--horizons", default=",".join(LEGACY_HORIZONS))
    parser.add_argument("--max-bars", type=int, default=PROD_BARS)
    parser.add_argument("--journal", action="store_true",
                        help="read the confidence track record from the local journal (read-only)")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def _tickers(arg: str | None) -> list[str]:
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    from swingbot.core.marketdata.watchlist import load_watchlist
    return [t.upper() for t in load_watchlist()]


def _print_summary(report: dict, out: str) -> None:
    print(f"{report['tickers']} tickers ({len(report['missing'])} without a local frame) -> {out}")
    for name, run in report["runs"].items():
        print(f"  {name}: {run['per_ticker_s']} s/ticker")
        for row in run["candidates"][:12]:
            print(f"    {row['share']:7.2%}  {row['calls']:7d}  {row['label']}")


def _memory(frames: dict, horizons: list[str], io) -> dict:
    per_ticker = _per_ticker_bytes(frames)
    return {"analysis_peak_mb": _analysis_peak_mb(frames, horizons, io),
            "trendline_bytes_per_ticker": {
                "pickled": _dist([r["pickled"] for r in per_ticker.values()]),
                "retained": _dist([r["retained"] for r in per_ticker.values()])},
            "per_ticker": per_ticker}


def main(argv=None) -> int:
    args = _parse(argv)
    tickers = _tickers(args.tickers)
    frames = {t: df.tail(args.max_bars) for t, df in load_frames(tickers).items()}
    if not frames:
        print("no local frames for any ticker (data/market_data/daily)", file=sys.stderr)
        return 1
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    io = JOURNAL_IO if args.journal else QUIET_IO
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    stem = os.path.splitext(out)[0]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": len(frames), "missing": sorted(set(tickers) - set(frames)),
        "bars": _dist([len(df) for df in frames.values()]), "horizons": horizons,
        "journal": args.journal,
        "runs": {"completed": _run(frames, horizons, forming=False, io=io, prof_stem=stem),
                 "forming": _run(frames, horizons, forming=True, io=io, prof_stem=stem)},
        "memory": _memory(frames, horizons, io),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    _print_summary(report, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run them to see them pass, then a smoke run**

Run: `python scripts/dev/testrun.py file tests/scripts/test_profile_analysis.py`
Expected: PASS, `0 failed` (14 tests).

Smoke run on one real ticker (`--tickers` needs no database):
`python scripts/perf/profile_analysis.py --tickers AAPL --horizons 4w --out logs/v245-profile/smoke.json`
Expected: exit 0, a summary with `_scan_one` at the top of both runs, and
`logs/v245-profile/smoke.json` plus `smoke-completed.prof` /
`smoke-forming.prof` written. If `AAPL` has no local frame, use any ticker
listed in `data/market_data/daily/`.

- [ ] **Step 5: Commit**

```bash
git add scripts/perf/profile_analysis.py tests/scripts/test_profile_analysis.py
git commit -m "feat(v245): profiler memory passes, trendline-cache bytes and CLI (V245-2b)"
```

### Task V245-3: Profile run, tags and results doc

**Model:** opus — judgement task: reads code to tag each hot spot and ranks the fixes Part 2 builds; a wrong tag would let a later task cache something that reads the tail.

Spec § Task 0 steps 2–3: run V245-2's profiler over the production
watchlist's local frames, tag every candidate (reads the last row? reads
`current_price`? prefix-pure?), measure the bytes a trendline cache entry
costs, and write the ranked fixes (`F1..Fn`) and prefix-pure units
(`U1..Un`) that V245-4, V245-5 and (if Phase B runs) V245-11 consume.
No production code changes in this task.

**Files:**
- Create: `docs/superpowers/results/2026-11-23-v245-analysis-profile.md`

**Interfaces:**
- Consumes: `scripts/perf/profile_analysis.py` (V245-2/V245-2b: `main`, `candidate_shares`, `_dist`, `CANDIDATES`, the `.prof` and JSON outputs); V245-1b's golden (unchanged by this task).
- Produces (ledger): the doc with sections `## Shares`, `## Tags`, `## Bytes per object`, `## Byte-identical fixes` (ranked `F1..Fn`), `## Prefix-pure units` (ranked `U1..Un`, `U1` = trendline pair search), `## Cache size` (recommended `STRUCTURE_CACHE_MAX`), plus `## What Part 2 takes`. V245-4 reads `F1`, V245-5 reads `F2..`, V245-7 reads `## Cache size`, V245-11 reads `U2..`.

Rules this task applies:
- **Byte-identical fix** (spec § Task 0 step 4): a fix may only remove a call whose inputs equal those of an earlier call in the same `_scan_one` (same frame values, same parameters), returning the earlier result. Never an incremental or rolling-update reformulation: incremental `ewm`/`rolling` is not float byte-identical (spec § Exact prefix caching table).
- **Prefix-pure unit** (spec § Exact prefix caching): a pure function of `df.iloc[:m]`, `m = len(df) - W`, that reads neither `current_price` nor `now`, and that can be split from its per-scan remainder without a float difference. Everything in the index § Global Constraints never-cache list is out, whatever the profile says.
- Long runs checkpoint (CLAUDE.md): the profile runs in chunks of 20 tickers, each chunk persisted as it finishes; a restart skips finished chunks.

- [ ] **Step 1: Bring the local replica up to date**

Run `/replicate-prod-db` (the watchlist comes from Postgres). Then:
`python -c "from swingbot.core.marketdata.watchlist import load_watchlist; print(len(load_watchlist()))"`
Expected: about 92 (production's watchlist size, spec § Why). A very
different count means the replica is stale: stop and report.

- [ ] **Step 2: Profile in persisted chunks**

```bash
python - <<'EOF'
import os, subprocess, sys
sys.path.insert(0, ".")
from swingbot.core.marketdata.watchlist import load_watchlist
tickers = sorted(t.upper() for t in load_watchlist())
os.makedirs("logs/v245-profile", exist_ok=True)
for k in range(0, len(tickers), 20):
    out = f"logs/v245-profile/chunk-{k // 20:02d}.json"
    if os.path.exists(out):
        continue                                  # finished chunk: a restart skips it
    subprocess.run([sys.executable, "scripts/perf/profile_analysis.py",
                    "--tickers", ",".join(tickers[k:k + 20]), "--out", out], check=True)
    print("done", out, flush=True)
EOF
python scripts/perf/profile_analysis.py --journal --tickers "$(python -c "import json; print(','.join(sorted(json.load(open('logs/v245-profile/chunk-00.json'))['memory']['per_ticker'])))")" --out logs/v245-profile/journal-00.json
```

Expected: five chunk JSONs (`chunk-00..04.json`) each with its two `.prof`
files, and `journal-00.json` (the same 20 tickers as chunk 00, with the
read-only journal track record). A chunk that dies is rerun by running the
block again.

- [ ] **Step 3: Merge the chunks**

```bash
python - <<'EOF'
import glob, json, pstats, sys
sys.path.insert(0, ".")
from scripts.perf import profile_analysis as pa
chunks = sorted(glob.glob("logs/v245-profile/chunk-[0-9][0-9].json"))
docs = [json.load(open(c, encoding="utf-8")) for c in chunks]
merged = {"tickers": sum(d["tickers"] for d in docs),
          "missing": sorted(m for d in docs for m in d["missing"]),
          "bars_median": sorted(d["bars"]["median"] for d in docs)[len(docs) // 2]}
for run in ("completed", "forming"):
    stats = pstats.Stats(*[c[:-5] + f"-{run}.prof" for c in chunks])
    total = sum(d["runs"][run]["total_s"] for d in docs)
    merged[run] = {"total_s": round(total, 3), "per_ticker_s": round(total / merged["tickers"], 4),
                   "candidates": pa.candidate_shares(stats, total)}
per_ticker = {t: r for d in docs for t, r in d["memory"]["per_ticker"].items()}
merged["memory"] = {"analysis_peak_mb": max(d["memory"]["analysis_peak_mb"] for d in docs),
                    "per_ticker_bytes": {k: pa._dist([r[k] for r in per_ticker.values()])
                                         for k in ("pickled", "retained")},
                    "pivots_max": max(max(r["pivots"].values()) for r in per_ticker.values())}
json.dump(merged, open("logs/v245-profile/merged.json", "w", encoding="utf-8"), indent=1)
print(json.dumps({k: merged[k] for k in ("tickers", "missing", "memory")}, indent=1))
EOF
```

Expected: `logs/v245-profile/merged.json`; the printout shows the ticker
count, the tickers without a local frame, and the memory figures.

- [ ] **Step 4: Drill into call counts**

```bash
python -c "import pstats; s=pstats.Stats('logs/v245-profile/chunk-00-forming.prof'); s.sort_stats('cumulative').print_stats(45)" > logs/v245-profile/top45.txt
python -c "import pstats; s=pstats.Stats('logs/v245-profile/chunk-00-forming.prof'); [s.print_callers(f) for f in ('zigzag_pivots','_volume_confirmed_pivots','ema','atr','rolling_vwap','bollinger_bands','horizon_trend','count_confirming_strategies')]" > logs/v245-profile/callers.txt
```

Read both files. For each duplicated call establish: calls per ticker, which
callers, and whether the arguments are equal across those calls (read the
call sites). The known suspects, to confirm or refute with numbers:
- `zigzag_pivots` from `_volume_confirmed_pivots`: `custom_scanner_levels`
  calls `_find_best_trendline` once per side, and each trims the same frame
  and runs zigzag at `PIVOT_THRESHOLD_PCT=3.0` on it: two identical zigzags
  per ticker (V245-4's prepared design).
- `zigzag_pivots` from `collect_candidate_levels` (levels.py:~276) at
  `h["max_risk_pct"]` once per horizon: horizons sharing a `max_risk_pct`
  compute identical pivots.
- `ema`/`atr`/`rolling_vwap`/`bollinger_bands` per horizon with the same
  window on the same frame (`atr(df, 14)` in `levels.atr_floor_pct` for
  every horizon, plus `_band_live` and confidence): V245-5's prepared memo.
- `count_confirming_strategies` twice per scenario over the same
  `candidates` with different targets: name any target-independent work
  inside it that both calls redo (levels.py:499).
- `get_htf_bias` / `adjacent_aligned` / `macro_aligned`: per scenario, but
  the trend they read depends only on `(df, horizon_key)`; check whether
  the direction-independent part is computed twice for a horizon with both
  a bullish and a bearish scenario.

- [ ] **Step 5: Tag every candidate**

Start from these expected tags and confirm each against the cited code;
where the code disagrees, change the tag and write the line that proves it
in the Evidence column.

| Candidate | Last row | `current_price` | Prefix-pure | Expected evidence |
|---|---|---|---|---|
| `custom_scanner_levels`, `_find_best_trendline` | y | y | split → U1 | `n_bars`, `line_at_now` at `len-1`, both price gates (trendlines.py:234-246) |
| `_volume_confirmed_pivots`, `zigzag_pivots` | y | n | pivots older than the confirmation window only | zigzag's last pivots are unconfirmed extremes (trendlines.py:142-208, indicators.py:73) |
| `_score_candidate` | y | y | n | `recency`, `n_bars`, price gates |
| `trendline_levels`, `_trendln_fallback_levels` | y | y | n | spec table, never cached |
| `_horizon_scenarios`, `build_level_map`, `_cluster_levels`, `build_scenarios` | y | y | n | candidate set includes per-scan sources (levels.py:114) |
| `collect_candidate_levels` | y | y | n | `iloc[-1]` sources, floor pivots `iloc[-2]` (levels.py:320) |
| `_fvg_candidates` | y | per levels.py:180 | n | read levels.py:180 |
| `atr_floor_pct` | y | y | n | `atr(df, 14).iloc[-1] / current_price` |
| `count_confirming_strategies` | n (given `candidates`) | y | n | pure over `candidates` and target (levels.py:499) |
| `score_confidence`, `_build_requirement_checks` | y | y | n | scenario + df |
| `get_htf_bias`, `macro_aligned`, `adjacent_aligned` | y | n | n | last close |
| `_rs_pctile`, E12 `liquidity_reason`, E16 `data_quality_issues` | y | n | n | tail windows |
| `_apply_pullback_dryup`, `_band_live` | y (`now`) | `_band_live` y | n | `completed_frame(df, now)` |
| `_apply_headroom` | n | y (scenarios) | n | levels and scenario only |
| `ema`, `atr`, `rolling_vwap`, `bollinger_bands`, `fibonacci_levels` | y | n | n | series end at the last row; incremental is not byte-identical |

- [ ] **Step 6: Write the results doc**

Create `docs/superpowers/results/2026-11-23-v245-analysis-profile.md` with
this structure, every value filled from `merged.json`, `journal-00.json`,
`top45.txt`, `callers.txt` and Step 5:

~~~markdown
# v245 — Analysis profile (Task 0)

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Plan:** [index](../plans/2026-11-23-v245-exact-analysis-cache_0-index.md), task V245-3
**Run:** <UTC date>, commit <short sha>, <N> tickers from the local replica's watchlist (<M> without a local frame: <tickers>), frames trimmed to 2515 bars (median <b>), horizons 2w..9m, <CPU model>.

Shares are local and relative. The 0.7 s per ticker target is judged only
from production `phases_s` (V245-6), never from these numbers.

## Shares

<table: one row per CANDIDATES label, columns: completed share, completed calls/ticker, forming share, forming calls/ticker; sorted by forming share; `_scan_one` = 100 %>

<one paragraph: local s/ticker completed and forming; journal track-record share from journal-00.json; not measured: update_open_trades / _check_near_close (they write; production pays them per ticker inside the analysis phase)>

## Tags

<Step 5's table, Evidence column with file:line for every row>

## Bytes per object

<per-ticker trendline entry bytes (both sides) pickled and retained: median / p95 / max; largest pivot count; analysis peak MB; note that the estimate keeps the two unstable pivots V245-8 leaves to the tail, so it errs high>

## Byte-identical fixes

| Id | Hot spot | Calls/ticker now -> after | Share saved (forming) | Why byte-identical | Files |
|---|---|---|---|---|---|
| F1 | ... | ... | ... | ... | ... |

<ranked by share saved, largest first; ties go to the smaller diff; each row names the equal-input calls it removes>

## Prefix-pure units

| Id | Unit | Window W | Horizon-specific | Share (forming) | Verdict |
|---|---|---|---|---|---|
| U1 | trendline pair search (confirmed pivots, pair geometry and touches against confirmed pivots) | 1 bar + 2 unstable pivots (index Decision 4) | no | ... | build in V245-8 |

<every other candidate tagged prefix-pure, with its verdict; "none beyond U1" is a valid outcome and is stated as such>

## Cache size

<per-entry p95 retained bytes = per-ticker p95 / 2; entries that fit 150 MB = floor(150e6 / per-entry p95); recommended STRUCTURE_CACHE_MAX = min(600, that figure), with the arithmetic shown>

## What Part 2 takes

<V245-4 takes F1; V245-5 takes F2 onward (as many as stay byte-identical, one commit each); if F1 is not V245-4's prepared design, say which file it touches instead>
~~~

The doc's ranking, not the plan's prepared designs, decides what V245-4 and
V245-5 build. If the zigzag duplicate or the indicator memo saves less than
1 % of forming time, rank it below whatever the numbers put first.

- [ ] **Step 7: Check the doc's shape**

```bash
python -c "import pathlib,sys; t=pathlib.Path('docs/superpowers/results/2026-11-23-v245-analysis-profile.md').read_text(encoding='utf-8'); need=('## Shares','## Tags','## Bytes per object','## Byte-identical fixes','## Prefix-pure units','## Cache size','## What Part 2 takes','| F1 |','| U1 |','STRUCTURE_CACHE_MAX'); miss=[h for h in need if h not in t]; print(miss or 'OK'); sys.exit(bool(miss))"
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
```

Expected: `OK`, then the golden PASSES unchanged (`0 failed`). No `<...>`
fill-in marker is left in the doc (`grep -n "<" docs/superpowers/results/2026-11-23-v245-analysis-profile.md` shows only real comparisons or links).

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/results/2026-11-23-v245-analysis-profile.md
git commit -m "docs(v245): analysis profile, hot-spot tags, ranked fixes and cache size (V245-3)"
```
