# Admin SPA refresh — Design (v18)

**Version:** ui 1.1.0 · bot 1.1.2
**Date:** 2026-08-13
**Status:** approved, not yet implemented
**Supersedes parts of:**

- `2026-08-08-v20-admin-design-system-design.md` — **Decision 2** (which removed the
  compact/full toggle and drag-to-reorder, and fixed the Trades table at seven
  columns) and **Decision 3** (the colour rules and the motion scale).
- `2026-08-08-v14-angular-workspaces-design.md` — **Decision 5**, the Cockpit's
  fixed four-column summary table.
- `2026-08-08-v15-jinja-cutover-design.md` — **Decision 1**'s schedule only. Its
  Decision 3 (the PNG chart routes stay deleted) is *upheld*, not reversed.
- The migration plan's global constraint *"`visible` columns carry no order"*.

---

## Why this exists

The Angular SPA shipped as the default admin UI on 2026-08-13 (Release A, `ui`
1.1.0). It is correct, it is fast, and it is missing things the Jinja UI had —
not by oversight in every case, but by decisions taken during the migration that
have not survived contact with daily use.

Three of those decisions are reversed here, deliberately and on the record:

1. **The colour system was too restrictive.** `green/red = money only · amber =
   caution · blue = interactive only · everything else greyscale` produced a UI
   that is consistent and almost entirely grey. Confidence and tier — the two
   fields that most want to be scannable — were explicitly rendered greyscale.
2. **Motion was ruled out.** "120ms on state change and nothing on entrance",
   on the reasoning that with real-time push "something changed" is continuous.
   True for card flashes; it also removed the feedback that makes a live table
   feel live.
3. **The PNG chart routes were deleted** on the reasoning that the SPA draws its
   own charts. It does — but the SPA's chart draws candles, and the PNG draws
   the *reason the trade exists*. The information went away with the route.

Alongside those, the migration ported routes but never audited *features*, the
Trades table lost the Jinja dashboard's compact/full density model, and the
layout was verified at exactly one viewport width.

This document is the design for fixing all of it in one pass.

## The problem being solved

Concretely, as observed:

- The Trades table shows seven columns with no density control. The Jinja
  dashboard had a Compact/Full toggle, an `entry → target / stop` combined
  cell, ▲/▼ direction arrows and a per-page selector. None were carried over.
- The Status column is a text chip. The Jinja dashboard's Status cell was a
  pulsing proximity dot, an SL→TP position bar with an entry tick, and a
  progress percentage — the single densest, most-used cell in the old UI.
- Confidence and tier are greyscale by design and therefore unscannable.
- The Dashboard (then "Cockpit") table is a fixed four-column summary that
  shares no behaviour with the Trades table.
- The trade Chart tab draws a bare candlestick series. The indicators, plan
  levels, risk/reward shading and confirmed-strategy overlay that the Discord
  PNG carries have no equivalent anywhere in the UI.
- "Cockpit" and "Universe" are names nobody uses. The bot's own vocabulary is
  *dashboard* and *watchlist*.
- The sidebar is a fixed 168px column of six text labels, always expanded.
- Layout is committed to 1280px. Below that it degrades; on a phone it is
  unusable. Above 1440px content stretches.
- The guinea-pig/cat artwork — favicon, avatar — did not make the migration.
  The SPA ships Angular's default `favicon.ico`.

## Scope

One spec, one plan, five phases, executed on a worktree branch. Phases merge to
`main` individually. Jinja remains reachable via `ADMIN_UI=jinja` for the whole
duration.

---

# Decision 1 — Phasing, and the parallelism model

Five phases. The ordering is driven by two constraints: *build once against the
final palette*, and *do the wide mechanical edits before anything fans out*.

| Phase | Content | Lanes |
|---|---|---|
| **P0 Foundation** | `tokens.css` re-palette · motion and spacing scales · Cockpit→Dashboard and Universe→Watchlist end-to-end · avatar/favicon assets into `frontend/public/` | **1 — serial** |
| **P1 Tables** | `TradeRow` status/progress fields · plan cell, direction arrow, confidence cell · compact/full density · picker, reorder, per-page · Dashboard adopts the table | **4** |
| **P2 Shell & responsive** | Collapsible icon-rail sidebar · profile menu · breakpoint system · table→cards at phone width · per-workspace responsive passes | **8** |
| **P3 Chart** | Server geometry endpoint · panes and indicators · plan-line primitives · strategy-overlay primitives | **2, then 3** |
| **P4 Parity** | 19-template feature audit · gap table · gap fills | **~5, then 1/gap** |

### Why the renames go first

Cockpit→Dashboard and Universe→Watchlist touch the route, the API path, the
store, the component files, `spa.py`'s workspace prefixes, the tests and the
specs. Every one of those files is also touched by P1–P4. Doing the renames
mid-plan would guarantee merge conflicts between concurrently dispatched
agents. They are mechanical, they are wide, and they belong in the serial
phase where nothing else is running.

### Why the palette goes first

P1's cells are colour decisions: the plan cell's target/stop hues, the status
bar's fill ramp, the confidence badge, the direction arrows. Building them
against the current near-greyscale tokens and restyling later means making each
decision twice — and the second pass is exactly where inconsistency enters.
`tokens.css` is one file that every component already reads through CSS custom
properties, so the swap is cheap when done first and expensive when done last.

### What the plan must carry for parallel dispatch

Every task in the implementation plan carries two extra lines:

- **`Owns:`** — the exact file paths that task creates or edits.
- **`Blocked by:`** — the task IDs that must land first.

A dispatching session reads those two lines to decide what is safe to run
concurrently, rather than inferring it from prose. Two tasks in the same phase
whose `Owns:` sets are disjoint may run in parallel; any overlap serialises them.

---

# Decision 2 — The colour system

**The rule changes from "one colour, one domain" to "one colour, one valence."**

The old rule was restrictive because it bound each hue to a single data type,
which left no colour available for anything that was neither money nor
interactive. The new rule binds each hue to a *meaning*, which can appear in
any domain — so confidence, tier, direction and status can all be coloured
without any hue meaning two contradictory things.

| Token | Value | Means, everywhere |
|---|---|---|
| `--pos` | `#17c98e` | good — gain, long, target |
| `--neg` | `#ff5470` | bad — loss, short, stop |
| `--warn` | `#ffb43d` | caution — stale data, risk near cap, paused, ageing trade |
| `--accent` | `#7b5cfa` | interactive and brand — links, focus, selection, active nav |
| `--info` | `#46c2ff` | neutral information — horizon pills, strategy tags, counts |

Greyscale remains structure and secondary text. A sixth hue is a review defect.

### Surfaces and text

Off pure black, onto an indigo-charcoal ramp — the "modern fintech" direction.

```
--bg               #0a0b10
--surface          #10121a
--surface-raised   #171a25
--surface-overlay  #1e2230
--border           #232838
--border-strong    #333a4f

--text             #e9ebf5
--text-secondary   #9ba3bd
--text-muted       #6d7590
--text-faint       #464d63
```

Each semantic colour additionally gets a `-soft` variant at 12% alpha
(`--pos-soft`, `--neg-soft`, `--warn-soft`, `--accent-soft`, `--info-soft`) for
cell backgrounds, chips and hover states. The three headline Dashboard metrics
carry an accent gradient; nothing else does. Gradients are a garnish, and a
gradient on every panel is the failure mode of this palette direction.

### The quality ramp

Confidence and tier stop being greyscale and take the valence ramp:

| Band | Confidence | Tier | Token |
|---|---|---|---|
| best | Lv5 | A | `--pos` |
| good | Lv4 | — | `--info` |
| neutral | Lv3 | B | `--text-secondary` |
| weak | Lv2 | C | `--warn` |
| worst | Lv1 | — | `--neg` |

This is consistent with the valence rule — Lv1 genuinely is bad — and it is
what the Jinja UI did, which is why the column was asked for back.

### The one recorded exception

**LONG ▲ uses `--pos`, SHORT ▼ uses `--neg`.** A short position is not "bad",
so this bends the valence rule. It is kept because the *glyph* is the primary
signal and the colour only reinforces it, and because every trading platform in
existence renders direction this way — a UI that broke the convention to satisfy
an internal rule would be worse, not more consistent.

Colour-blind accommodation is explicitly **out of scope**: single user, normal
colour vision, confirmed. Where a redundant cue exists anyway (the ▲/▼ glyphs,
the `+`/`−` on P&L, position along the status bar) it is kept because it costs
nothing, but no design decision is made for that reason.

### Light theme

Still no. Dark only, no `prefers-color-scheme` block, no `[data-theme]` hook.
Unchanged from the design-system spec.

---

# Decision 3 — Motion

The single `--duration: 120ms` becomes a three-step scale:

```
--dur-instant  90ms   hover, press, focus ring
--dur-base    160ms   state change, value flash, bar easing
--dur-slow    260ms   layout — sidebar, panel reflow, route transition
--ease-out    cubic-bezier(.2, .8, .3, 1)
--ease-spring cubic-bezier(.34, 1.4, .64, 1)   sidebar only
```

Four categories of motion, all in:

1. **Live-data feedback.** Price cells flash `--pos-soft` / `--neg-soft` for
   `--dur-base` on tick. The status dot pulses at a period taken from the
   server's `blink_seconds`. Progress bars ease to their new width rather than
   jumping.
2. **Navigation and layout.** Sidebar collapse/expand at `--dur-slow` with
   `--ease-spring`; route change cross-fades; the tab underline slides.
3. **Interaction feedback.** Button press states, row and card hover lift,
   toast slide-in, dialog scale-in, skeleton shimmer while loading.
4. **Chart.** Pan/zoom easing, crosshair fade, plan lines drawing in on mount.

**The design-system spec's original concern still stands and is answered:** the
thing it ruled out was a card-flash on *every push event*, which under
continuous real-time push becomes a permanent flicker. Category 1 is scoped to
the specific cell whose value changed, not the card containing it, which is why
it does not reproduce that failure.

A `@media (prefers-reduced-motion: reduce)` block sets every duration to `0ms`.
Three lines, and it is the difference between "animated" and "unusable at the
end of a long day".

---

# Decision 4 — The Trades table

## Two modes, default compact

| Mode | Columns |
|---|---|
| **Compact** *(default)* | `#` · Status · Ticker · Confidence · Direction · Now · Plan · P&L % · R · Opened · Closed |
| **Full** | `#` · Status · Ticker · Confidence · Direction · Now · Plan · R:R · R · Strategy · Horizon · P&L % · Held · Realized · Opened · Closed |

Row actions (↗ open detail, ✕ close trade) are **pinned at the row end in both
modes** and are not part of either column list — they cannot be picked away or
dragged out of position. This is a change from the current table, where
`actions` is an ordinary column entry.

Compact is the default for both tables, on first load and for any user with no
stored preference.

## The combined Plan column

One column replaces Entry, Target and Stop in **both** modes:

```
178.00 → 195.00 / 170.00
 entry    target    stop
 muted    --pos     --neg
```

Rendered in `--font-mono`, one line, no wrap. The reading is always
`entry → target / stop` regardless of direction — for a SHORT the target is the
lower number and the stop the higher one, and the colours, not the positions,
carry which is which. A hover tooltip spells out `Entry 178.00 · Target 195.00 ·
Stop 170.00` for anyone who has not learned the shorthand.

Not sortable. There is no meaningful single sort key for three prices, and
offering a control that sorts by an arbitrary one of them would be worse than
offering none. `entry`, `stop_loss` and `target` remain as individual columns in
the picker for anyone who wants a sortable price column back.

## Direction

Glyph only: **▲** in `--pos` for LONG/bullish, **▼** in `--neg` for SHORT/bearish.
No text. `title` and `aria-label` carry "Long (bullish)" / "Short (bearish)" so
the meaning is reachable by hover and by screen reader. Sortable, keyed on
direction so all longs group together.

## Confidence

`Lv4 · 78` in one cell — level and score together, the score in
`--text-secondary`, the level in its quality-ramp colour. Sortable on level.
When a trade carries no score (older records), the cell renders `Lv4` alone
rather than `Lv4 · —`.

## Controls that survive alongside the modes

All four, on the toolbar beside the mode toggle:

- **Column picker.** The mode sets the baseline visible set; any add or remove
  after that is stored *per mode*, so customising Full does not disturb Compact
  and switching back and forth does not discard either. Every column outside a
  given baseline stays reachable here — Shares, Deployed, Exit, Origin, Tier and
  the three individual price columns in both modes, plus R:R, Strategy, Horizon,
  Held and Realized when you are in Compact.
- **Drag-to-reorder.** Header drag reorders columns, persisted per table and per
  mode.
- **Per-page.** 10 / 25 / 50 / All, as the Jinja table had.
- **Filters and status chips.** Unchanged from the current workspace.

## Row expansion stays

The design-system spec introduced row expansion to hold the eleven fields the
seven-column default hid. It is **kept**, with a narrowed job: it now holds
whatever is outside the *current* mode's visible set, which in Full mode is
little and in Compact mode is most of the analytical fields. Two reasons it
earns its place even now that Full exists: some fields (target sources, the leg
breakdown of a partially-closed trade, the note) are genuinely one-trade-at-a-time
reading and were never candidates for a column; and the expansion's label/value
grid is the same layout the phone card uses (Decision 9), so keeping it means
the mobile view is a re-flow of something that already exists rather than a
third rendering of the same row.

### Reversal recorded

The migration plan's global constraint reads *"`visible` columns carry no order.
The data table renders in `columns` order. Do not add an ordering input at any
call site."* **That constraint is withdrawn.** `DataTableComponent` gains an
optional ordered visible-column list, and `PreferencesStore` persists it. The
original reasoning — that ordering is a second source of truth that can
disagree with `columns` — is handled by making the persisted order a *filter and
sort over* `columns` rather than a parallel list: an unknown key in the stored
order is dropped on read, and a column present in `columns` but absent from the
stored order appends at the end. A stale preference can therefore never hide a
column or crash a render.

## Persistence

`PreferencesStore` (server-side, not localStorage — unchanged from spec v13)
gains one key per table:

```
tables.<tableId>.density            "compact" | "full"
tables.<tableId>.<density>.columns  ordered string[]
tables.<tableId>.perPage            10 | 25 | 50 | 0
```

`tableId` is `trades` and `dashboard`. Reads tolerate absence at every level and
fall back to the baseline.

---

# Decision 5 — The Status cell

Three parts, restored from the Jinja dashboard:

```
● ▓▓▓▓▓▓░░░░  62%
│ │     │       └ 0% = stop, 100% = target
│ │     └ entry tick
│ └ fill: stop (left) → target (right), coloured by side
└ proximity dot; pulses, faster the nearer SL or TP
```

## The maths already exists — do not reimplement it

- `swingbot/core/performance.py` computes `proximity`, `color`, `blink_seconds`
  and `label` for a trade.
- `swingbot/admin/dashboard.py` computes `pos_pct` (0 = stop, 100 = target),
  `entry_pct` (where the entry tick sits) and `pos_color(pos_pct, entry_pct)`.

The API exposes these on `TradeRow`; the SPA renders them. **No TypeScript
reimplementation.** A second implementation of the proximity ramp would drift
from the one the bot uses for its own near-close alerts, and the two disagreeing
about how close a trade is to its stop is a correctness bug, not a cosmetic one.

New `TradeRow` fields:

```
progress_pct    float | null   0..100, null when no live price
entry_pct       float | null   0..100
progress_color  string | null  token name, not a hex literal
blink_seconds   float | null
status_label    string         human-readable, drives the tooltip
```

`progress_color` returns a **token name**, never a hex value. The server does
not own the palette; sending `#6dda9e` from Python is how the Jinja UI ended up
with colours that no longer matched its own stylesheet.

**Refinement, found while planning:** the Jinja bar's fill is not one colour but
an *interpolation* — red at the stop, grey at the entry tick, green at the
target (`admin/dashboard.py::pos_color`) — and a token name cannot express a
lerp. So the field is `progress_band ∈ {toward_stop, neutral, toward_target}`,
naming which pair of tokens to interpolate between, and the client does the
interpolation in CSS between `--neg` / `--text-muted` / `--pos`. The semantics
(which band, how urgent) stay server-side; only the mixing moves to the client,
which is where the palette lives.

## Degraded states

The bar is meaningless without a live price and a live position, so:

| Condition | Renders |
|---|---|
| ACTIVE/PARTIAL with a live price | dot + bar + `62%` |
| ACTIVE/PARTIAL, no live price | text status chip + `no price` in `--text-muted` |
| PENDING | text status chip only — nothing has been entered yet |
| CLOSED / CANCELLED / EXPIRED | text status chip, coloured by outcome |

The text status chip is the current SPA `StatusIndicator`, kept for exactly
these cases rather than deleted.

## Sorting

The column sorts on `progress_pct`, so "closest to its target" and "closest to
its stop" are one click apart. Rows with no progress sort last in both
directions rather than clustering at whichever end zero happens to fall.

---

# Decision 6 — The Dashboard table

The Dashboard (ex-Cockpit) "Open positions" table becomes **the same component,
the same two modes, the same column definitions, the same picker / reorder /
per-page controls** as Trades, filtered to open positions and defaulting to
compact.

Its `tableId` is `dashboard`, so its density and column choices are stored
separately from the Trades table's — the same table, independently configured.

This reverses spec v14's "four columns, and no column picker: this is a summary,
and every field earns its place". The counter-argument that wins: two tables of
the same rows that behave differently is a thing to learn twice, and the
Dashboard is where a position is most often looked at first.

---

# Decision 7 — Renames

Both go end-to-end: route, API path, store, component files, `spa.py` workspace
prefixes, tests, docs.

| From | To |
|---|---|
| `/cockpit` | `/dashboard` |
| `/api/v1/cockpit` | `/api/v1/dashboard` |
| `CockpitStore`, `cockpit.store.ts`, `cockpit.ts`, `api_v1/cockpit.py` | `Dashboard*`, `dashboard.*` |
| `/universe` | `/watchlist` |
| `/api/v1/universe` | `/api/v1/watchlist` |
| `UniverseStore`, `universe.store.ts`, `universe.ts`, `api_v1/universe.py` | `Watchlist*`, `watchlist.*` |

`/cockpit` and `/universe` keep a client-side redirect to their new paths, so an
existing bookmark or an open tab does not 404. The old `/api/v1/` paths are
**not** aliased — the API has exactly one consumer, shipped from the same build.

**`SCAN_UNIVERSE` keeps its name.** It is a bot config key naming which tickers
get scanned, it is not the UI's word, and renaming it would touch `.env` on a
deployed server for no benefit. The spec notes the collision so a future reader
does not "fix" it: *watchlist* is the UI workspace and the bot's
`!watchlist`-managed ticker list; *universe* survives only as the name of the
scan-breadth setting.

There is one name collision worth stating: `swingbot/admin/dashboard.py` already
exists and is Jinja's dashboard module. The new API module is
`swingbot/admin/api_v1/dashboard.py`, a different package — no clash, but the
two must not be confused when the parity audit reads either one.

---

# Decision 8 — Shell, navigation and identity

## Sidebar

- **Expanded 200px**, **icon rail 52px**. Toggle button at the sidebar foot.
- State persisted in `PreferencesStore` (`shell.sidebar` = `expanded` | `rail`).
- **Auto-collapses to the rail below 1024px**, and becomes an **overlay** below
  640px (hamburger in the top bar, backdrop, closes on navigate). The user's
  explicit toggle wins within a breakpoint; crossing a breakpoint re-applies the
  automatic state.
- Railed entries show the icon only, with the label as a tooltip on hover and as
  `aria-label` always.

## Icons

Ten hand-authored inline SVGs — six nav entries, sidebar toggle, profile,
sign-out, hamburger — in a single sprite component. **Zero CDN**, per the
migration's standing constraint: no icon font, no external package, no runtime
network request. Stroke-based, 16px grid, `currentColor` so they inherit the
active/inactive nav colour.

## Identity

The artwork already exists at `swingbot/admin/static/images/`. It moves to
`frontend/public/` so the SPA build ships it, and appears in four places:

1. **Browser tab** — `favicon.svg` primary, `favicon.png` and `favicon.ico`
   fallbacks, `apple-touch-icon.png` for a phone home screen.
2. **Sidebar brand mark** — beside "swingbot", shrinking to the avatar alone on
   the rail.
3. **Login card** — above the form, as `login.html` had it.
4. **Profile menu** — a clickable avatar in the top bar opening a small menu.
   It absorbs the current "Sign out" button, which leaves the sidebar.

`swingbot/admin/static/images/` keeps its copies while Jinja lives. The two
directories are the same bytes; the duplication ends when Jinja is deleted.

---

# Decision 9 — Responsive

Four breakpoints: **640 / 1024 / 1440 / 1920**.

| Range | Sidebar | Panels | Tables | Padding |
|---|---|---|---|---|
| `< 640` phone | overlay | 1 column | **stacked cards** | 10px |
| `640–1023` | rail | 1 column | horizontal scroll in-container | 14px |
| `1024–1439` | rail | 2 columns | horizontal scroll in-container | 14px |
| `1440–1919` | expanded | 3 columns | fits | 20px |
| `≥ 1920` | expanded | 4 columns | fits, content max-width 1760px | 20px |

## The phone table

Below 640px a data table renders as **one card per row** using the compact
column set: ticker and direction as the card heading, the status bar full-width
beneath it, and the remaining compact columns as label/value pairs in a
two-column grid. Row actions become full-width buttons at the card foot.

This is a rendering mode of `DataTableComponent`, not a second component —
same column definitions, same sort, same pagination, different layout. A
separate mobile table would drift from the desktop one within two changes.

## "Remove redundant spaces"

Workspace padding drops from a flat 20px to 14px below 1440px; panel headers
lose their extra top margin; the toolbar row and the table header merge into one
band; `--space-28` is removed from the scale as unused at any breakpoint. These
are token and layout-shell changes, not per-component ones.

## No horizontal document scroll, ever

At every breakpoint the document body must not scroll horizontally. Wide content
scrolls inside its own `overflow-x: auto` container. This was already found once
in NG54 (the Trades table at 24 columns scrolled the page) and is the single
easiest regression to reintroduce while adding breakpoints.

---

# Decision 10 — The trade chart

**One interactive chart carrying everything the PNG draws.** Not a PNG in the UI,
not a PNG beside a chart — the interactive chart gains the PNG's information.

## Server-computed geometry

New endpoint:

```
GET /api/v1/market/chart/<trade_id>?window=<bars>
```

returning:

```
ohlcv        [{t, o, h, l, c, v}]
indicators   { macd: {line, signal, hist}, rsi: [], kc: {upper, lower} }
volume_profile [{price, volume}]
levels       { entry, stop, target1, target2, working_stop }
overlay      { side: "target"|"stop", shape: <typed geometry> } | null
currency     string
```

`shape` is a discriminated union mirroring what `chart_strategy_overlay.py`
already draws:

| `kind` | Payload |
|---|---|
| `trendline` | `{ p1: [t, price], p2: [t, price], pivots: [[t, price], …] }` |
| `fib_fan` | `{ origin: [t, price], anchor: [t, price], ratios: [] }` |
| `fvg_zone` | `{ t_from, t_to, price_low, price_high }` |
| `curve` | `{ label, points: [[t, price], …] }` |
| `horizontal` | `{ price, t_from, t_to, label }` |

**Every number in that payload is computed by the same Python that draws the
PNG.** The geometry is extracted out of `chart_strategy_overlay.py` into a
serialisable form that both the matplotlib renderer and this endpoint consume;
the renderer is refactored to call it, not duplicated. This is the whole point
of choosing a server-computed endpoint: the chart in the browser and the image
in Discord cannot disagree about where a Fibonacci level sits, and the
repo's NO-LOOKAHEAD rule keeps exactly one home.

## Client rendering

`lightweight-charts` 5.2.1, which supports multiple panes natively.

- **Pane 0** — candlesticks, volume histogram overlaid, Keltner bands, the
  volume-profile histogram along the left edge, plan levels as price lines with
  TradingView-style right-axis tags, risk (entry→stop) and reward
  (entry→target) shaded, and the strategy overlay.
- **Pane 1** — MACD line, signal and histogram, zero line.
- **Pane 2** — RSI with 70 / 50 / 30 reference lines.

The four shape kinds and the risk/reward shading are drawn as **custom series
primitives** (the v5 plugin API) — lightweight-charts has no native shape
support, and this is the part of the phase carrying real unknowns. The plan
sequences the primitives after a scaffold task that proves one primitive draws
correctly, so the risk surfaces on task one rather than task four.

## Degraded states

| Condition | Renders |
|---|---|
| Endpoint fails | empty state naming the reason, with a retry — never a blank pane |
| `overlay: null` (older trade, no `target_sources`) | candles, indicators and plan lines only |
| Insufficient history for an indicator | that pane is omitted, not drawn empty |

The last two mirror what the PNG generator already does, so a trade that renders
without an overlay in Discord renders without one here for the same reason.

## The PNG is untouched

`generate_trade_chart` keeps working and the bot keeps posting images to Discord.
The only change to that code path is the geometry extraction described above,
which is a refactor with identical output. The deleted `GET /trades/<id>/chart.png`
admin route stays deleted — nothing needs it now.

---

# Decision 11 — Feature parity with the Jinja UI

The migration audited **routes**. This audits **features**.

## Method

Walk all 19 templates in `swingbot/admin/templates/`. For each, enumerate every
control, column, tooltip, chart, computed number and empty state, and classify:

- **migrated** — present in the SPA, with where
- **dropped on purpose** — with the decision that dropped it
- **missing** — no SPA equivalent and no decision to drop it

The output is one gap table committed to
`docs/superpowers/results/2026-08-13-jinja-feature-parity.md`. Every row marked
*missing* becomes either a fill task in this plan or a line in the "dropped, and
here is why" section — nothing stays unclassified.

## Why a table and not a list of fixes

Because "all the important features" is not a set anyone currently knows. Ten
items were named from memory; the audit exists to find the rest, and to make
"done" mean something checkable rather than "nothing else has been noticed yet".

## Parallelism

Templates batch into roughly five groups by workspace (dashboard/plans ·
trades/journal/detail · stats/strategies/calibration · risk/tuning · settings/
logs/watchlist). Each batch is one audit task, and they are independent.

---

# Decision 12 — Testing and verification

## Automated

**Vitest** — every piece of logic that can carry a test:

- column sets per mode; the picker's per-mode persistence; reorder read
  tolerating unknown and missing keys
- plan-cell formatting for LONG **and** SHORT, and with a null target or stop
- status-cell maths at the edges: price beyond the target, beyond the stop, no
  live price, PENDING, CLOSED
- responsive mode selection (card vs table) at each breakpoint boundary
- chart geometry mapping — each of the five `shape` kinds to its primitive

**pytest** — the API additions: the new `TradeRow` fields including their null
cases, the chart-data endpoint's payload shape and its degraded responses, and
the renamed route paths. Full suite green (`0 failed`) before each commit, per
repo convention.

## Manual

A written QA checklist per phase, walked at **390 / 768 / 1280 / 1920**, covering
every workspace, the sidebar in both states, both table modes, and the chart's
four layers. The checklist is part of the phase's final task, in the same form
NG54's acceptance gate used — a numbered walk with a recorded result, not "looks
fine".

Automated screenshot testing was considered and declined: the value is in
catching regressions over time, and this is a one-off overhaul.

---

# Decision 13 — Jinja stays until this lands

NG57 (delete the Jinja UI) is **deferred** until this plan completes. The
migration plan scheduled it for no earlier than 2026-08-27; this spec moves the
gate from a date to an event.

Reasoning: the parity audit reads the templates, and the status bar, density
model and plan cell are being ported *from* them. Deleting the reference
halfway through the port is how details get lost. Jinja costs nothing to leave
in place — it is behind `ADMIN_UI=jinja`, it is not the default, and it is the
rollback path if any phase of this work goes wrong on the live server.

The migration plan's Progress block is updated to say so, so a session resuming
NG56 does not find a date that has passed and proceed.

---

## Definition of done

- [ ] Both tables render compact by default with the specified column sets, the
      combined plan cell, ▲/▼ direction and `Lv4 · 78` confidence.
- [ ] Picker, drag-reorder, per-page and pinned row actions all work and persist
      per table and per mode.
- [ ] The status cell shows dot, bar and percentage for live positions and
      degrades correctly for the four other states, driven by server fields.
- [ ] `tokens.css` carries the new palette and the three-step motion scale;
      no component contains a hex literal.
- [ ] `/dashboard` and `/watchlist` are the routes, the API paths, the store
      names and the filenames; `/cockpit` and `/universe` redirect.
- [ ] The sidebar collapses to an icon rail, persists, auto-collapses below
      1024px and overlays below 640px.
- [ ] The avatar appears in the tab, the sidebar, the login card and the profile
      menu.
- [ ] No horizontal document scroll at 390, 768, 1280 or 1920, on any workspace.
- [ ] The trade chart draws candles, volume, MACD, RSI, Keltner, volume profile,
      all plan levels with axis tags, risk/reward shading and the confirmed
      strategy overlay — from one server endpoint.
- [ ] The parity gap table is committed and every row is classified.
- [ ] Full pytest suite green; Vitest green; the four QA checklists walked and
      recorded.

## Explicitly out of scope

- **A light theme.** Dark only, still.
- **Colour-blind-safe palette work.** Declined, on the record, single user.
- **Automated screenshot/visual-regression testing.** Declined above.
- **Renaming `SCAN_UNIVERSE`.** Bot config, not UI vocabulary.
- **Restoring the PNG chart routes.** The interactive chart replaces them; the
  PNG remains Discord-only.
- **Changing the bot process.** Same constraint the migration plan carried: the
  only Python touched is `swingbot/admin/` plus the chart-geometry extraction,
  which is a refactor with identical output.
- **Deleting Jinja.** That is NG57, deferred, and it is that plan's task.

## Risks

| Risk | Mitigation |
|---|---|
| **Custom chart primitives are harder than assumed.** lightweight-charts' plugin API is the least-travelled part of this design. | The phase opens with a scaffold task that draws one primitive end-to-end. If that task reveals the API cannot express these shapes, the phase stops and the fallback — a canvas overlay layer synchronised to the chart's coordinate system — is decided then, not after four tasks have been built on a bad assumption. |
| **The geometry extraction changes PNG output.** It is a refactor of code the bot depends on. | The extraction task's acceptance is byte-identical PNG output for a fixed set of fixture trades, checked before and after. |
| **Phone support is larger than one phase.** Six workspaces, each with its own layout. | Per-workspace responsive passes are separate parallel tasks; if the phase overruns, the workspaces that matter on a phone (Dashboard, Trades, trade detail) are sequenced first and the rest can land in a follow-up without blocking the merge. |
| **The re-palette misses a hex literal.** Components written before the token discipline may hardcode colours. | A grep-based task enumerates every hex literal in `frontend/src` and either tokenises it or records why it is exempt. Fails the phase if any remain unclassified. |
| **Parallel agents collide despite `Owns:`.** | The renames are serialised in P0, and the plan's phase-boundary merges give a clean base for each fan-out. Any task whose `Owns:` overlaps another in the same phase is marked serial explicitly. |
| **Preference schema change orphans stored values.** | Every read tolerates absence and unknown keys at every level and falls back to the baseline. A stale preference degrades to the default; it never hides a column or breaks a render. |

## Open questions

None. Everything above was decided during the design conversation; where a
decision reverses an earlier spec, the reversal is recorded in place rather than
left as a contradiction between two live documents.
