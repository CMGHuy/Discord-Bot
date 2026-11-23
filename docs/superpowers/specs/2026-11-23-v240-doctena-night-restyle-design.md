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
The panel review changed three things the mockups show: the active nav marker
and the "Capital" wordmark are blue, not mint (§1, §5); `--text-faint` and
`--accent` are lighter than drawn; and the tab-bar editor has no grip handle.

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
| `--text-faint` | `#6E94A8`. Its existing contract holds: a rule and divider colour, never text (`contrast.spec.ts:56-60`, the `tokens.css` comment), held to the non-text threshold. Doctena's `#4B748A` is lifted anyway so dividers read on all four surfaces. Captions and hints use `--text-muted`, which clears 4.5:1; a scan pins that no text rule reads `--text-faint` |
| `--accent` (accent text, links, nav marker) | `#5AA9D6` (doctena `#328EC0` is 4.1:1 on `--surface-raised`; lifted to clear 4.5:1) |
| `--accent-fill` / `--accent-fill-hi` | `#0072B0` / `#005B8C` (white text 5.1:1 / 7:1; hover darkens, as doctena's pressed state does) |
| `--accent-soft` | `#328EC0` at 24% |
| `--control-border` (new) | `#0072B0`: inputs, selects and segmented controls, 3.28:1 on `--surface` (WCAG 1.4.11 needs 3:1). `--border` stays for panels and rules, where it is decorative |
| `--pos` (gains, long) | `#53CEB5` (doctena mint) |
| `--neg` (losses, short) | `#F07A7A` (doctena error `#C52020`, lifted for a dark ground) |
| `--pos-soft` / `--neg-soft` | mint / coral at 14%. These are palette alpha entries today, so the Navy block re-points them too, or they keep the old hue |

The Navy block now re-points more than the eleven ground and ink tokens, so
`tokens.spec.ts`'s `SHARED` list and its `GROUND_INK_TOKENS` "re-points
exactly" test are rewritten to the new set.

**Mint never marks navigation.** `--pos` and `--neg` have 157 reads in 69
files today, and many are good/bad status rather than money: danger and error
styles, the kill-switch, the shock pill, chip good/bad, flash animations, the
tape and scan progress. Those keep their meaning. This spec adds one rule:
navigation, the brand, active and current states and focus rings never read
`--pos`/`--neg`. They use `--accent`. A source scan pins it over the shell,
rail, tab bar, More sheet, editor and wordmark files. P&L figures keep taking
their colour from their sign, never from the trade's direction. Direction
markers keep today's convention (green ▲ long, red ▼ short), drawn with the
new arrows.

**Every loss carries a true minus** (`−`, U+2212), so a loss never reads by
hue alone (red-green colour blindness). `format.ts` already does this in
`pct`, `money`, `rMultiple` and `signed`. These sites can print an ASCII
hyphen today and are fixed to use the shared formatters or U+2212: `riskPct`,
`attribution.ts` `rFormat` and its `toFixed` calls, `metric-card` and
`metric-chip` `toFixed`, `plan-cell` `formatR`, `tape.ts` `signed`, and the
`figure-text.ts` count-up. Each gets a test with a negative value.

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
  the wrong theme. That script carries copied literals today: `NAVY_BG =
  '#070c18'`, pinned to `--midnight-950` by `primitives.spec.ts` (line 156
  and 286–312) and `tokens.spec.ts` (378–444), and the static
  `<meta name="theme-color" content="#0d0f12">` is Graphite. After this
  change the static meta, the inline cold-load `<style>` ground and the web
  manifest's `background_color`/`theme_color` all take the doctena `--bg`
  (`#00131F`), so a default Navy user never sees a Graphite flash. The script
  gains a `GRAPHITE_BG` literal that it applies only on an explicit
  `'graphite'`. Both literals are pinned to their tokens by the same tests,
  re-pointed, and `HEX_ALLOWLIST`'s exact, source-ordered `index.html` entry
  is updated to match.
- **The generated fixture changes.** `tests/charts/resolved_tokens.json` is
  bare-`:root` only, but it holds the `--font-*` tokens, the radii and every
  palette name. The new radii, fonts, `--control-border`, `--pill-radius` and
  `doctena-*` ramp, and the deleted `midnight-*`/`frost-*`, all change it, so
  each such commit reruns `python scripts/dev/dump_tokens.py` and commits the
  JSON with it. The Navy block must not contain `}` (the block regex in
  `tests/dev/test_dump_tokens.py`).
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
  JetBrains Mono `@font-face` rules.
- **Owners of the old files.** `vendor/inter/` stays while
  `swingbot/core/charts/chart_style.py:20` reads `inter-500.woff2` for the
  Discord charts; it is removed only with that reader. `vendor/jetbrains-mono/`
  has no reader once `fonts.css` drops it, and is deleted in the same plan,
  after the `tnum` check below passes.
- Add doctena's metric-matched fallback faces so a slow font load does not
  shift the layout. Measured from doctena.de's stylesheet, 2026-11-23 (all
  with `line-gap-override: 0%`):

  | Face | Weights | `src: local(...)` | size-adjust | ascent | descent |
  |---|---|---|---|---|---|
  | `Jost Fallback` | 100–500 | Arial, ArialMT | 95.87% | 111.61% | 39.12% |
  | `Jost Fallback` | 600–900 | Arial Bold, Arial-BoldMT | 95.49% | 112.06% | 39.27% |
  | `Jost Fallback Android` | 100–500 | Roboto, Roboto Regular, Roboto-Regular | 96.08% | 111.37% | 39.03% |
  | `Jost Fallback Android` | 600–900 | Roboto Bold, Roboto-Bold | 101.36% | 105.57% | 37% |
- Tokens: `--font-sans: "Jost", "Jost Fallback", "Jost Fallback Android",
  system-ui, sans-serif;` and `--font-mono: var(--font-sans)`. `--font-num`
  and `--font-figure` keep reading those tokens, so no component changes.
  Every rule that reads `--font-num` or `--font-mono` already sets, or now
  gets, `font-variant-numeric: tabular-nums`. Jost has tabular figures (the
  `tnum` feature), which is what keeps columns aligned without a mono face.
  The plan's first font task confirms `tnum` in the vendored file before
  anything depends on it. The plan brief already ran the check (fontTools,
  2026-11-23): `jost-latin-wght-normal.woff2` has the `tnum` GSUB feature,
  weights 100–900 and U+2212; the latin-ext file has no digits, so figures
  always come from the latin file. The plan task re-runs it as a test so a
  future file swap cannot silently lose `tnum`.
- **Gate:** a source-scan test fails any rule that reads `--font-num` or
  `--font-mono`, or styles a `.num` cell, without `font-variant-numeric:
  tabular-nums`. Numeric columns stay right-aligned. The three-device check
  (§9) includes a 12–13px price column, where Jost's x-height is smallest.
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
| `--pill-radius` (new) | – | 999px. The radius gate in `primitives.spec.ts` bans px literals in components, so pills read this token |
| `--chip-radius` | 4px | `var(--pill-radius)` |
| `--radius-sm` | 2px | 6px for swatches and cells; bars and tracks under 6px tall use `--pill-radius` |
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
| `edit`, `up`, `down`, `plus`, `minus` | the tab-bar editor (§6) and drawers. No `grip`: the editor has no drag-reorder, so nothing should look draggable |

**Text glyphs that act as icons become `sb-icon`.** The plan inventories
them from the 48 files that hold `▲ ▼ ⓘ × ✓ ✗ ⚠ ● ○ ★` today. The rule:
a glyph that stands alone as a status, direction, action or info marker
becomes an icon. A glyph inside a sentence or a notation stays text:
`115.26 → 123.05`, `+2.9%`, `N = 412`, and the `→` in "View in Trades →".
Each replaced glyph keeps its accessible name on the control or cell that
holds it (icons stay `aria-hidden`). Glyphs such as `✓ ✗ ⚠ ● ○ ★` may carry
meaning today, so a test checks that each status, direction and outcome cell
keeps its text or `aria-label` after the swap.

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
- **Active entry:** `--accent-soft` fill plus a 3px `--accent` bar on the
  rail's inner edge, and `aria-current="page"`. Mockup 2 drew the bar in mint.
  The panel moved it to `--accent`, because mint means "gain" (§1). The bar
  and the fill are two cues, so the state does not rest on one hue.
- **Order:** Dashboard, Watchlist, Trades, **Calendar**, Risk, Insights;
  System at the foot (admin only, as today).
- **Brand:** the diamond heads the rail. The top-bar wordmark reads
  **Bomeo Capital**, Bomeo in `--text` weight 700 and Capital in `--accent`
  weight 500 (the two-tone treatment v202 D2 kept; blue, not mint, per §1). Every
  `aria-label="Bomeo Capital — …"` already matches. `LABELS.brand` changes
  from "Swingbot" to "Bomeo Capital".
- Tablet (640–1023px) and desktop use the same rail. Phone hides it, as today.

### 6. Calendar as a destination, and the phone tab bar

**Navigation model** (`frontend/src/app/shell/nav.ts`):

- `NAV_ENTRIES` gains `{ path: '/calendar', label: 'Calendar', icon:
  'calendar' }` after Trades. Trades loses its `sections`: Book is the whole
  page, so its section tabs disappear.
- Routes: the redirect direction flips, in one change. Today
  `app.routes.ts:84-85` sends `calendar` and `calendar/:date` to
  `trades/calendar[/:date]`, and `nav.ts:98` holds the alias
  `'/calendar': '/trades/calendar'`. After: the Calendar workspace loads at
  `/calendar` and `/calendar/:date`; `/trades/calendar` and
  `/trades/calendar/:date` redirect to them (query string kept); the old
  redirects and the alias are deleted, so no pair of redirects points at each
  other. The `trades/calendar` route guard comment (`app.routes.ts:49`) moves
  with it. Bookmarks and old Discord links still land.
- `swingbot/admin/spa.py`: `"calendar"` is **already** in `WORKSPACES`
  (line 57), but in the "pre-v202 names … removed at Phase 4's close-out"
  group, and the comment at lines 44–49 lists it for removal. It moves into
  the destinations group (line 55) and the removal note drops it, so no later
  close-out deletes a live destination's prefix. `"trades"` stays, which
  keeps `/trades/calendar` reachable on a reload for its redirect. This is the
  `bot patch`, and a Python test pins `calendar` as a destination.
- The command palette, breadcrumb (`breadcrumbFor`: "Calendar", then
  "Calendar / 23 Nov 2026" on a day) and section tabs all read the nav model,
  so they follow without their own changes. Their tests update.

**Phone tab bar** (`phone-tab-bar.ts`, `more-sheet.ts`):

- **Labels always shown**, under each icon, 11px, weight 600. The active tab
  gets the `--accent-soft` pill with the icon in `--accent` (not mint, §1) and
  `aria-current="page"`. The Dashboard tab keeps its "Home" label (v202 §3).
  Tabs share the bar's width equally, whether it holds 2 or 5, and the 5-tab
  bar is checked at 320px.
- **Default tabs:** Home, Watchlist, Trades, Calendar, then More. Risk,
  Insights and System (admin) sit in the More sheet.
- **Press and hold (long-press):** a touch held for 500ms without moving
  more than 10px opens that tab's tooltip above it, using the same `sb-hint`
  as the rail, and navigates nowhere. The tooltip stays until the next touch
  anywhere, or Escape (no timed close, so a slow reader is not rushed). The
  click that follows a long-press is swallowed. A move over 10px or a second
  finger cancels it. This lives in one shared `sbLongPress` directive, which
  the rail (§5) and the tab bar both use, and which emits on its own (no hint
  coupling), so it is testable alone.
- **The OS must not fight it.** A held touch on a link opens the iOS/Android
  link preview, the context menu or text selection. The directive's host
  links get `-webkit-touch-callout: none` and `user-select: none`, and the
  directive prevents `contextmenu` for touch-originated presses only. Tests
  cover all three.
- **Editing the bar.** The More sheet gains an **Edit tab bar** action
  (pencil icon) that opens the editor in an `sb-drawer` (§7):
  - "In the tab bar": the chosen pages, in order, each with up/down buttons
    (44px targets) and a remove (minus) button. Dashboard is pinned first
    and has none.
  - "Under More": every other page the login may see, each with an add (plus)
    button. Add is disabled while the bar holds 4 pages, and the reason
    ("The bar holds 4 pages. Remove one to add another.") shows as inline text
    above the Under More list, never only in a tooltip.
  - A live preview of the bar, **Reset** (back to the default) and **Done**.
    Changes apply at once; Done closes. Reset shows an inline **Undo** for 8
    seconds. Every move, add, remove and reset is announced through an
    `aria-live="polite"` region ("Calendar moved to position 3").
  - Up to **4 pages + More**. Fewer than 4 is allowed (minimum: Dashboard).
  - Reordering is by the buttons only, so nothing in the editor competes with
    the sheet's drag-to-close. Focus is trapped in the editor and returns to
    the **Edit tab bar** button when it closes.
  - **Risk is never out of reach.** The editor moves pages between the bar
    and More and never hides one, so Risk (heat, the 2% dollar-risk cap) is
    always one tap from the bar. A test pins that every nav page the login
    may see is in exactly one of the two lists. The Dashboard's open-risk
    figure (`trading-performance.ts`) stays on the phone layout, so heat is
    readable without opening Risk.
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
- **Drag down to close**, in three separate steps so each is provable:
  1. **Extract, no behaviour change.** The swipe logic (`layout.ts:600-638`)
     moves out of `Drawer` into a shared `sbSwipeDismiss` directive
     (`frontend/src/app/ui/swipe-dismiss.ts`). Phone behaviour is identical:
     a downward drag from the handle or header, or from the body while the
     body is scrolled to the top, pulls the sheet with the finger; release
     past `SWIPE_CLOSE_PX` (80px) closes it from where it was let go,
     otherwise it springs back. The existing swipe tests move with it,
     unchanged, and pass.
  2. **Widen.** The gesture works below 1024px (`viewport.isNarrow()`,
     today `isPhone()`).
  3. **Add flick.** A fast flick (over 0.5px/ms over the last 100ms, and over
     24px) also closes it. New tests cover it.

  Scrolling a long body never closes the sheet until the body is back at its
  top.
- **A visible close button stays on every sheet**: `sb-drawer`, More and
  Live, at least 44×44px, as the non-drag alternative (WCAG 2.5.7). The
  close `×` text becomes the `close` icon (§4). Focus returns to the control
  that opened the sheet.
- **Landscape phone** (e.g. 844×390) is 640px+ wide and below 1024px, so it
  gets the centred sheet. At 85dvh of 390px (about 330px) the handle and
  header stay fixed and the body scrolls; §9 adds this size to the checks.

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

**`sb-data-table` gets an explicit, per-table policy.** Today the row drawer
is gated by `phone()` and at least one `compact` column
(`data-table.ts:723-757`), and `phoneTap` (`'drawer' | 'emit'`) applies to
phones only; its docstring promises "tablet and desktop rows are unaffected".
Turning drawers on for tablet changes all 18 consumers at once, so the input
is renamed `narrowTap` (`'drawer' | 'emit' | 'none'`), applies below 1024px,
and defaults to `'drawer'`. Each consumer is set explicitly in the plan, so
the change is auditable table by table:

- `'emit'` keeps its owner's drawer at tablet width too: Dashboard positions
  → `TradeDrawer`, Research ledger → its own drawer.
- `'none'` for any table whose rows carry nothing beyond what the row shows.
- The card layout (`cardsAt`) stays phone-only: tablet keeps full columns.
  `[expansion]` content renders inside the drawer on both widths, and the
  inline chevron row is removed below 1024px.

Rules that apply everywhere:

- **An interactive cell wins over the row.** A link, button, sort header or
  checkbox in a row does its own thing; only a tap elsewhere on the row opens
  the drawer. A tappable row shows a trailing chevron and is focusable
  (`tabindex="0"`); Enter or Space opens the drawer, and focus returns to the
  row when it closes.
- **The drawer adds to the row; it never replaces it.** No column a row shows
  today is removed by this spec. On phone the `compact` columns that carry
  risk (risk $, % of account, stop, R on trade, plan and exposure tables)
  stay on the card. Risk sector rows keep their heat % against the heat cap
  visible on the row; the drawer adds the exact figures. `TradeDrawer`
  already shows entry, stop, target and dollar risk; a test pins that.
- **Drawers carry the row's caveats.** A drawer for a plan, trade or
  strategy row shows its badge tier and as-of time. Any caveat label a
  figure carries in its row (pre-cost, pre-tax, sample size) is repeated
  beside that figure in the drawer.
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

Every changed screen is checked at phone (390px, and 320px for the tab bar),
landscape phone (844×390), tablet (820px) and desktop (1440px) per `docs/claude/ui-design.md`: rail, top bar, tab bar, editor,
every drawer in §7's table, and one page per workspace for font and shapes.
Touch targets stay ≥44px, nothing scrolls sideways at 390px, and long
labels wrap or truncate with their full text in the drawer.

### 10. Rollback

If the image is rolled back after v240 (`scripts/ops/rollback_to.sh`):

- `/calendar` bookmarks keep working: the old `spa.py` already serves the
  `calendar` prefix (line 57), and the old router redirects it to
  `/trades/calendar` (`app.routes.ts:84-85`).
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
- **Panel-driven gates:** no nav, brand, active-state or focus rule reads
  `--pos`/`--neg` (source scan over the shell files); no text rule reads
  `--text-faint`; Jost's `tnum` feature is present in the vendored latin file
  (fontTools test); every formatted loss carries U+2212, including the seven
  sites listed in §1; every
  `--font-num`/`.num` rule has `tabular-nums` (source scan); status,
  direction and outcome cells keep an accessible name after the glyph swap;
  `narrowTap` is set explicitly on every `sb-data-table` consumer; an
  interactive cell click does not open the row drawer; Enter/Space on a
  focused row opens it; `TradeDrawer` shows entry, stop, target and
  dollar risk; drawers show badge tier and as-of time; the editor's two lists
  partition the visible nav pages; long-press host links carry
  `-webkit-touch-callout: none` and touch `contextmenu` is prevented.
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

Five plans, each numbered when written, each under the 20-task cap, run
**strictly in this order** (one worktree at a time):

1. **Theme and type**: Jost vendoring and the `tnum` check, fonts.css and
   fallbacks, the Navy palette and default flip (pre-boot literals, meta),
   `--control-border`, radius and button tokens, the money-colour and
   true-minus rules, the `tabular-nums` gate, JetBrains Mono removal.
2. **Icons**: the 24-grid `sb-icon` with `size` and filled sub-paths, the
   full redraw, the new names, and glyph-to-icon replacement across the
   48 files, with accessible-name tests.
3. **Shell and navigation**: the 64px rail with tooltips, `sbLongPress`,
   Calendar as a destination (redirect flip, alias removal, `spa.py`
   regrouping), the wordmark, `TabBarPrefs`, tab-bar labels, the editor.
4. **Drawer core**: `sbSwipeDismiss` (extract, widen, flick as separate
   tasks), the bottom sheet below 1024px, More and Live sheets on the
   gesture with close buttons, and `sb-data-table`'s `narrowTap` policy set
   on all 18 consumers.
5. **Drawer surfaces**: the bespoke moves in §7's table (watchlist,
   calendar day cards, dashboard watchlist panel, risk sector/matrix/
   clusters, versions lanes, caveats in drawers).

Why strictly in order: plans 1 and 2 change tokens and icons every later
screen is checked against. Plans 3 and 4 both edit `shell/more-sheet.ts`
(the Edit action and `TabBarPrefs` in 3; the gesture and handle in 4) and
`sb-drawer` use, so they never run in parallel. Plan 5 builds on plan 4's
policy input.

## Panel review

Run 2026-11-23 on a91c43db, serially: ux-designer (sonnet), staff-engineer
(opus), financial-advisor (sonnet). No BLOCKING findings; 32 ADVISORY.
Duplicates are merged on one line naming every seat.

- ux-designer, financial-advisor: mint marks the active nav entry, tab pill and wordmark, so it means both "you are here" and "gain" -- applied: nav, brand and active states use `--accent`; mint and coral only on signed money, R and direction (§1, §5, §6).
- ux-designer: `--text-faint` `#4B748A` is 3.4–3.7:1, under 4.5:1 for text -- applied: `#6E94A8` (§1).
- ux-designer: `--accent-fill-hi` and accent text under 4.5:1 -- applied: hover `#005B8C`, accent text `#5AA9D6` (§1).
- ux-designer: borders under 3:1 in a flat, shadowless design -- applied: new `--control-border` `#0072B0` for controls; `--border` stays decorative (§1).
- ux-designer, financial-advisor: no gate that numeric rules carry `tabular-nums`; small-size legibility -- applied: source-scan gate, right alignment, 12–13px check, and a JetBrains Mono fallback for `--font-num` if `tnum` is missing (§2). Slashed zero -- rejected: IDs are hex and tickers are letters, so 0/O is not ambiguous here.
- ux-designer: icon-only rail is undiscoverable on tablet; keep labels or an expand toggle there -- rejected: the partner chose icons only (D5), knowingly reversing v202 §3; tooltips on hover, focus and long-press cover it.
- ux-designer: long-press fights the OS link preview, context menu and text selection; the 1.5s close is short -- applied: callout/selection off, touch `contextmenu` prevented, tooltip stays until the next touch (§6). Dropping long-press from the labelled tab bar -- rejected: the partner asked for it (D9).
- ux-designer: `grip` implies drag-reorder; where the add-disabled reason shows; Reset undo; announcements -- applied: no grip, inline reason, 8s Undo, `aria-live` (§4, §6).
- ux-designer: editor reorder vs sheet drag; focus trap and return -- applied: buttons only, focus trapped and returned (§6).
- ux-designer: tablet row drawers conflict with cell links and sort headers; rows need an affordance and keyboard access -- applied: interactive cells win, trailing chevron, focusable rows, Enter/Space, focus return (§7).
- ux-designer: drag needs a non-drag alternative on every sheet; landscape phone falls into the tablet sheet -- applied: 44px close button on drawer, More and Live; 844×390 added to §9 (§7, §9).
- ux-designer: tab spacing with fewer tabs; 320px -- applied: equal-width tabs, 320px check (§6, §9).
- staff-engineer: `calendar` is already in `spa.py` `WORKSPACES`, flagged for removal -- applied: move it to the destinations group and rewrite the removal note, not "add" it (§6).
- staff-engineer: rollback text wrong, old image still serves `/calendar` -- applied (§10).
- staff-engineer: `app.routes.ts:84-85` and the `nav.ts:98` alias redirect the other way, so the two would loop -- applied: flip and delete in one change (§6).
- staff-engineer: pre-boot `NAVY_BG` and the static theme-color meta are copied literals pinned to the deleted `--midnight-950` -- applied: doctena `--bg` for meta and default, `GRAPHITE_BG` for explicit Black, both pinned (§1).
- staff-engineer: tablet drawers flip the default for all 18 `sb-data-table` consumers; `phoneTap: 'emit'` owners unaddressed -- applied: `narrowTap` policy (`drawer`/`emit`/`none`) set explicitly per consumer, `cardsAt` stays phone-only (§7).
- staff-engineer: "byte-for-byte" refactor contradicts the added flick -- applied: extract, widen and flick are three separate steps with their own tests (§7).
- staff-engineer: plans 1 and 3 would exceed 20 tasks -- applied: five plans, theme/type, icons, shell, drawer core, drawer surfaces (What follows).
- staff-engineer: plans 2 and 3 both edit `more-sheet.ts` -- applied: strict order, never parallel (What follows).
- staff-engineer: fallback-face metrics cited but not recorded -- applied: measured values tabled (§2).
- staff-engineer: JetBrains Mono and Inter files lose their SPA readers; name owners -- applied: Inter kept while `chart_style.py:20` reads it; JetBrains Mono deleted after the `tnum` check (§2).
- financial-advisor: direction arrows on P&L tokens make a winning short red -- rejected: today's convention (green ▲ long, red ▼ short) is kept with the new arrows, and P&L figures already take colour from their sign (§1 states it).
- financial-advisor: losses readable only by hue -- applied: true minus on every loss, formatter test (§1).
- financial-advisor: Risk behind More by default -- applied: the editor never hides a page, a partition test, and the Dashboard open-risk figure stays on phone (§6).
- financial-advisor: drawers must not replace row risk figures -- applied: no column removed; risk compact columns stay on phone cards; heat % stays on sector rows; `TradeDrawer` contents pinned (§7).
- financial-advisor: drawers must carry badge tier, as-of time and caveats -- applied (§7).
- financial-advisor: status cells must keep accessible names after the glyph swap -- applied, with a test (§4).
- financial-advisor: mint/coral must not be confused with chip blues -- applied: the money-colour rule (§1).

### Corrections from the plan 1 code brief (2026-11-23)

The brief for plan 1 read the code the panel could not, and corrected four
premises: `--text-faint` keeps its non-text (divider) contract and text uses
`--text-muted`; the whole-app "mint for money only" scan cannot pass (157
reads in 69 files, many legitimate good/bad status), so the rule narrows to
navigation, brand, active and focus states; the cold-load inline style and the
web manifest join the meta in taking the Navy ground; and `--control-border`
measures 3.28:1, not 3.4:1. It also confirmed Jost's `tnum`, so the JetBrains
Mono fallback is dropped. It added `--pill-radius`, the Navy `--pos-soft`/`--neg-soft`
re-point, the fixture regeneration rule, and the seven true-minus sites.

### Corrections from the plan 2 code brief (2026-11-23)

The brief for plan 2 read the icon and glyph sites and corrected these premises.
**Glyph count:** "48 files" counted comments and `×` used as multiplication
(`1.40×`, `1.5 × ATR`), which §4's rule keeps as text. Only about 8 standalone
markers exist: `direction-arrow.ts` ▲/▼, `layout.ts` × close and ▾/▸ toggle,
`data-table.ts` ▾/▸, `watchlist.ts` ◉/○, `versions.ts` `&#9650;`, and `guide.ts`
CSS ▸/▾. Replacing them is one task.
**Absent glyphs:** `ⓘ ✗ ● ★` appear nowhere. `✓` is a value suffix in `plan-cell.ts`
and stays text. `⚠` is a server-built prefix (`short_notice.py`) and stays.
**Hint:** `sb-hint` draws a letter in a CSS circle, not `ⓘ`. It now always
draws the `info` icon and loses its `glyph` input. The rail's version hint (`v`)
and the dashboard's open-positions help (`?`) become `info` too (partner,
2026-11-23).
**Accessible names:** status and outcome cells are a CSS dot, bar and text,
so they have no glyph to lose. The accessible-name test instead guards these:
- direction-arrow
- the recent-activity icon host
- the plan-cell closed icon
- the tape toggle
- the drawer close button
- the panel and row toggles
- the `info` trigger
**Mockup conflicts, where the spec wins:** stroke is 1.8 everywhere (mockup 4
draws 2), `analytics` is the bulb with a rising line (mockup 4 draws bars), and
there is no `grip` (mockups 3 and 4 draw one).
**Existing pins:** `icon.spec.ts` pins the old half-hatched `theme` path, and
`shell.css`/`shell.spec.ts` pin the 24px svg override. Both move with the new
`theme` crescent and the `size` input.
