# SPA refresh — QA walk

Plan `2026-08-13-v21-spa-refresh.md`. One section per phase, walked against a
running SPA on the built bundle, not against `ng serve` — the bundle is what
deploys, and NG54 already cost a release to that distinction.

Fixtures come from `scripts/seed_parity_fixtures.py`, in the worktree's own
`data/`.

---

## Phase 1 — Tables (SR7–SR18)

Walked 2026-08-13. Server on the real bundle, Chromium at 1440×900.

### Both tables, both modes

| Line | Result |
|---|---|
| Trades renders the compact set, in order | **PASS** — `# status ticker confidence direction now plan pnl r opened closed` |
| Trades renders the full set | **PASS** — adds `R:R strategy horizon held realised` |
| Density toggle switches between them | **PASS**, and back again |
| Dashboard renders the same definitions | **PASS** — same headers, its own table id |
| Dashboard has no per-page control | **PASS** — deliberate; the panel is capped and its filter is fixed |

### The cells

| Line | Result |
|---|---|
| Plan cell on a long | **PASS** — `101.00 → 110.00 / 95.00`, target green, stop red |
| Plan cell on a short | **PASS** — same order, target is the lower number, colours carry the roles |
| Direction arrow | **PASS** — ▲/▼ with `aria-label` "Long (bullish)" / "Short (bearish)" |
| Confidence | **PASS** — `Lv4 · 81`; separator absent when the score is |
| Status bar near TP | **PASS** — 85%, band `toward_target`, "Near target" |
| Status bar near SL | **PASS** — 15%, band `toward_stop`, "Near stop-loss" |
| Status bar at entry | **PASS** — 50%, band `neutral`, "Near entry" |
| Status bar with no price | **PASS** — chip plus "no price" |
| PENDING | **PASS** — chip alone, no bar |
| CLOSED | **PASS** — chip alone |

**The spectrum needed new fixtures.** The original set prices plans at ~101
against real quotes near 493, so every live bar clamped to 100% and the walk
showed four identical full bars. `_spectrum_plans()` now derives stop and
target *from the live price* so a position lands at a chosen point on its own
span. First attempt placed them symmetrically and moved the entry instead,
which varied only the band and left three identical half-bars — the levels have
to be asymmetric for the bar length itself to differ.

### Interaction

| Line | Result |
|---|---|
| Picker independence across modes | **PASS** — arranging Full left Compact untouched |
| Drag-reorder by mouse | **PASS** |
| Reorder by keyboard | **PASS** — Left/Right on a focused header |
| Pinned column immovable | **PASS** — actions neither drags nor accepts a drop |
| Per-page 10 / 25 / 50 / All | **PASS** — 10 → 10 rows, All → all 40 |
| Selector survives choosing All | **PASS** — it is outside the pager, so it does not delete itself |
| Preferences survive a reload | **PASS**, after two defects below |
| Console clean | **PASS** — no errors, no 4xx |

### Defects found and fixed

**1. Per-page changed nothing.** The selector wrote the preference and the
query kept sending `DEFAULT_PER_PAGE` — a constant, so the effect had nothing
to re-run on. Choosing "All" saved "All" and returned 25 rows forever. Fixed by
reading the signal in the query.

**2. Saved preferences were written and then ignored.** Every workspace seeded
its density, columns and page size synchronously in a field initialiser, but
`PreferencesStore.load()` is async — so on a cold load those reads got `{}` and
everyone saw the defaults. The write path worked perfectly, which is what makes
this hard to notice: the server had the right values the whole time. Fixed with
an effect that applies stored preferences once `isLoaded()` flips.

**3. The per-page control disagreed with the table.** `[value]` on a `<select>`
is applied before `@for` has created any options, so it matched nothing and the
control fell back to its first entry — it read "10" while the table was paging
by 50. Moved to `[selected]` on the option.

All three are pinned by tests. Each is the same shape: a control that looked
right and did nothing, or did something and looked wrong.

### Not walked

- **A second browser.** Preferences are server-side, so a reload in one browser
  exercises the same path a second browser would; a genuinely concurrent check
  belongs with the multi-session work, not here.

---

## Phase 2 — Shell and responsive (SR20–SR31)

Walked 2026-08-13, same server and bundle.

### Every workspace at four widths

`document.documentElement.scrollWidth` vs `window.innerWidth`, measured rather
than eyeballed. Twenty combinations, every one equal:

| | 390 | 768 | 1280 | 1920 |
|---|---|---|---|---|
| Dashboard | 390 | 768 | 1280 | 1920 |
| Trades | 390 | 768 | 1280 | 1920 |
| Analytics | 390 | 768 | 1280 | 1920 |
| Watchlist | 390 | 768 | 1280 | 1920 |
| System | 390 | 768 | 1280 | 1920 |

**PASS** — no horizontal document scroll anywhere. Cards render only at 390
(Trades 25, Watchlist 7, Analytics 5); the tables return above it.

### The sidebar

| Line | Result |
|---|---|
| Expanded is 200px, rail is 52px | **PASS** — measured |
| Toggle flips it | **PASS**, after the defect below |
| Toggle persists through a reload | **PASS** |
| Labels survive the collapse | **PASS** — clipped to 1px, text still in the DOM, `aria-label` intact |
| 1024 forces the rail, descending | **PASS** — 1024 expanded, 1023 railed |
| 1024 restores it, ascending | **PASS** — with no stored preference |
| 640 switches to overlay | **PASS** — 640 no overlay, 639 overlay |
| A navigation closes the overlay | **PASS** |
| Scrim dismisses it | **PASS** |

### The profile menu

| Line | Result |
|---|---|
| Opens on the avatar | **PASS** |
| Opens by keyboard | **PASS** — focus the trigger, Enter |
| Escape closes | **PASS** |
| Outside click closes | **PASS** |
| A click inside does not close it | **PASS** |
| Focus returns to the trigger | **PASS** |
| The sidebar's own Sign out is gone | **PASS** |

### The avatar

Sidebar mark, profile trigger (with a 2× `srcset`), and the favicon set —
**PASS**. Not on the login card: that card is Jinja and NG57 deletes it, so an
avatar there would be added only to be removed.

### Defect found and fixed

**The sidebar toggle did nothing.** The handler computed the new state and
then wrote its own inverse, so the two cancelled and the class never changed.
The composition rule the unit tests check was correct the whole time — the
handler feeding it was not, which is exactly the gap a walk exists to cover.

### An ambiguity, resolved and recorded

SR21's prose says crossing a breakpoint "re-applies the automatic state",
which read strictly would discard a user's explicit collapse the moment they
resized. Its own step 1 test list says only that crossing below 1024 "forces
the rail regardless of the stored value" — and says nothing about ascending.
The implementation follows the test list: below `md` the rail is forced; above
it the stored preference applies if there is one, and the automatic state if
there is not. Both readings agree on everything the checklist actually names;
they differ only for a user who collapsed deliberately and then resized, and
silently discarding that choice is the worse of the two.

---

## Phase 3 — The chart (SR32–SR40)

Walked 2026-08-13.

### How it was walked

Step 4 asks for each fixture's interactive chart beside its generated PNG.
SR32's fixtures are synthetic frames rather than real positions — the trades
`scripts/seed_parity_fixtures.py` seeds for Phases 1 and 2 are not those
fixtures, and only those fixtures have a PNG to compare against. So the two
sides were produced like this:

- **PNG:** `python scripts/render_chart_fixtures.py --out /tmp/chart-png` — the
  same 10 fixtures SR32 baselined.
- **Browser:** `python scripts/dump_chart_payloads.py` drives the **actual**
  `/api/v1/market/chart` Flask route with `_ohlcv_frame` and `_trade_for_levels`
  patched to the fixture (the two seams `tests/admin/test_api_v1_market.py`
  already uses), and `frontend/chart-harness/` draws that payload with the real
  chart modules in Chromium via Playwright.

The harness is kept (`frontend/chart-harness/README.md`). What it does **not**
cover: `TradeChart` itself, the store and the tab chrome, since bundling an
Angular component needs the Angular compiler — those are covered by `ng build`
and the unit tests.

### Findings — three defects, all fixed

**1. The plan's targets were drawn off the top of the pane.** `curve_ema` has
entry 124.88, TP1 134.88, TP2 142.37 over candles topping out at 125. The PNG's
axis spans 117–144 and shows all four levels; the browser's stopped at 128 and
showed two. Price lines take no part in the library's autoscale — the same trap
SR37 had already hit with the RSI thresholds and solved with
`autoscaleInfoProvider`. The price pane now uses `paneAutoscale` with
`planLevelPrices`, and the two axes agree. **This is the defect the walk exists
to catch**: every unit test passed, both renderers had the right number, and
one of them was drawing it where nobody could see it.

**2. Fibonacci was drawn as a diagonal fan, not as levels.** SR39 step 1 says
"one ray per ratio from the shared origin", and that is what was built. The PNG
draws each ratio as a **horizontal** line at the price the server computed —
61.8% at 120.10 across the frame. A ray is at that price at exactly one x.
Spec Decision 10 cites this exact case ("cannot disagree about where a
Fibonacci level sits"), so the spec beats the plan's wording: ratios are now
horizontal segments spanning the swing, the matched one solid and bolder, with
a diamond at each of the two swing anchors as the PNG marks them.

**3. A pivot marker was invisible.** The overlay colour is fixed per side, so a
`--pos` diamond regularly lands on an up candle — same hue, four pixels, gone.
Markers are now 5px with a `--surface` outline, which reads on either candle
colour.

Two of the three came from putting the images side by side. None of them would
have failed a unit test, and two of them looked completely fine in isolation.

### Fixture-by-fixture

| Fixture | Overlay | Verdict |
|---|---|---|
| `curve_ema` | curve (EMA20) | Levels, bands, curve, Keltner, profile, both panes all match after fix 1. |
| `fib_fan` | fib_fan (Fib 61.8%) | Matches after fix 2; solid 61.8% sits on the PNG's 120.10. |
| `fvg_zone` | fvg_zone (FVG bullish) | Box spans the gap's prices from the pattern's third candle to the right edge, as the PNG draws it. |
| `marker_pivot` | marker (Pivot low) | Matches after fix 3; diamond sits on the trough. |
| `horizontal_rolling` | horizontal | Same polyline path as fix 2's levels; bounded to its lookback. |
| `horizontal_hvn` | horizontal | As above, `full_width` spans supplied by the geometry. |
| `secondary_sources` | fvg_zone | Primary source resolves to the FVG, as the endpoint reports. |
| `trendline` | **none** | Known gap — see below. |
| `secondary_bollinger` | **none** | Known gap. |
| `no_drawable_source` | **none** | Correct: no drawable source on either side, and the PNG's fallback is a trendline. |

### Known parity gap: trendlines

Three fixtures draw a trendline in the PNG and nothing in the browser. This is
deliberate and predates the walk: `generate_trade_chart` fits the pair *before*
the display window is chosen (the window is then widened to fit the line's own
touches), so `overlay_geometry` takes a `trend_info` and returns `None` without
one — and `/market/chart` does not fit trendlines. SR32 and SR33 both record
this. `strategy-overlay.ts` handles the `trendline` shape and is tested, so the
client is ready if the endpoint ever supplies one; closing the gap means
deciding where the fit happens, which is a plan-level decision and not SR40's.

### Not checked here

- **The Chart tab in the running admin, against a real trade.** This is the one
  gap that matters: it is the only thing that exercises `TradeChart`'s own
  wiring, `ChartStore`, and the tab chrome together. It is not blocked — seed
  with `scripts/seed_parity_fixtures.py` and serve the built bundle, the way
  Phases 1 and 2 were walked — it simply was not done here.
- Degraded states in the browser. The retry, the `overlay: null` path and the
  omitted-pane path are unit-tested (`chart-container.spec.ts`,
  `strategy-overlay.spec.ts`, `indicator-panes.spec.ts`) but were not walked.
- A lone `marker` still has no label. SR39 deferred canvas text to the tab's
  caption, which prints `overlay.source` — legible in the Chart tab, absent in
  this harness.

### Suite state at the end of the walk

- `python scripts/testrun.py full` → **1738 passed, 136 skipped, 1 xfailed, 0 failed**
- `ng test` → **36 files, 571 passed**
- `ng build` → clean

---

## Phase 4 — Parity and the gap fill (SR41–SR64)

**NOT WALKED. This section records that, rather than recording a pass.**

Phases 1–3 above were walked against a running SPA on the built bundle.
Phase 4 was implemented across SR41–SR64 in an agent session on 2026-08-14
with no browser available, so **SR64 Step 3's end-to-end walk at four widths
did not happen** and nothing below should be read as if it had.

Writing "PASS" here from unit tests would be the specific failure this
document exists to prevent — NG54 already cost a release to the difference
between "the tests pass" and "the bundle works".

### What IS verified, and by what

| Evidence | Result |
|---|---|
| `python scripts/testrun.py full` | **1826 passed, 136 skipped, 1 xfailed, 0 failed** |
| `npx ng test` | **701 passed, 42 files** |
| `npx tsc --noEmit` | clean |
| `npx ng build` | clean, initial total 328.16 kB / 88.29 kB transferred |

Every SR41–SR63 task landed with tests at the layer it changed: server
contract tests for the new endpoints and their shapes (SR54, SR55, SR58),
store tests for the client wiring (SR54–SR58), and pure-function tests for
the derived metrics (SR54). Those cover behaviour. They do not cover layout,
overflow, focus order, or how any of it looks at 390px.

### What a walk still has to check

The copy tasks (SR59–SR63) added visible text to six workspaces and were
verified only by compilation. Specifically unwalked:

- **Every `section-help` paragraph added by SR59–SR63.** A defect found while
  closing SR64: `.section-help` was defined in exactly ONE component's styles
  while the copy tasks used the class in six workspaces, so most of that new
  text was rendering as an unstyled `<p>`. It is a global rule now
  (`styles.css`), but "it has a rule" is not "it looks right".
- **The analytics glossary** (`<details>`), the settings **default-value
  badges** and **field-count badges**, and the **log level colouring** — all
  new visual elements, none seen.
- **Log scroll-to-bottom**, which depends on real scroll geometry and cannot
  be exercised in jsdom.
- **The dashboard scope toggle and analytics date range** at narrow widths;
  both are new control rows in headers that were previously tight.
- All four widths, for everything in this phase.

### Consequence for NG57

The migration plan's second gate (v21 completing) is released. **The soak
gate and this walk are not.** NG57 deletes the Jinja templates, and the
argument that nothing is lost rests on the parity audit plus this phase
having actually been *seen* to work. One of those two is still outstanding.
