# v225 — Dark blue theme beside Graphite, picked per browser (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v225 — Dark blue theme: a second ground beside Graphite, picked per browser](../specs/2026-11-10-v225-dark-blue-theme-design.md) (all sections; § Decisions are the partner's and are not reopened here)

## Goal

The admin SPA has one look today, Graphite: a neutral near-black ground with
grey inks (v195 §1.1). The partner spends long sessions in it and wants a
second, dark blue ground to choose instead, because one or the other is
easier on the eyes depending on the day and the room. Nothing about the
data, the alerts, the trading or the Discord images changes. It is a colour
preference, and it is kept per browser, not per account.

Once this plan ships, every admin user sees a new control: an icon button
in the top bar on tablet and desktop, and a "Theme" row (Black | Dark blue)
in the profile menu on every device, which is the only switch on a phone.
A browser that never chose stays on Black, so nobody's screen changes until
they flip it. Choosing Dark blue repaints the whole SPA at once, charts
included, with no reload, and a cold load in Dark blue never flashes black
because a small inline script applies the stored choice before the first
paint.

The idea is a second tier-1 palette (`--midnight-*` grounds, `--frost-*`
inks) and one tier-2 block, `:root[data-theme="navy"]`, that re-points
exactly the eleven ground and ink tokens to it. Everything that already
reads `var(--…)` follows the attribute for free. The valence colours
(green, red, amber, violet, the steel accent), the chart series and the
quality colours are shared by both themes, so a gain, a loss or a warning
reads the same in either. A `ThemeService` modelled on `DensityService`
owns the attribute and the `ui.theme` key in localStorage. The two
lightweight-charts hosts, which read token strings once at creation, learn
to re-apply their options when the theme signal moves.

It leaves alone: the Discord chart PNGs (`chart_style.THEME`,
`STYLE_VERSION` and every existing key of `tests/charts/resolved_tokens.json`
keep their values; the fixture only gains the eleven raw palette names),
the PWA manifest and favicons (Graphite), every Jinja page, the account
preferences store, and any light theme or `prefers-color-scheme` hook.

Success is measured by the tests each task adds (token re-points, contrast
gates run once per theme, a Discord-parity test proving the Navy block is
invisible to `dump_tokens.py`, the cold-load copy pinned to the resolved
Navy `--bg`, the service, the controls, the chart refresh), by
`layout-audit.mjs` exiting 0 at 390, 768 and 1440 in **both** themes with
the open profile menu covered at 390, and by Playwright screenshots of the
Dashboard equity candles at 390 and 1440 in each theme, taken after
toggling with the chart mounted, attached to the implementation's review.

## Architecture

- **Tier 1 (`frontend/src/styles/palette.css`):** eleven new entries in the
  existing bare `:root`: `--midnight-950/900/850/800/750/700/500`,
  `--midnight-950-a72`, `--frost-100/300/400`. The names avoid the Arctic
  Navy guard (`--navy-N`/`--slate-N`/`--sky-N`/`--teal-N`).
- **Tier 2 (`frontend/src/styles/tokens.css`):** one block
  `:root[data-theme="navy"] { … }`, `var()` references only, placed after
  the tier-2 `:root` and the density `@media`, before the tier-3 banner.
  Both resolvers (`scripts/dev/dump_tokens.py`,
  `frontend/src/app/ui/testing/resolve-token.ts`) read only blocks whose
  selector is exactly `:root`, so the jsdom fixture and the Discord parity
  stay Graphite. A test-only helper (`ui/testing/theme-tokens.ts`) layers
  the Navy block for the contrast and token specs.
- **State (`frontend/src/app/ui/theme.service.ts`):** signal
  `theme(): Theme`, `set()`, `toggle()`; storage behind `THEME_STORAGE`
  (guarded localStorage, key `ui.theme`); writes
  `document.documentElement.dataset.theme` and the `theme-color` meta
  (read back from the computed `--bg`, never a TS literal); instantiated at
  boot by `provideAppInitializer` beside `DensityService`.
- **Pre-paint (`frontend/src/index.html`):** an inline `<script>` between
  the `theme-color` meta and the inline `<style>`, one literal
  (`var NAVY_BG = '#070c18';`), applying `data-theme="navy"`, the meta and
  a `html[data-theme="navy"]`-scoped ground rule when `ui.theme` is
  exactly `navy`.
- **Controls:** bar button in `shell.html` (not rendered when `isPhone()`),
  "Theme" segmented row in `profile-menu.ts` (input/output bound in the
  shell, same pattern as Density), one "Switch theme" palette command. All
  three write through the one `ThemeService`.
- **Charts:** `trade-chart.ts` (with `price-pane.ts` and the legend
  primitive) and `equity-candles.ts` gain an effect on `theme()` that
  re-reads `chartPalette()` and re-applies chart, series and primitive
  colours. CSS/SVG charts need nothing.
- **Audit:** `layout-audit.mjs` gains `--theme graphite|navy` (seeded into
  localStorage before load) and an open-profile-menu check at phone widths.

**Tech stack:** Angular (standalone components, signals, zoneless), Vitest
via `frontend/scripts/ng-test.mjs`, lightweight-charts, `node:test` for the
audit lib, Playwright for the audit and screenshots, Python 3.11 + pytest
for the dump/parity test.

## Global Constraints

- Navy values, exactly (spec § Palette): `--midnight-950 #070c18` (`--bg`), `--midnight-900 #0c1424` (`--surface`), `--midnight-850 #121c32` (`--surface-raised`), `--midnight-800 #172440` (`--surface-overlay`), `--midnight-750 #182540` (`--border`), `--midnight-700 #233453` (`--border-strong`), `--midnight-500 #5f6f8a` (`--text-faint`), `--midnight-950-a72 rgba(7, 12, 24, 0.72)` (`--overlay-dim`), `--frost-100 #e6ecf5` (`--text`), `--frost-300 #c9d4e3` (`--text-secondary`), `--frost-400 #9fb0c8` (`--text-muted`).
- The ground/ink list is closed and named: `--bg`, `--surface`, `--surface-raised`, `--surface-overlay`, `--overlay-dim`, `--border`, `--border-strong`, `--text`, `--text-secondary`, `--text-muted`, `--text-faint`. Every one has a Navy re-point; no other token is re-pointed. Graphite values do not change.
- `<html data-theme="navy">` is Dark blue; no attribute or any other value is Graphite. Storage key `ui.theme`, values `graphite` | `navy`; anything else reads as `graphite` and is not rewritten until the user chooses.
- User-facing copy, exactly: bar button `aria-label` and hint "Dark blue theme" (fixed, the state is `aria-pressed`); profile-menu row label "Theme" with segments "Black" | "Dark blue"; palette command "Switch theme".
- No colour literal in any `.ts`/`.html` under `frontend/src` outside `styles/` (`primitives.spec.ts` gate). `index.html` carries exactly three literals in order: Graphite meta, Navy script variable, Graphite inline style.
- `scripts/dev/dump_tokens.py` and `resolve-token.ts` keep their logic and stay line-for-line twins; neither gains a theme argument. `chart_style.THEME`, `STYLE_VERSION` and the existing keys of `tests/charts/resolved_tokens.json` do not change; the fixture gains exactly the eleven `midnight-*`/`frost-*` keys, regenerated by `python scripts/dev/dump_tokens.py`, never hand-edited.
- `frontend/public/manifest.webmanifest` stays Graphite. No Jinja template changes.
- Three-device rule (`docs/claude/ui-design.md`): bar button only at tablet and desktop, 44px hit area via `sb-hit`; the menu row's segments are at least 44px wide on touch/narrow screens; checked at 390, 768 and 1440 in both themes.
- No new text in `--text-faint`. No new contrast gate for `--neg` on `--neg-soft` over `--surface-overlay` (4.48:1 in both themes, recorded by the spec, out of scope).
- Per-task verification is the narrow run: `node frontend/scripts/ng-test.mjs frontend --include <spec>`, `node --test frontend/scripts/layout-audit-lib.test.mjs`, `python scripts/dev/testrun.py file <test>`. **No task runs the full suite; CI does after the push.**
- Any spec that mounts the shell, the palette or `ThemeService` provides a fake `THEME_STORAGE` (or clears `ui.theme`) and deletes `document.documentElement.dataset['theme']` in `afterEach`, the same hygiene as the density specs.
- Specs read files from `process.cwd()` (`frontend/`), never `?raw` or `import.meta.url`.
- Implementation runs in worktree `.claude/worktrees/2026-11-10-v225-dark-blue-theme` (branch of the same name). Name it in every dispatch. Nothing reaches `main` except through V225-13's merge, after the partner's yes.
- Commit messages are one subject line, no body and no attribution trailer. Several scoped commits, never one big one.
- Bot version unchanged (`VERSION.json` `bot` stays); ui gets one minor bump in V225-13.

## Review Focus

1. **Toggling with a chart on screen.** A user flips the theme while a trade chart or the Dashboard equity candles are mounted and expects the chart ground, grid, axis text, legend box and seam label to change at once. Pinned by V225-9 (trade chart: `applyOptions` with the new `--surface`, legend palette replaced) and V225-10 (equity candles: chart options, candle series, baseline and seam colours re-applied), and checked by V225-12's screenshots.
2. **Storage that throws or holds junk.** Private mode, a blocked localStorage, or a stale value such as `NAVY` or `"navy "`: the page is Graphite, nothing throws, a choice made on the page holds for its life, and the junk is not rewritten. Pinned by V225-3 (service) and V225-4 (the pre-paint script only acts on exactly `navy` and swallows errors).
3. **Two switches disagreeing.** The bar button, the menu row and the palette command must always show the same state. Pinned by V225-7's shell spec (bar toggle moves the open menu's pressed segment, and the menu moves the bar's `aria-pressed`) and V225-8 (palette command toggles through the same service).
4. **Toggling back to Black after a Dark blue cold load.** The pre-paint ground rule must stop applying once `data-theme` changes, or the body stays navy under a Graphite UI. Pinned by V225-4 (the injected rule is scoped to `html[data-theme="navy"]`) and V225-3 (the service always writes the attribute).
5. **The phone's only switch overflowing.** At 390px the open profile menu with the Theme row must sit inside the viewport with 44px segments. Pinned by V225-7 (touch-width CSS rule extended to `.theme-control`) and V225-11/V225-12 (audit opens the menu at phone widths in both themes).

## Parallelisation

| Group | Tasks | Why this order |
|---|---|---|
| A | V225-1 → V225-2 | V225-2 consumes V225-1's `theme-tokens.ts` helper and edits `resolve-token.ts` after it (same file). |
| B | V225-3 | Disjoint files (`theme.service.ts`, its spec, `app.config.ts`); no dependency on A (its spec injects its own `--bg` style). May run beside V225-1. |
| C | V225-5 | Disjoint (`icon.ts`, `icon.spec.ts`). May run beside anything. |
| D | V225-4 | Needs V225-1 (`--midnight-950` resolvable) and V225-3 (`THEME_PREF_KEY`). Edits `index.html` and `primitives.spec.ts` only. |
| E | V225-6 → V225-7 | Both edit `shell.html` and `shell.spec.ts` (same files: sequential). V225-6 needs V225-3 and V225-5; V225-7 needs V225-6. |
| F | V225-8 | Needs V225-3. Disjoint palette files; may run beside E. |
| G | V225-9, V225-10 | Each needs V225-3; disjoint files (`ui/chart/*` vs `equity-candles.*`); may run in parallel with each other and with E/F. |
| H | V225-11 | Disjoint audit scripts; no contract with the SPA beyond the class names `sb-profile-menu .avatar` and `.theme-control .segment` fixed in the ledger. May run any time. |
| I | V225-12 → V225-13 | Sequential edge on everything: the audit runs and screenshots need every control and chart task merged into the worktree branch; the release needs V225-12 green. |

At most 2 implementers at once (`CLAUDE.md`). Suggested waves: (V225-1 ∥ V225-3), (V225-2 ∥ V225-5), (V225-4 ∥ V225-11), (V225-6 ∥ V225-8), (V225-7 ∥ V225-9), V225-10, V225-12, V225-13.

## Task ledger

| Id | Title | Part | Model | Files created / modified | Symbols for later tasks |
|---|---|---|---|---|---|
| V225-1 | Midnight/frost palette, the Navy tier-2 block, fixture regeneration, token pins | 1 | sonnet | M `frontend/src/styles/palette.css`; M `frontend/src/styles/tokens.css` (header rewrite + `:root[data-theme="navy"]` block); M `tests/charts/resolved_tokens.json` (regenerated); M `frontend/src/app/ui/testing/resolve-token.ts` (`export` on `topLevelBlocks`, `declarations` only); C `frontend/src/app/ui/testing/theme-tokens.ts`; M `frontend/src/app/ui/tokens.spec.ts` (new `v225: the Navy ground` describe) | tier-1 `--midnight-950/900/850/800/750/700/500`, `--midnight-950-a72`, `--frost-100/300/400`; selector `:root[data-theme="navy"]`; `theme-tokens.ts`: `export type TokenTheme = 'graphite' \| 'navy'`, `export const TOKEN_THEMES: readonly TokenTheme[]`, `export const GROUND_INK_TOKENS: readonly string[]` (the eleven, `--` prefixed), `export function navyRepoints(css?: string): Record<string, string>` (`'--bg' -> 'var(--midnight-950)'`), `export function resolveTokenIn(theme: TokenTheme, name: string): string` |
| V225-2 | Contrast gates per theme, resolver pairing notes, Discord parity test | 1 | sonnet | M `frontend/src/app/ui/contrast.spec.ts`; M `frontend/src/app/ui/testing/resolve-token.ts` (docblock +1 line); M `scripts/dev/dump_tokens.py` (docstring +1 line); M `tests/dev/test_dump_tokens.py` | pytest `test_navy_block_is_invisible_to_the_discord_fixture`, `test_parse_root_skips_the_navy_selector` |
| V225-3 | `ThemeService`: signal, guarded storage, attribute, `theme-color` meta, boot | 1 | sonnet | C `frontend/src/app/ui/theme.service.ts`; C `frontend/src/app/ui/theme.service.spec.ts`; M `frontend/src/app/app.config.ts` | `export type Theme = 'graphite' \| 'navy'`; `export const THEME_PREF_KEY = 'ui.theme'`; `export interface ThemeStorage { get(key: string): string \| null; set(key: string, value: string): void }`; `export const THEME_STORAGE: InjectionToken<ThemeStorage>`; `export function readTheme(storage: ThemeStorage): Theme`; `@Injectable({ providedIn: 'root' }) export class ThemeService { readonly theme: Signal<Theme>; set(theme: Theme): void; toggle(): void }` (always writes `dataset['theme']` = current value) |
| V225-4 | Pre-paint script in `index.html`, colour-gate allow-list, cold-load pins | 1 | sonnet | M `frontend/src/index.html`; M `frontend/src/app/ui/primitives.spec.ts` (`HEX_ALLOWLIST` + comment, cold-load describe) | literal `var NAVY_BG = '#070c18';` in the inline script; injected rule scoped to `html[data-theme="navy"]` |
| V225-5 | `theme` icon glyph | 1 | haiku | M `frontend/src/app/ui/icon.ts`; M `frontend/src/app/ui/icon.spec.ts` | `IconName` `'theme'` (in `ICON_NAMES`, `PATHS`, `LABELS` = `'Theme'`) |
| V225-6 | Top-bar theme button (tablet/desktop) with a visible pressed state | 1 | sonnet | M `frontend/src/app/shell/shell.html`; M `frontend/src/app/shell/shell.ts`; M `frontend/src/app/shell/shell.css`; M `frontend/src/app/shell/shell.spec.ts` (desktop bar order pin ~l.1317) | `Shell.theme = inject(ThemeService)` (protected); bar element `button.theme-toggle` between `button.palette-trigger` and `sb-profile-menu`, `aria-label="Dark blue theme"`, `[attr.aria-pressed]` |
| V225-7 | Profile-menu "Theme" row on every device, bound through the shell | 2 | sonnet | M `frontend/src/app/shell/profile-menu.ts`; M `frontend/src/app/shell/profile-menu.spec.ts`; M `frontend/src/app/shell/shell.html` (`[theme]`/`(themeChanged)` bindings); M `frontend/src/app/shell/shell.spec.ts` | `ProfileMenu.theme = input<Theme>('graphite')`; `ProfileMenu.themeChanged = output<Theme>()`; `THEME_OPTIONS: SegmentOption[]` (`graphite`→"Black", `navy`→"Dark blue"); element `sb-segmented.theme-control` in `.theme-row` |
| V225-8 | "Switch theme" command in the palette | 2 | sonnet | M `frontend/src/app/shell/palette/palette-items.ts`; M `frontend/src/app/shell/palette/palette-items.spec.ts`; M `frontend/src/app/shell/palette/command-palette.ts`; M `frontend/src/app/shell/palette/command-palette.spec.ts` | `PaletteItem.action?: 'toggle-theme'`; item `{ key: 'pref:theme:toggle', group: 'preferences', label: 'Switch theme', sub: 'Black or Dark blue', route: null, action: 'toggle-theme' }` |
| V225-9 | Trade chart follows the theme (options, price pane, legend) | 2 | sonnet | M `frontend/src/app/ui/chart/trade-chart.ts`; M `frontend/src/app/ui/chart/price-pane.ts`; M `frontend/src/app/ui/chart/primitives/legend-primitive.ts`; M `frontend/src/app/ui/chart/trade-chart.spec.ts` (+ the legend primitive's spec if one exists) | `export function applyPricePanePalette(pane: PricePane, palette: ChartPalette): void`; `LegendPrimitive.setPalette(palette: ChartPalette): void` |
| V225-10 | Dashboard equity candles follow the theme | 2 | sonnet | M `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`; M `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` | — |
| V225-11 | Layout audit: `--theme` switch and the open profile menu at phone widths | 2 | sonnet | M `frontend/scripts/layout-audit-lib.mjs`; M `frontend/scripts/layout-audit.mjs`; M `frontend/scripts/layout-audit-lib.test.mjs` | `parseArgs(argv).theme: 'graphite' \| 'navy'` (default `'graphite'`; `--theme <x>` throws `unknown theme <x>` otherwise); `export const THEME_KEY = 'ui.theme'`; screenshots/out names carry a `-navy` suffix under Navy |
| V225-12 | Both-theme layout audit at 390/768/1440 and the canvas screenshots | 2 | sonnet | none planned (fixes, if any, go in the owning task's files as scoped commits) | screenshots under `.superpowers/v225-shots/` (gitignored), listed for the review |
| V225-13 | Release (ui minor), version history, partner gate, merge, CI watch | 2 | sonnet | M `VERSION.json` (`ui` minor only); M `swingbot/admin/version_history.json` (regenerated) | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-11-10-v225-dark-blue-theme_1-palette-service-bar.md`](2026-11-10-v225-dark-blue-theme_1-palette-service-bar.md) | V225-1..V225-6 | Palette and Navy block with fixture and token/contrast/parity tests; `ThemeService`; pre-paint and colour gate; icon; the top-bar button |
| 2 | [`2026-11-10-v225-dark-blue-theme_2-menu-charts-release.md`](2026-11-10-v225-dark-blue-theme_2-menu-charts-release.md) | V225-7..V225-13 | Profile-menu row, palette command, chart refresh, layout-audit switch, both-theme audit and screenshots, release |

## Notes for part writers

- **V225-1:** `tokens.css` header (l.1-17) is rewritten: both themes are dark, still no light theme and no `prefers-color-scheme`, `data-theme` exists for the ground only (spec v225), and the standing rule names the ground/ink list (a future ground or ink token gets its Navy value in the same commit). Keep the `--text-faint … rule and divider` comment that `contrast.spec.ts` regexes. `tokens.spec.ts` checks both ways: `Object.keys(navyRepoints())` sorted equals `GROUND_INK_TOKENS` sorted; each value is `var(--midnight-*|--frost-*)` per the table; `resolveTokenIn('navy', t)` equals the table hex; the block holds no hex/`rgb(`; `resolveToken` (Graphite) values unchanged; the Arctic Navy guard still passes. Run `python scripts/dev/dump_tokens.py` then `--check`, and `resolve-token.spec.ts` ("reproduces the committed fixture").
- **V225-2:** `contrast.spec.ts` wraps every existing theme-dependent describe in `for (const theme of TOKEN_THEMES)` using `resolveTokenIn(theme, …)` with the theme in each test name; the source-scan describe runs once. The Python parity test runs `dt.resolve_tokens` on tmp copies of `palette.css` + `tokens.css` with and without the Navy block (strip it by regex) and asserts equal dicts; both pairing comments gain one line: "The `[data-theme]` blocks are deliberately invisible here; never teach this resolver a theme (v225)".
- **V225-3:** mirror `density.service.ts` / its spec. `apply()` order: write `dataset['theme']`, then read `getComputedStyle(root).getPropertyValue('--bg').trim()` and, when a `meta[name="theme-color"]` exists and the value is non-empty, set its `content`. Spec creates/removes that meta and injects `<style>:root[data-theme="navy"]{--bg:<midnight-950 via resolveTokenIn>}</style>` to observe the swap. Doc comment cites spec v225 for why localStorage, not `PreferencesStore`. Boot check reads `app.config.ts` for `inject(ThemeService)` inside `provideAppInitializer`.
- **V225-4:** the script sits after the `theme-color` meta and before the `<style>` comment block; it checks `localStorage.getItem('ui.theme') === 'navy'` inside `try { } catch (e) { }`, sets the attribute, the meta and appends a `<style>` with `html[data-theme="navy"], html[data-theme="navy"] body { background: ' + NAVY_BG + '; }`. Keep the exact shapes the existing regexes match. The comment by the cold-load copies says the manifest stays Graphite (a Dark blue home-screen splash is black for an instant, accepted, spec v225). Tests: allow-list `['#0d0f12', '#070c18', '#0d0f12']`; `NAVY_BG` equals `resolveToken('--midnight-950')` and `resolveTokenIn('navy', '--bg')`; the script precedes the `<style>`, names `THEME_PREF_KEY`, compares with `=== 'navy'`; the manifest still equals Graphite `--bg`.
- **V225-6:** button `sb-button variant="icon"`, classes `theme-toggle sb-hit`, an `<sb-hint>` anchored to it with text "Dark blue theme", inside an `@if (!isPhone())` after the search `@if/@else` and before `<sb-profile-menu>`. Pressed CSS: `.theme-toggle[aria-pressed="true"] { color: var(--accent); background: var(--accent-soft); }`. Specs: desktop order pin gains `button.theme-toggle`; phone order pin unchanged and `button.theme-toggle` absent; click flips `aria-pressed`, `html.dataset['theme']` and the fake storage's `ui.theme`.
- **V225-7:** row after the Density row, before Sign out; same `.motion-row, .density-row` layout and the touch `min-width: 44px` rule extended to `.theme-control .segment`. No "Desktop only" note. Shell spec: menu row sets the theme; bar toggle while the menu is open moves its pressed segment and the reverse.
- **V225-8:** update the pins named in the brief: `PREFERENCE_ITEMS` map, allowed keys (+`action`), the "route or density" invariant (+`action`), the injected-services list in `command-palette.spec.ts` (+`ThemeService`), and confirm `type 'dense'` still lists only `Density: Dense`. `choose()`: `action === 'toggle-theme'` → `theme.toggle()`, then close.
- **V225-9 / V225-10:** jsdom resolves `token()` against the flat Graphite fixture, so specs inject `<style>:root[data-theme="navy"]{--surface:#0c1424; …}</style>` (removed in `afterEach`), set the theme through a `ThemeService` with fake storage, `await` a settle, and assert the spied `applyOptions` received `#0c1424` as the layout background (read the exact option path from `chartOptions`). `vline-primitive.ts` needs no change: its colours come from the host's `setLine` spec, which V225-10 re-issues.
- **V225-11:** seed in `withContext` via `context.addInitScript` writing `ui.theme` to the chosen theme every run (the persistent profile may hold the other value). Profile-menu check at widths < 640: click `sb-profile-menu .avatar`, wait for `[role=menu]`, fail when its box leaves the viewport or a `.theme-control .segment` is under 44px wide, screenshot it.
- **V225-12:** needs a local admin + dev server with `.env` credentials loaded inside the script and never printed (`CLAUDE.md`). Run the audit six times (3 widths × 2 themes, or one run per theme with `--widths 390,768,1440`) to exit 0; take the four equity-candles screenshots with a scratch Playwright script under the session scratchpad (390/1440 × Black/Dark blue, toggled through the bar button or menu row after the chart has mounted). Any finding is fixed in the owning file with a scoped commit, then the run repeats.
- **V225-13:** mirror v217's `V217-6` release shape, adapted: preconditions, narrow verification of every touched spec/test, **ui minor** bump only (minor + 1, patch 0; bot unchanged), `build_version_matrix.py` regeneration and its test, `AskUserQuestion` deploy gate, merge via `worktree-lifecycle`, push, `gh run watch` in the background, read-only check that production serves the new bundle. Commit subjects only.
