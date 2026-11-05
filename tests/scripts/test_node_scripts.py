"""Run the frontend's pure node tests (frontend/scripts/*.test.mjs) under pytest.

`node --test` files had no runner in CI; this wrapper puts them in the
`tooling` suite. They import only node built-ins and sibling `*-lib.mjs`
files, never `node_modules`, so they need Node and nothing else.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "frontend" / "scripts"
NODE = shutil.which("node")
NO_NODE = "node is not on PATH; frontend/scripts/*.test.mjs need Node 20+"


def node_test_files(scripts_dir: Path = SCRIPTS) -> list[Path]:
    """Every `*.test.mjs` directly in `scripts_dir`, sorted by name."""
    return sorted(scripts_dir.glob("*.test.mjs"))


def run_node_test(test_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE, "--test", str(test_file)], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )


def test_node_test_files_finds_layout_audit_lib():
    assert SCRIPTS / "layout-audit-lib.test.mjs" in node_test_files()


def test_node_test_files_is_empty_for_a_dir_without_tests(tmp_path):
    (tmp_path / "browse.mjs").write_text("", encoding="utf-8")
    assert node_test_files(tmp_path) == []


def test_node_test_files_keeps_only_test_mjs_sorted(tmp_path):
    for name in ("b.test.mjs", "a.test.mjs", "lib.mjs", "c.test.js"):
        (tmp_path / name).write_text("", encoding="utf-8")
    assert node_test_files(tmp_path) == [tmp_path / "a.test.mjs", tmp_path / "b.test.mjs"]


@pytest.mark.skipif(NODE is None, reason=NO_NODE)
def test_run_node_test_reports_a_failing_file(tmp_path):
    failing = tmp_path / "fails.test.mjs"
    failing.write_text(
        "import { test } from 'node:test';\n"
        "import { strict as assert } from 'node:assert';\n"
        "test('always fails', () => assert.equal(1, 2));\n",
        encoding="utf-8",
    )
    assert run_node_test(failing).returncode != 0


@pytest.mark.skipif(NODE is None, reason=NO_NODE)
@pytest.mark.parametrize("test_file", node_test_files(), ids=lambda p: p.name)
def test_node_test_file_passes(test_file):
    result = run_node_test(test_file)
    assert result.returncode == 0, (
        f"node --test {test_file.name} failed:\n"
        f"{result.stdout[-4000:]}\n{result.stderr[-2000:]}"
    )
