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

A controlled follow-up (2026-10-19, same machine, interleaved, three runs each of before = `main`, after = branch, and after with motion forced off through `--force-off`) gave, per run, long tasks (count, summed ms) and `lightweight-charts` script time:

| Run | before | after | after, motion off |
|---|---|---|---|
| 1 | 11 tasks, 842ms, chart 0ms | 7 tasks, 707ms, chart 0ms | 2 tasks, 227ms, chart 0ms |
| 2 | 3 tasks, 230ms, chart 0ms | 6 tasks, 342ms, chart 630ms | 4 tasks, 293ms, chart 0ms |
| 3 | 14 tasks, 953ms, chart 117ms | 0 tasks, 0ms, chart 0ms | 1 task, 90ms, chart 0ms |

Long tasks are the page's own timers and renders in every column; `main` (no motion) has as many and as heavy as the branch, and shows chart-library work too (run 3). The branch is not consistently worse than `main`, so the long tasks cannot be attributed to motion. The earlier impression that chart-library time appeared only in the motion build was sampling luck: whether the equity chart renders inside the 5-second window depends on when its candles arrive. The machine was running two `ng serve`, the API and a headed browser, so single numbers swing widely (0-630ms of chart time under identical conditions); the table is the honest summary, not a precise benchmark.

**Attributable to motion, by the plan's rule:** none. The one 60ms style-work task in the first trace has a counterpart in every before run (long tasks of 85-133ms with Layout / TimerFire children).

## Verdict

Pass on all four criteria. Criteria 1-3 at 390 / 768 / 1440 from the animation samples; criterion 4 from the three-run comparison above (no long task attributable to motion; measurement noise is large on this machine). Shot notes: none.
