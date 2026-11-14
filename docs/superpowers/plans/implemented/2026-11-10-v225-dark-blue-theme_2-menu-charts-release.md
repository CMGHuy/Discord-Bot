# v225 — Dark blue theme, part 2: menu row, palette command, charts, audit, release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v225 — Dark blue theme](../specs/2026-11-10-v225-dark-blue-theme-design.md)
**Index:** [`2026-11-10-v225-dark-blue-theme_0-index.md`](2026-11-10-v225-dark-blue-theme_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.

Tasks V225-7..V225-13. `<wt>` is the worktree `.claude/worktrees/2026-11-10-v225-dark-blue-theme` (branch of the same name); `<main>` is the main checkout. Every command names a path under `<wt>` and never `cd`s into a subdirectory of the main tree.

Consumed from part 1 (ledger contracts, final): `Theme`, `THEME_PREF_KEY`, `ThemeStorage`, `THEME_STORAGE`, `ThemeService { theme(); set(); toggle() }` in `frontend/src/app/ui/theme.service.ts` (V225-3, which always writes `document.documentElement.dataset['theme']`); `Shell.theme = inject(ThemeService)` and `header.topbar button.theme-toggle` (V225-6); the Navy values in the index's Global Constraints.

# Phase C — the menu row and the palette command

### Task V225-7: Profile-menu "Theme" row on every device, bound through the shell

**Model:** sonnet — a new segmented row copying the Density row's shape, plus two bindings and cross-control specs; no new pattern.

**Files:**
- Modify: `frontend/src/app/shell/profile-menu.ts` (import, `THEME_OPTIONS`, template row after the Density row, CSS selectors, input/output/handler, class doc comment)
- Modify: `frontend/src/app/shell/profile-menu.spec.ts` (new describe `Theme control (v225)` inside `describe('ProfileMenu')`)
- Modify: `frontend/src/app/shell/shell.html` (two bindings on `<sb-profile-menu>`)
- Modify: `frontend/src/app/shell/shell.spec.ts` (new describe `v225: one theme across the bar button and the profile menu`)

**Interfaces:**
- Consumes: `Theme` (type) and `THEME_STORAGE` (specs only) from `frontend/src/app/ui/theme.service.ts` (V225-3); `Shell.theme` (`ThemeService`, protected, V225-6); the bar element `header.topbar button.theme-toggle` with `[attr.aria-pressed]` (V225-6).
- Produces: `ProfileMenu.theme = input<Theme>('graphite')`; `ProfileMenu.themeChanged = output<Theme>()`; module const `THEME_OPTIONS: SegmentOption[]`; DOM `div.theme-row > sb-segmented.theme-control` whose segments are `.segment` buttons labelled `Black` and `Dark blue`. V225-11's audit selects `sb-profile-menu .avatar` and `.theme-control .segment`, so neither class name may change.

- [ ] **Step 1: Write the failing profile-menu specs**

Append inside `describe('ProfileMenu', …)` of `frontend/src/app/shell/profile-menu.spec.ts`, after the `Density control (v195 §1.4)` describe. Add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top.

```ts
  describe('Theme control (v225)', () => {
    const control = () => el.querySelector('sb-segmented.theme-control');
    const segments = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('sb-segmented.theme-control .segment'));
    const pressed = () =>
      segments().find((b) => b.getAttribute('aria-pressed') === 'true')!.textContent!.trim();

    it('offers Black and Dark blue under the label "Theme"', () => {
      openMenu();
      expect(control()!.querySelector('[role=group]')!.getAttribute('aria-label')).toBe('Theme');
      expect(el.querySelector('.theme-row .menu-label')!.textContent!.trim()).toBe('Theme');
      expect(segments().map((b) => b.textContent!.trim())).toEqual(['Black', 'Dark blue']);
    });

    it('sits under Density and directly above Sign out', () => {
      openMenu();
      const row = el.querySelector('.theme-row')!;
      expect(row.previousElementSibling!.classList.contains('density-row')).toBe(true);
      expect(row.nextElementSibling!.textContent).toContain('Sign out');
    });

    it('defaults to Black and marks the theme it is given', () => {
      openMenu();
      expect(pressed()).toBe('Black');
      fixture.componentRef.setInput('theme', 'navy');
      fixture.detectChanges();
      expect(pressed()).toBe('Dark blue');
    });

    it('emits the chosen theme and keeps the menu open', () => {
      const chosen: string[] = [];
      fixture.componentInstance.themeChanged.subscribe((theme) => chosen.push(theme));
      openMenu();
      segments()[1].click();
      fixture.detectChanges();
      segments()[0].click();
      fixture.detectChanges();
      expect(chosen).toEqual(['navy', 'graphite']);
      expect(menu()).not.toBeNull();
    });

    it('reads anything but navy as graphite: the segmented control hands back a string', () => {
      const chosen: string[] = [];
      fixture.componentInstance.themeChanged.subscribe((theme) => chosen.push(theme));
      for (const value of ['navy', 'NAVY', 'navy ', '', 'dark']) fixture.componentInstance['onTheme'](value);
      expect(chosen).toEqual(['navy', 'graphite', 'graphite', 'graphite', 'graphite']);
    });

    it('carries no "Desktop only" note: the theme changes every device', () => {
      openMenu();
      expect(el.querySelector('.theme-row .menu-note')).toBeNull();
    });

    it('lays the row out like Motion and Density, with 44px segments on touch', () => {
      const source = readFileSync(join(process.cwd(), 'src/app/shell/profile-menu.ts'), 'utf8');
      expect(source).toMatch(/\.motion-row,\s*\.density-row,\s*\.theme-row\s*\{\s*display: flex;/);
      expect(source).toMatch(
        /@media \(pointer: coarse\), \(max-width: 1023px\) \{[^{}]*\.theme-control \.segment \{ min-width: 44px;/,
      );
    });
  });
```

- [ ] **Step 2: Write the failing shell specs**

In `frontend/src/app/shell/shell.spec.ts` (as left by V225-6: `THEME_STORAGE` is imported, `shellProviders()` already supplies `memoryThemeStorage()`, and a file-level `afterEach` clears `data-theme`), make sure `ComponentFixture` is in the `@angular/core/testing` import. Append a new top-level describe after `describe('shell top-bar cluster (v195 Phase 3)', …)`. It reuses the file's `shellProviders()`, `createShell()`, `memoryThemeStorage(map)`, `CLOCK`, `DENSITY_STORAGE` and `ViewportService`; its own `THEME_STORAGE` provider comes after `shellProviders()`, so it wins and `stored` sees `ui.theme`. Do not touch the desktop bar-order pin: V225-6 already set it to `… button.palette-trigger, button.theme-toggle, sb-hint, sb-profile-menu …`.

```ts
describe('v225: one theme across the bar button and the profile menu', () => {
  const NOW = Date.parse('2026-10-27T12:00:00Z');
  const html = document.documentElement;
  let stored: Map<string, string>;
  const fakeStorage = () => ({
    get: (key: string) => stored.get(key) ?? null,
    set: (key: string, value: string) => stored.set(key, value),
  });

  beforeEach(() => {
    stored = new Map();
    TestBed.configureTestingModule({
      providers: [
        ...shellProviders(),
        { provide: DENSITY_STORAGE, useValue: fakeStorage() },
        { provide: THEME_STORAGE, useValue: memoryThemeStorage(stored) },
      ],
    });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
  });

  afterEach(() => {
    delete html.dataset['density'];   // data-theme is cleared by the file-level afterEach (V225-6)
  });

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function mount() {
    const fixture = createShell();
    await settle(fixture);
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const openMenu = async (fixture: ComponentFixture<unknown>, el: HTMLElement) => {
    el.querySelector<HTMLButtonElement>('sb-profile-menu .avatar')!.click();
    await settle(fixture);
  };
  const themeSegments = (el: HTMLElement) =>
    Array.from(el.querySelectorAll<HTMLButtonElement>('sb-profile-menu .theme-control .segment'));
  const segment = (el: HTMLElement, label: 'Black' | 'Dark blue') =>
    themeSegments(el).find((button) => button.textContent!.trim() === label)!;
  const pressedSegment = (el: HTMLElement) =>
    themeSegments(el).find((button) => button.getAttribute('aria-pressed') === 'true')!.textContent!.trim();
  const barButton = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('header.topbar button.theme-toggle');

  it('writes ui.theme and data-theme from the menu row, and the bar button follows', async () => {
    const { fixture, el } = await mount();
    expect(html.dataset['theme']).toBe('graphite');
    await openMenu(fixture, el);
    segment(el, 'Dark blue').click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
    expect(pressedSegment(el)).toBe('Dark blue');
    expect(barButton(el)!.getAttribute('aria-pressed')).toBe('true');
  });

  it('moves the pressed segment when the bar button is clicked, and the bar when the menu is', async () => {
    const { fixture, el } = await mount();
    await openMenu(fixture, el);
    expect(pressedSegment(el)).toBe('Black');
    barButton(el)!.click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('navy');
    // A click outside the menu closes it (ProfileMenu's document click); reopen to read it.
    if (!el.querySelector('sb-profile-menu [role=menu]')) await openMenu(fixture, el);
    expect(pressedSegment(el)).toBe('Dark blue');
    segment(el, 'Black').click();
    await settle(fixture);
    expect(barButton(el)!.getAttribute('aria-pressed')).toBe('false');
    expect(stored.get('ui.theme')).toBe('graphite');
  });

  it('keeps the Theme row on a phone, where it is the only switch', async () => {
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(true), isNarrow: signal(true), viewport: signal('xs') },
    });
    const { fixture, el } = await mount();
    expect(barButton(el)).toBeNull();
    await openMenu(fixture, el);
    segment(el, 'Dark blue').click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
  });
});
```

- [ ] **Step 3: Run the specs to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts`
Expected: FAIL. The `Theme control (v225)` tests find no `sb-segmented.theme-control` and `onTheme` is not a function; the shell tests find no `.theme-control .segment`.

- [ ] **Step 4: Implement the row in `frontend/src/app/shell/profile-menu.ts`**

- Import: `import { Theme } from '../ui/theme.service';`.
- Below `DENSITY_OPTIONS`:

```ts
/** The two grounds, in the order the control shows them (spec v225). The
 *  stored values stay `graphite` | `navy`; the labels are what a user reads. */
const THEME_OPTIONS: SegmentOption[] = [
  { value: 'graphite', label: 'Black' },
  { value: 'navy', label: 'Dark blue' },
];
```

- Template, between the closing `</div>` of `.density-row` and the Sign out `<button>`:

```html
        <div class="theme-row" role="none">
          <span class="menu-label" aria-hidden="true">Theme</span>
          <sb-segmented
            class="theme-control"
            label="Theme"
            [options]="themeOptions"
            [value]="theme()"
            (valueChange)="onTheme($event)"
          />
        </div>
```

- CSS: the shared layout rule's selector list becomes `.motion-row,` / `.density-row,` / `.theme-row {` (one per line, body unchanged). In the `@media (pointer: coarse), (max-width: 1023px)` rule, append `:host ::ng-deep .theme-control .segment` as the **last** selector of the list, so its final line reads `:host ::ng-deep .theme-control .segment { min-width: 44px; justify-content: center; }` and the `.density-control .segment` line before it ends in a comma.
- Class members, after the density block:

```ts
  /** The current ground, owned by the shell's ThemeService (spec v225). */
  readonly theme = input<Theme>('graphite');
  readonly themeChanged = output<Theme>();

  protected readonly themeOptions = THEME_OPTIONS;

  /** Validated, not trusted: anything but exactly 'navy' is the default. */
  protected onTheme(value: string): void {
    this.themeChanged.emit(value === 'navy' ? 'navy' : 'graphite');
  }
```

- Class doc comment: add a paragraph after the Density one: "Theme (spec v225) sits under Density: Black (Graphite) or Dark blue (Navy), a per-browser choice the shell writes through `ThemeService`. Unlike Density it changes every device, so it carries no note; on a phone it is the only switch, because the bar button is tablet and desktop only."

- [ ] **Step 5: Bind the row in `frontend/src/app/shell/shell.html`**

On `<sb-profile-menu>`, add one line directly after the `[density]="density.density()" (densityChanged)="density.set($event)"` line:

```html
                       [theme]="theme.theme()" (themeChanged)="theme.set($event)"
```

- [ ] **Step 6: Run the specs to see them pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/primitives.spec.ts`
Expected: PASS, `0 failed`. `primitives.spec.ts` confirms no colour literal entered the component.

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/profile-menu.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.spec.ts
git -C "<wt>" commit -m "feat(v225): Theme row (Black | Dark blue) in the profile menu on every device, bound to ThemeService (V225-7)"
```

### Task V225-8: "Switch theme" command in the palette

**Model:** sonnet — one data item, one closed-union field and one `choose()` branch, with four existing pins to move in step.

**Files:**
- Modify: `frontend/src/app/shell/palette/palette-items.ts` (`PaletteItem.action`, third `PREFERENCE_ITEMS` row, doc comments)
- Modify: `frontend/src/app/shell/palette/palette-items.spec.ts` (preference pin l.90-96, allowed-keys/invariant test l.98-115, new ranking test)
- Modify: `frontend/src/app/shell/palette/command-palette.ts` (inject `ThemeService`, `choose()` branch, class doc comment)
- Modify: `frontend/src/app/shell/palette/command-palette.spec.ts` (fake `THEME_STORAGE`, `afterEach` hygiene, new test, injected-services pin l.268-273)

**Interfaces:**
- Consumes: `ThemeService.toggle(): void`, `THEME_STORAGE` from `frontend/src/app/ui/theme.service.ts` (V225-3).
- Produces: `PaletteItem.action?: 'toggle-theme'`; the item `{ key: 'pref:theme:toggle', group: 'preferences', label: 'Switch theme', sub: 'Black or Dark blue', route: null, action: 'toggle-theme' }` as the last entry of `PREFERENCE_ITEMS`.

- [ ] **Step 1: Move the palette-items pins and add the ranking test**

In `frontend/src/app/shell/palette/palette-items.spec.ts`, replace the test `'offers the density preference both ways, applied in place'` with:

```ts
  it('offers the density preference both ways and the theme switch, all applied in place', () => {
    expect(PREFERENCE_ITEMS.map((item) => [item.label, item.density, item.action, item.route])).toEqual([
      ['Density: Dense', 'dense', undefined, null],
      ['Density: Comfortable', 'comfortable', undefined, null],
      ['Switch theme', undefined, 'toggle-theme', null],
    ]);
    expect(PREFERENCE_ITEMS.at(-1)).toEqual({
      key: 'pref:theme:toggle', group: 'preferences', label: 'Switch theme',
      sub: 'Black or Dark blue', route: null, action: 'toggle-theme',
    });
    expect(PALETTE_GROUP_LABELS).toEqual({ tickers: 'Ticker', trades: 'Trade', pages: 'Page', preferences: 'Preference' });
  });

  it('finds the theme switch by "theme", "switch", "dark blue" and "black"', () => {
    for (const query of ['theme', 'switch', 'dark blue', 'black']) {
      expect(rankPaletteItems(query, PREFERENCE_ITEMS).map((item) => item.label), query).toEqual(['Switch theme']);
    }
  });
```

Import `rankPaletteItems` into this spec if the import list lacks it. In the next test (rename it `'registers no destructive or money-moving action: every item navigates, sets density or switches the theme'`):
- `allowedKeys` gains `'action'`: `new Set(['key', 'group', 'label', 'sub', 'route', 'queryParams', 'density', 'action', 'recency'])`.
- The invariant line becomes:

```ts
      expect(item.route !== null || item.density !== undefined || item.action === 'toggle-theme', item.key).toBe(true);
```

The "no function value" line and the destructive-label regex stay as they are; "Switch theme" and "Black or Dark blue" match none of its words.

- [ ] **Step 2: Add the palette behaviour test and move the injection pin**

In `frontend/src/app/shell/palette/command-palette.spec.ts`:
- Import `THEME_STORAGE` from `'../../ui/theme.service'`.
- In `beforeEach`, add beside the `DENSITY_STORAGE` provider: `{ provide: THEME_STORAGE, useValue: { get: (k: string) => stored.get(k) ?? null, set: (k: string, v: string) => stored.set(k, v) } },`.
- In `afterEach`, add `delete document.documentElement.dataset['theme'];`.
- After `'applies a density preference in place, without navigating'`, add:

```ts
  it('switches the theme in place, without navigating, and back again', async () => {
    const { fixture, el, host } = await mount();
    const router = TestBed.inject(Router);
    const before = router.url;
    await type(fixture, el, 'theme');
    expect(optionLabels(el)).toEqual(['Switch theme']);
    await press(fixture, el, 'Enter');
    expect(document.documentElement.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
    expect(router.url).toBe(before);
    expect(host.closes).toBe(1);

    host.open.set(true);
    await settle(fixture);
    await type(fixture, el, 'switch');
    await press(fixture, el, 'Enter');
    expect(document.documentElement.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
    expect(host.closes).toBe(2);
  });
```

- Rename `'can only navigate and set density: it injects nothing that acts'` to `'can only navigate, set density and switch the theme: it injects nothing that acts'` and change its pin to:

```ts
    expect(injected).toEqual(['DensityService', 'Router', 'SearchIndexStore', 'SessionStore', 'ThemeService']);
```

The `type(fixture, el, 'dense')` → `['Density: Dense']` and `'comf'` → `['Density: Comfortable']` pins stay unchanged: the new item's label and sub hold neither string.

- [ ] **Step 3: Run the specs to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/shell/palette/palette-items.spec.ts --include src/app/shell/palette/command-palette.spec.ts`
Expected: FAIL. The preference pin sees two rows, not three; `'theme'` matches nothing; the injection pin lacks `ThemeService`.

- [ ] **Step 4: Implement in `frontend/src/app/shell/palette/palette-items.ts`**

- `PaletteItem`, after `density?: RowDensity;`:

```ts
  /** An in-place preference with no value to carry: the theme toggle (spec
   *  v225). A closed union of names, never a callback, so an item stays data. */
  action?: 'toggle-theme';
```

- `PREFERENCE_ITEMS`: doc comment becomes `/** Density, both ways (spec §1.4), and the theme switch (spec v225). Applied in place; no route. */`; append the third row:

```ts
  { key: 'pref:theme:toggle', group: 'preferences', label: 'Switch theme', sub: 'Black or Dark blue', route: null, action: 'toggle-theme' },
```

- The file header comment's "palette-items.spec.ts fails if a field that could carry one ever appears" stays true: `action` is a string union, and the spec's allowed-keys list names it.

- [ ] **Step 5: Implement in `frontend/src/app/shell/palette/command-palette.ts`**

- Import `ThemeService` from `'../../ui/theme.service'`.
- Field beside `density`: `private readonly theme = inject(ThemeService);`.
- `choose()`:

```ts
  protected choose(item: PaletteItem): void {
    if (item.density) this.density.set(item.density);
    else if (item.action === 'toggle-theme') this.theme.toggle();
    else if (item.route) void this.router.navigate([item.route], { queryParams: item.queryParams ?? {} });
    this.closed.emit();
  }
```

- Class doc comment: "or set the row density" becomes "set the row density, or switch the theme"; "the search index and the density service and nothing else" becomes "the search index and the density and theme services and nothing else".

- [ ] **Step 6: Run the specs to see them pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/shell/palette/palette-items.spec.ts --include src/app/shell/palette/command-palette.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, `0 failed` (`shell.spec.ts` mounts the palette through the shell).

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add frontend/src/app/shell/palette/palette-items.ts frontend/src/app/shell/palette/palette-items.spec.ts frontend/src/app/shell/palette/command-palette.ts frontend/src/app/shell/palette/command-palette.spec.ts
git -C "<wt>" commit -m "feat(v225): Switch theme command in the palette, through ThemeService (V225-8)"
```

# Phase D — charts follow the theme

### Task V225-9: Trade chart follows the theme (options, price pane, legend)

**Model:** sonnet — a signal effect re-applying options on a real lightweight-charts instance, a behaviour-preserving split of `render()`, and a mutable palette on a canvas primitive; mechanical once the seams are named.

**Files:**
- Modify: `frontend/src/app/ui/chart/trade-chart.ts` (inject `ThemeService`, third effect, `restyle()`, `render()` split into `paintLayers()`)
- Modify: `frontend/src/app/ui/chart/price-pane.ts` (shared colour helper, `applyPricePanePalette`)
- Modify: `frontend/src/app/ui/chart/primitives/legend-primitive.ts` (palette read through a getter, `setPalette`)
- Modify: `frontend/src/app/ui/chart/trade-chart.spec.ts` (theme hygiene, new describe)
- Modify: `frontend/src/app/ui/chart/primitives/legend-primitive.spec.ts` (new describe)

**Interfaces:**
- Consumes: `ThemeService { theme(): Theme; set(theme: Theme): void }`, `THEME_STORAGE` from `frontend/src/app/ui/theme.service.ts` (V225-3); existing `chartPalette(): ChartPalette`, `chartOptions(palette): DeepPartial<ChartOptions>` (`ui/chart/chart-theme.ts`); `PricePane { candles; volume }` (`price-pane.ts`).
- Produces: `export function applyPricePanePalette(pane: PricePane, palette: ChartPalette): void`; `LegendPrimitive.setPalette(palette: ChartPalette): void`.

Why: `create()` reads `chartPalette()` once, so the chart options (ground, grid, axis text, crosshair, pane separators), the candle and volume series colours and the legend's constructor-held palette keep the old theme after a toggle. `render()` already re-reads `chartPalette()` for the indicator panes, overlays, strategy overlay and plan lines, so re-running those parts repaints them. `vline-primitive.ts` is not used here and needs nothing (its colours arrive through `setLine`).

- [ ] **Step 1: Write the failing legend spec**

Append to `frontend/src/app/ui/chart/primitives/legend-primitive.spec.ts` (add `vi` to the vitest import):

```ts
/** A canvas context that records every fill and stroke colour it is handed. */
function recordingContext() {
  const fills: string[] = [];
  const strokes: string[] = [];
  const context = {
    save() {}, restore() {}, fillRect() {}, strokeRect() {}, fillText() {},
    globalAlpha: 1, lineWidth: 1, font: '', textBaseline: '',
    set fillStyle(value: string) { fills.push(value); },
    get fillStyle(): string { return fills.at(-1) ?? ''; },
    set strokeStyle(value: string) { strokes.push(value); },
    get strokeStyle(): string { return strokes.at(-1) ?? ''; },
  };
  return { context, fills, strokes };
}

function draw(legend: LegendPrimitive) {
  const recorded = recordingContext();
  legend.paneViews()[0].renderer()!.draw({
    useMediaCoordinateSpace: (cb: (scope: unknown) => void) =>
      cb({ context: recorded.context, mediaSize: { width: 800, height: 400 } }),
  } as never);
  return recorded;
}

describe('LegendPrimitive.setPalette (v225)', () => {
  const GRAPHITE = { text: '#e6e8eb', textMuted: '#9aa4b2', tooltipSurface: '#1f242b', tooltipBorder: '#2d333b' } as never;
  const NAVY = { text: '#e6ecf5', textMuted: '#9fb0c8', tooltipSurface: '#172440', tooltipBorder: '#233453' } as never;

  it('draws the box and the lines in the palette it was last given', () => {
    const legend = new LegendPrimitive(GRAPHITE, ['AAPL · 2w', 'EMA20']);
    expect(draw(legend).fills).toEqual(['#1f242b', '#e6e8eb', '#9aa4b2']);
    legend.setPalette(NAVY);
    const { fills, strokes } = draw(legend);
    expect(fills).toEqual(['#172440', '#e6ecf5', '#9fb0c8']);
    expect(strokes).toEqual(['#233453']);
  });

  it('asks the chart for a redraw when the palette changes, and is quiet before it is attached', () => {
    const legend = new LegendPrimitive(GRAPHITE, ['AAPL']);
    expect(() => legend.setPalette(NAVY)).not.toThrow();
    const requestUpdate = vi.fn();
    legend.attached({ requestUpdate } as never);
    legend.setPalette(GRAPHITE);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Write the failing trade-chart spec**

In `frontend/src/app/ui/chart/trade-chart.spec.ts`:
- Imports: `afterEach, vi` from vitest; `THEME_STORAGE, ThemeService` from `'../theme.service'`; `chartPalette` from `'./chart-theme'`; `applyPricePanePalette` from `'./price-pane'`.
- The existing `beforeEach` gains the provider `{ provide: THEME_STORAGE, useValue: { get: () => null, set: () => {} } }` (so no spec here touches real localStorage), and add a file-level `afterEach(() => { delete document.documentElement.dataset['theme']; });`.
- Append:

```ts
describe('TradeChart follows the theme (v225)', () => {
  // jsdom resolves token() against the flat Graphite fixture (test-setup.ts),
  // so the Navy ground is layered here the way tokens.css layers it.
  const NAVY_CSS = ':root[data-theme="navy"]{--surface:#0c1424;--text:#e6ecf5;--text-muted:#9fb0c8;--text-faint:#5f6f8a}';
  let style: HTMLStyleElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: THEME_STORAGE, useValue: { get: () => null, set: () => {} } }],
    });
    style = document.createElement('style');
    style.textContent = NAVY_CSS;
    document.head.appendChild(style);
  });

  afterEach(() => {
    style.remove();
    delete document.documentElement.dataset['theme'];
  });

  async function mounted() {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  async function flip(fixture: Awaited<ReturnType<typeof mounted>>, theme: 'graphite' | 'navy') {
    TestBed.inject(ThemeService).set(theme);
    fixture.detectChanges();
    await fixture.whenStable();
  }

  it('re-applies the chart ground, the series colours and the legend palette on a flip', async () => {
    const fixture = await mounted();
    const component = fixture.componentInstance;
    const applied = vi.spyOn(component['chart']!, 'applyOptions');
    const candles = vi.spyOn(component['candles']!, 'applyOptions');
    const volume = vi.spyOn(component['volume']!, 'applyOptions');

    await flip(fixture, 'navy');

    expect(applied.mock.calls.at(-1)![0]).toMatchObject({ layout: { background: { color: '#0c1424' }, textColor: '#9fb0c8' } });
    expect(candles).toHaveBeenCalledWith(expect.objectContaining({ upColor: chartPalette().up, wickDownColor: chartPalette().down }));
    expect(volume).toHaveBeenCalledWith({ color: '#5f6f8a' });
    expect(component['legend']!['currentPalette'].surface).toBe('#0c1424');
  });

  it('repaints the palette-fed layers without moving the viewport', async () => {
    const fixture = await mounted();
    const component = fixture.componentInstance;
    const strategy = vi.spyOn(component['strategy']!, 'render');
    const fit = vi.spyOn(component['chart']!.timeScale(), 'fitContent');

    await flip(fixture, 'navy');

    expect(strategy).toHaveBeenCalledTimes(1);
    expect(strategy.mock.calls[0][1].surface).toBe('#0c1424');
    expect(fit).not.toHaveBeenCalled();
  });

  it('returns to the Graphite ground when flipped back', async () => {
    const fixture = await mounted();
    const graphiteSurface = chartPalette().surface;
    await flip(fixture, 'navy');
    const applied = vi.spyOn(fixture.componentInstance['chart']!, 'applyOptions');
    await flip(fixture, 'graphite');
    expect(graphiteSurface).not.toBe('#0c1424');
    expect(applied.mock.calls.at(-1)![0]).toMatchObject({ layout: { background: { color: graphiteSurface } } });
  });

  it('restyles nothing after the chart is destroyed', async () => {
    const fixture = await mounted();
    fixture.destroy();
    expect(() => TestBed.inject(ThemeService).set('navy')).not.toThrow();
  });
});

describe('applyPricePanePalette (v225)', () => {
  it('gives the candles and the volume the same colours createPricePane does', () => {
    const candles = { applyOptions: vi.fn() };
    const volume = { applyOptions: vi.fn() };
    const palette = { up: '#1', down: '#2', volume: '#3' } as never;
    applyPricePanePalette({ candles, volume } as never, palette);
    expect(candles.applyOptions).toHaveBeenCalledWith({
      upColor: '#1', downColor: '#2', borderUpColor: '#1', borderDownColor: '#2', wickUpColor: '#1', wickDownColor: '#2',
    });
    expect(volume.applyOptions).toHaveBeenCalledWith({ color: '#3' });
  });
});
```

The spec files are outside the colour gate (`*.spec.ts` is excluded), so the hex values here are allowed.

- [ ] **Step 3: Run the specs to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/ui/chart/trade-chart.spec.ts --include src/app/ui/chart/primitives/legend-primitive.spec.ts`
Expected: FAIL. `setPalette` and `applyPricePanePalette` do not exist; no `applyOptions` call follows a flip.

- [ ] **Step 4: `price-pane.ts`: one colour helper for both paths**

- Add a module-private `function priceSeriesColors(palette: ChartPalette)` returning `{ candles: { upColor, downColor, borderUpColor, borderDownColor, wickUpColor, wickDownColor }, volume: { color: palette.volume } }` (bodies, borders and wicks from `palette.up`/`palette.down`, as today). Move the "Bodies, borders and wicks share their side's colour" comment onto it.
- In `createPricePane`, the candle options spread `...priceSeriesColors(palette).candles` in place of the six literal keys, and the volume options spread `...priceSeriesColors(palette).volume` in place of `color: palette.volume` (keep its "One colour for every bar" comment beside the spread). Every other option stays.
- Add:

```ts
/** Re-colours an existing pane after a theme flip (spec v225): the same
 *  colours `createPricePane` gave it, read from a fresh palette. */
export function applyPricePanePalette(pane: PricePane, palette: ChartPalette): void {
  const colors = priceSeriesColors(palette);
  pane.candles.applyOptions(colors.candles);
  pane.volume.applyOptions(colors.volume);
}
```

- [ ] **Step 5: `legend-primitive.ts`: a palette that can change**

- `LegendRenderer` and `LegendPaneView` take `palette: () => ChartPalette` instead of `palette: ChartPalette`. In `draw()`, read `const palette = this.palette();` once after the empty-lines return and use it for `tooltipSurface`, `tooltipBorder`, `text` and `textMuted`.
- `LegendPrimitive`: new field `private currentPalette: ChartPalette;` set in the constructor; the view is built with `() => this.currentPalette`. Add, after `setLines`:

```ts
  /** Swaps the colours in place after a theme flip (spec v225) and asks for
   *  a redraw, the same way `setLines` does. */
  setPalette(palette: ChartPalette): void {
    this.currentPalette = palette;
    this.requestUpdate?.();
  }
```

- The class doc comment's "calls `setLines` whenever the trade, the crosshair, or the theme changes" becomes "calls `setLines` whenever the trade or the crosshair changes, and `setPalette` when the theme does (v225)". The constructor signature `(palette: ChartPalette, lines: string[])` is unchanged.

- [ ] **Step 6: `trade-chart.ts`: restyle on the theme signal**

- Imports: `ThemeService` from `'../theme.service'`; `applyPricePanePalette` beside `createPricePane`.
- Field: `private readonly theme = inject(ThemeService);`.
- Split `render()` behaviour-preservingly: everything after `volume.setData(…)` up to and including `this.legend?.setLines(this.legendLines());` moves, verbatim with its comments, into `private paintLayers(data: ChartResponse, visible: Record<ChartLayer, boolean>): void`. `render()` then calls `this.paintLayers(data, visible);` followed by its unchanged `this.chart?.timeScale().fitContent();`.
- Add `private restyle(): void`: return early unless `this.chart`, `this.candles` and `this.volume` are set; read `const palette = chartPalette();`; `this.chart.applyOptions(chartOptions(palette))`; `applyPricePanePalette({ candles: this.candles, volume: this.volume }, palette)`; `this.legend?.setPalette(palette)`; then `const data = this.data(); if (data) this.paintLayers(data, this.prefs.visible());`. No `fitContent`: a flip must not move the viewport.
- In the constructor, after the render effect and before `destroyRef.onDestroy`:

```ts
    // v225: create() read the palette once. A theme flip re-reads it and
    // re-applies everything that copied a colour, so no pixel keeps the
    // other ground. untracked: data and layer changes stay render()'s job.
    effect(() => {
      this.theme.theme();
      untracked(() => this.restyle());
    });
```

Its first run, right after creation, re-applies the same colours and is harmless.

- [ ] **Step 7: Run the specs to see them pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/ui/chart/trade-chart.spec.ts --include src/app/ui/chart/primitives/legend-primitive.spec.ts --include src/app/ui/chart/chart-theme.spec.ts --include src/app/ui/primitives.spec.ts`
Expected: PASS, `0 failed`. The three earlier `TradeChart` tests still pass unchanged, and `primitives.spec.ts` finds no colour literal in the chart code.

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add frontend/src/app/ui/chart/trade-chart.ts frontend/src/app/ui/chart/price-pane.ts frontend/src/app/ui/chart/primitives/legend-primitive.ts frontend/src/app/ui/chart/trade-chart.spec.ts frontend/src/app/ui/chart/primitives/legend-primitive.spec.ts
git -C "<wt>" commit -m "feat(v225): trade chart re-applies its options, series colours and legend palette on a theme flip (V225-9)"
```

### Task V225-10: Dashboard equity candles follow the theme

**Model:** sonnet — turns a read-once colour object into a theme-tracked computed and adds one restyle effect on a real chart; the effect order and the intraday axis are the only traps, both pinned below.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`

**Interfaces:**
- Consumes: `ThemeService { theme(); set() }`, `THEME_STORAGE` from `frontend/src/app/ui/theme.service.ts` (V225-3); existing `chartPalette()`, `chartOptions(palette)`, `token()` from `ui/chart/chart-theme.ts`; `isIntraday(tf)` and `CandleColors` from `./equity-candles.model`; `VLinePrimitive.current(): VLineSpec | null`, `BaselinePrimitive.current(): BaselineSpec | null`.
- Produces: nothing a later task consumes.

Why: `colors` (l.~328) is an IIFE run once at construction, and `create()` (l.~579) reads `chartPalette()` once for the chart options and the candle series. After a flip the ground, grid, axis text, candle colours, the hollow candles' wick, the seam line and label and the baseline line and fills would all keep the old theme. `vline-primitive.ts` needs no change: its colours come from the `setLine` spec this component re-issues on every render.

- [ ] **Step 1: Write the failing specs**

In `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`:
- Imports: `THEME_STORAGE, ThemeService` from `'../../../ui/theme.service'`; `chartPalette` beside `token` from `'../../../ui/chart/chart-theme'`.
- The `render()` helper's providers gain `{ provide: THEME_STORAGE, useValue: { get: () => null, set: () => {} } }`.
- First statement inside `describe('sb-equity-candles', …)`: `afterEach(() => { delete document.documentElement.dataset['theme']; });`.
- Append inside `describe('sb-equity-candles', …)`:

```ts
  describe('follows the theme (v225)', () => {
    // jsdom resolves token() against the flat Graphite fixture (test-setup.ts);
    // the Navy ground is layered here the way tokens.css layers it.
    const NAVY_CSS = ':root[data-theme="navy"]{--surface:#0c1424;--text-muted:#9fb0c8;--text-faint:#5f6f8a}';
    let style: HTMLStyleElement;
    type Internals = {
      chart: { applyOptions(o: unknown): void; options(): { timeScale: { timeVisible: boolean } } };
      series: { applyOptions(o: unknown): void };
      seam: { current(): { label: string; color: string; textColor: string } | null } | null;
      baseline: { current(): { line: string } | null } | null;
    };
    const internals = (fixture: { componentInstance: EquityCandles }) => fixture.componentInstance as unknown as Internals;

    beforeEach(() => {
      style = document.createElement('style');
      style.textContent = NAVY_CSS;
      document.head.appendChild(style);
    });

    afterEach(() => style.remove());

    async function flip(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }, theme: 'graphite' | 'navy') {
      TestBed.inject(ThemeService).set(theme);
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    }

    it('re-applies the chart ground and the candle colours, and keeps the intraday time axis', async () => {
      const { fixture } = render(response(hourlyCandles(30), { tf: '1H' }));
      const component = internals(fixture);
      const applied = vi.spyOn(component.chart, 'applyOptions');
      const series = vi.spyOn(component.series, 'applyOptions');

      await flip(fixture, 'navy');

      expect(applied).toHaveBeenCalledWith(expect.objectContaining({
        layout: expect.objectContaining({ background: { color: '#0c1424' }, textColor: '#9fb0c8' }),
      }));
      expect(series).toHaveBeenCalledWith(expect.objectContaining({
        upColor: chartPalette().up, downColor: chartPalette().down, wickUpColor: chartPalette().up,
      }));
      expect(component.chart.options().timeScale.timeVisible).toBe(true);
    });

    it('redraws the seam and the baseline in the new inks', async () => {
      const { fixture } = render(response(MIXED));
      at(fixture, 0, 2);
      await flip(fixture, 'navy');
      at(fixture, 0, 2);
      const component = internals(fixture);
      expect(component.seam!.current()).toMatchObject({ label: 'Recording started', color: '#5f6f8a', textColor: '#9fb0c8' });
      expect(component.baseline!.current()).toMatchObject({ line: '#9fb0c8' });
    });

    it('returns to the Graphite inks when flipped back', async () => {
      const { fixture } = render(response(MIXED));
      const graphiteFaint = token('--text-faint');
      await flip(fixture, 'navy');
      await flip(fixture, 'graphite');
      expect(graphiteFaint).not.toBe('#5f6f8a');
      expect(internals(fixture).seam!.current()!.color).toBe(graphiteFaint);
    });
  });
```

`at(fixture, 0, 2)` runs again after the flip because jsdom's 0px chart may report its own range when the series is redrawn; the second call puts the three MIXED candles back in view so the baseline has a first candle.

- [ ] **Step 2: Run the spec to see it fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: FAIL in `follows the theme (v225)`: no `applyOptions` carries `#0c1424`, and the seam keeps the Graphite `--text-faint`. Every earlier test still passes.

- [ ] **Step 3: Implement in `equity-candles.ts`**

- Import `ThemeService` from `'../../../ui/theme.service'`; import `ChartPalette` (type) beside `chartOptions, chartPalette, token`.
- Two module-private helpers above the component:

```ts
/** The candle series' six colours: bodies, borders and wicks by side. */
function candleSeriesColors(palette: ChartPalette) {
  return {
    upColor: palette.up, downColor: palette.down,
    borderUpColor: palette.up, borderDownColor: palette.down,
    wickUpColor: palette.up, wickDownColor: palette.down,
  };
}

/** Time on the axis for 1H/4H only; one place for render() and a theme flip,
 *  because chartOptions() alone resets timeVisible to false. */
function timeScaleOptions(data: EquityCandlesResponse | null) {
  return { timeVisible: data ? isIntraday(data.tf) : false, secondsVisible: false };
}
```

- Field: `private readonly theme = inject(ThemeService);` declared above `colors`.
- `colors` becomes a computed that tracks the theme (doc comment: "Chart colours from the tokens, re-read when the theme flips (spec v225). `--text-faint` is the hollow candle's wick."):

```ts
  private readonly colors = computed(() => {
    this.theme.theme();
    const palette = chartPalette();
    return { up: palette.up, down: palette.down, faint: token('--text-faint'), muted: palette.textMuted,
             posSoft: palette.posSoft, negSoft: palette.negSoft };
  });
```

  `ThemeService.set()` writes `data-theme` before anything reads this computed again, so the re-read sees the new ground.
- Every `this.colors` read becomes `this.colors()`: in `seriesData` (`toSeriesData(this.candles(), data.tf, this.colors())`), in the baseline effect (`line`, `above`, `below`) and in `render()`'s seam `setLine` (`color`, `textColor`). Because `seriesData` and the baseline effect now read the computed, a flip re-runs the render effect (new hollow-candle colours and seam inks) and the baseline effect by themselves.
- `create()`: the candle series options spread `...candleSeriesColors(palette)` in place of the six keys; `priceLineVisible` and `priceFormat` stay.
- `render()`: `chart.applyOptions({ timeScale: timeScaleOptions(data) });` replaces the inline object.
- New method:

```ts
  /** v225: what create() copied out of the palette, re-applied on a flip. */
  private restyle(): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    const palette = chartPalette();
    chart.applyOptions(chartOptions(palette));
    chart.applyOptions({ timeScale: timeScaleOptions(this.store.data()) });
    series.applyOptions(candleSeriesColors(palette));
  }
```

- Constructor: directly after the create effect (so it is registered before the render effect), add:

```ts
    // v225: the chart options and the series colours were read once in
    // create(); re-apply them whenever the theme-tracked colours change.
    effect(() => {
      this.colors();
      untracked(() => this.restyle());
    });
```

  Its first run follows creation and re-applies the same colours; it moves no range (no `fitContent`, no `setVisibleRange`).
- Update the old "Read once: chart colours come from the tokens at creation, as in `TradeChart`" comment: it is replaced by the computed's doc comment above.

- [ ] **Step 4: Run the spec to see it pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/primitives.spec.ts`
Expected: PASS, `0 failed`. The two-way scope-link tests still pass: the restyle effect moves no range, so no gesture or programmatic move is reported.

- [ ] **Step 5: Commit**

```bash
git -C "<wt>" add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts
git -C "<wt>" commit -m "feat(v225): Dashboard equity candles re-apply chart, candle, seam and baseline colours on a theme flip (V225-10)"
```

# Phase E — audit and screenshots

### Task V225-11: Layout audit: `--theme` switch and the open profile menu at phone widths

**Model:** sonnet — a new flag, one pure verdict function and one Playwright step, all following the audit's existing dock-check pattern.

**Files:**
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`DEFAULTS.theme`, `--theme` flag, `THEMES`, `THEME_KEY`, `themeSuffix`, `CHECKS` + `'profile-menu'`, `PROFILE_MENU_MAX_WIDTH`, `PROFILE_MENU_SELECTORS`, `profileMenuVerdict`)
- Modify: `frontend/scripts/layout-audit.mjs` (seed the theme in `withContext`, check it took, `auditProfileMenu`, suffixed screenshot and out names, usage docstring)
- Modify: `frontend/scripts/layout-audit-lib.test.mjs`

**Interfaces:**
- Consumes: the SPA's `sb-profile-menu .avatar`, `sb-profile-menu [role=menu]` and `sb-profile-menu .theme-control .segment` (V225-7); the storage key `ui.theme` and the attribute `<html data-theme="navy">` (V225-3, V225-4).
- Produces: `parseArgs(argv).theme: 'graphite' | 'navy'` (default `'graphite'`; `--theme <x>` throws `unknown theme <x>` for anything else); `export const THEME_KEY = 'ui.theme'`; `export const THEMES = Object.freeze(['graphite', 'navy'])`; `export function themeSuffix(theme): '' | '-navy'`; `CHECKS` ending in `'profile-menu'`; `export const PROFILE_MENU_MAX_WIDTH = 639`; `export function profileMenuVerdict({ menu, segments, viewport }): { ok: boolean, reason: string | null }`. V225-12 runs `node frontend/scripts/layout-audit.mjs --theme navy`.

The allow-list stays theme-blind: an entry matches a finding in either theme (no new field). A finding that appears only under Navy is a real defect and is fixed, never allowed.

- [ ] **Step 1: Write the failing lib tests**

In `frontend/scripts/layout-audit-lib.test.mjs`, add `PROFILE_MENU_MAX_WIDTH, PROFILE_MENU_SELECTORS, THEMES, THEME_KEY, profileMenuVerdict, themeSuffix` to the import list, then:

- Replace the `CHECKS` test:

```js
test('CHECKS are the spec six plus vcenter, hint (v194 A2), rail-label (v195 Phase 7), dock (v203) and profile-menu (v225), in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint', 'rail-label', 'dock', 'profile-menu']);
});
```

- In `'parseArgs: defaults are the local replica at the three widths'` add `assert.equal(opts.theme, 'graphite');`.
- In `'parseArgs: every flag, …'` add `'--theme', 'navy'` to the argv and `assert.equal(opts.theme, 'navy');`.
- In `'parseArgs: unknown flags, missing values and bad widths throw'` add:

```js
  assert.throws(() => parseArgs(['--theme', 'blue']), /unknown theme blue/);
  assert.throws(() => parseArgs(['--theme', 'NAVY']), /unknown theme NAVY/);
  assert.throws(() => parseArgs(['--theme']), /incomplete flag --theme/);
```

- In `'countByCheck counts every check, zero included'` the expected object gains `'profile-menu': 0`.
- Append:

```js
test('the theme is seeded under the SPA key, and Navy output is told apart by a suffix', () => {
  assert.equal(THEME_KEY, 'ui.theme');
  assert.deepEqual([...THEMES], ['graphite', 'navy']);
  assert.equal(themeSuffix('graphite'), '');
  assert.equal(themeSuffix('navy'), '-navy');
});

test('PROFILE_MENU_MAX_WIDTH: the menu check runs at the phone width only of the three', () => {
  assert.deepEqual(FULL_WIDTHS.filter((w) => w <= PROFILE_MENU_MAX_WIDTH), [390]);
  assert.equal(PROFILE_MENU_MAX_WIDTH, RAIL_MIN_WIDTH - 1);
});

const VIEW = { width: 390, height: 900 };
const MENU = { left: 150, right: 382, top: 56, bottom: 420 };

test('profileMenuVerdict: an opened menu inside the viewport with two 44px theme segments passes', () => {
  assert.deepEqual(profileMenuVerdict({ menu: MENU, segments: [60, 88], viewport: VIEW }), { ok: true, reason: null });
  assert.deepEqual(profileMenuVerdict({ menu: { ...MENU, right: 390.4 }, segments: [44, 44], viewport: VIEW }), { ok: true, reason: null });
});

test('profileMenuVerdict: not opened, off-screen, no theme row, then a narrow segment, first rule first', () => {
  assert.equal(profileMenuVerdict({ menu: null, segments: [], viewport: VIEW }).reason, 'menu-not-opened');
  assert.equal(profileMenuVerdict({ menu: { ...MENU, right: 402 }, segments: [], viewport: VIEW }).reason, 'menu-off-screen');
  assert.equal(profileMenuVerdict({ menu: { ...MENU, left: -8 }, segments: [60, 60], viewport: VIEW }).reason, 'menu-off-screen');
  assert.equal(profileMenuVerdict({ menu: MENU, segments: [60], viewport: VIEW }).reason, 'no-theme-row');
  assert.equal(profileMenuVerdict({ menu: MENU, segments: [60, 43], viewport: VIEW }).reason, 'segment-under-44');
});

test('every profile-menu reason names its element', () => {
  for (const reason of ['menu-not-opened', 'menu-off-screen', 'no-theme-row', 'segment-under-44']) {
    assert.match(PROFILE_MENU_SELECTORS[reason], /^sb-profile-menu /);
  }
});

test('the audit seeds the theme before any page script, and checks it took', () => {
  const src = readFileSync(join(HERE, 'layout-audit.mjs'), 'utf8');
  assert.match(src, /addInitScript\(/);
  assert.match(src, /THEME_KEY/);
  assert.match(src, /dataset\.theme/);
  assert.match(src, /profileMenuVerdict/);
});
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `node --test "<wt>/frontend/scripts/layout-audit-lib.test.mjs"`
Expected: FAIL. The new imports are undefined, `CHECKS` has ten entries, `parseArgs(['--theme', 'blue'])` throws `unknown or incomplete flag --theme`.

- [ ] **Step 3: Implement in `layout-audit-lib.mjs`**

- `CHECKS` gains `'profile-menu'` as its last entry.
- After `FULL_WIDTHS`:

```js
/** The two SPA grounds (spec v225); the audit seeds one into localStorage before load. */
export const THEMES = Object.freeze(['graphite', 'navy']);
/** The SPA's own key (ui/theme.service.ts THEME_PREF_KEY). */
export const THEME_KEY = 'ui.theme';
/** Navy runs write `<slug>@<width>-navy.png` and their own out dir, so both themes' shots sit side by side. */
export const themeSuffix = (theme) => (theme === 'navy' ? '-navy' : '');
```

- `DEFAULTS` gains `theme: 'graphite'`. `FLAGS` gains:

```js
  '--theme': (opts, value) => {
    if (!THEMES.includes(value)) throw new Error(`unknown theme ${value}`);
    opts.theme = value;
  },
```

- After `DOCK_SELECTORS`/`dockVerdict`, the profile-menu check, judged the same way (reuse the module's `outsideViewport` and `DOCK_EDGE_SLACK_PX`):

```js
/** The profile menu holds the phone's only theme switch (spec v225), so at phone widths the audit
 *  opens it: below RAIL_MIN_WIDTH, i.e. 390 of the three widths. */
export const PROFILE_MENU_MAX_WIDTH = RAIL_MIN_WIDTH - 1;

const PROFILE_MENU_RULES = Object.freeze([
  ['menu-not-opened', (f) => !f.menu],
  ['menu-off-screen', (f) => outsideViewport(f.menu, f.viewport)],
  ['no-theme-row', (f) => f.segments.length < 2],
  ['segment-under-44', (f) => f.segments.some((width) => width < MIN_TAP_PX - DOCK_EDGE_SLACK_PX)],
]);

export const PROFILE_MENU_SELECTORS = Object.freeze({
  'menu-not-opened': 'sb-profile-menu [role=menu]',
  'menu-off-screen': 'sb-profile-menu [role=menu]',
  'no-theme-row': 'sb-profile-menu .theme-control',
  'segment-under-44': 'sb-profile-menu .theme-control .segment',
});

/** Verdict on `{ menu, segments, viewport }`: the opened menu's rect (or null), the widths of the
 *  Theme row's segments, the viewport size. Runs in Node on measured numbers. */
export function profileMenuVerdict(facts) {
  const broken = PROFILE_MENU_RULES.find(([, fails]) => fails(facts));
  return broken ? { ok: false, reason: broken[0] } : { ok: true, reason: null };
}
```

`RAIL_MIN_WIDTH` and `MIN_TAP_PX` are declared above this point in the file; if `RAIL_MIN_WIDTH` is declared later, place this block after it.

- [ ] **Step 4: Implement in `layout-audit.mjs`**

- Import `PROFILE_MENU_MAX_WIDTH, PROFILE_MENU_SELECTORS, THEME_KEY, profileMenuVerdict, themeSuffix` from the lib.
- `withContext(width, theme, fn)`: after `launchPersistentContext`, seed the theme on every document before any page script (the persistent profile may hold the other value):

```js
  await context.addInitScript(([key, value]) => {
    try { localStorage.setItem(key, value); } catch { /* blocked storage: the check below reports it */ }
  }, [THEME_KEY, theme]);
```

  Every caller passes `opts.theme` (`main()`'s id lookup at 1440 and `auditWidth`).
- In `auditWidth`, after the first `page.goto(...)` and ready wait of the run, check the seed took, else stop the run as `CannotRun`:

```js
      const applied = await page.evaluate(() => document.documentElement.dataset.theme ?? null);
      if ((opts.theme === 'navy') !== (applied === 'navy')) {
        throw new CannotRun(`--theme ${opts.theme} did not apply at ${width}px (data-theme=${applied})`);
      }
```

  (Do it for the first route only; a flag `checked` local to `auditWidth` keeps it to one evaluate.)
- Screenshot names: `` `${slug(route)}@${width}${themeSuffix(opts.theme)}.png` ``.
- New check, after `auditDock` in the route loop, once per width on `ROUTES[0]` and only when `width <= PROFILE_MENU_MAX_WIDTH`:

```js
/** Runs inside the page: the open profile menu's rect and its Theme segments' widths. Self-contained. */
function measureProfileMenu() {
  const r = document.querySelector('sb-profile-menu [role=menu]')?.getBoundingClientRect();
  const root = document.documentElement;
  return {
    menu: r && r.width > 0 && r.height > 0 ? { left: r.left, right: r.right, top: r.top, bottom: r.bottom } : null,
    segments: [...document.querySelectorAll('sb-profile-menu .theme-control .segment')].map((s) => s.getBoundingClientRect().width),
    viewport: { width: root.clientWidth, height: root.clientHeight },
  };
}

/** Tap the avatar, measure the open menu, keep a shot of it, close it with Escape (spec v225). */
async function auditProfileMenu(page, width, opts) {
  try {
    await page.locator('sb-profile-menu .avatar').tap({ timeout: 2000 });
  } catch (error) {
    console.error(`  profile menu @${width}: cannot tap (${String(error).split('\n')[0]})`);
  }
  await page.locator('sb-profile-menu [role=menu]').waitFor({ state: 'visible', timeout: 5000 }).catch(() => null);
  await page.waitForTimeout(SHEET_SETTLE_MS);
  const facts = await page.evaluate(measureProfileMenu);
  await page.screenshot({ path: join(opts.out, `profile-menu@${width}${themeSuffix(opts.theme)}.png`) });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(SHEET_SETTLE_MS);
  const verdict = profileMenuVerdict(facts);
  if (verdict.ok) return [];
  return [{ check: 'profile-menu', selector: PROFILE_MENU_SELECTORS[verdict.reason], text: '', detail: `profile menu ${verdict.reason} at ${width}px` }];
}
```

  In the loop: `const menus = width <= PROFILE_MENU_MAX_WIDTH && route === ROUTES[0] ? await auditProfileMenu(page, width, opts) : [];` and spread `...menus` into the same `findings.push` and the raw-count log line as `hints`, `rails` and `docks`.
- `setUp`: the default out becomes `` join(tmpdir(), `swingbot-layout-audit${themeSuffix(opts.theme)}`) ``.
- `main()`: `audit.json` gains `theme: opts.theme` after `widths`; `report()`'s first line becomes `` `layout audit ${opts.base} @ ${opts.widths.join(',')} (${opts.theme}): …` ``.
- Usage docstring: the command line gains `[--theme graphite|navy]`; add a check line `profile-menu  at widths below 640 the profile menu, opened from sb-profile-menu .avatar, must sit inside the viewport and its Theme row show two segments at least 44px wide (spec v225). Never allowed.`; add a sentence: "`--theme navy` seeds `ui.theme` before every page load (default graphite) and stops with exit 2 when the page does not come up in that theme; Navy shots and the default out dir carry a `-navy` suffix."

- [ ] **Step 5: Run the tests to see them pass**

Run: `node --test "<wt>/frontend/scripts/layout-audit-lib.test.mjs"` and `node --check "<wt>/frontend/scripts/layout-audit.mjs"`
Expected: every test passes (`# fail 0`); `--check` prints nothing. The real browser run is V225-12.

- [ ] **Step 6: Commit**

```bash
git -C "<wt>" add frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit.mjs frontend/scripts/layout-audit-lib.test.mjs
git -C "<wt>" commit -m "feat(v225): layout audit --theme graphite|navy, and the open profile menu checked at phone widths (V225-11)"
```

### Task V225-12: Both-theme layout audit at 390/768/1440 and the canvas screenshots

**Model:** sonnet — runs the audit twice and a scripted screenshot pass against a local instance; judgement is limited to reading four chart shots and two menu shots.

**Files:**
- Create (scratch, never committed): `<scratchpad>/v225_equity_shots.mjs`
- Output (git-ignored, under `<main>` so it outlives the worktree): `<main>/.superpowers/v225-shots/` (the four chart shots), `<main>/.superpowers/v225-audit-graphite.log`, `<main>/.superpowers/v225-audit-navy.log`
- Modify: none planned. A finding is fixed in the file of the task that owns it (V225-1 tokens, V225-6 bar button, V225-7 menu row, V225-9/V225-10 charts), as its own scoped `fix(v225): …` commit, never in `frontend/scripts/layout-audit.allow.json`.

**Interfaces:**
- Consumes: every task V225-1..V225-11 committed on the worktree branch; `layout-audit.mjs --theme graphite|navy` and its `profile-menu` check (V225-11); `header.topbar button.theme-toggle` (V225-6); `sb-profile-menu .avatar` and `.theme-control .segment` labelled `Black` / `Dark blue` (V225-7); the Dashboard's `sb-equity-candles` (V225-10).
- Produces: two clean audit logs and four screenshots, listed in the report for the implementation's review (spec § Testing, "Canvas check").

Rules: `.env` credentials are loaded only inside `browse.mjs` (never printed, echoed or logged); no full-suite run.

- [ ] **Step 1: Bring up the local instance**

Run `/replicate-prod-db` first if no task in this session has (shared `swing-db`, port 56789). Then:

```bash
cd "<wt>/frontend" && npm run build
```

Start `python "<wt>/admin_ui.py"` with `run_in_background`, wait until `http://localhost:1234` answers, then sign the Playwright profile in once:

```bash
node "<wt>/frontend/scripts/browse.mjs" login --base http://localhost:1234
```

Expected: the build succeeds; `login` reports a session without printing any credential.

- [ ] **Step 2: Run the audit in both themes**

Each run covers 390, 768 and 1440 (the default widths). Start each with `run_in_background` and wait for its exit notification; never poll:

```bash
node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234 --theme graphite > "<main>/.superpowers/v225-audit-graphite.log" 2>&1; echo "exit $?"
node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234 --theme navy > "<main>/.superpowers/v225-audit-navy.log" 2>&1; echo "exit $?"
```

Expected: `exit 0` twice. Each log's summary line names its theme (`(graphite)` / `(navy)`) and shows `profile-menu=0`. Read only the summary and any `FAIL` lines (`grep -n "layout audit\|FAIL\|cannot run" <log>`), never the whole log.

- An `exit 2` with `--theme navy did not apply`: the pre-paint script (V225-4) or the service boot (V225-3) is broken; fix there and rerun.
- A `FAIL`: fix it in the owning file, run that task's narrow spec command, commit `fix(v225): <what> (V225-12)`, rebuild (`npm run build`), and rerun **that theme's** audit until it exits 0. A finding in one theme only is still a defect.

Then read the two menu shots the audit wrote: `<tmp>/swingbot-layout-audit/profile-menu@390.png` and `<tmp>/swingbot-layout-audit-navy/profile-menu@390-navy.png` (`<tmp>` is the OS temp dir). Expected: the open menu fits the 390px viewport with the Theme row under Density, segments Black | Dark blue, the pressed one in the accent look.

- [ ] **Step 3: Write the canvas screenshot script**

The layout audit cannot see canvas pixels, so this pass toggles with the Dashboard equity chart already mounted and keeps one shot per theme at 390 and 1440. Write `<scratchpad>/v225_equity_shots.mjs`:

```js
// v225 canvas check: Dashboard equity candles at 390 and 1440, toggled with the chart mounted.
// node <scratchpad>/v225_equity_shots.mjs <wt> <out-dir>
import { mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';

const [wt, out] = process.argv.slice(2);
const { chromium } = createRequire(join(wt, 'frontend', 'package.json'))('playwright');
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const BASE = 'http://localhost:1234';
mkdirSync(out, { recursive: true });

async function toggle(page, width, to) {
  if (width >= 640) {
    await page.locator('header.topbar button.theme-toggle').click();
  } else {
    await page.locator('sb-profile-menu .avatar').tap();
    await page.locator('sb-profile-menu .theme-control .segment', { hasText: to === 'navy' ? 'Dark blue' : 'Black' }).tap();
    await page.keyboard.press('Escape');
  }
  await page.waitForFunction((want) => (document.documentElement.dataset.theme ?? 'graphite') === want, to);
  await page.waitForTimeout(600);
}

/** The chart ground straight off the canvas, 6px in from the pane's top-left corner. */
const groundPixel = (page) => page.evaluate(() => {
  const canvas = document.querySelector('sb-equity-candles canvas');
  const [r, g, b] = canvas.getContext('2d').getImageData(6, 6, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
});

for (const width of [390, 1440]) {
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: true, viewport: { width, height: 900 }, deviceScaleFactor: 1, serviceWorkers: 'block',
    hasTouch: width <= 1023, isMobile: width < 640,
  });
  await context.addInitScript(() => { try { localStorage.setItem('ui.theme', 'graphite'); } catch { /* reported below */ } });
  const page = context.pages()[0] ?? (await context.newPage());
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'load' });
  await page.locator('sb-equity-candles canvas').first().waitFor({ state: 'visible', timeout: 30_000 });
  await page.waitForTimeout(1500);
  const chart = page.locator('sb-equity-candles');
  for (const [theme, name] of [['navy', 'dark-blue'], ['graphite', 'black']]) {
    await toggle(page, width, theme);
    await chart.scrollIntoViewIfNeeded();
    await chart.screenshot({ path: join(out, `equity-candles@${width}-${name}.png`) });
    console.log(`${width} ${name}: ground ${await groundPixel(page)}`);
  }
  await context.close();
}
```

- [ ] **Step 4: Take the four shots**

```bash
node "<scratchpad>/v225_equity_shots.mjs" "<wt>" "<main>/.superpowers/v225-shots"
```

Expected: four lines. Both `dark-blue` lines print `ground rgb(12, 20, 36)` (Navy `--surface` `#0c1424`) and both `black` lines print `ground rgb(21, 24, 29)` (Graphite `--surface` `#15181d`). If a printed pixel is a grid line or a candle instead of the ground, move the sample point (say so in the report) rather than accept a mismatch. Then read the four PNGs in `<main>/.superpowers/v225-shots/`: in each, the chart ground, grid, axis text, the seam line and its label, and the candle colours belong to the shot's theme, with no strip of the other ground. The Black pair also proves the flip back (Review Focus 4).

- [ ] **Step 5: Stop the instance and report**

Stop the background `admin_ui.py`. Nothing is committed in this task unless Step 2 needed a fix. The report lists both audit logs' summary lines, the two menu shots, the four chart shots with their printed ground pixels, and every `fix(v225)` commit hash, for the implementation's review.

# Phase F — release

### Task V225-13: Release (ui minor), version history, partner gate, merge, CI watch

**Model:** sonnet — a scripted release and a gated merge with read-only production checks; every figure is generated, none judged.

**Files:**
- Modify: `VERSION.json` (`ui` minor + 1, patch 0; `bot` unchanged)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: every task V225-1..V225-12 committed on branch `2026-11-10-v225-dark-blue-theme`, and V225-12's two clean audit logs and four shots.
- Produces: the released and deployed ui version.

**Gates (in this order, none skipped):**

1. **Partner approval before anything reaches `main`.** A push to `main` deploys to production by itself (CI → Hetzner, `docs/deploy/DEPLOY_HETZNER.md`). The merge and the push wait for the partner's explicit yes in Step 5, asked through `AskUserQuestion`. No yes: no merge, no push; the branch stays as it is and the task stops.
2. **`mirror-prod` rules.** The deploy is the CI pipeline; nothing is changed by hand on the VM. Production is touched read-only, only through `bash scripts/ops/ssh-hetzner.sh` (standing permission). If anything on the VM has to change by hand, stop, invoke `mirror-prod`, and mirror and commit the change before this task counts as done.
3. **No full-suite run here.** CI runs it after the push (Step 7).

- [ ] **Step 1: Check the preconditions**

```bash
git -C "<wt>" log --oneline main..HEAD
git -C "<wt>" status --short
grep -c "exit 0\|layout audit" "<main>/.superpowers/v225-audit-graphite.log" "<main>/.superpowers/v225-audit-navy.log"
ls "<main>/.superpowers/v225-shots/"
```

Expected: commits naming V225-1 through V225-11 (plus any `fix(v225)` from V225-12); a clean status; both audit logs present with a `0 unallowed` summary; four `equity-candles@*.png` files. Anything missing: stop and finish V225-12 first.

- [ ] **Step 2: Narrow verification of everything this plan touched**

One command per runner, logs under `<wt>/.superpowers/` (never the full suite):

```bash
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/ui/tokens.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/theme.service.spec.ts --include src/app/ui/icon.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/shell/palette/command-palette.spec.ts --include src/app/ui/chart/trade-chart.spec.ts --include src/app/ui/chart/primitives/legend-primitive.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts > "<wt>/.superpowers/v225-ng.log" 2>&1 && echo "PASS ng" || echo "FAIL ng"
node --test "<wt>/frontend/scripts/layout-audit-lib.test.mjs" > "<wt>/.superpowers/v225-audit-lib.log" 2>&1 && echo "PASS audit-lib" || echo "FAIL audit-lib"
cd "<wt>" && python scripts/dev/dump_tokens.py --check && echo "PASS fixture"
cd "<wt>" && for t in tests/dev/test_dump_tokens.py tests/charts/test_chart_theme.py; do python scripts/dev/testrun.py file "$t" > "<wt>/.superpowers/v225-$(basename "$t" .py).log" 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
```

Expected: `PASS ng`, `PASS audit-lib`, `PASS fixture`, two `PASS tests/...` lines. A `FAIL`: read only that log's failing test names and assertion lines, fix, rerun that one file alone, commit the fix scoped.

- [ ] **Step 3: Bump `ui` by one minor**

`VERSION.json` may be checked out with CRLF line endings; the script keeps whatever the file has and reads the current value rather than assuming it:

```bash
python - "<wt>/VERSION.json" <<'EOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path = Path(sys.argv[1])
raw = path.read_bytes()
nl = "\r\n" if b"\r\n" in raw else "\n"
data = json.loads(raw.decode("utf-8"))
major, minor, _patch = (int(x) for x in data["ui"].split("."))
data["ui"] = f"{major}.{minor + 1}.0"
data["ui_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_bytes((json.dumps(data, indent=2).replace("\n", nl) + nl).encode("utf-8"))
print("ui", data["ui"], "| bot", data["bot"])
EOF
git -C "<wt>" diff --stat VERSION.json
```

Expected: `ui <major>.<minor+1>.0 | bot <unchanged>` (from `ui 1.40.5` that is `1.41.0`, unless another release landed first), and the diff touches 2 lines. If it shows the whole file, restore with `git -C "<wt>" checkout VERSION.json` and match the original format. Commit:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(ui): <new ui> -- Dark blue theme beside Black, picked per browser (v225)"
```

- [ ] **Step 4: Regenerate the version history and check it**

The generator walks `git log` for `VERSION.json`, so it runs after the release commit:

```bash
cd "<wt>" && python scripts/dev/build_version_matrix.py
cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C "<wt>" add swingbot/admin/version_history.json
git -C "<wt>" commit -m "chore(ui): <new ui> -- version history (v225)"
```

Expected: the test passes; `git -C "<wt>" show --stat HEAD` lists only `swingbot/admin/version_history.json`, and its newest entry is the new ui version, never `"commit": "uncommitted"`.

- [ ] **Step 5: Deploy gate: ask the partner**

Ask through `AskUserQuestion`, one question, recommended option first:

- Question: "v225 is released on its branch (ui <new ui>, bot unchanged; narrow tests green; layout audit clean in both themes at 390/768/1440; four equity-chart shots in `.superpowers/v225-shots/`). Merging into `main` and pushing deploys it to production through CI. Deploy now?"
- Options: "Merge and deploy now (Recommended)" / "Not yet: leave the branch unmerged".

"Not yet": stop and report the branch head and the new ui version. Any other answer is not a yes: ask again or stop.

- [ ] **Step 6: Merge into `main` and push (only after the yes)**

Invoke the `worktree-lifecycle` skill for the merge, because another session may be committing on `main`. Then:

```bash
git -C "<main>" fetch origin
git -C "<main>" status --short --branch
git -C "<main>" log --oneline -1 origin/main
```

Expected: `main` is not behind `origin/main` (pull `--ff-only` first if it is), and no uncommitted change in `<main>` touches a file this plan changed. Another session's uncommitted files stay as they are; never stash or reset them.

```bash
git -C "<main>" merge --no-ff 2026-11-10-v225-dark-blue-theme -m "merge: v225 -- Dark blue theme beside Black, picked per browser"
git -C "<main>" push origin main
```

- [ ] **Step 7: Watch the pipeline**

```bash
gh run list --branch main --limit 1 --json databaseId,status,conclusion
```

Run `gh run watch <id> --exit-status` with `run_in_background` and wait for its exit notification (do not poll). Green: continue. Red: `gh run view <id> --log-failed > "<scratchpad>/v225-ci.log"`, read only the failing test names and assertion lines, fix each in `<main>` (one file at a time with `testrun.py file` or `ng-test.mjs --include`), commit scoped, push, watch again (`working-conventions.md` § Pipeline watch). Each fix push deploys too; the Step 5 yes covers fixes to this release only.

- [ ] **Step 8: Confirm production serves the new bundle (read-only)**

The deploy follows a green run by itself:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c \"import json, pathlib; print(json.loads(pathlib.Path('VERSION.json').read_text())['ui'])\""
curl -s https://bomeo-capital.com/app/ | grep -c "NAVY_BG"
```

Expected: the new ui version, and a count of `1` (the pre-paint script from V225-4 is in the served `index.html`). An old version or `0`: the deploy has not landed; wait a few minutes and repeat. If `/app/` does not serve the SPA index, curl the route the admin container serves `index.html` from (`docs/deploy/DEPLOY_HETZNER.md`) instead. Never change anything on the VM.

The plan's `/close-out` follows this task (standing permission, `CLAUDE.md`); it is not a step here.
