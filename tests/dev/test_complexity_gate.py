"""The complexity ratchet (spec v149 H1): scripts/dev/complexity_gate.py."""
import importlib.util
import json
import os
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


def test_check_skips_without_git(gate, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    assert _run(gate, tmp_path) == 0
    assert capsys.readouterr().out.startswith("VERDICT: SKIP")


def test_check_fails_closed_without_git_in_ci(gate, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert _run(gate, tmp_path) == 1
    assert capsys.readouterr().out.startswith("VERDICT: FAIL")


def test_empty_ci_variable_still_skips(gate, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CI", "")
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


# -- the real tree ----------------------------------------------------------

@pytest.mark.slow
@pytest.mark.skipif(
    bool(os.environ.get("CI")),
    reason="CI runs the gate as its own named step in backend-lint-gate")
def test_committed_tree_matches_the_baseline(gate):
    """~20 s warm, so `slow`: `testrun.py full` runs it, `fast` does not.

    A failure here means a function crossed 15, rose, improved or went away.
    Run `python scripts/dev/complexity_gate.py` for the list.
    """
    current = gate.measure(gate.REPO, gate.python_files(gate.REPO))
    assert gate.compare(current, gate.load_baseline(gate.BASELINE)) == []
