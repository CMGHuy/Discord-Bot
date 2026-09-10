# v80 — Terminal foundation: TradingView Blue tokens and the canonical component set

**Version:** ui 1.12.0 · bot 1.6.3
**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Depends on:** v77's code merged to `main` (it adds the `danger-icon` variant to `ui/button.ts`, which D4 redesigns). Check: `git merge-base --is-ancestor 24688ff4 main`.

The first of three specs (see "Follow-on specs"). It changes tokens, shared
components and the Discord chart palette. It changes **no workspace code**:
every screen picks up the new look through tokens, and nothing breaks.

## Why this exists

A trader-reported problem, 2026-09-10: screens are inconsistent, hard to scan,
look flat, and the phone view is poor. Both complaints were measured the same
day, not assumed (below). This is `Edge: none (integrity)`: under CLAUDE.md's
ranking it sits behind v79 (expectancy). It shares no file with v79, so the two
may run in parallel worktrees.

The version bump is argued from observable difference. Changing tokens alone
makes every admin screen look different (`ui minor`) and every Discord alert
chart image look different (`bot minor`), before any screen is migrated.

## Decisions taken in the brainstorm (human partner, 2026-09-10)

- **Consistency covers every family:** buttons and form controls, tables,
  panels and headings, chips, badges and status.
- **Design a new canonical set** rather than converge on existing variants;
  the "feels flat" refresh is part of it.
- **Pro-terminal direction C, "TradingView Blue"**, picked from side-by-side
  mockups (private artifact:
  https://claude.ai/code/artifact/5069719a-3226-4b27-8f33-c10e33173801).
- **Two densities stay** (presentation / instrument registers, v54 D1).
- **Every screen first-class on a phone.**
- **Discord charts adopt the same palette.**
- **Three specs:** this Foundation, then Migration, then Phone screens.
- **Table cells keep today's content conventions** (spec review): see D4's
  "Table cell contracts".

## Measured starting point (2026-09-10)

| Finding | Value |
|---|---|
| Headline-number treatments | 4 (cards, chips, a mix, Risk's hand-built 25px/700 figure) |
| Segmented toggles | 6 hand-built, plus `sb-filter-chips` (2 uses) and `segment`/`chip` button variants (9) |
| `sb-metric-card` / `sb-metric-chip` call sites | 10 / 17 |
| Empty-state styles | 4; three screens print them in `--text-faint`, which is divider-only |
| Hand-built uppercase labels / help-text styles | 11 files, 4 letter-spacings / 4 styles |
| Panel-grid minimum widths | 6 (140–300px) |
| Screens using the shared filter bar | 1 of 10 |
| Touch targets | controls 28px, chips ~22px, pager ~23px, phone menu button ~24px; no `pointer: coarse` rule |
| Phone tables | automatic card mode on every table, with no sort control |
| Tab bar at 390px | Analytics clips "Tuning" and "Plans" with no way to reach them |
| Hover-only `title` tooltips | 35 across 19 files |
| P&L cell | the same `% (amount)` template copied in Trades and Dashboard; Ticker detail shows % only |

Already clean, and kept that way: no raw `<button>` outside `ui/`, one raw
control (`settings-tab.ts:344`), one computed colour literal (`versions.ts:383`).

## Non-goals

- **No workspace edits.** Migration moves call sites and deletes superseded
  components. Foundation adds and restyles, and every existing API keeps working.
- **No per-screen phone layouts** (Calendar's 7 columns, Analytics charts, fixed
  chart heights, settings diffs). Those belong to Phone screens.
- **No light theme, no new font files, no screenshot-test toolchain.**
- **No chart behaviour change.** Colours and chrome only; geometry tests stay green.

---

## D1 — Colour tokens

Every value below is in `frontend/src/styles/tokens.css`. This deliberately
reopens v54's "no token churn" non-goal: choosing a new direction is what this
spec is for.

| Token | Today | New | Note |
|---|---|---|---|
| `--bg` | `#0a0b10` | `#0c0f16` | |
| `--surface` | `#10121a` | `#131722` | TradingView's chart pane |
| `--surface-raised` | `#171a25` | `#1c212d` | |
| `--surface-overlay` | `#1e2230` | `#242936` | menus, drawers, dialogs |
| `--overlay-dim` | `rgba(10,11,16,.72)` | `rgba(12,15,22,.72)` | |
| `--border` | `#232838` | `#2a2e39` | hairline |
| `--border-strong` | `#333a4f` | `#363a45` | |
| `--text` | `#e9ebf5` | `#d9dce4` | ≥10.59:1 on every surface |
| `--text-secondary` | `#9ba3bd` | `#9ea2ad` | ≥5.69:1 |
| `--text-muted` | `#878ea4` | `#9195a0` | ≥4.85:1 (worst: overlay) |
| `--text-faint` | `#464d63` | `#4e5361` | divider only, 2.33:1 on surface |
| `--accent` | `#7b5cfa` | `#5593ff` | text and active states, ≥4.85:1 |
| `--accent-fill` *(new)* | — | `#2962ff` | filled buttons |
| `--on-accent` *(new)* | — | `#ffffff` | 4.90:1 on `--accent-fill` |
| `--accent-soft` | `rgba(123,92,250,.12)` | `rgba(41,98,255,.18)` | selected-segment ground |
| `--info` | `#46c2ff` | `#b39ddb` | moved off the accent's blue |
| `--info-soft` | `rgba(70,194,255,.12)` | `rgba(179,157,219,.14)` | |
| `--pos` / `--neg` / `--warn` | `#17c98e` / `#ff5470` / `#ffb43d` | unchanged | ≥4.67:1 as text |
| `--quality-1..5` | aliases + `#9acd32` | unchanged | level 3 follows `--text-secondary` |

The valence law is unchanged: one hue, one meaning. The only meaning that moves
is info, because under C the accent took its blue.

## D2 — Chart series namespace

`--chart-1..8` becomes **`--chart-1..6`**, validated against `--surface`
`#131722` with the dataviz palette validator (OKLCH L 0.48–0.67, chroma ≥ 0.10,
adjacent CVD ΔE ≥ 8, normal-vision ΔE ≥ 15, contrast ≥ 3:1):

`#4c8dff` · `#c97a22` · `#a868e0` · `#b08c14` · `#1a9db3` · `#7076e8`

Worst adjacent pair: CVD 11.6, normal 15.9. Every series is ≥ 15.6
normal-vision ΔE from both `--pos` and `--neg`. **Every ΔE in this spec is
OKLab distance ×100**, the validator's metric.

- **No longer pinned to accent / info / warn.** C's lavender info fails the
  chroma floor and sits 14.9 from the blue accent. Amber fails the lightness
  band. Series and semantic colour are separate namespaces, as `tokens.css`
  already argues. They now also have separate values.
- **Six, not eight.** Eight hues that avoid both the gain-green and loss-red
  families inside this band do not validate. A seventh series folds into
  "Other" (`ui/line-chart.ts` `SERIES` becomes length 6).
- **One colour-difference metric for every gate.** `chart-palette.spec.ts`
  computes CIE76 today, under which the old pink resistance line (`#ec407a`)
  sits 15.4 from loss and passes, although it reads as a loss (5.9 in OKLab).
  Both the admin gate and D5's Python gate therefore use OKLab ×100, with the
  thresholds unchanged.
- Two candidates were rejected, and the reason is recorded so nobody reintroduces
  them: a pink series (10.8 from loss) and an olive one (12.6 from gain). They
  pass a bare ΔE 10 gate but read as loss and gain on a P&L chart.

## D3 — Type, shape, depth, touch

- **Families unchanged.** Inter is for UI text and prose. JetBrains Mono is for
  every number, label, ticker, status and code. Weights stay within what is
  self-hosted: Inter 400/500/600/700 and Mono 400/500/700. Mono 700 is used for
  ticker symbols only.
- **One label style:** `.sb-label` in `styles.css`. Mono, `--text-micro`,
  weight 500, `0.08em`, uppercase, `--text-muted`.
- **One help-text style:** `.sb-help`. `--text-chip`, `--text-secondary`,
  `max-width: 65ch`.
- **Headline figure:** `--text-metric` 25px → **28px**, mono 500, tabular.
  20px below 640px. No other type-scale change.
- **Radii:** `--radius` 4px → **2px**, `--radius-chip` 3px → **2px**.
- **Depth:** panels separate by hairlines, not cards. The one-shadow law
  (overlays only) is unchanged.
- **Touch** (tokens media block `(pointer: coarse), (max-width: 639px)`):
  - `--control-h` 28 → 44px;
  - new `--row-h` 32 → 44px;
  - new `--text-control` 14 → 16px, which stops phones zooming into a focused field.
- **Layout responsiveness is per component, via container queries.** A filter
  bar in a narrow drawer stacks exactly as it does on a phone. Touch sizing stays
  global because it follows the pointer, not the box.
- **Two exceptions, found in planning:** `sb-control-row` and `sb-panel-grid`
  switch at the 640px **viewport** breakpoint. Both sit inside flex and grid
  layouts, where declaring an inline-size container removes their intrinsic
  width and collapses them.

## D4 — The canonical component set

"Restyle" means the API is unchanged. "Deprecated" means it keeps working until
Migration deletes it.

**Buttons and form controls**

| Component | Change | Phone / touch |
|---|---|---|
| `button[sb-button]` | Restyle: primary (`--accent-fill`), secondary (hairline), ghost, danger (loss outline, fills on hover), link, icon, `danger-icon` (v77). `segment` and `chip` variants deprecated. | 44px; icon variants 44×44 |
| `sb-select`, `sb-text-input`, `sb-checkbox` | Restyle to hairlines, `--text-control` | 44px, 16px text |
| **`sb-segmented`** *(new)* | One toggle: options with optional counts, `value` / `valueChange`, arrow keys, roving tabindex, `aria-pressed` | Scrolls horizontally, never clips |
| `sb-filter-chips` | Deprecated in favour of `sb-segmented` | — |
| `sb-filter-bar` | Restyle; shows "N active · X of Y" and Clear when filters are on. `controls.spec.ts` pins the "N active" wording, so it stays. | Stacks to a 2-column grid below 640px (container) |

**Tables**

| Component | Change | Phone / touch |
|---|---|---|
| `sb-data-table` | Restyle: `.sb-label` headers, mono tabular numbers, `--row-h` rows, accent sort arrow | **Card mode is replaced.** Below 640px (container) it keeps the table, pins the first column, scrolls sideways, and renders its own sort select above the table. `cardsAt` becomes a test hook for the pinned mode. |
| `sb-pagination` | Restyle | 44px buttons and inputs |

**Table cell contracts.** Binding on every table, from the human partner's spec
review (2026-09-10). Four of the five are today's conventions, kept against a
mockup that departed from them.

| Cell | Renders | Component |
|---|---|---|
| Direction | **One triangle, nothing else:** ▲ in `--pos` for long, ▼ in `--neg` for short, no "L"/"S" letter. Accessible name "Long (bullish)" / "Short (bearish)". | `sb-direction-arrow`, unchanged |
| Plan | **One column,** `entry → target / stop`, target in `--pos`, stop in `--neg`. A PENDING row shows the trigger with a dashed underline. Default column sets never split it into separate Entry, Stop and Target columns; the column picker may still offer them. | `sb-plan-cell`, unchanged layout |
| P&L | **One cell, both figures:** `+4.20% (+9.80 €)`, coloured by sign, flashing when the value changes, money in the account currency via `money()`. `—` when there is nothing to price; the percentage alone when the amount is unknown (no position size), never `(—)`. | **`sb-pnl-cell`** *(new)*, extracted from the identical templates at `trades.ts:327` and `dashboard.ts:474` |
| Confidence | **Text:** `Lv4 · 78`, the level coloured by `--quality-1..5`, the score in `--text-secondary`. No meter. `Lv4` alone when there is no score. | `sb-confidence-cell`, unchanged |
| Held | **Always includes minutes:** `4d 2h 15m`, `4d 0h 5m`, `3h 0m`, `45m`. Today `held()` omits zero parts ("3h", "4d 15m"). Open rows stay live from `elapsedHours(opened_at, clock)`; the ambient clock ticks every 30s. | `format.ts` `held()` |

**Panels, cards and headings**

| Component | Change | Phone / touch |
|---|---|---|
| `sb-section-head` | Adds a `back` slot (always before the title) and a `status` slot (freshness only: as-of, stale, counts). `actions` is deprecated. | Title wraps; status stays beside it |
| **`sb-figure`**, **`sb-figure-strip`** *(new)* | One headline figure (label, value, unit, tone, decimals, one sub-line) in a hairline-divided strip of up to 4 per row | 2 per row below 640px |
| `sb-metric-card`, `sb-metric-chip` | Deprecated in favour of `sb-figure` | — |
| `sb-panel` | Restyle: hairline, heading uses `.sb-label` | — |
| **`sb-panel-grid`** *(new)* | Two track widths only, `narrow` (220px) and `wide` (320px), replacing six hand-picked ones | One column below the 640px viewport breakpoint |
| `sb-tab-bar` | Restyle; scrolls on overflow with an edge fade | 44px tabs |
| `sb-control-row` | Restyle; `stacked` becomes automatic below the 640px viewport breakpoint | — |
| `sb-drawer` | Restyle; height `100dvh` | Full width |
| `sb-confirm-dialog` | Restyle | — |

**Chips, badges and status**

| Component | Change | Phone / touch |
|---|---|---|
| `sb-chip` | Restyle: good / warn / info / neutral as outline or tint, mono, 2px. Capitals by default through a new `caps` input, which quality chips turn off so `Lv4` never renders as `LV4`. | 28px min-height |
| **`sb-status`** *(new)* | Trade status whose marker **shape** carries state: pending outline, active filled, partial half-filled, closed muted. Label in text tokens, never colour alone. | — |
| `sb-confidence-cell`, `sb-quality-chip` | Restyle only; content per "Table cell contracts" | — |
| `sb-empty-state` | Restyle: dashed hairline box; optional `reason` input ("Result: 0" / "Awaiting data"), matching `sb-async`'s two empties | — |
| **`sb-hint`** *(new)* | Info popover that opens on hover, focus **or tap** and closes on Escape or outside tap. Screens adopt it in Phone screens. | Tap target 44px |

Restyle only, via tokens: `sb-status-cell`, `sb-status-indicator`, `sb-row-link`,
column picker, chart chrome (`chart-theme.ts`). Every component reads the
register variables; none carries its own spacing.

## D5 — Discord charts

`swingbot/core/charts/chart_style.py` adopts D1/D2:

| Constant(s) | Today | New |
|---|---|---|
| `CHART_BG` | `#0a0a0a` | `--surface` `#131722` |
| `GRID_COLOR` / `SPINE_COLOR` | `#1c1c1c` / `#2a2a2a` | `--border` / `--border-strong` |
| `TEXT_COLOR` / `MUTED_TEXT_COLOR` | `#f0f0f0` / `#666666` (3.6:1, failing) | `--text` / `--text-muted` |
| `CHIP_BG` / `CHIP_EDGE` | `#121212` / `#2a2a2a` | `--surface-raised` / `--border-strong` |
| `UP_COLOR`, `TARGET_COLOR` | `#00d26a` | `--pos` `#17c98e` |
| `DOWN_COLOR`, `STOP_COLOR` | `#ff4d4d` | `--neg` `#ff5470` |
| `CURRENT_PRICE_COLOR` | `#ffb020` | `--warn` `#ffb43d` |
| `ENTRY_COLOR` | `#4d9fff` | `--chart-1` `#4c8dff` |

**Overlay roles** (TP2, support and resistance trendlines, AVWAP, strategy
target and stop, MACD and signal, RSI, Keltner, volume profile, path) are
re-derived from the six series under three rules:

1. Roles that can share the price pane get distinct colours.
2. Indicator panes may reuse series.
3. No overlay sits within ΔE 10 of gain or loss. This moves today's pink
   resistance line (`#ec407a`) out of the loss family.

Planning enumerated the co-occurrence: the plan's D5 task carries the role table.
Six series cannot give every price-pane role its own colour, so Keltner bands
take `--text-muted` and volume profile takes `--info`. Both are D1 tokens, which
gate 5 allows. The closest price-pane pair is 10.2 apart, so no role needs a
dash style to stay distinct.

- **Stray literals move into `chart_style.py`:** three hex values in
  `portfolio_charts.py`, one hex and one named colour in `trade_chart.py`, one
  named colour in `analytics_charts.py`, and `edgecolors="white"` at
  `chart_drawing.py:180`.
- **Delete `swingbot/admin/static/tokens.css`.** The page it styled was deleted
  in Release B; it survives as the other side of a sync test.
  `tests/charts/test_chart_theme.py` reads `frontend/src/styles/tokens.css`
  instead, mapping `THEME` keys to the admin token names. Two live files
  follow it:
  - `scripts/dev/testrun.py`'s `ESCALATE_PREFIXES` keeps `swingbot/admin/static/`
    only because of this file (its comment says so). Replace that reason with
    `frontend/src/styles/tokens.css`, or `fast` stops escalating when a token
    edit can break the chart-theme test.
  - `docs/features/features-admin.md:119` still names it the palette source.
- **Embed colours** (`swingbot/core/presentation/tokens.py`): `ACCENT_RAMP[3]`
  and `ACCENT_BLOCKED` follow `--text-secondary`, `#9BA3BD` → `#9EA2AD`.
  The other four already match.

## D6 — The UI gallery is the reference

`workspaces/gallery/gallery.ts` (`/ui`) renders every D4 component in every
variant and state, in both registers, including one table row exercising every
cell contract. A new component is not done until the gallery shows it.

## Acceptance gates

1. **`tokens.spec.ts`:**
   - defines every new token;
   - `--chart-7` and `--chart-8` are absent;
   - the touch block sets `--control-h`, `--row-h` and `--text-control` to 44px / 44px / 16px;
   - `--radius` and `--radius-chip` are 2px.
2. **`contrast.spec.ts`:** every text/surface pair ≥ 4.5:1, now including
   `--accent` as text and `--on-accent` on `--accent-fill`; `--text-faint`
   still documented as non-text. `confidence-cell.spec.ts` pins `--info` to
   `#46c2ff`; it moves to `#b39ddb` with D1.
3. **`chart-palette.spec.ts`:**
   - six series;
   - the chart-1/2/3 pin test removed;
   - its ΔE switched from CIE76 to OKLab ×100, thresholds unchanged (≥ 10 from
     `--pos`/`--neg`, adjacent ≥ 15);
   - the OKLCH band (0.48–0.67) and chroma (≥ 0.10) checks added.
4. **One spec file per new or changed component** (so plan tasks stay
   file-disjoint), covering:
   - `sb-segmented`: keys, counts, pressed state, no clipping;
   - `sb-figure` tones;
   - `sb-status`: shapes plus accessible name;
   - `sb-hint`: hover, focus, tap, Escape;
   - `sb-data-table` below 640px: table not cards, sticky first column, sort select;
   - `sb-tab-bar` overflow scroll;
   - `sb-section-head` slots;
   - `sb-panel-grid` tracks;
   - `sb-chip` `caps` input;
   - `sb-pnl-cell`: percent and amount together, sign colour, `—` when unpriced,
     percentage alone when the amount is unknown;
   - `held()` (`format.spec.ts`): minutes always present, including `3h 0m` and `4d 0h 5m`.
5. **`tests/charts/test_chart_theme.py`:**
   - `THEME` matches the admin tokens;
   - no colour literal in `swingbot/core/charts/` outside `chart_style.py`;
   - every colour constant is a D1 token or a D2 series;
   - none within OKLab ΔE 10 of gain/loss (bar the gain/loss constants themselves).
6. **`tests/presentation/test_tokens.py`:** level 3 and blocked are `#9EA2AD`.
7. **The existing gates stay green unchanged:** `primitives.spec.ts`, `register.spec.ts`,
   `async-coverage.spec.ts`, `numeric.spec.ts`, `elevation.spec.ts`,
   `breakpoints.spec.ts`, `controls.spec.ts`, and every chart geometry test.
8. **Walk it once, in a browser, before reporting done:** `/ui` at 1440px and at
   390px, plus one Discord chart per overlay kind from
   `scripts/dev/render_chart_fixtures.py --out <dir>`. Its hashes change by design,
   so this is a look, not a hash check.
9. **Full suites once, as the plan's last task:** `python scripts/dev/testrun.py full`
   and `cd frontend && npm test`.

## Follow-on specs (recorded here, specified later)

Each gets its own spec and plan when its turn comes. The decisions below were
taken in this brainstorm and bind them. Because both are still to be written
from this document, **this spec stays at the top level of `specs/` at
close-out**; only the plan moves to `implemented/`.

**Migration.**
- **Every workspace moves onto D4.** Trade detail adopts `sb-section-head`; the
  four headline treatments become `sb-figure`; the six toggles become `sb-segmented`.
- **Cell contracts are applied everywhere.** Trades, Dashboard and Ticker detail
  render P&L through `sb-pnl-cell`, so Ticker detail gains the amount. Default
  column sets use the single Plan cell.
- **Deprecated APIs are deleted:** `sb-metric-card`, `sb-metric-chip`,
  `sb-filter-chips`, the `segment`/`chip` variants and the `actions` slot.
  `sb-empty-state`'s `reason` becomes required.
- **The shell gets restyled:** the nav rail shows three-letter mnemonics (TRD,
  RSK, …) beside full names, and the top bar follows D1.
- **Ratchet.** The first task adds bans with commented allowlists of today's
  offenders:
  - hand-built toggles;
  - uppercase or letter-spaced text outside `.sb-label`;
  - local help-text classes;
  - radius literals;
  - grid minimum widths outside `sb-panel-grid`;
  - off-scale `@media` widths (720, 1000);
  - hand-built empty states;
  - hand-built P&L templates;
  - detail views with no register.

  Each workspace task empties its entries; the last asserts every allowlist is empty.

**Phone screens.**
- **Shell on a phone:** a bottom tab bar (Home, Trades, Watch, Risk, More),
  and a top bar that adapts (no longer hiding the killswitch badge under the menu button).
- **Calendar** stops keeping 7 columns below 640px.
- **Analytics:** charts sized to the viewport, and the heatmap gets a pinned label column.
- **Trade and ticker charts** size by viewport height (520px and 380px today).
- **Lifecycle diagram** stays readable (~6px labels today).
- **Two diffs stop clipping:** the proposal and settings diffs.
- **`sb-hint`** replaces the 35 hover-only tooltips.
- **Primary content moves off 11px:** table headers, earnings times, version numbers.

## Parallelisation

- **Sequential first, in this order:**
  1. chart series (D2: the `tokens.css` series block, `line-chart.ts`,
     `chart-palette.spec.ts`);
  2. colour tokens (D1), which must come second or the old chart-1/2/3 pin test
     goes red the moment accent and info change;
  3. type, shape and touch (D3, `tokens.css` and `styles.css`).

  Every component consumes all three.
- **Group A (parallel, after the three token tasks), one task per file:**
  - existing components: `button.ts` (only once v77's code is in `main`),
    `form-controls.ts`, `chip.ts`, `layout.ts`, `data-table.ts`, `pagination.ts`,
    `confidence-cell.ts`, `empty-state.ts`, `section-head.ts`, `filter-bar.ts`,
    `format.ts` (`held()`);
  - new files: `segmented.ts`, `figure.ts`, `panel-grid.ts`, `status.ts`, `hint.ts`,
    `pnl-cell.ts`.

  Each task carries its own spec file, which is why gate 4 is per component.
  `controls.spec.ts` is not edited, so it cannot become a shared file.
- **Group B (parallel with everything frontend):** Discord charts (D5) —
  `chart_style.py`, the five stray modules, `presentation/tokens.py`, the two
  Python test files, deleting `admin/static/tokens.css`, plus
  `scripts/dev/testrun.py`'s escalation prefix and `docs/features/features-admin.md`.
  No frontend file.
- **Sequential last:**
  - the gallery after Group A (it consumes every component);
  - the browser walk, the full-suite task, then release.

## Risks

- **Worse before better.** Tokens change every screen's look on landing, while
  hand-built variants are still in place, so the inconsistency is more visible
  until Migration. Migration is queued directly behind this spec.
- **Thin margins on the overlay surface.** Muted and accent text sit at 4.85:1;
  `contrast.spec.ts` fails the build if a later tweak crosses 4.5.
- **Tight overlay separation on the price pane.** The closest pair is 10.2,
  just over the gate. A new overlay role will likely need a dash style or a pane
  of its own rather than a seventh colour.
- **Unit tests cannot see container queries.** Verified in planning (jsdom
  28.1.0): jsdom ignores rules inside `@container` blocks but keeps the rules
  after them, and Angular's emulated encapsulation scopes `@container`
  selectors normally. Unit tests therefore assert phone behaviour through
  class-based rules; the gate-8 browser walk is the only check of the container
  queries themselves.
- **Discord followers see new chart images** the moment the bot deploys.
- **v77's release reached `main` without its code.** `main` carries
  `release(ui): 1.13.0 -- live tape` and v77's plan in `implemented/`, but none
  of v77's feature commits. Whoever merges v77 hits one conflict, in
  `frontend/src/app/shell/shell.ts`'s `imports:` line. Resolve it to
  `Button, Icon, ProfileMenu, MarketLane, NamesLane,`, keeping `Select` out
  (the text-size fix removed it).
