"""Change-aware test selection (v99).

Every case runs against a fixture tree under tmp_path, not the real repo: the
real graph changes every commit and a test pinned to it would drift.
"""
import ast
import functools
import importlib.util
import pathlib
import subprocess
import sys
import warnings

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sel():
    spec = importlib.util.spec_from_file_location(
        "select_tests_mod", REPO / "scripts/dev/select_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # @dataclass resolves string annotations through sys.modules[cls.__module__].
    sys.modules[spec.name] = module
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


def test_ancestor_package_inits_reach_importers_of_submodules(sel, tmp_path):
    """Importing pkg.sub.mod executes pkg/__init__ and pkg/sub/__init__ too."""
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/mod.py": "VALUE = 1\n",
        "tests/test_mod.py": "from pkg.sub import mod\n",
    })
    reverse = sel.build_import_graph(repo)
    assert "tests/test_mod.py" in sel.importers_of(reverse, "pkg/__init__.py")
    assert "tests/test_mod.py" in sel.importers_of(reverse, "pkg/sub/__init__.py")


def test_tracked_but_deleted_file_keeps_its_importer_edge(sel, tmp_path):
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/gone.py": "VALUE = 1\n",
        "tests/test_gone.py": "from pkg.gone import VALUE\n",
    })
    (repo / "pkg/gone.py").unlink()
    reverse = sel.build_import_graph(repo)
    assert reverse["pkg/gone.py"] == {"tests/test_gone.py"}


def test_unreadable_file_raises_unparseable(sel, tmp_path):
    repo = _tree(tmp_path, {"pkg/dir.py": "x = 1\n"})
    (repo / "pkg/dir.py").unlink()
    (repo / "pkg/dir.py").mkdir()  # exists but read_text raises OSError
    with pytest.raises(sel.UnparseableFile) as caught:
        sel.build_import_graph(repo)
    assert caught.value.path == "pkg/dir.py"


def test_null_byte_source_raises_unparseable(sel, tmp_path):
    repo = _tree(tmp_path, {"pkg/nullbyte.py": "x = 1\n"})
    (repo / "pkg/nullbyte.py").write_bytes(b"x = 1\x00\n")
    with pytest.raises(sel.UnparseableFile):
        sel.build_import_graph(repo)


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
    result = sel.select(["docs/deploy/NOTES.md"], _repo(tmp_path))
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


def test_deleted_source_file_reaches_its_importers(sel, tmp_path):
    """A tracked file removed from disk stays in the graph; it must neither
    crash select nor narrow below its importers' tests."""
    repo = _repo(tmp_path)
    (repo / "swingbot/core/planning/plan_engine.py").unlink()
    result = sel.select(["swingbot/core/planning/plan_engine.py"], repo)
    assert result.full is False
    assert "tests/scanning/test_engine.py" in result.targets


def test_deleted_test_file_is_not_a_target(sel, tmp_path):
    """pytest errors on a path that no longer exists; widen instead."""
    repo = _repo(tmp_path)
    (repo / "tests/planning/test_plan_engine.py").unlink()
    result = sel.select(["tests/planning/test_plan_engine.py"], repo)
    assert result.full is True


# --- final-review fix wave (2026-09-29) ------------------------------------

@pytest.mark.parametrize("source", [
    "a" + ".b" * 300000,   # RecursionError during ast construction
    "-" * 200000 + "1",    # MemoryError from the parser stack
], ids=["recursion", "memory"])
def test_pathological_source_raises_unparseable(sel, tmp_path, source):
    repo = _tree(tmp_path, {"pkg/deep.py": source})
    with pytest.raises(sel.UnparseableFile):
        sel.build_import_graph(repo)


def test_bare_name_import_after_sys_path_insert_reaches_the_script(sel, tmp_path):
    """~20 tests do sys.path.insert(0, ROOT/'scripts'/'backtest') then
    `import validate_component`: a top-level name no dotted module matches."""
    repo = _tree(tmp_path, {
        "scripts/backtest/validate_component.py": "VALUE = 1\n",
        "tests/test_cli.py": "import scripts.backtest.validate_component\n",
        "tests/test_stamps.py": (
            "import sys\nsys.path.insert(0, 'scripts/backtest')\n"
            "import validate_component\n"),
        "tests/test_from.py": "from validate_component import VALUE\n",
        "tests/test_pkg_rel.py": "from backtest import validate_component\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse["scripts/backtest/validate_component.py"] == {
        "tests/test_cli.py", "tests/test_stamps.py", "tests/test_from.py",
        "tests/test_pkg_rel.py",
    }


def test_unresolved_bare_name_over_approximates_to_every_same_named_file(sel, tmp_path):
    repo = _tree(tmp_path, {
        "scripts/a/tool.py": "X = 1\n",
        "scripts/b/tool/__init__.py": "X = 2\n",
        "tests/test_tool.py": "import tool\n",
    })
    reverse = sel.build_import_graph(repo)
    assert reverse["scripts/a/tool.py"] == {"tests/test_tool.py"}
    assert reverse["scripts/b/tool/__init__.py"] == {"tests/test_tool.py"}


def test_conftest_imported_by_the_root_conftest_widens(sel, tmp_path):
    """tests/conftest.py re-exports tests/db/conftest.py fixtures suite-wide."""
    repo = _repo(tmp_path)
    (repo / "tests/db").mkdir()
    (repo / "tests/db/__init__.py").write_text("", encoding="utf-8")
    (repo / "tests/db/conftest.py").write_text("FIXTURE = 1\n", encoding="utf-8")
    (repo / "tests/conftest.py").write_text(
        "from tests.db.conftest import FIXTURE\n", encoding="utf-8")
    result = sel.select(["tests/db/conftest.py"], repo)
    assert result.full is True
    assert "root conftest" in result.reason


def test_module_imported_by_a_conftest_selects_the_conftest_subtree(sel, tmp_path):
    repo = _repo(tmp_path)
    (repo / "tests/scanning/helpers.py").write_text("H = 1\n", encoding="utf-8")
    (repo / "tests/scanning/conftest.py").write_text(
        "from tests.scanning.helpers import H\n", encoding="utf-8")
    result = sel.select(["tests/scanning/helpers.py"], repo)
    assert (result.full, result.targets) == (False, ["tests/scanning/"])


def test_non_ascii_paths_are_listed_despite_core_quotepath(sel, tmp_path):
    """core.quotePath wraps non-ASCII names in quotes; they must still list."""
    repo = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/caf\u00e9.py": "VALUE = 1\n",
        "tests/test_caf\u00e9.py": "from pkg.caf\u00e9 import VALUE\n",
    })
    subprocess.run(["git", "config", "core.quotepath", "true"], cwd=repo, check=True)
    (repo / "pkg/new_\u00fc.py").write_text("X = 1\n", encoding="utf-8")  # untracked
    files = sel.repo_python_files(repo)
    assert "pkg/caf\u00e9.py" in files and "tests/test_caf\u00e9.py" in files
    assert "pkg/new_\u00fc.py" in files


def _with_readers(repo: pathlib.Path) -> pathlib.Path:
    """Add the tests that read repo data files rather than importing code."""
    for rel in ("tests/hooks/test_guardrails.py", "tests/hooks/test_codex_mirror.py",
                "tests/dev/test_testrun_ci_invocations.py"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("X = 1\n", encoding="utf-8")
    return repo


@pytest.mark.parametrize("path, expected", [
    (".github/workflows/deploy.yml", ["tests/dev/test_testrun_ci_invocations.py"]),
    (".claude/settings.json", ["tests/hooks/"]),
    (".claude/skills/gate/SKILL.md", ["tests/hooks/"]),
    (".claude/agents/test-runner.md", ["tests/hooks/"]),
    ("CLAUDE.md", ["tests/hooks/"]),
    ("AGENTS.md", ["tests/hooks/"]),
    ("docs/claude/backtest-methodology.md",
     ["tests/hooks/test_codex_mirror.py", "tests/hooks/test_guardrails.py"]),
])
def test_data_read_path_routes_to_its_readers(sel, tmp_path, path, expected):
    """Partner decision 2026-09-29: the widening rule beats the inert list."""
    result = sel.select([path], _with_readers(_repo(tmp_path)))
    assert (result.full, result.targets) == (False, expected)


@pytest.mark.parametrize("path", ["requirements.txt", ".github/dependabot.yml"])
def test_formerly_inert_non_python_now_widens(sel, tmp_path, path):
    result = sel.select([path], _with_readers(_repo(tmp_path)))
    assert result.full is True


def test_data_reader_target_missing_on_disk_widens(sel, tmp_path):
    result = sel.select([".github/workflows/deploy.yml"], _repo(tmp_path))
    assert result.full is True
    assert "test_testrun_ci_invocations.py" in result.reason


def test_data_read_path_and_source_union_their_targets(sel, tmp_path):
    result = sel.select(
        ["CLAUDE.md", "tests/planning/test_plan_engine.py"],
        _with_readers(_repo(tmp_path)),
    )
    assert (result.full, result.targets) == (
        False, ["tests/hooks/", "tests/planning/test_plan_engine.py"])


def _is_str(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_div(node) -> bool:
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)


def _join_parts(node) -> list | None:
    """Operands of a path join -- `a / 'b' / 'c'` or os.path.join(a, 'b',
    'c') -- in order, else None."""
    if _is_div(node):
        left = _join_parts(node.left)
        return (left if left is not None else [node.left]) + [node.right]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join" and not _is_str(node.func.value)):
        return list(node.args)
    return None


def _string_tail(parts: list) -> str:
    """'b/c' for [ROOT, 'b', 'c'] -- the trailing string operands, joined."""
    tail: list[str] = []
    for part in reversed(parts):
        if not _is_str(part):
            break
        tail.insert(0, part.value)
    return "/".join(tail)


def _path_literals(tree) -> set[str]:
    """String constants, plus the joined string tail of every path join.
    Join fragments are consumed so a lone 'docs' or 'frontend' never stands
    in for the joined path."""
    found, consumed = set(), set()
    # ast.walk is breadth-first: a join is always seen before its operands.
    for node in ast.walk(tree):
        if id(node) in consumed:
            continue
        if _is_str(node) and len(node.value) < 200:
            found.add(node.value)
        parts = _join_parts(node) or []
        tail = _string_tail(parts)
        if tail:
            found.add(tail)
        consumed |= {id(part) for part in parts if _is_str(part)}
        consumed |= _inner_links(node)
    return found


def _inner_links(node) -> set[int]:
    """ids of the inner BinOps of the `/` chain `node` heads."""
    links: set[int] = set()
    while _is_div(node) and _is_div(node.left):
        node = node.left
        links.add(id(node))
    return links


# Literals that name an existing file but are only ever fed to a function as
# a string -- never opened -- so their being inert is correct.
_NOT_READ = {
    # test_sse_contract.py names the frontend/ directory; it reads sources,
    # and the directory walk also lists these READMEs.
    "frontend/README.md",
    "frontend/chart-harness/README.md",
    # test_guardrails.py feeds these to the hook's plan-doc shape check.
    "docs/superpowers/plans/implemented/2026-09-18-v96-claude-skills-layer.md",
    "docs/superpowers/plans/implemented/2026-09-16-v92-exit-quality-harvest.md",
    "docs/superpowers/plans/2026-08-29-v67-json-to-postgres_1a-foundation-core.md",
    # test_env_example_sync.py quotes these in an assertion message.
    "docs/superpowers/plans/implemented/v34-train-preregistration.md",
    "docs/superpowers/plans/implemented/v35-avwap-preregistration.md",
}


@functools.lru_cache(maxsize=None)
def _listed_under(rel_dir: str) -> tuple[str, ...]:
    """Files under a directory that could show up in a diff: tracked, or
    untracked and not ignored -- the same set testrun.changed_paths sees."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", rel_dir], cwd=REPO, capture_output=True, check=True)
    return tuple(item for item in out.stdout.decode("utf-8").split("\0") if item)


@functools.lru_cache(maxsize=None)
def _entries(directory: pathlib.Path) -> frozenset[str]:
    return frozenset(entry.name for entry in directory.iterdir()) | {".."}


def _candidates(literal: str, test_dir: pathlib.Path) -> list[str]:
    """Non-.py repo files a literal names: the file itself, or for a
    directory every listable file under it (a directory reader reads them)."""
    literal = literal.replace("\\", "/").strip("/")
    if not literal or any(c in literal for c in "\0\n*?<>|:{"):
        return []
    target = _existing_in_repo(literal, test_dir)
    if target is None:
        return []
    rel = target.relative_to(REPO).as_posix()
    listed = _listed_under(rel) if target.is_dir() else (rel,)
    return [path for path in listed if not path.endswith(".py")]


def _existing_in_repo(literal: str, test_dir: pathlib.Path) -> pathlib.Path | None:
    """The existing in-repo path a literal names, relative to the repo root
    or to the naming test's own directory."""
    first = literal.split("/", 1)[0]
    for base in (REPO, test_dir):
        if first not in _entries(base):  # cheap pre-filter before resolve()
            continue
        target = (base / literal).resolve()
        if target.exists() and REPO in target.parents:
            return target
    return None


def test_no_path_a_test_reads_is_classified_inert(sel, monkeypatch):
    """Against the REAL repo: every repo file a test names by literal must
    route somewhere (targets or full), never to 'nothing to test'. A new
    test reading, say, docs/strategy/x.md fails here until DATA_READERS
    learns about it.

    This file is skipped: its path literals are inputs to select() on
    fixture trees, not files it reads. The threshold is stubbed out because
    it can only widen, so it cannot change an inert verdict -- and it costs
    two whole-repo git listings per call.
    """
    monkeypatch.setattr(sel, "_threshold_reason", lambda *_a: None)
    this = pathlib.Path(__file__).resolve()
    named: dict[str, str] = {}
    for test in sorted((REPO / "tests").rglob("*.py")):
        if test == this:
            continue
        with warnings.catch_warnings():  # invalid escapes in other tests' source
            warnings.simplefilter("ignore")
            tree = ast.parse(test.read_text(encoding="utf-8", errors="replace"))
        for literal in _path_literals(tree):
            for rel in _candidates(literal, test.parent):
                named.setdefault(rel, test.relative_to(REPO).as_posix())
    inert = []
    for rel, test in sorted(named.items()):
        result = sel.select([rel], REPO)
        if rel not in _NOT_READ and not result.full and not result.targets:
            inert.append(f"{rel} (named in {test})")
    assert not inert, "\n".join(inert)


def test_unreached_source_widens_even_beside_a_reached_one(sel, tmp_path):
    """A second, reachable change must not hide one no test imports."""
    repo = _repo(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts/orphan.py").write_text("X = 1\n", encoding="utf-8")
    result = sel.select(
        ["scripts/orphan.py", "swingbot/core/planning/plan_engine.py"], repo)
    assert result.full is True
    assert "scripts/orphan.py" in result.reason


def test_targets_inside_a_selected_directory_are_collapsed(sel, tmp_path):
    """tests/hooks/ plus tests/hooks/test_guardrails.py would hand pytest the
    same file twice; the directory already covers it."""
    result = sel.select(["AGENTS.md", "docs/claude/testing-cost.md"],
                        _with_readers(_repo(tmp_path)))
    assert (result.full, result.targets) == (False, ["tests/hooks/"])
