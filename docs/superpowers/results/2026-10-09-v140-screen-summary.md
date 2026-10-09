# v140 first screen batch — summary

**Spec:** `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`
**Pass rule:** ΔExpR ≥ +0.10R after costs, lower 95% week-cluster bound > 0, ≥ 7 of 9 years (2011–2019) positive, N ≥ 300 (`docs/claude/backtest-methodology.md` § Stage −2).

| Idea | Verdict | N | ΔExpR | 95% interval | Years positive | Record |
|---|---|---|---|---|---|---|
| `high52w` | SCREEN-FAIL | 3612 | -0.3660R | [-0.4261, -0.3036] | 0/9 | `results/2026-10-08-screen-high52w.md` |
| `uptrend_pullback` | SCREEN-PASS | 26912 | +0.3672R | [+0.3107, +0.4261] | 9/9 | `results/2026-10-08-screen-uptrend_pullback.md` |
| `gap_volume` | SCREEN-FAIL | 1834 | -0.4639R | [-0.5505, -0.3787] | 0/9 | `results/2026-10-09-screen-gap_volume.md` |
| `turn_of_month` | SCREEN-FAIL | 38349 | -0.0453R | [-0.1271, +0.0362] | 1/9 | `results/2026-10-09-screen-turn_of_month.md` |

**1 of 4 passed.**

## What follows (spec § What follows a result)

`uptrend_pullback` earns its own later spec — a strategy or a filter — carrying `**Screen:** screen-uptrend_pullback SCREEN-PASS`, with live-trigger/screen-trigger parity pinned by a test there. Not part of v140. A pass buys a spec, not a verdict: the idea still runs the unchanged funnel.

Read the pass for what it is: ΔExpR is measured against the matched null, and that null is negative (mean R_null −0.2892R) because the fixed 1.5/3 ATR race loses money on a random day in an uptrend. The event's own mean R is only +0.0780R after costs, so the spec must prove absolute expectancy, not just lift over the null.

The three fails are closed. `gap_volume` and `high52w` sat far below a null that is itself strongly positive (+0.58R, +0.44R), and `turn_of_month` is flat (−0.0453R). The next batch moves to a different information source (earnings calendars, sector flows), not to looser bars or re-parameterised versions of these.

## Disclosure

Every results doc carries the PIT members missing from the cache (survivorship that remains), every drop/skip counter, both arms' exit mix, the per-year table and the forward-drift table. All four ideas count events from 2011-01-01 (2010 bars only prime the indicators), so each year rule is 7 of 9 calendar years.
