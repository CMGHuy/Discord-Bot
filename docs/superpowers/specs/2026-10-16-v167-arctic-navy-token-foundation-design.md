# v167 — Arctic Navy token foundation: three-tier tokens, refined-terminal geometry, chart lockstep

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot patch. Every admin screen changes colour and geometry. The Discord chart PNGs change colour, but the bot's behaviour does not.
**Edge:** none (integrity). This is a visual and maintainability change. It touches no signal, threshold, plan, sizing or badge.
**Screen:** exempt (integrity)
**Panel:** senior-engineer, staff-engineer
**Status:** spec written 2026-10-16 from a brainstorm with the partner. Direction, palette and approach were approved in chat, and the palette was picked from live mockups in the visual companion. This is the first of three specs: **v167 Foundation → v168 Motion system → v169 Polish sweep**, run in that order.

## Why

The partner asked for a more elegant, more professional dark theme that stays blue, set by global rules so that one change reaches every screen, with a more centralized CSS configuration.

The admin (`frontend/`, Angular 21) already has a single token file, `frontend/src/styles/tokens.css`, which about 100 components consume through `var(--…)`. Three things stand in the way of the request:

1. **There is no palette layer.** Semantic tokens (`--surface`, `--accent`) hold raw hex directly. Changing "the blue" means editing meaning-level tokens one by one, and nothing stops a component from writing hex of its own.
2. **There is no component layer.** "How a panel looks" (background, border, radius, shadow) is spelled out again in each component's `styles:`. The `var(--radius)` call sites (42) and `var(--radius-chip)` call sites (11) share one 2px value, and 12 further sites hard-code `border-radius: 2px`/`3px`/`4px`.
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
  palette.css    tier 1 -- raw named colours. THE ONLY FILE WITH HEX.
  tokens.css     tier 2 -- semantic (--bg, --accent, --pos ...), each var(--palette-name)
                 tier 3 -- component tokens (--panel-*, --control-*, --chip-*, --glow-*)
  fonts.css      unchanged
```

`styles.css` imports `palette.css` before `tokens.css`. Tier 3 lives at the bottom of `tokens.css` under its own banner rather than in a fourth file. It is short, and keeping it beside tier 2 keeps the "what does a panel look like" answer one file away from "what does surface mean".

**Exception, kept from today:** `--chart-1…6` and `--quality-4` stay **literal hex inside `tokens.css`**. `line-chart.ts` reads them through `getComputedStyle` under jsdom, which does not resolve a nested `var()`. `chart-palette.spec.ts` also parses the file as text. The hex gate (§5) allow-lists exactly these seven names.

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
| `--accent-fill-hi` (new, gradient top stop) | — | `#2474d2` | white ≥ 4.5:1 (gate) |
| `--pos` | `#17c98e` | `#3ddc97` | 8.59:1 |
| `--neg` | `#ff5470` | `#ff6f7d` | 5.66:1 |
| `--warn` | `#ffb43d` | `#ffc266` | 9.52:1 |
| `--info` | `#b39ddb` | `#c3a6ff` | 7.39:1 |
| `--*-soft` tints | 12% of the old hue | the same alphas, re-derived from the new hues. `--accent-soft` is 16% of `--accent-fill` | — |
| `--quality-4` | `#9acd32` | unchanged | — |
| `--chart-1…6` | — | **unchanged.** All are ≥ 4.82:1 on the new `--surface`. `chart-palette.spec.ts` re-validates OKLCH band and ΔE against the new surface, and a failure there reopens this table rather than loosening the gate | — |

The contrast figures were computed during the brainstorm. `contrast.spec.ts` is the gate that must agree with them.

The valence rule (one hue = one meaning; a sixth hue is a review defect) is **unchanged**. The palette swaps values only.

### 3. Geometry and elevation (tier 3)

```css
--panel-radius: 8px;
--control-radius: 6px;          /* buttons, inputs, selects, segmented controls */
--chip-radius: 999px;           /* pills */
--radius: var(--control-radius);      /* alias -- the 42 existing call sites follow */
--radius-chip: var(--chip-radius);    /* alias -- the 11 existing call sites follow */

--panel-bg: linear-gradient(180deg, var(--surface-raised), var(--surface));
--panel-border: 1px solid var(--border);
--panel-shadow: inset 0 1px 0 rgba(255,255,255,.03), 0 6px 18px rgba(0,0,0,.25);
--shadow-overlay: 0 16px 40px rgba(0,0,0,.55), 0 2px 8px rgba(0,0,0,.4);

--btn-fill: linear-gradient(180deg, var(--accent-fill-hi), var(--accent-fill));
--glow-accent: 0 4px 14px rgba(28,109,208,.35);
--glow-ambient: radial-gradient(120% 60% at 0% 0%, rgba(28,109,208,.12), transparent 60%);
```

The `rgba(...)` values above are shadow and glow geometry. Under the hex gate (§5) they may appear **only in `tokens.css` tier 3 and `palette.css`**.

- **Elevation moves from one level to two.** v18's rule ("one non-inset shadow, L3 only") becomes: `--panel-shadow` for an in-flow panel (L1/L2) and `--shadow-overlay` for anything out of flow (L3). `elevation.spec.ts` is updated to allow **exactly these two tokens** as non-inset shadows and to keep failing on any raw shadow.
- The 12 raw `border-radius: <n>px` sites are migrated to a tier-3 token. `50%` (dots, avatars) and `0` stay as they are.
- The body background becomes `var(--glow-ambient), var(--bg)`, a faint blue glow in the top-left.
- Primitives that paint a panel (the panel and card primitives in `ui/layout.ts`, `figure.ts`, `chart-container.ts`) read `--panel-bg/--panel-border/--panel-radius/--panel-shadow`. Primary `button.ts` reads `--btn-fill/--glow-accent/--control-radius`. `chip.ts` reads `--chip-radius`.

### 4. Discord chart lockstep

`swingbot/core/charts/chart_style.py:THEME` copies, byte for byte, every token it names (`bg`, `surface`, `surface-raised`, `border`, `border-strong`, `text`, `text-muted`, `text-faint`, `pos`, `neg`, `warn`, `info`, `chart-*`). Its new values land **in the same commit** as `palette.css`/`tokens.css`. `tests/charts/test_chart_theme.py` keeps comparing the two, and it now resolves a tier-2 `var(--x)` through `palette.css` before comparing. Discord alert charts turn navy.

`--text-faint` in a PNG is used for fine rules only, so the same "never text" rule holds there.

### 5. Gates (new or changed)

| Gate | Rule |
|---|---|
| `ui/no-raw-colour.spec.ts` (new) | No hex and no `rgb(`/`rgba(`/`hsl(` colour literal in any `frontend/src/**/*.{ts,css}` outside `styles/palette.css` and `styles/tokens.css`. Spec files and comments are excluded. Inside `tokens.css`, hex is allowed only on the seven allow-listed names (§1). |
| `ui/no-raw-radius.spec.ts` (new) | No `border-radius: <n>px` outside `styles/`. `50%` and `0` are allowed. |
| `elevation.spec.ts` (changed) | Non-inset `box-shadow` may only be `var(--panel-shadow)` or `var(--shadow-overlay)`. |
| `contrast.spec.ts` (unchanged rule) | Re-run on the new values: text tokens ≥ 4.5:1 on all four surfaces. White on `--accent-fill` **and** `--accent-fill-hi` ≥ 4.5:1 (the second stop is new). |
| `chart-palette.spec.ts` (unchanged rule) | Re-validates `--chart-*` against the new `--surface`. |
| `test_chart_theme.py` (changed) | Python `THEME` equals the resolved token values. |

### 6. Superseded rules

The superseded passages are marked in place, not deleted (this repo's convention):
- spec v80 D1 (TradingView Blue palette) and D3's 2px radius;
- v18's single-shadow elevation rule;
- the "radii, motion" comment block in `tokens.css` ("Tight radii: terminal, not consumer app").

Each mark points at v167.

### 7. Devices (`docs/claude/ui-design.md`)

Nothing in the new tokens depends on viewport width. `--control-h` keeps its 44px `pointer: coarse` / `< 640` override, and `--control-radius` holds at 6px at every height. Before and after screenshots at **390 / 768 / 1440** of the dashboard, trades list and a drawer are the evidence for this spec. The full every-workspace pass is v169.

`index.html` `theme-color` and `manifest.webmanifest` `theme_color`/`background_color` (both `#0a0b10` today) move to `--bg` `#070b14`, so the PWA title bar matches.

## Out of scope

- All motion and animation (v168). This spec leaves `--dur-*`, keyframes and the `prefers-reduced-motion` block untouched.
- Per-workspace visual fixes that the new geometry exposes (v169).
- A light theme. `tokens.css` keeps "dark only".
- Typography scale and spacing scale. Both are unchanged.

## Interaction with live plans

- **v165 (calendar day page)** and **v166 (trade detail reorganisation)** add components. They must use tokens, not hex, which v165/v166 already require. Whichever lands second rebases. The new gates will name any stray literal.

## Testing

- The gates in §5. This spec introduces two of them and changes two.
- `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py` covers the Python side.
- Frontend: `npx vitest run src/app/ui` while iterating, then the plan's single full-suite task.
- Playwright screenshots at three widths (§7), stored under `docs/superpowers/results/v167/`.
