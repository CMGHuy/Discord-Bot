# v195 — Graphite, Part 11b: Versions, the `/ui` gallery and the workspace-consistency gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-33:" -A 600 <this file>`.

**Scope of this part (V195-33):** split from Part 11 (`2026-10-25-v195-graphite-frontend-redesign_11-calendar-insights-gallery.md`) for the 1500-line cap. Spec §5.1 (the `/ui` gallery stays off the rail and becomes the reference page for every primitive), §5.2 and Phase 4 (Versions on `sb-page`; destructive actions only in the header), and § Testing (`workspace-consistency.spec.ts` extended to assert every route uses `sb-page`). It runs after every Phase 5 task (index § Parallelisation): its gate reads the final shape of every workspace.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 11's list binds this task (the `sb-page` contract and spec patterns, `StatTile` with `about` and `PERFORMANCE_CAVEAT`, `StatStrip`). On top of that, the final shape of every route entry the gate reads, from Parts 8b–11:

- Every route entry component renders `<sb-page` and imports `Page` from `ui/page`: `dashboard/dashboard.ts` (V195-27), `trades/trades.ts` (V195-29), `trades/trade-detail.ts`, `plans/plan-detail.ts` (V195-30), `analytics/analytics.ts`, `research/research.ts`, `reports/reports.ts` (V195-32), `calendar/calendar.ts`, `calendar/day/calendar-day.ts`, `cancels/cancels.ts` (V195-31), `watchlist/watchlist.ts`, `watchlist/ticker-detail.ts` (V195-28), `risk/risk.ts` (V195-25), `system/system.ts` (V195-24); this task adds `versions/versions.ts` and `gallery/gallery.ts`. Each has exactly one `page-primary` element.
- Destructive controls (a button whose `variant` is `danger` or `danger-quiet`, static or in a `[variant]` binding) in workspace sources sit inside the page's `[page-actions]` element: Risk's killswitch (`[variant]="store.killswitchOn() ? 'secondary' : 'danger'"`), Dashboard's `data-action="close-all"`, Trades' `clear-open` / `clear-history` (`data-action`; `TRADES_CONTROLS` is 13 entries), trade detail's command row (`[variant]="kind === 'delete' ? 'danger-quiet' : 'secondary'"`), System's `restart` / `clear-log` / `discard`. **Per-row commands stay in their row**: Watchlist's row bin (`variant="danger-icon"`, its own confirm) and the Analytics Tuning tab's per-proposal `Delete` (`analytics/tabs/tuning.ts`, `variant="danger-quiet"` since V195-8, `(click)="pendingDelete.set(proposal)"`, its own confirm). Plan detail, ticker detail, Calendar, the calendar day, Cancels, Analytics, Research, Reports have no destructive control.
- Shapes the gate must accept: Trades has no KPI strip and no secondary panel; plan detail has no `[page-actions]`; trade and plan detail put their identity header in `div.summary[page-kpis]`; Reports puts `sb-freshness` itself in `[page-actions]` and `sb-tab-bar` itself in `[page-scope]`; Risk and System project `sb-confirm-dialog`s through the default slot. `SectionHead` is no longer imported by any route entry except `gallery.ts` (which demos it); `dashboard.ts` keeps one comment mentioning `sb-section-head`, not an element.
- `ui/button.spec.ts` (V195-8) already pins `variant="danger"` / `'danger'` to the Risk killswitch and the gallery; this task's gate does not repeat it.
- `ui/hint.ts` (V195-14): `Hint.anchor = input<HTMLElement | null>(null)`; with an anchor it renders no trigger button, opens on the anchor's hover and focus, and its host gets class `anchored`. Usage: `<a #link …>…</a><sb-hint [anchor]="link" [text]="…" />`. `ui/risk-units.ts` (V195-7): `riskUnits(pct, balance, unit)` → `'1,420 $ · 1.42%'`.
- **Known gap from V195-21** (see the return's OPEN): `gallery.spec.ts`'s `the gallery shows every primitive` generates `renders sb-page` from every `selector: 'sb-…'` under `ui/`, and `ui/page.ts` added one; if V195-21's implementer did not already add `<sb-page` to `gallery.ts`, that one case has been red since V195-21 and this task turns it green. If V195-21 did add a minimal `sb-page` wrapper, this task replaces it with the layout below.

v194 and V195-1..V195-32 edited files below. Each step names its edit by symbol or quoted string, never by line number; re-read each file before editing it.

---

# Phase 5 — Workspaces: Versions, gallery and the gate

### Task V195-33: Versions on `sb-page`; `/ui` gallery re-laid out as the primitive reference (`danger` / `danger-quiet`, `sb-page`, KPI strip, rail label hint); `workspace-consistency` asserts every route entry uses `sb-page`
**Model:** sonnet — one small workspace re-slotted, a reference page re-framed around the template it demonstrates, and a source-scanning spec; the care is in the gate deriving the route list from the route files rather than trusting a hand list, and in its tag scanner placing every destructive button inside or outside the header actions without false alarms on per-row commands.

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts` (template on `sb-page`; imports; styles)
- Modify: `frontend/src/app/workspaces/versions/versions.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` (template wrapped in `sb-page` with a demo in every slot; a *Destructive actions* panel; an anchored-hint panel; new members; imports; styles; class doc comment)
- Modify: `frontend/src/app/workspaces/gallery/gallery.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/workspace-consistency.spec.ts` (imports; the D4 case's name; `PAGE_ROUTES`, `ROW_COMMANDS` and the scanner helpers; one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, V195-21); `RouteTitleService.set` (spec only); `ConfirmDialog` (`open`, `title`, `consequence`, `confirmLabel`, `dangerVariant`, `confirmed`, `cancelled`) and `Button` variants `danger` / `danger-quiet` / `danger-icon` (V195-8); `StatStrip`, `StatTile` (`about`), `PERFORMANCE_CAVEAT`; `riskUnits` (`ui/risk-units.ts`, V195-7); `Hint.anchor` (V195-14); `Icon` with `'dashboard'` in `ICON_NAMES`; `Segmented`, `SegmentOption`; `allSources()` (`ui/testing/all-sources.ts`: `{ name, source }[]`, names relative to `src/` like `'app/workspaces/risk/risk.ts'`, specs excluded); `installDialogPolyfill` (spec only); the existing `Versions` members (`store`, `async`, the lane and timeline members) and `Gallery` members (`segmentOptions`, `segmentValue`, `confirmOpen`, `buttonVariants`, …).
- Produces (V195-36's full suite runs it; nothing else consumes it):
  - Versions markup: `sb-page` > `div.head-status[page-actions]` (the stale-history notice, if `store.stale()`); `sb-async[page-primary]` (everything it held, unchanged). No `sb-section-head`, no scope or KPI slot.
  - Gallery markup: `sb-page` (heading from the route title `UI gallery`) > `div.page-actions[page-actions]` (`button[data-action="demo-clear"]`, `danger-quiet`); `sb-segmented[page-scope]` (`Scope (demo)`); `sb-stat-strip.demo-kpis[page-kpis]` (ExpR, Win rate, Open risk, Payoff ratio); `div.reference[page-primary]` (every existing section, plus a *Destructive actions* section and an anchored-hint panel); two `sb-panel[page-secondary]`; the header-action confirm, the killswitch-demo confirm (`dangerVariant="danger"`) and the housekeeping-demo confirm in the default slot. No hard-coded `<h1>`.
  - `workspace-consistency.spec.ts`: `PAGE_ROUTES` (16 paths relative to `src/app/workspaces`), `ROW_COMMANDS` (`Record<string, string>`, one entry: `'app/workspaces/analytics/tabs/tuning.ts'`), helpers `routeEntries(): string[]`, `templateOf(source: string): string`, `tags(template: string): Tag[]`, `actionRanges(list: Tag[]): [number, number][]`, `destructiveOutsideActions(source: string): number`.

**What changes, and what is already there.** Spec Phase 4, §5.1, §5.2 and § Testing. Versions today is a heading-less `sb-section-head` holding the "History not regenerated" notice, then one `sb-async` around the running-now chips, the lane strip, the legend, the release stream and the pager. After this task the route title is its one `h1`, the notice sits at the header's right, and the `sb-async` is the primary element, unchanged; the running-now chips are a filter inside the timeline's own content, not a page scope, and stay where they are.

The gallery today opens with a hard-coded `<h1>UI gallery</h1>` and ~45 panels under level-2 section heads. After this task it is the reference for the page template itself: it renders `sb-page`, so its `h1` is the route title like every page; its header carries one `danger-quiet` action that opens its confirm (the only home for a destructive command); its scope bar is a demo `sb-segmented`; its KPI slot is a demo strip that follows §5.2 (ExpR first, win rate after it, each with `N=` and the basis in its About hint, open risk as money · % of account via `riskUnits`); every existing section is the primary panel, unchanged; two short secondary panels show the two-column grid from 1440px. Two panels are added inside the primary: *Destructive actions* (the solid `danger` button reserved for the killswitch beside `danger-quiet` for housekeeping, each opening its confirm with the matching `dangerVariant`, and a line saying where each may sit) and *sb-hint anchor mode* (an icon link with the rail's anchored label: no trigger button, opened by hover and focus). Nothing is removed: every primitive demo, help line and edge state stays.

`workspace-consistency.spec.ts` today scans each workspace's top-level sources for hand-rolled patterns and bans `<h1` there; that ban stays and its name now says why (sb-page renders the one `h1`). The new `describe` proves the spec's § Testing rule: it reads `app.routes.ts` and every `*.routes.ts` under `workspaces/`, collects the file each `loadComponent` imports, and requires the list to equal `PAGE_ROUTES` (so a new route is a deliberate edit) and every one of them to render `<sb-page`, import and declare `Page`, and fill `page-actions`, `page-scope` and `page-kpis` with at most one element and `page-primary` with exactly one. It requires that no route entry but the gallery renders `sb-section-head` (sb-page's header replaced it everywhere). And it scans every workspace template (nested tabs included, the gallery excluded) for a button whose variant is `danger` or `danger-quiet` and requires each to sit inside the `[page-actions]` element; `danger-icon` is the per-row variant and is not matched, and the one labelled per-row command (Tuning's per-proposal Delete) is listed in `ROW_COMMANDS` with its reason, and the list itself is checked so a stale entry fails. The scanner strips HTML comments, reads the template literal only (TypeScript generics like `signal<string>` would otherwise look like tags), and honours double-quoted attribute values, so `[variant]="a > b ? …"` cannot end a tag early.

- [ ] **Step 1: Write the failing Versions tests**

In `$WT/frontend/src/app/workspaces/versions/versions.spec.ts`, add `import { RouteTitleService } from '../../routing/route-title.service';` below the existing imports and append at the end of the file:

```ts
/* -- v195 Phase 4 -- Versions on sb-page ------------------------------------ */

describe('Versions on sb-page (v195 Phase 4)', () => {
  it('renders the route title as the one h1, from sb-page', async () => {
    const fixture = seed(SIX);
    TestBed.inject(RouteTitleService).set('Versions', "What's deployed, and when it changed");
    fixture.detectChanges();
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Versions');
    expect(el.querySelector('sb-section-head')).toBeNull();
  });

  it('puts the stale-history notice at the header right, and only when stale', async () => {
    const stale = seed({ ...SIX, stale: true });
    stale.detectChanges();
    await stale.whenStable();
    const actions = (stale.nativeElement as HTMLElement).querySelector('sb-page [page-actions]')!;
    expect(actions.textContent).toContain('History not regenerated');
    expect(actions.querySelector('code')!.textContent).toContain('build_version_matrix.py');

    const fresh = seed(SIX);
    fresh.detectChanges();
    await fresh.whenStable();
    expect((fresh.nativeElement as HTMLElement).querySelector('sb-page [page-actions] .stale')).toBeNull();
  });

  it('keeps the timeline and its pager in one primary element, with no scope bar', async () => {
    const fixture = seed(SIX);
    fixture.detectChanges();
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const primary = el.querySelector('sb-page [page-primary]')!;
    expect(primary.tagName.toLowerCase()).toBe('sb-async');
    expect(primary.querySelector('sb-timeline')).not.toBeNull();
    expect(primary.querySelector('sb-pagination')).not.toBeNull();
    expect(el.querySelector('[page-scope]')).toBeNull();
  });
});
```

   `seed`, `SIX` and `TestBed` already exist in this file.

- [ ] **Step 2: Write the failing gallery tests**

In `$WT/frontend/src/app/workspaces/gallery/gallery.spec.ts`, add below the existing imports:

```ts
import { By } from '@angular/platform-browser';
import { RouteTitleService } from '../../routing/route-title.service';
import { PERFORMANCE_CAVEAT, StatTile } from '../../ui/stat-tile';
```

and append at the end of the file:

```ts
/* -- v195 §5.1 -- the gallery is the reference page for sb-page ------------- */

describe('the gallery is the sb-page reference (v195 §5.1, Phase 4)', () => {
  beforeEach(() => {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([]),
        { provide: ConnectionStore, useValue: { marketActive: () => true } }],
    });
    TestBed.inject(RouteTitleService).set('UI gallery', 'Every primitive, in one place');
  });

  function mount() {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders the route title as its one h1, and writes none itself', () => {
    const { el } = mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('UI gallery');
    expect(GALLERY).not.toMatch(/<h1[\s>]/);
  });

  it('fills every slot: actions, scope, KPIs, the primary reference and two secondary panels', () => {
    const { el } = mount();
    for (const slot of ['[page-actions]', '[page-scope]', '[page-kpis]', '[page-primary]']) {
      expect(el.querySelectorAll(`sb-page ${slot}`), slot).toHaveLength(1);
    }
    expect(el.querySelectorAll('sb-page [page-secondary]')).toHaveLength(2);
    expect(el.querySelector('sb-page [page-primary] sb-stat-tile .thin')).not.toBeNull();
  });

  it('demos the header action as danger-quiet, behind its confirm', () => {
    const { fixture, el } = mount();
    const button = el.querySelector<HTMLButtonElement>('sb-page [page-actions] [data-action="demo-clear"]')!;
    expect(button.classList).toContain('danger-quiet');
    expect(button.classList).not.toContain('danger');
    button.click();
    fixture.detectChanges();
    expect(el.querySelector('dialog[open]')!.textContent).toContain('Clear the demo log?');
  });

  it('shows danger for the killswitch alone and danger-quiet for housekeeping, each confirming', () => {
    const { fixture, el } = mount();
    const halt = el.querySelector<HTMLButtonElement>('[data-demo="killswitch"]')!;
    const quiet = el.querySelector<HTMLButtonElement>('[data-demo="housekeeping"]')!;
    expect(halt.classList).toContain('danger');
    expect(halt.classList).not.toContain('danger-quiet');
    expect(quiet.classList).toContain('danger-quiet');
    halt.click();
    fixture.detectChanges();
    const dialog = el.querySelector('dialog[open]')!;
    expect(dialog.textContent).toContain('Halt trading?');
    expect(dialog.querySelector('button.danger')).not.toBeNull();
  });

  it('leads the demo KPI strip with ExpR, with N and the basis, and risk in two units', () => {
    const { fixture } = mount();
    const tiles = fixture.debugElement.queryAll(By.css('[page-kpis] sb-stat-tile'))
      .map((d) => d.componentInstance as StatTile);
    expect(tiles.map((t) => t.label())).toEqual(['ExpR', 'Win rate', 'Open risk', 'Payoff ratio']);
    for (const tile of [tiles[0], tiles[1], tiles[3]]) {
      expect(tile.sample(), tile.label()).not.toBeNull();
      expect(tile.about(), tile.label()).toContain(PERFORMANCE_CAVEAT);
    }
    expect(tiles[2].value()).toMatch(/ · \d+\.\d{2}%$/);
  });

  it('demos the rail label: an anchored hint beside a link, with no trigger button', () => {
    const { el } = mount();
    const link = el.querySelector<HTMLAnchorElement>('a.rail-demo')!;
    expect(link.getAttribute('aria-label')).toBe('Dashboard');
    const hint = link.nextElementSibling!;
    expect(hint.tagName.toLowerCase()).toBe('sb-hint');
    expect(hint.querySelector('button')).toBeNull();
  });
});
```

   `GALLERY`, `Gallery`, `ConnectionStore`, `installDialogPolyfill`, `provideZonelessChangeDetection`, `provideRouter`, `TestBed` and `beforeEach` already exist in this file.

- [ ] **Step 3: Write the failing consistency gate**

In `$WT/frontend/src/app/workspaces/workspace-consistency.spec.ts`:

1. Change `import { join } from 'node:path';` to `import { dirname, join, relative } from 'node:path';`.

2. Rename `it('renders no in-page heading — the top bar owns the title (D4)', ...)` to `it('writes no h1 of its own — sb-page renders the one heading (D4, v195)', ...)`; its body is unchanged.

3. Append at the end of the file:

```ts
/* -- v195 Phase 4, §5.2, § Testing -- every route is an sb-page ------------- */

const APP = join(process.cwd(), 'src/app');

/** Every route entry component, relative to src/app/workspaces. Pinned by
 *  hand so a new route is a deliberate edit here; the first case proves the
 *  list equals what the route files actually load. */
const PAGE_ROUTES = [
  'analytics/analytics.ts',
  'calendar/calendar.ts',
  'calendar/day/calendar-day.ts',
  'cancels/cancels.ts',
  'dashboard/dashboard.ts',
  'gallery/gallery.ts',
  'plans/plan-detail.ts',
  'reports/reports.ts',
  'research/research.ts',
  'risk/risk.ts',
  'system/system.ts',
  'trades/trade-detail.ts',
  'trades/trades.ts',
  'versions/versions.ts',
  'watchlist/ticker-detail.ts',
  'watchlist/watchlist.ts',
] as const;

/** Per-row commands: a destructive button on one row of a list, with its
 *  own confirm, that stays in its row rather than the page header (the
 *  sb-page contract). `danger-icon` (Watchlist's row bin) is the per-row
 *  variant and is never matched; this lists the rows that use a labelled
 *  danger-quiet button instead, each with its reason. */
const ROW_COMMANDS: Record<string, string> = {
  'app/workspaces/analytics/tabs/tuning.ts': "each proposal's own Delete, behind its own confirm",
};

/** The files every `loadComponent` imports, from app.routes.ts and each
 *  *.routes.ts under workspaces/, relative to workspaces/. */
function routeEntries(): string[] {
  const files = [join(APP, 'app.routes.ts')];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.routes.ts')) files.push(full);
    }
  };
  walk(ROOT);
  const out = new Set<string>();
  for (const file of files) {
    const source = readFileSync(file, 'utf8');
    for (const [, target] of source.matchAll(/loadComponent:\s*\(\)\s*=>\s*import\('([^']+)'\)/g)) {
      out.add(relative(ROOT, join(dirname(file), `${target}.ts`)).replace(/\\/g, '/'));
    }
  }
  return [...out].sort();
}

/** The component's inline template (the first `template: \`…\``), with
 *  escapes resolved and HTML comments removed. Only the template is scanned:
 *  TypeScript generics such as `signal<string>` would read as tags. */
function templateOf(source: string): string {
  const open = 'template: `';
  const start = source.indexOf(open);
  if (start < 0) return '';
  let out = '';
  for (let i = start + open.length; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '`') break;
    if (ch === '\\') { out += source[i + 1] ?? ''; i += 1; continue; }
    out += ch;
  }
  return out.replace(/<!--[\s\S]*?-->/g, '');
}

interface Tag { name: string; attrs: string; close: boolean; selfClosing: boolean; index: number }

/** Opening and closing tags in order. Attribute values are double-quoted in
 *  every template here, so a `>` inside one never ends the tag early. */
const TAG = /<\/([a-z][\w-]*)\s*>|<([a-z][\w-]*)((?:\s+[^\s=>/"']+(?:\s*=\s*"[^"]*")?)*)\s*(\/?)>/g;

function tags(template: string): Tag[] {
  return [...template.matchAll(TAG)].map((m) => (m[1]
    ? { name: m[1], attrs: '', close: true, selfClosing: false, index: m.index! }
    : { name: m[2], attrs: m[3], close: false, selfClosing: m[4] === '/', index: m.index! }));
}

const hasAttr = (attrs: string, name: string): boolean =>
  new RegExp(`(?:^|\\s)${name}(?=\\s|=|$)`).test(attrs);

/** Index of the tag that closes list[i], or -1. */
function closingIndex(list: Tag[], i: number): number {
  let depth = 0;
  for (let j = i + 1; j < list.length; j += 1) {
    const tag = list[j];
    if (tag.name !== list[i].name || tag.selfClosing) continue;
    if (!tag.close) { depth += 1; continue; }
    if (depth === 0) return tag.index;
    depth -= 1;
  }
  return -1;
}

/** [open, close) source offsets of every element carrying page-actions. */
function actionRanges(list: Tag[]): [number, number][] {
  return list.flatMap((tag, i): [number, number][] => {
    if (tag.close || tag.selfClosing || !hasAttr(tag.attrs, 'page-actions')) return [];
    return [[tag.index, closingIndex(list, i)]];
  });
}

/** A danger or danger-quiet button, static or bound; never danger-icon. */
const DESTRUCTIVE = /(?:^|\s)variant="danger(?:-quiet)?"|\[variant\]="[^"]*'danger(?:-quiet)?'/;

/** How many destructive buttons in the source sit outside its page-actions. */
function destructiveOutsideActions(source: string): number {
  const list = tags(templateOf(source));
  const ranges = actionRanges(list);
  return list
    .filter((tag) => !tag.close && DESTRUCTIVE.test(tag.attrs))
    .filter((tag) => !ranges.some(([open, close]) => tag.index > open && tag.index < close))
    .length;
}

/** Elements carrying the slot attribute in the source's template. */
const slotCount = (source: string, slot: string): number =>
  tags(templateOf(source)).filter((tag) => !tag.close && hasAttr(tag.attrs, slot)).length;

const routeSource = (path: string): string => readFileSync(join(ROOT, path), 'utf8');

/** Every workspace .ts (nested tabs and panels included), the gallery aside:
 *  it demos every variant on purpose. */
const WORKSPACE_TS = allSources().filter(({ name }) => name.startsWith('app/workspaces/')
  && name.endsWith('.ts') && !name.startsWith('app/workspaces/gallery/'));

describe('every route is an sb-page (v195 Phase 4, § Testing)', () => {
  it('pins the route list to what the route files load', () => {
    expect(routeEntries()).toEqual([...PAGE_ROUTES]);
  });

  it.each(PAGE_ROUTES)('%s renders sb-page and imports Page', (path) => {
    const source = routeSource(path);
    expect(source).toContain('<sb-page');
    expect(source).toMatch(/import \{ Page \} from '(?:\.\.\/)+ui\/page';/);
    expect(source).toMatch(/imports:\s*\[[^\]]*\bPage\b/);
  });

  it.each(PAGE_ROUTES)('%s fills each slot with one element, and has one primary', (path) => {
    const source = routeSource(path);
    for (const slot of ['page-actions', 'page-scope', 'page-kpis']) {
      expect(slotCount(source, slot), slot).toBeLessThanOrEqual(1);
    }
    expect(slotCount(source, 'page-primary')).toBe(1);
  });

  it('leaves sb-section-head to the gallery: sb-page heads every page', () => {
    const offenders = PAGE_ROUTES
      .filter((path) => path !== 'gallery/gallery.ts')
      .filter((path) => /<sb-section-head[\s>]/.test(routeSource(path)));
    expect(offenders).toEqual([]);
  });
});

describe('destructive actions live in the header (v195 Phase 4, §5.2)', () => {
  it('keeps every danger and danger-quiet button inside [page-actions], per-row commands aside', () => {
    const offenders = WORKSPACE_TS
      .filter(({ name }) => !(name in ROW_COMMANDS))
      .map(({ name, source }) => ({ name, count: destructiveOutsideActions(source) }))
      .filter(({ count }) => count > 0)
      .map(({ name, count }) => `${name} (${count})`);
    expect(offenders).toEqual([]);
  });

  it('lists only per-row commands that still exist', () => {
    for (const name of Object.keys(ROW_COMMANDS)) {
      const file = WORKSPACE_TS.find((s) => s.name === name);
      expect(file, name).toBeDefined();
      expect(destructiveOutsideActions(file!.source), name).toBeGreaterThan(0);
    }
  });

  it('reads a button inside the header actions as placed, and one outside as not', () => {
    const inside = 'template: `<div page-actions class="a"><div><button sb-button variant="danger-quiet">x</button></div></div>`';
    const outside = 'template: `<div page-actions></div><button sb-button [variant]="n > 0 ? \'danger\' : \'ghost\'">x</button>`';
    const rowBin = 'template: `<button sb-button variant="danger-icon">x</button>`';
    expect(destructiveOutsideActions(inside)).toBe(0);
    expect(destructiveOutsideActions(outside)).toBe(1);
    expect(destructiveOutsideActions(rowBin)).toBe(0);
  });
});
```

   `ROOT`, `allSources`, `readdirSync`, `readFileSync` and `join` already exist in this file. The last case pins the scanner itself: the `>` inside the bound `[variant]` value must not end the tag, and `danger-icon` is never matched.

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: FAIL. Versions and the gallery render no `sb-page`, so no slots; the gallery still writes `<h1>`; the gate's `renders sb-page` and `one primary` cases fail for `versions/versions.ts` and `gallery/gallery.ts` only, and `leaves sb-section-head to the gallery` names `versions/versions.ts`. Every other route entry passes: if one fails, the earlier task that moved it left a different shape (read its "Produces" block), and the fix goes in that file only if it breaks the sb-page contract (two primary elements, a destructive button outside the header); a shape the contract allows (Trades without KPIs, plan detail without actions, Reports' `sb-freshness` as its actions element) must pass as written. If `pins the route list` fails with an extra or missing path, a route was added or renamed since this plan: add it to `PAGE_ROUTES` only if it is a real route entry, and give it `sb-page` in this task.

- [ ] **Step 5: Move Versions onto `sb-page`**

In `$WT/frontend/src/app/workspaces/versions/versions.ts`:

1. Imports: delete `import { SectionHead } from '../../ui/section-head';`, add `import { Page } from '../../ui/page';`; in the component's `imports` array replace `SectionHead` with `Page`.

2. Template: replace the `<sb-section-head> … </sb-section-head>` element with the header-actions element below, wrap it and the `<sb-async …> … </sb-async>` element in `<sb-page> … </sb-page>`, and add `page-primary` to the `sb-async`'s opening tag (`<sb-async page-primary [loading]="async().loading" …`):

```html
    <!-- v195 Phase 4: the route title is the page's one h1. -->
    <sb-page>
      <div page-actions class="head-status">
        @if (store.stale()) {
          <!-- The frozen file is behind VERSION.json. Saying so is the whole
               point: a timeline silently missing the newest release looks
               complete, which is the one way this page could mislead. -->
          <span class="stale" role="status">
            History not regenerated — run <code>scripts/dev/build_version_matrix.py</code>
          </span>
        }
      </div>

      <!-- the <sb-async page-primary …> … </sb-async> element, otherwise unchanged -->
    </sb-page>
```

   (the second comment line above marks where the existing `sb-async` goes; do not keep it as text).

3. Styles: replace the first `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }` rule with `:host { display: block; min-width: 0; }` and replace its two comments (about `minmax(0, 1fr)` and the v54 gap) with `/* v195 Phase 4: sb-page owns the page rhythm. No backticks in here: these styles live in a TS template literal. */`. The `:host { --lane-w: 4.5rem; }` rule and its media query stay. Add `.head-status { display: flex; align-items: center; }`.

- [ ] **Step 6: Re-lay the gallery out on `sb-page`**

In `$WT/frontend/src/app/workspaces/gallery/gallery.ts`:

1. Imports: add

```ts
import { Page } from '../../ui/page';
import { riskUnits } from '../../ui/risk-units';
```

   change the stat-tile import to `import { PERFORMANCE_CAVEAT, StatTile } from '../../ui/stat-tile';`, and add `Page` to the component's `imports` array (alphabetical, after `PaginationComponent`). `ConfirmDialog`, `Hint`, `Icon`, `Segmented`, `SegmentOption`, `StatStrip` and `StatTile` are already imported.

2. Template: delete the `<h1>UI gallery</h1>` line. Wrap everything that remains as below (`<!-- MOVE: … -->` lines are instructions, not template text):

```html
    <!-- v195 §5.1: the gallery is the reference for the page template too.
         Every slot holds a demo of what belongs there; the route title is
         the h1, as on every page. -->
    <sb-page>
      <!-- The header's actions: the only home for a destructive command,
           always behind its confirm (spec Phase 4). -->
      <div page-actions class="page-actions">
        <button sb-button variant="danger-quiet" type="button" data-action="demo-clear"
                (click)="headerConfirmOpen.set(true)">Clear demo log</button>
      </div>

      <!-- The scope bar: filters and tabs only, never a destructive action. -->
      <sb-segmented page-scope label="Scope (demo)" [options]="scopeOptions" [(value)]="scopeValue" />

      <!-- The KPI strip (spec §5.2): ExpR first, win rate after it, N and the
           basis on every performance figure, risk as money · % of account. -->
      <sb-stat-strip page-kpis class="demo-kpis">
        <sb-stat-tile label="ExpR" value="+0.21R" [sample]="412" [about]="perfAbout" />
        <sb-stat-tile label="Win rate" value="54.2%" [sample]="412" [about]="perfAbout" />
        <sb-stat-tile label="Open risk" [value]="openRisk" secondary="cap 6.00%" />
        <sb-stat-tile label="Payoff ratio" value="1.80" [sample]="7" [about]="perfAbout" />
      </sb-stat-strip>

      <!-- The primary panel: every primitive, section by section. -->
      <div page-primary class="reference">
        <!-- MOVE: everything that was in the template after the deleted <h1> line, unchanged, with the two
             additions in items 3 and 4 below -->
      </div>

      <!-- The secondary grid: one column, two from 1440px. -->
      <sb-panel page-secondary heading="Secondary panel">
        <p class="sb-help">Supporting panels sit here, after the primary one: one column below 1440px, two from it.</p>
      </sb-panel>
      <sb-panel page-secondary heading="Secondary panel, second column">
        <p class="sb-help">An empty slot takes no space, so a page without secondary panels shows no gap.</p>
      </sb-panel>

      <sb-confirm-dialog
        [open]="headerConfirmOpen()"
        title="Clear the demo log?"
        consequence="Nothing is cleared: this is the gallery's demo of a header action."
        confirmLabel="Clear"
        (confirmed)="headerConfirmOpen.set(false)"
        (cancelled)="headerConfirmOpen.set(false)"
      />
      <sb-confirm-dialog
        [open]="haltConfirmOpen()"
        title="Halt trading?"
        consequence="Demo only. On Risk this stops every new plan until it is re-armed."
        confirmLabel="Halt"
        dangerVariant="danger"
        (confirmed)="haltConfirmOpen.set(false)"
        (cancelled)="haltConfirmOpen.set(false)"
      />
      <sb-confirm-dialog
        [open]="quietConfirmOpen()"
        title="Delete this demo row?"
        consequence="Demo only. Housekeeping confirms in the quiet style."
        confirmLabel="Delete"
        (confirmed)="quietConfirmOpen.set(false)"
        (cancelled)="quietConfirmOpen.set(false)"
      />
    </sb-page>
```

   If V195-21 already wrapped the gallery in a minimal `sb-page`, replace that wrapper with this one.

3. Inside the moved content, directly after the `-- buttons --` section's `</sb-panel>`, add:

```html
        <!-- -- destructive actions (v195 Phase 2, Phase 4) -------------------- -->
        <sb-section-head [heading]="'Destructive actions'" [level]="2" />
        <sb-panel heading="danger is the killswitch alone; danger-quiet is housekeeping">
          <sb-control-row>
            <button sb-button variant="danger" type="button" data-demo="killswitch"
                    (click)="haltConfirmOpen.set(true)">Halt trading</button>
            <button sb-button variant="danger-quiet" type="button" data-demo="housekeeping"
                    (click)="quietConfirmOpen.set(true)">Delete demo row</button>
          </sb-control-row>
          <p class="sb-help">
            Both always open a confirm, with the matching style on its confirm button,
            and live only in a page's header actions. A per-row command (the
            <code>danger-icon</code> bin, or a row's own Delete) stays in its row with its own confirm.
          </p>
        </sb-panel>
```

4. Inside the moved content, directly after the `sb-hint -- hover, focus or tap; …` panel's `</sb-panel>`, add:

```html
        <sb-panel heading="sb-hint anchor mode -- the rail's label: hover or focus the icon">
          <a #railDemo class="rail-demo sb-hit" href="#gallery-rail-demo" id="gallery-rail-demo" aria-label="Dashboard">
            <sb-icon name="dashboard" />
          </a>
          <sb-hint [anchor]="railDemo" text="Dashboard" />
          <p class="sb-help">
            No trigger button and no extra tab stop: the label opens on the link's
            hover and keyboard focus and closes on Escape, the way every rail entry names itself.
          </p>
        </sb-panel>
```

5. Class: add after `confirmOpen` (keep the existing members):

```ts
  /** v195 §5.1: the sb-page demos -- the header action, the scope bar and
   *  the KPI strip, built from the same rules the workspaces follow. */
  protected readonly headerConfirmOpen = signal(false);
  protected readonly haltConfirmOpen = signal(false);
  protected readonly quietConfirmOpen = signal(false);
  protected readonly scopeOptions: SegmentOption[] = [
    { value: 'all', label: 'All' },
    { value: 'long', label: 'Long' },
    { value: 'short', label: 'Short' },
  ];
  protected readonly scopeValue = signal('all');
  protected readonly perfAbout = `Demo figures. ${PERFORMANCE_CAVEAT}`;
  protected readonly openRisk = riskUnits(1.42, 100_000, '$');
```

   (`segmentValue` shows the shape `[(value)]` binds to; if it is a `model`/`signal` of another type, match it).

6. Styles: add

```css
    .page-actions { display: flex; flex-wrap: wrap; gap: var(--space-8); }
    .reference { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); min-width: 0; }
    .rail-demo { display: inline-flex; align-items: center; justify-content: center; color: var(--text-secondary); }
    .rail-demo:hover, .rail-demo:focus-visible { color: var(--text); }
```

   and change the `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); padding: var(--space-20); }` rule to `:host { display: block; min-width: 0; padding: var(--space-20); }` (the `.reference` rule now lays the sections out; the page keeps its padding).

7. In the class doc comment (`` `/ui` -- every shared primitive, every variant, side by side. ``), append:

```ts
 *
 * Since v195 it is also the reference for the page template: it renders
 * sb-page with a demo in every slot, and shows the two danger variants and
 * the rail's anchored label beside the rest.
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/versions/versions.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/button.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `gallery.spec.ts`'s `renders sb-page` (generated from `ui/page.ts`'s selector) is green. `button.spec.ts`'s `variant="danger"` allow-list (Risk and the gallery) still holds: the new solid button is in the gallery. `primitives.spec.ts`'s raw-control gate finds no raw `<button>` (every new one is `sb-button`) and no raw `<input>`. If the gate's destructive case names a file, print its template's offending tag (`tags(templateOf(source)).filter(...)`) and check whether that button is a per-row command with its own confirm (then it belongs in `ROW_COMMANDS` with its reason) or a page command left outside the header (then the task that moved that page left a defect: report it, do not move it here). If `pins the route list` lists `gallery/gallery.ts` twice or misses it, check `app.routes.ts`'s `loadComponent` for the gallery still reads `import('./workspaces/gallery/gallery')`.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. Lint flags a leftover `SectionHead` import in `versions.ts`.

- [ ] **Step 8: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, click to Versions (rail, System group), then open `/app/ui` by URL (it is not on the rail). At 1440, 768 and 390: Versions has one `h1` `Versions`, the lanes and the stream below it, no horizontal page scroll (the strip scrolls in its own box). The gallery has one `h1` `UI gallery`; the header's `Clear demo log` is bordered red text on no fill, and opens its confirm (press **Cancel**); the demo scope bar and KPI strip sit under it (ExpR first, `N=412`, Open risk `1,420 $ · 1.42%`); *Destructive actions* shows the solid `Halt trading` beside the bordered `Delete demo row`, and `Halt trading`'s confirm button is solid; Tab onto the *sb-hint anchor mode* icon and its `Dashboard` label shows with no extra tab stop; at 1440 the two secondary panels sit side by side, below it they stack. Save the PNGs under the session scratchpad.

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/workspaces/workspace-consistency.spec.ts`), plus `frontend/src/app/workspaces/versions/versions.spec.ts` and `frontend/src/app/workspaces/gallery/gallery.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/versions/versions.ts frontend/src/app/workspaces/versions/versions.spec.ts frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts frontend/src/app/workspaces/workspace-consistency.spec.ts
git -C "$WT" commit -m "feat(v195): Versions and the gallery on sb-page; every route proven an sb-page (V195-33)" -m "Spec Phase 4, §5.1, §5.2 and § Testing. Versions: the stale notice in the header, the timeline primary. Gallery: the reference for the page template (a danger-quiet header action behind its confirm, a demo scope bar, a §5.2 KPI strip, the reference sections primary, two secondary panels), plus the danger/danger-quiet pair and the rail's anchored label. workspace-consistency: the route list is derived from the route files and pinned; every entry renders sb-page with one primary; only the gallery keeps sb-section-head; every danger and danger-quiet button sits in [page-actions], per-row commands listed with their reason." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

