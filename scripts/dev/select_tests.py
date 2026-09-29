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
    except (SyntaxError, ValueError, OSError) as exc:
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


def build_import_graph(repo: pathlib.Path) -> dict[str, set[str]]:
    """file -> set of files that import it (reverse edges, direct only).

    Importing a.b.c also executes a/__init__.py and a/b/__init__.py, so those
    get edges too. Raises UnparseableFile, which every caller must turn into
    a full run.
    """
    files = repo_python_files(repo)
    by_module = {_module_name(rel): rel for rel in files}
    reverse: dict[str, set[str]] = {rel: set() for rel in files}

    for rel in files:
        tree = _parse(repo, rel)
        if tree is None:
            continue
        for name in _imported_names(tree, _package_of(rel)):
            for target in _with_ancestor_packages(name, by_module):
                if target != rel:
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
