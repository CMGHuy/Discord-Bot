# v240 — Doctena night, plan 1 of 5: Theme and type (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V240-7" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) — plan 1 of its "What follows" list; its `### Corrections from the plan 1 code brief` section overrides the text above it.
**Brief:** `.superpowers/briefs/v240-plan1-theme-and-type.md`

## Goal

The partner asked for bomeo-capital.com to take doctena.de's font and look,
translated into a dark theme. Spec v240 approved that redesign in six parts
and split the work into five plans that run strictly in order. This is the
first. It changes only the foundations every later screen is checked
against: the colours, the typeface, the corner shapes and the type rules.
Icons, the rail, Calendar as a destination and the drawers are plans 2 to 5.
They need this plan merged first, because their three-device checks would
otherwise be made against tokens that are about to move.

Once this ships, a browser that never chose a theme opens in **Navy**, which
now shows "doctena night": a deep blue ground (`#00131F`), blue accents,
doctena's mint for gains and a lifted coral for losses. A browser that
explicitly chose **Black** keeps Black, with the same colours as today. The
first paint already shows the right ground, because the pre-boot script,
the static `theme-color` meta, the inline cold-load style and the web
manifest all move to the Navy ground together. **Jost** replaces Inter and
JetBrains Mono for every piece of text, numbers included. It is
self-hosted (no CDN) with metric-matched fallback faces, so a slow font
load does not shift the layout. Corners grow to doctena's 10 to 12px,
chips become pills, buttons read UPPERCASE with a little tracking, and
large headings tighten. Inputs, selects and segmented controls get a
visible `--control-border` that clears 3:1 on Navy.

How it works: the Navy block in `tokens.css` re-points twenty tokens
(ground, ink, accent, P&L, control border) to a new `doctena-*` ramp in
`palette.css`, and the old `midnight-*`/`frost-*` ramps are deleted. The
bare `:root` stays Graphite, so `dump_tokens.py`, the token fixture and
the Discord chart PNGs keep the Black colours (and Inter: the PNGs are out
of scope). The font tokens change once, `--font-mono` becomes an alias of
`--font-sans`, and no component changes its `font-family`.

Four source-scan gates make the rules stick. Every rule that reads
`--font-num`/`--font-mono`, or styles a `.num` cell, carries
`font-variant-numeric: tabular-nums`, because Jost is proportional and
columns only stay aligned through its `tnum` feature (a Python test pins
that feature in the vendored file). No rule paints text in `--text-faint`,
which stays a divider colour: about 97 such reads move to `--text-muted`.
Navigation, brand, active and focus rules never read `--pos`/`--neg`, so
mint means "gain", never "you are here". Every formatted loss prints a true
minus (U+2212), so a loss never reads by hue alone; seven sites that can
print an ASCII hyphen today are fixed. The first two gates start with a
pending list of today's offenders. Four sweep tasks empty it by area, and
the last one deletes the pending machinery.

What it leaves alone: no data, schema, alert, API or trading behaviour; the
icon set, the rail, navigation and drawers (plans 2 to 5); the Discord
charts (`chart_style.py` and the `vendor/inter/` files it names); and the
good/bad status uses of `--pos`/`--neg` (errors, danger buttons, the
kill-switch, shock pill, flashes, tape), which the corrected spec keeps.
Success: every listed spec is green in both themes (`contrast.spec.ts`
runs over `TOKEN_THEMES`); the four gates pass with empty pending lists;
`python scripts/dev/dump_tokens.py --check` passes; the vendored-font
Python test passes; and the controller's three-device look at 390, 820 and
1440px (one page per workspace, including a 12 to 13px price column) shows
Jost and the new shapes in both themes with nothing scrolling sideways.

## Architecture

- **Colours (`frontend/src/styles/`).** `palette.css` gains the `doctena-*`
  ramp and four alpha entries, and loses `midnight-*`/`frost-*`.
  `tokens.css`'s single `:root[data-theme="navy"]` block re-points the 20
  tokens in `NAVY_TOKENS` (Global Constraints). It holds `var()` references
  only, never a `}` or a literal (`tests/dev/test_dump_tokens.py`
  `_NAVY_BLOCK`). `frontend/src/app/ui/testing/theme-tokens.ts` mirrors the
  set as `NAVY_TOKENS` (renamed from `GROUND_INK_TOKENS`).
- **Default flip.** `readTheme` inverts (anything but exactly `'graphite'`
  is Navy). The pre-boot script in `frontend/src/index.html` always sets
  `data-theme` before first paint, using `NAVY_BG` or `GRAPHITE_BG` for the
  meta. The static meta, the inline `html, body` ground and
  `manifest.webmanifest` hold the Navy `--bg`.
- **Fonts.** `swingbot/admin/static/vendor/jost/` holds two variable woff2
  subsets plus the OFL licence. `fonts.css` declares `Jost` per subset and
  the two metric-matched fallback families. `vendor/jetbrains-mono/` is
  deleted; `vendor/inter/` stays for `chart_style.py:20`.
- **Gates share one parser.** `frontend/src/app/ui/testing/style-rules.ts`
  (V240-6) turns a source into `{ selector, body }` rules, reading only real
  style text: a `.css` file whole, a `.ts` file's `styles:` template
  literals, nothing from `.html`. It strips comments with `stripComments`
  from `all-sources.ts`. The control-border, thin-bar radius, type and
  money-colour gates all use it, so a TS code block is never mistaken for a
  CSS rule.
- **Fixture rule.** Every task that changes a bare-`:root` declaration in
  `palette.css` or `tokens.css` (V240-2, V240-3, V240-7) runs
  `python scripts/dev/dump_tokens.py` and commits
  `tests/charts/resolved_tokens.json` in the same commit.

## Decisions this index fixes (spec silent; controller may override)

1. **Black's `--control-border` is `var(--border-strong)`.** The bare
   `:root` gains `--control-border: var(--border-strong);`, so Black
   controls look exactly as today. The 3:1 non-text gate on
   `--control-border` runs for **Navy only**. Black's `#2d333b` is about
   1.5:1 on its surface and stays a known gap, listed in Handoff. Raising
   it would change Black's colours, and the spec keeps those.
2. **The pre-boot script always sets `data-theme`** (`navy` unless storage
   holds exactly `'graphite'`; a throwing storage gives `navy`), so a
   default user's first paint already uses the Navy tokens, not just the
   Navy ground. It sets the meta to `NAVY_BG` or `GRAPHITE_BG`, and injects
   a ground `<style>` only for Graphite. `index.html`'s comment beside the
   cold-load copies reads `manifest.webmanifest takes the Navy ground`
   (pinned by test, replacing `... stays Graphite`).
3. **`--text-faint` → `--text-muted` for every `color:` read**, in both
   themes. The gate matches the property `color` exactly, so
   `border-color`, `background` and `fill` reads stay legal: those are
   dividers and marks. Black's captions get lighter too (Graphite faint is
   about 3.7:1, below AA for text), which is the spec's intent.
4. **`tabular-nums` is added to every flagged rule, with no exemption
   list.** It only changes digits, so tickers, codes and labels are
   unaffected. Exemptions would be judgement calls a sweep should not make.
5. **The money-colour scan has two parts.** (a) Any rule anywhere whose
   selector holds `:focus`, `:focus-visible`, `:focus-within`,
   `[aria-current` or `.active` must not read `--pos`/`--neg`. (b) Every
   rule in the nav files must not read them. These are
   `app/shell/phone-tab-bar.ts`, `app/shell/more-sheet.ts`,
   `app/shell/section-tabs.ts`, `app/shell/breadcrumb.ts` and
   `app/shell/shell.css` rules whose selector matches
   `/rail|brand|wordmark|nav|tab/`. `shell.css`'s `.killswitch-strip`
   (status) is outside that selector filter. Plan 3 adds its editor file to
   the list.
6. **Uppercase buttons.** `text-transform: uppercase; letter-spacing:
   0.04em;` goes on `sb-button`'s `:host`. It is reset
   (`text-transform: none; letter-spacing: normal;`) on the `icon`,
   `danger-icon`, `chip`, `segment` and `link` variants. Those are icon
   buttons, filter chips, segmented tabs and inline links, which doctena
   does not uppercase.
7. **Heading tracking is the literal `letter-spacing: -0.02em`** on the
   eight heading rules the brief lists. No new token is added, so the
   fixture does not change.
8. **The `tnum` test needs Brotli.** fontTools already arrives with
   matplotlib, but woff2 decoding needs `brotli`, so `requirements.txt`
   gains `Brotli>=1.1.0` (test-only, like `pytest`). The test asserts the
   module imports, never skips.
9. **A shared `fixed(value, decimals)` formatter** goes in `format.ts` for
   the plain-number true-minus sites. It prints no `+` on gains (those
   sites never printed one) and never prints `−0.00`.
10. **The zero-sign rule extends to every formatter** (partner decision,
    2026-11-23). A value that rounds to zero prints unsigned app-wide, not
    only in `fixed()`, `formatFigureText` and the tape: `pct`, `money`,
    `rMultiple` and `signed` in `ui/format.ts` print `0.00`, never `−0.00`
    or `+0.00` (`pct(-0.004)` is `0.00%`). One private
    `signFor(value, magnitude)` signs only a printed magnitude holding a
    non-zero digit. V240-11 does it and moves the pins of today's signed
    zero (`format.spec.ts`, `status-cell.spec.ts:75`). The local
    formatters `partials.ts` `rText` and `calendar.helpers.ts` `cellValue`
    (`+0.00R` on an exact zero) are outside `format.ts` and not in this
    plan.
11. **`NUM_FACE` accepts a `var()` fallback**
    (`var\(--font-(?:num|mono)\s*(?:,[^)]*)?\)`), so
    `calendar.ts`'s `.trade-id { font-family: var(--font-mono, monospace) }`
    is gated (V240-9) and fixed in V240-15. The tabular offender count is
    67 rules in 39 files (`calendar.ts` was already pending).

## Global Constraints

- Navy (`:root[data-theme="navy"]`) values. Palette names map to values,
  and the hex is written lowercase in `palette.css`:
  `--doctena-950: #00131f` (bg), `--doctena-900: #001e30` (surface),
  `--doctena-850: #032a42` (raised), `--doctena-800: #073652` (overlay),
  `--doctena-750: #0d3d59` (border), `--doctena-700: #1d5373`
  (border-strong), `--doctena-500: #6e94a8` (faint), `--doctena-300:
  #8fb3c8` (muted), `--doctena-200: #c8e1ef` (secondary), `--doctena-50:
  #fafdff` (text), `--doctena-sky-400: #5aa9d6` (accent),
  `--doctena-blue-600: #0072b0` (accent-fill, control-border),
  `--doctena-blue-700: #005b8c` (accent-fill-hi), `--doctena-mint-400:
  #53ceb5` (pos), `--doctena-coral-400: #f07a7a` (neg),
  `--doctena-950-a72: rgba(0, 19, 31, 0.72)` (overlay-dim),
  `--doctena-blue-500-a24: rgba(50, 142, 192, 0.24)` (accent-soft),
  `--doctena-mint-400-a14: rgba(83, 206, 181, 0.14)` (pos-soft),
  `--doctena-coral-400-a14: rgba(240, 122, 122, 0.14)` (neg-soft).
- `NAVY_TOKENS` (exactly these 20, in this order): `--bg, --surface,
  --surface-raised, --surface-overlay, --overlay-dim, --border,
  --border-strong, --text, --text-secondary, --text-muted, --text-faint,
  --accent, --accent-fill, --accent-fill-hi, --accent-soft,
  --control-border, --pos, --neg, --pos-soft, --neg-soft`.
- **Contrast thresholds never drop.** A Navy value that fails its
  existing gate is moved in `palette.css` (lighter text, darker fill) until
  it passes, and the new value is recorded in the task's commit message.
  `--control-border` ≥ 3:1 on `--bg` and `--surface` (Navy).
- Fonts: `--font-sans: "Jost", "Jost Fallback", "Jost Fallback Android",
  system-ui, sans-serif;` and `--font-mono: var(--font-sans);`.
  `--font-num: var(--font-mono);` and `--font-figure: var(--font-sans);`
  are unchanged. The Jost faces use `font-weight: 100 900`,
  `font-display: swap`, and the `unicode-range` strings quoted in the brief
  (§3 Fonts), verbatim. The fallback faces use the spec §2 table verbatim
  (`line-gap-override: 0%` on all four).
- Radii: `--panel-radius: 10px; --control-radius: 12px; --pill-radius:
  999px; --chip-radius: var(--pill-radius); --radius-sm: 6px;
  --panel-inner-radius: 8px; --panel-shadow: none;`. A rule reading
  `--radius-sm` that declares a `height` under 6px uses `--pill-radius`
  instead. Components never write a px radius literal (primitives.spec
  radius gate).
- Theme semantics: `readTheme` returns `'graphite'` only for a stored
  value of exactly `'graphite'`, otherwise `'navy'` (missing, junk or
  throwing storage). The profile menu lists Dark blue first, and its labels
  stay `Black` / `Dark blue`.
- True minus: U+2212 (`MINUS` in `ui/format.ts`) on every negative
  formatted figure. A value that rounds to zero prints no sign.
- The bare `:root` stays Graphite. Never teach `dump_tokens.py` or
  `resolve-token.ts` a theme (v225). `chart_style.py` and `vendor/inter/`
  are untouched.
- Per-task verification is narrow:
  `cd frontend && npx ng test --watch=false --include <spec>` (one or a few
  spec files; a 60s `Timeout waiting for worker` is load, so re-run once),
  and `python scripts/dev/testrun.py file <test>` for Python. No task runs
  the full suite; CI does.
- Every function written or changed stays under cyclomatic complexity 15.
  Scans are table-driven.
- Commit in scoped commits; never stage another session's files on `main`
  (the controller commits).

## Parallelisation

The plan runs **in id order in one worktree** (spec: plans 1 to 5 are
strictly sequential; one worktree at a time). The sequential edges inside
it, and their reasons:

- V240-2 → V240-3 → V240-7: all three edit `tokens.css` and regenerate
  `tests/charts/resolved_tokens.json`, a single generated file.
  V240-1 → V240-2: the spec says JetBrains Mono is deleted only after the
  `tnum` check exists.
- V240-3 → V240-3b: same files (`contrast.spec.ts`, `tokens.spec.ts`, `tokens.css`); 3b gates what 3 sets.
- V240-3 → V240-5: the pre-boot literals are pinned to the Navy `--bg` that
  V240-3 sets, and both edit `index.html` and `primitives.spec.ts`.
  V240-4 → V240-5: the script mirrors `readTheme`'s inverted rule, and both
  rewrite default-theme tests.
- V240-6 → V240-7, V240-9, V240-10: they consume `styleRules` (contract).
- V240-7 ∥ V240-8 is not allowed: both edit `ui/layout.ts`.
- V240-9 → V240-13 → V240-14 → V240-15 → V240-16: every sweep edits the
  pending sets in `ui/type-gates.spec.ts`, and V240-16 deletes them.
- V240-11 → V240-12: V240-12 consumes `fixed()` from V240-11.
- V240-13 also edits `ui/plan-cell.ts`, `ui/metric-chip.ts` (V240-11) and
  `ui/button.ts` (V240-8), so it runs after both.

Safe to run in parallel if the controller wants to: **V240-1 ∥ V240-3 ∥
V240-4** (disjoint files: vendor/requirements/tests/dev vs styles and
theme-tokens vs theme.service/profile-menu/shell specs, and no contract
between them). Also **V240-10 ∥ V240-11** (spec-only scan vs formatters;
disjoint files), both after V240-9.

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify, D delete) | Symbols for later tasks |
|---|---|---|---|---|---|
| V240-1 | Vendor Jost and pin `tnum` in a Python test | 1 | haiku | C `swingbot/admin/static/vendor/jost/jost-latin-wght-normal.woff2`, C `swingbot/admin/static/vendor/jost/jost-latin-ext-wght-normal.woff2`, C `swingbot/admin/static/vendor/jost/LICENSE.txt`, C `tests/dev/test_vendored_fonts.py`, M `requirements.txt` | `tests/dev/test_vendored_fonts.py` constants `VENDOR = ROOT / "swingbot/admin/static/vendor"`, `JOST_LATIN`, `JOST_LATIN_EXT`; V240-2 adds a "jetbrains-mono is gone" test to this file |
| V240-2 | Jost in `fonts.css` with metric-matched fallbacks; font tokens; JetBrains Mono removed | 1 | sonnet | M `frontend/src/styles/fonts.css`, M `frontend/src/styles/tokens.css`, M `frontend/src/styles.css`, M `frontend/src/app/ui/layout.ts`, M `frontend/src/app/ui/metric-card.ts`, C `frontend/src/app/ui/fonts.spec.ts`, M `frontend/src/app/ui/tokens.spec.ts`, M `tests/dev/test_vendored_fonts.py`, M `tests/charts/resolved_tokens.json`, D `swingbot/admin/static/vendor/jetbrains-mono/` | `--font-sans`, `--font-mono` values (Global Constraints); `.sb-label` keeps `font-family: var(--font-mono)` |
| V240-3 | Doctena night palette: `doctena-*` ramp, the 20-token Navy block, `--control-border`, contrast | 1 | sonnet | M `frontend/src/styles/palette.css`, M `frontend/src/styles/tokens.css`, M `frontend/src/app/ui/testing/theme-tokens.ts`, M `frontend/src/app/ui/tokens.spec.ts`, M `frontend/src/app/ui/contrast.spec.ts`, M `frontend/src/index.html` (the `NAVY_BG` literal only), M `frontend/src/app/ui/primitives.spec.ts` (`--midnight-950` pins and the `HEX_ALLOWLIST` entry only), M `tests/charts/resolved_tokens.json` | `NAVY_TOKENS: readonly string[]` exported from `ui/testing/theme-tokens.ts` (replaces `GROUND_INK_TOKENS`); `--control-border` token (bare `var(--border-strong)`, Navy `var(--doctena-blue-600)`); palette names in Global Constraints |
| V240-3b | Contrast gates for the divider and the control border; tokens.css header names the Navy list | 1 | haiku | M `frontend/src/app/ui/contrast.spec.ts`, M `frontend/src/app/ui/tokens.spec.ts`, M `frontend/src/styles/tokens.css` (header comment only) | none |
| V240-4 | Navy is the default at runtime: `readTheme`, profile menu, shell and palette specs | 1 | sonnet | M `frontend/src/app/ui/theme.service.ts`, M `frontend/src/app/ui/theme.service.spec.ts`, M `frontend/src/app/shell/profile-menu.ts`, M `frontend/src/app/shell/profile-menu.spec.ts`, M `frontend/src/app/shell/shell.spec.ts`, M `frontend/src/app/shell/palette/command-palette.spec.ts`, M `frontend/src/app/ui/chart/trade-chart.spec.ts`, M `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` (theme-storage stubs return `'graphite'`) | `readTheme(storage): Theme` returns `'graphite'` only for `'graphite'`; `ProfileMenu.theme = input<Theme>('navy')` |
| V240-5 | Cold load in Navy: pre-boot script with `GRAPHITE_BG`, static meta, inline ground, web manifest | 1 | sonnet | M `frontend/src/index.html`, M `frontend/public/manifest.webmanifest`, M `frontend/src/app/ui/primitives.spec.ts` | index.html script vars `NAVY_BG = '#00131f'`, `GRAPHITE_BG = '#0d0f12'`; comment phrase `manifest.webmanifest takes the Navy ground` |
| V240-6 | `styleRules` parser; `--control-border` on inputs, selects and segmented controls | 1 | sonnet | C `frontend/src/app/ui/testing/style-rules.ts`, C `frontend/src/app/ui/testing/style-rules.spec.ts`, C `frontend/src/app/ui/control-border.spec.ts`, M `frontend/src/app/ui/form-controls.ts`, M `frontend/src/app/ui/form-controls.spec.ts`, M `frontend/src/app/ui/segmented.ts`, M `frontend/src/app/ui/date-range.ts`, M `frontend/src/app/ui/pagination.ts`, M `frontend/src/app/ui/data-table/data-table.ts` | `export type StyleRule = { selector: string; body: string }`; `export function styleRules(name: string, source: string): StyleRule[]` (`.css` whole file; `.ts` every `styles:` template literal, single or array; `.html` → `[]`; comments stripped; selector trimmed to its last line) |
| V240-7 | Radius tokens, `--pill-radius`, thin bars on pills | 2 | sonnet | M `frontend/src/styles/tokens.css`, M `frontend/src/app/ui/tokens.spec.ts`, M `frontend/src/app/ui/chip.spec.ts`, C `frontend/src/app/ui/radius.spec.ts`, M `frontend/src/app/ui/layout.ts`, M `frontend/src/app/ui/magnitude.ts`, M `tests/charts/resolved_tokens.json`, M `frontend/src/app/ui/testing/style-rules.ts`, M `frontend/src/app/ui/testing/style-rules.spec.ts` (`closingBacktick`: escaped backticks no longer end a styles block), M `frontend/src/app/shell/scan-progress.css`, M `frontend/src/app/ui/chart-tooltip.ts`, M `frontend/src/app/ui/status-cell.ts`, M `frontend/src/app/ui/status-indicator.ts` | `--pill-radius: 999px` |
| V240-8 | Uppercase buttons; −0.02em on headings at `--text-title` and above | 2 | sonnet | M `frontend/src/app/ui/button.ts`, M `frontend/src/app/ui/button.spec.ts`, M `frontend/src/app/ui/page.ts`, M `frontend/src/app/ui/section-head.ts`, M `frontend/src/app/ui/section-head.spec.ts`, M `frontend/src/app/workspaces/gallery/gallery.ts`, M `frontend/src/app/workspaces/plans/plan-detail.ts`, M `frontend/src/app/workspaces/trades/trade-detail.ts`, M `frontend/src/app/workspaces/trades/outcome-strip.ts`, C `frontend/src/app/ui/headings.spec.ts` | none |
| V240-9 | Type gates: `tabular-nums` on numeric rules, no text in `--text-faint` (with pending lists) | 2 | sonnet | C `frontend/src/app/ui/type-gates.spec.ts`, M `frontend/src/app/ui/testing/style-rules.ts`, M `frontend/src/app/ui/testing/style-rules.spec.ts` | `export function withChartChrome(source: string): string` in `ui/testing/style-rules.ts` (V240-10 consumes it); `NUM_FACE = /var\(--font-(?:num|mono)\s*(?:,[^)]*)?\)/` (accepts a fallback; V240-16 reuses it); `TABULAR_PENDING: ReadonlySet<string>` and `FAINT_PENDING: ReadonlySet<string>` (file names relative to `src/`, as `allSources()` names them), consts in `type-gates.spec.ts`; each holds exactly today's offenders; two tests per gate: every file outside the set passes, every file in the set still offends |
| V240-10 | Money-colour scan: nav, brand, active and focus never read `--pos`/`--neg` | 2 | sonnet | C `frontend/src/app/ui/money-colour.spec.ts` (plus any offending rule it finds, swapped to `--accent`) | `NAV_FILES: readonly string[]` const in `money-colour.spec.ts` (plan 3 appends its editor file) |
| V240-11 | True minus I: `fixed()`, `riskPct`, no signed zero in `pct`/`money`/`rMultiple`/`signed`, `metric-card`, `metric-chip`, `plan-cell` `formatR` | 2 | sonnet | M `frontend/src/app/ui/format.ts`, M `frontend/src/app/ui/format.spec.ts`, M `frontend/src/app/ui/status-cell.spec.ts`, M `frontend/src/app/ui/metric-card.ts`, M `frontend/src/app/ui/metric-card.spec.ts`, M `frontend/src/app/ui/metric-chip.ts`, C `frontend/src/app/ui/metric-chip.spec.ts`, M `frontend/src/app/ui/plan-cell.ts`, M `frontend/src/app/ui/plan-cell.spec.ts` | `export function fixed(value: number, decimals: number): string` in `ui/format.ts` (loss → `MINUS` + `abs.toFixed`; gain/zero → no sign; a value that rounds to zero → unsigned zero); `pct`/`money`/`rMultiple`/`signed` print an unsigned zero for a value that rounds to zero (Decision 10) |
| V240-12 | True minus II: `figure-text` count-up, `attribution.ts`, `tape.ts` `signed` | 2 | sonnet | M `frontend/src/app/ui/motion/figure-text.ts`, M `frontend/src/app/ui/motion/figure-text.spec.ts`, M `frontend/src/app/workspaces/analytics/tabs/attribution.ts`, M `frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts`, M `frontend/src/app/shell/tape/tape.ts`, M `frontend/src/app/shell/tape/tape.spec.ts` | none |
| V240-13 | Sweep 1: `app/ui/`, `app/shell/`, `styles.css` | 3 | sonnet | M offending files under `frontend/src/app/ui/`, `frontend/src/app/shell/` and `frontend/src/styles.css` (list in the task), their pinned specs, M `frontend/src/app/ui/type-gates.spec.ts` | removes every `app/ui/`, `app/shell/`, `styles.css` entry from both pending sets |
| V240-14 | Sweep 2: analytics, reports, research, cancels, guide, gallery | 3 | haiku | M offending files under `frontend/src/app/workspaces/{analytics,reports,research,cancels,guide,gallery}/` (list in the task), their pinned specs, M `frontend/src/app/ui/type-gates.spec.ts` | removes those entries |
| V240-15 | Sweep 3: dashboard, calendar, trades, plans, risk | 3 | haiku | M offending files under `frontend/src/app/workspaces/{dashboard,calendar,trades,plans,risk}/` (list in the task), their pinned specs, M `frontend/src/app/ui/type-gates.spec.ts` | removes those entries |
| V240-16 | Sweep 4: system, versions, watchlist; pending lists deleted | 3 | haiku | M offending files under `frontend/src/app/workspaces/{system,versions,watchlist}/` (list in the task), their pinned specs, M `frontend/src/app/ui/type-gates.spec.ts`, M `frontend/src/app/ui/contrast.spec.ts` (`V186_FILES` comment: the faint gate now covers all text) | `TABULAR_PENDING`/`FAINT_PENDING` and their "still offends" tests deleted; both gates now run with no exemptions |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-23-v240-doctena-night-theme-and-type_1-fonts-and-colours.md` | V240-1..V240-4 (with V240-3b) | Jost vendoring and `tnum` test, fonts.css and font tokens, JetBrains Mono removal, the doctena palette and Navy block, the default flip at runtime |
| 1b | `2026-11-23-v240-doctena-night-theme-and-type_1b-cold-load-and-controls.md` | V240-5..V240-6 | The Navy default at cold load, `styleRules` and the `--control-border` readers |
| 2 | `2026-11-23-v240-doctena-night-theme-and-type_2-shapes-and-rules.md` | V240-7..V240-10 | Radius tokens and pills, uppercase buttons and heading tracking, the type and money-colour gates |
| 2b | `2026-11-23-v240-doctena-night-theme-and-type_2b-true-minus.md` | V240-11..V240-12 | `fixed()` and the seven true-minus sites |
| 3 | `2026-11-23-v240-doctena-night-theme-and-type_3-type-sweeps.md` | V240-13..V240-16 | The four area sweeps that empty the type gates' pending lists |

Offender snapshot for the part 3 writer (scan at `ff4f6025`, rough parser;
V240-9's `styleRules` count is authoritative). The `tabular-nums` scan
found 67 rules in 39 files (with Decision 11's fallback-aware `NUM_FACE`;
`calendar.ts`'s `.trade-id` is the 67th) and the `--text-faint` text scan found 97 reads
in 46 files. Per-file detail is in the brief §4. The faint files are
`shell/breadcrumb`, `ui/{age-hint, bar-list, button, column-picker,
direction-arrow, freshness, market-value, matrix, metric-chip, plan-cell,
pnl-basis, share-bar, status-cell}`, `analytics/tabs/{benchmark, execution,
override-fidelity-panel, overview, partials, pipeline, runner-endings,
variance-band-panel}`, `calendar/calendar`, `cancels/cancels-summary`,
`dashboard/{dashboard, panels/equity-candles, panels/exposure-by-horizon,
panels/market-movers, panels/recent-activity, panels/watchlist-panel}`,
`guide/guide`, `plans/plan-detail`, `reports/{attribution-tab, gates-tab,
reports}`, `research/research`, `risk/risk`, `system/{logs-tab, scan-tab,
settings-tab}`, `trades/{trade-detail, trades, why/outcome-path}`,
`versions/versions` and `watchlist/{earnings-calendar, watchlist}`.

## Handoff

- Known gap, accepted: Black's `--control-border` (`--border-strong`,
  about 1.5:1) stays under 3:1. The spec keeps Black's colours, so the gate
  is Navy-only (Decision 1). A later spec may lift it.
- Plan 3 must append its tab-bar editor file to `NAV_FILES` in
  `ui/money-colour.spec.ts`.
- Guide chapters: nothing in `docs/guide/` names a theme or font today. The
  close-out records `guide: no reader-visible change` unless a chapter's
  `sources:` touches these files (`scripts/dev/guide_sources.py`).
