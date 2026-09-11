# v85 Part 9 — Analytics (wave 3)

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R9-01 … R9-02 are Group W3-BE**, sequential among themselves, parallel with
the Calendar and Versions backend strands. **R9-03 … R9-06 are Group W3-UI.**

---

## What changes, and what emphatically does not

Spec D39: **sheet 2 replaces the Performance tab.** The other four tabs —
Strategies, Calibration, Tuning, Plans — are restyled and otherwise left alone.
Analytics is 1,696 lines across five tabs and ~25 panels; a task here that
finds itself rewriting Calibration or Tuning has misread the spec.

Spec D41: **every displaced panel stays on the Performance tab**, beneath the
new composition, in a collapsible Breakdowns band. Nothing is deleted. The
first screen answers "how are we doing"; the band below answers "why".

---

### Task R9-01: The equity curve and drawdown series

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py`
- Test: `tests/admin/test_api_analytics.py`

**Interfaces:**
- Consumes: the closed-trade set the module's other endpoints already read.
- Produces: `GET /analytics/equity-curve`, returning

```json
{"points": [{"date": "2026-04-01", "cum_r": 3.4, "drawdown_r": 0.0}],
 "n": 782, "as_of": "2026-09-10"}
```

Consumed by R9-04.

**Ordered by close date, one point per closed trade, cumulative in R.** Not
by calendar day: a day with no closes is not a flat day on an R curve, it is a
day with no observation, and interpolating one would invent a data point. The
x-axis is the sequence of trades, dated.

`drawdown_r` at each point is `running_max(cum_r) - cum_r`, a non-negative
figure — that is what the Equity | Drawdown toggle switches between, from one
fetch rather than two.

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_analytics.py`:

```python
def test_the_curve_accumulates_r_in_close_order(client, closed_trades):
    closed_trades([
        {"closed_at": "2026-04-03T16:00:00Z", "r_multiple": 2.0},
        {"closed_at": "2026-04-01T16:00:00Z", "r_multiple": 1.0},
    ])
    pts = client.get("/api/v1/analytics/equity-curve").get_json()["points"]
    assert [p["cum_r"] for p in pts] == [1.0, 3.0]


def test_drawdown_is_measured_from_the_running_peak(client, closed_trades):
    closed_trades([
        {"closed_at": "2026-04-01T16:00:00Z", "r_multiple": 3.0},
        {"closed_at": "2026-04-02T16:00:00Z", "r_multiple": -1.0},
    ])
    pts = client.get("/api/v1/analytics/equity-curve").get_json()["points"]
    assert pts[0]["drawdown_r"] == 0.0
    assert pts[1]["drawdown_r"] == 1.0


def test_drawdown_is_never_negative(client, closed_trades):
    closed_trades([{"closed_at": f"2026-04-0{i}T16:00:00Z", "r_multiple": 1.0}
                   for i in range(1, 5)])
    pts = client.get("/api/v1/analytics/equity-curve").get_json()["points"]
    assert all(p["drawdown_r"] >= 0 for p in pts)


def test_the_sample_size_is_reported_beside_the_curve(client, closed_trades):
    closed_trades([{"closed_at": "2026-04-01T16:00:00Z", "r_multiple": 1.0}])
    assert client.get("/api/v1/analytics/equity-curve").get_json()["n"] == 1


def test_an_empty_book_returns_no_points_rather_than_a_flat_line(client, closed_trades):
    closed_trades([])
    body = client.get("/api/v1/analytics/equity-curve").get_json()
    assert body["points"] == []
    assert body["n"] == 0
    assert body["as_of"] is None


def test_a_trade_without_an_r_multiple_is_skipped_not_counted_as_zero(client, closed_trades):
    closed_trades([
        {"closed_at": "2026-04-01T16:00:00Z", "r_multiple": 1.0},
        {"closed_at": "2026-04-02T16:00:00Z", "r_multiple": None},
    ])
    body = client.get("/api/v1/analytics/equity-curve").get_json()
    assert body["n"] == 1
    assert [p["cum_r"] for p in body["points"]] == [1.0]


def test_the_strategy_filter_narrows_the_curve(client, closed_trades):
    closed_trades([
        {"closed_at": "2026-04-01T16:00:00Z", "r_multiple": 1.0, "strategy": "RSI"},
        {"closed_at": "2026-04-02T16:00:00Z", "r_multiple": 5.0, "strategy": "Fib"},
    ])
    body = client.get("/api/v1/analytics/equity-curve?strategy=RSI").get_json()
    assert body["n"] == 1
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_analytics.py
```

Expected: FAIL — 404 on the route.

- [ ] **Step 3: Add the endpoint**

Add `@api_v1.route("/analytics/equity-curve", methods=["GET"])` beside the
module's existing routes, reusing whatever it already uses to load and filter
closed trades — **do not add a second loader**. Accept the same `strategy` and
range parameters the neighbouring endpoints accept, so the page's control bar
drives all of its panels through one vocabulary.

A trade with a null `r_multiple` is skipped and not counted in `n`. Treating it
as 0.0 would flatten the curve with a trade that has no measured outcome.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_analytics.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_analytics.py
git commit -m "feat(api): analytics equity curve with drawdown series (v85 D39)"
```

---

### Task R9-02: Strategy and horizon aggregates, both measures

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py`
- Test: `tests/admin/test_api_analytics.py`

**Interfaces:**
- Consumes: the registry the existing `/analytics/registry` endpoint reads, and
  `HORIZONS` from `swingbot/core/market/strategy_types.py`.
- Produces: `GET /analytics/by-dimension?dim=strategy|horizon`, returning

```json
{"rows": [{"key": "RSI", "exp_r": 0.21, "total_r": 48.3, "win_rate": 0.62,
           "profit_factor": 1.9, "max_drawdown_r": 6.2, "n": 238,
           "badge": "VALIDATED"}],
 "as_of": "2026-09-10"}
```

Consumed by R9-05.

**Both measures on every row, computed server-side.** Spec D40: the page
toggles between ExpR and total R. Sending both in one payload is what makes the
toggle instant and what stops the client deriving one from the other — total R
is not `exp_r × n` once null-R trades are skipped, and a client that assumed it
was would print a number nobody computed.

**`badge` is only populated for `dim=strategy`.** Horizons do not carry
registry badges, and inventing a null field for them would invite a column that
is always empty.

- [ ] **Step 1: Write the failing test**

```python
def test_strategy_rows_carry_both_measures(client, closed_trades):
    closed_trades([
        {"strategy": "RSI", "r_multiple": 1.0}, {"strategy": "RSI", "r_multiple": -1.0},
        {"strategy": "RSI", "r_multiple": 2.0},
    ])
    row = client.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()["rows"][0]
    assert row["exp_r"] == pytest.approx(2.0 / 3)
    assert row["total_r"] == pytest.approx(2.0)
    assert row["n"] == 3


def test_strategy_rows_carry_the_registry_badge(client, closed_trades, registry):
    registry({"RSI": "WEAK"})
    closed_trades([{"strategy": "RSI", "r_multiple": 1.0}])
    row = client.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()["rows"][0]
    assert row["badge"] == "WEAK"


def test_horizon_rows_carry_no_badge_field(client, closed_trades):
    closed_trades([{"horizon": "6w", "r_multiple": 1.0}])
    row = client.get("/api/v1/analytics/by-dimension?dim=horizon").get_json()["rows"][0]
    assert "badge" not in row


def test_horizon_rows_use_the_real_horizon_vocabulary(client, closed_trades):
    from swingbot.core.market.strategy_types import HORIZONS
    closed_trades([{"horizon": h, "r_multiple": 1.0} for h in list(HORIZONS)[:3]])
    keys = [r["key"] for r in client.get("/api/v1/analytics/by-dimension?dim=horizon").get_json()["rows"]]
    assert set(keys) <= set(HORIZONS)


def test_total_r_is_not_expectancy_times_n_when_some_trades_lack_an_r(client, closed_trades):
    closed_trades([
        {"strategy": "RSI", "r_multiple": 2.0},
        {"strategy": "RSI", "r_multiple": None},
    ])
    row = client.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()["rows"][0]
    assert row["n"] == 1
    assert row["total_r"] == pytest.approx(2.0)


def test_profit_factor_is_null_when_there_are_no_losers(client, closed_trades):
    closed_trades([{"strategy": "RSI", "r_multiple": 1.0}])
    row = client.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()["rows"][0]
    assert row["profit_factor"] is None


def test_an_unknown_dimension_is_a_bad_request(client):
    assert client.get("/api/v1/analytics/by-dimension?dim=phase-of-moon").status_code == 400


def test_a_dimension_with_no_trades_returns_no_rows_not_a_row_of_zeroes(client, closed_trades):
    closed_trades([])
    assert client.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()["rows"] == []
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_analytics.py
```

Expected: FAIL — 404 on the route.

- [ ] **Step 3: Add the endpoint**

Group the closed trades by the requested dimension and compute each row from
the functions `swingbot/core/analytics/metrics.py` already exports —
`expectancy_r` at line 220 is the ExpR, and profit factor is already there with
its null-on-no-losers rule. `max_drawdown_r` comes from R8-01. **Do not
reimplement any of them here.**

Reject an unknown `dim` with 400: unlike an unknown *filter value*, which the
collection convention answers with an empty set, an unknown dimension is a
malformed request.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_analytics.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_analytics.py
git commit -m "feat(api): by-dimension aggregates carrying ExpR and total R (v85 D40)"
```

---

### Task R9-03: The KPI row

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: `sb-stat-tile` (R2-01), the existing performance payload, R9-01's
  `n`.
- Produces: nothing new.

**The six tiles, in this order** (spec D39): Total R · R per month ·
Sharpe (R) · Max drawdown (R) · Win rate · Profit factor.

- [ ] **Step 1: Write the failing test**

```typescript
it('renders the six KPI tiles in the specified order', () => {
  expect(kpiLabels()).toEqual([
    'Total R', 'R per month', 'Sharpe (R)', 'Max drawdown (R)',
    'Win rate', 'Profit factor',
  ]);
});

it('gives every KPI the sample it was computed from', () => {
  const tiles = kpiTiles({ n: 782 });
  expect(tiles.every((t) => t.querySelector('.sample')!.textContent!.includes('782'))).toBe(true);
});

it('de-emphasises every KPI when the book is thin', () => {
  const tiles = kpiTiles({ n: 12 });
  expect(tiles.every((t) => t.classList.contains('thin'))).toBe(true);
});

it('renders a null profit factor as no-value rather than zero', () => {
  const tile = kpiTile('Profit factor', { profit_factor: null });
  expect(tile.querySelector('.value')!.textContent!.trim()).toBe('—');
});

it('labels Sharpe as an R measure', () => {
  expect(kpiLabels()).toContain('Sharpe (R)');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Render the row**

Replace the Performance tab's Record / Overall / Risk-adjusted panels' top
matter with the six-tile row. **Do not delete those panels** — R9-06 moves them
into the Breakdowns band; this task only puts the KPI row above them.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics frontend/src/app/stores/analytics.store.ts
git commit -m "feat(analytics): six-tile KPI row on the Performance tab (v85 D39)"
```

---

### Task R9-04: Equity curve, win/loss donut, control bar and freshness

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: R9-01's endpoint, `ui/line-chart.ts`, `ui/donut.ts`,
  `sb-control-bar` (R2-02), `sb-freshness` (R2-06), `sb-date-range` (R6-04).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```typescript
it('draws the equity curve from the endpoint series', () => {
  const el = render({ points: [{ date: '2026-04-01', cum_r: 1, drawdown_r: 0 }] }).nativeElement as HTMLElement;
  expect(el.querySelector('.equity sb-line-chart')).not.toBeNull();
});

it('switches the same series to drawdown without refetching', () => {
  const f = render({ points: [{ date: '2026-04-01', cum_r: 1, drawdown_r: 0.4 }] });
  const before = fetchCount();
  toggle(f, 'Drawdown').click();
  expect(fetchCount()).toBe(before);
  expect(seriesValues(f)).toEqual([0.4]);
});

it('renders the win/loss donut with both average R figures', () => {
  const el = render({ win_rate: 0.68, avg_win_r: 1.24, avg_loss_r: -0.69 }).nativeElement as HTMLElement;
  expect(el.querySelector('.winloss')!.textContent).toContain('1.24');
  expect(el.querySelector('.winloss')!.textContent).toContain('-0.69');
});

it('shows an empty curve as measured-empty rather than a flat line', () => {
  const el = render({ points: [] }).nativeElement as HTMLElement;
  expect(el.querySelector('.equity sb-line-chart')).toBeNull();
  expect(el.querySelector('.equity')!.textContent).toContain('No closed trades');
});

it('puts the range and strategy pickers in the control bar', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('sb-control-bar sb-date-range')).not.toBeNull();
  expect(el.querySelector('sb-control-bar select.strategy')).not.toBeNull();
});

it('marks the curve panel with its own data age', () => {
  const el = render({ as_of: '2026-09-10' }).nativeElement as HTMLElement;
  expect(el.querySelector('.equity sb-freshness')).not.toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build the panels**

The Equity | Drawdown control is an `sb-segmented` over the two fields of the
**same** fetched points — one request, two views. The currency selector sheet 2
shows is dropped: this book reports in R and one account currency, and a
currency picker with one option is a control that does nothing.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics frontend/src/app/stores/analytics.store.ts
git commit -m "feat(analytics): equity curve with drawdown toggle, win/loss donut (v85 D39)"
```

---

### Task R9-05: Strategy table and horizon bars, with the measure toggle

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts`
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: R9-02's endpoint, `ui/magnitude.ts`, `sb-segmented`,
  `PreferencesStore`.
- Produces: nothing new.

**The toggle is the point of this task** (spec D40). ExpR answers "which is
better per shot"; total R answers "which made the most", and rewards whichever
strategy simply fired most often. Both are worth seeing; conflating them is the
trap ExpR exists to avoid, so the control is explicit and its position is
remembered as a preference.

- [ ] **Step 1: Write the failing test**

```typescript
it('sorts the strategy table by the active measure', () => {
  const f = render({ rows: [
    { key: 'A', exp_r: 0.1, total_r: 90, n: 900 },
    { key: 'B', exp_r: 0.5, total_r: 20, n: 40 },
  ]});
  expect(rowKeys(f)).toEqual(['B', 'A']);
  toggle(f, 'Total R').click();
  expect(rowKeys(f)).toEqual(['A', 'B']);
});

it('renders the registry badge as a rail beside each strategy', () => {
  const f = render({ rows: [{ key: 'RSI', exp_r: 0.2, total_r: 10, n: 238, badge: 'WEAK' }] });
  const row = firstRow(f);
  expect(row.classList).toContain('badge-weak');
  expect(row.textContent).toContain('WEAK');
});

it('de-emphasises a strategy row computed from a thin sample', () => {
  const f = render({ rows: [{ key: 'New', exp_r: 0.9, total_r: 6, n: 7 }] });
  expect(firstRow(f).classList).toContain('thin');
});

it('renders the horizon bars diverging around zero', () => {
  const f = render({ horizons: [{ key: '2w', exp_r: -0.2, total_r: -8, n: 40 }] });
  expect(bar(f, '2w').classList).toContain('neg');
});

it('labels each horizon bar with its sample size', () => {
  const f = render({ horizons: [{ key: '2w', exp_r: 0.2, total_r: 8, n: 40 }] });
  expect(bar(f, '2w').textContent).toContain('40');
});

it('drives both panels from one toggle', () => {
  const f = render({ rows: [{ key: 'A', exp_r: 0.1, total_r: 90, n: 900 }],
                     horizons: [{ key: '2w', exp_r: 0.1, total_r: 90, n: 900 }] });
  toggle(f, 'Total R').click();
  expect(bar(f, '2w').textContent).toContain('90');
});

it('remembers the chosen measure as a preference', () => {
  const f = render();
  toggle(f, 'Total R').click();
  expect(prefs().analyticsMeasure).toBe('total_r');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build both panels and the shared toggle**

One `sb-segmented` in the control bar drives both. The badge rail is a
left border plus the badge word — colour alone would break the plan's
second-cue rule, and the badge is exactly the kind of state a reader
colour-codes by mistake.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics
git commit -m "feat(analytics): strategy table and horizon bars with an ExpR/total-R toggle (v85 D40)"
```

---

### Task R9-06: The Breakdowns band, and the other four tabs

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Modify: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`
- Modify: `frontend/src/app/workspaces/analytics/sections/strategy-contribution.ts`
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: `PreferencesStore` for the band's open/closed state.
- Produces: nothing new.

**Ten panels move, none is deleted** (spec D41): Return distribution, both
R-multiple distributions, by holding period, by month, by planned R:R, by
direction, by day of week, Streaks, Journal, by-confidence.

- [ ] **Step 1: Write the failing test**

```typescript
it('keeps every displaced panel reachable in the Breakdowns band', () => {
  const headings = bandHeadings();
  for (const h of [
    'Return distribution', 'R-multiple distribution (selected range)',
    'R-multiple distribution (all-time)', 'By holding period', 'By month',
    'By planned R:R', 'By direction', 'By day of week', 'Streaks', 'Journal',
    'By confidence level',
  ]) {
    expect(headings).toContain(h);
  }
});

it('collapses the band by default so the first screen is the summary', () => {
  expect(band().getAttribute('open')).toBeNull();
});

it('remembers that the band was opened', () => {
  const f = render();
  bandToggle(f).click();
  expect(prefs().analyticsBreakdownsOpen).toBe(true);
});

it('leaves the other four tabs in place', () => {
  expect(tabLabels()).toEqual(['Performance', 'Strategies', 'Calibration', 'Tuning', 'Plans']);
});

it('renders no in-page heading anywhere on the page', () => {
  expect((render().nativeElement as HTMLElement).querySelector('h1')).toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Move the panels into the band**

Wrap them in a `<details>`-backed band whose open state is a preference. This
is a **move**, not a rewrite: the panel bodies keep their existing bindings and
`computed`s. If a move requires changing one, stop — that is a different task.

Apply the panel language to the four untouched tabs in the same pass: `sb-panel`
everywhere, `repeat(auto-fit, minmax(140px, 1fr))` metric grids, no in-page
heading, `sb-freshness` on each fetching panel.

- [ ] **Step 4: Run the spec and the guard**

```bash
cd frontend && npx ng test --include "src/app/workspaces/analytics/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: the analytics specs PASS; the guard no longer names any analytics
file.

- [ ] **Step 5: Screenshot at both widths**

Screenshot `/analytics` on all five tabs at 1440px and 390px. Confirm the first
screen of Performance is the KPI row plus the curve without scrolling at
1440px, and that at 390px the band still opens and every panel inside it is
readable.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/analytics
git commit -m "feat(analytics): Breakdowns band keeps every displaced panel (v85 D41)"
```
