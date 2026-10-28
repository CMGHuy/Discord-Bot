# v195 — Graphite, Part 7c: the page template

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-21:" -A 400 <this file>`.

**Scope of this part (V195-21):** split from Part 7 for the 1500-line cap, unchanged. V195-21 adds `sb-page`, the five-slot template every workspace route moves onto in Phase 5 (V195-22..V195-33), and with it the page's single `<h1>` (correction 9). It runs after V195-20 (Part 7b; the spec's phases are sequential), and touches no file another Phase 3 task edits.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave.** Part 7's "The state earlier tasks leave" list binds this task. What it relies on: `RouteTitleService` (`routing/route-title.service.ts`, V195-15: `title()`, `subtitle()`, `detail()`, `set(title, subtitle, path = null)`, `setDetail(detail)`; the router's title strategy fills `title`/`subtitle` from each route's `title` and `data.subtitle`, and every workspace route in `app.routes.ts` has both); `focusWorkspaceHeading(doc)` (`shell/route-focus.ts`, unchanged: focuses `.workspace h1` with `tabindex="-1"`); the shell renders no `<h1>` since V195-16, so until a page renders `sb-page` route focus finds nothing, as on most routes before v195; `ConfirmDialog` with `dangerVariant` and `Button` with `danger` / `danger-quiet` (V195-8; the button's host class is its variant); `installDialogPolyfill` (`testing/dialog-polyfill.ts`). `workspace-consistency.spec.ts` bans `<h1` in workspace sources; `sb-page` lives in `ui/`, which that scan never reads.

---

# Phase 4 — Page template

### Task V195-21: `sb-page` template: header (one `<h1>`, description, `[page-actions]`), `[page-scope]`, `[page-kpis]`, `[page-primary]`, `[page-secondary]` (2 columns at `lg`); empty slots take no space
**Model:** sonnet — one presentational component with content projection and its spec; the care is in empty slots collapsing without a gap, the title falling back to the route's, and the header's actions slot being the one home for a destructive control.

**Files:**
- Create: `frontend/src/app/ui/page.ts`
- Create: `frontend/src/app/ui/page.spec.ts`
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` (a minimal `sb-page` wrapper, Step 3b; V195-33 replaces it)

**Interfaces:**
- Consumes: `RouteTitleService.title(): string`, `RouteTitleService.subtitle(): string | null` (`routing/route-title.service.ts`); `focusWorkspaceHeading` (`shell/route-focus.ts`, spec only); `ConfirmDialog` (`sb-confirm-dialog`: `open`, `title`, `consequence`, `confirmLabel`, `dangerVariant`, outputs `confirmed`, `cancelled`), `Button` (`button[sb-button]`, `variant`) and `installDialogPolyfill` (spec only).
- Produces (every Phase 5 task, V195-22..V195-33, consumes these):
  - `Page` (`sb-page`, `ui/page.ts`): `heading = input<string | null>(null)` (empty or null falls back to `RouteTitleService.title()`); `description = input<string | null>(null)` (null falls back to `RouteTitleService.subtitle()`; no description element when both are empty).
  - Markup, in this order: `header.bar` > `div.heading` (`h1.title`, optional `p.description`) + `div.actions.slot` (`<ng-content select="[page-actions]">`); `div.scope.slot` (`[page-scope]`); `div.kpis.slot` (`[page-kpis]`); `div.primary.slot` (`[page-primary]`); `div.secondary.slot` (`[page-secondary]`, a grid: one column, two from 1440px); then a default `<ng-content />` for anything with no slot attribute (confirm dialogs, drawers), which renders after the secondary grid.
  - Host: a flex column with `gap: var(--space-14)`; `.slot:empty { display: none; }`, so an empty slot takes no space and adds no gap.
  - Usage rule Phase 5 follows: a slot's content is one element carrying the slot attribute (`<sb-toolbar page-scope …>`, `<div page-kpis>…</div>`, `<sb-panel page-primary …>`, one `<sb-panel page-secondary …>` per secondary panel). A conditional slot wraps its `@if` inside that element rather than putting the attribute on an element inside an `@if`, so the slot stays one stable node. Destructive controls go only in `[page-actions]`, each opening `sb-confirm-dialog` (projected through the default slot): the killswitch as `variant="danger"` with `dangerVariant="danger"`, everything else as `danger-quiet`.

**What changes, and what is already there.** Spec Phase 4: every workspace route renders the same five-slot frame. Today each workspace lays itself out by hand, and since V195-16 the page title is in no heading at all (the shell's `<h1>` went with the old top bar; the breadcrumb is a `nav` list, correction 9). `sb-page` puts the title back as the page's single `<h1>` inside `.workspace`, where `route-focus.ts` already looks, so keyboard focus lands on it after every navigation once a route is on `sb-page`. The title and the one-line description default to the route's own `title` and `data.subtitle` (the same strings the breadcrumb and `document.title` use), so most pages pass nothing; a page that wants different words passes `heading` / `description`. The header's right side is the actions slot and the only place a destructive control may sit (spec Phase 4); the scope bar holds filters and tabs only. The secondary grid is two columns from `lg` (1440px, `BREAKPOINTS.lg`) and one below. No workspace uses it yet: Phase 5 moves them, one task per workspace group, and V195-33 makes `workspace-consistency.spec.ts` assert every route entry does. The component carries no surface, border or shadow of its own; the panels inside it do.

- [ ] **Step 1: Write the failing tests**

Create `$WT/frontend/src/app/ui/page.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, Type, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { RouteTitleService } from '../routing/route-title.service';
import { focusWorkspaceHeading } from '../shell/route-focus';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { Button } from './button';
import { ConfirmDialog } from './confirm-dialog';
import { Page } from './page';

@Component({
  imports: [Page],
  template: `
    <sb-page>
      <span page-actions class="probe-action">Export</span>
      <div page-scope class="probe-scope">Scope</div>
      <div page-kpis class="probe-kpis">KPIs</div>
      <div page-primary class="probe-primary">Primary</div>
      <div page-secondary class="probe-secondary">A</div>
      <div page-secondary class="probe-secondary">B</div>
    </sb-page>
  `,
})
class EverySlot {}

@Component({
  imports: [Page],
  template: `
    <sb-page heading="Risk" description="Open exposure against the cap">
      <div page-primary class="probe-primary">Heat</div>
    </sb-page>
  `,
})
class PrimaryOnly {}

@Component({ imports: [Page], template: `<sb-page />` })
class RouteTitled {}

@Component({
  imports: [Page],
  template: `<main class="workspace"><sb-page><div page-primary>Table</div></sb-page></main>`,
})
class InWorkspace {}

@Component({
  imports: [Page, Button, ConfirmDialog],
  template: `
    <sb-page heading="System">
      <button sb-button variant="danger-quiet" type="button" page-actions class="restart" (click)="asking.set(true)">
        Restart bot
      </button>
      <div page-primary>Logs</div>
      <sb-confirm-dialog
        [open]="asking()"
        title="Restart the bot?"
        consequence="Scans stop until it is back."
        confirmLabel="Restart"
        dangerVariant="danger-quiet"
        (confirmed)="onConfirmed()"
        (cancelled)="asking.set(false)"
      />
    </sb-page>
  `,
})
class WithDestructive {
  readonly asking = signal(false);
  confirmed = 0;
  onConfirmed(): void {
    this.confirmed += 1;
    this.asking.set(false);
  }
}

const pageSource = () => readFileSync(join(process.cwd(), 'src/app/ui/page.ts'), 'utf8');

describe('sb-page (v195 Phase 4)', () => {
  beforeAll(() => installDialogPolyfill());

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  async function render<T>(host: Type<T>): Promise<{ fixture: ComponentFixture<T>; el: HTMLElement }> {
    const fixture = TestBed.createComponent(host);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it("renders the page's one h1 from the route title, and the route subtitle as its description", async () => {
    TestBed.inject(RouteTitleService).set('Risk', 'Open exposure against the cap');
    const { el } = await render(RouteTitled);
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('header.bar .heading h1.title')!.textContent!.trim()).toBe('Risk');
    expect(el.querySelector('.description')!.textContent!.trim()).toBe('Open exposure against the cap');
  });

  it('lets the heading and description inputs win over the route', async () => {
    TestBed.inject(RouteTitleService).set('Something else', 'Another line');
    const { el } = await render(PrimaryOnly);
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('Risk');
    expect(el.querySelector('.description')!.textContent!.trim()).toBe('Open exposure against the cap');
  });

  it('renders no description element when there is none', async () => {
    TestBed.inject(RouteTitleService).set('Versions', null);
    const { el } = await render(RouteTitled);
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('Versions');
    expect(el.querySelector('.description')).toBeNull();
  });

  it('follows the route title when it changes', async () => {
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Trades', null);
    const { fixture, el } = await render(RouteTitled);
    titles.set('Calendar', 'Every trading day');
    fixture.detectChanges();
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('Calendar');
  });

  it('projects each slot into its own region, in the spec order', async () => {
    const { el } = await render(EverySlot);
    const page = el.querySelector('sb-page')!;
    expect([...page.children].map((child) => child.classList[0])).toEqual(['bar', 'scope', 'kpis', 'primary', 'secondary']);
    expect(page.querySelector('header.bar > .actions > .probe-action')).not.toBeNull();
    expect(page.querySelector('.scope > .probe-scope')).not.toBeNull();
    expect(page.querySelector('.kpis > .probe-kpis')).not.toBeNull();
    expect(page.querySelector('.primary > .probe-primary')).not.toBeNull();
    expect(page.querySelectorAll('.secondary > .probe-secondary')).toHaveLength(2);
  });

  it('takes no space for an empty slot', async () => {
    const { el } = await render(PrimaryOnly);
    const page = el.querySelector('sb-page')!;
    for (const name of ['actions', 'scope', 'kpis', 'secondary']) {
      expect(page.querySelector(`.${name}`)!.matches(':empty'), name).toBe(true);
    }
    expect(page.querySelector('.primary')!.matches(':empty')).toBe(false);
    expect(pageSource()).toContain('.slot:empty { display: none; }');
  });

  it('lays the secondary grid out in two columns from lg (1440px) and one below', () => {
    const source = pageSource();
    expect(source).toMatch(/\.secondary \{[^}]*grid-template-columns: minmax\(0, 1fr\);/);
    expect(source).toMatch(/@media \(min-width: 1440px\) \{\s*\.secondary \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  });

  it('keeps a destructive action in the header and opens the confirm dialog from it', async () => {
    const { fixture, el } = await render(WithDestructive);
    const restart = el.querySelector<HTMLButtonElement>('sb-page header.bar .actions button.restart')!;
    expect(restart.classList).toContain('danger-quiet');
    const dialog = el.querySelector('dialog')!;
    expect(dialog.hasAttribute('open')).toBe(false);

    restart.click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(dialog.hasAttribute('open')).toBe(true);
    const confirm = [...dialog.querySelectorAll<HTMLButtonElement>('button')]
      .find((button) => button.textContent!.trim() === 'Restart')!;
    expect(confirm.classList).toContain('danger-quiet');

    confirm.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.confirmed).toBe(1);
  });

  it('projects anything without a slot after the grid, so dialogs need no slot of their own', async () => {
    const { el } = await render(WithDestructive);
    const page = el.querySelector('sb-page')!;
    expect(page.lastElementChild!.tagName.toLowerCase()).toBe('sb-confirm-dialog');
  });

  it('is the heading route focus lands on inside the workspace', async () => {
    TestBed.inject(RouteTitleService).set('Trades', null);
    const { el } = await render(InWorkspace);
    focusWorkspaceHeading(document);
    const heading = el.querySelector('sb-page h1')!;
    expect(document.activeElement).toBe(heading);
    expect(heading.getAttribute('tabindex')).toBe('-1');
  });

  it('paints no surface of its own: the panels inside it do', () => {
    const styles = pageSource().slice(pageSource().indexOf('styles:'));
    expect(styles).not.toMatch(/background|box-shadow|border:/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/page.spec.ts
```

Expected: FAIL. The spec does not compile: `./page` does not exist.

- [ ] **Step 3: Create `page.ts`**

Create `$WT/frontend/src/app/ui/page.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { RouteTitleService } from '../routing/route-title.service';

/**
 * The page template every workspace route renders -- v195 Phase 4.
 *
 * Five slots, in this order, each optional:
 *
 * 1. Header: the page's one `<h1>` and a one-line description on the left,
 *    `[page-actions]` on the right. The actions slot is the only home for a
 *    destructive control (killswitch, restart, stop, clear, discard, delete),
 *    and each opens `sb-confirm-dialog`: the killswitch as `danger`,
 *    everything else as `danger-quiet`.
 * 2. `[page-scope]`: filters and scope only (horizon, side, dates, tabs).
 * 3. `[page-kpis]`: the headline figures, one KPI strip.
 * 4. `[page-primary]`: the main table or chart, full width.
 * 5. `[page-secondary]`: the rest, two columns from lg (1440px), one below.
 *
 * Anything without a slot attribute (a confirm dialog, a drawer) is
 * projected last. An empty slot is `:empty` and hidden, so it takes no space
 * and adds no gap. Give a slot one element carrying its attribute; put a
 * conditional inside that element rather than the attribute inside an
 * `@if`.
 *
 * The `<h1>` is the page's only heading of that rank (correction 9): the
 * shell renders none, and `route-focus.ts` moves focus to `.workspace h1`
 * after each navigation, which is this one. Its words default to the
 * route's `title` and `data.subtitle`, the strings the breadcrumb and
 * `document.title` already use; `heading` / `description` override them.
 *
 * No surface of its own: panels inside it carry the surface and border.
 */
@Component({
  selector: 'sb-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="bar">
      <div class="heading">
        <h1 class="title">{{ headingText() }}</h1>
        @if (descriptionText(); as text) {
          <p class="description">{{ text }}</p>
        }
      </div>
      <div class="actions slot"><ng-content select="[page-actions]" /></div>
    </header>
    <div class="scope slot"><ng-content select="[page-scope]" /></div>
    <div class="kpis slot"><ng-content select="[page-kpis]" /></div>
    <div class="primary slot"><ng-content select="[page-primary]" /></div>
    <div class="secondary slot"><ng-content select="[page-secondary]" /></div>
    <ng-content />
  `,
  styles: `
    :host { display: flex; flex-direction: column; gap: var(--space-14); min-width: 0; }
    .slot:empty { display: none; }
    .bar {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--space-10) var(--space-14);
    }
    .heading { flex: 1 1 280px; min-width: 0; }
    .title { margin: 0; color: var(--text); font-size: var(--text-title); font-weight: 600; line-height: 1.25; }
    .description { margin: var(--space-4) 0 0; max-width: min(65ch, 100%); color: var(--text-muted); font-size: var(--text-body); }
    .actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--space-8); }
    .scope, .kpis, .primary { min-width: 0; }
    .secondary { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); }
    @media (min-width: 1440px) {
      .secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  `,
})
export class Page {
  /** Overrides the route title; empty or null falls back to it. */
  readonly heading = input<string | null>(null);
  /** Overrides the route subtitle; null falls back to it. */
  readonly description = input<string | null>(null);

  private readonly titles = inject(RouteTitleService);

  protected readonly headingText = computed(() => this.heading() || this.titles.title());
  protected readonly descriptionText = computed(() => this.description() ?? this.titles.subtitle());
}
```

- [ ] **Step 3b: Give the gallery a minimal `sb-page` wrapper**

`gallery.spec.ts`'s `the gallery shows every primitive` generates one `renders <selector>` case from every `selector: 'sb-…'` under `ui/`, so `ui/page.ts` adds `renders sb-page`, which fails until `gallery.ts` contains `<sb-page`. V195-33 lays the gallery out on the full template; until then it gets the smallest wrapper that keeps that case green and the page at one `<h1>`. In `$WT/frontend/src/app/workspaces/gallery/gallery.ts`:

1. Add `import { Page } from '../../ui/page';` beside the other `../../ui/` imports, and `Page,` to the `@Component` `imports` array in its alphabetical place.
2. In the `template`, replace the line `    <h1>UI gallery</h1>` with `    <sb-page>` followed by `      <div page-primary>`, and directly before the line `` `, `` that closes the `template` (the first line in the file that is exactly two spaces, a backtick and a comma) add `      </div>` and `    </sb-page>`. Everything between keeps its text; do not re-indent it (a whitespace-only diff hides the real change). The heading now comes from the route title, `UI gallery`, through `sb-page`'s `h1.title`.

No other edit: the gallery's host padding and every section stay as they are. V195-33 says to replace exactly this wrapper.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/page.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/text-styles.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `gallery.spec.ts` finds `<sb-page` (Step 3b) and every other primitive as before. `breakpoint-guard.spec.ts` accepts the one width query (1440 is on its list). `workspace-consistency.spec.ts` is unchanged and green: `page.ts` is in `ui/`, which its no-`<h1` scan never reads. If the empty-slot case finds a slot not `:empty`, a whitespace text node got between the wrapper and its `ng-content`: keep each wrapper and its `ng-content` on one line, as above. If the destructive case finds the dialog closed after the click, the polyfill is missing: `beforeAll(() => installDialogPolyfill())` must run before the first render. If the confirm button lacks `danger-quiet`, V195-8's `dangerVariant` binding is not in `confirm-dialog.ts`: that is V195-8's defect, fix it there, not here.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 5: Close**

Close: standard (test: `frontend/src/app/ui/page.spec.ts`). No browser pass in this task: nothing renders `sb-page` until Phase 5, and each Phase 5 task checks its own page at 390, 768 and 1440. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/page.ts frontend/src/app/ui/page.spec.ts frontend/src/app/workspaces/gallery/gallery.ts
git -C "$WT" commit -m "feat(v195): sb-page template with the page's one h1 (V195-21)" -m "Spec Phase 4 and correction 9: sb-page renders a header (the page's single h1 and a one-line description, defaulting to the route's title and subtitle, with a [page-actions] slot on the right, the only home for destructive controls), then [page-scope], [page-kpis], [page-primary] and [page-secondary] (two columns from 1440px). An empty slot takes no space; anything without a slot (dialogs, drawers) is projected last. route-focus.ts finds the h1 inside .workspace, so focus lands on it after navigation once a route is on the template (Phase 5)." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```
