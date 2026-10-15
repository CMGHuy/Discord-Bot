"""Guards tests/suites.toml -- the grouping that makes a partial test run possible
and that the CI matrix is built from (docs/claude/testing-cost.md "Test suites").

Without these, a new tests/ directory is silently absent from CI, or a suite
quietly grows until it is the whole suite again."""
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))

import suites  # noqa: E402


def test_the_manifest_is_sound():
    assert suites.problems() == []


def test_every_test_file_is_in_exactly_one_suite():
    seen: dict[Path, str] = {}
    for name, suite in suites.load()[1].items():
        for path in suite["paths"]:
            for f in suites.test_files(path):
                assert f not in seen, f"{f} is in {seen[f]} and {name}"
                seen[f] = name
    on_disk = set((REPO / "tests").rglob("test_*.py"))
    assert on_disk == set(seen)


def test_the_matrix_lists_every_suite():
    line = suites.github_matrix()
    assert line.startswith("matrix=")
    assert json.loads(line[len("matrix="):]) == {"suite": suites.names()}


def test_ci_builds_its_jobs_from_the_manifest_not_a_hand_list():
    jobs = yaml.safe_load((REPO / ".github/workflows/deploy.yml").read_text(encoding="utf-8"))["jobs"]
    assert not [j for j in jobs if j.startswith("backend-test-")], \
        "hand-listed shard job: add a suite to tests/suites.toml instead"
    assert jobs["backend-test"]["strategy"]["matrix"] == "${{ fromJSON(needs.test-plan.outputs.matrix) }}"
    assert "backend-test" in jobs["publish-image"]["needs"]
    assert "publish-image" in jobs["deploy"]["needs"]


def test_problems_flags_an_unowned_directory_and_an_oversized_suite(tmp_path):
    (tmp_path / "tests" / "orphan").mkdir(parents=True)
    (tmp_path / "tests" / "orphan" / "test_a.py").write_text("def test_a():\n    pass\n")
    (tmp_path / "tests" / "big").mkdir()
    (tmp_path / "tests" / "big" / "test_b.py").write_text("def test_b():\n    pass\ndef test_c():\n    pass\n")
    manifest = tmp_path / "suites.toml"
    manifest.write_text('max_tests = 1\n[suites.big]\ndescription = "x"\npaths = ["tests/big/"]\n')

    found = suites.problems(repo=tmp_path, manifest=manifest)

    assert any("tests/orphan/ holds tests but belongs to no suite" in p for p in found)
    assert any("suite big has 2 tests (limit 1)" in p for p in found)


def test_paths_for_rejects_an_unknown_suite():
    with pytest.raises(KeyError):
        suites.paths_for("no-such-suite")
