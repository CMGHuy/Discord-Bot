# v186 — UI foundation refresh: one panel title, divided stat strips, Inter figures, quiet skeletons

**Version:** ui 1.35.0 · bot 2.14.4 (at writing)
**Bump:** ui minor; bot none. New shared primitive (`sb-stat-strip`), a new token (`--font-figure`) and a visible change to every panel and tile.
**Edge:** none (integrity). Presentation only: no data, API, copy or colour value changes.
**Screen:** exempt (integrity)
**Panel:** senior-engineer
**Status:** spec written 2026-10-23 from a brainstorm with the partner, approved in chat section by section. First of four UI-refresh specs (foundation → shell → toolbars & tables → workspace passes); the other three are not yet written.

## Why

A walk through all 13 workspaces at 1440 and 390 (production, 2026-10-23) found that the token layer (v167 Arctic Navy, v168 motion, v179) is sound, and that the app reads as less professional than it is for four foundation-level reasons:

1. **Three heading voices for one job.** `sb-panel` (147 call sites) renders its heading as `.sb-label`: monospace caps, letter-spaced (`KILLSWITCH`, `TRADING PERFORMANCE`). `sb-panel-header` (43 call sites, mostly Analytics) renders a 16px bold sans `h2` (`Equity`, `Outcome`). Stat tiles add a third: spaced sans caps. Pages do not look like one product, and titles look the same as field labels, so hierarchy is flat.
2. **Box in box.** Every panel draws a header strip, a border, a gradient and a shadow. Stat tiles nested in it draw their own border and surface (Dashboard performance, Risk metrics, Calendar summary). Calm technical UIs separate siblings with hairlines and space, not nested frames.
3. **Large figures in a code face.** Every number is JetBrains Mono, including 28px tile values and the 44px hero. Mono digits are right for columns; at display size they read wide and blocky.
4. **Unreadable secondary text, loud loading.** Tile labels, `N=` and hints use `--text-faint`, which `tokens.css` itself defines as a rule/divider colour "never text that must be read" (~2:1). The loading skeleton is full-height slabs with a sweeping shimmer — the heaviest thing on the Dashboard while it loads.

## Decisions

### D1 — One panel title

Both `sb-panel`'s heading and `sb-panel-header`'s `h2` render:

- **Title:** `--font-sans`, weight 600, `--text-body` (14px), `--text`, sentence case, `letter-spacing: normal`, no `text-transform`.
- **Meta** after the title on the same baseline (`N=`, `all-time`, totals, as-of): `--font-num`, `--text-micro`, `--text-muted`. `all-time` keeps `--warn`. A **total** (`sb-panel-header`'s `total`) is a figure and takes `--font-figure` at `--text-chip` in `--text-secondary`.
- `.sb-label` (mono caps) is unchanged and remains the style for **field and tile labels** (`WIN RATE`, `TICKER`, `STRATEGY`). It is no longer used for panel titles.
- Header min-height and baseline alignment (v179 §3.4) are unchanged.

Text passed as a heading is not rewritten: titles already passed in sentence or title case render as passed. A caller that passes an ALL-CAPS literal is changed to sentence case in the migration task (grep, not guessed).

### D2 — Panel frame: keep the surface, make the header rule conditional

- `--panel-bg` (gradient), `--panel-border`, `--panel-radius` and `--panel-shadow` are **unchanged** (partner decision).
- The header's `border-bottom` is drawn only when the panel is `flush` **or** has the new boolean input `divided`. A flush panel's body is a table; `divided` is for a non-flush body that starts with a tab strip or a table-like list.
- Without the rule, the header keeps its padding and the body's top padding drops to `--space-4`, so title → first row is `--space-10` + `--space-4` = 14px rather than two paddings and a rule.

### D3 — `sb-stat-strip`: tiles separated by hairlines

New component `sb-stat-strip` in `frontend/src/app/ui/stat-strip.ts`:

- Projects `sb-stat-tile` and `sb-metric-card` children into a grid: `repeat(auto-fit, minmax(min(100%, 160px), 1fr))`; below 640px, `repeat(2, minmax(0, 1fr))`.
- **Hairlines between cells only, no outer frame.** Each cell draws `border-inline-end` and `border-block-end` `1px solid var(--border)`; the grid sits in a wrapper with `overflow: hidden` and the grid offset by `-1px` on its end and bottom edges, which clips the trailing rules. No `box-shadow` (primitives G3), no gap-background trick (it would expose the panel gradient as mismatched lines). Precedent: `sb-figure-strip` (`ui/figure.ts`) already rules its cells with `--figure-rule`; the plan's brief checks whether the strip can share that mechanism rather than add a second one, and the two must look identical side by side.
- Sets `--tile-bg: transparent`, `--tile-border: 0` and `--tile-radius: 0` on itself. `sb-stat-tile` and `sb-metric-card` read `background: var(--tile-bg, var(--surface))`, `border: var(--tile-border, 1px solid var(--border))`, `border-radius: var(--tile-radius, var(--panel-radius))`. Outside a strip a tile looks as it does today; nothing unmigrated breaks.
- Empty strip renders nothing (no stray rules); one tile renders without any rule.

**Tile anatomy** (`sb-stat-tile`; `sb-metric-card` aligned to the same rules):

| part | face | size | colour |
|---|---|---|---|
| label | `.sb-label` (mono caps) | `--text-micro` | `--text-muted` (was `--text-faint`) |
| value | `--font-figure` | `--text-metric` | `--text` / `--pos` / `--neg` |
| secondary | `--font-num` | `--text-micro` | `--text-secondary` |
| `N=`, hint | `--font-num` / `--font-sans` | `--text-micro` | `--text-muted` (was `--text-faint`) |

The thin-sample state keeps both cues (value opacity 0.62 **and** the "· thin sample" words).

**Migration.** Every row of two or more `sb-stat-tile` / `sb-metric-card` siblings inside an `sb-panel` is wrapped in `sb-stat-strip`, replacing the hand-built grid around them. The plan's first task greps and lists the call sites; the known ones are Dashboard (trading performance), Analytics (overview tiles), Risk (risk metrics) and Calendar (month summary). A tile row that is a page-level row of standalone cards (not inside a panel) is left as is.

### D4 — `--font-figure` for display figures

New tier-2 token in `tokens.css`, beside `--font-num`:

```css
--font-figure: var(--font-sans);   /* display figures: Inter, tabular */
```

and a global class in `styles.css`:

```css
.sb-figure { font-family: var(--font-figure); font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
```

`.sb-figure`, not `.figure`: `.figure` is already a local class in `ui/figure.ts` and `dashboard/panels/portfolio-value.ts`, and a global rule of that name would leak into both.

Applied to: tile values (`sb-stat-tile .value`, `sb-metric-card` value), `sb-figure`'s `.value` (`ui/figure.ts`, today `--font-mono` 500), the Dashboard portfolio hero (`portfolio-value.ts` `.figure`, `--text-hero`), and `sb-panel-header` totals. `portfolio-value.ts`'s absent state (`.figure.muted`) moves from `--text-faint` to `--text-muted` under the same readability rule as D3. **Not** applied to table cells, prices in tables, `N=`, axis ticks or secondary lines — those stay `--font-num` (mono) so columns align. Inter is vendored at 600 (`fonts.css`), so nothing is synthesised. Tabular digits keep the v168 count-up from jittering. `.pos`/`.neg` and sign glyphs are unchanged.

### D5 — Shaped, quiet skeletons

In `sb-async` (`ui/async.ts`):

- Each `.skeleton-cell` keeps its `--control-h` box (no layout shift on swap) and draws a centred **8px bar** inside it (`--radius-sm`), via a child element or `::before`, not the full box.
- Bar widths vary per column from a fixed sequence (40%, 65%, 30%, 55%, repeating) so the outline reads as data. Deterministic, so tests can assert it.
- New `SkeletonShape` `'tiles'`: per cell a short label bar (35%) above a value bar (60%), laid out in the same grid as `sb-stat-strip`.
- `sb-shimmer` is replaced on skeletons by a new keyframe `sb-skeleton-pulse` (opacity 0.5 → 0.9 → 0.5, 1.8s, ease-in-out, scaled by `--motion-scale`). `[data-motion=reduced]` and `[data-motion=off]` keep `animation: none` (existing rules in `motion.css`, retargeted). `sb-shimmer` is deleted if no other user remains.

## Out of scope

Shell (header, ticker tape, scan-progress line, sidebar), toolbars and filter bars, table density and alignment, danger-button placement, the correlation matrix, per-workspace layout and the Dashboard hero placement. Each is a later spec. No colour value changes, so `palette.css`, `chart_style.THEME` and `tests/charts/resolved_tokens.json` are untouched (if `dump_tokens.py` output changes because of the new `--font-figure` token, it is regenerated and committed in the same commit).

## Testing

Unit tests ship with each change (vitest, `frontend/src/app/ui/*.spec.ts`):

- **Panel title:** `sb-panel` heading and `sb-panel-header` `h2` both compute `font-family` from `--font-sans`, weight 600, no `text-transform`; meta spans use `--text-muted`, never `--text-faint`; `all-time` keeps `--warn`.
- **Header rule:** present for `flush`, present for `divided`, absent otherwise; body top padding follows.
- **Strip:** renders children in a grid; no rule on an empty strip; a single tile has no rule; tiles inside a strip have transparent background and no border; a tile outside a strip keeps its surface and border; thin-sample state keeps opacity and the words.
- **Figure:** tile value, `sb-figure` value, the portfolio hero and the panel-header total resolve to `--font-figure` (via `.sb-figure`); an `sb-data-table` cell and a tile `N=` do not; the existing `portfolio-value.spec.ts` `.figure` selectors still pass.
- **Skeleton:** bar widths follow the sequence for a 4- and 6-column grid; `'tiles'` shape renders label + value bars; Motion Off and Reduced set no animation; row box height still equals `--control-h`.
- **Gates that must stay green:** `contrast.spec.ts` (add: no text in `sb-stat-tile`, `sb-metric-card`, `sb-panel` header or `sb-panel-header` resolves to `--text-faint`), `primitives.spec.ts` G3 (no new non-inset shadow, no raw radius), `tokens.spec.ts`, `workspace-consistency.spec.ts` (no `::ng-deep` into tiles or the strip), `motion-css.spec.ts`, `vertical-centre.spec.ts`, `elevation.spec.ts`, `layout-audit` at three widths.
- **Visual check** (`ui-design.md`): Dashboard, Analytics, Risk and Calendar at 1440, 1024 and 390, before and after, with `frontend/scripts/browse.mjs shots` against a local build; page horizontal scroll stays 0.

## Rollout

One plan, several scoped commits: (1) `--font-figure` token + `.figure` class; (2) panel title + conditional rule in `sb-panel` and `sb-panel-header`; (3) tile/metric-card custom properties and colour fixes; (4) `sb-stat-strip`; (5) call-site migration, one workspace per commit; (6) skeleton bars, `'tiles'` shape and pulse; (7) full suite. Implemented in a worktree per CLAUDE.md.
