# v240 — Doctena night: Navy restyle, Jost, icon rail, Calendar destination, editable phone tabs, drawers below 1024px

**Version:** ui 1.45.0 · bot 2.19.5
**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer, financial-advisor

## Why

The partner asked for the admin SPA (bomeo-capital.com) to take the font and
visual design of https://www.doctena.de/de/, **as a dark theme**: doctena's
light palette translated into matching dark colours. During the brainstorm
(2026-11-23) the request grew into six linked changes, all approved with
mockups:

1. The **Navy** theme is reworked into "doctena night" and becomes the
   default. Black (graphite) stays as the alternative.
2. **Jost** replaces Inter and JetBrains Mono everywhere, numbers included.
3. Rounder, flat shapes: doctena's 10–12px corners, pill chips, uppercase
   buttons.
4. The rail becomes **icons only** with a tooltip, and **every icon in the
   app** is redrawn to say what it means.
5. **Calendar** becomes its own destination. On a phone the partner picks
   which pages the tab bar holds, and a press-and-hold shows a tab's name.
6. On phone **and tablet**, detail opens in **drawers** wherever it can,
   and dragging a drawer down closes it.

The product does the same thing after this change. It looks different and
navigates slightly differently. No data, schema, alert or trading behaviour
changes. Hence `ui minor` (every user sees a different product), `bot patch`
(one SPA route prefix in `swingbot/admin/spa.py`), and `Edge: none (integrity)`.

## The reference, measured

The plain fetch of doctena.de was refused (HTTP 403), so the page was read
with headless Playwright (partner-approved). Its computed styles, 2026-11-23:

| What | doctena.de value |
|---|---|
| Font | `Jost`, self-hosted woff2, weights 400/500/600/700, with metric-matched Arial/Roboto fallbacks |
| Body | 16px/24px, weight 400, colour `#003958` on `#FFFFFF` |
| Headings | weight 600; h1 56px with −0.01em tracking, h2 32–40px, h3 24px |
| Buttons | 16px, 600, UPPERCASE, +0.04em tracking, 12px radius, 12px×16px padding |
| Inputs | 12px radius, 1px `#0072B0` border |
| Cards | 10px radius, shadow `0 10px 15px -3px rgb(0 0 0/.1), 0 4px 6px -4px rgb(0 0 0/.1)` |
| Palette | ink `#003958`, muted `#4B748A`, brand blue `#0072B0`, `#005B8C`, `#328EC0`, chip `#C8E1EF`, pale `#E1EFF7`, mint `#53CEB5` / `#85DCCB`, error `#C52020` |

## Mockups

In `docs/superpowers/specs/v240-mockups/` (open in a browser; the Jost file
sits beside them):

1. `1-palette-directions.html`: Navy today vs **A, doctena night flat**
   (chosen) vs B, hero gradient with shadows (rejected).
2. `2-icon-rail-devices.html`: the nav icon set (current vs new) and A at
   desktop, tablet and phone, with the icon-only rail and its tooltips.
3. `3-calendar-tabbar.html`: Calendar in the rail, the Bomeo Capital
   wordmark, a phone press-and-hold tooltip, the More sheet and the tab-bar
   editor.
4. `4-icon-set.html`: every other icon, current vs new, plus Open positions
   and Recent activity redrawn with them.

The mockups are the visual reference. **This spec wins where they differ.**

## Decisions (partner, 2026-11-23)

- D1. Dark take on doctena, mockup **A (flat)**. No hero gradient and no card shadows.
- D2. The **Navy** theme is reworked into it, not added as a third theme.
  Navy becomes the default; Black stays in the picker.
- D3. **Jost for everything**: `--font-sans` and `--font-mono` alike,
  numbers included ("Everything, like SDV"). Tabular figures keep columns
  aligned.
- D4. Font and shapes change for **both** themes; only colours differ
  between Navy and Black.
- D5. The rail shows **icons only**, with the page name on a tooltip. This
  deliberately reverses v202 §3's labelled 80px rail. The touch gap that
  rail closed is covered by long-press (§5).
- D6. Icons are redrawn to express meaning: the nav set and **every other
  icon in the app** (mockups 2 and 4, approved).
- D7. Calendar leaves Trades and becomes a top-level destination in the
  rail, after Trades.
- D8. The wordmark reads **Bomeo Capital**.
- D9. Phone tab bar: labels always shown; press and hold shows the tooltip;
  Calendar is a default tab; the partner edits which pages the bar holds.
  The choice is saved **in this browser**, like the theme.
- D10. Phone and tablet: show detail in drawers as much as possible;
  dragging a drawer down closes it.
- D11. Below 1024px every drawer is a **bottom sheet**: full width on
  phone, centred and at most 720px wide on tablet. Desktop keeps the
  right-hand panel.

## Design

### 1. Colours: the Navy block becomes doctena night

`frontend/src/styles/tokens.css` `:root[data-theme="navy"]` today re-points
the eleven ground and ink tokens only. It grows to re-point the ground, ink,
accent and P&L tokens below. The new hues live in `palette.css` as a
`doctena-*` ramp, referenced by `var()` (the colour gate in
`primitives.spec.ts` stays satisfied). The `midnight-*`/`frost-*` ramps lose
their last readers and are deleted.

| Token | Navy (doctena night) |
|---|---|
| `--bg` | `#00131F` |
| `--surface` | `#001E30` |
| `--surface-raised` | `#032A42` |
| `--surface-overlay` | `#073652` |
| `--overlay-dim` | `#00131F` at 72% |
| `--border` / `--border-strong` | `#0D3D59` / `#1D5373` |
| `--text` / `--text-secondary` / `--text-muted` | `#FAFDFF` / `#C8E1EF` / `#8FB3C8` |
| `--text-faint` | `#4B748A` |
| `--accent` | `#328EC0` |
| `--accent-fill` / `--accent-fill-hi` | `#0072B0` / `#0A82C4` |
| `--accent-soft` | `#328EC0` at 18% |
| `--pos` (gains, long) | `#53CEB5` (doctena mint) |
| `--neg` (losses, short) | `#F07A7A` (doctena error `#C52020`, lifted for a dark ground) |

- **Contrast holds.** `contrast.spec.ts` runs over both themes
  (`theme-tokens.ts`, `TOKEN_THEMES`). Every Navy pair it checks must pass at
  its existing threshold. A value that fails is darkened or lightened in
  `palette.css` until it passes; the table above is the target, not a licence
  to lower a threshold.
- **Navy is the default.** `theme.service.ts` today reads "anything but
  exactly `'navy'` is graphite". This inverts: anything but exactly
  `'graphite'` is Navy, so a browser that never chose gets Navy, and one that
  explicitly chose Black keeps Black. The pre-boot script in
  `frontend/src/index.html` flips the same way, so the first paint is never
  the wrong theme, and so does the theme-color meta.
- **The bare `:root` stays Graphite.** `dump_tokens.py` and `resolve-token.ts`
  read only `:root` (v225), so the Discord chart PNGs and the token fixture
  (`tests/charts/resolved_tokens.json`) keep the Black colours. The Discord
  images are out of scope (see Out of scope).
- The profile menu labels stay "Black" / "Dark blue"; Dark blue moves first
  in the list, since it is now the default.

### 2. Font: Jost, self-hosted, everywhere

- Vendor `jost-latin-wght-normal.woff2` and `jost-latin-ext-wght-normal.woff2`
  (the variable-weight files from `@fontsource-variable/jost` 5.x, SIL OFL
  1.1) under `swingbot/admin/static/vendor/jost/`, with `LICENSE.txt`. The
  no-CDN rule (spec v13) holds.
- `frontend/src/styles/fonts.css` declares `Jost` once per subset with
  `font-weight: 100 900` and `unicode-range`, and drops the Inter and
  JetBrains Mono `@font-face` rules. The Inter and JetBrains Mono woff2 files
  stay on disk: `swingbot/core/charts/chart_style.py` loads Inter for the
  Discord charts.
- Add doctena's metric-matched fallback faces (`Jost Fallback` over local
  Arial/Arial Bold, and `Jost Fallback Android` over Roboto, using the
  size-adjust and ascent/descent overrides measured above) so a slow font
  load does not shift the layout.
- Tokens: `--font-sans: "Jost", "Jost Fallback", "Jost Fallback Android",
  system-ui, sans-serif;` and `--font-mono: var(--font-sans)`. `--font-num`
  and `--font-figure` keep reading those tokens, so no component changes.
  Every rule that reads `--font-num` or `--font-mono` already sets, or now
  gets, `font-variant-numeric: tabular-nums`. Jost has tabular figures (the
  `tnum` feature), which is what keeps columns aligned without a mono face.
  The plan's first font task confirms `tnum` in the vendored file before
  anything depends on it.
- Code samples (`code` in Insights → Tuning, the gallery) keep reading
  `--font-mono`, which is now Jost. That is the partner's "everything" choice.
- `styles.css:116`'s note about JetBrains Mono's missing 600 weight is
  deleted with its workaround: a variable font has every weight.

### 3. Shapes and type treatment (both themes)

Tier-3 tokens in `tokens.css`:

| Token | Today | New |
|---|---|---|
| `--panel-radius` | 6px | 10px |
| `--control-radius` | 4px | 12px |
| `--chip-radius` | 4px | 999px (pill) |
| `--radius-sm` | 2px | 6px for swatches and cells; bars and tracks under 6px tall keep `999px` ends |
| `--panel-inner-radius` | `var(--control-radius)` | 8px |
| `--panel-shadow` | none | none (D1: flat) |

- Buttons: `sb-button` text is UPPERCASE with +0.04em tracking and weight
  600, as on doctena. Icon buttons are unchanged.
- Headings keep weight 600 and gain −0.02em tracking on `--text-title` and
  above.
- v195 §1.5's "four radius targets" rule stays; only the values change.
  Tests that pin the old pixel values are updated, not deleted.

### 4. Icons: the whole set, redrawn

`frontend/src/app/ui/icon.ts` moves from a 16×16 grid at 1.5 stroke to a
**24×24 grid at 1.8 stroke** with round caps and joins. The component draws
16px in tables and inline text, 20px in lists, and 24px in the rail and tab
bar, through a `size` input (`16 | 20 | 24`, default 16) whose viewBox stays
24. A path may carry a filled sub-path (Partial's banked half, Pending's
sand) through a second `fill` path rendered with `fill="currentColor"
stroke="none"`.

Every existing name keeps its name, so no caller changes for the redraw.
Each path's comment says what it shows, as today.

| Name | New drawing (meaning) |
|---|---|
| `dashboard` | gauge with needle: the one-glance read of the book |
| `watchlist` | binoculars: tickers watched for a setup (an eye reads as show/hide) |
| `trades` | two candlesticks, redrawn at 24 |
| `calendar` | month grid with rings and day marks (also the new Calendar destination) |
| `risk` | shield with a percent sign: the 2% dollar-risk cap and heat |
| `analytics` (Insights) | light bulb with a rising line |
| `system` | monitor with a pulse line: health and versions (a gear reads as settings) |
| `pending` | hourglass with sand left |
| `opened` | live-signal broadcast: the position is running |
| `partial` | circle with the right half filled: TP1 banked, runner live |
| `closed` | finish flag: neutral for winners and losers |
| `cancelled` | crossed-out circle: void, never filled (EXPIRED maps here, as today) |
| `trailing` | upward stair with an arrowhead |
| `theme` | crescent moon (both themes are dark) |
| `clock`, `search`, `profile`, `signout`, `menu`, `more`, `trash`, `collapse`, `expand`, `versions`, `reports`, `research`, `brand` | the same subject, redrawn on the 24 grid |

**New names**, all on the same grid:

| Name | Use |
|---|---|
| `info` | replaces the `ⓘ` text glyph in `sb-hint` and every inline info marker |
| `long` / `short` | trend-up / trend-down arrows, replacing the `▲` / `▼` glyphs in `direction-arrow.ts` and every direction marker |
| `close` | replaces the `×` text in `sb-drawer`, sheets and dialogs |
| `edit`, `grip`, `up`, `down`, `plus`, `minus` | the tab-bar editor (§6) and drawers |

**Text glyphs that act as icons become `sb-icon`.** The plan inventories
them from the 48 files that hold `▲ ▼ ⓘ × ✓ ✗ ⚠ ● ○ ★` today. The rule:
a glyph that stands alone as a status, direction, action or info marker
becomes an icon. A glyph inside a sentence or a notation stays text:
`115.26 → 123.05`, `+2.9%`, `N = 412`, and the `→` in "View in Trades →".
Each replaced glyph keeps its accessible name on the control or cell that
holds it (icons stay `aria-hidden`).

### 5. The rail: 64px, icons only, tooltips

`frontend/src/app/shell/shell.html` and `shell.css`:

- The rail narrows from 80px to **64px**. Each entry is a 44×44 hit target
  with a 24px icon. `.rail-label` is removed from the DOM; the link keeps
  `aria-label="<label>"`, so screen readers and the e2e tests still find it
  by name.
- **Tooltip:** each entry gets an `sb-hint` anchored to it, opening to the
  right, showing the label. It opens on hover (after the existing hint
  delay), on keyboard focus, and on a **long-press** (§6) on a touch screen,
  and closes on leave, blur, Escape or tap elsewhere. Only one tooltip shows
  at a time.
- **Active entry:** `--accent-soft` fill plus a 3px `--pos` (mint) bar on the
  rail's inner edge, as in mockup 2.
- **Order:** Dashboard, Watchlist, Trades, **Calendar**, Risk, Insights;
  System at the foot (admin only, as today).
- **Brand:** the diamond heads the rail. The top-bar wordmark reads
  **Bomeo Capital**, Bomeo in `--text` weight 700 and Capital in `--pos`
  weight 500 (the two-tone treatment v202 D2 kept). Every
  `aria-label="Bomeo Capital — …"` already matches. `LABELS.brand` changes
  from "Swingbot" to "Bomeo Capital".
- Tablet (640–1023px) and desktop use the same rail. Phone hides it, as today.

### 6. Calendar as a destination, and the phone tab bar

**Navigation model** (`frontend/src/app/shell/nav.ts`):

- `NAV_ENTRIES` gains `{ path: '/calendar', label: 'Calendar', icon:
  'calendar' }` after Trades. Trades loses its `sections`: Book is the whole
  page, so its section tabs disappear.
- Routes: `/calendar` and `/calendar/:date` take the Calendar workspace and
  its day page. `/trades/calendar` and `/trades/calendar/:date` redirect
  (Angular `redirectTo`, query string kept) to them, so bookmarks and old
  Discord links still land.
- `swingbot/admin/spa.py`'s SPA prefix list gains `"calendar"`, so a hard
  refresh on `/calendar` serves the SPA instead of a 404. This is the
  `bot patch`.
- The command palette, breadcrumb (`breadcrumbFor`: "Calendar", then
  "Calendar / 23 Nov 2026" on a day) and section tabs all read the nav model,
  so they follow without their own changes. Their tests update.

**Phone tab bar** (`phone-tab-bar.ts`, `more-sheet.ts`):

- **Labels always shown**, under each icon, 11px, weight 600. The active tab
  gets the mint-tinted pill. The Dashboard tab keeps its "Home" label (v202 §3).
- **Default tabs:** Home, Watchlist, Trades, Calendar, then More. Risk,
  Insights and System (admin) sit in the More sheet.
- **Press and hold (long-press):** a touch held for 500ms without moving
  more than 10px opens that tab's tooltip above it, using the same `sb-hint`
  as the rail, and navigates nowhere. Release closes it after 1.5s or on the
  next touch, and the click that follows a long-press is swallowed. A move
  over 10px or a second finger cancels it. This lives in one shared
  `sbLongPress` directive, which the rail (§5) and the tab bar both use, and
  which emits on its own (no hint coupling), so it is testable alone.
- **Editing the bar.** The More sheet gains an **Edit tab bar** action
  (pencil icon) that opens the editor in an `sb-drawer` (§7):
  - "In the tab bar": the chosen pages, in order, each with up/down buttons
    (44px targets) and a remove (minus) button. Dashboard is pinned first
    and has none.
  - "Under More": every other page the login may see, each with an add (plus)
    button. Add is disabled while the bar holds 4 pages, with the reason
    shown.
  - A live preview of the bar, **Reset** (back to the default) and **Done**.
    Changes apply at once; Done closes.
  - Up to **4 pages + More**. Fewer than 4 is allowed (minimum: Dashboard).
- **Storage:** `localStorage['ui.tabbar']` holds a JSON array of nav paths,
  read and written through the existing storage wrapper, in try/catch like
  `ui.theme`. On read the list is validated against
  `navEntriesFor(isAdmin)`: unknown, duplicate or admin-only-for-a-viewer
  paths are dropped, Dashboard is forced first, and it is truncated to 4. If
  nothing valid remains, or the value is not JSON, the default is used.
  `/trades/calendar` in a stored list maps to `/calendar`.
- `PHONE_TABS` stops being a constant. A `TabBarPrefs` service exposes a
  `tabs()` signal that `PhoneTabBar`, `MoreSheet` and `phoneTabPathFor` read.
  `phoneTabPathFor` keeps lighting the right tab for detail routes
  (`/calendar/2026-11-23` lights Calendar, `/plans/7` lights Trades).

### 7. Drawers below 1024px: bottom sheets, drag down to close

**`sb-drawer` (`frontend/src/app/ui/layout.ts`):**

- **Below 1024px it is a bottom sheet** (D11): full width under 640px, and
  centred at `min(720px, 100vw)` from 640 to 1023px. Both have the drag
  handle, 85dvh maximum height and rounded top corners
  (`--panel-radius`). From 1024px it stays the right-hand panel. The
  640–1023px `85vw` side rule is deleted.
- **Drag down to close** works below 1024px (`viewport.isNarrow()`, today
  `isPhone()`). The rule is unchanged: a downward drag from the handle or
  header, or from the body while the body is scrolled to the top, pulls the
  sheet with the finger. Release past `SWIPE_CLOSE_PX` (80px) **or** a fast
  flick (over 0.5px/ms in the last 100ms, over 24px) closes it with the exit
  animation from where it was let go. Otherwise it springs back. Scrolling a
  long body never closes the sheet until the body is back at its top.
- The swipe logic moves out of `Drawer` into a shared `sbSwipeDismiss`
  directive (`frontend/src/app/ui/swipe-dismiss.ts`), so the other sheets
  reuse it rather than copy it. `Drawer` behaviour is byte-for-byte the
  same on phone; the existing swipe tests move with it and still pass.
- The close `×` becomes the `close` icon (§4).

**Other sheets get the same gesture:** `sb-more-sheet` and `sb-live-sheet`
(phone bottom sheet; on tablet the live sheet becomes a bottom sheet too,
per D11) adopt `sbSwipeDismiss` and the drag handle. The command palette,
the users-tab form `<dialog>` and `sb-confirm-dialog` are dialogs, not
drawers, and are left alone.

**Detail moves into drawers.** From the 2026-11-23 inventory of tap-for-detail
surfaces below 1024px:

| Surface | Today below 1024px | After |
|---|---|---|
| `sb-data-table` row drawer | phone only, only when a column declares `compact` | **phone and tablet**. Tablet tables keep their full columns; a row tap opens the drawer instead of the inline chevron. Tables with no `compact` columns get a drawer listing every column as label/value pairs, in column order |
| Analytics tables (overview ×3, attribution, benchmark daily, edge ×2, tuning ×2), reports gates and attribution, calendar by-weekday, provider health, swallowed errors | tap does nothing, or only scrolls the pinned column | row tap opens that drawer. Gates' `[expansion]` renders inside it |
| Ticker-detail trades, risk exposure, research registry, system users, cancels | phone drawer; tablet nothing or a route jump | drawer on both, with the existing `detailLink` ("Open full …") where the row has a page |
| Watchlist row on tablet | navigates to `/watchlist/:sym` | drawer preview with the "Open full ticker" link, as on phone |
| Calendar day-page trade cards, day sparklines | navigate to `/trades/:id` | open `TradeDrawer`, whose "Open full trade" link goes to the page |
| Dashboard watchlist panel rows | navigate to `/watchlist/:sym` | drawer preview with the link |
| Risk sector heat rows, matrix cells, clusters | hint popover / nothing | drawer with the row's figures (exact heat, the pair's correlation and both tickers' exposure) |
| Versions lane segments | hover-only tooltip, unreachable by tap | a tap opens a drawer with the segment's release details; the filter toggle moves to a button inside it |
| Live sheet activity/bot rows | nothing | stay as rows (the sheet is itself a drawer; no drawer stacks on a drawer) |

Rules that apply everywhere:

- **No drawer on top of a drawer.** A tap inside an open drawer that would
  open another one navigates instead (today's `detailLink` behaviour).
- **Desktop does not change.** At 1024px and up, row clicks keep today's
  behaviour (route, `TradeDrawer` or nothing). This spec moves only
  phone and tablet to drawers.
- Short explanations (`sb-hint` popovers on stat tiles and figures) and
  chart tooltips stay as they are: a sentence does not need a sheet.
- A drawer's heading is the row's identity (ticker, date, strategy). Its
  body lists the fields with labels, using the same formatters as the
  table, so a figure never reads differently in the drawer than in the row.

### 8. Error, empty and edge states

- No font file (blocked or slow): the metric-matched fallback renders and
  nothing shifts when Jost arrives (`font-display: swap`).
- `ui.theme` holding anything but `graphite`/`navy` → Navy (the new default).
- `ui.tabbar` missing, malformed, empty, over-long, with unknown or
  admin-only paths → validated as in §6. The editor never shows a page the
  login cannot open.
- A viewer (non-admin) never sees System in the rail, More sheet or editor.
- Long-press on a device with a mouse: not triggered by mouse (pointer type
  `touch` or `pen` only); hover covers mouse.
- `prefers-reduced-motion` / Motion Off: the sheet closes without the slide
  (existing `MotionService` path), and the swipe still closes it.
- A drawer opened for a row that disappears on refresh (closed position)
  shows its existing not-found state rather than stale figures.

### 9. Three devices

Every changed screen is checked at phone (390px), tablet (820px) and desktop
(1440px) per `docs/claude/ui-design.md`: rail, top bar, tab bar, editor,
every drawer in §7's table, and one page per workspace for font and shapes.
Touch targets stay ≥44px, nothing scrolls sideways at 390px, and long
labels wrap or truncate with their full text in the drawer.

### 10. Rollback

If the image is rolled back after v240 (`scripts/ops/rollback_to.sh`):

- `/calendar` bookmarks 404 at the server (the old `spa.py` has no
  `calendar` prefix). `/trades/calendar` works again.
- `ui.tabbar` stays in browser storage, unused and harmless. A `ui.theme` of
  `navy` shows the old Navy, and an unset theme shows Black again.
- No data, schema or bot behaviour changes, so there is nothing to undo
  beyond the image.

### 11. Testing

Every change updates the tests it affects and adds new ones for what is new,
edge and empty cases included (CLAUDE.md):

- **Tokens and contrast:** Navy values resolved through `theme-tokens.ts`.
  `contrast.spec.ts` passes for both themes. The radius tokens and the
  `--font-*` declarations are pinned in `tokens.spec.ts`. Nothing reads the
  deleted `midnight-*`/`frost-*` ramps.
- **Theme default:** unset → navy, `'graphite'` → graphite, junk → navy;
  the pre-boot script mirrors it (`index.html` test).
- **Fonts:** `fonts.css` declares only Jost (plus fallbacks), with
  `unicode-range`; the vendored files exist and the paths resolve. A Python
  test confirms the woff2 files and licence are present.
- **Icons:** every `ICON_NAMES` entry has a 24-grid path and a label; the
  `size` input sets the rendered size; filled sub-paths render with
  `fill=currentColor`. A source scan fails if a replaced glyph (`ⓘ ▲ ▼` and
  the standalone close `×`) reappears as an icon in a template.
- **Rail:** 64px; no visible labels; each link keeps its `aria-label`; a
  hint opens on hover, focus and long-press; Calendar sits after Trades.
- **Nav:** `NAV_ENTRIES` order; `/trades/calendar[/:date]` redirects with
  its query; breadcrumbs; `phoneTabPathFor` for detail routes; `spa.py`
  serves `/calendar` (Python test).
- **Tab-bar prefs:** default; valid custom; malformed JSON; empty array;
  more than 4; duplicates; unknown path; admin-only path for a viewer;
  `/trades/calendar` migration; Dashboard forced first; storage throwing.
- **Long-press directive:** fires at 500ms; not before; cancelled by a
  10px move, a second touch or touchcancel; ignores mouse; swallows the
  following click.
- **Swipe directive:** pull past 80px closes; a flick closes; a short pull
  springs back; a drag from a scrolled body does not close; it works at
  tablet width and does nothing at desktop width. The existing Drawer swipe
  tests pass unchanged against the directive.
- **Drawers:** for each surface in §7's table, a tablet-width and a
  phone-width test that a tap opens the drawer with the right heading and
  fields, and a desktop-width test that behaviour is unchanged.
- **E2E (Playwright):** the rail tooltip, the phone editor round-trip
  (remove Watchlist, add Risk, reload, still there, Reset), and drag-to-close
  on a phone and a tablet viewport.

## Out of scope

- The Discord alert chart PNGs and embeds: they keep Inter and the Graphite
  colours (`chart_style.py`, the bare `:root` fixture). Restyling them is a
  separate spec if wanted.
- A light theme.
- Doctena's hero gradient and card shadows (mockup B, rejected).
- The command palette, confirm dialog and users-tab form as drawers.
- Saving the tab-bar choice per account (D9 chose per browser).
- Any change to desktop row-click behaviour.

## What follows

Three plans, each numbered when written, in this order:

1. **Foundations**: Jost vendoring, fonts.css, the Navy palette and default
   flip, radius and button tokens, the icon component's 24 grid and the
   full redraw, glyph-to-icon replacement. Every later plan sits on these
   tokens and icons.
2. **Shell and navigation**: the 64px icon rail with tooltips, the
   `sbLongPress` directive, Calendar as a destination (routes, redirects,
   `spa.py`), the Bomeo Capital wordmark, `TabBarPrefs`, the tab-bar labels,
   the editor.
3. **Drawers**: `sbSwipeDismiss`, the bottom sheet below 1024px, More and
   Live sheets on the gesture, and the surface-by-surface moves in §7's table.

Plan 2's editor opens in an `sb-drawer`, so it gets drag-to-close as soon as
plan 3 lands. Plan 2 does not wait for plan 3.
