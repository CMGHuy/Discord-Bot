# v150 Reports and Research workspaces: Part 1, endpoints and wire models

> Part of the v150 plan. Header, Global Constraints, the blocked-task gate, the wire shapes and the parallelisation map are in [`_0-index`](2026-10-09-v150-reports-research-workspaces_0-index.md). **Never read this file whole**: `/task-brief V150-3`.

All commands run inside the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v150-reports-research-workspaces`.

---

### Task V150-1: `GET /api/v1/research/ledger`

**Model:** sonnet — one admin endpoint over an existing validated reader, behaviour given by the spec.

**Files:**
- Create: `swingbot/admin/api_v1/research.py`
- Create: `tests/admin/test_api_v1_research.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (the `from . import (...)` list in `register()`, about line 208)
- Modify: `scripts/dev/select_tests.py` (the ledger row of `DATA_READERS`, about line 274)

**Interfaces:**
- Consumes (existing): `swingbot.core.backtesting.instrument.stats`: `LEDGER_PATH`, `load_ledger(path)`, `ledger_qvalues(rows) -> dict[id, q | None]`, `VERDICTS`, `INSTRUMENTS`, `LEDGER_FIELDS`. `swingbot.admin.api_v1`: `api_v1`, `ApiError(code, message, status)`. `swingbot.admin.api_v1.auth.require_auth`.
- Produces: `GET /api/v1/research/ledger` →

```
{ "rows": [ { id: str, date: str, hypothesis: str, instrument: str,
              n: int | null, exp_r: float | null, p: float | null,
              verdict: str, record: str,
              q: float | null, record_exists: bool,
              record_kind: "results" | "specs" | "plans" | "other" } ],
  "q_family_m": int, "verdicts": [str], "instruments": [str] }
```

An invalid ledger line → `500 {"error": {"code": "ledger_invalid", "message": "ledger line N: …"}}`.

- [ ] **Step 0: Create the worktree**

Invoke the `worktree-lifecycle` skill, then from the main tree:

```bash
git worktree add .claude/worktrees/2026-10-09-v150-reports-research-workspaces -b 2026-10-09-v150-reports-research-workspaces main
```

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_research.py`:

```python
"""GET /api/v1/research/ledger — the pre-registration ledger, read-only (v150).

The endpoint adds three derived fields to each validated ledger row and
ships the filter vocabularies, so the SPA hardcodes neither. It reuses
`stats.load_ledger`, which means an invalid line fails the whole request
rather than rendering a partial ledger.
"""
import json

import pytest

from swingbot.core.backtesting.instrument import stats
from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/research/ledger"

_ROW_SHAPE = {
    "id": str, "date": str, "hypothesis": str, "instrument": str,
    "n": (int, type(None)), "exp_r": NULLABLE_NUMBER, "p": NULLABLE_NUMBER,
    "verdict": str, "record": str,
    "q": NULLABLE_NUMBER, "record_exists": bool, "record_kind": str,
}


def _row(**over):
    row = {"id": "v999-demo", "date": "2026-10-06", "hypothesis": "Demo gate",
           "instrument": "v2", "n": 120, "exp_r": 0.12, "p": 0.03,
           "verdict": "FAIL", "record": "docs/superpowers/results/demo.md"}
    row.update(over)
    return row


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point the endpoint at a ledger inside a throwaway repo root.

    The path keeps the real layout (`<root>/docs/superpowers/results/`),
    because `record_exists` resolves record paths against that same root.
    """
    path = tmp_path / "docs" / "superpowers" / "results" / "preregistration-ledger.jsonl"
    path.parent.mkdir(parents=True)

    def write(rows, raw=None):
        text = raw if raw is not None else "".join(json.dumps(r) + "\n" for r in rows)
        path.write_text(text, encoding="utf-8")
        return tmp_path

    monkeypatch.setattr(stats, "LEDGER_PATH", path)
    return write


def test_requires_auth(client):
    assert client.get(_URL).status_code == 401


def test_shape_and_vocabularies(logged_in, ledger):
    ledger([_row()])
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, {"rows": list, "q_family_m": int, "verdicts": list,
                        "instruments": list})
    assert_shape(body["rows"][0], _ROW_SHAPE, where="rows[0]")
    assert body["verdicts"] == list(stats.VERDICTS)
    assert body["instruments"] == list(stats.INSTRUMENTS)


def test_rows_are_the_ledger_rows_in_file_order(logged_in, ledger):
    rows = [_row(id="a"), _row(id="b", date="2026-10-07"), _row(id="c", p=None)]
    ledger(rows)
    body = logged_in.get(_URL).get_json()
    assert [r["id"] for r in body["rows"]] == ["a", "b", "c"]
    for sent, source in zip(body["rows"], rows):
        assert {name: sent[name] for name in stats.LEDGER_FIELDS} == source


def test_q_matches_ledger_qvalues_and_the_family_size(logged_in, ledger):
    rows = [_row(id="a", p=0.01), _row(id="b", p=0.04), _row(id="c", p=None),
            _row(id="d", p=0.5)]
    ledger(rows)
    body = logged_in.get(_URL).get_json()
    expected = stats.ledger_qvalues(rows)
    assert {r["id"]: r["q"] for r in body["rows"]} == pytest.approx(expected)
    assert body["rows"][2]["q"] is None
    assert body["q_family_m"] == 3


def test_null_figures_pass_through_as_null(logged_in, ledger):
    ledger([_row(n=None, exp_r=None, p=None)])
    row = logged_in.get(_URL).get_json()["rows"][0]
    assert (row["n"], row["exp_r"], row["p"], row["q"]) == (None, None, None, None)


@pytest.mark.parametrize("record, kind", [
    ("docs/superpowers/results/demo.md", "results"),
    ("docs/superpowers/specs/2026-10-09-v150-x-design.md", "specs"),
    ("docs/superpowers/plans/implemented/v35-avwap-preregistration.md", "plans"),
    ("docs/strategy/notes.md", "other"),
    ("README.md", "other"),
])
def test_record_kind(logged_in, ledger, record, kind):
    ledger([_row(record=record)])
    assert logged_in.get(_URL).get_json()["rows"][0]["record_kind"] == kind


def test_record_exists_resolves_against_the_ledgers_repo_root(logged_in, ledger):
    root = ledger([_row(id="there", record="docs/superpowers/results/there.md"),
                   _row(id="gone", record="docs/superpowers/results/gone.md"),
                   _row(id="escape", record="../outside.md")])
    (root / "docs/superpowers/results/there.md").write_text("x", encoding="utf-8")
    (root.parent / "outside.md").write_text("x", encoding="utf-8")
    rows = {r["id"]: r["record_exists"] for r in logged_in.get(_URL).get_json()["rows"]}
    assert rows == {"there": True, "gone": False, "escape": False}


def test_empty_or_absent_ledger_is_an_empty_list(logged_in, ledger, monkeypatch, tmp_path):
    ledger([])
    assert logged_in.get(_URL).get_json()["rows"] == []
    monkeypatch.setattr(stats, "LEDGER_PATH", tmp_path / "nowhere" / "ledger.jsonl")
    body = logged_in.get(_URL).get_json()
    assert (body["rows"], body["q_family_m"]) == ([], 0)


def test_invalid_ledger_line_is_a_500_not_a_partial_ledger(logged_in, ledger):
    ledger([], raw=json.dumps(_row()) + "\n" + json.dumps(_row(id="b", verdict="MAYBE")) + "\n")
    resp = logged_in.get(_URL)
    assert resp.status_code == 500
    error = resp.get_json()["error"]
    assert error["code"] == "ledger_invalid"
    assert "ledger line 2" in error["message"]


def test_the_committed_ledger_loads_through_the_endpoint(logged_in):
    """A ledger the page cannot render must fail CI, not production."""
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["rows"]) == len(stats.load_ledger(stats.LEDGER_PATH))
    assert len(body["rows"]) > 0
    for row in body["rows"]:
        assert_shape(row, _ROW_SHAPE, where=f"row {row['id']}")
        assert row["record_kind"] in {"results", "specs", "plans", "other"}
    assert body["q_family_m"] == sum(1 for row in body["rows"] if row["p"] is not None)
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py`
Expected: FAIL. `test_requires_auth` gets 404 instead of 401 and the rest get 404 bodies: the route does not exist.

- [ ] **Step 3: Write the endpoint**

Create `swingbot/admin/api_v1/research.py`:

```python
"""GET /api/v1/research/ledger — the pre-registration ledger, read-only.

The ledger (`docs/superpowers/results/preregistration-ledger.jsonl`) is a
git-tracked record, not a runtime store: it ships inside the image, so what
this endpoint serves is **the ledger as of the deployed build**. A row
appended on `main` appears after the next deploy. Nothing here writes to it;
rows are appended only through `scripts/reports/preregistration_ledger.py`.

Each row gets three derived fields:

- `q` — its Benjamini-Hochberg q-value across every ledger row that has a
  p-value (`q_family_m` of them). Reported, never gating, and it mixes
  instruments by construction.
- `record_exists` / `record_kind` — whether the row's `record` path resolves
  in this deploy, and which docs folder it points into.

The whole ledger is returned (a few dozen rows); filtering, search and paging
are client-side. An invalid line makes `load_ledger` raise, and that surfaces
as a 500: a partial ledger would look complete.
"""
from __future__ import annotations

import os
from typing import Any

from flask import jsonify

from . import ApiError, api_v1
from .auth import require_auth

_RECORD_KINDS = ("results", "specs", "plans")


def _record_kind(record: str) -> str:
    parts = record.split("/")
    if len(parts) > 3 and parts[:2] == ["docs", "superpowers"] and parts[2] in _RECORD_KINDS:
        return parts[2]
    return "other"


def _record_exists(record: str, root: str) -> bool:
    parts = record.split("/")
    if os.path.isabs(record) or ".." in parts:
        return False
    return os.path.isfile(os.path.join(root, *parts))


def _enrich(row: dict, qvalues: dict, root: str) -> dict[str, Any]:
    return {
        **row,
        "q": qvalues.get(row["id"]),
        "record_exists": _record_exists(row["record"], root),
        "record_kind": _record_kind(row["record"]),
    }


@api_v1.route("/research/ledger", methods=["GET"])
@require_auth
def research_ledger():
    # Imported per request, like `analytics_registry` does with its reader.
    # `LEDGER_PATH` is read here, not bound as a default, so a test can point
    # the endpoint at a fixture ledger.
    from swingbot.core.backtesting.instrument import stats

    path = stats.LEDGER_PATH
    try:
        rows = stats.load_ledger(path)
    except ValueError as exc:
        raise ApiError("ledger_invalid", str(exc), 500) from exc

    # <root>/docs/superpowers/results/<ledger>: record paths are relative to
    # the tree the ledger itself lives in.
    root = str(path.parents[3])
    qvalues = stats.ledger_qvalues(rows)
    return jsonify({
        "rows": [_enrich(row, qvalues, root) for row in rows],
        "q_family_m": sum(1 for row in rows if row["p"] is not None),
        "verdicts": list(stats.VERDICTS),
        "instruments": list(stats.INSTRUMENTS),
    })
```

- [ ] **Step 4: Register the module**

In `swingbot/admin/api_v1/__init__.py`, inside `register()`, add `research` to the import list, keeping it alphabetical:

```python
    from . import (analytics, calendar, dashboard, jobs, market,  # noqa: F401
                   research, risk, session, system, trade_commands, trades,
                   versions, watchlist)  # (register routes)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py`
Expected: `VERDICT: PASS`.

If `test_q_matches_ledger_qvalues_and_the_family_size` fails on NaN or float type, print `stats.ledger_qvalues(rows)`: the endpoint must send exactly what that function returns, so fix the test's comparison, not the endpoint.

- [ ] **Step 6: Route a ledger edit to this test**

In `scripts/dev/select_tests.py`, extend the ledger row of `DATA_READERS`:

```python
    # The pre-registration ledger is loaded and validated row by row.
    ("docs/superpowers/results/preregistration-ledger.jsonl",
     ("tests/backtesting/test_preregistration_ledger_file.py",
      "tests/backtesting/test_instrument_stats_ledger.py",
      "tests/scripts/test_preregistration_ledger_cli.py",
      "tests/admin/test_api_v1_research.py")),
```

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 7: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/admin/api_v1/research.py`
Expected: no output.

```bash
git add swingbot/admin/api_v1/research.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_v1_research.py
git commit -m "feat(v150): GET /api/v1/research/ledger -- ledger rows with q, record flags and filter vocabularies"
git add scripts/dev/select_tests.py
git commit -m "test(v150): a ledger edit selects the research endpoint test"
```


---

### Task V150-2: Document where the reports run in production

**Model:** haiku — one fixed paragraph added to a runbook; the text is given by this brief.

**Files:**
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (after the "Remote commands through `ssh-hetzner.sh`" paragraph, about line 421)

**Interfaces:**
- Consumes: nothing.
- Produces: the command V150-11's "Not yet run" state quotes.

- [ ] **Step 1: Find the paragraph**

Run: `grep -n "Remote commands through" docs/deploy/DEPLOY_HETZNER.md`
Expected: one line, near 421.

- [ ] **Step 2: Add the section directly after that paragraph**

````markdown
**Running the Reports workspace's reports (v146, v147).** The live trade book is on this VM, so
both report scripts run here, inside the bot container, and write `/opt/swing-bot/data/reports/`.
`data/` is bind-mounted into both containers, so the admin shows a new result without a rebuild
or a restart:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/<script>.py"
```

`<script>` is the v146 or v147 report script; each one's own spec names its arguments. The TRAIN
half of each report is a backtest produced on the dev machine. Upload its JSONL inputs first, over
ssh stdin (never `scp`, never another key path):

```bash
bash scripts/ops/ssh-hetzner.sh "mkdir -p /opt/swing-bot/data/reports/inputs"
bash scripts/ops/ssh-hetzner.sh "cat > /opt/swing-bot/data/reports/inputs/<file>" < <local file>
```

Each run overwrites its one result file; there is no history beyond the latest. A report that has
never run shows as "Not yet run" on the page, which is a state, not a fault. These runs are manual:
nothing schedules them.
````

- [ ] **Step 3: Run the test that parses this runbook**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backup_db.py`
Expected: `VERDICT: PASS` (it parses the backup commands this file documents; the new section adds none).

- [ ] **Step 4: Commit**

```bash
git add docs/deploy/DEPLOY_HETZNER.md
git commit -m "docs(v150): where the v146/v147 reports run in production, and the TRAIN-input upload"
```


---

### Task V150-3: `GET /api/v1/reports/*`

**Model:** sonnet — one admin endpoint module wrapping two loaders; the envelope is given by the spec.

**Blocked until** the gate in `_0-index` § "Blocked tasks" passes. Run it first; if it fails, stop.

**Files:**
- Create: `swingbot/admin/api_v1/reports.py`
- Create: `tests/admin/test_api_v1_reports.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (the import list V150-1 edited)

**Interfaces:**
- Consumes (v146, v147): `swingbot.core.analytics.expectancy_attribution.load_latest() -> dict | None`, `swingbot.core.analytics.gate_counterfactual_report.load_report() -> dict | None`. If the gate showed the loaders in separate light modules, use those paths in `_load_attribution` / `_load_gates` below and nowhere else.
- Produces:
  - `GET /api/v1/reports/expectancy-attribution`, `GET /api/v1/reports/gate-counterfactual`, each →
    `{ "status": "ok" | "not_run", "generated_at": str | null, "result": dict | null }`
  - A loader that raises → `500 {"error": {"code": "report_unreadable", "message": …}}`
  - Module attributes `reports._load_attribution` and `reports._load_gates` (zero-argument callables; tests replace them).

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_reports.py`:

```python
"""GET /api/v1/reports/* — the v146 and v147 results, served unchanged (v150).

The endpoints compute nothing. Each calls one loader and wraps what it
returns: `None` is "not yet run" (a 200, a state the page renders), a dict
passes through untouched, and a loader that raises is a real fault (the
writers are atomic, so a present-but-unparseable file cannot be a race).
"""
import ast
import pathlib

import pytest

from tests.admin.api_v1_contract import NULLABLE_STR, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
_ENVELOPE = {"status": str, "generated_at": NULLABLE_STR, "result": (dict, type(None))}

# (url, the module attribute that loads it)
_REPORTS = [
    ("/api/v1/reports/expectancy-attribution", "_load_attribution"),
    ("/api/v1/reports/gate-counterfactual", "_load_gates"),
]


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def reports():
    from swingbot.admin.api_v1 import reports as module
    return module


@pytest.mark.parametrize("url, _loader", _REPORTS)
def test_requires_auth(client, url, _loader):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_never_run_is_a_200_not_run(logged_in, reports, monkeypatch, url, loader):
    monkeypatch.setattr(reports, loader, lambda: None)
    resp = logged_in.get(url)
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, _ENVELOPE)
    assert body == {"status": "not_run", "generated_at": None, "result": None}


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_a_result_passes_through_unchanged(logged_in, reports, monkeypatch, url, loader):
    result = {"generated_at": "2026-10-09T21:30:00+00:00", "verdict": "WEAK",
              "nested": {"buckets": [{"label": "0-5", "n": 12, "thin": True}],
                         "none": None, "float": 0.125}}
    monkeypatch.setattr(reports, loader, lambda: result)
    body = logged_in.get(url).get_json()
    assert_shape(body, _ENVELOPE)
    assert body["status"] == "ok"
    assert body["generated_at"] == "2026-10-09T21:30:00+00:00"
    assert body["result"] == result


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_a_result_without_generated_at_still_serves(logged_in, reports, monkeypatch, url, loader):
    monkeypatch.setattr(reports, loader, lambda: {"verdict": "WEAK"})
    body = logged_in.get(url).get_json()
    assert (body["status"], body["generated_at"]) == ("ok", None)


@pytest.mark.parametrize("url, loader", _REPORTS)
def test_a_loader_that_raises_is_a_500_never_a_silent_not_run(
        logged_in, reports, monkeypatch, url, loader):
    def boom():
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(reports, loader, boom)
    resp = logged_in.get(url)
    assert resp.status_code == 500
    error = resp.get_json()["error"]
    assert error["code"] == "report_unreadable"
    assert "Expecting value" in error["message"]


def test_one_report_failing_does_not_affect_the_other(logged_in, reports, monkeypatch):
    def boom():
        raise OSError("disk")

    monkeypatch.setattr(reports, "_load_attribution", boom)
    monkeypatch.setattr(reports, "_load_gates", lambda: None)
    assert logged_in.get(_REPORTS[0][0]).status_code == 500
    assert logged_in.get(_REPORTS[1][0]).get_json()["status"] == "not_run"


def test_the_real_loaders_answer_without_a_report_file(logged_in):
    """Unpatched, against the test data dir: no file yet, so `not_run`."""
    for url, _loader in _REPORTS:
        assert logged_in.get(url).get_json()["status"] == "not_run"


def test_no_module_level_import_from_swingbot_core(reports):
    """The report modules load only when a report endpoint is called.

    The spec asked for a fresh-interpreter `sys.modules` check; an api_v1
    module cannot be imported on its own (it reaches `swingbot.admin.app`,
    which registers every endpoint), so this pins the same intent statically.
    """
    tree = ast.parse(pathlib.Path(reports.__file__).read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:
        names = []
        if isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        offenders += [name for name in names if name.startswith("swingbot.core")]
    assert offenders == []
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_reports.py`
Expected: FAIL: `ImportError: cannot import name 'reports' from 'swingbot.admin.api_v1'`.

- [ ] **Step 3: Write the endpoint**

Create `swingbot/admin/api_v1/reports.py`:

```python
"""GET /api/v1/reports/* — the v146 and v147 results behind the Reports page.

Display only. Neither endpoint computes a figure, applies a floor or reshapes
a field: each calls one loader and wraps its return value.

    { "status": "ok" | "not_run", "generated_at": str | null, "result": {...} | null }

`not_run` is a 200, not a 404: the endpoint is answering truthfully that
nothing has been produced yet, and the page renders that as a state. A loader
that raises is different. The report writers replace their file atomically
(temp file + `os.replace`), so a file that is present but unreadable is never
a half-written one; it is a real fault and surfaces as a 500 rather than
hiding behind `not_run`.

No request runs a backtest or builds a report. The results are produced by
scripts run on the VM (`docs/deploy/DEPLOY_HETZNER.md`); `data/` is mounted
into both containers, so a new run is visible here without a restart.
"""
from __future__ import annotations

from typing import Callable

from flask import jsonify

from . import ApiError, api_v1
from .auth import require_auth


def _load_attribution() -> dict | None:
    # Imported on call: the report modules are heavy to import and only these
    # two endpoints need them.
    from swingbot.core.analytics import expectancy_attribution

    return expectancy_attribution.load_latest()


def _load_gates() -> dict | None:
    from swingbot.core.analytics import gate_counterfactual_report

    return gate_counterfactual_report.load_report()


def _envelope(load: Callable[[], dict | None]):
    try:
        result = load()
    except Exception as exc:  # noqa: BLE001 - any loader failure is the same 500
        raise ApiError("report_unreadable", f"{type(exc).__name__}: {exc}", 500) from exc
    if result is None:
        return jsonify({"status": "not_run", "generated_at": None, "result": None})
    return jsonify({"status": "ok", "generated_at": result.get("generated_at"),
                    "result": result})


@api_v1.route("/reports/expectancy-attribution", methods=["GET"])
@require_auth
def report_expectancy_attribution():
    return _envelope(lambda: _load_attribution())


@api_v1.route("/reports/gate-counterfactual", methods=["GET"])
@require_auth
def report_gate_counterfactual():
    return _envelope(lambda: _load_gates())
```

The two handlers wrap the loader in a `lambda` on purpose: it looks the name up at call time, so `monkeypatch.setattr(reports, "_load_gates", …)` takes effect. Passing `_load_gates` directly would also work today; the lambda keeps that true if the handlers are ever decorated or cached.

- [ ] **Step 4: Register the module**

In `swingbot/admin/api_v1/__init__.py`, add `reports` to the list V150-1 edited:

```python
    from . import (analytics, calendar, dashboard, jobs, market,  # noqa: F401
                   reports, research, risk, session, system, trade_commands,
                   trades, versions, watchlist)  # (register routes)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_reports.py`
Expected: `VERDICT: PASS`.

If `test_the_real_loaders_answer_without_a_report_file` fails because a loader reads a path baked at import time (so it sees the developer's real `data/reports/`), that is the conftest trap described at the top of `tests/admin/conftest.py`. Report it as a v146/v147 loader defect (the loader must resolve `config.DATA_DIR` per call); do not add the report modules to `_RELOAD_MODULES` to hide it.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/admin/api_v1/reports.py`
Expected: no output.

```bash
git add swingbot/admin/api_v1/reports.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_v1_reports.py
git commit -m "feat(v150): GET /api/v1/reports/* -- the v146/v147 results in a not_run-aware envelope"
```


---

### Task V150-4: Research models, the client method, and `StrategyRow` in `api/models.ts`

**Model:** sonnet — typed wire models plus a type move that must leave every Analytics import compiling.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (the `AnalyticsRegistry` interface, about line 662; new interfaces after it)
- Modify: `frontend/src/app/api/api-client.ts` (after `analyticsPlans()`, about line 281)
- Modify: `frontend/src/app/stores/analytics.store.ts` (the `StrategyRow` interface, about lines 48-73)
- Test: `frontend/src/app/api/api-client.spec.ts` if it exists (check with `ls frontend/src/app/api/*.spec.ts`); otherwise the store specs in V150-6 cover the method.

**Interfaces:**
- Consumes: the response shape in V150-1's Interfaces block.
- Produces (in `api/models.ts`):
  - `StrategyRow` (moved, unchanged), `AnalyticsRegistry { registry: StrategyRow[] }`
  - `LedgerRecordKind = 'results' | 'specs' | 'plans' | 'other'`
  - `LedgerRow`, `ResearchLedger`
  - `ReportEnvelope<T> { status: 'ok' | 'not_run'; generated_at: string | null; result: T | null }`
- Produces (in `ApiClient`): `researchLedger(): Observable<ResearchLedger>`
- `stores/analytics.store.ts` keeps exporting the name `StrategyRow`.

- [ ] **Step 1: Move `StrategyRow`**

Cut the whole `StrategyRow` interface, with its doc comments, out of `frontend/src/app/stores/analytics.store.ts` and paste it into `frontend/src/app/api/models.ts` directly above `AnalyticsRegistry`. Do not change a field.

In `analytics.store.ts`, where the interface was, leave a re-export, and import the type for the store's own use (merge it into the existing `../api/models` import if there is one):

```ts
import { StrategyRow } from '../api/models';

/** Moved to `api/models.ts` (v150): the Research workspace reads the same
 *  rows. Re-exported so every existing Analytics import keeps working. */
export type { StrategyRow } from '../api/models';
```

- [ ] **Step 2: Narrow `AnalyticsRegistry` and add the Research models**

In `frontend/src/app/api/models.ts`, change the last line of the `AnalyticsRegistry` interface and append the new types after it:

```ts
export interface AnalyticsRegistry {
  registry: StrategyRow[];
}

/* -- research (v150) ---------------------------------------------------- */

/** Which docs folder a ledger row's `record` points into. */
export type LedgerRecordKind = 'results' | 'specs' | 'plans' | 'other';

/** One pre-registration: the nine fields the ledger stores, plus three the
 *  endpoint derives. `n`, `exp_r` and `p` are null on most historical rows —
 *  a null is "not recorded", never zero. */
export interface LedgerRow {
  id: string;
  /** `YYYY-MM-DD`. */
  date: string;
  hypothesis: string;
  instrument: string;
  n: number | null;
  exp_r: number | null;
  p: number | null;
  verdict: string;
  /** Repo-relative path of the results doc, spec or plan that records it. */
  record: string;
  /** BH q-value across every ledger row with a p-value. Reported, never
   *  gating; null when `p` is null. Filters do not change it. */
  q: number | null;
  /** Whether `record` resolves in the deployed build. */
  record_exists: boolean;
  record_kind: LedgerRecordKind;
}

/** `GET /research/ledger`. The vocabularies come from the server so a
 *  verdict added to the ledger later appears as a filter without a release. */
export interface ResearchLedger {
  rows: LedgerRow[];
  /** How many rows have a p-value: the BH family size behind every `q`. */
  q_family_m: number;
  verdicts: string[];
  instruments: string[];
}

/* -- reports (v150) ----------------------------------------------------- */

/** The envelope both `GET /reports/*` endpoints return. `not_run` is a
 *  state the page renders ("Not yet run"), not an error. */
export interface ReportEnvelope<T> {
  status: 'ok' | 'not_run';
  generated_at: string | null;
  result: T | null;
}
```

- [ ] **Step 3: Add the client method**

In `frontend/src/app/api/api-client.ts`, add `ResearchLedger` to the `./models` import, and after `analyticsPlans()`:

```ts
  /* -- research ---------------------------------------------------------- */

  /** The whole pre-registration ledger. Filtering and paging are client-side. */
  researchLedger(): Observable<ResearchLedger> {
    return this.http.get<ResearchLedger>(`${this.base}/research/ledger`);
  }
```

- [ ] **Step 4: Remove any cast the narrowing made redundant**

Run: `grep -n "as StrategyRow\[\]\|registry as\|unknown\[\]" frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/trade-detail.store.ts`

Where a line casts `registry` (now typed) to `StrategyRow[]`, delete the cast and keep the expression. Leave any other `unknown[]` alone.

- [ ] **Step 5: Type-check and run the specs that import the moved type**

```bash
cd frontend
npx tsc -p tsconfig.app.json --noEmit
npm test -- --include src/app/stores/analytics.store.spec.ts --include src/app/workspaces/analytics/analytics.columns.spec.ts --include src/app/stores/trade-detail.store.spec.ts --watch=false
```

Expected: no type errors; all three spec files pass. A failure here means an import of `StrategyRow` from `analytics.store` stopped resolving: the re-export in Step 1 is missing or misspelt.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/trade-detail.store.ts
git commit -m "feat(v150): research ledger wire types and client method; StrategyRow moves to api/models"
```


---

### Task V150-5: Pin the report wire shapes — models, client methods, fixtures

**Model:** opus — it reads two statistical report modules and fixes the contract every Reports UI task is tested against; a wrong name here is silently `undefined` on the page.

**Blocked until** the gate in `_0-index` § "Blocked tasks" passes and V150-3 is merged into the worktree.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append to the "reports (v150)" section V150-4 created)
- Modify: `frontend/src/app/api/api-client.ts` (after `researchLedger()`)
- Create: `frontend/src/app/testing/report-fixtures.ts`
- Modify: `docs/superpowers/plans/2026-10-09-v150-reports-research-workspaces_0-index.md` (§ "Assumed wire shapes": replace assumptions with what was found)

**Interfaces:**
- Consumes: the dicts `load_latest()` and `load_report()` actually return on `main`.
- Produces (names every later Reports task imports):
  - `api/models.ts`: `VerdictOfRecord`, `AttributionMonotonicity`, `AttributionFactor`, `AttributionBucket`, `AttributionPopulation`, `ExpectancyAttribution`, `GateCell`, `GateRow`, `GateCounterfactual`
  - `ApiClient.reportExpectancyAttribution(): Observable<ReportEnvelope<ExpectancyAttribution>>`, `ApiClient.reportGateCounterfactual(): Observable<ReportEnvelope<GateCounterfactual>>`
  - `testing/report-fixtures.ts`: `ATTRIBUTION: ExpectancyAttribution`, `GATES: GateCounterfactual`, `ok<T>(result: T & { generated_at: string }): ReportEnvelope<T>`, `NOT_RUN: ReportEnvelope<never>`

- [ ] **Step 1: Read the real shapes**

```bash
git grep -n "def load_latest\|def build_\|def _population\|def _bucket\|def _factor\|def _monotonicity\|verdict_of_record\|\"looks\"\|\"thin\"" -- swingbot/core/analytics/expectancy_attribution.py
git grep -n "def load_report\|def build_report\|def _cell\|def _row\|verdict_of_record\|over_cap\|in_sample\|near_miss\|WAITING" -- swingbot/core/analytics/gate_counterfactual_report.py
ls tests/analytics/ | grep -i "attribution\|counterfactual"
```

Then read the functions that build each dict, and the tests' fixture results, until every key of both results is known. Write the two shapes down as they are.

- [ ] **Step 2: Compare with the plan's assumptions and record the differences**

Open `_0-index` § "Assumed wire shapes". For each assumed name, mark it confirmed or write the real name. Rewrite that section so it states the real shapes, headed `## Wire shapes (pinned <date> from <commit>)`. Three points must be answered explicitly in it, because later tasks branch on them:

1. Where the per-population direction and horizon splits live (assumed `populations.<p>.splits.direction|horizon`).
2. Whether v147 persists the two non-verdict states (`"no TRAIN population"`, `"no verdict — no-plan"`) or the page derives them from the gate name (assumed: a `note` field on the cell).
3. Whether the latest reading's interval is `ci_low` / `ci_high` or a nested object.

- [ ] **Step 3: Write the models**

Append to the "reports (v150)" section of `frontend/src/app/api/models.ts`. This is the text for the assumed shapes; **change every name Step 2 found to differ**, and nothing else:

```ts
/** The verdict that counts: fixed at the first qualifying run and carried
 *  forward unchanged by every later one. */
export interface VerdictOfRecord {
  verdict: string;
  /** `YYYY-MM-DD` of the run that fixed it. */
  date: string;
  n: number;
}

/** v146: does confidence order R? Spearman rho plus the top-minus-bottom
 *  tercile ExpR with its week-clustered 95% interval. */
export interface AttributionMonotonicity {
  n: number;
  spearman_rho: number | null;
  tercile_spread: number | null;
  ci_low: number | null;
  ci_high: number | null;
  /** The interval lies wholly below zero. Reported inside NOT PREDICTIVE. */
  inverted: boolean;
}

/** v146: ExpR where a confidence factor scored > 0, minus where it scored 0. */
export interface AttributionFactor {
  key: string;
  n: number;
  delta: number | null;
  ci_low: number | null;
  ci_high: number | null;
  /** BH q over every look on the report. */
  q: number | null;
}

export interface AttributionBucket {
  label: string;
  n: number;
  win_rate: number | null;
  exp_r: number | null;
  /** v146 sets this on every bucket below its floor. The page never tests N. */
  thin: boolean;
  q: number | null;
}

export interface AttributionPopulation {
  window: string | null;
  n: number;
  monotonicity: AttributionMonotonicity;
  factors: AttributionFactor[];
  /** Dimension key -> its buckets, in the report's own order. */
  buckets: Record<string, AttributionBucket[]>;
  splits: {
    direction: Record<string, AttributionMonotonicity>;
    horizon: Record<string, AttributionMonotonicity>;
  };
}

/** `load_latest()` of `swingbot/core/analytics/expectancy_attribution.py`. */
export interface ExpectancyAttribution {
  generated_at: string;
  /** The latest run's reading. Descriptive once a verdict of record exists. */
  verdict: string;
  verdict_of_record: VerdictOfRecord;
  /** The BH family size behind every q on this report. */
  looks: number;
  seed: number;
  /** Never pooled. Either side may be absent from a run. */
  populations: {
    live: AttributionPopulation | null;
    train: AttributionPopulation | null;
  };
}

/** v147: one verdict cell, gate x population. */
export interface GateCell {
  gate: string;
  population: 'live' | 'train';
  /** The latest reading: GATE EARNS | GATE COSTS | INCONCLUSIVE | WAITING. */
  verdict: string;
  /** Distinct filled blocked setups. v147 counts it; the page never does. */
  n: number;
  /** Null until the first reading at or above v147's floor. */
  verdict_of_record: VerdictOfRecord | null;
  /** Blocked ExpR minus taken ExpR, its interval and BH q over the cells. */
  latest: { difference: number | null; ci_low: number | null; ci_high: number | null; q: number | null } | null;
  in_sample: boolean;
  /** A fixed non-verdict state, e.g. "no TRAIN population". */
  note: string | null;
}

/** v147: one detail row, gate x reason x population. */
export interface GateRow {
  gate: string;
  reason: string;
  population: 'live' | 'train';
  blocked_n: number;
  no_plan_n: number;
  fill_rate: number | null;
  blocked_exp_r: number | null;
  blocked_win_rate: number | null;
  taken_exp_r: number | null;
  taken_win_rate: number | null;
  near_miss_n: number | null;
  near_miss_exp_r: number | null;
  rest_n: number | null;
  rest_exp_r: number | null;
  /** `risk_cap` rows only: the fixed-dollar-risk figure beside R. */
  dollar_risk: number | null;
  over_cap: boolean;
  in_sample: boolean;
}

/** `load_report()` of `swingbot/core/analytics/gate_counterfactual_report.py`. */
export interface GateCounterfactual {
  generated_at: string;
  live_window: string | null;
  cells: GateCell[];
  rows: GateRow[];
}
```

- [ ] **Step 4: Add the client methods**

In `frontend/src/app/api/api-client.ts`, add `ExpectancyAttribution`, `GateCounterfactual` and `ReportEnvelope` to the `./models` import, and after `researchLedger()`:

```ts
  /* -- reports ----------------------------------------------------------- */

  /** v146's latest result, or `status: 'not_run'`. Never recomputed here. */
  reportExpectancyAttribution(): Observable<ReportEnvelope<ExpectancyAttribution>> {
    return this.http.get<ReportEnvelope<ExpectancyAttribution>>(`${this.base}/reports/expectancy-attribution`);
  }

  /** v147's latest result, or `status: 'not_run'`. */
  reportGateCounterfactual(): Observable<ReportEnvelope<GateCounterfactual>> {
    return this.http.get<ReportEnvelope<GateCounterfactual>>(`${this.base}/reports/gate-counterfactual`);
  }
```

- [ ] **Step 5: Write the shared fixtures**

Create `frontend/src/app/testing/report-fixtures.ts`. The values are chosen so each display rule has exactly one case that exercises it; keep those cases when renaming fields:

```ts
import {
  AttributionMonotonicity,
  AttributionPopulation,
  ExpectancyAttribution,
  GateCounterfactual,
  ReportEnvelope,
} from '../api/models';

/* Shared by every Reports spec (store, both tabs, the shell), so the two
 * tabs cannot be tested against two different ideas of the wire.
 *
 * Cases each fixture carries on purpose:
 *   ATTRIBUTION  verdict of record WEAK (2026-10-12, n 214) while the latest
 *                reading says PREDICTIVE: the page must show WEAK as THE
 *                verdict; one thin bucket (`0-5`, n 12); one factor at
 *                q 0.04 (a screen candidate) and one at q 0.31 (not); one
 *                bucket at q 0.08 (candidate) and a THIN bucket at q 0.01
 *                (must NOT be marked: thin enters no marker).
 *   GATES        five cells; live `rs` is WAITING at n 29; live `risk_cap`
 *                has a verdict of record GATE EARNS that differs from its
 *                latest reading INCONCLUSIVE; TRAIN `compression` is
 *                in-sample; a `risk_cap` row is over-cap with a dollar figure.
 */

const mono = (over: Partial<AttributionMonotonicity> = {}): AttributionMonotonicity => ({
  n: 214, spearman_rho: 0.18, tercile_spread: 0.22, ci_low: 0.03, ci_high: 0.41,
  inverted: false, ...over,
});

const LIVE: AttributionPopulation = {
  window: '2026-07-01..2026-10-09',
  n: 214,
  monotonicity: mono(),
  factors: [
    { key: 'trend_alignment', n: 214, delta: 0.19, ci_low: 0.04, ci_high: 0.35, q: 0.04 },
    { key: 'volume_confirmation', n: 214, delta: 0.03, ci_low: -0.12, ci_high: 0.18, q: 0.31 },
  ],
  buckets: {
    regime: [
      { label: 'bull', n: 140, win_rate: 0.58, exp_r: 0.24, thin: false, q: 0.08 },
      { label: 'bear', n: 74, win_rate: 0.41, exp_r: -0.06, thin: false, q: 0.42 },
    ],
    earnings_bucket: [
      { label: '0-5', n: 12, win_rate: 0.33, exp_r: -0.4, thin: true, q: 0.01 },
      { label: '>20', n: 202, win_rate: 0.54, exp_r: 0.16, thin: false, q: 0.6 },
    ],
  },
  splits: {
    direction: { long: mono({ n: 170 }), short: mono({ n: 44, tercile_spread: -0.05, ci_low: -0.3, ci_high: 0.2 }) },
    horizon: { swing: mono({ n: 150 }), position: mono({ n: 64 }) },
  },
};

const TRAIN: AttributionPopulation = {
  window: '2019-01-01..2023-12-31',
  n: 3120,
  monotonicity: mono({ n: 3120, spearman_rho: 0.06, tercile_spread: 0.04, ci_low: -0.02, ci_high: 0.1 }),
  factors: [
    { key: 'trend_alignment', n: 3120, delta: 0.05, ci_low: -0.01, ci_high: 0.11, q: 0.2 },
    { key: 'volume_confirmation', n: 3120, delta: 0.01, ci_low: -0.04, ci_high: 0.06, q: 0.7 },
  ],
  buckets: {
    regime: [
      { label: 'bull', n: 2100, win_rate: 0.52, exp_r: 0.11, thin: false, q: 0.3 },
      { label: 'bear', n: 1020, win_rate: 0.47, exp_r: 0.02, thin: false, q: 0.5 },
    ],
    earnings_bucket: [
      { label: '0-5', n: 310, win_rate: 0.5, exp_r: 0.05, thin: false, q: 0.5 },
      { label: '>20', n: 2810, win_rate: 0.51, exp_r: 0.09, thin: false, q: 0.5 },
    ],
  },
  splits: {
    direction: { long: mono({ n: 2500 }), short: mono({ n: 620 }) },
    horizon: { swing: mono({ n: 2200 }), position: mono({ n: 920 }) },
  },
};

export const ATTRIBUTION: ExpectancyAttribution = {
  generated_at: '2026-10-20T21:30:00+00:00',
  verdict: 'PREDICTIVE',
  verdict_of_record: { verdict: 'WEAK', date: '2026-10-12', n: 214 },
  looks: 37,
  seed: 42,
  populations: { live: LIVE, train: TRAIN },
};

export const GATES: GateCounterfactual = {
  generated_at: '2026-10-20T21:45:00+00:00',
  live_window: '2026-10-01..2026-10-20',
  cells: [
    { gate: 'rs', population: 'live', verdict: 'WAITING', n: 29, verdict_of_record: null,
      latest: { difference: -0.3, ci_low: -0.9, ci_high: 0.2, q: 0.4 }, in_sample: false, note: null },
    { gate: 'rs', population: 'train', verdict: 'WAITING', n: 0, verdict_of_record: null,
      latest: null, in_sample: false, note: 'no TRAIN population' },
    { gate: 'risk_cap', population: 'live', verdict: 'INCONCLUSIVE', n: 46,
      verdict_of_record: { verdict: 'GATE EARNS', date: '2026-10-14', n: 31 },
      latest: { difference: -0.08, ci_low: -0.31, ci_high: 0.12, q: 0.44 }, in_sample: false, note: null },
    { gate: 'risk_cap', population: 'train', verdict: 'GATE EARNS', n: 412,
      verdict_of_record: { verdict: 'GATE EARNS', date: '2026-10-14', n: 412 },
      latest: { difference: -0.21, ci_low: -0.33, ci_high: -0.09, q: 0.01 }, in_sample: false, note: null },
    { gate: 'compression', population: 'live', verdict: 'INCONCLUSIVE', n: 38,
      verdict_of_record: { verdict: 'INCONCLUSIVE', date: '2026-10-16', n: 30 },
      latest: { difference: 0.05, ci_low: -0.2, ci_high: 0.3, q: 0.7 }, in_sample: false, note: null },
    { gate: 'compression', population: 'train', verdict: 'GATE COSTS', n: 260,
      verdict_of_record: { verdict: 'GATE COSTS', date: '2026-10-14', n: 260 },
      latest: { difference: 0.17, ci_low: 0.04, ci_high: 0.3, q: 0.03 }, in_sample: true, note: null },
  ],
  rows: [
    { gate: 'rs', reason: 'rs_below_floor', population: 'live', blocked_n: 29, no_plan_n: 4,
      fill_rate: 0.72, blocked_exp_r: -0.2, blocked_win_rate: 0.4, taken_exp_r: 0.1,
      taken_win_rate: 0.52, near_miss_n: 9, near_miss_exp_r: 0.05, rest_n: 20, rest_exp_r: -0.31,
      dollar_risk: null, over_cap: false, in_sample: false },
    { gate: 'risk_cap', reason: 'risk_cap_exceeded', population: 'live', blocked_n: 46, no_plan_n: 0,
      fill_rate: 0.8, blocked_exp_r: 0.02, blocked_win_rate: 0.48, taken_exp_r: 0.1,
      taken_win_rate: 0.52, near_miss_n: 12, near_miss_exp_r: 0.08, rest_n: 34, rest_exp_r: 0,
      dollar_risk: 412.5, over_cap: true, in_sample: false },
    { gate: 'compression', reason: 'range_too_wide', population: 'train', blocked_n: 260, no_plan_n: 11,
      fill_rate: 0.66, blocked_exp_r: 0.27, blocked_win_rate: 0.55, taken_exp_r: 0.1,
      taken_win_rate: 0.5, near_miss_n: 80, near_miss_exp_r: 0.3, rest_n: 180, rest_exp_r: 0.25,
      dollar_risk: null, over_cap: false, in_sample: true },
  ],
};

export const ok = <T extends { generated_at: string }>(result: T): ReportEnvelope<T> => ({
  status: 'ok', generated_at: result.generated_at, result,
});

export const NOT_RUN: ReportEnvelope<never> = { status: 'not_run', generated_at: null, result: null };
```

If Step 2 found that v147 does not persist a `note`, delete the `note` field from `GateCell` and from this fixture, and state in the index that `gatesView` (V150-7) derives the two states from the gate name and population.

- [ ] **Step 6: Check the fixtures against the real modules**

The fixtures are hand-written; this proves they are the modules' shape. Dump one real result's keys and compare by eye with the fixture, key by key, at every level:

```bash
python - <<'EOF'
import json
from swingbot.core.analytics import expectancy_attribution as a, gate_counterfactual_report as g

def keys(value, depth=0, name="result"):
    if isinstance(value, dict):
        print("  " * depth + f"{name}: {{{', '.join(value)}}}")
        for key, inner in list(value.items())[:6]:
            keys(inner, depth + 1, key)
    elif isinstance(value, list) and value:
        keys(value[0], depth, name + "[0]")

for label, result in (("v146", a.load_latest()), ("v147", g.load_report())):
    print("==", label, "(None means: build one from the module's own test fixture)")
    if result is not None:
        keys(result)
EOF
```

If both print `None` (no report has been run on this machine), build each result from its module's test fixture instead (the builders' unit tests construct one) and pass it to `keys`. Every key the fixtures use must appear; every key the modules emit must be in the TypeScript models.

- [ ] **Step 7: Type-check and commit**

```bash
cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx tsc -p tsconfig.spec.json --noEmit; cd ..
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/testing/report-fixtures.ts
git commit -m "feat(v150): report wire types, client methods and shared fixtures, pinned from the v146/v147 modules"
git add docs/superpowers/plans/2026-10-09-v150-reports-research-workspaces_0-index.md
git commit -m "docs(v150): record the pinned v146/v147 wire shapes in the plan index"
```

