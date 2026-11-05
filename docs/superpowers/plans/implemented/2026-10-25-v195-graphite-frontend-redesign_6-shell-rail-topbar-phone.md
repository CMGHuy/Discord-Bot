# v195 — Graphite, Part 6: the icon rail and the 40px top bar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-16:" -A 400 <this file>`.

**Scope of this part (V195-16; V195-17 is in Part 6b, `2026-10-25-v195-graphite-frontend-redesign_6b-topbar-cluster-and-phone.md`, and V195-18 in Part 6c, `2026-10-25-v195-graphite-frontend-redesign_6c-phone-shell.md`, split for the 1500-line cap):** the shell is rebuilt on the building blocks of Parts 5 and 5b, in three sequential tasks that all rewrite `shell.html`, `shell.css`, `shell.ts` and `shell.spec.ts`. V195-16 replaces the expandable sidebar with the always-collapsed 48px icon rail in four groups (labels through `Hint.anchor`), shrinks the top bar to 40px with the breadcrumb in the lead, removes the shell's `<h1>` (correction 9) and stops reading `shell.sidebar`. V195-17 then fills the top bar's right cluster (killswitch and freshness chips, scan progress, clock, the profile menu with Density) and moves the tape to a strip under the bar; V195-18 gives phones the bottom tab bar and the More sheet. The command palette itself is Part 7 (V195-19, V195-20).

**Where commands run.** Shell state does not persist between Bash calls and `cd` breaks the guardrail hooks, so every command below spells out the worktree path:

- `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`
- `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`

Frontend runs through `npm --prefix "$WT/frontend" ...`. Edit files only under `$WT/`; never the main tree's copies.

**The state earlier tasks leave (read before editing).** After V195-15, in `$WT`:

- `frontend/src/app/shell/shell.html`, `shell.css`, `shell.ts`: as on `main`, except V195-4 deleted the `.ambient` layer (comment and `div`), the `.shell` rule's `isolation` declaration and its comment, the `.ambient` rule, the `sbRouteEntrance` attribute on `div.workspace-content`, and the `RouteEntrance` import and `imports` entry. `shell.ts` still has its own `NavEntry`/`NavGroup` interfaces, the three-group `navGroups` literal, `userCollapsed`, `railed`, `overlay`, `overlayOpen`, `toggleSidebar`, `openOverlay`, `closeOverlay` and `applyStoredSidebar`.
- `frontend/src/app/shell/shell.spec.ts`: V195-4 added `existsSync` to the `node:fs` import, replaced the ambient-glow case with `paints no ambient layer and routes into a plain host (v195 §1.2)` and `no longer ships the route-entrance directive (v195 §1.2)`, and renamed `describe('ambient live cues (v168 §3 #10)', ...)` to `describe('live cues (v168 §3 #10)', ...)` with its first case replaced by `declares no ambient layer and no stacking context for one`. Every other case is as on `main`.
- `frontend/src/app/shell/nav.ts` (V195-15): `NavEntry`, `NavGroup`, `NAV_GROUPS` (`nav-monitor` "Monitor", `nav-review` "Review", `nav-insights` "Insights", `nav-system` "System"), `PHONE_TABS`, `navEntryFor`, `breadcrumbFor`, `detailCrumb`. `frontend/src/app/shell/breadcrumb.ts` (V195-15): `Crumb`, `crumbsFor`, `Breadcrumb` (`sb-breadcrumb`, reads the router and `RouteTitleService` itself, takes no input; below 640px it shows only the current crumb).
- `frontend/src/app/ui/hint.ts` (V195-14): `Hint.anchor = input<HTMLElement | null>(null)`; in anchor mode no trigger button renders, the host carries class `anchored` (`display: contents`), the popover (`[role=tooltip]`, class `pop label`) opens on the anchor's `mouseenter`/`focus` and closes on `mouseleave`/`blur`/Escape, and the anchor's `aria-describedby` is the popover's id. `frontend/src/app/testing/popover-polyfill.ts` exports `POPOVER_OPEN_ATTR` (the attribute an open popover carries under jsdom). `frontend/src/app/ui/icon.ts`: `'search'` is in `ICON_NAMES` (magnifier); `research` is a flask.
- `frontend/src/app/ui/density.service.ts` (V195-6): `RowDensity`, `DENSITY_PREF_KEY = 'ui.density'`, `DensityStorage`, `DENSITY_STORAGE`, `readDensity`, `DensityService` (root; `density: Signal<RowDensity>`, `set(d)`, writes `<html data-density>` at construction and on every `set`).
- `frontend/src/styles/tokens.css` (V195-2..V195-6): tier-2 names unchanged (`--surface`, `--surface-raised`, `--border`, `--border-strong`, `--text`, `--text-secondary`, `--text-muted`, `--text-faint`, `--accent`, `--accent-soft`, `--pos`, `--neg`, `--neg-soft`); `--control-h` 28px at rest and 44px in the touch block `@media (pointer: coarse), (max-width: 1023px)`; `--hit-min` 24px / 44px; `--transition` is 120ms; `--chip-radius` and `--control-radius` 4px; `--text-micro`/`--text-chip` 12px.
- `frontend/src/styles/motion.css` (V195-5): still carries `[data-motion=off] sb-shell .shell, [data-motion=off] sb-shell .shell.overlay .sidebar { transition: none !important; }` and the route-spinner guard; `motion-css.spec.ts` pins both lines verbatim. This part leaves them (see V195-16, "What is left alone").
- `frontend/src/app/shell/profile-menu.ts`, `nav-indicator.ts`, `route-focus.ts`, `connection-status.ts`, `scan-progress.ts`, `tape/tape.ts` and their specs, `frontend/src/app/stores/connection.store.ts` and its spec, `frontend/src/app/ui/hit-area.spec.ts` (V195-6 touched only its token cases): as on `main` plus v194 (v194 left `profile-menu.ts`'s `[attr.title]="haloTitle()"` and `connection-status.ts`'s `[title]="hint()"` in `title-usage.allow.ts` as control names).

v194 and V195-4..V195-15 edited several of these files: every step below names its edit by symbol or by the exact string, never by line number. Re-read each file before editing it.

**`title` in new templates.** v194's `title-usage.spec.ts` scans every non-spec `.ts` file under `src/app` for `title="…"`, `[title]` and `[attr.title]` and fails on any binding not in `title-usage.allow.ts`. The new components of Phase 3 (`killswitch-chip.ts`, `freshness-chip.ts`, `phone-tab-bar.ts`, `more-sheet.ts`, Parts 6b and 6c) therefore carry no `title` binding at all, not even `title=""` on an `sb-icon`; an icon inside a link is wrapped in an `aria-hidden` span instead, so its default host `title` never reaches the link's accessible name. `shell.html` is a separate template file the scanner does not read; the rail suppresses the icon's native tooltip there with `title=""` so it never competes with the label hint.

---

# Phase 3 — Shell (rebuilt)

### Task V195-16: Icon rail: 48px always-collapsed rail in four groups, dividers without text, `Hint.anchor` labels, active bar; 40px top bar with the breadcrumb; shell `<h1>` removed; expand/collapse, overlay, hamburger and `shell.sidebar` read/write deleted
**Model:** sonnet — a template and stylesheet rewrite of the shell plus deletions in its class; the care is in retiring exactly the named spec cases (moved, never silently dropped) and keeping the hit-area, nav-indicator and route-focus pins green.

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (whole file replaced)
- Modify: `frontend/src/app/shell/shell.css` (whole file replaced)
- Modify: `frontend/src/app/shell/shell.ts` (imports; the `NavEntry`/`NavGroup` interfaces deleted; class docblock; `imports` array; `viewport` and `titles` fields deleted; `navGroups` from `NAV_GROUPS`; new `versionText`; `userCollapsed`, `railed`, `overlay`, `overlayOpen`, `toggleSidebar`, `openOverlay`, `closeOverlay`, `applyStoredSidebar` deleted)
- Modify: `frontend/src/app/shell/shell.spec.ts` (imports; two helpers; named cases updated or retired; two new describes)
- Modify: `frontend/src/app/shell/nav-indicator.ts` (docblocks only: the container is the rail)
- Modify: `frontend/src/app/shell/nav-indicator.spec.ts` (host markup and selectors: `nav.rail` with a divider between the lists)
- Modify: `frontend/src/app/shell/route-focus.spec.ts` (one new case)
- Modify: `frontend/src/app/ui/hit-area.spec.ts` (the shell's three entries repointed at the rail; not in the ledger row, see "What changes")

**Interfaces:**
- Consumes: `NAV_GROUPS` (`shell/nav.ts`, V195-15); `Breadcrumb` (`sb-breadcrumb`, `shell/breadcrumb.ts`, V195-15, no inputs); `Hint` with its `anchor`, `text`, `label`, `glyph`, `align` inputs (`ui/hint.ts`, V195-14); `POPOVER_OPEN_ATTR` (`testing/popover-polyfill.ts`, v194); `NavIndicator`, `indicatorBox`; `focusWorkspaceHeading`; `ConnectionStore.versions`, `ConnectionStore.lastUpdated`.
- Produces (V195-17, V195-18, V195-20 and V195-35 rely on these):
  - Rail markup: `nav.rail[aria-label="Primary"]` > `sb-nav-indicator`, `div.mark` > `a.brand.sb-hit` + `sb-hint` (anchor), then per group (a `div.rail-divider[aria-hidden=true]` before every group but the first) `ul.nav[aria-label=<group label>]` > `li` > `a.rail-link.sb-hit[aria-label=<entry label>]` (icon only, `routerLinkActive="active"`) + sibling `sb-hint` in anchor mode whose `text` is the entry label; `div.rail-foot` > `sb-hint.version` (glyph `v`). V195-35's `rail-label` check reads `nav.rail a.rail-link`.
  - Top bar markup: `header.topbar` > `sb-breadcrumb.topbar-lead`, `div.topbar-tape` > `sb-tape`, `div.status-cluster` (`sb-connection-status`, `span.clock`), `sb-profile-menu`. No `<h1>` anywhere in the shell.
  - CSS: `.shell { --rail-w: 48px; --topbar-h: 40px; grid-template-columns: var(--rail-w) 1fr; }`; `--topbar-h` is 48px in the touch block; `.topbar` is sticky (`top: 0`, `z-index: 15`, `background: var(--bg)`).
  - `Shell.versionText` (protected computed string: `ui <ui> · bot <bot>`, plus ` · updated <last_updated>` when known; `''` before the first answer).
  - Deleted: `railed`, `overlay`, `overlayOpen`, `toggleSidebar`, `openOverlay`, `closeOverlay`, `userCollapsed`, `applyStoredSidebar`, the shell's own `NavEntry`/`NavGroup`/three-group literal, and the `viewport` and `titles` fields (V195-18 re-injects `ViewportService` for the phone bar).

**What changes, and what is already there.** Today the sidebar is 200px with three labelled groups, collapses to a 52px rail (by width below 1024px, or by a toggle stored server-side as `shell.sidebar`), and becomes a slide-over sheet with a hamburger and a scrim below 640px; the top bar is 68px and owns the page's `<h1>` and subtitle. Phase 3 replaces all of that with one state: a 48px rail that never expands, four groups from `NAV_GROUPS` split by thin rules with no text, each entry an icon whose name is its `aria-label` and whose visible label is an anchored `sb-hint` opened by hover and keyboard focus (correction 10: no button in the link, no extra tab stop). The active entry keeps `sb-nav-indicator`'s 2px accent bar, now on the rail's left edge, plus a tint and a brighter glyph. The top bar drops to 40px (48px under the touch rules, where its controls are 44px) and leads with `sb-breadcrumb`; the title and subtitle leave it, and the shell renders no `<h1>` at all, so `route-focus.ts`'s `.workspace h1` finds the one `sb-page` renders from V195-21 on (correction 9). Until the workspaces move onto `sb-page` (V195-22..V195-33) a page has no `<h1>` and route focus finds nothing, as on most routes today; the branch is merged only at V195-36. The version block becomes a `v` hint at the rail's foot, because a 48px rail cannot hold `ui 1.36.1`; its words are unchanged. The phone keeps this rail for now (48px beside the page); V195-18 swaps it for the bottom tab bar.

`hit-area.spec.ts` pins three shell strings (`.nav a` grows to `--control-h`; the brand link and the nav link carry `.sb-hit`), so it moves with the markup in this task's commit. The ledger row omits it; no other Phase 3 task touches it.

**What is left alone.** `shell.sidebar` stays in the server's preferences (the spec's Rollback: an older image reads it again); nothing writes or reads it here, and V195-36 lists it as orphaned. `motion.css` keeps `[data-motion=off] sb-shell .shell, [data-motion=off] sb-shell .shell.overlay .sidebar { transition: none !important; }`: `motion-css.spec.ts` pins the line verbatim and V195-5 owns that file; after this task `.shell` declares no transition, so the guard has nothing to stop. `route-focus.ts` does not change. The killswitch strip, the scan-progress overlay, the tape and the profile menu stay where they are until V195-17.

- [ ] **Step 1: Write the failing shell tests**

In `$WT/frontend/src/app/shell/shell.spec.ts`:

1. Imports. In the `@angular/core` import add `Component`; replace `import { provideRouter } from '@angular/router';` with `import { Router, Routes, provideRouter } from '@angular/router';`; delete `import { RouteTitleService } from '../routing/route-title.service';` (its two cases retire below); after `import { provideMotion } from '../ui/motion/motion.service';` add:

```ts
import { POPOVER_OPEN_ATTR } from '../testing/popover-polyfill';
import { NAV_GROUPS } from './nav';
```

2. Directly after the closing brace of `class FakeEventStream`, add:

```ts

@Component({ template: '' })
class Blank {}

/** The providers every v195 shell describe uses: the same fakes as the
 *  `shell navigation` block, with a route table the breadcrumb can read. */
function shellProviders(routes: Routes = []) {
  return [
    provideZonelessChangeDetection(),
    provideRouter(routes),
    provideHttpClient(),
    provideHttpClientTesting(),
    { provide: EventStream, useValue: new FakeEventStream() },
    { provide: TapeStore, useValue: { load: vi.fn(), visible: signal(false), rows: signal([]), asOf: signal(null) } },
  ];
}

const readSource = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
```

3. Inside `describe('shell navigation', ...)`:

   - Delete the case `it('groups the eleven workspaces into three named groups', ...)` (replaced by the rail describe below).
   - Replace the case `it('keeps each group a real list so the grouping reaches assistive tech', ...)` with:

```ts
  it('keeps each of the four groups a real, named list for assistive tech', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const groups = (f.nativeElement as HTMLElement).querySelectorAll('nav.rail ul.nav[aria-label]');
    expect(groups.length).toBe(4);
  });
```

   - Delete the cases `it('renders the route title and subtitle in the top bar', ...)` and `it('renders no subtitle element at all when the route has none', ...)` (the top bar shows the breadcrumb; the title moves to `sb-page`, V195-21).
   - Replace the case `it('marks the active entry with a rail plus tint and weight, not colour alone', ...)` with:

```ts
  it('marks the active entry with the bar, a tint and a brighter glyph, not colour alone', () => {
    // v168 §3 #6 kept: one sliding sb-nav-indicator in the rail. On an
    // icon-only rail weight means nothing, so the third cue is the glyph's
    // colour stepping from muted to full text.
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelectorAll('nav.rail > sb-nav-indicator').length).toBe(1);
    const css = readSource('src/app/shell/shell.css');
    const active = css.match(/^\.rail-link\.active \{[^}]*\}/m)?.[0] ?? '';
    expect(active).toContain('background: var(--accent-soft);');
    expect(active).toContain('color: var(--text);');
    expect(css.match(/^\.rail-link \{[^}]*\}/m)?.[0]).toContain('color: var(--text-muted);');
    expect(css).not.toMatch(/border-left-color/);
  });
```

   - Replace the case `it('keeps the version block pinned to the foot of the rail', ...)` with:

```ts
  it('keeps the ui and bot versions in a hint at the foot of the rail', async () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    await f.whenStable();
    const el = f.nativeElement as HTMLElement;
    // Nothing until the first /health answer: a version that reads 0.0.0
    // while it waits looks real.
    expect(el.querySelector('sb-hint.version')).toBeNull();
    const backend = TestBed.inject(HttpTestingController);
    for (const request of backend.match((r) => r.url.endsWith('/health'))) {
      request.flush({
        ok: true,
        versions: { ui: '1.36.1', bot: '2.15.3', last_updated: '2026-10-25T06:00:00Z' },
        market_active: true,
        currency: '€',
      });
    }
    f.detectChanges();
    await f.whenStable();
    const foot = el.querySelector('nav.rail > .rail-foot')!;
    const hint = foot.querySelector('sb-hint.version')!;
    expect(hint.querySelector('[role=tooltip]')!.textContent!.trim())
      .toBe('ui 1.36.1 · bot 2.15.3 · updated 2026-10-25T06:00:00Z');
    expect(el.querySelector('.version-row')).toBeNull();
  });
```

   - Replace the case `it('drops the subtitle and the clock before it lets the bar overflow', ...)` with:

```ts
  it('drops the clock and the tape on a phone before it lets the bar overflow', () => {
    const css = readSource('src/app/shell/shell.css');
    // v95 A2's declared breakpoint. The subtitle it used to drop at 1023px
    // has left the bar (v195: the breadcrumb leads, sb-page carries the title).
    expect(css).toMatch(/max-width:\s*639px[\s\S]*\.clock[\s\S]*display:\s*none/);
    expect(css).toMatch(/max-width:\s*639px[\s\S]*\.topbar-tape[\s\S]*display:\s*none/);
    expect(css).not.toContain('.page-subtitle');
  });
```

   - Replace the case `it('renders the brand mark beside the wordmark', ...)` with:

```ts
  it('renders the brand as the mark alone, named for assistive tech and labelled on focus', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    const brand = el.querySelector('nav.rail .mark a.brand') as HTMLAnchorElement;
    expect(brand.querySelector('sb-icon')).not.toBeNull();
    expect(brand.textContent!.trim()).toBe('');
    expect(brand.getAttribute('aria-label')).toContain('Bomeo Capital');
    expect(brand.nextElementSibling!.tagName.toLowerCase()).toBe('sb-hint');
  });
```

   - Keep `it('the brand mark links back to the Dashboard', ...)` as it is.
   - Delete the cases `it('renders the two-tone wordmark as two spans, not one coloured string', ...)`, `it('renders the rail tagline', ...)` and `it('keeps the mark and drops the words when the rail is collapsed', ...)` (the wordmark, the tagline and the collapsed state retire with the expandable sidebar).

4. Delete the whole `describe('shell wordmark on a phone', ...)` block (the phone overlay is retired; V195-18 owns the phone shell).

5. In `describe('shell topbar centred on one axis (v179 layout audit)', ...)`, replace the case `it('gives the topbar and the sidebar wordmark row the same height, so the two centres meet', ...)` with:

```ts
  it('gives the topbar and the rail mark the same height, so the two centres meet', () => {
    expect(rule('.topbar')).toContain('height: var(--topbar-h)');
    expect(rule('.mark')).toContain('height: var(--topbar-h)');
    expect(rule('.topbar')).toContain('position: sticky;');
  });
```

6. At the end of the file, append:

```ts

describe('shell icon rail (v195 Phase 3, correction 10)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
  });

  async function mount() {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('is one rail of four unlabelled groups split by thin rules', async () => {
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    expect(rail.getAttribute('aria-label')).toBe('Primary');
    expect([...rail.querySelectorAll('ul.nav')].map((ul) => ul.getAttribute('aria-label')))
      .toEqual(['Monitor', 'Review', 'Insights', 'System']);
    const dividers = [...rail.querySelectorAll('.rail-divider')];
    expect(dividers).toHaveLength(3);
    for (const divider of dividers) {
      expect(divider.getAttribute('aria-hidden')).toBe('true');
      expect(divider.textContent!.trim()).toBe('');
      // Between groups, never before the first or after the last.
      expect(divider.previousElementSibling!.matches('ul.nav')).toBe(true);
      expect(divider.nextElementSibling!.matches('ul.nav')).toBe(true);
    }
    expect(el.querySelector('.nav-group-label')).toBeNull();
  });

  it('names every entry and labels it with an anchored hint, never a title', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map((a) => a.getAttribute('aria-label')))
      .toEqual(NAV_GROUPS.flatMap((group) => group.entries.map((entry) => entry.label)));
    for (const link of links) {
      const name = link.getAttribute('aria-label')!;
      expect(link.hasAttribute('title'), name).toBe(false);
      expect(link.querySelector('sb-icon')!.getAttribute('title'), name).toBe('');
      expect(link.textContent!.trim(), name).toBe('');
      const hint = link.nextElementSibling as HTMLElement;
      expect(hint.tagName.toLowerCase(), name).toBe('sb-hint');
      expect(hint.classList, name).toContain('anchored');
      const pop = hint.querySelector('[role=tooltip]')!;
      expect(pop.textContent!.trim(), name).toBe(name);
      expect(link.getAttribute('aria-describedby'), name).toBe(pop.id);
    }
  });

  it('shows an entry label on keyboard focus without adding a tab stop', async () => {
    const { fixture, el } = await mount();
    const trades = el.querySelector<HTMLAnchorElement>('a.rail-link[aria-label="Trades"]')!;
    const pop = trades.nextElementSibling!.querySelector('[role=tooltip]')!;
    expect(pop.hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    trades.dispatchEvent(new FocusEvent('focus'));
    fixture.detectChanges();
    await fixture.whenStable();
    expect(pop.hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    expect(el.querySelectorAll('nav.rail ul.nav button')).toHaveLength(0);
  });

  it('marks the routed entry active', async () => {
    const { fixture, el } = await mount();
    await TestBed.inject(Router).navigateByUrl('/trades');
    fixture.detectChanges();
    await fixture.whenStable();
    expect([...el.querySelectorAll('a.rail-link.active')].map((a) => a.getAttribute('aria-label')))
      .toEqual(['Trades']);
  });

  it('has no expanded, collapsed or overlay state, and ignores a stored shell.sidebar', async () => {
    const { fixture, el } = await mount();
    const backend = TestBed.inject(HttpTestingController);
    for (const request of backend.match((r) => r.url.endsWith('/system/preferences'))) {
      request.flush({ preferences: { 'shell.sidebar': 'expanded' } });
    }
    fixture.detectChanges();
    await fixture.whenStable();
    expect(el.querySelector('.shell')!.className).toBe('shell');
    for (const gone of ['.collapse', '.menu-button', '.scrim', '.sidebar', '.rail-tagline', '.brand .word']) {
      expect(el.querySelector(gone), gone).toBeNull();
    }
    // Read nowhere and written nowhere: no preference write left the page.
    expect(backend.match((r) => r.method !== 'GET')).toEqual([]);
    const code = readSource('src/app/shell/shell.ts').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    for (const word of ['shell.sidebar', 'toggleSidebar', 'userCollapsed', 'overlayOpen', 'railed', 'applyStoredSidebar']) {
      expect(code, word).not.toContain(word);
    }
  });
});

describe('shell top bar (v195 Phase 3, correction 9)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: shellProviders([{ path: 'trades', component: Blank }]) });
  });

  it('leads the bar with the breadcrumb and renders no heading of its own', async () => {
    const fixture = TestBed.createComponent(Shell);
    fixture.detectChanges();
    await TestBed.inject(Router).navigateByUrl('/trades');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const bar = el.querySelector('header.topbar')!;
    expect(bar.firstElementChild!.tagName.toLowerCase()).toBe('sb-breadcrumb');
    const crumbs = [...bar.querySelectorAll('nav[aria-label="Breadcrumb"] li')]
      .map((li) => li.textContent!.replace('/', '').trim());
    expect(crumbs).toEqual(['Review', 'Trades']);
    expect(el.querySelectorAll('h1')).toHaveLength(0);
    expect(el.querySelector('.page-title, .page-subtitle')).toBeNull();
  });

  it('sizes the rail and the bar from two shell tokens, with no animated width', () => {
    const css = readSource('src/app/shell/shell.css');
    const shell = css.match(/^\.shell \{[^}]*\}/m)?.[0] ?? '';
    expect(shell).toContain('--rail-w: 48px;');
    expect(shell).toContain('--topbar-h: 40px;');
    expect(shell).toContain('grid-template-columns: var(--rail-w) 1fr;');
    expect(shell).not.toContain('transition');
    // The touch rules win (spec §1.4): the bar grows to hold 44px controls.
    expect(css).toMatch(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{\s*\.shell \{ --topbar-h: 48px; \}/);
  });
});
```

- [ ] **Step 2: Write the failing pin updates beside the shell**

1. `$WT/frontend/src/app/ui/hit-area.spec.ts`:
   - In `GROWN`, replace `['src/app/shell/shell.css', '.nav a', 'min-height: var(--control-h)'],` with `['src/app/shell/shell.css', '.rail-link', 'min-height: var(--control-h)'],`.
   - In `PADDED`, replace the comment `// The collapsed rail is 52px wide: a 32px link cannot grow, so it pads with .sb-hit.` with `// The rail is 48px wide: its brand link pads with .sb-hit rather than grow.` (the brand entry under it stays as it is), and replace the last entry `['src/app/shell/shell.html', /<a\s+class="sb-hit"\s+\[routerLink\]="entry\.path"/],` with `['src/app/shell/shell.html', /<a\s+#link\s+class="rail-link sb-hit"\s+\[routerLink\]="entry\.path"/],`.

2. `$WT/frontend/src/app/shell/nav-indicator.spec.ts`: the indicator now lives in the rail, whose lists are split by dividers. In `class Host`'s template replace

```html
    <nav class="sidebar">
      <sb-nav-indicator />
      <ul class="nav"><li><a class="first">One</a></li><li><a class="second">Two</a></li></ul>
      <ul class="nav"><li><a class="third">Three</a></li></ul>
    </nav>
```

with

```html
    <nav class="rail">
      <sb-nav-indicator />
      <ul class="nav"><li><a class="first">One</a></li><li><a class="second">Two</a></li></ul>
      <div class="rail-divider" aria-hidden="true"></div>
      <ul class="nav"><li><a class="third">Three</a></li></ul>
    </nav>
```

   then replace the two remaining `nav.sidebar` selectors (in `mount()` and in the observed-elements case) with `nav.rail`, and rename the helper `function sidebar(): HTMLElement` in `describe('indicatorBox (v168 §3 #6)', ...)` to `function rail(): HTMLElement`, with its two call sites `const nav = sidebar();` becoming `const nav = rail();`. The observed-elements case keeps its expectation (the rail, every `.nav`, every `.nav a`): the divider is not observed.

3. `$WT/frontend/src/app/shell/route-focus.spec.ts`: inside `describe('focusWorkspaceHeading', ...)`, after the last case, add:

```ts

  it('focuses the page heading, never a heading outside the workspace (v195 correction 9)', () => {
    // The top bar leads with a breadcrumb list, not a heading; a stray h1
    // outside .workspace must never take focus from the page's own.
    document.body.innerHTML = '<header class="topbar"><nav aria-label="Breadcrumb"><ol><li>Review</li></ol></nav>'
      + '<h1>Stray</h1></header><main class="workspace"><h1>Trades</h1></main>';
    focusWorkspaceHeading(document);
    expect(document.activeElement?.textContent).toBe('Trades');
  });
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/shell.spec.ts --include src/app/shell/nav-indicator.spec.ts --include src/app/shell/route-focus.spec.ts --include src/app/ui/hit-area.spec.ts
```

Expected: FAIL. `shell.spec.ts`: every case reading `nav.rail`, `.rail-link`, `.rail-foot`, `sb-breadcrumb`, `--rail-w` or the sticky `.topbar` fails (the shell still renders `nav.sidebar`), and `has no expanded ... state` fails on `.sidebar` and on `shell.ts` still containing `toggleSidebar`. `hit-area.spec.ts`: the `.rail-link` and `#link class="rail-link sb-hit"` entries fail. `nav-indicator.spec.ts` and `route-focus.spec.ts` pass already (the indicator measures whatever container holds it; `focusWorkspaceHeading` already scopes to `.workspace`): they pin the new structure, not new behaviour.

- [ ] **Step 4: Rewrite `shell.html`**

Replace the whole of `$WT/frontend/src/app/shell/shell.html` with:

```html
<div class="shell">
  <!-- v195 Phase 3: one always-collapsed 48px icon rail. No expanded state,
       no overlay, no hamburger: each entry is a glyph whose name is its
       aria-label and whose label is an anchored hint, shown on hover and on
       keyboard focus (correction 10). -->
  <nav class="rail" aria-label="Primary">
    <!-- v168 §3 #6: one 2px accent bar that slides to the active entry.
         Absolutely placed (shell.css), so it takes no part in the flex gap. -->
    <sb-nav-indicator />
    <div class="mark">
      <a class="brand sb-hit" routerLink="/dashboard" #brand aria-label="Bomeo Capital — go to the Dashboard">
        <sb-icon name="brand" title="" />
      </a>
      <sb-hint [anchor]="brand" text="Bomeo Capital · Dashboard" />
    </div>

    @for (group of navGroups; track group.id; let first = $first) {
      <!-- Groups are told apart by a thin rule, never by text (spec §1.3);
           each list still carries its group's name for assistive tech. -->
      @if (!first) {
        <div class="rail-divider" aria-hidden="true"></div>
      }
      <ul class="nav" [attr.aria-label]="group.label">
        @for (entry of group.entries; track entry.path) {
          <li>
            <!-- title="" on the icon: its default native tooltip would sit on
                 top of the label hint. The hint is the link's sibling, never
                 its child: a button cannot nest in a link, and in anchor mode
                 the hint renders none. -->
            <a
              #link
              class="rail-link sb-hit"
              [routerLink]="entry.path"
              routerLinkActive="active"
              [routerLinkActiveOptions]="{ exact: false }"
              [attr.aria-label]="entry.label"
            >
              <sb-icon [name]="entry.icon" title="" />
            </a>
            <sb-hint [anchor]="link" [text]="entry.label" />
          </li>
        }
      </ul>
    }

    <!-- The install's version, as a hint: 48px holds no "ui 1.36.1" line.
         Nothing renders until the first /health answer -- a version that
         reads 0.0.0 while it waits looks real. -->
    <div class="rail-foot">
      @if (connection.versions()) {
        <sb-hint class="version" glyph="v" label="Version" align="left" [text]="versionText()" />
      }
    </div>
  </nav>

  <div class="main">
    <header class="topbar">
      <!-- A labelled list, never a heading: the page's one <h1> belongs to
           sb-page (correction 9), which route-focus.ts finds inside .workspace. -->
      <sb-breadcrumb class="topbar-lead" />
      <div class="topbar-tape">
        <sb-tape />
      </div>
      <!-- Sheet 2's form: dot, word, clock, read together as one group.
           The dot answers only "is the event stream connected" (D30) -- it
           must never be read as "these numbers are current"; that claim
           belongs to each panel's own sb-freshness. -->
      <div class="status-cluster">
        <sb-connection-status
          [state]="connection.state()"
          [botAlive]="connection.botAlive()"
          [botHealthy]="connection.botHealthy()"
          [marketActive]="connection.marketActive()"
        />
        <span class="clock">
          <sb-icon name="clock" />
          {{ now() }}
        </span>
      </div>
      <sb-profile-menu [zoom]="zoom()" [state]="connection.state()"
                       [botAlive]="connection.botAlive()" [marketActive]="connection.marketActive()" (zoomCycled)="cycleZoom()"
                       [motion]="motionMode()" (motionChanged)="setMotion($event)"
                       (signedOut)="logout()" />
    </header>

    <!-- Engaged killswitch is shell-level and unmissable: it means the bot
         has stopped taking positions, which is true no matter which
         workspace happens to be open. Its own strip, not squeezed into the
         bar, because this is the one message on the page that must never
         be truncated. -->
    @if (killswitchOn()) {
      <div class="killswitch-strip" role="alert">KILLSWITCH ENGAGED</div>
    }

    <main class="workspace" [class.route-pending]="routeLoading.visible()" [attr.aria-busy]="routeLoading.visible() ? 'true' : null">
      <!-- Over the content, never in the flow. An automatic scan runs every
           SCAN_INTERVAL_MINUTES for the whole session, so a strip that took
           up layout would push whatever is being read down and back,
           several times an hour. -->
      <sb-scan-progress
        [running]="connection.scanRunning()"
        [progress]="connection.scanProgress()"
      />
      <div class="workspace-content" [attr.inert]="routeLoading.visible() ? '' : null"><router-outlet /></div>
      @if (routeLoading.visible()) {
        <div class="route-loading-overlay" role="status" aria-live="polite"><span class="route-loading-mark" aria-hidden="true"></span><span>{{ routeLoading.label() }}</span></div>
      }
    </main>
  </div>

  <sb-toast-host />
</div>
```

- [ ] **Step 5: Rewrite `shell.css`**

Replace the whole of `$WT/frontend/src/app/shell/shell.css` with:

```css
.shell {
  /* v195 Phase 3: an always-collapsed icon rail and a 40px top bar. One
     state, so nothing here animates: the old width transition served the
     expand/collapse gesture, which is gone. */
  --rail-w: 48px;
  --topbar-h: 40px;
  display: grid;
  grid-template-columns: var(--rail-w) 1fr;
  min-height: 100vh;
}

/* Sticky and exactly one viewport tall, so the foot (the version hint) sits
 * at the bottom of the screen rather than the bottom of a 4000px page.
 * `height`, not `min-height`: the foot's `margin-top: auto` needs a definite
 * box, and `overflow-y: auto` handles a viewport too short for eleven
 * entries. The scrollbar is hidden: on a 48px rail it would eat a third of
 * the width. */
.rail {
  position: sticky;
  top: 0;
  height: 100vh;
  height: 100dvh;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding-bottom: var(--space-10);
  background: var(--surface);
  border-right: 1px solid var(--border);
}
.rail::-webkit-scrollbar { display: none; }

/* As tall as the top bar (its border included), so the brand mark and the
   breadcrumb centre on one line. */
.mark {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: var(--topbar-h);
  flex: none;
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  text-decoration: none;
}
.brand sb-icon { flex: none; }

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* The rule between groups: a divider, never text (spec §1.3). */
.rail-divider {
  flex: none;
  height: 1px;
  margin: var(--space-4) var(--space-10);
  background: var(--border-strong);
}

/* One glyph, centred in the rail. 36px tall at a desktop pointer; the touch
   block raises --control-h to 44px, and min-height wins over block-size.
   Each link reserves a 2px transparent strip on its left edge, where the
   sliding sb-nav-indicator lands, so nothing shifts when the bar moves. */
.rail-link {
  display: flex;
  align-items: center;
  justify-content: center;
  block-size: 36px;
  min-height: var(--control-h);
  border-left: 2px solid transparent;
  color: var(--text-muted);
  text-decoration: none;
  transition: color var(--transition), background var(--transition);
}

.rail-link sb-icon { flex: none; }

.rail-link:hover { background: var(--surface-raised); color: var(--text); }

/* The bar (sb-nav-indicator), a tint and the glyph stepping from muted to
   full text: three cues, so the active entry survives a monochrome or
   low-vision reading. */
.rail-link.active {
  background: var(--accent-soft);
  color: var(--text);
}

/* Placed against .rail (sticky, so positioned; absolute children scroll
   with its content), on the links' 2px left strip. */
sb-nav-indicator {
  position: absolute;
  top: 0;
  left: 0;
  width: 2px;
  pointer-events: none;
}

.rail-foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-6);
  padding-top: var(--space-8);
  border-top: 1px solid var(--border);
}

.main {
  display: flex;
  flex-direction: column;
  min-width: 0; /* let wide tables scroll instead of stretching the grid */
}

/* Every child centres on the bar. Sticky at every width, so the breadcrumb
   (and, from V195-17, the killswitch and freshness chips) stays in view
   while a long page scrolls. */
.topbar {
  position: sticky;
  top: 0;
  z-index: 15;
  display: flex;
  align-items: center;
  box-sizing: border-box;
  height: var(--topbar-h);
  gap: var(--space-14);
  padding: 0 var(--space-14);
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}

.topbar-lead { flex: 0 1 auto; min-width: 0; }

/* Grows to fill the gap between the breadcrumb and the status cluster, and
   scrolls within it when more symbols arrive than fit. */
.topbar-tape {
  flex: 1 1 0%;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-20);
  overflow-x: auto;
  scrollbar-width: none;
}
.topbar-tape::-webkit-scrollbar { display: none; }

.killswitch-strip {
  padding: var(--space-6) var(--space-14);
  background: var(--neg-soft);
  border-bottom: 1px solid var(--neg);
  color: var(--neg);
  font-size: var(--text-chip);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-align: center;
}

.workspace {
  flex: 1;
  min-width: 0;
  padding: var(--space-20);
}

/* SR23 -- spacing per range. The literals are repeated from breakpoints.ts
   because @media cannot evaluate var(); breakpoint-guard.spec.ts keeps the
   two honest. */
@media (max-width: 1439px) {
  .workspace { padding: var(--space-14); }
}

/* At the widest sizes the limit is the reader, not the screen. */
@media (min-width: 1920px) {
  .workspace { max-width: 1760px; margin-inline: auto; }
}

/* Dot, word and clock read as one cluster, tighter than the bar's own gap. */
.status-cluster {
  display: flex;
  align-items: center;
  gap: var(--space-6);
}

.clock {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
  color: var(--text-secondary);
  font-size: var(--text-chip);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* SR76: tabular-nums so cycling 90/100/110/125 doesn't jiggle the width. */
.zoom {
  min-width: 4.5rem;
  font-variant-numeric: tabular-nums;
}

.workspace { position: relative; }
.workspace-content { min-width: 0; transition: opacity var(--transition); }
.route-pending .workspace-content { opacity: 0.32; pointer-events: none; user-select: none; }
.route-loading-overlay { position: absolute; inset: 0; z-index: 10; display: grid; place-content: center; justify-items: center; gap: var(--space-10); color: var(--text-secondary); background: color-mix(in srgb, var(--surface) 58%, transparent); backdrop-filter: blur(1px); }
.route-loading-mark { width: 24px; height: 24px; border: 2px solid var(--border-strong); border-top-color: var(--accent); border-radius: 50%; animation: sb-route-spin 700ms linear infinite; }

/* The touch rules win (spec §1.4): under a coarse pointer or below 1024px
   the bar's controls are 44px, so the bar grows to hold them. */
@media (pointer: coarse), (max-width: 1023px) {
  .shell { --topbar-h: 48px; }
}

/* Everything here is a removal: the bar never wraps to a second row, which
   would change the height of every page's content area. The breadcrumb
   already shows only the current crumb below 640px and truncates it with
   an ellipsis. */
@media (max-width: 639px) {
  .clock { display: none; }
  .topbar { gap: var(--space-10); padding: 0 var(--space-10); }
  .topbar-tape { display: none; }
  .topbar-lead { flex: 1 1 auto; }
}
```

The `.route-loading-overlay`, `.route-loading-mark`, `.workspace-content`, `.route-pending`, `.killswitch-strip`, `.clock`, `.zoom` and both `.workspace` media rules are today's, unchanged. Deleted with the sidebar: `.shell.railed`, `.shell.overlay` and everything under them, `.scrim`, `.menu-button`, `.sidebar`, `.sidebar-foot`, `.tagline-row`, `.rail-tagline`, `.brand .word`, `.nav-group-label`, `.nav a`, `.version`, `.version-row`, `.page-title`, `.page-subtitle`, and the 1023px block's `--topbar-h: 56px` and subtitle rule.

- [ ] **Step 6: Edit `shell.ts`**

In `$WT/frontend/src/app/shell/shell.ts`:

1. Imports. Delete `import { ViewportService } from '../ui/breakpoints';`, `import { Button } from '../ui/button';` and `import { RouteTitleService } from '../routing/route-title.service';`. Replace `import { Icon, IconName } from '../ui/icon';` with `import { Icon } from '../ui/icon';`. After `import { CLOCK } from '../ui/clock';` add `import { Hint } from '../ui/hint';`. After `import { ConnectionStatus } from './connection-status';` add:

```ts
import { Breadcrumb } from './breadcrumb';
import { NAV_GROUPS } from './nav';
```

2. Delete `interface NavEntry { ... }` and `interface NavGroup { ... }` (both blocks; the shell reads `shell/nav.ts`'s).

3. Replace the class docblock that opens with ` * Sidebar, workspace header, connection status, toast host, outlet.` (from its `/**` to its closing ` */`, the line before `/** The zoom steps the control offers ...`) with:

```ts
/**
 * Icon rail, top bar, connection status, toast host, outlet -- v195 Phase 3.
 *
 * Rendered by App instead of the login form -- it is not itself routed, so
 * there is no state in which the shell exists without a session.
 *
 * **One rail state.** The rail is always 48px and always icons: there is no
 * expanded sidebar, no overlay and no stored collapse choice. The server's
 * pre-v195 sidebar preference is left in place (an older image reads it
 * again on rollback) and is never read or written here.
 *
 * **Scan and bot status live here and nowhere else.** They were on the old
 * Dashboard as well as the header, which meant two renderings of one fact
 * that could disagree; the design system moves them to the shell precisely
 * so a workspace cannot own a second copy. Do not add them to Dashboard.
 *
 * **No heading.** The top bar leads with `sb-breadcrumb`, a labelled list;
 * the page's one `<h1>` is `sb-page`'s (correction 9).
 */
```

4. In `@Component`, replace the `imports` array with:

```ts
  imports: [
    RouterOutlet, RouterLink, RouterLinkActive, ConnectionStatus, ToastHost,
    ScanProgressStrip, Icon, Hint, Breadcrumb, ProfileMenu, NavIndicator, Tape,
  ],
```

5. Delete the two fields `private readonly viewport = inject(ViewportService);` and `protected readonly titles = inject(RouteTitleService);`.

6. Replace the `navGroups` docblock and literal (from the `/**` that opens with `   * Three groups, because eight flat entries stopped communicating.` through the literal's closing `];`) with:

```ts
  /**
   * The four rail groups (v195 §5.1), from the one nav model the phone bar,
   * the More sheet, the palette and the breadcrumb also read. The /ui
   * gallery is deliberately absent: a developer surface, reachable by URL.
   */
  protected readonly navGroups = NAV_GROUPS;

  /** The rail foot's version hint: the words the old footer block showed,
   *  on one line. Empty until the first /health answer; the template
   *  renders no hint until then. */
  protected readonly versionText = computed(() => {
    const versions = this.connection.versions();
    if (!versions) return '';
    const updated = this.connection.lastUpdated();
    return `ui ${versions.ui} · bot ${versions.bot}${updated ? ` · updated ${updated}` : ''}`;
  });
```

7. Delete everything from the `/**` that opens with `   * Whether the sidebar is collapsed to its icon rail — spec v18 Decision 8.` through the closing brace of `protected closeOverlay(): void { ... }` (the `userCollapsed`, `railed`, `overlay`, `overlayOpen`, `toggleSidebar`, `openOverlay` and `closeOverlay` members and their comments).

8. Delete `private readonly applyStoredSidebar = effect(() => { ... });` (the whole effect).

Leave the zoom, motion and killswitch members and the constructor as they are; `computed`, `effect`, `signal` and `untracked` are all still used.

- [ ] **Step 7: Edit `nav-indicator.ts`'s docblocks**

In `$WT/frontend/src/app/shell/nav-indicator.ts` (no code changes: the component measures whichever element contains it):

1. Replace `/** Where the bar sits, in the sidebar's scrolled coordinate space. */` with `/** Where the bar sits, in the rail's scrolled coordinate space. */`.
2. Replace `` * The active link's box relative to `container` (the scrolling `.sidebar`):`` with `` * The active link's box relative to `container` (the scrolling `.rail`):``.
3. Replace the two lines

```ts
 * per-link left border. It lives in `.sidebar`, not in a `.nav` list, because
 * the nav is three lists with group labels between them; the shell places
```

with

```ts
 * per-link left border. It lives in `.rail`, not in a `.nav` list, because
 * the nav is four lists with dividers between them (v195); the shell places
```

4. Replace ` * sidebar, a list or a link changes size: a sidebar collapse, a text-size` with ` * rail, a list or a link changes size: a text-size`.

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/shell/shell.spec.ts --include src/app/shell/nav-indicator.spec.ts --include src/app/shell/route-focus.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/motion-css.spec.ts --include src/app/ui/all-sources.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `motion-css.spec.ts` still finds the `.shell.overlay .sidebar` guard line in `motion.css` (left alone, see "What is left alone"). `title-usage.spec.ts` sees no change (it reads `.ts` files; `shell.ts` binds no `title`). If the focus case reads the popover closed, the hint's anchor listeners were bound before the link rendered: `mount()` already awaits `whenStable()` before reading; do not add a timer. If `has no expanded ... state` fails on a word inside a comment, reword the comment rather than loosen the test.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. A spec elsewhere that queried `.page-title`, `.nav-group-label` or `nav.sidebar` in the shell fails here: `git -C "$WT" grep -n "page-title\|nav-group-label\|nav.sidebar" frontend/src` lists them; repoint each to `sb-breadcrumb` or `nav.rail` the same way.

- [ ] **Step 9: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` (a cold `/app/<route>` bounces by design). At 1440 and 768: the rail is 48px with the brand mark, eleven glyphs in four groups split by three rules, and the `v` hint at the foot; hover the Trades glyph and its label appears to its right on one line without covering the next glyph; press Tab from the brand until Research has focus and its label shows, then Escape hides it while focus stays; the accent bar sits on the active glyph's left edge and follows a click to Calendar; the top bar is 40px at 1440 and 48px at 768 (`getBoundingClientRect().height`) and reads `Monitor / Dashboard`, then `Review / Calendar`; open a trade from Trades and it reads `Review / Trades / <route title>` with Trades linking back. `document.querySelectorAll('h1').length` is 0 on every page (`sb-page` lands in V195-21). At 390: the rail still sits beside the page (the tab bar is V195-18), the breadcrumb shows only the current page, and nothing overflows the bar. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/shell/shell.spec.ts`), plus `frontend/src/app/shell/nav-indicator.spec.ts`, `frontend/src/app/shell/route-focus.spec.ts` and `frontend/src/app/ui/hit-area.spec.ts` in step 2 of the close. One frontend commit; its body names the retired cases (Global Constraints: each retired spec is named in the commit that removes its feature):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/nav-indicator.ts frontend/src/app/shell/nav-indicator.spec.ts frontend/src/app/shell/route-focus.spec.ts frontend/src/app/ui/hit-area.spec.ts
git -C "$WT" commit -m "feat(v195): 48px icon rail in four groups and a 40px breadcrumb top bar (V195-16)" -m "Spec Phase 3, corrections 9 and 10: the rail is always collapsed; each entry is a glyph named by its aria-label and labelled by an anchored sb-hint on hover and focus; groups are split by rules with no text; the active entry keeps sb-nav-indicator's bar plus a tint. The top bar leads with sb-breadcrumb and the shell renders no h1 (sb-page owns it, V195-21). The version block becomes a hint at the rail foot. shell.sidebar is no longer read or written (left on the server for rollback)." -m "Retired with the expandable sidebar (shell.spec.ts): groups the eleven workspaces into three named groups; renders the route title and subtitle in the top bar; renders no subtitle element at all when the route has none; renders the two-tone wordmark as two spans; renders the rail tagline; keeps the mark and drops the words when the rail is collapsed; the 'shell wordmark on a phone' describe. Moved, not dropped: the active-entry, version-foot, bar-overflow, brand-mark and topbar-axis cases now pin the rail. hit-area.spec.ts and nav-indicator.spec.ts repointed at the rail." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

