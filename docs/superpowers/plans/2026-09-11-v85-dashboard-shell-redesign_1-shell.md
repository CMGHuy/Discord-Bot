# v85 Part 1 — Shell

Header block, global constraints, parallelisation and exit criteria live in
`2026-09-11-v85-dashboard-shell-redesign_0-index.md`. Read that first; this
file carries only the tasks.

Part 1 is a **chain**, not a group: R1-05 through R1-12 all edit
`shell.html` / `shell.css` / `shell.ts`. Run them in order, one at a time.

---

# Phase 1 — Foundations

### Task R1-01: Restore the chrome-devtools MCP connection

**Files:**
- Modify: `.mcp.json` (only if the diagnosis points there)
- Create: none

**Interfaces:**
- Consumes: nothing.
- Produces: a working `chrome-devtools` MCP server, so every later task can be
  visually verified. No code symbol.

This task is diagnosis, not construction. It has no unit test — its
verification is that the tools appear and respond.

- [ ] **Step 1: Reproduce the failure and capture the reason**

The session reported `MCP server plugin:chrome-devtools-mcp:chrome-devtools
connection timed out after 30000ms`. Find out why before changing anything:

```bash
claude mcp list
```

Note which servers report connected and which time out.

- [ ] **Step 2: Check the three things that actually cause this**

```bash
node --version && npx --version
npx -y chrome-devtools-mcp@latest --version
ls "/c/Program Files/Google/Chrome/Application/chrome.exe"
```

In order, these test: that `npx` can run at all; that the package downloads and
starts (a cold `npx` fetch is the single most common cause of a 30s timeout on
first use — the download exceeds the handshake budget); and that Chrome is
where the server expects it.

- [ ] **Step 3: Apply the fix the diagnosis indicates**

If the cold fetch was the cause, the package is now cached and the server will
connect on the next start — no file change. If Chrome is elsewhere, add its
path to the server's args in `.mcp.json`. Do **not** paste a speculative config
change if step 2 passed cleanly; find the real cause first.

- [ ] **Step 4: Verify the connection**

Restart the session, then:

```bash
claude mcp list
```

Expected: `chrome-devtools` listed as connected. Then confirm a tool actually
responds by taking one screenshot of any page.

- [ ] **Step 5: Commit (only if a file changed)**

```bash
git add .mcp.json
git commit -m "fix(mcp): point chrome-devtools at the installed Chrome"
```

If nothing changed, record in the task notes that the cold `npx` fetch was the
cause and move on — there is nothing to commit.

---

### Task R1-02: Add the hero type token

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Test: `frontend/src/app/ui/tokens.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `--text-hero`, a display size above `--text-metric`, consumed by
  R4-01's Portfolio Value figure.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/ui/tokens.spec.ts`, following the assertions already
in that file:

```ts
it('offers a hero size above the primary metric size', () => {
  const style = getComputedStyle(document.documentElement);
  const hero = style.getPropertyValue('--text-hero').trim();
  expect(hero).not.toBe('');
  // Same calc(px * var(--text-scale)) shape as every other size token, so
  // the zoom control reaches it too.
  expect(hero).toContain('var(--text-scale)');
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/ui/tokens.spec.ts
```

Expected: FAIL — `--text-hero` resolves to `''`.

- [ ] **Step 3: Add the token**

In `frontend/src/styles/tokens.css`, beside `--text-metric`:

```css
  --text-hero: calc(44px * var(--text-scale));      /* v85: portfolio figure */
```

44px, not the mockup's measured size: `--text-metric` is 28px and the hero
figure must dominate it without leaving the type scale. It multiplies through
`--text-scale` like every other size token, so the zoom control still reaches
it — a hero number that ignored zoom would be the one figure on the page a
low-vision user could not enlarge.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/ui/tokens.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts
git commit -m "feat(ui): add --text-hero for the portfolio figure"
```

---

### Task R1-03: Add the icons this redesign needs

**Files:**
- Modify: `frontend/src/app/ui/icon.ts`
- Test: `frontend/src/app/ui/icon.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: four new `IconName` values — `'clock'`, `'more'`, `'opened'`,
  `'closed'` — consumed by R1-07 (clock), R5-05 (row menu) and R4-04 (activity
  feed).

- [ ] **Step 1: Write the failing test**

```ts
it('carries the icons the v85 chrome and feed need', () => {
  for (const name of ['clock', 'more', 'opened', 'closed'] as const) {
    expect(ICON_NAMES).toContain(name);
  }
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/ui/icon.spec.ts
```

Expected: FAIL — `ICON_NAMES` does not contain `'clock'`.

- [ ] **Step 3: Add the four paths**

In `frontend/src/app/ui/icon.ts`, add the names to `ICON_NAMES` and the paths
to `PATHS`. Stroke-only on the same 16×16 grid at 1.5 width as the rest of the
set — no fills, no second style:

```ts
  // A dial with two hands: the wall clock in the top bar.
  clock: 'M8 14.5A6.5 6.5 0 1 0 8 1.5a6.5 6.5 0 0 0 0 13z M8 4.5V8l2.5 1.5',
  // Three dots: the row overflow menu.
  more: 'M3.5 8h.01 M8 8h.01 M12.5 8h.01',
  // An arrow leaving a baseline: a position opening.
  opened: 'M2 13.5h12 M8 11V3 M5 6l3-3 3 3',
  // An arrow arriving at a baseline: a position closing.
  closed: 'M2 13.5h12 M8 3v8 M5 8l3 3 3-3',
```

`more` uses three 0.01-length segments rather than circles because the shared
`<svg>` is stroke-only with `stroke-linecap="round"` — a zero-length round-cap
segment renders as a dot, so three dots cost no fill rule and no second style.
Verify the cap attribute is present on the `<svg>` in this file before relying
on it; if it is not, use three `M…a` circles instead.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/ui/icon.spec.ts
```

Expected: PASS. Then open `/ui` in the dev server and confirm all four render
as shapes rather than as empty boxes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts
git commit -m "feat(ui): add clock, more, opened and closed icons"
```

---

### Task R1-04: Route titles and subtitles

**Files:**
- Create: `frontend/src/app/routing/route-title.service.ts`
- Create: `frontend/src/app/routing/route-title.service.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`
- Modify: `frontend/src/app/app.config.ts` (register the title strategy)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `RouteTitleService` with `readonly title: Signal<string>` and
    `readonly subtitle: Signal<string | null>`.
  - `SubtitleTitleStrategy extends TitleStrategy`, registered in
    `app.config.ts`, which updates both signals and still sets `document.title`.
  - `data: { subtitle: string }` on every workspace route.

  R1-05 renders both signals in the top bar; R1-11 removes the in-page
  headings they replace.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/routing/route-title.service.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, TitleStrategy, provideRouter } from '@angular/router';
import { describe, expect, it, beforeEach } from 'vitest';

import { RouteTitleService, SubtitleTitleStrategy } from './route-title.service';

class Blank {}

describe('route title service', () => {
  let router: Router;
  let titles: RouteTitleService;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([
          { path: 'dashboard', component: Blank, title: 'Dashboard',
            data: { subtitle: "What's happening right now" } },
          { path: 'versions', component: Blank, title: 'Versions',
            data: { subtitle: "What's deployed, and when it changed" } },
          { path: 'bare', component: Blank, title: 'Bare' },
        ]),
        { provide: TitleStrategy, useClass: SubtitleTitleStrategy },
      ],
    });
    router = TestBed.inject(Router);
    titles = TestBed.inject(RouteTitleService);
  });

  it('publishes the active route title and subtitle', async () => {
    await router.navigateByUrl('/dashboard');
    expect(titles.title()).toBe('Dashboard');
    expect(titles.subtitle()).toBe("What's happening right now");
  });

  it('updates both on navigation', async () => {
    await router.navigateByUrl('/dashboard');
    await router.navigateByUrl('/versions');
    expect(titles.title()).toBe('Versions');
    expect(titles.subtitle()).toBe("What's deployed, and when it changed");
  });

  it('clears the subtitle on a route that has none, rather than keeping the last', async () => {
    await router.navigateByUrl('/dashboard');
    await router.navigateByUrl('/bare');
    expect(titles.title()).toBe('Bare');
    expect(titles.subtitle()).toBeNull();
  });
});
```

The third case is the one that matters: a stale subtitle under a new title is
a caption describing the wrong page, which is worse than no caption.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/routing/route-title.service.spec.ts
```

Expected: FAIL — cannot resolve `./route-title.service`.

- [ ] **Step 3: Write the service and strategy**

Create `frontend/src/app/routing/route-title.service.ts`:

```ts
import { Injectable, Signal, inject, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import {
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
  TitleStrategy,
} from '@angular/router';

/**
 * The active route's title and subtitle, as signals — v85 D4.
 *
 * The shell's top bar renders these; workspaces no longer render a heading of
 * their own. One page, one title, and it lives where the design puts it.
 */
@Injectable({ providedIn: 'root' })
export class RouteTitleService {
  private readonly _title = signal('');
  private readonly _subtitle = signal<string | null>(null);

  readonly title: Signal<string> = this._title.asReadonly();
  readonly subtitle: Signal<string | null> = this._subtitle.asReadonly();

  set(title: string, subtitle: string | null): void {
    this._title.set(title);
    this._subtitle.set(subtitle);
  }
}

/** Reads `title` the way Angular already does, and `data.subtitle` from the
 *  deepest activated route that defines one. Still sets `document.title`:
 *  this replaces the default strategy rather than sitting beside it. */
@Injectable({ providedIn: 'root' })
export class SubtitleTitleStrategy extends TitleStrategy {
  private readonly document = inject(Title);
  private readonly titles = inject(RouteTitleService);

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const title = this.buildTitle(snapshot) ?? '';
    this.titles.set(title, subtitleOf(snapshot.root));
    if (title) this.document.setTitle(title);
  }
}

/** The deepest defined subtitle, or null. Walks the whole firstChild chain
 *  rather than reading the root: with `loadChildren`, the route carrying the
 *  data may be either the parent entry or the lazy child. */
function subtitleOf(route: ActivatedRouteSnapshot): string | null {
  let found: string | null = null;
  for (let node: ActivatedRouteSnapshot | null = route; node; node = node.firstChild) {
    const value = node.data['subtitle'];
    if (typeof value === 'string') found = value;
  }
  return found;
}
```

- [ ] **Step 4: Register it and fill in the route data**

In `frontend/src/app/app.config.ts`, add to the providers array:

```ts
  { provide: TitleStrategy, useClass: SubtitleTitleStrategy },
```

In `frontend/src/app/app.routes.ts`, add `title` and `data.subtitle` to each
workspace route. Copy exactly — this is the approved copy from spec D4:

```ts
  { path: 'dashboard',        title: 'Dashboard',     data: { subtitle: "What's happening right now" },      /* …existing keys… */ },
  { path: 'trades',           title: 'Trades',        data: { subtitle: 'Every plan, filled or not' },       /* … */ },
  { path: 'trades/:id',       title: 'Trade detail',  data: { subtitle: 'One position, end to end' },        /* … */ },
  { path: 'analytics',        title: 'Analytics',     data: { subtitle: 'What already happened, measured' }, /* … */ },
  { path: 'calendar',         title: 'Calendar',      data: { subtitle: 'P&L by day' },                      /* … */ },
  { path: 'watchlist',        title: 'Watchlist',     data: { subtitle: 'The symbols being scanned' },       /* … */ },
  { path: 'watchlist/:symbol',title: 'Ticker detail', data: { subtitle: 'One symbol, in depth' },            /* … */ },
  { path: 'risk',             title: 'Risk',          data: { subtitle: 'Exposure, caps and the killswitch' },/* … */ },
  { path: 'system',           title: 'System',        data: { subtitle: 'What the bot itself is doing' },    /* … */ },
  { path: 'versions',         title: 'Versions',      data: { subtitle: "What's deployed, and when it changed" }, /* … */ },
  { path: 'ui',               title: 'UI gallery',    data: { subtitle: 'Every primitive, in one place' },   /* … */ },
```

Keep each route's existing `canMatch` and `loadChildren`/`loadComponent` keys —
these are additions, not replacements.

- [ ] **Step 5: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/routing/route-title.service.spec.ts
```

Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/routing/route-title.service.ts \
        frontend/src/app/routing/route-title.service.spec.ts \
        frontend/src/app/app.routes.ts frontend/src/app/app.config.ts
git commit -m "feat(shell): publish route title and subtitle as signals"
```

---

# Phase 2 — The top bar

### Task R1-05: Put the title and subtitle in the top bar

**Files:**
- Modify: `frontend/src/app/shell/shell.html:108-153` (the `<header class="topbar">` block)
- Modify: `frontend/src/app/shell/shell.ts` (inject `RouteTitleService`)
- Modify: `frontend/src/app/shell/shell.css`
- Test: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: `RouteTitleService.title` / `.subtitle` from R1-04.
- Produces: `.topbar .page-title` and `.topbar .page-subtitle` elements, and
  the `.topbar-lead` / `.topbar-status` layout slots that R1-06 and R1-07 fill.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/shell/shell.spec.ts`, inside the existing describe
(the module setup there already provides router, http and the event stream):

```ts
it('renders the route title and subtitle in the top bar', () => {
  const titles = TestBed.inject(RouteTitleService);
  titles.set('Dashboard', "What's happening right now");
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  expect(el.querySelector('.topbar .page-title')?.textContent?.trim()).toBe('Dashboard');
  expect(el.querySelector('.topbar .page-subtitle')?.textContent?.trim())
    .toBe("What's happening right now");
});

it('renders no subtitle element at all when the route has none', () => {
  TestBed.inject(RouteTitleService).set('Bare', null);
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  expect((f.nativeElement as HTMLElement).querySelector('.page-subtitle')).toBeNull();
});
```

Add `import { RouteTitleService } from '../routing/route-title.service';` to
the spec's imports.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL — `.page-title` is null.

- [ ] **Step 3: Render them**

In `shell.ts`, add the injection beside the other `inject()` calls:

```ts
  protected readonly titles = inject(RouteTitleService);
```

In `shell.html`, at the top of the `<header class="topbar">` block, before the
killswitch span:

```html
      <div class="topbar-lead">
        <h1 class="page-title">{{ titles.title() }}</h1>
        @if (titles.subtitle(); as subtitle) {
          <p class="page-subtitle">{{ subtitle }}</p>
        }
      </div>
```

`@if` rather than a class toggle: an empty `<p>` still occupies its line-height
and pushes the title off the bar's optical centre on routes with no subtitle.

In `shell.css`, add:

```css
.topbar-lead { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.page-title {
  margin: 0;
  font-size: var(--text-title);
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.page-subtitle {
  margin: 0;
  font-size: var(--text-chip);
  color: var(--text-secondary);
  white-space: nowrap;
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts \
        frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): render the route title and subtitle in the top bar"
```

---

### Task R1-06: Move both ticker lanes into the top bar row

**Files:**
- Modify: `frontend/src/app/shell/shell.html:155-160`
- Modify: `frontend/src/app/shell/shell.css`
- Modify: `frontend/src/app/shell/tape/tape.css`
- Test: `frontend/src/app/shell/shell.spec.ts:85-92` (an existing assertion changes)

**Interfaces:**
- Consumes: `.topbar-lead` from R1-05.
- Produces: the lanes as children of `header.topbar`. `.main`'s child order
  becomes `['header', 'main']`.

**This task changes an existing passing test.** `places both lanes between the
topbar and the workspace` asserts the old structure. That assertion is not a
casualty to delete — it is the thing being deliberately changed, so it gets
rewritten to assert the new contract.

- [ ] **Step 1: Rewrite the existing structural test**

Replace the body of `places both lanes between the topbar and the workspace`
in `shell.spec.ts` with:

```ts
it('carries both lanes inside the top bar row, not beneath it', () => {
  const fixture = TestBed.createComponent(Shell);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;

  const main = el.querySelector('.main') as HTMLElement;
  expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
    .toEqual(['header', 'main']);

  const header = el.querySelector('header.topbar') as HTMLElement;
  expect(header.querySelector('sb-market-lane')).not.toBeNull();
  expect(header.querySelector('sb-names-lane')).not.toBeNull();
});
```

Rename the test as shown — a test whose name describes the old layout is a
worse lie than no test.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL — `.main` still has four children and the header has no lanes.

- [ ] **Step 3: Move them**

In `shell.html`, delete the two standalone lane elements between `</header>`
and `<main class="workspace">`, and place them inside the header, between the
lead block and the status cluster:

```html
        <div class="topbar-tape">
          <sb-market-lane />
          <sb-names-lane />
        </div>
```

In `shell.css`:

```css
.topbar {
  display: flex;
  align-items: center;
  gap: var(--space-14);
}
/* The tape takes the slack and is the only thing allowed to scroll: a
   min-width of 0 on a flex child is what lets it shrink below its content
   instead of pushing the status cluster off the end of the bar. */
.topbar-tape {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-10);
  overflow-x: auto;
  scrollbar-width: none;
}
.topbar-tape::-webkit-scrollbar { display: none; }
```

In `tape.css`, the lanes were sized as full-width strips. Remove any
`width: 100%` and any block-level vertical padding on the lane hosts so they
sit as inline chip rows inside the bar; keep their per-chip styling.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS. Then look at it: `cd frontend && npm start`, open
`http://localhost:4200/dashboard`, and confirm the bar is one row with the
tape between the title and the status cluster, and that narrowing the window
scrolls the tape rather than pushing the avatar off-screen.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css \
        frontend/src/app/shell/tape/tape.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): merge both ticker lanes into the top bar row"
```

---

### Task R1-07: Clock and date in the status cluster

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (the status cluster)
- Modify: `frontend/src/app/shell/shell.ts`
- Modify: `frontend/src/app/shell/shell.css`
- Test: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: `CLOCK` from `ui/clock.ts`; `'clock'` icon from R1-03.
- Produces: `.topbar .clock` showing `Thu, Sep 11, 2026 16:58`.

**Reuse `CLOCK`; do not add an interval.** `CLOCK_INTERVAL_MS` is already
30_000, which is ample for a minute-resolution display, and the token is
overridable in tests — a private `setInterval` in the shell would tick a
second timer for no gain and leave it running in vitest.

- [ ] **Step 1: Write the failing test**

```ts
it('shows the date and time from the ambient clock', () => {
  // A fixed instant, so the assertion is not a function of when the suite runs.
  const fixed = new Date('2026-09-11T16:58:00').getTime();
  TestBed.overrideProvider(CLOCK, { useValue: signal(fixed) });
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const text = (f.nativeElement as HTMLElement).querySelector('.clock')?.textContent ?? '';
  expect(text).toContain('Sep 11, 2026');
  expect(text).toContain('16:58');
});
```

Add `import { CLOCK } from '../ui/clock';` to the spec.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL — `.clock` is null.

- [ ] **Step 3: Implement it**

In `shell.ts`:

```ts
  private readonly clock = inject(CLOCK);

  /** `Thu, Sep 11, 2026 16:58` — one string, so the bar cannot render a date
   *  and a time from two different reads of the clock. 24-hour and
   *  zero-padded via hourCycle: the bar is a monitoring surface and 4:58
   *  next to a 16:58 market close reads as an error. */
  protected readonly now = computed(() => {
    const at = new Date(this.clock());
    const date = at.toLocaleDateString(undefined, {
      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
    });
    const time = at.toLocaleTimeString(undefined, {
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    });
    return `${date} ${time}`;
  });
```

In `shell.html`, in the status cluster beside the market pill:

```html
      <span class="clock">
        <sb-icon name="clock" />
        {{ now() }}
      </span>
```

In `shell.css`:

```css
.clock {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
  color: var(--text-secondary);
  font-size: var(--text-chip);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
```

`tabular-nums` so the bar does not twitch as the minute digits change width.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts \
        frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): show the date and time in the top bar"
```

---

### Task R1-08: Move the zoom control into the profile menu

**Files:**
- Modify: `frontend/src/app/shell/profile-menu.ts`
- Modify: `frontend/src/app/shell/shell.html` (remove the `.zoom` button, bind the menu)
- Test: `frontend/src/app/shell/profile-menu.spec.ts`
- Test: `frontend/src/app/shell/shell.spec.ts:143-155` (the existing zoom test moves)

**Interfaces:**
- Consumes: `Shell.zoom()` and `Shell.cycleZoom()`, both already present in
  `shell.ts:172-205`.
- Produces: `ProfileMenu.zoom` (an `input<number>`) and
  `ProfileMenu.zoomCycled` (an `output<void>`).

The cycling logic does not move — `ZOOM_CHOICES`, `cycleZoom()` and the
`PreferencesStore` write all stay in `shell.ts`. Only the button moves.

- [ ] **Step 1: Write the failing test**

In `frontend/src/app/shell/profile-menu.spec.ts`:

```ts
it('offers the text-size control inside the menu and emits on click', () => {
  const f = TestBed.createComponent(ProfileMenu);
  f.componentRef.setInput('zoom', 110);
  f.detectChanges();

  const el = f.nativeElement as HTMLElement;
  // Closed, the control is not in the DOM at all.
  expect(el.querySelector('.zoom')).toBeNull();

  el.querySelector<HTMLButtonElement>('.avatar')!.click();
  f.detectChanges();

  const zoom = el.querySelector<HTMLButtonElement>('.zoom')!;
  expect(zoom.textContent?.trim()).toBe('Aa 110%');

  let cycled = 0;
  f.componentInstance.zoomCycled.subscribe(() => (cycled += 1));
  zoom.click();
  expect(cycled).toBe(1);
});
```

Then move the shell's existing `cycles the text-size button…` test out of
`shell.spec.ts`: the shell no longer renders `.zoom`, so assert the same
cycling through the menu instead — open the menu, click, and check the label
walks 100 → 110 → 125 → 90.

- [ ] **Step 2: Run both and watch them fail**

```bash
cd frontend && npx ng test --include src/app/shell/profile-menu.spec.ts
```

Expected: FAIL — no `.zoom` in the menu.

- [ ] **Step 3: Add the control to the menu**

In `profile-menu.ts`, add to the class:

```ts
  readonly zoom = input<number>(100);
  readonly zoomCycled = output<void>();
```

and to the template, inside the `@if (open())` menu block, above Sign out:

```html
        <button sb-button variant="ghost" type="button" role="menuitem"
                class="zoom"
                [attr.aria-label]="'Text size ' + zoom() + '%. Click to change.'"
                (click)="zoomCycled.emit()">
          <sb-icon name="expand" />
          <span>Aa {{ zoom() }}%</span>
        </button>
```

Add `input` and `output` to the `@angular/core` import list.

In `shell.html`, delete the `.zoom` button from the topbar and bind the menu:

```html
      <sb-profile-menu [zoom]="zoom()" (zoomCycled)="cycleZoom()" (signedOut)="logout()" />
```

The menu deliberately stays open after a click: cycling is a compare-and-repeat
action, and a menu that closed on each step would need reopening three times to
reach 125%.

- [ ] **Step 4: Run both and watch them pass**

```bash
cd frontend && npx ng test --include src/app/shell/profile-menu.spec.ts
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS for both.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/profile-menu.spec.ts \
        frontend/src/app/shell/shell.html frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): move the text-size control into the profile menu"
```

---

### Task R1-09: Killswitch as a full-width strip

**Files:**
- Modify: `frontend/src/app/shell/shell.html:108-114`
- Modify: `frontend/src/app/shell/shell.css`
- Test: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: `Shell.killswitchOn()`, already present.
- Produces: `.killswitch-strip` as a sibling *below* `header.topbar`, inside
  `.main`. `.main`'s child order becomes `['header', 'div', 'main']` when
  engaged and `['header', 'main']` when not.

- [ ] **Step 1: Write the failing test**

```ts
it('renders the killswitch as a full-width strip below the bar, only when engaged', () => {
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  expect(el.querySelector('.killswitch-strip')).toBeNull();

  // killswitchOn is a protected signal set from the risk endpoint; drive it
  // the way the component does rather than reaching into the instance.
  (f.componentInstance as unknown as { killswitchOn: WritableSignal<boolean> })
    .killswitchOn.set(true);
  f.detectChanges();

  const strip = el.querySelector('.killswitch-strip')!;
  expect(strip.getAttribute('role')).toBe('alert');
  expect(strip.textContent).toContain('KILLSWITCH ENGAGED');
  expect(strip.parentElement?.classList.contains('main')).toBe(true);
  expect(strip.previousElementSibling?.tagName.toLowerCase()).toBe('header');
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL — no `.killswitch-strip`.

- [ ] **Step 3: Move it out of the bar**

In `shell.html`, delete the `killswitch` span from inside `<header>`, and add
immediately after `</header>`:

```html
    @if (killswitchOn()) {
      <div class="killswitch-strip" role="alert">KILLSWITCH ENGAGED</div>
    }
```

In `shell.css`, replace the old `.killswitch` rule with:

```css
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
```

Out of the bar and into its own strip because the bar is now full: competing
for width with the tape is how an alert ends up truncated, and this is the one
message on the page that must never be.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css \
        frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): move the killswitch alert to a full-width strip"
```

---

# Phase 3 — Nav and responsive

### Task R1-10: Restyle the left nav

**Files:**
- Modify: `frontend/src/app/shell/shell.css`
- Modify: `frontend/src/app/shell/shell.html:11-99` (classes only)
- Test: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: no new symbols. The nav's structure, routes, grouping and version
  block are unchanged — this is presentation only.

**Do not touch `navGroups` in `shell.ts`.** The eight routes and the three
group labels are D1, and two existing tests assert them.

This task also restyles the sidebar `.mark` block — the avatar, the `swingbot`
wordmark and the `paper` tag. **Correction (recorded during implementation):**
this paragraph previously claimed the name stays `swingbot`/`paper` under D3,
which directly contradicted D3 as written in the design spec ("Branding is
adopted... The PWA manifest and document titles follow the same name") and
R1-14's own test asserting a `Bomeo` wordmark. Asked the human partner to
resolve the contradiction rather than picking a side silently: the spec's D3
is authoritative — the wordmark, tagline and manifest name change to the
mockup's "Bomeo Capital" branding. R1-14 owns that change; this task
restyles only the `.mark` block's layout/spacing, not its text.

- [ ] **Step 1: Write the failing test**

```ts
it('marks the active entry with an accent rail rather than colour alone', () => {
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const link = (f.nativeElement as HTMLElement).querySelector('.nav a')!;
  link.classList.add('active');
  f.detectChanges();
  // The rule must exist in the component stylesheet; colour alone fails
  // contrast guidance for state, which is why this asserts a border.
  const styles = [...document.styleSheets]
    .flatMap((sheet) => { try { return [...sheet.cssRules]; } catch { return []; } })
    .map((rule) => rule.cssText);
  expect(styles.some((text) => text.includes('.nav a.active') && text.includes('border-left')))
    .toBe(true);
});

it('keeps the version block pinned to the foot of the rail', () => {
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const foot = (f.nativeElement as HTMLElement).querySelector('.sidebar-foot');
  expect(foot).not.toBeNull();
  expect(foot?.parentElement?.classList.contains('sidebar')).toBe(true);
});
```

The second test is a guard, not a feature: the version block is the one thing
D1 says must survive this restyle, and a CSS pass is exactly where it would
get lost.

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL on the first test — no `border-left` rule for `.nav a.active`.

- [ ] **Step 3: Restyle**

In `shell.css`, update the nav rules:

```css
.nav a {
  display: flex;
  align-items: center;
  gap: var(--space-10);
  padding: var(--space-8) var(--space-12);
  border-left: 2px solid transparent;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--text-secondary);
  font-size: var(--text-body);
  text-decoration: none;
}
.nav a:hover { background: var(--surface-raised); color: var(--text); }
.nav a.active {
  border-left-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
  font-weight: 600;
}
.nav-group-label {
  margin: var(--space-14) 0 var(--space-4) var(--space-12);
  color: var(--text-faint);
  font-size: var(--text-micro);
  letter-spacing: 0.12em;
}
```

An accent rail plus a background tint plus weight — three cues, not colour
alone, so the active entry survives a monochrome or low-vision reading.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS, including the two pre-existing grouping tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/shell.css frontend/src/app/shell/shell.html \
        frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): restyle the nav rail to the v85 language"
```

---

### Task R1-11: Remove the in-page headings the top bar now owns

**Files:**
- Modify: one line each in the eight workspace components —
  `workspaces/dashboard/dashboard.ts:111`, and the equivalent
  `<sb-section-head heading="…">` in `trades/`, `analytics/`, `calendar/`,
  `watchlist/`, `risk/`, `system/`, `versions/`
- Test: the affected workspace specs

**Interfaces:**
- Consumes: R1-04's title mechanism (the title now renders in the bar).
- Produces: nothing. This removes duplication.

**Remove only the `heading` attribute, never the `sb-section-head` element**
where it also projects actions — several workspaces project controls into it
(the Dashboard projects its scope toggle), and deleting the element would drop
those controls on the floor.

- [ ] **Step 1: Find every occurrence**

```bash
git grep -n "sb-section-head" -- frontend/src/app/workspaces
```

Expect one per workspace. Note which also have projected content.

- [ ] **Step 2: Write the failing test**

Pick the Dashboard as the representative and add to
`frontend/src/app/workspaces/dashboard/dashboard.spec.ts`:

```ts
it('renders no in-page heading, because the top bar owns the title', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  expect(el.textContent).not.toContain('Dashboard');
});
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL — the heading still renders the word.

- [ ] **Step 4: Strip the heading attribute in all eight**

For a workspace with projected actions, drop the attribute and keep the
element:

```html
    <sb-section-head>
      <sb-control-row actions class="scope" role="group" aria-label="Date scope">
```

For one with a bare heading and nothing projected, delete the element and its
import.

- [ ] **Step 5: Run the eight specs and watch them pass**

```bash
cd frontend && npx ng test --include "src/app/workspaces/**/*.spec.ts"
```

Expected: PASS. Any spec asserting its own heading text needs the same
treatment as the Dashboard's — update the assertion, do not delete the test.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces
git commit -m "refactor(workspaces): drop in-page headings now owned by the top bar"
```

---

### Task R1-12: Responsive rules for the merged bar

**Files:**
- Modify: `frontend/src/app/shell/shell.css`
- Test: `frontend/src/app/shell/shell.css` is asserted through
  `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: every element R1-05 … R1-09 added.
- Produces: nothing new. This is the drop order from the spec's Responsive
  section made real.

- [ ] **Step 1: Write the failing test**

```ts
it('drops the subtitle and the clock before it lets the bar overflow', () => {
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const rules = [...document.styleSheets]
    .flatMap((sheet) => { try { return [...sheet.cssRules]; } catch { return []; } })
    .map((rule) => rule.cssText)
    .join('\n');
  // Both must be hidden under a max-width query -- the order in the spec is
  // subtitle first, then clock, so the subtitle's breakpoint is the wider one.
  expect(rules).toMatch(/max-width:\s*900px[\s\S]*\.page-subtitle[\s\S]*display:\s*none/);
  expect(rules).toMatch(/max-width:\s*720px[\s\S]*\.clock[\s\S]*display:\s*none/);
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL — neither media query exists.

- [ ] **Step 3: Add the drop order**

At the foot of `shell.css`:

```css
/* The drop order, widest trigger first — spec v85 "Responsive behaviour".
   Everything here is a removal: the bar never wraps to a second row, because
   a two-row bar changes the height of every page's content area. */
@media (max-width: 900px) {
  .page-subtitle { display: none; }
}
@media (max-width: 720px) {
  .clock { display: none; }
  .topbar { gap: var(--space-10); }
}
```

The title itself already truncates with an ellipsis (R1-05) and the tape
already scrolls (R1-06), so below 720px the bar degrades to
mark · title · scrolling tape · status, with nothing overflowing.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Verify it in a browser at three widths**

With `npm start` running, use chrome-devtools (R1-01) to screenshot
`/dashboard` at 1440px, 900px and 390px. Confirm: no horizontal page scroll at
any width, the avatar is reachable at all three, and the tape scrolls rather
than pushing anything off the end.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(shell): define the top bar's responsive drop order"
```

---

# Phase 4 — Sheet 2 reconciliation

Two tasks added when the second mockup sheet arrived. Both are amendments to
the shell this part has already built, not rebuilds of it.

### Task R1-13: The status cluster reads "Live · clock", sheet 2's form

**Files:**
- Modify: `frontend/src/app/shell/connection-status.ts`
- Modify: `frontend/src/app/shell/shell.html`
- Modify: `frontend/src/app/shell/shell.css`
- Test: `frontend/src/app/shell/connection-status.spec.ts`

**Interfaces:**
- Consumes: the merged top bar from R1-05/R1-06, the clock from R1-07.
- Produces: nothing new. Presentation and copy only.

**What is actually different.** Sheet 1 shows a "MARKETS LIVE" pill. Sheet 2
shows a small dot labelled "Live" immediately before the clock. The market lane
already renders named index labels with value and signed change
(`INDEX_LABELS` in `shell/tape/market-lane.ts`), so the tape itself needs
nothing. The change is the status cluster: dot, word, clock, in that order, as
one group.

**The dot means one thing** — spec D30. It reports that the event stream is
connected. It must never be read as "these numbers are current"; that claim
belongs to each panel's own `sb-freshness` (R2-06).

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/shell/connection-status.spec.ts`:

```typescript
it('labels the dot Live when the stream is connected', () => {
  const el = render({ connected: true });
  expect(el.querySelector('.state')!.textContent!.trim()).toBe('Live');
});

it('says what is live, not that the data is fresh', () => {
  const el = render({ connected: true });
  expect(el.getAttribute('title')).toContain('event stream');
  expect(el.getAttribute('title')).not.toContain('up to date');
});

it('names the disconnected state in words, not by colour alone', () => {
  const el = render({ connected: false });
  expect(el.querySelector('.state')!.textContent!.trim()).toBe('Offline');
});
```

If `render` does not exist in that spec, write it to match the existing
helpers there rather than inventing a second style.

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/shell/connection-status.spec.ts
```

Expected: FAIL on the three new assertions.

- [ ] **Step 3: Make the change**

In `connection-status.ts`, render the dot followed by a `.state` word, and set
the host `title` to `Event stream connected` / `Event stream disconnected —
panels show their own data age`. In `shell.html`, place the component
immediately before the clock inside the status cluster. In `shell.css`, group
the two with `display: flex; align-items: center; gap: var(--gap);`.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/shell/connection-status.spec.ts
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: both PASS.

- [ ] **Step 5: Screenshot the bar**

With `npm start` running, screenshot `/dashboard` at 1440px and 390px. Confirm
the cluster reads dot → Live → clock, and that at 390px the clock drops before
the dot does (R1-12's drop order).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/connection-status.ts frontend/src/app/shell/connection-status.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css
git commit -m "feat(shell): status cluster reads Live then clock (v85 D2)"
```

---

### Task R1-14: The brand mark, wordmark and rail tagline

**Files:**
- Modify: `frontend/src/app/ui/icon.ts`
- Modify: `frontend/src/app/shell/shell.html`
- Modify: `frontend/src/app/shell/shell.css`
- Modify: `frontend/public/manifest.webmanifest`
- Test: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: the icon registry from R1-03.
- Produces: icon name `brand` in `ui/icon.ts`, available to any component.

**Do not ship `images/logo.png`** — spec D3 and finding 16. It is a
photorealistic brushed-metal serif monogram on a white ground: it cannot take
the accent colour, will not read at 24px on `--bg`, and has no collapsed-rail
form. The mark is authored as a path on the existing 16×16 grid at 1.5 stroke
width, like every other icon in the registry, and inherits `currentColor`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/shell/shell.spec.ts`:

```typescript
it('renders the brand mark beside the wordmark', () => {
  const el = render();
  expect(el.querySelector('.brand sb-icon')).not.toBeNull();
  expect(el.querySelector('.brand')!.textContent).toContain('Bomeo');
});

it('renders the two-tone wordmark as two spans, not one coloured string', () => {
  expect(render().querySelectorAll('.brand .word span').length).toBe(2);
});

it('renders the rail tagline', () => {
  expect(render().querySelector('.rail-tagline')!.textContent)
    .toContain('Trade smarter. Build further.');
});

it('keeps the mark and drops the words when the rail is collapsed', () => {
  const el = render({ collapsed: true });
  expect(el.querySelector('.brand sb-icon')).not.toBeNull();
  expect(el.querySelector('.brand .word')).toBeNull();
});
```

Use the spec's existing `render` helper and its existing way of driving the
collapsed rail; do not add a second mechanism.

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
```

Expected: FAIL on the four new assertions.

- [ ] **Step 3: Add the icon**

In `ui/icon.ts`, add a `brand` entry to the registry alongside the existing
ones, authored on the same 16×16 viewBox at `stroke-width="1.5"` with
`stroke="currentColor"` and `fill="none"`. Keep it to two or three path
commands — at 24px, detail is noise.

- [ ] **Step 4: Render the wordmark and tagline**

In `shell.html`, the brand block is the mark, then
`<span class="word"><span>Bomeo</span><span>Capital</span></span>`; the second
span takes `--accent`. Below the nav list, add
`<p class="rail-tagline">Trade smarter. Build further.</p>`. In `shell.css`,
hide `.word` and `.rail-tagline` in the collapsed-rail state — the mark stays.

- [ ] **Step 5: Update the manifest**

In `frontend/public/manifest.webmanifest`, set `name` and `short_name` to match
the wordmark. Leave the icons as they are; replacing them is not this task.

- [ ] **Step 6: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/shell/shell.spec.ts
cd frontend && npx ng test --include src/app/ui/icon.spec.ts
```

Expected: both PASS.

- [ ] **Step 7: Screenshot both rail states**

Screenshot `/dashboard` at 1440px with the rail expanded and collapsed.
Confirm the mark reads at rail size, the two-tone wordmark is legible, and the
tagline sits above the version block rather than displacing it.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/icon.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/public/manifest.webmanifest
git commit -m "feat(shell): brand mark, two-tone wordmark and rail tagline (v85 D3)"
```
