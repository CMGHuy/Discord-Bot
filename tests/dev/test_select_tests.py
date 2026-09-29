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
