# v211 shock-short screens — outcome-blind preflight

**Spec:** `docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md` § Track 2 → Printed alongside each verdict
**Plan:** `docs/superpowers/plans/2026-11-06-v211-shock-short-screens_0-index.md` (V211-13)
**Run date:** 2026-11-10 (Berlin)
**Definition commit:** fb6d5a62ce9a28b938ad76a1e0a28cd616b21721
**Context pins:** `results/2026-10-18-v174-context-hashes.json`: `BREADTH_ATR1` b5bcbe2d7d4b, `^VIX` e67ada509441 (commit 2970178a). The pin step also pinned `^VIX3M` 722b90510043, because it pins every registered context file; `^VIX3M` is the context of the still-unscreened `vix_curve_calm` and neither shock idea uses it.

Printed before either shot and before any race. **It is outcome-blind and decides nothing:** both shots run as registered (spec § Printed alongside each verdict). Shock weeks are the bootstrap's clusters (ISO weeks), so they state the effective N; a year with no events counts against the 7-of-9 rule.

## Context build

- `^VIX.csv`: 2768 rows, 2009-01-02..2019-12-31, 0 NaN. An older unpinned copy (truncated, starting 2009-06-01, whose 2666 dates matched this fetch exactly) was backed up outside the repo and replaced, with partner approval.
- `BREADTH_ATR1.csv`: 2666 sessions, 2009-06-01..2019-12-31 (starts at the shared `CONTEXT_START` constant by design), Close 0.0-0.97, 0 NaN; sessions at `BREADTH_ATR1 >= 0.40`: 80. Coverage per year (members with a finite move / PIT members; 224 PIT members have no cache file):

- 2009: 286.7 of 498.9 PIT members with a finite move per session (57.5%)
- 2010: 327.3 of 498.2 PIT members with a finite move per session (65.7%)
- 2011: 330.9 of 497.0 PIT members with a finite move per session (66.6%)
- 2012: 341.1 of 497.0 PIT members with a finite move per session (68.6%)
- 2013: 351.0 of 497.0 PIT members with a finite move per session (70.6%)
- 2014: 357.2 of 498.2 PIT members with a finite move per session (71.7%)
- 2015: 368.3 of 500.6 PIT members with a finite move per session (73.6%)
- 2016: 387.9 of 505.4 PIT members with a finite move per session (76.8%)
- 2017: 403.1 of 506.0 PIT members with a finite move per session (79.7%)
- 2018: 412.1 of 505.6 PIT members with a finite move per session (81.5%)
- 2019: 425.5 of 505.0 PIT members with a finite move per session (84.3%)

Eight of eleven years sit under about 80% coverage. This is reported, not fixed: the definition is frozen, and coverage never decides whether to shoot.

## `shock_support_break_short`

(Ticker progress lines dropped; the doc's own headings demoted to H3.)

### v182 count: `shock_support_break_short` (outcome-blind: no race, no R)

**Window:** 2010-01-01..2019-12-31 (events from 2011-01-01). **Universe:** 719 PIT S&P 500 members, 492 counted, 213 missing from the cache, 14 empty frames.
**Idea:** short, entry next_open, fixed race, cap 10 bars.
**Command:** `python scripts/backtest/screen_idea.py --idea shock_support_break_short --count-only`

| step | events |
|---|---:|
| raw events | 10946 |
| dropped_nonmember | 2109 |
| dropped_warmup | 881 |
| dropped_window | 0 |
| skipped_overlap (full-cap bound) | 1436 |
| dropped_no_match | 468 |
| **count N** | **6052** |

Non-overlap here assumes every trade lasts the full 10-bar cap, so the real run books at least as many events before the null match.

**Gate:** N = 6052 ≥ 300: the one shot may run.

### Preflight — shock days, weeks and events per year (outcome-blind)

Printed before the shot from the context and the counted events only; it never decides whether the shot runs (the shot runs as registered). A shock week is an ISO week; a week spanning New Year counts once in each year.
Years without a shock day: 0 of 9.

| year | shock days | shock weeks | events |
|---:|---:|---:|---:|
| 2011 | 34 | 13 | 746 |
| 2012 | 10 | 6 | 475 |
| 2013 | 10 | 5 | 469 |
| 2014 | 26 | 14 | 1022 |
| 2015 | 20 | 8 | 784 |
| 2016 | 13 | 6 | 714 |
| 2017 | 4 | 2 | 186 |
| 2018 | 17 | 8 | 1018 |
| 2019 | 12 | 8 | 638 |
| **total** | **146** | **70** | **6052** |

## `shock_failed_bounce_short`

(Ticker progress lines dropped; the doc's own headings demoted to H3.)

### v182 count: `shock_failed_bounce_short` (outcome-blind: no race, no R)

**Window:** 2010-01-01..2019-12-31 (events from 2011-01-01). **Universe:** 719 PIT S&P 500 members, 492 counted, 213 missing from the cache, 14 empty frames.
**Idea:** short, entry next_open, fixed race, cap 10 bars.
**Command:** `python scripts/backtest/screen_idea.py --idea shock_failed_bounce_short --count-only`

| step | events |
|---|---:|
| raw events | 14352 |
| dropped_nonmember | 3017 |
| dropped_warmup | 1530 |
| dropped_window | 0 |
| skipped_overlap (full-cap bound) | 1613 |
| dropped_no_match | 319 |
| **count N** | **7873** |

Non-overlap here assumes every trade lasts the full 10-bar cap, so the real run books at least as many events before the null match.

**Gate:** N = 7873 ≥ 300: the one shot may run.

### Preflight — shock days, weeks and events per year (outcome-blind)

Printed before the shot from the context and the counted events only; it never decides whether the shot runs (the shot runs as registered). A shock week is an ISO week; a week spanning New Year counts once in each year.
Years without a shock day: 0 of 9.

| year | shock days | shock weeks | events |
|---:|---:|---:|---:|
| 2011 | 34 | 13 | 1428 |
| 2012 | 10 | 6 | 484 |
| 2013 | 10 | 5 | 700 |
| 2014 | 26 | 14 | 1374 |
| 2015 | 20 | 8 | 1010 |
| 2016 | 13 | 6 | 742 |
| 2017 | 4 | 2 | 355 |
| 2018 | 17 | 8 | 1021 |
| 2019 | 12 | 8 | 759 |
| **total** | **146** | **70** | **7873** |

## Reading (outcome-blind)

- `shock_support_break_short`: 6052 counted events across 146 shock days and 70 shock weeks (2011-2019); years without a shock day: 0 of 9; no year has zero events.
- `shock_failed_bounce_short`: 7873 counted events across the same 146 shock days and 70 shock weeks; years without a shock day: 0 of 9; no year has zero events.
- Both counts clear the 300 gate. The preflight is outcome-blind (no R, no win rate, no guess at a verdict) and decides nothing: both shots run as registered. The 70 shock weeks, not the event counts, are the effective N for the bootstrap.
- That gate line is the v182 convention; spec v209 § Track 2 overrides it for these two ideas: the preflight never decides whether to shoot.
