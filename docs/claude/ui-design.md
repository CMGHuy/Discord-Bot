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
  the only affordance.
- Layout responds to its **container** where it can sit in a narrow panel
  (`container-type: inline-size` + `@container`), not only the viewport.
- No horizontal page scroll; a wide table scrolls inside its own box.
- Controls that have a desktop row layout say how they wrap on narrow widths.
- State what each class defaults to (page size, density, columns) and whether a
  saved choice is per device class.

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
