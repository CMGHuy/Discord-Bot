# v236 — Guide page (frontend half of spec v215 Plan A): Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V236-4" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan A ("Foundation"), frontend half.
**Depends on:** v235 — [2026-11-18-v235-guide-foundation_0-index.md](2026-11-18-v235-guide-foundation_0-index.md), merged first (API V235-5, anchor fixture and `figure_names()` V235-6, `guide_sources.py` V235-7).
**Brief:** `.superpowers/briefs/2026-11-18-v235-guide-foundation.md`

## Goal

Plan v235 builds everything behind the guidebook — the chapter loader, the
placeholder whitelist, the two read-only `/api/v1/guide` routes and the
freshness checks — but leaves nothing a trader can open. Spec v215's Plan A
promised a page, and the 20-task cap forced it into its own plan: on
2026-11-18 the partner split Plan A in two, backend in v235 and the page here.
Without this plan the API answers nobody, and the question that started the
spec — what does a badge, the stop-distance cap or a quiet day mean — still
has no answer inside the admin site.

Once v236 ships, **Insights → Guide** is the fourth Insights section
(`/insights/guide`, `/insights/guide/<slug>`). It shows chapters 1 "What the
bot is (and isn't)" with the full education-not-advice notice, 3 "The scan
pipeline, end to end" with its diagram (each box links to its chapter once
that chapter exists) and 12 "Glossary". Every chapter carries a "Reviewed for
bot vX.Y.Z" stamp, every heading a permalink, and
`/insights/guide/<slug>#<anchor>` opens the chapter scrolled to the heading.
The table of contents is a sticky rail on desktop, a drawer on tablet and a
chapter picker on phone; search runs in the browser over titles, headings and
loaded text, with an empty state. The `?` link component
(`GuideLinkComponent`) exists and is checked against the anchor fixture, ready
for Plan C to place.

How it works in idea: a route-scoped `GuideStore` fetches the chapter index
once (it carries every heading, so heading search and the TOC work before any
chapter loads) and each chapter body on demand. `marked` turns the resolved
Markdown into HTML that is bound through Angular's sanitiser — never bypassed
— so a chapter can never inject script. The sanitiser strips `id`, so the page
sets each heading's anchor afterwards from the API's heading list, in document
order; the anchor algorithm lives only in the backend. A figure marker line
`<!-- figure:<name> -->` splits the chapter so a registered Angular component
(the inline-SVG pipeline diagram) renders between Markdown segments.

Left alone: the backend (all of it is v235), chapters 2 and 4–11 (Plans B and
C), `?` placements on other pages (Plan C), every other Insights section, and
all trading behaviour.

Success: the page renders chapters 1, 3 and 12 at 390, 820 and 1440 px with no
horizontal overflow and 44px touch targets on phone and tablet (Playwright
layout check, V236-11); every deep link scrolls to its heading; the specs for
store, link, anchors, Markdown sanitising (`details`/`summary` survive, script
does not), search hit and empty state, and TOC mode per width are green; the
four Insights route/nav specs and `workspace-consistency.spec.ts` list the new
page; CI is green (V236-12).

## Architecture

- **Client** (V236-1): models in `api/models.ts`, two `ApiClient` methods, and
  `stores/guide.store.ts` (`signalStore`, provided by the guide route, not
  root).
- **Link component** (V236-2): `ui/guide-link.ts` plus
  `workspaces/guide/guide-anchors.spec.ts`, which checks every literal
  `sb-guide-link target="…"` against v235's generated `guide-anchors.json`.
- **Page** `frontend/src/app/workspaces/guide/`: `guide-markdown.ts` (segments,
  anchors, scroll, internal links) and `guide-figures.ts` (the registry
  `figure_names()` parses) in V236-3; `guide.routes.ts` and `guide.ts` in
  V236-4; `guide-search.ts` in V236-5; the TOC at three widths and search
  wired into `guide.ts` in V236-6.
- **Shell** (V236-7): `insights/guide` in `app.routes.ts`, the nav section, and
  the four hard-coded Insights specs.
- **Content** (V236-8..10): `docs/guide/01-what-it-is.md`, `03-pipeline.md`
  with `pipeline-diagram.ts`, `12-glossary.md`; each regenerates
  `guide-anchors.json` with `python scripts/dev/guide_anchors.py`.
- **Layout check** (V236-11): `scripts/dev/guide_layout_check.py` (Playwright,
  three widths) and its result note.

**Tech stack:** Angular ~21.2, `@ngrx/signals`, `marked` 18.2.1 (exact pin),
vitest via `ng test`; Markdown chapters with YAML front matter (v235 loader);
Python 3.11 + Playwright for the layout check only.

## Global Constraints

v235's `## Global Constraints` bind here wherever they touch the frontend or
the chapters (anchor algorithm, chapter format, placeholders, provenance
labels, complexity < 15, `.env` login). Restated and added for this plan:

- `**Bump:**` ui minor; `VERSION.json` (ui 1.44.1 / bot 2.19.2 today) is computed at `/close-out`, never in a task.
- `marked` is added at the exact version `18.2.1` (`npm install marked@18.2.1 --save-exact`) with `package-lock.json` updated, so CI `npm ci` passes.
- Chapter HTML is bound with `[innerHTML]` through Angular's sanitiser; no `bypassSecurityTrust*` anywhere for chapter text. A spec proves `details`/`summary` survive and `<script>`/`on*` attributes do not.
- The browser never computes an anchor: ids come from the API's heading list, set on rendered `.md > h2`/`.md > h3` in document order after sanitising.
- `guide-anchors.json` is generated by `python scripts/dev/guide_anchors.py` (V235-6), never hand-edited; every chapter task regenerates it and commits it with the chapter.
- `guide-figures.ts` keeps the literal `export const GUIDE_FIGURES: Record<string, Type<unknown>> = { … };` with no nested braces inside it (V235-6's `figure_names()` parses keys up to the first `}`).
- Every UI task covers mobile (< 640), tablet (640–1023) and desktop (≥ 1024): touch targets use `--hit-min` / `.sb-hit` (44px on coarse pointer or below 1024px) without growing their row (commit 2a11a416 pattern); tables and code blocks scroll inside themselves; no `<h1` in workspace files (`sb-page` owns it); `sb-panel` for panels; tokens only, no off-scale px.
- The page's `sb-async` wrapper passes `[staleAsOf]="null"`: the guide is reference text with no data age, and `workspace-consistency.spec.ts` (v85 D30) requires every fetching page to declare its freshness marker.
- `workspace-consistency.spec.ts` `PAGE_ROUTES` gains `'guide/guide.ts'` (after `'gallery/gallery.ts'`) in the same task that creates `guide.routes.ts` (V236-4); that spec fails the moment the routes file exists.
- Chapters: `docs/guide/NN-<slug>.md`, `reviewed_for: 2.19.2`, body opens with `> **In plain words** …`, developer boxes `<details><summary>Under the hood</summary> … </details>`, `##`/`###` headings only and never inside `<details>`; no rule number typed into prose (placeholders only); performance figures carry their provenance label.
- Every function at cyclomatic complexity < 15 (`scripts/dev/complexity_gate.py`).
- Layout check login uses `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded inside the script and never printed.
- Per-task verification is the narrow run: `cd frontend && npx ng test --watch=false --include <spec>` or `python scripts/dev/testrun.py file <test>`. A 60 s "Timeout waiting for worker" is a known flake: re-run the same command once. Only V236-12 relies on the full suite, run by CI.
- New Python tests land in an existing suite (`tooling`); no new `tests/` directory.

## Parallelisation

Mostly one stream: V236-3..V236-6 build one page in shared files, and the
chapters need the page's figure registry and the shell route.

Sequential edges and why:

- v235 merged → V236-1, V236-2: the store calls V235-5's routes; the anchor spec reads V235-6's `guide-anchors.json`.
- V236-1 → V236-4, V236-5: the page injects `GuideStore`; search types against `GuideChapterSummary`/`GuideChapter`.
- V236-3 → V236-4: `guide.ts` imports `renderGuideSegments`, `applyHeadingAnchors`, `scrollToAnchor`, `internalGuideUrl` and `GUIDE_FIGURES`.
- V236-4 → V236-6: both modify `guide.ts` and `guide.spec.ts`; V236-6 keeps V236-4's `div.guide-layout` / `article.guide-chapter` structure and spec helpers.
- V236-6 → V236-6b: both modify `guide.ts` and `guide.spec.ts`.
- V236-5 → V236-6b: V236-6b wires `buildGuideSearchIndex` / `searchGuide` / `snippetFor` into the page.
- V236-4 → V236-7: the app route mounts `guideRoutes`.
- V236-3 → V236-9: V236-9 adds `pipeline` to `GUIDE_FIGURES` (V235-6's content test checks every figure marker against that file).
- V236-8 → V236-9 → V236-10: all three regenerate and modify `guide-anchors.json`; one at a time.
- V236-6, V236-6b, V236-7, V236-8, V236-9, V236-10 → V236-11: the layout check needs the full page, the route and all three chapters.
- V236-11 → V236-12: last.

Groups that may run side by side (disjoint files, no contract between them):

- {V236-1, V236-2, V236-3} once v235 is merged.
- {V236-4, V236-5} (V236-5 creates only `guide-search.ts` and its spec).
- {V236-8} beside V236-4..V236-7 (Markdown and the fixture only).

## Task ledger

| Id | Title | Part | Model | Files | Produces (consumed later) |
|---|---|---|---|---|---|
| V236-1 | `marked`, API client, models and `GuideStore` | 1 | sonnet | M `frontend/package.json`, M `frontend/package-lock.json`, M `frontend/src/app/api/models.ts`, M `frontend/src/app/api/api-client.ts`, C `frontend/src/app/stores/guide.store.ts`, C `frontend/src/app/stores/guide.store.spec.ts` | models `GuideHeading {level: number; text: string; anchor: string}`, `GuideChapterSummary {slug; title; order: number; reviewed_for: string; headings: GuideHeading[]}`, `GuideIndex {chapters: GuideChapterSummary[]}`, `GuideChapter {slug; title; reviewed_for; markdown: string}`; `ApiClient.guide(): Observable<GuideIndex>`, `ApiClient.guideChapter(slug: string): Observable<GuideChapter>`; `GuideStore` (signalStore, route-provided) state `{chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>, status: 'idle' \| 'loading' \| 'ready' \| 'error', error: string \| null, chapterStatus: Record<string, 'loading' \| 'ready' \| 'missing' \| 'error'>}`, computed `firstSlug(): string \| null`, methods `ensureLoaded(): Promise<void>`, `loadChapter(slug: string): void` |
| V236-2 | `GuideLinkComponent` and the anchor spec | 1 | sonnet | C `frontend/src/app/ui/guide-link.ts`, C `frontend/src/app/ui/guide-link.spec.ts`, C `frontend/src/app/workspaces/guide/guide-anchors.spec.ts` | `interface GuideTarget {slug: string; anchor: string \| null}`; `parseGuideTarget(target: string): GuideTarget`; `GuideLinkComponent` selector `sb-guide-link`, inputs `target = input.required<string>()`, `label = input<string>('Open the guide')`; renders `a.guide-link.sb-hit` `?` to `/insights/guide/<slug>` with `fragment` = anchor, 44px hit area via `::after` (no row growth); the anchor spec checks every literal `sb-guide-link target="…"` under `frontend/src/app` (specs excluded) against `guide-anchors.json` and fails on a bound `[target]` |
| V236-3 | Markdown helpers and figure registry | 1 | sonnet | C `frontend/src/app/workspaces/guide/guide-markdown.ts`, C `frontend/src/app/workspaces/guide/guide-markdown.spec.ts`, C `frontend/src/app/workspaces/guide/guide-figures.ts` | `type GuideSegment = {kind: 'md'; html: string} \| {kind: 'figure'; name: string}`; `renderGuideSegments(markdown: string): GuideSegment[]` (splits on `<!-- figure:<name> -->` lines, `marked.parse` per Markdown segment); `applyHeadingAnchors(container: HTMLElement, headings: readonly GuideHeading[], basePath = ''): void` (sets `id` on `.md > h2`/`.md > h3` in document order, appends one `a.permalink.sb-hit` to `basePath#anchor`); `scrollToAnchor(container: HTMLElement, anchor: string): boolean`; `internalGuideUrl(href: string, slug: string \| null): string \| null`; `GUIDE_FIGURES: Record<string, Type<unknown>> = {}` (literal form, no nested braces) |
| V236-4 | Guide routes and page | 1 | sonnet | C `frontend/src/app/workspaces/guide/guide.routes.ts`, C `frontend/src/app/workspaces/guide/guide.ts`, C `frontend/src/app/workspaces/guide/guide.spec.ts`, M `frontend/src/app/workspaces/workspace-consistency.spec.ts` (`PAGE_ROUTES` += `'guide/guide.ts'`) | `guideRoutes: Routes` (componentless parent with `providers: [GuideStore]`, `runGuardsAndResolvers: 'always'`, `data: routeData('Guide', onEvents())`, `resolve.ready`; children `''` (first chapter in place, no redirect) and `':slug'`, both `Guide`); `Guide` selector `sb-guide`, input `slug = input<string>()`; exported `GUIDE_NOTICE: string`; template keeps one `[page-primary]` `div.guide-layout` holding `article.guide-chapter`; `sb-async` with `[staleAsOf]="null"`; stamp "Reviewed for bot v<reviewed_for>"; footer notice; spec helpers `openGuide`/`settle`/`INDEX`/`BODY` in `guide.spec.ts` |
| V236-5 | Guide search module | 2 | sonnet | C `frontend/src/app/workspaces/guide/guide-search.ts`, C `frontend/src/app/workspaces/guide/guide-search.spec.ts` | `interface GuideSearchEntry {slug: string; chapterTitle: string; anchor: string \| null; text: string}`; `plainText(markdown: string): string`; `splitSections(markdown: string): string[]`; `buildGuideSearchIndex(chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>): GuideSearchEntry[]`; `searchGuide(entries: GuideSearchEntry[], query: string, limit = 20): GuideSearchEntry[]` (every word, case-insensitive, document order, `[]` for blank); `snippetFor(text: string, query: string, width = 120): string` |
| V236-6 | Contents rail, drawer and picker | 2 | sonnet | M `frontend/src/app/workspaces/guide/guide.ts`, M `frontend/src/app/workspaces/guide/guide.spec.ts` | DOM the layout check reads: `nav.guide-rail` (≥ 1024, sticky), `button.guide-contents` + `sb-drawer` (640–1023), `sb-select.guide-picker` (< 640) |
| V236-6b | Search wired into the page | 2 | sonnet | M `frontend/src/app/workspaces/guide/guide.ts`, M `frontend/src/app/workspaces/guide/guide.spec.ts` | `.guide-search`, `a.guide-result`, `p.guide-no-match` (`No section matches “<query>”`); typing a non-blank query loads chapter bodies not yet requested (never re-fetches a chapter that has a status) |
| V236-7 | Routes, nav and the four hard-coded Insights specs | 2 | sonnet | M `frontend/src/app/app.routes.ts`, M `frontend/src/app/app.routes.spec.ts`, M `frontend/src/app/shell/nav.ts`, M `frontend/src/app/shell/nav.spec.ts`, M `frontend/src/app/shell/more-sheet.spec.ts`, M `frontend/src/app/shell/breadcrumb.spec.ts`, M `frontend/src/app/shell/palette/palette-items.spec.ts` | route `insights/guide` (title `Guide`, subtitle `How the bot finds, builds, sizes and closes trades`, `canMatch: [authGuard]`, `loadChildren` → `guideRoutes`); nav section `{ path: '/insights/guide', label: 'Guide' }` after Reports |
| V236-8 | Chapter 1: What the bot is (and isn't) | 3 | sonnet | C `docs/guide/01-what-it-is.md`, M `frontend/src/app/workspaces/guide/guide-anchors.json` | slug `what-it-is`, order 1; anchors include `the-notice` (the full education-not-advice notice) and `swing-horizons` (`{{horizons.table}}`) |
| V236-9 | Chapter 3: the pipeline and its diagram | 3 | sonnet | C `docs/guide/03-pipeline.md`, C `frontend/src/app/workspaces/guide/pipeline-diagram.ts`, C `frontend/src/app/workspaces/guide/pipeline-diagram.spec.ts`, M `frontend/src/app/workspaces/guide/guide-figures.ts`, M `frontend/src/app/workspaces/guide/guide-anchors.json` | slug `pipeline`, order 3; `GuidePipelineDiagram` selector `sb-guide-pipeline-diagram` (inline SVG, theme tokens, boxes link to `/insights/guide/<slug>` only when that slug is in `GuideStore.chapters()`); `GUIDE_FIGURES.pipeline` |
| V236-10 | Chapter 12: Glossary | 3 | sonnet | C `docs/guide/12-glossary.md`, M `frontend/src/app/workspaces/guide/guide-anchors.json` | slug `glossary`, order 12; one `###` heading per term (one anchor each) |
| V236-11 | Layout check at three widths | 3 | sonnet | C `scripts/dev/guide_layout_check.py`, C `tests/scripts/test_guide_layout_check.py`, C `docs/superpowers/results/2026-11-18-v236-guide-layout.md` | `guide_layout_check.main(argv=None) -> int` (Playwright; widths 390, 820, 1440; checks no horizontal overflow, TOC mode per width, hit targets ≥ 44px on 390/820, deep-link scroll); screenshots under `logs/v236-layout/` |
| V236-12 | Full-suite verification | 3 | haiku | none (run only; CI) | push, then watch the CI run green (`0 failed`, `0 xfailed`), frontend `frontend-test` job included |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-18-v236-guide-page_1-client-page.md` | V236-1..V236-4 | `marked`, client and store, `GuideLinkComponent` and anchor spec, Markdown helpers and figure registry, routes and page |
| 2 | `2026-11-18-v236-guide-page_2-contents-nav.md` | V236-5, V236-6, V236-6b, V236-7 | search module, TOC at three widths, search wired in, app route, nav and the Insights specs |
| 3 | `2026-11-18-v236-guide-page_3-chapters.md` | V236-8..V236-12 | chapters 1, 3 (with diagram) and 12, layout check, CI full suite |

## Handoff

Binding on every part writer (controller and partner decisions, 2026-11-18):

1. **Origin.** Plan v235's frontend tasks moved here at the 20-task cap (partner, 2026-11-18; v235 `## Handoff` item 9). Old ids map V235-9 → V236-1, V235-10 → V236-2, V235-11 → V236-3 + V236-4, V235-12 → V236-5 + V236-6, V235-13..V235-18 → V236-7..V236-12. Drafts written against the old ids must be renamed (e.g. V235-13 → V236-7, V235-15 → V236-9, V235-17 → V236-11). **V235-5..V235-8 stay v235 ids** (API, fixture, `guide_sources.py`, close-out rule) and are cited as such.
2. **`marked`** is pinned exactly at `18.2.1` with `package-lock.json` updated; chapter HTML goes through Angular's sanitiser, never `bypassSecurityTrust*` (v235 Handoff 3).
3. **UI** covers mobile, tablet and desktop in every UI task; V236-7 updates the four hard-coded Insights specs (`app.routes.spec.ts`, `shell/nav.spec.ts`, `shell/more-sheet.spec.ts`, `shell/breadcrumb.spec.ts`) (v235 Handoff 7).
4. **The pipeline diagram is an Angular component**, not a served `.svg`: inline-SVG template in `pipeline-diagram.ts` using theme tokens (precedent `ui/plan-lifecycle-diagram.ts`), placed by a `<!-- figure:pipeline -->` line; no `docs/guide/assets/`.
5. **Anchors are applied after sanitising**, from the API's heading list, in document order (V236-3, V236-4); V235-6's content test forbids headings inside `<details>` so the two orders agree.
6. **Placeholders resolve per request** on the server; the client never sees `{{…}}` and caches bodies only in the route-scoped store.
7. **Files outside the moved rows, found by the previous writer:** V236-4 also edits `frontend/src/app/workspaces/workspace-consistency.spec.ts` (`PAGE_ROUTES` += `'guide/guide.ts'`); the page's `sb-async` passes `[staleAsOf]="null"` (D30 freshness rule). Both are in the ledger now.
8. **Splits of the old tasks** (each under 20 KB, never compressed): V236-3 = Markdown helpers + figure registry (~11 KB); V236-4 = routes + page (~20 KB: tighten prose, never code). V236-5 = search module + spec (~9 KB); V236-6 = TOC rail/drawer/picker + search wired into the page (~16 KB). Drafts in the controller's scratchpad: `t11.md` (→ V236-3/4) and `t12.md` (→ V236-5/6), written against old ids.
9. **Layout check artefacts** carry the v236 number: result note `docs/superpowers/results/2026-11-18-v236-guide-layout.md`, screenshots `logs/v236-layout/` (the moved row said v235; corrected here).
10. **Part 1 is partly on disk**: `_1-client-page.md` holds V236-1 and V236-2 complete; append V236-3 and V236-4 there.
11. **Verification**: per-task narrow runs only; V236-12 is the one full-suite task, run by CI after the push.
9. **Part 2 split (2026-11-18)**: V236-6 came to ~20.4 KB, so search wiring moved to V236-6b (runs after V236-6; same files). V236-7 also edits `shell/palette/palette-items.spec.ts` (its RAIL/route lists hard-code the Insights sections).
