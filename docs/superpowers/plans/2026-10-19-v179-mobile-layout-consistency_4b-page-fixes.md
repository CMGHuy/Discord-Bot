# v179 — Mobile layout consistency, Part 4b: page fixes and the Part 4 browser check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — §2.3 "Numbers", §2.4, §3.3 "Numbers" and "`sb-panel`", §3.4.
**Index:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](2026-10-19-v179-mobile-layout-consistency_0-index.md) — Goal, Architecture, **Global Constraints**, **Contracts**, **Parallelisation** and the task ledger live there and bind every task below.

Tasks V179-17..V179-18: the second half of Part 4. The index lists them in `_4-dashboard-and-pages.md`; that file reached 1254 lines with V179-14..V179-16, and these two tasks would take it past the 1500-line cap, so they live here, unchanged in id, scope, files and order (the part header of `_4-dashboard-and-pages.md` lists this part's file additions). Every task runs in the worktree `.claude/worktrees/2026-10-19-v179-mobile-layout-consistency`; commands run from the worktree root.

---

### Task V179-17: Trade-detail fixes: title baseline, "Confirmed by:" space, one numeric face in cards

**Model:** haiku — mechanical class and CSS edits with an exact before/after for each, guarded by source-text tests.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/why/why-panel.ts`
- Modify: `frontend/src/app/workspaces/trades/why/why-panel.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/strategy-record-card.ts`
- Modify: `frontend/src/app/workspaces/trades/scores-card.ts`
- Modify: `frontend/src/app/workspaces/trades/why/levels-block.ts`
- Modify: `frontend/src/app/workspaces/trades/why/sizing-panel.ts`
- Modify: `frontend/src/app/workspaces/trades/why/if-it-gets-there.ts`
- Modify: `frontend/src/app/ui/status-indicator.ts`

**Interfaces:**
- Consumes: `.num` → `font-family: var(--font-num); font-variant-numeric: tabular-nums` (V179-1, `frontend/src/styles.css`); the baseline `sb-panel` header (V179-3).
- Produces: nothing later tasks call. The last three files are this part's addition to the ledger (see `_4-dashboard-and-pages.md`'s header): they hold the measured defects.

**What is wrong (spec §2.3, §2.4, §3.4), traced in the code:**
- **Title, 3px offset.** `.trade-title` is `align-items: center`, and `sb-status-indicator`'s `.wrap` is `inline-flex; align-items: center` with an empty 6px dot as its first item. A flex container's baseline is its first item's, so the indicator's baseline is the dot's bottom edge, not the "CLOSED" text. Both rules change: the title aligns on the baseline, and the indicator aligns its items on the baseline with the dot and progress track centred (`align-self: center`) — they have no text, and an item that does not take part in baseline alignment does not set the container's baseline, so the label's does.
- **"Confirmed by:Fib".** `why-panel.ts` writes `<span class="muted">Confirmed by:</span>` and then a newline before `@for`; Angular drops whitespace-only text nodes, so no space renders. An explicit `{{ ' ' }}` keeps it (the same idiom as `{{ ' → ' }}` in `dashboard.ts`).
- **Mono and sans numbers in one card.** `sizing-panel.ts`, `if-it-gets-there.ts` and `why-panel.ts` mark numbers with `sb-num`, a class no stylesheet defines — "1,000.00" (Deployed) and "5.51%" (Gap risk p90) render in the UI face beside `240.40` in the numeric face. `strategy-record-card.ts` and the why-panel Levels list put numbers in bare `<dd>`s. Every number gets `.num`; prose around a number does not (`if-it-gets-there.ts` wraps only the figure).
- **Label and value on two baselines.** The `dl > div` rows put a UI-face `dt` beside a numeric-face `dd` with the default `align-items: stretch`, so the two texts start at the top of their boxes and their baselines differ. They become `align-items: baseline`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (`readFileSync` and `join` are already imported there):

```ts
describe('TradeDetail — one numeric face, one baseline (v179 §3.3, §3.4)', () => {
  const APP = join(process.cwd(), 'src/app');
  const read = (path: string) => readFileSync(join(APP, path), 'utf8');
  const CARDS = [
    'workspaces/trades/trade-detail.ts',
    'workspaces/trades/strategy-record-card.ts',
    'workspaces/trades/scores-card.ts',
    'workspaces/trades/why/why-panel.ts',
    'workspaces/trades/why/levels-block.ts',
    'workspaces/trades/why/sizing-panel.ts',
    'workspaces/trades/why/if-it-gets-there.ts',
  ];

  it('marks numbers with .num, the class that exists, never the undefined sb-num', () => {
    for (const path of CARDS) expect(read(path), path).not.toMatch(/\bsb-num\b/);
  });

  it('puts every formatted number in a dd in the numeric face', () => {
    const bareNumber = /<dd(?![^>]*\bnum\b)[^>]*>\s*\{\{\s*(?:fmt|fmtNum|fmtPct|fmtShare|fmtSigned)\(/;
    for (const path of CARDS) expect(read(path), path).not.toMatch(bareNumber);
  });

  it('aligns each label/value row on the text baseline', () => {
    for (const path of [
      'workspaces/trades/strategy-record-card.ts',
      'workspaces/trades/scores-card.ts',
      'workspaces/trades/why/levels-block.ts',
      'workspaces/trades/why/sizing-panel.ts',
      'workspaces/trades/why/if-it-gets-there.ts',
    ]) {
      expect(read(path), path).toMatch(/dl > div \{[^}]*align-items: baseline/);
    }
  });

  it('sets the ticker, side and status of the title on one baseline', () => {
    const title = read('workspaces/trades/trade-detail.ts').match(/\.trade-title \{[^}]*\}/)![0];
    expect(title).toContain('align-items: baseline');
    expect(title).not.toContain('align-items: center');
    const indicator = read('ui/status-indicator.ts');
    expect(indicator.match(/\.wrap \{[^}]*\}/)![0]).toContain('align-items: baseline');
    expect(indicator).toMatch(/\.dot,\s*\.track \{ align-self: center; \}/);
  });
});
```

In `frontend/src/app/workspaces/trades/why/why-panel.spec.ts`, append inside `describe('WhyPanel', …)`:

```ts
  it('puts a space after "Confirmed by:" (v179 §3.4)', () => {
    const f = mount({ confirmedBy: [{ strategy: 'Fib', horizon: null }, { strategy: 'RSI', horizon: '2w' }] });
    const line = [...f.nativeElement.querySelectorAll('p.source')]
      .map((p: Element) => p.textContent!.replace(/\s+/g, ' ').trim())
      .find((text: string) => text.startsWith('Confirmed by'));
    expect(line).toBe('Confirmed by: Fib, RSI (2w)');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/why/why-panel.spec.ts`
Expected: FAIL — `sb-num` found in three files; bare numeric `<dd>`s in `strategy-record-card.ts` and `why-panel.ts`; no `align-items: baseline` on the `dl > div` rows or the title; the confirmation line reads `Confirmed by:Fib, RSI (2w)`.

- [ ] **Step 3: Title and status indicator on the baseline**

`frontend/src/app/workspaces/trades/trade-detail.ts` — in the `.trade-title { … }` rule change `align-items: center;` to `align-items: baseline;` and put this comment above the rule:

```css
    /* Baseline, not centre (v179 §3.4): the 18px mono ticker, the side and
       the 11.7px status text sat 3px apart when centred. */
```

`frontend/src/app/ui/status-indicator.ts` — replace

```css
    .wrap { display: inline-flex; align-items: center; gap: var(--space-6); }
```

with

```css
    /* Baseline (v179 §3.4) so a title or row can align this indicator's
       status text with its own; the dot and track carry no text and stay
       centred, which also keeps them out of the container's baseline. */
    .wrap { display: inline-flex; align-items: baseline; gap: var(--space-6); }
    .dot, .track { align-self: center; }
```

- [ ] **Step 4: "Confirmed by:" space and the why-panel numbers**

`frontend/src/app/workspaces/trades/why/why-panel.ts`:
- replace `<p class="source"><span class="muted">Confirmed by:</span>` with `<p class="source"><span class="muted">Confirmed by:</span>{{ ' ' }}`;
- in the `dl.levels` list add `class="num"` to the five `<dd>`s (Trigger/Entry, stop, Target 1, Target 2, Acceptance level), e.g. `<dd class="num">{{ fmtNum(stop()) }}</dd>`;
- replace every `sb-num` with `num` (the factor points, the total, the factor rows, and the gate Value/Threshold/Margin spans — `git grep -n "sb-num" frontend/src/app/workspaces/trades/why/why-panel.ts` lists them);
- the `dd { margin: var(--space-4) 0 0; font-variant-numeric: tabular-nums; }` rule loses `font-variant-numeric: tabular-nums;` (`.num` sets it now) and becomes `dd { margin: var(--space-4) 0 0; }`.

- [ ] **Step 5: The other cards**

`frontend/src/app/workspaces/trades/strategy-record-card.ts` — add `class="num"` to the six numeric `<dd>`s (OOS sample, OOS win rate, OOS expectancy, Live sample, Live win rate, Live vs OOS); Strategy, Status and Window stay text. Change `dl > div { display: flex; justify-content: space-between; gap: var(--space-10); min-width: 0; }` to `dl > div { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-10); min-width: 0; }`.

`frontend/src/app/workspaces/trades/scores-card.ts` — change `dl > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-4); }` to `dl > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: baseline; gap: var(--space-4); }`. Badge stays a text `<dd>` (a tier name, not a number).

`frontend/src/app/workspaces/trades/why/levels-block.ts` — change `dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }` to `dl > div { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-10); }`. (Its numbers already carry `.num`.)

`frontend/src/app/workspaces/trades/why/sizing-panel.ts` — replace the `<dl>` body's numeric cells:

```html
        <div><dt>Shares</dt><dd class="num">{{ fmtNum(shares(), 0) }}</dd></div>
        <div><dt>Deployed</dt><dd class="num">{{ fmtNum(positionValue()) }}</dd></div>
        <div><dt>Sizing mode</dt><dd>{{ fmtText(sizingMode()) }}</dd></div>
        <div><dt>Working stop</dt><dd class="num">{{ fmtNum(workingStop()) }}</dd></div>
        <div>
          <dt>Gap risk (p90)</dt>
          <dd class="gap-risk">
            <span class="num">{{ fmtShare(gapP90Pct(), 2) }}</span>
```

(the `@if (gapFragile() === true)` chip and the closing tags below it stay as they are — the chip keeps its own face), and change `dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }` to `dl > div { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-10); }`.

`frontend/src/app/workspaces/trades/why/if-it-gets-there.ts` — the two `<dd>`s are sentences with one figure each; only the figure takes the numeric face:

```html
          <dd>
            @if (target2() !== null) {
              next stop <span class="num">{{ fmtNum(target2()) }}</span>
            } @else {
              <span class="absent">no further level found</span>
            }
          </dd>
```

```html
          <dd>pulls back toward {{ oppositeWord() }} at <span class="num">{{ fmtNum(stopLoss()) }}</span></dd>
```

and change `dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }` to `dl > div { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-10); }`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/why/why-panel.spec.ts --include src/app/workspaces/trades/why/sizing-panel.spec.ts --include src/app/workspaces/trades/why/if-it-gets-there.spec.ts --include src/app/workspaces/trades/why/levels-block.spec.ts --include src/app/workspaces/trades/strategy-record-card.spec.ts --include src/app/workspaces/trades/scores-card.spec.ts --include src/app/ui/text-styles.spec.ts`
Expected: PASS, 0 failed. A spec that asserted an `sb-num` selector (none exists today: `git grep -n "sb-num" -- "*.spec.ts"` is empty) would be updated to `.num`, never the guard loosened.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/ui/status-indicator.ts
git commit -m "fix(v179): trade title on one baseline -- status indicator aligns by its text"
git add frontend/src/app/workspaces/trades/why/why-panel.ts frontend/src/app/workspaces/trades/why/why-panel.spec.ts frontend/src/app/workspaces/trades/strategy-record-card.ts frontend/src/app/workspaces/trades/scores-card.ts frontend/src/app/workspaces/trades/why/levels-block.ts frontend/src/app/workspaces/trades/why/sizing-panel.ts frontend/src/app/workspaces/trades/why/if-it-gets-there.ts
git commit -m "fix(v179): one numeric face in trade-detail cards; Confirmed by: gets its space

sb-num was never defined, so Deployed and Gap risk rendered in the UI face.
Label/value rows align on the text baseline."
```

---

### Task V179-18: Versions "Running now", Dashboard performance segmented header, Analytics population line and empty N; Part 4 browser check

**Model:** sonnet — three template fixes with source and DOM tests, then a judgement-heavy three-width browser check of everything Part 4 changed.

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Modify: `frontend/src/app/workspaces/versions/versions.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/scope-bar.ts`
- Modify: `frontend/src/app/workspaces/analytics/scope-bar.spec.ts`

**Interfaces:**
- Consumes: `sb-control-row` on `align-items: last baseline` (V179-3 — its docstring names the Versions "Running now" label as the case it fixes); the baseline `sb-panel` header (V179-3); `sb-segmented` (`options: SegmentOption[]`, `label`, `value` model; segments 44px under `(pointer: coarse), (max-width: 1023px)` since V179-2); the Dashboard trade drawer (V179-14..V179-16) for the browser check.
- Produces: nothing later tasks call. `dashboard.spec.ts` changes by one selector (the scope buttons become `sb-segmented` segments); V179-16 owns the rest of that file and runs first.

**What is wrong (spec §2.4, §3.3 "`sb-panel`", §3.4), traced in the code:**
- **Versions.** `.headline` is a flex row on `baseline`, but its second item is a whole `sb-control-row` — a block whose baseline is its first chip's — and below 640px that row turns into a column. The label belongs *in* the control row as its first item, where V179-3's `last baseline` puts plain text on the chips' text line.
- **Dashboard "Trading performance".** The header's scope control is an `sb-control-row` of two `sb-button`s (`secondary` when pressed, `ghost` when not), so "Today" is bordered and "All days" is not, and they stack below 640px. Spec §3.3: Today / All days become one `sb-segmented` control on the header line.
- **Analytics population line.** `scope-bar.ts` projects the `sb-segmented` unit toggle, the `N=… closed` span and the freshness stamp straight into `sb-control-bar`'s `.scope` box, which is `align-items: center` — text at two sizes beside a 28/44px control lands at two heights. A `div[scope].scope-line` of its own on `align-items: baseline` fixes it without touching `sb-control-bar` (V179-5's file).
- **"N=— closed".** `N={{ n() ?? '—' }} closed` prints a dash where the sample is empty. Spec §3.4: an empty sample says "no closed trades". Zero is the same measured answer, so `0` reads the same way.

- [ ] **Step 1: Write the failing tests**

Append inside `describe('Versions', …)` of `frontend/src/app/workspaces/versions/versions.spec.ts`:

```ts
  it('puts "Running now" in the chip row, on the chips\' text baseline (v179 §3.4)', async () => {
    const fixture = seed(PAIRED);
    await fixture.whenStable();
    fixture.detectChanges();
    const row = (fixture.nativeElement as HTMLElement).querySelector('sb-control-row.headline .row')!;
    expect(row.firstElementChild?.classList).toContain('label');
    expect(row.firstElementChild?.textContent?.trim()).toBe('Running now');
    expect(row.querySelectorAll('button.chip').length).toBeGreaterThan(0);
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/versions/versions.ts'), 'utf8');
    expect(src).not.toMatch(/<div class="headline">/);
    expect(src).not.toMatch(/\.headline \{[^}]*display: flex/);
  });
```

Append inside `describe('trading performance panel', …)` of `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`, and replace the existing `'emits the scope the user picked'` test with the second one below:

```ts
  it('puts Today / All days in one segmented control on the header line (v179 §3.3)', () => {
    const el = render({ scope: 'today' });
    const control = el.querySelector('sb-panel header sb-segmented')!;
    expect(control).not.toBeNull();
    const segments = [...control.querySelectorAll<HTMLButtonElement>('.segment')];
    expect(segments.map((s) => s.textContent!.trim())).toEqual(['Today', 'All days']);
    expect(segments.map((s) => s.getAttribute('aria-pressed'))).toEqual(['true', 'false']);
    expect(el.querySelector('sb-panel header sb-control-row')).toBeNull();
    expect(el.querySelector('[data-scope]')).toBeNull();
  });

  it('emits the scope the user picked', () => {
    const f = TestBed.createComponent(TradingPerformance);
    f.componentRef.setInput('scope', 'today');
    f.detectChanges();
    let picked: string | undefined;
    f.componentInstance.scopeChange.subscribe((s: string) => (picked = s));
    [...(f.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('sb-segmented .segment')]
      .find((s) => s.textContent!.trim() === 'All days')!.click();
    expect(picked).toBe('all');
  });

  it('presses no segment for a scope the toggle never sets', () => {
    const el = render({ scope: 'active' });
    const pressed = [...el.querySelectorAll('sb-segmented .segment')].map((s) => s.getAttribute('aria-pressed'));
    expect(pressed).toEqual(['false', 'false']);
  });
```

In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, test `'routes the panel scope control back into the store'`, replace

```ts
    el.querySelector<HTMLButtonElement>('[data-scope="all"]')!.click();
```

with

```ts
    [...el.querySelectorAll<HTMLButtonElement>('sb-trading-performance sb-segmented .segment')]
      .find((s) => s.textContent!.trim() === 'All days')!.click();
```

Append inside `describe('ScopeBar', …)` of `frontend/src/app/workspaces/analytics/scope-bar.spec.ts` (add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top):

```ts
  it('says "no closed trades" for an empty sample, never "N=—" (v179 §3.4)', () => {
    for (const n of [null, 0]) {
      const { el } = create({ n });
      const line = el.querySelector('.population')!;
      expect(line.textContent!.trim()).toBe('no closed trades');
      expect(line.classList).not.toContain('num');
      expect(el.textContent).not.toContain('N=—');
    }
    const { el } = create({ n: 972 });
    expect(el.querySelector('.population')!.textContent!.trim()).toBe('N=972 closed');
    expect(el.querySelector('.population')!.classList).toContain('num');
  });

  it('sets the unit toggle, population and freshness on one baseline', () => {
    const { el } = create();
    const line = el.querySelector('sb-control-bar .scope .scope-line')!;
    expect(line.querySelector('sb-segmented')).not.toBeNull();
    expect(line.querySelector('.population')).not.toBeNull();
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/scope-bar.ts'), 'utf8');
    expect(src).toMatch(/\.scope-line \{[^}]*align-items: baseline/);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/analytics/scope-bar.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL — no `sb-control-row.headline`; no `sb-segmented` in the performance header (and the rewritten selector in `dashboard.spec.ts` finds nothing); the population reads `N=— closed` / `N=0 closed`; no `.scope-line`.

- [ ] **Step 3: Versions — the label joins the chip row**

In `frontend/src/app/workspaces/versions/versions.ts` replace

```html
      <div class="headline">
        <span class="label">Running now</span>
        <sb-control-row>
```

with

```html
      <!-- v179 §3.4: the label is the row's first item, so sb-control-row's
           last-baseline alignment puts it on the chips' text line (and it
           heads the stack below 640px rather than floating beside it). -->
      <sb-control-row class="headline">
        <span class="label">Running now</span>
```

and the matching closing `</sb-control-row>` followed by `</div>` with just `</sb-control-row>`. Delete the rule `.headline { display: flex; align-items: baseline; gap: var(--register-pad); flex-wrap: wrap; }` (the `.label` rule after it stays; `sb-control-row` already sets the gap and wrapping).

- [ ] **Step 4: Dashboard — Today / All days as one segmented control**

In `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`:

Imports: remove `Button` and `ControlRow` (nothing else in the template uses them — `git grep -n "sb-button\|sb-control-row" frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` must be empty after the edit), import `Panel` alone from `'../../../ui/layout'`, and add `import { SegmentOption, Segmented } from '../../../ui/segmented';`. The component `imports` array becomes `[Panel, MetricCard, Segmented, PortfolioValue]`.

Replace the whole `<sb-control-row panel-actions role="group" aria-label="Date scope"> … </sb-control-row>` block with:

```html
      <!-- v179 §3.3: one segmented control on the header line, in place of a
           bordered and a borderless button that stacked on a phone. -->
      <sb-segmented panel-actions label="Date scope" [options]="scopeOptions"
                    [value]="scope()" (valueChange)="pickScope($event)" />
```

In the class, replace the `scopes` array with:

```ts
  /** The two scopes this toggle sets. `active` is never offered, so it
   *  presses no segment (see DashboardScopeMode above). */
  protected readonly scopeOptions: SegmentOption[] = [
    { value: 'today', label: 'Today' },
    { value: 'all', label: 'All days' },
  ];

  protected pickScope(value: string): void {
    this.scopeChange.emit(value as DashboardScopeMode);
  }
```

- [ ] **Step 5: Analytics — one baseline and an honest empty sample**

In `frontend/src/app/workspaces/analytics/scope-bar.ts` replace the `<ng-container scope> … </ng-container>` block with:

```html
      <!-- v179 §3.4: a box of its own on the text baseline -- sb-control-bar's
           .scope centres its children, which put the population text and the
           unit toggle's labels at two heights. -->
      <div scope class="scope-line">
        <sb-segmented label="Unit" [options]="unitOptions" [value]="unit()"
                      (valueChange)="unitChange.emit($any($event))" />
        @if (!tuning()) {
          <span class="population" [class.num]="hasSample()">{{ population() }}</span>
          @if (asOf()) { <sb-freshness [at]="asOf()!" /> }
          @if (allTimePanels() > 0) {
            <span class="all-time">{{ allTimePanels() }} panels all-time</span>
          }
        }
      </div>
```

Add to the styles, before `.population`:

```css
    .scope-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-10); min-width: 0; }
```

and in `.population` drop `font-variant-numeric: tabular-nums;` (`.num` carries it when there is a number). Add to the class, after `activeCount`:

```ts
  /** Spec §3.4: an empty sample reads as "no data", never a dash beside a
   *  value. Zero closed trades is the same answer as none. */
  protected readonly hasSample = computed(() => (this.n() ?? 0) > 0);
  protected readonly population = computed(() =>
    this.hasSample() ? `N=${this.n()} closed` : 'no closed trades');
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/analytics/scope-bar.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/analytics/analytics.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/versions/versions.ts frontend/src/app/workspaces/versions/versions.spec.ts
git commit -m "fix(v179): Versions Running now sits in the chip row, on the chips' baseline"
git add frontend/src/app/workspaces/dashboard/panels/trading-performance.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "fix(v179): Dashboard performance scope is one segmented control on the header line"
git add frontend/src/app/workspaces/analytics/scope-bar.ts frontend/src/app/workspaces/analytics/scope-bar.spec.ts
git commit -m "fix(v179): Analytics population on one baseline; an empty sample says no closed trades"
```

- [ ] **Step 8: Part 4 browser check at 1440, 768 and 390**

Run `/replicate-prod-db`, then from the worktree root build and serve (leave `admin_ui.py` running, `run_in_background`), sign in once (`.env` credentials are loaded inside `browse.mjs`, never printed), and pick a recent trade id from the replica:

```bash
cd frontend && npm run build && cd ..
python admin_ui.py
node frontend/scripts/browse.mjs login --base http://localhost:1234
node frontend/scripts/browse.mjs api --base http://localhost:1234 --path "/api/v1/trades?sort=-opened_at&page=1&per_page=1"
```

Take the `id` of the first item as `TRADE` (`TRADE=<that id>`), then:

```bash
OUT="$(mktemp -d)"
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --widths 1440,768,390 --out "$OUT" \
  --path /dashboard --path /versions --path /analytics --path "/analytics?tab=partials" --path "/trades/$TRADE" \
  --path "/dashboard?trade=$TRADE"
OUT2="$(mktemp -d)"
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --widths 1440,390 --out "$OUT2" \
  --path /dashboard --click "sb-recent-activity button.event-hit"
grep -H "page-scroll-x" "$OUT"/*.txt "$OUT2"/*.txt | grep -v "page-scroll-x: 0"
```

Expected: the `grep` prints nothing. Then open the PNGs and check:

| What | Where | Pass when |
|---|---|---|
| Activity rows (V179-14) | `/dashboard` @390, @768 | each row is one full-width tap target ≥ 44px; ticker, detail and time on one text line |
| Trade drawer (V179-15, V179-16) | `$OUT2` `/dashboard` @1440 and @390 | side panel at 1440, bottom sheet at 390; heading = ticker with a "Paper trade" marker beside it; P&L shows % **and** € (or "—" with no amount for a plan not yet filled); Entry/Trigger, Stop, TP1, TP2, R:R, Opened, Held, Strategy, Horizon; row actions and "Open full trade →" on one line; no field reads `NaN`, `undefined` or blank |
| Cold link (V179-16) | `$OUT` `/dashboard?trade=$TRADE` | the drawer is open over the Dashboard (the trade is among the 20 newest), not an empty drawer |
| Positions on a phone (V179-16) | `/dashboard` @390 | compact rows (V179-11); none opens a generic row drawer — tapping is the trade drawer (check by hand in the headed browser: tap a row, then press Back: the drawer closes and the URL loses `?trade=`) |
| Trade title (V179-17) | `/trades/$TRADE` @1440, @390 | ticker, side and status text on one baseline; "Confirmed by: …" has its space; Sizing "Deployed" and "Gap risk" in the same numeric face as the Levels figures |
| Versions (V179-18) | `/versions` @390, @1440 | "RUNNING NOW" on the chips' text line at 1440; heading the chip stack at 390 |
| Performance header (V179-18) | `/dashboard` @390, @768, @1440 | Today / All days one segmented control on the header line, both segments the same height and border |
| Population line (V179-18) | `/analytics` and `/analytics?tab=partials` @390 | unit toggle, `N=… closed` and the freshness stamp on one baseline; a scope with no closed trades reads "no closed trades" |

Each failure is fixed in the file it traces to (the Part 4 task that owns it), with a test in that file's spec in the style of the owning task, run with that spec's narrow `ng test --include`, and committed as `fix(ui): <what> -- v179 Part 4 browser check`. Re-shoot the affected paths until the table passes. Stop `admin_ui.py` when done.
