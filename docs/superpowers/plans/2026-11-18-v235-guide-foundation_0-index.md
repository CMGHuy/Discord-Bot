# v235 — Guide foundation (Plan A of spec v215): Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V235-7" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan A ("Foundation") of its `## Delivery: one spec, three plans` table only.
**Brief:** `.superpowers/briefs/2026-11-18-v235-guide-foundation.md`

## Goal

Nothing in the admin site explains the bot. A trader who acts on the alerts
cannot look up what a badge, the stop-distance cap or a quiet day means; the
explanation that exists (about 2,800 lines under `docs/strategy/`,
`docs/strategy-types/`, `docs/features/`) is written for developers and is
partly stale by its own admission. On 2026-11-06 the partner asked for a
guidebook page under Insights that serves newcomers, traders and developers at
once and stays current whenever the bot changes. Spec v215 designs that page
and splits delivery into three plans; this is Plan A, the foundation.

Once Plan A ships, **Insights → Guide** (`/insights/guide`, fourth Insights
section) is live on mobile, tablet and desktop with three chapters: 1 "What the
bot is (and isn't)" (with the full education-not-advice notice), 3 "The scan
pipeline, end to end" (one diagram, each box linking to its chapter when that
chapter exists) and 12 "Glossary". The page has a table of contents (sticky
rail on desktop, drawer on tablet, chapter picker on phone), client-side
search with an empty state, deep links to every heading and a "Reviewed for
bot vX.Y.Z" stamp per chapter. The reusable `?` link component
(`GuideLinkComponent`) exists, but placing it on other pages is Plan C.

How it works: chapters are Markdown files in `docs/guide/` with YAML front
matter (`title`, `slug`, `order`, `reviewed_for`, `sources`). A loader parses
them once per process; a **fixed whitelist** of `{{name}}` placeholders fills
in live values (config limits, horizons, level families, gates, alert
frequency with provenance) at request time, so no rule number is ever typed
into prose and no unlisted config key (a token, an eToro key) can ever be
rendered. Two read-only `/api/v1/guide` routes serve the index and one
resolved chapter; the Angular page renders Markdown with `marked` through
Angular's sanitiser. Freshness has three layers: a pytest content test (every
placeholder resolves, every `sources:` path and symbol still exists, horizons
all appear, `reviewed_for` no newer than `VERSION.json`), a generated anchor
fixture shared by the backend test and a frontend spec, and a `/close-out`
rule backed by `scripts/dev/guide_sources.py` that names the chapters a diff
touches.

Deliberately untouched: chapters 2 and 4–11 (Plans B and C), the per-strategy
cards and `docs/guide/strategies/` (Plan B), `?` link placements (Plan C),
the developer docs under `docs/strategy*`/`docs/features/`, and all trading
behaviour. The one change under `swingbot/core` is extracting the hard-coded
90-day correlation window into a named constant, behaviour-preserving.

Success: `/insights/guide` renders chapters 1, 3 and 12 at all three widths
(Playwright check with no horizontal overflow and 44px targets), every deep
link scrolls to its heading, the content test and anchor test pass with Plans
B and C absent, an unknown placeholder fails the content test and returns a
500 (never raw `{{…}}`), and `tests/hooks/test_codex_mirror.py` is green after
the `/close-out` and `CLAUDE.md` changes.

## Architecture

- **Backend package `swingbot/admin/guide/`.** `chapters.py` (loader, front
  matter via `yaml.safe_load`, headings, anchors), `placeholders.py`
  (registry, `resolve`, provenance label), `live_risk.py` (risk and sizing
  placeholders), `live_market.py` (horizons, level families, gates, alerts per
  week, registered strategy keys). The registry is one read-only mapping
  merged from `RISK_PLACEHOLDERS` and `MARKET_PLACEHOLDERS`; nothing resolves
  by attribute name.
- **API `swingbot/admin/api_v1/guide.py`**, registered in `register()`'s
  import tuple. Chapter files are cached per process (`lru_cache`), but
  placeholders resolve per request so live values (alerts per week) stay
  live. Viewer-readable: not in `ADMIN_ONLY_PREFIXES`.
- **Content** in `docs/guide/NN-<slug>.md` (shipped in the image by
  `COPY . .`). Figures are marked in Markdown with an HTML comment line
  `<!-- figure:<name> -->`; the page renders the matching Angular component
  (the pipeline diagram is an inline-SVG component using theme tokens, the
  `ui/plan-lifecycle-diagram.ts` precedent).
- **Frontend** `frontend/src/app/workspaces/guide/` (routes, page, Markdown
  renderer, search, figure registry), `stores/guide.store.ts`,
  `ui/guide-link.ts`. Angular's sanitiser drops `id` attributes, so heading
  anchors are applied to the rendered `h2`/`h3` elements after binding, in
  order, from the backend's heading list.
- **Freshness**: `tests/admin/test_guide_content.py`;
  `scripts/dev/guide_anchors.py` writes
  `frontend/src/app/workspaces/guide/guide-anchors.json`, checked by both the
  backend test and a frontend spec; `scripts/dev/guide_sources.py`; the
  `/close-out` Step 5b guide check.

**Tech stack:** Python 3.11, Flask, PyYAML 6.0.3 (promoted to runtime),
pytest; Angular ~21.2, `@ngrx/signals`, `marked` (exact pin), vitest;
Playwright (layout check only).

## Global Constraints

- `**Bump:**` ui minor, bot patch. `VERSION.json` is ui 1.44.1 / bot 2.19.2 today; the numbers are computed at `/close-out`, never in a task.
- No change to trading behaviour. The only `swingbot/core` edit is the correlation window constant, behaviour-preserving (existing `tests/edge/test_edge_correlation.py` stays green unchanged).
- Placeholders: only names in the registry resolve; no expressions, no generic `config.<KEY>` access. An unknown name raises `UnknownPlaceholder` at load/resolve time; the API logs the name and returns 500 `guide_placeholder`, never the raw `{{…}}` text.
- Every performance figure (ExpR, win rate, badge, alerts per week) renders with its provenance label: source (backtest window, validation, or live paper book), N, run date, costs included or not, "before tax". A badge never renders without its N and date.
- Masked horizons and strategies are read at call time through `live_horizons()` / `admits()`, never a hard-coded `"1w"`.
- Front matter: `yaml.safe_load` only; PyYAML is pinned in the runtime section of `requirements.txt` (`PyYAML==6.0.3`).
- Frontend: `marked` added with an exact version (no `^`/`~`) and `package-lock.json` updated so CI `npm ci` passes; Markdown bound with `[innerHTML]` through Angular's sanitiser (no `bypassSecurityTrust*` anywhere for chapter text); `details`/`summary` survive, proved by a spec.
- Every UI task covers mobile (< 640), tablet (640–1023) and desktop (≥ 1024): touch targets use `--hit-min` / `.sb-hit` (44px on coarse pointer or < 1024px) without growing their row (commit 2a11a416 pattern); no `<h1` in workspace files (`sb-page` owns it); `sb-panel` for panels; tokens only, no off-scale px.
- Chapters: `docs/guide/NN-<slug>.md`; `reviewed_for` = `2.19.2` (no newer than `VERSION.json` bot); body opens with `> **In plain words** …`; developer boxes are `<details><summary>Under the hood</summary> … </details>`; headings are `##`/`###` only and never inside `<details>`; chapters 7–9 (Plan B) carry no bare `N%`.
- Anchor algorithm (backend and fixture, final): lowercase; drop every character outside `[a-z0-9 _-]`; runs of whitespace become `-`; collapse repeated `-`; strip leading/trailing `-`; empty becomes `section`; a repeat within one chapter gets `-2`, `-3`, ….
- Every function at cyclomatic complexity < 15 (`scripts/dev/complexity_gate.py`).
- Login in any browser check uses `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded inside the script and never printed.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`, `cd frontend && npx ng test --watch=false --include <spec>`); only V235-18 runs the full suite.
- New backend tests land in existing suites (`admin`, `admin-core`, `tooling`, `edge`); no new `tests/` directory.

## Parallelisation

Two streams can run side by side once V235-2 is merged: **backend/freshness** (V235-1, V235-3..V235-8) and **frontend** (V235-9..V235-13). They share no files; the contract between them is the JSON shape in the ledger (V235-5) and the anchor fixture (V235-6).

Sequential edges and why:

- V235-1 → V235-3: `correlation.window` reads `correlation.DEFAULT_WINDOW`.
- V235-2 → V235-3, V235-5, V235-6, V235-7: all import `chapters.py`.
- V235-3 → V235-4: both modify `placeholders.py` (registry merge).
- V235-4 → V235-5, V235-6: the API and the content test need the full whitelist.
- V235-6 → V235-10: the anchor spec reads `guide-anchors.json`, created by V235-6.
- V235-7 → V235-8: the `/close-out` rule names `scripts/dev/guide_sources.py`.
- V235-9 → V235-11: the page uses `GuideStore`, models and `marked`.
- V235-11 → V235-12 and V235-13: V235-12 edits `guide.ts` (same file); V235-13 imports `guide.routes.ts`. V235-12 and V235-13 touch disjoint files and may run in parallel.
- V235-5, V235-6, V235-11 → V235-14..V235-16: chapters are checked by the content test and regenerate the anchor fixture; V235-15 adds a figure to the registry V235-11 creates.
- V235-14 → V235-15 → V235-16: each regenerates `guide-anchors.json` (same file); the glossary links into chapters 1 and 3.
- V235-17 after every UI and chapter task; V235-18 last.

## Task ledger

| Id | Title | Part | Model | Files | Produces (consumed later) |
|---|---|---|---|---|---|
| V235-1 | Correlation window constant | 1 | haiku | M `swingbot/core/edge/correlation.py`, M `tests/edge/test_edge_correlation.py` | `correlation.DEFAULT_WINDOW = 90` (module constant beside `DEFAULT_THRESHOLD`); `returns_corr(df_a, df_b, window: int = DEFAULT_WINDOW)`, `cluster_exposure(..., *, window: int = DEFAULT_WINDOW, ...)`; behaviour unchanged |
| V235-2 | Chapter loader and runtime PyYAML | 1 | sonnet | M `requirements.txt`, C `swingbot/admin/guide/__init__.py`, C `swingbot/admin/guide/chapters.py`, C `tests/admin/test_guide_chapters.py` | `class GuideFormatError(ValueError)`; `@dataclass(frozen=True) Heading(level: int, text: str, anchor: str)`; `@dataclass(frozen=True) Chapter(slug: str, title: str, order: int, reviewed_for: str, sources: tuple[str, ...], body: str, headings: tuple[Heading, ...], path: Path)`; `guide_dir() -> Path` (`Path(config._PROJECT_ROOT) / "docs" / "guide"`, read at call time); `anchor_for(text: str, seen: dict[str, int]) -> str`; `extract_headings(markdown: str) -> tuple[Heading, ...]` (`##`/`###` outside code fences); `split_source(entry: str) -> tuple[str, str \| None]` (`"path:symbol"` → `(path, symbol)`); `parse_chapter(path: Path) -> Chapter`; `load_chapters(root: Path \| None = None) -> list[Chapter]` (top-level `NN-*.md` only, sorted by `order`; duplicate slug or order raises `GuideFormatError`); `FIGURE_RE = re.compile(r"^<!-- figure:([a-z0-9-]+) -->$", re.M)` |
| V235-3 | Placeholder registry, resolver and risk placeholders | 1 | sonnet | C `swingbot/admin/guide/placeholders.py`, C `swingbot/admin/guide/live_risk.py`, C `tests/admin/test_guide_placeholders.py` | `PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")`; `class UnknownPlaceholder(KeyError)` with `.name: str`; `PLACEHOLDERS: Mapping[str, Callable[[], str]]` (`MappingProxyType`); `names_in(markdown: str) -> list[str]`; `resolve(markdown: str) -> str`; `provenance_label(*, source: str, n: int, run_date: str, costs_included: bool) -> str` (always ends "before tax"); `live_risk.RISK_PLACEHOLDERS: dict[str, Callable[[], str]]` with names `MAX_STOP_LOSS_PCT`, `MIN_STOP_DISTANCE_PCT`, `CLAMP_STOP_TO_HARD_CAP`, `RISK_PER_TRADE_PCT`, `RISK_PER_TRADE_PCT.max`, `MAX_RISK_AMOUNT_ABSOLUTE`, `PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`, `POSITION_SIZING_MODE`, `correlation.threshold`, `correlation.window`, `correlation.sector_fallback`, `sizing.kelly_cap`, `sizing.risk_floor`, `sizing.risk_ceiling`, `sizing.gap` (table from `SHORT_GAP_SIZING`, `LONG_GAP_SIZING`, `gap_sizing.LOOKBACK`, `MIN_UP_GAPS`, `MIN_DOWN_GAPS`, `RULE_GAP`), `version.bot` |
| V235-4 | Market placeholders and alerts per week | 1 | sonnet | C `swingbot/admin/guide/live_market.py`, M `swingbot/admin/guide/placeholders.py`, C `tests/admin/test_guide_live_market.py` | `live_market.MARKET_PLACEHOLDERS` with names `levels.families` (`ALL_STRATEGY_FAMILIES`, AVWAP marked "only when AVWAP_LEVELS_ENABLED"), `CLUSTER_TOLERANCE_PCT`, `horizons.table` (every `HORIZONS` key in `horizon_order()`, masked ones labelled "masked — research only" via `live_horizons()`), `gates.list` (from `STRATEGY_GATES`), `alerts.per_week` (mean over the last 8 full weeks of `opened_at`, with `provenance_label(source="live paper book", …)`; "no live alerts in the last 8 weeks" when empty); `live_market._load_trades: Callable[[], list[dict]]` and `live_market._now: Callable[[], datetime]` (module attributes, monkeypatchable); `registered_strategy_keys() -> tuple[str, ...]` (sorted union of `strategy.STRATEGY_FUNCS` and `STRATEGY_GATES` keys); `strategy_file_slug(key: str) -> str` (anchor rule, e.g. `"Break & Retest"` → `break-retest`); `PLACEHOLDERS` now merges both tables |
| V235-5 | Guide API routes and access rows | 1 | sonnet | C `swingbot/admin/api_v1/guide.py`, M `swingbot/admin/api_v1/__init__.py`, M `tests/admin/access_expectations.py`, C `tests/admin/test_api_v1_guide.py` | `GET /api/v1/guide` → `{"chapters": [{"slug", "title", "order", "reviewed_for", "headings": [{"level", "text", "anchor"}]}]}` (headings from the resolved body); `GET /api/v1/guide/<slug>` → `{"slug", "title", "reviewed_for", "markdown"}` (resolved), 404 `not_found`, 500 `guide_placeholder`; `guide._chapters() -> tuple[Chapter, ...]` (`lru_cache(maxsize=1)`), `guide.clear_cache() -> None` |
| V235-6 | Content test and anchor fixture | 2 | sonnet | C `tests/admin/test_guide_content.py`, C `scripts/dev/guide_anchors.py`, C `frontend/src/app/workspaces/guide/guide-anchors.json`, C `tests/scripts/test_guide_anchors.py` | `guide_anchors.build(root: Path \| None = None) -> dict` shaped `{"chapters": {"<slug>": ["<anchor>", …]}}` (slugs sorted, anchors in document order); `guide_anchors.main(argv=None) -> int` (writes the fixture, 2-space indent, trailing newline; `--check` exits 1 on drift); `FIXTURE = Path("frontend/src/app/workspaces/guide/guide-anchors.json")`; content checks: placeholders resolve, sources and `path:symbol` exist, horizons all in `horizons.table`, `reviewed_for` ≤ bot version, no heading inside `<details>`, figure names in `guide-figures.ts`, strategies file set equals `registered_strategy_keys()` once `docs/guide/strategies/` holds any `.md`, no bare `N%` in orders 7–9 |
| V235-7 | `guide_sources.py` diff helper | 2 | sonnet | C `scripts/dev/guide_sources.py`, C `tests/scripts/test_guide_sources.py` | `guide_sources.touched(paths: Iterable[str], chapters: list[Chapter]) -> list[tuple[Chapter, list[str]]]`; `changed_paths(rev_range: str) -> list[str]` (`git diff --name-only <base>..<head>`); `main(argv=None) -> int` (`python scripts/dev/guide_sources.py <base>..<head>` prints `NN-<slug>.md: <path>, …` per touched chapter, or `guide: no chapter sources touched`; exit 0; bad range exit 2); also scans `docs/guide/strategies/*.md` |
| V235-8 | `/close-out` guide rule, CLAUDE.md and mirrors | 2 | sonnet | M `.claude/skills/close-out/SKILL.md`, M `.agents/skills/close-out/SKILL.md` (generated by `python scripts/dev/sync_codex.py`), M `docs/claude/document-lifecycle.md`, M `CLAUDE.md`, M `AGENTS.md`, M one existing `docs/claude/*.md` that receives lines moved out of `CLAUDE.md` (V235-8 picks the section owner; no new `docs/claude/` file) | Step 5b text: run `guide_sources.py <base>..<head>`; a touched chapter gets its text updated where behaviour changed and `reviewed_for` bumped, or the close-out commit records `guide: no reader-visible change`; `CLAUDE.md` stays < 200 lines |
| V235-9 | `marked`, API client, models and `GuideStore` | 3 | sonnet | M `frontend/package.json`, M `frontend/package-lock.json`, M `frontend/src/app/api/models.ts`, M `frontend/src/app/api/api-client.ts`, C `frontend/src/app/stores/guide.store.ts`, C `frontend/src/app/stores/guide.store.spec.ts` | models `GuideHeading {level: number; text: string; anchor: string}`, `GuideChapterSummary {slug; title; order: number; reviewed_for: string; headings: GuideHeading[]}`, `GuideIndex {chapters: GuideChapterSummary[]}`, `GuideChapter {slug; title; reviewed_for; markdown: string}`; `ApiClient.guide(): Observable<GuideIndex>`, `ApiClient.guideChapter(slug: string): Observable<GuideChapter>`; `GuideStore` (signalStore) state `{chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>, status: 'idle' \| 'loading' \| 'ready' \| 'error', error: string \| null, chapterStatus: Record<string, 'loading' \| 'ready' \| 'missing' \| 'error'>}`, methods `ensureLoaded(): Promise<void>`, `loadChapter(slug: string): void` |
| V235-10 | `GuideLinkComponent` and the anchor spec | 3 | sonnet | C `frontend/src/app/ui/guide-link.ts`, C `frontend/src/app/ui/guide-link.spec.ts`, C `frontend/src/app/workspaces/guide/guide-anchors.spec.ts` | `parseGuideTarget(target: string): {slug: string; anchor: string \| null}`; `GuideLinkComponent` selector `sb-guide-link`, inputs `target = input.required<string>()`, `label = input<string>('Open the guide')`; renders a `?` link to `/insights/guide/<slug>` with `fragment` = anchor, `aria-label` = label, 44px hit area via `::after` (no row growth); the anchor spec checks every `sb-guide-link target="…"` literal in `frontend/src/app/**/*.ts` against `guide-anchors.json` |
| V235-11 | Guide page: Markdown render, sanitiser, anchors, deep links, figures | 3 | sonnet | C `frontend/src/app/workspaces/guide/guide.routes.ts`, C `frontend/src/app/workspaces/guide/guide.ts`, C `frontend/src/app/workspaces/guide/guide-markdown.ts`, C `frontend/src/app/workspaces/guide/guide-figures.ts`, C `frontend/src/app/workspaces/guide/guide.spec.ts`, C `frontend/src/app/workspaces/guide/guide-markdown.spec.ts` | `guideRoutes: Routes` (children `''` → first chapter, `':slug'`); `Guide` component selector `sb-guide`; `type GuideSegment = {kind: 'md'; html: string} \| {kind: 'figure'; name: string}`; `renderGuideSegments(markdown: string): GuideSegment[]` (splits on `<!-- figure:<name> -->`, `marked.parse` per Markdown segment); `applyHeadingAnchors(container: HTMLElement, headings: GuideHeading[]): void`; `GUIDE_FIGURES: Record<string, Type<unknown>>` (empty until V235-15); freshness stamp "Reviewed for bot v<reviewed_for>"; footer notice line |
| V235-12 | Guide page: table of contents at three widths and search | 3 | sonnet | M `frontend/src/app/workspaces/guide/guide.ts`, M `frontend/src/app/workspaces/guide/guide.spec.ts`, C `frontend/src/app/workspaces/guide/guide-search.ts`, C `frontend/src/app/workspaces/guide/guide-search.spec.ts` | `GuideSearchEntry {slug; chapterTitle; anchor: string \| null; text: string}`; `buildGuideSearchIndex(chapters: GuideChapterSummary[], bodies: Record<string, GuideChapter>): GuideSearchEntry[]`; `searchGuide(entries: GuideSearchEntry[], query: string, limit?: number): GuideSearchEntry[]`; TOC: sticky rail ≥ 1024, `Drawer` 640–1023, chapter picker < 640; empty state "No section matches “<query>”" |
| V235-13 | Routes, nav and the four hard-coded Insights specs | 3 | sonnet | M `frontend/src/app/app.routes.ts`, M `frontend/src/app/app.routes.spec.ts`, M `frontend/src/app/shell/nav.ts`, M `frontend/src/app/shell/nav.spec.ts`, M `frontend/src/app/shell/more-sheet.spec.ts`, M `frontend/src/app/shell/breadcrumb.spec.ts` | route `insights/guide` (title `Guide`, subtitle `How the bot finds, builds, sizes and closes trades`, `canMatch: [authGuard]`, `loadChildren` → `guideRoutes`); nav section `{ path: '/insights/guide', label: 'Guide' }` after Reports |
| V235-14 | Chapter 1: What the bot is (and isn't) | 4 | sonnet | C `docs/guide/01-what-it-is.md`, M `frontend/src/app/workspaces/guide/guide-anchors.json` | slug `what-it-is`, order 1; anchors include `the-notice` (the full education-not-advice notice) and `swing-horizons` (`{{horizons.table}}`) |
| V235-15 | Chapter 3: the pipeline and its diagram | 4 | sonnet | C `docs/guide/03-pipeline.md`, C `frontend/src/app/workspaces/guide/pipeline-diagram.ts`, C `frontend/src/app/workspaces/guide/pipeline-diagram.spec.ts`, M `frontend/src/app/workspaces/guide/guide-figures.ts`, M `frontend/src/app/workspaces/guide/guide-anchors.json` | slug `pipeline`, order 3; `GuidePipelineDiagram` selector `sb-guide-pipeline-diagram` (inline SVG, theme tokens, boxes link to `/insights/guide/<slug>` only when that slug is in `GuideStore.chapters()`); `GUIDE_FIGURES.pipeline` |
| V235-16 | Chapter 12: Glossary | 4 | sonnet | C `docs/guide/12-glossary.md`, M `frontend/src/app/workspaces/guide/guide-anchors.json` | slug `glossary`, order 12; one `###` heading per term (one anchor each) |
| V235-17 | Layout check at three widths | 4 | sonnet | C `scripts/dev/guide_layout_check.py`, C `tests/scripts/test_guide_layout_check.py`, C `docs/superpowers/results/2026-11-18-v235-guide-layout.md` | `guide_layout_check.main(argv=None) -> int` (Playwright; widths 390, 820, 1440; checks no horizontal overflow, TOC mode per width, hit targets ≥ 44px on 390/820, deep-link scroll); screenshots under `logs/v235-layout/` |
| V235-18 | Full-suite verification | 4 | haiku | none (run only; CI) | push, then watch the CI run green (`0 failed`, `0 xfailed`), frontend `frontend-test` job included |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-18-v235-guide-foundation_1-backend.md` | V235-1..V235-5 | correlation constant, loader, placeholder whitelist (risk and market), API and access rows |
| 2 | `2026-11-18-v235-guide-foundation_2-freshness.md` | V235-6..V235-8 | content test and anchor fixture, `guide_sources.py`, `/close-out` rule with CLAUDE.md/AGENTS.md mirrors |
| 3 | `2026-11-18-v235-guide-foundation_3-frontend.md` | V235-9..V235-13 | `marked`, client and store, `GuideLinkComponent` and anchor spec, page render, TOC and search, routes and nav |
| 4 | `2026-11-18-v235-guide-foundation_4-chapters.md` | V235-14..V235-18 | chapters 1, 3 (with diagram), 12, layout check, full-suite verification |

## Handoff

Controller decisions, 2026-11-18 (binding on every part writer):

1. **Front matter**: promote PyYAML to a pinned runtime dependency in `requirements.txt` (`PyYAML==6.0.3`, moved out of the "Test-only dependencies" block) and parse with `yaml.safe_load`; no hand parser (V235-2).
2. **Module paths**: use the real paths from the brief (`swingbot/core/market/levels.py`, `swingbot/core/market/levels_lifecycle.py`, `swingbot/core/market/mtf.py`, `swingbot/core/market/strategy_types.py`, …), never the spec's shortened ones, in code and in chapter `sources:`.
3. **`marked`**: added to `frontend/package.json` at an exact version with `package-lock.json` updated (`npm install marked@<x.y.z> --save-exact`); rendered HTML goes through Angular's sanitiser per the spec (V235-9, V235-11).
4. **CLAUDE.md is at 199 lines**: the one-line guide rule forces moving existing CLAUDE.md content into the matching `docs/claude/*.md` (pointer left behind), with `AGENTS.md` mirrored and `python scripts/dev/sync_codex.py` run, all in one commit (V235-8).
5. **Registered strategy keys and placeholders**: resolved from the brief. Registered keys = sorted union of `strategy.STRATEGY_FUNCS` and `STRATEGY_GATES` keys (checked 2026-11-18: 11 and 16 keys, 3 only in the first, 8 only in the second; cards for masked ones read "masked — research only" in Plan B). Gap-sizing names come from `swingbot/core/planning/gap_sizing.py` (`LOOKBACK = 250`, `MIN_UP_GAPS = 60`, `MIN_DOWN_GAPS = 60`, `RULE_GAP = "gap_p99"`); V235-3 reads that module before writing `sizing.gap`. Extracting the two `window: int = 90` defaults into `DEFAULT_WINDOW` is a behaviour-preserving refactor (V235-1). V235-3 reads `edge/correlation.py` (58 lines) for what `correlation.sector_fallback` describes.
6. **Versions**: `VERSION.json` is ui 1.44.1 / bot 2.19.2; the spec header is stale. Bump levels stand (ui minor, bot patch); chapters carry `reviewed_for: 2.19.2`.
7. **UI**: every UI task covers mobile, tablet and desktop; V235-13 updates the four hard-coded Insights specs (`app.routes.spec.ts`, `shell/nav.spec.ts`, `shell/more-sheet.spec.ts`, `shell/breadcrumb.spec.ts`); V235-5 adds the `access_expectations.py` rows (`/guide`, `/guide/<slug>` in `_VIEWER_GET`; `SAMPLE_PATHS` maps `f"{V1}/guide/<slug>"` to `f"{V1}/guide/what-it-is"`).
8. **Verification**: the plan ends with one full-suite task (V235-18), run by CI after the push per CLAUDE.md.

Plan-writer decisions (index, 2026-11-18), for the controller to check:

- **The pipeline diagram is an Angular component, not a served `.svg` file.** Angular's sanitiser strips inline `<svg>` and an `<img>` SVG cannot read the app's theme tokens, so the "checked-in SVG using theme tokens" lives as the inline-SVG template of `pipeline-diagram.ts` (precedent `ui/plan-lifecycle-diagram.ts`). Chapter Markdown places it with a line `<!-- figure:pipeline -->`; the page splits on that marker and renders the registered component between Markdown segments. No `docs/guide/assets/` directory.
- **Anchors are applied after sanitising.** Angular's sanitiser drops `id`, so the page sets `id` on rendered `h2`/`h3` in order from the API's heading list (V235-11); the content test forbids headings inside `<details>` so the two orders always agree.
- **Placeholders resolve per request; chapter files cache per process.** Live values (alerts per week) would otherwise freeze until a restart; the spec's "cached per process" is honoured for the files.
- **Plan B/C checks are wired now but vacuous.** The strategies file-set check activates once `docs/guide/strategies/` holds any `.md`; the bare-`N%` check runs over orders 7–9, absent in Plan A.
