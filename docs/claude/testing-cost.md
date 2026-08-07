# Test-suite cost (measured, not estimated)

Referenced from the root `CLAUDE.md`. Read this before optimising, timing, or
reasoning about how long the suite takes. Every number here was measured on
2026-08-07 at `main` = `017c777`, 12 logical cores. Full design:
`docs/superpowers/specs/2026-08-07-test-cost-reduction-design.md`.

## Baseline

**1145 collected — 1008 passed, 136 skipped, 1 xfailed, 0 failed.**

Green means **0 failed**. The single wall-clock-dependent test
(`test_flag_on_polls_open_plans`) is quarantined `xfail(strict=False)`, so no
judgment call is needed to tell it apart from a real regression. An `xpass`
there is fine; a `failed` anywhere is yours.

> Older docs record `841 passed, 54 skipped, 1 failed`. That baseline is
> **stale** — the suite has grown to 1145. Don't compare against it.

## Timings

| Config | Wall | Speedup |
| --- | --- | --- |
| Full suite, serial | 180.4s | 1.0x |
| **Full suite, `-n 4`** | **40.2s** | **4.5x** |
| Full suite, `-n auto` (12 workers) | 60.0s | 3.0x |
| Fast tier (9 heavy files excluded), serial | 27.1s | 6.7x |
| Fast tier, `-n 4` | 27.2s | no gain |

- **`-n 4` beats `-n auto`.** Over-subscribing 12 logical cores costs ~20s in
  worker startup and contention. Prefer `-n 4` on this box.
- **The fast tier gains nothing from parallelism** — at ~27s it is already at
  the fixed per-invocation overhead floor (~4.6s startup + 7.7s collection).
  Run it serial; workers only add cost.
- **Single file** (`test_universe.py`, 45 tests): ~7s wall, ~2.4-4.3s internal.

## Measuring is fragile — two traps

1. **Cool down 20s between runs.** Back-to-back runs inflate each other by up
   to 4x. This invalidated an entire round of measurements during design (a
   single file "took" 27s; cooled, it was 7s).
2. **Another session on this box changes everything.** The same `-n 4` full
   run that cools to 40.2s measured **110.7s** while a concurrent Claude
   session was working. Check for competing work before trusting a timing:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300
```

Counts are still valid under contention; only timings are not.

## Re-deriving the worker count on different hardware

`-n 4` is measured-optimal here, not a universal constant:

```powershell
foreach ($n in 2,4,6,8) { Start-Sleep 20; "n=$n"; Measure-Command { python -m pytest tests/ -n $n } | Select TotalSeconds }
```

## Where the time goes

Nine files are ~153s of the 180.4s serial suite (**85%**):

```
test_decision_chart.py      test_plan_chart_overlays.py   test_trade_chart_v2.py
test_portfolio_charts.py    test_chart_theme.py           test_analytics_charts.py
test_backtest_scenarios.py  test_growth_command.py        test_chart_cache.py
```

The 5 core chart files alone are 84s (43%) across 34 tests, rendering 16x9
PNGs at dpi=110-150. One trivial `savefig` is 0.23s;
`matplotlib`+`mplfinance` import is 3.8s *per process*. Forcing dpi=30 cuts
that tier to 44s — no test asserts on resolution.

## Gotcha: `-q` hides the counts

`pytest.ini` sets `addopts = -q`, and **pytest 9.1.1 suppresses the summary
count line under `-q`**. Any tooling that parses pass/fail counts must
override it, and must never read "no counts found" as success:

```powershell
python -m pytest tests/ -p no:cacheprovider -n 4     # no -q: prints the counts line
```
