# v179 layout audit — results

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) §7
**Plan:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](../plans/2026-10-19-v179-mobile-layout-consistency_0-index.md) — task V179-20
**Run:** 2026-10-21 ~22:30, local replica (`/replicate-prod-db` at 20:54, 33 tables, alembic `v173_002`), branch `2026-10-19-v179-mobile-layout-consistency` at `a1c989e3`
**Command:** `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths <w> --out <dir>` (one run per width: 390, 768, 1440)
**Ids the placeholders resolved to:** trade `f7efca42-1717-4cff-99de-6bbcc50c438a`, plan `9d62b94b-7bc3-4a3c-a297-cbd90164a5e6`, symbol `ABNB`, day `2026-10-21`

## Verdict (§7.1)

| Run | Unallowed | overflow | offscreen | clipped | tap | text | baseline | Allowed |
|---|---|---|---|---|---|---|---|---|
| First of this session (all widths, after the earlier audit fixes on the branch) | 69 | 0 | 0 | 15 | 54 | 0 | 0 | 0 |
| Final @390 | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Final @768 | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Final @1440 | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

The first run's 15 `clipped` findings were the topbar tape at 768 (`/system`, `/ui`); they were a settle-time artefact of an unfinished tape page measure and did not recur once the page was given time to load. Stale allow-list entries: none (the allow-list is empty).

Two harness faults surfaced while verifying, both in the run, not the app: (1) `swingbot/admin/static/app` is a gitignored copy of the build and `npm run build` alone does not refresh it, so the first re-runs measured the old bundle; (2) the Angular service worker in the persistent Playwright profile can serve a cached build, so `layout-audit.mjs` now launches with `serviceWorkers: 'block'`.

## Fixes made by the audit

| Commit | Check | Selector (routes) | Owning file |
|---|---|---|---|
| `bc79d5cc` | tap | `sb-histogram > li`, `sb-bar-list > li`, `sb-share-bar > span.seg`, `sb-heat-grid > td`, `sb-waterfall > rect.bar`, `sb-dot-plot > circle.hit` (Analytics tabs, `/ui`) | `ui/histogram.ts`, `bar-list.ts`, `share-bar.ts`, `heat-grid.ts`, `waterfall.ts`, `dot-plot.ts` |
| `b6c92c3d` | tap | `sb-async > button.segment` (`/versions`) | `workspaces/versions/versions.ts` |
| `a1c989e3` | tap | `sb-dot-plot > circle.hit` 40px when the svg scales down (`/ui`) | `ui/dot-plot.ts` |

Earlier commits on the branch from the same audit (tape, lifecycle diagram, calendar toggle, inputs, links, baselines, …) are listed by `git log main..HEAD --grep "layout audit"`.

Design notes for the panel: the tooltip-only chart marks take `.sb-hit` (partner's choice over allow-listing). Thin adjacent marks (share-bar segments, Versions timeline segments) have overlapping hit areas, so a click on a thin segment's own pixels can land on a later neighbour's padded area; the Versions page already documents that dense-lane segment widths are approximate. `.share-bar` no longer clips with `overflow: hidden` (that would have clipped the pad); its end segments carry the rounded corners instead.

## Allow-list (each entry's reason)

None — the allow-list is empty.

## Dashboard drawer round trip (§7.3)

```text
PASS positions @1440: the click pushes ?trade=<id>
PASS positions @1440: still on /dashboard
PASS positions @1440: drawer open with its "Paper trade" marker
PASS positions @1440: Back drops ?trade= and stays on /dashboard
PASS positions @1440: Back closes the drawer
PASS positions @1440: "Open full trade" reaches /trades/9d62b94b-7bc3-4a3c-a297-cbd90164a5e6
PASS activity @1440: (same six checks)
PASS @1440: at least one source had a trade to open
PASS positions @390: (same six checks)
PASS activity @390: (same six checks)
PASS @390: at least one source had a trade to open
round trip: all passed
```

## Screenshots (§7.2)

81 full-page PNGs (27 routes and tabs × 390/768/1440), `<slug>@<width>.png`, in the run's scratch directory (outside the repo; regenerate with the command above). Reviewed in this session: Versions, Analytics Attribution and Partials, Trades at 390 (the routes the last fixes touched), plus the audit's zero-finding result for every route at three widths.

| Check | Result |
|---|---|
| No sideways page, nothing cut | pass — Attribution heat grid scrolls in its own box; Partials tiles and tables stay inside the page |
| Compact rows (money and badge floors) | pass — Trades @390 two-line rows with P&L amount and status/fill on line 2 |
| One look per primitive | pass on the reviewed pages |
| Tab rails | pass — Analytics and Partials rails scroll, active tab in view |
| Baselines and numbers | pass (audit `baseline=0`) |
| Captions travel | pass on the reviewed pages (N= samples, hints present) |
| Desktop unchanged | not re-reviewed by eye beyond the audit's zero findings at 1440 |
