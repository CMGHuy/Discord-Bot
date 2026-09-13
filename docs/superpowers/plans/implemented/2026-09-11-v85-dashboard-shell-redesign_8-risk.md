# v85 Part 8 — Risk, and the wave 2 release

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R8-01 … R8-03 are Group W2-BE**, sequential among themselves, parallel with
the Trades and Watchlist backend strands. **R8-04 … R8-06 are Group W2-UI.**
**R8-07 runs last and alone.**

---

## The honesty problem this part carries

Spec D37 asks for VaR, expected shortfall, annualised volatility, beta, Sharpe
and max drawdown — institutional measures, computed here over a paper book of
perhaps ten to twenty open positions. **These numbers are thin by
construction.** That is not a reason to refuse them; it is the reason every one
of them renders through `sb-stat-tile` (R2-01) with its N, and de-emphasises
itself below `MIN_SAMPLE_N`.

A task in this part that renders a risk figure without its sample size has
produced the exact over-reading the repo's backtest methodology exists to
prevent. There is no exception for "the tile looked cleaner without it".

**Two different samples are in play, and they must not be conflated:**

- VaR, expected shortfall, annualised volatility and beta are computed over the
  **open book's daily returns** — their N is the number of overlapping daily
  bars, not the number of positions.
- Sharpe and max drawdown are computed over the **closed-trade R series** —
  their N is the number of closed trades.

Each metric carries the N it was actually computed from.

---

### Task R8-01: The risk metric computations

**Files:**
- Create: `swingbot/core/analytics/risk_metrics.py`
- Create: `tests/analytics/test_risk_metrics.py`

**Interfaces:**
- Consumes: `get_daily_data_batch` from `swingbot/core/marketdata/data.py`.
- Produces:
  - `portfolio_returns(weights: dict[str, float], bars: dict[str, "pd.DataFrame"]) -> "pd.Series"`
  - `value_at_risk(returns, level: float = 0.95) -> float | None`
  - `expected_shortfall(returns, level: float = 0.95) -> float | None`
  - `annualised_vol(returns) -> float | None`
  - `beta_vs(returns, benchmark) -> float | None`
  - `sharpe_of(r_multiples: list[float]) -> float | None`
  - `max_drawdown_r(r_multiples: list[float]) -> float | None`

  Consumed by R8-03.

**Every formula, stated, so the implementer is not guessing:**

- **Portfolio returns**: daily simple returns per symbol, weighted by each
  position's share of total notional, summed per day. Days where any position
  has no bar are dropped — a partial day would understate the spread.
- **VaR 95%**: the 5th percentile of the portfolio's daily return series,
  reported as a positive loss figure. Historical, not parametric: a normal
  assumption on twenty positions of swing equity is a worse lie than a thin
  empirical quantile.
- **Expected shortfall 95%**: the mean of the returns at or below that 5th
  percentile.
- **Annualised volatility**: sample standard deviation of daily returns ×
  √252.
- **Beta vs SPY**: covariance(portfolio, SPY) ÷ variance(SPY), over the same
  overlapping days.
- **Sharpe of R**: mean(R) ÷ stdev(R) over closed trades. **No risk-free rate
  and no annualisation** — an R-multiple is already excess-over-risk, and
  annualising a series with no fixed cadence invents a time axis the data does
  not have. The tile is labelled "Sharpe (R)" for that reason.
- **Max drawdown (R)**: the largest peak-to-trough fall of the cumulative R
  curve, as a positive number.

**Every one returns `None` rather than a number it cannot justify:** fewer than
`_MIN_BARS` overlapping days, zero variance in the denominator, an empty book.
`None` is never `0.0` here — a zero beta and an unknown beta are opposite
claims.

- [ ] **Step 1: Write the failing test**

Create `tests/analytics/test_risk_metrics.py`:

```python
import math

import pandas as pd
import pytest

from swingbot.core.analytics import risk_metrics as rm


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2026-01-01", periods=len(values)))


def _frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes}, index=pd.bdate_range("2026-01-01", periods=len(closes)))


class TestValueAtRisk:
    def test_is_the_fifth_percentile_reported_as_a_positive_loss(self):
        returns = _series([-0.10, -0.05, 0.0, 0.01, 0.02] * 20)
        var = rm.value_at_risk(returns, level=0.95)
        assert var > 0
        assert var == pytest.approx(0.10, abs=0.02)

    def test_is_none_for_a_series_too_short_to_have_a_tail(self):
        assert rm.value_at_risk(_series([0.01, -0.01])) is None

    def test_is_none_for_an_empty_series(self):
        assert rm.value_at_risk(_series([])) is None


class TestExpectedShortfall:
    def test_is_at_least_as_large_as_var(self):
        returns = _series([-0.20, -0.10, -0.05, 0.0, 0.01] * 20)
        assert rm.expected_shortfall(returns) >= rm.value_at_risk(returns)

    def test_is_none_when_var_is_none(self):
        assert rm.expected_shortfall(_series([0.01])) is None


class TestAnnualisedVol:
    def test_scales_the_daily_deviation_by_root_252(self):
        returns = _series([0.01, -0.01] * 60)
        daily = returns.std(ddof=1)
        assert rm.annualised_vol(returns) == pytest.approx(daily * math.sqrt(252))

    def test_is_none_for_a_flat_series_rather_than_zero(self):
        assert rm.annualised_vol(_series([0.0] * 60)) is None


class TestBeta:
    def test_a_portfolio_that_is_the_benchmark_has_beta_one(self):
        bench = _series([0.01, -0.02, 0.03, -0.01] * 20)
        assert rm.beta_vs(bench, bench) == pytest.approx(1.0)

    def test_a_portfolio_of_twice_the_benchmark_has_beta_two(self):
        bench = _series([0.01, -0.02, 0.03, -0.01] * 20)
        assert rm.beta_vs(bench * 2, bench) == pytest.approx(2.0)

    def test_is_none_when_the_benchmark_never_moves(self):
        bench = _series([0.0] * 80)
        assert rm.beta_vs(_series([0.01] * 80), bench) is None

    def test_uses_only_overlapping_days(self):
        bench = _series([0.01, -0.02, 0.03, -0.01] * 20)
        short = bench.iloc[:40]
        assert rm.beta_vs(short, bench) is not None


class TestSharpeOfR:
    def test_is_mean_over_standard_deviation(self):
        assert rm.sharpe_of([1.0, -1.0, 2.0, -1.0, 1.0]) == pytest.approx(
            pd.Series([1.0, -1.0, 2.0, -1.0, 1.0]).mean()
            / pd.Series([1.0, -1.0, 2.0, -1.0, 1.0]).std(ddof=1)
        )

    def test_is_none_when_every_trade_returned_the_same(self):
        assert rm.sharpe_of([1.0, 1.0, 1.0]) is None

    def test_is_none_for_fewer_than_two_trades(self):
        assert rm.sharpe_of([1.0]) is None

    def test_is_none_for_no_trades_rather_than_zero(self):
        assert rm.sharpe_of([]) is None


class TestMaxDrawdownR:
    def test_measures_the_largest_peak_to_trough_fall(self):
        assert rm.max_drawdown_r([1.0, 1.0, -3.0, 1.0]) == pytest.approx(3.0)

    def test_is_zero_for_a_curve_that_only_rises(self):
        assert rm.max_drawdown_r([1.0, 1.0, 1.0]) == pytest.approx(0.0)

    def test_is_none_for_no_trades(self):
        assert rm.max_drawdown_r([]) is None


class TestPortfolioReturns:
    def test_weights_each_position_by_its_share_of_notional(self):
        bars = {"A": _frame([100, 110]), "B": _frame([100, 100])}
        out = rm.portfolio_returns({"A": 0.5, "B": 0.5}, bars)
        assert out.iloc[-1] == pytest.approx(0.05)

    def test_drops_days_a_position_has_no_bar_for(self):
        bars = {"A": _frame([100, 110, 121]), "B": _frame([100, 100])}
        assert len(rm.portfolio_returns({"A": 0.5, "B": 0.5}, bars)) == 1

    def test_is_empty_for_an_empty_book(self):
        assert rm.portfolio_returns({}, {}).empty
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/analytics/test_risk_metrics.py
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/analytics/risk_metrics.py`. Follow the formulas above
exactly. The module-level guard:

```python
#: Fewer overlapping days than this and no distributional figure is reported.
#: 20 is one trading month -- below it the 5th percentile is one observation,
#: and one observation is an anecdote with a decimal point.
_MIN_BARS = 20
```

Every function returns `None` on an empty input, a too-short input, or a zero
denominator. None of them raises: this module is called to render a page, and a
book with one position is a normal Tuesday, not an error.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/analytics/test_risk_metrics.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/risk_metrics.py tests/analytics/test_risk_metrics.py
git commit -m "feat(analytics): portfolio risk metrics, each None rather than guessed (v85 D37)"
```

---

### Task R8-02: The correlation matrix

**Files:**
- Modify: `swingbot/core/analytics/risk_metrics.py`
- Test: `tests/analytics/test_risk_metrics.py`

**Interfaces:**
- Consumes: the same cached bars.
- Produces: `correlation_matrix(symbols, bars) -> tuple[list[str], list[list[float | None]]]`
  — labels in the given order, and a square matrix of Pearson correlations of
  daily returns. Consumed by R8-03.

**A pair with too few overlapping bars is `None`, not `0.0`.** Zero
correlation is a finding; no data is not. The `sb-matrix` primitive (R2-04)
already renders the two differently, and this is the value that drives it.

- [ ] **Step 1: Write the failing test**

```python
class TestCorrelationMatrix:
    def test_the_diagonal_is_one(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10), "B": _frame([50, 55, 52, 60] * 10)}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][0] == pytest.approx(1.0)
        assert m[1][1] == pytest.approx(1.0)

    def test_is_symmetric(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10), "B": _frame([50, 52, 55, 53] * 10)}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] == pytest.approx(m[1][0])

    def test_two_symbols_that_move_together_correlate_near_one(self):
        closes = [100, 110, 105, 120] * 10
        bars = {"A": _frame(closes), "B": _frame([c * 2 for c in closes])}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] == pytest.approx(1.0, abs=0.01)

    def test_a_pair_with_too_little_overlap_is_none_not_zero(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10), "B": _frame([50, 55])}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] is None

    def test_a_symbol_with_no_bars_yields_a_row_of_nones_and_keeps_its_label(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10)}
        labels, m = rm.correlation_matrix(["A", "GHOST"], bars)
        assert labels == ["A", "GHOST"]
        assert m[1][0] is None

    def test_labels_keep_the_order_they_were_given(self):
        bars = {"B": _frame([100, 110] * 20), "A": _frame([100, 105] * 20)}
        labels, _ = rm.correlation_matrix(["B", "A"], bars)
        assert labels == ["B", "A"]

    def test_an_empty_book_yields_empty_labels_and_matrix(self):
        assert rm.correlation_matrix([], {}) == ([], [])
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/analytics/test_risk_metrics.py
```

Expected: FAIL — `correlation_matrix` is undefined.

- [ ] **Step 3: Implement it**

Pairwise Pearson correlation of daily returns over each pair's own overlapping
index, gated by `_MIN_BARS`. Do not build one aligned frame and correlate it
wholesale: a single short symbol would truncate every pair in the book.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/analytics/test_risk_metrics.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/risk_metrics.py tests/analytics/test_risk_metrics.py
git commit -m "feat(analytics): pairwise correlation matrix over the open book (v85 D38)"
```

---

### Task R8-03: Serve the metrics and the matrix from `GET /risk`

**Files:**
- Modify: `swingbot/admin/api_v1/risk.py:101-148`
- Test: `tests/admin/test_api_risk.py`

**Interfaces:**
- Consumes: R8-01 and R8-02, and `_collect_portfolio_state` /`_positions` which
  the endpoint already uses.
- Produces: two new blocks on the existing payload —

```json
"metrics": {
  "var_95": {"value": 0.031, "n": 118},
  "expected_shortfall_95": {"value": 0.047, "n": 118},
  "annualised_vol": {"value": 0.148, "n": 118},
  "beta_spy": {"value": 1.12, "n": 118},
  "sharpe_r": {"value": 0.96, "n": 782},
  "max_drawdown_r": {"value": 8.4, "n": 782},
  "as_of": "2026-09-10"
},
"correlation": {"labels": ["AAPL", "MSFT"], "values": [[1.0, 0.68], [0.68, 1.0]]}
```

Consumed by R8-04 and R8-05.

**Every metric is a `{value, n}` pair, never a bare number.** That shape is what
makes it impossible for the frontend to render a figure without its sample size
— the rule from D23 enforced by the payload rather than by discipline.

**Nothing already on this payload changes.** `heat`, `positions`,
`sector_heat`, `clusters`, `throttle`, `killswitch` and `scan_health` are
untouched: the gauge and the risk budget are compositions of `heat`, which
already exists (index finding 13).

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_risk.py`:

```python
def test_every_metric_carries_its_own_sample_size(client, open_book):
    open_book(["AAPL", "MSFT"])
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    for key in ("var_95", "expected_shortfall_95", "annualised_vol",
                "beta_spy", "sharpe_r", "max_drawdown_r"):
        assert set(metrics[key]) == {"value", "n"}


def test_a_metric_that_cannot_be_computed_is_null_not_zero(client, open_book):
    open_book(["AAPL"], bars=3)
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["var_95"]["value"] is None
    assert metrics["var_95"]["n"] is not None


def test_distributional_and_trade_metrics_report_different_samples(client, open_book):
    open_book(["AAPL", "MSFT"], bars=120, closed_trades=40)
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["var_95"]["n"] != metrics["sharpe_r"]["n"]


def test_an_empty_book_returns_metrics_of_nulls_rather_than_omitting_them(client, open_book):
    open_book([])
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["var_95"]["value"] is None
    assert metrics["beta_spy"]["value"] is None


def test_the_correlation_labels_match_the_open_positions(client, open_book):
    open_book(["AAPL", "MSFT"])
    corr = client.get("/api/v1/risk").get_json()["correlation"]
    assert corr["labels"] == ["AAPL", "MSFT"]
    assert len(corr["values"]) == 2


def test_the_existing_payload_blocks_are_untouched(client, open_book):
    open_book(["AAPL"])
    body = client.get("/api/v1/risk").get_json()
    for key in ("heat", "positions", "sector_heat", "clusters", "throttle",
                "killswitch", "scan_health"):
        assert key in body


def test_a_market_data_failure_degrades_the_metrics_not_the_page(client, open_book, monkeypatch):
    open_book(["AAPL"])
    monkeypatch.setattr(
        "swingbot.admin.api_v1.risk.get_daily_data_batch",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network")),
    )
    body = client.get("/api/v1/risk")
    assert body.status_code == 200
    assert body.get_json()["metrics"]["var_95"]["value"] is None
    assert body.get_json()["heat"] is not None
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_risk.py
```

Expected: FAIL — no `metrics` key.

- [ ] **Step 3: Wire the endpoint**

Fetch bars once for the open symbols plus `SPY`, compute both blocks, and add
them to the existing `jsonify`. Wrap the whole market-data section in a
`try/except` that degrades to a metrics block of nulls — **the heat, killswitch
and scan-health blocks must survive a market-data failure**, because the
killswitch is a live control and a page that fails to render it is worse than
one with empty metrics.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_risk.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/risk.py tests/admin/test_api_risk.py
git commit -m "feat(api): risk metrics and correlation on GET /risk (v85 D37/D38)"
```

---

### Task R8-04: The metric tiles

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Modify: `frontend/src/app/stores/risk.store.ts`
- Test: `frontend/src/app/workspaces/risk/risk.spec.ts`

**Interfaces:**
- Consumes: R8-03's `metrics` block, `sb-stat-tile` (R2-01).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```typescript
it('renders the six metrics as stat tiles', () => {
  const labels = tileLabels();
  expect(labels).toEqual([
    'VaR 95%', 'Expected shortfall', 'Annualised vol', 'Beta vs SPY',
    'Sharpe (R)', 'Max drawdown (R)',
  ]);
});

it('renders each metric with the sample it was computed from', () => {
  const tile = tile('Beta vs SPY', { beta_spy: { value: 1.12, n: 118 } });
  expect(tile.querySelector('.sample')!.textContent).toContain('N=118');
});

it('de-emphasises a metric computed from a thin sample', () => {
  const tile = tile('Sharpe (R)', { sharpe_r: { value: 0.96, n: 7 } });
  expect(tile.classList).toContain('thin');
});

it('renders an uncomputable metric as no-value, never as zero', () => {
  const tile = tile('VaR 95%', { var_95: { value: null, n: 3 } });
  expect(tile.querySelector('.value')!.textContent!.trim()).toBe('—');
});

it('labels Sharpe as an R measure so it is not read as annualised', () => {
  expect(tileLabels()).toContain('Sharpe (R)');
});

it('does not reuse one sample size across both metric families', () => {
  const el = render({ var_95: { value: 0.03, n: 118 }, sharpe_r: { value: 0.9, n: 782 } });
  expect(tile('VaR 95%').querySelector('.sample')!.textContent).toContain('118');
  expect(tile('Sharpe (R)').querySelector('.sample')!.textContent).toContain('782');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/risk/risk.spec.ts
```

Expected: FAIL — no stat tiles.

- [ ] **Step 3: Render the tiles**

Add the `metrics` block to the store's state and render six `sb-stat-tile`s in
a `repeat(auto-fit, minmax(140px, 1fr))` grid. Format each value in the
component — percentages for the first three, a plain ratio for beta and Sharpe,
an R figure for drawdown. Pass `sample` from each metric's own `n`.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/risk/risk.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/risk frontend/src/app/stores/risk.store.ts
git commit -m "feat(risk): six metric tiles, each carrying its own N (v85 D37)"
```

---

### Task R8-05: The gauge, the risk budget and the matrix

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Test: `frontend/src/app/workspaces/risk/risk.spec.ts`

**Interfaces:**
- Consumes: `sb-gauge` (R2-03), `sb-matrix` (R2-04), the existing `heat`,
  `clusters` and new `correlation` blocks.
- Produces: nothing new.

**The gauge is heat utilisation and nothing else** (spec D36). The value is
already on the payload, already unclamped, and the API comments on why. Do not
clamp it on the way in, and do not invent a composite score.

**Both correlation panels stay** (spec D38). The matrix is new; the existing
"Correlated clusters" list is untouched and sits beside it. The clusters are
what actually throttle position size, so they keep a readable list.

- [ ] **Step 1: Write the failing test**

```typescript
it('drives the gauge from heat utilisation', () => {
  const el = render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52 } }).nativeElement as HTMLElement;
  expect(el.querySelector('sb-gauge .readout')!.textContent).toContain('52');
});

it('shows a utilisation past the cap truthfully rather than pinned at 100', () => {
  const el = render({ heat: { open_pct: 7.8, cap_pct: 6, utilisation_pct: 130 } }).nativeElement as HTMLElement;
  expect(el.querySelector('sb-gauge .readout')!.textContent).toContain('130');
  expect(el.querySelector('sb-gauge .readout')!.textContent).toContain('over limit');
});

it('breaks the risk budget into cap, used and remaining', () => {
  const el = render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52 } }).nativeElement as HTMLElement;
  const budget = el.querySelector('.risk-budget')!;
  expect(budget.textContent).toContain('6');
  expect(budget.textContent).toContain('3.1');
  expect(budget.textContent).toContain('2.9');
});

it('reports no remaining budget rather than a negative one when over the cap', () => {
  const el = render({ heat: { open_pct: 7.8, cap_pct: 6, utilisation_pct: 130 } }).nativeElement as HTMLElement;
  expect(el.querySelector('.risk-budget .remaining')!.textContent).toContain('0');
  expect(el.querySelector('.risk-budget')!.textContent).toContain('over');
});

it('renders the correlation matrix with the clusters outlined on it', () => {
  const el = render({
    correlation: { labels: ['AAPL', 'MSFT'], values: [[1, 0.68], [0.68, 1]] },
    clusters: [['AAPL', 'MSFT']],
  }).nativeElement as HTMLElement;
  expect(el.querySelector('sb-matrix .clustered')).not.toBeNull();
});

it('keeps the cluster list beside the matrix', () => {
  const el = render({ clusters: [['AAPL', 'MSFT']] }).nativeElement as HTMLElement;
  expect(el.querySelector('sb-panel[heading="Correlated clusters"]')).not.toBeNull();
});

it('keeps the killswitch panel', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('sb-panel[heading="Killswitch"]')).not.toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/risk/risk.spec.ts
```

Expected: FAIL on the new assertions.

- [ ] **Step 3: Compose the panels**

Gauge and risk budget in the top row beside the metric tiles; matrix and the
existing cluster panel side by side beneath. Remaining budget is
`max(cap - used, 0)` with an explicit "over" note when the subtraction would
have gone negative — a negative remaining budget is a arithmetic result, not a
readable one.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/risk/risk.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/risk
git commit -m "feat(risk): heat gauge, risk budget and correlation matrix (v85 D36/D38)"
```

---

### Task R8-06: Control bar, freshness, and the narrow-width pass

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Test: `frontend/src/app/workspaces/risk/risk.spec.ts`

**Interfaces:**
- Consumes: `sb-control-bar` (R2-02), `sb-freshness` (R2-06).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```typescript
it('marks the metrics panel with the bar date they were computed from', () => {
  const el = render({ metrics: { as_of: '2026-09-10' } }).nativeElement as HTMLElement;
  expect(el.querySelector('.metrics sb-freshness')).not.toBeNull();
});

it('does not claim the scan-health panel is as fresh as the metrics', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelectorAll('sb-freshness').length).toBeGreaterThan(1);
});

it('renders no in-page heading', () => {
  expect((render().nativeElement as HTMLElement).querySelector('h1')).toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/risk/risk.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Apply the panel language**

Wrap the page's controls in `sb-control-bar`; give each fetching panel its own
`sb-freshness`; remove the in-page heading (the top bar owns it, R1-11); make
every metric grid `repeat(auto-fit, minmax(140px, 1fr))`.

- [ ] **Step 4: Run the spec and the guard**

```bash
cd frontend && npx ng test --include src/app/workspaces/risk/risk.spec.ts
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: the risk spec PASSES; the guard no longer names `risk/risk.ts`.

- [ ] **Step 5: Screenshot at both widths**

Screenshot `/risk` at 1440px and 390px. Confirm at 390px: the correlation
matrix scrolls inside its own container, the gauge does not overflow, the
tiles reflow to two columns, and no panel is hidden.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/risk
git commit -m "style(risk): control bar, per-panel freshness, narrow-width pass"
```

---

# Phase 2 — Wave 2 verification and release

### Task R8-07: Wave 2 — full suite, screenshots, release

**Files:**
- Modify: `VERSION.json`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: every task in Parts 6–8.
- Produces: a released `ui` minor and `bot` patch. Wave 3 branches from it.

**This is the only full-suite run in wave 2.**

- [ ] **Step 1: Run the frontend suite**

```bash
cd frontend && npx ng test
```

Expected: PASS, except `workspace-consistency.spec.ts`, which must now name
strictly fewer files than it did at R5-07. Record the remaining list.

- [ ] **Step 2: Run the backend suite**

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed` and `0 xfailed`. Dispatch the `test-runner` subagent.

- [ ] **Step 3: Check the new endpoints against the real book**

With the admin running against real data, fetch `/api/v1/risk` and
`/api/v1/watchlist/tickers` and read the output. Confirm: no metric is `0.0`
where it should be `null`, every `n` is plausible, and no watchlist row has a
price without an `as_of`.

- [ ] **Step 4: Screenshot Trades, Watchlist and Risk at both widths**

1440px and 390px each. Confirm no horizontal page scroll anywhere.

- [ ] **Step 5: Bump the version**

Read `VERSION.json` **now**. Bump `ui` one minor and `bot` one patch — wave 2
adds endpoints and a computation module to the bot package.

- [ ] **Step 6: Commit and merge**

```bash
git add VERSION.json CHANGELOG.md
git commit -m "release(ui,bot): <resolved versions> -- Trades, Watchlist and Risk redesign"
```

Before merging, check for other live sessions on this tree (`git worktree list`
and the session cursor). If another session is active on a shared branch,
**stop and ask**.

- [ ] **Step 7: Record the wave in the progress ledger**

Append to `.superpowers/sdd/progress.md`: tasks completed, full-suite figures,
the endpoint spot-check outcome, and the remaining consistency worklist.
