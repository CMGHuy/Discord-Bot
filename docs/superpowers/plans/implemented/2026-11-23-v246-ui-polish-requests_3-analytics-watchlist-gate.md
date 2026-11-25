# v246 — UI polish, Plan A of five: requests — Part 3: Analytics scope bar, Watchlist and Dashboard toggles, the consistency gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V246-10" -A 400 <this file>`).

**Spec:** [2026-11-23-v246-ui-polish-filters-charts-interactions-design.md](../specs/2026-11-23-v246-ui-polish-filters-charts-interactions-design.md) §A2 ("Date ranges", "Toggle groups", "Consumers in this plan", "The consistency gate", "Phone") and the A rows of "Error, empty and edge states", "Three devices" and "Testing".
**Index:** [2026-11-23-v246-ui-polish-requests_0-index.md](2026-11-23-v246-ui-polish-requests_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the binding `## Handoff` decisions live there; every task below implicitly includes them.

Tasks: V246-9 (Analytics scope bar wrapped in `sb-field`, the date range one field, Units in a field), V246-10 (Watchlist search and the Dashboard equity toggles "Interval" / "Trades" in `sb-field`), V246-11 (the consistency gate and `FIELD_GATE_ALLOWLIST`).

Order: V246-9 and V246-10 touch disjoint files and may run in either order once Parts 1 and 2 (V246-3..V246-6) are merged; V246-11 runs last, after V246-7..V246-10, because it gates their files. All frontend commands run from the worktree root with `cd frontend &&`; `--include` paths are relative to `frontend/`.

Contracts from Parts 1 and 2 these tasks rely on (import them, do not restate them in code):
- `Field` (`sb-field`, `frontend/src/app/ui/field.ts`, V246-3): inputs `label` (`''` → `aria-hidden` filler line), `size: 's' | 'm' | 'l' | 'auto'` (default `'m'`), `fullRow`; host `data-size`, classes `no-label`, `full-row`; caption `.sb-label.field-label`, always `aria-hidden="true"`; sets `--sb-control-w` (`--field-s/m/l` = 136/176/240px; `100%` below 640px except `auto`); below 640px `:host(.full-row)` is `flex: 1 1 100%; width: 100%` and a full-row field with no label hides its filler.
- `sb-select` / `sb-text-input` inside a field draw no `.sb-label`, carry host class `in-field`, and name themselves own `label` → `ariaLabel` → field label (V246-4).
- `sb-date-range` inside a labelled field names its inputs `"<label> from"` / `"<label> to"`; inside an unlabelled field or alone, `"From date"` / `"To date"` (V246-4).
- `sb-segmented` with 3+ options carries host class `many` and fills its row in equal segments below 640px (V246-5).
- `sb-control-bar` `.bar`, `.filters, .scope` and `sb-toolbar` `:host`, `.toolbar-inline` align `flex-end`; the control bar's phone `.filters` is a two-column grid (V246-6). `sb-control-row` takes opt-in `align="end"` (`data-align` on the host); its default stays `last baseline` (V246-6, Handoff 8 amended).
- `sb-field` only spans a flex row; in a grid the consumer adds `.range-field { grid-column: 1 / -1; }` on the field (V246-7's pattern).

---

# Phase 5 — Analytics, Watchlist and Dashboard wrapped

### Task V246-9: Analytics scope bar: Range/Ledger/Strategy/Horizon/Direction in `sb-field`, date range "Range", Unit segmented "Units"

**Model:** sonnet — template wrapping of one 167-line shared bar plus three CSS rules; every label, size and class is fixed in the table below.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/scope-bar.ts` — the import block (lines 6-10), `imports: [...]` (line 26), the template (lines 28-74), the styles (lines 76-82)
- Modify: `frontend/src/app/workspaces/analytics/scope-bar.spec.ts` — the `sets the unit toggle, population and freshness on one baseline` test (lines 88-95) and one added `describe` after `describe('ScopeBar', …)` (ends line 117)

**Interfaces:**
- Consumes: `Field` (`sb-field`, V246-3); the label drop and naming in `sb-select` and `sb-date-range` (V246-4); the `many` phone rule of `sb-segmented` (V246-5); `sb-control-bar`'s flex-end rows and its two-column phone grid (V246-6). Existing `ScopeBar` inputs, outputs and computed values are unchanged.
- Produces: nothing a later task imports. V246-11's gate reads this file: every `<sb-select`, `<sb-date-range` and `<sb-segmented` between `<sb-control-bar` and `</sb-control-bar>` sits inside an `<sb-field`. The scope bar is shared, so Overview, Tuning, Partials, Attribution, Benchmark and every other Analytics tab that mounts `sb-scope-bar` gets the wrapped bar from this one task.

**Why.** Spec §A2: on Analytics "the date boxes sit above the Ledger, Strategy, Horizon and Direction selects, and the R/%/€ switch drops to a row of its own", and at 390 "the second date was clipped". Each control goes into one `sb-field`, the field draws the only caption (Handoff 2) and names the control, and `sb-control-bar` (flex-end since V246-6) lines the field bottoms up. The fields, in reading order:

| mode | field label | size | classes | control |
|---|---|---|---|---|
| benchmark | Range | `auto`, `fullRow` | `range-field` | `sb-date-range` (inputs "Range from" / "Range to") |
| default | Range | `m` | — | `sb-select` presets ("Last 30 days", "Year to date", "Custom…") |
| default, preset `custom` | none (filler) | `auto`, `fullRow` | `range-field` | `sb-date-range` (inputs "From date" / "To date") |
| default | Ledger | `m` | — | `sb-select` ("Both ledgers") |
| default | Strategy | `m` | — | `sb-select` "Any strategy" |
| default | Horizon | `s` | — | `sb-select` "Any horizon" |
| default | Direction | `s` | — | `sb-select` "Both" |
| every mode but benchmark (scope slot) | Units | `auto`, `fullRow` | — | `sb-segmented` "Units": R, %, the currency |

Sizes follow the field rule (S a short single-value select, M a date or a longer option such as "Last 30 days" or "Both ledgers"). The spec's "Date ranges" gives the Analytics range the label "Range". In benchmark mode the date range is the only Range control and carries that caption. In the default mode the "Range" caption already sits on the preset select directly to its left, so the custom dates field (shown only when the preset reads "Custom…") stays uncaptioned: a second "RANGE" one field over would read as a stutter. Its inputs keep their standalone names "From date" / "To date", and its empty label line keeps its bottom edge level with the selects on desktop.

"Toggle groups": R/%/€ gets the caption "Units", and the group's accessible name becomes "Units" (it was "Unit") so the name holds the visible word (WCAG 2.5.3). Three options make it `many` (V246-5), so on a phone it fills its row in equal segments; the field is `fullRow` so it takes that row, and `.scope-line` grows to the full phone width so the row it fills is the bar's.

"Phone": the control bar's `.filters` is a two-column grid below 640px, where `fullRow` (a flex rule) does nothing. `.range-field { grid-column: 1 / -1; }` on the field gives the date range the whole grid row, so From and To split it 50/50 instead of clipping at 390 (V246-7 has the same rule for Trades). `.scope-line` changes from `align-items: baseline` to `last baseline`: the Units field's first line is now its caption, so plain `baseline` would set the population text and freshness on the caption line, above the buttons; `last baseline` puts them on the buttons' text line, which is what the v179 §3.4 rule meant.

- [ ] **Step 1: Update the baseline test**

In `frontend/src/app/workspaces/analytics/scope-bar.spec.ts`, replace the test at lines 88-95:

```ts
  it('sets the unit toggle, population and freshness on one baseline', () => {
    const { el } = create();
    const line = el.querySelector('sb-control-bar .scope .scope-line')!;
    expect(line.querySelector('sb-segmented')).not.toBeNull();
    expect(line.querySelector('.population')).not.toBeNull();
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
    expect(src).toMatch(/\.scope-line \{[^}]*align-items: baseline/);
  });
```

with:

```ts
  it('sets the unit toggle, population and freshness on one text line: the buttons\' (v179 §3.4, v246 §A2)', () => {
    const { el } = create();
    const line = el.querySelector('sb-control-bar .scope .scope-line')!;
    expect(line.querySelector('sb-field sb-segmented')).not.toBeNull();
    expect(line.querySelector('.population')).not.toBeNull();
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
    // The Units field's first line is its caption; its last is the buttons'.
    expect(src).toMatch(/\.scope-line \{[^}]*align-items: last baseline/);
  });
```

- [ ] **Step 2: Write the failing spec**

In the same file, directly after the closing `});` of `describe('ScopeBar', …)` (line 117) and before `describe('fxMissingText', …)`, add:

```ts
/* -- v246 §A2 -- every scope-bar control in one sb-field ------------------ */

describe('ScopeBar fields (v246 §A2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
  const PHONE = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';
  /** Bounds no preset produces, so the preset select reads "Custom…". */
  const CUSTOM = { ...DEFAULT_SCOPE, from: '2026-01-05', to: '2026-02-01' };

  beforeEach(() => {
    TestBed.resetTestingModule();
    connection.currency.set('€');
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: ConnectionStore, useValue: connection }],
    });
  });

  const filterFields = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('sb-control-bar .filters > sb-field')];
  const caption = (field: HTMLElement) => field.querySelector('.field-label')!.textContent!.trim();

  it('puts Range, Ledger, Strategy, Horizon and Direction each in one sb-field, in reading order', () => {
    const fields = filterFields(create().el);
    expect(fields.map(caption)).toEqual(['Range', 'Ledger', 'Strategy', 'Horizon', 'Direction']);
    expect(fields.map((f) => f.getAttribute('data-size'))).toEqual(['m', 'm', 'm', 's', 's']);
    for (const field of fields) expect(field.querySelector('sb-select')).not.toBeNull();
  });

  it('draws one caption per field and names every select from it', () => {
    const fields = filterFields(create().el);
    for (const field of fields) expect(field.querySelectorAll('.sb-label'), caption(field)).toHaveLength(1);
    expect(fields.map((f) => f.querySelector('select')!.getAttribute('aria-label')))
      .toEqual(['Range', 'Ledger', 'Strategy', 'Horizon', 'Direction']);
  });

  it('adds the custom dates as an uncaptioned field right after Range, a whole row wherever the bar is a grid', () => {
    const fields = filterFields(create({ scope: CUSTOM }).el);
    expect(fields).toHaveLength(6);
    const dates = fields[1];
    expect(dates.querySelector('sb-date-range')).not.toBeNull();
    expect(caption(dates)).toBe('');
    expect(dates.getAttribute('data-size')).toBe('auto');
    expect([...dates.classList]).toEqual(expect.arrayContaining(['no-label', 'full-row', 'range-field']));
    expect(dates.querySelector('input.from')!.getAttribute('aria-label')).toBe('From date');
    expect(dates.querySelector('input.to')!.getAttribute('aria-label')).toBe('To date');
    expect(caption(fields[0])).toBe('Range');
  });

  it('hides the custom dates field until the preset reads Custom', () => {
    const { el } = create();
    expect(el.querySelector('sb-date-range')).toBeNull();
    expect(filterFields(el)).toHaveLength(5);
  });

  it('captions the benchmark date range "Range" and names its inputs from it', () => {
    const fields = filterFields(create({ benchmark: true }).el);
    expect(fields).toHaveLength(1);
    expect(caption(fields[0])).toBe('Range');
    expect([...fields[0].classList]).toEqual(expect.arrayContaining(['full-row', 'range-field']));
    expect(fields[0].querySelector('input.from')!.getAttribute('aria-label')).toBe('Range from');
    expect(fields[0].querySelector('input.to')!.getAttribute('aria-label')).toBe('Range to');
  });

  it('puts the unit switch in a Units field on the scope line, a whole row on a phone', () => {
    for (const inputs of [{}, { tuning: true }]) {
      const { el } = create(inputs);
      const field = el.querySelector<HTMLElement>('sb-control-bar .scope .scope-line > sb-field')!;
      expect(caption(field)).toBe('Units');
      expect(field.getAttribute('data-size')).toBe('auto');
      expect(field.classList).toContain('full-row');
      expect(field.querySelector('[role="group"]')!.getAttribute('aria-label')).toBe('Units');
      expect(field.querySelector('sb-segmented')!.classList).toContain('many');
    }
  });

  it('spans the phone grid with the date range and the phone row with the scope line', () => {
    expect(SOURCE).toMatch(/\.range-field \{ grid-column: 1 \/ -1; \}/);
    expect(PHONE).toMatch(/\.scope-line \{ flex: 1 1 100%; \}/);
  });

  it('wraps every select, date range and segmented of the bar in a field, none captioning itself', () => {
    const bar = SOURCE.slice(SOURCE.indexOf('<sb-control-bar'), SOURCE.indexOf('</sb-control-bar>'));
    expect(bar.match(/<sb-(select|text-input|date-range|segmented)\b/g)).toHaveLength(8);
    expect(bar.match(/<sb-field\b/g)).toHaveLength(8);
    // \s before label: ariaLabel= is not a caption.
    expect(bar).not.toMatch(/<sb-(select|date-range)\b[^>]*\slabel=/);
  });
});
```

`readFileSync`, `join`, `TestBed`, `provideZonelessChangeDetection`, `beforeEach`, `DEFAULT_SCOPE`, `ConnectionStore`, `connection` and `create` are already in scope (lines 1-25).

- [ ] **Step 3: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/scope-bar.spec.ts`
Expected: FAIL. There is no `sb-field` in `.filters` or `.scope-line`, the selects print their own captions and carry no `aria-label`, the benchmark date inputs are named `From date` / `To date`, the group is named `Unit`, and the source has no `.range-field` rule, no phone `.scope-line` rule and still `align-items: baseline`. The other `ScopeBar` tests pass.

- [ ] **Step 4: Imports**

In `frontend/src/app/workspaces/analytics/scope-bar.ts`, add after `import { DateRange } from '../../ui/date-range';` (line 7):

```ts
import { Field } from '../../ui/field';
```

and change the `imports` line (line 26) to:

```ts
  imports: [ControlBar, DateRange, Field, Select, Segmented, Freshness],
```

- [ ] **Step 5: Wrap the controls**

Replace the template (lines 28-74, from `<sb-control-bar` through `</sb-control-bar>`) with:

```html
    <sb-control-bar [activeCount]="activeCount()" (cleared)="cleared.emit()">
      <!-- One ng-container per slot: an @if with several roots inside a
           projection slot silently drops every node but the first
           (NG8011), and a filter that vanishes is the failure this bar
           exists to prevent.
           v246 §A2: each control sits in one sb-field, which draws the one
           caption and names the control; the bar lines the field bottoms
           up. S a short select, M a date or a longer option. -->
      <ng-container filters>
        @if (benchmark()) {
          <sb-field class="range-field" label="Range" size="auto" [fullRow]="true">
            <sb-date-range [from]="scope().from" [to]="scope().to" (changed)="scopeChange.emit($event)" />
          </sb-field>
        } @else if (!tuning()) {
          <sb-field label="Range" size="m">
            <sb-select [value]="preset()" [options]="presetOptions" (valueChange)="onPreset($event)" />
          </sb-field>
          @if (preset() === 'custom') {
            <!-- No caption: "Range" sits on the preset select just left of
                 it. The empty line keeps its bottom edge level with the
                 selects; on a phone it drops and the dates take a row. -->
            <sb-field class="range-field" size="auto" [fullRow]="true">
              <sb-date-range [from]="scope().from" [to]="scope().to"
                             (changed)="scopeChange.emit($event)" />
            </sb-field>
          }
          <sb-field label="Ledger" size="m">
            <sb-select [value]="scope().ledger" [options]="ledgerOptions"
                       (valueChange)="scopeChange.emit({ ledger: $any($event) })" />
          </sb-field>
          <sb-field label="Strategy" size="m">
            <sb-select placeholder="Any strategy" [value]="scope().strategy ?? ''"
                       [options]="options(strategies())" (valueChange)="scopeChange.emit({ strategy: $event || null })" />
          </sb-field>
          <sb-field label="Horizon" size="s">
            <sb-select placeholder="Any horizon" [value]="scope().horizon ?? ''"
                       [options]="options(horizons())" (valueChange)="scopeChange.emit({ horizon: $event || null })" />
          </sb-field>
          <sb-field label="Direction" size="s">
            <sb-select placeholder="Both" [value]="scope().direction ?? ''"
                       [options]="directionOptions" (valueChange)="scopeChange.emit({ direction: $event || null })" />
          </sb-field>
        }
      </ng-container>
      <!-- v179 §3.4: a box of its own, its items on one text line. v246 §A2:
           last baseline -- the Units field's first line is its caption, its
           last the buttons' text, where the population and freshness sit. -->
      <div ngProjectAs="[scope]" class="scope-line">
        @if (benchmark()) {
          <span class="account-wide" role="note">{{ accountWideNote }}</span>
        } @else {
        <sb-field label="Units" size="auto" [fullRow]="true">
          <sb-segmented label="Units" [options]="unitOptions()" [value]="unit()"
                        (valueChange)="unitChange.emit($any($event))" />
        </sb-field>
        @if (!tuning()) {
          <span class="population" [class.num]="hasSample()">{{ population() }}</span>
          @if (asOf()) { <sb-freshness [at]="asOf()!" /> }
          @if (allTimePanels() > 0) {
            <span class="all-time">{{ allTimePanels() }} panels all-time</span>
          }
          @if (fxMissing() > 0) {
            <span class="fx-caveat" role="note">{{ fxText() }}</span>
          }
        }
        }
      </div>
    </sb-control-bar>
```

Every binding and handler is today's. The selects lose their own `label` (the field captions and names them), and the segmented's name goes from "Unit" to "Units". Both slots keep one root each (the `ng-container` and the `div`), so NG8011 cannot drop a field (brief Trap 4).

- [ ] **Step 6: Styles**

Replace the `.scope-line` line (line 77) with:

```css
    .scope-line { display: flex; flex-wrap: wrap; align-items: last baseline; gap: var(--space-10); min-width: 0; }
    /* v246 §A2: the date range takes a whole row where sb-control-bar's
       .filters is a grid (two columns below 640px); fullRow covers a flex
       row. On the field, which carries this component's style scope. */
    .range-field { grid-column: 1 / -1; }
```

and add, after the `.all-time` line (line 81):

```css
    /* v246 §A2: on a phone the scope line is the bar's full width, so the
       full-row Units field fills the row and its segments split it evenly. */
    @media (max-width: 639px) {
      .scope-line { flex: 1 1 100%; }
    }
```

The closing `}` of the `@media` block sits on its own line indented four spaces: the spec's `PHONE` regex reads up to that line.

- [ ] **Step 7: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/scope-bar.spec.ts`
Expected: PASS, 0 failed.

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed. This pulls in the Analytics workspace and tab specs that mount `sb-scope-bar`. A tab spec that queries a select by its old caption (`.sb-label` text "Strategy" inside `sb-select`) or the group by `aria-label="Unit"` has pinned the pre-v246 markup: re-point it at the field (`sb-field .field-label`) or at `aria-label="Units"`, add a one-line `v246 §A2` comment, and list the file in the commit body. No tab's own template changes here.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/workspaces/analytics/scope-bar.ts frontend/src/app/workspaces/analytics/scope-bar.spec.ts
git commit -m "feat(v246): Analytics scope bar in sb-field -- Range, Ledger, Strategy M; Horizon, Direction S; dates one field; Units segmented" -m "The field draws the one caption and names the control; the custom dates sit uncaptioned after the Range select and span the phone grid row; the scope line sits on the buttons' text line (last baseline)."
```

### Task V246-10: Watchlist search in `sb-field` L; Dashboard trading-performance presets and equity-candles toggles labelled ("Interval", "Trades") in `sb-field`

**Model:** sonnet — template wrapping in two workspaces, two renamed group names carried through three specs, and one baseline rule; every label, size and name is fixed below.

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` — imports (after `import { FilterChip, FilterChips } from '../../ui/filter-bar';`, line 27), the `imports: [...]` array (line 188), the `slot="search"` text input (lines 232-239)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts` — one added `describe` after `describe('Watchlist tag chips, search and freshness', …)` (ends line 602)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts` — imports (after line 35), `imports: [...]` (line 131), the `<div class="controls">` block (lines 132-148), styles `.controls` (lines 208-215), the phone rule (line 260), the desktop baseline rule (line 276)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` — the group names in the toggle tests (lines 552-578), the baseline test (lines 526-529), one added `describe` at the end of the file
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` — the timeframe-chip query (line 535), the group's new name

The ledger row also names `.../panels/trading-performance.ts` and its spec. This task leaves both untouched; the reason is under **Why**, and the controller should confirm it (it changes no contract another task uses).

**Interfaces:**
- Consumes: `Field` (`sb-field`, V246-3); the field naming in `sb-text-input` (own `ariaLabel` wins over the field label, V246-4); the `many` phone rule of `sb-segmented` (V246-5); `sb-toolbar`'s flex-end rows (V246-6). Existing `Watchlist.symbolQuery`, `EquityCandles.onTimeframe`, `EquityCandles.onBasis`, `timeframeOptions`, `basisOptions` are unchanged.
- Produces: nothing a later task imports. V246-11's gate reads `watchlist.ts`: the one `<sb-text-input` between `<sb-toolbar` and `</sb-toolbar>` sits inside an `<sb-field`; the `+ Tag` form's `sb-control-row` (no `align="end"`) is a form, not a bar, and keeps its own labelled controls. The equity toggle groups are named `"Candle interval"` and `"Trades counted"` (were `"Candle timeframe"` and `"Equity basis"`). V246-16 edits `equity-candles.ts` after this task and must keep the `.controls` block as written here.

**Why.** Spec §A2 "Consumers in this plan" lists Watchlist and "the Dashboard trading-performance toggles". "Toggle groups" names those toggles: 1H/4H/1D/1W and Open + closed / Closed only render "as `sb-segmented` in one style, with a label when they sit in a bar ('Interval', 'Trades')". Both groups live in `sb-equity-candles`, the chart inside the Trading performance card (`portfolio-value.ts:47`). They are already `sb-segmented` (brief §0.5); here they get a captioned `sb-field` each.

| where | field label | size | control, accessible name |
|---|---|---|---|
| Watchlist toolbar, `slot="search"` | Symbol | `l` | `sb-text-input type=search`, "Filter the watchlist by symbol" (unchanged) |
| Equity chart `.controls` | Interval | `auto`, `fullRow` | `sb-segmented` 1H/4H/1D/1W, "Candle interval" |
| Equity chart `.controls` | Trades | `auto`, `fullRow` | `sb-segmented` Open + closed / Closed trades only, "Trades counted" |

The visible caption is `aria-hidden` (V246-3), so each control's accessible name must hold the caption's word (WCAG 2.5.3, label in name). The search keeps its longer name, which already ends "by symbol". The two groups are renamed "Candle interval" and "Trades counted", the way Trades kept "Row density" for its "Density" caption (V246-7). The search is the free-text L field the spec's size rule names. The tag chips beside it are not one of the gated controls and need no field: flex-end (V246-6) already sets their bottom edge, one `--control-h` tall, level with the search box.

On the chart, `.controls` stops centring and aligns `flex-end`, so the two fields' bottoms meet. "Phone": both fields are `fullRow`, so each takes a row (as the old `.controls sb-segmented { flex: 1 1 100%; }` did, now from the field), and the four-option Interval group is `many` (V246-5) and splits its row evenly. The two-option Trades group keeps its natural width. On desktop the toggle row and the readout share a grid row with `align-self: baseline`. A field's first baseline is now its caption, which would lift the readout to the caption line. `last baseline` puts the readout on the buttons' text line.

The trading-performance date presets (Today…All in the card header) stay as they are. They are not one of the spec's toggle groups: spec §B9 converts them ("The range chips (TODAY…ALL) use `sb-segmented` like the rest"), and they sit alone in the panel header with no captioned neighbour to misalign against. A field around them now would add a caption line to the card header that B9 rewrites anyway.

- [ ] **Step 1: Write the failing Watchlist spec**

In `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, directly after the closing `});` of `describe('Watchlist tag chips, search and freshness', …)` (line 602), add:

```ts
/* -- v246 §A2 -- the symbol search in an sb-field -------------------------- */

describe('Watchlist toolbar field (v246 §A2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/watchlist/watchlist.ts'), 'utf8');
  const search = (el: HTMLElement) => el.querySelector('sb-toolbar [slot="search"]') as HTMLElement;

  it('puts the symbol search in an L sb-field captioned Symbol, the field carrying the toolbar slot', () => {
    const field = search(render().nativeElement as HTMLElement);
    expect(field.tagName.toLowerCase()).toBe('sb-field');
    expect(field.getAttribute('data-size')).toBe('l');
    expect(field.querySelector('.field-label')!.textContent!.trim()).toBe('Symbol');
    expect(field.querySelectorAll('.sb-label')).toHaveLength(1);
    expect(field.querySelector('input[type="search"]')).not.toBeNull();
  });

  it('keeps the input\'s own longer name, which holds the caption (WCAG 2.5.3)', () => {
    const name = search(render().nativeElement as HTMLElement).querySelector('input')!.getAttribute('aria-label')!;
    expect(name).toBe('Filter the watchlist by symbol');
    expect(name.toLowerCase()).toContain('symbol');
  });

  it('still narrows the table by symbol through the field', () => {
    const f = render({ symbols: ['AAPL', 'XOM'] });
    const input = search(f.nativeElement as HTMLElement).querySelector('input')!;
    input.value = 'xo';
    input.dispatchEvent(new Event('input'));
    f.detectChanges();
    expect(visibleSymbols(f)).toEqual(['XOM']);
  });

  it('wraps the toolbar\'s one text input in a field; the field, not the input, carries the slot', () => {
    const toolbar = SOURCE.slice(SOURCE.indexOf('<sb-toolbar'), SOURCE.indexOf('</sb-toolbar>'));
    expect(toolbar.match(/<sb-(select|text-input|date-range|segmented)\b/g)).toHaveLength(1);
    expect(toolbar.match(/<sb-field\b/g)).toHaveLength(1);
    expect(toolbar).not.toMatch(/<sb-text-input\b[^>]*\bslot=/);
  });

  it('leaves the + Tag form alone: a form row, not a bar, its controls captioned by themselves', () => {
    const f = render();
    const el = f.nativeElement as HTMLElement;
    (el.querySelector('.add-tag') as HTMLButtonElement).click();
    f.detectChanges();
    const form = el.querySelector('.tag-form')!;
    expect(form.querySelector('sb-field')).toBeNull();
    expect(form.getAttribute('data-align')).toBe('baseline');
    expect([...form.querySelectorAll('.sb-label')].map((n) => n.textContent!.trim())).toEqual(['Symbol', 'Tag']);
  });
});
```

`render()`, `visibleSymbols()`, `readFileSync` and `join` are already in scope (lines 31-32, 522-583).

- [ ] **Step 2: Write the failing equity-candles spec**

In `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`:

1. Replace every `'Candle timeframe'` with `'Candle interval'` (lines 552, 559, 562, 577) and every `'Equity basis'` with `'Trades counted'` (lines 568, 578). The tests keep their titles; only the group they find is renamed.
2. Replace the baseline test (lines 526-529):

```ts
  it('puts the controls and the readout on one baseline on desktop, now the caption row is gone', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/panels/equity-candles.ts'), 'utf8');
    expect(source).toMatch(/\.controls, \.readout \{ align-self: baseline; \}/);
  });
```

with:

```ts
  it('puts the readout on the toggle buttons\' text line on desktop (v246 §A2: last baseline, the fields\' first line is a caption)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/panels/equity-candles.ts'), 'utf8');
    expect(source).toMatch(/\.controls, \.readout \{ align-self: last baseline; \}/);
  });
```

3. At the end of the file, after the closing `});` of `describe('sb-equity-candles', …)`, add:

```ts
/* -- v246 §A2 -- the Interval and Trades toggles in sb-field --------------- */

describe('sb-equity-candles toggles in sb-field (v246 §A2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/panels/equity-candles.ts'), 'utf8');
  const fields = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>('.controls > sb-field')];
  const caption = (field: HTMLElement) => field.querySelector('.field-label')!.textContent!.trim();

  it('puts Interval and Trades each in one captioned sb-field, a whole row each on a phone', () => {
    const all = fields(render(response(MIXED)).el);
    expect(all.map(caption)).toEqual(['Interval', 'Trades']);
    for (const field of all) {
      expect(field.getAttribute('data-size')).toBe('auto');
      expect(field.classList).toContain('full-row');
      expect(field.querySelectorAll('.sb-label')).toHaveLength(1);
      expect(field.querySelectorAll('sb-segmented')).toHaveLength(1);
    }
  });

  it('names each group with a phrase that holds its caption (WCAG 2.5.3)', () => {
    const all = fields(render(response(MIXED)).el);
    const names = all.map((f) => f.querySelector('[role="group"]')!.getAttribute('aria-label')!);
    expect(names).toEqual(['Candle interval', 'Trades counted']);
    all.forEach((f, i) => expect(names[i].toLowerCase()).toContain(caption(f).toLowerCase()));
  });

  it('splits the four intervals evenly on a phone; the two-option Trades keeps its width', () => {
    const { el } = render(response(MIXED));
    expect(el.querySelector('sb-segmented.timeframe')!.classList).toContain('many');
    expect(el.querySelector('sb-segmented.basis')!.classList).not.toContain('many');
  });

  it('keeps both captioned toggles when there is nothing to draw', () => {
    expect(fields(render(response([], { tf: '1H' })).el).map(caption)).toEqual(['Interval', 'Trades']);
  });

  it('lines the fields up on their bottom edge; the field, not a page rule, takes the phone row', () => {
    expect(SOURCE).toMatch(/\.controls \{[^}]*align-items: flex-end;/);
    expect(SOURCE).not.toMatch(/\.controls \{[^}]*align-items: center;/);
    expect(SOURCE).not.toMatch(/\.controls sb-segmented/);
  });

  it('wraps both segmented groups of the toggle row in a field', () => {
    const row = SOURCE.slice(SOURCE.indexOf('<div class="controls">'), SOURCE.indexOf('@if (readout().length)'));
    expect(row.match(/<sb-segmented\b/g)).toHaveLength(2);
    expect(row.match(/<sb-field\b/g)).toHaveLength(2);
  });
});
```

`render`, `response`, `MIXED`, `readFileSync` and `join` are module-level in this file (lines 1-2, 24-48).

- [ ] **Step 3: Update the Dashboard spec**

In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` line 535, change `'sb-equity-candles [aria-label="Candle timeframe"] button'` to `'sb-equity-candles [aria-label="Candle interval"] button'`.

- [ ] **Step 4: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL. `[slot="search"]` is the bare `sb-text-input`. The equity groups are still named "Candle timeframe" / "Equity basis", so every renamed query and the Dashboard chip query find nothing. `.controls > sb-field` is empty, `.controls` still centres, and the desktop rule is still `align-self: baseline`. The tag-form test and the other pre-existing tests pass.

- [ ] **Step 5: Wrap the Watchlist search**

In `frontend/src/app/workspaces/watchlist/watchlist.ts`, add after `import { FilterChip, FilterChips } from '../../ui/filter-bar';` (line 27):

```ts
import { Field } from '../../ui/field';
```

and add `Field,` to the `imports: [...]` array (line 188) directly after `FilterChips,`. Replace the `slot="search"` text input (lines 232-239):

```html
            <sb-text-input
              slot="search"
              type="search"
              ariaLabel="Filter the watchlist by symbol"
              placeholder="Filter by symbol"
              [value]="symbolQuery()"
              (valueChange)="symbolQuery.set($event)"
            />
```

with:

```html
            <!-- v246 §A2: the search is an L sb-field; the field carries the
                 toolbar slot and the one caption, and the input keeps its
                 longer name, which holds the caption's word. -->
            <sb-field slot="search" label="Symbol" size="l">
              <sb-text-input
                type="search"
                ariaLabel="Filter the watchlist by symbol"
                placeholder="Filter by symbol"
                [value]="symbolQuery()"
                (valueChange)="symbolQuery.set($event)"
              />
            </sb-field>
```

The tag chips, `+ Tag`, `sb-freshness` and the `+ Tag` form are unchanged. The field is one element carrying `slot`, never inside a host-side `@if` / `@for` (brief Trap 3).

- [ ] **Step 6: Wrap the equity toggles**

In `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, add after `import { SegmentOption, Segmented } from '../../../ui/segmented';` (line 35):

```ts
import { Field } from '../../../ui/field';
```

change `imports: [Async, Segmented, Button, Hint],` (line 131) to `imports: [Async, Segmented, Button, Hint, Field],`, and replace the `<div class="controls">` block (lines 132-148) with:

```html
    <!-- v246 §A2: each toggle sits in a captioned sb-field ("Interval",
         "Trades"), the label line and bottom edge every control row shares;
         each group's name holds its caption's word. -->
    <div class="controls">
      <sb-field label="Interval" size="auto" [fullRow]="true">
        <sb-segmented
          class="timeframe"
          label="Candle interval"
          [options]="timeframeOptions"
          [value]="store.tf()"
          (valueChange)="onTimeframe($event)"
        />
      </sb-field>
      <sb-field label="Trades" size="auto" [fullRow]="true">
        <sb-segmented
          class="basis"
          label="Trades counted"
          [options]="basisOptions"
          [value]="store.basis()"
          (valueChange)="onBasis($event)"
        />
      </sb-field>
    </div>
```

- [ ] **Step 7: Equity styles**

In the same file, in the `.controls` rule (lines 208-215) change `align-items: center;` to `align-items: flex-end;` and put this comment directly above `.controls {`:

```css
    /* v246 §A2: the bottom edge, not the centre: both toggles sit in
       captioned sb-fields, so their field bottoms are the button bottoms. */
```

Delete the phone line `.controls sb-segmented { flex: 1 1 100%; }` (line 260): each field is `fullRow`, which takes the phone row itself (V246-3), and the Interval group fills it (V246-5). Replace the desktop comment and rule (lines 274-276):

```css
      /* One row now (the account caption that made it two is gone): the
         timeframe buttons and the readout share a text baseline. */
      .controls, .readout { align-self: baseline; }
```

with:

```css
      /* One row now (the account caption that made it two is gone): the
         toggle buttons and the readout share a text line. v246 §A2: last
         baseline, because each toggle's field starts with its caption. */
      .controls, .readout { align-self: last baseline; }
```

- [ ] **Step 8: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS, 0 failed.

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed. It pulls in `portfolio-value.spec.ts`, `trading-performance.spec.ts` and the Dashboard specs that mount the chart. A spec still querying `aria-label="Candle timeframe"` or `"Equity basis"` was missed by the `git grep` below: rename it the same way and list it in the commit body.

Before committing, confirm no other reference to the old names is left:
Run: `git grep -n "Candle timeframe\|Equity basis" -- frontend`
Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "feat(v246): Watchlist search in an L sb-field; Dashboard equity toggles captioned Interval and Trades" -m "The groups are renamed Candle interval / Trades counted so each name holds its caption; .controls aligns flex-end and the readout sits on the buttons' text line (last baseline). Trading-performance date presets are left to B9."
```

# Phase 6 — The consistency gate

### Task V246-11: Consistency gate: a control in a bar outside `sb-field` fails; allowlist for the B10 bars

**Model:** sonnet — one source-scanning rule with a small tag-depth walk, self-tested on synthetic templates, in an existing spec file; the allowlist is measured, not guessed.

**Files:**
- Modify: `frontend/src/app/workspaces/workspace-consistency.spec.ts` (one added block at the end of the file: the allowlist, three helpers and two `describe`s)

**Interfaces:**
- Consumes: `WORKSPACE_TS` (module-level in this file, line 248: every workspace `.ts` under `src/app/workspaces/`, nested tabs and panels included, specs and the gallery left out, as `{ name, source }` with `name` relative to `src/`, e.g. `app/workspaces/trades/trades.ts`); the wrapped consumers of V246-7 (`trades/trades.ts`), V246-8 (`calendar/calendar.ts`, `<sb-control-row page-scope align="end">`), V246-9 (`analytics/scope-bar.ts`), V246-10 (`watchlist/watchlist.ts`).
- Produces: `const FIELD_GATE_ALLOWLIST: readonly string[]`: the workspace files, named relative to `src/app/workspaces/` (`'research/research.ts'`), whose bars still hold an unwrapped control. Plan B's B10 wraps them, empties the list and deletes it. Nothing outside this file imports it.

**Why.** Spec §A2 "The consistency gate": "a control in a bar that sits outside an `sb-field` fails. It ships with an allowlist naming those not-yet-wrapped consumers, so it passes when A merges. B10 empties the allowlist and deletes it." Spec "Testing" names the bars as `sb-control-bar` / `sb-filter-bar`. This task gates those plus `sb-toolbar` (Handoff 4: Trades, Watchlist and Research use it) and any `sb-control-row align="end"`. Handoff 8 (amended) makes `sb-control-row` a bar only when a v246 bar opts in. The `+ Tag` form, the settings save bar and the Versions headline stay plain rows, and a plain row's labelled controls are not offenders.

The definitions:
- **A bar** is the template text from `<sb-control-bar`, `<sb-toolbar` or `<sb-filter-bar` to its matching close tag, or an `<sb-control-row …align="end"…>` block. A self-closing `<sb-filter-bar … />` (Trades' summary strip) holds nothing and is not a block.
- **A control** is `<sb-select`, `<sb-text-input`, `<sb-date-range` or `<sb-segmented`, the four `sb-field` wraps (V246-4, V246-5). Chips, buttons and links are not field controls (spec "Control height" sizes them with `--control-h` directly).
- **Outside a field** means the control's tag opens while no `<sb-field` is open. The walk counts `<sb-field …>` opens (a self-closing `<sb-field … />` opens nothing) against `</sb-field>` closes, in source order. HTML and block comments are stripped first, so a commented-out control or a docblock that quotes a tag is not read as markup.
- **A v246 control row** is any `sb-control-row` that holds an `sb-field`. It must set `align="end"` (Handoff 8: "the gate checks that a v246 bar using `sb-control-row` sets `align="end"`"), or its fields stay on v179's `last baseline` and the bottom edges drift apart.

The allowlist is measured, not copied from the spec's list. Run against today's tree with V246-7..V246-10 applied, the only workspace whose bar still holds one of the four controls unwrapped is `research/research.ts` (an `sb-text-input slot="search"` and an `sb-segmented slot="instrument"` in its `sb-toolbar`). The spec's other B10 names hold none. System logs and scan put button groups and a link in their toolbars. System settings has no bar, only plain control rows. Tuning, Partials, Attribution and Benchmark have no bar of their own: they mount the shared `sb-scope-bar`, which V246-9 wrapped. A list holding files that pass would hide a regression in them, so a second test fails on any stale entry. The list can only shrink, and B10 deletes it when it is empty. A third test proves the gate reads real bars (one or more per v246 consumer), so a broken regex cannot pass by matching nothing.

- [ ] **Step 1: Write the failing gate**

At the end of `frontend/src/app/workspaces/workspace-consistency.spec.ts` (after the closing `});` of `describe('destructive actions live in the header (v195 Phase 4, §5.2)', …)`), add:

```ts
/* -- v246 §A2 -- every control in a bar sits in an sb-field ----------------- */

/** Workspace files whose bars still hold a control outside an sb-field,
 *  relative to src/app/workspaces/. Plan B's B10 wraps them, empties this
 *  list and deletes it (spec v246 §A2, "The consistency gate"). Every entry
 *  must still offend (the stale-entry test below), so the list only shrinks.
 *  Measured, not the spec's list: System logs/scan toolbars hold buttons and
 *  a link, Settings has no bar, and Tuning, Partials, Attribution and
 *  Benchmark mount the shared sb-scope-bar, wrapped in V246-9. */
const FIELD_GATE_ALLOWLIST: readonly string[] = ['research/research.ts'];

/** The v246 consumers whose bars this plan wrapped (V246-7..V246-10). */
const FIELD_GATE_CONSUMERS: readonly string[] = [
  'analytics/scope-bar.ts', 'calendar/calendar.ts', 'trades/trades.ts', 'watchlist/watchlist.ts',
];

const BAR_BLOCK = /<(sb-control-bar|sb-toolbar|sb-filter-bar)\b[\s\S]*?<\/\1>/g;
const ROW_BLOCK = /<sb-control-row\b([^>]*)>([\s\S]*?)<\/sb-control-row>/g;
const FIELD_TOKEN = /<sb-field\b[^>]*>|<\/sb-field>|<sb-(?:select|text-input|date-range|segmented)\b/g;
const ALIGN_END = /\balign="end"/;

/** Source without HTML or block comments: a commented-out control, or a
 *  docblock that quotes a tag, is not markup. */
function withoutComments(source: string): string {
  return source.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '');
}

/** The template text of every bar in a source: sb-control-bar, sb-toolbar
 *  and sb-filter-bar blocks, and each sb-control-row that sets align="end". */
function barBlocks(source: string): string[] {
  const text = withoutComments(source);
  const bars = [...text.matchAll(BAR_BLOCK)].map((m) => m[0]);
  const rows = [...text.matchAll(ROW_BLOCK)].filter((m) => ALIGN_END.test(m[1])).map((m) => m[0]);
  return [...bars, ...rows];
}

/** The control tags in a bar that open while no sb-field is open. */
function unwrappedControls(block: string): string[] {
  let depth = 0;
  const out: string[] = [];
  for (const [token] of block.matchAll(FIELD_TOKEN)) {
    if (token.startsWith('<sb-field')) {
      if (!token.endsWith('/>')) depth += 1;
    } else if (token === '</sb-field>') {
      depth = Math.max(0, depth - 1);
    } else if (depth === 0) {
      out.push(token.slice(1));
    }
  }
  return out;
}

/** sb-control-rows that hold an sb-field but keep the baseline default. */
function unalignedFieldRows(source: string): string[] {
  return [...withoutComments(source).matchAll(ROW_BLOCK)]
    .filter((m) => /<sb-field\b/.test(m[2]) && !ALIGN_END.test(m[1]))
    .map((m) => `<sb-control-row${m[1]}>`);
}

const workspaceName = (name: string) => name.slice('app/workspaces/'.length);
const offendersIn = (source: string) => barBlocks(source).flatMap(unwrappedControls);

describe('the field gate reads templates the way Angular does (v246 §A2)', () => {
  it('flags a control directly in a bar and passes one inside a field', () => {
    expect(offendersIn('<sb-toolbar [controls]="c"><sb-select slot="a" /></sb-toolbar>')).toEqual(['sb-select']);
    expect(offendersIn('<sb-toolbar [controls]="c"><sb-field slot="a" label="A"><sb-select /></sb-field></sb-toolbar>'))
      .toEqual([]);
  });

  it('counts a control nested deeper inside a field as wrapped', () => {
    expect(offendersIn('<sb-control-bar><ng-container filters><sb-field label="A"><div><sb-date-range /></div></sb-field></ng-container></sb-control-bar>'))
      .toEqual([]);
  });

  it('does not let a self-closing field wrap the control after it', () => {
    expect(offendersIn('<sb-control-bar><sb-field label="A" /><sb-segmented label="B" /></sb-control-bar>'))
      .toEqual(['sb-segmented']);
  });

  it('catches the second control after a field closes', () => {
    expect(offendersIn('<sb-toolbar><sb-field><sb-select /></sb-field><sb-text-input slot="b" /></sb-toolbar>'))
      .toEqual(['sb-text-input']);
  });

  it('ignores commented-out controls and controls outside any bar', () => {
    expect(offendersIn('<sb-toolbar><!-- <sb-select slot="old" /> --></sb-toolbar>')).toEqual([]);
    expect(offendersIn('/** <sb-toolbar> <sb-select> </sb-toolbar> */ <sb-select label="A" />')).toEqual([]);
    expect(offendersIn('<sb-control-row class="tag-form"><sb-select label="Symbol" /></sb-control-row>')).toEqual([]);
  });

  it('treats a control row that opts into align="end" as a bar', () => {
    expect(offendersIn('<sb-control-row page-scope align="end"><sb-select label="A" /></sb-control-row>'))
      .toEqual(['sb-select']);
  });

  it('reads no block out of a self-closing sb-filter-bar', () => {
    expect(barBlocks('<sb-filter-bar [active]="a" (cleared)="b()" />')).toEqual([]);
  });

  it('flags a control row of fields that keeps the baseline default', () => {
    expect(unalignedFieldRows('<sb-control-row page-scope><sb-field label="A"><sb-select /></sb-field></sb-control-row>'))
      .toEqual(['<sb-control-row page-scope>']);
    expect(unalignedFieldRows('<sb-control-row page-scope align="end"><sb-field><sb-select /></sb-field></sb-control-row>'))
      .toEqual([]);
    expect(unalignedFieldRows('<sb-control-row class="add"><sb-text-input ariaLabel="x" /></sb-control-row>')).toEqual([]);
  });
});

describe('every control in a bar sits in an sb-field (v246 §A2)', () => {
  const GATED = WORKSPACE_TS.map(({ name, source }) => ({ name: workspaceName(name), source }));
  const sourceOf = (name: string) => GATED.find((s) => s.name === name)?.source ?? '';

  it('reads at least one bar in each v246 consumer and in each allowlisted file', () => {
    for (const name of [...FIELD_GATE_CONSUMERS, ...FIELD_GATE_ALLOWLIST]) {
      expect(barBlocks(sourceOf(name)).length, name).toBeGreaterThan(0);
    }
  });

  it('puts every select, text input, date range and segmented in a bar inside an sb-field', () => {
    const offenders = GATED
      .filter(({ name }) => !FIELD_GATE_ALLOWLIST.includes(name))
      .flatMap(({ name, source }) => offendersIn(source).map((tag) => `${name}: ${tag}`));
    expect(offenders).toEqual([]);
  });

  it('lists only files whose bars still hold an unwrapped control (B10 empties the list)', () => {
    const stale = FIELD_GATE_ALLOWLIST.filter((name) => offendersIn(sourceOf(name)).length === 0);
    expect(stale).toEqual([]);
  });

  it('opts every control row of sb-fields into bottom-edge alignment', () => {
    const offenders = GATED.flatMap(({ name, source }) => unalignedFieldRows(source).map((row) => `${name}: ${row}`));
    expect(offenders).toEqual([]);
  });
});
```

`WORKSPACE_TS` is a module-level `const` declared above (line 248), so this block, appended after it, may use it. `describe`, `expect` and `it` are already imported (line 4).

- [ ] **Step 2: Run the gate to see it fail**

To prove the gate bites before it is trusted, run it once with the allowlist emptied. Change `const FIELD_GATE_ALLOWLIST: readonly string[] = ['research/research.ts'];` to `= [];` for this one run.

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: FAIL in exactly one test, `puts every select, text input, date range and segmented in a bar inside an sb-field`, listing `research/research.ts: sb-segmented` and `research/research.ts: sb-text-input` (in source order) and nothing else. The self-tests and the other three gate tests pass.

If any other file appears, resolve it before going on:
- **A v246 consumer** (`trades/trades.ts`, `calendar/calendar.ts`, `analytics/scope-bar.ts`, `watchlist/watchlist.ts`): the task that wrapped it missed a control. Wrap it in that file the way the task did, and list the file in this commit's body.
- **A file spec §B10 names** (System logs/scan/settings, Research, Tuning, Partials, Attribution, Benchmark), for example a control a later merge added: add its name to `FIELD_GATE_ALLOWLIST` in sorted order, and add a clause to the list's docblock saying what it holds.
- **Any other file**, such as a page v247 added: stop and report it to the controller. It is neither Plan A's to wrap nor B10's to own.

If `unalignedFieldRows` names a row, it is a control row that holds sb-fields without `align="end"`. Add the attribute in that file (V246-6's opt-in) and list the file in the commit body.

- [ ] **Step 3: Restore the allowlist and run the gate to pass**

Set the list back to `['research/research.ts']` (plus any B10 file Step 2 added).

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: PASS, 0 failed.

Then the stale-entry check: temporarily add `'trades/trades.ts'` to the list and run the same command.
Expected: FAIL in `lists only files whose bars still hold an unwrapped control`, naming `trades/trades.ts`. Remove the entry again and re-run: PASS.

- [ ] **Step 4: Narrow run**

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed (this task changes one spec file; the run confirms nothing else selects on it).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/workspace-consistency.spec.ts
git commit -m "test(v246): consistency gate -- a select, text input, date range or segmented in a bar must sit in an sb-field" -m "Bars are sb-control-bar, sb-toolbar, sb-filter-bar and any sb-control-row align=end; a control row of fields must opt into align=end. FIELD_GATE_ALLOWLIST holds research/research.ts, the one measured offender; B10 empties and deletes it. A stale entry fails."
```
