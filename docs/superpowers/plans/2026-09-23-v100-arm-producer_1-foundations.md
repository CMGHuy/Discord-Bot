# Standard Arm Producer — Part 1: Foundations

**Index:** `docs/superpowers/plans/2026-09-23-v100-arm-producer_0-index.md` — header block, Global Constraints, planning deviations and `## Parallelisation` live there and apply to every task below.
**Spec:** `docs/superpowers/specs/2026-09-23-v100-arm-producer.md`
**Bump:** none
**Edge:** none (integrity)

---

# Phase A — Foundations

### Task V100-1: `ArmTrade` source/direction + pairing helpers

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py` (`ArmTrade`, `arm_trade_from_plan`)
- Create: `swingbot/core/backtesting/arms/__init__.py`, `swingbot/core/backtesting/arms/pairing.py`
- Test: `tests/backtesting/arms/__init__.py` (empty), `tests/backtesting/arms/test_pairing.py`

**Interfaces:**
- Produces: `ArmTrade(..., source: str | None = None, direction: str | None = None)`; `ArmTrade.key -> (ticker, strategy, horizon_key, entry_date, source, direction)`; `pairing.DuplicateKeyError`; `pairing.index_by_key(trades) -> dict`; `pairing.changed_outcomes(baseline, component) -> int`; `pairing.overlap(baseline, component) -> int`.

- [ ] **Step 1: Write the failing test** — `tests/backtesting/arms/test_pairing.py`:

```python
import pytest

from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import pairing


def t(date, outcome="win", r=2.0, direction="bullish", source="strategy", ticker="AAA"):
    return ArmTrade(ticker=ticker, strategy="MACD", horizon_key="3m", entry_date=date,
                    outcome=outcome, r_multiple=r, planned_rr=2.0,
                    source=source, direction=direction)


def test_pre_v100_rows_still_load_and_pair():
    row = {"ticker": "A", "strategy": "MACD", "horizon_key": "3m", "entry_date": "2021-01-04",
           "outcome": "win", "r_multiple": 2.0, "planned_rr": 2.0}
    a, b = ArmTrade(**row), ArmTrade(**row)
    assert a.key == b.key
    assert a.key[-2:] == (None, None)


def test_direction_and_source_separate_keys():
    assert t("2021-01-04", direction="bullish").key != t("2021-01-04", direction="bearish").key
    assert t("2021-01-04", source="strategy").key != t("2021-01-04", source="confluence").key


def test_duplicate_key_raises():
    with pytest.raises(pairing.DuplicateKeyError):
        pairing.index_by_key([t("2021-01-04"), t("2021-01-04")])


def test_identical_arms_change_nothing():
    arm = [t("2021-01-04"), t("2021-01-05", "loss", -1.0)]
    assert pairing.changed_outcomes(arm, list(arm)) == 0


def test_removed_added_and_flipped_each_count():
    base = [t("2021-01-04"), t("2021-01-05", "loss", -1.0), t("2021-01-06")]
    comp = [t("2021-01-04"), t("2021-01-05", "win", 2.0), t("2021-01-07")]
    # 01-06 removed, 01-07 added, 01-05 flipped
    assert pairing.changed_outcomes(base, comp) == 3


def test_r_change_without_outcome_change_counts():
    assert pairing.changed_outcomes([t("2021-01-04", r=2.0)], [t("2021-01-04", r=1.4)]) == 1


def test_overlap_counts_shared_keys():
    assert pairing.overlap([t("2021-01-04"), t("2021-01-05")], [t("2021-01-05")]) == 1
```

- [ ] **Step 2: Run it — expect FAIL** (`TypeError: unexpected keyword argument 'source'`)

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_pairing.py`

- [ ] **Step 3: Implement.** In `acceptance.py`, extend `ArmTrade` (fields after `planned_rr`, defaults keep old JSON loadable):

```python
    planned_rr: float | None
    source: str | None = None       # "confluence" | "strategy"; None on pre-v100 rows
    direction: str | None = None    # "bullish" | "bearish"; None on pre-v100 rows

    @property
    def key(self) -> tuple:
        """Pairing key across arms. source/direction are None on rows written
        before v100, which keeps those rows pairing exactly as they did."""
        return (self.ticker, self.strategy, self.horizon_key, self.entry_date,
                self.source, self.direction)
```

and in `arm_trade_from_plan` pass `source=plan.source, direction=plan.direction` to the constructor.

Create `swingbot/core/backtesting/arms/__init__.py`:

```python
"""v100 standard arm producer. See docs/superpowers/specs/2026-09-23-v100-arm-producer.md."""
```

Create `swingbot/core/backtesting/arms/pairing.py`:

```python
"""Pairing baseline and component arms by ArmTrade.key.

A duplicate key inside one arm is a harness bug, not data: pairing would
silently keep the last row and every downstream delta would be wrong."""
from __future__ import annotations


class DuplicateKeyError(ValueError):
    pass


def index_by_key(trades) -> dict:
    out: dict = {}
    for t in trades:
        if t.key in out:
            raise DuplicateKeyError(f"duplicate pairing key {t.key}")
        out[t.key] = t
    return out


def _fingerprint(t) -> tuple:
    r = None if t.r_multiple is None else round(t.r_multiple, 6)
    return (t.outcome, r)


def changed_outcomes(baseline, component) -> int:
    """Trades that differ between arms: removed + added + same key with a
    different (outcome, R). Zero means the component never reached a trade."""
    b, c = index_by_key(baseline), index_by_key(component)
    moved = len(b.keys() ^ c.keys())
    flipped = sum(1 for k in b.keys() & c.keys() if _fingerprint(b[k]) != _fingerprint(c[k]))
    return moved + flipped


def overlap(baseline, component) -> int:
    return len({t.key for t in baseline} & {t.key for t in component})
```

- [ ] **Step 4: Run it — expect PASS.** Also run `python scripts/dev/testrun.py file tests/backtesting/test_acceptance.py` (existing clause tests use `key` via the split) — expect PASS. If that file name differs, `git grep -ln "from swingbot.core.backtesting.acceptance import" tests` and run each.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/arms/ tests/backtesting/arms/
git commit -m "feat(v100): ArmTrade source/direction pairing key and pairing helpers"
```

---

### Task V100-2: Paired MDE

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py` (add `mde_paired` after `mde_win_rate`)
- Modify: `swingbot/core/backtesting/acceptance_harvest.py` (docstring pointer only)
- Test: `tests/backtesting/arms/test_mde_paired.py`

**Interfaces:**
- Consumes: `cluster_bootstrap`, `delta_standardised_win_rate`, `delta_expectancy_r`, `mde_win_rate`, `_Z_ALPHA_ONE_SIDED`, `_Z_POWER`, `MDE_POWER`, `ALPHA`, `BOOTSTRAP_RESAMPLES` (all existing in `acceptance.py`).
- Produces: `mde_paired(baseline, component, statistic, *, observed_n: int, target_n: int, power=MDE_POWER, alpha=ALPHA, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> float | None` — same units as `statistic` (pp for WR deltas, R for ExpR deltas).

- [ ] **Step 1: Write the failing test** — `tests/backtesting/arms/test_mde_paired.py`:

```python
import numpy as np
import pytest

from swingbot.core.backtesting.acceptance import (
    ArmTrade, delta_expectancy_r, delta_standardised_win_rate, mde_paired, mde_win_rate,
)


def _arm(rng, n_tickers=40, per=25, p=0.4, date_offset=0):
    out = []
    for k in range(n_tickers):
        for i in range(per):
            win = rng.random() < p
            out.append(ArmTrade(ticker=f"T{k}", strategy="MACD", horizon_key="3m",
                                entry_date=f"D{i + date_offset:04d}",
                                outcome="win" if win else "loss",
                                r_multiple=2.0 if win else -1.0, planned_rr=2.0))
    return out


def _decided(arm):
    return sum(1 for t in arm if t.outcome in ("win", "loss"))


def test_small_paired_change_has_far_smaller_mde_than_unpaired():
    rng = np.random.default_rng(1)
    base = _arm(rng)
    comp, flipped = [], set()
    for t in base:        # flip the first loss per ticker to a win
        if t.outcome == "loss" and t.ticker not in flipped:
            flipped.add(t.ticker)
            t = ArmTrade(**{**t.__dict__, "outcome": "win", "r_multiple": 2.0})
        comp.append(t)
    n = _decided(base)
    paired = mde_paired(base, comp, delta_standardised_win_rate, observed_n=n, target_n=n)
    unpaired = mde_win_rate(base, target_n=n)
    assert paired is not None and unpaired is not None
    assert paired < 0.5 * unpaired


def test_independent_arms_match_the_unpaired_formula():
    rng = np.random.default_rng(2)
    base, comp = _arm(rng), _arm(rng, date_offset=10_000)   # zero key overlap
    n = _decided(base)
    paired = mde_paired(base, comp, delta_standardised_win_rate, observed_n=n, target_n=n)
    unpaired = mde_win_rate(base, target_n=n)
    assert 0.7 * unpaired < paired < 1.4 * unpaired


def test_scales_with_sqrt_of_target_n():
    rng = np.random.default_rng(3)
    base, comp = _arm(rng), _arm(rng, date_offset=10_000)
    n = _decided(base)
    one = mde_paired(base, comp, delta_expectancy_r, observed_n=n, target_n=n)
    four = mde_paired(base, comp, delta_expectancy_r, observed_n=n, target_n=4 * n)
    assert four == pytest.approx(one / 2.0)


def test_undefined_inputs_return_none():
    rng = np.random.default_rng(4)
    base = _arm(rng, n_tickers=3)
    assert mde_paired(base, base, delta_expectancy_r, observed_n=0, target_n=10) is None
    assert mde_paired(base, base, delta_expectancy_r, observed_n=10, target_n=0) is None
    assert mde_paired([], [], delta_expectancy_r, observed_n=10, target_n=10) is None
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError: cannot import name 'mde_paired'`)

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_mde_paired.py`

- [ ] **Step 3: Implement** in `acceptance.py`, directly after `mde_win_rate`:

```python
def mde_paired(baseline, component, statistic, *, observed_n: int, target_n: int,
               power: float = MDE_POWER, alpha: float = ALPHA,
               n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> float | None:
    """MDE for the delta `statistic` measures, from the ticker-cluster
    bootstrap SE of that delta on the observed arms (v100).

    mde_win_rate / acceptance_harvest.mde_expectancy_r assume two
    INDEPENDENT populations. Nearly every design here is paired -- a veto
    arm is a subset of its baseline, an exit arm replays the same entries --
    so the delta's variance is far smaller than the unpaired formula says,
    and Stage 0 refused answerable questions. cluster_bootstrap resamples
    tickers with the SAME draw for both arms, so it keeps the pairing and the
    clustering at once; one estimator covers subset, exit-only and
    zero-overlap designs alike. The SE is scaled from observed_n to target_n
    by sqrt, the same projection mde_win_rate's n_eff makes.
    """
    if observed_n <= 0 or target_n <= 0:
        return None
    z_a = _Z_ALPHA_ONE_SIDED.get(alpha)
    z_b = _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed)
    if draws.size < 2:
        return None
    se = float(np.std(draws, ddof=1)) * float(np.sqrt(observed_n / target_n))
    return float((z_a + z_b) * se)
```

In `acceptance_harvest.mde_expectancy_r`'s docstring, append one line after "…before citing this function's output as a bound.": `v100: that paired variant is acceptance.mde_paired(..., statistic=delta_expectancy_r).`

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/acceptance_harvest.py tests/backtesting/arms/test_mde_paired.py
git commit -m "feat(v100): paired MDE from the ticker-cluster bootstrap SE"
```

---

### Task V100-3: Stage-window table and reachability registry

**Files:**
- Create: `swingbot/core/backtesting/arms/windows.py`, `swingbot/core/backtesting/arms/reachability.py`
- Test: `tests/backtesting/arms/test_windows.py`, `tests/backtesting/arms/test_reachability.py`

**Interfaces:**
- Produces (`windows`): `VALIDATION_START = "2024-01-01"`, `ALL_HORIZONS: tuple[str, ...]`, `PILOT_TICKERS = 10`, `StageSpec(name, signal_window, full_width, folds=(), fold_key="", fold_label_key="")`, `STAGES: dict[str, StageSpec]`, `FUNNEL_TO_PRODUCER_STAGE: dict[str, str]`, `resolve(stage) -> StageSpec`, `universe_for(stage, cached_universe) -> list[str]`.
- Produces (`reachability`): constants `REACHABLE`, `LIVE_SCAN_ONLY`, `JOURNAL_DEPENDENT`, `OUTSIDE_REPLAY`, `UNCLASSIFIED`; `Reach(cls, reason, observed_by=frozenset(), fixture_observable=False)`; `REGISTRY: dict[str, Reach]`; `classify(attr) -> str`; `reason(attr) -> str`.

- [ ] **Step 1: Write the failing tests.**

`tests/backtesting/arms/test_windows.py`:

```python
import pytest

from swingbot.core.backtesting.arms import windows as w


def test_only_validation_touches_the_validation_window():
    for name, spec in w.STAGES.items():
        start, end = spec.signal_window
        if name == "validation":
            assert start == w.VALIDATION_START
        else:
            assert end < w.VALIDATION_START, name


def test_folds_sit_inside_their_stage_window():
    for spec in w.STAGES.values():
        for _label, start, end in spec.folds:
            assert spec.signal_window[0] <= start <= end <= spec.signal_window[1]


def test_walkforward_folds_are_the_three_documented_test_years():
    spec = w.STAGES["walkforward"]
    assert [f[0] for f in spec.folds] == ["2021", "2022", "2023"]
    assert spec.fold_key == "folds" and spec.fold_label_key == "test_year"


def test_pilot_is_narrow_and_everything_else_is_full():
    universe = [f"T{i:02d}" for i in range(30)]
    assert w.universe_for("pilot", universe) == sorted(universe)[:w.PILOT_TICKERS]
    for stage in ("selection", "walkforward", "validation"):
        assert w.universe_for(stage, universe) == sorted(universe)


def test_every_funnel_stage_maps_to_a_producer_stage():
    assert set(w.FUNNEL_TO_PRODUCER_STAGE.values()) <= set(w.STAGES)


def test_unknown_stage_is_an_error():
    with pytest.raises(ValueError):
        w.resolve("nonsense")
```

`tests/backtesting/arms/test_reachability.py`:

```python
from swingbot import config
from swingbot.core.backtesting.arms import reachability as r

CLASSES = {r.REACHABLE, r.LIVE_SCAN_ONLY, r.JOURNAL_DEPENDENT, r.OUTSIDE_REPLAY}


def test_every_searchable_knob_is_classified_exactly_once():
    assert set(r.REGISTRY) == set(config.searchable_attrs()), (
        "a searchable knob was added or removed -- classify it in reachability.py")


def test_entries_are_well_formed():
    for attr, reach in r.REGISTRY.items():
        assert reach.cls in CLASSES, attr
        assert reach.reason.strip(), attr
        if reach.cls == r.REACHABLE:
            assert reach.observed_by and reach.observed_by <= {"confluence", "strategy"}, attr
        else:
            assert not reach.observed_by and not reach.fixture_observable, attr


def test_journal_knobs_are_refused():
    assert r.classify("STALL_EXIT_ENABLED") == r.JOURNAL_DEPENDENT
    assert r.classify("DATA_DRIVEN_STOPS_ENABLED") == r.JOURNAL_DEPENDENT


def test_unknown_knob_is_unclassified():
    assert r.classify("NOT_A_KNOB") == r.UNCLASSIFIED
    assert "not a searchable" in r.reason("NOT_A_KNOB")
```

- [ ] **Step 2: Run both — expect FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `swingbot/core/backtesting/arms/windows.py`:

```python
"""The single stage -> signal window / width table (v100).

Values are today's documented windows (backtest-methodology.md funnel
table), consolidated here so no measurement script picks its own. Windows
restrict SIGNAL dates; exits walk forward, the convention every existing
harness uses."""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.market.strategy_types import HORIZONS

VALIDATION_START = "2024-01-01"
ALL_HORIZONS: tuple[str, ...] = tuple(HORIZONS)
PILOT_TICKERS = 10


@dataclass(frozen=True)
class StageSpec:
    name: str
    signal_window: tuple[str, str]
    full_width: bool
    folds: tuple = ()           # ((label, start, end), ...), sliced from one run
    fold_key: str = ""          # JSON key the folds are written under
    fold_label_key: str = ""    # per-fold label field name


STAGES: dict[str, StageSpec] = {
    "pilot": StageSpec("pilot", ("2018-06-01", "2020-12-31"), full_width=False),
    "selection": StageSpec(
        "selection", ("2018-06-01", "2022-12-31"), full_width=True,
        folds=(("2020", "2018-06-01", "2020-12-31"),
               ("2021", "2018-06-01", "2021-12-31"),
               ("2022", "2018-06-01", "2022-12-31")),
        fold_key="train_folds", fold_label_key="train_end"),
    "walkforward": StageSpec(
        "walkforward", ("2021-01-01", "2023-12-31"), full_width=True,
        folds=(("2021", "2021-01-01", "2021-12-31"),
               ("2022", "2022-01-01", "2022-12-31"),
               ("2023", "2023-01-01", "2023-12-31")),
        fold_key="folds", fold_label_key="test_year"),
    "validation": StageSpec("validation", (VALIDATION_START, "2025-12-31"), full_width=True),
}

#: validate_component --stage -> the producer stage whose stamp it accepts.
FUNNEL_TO_PRODUCER_STAGE = {
    "reachability": "pilot",
    "mde": "selection",
    "walkforward": "walkforward",
    "validation": "validation",
}


def resolve(stage: str) -> StageSpec:
    try:
        return STAGES[stage]
    except KeyError:
        raise ValueError(f"unknown stage {stage!r}; expected one of {sorted(STAGES)}") from None


def universe_for(stage: str, cached_universe) -> list[str]:
    universe = sorted(cached_universe)
    return universe if resolve(stage).full_width else universe[:PILOT_TICKERS]
```

`swingbot/core/backtesting/arms/reachability.py`:

```python
"""Which searchable knobs the replay engines can see (v100).

Supersedes tests/backtesting/test_knob_observability.py's local EXEMPT
dict: one source of truth, read by the producer (static Stage -1 refusal)
and by the observability test. A non-reachable knob is evidence about the
instrument, never permission to tune by noise."""
from __future__ import annotations

from dataclasses import dataclass

REACHABLE = "reachable"
LIVE_SCAN_ONLY = "live_scan_only"
JOURNAL_DEPENDENT = "journal_dependent"
OUTSIDE_REPLAY = "outside_replay"
UNCLASSIFIED = "unclassified"

C, S = frozenset({"confluence"}), frozenset({"strategy"})
CS = C | S


@dataclass(frozen=True)
class Reach:
    cls: str
    reason: str
    observed_by: frozenset = frozenset()
    fixture_observable: bool = False    # a one-step perturbation changes the v74 fixture


def _live(reason):
    return Reach(LIVE_SCAN_ONLY, reason)


def _outside(reason):
    return Reach(OUTSIDE_REPLAY, reason)


_OPEX = "OPEX adjustment needs the calendar-aware live scan date path; replay has no OPEX-date input."
_RS = "Relative strength is cross-sectional and evaluated in scanning/engine.py, which no replay runs."
_DCB = "Measured through its dedicated DCB harness (replay_scenarios takes dcb_params, not config)."
_TIGHTEN = ("Only active when ADAPTIVE_RUNNER_TRAIL_ENABLED=true; a lone perturbation at the "
            "default is inert by design.")

REGISTRY: dict[str, Reach] = {
    # --- reachable: confluence population ---
    "MIN_REWARD_PCT": Reach(REACHABLE, "Scenario admission gate in replay_scenarios.", C, True),
    "MIN_STOP_DISTANCE_PCT": Reach(REACHABLE, "Scenario admission gate in replay_scenarios.", C, True),
    "MAX_STOP_LOSS_PCT": Reach(REACHABLE, "Scenario admission gate; the fixture never reaches the max-stop boundary.", C),
    "MIN_TARGET_CONFLUENCE_COUNT": Reach(REACHABLE, "passes_confluence in replay; fixture scenarios clear it either way.", C),
    "AVWAP_LEVELS_ENABLED": Reach(REACHABLE, "Level-map source; the fixture has no AVWAP anchor that changes a selected plan.", C),
    "VOLUME_PROFILE_NODES_ENABLED": Reach(REACHABLE, "Level-map source; fixture nodes do not change a selected plan.", C),
    # --- reachable: strategy population ---
    "LEVEL_LIFECYCLE_STOPS_ENABLED": Reach(REACHABLE, "apply_level_lifecycle inside build_strategy_plan.", S, True),
    "RSI_DIV_MIN_CONSECUTIVE_TURN": Reach(REACHABLE, "Read from config in entry_filters.py at entry time.", S, True),
    "MA_RIBBON_CONFIRM_BARS": Reach(REACHABLE, "Read from config in entry_filters.py at entry time.", S, True),
    "SR_MIN_LEVEL_TOUCHES": Reach(REACHABLE, "Read from config in entry_filters.py at entry time.", S, True),
    "FIB_TARGET_1_0_EXTENSION": Reach(REACHABLE, "Read from config in targets.py; v84 saw it change one trade in all of TRAIN, too rare for the fixture.", S),
    # --- reachable: exits, both populations (outcomes are compared, not plan fields) ---
    "ADAPTIVE_RUNNER_TRAIL_ENABLED": Reach(REACHABLE, "Post-TP1 runner trail in simulate_exit.", CS, True),
    "TIGHTEN_TRIGGER_R": Reach(REACHABLE, _TIGHTEN, CS),
    "TIGHTEN_ATR_MULT": Reach(REACHABLE, _TIGHTEN, CS),
    # --- live scan only (sub-project D) ---
    "CONFLUENCE_DEVIATION_PCT": _live("Confirmation counting happens in scan analysis; replay uses a fixed 5.0 tolerance."),
    "MIN_ALERT_CONFIDENCE_LEVEL": _live("Confidence scoring belongs to scanning.confidence."),
    "UNIFIED_CONFIDENCE": _live("Confidence scoring belongs to scanning.confidence."),
    "DEDUP_TOLERANCE_PCT": _live("Deduplication runs when the live scan builds its alert set."),
    "MAX_ALERTS_PER_SCAN": _live("Alert-delivery cap in the scan run."),
    "RS_GATE": _live(_RS),
    "RS_LEADER_PERCENTILE": _live(_RS),
    "RS_LAGGARD_PERCENTILE": _live(_RS),
    "REGIME_GATES_ENABLED": _live("Needs the benchmark ticker and attached market context of the live scan."),
    "HTF_CONFLUENCE_ENABLED": _live("Higher-timeframe confirmation is evaluated in scan analysis."),
    "MTF_ADJACENT_GATE": _live("Adjacent-horizon alignment is evaluated in scan analysis."),
    "OPEX_CAUTION_ENABLED": _live(_OPEX),
    "OPEX_MONTHLY_CONFIDENCE_BUMP": _live(_OPEX),
    "OPEX_MONTHLY_CONFLUENCE_BUMP": _live(_OPEX),
    "OPEX_WEEKLY_CONFLUENCE_BUMP": _live(_OPEX),
    "OPEX_STOP_WIDEN_PCT": _live(_OPEX),
    # --- journal dependent: replay must never read live journal state ---
    "DATA_DRIVEN_STOPS_ENABLED": Reach(JOURNAL_DEPENDENT, "Resolves stops from the live journal (edge E31/E32)."),
    "STALL_EXIT_ENABLED": Reach(JOURNAL_DEPENDENT, "Resolves stall_exit_day from journal days_to_half_r (v92 H2)."),
    # --- outside replay ---
    "UNIVERSE_MIN_DOLLAR_VOL": _outside("Universe construction precedes replay."),
    "UNIVERSE_MIN_PRICE": _outside("Universe construction precedes replay."),
    "OPEX_SIZE_REDUCTION_PCT": _outside("Position sizing; replay records plan prices and exits only."),
    "PYRAMIDING_ENABLED": _outside("Live portfolio decision after a plan is open."),
    "PLAN_ENGINE_V2": _outside("Replay is the v2 plan path by construction."),
    "SCALE_OUT_ENABLED": _outside("Engines always simulate scale_out=True; the live switch is not a replay dimension."),
    "DEAD_CAT_BOUNCE_VETO": _outside(_DCB),
    "DCB_DECLINE_PCT": _outside(_DCB),
    "DCB_GAP_REQUIRED": _outside(_DCB),
    "DCB_VOLUME_RATIO": _outside(_DCB),
}


def classify(attr: str) -> str:
    reach = REGISTRY.get(attr)
    return reach.cls if reach else UNCLASSIFIED


def reason(attr: str) -> str:
    reach = REGISTRY.get(attr)
    return reach.reason if reach else f"{attr} is not a searchable knob (config.searchable_attrs())."
```

- [ ] **Step 4: Run both — expect PASS.** If `test_every_searchable_knob_is_classified_exactly_once` fails, the diff names the knob; classify it from its `EXEMPT` reason in `tests/backtesting/test_knob_observability.py` — never by guessing.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/windows.py swingbot/core/backtesting/arms/reachability.py tests/backtesting/arms/test_windows.py tests/backtesting/arms/test_reachability.py
git commit -m "feat(v100): stage-window table and knob reachability registry"
```

---

### Task V100-4: Knob overrides, engine protocol, confluence engine

**Files:**
- Create: `swingbot/core/backtesting/arms/knobs.py`, `swingbot/core/backtesting/arms/engine.py`, `swingbot/core/backtesting/arms/confluence_engine.py`
- Test: `tests/backtesting/arms/test_knobs.py`, `tests/backtesting/arms/test_confluence_engine.py`

**Interfaces:**
- Consumes: `acceptance.arm_trade_from_plan` (V100-1), `backtest_scenarios.replay_scenarios`, `plan_engine.simulate_exit`, `config.FIELDS`, `config._cast`, `ScanParams.from_config`.
- Produces: `knobs.parse_knob(text) -> tuple[str, object]`; `knobs.apply_knobs(delta: dict)` (context manager); `engine.ArmEngine` protocol (`engine_id`, `run_ticker(ticker, df, horizons, signal_window, params) -> list[ArmTrade]`); `engine.DEFAULT_ENGINES = ("confluence", "strategy")`; `engine.get_engine(engine_id)`; `engine.run_arm(ticker, df, engine_ids, horizons, signal_window, delta) -> list[ArmTrade]`; `confluence_engine.ConfluenceEngine`; `confluence_engine.SKIPPED = ("not_triggered", "no_trade")`.

- [ ] **Step 1: Write the failing tests.**

`tests/backtesting/arms/test_knobs.py`:

```python
import pytest

from swingbot import config
from swingbot.core.backtesting.arms.knobs import apply_knobs, parse_knob


def test_parse_casts_through_the_config_field_type():
    assert parse_knob("STALL_EXIT_ENABLED=true") == ("STALL_EXIT_ENABLED", True)
    attr, value = parse_knob("TIGHTEN_TRIGGER_R=2.5")
    assert attr == "TIGHTEN_TRIGGER_R" and value == 2.5


@pytest.mark.parametrize("bad", ["NOEQUALS", "=1", "NOT_A_FIELD=1"])
def test_parse_rejects_malformed_or_unknown(bad):
    with pytest.raises(ValueError):
        parse_knob(bad)


def test_apply_knobs_sets_and_restores():
    before = config.MIN_REWARD_PCT
    with apply_knobs({"MIN_REWARD_PCT": before + 1.0}):
        assert config.MIN_REWARD_PCT == before + 1.0
    assert config.MIN_REWARD_PCT == before


def test_apply_knobs_restores_on_error():
    before = config.MIN_REWARD_PCT
    with pytest.raises(RuntimeError):
        with apply_knobs({"MIN_REWARD_PCT": before + 1.0}):
            raise RuntimeError("boom")
    assert config.MIN_REWARD_PCT == before
```

`tests/backtesting/arms/test_confluence_engine.py`:

```python
import pytest

from swingbot import config
from swingbot.core.backtesting.arms.engine import get_engine, run_arm

from ..test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


def test_confluence_trades_are_keyed_and_in_window(frame):
    trades = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert trades, "fixture should yield confluence trades on 4w"
    assert all(t.source == "confluence" and t.direction in ("bullish", "bearish") for t in trades)
    assert len({t.key for t in trades}) == len(trades)
    assert all(t.outcome in ("win", "loss", "scratch", "timeout") for t in trades)


def test_signal_window_filters_by_entry_date(frame):
    trades = run_arm("AAPL", frame, ("confluence",), ("4w",), ("2025-01-01", "2025-06-30"), {})
    assert all("2025-01-01" <= t.entry_date <= "2025-06-30" for t in trades)


def test_knob_delta_reaches_the_engine(frame):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    tight = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW,
                    {"MIN_REWARD_PCT": config.MIN_REWARD_PCT * 1.75 + 0.5})
    assert tight != base


def test_unknown_engine_is_an_error():
    with pytest.raises(ValueError):
        get_engine("nope")
```

- [ ] **Step 2: Run both — expect FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement.**

`swingbot/core/backtesting/arms/knobs.py`:

```python
"""Knob deltas for one arm, applied to config globals (v100).

Applied INSIDE the worker process: a spawned ProcessPool worker re-imports
config from .env and never sees a parent's mutation, which is why v92's
in-process `config.X = ...` pattern cannot be pooled. Several reachable
knobs are read from config at call time (entry_filters.py, targets.py), so
a ScanParams override alone would miss them."""
from __future__ import annotations

from contextlib import contextmanager

from swingbot import config


def _field(attr: str):
    for f in config.FIELDS:
        if f.attr == attr:
            return f
    raise ValueError(f"{attr} is not a config field")


def parse_knob(text: str) -> tuple[str, object]:
    attr, sep, raw = text.partition("=")
    if not sep or not attr:
        raise ValueError(f"--knob must be ATTR=value, got {text!r}")
    return attr, config._cast(_field(attr), raw)


@contextmanager
def apply_knobs(delta: dict):
    missing = object()
    saved = {attr: getattr(config, attr, missing) for attr in delta}
    try:
        for attr, value in delta.items():
            setattr(config, attr, value)
        yield
    finally:
        for attr, value in saved.items():
            if value is missing:
                delattr(config, attr)
            else:
                setattr(config, attr, value)
```

`swingbot/core/backtesting/arms/engine.py`:

```python
"""The ArmEngine seam (v100). Sub-project D's historical scan-replay engine
registers here later without any funnel change."""
from __future__ import annotations

from typing import Protocol

from swingbot.core.backtesting.arms.knobs import apply_knobs

DEFAULT_ENGINES = ("confluence", "strategy")


class ArmEngine(Protocol):
    engine_id: str

    def run_ticker(self, ticker: str, df, horizons, signal_window: tuple[str, str],
                   params) -> list: ...


def get_engine(engine_id: str) -> ArmEngine:
    if engine_id == "confluence":
        from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
        return ConfluenceEngine()
    if engine_id == "strategy":
        from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
        return StrategyEngine()
    raise ValueError(f"unknown engine {engine_id!r}; expected one of {DEFAULT_ENGINES}")


def run_arm(ticker: str, df, engine_ids, horizons, signal_window, delta: dict) -> list:
    """One arm, one ticker. Knobs are applied here, inside whichever process
    runs this, and ScanParams is read AFTER they are applied."""
    from swingbot.scan_params import ScanParams
    with apply_knobs(delta):
        params = ScanParams.from_config()
        out: list = []
        for engine_id in engine_ids:
            out.extend(get_engine(engine_id).run_ticker(ticker, df, horizons, signal_window, params))
    return out
```

`swingbot/core/backtesting/arms/confluence_engine.py`:

```python
"""Confluence population: replay_scenarios + simulate_exit (v100).

Signals are generated on df.loc[:end] only -- replay_scenarios walks every
bar to the end of the frame it is given, and bars past the signal window
would be computed and thrown away. The exit walk gets the full frame, the
run_scenario_backtest convention."""
from __future__ import annotations

from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.planning.plan_engine import simulate_exit

SKIPPED = ("not_triggered", "no_trade")


class ConfluenceEngine:
    engine_id = "confluence"

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        start, end = signal_window
        signal_df = df.loc[:end]
        out = []
        for hk in horizons:
            for i, plan in replay_scenarios(ticker, signal_df, hk, params=params):
                date = str(df.index[i].date())
                if date < start:
                    continue
                res = simulate_exit(df, i, plan, scale_out=True)
                if res.outcome in SKIPPED:
                    continue
                out.append(arm_trade_from_plan(plan, entry_date=date, outcome=res.outcome,
                                               r_multiple=res.r_total))
        return out
```

- [ ] **Step 4: Run both — expect PASS.** If `parse_knob("STALL_EXIT_ENABLED=true")` returns a string, that field's `type` is not `checkbox`; read its `Field(...)` in `swingbot/config.py` and assert the value `_cast` actually produces — do not change `config.py`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/knobs.py swingbot/core/backtesting/arms/engine.py swingbot/core/backtesting/arms/confluence_engine.py tests/backtesting/arms/test_knobs.py tests/backtesting/arms/test_confluence_engine.py
git commit -m "feat(v100): in-worker knob overrides, ArmEngine seam, confluence engine"
```

---

### Task V100-5: Strategy engine through `build_strategy_plan` + parity test

Load the `no-lookahead` skill first.

**Files:**
- Create: `swingbot/core/backtesting/arms/strategy_engine.py`
- Test: `tests/backtesting/arms/test_strategy_engine.py`

**Interfaces:**
- Consumes: `backtest._vectorized_entries`, `backtest.ENTRY_SHIFT`, `backtest.ALL_STRATEGIES`, `backtest.run_backtest` (test only), `builders.build_strategy_plan`, `levels.build_level_map`, `plan_engine.exit_params_for`, `plan_engine.simulate_exit`, `strategy_types.HORIZONS/MIN_BARS`, `confluence_engine.SKIPPED`.
- Produces: `StrategyEngine(strategies=None)`; `.run_ticker(...)`; `.iter_trades(ticker, df, strategy, horizon_key, signal_window, params)` yielding `(date: str, plan: TradePlanV2, res: ExitResult)`.

- [ ] **Step 1: Write the failing test** — `tests/backtesting/arms/test_strategy_engine.py`:

```python
import pytest

from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.scan_params import ScanParams

from ..test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
HORIZONS_UNDER_TEST = ("4w", "3m")


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


@pytest.mark.slow
@pytest.mark.parametrize("hk", HORIZONS_UNDER_TEST)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_parity_with_run_backtest(frame, strategy, hk):
    """The one real behaviour change: strategy plans now come from
    build_strategy_plan, not _trade_plan_at. Entries and stops must match
    run_backtest's v2 path exactly; see Task V100-5 Step 4 for targets."""
    ref = run_backtest("AAPL", frame, strategy, hk, one_at_a_time=True, exit_model="v2",
                       scale_out=True, tp2_mode="levels", frictions=True)
    ours = list(StrategyEngine().iter_trades("AAPL", frame, strategy, hk, WINDOW,
                                             ScanParams.from_config()))
    assert [t.entry_date for t in ref.trades] == [d for d, _p, _r in ours]
    for t, (_d, plan, res) in zip(ref.trades, ours):
        assert round(plan.stop_loss, 4) == t.stop_loss
        assert round(plan.tp1, 4) == t.take_profit
        assert res.outcome == t.outcome


def test_run_ticker_emits_keyed_strategy_trades(frame):
    trades = StrategyEngine(strategies=("MACD",)).run_ticker(
        "AAPL", frame, ("4w",), WINDOW, ScanParams.from_config())
    assert all(t.source == "strategy" and t.strategy == "MACD" for t in trades)
    assert len({t.key for t in trades}) == len(trades)


def test_signal_window_filters_but_dedup_state_survives(frame):
    """Trades before the window still occupy the position (one_at_a_time),
    so a windowed run is a strict suffix of the full run -- never a
    different trade sequence."""
    eng, p = StrategyEngine(strategies=("MACD",)), ScanParams.from_config()
    full = eng.run_ticker("AAPL", frame, ("4w",), WINDOW, p)
    part = eng.run_ticker("AAPL", frame, ("4w",), ("2025-01-01", "2100-12-31"), p)
    assert part == [t for t in full if t.entry_date >= "2025-01-01"]
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`).

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_strategy_engine.py`

- [ ] **Step 3: Implement** `swingbot/core/backtesting/arms/strategy_engine.py`:

```python
"""Strategy-source population through THE live constructor (v100).

run_backtest builds plans via _trade_plan_at + an inline TradePlanV2, so
anything wired only into planning/builders.py:build_strategy_plan was
invisible to it -- DATA_DRIVEN_STOPS_ENABLED burned a VALIDATION shot that
way and STALL_EXIT_ENABLED closed on TRAIN the same way. This engine keeps
run_backtest's entry signals, one-at-a-time dedup and 5-bar level-map
cache, and swaps only the plan constructor. run_backtest itself is
unchanged (badges and --emit-registry keep their path).

NO-LOOKAHEAD: the plan at bar i is built from df.iloc[:i+1]; only the exit
walk sees later bars."""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.arms.confluence_engine import SKIPPED
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.plan_engine import exit_params_for, simulate_exit


class StrategyEngine:
    engine_id = "strategy"

    def __init__(self, strategies=None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        out = []
        for hk in horizons:
            for strategy in self.strategies:
                for date, plan, res in self.iter_trades(ticker, df, strategy, hk,
                                                        signal_window, params):
                    out.append(arm_trade_from_plan(plan, entry_date=date, outcome=res.outcome,
                                                   r_multiple=res.r_total))
        return out

    def iter_trades(self, ticker, df, strategy, horizon_key, signal_window, params):
        start, end = signal_window
        min_bars = MIN_BARS[horizon_key]
        if len(df) < min_bars + 10:
            return
        bull, bear = bt._vectorized_entries(df, strategy, horizon_key)
        if bt.ENTRY_SHIFT:
            bull = pd.Series(np.roll(bull.values, bt.ENTRY_SHIFT), index=df.index)
            bear = pd.Series(np.roll(bear.values, bt.ENTRY_SHIFT), index=df.index)
        wants_tp2 = bool(exit_params_for(strategy)["tp2"])
        open_until, lm_key, level_map = -1, None, None
        for i in np.where(bull.values | bear.values)[0]:
            if i < min_bars or i <= open_until:
                continue
            date = str(df.index[i].date())
            if date > end:
                break
            direction = "bullish" if bull.values[i] else "bearish"
            window = df.iloc[:i + 1]
            if wants_tp2 and i // 5 != lm_key:      # run_backtest's tp2 level-map cache
                level_map = build_level_map(window, HORIZONS[horizon_key],
                                            float(df["Close"].iloc[i]))
                lm_key = i // 5
            plan = build_strategy_plan(window, i, ticker=ticker, strategy=strategy,
                                       horizon_key=horizon_key, direction=direction,
                                       level_map=level_map if wants_tp2 else None,
                                       scan_params=params)
            if plan is None:
                continue
            res = simulate_exit(df, i, plan, scale_out=True)
            if res.outcome in SKIPPED:
                continue
            open_until = res.exit_index
            if date >= start:
                yield date, plan, res
```

- [ ] **Step 4: Run — interpret parity honestly.**
  - Entry dates and stops must match for every (strategy, horizon) **except** the Elliott repaint case below. A stop mismatch, or an entry-date mismatch outside Elliott Wave, is a bug in this engine: fix it here, never in `run_backtest`. An entry-date mismatch confined to Elliott Wave (the builder sees `elliott_wave3_entries` on the slice, `_plan_series` on the full frame) is a finding — record it and exempt that case the same way as a target divergence; if it is real, it is lookahead in `run_backtest`, flagged for its own plan, not fixed here.
  - A **target/outcome** mismatch may be real divergence between the two constructors (v31 documents deliberate target divergence; `build_strategy_plan` passes `level_map` into `apply_level_lifecycle`, `_trade_plan_at` does not; Elliott's `elliott_wave3_entries` is computed on the full frame in `_plan_series` but on the slice here — a full-frame zigzag can repaint, which would be lookahead **in `run_backtest`**). For each mismatching (strategy, horizon): write the strategy, horizon, count and first differing date into a scratch note for Task V100-10's results doc, then narrow only that case — replace the two lines with:

```python
        assert round(plan.stop_loss, 4) == t.stop_loss
        # tp1/outcome parity deliberately not asserted for <strategy>/<hk>:
        # <one-line cause>, recorded in results/<v100 results doc>.
```

    using a `KNOWN_TARGET_DIVERGENCE = {("Elliott Wave", "4w"), ...}` set checked inside the test, with the real names and cause. Never `xfail`.
  - Then: `python scripts/dev/testrun.py file tests/backtesting/arms/test_strategy_engine.py` — expect PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/strategy_engine.py tests/backtesting/arms/test_strategy_engine.py
git commit -m "feat(v100): strategy engine through build_strategy_plan, parity-tested against run_backtest"
```

---

### Task V100-6: Provenance stamp

**Files:**
- Create: `swingbot/core/backtesting/arms/provenance.py`
- Test: `tests/backtesting/arms/test_provenance.py`

**Interfaces:**
- Consumes: `windows.VALIDATION_START`, `windows.ALL_HORIZONS`, `windows.FUNNEL_TO_PRODUCER_STAGE` (V100-3).
- Produces: `PRODUCER_VERSION = 1`; `REFUSAL_TOKENS` tuple; `code_hash(root=SWINGBOT_ROOT) -> str`; `git_head() -> str`; `build_stamp(*, stage, signal_window, universe, horizons, engines, knob_delta, engine_hash_baseline, engine_hash_component, changed_outcomes, preregistration=None) -> dict`; `check_stamp(blob, *, funnel_stage, full_universe) -> str | None`.

- [ ] **Step 1: Write the failing test** — `tests/backtesting/arms/test_provenance.py`:

```python
import pytest

from swingbot.core.backtesting.arms import provenance as pv
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS

UNIVERSE = ["AAA", "BBB", "CCC"]


def stamp(**over):
    kw = dict(stage="selection", signal_window=("2018-06-01", "2022-12-31"),
              universe=UNIVERSE, horizons=ALL_HORIZONS, engines=("confluence", "strategy"),
              knob_delta={"MIN_REWARD_PCT": 4.0}, engine_hash_baseline="h",
              engine_hash_component="h", changed_outcomes=12)
    kw.update(over)
    return {"provenance": pv.build_stamp(**kw)}


def test_good_stamp_passes():
    assert pv.check_stamp(stamp(), funnel_stage="mde", full_universe=UNIVERSE) is None


@pytest.mark.parametrize("blob,funnel_stage,token", [
    ({"baseline": []}, "mde", "refused:unstamped"),
    (stamp(stage="pilot"), "mde", "refused:stage-mismatch"),
    (stamp(engine_hash_component="other"), "mde", "refused:engine-mismatch"),
    (stamp(signal_window=("2018-06-01", "2024-03-01")), "mde", "refused:window-contact"),
    (stamp(universe=UNIVERSE[:2]), "mde", "refused:narrow-universe"),
    (stamp(horizons=ALL_HORIZONS[:3]), "mde", "refused:narrow-universe"),
])
def test_each_refusal_token(blob, funnel_stage, token):
    assert pv.check_stamp(blob, funnel_stage=funnel_stage, full_universe=UNIVERSE) == token
    assert token in pv.REFUSAL_TOKENS


def test_pilot_may_be_narrow():
    blob = stamp(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["AAA"])
    assert pv.check_stamp(blob, funnel_stage="reachability", full_universe=UNIVERSE) is None


def test_validation_may_touch_the_validation_window():
    blob = stamp(stage="validation", signal_window=("2024-01-01", "2025-12-31"))
    assert pv.check_stamp(blob, funnel_stage="validation", full_universe=UNIVERSE) is None


def test_code_hash_tracks_file_content(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = pv.code_hash(tmp_path)
    assert pv.code_hash(tmp_path) == first
    (tmp_path / "a.py").write_text("x = 2\n")
    assert pv.code_hash(tmp_path) != first
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement** `swingbot/core/backtesting/arms/provenance.py`:

```python
"""The provenance stamp every producer-written arms file carries (v100),
and the funnel's check of it. Tokens are stable literals, same convention
as run_backtest_range.REFUSAL_TOKENS. Every refusal leaves the budget
intact."""
from __future__ import annotations

import datetime as dt
import hashlib
import subprocess
from pathlib import Path

from swingbot.core.backtesting.arms.windows import (
    ALL_HORIZONS, FUNNEL_TO_PRODUCER_STAGE, VALIDATION_START,
)

PRODUCER_VERSION = 1
SWINGBOT_ROOT = Path(__file__).resolve().parents[3]

REFUSAL_TOKENS = (
    "refused:unstamped",
    "refused:stage-mismatch",
    "refused:engine-mismatch",
    "refused:window-contact",
    "refused:narrow-universe",
    "refused:zero-diff",
    # refused:unreachable:<class> is parameterised; see reachability.py
)


def code_hash(root: Path = SWINGBOT_ROOT) -> str:
    """sha256 over every .py under `root`, taken at the start of each arm.
    Runs last hours while other sessions edit this tree; baseline and
    component must have run the same code."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        h.update(path.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_stamp(*, stage, signal_window, universe, horizons, engines, knob_delta,
                engine_hash_baseline, engine_hash_component, changed_outcomes,
                preregistration=None) -> dict:
    return {
        "producer": "measure_arms", "producer_version": PRODUCER_VERSION,
        "stage": stage, "signal_window": list(signal_window),
        "universe": sorted(universe), "universe_count": len(universe),
        "horizons": list(horizons), "engines": list(engines),
        "knob_delta": dict(knob_delta),
        "engine_hash": {"baseline": engine_hash_baseline, "component": engine_hash_component},
        "changed_outcomes": int(changed_outcomes),
        "preregistration": preregistration,
        "git_head": git_head(),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def check_stamp(blob: dict, *, funnel_stage: str, full_universe) -> str | None:
    p = blob.get("provenance")
    if not p:
        return "refused:unstamped"
    expected = FUNNEL_TO_PRODUCER_STAGE[funnel_stage]
    if p.get("stage") != expected:
        return "refused:stage-mismatch"
    hashes = p.get("engine_hash") or {}
    if not hashes.get("baseline") or hashes.get("baseline") != hashes.get("component"):
        return "refused:engine-mismatch"
    if expected != "validation" and p["signal_window"][1] >= VALIDATION_START:
        return "refused:window-contact"
    if expected != "pilot" and (sorted(p["universe"]) != sorted(full_universe)
                                or list(p["horizons"]) != list(ALL_HORIZONS)):
        return "refused:narrow-universe"
    return None
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/provenance.py tests/backtesting/arms/test_provenance.py
git commit -m "feat(v100): provenance stamp and funnel stamp check"
```

---
