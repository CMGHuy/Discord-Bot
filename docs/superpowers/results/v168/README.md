# v168 motion system: evidence (MO18)

Recorded 2026-10-19 against local stacks: before = `main` at f067dccc (:4123), after = branch `2026-10-16-v168-motion-system` at 35d3a53b (:4124, `main` merged in). API: `admin_ui.py` on :1234 against the local `swingbot_prod_replica` (production copy of 2026-10-19 17:58Z). The SPA is served under `/app/`; the script adds the prefix itself. Script: `motion-evidence.cjs` (this directory); raw samples: `animations.json`.

## 1. Route change (`route@<w>-mid.png`, `route@<w>-settled.png`)

| Width | Running just after the URL changed | Running 1.5s later |
|---|---|---|
| 390 | sb-enter | none |
| 768 | sb-ambient-drift, sb-enter, sb-tape-slide | sb-ambient-drift, sb-tape-slide |
| 1440 | sb-ambient-drift, sb-enter, sb-pulse-blink, sb-tape-slide | sb-ambient-drift, sb-pulse-blink, sb-tape-slide |

Nothing named `sb-enter`, `sb-fade-in` or `sb-draw-*` is left running; the rest are the ambient and live cues. **Pass.**

## 2. Drawer (`drawer@<w>-opening|open|closing.png`)

| Width | Opening | Closing | Geometry seen |
|---|---|---|---|
| 390 | sb-fade-in, sb-sheet-in | sb-sheet-out | bottom sheet, drag handle |
| 768 | sb-drawer-in, sb-fade-in (+ambient) | sb-drawer-out (+ambient) | from the right, about 85vw |
| 1440 | sb-drawer-in, sb-fade-in (+ambient) | sb-drawer-out (+ambient) | from the right |

`sb-fade-in` is the backdrop. **Pass.**

## 3. Motion = Off (`off@<w>-loading.png`, `off@<w>-settled.png`)

Forced through `<html data-motion="off">` after preferences loaded; no preference was written. TS-side Off (no count-up, draw-in or flash class) is proven by `count-up.spec.ts`, `draw-in.spec.ts` and `flash.spec.ts`. The Trades chunk is loaded first, because the route overlay only shows after the resolver has been pending for 1000ms.

| Width | Running while the route loads (name, ms) | Running once settled |
|---|---|---|
| 390 | sb-route-spin 2400 | none |
| 768 | sb-route-spin 2400 | none |
| 1440 | sb-route-spin 2400 | none |

**Pass.**

## 4. Performance trace (`trace-before.json`, `trace-after.json`, 1440, dashboard -> trades -> dashboard)

Slimmed to metadata plus events of 1ms or more; both load in Chrome DevTools -> Performance -> Load profile.

| Trace | Long tasks > 50ms (at ms, duration, heaviest children) |
|---|---|
| before | @1360 115ms TimerFire / FunctionCall chunk-VKM6RLSZ (page timer); @1475 85ms Layout 62ms, UpdateLayoutTree 12ms, Paint 4ms |
| after | @1071 81ms FireAnimationFrame 57ms (chunk-6MEYMZ7U), Layout 16ms; @2701 168ms lightweight-charts 78ms, FireAnimationFrame 53ms; @2878 51ms lightweight-charts 36ms; @3066 60ms UpdateLayoutTree 22ms, FireAnimationFrame 17ms; @4856 50ms (no children) |

Two further runs per stack (not committed, same method): before had 1-3 long tasks, all the page's own timer or a layout (72-133ms TimerFire, one 85ms Layout); after had 2-3, one of them a 172ms TimerFire in the shared page chunk and the others `lightweight-charts` frames of 33-115ms. A run with `--force-off` (motion off, branch) still showed chart-library work but about a third of it (35-38ms total against 83-175ms with motion on).

**Attributable to motion, by the plan's rule:** one task, after @3066 (60ms): no counterpart in the before trace at that step and its heaviest child is style work (`UpdateLayoutTree`). It is small and not repeated in the other runs, so it may be noise, but the rule counts it.

**Not attributable by the rule, but a finding:** `lightweight-charts` script frames appear in every after run (83-175ms of chart code per run, 33-168ms single tasks) and in no before run. They are script, not style/layout/paint, so they do not meet the rule, and the same code runs with motion off at a third of the cost, which points at motion making the dashboard equity chart re-render more often while it animates in (a resize or re-layout during `sb-enter` / `sb-draw-in`). Not investigated further here: the remedy would change the spec's design (drop the entrance from the chart host, or draw the chart after the entrance), so it goes to the partner first.

## Verdict

Criteria 1-3 pass at 390 / 768 / 1440. Criterion 4 is **open**: one task attributable by the rule and a consistent chart-library cost that only the motion build shows. No fix applied. Shot notes: none.
