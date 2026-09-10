# v74 part 1 — `ScanParams` and the seam

Header, global constraints and parallelisation: `2026-09-09-v74-injectable-scan-params_0-index.md`. **Read that first** — its Global Constraints are part of every task below.

---

### Task A1: The `ScanParams` record

**Files:**
- Create: `swingbot/scan_params.py`
- Test: `tests/test_scan_params.py`

**Interfaces:**
- Consumes: `swingbot.config` module globals only.
- Produces: `ScanParams` (frozen dataclass), `ScanParams.from_config() -> ScanParams`. Later tasks vary it with `dataclasses.replace(params, min_target_confluence_count=1)`.

**Why a new module rather than extending `swingbot/core/planning/params.py`:** that file holds exit-v2 constants and badge helpers, and it imports `swingbot.core.backtesting.registry`. `ScanParams` must sit *below* both scanning and planning to avoid an import cycle, so it goes top-level beside `config.py`. It is named `scan_params.py`, never `params.py`, so the two are never confused in a traceback.

**Frozen constants that are NOT config fields:** `BREAKEVEN_TRIGGER_FRACTION` (`swingbot/core/backtesting/backtest.py`) and `TP1_FRACTION` (`swingbot/core/planning/params.py`) are module constants, not `config.FIELDS` entries. They are **deliberately excluded** from `ScanParams` in v74: nothing in this seam varies them, and importing `core.backtesting` from `scan_params` would invert the layering the module exists to keep clean. This is a recorded decision, not an oversight — v75 adds them if its search needs them.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan_params.py
"""ScanParams is the contract v75's search engine depends on: frozen so no
worker can mutate a shared cell, picklable so cells cross a process pool.
Both properties are asserted here rather than assumed."""
import dataclasses
import pickle

import pytest

from swingbot import config
from swingbot.scan_params import ScanParams


def test_from_config_reads_the_shipped_defaults():
    p = ScanParams.from_config()
    assert p.min_target_confluence_count == config.MIN_TARGET_CONFLUENCE_COUNT
    assert p.min_risk_reward_ratio == config.MIN_RISK_REWARD_RATIO
    assert p.min_reward_pct == config.MIN_REWARD_PCT
    assert p.avwap_levels_enabled == config.AVWAP_LEVELS_ENABLED


def test_is_frozen():
    p = ScanParams.from_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.min_target_confluence_count = 99


def test_survives_a_pickle_round_trip():
    """v75 scores grid cells in a ProcessPoolExecutor. A cell that cannot be
    pickled cannot be a cell."""
    p = ScanParams.from_config()
    assert pickle.loads(pickle.dumps(p)) == p


def test_replace_produces_an_independent_value():
    p = ScanParams.from_config()
    q = dataclasses.replace(p, min_target_confluence_count=1)
    assert q.min_target_confluence_count == 1
    assert p.min_target_confluence_count == config.MIN_TARGET_CONFLUENCE_COUNT
    assert q != p


def test_every_field_is_immutable_typed():
    """A list/dict/set field would break both frozen-ness and hashing. Tuples
    only -- this test is what stops a future task regressing that."""
    for f in dataclasses.fields(ScanParams):
        assert not isinstance(getattr(ScanParams.from_config(), f.name), (list, dict, set)), f.name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scan_params.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.scan_params'`.

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/scan_params.py
"""The trade-plan decision surface as one frozen, passable value.

Read docs/claude/known-traps.md before changing this. Config is module
globals that reload() mutates in place on SIGHUP; a grid that varies a knob
by mutating those globals is, in backtest_scenarios.replay_scenarios' own
words, "a global the workers fight over". ScanParams is the alternative:
built once at the boundary with from_config(), varied with
dataclasses.replace(), and passed down explicitly.

Frozen and tuple-only so it is hashable and picklable -- v75 scores grid
cells in a process pool and each cell is one of these.

NOT named params.py: swingbot/core/planning/params.py already exists and
holds exit-v2 constants. Two modules named `params` is a reading hazard.
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot import config


@dataclass(frozen=True)
class ScanParams:
    # --- gating: which setups become alerts at all (class 1) ---
    min_reward_pct: float
    min_stop_distance_pct: float
    max_stop_loss_pct: float
    confluence_deviation_pct: float
    min_target_confluence_count: int
    min_alert_confidence_level: str
    unified_confidence: bool
    dedup_tolerance_pct: float
    max_alerts_per_scan: int
    earnings_blackout_days: int

    # --- relative strength (class 1) ---
    rs_gate: bool
    rs_leader_percentile: float
    rs_laggard_percentile: float

    # --- multi-timeframe (class 1) ---
    htf_confluence_enabled: bool
    mtf_adjacent_gate: bool

    # --- opex calendar adjustments (class 1) ---
    opex_caution_enabled: bool
    opex_monthly_confidence_bump: float
    opex_monthly_confluence_bump: float
    opex_weekly_confluence_bump: float
    opex_stop_widen_pct: float
    opex_size_reduction_pct: float

    # --- level construction and stops (class 1) ---
    avwap_levels_enabled: bool
    volume_profile_nodes_enabled: bool
    level_lifecycle_stops_enabled: bool
    data_driven_stops_enabled: bool
    regime_gates_enabled: bool
    pyramiding_enabled: bool

    # --- plan engine (class 1) ---
    plan_engine_v2: bool
    scale_out_enabled: bool

    # --- universe (class 1) ---
    universe_min_dollar_vol: float
    universe_min_price: float

    # --- dead-cat-bounce veto (class 1, v68) ---
    dead_cat_bounce_veto: bool
    dcb_decline_pct: float
    dcb_gap_required: bool
    dcb_volume_ratio: float

    # --- frozen band: injectable so the harness sees it, never tuned here
    #     (class 2). v72's geometry-lock clause watches this axis. ---
    min_risk_reward_ratio: float
    max_risk_reward_ratio: float

    # --- measurement fidelity: never searchable, tuning these is
    #     self-deception (class 4) ---
    slippage_bps: float
    commission_per_trade: float
    commission_risk_basis: str

    @classmethod
    def from_config(cls) -> "ScanParams":
        """The live default. Reads each config global once, at the boundary."""
        return cls(
            min_reward_pct=config.MIN_REWARD_PCT,
            min_stop_distance_pct=config.MIN_STOP_DISTANCE_PCT,
            max_stop_loss_pct=config.MAX_STOP_LOSS_PCT,
            confluence_deviation_pct=config.CONFLUENCE_DEVIATION_PCT,
            min_target_confluence_count=config.MIN_TARGET_CONFLUENCE_COUNT,
            min_alert_confidence_level=config.MIN_ALERT_CONFIDENCE_LEVEL,
            unified_confidence=config.UNIFIED_CONFIDENCE,
            dedup_tolerance_pct=config.DEDUP_TOLERANCE_PCT,
            max_alerts_per_scan=config.MAX_ALERTS_PER_SCAN,
            earnings_blackout_days=config.EARNINGS_BLACKOUT_DAYS,
            rs_gate=config.RS_GATE,
            rs_leader_percentile=config.RS_LEADER_PERCENTILE,
            rs_laggard_percentile=config.RS_LAGGARD_PERCENTILE,
            htf_confluence_enabled=config.HTF_CONFLUENCE_ENABLED,
            mtf_adjacent_gate=config.MTF_ADJACENT_GATE,
            opex_caution_enabled=config.OPEX_CAUTION_ENABLED,
            opex_monthly_confidence_bump=config.OPEX_MONTHLY_CONFIDENCE_BUMP,
            opex_monthly_confluence_bump=config.OPEX_MONTHLY_CONFLUENCE_BUMP,
            opex_weekly_confluence_bump=config.OPEX_WEEKLY_CONFLUENCE_BUMP,
            opex_stop_widen_pct=config.OPEX_STOP_WIDEN_PCT,
            opex_size_reduction_pct=config.OPEX_SIZE_REDUCTION_PCT,
            avwap_levels_enabled=config.AVWAP_LEVELS_ENABLED,
            volume_profile_nodes_enabled=config.VOLUME_PROFILE_NODES_ENABLED,
            level_lifecycle_stops_enabled=config.LEVEL_LIFECYCLE_STOPS_ENABLED,
            data_driven_stops_enabled=config.DATA_DRIVEN_STOPS_ENABLED,
            regime_gates_enabled=config.REGIME_GATES_ENABLED,
            pyramiding_enabled=config.PYRAMIDING_ENABLED,
            plan_engine_v2=config.PLAN_ENGINE_V2,
            scale_out_enabled=config.SCALE_OUT_ENABLED,
            universe_min_dollar_vol=config.UNIVERSE_MIN_DOLLAR_VOL,
            universe_min_price=config.UNIVERSE_MIN_PRICE,
            dead_cat_bounce_veto=config.DEAD_CAT_BOUNCE_VETO,
            dcb_decline_pct=config.DCB_DECLINE_PCT,
            dcb_gap_required=config.DCB_GAP_REQUIRED,
            dcb_volume_ratio=config.DCB_VOLUME_RATIO,
            min_risk_reward_ratio=config.MIN_RISK_REWARD_RATIO,
            max_risk_reward_ratio=config.MAX_RISK_REWARD_RATIO,
            slippage_bps=config.SLIPPAGE_BPS,
            commission_per_trade=config.COMMISSION_PER_TRADE,
            commission_risk_basis=config.COMMISSION_RISK_BASIS,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scan_params.py -v`
Expected: PASS, 5 tests.

If `test_from_config_reads_the_shipped_defaults` fails with `AttributeError`, a field name above does not match its `Field.attr` in `swingbot/config.py`. Fix the `ScanParams` field name to match config — never the other way round.

- [ ] **Step 5: Commit**

```bash
git add swingbot/scan_params.py tests/test_scan_params.py
git commit -m "feat(v74): ScanParams -- the decision surface as one passable value"
```

---

### Task A2: Classify all 121 config fields

**Files:**
- Modify: `swingbot/config.py:74-93` (the `Field` dataclass), and the `FIELDS` list entries named below
- Test: `tests/test_scan_params_coverage.py`

**Interfaces:**
- Consumes: `ScanParams` from A1.
- Produces: `config.Field.search_class` (`"searchable" | "frozen" | "live_only" | "never" | "excluded"`), and `config.searchable_attrs() -> tuple[str, ...]`.

Putting the class on `Field` itself means config stays the single source of truth and the classification cannot drift into a separate registry. **`"excluded"` is the default**, so only classes 1–4 are enumerated below; every unlisted field is excluded by omission, which is the safe direction — a field wrongly excluded is invisible to a search, while a field wrongly searchable produces silent no-op cells.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan_params_coverage.py
"""The classification and ScanParams must agree exactly. Drift here is how a
search silently loses a knob (or gains a no-op one), which is spec finding 5
in miniature."""
import dataclasses

from swingbot import config
from swingbot.scan_params import ScanParams

VALID = {"searchable", "frozen", "live_only", "never", "excluded"}


def test_every_field_has_a_valid_class():
    for f in config.FIELDS:
        assert f.search_class in VALID, f"{f.attr} has search_class={f.search_class!r}"


def test_scan_params_covers_exactly_the_non_excluded_config_fields():
    in_params = {f.name.upper() for f in dataclasses.fields(ScanParams)}
    in_config = {f.attr for f in config.FIELDS
                 if f.search_class in ("searchable", "frozen", "never")}
    assert in_config - in_params == set(), f"classified but not in ScanParams: {in_config - in_params}"
    assert in_params - in_config == set(), f"in ScanParams but not classified: {in_params - in_config}"


def test_searchable_attrs_excludes_frozen_and_never():
    attrs = set(config.searchable_attrs())
    assert "MIN_RISK_REWARD_RATIO" not in attrs      # frozen: needs its own pre-registration
    assert "SLIPPAGE_BPS" not in attrs               # never: tuning it is self-deception
    assert "NEAR_TP_TIMEOUT_MINUTES" not in attrs    # live_only: no sub-daily resolution
    assert "DISCORD_TOKEN" not in attrs              # excluded
    assert "MIN_TARGET_CONFLUENCE_COUNT" in attrs


def test_the_measurement_fidelity_knobs_are_never_searchable():
    """Lowering modelled slippage improves every number and buys zero edge.
    This test is the thing that stops a future grid including it by accident."""
    for attr in ("SLIPPAGE_BPS", "COMMISSION_PER_TRADE", "COMMISSION_RISK_BASIS"):
        f = next(f for f in config.FIELDS if f.attr == attr)
        assert f.search_class == "never", attr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scan_params_coverage.py -v`
Expected: FAIL — `AttributeError: 'Field' object has no attribute 'search_class'`.

- [ ] **Step 3: Write minimal implementation**

Add the attribute to the `Field` dataclass in `swingbot/config.py`, after `hot_reloadable`:

```python
    hot_reloadable: bool = True     # see module docstring
    #: v74 search classification. "excluded" is the default and the safe
    #: direction: a field wrongly excluded is merely invisible to a search,
    #: while a field wrongly "searchable" produces grid cells that differ
    #: only by noise. See docs/superpowers/specs/2026-09-09-v74-injectable-
    #: scan-params-design.md for what each class means.
    #:   searchable -- a decision knob a daily-bar replay can observe
    #:   frozen     -- injectable, but changing it needs a pre-registration
    #:   live_only  -- wall-clock/intraday; this harness cannot measure it
    #:   never      -- measurement fidelity; tuning it is self-deception
    #:   excluded   -- not a trade-plan decision knob at all
    search_class: str = "excluded"
```

Then add `search_class=` to the `FIELDS` entries below and nowhere else.

`search_class="searchable"` — `MIN_REWARD_PCT`, `MIN_STOP_DISTANCE_PCT`, `MAX_STOP_LOSS_PCT`, `CONFLUENCE_DEVIATION_PCT`, `MIN_TARGET_CONFLUENCE_COUNT`, `MIN_ALERT_CONFIDENCE_LEVEL`, `UNIFIED_CONFIDENCE`, `DEDUP_TOLERANCE_PCT`, `RS_GATE`, `RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE`, `OPEX_CAUTION_ENABLED`, `OPEX_MONTHLY_CONFIDENCE_BUMP`, `OPEX_MONTHLY_CONFLUENCE_BUMP`, `OPEX_WEEKLY_CONFLUENCE_BUMP`, `OPEX_STOP_WIDEN_PCT`, `OPEX_SIZE_REDUCTION_PCT`, `HTF_CONFLUENCE_ENABLED`, `MTF_ADJACENT_GATE`, `PLAN_ENGINE_V2`, `SCALE_OUT_ENABLED`, `UNIVERSE_MIN_DOLLAR_VOL`, `UNIVERSE_MIN_PRICE`, `EARNINGS_BLACKOUT_DAYS`, `REGIME_GATES_ENABLED`, `LEVEL_LIFECYCLE_STOPS_ENABLED`, `AVWAP_LEVELS_ENABLED`, `PYRAMIDING_ENABLED`, `VOLUME_PROFILE_NODES_ENABLED`, `MAX_ALERTS_PER_SCAN`, `DATA_DRIVEN_STOPS_ENABLED`, `DEAD_CAT_BOUNCE_VETO`, `DCB_DECLINE_PCT`, `DCB_GAP_REQUIRED`, `DCB_VOLUME_RATIO`.

`search_class="frozen"` — `MIN_RISK_REWARD_RATIO`, `MAX_RISK_REWARD_RATIO`.

`search_class="live_only"` — `SESSION_START_HOUR`, `SESSION_END_HOUR`, `SCAN_INTERVAL_MINUTES`, `SIGNAL_CONFIRMATION_SCANS`, `NEAR_CLOSE_ALERTS_ENABLED`, `NEAR_CLOSE_THRESHOLD_PCT`, `REVERSAL_ENABLED`, `REVERSAL_MIN_HOLD_HOURS`, `REVERSAL_COOLDOWN_HOURS`, `REVERSAL_MIN_CONF_MARGIN`, `REVERSAL_MAX_PER_DAY`, `NEAR_TP_TIMEOUT_ENABLED`, `NEAR_TP_TIMEOUT_THRESHOLD_PCT`, `NEAR_TP_TIMEOUT_MINUTES`, `NEAR_TP_STALL_CHECK_MINUTES`, `NEAR_TP_STALL_MAX_FLUCTUATION_PCT`, `OPEX_NEAR_CLOSE_SUPPRESS_MINUTES`, `INTRADAY_MANAGER_V2`, `INTRADAY_RTH_ONLY`, `EXTENDED_HOURS_EXIT_CHECK`, `QUIET_HOURS_START_ET`, `QUIET_HOURS_END_ET`, `EXTENDED_HOURS_DEBOUNCE_TICKS`.

`search_class="never"` — `SLIPPAGE_BPS`, `COMMISSION_PER_TRADE`, `COMMISSION_RISK_BASIS`.

Everything else keeps the `"excluded"` default — including all 15 Account Defaults, which are portfolio-level and belong to `backtest_wf.portfolio_replay`'s unit of analysis, not per-trade selection.

Add the accessor at the end of `swingbot/config.py`:

```python
def searchable_attrs() -> tuple[str, ...]:
    """The knobs v75's search engine may vary. Deliberately excludes
    "frozen" (needs its own pre-registration), "never" (measurement
    fidelity) and "live_only" (this harness cannot see them)."""
    return tuple(f.attr for f in FIELDS if f.search_class == "searchable")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scan_params_coverage.py tests/test_scan_params.py -v`
Expected: PASS.

`test_scan_params_covers_exactly_the_non_excluded_config_fields` is the one that will fail if A1's field list and this classification disagree — its assertion message names the offending attrs. Reconcile by editing whichever side is wrong; do not weaken the test.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py tests/test_scan_params_coverage.py
git commit -m "feat(v74): classify all 121 config fields by searchability"
```

---

### Task B1: `builders.py` takes `params`

**Files:**
- Modify: `swingbot/core/planning/builders.py:54,273,350,367,390`
- Test: `tests/planning/test_builders_params.py`

**Interfaces:**
- Consumes: `ScanParams` from A1.
- Produces: `build_confluence_plan(..., params: ScanParams | None = None)`. `None` means `ScanParams.from_config()`, preserving every existing call site unchanged.

`builders.py` reads config in exactly five places and every one of them is the same pair — `config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO`. This is the whole shared-layer config dependency.

- [ ] **Step 1: Write the failing test**

```python
# tests/planning/test_builders_params.py
"""build_confluence_plan is shared by the live scan and replay_scenarios
(backtest_scenarios.py's docstring: "the SAME plan constructor"). Threading
params here is what makes the RR band visible to a search without touching
either caller."""
import dataclasses

from swingbot import config
from swingbot.core.planning.builders import build_confluence_plan
from swingbot.scan_params import ScanParams


#: The plan fields this seam can move. Deliberately NOT dataclasses.asdict():
#: TradePlanV2 carries plan_id and created_at, which differ between two calls
#: for reasons that have nothing to do with params.
PRICES = ("trigger_price", "entry_price", "stop_loss", "tp1", "tp2")


def _prices(plan):
    return None if plan is None else tuple(getattr(plan, f) for f in PRICES)


def test_params_none_matches_the_config_globals(confluence_scenario, ohlcv_df):
    """The default path must be byte-identical to today -- global constraint 1."""
    a = build_confluence_plan(confluence_scenario, ohlcv_df, ticker="AAPL",
                              horizon_key="3m", primary_strategy="MACD")
    b = build_confluence_plan(confluence_scenario, ohlcv_df, ticker="AAPL",
                              horizon_key="3m", primary_strategy="MACD",
                              params=ScanParams.from_config())
    assert _prices(a) == _prices(b)


def test_a_wider_rr_band_changes_the_selected_target(confluence_scenario, ohlcv_df):
    """If this passes with identical targets, the RR band is not actually
    reaching select_structural_target and the thread is incomplete."""
    base = ScanParams.from_config()
    wide = dataclasses.replace(base, min_risk_reward_ratio=0.1,
                               max_risk_reward_ratio=10.0)
    a = build_confluence_plan(confluence_scenario, ohlcv_df, ticker="AAPL",
                              horizon_key="3m", primary_strategy="MACD",
                              params=base)
    b = build_confluence_plan(confluence_scenario, ohlcv_df, ticker="AAPL",
                              horizon_key="3m", primary_strategy="MACD",
                              params=wide)
    assert (a is None) != (b is None) or a.tp1 != b.tp1
```

Add the two fixtures to `tests/planning/conftest.py` (create the file if absent):

```python
# tests/planning/conftest.py
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import levels


@pytest.fixture
def ohlcv_df():
    """160 bars of a gently trending synthetic series -- enough for the
    3m horizon's warmup, deterministic so target selection is stable."""
    idx = pd.date_range("2023-01-02", periods=160, freq="B")
    close = np.linspace(100.0, 130.0, 160)
    return pd.DataFrame({"Open": close - 0.4, "High": close + 1.0,
                         "Low": close - 1.0, "Close": close,
                         "Volume": np.full(160, 1_000_000.0)}, index=idx)


@pytest.fixture
def confluence_scenario(ohlcv_df):
    price = float(ohlcv_df["Close"].iloc[-1])
    supports, resistances = levels.build_level_map(
        ohlcv_df, {"bars": 60, "label": "3m"}, price)
    scs = levels.build_scenarios(price, supports, resistances, 3.0,
                                 atr_floor=1.0, min_stop_distance_pct=2.0,
                                 max_stop_distance_pct=7.0, min_risk_reward=0.5)
    if not scs:
        pytest.skip("synthetic frame produced no scenario; adjust the fixture")
    return scs[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_builders_params.py -v`
Expected: FAIL — `TypeError: build_confluence_plan() got an unexpected keyword argument 'params'`.

- [ ] **Step 3: Write minimal implementation**

In `swingbot/core/planning/builders.py`, add the parameter to the signature at line 251:

```python
def build_confluence_plan(scenario, df, *, ticker, horizon_key,
                          primary_strategy, level_map=None,
                          quality_inputs=None, params=None) -> TradePlanV2 | None:
```

At the top of the body, before `entry = scenario.entry`:

```python
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
```

The lazy import matches the established seam idiom in this package — `planning/params.py:_journal_entries` uses the same deferred-import pattern with the same rationale (keep the import graph shallow at module load).

Then replace each of the five `config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO` pairs (lines 54, 273, 350, 367, 390) with `params.min_risk_reward_ratio, params.max_risk_reward_ratio`.

Line 54 sits in a different function from `build_confluence_plan`. Give that function the same `params=None` keyword and the same three-line default block, and pass `params=params` from every in-module caller. Do not leave a single `config.MIN_RISK_REWARD_RATIO` read in the file — `grep -n "config\.MIN_RISK_REWARD_RATIO\|config\.MAX_RISK_REWARD_RATIO" swingbot/core/planning/builders.py` must return nothing when this step is done.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/planning/test_builders_params.py`
Then the existing planning suite, which is the real regression check:
Run: `python scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py`
Expected: PASS on both. A failure in `test_exit_parity.py` means the default path changed — global constraint 1 is violated and the cause must be found, not the test adjusted.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/builders.py tests/planning/
git commit -m "feat(v74): builders.py takes ScanParams; RR band stops being a global read"
```

---

### Task B2: `levels.py` takes `params`

**Files:**
- Modify: `swingbot/core/market/levels.py:372,397`
- Test: `tests/market/test_levels_params.py`

**Interfaces:**
- Consumes: `ScanParams` from A1.
- Produces: `build_level_map(..., params: ScanParams | None = None)`.

`levels.py` reads config in exactly two live places: `config.AVWAP_LEVELS_ENABLED` (line 372) and `config.VOLUME_PROFILE_NODES_ENABLED` (line 397). Both are class-1 searchable knobs that decide which level families exist, so they change which scenarios can be built at all.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_levels_params.py
"""AVWAP and volume-profile levels are level *families*: turning one off
removes candidate levels, which changes which scenarios exist. That is
exactly why they must be searchable, and exactly why a global read makes
them unsearchable in a worker pool."""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import levels
from swingbot.scan_params import ScanParams


@pytest.fixture
def df():
    idx = pd.date_range("2023-01-02", periods=200, freq="B")
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1.2, 200))
    return pd.DataFrame({"Open": close - 0.3, "High": close + 1.2,
                         "Low": close - 1.2, "Close": close,
                         "Volume": rng.integers(5e5, 2e6, 200).astype(float)},
                        index=idx)


def test_params_none_matches_the_config_globals(df):
    price = float(df["Close"].iloc[-1])
    h = {"bars": 60, "label": "3m"}
    a = levels.build_level_map(df, h, price)
    b = levels.build_level_map(df, h, price, params=ScanParams.from_config())
    assert [lv.price for lv in a[0]] == [lv.price for lv in b[0]]
    assert [lv.price for lv in a[1]] == [lv.price for lv in b[1]]


def test_disabling_avwap_removes_avwap_levels(df):
    price = float(df["Close"].iloc[-1])
    h = {"bars": 60, "label": "3m"}
    on = dataclasses.replace(ScanParams.from_config(), avwap_levels_enabled=True)
    off = dataclasses.replace(ScanParams.from_config(), avwap_levels_enabled=False)
    n_on = sum(len(x) for x in levels.build_level_map(df, h, price, params=on))
    n_off = sum(len(x) for x in levels.build_level_map(df, h, price, params=off))
    assert n_off < n_on
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/market/test_levels_params.py -v`
Expected: FAIL — `TypeError: build_level_map() got an unexpected keyword argument 'params'`.

- [ ] **Step 3: Write minimal implementation**

Add `params=None` to `build_level_map`'s signature, resolve it with the same three-line lazy-import default block used in B1, and replace:

- line 372: `if config.AVWAP_LEVELS_ENABLED:` → `if params.avwap_levels_enabled:`
- line 397: `if config.VOLUME_PROFILE_NODES_ENABLED:` → `if params.volume_profile_nodes_enabled:`

If either flag is read inside a helper `build_level_map` calls rather than in its own body, thread `params` into that helper too with the same `params=None` default. `grep -n "config\.AVWAP_LEVELS_ENABLED\|config\.VOLUME_PROFILE_NODES_ENABLED" swingbot/core/market/levels.py` must return only comment lines when this step is done.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_levels_params.py`
Expected: PASS.

If `test_disabling_avwap_removes_avwap_levels` fails with equal counts, the flag is not reaching level construction — that is the real bug, not the test.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/levels.py tests/market/test_levels_params.py
git commit -m "feat(v74): levels.py takes ScanParams for its two family flags"
```

---

### Task B3: Extract the gating into one pure module

**Files:**
- Create: `swingbot/core/scanning/gating.py`
- Modify: `swingbot/core/backtesting/backtest_scenarios.py:44-52,87,104-126`
- Test: `tests/scanning/test_gating.py`

**Interfaces:**
- Consumes: `ScanParams` from A1.
- Produces: `scenario_gate_inputs(params, horizon) -> dict` and `passes_confluence(n_confluent, params) -> bool`.

`replay_scenarios` currently spreads gating across three shapes: two `max(...)` expressions computing effective bounds (lines 104–107), four values passed into `levels.build_scenarios` (117–119), and one post-filter (`if n_confl < gates.get("min_confluence", 1)`, line 125). A single `passes_gates(plan, params)` cannot honestly represent that, because two of the three are *inputs* to scenario construction rather than a predicate over a finished plan. Two functions, matching the two real shapes.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_gating.py
"""One implementation of the gate arithmetic, called by both the live scan
and the backtest replay. Spec finding 8: three disagreeing sources of truth
for these same five numbers is how v68 measured a population the live bot
would never alert on."""
import dataclasses

from swingbot.core.scanning.gating import passes_confluence, scenario_gate_inputs
from swingbot.scan_params import ScanParams

H3M = {"bars": 60, "label": "3m", "sr_target_min_pct": 8.0, "max_risk_pct": 9.0}


def test_effective_min_reward_is_the_larger_of_the_two_floors():
    p = dataclasses.replace(ScanParams.from_config(), min_reward_pct=3.0)
    got = scenario_gate_inputs(p, H3M)
    assert got["min_reward_pct"] == max(3.0, 8.0 * 0.15)


def test_effective_max_stop_is_the_larger_of_the_two_ceilings():
    p = dataclasses.replace(ScanParams.from_config(), max_stop_loss_pct=7.0)
    got = scenario_gate_inputs(p, H3M)
    assert got["max_stop_distance_pct"] == max(7.0, 9.0)


def test_a_horizon_without_the_optional_keys_falls_back_to_params():
    p = dataclasses.replace(ScanParams.from_config(), min_reward_pct=3.0,
                            max_stop_loss_pct=7.0)
    got = scenario_gate_inputs(p, {"bars": 20, "label": "2w"})
    assert got["min_reward_pct"] == 3.0
    assert got["max_stop_distance_pct"] == 7.0


def test_confluence_filter_uses_the_params_value():
    p = dataclasses.replace(ScanParams.from_config(), min_target_confluence_count=2)
    assert passes_confluence(2, p) is True
    assert passes_confluence(1, p) is False


def test_shipped_defaults_reproduce_the_old_confluence_gates_dict():
    """CONFLUENCE_GATES was in parity with config. This pins that it stays so
    after the dict is deleted."""
    p = ScanParams.from_config()
    got = scenario_gate_inputs(p, {"bars": 60, "label": "3m"})
    assert got["min_reward_pct"] == 3.0
    assert got["min_stop_distance_pct"] == 2.0
    assert got["max_stop_distance_pct"] == 7.0
    assert got["min_risk_reward"] == 1.5
    assert p.min_target_confluence_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scanning/test_gating.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.scanning.gating'`.

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/scanning/gating.py
"""The gate arithmetic, once.

Before v74 these five numbers existed in three places that could and did
disagree: config's globals, backtest_scenarios.CONFLUENCE_GATES, and
measure_dcb_veto.BASE_GATES (min_confluence 1 against a shipped 2,
min_risk_reward 0.0 against a shipped 1.5). A measurement script that wants
a non-shipped population must now say so with an explicit
dataclasses.replace() a reviewer can see.
"""
from __future__ import annotations

from swingbot.scan_params import ScanParams


def scenario_gate_inputs(params: ScanParams, horizon: dict) -> dict:
    """The four bounds levels.build_scenarios needs, for one horizon.

    Two of them are the larger of a global floor/ceiling and a per-horizon
    one -- a horizon that demands a wider target or tolerates a wider stop
    overrides the global, never the reverse.
    """
    return {
        "min_reward_pct": max(params.min_reward_pct,
                              horizon.get("sr_target_min_pct", 0) * 0.15),
        "min_stop_distance_pct": params.min_stop_distance_pct,
        "max_stop_distance_pct": max(params.max_stop_loss_pct,
                                     horizon.get("max_risk_pct", 0)),
        "min_risk_reward": params.min_risk_reward_ratio,
    }


def passes_confluence(n_confluent: int, params: ScanParams) -> bool:
    """How many strategies must independently confirm a target."""
    return n_confluent >= params.min_target_confluence_count
```

Then in `backtest_scenarios.py`:

1. Change `replay_scenarios`' signature from `*, gates: dict, dcb_params: dict | None = None` to `*, params: ScanParams | None = None, dcb_params: dict | None = None`, resolving `None` to `ScanParams.from_config()`.
2. Replace lines 104–107 and the four `gates[...]` arguments at 117–119 with one call:

```python
        g = scenario_gate_inputs(params, h)
        scenarios = levels.build_scenarios(
            price, supports, resistances, g["min_reward_pct"],
            atr_floor=floor_pct,
            min_stop_distance_pct=g["min_stop_distance_pct"],
            max_stop_distance_pct=g["max_stop_distance_pct"],
            min_risk_reward=g["min_risk_reward"],
            block_bullish=block_bullish)
```

3. Replace line 125 with `if not passes_confluence(n_confl, params): continue`.
4. Replace line 87's `cooldown = gates.get("cooldown_bars", 5)` with `cooldown = 5` and a comment: cooldown is not a config field and is not part of the v74 surface; it stays a literal until a spec makes it one.
5. Pass `params=params` into the `build_confluence_plan` call at line 131.
6. **Delete `CONFLUENCE_GATES` (lines 44–52), but move its 27-line provenance comment (lines 24–43) verbatim** to sit above `ScanParams` usage in this module. That comment is the only record that the July 2026 confluence grid found no qualifying config and that these are unvalidated defaults — spec finding 9. Losing it would delete the evidence.
7. Update every caller: `measure_dcb_veto.py:133`, `tune_confluence_gates.py`, and `tests/backtesting/test_backtest_scenarios.py` / `test_replay_dcb_veto.py` / `test_scenario_parallel.py`. `measure_dcb_veto`'s `BASE_GATES` becomes an explicit deviation and **must keep its divergence visible**:

```python
# v68 measured on a deliberately more permissive population than ships
# (min_confluence 1 vs 2, min_risk_reward 0.0 vs 1.5) to buy sample size.
# v74 makes that deviation explicit instead of a hand-typed dict. Whether
# it was the right call for v68 is an open question for the human partner
# -- see the v74 spec, finding 8. Do NOT silently "fix" it to the shipped
# values: that would change what v72's Task B1 fixture contains.
BASE_PARAMS = dataclasses.replace(
    ScanParams.from_config(), min_target_confluence_count=1,
    min_risk_reward_ratio=0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_gating.py`
Then the replay suites, which are the regression check:
Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/test_replay_dcb_veto.py`
Expected: PASS on all three.

`test_replay_dcb_veto.py` failing means the `BASE_GATES` → `BASE_PARAMS` translation changed v68's population. That is a real behaviour change and must be reconciled to identity, not accepted.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/gating.py swingbot/core/backtesting/backtest_scenarios.py scripts/backtest/measure_dcb_veto.py scripts/backtest/tune_confluence_gates.py tests/scanning/test_gating.py tests/backtesting/
git commit -m "feat(v74): one gating implementation, replacing three that disagreed"
```

---

### Task B4: `scan_run` calls the same gating — or records why it cannot

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py:116-...` (`_sync_run_scan`)
- Test: `tests/scanning/test_gating_live_parity.py`

**Interfaces:**
- Consumes: `scenario_gate_inputs`, `passes_confluence` from B3.
- Produces: no new public symbol; `_sync_run_scan` gains `params: ScanParams | None = None`.

**This task has a halt condition and it is the point of the task.** `scan_run.py` has 33 config reads and its own gating arithmetic. If that arithmetic already matches `scenario_gate_inputs`, replacing it is a no-op refactor and proceeds. **If it differs, unifying them would change live bot behaviour**, which global constraint 1 forbids. In that case: stop, record the difference, and leave `scan_run` on its own arithmetic behind the same `params` argument.

Discovering that the live scan and the backtest gate differently is a *finding worth more than the refactor* — it would mean every backtest in this repo measures a bot that does not ship.

- [ ] **Step 1: Establish whether the two agree**

Run:
```bash
grep -n "min_reward_pct\|sr_target_min_pct\|max_risk_pct\|min_stop_distance\|min_risk_reward\|MIN_TARGET_CONFLUENCE_COUNT" swingbot/core/scanning/scan_run.py
```

Compare each expression against `scenario_gate_inputs` in `swingbot/core/scanning/gating.py`. Write the comparison into the task's notes before touching code. Two outcomes:

- **Identical** → proceed to Step 2.
- **Different in any term** → skip Steps 2–4. Instead: add `params: ScanParams | None = None` to `_sync_run_scan`, replace only the *direct* `config.X` reads for class-1 attrs with `params.x` (a pure substitution that cannot change behaviour), and go to Step 5's second commit message. Then add the divergence to `docs/claude/known-traps.md` in Task D2 with both expressions quoted.

- [ ] **Step 2: Write the failing test** *(identical case only)*

```python
# tests/scanning/test_gating_live_parity.py
"""The live scan and the backtest replay must gate identically, or every
backtest in this repo measures a bot that does not ship. B3 gave them one
implementation; this pins that scan_run actually uses it."""
import inspect

from swingbot.core.scanning import scan_run


def test_scan_run_uses_the_shared_gating_module():
    src = inspect.getsource(scan_run)
    assert "scenario_gate_inputs" in src
    assert "passes_confluence" in src


def test_scan_run_no_longer_reads_the_gate_knobs_from_config():
    src = inspect.getsource(scan_run)
    for attr in ("config.MIN_REWARD_PCT", "config.MIN_STOP_DISTANCE_PCT",
                 "config.MAX_STOP_LOSS_PCT", "config.MIN_RISK_REWARD_RATIO",
                 "config.MIN_TARGET_CONFLUENCE_COUNT"):
        assert attr not in src, f"{attr} is still a global read in scan_run"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/scanning/test_gating_live_parity.py -v`
Expected: FAIL — `assert 'scenario_gate_inputs' in src`.

- [ ] **Step 4: Write minimal implementation**

Add `params: ScanParams | None = None` to `_sync_run_scan`, resolve `None` to `ScanParams.from_config()` once at the top, replace the local gate arithmetic with `scenario_gate_inputs(params, h)` and the confluence check with `passes_confluence(n, params)`, and pass `params=params` into `build_confluence_plan` and `build_level_map`.

Leave the class-3 (`live_only`) reads — session hours, quiet hours, intraday, near-TP timers — reading `config` directly. They are not in `ScanParams` by design, and routing them through it would imply they are searchable.

- [ ] **Step 5: Commit**

Identical case:
```bash
git add swingbot/core/scanning/scan_run.py tests/scanning/test_gating_live_parity.py
git commit -m "feat(v74): scan_run uses the shared gating; live and replay cannot diverge"
```

Different case:
```bash
git add swingbot/core/scanning/scan_run.py
git commit -m "feat(v74): scan_run takes ScanParams; live/replay gate divergence recorded not fixed"
```
