---
name: gate
description: Pre-commit verification gate — syntax pass plus the full suite via scripts/testrun.py, where green means literally zero failures.
disable-model-invocation: true
---

# Pre-commit gate

Green means **`0 failed`**. Nothing subtler.

That used to require judgment: the suite carried one wall-clock-dependent
failure, and every run meant deciding whether the single failure was *that*
one or a real regression. It was quarantined `xfail(strict=False)` to make the
comparison mechanical, and **as of 2026-08-14 it is fixed rather than
quarantined** — the test injects its bar count instead of counting real
trading days from a fixed 2026-07-11 fixture. The suite now carries **no
xfail at all**, so `0 failed` and `0 xfailed` are both expected. A new
`xfailed` is a new quarantine someone added; find out why.

## Step 1 — Do not fight another session for the CPU

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object CPU -gt 300 |
  Select-Object Id, StartTime, CPU
```

A hit means a multi-hour walk-forward run is live. Wait, or run only the
touched file. Contention does not change counts, but it wrecks timings: the
same suite has measured 40s idle and 262s under load.

## Step 2 — Syntax pass

No `make` on Windows:

```powershell
python -m py_compile bot.py admin_ui.py
python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('swingbot', quiet=2) else 1)"
```

## Step 3 — Suite

```powershell
python scripts/testrun.py full
```

Full output is parked in `.pytest-last-run.log`; stdout is a one-line verdict
and stderr is progress. Never run bare `pytest` for a gate — `pytest.ini` sets
`addopts = -q`, and pytest 9.1.1 prints **no summary counts line** under `-q`.

Iterating rather than gating? `python scripts/testrun.py fast` (~27s, skips
the render-heavy tier and auto-escalates to `full` if you touched
charts/templates/static), or `... file tests/test_edge_gates.py` for one file.
Do not re-run the full suite to check a local change.

For a gate run, prefer dispatching the `test-runner` subagent: it returns the
verdict and nothing else, so ~1150 progress lines never reach your context.

## Step 4 — Read the verdict

The wrapper prints exactly one of:

- `VERDICT: PASS` — proceed.
- `VERDICT: FAIL` — yours. Do not commit. Load
  `superpowers:systematic-debugging` before proposing a fix; guessing at
  numbers and failing gates is expensive here.
- `VERDICT: UNKNOWN` — the output could not be parsed. A tooling problem, and
  **never** to be read as success. Investigate the wrapper or the exit code.

Reference baseline: **1686 passed, 66 skipped, 0 xfailed, 0 failed**
(1752 collected). The pass count drifts upward as tasks land tests and concurrent
sessions commit — a changed pass count is not itself a failure. `0 failed` is
the check. An `xpass` on the quarantined test is also fine.

Never state PASS without pasting the `VERDICT:` line you are basing it on.

## Step 5 — Stage narrowly

Concurrent sessions share this tree, and uncommitted generated state has been
silently wiped before.

```powershell
git add <explicit paths>      # never git add -A
```

Commit generated artifacts (especially `validation_registry.json`)
immediately. Conventional commit, one per task, then update **both**
`docs/superpowers/plans/<plan>.md` (Progress block) and
`.superpowers/sdd/progress.md`.
