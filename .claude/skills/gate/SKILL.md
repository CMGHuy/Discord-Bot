---
name: gate
description: Pre-commit verification gate — syntax pass plus full suite compared against the recorded baseline, so a pre-existing failure is never mistaken for a regression.
disable-model-invocation: true
---

# Pre-commit gate

"Green" in this repo does **not** mean zero failures. It means *your diff added no
new failure*. There is a carried, wall-clock-dependent failure in the ledger since
Task E7. Treating it as a regression has already cost sessions; "fixing" it is a
forbidden side quest.

## Step 1 — Do not fight another session for the CPU

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object CPU -gt 300 |
  Select-Object Id, StartTime, CPU
```

A hit means a multi-hour walk-forward run is live. Wait, or run only the touched
test file. The full suite takes ~3 min serially and will be far slower under contention.

## Step 2 — Establish the baseline from the ledger, not from memory

Each ledger entry records the suite counts at that commit, so the ledger is
self-updating where a hardcoded number rots:

```powershell
Get-Content .superpowers/sdd/progress.md -Tail 3 |
  Select-String -Pattern 'full suite \d+/\d+' -AllMatches
```

Last known-good published baseline: **841 passed, 54 skipped, 1 failed** (~3m13s,
commit `a7d23ab`, 2026-07-25). Task count grows as tasks land tests, so trust the
ledger tail over that number.

The one permitted failure:

```
tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans
  (cancelled_expired != filled)
```

Pre-existing, expiry/wall-clock dependent. Its sibling
`test_pending_fills_when_price_crosses_trigger` passes on the same fixture — the
difference is `run_manager_tick()` going through real dates.

## Step 3 — Syntax pass

No `make` on Windows:

```powershell
python -m py_compile bot.py admin_ui.py
Get-ChildItem swingbot -Recurse -Filter *.py | ForEach-Object { python -m py_compile $_.FullName }
```

## Step 4 — Suite

```powershell
python -m pytest            # serial, matches the recorded baseline conditions
python -m pytest -n auto    # faster; only when the box is otherwise idle
```

Iterating on one file? `python -m pytest tests/test_edge_gates.py`. Do not
re-run the full suite to check a local change. Don't add `-q` — `pytest.ini`'s
`addopts` already sets it, and a second `-q` on the command line stacks to
quiet-level 2, which suppresses the final "N passed" summary line entirely.

## Step 5 — Compare and report honestly

Report the actual counts. Then exactly one verdict:

- **PASS** — counts match the ledger baseline and the only failure is
  `test_flag_on_polls_open_plans`.
- **FAIL** — any different count, or a second failure. That one is yours. Do not
  commit. Load `superpowers:systematic-debugging` before proposing a fix; guessing
  at backtest numbers and failing gates is expensive here.

Never state PASS without pasting the pytest summary line you are basing it on.

## Step 6 — Stage narrowly

Concurrent sessions share this tree, and uncommitted generated state has been
silently wiped before.

```powershell
git add <explicit paths>      # never git add -A
```

Commit generated artifacts (especially `validation_registry.json`) immediately.
Conventional commit, one per task, then update **both**
`docs/superpowers/plans/<plan>.md` (Progress block) and `.superpowers/sdd/progress.md`.
