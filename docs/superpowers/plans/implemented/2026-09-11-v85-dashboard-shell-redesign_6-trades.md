# v85 Part 6 — Trades (wave 2)

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R6-01 is Group W2-BE** — `swingbot/admin/api_v1/trades.py` only, parallel with
the Watchlist and Risk backend strands. **R6-02 … R6-05 are Group W2-UI**,
sequential among themselves, parallel with the other two workspaces.

**Trades is the most mature workspace in the app.** It already has URL-driven
filters, column preferences, sorting, pagination and export. This part adds
three things it lacks — a promoted chip lane, a date range, and an honest count
footer — and changes nothing else. A task here that finds itself rebuilding the
table has misread the spec (D32).

---

### Task R6-01: `from` and `to` on `GET /trades`

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py:766-800`
- Test: `tests/admin/test_api_trades.py`

**Interfaces:**
- Consumes: `parse_collection_params`, `FILTERS`, `build_rows` — all already in
  that module.
- Produces: two new accepted query parameters, `opened_from` and `opened_to`,
  both `YYYY-MM-DD`, both inclusive, filtering on each row's `opened_at`.
  Consumed by R6-02.

**Why inclusive at both ends, and why on `opened_at`.** A date picker that
excludes its end date is the single most common off-by-one in a trade log —
"Apr 1 to Apr 28" must include Apr 28. And the range filters on when a position
was *opened*, not closed: the Trades page is a log of decisions, and a decision
belongs to the day it was made.

**Do not add these to `_CASELESS_FILTERS` or `_FILTER_KEYS`.** Those paths do
equality. A range needs its own branch, before the generic `else`.

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_trades.py`:

```python
def test_opened_from_is_inclusive(client, seed_trades):
    seed_trades([
        {"ticker": "AAPL", "opened_at": "2026-04-01T14:00:00Z"},
        {"ticker": "MSFT", "opened_at": "2026-03-31T14:00:00Z"},
    ])
    body = client.get("/api/v1/trades?opened_from=2026-04-01").get_json()
    assert [r["ticker"] for r in body["items"]] == ["AAPL"]


def test_opened_to_is_inclusive(client, seed_trades):
    seed_trades([
        {"ticker": "AAPL", "opened_at": "2026-04-28T23:30:00Z"},
        {"ticker": "MSFT", "opened_at": "2026-04-29T00:30:00Z"},
    ])
    body = client.get("/api/v1/trades?opened_to=2026-04-28").get_json()
    assert [r["ticker"] for r in body["items"]] == ["AAPL"]


def test_range_narrows_the_total_not_just_the_page(client, seed_trades):
    seed_trades([{"ticker": f"T{i}", "opened_at": f"2026-04-{i:02d}T14:00:00Z"}
                 for i in range(1, 21)])
    body = client.get("/api/v1/trades?opened_from=2026-04-05&opened_to=2026-04-09").get_json()
    assert body["total"] == 5


def test_an_inverted_range_matches_nothing_rather_than_erroring(client, seed_trades):
    seed_trades([{"ticker": "AAPL", "opened_at": "2026-04-10T14:00:00Z"}])
    resp = client.get("/api/v1/trades?opened_from=2026-04-20&opened_to=2026-04-10")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_a_malformed_date_is_a_bad_request(client, seed_trades):
    seed_trades([{"ticker": "AAPL", "opened_at": "2026-04-10T14:00:00Z"}])
    assert client.get("/api/v1/trades?opened_from=last-tuesday").status_code == 400


def test_an_open_ended_range_works_from_either_side(client, seed_trades):
    seed_trades([
        {"ticker": "AAPL", "opened_at": "2026-04-01T14:00:00Z"},
        {"ticker": "MSFT", "opened_at": "2026-05-01T14:00:00Z"},
    ])
    assert client.get("/api/v1/trades?opened_from=2026-04-15").get_json()["total"] == 1
    assert client.get("/api/v1/trades?opened_to=2026-04-15").get_json()["total"] == 1


def test_a_row_with_no_opened_at_is_excluded_by_any_range(client, seed_trades):
    seed_trades([{"ticker": "AAPL", "opened_at": None}])
    assert client.get("/api/v1/trades?opened_from=2026-01-01").get_json()["total"] == 0
```

If `seed_trades` does not exist as a fixture in that file, use whatever the
existing tests there use to install rows; do not add a second seeding style.

- [ ] **Step 2: Run them to make sure they fail**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_trades.py
```

Expected: FAIL — the parameters are rejected by the `FILTERS` allowlist, so the
counts come back unfiltered.

- [ ] **Step 3: Implement the range filter**

In `swingbot/admin/api_v1/trades.py`, add `"opened_from"` and `"opened_to"` to
`FILTERS`, and add a branch to the filter loop **before** the generic `else`:

```python
_RANGE_FILTERS = {"opened_from", "opened_to"}


def _as_date(value: str) -> date:
    """Parse a YYYY-MM-DD filter bound, or 400.

    A malformed bound is a malformed request -- unlike an unknown *value* for
    status or outcome, which the collection convention answers with an empty
    set. "last-tuesday" is not a request for no trades; it is a mistake.
    """
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        abort(400, description=f"Not a YYYY-MM-DD date: {value!r}")


def _row_opened_date(row: dict) -> date | None:
    raw = row.get("opened_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        return None
```

and in the loop:

```python
        elif key in _RANGE_FILTERS:
            bound = _as_date(str(value))
            if key == "opened_from":
                rows = [r for r in rows
                        if (d := _row_opened_date(r)) is not None and d >= bound]
            else:
                rows = [r for r in rows
                        if (d := _row_opened_date(r)) is not None and d <= bound]
```

A row with no `opened_at` is excluded by any bound rather than kept: it cannot
be shown to satisfy the range, and silently keeping it would make the count
disagree with the rows.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_trades.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_api_trades.py
git commit -m "feat(api): inclusive opened_from/opened_to range on GET /trades (v85 D32)"
```

---

### Task R6-02: Bind the range through the client and the store

**Files:**
- Modify: `frontend/src/app/api/api-client.ts`
- Modify: `frontend/src/app/stores/trades.store.ts`
- Test: `frontend/src/app/stores/trades.store.spec.ts`

**Interfaces:**
- Consumes: R6-01's two parameters.
- Produces: `openedFrom` and `openedTo` on the store's query slice, both
  `string | null`, both projected from the URL. Consumed by R6-03 and R6-04.

**The range lives in the URL, like every other filter here.** The store's query
slice is a projection of the route, not a fourth copy of the truth — that is
what makes a filtered view survive a reload and stay pasteable, and it is the
reason `app.routes.ts` comments on it at length. A range held only in the store
breaks the back button on a filter.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/stores/trades.store.spec.ts`:

```typescript
it('sends the range to the API when both bounds are set', async () => {
  const store = setup();
  store.setQuery({ openedFrom: '2026-04-01', openedTo: '2026-04-28' });
  await flush();
  expect(lastUrl()).toContain('opened_from=2026-04-01');
  expect(lastUrl()).toContain('opened_to=2026-04-28');
});

it('omits a bound that is null rather than sending an empty parameter', async () => {
  const store = setup();
  store.setQuery({ openedFrom: '2026-04-01', openedTo: null });
  await flush();
  expect(lastUrl()).toContain('opened_from=2026-04-01');
  expect(lastUrl()).not.toContain('opened_to');
});

it('counts each set bound towards the active filter count', () => {
  const store = setup();
  store.setQuery({ openedFrom: '2026-04-01', openedTo: '2026-04-28' });
  expect(store.activeFilterCount()).toBe(1);
});

it('resets to page 1 when the range changes', async () => {
  const store = setup();
  store.setQuery({ page: 3 });
  store.setQuery({ openedFrom: '2026-04-01' });
  await flush();
  expect(lastUrl()).toContain('page=1');
});
```

Use the spec's existing `setup`, `flush` and `lastUrl` helpers.

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/stores/trades.store.spec.ts
```

Expected: FAIL — `openedFrom` is not a query key.

- [ ] **Step 3: Add the two keys**

Add `openedFrom` and `openedTo` to the store's query type and to its URL
projection, mapping to `opened_from` / `opened_to`. A null bound drops the
parameter entirely — the existing pattern in this store for a cleared filter.
**The pair counts as one active filter**, not two: it is one control on screen,
and reporting "2" for one date picker would make Clear's count read wrong.
Follow the store's existing page-reset rule so a range change returns to page 1,
for the reason its comment already gives — a filtered page 3 that no longer
exists reads as "no results".

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/stores/trades.store.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/api-client.ts frontend/src/app/stores/trades.store.ts frontend/src/app/stores/trades.store.spec.ts
git commit -m "feat(trades): bind the opened-at range through client and store"
```

---

### Task R6-03: Promote the chip lane into the shared control bar

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts`
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`

**Interfaces:**
- Consumes: `sb-control-bar` (R2-02), the store's query slice.
- Produces: nothing new.

**Which chips, and why these.** Spec D32: the mockup's lane is asset classes,
which this bot does not have. The lane becomes
*All · Open · Closed · Pending · Win · Loss · Long · Short* — the filters
actually reached for, lifted out of the collapsible filter bar so they are one
click rather than two. **The filter bar stays** and keeps strategy, horizon,
symbol and the rest; this task moves eight controls, it does not delete a
surface.

`All` is not a ninth filter value. It is the cleared state, and pressing it
clears status, outcome and side together while leaving the others alone.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/workspaces/trades/trades.spec.ts`:

```typescript
it('renders the eight promoted chips in the control bar', () => {
  const labels = Array.from(
    (render().nativeElement as HTMLElement).querySelectorAll('sb-control-bar [filters] .chip'),
  ).map((c) => c.textContent!.trim());
  expect(labels).toEqual(['All', 'Open', 'Closed', 'Pending', 'Win', 'Loss', 'Long', 'Short']);
});

it('marks All active when nothing in the lane is filtered', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('.chip')!.classList).toContain('active');
});

it('sets the status filter when Open is pressed', () => {
  const f = render();
  chip(f, 'Open').click();
  expect(f.componentInstance.store.query().status).toBe('open');
});

it('clears status, outcome and side when All is pressed, and nothing else', () => {
  const f = render();
  f.componentInstance.store.setQuery({ status: 'open', strategy: 'RSI' });
  chip(f, 'All').click();
  expect(f.componentInstance.store.query().status).toBeNull();
  expect(f.componentInstance.store.query().outcome).toBeNull();
  expect(f.componentInstance.store.query().side).toBeNull();
  expect(f.componentInstance.store.query().strategy).toBe('RSI');
});

it('keeps the filter bar for the filters the lane does not carry', () => {
  expect((render().nativeElement as HTMLElement).querySelector('sb-filter-bar')).not.toBeNull();
});
```

Write the `chip(fixture, label)` helper in this spec if it does not exist: find
the `.chip` whose `textContent` trims to `label`.

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/trades/trades.spec.ts
```

Expected: FAIL — no `sb-control-bar` in the template.

- [ ] **Step 3: Add the lane**

Wrap the existing header controls in `sb-control-bar`. The chips go in the
`filters` slot; the export button and column picker go in the `scope` slot.
Each chip writes a single query key through the store's existing `setQuery`,
which already projects to the URL — no new state.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/trades/trades.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades
git commit -m "feat(trades): promote status/outcome/side chips into the control bar (v85 D32)"
```

---

### Task R6-04: The date-range picker

**Files:**
- Create: `frontend/src/app/ui/date-range.ts`
- Create: `frontend/src/app/ui/date-range.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.ts`

**Interfaces:**
- Consumes: R6-02's `openedFrom` / `openedTo`.
- Produces: `DateRange` component (selector `sb-date-range`), inputs `from`
  (`string | null`), `to` (`string | null`); output `changed` emitting
  `{ from: string | null; to: string | null }`. Reusable by R9-04.

**Two native date inputs, not a calendar widget.** The plan forbids a
third-party dependency, and a hand-rolled calendar popover is a week of
accessibility work to reproduce something the browser already does correctly on
every platform including mobile.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/date-range.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { DateRange } from './date-range';

function setup(from: string | null = null, to: string | null = null) {
  const f = TestBed.createComponent(DateRange);
  f.componentRef.setInput('from', from);
  f.componentRef.setInput('to', to);
  f.detectChanges();
  return f;
}

function input(f: ReturnType<typeof setup>, which: 'from' | 'to'): HTMLInputElement {
  return (f.nativeElement as HTMLElement).querySelector(`input.${which}`)!;
}

describe('DateRange (v85 D32)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders both bounds as native date inputs', () => {
    const f = setup();
    expect(input(f, 'from').type).toBe('date');
    expect(input(f, 'to').type).toBe('date');
  });

  it('emits both bounds when one changes', () => {
    const f = setup('2026-04-01', null);
    let emitted: unknown = null;
    f.componentInstance.changed.subscribe((v: unknown) => (emitted = v));
    const el = input(f, 'to');
    el.value = '2026-04-28';
    el.dispatchEvent(new Event('change'));
    expect(emitted).toEqual({ from: '2026-04-01', to: '2026-04-28' });
  });

  it('emits null for a cleared bound rather than an empty string', () => {
    const f = setup('2026-04-01', '2026-04-28');
    let emitted: { from: string | null; to: string | null } | null = null;
    f.componentInstance.changed.subscribe((v: { from: string | null; to: string | null }) => (emitted = v));
    const el = input(f, 'from');
    el.value = '';
    el.dispatchEvent(new Event('change'));
    expect(emitted!.from).toBeNull();
  });

  it('stops the end bound from preceding the start bound', () => {
    const f = setup('2026-04-20', null);
    expect(input(f, 'to').min).toBe('2026-04-20');
  });

  it('labels both inputs', () => {
    const f = setup();
    expect(input(f, 'from').getAttribute('aria-label')).toBe('From date');
    expect(input(f, 'to').getAttribute('aria-label')).toBe('To date');
  });
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/ui/date-range.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component and mount it**

Create `frontend/src/app/ui/date-range.ts` with two `<input type="date">`
elements carrying classes `from` and `to`, `aria-label`s as asserted, and a
`min` on the end bound bound to `from()`. Emit `{ from, to }` on every change,
mapping `''` to `null`. Mount it in the Trades control bar's `scope` slot,
wiring `changed` to `store.setQuery`.

- [ ] **Step 4: Run both specs and confirm they pass**

```bash
cd frontend && npx ng test --include src/app/ui/date-range.spec.ts
cd frontend && npx ng test --include src/app/workspaces/trades/trades.spec.ts
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/date-range.ts frontend/src/app/ui/date-range.spec.ts frontend/src/app/workspaces/trades
git commit -m "feat(ui): sb-date-range, and the Trades opened-at range (v85 D32)"
```

---

### Task R6-05: The count footer, and the narrow-width pass

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts`
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`

**Interfaces:**
- Consumes: the store's `total`, `page` and `perPage`.
- Produces: nothing new.

**The footer is a measured answer, not a decoration.** "Showing 1–12 of 142"
tells you the filter narrowed 142 rows to a page of 12. An empty filtered set
must say so as an empty filtered set — "0 of 0" for a filter that matched
nothing is a *measured zero*, and this repo distinguishes that from "no trades
yet" everywhere else.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/workspaces/trades/trades.spec.ts`:

```typescript
it('reports the visible slice and the filtered total', () => {
  const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
  expect(el.querySelector('.count')!.textContent).toContain('Showing 1–12 of 142');
});

it('reports the last page without overrunning the total', () => {
  const el = render({ total: 142, page: 12, perPage: 12 }).nativeElement as HTMLElement;
  expect(el.querySelector('.count')!.textContent).toContain('Showing 133–142 of 142');
});

it('distinguishes a filter that matched nothing from an empty log', () => {
  const el = render({ total: 0, page: 1, perPage: 12, activeFilterCount: 2 }).nativeElement as HTMLElement;
  expect(el.querySelector('.count')!.textContent).toContain('No trades match');
});

it('says the log is empty when nothing is filtered and there is nothing', () => {
  const el = render({ total: 0, page: 1, perPage: 12, activeFilterCount: 0 }).nativeElement as HTMLElement;
  expect(el.querySelector('.count')!.textContent).toContain('No trades yet');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/trades/trades.spec.ts
```

Expected: FAIL — no `.count` element.

- [ ] **Step 3: Render the footer**

Add the footer beside the existing pagination, computing the slice bounds from
`page`, `perPage` and `total` — clamping the upper bound to `total` so the last
page does not claim rows it did not show.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/trades/trades.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Screenshot at both widths**

Screenshot `/trades` at 1440px and 390px. Confirm: the chip lane wraps rather
than scrolling the page, both date inputs are reachable at 390px, the table
scrolls inside its own container, and the footer stays legible.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/trades
git commit -m "feat(trades): showing-X-of-N footer that distinguishes measured zero"
```
