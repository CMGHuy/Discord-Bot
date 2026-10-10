# v150 Reports and Research workspaces: Part 4, the Reports shell, route rewiring and close-out

> Part of the v150 plan. Header, Global Constraints, the blocked-task gate, the wire shapes and the parallelisation map are in [`_0-index`](2026-10-09-v150-reports-research-workspaces_0-index.md). **Never read this file whole**: `/task-brief V150-12`.

All commands run inside the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v150-reports-research-workspaces`.

The repo guards named at the top of [`_3-research-and-report-tabs`](2026-10-09-v150-reports-research-workspaces_3-research-and-report-tabs.md) apply to every workspace file here too: the small-print class is `.aside`, never `.note`.

---

### Task V150-11: The Reports shell and its route

**Model:** sonnet — a thin shell (tab bar, freshness, not-run state, footer) over two finished tabs.

**Blocked until** V150-9 and V150-10 are done. V150-8 must also be done: the spec imports Research's `DISCLAIMER` to assert the two footers are one string.

**Files:**
- Create: `frontend/src/app/workspaces/reports/reports.ts`
- Create: `frontend/src/app/workspaces/reports/reports.spec.ts`
- Create: `frontend/src/app/workspaces/reports/reports.routes.ts`

**Interfaces:**
- Consumes (V150-7): `ReportsStore` (signals `tab`, `data`, `loading`, `error`, `notRun`, `generatedAt`; methods `resolveTab`, `load`), `ReportTab`, `tabFromParams`. (V150-9, V150-10): `AttributionTab`, `GatesTab`. (V150-8): `DISCLAIMER` from `../research/research`. (V150-2): the production command documented in `DEPLOY_HETZNER.md`. Existing: `Async`/`asyncInputs`, `Freshness` (`ui/freshness`), `Tab`/`TabBar` (`ui/layout`), `SectionHead` (`ui/section-head`).
- Produces: `Reports` (selector `sb-reports`), `DISCLAIMER`, `reportsRoutes` (consumed by V150-12).

- [ ] **Step 1: Confirm the two script names**

The "Not yet run" hint names each report's script. Check both exist on `main` under these names:

```bash
git ls-files scripts/reports/expectancy_attribution.py scripts/reports/gate_counterfactual_report.py
```

Expected: both paths print. If v146 or v147 named its script differently, use the real name in `RUN_COMMAND` (Step 4) and in the two spec assertions that quote it.

- [ ] **Step 2: Write the failing spec**

Create `frontend/src/app/workspaces/reports/reports.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { ReportTab, ReportsStore } from '../../stores/reports.store';
import { ATTRIBUTION, GATES, NOT_RUN, ok } from '../../testing/report-fixtures';
import { DISCLAIMER as RESEARCH_DISCLAIMER } from '../research/research';
import { DISCLAIMER, Reports } from './reports';

const URLS: Record<ReportTab, string> = {
  attribution: '/api/v1/reports/expectancy-attribution',
  gates: '/api/v1/reports/gate-counterfactual',
};

function create(): {
  fixture: ComponentFixture<Reports>;
  store: InstanceType<typeof ReportsStore>;
  http: HttpTestingController;
  router: Router;
} {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  return {
    fixture: TestBed.createComponent(Reports),
    store: TestBed.inject(ReportsStore),
    http: TestBed.inject(HttpTestingController),
    router: TestBed.inject(Router),
  };
}

const host = (fixture: ComponentFixture<Reports>): HTMLElement => fixture.nativeElement;
const text = (fixture: ComponentFixture<Reports>): string =>
  host(fixture).textContent?.replace(/\s+/g, ' ') ?? '';

describe('Reports', () => {
  it('opens on Expectancy attribution and fetches only that report', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    http.expectNone(URLS.gates);
    fixture.detectChanges();
    expect(host(fixture).querySelector('sb-expectancy-attribution-tab')).not.toBeNull();
    expect(host(fixture).querySelector('sb-gates-tab')).toBeNull();
    expect(text(fixture)).toContain('Expectancy attribution');
  });

  it('shows the other tab once the store is on it', () => {
    const { fixture, store, http } = create();
    store.resolveTab('gates').subscribe();
    http.expectOne(URLS.gates).flush(ok(GATES));
    http.expectNone(URLS.attribution);
    fixture.detectChanges();
    expect(host(fixture).querySelector('sb-gates-tab')).not.toBeNull();
    expect(host(fixture).querySelector('sb-expectancy-attribution-tab')).toBeNull();
  });

  it('writes a tab switch to the URL, and leaves no ?tab= for the default', async () => {
    const { fixture, store, http, router } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    fixture.detectChanges();
    const tabs = Array.from(host(fixture).querySelectorAll<HTMLElement>('sb-tab-bar [role="tab"]'));
    tabs.find((tab) => tab.textContent?.includes('Gate counterfactual'))!.click();
    await fixture.whenStable();
    expect(router.url).toContain('tab=gates');
    tabs.find((tab) => tab.textContent?.includes('Expectancy attribution'))!.click();
    await fixture.whenStable();
    expect(router.url).not.toContain('tab=');
  });

  it('says "Not yet run" with the production command, and draws no figures', () => {
    const { fixture, store, http } = create();
    store.resolveTab('gates').subscribe();
    http.expectOne(URLS.gates).flush(NOT_RUN);
    fixture.detectChanges();
    expect(text(fixture)).toContain('Not yet run');
    expect(text(fixture)).toContain('scripts/ops/ssh-hetzner.sh');
    expect(text(fixture)).toContain('scripts/reports/gate_counterfactual_report.py');
    expect(host(fixture).querySelector('sb-gates-tab')).toBeNull();
    expect(host(fixture).querySelector('sb-data-table')).toBeNull();
  });

  it('names the attribution script on the attribution tab', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(NOT_RUN);
    fixture.detectChanges();
    expect(text(fixture)).toContain('scripts/reports/expectancy_attribution.py');
  });

  it('shows the error state, not "Not yet run", when the report is unreadable', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(
      { error: { code: 'report_unreadable', message: 'ValueError: Expecting value' } },
      { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect(text(fixture)).not.toContain('Not yet run');
    expect(host(fixture).querySelector('sb-expectancy-attribution-tab')).toBeNull();
  });

  it('marks when the result was generated', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    fixture.detectChanges();
    const freshness = host(fixture).querySelector('sb-freshness')!;
    expect(freshness.textContent).toContain('as of');
    expect(freshness.textContent).not.toContain('stale');
  });

  it('carries the fixed footer, the same one Research carries', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    fixture.detectChanges();
    expect(text(fixture)).toContain(DISCLAIMER);
    expect(DISCLAIMER).toBe(RESEARCH_DISCLAIMER);
  });
});
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/reports/reports.spec.ts --watch=false`
Expected: FAIL: cannot resolve `./reports`.

- [ ] **Step 4: Write the shell**

Create `frontend/src/app/workspaces/reports/reports.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';

import { ReportTab, ReportsStore } from '../../stores/reports.store';
import { Async, asyncInputs } from '../../ui/async';
import { Freshness } from '../../ui/freshness';
import { Tab, TabBar } from '../../ui/layout';
import { SectionHead } from '../../ui/section-head';
import { AttributionTab } from './attribution-tab';
import { GatesTab } from './gates-tab';

export const DISCLAIMER = 'Historical measurement on paper trades; not a forecast or advice.';

/** The production run path, per report (`docs/deploy/DEPLOY_HETZNER.md`). */
const RUN_COMMAND: Record<ReportTab, string> = {
  attribution:
    'bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/expectancy_attribution.py"',
  gates:
    'bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/gate_counterfactual_report.py"',
};

/**
 * Reports — what the measurements say about entries and gates.
 *
 * A shell: the tab strip, the freshness marker, the not-yet-run state and
 * the fixed footer. Each tab is its own component and fetches only its own
 * report (the route resolver calls `ReportsStore.resolveTab`).
 *
 * "Not yet run" is a state, not an error: a report exists only after someone
 * runs its script on the VM, so the page says how rather than showing a zero
 * or an empty axis.
 */
@Component({
  selector: 'sb-reports',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, AttributionTab, Freshness, GatesTab, SectionHead, TabBar],
  host: { class: 'register-instrument' },
  template: `
    <sb-section-head>
      <!-- A report has no cadence, so it is never flagged stale: the
           timestamp itself is the information. -->
      <sb-freshness actions [at]="store.generatedAt()" [staleAfterSec]="neverStale" />
    </sb-section-head>

    <sb-tab-bar [tabs]="tabs" [active]="store.tab()" (activeChange)="goToTab($event)" />

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="no-data-yet"
      emptyTitle="Not yet run"
      [emptyHint]="runHint()"
      [skeletonRows]="8"
      [skeletonCols]="5"
      (retry)="store.load()"
    >
      @switch (store.tab()) {
        @case ('gates') { <sb-gates-tab /> }
        @default { <sb-expectancy-attribution-tab /> }
      }
    </sb-async>

    <p class="disclaimer">{{ disclaimer }}</p>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .disclaimer { margin: 0; color: var(--text-faint); font-size: var(--text-micro); }
  `,
})
export class Reports {
  protected readonly store = inject(ReportsStore);
  private readonly router = inject(Router);

  protected readonly disclaimer = DISCLAIMER;
  protected readonly neverStale = Number.MAX_SAFE_INTEGER;
  protected readonly tabs: Tab[] = [
    { id: 'attribution', label: 'Expectancy attribution' },
    { id: 'gates', label: 'Gate counterfactual' },
  ];

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (envelope) => envelope.status === 'not_run' }),
  );

  protected readonly runHint = computed(
    () => `Run it on the VM: ${RUN_COMMAND[this.store.tab()]}`,
  );

  /** The default tab leaves no `?tab=` behind. */
  protected goToTab(tab: string): void {
    this.router.navigate([], {
      queryParams: { tab: tab === 'attribution' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
```

`asyncInputs` treats `not_run` as the *empty* state, so `sb-async` renders "Not yet run" with the command and the tab component is never created: no zero and no empty axis can appear.

- [ ] **Step 5: Write the route file**

Create `frontend/src/app/workspaces/reports/reports.routes.ts`:

```ts
import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ReportsStore, tabFromParams } from '../../stores/reports.store';

/** `?tab=attribution|gates` picks the report, and each navigation fetches
 *  only that one. No server event refreshes this page: a result changes only
 *  when someone runs a report script on the VM. */
export const reportsRoutes: Routes = [{
  path: '',
  providers: [ReportsStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Reports', onEvents()),
  resolve: {
    ready: resolveRoute((route) =>
      inject(ReportsStore).resolveTab(tabFromParams(route.queryParamMap))),
  },
  loadComponent: () => import('./reports').then((m) => m.Reports),
}];
```

- [ ] **Step 6: Run the spec and the guards**

```bash
cd frontend
npm test -- --include "src/app/workspaces/reports/*.spec.ts" --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --watch=false
npx tsc -p tsconfig.app.json --noEmit
```

Expected: all pass, no type errors.

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend/src/app/workspaces/reports/reports.ts frontend/src/app/workspaces/reports/reports.spec.ts frontend/src/app/workspaces/reports/reports.routes.ts
git commit -m "feat(v150): Reports workspace shell -- two routed tabs, freshness, a not-yet-run state with the VM command"
```


---

### Task V150-12: Point both routes at the real pages and delete the placeholder

**Model:** haiku — two route edits, one test replaced, one directory deleted; every diff is given by this brief.

**Blocked until** V150-8 and V150-11 are done.

**Files:**
- Modify: `frontend/src/app/app.routes.ts` (the `research` and `reports` entries, about lines 106-115)
- Modify: `frontend/src/app/app.routes.spec.ts` (imports; the stub test, about lines 96-105; the readiness list, about line 110)
- Delete: `frontend/src/app/workspaces/stubs/` (`planned-workspace.ts`, `planned-workspace.spec.ts`, `reports.routes.ts`, `research.routes.ts`)

**Interfaces:**
- Consumes: `researchRoutes` (V150-8), `reportsRoutes` (V150-11).
- Produces: `/research` and `/reports` serve the real workspaces.

- [ ] **Step 1: Rewrite the two route entries**

In `frontend/src/app/app.routes.ts`, replace the two entries with:

```ts
  {
    path: 'research', canMatch: [authGuard], title: 'Research',
    data: { subtitle: 'Every pre-registration and its verdict' },
    loadChildren: () => import('./workspaces/research/research.routes').then((m) => m.researchRoutes),
  },
  {
    path: 'reports', canMatch: [authGuard], title: 'Reports',
    data: { subtitle: 'What the measurements say about entries and gates' },
    loadChildren: () => import('./workspaces/reports/reports.routes').then((m) => m.reportsRoutes),
  },
```

- [ ] **Step 2: Update the routes spec**

In `frontend/src/app/app.routes.spec.ts`:

(a) Add at the very top of the file:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

```

(b) Replace the whole test `it('exposes Research and Reports as guarded, titled lazy stubs', …)` with:

```ts
  it('serves Research and Reports as real pages, with no placeholder left', async () => {
    for (const path of ['research', 'reports']) {
      const route = routes.find((item) => item.path === path);
      expect(route?.title).toBeTruthy();
      expect(String(route?.data?.['subtitle'])).not.toMatch(/planned/i);
      // The stub routes carried a `planned` blurb in their data.
      const children = await route!.loadChildren!() as Routes;
      expect(children[0].data?.['planned']).toBeUndefined();
      expect(await children[0].loadComponent!()).toBeDefined();
    }
    expect(readFileSync(join(process.cwd(), 'src/app/app.routes.ts'), 'utf8'))
      .not.toContain('workspaces/stubs');
  });
```

(c) In `describe('route data readiness contract', …)`, add both paths to `expected`:

```ts
  const expected = [
    'dashboard', 'trades', 'trades/:id', 'analytics', 'calendar', 'watchlist',
    'watchlist/:symbol', 'risk', 'system', 'versions', 'research', 'reports',
  ] as const;
```

That contract (guarded, lazy, route-scoped providers, `runGuardsAndResolvers: 'always'`, a `ready` resolver) is what supersedes the old stub test's guard and title checks.

- [ ] **Step 3: Delete the placeholder**

```bash
git rm -r frontend/src/app/workspaces/stubs
git grep -n "workspaces/stubs\|PlannedWorkspace\|planned-workspace" -- frontend/src
```

Expected: the second command prints only the one line in `app.routes.spec.ts` that asserts the string is absent.

- [ ] **Step 4: Run the route spec, the guards and a type-check**

```bash
cd frontend
npm test -- --include src/app/app.routes.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --watch=false
npx tsc -p tsconfig.app.json --noEmit
```

Expected: all pass, no type errors.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts
git commit -m "feat(v150): Research and Reports routes serve the real workspaces; the planned-workspace stub is deleted"
```


---

### Task V150-13: Full-suite verification

**Model:** sonnet — runs each touched suite once and fixes forward from whatever they name.

**Files:** none edited unless a run names a regression.

- [ ] **Step 1: Confirm every task landed**

```bash
git log --oneline main..HEAD
for f in docs/superpowers/plans/2026-10-09-v150-reports-research-workspaces_*.md; do
  echo "$(basename $f): $(grep -o '^### Task V150-[0-9]*' $f | tr '\n' ' ')"
done
```

Expected: the commits of V150-1 .. V150-12, and the task ids V150-1 .. V150-13 across the parts, none missing.

- [ ] **Step 2: Complexity over the Python the plan touched**

```bash
python -m radon cc -s -n C swingbot/admin/api_v1/research.py swingbot/admin/api_v1/reports.py
```

Expected: no output. (If v149's gate has landed, also run `python scripts/dev/complexity_gate.py` and expect `VERDICT: PASS`.)

- [ ] **Step 3: Run the Python suite once**

Dispatch the `test-runner` agent (worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v150-reports-research-workspaces`) with `python scripts/dev/testrun.py full`.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). The test database must be reachable (`docker compose --profile test up -d db-test`): with it down the admin tests SKIP, and a skip is not a pass for `tests/admin/test_api_v1_research.py` and `tests/admin/test_api_v1_reports.py`.

- [ ] **Step 4: Run the frontend suite and a production build once**

```bash
cd frontend && npx ng test --watch=false && npm run build
```

Expected: every test file passes; the build succeeds. (If v149's lint has landed, also run `npm run lint` and expect exit 0; a new violation in a v150 file is fixed, never suppressed.)

- [ ] **Step 5: Look at both pages once in the running app**

```bash
make up        # or, where make is unavailable: docker compose up -d --build
```

Open `/app/research` and `/app/reports` in the admin (log in first). Check by eye: the Research ledger lists rows newest first and a row opens the drawer; a verdict chip changes the URL; Reports shows either the two tabs' content or "Not yet run" with the VM command; both pages carry the fixed footer; at phone width the side-by-side panels stack. Report anything that reads wrong; do not restyle here.

- [ ] **Step 6: Fix forward**

If any run is red, fix from the failures it names and rerun only that run. The task is done when the Python suite, the frontend suite and the build are all green.

- [ ] **Step 7: Hand back to the controller**

Report the three verdicts and anything Step 5 found. The controller then:

1. runs `/panel staff-engineer,financial-advisor,quant-researcher` over `main...2026-10-09-v150-reports-research-workspaces`;
2. merges and runs `/close-out` (`Bump: ui minor`: the level is resolved from `VERSION.json` on disk at that moment, and the version history is regenerated in the same commit);
3. leaves running the two reports on the VM to the partner (`docs/deploy/DEPLOY_HETZNER.md`); until then both tabs read "Not yet run" in production, which is the designed state.
