# Admin read performance, Layer 1 -- Part 1b: money references and frozen goldens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-d. Measurement stays in the product", "Testing".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract.

V205-4b is the second half of V205-4 (split at 20 KB). It runs directly after V205-4 (part 1) and before V205-5 (part 2): V205-5's budgets and every refactor from V205-7 on are measured against the goldens it freezes.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

# Phase 1 -- Measurement (L1-d), continued

### Task V205-4b: Money references, the recorder and the frozen goldens

**Model:** opus — the money pointers are found by probe but valued by hand, and the goldens are recorded exactly once from unchanged code.

**Files:**
- Create: `tests/admin_perf/money_reference.py`
- Create: `tests/admin_perf/record_golden.py`
- Create: `tests/admin_perf/golden/<name>.json`, one per `ENDPOINTS` key (8 files, written by the recorder, never by hand)
- Modify: `tests/admin_perf/test_golden_endpoints.py` (V205-4's file: append the golden and money tests)

**Interfaces:**
- Consumes (V205-4): `golden_book` (`ENDPOINTS`, `golden_path`, `resolve`, `mask`, `diff_pointers`, `MASK`, `GOLDEN_DIR`, `VOLATILE_KEYS`), fixtures `golden_seed` (`set_fx(scale)`), `frozen_clock`, `logged_in`, helper `_get(client, name)`.
- Produces (index "Golden book"): `money_reference.EXPECTED_MONEY: dict[str, dict[str, float | None]]` (endpoint name -> JSON pointer -> hand-computed value; exactly the FX-sensitive pointers) and its named constants (`T2_AAPL_WIN`, `DAY_2026_11_03`, ...); `record_golden.write_golden(name, payload) -> bool` (never overwrites), `record_golden.main() -> int`; the 8 golden files. V205-7..V205-10 must pass them unchanged; V205-15/16 edit only `money_reference.py` (and V205-15 the seed).

**Rules (index Global Constraints):** goldens are recorded once from today's unchanged code and never regenerated or edited. Money compares against `EXPECTED_MONEY`: literals or arithmetic over this module's constants, never `fx_convert`. A failing golden later means the code is fixed, never the golden.

**The book** (EUR account, balance 10,000 from `admin_app`; `AAPL` is the one USD ticker; frozen now = 2026-11-04 12:00 UTC = 13:00 Berlin, CET):

| Trade | Ticker | Status | Closed (UTC) | Amount (quote ccy) | Note |
|---|---|---|---|---|---|
| T1 | SAP.DE | win | 2026-11-03 14:00 | +120.00 EUR | no conversion |
| T2 | AAPL | win | 2026-11-03 20:30 | +50.00 USD | 21:30 Berlin, same day |
| T3 | AAPL | loss | 2026-11-02 23:30 | -30.00 USD | 00:30 Berlin **11-03**: a UTC/Berlin boundary |
| T4 | AAPL | win, 2 legs | leg 1 2026-10-29 15:00, leg 2 2026-11-02 15:00 | +70.00 USD (legs 50.00 + 20.00) | leg 1 exits on the day after the 0.0 close |
| T5 | AAPL | open (plan P1 ACTIVE) | -- | unrealised 10 x (104 - 100) = +40.00 USD | live price 104 |
| T6 | SAP.DE | open | -- | unrealised 5 x (212 - 200) = +60.00 EUR | live price 212 |

`USDEUR=X` closes: 10-26 0.8600, 10-27 0.8620, **10-28 0.0** (non-positive), 10-29 0.8650, 10-30 0.8640, (10-31, 11-01 weekend, no bar), 11-02 0.8680, 11-03 0.8700, 11-04 0.8720.

- [ ] **Step 1: Write `money_reference.py` (constants first; the pointers come in Step 4)**

Create `tests/admin_perf/money_reference.py`:

```python
"""Hand-computed account-currency (EUR) money of the golden book (v205 V205-4b).

Never computed through fx_convert. Today's rule (fx.py `_close_on_or_before`,
fx_convert `_day`): the rate is the last positive USDEUR=X close ON or before the
UTC date of the amount's stamp; an open position converts at `date.today()`
(frozen: 2026-11-04). Rounded to cents per leg, then the sum rounded.
V205-15 and V205-16 change these values, each with its arithmetic, never the goldens.
"""
from tests.admin_perf.golden_book import ENDPOINTS

T1_SAP_WIN = 120.00       # EUR quote: no conversion
T2_AAPL_WIN = 43.50       # 50.00 x 0.8700 (close 2026-11-03; exit 2026-11-03 20:30 UTC)
T3_AAPL_LOSS = -26.04     # -30.00 x 0.8680 (close 2026-11-02; exit 2026-11-02 23:30 UTC)
T4_LEG1 = 43.25           # 50.00 x 0.8650 (close 2026-10-29)
T4_LEG2 = 17.36           # 20.00 x 0.8680 (close 2026-11-02)
T4_TOTAL = 60.61          # round(43.25 + 17.36, 2)
T5_OPEN_AAPL = 34.88      # 40.00 x 0.8720 (close 2026-11-04, the frozen date.today())
T6_OPEN_SAP = 60.00       # EUR quote: no conversion
DAY_2026_11_02 = -8.68    # T3 + T4 leg 2 = -26.04 + 17.36 (the Calendar buckets closed_at[:10])
DAY_2026_11_03 = 163.50   # T1 + T2 = 120.00 + 43.50
MONTH_2026_11 = 154.82    # -8.68 + 163.50

#: endpoint name -> JSON pointer -> hand-computed value. Exactly the FX-sensitive
#: pointers (test_money_pointers_are_exactly_the_fx_sensitive_fields).
EXPECTED_MONEY: dict[str, dict[str, float | None]] = {name: {} for name in ENDPOINTS}
```

- [ ] **Step 2: Write `record_golden.py` and append the golden tests**

Create `tests/admin_perf/record_golden.py`:

```python
"""Record the v205 admin goldens ONCE, from today's code:

    python -m tests.admin_perf.record_golden

Writes golden/<name>.json only where it is missing; an existing golden is frozen
and never rewritten. A failing golden means the code is fixed, never the golden."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.admin_perf import golden_book as gb


def write_golden(name: str, payload) -> bool:
    path = gb.golden_path(name)
    if path.exists():
        return False
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return True


def main() -> int:
    if all(gb.golden_path(name).exists() for name in gb.ENDPOINTS):
        print("every golden exists; nothing recorded (they are frozen)")
        return 0
    os.environ["ADMIN_PERF_RECORD"] = "1"
    test = Path(__file__).with_name("test_golden_endpoints.py")
    return int(pytest.main(["-q", "-n", "0", f"{test}::test_endpoint_matches_its_frozen_golden"]))


if __name__ == "__main__":
    raise SystemExit(main())
```

Append to `tests/admin_perf/test_golden_endpoints.py`, and add `import json`, `import os`, `from tests.admin_perf import money_reference as mr` and `from tests.admin_perf import record_golden` to its imports:

```python
@pytest.mark.parametrize("name", NAMES)
def test_endpoint_matches_its_frozen_golden(name, golden_seed, frozen_clock, logged_in):
    live = _get(logged_in, name)
    if os.environ.get("ADMIN_PERF_RECORD") == "1":
        record_golden.write_golden(name, live)
    golden = json.loads(gb.golden_path(name).read_text(encoding="utf-8"))
    pointers = list(mr.EXPECTED_MONEY[name])
    assert gb.mask(live, pointers) == gb.mask(golden, pointers)


@pytest.mark.parametrize("name", NAMES)
def test_money_fields_match_the_hand_computed_reference(name, golden_seed, frozen_clock, logged_in):
    live = _get(logged_in, name)
    for pointer, expected in mr.EXPECTED_MONEY[name].items():
        actual = gb.resolve(live, pointer)
        if isinstance(expected, float):
            assert actual == pytest.approx(expected, abs=0.005), pointer
        else:
            assert actual == expected, pointer


@pytest.mark.parametrize("name", NAMES)
def test_money_pointers_are_exactly_the_fx_sensitive_fields(name, golden_seed, frozen_clock, logged_in):
    base = _get(logged_in, name)
    golden_seed.set_fx(2.0)                             # every USDEUR=X close doubled
    doubled = _get(logged_in, name)
    assert gb.diff_pointers(gb.mask(base), gb.mask(doubled)) == set(mr.EXPECTED_MONEY[name])


def test_no_golden_is_ever_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(gb, "GOLDEN_DIR", tmp_path)
    assert record_golden.write_golden("dashboard", {"a": 1}) is True
    assert record_golden.write_golden("dashboard", {"a": 2}) is False
    assert json.loads((tmp_path / "dashboard.json").read_text(encoding="utf-8")) == {"a": 1}
```

- [ ] **Step 3: Run them and read the probe**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet.

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`
Expected: V205-4's 19 tests pass; `test_no_golden_is_ever_overwritten` passes; `test_endpoint_matches_its_frozen_golden[*]` fails with `FileNotFoundError` (no goldens yet); `test_money_pointers_are_exactly_the_fx_sensitive_fields[*]` fails, its assertion diff listing each endpoint's FX-sensitive pointers; the money-reference tests pass vacuously (empty dicts).

- [ ] **Step 4: Fill `EXPECTED_MONEY` from the probe, by hand**

From the money-pointer failures, take each endpoint's FX-sensitive pointer set. For every pointer, find the figure in the book table above and write its value as a literal or an expression over the module's constants, with the arithmetic in a comment. Replace the comprehension with one dict literal naming all eight endpoints (`{}` where an endpoint has no FX-sensitive pointer), in this shape:

```python
EXPECTED_MONEY: dict[str, dict[str, float | None]] = {
    "trades": {
        "/items/<i>/realized_pnl_amount": T2_AAPL_WIN,          # 50.00 x 0.8700
    },
    "calendar_month": {
        "/<pointer of the 2026-11-03 cell total>": DAY_2026_11_03,   # 120.00 + 43.50
    },
    # ... every other endpoint name, {} when the probe lists nothing
}
```

Each `<...>` is the exact pointer the probe printed. A derived figure (a balance, a sum, a percent of the account) is written as its arithmetic over the constants: `round(10000.0 + T1_SAP_WIN + T2_AAPL_WIN + T3_AAPL_LOSS + T4_TOTAL, 2)`. If a **non-numeric** pointer is FX-sensitive (an ordering by converted money), record its hand-derived value as a string. If a pointer you expect (T2's converted amount on `/trades`) is **missing** from the probe, a process cache served the old rate: find it and clear it in `set_fx`; never add the pointer by hand. Re-run until `test_money_pointers_are_exactly_the_fx_sensitive_fields[*]` passes.

- [ ] **Step 5: Record the goldens from today's code, once**

Confirm nothing under `swingbot/` differs from the branch point: `git -C <wt> diff --stat main -- swingbot/` must list only V205-2/V205-3's files (`core/db/engine.py`, `admin/request_timing.py`, `admin/app.py`, `config.py`), none of which changes a response body.

Run (no `cd`: the repo root goes on `sys.path` explicitly, the `python -m tests.admin_perf.record_golden` form being for a shell already at `<wt>`):

```bash
python -c "import sys; sys.path.insert(0, r'<wt>'); from tests.admin_perf.record_golden import main; raise SystemExit(main())"
```

Expected: 8 files under `tests/admin_perf/golden/`, exit 0. A second run prints "every golden exists; nothing recorded".

Run the whole file twice: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`. Any key that differs between the recording and a later run (a DB `updated_at`, a generated id) goes into `VOLATILE_KEYS` with its reason, e.g. `"updated_at": "clock_timestamp() of the seeding insert"`; never edit a golden file. Expected finally: `44 passed` (V205-4's 19, plus 3 x 8 parametrised + 1), `0 failed`, `0 xfailed`. Open one golden and confirm it is real data (T2's id and amount present), not an error body.

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf` -- expected `0 failed`.
Run: `python <wt>/scripts/dev/testrun.py file tests/dev/test_suites.py` -- expected `0 failed`.

- [ ] **Step 6: Commit (two scoped commits)**

```bash
git -C <wt> add tests/admin_perf/money_reference.py tests/admin_perf/record_golden.py tests/admin_perf/test_golden_endpoints.py tests/admin_perf/golden_book.py
git -C <wt> commit -m "test(admin): hand-computed money references and the golden recorder (v205 V205-4b)"
git -C <wt> add tests/admin_perf/golden/
git -C <wt> commit -m "test(admin): freeze the eight profiled endpoints' JSON from pre-v205 code (v205 V205-4b)"
```

(`golden_book.py` is in the first commit only if Step 5 added `VOLATILE_KEYS` entries.)

