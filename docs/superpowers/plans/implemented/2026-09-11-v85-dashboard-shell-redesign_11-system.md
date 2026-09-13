# v85 Part 11 — System (wave 3)

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R11-01 … R11-05 are Group W3-UI**, sequential among themselves, parallel with
Analytics, Calendar and Versions. There is no backend task in this part —
`POST /system/settings/preview` already exists (index finding 15), and R11-04's
one new preference rides the existing preferences endpoint.

---

## The shape, decided

Spec D27. **The Settings · Logs · Scan tab bar stays.** A live log tail and a
scan controller are operations, not configuration; filing them under a list of
settings categories would misplace them, and sheet 2 simply does not show that
this app has them.

Inside the **Settings** tab, the flat grouping is replaced by sheet 2's left
category rail, a settings search above it, and a sticky
"N unsaved changes · Discard Changes · Review Changes" footer.

---

### Task R11-01: The category rail

**Files:**
- Modify: `frontend/src/app/workspaces/system/settings-grouping.ts`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts`
- Test: `frontend/src/app/workspaces/system/settings-grouping.spec.ts`

**Interfaces:**
- Consumes: the settings schema `settings-grouping.ts` already derives groups
  from.
- Produces: `settingsCategories(schema)` returning
  `{ id: string; label: string; keys: string[] }[]` in display order, and an
  `activeCategory` signal on the settings tab. Consumed by R11-02 and R11-03.

**Derive the categories from the schema, do not hand-list them.** `.env` is the
single config source and `swingbot/config.py` is its schema; a hard-coded
category list silently drops every setting added after this task. Every key in
the schema must land in exactly one category, and the spec below asserts that.

- [ ] **Step 1: Write the failing test**

```typescript
it('puts every schema key in exactly one category', () => {
  const cats = settingsCategories(SCHEMA);
  const placed = cats.flatMap((c) => c.keys);
  expect(new Set(placed).size).toBe(placed.length);
  expect(new Set(placed)).toEqual(new Set(Object.keys(SCHEMA)));
});

it('orders categories with General first', () => {
  expect(settingsCategories(SCHEMA)[0].id).toBe('general');
});

it('gives every category a non-empty label', () => {
  expect(settingsCategories(SCHEMA).every((c) => c.label.length > 0)).toBe(true);
});

it('drops a category that has no keys rather than rendering it empty', () => {
  const cats = settingsCategories({ SOME_KEY: { group: 'general', type: 'string' } });
  expect(cats.map((c) => c.id)).toEqual(['general']);
});

it('files an unrecognised group under Other rather than losing the key', () => {
  const cats = settingsCategories({ ODD: { group: 'zzz-unknown', type: 'string' } });
  expect(cats.find((c) => c.id === 'other')!.keys).toContain('ODD');
});
```

Build `SCHEMA` in the spec from the real shape `settings-grouping.ts` already
consumes.

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/system/settings-grouping.spec.ts
```

Expected: FAIL — `settingsCategories` is undefined.

- [ ] **Step 3: Implement and render the rail**

Add `settingsCategories` beside the existing grouping logic; render the rail in
`settings-tab.ts` with the active category as a signal. The right pane renders
only the active category's keys.

- [ ] **Step 4: Run both specs and confirm they pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/system/settings-grouping.spec.ts
cd frontend && npx ng test --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system
git commit -m "feat(system): settings category rail derived from the schema (v85 D27)"
```

---

### Task R11-02: Settings search

**Files:**
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts`
- Test: `frontend/src/app/workspaces/system/settings-tab.spec.ts`

**Interfaces:**
- Consumes: R11-01's categories.
- Produces: nothing new.

**Search crosses categories; that is the whole point.** Someone who types "risk
limit" does not know which category it is in — that is why they are searching.
A search that only filters the active category would be a worse version of
scrolling.

- [ ] **Step 1: Write the failing test**

```typescript
it('matches on the setting key', () => {
  const f = render();
  search(f, 'PORTFOLIO_HEAT');
  expect(visibleKeys(f)).toContain('PORTFOLIO_HEAT_CAP_PCT');
});

it('matches on the human label and the description', () => {
  const f = render();
  search(f, 'heat cap');
  expect(visibleKeys(f)).toContain('PORTFOLIO_HEAT_CAP_PCT');
});

it('searches across every category, not only the active one', () => {
  const f = render({ activeCategory: 'general' });
  search(f, 'heat cap');
  expect(visibleKeys(f).length).toBeGreaterThan(0);
});

it('says which category each result came from', () => {
  const f = render();
  search(f, 'heat cap');
  expect(firstResult(f).querySelector('.from-category')!.textContent!.trim().length)
    .toBeGreaterThan(0);
});

it('reports a search that matched nothing as a measured zero', () => {
  const f = render();
  search(f, 'zzzz-no-such-setting');
  expect((f.nativeElement as HTMLElement).textContent).toContain('No settings match');
});

it('restores the category view when the search is cleared', () => {
  const f = render({ activeCategory: 'general' });
  search(f, 'heat cap');
  search(f, '');
  expect(visibleKeys(f)).toEqual(keysOf('general'));
});

it('does not lose an unsaved edit when the search changes', () => {
  const f = render();
  edit(f, 'PORTFOLIO_HEAT_CAP_PCT', '7');
  search(f, 'heat cap');
  expect(valueOf(f, 'PORTFOLIO_HEAT_CAP_PCT')).toBe('7');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement search**

Case-insensitive substring over key, label and description. **Search is a view
filter over the pending edit state, not a reload** — the last assertion is the
one that matters: a search that discards a half-typed value is a data-loss bug.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system
git commit -m "feat(system): cross-category settings search (v85 D27)"
```

---

### Task R11-03: The unsaved-changes footer over the existing preview flow

**Files:**
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts`
- Test: `frontend/src/app/workspaces/system/settings-tab.spec.ts`

**Interfaces:**
- Consumes: `POST /api/v1/system/settings/preview` and `PUT /system/settings`,
  both already bound in the API client.
- Produces: nothing new.

**Review, then save — never save straight from the footer.** The preview
endpoint exists precisely so a config change is seen before it is applied, and
`.env` is hot-reloaded via SIGHUP into a process that trades. The footer's
primary action opens the review; the review's action saves.

- [ ] **Step 1: Write the failing test**

```typescript
it('stays hidden while nothing is edited', () => {
  expect((render().nativeElement as HTMLElement).querySelector('.unsaved')).toBeNull();
});

it('counts the settings actually changed, not the fields touched', () => {
  const f = render();
  edit(f, 'A', 'new');
  edit(f, 'B', originalValueOf('B'));
  expect(footerText(f)).toContain('1 unsaved change');
});

it('pluralises the count', () => {
  const f = render();
  edit(f, 'A', 'new');
  edit(f, 'B', 'new');
  expect(footerText(f)).toContain('2 unsaved changes');
});

it('counts edits made in other categories too', () => {
  const f = render({ activeCategory: 'general' });
  edit(f, 'RISK_KEY', 'new');
  selectCategory(f, 'general');
  expect(footerText(f)).toContain('1 unsaved change');
});

it('calls preview rather than saving when Review Changes is pressed', () => {
  const f = render();
  edit(f, 'A', 'new');
  reviewButton(f).click();
  expect(lastCall()).toContain('/system/settings/preview');
  expect(lastCall()).not.toContain('PUT');
});

it('restores every original value on Discard', () => {
  const f = render();
  edit(f, 'A', 'new');
  discardButton(f).click();
  expect(valueOf(f, 'A')).toBe(originalValueOf('A'));
  expect((f.nativeElement as HTMLElement).querySelector('.unsaved')).toBeNull();
});

it('asks before discarding, because the edits are not recoverable', () => {
  const f = render();
  edit(f, 'A', 'new');
  discardButton(f).click();
  expect(confirmDialogShown()).toBe(true);
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build the footer**

Sticky at the bottom of the settings pane, rendered only when the pending-edit
map differs from the loaded values. The count compares values, so typing a
change and typing it back counts as nothing changed. Discard goes through the
existing confirm dialog.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system
git commit -m "feat(system): unsaved-changes footer over the existing preview flow (v85 D27)"
```

---

### Task R11-04: The minimum-sample setting

**Files:**
- Modify: `frontend/src/app/ui/stat-tile.ts`
- Modify: `swingbot/admin/api_v1/system.py:523-570`
- Test: `frontend/src/app/ui/stat-tile.spec.ts`, `tests/admin/test_api_system.py`

**Interfaces:**
- Consumes: R2-01's `MIN_SAMPLE_N`, the preferences endpoint.
- Produces: a `minSampleN` preference (default 30) that `sb-stat-tile` reads,
  falling back to the constant.

**This closes the loop opened in wave 1.** `MIN_SAMPLE_N` shipped as a constant
so the primitive could land before the control existed. The constant stays as
the fallback — a tile rendered before preferences load must still apply a
threshold, and applying none would silently mark every thin figure as sound.

- [ ] **Step 1: Write the failing test**

```typescript
it('uses the preference when one is set', () => {
  setPrefs({ minSampleN: 100 });
  expect(render({ sample: 50 }).classList).toContain('thin');
});

it('falls back to the constant when preferences have not loaded', () => {
  setPrefs(null);
  expect(render({ sample: 50 }).classList).not.toContain('thin');
  expect(render({ sample: 7 }).classList).toContain('thin');
});

it('says how many more trades are needed against the configured threshold', () => {
  setPrefs({ minSampleN: 100 });
  expect(render({ sample: 60 }).querySelector('.sample')!.getAttribute('title'))
    .toContain('40 more');
});
```

```python
def test_the_minimum_sample_preference_round_trips(client):
    client.put("/api/v1/system/preferences", json={"minSampleN": 50})
    assert client.get("/api/v1/system/preferences").get_json()["minSampleN"] == 50


def test_it_defaults_to_thirty(client):
    assert client.get("/api/v1/system/preferences").get_json()["minSampleN"] == 30


def test_a_nonsensical_threshold_is_rejected_rather_than_stored(client):
    assert client.put("/api/v1/system/preferences", json={"minSampleN": 0}).status_code == 400
    assert client.put("/api/v1/system/preferences", json={"minSampleN": -5}).status_code == 400
```

- [ ] **Step 2: Run them to make sure they fail**

```bash
cd frontend && npx ng test --include src/app/ui/stat-tile.spec.ts
python scripts/dev/testrun.py file tests/admin/test_api_system.py
```

Expected: both FAIL.

- [ ] **Step 3: Implement both ends**

Add the preference with its validation server-side; have `sb-stat-tile` inject
`PreferencesStore` and use `minSampleN` when present, `MIN_SAMPLE_N` otherwise.
Surface the setting in the Settings tab's General category.

- [ ] **Step 4: Run both suites and confirm they pass**

```bash
cd frontend && npx ng test --include src/app/ui/stat-tile.spec.ts
python scripts/dev/testrun.py file tests/admin/test_api_system.py
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/stat-tile.spec.ts swingbot/admin/api_v1/system.py tests/admin/test_api_system.py frontend/src/app/workspaces/system
git commit -m "feat(system): minimum-sample threshold as a setting (v85 D23/D27)"
```

---

### Task R11-05: Logs, Scan, and the narrow-width pass

**Files:**
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts`
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts`
- Modify: `frontend/src/app/workspaces/system/system.ts`
- Test: `frontend/src/app/workspaces/system/logs-tab.spec.ts`

- [ ] **Step 1: Run the existing specs and note them green**

```bash
cd frontend && npx ng test --include "src/app/workspaces/system/**/*.spec.ts"
```

Expected: PASS — the baseline.

- [ ] **Step 2: Write the failing test**

```typescript
it('keeps all three tabs', () => {
  expect(tabLabels()).toEqual(['Settings', 'Logs', 'Scan']);
});

it('renders no in-page heading', () => {
  expect((render().nativeElement as HTMLElement).querySelector('h1')).toBeNull();
});

it('marks the log tail with its own data age', () => {
  expect((renderLogs().nativeElement as HTMLElement).querySelector('sb-freshness')).not.toBeNull();
});

it('marks the scan panel with its own data age, separately', () => {
  expect((renderScan().nativeElement as HTMLElement).querySelector('sb-freshness')).not.toBeNull();
});
```

- [ ] **Step 3: Apply the panel language**

`sb-panel` everywhere, no in-page heading, `sb-freshness` on Logs and Scan
independently, metric grids on `repeat(auto-fit, minmax(140px, 1fr))`. Do not
restructure either tab; they are operations surfaces that work.

- [ ] **Step 4: Run the specs and the guard**

```bash
cd frontend && npx ng test --include "src/app/workspaces/system/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: system specs PASS; the guard no longer names any system file.

- [ ] **Step 5: Screenshot at both widths**

Screenshot all three tabs at 1440px and 390px. Confirm at 390px the category
rail collapses to a select rather than disappearing, the sticky footer does not
cover the last setting, and the log tail scrolls inside its own container.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/system
git commit -m "style(system): panel language across Logs and Scan, narrow-width pass"
```
