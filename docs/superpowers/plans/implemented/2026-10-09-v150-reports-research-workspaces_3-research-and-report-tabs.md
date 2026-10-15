# v150 Reports and Research workspaces: Part 3, the Research page and the two report tabs

> Part of the v150 plan. Header, Global Constraints, the blocked-task gate, the wire shapes and the parallelisation map are in [`_0-index`](2026-10-09-v150-reports-research-workspaces_0-index.md). **Never read this file whole**: `/task-brief V150-9`.

All commands run inside the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v150-reports-research-workspaces`.

Three repo guards catch most mistakes in these tasks; run them whenever a workspace file changes:

```bash
cd frontend && npm test -- --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --watch=false
```

- `workspace-consistency.spec.ts`: no in-page `<h1>`, `sb-panel` for cards, `sb-toolbar` for filters, `auto-fit` grids, a freshness marker on every page with `sb-async`.
- `primitives.spec.ts`: a workspace file must not define the promoted classes `.head`, `.row-link`, `.note`, `.chips`, must not use a raw `<button>` without `sb-button`, and must not hard-code a hex colour. The small-print class in these components is therefore `.aside`, never `.note`.

---

### Task V150-8: The Research workspace

**Model:** sonnet — one page component over an existing store, built from existing primitives.

**Files:**
- Create: `frontend/src/app/workspaces/research/research.ts`
- Create: `frontend/src/app/workspaces/research/research.spec.ts`
- Create: `frontend/src/app/workspaces/research/research.routes.ts`

**Interfaces:**
- Consumes (V150-6): `ResearchStore` (signals `data`, `loading`, `error`, `filters`, `sort`, `registry`, `verdicts`, `instruments`, `familySize`, `verdictCounts`, `visible`, `pageSpec`, `selected`; methods `ensureLoaded`, `load`, `hydrate`, `setSort`, `setPage`, `select`), `LedgerFilters`, `filtersFromParams`, `filtersToParams`. (V150-4): `LedgerRow`, `StrategyRow`. Existing primitives: `Async`/`asyncInputs` (`ui/async`), `Button` (`ui/button`), `Chip`/`ChipTone` (`ui/chip`), `DataTable` (`ui/data-table/data-table`), `TextInput` (`ui/form-controls`), `Drawer`/`Panel` (`ui/layout`), `Segmented` (`ui/segmented`), `Toolbar` (`ui/toolbar`).
- Produces: `Research` (selector `sb-research`), `DISCLAIMER` (the fixed footer string, which V150-11 asserts equal to its own), `researchRoutes` (consumed by V150-12).

The route file is created here but **not wired**: `app.routes.ts` still points at the stub until V150-12.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/research/research.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, convertToParamMap, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { LedgerRow, ResearchLedger, StrategyRow } from '../../api/models';
import { ResearchStore, filtersFromParams } from '../../stores/research.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { DISCLAIMER, Research } from './research';

/* The page is a renderer over ResearchStore, so these tests look at what a
 * reader sees: which rows, how a missing figure and a missing record read,
 * what the q-value is said to be, and that the filters are the URL. */

const row = (over: Partial<LedgerRow>): LedgerRow => ({
  id: 'x', date: '2026-10-01', hypothesis: 'A gate', instrument: 'v2', n: 100, exp_r: 0.1,
  p: 0.04, verdict: 'FAIL', record: 'docs/superpowers/results/x.md', q: 0.08,
  record_exists: true, record_kind: 'results', ...over,
});

const LEDGER: ResearchLedger = {
  rows: [
    row({ id: 'e33-avwap', date: '2026-07-26', hypothesis: 'AVWAP levels', instrument: 'v1', n: null, exp_r: null, p: null, q: null, verdict: 'FAIL', record: 'docs/superpowers/plans/implemented/v35.md', record_exists: false, record_kind: 'plans' }),
    row({ id: 'v136-rs', date: '2026-10-06', hypothesis: 'RS gate lift', n: 120, exp_r: 0.12, p: 0.03, q: 0.06, verdict: 'PASS' }),
    row({ id: 'v140-screen', date: '2026-10-08', hypothesis: 'Idea screen', instrument: 'screen-v1', verdict: 'SCREEN-FAIL' }),
  ],
  q_family_m: 2,
  verdicts: ['PASS', 'FAIL', 'SCREEN-FAIL'],
  instruments: ['v1', 'v2', 'screen-v1'],
};

const strategy = (over: Partial<StrategyRow>): StrategyRow => ({
  strategy: 'RSI', status: 'VALIDATED', n: 80, win_rate: 55, expectancy_r: 0.21,
  window: '2024-01..2025-06', run_date: '2026-08-01', live_n: 12, live_wr: 50,
  delta_vs_oos: -5, decayed: false, evidence_decay: 'fresh', gate_description: null,
  win_rate_series: [], ...over,
});

const REGISTRY = [strategy({}), strategy({ strategy: 'EMA', status: 'WEAK', run_date: '2026-07-15', window: '2023-01..2024-06' })];

function create(
  ledger: ResearchLedger = LEDGER,
  registry: StrategyRow[] = REGISTRY,
): { fixture: ComponentFixture<Research>; store: InstanceType<typeof ResearchStore>; router: Router } {
  // The row drawer is a real <dialog>; jsdom has no showModal()/close().
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ResearchStore,
    ],
  });
  const fixture = TestBed.createComponent(Research);
  const store = TestBed.inject(ResearchStore);
  const http = TestBed.inject(HttpTestingController);
  store.load();
  http.expectOne('/api/v1/research/ledger').flush(ledger);
  http.expectOne('/api/v1/analytics/registry').flush({ registry });
  fixture.detectChanges();
  return { fixture, store, router: TestBed.inject(Router) };
}

const text = (fixture: ComponentFixture<Research>): string =>
  (fixture.nativeElement as HTMLElement).textContent?.replace(/\s+/g, ' ') ?? '';

const tables = (fixture: ComponentFixture<Research>): HTMLElement[] =>
  Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('sb-data-table'));

describe('Research', () => {
  it('lists the ledger newest first, with an em dash for a figure that was not recorded', () => {
    const { fixture } = create();
    const ledger = tables(fixture)[1].textContent ?? '';
    expect(ledger.indexOf('v140-screen')).toBeLessThan(ledger.indexOf('v136-rs'));
    expect(ledger.indexOf('v136-rs')).toBeLessThan(ledger.indexOf('e33-avwap'));
    expect(ledger).toContain('—');
    expect(ledger).not.toContain('null');
  });

  it('shows the registry with the tier, its run date and window, and WEAK muted', () => {
    const { fixture } = create();
    const registry = tables(fixture)[0];
    expect(registry.textContent).toContain('2026-08-01');
    expect(registry.textContent).toContain('2024-01..2025-06');
    const chips = Array.from(registry.querySelectorAll('sb-chip'));
    expect(chips.map((chip) => chip.textContent?.trim())).toEqual(['VALIDATED', 'WEAK']);
    expect(chips[0].innerHTML).not.toEqual(chips[1].innerHTML.replace('WEAK', 'VALIDATED'));
    expect(text(fixture)).toContain('Figures in R, pre-tax.');
  });

  it('says so when no strategy has a registry entry', () => {
    const { fixture } = create(LEDGER, []);
    expect(text(fixture)).toContain('No strategy has a registry entry');
  });

  it('offers one chip per server verdict, each with its count', () => {
    const { fixture } = create();
    const chips = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button.verdict'));
    expect(chips.map((chip) => chip.textContent?.replace(/\s+/g, ' ').trim()))
      .toEqual(['PASS 1', 'FAIL 1', 'SCREEN-FAIL 1']);
  });

  it('writes a verdict toggle to the URL, and the URL filters the rows', async () => {
    const { fixture, store, router } = create();
    const fail = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button.verdict'))
      .find((chip) => chip.textContent?.includes('FAIL') && !chip.textContent.includes('SCREEN'))!;
    fail.click();
    await fixture.whenStable();
    expect(router.url).toContain('verdict=FAIL');

    // What the route resolver does with that URL.
    store.hydrate(filtersFromParams(convertToParamMap({ verdict: 'FAIL', instrument: 'v1', q: 'avwap' })));
    fixture.detectChanges();
    const ledger = tables(fixture)[1].textContent ?? '';
    expect(ledger).toContain('e33-avwap');
    expect(ledger).not.toContain('v136-rs');
    expect(fail.getAttribute('aria-pressed')).toBe('true');
  });

  it('says what the q-value is, and over how many rows, in the drawer', () => {
    const { fixture, store } = create();
    store.select('v136-rs');
    fixture.detectChanges();
    const page = text(fixture);
    expect(page).toContain('reported, never gating — BH over all 2 ledger rows with a p-value, mixing instruments; filters do not change it');
    expect(page).toContain('window and method: see record');
    expect(page).toContain('docs/superpowers/results/x.md');
    expect(page).not.toContain('not in this deploy');
  });

  it('strikes through a record that is not in this deploy', () => {
    const { fixture, store } = create();
    store.select('e33-avwap');
    fixture.detectChanges();
    const record = (fixture.nativeElement as HTMLElement).querySelector('code.record')!;
    expect(record.classList.contains('missing')).toBe(true);
    expect(text(fixture)).toContain('not in this deploy');
  });

  it('carries the fixed footer and the read-only note', () => {
    const { fixture } = create();
    expect(text(fixture)).toContain(DISCLAIMER);
    expect(text(fixture)).toContain('this page never edits it');
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/research/research.spec.ts --watch=false`
Expected: FAIL: cannot resolve `./research`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/research/research.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';

import { LedgerRow, StrategyRow } from '../../api/models';
import { LedgerFilters, ResearchStore, filtersToParams } from '../../stores/research.store';
import { Async, asyncInputs } from '../../ui/async';
import { Button } from '../../ui/button';
import { Chip, ChipTone } from '../../ui/chip';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState, RowContext } from '../../ui/data-table/data-table.types';
import { TextInput } from '../../ui/form-controls';
import { Drawer, Panel } from '../../ui/layout';
import { SegmentOption, Segmented } from '../../ui/segmented';
import { Toolbar, ToolbarControl } from '../../ui/toolbar';

export const DISCLAIMER = 'Historical measurement on paper trades; not a forecast or advice.';

const HYPOTHESIS_MAX = 90;

/** A verdict's colour says how the measurement came out, never whether to
 *  act on it. A verdict added to the ledger later stays neutral. */
const VERDICT_TONE: Record<string, ChipTone> = {
  PASS: 'good',
  'SCREEN-PASS': 'good',
  FAIL: 'bad',
  'SCREEN-FAIL': 'bad',
  'NO-LIFT': 'neutral',
  OPEN: 'info',
  UNMEASURABLE: 'muted',
  WITHDRAWN: 'muted',
  'SCREEN-UNDERPOWERED': 'warn',
};

const fixed = (value: number | null, digits: number): string | null =>
  value === null ? null : value.toFixed(digits);

/**
 * Research — every pre-registration this repo has measured, and the badge
 * each strategy earned.
 *
 * Read-only. The ledger is a git-tracked record that ships inside the image,
 * so the page shows it as of the deployed build and offers no way to edit
 * it; rows are appended through `scripts/reports/preregistration_ledger.py`.
 *
 * Two stacked sections rather than tabs: the registry is about a dozen rows
 * and reads as context for the ledger below it.
 */
@Component({
  selector: 'sb-research',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, Button, Chip, DataTable, Drawer, Panel, Segmented, TextInput, Toolbar],
  host: { class: 'register-instrument' },
  template: `
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="no-data-yet"
      emptyTitle="No ledger"
      emptyHint="The pre-registration ledger is empty in this build."
      [skeletonRows]="10"
      [skeletonCols]="6"
      (retry)="store.load()"
    >
      <sb-panel heading="Strategy registry">
        <p class="caption">Figures in R, pre-tax.</p>
        <sb-async
          [empty]="store.registry().length === 0"
          [staleAsOf]="null"
          emptyReason="measured-zero"
          emptyTitle="No strategy has a registry entry"
        >
          <sb-data-table
            [rows]="store.registry()"
            [columns]="registryColumns()"
            [visible]="registryVisible"
            [rowKey]="strategyKey"
            [fillPage]="false"
          />
        </sb-async>
      </sb-panel>

      <sb-panel heading="Pre-registration ledger">
        <sb-toolbar [controls]="controls()">
          <div slot="verdict" class="verdicts" role="group" aria-label="Verdict">
            @for (verdict of store.verdicts(); track verdict) {
              <button sb-button variant="chip" type="button" class="verdict"
                      [class.on]="isOn(verdict)" [attr.aria-pressed]="isOn(verdict)"
                      (click)="toggleVerdict(verdict)">
                {{ verdict }} <span class="num">{{ store.verdictCounts()[verdict] }}</span>
              </button>
            }
          </div>
          <sb-segmented slot="instrument" label="Instrument" [options]="instrumentOptions()"
                        [value]="store.filters().instrument" (valueChange)="setInstrument($event)" />
          <sb-text-input slot="search" type="search" ariaLabel="Search id and hypothesis"
                         placeholder="Search id or hypothesis"
                         [value]="store.filters().search" (valueChange)="setSearch($event)" />
        </sb-toolbar>

        <sb-data-table
          [rows]="store.visible()"
          [columns]="ledgerColumns()"
          [visible]="ledgerVisible"
          [rowKey]="ledgerKey"
          [sort]="store.sort()"
          [pagination]="store.pageSpec()"
          [emptyState]="noMatch"
          (sortChange)="store.setSort($event)"
          (pageChange)="store.setPage($event)"
          (rowActivate)="store.select($event.id)"
        />
        <p class="caption">
          The ledger as of the deployed build. Append rows with
          <code>scripts/reports/preregistration_ledger.py</code>; this page never edits it.
        </p>
      </sb-panel>
    </sb-async>

    <p class="disclaimer">{{ disclaimer }}</p>

    <sb-drawer [open]="store.selected() !== null" [heading]="store.selected()?.id ?? ''"
               (closed)="store.select(null)">
      @if (store.selected(); as row) {
        <dl class="detail">
          <dt>Date</dt><dd>{{ row.date }}</dd>
          <dt>Hypothesis</dt><dd>{{ row.hypothesis }}</dd>
          <dt>Instrument</dt><dd>{{ row.instrument }}</dd>
          <dt>Verdict</dt><dd><sb-chip [label]="row.verdict" [tone]="verdictTone(row.verdict)" /></dd>
          <dt>N</dt><dd class="num">{{ row.n ?? '—' }}</dd>
          <dt>ExpR</dt><dd class="num">{{ figure(row.exp_r, 3) }}</dd>
          <dt>p</dt><dd class="num">{{ figure(row.p, 4) }}</dd>
          <dt>q</dt>
          <dd>
            <span class="num">{{ figure(row.q, 4) }}</span>
            <span class="aside">
              reported, never gating — BH over all {{ store.familySize() }} ledger rows with a
              p-value, mixing instruments; filters do not change it
            </span>
          </dd>
          <dt>Record</dt>
          <dd>
            <code class="record" [class.missing]="!row.record_exists">{{ row.record }}</code>
            <button sb-button variant="link" type="button" (click)="copy(row.record)">
              {{ copied() === row.record ? 'Copied' : 'Copy path' }}
            </button>
            @if (!row.record_exists) { <span class="aside">not in this deploy</span> }
            <span class="aside">window and method: see record</span>
          </dd>
        </dl>
      }
    </sb-drawer>

    <ng-template #tierCell let-row>
      <span class="tier">
        <sb-chip [label]="row.status" [tone]="tierTone(row.status)" />
        <span class="aside">{{ row.run_date ?? 'no run date' }} · {{ row.window ?? 'no window' }}</span>
      </span>
    </ng-template>
    <ng-template #verdictCell let-row>
      <sb-chip [label]="row.verdict" [tone]="verdictTone(row.verdict)" />
    </ng-template>
    <ng-template #hypothesisCell let-row>
      <span [attr.title]="row.hypothesis">{{ truncate(row.hypothesis) }}</span>
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .caption, .disclaimer { margin: 0; color: var(--text-faint); font-size: var(--text-micro); }
    .verdicts { display: flex; flex-wrap: wrap; gap: var(--space-6); }
    .verdict.on { color: var(--accent); }
    .tier { display: inline-flex; align-items: center; gap: var(--space-8); flex-wrap: wrap; }
    .aside { color: var(--text-faint); font-size: var(--text-micro); }
    .detail { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--space-6) var(--space-14); margin: 0; }
    .detail dt { color: var(--text-muted); }
    .detail dd { margin: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .record { font-family: var(--font-mono); overflow-wrap: anywhere; }
    .record.missing { text-decoration: line-through; color: var(--text-faint); }
  `,
})
export class Research {
  protected readonly store = inject(ResearchStore);
  private readonly router = inject(Router);

  protected readonly disclaimer = DISCLAIMER;
  protected readonly copied = signal<string | null>(null);

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.ledger.rows.length === 0 }),
  );

  private readonly tierCell = viewChild.required<TemplateRef<RowContext<StrategyRow>>>('tierCell');
  private readonly verdictCell = viewChild.required<TemplateRef<RowContext<LedgerRow>>>('verdictCell');
  private readonly hypothesisCell = viewChild.required<TemplateRef<RowContext<LedgerRow>>>('hypothesisCell');

  protected readonly registryVisible = ['strategy', 'status', 'n', 'expectancy_r', 'live_n', 'evidence_decay'];
  protected readonly registryColumns = computed<ColumnDef<StrategyRow>[]>(() => [
    { key: 'strategy', header: 'Strategy', value: (row) => row.strategy },
    { key: 'status', header: 'Badge tier', cell: this.tierCell() },
    { key: 'n', header: 'OOS N', numeric: true, value: (row) => row.n },
    { key: 'expectancy_r', header: 'OOS ExpR', numeric: true, value: (row) => fixed(row.expectancy_r, 2) },
    { key: 'live_n', header: 'Live N', numeric: true, value: (row) => row.live_n },
    { key: 'evidence_decay', header: 'Evidence', value: (row) => row.evidence_decay },
  ]);

  protected readonly ledgerVisible = ['date', 'id', 'hypothesis', 'instrument', 'n', 'exp_r', 'p', 'q', 'verdict'];
  protected readonly ledgerColumns = computed<ColumnDef<LedgerRow>[]>(() => [
    { key: 'date', header: 'Date', sortable: true, value: (row) => row.date },
    { key: 'id', header: 'Id', sortable: true, value: (row) => row.id },
    { key: 'hypothesis', header: 'Hypothesis', cell: this.hypothesisCell(), inlineFrom: 'md' },
    { key: 'instrument', header: 'Instrument', sortable: true, value: (row) => row.instrument, inlineFrom: 'md' },
    { key: 'n', header: 'N', numeric: true, sortable: true, value: (row) => row.n },
    { key: 'exp_r', header: 'ExpR', numeric: true, sortable: true, value: (row) => fixed(row.exp_r, 3) },
    { key: 'p', header: 'p', numeric: true, sortable: true, value: (row) => fixed(row.p, 4), inlineFrom: 'md' },
    { key: 'q', header: 'q', numeric: true, sortable: true, value: (row) => fixed(row.q, 4), inlineFrom: 'md' },
    { key: 'verdict', header: 'Verdict', sortable: true, cell: this.verdictCell() },
  ]);

  protected readonly noMatch: EmptyState = {
    title: 'No pre-registration matches these filters',
    hint: 'Clear a verdict, the instrument or the search.',
  };

  protected readonly instrumentOptions = computed<SegmentOption[]>(() => [
    { value: '', label: 'All' },
    ...this.store.instruments().map((instrument) => ({ value: instrument, label: instrument })),
  ]);

  protected readonly controls = computed<ToolbarControl[]>(() => {
    const filters = this.store.filters();
    return [
      { id: 'verdict', label: 'Verdict', active: filters.verdicts.length > 0 },
      { id: 'instrument', label: 'Instrument', inlineFrom: 'md', active: filters.instrument !== '' },
      { id: 'search', label: 'Search', inlineFrom: 'md', active: filters.search !== '' },
    ];
  });

  protected readonly strategyKey = (row: StrategyRow): string => row.strategy;
  protected readonly ledgerKey = (row: LedgerRow): string => row.id;

  protected isOn(verdict: string): boolean {
    return this.store.filters().verdicts.includes(verdict);
  }

  protected toggleVerdict(verdict: string): void {
    const current = this.store.filters().verdicts;
    const verdicts = current.includes(verdict)
      ? current.filter((v) => v !== verdict)
      : [...current, verdict];
    this.apply({ verdicts });
  }

  protected setInstrument(instrument: string): void {
    if (instrument !== this.store.filters().instrument) this.apply({ instrument });
  }

  protected setSearch(search: string): void {
    if (search !== this.store.filters().search) this.apply({ search });
  }

  protected verdictTone(verdict: string): ChipTone {
    return VERDICT_TONE[verdict] ?? 'neutral';
  }

  /** WEAK is muted so it is visibly not VALIDATED. The tier text itself is
   *  the server's, verbatim. */
  protected tierTone(status: string): ChipTone {
    return status === 'VALIDATED' ? 'good' : 'muted';
  }

  protected truncate(text: string): string {
    return text.length > HYPOTHESIS_MAX ? `${text.slice(0, HYPOTHESIS_MAX - 1)}…` : text;
  }

  protected figure(value: number | null, digits: number): string {
    return fixed(value, digits) ?? '—';
  }

  protected copy(path: string): void {
    void navigator.clipboard?.writeText(path);
    this.copied.set(path);
  }

  /** The URL is the filter state: the resolver reads it back into the store,
   *  so a reload and a shared link land on the same rows. */
  private apply(patch: Partial<LedgerFilters>): void {
    const next = { ...this.store.filters(), ...patch };
    this.router.navigate([], {
      queryParams: filtersToParams(next), queryParamsHandling: 'merge', replaceUrl: true,
    });
  }
}
```

Points that are easy to get wrong:

- The three toolbar controls are each **one element carrying `slot="<id>"`**, with no `@if` or `@for` around them (`sb-toolbar` moves them by DOM). The `@for` over verdicts is *inside* the `slot="verdict"` element, which is allowed.
- The inner `sb-async` around the registry table passes `[staleAsOf]="null"` so the freshness rule in `workspace-consistency.spec.ts` sees an explicit contract; the outer one carries the real stale timestamp.
- The setters compare before navigating: `sb-segmented` and `sb-text-input` emit `valueChange` when the store writes the value back, and an unconditional `navigate` there loops.

- [ ] **Step 4: Write the route file**

Create `frontend/src/app/workspaces/research/research.routes.ts`:

```ts
import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ResearchStore, filtersFromParams } from '../../stores/research.store';

/** The filters are the query string (so a filtered view is a link), which
 *  makes every filter change a navigation. The resolver therefore re-applies
 *  the filters each time but fetches only once per visit. No server event
 *  refreshes this page: the ledger and the registry change only on a deploy. */
export const researchRoutes: Routes = [{
  path: '',
  providers: [ResearchStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Research', onEvents()),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(ResearchStore);
      store.hydrate(filtersFromParams(route.queryParamMap));
      return store.ensureLoaded();
    }),
  },
  loadComponent: () => import('./research').then((m) => m.Research),
}];
```

- [ ] **Step 5: Run the spec and the guards**

```bash
cd frontend
npm test -- --include src/app/workspaces/research/research.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --watch=false
npx tsc -p tsconfig.app.json --noEmit
```

Expected: all pass, no type errors.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/app/workspaces/research/
git commit -m "feat(v150): Research workspace -- ledger browser with URL filters and a row drawer, plus the strategy registry"
```


---

### Task V150-9: The Expectancy-attribution tab

**Model:** sonnet — a renderer over a view model whose rules were decided and tested in V150-7.

**Blocked until** V150-7 is done.

**Files:**
- Create: `frontend/src/app/workspaces/reports/attribution-tab.ts`
- Create: `frontend/src/app/workspaces/reports/attribution-tab.spec.ts`

**Interfaces:**
- Consumes (V150-7): `ReportsStore.attribution(): AttributionView | null`, `ReadingView`, `LATEST_HEADING`, `R_CAPTION`. (V150-5): fixtures `ATTRIBUTION`, `NOT_RUN`, `ok`. Existing: `BarList` (`ui/bar-list`), `Chip` (`ui/chip`), `Panel` (`ui/layout`).
- Produces: `AttributionTab` (selector `sb-expectancy-attribution-tab`), `formatR(value: number | null): string`, `formatInterval(low: number | null, high: number | null): string` (V150-10 imports both formatters).

The component reads **only** `store.attribution()`. It never touches the wire model, so a field V150-5 renamed needs no change here.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/reports/attribution-tab.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { ExpectancyAttribution, ReportEnvelope } from '../../api/models';
import { LATEST_HEADING, R_CAPTION, ReportsStore } from '../../stores/reports.store';
import { ATTRIBUTION, NOT_RUN, ok } from '../../testing/report-fixtures';
import { AttributionTab, formatInterval, formatR } from './attribution-tab';

/* The fixture's latest reading says PREDICTIVE while its verdict of record
 * says WEAK, so "which one did the page show as the verdict" has a wrong
 * answer these tests can catch. */

function create(
  envelope: ReportEnvelope<ExpectancyAttribution> = ok(ATTRIBUTION),
): ComponentFixture<AttributionTab> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  const fixture = TestBed.createComponent(AttributionTab);
  TestBed.inject(ReportsStore).resolveTab('attribution').subscribe();
  TestBed.inject(HttpTestingController)
    .expectOne('/api/v1/reports/expectancy-attribution').flush(envelope);
  fixture.detectChanges();
  return fixture;
}

const host = (fixture: ComponentFixture<AttributionTab>): HTMLElement => fixture.nativeElement;
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
const panel = (fixture: ComponentFixture<AttributionTab>, heading: string): HTMLElement =>
  Array.from(host(fixture).querySelectorAll<HTMLElement>('sb-panel'))
    .find((el) => text(el).startsWith(heading))!;

describe('formatR / formatInterval', () => {
  it('signs positive values and writes an em dash for a missing one', () => {
    expect([formatR(0.224), formatR(-0.05), formatR(0), formatR(null)]).toEqual(['+0.22R', '-0.05R', '0.00R', '—']);
    expect(formatInterval(0.03, 0.41)).toBe('[+0.03R, +0.41R]');
    expect(formatInterval(null, 0.41)).toBe('—');
  });
});

describe('AttributionTab', () => {
  it('shows exactly one verdict chip: the verdict of record, with its date and N', () => {
    const fixture = create();
    const chips = Array.from(host(fixture).querySelectorAll('sb-chip'));
    expect(chips.map((chip) => text(chip))).toEqual(['WEAK']);
    expect(text(panel(fixture, 'Verdict of record'))).toContain('fixed 2026-10-12 · N 214');
    // The latest reading's own verdict word never appears as a verdict.
    expect(text(host(fixture))).not.toContain('PREDICTIVE');
  });

  it('puts the latest reading in its own descriptive block, one column per population', () => {
    const fixture = create();
    const latest = panel(fixture, LATEST_HEADING);
    expect(latest.querySelector('sb-chip')).toBeNull();
    expect(text(latest.querySelector('[data-population="Live"]'))).toContain('+0.22R [+0.03R, +0.41R]');
    expect(text(latest.querySelector('[data-population="TRAIN"]'))).toContain('+0.04R [-0.02R, +0.10R]');
  });

  it('shows each factor as delta and interval, with the candidate marker only below q 0.10', () => {
    const fixture = create();
    const row = (key: string) => text(host(fixture).querySelector(`[data-factor="${key}"]`));
    expect(row('trend_alignment')).toContain('+0.19R [+0.04R, +0.35R]');
    expect(row('trend_alignment')).toContain('screen candidate');
    expect(row('volume_confirmation')).toContain('+0.03R [-0.12R, +0.18R]');
    expect(row('volume_confirmation')).not.toContain('screen candidate');
    expect(panel(fixture, 'Factors').querySelector('sb-chip')).toBeNull();
  });

  it('draws a thin bucket withheld, with its N, and gives it no marker', () => {
    const fixture = create();
    const earnings = host(fixture).querySelector<HTMLElement>('[data-dimension="earnings_bucket"]')!;
    const withheld = earnings.querySelector('li.withheld')!;
    expect(text(withheld)).toContain('0-5');
    expect(text(withheld)).toContain('12');
    expect(text(earnings)).not.toContain('screen candidate');
  });

  it('marks a bucket below q 0.10 and names its population', () => {
    const fixture = create();
    const regime = host(fixture).querySelector<HTMLElement>('[data-dimension="regime"]')!;
    expect(text(regime)).toContain('screen candidate: bull (Live)');
    expect(regime.querySelectorAll('sb-bar-list').length).toBe(2);
  });

  it('repeats the reading per direction and per horizon', () => {
    const fixture = create();
    const short = text(host(fixture).querySelector('[data-split="Direction:short"]'));
    expect(short).toContain('-0.05R [-0.30R, +0.20R]');
    expect(short).toContain('44');
    expect(host(fixture).querySelectorAll('[data-split]').length).toBe(4);
  });

  it('states the looks count, the seed and the caption in the footer', () => {
    const fixture = create();
    const footer = text(host(fixture).querySelector('.footer'));
    expect(footer).toContain('looks: 37 — BH family for every q on this tab');
    expect(footer).toContain('Seed 42');
    expect(footer).toContain(R_CAPTION);
    expect(footer).toContain('descriptive — not a gate');
    expect(footer).toContain('Live: 2026-07-01..2026-10-09, N 214');
  });

  it('reads an absent population as "not in this run", never as zeros', () => {
    const fixture = create(ok({ ...ATTRIBUTION, populations: { live: ATTRIBUTION.populations.live, train: null } }));
    expect(text(host(fixture).querySelector('[data-population="TRAIN"]'))).toContain('not in this run');
    expect(text(host(fixture).querySelector('[data-dimension="regime"]'))).toContain('not in this run');
    expect(text(host(fixture))).not.toContain('0.00R');
  });

  it('renders nothing of its own when the report has not run', () => {
    const fixture = create(NOT_RUN);
    expect(host(fixture).querySelector('sb-panel')).toBeNull();
    expect(host(fixture).querySelector('sb-chip')).toBeNull();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/reports/attribution-tab.spec.ts --watch=false`
Expected: FAIL: cannot resolve `./attribution-tab`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/reports/attribution-tab.ts`:

```ts
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import {
  LATEST_HEADING,
  R_CAPTION,
  ReadingView,
  ReportsStore,
} from '../../stores/reports.store';
import { BarList } from '../../ui/bar-list';
import { Chip } from '../../ui/chip';
import { Panel } from '../../ui/layout';

/** Signed R to two places, or an em dash: an absent figure is never zero. */
export function formatR(value: number | null): string {
  if (value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}R`;
}

export function formatInterval(low: number | null, high: number | null): string {
  return low === null || high === null ? '—' : `[${formatR(low)}, ${formatR(high)}]`;
}

/**
 * Expectancy attribution (v146) — does confidence predict R, and which
 * buckets separate good trades from bad.
 *
 * Renders `ReportsStore.attribution()` and decides nothing: the verdict of
 * record, the thin flags and every q-value arrive already computed. Named
 * "Expectancy attribution" because the Analytics workspace has its own
 * "Attribution" tab, which answers a different question.
 *
 * One rule this template must keep: exactly ONE verdict chip, the verdict of
 * record. Everything below it is a reading, and is laid out as one.
 */
@Component({
  selector: 'sb-expectancy-attribution-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [BarList, Chip, Panel],
  template: `
    @if (store.attribution(); as view) {
      <sb-panel heading="Verdict of record">
        <div class="verdict">
          <sb-chip [label]="view.verdict.label" [tone]="view.verdict.tone" />
          <span class="aside">fixed {{ view.verdict.date }} · N {{ view.verdict.n }}</span>
          @if (view.verdict.inverted) {
            <span class="aside">inverted: the interval lies wholly below zero</span>
          }
        </div>
        <p class="caption">
          Does confidence predict R. Computed once, at the scheduled run; later runs never revise it.
        </p>
      </sb-panel>

      <sb-panel [heading]="latestHeading">
        <div class="pair">
          @for (reading of view.readings; track reading.population) {
            <div class="reading" [attr.data-population]="reading.population">
              <span class="population">{{ reading.population }}</span>
              @if (reading.present) {
                <dl>
                  <dt>Spearman ρ</dt><dd class="num">{{ rho(reading) }}</dd>
                  <dt>Top − bottom tercile ExpR</dt>
                  <dd class="num">{{ r(reading.spread) }} {{ interval(reading.ciLow, reading.ciHigh) }}</dd>
                  <dt>N</dt><dd class="num">{{ reading.n }}</dd>
                  <dt>Window</dt><dd>{{ reading.window ?? '—' }}</dd>
                </dl>
              } @else {
                <p class="aside">not in this run</p>
              }
            </div>
          }
        </div>
        <p class="caption">95% interval, week-clustered. {{ caption }}</p>
      </sb-panel>

      <sb-panel heading="Factors">
        <table class="figures">
          <thead>
            <tr><th>Factor</th><th>Live Δ ExpR</th><th>TRAIN Δ ExpR</th><th></th></tr>
          </thead>
          <tbody>
            @for (factor of view.factors; track factor.key) {
              <tr [attr.data-factor]="factor.key">
                <td>{{ factor.key }}</td>
                <td class="num">
                  @if (factor.live; as live) { {{ r(live.delta) }} {{ interval(live.ciLow, live.ciHigh) }} }
                  @else { <span class="aside">not in this run</span> }
                </td>
                <td class="num">
                  @if (factor.train; as train) { {{ r(train.delta) }} {{ interval(train.ciLow, train.ciHigh) }} }
                  @else { <span class="aside">not in this run</span> }
                </td>
                <td>@if (factor.candidate) { <span class="candidate">screen candidate</span> }</td>
              </tr>
            }
          </tbody>
        </table>
        <p class="caption">
          ExpR where the factor scored above zero, minus where it scored zero. A screen candidate
          (BH q &lt; 0.10) is a candidate for a Stage −2 screen, never a filter. {{ caption }}
        </p>
      </sb-panel>

      @for (dimension of view.dimensions; track dimension.key) {
        <sb-panel [heading]="dimension.label" [attr.data-dimension]="dimension.key">
          <div class="pair">
            <div>
              <span class="population">Live</span>
              @if (dimension.live; as rows) {
                <sb-bar-list [rows]="rows" mode="signed" [format]="r" />
              } @else { <p class="aside">not in this run</p> }
            </div>
            <div>
              <span class="population">TRAIN</span>
              @if (dimension.train; as rows) {
                <sb-bar-list [rows]="rows" mode="signed" [format]="r" />
              } @else { <p class="aside">not in this run</p> }
            </div>
          </div>
          @for (candidate of dimension.candidates; track candidate) {
            <span class="candidate">screen candidate: {{ candidate }}</span>
          }
          <p class="caption">ExpR per bucket. A faded bucket is below the report's floor: shown, not evidence. {{ caption }}</p>
        </sb-panel>
      }

      <sb-panel heading="Direction and horizon splits">
        <table class="figures">
          <thead>
            <tr><th>Split</th><th>Live top − bottom</th><th>Live N</th><th>TRAIN top − bottom</th><th>TRAIN N</th></tr>
          </thead>
          <tbody>
            @for (split of view.splits; track split.axis + split.name) {
              <tr [attr.data-split]="split.axis + ':' + split.name">
                <td>{{ split.axis }}: {{ split.name }}</td>
                <td class="num">{{ r(split.live?.spread ?? null) }} {{ interval(split.live?.ciLow ?? null, split.live?.ciHigh ?? null) }}</td>
                <td class="num">{{ split.live?.n ?? '—' }}</td>
                <td class="num">{{ r(split.train?.spread ?? null) }} {{ interval(split.train?.ciLow ?? null, split.train?.ciHigh ?? null) }}</td>
                <td class="num">{{ split.train?.n ?? '—' }}</td>
              </tr>
            }
          </tbody>
        </table>
        <p class="caption">The same reading per direction and per horizon, so a lift concentrated in one is visible. {{ caption }}</p>
      </sb-panel>

      <p class="footer">
        @for (reading of view.readings; track reading.population) {
          @if (reading.present) { {{ reading.population }}: {{ reading.window ?? 'window not recorded' }}, N {{ reading.n }}. }
        }
        Seed {{ view.seed }}. looks: {{ view.looks }} — BH family for every q on this tab.
        {{ caption }} descriptive — not a gate.
      </p>
    }
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .verdict { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-10); }
    .pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: var(--space-14); }
    .population { display: block; color: var(--text-muted); font-size: var(--text-micro); text-transform: uppercase; letter-spacing: 0.08em; }
    dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--space-4) var(--space-14); margin: var(--space-6) 0 0; }
    dt { color: var(--text-muted); }
    dd { margin: 0; }
    .figures { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .figures th { text-align: left; color: var(--text-muted); font-weight: 500; }
    .figures th, .figures td { padding: var(--space-4) var(--space-8); border-bottom: 1px solid var(--border); }
    .aside, .caption, .footer { color: var(--text-faint); font-size: var(--text-micro); }
    .caption, .footer { margin: var(--space-8) 0 0; }
    .candidate { display: inline-block; margin: var(--space-6) var(--space-8) 0 0; color: var(--info); font-size: var(--text-micro); }
  `,
})
export class AttributionTab {
  protected readonly store = inject(ReportsStore);

  protected readonly latestHeading = LATEST_HEADING;
  protected readonly caption = R_CAPTION;

  /** Arrow functions: `sb-bar-list` calls `format` detached from this class. */
  protected readonly r = (value: number | null): string => formatR(value);
  protected readonly interval = formatInterval;

  protected rho(reading: ReadingView): string {
    return reading.rho === null ? '—' : reading.rho.toFixed(2);
  }
}
```

The rule to keep while editing this template: **one `sb-chip`, in the "Verdict of record" panel, and nowhere else.** The first test counts the chips on the whole tab.

- [ ] **Step 4: Run the spec and the guards**

```bash
cd frontend
npm test -- --include src/app/workspaces/reports/attribution-tab.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --watch=false
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/app/workspaces/reports/attribution-tab.ts frontend/src/app/workspaces/reports/attribution-tab.spec.ts
git commit -m "feat(v150): Expectancy-attribution tab -- one verdict of record, descriptive readings, factors, buckets and splits"
```


---

### Task V150-10: The Gate-counterfactual tab

**Model:** sonnet — a renderer over a view model whose rules were decided and tested in V150-7.

**Blocked until** V150-7 and V150-9 are done (it imports V150-9's two formatters).

**Files:**
- Create: `frontend/src/app/workspaces/reports/gates-tab.ts`
- Create: `frontend/src/app/workspaces/reports/gates-tab.spec.ts`

**Interfaces:**
- Consumes (V150-7): `ReportsStore.gates(): GateCellView[] | null`, `GateCellView`, `FLOOR_N_DISPLAY`, `LATEST_HEADING`, `OVER_CAP_NOTE`, `R_CAPTION`, and in the spec `PORTFOLIO_NOTE`, `HOLDOUT_NOTE`. (V150-9): `formatR`, `formatInterval` from `./attribution-tab`. (V150-5): fixtures `GATES`, `NOT_RUN`, `ok`. Existing: `Chip`, `DataTable`, `ColumnDef`, `RowContext`, `Panel`.
- Produces: `GatesTab` (selector `sb-gates-tab`).

**Deviation from the spec, recorded:** the spec asks for the latest reading "under a 'Latest reading — descriptive' column group". `sb-data-table` has no column groups and this plan adds no primitive, so the three columns are headed `Latest: …` and a caption above the table states that they are the latest reading and descriptive. The words `Latest reading — descriptive` appear on the tab verbatim.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/reports/gates-tab.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { GateCounterfactual, ReportEnvelope } from '../../api/models';
import {
  HOLDOUT_NOTE,
  LATEST_HEADING,
  OVER_CAP_NOTE,
  PORTFOLIO_NOTE,
  R_CAPTION,
  ReportsStore,
} from '../../stores/reports.store';
import { GATES, NOT_RUN, ok } from '../../testing/report-fixtures';
import { GatesTab } from './gates-tab';

/* The fixture's live `rs` cell is WAITING at N 29 and still carries a latest
 * reading on the wire, and its live `risk_cap` cell has a verdict of record
 * (GATE EARNS) that differs from its latest reading (INCONCLUSIVE). Both are
 * there so the wrong rendering has something to show. */

function create(
  envelope: ReportEnvelope<GateCounterfactual> = ok(GATES),
): ComponentFixture<GatesTab> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  const fixture = TestBed.createComponent(GatesTab);
  TestBed.inject(ReportsStore).resolveTab('gates').subscribe();
  TestBed.inject(HttpTestingController)
    .expectOne('/api/v1/reports/gate-counterfactual').flush(envelope);
  fixture.detectChanges();
  return fixture;
}

const host = (fixture: ComponentFixture<GatesTab>): HTMLElement => fixture.nativeElement;
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';

/** The table's body rows that are cells (not expansion rows), in order. */
const cellRows = (fixture: ComponentFixture<GatesTab>): HTMLElement[] =>
  Array.from(host(fixture).querySelectorAll<HTMLElement>('sb-data-table tbody tr'))
    .filter((tr) => !tr.classList.contains('expansion'));

const rowFor = (fixture: ComponentFixture<GatesTab>, gate: string, population: string): HTMLElement =>
  cellRows(fixture).find((tr) => text(tr).startsWith(`${gate} ${population}`)
    || (text(tr).includes(gate) && text(tr).includes(population)))!;

/** Open a cell's detail through the table's own expand control. */
function expand(fixture: ComponentFixture<GatesTab>, gate: string, population: string): HTMLElement {
  rowFor(fixture, gate, population).querySelector<HTMLButtonElement>('button[aria-expanded]')!.click();
  fixture.detectChanges();
  return host(fixture).querySelector<HTMLElement>(`[data-cell="${gate}:${population.toLowerCase()}"]`)!;
}

describe('GatesTab', () => {
  it('lists one row per cell, in the report order', () => {
    const fixture = create();
    expect(cellRows(fixture).length).toBe(6);
    expect(text(cellRows(fixture)[0])).toContain('rs');
    expect(text(cellRows(fixture)[5])).toContain('compression');
  });

  it('shows WAITING with N progress and nothing else below the floor', () => {
    const fixture = create();
    const waiting = rowFor(fixture, 'rs', 'Live');
    expect(text(waiting)).toContain('WAITING');
    expect(text(waiting)).toContain('N 29 / 30');
    expect(waiting.querySelector('progress')).not.toBeNull();
    // No badge, and none of the latest reading the wire still carries.
    expect(waiting.querySelector('sb-chip')).toBeNull();
    expect(text(waiting)).not.toContain('-0.30R');
    expect(text(waiting)).not.toContain('[');
    expect(text(waiting)).not.toContain('0.40');
  });

  it('shows the verdict of record as the verdict, and a different latest reading apart', () => {
    const fixture = create();
    const riskCap = rowFor(fixture, 'risk_cap', 'Live');
    expect(text(riskCap.querySelector('sb-chip'))).toBe('GATE EARNS');
    expect(text(riskCap)).toContain('fixed 2026-10-14 · N 31');
    expect(text(riskCap)).toContain('-0.08R');
    expect(text(riskCap)).toContain('[-0.31R, +0.12R]');
    expect(text(riskCap)).toContain('0.44');
    // The latest reading's own verdict word is never printed.
    expect(text(riskCap)).not.toContain('INCONCLUSIVE');
    expect(text(host(fixture))).toContain(LATEST_HEADING);
  });

  it('shows a fixed note where a gate has no TRAIN population', () => {
    const fixture = create();
    const rsTrain = rowFor(fixture, 'rs', 'TRAIN');
    expect(text(rsTrain)).toContain('no TRAIN population');
    expect(rsTrain.querySelector('sb-chip')).toBeNull();
  });

  it('puts the portfolio-state and holdout notes beside a live verdict', () => {
    const fixture = create();
    const detail = expand(fixture, 'risk_cap', 'Live');
    expect(text(detail)).toContain(PORTFOLIO_NOTE);
    expect(text(detail)).toContain(HOLDOUT_NOTE);
    expect(text(detail)).toContain('Over these trades, the gate’s blocked setups returned less than its taken ones.');
  });

  it('labels TRAIN compression in-sample', () => {
    const fixture = create();
    const detail = expand(fixture, 'compression', 'TRAIN');
    expect(text(detail)).toContain('in-sample');
    expect(text(detail)).not.toContain(PORTFOLIO_NOTE);
  });

  it('shows the dollar-risk figure and the over-cap tag on a risk_cap row', () => {
    const fixture = create();
    const detail = expand(fixture, 'risk_cap', 'Live');
    expect(text(detail)).toContain('risk_cap_exceeded');
    expect(text(detail)).toContain('$412.50');
    expect(text(detail)).toContain(`over-cap: ${OVER_CAP_NOTE}`);
    expect(text(detail)).toContain('+0.02R / 48%');
    expect(text(detail)).toContain(R_CAPTION);
  });

  it('states the BH family and that a verdict changes no gate', () => {
    const fixture = create();
    const footer = text(host(fixture).querySelector('.footer'));
    expect(footer).toContain('BH family: the five verdict cells');
    expect(footer).toContain(R_CAPTION);
    expect(footer).toContain('a change goes through its own pre-registration');
  });

  it('renders nothing of its own when the report has not run', () => {
    const fixture = create(NOT_RUN);
    expect(host(fixture).querySelector('sb-panel')).toBeNull();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/reports/gates-tab.spec.ts --watch=false`
Expected: FAIL: cannot resolve `./gates-tab`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/reports/gates-tab.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  viewChild,
} from '@angular/core';

import {
  FLOOR_N_DISPLAY,
  GateCellView,
  LATEST_HEADING,
  OVER_CAP_NOTE,
  R_CAPTION,
  ReportsStore,
} from '../../stores/reports.store';
import { Chip } from '../../ui/chip';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext } from '../../ui/data-table/data-table.types';
import { Panel } from '../../ui/layout';
import { formatInterval, formatR } from './attribution-tab';

const percent = (value: number | null): string =>
  value === null ? '—' : `${(value * 100).toFixed(0)}%`;

/**
 * Gate counterfactual (v147) — does each gate earn the trades it blocks.
 *
 * One row per verdict cell (gate x population). The verdict column is the
 * verdict of record; the three "Latest" columns are the newest reading and
 * are descriptive only. A cell below v147's floor shows WAITING and an N
 * progress figure, and nothing else: no badge, no interval, no difference.
 *
 * Renders `ReportsStore.gates()` and decides nothing. A verdict here changes
 * no gate; that takes its own pre-registration.
 */
@Component({
  selector: 'sb-gates-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip, DataTable, Panel],
  template: `
    @if (store.gates(); as cells) {
      <sb-panel heading="Verdicts">
        <p class="caption">
          Verdict: the verdict of record. The three "Latest" columns: {{ latestHeading }}.
        </p>
        <sb-data-table
          [rows]="cells"
          [columns]="columns()"
          [visible]="visible"
          [rowKey]="cellKey"
          [expansion]="detail"
          [fillPage]="false"
        />
        <p class="footer">
          BH family: the five verdict cells. {{ caption }}
          A verdict here changes no gate; a change goes through its own pre-registration.
        </p>
      </sb-panel>
    }

    <ng-template #verdictCell let-cell>
      @switch (cell.state) {
        @case ('verdict') {
          <span class="verdict">
            <sb-chip [label]="cell.verdict.label" [tone]="cell.verdict.tone" />
            <span class="aside">fixed {{ cell.verdict.date }} · N {{ cell.verdict.n }}</span>
          </span>
        }
        @case ('waiting') {
          <span class="waiting">
            <span class="word">WAITING</span>
            <progress [value]="cell.n" [max]="floor" [attr.aria-label]="'N ' + cell.n + ' of ' + floor"></progress>
            <span class="num">N {{ cell.n }} / {{ floor }}</span>
          </span>
        }
        @default { <span class="aside">{{ cell.note }}</span> }
      }
    </ng-template>

    <ng-template #detail let-cell>
      <div class="detail" [attr.data-cell]="cell.id">
        @if (cell.verdict; as verdict) { <p class="sentence">{{ verdict.sentence }}</p> }
        @for (label of cell.labels; track label) { <span class="label">{{ label }}</span> }
        @if (cell.rows.length) {
          <table class="figures">
            <thead>
              <tr>
                <th>Reason</th><th>Blocked N</th><th>No-plan N</th><th>Fill rate</th>
                <th>Blocked ExpR / WR</th><th>Taken ExpR / WR</th>
                <th>Near-miss ExpR (N)</th><th>Rest ExpR (N)</th><th>Dollar risk</th>
              </tr>
            </thead>
            <tbody>
              @for (row of cell.rows; track row.reason) {
                <tr>
                  <td>{{ row.reason }}</td>
                  <td class="num">{{ row.blockedN }}</td>
                  <td class="num">{{ row.noPlanN }}</td>
                  <td class="num">{{ pct(row.fillRate) }}</td>
                  <td class="num">{{ r(row.blockedExpR) }} / {{ pct(row.blockedWinRate) }}</td>
                  <td class="num">{{ r(row.takenExpR) }} / {{ pct(row.takenWinRate) }}</td>
                  <td class="num">{{ r(row.nearMissExpR) }} ({{ row.nearMissN ?? '—' }})</td>
                  <td class="num">{{ r(row.restExpR) }} ({{ row.restN ?? '—' }})</td>
                  <td class="num">
                    @if (row.dollarRisk !== null) { {{ dollars(row.dollarRisk) }} } @else { — }
                    @if (row.overCap) { <span class="over-cap">over-cap: {{ overCapNote }}</span> }
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <p class="caption">{{ caption }}</p>
        } @else {
          <p class="aside">No blocked-setup rows for this cell.</p>
        }
      </div>
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .verdict, .waiting { display: inline-flex; align-items: center; gap: var(--space-8); flex-wrap: wrap; }
    .word { font-family: var(--font-mono); color: var(--text-muted); letter-spacing: 0.08em; }
    progress { width: 5rem; height: 6px; }
    .detail { display: grid; gap: var(--space-8); }
    .sentence { margin: 0; }
    .label, .over-cap { display: inline-block; color: var(--warn); font-size: var(--text-micro); }
    .label { margin-right: var(--space-10); }
    .figures { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .figures th { text-align: left; color: var(--text-muted); font-weight: 500; }
    .figures th, .figures td { padding: var(--space-4) var(--space-8); border-bottom: 1px solid var(--border); }
    .aside, .caption, .footer { color: var(--text-faint); font-size: var(--text-micro); }
    .caption, .footer { margin: var(--space-8) 0; }
  `,
})
export class GatesTab {
  protected readonly store = inject(ReportsStore);

  protected readonly latestHeading = LATEST_HEADING;
  protected readonly caption = R_CAPTION;
  protected readonly overCapNote = OVER_CAP_NOTE;
  protected readonly floor = FLOOR_N_DISPLAY;

  private readonly verdictCell = viewChild.required<TemplateRef<RowContext<GateCellView>>>('verdictCell');

  protected readonly visible = ['gate', 'population', 'verdict', 'difference', 'interval', 'q'];
  /** The three Latest columns read from `cell.latest`, which the store nulls
   *  while a cell is waiting, so they are blank exactly when they must be. */
  protected readonly columns = computed<ColumnDef<GateCellView>[]>(() => [
    { key: 'gate', header: 'Gate', value: (cell) => cell.gate },
    { key: 'population', header: 'Population', value: (cell) => cell.population },
    { key: 'verdict', header: 'Verdict of record', cell: this.verdictCell() },
    { key: 'difference', header: 'Latest: blocked − taken', numeric: true,
      value: (cell) => (cell.latest ? formatR(cell.latest.difference) : '') },
    { key: 'interval', header: 'Latest: 95% CI', numeric: true,
      value: (cell) => (cell.latest ? formatInterval(cell.latest.ciLow, cell.latest.ciHigh) : '') },
    { key: 'q', header: 'Latest: BH q', numeric: true,
      value: (cell) => (cell.latest?.q === null || cell.latest?.q === undefined ? '' : cell.latest.q.toFixed(2)) },
  ]);

  protected readonly cellKey = (cell: GateCellView): string => cell.id;
  protected readonly r = formatR;
  protected readonly pct = percent;

  protected dollars(value: number): string {
    return `$${value.toFixed(2)}`;
  }
}
```

Points that are easy to get wrong:

- **WAITING is plain text plus a `<progress>` element, never an `sb-chip`.** A chip there would be the muted provisional badge the quant panel blocked.
- The three `Latest` columns return `''` (blank), not `null`, when `cell.latest` is null. `null` would render the table's em dash, which reads as "a figure exists but is unknown".
- `[expansion]="detail"` refers to the `#detail` template variable declared lower in the same template.

- [ ] **Step 4: Run the spec and the guards**

```bash
cd frontend
npm test -- --include src/app/workspaces/reports/gates-tab.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --watch=false
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/app/workspaces/reports/gates-tab.ts frontend/src/app/workspaces/reports/gates-tab.spec.ts
git commit -m "feat(v150): Gate-counterfactual tab -- verdict of record per cell, WAITING with N progress, labelled detail rows"
```

