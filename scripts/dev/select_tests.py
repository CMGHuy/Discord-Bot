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
    """Run a NUL-separated (-z) git listing. Newline output is not safe:
    core.quotePath wraps non-ASCII names in quotes, and a quoted '.py"' name
    would silently drop out of the graph."""
    out = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, timeout=30,
    )
    if out.returncode != 0:
        stderr = out.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    text = out.stdout.decode("utf-8", errors="surrogateescape")
    return [item.replace("\\", "/") for item in text.split("\0") if item]


def repo_python_files(repo: pathlib.Path) -> list[str]:
    """Tracked AND untracked .py, repo-relative, worktrees excluded.

    Untracked is not optional: a brand-new source file is exactly the case
    where you most want its new test selected, and a tracked-only listing
    would leave it out of the graph entirely.
    """
    paths = _git(repo, "ls-files", "-z", "*.py")
    paths += _git(repo, "ls-files", "-z", "--others", "--exclude-standard", "*.py")
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


def _from_import_names(node: ast.ImportFrom, package: str) -> set[str]:
    """Names one `from ... import ...` contributes (relative levels resolved)."""
    prefix = ""
    if node.level:
        parts = package.split(".") if package else []
        drop = node.level - 1
        parts = parts[: len(parts) - drop] if drop else parts
        prefix = ".".join(parts)
    base = ".".join(part for part in (prefix, node.module or "") if part)
    names = {base} if base else set()
    for alias in node.names:
        names.add(".".join(part for part in (base, alias.name) if part))
    return names


def _imported_names(tree: ast.AST, package: str) -> set[str]:
    """Absolute dotted names this AST imports.

    `from x import y` contributes BOTH 'x' and 'x.y', because y may be a
    submodule or an ordinary symbol and only the file map can tell which.
    Whichever does not resolve to a repo file is dropped as third-party.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names |= _from_import_names(node, package)
    return names


def _parse(repo: pathlib.Path, rel: str) -> ast.AST | None:
    """Parse one file. None when it is gone from disk (tracked but deleted):
    it imports nothing now, yet stays a resolution target so its importers
    keep their edge. Anything else unreadable or unparseable must widen."""
    path = repo / rel
    if not path.exists() and not path.is_symlink():
        return None
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source)
    # RecursionError / MemoryError: pathologically nested source blows the
    # parser's stack. Still "could not parse", so still widen.
    except (SyntaxError, ValueError, OSError, RecursionError, MemoryError) as exc:
        raise UnparseableFile(rel) from exc


def _with_ancestor_packages(name: str, by_module: dict[str, str]) -> set[str]:
    """Files executed by importing `name`: itself plus every ancestor
    package's __init__.py that exists in the repo."""
    parts = name.split(".")
    found: set[str] = set()
    for end in range(1, len(parts) + 1):
        target = by_module.get(".".join(parts[:end]))
        if target is not None and (end == len(parts) or target.endswith("__init__.py")):
            found.add(target)
    return found


def _suffix_index(by_module: dict[str, str]) -> dict[str, set[str]]:
    """Every dotted suffix of every module -> the files it could name.

    'scripts.backtest.validate_component' is indexed under
    'validate_component', 'backtest.validate_component' and itself.
    """
    index: dict[str, set[str]] = {}
    for module, rel in by_module.items():
        parts = module.split(".")
        for start in range(len(parts)):
            index.setdefault(".".join(parts[start:]), set()).add(rel)
    return index


def _by_suffix(name: str, suffixes: dict[str, set[str]]) -> set[str]:
    """Fallback for a name no dotted module matches -- typically a bare
    `import validate_component` after sys.path.insert(0, 'scripts/backtest').
    The static graph cannot know sys.path, so link to EVERY repo file the
    name could mean. Over-approximation only widens; a stdlib/third-party
    name that collides with a repo basename just adds a spurious edge."""
    parts = name.split(".")
    found: set[str] = set()
    for end in range(1, len(parts) + 1):
        for target in suffixes.get(".".join(parts[:end]), ()):
            if end == len(parts) or target.endswith("__init__.py"):
                found.add(target)
    return found


def build_import_graph(repo: pathlib.Path) -> dict[str, set[str]]:
    """file -> set of files that import it (reverse edges, direct only).

    Importing a.b.c also executes a/__init__.py and a/b/__init__.py, so those
    get edges too. A name that resolves to no dotted module falls back to
    every file whose module name ends with it (_by_suffix). Raises
    UnparseableFile, which every caller must turn into a full run.
    """
    files = repo_python_files(repo)
    by_module = {_module_name(rel): rel for rel in files}
    suffixes = _suffix_index(by_module)
    reverse: dict[str, set[str]] = {rel: set() for rel in files}

    for rel in files:
        tree = _parse(repo, rel)
        if tree is None:
            continue
        for name in _imported_names(tree, _package_of(rel)):
            targets = (_with_ancestor_packages(name, by_module)
                       or _by_suffix(name, suffixes))
            for target in targets - {rel}:
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

# Non-Python files that tests READ as data (open/read_text/json.load/glob),
# which an import graph cannot see. Checked BEFORE the inert rule: partner
# decision 2026-09-29 -- the widening rule beats the inert allowlist. A key
# ending in '/' is a prefix; any other key is an exact path. A target missing
# on disk widens. tests/dev/test_select_tests.py::
# test_no_path_a_test_reads_is_classified_inert fails when a test starts
# naming a data file this table (or the inert rule) mis-routes.
DATA_READERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Skill/agent/settings shape and the Codex mirror: test_skill_shape,
    # test_agent_shape, test_codex_mirror (directly and via sync_codex.py),
    # test_guardrails.
    (".claude/", ("tests/hooks/",)),
    ("CLAUDE.md", ("tests/hooks/",)),
    # Codex mirror outputs, compared against a fresh render by test_codex_mirror.
    ("AGENTS.md", ("tests/hooks/",)),
    (".agents/", ("tests/hooks/",)),
    (".codex/", ("tests/hooks/",)),
    # backtest-methodology.md's closed table (test_guardrails); every
    # reference doc must be named in AGENTS.md (sync_codex via test_codex_mirror);
    # skills-tools.md's roles table pins each reviewer model (test_role_skills).
    ("docs/claude/", ("tests/hooks/test_guardrails.py",
                      "tests/hooks/test_codex_mirror.py",
                      "tests/hooks/test_role_skills.py")),
    # The backup runbook is parsed for the commands it documents.
    ("docs/deploy/DEPLOY_HETZNER.md", ("tests/scripts/test_backup_db.py",)),
    # Every testrun.py command line deploy.yml runs is parsed for real.
    (".github/workflows/", ("tests/dev/test_testrun_ci_invocations.py",)),
    # Every spec past v140 must carry a valid **Screen:** header line, and
    # every spec past v145 a valid **Panel:** line.
    ("docs/superpowers/specs/", ("tests/hooks/test_spec_screen_header.py",
                                 "tests/hooks/test_spec_panel_header.py")),
    # Every plan past v145 must stamp **Model:** under each ### Task.
    ("docs/superpowers/plans/", ("tests/hooks/test_plan_model_stamp.py",)),
    # The pre-registration ledger is loaded and validated row by row.
    ("docs/superpowers/results/preregistration-ledger.jsonl",
     ("tests/backtesting/test_preregistration_ledger_file.py",
      "tests/backtesting/test_instrument_stats_ledger.py",
      "tests/scripts/test_preregistration_ledger_cli.py")),
)

# Known to affect no test. Distinct from "unplaceable", which widens: silence
# and ignorance get opposite treatment. Python is checked FIRST and is never
# inert -- .claude/hooks/guardrails.py is tested by tests/hooks/test_guardrails.py.
# Data-read paths (DATA_READERS) are checked before this list.
INERT_PREFIXES = ("docs/", ".superpowers/")
INERT_SUFFIXES = (".md",)

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


def _readers_of(path: str) -> tuple[str, ...]:
    """DATA_READERS targets for a non-Python path, else ()."""
    if _is_python(path):
        return ()
    for key, targets in DATA_READERS:
        if path == key or (key.endswith("/") and path.startswith(key)):
            return targets
    return ()


def _is_inert(path: str) -> bool:
    return path.startswith(INERT_PREFIXES) or path.endswith(INERT_SUFFIXES)


def _data_targets(changed: list[str], repo: pathlib.Path) -> set[str] | str:
    """Reader targets for the data-read paths in `changed`, or a widening
    reason when a reader named in DATA_READERS is gone from disk."""
    targets: set[str] = set()
    for path in changed:
        for target in _readers_of(path):
            if not (repo / target).exists():
                return f"{path} is read by {target}, which does not exist"
            targets.add(target)
    return targets


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


def _widen_for_path(changed: list[str]) -> str | None:
    """Reason to run everything based on paths alone, else None."""
    for prefixes, label in (
        (REGISTRY_PREFIXES, "registry dispatch, invisible to an import graph"),
        (ESCALATE_PREFIXES, "render tier"),
    ):
        hits = [path for path in changed if path.startswith(prefixes)]
        if hits:
            return f"{hits[0]} touched ({label})"
    unplaceable = [p for p in changed
                   if not (_is_python(p) or _readers_of(p) or _is_inert(p))]
    if unplaceable:
        return f"{unplaceable[0]} is not placeable by an import graph"
    return None


def _is_conftest(path: str) -> bool:
    return path.rsplit("/", 1)[-1] == "conftest.py"


def _reach_of(path: str, reverse: dict[str, set[str]],
              repo: pathlib.Path) -> set[str] | str:
    """Targets for one changed source, or a widening reason (str).

    The changed file and every transitive importer are treated alike: a
    conftest among them contributes its whole subtree (fixtures reach tests
    by NAME, not by import), and the root conftest means the whole suite --
    tests/conftest.py re-exports tests/db/conftest.py suite-wide.
    """
    targets: set[str] = set()
    for hit in sorted({path} | importers_of(reverse, path)):
        if _is_conftest(hit):
            subtree = hit[: -len("conftest.py")]
            if subtree in ("tests/", ""):
                return f"{hit} is the root conftest -- its subtree is the suite"
            targets.add(subtree)
        # A deleted test file is no target: pytest errors on a missing path.
        elif _is_test_file(hit) and (hit != path or (repo / path).exists()):
            targets.add(hit)
    return targets


def _targets_for(
    sources: list[str], reverse: dict[str, set[str]], repo: pathlib.Path
) -> set[str] | str:
    """Test targets reaching `sources`, or a widening reason (str)."""
    targets: set[str] = set()
    for path in sources:
        reach = _reach_of(path, reverse, repo)
        if isinstance(reach, str):
            return reach
        if not reach:
            # Per source, not per change set: a reachable second change must
            # not hide one that no test imports.
            return f"no test reaches {path}"
        targets |= reach
    return targets


def _source_targets(sources: list[str], repo: pathlib.Path) -> set[str] | str:
    """Import-graph targets for changed Python, or a widening reason (str)."""
    if not sources:
        return set()  # data-read paths only: no graph to build
    try:
        reverse = build_import_graph(repo)
    except (UnparseableFile, RuntimeError) as exc:
        return str(exc)
    return _targets_for(sources, reverse, repo)


def _threshold_reason(targets: set[str], repo: pathlib.Path) -> str | None:
    """Reason to run everything when the selection covers most of the suite."""
    all_tests = [p for p in repo_python_files(repo) if _is_test_file(p)]
    if not all_tests:
        return None
    share = _covered(targets, all_tests) / len(all_tests)
    if share > FULL_THRESHOLD:
        return (f"{share:.0%} of test files selected -- -n 4 over "
                "everything is cheaper than serial over most of it")
    return None


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

    widen = _widen_for_path(changed)
    if widen:
        return Selection(full=True, changed=changed, reason=widen)
    return _select_placed(changed, repo)


def _collapse(targets: set[str]) -> set[str]:
    """Drop targets already inside a selected directory target ('x/'), so
    pytest is never handed the same file twice."""
    dirs = [t for t in targets if t.endswith("/")]
    return {t for t in targets
            if not any(t != d and t.startswith(d) for d in dirs)}


def _select_placed(changed: list[str], repo: pathlib.Path) -> Selection:
    """select() once every path is known placeable: data-read, Python or inert."""
    targets = _data_targets(changed, repo)
    if isinstance(targets, str):
        return Selection(full=True, changed=changed, reason=targets)

    sources = [path for path in changed if _is_python(path)]
    if not sources and not targets:
        return Selection(changed=changed,
                         reason=f"nothing to test ({len(changed)} inert path(s))")

    found = _source_targets(sources, repo)
    if isinstance(found, str):
        return Selection(full=True, changed=changed, reason=found)
    targets |= found

    too_wide = _threshold_reason(targets, repo)
    if too_wide:
        return Selection(full=True, changed=changed, reason=too_wide)

    placed = len(sources) + sum(1 for path in changed if _readers_of(path))
    targets = _collapse(targets)
    return Selection(
        targets=sorted(targets), changed=changed,
        reason=f"{len(targets)} target(s) from {placed} changed file(s)",
    )
