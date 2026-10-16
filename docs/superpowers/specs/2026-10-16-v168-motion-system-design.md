# v168 — Motion system: one motion file, a Motion preference (default On), ten animations

**Version:** ui 1.24.1 · bot 2.5.2 (at writing)
**Bump:** ui minor; bot none. Every screen gains motion, and the shell gains a Motion setting. The Discord bot is untouched.
**Edge:** none (integrity). This is presentation only. It changes no signal, threshold, plan, sizing or badge.
**Screen:** exempt (integrity)
**Panel:** senior-engineer
**Status:** spec written 2026-10-16 from the same brainstorm as v167. The partner watched all ten animations play live in the visual companion (Arctic Navy) and chose **all ten**, with **animations on by default**. Depends on **v167** (tier-3 tokens, `styles/` layout). Is followed by v169.

## Why

The partner asked for "more animations across the pages", **enabled by default**.

Today:
- Motion is deliberately minimal. `tokens.css` says "nothing on entrance", reasoning that live push updates make entrance animation a permanent flicker.
- Keyframes are scattered over ten files, and `pulse` is defined four times and `spin` twice.
- `tokens.css`'s `@media (prefers-reduced-motion: reduce)` block zeroes every duration. Windows reports that preference whenever *Animation effects* is off, which is common on laptops, so on such a machine the admin has no motion at all and no way to opt back in.

The flicker argument still holds for **re-animating on a push**, and that stays forbidden (§4). It never justified having no entrance motion on navigation.

## Decisions taken in the brainstorm

| # | Question | Answer |
|---|---|---|
| D1 | Which animations? | All ten in §3. |
| D2 | "On by default" against the OS reduced-motion setting? | A **shell Motion control** (On / Reduced / Off), **default On even when the OS asks for reduced motion**, persisted through `PreferencesStore`. |

## Design

### 1. One knob: `--motion-scale`

In `tokens.css`:

```css
--motion-scale: 1;                                   /* On */
--dur-instant: calc(90ms  * var(--motion-scale));
--dur-base:    calc(160ms * var(--motion-scale));
--dur-slow:    calc(260ms * var(--motion-scale));
--dur-enter:   calc(420ms * var(--motion-scale));    /* new: route + panel entrance */
--dur-count:   calc(900ms * var(--motion-scale));    /* new: count-up */
--dur-draw:    calc(1200ms * var(--motion-scale));   /* new: chart draw-in */
--ease-out: cubic-bezier(0.2, 0.8, 0.2, 1);
--ease-spring: cubic-bezier(0.34, 1.4, 0.64, 1);
```

The shell writes `data-motion` on `<html>`:

| Setting | `data-motion` | `--motion-scale` | What runs |
|---|---|---|---|
| **On** (default) | `on` | 1 | everything |
| Reduced | `reduced` | 0.4 | hover/press, value flash, nav indicator, drawer. **No** entrance, stagger, count-up, draw-in, ambient drift or ping. |
| Off | `off` | 0 | nothing. Every `animation` and `transition` is set to `none`, and directives render the final state. |

- The control sits in the shell beside **Text size**, works the same way, and is stored in `PreferencesStore`, never in `localStorage`. This is plan v21's Global Constraint, the same one Text size follows.
- The `@media (prefers-reduced-motion: reduce)` block in `tokens.css` is **removed**. The three component-level copies in `connection-status.ts`, `scan-progress.css` and `shell.css` become `[data-motion=off]` / `[data-motion=reduced]` selectors.
- The OS setting is ignored by design (D2). The control is the way out. A comment in `tokens.css` records this decision and the reason for it.

TS code that needs the setting, such as count-up and draw-in, reads it from a `MotionService` (`ui/motion/motion.service.ts`), a signal derived from `PreferencesStore`. It never reads the DOM attribute.

### 2. One home: `styles/motion.css`

- **Every `@keyframes` in the app lives here**, imported by `styles.css` after `tokens.css`. Duplicates merge: `pulse`×4 → `sb-pulse`, `spin`×2 → `sb-spin`. `route-spin`, `scan-sweep`, `scan-strip-in`, `flash-up`, `flash-down`, `sb-row-blink` and `tape-slide` each move once and get an `sb-` prefix.
- Shared utility classes: `.sb-enter`, `.sb-stagger`, `.sb-lift`, `.sb-skeleton`, `.sb-pop-in`, `.sb-drawer-in`, `.sb-sheet-in`.
- Gate `ui/motion-home.spec.ts` (new): no `@keyframes` in any `frontend/src/**/*.{ts,css}` except `styles/motion.css`.
- Angular component styles are emulated-encapsulated, but keyframe names are global, so components reference the global names directly.

### 3. The ten animations

| # | Animation | Mechanism | Duration / easing | Runs |
|---|---|---|---|---|
| 1 | **Route transition** | `.sb-enter` on the routed workspace host: opacity 0→1, `translateY(8px)`→0, `blur(3px)`→0. The shell re-applies it on `NavigationEnd`. `withViewTransitions()` was considered and **rejected**: it snapshots the whole page, the tape and live dot included, which freezes the ticker mid-scroll for the transition. | `--dur-enter`, `--ease-out` | each navigation |
| 2 | **Staggered panel entrance** | `.sb-stagger` on a workspace's panel grid. Each child's delay is `calc(var(--i) * 60ms * var(--motion-scale))`, where `--i` is set by a tiny `[sbStaggerIndex]` directive and capped at 8 (later panels share the 8th delay). | `--dur-enter` | **once per route activation**, never on a store update |
| 3 | **Number count-up** | `[sbCountUp]` directive on `figure.ts` (hero metric) and KPI tiles. It takes the numeric value and the existing formatter. First render: 0 → value. Later changes ease from the old value to the new one. It writes `textContent` via `requestAnimationFrame` outside Angular's zone, so change detection does not run every frame. | `--dur-count`, ease-out-cubic | first render, then each change |
| 4 | **Skeleton shimmer** | `async.ts`'s loading state renders `<sb-skeleton [rows]="n" [shape]="'table'|'panel'|'figure'">`, shaped bars with a moving gradient, instead of loading text. The `aria-busy` and live-region text stay for screen readers. | 1.6s linear loop | while loading |
| 5 | **Hover and press** | `.sb-lift` on panels and cards: `translateY(-2px)`, `--border-strong`, deeper shadow, **only under `@media (hover: hover)`**. Primary button: hover brightness plus `--glow-accent`, `:active` `scale(.97)` on every device. Touch press: `:active` tint `--accent-soft`. | `--dur-instant` / `--dur-base` | on interaction |
| 6 | **Sliding nav indicator** | One absolutely positioned indicator element in the shell nav, moved by `transform: translateY(<active link offsetTop>)`. It replaces the per-link inset bar. It recomputes on route change and on sidebar resize via `ResizeObserver`. | 350ms × scale, `--ease-spring` | route change |
| 7 | **Drawer / dialog / toast / popover** | `Drawer` (`ui/layout.ts`) uses `.sb-drawer-in` (`translateX(100%)`→0) on tablet and desktop and `.sb-sheet-in` (`translateY(100%)`→0, a bottom sheet) on phone. `confirm-dialog.ts`, popovers and `toast-host.ts` use `.sb-pop-in` (scale .96→1 plus fade). The scrim fades in with `backdrop-filter: blur(2px)`. | 450ms × scale, `--ease-spring` | open, and the reverse on close |
| 8 | **Cell value flash (refined)** | `flash.ts` keeps its rule: only the changed cell flashes. The tint becomes `--pos-soft`/`--neg-soft` fading to transparent, with the text colour briefly matching. | 1.1s ease-out | on value change |
| 9 | **Chart draw-in** | `[sbDrawIn]` on SVG charts (`sparkline.ts`, gauge, donut, dot-plot): the stroke draws via `stroke-dashoffset` from `getTotalLength()` and the area fill fades in after 50%. Lightweight-charts canvases get a `clip-path: inset(0 100% 0 0)` → `inset(0)` reveal on `chart-container.ts`. | `--dur-draw`, `--ease-out` | **first render only**. Data updates repaint without redrawing. |
| 10 | **Ambient live cues** | Live dot: `sb-ping` ring (connection-status). Scan progress: the existing sweep, restyled to an accent gradient. Background: the `--glow-ambient` layer drifts on a 12s alternate `transform` loop on a fixed pseudo-element. | loops | On only |

All animations use only `transform`, `opacity`, `filter`, `clip-path`, `stroke-dashoffset` and `background-position`, never width, height, top or left.

### 4. The no-flicker rule

**Nothing re-enters on a push.** Entrance (#1, #2), count-up from zero (#3) and draw-in (#9) are keyed to route activation or first render, never to a store emission. The gate is `ui/motion/no-replay.spec.ts`: it mounts a workspace, lets the entrance finish, pushes a store update, and asserts that no element gains `.sb-enter`/`.sb-stagger` again and no `sbDrawIn` restarts. Count-up on a change (#3) and the cell flash (#8) are the two **intended** push reactions, and both are scoped to the value that changed.

### 5. Devices (`docs/claude/ui-design.md`)

| | Phone < 640 | Tablet 640–1023 | Desktop ≥ 1024 |
|---|---|---|---|
| Stagger | cap 4, 40ms step | cap 8, 60ms | cap 8, 60ms |
| Drawer | bottom sheet (`.sb-sheet-in`), full width | from the right, 85% width | from the right, current width |
| Hover lift | none (no hover); `:active` tint | `:active` tint, plus hover lift if `hover: hover` | hover lift |
| Ambient glow drift | static (battery) | drift | drift |

The Motion control is in the shell's settings area on every class. On phone it is in the same menu as Text size. Its three options are 44px touch targets.

### 6. Performance guardrails

- Count-up and draw-in run outside the Angular zone and cancel their frame on destroy.
- `will-change` is set only for the duration of an animation, never left in place.
- The ambient drift layer is `position: fixed; pointer-events: none; z-index: -1`, one element in the shell, not one per panel.
- Lighthouse / Performance trace on the dashboard before and after: no long task > 50ms attributable to motion. Recorded in `docs/superpowers/results/v168/`.

## Out of scope

- Palette and geometry (v167).
- Per-workspace adoption beyond the shared primitives. v168 wires the ten animations into the shell and the shared `ui/` primitives (figure, async, Drawer, dialog, toast, sparkline, gauge, donut, chart-container, flash, button), so every workspace that uses those gets them. Workspace-specific panel grids get `.sb-stagger` in v169.

## Testing

- New gates: `motion-home.spec.ts`, `motion/no-replay.spec.ts`.
- Unit specs per directive (`sbCountUp`, `sbDrawIn`, `sbStaggerIndex`): final state reached; `data-motion=off` renders the final state synchronously; a value change from A to B passes through intermediate values, then settles on B's formatted string.
- `MotionService` spec: default `on`; persisted value restored; the OS `prefers-reduced-motion` does not change the default.
- Shell spec: the Motion control writes `PreferencesStore` and `data-motion`.
- Playwright at 390 / 768 / 1440: route change, drawer open on phone (sheet) vs desktop (side), Motion = Off shows no animation.
- The plan ends with the single full-suite task.
