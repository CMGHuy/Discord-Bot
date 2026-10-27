# v195 — Graphite, Part 9: Risk and Dashboard on `sb-page`, the performance strip led by ExpR

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-25:" -A 400 <this file>`.

**Scope of this part (V195-25..V195-26; V195-27 is in Part 9b, `2026-10-25-v195-graphite-frontend-redesign_9b-dashboard-page.md`, split for the 1500-line cap):** spec §5.2 (risk figures carry money and % together; performance strips lead with ExpR, show `N=` with the small-N cue and state their basis), §5.1 (concentration stays on Risk, Dashboard links to it), Phase 4 for Risk and Dashboard, §1.4 for the Dashboard's open positions, and the index's plan decisions 1 and 2. V195-25 moves Risk onto `sb-page`: the killswitch button and the page's stale notice in `[page-actions]`, a four-tile KPI strip (open risk and cap headroom as money · %, top sector, max cluster), Portfolio heat as the primary panel, everything else secondary; `RiskStore` gains the account balance from the existing `GET /dashboard` and a `headroomPct` computed. V195-26 reorders the Trading performance panel so Expectancy leads and Win rate follows, puts `N=` with the thin-sample cue on Expectancy, Win rate and Payoff ratio, and appends the paper / pre-cost / pre-tax caveat to every performance hint, the phone summary following the same order. V195-27 moves the Dashboard onto `sb-page`: a five-tile KPI strip (Expectancy, Win rate, Open risk linking to `/risk`, Realised in period, Open positions), Close all in `[page-actions]` (`danger-quiet`), open positions primary at the 14px order-figure step, then Trading performance, Recent activity and Market movers secondary. V195-25 is the last task of the System + Risk lane; V195-26 → V195-27 open the Dashboard + Watchlist lane (index § Parallelisation). The two lanes share no file.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 8's list binds these tasks (the `sb-page` contract, V195-8's `danger-quiet` call sites, the `primitives.spec.ts` button and form-control gates, the `title` rule: no `title`, `[title]` or `[attr.title]` on a native element in new template text; `sb-confirm-dialog`'s static `title="…"` input is allowed). On top of that:

- `frontend/src/app/ui/page.ts` (V195-21): `Page` (`sb-page`). Markup `header.bar` > `div.heading` (`h1.title`, optional `p.description`) + `div.actions.slot`; `div.scope.slot`; `div.kpis.slot`; `div.primary.slot`; `div.secondary.slot` (a grid: one column, two from 1440px); then the default `<ng-content />` (dialogs, drawers). Heading and description fall back to `RouteTitleService.title()` / `subtitle()`. **Each slot's content is ONE element carrying the slot attribute**, one element per secondary panel; a conditional goes inside that element, never the attribute inside an `@if`. Projected elements are styled by the workspace's own component styles (they carry its encapsulation attribute), so a secondary panel may take `grid-column: 1 / -1` from the workspace's stylesheet.
- `frontend/src/app/ui/format.ts` (V195-7, v194 V194-7): `MINUS = '\u2212'`; `pct`, `money`, `rMultiple` sign a negative with `MINUS` and a positive with `+`; `amount` is unsigned; `num(null)` and `share(null)` are `—` (`ABSENT`); `riskPct(v)` (`"0.00%"`, `"<0.01%"`, else two decimals + `%`). `frontend/src/app/ui/risk-units.ts` (V195-7): `riskUnits(pct, balance, unit)` → `'1,420 € · 1.42%'`, `'— · 1.42%'` without a finite balance, `'—'` without a finite pct, one `MINUS` on each part when `pct < 0`.
- `frontend/src/app/ui/stat-tile.ts` (v194 V194-11, V195-11): `StatTile` inputs `label` (required), `value: string | null` (pre-formatted, required), `sample: number | null`, `tone: 'neutral' | 'pos' | 'neg'`, `hint: string | undefined` (visible `.hint` line), `secondary: string | null` (`.secondary` line), `about: string | undefined` (renders an `sb-hint` glyph button labelled `About <label>`); `.tile.thin` and `N=<n> · thin sample` below `MIN_SAMPLE_N` (or the `minSampleN` preference). `PERFORMANCE_CAVEAT` = `'Paper trades (simulated fills), gross of commissions and slippage, pre-tax.'`. A `sb-stat-strip` outside a panel is its own bordered surface (V195-11).
- `frontend/src/app/ui/button.ts`, `confirm-dialog.ts` (V195-8): `variant="danger"` is the solid fill (killswitch only), `danger-quiet` the bordered look; `ConfirmDialog.dangerVariant`. V195-8 already gave Risk's killswitch dialog `dangerVariant="danger"` and kept its button `[variant]="store.killswitchOn() ? 'secondary' : 'danger'"`; the Dashboard's `data-action="close-all"` button is `variant="danger-quiet"`.
- `frontend/src/app/workspaces/risk/risk.ts` after V195-23: no Scan health or Data source panel, no `Sparkline`, `sourceName` or `fallbackText`; still `sb-section-head` (the `store.error()` message in its `[actions]`), the Killswitch panel with its button and command error, the `sb-confirm-dialog`, the metrics `sb-async` (`Risk metrics`, two `sb-freshness` in the file counting the correlation one), the second `sb-async` around Portfolio heat, Exposure by position, Sector heat and the `.split` of Correlation matrix + Correlated clusters. v194 added `riskPct`/`shareCount` formatting, the sector-concentration banner (`store.unmappedCount()`, V194-9), basis-named Sharpe / Max drawdown tiles with `about` hints and a money drawdown (V194-11); those stay exactly as v194 left them.
- `risk.spec.ts` after V195-23: `describe('Risk keeps only risk (v195 §5.1)')` (no Scan health / Data source heading, no `sb-sparkline`) must stay green; the freshness case is named `dates each metrics panel by its own bar, not one stamp for the page`. `risk.store.spec.ts`: the `RESPONSE` fixture still carries `scan_health` (the payload type requires it) and a case asserts the four scan computeds are absent.
- `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` after V195-7b and v194: imports `MINUS`; `fmtFigure` signs a negative with `MINUS`; v194 V194-4b added `todayError`; v194 converted the `sb-metric-card` `description` from a host `title` to a hint (`MetricCard.description` is still the input every card binds).

v194 and V195-1..V195-24 edited every file below. Each step names its edit by symbol or quoted string, never by line number; re-read each file before editing it. Where a quoted string differs because v194 reworded it, keep v194's wording and make the same structural edit.

---

# Phase 5 — Workspaces: Risk and Dashboard

### Task V195-25: Risk on `sb-page`: killswitch in `[page-actions]`; KPI strip (open risk, cap headroom as money · %, top sector, max cluster); Portfolio heat primary; the rest secondary
**Model:** sonnet — one workspace re-slotted onto an existing template plus one store field and one computed; the care is in every slot being one stable element, the killswitch staying usable and loud, and a failed balance read never inventing money or failing the route.

**Files:**
- Modify: `frontend/src/app/stores/risk.store.ts` (`RiskSlice.balance`, the initial state, `headroomPct`, `finiteOrNull`, `readBalance`, `resolve`, doc comment)
- Modify: `frontend/src/app/stores/risk.store.spec.ts` (one appended `describe`)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (template re-slotted on `sb-page`; `RISK_KPI_ABOUT`, `topSectorOf`, `largestCluster` exported; KPI computeds; `breakdownDisplay`; imports; styles; doc comment)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts` (imports; the metric-tile helpers scoped to `.metrics`; the `renders no in-page heading` case rewritten; four appended `describe` blocks)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21); `riskUnits(pct, balance, unit)` (`ui/risk-units.ts`, V195-7); `StatStrip` (`cols`, `colsMd`), `StatTile` (`label`, `value`, `secondary`, `hint`, `tone`, `about`), `StatTone` (`ui/stat-tile.ts`); `ConfirmDialog.dangerVariant` and `button[sb-button]` `variant="danger"` (V195-8); `ApiClient.dashboard(mode?, window?): Observable<Dashboard>` and `Dashboard.account_balance: number | null` (`api/models.ts`, existing); `ApiClient.risk()`; `routeRequest` (`routing/route-request.ts`); `RiskStore` members `openHeatPct`, `heatCapPct`, `sectorHeat`, `clusters`, `positions`, `empty`, `error`, `killswitchOn`, `toggling`, `commandError`, `dismissCommandError`, `toggleKillswitch`, `unmappedCount` (v194 V194-9); `ConnectionStore.currency()`; `SectorHeat` (`api/models.ts`); `RouteTitleService.set(title, subtitle)`, `installDialogPolyfill` (spec only).
- Produces:
  - `RiskStore` state `balance: number | null` — read from the existing `api.dashboard()` each time `resolve()` is subscribed (so on every route resolve and every `load()`), beside `api.risk()`; the route finishes on the `/risk` read alone; a failed or non-finite balance leaves the previous value (`null` before the first success) and never sets `error`.
  - `RiskStore.headroomPct: Signal<number | null>` — `heat.cap_pct − heat.open_pct`, unclamped (negative over the cap), `null` when either is null.
  - `risk.ts` exports `RISK_KPI_ABOUT` (`openRisk`, `headroom`, `topSector`, `maxCluster` strings), `topSectorOf(rows: readonly SectorHeat[]): SectorHeat | null`, `largestCluster<T extends { tickers: readonly string[] }>(clusters: readonly T[]): T | null`.
  - Markup: `sb-page` > `div.page-actions[page-actions]` (optional `span.stale[role="status"]`, `button[sb-button][data-action="killswitch"]`, optional `p.command-error[role="alert"]`); `sb-stat-strip.kpis[page-kpis]` with four `sb-stat-tile`s labelled `Open risk`, `Cap headroom`, `Top sector`, `Max cluster`; `sb-async.heat-async[page-primary]` around `Portfolio heat`; secondary, in order: `Killswitch` panel, `sb-async.metrics-async` around `Risk metrics`, `Exposure by position`, `Sector heat`, `Correlation matrix`, `Correlated clusters`; the killswitch `sb-confirm-dialog` in the default slot. V195-33's `workspace-consistency` check reads `<sb-page` and the `Page` import here.

**What changes, and what is already there.** Spec Phase 4 and §5.2. Risk today stacks `sb-section-head` (the stale notice), the Killswitch panel with its button, the metrics panel and one `sb-async` around heat, exposure, sectors and the correlation pair. After this task Risk renders `sb-page`: the route title is the page's one `h1`; the header's actions slot carries the killswitch button (the one `variant="danger"` in the app, opening its `dangerVariant="danger"` dialog, both unchanged since V195-8), the stale notice that used to sit in `sb-section-head`, and a failed toggle's error with its Dismiss, so a command that did not happen is reported beside the button that sent it. The Killswitch panel keeps the state (`ENGAGED` / `Clear`), its explanation and its detail line, and becomes the first secondary panel. The KPI strip is new and holds the four figures the partner acts on (§5.2): open risk and cap headroom, each as money and % of account side by side through `riskUnits` (index plan decision 1: the money is `pct / 100 × balance`, the server's own relation, with the balance read from the existing `GET /dashboard`, so no API changes, and a missing balance shows `— · 3.00%`, never an invented figure); the top sector with its risk in both units; the largest correlated cluster with its tickers. Cap headroom is not clamped: over the cap it reads negative with a true minus and a `neg` tone, where the budget panel below keeps its own "remaining shown as 0" rule. Each tile carries an `about` hint (new explanation goes into `sb-hint`, never `title`). Portfolio heat is the primary panel inside its own `sb-async` (it shows the skeleton, the first-load error, the stale marker and the "No open risk" empty state that used to cover the whole set). The four breakdown panels (exposure, sector heat, correlation matrix, clusters) are secondary, each its own slot element; they need an open position to mean anything, so they are hidden with `display: none` (not `@if`, which would break the one-stable-element rule) whenever Portfolio heat's `sb-async` is not showing content. The metrics `sb-async` stays separate and always on (the v85 regression its comment records). Exposure spans both secondary columns, being a table. Nothing on Risk is dropped: every panel keeps its heading, text and v194 hint; only Scan health and Data source left, in V195-23. Concentration stays on Risk only (§5.1); the Dashboard links here (V195-27).

- [ ] **Step 1: Write the failing store tests**

In `$WT/frontend/src/app/stores/risk.store.spec.ts`, after the closing `});` of `describe('RiskStore', ...)`, append:

```ts
/* -- v195 §5.2 -- the account balance, so risk can be shown in money -- */

describe('RiskStore balance and cap headroom (v195 §5.2)', () => {
  let store: InstanceType<typeof RiskStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        RiskStore,
      ],
    });
    store = TestBed.inject(RiskStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const respond = (body: Partial<Risk> = {}) =>
    backend.expectOne('/api/v1/risk').flush({ ...RESPONSE, ...body });
  const unavailable = { status: 503, statusText: 'Service Unavailable' };
  const DOWN = { error: { code: 'unavailable', message: 'down' } };

  it('reads the balance from the existing dashboard endpoint, beside /risk', () => {
    store.load();
    respond();
    backend.expectOne('/api/v1/dashboard').flush({ account_balance: 10000 });

    expect(store.balance()).toBe(10000);
    expect(store.openHeatPct()).toBe(3);
  });

  it('leaves the balance null and the risk loaded when the dashboard read fails', () => {
    store.load();
    respond();
    backend.expectOne('/api/v1/dashboard').flush(DOWN, unavailable);

    expect(store.balance()).toBeNull();
    expect(store.error()).toBeNull();
    expect(store.positions()).toHaveLength(2);
  });

  it('keeps the last balance when a later dashboard read fails', () => {
    store.load();
    respond();
    backend.expectOne('/api/v1/dashboard').flush({ account_balance: 10000 });

    store.load();
    respond();
    backend.expectOne('/api/v1/dashboard').flush(DOWN, unavailable);
    expect(store.balance()).toBe(10000);
  });

  it('never takes a balance that is not a finite number', () => {
    store.load();
    respond();
    backend.expectOne('/api/v1/dashboard').flush({ account_balance: null });
    expect(store.balance()).toBeNull();
  });

  it('finishes the route on the /risk read alone, before the balance answers', () => {
    let finished = 0;
    store.resolve().subscribe({ complete: () => { finished += 1; } });
    respond();

    expect(finished).toBe(1);
    // Still in flight, and that holds nothing up.
    expect(backend.match('/api/v1/dashboard')).toHaveLength(1);
  });

  it('reads nothing until the resolver is subscribed', () => {
    store.resolve();
    backend.expectNone('/api/v1/risk');
    backend.expectNone('/api/v1/dashboard');
  });

  it('measures cap headroom as the cap less the open heat, unclamped', () => {
    store.load();
    respond({ heat: { open_pct: 3, cap_pct: 6, utilisation_pct: 50 } });
    expect(store.headroomPct()).toBe(3);

    store.load();
    respond({ heat: { open_pct: 7.5, cap_pct: 6, utilisation_pct: 125 } });
    expect(store.headroomPct()).toBe(-1.5);
  });

  it('has no headroom when either side is unknown, and before the first answer', () => {
    expect(store.headroomPct()).toBeNull();
    store.load();
    respond({ heat: { open_pct: null, cap_pct: 6, utilisation_pct: null } });
    expect(store.headroomPct()).toBeNull();
    store.load();
    respond({ heat: { open_pct: 3, cap_pct: null, utilisation_pct: null } });
    expect(store.headroomPct()).toBeNull();
  });
});
```

(`FakeEventStream`, `RESPONSE`, `EventStream`, `beforeEach` and the interceptors are already declared or imported at the top of this file.)

- [ ] **Step 2: Write the failing component tests**

In `$WT/frontend/src/app/workspaces/risk/risk.spec.ts`:

1. Change `import { describe, expect, it } from 'vitest';` to `import { beforeAll, describe, expect, it } from 'vitest';`, change `import { Risk } from './risk';` to `import { RISK_KPI_ABOUT, Risk, largestCluster, topSectorOf } from './risk';`, and add below the existing imports:

```ts
import { By } from '@angular/platform-browser';

import { RouteTitleService } from '../../routing/route-title.service';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { StatTile } from '../../ui/stat-tile';
```

2. The metric-tile helpers now scope to the metrics panel, because the page also carries KPI tiles. In `function tileHost(...)` change `querySelectorAll('sb-stat-tile')` to `querySelectorAll('.metrics sb-stat-tile')`; in `function tileLabels(...)` change `querySelectorAll('sb-stat-tile .label')` to `querySelectorAll('.metrics sb-stat-tile .label')`. In `it('rules the six tiles with one stat strip, auto-fit at 140px', ...)` change `expect(el.querySelectorAll('sb-stat-tile')).toHaveLength(6);` to `expect(el.querySelectorAll('.metrics sb-stat-tile')).toHaveLength(6);`.

3. Replace the case `it('renders no in-page heading', ...)` (in `describe('Risk freshness and chrome', ...)`) with:

```ts
  it('renders the route title as the one h1, from sb-page, and no section head', async () => {
    const fixture = await render();
    TestBed.inject(RouteTitleService).set('Risk', 'Exposure, heat and the killswitch');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Risk');
    expect(el.querySelector('sb-section-head')).toBeNull();
  });
```

4. Append at the end of the file:

```ts
/* -- v195 Phase 4 and §5.2 -- Risk on sb-page ---------------------------- */

const OPEN_POSITION = {
  trade_id: 't1', ticker: 'AAPL', strategy: 'VWAP',
  shares: 10, entry: 100, stop_loss: 95, risk_pct: 3,
};
const DOWN = { error: { code: 'unavailable', message: 'down' } };
const UNAVAILABLE = { status: 503, statusText: 'Service Unavailable' };

/** Flushes /risk and then the balance read the store makes beside it.
 *  `balance: 'fail'` answers the dashboard read with a 503. */
async function renderPage(
  overrides: Partial<RiskData> = {},
  balance: number | null | 'fail' = 10000,
): Promise<ComponentFixture<Risk>> {
  const { fixture, backend } = seed();
  TestBed.inject(RouteTitleService).set('Risk', 'Exposure, heat and the killswitch');
  fixture.detectChanges();
  backend.expectOne('/api/v1/risk').flush(payload({
    heat: { open_pct: 3, cap_pct: 20, utilisation_pct: 15 },
    positions: [OPEN_POSITION],
    ...overrides,
  }));
  const read = backend.expectOne('/api/v1/dashboard');
  if (balance === 'fail') read.flush(DOWN, UNAVAILABLE);
  else read.flush({ account_balance: balance });
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

/** The KPI tiles' own inputs, read from the components: the rendered value
 *  counts up, the input is the figure. */
function kpis(fixture: ComponentFixture<Risk>): Map<string, StatTile> {
  return new Map(fixture.debugElement.queryAll(By.css('[page-kpis] sb-stat-tile'))
    .map((d) => d.componentInstance as StatTile)
    .map((tile) => [tile.label(), tile] as const));
}

const headerActions = (el: HTMLElement) => el.querySelector('sb-page header.bar .actions')!;
const killButton = (el: HTMLElement) =>
  headerActions(el).querySelector<HTMLButtonElement>('button[data-action="killswitch"]')!;
const panelHeadings = (scope: Element | null) =>
  [...(scope?.querySelectorAll('sb-panel') ?? [])].map((p) => p.getAttribute('heading'));
const BREAKDOWN = ['Exposure by position', 'Sector heat', 'Correlation matrix', 'Correlated clusters'];

describe('Risk on sb-page (v195 Phase 4)', () => {
  beforeAll(() => installDialogPolyfill());

  it('puts Portfolio heat in the primary slot and the rest in the secondary grid, in order', async () => {
    const el = (await renderPage()).nativeElement as HTMLElement;
    expect(panelHeadings(el.querySelector('sb-page div.primary.slot'))).toEqual(['Portfolio heat']);
    expect(panelHeadings(el.querySelector('sb-page div.secondary.slot'))).toEqual(
      ['Killswitch', 'Risk metrics', ...BREAKDOWN]);
  });

  it('puts the killswitch button in the header actions, solid danger while clear', async () => {
    const el = (await renderPage()).nativeElement as HTMLElement;
    const button = killButton(el);
    expect(button.textContent!.trim()).toBe('Engage killswitch');
    expect(button.classList).toContain('danger');
    // The Killswitch panel keeps the state and its explanation, not the control.
    const panel = el.querySelector('sb-panel[heading="Killswitch"]')!;
    expect(panel.textContent).toContain('Clear');
    expect([...panel.querySelectorAll('button')].some((b) => /killswitch/i.test(b.textContent ?? ''))).toBe(false);
  });

  it('offers Release, not danger, once the killswitch is engaged', async () => {
    const el = (await renderPage({ killswitch: { on: true, reason: 'drawdown', at: null } }))
      .nativeElement as HTMLElement;
    expect(killButton(el).textContent!.trim()).toBe('Release killswitch');
    expect(killButton(el).classList).not.toContain('danger');
    expect(el.querySelector('sb-panel[heading="Killswitch"]')!.textContent).toContain('ENGAGED');
  });

  it('asks through the solid danger dialog before anything is sent', async () => {
    const fixture = await renderPage();
    const el = fixture.nativeElement as HTMLElement;
    killButton(el).click();
    fixture.detectChanges();

    expect(el.querySelector<HTMLDialogElement>('sb-confirm-dialog dialog')!.open).toBe(true);
    const dialog = fixture.debugElement.query(By.directive(ConfirmDialog)).componentInstance as ConfirmDialog;
    expect(dialog.dangerVariant()).toBe('danger');
    TestBed.inject(HttpTestingController).expectNone('/api/v1/risk/killswitch');
  });

  it('reports a failed toggle beside the button that sent it', async () => {
    const fixture = await renderPage();
    const el = fixture.nativeElement as HTMLElement;
    const backend = TestBed.inject(HttpTestingController);
    killButton(el).click();
    fixture.detectChanges();
    [...el.querySelectorAll<HTMLButtonElement>('sb-confirm-dialog button')].at(-1)!.click();
    backend.expectOne('/api/v1/risk/killswitch').error(new ProgressEvent('error'), { status: 0 });
    fixture.detectChanges();

    expect(headerActions(el).querySelector('[role="alert"]')!.textContent).toContain('NOT engaged');
  });

  it('keeps the stale notice in the header when a refetch fails', async () => {
    const fixture = await renderPage();
    const backend = TestBed.inject(HttpTestingController);
    TestBed.inject(RiskStore).load();
    backend.expectOne('/api/v1/risk').flush(DOWN, UNAVAILABLE);
    fixture.detectChanges();
    expect(headerActions(fixture.nativeElement).querySelector('.stale[role="status"]')!.textContent)
      .toContain('may be stale');
  });

  it('hides the four breakdown panels at zero open risk, keeping the killswitch and the metrics', async () => {
    const el = (await renderPage({ positions: [] })).nativeElement as HTMLElement;
    const display = (heading: string) =>
      el.querySelector<HTMLElement>(`sb-panel[heading="${heading}"]`)!.style.display;
    for (const heading of BREAKDOWN) expect(display(heading)).toBe('none');
    expect(display('Killswitch')).toBe('');
    expect(el.querySelector('.metrics')).not.toBeNull();
    expect(el.textContent).toContain('No open risk');
  });

  it('shows the breakdown panels once a position is open', async () => {
    const el = (await renderPage()).nativeElement as HTMLElement;
    for (const heading of BREAKDOWN) {
      expect(el.querySelector<HTMLElement>(`sb-panel[heading="${heading}"]`)!.style.display).toBe('');
    }
  });
});

describe('Risk KPI strip (v195 §5.2)', () => {
  it('holds open risk, cap headroom, top sector and max cluster, in that order', async () => {
    expect([...kpis(await renderPage()).keys()])
      .toEqual(['Open risk', 'Cap headroom', 'Top sector', 'Max cluster']);
  });

  it('shows open risk and cap headroom as money and % of account side by side', async () => {
    const tiles = kpis(await renderPage());
    expect(tiles.get('Open risk')!.value()).toBe('300 € · 3.00%');
    expect(tiles.get('Open risk')!.secondary()).toBe('cap 2,000 € · 20.00%');
    expect(tiles.get('Cap headroom')!.value()).toBe('1,700 € · 17.00%');
    expect(tiles.get('Cap headroom')!.tone()).toBe('neutral');
  });

  it('reads headroom over the cap as negative, with a true minus, never clamped', async () => {
    const tiles = kpis(await renderPage({ heat: { open_pct: 7.5, cap_pct: 6, utilisation_pct: 125 } }));
    expect(tiles.get('Cap headroom')!.value()).toBe('−150 € · −1.50%');
    expect(tiles.get('Cap headroom')!.tone()).toBe('neg');
  });

  it('never invents money when the balance read fails', async () => {
    const tiles = kpis(await renderPage({}, 'fail'));
    expect(tiles.get('Open risk')!.value()).toBe('— · 3.00%');
    expect(tiles.get('Cap headroom')!.value()).toBe('— · 17.00%');
  });

  it('names the top sector with its risk in both units, and the largest cluster with its tickers', async () => {
    const tiles = kpis(await renderPage({
      sector_heat: [{ sector: 'Energy', heat_pct: 1 }, { sector: 'Technology', heat_pct: 2 }],
      clusters: [['XOM', 'CVX'], ['AAPL', 'MSFT', 'NVDA']],
    }));
    expect(tiles.get('Top sector')!.value()).toBe('Technology');
    expect(tiles.get('Top sector')!.secondary()).toBe('200 € · 2.00%');
    expect(tiles.get('Max cluster')!.value()).toBe('3 positions');
    expect(tiles.get('Max cluster')!.secondary()).toBe('AAPL · MSFT · NVDA');
  });

  it('says None for no cluster and leaves the sector absent when nothing is mapped', async () => {
    const tiles = kpis(await renderPage({ sector_heat: [], clusters: [] }));
    expect(tiles.get('Max cluster')!.value()).toBe('None');
    expect(tiles.get('Top sector')!.value()).toBeNull();
    expect(tiles.get('Top sector')!.secondary()).toBeNull();
  });

  it('explains every KPI in an About hint', async () => {
    const tiles = kpis(await renderPage());
    expect(tiles.get('Open risk')!.about()).toBe(RISK_KPI_ABOUT.openRisk);
    expect(tiles.get('Cap headroom')!.about()).toBe(RISK_KPI_ABOUT.headroom);
    expect(tiles.get('Top sector')!.about()).toBe(RISK_KPI_ABOUT.topSector);
    expect(tiles.get('Max cluster')!.about()).toBe(RISK_KPI_ABOUT.maxCluster);
  });
});

describe('Risk KPI helpers (v195 §5.2)', () => {
  it('picks the sector with the most heat, skipping unknown heat, first on a tie', () => {
    expect(topSectorOf([
      { sector: 'Energy', heat_pct: 1 }, { sector: 'Unknown', heat_pct: null },
      { sector: 'Technology', heat_pct: 2.5 }, { sector: 'Health', heat_pct: 2.5 },
    ])).toEqual({ sector: 'Technology', heat_pct: 2.5 });
    expect(topSectorOf([])).toBeNull();
    expect(topSectorOf([{ sector: 'Unknown', heat_pct: null }])).toBeNull();
  });

  it('picks the largest cluster, the first one on a tie', () => {
    const a = { index: 1, tickers: ['A', 'B'] };
    const b = { index: 2, tickers: ['C', 'D', 'E'] };
    const c = { index: 3, tickers: ['F', 'G', 'H'] };
    expect(largestCluster([a, b, c])).toBe(b);
    expect(largestCluster([])).toBeNull();
  });
});

describe('Risk on sb-page, source (v195 Phase 4)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/risk/risk.ts'), 'utf8');

  it('renders sb-page with the killswitch confirm on solid danger, and no section head', () => {
    expect(src).toContain('<sb-page>');
    expect(src).toContain('dangerVariant="danger"');
    expect(src).not.toContain('<sb-section-head');
    expect(src).not.toMatch(/import \{ SectionHead \}/);
  });

  it('never puts a slot attribute on an element inside a conditional', () => {
    // Each slot is one stable element; a conditional sits inside it.
    expect(src).not.toMatch(/@if \([^)]*\) \{\s*<[^>]*\bpage-(actions|scope|kpis|primary|secondary)\b/);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/stores/risk.store.spec.ts --include src/app/workspaces/risk/risk.spec.ts
```

Expected: FAIL. The store cases find no `/api/v1/dashboard` request and `store.balance` / `store.headroomPct` are not functions; `risk.spec.ts` does not compile until `RISK_KPI_ABOUT`, `topSectorOf` and `largestCluster` exist (TS2305 "has no exported member"). The rescoped metric-tile cases would pass on their own.

- [ ] **Step 4: Give `RiskStore` the balance and the headroom**

In `$WT/frontend/src/app/stores/risk.store.ts`:

1. Change `import { Observable } from 'rxjs';` to `import { Observable, defer } from 'rxjs';`.

2. In `interface RiskSlice`, after `commandError: string | null;` add:

```ts

  /** v195 §5.2: the account balance, read from the existing `GET /dashboard`
   *  beside `GET /risk`, so risk can be shown in money as well as % of
   *  account (`pct / 100 × balance`, the server's own relation in
   *  `trade_risk_pct`). Null until a read lands; a failed read leaves the
   *  last value, never a guess. */
  balance: number | null;
```

3. In `withState<RiskSlice>({ ... })`, after `commandError: null,` add `balance: null,`.

4. Directly above `/** A cluster is a list of correlated tickers.`, add:

```ts
/** A balance is money only when it is a finite number; anything else from
 *  the wire (null, a string, NaN) leaves the money figures blank. */
function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

```

5. In `withComputed`, after `heatCapPct: computed(() => data()?.heat?.cap_pct ?? null),` add:

```ts

    /** v195 §5.2: room left under the cap, in % of account. **Not
     *  clamped**: over the cap it is negative, which is the state the KPI
     *  must show. The budget panel keeps its own floor-at-zero rule. */
    headroomPct: computed(() => {
      const cap = data()?.heat?.cap_pct;
      const open = data()?.heat?.open_pct;
      if (cap === null || cap === undefined || open === null || open === undefined) return null;
      return cap - open;
    }),
```

6. In `withMethods`, replace the whole `const resolve = (): Observable<void> => routeRequest(api.risk(), { … });` statement with:

```ts
    /** Fire and forget: the route never waits for it, and a failure keeps the
     *  last balance (null before the first), so the KPIs fall back to
     *  "— · 3.00%" instead of failing the page. */
    const readBalance = (): void => {
      api.dashboard().subscribe({
        next: (dashboard) => {
          const balance = finiteOrNull(dashboard.account_balance);
          if (balance !== null || store.balance() === null) patchState(store, { balance });
        },
        error: () => undefined,
      });
    };
    /** `defer`: both reads start when the resolver is subscribed, not when it
     *  is built, so a resolver that is never subscribed reads nothing. */
    const resolve = (): Observable<void> => defer(() => {
      readBalance();
      return routeRequest(api.risk(), {
        start: () => patchState(store, { loading: true }),
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error) => patchState(store, {
          loading: false,
          error: error.code === 'unavailable' ? 'The admin is not responding — these figures may be stale.' : error.message,
        }),
      });
    });
```

   (The `start`/`next`/`error` bodies are today's, unchanged; if v194 reworded the error text, keep v194's.)

7. In the store's doc comment, after the paragraph that starts `Everything the Jinja Risk page renders is projected by`, add a paragraph:

```ts
 *
 * **One read beside it (v195 §5.2).** `GET /risk` carries risk as % of
 * account only, and the KPI strip shows money and % together. The balance
 * comes from the existing `GET /dashboard` (`account_balance`), read each
 * time the resolver runs and never waited on: a slow or failed read leaves
 * the money half of each figure blank, it does not hold or fail the route.
```

- [ ] **Step 5: Move Risk onto `sb-page`**

In `$WT/frontend/src/app/workspaces/risk/risk.ts`:

1. Imports. Delete `import { SectionHead } from '../../ui/section-head';`. Change `import { RiskPosition } from '../../api/models';` to `import { RiskPosition, SectorHeat } from '../../api/models';`. In the `'../../ui/stat-tile'` import add `StatTone` beside what is there (v194 made it `import { PERFORMANCE_CAVEAT, StatTile } from '../../ui/stat-tile';`; it becomes `import { PERFORMANCE_CAVEAT, StatTile, StatTone } from '../../ui/stat-tile';`). Add:

```ts
import { Page } from '../../ui/page';
import { riskUnits } from '../../ui/risk-units';
```

   In the component's `imports: [...]` array remove `SectionHead` and add `Page`.

2. Directly above the class doc comment (the `/**` that opens `* Risk — exposure, heat against`), add:

```ts
/** v195 §5.2: the About hints of the four KPI tiles. New explanation lives in
 *  a hint, never a `title`. */
export const RISK_KPI_ABOUT = {
  openRisk:
    'What the open positions lose together if every stop fills, in money and as a share of the '
    + 'account. The cap beneath is the most open risk the bot allows before it blocks new entries.',
  headroom:
    'How much more risk the bot may take on before new entries are blocked: the cap less the open '
    + 'risk, in money and as a share of the account. Below zero, the book is over the cap.',
  topSector:
    'The sector carrying the most open risk, with that risk in money and as a share of the account. '
    + 'Sector heat below lists every sector.',
  maxCluster:
    'The largest group of open positions whose daily returns move together. They tend to lose '
    + 'together, so their risk adds up. Correlated clusters below lists every group.',
} as const;

/** The sector with the most heat; unknown heat never wins. First on a tie,
 *  which is the server's order. */
export function topSectorOf(rows: readonly SectorHeat[]): SectorHeat | null {
  let top: SectorHeat | null = null;
  for (const row of rows) {
    if (row.heat_pct === null) continue;
    if (top === null || row.heat_pct > (top.heat_pct as number)) top = row;
  }
  return top;
}

/** The cluster with the most tickers; first on a tie. */
export function largestCluster<T extends { tickers: readonly string[] }>(clusters: readonly T[]): T | null {
  let best: T | null = null;
  for (const cluster of clusters) {
    if (best === null || cluster.tickers.length > best.tickers.length) best = cluster;
  }
  return best;
}

```

3. The class doc comment: after its paragraph about the engaged state also being rendered by the shell, add:

```ts
 *
 * **On `sb-page` (v195 Phase 4, §5.2).** The route title is the page's one
 * `h1`. The killswitch button is the header's action, the only solid
 * `danger` control in the app; the stale notice and a failed toggle's error
 * sit beside it. The KPI strip holds the four figures acted on (open risk
 * and cap headroom in money and % of account, top sector, max cluster),
 * Portfolio heat is the primary panel, and everything else is secondary,
 * each panel its own slot element.
```

4. The template. Apply these edits in order. Every element named "move" keeps its markup, bindings, comments and v194 hints exactly as they are; only its position and the attributes named here change.

   a. Delete the whole `<sb-section-head> … </sb-section-head>` element (its message and comment are re-created in the actions element below).

   b. At the top of the template insert:

```html
    <sb-page>
      <div page-actions class="page-actions">
        @if (store.error(); as message) {
          <!-- The killswitch panel stays outside every sb-async and has no
               error surface of its own: this is the only place its staleness
               shows. It duplicates Portfolio heat's own stale display on a
               first-load failure, an acceptable trade for not losing the
               killswitch's. -->
          <span class="stale" role="status">{{ message }}</span>
        }
        <!-- Both directions go through the dialog. Releasing is as
             consequential as engaging -- it puts money back at risk -- and a
             one-click release beside a guarded engage is an invitation to
             undo a deliberate stop by accident. -->
        <button
          sb-button
          data-action="killswitch"
          [variant]="store.killswitchOn() ? 'secondary' : 'danger'"
          type="button"
          [loading]="store.toggling()"
          [disabled]="store.empty()"
          (click)="ask()"
        >
          {{ store.killswitchOn() ? 'Release killswitch' : 'Engage killswitch' }}
        </button>
        @if (store.commandError(); as message) {
          <!-- Held until the next attempt rather than auto-dismissed: the user
               asked for a state change that did not happen, and it is
               reported beside the button that asked. -->
          <p class="command-error" role="alert">
            {{ message }}
            <button sb-button variant="ghost" type="button" (click)="store.dismissCommandError()">
              Dismiss
            </button>
          </p>
        }
      </div>

      <!-- v195 §5.2: the four figures acted on. Risk carries money and % of
           account together (riskUnits); the money half is blank, never
           guessed, until the balance read lands. -->
      <sb-stat-strip page-kpis class="kpis" [cols]="4" [colsMd]="2">
        <sb-stat-tile label="Open risk" [value]="openRiskText()" [secondary]="capText()"
                      [about]="kpiAbout.openRisk" />
        <sb-stat-tile label="Cap headroom" [value]="headroomText()" [tone]="headroomTone()"
                      [about]="kpiAbout.headroom" />
        <sb-stat-tile label="Top sector" [value]="topSector()?.sector ?? null" [secondary]="topSectorText()"
                      [hint]="unmappedHint()" [about]="kpiAbout.topSector" />
        <sb-stat-tile label="Max cluster" [value]="maxClusterText()" [secondary]="maxClusterTickers()"
                      [about]="kpiAbout.maxCluster" />
      </sb-stat-strip>
```

   c. In `<sb-panel heading="Killswitch">`: change the opening tag to `<sb-panel page-secondary heading="Killswitch">`; delete the killswitch `<button sb-button [variant]="store.killswitchOn() ? 'secondary' : 'danger'" …> … </button>` element and the `<!-- Both directions go through the dialog. … -->` comment above it; delete the `@if (store.commandError(); as message) { … }` block and its comment (both re-created in `page-actions`). Inside `.kill-state`, directly after the `@if (killswitchDetail(); as detail) { … }` block, add `<p class="kill-where">The control is at the top of this page.</p>`.

   d. The second `sb-async` (the one with `[empty]="async().empty"` and `[announce]="announce()"`): add `page-primary class="heat-async"` to its opening tag, and close it (`</sb-async>`) directly after `<sb-panel heading="Portfolio heat"> … </sb-panel>`, so it wraps that panel only. Replace its comment `<!-- heat, exposure, sector/cluster breakdown … -->` with:

```html
    <!-- Portfolio heat, the primary panel. Its sb-async owns the first-load
         skeleton, the error, the stale marker and the "No open risk" empty
         state for the four breakdown panels below too: they are hidden
         (breakdownDisplay) whenever this one is not showing content. The
         killswitch panel stays outside it deliberately: it is an operational
         control that must stay usable at zero open risk (an operator may want
         to engage it exactly when flat, to stop the bot opening anything
         new). It already degrades gracefully via the store's own null-safe
         defaults while the first fetch is in flight. -->
```

   e. Move the edited `<sb-panel page-secondary heading="Killswitch"> … </sb-panel>` to directly after the `heat-async` element's `</sb-async>`.

   f. Move the metrics `sb-async` (`[empty]="false"`, around `<sb-panel heading="Risk metrics">`) with its comment to directly after the Killswitch panel, and add `page-secondary class="metrics-async"` to its opening tag.

   g. After the metrics `</sb-async>`, place the four breakdown panels, each gaining `page-secondary` and `[style.display]="breakdownDisplay()"` on its opening tag: `Exposure by position` (also `class="exposure"`, keeping `[flush]="true"`), `Sector heat`, `Correlation matrix`, `Correlated clusters`, in that order. Delete the `<div class="split">` wrapper and its closing `</div>`, keeping the `<!-- correlation (v85 D38) … -->` comment above `Correlation matrix`. Delete the old closing `</sb-async>` that followed `Correlated clusters`.

   h. Move the killswitch `<sb-confirm-dialog [open]="asking()" … />` (unchanged, `dangerVariant="danger"` included) to directly after `Correlated clusters`, then close the page with `</sb-page>`, before the `<!-- cells --- -->` comment. The `#tickerCell` and `#riskCell` templates stay outside `sb-page`, unchanged.

   After the edit, `git -C "$WT" grep -n -E "page-(actions|kpis|primary|secondary)" -- frontend/src/app/workspaces/risk/risk.ts` prints exactly nine template lines: one `page-actions`, one `page-kpis`, one `page-primary`, six `page-secondary`.

5. The class. After `protected readonly asking = signal(false);` add:

```ts

  /* -- v195 §5.2: the KPI strip ----------------------------------------- */

  protected readonly kpiAbout = RISK_KPI_ABOUT;

  /** One place that turns a % of account into "money · %". */
  private units(pct: number | null): string {
    return riskUnits(pct, this.store.balance(), this.connection.currency());
  }

  protected readonly openRiskText = computed(() => this.units(this.store.openHeatPct()));
  /** The cap, in the same two units: the dollar-risk cap is the reference. */
  protected readonly capText = computed(() => {
    const cap = this.store.heatCapPct();
    return cap === null ? null : `cap ${this.units(cap)}`;
  });
  protected readonly headroomText = computed(() => this.units(this.store.headroomPct()));
  /** Over the cap is a loss of room, so the one tile that can go negative
   *  reads neg there; at or under the cap it is a plain figure. */
  protected readonly headroomTone = computed<StatTone>(() =>
    ((this.store.headroomPct() ?? 0) < 0 ? 'neg' : 'neutral'));

  protected readonly topSector = computed(() => topSectorOf(this.store.sectorHeat()));
  protected readonly topSectorText = computed(() => {
    const top = this.topSector();
    return top === null ? null : this.units(top.heat_pct);
  });
  /** v194 B6: positions the sector map does not know make "top sector" a
   *  partial answer, so the tile says how many it could not count. */
  protected readonly unmappedHint = computed(() => {
    const n = this.store.unmappedCount();
    return n > 0 ? `${n} position${n === 1 ? '' : 's'} without a sector` : undefined;
  });

  protected readonly maxCluster = computed(() => largestCluster(this.store.clusters()));
  /** "None" once the read has landed and found no cluster; no value before. */
  protected readonly maxClusterText = computed(() => {
    if (this.store.empty()) return null;
    const cluster = this.maxCluster();
    return cluster === null ? 'None' : `${cluster.tickers.length} positions`;
  });
  protected readonly maxClusterTickers = computed(() => this.maxCluster()?.tickers.join(' · ') ?? null);

  /** The four breakdown panels need an open position to mean anything. They
   *  are hidden exactly when Portfolio heat's sb-async shows no content
   *  (before the first answer, a first-load failure, nothing open), and that
   *  sb-async says why. `display`, not `@if`: each panel stays one stable
   *  slot element (the sb-page contract). */
  protected readonly breakdownDisplay = computed(() =>
    (this.store.empty() || this.store.positions().length === 0 ? 'none' : null));
```

6. Styles. Replace the rule `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }` and the two comments above it (from `/* minmax(0, 1fr), not the implicit auto track.` through `opting this workspace into the instrument register. */`) with:

```css
    /* v195 Phase 4: sb-page lays out the header, the KPI strip, the primary
       panel and the secondary grid, and owns their gaps; the host is only a
       block. No backticks in here: these styles live in a TS template
       literal. */
    :host { display: block; }

    /* The header's actions: the stale notice, the killswitch, and a failed
       toggle's error on its own line beneath them. */
    .page-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
      gap: var(--space-8);
    }
    .page-actions .command-error { flex-basis: 100%; justify-content: flex-end; margin: 0; }

    /* A table: it takes both secondary columns from 1440px. */
    .exposure { grid-column: 1 / -1; }

    .kill-where { margin-top: var(--space-6); color: var(--text-secondary); font-size: var(--text-table); }
```

   Delete the `/* -- the two side-by-side panels -- */` block: its comment and the whole `.split { … }` rule (the secondary grid pairs the two correlation panels now). Leave every other rule as it is.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/stores/risk.store.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`, including V195-23's `Risk keeps only risk (v195 §5.1)` and the renamed freshness case (two `sb-freshness` remain: the metrics panel's and the correlation matrix's). If the h1 case finds two headings, `sb-section-head` is still in the template. If a `Risk metric tiles` case sees ten tiles, a helper still reads `sb-stat-tile` without the `.metrics` scope. If the secondary-order case lists `Portfolio heat` in the secondary grid, the heat panel is still inside the metrics `sb-async`. If the stale-notice case finds no `.stale`, the error interceptor retried the 503: drain the retry with `backend.match('/api/v1/risk').forEach((r) => r.flush(DOWN, UNAVAILABLE))`. `title-usage.spec.ts` stays green: no `title` attribute was added. `primitives.spec.ts` stays green: both buttons are `button[sb-button]`.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. Lint flags a leftover `SectionHead` import or an unused member.

- [ ] **Step 7: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click through the rail to Risk. At 1440, 768 and 390: one `h1` reading `Risk`; `Engage killswitch` (or `Release killswitch`) at the header's right, solid red only while engaging, wrapping under the title at 390 with nothing clipped, at least 44px tall at 768 and 390; open its dialog and **cancel** (never confirm against the live killswitch); the KPI strip shows four tiles, open risk and headroom each as `<money> <unit> · <pct>%` (4 across at 1440, 2 at 768 and 390); Portfolio heat directly under the strip; then Killswitch, Risk metrics, Exposure (full width), Sector heat, Correlation matrix, Correlated clusters, two per row at 1440 and one per row below. No horizontal page scroll at any width (`document.documentElement.scrollWidth <= innerWidth`). Save the PNGs under the session scratchpad.

- [ ] **Step 8: Close**

Close: standard (test: `frontend/src/app/workspaces/risk/risk.spec.ts`), plus `frontend/src/app/stores/risk.store.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/stores/risk.store.ts frontend/src/app/stores/risk.store.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts
git -C "$WT" commit -m "feat(v195): Risk on sb-page, risk KPIs in money and % of account (V195-25)" -m "Spec Phase 4 and §5.2: Risk renders sb-page. The killswitch button (the one solid danger control, its dialog unchanged), the stale notice and a failed toggle's error sit in the header's actions. A KPI strip shows open risk and cap headroom as money and % of account side by side, the top sector and the largest correlated cluster. Portfolio heat is primary; the Killswitch state, Risk metrics, Exposure, Sector heat and the correlation pair are secondary. RiskStore reads the balance from the existing GET /dashboard beside GET /risk (never waited on; a failure leaves the money half blank) and gains an unclamped headroomPct." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-26: Trading performance: Expectancy first, Win rate after, `N=` with the thin-sample cue on every rate KPI, the paper / pre-cost / pre-tax basis in every performance hint; the phone summary in the same order
**Model:** sonnet — one panel's card order, sub-lines and hint texts, with its spec; the care is in the payoff N coming from the right sample, the caveat never doubling where v194 already added it, and the phone summary staying findable by its labels.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (`PERF_BASIS`, `withBasis`, `performanceSample`, `joinSub` exported; the strip's card order; `sample`, `payoffSub`; `about`; the `.mobile-summary` rows; styles; doc comment)
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts` (imports; the loading-ring and tooltip cases updated; two appended `describe` blocks)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (the panel-tooltip case expects the panel hint with its basis)

**Interfaces:**
- Consumes: `MetricCard` (`sb-metric-card`: `label`, `value`, `sub`, `description`, `loading`, `tint`; `sub` renders in `.sub`) (`ui/metric-card.ts`); `MIN_SAMPLE_N` (30) and `PERFORMANCE_CAVEAT` (`ui/stat-tile.ts`, v194 V194-11); `KPI_HELP`, `PANEL_HELP` (`panels/panel-help.ts`); `TradingPerformance` inputs `expectancyR`, `expectancyN`, `winRate`, `winRateN`, `payoffRatio`, `loading`, `selection` (unchanged); `fmtFigure` (V195-7b).
- Produces (this file only; V195-27 binds the same inputs it binds today and reads none of these):
  - `export function withBasis(text: string): string` — `text` plus `' ' + PERFORMANCE_CAVEAT`, unless `text` already contains it.
  - `export function performanceSample(n: number | null, minimum = MIN_SAMPLE_N): string | null` — `null` for `null`; `'N=<n>'` from `minimum` up; `'N=<n> · thin sample'` below it (the stat tile's own words).
  - `export function joinSub(...parts: (string | null)[]): string | null` — the non-null parts joined by `' · '`, `null` when none.
  - `export const PERF_BASIS` — the card hints with the basis: `openPnl`, `expectancy`, `winRate`, `payoffRatio`, `realizedToday`, `realized` (each `withBasis(KPI_HELP.<key>)`).
  - Strip order: Expectancy, Win rate, Payoff ratio, Open P&L, Realised today, (Realised in period), Open trades, Avg confidence. Phone summary order: Portfolio, Today, Open, Expectancy, Win rate, Payoff, Realised today, (Realised in period), with `small.n` (`N=…`) inside the Expectancy, Win rate and Payoff figures.

**What changes, and what is already there.** Spec §5.2 and correction 2 (financial-advisor BLOCKING 2): a performance strip leads with expectancy, never with win rate; every performance KPI shows its sample size with the existing small-N cue and states its basis. Today the strip reads Open P&L, Win rate, Expectancy, Payoff ratio, …; Win rate and Expectancy carry `N=<n>` with no cue; Payoff ratio carries no N; the hints say nothing about paper fills, costs or tax. After this task the strip opens Expectancy, Win rate, Payoff ratio (the triple the class comment says decomposes expectancy, now in its causal order), then the money and count cards as before. Win rate shows `N=` from `win_rate_n`; Expectancy and Payoff ratio show it from `expectancy_n`, because the server computes both from the same scoped R list (`payoff_ratio_from_rs(scoped_rs)` and `expectancy_n = len(scoped_rs)`, `swingbot/admin/api_v1/dashboard.py`). Below `MIN_SAMPLE_N` the line reads `N=12 · thin sample`, the stat tile's own cue in its own words; the payoff card keeps its no-close hint after the N. The figures themselves (value, tint, rings) are untouched. Every performance card (Open P&L, Expectancy, Win rate, Payoff ratio, Realised today, Realised in period) and the panel hint gain v194's one caveat sentence (`PERFORMANCE_CAVEAT`); `withBasis` adds it once, so a hint v194's content audit already extended is left as it is. Open trades and Avg confidence are counts, not performance, and keep their hints. The phone summary follows: Expectancy before Win rate, each rate figure carrying its `N=` beneath it. The thin cue reads the `MIN_SAMPLE_N` constant: this panel is rendered without `PreferencesStore` in its specs, and a `minSampleN` preference only moves the cue's threshold.

- [ ] **Step 1: Write the failing tests**

In `$WT/frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`:

1. Change `import { TradingPerformance, presetLabel } from './trading-performance';` to

```ts
import {
  PERF_BASIS, TradingPerformance, joinSub, performanceSample, presetLabel, withBasis,
} from './trading-performance';
import { MetricCard } from '../../../ui/metric-card';
import { MIN_SAMPLE_N, PERFORMANCE_CAVEAT } from '../../../ui/stat-tile';
```

2. In `describe('loading rings', ...)`:
   - in `it('ring the five window-scoped cards while a refetch is in flight, …')` change the expected list to `['Expectancy', 'Win rate', 'Payoff ratio', 'Realised today', 'Avg confidence']`;
   - in `it('also ring the phone summary rows, …')` change `expect(busyRows).toEqual(['Win rate', 'Expectancy', 'Payoff', 'Realised today']);` to `expect(busyRows).toEqual(['Expectancy', 'Win rate', 'Payoff', 'Realised today']);`.

3. In `describe('tooltips', ...)`, `it('describe the panel and every KPI card', ...)`: keep the way v194 reads each hint, and change the expected texts of the panel and the five performance cards to their basis form: the panel's `PANEL_HELP.tradingPerformance` becomes `withBasis(PANEL_HELP.tradingPerformance)`, and `KPI_HELP.openPnl`, `KPI_HELP.winRate`, `KPI_HELP.expectancy`, `KPI_HELP.payoffRatio`, `KPI_HELP.realizedToday` become `PERF_BASIS.openPnl`, `PERF_BASIS.winRate`, `PERF_BASIS.expectancy`, `PERF_BASIS.payoffRatio`, `PERF_BASIS.realizedToday`. `Open trades` and `Avg confidence` keep `KPI_HELP.openTrades` and `KPI_HELP.avgConfidence`.

4. Append at the end of the file:

```ts
/* -- v195 §5.2 -- the performance strip leads with expectancy ------------ */

describe('trading performance leads with expectancy (v195 §5.2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
        { provide: ViewportService, useValue: { isPhone: signal(false) } },
      ],
    });
  });

  function mount(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(TradingPerformance);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f;
  }
  /** The cards' own inputs, in DOM order. */
  const cards = (f: ReturnType<typeof mount>) =>
    f.debugElement.queryAll(By.directive(MetricCard)).map((d) => d.componentInstance as MetricCard);
  const labels = (f: ReturnType<typeof mount>) => cards(f).map((c) => c.label());
  const cardSub = (f: ReturnType<typeof mount>, label: string) =>
    cards(f).find((c) => c.label() === label)!.sub();
  const cardHint = (f: ReturnType<typeof mount>, label: string) =>
    cards(f).find((c) => c.label() === label)!.description();
  const summaryLabels = (el: HTMLElement) =>
    [...el.querySelectorAll('.mobile-summary > div > span')].map((s) => s.textContent!.replace(/\s+/g, ' ').trim());
  const summaryRow = (el: HTMLElement, label: string) =>
    [...el.querySelectorAll<HTMLElement>('.mobile-summary > div')]
      .find((d) => d.querySelector('span')?.textContent?.trim() === label)!;

  it('opens the strip with Expectancy, then Win rate, then Payoff ratio', () => {
    expect(labels(mount({ currency: '€' }))).toEqual([
      'Expectancy', 'Win rate', 'Payoff ratio', 'Open P&L', 'Realised today', 'Open trades', 'Avg confidence',
    ]);
  });

  it('keeps that lead in Period mode, the period card after Realised today', () => {
    expect(labels(mount({ selection: { kind: 'preset', preset: '1M' }, currency: '€' }))).toEqual([
      'Expectancy', 'Win rate', 'Payoff ratio', 'Open P&L', 'Realised today', 'Realised in period',
      'Open trades', 'Avg confidence',
    ]);
  });

  it('shows N= on every rate card, payoff from the expectancy sample', () => {
    const f = mount({ expectancyR: 0.2, expectancyN: 42, winRate: 55, winRateN: 40, payoffRatio: 1.5, currency: '€' });
    expect(cardSub(f, 'Expectancy')).toBe('N=42');
    expect(cardSub(f, 'Win rate')).toBe('N=40');
    expect(cardSub(f, 'Payoff ratio')).toBe('N=42');
  });

  it('flags a thin sample in the stat tile\'s own words, and not from the threshold up', () => {
    const f = mount({ expectancyR: 0.2, expectancyN: 12, winRate: 55, winRateN: MIN_SAMPLE_N, payoffRatio: 1.5, currency: '€' });
    expect(cardSub(f, 'Expectancy')).toBe('N=12 · thin sample');
    expect(cardSub(f, 'Payoff ratio')).toBe('N=12 · thin sample');
    expect(cardSub(f, 'Win rate')).toBe(`N=${MIN_SAMPLE_N}`);
  });

  it('keeps the payoff no-close hint after its N', () => {
    const f = mount({ payoffRatio: null, expectancyN: 0, currency: '€' });
    expect(cardSub(f, 'Payoff ratio')).toBe('N=0 · thin sample · none closed today');
  });

  it('states the basis once in every performance hint, and not on the counts', () => {
    const f = mount({ selection: { kind: 'preset', preset: '1M' }, currency: '€' });
    for (const label of ['Expectancy', 'Win rate', 'Payoff ratio', 'Open P&L', 'Realised today', 'Realised in period']) {
      const hint = cardHint(f, label)!;
      expect(hint.split(PERFORMANCE_CAVEAT)).toHaveLength(2);
    }
    expect(cardHint(f, 'Expectancy')).toContain(KPI_HELP.expectancy);
    expect(cardHint(f, 'Realised in period')).toBe(PERF_BASIS.realized);
    expect(cardHint(f, 'Open trades')).toBe(KPI_HELP.openTrades);
    expect(cardHint(f, 'Avg confidence')).toBe(KPI_HELP.avgConfidence);
  });

  it('puts Expectancy before Win rate in the phone summary, each with its N', () => {
    const el = mount({ expectancyR: -0.16, expectancyN: 12, winRate: 49.1, winRateN: 40, payoffRatio: 2.34, currency: '€' })
      .nativeElement as HTMLElement;
    expect(summaryLabels(el)).toEqual(['Portfolio', 'Today', 'Open', 'Expectancy', 'Win rate', 'Payoff', 'Realised today']);
    expect(summaryRow(el, 'Expectancy').querySelector('strong')!.textContent).toContain('−0.16R');
    expect(summaryRow(el, 'Expectancy').querySelector('.n')!.textContent!.trim()).toBe('N=12 · thin sample');
    expect(summaryRow(el, 'Win rate').querySelector('.n')!.textContent!.trim()).toBe('N=40');
    expect(summaryRow(el, 'Payoff').querySelector('.n')!.textContent!.trim()).toBe('N=12 · thin sample');
  });

  it('shows no N line in the summary before a sample is known', () => {
    const el = mount({ currency: '€' }).nativeElement as HTMLElement;
    expect(el.querySelectorAll('.mobile-summary .n')).toHaveLength(0);
  });
});

describe('trading performance helpers (v195 §5.2)', () => {
  it('adds the caveat once', () => {
    expect(withBasis('Average R per trade.')).toBe(`Average R per trade. ${PERFORMANCE_CAVEAT}`);
    expect(withBasis(`Average R per trade. ${PERFORMANCE_CAVEAT}`)).toBe(`Average R per trade. ${PERFORMANCE_CAVEAT}`);
  });

  it('writes N, with the thin cue below the minimum', () => {
    expect(performanceSample(null)).toBeNull();
    expect(performanceSample(0)).toBe('N=0 · thin sample');
    expect(performanceSample(MIN_SAMPLE_N - 1)).toBe(`N=${MIN_SAMPLE_N - 1} · thin sample`);
    expect(performanceSample(MIN_SAMPLE_N)).toBe(`N=${MIN_SAMPLE_N}`);
    expect(performanceSample(10, 5)).toBe('N=10');
  });

  it('joins only the parts that exist', () => {
    expect(joinSub('N=4', null, 'none closed today')).toBe('N=4 · none closed today');
    expect(joinSub(null, null)).toBeNull();
  });
});
```

5. In `$WT/frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, change `import { TradingPerformance } from './panels/trading-performance';` to `import { TradingPerformance, withBasis } from './panels/trading-performance';`, and in `it('gives every panel on the page a tooltip saying what it is about', ...)` change the expected `PANEL_HELP.tradingPerformance` to `withBasis(PANEL_HELP.tradingPerformance)` (keep the reader v194 left there: a `title` attribute pre-v194, the panel's hint text after it). `it('explains each KPI card on hover, payoff ratio included', ...)` needs no change: it checks with `toContain`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL. Neither spec does not compile until `PERF_BASIS`, `withBasis`, `performanceSample` and `joinSub` exist (TS2305); once they do, the order cases find Open P&L first and Win rate before Expectancy, the payoff card has no `N=`, and no hint carries the caveat.

- [ ] **Step 3: Implement**

In `$WT/frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`:

1. Add `import { MIN_SAMPLE_N, PERFORMANCE_CAVEAT } from '../../../ui/stat-tile';` below the `MetricCard` import.

2. Below `export function presetLabel(...) { … }`, add:

```ts
/** v195 §5.2: every performance figure states its basis, in v194's one
 *  wording. Added once: a hint v194's content audit already extended is left
 *  as it is. */
export function withBasis(text: string): string {
  return text.includes(PERFORMANCE_CAVEAT) ? text : `${text} ${PERFORMANCE_CAVEAT}`;
}

/** "N=42", or "N=12 · thin sample" below the minimum: the stat tile's own
 *  small-N cue, in its own words, for the cards that are not stat tiles. */
export function performanceSample(n: number | null, minimum = MIN_SAMPLE_N): string | null {
  if (n === null) return null;
  return n < minimum ? `N=${n} · thin sample` : `N=${n}`;
}

/** A card's sub-line from its parts, " · " between the ones that exist. */
export function joinSub(...parts: (string | null)[]): string | null {
  const present = parts.filter((part): part is string => part !== null);
  return present.length ? present.join(' · ') : null;
}

/** The hints of the six performance cards, with the basis. Open trades and
 *  Avg confidence are counts, not performance, and keep theirs. */
export const PERF_BASIS = {
  openPnl: withBasis(KPI_HELP.openPnl),
  expectancy: withBasis(KPI_HELP.expectancy),
  winRate: withBasis(KPI_HELP.winRate),
  payoffRatio: withBasis(KPI_HELP.payoffRatio),
  realizedToday: withBasis(KPI_HELP.realizedToday),
  realized: withBasis(KPI_HELP.realized),
} as const;
```

3. In the class: change `protected readonly about = PANEL_HELP.tradingPerformance;` to `protected readonly about = withBasis(PANEL_HELP.tradingPerformance);` and add `protected readonly basis = PERF_BASIS;` below `protected readonly help = KPI_HELP;`. Replace

```ts
  protected sample(n: number | null): string | null { return n === null ? null : `N=${n}`; }
```

with

```ts
  /** v195 §5.2: N on every rate card, with the thin-sample cue. */
  protected sample(n: number | null): string | null { return performanceSample(n); }
```

   and below `protected noCloseHint(...) { … }` add:

```ts
  /** Payoff is computed from the same scoped R list as expectancy
   *  (payoff_ratio_from_rs over scoped_rs), so it carries expectancy's N,
   *  then the no-close hint when there is no figure. */
  protected readonly payoffSub = computed(() =>
    joinSub(this.sample(this.expectancyN()), this.noCloseHint(this.payoffRatio())));
```

4. In the template's `<sb-stat-strip class="grid" …>`, put the cards in this order, each card's other bindings unchanged except those named:

```html
          <sb-metric-card label="Expectancy" [description]="basis.expectancy" [value]="expectancyR()" [tint]="expectancyTone()" unit="R" [sub]="sample(expectancyN())" [loading]="loading()" />
          <sb-metric-card label="Win rate" [description]="basis.winRate" [value]="winRate()" [tint]="winPairTone()" unit="%" [decimals]="1" [sub]="sample(winRateN())" [loading]="loading()" />
          <sb-metric-card label="Payoff ratio" [description]="basis.payoffRatio" [value]="payoffRatio()" [tint]="payoffTone()" [decimals]="2" [sub]="payoffSub()" [loading]="loading()" />
          <sb-metric-card label="Open P&L" [description]="basis.openPnl" [value]="openPnlPct()" [tint]="openPnlTone()" unit="%" [sub]="openPnlSub()" [subPnl]="openPnlAmount()" />
```

   then the `Realised today` card with `[description]="basis.realizedToday"`, the `@if (inPeriod()) { … }` `Realised in period` card with `[description]="basis.realized"`, then `Open trades` and `Avg confidence` unchanged (`help.openTrades`, `help.avgConfidence`). If v194 V194-4b gave `Realised today` a `todayError`-driven `sub` or other binding, keep it; only the `description` binding changes.

5. In `<div class="mobile-summary" …>`: move the `Expectancy` row above the `Win rate` row, and give the three rate rows an N line inside their figure:

```html
        <div [attr.data-tone]="tinted(expectancyTone())" [class.busy]="loading()"><span>Expectancy @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(expectancyR(), 'R', 2) }}@if (sample(expectancyN()); as n) {<small class="n">{{ n }}</small>}</strong></div>
        <div [attr.data-tone]="tinted(winPairTone())" [class.busy]="loading()"><span>Win rate @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(winRate(), '%', 1) }}@if (sample(winRateN()); as n) {<small class="n">{{ n }}</small>}</strong></div>
        <div [attr.data-tone]="tinted(payoffTone())" [class.busy]="loading()"><span>Payoff @if (loading()) { <sb-spinner label="Updating" /> }</span><strong>{{ fmtFigure(payoffRatio(), '', 2) }}@if (sample(expectancyN()); as n) {<small class="n">{{ n }}</small>}</strong></div>
```

   The `Portfolio`, `Today` and `Open` rows stay first; the `Realised today` and `Realised in period` rows stay after `Payoff`, unchanged.

6. Styles: inside the `@media (max-width: 639px) { … }` block, after `.mobile-summary strong { font-family: var(--font-mono); }`, add:

```css
      /* v195 §5.2: the sample under each rate figure, quiet and never toned:
         it says how far to trust the figure, not whether it is good. */
      .mobile-summary strong .n { display: block; color: var(--text-secondary); font-size: var(--text-chip); font-weight: 400; text-align: right; }
```

7. The class doc comment: replace the paragraph that begins `Win rate, expectancy and payoff ratio travel together on purpose:` with:

```ts
 * Expectancy, win rate and payoff ratio travel together on purpose, in that
 * order (v195 §5.2): expectancy is the figure that says whether the book
 * pays, and win rate and payoff ratio decompose it, so read as a triple they
 * say why the expectancy is what it is. Win rate never leads. Each carries
 * its sample (`N=`, with the thin-sample cue below `MIN_SAMPLE_N`), and every
 * performance hint states the basis: paper fills, before costs and tax.
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. The existing `says why a figure is absent` case still reads exactly `none closed today` / `none closed in range` for the payoff card: it sets no `expectancyN`, so `payoffSub` is the hint alone. `phone summary carries win rate, expectancy, payoff and realised` still finds `−0.16R` (V195-7b) and `2.34` in the summary text. In `dashboard.spec.ts` the panel-tooltip case now finds the hint with its basis; if another of its cases compares a performance card's hint with `KPI_HELP.<key>` by equality (v194 may have added one), change that expectation to `PERF_BASIS.<key>` (the text now ends with the caveat). If the strip case finds `Open P&L` first, the card lines were moved but the `@if (inPeriod())` card was left above them.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 5: Close**

Close: standard (test: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`), plus `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/dashboard/panels/trading-performance.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git -C "$WT" commit -m "feat(v195): performance strip leads with expectancy, N and basis on every rate (V195-26)" -m "Spec §5.2 and correction 2: Trading performance opens with Expectancy, then Win rate, then Payoff ratio, never win rate first. Each rate card shows N= with the stat tile's thin-sample cue below MIN_SAMPLE_N, payoff from the expectancy sample it is computed from. Every performance hint and the panel hint end with v194's PERFORMANCE_CAVEAT (paper, gross of costs, pre-tax), added once. The phone summary follows the same order with N under each rate." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

