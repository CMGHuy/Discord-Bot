# v235 — Guide foundation (Plan A of spec v215): Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V235-7" -A 400 <part file>`); never read a part whole.

**Bump:** bot patch
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

- `**Bump:**` bot patch (the ui minor moved to v236 with the page). `VERSION.json` is ui 1.44.1 / bot 2.19.2 today; the numbers are computed at `/close-out`, never in a task.
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
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`, `cd frontend && npx ng test --watch=false --include <spec>`); only V235-9 runs the full suite.
- New backend tests land in existing suites (`admin`, `admin-core`, `tooling`, `edge`); no new `tests/` directory.

## Parallelisation

One stream. The frontend half moved to plan v236 (see `## Handoff` item 9), so everything here is backend, tests and docs.

Sequential edges and why:

- V235-1 → V235-3: `correlation.window` reads `correlation.DEFAULT_WINDOW`.
- V235-2 → V235-2b: `parse_chapter`/`load_chapters` extend `chapters.py`.
- V235-2b → V235-3b, V235-5, V235-6, V235-7: all load chapters.
- V235-3 → V235-3b: the registry merges `live_risk.RISK_PLACEHOLDERS`.
- V235-3b → V235-4: both modify `placeholders.py` (registry merge).
- V235-4 → V235-5, V235-6: the API and the content test need the full whitelist.
- V235-7 → V235-8: the `/close-out` rule names `scripts/dev/guide_sources.py`.
- V235-9 last.
- Groups that may run side by side: {V235-1, V235-2}; {V235-6, V235-7} after V235-5.

## Task ledger

| Id | Title | Part | Model | Files | Produces (consumed later) |
|---|---|---|---|---|---|
| V235-1 | Correlation window constant | 1 | haiku | M `swingbot/core/edge/correlation.py`, M `tests/edge/test_edge_correlation.py` | `correlation.DEFAULT_WINDOW = 90` (module constant beside `DEFAULT_THRESHOLD`); `returns_corr(df_a, df_b, window: int = DEFAULT_WINDOW)`, `cluster_exposure(..., *, window: int = DEFAULT_WINDOW, ...)`; behaviour unchanged |
| V235-2 | Chapter loader: package, types, anchors, headings | 1 | sonnet | C `swingbot/admin/guide/__init__.py`, C `swingbot/admin/guide/chapters.py`, C `tests/admin/test_guide_chapters.py` | `class GuideFormatError(ValueError)`; `@dataclass(frozen=True) Heading(level: int, text: str, anchor: str)`; `@dataclass(frozen=True) Chapter(slug: str, title: str, order: int, reviewed_for: str, sources: tuple[str, ...], body: str, headings: tuple[Heading, ...], path: Path)`; `guide_dir() -> Path` (`Path(config._PROJECT_ROOT) / "docs" / "guide"`, read at call time); `anchor_for(text: str, seen: dict[str, int]) -> str`; `extract_headings(markdown: str) -> tuple[Heading, ...]` (`##`/`###` outside code fences); `split_source(entry: str) -> tuple[str, str \| None]` (`"path:symbol"` → `(path, symbol)`); `FIGURE_RE = re.compile(r"^<!-- figure:([a-z0-9-]+) -->$", re.M)` |
| V235-2b | Runtime PyYAML, `parse_chapter`, `load_chapters` | 1 | sonnet | M `requirements.txt`, M `swingbot/admin/guide/chapters.py`, M `tests/admin/test_guide_chapters.py` | `parse_chapter(path: Path) -> Chapter` (file name must equal `f"{order:02d}-{slug}.md"`); `load_chapters(root: Path \| None = None) -> list[Chapter]` (top-level `NN-*.md` only, sorted by `order`; duplicate slug or order raises `GuideFormatError`) |
| V235-3 | Risk placeholders (`live_risk.py`) | 1 | sonnet | C `swingbot/admin/guide/live_risk.py`, C `tests/admin/test_guide_placeholders.py` | `PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")`; `class UnknownPlaceholder(KeyError)` with `.name: str`; `PLACEHOLDERS: Mapping[str, Callable[[], str]]` (`MappingProxyType`); `names_in(markdown: str) -> list[str]`; `resolve(markdown: str) -> str`; `provenance_label(*, source: str, n: int, run_date: str, costs_included: bool) -> str` (always ends "before tax"); `live_risk.RISK_PLACEHOLDERS: dict[str, Callable[[], str]]` with names `MAX_STOP_LOSS_PCT`, `MIN_STOP_DISTANCE_PCT`, `CLAMP_STOP_TO_HARD_CAP`, `RISK_PER_TRADE_PCT`, `RISK_PER_TRADE_PCT.max`, `MAX_RISK_AMOUNT_ABSOLUTE`, `PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`, `POSITION_SIZING_MODE`, `correlation.threshold`, `correlation.window`, `correlation.sector_fallback`, `sizing.kelly_cap`, `sizing.risk_floor`, `sizing.risk_ceiling`, `sizing.gap` (table from `SHORT_GAP_SIZING`, `LONG_GAP_SIZING`, `gap_sizing.LOOKBACK`, `MIN_UP_GAPS`, `MIN_DOWN_GAPS`, `RULE_GAP`), `version.bot` |
| V235-3b | Placeholder registry and resolver | 1 | sonnet | C `swingbot/admin/guide/placeholders.py`, M `tests/admin/test_guide_placeholders.py` | `PLACEHOLDER_RE`, `UnknownPlaceholder`, `PLACEHOLDERS`, `names_in`, `resolve` (rejects any unregistered or malformed `{{…}}` before substituting), `_merge`, `provenance_label` -- signatures as in the V235-3 row (moved here by split) |
| V235-4 | Market placeholders and alerts per week | 1 | sonnet | C `swingbot/admin/guide/live_market.py`, M `swingbot/admin/guide/placeholders.py`, C `tests/admin/test_guide_live_market.py` | `live_market.MARKET_PLACEHOLDERS` with names `levels.families` (`ALL_STRATEGY_FAMILIES`, AVWAP marked "only when AVWAP_LEVELS_ENABLED"), `CLUSTER_TOLERANCE_PCT`, `horizons.table` (every `HORIZONS` key in `horizon_order()`, masked ones labelled "masked — research only" via `live_horizons()`), `gates.list` (from `STRATEGY_GATES`), `alerts.per_week` (mean over the last 8 full weeks of `opened_at`, with `provenance_label(source="live paper book", …)`; "no live alerts in the last 8 weeks" when empty); `live_market._load_trades: Callable[[], list[dict]]` and `live_market._now: Callable[[], datetime]` (module attributes, monkeypatchable); `registered_strategy_keys() -> tuple[str, ...]` (sorted union of `strategy.STRATEGY_FUNCS` and `STRATEGY_GATES` keys); `strategy_file_slug(key: str) -> str` (anchor rule, e.g. `"Break & Retest"` → `break-retest`); `PLACEHOLDERS` now merges both tables |
| V235-5 | Guide API routes and access rows | 1 | sonnet | C `swingbot/admin/api_v1/guide.py`, M `swingbot/admin/api_v1/__init__.py`, M `tests/admin/access_expectations.py`, C `tests/admin/test_api_v1_guide.py` | `GET /api/v1/guide` → `{"chapters": [{"slug", "title", "order", "reviewed_for", "headings": [{"level", "text", "anchor"}]}]}` (headings from the resolved body); `GET /api/v1/guide/<slug>` → `{"slug", "title", "reviewed_for", "markdown"}` (resolved), 404 `not_found`, 500 `guide_placeholder`; `guide._chapters() -> tuple[Chapter, ...]` (`lru_cache(maxsize=1)`), `guide.clear_cache() -> None` |
| V235-6 | Content test and anchor fixture | 2 | sonnet | C `tests/admin/test_guide_content.py`, C `scripts/dev/guide_anchors.py`, C `frontend/src/app/workspaces/guide/guide-anchors.json`, C `tests/scripts/test_guide_anchors.py` | `guide_anchors.build(root: Path \| None = None) -> dict` shaped `{"chapters": {"<slug>": ["<anchor>", …]}}` (slugs sorted, anchors in document order); `guide_anchors.main(argv=None) -> int` (writes the fixture, 2-space indent, trailing newline; `--check` exits 1 on drift); `FIXTURE = Path("frontend/src/app/workspaces/guide/guide-anchors.json")`; content checks: placeholders resolve, sources and `path:symbol` exist, horizons all in `horizons.table`, `reviewed_for` ≤ bot version, no heading inside `<details>`, figure names in `guide-figures.ts`, strategies file set equals `registered_strategy_keys()` once `docs/guide/strategies/` holds any `.md`, no bare `N%` in orders 7–9 |
| V235-7 | `guide_sources.py` diff helper | 2 | sonnet | C `scripts/dev/guide_sources.py`, C `tests/scripts/test_guide_sources.py` | `guide_sources.touched(paths: Iterable[str], chapters: list[Chapter]) -> list[tuple[Chapter, list[str]]]`; `changed_paths(rev_range: str) -> list[str]` (`git diff --name-only <base>..<head>`); `main(argv=None) -> int` (`python scripts/dev/guide_sources.py <base>..<head>` prints `NN-<slug>.md: <path>, …` per touched chapter, or `guide: no chapter sources touched`; exit 0; bad range exit 2); also scans `docs/guide/strategies/*.md` |
| V235-8 | `/close-out` guide rule, CLAUDE.md and mirrors | 2 | sonnet | M `.claude/skills/close-out/SKILL.md`, M `.agents/skills/close-out/SKILL.md` (generated by `python scripts/dev/sync_codex.py`), M `docs/claude/document-lifecycle.md`, M `CLAUDE.md`, M `AGENTS.md`, M one existing `docs/claude/*.md` that receives lines moved out of `CLAUDE.md` (V235-8 picks the section owner; no new `docs/claude/` file), C `tests/hooks/test_guide_closeout_rule.py` | Step 5b text: run `guide_sources.py <base>..<head>`; a touched chapter gets its text updated where behaviour changed and `reviewed_for` bumped, or the close-out commit records `guide: no reader-visible change`; `CLAUDE.md` stays < 200 lines |
| V235-9 | Full-suite verification | 2 | haiku | none (run only; CI) | push, then watch the CI run green (`0 failed`, `0 xfailed`) |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-18-v235-guide-foundation_1-backend.md` | V235-1, V235-2, V235-2b, V235-3, V235-3b | correlation constant, loader, risk placeholders, registry and resolver |
| 1b | `2026-11-18-v235-guide-foundation_1b-market-api.md` | V235-4, V235-5 | market placeholders, API and access rows |
| 2 | `2026-11-18-v235-guide-foundation_2-freshness.md` | V235-6..V235-9 | content test and anchor fixture, `guide_sources.py`, `/close-out` rule with CLAUDE.md/AGENTS.md mirrors |

## Handoff

Controller decisions, 2026-11-18 (binding on every part writer):

1. **Front matter**: promote PyYAML to a pinned runtime dependency in `requirements.txt` (`PyYAML==6.0.3`, moved out of the "Test-only dependencies" block) and parse with `yaml.safe_load`; no hand parser (V235-2).
2. **Module paths**: use the real paths from the brief (`swingbot/core/market/levels.py`, `swingbot/core/market/levels_lifecycle.py`, `swingbot/core/market/mtf.py`, `swingbot/core/market/strategy_types.py`, …), never the spec's shortened ones, in code and in chapter `sources:`.
3. **`marked`**: added to `frontend/package.json` at an exact version with `package-lock.json` updated (`npm install marked@<x.y.z> --save-exact`); rendered HTML goes through Angular's sanitiser per the spec (V236-1, V236-3).
4. **CLAUDE.md is at 199 lines**: the one-line guide rule forces moving existing CLAUDE.md content into the matching `docs/claude/*.md` (pointer left behind), with `AGENTS.md` mirrored and `python scripts/dev/sync_codex.py` run, all in one commit (V235-8).
5. **Registered strategy keys and placeholders**: resolved from the brief. Registered keys = sorted union of `strategy.STRATEGY_FUNCS` and `STRATEGY_GATES` keys (checked 2026-11-18: 11 and 16 keys, 3 only in the first, 8 only in the second; cards for masked ones read "masked — research only" in Plan B). Gap-sizing names come from `swingbot/core/planning/gap_sizing.py` (`LOOKBACK = 250`, `MIN_UP_GAPS = 60`, `MIN_DOWN_GAPS = 60`, `RULE_GAP = "gap_p99"`); V235-3 reads that module before writing `sizing.gap`. Extracting the two `window: int = 90` defaults into `DEFAULT_WINDOW` is a behaviour-preserving refactor (V235-1). V235-3 reads `edge/correlation.py` (58 lines) for what `correlation.sector_fallback` describes.
6. **Versions**: `VERSION.json` is ui 1.44.1 / bot 2.19.2; the spec header is stale. Bump levels stand (ui minor, bot patch); chapters carry `reviewed_for: 2.19.2`.
7. **UI**: every UI task covers mobile, tablet and desktop; V236-7 updates the four hard-coded Insights specs (`app.routes.spec.ts`, `shell/nav.spec.ts`, `shell/more-sheet.spec.ts`, `shell/breadcrumb.spec.ts`); V235-5 adds the `access_expectations.py` rows (`/guide`, `/guide/<slug>` in `_VIEWER_GET`; `SAMPLE_PATHS` maps `f"{V1}/guide/<slug>"` to `f"{V1}/guide/what-it-is"`).
8. **Verification**: the plan ends with one full-suite task (V235-9), run by CI after the push per CLAUDE.md.
9. **Split (partner, 2026-11-18)**: the frontend tasks needed two `b` splits, past the 20-task cap. The partner chose to split the plan: v235 keeps backend + freshness (V235-1..V235-8, full suite V235-9); the page, nav, chapters 1/3/12 and the layout check moved to **plan v236** (`2026-11-18-v236-guide-page_0-index.md`), which depends on v235 being merged. Old ids V235-9..V235-18 map to V236-1..V236-12 (V235-11 → V236-3/V236-4, V235-12 → V236-5/V236-6). References in this plan to those ids now name the V236 ids. Decisions 3 and 7 apply to v236.

Plan-writer decisions (index, 2026-11-18), for the controller to check:

- **The pipeline diagram is an Angular component, not a served `.svg` file.** Angular's sanitiser strips inline `<svg>` and an `<img>` SVG cannot read the app's theme tokens, so the "checked-in SVG using theme tokens" lives as the inline-SVG template of `pipeline-diagram.ts` (precedent `ui/plan-lifecycle-diagram.ts`). Chapter Markdown places it with a line `<!-- figure:pipeline -->`; the page splits on that marker and renders the registered component between Markdown segments. No `docs/guide/assets/` directory.
- **Anchors are applied after sanitising.** Angular's sanitiser drops `id`, so the page sets `id` on rendered `h2`/`h3` in order from the API's heading list (V236-3); the content test forbids headings inside `<details>` so the two orders always agree.
- **Placeholders resolve per request; chapter files cache per process.** Live values (alerts per week) would otherwise freeze until a restart; the spec's "cached per process" is honoured for the files.
- **Plan B/C checks are wired now but vacuous.** The strategies file-set check activates once `docs/guide/strategies/` holds any `.md`; the bare-`N%` check runs over orders 7–9, absent in Plan A.

## Panel review (pre-close-out, 2026-11-19)

Range `bc265140..5edb5fe5`. No BLOCKING; every ADVISORY is carried to the chapter
prose and placeholder work of v236 / Plans B and C (none ships prose here).

- technical-analyst: `CLUSTER_TOLERANCE_PCT` (`live_market.py:136`) is only the tight 1.5% pass, not the looser second pass (`levels.py:507`) -- prose must say which -- carried
- technical-analyst: `levels.families` lists 12 flat families; prose must not count EMA/VWAP/AVWAP as independent confirmations -- carried
- technical-analyst: horizons/gates read at call time, no lookahead -- clean
- risk-manager: `MAX_RISK_AMOUNT_ABSOLUTE` renders `$0` when the cap is disabled (`live_risk.py:91`, `config.py:669-676`); render "disabled" before any chapter uses it -- carried
- risk-manager: gap table covers plain gap sizing only, not the ATR-band path (`gap_sizing.py:173-184`) -- carried
- risk-manager: the 2% appears as `RISK_PER_TRADE_PCT`, `.max` and `sizing.risk_ceiling`; prose states dollar risk and which bound binds -- carried
- risk-manager: per-horizon stop caps may bind tighter than `MAX_STOP_LOSS_PCT` (`sizing.py:50-60`) -- carried
- risk-manager: heat caps are computed from each open plan's current stop; prose must say so -- carried
- risk-manager: `sizing.kelly_cap` prose conditional on `POSITION_SIZING_MODE` -- carried
- financial-advisor: `alerts.per_week` counts both ledgers (controller ruling: weak-ledger strategy alerts post too); name the population in the label -- carried
- financial-advisor: show the busiest of the 8 weeks beside the mean -- carried
- financial-advisor: `provenance_label` needs `unit` and `ledger`/`tier` before the first performance figure ships (`placeholders.py:77-80`) -- carried
- financial-advisor: turnover / short-term tax drag stated in Plan C prose -- carried
- financial-advisor: content test that every performance placeholder routes through `provenance_label` -- carried
- financial-advisor: `alerts.per_week` "as of" is the render date; show latest `opened_at` -- carried
