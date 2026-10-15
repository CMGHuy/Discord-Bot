"""Test suites -- loader and validator for tests/suites.toml.

Stdlib only: the CI `test-plan` job runs this before any dependency install.
See docs/claude/testing-cost.md "Test suites" for the rule this enforces.
"""
import json
import pathlib
import re
import tomllib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
MANIFEST = REPO / "tests" / "suites.toml"
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def test_", re.MULTILINE)


def load(manifest: pathlib.Path = MANIFEST) -> tuple[int, dict[str, dict]]:
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return int(data["max_tests"]), data["suites"]


def expand(path: str, repo: pathlib.Path = REPO) -> list[str]:
    """A suite path is a directory, or a glob (`tests/test_*.py`) for loose files.
    Returns what pytest should be given: the directory itself, or each match."""
    if (repo / path).is_dir():
        return [path]
    return sorted(f.relative_to(repo).as_posix() for f in repo.glob(path))


def test_files(path: str, repo: pathlib.Path = REPO) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for item in expand(path, repo):
        target = repo / item
        found += sorted(target.rglob("test_*.py")) if target.is_dir() else [target]
    return found


def count_tests(paths: list[str], repo: pathlib.Path = REPO) -> int:
    """`def test_` occurrences -- an approximation (parametrize not expanded),
    but stable and cheap, which is what a size limit needs."""
    return sum(len(_TEST_DEF.findall(f.read_text(encoding="utf-8")))
               for p in paths for f in test_files(p, repo))


def problems(repo: pathlib.Path = REPO, manifest: pathlib.Path = MANIFEST) -> list[str]:
    """Everything wrong with the manifest; empty means the suites are sound."""
    max_tests, suites = load(manifest)
    out: list[str] = []
    owner: dict[str, str] = {}
    for name, suite in suites.items():
        for path in suite["paths"]:
            if not expand(path, repo):
                out.append(f"suite {name}: {path} matches nothing")
            elif path in owner:
                out.append(f"{path} is in both {owner[path]} and {name}")
            owner[path] = name
        size = count_tests(suite["paths"], repo)
        if size > max_tests:
            out.append(f"suite {name} has {size} tests (limit {max_tests}) -- split it "
                       "by feature into smaller suites")
    on_disk = {f"tests/{d.name}/" for d in (repo / "tests").iterdir()
               if d.is_dir() and test_files(f"tests/{d.name}", repo)}
    out += [f"{d} holds tests but belongs to no suite -- add it to tests/suites.toml"
            for d in sorted(on_disk - set(owner))]
    covered = {f for p in owner for f in test_files(p, repo)}
    out += [f"tests/{f.name} is a loose top-level test file in no suite"
            for f in sorted((repo / "tests").glob("test_*.py")) if f not in covered]
    return out


def names() -> list[str]:
    return list(load()[1])


def paths_for(name: str) -> list[str]:
    suites = load()[1]
    if name not in suites:
        raise KeyError(f"unknown suite {name!r}; known: {', '.join(suites)}")
    return [item for p in suites[name]["paths"] for item in expand(p)]


def github_matrix() -> str:
    """The `matrix=...` line the CI test-plan job appends to $GITHUB_OUTPUT."""
    return "matrix=" + json.dumps({"suite": names()}, separators=(",", ":"))
