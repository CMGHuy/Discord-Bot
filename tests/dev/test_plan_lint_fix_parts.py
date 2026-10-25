"""plan_lint --fix-parts: the index's parts table is generated, never hand-edited (v193)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"
BASE = "2026-10-25-v900-demo"

BEFORE = "# v900 Demo\n\n**Bump:** none\n\n## Goal\n\nWhy.\n\n"
PARTS = ("## Parts\n\n| Part | File | Tasks | Scope |\n|---|---|---|---|\n"
         "| 1 | `old-name.md` | V900-1 | alpha \\| beta |\n"
         f"| 2 | `{BASE}_2-second.md` | V900-9 | gamma |\n\n")
AFTER = "## Task ledger\n\n| Task | Title |\n|---|---|\n| V900-1 | a |\n"


def _task(task_id: str) -> str:
    return f"### Task {task_id}: t\n\nbody\n\n"


def _plan(d: Path, index_text: str, parts: dict[str, str]) -> Path:
    index = d / f"{BASE}_0-index.md"
    index.write_text(index_text, encoding="utf-8")
    for suffix, text in parts.items():
        (d / f"{BASE}_{suffix}.md").write_text(text, encoding="utf-8")
    return index


def _run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


SPLIT = {"1-first": _task("V900-1") + _task("V900-2"),
         "1b-spill-over": _task("V900-3"),
         "2-second": _task("V900-4")}


def test_fix_parts_regenerates_table_and_keeps_scopes(tmp_path):
    index = _plan(tmp_path, BEFORE + PARTS + AFTER, SPLIT)
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    assert f"PARTS TABLE: 3 part(s) in {index.name}" in out
    want = ("## Parts\n\n| Part | File | Tasks | Scope |\n|---|---|---|---|\n"
            f"| 1 | `{BASE}_1-first.md` | V900-1..V900-2 | alpha \\| beta |\n"
            f"| 1b | `{BASE}_1b-spill-over.md` | V900-3 | spill over |\n"
            f"| 2 | `{BASE}_2-second.md` | V900-4 | gamma |\n\n")
    assert index.read_bytes().decode("utf-8") == BEFORE + want + AFTER


def test_fix_parts_idempotent(tmp_path):
    index = _plan(tmp_path, BEFORE + PARTS + AFTER, SPLIT)
    assert _run("--fix-parts", str(index))[0] == 0
    first = index.read_bytes()
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    assert index.read_bytes() == first


def test_fix_parts_inserts_table_under_an_empty_section(tmp_path):
    index = _plan(tmp_path, BEFORE + "## Parts\n\n" + AFTER, {"1-only": _task("V900-1")})
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    assert index.read_text(encoding="utf-8") == (
        BEFORE + "## Parts\n\n| Part | File | Tasks | Scope |\n|---|---|---|---|\n"
        f"| 1 | `{BASE}_1-only.md` | V900-1 | only |\n\n" + AFTER)
    first = index.read_bytes()
    assert _run("--fix-parts", str(index))[0] == 0
    assert index.read_bytes() == first


def test_fix_parts_numeric_order_and_part_without_tasks(tmp_path):
    index = _plan(tmp_path, BEFORE + "## Parts\n\n" + AFTER,
                  {"10-ten": "# no tasks yet\n", "2-two": _task("V900-1")})
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    text = index.read_text(encoding="utf-8")
    two = text.index(f"| 2 | `{BASE}_2-two.md` | V900-1 | two |")
    ten = text.index(f"| 10 | `{BASE}_10-ten.md` | — | ten |")
    assert two < ten


def test_fix_parts_without_parts_section(tmp_path):
    index = _plan(tmp_path, BEFORE + AFTER, SPLIT)
    code, out = _run("--fix-parts", str(index))
    assert code == 1
    assert f"PARTS TABLE: no ## Parts section in {index.name}" in out
    assert index.read_text(encoding="utf-8") == BEFORE + AFTER


def test_fix_parts_bad_arguments(tmp_path):
    for args in (("--fix-parts",), ("--fix-parts", str(tmp_path / "missing.md"))):
        code, out = _run(*args)
        assert code == 2, args
        assert "--fix-parts <index>" in out
