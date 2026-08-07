# Test-Suite Cost Reduction — Design

**Date:** 2026-08-07
**Status:** Approved for planning (plan: `docs/superpowers/plans/2026-08-07-test-cost-reduction-v7.md`)

## Problem

Every implementation task in this repo ends with a 1145-test suite run. At
~3 minutes serial, repeated mid-implementation, per plan task, at the
pre-commit gate, and again while debugging, this dominates both wall-clock
time and the agent context budget. Three costs were named as equally painful:
Claude context/tokens, wall-clock time, and API spend.

These are two separable problems, and conflating them is why the obvious
fixes have not helped:

- **Wall-clock**: how long pytest takes to run.
- **Context/tokens**: how much pytest *output* lands in the agent's context.

The second is independent of the first. A 5-second suite that dumps 900
progress dots and a traceback still costs thousands of tokens.

## Measurements

All figures measured on this machine (12 logical cores), 2026-08-07, at
`main` = `017c777`. Runs were separated by a 20-second cooldown; back-to-back
runs inflate each other by up to 4x, which invalidated an earlier round of
measurements and is the reason the cooldown is mandatory when re-measuring.

### Suite shape

| Metric | Value |
| --- | --- |
| Tests collected | **1145** (1008 passed, 136 skipped, 1 failed) |
| Test files | 113 |
| Collection only | 7.7s |
| Fixed overhead per pytest invocation | ~4.6s |
| Single file (`test_universe.py`, 45 tests) | 2.4-4.3s internal, ~7s wall |

> **CLAUDE.md's recorded baseline (`841 passed, 54 skipped`) is stale** — the
> suite has grown to 1145 collected. The `/gate` skill instructs comparing
> against that number, so the gate is currently comparing against a baseline
> that no longer exists. T12 corrects this.

> **`-q` suppresses the summary count line in pytest 9.1.1.** Every count
> above was obtained by running *without* `-q`. `pytest.ini` sets
> `addopts = -q`, so any tooling that parses counts must override it. This
> constrains the wrapper's parser (T4).

### Parallelism (the dominant lever)

| Config | Wall | Speedup |
| --- | --- | --- |
| Full suite, serial | 180.4s | 1.0x |
| **Full suite, `-n 4`** | **40.2s** | **4.5x** |
| Full suite, `-n auto` (12 workers) | 60.0s | 3.0x |
| Fast tier (9 heavy files excluded), serial | 27.1s | 6.7x |
| Fast tier, `-n 4` | 27.2s | no gain |

**Variance caveat:** these four rows were taken in one script with identical
20s cooldowns, so they are internally comparable. An *uncooled* `-n 4` run
measured 60.5s against the cooled 40.2s — so treat `-n 4` as **~40-60s
depending on machine state**, not a hard 40s. The `-n 4` < `-n auto` ordering
is a 50% gap between equally-cooled runs and is judged real, but it has not
been replicated across sessions.

Two non-obvious results:

1. **`-n 4` beats `-n auto`.** Over-subscribing 12 logical cores costs ~20s
   in worker startup and contention. `pytest.ini` and the `/gate` skill
   currently both recommend `-n auto`; that advice is wrong on this hardware.
2. **The fast tier does not benefit from parallelism.** At 27s it is already
   at the fixed-overhead floor, so it must run serial. Adding workers only
   adds startup cost.

### Where the time is

Nine files account for ~153s of the 180.4s serial suite (**85%**):

```
test_decision_chart.py      test_plan_chart_overlays.py   test_trade_chart_v2.py
test_portfolio_charts.py    test_chart_theme.py           test_analytics_charts.py
test_backtest_scenarios.py  test_growth_command.py        test_chart_cache.py
```

The 5 core chart files alone are 84s (43% of the suite) across 34 tests.
They render 16x9 PNGs at dpi=110-150 via matplotlib/mplfinance. Rendering is
genuinely expensive: one trivial `savefig` is 0.23s, and
`matplotlib`+`mplfinance` import costs 3.8s *per process*.

Forcing dpi=30 cuts that tier **84s -> 44s**. No test asserts on pixel
dimensions, resolution, or DPI, so this is assertion-safe — with one
exception, which is itself the finding below.

### The `getsize` proxy

24 chart assertions take the form `assert os.path.getsize(path) > N`, a
stand-in for "did it actually render something rather than a blank canvas".
At dpi=30, `test_heat_treemap_renders` fails on `3719 > 5000` — not a real
regression, just the proxy breaking. These assertions are simultaneously the
reason the tier is slow and a weak check.

### Known-failing test

`tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans` fails on
wall-clock/expiry dependence (`cancelled_expired` != `filled`). Because the
baseline is "1 failed", every run requires a human or model judgment call to
distinguish it from a real regression — a cost the `/gate` skill spends ~40
lines mitigating.

## Design

### Priority order

Ordered by measured value per unit of effort, which is **not** the order
these ideas were originally proposed in:

1. **`-n 4` as the default** — 180s -> 40s. One config change. ~90% of the
   available wall-clock win.
2. **Quiet wrapper + subagent delegation** — the entire token/API-spend half
   of the problem. Independent of wall-clock.
3. **`xfail` quarantine** — makes the verdict machine-checkable.
4. **Tiering (`slow` marker)** — 40s -> 27s on the inner loop. Real but
   modest once (1) is in place.
5. **Chart-test refactor** — primarily an *assertion-quality* improvement;
   the speed benefit is largely already captured by (1).

### Worker count

`-n 4`, not `-n auto`. Encoded in the wrapper rather than in `addopts`, so
the bare `python -m pytest` that `/gate` documents keeps its current serial
semantics and remains directly comparable to the recorded baseline.

`-n 4` is measured-optimal on a 12-logical-core machine. It is a starting
value, not a universal constant; the plan records how to re-derive it.

### Tiers

One registered marker, `slow`, applied as module-level
`pytestmark = pytest.mark.slow` (one line per file, not per test) to the nine
heavy files.

| Invocation | Scope | Expected |
| --- | --- | --- |
| `python scripts/testrun.py fast` | `-m "not slow"`, serial | ~27s |
| `python scripts/testrun.py full` | everything, `-n 4` | ~40s |
| `python scripts/testrun.py file <path>` | one file, serial | ~7s |
| `python -m pytest` | unchanged serial default | ~180s |

`-m "not slow"` is deliberately **not** added to `addopts`. Putting it there
would silently make the documented bare `python -m pytest` skip 85% of the
suite — precisely the class of silent no-op that
`docs/claude/known-traps.md` exists to catch.

**Auto-escalation:** `fast` inspects `git diff --name-only HEAD` and
transparently escalates to the `full` profile when anything under
`swingbot/core/charts/`, `swingbot/admin/templates/`, or
`swingbot/admin/static/` has changed, printing one line saying it did. This
closes the coverage gap that tiering otherwise opens, without requiring the
caller to remember.

### The wrapper: `scripts/testrun.py`

The single entry point any agent calls. Contract:

- Full pytest output goes to `.pytest-last-run.log` (gitignored).
- Progress goes to **stderr**, one flushed line per completed file, per the
  CLAUDE.md rule for long-running scripts. Never on the read path.
- **stdout is a 1-3 line verdict only**:
  ```
  VERDICT: PASS  862 passed, 54 skipped, 1 xfailed, 0 failed  in 40.2s
  ```
  On failure: the summary, up to 10 failing node IDs, and the log path.
  Never tracebacks.
- Exit code mirrors pass/fail so it composes with other tooling.

This is the core of the token fix: a run costs ~50 tokens to read instead of
hundreds or thousands.

### Subagent delegation

A `test-runner` subagent (`.claude/agents/test-runner.md`), mirroring the
existing `backtest-runner` pattern (tools: `Bash, Read, Grep`), owns
full-suite runs and returns only the verdict. Full pytest output never
enters the main session context at all.

### Quarantine

`test_flag_on_polls_open_plans` gets
`@pytest.mark.xfail(strict=False, reason=...)`. The baseline becomes
**0 failed, 1 xfailed**, so "green" is a machine comparison rather than a
judgment call. This is quarantining, not fixing — the underlying wall-clock
dependency is untouched, and CLAUDE.md's prohibition on "fixing" it stands.

### Chart-test refactor

Ordered, because the reverse order breaks the suite:

1. **`assert_rendered(path)`** helper in `tests/conftest.py` replaces all 24
   `getsize` proxies. Uses PIL (12.3.0, already installed — no new
   dependency): assert the file decodes, has non-zero dimensions, and
   contains more than a trivial number of distinct colors. Resolution-
   independent, so it survives any DPI and is a genuinely stronger check
   than a byte count.
2. **Autouse low-DPI fixture** forcing `figure`/`subplots`/`savefig` to
   dpi=30, with a `SWINGBOT_TEST_FULL_DPI=1` escape hatch for when a
   test-generated PNG needs to be eyeballed.

Step 1 must land before step 2, or `test_heat_treemap_renders` fails exactly
as it did under measurement.

## Non-goals

- **`pytest-testmon`** (coverage-based automatic selection). Rejected: a new
  dependency plus a coverage DB that goes stale and silently under-selects.
  In a repo where a missed regression can cost a backtest session, silent
  under-selection is the wrong failure mode.
- **Fixing the wall-clock test.** Explicitly a forbidden side quest per
  CLAUDE.md. Quarantine only.
- **Reducing the ~4.6s fixed pytest startup.** Investigated; it is spread
  across interpreter start, conftest imports (1.4s), and collection (7.7s
  for the full tree). No single dominant cause worth attacking.
- **Changing what any test asserts**, beyond replacing the 24 `getsize`
  proxies with a strictly stronger check.

## Success criteria

| Measure | Before | Target |
| --- | --- | --- |
| Inner-loop run | 180s | <= 30s |
| Pre-commit gate | 180s | <= 60s |
| Context cost per run | hundreds-thousands of tokens | ~50 tokens |
| Gate verdict | manual baseline comparison | machine-checkable (0 failed) |
| Chart tier | 84s | ~44s |
| Recorded baseline | stale (841/54, suite is now 1145) | current and self-checking |

Every task must leave the suite green, where green now means **0 failed,
1 xfailed** against **1145 collected** (1008 passed, 136 skipped pre-change).
