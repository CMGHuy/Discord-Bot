# v241 — Doctena night, plan 2 of 5: Icons — Part 1: the icon set

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V241-2" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §4 and its `### Corrections from the plan 2 code brief (2026-11-23)` (which wins over earlier text and the mockups).
**Index:** [2026-11-23-v241-doctena-night-icons_0-index.md](2026-11-23-v241-doctena-night-icons_0-index.md) — Goal, Architecture, Decisions, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly includes its Global Constraints.

This part: V241-1..V241-4 — the 24-grid `sb-icon` with `size` and filled sub-paths, the redraw of all 27 names, the nine new names and the gallery, sizes per surface, and the direction arrows.

Verification in every task is the narrow run, from `frontend/`:
`npx ng test --watch=false --include <spec>` (a 60s `Timeout waiting for worker` is machine load: re-run once). No task runs the full suite; CI does.

**Template note (applies to V241-3 and every later caller):** `frontend/tsconfig.json` has `strictTemplates: true` and `size` is typed `IconSize = 16 | 20 | 24`, so a caller writes `[size]="24"` (a number binding). A static `size="24"` is the string `'24'` and fails the template type check.

# Phase 1 — the component and the set

### Task V241-1: `sb-icon` on the 24 grid: filled sub-paths, 1.8 stroke, all 27 names redrawn

**Model:** sonnet — one component and its spec, but 27 path strings to copy exactly and a pinned path in a second spec to move with them.

**Files:**
- Modify: `frontend/src/app/ui/icon.ts` (header comment l.3-20, `PATHS` l.53-125, the component l.139-180; `ICON_NAMES`, `LABELS` and `STATUS_ICON` unchanged)
- Modify: `frontend/src/app/ui/icon.spec.ts` (rewritten whole below)
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts` (l.61 and l.69-70 pin the old 16-grid `partial` and `opened` path data; **not in the index ledger row**, see the controller note at the end of this task)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `const FILLS: Partial<Record<IconName, string>>` with `pending`, `opened`, `partial` (module-private); the svg renders a second `<path class="fill" fill="currentColor" stroke="none">` after the stroked path when the name has a fill. `ICON_NAMES` keeps its 27 names in order (V241-2 appends nine). The svg still renders at a fixed 16px (`width="16" height="16"`) until V241-1b adds `size` (this task was split from V241-1 at the 20 KB cap).

**Why each drawing:** spec §4's table. `analytics` is the bulb with a rising line (not mockup 4's bars), stroke is 1.8 at every size (not mockup 4's 2.0), no `grip` (spec correction). Path data is copied verbatim from the brief §6 table.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `frontend/src/app/ui/icon.spec.ts` with:

```ts
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ICON_NAMES, Icon, IconName } from './icon';

function render(name: string) {
  const f = TestBed.createComponent(Icon);
  f.componentRef.setInput('name', name as IconName);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

/** The absolute coordinates every `M` command moves to, in order. */
function moveTargets(d: string): number[] {
  return [...d.matchAll(/M\s*(-?[\d.]+)[\s,]+(-?[\d.]+)/g)].flatMap((m) => [Number(m[1]), Number(m[2])]);
}

/** The names that carry a filled sub-path (spec §4: Pending's sand,
 *  Opened's broadcast source, Partial's banked half). */
const FILLED: readonly IconName[] = ['pending', 'opened', 'partial'];

describe('Icon', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it.each([...ICON_NAMES])('renders an svg for %s', (name) => {
    expect(render(name).querySelector('svg')).not.toBeNull();
  });

  it.each([...ICON_NAMES])('draws %s on the 24 grid at a 1.8 round stroke', (name) => {
    const svg = render(name).querySelector('svg')!;
    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    expect(svg.getAttribute('stroke-width')).toBe('1.8');
    expect(svg.getAttribute('stroke-linecap')).toBe('round');
    expect(svg.getAttribute('stroke-linejoin')).toBe('round');
    // Every move target sits inside the 24 box: a path left on the old 16
    // grid would still pass this, which is why the drawings below are pinned.
    for (const value of moveTargets(svg.querySelector('path')!.getAttribute('d')!)) {
      expect(value, name).toBeGreaterThanOrEqual(0);
      expect(value, name).toBeLessThanOrEqual(24);
    }
  });

  it.each([...ICON_NAMES])('names %s when the caller gives no title', (name) => {
    // No icon is mute: the default tooltip is the label.
    expect(render(name).getAttribute('title')!.length, name).toBeGreaterThan(0);
  });

  it.each([...FILLED])('draws the filled part of %s as a second, solid path', (name) => {
    const paths = render(name).querySelectorAll('svg path');
    expect(paths).toHaveLength(2);
    const fill = paths[1];
    expect(fill.classList).toContain('fill');
    expect(fill.getAttribute('fill')).toBe('currentColor');
    expect(fill.getAttribute('stroke')).toBe('none');
    expect(paths[0].classList).not.toContain('fill');
  });

  it('draws every other name as one stroked path', () => {
    for (const name of ICON_NAMES.filter((n) => !FILLED.includes(n))) {
      expect(render(name).querySelectorAll('svg path'), name).toHaveLength(1);
    }
  });

  it('banks the right half of the partial circle', () => {
    const paths = render('partial').querySelectorAll('svg path');
    expect(paths[0].getAttribute('d')).toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z');
    expect(paths[1].getAttribute('d')).toBe('M12 3a9 9 0 0 1 0 18z');
  });

  it('has a path for the calendar icon', () => {
    expect(ICON_NAMES).toContain('calendar');
  });

  it('renders nothing for an unknown name, and does not throw', () => {
    // A missing icon should leave a gap, not take the screen down with it.
    expect(() => render('not-an-icon')).not.toThrow();
    expect(render('not-an-icon').querySelector('svg')).toBeNull();
  });

  it('inherits its colour from the control it sits in', () => {
    // currentColor is what lets one sprite serve an active nav entry, a
    // hovered one and a disabled one without three copies of the path data.
    const svg = render('trades').querySelector('svg')!;
    expect(svg.getAttribute('stroke')).toBe('currentColor');
    expect(svg.getAttribute('fill')).toBe('none');
  });

  it('is hidden from assistive tech', () => {
    // The label always lives on the parent control. An icon that announces
    // itself as well produces "Trades Trades" on every nav entry.
    expect(render('trades').querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('covers every name the shell needs', () => {
    for (const needed of ['dashboard', 'trades', 'analytics', 'watchlist', 'risk',
                          'system', 'collapse', 'expand', 'profile', 'signout', 'menu', 'search']) {
      expect(ICON_NAMES, `missing icon: ${needed}`).toContain(needed);
    }
  });

  it('keeps every existing name in its place (callers reach the redraw untouched)', () => {
    expect(ICON_NAMES.slice(0, 27)).toEqual([
      'dashboard', 'trades', 'analytics', 'calendar', 'watchlist', 'risk', 'system', 'versions',
      'collapse', 'expand', 'profile', 'signout', 'menu', 'trash', 'clock', 'more', 'opened',
      'closed', 'pending', 'partial', 'cancelled', 'trailing', 'brand', 'reports', 'research',
      'search', 'theme',
    ]);
  });

  it('draws the destinations as what they mean (spec §4)', () => {
    const d = (name: string) => render(name).querySelector('svg path')!.getAttribute('d');
    // A gauge with a needle, not the old 2x2 grid of panels.
    expect(d('dashboard')).toBe('M3.5 17a8.5 8.5 0 0 1 17 0 M12 8.5V10 M6.6 10.6l1 1 M17.4 10.6l-1 1 M12 17l3.6-4.6 M3.5 20h17');
    // Binoculars, not an eye (an eye reads as show/hide).
    expect(d('watchlist')).toMatch(/^M6\.5 19\.5a3\.5 3\.5 0 1 0 0-7/);
    // The light bulb with a rising line: the spec's drawing, not mockup 4's bars.
    expect(d('analytics')).toContain('M9.5 10.5l1.7-1.7 1.6 1.6 1.9-2');
    // A shield with a percent sign.
    expect(d('risk')).toContain('M9.3 15.2l5.4-6.4');
    // A monitor with a pulse line, not a gear.
    expect(d('system')).toBe('M3 4h18v12H3z M8 20h8 M12 16v4 M5.5 10h3l1.5-3 2 6 1.5-3h5');
    // A finish flag: neutral for winners and losers.
    expect(d('closed')).toBe('M5 21V4 M5 4h13l-2.5 4L18 12H5');
  });

  it('renders the trash icon', () => {
    expect(ICON_NAMES).toContain('trash');
  });

  it('carries the icons the v85 chrome and feed need', () => {
    for (const name of ['clock', 'more', 'opened', 'closed'] as const) {
      expect(ICON_NAMES).toContain(name);
    }
  });

  it('renders the brand icon (R1-14)', () => {
    expect(ICON_NAMES).toContain('brand');
  });

  it('carries the search glyph the top bar and the phone bar use (v195 correction 1)', () => {
    expect(ICON_NAMES).toContain('search');
    expect(render('search').querySelector('svg path')).not.toBeNull();
    // Named by its default label when the caller gives none.
    expect(render('search').getAttribute('title')).toBe('Search');
  });

  it('draws the theme toggle as a crescent moon (v240: both themes are dark)', () => {
    expect(ICON_NAMES).toContain('theme');
    const path = render('theme').querySelector('svg path')!;
    expect(path.getAttribute('d')).toBe('M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z');
    expect(render('theme').getAttribute('title')).toBe('Theme');
  });

  it('never draws two names with the same glyph -- an icon-only rail reads by shape', () => {
    const glyphs = new Map<string, string>();
    for (const name of ICON_NAMES) {
      const d = render(name).querySelector('svg path')!.getAttribute('d')!;
      expect(glyphs.get(d), `${name} draws the same glyph as ${glyphs.get(d)}`).toBeUndefined();
      glyphs.set(d, name);
    }
  });
});
```

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`, the two path pins move to the 24-grid drawings (the first `<path>` is still the stroked one; the filled sub-path comes second). Replace

```ts
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe('M8 14.5A6.5 6.5 0 1 0 8 1.5a6.5 6.5 0 0 0 0 13z M8 1.5v13');
```

with

```ts
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z');
```

and replace

```ts
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe(
      'M8 13.5A5.5 5.5 0 1 0 8 2.5a5.5 5.5 0 0 0 0 11z M8 8.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z',
    );
```

with

```ts
    const path = el.querySelector('sb-icon path')!;
    expect(path.getAttribute('d')).toBe(
      'M8.2 15.8a5.4 5.4 0 0 1 0-7.6 M15.8 8.2a5.4 5.4 0 0 1 0 7.6 M5.4 18.6a9.3 9.3 0 0 1 0-13.2 M18.6 5.4a9.3 9.3 0 0 1 0 13.2',
    );
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts`
Expected: FAIL — the 24-grid, fill, drawing and crescent tests fail on the 16-grid output, and recent-activity's two path pins fail.

- [ ] **Step 3: Redraw the set and render the fills**

In `frontend/src/app/ui/icon.ts`, replace the header comment (the `/** The icon set — spec v18 Decision 8. ... */` block above `ICON_NAMES`) with:

```ts
/**
 * The icon set — spec v18 Decision 8, redrawn by v240 §4 (doctena night).
 *
 * **Hand-authored, no package, no font, no CDN.** The repo's zero-third-party
 * constraint is not an aesthetic preference: an icon font is a network request
 * to somebody else's host on every page load, and an icon package is tens of
 * thousands of glyphs shipped to use a few dozen. These paths cost less than
 * the dependency's own README.
 *
 * Stroked on a 24×24 grid at 1.8 width with round caps and joins, so the whole
 * set looks like one hand.
 *
 * A few icons carry one filled sub-path (`FILLS`): Pending's sand, Opened's
 * broadcast source, Partial's banked half. The svg is `fill="none"`, so the
 * filled part is a second path with its own `fill="currentColor"`.
 *
 * `currentColor` is what lets a single definition serve an active nav entry,
 * a hovered one and a muted one without three copies of the path data.
 *
 * Always `aria-hidden`. The accessible name belongs on the control the icon
 * sits inside — a nav link that labels itself AND contains a labelled icon
 * announces "Trades Trades".
 */
```

Replace the `PATHS` constant (from `/** Path data only` through its closing `};`) with:

```ts
/** Stroked path data only — every shared attribute lives on the `<svg>` below. */
const PATHS: Record<IconName, string> = {
  // A gauge with its needle: the one-glance read of the book.
  dashboard: 'M3.5 17a8.5 8.5 0 0 1 17 0 M12 8.5V10 M6.6 10.6l1 1 M17.4 10.6l-1 1 M12 17l3.6-4.6 M3.5 20h17',
  // Two candlesticks, wicks and bodies: what the table is about.
  trades: 'M7 3v4 M7 17v4 M5 7h4v10H5z M17 3v3 M17 15v6 M15 6h4v9h-4z',
  // A light bulb with a rising line inside it: Insights, what the book teaches.
  analytics:
    'M9.5 18h5 M10.3 21h3.4 M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.1v.1h5v-.1c0-.8.4-1.6 1.1-2.1A6 6 0 0 0 12 3z M9.5 10.5l1.7-1.7 1.6 1.6 1.9-2',
  // A month grid: a header bar, two binder rings and day marks.
  calendar: 'M4 5.5h16v15H4z M4 10h16 M8.5 3v4 M15.5 3v4 M8 13.5h2 M14 13.5h2 M8 17h2',
  // Binoculars: tickers watched for a setup (an eye reads as show/hide).
  watchlist:
    'M6.5 19.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M17.5 19.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M10 16h4 M3.4 14.6 5.5 5h3.2l1 9 M20.6 14.6 18.5 5h-3.2l-1 9',
  // A shield with a percent sign: the 2% dollar-risk cap and the heat cap.
  risk:
    'M12 2.5 4.5 5.5v6c0 4.6 3.2 8.4 7.5 10 4.3-1.6 7.5-5.4 7.5-10v-6z M9.3 15.2l5.4-6.4 M9.6 10.2a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8z M14.4 15.6a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8z',
  // A monitor with a pulse line: health and versions (a gear reads as settings).
  system: 'M3 4h18v12H3z M8 20h8 M12 16v4 M5.5 10h3l1.5-3 2 6 1.5-3h5',
  // Stacked layers: two components released as one image, over and over.
  versions: 'M12 3 3 7.5l9 4.5 9-4.5z M3 12l9 4.5 9-4.5 M3 16.5 12 21l9-4.5',
  // A chevron pointing left: fold the rail or panel away.
  collapse: 'M15 6l-6 6 6 6',
  // A chevron pointing right: open it out (also a collapsed row's marker).
  expand: 'M9 6l6 6-6 6',
  // A head and shoulders.
  profile: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20.5c0-3.5 3.3-5.5 7.5-5.5s7.5 2 7.5 5.5',
  // A door with an arrow leaving it.
  signout: 'M10 4H5v16h5 M15 8l4 4-4 4 M19 12H9',
  // Three bars.
  menu: 'M4 7h16 M4 12h16 M4 17h16',
  // A bin: lid, handle, tapered body and two staves.
  trash: 'M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v5 M14 11v5',
  // A dial with two hands: the wall clock in the top bar.
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3.5 2',
  // Three dots: the row overflow menu. Zero-length strokes; the round caps
  // draw the dots.
  more: 'M5 12h.01 M12 12h.01 M19 12h.01',
  // A live-signal broadcast, two arcs each side of a solid source (FILLS):
  // the position is running. A status, not a direction.
  opened: 'M8.2 15.8a5.4 5.4 0 0 1 0-7.6 M15.8 8.2a5.4 5.4 0 0 1 0 7.6 M5.4 18.6a9.3 9.3 0 0 1 0-13.2 M18.6 5.4a9.3 9.3 0 0 1 0 13.2',
  // A finish flag on its pole: the trade ended, neutral for winners and
  // losers alike.
  closed: 'M5 21V4 M5 4h13l-2.5 4L18 12H5',
  // An hourglass with sand left in the lower bulb (FILLS): waiting for the
  // entry trigger, nothing has happened yet.
  pending: 'M6 3h12 M6 21h12 M7 3c0 4 5 5.5 5 9s-5 5-5 9 M17 3c0 4-5 5.5-5 9s5 5 5 9',
  // A circle whose right half is solid (FILLS): TP1 banked, the runner live.
  partial: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
  // A crossed-out circle: void, never filled (EXPIRED maps here too) --
  // distinct from `closed`'s flag so a plan that never filled cannot be
  // misread as one that did.
  cancelled: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8.5 8.5l7 7 M15.5 8.5l-7 7',
  // An upward stair with an arrowhead: the stop ratchets with price and
  // never gives ground, which is what a trailing stop does.
  trailing: 'M3 19h5v-5h5V9h5 M15 4.5h4.5V9',
  // A diamond: the rail's brand mark, a shape that inherits currentColor.
  brand: 'M12 2.5 21 12l-9 9.5L3 12z',
  // A page with a folded corner and ruled text lines: a document, not a
  // chart, so Reports and Insights never share a glyph.
  reports: 'M6 3h9l3 3v15H6z M15 3v3h3 M9 11h6 M9 14.5h6 M9 18h3.5',
  // A flask: experiments and their verdicts -- the strategy registry and the
  // pre-registration ledger (the magnifier belongs to `search`, v195).
  research: 'M9 3h6 M10 3v6l-5.4 9.3A1.8 1.8 0 0 0 6.2 21h11.6a1.8 1.8 0 0 0 1.6-2.7L14 9V3 M7 15h10',
  // A magnifying glass: the command palette's trigger and the phone bar's
  // search icon (v195 correction 1).
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z M15.5 15.5 20 20',
  // A crescent moon: the theme toggle (both themes are dark).
  theme: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
};

/** The solid part of an icon, drawn after its stroke with `fill="currentColor"`. */
const FILLS: Partial<Record<IconName, string>> = {
  // The sand already fallen: a small heap in the hourglass's lower bulb.
  pending: 'M9.5 18.5h5L12 16z',
  // The broadcast's source: a solid dot between the arcs.
  opened: 'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  // The banked half: the circle's right half, solid.
  partial: 'M12 3a9 9 0 0 1 0 18z',
};
```

Replace the `@Component({ selector: 'sb-icon', ... })` decorator and the `Icon` class (through the class's closing `}`) with:

```ts
@Component({
  selector: 'sb-icon',
  host: { '[attr.title]': 'tip()' },
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (path(); as d) {
      <svg
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path [attr.d]="d" />
        @if (fill(); as f) {
          <path class="fill" [attr.d]="f" fill="currentColor" stroke="none" />
        }
      </svg>
    }
  `,
  styles: `
    /* vertical-align centres an icon set inline in running text on that
       text; in a flex row (every current use) it is ignored. */
    :host { display: inline-flex; line-height: 0; vertical-align: middle; }
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
  /** Overrides the default tooltip (the icon's name). */
  readonly title = input<string | undefined>(undefined);
  protected readonly tip = computed(() => this.title() ?? LABELS[this.name()]);

  /**
   * Undefined for a name with no path, which renders nothing.
   *
   * A missing icon should leave a gap rather than take the screen down: the
   * name arrives from a nav config, and a typo there should not be fatal to
   * the shell that contains it.
   */
  protected readonly path = computed<string | undefined>(() => PATHS[this.name()]);
  /** The filled sub-path, for the few icons that have one; rendered second. */
  protected readonly fill = computed<string | undefined>(() => FILLS[this.name()]);
}
```

Leave `ICON_NAMES`, `IconName`, `LABELS` and `STATUS_ICON` exactly as they are.

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts`
Expected: PASS, 0 failed.

Then check no other spec or template pinned the old drawing or grid: `git grep -n -E "M8 14\.5A6\.5|M8 13\.5A5\.5|0 0 16 16" -- frontend/src`. Expected: hits only in `frontend/src/app/shell/voice-chip.ts` (its own hand-rolled speaker svg, Decision 5: left as is).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts
git commit -m "feat(ui): sb-icon on the 24 grid at 1.8 -- filled sub-paths, all 27 names redrawn (V241-1)"
```

**Controller note:** `recent-activity.spec.ts` pins the `partial` and `opened` path data (l.61, l.69-70), so the redraw cannot land green without it; the index ledger row for V241-1 should list it (V241-3 edits the same file afterwards, already sequential).


### Task V241-1b: `sb-icon` gains a `size` input (16, 20, 24) over the fixed 24 viewBox

**Model:** sonnet — a typed input and a template binding, small, but the type is the contract every later caller binds against.

**Files:**
- Modify: `frontend/src/app/ui/icon.ts` (the header comment's grid paragraph; a new `IconSize` type above `PATHS`; the svg's `width`/`height`; a `size` input on `Icon`)
- Modify: `frontend/src/app/ui/icon.spec.ts` (the import, `render`, two new tests)

**Interfaces:**
- Consumes: V241-1's 24-grid template (`viewBox="0 0 24 24"`, `width="16" height="16"` static) and `icon.spec.ts`'s `render(name)` helper.
- Produces: `export type IconSize = 16 | 20 | 24;` and `Icon.size = input<IconSize>(16)`; the svg's `width` and `height` attributes equal `size()`. V241-2 (gallery) and V241-3 (callers, `[size]="24"` / `[size]="20"`) consume both.

This is the `size` half of the ledger's V241-1, split off at the 20 KB task cap (`SPLIT: V241-1 -> V241-1b`); the controller adds its ledger row directly below V241-1.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/icon.spec.ts`, replace the import and the `render` helper:

```ts
import { ICON_NAMES, Icon, IconName } from './icon';

function render(name: string) {
  const f = TestBed.createComponent(Icon);
  f.componentRef.setInput('name', name as IconName);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}
```

with:

```ts
import { ICON_NAMES, Icon, IconName, IconSize } from './icon';

function render(name: string, size?: IconSize) {
  const f = TestBed.createComponent(Icon);
  f.componentRef.setInput('name', name as IconName);
  if (size !== undefined) f.componentRef.setInput('size', size);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}
```

and add these two tests directly after the `names %s when the caller gives no title` test:

```ts
  it('draws 16px by default, the size of a table cell or a line of text', () => {
    const svg = render('trades').querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('16');
    expect(svg.getAttribute('height')).toBe('16');
  });

  it.each([16, 20, 24] as const)('sets width and height to %ipx and keeps the 24 viewBox', (size) => {
    // Size is the caller's only lever: the drawing and its 1.8 stroke stay on
    // the 24 grid and scale with it, so no caller overrides the svg in CSS.
    const svg = render('trades', size).querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe(String(size));
    expect(svg.getAttribute('height')).toBe(String(size));
    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    expect(svg.getAttribute('stroke-width')).toBe('1.8');
  });

  it('follows a size change after the first render', () => {
    const f = TestBed.createComponent(Icon);
    f.componentRef.setInput('name', 'menu');
    f.detectChanges();
    f.componentRef.setInput('size', 20);
    f.detectChanges();
    const svg = (f.nativeElement as HTMLElement).querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('20');
    expect(svg.getAttribute('height')).toBe('20');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon.spec.ts`
Expected: FAIL — a type error: `Module './icon' has no exported member 'IconSize'` (and, once exported, the 20px and 24px cases and the size-change test fail on the fixed `width="16"`).

- [ ] **Step 3: Add the type, the input and the binding**

In `frontend/src/app/ui/icon.ts`, in the header comment, replace:

```ts
 * Stroked on a 24×24 grid at 1.8 width with round caps and joins, so the whole
 * set looks like one hand.
```

with:

```ts
 * Stroked on a 24×24 grid at 1.8 width with round caps and joins, so the whole
 * set looks like one hand. `size` sets only the rendered width and height
 * (16 in tables and inline text, 20 in lists, 24 in the rail and the phone tab
 * bar); the viewBox stays 24, and the stroke scales with it, so one drawing
 * serves every size. A caller picks a size; it never overrides the svg in CSS.
```

Directly above `/** Stroked path data only — every shared attribute lives on the `<svg>` below. */`, add:

```ts
/** The sizes an icon draws at: tables and inline text, lists, rail and tab bar. */
export type IconSize = 16 | 20 | 24;

```

In the `sb-icon` template, replace:

```html
        width="16"
        height="16"
```

with:

```html
        [attr.width]="size()"
        [attr.height]="size()"
```

In the `Icon` class, directly after the `title` input, add:

```ts
  /** Rendered width and height in px; the drawing stays on the 24 grid. */
  readonly size = input<IconSize>(16);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts`
Expected: PASS, 0 failed (recent-activity's callers bind no `size` yet and keep the 16 default).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts
git commit -m "feat(ui): sb-icon size input -- 16, 20 or 24px over the fixed 24 viewBox (V241-1b)"
```


### Task V241-2: Nine new names, their labels, and the full set in the gallery

**Model:** haiku — appending nine verbatim path strings, nine labels and a gallery list; every value is given below.

**Files:**
- Modify: `frontend/src/app/ui/icon.ts` (`ICON_NAMES`, `PATHS`, `LABELS`)
- Modify: `frontend/src/app/ui/icon.spec.ts` (three new tests)
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` (the icon import, the `Icons` panel in the template, two styles rules, `iconNames`, a new `iconSizes`)
- Modify: `frontend/src/app/workspaces/gallery/gallery.spec.ts` (the import of `ICON_NAMES`, one new test)

**Interfaces:**
- Consumes: V241-1's `PATHS` (24 grid) and V241-1b's `export type IconSize = 16 | 20 | 24` and `Icon.size` input.
- Produces: `IconName` gains `'info' | 'long' | 'short' | 'close' | 'edit' | 'up' | 'down' | 'plus' | 'minus'` (appended to `ICON_NAMES` in that order, 36 names). V241-4 consumes `long`/`short`; part 2 consumes `info`, `close`, `down`, `expand`, `up`, `plus`, `minus`. Gallery: `protected readonly iconNames: readonly IconName[] = ICON_NAMES;` and `protected readonly iconSizes: readonly IconSize[] = [16, 20, 24];`, rendered as one `div.icon-set` row per size.

Index Decision 7 fixes the labels; Decision 6 (and the spec correction): no `grip`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/icon.spec.ts`, add these tests directly after the `keeps every existing name in its place` test:

```ts
  it('appends the nine new names after the existing 27, in order (spec §4)', () => {
    expect(ICON_NAMES).toHaveLength(36);
    expect(ICON_NAMES.slice(27)).toEqual([
      'info', 'long', 'short', 'close', 'edit', 'up', 'down', 'plus', 'minus',
    ]);
  });

  it.each([
    ['info', 'Information'],
    ['long', 'Long'],
    ['short', 'Short'],
    ['close', 'Close'],
    ['edit', 'Edit'],
    ['up', 'Move up'],
    ['down', 'Move down'],
    ['plus', 'Add'],
    ['minus', 'Remove'],
  ] as const)('labels %s as "%s" when the caller gives no title', (name, label) => {
    expect(render(name).getAttribute('title')).toBe(label);
  });

  it('has no grip: the tab editor has no drag-reorder, so nothing should look draggable', () => {
    expect(ICON_NAMES as readonly string[]).not.toContain('grip');
  });
```

(The existing `it.each([...ICON_NAMES])` tests — an svg per name, the 24 grid at 1.8, a default title — and the unique-glyph test now cover the nine new names too.)

In `frontend/src/app/workspaces/gallery/gallery.spec.ts`, add the import below the existing `import { Hint } from '../../ui/hint';` line:

```ts
import { ICON_NAMES } from '../../ui/icon';
```

and add this test inside `describe('the gallery renders', ...)`, directly after the `mounts without throwing` test:

```ts
  it('shows the whole icon set at each of the three sizes', () => {
    // The gallery is where a redraw is reviewed by eye: every name, at the
    // table (16), list (20) and rail (24) sizes, one wrapping row each.
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const rows = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.icon-set')];
    expect(rows).toHaveLength(3);
    rows.forEach((row, index) => {
      const size = String([16, 20, 24][index]);
      const svgs = [...row.querySelectorAll('sb-icon svg')];
      expect(svgs).toHaveLength(ICON_NAMES.length);
      for (const svg of svgs) expect(svg.getAttribute('width')).toBe(size);
    });
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: FAIL — `ICON_NAMES` has 27 names, the nine label cases render no svg/title, and the gallery has no `.icon-set` rows.

- [ ] **Step 3: Add the names, paths and labels**

In `frontend/src/app/ui/icon.ts`, in `ICON_NAMES`, replace the last entry:

```ts
  'theme',
] as const;
```

with:

```ts
  'theme',
  // v240 §4: the new names, appended so every existing name keeps its place.
  'info',
  'long',
  'short',
  'close',
  'edit',
  'up',
  'down',
  'plus',
  'minus',
] as const;
```

In `PATHS`, replace the last entry:

```ts
  // A crescent moon: the theme toggle (both themes are dark).
  theme: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
};
```

with:

```ts
  // A crescent moon: the theme toggle (both themes are dark).
  theme: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
  // A circle with a lowercase i: more information (sb-hint's trigger).
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1',
  // A trend line rising to an arrowhead: a long position.
  long: 'M3 17l6-6 4 4 8-8 M15 7h6v6',
  // A trend line falling to an arrowhead: a short position.
  short: 'M3 7l6 6 4-4 8 8 M15 17h6v-6',
  // A plain cross: close a drawer, sheet or dialog (distinct from
  // `cancelled`'s crossed-out circle).
  close: 'M6 6l12 12 M18 6 6 18',
  // A pencil: edit (the tab-bar editor, v240 §6).
  edit: 'M4 20h4L19 9l-4-4L4 16z M13.5 6.5l4 4',
  // A chevron pointing up: move up, or the "now" end of a timeline.
  up: 'M6 15l6-6 6 6',
  // A chevron pointing down: move down, or an expanded panel or row.
  down: 'M6 9l6 6 6-6',
  // A plus: add.
  plus: 'M12 7v10 M7 12h10',
  // A minus: remove.
  minus: 'M7 12h10',
};
```

In `LABELS`, replace:

```ts
  reports: 'Reports', research: 'Research', search: 'Search',
  theme: 'Theme',
};
```

with:

```ts
  reports: 'Reports', research: 'Research', search: 'Search',
  theme: 'Theme',
  info: 'Information', long: 'Long', short: 'Short', close: 'Close', edit: 'Edit',
  up: 'Move up', down: 'Move down', plus: 'Add', minus: 'Remove',
};
```

- [ ] **Step 4: Show the full set in the gallery**

In `frontend/src/app/workspaces/gallery/gallery.ts`, replace the import:

```ts
import { Icon, IconName } from '../../ui/icon';
```

with:

```ts
import { ICON_NAMES, Icon, IconName, IconSize } from '../../ui/icon';
```

In the template, replace the Icons panel:

```html
    <sb-panel>
      <sb-control-row>
        @for (name of iconNames; track name) {
          <sb-icon [name]="name" />
        }
      </sb-control-row>
    </sb-panel>
```

with (a plain wrapping row, not `sb-control-row`, which stacks its children in a column below 640px and would turn 36 icons into a 36-row list on a phone):

```html
    <sb-panel>
      @for (size of iconSizes; track size) {
        <div class="icon-set">
          @for (name of iconNames; track name) {
            <sb-icon [name]="name" [size]="size" />
          }
        </div>
      }
    </sb-panel>
```

In the component's `styles`, directly after the `sb-panel { display: block; }` line, add:

```css
    /* v240 §4 -- the whole icon set, one wrapping row per size (16, 20, 24). */
    .icon-set { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-10); }
    .icon-set + .icon-set { margin-top: var(--space-14); }
```

Replace the class field:

```ts
  protected readonly iconNames: IconName[] = [
    'dashboard', 'trades', 'analytics', 'calendar', 'watchlist', 'risk',
    'system', 'versions', 'collapse', 'expand', 'profile', 'signout', 'menu', 'trash',
  ];
```

with:

```ts
  /** Every name, so a new or redrawn icon is reviewed here the day it lands. */
  protected readonly iconNames: readonly IconName[] = ICON_NAMES;
  protected readonly iconSizes: readonly IconSize[] = [16, 20, 24];
```

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/icon.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: PASS, 0 failed. (The unique-glyph test proves `partial`'s bare circle, `info`, `clock` and `cancelled` — all four start with the same circle — still differ, and that `close` differs from `cancelled`.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts
git commit -m "feat(ui): nine new icons (info, long, short, close, edit, up, down, plus, minus); gallery shows the full set at 16/20/24 (V241-2)"
```


# Phase 2 — callers

### Task V241-3: Sizes per surface: rail and tab bar 24, lists 20; the `shell.css` svg override deleted

**Model:** sonnet — five components and their specs, one CSS deletion whose pin moves to `styleRules`; mechanical but spread across the shell.

**Files:**
- Modify: `frontend/src/app/shell/shell.html` (the rail brand icon, l.9; the two rail-pill icons, l.19 and l.33)
- Modify: `frontend/src/app/shell/shell.css` (delete the `.rail-pill sb-icon svg` rule, l.89)
- Modify: `frontend/src/app/shell/shell.spec.ts` (the `sizes each entry 64x52` test's svg assertion, l.329; one new test in `describe('shell labelled rail (v202 §3)')`; one import)
- Modify: `frontend/src/app/shell/phone-tab-bar.ts` (l.38 and l.50)
- Modify: `frontend/src/app/shell/phone-tab-bar.spec.ts` (one new test)
- Modify: `frontend/src/app/shell/profile-menu.ts` (l.100 and l.135)
- Modify: `frontend/src/app/shell/profile-menu.spec.ts` (one new test)
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts` (l.39)
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts` (one new test)

Line numbers are from main before plan 1; plan 1 edits some of these files, so find each site by the quoted text.

**Interfaces:**
- Consumes: V241-1b's `Icon.size = input<IconSize>(16)` (`IconSize = 16 | 20 | 24`); plan 1 V240-6's `styleRules(name: string, source: string): StyleRule[]` and `StyleRule = { selector: string; body: string }` from `frontend/src/app/ui/testing/style-rules.ts`.
- Produces: rail brand and rail-pill icons at `[size]="24"` with no CSS override (plan 3 builds its 64px rail on this and must not restore a CSS svg override); nothing a later task in this plan consumes.

Index Decision 2: `24` on the rail pills, the rail brand and the phone tab bar; `20` on the recent-activity status icon and the profile-menu items; every other caller keeps the default `16` (the phone top-bar brand at `shell.html` l.58 included). `strictTemplates` is on, so every caller writes `[size]="24"`, never `size="24"`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/shell/shell.spec.ts`, add with the other `../ui/` imports:

```ts
import { styleRules } from '../ui/testing/style-rules';
```

In the test `it('sizes each entry 64x52, a 24px icon over a micro label', ...)`, replace:

```ts
    expect(css).toMatch(/^\.rail-pill sb-icon svg \{[^}]*width: 24px;[^}]*height: 24px;/m);
```

with:

```ts
    // The icon draws at 24 through sb-icon's size input (v240 §4); no rule
    // reaches into the svg to resize it.
    expect(styleRules('shell.css', css).filter((rule) => /sb-icon\s+svg/.test(rule.selector))).toEqual([]);
```

In `describe('shell labelled rail (v202 §3)', ...)`, add after the `draws each entry as its icon over its visible label, with no hint and no title` test:

```ts
  it('draws the brand and every destination icon at 24px through sb-icon size (v240 §4)', async () => {
    const { el } = await mount();
    const svgs = [...el.querySelectorAll(
      'nav.rail > a.rail-brand > sb-icon svg, nav.rail .rail-pill > sb-icon svg',
    )];
    // The brand plus one icon per destination.
    expect(svgs).toHaveLength(1 + NAV_ENTRIES.length);
    for (const svg of svgs) {
      expect(svg.getAttribute('width')).toBe('24');
      expect(svg.getAttribute('height')).toBe('24');
      expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    }
  });
```

In `frontend/src/app/shell/phone-tab-bar.spec.ts`, add after the `keeps every glyph out of the accessible name` test:

```ts
  it('draws each tab icon at 24px, the tab-bar size (v240 §4)', async () => {
    const { el } = await mount('/dashboard');
    const svgs = [...el.querySelectorAll('sb-icon svg')];
    expect(svgs).toHaveLength(5);
    for (const svg of svgs) {
      expect(svg.getAttribute('width')).toBe('24');
      expect(svg.getAttribute('height')).toBe('24');
    }
  });
```

In `frontend/src/app/shell/profile-menu.spec.ts`, add after the `opens on the avatar` test:

```ts
  it('draws its menu-item icons at 20px, the list size (v240 §4)', () => {
    openMenu();
    // Text size and Sign out: the two menu items that carry an icon.
    const svgs = [...el.querySelectorAll('[role=menuitem] > sb-icon svg')];
    expect(svgs).toHaveLength(2);
    for (const svg of svgs) {
      expect(svg.getAttribute('width')).toBe('20');
      expect(svg.getAttribute('height')).toBe('20');
    }
  });
```

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`, inside `describe('recent activity panel', ...)`, add after the `gives the status icon a tooltip and accessible name` test:

```ts
  it('draws the status icon at 20px, the list size (v240 §4)', () => {
    const el = render({ events: [
      { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'A', direction: null, status: 'PARTIAL', detail: '', id: '1' },
    ]});
    // The direct child of the row button: the status icon, not the
    // direction arrow's own (16px) icon.
    const svg = el.querySelector('.event-hit > sb-icon svg')!;
    expect(svg.getAttribute('width')).toBe('20');
    expect(svg.getAttribute('height')).toBe('20');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/shell/phone-tab-bar.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts`
Expected: FAIL — the svg rule is still in `shell.css`, and every new size test reads `'16'`.

- [ ] **Step 3: Set the sizes and delete the override**

In `frontend/src/app/shell/shell.html`, the rail brand (inside `<a class="rail-brand sb-hit" ...>`), replace:

```html
      <sb-icon name="brand" title="" />
    </a>
    <sb-hint [anchor]="brand" text="Bomeo Capital · Dashboard" />
```

with:

```html
      <sb-icon name="brand" title="" [size]="24" />
    </a>
    <sb-hint [anchor]="brand" text="Bomeo Capital · Dashboard" />
```

(Only that one: the phone top-bar brand inside `<a class="brand sb-hit" ...>` keeps the default 16.)

In the same file, replace both rail-pill icons (one in `rail-work`, one in `rail-foot`):

```html
<span class="rail-pill"><sb-icon [name]="entry.icon" title="" /></span>
```

with:

```html
<span class="rail-pill"><sb-icon [name]="entry.icon" title="" [size]="24" /></span>
```

In `frontend/src/app/shell/shell.css`, delete the whole rule:

```css
.rail-pill sb-icon svg { width: 24px; height: 24px; }
```

In `frontend/src/app/shell/phone-tab-bar.ts`, replace:

```html
          <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" /></span>
```

with:

```html
          <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" [size]="24" /></span>
```

and replace:

```html
        <span class="glyph" aria-hidden="true"><sb-icon name="more" /></span>
```

with:

```html
        <span class="glyph" aria-hidden="true"><sb-icon name="more" [size]="24" /></span>
```

In `frontend/src/app/shell/profile-menu.ts`, replace:

```html
          <sb-icon name="expand" />
```

with:

```html
          <sb-icon name="expand" [size]="20" />
```

and replace:

```html
          <sb-icon name="signout" />
```

with:

```html
          <sb-icon name="signout" [size]="20" />
```

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`, replace:

```html
                <sb-icon [name]="icon(event)" [title]="statusLabel(event)"
                         [attr.aria-label]="statusLabel(event)" />
```

with:

```html
                <sb-icon [name]="icon(event)" [title]="statusLabel(event)"
                         [attr.aria-label]="statusLabel(event)" [size]="20" />
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/shell/shell.spec.ts --include src/app/shell/phone-tab-bar.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts`
Expected: PASS, 0 failed.

Then confirm no CSS anywhere still resizes an icon's svg: `git grep -n -E "sb-icon\s+svg" -- frontend/src ':!*.spec.ts'`. Expected: no output.

- [ ] **Step 5: Check the three widths**

The rail exists at tablet and desktop, the tab bar on a phone. Build and look, per `docs/claude/ui-design.md` (Playwright only, `.env` admin credentials loaded inside the script, never printed): at 390px the five tab icons sit 24px over their labels inside the 56px bar; at 820px and 1440px the rail's brand diamond and six destination icons are 24px, centred in their 48×28 pills, with no clipped stroke. The profile menu (any width) shows its two item icons at 20px beside their text; the Dashboard's Recent Activity rows show the 20px status icon centred on the row.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/phone-tab-bar.ts frontend/src/app/shell/phone-tab-bar.spec.ts frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/profile-menu.spec.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts
git commit -m "feat(ui): icon sizes per surface -- rail and tab bar 24, lists 20; drop the shell.css svg override (V241-3)"
```


### Task V241-4: Direction arrows draw `long`/`short` icons

**Model:** sonnet — one primitive rendered on four surfaces; the accessible name and the colour valence exception must survive the swap, and three specs pin the old glyph text.

**Files:**
- Modify: `frontend/src/app/ui/direction-arrow.ts` (rewritten whole below)
- Modify: `frontend/src/app/ui/direction-arrow.spec.ts` (rewritten whole below)
- Modify: `frontend/src/app/ui/confidence-cell.spec.ts` (the two arrow tests, l.58-76)
- Modify: `frontend/src/app/workspaces/gallery/gallery.spec.ts` (l.126-127)
- Modify: `frontend/src/styles/tokens.css` (the valence-exception comment, l.48-49; comment only)

**Interfaces:**
- Consumes: V241-2's `long` and `short` names (`IconName`); V241-1b's 16px default size; plan 1 V240-6's `styleRules(name: string, source: string): StyleRule[]` from `frontend/src/app/ui/testing/style-rules.ts`.
- Produces: `sb-direction-arrow` renders `<span class="arrow long|short" role="img" [title] [attr.aria-label]><sb-icon [name]="icon()" title="" /></span>`; `aria-label`/`title` stay `'Long (bullish)'` / `'Short (bearish)'`; unknown direction still renders the `ABSENT` dash. V241-8's accessible-name guard reads this source.

**Why `role="img"`:** the cell used to hold the text `▲`, which a screen reader read out. Once the content is an `aria-hidden` svg, the span has no text, and an `aria-label` on a role-less `<span>` is ignored by most screen readers — the column would go silent, which is exactly what the component's header comment forbids. `role="img"` makes the span a named graphic, so the name it already carries is announced. Colour stays `--pos`/`--neg` (spec §1, the recorded valence exception; `direction-arrow.ts` is not a `NAV_FILES` entry in `money-colour.spec.ts`).

- [ ] **Step 1: Write the failing tests**

Replace the whole of `frontend/src/app/ui/direction-arrow.spec.ts` with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { DirectionArrow } from './direction-arrow';
import { styleRules } from './testing/style-rules';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/direction-arrow.ts'), 'utf8');

/** The `long` and `short` drawings from icon.ts (V241-2). sb-icon's `name`
 *  is a property binding with no DOM trace, so the drawing is the check. */
const LONG_D = 'M3 17l6-6 4 4 8-8 M15 7h6v6';
const SHORT_D = 'M3 7l6 6 4-4 8 8 M15 17h6v-6';

function render(direction: string | null) {
  const f = TestBed.createComponent(DirectionArrow);
  f.componentRef.setInput('direction', direction);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const drawn = (el: HTMLElement) =>
  el.querySelector('.arrow > sb-icon svg path')?.getAttribute('d') ?? null;

describe('DirectionArrow', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('draws the rising trend arrow for a long', () => {
    const el = render('bullish');
    expect(drawn(el)).toBe(LONG_D);
    expect(el.querySelector('.long')).not.toBeNull();
    // No text glyph left: the shape no longer depends on the font.
    expect(el.textContent!.trim()).toBe('');
  });

  it('draws the falling trend arrow for a short', () => {
    const el = render('bearish');
    expect(drawn(el)).toBe(SHORT_D);
    expect(el.querySelector('.short')).not.toBeNull();
    expect(el.textContent!.trim()).toBe('');
  });

  it('is an em dash when the direction is unknown', () => {
    const el = render(null);
    expect(el.textContent!.trim()).toBe('—');
    expect(el.querySelector('sb-icon')).toBeNull();
  });

  it('draws at the table size, 16px', () => {
    const svg = render('bullish').querySelector('sb-icon svg')!;
    expect(svg.getAttribute('width')).toBe('16');
  });

  it('names itself for a screen reader, because the icon is the whole cell', () => {
    // Not optional: an arrow with no accessible name makes the entire column
    // unreadable to anyone not looking at it. role="img" is what makes a
    // screen reader announce a span's aria-label once it holds no text.
    const el = render('bullish');
    const arrow = el.querySelector('[aria-label]')!;
    expect(arrow.getAttribute('aria-label')).toBe('Long (bullish)');
    expect(arrow.getAttribute('title')).toBe('Long (bullish)');
    expect(arrow.getAttribute('role')).toBe('img');
  });

  it('names a short the same way', () => {
    const arrow = render('bearish').querySelector('[aria-label]')!;
    expect(arrow.getAttribute('aria-label')).toBe('Short (bearish)');
    expect(arrow.getAttribute('title')).toBe('Short (bearish)');
    expect(arrow.getAttribute('role')).toBe('img');
  });

  it('keeps the icon out of the name: no tooltip of its own, svg hidden', () => {
    // Exactly one name per cell: "Long (bullish)", never "Long (bullish) Long".
    const el = render('bullish');
    expect(el.querySelectorAll('[aria-label]')).toHaveLength(1);
    expect(el.querySelector('sb-icon')!.getAttribute('title')).toBe('');
    expect(el.querySelector('sb-icon svg')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('colours long and short with --pos and --neg, the recorded valence exception', () => {
    const rules = styleRules('direction-arrow.ts', SOURCE);
    expect(rules.find((r) => r.selector === '.long')?.body).toContain('var(--pos)');
    expect(rules.find((r) => r.selector === '.short')?.body).toContain('var(--neg)');
  });
});
```

In `frontend/src/app/ui/confidence-cell.spec.ts`, replace the two arrow tests:

```ts
  it('renders the direction arrow to the left of the level when given', () => {
    // The Dashboard's four lifecycle tables fold Direction into this column
    // to save width; every other call site leaves `direction` unset and
    // gets exactly the old markup (the test above).
    const el = render(4, 78, 'bullish');
    const arrow = el.querySelector('sb-direction-arrow');
    expect(arrow).not.toBeNull();
    expect(text(el)).toBe('▲ Lv4 · 78');
  });

  it('still shows the direction arrow when there is no confidence level yet', () => {
    // A PENDING plan has a direction from the moment it is built, well
    // before it has a linked trade to score for confidence -- gating the
    // arrow on level() too would silently lose the only direction info the
    // row has left, now that there is no separate Direction column.
    const el = render(null, null, 'bearish');
    expect(el.querySelector('sb-direction-arrow')).not.toBeNull();
    expect(text(el)).toBe('▼ —');
  });
```

with:

```ts
  it('renders the direction arrow to the left of the level when given', () => {
    // The Dashboard's four lifecycle tables fold Direction into this column
    // to save width; every other call site leaves `direction` unset and
    // gets exactly the old markup (the test above).
    const el = render(4, 78, 'bullish');
    const arrow = el.querySelector('sb-direction-arrow')!;
    expect(arrow).not.toBeNull();
    // The arrow is an icon now (v240 §4): it adds no text, and it leads.
    expect(el.querySelector('.conf')!.firstElementChild).toBe(arrow);
    expect(arrow.querySelector('svg')).not.toBeNull();
    expect(arrow.querySelector('[aria-label]')!.getAttribute('aria-label')).toBe('Long (bullish)');
    expect(text(el)).toBe('Lv4 · 78');
  });

  it('still shows the direction arrow when there is no confidence level yet', () => {
    // A PENDING plan has a direction from the moment it is built, well
    // before it has a linked trade to score for confidence -- gating the
    // arrow on level() too would silently lose the only direction info the
    // row has left, now that there is no separate Direction column.
    const el = render(null, null, 'bearish');
    const arrow = el.querySelector('sb-direction-arrow')!;
    expect(arrow).not.toBeNull();
    expect(arrow.querySelector('[aria-label]')!.getAttribute('aria-label')).toBe('Short (bearish)');
    expect(text(el)).toBe('—');
  });
```

In `frontend/src/app/workspaces/gallery/gallery.spec.ts`, in `renders one row per cell-contract case, with minutes in every Held value`, replace:

```ts
    expect(cell(rows[0], 'sb-direction-arrow')).toBe('▲');
    expect(cell(rows[1], 'sb-direction-arrow')).toBe('▼');
```

with:

```ts
    // Direction is an icon now (v240 §4): no text, the name on the cell.
    const arrowName = (row: Element) =>
      row.querySelector('sb-direction-arrow [aria-label]')!.getAttribute('aria-label');
    expect(cell(rows[0], 'sb-direction-arrow')).toBe('');
    expect(arrowName(rows[0])).toBe('Long (bullish)');
    expect(arrowName(rows[1])).toBe('Short (bearish)');
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/direction-arrow.spec.ts --include src/app/ui/confidence-cell.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: FAIL — the arrow still renders `▲`/`▼` text, no `sb-icon` and no `role`.

- [ ] **Step 3: Draw the icon**

Replace the whole of `frontend/src/app/ui/direction-arrow.ts` with:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ABSENT } from './format';
import { Icon, IconName } from './icon';

/**
 * Direction as a single icon — spec v18 Decision 4, drawn by v240 §4: the
 * `long` / `short` trend arrows replaced the ▲ / ▼ text glyphs, whose shape
 * changed with the font and sat off the baseline.
 *
 * **The one recorded exception to the valence rule.** Everywhere else green
 * and red mean money made and money lost; here they mean long and short,
 * which is a direction and not an outcome. It is allowed because the pairing
 * is so strongly conventional in trading UIs that the alternative reads as a
 * bug, and it is written down so nobody "fixes" it later by making both
 * arrows grey.
 *
 * The icon is the entire content of the cell, so the accessible name is
 * load-bearing rather than a nicety: without it the column is silent to a
 * screen reader and the shape carries everything. The icon is aria-hidden
 * with an empty title; the span is `role="img"` so its aria-label is
 * announced although it holds no text.
 */
@Component({
  selector: 'sb-direction-arrow',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (label(); as text) {
      <span class="arrow" [class]="cls()" role="img" [title]="text" [attr.aria-label]="text">
        <sb-icon [name]="icon()" title="" />
      </span>
    } @else {
      <span class="absent" aria-hidden="true">{{ absent }}</span>
    }
  `,
  styles: `
    /* An svg has no text baseline: in a baseline-aligned flex row (Recent
       Activity) the arrow centres on the row as sb-icon does, and inline in
       text (the confidence cell) it centres on the line. */
    :host { display: inline-flex; align-self: center; vertical-align: middle; }
    .arrow { display: inline-flex; line-height: 0; cursor: help; }
    .long  { color: var(--pos); }
    .short { color: var(--neg); }
    .absent { color: var(--text-faint); }
  `,
})
export class DirectionArrow {
  readonly direction = input<string | null>(null);

  protected readonly absent = ABSENT;

  private readonly isLong = computed(() => this.direction() === 'bullish');
  private readonly isShort = computed(() => this.direction() === 'bearish');

  /** Read only when `label()` is set, i.e. for a long or a short. */
  protected readonly icon = computed<IconName>(() => (this.isLong() ? 'long' : 'short'));
  protected readonly cls = computed(() => (this.isLong() ? 'long' : 'short'));

  /** Null for an unknown direction, which is what selects the dash branch. */
  protected readonly label = computed(() =>
    this.isLong() ? 'Long (bullish)' : this.isShort() ? 'Short (bearish)' : null,
  );
}
```

(`.absent` keeps `--text-faint` exactly as today; if plan 1's V240-9 type gate moved it to another token, keep plan 1's token, not this line.)

In `frontend/src/styles/tokens.css`, in the comment that records the direction exception, replace:

```css
   * --neg, though a short is not "bad". The glyph (▲/▼) is the primary
```

with:

```css
   * --neg, though a short is not "bad". The icon (rising/falling arrow) is the primary
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false --include src/app/ui/direction-arrow.spec.ts --include src/app/ui/confidence-cell.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts --include src/app/ui/money-colour.spec.ts --include src/app/ui/type-gates.spec.ts`
Expected: PASS, 0 failed (recent-activity, money-colour and type-gates are run because the arrow sits in Recent Activity and its CSS is scanned by both gates).

Then: `git grep -n -E "▲|▼" -- frontend/src ':!*.spec.ts'`. Expected: no output (the versions `&#9650;` reference is V241-7's).

- [ ] **Step 5: Check the three widths**

Per `docs/claude/ui-design.md` (Playwright only, `.env` admin credentials loaded inside the script, never printed): on `/dashboard` at 390px, 820px and 1440px, each Recent Activity row shows the 16px trend arrow in green (long) or red (short) centred on the row beside the ticker; the lifecycle tables' confidence column shows the arrow before `Lv4 · 78` on one line, centred on the text; `/trades` shows it in the Direction column. Hovering an arrow shows "Long (bullish)" / "Short (bearish)".

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/direction-arrow.ts frontend/src/app/ui/direction-arrow.spec.ts frontend/src/app/ui/confidence-cell.spec.ts frontend/src/app/workspaces/gallery/gallery.spec.ts frontend/src/styles/tokens.css
git commit -m "feat(ui): direction arrows draw the long/short trend icons, named as role=img (V241-4)"
```

