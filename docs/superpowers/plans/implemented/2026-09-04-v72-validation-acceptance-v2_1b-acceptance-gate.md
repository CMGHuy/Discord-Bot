# v72 — Validation acceptance v2, Part 1b: the gate

> Part of the v72 plan. Header block, global constraints, parallelisation map
> and the part table live in `_0-index`. **Read that first.** These tasks
> consume `ArmTrade`, `win_rate`, `expectancy_r`, `stratum_weights`,
> `standardised_win_rate`, `bootstrap_delta`, `delta_standardised_win_rate`
> and `delta_expectancy_r` from Part 1a.

# Phase A — the acceptance module (continued)

### Task A4: The minimum-detectable-effect precheck

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py`
- Test: `tests/backtesting/test_acceptance_mde.py`

**Interfaces:**
- Consumes: `ArmTrade`, `win_rate`, `DECIDED` from A1–A2.
- Produces: `intracluster_correlation(trades) -> float`, `design_effect(trades) -> float`, `mde_win_rate(population, *, target_n, power, alpha) -> float | None`, `project_target_n(observed_n, observed_days, target_days) -> int`.

Stage 0 of the funnel. This is the task that would have refused v68's shot before it was fired.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_mde.py
"""Stage 0: is the hypothesis answerable at the N we can actually get?

v68 spent a one-shot budget on a +0.0104R effect with a standard error
near +-0.05R. Nothing stopped it. This does.
"""
import pytest

from swingbot.core.backtesting.acceptance import (
    ArmTrade, design_effect, intracluster_correlation, mde_win_rate,
    project_target_n,
)


def mk(ticker, outcome, date="2021-01-01"):
    return ArmTrade(ticker=ticker, strategy="MACD", horizon_key="3m",
                    entry_date=date, outcome=outcome,
                    r_multiple=2.0 if outcome == "win" else -1.0,
                    planned_rr=2.0)


def test_icc_is_near_zero_when_tickers_do_not_differ():
    """Every ticker at exactly 50% -- no between-ticker signal at all."""
    trades = []
    for t in range(20):
        trades += [mk(f"T{t}", "win") for _ in range(5)]
        trades += [mk(f"T{t}", "loss") for _ in range(5)]
    assert intracluster_correlation(trades) < 0.05


def test_icc_is_high_when_outcome_is_decided_by_ticker():
    """Half the tickers always win, half always lose -- the outcome is a
    property of the symbol, which is the worst case for independence."""
    trades = []
    for t in range(20):
        outcome = "win" if t % 2 == 0 else "loss"
        trades += [mk(f"T{t}", outcome) for _ in range(10)]
    assert intracluster_correlation(trades) > 0.8


def test_design_effect_is_one_when_every_cluster_is_a_singleton():
    trades = [mk(f"T{t}", "win" if t % 2 else "loss") for t in range(40)]
    assert abs(design_effect(trades) - 1.0) < 1e-9


def test_design_effect_grows_with_cluster_size_and_icc():
    clustered = []
    for t in range(20):
        outcome = "win" if t % 2 == 0 else "loss"
        clustered += [mk(f"T{t}", outcome) for _ in range(10)]
    assert design_effect(clustered) > 5.0


def test_mde_shrinks_as_target_n_grows():
    trades = []
    for t in range(20):
        trades += [mk(f"T{t}", "win") for _ in range(4)]
        trades += [mk(f"T{t}", "loss") for _ in range(6)]
    small = mde_win_rate(trades, target_n=500)
    large = mde_win_rate(trades, target_n=50_000)
    assert small > large > 0.0


def test_mde_is_none_without_decided_trades():
    assert mde_win_rate([mk("T1", "scratch")], target_n=1000) is None


def test_mde_matches_the_textbook_two_proportion_formula():
    """Independent trades (one per ticker) at p=0.5, N=1000 per arm.
    (z_a + z_b) * sqrt(2 p (1-p) / N) = (1.6449 + 0.8416) * sqrt(0.5/1000)
    = 0.0556 -> 5.56pp.
    """
    trades = [mk(f"T{i}", "win" if i % 2 else "loss") for i in range(1000)]
    got = mde_win_rate(trades, target_n=1000)
    assert got == pytest.approx(5.56, abs=0.10)


def test_project_target_n_scales_by_window_length():
    """Achievable N is projected from fold-test years, NEVER read out of
    2024-25 -- touching the validation window to size a run is still
    touching it."""
    assert project_target_n(observed_n=800, observed_days=365,
                            target_days=730) == 1600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_mde.py -v`
Expected: FAIL — `ImportError: cannot import name 'design_effect'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/backtesting/acceptance.py`:

```python
MDE_POWER = 0.80

#: Standard normal quantiles, hardcoded because scipy is NOT in
#: requirements.txt and this module ships in the Docker image.
#: z(1-0.05) = 1.6449 (one-sided alpha), z(0.80) = 0.8416 (power).
_Z_ALPHA_ONE_SIDED = {0.05: 1.6449, 0.01: 2.3263, 0.10: 1.2816}
_Z_POWER = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}


def intracluster_correlation(trades) -> float:
    """ICC of the win indicator, grouped by ticker, by the one-way ANOVA
    estimator. Clamped to [0, 1] -- a negative estimate is sampling noise
    around zero, and letting it through would shrink the design effect
    below 1 and overstate power, the exact error this exists to prevent.
    """
    grouped = _group_by_ticker([t for t in trades if t.outcome in DECIDED])
    groups = [[1.0 if t.outcome == "win" else 0.0 for t in g]
              for g in grouped.values() if g]
    k = len(groups)
    n_total = sum(len(g) for g in groups)
    if k < 2 or n_total <= k:
        return 0.0
    grand = float(np.mean([v for g in groups for v in g]))
    ms_between = sum(len(g) * (float(np.mean(g)) - grand) ** 2
                     for g in groups) / (k - 1)
    ms_within = sum((v - float(np.mean(g))) ** 2
                    for g in groups for v in g) / (n_total - k)
    # Mean cluster size, ANOVA-corrected for unequal sizes.
    m0 = (n_total - sum(len(g) ** 2 for g in groups) / n_total) / (k - 1)
    if m0 <= 0 or (ms_between + (m0 - 1) * ms_within) == 0:
        return 0.0
    icc = (ms_between - ms_within) / (ms_between + (m0 - 1) * ms_within)
    return float(min(1.0, max(0.0, icc)))


def design_effect(trades) -> float:
    """DEFF = 1 + (mean cluster size - 1) * ICC. The factor by which
    clustering inflates the variance over the independent-sample formula.
    """
    decided = [t for t in trades if t.outcome in DECIDED]
    grouped = _group_by_ticker(decided)
    if not grouped:
        return 1.0
    mean_size = len(decided) / len(grouped)
    return 1.0 + (mean_size - 1.0) * intracluster_correlation(decided)


def mde_win_rate(population, *, target_n: int, power: float = MDE_POWER,
                 alpha: float = ALPHA) -> float | None:
    """Smallest ΔWR, in percentage points, detectable at `power` with a
    one-sided test at `alpha`, given `target_n` decided trades per arm and
    the clustering `population` exhibits.

    A TRAIN effect smaller than this is not a small edge -- it is an
    unanswerable question, and firing a one-shot budget at it wastes the
    shot whatever the answer comes back as.
    """
    decided = [t for t in population if t.outcome in DECIDED]
    if not decided or target_n <= 0:
        return None
    p = win_rate(decided) / 100.0
    z_a = _Z_ALPHA_ONE_SIDED.get(alpha)
    z_b = _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    n_eff = target_n / design_effect(decided)
    if n_eff <= 0:
        return None
    return 100.0 * (z_a + z_b) * float(np.sqrt(2.0 * p * (1.0 - p) / n_eff))


def project_target_n(*, observed_n: int, observed_days: int,
                     target_days: int) -> int:
    """Project achievable N by window length, from a window we are allowed
    to look at. Reading a count out of 2024-25 to size a run is still
    contact with the validation window."""
    if observed_days <= 0:
        return 0
    return int(round(observed_n * target_days / observed_days))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_mde.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_mde.py
git commit -m "feat(v72): MDE precheck -- refuse a shot at a question the sample cannot answer"
```

---

### Task A5: The clause set and `evaluate()`

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py`
- Test: `tests/backtesting/test_acceptance_gate.py`

**Interfaces:**
- Consumes: everything from A1–A4.
- Produces: `ClauseResult` (fields `name`, `verdict`, `detail`, `value`, `threshold`), `AcceptanceResult` (fields `stage`, `verdict`, `clauses`, `strata`, `split`, `version`), `evaluate(baseline, component, *, stage, permutation_p=None, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> AcceptanceResult`, `population_split(baseline, component) -> dict`, `median_planned_rr(trades) -> float | None`, `mean_win_r(trades) -> float | None`.

Constants: `NON_INFERIORITY_R = -0.01`, `GEOMETRY_MAX_DROP_PCT = 2.0`, `VOLUME_MAX_CUT_PCT = 25.0`.

Stage semantics: `"walkforward"` requires clauses 1–4 and 6; `"validation"` requires all six and **fails** if `permutation_p` is not supplied. A clause that cannot apply (clause 6 on a non-subset feature) is `SKIPPED`, and a `SKIPPED` clause never blocks a `PASS` — but it is printed, so a skip is a visible fact rather than a silent one.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_gate.py
"""The pre-registered clause set.

Clause 3 is the load-bearing one: without it, 'win rate up, expectancy
flat' is passed trivially by pulling targets nearer, and the repo ships a
stream of features that feel better and earn identically.
"""
from swingbot.core.backtesting.acceptance import (
    ArmTrade, evaluate, mean_win_r, median_planned_rr, population_split,
)


def mk(ticker, outcome, *, rr=2.0, r=None, date="2021-01-01",
       strategy="MACD", horizon="3m"):
    if r is None:
        r = {"win": 2.0, "loss": -1.0}.get(outcome, 0.0)
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon,
                    entry_date=date, outcome=outcome, r_multiple=r,
                    planned_rr=rr)


def good_filter_arms(n_tickers=30):
    """A feature that removes only losers -- real discrimination, and the
    shape that SHOULD pass every clause."""
    baseline, component = [], []
    for t in range(n_tickers):
        for i in range(10):
            trade = mk(f"T{t}", "win" if i < 4 else "loss",
                       date=f"2021-03-{i + 1:02d}")
            baseline.append(trade)
            if not (i >= 8):          # drop 2 losers of every 10
                component.append(trade)
    return baseline, component


def test_a_real_discriminator_passes():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.verdict == "PASS"
    assert res.clause("win_rate").verdict == "PASS"
    assert res.clause("mechanism").verdict == "PASS"


def test_geometry_cheat_is_rejected():
    """Same trades, but the component pulled every target from 2.0R to
    1.4R. Win rate rises; the feature is worthless. Clause 3 must catch it
    even though clause 1 is happy."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            b.append(mk(f"T{t}", "win" if i < 4 else "loss", rr=2.0,
                        date=f"2021-03-{i + 1:02d}"))
            c.append(mk(f"T{t}", "win" if i < 7 else "loss", rr=1.4,
                        r=1.4 if i < 7 else -1.0,
                        date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("win_rate").verdict == "PASS"
    assert res.clause("geometry").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_volume_floor_rejects_a_filter_that_barely_trades():
    b, c = [], []
    for t in range(30):
        for i in range(10):
            trade = mk(f"T{t}", "win" if i < 4 else "loss",
                       date=f"2021-03-{i + 1:02d}")
            b.append(trade)
            if i < 3:                 # keeps 30% -> a 70% cut
                c.append(trade)
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("volume").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_profit_floor_rejects_a_win_rate_bought_with_expectancy():
    """Removes big winners along with losers: win rate up, expectancy
    materially down."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            outcome = "win" if i < 4 else "loss"
            r = 8.0 if i == 0 else (2.0 if outcome == "win" else -1.0)
            trade = mk(f"T{t}", outcome, r=r, date=f"2021-03-{i + 1:02d}")
            b.append(trade)
            if i not in (0, 8, 9):    # drop the huge winner and two losers
                c.append(trade)
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("profit_floor").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_mechanism_clause_skipped_for_a_non_subset_feature():
    """A feature that changes outcomes rather than removing trades has no
    'removed population' -- the clause is SKIPPED and says so, and the
    skip does not block a PASS."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            b.append(mk(f"T{t}", "win" if i < 4 else "loss",
                        date=f"2021-03-{i + 1:02d}"))
            c.append(mk(f"T{t}", "win" if i < 6 else "loss",
                        date=f"2021-03-{i + 1:02d}"))
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("mechanism").verdict == "SKIPPED"
    assert res.verdict == "PASS"


def test_validation_stage_fails_without_a_permutation_p():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="validation", n_resamples=300, seed=42)
    assert res.clause("permutation").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_validation_stage_passes_with_a_significant_permutation_p():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="validation", permutation_p=0.01,
                   n_resamples=300, seed=42)
    assert res.clause("permutation").verdict == "PASS"
    assert res.verdict == "PASS"


def test_walkforward_stage_does_not_require_permutation():
    b, c = good_filter_arms()
    res = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    assert res.clause("permutation").verdict == "SKIPPED"


def test_population_split_names_removed_changed_and_unchanged():
    b = [mk("T1", "win", date="2021-01-01"), mk("T1", "loss", date="2021-01-02"),
         mk("T1", "win", date="2021-01-03")]
    c = [mk("T1", "win", date="2021-01-01"), mk("T1", "win", date="2021-01-02")]
    split = population_split(b, c)
    assert len(split["removed"]) == 1        # 01-03 is gone
    assert len(split["changed"]) == 1        # 01-02 flipped loss -> win
    assert len(split["unchanged"]) == 1
    assert split["is_subset"] is False       # an outcome changed


def test_geometry_helpers():
    trades = [mk("T1", "win", rr=2.0, r=2.0), mk("T1", "loss", rr=3.0, r=-1.0),
              mk("T1", "win", rr=1.0, r=1.0)]
    assert median_planned_rr(trades) == 2.0
    assert mean_win_r(trades) == 1.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/backtesting/acceptance.py`:

```python
#: PRE-REGISTERED gate constants. Changing one is a new pre-registration,
#: not a tuning step -- see docs/claude/backtest-methodology.md.
NON_INFERIORITY_R = -0.01      # clause 2: how much ExpR may slip, at 95%
GEOMETRY_MAX_DROP_PCT = 2.0    # clause 3: max fall in median RR / mean win R
VOLUME_MAX_CUT_PCT = 25.0      # clause 4: max cut in accepted alerts

STAGES = ("walkforward", "validation")


@dataclass(frozen=True)
class ClauseResult:
    name: str
    verdict: str          # PASS | FAIL | SKIPPED
    detail: str
    value: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class AcceptanceResult:
    stage: str
    verdict: str
    clauses: tuple
    strata: list
    split: dict
    version: int = VERSION

    def clause(self, name: str) -> ClauseResult:
        for c in self.clauses:
            if c.name == name:
                return c
        raise KeyError(name)


def median_planned_rr(trades) -> float | None:
    vals = [t.planned_rr for t in trades if t.planned_rr is not None]
    return float(np.median(vals)) if vals else None


def mean_win_r(trades) -> float | None:
    vals = [t.r_multiple for t in trades
            if t.outcome == "win" and t.r_multiple is not None]
    return float(np.mean(vals)) if vals else None


def population_split(baseline, component) -> dict:
    """Partition the baseline against the component by pairing key.

    `is_subset` is True only when the component removes trades and changes
    no surviving outcome -- the shape a filter/veto has, and the only shape
    clause 6's mechanism question is meaningful for.
    """
    b_by = {t.key: t for t in baseline}
    c_by = {t.key: t for t in component}
    removed = [t for k, t in b_by.items() if k not in c_by]
    added = [t for k, t in c_by.items() if k not in b_by]
    changed, unchanged = [], []
    for k, bt in b_by.items():
        ct = c_by.get(k)
        if ct is None:
            continue
        (changed if ct.outcome != bt.outcome else unchanged).append((bt, ct))
    return {"removed": removed, "added": added, "changed": changed,
            "unchanged": unchanged,
            "is_subset": not added and not changed and bool(removed)}


def _clause_win_rate(baseline, component, n_resamples, seed) -> ClauseResult:
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.p_greater_than_zero is None:
        return ClauseResult("win_rate", "FAIL",
                            "no decided trades in one arm", None, 0.0)
    ok = res.point > 0.0 and res.p_greater_than_zero < ALPHA
    return ClauseResult(
        "win_rate", "PASS" if ok else "FAIL",
        f"standardised dWR {res.point:+.2f}pp [{res.lo:+.2f},{res.hi:+.2f}] "
        f"p={res.p_greater_than_zero:.4f}", res.point, 0.0)


def _clause_profit_floor(baseline, component, n_resamples, seed) -> ClauseResult:
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.lo is None:
        return ClauseResult("profit_floor", "FAIL",
                            "no closed trades in one arm", None,
                            NON_INFERIORITY_R)
    ok = res.lo > NON_INFERIORITY_R
    return ClauseResult(
        "profit_floor", "PASS" if ok else "FAIL",
        f"dExpR {res.point:+.4f}R, lower bound {res.lo:+.4f}R vs floor "
        f"{NON_INFERIORITY_R:+.4f}R", res.lo, NON_INFERIORITY_R)


def _pct_drop(before: float | None, after: float | None) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return 100.0 * (before - after) / abs(before)


def _clause_geometry(baseline, component) -> ClauseResult:
    rr_drop = _pct_drop(median_planned_rr(baseline), median_planned_rr(component))
    win_drop = _pct_drop(mean_win_r(baseline), mean_win_r(component))
    drops = [d for d in (rr_drop, win_drop) if d is not None]
    if not drops:
        return ClauseResult("geometry", "SKIPPED",
                            "no planned RR or win R on either arm", None,
                            GEOMETRY_MAX_DROP_PCT)
    worst = max(drops)
    ok = worst <= GEOMETRY_MAX_DROP_PCT
    return ClauseResult(
        "geometry", "PASS" if ok else "FAIL",
        f"median planned RR drop {rr_drop if rr_drop is None else f'{rr_drop:+.2f}%'}, "
        f"mean win R drop {win_drop if win_drop is None else f'{win_drop:+.2f}%'} "
        f"vs max {GEOMETRY_MAX_DROP_PCT:.1f}%", worst, GEOMETRY_MAX_DROP_PCT)


def _clause_volume(baseline, component) -> ClauseResult:
    if not baseline:
        return ClauseResult("volume", "FAIL", "empty baseline arm", None,
                            VOLUME_MAX_CUT_PCT)
    cut = 100.0 * (len(baseline) - len(component)) / len(baseline)
    ok = cut <= VOLUME_MAX_CUT_PCT
    return ClauseResult(
        "volume", "PASS" if ok else "FAIL",
        f"alert cut {cut:+.2f}% vs max {VOLUME_MAX_CUT_PCT:.1f}% "
        f"({len(baseline)} -> {len(component)})", cut, VOLUME_MAX_CUT_PCT)


def _clause_permutation(stage: str, permutation_p: float | None) -> ClauseResult:
    if stage != "validation":
        return ClauseResult("permutation", "SKIPPED",
                            f"not required at stage '{stage}'", None, ALPHA)
    if permutation_p is None:
        return ClauseResult(
            "permutation", "FAIL",
            "no permutation p supplied -- run permutation_test.py and pass "
            "its result; a validation verdict without a null distribution "
            "is not a verdict", None, ALPHA)
    ok = permutation_p < ALPHA
    return ClauseResult("permutation", "PASS" if ok else "FAIL",
                        f"permutation p={permutation_p:.4f} vs alpha {ALPHA}",
                        permutation_p, ALPHA)


def _clause_mechanism(split: dict) -> ClauseResult:
    """Are the trades this feature removed actually the bad ones?

    Clause 1 can pass on a lucky pooled shift. This asks the mechanism
    question directly, and it is what makes a passing result explainable
    rather than merely significant.
    """
    if not split["is_subset"]:
        return ClauseResult("mechanism", "SKIPPED",
                            "not a subset feature -- no removed population "
                            "to interrogate", None, None)
    removed = split["removed"]
    retained = [ct for _, ct in split["unchanged"]]
    r_wr, k_wr = win_rate(removed), win_rate(retained)
    r_exp = expectancy_r(removed)
    if r_wr is None or k_wr is None or r_exp is None:
        return ClauseResult("mechanism", "FAIL",
                            "removed or retained population has no decided "
                            "trades to compare", None, None)
    ok = r_wr < k_wr and r_exp <= 0.0
    return ClauseResult(
        "mechanism", "PASS" if ok else "FAIL",
        f"removed WR {r_wr:.2f}% vs retained {k_wr:.2f}%, removed ExpR "
        f"{r_exp:+.4f}R (must be <= 0)", r_wr, k_wr)


def evaluate(baseline, component, *, stage: str,
             permutation_p: float | None = None,
             n_resamples: int = BOOTSTRAP_RESAMPLES,
             seed: int = 42) -> AcceptanceResult:
    """The gate. Every applicable clause must PASS.

    A SKIPPED clause never blocks a PASS, but it is always reported -- a
    skip is a fact about the measurement, not an absence of one.
    """
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    split = population_split(baseline, component)
    clauses = (
        _clause_win_rate(baseline, component, n_resamples, seed),
        _clause_profit_floor(baseline, component, n_resamples, seed),
        _clause_geometry(baseline, component),
        _clause_volume(baseline, component),
        _clause_permutation(stage, permutation_p),
        _clause_mechanism(split),
    )
    verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"
    return AcceptanceResult(stage=stage, verdict=verdict, clauses=clauses,
                            strata=stratum_table(baseline, component),
                            split={k: len(v) if isinstance(v, list) else v
                                   for k, v in split.items()})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_gate.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_gate.py
git commit -m "feat(v72): the six-clause acceptance gate"
```

---

### Task A6: Results-doc rendering

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py`
- Test: `tests/backtesting/test_acceptance_render.py`

**Interfaces:**
- Consumes: `AcceptanceResult`, `ClauseResult` from A5.
- Produces: `render_markdown(result, *, title, window, notes=None) -> str`, `render_json(result) -> dict`.

The renderer lives beside the computation so a results doc cannot drift from the numbers that produced it — the failure mode where a table is hand-copied and a digit changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_render.py
from swingbot.core.backtesting.acceptance import (
    ArmTrade, evaluate, render_json, render_markdown,
)


def arms():
    b, c = [], []
    for t in range(20):
        for i in range(10):
            trade = ArmTrade(ticker=f"T{t}", strategy="MACD", horizon_key="3m",
                             entry_date=f"2021-03-{i + 1:02d}",
                             outcome="win" if i < 4 else "loss",
                             r_multiple=2.0 if i < 4 else -1.0, planned_rr=2.0)
            b.append(trade)
            if i < 8:
                c.append(trade)
    return b, c


def test_markdown_carries_every_clause_and_the_verdict():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    md = render_markdown(res, title="v99 test component",
                         window="2021-01-01..2021-12-31")
    for name in ("win_rate", "profit_floor", "geometry", "volume",
                 "permutation", "mechanism"):
        assert name in md
    assert "v99 test component" in md
    assert "2021-01-01..2021-12-31" in md
    assert res.verdict in md


def test_markdown_records_the_procedure_version_and_seed():
    """A results doc that does not say which procedure produced it cannot
    be re-read safely two quarters later."""
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=7)
    md = render_markdown(res, title="t", window="w")
    assert "acceptance v2" in md
    assert "seed 7" in md


def test_markdown_includes_the_per_stratum_table():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    md = render_markdown(res, title="t", window="w")
    assert "MACD" in md and "3m" in md


def test_notes_are_rendered_when_given():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    md = render_markdown(res, title="t", window="w",
                         notes="Cell selected on fold-train only.")
    assert "Cell selected on fold-train only." in md


def test_render_json_round_trips_the_clause_verdicts():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    blob = render_json(res)
    assert blob["verdict"] == res.verdict
    assert blob["acceptance_version"] == 2
    assert {c["name"] for c in blob["clauses"]} == {
        "win_rate", "profit_floor", "geometry", "volume", "permutation",
        "mechanism"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_markdown'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/backtesting/acceptance.py`:

```python
def render_json(result: AcceptanceResult) -> dict:
    return {
        "acceptance_version": result.version,
        "stage": result.stage,
        "verdict": result.verdict,
        "seed": result.seed,
        "clauses": [{"name": c.name, "verdict": c.verdict, "detail": c.detail,
                     "value": c.value, "threshold": c.threshold}
                    for c in result.clauses],
        "strata": [{**r, "stratum": list(r["stratum"])} for r in result.strata],
        "split": result.split,
    }


def _fmt_pct(value) -> str:
    """Win rates, in percent."""
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_r(value) -> str:
    """R-multiples need more places than a percentage: the deltas that
    matter here are third-decimal (v68's was -0.0097R), and rounding one to
    two places prints an honest number as 0.01 or -0.01."""
    return "n/a" if value is None else f"{value:+.4f}"


def render_markdown(result: AcceptanceResult, *, title: str, window: str,
                    notes: str | None = None) -> str:
    """The results-doc body. Rendered from the same object the gate
    returned, so the table and the verdict cannot drift apart."""
    lines = [
        f"# {title} — {result.stage.upper()}",
        "",
        f"Procedure: **acceptance v{result.version}** "
        f"(`swingbot/core/backtesting/acceptance.py`), "
        f"bootstrap seed {result.seed}.",
        f"**Window:** {window}",
        "",
        "## Clauses",
        "",
        "| Clause | Verdict | Detail |",
        "|---|---|---|",
    ]
    for c in result.clauses:
        lines.append(f"| `{c.name}` | **{c.verdict}** | {c.detail} |")
    lines += [
        "",
        f"**Overall: {result.verdict}**",
        "",
        "## Population split",
        "",
        f"- removed: {result.split['removed']}",
        f"- changed: {result.split['changed']}",
        f"- unchanged: {result.split['unchanged']}",
        f"- added: {result.split['added']}",
        f"- subset feature: {result.split['is_subset']}",
        "",
        "## Per stratum",
        "",
        "| Strategy | Horizon | Base N | Comp N | Base WR | Comp WR | "
        "Base ExpR | Comp ExpR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in result.strata:
        strategy, horizon = row["stratum"]
        lines.append(
            f"| {strategy} | {horizon} | {row['baseline_n']} | "
            f"{row['component_n']} | {_fmt_pct(row['baseline_win_rate'])} | "
            f"{_fmt_pct(row['component_win_rate'])} | "
            f"{_fmt_r(row['baseline_expectancy_r'])} | "
            f"{_fmt_r(row['component_expectancy_r'])} |")
    if notes:
        lines += ["", "## Notes", "", notes]
    return "\n".join(lines) + "\n"
```

`result.seed` does not exist yet — add it in the same edit. In the
`AcceptanceResult` dataclass from Task A5, add one field **above** the
defaulted `version` field (a non-defaulted field cannot follow a defaulted
one):

```python
@dataclass(frozen=True)
class AcceptanceResult:
    stage: str
    verdict: str
    clauses: tuple
    strata: list
    split: dict
    seed: int = 42          # recorded so a results doc is reproducible
    version: int = VERSION
```

and pass it from `evaluate()`'s existing `seed` parameter in the return:

```python
    return AcceptanceResult(stage=stage, verdict=verdict, clauses=clauses,
                            strata=stratum_table(baseline, component),
                            split={k: len(v) if isinstance(v, list) else v
                                   for k, v in split.items()},
                            seed=seed)
```

A results doc that cannot name the seed that produced it cannot be
re-derived two quarters later, which is the whole reason the seed is
pre-registered rather than left to a default.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_render.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_render.py
git commit -m "feat(v72): render results docs from the gate object, not by hand"
```

---
