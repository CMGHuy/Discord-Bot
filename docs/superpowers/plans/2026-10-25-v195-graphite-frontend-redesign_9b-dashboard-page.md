# v195 — Graphite, Part 9b: Dashboard on `sb-page`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-27:" -A 400 <this file>`.

**Scope of this part (V195-27):** split from Part 9 (`2026-10-25-v195-graphite-frontend-redesign_9-risk-and-dashboard.md`) for the 1500-line cap, unchanged. V195-27 moves the Dashboard onto `sb-page`: a five-tile KPI strip (Expectancy, Win rate, Open risk as money · % linking to `/risk`, Realised in period, Open positions), Close all in `[page-actions]` (`danger-quiet`), the open positions table as the primary panel at the 14px order-figure step (§1.4), then Trading performance (full width), Recent activity and Market movers in the secondary grid. It runs after V195-26 (same lane: `dashboard.spec.ts`).

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 9's list binds this task (the `sb-page` contract and slot rule, `riskUnits`, `MINUS`/`rMultiple`/`money`, `StatTile` and its `about`/`hint`/`secondary`/`sample` inputs, `PERFORMANCE_CAVEAT`, V195-8's `danger-quiet`, the button and `title` gates). On top of that:

- `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (V195-26): exports `PERF_BASIS` (`openPnl`, `expectancy`, `winRate`, `payoffRatio`, `realizedToday`, `realized`: each `KPI_HELP` text plus the caveat), `withBasis`, `performanceSample`, `joinSub`, `presetLabel` (`'1D'` → `'Today'`). The panel's strip leads Expectancy, Win rate, Payoff ratio. Its inputs are unchanged, so `dashboard.ts` binds it as before.
- `dashboard.spec.ts` (V195-26): imports `withBasis` from `./panels/trading-performance`; the panel-tooltip case expects `withBasis(PANEL_HELP.tradingPerformance)`.
- `frontend/src/app/workspaces/dashboard/dashboard.ts` (V195-8, V195-13, v194): the close-all trigger is `<button sb-button variant="danger-quiet" … data-action="close-all" …>` inside `div.close-all-menu[table-actions]` (`#closeAllMenu`) projected into `sb-positions-table`; its `sb-confirm-dialog` uses the default `dangerVariant` (`danger-quiet`). v194 converted the positions panel's and cells' `title` explanations to hints and added the leg label and FX caveat; those stay as they are.
- `frontend/src/app/stores/dashboard.store.ts` (unchanged here): `balance()` (`account_balance`), `riskUsedPct()`, `riskCapPct()`, `expectancyR()`, `expectancyN()`, `winRate()`, `winRateN()`, `payoffRatio()`, `realizedAmount()`, `realizedCount()` (`realized.n`, 0 when absent), `openTrades()`, `selection(): ScopeSelection`.
- `panels/equity-range.model.ts` (unchanged): `ScopeSelection` (`{ kind: 'preset'; preset: ScopePreset } | { kind: 'range'; window: TimeWindow }`), `rangeChipLabel(window)`, `signTone(value)` and `breakevenPairTone(winRate, payoff, n)`, both typed `PnlTone` (`'pos' | 'neg' | 'warn' | 'neutral'`; a stat tile has no `warn`, hence `statTone`).

Re-read each file before editing it; every step names its edit by symbol or exact string.

---

# Phase 5 — Workspaces: Dashboard

### Task V195-27: Dashboard on `sb-page`: KPI strip (Expectancy, Win rate, Open risk money · % linking to `/risk`, Realised in period, Open positions); Close all in `[page-actions]` (`danger-quiet`); open positions primary; performance, activity and movers secondary
**Model:** sonnet — one workspace re-slotted onto an existing template, a KPI strip from figures the store already has, and a projection slot retired; the care is in the close-all menu keeping its outside-click and Escape behaviour from its new place, the open-risk link holding no nested button, and the order figures reaching the 14px step.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (template on `sb-page`; `DASHBOARD_PANEL_ORDER` and its doc comment; `scopeLabel`, `statTone` exported; KPI computeds; imports; styles; class doc comment)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (imports; the in-page-heading, panel-order and old-metric-rows cases updated; three appended `describe` blocks)
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.ts` (the `[table-actions]` projection removed; the 14px order-figure step on the host; doc comment)
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.spec.ts` (one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21); `riskUnits` (`ui/risk-units.ts`, V195-7); `rMultiple`, `money`, `share`, `num` (`ui/format.ts`; `rMultiple`/`money` sign with `+`/`MINUS`); `StatStrip`, `StatTile`, `StatTone` (`ui/stat-tile.ts`); `PERF_BASIS`, `presetLabel` (`panels/trading-performance.ts`, V195-26); `KPI_HELP` (`panels/panel-help.ts`); `ScopeSelection`, `rangeChipLabel`, `signTone`, `breakevenPairTone`, `PnlTone` (`panels/equity-range.model.ts`); `DashboardStore` members listed in this part's header; `ConnectionStore.currency()`; `RouterLink` (`@angular/router`); `RouteTitleService.set(title, subtitle)` (spec only).
- Produces (nothing a later task consumes beyond V195-33's `workspace-consistency` check that `dashboard.ts` contains `<sb-page` and imports `Page`):
  - `dashboard.ts` exports `scopeLabel(selection: ScopeSelection): string` (`'Today'` for 1D, `'All days'` for All, the preset code otherwise, the range chip label for a range) and `statTone(tone: PnlTone): StatTone` (`'warn'` → `'neutral'`).
  - `DASHBOARD_PANEL_ORDER` = `['kpis', 'positions', 'performance', 'activity', 'movers']` for every band (`xs`, `sm`, `md`, `lg`, `xl`).
  - Markup: `sb-page` > `div.close-all-menu[page-actions]` (`#closeAllMenu`, `button[data-action="close-all"]`, `variant="danger-quiet"`, the menu); `sb-stat-strip.kpis[page-kpis]` with `sb-stat-tile`s `Expectancy`, `Win rate`, then `a.kpi-link[href="/risk"]` around `Open risk`, then `Realised in period`, `Open positions`; `sb-panel.positions-panel[page-primary]`; secondary `sb-async.performance-async` (full width), `sb-async.activity-async`, `sb-async.movers-async`; then the close-all `sb-confirm-dialog` and the trade drawer in the default slot.
  - `sb-positions-table` no longer projects `[table-actions]`; its host sets `--text-table: var(--text-body)`.

**What changes, and what is already there.** Spec Phase 4, §5.2, §5.1 and §1.4, and the index's plan decision 2. Today the Dashboard is a hand-laid grid: the Trading performance panel, the Open positions panel (whose table header carries the Close all menu), then a two-up row of Recent activity and Market movers. After this task it renders `sb-page`. The route title is the page's one `h1`. **Close all** (a money-moving bulk action) leaves the table header for the page header's actions slot, as `danger-quiet`, with its three-scope menu, its outside-click and Escape dismissal and its confirm dialog unchanged; `sb-positions-table` stops projecting `[table-actions]`, which nothing else used. **The KPI strip** holds what the partner acts on, from figures the store already has (plan decision 2): Expectancy first and Win rate after (§5.2; each with `N=` and the thin-sample cue through `StatTile.sample`, the scope it covers as its secondary line, and the basis in its About hint from V195-26's `PERF_BASIS`), Open risk as money · % of account with the cap beneath in the same two units, Realised in period (signed money, `N=` closes), Open positions. The Open risk tile is a link to `/risk`, where concentration lives (§5.1: Dashboard links to it, never repeats it); it carries a visible "Breakdown on Risk →" line instead of an About hint, because an `sb-hint` is a button and cannot sit inside a link (correction 10). The spec's "month R" is an example with no source field, so it is not added (plan decision 2). **Open positions is the primary panel**, and its figures (entry, stop, target, size in the plan and table cells) read the 14px body step in both densities: the positions table sets `--text-table` to `--text-body` on its own host, so only this table grows. **Trading performance** (portfolio value, equity candles, the eight cards and the scope presets) moves to the secondary grid, first and spanning both columns, so its candles keep the full width v172 needs; Recent activity and Market movers follow, side by side from 1440px. `DASHBOARD_PANEL_ORDER` records the new order at every band and its v95 C3 note is rewritten: v95 moved performance above the table because the phone buried the portfolio figure, win rate and expectancy under ~900px of rows; the KPI strip now puts expectancy, win rate and open risk above the table at every width, which answers that finding, and the spec names open positions as the primary panel.

- [ ] **Step 1: Write the failing tests**

1. In `$WT/frontend/src/app/workspaces/dashboard/dashboard.spec.ts`:

   - Add below the existing imports:

```ts
import { RouteTitleService } from '../../routing/route-title.service';
import { StatTile } from '../../ui/stat-tile';
import { PERF_BASIS } from './panels/trading-performance';
import { scopeLabel, statTone } from './dashboard';
```

     (merge `scopeLabel, statTone` into the existing `import { Dashboard, DASHBOARD_COLUMNS, DASHBOARD_PANEL_ORDER } from './dashboard';`, giving `import { Dashboard, DASHBOARD_COLUMNS, DASHBOARD_PANEL_ORDER, scopeLabel, statTone } from './dashboard';`, and merge `PERF_BASIS` into the `./panels/trading-performance` import V195-26 left: `import { PERF_BASIS, TradingPerformance, withBasis } from './panels/trading-performance';`).

   - Replace `it('renders no in-page heading, because the top bar owns the title', ...)` with:

```ts
  it('renders the route title as the one h1, from sb-page', () => {
    const { fixture } = seed();
    TestBed.inject(RouteTitleService).set('Dashboard', "What's happening right now");
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Dashboard');
  });
```

   - Replace the whole `describe('Dashboard panel order', ...)` first case `it('leads with performance at every band', ...)` with:

```ts
  it('leads with the KPI strip, then open positions, at every band (v195 §5.2)', () => {
    // v95 C3 put performance first because a phone buried the portfolio
    // figure, win rate and expectancy under a ~900px table. The KPI strip now
    // carries expectancy, win rate and open risk above the table everywhere,
    // and the spec makes open positions the primary panel.
    for (const band of ['xs', 'sm', 'md', 'lg', 'xl'] as const) {
      expect(DASHBOARD_PANEL_ORDER[band]).toEqual(['kpis', 'positions', 'performance', 'activity', 'movers']);
    }
  });
```

     (the second case, `no longer carries an undeclared breakpoint`, stays.)

   - In `it('drops the old metric rows the panels replaced', ...)` change `expect(el.querySelector('.primary')).toBeNull();` to `expect(el.querySelector('.primary:not(.slot)')).toBeNull();` (the retired metric row was `.primary`; `sb-page`'s primary slot is `div.primary.slot`).

   - Append at the end of the file:

```ts
/* -- v195 Phase 4, §5.2 -- the Dashboard on sb-page ------------------------- */

/** The KPI tiles' own inputs, read from the components: the rendered value
 *  counts up, the input is the figure. */
function kpis(fixture: ComponentFixture<Dashboard>): Map<string, StatTile> {
  return new Map(fixture.debugElement.queryAll(By.css('[page-kpis] sb-stat-tile'))
    .map((d) => d.componentInstance as StatTile)
    .map((tile) => [tile.label(), tile] as const));
}

describe('Dashboard on sb-page (v195 Phase 4)', () => {
  it('puts open positions in the primary slot, then performance, activity and movers', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-page div.primary.slot > sb-panel.positions-panel')).not.toBeNull();
    const secondary = [...el.querySelectorAll('sb-page div.secondary.slot > [page-secondary]')];
    const names = ['performance-async', 'activity-async', 'movers-async'];
    expect(secondary.map((s) => names.find((name) => s.classList.contains(name))))
      .toEqual(names);
    expect(secondary[0].querySelector('sb-trading-performance')).not.toBeNull();
  });

  it('puts Close all in the header actions as danger-quiet, and nowhere in the table', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const el = fixture.nativeElement as HTMLElement;
    const button = el.querySelector<HTMLButtonElement>('sb-page header.bar .actions [data-action="close-all"]');
    expect(button).not.toBeNull();
    expect(button!.classList).toContain('danger-quiet');
    expect(button!.classList).not.toContain('danger');
    expect(el.querySelector('sb-positions-table [data-action="close-all"]')).toBeNull();
  });

  it('opens the close-all menu from the header and closes it on an outside click', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('[data-action="close-all"]')!.click();
    fixture.detectChanges();
    expect(el.querySelectorAll('sb-page header.bar .actions [role="menuitem"]')).toHaveLength(3);

    el.querySelector<HTMLElement>('sb-page h1.title')!.click();
    fixture.detectChanges();
    expect(el.querySelectorAll('[role="menuitem"]')).toHaveLength(0);
  });

  it('projects the close-all dialog and nothing destructive into a scope bar', async () => {
    const el = (await loaded()).nativeElement as HTMLElement;
    expect(el.querySelector('sb-page sb-confirm-dialog')).not.toBeNull();
    expect(el.querySelector('sb-page div.scope.slot')!.children).toHaveLength(0);
  });
});

describe('Dashboard KPI strip (v195 §5.2)', () => {
  it('holds expectancy first, win rate after, then open risk, realised and open positions', async () => {
    expect([...kpis(await loaded()).keys()])
      .toEqual(['Expectancy', 'Win rate', 'Open risk', 'Realised in period', 'Open positions']);
  });

  it('gives expectancy and win rate their N, signed figures and the scope they cover', async () => {
    const tiles = kpis(await loaded({ expectancy_r: -0.16, expectancy_n: 12, win_rate: 55, win_rate_n: 40 }));
    expect(tiles.get('Expectancy')!.value()).toBe('−0.16R');
    expect(tiles.get('Expectancy')!.sample()).toBe(12);
    expect(tiles.get('Expectancy')!.tone()).toBe('neg');
    expect(tiles.get('Expectancy')!.secondary()).toBe('Today');
    expect(tiles.get('Win rate')!.value()).toBe('55.0%');
    expect(tiles.get('Win rate')!.sample()).toBe(40);
  });

  it('states the paper / pre-cost / pre-tax basis in every performance hint', async () => {
    const tiles = kpis(await loaded());
    expect(tiles.get('Expectancy')!.about()).toBe(PERF_BASIS.expectancy);
    expect(tiles.get('Win rate')!.about()).toBe(PERF_BASIS.winRate);
    expect(tiles.get('Realised in period')!.about()).toBe(PERF_BASIS.realized);
  });

  it('shows open risk as money and % of account, the cap beneath, linking to Risk', async () => {
    const fixture = await loaded({ account_balance: 10000, risk_used_pct: 3, risk_cap_pct: 20 });
    const tiles = kpis(fixture);
    expect(tiles.get('Open risk')!.value()).toBe('300 $ · 3.00%');
    expect(tiles.get('Open risk')!.secondary()).toBe('cap 2,000 $ · 20.00%');
    expect(tiles.get('Open risk')!.hint()).toBe('Breakdown on Risk →');

    const link = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>('[page-kpis] a.kpi-link')!;
    expect(link.getAttribute('href')).toBe('/risk');
    expect(link.querySelector('sb-stat-tile .label')!.textContent!.trim()).toBe('Open risk');
    // A hint is a button, and a button cannot sit inside a link.
    expect(link.querySelector('button, sb-hint')).toBeNull();
  });

  it('never invents money without a balance', async () => {
    const tiles = kpis(await loaded({ account_balance: null, risk_used_pct: 3 }));
    expect(tiles.get('Open risk')!.value()).toBe('— · 3.00%');
  });

  it('shows realised money signed, with the closes behind it as N, and the open count', async () => {
    const tiles = kpis(await loaded({
      realized: { amount: -40, pct: -0.4, n: 3, wins: 1, losses: 2 } as never, open_trades: 2,
    }));
    expect(tiles.get('Realised in period')!.value()).toBe('−40.00 $');
    expect(tiles.get('Realised in period')!.sample()).toBe(3);
    expect(tiles.get('Realised in period')!.tone()).toBe('neg');
    expect(tiles.get('Open positions')!.value()).toBe('2');
  });
});

describe('Dashboard KPI helpers (v195 §5.2)', () => {
  it('names the scope in the strip\'s words', () => {
    expect(scopeLabel({ kind: 'preset', preset: '1D' })).toBe('Today');
    expect(scopeLabel({ kind: 'preset', preset: '1M' })).toBe('1M');
    expect(scopeLabel({ kind: 'preset', preset: 'All' })).toBe('All days');
  });

  it('maps a P&L tone onto a stat tone, warn to neutral', () => {
    expect(statTone('pos')).toBe('pos');
    expect(statTone('neg')).toBe('neg');
    expect(statTone('warn')).toBe('neutral');
    expect(statTone('neutral')).toBe('neutral');
  });
});
```

2. In `$WT/frontend/src/app/workspaces/dashboard/positions-table.spec.ts`, append at the end of the file (add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top if the file does not import them yet):

```ts
/* -- v195 Phase 4 and §1.4 -------------------------------------------------- */

describe('positions table after the Dashboard moved onto sb-page', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/positions-table.ts'), 'utf8');

  it('no longer projects table actions: Close all is the page header\'s', () => {
    expect(src).not.toContain('table-actions');
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts
```

Expected: FAIL. `dashboard.spec.ts` does not compile until `scopeLabel` and `statTone` exist (TS2305); once they do, no `sb-page`, no `[page-kpis]` and no header `close-all` are found, and the panel order still leads with `performance`. The positions-table cases find `table-actions` and no `--text-table` override.

- [ ] **Step 3: Retire the table-actions slot and lift the order figures**

In `$WT/frontend/src/app/workspaces/dashboard/positions-table.ts`:

1. In the template, delete `<ng-content select="[table-actions]" />` (the `.table-head` keeps its `View in Trades →` link).

2. In the styles, change `:host { display: block; }` to:

```css
    /* v195 §1.4: entry, stop, target and size are order figures and never
       shrink below the 14px body step, in either density. The table and the
       plan cell read --text-table; this table alone re-points it. */
    :host { display: block; --text-table: var(--text-body); }
```

3. In the class doc comment, after the paragraph that starts `Only CLOSED and CANCELLED honour the page's Today/All scope.`, add:

```ts
 *
 * Close all is the Dashboard page header's (v195 Phase 4), so this table
 * projects no actions of its own.
```

- [ ] **Step 4: Move the Dashboard onto `sb-page`**

In `$WT/frontend/src/app/workspaces/dashboard/dashboard.ts`:

1. Imports. Add `import { RouterLink } from '@angular/router';` beside the existing `ActivatedRoute, Router` import (merge: `import { ActivatedRoute, Router, RouterLink } from '@angular/router';`). In the `'../../ui/format'` import add `num`, `rMultiple` and `share` beside what is there (keep v194's additions). Add:

```ts
import { Page } from '../../ui/page';
import { riskUnits } from '../../ui/risk-units';
import { StatStrip } from '../../ui/stat-strip';
import { StatTile, StatTone } from '../../ui/stat-tile';
import { PERF_BASIS, presetLabel } from './panels/trading-performance';
import {
  PnlTone, ScopeSelection, breakevenPairTone, rangeChipLabel, signTone,
} from './panels/equity-range.model';
```

   (If `dashboard.ts` already imports `TradingPerformance` from `./panels/trading-performance` or names from `./panels/equity-range.model`, merge into those lines.) `KPI_HELP` comes from `./panels/panel-help`, which the file already imports for `PANEL_HELP`: make it `import { KPI_HELP, PANEL_HELP } from './panels/panel-help';`. In the component's `imports: [...]` add `Page`, `RouterLink`, `StatStrip`, `StatTile`.

2. Replace the `DASHBOARD_PANEL_ORDER` doc comment and constant (from `/**` / ` * Panel order per band — v95 C3` through the constant's closing `};`) with:

```ts
/** The page's order, top to bottom. */
const PAGE_ORDER = ['kpis', 'positions', 'performance', 'activity', 'movers'];

/**
 * Panel order per band — v95 C3, re-decided in v195 §5.2.
 *
 * v95 moved performance above the positions table because on a phone the
 * portfolio figure, win rate and expectancy sat below ~900px of rows. v195
 * answers that with the KPI strip: expectancy, win rate and open risk sit
 * above the table at every width, and the spec makes open positions the
 * primary panel, with Trading performance (portfolio value, candles, the
 * full card set) first in the secondary grid.
 *
 * A declaration, not a live reorder: sb-page's slots already render in this
 * order (KPIs, primary, secondary) at every band, and the secondary
 * elements sit in the template in this order.
 */
export const DASHBOARD_PANEL_ORDER: Partial<Record<Viewport, string[]>> = {
  xs: PAGE_ORDER,
  sm: PAGE_ORDER,
  md: PAGE_ORDER,
  lg: PAGE_ORDER,
  xl: PAGE_ORDER,
};

/** The scope a KPI covers, in the panel's own words: "Today" for 1D,
 *  "All days" for All, the preset code otherwise, the dates for a range. */
export function scopeLabel(selection: ScopeSelection): string {
  if (selection.kind === 'range') return rangeChipLabel(selection.window);
  return selection.preset === 'All' ? 'All days' : presetLabel(selection.preset);
}

/** A stat tile has no amber: the P&L helpers' `warn` reads as neutral. */
export function statTone(tone: PnlTone): StatTone {
  return tone === 'pos' || tone === 'neg' ? tone : 'neutral';
}
```

3. The template. Apply these edits in order. Every element named "move" keeps its markup, bindings, comments and v194 hints exactly as they are; only its position and the attributes named here change.

   a. At the top of the template (before the `<!-- Each panel owns its first-load state. … -->` comment) insert:

```html
    <sb-page>
      <!-- v195 Phase 4: Close all is a money-moving bulk action, so it sits
           in the page header's actions, danger-quiet, behind its menu and its
           confirm dialog. Deliberately not clear-open (it DELETES records and
           stays on Trades) -- see closeAllConsequence for the wording that
           keeps the two apart. A dropdown, not one button: ACTIVE and PARTIAL
           are different enough states that closing only one of them is a
           real, distinct action. -->
      <div page-actions class="close-all-menu" #closeAllMenu>
        <!-- MOVE here: the <button sb-button variant="danger-quiet" … data-action="close-all" …>
             trigger and its @if (closeAllMenuOpen()) { <div class="menu elev-overlay" role="menu"> … } block,
             unchanged, from the old div.close-all-menu[table-actions]. -->
      </div>

      <!-- v195 §5.2: the figures acted on, from what the store already has.
           Expectancy leads and win rate follows, each with its N and basis;
           open risk in money and % of account, linking to the breakdown on
           Risk (concentration lives there, §5.1). -->
      <sb-stat-strip page-kpis class="kpis">
        <sb-stat-tile label="Expectancy" [value]="expectancyText()" [sample]="store.expectancyN()"
                      [tone]="expectancyTone()" [secondary]="scope()" [about]="basis.expectancy" />
        <sb-stat-tile label="Win rate" [value]="winRateText()" [sample]="store.winRateN()"
                      [tone]="winRateTone()" [secondary]="scope()" [about]="basis.winRate" />
        <!-- A link, so no About hint: an sb-hint is a button, and a button
             cannot sit inside a link (correction 10). The visible line says
             where it goes. -->
        <a class="kpi-link" routerLink="/risk">
          <sb-stat-tile label="Open risk" [value]="openRiskText()" [secondary]="riskCapText()"
                        hint="Breakdown on Risk →" />
        </a>
        <sb-stat-tile label="Realised in period" [value]="realizedText()" [sample]="store.realizedCount()"
                      [tone]="realizedTone()" [secondary]="scope()" [about]="basis.realized" />
        <sb-stat-tile label="Open positions" [value]="openPositionsText()" [about]="help.openTrades" />
      </sb-stat-strip>
```

   b. Move the `<button sb-button variant="danger-quiet" type="button" data-action="close-all" …> … </button>` element and the `@if (closeAllMenuOpen()) { … }` block from `<div class="close-all-menu" table-actions #closeAllMenu>` into the new `div.close-all-menu[page-actions]`, replacing the `<!-- MOVE here: … -->` comment. Then delete the old `<div class="close-all-menu" table-actions #closeAllMenu> … </div>` (now empty) and the `<!-- v85 D13/D14: replaces the mockup's "+ New Trade" … -->` comment above it (its content is in the new comment). `sb-positions-table` keeps every binding and gets no children.

   c. `<sb-panel class="positions-panel" heading="Open positions" …>`: add `page-primary` to its opening tag (`<sb-panel page-primary class="positions-panel" heading="Open positions" …>`), and move the whole panel (with its lifecycle `sb-hint` and `sb-positions-table`) to directly after the `sb-stat-strip`.

   d. The performance `sb-async class="performance-async"` with its two comments and the `div.performance-stack` inside: add `page-secondary` to its opening tag (`<sb-async page-secondary class="performance-async" …>`) and place it directly after the positions panel.

   e. Delete the `<div class="bottom-row">` wrapper and its closing `</div>`; the two `sb-async`s inside it follow the performance async directly, as `<sb-async page-secondary class="activity-async" [loading]="activityAsync().loading" …>` (around `sb-recent-activity`) and `<sb-async page-secondary class="movers-async" [loading]="tapeAsync().loading" …>` (around `sb-market-movers`), all other bindings unchanged.

   f. Leave the close-all `<sb-confirm-dialog [open]="confirmCloseAll() !== null" … />` and the `@if (drawerTrade(); as trade) { <sb-trade-drawer … /> }` block with its comment after the movers async, then close the page with `</sb-page>`. The `<ng-template #statusCell>` … `<ng-template #actionsCell>` cell templates stay after `</sb-page>`, unchanged.

   After the edit, `git -C "$WT" grep -n -E "page-(actions|kpis|primary|secondary)" -- frontend/src/app/workspaces/dashboard/dashboard.ts` prints exactly six template lines (one `page-actions`, one `page-kpis`, one `page-primary`, three `page-secondary`) plus the comment mentions, and `git -C "$WT" grep -n "table-actions" -- frontend/src/app/workspaces/dashboard/` prints nothing.

4. The class. After `protected readonly connection = inject(ConnectionStore);` add:

```ts

  /* -- v195 §5.2: the KPI strip ----------------------------------------- */

  protected readonly basis = PERF_BASIS;
  protected readonly help = KPI_HELP;
  /** Which window the scoped figures cover: Today, 1M, All days, a range. */
  protected readonly scope = computed(() => scopeLabel(this.store.selection()));

  protected readonly expectancyText = computed(() => rMultiple(this.store.expectancyR()));
  protected readonly expectancyTone = computed(() => statTone(signTone(this.store.expectancyR())));
  protected readonly winRateText = computed(() => share(this.store.winRate(), 1));
  /** Judged against break-even with the payoff, as the panel judges it. */
  protected readonly winRateTone = computed(() => statTone(
    breakevenPairTone(this.store.winRate(), this.store.payoffRatio(), this.store.winRateN())));

  /** Money and % of account together (§5.2), against the dollar-risk cap. */
  protected readonly openRiskText = computed(() =>
    riskUnits(this.store.riskUsedPct(), this.store.balance(), this.connection.currency()));
  protected readonly riskCapText = computed(() => {
    const cap = this.store.riskCapPct();
    return cap === null ? null : `cap ${riskUnits(cap, this.store.balance(), this.connection.currency())}`;
  });

  protected readonly realizedText = computed(() => money(this.store.realizedAmount(), this.connection.currency()));
  protected readonly realizedTone = computed(() => statTone(signTone(this.store.realizedAmount())));
  protected readonly openPositionsText = computed(() => num(this.store.openTrades(), 0));
```

   If v194 already declared a member named `help`, `basis` or `scope` on this class, rename the new one (`kpiHelp`, `kpiBasis`, `kpiScope`) in both the class and the template.

5. The class doc comment: after its first paragraph add:

```ts
 *
 * **On `sb-page` (v195 Phase 4, §5.2).** The route title is the page's one
 * `h1`; Close all is the header's action. The KPI strip leads with
 * expectancy, then win rate, open risk (money and % of account, linking to
 * Risk), realised in the period and the open count. Open positions is the
 * primary panel; Trading performance, Recent activity and Market movers
 * are secondary.
```

6. Styles:
   - Replace `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }` and its comment block above it (from `/* minmax(0, 1fr), not the implicit auto track.` through `register instead of a hardcoded token. */`) with:

```css
    /* v195 Phase 4: sb-page lays out the header, the KPI strip, the primary
       panel and the secondary grid, and owns their gaps; the host is only a
       block. No backticks in here: these styles live in a TS template
       literal. */
    :host { display: block; }

    /* Trading performance keeps the full width: its candles need it (v172). */
    .performance-async { grid-column: 1 / -1; }

    /* The open-risk tile is a link to Risk: the tile fills the cell, the link
       adds only the hover and the focus ring. */
    .kpi-link { display: block; min-width: 0; color: inherit; text-decoration: none; }
    .kpi-link:hover { background: var(--surface-raised); }
    .kpi-link:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
```

   - Delete the `.bottom-row { … }` rule and the comment above it (`/* Both panels below own their OWN top margin, …`).
   - In the comment above `.close-all-menu { position: relative; display: inline-flex; }`, replace `this sits inside the table's own right-aligned actions slot, and a left-aligned menu would spill it past the table's right edge.` with `this sits at the right of the page header, and a left-aligned menu would spill past the page's right edge.`
   - In the comment that starts `/* v95 C3: the phone reorder above (positions before performance) is` replace its text with `/* v195 §5.2: the order is sb-page's slots, the same at every band -- see DASHBOARD_PANEL_ORDER. Nothing here reorders. */`, keeping the `@media (max-width: 639px) { … }` rule below it.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. Every `Dashboard v85 close-all` case still passes (the trigger, the menu items and the dialog are the same elements, found by `[data-action="close-all"]` and `[role="menuitem"]` anywhere). If the outside-click case leaves the menu open, `#closeAllMenu` is no longer on the element that wraps the trigger and the menu: it must sit on `div.close-all-menu[page-actions]`. If the open-risk case finds a `button` inside the link, an `about` was bound on that tile. If `loaded({ realized: … })` leaves `Realised in period` at `—`, the payload key is `realized` (`Dashboard.realized`), check the cast. If `workspace-consistency.spec.ts` flags a fixed `repeat(N`, a `cols` was bound on the strip: the KPI strip keeps the strip's default auto-fit. If the `money` case expects a different form, `money()`'s unit suffix is `' $'` after the figure (V195-7); match the formatter, never the other way round.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 6: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`. At 1440, 768 and 390: one `h1` reading `Dashboard`; `Close all open/partial` at the header's right, quiet-bordered (not solid), wrapping under the title at 390, at least 44px tall at 768 and 390; open its menu, see the three scopes, press Escape and click outside (both close it), and do **not** confirm a close. The KPI strip reads Expectancy, Win rate, Open risk, Realised in period, Open positions, with `N=` under the two rates, open risk as `<money> <unit> · <pct>%` and a "Breakdown on Risk →" line; click Open risk and land on `/risk`, then go back. Open positions sits directly under the strip; in it, `getComputedStyle(document.querySelector('sb-positions-table sb-plan-cell .plan')).fontSize` is `14px` at 1440 with density dense and with comfortable, and at 768 and 390. Trading performance follows at full width with its candles; Recent activity and Market movers sit side by side at 1440 and stacked below. No horizontal page scroll at any width (`document.documentElement.scrollWidth <= innerWidth`). Save the PNGs under the session scratchpad.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`), plus `frontend/src/app/workspaces/dashboard/positions-table.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/workspaces/dashboard/positions-table.ts frontend/src/app/workspaces/dashboard/positions-table.spec.ts
git -C "$WT" commit -m "feat(v195): Dashboard on sb-page, KPI strip led by expectancy (V195-27)" -m "Spec Phase 4, §5.2, §5.1 and §1.4: the Dashboard renders sb-page. Close all moves from the positions table header to the page header, danger-quiet, menu and confirm unchanged; sb-positions-table no longer projects table actions. A KPI strip shows Expectancy then Win rate (N, scope, paper/pre-cost/pre-tax hint), Open risk in money and % of account linking to Risk, Realised in period and the open count. Open positions is primary, its order figures on the 14px body step; Trading performance (full width), Recent activity and Market movers are secondary. DASHBOARD_PANEL_ORDER records the new order: the strip now answers v95 C3's buried-figures finding above the table at every width." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

