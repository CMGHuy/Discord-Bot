# v72 — Validation acceptance v2, Part 1a: the acceptance core

> Part of the v72 plan. Header block, global constraints, parallelisation map
> and the part table live in `_0-index`. **Read that first** — every task here
> inherits its constraints, and two of them (numpy-only, v68's verdict
> untouchable) are the ones a task is most likely to violate without noticing.

# Phase A — the acceptance module

### Task A1: The `ArmTrade` record and its adapters

**Files:**
- Create: `swingbot/core/backtesting/acceptance.py`
- Test: `tests/backtesting/test_acceptance_records.py`

**Interfaces:**
- Consumes: `swingbot.core.planning.plan_types.TradePlanV2` (fields `ticker`, `strategy`, `horizon_key`, `entry_price`, `trigger_price`, `stop_loss`, `tp1`); `swingbot.core.backtesting.backtest.BacktestTrade` (fields `entry_date`, `entry`, `stop_loss`, `take_profit`, `outcome`, `r_multiple`).
- Produces: `ArmTrade` (frozen dataclass), `ArmTrade.key`, `ArmTrade.stratum`, `arm_trade_from_plan(plan, *, entry_date, outcome, r_multiple) -> ArmTrade`, `arm_trade_from_backtest(trade, *, ticker, strategy, horizon_key) -> ArmTrade`, `planned_rr(entry, stop, target) -> float | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_records.py
"""ArmTrade is the neutral record every acceptance clause reads.

It exists so acceptance.py depends on neither BacktestTrade nor any
measurement script's private row dialect -- measure_dcb_veto's rows, for
one, carry no `strategy` and no geometry at all.
"""
from swingbot.core.backtesting.acceptance import (
    ArmTrade, arm_trade_from_backtest, arm_trade_from_plan, planned_rr,
)


def _trade(**kw):
    base = dict(ticker="AAPL", strategy="MACD", horizon_key="3m",
                entry_date="2021-03-01", outcome="win", r_multiple=1.5,
                planned_rr=2.0)
    base.update(kw)
    return ArmTrade(**base)


def test_key_is_the_pairing_tuple():
    t = _trade()
    assert t.key == ("AAPL", "MACD", "3m", "2021-03-01")


def test_stratum_is_strategy_by_horizon():
    assert _trade().stratum == ("MACD", "3m")


def test_planned_rr_is_reward_over_risk():
    # entry 100, stop 95 -> risk 5; target 110 -> reward 10; RR 2.0
    assert planned_rr(100.0, 95.0, 110.0) == 2.0


def test_planned_rr_is_direction_agnostic():
    # A bearish plan: entry 100, stop 105, target 90. Same 2.0.
    assert planned_rr(100.0, 105.0, 90.0) == 2.0


def test_planned_rr_is_none_on_zero_risk():
    assert planned_rr(100.0, 100.0, 110.0) is None


def test_from_plan_prefers_entry_price_over_trigger():
    class _Plan:
        ticker, strategy, horizon_key = "MSFT", "VWAP", "4w"
        entry_price, trigger_price = 50.0, 49.0
        stop_loss, tp1 = 45.0, 60.0
    t = arm_trade_from_plan(_Plan(), entry_date="2021-06-02",
                            outcome="loss", r_multiple=-1.0)
    assert t.ticker == "MSFT" and t.strategy == "VWAP"
    assert t.entry_date == "2021-06-02"
    assert t.planned_rr == 2.0        # |60-50| / |50-45|


def test_from_plan_falls_back_to_trigger_price():
    class _Plan:
        ticker, strategy, horizon_key = "MSFT", "VWAP", "4w"
        entry_price, trigger_price = None, 50.0
        stop_loss, tp1 = 45.0, 60.0
    assert arm_trade_from_plan(_Plan(), entry_date="2021-06-02",
                               outcome="win", r_multiple=2.0).planned_rr == 2.0


def test_from_backtest_takes_context_the_trade_does_not_carry():
    class _BT:
        entry_date, entry, stop_loss, take_profit = "2022-01-04", 10.0, 9.0, 12.0
        outcome, r_multiple = "win", 2.0
    t = arm_trade_from_backtest(_BT(), ticker="SPY", strategy="RSI",
                                horizon_key="2m")
    assert t.stratum == ("RSI", "2m")
    assert t.planned_rr == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_records.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.acceptance'`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/backtesting/acceptance.py
"""The acceptance gate -- what a feature must prove before it ships on.

Read `docs/claude/backtest-methodology.md` before changing anything here.
The clause set and its constants are PRE-REGISTERED: they are the bar, and
a component that fails them is dropped and documented, never re-measured
against a bar moved to fit it.

Win rate is the objective; expectancy is a non-inferiority constraint. The
two move against each other along the *geometry* axis (break-even win rate
at reward:risk X is 1/(1+X), so a nearer target buys win rate and no
profit) and together only along the *discrimination* axis. Clause 3 exists
to force a feature onto the second axis.

numpy only -- scipy is NOT in requirements.txt and is absent from the
Docker image this module ships in.
"""
from __future__ import annotations

from dataclasses import dataclass

VERSION = 2   # acceptance-procedure version, recorded in every results doc


@dataclass(frozen=True)
class ArmTrade:
    """One trade in one arm, carrying exactly what the clauses read.

    Deliberately not BacktestTrade: that record has no ticker/strategy/
    horizon (they live on its BacktestSummary parent) and the measurement
    scripts each carry their own row dialect. This is the shared shape both
    adapt into.
    """
    ticker: str
    strategy: str
    horizon_key: str
    entry_date: str
    outcome: str                  # win | loss | scratch | timeout | not_triggered
    r_multiple: float | None
    planned_rr: float | None

    @property
    def key(self) -> tuple:
        """Pairing key across arms."""
        return (self.ticker, self.strategy, self.horizon_key, self.entry_date)

    @property
    def stratum(self) -> tuple:
        """Mix-standardisation and per-stratum reporting unit."""
        return (self.strategy, self.horizon_key)


def planned_rr(entry: float, stop: float, target: float) -> float | None:
    """Reward:risk as the plan was written, before the market answered.

    Direction-agnostic by construction (both legs are absolute), so a
    bearish plan and its mirror-image bullish plan return the same number.
    None on zero risk -- a plan that cannot lose cannot be priced.
    """
    risk = abs(entry - stop)
    if not risk:
        return None
    return abs(target - entry) / risk


def arm_trade_from_plan(plan, *, entry_date: str, outcome: str,
                        r_multiple: float | None) -> ArmTrade:
    """Adapt a TradePlanV2 (what replay_scenarios yields) plus its outcome."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return ArmTrade(ticker=plan.ticker, strategy=plan.strategy,
                    horizon_key=plan.horizon_key, entry_date=entry_date,
                    outcome=outcome, r_multiple=r_multiple,
                    planned_rr=planned_rr(entry, plan.stop_loss, plan.tp1))


def arm_trade_from_backtest(trade, *, ticker: str, strategy: str,
                            horizon_key: str) -> ArmTrade:
    """Adapt a BacktestTrade. The three context fields live on the trade's
    BacktestSummary parent, not the trade, so the caller supplies them."""
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon_key,
                    entry_date=trade.entry_date, outcome=trade.outcome,
                    r_multiple=trade.r_multiple,
                    planned_rr=planned_rr(trade.entry, trade.stop_loss,
                                          trade.take_profit))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_records.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_records.py
git commit -m "feat(v72): ArmTrade -- the neutral record the acceptance clauses read"
```

---

### Task A2: Mix-standardised win rate

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py`
- Test: `tests/backtesting/test_acceptance_stats.py`

**Interfaces:**
- Consumes: `ArmTrade` from Task A1.
- Produces: `win_rate(trades) -> float | None`, `expectancy_r(trades) -> float | None`, `stratum_weights(trades) -> dict[tuple, float]`, `standardised_win_rate(trades, weights) -> float | None`, `stratum_table(baseline, component) -> list[dict]`.

This is the clause that kills the Simpson artifact: a feature that only changes *which* strata are represented, without improving any single one, must score a standardised ΔWR of ~0 and fail.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_stats.py
"""Win rate is over win+loss only; expectancy is over all CLOSED trades
(scratches and timeouts included, not_triggered excluded). That split is
the methodology doc's, and measure_dcb_veto._aggregate already obeys it.
"""
from swingbot.core.backtesting.acceptance import (
    ArmTrade, expectancy_r, standardised_win_rate, stratum_table,
    stratum_weights, win_rate,
)


def mk(strategy, horizon, outcome, r=0.0, ticker="AAPL", date="2021-01-01"):
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key=horizon,
                    entry_date=date, outcome=outcome, r_multiple=r,
                    planned_rr=2.0)


def test_win_rate_ignores_scratches_and_timeouts():
    trades = [mk("MACD", "3m", "win"), mk("MACD", "3m", "loss"),
              mk("MACD", "3m", "scratch"), mk("MACD", "3m", "timeout")]
    assert win_rate(trades) == 50.0


def test_win_rate_is_none_with_no_decided_trades():
    assert win_rate([mk("MACD", "3m", "scratch")]) is None


def test_expectancy_includes_scratches_and_timeouts():
    trades = [mk("MACD", "3m", "win", r=2.0), mk("MACD", "3m", "loss", r=-1.0),
              mk("MACD", "3m", "scratch", r=0.0)]
    assert abs(expectancy_r(trades) - (1.0 / 3.0)) < 1e-12


def test_expectancy_excludes_not_triggered():
    trades = [mk("MACD", "3m", "win", r=2.0),
              mk("MACD", "3m", "not_triggered", r=None)]
    assert expectancy_r(trades) == 2.0


def test_stratum_weights_sum_to_one_over_decided_trades():
    trades = [mk("MACD", "3m", "win"), mk("MACD", "3m", "loss"),
              mk("RSI", "4w", "win"), mk("RSI", "4w", "scratch")]
    w = stratum_weights(trades)
    assert abs(sum(w.values()) - 1.0) < 1e-12
    # RSI/4w has ONE decided trade (the scratch does not count)
    assert abs(w[("RSI", "4w")] - 1 / 3) < 1e-12


def test_mix_shift_alone_produces_zero_standardised_delta():
    """THE regression test for finding 7.

    Baseline: a strong stratum at 80% WR and a weak one at 20%, equally
    sized. The 'feature' removes half the weak stratum and nothing else --
    no within-stratum outcome changes at all. Raw win rate jumps; the
    standardised one must not move, because nothing actually improved.
    """
    strong = [mk("MACD", "3m", "win") for _ in range(8)] + \
             [mk("MACD", "3m", "loss") for _ in range(2)]
    # Interleaved 1-in-5 so ANY prefix of `weak` is still 20% -- otherwise
    # the slice below would change the stratum's own win rate and the test
    # would be measuring two things at once.
    weak = ([mk("RSI", "4w", "win")] + [mk("RSI", "4w", "loss")] * 4) * 2
    baseline = strong + weak
    component = strong + weak[:5]      # drops 5 of the weak stratum's 10

    weights = stratum_weights(baseline)
    raw_delta = win_rate(component) - win_rate(baseline)
    std_delta = (standardised_win_rate(component, weights)
                 - standardised_win_rate(baseline, weights))

    assert raw_delta > 5.0             # materially non-zero
    assert abs(std_delta) < 1e-9       # and entirely an artifact


def test_real_within_stratum_improvement_survives_standardisation():
    """The mirror case: the feature removes only LOSERS from one stratum.
    That is genuine discrimination and must show up standardised."""
    baseline = [mk("MACD", "3m", "win") for _ in range(5)] + \
               [mk("MACD", "3m", "loss") for _ in range(5)]
    component = [mk("MACD", "3m", "win") for _ in range(5)] + \
                [mk("MACD", "3m", "loss") for _ in range(2)]
    weights = stratum_weights(baseline)
    std_delta = (standardised_win_rate(component, weights)
                 - standardised_win_rate(baseline, weights))
    assert std_delta > 10.0


def test_stratum_table_reports_both_arms_per_stratum():
    baseline = [mk("MACD", "3m", "win"), mk("MACD", "3m", "loss"),
                mk("RSI", "4w", "loss")]
    component = [mk("MACD", "3m", "win")]
    rows = stratum_table(baseline, component)
    by = {r["stratum"]: r for r in rows}
    assert by[("MACD", "3m")]["baseline_n"] == 2
    assert by[("MACD", "3m")]["component_n"] == 1
    assert by[("MACD", "3m")]["component_win_rate"] == 100.0
    # A stratum the component emptied still appears, with None, not a gap.
    assert by[("RSI", "4w")]["component_n"] == 0
    assert by[("RSI", "4w")]["component_win_rate"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_stats.py -v`
Expected: FAIL — `ImportError: cannot import name 'win_rate'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/backtesting/acceptance.py`:

```python
from collections import Counter, defaultdict

import numpy as np

#: Outcomes that count toward the win-rate denominator.
DECIDED = ("win", "loss")
#: Outcomes that count as a closed trade for expectancy.
CLOSED = ("win", "loss", "scratch", "timeout")


def win_rate(trades) -> float | None:
    """Percent, over decided trades only. None when nothing was decided."""
    decided = [t for t in trades if t.outcome in DECIDED]
    if not decided:
        return None
    return 100.0 * sum(1 for t in decided if t.outcome == "win") / len(decided)


def expectancy_r(trades) -> float | None:
    """Mean R over all CLOSED trades -- scratches and timeouts drag it down,
    which is the point: they are capital that was committed and returned
    nothing."""
    rs = [t.r_multiple for t in trades
          if t.outcome in CLOSED and t.r_multiple is not None]
    if not rs:
        return None
    return float(np.mean(rs))


def _by_stratum(trades) -> dict:
    out = defaultdict(list)
    for t in trades:
        out[t.stratum].append(t)
    return out


def stratum_weights(trades) -> dict:
    """Share of DECIDED trades in each (strategy, horizon) stratum."""
    counts = Counter(t.stratum for t in trades if t.outcome in DECIDED)
    total = sum(counts.values())
    if not total:
        return {}
    return {k: v / total for k, v in counts.items()}


def standardised_win_rate(trades, weights: dict) -> float | None:
    """The win rate this arm would show if its stratum mix matched
    `weights` -- i.e. holding composition fixed so only within-stratum
    skill can move the number.

    Strata the arm has no decided trade in are dropped and the remaining
    weights renormalised, rather than imputed: an arm that emptied a
    stratum has no win rate there to standardise, and inventing one would
    reward exactly the mix shift this function exists to neutralise.
    """
    grouped = _by_stratum(trades)
    total = 0.0
    weight_sum = 0.0
    for stratum, weight in weights.items():
        wr = win_rate(grouped.get(stratum, []))
        if wr is None:
            continue
        total += weight * wr
        weight_sum += weight
    if not weight_sum:
        return None
    return total / weight_sum


def stratum_table(baseline, component) -> list:
    """One row per stratum present in EITHER arm, sorted for stable output."""
    b, c = _by_stratum(baseline), _by_stratum(component)
    rows = []
    for stratum in sorted(set(b) | set(c)):
        bt, ct = b.get(stratum, []), c.get(stratum, [])
        rows.append({
            "stratum": stratum,
            "baseline_n": sum(1 for t in bt if t.outcome in DECIDED),
            "component_n": sum(1 for t in ct if t.outcome in DECIDED),
            "baseline_win_rate": win_rate(bt),
            "component_win_rate": win_rate(ct),
            "baseline_expectancy_r": expectancy_r(bt),
            "component_expectancy_r": expectancy_r(ct),
        })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_stats.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_stats.py
git commit -m "feat(v72): mix-standardised win rate -- a stratum shift is not an improvement"
```

---

### Task A3: The ticker-cluster bootstrap

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py`
- Test: `tests/backtesting/test_acceptance_bootstrap.py`

**Interfaces:**
- Consumes: `ArmTrade`, `win_rate`, `expectancy_r`, `standardised_win_rate`, `stratum_weights` from A1–A2.
- Produces: `cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray`, `delta_standardised_win_rate(baseline, component) -> float | None`, `delta_expectancy_r(baseline, component) -> float | None`, `BootstrapResult` (fields `point`, `lo`, `hi`, `p_greater_than_zero`, `n_resamples`, `seed`), `bootstrap_delta(baseline, component, statistic, *, n_resamples, seed) -> BootstrapResult`.

Why tickers and not trades: every trade on one symbol rides the same price path, so they are nowhere near independent. Resampling trades would price that correlation at zero and overstate significance — which is how a 0.01R effect comes to look meaningful.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_bootstrap.py
"""The bootstrap resamples TICKERS, not trades.

Trades on one symbol share a price path. Treating them as independent
overstates power -- the failure that let v68 fire a one-shot budget at a
+0.0104R effect against a +-0.05R standard error.
"""
import numpy as np

from swingbot.core.backtesting.acceptance import (
    ArmTrade, bootstrap_delta, cluster_bootstrap, delta_expectancy_r,
    delta_standardised_win_rate, win_rate,
)


def pop(n_tickers, per_ticker, win_frac, r_win=2.0, r_loss=-1.0, tag=""):
    """A population with an exact win fraction per ticker."""
    out = []
    for t in range(n_tickers):
        for i in range(per_ticker):
            is_win = i < int(per_ticker * win_frac)
            out.append(ArmTrade(
                ticker=f"{tag}T{t}", strategy="MACD", horizon_key="3m",
                entry_date=f"2021-01-{(i % 28) + 1:02d}",
                outcome="win" if is_win else "loss",
                r_multiple=r_win if is_win else r_loss, planned_rr=2.0))
    return out


def test_bootstrap_is_deterministic_under_a_fixed_seed():
    b, c = pop(20, 10, 0.4), pop(20, 10, 0.5)
    a = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    d = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    assert np.array_equal(a, d)


def test_a_different_seed_gives_a_different_draw():
    b, c = pop(20, 10, 0.4), pop(20, 10, 0.5)
    a = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    d = cluster_bootstrap(b, c, delta_standardised_win_rate,
                          n_resamples=200, seed=7)
    assert not np.array_equal(a, d)


def test_identical_arms_give_a_zero_delta_and_a_useless_p_value():
    b = pop(20, 10, 0.4)
    res = bootstrap_delta(b, list(b), delta_standardised_win_rate,
                          n_resamples=200, seed=42)
    assert abs(res.point) < 1e-9
    assert res.p_greater_than_zero > 0.5      # cannot beat its own self


def test_a_large_real_improvement_is_significant():
    b = pop(30, 20, 0.30)
    c = pop(30, 20, 0.70)
    res = bootstrap_delta(b, c, delta_standardised_win_rate,
                          n_resamples=500, seed=42)
    assert res.point > 30.0
    assert res.p_greater_than_zero < 0.05
    assert res.lo > 0.0


def hetero_pop(n_tickers, per_ticker, win_counts, tag=""):
    """Like `pop`, but each ticker gets its own win count (cycled through
    `win_counts`). Heterogeneous tickers are what make cluster count
    matter -- if every ticker were identical, resampling tickers would
    return the same population every draw and the bootstrap would show
    zero variance regardless of how many clusters there are.
    """
    out = []
    for t in range(n_tickers):
        wins = win_counts[t % len(win_counts)]
        for i in range(per_ticker):
            is_win = i < wins
            out.append(ArmTrade(
                ticker=f"{tag}T{t}", strategy="MACD", horizon_key="3m",
                entry_date=f"2021-01-{(i % 28) + 1:02d}",
                outcome="win" if is_win else "loss",
                r_multiple=2.0 if is_win else -1.0, planned_rr=2.0))
    return out


def test_clustering_widens_the_interval_versus_pretending_independence():
    """Identical trade counts and identical pooled win rates -- 4 tickers
    x 100 trades against 40 tickers x 10. Both arms move +10pp. The
    4-cluster interval must be WIDER: that is the within-symbol
    correlation being priced instead of ignored, and it is exactly the
    inflation that let a 0.0104R effect look meaningful.
    """
    few = hetero_pop(4, 100, [20, 40, 60, 30])
    few_c = hetero_pop(4, 100, [30, 50, 70, 40])
    many = hetero_pop(40, 10, [2, 4, 6, 3])
    many_c = hetero_pop(40, 10, [3, 5, 7, 4])
    # Same N and same pooled win rate on both sides of the comparison.
    assert len(few) == len(many) == 400
    assert abs(win_rate(few) - win_rate(many)) < 1e-9

    wide = bootstrap_delta(few, few_c, delta_standardised_win_rate,
                           n_resamples=500, seed=42)
    narrow = bootstrap_delta(many, many_c, delta_standardised_win_rate,
                             n_resamples=500, seed=42)
    assert (wide.hi - wide.lo) > (narrow.hi - narrow.lo)


def test_expectancy_delta_tracks_the_r_multiples():
    b = pop(20, 10, 0.50, r_win=2.0, r_loss=-1.0)
    c = pop(20, 10, 0.50, r_win=3.0, r_loss=-1.0)
    assert delta_expectancy_r(b, c) > 0.4


def test_coverage_is_about_95_percent_on_a_known_delta():
    """Acceptance criterion 2 from the spec: the 95% interval must contain
    the true value about 95% of the time. 200 draws, not 1000, so the test
    stays under the ~7s per-file budget -- the tolerance is widened to
    match rather than the claim weakened."""
    rng = np.random.default_rng(2026)
    hits = 0
    trials = 200
    for _ in range(trials):
        b, c = [], []
        for t in range(25):
            for i in range(8):
                bw = rng.random() < 0.40
                cw = rng.random() < 0.50
                for arm, is_win in ((b, bw), (c, cw)):
                    arm.append(ArmTrade(
                        ticker=f"T{t}", strategy="MACD", horizon_key="3m",
                        entry_date=f"2021-02-{i + 1:02d}",
                        outcome="win" if is_win else "loss",
                        r_multiple=2.0 if is_win else -1.0, planned_rr=2.0))
        res = bootstrap_delta(b, c, delta_standardised_win_rate,
                              n_resamples=200, seed=int(rng.integers(1e6)))
        if res.lo <= 10.0 <= res.hi:      # true delta is 50 - 40 = 10pp
            hits += 1
    assert 0.88 <= hits / trials <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_bootstrap.py -v`
Expected: FAIL — `ImportError: cannot import name 'bootstrap_delta'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/backtesting/acceptance.py`:

```python
#: Pre-registered. 10k resamples resolves a one-sided p at the 0.05 bar with
#: room to spare; tests override it downward for speed, never a real run.
BOOTSTRAP_RESAMPLES = 10_000
ALPHA = 0.05


@dataclass(frozen=True)
class BootstrapResult:
    point: float | None
    lo: float | None
    hi: float | None
    p_greater_than_zero: float | None
    n_resamples: int
    seed: int


def delta_standardised_win_rate(baseline, component) -> float | None:
    """ΔWR in percentage points, holding the BASELINE's stratum mix fixed.

    Standardising to the baseline (not the component, not the pool) is the
    choice that makes the number mean 'what this feature did to the book we
    already have'.
    """
    weights = stratum_weights(baseline)
    b = standardised_win_rate(baseline, weights)
    c = standardised_win_rate(component, weights)
    if b is None or c is None:
        return None
    return c - b


def delta_expectancy_r(baseline, component) -> float | None:
    b, c = expectancy_r(baseline), expectancy_r(component)
    if b is None or c is None:
        return None
    return c - b


def _group_by_ticker(trades) -> dict:
    out = defaultdict(list)
    for t in trades:
        out[t.ticker].append(t)
    return out


def cluster_bootstrap(baseline, component, statistic, *,
                      n_resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = 42) -> np.ndarray:
    """Resample TICKERS with replacement, recomputing `statistic` on each
    draw. Both arms are resampled with the SAME ticker draw, so the pairing
    between arms survives -- resampling them independently would break the
    very comparison being measured.

    Draws where the statistic is undefined (an arm with no decided trade)
    are dropped, not zero-filled: a missing statistic is missing data, and
    zero is a specific, wrong claim about it.
    """
    b_by, c_by = _group_by_ticker(baseline), _group_by_ticker(component)
    tickers = sorted(set(b_by) | set(c_by))
    if not tickers:
        return np.array([])
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(tickers), size=(n_resamples, len(tickers)))
    out = []
    for row in picks:
        b_draw, c_draw = [], []
        for j in row:
            name = tickers[j]
            b_draw.extend(b_by.get(name, ()))
            c_draw.extend(c_by.get(name, ()))
        value = statistic(b_draw, c_draw)
        if value is not None:
            out.append(value)
    return np.asarray(out, dtype=float)


def bootstrap_delta(baseline, component, statistic, *,
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> BootstrapResult:
    """Point estimate on the real data, interval and one-sided p from the
    ticker-cluster bootstrap.

    `p_greater_than_zero` is the share of draws at or below zero -- the
    bootstrap reading of 'could this delta have been no improvement at
    all'.
    """
    point = statistic(baseline, component)
    draws = cluster_bootstrap(baseline, component, statistic,
                              n_resamples=n_resamples, seed=seed)
    if point is None or draws.size == 0:
        return BootstrapResult(point, None, None, None, n_resamples, seed)
    lo, hi = (float(np.percentile(draws, 100 * ALPHA / 2)),
              float(np.percentile(draws, 100 * (1 - ALPHA / 2))))
    p = float(np.mean(draws <= 0.0))
    return BootstrapResult(float(point), lo, hi, p, n_resamples, seed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_bootstrap.py -v`
Expected: PASS, 7 passed. If `test_coverage_is_about_95_percent_on_a_known_delta` runs over ~20s, lower `trials` to 120 and keep the same tolerance — do **not** widen the tolerance to make it pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_bootstrap.py
git commit -m "feat(v72): ticker-cluster bootstrap -- price the correlation instead of ignoring it"
```

---
