# UI shell cockpit (v203), part 1: labelled rail, `LiveStore`, live-state rules, Bot section

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md) (§1, §3 "Rail items", §4 "Bot", "Data source", "Open/collapsed state", §6, §8 "Shell" and "Dock")
**Index:** [`2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`](2026-10-29-v203-ui-shell-cockpit-dock_0-index.md). Its Global Constraints, Parallelisation, task ledger and cross-task contracts apply to every task here.

Part scope: V203-1 … V203-4. v202 (plan A) is merged on `main` before this plan starts, so `NAV_ENTRIES`, `navEntryFor`, `destinationFor`, `Shell.navHere`, `SectionTabs` and `GET /api/v1/live` exist "from v202 (merged)". Line numbers below are pre-v202 `main`; v202 shifts some of them, so every edit names the test, rule or element it changes, not only a line.

`<wt>` is the plan's worktree root (absolute). FE paths below are relative to `frontend/src/app/` unless they start with `frontend/`.

---

### Task V203-1: Labelled 80 px rail, System at the foot; retire `sb-nav-indicator`, per-link hints and `NAV_GROUPS`

**Model:** sonnet — a markup/CSS rewrite with many explicit spec retirements, every target named here.

This ledger task is split in two to stay under 20 KB. This half rewrites the rail itself; V203-1b deletes the group model and the indicator files and moves the layout audit's `rail-label` check onto the visible labels.

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (the `nav.rail` block, lines 1-54)
- Modify: `frontend/src/app/shell/shell.css` (the `.shell` rule and the rail rules, lines 1-119)
- Modify: `frontend/src/app/shell/shell.ts` (imports, `navGroups`), `frontend/src/app/shell/shell.spec.ts`
- Modify: `frontend/src/app/ui/hit-area.spec.ts` (the two rail markup pins and the `.rail-link` grown size)

**Interfaces:**
- Consumes (from v202, merged): `NAV_ENTRIES` (`NavEntry { path; label; icon; sections?; foot? }`, System alone `foot: true`), and `Shell.navHere: Signal<{ entry: NavEntry; section: NavSection | null } | null>` (`protected readonly` in `shell.ts`).
- Produces (index ledger, final): `nav.rail > a.rail-brand` (its `sb-hint` sibling follows), then `ul.nav.rail-work > li > a.rail-link` ×5, then `ul.nav.rail-foot > li > a.rail-link` (System), then `div.rail-version` (the version hint). Each `a.rail-link` holds `span.rail-pill > sb-icon` and `span.rail-label`. Active = `a.rail-link.active[aria-current=page]`, pill `.rail-link.active .rail-pill`. Token `--rail-width: 80px` on `.shell`. V203-1b's audit check reads `.rail-label`. V203-9 adds the top bar's own `a.brand`.

**Retired or moved, explicitly** (by test title; `shell.spec.ts` line numbers are pre-v202):
- Retired: `'is one rail of four unlabelled groups split by thin rules'` (:516) → replaced by `'draws six labelled destinations, five work entries then System at the foot (v202 §3)'`.
- Retired: `'names every entry and labels it with an anchored hint, never a title'` (:534) and `'shows an entry label on keyboard focus without adding a tab stop'` (:553) → replaced by `'draws each entry as its icon over its visible label, with no hint and no title'`, which keeps the "no button in the rail" assertion.
- Retired: `'marks the active entry with the bar, a tint and a brighter glyph, not colour alone'` (:278), with its `sb-nav-indicator` count → replaced by `'marks the active entry with the pill and a brighter glyph and label'`.
- Moved: `'marks the routed entry active'` (:565) → an `it.each` over five URLs, found by `.rail-label` (there is no `aria-label` any more).
- Moved: `'keeps each of the four groups a real, named list …'` (:246) → `'keeps the work destinations and System as two named lists'`.
- Moved: version (:294) `nav.rail > .rail-foot` → `nav.rail > .rail-version`; brand (:329) `nav.rail .mark a.brand` → `nav.rail > a.rail-brand`; brand link (:340) `.brand` → `a.rail-brand`; bar height (:496) `rule('.mark')` → `rule('.rail-brand')`; tokens (:617) `--rail-w: 48px` → `--rail-width: 80px`.
- Unchanged: `'has no expanded, collapsed or overlay state, …'`. `.brand .word` stays in its gone-list until V203-9.
- Retired in `hit-area.spec.ts`: the PADDED pin `<a\s+#link\s+class="rail-link sb-hit"…`. A 64×52 link is grown, not padded, so it moves to GROWN.

- [ ] **Step 1: Write the failing shell specs**

In `shell/shell.spec.ts`, change `import { NAV_GROUPS } from './nav';` to `import { NAV_ENTRIES } from './nav';`.

In `describe('shell navigation')`, replace the four-groups test with:

```ts
  it('keeps the work destinations and System as two named lists', () => {
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const lists = (f.nativeElement as HTMLElement).querySelectorAll('nav.rail ul.nav[aria-label]');
    expect([...lists].map((ul) => ul.getAttribute('aria-label'))).toEqual(['Destinations', 'System']);
  });
```

Replace the indicator-bar test with:

```ts
  it('marks the active entry with the pill and a brighter glyph and label', () => {
    const css = readSource('src/app/shell/shell.css');
    expect(css.match(/^\.rail-link\.active \.rail-pill \{[^}]*\}/m)?.[0]).toContain('background: var(--accent-soft);');
    expect(css.match(/^\.rail-link\.active \{[^}]*\}/m)?.[0]).toContain('color: var(--text);');
    expect(css.match(/^\.rail-link \{[^}]*\}/m)?.[0]).toContain('color: var(--text-muted);');
    expect(css).not.toMatch(/sb-nav-indicator|border-left-color/);
  });

  it('sizes each entry 64x52, a 24px icon over a micro label', () => {
    const css = readSource('src/app/shell/shell.css');
    const link = css.match(/^\.rail-link \{[^}]*\}/m)?.[0] ?? '';
    expect(link).toContain('width: 64px;');
    expect(link).toContain('min-height: 52px;');
    expect(css).toMatch(/^\.rail-pill sb-icon svg \{[^}]*width: 24px;[^}]*height: 24px;/m);
    expect(css.match(/^\.rail-label \{[^}]*\}/m)?.[0]).toContain('font-size: var(--text-micro);');
  });
```

Make the "Moved" selector edits listed above, one line each (the two token lines become `expect(shell).toContain('--rail-width: 80px;');` and `expect(shell).toContain('grid-template-columns: var(--rail-width) 1fr;');`).

Rename `describe('shell icon rail (v195 Phase 3, correction 10)')` to `'shell labelled rail (v202 §3)'`, and change its `beforeEach` to:

```ts
    TestBed.configureTestingModule({
      providers: shellProviders([
        { path: 'trades', component: Blank },
        { path: 'trades/calendar', component: Blank },
        { path: 'plans/:id', component: Blank },
        { path: 'insights/analytics', component: Blank },
        { path: 'system/versions', component: Blank },
      ]),
    });
```

Delete its three retired tests and `'marks the routed entry active'`, and add:

```ts
  const labelOf = (link: Element) => link.querySelector('.rail-label')!.textContent!.trim();

  it('draws six labelled destinations, five work entries then System at the foot (v202 §3)', async () => {
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    expect(rail.getAttribute('aria-label')).toBe('Primary');
    expect(rail.firstElementChild!.matches('a.rail-brand')).toBe(true);
    const lists = [...rail.querySelectorAll(':scope > ul.nav')];
    expect(lists.map((ul) => ul.className)).toEqual(['nav rail-work', 'nav rail-foot']);
    const labels = (ul: Element) => [...ul.querySelectorAll(':scope > li > a.rail-link')].map(labelOf);
    expect(labels(lists[0])).toEqual(['Dashboard', 'Watchlist', 'Trades', 'Risk', 'Insights']);
    expect(labels(lists[1])).toEqual(['System']);
    expect(lists[1].nextElementSibling!.matches('.rail-version')).toBe(true);
    expect(rail.querySelector('.rail-divider, sb-nav-indicator, .nav-group-label')).toBeNull();
  });

  it('draws each entry as its icon over its visible label, with no hint and no title', async () => {
    const { el } = await mount();
    const links = [...el.querySelectorAll<HTMLAnchorElement>('nav.rail a.rail-link')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual(NAV_ENTRIES.map((entry) => entry.path));
    for (const link of links) {
      const label = labelOf(link);
      // The visible label is the accessible name; the icon is aria-hidden.
      expect(link.hasAttribute('aria-label'), label).toBe(false);
      expect(link.hasAttribute('title'), label).toBe(false);
      expect(link.querySelector(':scope > .rail-pill > sb-icon')!.getAttribute('title'), label).toBe('');
      expect(link.textContent!.trim(), label).toBe(label);
      expect(link.parentElement!.querySelector('sb-hint'), label).toBeNull();
    }
    expect(el.querySelectorAll('nav.rail ul.nav button')).toHaveLength(0);
  });

  it.each([
    ['/trades', 'Trades'],
    ['/trades/calendar', 'Trades'],
    ['/plans/7', 'Trades'],
    ['/insights/analytics?tab=tuning#x', 'Insights'],
    ['/system/versions', 'System'],
  ])('lights exactly one entry, aria-current, on %s', async (url, label) => {
    const { fixture, el } = await mount();
    await TestBed.inject(Router).navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const active = [...el.querySelectorAll('a.rail-link.active')];
    expect(active.map(labelOf)).toEqual([label]);
    expect(active[0].getAttribute('aria-current')).toBe('page');
    expect(el.querySelectorAll('nav.rail [aria-current]')).toHaveLength(1);
  });

  it('lights nothing off the nav model', async () => {
    // The test bed starts at '', which navEntryFor resolves to null.
    const { el } = await mount();
    expect(el.querySelectorAll('a.rail-link.active, nav.rail [aria-current]')).toHaveLength(0);
  });
```


- [ ] **Step 2: Write the failing hit-area pins**

In `ui/hit-area.spec.ts`, replace the GROWN row `['src/app/shell/shell.css', '.rail-link', 'min-height: var(--control-h)'],` with:

```ts
    // v202 §3: a 64x52 rail entry is past the 44px hit size at every width.
    ['src/app/shell/shell.css', '.rail-link', 'min-height: 52px'],
    ['src/app/shell/shell.css', '.rail-link', 'width: 64px'],
```

In PADDED, replace the brand comment and row with `// The rail's brand mark pads with .sb-hit rather than grow.` and `['src/app/shell/shell.html', /<a class="rail-brand sb-hit" routerLink="\/dashboard"/],`, and delete the last row (`rail-link sb-hit`).

- [ ] **Step 3: Run them to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
```

Expected: FAIL. The rail still draws four groups with hints and no `.rail-label`, and the brand and rail-link pins miss.

- [ ] **Step 4: Rewrite the rail markup**

In `shell/shell.html`, replace the rail's leading comment and the whole `<nav class="rail" …>…</nav>` block (lines 2-54) with:

```html
  <!-- v203 (spec v202 §3): an 80px labelled rail. The diamond mark heads it,
       the five work destinations follow, System sits at the foot. Each entry
       draws its icon over its label, so it needs no hint, and the active
       entry's pill is the indicator. "Active" comes from the nav model
       (navHere), not routerLinkActive, so /plans/7 lights Trades. -->
  <nav class="rail" aria-label="Primary">
    <a class="rail-brand sb-hit" routerLink="/dashboard" #brand aria-label="Bomeo Capital — go to the Dashboard">
      <sb-icon name="brand" title="" />
    </a>
    <sb-hint [anchor]="brand" text="Bomeo Capital · Dashboard" />

    <ul class="nav rail-work" aria-label="Destinations">
      @for (entry of railWork; track entry.path) {
        <li>
          <a class="rail-link" [routerLink]="entry.path"
             [class.active]="entry.path === activePath()"
             [attr.aria-current]="entry.path === activePath() ? 'page' : null">
            <span class="rail-pill"><sb-icon [name]="entry.icon" title="" /></span>
            <span class="rail-label">{{ entry.label }}</span>
          </a>
        </li>
      }
    </ul>

    <ul class="nav rail-foot" aria-label="System">
      @for (entry of railFoot; track entry.path) {
        <li>
          <a class="rail-link" [routerLink]="entry.path"
             [class.active]="entry.path === activePath()"
             [attr.aria-current]="entry.path === activePath() ? 'page' : null">
            <span class="rail-pill"><sb-icon [name]="entry.icon" title="" /></span>
            <span class="rail-label">{{ entry.label }}</span>
          </a>
        </li>
      }
    </ul>

    <!-- The install's version, as a hint. Nothing renders until the first
         /health answer: a version that reads 0.0.0 while it waits looks real. -->
    <div class="rail-version">
      @if (connection.versions()) {
        <sb-hint class="version" glyph="v" label="Version" align="left" [text]="versionText()" />
      }
    </div>
  </nav>
```

- [ ] **Step 5: Rewrite the rail styles**

In `shell/shell.css`, replace everything from the `.shell {` rule through the `.rail-foot { … }` rule (lines 1-119) with:

```css
.shell {
  /* v203 (spec v202 §3): an 80px labelled rail and a 40px top bar. One
     state, so nothing here animates. */
  --rail-width: 80px;
  --topbar-h: 40px;
  display: grid;
  grid-template-columns: var(--rail-width) 1fr;
  min-height: 100vh;
}

/* Sticky and one viewport tall, so the foot (System, the version) sits at
 * the bottom of the screen; overflow-y handles a window too short for it. */
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
  padding-bottom: var(--space-10);
  background: var(--surface);
  border-right: 1px solid var(--border);
}
.rail::-webkit-scrollbar { display: none; }

/* As tall as the top bar (its border included), so the two centre on one line. */
.rail-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: var(--topbar-h);
  flex: none;
  border-bottom: 1px solid var(--border);
  color: var(--accent);
  text-decoration: none;
}
.rail-brand sb-icon { flex: none; }

.nav {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin: 0;
  padding: var(--space-6) 0 0;
  list-style: none;
}

/* System, apart from the work destinations. */
.rail-foot {
  margin-top: auto;
  padding-top: var(--space-8);
  border-top: 1px solid var(--border);
}

/* 64x52 at every width: past the 44px touch size, so no .sb-hit. */
.rail-link {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  box-sizing: border-box;
  width: 64px;
  min-height: 52px;
  padding: var(--space-4) 0;
  border-radius: var(--control-radius);
  color: var(--text-muted);
  text-decoration: none;
  transition: color var(--transition);
}
.rail-link:hover { color: var(--text); }
.rail-link:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }

/* The pill behind the icon is the indicator. */
.rail-pill {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 28px;
  border-radius: var(--control-radius);
  transition: background var(--transition);
}
.rail-pill sb-icon svg { width: 24px; height: 24px; }
.rail-link:hover .rail-pill { background: var(--surface-raised); }

.rail-label {
  max-width: 100%;
  overflow: hidden;
  font-size: var(--text-micro);
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Three cues, so the active entry survives a monochrome reading: the pill,
   glyph and label stepping up to full text, and aria-current. */
.rail-link.active .rail-pill {
  background: var(--accent-soft);
}
.rail-link.active {
  color: var(--text);
}

.rail-version {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-6);
  padding-top: var(--space-8);
}
```

The phone block keeps `.shell { grid-template-columns: 1fr; }` and `.rail { display: none; }` unchanged.

- [ ] **Step 6: Wire the shell**

In `shell/shell.ts`:
- Change `import { NAV_GROUPS, navEntryFor } from './nav';` to `import { NAV_ENTRIES, navEntryFor } from './nav';`.
- Delete `import { NavIndicator } from './nav-indicator';`. Remove `NavIndicator` and `RouterLinkActive` from the component's `imports` array, and drop `RouterLinkActive` from the `@angular/router` import (the rail was its only user).
- Replace the `navGroups` doc comment and field with:

```ts
  /** The rail's five work destinations and its foot (System), from the one
   *  nav model the phone bar, More sheet, palette and breadcrumb read
   *  (v202 §1). The /ui gallery is not on it: a developer surface. */
  protected readonly railWork = NAV_ENTRIES.filter((entry) => !entry.foot);
  protected readonly railFoot = NAV_ENTRIES.filter((entry) => entry.foot);
```

- Directly below `navHere`, add:

```ts
  /** The destination the rail lights: one entry, or none off the nav model. */
  protected readonly activePath = computed(() => this.navHere()?.entry.path ?? null);
```

- In the class doc comment, change "Icon rail" to "Labelled rail", and start the "**One rail state.**" paragraph with "The rail is always 80px, each entry an icon over its label (v202 §3):", keeping the rest.

`NAV_GROUPS` stays in `nav.ts`, unread, until V203-1b deletes it in the next commit. `nav-indicator.ts` stays on disk, unimported, until then too.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/phone-tab-bar.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean.

Complexity: `activePath` is one expression. The template adds no method.

Layout: the three-width audit runs once V203-1b has moved its `rail-label` check onto the visible labels. Until then that check still looks for the retired hints. Here, build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), and open `/dashboard`, `/insights/analytics` and `/system/versions` at 768 and 1440 px with Playwright. Report: no horizontal scroll, six labelled entries with System at the foot, one lit pill, and "Watchlist" and "Insights" with no ellipsis. At 390 px the rail is absent.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.ts \
  frontend/src/app/shell/shell.spec.ts frontend/src/app/ui/hit-area.spec.ts
git -C <wt> commit -m "feat(v203): labelled 80px rail, six destinations, System at the foot

Each entry draws its 24px icon over its label in a 64x52 target; the
active one sits on an accent-soft pill with aria-current, lit from the
nav model, so /plans/7 lights Trades. The rail no longer renders the
sliding indicator or per-link hints.

Retired: the four-group, anchored-hint, label-on-focus and indicator
shell tests and the rail-link .sb-hit pin. Moved, not dropped: brand,
version, token and active-entry tests onto the new markup.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-1b: Delete `NAV_GROUPS` and the sliding indicator; the audit's `rail-label` check reads the visible label

**Model:** sonnet — deletions plus one audit check rewritten onto a new DOM fact, with a pure verdict to test.

The second half of ledger task V203-1, split to stay under 20 KB. It runs straight after V203-1, on the same files list in the ledger.

**Files:**
- Modify: `frontend/src/app/shell/nav.ts` (delete `NavGroup`, `NAV_GROUPS`), `frontend/src/app/shell/nav.spec.ts`
- Delete: `frontend/src/app/shell/nav-indicator.ts`, `frontend/src/app/shell/nav-indicator.spec.ts`
- Modify: `frontend/src/styles/motion.css`, `frontend/src/app/ui/motion-css.spec.ts` (the indicator's motion rule and its test)
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`railLabelVerdict`), `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs` (`railEntry`, `auditRailLabels`, header lines)
- Modify, only if V202-6b added one: `frontend/eslint-suppressions.json` (the `src/app/shell/shell.ts` entry for the deprecated `NAV_GROUPS`)

**Interfaces:**
- Consumes: V203-1's rail markup (`nav.rail a.rail-link` holding `span.rail-label`). `shell.ts` already reads `NAV_ENTRIES`, not `NAV_GROUPS`.
- Produces: `railLabelVerdict({ name, label, labelVisible }) -> { ok: boolean; reason: 'no-name' | 'no-label' | 'label-hidden' | 'label-not-in-name' | null }`. `CHECKS` keeps `'rail-label'`. V203-10 extends the audit on top of this.

**Retired, explicitly:** `nav-indicator.spec.ts` (the file is deleted); `motion-css.spec.ts` `'slides the nav indicator on a spring under On, fades it under Reduced (#6)'`, with the two rules it pins; and the three hint-based `railLabelVerdict` tests in `layout-audit-lib.test.mjs` (`'a named entry whose label shows passes'`, `'an entry with no accessible name fails no-name …'`, `'a named entry whose label stays hidden on focus fails hint-hidden'`), replaced below.

- [ ] **Step 1: Write the failing tests**

In `shell/nav.spec.ts`, import `existsSync`, `readFileSync` (`node:fs`) and `join` (`node:path`) if absent, and append:

```ts
describe('v203: the v195 group model is gone', () => {
  it('exports no NAV_GROUPS or NavGroup, and the sliding indicator is deleted', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/nav.ts'), 'utf8');
    expect(source).not.toMatch(/\bNAV_GROUPS\b|\bNavGroup\b/);
    expect(existsSync(join(process.cwd(), 'src/app/shell/nav-indicator.ts'))).toBe(false);
  });
});
```

In `frontend/scripts/layout-audit-lib.test.mjs`, replace the `railLabelVerdict` comment and its three tests (lines 287-302) with:

```js
// railLabelVerdict (v202 §3): a labelled-rail entry's accessible name, its visible .rail-label, and
// label-in-name (WCAG 2.5.3): the name a screen reader hears contains the word the eye reads.
test('railLabelVerdict: a named entry whose label shows and is in its name passes', () => {
  assert.deepEqual(railLabelVerdict({ name: 'Dashboard', label: 'Dashboard', labelVisible: true }), { ok: true, reason: null });
  assert.deepEqual(railLabelVerdict({ name: 'Insights section', label: 'insights', labelVisible: true }), { ok: true, reason: null });
});

test('railLabelVerdict: no accessible name fails no-name first, whatever the label does', () => {
  for (const name of ['', '   ', null, undefined]) {
    assert.deepEqual(railLabelVerdict({ name, label: 'Risk', labelVisible: true }), { ok: false, reason: 'no-name' }, String(name));
    assert.deepEqual(railLabelVerdict({ name, label: '', labelVisible: false }), { ok: false, reason: 'no-name' }, String(name));
  }
});

test('railLabelVerdict: a missing label, a hidden one and a name without it each fail', () => {
  assert.deepEqual(railLabelVerdict({ name: 'Risk', label: '  ', labelVisible: true }), { ok: false, reason: 'no-label' });
  assert.deepEqual(railLabelVerdict({ name: 'Risk', label: 'Risk', labelVisible: false }), { ok: false, reason: 'label-hidden' });
  assert.deepEqual(railLabelVerdict({ name: 'Open the book', label: 'Trades', labelVisible: true }),
    { ok: false, reason: 'label-not-in-name' });
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts
node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs
```

Expected: FAIL. `nav.ts` still exports `NAV_GROUPS`, `nav-indicator.ts` exists, and `railLabelVerdict` returns `hint-hidden` for `{ labelVisible: false }` and ignores `label`.

- [ ] **Step 3: Delete the group model and the indicator**

In `shell/nav.ts`, delete the `@deprecated` `NavGroup` interface and `NAV_GROUPS` array, with their doc comments. If `frontend/eslint-suppressions.json` holds a `src/app/shell/shell.ts` entry for the deprecated `NAV_GROUPS`, delete it.

```bash
git -C <wt> rm frontend/src/app/shell/nav-indicator.ts frontend/src/app/shell/nav-indicator.spec.ts
```

In `frontend/src/styles/motion.css`, delete the `/* -- #6 nav indicator (sb-nav-indicator, MO11) … */` comment and its two `sb-nav-indicator .nav-indicator` rules. In `frontend/src/app/ui/motion-css.spec.ts`, delete the test `'slides the nav indicator on a spring under On, fades it under Reduced (#6)'`.

- [ ] **Step 4: Move the audit's rail check onto the visible label**

In `frontend/scripts/layout-audit-lib.mjs`, change the `RAIL_MIN_WIDTH` comment's "icon rail" to "labelled rail", and replace `railLabelVerdict` and its doc comment with:

```js
/**
 * The rail-label check's verdict (spec v202 §3) on one labelled-rail entry: its accessible name, its
 * .rail-label text and whether that label shows (layout-audit.mjs auditRailLabels). No name fails
 * first, then no label, then a hidden one, then a name without the label (WCAG 2.5.3 label-in-name).
 */
export function railLabelVerdict(entry) {
  const name = String(entry.name ?? '').trim();
  const label = String(entry.label ?? '').trim();
  if (!name) return { ok: false, reason: 'no-name' };
  if (!label) return { ok: false, reason: 'no-label' };
  if (!entry.labelVisible) return { ok: false, reason: 'label-hidden' };
  if (!name.toLowerCase().includes(label.toLowerCase())) return { ok: false, reason: 'label-not-in-name' };
  return { ok: true, reason: null };
}
```

In `frontend/scripts/layout-audit.mjs`, replace `railEntry`, and `auditRailLabels` with its doc comment, with:

```js
/** Runs inside the page (locator.evaluate): a rail link's accessible name (aria-labelledby,
 *  aria-label, then text) and href, and its .rail-label's text and whether it shows.
 *  Self-contained: isVisuallyHidden arrives as source. */
function railEntry(link, hiddenSrc) {
  const isVisuallyHidden = new Function(`return ${hiddenSrc}`)();
  const shows = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width <= 0 || rect.height <= 0 || style.visibility === 'hidden') return false;
    return !isVisuallyHidden(style, rect) && rect.left >= 0 && rect.right <= window.innerWidth;
  };
  const labelledBy = (link.getAttribute('aria-labelledby') ?? '').split(/\s+/).filter(Boolean)
    .map((id) => document.getElementById(id)?.textContent ?? '').join(' ').trim();
  const name = labelledBy || (link.getAttribute('aria-label') ?? '').trim() || (link.textContent ?? '').trim();
  const label = link.querySelector('.rail-label');
  return {
    name, href: link.getAttribute('href') ?? '',
    label: (label?.textContent ?? '').trim(), labelVisible: label ? shows(label) : false,
  };
}

/**
 * The rail-label check (spec v202 §3): every labelled-rail entry needs an accessible name and a
 * visible .rail-label its name contains. Skipped below RAIL_MIN_WIDTH (the phone's tab bar
 * navigates). Nothing is focused or hovered: the labels are always drawn.
 */
async function auditRailLabels(page, width) {
  if (width < RAIL_MIN_WIDTH) return [];
  const links = page.locator('nav.rail a.rail-link');
  const count = await links.count();
  if (count === 0) return [railFinding({ href: '', name: '' }, 'no rail entries found', `width ${width}`)];
  const hiddenSrc = isVisuallyHidden.toString();
  const findings = [];
  for (let i = 0; i < count; i += 1) {
    const entry = await links.nth(i).evaluate(railEntry, hiddenSrc);
    const verdict = railLabelVerdict(entry);
    if (!verdict.ok) findings.push(railFinding(entry, verdict.reason, entry.label));
  }
  return findings;
}
```

In its header comment, replace the three `rail-label` lines with:

```
 *   rail-label a labelled-rail entry (nav.rail a.rail-link; widths >= 640 only, the phone navigates by
 *              its tab bar) with no accessible name, no visible .rail-label, or a name that does not
 *              contain its label (spec v202 §3). Never allowed.
```

`measureHint`, `hintVerdict` and `HINT_SETTLE_MS` stay: the `hint` check still uses them.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/nav.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/motion-css.spec.ts
node --test <wt>/frontend/scripts/layout-audit-lib.test.mjs
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean, and `git -C <wt> grep -n "NAV_GROUPS\|NavGroup\|nav-indicator\|NavIndicator" -- frontend/src` prints nothing.

Complexity: `railLabelVerdict` 5, `shows` 3, `auditRailLabels` 4.

Layout, at all three widths (this covers V203-1's rail): build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. Report: no horizontal scroll; no `rail-label`, `tap` or `clipped` finding on the rail; each entry 64×52 at 768 and 1440; "Watchlist" and "Insights" fit 64 px without an ellipsis; System at the foot with the version hint below it; on a short window the rail scrolls rather than clips. At 390 the check is skipped: the rail is absent and the tab bar navigates.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts \
  frontend/src/styles/motion.css frontend/src/app/ui/motion-css.spec.ts \
  frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs frontend/scripts/layout-audit.mjs
git -C <wt> add frontend/eslint-suppressions.json   # only if Step 3 changed it
git -C <wt> commit -m "refactor(v203): delete NAV_GROUPS and the sliding indicator; audit reads rail labels

The v195 four-group model and sb-nav-indicator had no reader left after
the labelled rail. The layout audit's rail-label check now requires a
visible .rail-label that the entry's accessible name contains (WCAG
2.5.3), instead of an anchored hint opened on focus.

Retired: nav-indicator.spec, the indicator's motion test and the three
hint-based railLabelVerdict tests.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`git rm` in Step 3 already staged the two deleted files.)

### Task V203-2: `/live` client types, `ApiClient.live`, root `LiveStore` (debounced refresh)

**Model:** sonnet — a typed client method and a small signal store with timer logic, specified to the line.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append the live types at the end)
- Modify: `frontend/src/app/api/api-client.ts` (one method, after `health()`), `frontend/src/app/api/api-client.spec.ts`
- Create: `frontend/src/app/stores/live.store.ts`, `frontend/src/app/stores/live.store.spec.ts`

**Interfaces:**
- Consumes (from v202, merged): `GET /api/v1/live?limit=` and its payload (index § "`/live` payload"). `EventStream.changes(name): Signal<number>` (`api/event-stream.ts`). `killswitch` raises `risk`, `scan_progress` raises `scan` and `bot_heartbeat` raises `bot`.
- Produces (index ledger, final): the types in index § "SPA types" (`LiveAvailability`, `LiveHeat`, `LiveAwaiting`, `LiveKillswitch`, `LiveEventKind`, `LiveTone`, `LiveEvent`, `LiveEventsMeta`, `LiveSnapshot`). `ApiClient.live(limit?: number): Observable<LiveSnapshot>`. `LiveStore` (root `signalStore`) with `snapshot(): LiveSnapshot | null`, `loading(): boolean`, `failed(): boolean`, `heat(): LiveHeat | null`, `awaiting(): LiveAwaiting | null`, `killswitch(): LiveKillswitch | null`, `events(): readonly LiveEvent[]`, `eventsMeta(): LiveEventsMeta | null`, `load(): void`, `retry(): void`. Constants `LIVE_REFRESH_DEBOUNCE_MS = 2000` and `LIVE_REFRESH_EVENTS = ['trades', 'scan', 'bot', 'risk'] as const`. V203-3 reads the types. V203-7 injects the store, and the dock is the only reader.

Behaviour this task pins:
- **First load on init**, then one refresh **2 s after the first of a burst** of `trades`/`scan`/`bot`/`risk` events. Later events in the window fold into that one request. This is a fixed window, not a resetting debounce: a running scan raises `scan` about once a second, and a timer that restarts on every event would never fire during a scan. That keeps the spec's "one request per 2 s".
- **A failed refresh keeps the last answer** and raises `failed()`. Each section carries its own `as_of`, so the age shows the data getting old. Blanking the dock on one bad poll would make it flicker; ConnectionStore makes the same choice. A later success clears `failed()`.
- **`retry()`** loads at once and drops a pending refresh. A new load cancels the one still in flight, so an older answer can never land last.

- [ ] **Step 1: Write the failing client spec**

Append to `api/api-client.spec.ts`:

```ts
describe('ApiClient — live (v203)', () => {
  let api: ApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor])),
        provideHttpClientTesting(),
        { provide: RouteRefreshService, useValue: { requestMutationRefresh: () => undefined } },
      ],
    });
    api = TestBed.inject(ApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('GETs /live with no limit by default, and returns the body untouched', () => {
    const body = { heat: {}, awaiting: {}, killswitch: {}, events: [], events_meta: {} };
    let seen: unknown;
    api.live().subscribe((snapshot) => (seen = snapshot));
    const req = http.expectOne((r) => r.url === '/api/v1/live');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys()).toEqual([]);
    req.flush(body);
    expect(seen).toEqual(body);
  });

  it('sends a limit only when one is given', () => {
    api.live(20).subscribe();
    expect(http.expectOne((r) => r.url === '/api/v1/live').request.params.get('limit')).toBe('20');
  });
});
```

- [ ] **Step 2: Write the failing store spec**

Create `stores/live.store.spec.ts`:

```ts
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApplicationRef, Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { LiveSnapshot } from '../api/models';
import { LIVE_REFRESH_DEBOUNCE_MS, LIVE_REFRESH_EVENTS, LiveStore } from './live.store';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  readonly lastSeq = signal(0);
  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }
  changes(name: string): Signal<number> { return this.counterFor(name).asReadonly(); }
  state(): 'live' { return 'live'; }
  connect(): void { /* no-op */ }
  raise(name: string): void { this.counterFor(name).update((n) => n + 1); }
}

const AS_OF = '2026-10-29T13:32:00+00:00';
const SNAPSHOT: LiveSnapshot = {
  heat: { availability: 'ok', as_of: AS_OF, reason: null, open_pct: 4.2, cap_pct: 6, utilisation_pct: 70,
    open_amount: 2010, cap_amount: 2893, headroom_pct: 1.8, headroom_amount: 883, balance: 48210, includes_resting: true },
  awaiting: { availability: 'ok', as_of: AS_OF, reason: null, count: 3, next_expiry: '2026-10-30T20:00:00+00:00' },
  killswitch: { availability: 'ok', as_of: AS_OF, reason: null, engaged: false, since: null, detail: null },
  events: [{ at: AS_OF, kind: 'trade_closed', text: 'NVDA closed · TP2', tone: 'positive', ref: '812', pnl: { r: 2.1, amount: 441 } }],
  events_meta: { availability: 'ok', as_of: AS_OF, missing: [] },
};

describe('LiveStore (v203)', () => {
  let store: InstanceType<typeof LiveStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;
  const tick = () => TestBed.inject(ApplicationRef).tick();
  const pending = () => backend.match((r) => r.url === '/api/v1/live');

  beforeEach(() => {
    vi.useFakeTimers();
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
      ],
    });
    store = TestBed.inject(LiveStore);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
    vi.useRealTimers();
  });

  it('refreshes on exactly the trades, scan, bot and risk events, 2 s apart', () => {
    expect(LIVE_REFRESH_EVENTS).toEqual(['trades', 'scan', 'bot', 'risk']);
    expect(LIVE_REFRESH_DEBOUNCE_MS).toBe(2000);
  });

  it('reads nothing before the first answer, and says it is loading', () => {
    expect(store.snapshot()).toBeNull();
    expect(store.loading()).toBe(true);
    expect(store.heat()).toBeNull();
    expect(store.awaiting()).toBeNull();
    expect(store.killswitch()).toBeNull();
    expect(store.eventsMeta()).toBeNull();
    expect(store.events()).toEqual([]);
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
  });

  it('loads once on init and exposes each section', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    expect(store.loading()).toBe(false);
    expect(store.failed()).toBe(false);
    expect(store.heat()?.open_amount).toBe(2010);
    expect(store.awaiting()?.count).toBe(3);
    expect(store.killswitch()?.engaged).toBe(false);
    expect(store.events()).toHaveLength(1);
    expect(store.eventsMeta()?.availability).toBe('ok');
  });

  it('folds a burst of events into one request, 2 s after the first', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('trades');
    tick();
    vi.advanceTimersByTime(1000);
    events.raise('scan');
    events.raise('risk');
    tick();
    vi.advanceTimersByTime(999);
    expect(pending()).toHaveLength(0);
    vi.advanceTimersByTime(1);
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    vi.advanceTimersByTime(5000);
    expect(pending()).toHaveLength(0);
  });

  it('still refreshes every 2 s while a scan raises scan every second', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    for (let second = 0; second < 4; second += 1) {
      events.raise('scan');
      tick();
      vi.advanceTimersByTime(1000);
    }
    // A resetting debounce would still be waiting. The fixed window fired at
    // 2 s and at 4 s, and the second load cancelled the first, unanswered one.
    const requests = pending();
    expect(requests.map((r) => r.cancelled)).toEqual([true, false]);
    requests[1].flush(SNAPSHOT);
  });

  it('ignores every other event', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('jobs');
    events.raise('watchlist');
    tick();
    vi.advanceTimersByTime(LIVE_REFRESH_DEBOUNCE_MS * 2);
    expect(pending()).toHaveLength(0);
  });

  it('keeps the last answer on a failed refresh and says so, until a later success', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('bot');
    tick();
    vi.advanceTimersByTime(LIVE_REFRESH_DEBOUNCE_MS);
    backend.expectOne('/api/v1/live').flush({ error: 'boom' }, { status: 503, statusText: 'down' });
    expect(store.failed()).toBe(true);
    expect(store.loading()).toBe(false);
    expect(store.heat()?.open_amount).toBe(2010);
    store.retry();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    expect(store.failed()).toBe(false);
  });

  it('fails cleanly when the very first read fails: no snapshot, not loading', () => {
    tick();
    backend.expectOne('/api/v1/live').error(new ProgressEvent('error'), { status: 0 });
    expect(store.snapshot()).toBeNull();
    expect(store.failed()).toBe(true);
    expect(store.loading()).toBe(false);
  });

  it('retries at once, drops the pending refresh, and lets no older answer land last', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('trades');
    tick();
    store.retry();
    const [first] = pending();
    store.retry();
    expect(first.cancelled).toBe(true);
    // match() already removed the first request, so only the second is open.
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    vi.advanceTimersByTime(LIVE_REFRESH_DEBOUNCE_MS * 2);
    expect(pending()).toHaveLength(0);
  });
});
```

`backend.match` returns the matched requests and takes them off the controller's open list, so `verify()` no longer sees them. `TestRequest.cancelled` is true once the store has unsubscribed.

- [ ] **Step 3: Run them to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/api/api-client.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/stores/live.store.spec.ts
```

Expected: FAIL to compile: `ApiClient.live`, `LiveSnapshot` and `./live.store` do not exist.

- [ ] **Step 4: Add the types**

Append to `api/models.ts`:

```ts
/* -- v203: GET /api/v1/live, the dock's one read (spec v202 §5) ---------- */

/** Per section. `partial` only on events: heat and awaiting are all or nothing. */
export type LiveAvailability = 'ok' | 'partial' | 'unavailable';

/** Every section's envelope. A failed section keeps its keys with null
 *  values, `availability: 'unavailable'` and a short `reason`. */
interface LiveSectionBase { availability: LiveAvailability; as_of: string; reason: string | null; }

/** Open heat against the cap: the Risk page's own definition (v202
 *  `open_heat_state`), counting resting orders. `utilisation_pct` is
 *  unclamped; `headroom_*` goes negative over the cap. */
export interface LiveHeat extends LiveSectionBase {
  open_pct: number | null; cap_pct: number | null; utilisation_pct: number | null;
  open_amount: number | null; cap_amount: number | null; headroom_pct: number | null; headroom_amount: number | null;
  balance: number | null; includes_resting: boolean;
}

/** PENDING plans. `next_expiry` only among plans with a `valid_session`. */
export interface LiveAwaiting extends LiveSectionBase { count: number | null; next_expiry: string | null; }

/** The current killswitch row. `since` is set only while engaged. */
export interface LiveKillswitch extends LiveSectionBase { engaged: boolean | null; since: string | null; detail: string | null; }

export type LiveEventKind = 'plan_alerted' | 'paper_filled' | 'tp1_hit' | 'trade_closed' | 'killswitch';
export type LiveTone = 'info' | 'positive' | 'negative' | 'warning' | 'neutral';

/** One activity row. `text` carries no P&L; `pnl.amount` may be null. */
export interface LiveEvent {
  at: string; kind: LiveEventKind; text: string; tone: LiveTone; ref: string | null;
  pnl: { r: number; amount: number | null } | null;
}

/** `missing` names the kinds whose source failed. */
export interface LiveEventsMeta { availability: LiveAvailability; as_of: string; missing: LiveEventKind[]; }

export interface LiveSnapshot {
  heat: LiveHeat; awaiting: LiveAwaiting; killswitch: LiveKillswitch;
  events: LiveEvent[]; events_meta: LiveEventsMeta;
}
```

- [ ] **Step 5: Add the client method**

In `api/api-client.ts`, add `LiveSnapshot` to the `import { … } from './models'` list, and add directly after `health()`:

```ts
  /** v203: the dock's one read -- heat, plans awaiting order, the killswitch
   *  and recent activity, from Postgres only (spec v202 §5). The server
   *  defaults `limit` to 8 and caps it at 50. */
  live(limit?: number): Observable<LiveSnapshot> {
    const params = limit === undefined ? new HttpParams() : new HttpParams().set('limit', String(limit));
    return this.http.get<LiveSnapshot>(`${this.base}/live`, { params });
  }
```

- [ ] **Step 6: Write the store**

Create `stores/live.store.ts`:

```ts
import { computed, effect, inject, untracked } from '@angular/core';
import { patchState, signalStore, withComputed, withHooks, withMethods, withState } from '@ngrx/signals';
import { Subscription } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { LiveEvent, LiveSnapshot } from '../api/models';

/** The events that can move a dock figure: a trade or plan row, a scan, the
 *  bot's heartbeat and the killswitch (which raises `risk`). */
export const LIVE_REFRESH_EVENTS = ['trades', 'scan', 'bot', 'risk'] as const;

/** At most one `/live` request per window (spec v202 §4). */
export const LIVE_REFRESH_DEBOUNCE_MS = 2000;

const NO_EVENTS: readonly LiveEvent[] = [];

interface LiveSlice {
  snapshot: LiveSnapshot | null;
  /** True until the first answer, and while a request is in flight. */
  loading: boolean;
  /** The last request failed. The last good snapshot is kept: each section
   *  carries its own `as_of`, so its age shows the data getting old. */
  failed: boolean;
}

/**
 * The Live dock's data -- v203 (spec v202 §4 "Data source"). Root-scoped,
 * read only by the shell's dock, edge tab and strip. It never touches
 * `RiskStore` or `/risk`; heat comes only from `/live`.
 *
 * Refresh: one load on init, then one request LIVE_REFRESH_DEBOUNCE_MS after
 * the FIRST event of a burst. It is a fixed window, not a resetting
 * debounce: a running scan raises `scan` about once a second, and a timer
 * that restarted on each one would never fire.
 */
export const LiveStore = signalStore(
  { providedIn: 'root' },
  withState<LiveSlice>({ snapshot: null, loading: true, failed: false }),
  withComputed(({ snapshot }) => ({
    heat: computed(() => snapshot()?.heat ?? null),
    awaiting: computed(() => snapshot()?.awaiting ?? null),
    killswitch: computed(() => snapshot()?.killswitch ?? null),
    events: computed<readonly LiveEvent[]>(() => snapshot()?.events ?? NO_EVENTS),
    eventsMeta: computed(() => snapshot()?.events_meta ?? null),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    let inflight: Subscription | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const cancelTimer = (): void => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    };

    const load = (): void => {
      cancelTimer();
      inflight?.unsubscribe();
      patchState(store, { loading: true });
      inflight = api.live().subscribe({
        next: (snapshot) => patchState(store, { snapshot, loading: false, failed: false }),
        error: () => patchState(store, { loading: false, failed: true }),
      });
    };

    return {
      load,
      /** The panel-error retry: at once, dropping any pending refresh. */
      retry: load,
      /** One request at the end of the current window; later events join it. */
      _scheduleRefresh(): void {
        if (timer === null) timer = setTimeout(load, LIVE_REFRESH_DEBOUNCE_MS);
      },
      _stop(): void {
        cancelTimer();
        inflight?.unsubscribe();
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const counters = LIVE_REFRESH_EVENTS.map((name) => events.changes(name));
      let first = true;
      // Reading the counters subscribes; the first run is the initial load.
      effect(() => {
        counters.forEach((counter) => counter());
        untracked(() => {
          if (first) store.load();
          else store._scheduleRefresh();
          first = false;
        });
      });
    },
    onDestroy(store) {
      store._stop();
    },
  }),
);
```

`_`-prefixed members are private to the store in `@ngrx/signals` 21: `withHooks` sees them, consumers do not.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/api/api-client.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/stores/live.store.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean.

Complexity: `load` 1, `cancelTimer` 2, `_scheduleRefresh` 2, the effect body 2.

Layout: no UI in this task. The dock that renders it is checked at three widths in V203-7 and V203-8.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts \
  frontend/src/app/stores/live.store.ts frontend/src/app/stores/live.store.spec.ts
git -C <wt> commit -m "feat(v203): /live client types and a root LiveStore

ApiClient.live reads v202's DB-only endpoint. LiveStore loads it once
and then at most once per 2 s window on the trades, scan, bot and risk
events. The window is fixed, so a scan's once-a-second event still
refreshes. A failed refresh keeps the last answer and raises failed();
retry() loads at once and cancels the request in flight.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-3: Live-state rules (warnings, alarm, heat tone, times) and the dock preference

**Model:** sonnet — pure table-driven rules, every rule and its wording spelled out here.

Ledger task V203-3 is split in two to stay under 20 KB. This half writes the pure rules in `live-state.ts` and exports the stale rule. V203-3b writes `DockState` on top of them.

**Files:**
- Create: `frontend/src/app/shell/live/live-state.ts`, `frontend/src/app/shell/live/live-state.spec.ts`
- Modify: `frontend/src/app/ui/freshness.ts` (export `STALE_AFTER_SEC`)

**Interfaces:**
- Consumes: `LiveHeat` (V203-2), `Preferences` (`api/models.ts`), `ConnectionState` (`stores/connection.store.ts`), `ABSENT` and `timeInZone` (`ui/format.ts:10,176`), `scanAge(at, nowMs)` (`shell/freshness-chip.ts:12`).
- Produces (index § "Live-state rules", final, verbatim): `LiveWarning`, `LiveWarningInput`, `liveWarnings`, `warningLabel`, `AlarmKind`, `Alarm`, `alarmFor`, `isStale`, `HeatTone`, `heatTone`, `heatStripText`, `liveTime`, `DOCK_PREF_KEY`, `DOCK_DEFAULT_OPEN`, `dockDefaultOpen`, `readDockOpen`, `writeDockOpen`; and `STALE_AFTER_SEC = 900` in `ui/freshness.ts`. V203-3b and V203-4…V203-9 read these. No surface words a state itself.

Rules pinned here:
- **Warnings** come in the type's fixed order. `heat-near-cap` applies at a utilisation ≥ 80 and ≤ 100, `over-cap` above 100 (never both). `stale` applies only once `/health` has answered (`botAlive !== null`), so a cold load raises no alarm. `disconnected` means the stream is `dead` or `degraded`, `bot-down` means `botAlive === false`, and `killswitch` means `killswitchOn === true`.
- **Alarm** priority is bot-down > disconnected > stale. The stale text is `Data stale N min` under an hour, then `Data stale Nh`, then `Data stale Nd`, and just `Data stale` with no time.
- **Strip heat** prints the currency symbol before a whole amount (the spec's `$2,010`), one decimal at most on each percent (`4.2%`, `6%`), and `· Over cap` above 100 %. It prints `Heat —` for a missing, unavailable or incomplete heat.
- **`liveTime`**: `14:32 · 6m ago` in Berlin time. The age is `scanAge`'s wording, the same as the freshness chip ("6m ago", "5h ago"), and an absent or bad time gives `—`.
- **Dock preference**: `prefs['shell.dock']` is a map from destination path to boolean. A non-object map or a non-boolean value reads as the fallback. A write returns a new object and keeps the other destinations.

- [ ] **Step 1: Write the failing spec**


Create `shell/live/live-state.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { LiveHeat } from '../../api/models';
import { STALE_AFTER_SEC } from '../../ui/freshness';
import {
  DOCK_DEFAULT_OPEN, DOCK_PREF_KEY, LiveWarning, LiveWarningInput, alarmFor, dockDefaultOpen, heatStripText, heatTone,
  isStale, liveTime, liveWarnings, readDockOpen, warningLabel, writeDockOpen,
} from './live-state';

const NOW = new Date('2026-10-29T13:00:00Z');            // 14:00 in Berlin (CET)
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const calm: LiveWarningInput = { utilisationPct: 50, lastSuccess: ago(2), now: NOW, streamState: 'live', botAlive: true, killswitchOn: false };
const heat = (over: Partial<LiveHeat> = {}): LiveHeat => ({
  availability: 'ok', as_of: ago(0), reason: null, open_pct: 4.2, cap_pct: 6, utilisation_pct: 70, open_amount: 2010.4,
  cap_amount: 2893, headroom_pct: 1.8, headroom_amount: 883, balance: 48210, includes_resting: true, ...over,
});

describe('the stale rule (one 900 s rule, ui/freshness.ts)', () => {
  it('exports 900 s and freshness.ts uses it as its default', () => {
    expect(STALE_AFTER_SEC).toBe(900);
    expect(readFileSync(join(process.cwd(), 'src/app/ui/freshness.ts'), 'utf8')).toContain('input<number>(STALE_AFTER_SEC)');
  });
  it.each([[null, true], ['not a time', true], [ago(14), false], [ago(15), false], [ago(16), true]])(
    'isStale(%s) is %s', (at, stale) => expect(isStale(at, NOW)).toBe(stale));
  it('takes another window when given one', () => expect(isStale(ago(3), NOW, 60)).toBe(true));
});

describe('heatTone: amber from 80 %, over above 100 %, never clamped', () => {
  it.each([[null, 'unknown'], [Number.NaN, 'unknown'], [0, 'ok'], [79.9, 'ok'], [80, 'near'], [100, 'near'], [100.1, 'over'], [130, 'over']])(
    '%s -> %s', (pct, tone) => expect(heatTone(pct as number | null)).toBe(tone));
});

describe('liveWarnings', () => {
  it('raises nothing on a calm book', () => expect(liveWarnings(calm)).toEqual([]));
  it.each<[Partial<LiveWarningInput>, LiveWarning[]]>([
    [{ utilisationPct: 85 }, ['heat-near-cap']],
    [{ utilisationPct: 130 }, ['over-cap']],
    [{ lastSuccess: ago(20) }, ['stale']],
    [{ lastSuccess: null }, ['stale']],
    [{ streamState: 'degraded' }, ['disconnected']],
    [{ streamState: 'dead' }, ['disconnected']],
    [{ streamState: 'connecting' }, []],
    [{ botAlive: false }, ['bot-down']],
    [{ killswitchOn: true }, ['killswitch']],
    [{ killswitchOn: null }, []],
  ])('%o -> %o', (change, expected) => expect(liveWarnings({ ...calm, ...change })).toEqual(expected));
  it('raises no stale alarm before /health answers', () => {
    expect(liveWarnings({ ...calm, botAlive: null, lastSuccess: null })).toEqual([]);
  });
  it('lists every warning at once, in the fixed order', () => {
    expect(liveWarnings({ utilisationPct: 101, lastSuccess: ago(300), now: NOW, streamState: 'dead', botAlive: false, killswitchOn: true }))
      .toEqual(['over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch']);
  });
  it('names each warning', () => {
    expect((['heat-near-cap', 'over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch'] as LiveWarning[]).map(warningLabel))
      .toEqual(['Heat near cap', 'Over cap', 'Data stale', 'Disconnected', 'Bot down', 'Killswitch active']);
  });
});

describe('alarmFor: the top bar alarm, in exactly three conditions', () => {
  const base = { lastSuccess: ago(2), now: NOW, streamState: 'live' as const, botAlive: true };
  it('is null when nothing is wrong, and before /health answers', () => {
    expect(alarmFor(base)).toBeNull();
    expect(alarmFor({ ...base, botAlive: null, lastSuccess: null })).toBeNull();
  });
  it.each([[12, 'Data stale 12 min'], [59, 'Data stale 59 min'], [300, 'Data stale 5h'], [3000, 'Data stale 2d']])(
    'words a %s-minute-old success as %s', (min, text) => expect(alarmFor({ ...base, lastSuccess: ago(min) })).toEqual({ kind: 'stale', text }));
  it('words a missing success as plain Data stale', () => {
    expect(alarmFor({ ...base, lastSuccess: null })).toEqual({ kind: 'stale', text: 'Data stale' });
  });
  it('puts bot-down over disconnected over stale', () => {
    const all = { ...base, lastSuccess: ago(60), streamState: 'dead' as const, botAlive: false };
    expect(alarmFor(all)).toEqual({ kind: 'bot-down', text: 'Bot down' });
    expect(alarmFor({ ...all, botAlive: true })).toEqual({ kind: 'disconnected', text: 'Disconnected' });
  });
});

describe('heatStripText', () => {
  it('reads dollars, then percent against the cap', () => expect(heatStripText(heat(), '$')).toBe('Heat 2,010 $ · 4.2% / 6%'));
  it('adds Over cap above 100 % and never clamps', () => {
    expect(heatStripText(heat({ open_amount: 3100, open_pct: 7.8, utilisation_pct: 130 }), '$')).toBe('Heat 3,100 $ · 7.8% / 6% · Over cap');
    expect(heatStripText(heat({ utilisation_pct: 100 }), '€')).toBe('Heat 2,010 € · 4.2% / 6%');
  });
  it.each([['null', null], ['unavailable', heat({ availability: 'unavailable' })], ['no amount', heat({ open_amount: null })],
    ['no cap', heat({ cap_pct: null })]])('prints Heat — for %s', (_, value) => expect(heatStripText(value, '$')).toBe('Heat —'));
});

describe('liveTime', () => {
  it('prints Berlin time and the age', () => expect(liveTime(ago(6), NOW)).toBe('13:54 · 6m ago'));
  it('crosses into summer time correctly', () => {
    expect(liveTime('2026-07-01T07:00:00Z', new Date('2026-07-01T12:00:00Z'))).toBe('09:00 · 5h ago');
  });
  it.each([[null], [''], ['garbage']])('prints — for %s', (iso) => expect(liveTime(iso, NOW)).toBe('—'));
});

describe('the dock preference (shell.dock, keyed by destination)', () => {
  it('opens on Dashboard and Risk only by default', () => {
    expect([...DOCK_DEFAULT_OPEN]).toEqual(['/dashboard', '/risk']);
    expect(['/dashboard', '/risk', '/trades', '/insights', '/system', null].map(dockDefaultOpen))
      .toEqual([true, true, false, false, false, false]);
  });
  it('reads a stored boolean, else the fallback', () => {
    const prefs = { [DOCK_PREF_KEY]: { '/trades': true, '/risk': 'yes' } };
    expect(readDockOpen(prefs, '/trades', false)).toBe(true);
    expect(readDockOpen(prefs, '/risk', true)).toBe(true);
    expect(readDockOpen(prefs, '/watchlist', false)).toBe(false);
    for (const junk of [null, 'open', ['/trades'], 7]) {
      expect(readDockOpen({ [DOCK_PREF_KEY]: junk }, '/trades', false), String(junk)).toBe(false);
    }
    expect(readDockOpen({}, '/dashboard', true)).toBe(true);
  });
  it('writes a new object, keeping other keys and destinations', () => {
    const before = { 'x.other': 1, [DOCK_PREF_KEY]: { '/risk': false } };
    const after = writeDockOpen(before, '/trades', true);
    expect(after).toEqual({ 'x.other': 1, [DOCK_PREF_KEY]: { '/risk': false, '/trades': true } });
    expect(before[DOCK_PREF_KEY]).toEqual({ '/risk': false });
    expect(writeDockOpen({ [DOCK_PREF_KEY]: 'junk' }, '/risk', true)).toEqual({ [DOCK_PREF_KEY]: { '/risk': true } });
  });
});
```


- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-state.spec.ts
```

Expected: FAIL to compile: `./live-state` and `STALE_AFTER_SEC` do not exist.

- [ ] **Step 3: Export the stale rule**


In `ui/freshness.ts`, add above the `@Component` decorator:

```ts
/** The one staleness rule (spec v202 §3): older than this, data is stale.
 *  The shell's alarm chip, the dock's warning tone and "No scan since" read
 *  it through shell/live/live-state.ts. */
export const STALE_AFTER_SEC = 900;
```

Then change `readonly staleAfterSec = input<number>(900);` to `readonly staleAfterSec = input<number>(STALE_AFTER_SEC);`.


- [ ] **Step 4: Write the rules**


Create `shell/live/live-state.ts`:

```ts
import { LiveHeat, Preferences } from '../../api/models';
import { ConnectionState } from '../../stores/connection.store';
import { ABSENT, amount, timeInZone } from '../../ui/format';
import { STALE_AFTER_SEC } from '../../ui/freshness';
import { scanAge } from '../freshness-chip';

/**
 * Live state, worded once -- v203 (spec v202 §3, §4, §6). The edge tab, the
 * strip, the alarm chip and the dock sections all read these, so a state
 * never reads two ways on two surfaces. Pure, and table-driven.
 */
export type LiveWarning = 'heat-near-cap' | 'over-cap' | 'stale' | 'disconnected' | 'bot-down' | 'killswitch';

export interface LiveWarningInput {
  utilisationPct: number | null; lastSuccess: string | null; now: Date;
  streamState: ConnectionState; botAlive: boolean | null; killswitchOn: boolean | null;
}

export type AlarmKind = 'bot-down' | 'disconnected' | 'stale';
export interface Alarm { kind: AlarmKind; text: string; }
export type HeatTone = 'unknown' | 'ok' | 'near' | 'over';

const NEAR_CAP_PCT = 80;
const MINUTE_MS = 60_000;
const BERLIN = 'Europe/Berlin';

/** True when `lastSuccess` is absent, unreadable or older than the window. */
export function isStale(lastSuccess: string | null, now: Date, staleAfterSec = STALE_AFTER_SEC): boolean {
  const at = lastSuccess ? Date.parse(lastSuccess) : Number.NaN;
  return Number.isNaN(at) || (now.getTime() - at) / 1000 > staleAfterSec;
}

/** Amber from 80 % of the cap, "over" above 100 %. Never clamped, never red (Phase 1). */
export function heatTone(utilisationPct: number | null): HeatTone {
  if (utilisationPct === null || !Number.isFinite(utilisationPct)) return 'unknown';
  if (utilisationPct > 100) return 'over';
  return utilisationPct >= NEAR_CAP_PCT ? 'near' : 'ok';
}

const disconnected = (state: ConnectionState) => state === 'dead' || state === 'degraded';
/** Stale counts only once /health has answered: a cold load is not an alarm. */
const staleAfterHealth = (i: { botAlive: boolean | null; lastSuccess: string | null; now: Date }) =>
  i.botAlive !== null && isStale(i.lastSuccess, i.now);

const WARNING_RULES: readonly (readonly [LiveWarning, (i: LiveWarningInput) => boolean])[] = [
  ['heat-near-cap', (i) => heatTone(i.utilisationPct) === 'near'],
  ['over-cap', (i) => heatTone(i.utilisationPct) === 'over'],
  ['stale', staleAfterHealth],
  ['disconnected', (i) => disconnected(i.streamState)],
  ['bot-down', (i) => i.botAlive === false],
  ['killswitch', (i) => i.killswitchOn === true],
];

const WARNING_LABELS: Readonly<Record<LiveWarning, string>> = {
  'heat-near-cap': 'Heat near cap', 'over-cap': 'Over cap', stale: 'Data stale',
  disconnected: 'Disconnected', 'bot-down': 'Bot down', killswitch: 'Killswitch active',
};

/** Every warning that applies, in the type's fixed order. */
export function liveWarnings(input: LiveWarningInput): LiveWarning[] {
  return WARNING_RULES.filter(([, applies]) => applies(input)).map(([warning]) => warning);
}

export function warningLabel(warning: LiveWarning): string {
  return WARNING_LABELS[warning];
}

/** 'Data stale 12 min' / '… 5h' / '… 2d'; plain 'Data stale' with no time. */
function staleText(lastSuccess: string | null, now: Date): string {
  const at = lastSuccess ? Date.parse(lastSuccess) : Number.NaN;
  if (Number.isNaN(at)) return 'Data stale';
  const minutes = Math.floor(Math.max(0, now.getTime() - at) / MINUTE_MS);
  if (minutes < 60) return `Data stale ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `Data stale ${hours}h` : `Data stale ${Math.floor(hours / 24)}d`;
}

type AlarmInput = Omit<LiveWarningInput, 'utilisationPct' | 'killswitchOn'>;
const ALARM_RULES: readonly (readonly [AlarmKind, (i: AlarmInput) => boolean, (i: AlarmInput) => string])[] = [
  ['bot-down', (i) => i.botAlive === false, () => 'Bot down'],
  ['disconnected', (i) => disconnected(i.streamState), () => 'Disconnected'],
  ['stale', staleAfterHealth, (i) => staleText(i.lastSuccess, i.now)],
];

/** The top bar's alarm (spec v202 §3): only while it applies, else null. */
export function alarmFor(input: AlarmInput): Alarm | null {
  const rule = ALARM_RULES.find(([, applies]) => applies(input));
  return rule ? { kind: rule[0], text: rule[2](input) } : null;
}

const percent = (value: number) => `${Number(value.toFixed(1))}%`;

/** 'Heat 2,010 € · 4.2% / 6%', plus ' · Over cap' above 100 %; 'Heat —' when unknown.
 *  Money goes through the app's `amount()` (ui/format.ts), unit after the figure. */
export function heatStripText(heat: LiveHeat | null, currency: string): string {
  if (heat?.availability !== 'ok' || heat.open_amount === null || heat.open_pct === null || heat.cap_pct === null) {
    return `Heat ${ABSENT}`;
  }
  const text = `Heat ${amount(heat.open_amount, currency, 0)} · ${percent(heat.open_pct)} / ${percent(heat.cap_pct)}`;
  return heatTone(heat.utilisation_pct) === 'over' ? `${text} · Over cap` : text;
}

/** '14:32 · 6m ago': Berlin local time and the freshness chip's age wording. */
export function liveTime(iso: string | null, now: Date): string {
  const age = scanAge(iso, now.getTime());
  return age === null ? ABSENT : `${timeInZone(iso, BERLIN)} · ${age}`;
}

/* -- the dock's open/collapsed preference (spec v202 §4, D4) ------------- */

export const DOCK_PREF_KEY = 'shell.dock';
export const DOCK_DEFAULT_OPEN: ReadonlySet<string> = new Set(['/dashboard', '/risk']);

export function dockDefaultOpen(destination: string | null): boolean {
  return destination !== null && DOCK_DEFAULT_OPEN.has(destination);
}

function dockMap(prefs: Preferences): Record<string, unknown> {
  const raw = prefs[DOCK_PREF_KEY];
  return raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
}

/** The stored choice for one destination; anything but a boolean is the fallback. */
export function readDockOpen(prefs: Preferences, destination: string, fallback: boolean): boolean {
  const stored = dockMap(prefs)[destination];
  return typeof stored === 'boolean' ? stored : fallback;
}

/** A new preferences object with this destination's choice set. */
export function writeDockOpen(prefs: Preferences, destination: string, open: boolean): Preferences {
  return { ...prefs, [DOCK_PREF_KEY]: { ...dockMap(prefs), [destination]: open } };
}
```

(`timeInZone` and `scanAge` both reject an empty or unparseable time, so `liveTime` checks once through `scanAge`.)


- [ ] **Step 5: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-state.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/freshness.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. If `ui/freshness.spec.ts` does not exist, skip that line: its behaviour is unchanged. If the Berlin expectations are off by an hour, the machine lacks ICU time-zone data. Node ships full ICU by default, so check `node -p "new Date('2026-07-01T07:00:00Z').toLocaleTimeString('en-GB', { timeZone: 'Europe/Berlin' })"` (it should print `09:00:00`) before touching the code.

Complexity: `heatStripText` 6, `staleText` 4, `heatTone` 4, `isStale` 3, and every other function at most 2.

Layout: no UI in this task. The surfaces that word these states are checked at three widths in V203-7, V203-8 and V203-9.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-state.ts frontend/src/app/shell/live/live-state.spec.ts frontend/src/app/ui/freshness.ts
git -C <wt> commit -m "feat(v203): live-state rules, worded once

Warnings in a fixed order; the top-bar alarm (bot down > disconnected >
stale, on the one 900 s rule now exported from ui/freshness.ts); heat
tone (amber from 80 %, Over cap above 100 %, unclamped); strip heat;
Berlin times with the freshness chip's age; and the shell.dock
preference map keyed by destination, with a per-page default.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

