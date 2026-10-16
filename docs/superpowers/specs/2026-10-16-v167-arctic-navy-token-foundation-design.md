# v167 — Arctic Navy token foundation: three-tier tokens, refined-terminal geometry, chart lockstep

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot patch. Every admin screen changes colour and geometry. The Discord chart PNGs change colour, but the bot's behaviour does not.
**Edge:** none (integrity). This is a visual and maintainability change. It touches no signal, threshold, plan, sizing or badge.
**Screen:** exempt (integrity)
**Panel:** senior-engineer, staff-engineer
**Status:** spec written 2026-10-16 from a brainstorm with the partner. Direction, palette and approach were approved in chat, and the palette was picked from live mockups in the visual companion. Revised the same day after the panel (see `## Panel review`). This is the first of three specs: **v167 Foundation → v168 Motion system → v169 Polish sweep**, run in that order.

## Why

The partner asked for a more elegant, more professional dark theme that stays blue, set by global rules so that one change reaches every screen, with a more centralized CSS configuration.

The admin (`frontend/`, Angular 21) already has a single token file, `frontend/src/styles/tokens.css`, which about 100 components consume through `var(--…)`. Three things stand in the way of the request:

1. **There is no palette layer.** Semantic tokens (`--surface`, `--accent`) hold raw hex directly. Changing "the blue" means editing meaning-level tokens one by one.
2. **There is no component layer.** "How a panel looks" (background, border, radius, shadow) is spelled out again in each component's `styles:`.
   - About 44 `var(--radius)` call sites and 12 `var(--radius-chip)` call sites share one 2px value, whether the element is a panel, a control or a 3px-high bar.
   - About 18 further sites hard-code `border-radius: <n>px`.
3. **The current look is a deliberate "pro terminal".** Spec v80 D1 ("TradingView Blue", `#2962ff`), 2px corners (v80 D3), and v18's "one shadow, overlays only" elevation rule all produce it. The partner chose a **refined terminal** instead: keep the density and the data-first layout, but soften the geometry and use a richer navy palette.

## Decisions taken in the brainstorm

| # | Question | Answer |
|---|---|---|
| D1 | How far from the dense terminal look? | **Refined terminal.** Density stays. Radii go to 6–8px, borders become blue-tinted hairlines, panels get soft elevation and a subtle gradient. |
| D2 | Do the Discord chart PNGs follow? | **Yes, in lockstep.** One palette everywhere. |
| D3 | Which palette? | **B · Arctic Navy**: near-black navy with an icy sky-blue accent (picked from three live mockups). |
| D4 | How to centralise? | **Approach A**: three tiers of tokens (palette → semantic → component) plus gates. SCSS was rejected because runtime theming needs custom properties anyway. An in-place re-skin was rejected because it centralises nothing. |
| D5 | Scope | Split into three specs. This one covers tokens, palette, geometry, chart lockstep and gates. Motion is v168, and the per-workspace sweep is v169. |

## Design

### 1. Three tiers

```
frontend/src/styles/
  palette.css    tier 1 -- raw named colours. THE ONLY FILE WITH HEX (one exception, below).
  tokens.css     tier 2 -- semantic (--bg, --accent, --pos ...), each var(--palette-name)
                 tier 3 -- component tokens (--panel-*, --control-*, --chip-*, --radius-sm, --glow-*)
  fonts.css      unchanged
```

`styles.css` imports `palette.css` before `tokens.css`. Tier 3 lives at the bottom of `tokens.css` under its own banner rather than in a fourth file. It is short, and keeping it beside tier 2 keeps the "what does a panel look like" answer one file away from "what does surface mean".

**Exception, kept from today:** `--chart-1…6` and `--quality-4` stay **literal hex inside `tokens.css`**. `line-chart.ts` reads them through `getComputedStyle` under jsdom, which does not resolve a nested `var()`. `chart-palette.spec.ts` also parses the file as text. The colour gate (§5) allow-lists exactly these seven names.

**One shared token resolver for the specs.** `contrast.spec.ts:8-10`, `chart-palette.spec.ts:7-11` and `tests/charts/test_chart_theme.py:_tokens()` each match only `--name: #hex;` in `tokens.css`. Once tier 2 is `var(--palette-x)`, all three throw. The fix is one helper per language:
- `frontend/src/app/ui/testing/resolve-token.ts`, which reads `palette.css` and `tokens.css` and follows `var()` hops until it reaches a literal;
- a matching `_resolve()` in `test_chart_theme.py`.

Both vitest specs import the TS helper. Nobody keeps a private copy.

**The two resolvers are tested against each other.**
- The TS spec writes nothing.
- Instead, a committed fixture `tests/charts/resolved_tokens.json` lists every token name → resolved hex.
- Both `resolve-token.spec.ts` and `test_chart_theme.py` assert that their own resolver reproduces that fixture exactly.
- Regenerating the fixture is a one-line script, `scripts/dev/dump_tokens.py`.
- So a resolver drift in either language, or a token edit without regenerating, fails a test.

**Test selection follows the new file.** `scripts/dev/select_tests.py:222-225` `ESCALATE_PREFIXES` (and `testrun.py:118`) name only `frontend/src/styles/tokens.css`. The same commit that creates `palette.css` widens the prefix to `frontend/src/styles/`. Otherwise a palette-only edit under `testrun.py fast` would skip the slow-tier `test_chart_theme.py` (`pytestmark = slow`, line 22), and the PNG lockstep could drift unnoticed.

### 2. Arctic Navy palette (tier 1 values, tier 2 mapping)

| Semantic token | Before | After | Worst-case contrast (vs the four surfaces) |
|---|---|---|---|
| `--bg` | `#0c0f16` | `#070b14` | — |
| `--surface` | `#131722` | `#0c1320` | — |
| `--surface-raised` | `#1c212d` | `#121b2d` | — |
| `--surface-overlay` | `#242936` | `#1a2540` | — |
| `--overlay-dim` | `rgba(12,15,22,.72)` | `rgba(7,11,20,.72)` | — |
| `--border` | `#2a2e39` | `#1d2940` | — |
| `--border-strong` | `#363a45` | `#2a3a58` | — |
| `--text` | `#d9dce4` | `#e8eef8` | 13.03:1 |
| `--text-secondary` | `#9ea2ad` | `#b3bfd3` | 8.18:1 |
| `--text-muted` | `#9195a0` | `#8f9db5` | 5.54:1 (gate 4.5) |
| `--text-faint` (divider only) | `#4e5361` | `#3a4a66` | ~2:1, never text |
| `--accent` | `#5593ff` | `#7cc4ff` | 8.10:1 |
| `--accent-fill` | `#2962ff` | `#1c6dd0` | `--on-accent` white 5.06:1 |
| `--accent-fill-hi` (new, gradient top stop) | — | `#2474d2` | white 4.66:1. That is a thin margin, so the gate checks this stop explicitly. |
| `--pos` | `#17c98e` | `#3ddc97` | 8.59:1 |
| `--neg` | `#ff5470` | `#ff6f7d` | 5.66:1 |
| `--warn` | `#ffb43d` | `#ffc266` | 9.52:1 |
| `--info` | `#b39ddb` | `#c3a6ff` | 7.39:1 |
| `--pos-soft`, `--neg-soft`, `--warn-soft` | 12% | 12% of the new hue | — |
| `--info-soft` | 14% | 14% of the new hue | — |
| `--accent-soft` | 18% of `--accent-fill` | **18%** of the new `--accent-fill` (unchanged alpha; the brainstorm mockup's 16% was a mockup value) | — |
| `--quality-4` | `#9acd32` | unchanged | — |
| `--chart-1…6` | — | **unchanged** | — |

Notes on the table:
- **The contrast figures** were computed during the brainstorm and re-derived independently by the panel. `contrast.spec.ts` is the gate that must agree with them.
- **The `--chart-1…6` floor holds on `--surface` only.** They are ≥ 4.82:1 there, but on `--surface-overlay` chart-6 is 3.94:1 and chart-3 is 4.14:1. Chart series render on `--surface` (`chart-container.ts`, the PNG `CHART_BG`), and **a series colour on `--surface-overlay` (e.g. a tooltip swatch) carries no text**. `chart-palette.spec.ts` re-validates OKLCH band and ΔE against the new `--surface`, and a failure there reopens this table rather than loosening the gate.
- **The perceptual margins are thin but pass.** The panel measured `--info` vs chart-3 at ΔE 15.7, `--text-muted` vs chart-5 at ΔE 10.1 (the `KC_COLOR` / `TRENDLINE_SUPPORT_COLOR` pair in `test_chart_theme.py`), and the nearest chart colour to the new pos/neg at ΔE 14.5 (chart-2 vs neg). They are recorded so a later tweak knows how little room there is.

The valence rule (one hue = one meaning; a sixth hue is a review defect) is **unchanged**. The palette swaps values only.

### 3. Geometry and elevation (tier 3)

```css
--panel-radius: 8px;            /* panels, cards, drawers' inner sections, dialogs */
--control-radius: 6px;          /* buttons, inputs, selects, segmented controls */
--chip-radius: 999px;           /* pills */
--radius-sm: 2px;               /* thin bars, cells, swatches, tracks: anything under ~12px tall */

--panel-bg: linear-gradient(180deg, var(--surface-raised), var(--surface));
--panel-border: 1px solid var(--border);
--panel-shadow: inset 0 1px 0 rgba(255,255,255,.03), 0 6px 18px rgba(0,0,0,.25);
--panel-inner-bg: var(--surface-raised);   /* a panel nested in a panel: flat, no gradient */
--panel-inner-radius: var(--control-radius);/* and no shadow -- one level of elevation per stack */
--shadow-overlay: 0 16px 40px rgba(0,0,0,.55), 0 2px 8px rgba(0,0,0,.4);

--btn-fill: linear-gradient(180deg, var(--accent-fill-hi), var(--accent-fill));
--btn-fill-hover: linear-gradient(180deg, color-mix(in srgb, var(--accent-fill-hi) 88%, white),
                                          color-mix(in srgb, var(--accent-fill) 88%, white));
--glow-accent: 0 4px 14px color-mix(in srgb, var(--accent-fill) 35%, transparent);
--glow-ambient: radial-gradient(120% 60% at 0% 0%,
                color-mix(in srgb, var(--accent-fill) 12%, transparent), transparent 60%);
--scrim-soft: rgb(0 0 0 / 0.5);   /* shell.css:33's mobile-nav scrim, given a name */
```

**Radius call sites are classified, not aliased.**
- An alias `--radius: var(--control-radius)` would silently move every existing call site from 2px to 6px, including inner panels (`layout.ts:68`, `chart-container.ts:90,121`) that should be 8px.
- So the plan **inventories** every `var(--radius)`, `var(--radius-chip)` and raw `border-radius: <n>px` site and assigns each to exactly one of `--panel-radius`, `--control-radius`, `--chip-radius` or `--radius-sm`. Examples of `--radius-sm` sites: `magnitude.ts:25-26` (a 3px bar), `bar-list.ts`, `donut.ts`, `heat-grid.ts` cells, `share-bar.ts`, `histogram.ts:106,115`, `status-cell.ts:114`, `status-indicator.ts:90`, `scan-progress.css:39`, the 1px swatches `chart-tooltip.ts:27` and `status.ts:5`.
- `--radius-chip` sites in dense table cells are checked individually; a pill only where it reads as a tag.
- `--radius` and `--radius-chip` are **deleted** at the end of the migration, so no un-classified site survives.
- `border-radius: 50%` (dots) and `0` (the drawer's flush edge, `layout.ts:381`) stay as they are.

**Elevation moves from one level to two.**
- v18's rule ("one non-inset shadow, L3 only"), enforced by **`primitives.spec.ts` G3** (`:137-160`), becomes:
  - `--panel-shadow` for an in-flow panel (L1/L2);
  - `--shadow-overlay` for anything out of flow (L3).
- Both are applied through **global classes in `styles.css`**: `.sb-panel` (new) and the existing `.elev-overlay` (`styles.css:158`). Components never write `box-shadow` themselves, so G3's per-component "zero non-inset shadows" assertion stays as it is.
- G3's `styles.css` assertion changes from exactly `['var(--shadow-overlay)']` to exactly `['var(--panel-shadow)', 'var(--shadow-overlay)']`.
- `elevation.spec.ts` (which only regex-matches the `.elev-overlay`/`.elev-scrim` rules) gains a matching check for `.sb-panel`.

**Panels and buttons.**
- Panel primitives (`layout.ts`, `figure.ts`, `chart-container.ts`) add the `.sb-panel` class and read `--panel-bg/--panel-border/--panel-radius` for the rest.
- `--panel-bg` and `--btn-fill` are **gradients, i.e. images**. They are used only in `background`/`background-image`, never `background-color`.
- The primary `button.ts` swaps its hover `color-mix()` on a flat colour (`button.ts:67-68`) for `--btn-fill-hover`.
- `background` between two gradients does not transition. That is acceptable here, and v168 handles button hover with `filter: brightness()` and the glow, which do animate.

**Body background.** It becomes `var(--glow-ambient), var(--bg)`, a faint blue glow in the top-left.

### 4. Discord chart lockstep

- `swingbot/core/charts/chart_style.py:THEME` copies, byte for byte, every token it names: `bg`, `surface`, `surface-raised`, `border`, `border-strong`, `text`, `text-muted`, `text-faint`, `pos`, `neg`, `warn`, `info` and `chart-*`.
- Its new values land **in the same commit** as `palette.css`/`tokens.css`.
- `tests/charts/test_chart_theme.py` keeps comparing the two through the new `_resolve()` (§1). Its `D1_TOKENS` set and the keys `THEME` names stay exactly as they are. The test only checks keys present in `THEME`, so adding a token to the admin never forces a PNG change.
- Discord alert charts turn navy.
- `--text-faint` in a PNG is used for fine rules only, so the same "never text" rule holds there.

**Two Python colour sources stay outside the lockstep, deliberately:**
- **Discord embed stripes** (`swingbot/core/presentation/kinds.py:22-40`). They are tuned to read on Discord's own `#313338` dark and `#FFFFFF` light themes, not on the admin's ground, and they carry their own semantic ramp (setup level, result size). Moving them onto Arctic Navy would optimise them for a background they never sit on. "One palette everywhere" (D2) therefore means **the admin and the chart PNGs**.
- **The export disclaimer grey** (`swingbot/core/marketdata/export_data.py:91`, `#5a6169`). It is a plain historical export, not an alert chart, and stays as it is. v169 is frontend-only and declines it too, and it is recorded as a standing follow-up in v169's plan index `## Handoff` (see v169 § Out of scope).

**The chart cache outlives a deploy.** `swingbot/core/charts/cache.py` keys PNGs by content (e.g. `stats.py:242-245`, `:405-408`), not by style, and lives on the `./exports` host volume. Without a fix, `!stats` charts would keep the old palette for up to 7 days after deploy, and a rollback would serve navy PNGs for as long. Fix: `chart_style.py` exports a `STYLE_VERSION` string (bumped whenever `THEME` changes), and `cache.py` folds it into every key. `test_chart_theme.py` asserts that `STYLE_VERSION` changes whenever the `THEME` digest does: it pins the pair, so editing one without the other fails.

### 5. Gates (new or changed)

| Gate | Rule |
|---|---|
| `primitives.spec.ts` "no colour is declared outside tokens.css" (**extended**, not duplicated) | Today it matches `(?<!&)#hex` in every `ui/` call site, with an empty `HEX_ALLOWLIST`. It is extended in three ways. **Scope:** every `frontend/src/**/*.{ts,css}` and `frontend/src/index.html`, excluding specs, `styles/palette.css`, and `styles/tokens.css` (checked separately: hex only on the seven allow-listed names of §1; `rgb(a)` only inside tier-3 shadow tokens and only **black or white** at some alpha. Any hued glow derives from a tier-2 token with `color-mix()`, so a palette change reaches it.). **Pattern:** also `rgb(`/`rgba(`/`hsl(` in both comma and space syntax, so `shell.css:33`'s `rgb(0 0 0 / 0.5)` is caught (it migrates to `--scrim-soft`). It keeps the `(?<!&)` guard for `&#9650;` (`versions.ts:151`). **Comments:** `/* … */` and `//` comments are stripped before matching, so `button.ts:65-66`'s documentary hex stays legal. |
| `primitives.spec.ts` **raw radius** (new describe block, same file and helpers) | No `border-radius: <n>px` outside `styles/`. `50%` and `0` are allowed. No `var(--radius)`/`var(--radius-chip)` remains. |
| `primitives.spec.ts` **G3** (changed) | As §3: components cast no non-inset shadow, and `styles.css` casts exactly `var(--panel-shadow)` and `var(--shadow-overlay)`. |
| `elevation.spec.ts` (changed) | Also checks the `.sb-panel` rule. |
| `contrast.spec.ts` (**helper changed**, rule unchanged) | It resolves through `resolve-token.ts`. Text tokens must be ≥ 4.5:1 on all four surfaces, and white must be ≥ 4.5:1 on `--accent-fill` **and** on `--accent-fill-hi` (new). |
| `chart-palette.spec.ts` (**helper changed**, rule unchanged) | It resolves through `resolve-token.ts` and re-validates `--chart-*` against the new `--surface`. |
| `test_chart_theme.py` (**helper changed**) | Python `THEME` must equal the resolved token values. |

### 6. Superseded rules

The superseded passages are marked in place, not deleted (this repo's convention). Each mark points at v167. They are:
- spec v80 D1 (TradingView Blue palette) and D3's 2px radius;
- v18's single-shadow elevation rule;
- `tokens.css:14-17` and `:56-67`, the "TradingView Blue" header and the "ONE shadow … primitives.spec.ts enforces that" block;
- the `tokens.css` "radii, motion" comment ("Tight radii: terminal, not consumer app");
- `styles.css:145-154`, the one-shadow comment;
- `chart_style.py:19-27`, the "TradingView Blue / terminal" comment.

### 7. Devices (`docs/claude/ui-design.md`) and the cold-load colour

- Nothing in the new tokens depends on viewport width. `--control-h` keeps its 44px `pointer: coarse` / `< 640` override, and `--control-radius` holds at 6px at every height.
- `#0a0b10` appears in three places outside `styles/`, and all three move to `--bg` `#070b14`:
  - `index.html:21` (`theme-color`);
  - `index.html:42` (the inline `html, body { background }` that prevents a cold-load flash);
  - `manifest.webmanifest` (`theme_color` and `background_color`).

  `index.html` is in the colour gate's scope with an allow-list entry for exactly those two hex values, each with its comment. The cold-load style cannot use `var()`, because the stylesheet has not loaded yet.

Because they are copies, a new assertion in `primitives.spec.ts` checks, through `resolve-token.ts`, that all four literals equal the resolved `--bg`: `index.html` ×2, plus the manifest's `theme_color` and `background_color`. A later palette change then fails a test instead of leaving a cold-load flash and a stale PWA bar.

## Out of scope

- All motion and animation (v168). This spec leaves `--dur-*`, keyframes and the `prefers-reduced-motion` block untouched.
- Per-workspace visual fixes that the new geometry exposes (v169).
- A light theme. `tokens.css` keeps "dark only".
- Typography scale and spacing scale. Both are unchanged.

## Interaction with live plans

**v165 (calendar day page)** and **v166 (trade detail reorganisation)** spell out constructs that v167 deletes or bans:
- `v166 …_2-header-strip.md:742` uses `border-radius: var(--radius)`;
- `v165 …_3-day-page-ui.md:325, :694` and `…_3b-day-page-drawer-url.md:688` use `var(--radius-chip)` and a raw `border-radius: 2px`.

If either lands after v167, the new radius gate fails. If someone merges around the gate, a deleted `var()` silently resolves to radius 0.

**Required order:** v167's radius-inventory task runs **only after v165 and v166 are merged to `main`**, so that their components are inventoried like everything else. If either is still unmerged when v167 reaches that task, v167 stops there and records it in `## Handoff`. It never edits another plan's worktree. The palette, resolver and chart tasks that come before the inventory do not depend on v165 or v166.

## Deploy and rollback

- **No step on the Hetzner VM.** One image serves both containers, `.env` is untouched, and there is no schema change, cron job or store write.
- **Rollback** is the immutable `sha-` image tag (`docs/deploy/DEPLOY_HETZNER.md:208-217`). It reverts the SPA and the PNG palette together, and `STYLE_VERSION` (§4) keeps the chart cache from serving the wrong palette in either direction.
- **PWA:** the service worker (`frontend/ngsw-config.json:13`) picks up the new `manifest.webmanifest` on its next update check. An installed PWA may show the old title-bar colour until it next reloads. This is cosmetic and needs no action.

## Testing and evidence

- The gates in §5.
- Each plan task quotes the **verdict line** of its narrow run. "Should pass" is not evidence. The narrow runs are:
  - `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`;
  - `npx vitest run src/app/ui` (from `frontend/`).
- Then the plan's single full-suite task.
- **Screenshots** with Playwright (`scripts/browse.mjs`) at **390 / 768 / 1440** of the dashboard, the trades list and an open drawer, before and after, stored under `docs/superpowers/results/v167/`. **Pass criterion:** at each width, no horizontal page scroll, no text clipped by a new radius, every panel shows the gradient ground and hairline, and the partner signs the set off in chat. The screenshots are the evidence the partner reviews. They are not an automated diff.

## Panel review

Run 2026-10-16. senior-engineer reviewed commit `e8a8e9bc`, and staff-engineer reviewed `c17de9e6`. Every finding was ADVISORY, with no BLOCKING findings.

- senior-engineer: the shadow gate is `primitives.spec.ts` G3, not `elevation.spec.ts` (which only matches two rules) -- applied (§3, §5).
- senior-engineer: `contrast.spec.ts` and `chart-palette.spec.ts` token helpers are hex-only and will throw on `var()` tier-2 tokens -- applied (§1 shared resolver, §5).
- senior-engineer: a hex gate already exists in `primitives.spec.ts` (`HEX_ALLOWLIST`, `(?<!&)` guard); `shell.css:33` uses space-syntax `rgb()`; comment stripping unstated; `index.html:42` missed -- applied (§5 extends the existing gate, `--scrim-soft`, §7).
- senior-engineer: there are about 18 raw radius sites, not 12, and many are small bars or swatches that 6px would turn into pills -- applied (`--radius-sm`, §3 inventory).
- senior-engineer: the `--radius` alias silently moves 44 sites to 6px, including inner panels -- applied (classify every site, delete the aliases).
- senior-engineer: `--accent-soft` alpha contradiction; `--accent-fill-hi` margin unstated; chart floor holds on `--surface` only; thin ΔE margins -- applied (§2 notes).
- senior-engineer: gradients cannot be `background-color`; button hover `color-mix` needs a gradient token; gradient backgrounds do not transition -- applied (`--btn-fill-hover`, §3).
- senior-engineer: `chart_style.py:19-27` and `tokens.css` comments need supersede marks; keep `D1_TOKENS` unchanged -- applied (§4, §6).
- senior-engineer: tasks must quote narrow-run verdict lines; screenshots need a pass criterion -- applied (Testing and evidence).
- staff-engineer: `select_tests.py` `ESCALATE_PREFIXES` names only `tokens.css`; a palette-only edit would skip the slow chart-theme test -- applied (§1).
- staff-engineer: the content-hash chart cache has no style version and outlives deploy and rollback -- applied (§4 `STYLE_VERSION`).
- staff-engineer: embed stripe colours (`kinds.py`) and the export grey (`export_data.py:91`) sit outside the lockstep -- applied as an explicit out-of-scope statement with the reason (§4). Stripes are tuned to Discord's own themes.
- staff-engineer: hued glows hard-code the fill blue as `rgba` -- applied (`color-mix()` from `--accent-fill`; the gate allows only black or white `rgba`).
- staff-engineer: the `#070b14` copies in `index.html` and the manifest are unchecked against `--bg` -- applied (§7 equality assertion).
- staff-engineer: v165 and v166 plan text uses tokens v167 deletes -- applied (required order, § Interaction with live plans).
- staff-engineer: no deploy or rollback note -- applied (§ Deploy and rollback).
- staff-engineer: two hand-kept resolvers with no cross-check -- applied (shared fixture `resolved_tokens.json`, §1).
- senior-engineer (v169 panel, cross-spec): v169 needed a nested-panel token that only v167 may add -- applied (`--panel-inner-bg`/`--panel-inner-radius` in tier 3, §3).
