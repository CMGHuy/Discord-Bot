# v91 — Postgres Import Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every v67 importer round-trip production JSON into PostgreSQL without losing or silently altering a record, then prove it and flip the two safest stores to `dual`.

**Architecture:** Four independent defect fixes, ordered so the verifier is trustworthy before anything is verified with it. D4 (one verifier) lands first; D2 (codec-boundary NaN) and D1 (trades translator) are then provable; D3 (`created_at` contract) is decided by reading consumers, not by assumption. Production work is two tasks at the end, both reversible, both leaving JSON as the read path.

**Tech Stack:** Python 3.11, SQLAlchemy Core, Alembic, PostgreSQL 18, pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-v91-postgres-import-correctness-design.md`

**Bump:** bot patch
**Edge:** none (integrity)

## Global Constraints

- **`DB_STORES` stays empty for reads throughout this plan.** Tasks 1–5 change no stage at all; Task 6 moves `watchlist` and `state` to `dual` only. No store reaches `db`. JSON remains the source of truth for every read.
- **`trades` and `plans` do NOT change stage in this plan.** They carry the performance win and they are the stores these defects hit. They move in a later plan, after backups exist.
- **Import order is fixed and stated once:** `watchlist, state, plans, starred, trades, account, journal`. `starred_plans.plan_id` is a foreign key into `plans` (revision `p2_006`); `account`'s balance is derived from realised P&L in `trades`.
- **Production is `167.233.26.185`, directory `/opt/swing-bot`.** Reach it with `scripts/ops/ssh-hetzner.sh`. That script's `~` expands in the wrong shell under Git Bash — run it from WSL, or use `wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 bash -s' < script.sh`. Every `docker compose exec -T` in a script piped over stdin needs `</dev/null` or it eats the rest of the script.
- **Never read `.env` on production.** The credential classifier denies it and you do not need it; the `db` container being healthy already proves `POSTGRES_PASSWORD` is set.
- **Authoritative verification is `scripts/db/parity_report.py`.** No task may declare an import correct on the strength of any other check.
- **Test runs use `python scripts/dev/testrun.py file <path>` while iterating.** The full suite runs exactly once, in Task 7.

## Current production state (measured 2026-09-16, before this plan)

Schema is at `p6_000 (head)`, 19 tables, 12 MB. Imported and parity-OK:
`watchlist` 77/77, `state` 1170/1170, `account` (1 config row + 814 history),
`starred_plans` 0/0. Failing: `trades` 0/802, `journal` 517/609, `plans`
416/416 written but all 416 mismatch on `created_at`.

## Parallelisation

Tasks 1–4 touch disjoint files and may run concurrently in separate worktrees:

| Task | Files touched |
|---|---|
| 1 (D4 verifier) | `scripts/db/import_common.py`, `scripts/db/parity_report.py`, `tests/scripts/test_import_common.py` |
| 2 (D2 NaN) | `swingbot/core/db/codec.py`, `tests/db/test_codec.py` |
| 3 (D1 trades) | `scripts/db/import_trades.py`, `tests/scripts/test_import_trades.py` |
| 4 (D3 created_at) | `scripts/db/parity_report.py`, `tests/scripts/test_parity_report.py` |

Tasks 1 and 4 both touch `parity_report.py` — if run concurrently, land Task 1
first and rebase Task 4 onto it. Tasks 5, 6 and 7 are strictly sequential and
must follow all of 1–4.

---

# Phase 1 — Fix the defects

### Task P91-01: One verifier, not two

`run_import` compares source records against `repo.list_all()` raw
(`scripts/db/import_common.py:85`) with neither the `from_repo_shape`
translation nor the `ignore_fields` set that `parity_report.py` carries per
store. It reported `watchlist` FAILED where authoritative parity reports OK,
and reported OK for stores whose shapes it never translated. Delete the second
definition; delegate to the first.

**Files:**
- Modify: `scripts/db/parity_report.py` (add an optional source override to `parity()`)
- Modify: `scripts/db/import_common.py:70-88` (`run_import` delegates)
- Test: `tests/scripts/test_import_common.py`

**Interfaces:**
- Consumes: `parity_report.STORES`, `parity_report.parity`.
- Produces: `parity(store: str, source_path: str | None = None) -> ImportReport`.
  `run_import(...)` keeps its existing signature and return contract (0 on OK,
  1 on failure) but its verdict now comes from `parity()`.

**Why `name` can index `STORES` directly:** the `name=` each importer passes to
`run_import` already equals its `STORES` key — `watchlist`, `state`, `plans`,
`starred_plans`, `trades`, `journal`. Task step 1 pins that with a test so a
future importer cannot quietly break the mapping.

- [ ] **Step 1: Write the failing tests**

Add to `tests/scripts/test_import_common.py`:

```python
def test_every_run_import_name_is_a_parity_store():
    """run_import delegates verification by name, so the names must match."""
    import importlib
    from scripts.db.parity_report import STORES
    for module_name, expected in [
        ("import_watchlist", "watchlist"), ("import_state", "state"),
        ("import_plans", "plans"), ("import_starred", "starred_plans"),
        ("import_trades", "trades"), ("import_journal", "journal"),
    ]:
        importlib.import_module(f"scripts.db.{module_name}")
        assert expected in STORES, f"{module_name} verifies against a missing store"


def test_parity_accepts_a_source_override():
    """run_import --source must verify against the file it actually imported."""
    import inspect

    from scripts.db.parity_report import parity
    assert "source_path" in inspect.signature(parity).parameters


def test_run_import_verdict_comes_from_parity(monkeypatch, tmp_path):
    """A store whose parity is OK must not be reported FAILED by run_import."""
    import scripts.db.import_common as mod
    from scripts.db.import_common import ImportReport

    monkeypatch.setattr(mod, "parity",
                        lambda name, source_path=None: ImportReport(
                            source_count=3, imported_count=3))

    class FakeRepo:
        def count(self):
            return 0

    rc = mod.run_import([], load_source=lambda p: [{"k": 1}, {"k": 2}, {"k": 3}],
                        write_one=lambda repo, rec: None, repo=FakeRepo(),
                        key="k", name="watchlist")
    assert rc == 0


def test_run_import_fails_when_parity_fails(monkeypatch):
    import scripts.db.import_common as mod
    from scripts.db.import_common import ImportReport

    monkeypatch.setattr(mod, "parity",
                        lambda name, source_path=None: ImportReport(
                            source_count=3, imported_count=2, missing=["c"]))

    class FakeRepo:
        def count(self):
            return 0

    rc = mod.run_import([], load_source=lambda p: [{"k": 1}],
                        write_one=lambda repo, rec: None, repo=FakeRepo(),
                        key="k", name="watchlist")
    assert rc == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/scripts/test_import_common.py`
Expected: FAIL — `parity` has no `source_path` parameter, and
`scripts.db.import_common` has no attribute `parity`.

- [ ] **Step 3: Add the source override to `parity()`**

In `scripts/db/parity_report.py`, replace the body of `parity`:

```python
def parity(store: str, source_path: str | None = None) -> ImportReport:
    """Return a strict whole-store JSON-to-Postgres parity report.

    ``source_path`` mirrors the importers' ``--source`` flag: verification must
    read the same file the import read, or it is checking the wrong thing.
    """
    spec = STORES[store]
    source = read_json(source_path or os.path.join(config.DATA_DIR, spec.filename), [])
    if spec.loader is not None:
        source = spec.loader(source)
    if isinstance(source, dict):
        source = list(source.values())
    rows = [spec.from_repo_shape(row) for row in spec.repo_factory().list_all()]
    return compare(source, rows, key=spec.key, ignore_fields=spec.ignore_fields)
```

- [ ] **Step 4: Delegate from `run_import`**

In `scripts/db/import_common.py`, add the import near the top:

```python
from scripts.db.parity_report import parity  # noqa: E402  (circular-safe: parity_report imports only compare/ImportReport)
```

If that import is circular at runtime, move it inside `run_import` instead and
leave this comment in its place:

```python
    # Imported here, not at module scope: parity_report imports ImportReport and
    # compare from this module, so a top-level import would be circular.
    from scripts.db.parity_report import parity
```

Then replace `import_common.py:85` — the line
`report = compare(source, repo.list_all(), key=key)` — with:

```python
    # One verifier. The ad-hoc comparison this replaced had neither the
    # per-store from_repo_shape translation nor ignore_fields, so it reported
    # watchlist FAILED on all 77 rows while authoritative parity reported OK,
    # and passed stores whose shape it never translated.
    report = parity(name, args.source)
```

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_import_common.py`
Expected: PASS

Run: `python scripts/dev/testrun.py file tests/scripts/test_parity_report.py`
Expected: PASS — the override is optional, so existing callers are unaffected.

- [ ] **Step 6: Commit**

```bash
git add scripts/db/import_common.py scripts/db/parity_report.py tests/scripts/test_import_common.py
git commit -m "fix(v91): run_import verifies through parity_report, not its own comparison

The inline comparison had neither from_repo_shape nor ignore_fields, so it
reported watchlist FAILED on all 77 rows where authoritative parity reports OK,
and waved through stores whose shape it never translated. A verifier that cries
wolf on a healthy store and passes an unchecked one is worse than none.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task P91-02: Non-finite floats at the codec boundary

`json.dumps` emits bare `NaN`, which is not valid JSON; PostgreSQL's JSONB
rejects it with `Token "NaN" is invalid`. This cost 92 of 609 journal rows.
Journal is only the first store to carry one — the fix belongs where every
store crosses into the database.

**Files:**
- Modify: `swingbot/core/db/codec.py`
- Modify: `scripts/db/import_common.py` (`record_checksum` — so parity treats source `NaN` as equal to database `null`)
- Test: `tests/db/test_codec.py`, `tests/scripts/test_import_common.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `codec.sanitise_non_finite(value: Any) -> Any`, applied inside
  `split_doc` to both the promoted columns and the document.

- [ ] **Step 1: Write the failing tests**

Add to `tests/db/test_codec.py`:

```python
import math

from swingbot.core.db.codec import sanitise_non_finite, split_doc


def test_nan_in_a_document_field_becomes_none():
    """Bare NaN is not valid JSON and JSONB rejects it outright."""
    _, doc = split_doc({"trade_id": "t1", "mfe_r": float("nan")}, ["trade_id"])
    assert doc["mfe_r"] is None


def test_infinity_in_a_document_field_becomes_none():
    _, doc = split_doc({"trade_id": "t1", "r": float("inf")}, ["trade_id"])
    assert doc["r"] is None


def test_nan_nested_in_a_list_of_dicts_becomes_none():
    """legs_realized and status_history are lists of dicts; NaN hides in there."""
    _, doc = split_doc(
        {"trade_id": "t1", "legs": [{"r": float("nan"), "fraction": 0.5}]},
        ["trade_id"])
    assert doc["legs"][0]["r"] is None
    assert doc["legs"][0]["fraction"] == 0.5


def test_nan_in_a_promoted_column_becomes_none():
    columns, _ = split_doc({"trade_id": "t1", "entry": float("nan")},
                           ["trade_id", "entry"])
    assert columns["entry"] is None


def test_finite_values_are_untouched():
    columns, doc = split_doc(
        {"trade_id": "t1", "entry": 152.36, "n": 0, "flag": False, "s": "x"},
        ["trade_id", "entry"])
    assert columns["entry"] == 152.36
    assert doc == {"n": 0, "flag": False, "s": "x"}


def test_sanitise_leaves_bools_and_ints_alone():
    """bool is a subclass of int, not float -- it must not be coerced."""
    assert sanitise_non_finite({"a": True, "b": 3}) == {"a": True, "b": 3}
```

Add to `tests/scripts/test_import_common.py`:

```python
def test_checksum_treats_nan_as_null():
    """Source holds NaN; the database holds null. Parity must call that equal."""
    from scripts.db.import_common import record_checksum
    assert record_checksum({"k": "a", "v": float("nan")}) == \
           record_checksum({"k": "a", "v": None})
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/db/test_codec.py`
Expected: FAIL — `ImportError: cannot import name 'sanitise_non_finite'`.

- [ ] **Step 3: Implement the sanitiser**

In `swingbot/core/db/codec.py`, add after the imports:

```python
import math
```

and add before `split_doc`:

```python
def sanitise_non_finite(value: Any) -> Any:
    """Replace NaN and +/-Infinity with ``None``, recursively.

    ``json.dumps`` emits these as bare ``NaN``/``Infinity`` tokens, which
    Python's own parser accepts but JSON does not define and PostgreSQL's JSONB
    rejects outright.  Every producer of one here means "not computed", and the
    JSON stores already spell that ``None`` elsewhere, so this narrowing is
    deliberate and one-way: a value does not round-trip back to NaN.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {key: sanitise_non_finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitise_non_finite(item) for item in value]
    return value
```

Then apply it in `split_doc`, replacing the assignment loop body:

```python
    promoted_set = set(promoted)
    columns: dict[str, Any] = {}
    doc: dict[str, Any] = {}
    for key, value in record.items():
        if key in promoted_set:
            columns[key] = sanitise_non_finite(value)
        else:
            doc[key] = sanitise_non_finite(value)
    return columns, doc
```

`bool` is a subclass of `int`, not `float`, so it never reaches the first
branch — the test above pins that.

- [ ] **Step 4: Make parity agree**

In `scripts/db/import_common.py`, change `record_checksum`:

```python
def record_checksum(record: dict) -> str:
    """Return a type-sensitive canonical checksum for one source record.

    Non-finite floats are folded to None first: the write path narrows NaN to
    null at the codec boundary, so a source NaN and a stored null are the same
    record and parity must not report them as a mismatch.
    """
    from swingbot.core.db.codec import sanitise_non_finite
    blob = json.dumps(sanitise_non_finite(record), sort_keys=True,
                      default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/db/test_codec.py`
Expected: PASS

Run: `python scripts/dev/testrun.py file tests/scripts/test_import_common.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/codec.py scripts/db/import_common.py tests/db/test_codec.py tests/scripts/test_import_common.py
git commit -m "fix(v91): narrow non-finite floats to null at the codec boundary

json.dumps emits bare NaN, which JSONB rejects -- it cost 92 of 609 journal
rows on the first production import. Journal was only the first store to carry
one, so the fix goes where every store crosses, not in one importer. NaN means
'not computed' at every site that produces one here and the JSON stores already
spell that None, so the narrowing is deliberate and one-way; parity folds NaN
to None too, or it would report the write path's own correct behaviour as a
mismatch.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task P91-03: `import_trades` uses the live translator

`trades.json` keys the trade as `id`; the `trades` table has an infrastructure
`id BigInteger` primary key and a separate `trade_id Text` column
(`swingbot/core/db/schema.py:51-52`), and `TradeRepository` keys on `trade_id`.
`split_doc` rejects the raw record — correctly. `performance._db_record`
(`swingbot/core/tracking/performance.py:438-442`) is the translator, and the
live dual-write path already calls it (`performance.py:507`). The importer
never does.

**Files:**
- Modify: `scripts/db/import_trades.py:14-15`
- Test: `tests/scripts/test_import_trades.py` (create)

**Interfaces:**
- Consumes: `swingbot.core.tracking.performance._db_record`.
- Produces: `import_trades.load_source(path) -> list[dict]` now returning
  repo-shaped records (`trade_id`, `horizon`), not JSON-shaped ones.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_import_trades.py`:

```python
"""The trades importer must hand the repository repo-shaped records."""
import json

from scripts.db.import_trades import load_source
from swingbot.core.db.codec import RESERVED_KEYS, split_doc


def _write(tmp_path, records):
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return str(path)


def test_load_source_renames_id_to_trade_id(tmp_path):
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    record = load_source(path)[0]
    assert record["trade_id"] == "abc123"
    assert "id" not in record


def test_load_source_renames_horizon_key_to_horizon(tmp_path):
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    record = load_source(path)[0]
    assert record["horizon"] == "3m"
    assert "horizon_key" not in record


def test_loaded_records_use_no_reserved_key(tmp_path):
    """The exact failure that lost all 802 rows on the first production import."""
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    for record in load_source(path):
        assert not RESERVED_KEYS.intersection(record)


def test_loaded_records_survive_split_doc(tmp_path):
    """split_doc is where the ReservedKeyError was actually raised."""
    path = _write(tmp_path, [{"id": "abc123", "ticker": "AMD",
                              "horizon_key": "3m", "status": "open"}])
    columns, doc = split_doc(load_source(path)[0],
                             ["trade_id", "ticker", "horizon", "status"])
    assert columns["trade_id"] == "abc123"


def test_missing_source_file_yields_no_records(tmp_path):
    assert load_source(str(tmp_path / "absent.json")) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/scripts/test_import_trades.py`
Expected: FAIL — `KeyError: 'trade_id'`; the records still carry `id`.

- [ ] **Step 3: Apply the translator**

In `scripts/db/import_trades.py`, add to the imports:

```python
from swingbot.core.tracking.performance import _db_record  # noqa: E402
```

and replace `load_source`:

```python
def load_source(path: str | None) -> list[dict]:
    """Return repo-shaped trade records.

    Deliberately the same translator the live dual-write path uses
    (performance.py:507): it maps the JSON store's `id`/`horizon_key` onto the
    table's `trade_id`/`horizon`. An importer that shaped records differently
    from the live writer would produce a database that passes import and then
    diverges the moment dual-write starts.
    """
    raw = read_json(path or os.path.join(config.DATA_DIR, "trades.json"), [])
    return [_db_record(trade) for trade in raw]
```

- [ ] **Step 4: Run the test**

Run: `python scripts/dev/testrun.py file tests/scripts/test_import_trades.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/db/import_trades.py tests/scripts/test_import_trades.py
git commit -m "fix(v91): import trades through the live dual-write translator

trades.json keys the trade as 'id', which is an infrastructure column, so
split_doc rejected every record and the first production import wrote 0 of 802.
performance._db_record already maps id->trade_id and horizon_key->horizon, and
the live dual-write path calls it -- the importer just never did. Reusing it
rather than writing a second translator is the point: two shapes would pass
import and diverge the moment dual-write starts.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task P91-04: Resolve the `created_at` contract

All 416 plans mismatch on `created_at` alone: source `'2026-08-11'`, round-trip
`'2026-08-11T00:00:00+00:00'`. The column is a promoted `TIMESTAMP WITH TIME
ZONE`, so a date-only string is parsed on write and rendered in full on read.
No instant moves and no data is lost — but the string a consumer receives
changes.

**This task decides by reading consumers, not by assuming.** Known consumers,
all treating it as an opaque string: `swingbot/admin/api_v1/trades.py:317,650`
pass it through; `frontend/src/app/api/models.ts:133` types it
`string | null`; `frontend/src/app/workspaces/trades/trades.columns.ts:150`
feeds it to `age()`; `frontend/src/app/stores/trade-detail.store.ts:290` feeds
it to `asText()`.

**Files:**
- Modify: `scripts/db/parity_report.py` (`_plans_from_repo_shape`)
- Test: `tests/scripts/test_parity_report.py`

**Interfaces:**
- Consumes: `parity()` from Task P91-01 (rebase onto it if run concurrently).
- Produces: no new public names; `_plans_from_repo_shape` gains a date-only
  normalisation.

- [ ] **Step 1: Confirm the decision by reading the consumers**

Run these and read the results before writing any code:

```bash
git grep -n "created_at" -- swingbot/admin/api_v1/trades.py
git grep -n "created_at" -- frontend/src/app/workspaces/trades/trades.columns.ts
git grep -n "age\b" -- frontend/src/app/shared | head
```

Decide between:

- **(a) Normalise on read** — `_plans_from_repo_shape` renders a midnight-UTC
  timestamp back to `YYYY-MM-DD`. Keeps today's exact contract; parity goes
  green with no behaviour change anywhere.
- **(b) Accept the widening** — add `created_at` to the plans spec's
  `ignore_fields` and record the contract change.

**Take (a) unless a consumer is found that needs the full timestamp.** (b)
changes a string that reaches the UI, and this plan's whole point is that
nothing user-visible changes. Only choose (b) if step 1 finds a consumer that
would break under (a) — and if you do, stop and say so rather than proceeding,
because that is a spec change.

- [ ] **Step 2: Write the failing test**

Add to `tests/scripts/test_parity_report.py`:

```python
import datetime as dt

from scripts.db.parity_report import _plans_from_repo_shape


def test_midnight_utc_created_at_renders_back_to_a_date():
    """plans.json stores date-only strings; the promoted timestamptz widens them."""
    row = {"plan_id": "p1",
           "created_at": dt.datetime(2026, 8, 11, tzinfo=dt.timezone.utc)}
    assert _plans_from_repo_shape(row)["created_at"] == "2026-08-11"


def test_a_created_at_with_a_real_time_is_left_alone():
    """Only midnight collapses -- a genuine timestamp must not lose its time."""
    row = {"plan_id": "p1",
           "created_at": dt.datetime(2026, 8, 11, 12, 3, 7, tzinfo=dt.timezone.utc)}
    assert _plans_from_repo_shape(row)["created_at"].startswith("2026-08-11T12:03:07")


def test_a_null_created_at_survives():
    assert _plans_from_repo_shape({"plan_id": "p1", "created_at": None})["created_at"] is None


def test_a_plan_without_created_at_survives():
    assert "created_at" not in _plans_from_repo_shape({"plan_id": "p1"})
```

- [ ] **Step 3: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/scripts/test_parity_report.py`
Expected: FAIL — `created_at` comes back as a full ISO string, not `2026-08-11`.

- [ ] **Step 4: Implement option (a)**

In `scripts/db/parity_report.py`, replace `_plans_from_repo_shape`:

```python
def _plans_from_repo_shape(row: dict) -> dict:
    """Translate a plans row back to its JSON-store representation.

    `created_at` is a promoted timestamptz, so a date-only source string comes
    back widened to a full ISO instant. Every consumer treats the field as an
    opaque string -- api_v1/trades.py passes it through, the SPA types it
    `string | null` and feeds it to age()/asText() -- so the honest round trip
    is to render midnight UTC back to the date it was written as. A timestamp
    with a real time of day is left alone; only the widening is undone.
    """
    import datetime as dt

    from swingbot.core.db.dual import normalise

    out = dict(row)
    created = out.get("created_at")
    if isinstance(created, dt.datetime) and created.tzinfo is not None:
        midnight = (created.hour == 0 and created.minute == 0
                    and created.second == 0 and created.microsecond == 0
                    and created.utcoffset() == dt.timedelta(0))
        out["created_at"] = created.date().isoformat() if midnight else created.isoformat()
    return normalise(out)
```

- [ ] **Step 5: Run the test**

Run: `python scripts/dev/testrun.py file tests/scripts/test_parity_report.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/db/parity_report.py tests/scripts/test_parity_report.py
git commit -m "fix(v91): round-trip plan created_at back to its date-only form

All 416 plans mismatched on created_at alone -- a promoted timestamptz widens
a date-only source string to a full ISO instant. Every consumer treats the
field as an opaque string (api_v1/trades.py passes it through; the SPA types it
string|null and feeds it to age()/asText()), so collapsing midnight UTC back to
the date preserves today's exact contract. A timestamp carrying a real time of
day is left untouched.

The other fields flagged during diagnosis -- badge_stats, status_history,
legs_realized, gate, cohort_stats -- were repr() key-order artefacts, not
differences: record_checksum serialises with sort_keys=True.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Phase 2 — Prove it on production

### Task P91-05: Re-import production and prove parity — TOUCHES PRODUCTION

Additive and reversible: `DB_STORES` is unchanged, nothing reads PostgreSQL,
every write is an idempotent upsert, and the JSON files are read-only to the
importers. The 517 partial journal rows and 0 trades rows left by the first
attempt converge on re-run.

**Files:**
- Create: `scripts/ops/reimport_production.sh`
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (add a PostgreSQL section — it currently mentions Postgres zero times)

**Interfaces:**
- Consumes: every fix from Tasks 1–4, deployed to production.
- Produces: a production database where `parity_report.py --all` reports OK for
  all seven stores.

- [ ] **Step 1: Deploy the fixes**

Production auto-deploys on push to `main` and rebuilds the image, which is what
carries `scripts/db/` and `swingbot/core/db/` into the containers.

```bash
git push origin main
```

Wait for the new image, then confirm production is running it:

```bash
wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 "cd /opt/swing-bot && git rev-parse --short HEAD && docker compose ps --format \"{{.Name}} {{.Status}}\""'
```

Expected: the short SHA matches your local `main`, and `swing-bot`,
`swing-bot-admin`, `swing-db` are all `(healthy)`.

- [ ] **Step 2: Create the re-import script**

Create `scripts/ops/reimport_production.sh`:

```bash
#!/bin/bash
# Re-import every migrated store from JSON into PostgreSQL, then verify.
#
# Safe to re-run: every importer is an idempotent upsert and is read-only
# against its JSON source. DB_STORES is not touched, so nothing reads the
# database and JSON remains the source of truth throughout.
#
# Order is a correctness requirement: starred_plans.plan_id is a foreign key
# into plans (revision p2_006), and account's balance is derived from realised
# P&L in trades.
#
# Run it from WSL:
#   wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 bash -s' \
#     < scripts/ops/reimport_production.sh
#
# Every `docker compose exec -T` redirects stdin from /dev/null: this script
# arrives over stdin itself, and an exec that reads stdin eats the rest of it.
set +e
cd /opt/swing-bot || exit 1

failed=0
for name in watchlist state plans starred trades account journal; do
  echo "=== ${name} ==="
  docker compose exec -T bot python scripts/db/import_${name}.py </dev/null 2>&1 | tail -8
  rc=${PIPESTATUS[0]}
  echo "   exit=${rc}"
  [ "$rc" != "0" ] && failed=1
done

echo
echo "======== PARITY (authoritative) ========"
docker compose exec -T bot python scripts/db/parity_report.py --all </dev/null 2>&1 | tail -40
parity_rc=${PIPESTATUS[0]}
echo "   parity exit=${parity_rc}"

echo
echo "======== COUNTS ========"
docker compose exec -T db psql -U swingbot -d swingbot -tAc \
  "select 'trades='||(select count(*) from trades)
       ||' plans='||(select count(*) from plans)
       ||' journal='||(select count(*) from journal_entries)
       ||' signal_state='||(select count(*) from signal_state)
       ||' watchlist='||(select count(*) from watchlist)
       ||' starred='||(select count(*) from starred_plans)
       ||' acct_hist='||(select count(*) from account_balance_history);" \
  </dev/null 2>&1 | head -5

exit $(( failed || parity_rc ))
```

Make it executable: `chmod +x scripts/ops/reimport_production.sh`

- [ ] **Step 3: Run it against production**

```bash
wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 bash -s' \
  < scripts/ops/reimport_production.sh
```

**Required result — do not proceed past this step without it:**

```
trades=802 plans=416 journal=609 signal_state=1170 watchlist=77 starred=0 acct_hist=814
```

and `parity_report.py --all` reporting `VERDICT: OK` for all seven stores.

If `trades` is not 802 or `journal` is not 609, stop and diagnose. Do not move
to Task 6. A store that will not import is a store that must not be staged.

- [ ] **Step 4: Document the database on the deploy page**

`docs/deploy/DEPLOY_HETZNER.md` does not mention PostgreSQL at all. Add a
section covering: the `db` service and its `pgdata` volume; that `DB_STORES`
selects a per-store stage and empty means all-JSON; `alembic upgrade head` as
the schema step; `scripts/ops/reimport_production.sh` as the import step;
`parity_report.py --all` as the verification step; and that reaching the
database is `docker compose exec db psql -U swingbot -d swingbot` because the
port is deliberately unpublished.

State plainly that **nightly backups do not exist yet** (v67 P6-03/P6-04 are
unbuilt) and that no store may reach the `db` stage until they do.

- [ ] **Step 5: Commit**

```bash
git add scripts/ops/reimport_production.sh docs/deploy/DEPLOY_HETZNER.md
git commit -m "ops(v91): production re-import script and the missing Postgres runbook

DEPLOY_HETZNER.md mentioned Postgres zero times while the schema was already
live on the VM. Records the stage model, the import and verification steps, and
that no store may reach the db stage before nightly backups exist.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task P91-06: Flip `watchlist` and `state` to `dual` — TOUCHES PRODUCTION

The first live stage change. Both stores are small, fully reconstructible from
JSON — which `dual` keeps writing — and neither is read from the database at
this stage. Reads stay on JSON; only writes fan out.

**Files:**
- Modify: production `.env` (`DB_STORES`), mirrored into `.env.example` in the repo

- [ ] **Step 1: Set the stage**

`DB_STORES` is re-read dynamically (`core/db/stages.py`), so SIGHUP is enough —
no restart, no dropped scan.

Edit production `/opt/swing-bot/.env` to read:

```
DB_STORES=watchlist:dual,state:dual
```

Ask the human partner to make this edit, or make it in an interactive SSH
session — do not script a read of `.env`, which the credential classifier
denies.

Then reload both containers:

```bash
wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 "cd /opt/swing-bot && docker compose kill -s HUP bot admin && sleep 5 && docker compose ps --format \"{{.Name}} {{.Status}}\""'
```

- [ ] **Step 2: Confirm the bot sees the new stage**

```bash
wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 "cd /opt/swing-bot && docker compose exec -T bot python -c \"from swingbot.core.db import stages; print(stages.stage_for(\\\"watchlist\\\"), stages.stage_for(\\\"state\\\"), stages.stage_for(\\\"trades\\\"))\" </dev/null"'
```

Expected: `dual dual json` — `trades` must still read `json`.

- [ ] **Step 3: Watch for divergence across one trading day**

`core/db/dual.py`'s `compare_and_log` logs any JSON-vs-database divergence
rather than raising. After a full session:

```bash
wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 "cd /opt/swing-bot && docker compose logs --since 24h bot | grep -iE \"divergen|parity|dual\" | head -40"'
```

Expected: no divergence lines. Then re-run parity:

```bash
wsl bash -lc 'ssh -i ~/.ssh/id_rsa root@167.233.26.185 "cd /opt/swing-bot && docker compose exec -T bot python scripts/db/parity_report.py --store watchlist </dev/null && docker compose exec -T bot python scripts/db/parity_report.py --store state </dev/null"'
```

Expected: `VERDICT: OK` for both.

**Rollback, if anything diverges:** set `DB_STORES=` back to empty and SIGHUP.
JSON never stopped being written or read, so there is nothing to restore.

- [ ] **Step 4: Mirror the production change back into the repo**

CLAUDE.md requires every live config change to land in the repo. Update
`.env.example`'s `DB_STORES` line with a comment recording the live value and
why only these two stores are staged.

```bash
git add .env.example
git commit -m "config(v91): record watchlist and state at the dual stage

Mirrors the live DB_STORES change. Both stores are small, fully reconstructible
from the JSON that dual keeps writing, and neither is read from the database at
this stage. trades and plans stay on json: they carry the performance win, they
are the stores v91's defects hit, and they do not move before backups exist.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Phase 3 — Verification

### Task P91-07: Full suite and close-out

The plan's single full-suite run. Per CLAUDE.md it happens once, here, and not
per task.

- [ ] **Step 1: Run the full suite**

Dispatch the `test-runner` subagent so ~1150 progress lines stay out of the
session context. It runs:

```bash
python scripts/dev/testrun.py full
```

**Green means `0 failed` and `0 xfailed`.** A changed pass count is not a
failure — this plan adds tests.

- [ ] **Step 2: Fix anything that fails, then re-run**

Do not proceed on a red suite, and do not explain a failure away. If a failure
is genuinely pre-existing, prove it by checking out `main` and reproducing it
there.

- [ ] **Step 3: Confirm the success criteria**

Check each against real output, not memory:

1. `parity_report.py --all` reports OK for all seven stores on production.
2. `trades` 802 of 802; `journal` 609 of 609.
3. `run_import`'s verdict agrees with `parity_report`'s for every store.
4. `watchlist` and `state` ran a full trading day at `dual` with no divergence.
5. JSON is still the read path; no user-visible behaviour changed.

- [ ] **Step 4: Move the plan and spec to `implemented/`**

```bash
git mv docs/superpowers/plans/2026-09-16-v91-postgres-import-correctness.md docs/superpowers/plans/implemented/
git mv docs/superpowers/specs/2026-09-16-v91-postgres-import-correctness-design.md docs/superpowers/specs/implemented/
```

- [ ] **Step 5: Bump the version**

`Bump: bot patch`. Resolve the number from the then-current `VERSION.json` —
never from a number predicted when this plan was written.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs(v91): close Postgres import correctness

All seven stores round-trip production JSON with parity OK; trades 802/802 and
journal 609/609, both of which lost data before. watchlist and state run at the
dual stage. trades and plans remain on json pending backups.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## What this plan deliberately leaves for later

- **`trades` and `plans` to `dual`/`db`.** The performance win — the scan
  re-reads a 2.9 MB `trades.json` roughly 1,600 times per pass — lives here,
  but these stores move only after backups exist and after a caching layer
  makes the access pattern sane. Moving them as-is would turn 1,600 file reads
  into 1,600 queries.
- **v67 P6-03/P6-04**, nightly `pg_dump` and a restore exercised for real. Hard
  prerequisite for any `db`-stage flip.
- **v67 P3-16…24** (LISTEN/NOTIFY replacing the 0.5s file-poller) and Parts 4–9.
- **`scripts/db/import_all.py`** (P6-06's orchestrator): its `ORDER` list names
  importers that do not exist yet, and seven explicit invocations are adequate
  at this size.
