# UI design: mobile, tablet and desktop together

Any UI you design or change is designed for **all three device classes at
once**, not desktop first with a phone patch afterwards. Done means checked at
each width (Playwright, never claude-in-chrome — `skills-tools.md`).

## Device classes

`frontend/src/app/ui/breakpoints.ts:BREAKPOINTS` is authoritative: `sm` 640,
`md` 1024, `lg` 1440, `xl` 1920 (each a min-width floor).

| Class | Width | `ViewportService` |
|---|---|---|
| Phone | < 640 | `isPhone()` |
| Tablet | 640–1023 | `isNarrow()` and not `isPhone()` |
| Desktop | ≥ 1024 | otherwise |

"Compact" (tablet and phone) is `ViewportService.isNarrow()`.

## Checklist for every screen or control

- Touch targets at least 44px (2.75rem) on phone and tablet; hover is never
  the only affordance. A control whose box may grow takes
  `min-height: var(--control-h)`; one whose look must stay small takes
  `class="sb-hit"` (a transparent hit area of `--hit-min`, 44px under
  `(pointer: coarse), (max-width: 1023px)`).
- Text is never below 11px: size it with the text tokens (they carry the floor
  at every zoom step), never a literal `font-size` under 11px.
- Mixed text sizes on one line align on the baseline (`align-items: baseline`
  or `last baseline`), never `center`. Numbers use the numeric face (`.num`,
  `var(--font-num)`); labels stay in the UI font.
- Table cells centre vertically: every cell's content sits on the middle of
  its row, so a row's figures share one line. A decoration under a figure (a
  magnitude bar) hangs in the cell's padding, never adds to its content. An
  icon, checkbox or radio mark is centred on the text beside it (`sb-icon`
  carries `vertical-align: middle` for inline use).
- Layout responds to its **container** where it can sit in a narrow panel
  (`container-type: inline-size` + `@container`), not only the viewport.
- No horizontal page scroll. A wide chart or grid scrolls inside its own box
  with an edge fade; a data table on a phone is **declared, not hand-built**:
  its columns carry a `compact` slot (line 1 or 2, plus an order) and
  `sb-data-table` renders compact rows and the row drawer (v179). Open-position
  tables keep the P&L amount and the stop or risk on the compact row; strategy
  rows keep the badge tier and evidence freshness.
- Controls that have a desktop row layout say how they wrap on narrow widths.
- State what each class defaults to (page size, density, columns) and whether a
  saved choice is per device class.
- **Before merging any UI change, run the layout audit** against a local
  replica (`/replicate-prod-db`, `cd frontend && npm run build`,
  `python admin_ui.py`, then sign in once with
  `node frontend/scripts/browse.mjs login --base http://localhost:1234`):
  `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`
  must exit 0 at 390, 768 and 1440. It checks page overflow, off-screen and
  clipped text, sub-44px targets (phone/tablet), sub-11px text, baseline
  offsets over 2px, and (`vcenter`) table-cell content or an icon more than
  2px off centre, on every route and tab. A finding is fixed, not allowed;
  only canvas/third-party chart internals and browser-native parts go in
  `frontend/scripts/layout-audit.allow.json`, each entry with a reason and the
  date it was added. Entries nothing matches any more print as `STALE`; a run
  with `--prune` removes them. A route or tab added to the app is added to
  `ROUTES` in `frontend/scripts/layout-audit-lib.mjs` in the same commit. It
  is not in CI (spec v179 §6a.6).

## Tables and pagers

- Every data table has a rows-per-page dropdown beside the page controls:
  **5, 10, 20, 50, 100, All** (`PER_PAGE_OPTIONS` in `ui/table-prefs.ts`).
- Default **10 on desktop, 5 on tablet and phone** (`defaultPerPage`). A chosen
  value is saved per table **and** per device class
  (`tables.<id>.desktop|compact.per_page`), so 50 on a laptop never lands on a
  phone.
- Server-paged tables: "All" asks the API for its 200-row cap and the range
  label says `(capped)` when the total is larger. `sb-pagination` takes the
  user's choice through `perPageChoice`.
- A paged table is either server-paged (caller passes `pagination`), caller
  client-paged (`createClientPage`), or opts in with
  `<sb-data-table clientPaging="<table-id>">`. Use `tablePerPage(id)`
  (`ui/table-per-page.ts`) for the saved size; never read the prefs by hand.
- A client-paged table with 5 rows or fewer shows no pager.
- Not paged: fixed layouts (calendar grid, matrix, heat-grid) and tiny
  key/value diff tables.
