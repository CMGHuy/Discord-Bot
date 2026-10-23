# v186 — UI foundation refresh, part 2: figure face and strip migrations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v186-ui-foundation-refresh-design.md](../specs/2026-10-23-v186-ui-foundation-refresh-design.md) (D3 Migration, D4)
**Index:** [2026-10-23-v186-ui-foundation-refresh_0-index.md](2026-10-23-v186-ui-foundation-refresh_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

All paths are relative to the worktree root `.claude/worktrees/2026-10-23-v186-ui-foundation-refresh` (created in V186-1). Frontend commands run from its `frontend/` directory, exactly as the index's Global Constraints give them. A Vitest "Timeout waiting for worker to respond" at 60 s is machine load: re-run the same command. If `ng test` rejects a repeated `--include`, run one `--include` per command.

**Edits are anchored on rule text, not line numbers.** Part 1 (V186-2, V186-3) edits the same files first; a line number quoted from `main` at `a5cf0434` may have moved, the rule text named in each step has not.

# Phase 3 — One figure face (D4)

### Task V186-5: One figure face at the five display-figure sites

**Model:** sonnet — five components and their specs, specificity-sensitive CSS edits with source-text tests.

**Files:**
- Modify: `frontend/src/app/ui/stat-tile.ts` (the `.value` rule)
- Modify: `frontend/src/app/ui/stat-tile.spec.ts` (`StatTile: one variant everywhere (v179 §3.3)` describe)
- Modify: `frontend/src/app/ui/figure.ts` (`Figure` template and the `.value` rule)
- Modify: `frontend/src/app/ui/figure.spec.ts`
- Modify: `frontend/src/app/ui/metric-card.ts` (template `.value` span and the `.value` rule)
- Modify: `frontend/src/app/ui/metric-card.spec.ts`
- Modify: `frontend/src/app/ui/panel-header.ts` (template `.total` span and the `.total` rule)
- Modify: `frontend/src/app/ui/panel-header.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts` (`.figure` and `.figure.muted` rules)
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`

**Interfaces:**
- Consumes (V186-1): tier-2 tokens `--font-figure: var(--font-sans)`, `--figure-weight: 600`, `--figure-tracking: -0.02em` in `frontend/src/styles/tokens.css`.
- Consumes (V186-2): `panel-header.ts` with the new `h2` title and `.n, .all-time` in `--text-muted`. This task touches only the `.total` rule and the `.total` span, never the `h2` or `.n` rules.
- Consumes (V186-3): `stat-tile.ts` / `metric-card.ts` with the custom-property reads, `class="label sb-label"` labels and no `--text-faint`. This task touches only the `.value` rule and the `.value` span.
- Produces: the **figure-face block**, four declarations written in this order in every display-figure rule:
  ```css
  font-family: var(--font-figure);
  font-weight: var(--figure-weight);
  letter-spacing: var(--figure-tracking);
  font-variant-numeric: tabular-nums;
  ```
  V186-10's faint-text scan reads `portfolio-value.ts` and relies on `.figure.muted { color: var(--text-muted); }`.

Why each rule is edited in place: a global class `.x` (0,1,0) loses to a scoped `.value[_ngcontent-…]` (0,2,0), and the global `.num` class (`frontend/src/styles.css`, `.num { font-family: var(--font-num); … }`) on the same element would reassert mono. So the block goes into each component's own rule, and `num` leaves the three templates that put it on a display figure. Table cells, `N=`, secondary lines and `.sub` keep `--font-num`.

- [ ] **Step 1: Write the failing tests**

(a) `frontend/src/app/ui/stat-tile.spec.ts`: inside `describe('StatTile: one variant everywhere (v179 §3.3)', …)`, **replace** the whole test `it('sets the value, the secondary and N= in the numeric face', …)` with these two tests (the helpers `SOURCE`, `rule` and `render` already exist in that describe; `readFileSync` and `join` are already imported):

```ts
  it('sets the value in the figure face and the secondary and N= in the numeric face (v186 D4)', () => {
    const value = rule('.value');
    expect(value).toContain('font-family: var(--font-figure);');
    expect(value).toContain('font-weight: var(--figure-weight);');
    expect(value).toContain('letter-spacing: var(--figure-tracking);');
    expect(value).toContain('font-variant-numeric: tabular-nums;');
    expect(value).not.toContain('var(--font-num)');
    expect(SOURCE).toMatch(/\.sample, \.secondary \{ font-family: var\(--font-num\); \}/);
    const el = render({ secondary: '+1,240.00 €', sample: 412 });
    expect(el.querySelector('.value')!.classList).not.toContain('num');
    expect(el.querySelector('.secondary')!.classList).toContain('num');
  });

  it('leaves table cells in the numeric face (v186 D4 scope)', () => {
    const table = readFileSync(join(process.cwd(), 'src/app/ui/data-table/data-table.ts'), 'utf8');
    const global = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
    expect(table).toMatch(/<td \[class\.num\]="col\.numeric"/);
    const numRule = global.match(/\n\.num \{[^}]*\}/)?.[0] ?? '';
    expect(numRule).toContain('font-family: var(--font-num);');
  });
```

(b) `frontend/src/app/ui/figure.spec.ts`: add a new first line above the existing first import line:

```ts
import { readFileSync } from 'node:fs'; import { join } from 'node:path';
```

and append at the end of the file:

```ts
describe('Figure face (v186 D4)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/figure.ts'), 'utf8');

  it('sets the value in the figure face, not the code face', () => {
    // The first ` .value {` is the base rule; the @container one only resizes.
    const rule = SOURCE.match(/\s\.value \{[^}]*\}/)![0];
    expect(rule).toContain('font-family: var(--font-figure);');
    expect(rule).toContain('font-weight: var(--figure-weight);');
    expect(rule).toContain('letter-spacing: var(--figure-tracking);');
    expect(rule).toContain('font-variant-numeric: tabular-nums;');
    expect(rule).not.toContain('--font-mono');
    expect(rule).not.toContain('font-weight: 500');
  });

  it('drops the global num class from the value and keeps it on the sub line', () => {
    const e = figure(1.2, 'pnl', { sub: 'n = 184' });
    const value = e.querySelector('.value')!;
    expect(value.classList).not.toContain('num');
    expect(value.classList).toContain('pos');
    expect(e.querySelector('.sub')!.classList).toContain('num');
  });
});
```

(c) `frontend/src/app/ui/metric-card.spec.ts`: add at the top, above `import { provideZonelessChangeDetection } from '@angular/core';`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

```

and append at the end of the file:

```ts
describe('sb-metric-card figure face (v186 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/metric-card.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  /** The rule whose selector starts a line, so `.value` is not `:host(.loading) .value`. */
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('sets the value in the figure face at weight 600, not 700', () => {
    const value = rule('.value');
    expect(value).toContain('font-family: var(--font-figure);');
    expect(value).toContain('font-weight: var(--figure-weight);');
    expect(value).toContain('letter-spacing: var(--figure-tracking);');
    expect(value).toContain('font-variant-numeric: tabular-nums;');
    expect(value).not.toContain('font-weight: 700');
    // The density register still sizes the figure.
    expect(value).toContain('font-size: var(--register-figure, var(--text-metric));');
  });

  it('drops the global num class from the value and keeps it on the sub line', () => {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Expectancy');
    f.componentRef.setInput('value', 0.42);
    f.componentRef.setInput('sub', 'N=31');
    f.detectChanges();
    const host = f.nativeElement as HTMLElement;
    expect(host.querySelector('.value')!.classList).not.toContain('num');
    expect(host.querySelector('.sub')!.classList).toContain('num');
  });
});
```

(d) `frontend/src/app/ui/panel-header.spec.ts` (already imports `readFileSync`, `join`, `TestBed`, `provideZonelessChangeDetection`, `PanelHeader`): append at the end of the file:

```ts
describe('PanelHeader total (v186 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');

  it('sets the total in the figure face at chip size, secondary colour', () => {
    const total = SOURCE.match(/\.total \{[^}]*\}/)![0];
    expect(total).toContain('font-family: var(--font-figure);');
    expect(total).toContain('font-weight: var(--figure-weight);');
    expect(total).toContain('letter-spacing: var(--figure-tracking);');
    expect(total).toContain('font-variant-numeric: tabular-nums;');
    expect(total).toMatch(/font-size:\s*var\(--text-chip\)/);
    expect(total).toMatch(/color:\s*var\(--text-secondary\)/);
  });

  it('drops the global num class from the total', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.componentRef.setInput('total', '+$1,240');
    fixture.detectChanges();
    const total = (fixture.nativeElement as HTMLElement).querySelector('.total')!;
    expect(total.textContent).toBe('+$1,240');
    expect(total.classList).not.toContain('num');
  });
});
```

(e) `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`: add at the top, above `import { provideZonelessChangeDetection } from '@angular/core';`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

```

and append at the end of the file:

```ts
describe('portfolio figure face (v186 D4)', () => {
  const SOURCE = readFileSync(
    join(process.cwd(), 'src/app/workspaces/dashboard/panels/portfolio-value.ts'),
    'utf8',
  );

  it('tracks the hero figure like every display figure, keeping its Inter 600 title size', () => {
    const figure = SOURCE.match(/\n\s*\.figure \{[^}]*\}/)![0];
    expect(figure).toContain('letter-spacing: var(--figure-tracking);');
    expect(figure).toContain('font-weight: 600;');
    expect(figure).toContain('font-size: var(--text-title);');
    expect(figure).toContain('font-variant-numeric: tabular-nums;');
  });

  it('shows the missing-balance dash in a readable colour', () => {
    expect(SOURCE).toMatch(/\.figure\.muted \{ color: var\(--text-muted\); \}/);
    expect(SOURCE).not.toMatch(/color:\s*var\(--text-faint\)/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/stat-tile.spec.ts --include src/app/ui/figure.spec.ts --include src/app/ui/metric-card.spec.ts --include src/app/ui/panel-header.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
```
Expected: FAIL. The figure-face tests in all five files fail (`font-family: var(--font-figure);` or `letter-spacing: var(--figure-tracking);` not found), the three "drops the global num class" tests in figure, metric-card and panel-header fail (`num` still on `.value` / `.total`), and "shows the missing-balance dash in a readable colour" fails. The stat-tile figure-face test fails on the source check before it reaches the DOM checks. "leaves table cells in the numeric face" already PASSES (it guards scope). Every other test passes.

- [ ] **Step 3: Rewrite the five rules and the three templates**

(a) `frontend/src/app/ui/stat-tile.ts`: the `.value` rule becomes:

```css
    .value {
      font-family: var(--font-figure);
      font-weight: var(--figure-weight);
      letter-spacing: var(--figure-tracking);
      font-variant-numeric: tabular-nums;
      font-size: var(--text-metric);
      color: var(--text);
      overflow-wrap: anywhere;
    }
```

The template's value `div` has no `num` class today; leave the template alone.

(b) `frontend/src/app/ui/figure.ts`: in the `Figure` template change `<span class="value num" [class]="toneClass()"` to `<span class="value" [class]="toneClass()"` (the `<span class="sub num">` keeps `num`). In the `Figure` styles string, the base rule

```css
.value { font-family: var(--font-mono); font-size: var(--register-figure, var(--text-metric)); font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.1; white-space: nowrap; }
```

becomes

```css
.value { font-family: var(--font-figure); font-weight: var(--figure-weight); letter-spacing: var(--figure-tracking); font-variant-numeric: tabular-nums; font-size: var(--register-figure, var(--text-metric)); line-height: 1.1; white-space: nowrap; }
```

The `@container figures (max-width: 639px) { … .value { font-size: var(--text-title); } }` rule is unchanged. `FigureStrip` is not touched.

(c) `frontend/src/app/ui/metric-card.ts`: in the template change

```html
      <span class="value num" [class]="valueClass()" [sbCountUp]="value()"
```

to

```html
      <span class="value" [class]="valueClass()" [sbCountUp]="value()"
```

(`<span class="sub num" …>` keeps `num`). In the styles, the `.value` rule becomes (both comments kept, `font-weight: 700` replaced):

```css
    .value {
      font-family: var(--font-figure);
      font-weight: var(--figure-weight);
      letter-spacing: var(--figure-tracking);
      font-variant-numeric: tabular-nums;
      /* v54 D1: the register class on an ancestor panel/workspace sets
         --register-figure to the rung its density picked; the fallback is
         what this card rendered before the registers existed, so a card with
         no register ancestor (not yet migrated, or deliberately opted out)
         is unchanged. v186 D4: Inter 600 like every display figure (was 700
         in the code face). */
      font-size: var(--register-figure, var(--text-metric));
      line-height: 1.1;
      /* v168: the number counts up once when the route is entered, and eases
         to a new value when a push changes it -- 900ms, scoped to this one
         number, and only under Motion = On (CountUp). It never re-counts on a
         refetch, so a glance still reads a settled number. */
    }
```

(d) `frontend/src/app/ui/panel-header.ts`: in the template change `@if (total()) { <span class="total num">{{ total() }}</span> }` to `@if (total()) { <span class="total">{{ total() }}</span> }`. In the one-line styles string replace the `.total { … }` rule (on `main` today: `.total { font-size:var(--text-chip); color:var(--text-secondary); }`) with:

```css
.total { font-family: var(--font-figure); font-weight: var(--figure-weight); letter-spacing: var(--figure-tracking); font-variant-numeric: tabular-nums; font-size: var(--text-chip); color: var(--text-secondary); }
```

Do not touch the `header`, `.heading`, `h2`, `.n,.all-time` rules or the `@media (pointer: coarse), (max-width: 1023px)` block: `panel-header.spec.ts`'s alignment regexes and V186-2 own them.

(e) `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts`: the `.figure` rule gains one declaration after `font-weight: 600;`, and `.figure.muted` moves to `--text-muted`:

```css
    .figure {
      margin: 0;
      font-size: var(--text-title);
      font-weight: 600;
      letter-spacing: var(--figure-tracking);
      color: var(--text);
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
      /* v95 A5: the figure is one number -- wrapped, it reads as several. */
      white-space: nowrap;
    }
    .figure.muted { color: var(--text-muted); }
```

The hero already inherits Inter (`--font-sans`) at 600; spec D4 changes only its tracking and the dash colour.

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/stat-tile.spec.ts --include src/app/ui/figure.spec.ts --include src/app/ui/metric-card.spec.ts --include src/app/ui/panel-header.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
```
Expected: PASS, 0 failed.

- [ ] **Step 5: Run the specs that read these components' DOM or source**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/motion/count-up.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/vertical-centre.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```
Expected: PASS, 0 failed. `count-up.spec.ts` renders `sb-metric-card` and `sb-figure` and reads `.value`, not `.num`; `primitives.spec.ts` pins the `<div class="tile sb-lift"` / `<div class="card sb-lift">` lines and the `sb-figure-strip` host class, none of which this task touches. A failure here means an edit went beyond the `.value` / `.total` span and rule: undo that part, never edit the gate spec.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/stat-tile.spec.ts frontend/src/app/ui/figure.ts frontend/src/app/ui/figure.spec.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-card.spec.ts frontend/src/app/ui/panel-header.ts frontend/src/app/ui/panel-header.spec.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
git commit -F- <<'MSG'
feat(ui): v186 D4 one figure face for display numbers

Tile, figure, metric-card and panel-header totals read --font-figure /
--figure-weight / --figure-tracking with tabular digits in their own scoped
rules; num leaves those three templates. The portfolio hero gains the
tracking and its dash moves to --text-muted. Table cells and N= stay mono.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

# Phase 4 — Stat-strip migrations (D3 Migration)

### Task V186-6: Dashboard: Trading performance cards into a strip

**Model:** sonnet — one workspace panel with breakpoint CSS moving onto a new primitive's host, plus source-pinned spec rewrites.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (imports, the `<div class="grid" …>` wrapper, the `.grid` rules)
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts` (new describe; the two tablet-band tests rewritten)

**Interfaces:**
- Consumes (V186-4): `StatStrip` from `frontend/src/app/ui/stat-strip.ts`, selector `sb-stat-strip`, inputs `cols = input<number | null>(null)`, `colsMd = input<number>(2)`, host bindings `[style.--strip-cols]="cols()"` / `[style.--strip-cols-md]="colsMd()"`, template `<div class="sb-strip-grid" [class.sb-strip-fixed]="cols() !== null"><ng-content /></div>`; its `:host` sets `--figure-rule: 1px`, `--tile-bg: transparent`, `--tile-border: 0`, `--tile-radius: 0`, `--tile-tint-off: none`, `--panel-shadow-lift: none`. The global `.sb-strip-grid.sb-strip-fixed` rules in `frontend/src/styles.css` give 2 columns below 640 px, `--strip-cols-md` from 640 px and `--strip-cols` from 1024 px.
- Consumes (V186-3): `sb-metric-card` reads `--figure-rule`, `--tile-*` and `--tile-tint-off` on its own host, so the cards lose their frames and tints inside the strip with no change here.
- Produces: `<sb-stat-strip class="grid" [class.stale]="stale()" [cols]="4" [colsMd]="2">` as the KPI container. The class `grid` stays on the strip host, so the existing `.grid.stale` assertion, the ≤639 px `.grid { display: none; }` rule and the `.mobile-summary` fallback keep working unchanged.

**State check before editing.** On `main` at `a5cf0434` the `.grid` holds **8** `sb-metric-card`s (Risk used included). An uncommitted change seen on `main` the day this plan was written drops Risk used (7 cards), adds `[loading]` inputs and a rule `.grid > :last-child:nth-child(4n + 3) { grid-column: span 2; }`. Run `git grep -n "nth-child(4n + 3)" -- frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` in the worktree: Step 3(d) applies only if it prints a line. The tests below hold for either card count.

Why the class stays `grid`: Angular's emulated encapsulation tags the `sb-stat-strip` element with this component's `_ngcontent` attribute, because the element is written in this template. So `.grid.stale` (0,3,0) and `@media (max-width: 639px) { .grid { display: none; } }` (0,2,0) apply to the strip host and beat its `:host { display: block; }` (0,1,0). The cards themselves sit one level deeper now (`sb-stat-strip > div.sb-strip-grid > sb-metric-card`), so a `.grid > …` child rule no longer reaches them.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`:

(a) Inside `describe('trading-performance tablet band', …)`, **replace** the two tests `it('has a treatment between sm and md, not only below sm', …)` and `it('never leaves a four-track KPI grid below md', …)` with:

```ts
  it('has a treatment between sm and md, not only below sm', () => {
    // v186: the KPI strip's colsMd carries the tablet band. sb-stat-strip sets
    // --strip-cols-md and styles.css's .sb-strip-grid.sb-strip-fixed reads it
    // from 640 to 1023px, so iPad portrait gets two columns, not the 4-up floor.
    expect(src).toMatch(/<sb-stat-strip class="grid"[^>]*\[colsMd\]="2"/);
  });

  it('never leaves a four-track KPI grid below md', () => {
    expect(src).toMatch(/<sb-stat-strip class="grid"[^>]*\[cols\]="4"/);
    // The strip owns the columns; the panel declares no grid of its own.
    expect(src).not.toMatch(/\.grid\s*\{[^}]*grid-template-columns/);
  });
```

(b) Append at the end of the file a new describe:

```ts
describe('trading performance KPI strip (v186 D3)', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/dashboard/panels/trading-performance.ts'),
    'utf8',
  );

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
        { provide: ViewportService, useValue: { isPhone: signal(false) } },
      ],
    });
  });

  function render(inputs: Record<string, unknown>): HTMLElement {
    const f = TestBed.createComponent(TradingPerformance);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('puts every KPI card in one stat strip: four columns from md, two on a tablet', () => {
    const el = render({ currency: '€' });
    const strip = el.querySelector<HTMLElement>('sb-stat-strip.grid');
    expect(strip).not.toBeNull();
    expect(strip!.style.getPropertyValue('--strip-cols')).toBe('4');
    expect(strip!.style.getPropertyValue('--strip-cols-md')).toBe('2');
    expect(strip!.querySelector('.sb-strip-grid')!.classList).toContain('sb-strip-fixed');
    const cards = el.querySelectorAll('sb-metric-card');
    expect(cards.length).toBeGreaterThanOrEqual(7);
    expect(strip!.querySelectorAll('sb-metric-card')).toHaveLength(cards.length);
  });

  it('dims the strip host when the figures are stale, and only then', () => {
    expect(render({ stale: true, currency: '€' }).querySelector('sb-stat-strip')!.classList)
      .toContain('stale');
    expect(render({ currency: '€' }).querySelector('sb-stat-strip')!.classList)
      .not.toContain('stale');
  });

  it('keeps the stale dim and the phone hand-off to the summary on the strip host', () => {
    expect(src).toMatch(/\.grid\.stale, \.mobile-summary\.stale \{ opacity: 0\.55; \}/);
    const phone = src.match(/@media \(max-width: 639px\) \{[\s\S]*?\.mobile-summary \{/)?.[0] ?? '';
    expect(phone).toMatch(/\.grid \{ display: none; \}/);
  });

  it('draws no frame or gap of its own around the cards', () => {
    expect(src).not.toMatch(/\.grid\s*\{[^}]*gap:/);
    // The cards are grandchildren of the host now (host > .sb-strip-grid > card):
    // a child-combinator rule from .grid would silently match nothing.
    expect(src).not.toMatch(/\.grid\s*>/);
    if (/nth-child\(4n \+ 3\)/.test(src)) {
      expect(src).toMatch(/\.grid sb-metric-card:last-child:nth-child\(4n \+ 3\) \{ grid-column: span 2; \}/);
    }
  });
});
```

`readFileSync`, `join`, `provideZonelessChangeDetection`, `signal`, `TestBed`, `beforeEach`, `EquityCandlesStore`, `equityCandlesStoreStub`, `ViewportService` and `TradingPerformance` are already imported at the top of this spec.

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```
Expected: FAIL: both rewritten tablet-band tests (no `<sb-stat-strip class="grid"`, and `.grid { … grid-template-columns` still present), "puts every KPI card in one stat strip" (`sb-stat-strip.grid` is null), "dims the strip host…" (`querySelector('sb-stat-strip')` is null, TypeError), and "draws no frame or gap…" (`.grid { … gap:` present). "keeps the stale dim and the phone hand-off" already PASSES (it pins what must survive). Every pre-existing test passes.

- [ ] **Step 3: Migrate the KPI container**

All edits in `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`.

(a) Imports. After `import { MetricCard } from '../../../ui/metric-card';` add:

```ts
import { StatStrip } from '../../../ui/stat-strip';
```

and append `StatStrip` as the last entry of the `@Component` `imports:` array (on `main`: `imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue, Select],` becomes `imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue, Select, StatStrip],`; if the array also lists `Spinner`, keep it and add `StatStrip` after it).

(b) Template. Replace the opening tag

```html
        <div class="grid" [class.stale]="stale()">
```

with

```html
        <sb-stat-strip class="grid" [class.stale]="stale()" [cols]="4" [colsMd]="2">
```

and the matching closing `</div>` that ends the run of `sb-metric-card` lines (the line right after the last `<sb-metric-card … />`, before the `</div>` that closes `.combined`) with `</sb-stat-strip>`. Every `sb-metric-card` line between them stays exactly as it is.

(c) Styles. Delete the `.grid { display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: var(--space-14); }` rule **and** the comment block directly above it (starting `/* A fixed 4 columns, not auto-fit:`). Delete the tablet-band comment (starting `/* The tablet band -- v95 A5.`) **and** the whole block under it:

```css
    @media (max-width: 1023px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
```

In their place (directly after the `.mobile-summary` rules that precede them) put:

```css
    /* v186 D3: the KPI cards sit in one sb-stat-strip, ruled by hairlines
       instead of eight framed boxes. The strip owns the columns: 4 from md,
       2 in the tablet band (v95 A5: the 4-up floor starved the portfolio
       block at 768px) and 2 below sm, where this panel hides it for
       .mobile-summary. Fixed counts, not auto-fit, so the cards never split
       unevenly at an in-between width. The class stays .grid so the stale
       dim and the phone hide below keep applying to the strip host. */
```

Keep unchanged: `.grid.stale, .mobile-summary.stale { opacity: 0.55; }` and, inside `@media (max-width: 639px)`, `.grid { display: none; }`.

(d) Only if the state check printed a line: replace

```css
    .grid > :last-child:nth-child(4n + 3) { grid-column: span 2; }
```

with

```css
    .grid sb-metric-card:last-child:nth-child(4n + 3) { grid-column: span 2; }
```

keeping its comment ("Seven cards: the last one takes the rest of its row…"). The cards are now children of the strip's `div.sb-strip-grid`, not of `.grid`; the descendant selector still compiles to this component's `_ngcontent` attribute on both parts, which both elements carry.

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```
Expected: PASS, 0 failed. The existing tint, `.value.absent`, `.grid.stale` and `.mobile-summary` assertions pass untouched: the cards, their host classes and the `.grid` class are all still there.

- [ ] **Step 5: Run the neighbouring specs**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/metric-card.spec.ts --include src/app/ui/stat-strip.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts
```
Expected: PASS, 0 failed (`workspace-consistency.spec.ts` forbids `::ng-deep` into `sb-metric-card`; this task adds none).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/trading-performance.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts
git commit -F- <<'MSG'
feat(ui): v186 D3 Dashboard KPI cards in one stat strip

The Trading performance cards sit in sb-stat-strip (cols 4, colsMd 2)
instead of a hand-built grid of framed cards; the tablet-band media rule
goes, the .grid class stays on the strip host so the stale dim and the
phone hand-off to .mobile-summary are unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

### Task V186-7: Risk: metric tiles into a strip

**Model:** sonnet — one panel's tile row onto the new primitive, DOM plus source-text tests in a large workspace spec.

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (imports, the `<div class="metric-grid">` wrapper, the `.metric-grid` rule)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts` (new describe after `describe('Risk metric tiles', …)`)

**Interfaces:**
- Consumes (V186-4): `StatStrip` from `frontend/src/app/ui/stat-strip.ts` (selector `sb-stat-strip`; `cols = input<number | null>(null)`, `colsMd = input<number>(2)`; host `[style.--strip-cols]="cols()"`, `[style.--strip-cols-md]="colsMd()"`; inner `div.sb-strip-grid`, with `.sb-strip-fixed` only when `cols` is set). Without `cols`, the global `.sb-strip-grid` rule in `frontend/src/styles.css` lays the tiles out as `repeat(auto-fit, minmax(min(100%, 140px), 1fr))`, which is today's Risk minimum.
- Consumes (V186-3): `sb-stat-tile` reads `--figure-rule` / `--tile-*` on its own host.
- Produces: `<sb-stat-strip class="metric-grid">` (no `cols`) wrapping the `@for` of 6 `sb-stat-tile`s. Nothing later consumes it.

Column count is preserved: auto-fit at 140 px, as today. The tile gap changes from `var(--register-pad)` to 0 with hairlines between tiles; that is the D3 look, not a regression. Keeping the class `metric-grid` on the host keeps the page's own vocabulary; no spec selects on it today (`git grep -n "metric-grid" -- frontend/src/app/workspaces/risk/risk.spec.ts` prints nothing).

`workspace-consistency.spec.ts` "sizes metric grids with auto-fit" scans `risk.ts`: this task removes a `grid-template-columns` line and adds none, so it stays green.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/risk/risk.spec.ts`, directly after the closing `});` of `describe('Risk metric tiles', …)` (and before the `describe('Risk gauge, budget and correlation matrix', …)` block), add:

```ts
describe('Risk metric tiles in a stat strip (v186 D3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/risk/risk.ts'), 'utf8');

  it('rules the six tiles with one stat strip, auto-fit at 140px', async () => {
    const fixture = await renderWithMetrics();
    const el = fixture.nativeElement as HTMLElement;
    const strip = el.querySelector<HTMLElement>('sb-stat-strip.metric-grid');
    expect(strip).not.toBeNull();
    expect(strip!.querySelectorAll('sb-stat-tile')).toHaveLength(6);
    expect(el.querySelectorAll('sb-stat-tile')).toHaveLength(6);
    // No cols: the default auto-fit column rule, not the fixed-count one.
    expect(strip!.style.getPropertyValue('--strip-cols')).toBe('');
    expect(strip!.querySelector('.sb-strip-grid')!.classList).not.toContain('sb-strip-fixed');
  });

  it('keeps the thin-sample cues inside the strip', async () => {
    const fixture = await renderWithMetrics({ sharpe_r: { value: 0.96, n: 7 } });
    const tile = tileHost(fixture, 'Sharpe (R)');
    expect(tile.closest('sb-stat-strip')).not.toBeNull();
    expect(tile.classList).toContain('thin');
    expect(tile.querySelector('.flag')!.textContent).toContain('thin sample');
  });

  it('declares no metric grid of its own', () => {
    expect(src).not.toMatch(/\.metric-grid\s*\{/);
    expect(src).toMatch(/<sb-stat-strip class="metric-grid">/);
  });
});
```

`renderWithMetrics`, `tileHost`, `readFileSync` and `join` already exist in this spec (`renderWithMetrics` and `tileHost` are top-level functions defined above `describe('Risk metric tiles', …)`).

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/risk/risk.spec.ts
```
Expected: FAIL: "rules the six tiles with one stat strip" (`sb-stat-strip.metric-grid` is null), "keeps the thin-sample cues inside the strip" (`closest('sb-stat-strip')` is null) and "declares no metric grid of its own" (`.metric-grid {` present). Every pre-existing Risk test passes.

- [ ] **Step 3: Migrate the tile row**

All edits in `frontend/src/app/workspaces/risk/risk.ts`.

(a) Imports. After `import { StatTile } from '../../ui/stat-tile';` add:

```ts
import { StatStrip } from '../../ui/stat-strip';
```

and in the `@Component` `imports:` array (on `main`: `imports: [Async, Button, ConfirmDialog, DataTable, Flash, Freshness, Matrix, Panel, RowLink, SectionHead, Sparkline, StatTile],`) insert `StatStrip` before `StatTile`:

```ts
  imports: [Async, Button, ConfirmDialog, DataTable, Flash, Freshness, Matrix, Panel, RowLink, SectionHead, Sparkline, StatStrip, StatTile],
```

(b) Template, inside `<sb-panel heading="Risk metrics">`. Replace

```html
        <div class="metric-grid">
          @for (tile of metricTiles(); track tile.label) {
            <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" />
          }
        </div>
```

with

```html
        <!-- v186 D3: one strip, tiles split by hairlines; no cols, so the
             strip's default auto-fit at 140px keeps today's column count. -->
        <sb-stat-strip class="metric-grid">
          @for (tile of metricTiles(); track tile.label) {
            <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" />
          }
        </sb-stat-strip>
```

(c) Styles. Delete the rule

```css
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: var(--register-pad);
    }
```

and leave `.metrics { display: grid; gap: var(--space-8); }` and `.metrics-scope` as they are (`.metrics-scope`'s `--text-faint` is outside this spec's scoped files).

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/risk/risk.spec.ts
```
Expected: PASS, 0 failed. `describe('Risk metric tiles', …)` still finds its six `sb-stat-tile .label`s and the inner `.tile` classes, since the tiles are unchanged.

- [ ] **Step 5: Run the workspace gates**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/stat-strip.spec.ts
```
Expected: PASS, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts
git commit -F- <<'MSG'
feat(ui): v186 D3 Risk metric tiles in one stat strip

The six Risk metrics sit in sb-stat-strip with its default auto-fit at
140px (today's column rule), split by hairlines instead of framed tiles;
the page's .metric-grid rule goes.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

### Task V186-8: Calendar: summary tiles into a strip

**Model:** sonnet — one panel's tile row onto the new primitive, with a large spec whose selectors must keep matching.

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (imports, the `<div class="totals">` wrapper, the `.totals` rules)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (new describe after `describe('Calendar totals: one stat tile (v179 §3.3)', …)`)

**Interfaces:**
- Consumes (V186-4): `StatStrip` from `frontend/src/app/ui/stat-strip.ts` (selector `sb-stat-strip`; `cols = input<number | null>(null)`, `colsMd = input<number>(2)`; host `[style.--strip-cols]="cols()"`, `[style.--strip-cols-md]="colsMd()"`; inner `div.sb-strip-grid.sb-strip-fixed` when `cols` is set). The global fixed-count rules in `frontend/src/styles.css` give 2 columns below 640 px, `--strip-cols-md` from 640 px, `--strip-cols` from 1024 px.
- Consumes (V186-2): `calendar.ts` already carries `[divided]="true"` on the "By weekday" panel. Do not touch that line.
- Consumes (V186-3): `sb-stat-tile` reads `--figure-rule` / `--tile-*` on its own host.
- Produces: `<sb-stat-strip class="totals" [cols]="4" [colsMd]="4">` wrapping the 7 `sb-stat-tile`s. Nothing later consumes it.

Column counts are preserved: 4 at 640 px and up (`cols=4`, `colsMd=4`), 2 below 640 px (the strip's fixed-count floor), which is today's `.totals` rule. The class `totals` stays on the strip host because `calendar.spec.ts` selects `.totals`, `.totals sb-stat-tile` and `.totals sb-stat-tile .tile` in eight places, and asserts `.totals` is absent for an empty month; the strip lives inside the same `@if`, so all of them keep matching.

`calendar.spec.ts` also pins `calendar.ts` to contain no `::ng-deep`, no `grid-auto-rows` and no `sb-metric-card`: this task adds none of them. The calendar's week matrix keeps its fixed `repeat(7` columns; `workspace-consistency.spec.ts` exempts it through the `.week, .weekhead` regex, which this task does not touch.

The day drawer's `.day-summary` tiles and `calendar-day.ts` are page-level rows: **not** migrated (spec D3).

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/calendar/calendar.spec.ts`, directly after the closing `});` of `describe('Calendar totals: one stat tile (v179 §3.3)', …)` (and before `describe('Calendar totals metric formatting and tone (v179)', …)`), add:

```ts
describe('Calendar totals in a stat strip (v186 D3)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/calendar/calendar.ts'), 'utf8');

  it('rules the seven summary tiles with one stat strip: four columns from sm, two on a phone', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    const strip = el(fixture).querySelector<HTMLElement>('sb-stat-strip.totals');
    expect(strip).not.toBeNull();
    expect(strip!.querySelectorAll('sb-stat-tile')).toHaveLength(7);
    expect(strip!.style.getPropertyValue('--strip-cols')).toBe('4');
    expect(strip!.style.getPropertyValue('--strip-cols-md')).toBe('4');
    expect(strip!.querySelector('.sb-strip-grid')!.classList).toContain('sb-strip-fixed');
  });

  it('leaves the day drawer tiles out of any strip (page-level row)', () => {
    expect(SOURCE).not.toMatch(/<sb-stat-strip[^>]*class="day-summary"/);
    expect(SOURCE.match(/<sb-stat-strip/g)).toHaveLength(1);
  });

  it('declares no totals grid of its own', () => {
    expect(SOURCE).not.toMatch(/\.totals\s*\{[^}]*grid-template-columns/);
    expect(SOURCE).not.toMatch(/\.totals\s*\{[^}]*gap:/);
  });
});
```

`seed`, `el`, `readFileSync` and `join` already exist in this spec (`seed` is exported at the top, `el` is a top-level arrow function).

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/calendar/calendar.spec.ts
```
Expected: FAIL: "rules the seven summary tiles with one stat strip" (`sb-stat-strip.totals` is null), "leaves the day drawer tiles out of any strip" (`SOURCE.match(/<sb-stat-strip/g)` is `null`, not length 1) and "declares no totals grid of its own" (`.totals { … grid-template-columns` present). Every pre-existing Calendar test passes.

- [ ] **Step 3: Migrate the tile row**

All edits in `frontend/src/app/workspaces/calendar/calendar.ts`.

(a) Imports. After `import { MIN_SAMPLE_N, StatTile, StatTone } from '../../ui/stat-tile';` add:

```ts
import { StatStrip } from '../../ui/stat-strip';
```

and in the `@Component` `imports:` array (on `main`: `imports: [Button, ControlRow, Drawer, Panel, RouterLink, SectionHead, Select, StatTile, Async],`) insert `StatStrip` before `StatTile`:

```ts
  imports: [Button, ControlRow, Drawer, Panel, RouterLink, SectionHead, Select, StatStrip, StatTile, Async],
```

(b) Template, inside `<sb-panel inlineFrom="md" [digest]="calendarDigest()" [problem]="calendarProblem()">`. Replace the opening `<div class="totals">` with:

```html
        <sb-stat-strip class="totals" [cols]="4" [colsMd]="4">
```

and its closing `</div>` (the line after `<sb-stat-tile label="Worst day" … />`) with `</sb-stat-strip>`. The seven `sb-stat-tile` lines and the comment above them ("Seven summary figures in reading order; four columns on desktop and tablet, two on phone, with content-sized rows.") stay as they are.

(c) Styles. Replace the comment block that starts `/* Exactly 4 columns, 2 below sm -- on request (2026-09-14, "at most 2` together with the two rules under it:

```css
    .totals {
      display: grid;
      gap: var(--space-14);
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    @media (max-width: 639px) {
      .totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
```

with this comment alone (no rule):

```css
    /* Exactly 4 columns, 2 below sm -- on request (2026-09-14, "at most 2
       rows"): seven tiles at four per row is two rows. v186 D3: the totals
       are one sb-stat-strip (cols 4, colsMd 4), so the strip owns those
       columns and splits the tiles with hairlines instead of framing each;
       no fixed row height and no reaching into the tiles (v179 §3.3). */
```

Leave `sb-panel.calendar-panel { … }` and everything after it as it is.

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/calendar/calendar.spec.ts
```
Expected: PASS, 0 failed, including the pre-existing `.totals` selectors ("shows the visible month's pooled totals", the empty-month `.totals` null check, "renders every summary figure as the same stacked sb-stat-tile", the metric formatting `it.each`) and "restyles no tile from outside and fixes no row height".

- [ ] **Step 5: Run the workspace gates and the day page**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts --include src/app/ui/stat-strip.spec.ts
```
Expected: PASS, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -F- <<'MSG'
feat(ui): v186 D3 Calendar summary tiles in one stat strip

The seven month totals sit in sb-stat-strip (cols 4, colsMd 4: 4 columns
from 640px, 2 below), split by hairlines instead of framed tiles; the
page's .totals grid and its phone rule go, the .totals class stays on the
strip host for the existing selectors. The day drawer row is untouched.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

