# v236 — Guide page, Part 2: search, contents at three widths, route and nav (V236-5..V236-7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V236-6" -A 400 <this file>`).

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md) (Plan A, frontend half; § Page behaviour, § Design "frontend")
**Index:** [2026-11-18-v236-guide-page_0-index.md](2026-11-18-v236-guide-page_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below.

Contracts this part consumes from Part 1 (do not change them):

- **`GuideStore` (V236-1).** `chapters(): GuideChapterSummary[]`, `bodies(): Record<string, GuideChapter>`, `chapterStatus(): Record<string, 'loading' | 'ready' | 'missing' | 'error'>`, `loadChapter(slug)` (skips a slug already `loading`/`ready`; retries `missing`/`error`).
- **`Guide` page (V236-4).** `frontend/src/app/workspaces/guide/guide.ts`: selector `sb-guide`, `ViewEncapsulation.None` with every style rule under `sb-guide`, members `store`, `router`, `activeSlug`, `chapter`, `segments`, `loading`, `error`, `empty`, `emptyTitle`, `notice`, private `scrolledTo`, methods `figure`, `retry`, `onContentClick`; template `[page-primary]` `div.guide-layout` holding `sb-panel.guide-panel` → `sb-async` → `article#article.guide-chapter`, then `p.guide-notice`. `guide.spec.ts` helpers `INDEX`, `BODY`, `openGuide(slug, opts)`, `settle(fixture)` (file-local, not exported).
- **`guideRoutes` (V236-4).** `frontend/src/app/workspaces/guide/guide.routes.ts`, one componentless parent (`providers: [GuideStore]`, `runGuardsAndResolvers: 'always'`, `resolve.ready`, `routeData('Guide', onEvents())`) with children `''` and `':slug'`.

Token note for every style below: `--text-secondary` is a **colour** token; text sizes are `--text-micro`, `--text-table`, `--text-body`, `--text-subhead` (`frontend/src/styles/tokens.css:249-257`).

# Phase 4 — Search and contents

### Task V236-5: Guide search module

**Model:** sonnet — a pure TypeScript module with its spec; the heading rule must match the backend's exactly.

**Files:**
- Create: `frontend/src/app/workspaces/guide/guide-search.ts`
- Create: `frontend/src/app/workspaces/guide/guide-search.spec.ts`

**Interfaces:**
- Consumes: `GuideChapterSummary`, `GuideChapter` from `frontend/src/app/api/models.ts` (V236-1).
- Produces (V236-6 wires them into the page):
  - `interface GuideSearchEntry { slug: string; chapterTitle: string; anchor: string | null; text: string }` — one entry per chapter (`anchor: null`, text = title + the prose before the first heading) and one per heading (text = heading + its section's prose once the body is loaded, the heading alone before that);
  - `plainText(markdown: string): string`;
  - `splitSections(markdown: string): string[]` — the preface, then one section per `##`/`###` line outside code fences (the backend's heading rule in V235's `extract_headings`, so section *i* lines up with `headings[i - 1]`);
  - `buildGuideSearchIndex(chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>): GuideSearchEntry[]` — reading order;
  - `searchGuide(entries: GuideSearchEntry[], query: string, limit = 20): GuideSearchEntry[]` — every word must appear (chapter title or entry text), case-insensitive, document order, `[]` for a blank query;
  - `snippetFor(text: string, query: string, width = 120): string` — a window around the first matching word, `…` on a cut side.

Why: spec v215 § Page behaviour asks for client-side search over titles, headings and text with an empty state; § Design says the index is built from the chapter index plus the text of loaded chapters, so heading search works before any chapter opens. This task is the pure half; the page is V236-6. No UI here, so no width work.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/guide/guide-search.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { GuideChapter, GuideChapterSummary } from '../../api/models';
import { buildGuideSearchIndex, plainText, searchGuide, snippetFor, splitSections } from './guide-search';

const CHAPTERS: GuideChapterSummary[] = [
  { slug: 'what-it-is', title: 'What the bot is', order: 1, reviewed_for: '2.19.2',
    headings: [{ level: 2, text: 'Swing horizons', anchor: 'swing-horizons' }, { level: 3, text: 'Masked', anchor: 'masked' }] },
  { slug: 'glossary', title: 'Glossary', order: 12, reviewed_for: '2.19.2',
    headings: [{ level: 3, text: 'R multiple', anchor: 'r-multiple' }] },
];
const BODIES: Record<string, GuideChapter> = {
  'what-it-is': { slug: 'what-it-is', title: 'What the bot is', reviewed_for: '2.19.2', markdown: [
    '> **In plain words** paper trades only.', '## Swing horizons', 'Holding from days to weeks.',
    '```', '## not a heading', '```', '### Masked', 'Research only, never alerted.',
  ].join('\n') },
};

describe('plainText', () => {
  it('drops tags, comments, link targets and Markdown marks', () => {
    expect(plainText('<!-- figure:x --> **Bold** [the glossary](/insights/guide/glossary) <details>`code`</details>'))
      .toBe('Bold the glossary code');
  });

  it('is empty for empty input', () => {
    expect(plainText('')).toBe('');
  });
});

describe('splitSections', () => {
  it('splits at ##/### outside code fences, keeping the preface first', () => {
    const sections = splitSections(BODIES['what-it-is'].markdown);
    expect(sections).toHaveLength(3);
    expect(sections[0]).toBe('In plain words paper trades only.');
    expect(sections[1]).toBe('Holding from days to weeks. not a heading');
    expect(sections[2]).toBe('Research only, never alerted.');
  });

  it('does not split at #### or at a hash without a space', () => {
    expect(splitSections('a\n#### deep\n##tight')).toHaveLength(1);
  });

  it('reads Windows line endings like Unix ones', () => {
    expect(splitSections('pre\r\n## H\r\nbody')).toEqual(['pre', 'body']);
  });
});

describe('buildGuideSearchIndex', () => {
  const index = buildGuideSearchIndex(CHAPTERS, BODIES);

  it('lists each chapter, then each of its headings, in reading order', () => {
    expect(index.map((e) => [e.slug, e.anchor])).toEqual([
      ['what-it-is', null], ['what-it-is', 'swing-horizons'], ['what-it-is', 'masked'],
      ['glossary', null], ['glossary', 'r-multiple'],
    ]);
  });

  it('carries the section text of a loaded chapter and only the heading otherwise', () => {
    expect(index[0].text).toBe('What the bot is In plain words paper trades only.');
    expect(index[1].text).toBe('Swing horizons Holding from days to weeks. not a heading');
    expect(index[4].text).toBe('R multiple');
  });

  it('is empty for an empty guide', () => {
    expect(buildGuideSearchIndex([], {})).toEqual([]);
  });
});

describe('searchGuide', () => {
  const index = buildGuideSearchIndex(CHAPTERS, BODIES);

  it('finds headings before any body is loaded', () => {
    const bare = buildGuideSearchIndex(CHAPTERS, {});
    expect(searchGuide(bare, 'multiple').map((e) => e.anchor)).toEqual(['r-multiple']);
  });

  it('needs every word, ignores case and keeps document order', () => {
    expect(searchGuide(index, 'WEEKS holding').map((e) => e.anchor)).toEqual(['swing-horizons']);
    expect(searchGuide(index, 'research weeks')).toEqual([]);
  });

  it('matches the chapter title on every entry of that chapter', () => {
    expect(searchGuide(index, 'glossary multiple').map((e) => e.anchor)).toEqual(['r-multiple']);
  });

  it('returns nothing for a blank query and honours the limit', () => {
    expect(searchGuide(index, '   ')).toEqual([]);
    expect(searchGuide(index, 'i', 2)).toHaveLength(2);
  });
});

describe('snippetFor', () => {
  it('centres on the first matching word with ellipses', () => {
    const text = `${'a '.repeat(100)}target ${'b '.repeat(100)}`;
    const snippet = snippetFor(text, 'target', 40);
    expect(snippet).toContain('target');
    expect(snippet.startsWith('…')).toBe(true);
    expect(snippet.endsWith('…')).toBe(true);
  });

  it('starts at the beginning when nothing matches', () => {
    const text = `start ${'x '.repeat(100)}`;
    const snippet = snippetFor(text, 'zzz', 40);
    expect(snippet.startsWith('start')).toBe(true);
    expect(snippet.endsWith('…')).toBe(true);
  });

  it('returns short text whole', () => {
    expect(snippetFor('short text', 'zzz')).toBe('short text');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-search.spec.ts`
Expected: FAIL — `Cannot find module './guide-search'`.

- [ ] **Step 3: Write `guide-search.ts`**

Create `frontend/src/app/workspaces/guide/guide-search.ts`:

```ts
import { GuideChapter, GuideChapterSummary } from '../../api/models';

/** One searchable place: a chapter (anchor null) or one heading in it. */
export interface GuideSearchEntry {
  slug: string;
  chapterTitle: string;
  anchor: string | null;
  text: string;
}

/** The backend's heading rule (V235's `extract_headings`): `##` or `###`
 *  then whitespace, outside code fences. Kept identical so section i of a
 *  body is the section under `headings[i - 1]` of the chapter index. */
const HEADING_LINE = /^#{2,3}\s/;
const FENCE = /^\s*(```|~~~)/;

/** Markdown to searchable words: no comments, tags, link targets or marks. */
export function plainText(markdown: string): string {
  return markdown
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[`*_>#|~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** The preface, then one plain-text section per heading line. */
export function splitSections(markdown: string): string[] {
  const sections: string[][] = [[]];
  let fenced = false;
  for (const line of markdown.replace(/\r\n?/g, '\n').split('\n')) {
    if (FENCE.test(line)) fenced = !fenced;
    if (!fenced && HEADING_LINE.test(line)) sections.push([]);
    else sections[sections.length - 1].push(line);
  }
  return sections.map((lines) => plainText(lines.join('\n')));
}

/** Every chapter and heading in reading order; a heading carries its
 *  section's prose only once the chapter body is loaded. */
export function buildGuideSearchIndex(
  chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>,
): GuideSearchEntry[] {
  return chapters.flatMap((chapter) => {
    const body = bodies[chapter.slug];
    const sections = body ? splitSections(body.markdown) : [];
    const entry = (anchor: string | null, heading: string, at: number): GuideSearchEntry => ({
      slug: chapter.slug, chapterTitle: chapter.title, anchor,
      text: `${heading} ${sections[at] ?? ''}`.trim(),
    });
    return [entry(null, chapter.title, 0), ...chapter.headings.map((h, i) => entry(h.anchor, h.text, i + 1))];
  });
}

const words = (query: string): string[] => query.toLowerCase().split(/\s+/).filter((w) => w !== '');

/** Entries holding every word of the query, in document order. */
export function searchGuide(entries: GuideSearchEntry[], query: string, limit = 20): GuideSearchEntry[] {
  const needles = words(query);
  if (needles.length === 0) return [];
  return entries
    .filter((e) => {
      const haystack = `${e.chapterTitle} ${e.text}`.toLowerCase();
      return needles.every((w) => haystack.includes(w));
    })
    .slice(0, limit);
}

/** A `width`-character window around the first matching word. */
export function snippetFor(text: string, query: string, width = 120): string {
  if (text.length <= width) return text;
  const lower = text.toLowerCase();
  const hit = words(query).map((w) => lower.indexOf(w)).find((i) => i >= 0) ?? 0;
  const start = Math.max(0, Math.min(hit - Math.floor(width / 3), text.length - width));
  const body = text.slice(start, start + width).trim();
  return `${start > 0 ? '…' : ''}${body}${start + width < text.length ? '…' : ''}`;
}
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-search.spec.ts`
Expected: PASS (15 tests). A 60 s "Timeout waiting for worker" is the known flake: re-run the same command once.

- [ ] **Step 5: Run the source-as-text specs that police new files**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/all-sources.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: PASS (the new file carries no styles; this confirms nothing else trips).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/guide/guide-search.ts frontend/src/app/workspaces/guide/guide-search.spec.ts
git commit -m "feat(guide): client-side search index over titles, headings and loaded text (v236 V236-5)"
```

### Task V236-6: Contents rail, drawer and picker

**Model:** sonnet — one page's layout per breakpoint; precedents `ViewportService`, `Drawer`, `Select`.

**Files:**
- Modify: `frontend/src/app/workspaces/guide/guide.ts` (imports, template, styles appended, members; V236-4's anchor, deep-link, figure and breadcrumb code stays as is)
- Modify: `frontend/src/app/workspaces/guide/guide.spec.ts` (a `width` option in `openGuide`, one new `describe`)

**Interfaces:**
- Consumes: V236-4's `Guide` (`store`, `router`, `activeSlug`, `chapter`, private `scrolledTo`, the `#article` block inside `[page-primary]` `div.guide-layout`) and its spec helpers `openGuide`/`settle`/`INDEX`/`BODY`; `GuideStore.chapters` (V236-1); `ViewportService` (`frontend/src/app/ui/breakpoints.ts`, root-provided: `viewport()`, `isPhone` < 640, `isNarrow` < 1024); `Drawer` (`ui/layout.ts`, `sb-drawer`: inputs `open`, `heading`, output `closed`); `Select` (`sb-select`: `value` model, `options = input.required<SelectOption[]>()`, `ariaLabel`) and `SelectOption {value; label}` from `ui/form-controls.ts`; `Button` (`ui/button.ts`, `button[sb-button]`); `installDialogPolyfill` (`frontend/src/app/testing/dialog-polyfill.ts`).
- Produces:
  - for V236-6b (search, same files): the `Width` type, `fakeViewport` and the `width` option of `openGuide` in `guide.spec.ts`; in `guide.ts` the members `tocMode`, `drawerOpen`, `picked()`, the `div.guide-bar` (picker and drawer modes), `sb-drawer`, `nav.guide-rail` and the `<ng-template #contents>` block — V236-6b adds one `<ng-container *ngTemplateOutlet="search" />` into each of the three places contents are shown;
  - for V236-11's layout check: `nav.guide-rail` (≥ 1024, sticky), `button.guide-contents` + `sb-drawer` (640–1023), `sb-select.guide-picker` (< 640); TOC links `a.toc-chapter` (current one `aria-current="page"`) and `a.toc-heading`.

Three widths (spec v215 § Page behaviour, `ui-design.md` three-device rule):
- **Desktop ≥ 1024**: a sticky left rail (`minmax(14rem, 18rem)` column, its own scroll) holding the chapter list with the open chapter's headings; the article beside it. Rows `min-height: var(--hit-min)` (24px on a fine pointer).
- **Tablet 640–1023**: one column; a "Contents" button opens the shared `sb-drawer` holding the chapter list; following any link in it closes the drawer. Rows reach 44px (`--hit-min` is 44px below 1024px).
- **Phone < 640**: a full-width chapter picker (`sb-select`, `--control-h` 44px on touch) above the article. The picker takes `width: 100%` and long titles wrap in the list, so nothing is wider than the viewport.

Vertical-list rows grow to `--hit-min` (they are the list, so growing them is the layout, not a row-height regression); no `::after` boxes overlap in a list.

- [ ] **Step 1: Extend the page spec (failing)**

In `frontend/src/app/workspaces/guide/guide.spec.ts`:

1. Imports: add `signal` to the `@angular/core` import; add `import { installDialogPolyfill } from '../../testing/dialog-polyfill';` and `import { ViewportService } from '../../ui/breakpoints';`.
2. Add above `openGuide`:

```ts
type Width = 'phone' | 'tablet' | 'desktop';
const VIEWPORT = { phone: 'xs', tablet: 'sm', desktop: 'lg' } as const;
/** ViewportService pinned to one width: sb-drawer and sb-panel read `viewport()`, the page reads the two flags. */
const fakeViewport = (width: Width) => ({
  viewport: signal(VIEWPORT[width]), isPhone: signal(width === 'phone'), isNarrow: signal(width !== 'desktop'),
});
```

3. Change `openGuide`'s options type to `opts: { fragment?: string | null; status?: number; width?: Width } = {}` and add `{ provide: ViewportService, useValue: fakeViewport(opts.width ?? 'desktop') },` to its `providers` array (after the `ActivatedRoute` entry). The V236-4 tests keep the desktop default.
4. Append at the end of the file:

```ts
describe('Guide page: contents at three widths', () => {
  afterEach(() => vi.restoreAllMocks());

  it('desktop: a rail lists every chapter and the open chapter’s headings', async () => {
    const { el } = await openGuide('what-it-is');
    const rail = el.querySelector('nav.guide-rail')!;
    expect([...rail.querySelectorAll('a.toc-chapter')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/what-it-is', '/insights/guide/glossary']);
    expect(rail.querySelector('a[aria-current="page"]')!.textContent!.trim()).toBe('What the bot is (and isn’t)');
    expect([...rail.querySelectorAll('a.toc-heading')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/what-it-is#swing-horizons', '/insights/guide/what-it-is#masked']);
    expect(el.querySelector('button.guide-contents')).toBeNull();
    expect(el.querySelector('sb-select.guide-picker')).toBeNull();
  });

  it('desktop: lists headings only for the open chapter', async () => {
    const { el } = await openGuide('glossary');
    expect([...el.querySelectorAll('nav.guide-rail a.toc-heading')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/glossary#r-multiple']);
  });

  it('tablet: a Contents button opens the drawer with the same list', async () => {
    installDialogPolyfill();
    const { el, fixture } = await openGuide('what-it-is', { width: 'tablet' });
    expect(el.querySelector('nav.guide-rail')).toBeNull();
    expect(el.querySelector('sb-select.guide-picker')).toBeNull();
    expect(el.querySelectorAll('sb-drawer a.toc-chapter')).toHaveLength(0);
    el.querySelector<HTMLButtonElement>('button.guide-contents')!.click();
    await settle(fixture);
    expect(el.querySelectorAll('sb-drawer a.toc-chapter')).toHaveLength(2);
  });

  it('tablet: following a contents link closes the drawer', async () => {
    installDialogPolyfill();
    const { el, fixture } = await openGuide('what-it-is', { width: 'tablet' });
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    el.querySelector<HTMLButtonElement>('button.guide-contents')!.click();
    await settle(fixture);
    el.querySelectorAll<HTMLAnchorElement>('sb-drawer a.toc-chapter')[1].click();
    await settle(fixture);
    expect(el.querySelectorAll('sb-drawer a.toc-chapter')).toHaveLength(0);
  });

  it('phone: a labelled chapter picker above the article navigates to the chosen chapter', async () => {
    const { el, fixture } = await openGuide('what-it-is', { width: 'phone' });
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    expect(el.querySelector('nav.guide-rail')).toBeNull();
    expect(el.querySelector('button.guide-contents')).toBeNull();
    const select = el.querySelector<HTMLSelectElement>('.guide-bar sb-select.guide-picker select')!;
    expect(select.getAttribute('aria-label')).toBe('Chapter');
    expect(select.value).toBe('what-it-is');
    expect([...select.options].map((o) => o.value)).toEqual(['what-it-is', 'glossary']);
    select.value = 'glossary';
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
    expect(navigate).toHaveBeenCalledWith(['/insights/guide', 'glossary']);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide.spec.ts`
Expected: FAIL — no `nav.guide-rail`, no `button.guide-contents`, no `sb-select.guide-picker`; the V236-4 tests still pass.

- [ ] **Step 3: Update the imports in `guide.ts`**

In `frontend/src/app/workspaces/guide/guide.ts`:

- `import { NgComponentOutlet, NgTemplateOutlet } from '@angular/common';`
- add `signal` to the `@angular/core` import list;
- `import { ActivatedRoute, Router, RouterLink } from '@angular/router';`
- add `import { ViewportService } from '../../ui/breakpoints';`, `import { Button } from '../../ui/button';`, `import { Select, SelectOption } from '../../ui/form-controls';`, and change the layout import to `import { Drawer, Panel } from '../../ui/layout';`;
- the decorator's `imports:` becomes `[Async, Button, Drawer, NgComponentOutlet, NgTemplateOutlet, Page, Panel, RouterLink, Select]`.

- [ ] **Step 4: Replace the template**

Replace the whole `template:` value with (the `article` block is V236-4's, unchanged):

```ts
  template: `
    <sb-page [heading]="chapter()?.title ?? null">
      <div page-primary class="guide-layout">
        @if (tocMode() === 'picker') {
          <div class="guide-bar">
            <sb-select class="guide-picker" ariaLabel="Chapter" [options]="chapterOptions()"
                       [value]="activeSlug() ?? ''" (valueChange)="goTo($event)" />
          </div>
        } @else if (tocMode() === 'drawer') {
          <div class="guide-bar">
            <button sb-button type="button" class="guide-contents" (click)="drawerOpen.set(true)">Contents</button>
          </div>
          <sb-drawer [open]="drawerOpen()" heading="Contents" (closed)="drawerOpen.set(false)">
            <ng-container *ngTemplateOutlet="contents" />
          </sb-drawer>
        }
        <div class="guide-body">
          @if (tocMode() === 'rail') {
            <nav class="guide-rail" aria-label="Guide contents">
              <ng-container *ngTemplateOutlet="contents" />
            </nav>
          }
          <div class="guide-main">
            <sb-panel class="guide-panel">
              <sb-async [loading]="loading()" [error]="error()" [empty]="empty()" emptyReason="no-data-yet"
                        [emptyTitle]="emptyTitle()" [staleAsOf]="null" shape="panel" (retry)="retry()">
                <article #article class="guide-chapter" (click)="onContentClick($event)">
                  <p class="guide-stamp">Reviewed for bot v{{ chapter()?.reviewed_for }}</p>
                  @for (segment of segments(); track $index) {
                    @if (segment.kind === 'md') {
                      <div class="md" [innerHTML]="segment.html"></div>
                    } @else {
                      <ng-container *ngComponentOutlet="figure(segment.name)" />
                    }
                  }
                </article>
              </sb-async>
            </sb-panel>
            <p class="guide-notice">{{ notice }}</p>
          </div>
        </div>
      </div>
    </sb-page>

    <ng-template #contents>
      <ol class="guide-toc">
        @for (c of store.chapters(); track c.slug) {
          <li>
            <a class="toc-chapter" [routerLink]="['/insights/guide', c.slug]" (click)="picked()"
               [attr.aria-current]="c.slug === activeSlug() ? 'page' : null">{{ c.title }}</a>
            @if (c.slug === activeSlug() && c.headings.length) {
              <ol class="toc-headings">
                @for (h of c.headings; track h.anchor) {
                  <li><a class="toc-heading" [class.sub]="h.level === 3" [routerLink]="['/insights/guide', c.slug]"
                         [fragment]="h.anchor" (click)="picked()">{{ h.text }}</a></li>
                }
              </ol>
            }
          </li>
        }
      </ol>
    </ng-template>
  `,
```

- [ ] **Step 5: Append the styles**

Keep every V236-4 rule (its first rule already is `sb-guide .guide-layout { … }`). Append inside the `styles` string:

```css
    sb-guide .guide-bar { display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--space-10); min-width: 0; }
    sb-guide .guide-picker { flex: 1 1 100%; min-width: 0; }
    sb-guide .guide-picker .field, sb-guide .guide-picker select { width: 100%; max-width: 100%; }
    sb-guide .guide-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); align-items: start; }
    sb-guide .guide-main { display: flex; flex-direction: column; gap: var(--space-14); min-width: 0; }
    @media (min-width: 1024px) {
      sb-guide .guide-body { grid-template-columns: minmax(14rem, 18rem) minmax(0, 1fr); }
      sb-guide .guide-rail { position: sticky; top: var(--space-14); max-height: calc(100dvh - 8rem); overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-10); }
    }
    sb-guide .guide-toc, sb-guide .toc-headings { list-style: none; margin: 0; padding: 0; }
    sb-guide .toc-headings { padding-left: var(--space-10); }
    sb-guide .toc-chapter, sb-guide .toc-heading { display: flex; align-items: center; min-height: var(--hit-min); color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
    sb-guide .toc-heading { color: var(--text-secondary); font-size: var(--text-table); }
    sb-guide .toc-heading.sub { padding-left: var(--space-10); }
    sb-guide .toc-chapter[aria-current='page'] { color: var(--accent); font-weight: 600; }
```

`--text-secondary` is used only as a colour; the size is `--text-table`.

- [ ] **Step 6: Add the members**

Add to the `Guide` class, after `notice`:

```ts
  private readonly viewport = inject(ViewportService);
  /** Contents per width: rail ≥ 1024, drawer 640–1023, picker < 640. */
  protected readonly tocMode = computed<'rail' | 'drawer' | 'picker'>(() =>
    this.viewport.isPhone() ? 'picker' : this.viewport.isNarrow() ? 'drawer' : 'rail');
  protected readonly drawerOpen = signal(false);
  protected readonly chapterOptions = computed<SelectOption[]>(() =>
    this.store.chapters().map((c) => ({ value: c.slug, label: c.title })));
```

Add these methods after `retry()`:

```ts
  /** The phone picker: open the chosen chapter. */
  protected goTo(slug: string): void {
    if (slug && slug !== this.activeSlug()) void this.router.navigate(['/insights/guide', slug]);
  }

  /** A contents link was followed: close the drawer so the chapter is what
   *  the reader sees next, and let the fragment scroll again. */
  protected picked(): void {
    this.drawerOpen.set(false);
    this.scrolledTo = null;
  }
```

- [ ] **Step 7: Run the page and structural specs**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/all-sources.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: PASS. The V236-4 tests run at the desktop default; if one now matches two elements (the rail also lists headings), scope its query to `article`, never weaken the assertion. If a drawer test finds no links, check `installDialogPolyfill()` ran before `openGuide`. A 60 s "Timeout waiting for worker" is the known flake: re-run once.

- [ ] **Step 8: Build**

Run: `cd frontend && npx ng build --configuration development`
Expected: build succeeds (template bindings to `sb-select` and `sb-drawer` type-check).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/workspaces/guide/guide.ts frontend/src/app/workspaces/guide/guide.spec.ts
git commit -m "feat(guide): contents as a rail, drawer or picker per width (v236 V236-6)"
```

### Task V236-6b: Search wired into the page

**Model:** sonnet — wiring a finished pure module into one page at three widths; the only new logic is the search-intent effect.

**Files:**
- Modify: `frontend/src/app/workspaces/guide/guide.ts` (imports, three template insertions plus one `ng-template`, styles appended, members, one constructor effect, `picked()` extended)
- Modify: `frontend/src/app/workspaces/guide/guide.spec.ts` (one new `describe`)

**Interfaces:**
- Consumes: V236-6's `Guide` members `tocMode`, `drawerOpen`, `picked()`, its template (`div.guide-bar`, `sb-drawer`, `nav.guide-rail`, `<ng-template #contents>`) and spec helpers `openGuide(slug, { width })`, `settle`, `Width`; `buildGuideSearchIndex`, `searchGuide`, `snippetFor`, `GuideSearchEntry` (V236-5, `guide-search.ts`); `GuideStore.chapters`/`bodies`/`chapterStatus`/`loadChapter` (V236-1); `TextInput` (`ui/form-controls.ts`, `sb-text-input`: `value` model, `type`, `ariaLabel`, `placeholder`).
- Produces (V236-11's layout check reads these selectors): `.guide-search` wrapping one `sb-text-input` (in `nav.guide-rail` on desktop, first in the `sb-drawer` on tablet, in `div.guide-bar` below the picker on phone); `a.guide-result` links; `p.guide-no-match` reading `No section matches “<query>”`.
- Search intent: the first non-blank query fetches every chapter body the store has never requested (nothing loads before the reader searches; a `missing`/`error` chapter is not re-fetched per keystroke), so text search covers the whole guide; heading search works from the index alone.

Spec v215 § Page behaviour: client-side search over chapter titles, headings and text, with an empty state ("No section matches …"). Three widths: **desktop** the field heads the rail and results list inside the rail (its own scroll); **tablet** the field heads the drawer and following a result closes it; **phone** the field sits full-width below the picker (`.guide-bar` wraps; field `flex: 1 1 16rem`) and results show inline under it. Result rows reach `--hit-min` (44px below 1024px) and wrap long text (`overflow-wrap: anywhere`), so nothing is wider than 390px.

- [ ] **Step 1: Extend the page spec (failing)**

Append to `frontend/src/app/workspaces/guide/guide.spec.ts`:

```ts
const GLOSSARY = { slug: 'glossary', title: 'Glossary', reviewed_for: '2.19.1', markdown: '### R multiple\n\nOne R is the risk.' };

function typeQuery(el: HTMLElement, text: string): void {
  const field = el.querySelector<HTMLInputElement>('.guide-search input')!;
  field.value = text;
  field.dispatchEvent(new Event('input'));
}

describe('Guide page: search', () => {
  afterEach(() => vi.restoreAllMocks());

  it('places the field in the rail, the drawer or under the picker by width', async () => {
    let { el } = await openGuide('what-it-is');
    expect(el.querySelectorAll('.guide-search')).toHaveLength(1);
    expect(el.querySelector('nav.guide-rail .guide-search')).not.toBeNull();

    installDialogPolyfill();
    const tablet = await openGuide('what-it-is', { width: 'tablet' });
    expect(tablet.el.querySelector('.guide-search')).toBeNull();
    tablet.el.querySelector<HTMLButtonElement>('button.guide-contents')!.click();
    await settle(tablet.fixture);
    expect(tablet.el.querySelector('sb-drawer .guide-search')).not.toBeNull();

    ({ el } = await openGuide('what-it-is', { width: 'phone' }));
    expect(el.querySelector('.guide-bar .guide-search')).not.toBeNull();
  });

  it('loads nothing more until the reader searches, then finds a heading', async () => {
    const { el, fixture, http } = await openGuide('what-it-is');
    http.expectNone('/api/v1/guide/glossary');
    typeQuery(el, 'horizons');
    await settle(fixture);
    http.expectOne('/api/v1/guide/glossary').flush(GLOSSARY);
    await settle(fixture);
    const hit = el.querySelector<HTMLAnchorElement>('a.guide-result')!;
    expect(hit.getAttribute('href')).toBe('/insights/guide/what-it-is#swing-horizons');
    expect(hit.querySelector('.result-title')!.textContent!.trim()).toBe('Swing horizons');
  });

  it('searches the text of the chapters it fetched for the query', async () => {
    const { el, fixture, http } = await openGuide('what-it-is');
    typeQuery(el, 'risk');
    await settle(fixture);
    http.expectOne('/api/v1/guide/glossary').flush(GLOSSARY);
    await settle(fixture);
    expect([...el.querySelectorAll('a.guide-result')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/glossary#r-multiple']);
    expect(el.querySelector('a.guide-result .result-text')!.textContent).toContain('One R is the risk.');
  });

  it('says so when nothing matches', async () => {
    const { el, fixture, http } = await openGuide('what-it-is');
    typeQuery(el, 'zzz');
    await settle(fixture);
    http.expectOne('/api/v1/guide/glossary').flush(GLOSSARY);
    await settle(fixture);
    expect(el.querySelector('a.guide-result')).toBeNull();
    expect(el.querySelector('.guide-no-match')!.textContent!.trim()).toBe('No section matches “zzz”');
  });

  it('shows neither results nor the empty state for a blank query', async () => {
    const { el, fixture } = await openGuide('what-it-is');
    typeQuery(el, '   ');
    await settle(fixture);
    expect(el.querySelector('.guide-results')).toBeNull();
    expect(el.querySelector('.guide-no-match')).toBeNull();
  });

  it('does not re-fetch a missing chapter on the next keystroke', async () => {
    const { el, fixture, http } = await openGuide('what-it-is');
    typeQuery(el, 'r');
    await settle(fixture);
    http.expectOne('/api/v1/guide/glossary')
      .flush({ error: { code: 'not_found', message: 'none' } }, { status: 404, statusText: 'x' });
    await settle(fixture);
    typeQuery(el, 'ri');
    await settle(fixture);
    http.expectNone('/api/v1/guide/glossary');
  });

  it('clears the query once a result is followed', async () => {
    const { el, fixture, http } = await openGuide('what-it-is');
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    typeQuery(el, 'horizons');
    await settle(fixture);
    http.expectOne('/api/v1/guide/glossary').flush(GLOSSARY);
    await settle(fixture);
    el.querySelector<HTMLAnchorElement>('a.guide-result')!.click();
    await settle(fixture);
    expect(el.querySelector('a.guide-result')).toBeNull();
    expect(el.querySelector<HTMLInputElement>('.guide-search input')!.value).toBe('');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide.spec.ts`
Expected: FAIL — no `.guide-search`; the V236-4 and V236-6 tests still pass.

- [ ] **Step 3: Imports**

In `frontend/src/app/workspaces/guide/guide.ts`: the form-controls import becomes `import { Select, SelectOption, TextInput } from '../../ui/form-controls';`; add `import { GuideSearchEntry, buildGuideSearchIndex, searchGuide, snippetFor } from './guide-search';`; append `TextInput` to the decorator's `imports:` array.

- [ ] **Step 4: Place the search field in the three contents surfaces**

In the template, insert `<ng-container *ngTemplateOutlet="search" />`:

1. phone: inside the picker's `div.guide-bar`, on the line after the `<sb-select class="guide-picker" … />` element;
2. tablet: as the first child of `<sb-drawer …>`, before `<ng-container *ngTemplateOutlet="contents" />`;
3. desktop: as the first child of `<nav class="guide-rail" …>`, before `<ng-container *ngTemplateOutlet="contents" />`.

Then add this block between `</sb-page>` and `<ng-template #contents>`:

```html
    <ng-template #search>
      <div class="guide-search" role="search">
        <sb-text-input type="search" ariaLabel="Search the guide" placeholder="Search the guide"
                       [value]="query()" (valueChange)="query.set($event)" />
        @if (searching()) {
          @if (results().length) {
            <ul class="guide-results">
              @for (hit of results(); track hit.slug + '#' + hit.anchor) {
                <li><a class="guide-result" [routerLink]="['/insights/guide', hit.slug]"
                       [fragment]="hit.anchor ?? undefined" (click)="picked()">
                  <span class="result-title">{{ labelFor(hit) }}</span>
                  <span class="result-text">{{ snippet(hit.text) }}</span>
                </a></li>
              }
            </ul>
          } @else {
            <p class="guide-no-match">No section matches “{{ query().trim() }}”</p>
          }
        }
      </div>
    </ng-template>
```

- [ ] **Step 5: Append the styles**

Append inside the `styles` string:

```css
    sb-guide .guide-bar .guide-search { flex: 1 1 16rem; min-width: 0; }
    sb-guide .guide-search { display: flex; flex-direction: column; gap: var(--space-6); min-width: 0; }
    sb-guide .guide-search sb-text-input { display: block; }
    sb-guide .guide-results { list-style: none; margin: 0; padding: 0; }
    sb-guide .guide-result { display: flex; flex-direction: column; align-items: flex-start; justify-content: center; min-height: var(--hit-min); padding: var(--space-6) 0; border-bottom: 1px solid var(--border); color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
    sb-guide .result-text, sb-guide .guide-no-match { margin: 0; color: var(--text-muted); font-size: var(--text-table); }
```

- [ ] **Step 6: Members, `picked()` and the search-intent effect**

Add to the `Guide` class, after `chapterOptions`:

```ts
  protected readonly query = signal('');
  protected readonly searching = computed(() => this.query().trim() !== '');
  private readonly searchIndex = computed(() =>
    buildGuideSearchIndex(this.store.chapters(), this.store.bodies()));
  protected readonly results = computed(() => searchGuide(this.searchIndex(), this.query()));
```

Add these methods after `goTo()`:

```ts
  /** A result's label: its heading, or the chapter title for a chapter hit. */
  protected labelFor(hit: GuideSearchEntry): string {
    const chapter = this.store.chapters().find((c) => c.slug === hit.slug);
    return chapter?.headings.find((h) => h.anchor === hit.anchor)?.text ?? hit.chapterTitle;
  }

  protected snippet(text: string): string {
    return snippetFor(text, this.query());
  }
```

Replace V236-6's `picked()` with:

```ts
  /** A contents or result link was followed: close the drawer and the
   *  result list so the chapter is what the reader sees next, and let the
   *  fragment scroll again. */
  protected picked(): void {
    this.drawerOpen.set(false);
    this.query.set('');
    this.scrolledTo = null;
  }
```

At the end of the constructor, add:

```ts
    // Search intent: the first non-blank query fetches every body never
    // requested, so text search covers the whole guide. Keyed on
    // `searching`, not the text, and skipping any slug with a status, so a
    // missing or failed chapter is not re-fetched per keystroke.
    effect(() => {
      if (!this.searching()) return;
      const slugs = this.store.chapters().map((c) => c.slug);
      untracked(() => {
        const known = this.store.chapterStatus();
        slugs.filter((slug) => known[slug] === undefined).forEach((slug) => this.store.loadChapter(slug));
      });
    });
```

- [ ] **Step 7: Run the page, search and structural specs**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide.spec.ts --include src/app/workspaces/guide/guide-search.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/all-sources.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: PASS. If an earlier test now matches the rail's results too, scope its query to `article`, never weaken the assertion. A 60 s "Timeout waiting for worker" is the known flake: re-run once.

- [ ] **Step 8: Build**

Run: `cd frontend && npx ng build --configuration development`
Expected: build succeeds.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/workspaces/guide/guide.ts frontend/src/app/workspaces/guide/guide.spec.ts
git commit -m "feat(guide): search in the rail, drawer and phone bar, with an empty state (v236 V236-6b)"
```

# Phase 5 — Shell

### Task V236-7: Routes, nav and the hard-coded Insights specs

**Model:** sonnet — two one-line production edits whose weight is the five specs that pin the nav model; every list must change in rail order.

**Files:**
- Modify: `frontend/src/app/app.routes.ts:148-152` (new `insights/guide` entry after `insights/reports`)
- Modify: `frontend/src/app/shell/nav.ts:44-50` (Insights `sections` gains Guide after Reports)
- Modify: `frontend/src/app/app.routes.spec.ts` (~131-133 readiness list, ~113 real-page block, ~275-277 title table)
- Modify: `frontend/src/app/shell/nav.spec.ts` (:33 sections, :130-145 placements, :184 `isSectionUrl`, :205-208 breadcrumb cases)
- Modify: `frontend/src/app/shell/more-sheet.spec.ts` (:22, :77, :102)
- Modify: `frontend/src/app/shell/breadcrumb.spec.ts` (:28-36 section table, a new detail case)
- Modify: `frontend/src/app/shell/palette/palette-items.spec.ts` (:26-27 `RAIL`, :42-45 route list) — **not in the ledger row**: the palette derives its page list from `NAV_ENTRIES` and this spec hard-codes it, so it fails the moment `nav.ts` changes (found while writing this part; same task, no other task touches it).

**Interfaces:**
- Consumes: `guideRoutes` from `frontend/src/app/workspaces/guide/guide.routes.ts` (V236-4: one componentless parent with `providers: [GuideStore]`, `runGuardsAndResolvers: 'always'`, `resolve.ready`, `routeData('Guide', onEvents())`, children `''` and `':slug'`); `authGuard` (`shell/auth.guard.ts`).
- Produces: route `insights/guide` (title `Guide`, subtitle `How the bot finds, builds, sizes and closes trades`, `canMatch: [authGuard]`, `loadChildren` → `guideRoutes`); nav section `{ path: '/insights/guide', label: 'Guide' }` after Reports. V236-11's layout check opens `/insights/guide/<slug>` through it.

Spec v215 § Design: the page is lazy-loaded at `insights/guide` and `insights/guide/:slug` behind `authGuard`, added to the Insights sections in `shell/nav` and to `app.routes`, "with the existing route spec tables updated". `SPA_WORKSPACES` already serves `/insights/*` (no backend change).

Three widths: every nav surface derives from `NAV_ENTRIES`, so one entry reaches all of them — **desktop** the rail flyout and the Insights section tabs (`sb-section-tabs`, which scroll inside themselves: `.track { overflow-x: auto }`, `.segment { min-height: var(--control-h) }`); **tablet** the same section tabs at 44px touch height; **phone** the More sheet's Insights group (`a.page` rows) and the section tabs. Four segments ("Analytics Research Reports Guide") fit 390px, and if a larger text scale pushes them past it, the track scrolls rather than overflowing the page. The breadcrumb reads `Insights / Guide` on `/insights/guide` and `Insights / Guide / <chapter>` on a chapter URL, Guide linking back (`crumbsFor`'s detail rule: `/insights/guide/<slug>` is one level below a section URL).

- [ ] **Step 1: Update the specs (failing)**

1. `frontend/src/app/shell/nav.spec.ts`
   - line 33 becomes:
     ```ts
           '/insights': [['/insights/analytics', 'Analytics'], ['/insights/research', 'Research'], ['/insights/reports', 'Reports'], ['/insights/guide', 'Guide']],
     ```
   - in the `navEntryFor` `it.each` placements, after `['/insights/reports?tab=gates', ['Insights', 'Reports']],` add:
     ```ts
         ['/insights/guide', ['Insights', 'Guide']],
         ['/insights/guide/glossary#r-multiple', ['Insights', 'Guide']],
     ```
   - in the `isSectionUrl` "is true" list (line 184), add `'/insights/guide', '/insights/guide/glossary',` after `'/insights/analytics',`;
   - in the `breadcrumbFor` `it.each` (ends `['/watchlist/NVDA', 'NVDA', ['Watchlist', 'NVDA']],`), add:
     ```ts
         ['/insights/guide', null, ['Insights', 'Guide']],
         ['/insights/guide/glossary', 'Glossary', ['Insights', 'Guide', 'Glossary']],
     ```

2. `frontend/src/app/shell/more-sheet.spec.ts`
   - line 22 becomes:
     ```ts
           ['more-insights', 'Insights', [['Analytics', '/insights/analytics'], ['Research', '/insights/research'], ['Reports', '/insights/reports'], ['Guide', '/insights/guide']]],
     ```
   - line 77 becomes:
     ```ts
           .toEqual(['/risk', '/insights/analytics', '/insights/research', '/insights/reports', '/insights/guide']);
     ```
   - line 102 becomes:
     ```ts
           ['Analytics', '/insights/analytics'], ['Research', '/insights/research'], ['Reports', '/insights/reports'], ['Guide', '/insights/guide'],
     ```

3. `frontend/src/app/shell/breadcrumb.spec.ts`
   - in the `it.each` of "never reads the section of %s as a detail page", after `['/insights/analytics', 'Analytics', ['Insights', 'Analytics']],` add:
     ```ts
         ['/insights/guide', 'Guide', ['Insights', 'Guide']],
     ```
   - after the test "links the crumb before a detail back to its list", add:
     ```ts
       it('reads a guide chapter as a detail of the Guide section, linking back to it (v236)', () => {
         expect(crumbsFor('/insights/guide/glossary', 'Glossary', 'Guide')).toEqual([
           { label: 'Insights', link: null },
           { label: 'Guide', link: '/insights/guide' },
           { label: 'Glossary', link: null },
         ]);
       });
     ```

4. `frontend/src/app/shell/palette/palette-items.spec.ts`
   - `RAIL` becomes:
     ```ts
     const RAIL = ['Dashboard', 'Watchlist', 'Book', 'Calendar', 'Risk',
       'Analytics', 'Research', 'Reports', 'Guide', 'Health', 'Versions'];
     ```
   - in "routes every page to a path of the nav model", the second list line becomes:
     ```ts
           '/insights/analytics', '/insights/research', '/insights/reports', '/insights/guide', '/system', '/system/versions',
     ```

5. `frontend/src/app/app.routes.spec.ts`
   - the readiness contract's `expected` list (lines 130-134) becomes:
     ```ts
       const expected = [
         'dashboard', 'trades', 'trades/:id', 'plans/:id', 'insights/analytics', 'trades/calendar',
         'watchlist', 'watchlist/:symbol', 'risk', 'system', 'system/versions', 'insights/research',
         'insights/reports', 'insights/guide',
       ] as const;
     ```
     (`guideRoutes[0]` has `providers`, `runGuardsAndResolvers: 'always'`, `resolve.ready` and `routeData`'s loading label, which is what that test checks.)
   - in the title table, after `['insights/reports', 'Reports', 'What the measurements say about entries and gates'],` add:
     ```ts
         ['insights/guide', 'Guide', 'How the bot finds, builds, sizes and closes trades'],
     ```
   - after the test "serves Research and Reports as real pages, with no placeholder left", add:
     ```ts
       it('serves the Guide at /insights/guide and /insights/guide/:slug from one lazy parent (v236)', async () => {
         const route = routes.find((item) => item.path === 'insights/guide');
         expect(route?.canMatch).toEqual([authGuard]);
         const [parent, ...rest] = await route!.loadChildren!() as Routes;
         expect(rest).toEqual([]);
         expect(parent.children?.map((child) => child.path)).toEqual(['', ':slug']);
         for (const child of parent.children ?? []) expect(await child.loadComponent!()).toBeDefined();
       });

       it('declares the Guide after Reports, so the Insights sections keep rail order', () => {
         const at = (path: string) => routes.findIndex((r) => r.path === path);
         expect(at('insights/guide')).toBe(at('insights/reports') + 1);
       });
     ```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/breadcrumb.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/app.routes.spec.ts`
Expected: FAIL — every new Guide row (no `insights/guide` route, no Guide section). The breadcrumb section case also fails until the nav entry exists.

- [ ] **Step 3: Add the nav section**

In `frontend/src/app/shell/nav.ts`, the Insights entry's `sections` becomes:

```ts
    sections: [
      { path: '/insights/analytics', label: 'Analytics' },
      { path: '/insights/research', label: 'Research' },
      { path: '/insights/reports', label: 'Reports' },
      { path: '/insights/guide', label: 'Guide' },
    ],
```

- [ ] **Step 4: Add the route**

In `frontend/src/app/app.routes.ts`, directly after the `insights/reports` entry (it ends at line ~152 with `loadChildren: () => import('./workspaces/reports/reports.routes').then((m) => m.reportsRoutes),` and `},`), insert:

```ts
  // v236 (spec v215): the guidebook. One lazy parent holds the chapter
  // store; its children are the bare section ('', first chapter) and ':slug'.
  {
    path: 'insights/guide', canMatch: [authGuard], title: 'Guide',
    data: { subtitle: 'How the bot finds, builds, sizes and closes trades' },
    loadChildren: () => import('./workspaces/guide/guide.routes').then((m) => m.guideRoutes),
  },
```

The `:slug` child reaches `Guide.slug` through `withComponentInputBinding()`, already on in `app.config.ts`; nothing else changes there.

- [ ] **Step 5: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/breadcrumb.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/app.routes.spec.ts --include src/app/shell/section-tabs.spec.ts --include src/app/shell/phone-tab-bar.spec.ts`
Expected: PASS. A 60 s "Timeout waiting for worker" is the known flake: re-run the same command once. If another spec fails on a hard-coded Insights list, add Guide to it in rail order in this task (same rule) and name the file in the commit.

- [ ] **Step 6: Confirm the binding and the build**

Run: `git grep -n "withComponentInputBinding" -- frontend/src/app/app.config.ts`
Expected: the import and the `provideRouter(routes, withComponentInputBinding(), …)` call (so the `:slug` param reaches the page's `slug` input).

Run: `cd frontend && npx ng build --configuration development`
Expected: build succeeds, with a lazy chunk for `guide.routes`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/app.routes.ts frontend/src/app/shell/nav.ts frontend/src/app/app.routes.spec.ts frontend/src/app/shell/nav.spec.ts frontend/src/app/shell/more-sheet.spec.ts frontend/src/app/shell/breadcrumb.spec.ts frontend/src/app/shell/palette/palette-items.spec.ts
git commit -m "feat(guide): Insights -> Guide route and nav section, Insights specs updated (v236 V236-7)"
```

