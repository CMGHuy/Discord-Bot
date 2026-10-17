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
