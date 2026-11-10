# v225 — Dark blue theme: a second ground beside Graphite, picked per browser

**Version:** ui 1.40.5 · bot 2.18.2
**Bump:** ui minor (every admin user gets a new visible choice in the top bar; the bot and the Discord images are untouched, so bot none)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer

## Why

The admin SPA has one look: Graphite, a neutral near-black (v195 §1.1). The
partner wants a second, dark blue look and a switch between the two, so they can
pick whichever ground is easier on the eyes for long sessions. Nothing about the
data, the alerts or the trading changes. This is a colour preference only.

`frontend/src/styles/tokens.css` currently states "Dark only ... no
`[data-theme]` hook ... Adding one later means revisiting the spec". This spec is
that revisit. It still adds no light theme: both themes are dark, and the
valence colours (green, red, amber, violet, steel accent) stay identical so a
gain, a loss or a warning reads the same in either.

## Decisions (partner, 2026-11-10)

1. **Two themes: Black (Graphite, today's) and Dark blue (Navy).** The default
   for a browser that never chose is Black, so nobody's screen changes until
   they switch it.
2. **The switch is a toggle in the top bar on tablet and desktop, and a row
   in the profile menu on a phone** (the phone bar has no room for it),
   **saved per browser** (localStorage), not per account. It is applied before first paint, so a cold load in Dark
   blue never flashes black.
3. **The Navy ground ladder is "Navy, a bit darker"**, chosen from mockups
   (four options compared on one sample screen; the partner picked Navy and
   asked for one step darker). Values in § Palette.
4. **The Discord chart PNGs stay on Graphite.** `chart_style.THEME`,
   `tests/charts/resolved_tokens.json` and `STYLE_VERSION` do not change.

## Design

### Palette (tier 1, `palette.css`)

New tier-1 entries, alongside the existing Graphite ones (which stay as they
are):

| Tier-2 token | Graphite (unchanged) | Dark blue | Tier-1 name (my call) |
|---|---|---|---|
| `--bg` | `#0d0f12` | `#070c18` | `--midnight-950` |
| `--surface` | `#15181d` | `#0c1424` | `--midnight-900` |
| `--surface-raised` | `#1c2128` | `#121c32` | `--midnight-850` |
| `--surface-overlay` | `#1f242b` | `#172440` | `--midnight-800` |
| `--border` | `#23272e` | `#182540` | `--midnight-750` |
| `--border-strong` | `#2d333b` | `#233453` | `--midnight-700` |
| `--text-faint` (rules only) | `#6b7280` | `#5f6f8a` | `--midnight-500` |
| `--overlay-dim` | `rgba(13,15,18,.72)` | `rgba(7,12,24,.72)` | `--midnight-950-a72` |
| `--text` | `#e6e8eb` | `#e6ecf5` | `--frost-100` |
| `--text-secondary` | `#c9d1d9` | `#c9d4e3` | `--frost-300` |
| `--text-muted` | `#9aa4b2` | `#9fb0c8` | `--frost-400` |

The inks are blue-tinted to match the ground, as in the approved mockup.
Every other tier-2 colour token (`--accent*`, `--on-accent`, `--pos`, `--neg`,
`--warn`, `--info`, the five `*-soft` tints, `--quality-*`, `--chart-1..6`,
`--scrim-soft`, `--shadow-overlay`) is **the same in both themes**.

**Naming (my call):** `midnight` and `frost`, not `navy`. The test
`keeps no Arctic Navy palette name in either token file`
(`frontend/src/app/ui/tokens.spec.ts`) forbids `--navy-N`/`--slate-N`/`--sky-N`/`--teal-N`
so the retired v167 palette cannot creep back. That guard stays as it is; the
new palette takes names it does not match. The user-facing label is
"Dark blue".

**Measured contrast (WCAG, computed from the hexes above):**

| Ink | on bg | on surface | on raised | on overlay | Gate |
|---|---|---|---|---|---|
| `--text` | 16.45 | 15.49 | 14.28 | 12.97 | 4.5 |
| `--text-secondary` | 13.03 | 12.28 | 11.32 | 10.28 | 4.5 |
| `--text-muted` | 8.86 | 8.34 | 7.69 | 6.98 | 4.5 |
| `--accent` | 8.09 | 7.62 | 7.02 | 6.38 | 4.5 |
| `--pos` | 7.70 | 7.25 | 6.69 | 6.07 | 4.5 |
| `--neg` | 6.63 | 6.25 | 5.76 | 5.23 | 4.5 |
| `--warn` | 7.74 | 7.29 | 6.72 | 6.10 | 4.5 |
| `--info` | 8.06 | 7.59 | 7.00 | 6.36 | 4.5 |
| `--text-faint` (non-text) | 3.84 | 3.62 | 3.33 | 3.03 | none |

On their own tints (the `contrast.spec.ts` v181 gate measures over `--surface`
and `--surface-raised`): `--pos` 6.09 / 5.54, `--neg` 5.41 / 4.93. Every gated
pair clears 4.5:1. One ungated pair sits just under it: `--neg` on `--neg-soft`
over `--surface-overlay` is 4.48:1. Graphite measures the same, 4.48:1 on its
overlay `#1f242b`, and that pair is ungated there too. Fixing it means moving
an overlay step or the red tint in both themes, which is a palette change
outside this spec, so the plan reports it and moves no colour. The filled buttons do not change
(`--accent-fill`/`--accent-fill-hi` carry white at 5.74 / 5.00 in both themes).

### Mechanism (tier 2, `tokens.css`)

- `<html data-theme="navy">` selects Dark blue; **no attribute (or any other
  value) is Graphite**. The bare `:root` blocks keep Graphite exactly as now.
- One new block, `:root[data-theme="navy"] { … }`, re-points only the eleven
  tier-2 tokens in the table to the `midnight-*`/`frost-*` entries. It holds
  `var()` references only, never a hex, so the rule "tier 2 names a meaning,
  tier 1 holds the hue" still holds.
- **Placement:** after the tier-2 `:root` and before the tier-3 banner. The
  `data-density` override already sits there for the same reason (it keeps
  the tier-3 slice and the token fixture untouched).
- `scripts/dev/dump_tokens.py` and `frontend/src/app/ui/testing/resolve-token.ts`
  read only blocks whose selector is exactly `:root`, so the new block is
  invisible to both. The jsdom fixture, `resolved_tokens.json` and the Discord
  parity test resolve every meaning-level token to Graphite. The plan adds a
  test pinning that, so a future resolver change cannot silently make the
  Discord images Navy.
- **The fixtures do grow.** The new tier-1 entries live in a bare `:root` in
  `palette.css`, and both resolvers read every bare `:root` in it. The
  fixture already lists raw palette names (`"graphite-950": "#0d0f12"`). So
  `python scripts/dev/dump_tokens.py` must regenerate
  `tests/charts/resolved_tokens.json` (and the jsdom fixture) with the eleven
  added `midnight-*`/`frost-*` keys, and that regeneration is committed with
  the palette. Every existing key keeps its value. `chart_style.THEME` reads
  meaning-level tokens only, so `STYLE_VERSION` does not change.
- **The standing rule for future palette work:** the tokens that make up
  the *ground and ink* are a named list: `--bg`, the three surfaces,
  `--overlay-dim`, both borders, `--text`, `--text-secondary`,
  `--text-muted`, `--text-faint`. Every token on that list has a Navy value,
  and every token off it is shared. A future ground or ink token (a new
  surface step, a new text tier) joins the list and gets its Navy value in
  the same commit. The rewritten `tokens.css` header states this rule, and
  `tokens.spec.ts` checks it both ways: the Navy block re-points exactly
  the listed tokens, and every listed token is re-pointed.
- The `tokens.css` header note ("Dark only. There is no light theme ... no
  `[data-theme]` hook") is rewritten. Both themes are dark, there is still no
  light theme and no `prefers-color-scheme`, and `data-theme` exists for the
  ground only, citing this spec.

### Preference, storage and pre-paint

- A `ThemeService` (`frontend/src/app/ui/theme.service.ts`) modelled on
  `DensityService`: a signal `theme(): 'graphite' | 'navy'`, `set(theme)`,
  storage behind an injection token (guarded localStorage by default, an
  in-memory fake in specs), key `ui.theme`, validated on read (anything
  unknown is `graphite`). It writes `document.documentElement.dataset.theme`
  and nothing else in the DOM, except the `theme-color` meta (below).
- **Why localStorage and not `PreferencesStore`:** the partner chose per
  browser. It also has to be readable before the bundle parses to avoid the
  flash, and `PreferencesStore` loads over HTTP after the shell boots. This
  matches `DensityService`'s per-device precedent. The plan v21 constraint
  "shell preferences go through PreferencesStore" is about account-level
  settings and does not cover this one. The `ThemeService` doc comment says
  so, citing this spec.
- **The `theme-color` value is never a literal in TS.** `primitives.spec.ts`
  ("declares no colour literal") covers every `.ts` under `src/`. So
  `ThemeService` sets the attribute first, then reads the computed `--bg`
  off `document.documentElement` and writes that into the meta.
- **Pre-paint:** a small inline `<script>` in `frontend/src/index.html`, placed
  before the inline `<style>`, reads `ui.theme` (in try/catch). On `navy` it sets
  `data-theme="navy"` on `<html>`, swaps the `theme-color` meta's content, and
  paints the cold-load ground in the Navy `--bg`. The existing inline style
  stays Graphite for every other case.
- **The cold-load copies.** `index.html` gains exactly one more literal hex:
  the Navy `--bg`, held once in a script variable that both the meta swap
  and the ground paint read. The colour gate's exact, in-order allow-list
  for `index.html` (`primitives.spec.ts`, `HEX_ALLOWLIST`, today
  `['#0d0f12', '#0d0f12']`) becomes the three literals in file order: the
  Graphite meta, then the Navy script variable, then the Graphite inline
  style, if the script sits between the meta and the `<style>`. The
  allow-list comment is updated with the reason. `primitives.spec.ts`'s cold-load test is
  extended to assert it equals the resolved `--midnight-950`, the same
  guard that already pins the Graphite copies. `manifest.webmanifest` stays
  Graphite: a manifest is static and installed once, so it cannot follow a
  per-browser choice. A Dark blue user's home-screen splash is black for an
  instant. That is accepted, and the manifest's comment says so.
- On every toggle, `ThemeService` also updates `<meta name="theme-color">`.
  On a phone the browser chrome follows.

### The control

- **Top bar, tablet and desktop:** an icon button (`sb-button
  variant="icon"`, `sb-hit` for the 44px hit area on phone and tablet) placed
  between the search trigger and the profile menu in `shell.html`.
  `aria-pressed` reflects Dark blue, and the pressed state is visible too:
  the glyph takes `--accent` on an `--accent-soft` ground, the same
  selected look the segmented controls use. Without that, the icon looks
  the same in both states. Its `aria-label` and hint are "Dark blue
  theme", so the name stays fixed while the state toggles. One click
  switches; the change is immediate, with no reload.
- **Icon (my call):** a new `theme` glyph in `ui/icon.ts`, a circle half
  filled, drawn like the existing line icons (no emoji).
- **Profile menu row, all three device classes:** a "Theme" segmented row,
  Black | Dark blue, under the existing Motion and Density rows in
  `profile-menu.ts`. It follows their layout (label, then `sb-segmented`, and
  each segment at least 44px wide). It writes through the same
  `ThemeService`, so the menu and the bar can never disagree. It is the
  setting's only visible text label, and on a phone it is the only switch.
- **Command palette (my call):** one command, "Switch theme", in the
  palette's command list.
- **Phone (partner, 2026-11-10): no bar button.** The 390px bar already
  carries the brand, up to three chips, search and the profile menu. On a
  phone (`ViewportService.isPhone()`) the bar button is not rendered, and the
  profile menu's Theme row is the switch.

### Charts

- CSS-painted charts and SVG read `var(--…)` and follow the attribute with no
  code change.
- lightweight-charts charts (`trade-chart.ts`, `price-pane.ts`,
  `equity-candles.ts`) and the canvas primitives (`legend-primitive.ts`,
  `vline-primitive.ts`) read token strings once, through `chart-theme.ts`'s
  `token()`, at creation. Each must re-apply its options when
  `ThemeService.theme()` changes (an `effect` calling `applyOptions` with a
  fresh `chartTheme()` read, and the primitives re-reading on their next
  draw). Otherwise a chart open during the toggle keeps the old ground until
  the route is left.
- How each chart is refreshed is the builder's call. The requirement: after a
  toggle, no visible chart pixel still carries the other theme's ground,
  grid or text colour.

## Error handling

- localStorage absent, blocked or throwing (private mode, quota): the read
  falls back to Graphite and the write keeps the choice for this page life
  only, silently. This is the same as `DensityService`.
- A stored value that is not `graphite` or `navy`: treated as Graphite, and
  not rewritten until the user toggles.
- The pre-paint script failing for any reason: the page loads in Graphite,
  then `ThemeService` applies the stored theme on bootstrap. At worst that is
  one black frame, never a broken page.

## Testing

- **`theme.service.spec.ts`:** default Graphite; reads a stored `navy`;
  rejects junk; `set` writes storage, `data-theme` and the meta; a throwing
  storage neither throws nor loses the in-memory choice.
- **`tokens.spec.ts`:** a `v225: the Navy ground` block that pins the eleven
  `:root[data-theme="navy"]` re-points (each references its `midnight-*`/
  `frost-*` name and resolves to the table's hex) and asserts that the block
  holds no hex. It also asserts that no other tier-2 token is re-pointed in
  it, and that the Arctic Navy guard still passes.
- **`contrast.spec.ts`:** every existing gate runs twice, once per theme.
  A **separate test-only helper** (e.g. `resolveTokenIn(theme, name)` in
  `ui/testing/`) layers the `[data-theme="navy"]` block over the bare
  `:root` blocks. `resolve-token.ts`'s existing path stays byte-identical to
  its documented line-for-line twin `scripts/dev/dump_tokens.py`, which gets
  **no** theme argument. The pairing comment in both files gains one line
  saying so, so the drift is never "fixed" by teaching the Python half
  about Navy, which would put the Discord parity at risk.
- **`primitives.spec.ts`:** the Navy cold-load copy in `index.html` equals
  the resolved Navy `--bg`; the manifest still equals the Graphite `--bg`.
- **Discord parity:** a test that `dump_tokens.py`'s output is identical
  with and without the `[data-theme="navy"]` block in `tokens.css`. It
  compares two in-memory runs, not the committed file, so the PNGs cannot
  drift Navy. The existing `--check` drift test passes after the fixture is
  regenerated.
- **Shell and profile menu:** the bar button toggles `aria-pressed` and calls
  `ThemeService.set`, and it is not rendered when `isPhone()`; the menu row reflects and sets the same state; the
  palette command exists.
- **Charts:** for each lightweight-charts host, a spec that toggling the
  theme calls `applyOptions` with the new `--surface`.
- **Layout audit:** `layout-audit.mjs` must exit 0 at 390, 768 and 1440 in
  **both** themes. The plan gives the audit a `--theme navy` switch, or seeds
  `ui.theme` before the run. The audit also covers the **open profile
  menu** at 390px, because the Theme row is the phone's only control and the
  part most likely to overflow.
- **Canvas check:** the layout audit cannot see canvas pixels. So one
  Playwright screenshot of a chart screen (Dashboard equity candles) at
  390px and 1440px, in each theme, taken after toggling with the chart
  already mounted, is attached to the implementation's review.
- **No new faint text:** the existing `no-text-uses-text-faint` rule holds
  under Navy unchanged (`--text-faint` is 3.03 to 3.84:1). The plan adds no
  text in `--text-faint`.

## Out of scope

- A light theme, or following the OS `prefers-color-scheme`.
- Per-account theme sync through `PreferencesStore`.
- Navy Discord chart images, a Navy manifest, or Navy favicons.
- Changing any valence, accent, chart-series or quality colour.
- The Jinja templates (only the Angular SPA is themed). The login form is
  part of the SPA (`App` renders it in place of the shell), so it follows
  the theme. Any page still rendered by Jinja stays Graphite.

## Blast radius and rollback

Only the admin SPA bundle (the `admin` container) changes. The bot, the
refresher, the Discord alerts and their chart PNGs are untouched. Rolling
back to the previous ui release (`scripts/ops/rollback_to.sh`,
`docs/deploy/DEPLOY_HETZNER.md`) leaves a `ui.theme` key in localStorage
that the old bundle never reads: the page is simply Graphite again. There
is no schema, `.env`, cron or production data change.

## Panel review

Run 2026-11-10 on 08f9fdbd (ux-designer, staff-engineer). No BLOCKING findings.

- staff-engineer: the index.html colour-gate allow-list (`HEX_ALLOWLIST`, exact and in order) was unstated; the Navy hex could be written twice -- applied (§ Preference: one script variable, allow-list becomes three literals in file order).
- staff-engineer: where `ThemeService` gets the `theme-color` value was unstated; a TS hex fails "declares no colour literal" -- applied (reads the computed `--bg`).
- staff-engineer: a theme argument on `resolve-token.ts` breaks its line-for-line pairing with `dump_tokens.py` -- applied (separate test-only helper; pairing comment amended in both files).
- staff-engineer: the closed eleven-token re-point list silently leaves future ground/ink tokens Graphite under Navy -- applied (named ground/ink list, rule in the `tokens.css` header, checked both ways).
- staff-engineer: no blast-radius or rollback line -- applied (§ Blast radius and rollback).
- ux-designer: the bar icon shows no visible pressed state -- applied (`--accent` glyph on `--accent-soft`).
- ux-designer: the profile-menu Theme row should be unconditional, with its phone layout specified -- applied (row on all three classes, Motion/Density layout, 44px segments).
- ux-designer: the layout audit should cover the open profile menu at 390px -- applied.
- ux-designer: confirm no text uses `--text-faint` under Navy -- applied (stated in § Testing; the existing rule holds unchanged).
- ux-designer: gate or fix `--neg` on `--neg-soft` over the overlay (4.48:1) -- rejected: Graphite measures the same 4.48:1 on its overlay, so the fix is a palette change to both themes and out of this spec's scope; recorded in § Palette.
- ux-designer: the PWA splash (black) and the toggled `theme-color` disagree on a phone -- rejected: already accepted in § Preference; the reviewer agreed it is acceptable.
- ux-designer: canvas colours escape the layout audit; add screenshots of one chart screen in both themes -- applied (§ Testing, canvas check).
- ux-designer: say which Jinja pages stay Graphite -- applied (login is SPA-rendered; any Jinja page stays Graphite).
