# v147 Gate counterfactual: Part 2b, the light report store (V147-8)

> Part of the v147 plan, split from Part 2 to stay under the 1500-line cap. Header, Global Constraints, deviations, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v147-gate-counterfactual_0-index.md). **Never read this file whole**: `/task-brief V147-8` or `grep -n "^### Task V147-8:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_2b-report-store.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md) § The report (the persistence contract and v150's four requirements), § Pre-registered verdict / Freeze, § Testing (last bullet).

All commands run inside the plan's worktree `.claude/worktrees/2026-10-09-v147-gate-counterfactual` (created by V147-1). Paths below are relative to it. V147-8 depends on nothing in this plan (Group A, index § Parallelisation).

---

### Task V147-8: Light report store (atomic write, verdict-of-record carry-forward)

**Model:** sonnet — a small stdlib-only module whose contract (path, None cases, carry-forward, no heavy imports) is fully fixed by the ledger and v150's four requirements.

**Files:**
- Create: `swingbot/core/infra/gate_counterfactual_store.py`
- Create: `tests/infra/test_gate_counterfactual_store.py`

**Interfaces:**
- Consumes: `swingbot.config.DATA_DIR` (exists, `swingbot/config.py:64`); `jsonio.atomic_write_json(path: str, obj)` (temp file in the same directory, fsync, `os.replace`) and `jsonio.read_json(path, default)` (never raises; logs a corrupt file) (exist, `swingbot/core/infra/jsonio.py:52/80`).
- Produces (ledger): `report_path() -> Path` (`<config.DATA_DIR>/reports/gate-counterfactual.json`, resolved at call time so tests that repoint `config.DATA_DIR` are honoured); `load_report(path=None) -> dict | None` (None when the file is missing, empty, corrupt or not a JSON object); `write_report(result: dict, path=None) -> dict` (returns what it wrote; never mutates `result`). Consumers: V147-15 `build_report` writes through it and `gate_counterfactual_report` re-exports `load_report`; v150's endpoint imports this module directly.
- Carry-forward rule: cells are matched on `(cell["gate"], cell["population"])`. When the on-disk cell's `verdict_of_record` is complete (a dict whose `verdict`, `date` and `n` are all present and not `None`), it replaces the new cell's `verdict_of_record`; otherwise the new cell's value (a first reading's seed or `None`) is written as given. A new cell with no on-disk twin is written as given. Every other key — `verdict`, `n`, `latest`, `rows`, `generated_at` — is the latest reading (overwrite-latest retention).
- Imports only stdlib, `swingbot.config` and `swingbot.core.infra.jsonio`; a fresh-interpreter test proves `pandas`, `numpy` and `swingbot.core.backtesting` stay out of `sys.modules`.

- [ ] **Step 1: Write the failing tests**

Create `tests/infra/test_gate_counterfactual_store.py`:

```python
"""v147: the gate-counterfactual report file -- atomic, light to import, verdict of record frozen."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.infra import gate_counterfactual_store as store

REPO = Path(__file__).resolve().parents[2]
RECORD = {"verdict": "COSTS", "date": "2026-12-04", "n": 31}


def _cell(gate="risk_cap", population="live", *, verdict="INCONCLUSIVE", n=40, record=None):
    return {"gate": gate, "population": population, "verdict": verdict, "n": n,
            "verdict_of_record": record,
            "latest": {"difference": 0.12, "ci_low": -0.05, "ci_high": 0.3, "q": 0.4},
            "in_sample": False, "note": None}


def _result(*cells, generated_at="2026-12-04T21:00:00+00:00"):
    return {"generated_at": generated_at, "live_window": "2026-10-01..2026-12-04",
            "cells": list(cells), "rows": [{"gate": "risk_cap", "reason": "risk_cap", "population": "live",
                                            "over_cap": True, "in_sample": False}]}


@pytest.fixture
def path(tmp_path):
    return tmp_path / "reports" / "gate-counterfactual.json"


def test_the_default_path_is_under_data_reports_and_follows_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    assert store.report_path() == tmp_path / "reports" / "gate-counterfactual.json"


def test_load_is_none_before_the_first_run(path):
    assert store.load_report(path) is None


@pytest.mark.parametrize("content", ["", "{not json", "[1, 2]", "\"text\""])
def test_load_is_none_for_an_empty_corrupt_or_non_object_file(path, content):
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    assert store.load_report(path) is None


def test_write_then_load_round_trips_and_is_json_serialisable(path):
    written = store.write_report(_result(_cell(record=RECORD)), path)
    loaded = store.load_report(path)
    assert loaded == written == _result(_cell(record=RECORD))
    json.dumps(loaded)


def test_the_write_is_atomic_and_leaves_no_temp_file(path):
    store.write_report(_result(_cell()), path)
    assert sorted(p.name for p in path.parent.iterdir()) == ["gate-counterfactual.json"]


def test_the_first_reading_seeds_the_record_and_later_readings_never_replace_it(path):
    store.write_report(_result(_cell(verdict="COSTS", n=31, record=RECORD)), path)
    later = _cell(verdict="INCONCLUSIVE", n=55, record={"verdict": "INCONCLUSIVE", "date": "2027-01-08", "n": 55})
    written = store.write_report(_result(later, generated_at="2027-01-08T21:00:00+00:00"), path)
    (cell,) = written["cells"]
    assert cell["verdict_of_record"] == RECORD                       # frozen at the first reading
    assert (cell["verdict"], cell["n"]) == ("INCONCLUSIVE", 55)      # the latest reading is descriptive
    assert written["generated_at"] == "2027-01-08T21:00:00+00:00"
    assert store.load_report(path) == written


@pytest.mark.parametrize("partial", [None, {"verdict": "COSTS", "date": None, "n": 31}, {"verdict": "COSTS"}])
def test_an_incomplete_record_on_disk_is_not_carried_forward(path, partial):
    store.write_report(_result(_cell(verdict="WAITING", n=12, record=partial)), path)
    written = store.write_report(_result(_cell(verdict="COSTS", n=31, record=RECORD)), path)
    assert written["cells"][0]["verdict_of_record"] == RECORD


def test_cells_are_matched_on_gate_and_population(path):
    store.write_report(_result(_cell("risk_cap", "live", record=RECORD)), path)
    written = store.write_report(_result(_cell("risk_cap", "train", record=None),
                                         _cell("compression", "live", record=None),
                                         _cell("risk_cap", "live", record=None)), path)
    records = {(c["gate"], c["population"]): c["verdict_of_record"] for c in written["cells"]}
    assert records == {("risk_cap", "train"): None, ("compression", "live"): None, ("risk_cap", "live"): RECORD}


def test_the_input_is_never_mutated(path):
    store.write_report(_result(_cell(record=RECORD)), path)
    fresh = _result(_cell(record=None))
    before = copy.deepcopy(fresh)
    store.write_report(fresh, path)
    assert fresh == before


def test_a_corrupt_file_on_disk_is_overwritten_with_the_new_reading(path):
    path.parent.mkdir(parents=True)
    path.write_text("{torn", encoding="utf-8")
    written = store.write_report(_result(_cell(record=None)), path)
    assert store.load_report(path) == written


@pytest.mark.parametrize("heavy", ["pandas", "numpy", "swingbot.core.backtesting"])
def test_loader_imports_without_heavy_modules(heavy):
    code = ("import sys\n"
            "from swingbot.core.infra.gate_counterfactual_store import load_report\n"
            f"loaded = sorted(m for m in sys.modules if m.startswith({heavy!r}))\n"
            "assert not loaded, loaded\n"
            "print('light')\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True,
                          timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "light"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_gate_counterfactual_store.py`
Expected: FAIL — `ImportError: cannot import name 'gate_counterfactual_store'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/infra/gate_counterfactual_store.py`:

```python
"""v147: the gate-counterfactual report file, `data/reports/gate-counterfactual.json`.

The light half of the report: `gate_counterfactual_report.build_report` (analytics, pandas/numpy)
writes through `write_report`; v150's Reports endpoint and the analytics module's re-export read
through `load_report`. This module imports only the stdlib, `swingbot.config` and `jsonio`, so the
admin process can load a report without pandas, numpy or `swingbot.core.backtesting`
(tests/infra/test_gate_counterfactual_store.py proves it in a fresh interpreter).

Retention is overwrite-latest; the one thing never overwritten is a cell's `verdict_of_record` --
the first reading at distinct filled N >= 30 (spec § Freeze), carried forward from the file on disk.
"""
from __future__ import annotations

import copy
from pathlib import Path

from swingbot import config
from swingbot.core.infra import jsonio

REPORT_NAME = "gate-counterfactual.json"
RECORD_KEYS = ("verdict", "date", "n")


def report_path() -> Path:
    """`<DATA_DIR>/reports/gate-counterfactual.json`, read at call time (DATA_DIR is hot-reloadable)."""
    return Path(config.DATA_DIR) / "reports" / REPORT_NAME


def load_report(path=None) -> dict | None:
    """The last written report, or None when the file is missing, empty, corrupt or not a JSON object."""
    content = jsonio.read_json(str(path or report_path()), None)
    return content if isinstance(content, dict) else None


def _complete(record) -> bool:
    return isinstance(record, dict) and all(record.get(key) is not None for key in RECORD_KEYS)


def _records_on_disk(previous: dict | None) -> dict:
    """(gate, population) -> the complete verdict of record already on disk."""
    cells = (previous or {}).get("cells") or []
    return {(cell.get("gate"), cell.get("population")): cell["verdict_of_record"]
            for cell in cells if isinstance(cell, dict) and _complete(cell.get("verdict_of_record"))}


def write_report(result: dict, path=None) -> dict:
    """Atomically write `result` with every frozen verdict of record carried forward; return what was written.

    `result` itself is never mutated."""
    target = Path(path or report_path())
    frozen = _records_on_disk(load_report(target))
    out = copy.deepcopy(result)
    for cell in out.get("cells") or []:
        key = (cell.get("gate"), cell.get("population"))
        if key in frozen:
            cell["verdict_of_record"] = copy.deepcopy(frozen[key])
    jsonio.atomic_write_json(str(target), out)
    return out
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/infra/test_gate_counterfactual_store.py tests/infra/test_jsonio.py`
Expected: PASS. If the fresh-interpreter test fails, `swingbot/config.py` or `jsonio` started importing something heavy since 2026-10-10 (the brief measured both light): report it rather than moving the module.

- [ ] **Step 5: Complexity gate**

Run: `python -m radon cc -s -n C swingbot/core/infra/gate_counterfactual_store.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/infra/gate_counterfactual_store.py tests/infra/test_gate_counterfactual_store.py
git commit -m "feat(v147): light gate-counterfactual report store with frozen verdict of record (V147-8)"
```
