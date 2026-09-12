# v85 Part 10 — Calendar (wave 3)

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R10-01 is Group W3-BE** — `swingbot/admin/api_v1/calendar.py` only.
**R10-02 … R10-05 are Group W3-UI**, sequential among themselves.

Spec D42. The page today is three summary panels, the month grid, and a
by-weekday panel. It gains a persistent day-detail pane, a month summary strip,
and a selector for what the cells encode.

---

### Task R10-01: Day detail — contributors, detractors, and the day's shape

**Files:**
- Modify: `swingbot/admin/api_v1/calendar.py:118-160`
- Test: `tests/admin/test_api_calendar.py`

**Interfaces:**
- Consumes: the trade set `/calendar/pnl/day` already reads.
- Produces: the existing day payload, widened with

```json
{"trades": 12, "winners": 9, "losers": 3, "avg_trade_r": 0.34,
 "worst_drawdown_r": 1.8,
 "contributors": [{"ticker": "AAPL", "r": 1.82}],
 "detractors": [{"ticker": "TSLA", "r": -0.91}]}
```

Consumed by R10-03.

**Contributors and detractors are the same list, split by sign and truncated.**
Top five each, sorted by magnitude. A day with only winners has an empty
detractors list — **empty, not absent**: an empty list is the measured answer
"nothing lost money today", and dropping the key would make the client render
"no data".

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_calendar.py`:

```python
def test_the_day_payload_counts_winners_and_losers(client, day_trades):
    day_trades("2026-04-24", [{"ticker": "AAPL", "r_multiple": 1.0},
                              {"ticker": "TSLA", "r_multiple": -1.0},
                              {"ticker": "MSFT", "r_multiple": 2.0}])
    body = client.get("/api/v1/calendar/pnl/day?date=2026-04-24").get_json()
    assert body["trades"] == 3
    assert body["winners"] == 2
    assert body["losers"] == 1


def test_contributors_are_sorted_by_magnitude_and_capped_at_five(client, day_trades):
    day_trades("2026-04-24", [{"ticker": f"T{i}", "r_multiple": float(i)} for i in range(1, 9)])
    body = client.get("/api/v1/calendar/pnl/day?date=2026-04-24").get_json()
    assert [c["ticker"] for c in body["contributors"]] == ["T8", "T7", "T6", "T5", "T4"]


def test_detractors_are_the_losing_side_of_the_same_list(client, day_trades):
    day_trades("2026-04-24", [{"ticker": "AAPL", "r_multiple": 1.0},
                              {"ticker": "TSLA", "r_multiple": -2.0}])
    body = client.get("/api/v1/calendar/pnl/day?date=2026-04-24").get_json()
    assert [d["ticker"] for d in body["detractors"]] == ["TSLA"]


def test_a_day_with_only_winners_returns_an_empty_detractor_list_not_a_missing_key(client, day_trades):
    day_trades("2026-04-24", [{"ticker": "AAPL", "r_multiple": 1.0}])
    body = client.get("/api/v1/calendar/pnl/day?date=2026-04-24").get_json()
    assert body["detractors"] == []


def test_a_day_with_no_trades_is_measured_zero_not_an_error(client, day_trades):
    day_trades("2026-04-24", [])
    body = client.get("/api/v1/calendar/pnl/day?date=2026-04-24")
    assert body.status_code == 200
    assert body.get_json()["trades"] == 0
    assert body.get_json()["avg_trade_r"] is None


def test_the_average_trade_ignores_trades_with_no_r_multiple(client, day_trades):
    day_trades("2026-04-24", [{"ticker": "AAPL", "r_multiple": 2.0},
                              {"ticker": "MSFT", "r_multiple": None}])
    assert client.get("/api/v1/calendar/pnl/day?date=2026-04-24").get_json()["avg_trade_r"] == 2.0


def test_the_worst_drawdown_is_the_deepest_intraday_fall_of_the_days_curve(client, day_trades):
    day_trades("2026-04-24", [{"ticker": "A", "r_multiple": 2.0},
                              {"ticker": "B", "r_multiple": -1.5},
                              {"ticker": "C", "r_multiple": 1.0}])
    assert client.get("/api/v1/calendar/pnl/day?date=2026-04-24").get_json()["worst_drawdown_r"] == 1.5
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_calendar.py
```

Expected: FAIL — the new keys are absent.

- [ ] **Step 3: Widen the payload**

Add the fields to the existing day handler. Reuse the R-multiple accessor the
module already uses; do not add a second one. `avg_trade_r` is `None` for a day
with no measured trades — never `0.0`, which would claim a flat day.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_calendar.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/calendar.py tests/admin/test_api_calendar.py
git commit -m "feat(api): calendar day detail with contributors and detractors (v85 D42)"
```

---

### Task R10-02: The two-pane layout

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`

**Interfaces:**
- Consumes: the existing month grid and day store.
- Produces: a `selectedDate` signal on the component, the contract R10-03 fills.

- [ ] **Step 1: Write the failing test**

```typescript
it('lays the grid and the day pane side by side', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('.two-pane .grid')).not.toBeNull();
  expect(el.querySelector('.two-pane .day-pane')).not.toBeNull();
});

it('selects a day when its cell is pressed', () => {
  const f = render();
  cell(f, '2026-04-24').click();
  expect(f.componentInstance.selectedDate()).toBe('2026-04-24');
});

it('marks the selected cell for more than colour', () => {
  const f = render();
  cell(f, '2026-04-24').click();
  expect(cell(f, '2026-04-24').getAttribute('aria-pressed')).toBe('true');
});

it('selects the most recent day with trades on first load', () => {
  const f = render({ days: [{ date: '2026-04-20', trades: 2 }, { date: '2026-04-24', trades: 1 }] });
  expect(f.componentInstance.selectedDate()).toBe('2026-04-24');
});

it('selects nothing when the month has no trades', () => {
  const f = render({ days: [] });
  expect(f.componentInstance.selectedDate()).toBeNull();
});

it('stacks the pane under the grid at phone width', () => {
  expect(styleOf('.two-pane')).toContain('grid-template-columns');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build the layout**

A two-column grid that collapses to one below 900px, grid first. Selecting a
day is a signal write; the day store's own effect does the fetching — no
`subscribe()` and no fetch call in the component.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar
git commit -m "feat(calendar): two-pane grid and day detail layout (v85 D42)"
```

---

### Task R10-03: The day pane's contents

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`

**Interfaces:**
- Consumes: R10-01's payload, `sb-stat-tile` (R2-01), `sb-freshness` (R2-06).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```typescript
it('shows the day total, trade count, winners and losers', () => {
  const pane = dayPane({ total_r: 1.2, trades: 12, winners: 9, losers: 3 });
  expect(pane.textContent).toContain('12');
  expect(pane.textContent).toContain('9');
  expect(pane.textContent).toContain('3');
});

it('shows the average trade and the worst drawdown', () => {
  const pane = dayPane({ avg_trade_r: 0.34, worst_drawdown_r: 1.8 });
  expect(pane.textContent).toContain('0.34');
  expect(pane.textContent).toContain('1.8');
});

it('lists contributors and detractors separately', () => {
  const pane = dayPane({
    contributors: [{ ticker: 'AAPL', r: 1.82 }],
    detractors: [{ ticker: 'TSLA', r: -0.91 }],
  });
  expect(pane.querySelector('.contributors')!.textContent).toContain('AAPL');
  expect(pane.querySelector('.detractors')!.textContent).toContain('TSLA');
});

it('says nothing lost money rather than showing an empty detractor list', () => {
  const pane = dayPane({ contributors: [{ ticker: 'AAPL', r: 1.0 }], detractors: [] });
  expect(pane.querySelector('.detractors')!.textContent).toContain('Nothing lost');
});

it('distinguishes a day with no trades from a day not yet loaded', () => {
  expect(dayPane({ trades: 0 }).textContent).toContain('No trades closed');
  expect(dayPane(null).textContent).toContain('Select a day');
});

it('carries each derived figure with its trade count', () => {
  const pane = dayPane({ avg_trade_r: 0.34, trades: 12 });
  expect(pane.querySelector('.avg .sample')!.textContent).toContain('N=12');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build the pane**

Header (date, total in R and currency), a tile row, then the two lists. Both
lists render their empty state as a measured answer, never as a blank.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar
git commit -m "feat(calendar): day pane with contributors and detractors (v85 D42)"
```

---

### Task R10-04: The cell-metric selector and the month summary strip

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.helpers.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts`

**Interfaces:**
- Consumes: `sb-control-bar` (R2-02), `PreferencesStore`.
- Produces: `cellValue(day, metric)` in `calendar.helpers.ts`, where `metric` is
  `'r' | 'currency' | 'trades' | 'win_rate'`.

**Put the switch in the helper, not the template.** The helpers file already
has its own spec; a four-way branch inside an Angular template is the hardest
kind of logic in this app to test.

- [ ] **Step 1: Write the failing test**

Add to `calendar.helpers.spec.ts`:

```typescript
const DAY = { date: '2026-04-24', total_r: 1.2, total_ccy: 480, trades: 12, winners: 9 };

it('returns R when the metric is r', () => {
  expect(cellValue(DAY, 'r')).toEqual({ value: 1.2, text: '+1.20R', tone: 'pos' });
});

it('returns the currency total when the metric is currency', () => {
  expect(cellValue(DAY, 'currency').text).toContain('480');
});

it('returns the trade count as a neutral magnitude, never as profit', () => {
  expect(cellValue(DAY, 'trades')).toEqual({ value: 12, text: '12', tone: 'neutral' });
});

it('returns win rate as a percentage of that day trades', () => {
  expect(cellValue(DAY, 'win_rate').text).toBe('75%');
});

it('returns no value for a day with no trades rather than a zero win rate', () => {
  expect(cellValue({ date: '2026-04-25', trades: 0 }, 'win_rate')).toEqual({
    value: null, text: '', tone: 'empty',
  });
});

it('treats a day with no trades as empty for every metric', () => {
  for (const m of ['r', 'currency', 'trades', 'win_rate'] as const) {
    expect(cellValue({ date: '2026-04-25', trades: 0 }, m).tone).toBe('empty');
  }
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.helpers.spec.ts
```

Expected: FAIL — `cellValue` is undefined.

- [ ] **Step 3: Implement the helper, the selector and the strip**

Add `cellValue` to the helpers. Put the selector in the control bar, its value
in `PreferencesStore`. Add the summary strip beneath the grid: month total,
winning-day count and percentage, average day, best day, worst day — each with
the number of days it was computed from.

**The `trades` metric is toned neutral, never positive.** A busy day is not a
good day, and colouring volume with the profit ramp would say it was.

- [ ] **Step 4: Run both specs and confirm they pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.helpers.spec.ts
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.spec.ts
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar
git commit -m "feat(calendar): cell-metric selector and month summary strip (v85 D42)"
```

---

### Task R10-05: Panel language, freshness, and the narrow-width pass

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`

- [ ] **Step 1: Write the failing test**

```typescript
it('renders no in-page heading', () => {
  expect((render().nativeElement as HTMLElement).querySelector('h1')).toBeNull();
});

it('marks the grid and the day pane with their own data age', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelectorAll('sb-freshness').length).toBeGreaterThanOrEqual(2);
});

it('keeps the by-weekday panel', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('sb-panel[heading="By weekday (all history)"]')).not.toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/calendar/calendar.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Apply the panel language**

`sb-panel` everywhere, no in-page heading, `repeat(auto-fit, minmax(140px, 1fr))`
metric grids, `sb-freshness` per fetching panel.

- [ ] **Step 4: Run the spec and the guard**

```bash
cd frontend && npx ng test --include "src/app/workspaces/calendar/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: calendar specs PASS; the guard no longer names any calendar file.

- [ ] **Step 5: Screenshot at both widths**

Screenshot `/calendar` at 1440px and 390px. Confirm at 390px the day pane sits
below the grid, the grid cells stay tappable, and the summary strip wraps rather
than scrolling the page.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/calendar
git commit -m "style(calendar): panel language, per-panel freshness, narrow-width pass"
```
