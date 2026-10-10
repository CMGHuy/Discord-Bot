# v149 Hygiene gates: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief V149-3` or `grep -n "^### Task V149-3:" -A 400 docs/superpowers/plans/2026-10-09-v149-hygiene-gates.md`.

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v149-hygiene-gates-design.md`](../specs/2026-10-09-v149-hygiene-gates-design.md)

**Goal:** Turn three prose rules into failing checks: a ratcheting cyclomatic-complexity gate (H1), ESLint on the Angular frontend with a frozen baseline (H2), and a test that every `.py` path `README.md` names exists (H3).

**Architecture:** H1 is one script, `scripts/dev/complexity_gate.py`, that measures every tracked `.py` file with radon, compares the offenders (score >= 15) to a checked-in `complexity_baseline.json`, and fails on any difference in either direction; `--update` can only shrink the baseline. H2 is angular-eslint's flat config plus ESLint bulk suppressions (`frontend/eslint-suppressions.json`), run as `npm run lint`. H3 is a regex over `README.md`. Both gates freeze today's debt; this plan fixes no existing offender and no existing lint violation.

**Tech Stack:** Python 3.11, radon 6.0.1, pytest; Angular 21, ESLint 9 (>= 9.24), angular-eslint 21, typescript-eslint; GitHub Actions.

## Global Constraints

- **No existing complexity offender and no existing lint violation is fixed here.** A task that "tidies while it is there" is out of scope (spec § Scope, Out).
- `radon==6.0.1`, exact pin, in `requirements.txt` beside `pyflakes==3.4.0`. There is no other requirements file.
- The threshold, **15**, is a constant in the script. The baseline carries no `threshold` field.
- The baseline is **generated from the committed tree at implementation time** (`--init`), never copied from the spec's table.
- The gate scans **tracked files only** (`git ls-files`): `*.py` under `swingbot/`, `scripts/`, `tests/`, plus `bot.py` and `admin_ui.py`. `.claude/` stays out.
- Every function this plan writes ends below complexity 15. The gate script is gated by itself.
- No role-agent prompt (`.claude/agents/*.md`) changes.
- No Prettier, no stylistic ESLint rules, no lint or format pre-commit hook.
- ESLint lints `frontend/src/` only. `frontend/chart-harness/` and the root config files are not linted.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test file>`). The full suite runs once, in V149-8.
- `CLAUDE.md` stays under 200 lines (175 today).
- Both new CI steps sit in jobs `container-healthcheck` needs, so a red gate blocks the production deploy. That is intended (spec § Blast radius).

## Where to work

- **Branch and worktree:** `2026-10-09-v149-hygiene-gates` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v149-hygiene-gates`. V149-1 Step 0 creates it with the `worktree-lifecycle` skill. Every task runs there. Name the worktree in every subagent dispatch, and after each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` to confirm the main tree is unchanged.
- **Production:** nothing in this plan touches the Hetzner VM.
- **Close-out:** the spec carries `Panel: staff-engineer, senior-engineer`, so `/panel` reviews `main...<branch>` before `/close-out`.

## File map

| File | Task | Responsibility |
|---|---|---|
| `tests/dev/test_readme_paths.py` (new) | V149-1 | Every backticked `.py` token in the README is an existing repo path |
| `README.md` | V149-1 | Module lists and the `HORIZONS` pointer corrected to full paths |
| `scripts/dev/complexity_gate.py` (new) | V149-2, V149-3 | Measure, compare, shrink; the three modes |
| `tests/dev/test_complexity_gate.py` (new) | V149-2, V149-3, V149-4 | Unit tests, then the slow whole-tree test |
| `requirements.txt` | V149-2 | `radon==6.0.1` |
| `scripts/dev/complexity_baseline.json` (new) | V149-4 | Today's offenders |
| `scripts/dev/select_tests.py`, `tests/dev/test_select_tests.py` | V149-1, V149-4 | One `DATA_READERS` row each |
| `frontend/eslint.config.js`, `frontend/eslint-suppressions.json` (new), `frontend/package.json`, `frontend/package-lock.json`, `frontend/angular.json` | V149-5 | ESLint and its frozen baseline |
| `.github/workflows/deploy.yml` | V149-6 | The two CI steps |
| `CLAUDE.md`, `docs/claude/code-complexity.md`, `AGENTS.md` | V149-7 | "Measure by hand" becomes "enforced" |

## Parallelisation

- **Group 1 (parallel):** V149-1 (README and its test), the chain V149-2 → V149-3 (gate script and tests), V149-5 (`frontend/` only). Disjoint files, and no task consumes a symbol another introduces.
- **Sequential:**
  - V149-2 before V149-3: V149-3's modes call `measure`, `compare`, `shrink` and the baseline I/O that V149-2 defines, in the same two files.
  - V149-4 after V149-1 and V149-3: it runs `--init`, so the script must exist, and it edits `scripts/dev/select_tests.py` and `tests/dev/test_select_tests.py`, which V149-1 also edits.
  - V149-6 after V149-4 and V149-5: the CI steps run the script against the baseline and run `npm run lint`. Both hunks are in `.github/workflows/deploy.yml`, so they are one task.
  - V149-7 after V149-3 (the docs describe the script's flags). It is one task and one commit (Codex-mirror rule). If a v145 edit to `CLAUDE.md` / `AGENTS.md` is in flight in another session, it lands first and this task rebases onto it.
  - V149-8 last.

---

### Task V149-1: README paths and their test

**Model:** sonnet — a small TDD task; the two-home module names need a docstring check.

**Files:**
- Create: `tests/dev/test_readme_paths.py`
- Modify: `README.md` (the `swingbot/core/`, `swingbot/commands/` and `swingbot/admin/` lists, lines 53-87, and the `HORIZONS` line, 99)
- Modify: `scripts/dev/select_tests.py` (the `DATA_READERS` table)
- Modify: `tests/dev/test_select_tests.py` (`_with_readers`, the parametrised reader test, `test_inert_path_does_not_suppress_a_real_one`)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/dev/test_readme_paths.py` (V149-4 leaves it alone; `select_tests.py` now routes `README.md` to it).

- [ ] **Step 0: Create the worktree**

Invoke the `worktree-lifecycle` skill, then from the main tree:

```bash
git worktree add .claude/worktrees/2026-10-09-v149-hygiene-gates -b 2026-10-09-v149-hygiene-gates main
```

Every later command in this plan runs inside that worktree.

- [ ] **Step 1: Write the failing test**

Create `tests/dev/test_readme_paths.py`:

```python
"""Every `.py` path README.md names must exist (spec v149 H3).

The README's module lists went stale when v27 moved `swingbot/core/` into
packages: it named bare files (`levels.py`) that no longer sat where a reader
would look. Requiring every backticked `.py` token to be a full, existing
repo-relative path is what gives this test teeth. A check that only looked at
tokens starting with `swingbot/` would have passed on the stale README.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]

# A backticked token with no whitespace that ends in `.py`: a path, never a
# command line such as `python bot.py`.
_PY_TOKEN = re.compile(r"`([^`\s]+\.py)`")


def py_tokens(text: str) -> list[str]:
    return sorted(set(_PY_TOKEN.findall(text)))


def missing_paths(text: str, repo: pathlib.Path) -> list[str]:
    def exists(token: str) -> bool:
        if token.startswith("/") or ".." in token.split("/"):
            return False
        return (repo / token).is_file()

    return [token for token in py_tokens(text) if not exists(token)]


def test_a_bare_module_name_is_reported_missing(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "levels.py").write_text("", encoding="utf-8")
    text = "- `levels.py` is stale, `pkg/levels.py` is right, run `python bot.py`"
    assert missing_paths(text, tmp_path) == ["levels.py"]


def test_a_path_outside_the_repo_is_reported_missing(tmp_path):
    assert missing_paths("see `../other/x.py` and `/abs/y.py`", tmp_path) == [
        "../other/x.py", "/abs/y.py"]


def test_every_py_path_the_readme_names_exists():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    missing = missing_paths(text, REPO)
    assert not missing, (
        "README.md names .py paths that do not exist (write the full "
        "repo-relative path):\n  " + "\n  ".join(missing))
```

- [ ] **Step 2: Run it and confirm it fails on today's README**

Run: `python scripts/dev/testrun.py file tests/dev/test_readme_paths.py`
Expected: FAIL, 1 failed and 2 passed. `test_every_py_path_the_readme_names_exists` lists 24 distinct tokens, among them `levels.py`, `scanning.py`, `scanning/engine.py` and `app.py`.

- [ ] **Step 3: Fix the README**

Replace the leading token of each bullet as in the tables. Change only the backticked path; leave each bullet's description alone, with the two exceptions noted.

`swingbot/core/` list (`README.md:53-75`):

| Line | Old token | New token |
|---|---|---|
| 54 | `levels.py` | `swingbot/core/market/levels.py` |
| 55 | `trendlines.py` | `swingbot/core/market/trendlines.py` |
| 55 | `levels.py` (inside the description) | `swingbot/core/market/levels.py` |
| 56 | `volatility.py` | `swingbot/core/market/volatility.py` |
| 57 | `candlestick_patterns.py` | `swingbot/core/market/candlestick_patterns.py` |
| 58 | `strategy.py` | `swingbot/core/market/strategy.py` |
| 59 | `indicators.py` | `swingbot/core/market/indicators.py` |
| 60 | `confidence.py` | `swingbot/core/scanning/confidence.py` |
| 61 | `performance.py` | `swingbot/core/tracking/performance.py` |
| 62 | `risk_metrics.py` | `swingbot/core/tracking/risk_metrics.py` |
| 63 | `backtest.py` | `swingbot/core/backtesting/backtest.py` |
| 64 | `account.py` | `swingbot/core/planning/account.py` |
| 65 | `events.py` | `swingbot/core/market/events.py` |
| 66 | `market_events.py` | `swingbot/core/market/market_events.py` |
| 67 | `regime.py` | `swingbot/core/scanning/regime.py` |
| 68 | `explain.py` | `swingbot/core/market/explain.py` |
| 69 | `export_data.py` | `swingbot/core/marketdata/export_data.py` |
| 70 | `trade_chart.py` | `swingbot/core/charts/trade_chart.py` |
| 71 | `data_store.py` | `swingbot/core/marketdata/data_store.py` |
| 72 | `ticker_utils.py` | `swingbot/core/marketdata/ticker_utils.py` |
| 73 | `data.py` | `swingbot/core/marketdata/data.py` |
| 74 | `watchlist.py` / `state.py` | `swingbot/core/marketdata/watchlist.py` / `swingbot/core/infra/state.py` |
| 75 | `scanning/engine.py` | `swingbot/core/scanning/engine.py` |

Five names have two homes (`indicators`, `watchlist`, `account`, `events`, `risk_metrics`). Before writing each, open the chosen module's docstring and confirm it matches the bullet's description:

```bash
for f in swingbot/core/market/indicators.py swingbot/core/marketdata/watchlist.py \
         swingbot/core/planning/account.py swingbot/core/market/events.py \
         swingbot/core/tracking/risk_metrics.py; do echo "== $f"; sed -n 1,8p "$f"; done
```

If a docstring contradicts its bullet, stop and report it; do not pick the other home on a guess.

Change the heading line 53 from `**`swingbot/core/` (no Discord dependency):**` to:

```markdown
**`swingbot/core/` (no Discord dependency; the full package map is in [`docs/claude/architecture.md`](docs/claude/architecture.md)):**
```

`swingbot/commands/` list (`README.md:77-84`):

| Line | Old token | New token |
|---|---|---|
| 78 | `scanning.py` | `swingbot/commands/scanning/commands.py` |
| 79 | `watchlist.py` | `swingbot/commands/watchlist.py` |
| 80 | `info.py` | `swingbot/commands/info.py` |
| 81 | `trades.py` | `swingbot/commands/trades.py` |
| 82 | `backtest.py` | `swingbot/commands/backtest.py` |
| 83 | `account.py` | `swingbot/commands/account.py` |
| 84 | `data.py` | `swingbot/commands/data.py` |

`swingbot/admin/` (`README.md:87`): `app.py` → `swingbot/admin/app.py`. Leave the rest of that paragraph as it is (it still describes the deleted Jinja pages; the spec lists that under "Facts found" and does not fix it here).

`README.md:99`: `swingbot/core/market/strategy.py` → `swingbot/core/market/strategy_types.py` on the `HORIZONS` line only.

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python scripts/dev/testrun.py file tests/dev/test_readme_paths.py`
Expected: `VERDICT: PASS`, 3 passed.

- [ ] **Step 5: Route `README.md` to the new test in `select_tests.py`**

In `scripts/dev/select_tests.py`, add this row to `DATA_READERS`, directly after the `("CLAUDE.md", ("tests/hooks/",)),` row:

```python
    # Every `.py` path the README names must exist (v149 H3).
    ("README.md", ("tests/dev/test_readme_paths.py",)),
```

In `tests/dev/test_select_tests.py`:

1. In `_with_readers`, add `"tests/dev/test_readme_paths.py"` to the tuple of files it creates:

```python
    for rel in ("tests/hooks/test_guardrails.py", "tests/hooks/test_codex_mirror.py",
                "tests/hooks/test_role_skills.py",
                "tests/dev/test_testrun_ci_invocations.py",
                "tests/dev/test_readme_paths.py"):
```

2. Add one row to the parameter list of `test_data_read_path_routes_to_its_readers`, after the `("AGENTS.md", ["tests/hooks/"]),` row:

```python
    ("README.md", ["tests/dev/test_readme_paths.py"]),
```

3. `README.md` is no longer inert, so `test_inert_path_does_not_suppress_a_real_one` switches its inert example:

```python
def test_inert_path_does_not_suppress_a_real_one(sel, tmp_path):
    result = sel.select(
        ["docs/guides/setup.md", "tests/planning/test_plan_engine.py"], _repo(tmp_path)
    )
    assert (result.full, result.targets) == (False, ["tests/planning/test_plan_engine.py"])
```

- [ ] **Step 6: Run the selector tests**

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: `VERDICT: PASS`. `test_no_path_a_test_reads_is_classified_inert` runs against the real repo and passes because `README.md` now routes to a test that exists on disk.

- [ ] **Step 7: Commit**

```bash
git add tests/dev/test_readme_paths.py README.md
git commit -m "docs(v149): README names every module by its full path, with a test that each exists"
git add scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "test(v149): route README.md to test_readme_paths in the change-aware selector"
```

---

### Task V149-2: Complexity gate core — measure, compare, shrink, baseline I/O

**Model:** sonnet — a normal TDD task in one new module with the behaviour fixed by the spec.

**Files:**
- Create: `scripts/dev/complexity_gate.py`
- Create: `tests/dev/test_complexity_gate.py`
- Modify: `requirements.txt` (after the `pyflakes==3.4.0` line)

**Interfaces:**
- Consumes: nothing.
- Produces (V149-3 and V149-4 rely on these exact names):
  - `THRESHOLD = 15`, `REPO: pathlib.Path`, `BASELINE: pathlib.Path`
  - `class GateError(Exception)`, `class GitUnavailable(Exception)`
  - `@dataclass(frozen=True) class Finding: kind: str; key: str; old: int | None; new: int | None`
  - `python_files(repo: pathlib.Path) -> list[str]` (raises `GitUnavailable`)
  - `measure(repo: pathlib.Path, paths: list[str]) -> dict[str, int]` (raises `GateError`)
  - `load_baseline(path: pathlib.Path) -> dict[str, int]` (raises `GateError`)
  - `write_baseline(path: pathlib.Path, scores: dict[str, int]) -> None`
  - `compare(current: dict[str, int], baseline: dict[str, int]) -> list[Finding]`
  - `shrink(baseline: dict[str, int], current: dict[str, int]) -> dict[str, int]`

- [ ] **Step 1: Add the dependency and install it**

In `requirements.txt`, directly under `pyflakes==3.4.0`:

```
# Cyclomatic-complexity ratchet: scripts/dev/complexity_gate.py.
radon==6.0.1
```

Run: `python -m pip install radon==6.0.1 && python -m radon --version`
Expected: `6.0.1`.

- [ ] **Step 2: Write the failing tests**

Create `tests/dev/test_complexity_gate.py`:

```python
"""The complexity ratchet (spec v149 H1): scripts/dev/complexity_gate.py."""
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location(
        "complexity_gate_mod", REPO / "scripts/dev/complexity_gate.py")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: a frozen dataclass under `from __future__ import
    # annotations` resolves its own module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fn(name: str, score: int, indent: str = "") -> str:
    """Source of a function scoring exactly `score` (one `if` per point above 1)."""
    lines = [f"{indent}def {name}(x):"]
    lines += [f"{indent}    if x == {i}:\n{indent}        return {i}" for i in range(score - 1)]
    lines.append(f"{indent}    return -1")
    return "\n".join(lines) + "\n"


def _repo(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A git repo whose tracked files are exactly `files`."""
    for rel, source in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


# -- files scanned ----------------------------------------------------------

def test_python_files_are_tracked_and_in_scope(gate, tmp_path):
    repo = _repo(tmp_path, {
        "bot.py": "", "admin_ui.py": "", "setup.py": "",
        "swingbot/core/a.py": "", "scripts/dev/b.py": "", "tests/test_c.py": "",
        ".claude/hooks/guardrails.py": "", "swingbot/notes.md": "",
    })
    (repo / "swingbot/untracked.py").write_text("", encoding="utf-8")
    assert gate.python_files(repo) == [
        "admin_ui.py", "bot.py", "scripts/dev/b.py", "swingbot/core/a.py",
        "tests/test_c.py"]


def test_python_files_without_git_raise(gate, tmp_path):
    with pytest.raises(gate.GitUnavailable):
        gate.python_files(tmp_path)


# -- keying -----------------------------------------------------------------

def test_measure_keys_functions_methods_and_closures(gate, tmp_path):
    source = (
        _fn("plain", 15)
        + "class View:\n" + _fn("on_timeout", 16, indent="    ")
        + "def outer(x):\n" + _fn("inner", 17, indent="    ") + "    return inner(x)\n"
        + _fn("small", 14)
    )
    repo = _repo(tmp_path, {"swingbot/commands/views.py": source})
    assert gate.measure(repo, ["swingbot/commands/views.py"]) == {
        "swingbot.commands.views:plain": 15,
        "swingbot.commands.views:View.on_timeout": 16,
        "swingbot.commands.views:outer.inner": 17,
    }


def test_measure_counts_a_closure_nested_two_deep(gate, tmp_path):
    source = ("def outer(x):\n    def middle(y):\n"
              + _fn("innermost", 15, indent="        ")
              + "        return innermost(y)\n    return middle(x)\n")
    repo = _repo(tmp_path, {"scripts/a.py": source})
    assert gate.measure(repo, ["scripts/a.py"]) == {
        "scripts.a:outer.middle.innermost": 15}


def test_key_survives_code_moving_above_the_function(gate, tmp_path):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15)})
    before = gate.measure(repo, ["scripts/a.py"])
    (repo / "scripts/a.py").write_text("\n\nX = 1\n\n" + _fn("main", 15), encoding="utf-8")
    assert gate.measure(repo, ["scripts/a.py"]) == before == {"scripts.a:main": 15}


def test_duplicate_key_fails_naming_both_locations(gate, tmp_path):
    source = "if True:\n" + _fn("main", 15, indent="    ") + "else:\n" + _fn("main", 16, indent="    ")
    repo = _repo(tmp_path, {"scripts/a.py": source})
    with pytest.raises(gate.GateError) as excinfo:
        gate.measure(repo, ["scripts/a.py"])
    message = str(excinfo.value)
    assert "scripts.a:main" in message
    assert "scripts/a.py:2" in message and "scripts/a.py:33" in message


def test_two_blocks_under_the_threshold_may_share_a_name(gate, tmp_path):
    """A property getter and its setter share a fullname; neither is an offender."""
    source = ("class A:\n    @property\n    def v(self):\n        return 1\n"
              "    @v.setter\n    def v(self, x):\n        pass\n")
    repo = _repo(tmp_path, {"scripts/a.py": source})
    assert gate.measure(repo, ["scripts/a.py"]) == {}


def test_unparseable_file_fails_naming_its_path(gate, tmp_path):
    repo = _repo(tmp_path, {"scripts/broken.py": "def f(:\n"})
    with pytest.raises(gate.GateError, match="scripts/broken.py"):
        gate.measure(repo, ["scripts/broken.py"])


def test_a_tracked_file_deleted_from_disk_is_skipped(gate, tmp_path):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15)})
    (repo / "scripts/a.py").unlink()
    assert gate.measure(repo, ["scripts/a.py"]) == {}


# -- compare ----------------------------------------------------------------

def test_compare_sorts_every_difference_into_its_kind(gate):
    baseline = {"m:same": 20, "m:risen": 20, "m:improved": 20, "m:gone": 20}
    current = {"m:same": 20, "m:risen": 21, "m:improved": 16, "m:new": 15}
    F = gate.Finding
    assert gate.compare(current, baseline) == [
        F("gone", "m:gone", 20, None),
        F("improved", "m:improved", 20, 16),
        F("new", "m:new", None, 15),
        F("risen", "m:risen", 20, 21),
    ]


def test_compare_is_empty_when_nothing_moved(gate):
    assert gate.compare({"m:a": 15}, {"m:a": 15}) == []


# -- shrink -----------------------------------------------------------------

def test_shrink_lowers_and_drops_and_never_adds_or_raises(gate):
    baseline = {"m:same": 20, "m:risen": 20, "m:improved": 20, "m:gone": 20}
    current = {"m:same": 20, "m:risen": 21, "m:improved": 16, "m:new": 15}
    assert gate.shrink(baseline, current) == {
        "m:same": 20, "m:risen": 20, "m:improved": 16}


# -- baseline file ----------------------------------------------------------

def test_baseline_round_trips_sorted_with_a_trailing_newline(gate, tmp_path):
    path = tmp_path / "baseline.json"
    gate.write_baseline(path, {"z:f": 30, "a:f": 15})
    assert path.read_bytes() == (
        b'{\n  "functions": {\n    "a:f": 15,\n    "z:f": 30\n  }\n}\n')
    assert gate.load_baseline(path) == {"a:f": 15, "z:f": 30}


@pytest.mark.parametrize("content", [
    None,                                    # missing
    "{not json",                             # unparseable
    json.dumps([1, 2]),                      # not an object
    json.dumps({"functions": []}),           # functions not an object
    json.dumps({"functions": {"a:f": "15"}}),  # score not an integer
    json.dumps({"functions": {"a:f": True}}),  # bool is not a score
    json.dumps({"threshold": 15, "functions": {}}),  # no extra fields
])
def test_bad_baseline_fails_naming_its_path(gate, tmp_path, content):
    path = tmp_path / "baseline.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(gate.GateError, match="baseline.json"):
        gate.load_baseline(path)
```

- [ ] **Step 3: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_complexity_gate.py`
Expected: FAIL (errors): `scripts/dev/complexity_gate.py` does not exist.

- [ ] **Step 4: Write the module**

Create `scripts/dev/complexity_gate.py`:

```python
"""Ratcheting cyclomatic-complexity gate (spec v149 H1).

    python scripts/dev/complexity_gate.py            # check; exit 1 on any finding
    python scripts/dev/complexity_gate.py --update   # lock in gains; never accepts a regression
    python scripts/dev/complexity_gate.py --init     # write the first baseline; refuses if one exists

Every tracked `.py` file under swingbot/, scripts/ and tests/, plus bot.py and
admin_ui.py, is measured with radon. Functions and methods scoring THRESHOLD or
more are compared with `complexity_baseline.json` next to this file, and any
difference fails, in either direction: a baseline left at an old, higher score
would let a function climb back to it unnoticed.

A function is keyed `<dotted module path>:<radon fullname>`, with no line
number, so code moving above it never touches the baseline. Closures are
measured and keyed `module:outer.inner`: radon does not fold a closure's
branches into its parent, so without that walk an inner function would be a
way around the gate.

Known limit, shared with radon's own CLI: methods of a class nested inside
another class are not listed.

Exit codes: 0 pass (or skipped: no git), 1 findings or a gate error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass

from radon.complexity import cc_visit
from radon.visitors import Function

THRESHOLD = 15
REPO = pathlib.Path(__file__).resolve().parents[2]
BASELINE = pathlib.Path(__file__).with_name("complexity_baseline.json")
SCAN_PREFIXES = ("swingbot/", "scripts/", "tests/")
SCAN_FILES = ("bot.py", "admin_ui.py")


class GateError(Exception):
    """The gate cannot give a verdict: bad source, bad baseline, key collision."""


class GitUnavailable(Exception):
    """No git or no .git (the Docker image has neither): the gate skips."""


@dataclass(frozen=True)
class Finding:
    kind: str            # "new" | "risen" | "improved" | "gone"
    key: str
    old: int | None      # baseline score; None for "new"
    new: int | None      # measured score; None for "gone"


@dataclass(frozen=True)
class _Offender:
    key: str
    score: int
    where: str           # "<path>:<line>"


def python_files(repo: pathlib.Path) -> list[str]:
    """Tracked `.py` files in scope, as sorted posix paths.

    Tracked only: concurrent sessions share this tree, and another session's
    half-written module must not fail this one's run.
    """
    if not (repo / ".git").exists():
        raise GitUnavailable(f"no .git in {repo}")
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"], cwd=repo, check=True,
            capture_output=True, text=True, encoding="utf-8").stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitUnavailable(str(exc)) from exc
    paths = (pathlib.PurePosixPath(item).as_posix() for item in listing.split("\0") if item)
    return sorted(p for p in paths if p in SCAN_FILES or p.startswith(SCAN_PREFIXES))


def _module(path: str) -> str:
    return path[:-len(".py")].replace("/", ".")


def _walk(functions, parent: str = ""):
    """Yield (name, score, line) for each function and, recursively, its closures."""
    for function in functions:
        name = f"{parent}.{function.name}" if parent else function.fullname
        yield name, function.complexity, function.lineno
        yield from _walk(function.closures, name)


def _offenders(repo: pathlib.Path, path: str) -> list[_Offender]:
    try:
        source = (repo / path).read_text(encoding="utf-8")
    except FileNotFoundError:      # tracked, deleted on disk, not yet committed
        return []
    try:
        blocks = cc_visit(source)
    except (SyntaxError, ValueError) as exc:
        raise GateError(f"cannot parse {path}: {exc}") from exc
    functions = [block for block in blocks if isinstance(block, Function)]
    module = _module(path)
    return [_Offender(f"{module}:{name}", score, f"{path}:{line}")
            for name, score, line in _walk(functions) if score >= THRESHOLD]


def measure(repo: pathlib.Path, paths: list[str]) -> dict[str, int]:
    """`key -> score` for every function scoring THRESHOLD or more.

    Two offenders sharing a key is a visible failure, never a silent max.
    """
    seen: dict[str, _Offender] = {}
    for path in paths:
        for offender in _offenders(repo, path):
            first = seen.setdefault(offender.key, offender)
            if first is not offender:
                raise GateError(
                    f"key collision: {offender.key} is both {first.where} "
                    f"({first.score}) and {offender.where} ({offender.score}); "
                    "rename one of them")
    return {key: offender.score for key, offender in seen.items()}


def _valid_scores(functions) -> bool:
    return isinstance(functions, dict) and all(
        isinstance(key, str) and type(score) is int for key, score in functions.items())


def load_baseline(path: pathlib.Path) -> dict[str, int]:
    try:
        document = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"baseline missing: {path} (create it with --init)") from exc
    except ValueError as exc:
        raise GateError(f"baseline unparseable: {path}: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"functions"} \
            or not _valid_scores(document["functions"]):
        raise GateError(
            f"baseline malformed: {path} must be exactly "
            '{"functions": {"<key>": <int>, ...}}')
    return dict(document["functions"])


def write_baseline(path: pathlib.Path, scores: dict[str, int]) -> None:
    """Sorted keys, two-space indent, trailing newline: one-line diffs."""
    text = json.dumps({"functions": dict(sorted(scores.items()))}, indent=2) + "\n"
    pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")


def _kind(old: int | None, new: int | None) -> str | None:
    if old is None:
        return "new"
    if new is None:
        return "gone"
    if new > old:
        return "risen"
    return "improved" if new < old else None


def compare(current: dict[str, int], baseline: dict[str, int]) -> list[Finding]:
    """Every difference between the scan and the baseline, sorted by key."""
    findings = []
    for key in sorted(set(current) | set(baseline)):
        old, new = baseline.get(key), current.get(key)
        kind = _kind(old, new)
        if kind:
            findings.append(Finding(kind, key, old, new))
    return findings


def shrink(baseline: dict[str, int], current: dict[str, int]) -> dict[str, int]:
    """The `--update` rule: lower improved scores, drop gone keys, add nothing."""
    return {key: min(score, current[key])
            for key, score in baseline.items() if key in current}
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_complexity_gate.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 6: Check the script's own complexity**

Run: `python -m radon cc -s -n C scripts/dev/complexity_gate.py`
Expected: no output (nothing scores 11 or more).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt
git commit -m "build(v149): pin radon 6.0.1 for the complexity gate"
git add scripts/dev/complexity_gate.py tests/dev/test_complexity_gate.py
git commit -m "feat(v149): complexity gate core -- measure with closures, compare, shrink, baseline I/O"
```

---

### Task V149-3: Complexity gate modes — check, `--update`, `--init`

**Model:** sonnet — TDD inside the module V149-2 created; the refusal rules are fixed by the spec.

**Files:**
- Modify: `scripts/dev/complexity_gate.py` (append below `shrink`)
- Modify: `tests/dev/test_complexity_gate.py` (append)

**Interfaces:**
- Consumes (V149-2): `measure`, `python_files`, `load_baseline`, `write_baseline`, `compare`, `shrink`, `Finding`, `GateError`, `GitUnavailable`, `REPO`, `BASELINE`, `THRESHOLD`.
- Produces:
  - `rename_pairs(findings: list[Finding]) -> list[tuple[str, str]]` — `(gone key, new key)` pairs with equal scores
  - `run_check(repo, baseline_path) -> int`, `run_update(repo, baseline_path) -> int`, `run_init(repo, baseline_path) -> int`
  - `main(argv: list[str] | None = None) -> int`, with `--update`, `--init` (mutually exclusive), `--repo`, `--baseline`
  - stdout: first line `VERDICT: PASS …`, `VERDICT: FAIL  N finding(s)` or `VERDICT: SKIP …`

- [ ] **Step 1: Write the failing tests**

Append to `tests/dev/test_complexity_gate.py`:

```python
# -- modes ------------------------------------------------------------------

def _run(gate, repo, *flags):
    return gate.main([*flags, "--repo", str(repo),
                      "--baseline", str(repo / "baseline.json")])


def _baseline(gate, repo, scores):
    gate.write_baseline(repo / "baseline.json", scores)


def test_check_passes_on_a_tree_that_matches(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15)})
    _baseline(gate, repo, {"scripts.a:main": 15})
    assert _run(gate, repo) == 0
    assert capsys.readouterr().out.startswith("VERDICT: PASS")


@pytest.mark.parametrize("baseline, expected", [
    ({}, "new      scripts.a:main  15"),
    ({"scripts.a:main": 14}, "risen    scripts.a:main  14 -> 15"),
    ({"scripts.a:main": 20}, "improved scripts.a:main  20 -> 15  (run --update)"),
    ({"scripts.a:main": 15, "scripts.a:old": 30},
     "gone     scripts.a:old  30  (run --update)"),
])
def test_check_fails_on_each_kind(gate, tmp_path, capsys, baseline, expected):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15)})
    _baseline(gate, repo, baseline)
    assert _run(gate, repo) == 1
    out = capsys.readouterr().out
    assert out.startswith("VERDICT: FAIL  1 finding(s)")
    assert expected in out


def test_check_prints_at_most_twenty_findings(gate, tmp_path, capsys):
    source = "".join(_fn(f"f{i:02d}", 15) for i in range(25))
    repo = _repo(tmp_path, {"scripts/a.py": source})
    _baseline(gate, repo, {})
    assert _run(gate, repo) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "VERDICT: FAIL  25 finding(s)"
    assert len([line for line in lines if line.startswith("new ")]) == 20
    assert "... and 5 more" in lines


def test_check_hints_at_a_move_or_rename(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/b.py": _fn("main", 15)})
    _baseline(gate, repo, {"scripts.a:main": 15})
    assert _run(gate, repo) == 1
    assert ("hint: scripts.a:main -> scripts.b:main looks like a move or rename "
            "(score 15)") in capsys.readouterr().out


def test_check_fails_on_a_missing_baseline(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/a.py": ""})
    assert _run(gate, repo) == 1
    assert "baseline.json" in capsys.readouterr().out


def test_check_fails_on_an_unparseable_source_file(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/broken.py": "def f(:\n"})
    _baseline(gate, repo, {})
    assert _run(gate, repo) == 1
    assert "scripts/broken.py" in capsys.readouterr().out


def test_check_skips_without_git(gate, tmp_path, capsys):
    assert _run(gate, tmp_path) == 0
    assert capsys.readouterr().out.startswith("VERDICT: SKIP")


def test_update_locks_in_a_gain(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15)})
    _baseline(gate, repo, {"scripts.a:main": 20, "scripts.a:old": 30})
    assert _run(gate, repo, "--update") == 0
    assert gate.load_baseline(repo / "baseline.json") == {"scripts.a:main": 15}
    assert capsys.readouterr().out.startswith("VERDICT: PASS")


def test_update_writes_the_shrink_but_fails_on_new_or_risen(gate, tmp_path, capsys):
    source = _fn("main", 15) + _fn("fresh", 16) + _fn("worse", 21)
    repo = _repo(tmp_path, {"scripts/a.py": source})
    _baseline(gate, repo, {"scripts.a:main": 20, "scripts.a:worse": 20})
    assert _run(gate, repo, "--update") == 1
    # The gain is locked in; the regressions are neither added nor raised.
    assert gate.load_baseline(repo / "baseline.json") == {
        "scripts.a:main": 15, "scripts.a:worse": 20}
    out = capsys.readouterr().out
    assert "new      scripts.a:fresh  16" in out
    assert "risen    scripts.a:worse  20 -> 21" in out


def test_update_refuses_while_a_rename_pair_exists(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/b.py": _fn("main", 15)})
    _baseline(gate, repo, {"scripts.a:main": 15})
    before = (repo / "baseline.json").read_bytes()
    assert _run(gate, repo, "--update") == 1
    assert (repo / "baseline.json").read_bytes() == before     # nothing written
    assert "hand-edit the baseline key first" in capsys.readouterr().out


def test_init_writes_the_first_baseline(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15) + _fn("small", 3)})
    assert _run(gate, repo, "--init") == 0
    assert gate.load_baseline(repo / "baseline.json") == {"scripts.a:main": 15}


def test_init_refuses_when_the_baseline_exists(gate, tmp_path, capsys):
    repo = _repo(tmp_path, {"scripts/a.py": _fn("main", 15)})
    _baseline(gate, repo, {})
    assert _run(gate, repo, "--init") == 1
    assert gate.load_baseline(repo / "baseline.json") == {}
    assert "already exists" in capsys.readouterr().out


def test_rename_pairs_match_by_score_one_to_one(gate):
    F = gate.Finding
    findings = [F("gone", "a:f", 15, None), F("gone", "a:g", 15, None),
                F("new", "b:f", None, 15), F("new", "b:h", None, 22),
                F("risen", "c:f", 15, 16)]
    assert gate.rename_pairs(findings) == [("a:f", "b:f")]
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_complexity_gate.py`
Expected: FAIL: `AttributeError: module 'complexity_gate_mod' has no attribute 'main'` (and `rename_pairs`).

- [ ] **Step 3: Append the modes to `scripts/dev/complexity_gate.py`**

```python
MAX_LINES = 20


def rename_pairs(findings: list[Finding]) -> list[tuple[str, str]]:
    """(`gone` key, `new` key) pairs with equal scores: a likely move or rename.

    One-to-one, in key order. A `gone` key with no equal-score `new` key is
    simply gone.
    """
    unclaimed = [f for f in findings if f.kind == "new"]
    pairs = []
    for gone in (f for f in findings if f.kind == "gone"):
        match = next((new for new in unclaimed if new.new == gone.old), None)
        if match:
            unclaimed.remove(match)
            pairs.append((gone.key, match.key))
    return pairs


_FORMATS = {
    "new": "new      {key}  {new}",
    "risen": "risen    {key}  {old} -> {new}",
    "improved": "improved {key}  {old} -> {new}  (run --update)",
    "gone": "gone     {key}  {old}  (run --update)",
}


def _report(findings: list[Finding]) -> None:
    print(f"VERDICT: FAIL  {len(findings)} finding(s)")
    for finding in findings[:MAX_LINES]:
        print(_FORMATS[finding.kind].format(
            key=finding.key, old=finding.old, new=finding.new))
    if len(findings) > MAX_LINES:
        print(f"... and {len(findings) - MAX_LINES} more")
    scores = {f.key: f.old for f in findings if f.kind == "gone"}
    for gone, new in rename_pairs(findings):
        print(f"hint: {gone} -> {new} looks like a move or rename "
              f"(score {scores[gone]}): hand-edit the baseline key first, "
              "then run --update")


def _scan(repo: pathlib.Path) -> dict[str, int]:
    return measure(repo, python_files(repo))


def run_check(repo: pathlib.Path, baseline_path: pathlib.Path) -> int:
    current = _scan(repo)          # first: without git the gate skips, baseline or not
    baseline = load_baseline(baseline_path)
    findings = compare(current, baseline)
    if findings:
        _report(findings)
        return 1
    print(f"VERDICT: PASS  {len(baseline)} legacy function(s) at {THRESHOLD}+, "
          "none new, risen, improved or gone")
    return 0


def run_update(repo: pathlib.Path, baseline_path: pathlib.Path) -> int:
    """Shrink the baseline. Never adds a key, never raises a score."""
    current = _scan(repo)
    baseline = load_baseline(baseline_path)
    findings = compare(current, baseline)
    if rename_pairs(findings):
        _report(findings)
        print("refused: hand-edit the baseline key first; nothing was written")
        return 1
    write_baseline(baseline_path, shrink(baseline, current))
    blocking = [f for f in findings if f.kind in ("new", "risen")]
    if blocking:
        _report(blocking)
        return 1
    locked = len(findings)
    print(f"VERDICT: PASS  baseline updated, {locked} gain(s) locked in")
    return 0


def run_init(repo: pathlib.Path, baseline_path: pathlib.Path) -> int:
    if baseline_path.exists():
        print(f"VERDICT: FAIL  {baseline_path} already exists; --init never "
              "overwrites a baseline")
        return 1
    current = _scan(repo)
    write_baseline(baseline_path, current)
    print(f"VERDICT: PASS  baseline created with {len(current)} function(s) "
          f"at {THRESHOLD}+")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true",
                      help="lower improved scores and drop gone keys")
    mode.add_argument("--init", action="store_true",
                      help="write the first baseline; refuses if one exists")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    parser.add_argument("--baseline", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args(argv)
    run = run_init if args.init else run_update if args.update else run_check
    try:
        return run(args.repo, args.baseline)
    except GitUnavailable as exc:
        print(f"VERDICT: SKIP  git unavailable, nothing measured: {exc}")
        return 0
    except GateError as exc:
        print(f"VERDICT: FAIL  {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_complexity_gate.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Check the script's own complexity**

Run: `python -m radon cc -s -n C scripts/dev/complexity_gate.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/dev/complexity_gate.py tests/dev/test_complexity_gate.py
git commit -m "feat(v149): complexity gate modes -- check, shrink-only --update, one-shot --init, rename hint"
```

---

### Task V149-4: Generate the baseline and gate the real tree

**Model:** sonnet — mostly mechanical, but a key collision or an unparseable file on the real tree needs a judgement call to stop.

**Files:**
- Create: `scripts/dev/complexity_baseline.json` (generated, never hand-written)
- Modify: `tests/dev/test_complexity_gate.py` (append the slow test)
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`)
- Modify: `tests/dev/test_select_tests.py` (`_with_readers`, the parametrised reader test)

**Interfaces:**
- Consumes (V149-3): `python scripts/dev/complexity_gate.py --init`, `main`, `measure`, `python_files`, `compare`, `load_baseline`, `REPO`, `BASELINE`. (V149-1): the `README.md` row already in `DATA_READERS`.
- Produces: `scripts/dev/complexity_baseline.json`, which V149-6's CI step reads.

- [ ] **Step 1: Confirm the worktree is clean and holds V149-1 and V149-3**

```bash
git status --short
git log --oneline main..HEAD
```

Expected: no uncommitted changes; the commits of V149-1, V149-2 and V149-3 are listed. The baseline must be generated from a committed tree.

- [ ] **Step 2: Generate the baseline**

Run: `python scripts/dev/complexity_gate.py --init`
Expected: `VERDICT: PASS  baseline created with <N> function(s) at 15+`. The first run on a cold machine can take about three minutes; a warm run takes about 20 s.

**If it prints `VERDICT: FAIL  key collision …` or `cannot parse …`: stop and report it to the controller.** The spec measured zero collisions before closures were keyed; a collision now is a real finding the partner decides (rename one function, in its own commit), not something to work around in the script.

- [ ] **Step 3: Record the measured starting point**

```bash
python - <<'EOF'
import json, collections
scores = json.load(open("scripts/dev/complexity_baseline.json"))["functions"]
bands = collections.Counter(
    "15-19" if s < 20 else "20-29" if s < 30 else "30+" for s in scores.values())
roots = collections.Counter(k.split(":")[0].split(".")[0] for k in scores)
print(len(scores), dict(bands), dict(roots))
for key, score in sorted(scores.items(), key=lambda kv: -kv[1])[:5]:
    print(score, key)
EOF
```

Paste the output into the commit message body of Step 7. The spec measured 123 offenders without closures; a different count here is expected and is the number of record.

- [ ] **Step 4: Add the whole-tree test**

Append to `tests/dev/test_complexity_gate.py` (add `import os` to the imports at the top):

```python
# -- the real tree ----------------------------------------------------------

@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("CI")),
    reason="CI runs the gate as its own named step in backend-test-misc")
def test_committed_tree_matches_the_baseline(gate):
    """~20 s warm, so `slow`: `testrun.py full` runs it, `fast` does not.

    A failure here means a function crossed 15, rose, improved or went away.
    Run `python scripts/dev/complexity_gate.py` for the list.
    """
    current = gate.measure(gate.REPO, gate.python_files(gate.REPO))
    assert gate.compare(current, gate.load_baseline(gate.BASELINE)) == []
```

- [ ] **Step 5: Route the baseline file in `select_tests.py`**

In `scripts/dev/select_tests.py`, add to `DATA_READERS`, directly after the `("README.md", …)` row V149-1 added:

```python
    # The complexity ratchet's baseline is compared against the real tree.
    ("scripts/dev/complexity_baseline.json", ("tests/dev/test_complexity_gate.py",)),
```

In `tests/dev/test_select_tests.py`, add `"tests/dev/test_complexity_gate.py"` to the tuple in `_with_readers`:

```python
    for rel in ("tests/hooks/test_guardrails.py", "tests/hooks/test_codex_mirror.py",
                "tests/hooks/test_role_skills.py",
                "tests/dev/test_testrun_ci_invocations.py",
                "tests/dev/test_readme_paths.py",
                "tests/dev/test_complexity_gate.py"):
```

and one row to the parameter list of `test_data_read_path_routes_to_its_readers`, after the `README.md` row:

```python
    ("scripts/dev/complexity_baseline.json", ["tests/dev/test_complexity_gate.py"]),
```

- [ ] **Step 6: Run both test files and the gate**

```bash
python scripts/dev/testrun.py file tests/dev/test_complexity_gate.py
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
python scripts/dev/complexity_gate.py
```

Expected: both `VERDICT: PASS` (the gate file includes the slow test when run by path), and the gate prints `VERDICT: PASS  <N> legacy function(s) at 15+, none new, risen, improved or gone`.

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/complexity_baseline.json tests/dev/test_complexity_gate.py
git commit -m "feat(v149): freeze today's complexity offenders as the gate's baseline" \
  -m "<paste the Step 3 output here>"
git add scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "test(v149): route complexity_baseline.json to the gate test in the selector"
```

---

### Task V149-5: ESLint for the frontend, with today's violations frozen

**Model:** sonnet — tool setup with three behaviours to verify and one documented fallback to choose between.

**Files:**
- Create: `frontend/eslint.config.js` (generated by the schematic, then edited)
- Create: `frontend/eslint-suppressions.json` (generated by `eslint --suppress-all`)
- Modify: `frontend/package.json` (dev dependencies, the `lint` script)
- Modify: `frontend/package-lock.json`
- Modify: `frontend/angular.json` (the schematic adds a `lint` architect target)

**Interfaces:**
- Consumes: nothing.
- Produces: `npm run lint` (run from `frontend/`), exit 0 on the committed tree. V149-6's CI step runs it.

All commands in this task run from `frontend/` inside the worktree.

- [ ] **Step 1: Install dependencies and run the schematic**

```bash
cd frontend
npm ci
npx ng add angular-eslint@21 --skip-confirmation
npx eslint --version
```

Expected: `eslint.config.js` exists, `package.json` gained `eslint`, `angular-eslint` and `typescript-eslint` under `devDependencies`, `angular.json` gained a `lint` target, and the ESLint version is 9.24 or newer. Record the three resolved versions in this task's report.

If `ng add` resolves a major that does not match `@angular/core ~21.2.21`, remove what it added (`git checkout -- . && git clean -fd -- .`, from `frontend/`) and rerun with the exact matching major named.

- [ ] **Step 2: Set the config**

Edit the generated `eslint.config.js` so its content is equivalent to the block below. Keep the module format the schematic chose (`require` or `import`); change only what differs:

```js
// @ts-check
const eslint = require("@eslint/js");
const { defineConfig } = require("eslint/config");
const tseslint = require("typescript-eslint");
const angular = require("angular-eslint");

module.exports = defineConfig([
  {
    files: ["**/*.ts"],
    extends: [
      eslint.configs.recommended,
      tseslint.configs.recommended,
      angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      "@angular-eslint/directive-selector": [
        "error",
        { type: "attribute", prefix: "sb", style: "camelCase" },
      ],
      "@angular-eslint/component-selector": [
        "error",
        { type: "element", prefix: "sb", style: "kebab-case" },
      ],
    },
  },
  {
    files: ["**/*.html"],
    extends: [
      angular.configs.templateRecommended,
      angular.configs.templateAccessibility,
    ],
    rules: {},
  },
]);
```

Three points differ from what the schematic writes:

1. The selector prefix is `sb` (the project prefix, `angular.json:15`), not `app`.
2. If the schematic added `tseslint.configs.stylistic`, remove it. Stylistic rules are out of scope.
3. No `ignores` block is needed: the script lints `src` only.

- [ ] **Step 3: Add the script**

In `frontend/package.json`, add to `"scripts"`:

```json
    "lint": "eslint src"
```

It calls the ESLint CLI directly, not `ng lint`: the suppressions file is a CLI feature and the builder is not known to honour it.

- [ ] **Step 4: Freeze today's violations**

```bash
npx eslint src --suppress-all
npm run lint; echo "exit=$?"
```

Expected: `eslint-suppressions.json` is created in `frontend/`, and `npm run lint` prints `exit=0`. Record the number of suppressed violations per rule in this task's report:

```bash
node -e "const s=require('./eslint-suppressions.json');const t={};for(const f of Object.values(s))for(const [r,v] of Object.entries(f))t[r]=(t[r]||0)+v.count;console.table(t)"
```

- [ ] **Step 5: Verify the three behaviours the spec asks for, and record each answer**

(a) **Bulk suppressions are supported.** Step 4 creating the file answers it. If `--suppress-all` is an unknown option, go to Step 6 (fallback).

(b) **A new violation fails the run.** Append one line to a file that has no suppression entry, run lint, then revert:

```bash
echo "var __lintProbe = 1;" >> src/main.ts
npm run lint; echo "exit=$?"
git checkout -- src/main.ts
```

Expected: `exit=1`, naming `no-var` (or `@typescript-eslint/no-unused-vars`) in `src/main.ts`.

(c) **A fixed but unpruned suppression.** Pick one file and rule from `eslint-suppressions.json`, fix exactly one instance by hand, run lint, record the exit code and message, then revert the fix:

```bash
npm run lint; echo "exit=$?"
git checkout -- src
```

Record whether it exits non-zero with an "unused suppressions" message (expected: exit 2) or passes. Either answer is acceptable. If it passes, the lock-in-the-gain rule (`eslint --prune-suppressions` in the same commit as the fix) is enforced by review only, and the report says so.

- [ ] **Step 6: Fallback, only if (a) failed**

Skip this step when Step 4 worked. Otherwise set every rule that reported in Step 4 to `"warn"` in `eslint.config.js`, count the warnings (`npx eslint src -f json | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>console.log(JSON.parse(d).reduce((n,f)=>n+f.warningCount,0)))"`), set the script to `"lint": "eslint src --max-warnings <that count>"`, and report the downgrade so the controller records it in the spec's `Status:` line.

- [ ] **Step 7: Confirm lint is green and the build is untouched**

```bash
npm run lint; echo "exit=$?"
npm run build
```

Expected: `exit=0`, and the production build succeeds (the new dev dependencies must not change the build).

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend/package.json frontend/package-lock.json frontend/angular.json frontend/eslint.config.js
git commit -m "build(v149): add angular-eslint to the frontend with npm run lint"
git add frontend/eslint-suppressions.json
git commit -m "chore(v149): freeze today's frontend lint violations as bulk suppressions"
```

---

### Task V149-6: The two CI steps

**Model:** haiku — two fixed YAML insertions; the diff is given by this brief.

**Files:**
- Modify: `.github/workflows/deploy.yml` (`backend-test-misc` job, after "Compile every module"; `frontend-test` job, between "Install" and "Unit tests")

**Interfaces:**
- Consumes: (V149-4) `scripts/dev/complexity_gate.py` and its baseline; (V149-5) `npm run lint`.
- Produces: two named CI steps.

- [ ] **Step 1: Add the complexity step**

In the `backend-test-misc` job, between the `Compile every module` step and the `Test suite (db/scripts/hooks/dev)` step:

```yaml
      # The ratchet: fails on any function that crossed 15, rose, improved or
      # went away since scripts/dev/complexity_baseline.json. A named step so a
      # regression shows up as what it is. `--update` only shrinks the baseline.
      - name: Complexity gate
        run: python scripts/dev/complexity_gate.py
```

Confirm the job is the right one: the step after it runs `tests/db/ tests/scripts/ tests/hooks/ tests/dev/`.

- [ ] **Step 2: Add the lint step**

In the `frontend-test` job, between the `Install` step (`npm ci`) and the `Unit tests` step:

```yaml
      # Seconds, and it fails before the slower test run and build. Today's
      # violations are frozen in frontend/eslint-suppressions.json.
      - name: Lint
        run: npm run lint
```

- [ ] **Step 3: Run the test that parses this workflow**

Run: `python scripts/dev/testrun.py file tests/dev/test_testrun_ci_invocations.py`
Expected: `VERDICT: PASS` (it parses every `testrun.py` command line in the workflow; neither new step is one).

- [ ] **Step 4: Check the YAML parses and both jobs gate the deploy**

```bash
python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/deploy.yml',encoding='utf-8')); j=d['jobs']; print([s.get('name') for s in j['backend-test-misc']['steps']]); print([s.get('name') for s in j['frontend-test']['steps']]); print(j['container-healthcheck']['needs'])"
```

Expected: `Complexity gate` sits directly after `Compile every module`; `Lint` sits between `Install` and `Unit tests`; `needs` lists both `backend-test-misc` and `frontend-test`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci(v149): run the complexity gate and the frontend lint as named steps"
```

---

### Task V149-7: Docs and their Codex mirror

**Model:** sonnet — doc edits, but the `AGENTS.md` condensation is by hand and one sentence must be re-verified against radon before it is rewritten.

**Files (one commit):**
- Modify: `CLAUDE.md` (§ "Keep every function under complexity 15")
- Modify: `docs/claude/code-complexity.md` (§ Measuring, § Legacy functions already at 15 or more, one line under the audit table)
- Modify: `AGENTS.md` (§ "Function complexity limit")

**Interfaces:**
- Consumes: (V149-3) the script's flags and verdict names.
- Produces: nothing a later task reads.

- [ ] **Step 1: Re-verify the closure statement against radon 6.0.1**

```bash
cat > v149_closure_probe.py <<'EOF'
def outer(x):
    def inner(y):
        if y:
            return 1
        if y > 2:
            return 2
        return 3
    return inner(x)
EOF
python - <<'EOF'
from radon.complexity import cc_visit
for block in cc_visit(open("v149_closure_probe.py").read()):
    print(block.fullname, block.complexity, [(c.name, c.complexity) for c in block.closures])
EOF
python -m radon cc -s v149_closure_probe.py
rm v149_closure_probe.py
```

Expected: the first command prints `outer 1 [('inner', 3)]` (the parent's score does not include the closure's branches), and the CLI lists `outer` only. If the output differs, write what it actually shows in Step 3 and report the difference.

- [ ] **Step 2: Edit `CLAUDE.md`**

Find the section with `grep -n "Keep every function under complexity 15" CLAUDE.md`. Replace its four body lines with these four:

```markdown
Every function and method you write or change ends at cyclomatic complexity
**< 15**, enforced by `scripts/dev/complexity_gate.py` against
`complexity_baseline.json` (`testrun.py full` and CI; `--update` only shrinks it):
split into named helpers, return early. A legacy function already >= 15 never gets worse. A refactor never changes behaviour. Detail: `code-complexity.md`.
```

Run: `wc -l CLAUDE.md`
Expected: unchanged from before the edit, and under 200.

- [ ] **Step 3: Edit `docs/claude/code-complexity.md`**

(a) Replace the whole `## Measuring` section (from the heading to the line before `## Getting under the limit`) with:

````markdown
## Measuring

The limit is enforced by `scripts/dev/complexity_gate.py`. radon is pinned in
`requirements.txt`, so it is installed with everything else.

```bash
python scripts/dev/complexity_gate.py             # the gate: every tracked .py file against the baseline
python -m radon cc -s -n C <files you touched>    # while iterating: every block scoring 11+, with its number
```

The gate compares every function scoring 15 or more with
`scripts/dev/complexity_baseline.json` and fails on any difference:

| Verdict | Meaning | What to do |
|---|---|---|
| `new` | a function at 15 or more that is not in the baseline | split it |
| `risen` | a baseline function scores higher than recorded | move the new logic into a helper |
| `improved` | a baseline function scores lower, still 15 or more | `--update`, same commit |
| `gone` | a baseline function is now under 15 or no longer exists | `--update`, same commit |

`improved` and `gone` fail on purpose: a baseline left at the old score would
let the function climb back to it unnoticed. **`--update` only shrinks the
baseline.** It never adds a key and never raises a score, so it cannot accept
a regression.

It runs in `python scripts/dev/testrun.py full` (a `slow` test,
`tests/dev/test_complexity_gate.py`) and as the "Complexity gate" step in CI,
where a red result blocks the production deploy. A hotfix that lowers a
legacy function's score runs `--update` in the same commit.

**Moving or renaming a legacy function** shows up as a `gone` key plus a
`new` key with the same score, and the gate prints a hint naming the pair.
Hand-edit the key in the baseline first, then run `--update`; it refuses
while such a pair exists. The diff is one renamed key with an unchanged
score, which review confirms.

**Closures count on their own.** radon does not add a closure's branches to
its parent's score, and `radon cc` on the command line does not list
closures at all. The gate walks them and keys each as `module:outer.inner`,
so wrapping branches in an inner function is not a way under the limit.
Comprehensions are counted in the function that contains them.
````

If Step 1's output contradicted the closure paragraph, write what Step 1 showed instead.

(b) In `## Legacy functions already at 15 or more`, add this as the section's first paragraph:

```markdown
`scripts/dev/complexity_baseline.json` is the record of which functions are
legacy and at what score. A function not in it has no allowance.
```

(c) The audit table under `## Why this repo needs it` quotes 108 for `_sync_run_scan`. Leave the table as the dated 2026-09-24 audit it is, and add one line directly under it:

```markdown
Current scores are in `scripts/dev/complexity_baseline.json`; this table is the 2026-09-24 audit.
```

- [ ] **Step 4: Edit `AGENTS.md`**

Find the section with `grep -n "^## Function complexity limit" -A 6 AGENTS.md`. Replace its first paragraph (the four lines from "Every function and method" to "holds for urgent fixes too.") with:

```markdown
Every function and method you write or change ends at cyclomatic complexity
**below 15**. It is enforced by `python scripts/dev/complexity_gate.py` against
`scripts/dev/complexity_baseline.json`, in `testrun.py full` and in CI (radon is
pinned in `requirements.txt`); use `python -m radon cc -s -n C <files>` while
iterating. The gate fails on `new`, `risen`, `improved` and `gone`; run
`--update` in the same commit for the last two. `--update` only shrinks the
baseline, and closures are measured on their own. It covers `swingbot/`,
`bot.py`, `admin_ui.py`, `scripts/` and `tests/`, and holds for urgent fixes too.
```

Leave the three bullets and the `Detail:` line under it unchanged.

- [ ] **Step 5: Run the mirror and hook tests**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: `VERDICT: PASS`. `test_codex_mirror.py` checks coverage, not meaning, so a pass does not prove the condensation is faithful: reread the `AGENTS.md` paragraph against the `CLAUDE.md` one.

- [ ] **Step 6: Commit (one commit, Codex-mirror rule)**

```bash
git add CLAUDE.md docs/claude/code-complexity.md AGENTS.md
git commit -m "docs(v149): the complexity limit is enforced by the gate, not measured by hand"
```

---

### Task V149-8: Full-suite verification

**Model:** sonnet — runs the gates once and fixes forward from whatever they name.

**Files:** none edited unless a run names a regression.

- [ ] **Step 1: Confirm every task landed**

```bash
git log --oneline main..HEAD
grep -o '^### Task V149-[0-9]*' docs/superpowers/plans/2026-10-09-v149-hygiene-gates.md | tr '\n' ' '
```

Expected: the commits of V149-1 .. V149-7, and task ids V149-1 .. V149-8.

- [ ] **Step 2: Run the complexity gate on the final tree**

Run: `python scripts/dev/complexity_gate.py`
Expected: `VERDICT: PASS`. If a task after V149-4 lowered or removed an offender, run `--update` and commit the one-line diff. A `new` or `risen` finding is this plan's regression: split the function.

- [ ] **Step 3: Run the Python suite once**

Dispatch the `test-runner` agent (worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v149-hygiene-gates`) with `python scripts/dev/testrun.py full`.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 4: Run the frontend gates once**

```bash
cd frontend && npm run lint && npx ng test --watch=false
```

Expected: lint exits 0; the Vitest run reports no failures. This plan changed no frontend source, so a failure here is from the new dev dependencies and is this plan's to fix.

- [ ] **Step 5: Fix forward**

If any run is red, fix from the failures it names and rerun only that run. The task is done when all three are green.

- [ ] **Step 6: Hand back to the controller**

Report: the baseline's function count, the ESLint versions and suppressed-violation counts, and the answer to V149-5 Step 5 (c). The controller then:

1. runs `/panel staff-engineer,senior-engineer` over `main...2026-10-09-v149-hygiene-gates`;
2. merges and runs `/close-out` (`Bump: none`, so no `VERSION.json` change);
3. after the first push to `main`, reads the duration of the "Complexity gate" step in the `backend-test-misc` job (`gh run view --log` or the Actions page) and records it in the spec's `Status:` line. The spec measured 176 s cold locally; the CI figure is the number of record.
