# v186 — UI foundation refresh: one panel title, divided stat strips, Inter figures, quiet skeletons

**Version:** ui 1.35.0 · bot 2.14.4 (at writing)
**Bump:** ui minor; bot none. New shared primitive (`sb-stat-strip`), new figure tokens and a visible change to every panel and tile.
**Edge:** none (integrity). Presentation only: no data, API, copy or colour value changes.
**Screen:** exempt (integrity)
**Panel:** senior-engineer
**Status:** spec written 2026-10-23 from a brainstorm with the partner, approved in chat section by section; revised the same day after the panel (see `## Panel review`). First of four UI-refresh specs (foundation → shell → toolbars & tables → workspace passes); the other three are not yet written.

## Why

A walk through all 13 workspaces at 1440 and 390 (production, 2026-10-23) found that the token layer (v167 Arctic Navy, v168 motion, v179) is sound, and that the app reads as less professional than it is for four foundation-level reasons:

1. **Three heading voices for one job.** `sb-panel` (147 call sites) renders its heading as `<h2 class="sb-label">` (`ui/layout.ts:41`): monospace caps, letter-spaced (`KILLSWITCH`, `TRADING PERFORMANCE`). `sb-panel-header` (43 call sites, mostly Analytics) renders a 16px bold sans `h2` (`Equity`, `Outcome`). Stat tiles add a third: spaced sans caps. Pages do not look like one product, and titles look the same as field labels, so hierarchy is flat.
2. **Box in box.** Every panel draws a header strip, a border, a gradient and a shadow. Stat tiles nested in it draw their own border and surface (Dashboard performance, Risk metrics, Calendar summary). Calm technical UIs separate siblings with hairlines and space, not nested frames.
3. **Display figures in a code face.** Tile values (`stat-tile.ts` `.value`, `--font-num`, 28px) and `sb-figure` values (`figure.ts` `.value`, `--font-mono` 500) are JetBrains Mono. Mono digits are right for columns; at display size they read wide and blocky. (The Dashboard portfolio figure in `portfolio-value.ts` is already Inter 600 at `--text-title` and is not part of this problem.)
4. **Unreadable secondary text, loud loading.** Tile labels, `N=` and hints use `--text-faint`, which `tokens.css` itself defines as a rule/divider colour "never text that must be read" (~2:1). The loading skeleton is full-height slabs with a sweeping shimmer — the heaviest thing on the Dashboard while it loads.

## Decisions

### D1 — One panel title

Both `sb-panel`'s heading and `sb-panel-header`'s `h2` render:

- **Title:** `--font-sans`, weight 600, `--text-body` (14px), `--text`, sentence case, `letter-spacing: normal`, no `text-transform`. `sb-panel`'s `h2` drops the `sb-label` class and gets these declarations in `layout.ts`'s own styles.
- **Meta** after the title on the same baseline (`N=`, `all-time`, totals, as-of): `--font-num`, `--text-micro`, `--text-muted`. `all-time` keeps `--warn`. A **total** (`sb-panel-header`'s `total`) is a figure and takes the D4 figure face at `--text-chip` in `--text-secondary`.
- `.sb-label` (mono caps) is unchanged and remains the style for **field and tile labels** (`WIN RATE`, `TICKER`, `STRATEGY`). It is no longer used for panel titles.
- Text passed as a heading is not rewritten. The plan's first task greps (a) call-site heading literals in ALL CAPS, changed to sentence case, and (b) every test, e2e and `frontend/scripts/layout-audit*` selector that depends on `h2.sb-label`, `.sb-label` inside `sb-panel`, or a panel title's `text-transform`; each is updated in the same commit as the D1 change.

### D2 — Panel frame: keep the surface, make the header rule conditional

- `--panel-bg` (gradient), `--panel-border`, `--panel-radius` and `--panel-shadow` are **unchanged** (partner decision).
- The header rule is **visible** only when the panel is `flush` **or** has the new boolean input `divided` (`divided` is for a non-flush body that starts with a tab strip or a table-like list). Otherwise the header keeps a `1px solid transparent` bottom border, so the header's `min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px)` (`layout.ts:91`) and the v179 §3.4 one-header-height contract hold for ruled and unruled panels side by side.
- Template: `<header [class.ruled]="flush() || divided()">`; `.body` gets `[class.tight]="!!heading() && !flush() && !divided()"`.
- `.body.tight` has top padding `--space-4` (title → first row = header's `--space-10` + `--space-4`). A panel with no heading keeps the full `--space-14`; a flush body stays `padding: 0`.
- The collapse toggle (`.panel-toggle`, `layout.ts:125`) moves from `--text-faint` to `--text-muted` (it is an interactive glyph, not a rule).

### D3 — `sb-stat-strip`: tiles separated by hairlines

New component `sb-stat-strip` in `frontend/src/app/ui/stat-strip.ts`.

**Layout.** One global class in `styles.css`, `.sb-strip-grid`, owns the column rule so the strip and the D5 `'tiles'` skeleton share it rather than duplicating it:

- default: `grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr))`;
- with `--strip-cols: N` set: N columns from 1024px, `min(N, 3)` from 640–1023px, 2 below 640px (written as three media-query rules reading `--strip-cols` / `--strip-cols-md`, which the component sets from its `cols` input).

`sb-stat-strip` takes an optional `cols` input; the migration pins `cols` where today's layout has a fixed count (Dashboard trading performance: 4; Risk metrics: 6 → 3 at md), so column counts do not change by accident. A call site that wants auto-fit omits it and the reflow is accepted explicitly in its migration commit.

**Hairlines, start-edge, same geometry as `sb-figure-strip`.** `figure.ts` already rules its cells with `border-left` / `border-top` of `var(--figure-rule, 0px)` and a `-1px` start-edge offset (`figure.ts:15`). The strip reuses that mechanism: it sets `--figure-rule: 1px` on itself (an inherited custom property, so it crosses Angular's emulated encapsulation into projected children without `::ng-deep`), wraps the grid in an `overflow: hidden` box and offsets the grid `margin: -1px 0 0 -1px`, clipping the first row's top rule and the first column's left rule. `sb-stat-tile` (and `sb-metric-card`, if kept — see Migration) read `--figure-rule` on their `:host` exactly as `sb-figure` does. Because the rules are start-edge, an incomplete last row (5 tiles in 4 columns, an odd count at 2-up) leaves no stray rule beside the empty space.

**Tile surface inside a strip.** The strip also sets `--tile-bg: transparent`, `--tile-border: 0` and `--tile-radius: 0`; the tile's `.tile` reads `background: var(--tile-bg, var(--surface))`, `border: var(--tile-border, 1px solid var(--border))`, `border-radius: var(--tile-radius, var(--panel-radius))`. Outside a strip a tile looks as it does today; nothing unmigrated breaks.

**Hover lift.** `overflow: hidden` would clip `.sb-lift`'s translate and shadow (`motion.css` ~137). Inside a strip the lift is off: one global rule in `motion.css`, `sb-stat-strip .sb-lift:hover { transform: none; box-shadow: none; }` (global stylesheet, not `::ng-deep`; adds no shadow, so primitives G3 is unaffected). Tiles are not focusable, so no focus ring is clipped.

**Tint.** `sb-metric-card`'s `[tint]` paints a `--pos-soft` / `--neg-soft` gradient via `:host(.tint-*) .card` (`metric-card.ts`, end of styles), which outranks `--tile-bg`. Inside a strip the tint is **dropped**: valence is carried by the value colour and its sign glyph, which is the colour law's primary channel, and a tinted block inside a ruled strip reintroduces the box-in-box this spec removes. Implemented by the tint rule reading `var(--tile-tint-off, <gradient>)`, with the strip setting `--tile-tint-off: none`; tested.

Empty strip renders nothing (no stray rules); one tile renders with no visible rule.

**Tile anatomy** (`sb-stat-tile`; `sb-metric-card` aligned if kept):

| part | face | size | colour |
|---|---|---|---|
| label | `.sb-label` (mono caps) | `--text-micro` | `--text-muted` (was `--text-faint`) |
| value | D4 figure face | `--text-metric` | `--text` / `--pos` / `--neg` |
| secondary | `--font-num` | `--text-micro` | `--text-secondary` |
| `N=`, hint | `--font-num` / `--font-sans` | `--text-micro` | `--text-muted` (was `--text-faint`) |

The thin-sample state keeps both cues (value opacity 0.62 **and** the "· thin sample" words).

**Migration.** Every row of two or more tiles inside an `sb-panel` is wrapped in `sb-stat-strip`, replacing its hand-built grid (and that grid's breakpoint rules). The plan's first task greps and lists the call sites; the known ones are Dashboard (`trading-performance.ts`, 8 cards, today `repeat(4, minmax(140px, 1fr))` with a 2-up breakpoint, a `.grid.stale` opacity and a `mobile-summary` fallback — the stale opacity and mobile fallback move onto the strip host unchanged), Analytics (overview tiles), Risk (`.metric-grid`, 6 tiles) and Calendar (month summary). A page-level row of standalone cards outside a panel is left as is.

`sb-metric-card` is marked deprecated in its own doc comment (v80 D4). The plan's brief checks whether `sb-stat-tile` covers every input the strip-bound metric-card call sites use (`tint`, absent value, sub-line); if it does, those call sites move to `sb-stat-tile` and metric-card gains no new API; if not, metric-card gets the same `--figure-rule` / `--tile-*` / `--tile-tint-off` reads and the gap is recorded in the brief.

### D4 — One figure face for display numbers

New tier-2 tokens in `tokens.css`, beside `--font-num`:

```css
--font-figure: var(--font-sans);   /* display figures: Inter */
--figure-weight: 600;
--figure-tracking: -0.02em;
```

There is **no global class**: a global `.x` (0,1,0) loses to a component's scoped `.value[_ngcontent-…]` (0,2,0). Each display-figure rule is edited **in its own component's CSS**: its existing `font-family` / `font-weight` declarations are replaced with `font-family: var(--font-figure); font-weight: var(--figure-weight); letter-spacing: var(--figure-tracking); font-variant-numeric: tabular-nums;`, and any global `.num` class on that element is removed from the template (it would otherwise reassert mono). The sites:

| element | today | change |
|---|---|---|
| `stat-tile.ts` `.value` | `--font-num`, default weight | figure face, 600 |
| `figure.ts` `.value` (template also has `num`) | `--font-mono`, 500 | figure face, 600; drop `num` |
| `metric-card.ts` value (if kept) | weight 700 | figure face, 600 (visual weight change, noted) |
| `panel-header.ts` `.total` (template also has `num`) | mono via `.num` | figure face at `--text-chip`; drop `num` |
| `portfolio-value.ts` `.figure` | Inter 600 at `--text-title` already | add `letter-spacing: var(--figure-tracking)` only; `.figure.muted` moves `--text-faint` → `--text-muted` |

**Not** changed: table cells, prices in tables, `N=`, axis ticks and secondary lines stay `--font-num` (mono) so columns align. Inter is vendored at 400/500/600/700 (`fonts.css`), so nothing is synthesised. Tabular digits keep the v168 count-up from jittering. `.pos`/`.neg` and sign glyphs are unchanged. If `scripts/dev/dump_tokens.py` output changes because of the new tokens, `tests/charts/resolved_tokens.json` is regenerated and committed with them.

### D5 — Shaped, quiet skeletons

In `sb-async` (`ui/async.ts`):

- Each `.skeleton-cell` keeps its `--control-h` box (no layout shift on swap) and draws a centred **8px bar** inside it via `::before` (`--radius-sm`). The animation lives on the `::before`.
- Bar widths follow a fixed sequence **by column index** (40%, 65%, 30%, 55%, repeating), so a 4- and a 6-column grid are both deterministic. Implemented as a `--bar-w` value set per cell from its column index in the template.
- New `SkeletonShape` `'tiles'`: a separate template branch (not the flex-row grid) rendering a `.sb-strip-grid` container (the D3 global class, `--strip-cols` from a new `skeletonCols` value) of cells, each a short label bar (35%) above a value bar (60%). `skeletonGrid` keeps its `string[][]` contract for the existing shapes; `'tiles'` does not go through it.
- `sb-shimmer` is replaced by a new keyframe `sb-skeleton-pulse` (opacity 0.5 → 0.9 → 0.5, 1.8s, ease-in-out; duration multiplied by `--motion-scale`). `sb-shimmer` has no other user (`async.ts`, `motion.css:87`, specs only) and is deleted.
- `motion.css`'s `[data-motion=reduced] sb-async .skeleton-cell` (≈221) and `[data-motion=off] sb-async .skeleton-cell` (≈253) are **retargeted** to `sb-async .skeleton-cell::before` and the `'tiles'` bars; otherwise Reduced and Off users would get a pulse.

## Out of scope

Shell (header, ticker tape, scan-progress line, sidebar), toolbars and filter bars, table density and alignment, danger-button placement, the correlation matrix, per-workspace layout and the Dashboard hero placement. Each is a later spec. No colour value changes, so `palette.css` and `chart_style.THEME` are untouched. The 102 other `--text-faint` uses outside the files named here are not migrated by this spec (see Testing: the new check is scoped).

## Testing

Unit tests ship with each change (vitest, `frontend/src/app/ui/*.spec.ts`):

- **Panel title:** `sb-panel` heading has no `sb-label` class and its source styles set `--font-sans`, 600, `--text-body`, no `text-transform`; `sb-panel-header` `h2` the same; meta spans use `--text-muted`; `all-time` keeps `--warn`.
- **Header rule:** `.ruled` present for `flush`, for `divided`, absent otherwise; an unruled header still has a 1px (transparent) bottom border, so ruled and unruled headers compute the same height; `.body.tight` only with a heading and no rule; headingless panel keeps `--space-14`.
- **Strip:** renders children in `.sb-strip-grid`; sets `--figure-rule: 1px`; `cols` sets the three column counts; empty strip renders no rule; a single tile shows no visible rule; a 5-in-4 strip shows no rule beside the empty cell; tiles inside a strip have transparent background, no border, radius 0; a tinted card inside a strip has no tint, outside keeps it; a tile outside a strip keeps its surface and border; thin-sample state keeps opacity and the words.
- **Figure face:** a source-text check that each D4 site's scoped rule uses `var(--font-figure)` / `var(--figure-weight)` and that `figure.ts` / `panel-header.ts` templates no longer put `num` on those elements; an `sb-data-table` cell and a tile `N=` still use `--font-num`; existing `portfolio-value.spec.ts` `.figure` selectors still pass.
- **No faint text in scope:** a new **source-text scan** in `contrast.spec.ts` (jsdom does not resolve component `var()` chains; pattern as `async.spec.ts:166`) asserting `--text-faint` does not appear as a `color` in `stat-tile.ts`, `metric-card.ts` (including `.absent`), `layout.ts` (panel header and `.panel-toggle`), `panel-header.ts`, `figure.ts` and `portfolio-value.ts`. It is scoped to these files on purpose; the existing comment-only `no-text-uses-text-faint` note is not widened to the whole app here.
- **Skeleton:** bar widths follow the column-index sequence for 4- and 6-column grids; `'tiles'` renders label + value bars inside `.sb-strip-grid`; row box height still equals `--control-h`; Reduced and Off rules target the bar.
- **Gate specs that change, in the same commit as the code they pin:** `motion-css.spec.ts` `KEYFRAMES` list gains `sb-skeleton-pulse`, loses `sb-shimmer` (opacity is compositor-safe); `async.spec.ts:166` literal `animation: sb-shimmer 1.6s linear infinite;` updated to the pulse on `::before`; any selector found by the D1 grep.
- **Gates that must stay green unchanged:** `primitives.spec.ts` G3 (no new non-inset shadow, no raw radius), `tokens.spec.ts`, `workspace-consistency.spec.ts` (no `::ng-deep` into tiles or the strip), `elevation.spec.ts`, `vertical-centre.spec.ts`, `layout-audit` at three widths.
- **Visual check** (`ui-design.md`): Dashboard, Analytics, Risk and Calendar at 1440, 1024 and 390, before and after, with `frontend/scripts/browse.mjs shots` against a local build; page horizontal scroll stays 0; column counts per migrated strip match the `cols` pinned above.

## Rollout

One plan, several scoped commits: (1) figure tokens; (2) panel title + conditional rule in `sb-panel` and `sb-panel-header`, with the D1 selector updates; (3) tile custom-property reads, tint switch and colour fixes; (4) `sb-stat-strip` + `.sb-strip-grid` + the motion.css lift rule; (5) figure face at each D4 site; (6) call-site migration, one workspace per commit; (7) skeleton bars, `'tiles'` shape, pulse and the gate-spec edits; (8) full suite. Implemented in a worktree per CLAUDE.md.

## Panel review

senior-engineer (2026-10-23), 4 BLOCKING, 8 ADVISORY:

1. BLOCKING — strip rules cannot be drawn from the strip's scoped CSS across emulated encapsulation; needs an inherited property read by the tile -- applied: strip sets `--figure-rule`, tiles read it as `sb-figure` does (D3).
2. BLOCKING — `sb-metric-card` `[tint]` outranks `--tile-bg`, so tinted cards stay coloured in a strip -- applied: tint dropped inside a strip via `--tile-tint-off`, with reasoning and a test (D3).
3. BLOCKING — portfolio hero is already Inter 600 at `--text-title`, not mono at `--text-hero` -- applied: Why #3 corrected; hero only gains tracking and the muted-colour fix (D4).
4. BLOCKING — a global `.sb-figure` loses on specificity to scoped `.value` rules -- applied: no global class; each site's scoped rule is rewritten to the figure tokens and `num` removed (D4).
5. ADVISORY — end-edge rules differ from `figure.ts`'s start-edge geometry, leave a stray rule on an incomplete last row, and `overflow:hidden` clips `.sb-lift` -- applied: start-edge geometry reused; lift disabled in strips by a global motion.css rule (D3).
6. ADVISORY — conditional rule breaks the `+1px` header-height contract; tight padding under-specified; header not class-bound -- applied: transparent border keeps height; `.ruled` / `.tight` bindings and the headingless case specified (D2).
7. ADVISORY — tests and selectors may depend on `h2.sb-label` -- applied: D1 grep covers tests, e2e and layout-audit selectors.
8. ADVISORY — the faint-text assertion is not an existing test and must be a source scan; misses `.panel-toggle` and `.absent` -- applied: scoped source-text scan named with its files; both sites migrated (D2, D3, Testing).
9. ADVISORY — motion-css KEYFRAMES list, `async.spec.ts:166` and the Reduced/Off rules pin the old skeleton -- applied: listed as gate-spec edits; Reduced/Off retargeted to `::before` (D5, Testing).
10. ADVISORY — `'tiles'` cannot use the flex-row skeleton grid; width sequence ambiguous -- applied: separate branch on the shared `.sb-strip-grid`; sequence by column index (D5).
11. ADVISORY — auto-fit changes migrated column counts; metric-card is deprecated -- applied: `cols` input pins counts per call site; brief decides metric-card → stat-tile (D3).
12. ADVISORY — metric-card weight 700 → 600 undocumented -- applied: noted in the D4 table.
