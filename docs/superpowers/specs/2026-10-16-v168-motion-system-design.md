# v168 — Motion system: one motion file, a Motion preference (default On), ten animations

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot none. Every screen gains motion, and the shell gains a Motion setting. The Discord bot is untouched.
**Edge:** none (integrity). This is presentation only. It changes no signal, threshold, plan, sizing or badge.
**Screen:** exempt (integrity)
**Panel:** senior-engineer
**Status:** spec written 2026-10-16 from the same brainstorm as v167. The partner watched all ten animations play live in the visual companion (Arctic Navy) and chose **all ten**, with **animations on by default**. Revised the same day after the panel (see `## Panel review`). Depends on **v167** (tier-3 tokens, `styles/` layout). Is followed by v169.

## Why

The partner asked for "more animations across the pages", **enabled by default**.

Today:
- Motion is deliberately minimal. `tokens.css:255-266` says "nothing on entrance", reasoning that live push updates make entrance animation a permanent flicker.
- Keyframes are scattered over ten files, and `pulse` is defined four times and `spin` twice.
- `tokens.css`'s `@media (prefers-reduced-motion: reduce)` block zeroes every duration. Windows reports that preference whenever *Animation effects* is off, which is common on laptops, so on such a machine the admin has no motion at all and no way to opt back in.

The flicker argument still holds for **re-animating on a push**, and that stays forbidden (§4). It never justified having no entrance motion on navigation.

## Decisions taken in the brainstorm

| # | Question | Answer |
|---|---|---|
| D1 | Which animations? | All ten in §3. |
| D2 | "On by default" against the OS reduced-motion setting? | A **shell Motion control** (On / Reduced / Off), **default On even when the OS asks for reduced motion**, persisted through `PreferencesStore`. |

## Design

### 1. The Motion preference

**Three modes, written as `data-motion` on `<html>` by the shell:**

| Mode | `data-motion` | What runs |
|---|---|---|
| **On** (default) | `on` | everything in §3 |
| **Reduced** | `reduced` | **No transform-based motion.** Entrances (#1, #2) become a plain opacity fade at `--dur-base`. There is no count-up (#3: the final value shows at once), no draw-in (#9), no hover lift (only the border and glow change), no ping, no ambient drift, and the **tape is frozen**. The cell flash (#8), the drawer and dialog fade (no slide), the nav indicator (instant move, colour fade) and the skeleton shimmer (a static tint instead) stay. |
| **Off** | `off` | No decorative motion. Every animation and transition **keeps its existing non-motion fallback** (table below) rather than simply stopping. |

Reduced is **not** a duration multiplier: scaling durations by 0.4 makes motion faster and snappier, not gentler. `--motion-scale` exists only as `1` (On, Reduced) or `0` (Off) for the `calc()` durations, and the Reduced behaviour is written as `[data-motion=reduced]` rules in `motion.css`.

**Off and Reduced keep today's fallbacks.** Today's `prefers-reduced-motion` rules are replaced by `[data-motion=off]` rules (and `[data-motion=reduced]` where noted) at **all nine sites**, each keeping the fallback it has now:

| Site | Today's fallback, kept |
|---|---|
| `tokens.css` global block | replaced by the `--motion-scale` mechanism above |
| `shell/connection-status.ts:89-90` | live dot: steady colour, no pulse |
| `shell/scan-progress.css:87-91` | strip appears without sliding; sweep becomes a static 40% fill |
| `shell/shell.css:100` (sidebar width) and `:373` (route spinner) | width snaps; the spinner keeps spinning, slowed |
| `shell/tape/tape.css:54-67` | track frozen, `overflow-x: auto` so tiles stay reachable (also under Reduced) |
| `ui/data-table/data-table.ts:241-243` (spinner), `:325-338` (`.blink` row) | spinner slowed, not removed; the blinking row becomes a steady `--warn` tint |
| `ui/chart-container.ts:146` | spinner slowed, not removed |
| `ui/status-indicator.ts`, `ui/status-cell.ts` | steady state colour |

Loading spinners are **status, not decoration**. They never disappear under Off.

**Durations.** The existing `--dur-instant/base/slow` become `calc(<n>ms * var(--motion-scale))`. Three new durations join them: `--dur-enter` 420ms, `--dur-count` 900ms and `--dur-draw` 1200ms. `--ease-out` keeps its current value, `cubic-bezier(0.2, 0.8, 0.3, 1)`, so no existing transition changes curve. Loops that are literals today (spinner 700ms, the tape's computed speed, the 1.6s shimmer) are switched by the `[data-motion]` rules, not by the scale.

**Persistence and cold load.**
- Key `shell.motion`, values `on|reduced|off`. Unknown or missing values mean `on`.
- It is validated and applied the way `shell.zoom` is (`shell.ts:219-243`), and stored only in `PreferencesStore`, never `localStorage` (plan v21's Global Constraint).
- Preferences load asynchronously (`preferences.store.ts:61-75`). **Until `isLoaded()`, `<html>` carries `data-motion="pending"`.** That suppresses every entrance, count-up and draw-in (content renders in its final state at once) and freezes the tape. A user who chose Off therefore never sees a cold-load burst of motion. A user on On simply gets no entrance on the very first paint, and route transitions animate from the next navigation.
- **The OS setting is ignored by design (D2).** `MotionService` never consults `matchMedia('(prefers-reduced-motion: reduce)')`, and its spec asserts the mock is not called. A comment in `tokens.css` records this decision and the reason for it.

**The control.**
- It sits in the shell's profile menu beside **Text size** (`profile-menu.ts:61`): a three-option segmented control, keyboard-operable, with 44px targets on touch.
- Auto-starting loops (tape, ping, ambient drift, shimmer) are covered for WCAG 2.2.2 by this control. The tape also already pauses on hover and focus, and that stays.
- TS code reads the mode from `MotionService` (`ui/motion/motion.service.ts`), a signal derived from `PreferencesStore`, never from the DOM attribute.

### 2. One home: `styles/motion.css`

- **Every `@keyframes` in the app lives here**, imported by `styles.css` after `tokens.css`.
  - Duplicates merge: `pulse`×4 → `sb-pulse`, `spin`×2 → `sb-spin`.
  - `route-spin`, `scan-sweep`, `scan-strip-in`, `flash-up`, `flash-down`, `sb-row-blink` and `tape-slide` each move once and get an `sb-` prefix.
- Shared utility classes: `.sb-enter`, `.sb-stagger`, `.sb-lift`, `.sb-pop-in`, `.sb-drawer-in`, `.sb-sheet-in`, `.sb-drawer-out`, `.sb-fade-out`. It also holds every `[data-motion=reduced|off|pending]` rule.
- Gate `ui/motion-home.spec.ts` (new): no `@keyframes` in any `frontend/src/**/*.{ts,css}` except `styles/motion.css`. It excludes `*.spec.ts`, itself included.
- Keyframe names are global under Angular's emulated encapsulation, so components reference the global names directly.

### 3. The ten animations

**Every entrance-type animation runs once per route activation.** A new `RouteEntryService` (`ui/motion/route-entry.service.ts`) holds an **activation id**.
- The id increments only when the **path** changes. It does **not** increment on:
  - navigations carrying `BACKGROUND_REFRESH_INFO` (`routing/route-refresh.service.ts:42`);
  - a same-URL reload;
  - a change to query parameters or the fragment only.
- Each entrance consumer (#1 route, #2 stagger, #3 first count-up, #9 draw-in) asks `RouteEntryService.claim(key)` before animating, where `key` is a stable per-element string such as the panel id or the figure label.
  - The first claim within an activation returns `true`, and the element animates.
  - Every later claim in the same activation returns `false`, and the element renders its final state immediately.
- This is what survives `sb-async` destroying and recreating its projected content on every refetch (`ui/async.ts:46-70`). Re-creation produces a fresh element, but its claim was already spent.

| # | Animation | Mechanism | Duration / easing |
|---|---|---|---|
| 1 | **Route transition** | `.sb-enter` on the routed workspace host when a claim succeeds: opacity 0→1, `translateY(8px)`→0, `blur(3px)`→0. Uses `animation-fill-mode: backwards`, so no `transform`/`filter` lingers to create a containing block or stacking context for `position: fixed`/`sticky` descendants. `withViewTransitions()` was **rejected**: it snapshots the whole page, which freezes the tape and live dot mid-motion. | `--dur-enter`, `--ease-out` |
| 2 | **Staggered panel entrance** | `.sb-stagger` applied **inside the shared `sb-panel-grid`** (`ui/panel-grid.ts:6`), so every workspace that uses it staggers at once. Hand-built grids are v169's job. The `[sbStaggerIndex]` directive sets `--i` on each child, capped at 8 (later panels share the 8th delay). Delay is `calc(var(--i) * 60ms * var(--motion-scale))`. Fill mode `backwards`. Gated by the claim. | `--dur-enter` |
| 3 | **Number count-up** | `[sbCountUp]` directive on `figure.ts` and KPI tiles. **The directive owns the text node.** `figure.ts`'s template drops its `{{ display() }}` interpolation (`figure.ts:5`) in favour of a host element the directive writes. Inputs are the numeric value and the existing formatter. When the claim succeeds, it counts 0 → value. A later change eases from the old value to the new one (an intended push reaction, §4). A `null` value renders the ABSENT glyph at once, with no count. It writes `textContent` in `requestAnimationFrame` outside Angular's zone and cancels on destroy. | `--dur-count`, ease-out-cubic |
| 4 | **Skeleton shimmer** | `async.ts` **already** renders a shaped skeleton (`rows`/`cols`, pulse; `async.ts:22-23,99-109`). The change is narrow: replace the pulse with a moving-gradient shimmer on `.skeleton-cell`, and add an optional `shape` input (`table` default, `panel`, `figure`) for non-table placeholders. Row heights stay as they are now, so the existing no-layout-shift guarantee holds. `aria-busy` and the live-region text are unchanged. | 1.6s linear loop |
| 5 | **Hover and press** | `.sb-lift` on panels and cards: `translateY(-2px)`, `--border-strong`, deeper shadow, **only under `@media (hover: hover)`**. Primary button: hover `filter: brightness(1.1)` plus `--glow-accent`. Gradient backgrounds do not transition (v167 §3), so brightness carries the hover. `:active` `scale(.97)` on every device. Touch: an `:active` tint of `--accent-soft`. | `--dur-instant` / `--dur-base` |
| 6 | **Sliding nav indicator** | One absolutely positioned indicator element in the shell nav, replacing the per-link inset bar. It moves by `transform: translateY(<active link offsetTop>)` and its height follows the link. It recomputes on route change and through a `ResizeObserver` on **the nav list and each link**, which covers sidebar collapse, `--text-scale` changes (`shell.ts:211-216`) and nav height changes. | 350ms, `--ease-spring` |
| 7 | **Drawer / dialog / toast** | See §3a. | 450ms `--ease-spring` in; 200ms out |
| 8 | **Cell value flash (refined)** | `flash.ts` keeps its rule: only the changed cell flashes, and a new change restarts the flash (remove, reflow, add, as now). The tint becomes `--pos-soft`/`--neg-soft` fading to transparent over 1.1s (was `--dur-base`), and the text briefly takes new tier-3 tokens `--flash-up-text`/`--flash-down-text` (= `--pos`/`--neg`). Under Off, the directive **skips adding the class**, because `animationend` would never fire to remove it (`flash.ts:37-47`). | 1.1s ease-out |
| 9 | **Chart draw-in** | **A `clip-path` reveal, not a stroke-dash animation.** `[sbDrawIn]` animates `clip-path: inset(0 100% 0 0)` → `inset(0)` on the chart's host element, the same mechanism for SVG (sparkline, gauge, donut, dot-plot) and canvas (`chart-container.ts`). `getTotalLength()` was rejected because jsdom does not implement it, and the sparkline's `vector-effect: non-scaling-stroke` with `preserveAspectRatio="none"` (`sparkline.ts:58-81`) measures dashes in screen space but lengths in viewBox units. Gauge and donut use a radial-friendly variant (`clip-path: circle(0)` → `circle(75%)`). Gated by the claim, so data updates and refetches repaint without redrawing. | `--dur-draw`, `--ease-out` |
| 10 | **Ambient live cues** | Live dot: `sb-ping` ring (connection-status). Scan progress: the existing sweep restyled with an accent gradient. Background glow: **v168 moves v167's static `--glow-ambient` off the `body` background** and onto one `position: fixed; inset: 0; pointer-events: none` layer, the shell's first child, with the shell content above it in stacking order. That layer drifts on a 12s alternate `transform` loop. There is exactly one glow per page, never two. The login page sits outside the shell, so it gets its own single static glow layer in v169. | loops; On only |

#### 3a. Drawer, dialog and toast, in and out

`Drawer` (`ui/layout.ts:343-408`) and `ConfirmDialog` (`ui/confirm-dialog.ts:36-60`) are `<dialog>` elements, and `close()` removes them from rendering at once. Their `@if (open())` bodies are destroyed on close.

- **Opening:** `.sb-drawer-in` (`translateX(100%)` → 0), `.sb-sheet-in` on phone, or `.sb-pop-in` for the dialog (scale .96 → 1 plus fade). The `::backdrop` fades in with `backdrop-filter: blur(2px)`.
- **Closing:** the component's `close()` first sets a `closing` signal, which applies `.sb-drawer-out` or `.sb-fade-out` (200ms). On `animationend` it calls `dialog.close()` and flips `open` to false, so the body stays mounted for the exit. Under Off or `pending`, it closes immediately as today. An Escape key or backdrop click goes through the same path. A spec covers each.
- **Phone bottom sheet is a geometry change, not just a keyframe.** Below 640px the drawer changes from `margin: 0 0 0 auto; height: 100dvh; width: 100vw` (`layout.ts:364-408`) to `margin: auto 0 0; width: 100vw; max-height: 85dvh`, with a top `--panel-radius` and a drag-handle bar. On tablet (640–1023) it is `width: 85vw` from the right.
- **Toasts** (`shell/toast-host.ts:10-14`) use Angular 21's `animate.enter` / `animate.leave` on the `@for` item, with `.sb-pop-in` / `.sb-fade-out`, so a removed toast plays its exit before leaving the DOM.

New animations use only `transform`, `opacity`, `filter`, `clip-path` and `background-position`. Existing transitions that already animate layout (e.g. `shell.css:10`'s `grid-template-columns` sidebar transition) are left as they are.

### 4. The no-flicker rule

**Nothing re-enters on a push or a refetch.** Entrances (#1, #2), count-up from zero (#3) and draw-in (#9) all go through `RouteEntryService.claim()`. The two **intended** push reactions are count-up on a change (#3) and the cell flash (#8), both scoped to the value that changed.

Gate `ui/motion/no-replay.spec.ts`:
- Every directive and the route host call an injectable `MotionStarts` recorder when they **start** an animation. jsdom has no `getAnimations()` and does not fire `animationstart`, so the recorder is the observable.
- The spec mounts a workspace and lets the first activation's starts happen.
- It then drives **both** replay paths: (a) `RouteRefreshService`'s background refresh, a real `navigateByUrl` with `BACKGROUND_REFRESH_INFO`; and (b) toggling an `sb-async` from loading → content.
- It asserts that **zero** new entrance, stagger, first-count or draw-in starts were recorded.
- A third case changes the path and asserts the starts happen again.

### 5. Devices (`docs/claude/ui-design.md`)

| | Phone < 640 | Tablet 640–1023 | Desktop ≥ 1024 |
|---|---|---|---|
| Stagger | cap 4, 40ms step | cap 8, 60ms | cap 8, 60ms |
| Drawer | bottom sheet, `max-height: 85dvh` | from the right, `85vw` | from the right, current width |
| Hover lift | none (no hover); `:active` tint | `:active` tint, plus hover lift if `hover: hover` | hover lift |
| Ambient glow drift | static (battery) | drift | drift |

The Motion control is in the profile menu on every class, with 44px targets on touch.

### 6. Performance guardrails

- Count-up runs outside the Angular zone and cancels its frame on destroy.
- `will-change` is set only for the duration of an animation, never left in place.
- The ambient layer is one element in the shell, not one per panel.
- A Chrome Performance trace on the dashboard, before and after, must show no long task > 50ms attributable to motion. It is recorded in `docs/superpowers/results/v168/`.

## Out of scope

- Palette and geometry (v167).
- Per-workspace adoption beyond the shared primitives. v168 wires the ten animations into the shell and the shared `ui/` primitives (figure, async, Drawer, ConfirmDialog, toast host, sparkline, gauge, donut, dot-plot, chart-container, flash, button), so every workspace that uses those gets them. Workspace-specific panel grids get `.sb-stagger` in v169.

## Testing

**Test-environment default.**
- `src/test-setup.ts` provides `MotionService` in mode **`off`** for every spec. Existing specs that read `.textContent` synchronously (`figure.spec.ts:6-8` and the ~30 spec files that render `Figure`) therefore keep passing unchanged, because Off renders final values at once.
- Motion specs opt in with `provideMotion('on')`.
- Directive code must never touch `getTotalLength`, `getAnimations` or `matchMedia` unguarded.

**Inverted and rewritten tests and comments.**
- `ui/tokens.spec.ts:91-93` (`honours prefers-reduced-motion`, which asserts the media block exists) is **inverted**. It now asserts that `tokens.css` contains no `prefers-reduced-motion` and that `motion.css` contains `[data-motion=off]` rules.
- The comments and tests that assume the old rule are rewritten in the same task: `flash.ts:16-17`, `watchlist.ts:344`, and `tokens.css:255-266` ("nothing on entrance").

**New specs.**
- `motion-home.spec.ts` and `motion/no-replay.spec.ts` (§2, §4).
- `MotionService`: the default is `on`; a persisted value is restored; an unknown value falls back to `on`; `matchMedia` is never called; the mode is `pending` until preferences load.
- `RouteEntryService`: the id increments on a path change only, not on `BACKGROUND_REFRESH_INFO`, a same-URL reload or a query-only change; `claim()` is true once per key per activation.
- `sbCountUp`: in `on`, the value passes through intermediate values and settles on the formatted value; a change eases A→B; `null` shows ABSENT at once; `off` renders the final value synchronously.
- `sbDrawIn`: in `on`, the clip-path animation class is applied when the claim succeeds; a second claim renders unclipped.
- `Drawer`/`ConfirmDialog`: close plays the exit, then calls `dialog.close()`; under `off` the close is immediate; Escape and backdrop follow the same path.
- `flash.ts` under `off`: no class is added.
- Shell: the Motion control writes `shell.motion` and `data-motion`.

**Evidence.**
- Each task quotes its narrow run's verdict line (`npx vitest run <path>` from `frontend/`).
- Playwright at 390 / 768 / 1440: route change; drawer open and close on phone (sheet) vs desktop (side); Motion = Off shows no decorative motion and the spinners still turn.
- The plan ends with the single full-suite task.

## Panel review

Run 2026-10-16. senior-engineer reviewed commit `0d480ce8`.

- senior-engineer [BLOCKING]: background refresh emits `NavigationEnd` (`route-refresh.service.ts:33-42`), so the entrance would replay on every push -- applied (`RouteEntryService` path-change activation id, §3; the gate drives a real background refresh, §4).
- senior-engineer [BLOCKING]: `sb-async` re-creates content on refetch, so "first render" animations replay; the gate cannot see CSS replays in jsdom -- applied (`claim()` per activation; `MotionStarts` recorder gate).
- senior-engineer [BLOCKING]: `tokens.spec.ts:91-93` asserts the reduced-motion block that v168 deletes; stale comments in `flash.ts`, `watchlist.ts`, `tokens.css` -- applied (inverted test and rewrites listed under Testing).
- senior-engineer [BLOCKING]: count-up conflicts with `Figure`'s interpolation and breaks synchronous `.textContent` specs -- applied (directive owns the text node; test default `off`; `null` → ABSENT).
- senior-engineer [BLOCKING]: `getTotalLength()` is missing in jsdom and wrong under non-scaling-stroke; the sparkline has no area fill -- applied (`clip-path` reveal for every chart, §3 #9).
- senior-engineer: async already renders a shaped skeleton -- applied (reworded as a shimmer plus a `shape` input, §3 #4).
- senior-engineer: `<dialog>` close and toast removal have no exit mechanism; the bottom sheet is a geometry change -- applied (§3a).
- senior-engineer: Off would drop existing non-motion fallbacks at nine sites, spinners included -- applied (§1 fallback table).
- senior-engineer: Reduced as a 0.4 multiplier makes motion snappier; `--ease-out` silently changed -- applied (Reduced redefined as opacity-only; `--ease-out` kept).
- senior-engineer: cold-load motion before preferences load; WCAG 2.2.2; persistence key; `matchMedia` must not be consulted -- applied (`pending` mode, control placement and note, `shell.motion`, `MotionService` spec).
- senior-engineer: under Off, flash classes linger because `animationend` never fires -- applied (§3 #8).
- senior-engineer (v169 panel, cross-spec): the stagger belongs in the shared `sb-panel-grid`, not per workspace -- applied (§3 #2).
- senior-engineer: two ambient glows (v167 body plus v168 layer); gate must exclude spec files; `fill-mode: backwards`; "only transform…" claim too broad; `ResizeObserver` misses `--text-scale` -- applied (§3 #10, §2, §3 #1/#2, §3 last paragraph, §3 #6).

## Amendments from the plan brief (2026-10-16)

The plan-briefer's pass (`.superpowers/briefs/2026-10-16-v168-motion-system.md`) refuted several claims. These decisions bind the plan and override earlier text where they differ:

1. **Count-up targets.**
   - `<sb-figure>` is rendered only by `figure.ts` and `gallery.ts`, and only two specs render it (`figure.spec.ts`, `gallery.spec.ts`).
   - The real KPI tiles are `stat-tile`, `metric-card` and `metric-chip`, used by calendar, trading-performance, risk and trade-detail. `[sbCountUp]` goes on the **headline value of those three primitives and of `figure.ts`**, each owning its text node.
   - The plan re-counts the specs that render them. The global `off` default (amendment 5) keeps those specs synchronous.
2. **Stagger reach.**
   - The only non-spec user of `sb-panel-grid` is `gallery.ts`. Dashboard and the other workspaces use `.sb-stack`/`.sb-row` or hand-rolled grids.
   - Stagger therefore becomes **CSS-only and host-driven**. When a route-entry claim succeeds, the routed host `div.workspace-content` (shell.html, about :160) gets `.sb-entering` for the entrance duration.
   - `motion.css` gives direct children of the workspace's top-level `.sb-stack`, `.sb-row` and `sb-panel-grid` an `:nth-child(1..8)` delay (60ms steps, 40ms and cap 4 on phone).
   - The `[sbStaggerIndex]` directive is **dropped**. v169 handles hand-rolled grids by switching them to these layout primitives.
   - `panel-grid.spec.ts` reads `panel-grid.ts` as source text, so its minmax 220/320 and phone-query literals stay byte-identical.
3. **Route-entry detection.** `BACKGROUND_REFRESH_INFO` is defined at `routing/route-loading.service.ts:15`. `RouteEntryService` reads `info` and the target path at **`NavigationStart`**, because `currentNavigation()` is null by `NavigationEnd`. It commits the new activation id on `NavigationEnd`. The existing `.route-pending` opacity transition on the same host element is kept, and the entrance animates via `animation`, not that `transition`.
4. **Motion control.** The Text-size control is a cycle button (`profile-menu.ts:60-69`). The Motion control is an `sb-segmented` (`ui/segmented.ts`) with three options in the same menu.
5. **Global test default.** `test-setup.ts` has no providers today, and `initTestEnvironment` is called by the Angular builder. The plan adds a global `beforeEach(() => TestBed.configureTestingModule({ providers: [provideMotion('off')] }))` to `test-setup.ts` (`vitest/globals` is on). Specs that need motion override it with `provideMotion('on')`. `flash.spec.ts` and `pnl-cell.spec.ts:74-76` (which assert the `flash-up` class) opt in.
6. **Fallback corrections to the §1 table.**
   - Scan sweep under Off keeps today's `width: 100%; opacity: .4`.
   - The route spinner (`shell.css:373`) **stops** under reduced motion today. v168 deliberately changes it to spin slowly, because spinners are status, not decoration. Recorded as an intended behaviour change.
7. **`pulse` merge.** The four `pulse` definitions have three different shapes. They consolidate by shape into `sb-pulse-soft` (.45), `sb-pulse-dim` (.35) and `sb-pulse-blink` (1 → .25 → 1), keeping each call site's current duration. Identical copies merge, and no visual changes.
8. **Hover-lift shadow.** `.sb-lift`'s deeper shadow is a new tier-3 token `--panel-shadow-lift` (black rgba only, per v167's gate), applied only from `styles/motion.css`. `primitives.spec.ts` G3 is extended so that `motion.css` may cast exactly `var(--panel-shadow-lift)`.
9. **Interplay with v167's code.**
   - New `:root` tokens go **inside v167's tier-3 banner block** in `tokens.css`, not after it, and every commit that adds a token regenerates `tests/charts/resolved_tokens.json` (`scripts/dev/dump_tokens.py`).
   - v167 AN9's `body { background: var(--glow-ambient), var(--bg) }` and its `elevation.spec.ts` case are edited when the glow moves to the shell layer.
   - The button `.primary` hover is built on v167 AN10's `--btn-fill`/`--btn-fill-hover` lines.
10. **Drawer spec.** `layout.spec.ts:112-119` asserts the drawer's phone rule `width: 100vw` as source text. The bottom-sheet task rewrites that assertion to the new geometry.
11. **Nav indicator.** The nav is three `<ul class="nav">` groups inside a sticky, scrolling `.sidebar`, so the indicator lives in `.sidebar` and positions against it. `ResizeObserver` is undefined in jsdom, so the directive guards `typeof ResizeObserver`.
12. **Toasts.** Angular 21.2's `animate.enter`/`animate.leave` need no provider (`@angular/animations` is not installed and is not needed). In jsdom a leaving toast is removed immediately, and the specs assert that.
13. **Corrected citations and commands.**
    - `flash.ts:37-47` is actually :41-46, and the Drawer class runs to about :443.
    - Specs run with `cd frontend && npx ng test --watch=false --include '<glob>'`, not `npx vitest run`.
    - TypeScript has no radon. Complexity < 15 is held by review.
