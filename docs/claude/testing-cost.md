# Test-suite cost (measured, not estimated)

Referenced from the root `CLAUDE.md`. Read this before optimising, timing, or
reasoning about how long the suite takes. Every number here was measured on
2026-08-07 at `main` = `017c777`, 12 logical cores. Full design:
`docs/superpowers/specs/implemented/2026-08-07-v7-test-cost-reduction-design.md`.

## Baseline

**1145 collected — 1008 passed, 136 skipped, 1 xfailed, 0 failed.**

Green means **0 failed**. The single wall-clock-dependent test
(`test_flag_on_polls_open_plans`) WAS quarantined `xfail(strict=False)` when
this was measured; it was fixed on 2026-08-14 and the suite now carries no
xfail, so no
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
`matplotlib`+`mplfinance` import is 3.8s *per process*.

> **The dpi=30 speedup is UNVERIFIED.** An isolated design-phase measurement
> put the 5-file tier at 84s -> 44s, which is why `tests/conftest.py` renders
> at `TEST_DPI = 30`. A later same-conditions A/B measured the *opposite*
> (production 75.7s, dpi=30 137.5s) on a box under heavy external load, and
> the interleaved re-measurement needed to settle it was not run. Treat 84->44
> as unconfirmed. The fixture is correct and the tier is green either way;
> only the speed justification is open. Re-measure on an idle box with
> `SWINGBOT_TEST_FULL_DPI=1` as the control before quoting a number.

## Gotcha: `-q` hides the counts

`pytest.ini` sets `addopts = -q`, and **pytest 9.1.1 suppresses the summary
count line under `-q`**. Any tooling that parses pass/fail counts must
override it, and must never read "no counts found" as success:

```powershell
python -m pytest tests/ -p no:cacheprovider -n 4     # no -q: prints the counts line
```

## Runtime cost: the admin event watcher (NG24)

Not a test cost, but measured the same way and filed here because this is
where the repo keeps measured-not-estimated numbers. Measured 2026-08-12 on
the same box (Windows, NTFS, 12 logical cores), two runs, `time.process_time()
/ wall` over 30s windows. Spec: `2026-08-08-v12-realtime-push-design.md`,
which asks for a before/after because "it is small, but it never stops".

| | run 1 | run 2 |
| --- | --- | --- |
| One `stat()` sweep of all 20 paths | 1797 us | 1117 us |
| Admin idle, **no** event connection | 0.000% | 0.052% |
| Admin idle, **one** event connection | 0.624% | 0.728% |
| Attributable to the watcher | 0.62 pp | 0.68 pp |

**Verdict: not material — the 500ms interval stands.** ~0.65% of one core,
and only while a browser is actually connected: the watcher is started
lazily by the broker on the first SSE connection and stopped when the last
one closes, so an admin nobody has open measures at zero, which is what the
"no connection" row is.

Two things worth knowing before re-measuring:

- **The sweep is dominated by the 16 absent paths, not the 4 present ones.**
  Most watched paths (all four `.flag` files, and everything a fresh install
  has not written yet) do not exist, and each one costs a `FileNotFoundError`
  — an exception, not a syscall result. That is why a 20-path sweep costs
  ~1.5ms rather than ~50us. It also means the cost *falls* as the install
  fills in, which is the opposite of the intuition.
- **This is a pessimistic number for production.** `stat()` on Windows/NTFS
  is far more expensive than on the Linux container the admin actually
  deploys to. Treat ~0.65% as a ceiling, and re-measure on the Hetzner box
  before acting on it.

The sweep accounts for ~0.36 pp of the total (1.8ms x 2/s); the rest is the
run loop, which ticks every 250ms — the debounce granularity — so that a
settled event is not held back until the next sweep. Flushing is free
compared to sweeping, which is why the two cadences differ.

## Frontend: `ng test` times out before running anything (flaky)

`cd frontend && npx ng test --watch=false`. Vitest 4 via `@angular/build:unit-test`,
config in `frontend/vitest.config.ts`.

**Symptom:** exactly 60 seconds, then `[vitest-pool-runner]: Timeout waiting
for worker to respond`, `Test Files no tests`. Nothing ran.

**It is load, and a re-run fixes it.** 60s is `START_TIMEOUT`, a hard-coded
constant in vitest's pool runner — not an option, so it cannot be raised from
the config. Worker startup on this box occasionally exceeds it while an
Angular build or the Python suite is competing for the machine.

Two plausible-looking explanations were chased and are both wrong; don't
repeat them:

- **Not the `forks` pool.** Switching to `threads` made it pass at two spec
  files, and it failed again at three.
- **Not parallel worker startup.** `maxWorkers: 1` + `fileParallelism: false`
  made it pass at four, and it failed again at five — then the same command
  passed on retry with no change at all.

Those settings are still in the config: fewer workers is fewer chances to
trip the timeout, and these tests have no native modules or shared state, so
parallelism was buying wall-clock only. But they are mitigation, not a fix.

Same discipline as the Python suite above: **cool down, and don't measure or
diagnose while something else is running.**

## A second load-sensitive test: `test_analytics_perf`

`tests/test_analytics_perf.py::test_build_snapshot_5000_trades_under_2_seconds`
asserts a **wall-clock budget**, so it measures the machine as much as the
code. Observed on 2026-08-12 on a loaded box, same commit, consecutive runs:

| Run | build_snapshot(5000 trades) |
| --- | --- |
| in the full `-n 4` suite | 2.73s — FAILED |
| isolated, immediately after | 12.60s — FAILED |
| isolated, again | 3.23s — passed |

A 4x swing between two back-to-back runs of the same test. The same suite
passed 0-failed earlier the same day, when the full run took 180s rather
than 604s.

**Before believing this one, check the load.** It is not quarantined —
unlike `test_flag_on_polls_open_plans` it is a real budget worth keeping —
but a failure here on a busy box is evidence about the box. Re-run it
isolated on an idle machine before touching `swingbot/core/analytics/`.

## What the pass count means when it changes

Reference baseline: `1686 passed, 66 skipped, 0 failed`. **Green means
`0 failed`, and now also `0 xfailed`.**

That count dropped from 1898 on 2026-08-14 and **the drop is correct**, not lost
coverage: Release B deleted the Jinja UI, and with it the tests whose subject was
rendered HTML — 10 whole files plus 45 individually-removed tests that asserted
v1-against-Jinja parity or "the Jinja page still owns this URL". Builder-level
tests were kept untouched, which is what they were extracted for. An unexplained
drop from here is a different matter; investigate it.

The pass count drifts up as tasks land tests and concurrent sessions commit — a
*changed count* is not a failure; only `failed` is.

### The 66 skips are two parity files, and they are NOT dead weight

Every one of the 66 comes from `tests/test_exit_parity.py` and
`tests/test_sizing_parity.py`. Each is `3 tickers x 11 strategies x 2 horizons
= 66` cases; each skips exactly half. Run the pair alone and you get **66
passed, 66 skipped in 4.4s** — so half of this matrix is asserting real parity,
and "it mostly skips" is not a reason to delete it. That conclusion has been
reached once and reversed on the evidence; the numbers are here so it does not
get reached again.

The skip is at the END of the test body, not a guard at the top: when a
ticker/strategy/horizon produces no entry signals over the cached history there
is nothing to compare, so it skips rather than passing vacuously
(`test_sizing_parity.py:145`, `test_exit_parity.py:47`). Which combinations go
empty is a property of the *strategy at that horizon*, consistent across all
three tickers — VWAP/3m, Volume Profile at both, Support/Resistance 4w, RSI at
both, MACD 4w, EMA Crossover 3m, Elliott Wave 3m. `RSI Divergence` never skips.
**The number is therefore a function of `data/backtest_cache/`**: refresh it via
`scripts/data/fetch_backtest_data.py` and 66 moves without anything being wrong.

**Why deleting them would be expensive.** `test_sizing_parity.py` compares the
current `backtest._trade_plan_at` against `tests/fixtures/legacy_trade_plan_at.py`
— a frozen pre-extraction copy, and per that file's own docstring the *only
remaining independent old implementation*. `test_plan_engine_sizing.py` looks
like it covers the same ground and does not: it compares `plan_engine` against
the post-delegation `_trade_plan_at`, which is `plan_engine` calling itself
through one layer of indirection. Drop the parity file and nothing proves the
extraction preserved sizing behaviour.

**The real gap is CI, not the skips.** `data/backtest_cache/` is gitignored
(`.gitignore:20`, zero tracked files), so on CI the module-level `skipif` fires
and **all 132 cases skip** — CI reports ~136 skipped against a local 66. A
regression in sizing or exit parity cannot turn CI red. That guarantee is
currently enforced only on a machine that has run `fetch_backtest_data.py`, so
run the pair locally (4.4s) before trusting a green CI on anything touching
`plan_engine` sizing or `simulate_exit`.

### The long-standing `xfail` quarantine is gone (2026-08-14)

`test_flag_on_polls_open_plans` was quarantined as "wall-clock dependent", which
undersold it: the shared `_pending()` fixture is created at a fixed `2026-07-11`
with `expiry_bars=5`, while `_bars_since` counts real trading days from a real
data fetch. Once five trading days passed, the plan expired before it could fill
— so it was not failing intermittently, it was failing **permanently and
drifting further every day**, behind a `strict=False` that could never become an
`xpass`. Fixed by injecting `_bars_since` the same way the test already injected
`_price_fn`, plus a second test covering expiry through the same path.

If a new `xfailed` appears, it is new — investigate it rather than assuming it is
this one.
