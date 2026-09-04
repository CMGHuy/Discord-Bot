# v71 — Silent-failure hardening, part 3: the gate and verification

> **Part of a split plan.** The header block, Global Constraints and the
> cross-part map live in `2026-09-04-v71-silent-failure-hardening_0-index.md`.
> Read that first — this file carries only its phases.

# Phase D — Close the prevention gap

## Parallelisation

Sequential: H13 before H14 — the gate cannot land red, and H13 fixes the only
current violations.

### Task H13: Import ScanProgress where it is annotated

Four annotations name a symbol their module never imports. Harmless at runtime
(they are quoted), but they are the only thing standing between the tree and a
clean pyflakes run.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py:384`,
  `swingbot/core/scanning/fetch.py:169,250,333`
- Test: none — verified by the gate itself in H14.

- [ ] **Step 1: Confirm the four violations**

Run: `python -m pyflakes swingbot/core/scanning/analyze.py swingbot/core/scanning/fetch.py`
Expected: exactly four `undefined name 'ScanProgress'` lines.

- [ ] **Step 2: Import the symbol in both modules**

`ScanProgress` is defined in `swingbot/core/scanning/scan_run.py:51`. Both
modules are imported *by* `scan_run`, so a plain module-level import risks a
cycle. Use a `TYPE_CHECKING` guard, which costs nothing at runtime and is
exactly what quoted annotations are for.

In `swingbot/core/scanning/analyze.py`, after the existing `import os`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scan_run import ScanProgress
```

Add the identical block to `swingbot/core/scanning/fetch.py` after its
`import time`.

- [ ] **Step 3: Confirm pyflakes is clean on both files**

Run: `python -m pyflakes swingbot/core/scanning/analyze.py swingbot/core/scanning/fetch.py`
Expected: no `undefined name` lines. (Unused-import warnings are out of scope —
the gate in H14 filters to undefined names only.)

- [ ] **Step 4: Confirm no import cycle was introduced**

Run: `python -c "import swingbot.core.scanning.engine"`
Expected: no output, exit 0.

- [ ] **Step 5: Run the scanning tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_scanning_package_structure.py`
Expected: `VERDICT: PASS`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/analyze.py swingbot/core/scanning/fetch.py
git commit -m "fix(v71): import ScanProgress where its annotations reference it"
```

### Task H14: Gate undefined names in the full test run

**Files:**
- Modify: `scripts/dev/testrun.py:153-192` (`main()`)
- Test: `tests/scripts/test_testrun_lint_gate.py` (create)

**Interfaces:**
- Produces: `testrun.undefined_names() -> list[str]` — pyflakes
  `undefined name` lines over tracked Python, empty when clean.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_testrun_lint_gate.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))


def test_undefined_names_flags_a_broken_module(tmp_path):
    import testrun

    bad = tmp_path / "bad_module.py"
    bad.write_text("def go():\n    return not_a_real_name\n")

    found = testrun.undefined_names([str(bad)])

    assert len(found) == 1
    assert "not_a_real_name" in found[0]


def test_undefined_names_is_clean_on_a_good_module(tmp_path):
    import testrun

    good = tmp_path / "good_module.py"
    good.write_text("import os\n\n\ndef go():\n    return os.getcwd()\n")

    assert testrun.undefined_names([str(good)]) == []


def test_the_repo_itself_has_no_undefined_names():
    """The gate must be green on the tree it is about to police."""
    import testrun

    assert testrun.undefined_names() == []
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/scripts/test_testrun_lint_gate.py -v`
Expected: **FAIL** — `AttributeError: module 'testrun' has no attribute
'undefined_names'`.

- [ ] **Step 3: Implement the check**

Add to `scripts/dev/testrun.py`, above `main()`:

```python
def undefined_names(paths: list[str] | None = None) -> list[str]:
    """pyflakes `undefined name` findings over tracked Python.

    Undefined names only -- not unused imports. This is the class that took
    production down twice (the missing _send_alerts import, the missing
    _MANUAL_CLOSE_QUEUE reference): a NameError that py_compile cannot see,
    that no test covered, and that ran for five days behind a broad
    try/except. Everything else pyflakes reports is style, and gating style
    here would mean either a cleanup first or a blanket suppression.
    """
    if paths is None:
        tracked = subprocess.run(
            ["git", "ls-files", "*.py"],
            capture_output=True, text=True, cwd=ROOT,
        )
        paths = [p for p in tracked.stdout.split("\n") if p]
    if not paths:
        return []
    proc = subprocess.run(
        [sys.executable, "-m", "pyflakes", *paths],
        capture_output=True, text=True, cwd=ROOT,
    )
    return [ln for ln in proc.stdout.split("\n") if "undefined name" in ln]
```

Check the module's existing names first: it may already define `ROOT` (if it is
called something else, use that) and already import `subprocess` and `sys`. Add
only what is missing.

- [ ] **Step 4: Run it as part of the `full` profile**

In `main()`, immediately after `args = ap.parse_args()`:

```python
    if profile == "full":
        undefined = undefined_names()
        if undefined:
            print(f"VERDICT: FAIL  {len(undefined)} undefined name(s) -- "
                  f"this is the class that caused two production outages")
            for line in undefined[:10]:
                print(f"  {line}")
            return 1
```

Place it after the `profile` variable is resolved from the escalation block, so
an escalated `fast` run is gated too. Only `full` pays the ~1s cost — `file`
and `fast` stay fast for iteration.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_testrun_lint_gate.py`
Expected: `VERDICT: PASS`

- [ ] **Step 6: Prove the gate actually fires**

```bash
printf 'def go():\n    return definitely_not_defined\n' > swingbot/_gate_probe.py
python scripts/dev/testrun.py full
```

Expected: `VERDICT: FAIL  1 undefined name(s) ...`, naming
`swingbot/_gate_probe.py`, and **no pytest run**. Then remove the probe:

```bash
rm swingbot/_gate_probe.py
```

A gate nobody watched fail is a gate nobody knows works. This step is not
optional.

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/testrun.py tests/scripts/test_testrun_lint_gate.py
git commit -m "feat(v71): fail the full run on undefined names"
```

---

# Phase E — Verification

## Parallelisation

Sequential and alone. This is the plan's single full-suite run.

### Task H15: Full-suite verification

- [ ] **Step 1: Confirm the tree is clean and everything is committed**

Run: `git status --short`
Expected: no modified or staged files. `data/universe/rs_cache.json` may appear
as untracked runtime data — leave it alone, do not commit it.

- [ ] **Step 2: Run the full Python suite once**

Run: `python scripts/dev/testrun.py full` (or dispatch the `test-runner`
subagent so its ~1150 progress lines stay out of this context).

Expected: `VERDICT: PASS`, `0 failed`, `0 xfailed`. The last recorded baseline
was 2672 passed / 70 skipped; a changed pass count is not itself a failure, a
non-zero failed or xfailed count is.

**If it is not green, fix forward from those failures** — they are this plan's
regressions, and this task is not done until the run is green.

- [ ] **Step 3: Run the full frontend suite once**

Run: `cd frontend && npm test`
Expected: green, no failing specs.

- [ ] **Step 4: Verify the four fixed defects by hand**

```bash
python -m pyflakes $(git ls-files '*.py') | grep -c "undefined name"
```
Expected: `0`.

Then confirm the retrospective renders rather than raising:

```bash
python -c "
import datetime as dt
from swingbot.core.tracking import retrospective as r
t = [{'ticker':'AAPL','status':'closed','confidence_level':3,
      'opened_at':'2026-09-03T08:00:00+00:00','closed_at':'2026-09-03T18:00:00+00:00',
      'direction':'bullish','entry':100.0,'stop_loss':95.0,'exit_price':101.0}]
print('\n'.join(r.build_daily_retrospective(t, today=dt.date(2026,9,3)))[:400])
"
```
Expected: a rendered report containing `Level 3` and `n/a`, no traceback.

- [ ] **Step 5: Commit any fixes made during this task**

If Steps 2-4 required fixes, commit them individually with `fix(v71): ...`
messages describing what regressed. If nothing needed fixing, there is nothing
to commit — do not create an empty commit.

---

## After this plan

Not part of it, listed so they are not lost:

- **Release.** Two independent bumps — `bot 1.6.0 → 1.6.1` and
  `ui 1.11.0 → 1.11.1` — each its own commit, and `version_history.json`
  regenerated and committed **after** each bump lands (the local gate runs
  before the bump, so it structurally cannot catch a miss).
- **Deploy and confirm.** The whole point is an evening retrospective that
  posts. After deploying, check the next 21:15 run in
  `/opt/swing-bot/logs/bot.log` — not `docker logs`, which is empty after a
  redeploy.
- **v72** — the deferred audit: 248 `except Exception` handlers, the 125 unused
  imports and the dead-and-shadowed `alerts` import at `loops.py:17`, the
  placeholder-less f-string at `scripts/backtest/measure_alert_density.py:590`,
  and the yfinance false-delisted noise.
