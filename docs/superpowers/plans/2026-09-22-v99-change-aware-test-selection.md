# Change-Aware Test Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-22-v99-change-aware-test-selection-design.md`
**Bump:** none
**Edge:** none (integrity)

**Goal:** Add a `changed` profile to `scripts/dev/testrun.py` that runs only the test files reaching what you actually changed, and widens to the full suite whenever it cannot be sure.

**Architecture:** A new standalone module `scripts/dev/select_tests.py` builds a static import graph over tracked + untracked Python via `ast`, inverts it to a reverse-dependency map, and maps changed paths to test paths. It imports nothing from pytest and nothing from `swingbot`, so it is a pure function of (files on disk, changed paths) and testable against a `tmp_path` fixture tree. `testrun.py` owns the git query and calls into it.

**Tech Stack:** Python 3.11+ stdlib only (`ast`, `dataclasses`, `pathlib`, `subprocess`). No new dependencies. pytest + pytest-mock for the tests.

## Global Constraints

- **Every failure mode widens to the full suite. None narrows.** Unparseable file, unresolvable import, unknown extension, failed git call, zero test coverage for a changed source file — all return `full=True`. A selector bug may cost wall-clock; it may never cost coverage.
- **This plan does not touch the gate.** `/gate`, `.claude/hooks/guardrails.py`, and the plan-final full-suite verification task are out of scope. No task may modify them.
- **`FULL_THRESHOLD = 0.4` is unmeasured and its comment must say so.** Deriving the real serial-vs-`-n 4` crossover needs a cooled idle box (`docs/claude/testing-cost.md` — timings here swing up to 4x under load). Do not quote it as measured, and do not measure it as part of this plan.
- **`select_tests.py` must not import pytest, `swingbot`, or anything from `tests/`.** That purity is what makes it unit-testable.
- **Graph construction uses `git ls-files`, never a filesystem walk.** Four live worktrees sit under `.claude/worktrees/`; a walk would collect a different branch's tests. An explicit exclusion filter backs this up.
- **`CLAUDE.md` must stay under 200 lines.** It is at 199. Task V99-5 specifies a net-zero edit; do not let the Commands block simply grow.
- Python 3.11+ syntax is fine (`X | None`, `match` etc.). Match the surrounding comment density in `scripts/dev/testrun.py`: it explains *why*, not *what*.

---

# Phase A — Selection module

### Task V99-1: Import graph construction

**Files:**
- Create: `scripts/dev/select_tests.py`
- Test: `tests/dev/test_select_tests.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `UnparseableFile(Exception)` with attribute `.path: str`; `repo_python_files(repo: Path) -> list[str]` returning repo-relative POSIX paths; `build_import_graph(repo: Path) -> dict[str, set[str]]` mapping a repo-relative file to the set of repo-relative files that import it (reverse edges); `importers_of(reverse: dict[str, set[str]], start: str) -> set[str]` returning the transitive closure.

- [ ] **Step 1: Write the failing test**

Create `tests/dev/test_select_tests.py`. Note the loader fixture — it matches the existing pattern in `tests/dev/test_testrun_db_preflight.py`, because `scripts/` is not an importable package.

```python
"""Change-aware test selection (v99).

Every case runs against a fixture tree under tmp_path, not the real repo: the
real graph changes every commit and a test pinned to it would drift.
"""
import importlib.util
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sel():
    spec = importlib.util.spec_from_file_location(
        "select_tests_mod", REPO / "scripts/dev/select_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _tree(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """Write a fixture tree and make it a git repo so git ls-files works."""
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def test_direct_import_produces_a_reverse_edge(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "VALUE = 1\n",
        "tests/test_core.py": "from pkg.core import VALUE\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse["pkg/core.py"] == {"tests/test_core.py"}


def test_package_init_import_resolves(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "VALUE = 1\n",
        "tests/test_pkg.py": "from pkg import VALUE\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse["pkg/__init__.py"] == {"tests/test_pkg.py"}


def test_relative_import_resolves_against_its_package(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "VALUE = 1\n",
        "pkg/wrapper.py": "from .core import VALUE\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse["pkg/core.py"] == {"pkg/wrapper.py"}


def test_third_party_import_produces_no_edge_and_no_error(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "import pandas\nimport os\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse == {"pkg/__init__.py": set(), "pkg/core.py": set()}


def test_unparseable_file_raises_with_its_path(sel, tmp_path):
    repo = _tree(tmp_path, {"pkg/broken.py": "def f(:\n"})
    with pytest.raises(sel.UnparseableFile) as caught:
        sel.build_import_graph(repo)
    assert caught.value.path == "pkg/broken.py"


def test_importers_of_is_transitive(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/c.py": "VALUE = 1\n",
        "pkg/b.py": "from pkg.c import VALUE\n",
        "pkg/a.py": "from pkg.b import VALUE\n",
        "tests/test_a.py": "from pkg.a import VALUE\n",
    })
    reverse = sel.build_import_graph(repo)
    assert sel.importers_of(reverse, "pkg/c.py") == {
        "pkg/b.py", "pkg/a.py", "tests/test_a.py",
    }


def test_untracked_python_is_still_a_graph_node(sel, tmp_path):
    """A brand-new source file must be visible, or its tests are missed."""
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "tests/test_new.py": "from pkg.brand_new import VALUE\n",
    })
    (repo / "pkg/brand_new.py").write_text("VALUE = 1\n", encoding="utf-8")
    reverse = sel.build_import_graph(repo)
    assert reverse["pkg/brand_new.py"] == {"tests/test_new.py"}


def test_worktree_copies_are_excluded(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "VALUE = 1\n",
        ".claude/worktrees/other/tests/test_core.py": "from pkg.core import VALUE\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse["pkg/core.py"] == set()
    assert not any(p.startswith(".claude/worktrees/") for p in reverse)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/dev/test_select_tests.py -v
```

Expected: collection error — `select_tests.py` does not exist, so
`spec_from_file_location` returns a spec whose loader cannot find the file.

- [ ] **Step 3: Write the implementation**

Create `scripts/dev/select_tests.py`:

```python
"""Change-aware test selection (plan v99, Task V99-1/V99-2).

Maps the files you changed to the test files that reach them, so the inner
loop runs ~12 files instead of ~392. It does this with a static import graph
rather than a hand-written directory map (which under-selects on this repo's
cross-package imports) or a coverage index (a dependency plus a state file
that goes stale silently).

THE INVARIANT: every failure mode widens to the full suite. None narrows.
An unparseable file, an unplaceable extension, a failed git call and a source
file no test imports all return full=True. A bug here may cost wall-clock; it
may not cost coverage. This is the same "fail safe, not fast" rule that
testrun.should_escalate() already follows.

This module imports nothing from pytest, nothing from swingbot and nothing
from tests/. That purity is what lets tests/dev/test_select_tests.py drive it
against a throwaway fixture tree.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess

# Worktrees are full repo copies of OTHER branches: collecting them would build
# a graph over the wrong code. market_data/ and data/ hold no source but can
# hold generated .py. pytest.ini's norecursedirs makes the same exclusions for
# the same reason.
EXCLUDED_DIRS = (
    ".claude/worktrees/",
    "market_data/",
    "data/",
    "logs/",
)


class UnparseableFile(Exception):
    """A tracked .py file that ast could not parse. Callers must widen."""

    def __init__(self, path: str):
        super().__init__(f"{path} does not parse")
        self.path = path


def _git(repo: pathlib.Path, *args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return [line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()]


def repo_python_files(repo: pathlib.Path) -> list[str]:
    """Tracked AND untracked .py, repo-relative, worktrees excluded.

    Untracked is not optional: a brand-new source file is exactly the case
    where you most want its new test selected, and a tracked-only listing
    would leave it out of the graph entirely.
    """
    paths = _git(repo, "ls-files", "*.py")
    paths += _git(repo, "ls-files", "--others", "--exclude-standard", "*.py")
    seen: dict[str, None] = {}
    for path in paths:
        if path.startswith(EXCLUDED_DIRS):
            continue
        seen[path] = None
    return sorted(seen)


def _module_name(rel: str) -> str:
    """'a/b/c.py' -> 'a.b.c'; 'a/b/__init__.py' -> 'a.b'."""
    parts = rel[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_of(rel: str) -> str:
    """The dotted package a file lives in ('' at the repo root)."""
    return ".".join(rel.split("/")[:-1])


def _imported_names(tree: ast.AST, package: str) -> set[str]:
    """Absolute dotted names this AST imports.

    `from x import y` contributes BOTH 'x' and 'x.y', because y may be a
    submodule or an ordinary symbol and only the file map can tell which.
    Whichever does not resolve to a repo file is dropped as third-party.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".") if package else []
                drop = node.level - 1
                parts = parts[: len(parts) - drop] if drop else parts
                prefix = ".".join(parts)
            else:
                prefix = ""
            base = ".".join(part for part in (prefix, node.module or "") if part)
            if base:
                names.add(base)
            for alias in node.names:
                names.add(".".join(part for part in (base, alias.name) if part))
    return names


def build_import_graph(repo: pathlib.Path) -> dict[str, set[str]]:
    """file -> set of files that import it (reverse edges, direct only).

    Raises UnparseableFile, which every caller must turn into a full run.
    """
    files = repo_python_files(repo)
    by_module = {_module_name(rel): rel for rel in files}
    reverse: dict[str, set[str]] = {rel: set() for rel in files}

    for rel in files:
        source = (repo / rel).read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise UnparseableFile(rel) from exc
        for name in _imported_names(tree, _package_of(rel)):
            target = by_module.get(name)
            if target is not None and target != rel:
                reverse[target].add(rel)
    return reverse


def importers_of(reverse: dict[str, set[str]], start: str) -> set[str]:
    """Transitive closure of importers. Cycle-safe."""
    seen: set[str] = set()
    stack = [start]
    while stack:
        for importer in reverse.get(stack.pop(), ()):
            if importer not in seen:
                seen.add(importer)
                stack.append(importer)
    return seen
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/dev/test_select_tests.py -v
```

Expected: 8 passed.

If `test_worktree_copies_are_excluded` fails, check that the fixture's
`git add -A` actually tracked the `.claude/` path — `_tree` writes no
`.gitignore`, so it should. The exclusion must come from `EXCLUDED_DIRS`,
not from git.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "feat(v99): build a reverse import graph over repo Python

Tracked and untracked .py both become graph nodes -- a brand-new source file
is exactly the case where you most want its new test selected. Worktree
copies are excluded by an explicit filter, not by luck: they are full repo
copies of other branches.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task V99-2: The selection algorithm

**Files:**
- Modify: `scripts/dev/select_tests.py` (append; do not alter Task V99-1's functions)
- Test: `tests/dev/test_select_tests.py` (append)

**Interfaces:**
- Consumes: `build_import_graph`, `importers_of`, `repo_python_files`, `UnparseableFile` from Task V99-1.
- Produces: `Selection` frozen dataclass with fields `targets: list[str]`, `full: bool`, `reason: str`, `changed: list[str]`; `select(changed: list[str] | None, repo: Path) -> Selection`; module constants `ESCALATE_PREFIXES`, `REGISTRY_PREFIXES`, `INERT_PREFIXES`, `INERT_SUFFIXES`, `FULL_THRESHOLD`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/dev/test_select_tests.py`:

```python
def _repo(tmp_path):
    """A fixture tree shaped like this repo.

    ELEVEN test files on purpose. FULL_THRESHOLD is 0.4, so a fixture with
    four would make the threshold fire on selections these tests expect to be
    narrow -- the test would then pass or fail for a reason it is not about.
    `hub.py` exists to be the one module that DOES trip the threshold, since
    the obvious real hub (config.py) is in REGISTRY_PREFIXES and widens one
    rule earlier.
    """
    unrelated = "from swingbot.core.unrelated import NOOP\n"
    return _tree(tmp_path, {
        "swingbot/__init__.py": "",
        "swingbot/config.py": "SETTING = 1\n",
        "swingbot/core/__init__.py": "",
        "swingbot/core/hub.py": "SHARED = 1\n",
        "swingbot/core/unrelated.py": "NOOP = 0\n",
        "swingbot/core/planning/__init__.py": "",
        "swingbot/core/planning/plan_engine.py": "VALUE = 1\n",
        "swingbot/core/scanning/__init__.py": "",
        "swingbot/core/scanning/engine.py": "from swingbot.core.planning.plan_engine import VALUE\n",
        "swingbot/core/edge/__init__.py": "",
        "swingbot/core/edge/rsi.py": "NAME = 'rsi'\n",
        "swingbot/core/charts/__init__.py": "",
        "swingbot/core/charts/render.py": "DPI = 110\n",
        "tests/__init__.py": "",
        "tests/conftest.py": "",
        "tests/planning/__init__.py": "",
        "tests/planning/test_plan_engine.py": "from swingbot.core.planning.plan_engine import VALUE\n",
        "tests/scanning/__init__.py": "",
        "tests/scanning/conftest.py": "",
        "tests/scanning/test_engine.py": "from swingbot.core.scanning.engine import VALUE\n",
        "tests/scanning/test_extra.py": "from swingbot.core.scanning.engine import VALUE\n",
        "tests/test_config.py": "from swingbot.config import SETTING\n",
        # Five importers of the hub: changing hub.py selects 5 of 11 test
        # files (45%), over the 0.4 threshold. Every other case here selects
        # at most 3 of 11 (27%) and stays narrow.
        "tests/test_hub_a.py": "from swingbot.core.hub import SHARED\n",
        "tests/test_hub_b.py": "from swingbot.core.hub import SHARED\n",
        "tests/test_hub_c.py": "from swingbot.core.hub import SHARED\n",
        "tests/test_hub_d.py": "from swingbot.core.hub import SHARED\n",
        "tests/test_hub_e.py": "from swingbot.core.hub import SHARED\n",
        "tests/test_filler_a.py": unrelated,
        "tests/test_filler_b.py": unrelated,
    })


def test_git_unavailable_widens(sel, tmp_path):
    result = sel.select(None, _repo(tmp_path))
    assert result.full is True
    assert "git unavailable" in result.reason


def test_nothing_changed_runs_nothing(sel, tmp_path):
    result = sel.select([], _repo(tmp_path))
    assert (result.full, result.targets) == (False, [])
    assert "nothing changed" in result.reason


def test_source_change_selects_transitively(sel, tmp_path):
    """plan_engine is imported by scanning/engine, so scanning's tests count."""
    result = sel.select(["swingbot/core/planning/plan_engine.py"], _repo(tmp_path))
    assert result.full is False
    assert set(result.targets) == {
        "tests/planning/test_plan_engine.py",
        "tests/scanning/test_engine.py",
        "tests/scanning/test_extra.py",
    }


def test_changed_test_file_selects_itself(sel, tmp_path):
    result = sel.select(["tests/planning/test_plan_engine.py"], _repo(tmp_path))
    assert (result.full, result.targets) == (False, ["tests/planning/test_plan_engine.py"])


def test_changed_conftest_selects_its_subtree(sel, tmp_path):
    result = sel.select(["tests/scanning/conftest.py"], _repo(tmp_path))
    assert (result.full, result.targets) == (False, ["tests/scanning/"])


def test_root_conftest_widens(sel, tmp_path):
    """tests/conftest.py's subtree IS the suite; say so rather than pretend."""
    result = sel.select(["tests/conftest.py"], _repo(tmp_path))
    assert result.full is True


def test_registry_prefix_widens(sel, tmp_path):
    result = sel.select(["swingbot/core/edge/rsi.py"], _repo(tmp_path))
    assert result.full is True
    assert "swingbot/core/edge/rsi.py" in result.reason


def test_escalate_prefix_widens(sel, tmp_path):
    result = sel.select(["swingbot/core/charts/render.py"], _repo(tmp_path))
    assert result.full is True
    assert "swingbot/core/charts/render.py" in result.reason


def test_unplaceable_extension_widens(sel, tmp_path):
    result = sel.select(["frontend/src/styles/theme.css"], _repo(tmp_path))
    assert result.full is True
    assert "theme.css" in result.reason


def test_inert_path_alone_runs_nothing(sel, tmp_path):
    result = sel.select(["docs/claude/testing-cost.md"], _repo(tmp_path))
    assert (result.full, result.targets) == (False, [])
    assert "inert" in result.reason


def test_inert_path_does_not_suppress_a_real_one(sel, tmp_path):
    result = sel.select(
        ["README.md", "tests/planning/test_plan_engine.py"], _repo(tmp_path)
    )
    assert (result.full, result.targets) == (False, ["tests/planning/test_plan_engine.py"])


def test_python_is_never_inert(sel, tmp_path):
    """.claude/hooks/guardrails.py is Python under an otherwise-inert prefix."""
    repo = _repo(tmp_path)
    (repo / ".claude/hooks").mkdir(parents=True, exist_ok=True)
    (repo / ".claude/hooks/guardrails.py").write_text("RULES = []\n", encoding="utf-8")
    result = sel.select([".claude/hooks/guardrails.py"], repo)
    assert result.full is True          # no test imports it -> widen, never skip
    assert "no test reaches" in result.reason


def test_unparseable_file_widens_and_names_it(sel, tmp_path):
    repo = _repo(tmp_path)
    (repo / "swingbot/core/planning/plan_engine.py").write_text("def f(:\n", encoding="utf-8")
    result = sel.select(["swingbot/core/planning/plan_engine.py"], repo)
    assert result.full is True
    assert "plan_engine.py" in result.reason


def test_threshold_widens(sel, tmp_path):
    """hub.py reaches 5 of 11 test files (45%), over the 0.4 threshold.

    Note this must NOT use config.py: it is in REGISTRY_PREFIXES and widens
    one rule earlier, so the reason would name registry dispatch and this
    test would pass without ever exercising the threshold.
    """
    result = sel.select(["swingbot/core/hub.py"], _repo(tmp_path))
    assert result.full is True
    assert "%" in result.reason and "cheaper" in result.reason


def test_narrow_selection_stays_under_the_threshold(sel, tmp_path):
    """The other side of the same boundary: 3 of 11 must not widen."""
    result = sel.select(["swingbot/core/planning/plan_engine.py"], _repo(tmp_path))
    assert result.full is False


def test_selection_is_sorted_and_deterministic(sel, tmp_path):
    repo = _repo(tmp_path)
    first = sel.select(["swingbot/core/scanning/engine.py"], repo)
    second = sel.select(["swingbot/core/scanning/engine.py"], repo)
    assert first.targets == second.targets == sorted(first.targets)


def test_real_repo_smoke(sel):
    """Against the live repo: must not raise, and config.py must widen.

    Deliberately not a fixed expected set -- that would need editing on every
    unrelated commit.
    """
    result = sel.select(["swingbot/config.py"], REPO)
    assert isinstance(result.reason, str) and result.reason
    assert result.full is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/dev/test_select_tests.py -v -k "not graph and not import"
```

Expected: `AttributeError: module 'select_tests_mod' has no attribute 'select'`.

- [ ] **Step 3: Write the implementation**

Append to `scripts/dev/select_tests.py`:

```python
# --- selection ---------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402  (grouped with its users)

# Moved here from testrun.py so both the fast tier and the changed tier read
# one list. Editing any of these can break a test that only runs in the slow
# tier. Tiering is a speed optimisation; it must not become a way to miss a
# regression.
ESCALATE_PREFIXES = (
    "swingbot/core/charts/",
    "frontend/src/styles/tokens.css",
)

# Reached by NAME, not by import -- a static graph structurally cannot see the
# edge, so these widen unconditionally. Each entry needs its reason, because a
# future reader's first instinct will be to delete it as over-cautious.
REGISTRY_PREFIXES = (
    # Strategy modules dispatched through the registry by name.
    "swingbot/core/edge/",
    # HORIZONS and strategy identity, consumed by name across the scan pipeline.
    "swingbot/core/market/strategy_types.py",
    # .env-driven schema read by attribute across the tree. Also a hub that
    # would select nearly everything anyway, so widening costs little.
    "swingbot/config.py",
)

# Known to affect no test. Distinct from "unplaceable", which widens: silence
# and ignorance get opposite treatment. Python is checked FIRST and is never
# inert -- .claude/hooks/guardrails.py lives under an inert prefix and is
# tested by tests/hooks/test_guardrails.py.
INERT_PREFIXES = ("docs/", ".claude/", ".superpowers/", ".github/")
INERT_SUFFIXES = (".md", ".txt")

# UNMEASURED. The serial-vs-`-n 4` crossover has not been derived: it needs a
# cooled idle box, and docs/claude/testing-cost.md records timings on this
# machine swinging up to 4x under load. 0.4 is a placeholder that is honest
# about being one. Do not quote it as measured.
FULL_THRESHOLD = 0.4


@dataclass(frozen=True)
class Selection:
    """What to run, and -- always -- why.

    full=True means the caller must run the whole suite instead of `targets`.
    `reason` is never empty: an unexplained selection is an unauditable one.
    """

    targets: list[str] = field(default_factory=list)
    full: bool = False
    reason: str = ""
    changed: list[str] = field(default_factory=list)


def _is_python(path: str) -> bool:
    return path.endswith(".py")


def _is_inert(path: str) -> bool:
    return path.startswith(INERT_PREFIXES) or path.endswith(INERT_SUFFIXES)


def _is_test_file(path: str) -> bool:
    return (
        path.startswith("tests/")
        and path.endswith(".py")
        and path.rsplit("/", 1)[-1].startswith("test_")
    )


def _covered(targets: set[str], all_tests: list[str]) -> int:
    """How many test files a target set resolves to (dir targets end in '/')."""
    return sum(
        1 for test in all_tests
        if any(test == target or test.startswith(target) for target in targets)
    )


def select(changed: list[str] | None, repo: pathlib.Path) -> Selection:
    """Map changed paths to test paths. Widens to full on any uncertainty.

    `changed=None` means the caller's git query failed. The caller owns that
    query (testrun.changed_paths) so this module stays a pure function of
    (files on disk, changed paths).

    Rules are evaluated in order; the first match decides.
    """
    if changed is None:
        return Selection(full=True, reason="git unavailable")

    changed = sorted({path.strip().replace("\\", "/") for path in changed if path.strip()})
    if not changed:
        return Selection(reason="nothing changed")

    for prefixes, label in (
        (REGISTRY_PREFIXES, "registry dispatch, invisible to an import graph"),
        (ESCALATE_PREFIXES, "render tier"),
    ):
        hits = [path for path in changed if path.startswith(prefixes)]
        if hits:
            return Selection(full=True, changed=changed,
                             reason=f"{hits[0]} touched ({label})")

    unplaceable = [p for p in changed if not _is_python(p) and not _is_inert(p)]
    if unplaceable:
        return Selection(full=True, changed=changed,
                         reason=f"{unplaceable[0]} is not placeable by an import graph")

    sources = [path for path in changed if _is_python(path)]
    if not sources:
        return Selection(changed=changed,
                         reason=f"nothing to test ({len(changed)} inert path(s))")

    try:
        reverse = build_import_graph(repo)
    except (UnparseableFile, RuntimeError) as exc:
        return Selection(full=True, changed=changed, reason=str(exc))

    targets: set[str] = set()
    for path in sources:
        if path.endswith("conftest.py"):
            subtree = path[: -len("conftest.py")]
            if subtree in ("tests/", ""):
                return Selection(full=True, changed=changed,
                                 reason=f"{path} is the root conftest -- its subtree is the suite")
            targets.add(subtree)
            continue
        if _is_test_file(path):
            targets.add(path)
        targets |= {p for p in importers_of(reverse, path) if _is_test_file(p)}

    if not targets:
        return Selection(full=True, changed=changed,
                         reason=f"no test reaches {sources[0]}")

    all_tests = [p for p in repo_python_files(repo) if _is_test_file(p)]
    if all_tests:
        share = _covered(targets, all_tests) / len(all_tests)
        if share > FULL_THRESHOLD:
            return Selection(full=True, changed=changed,
                             reason=f"{share:.0%} of test files selected -- -n 4 over "
                                    "everything is cheaper than serial over most of it")

    return Selection(
        targets=sorted(targets), changed=changed,
        reason=f"{len(targets)} target(s) from {len(sources)} changed file(s)",
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/dev/test_select_tests.py -v
```

Expected: 25 passed (8 from Task V99-1, 17 from this task).

Two failures worth predicting. If `test_python_is_never_inert` reports
`full is False`, the `_is_python` check is running after `_is_inert` — Python
must be tested first. If `test_source_change_selects_transitively` returns
only `tests/planning/test_plan_engine.py`, `importers_of` is returning direct
edges rather than the closure.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "feat(v99): map changed paths to test paths, widening on doubt

Rules run in order and the first match decides. Registry and render prefixes
widen unconditionally; an unplaceable extension widens; an inert path selects
nothing. Silence and ignorance get opposite treatment on purpose -- a .md is
known to affect no test, a .css is one the graph has no opinion about.

FULL_THRESHOLD ships unmeasured and its comment says so.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# Phase B — Runner and docs

**Both tasks in this phase depend on Phase A and on nothing else.** See
`## Parallelisation`.

### Task V99-3: Wire the `changed` profile into testrun.py

**Files:**
- Modify: `scripts/dev/testrun.py` (imports at top; `ESCALATE_PREFIXES` block at lines 55-66; `build_args`; `main`)
- Test: `tests/dev/test_testrun_changed_profile.py`

**Interfaces:**
- Consumes: `Selection`, `select`, `ESCALATE_PREFIXES` from Task V99-2.
- Produces: `testrun.py` accepting `changed` as a `profile` choice and `--dry-run` as a flag; `resolve_changed(args) -> Selection | None` returning `None` when the caller should fall through to the `full` path.

- [ ] **Step 1: Write the failing test**

Create `tests/dev/test_testrun_changed_profile.py`:

```python
"""The `changed` profile wires selection into the runner (v99, Task V99-3)."""
import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def testrun():
    spec = importlib.util.spec_from_file_location("testrun_mod", REPO / "scripts/dev/testrun.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_escalate_prefixes_come_from_select_tests(testrun):
    """One list, not two copies that can drift apart."""
    import sys
    sys.path.insert(0, str(REPO / "scripts/dev"))
    import select_tests
    assert testrun.ESCALATE_PREFIXES is select_tests.ESCALATE_PREFIXES


def test_changed_is_an_accepted_profile(testrun):
    parser = testrun.build_parser()
    args = parser.parse_args(["changed"])
    assert args.profile == "changed"
    assert args.dry_run is False


def test_build_args_for_changed_takes_explicit_targets(testrun):
    args = testrun.build_args("changed", None, targets=["tests/planning/", "tests/test_x.py"])
    assert args[-2:] == ["tests/planning/", "tests/test_x.py"]
    assert "-n" not in args, "selected sets are small; xdist startup dominates"


def test_full_selection_falls_through_to_the_full_profile(testrun, monkeypatch, capsys):
    from dataclasses import dataclass, field

    @dataclass
    class FakeSelection:
        targets: list = field(default_factory=list)
        full: bool = True
        reason: str = "registry dispatch"
        changed: list = field(default_factory=list)

    monkeypatch.setattr(testrun, "select", lambda *_a, **_k: FakeSelection())
    monkeypatch.setattr(testrun, "changed_paths", lambda: ["swingbot/core/edge/rsi.py"])
    parser = testrun.build_parser()
    resolved = testrun.resolve_changed(parser.parse_args(["changed"]))
    assert resolved is None, "None means: run the full profile"
    assert "registry dispatch" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/dev/test_testrun_changed_profile.py -v
```

Expected: `AttributeError: module 'testrun_mod' has no attribute 'build_parser'`.

- [ ] **Step 3: Write the implementation**

In `scripts/dev/testrun.py`, immediately after the existing
`WORKERS = "4"` line, add the sibling import:

```python
# scripts/dev is sys.path[0] when this is run directly, but NOT when a test
# loads it via spec_from_file_location. Insert explicitly so both work.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from select_tests import ESCALATE_PREFIXES, Selection, select  # noqa: E402
```

**Delete** the existing `ESCALATE_PREFIXES` assignment and its comment block
(lines 55-66, from `# Editing any of these can break` through the closing
`)`). Its comment moved to `select_tests.py` verbatim in Task V99-2 —
`should_escalate()` keeps working against the imported name unchanged.

Replace `build_args` with:

```python
def build_args(profile: str, target: str | None,
               targets: list[str] | None = None) -> list[str]:
    if profile == "fast":
        return BASE + ["-m", "not slow", "tests/"]
    if profile == "full":
        return BASE + ["-n", WORKERS, "tests/"]
    if profile == "lf":
        return BASE + ["--lf", "tests/"]
    if profile == "changed":
        if not targets:
            sys.exit("testrun.py changed: no targets resolved")
        # Serial on purpose: below FULL_THRESHOLD the set is small and xdist's
        # worker startup dominates, the same reason `fast` runs serial.
        return BASE + list(targets)
    if profile == "file":
        if not target:
            sys.exit("testrun.py file <path>: missing path")
        return BASE + [target]
    sys.exit(f"unknown profile: {profile}")
```

Add, above `main`:

```python
def resolve_changed(args) -> Selection | None:
    """Print the selection; return it, or None meaning 'run the full profile'.

    --dry-run exits here rather than returning, so a wrong selection is
    visible rather than inferred from a suspiciously fast green run.
    """
    selection = select(changed_paths(), REPO)
    print(f"SELECTION: {selection.reason}")
    if selection.full:
        return None
    for path in selection.targets:
        print(f"  {path}")
    if args.dry_run:
        sys.exit(0)
    return selection
```

Extract the parser so tests can reach it, and wire the profile in `main`:

```python
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profile", choices=["fast", "full", "file", "lf", "changed"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--no-escalate", action="store_true",
                    help="keep `fast` narrow even if chart/token files changed")
    ap.add_argument("--dry-run", action="store_true",
                    help="`changed`: print the selection and exit without running")
    return ap


def main() -> int:
    args = build_parser().parse_args()

    profile = args.profile
    targets: list[str] | None = None

    if profile == "changed":
        selection = resolve_changed(args)
        if selection is None:
            profile = "full"
        elif not selection.targets:
            return 0                      # inert change: nothing to run, and that is a pass
        else:
            targets = selection.targets

    if profile == "fast" and not args.no_escalate:
        escalate, why = should_escalate()
        if escalate:
            print(f"NOTE: {why} -> escalating to full tier")
            profile = "full"

    if profile == "full":
        try:
            findings = undefined_names()
        except RuntimeError as exc:
            print(f"VERDICT: FAIL  {exc}")
            return 1
        if findings:
            print(f"VERDICT: FAIL  {len(findings)} undefined name(s) -- this is the class that caused two production outages")
            for finding in findings[:10]:
                print(f"  {finding}")
            return 1

    warning = db_preflight()
    if warning:
        print(warning, file=sys.stderr, flush=True)

    counts, failed, elapsed, rc = run(build_args(profile, args.target, targets))
    ...
```

Leave everything from `# No parseable counts` onward exactly as it is, with
one change — append the selection to the PASS line:

```python
    if bad == 0 and rc == 0:
        suffix = f"  ({len(targets)} target(s) selected)" if targets else ""
        print(f"VERDICT: PASS  {summary}  in {elapsed:.1f}s{suffix}")
        return 0
```

Finally, add the profile to the module docstring's profile list, after the
`file` line:

```
    python scripts/dev/testrun.py changed          # only tests reaching your diff
    python scripts/dev/testrun.py changed --dry-run  # print the selection, run nothing
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/dev/ -v
```

Expected: all of `test_select_tests.py`, `test_testrun_changed_profile.py`
and the pre-existing `test_testrun_db_preflight.py` pass. The db-preflight
file must still pass — it loads `testrun.py` the same way and the new
`sys.path` insert runs at module exec.

- [ ] **Step 5: Verify it works end to end**

```bash
python scripts/dev/testrun.py changed --dry-run
```

Expected: a `SELECTION:` line naming a real reason. With only this plan's own
files dirty (`scripts/dev/*.py`, `tests/dev/*.py`), the selection should be
the `tests/dev/` files and nothing else. If it prints a full-suite reason,
read the reason before changing anything — a dirty `.md` is inert, but a dirty
`.json` or `.css` correctly widens.

- [ ] **Step 6: Commit**

```bash
git add scripts/dev/testrun.py tests/dev/test_testrun_changed_profile.py
git commit -m "feat(v99): add the changed profile to testrun

ESCALATE_PREFIXES moves to select_tests so the fast tier and the changed tier
read one list rather than two copies that drift. A full selection falls
through to the existing full path, undefined-name gate and all.

--dry-run exists so a wrong selection is visible rather than inferred from a
suspiciously fast green run.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task V99-4: Document the profile

**Files:**
- Modify: `docs/claude/testing-cost.md` (new section, after `## Timings`)
- Modify: `CLAUDE.md:101-105` and `CLAUDE.md:139`
- Modify: `.codex/AGENTS.md:132-136`

**Interfaces:**
- Consumes: the CLI surface from Task V99-3 (`changed`, `--dry-run`). Touches no code.
- Produces: nothing code-level.

- [ ] **Step 1: Add the section to `docs/claude/testing-cost.md`**

Insert immediately before the `## Measuring is fragile — two traps` heading
(currently line 39):

```markdown
## Change-aware selection (`changed`)

`python scripts/dev/testrun.py changed` runs only the test files that reach
what you changed. `--dry-run` prints the selection without running it.

**It is an inner-loop tool and not a gate.** `/gate` and a plan's final
verification task still run everything. That boundary is the safety argument:
a selection bug costs a slow feedback cycle, never a missed regression.

**Every failure mode widens; none narrows.** Unparseable file, unplaceable
extension, failed git call, or a changed source file no test imports — all
run the full suite, and the `SELECTION:` line says which one fired. Read that
line before doubting it.

**What it cannot see:** anything reached by name rather than by import. The
strategy registry under `swingbot/core/edge/` is the standing example, which
is why `REGISTRY_PREFIXES` in `scripts/dev/select_tests.py` widens on it
unconditionally. If you add wiring of that shape, add the prefix — a gap
there is the one kind of miss that matters.

**`FULL_THRESHOLD = 0.4` is unmeasured**, and its comment in the source says
so. The serial-vs-`-n 4` crossover needs a cooled idle box; per the two traps
below, a reading taken while anything else runs is worthless. Deriving it is
open work, not a number to quote.
```

- [ ] **Step 2: Edit `CLAUDE.md` — net zero lines**

`CLAUDE.md` is at **199 lines** and capped at 200. This edit adds one line to
the Commands block and removes one from the token-discipline bullet, landing
back at 199. Verify with `wc -l` in Step 4; do not let the block simply grow.

Replace lines 101-105 (5 lines) with these 4:

```markdown
- **Don't re-run the full suite to check a local change** — use
  `python scripts/dev/testrun.py changed` (diff-selected; widens when unsure)
  or `... file tests/test_foo.py` (~7s). One-line verdict, not ~1150 lines.
  Full runs: dispatch `test-runner`. Plan cadence: "Naming specs and plans".
```

Insert one line into the Commands block, directly after the `fast` line
(currently line 138):

```
python scripts/dev/testrun.py changed          # only tests reaching your diff; widens to full when unsure
```

- [ ] **Step 3: Mirror into `.codex/AGENTS.md`**

Condensed, not copied — the sync is one-way and `.codex/AGENTS.md` is a
mirror, never a source. Add one bullet to the list at lines 132-136, above
the `file` bullet:

```markdown
- `python scripts/dev/testrun.py changed` — runs only the tests reaching your
  diff, and widens to the full suite whenever it cannot be sure (registry
  dispatch, an unplaceable file type, a failed git call). Inner loop only:
  it is not a gate, and the plan-final full run is unchanged. `--dry-run`
  prints the selection without running it.
```

- [ ] **Step 4: Verify the line cap and the cross-references**

```bash
wc -l CLAUDE.md
grep -n "testrun.py changed" CLAUDE.md docs/claude/testing-cost.md .codex/AGENTS.md
```

Expected: `CLAUDE.md` at **199 or fewer**, and a hit in all three files. If
`CLAUDE.md` exceeds 200, the bullet rewrite in Step 2 was not applied — fix
that rather than trimming something unrelated.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/claude/testing-cost.md .codex/AGENTS.md
git commit -m "docs(v99): document the changed profile

Records the three things a future session will need and cannot infer: it is
an inner-loop tool and not a gate, every failure mode widens, and it cannot
see registry dispatch. FULL_THRESHOLD is documented as unmeasured in the one
file this repo keeps measured-not-estimated numbers in.

CLAUDE.md stays at 199 lines -- the Commands line is paid for by condensing
the token-discipline bullet.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

# Phase C — Audit and verification

### Task V99-5: `--audit` mode

**Files:**
- Modify: `scripts/dev/testrun.py` (`build_parser`, `main`)
- Test: `tests/dev/test_testrun_changed_profile.py` (append)

**Interfaces:**
- Consumes: `resolve_changed`, `run`, `build_args` from Task V99-3.
- Produces: `audit_misses(selected_targets: list[str], full_failed: list[str]) -> list[str]` returning the failing node ids no selected target covers.

- [ ] **Step 1: Write the failing test**

Append to `tests/dev/test_testrun_changed_profile.py`:

```python
def test_audit_misses_finds_the_uncovered_failure(testrun):
    misses = testrun.audit_misses(
        ["tests/planning/test_plan_engine.py", "tests/scanning/"],
        [
            "tests/planning/test_plan_engine.py::test_a",
            "tests/scanning/test_engine.py::test_b",
            "tests/market/test_session.py::test_c",
        ],
    )
    assert misses == ["tests/market/test_session.py::test_c"]


def test_audit_misses_is_empty_when_everything_was_selected(testrun):
    assert testrun.audit_misses(
        ["tests/planning/"], ["tests/planning/test_plan_engine.py::test_a"]
    ) == []


def test_audit_is_an_accepted_flag(testrun):
    assert testrun.build_parser().parse_args(["changed", "--audit"]).audit is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/dev/test_testrun_changed_profile.py -v -k audit
```

Expected: `AttributeError: module 'testrun_mod' has no attribute 'audit_misses'`.

- [ ] **Step 3: Write the implementation**

Add to `scripts/dev/testrun.py`, next to `resolve_changed`:

```python
def audit_misses(selected: list[str], full_failed: list[str]) -> list[str]:
    """Failing node ids that the selection would NOT have run.

    This set is the only interesting output of an audit: a regression the
    inner loop would have hidden. Directory targets end in '/', so a prefix
    match is the right test for both shapes.
    """
    return [
        node for node in full_failed
        if not any(node.split("::")[0].startswith(t) or node.split("::")[0] == t
                   for t in selected)
    ]
```

In `build_parser`, add:

```python
    ap.add_argument("--audit", action="store_true",
                    help="`changed`: run the selection, then the full suite, "
                         "and report any failure the selection would have missed")
```

In `main`, after the selected run produces its verdict and before returning,
add the audit leg. Place it immediately before the final `return 0` / `return 1`
block, guarded so it only runs for `changed --audit`:

```python
    if args.profile == "changed" and args.audit:
        print("AUDIT: running the full suite to check the selection...")
        full_counts, full_failed, full_elapsed, _ = run(build_args("full", None))
        misses = audit_misses(targets or [], full_failed)
        if misses:
            print(f"AUDIT: MISS  {len(misses)} failure(s) the selection would not have run:")
            for node in misses[:10]:
                print(f"  {node}")
        else:
            print(f"AUDIT: OK  selection covered every failure  (full: {full_elapsed:.1f}s)")
```

An audit that finds no misses is weak evidence from one run, not proof — say
"covered every failure", never "the selection is safe".

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/dev/test_testrun_changed_profile.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/testrun.py tests/dev/test_testrun_changed_profile.py
git commit -m "feat(v99): add --audit to compare a selection against a full run

Reports only failures the selection would not have run -- the set that
matters, because it is the regression the inner loop would have hidden. Not
routine: it exists to accumulate the evidence a later 'can this gate?'
question would need, which can otherwise only be answered by assertion.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task V99-6: Full-suite verification

- [ ] **Step 1: Run the full suite once, over everything this plan implemented**

Run `python scripts/dev/testrun.py full`, or dispatch the `test-runner`
subagent so none of the output reaches the session context. Expect
`0 failed`, `0 xfailed`. A changed pass count is not a failure
(`docs/claude/testing-cost.md`).

**If it is not green, fix forward from those failures** — they are this
plan's regressions, and the task is not done until the run is. This plan
touches no `frontend/` file, so `npm test` is not required.

- [ ] **Step 2: Verify the new profile against the real repo**

```bash
python scripts/dev/testrun.py changed --dry-run
```

Expected: a `SELECTION:` line with a real reason. With the plan's own files
committed and the tree clean, expect `nothing changed`.

- [ ] **Step 3: Run one audit as the first evidence point**

```bash
python scripts/dev/testrun.py changed --audit
```

Only meaningful with something dirty. If the tree is clean, touch a
whitespace-only change in `swingbot/core/planning/plan_engine.py` first,
run the audit, then revert it. Record the `AUDIT:` line in the close-out
commit message — one data point, stated as one data point.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "test(v99): full-suite verification

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Parallelisation

- **Sequential: V99-1 → V99-2.** V99-2 consumes `build_import_graph`,
  `importers_of`, `repo_python_files` and `UnparseableFile`, and appends to the
  same two files. They cannot overlap.
- **Sequential: V99-2 → Phase B.** Both Phase B tasks depend on the
  `Selection` contract and the `ESCALATE_PREFIXES` move.
- **Group 1 (parallel): V99-3 and V99-4.** Disjoint files —
  `scripts/dev/testrun.py` + `tests/dev/test_testrun_changed_profile.py`
  versus `CLAUDE.md` + `docs/claude/testing-cost.md` + `.codex/AGENTS.md` —
  and neither consumes a symbol the other introduces. V99-4 documents a CLI
  surface this plan has already fixed in writing, so it does not need V99-3 to
  have landed.
- **Sequential: V99-3 → V99-5.** `--audit` extends `main` and `build_parser`
  in the same file V99-3 rewrites, and appends to the same test file.
- **Sequential: everything → V99-6.**

Concurrent sessions share this working tree. Do not dispatch V99-3 and V99-5
together on the strength of them being "both testrun work" — they edit the
same two files, and the second overwrites the first silently.
