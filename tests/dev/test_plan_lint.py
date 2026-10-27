"""plan_lint catches the defects plan writers used to check by hand."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"

HEADER = ("# v900 Demo\n\n**Bump:** none\n**Edge:** none (integrity)\n"
          "**Spec:** [spec](../specs/x.md)\n\n## Parallelisation\n\nSerial.\n\n"
          "## Task ledger\n\n| Id | Title |\n|---|---|\n| V900-1 | a |\n| V900-2 | b |\n\n")
TASK = "### Task {id}: t\n\n**Model:** sonnet — mechanical\n\n- Modify: `bot.py`\n\n"


def _lint(tmp_path: Path, files: dict[str, str]) -> tuple[int, str]:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    first = sorted(files)[0]
    proc = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / first)],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


def test_complete_split_plan_passes(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-09-v900-demo_0-index.md": HEADER,
        "2026-10-09-v900-demo_1-a.md": TASK.format(id="V900-1"),
        "2026-10-09-v900-demo_2-b.md": TASK.format(id="V900-2"),
    })
    assert code == 0, out
    assert "PLAN LINT: PASS  3 file(s)" in out


def test_missing_task_model_line_and_bad_path_fail(tmp_path):
    body = HEADER + "### Task V900-1: t\n\nNo model line.\n\n- Modify: `nope/gone.py`\n"
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 1
    assert "no ### Task yet for V900-2" in out
    assert "Task V900-1 -- first line is not **Model:**" in out
    assert "Modify `nope/gone.py`" in out


def test_created_earlier_then_modified_is_fine(tmp_path):
    body = (HEADER + "### Task V900-1: t\n\n**Model:** haiku — docs\n\n- Create: `new/mod.py`\n\n"
            + "### Task V900-2: t\n\n**Model:** sonnet — code\n\n- Modify: `new/mod.py`\n")
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 0, out


def test_header_cap_duplicates_and_placeholders(tmp_path):
    body = ("# v900\n\n**Bump:** none\n**Edge:** vibes\n\n" + TASK.format(id="V900-1") * 2
            + "TBD\nPLAN_TASK_EOF\n" + "x\n" * 1500)
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 1
    for needle in ("missing **Spec:**", "Edge 'vibes'", "missing ## Parallelisation",
                   "appears twice", "TBD", "PLAN_TASK_EOF", "cap 1500"):
        assert needle in out, needle


SECOND = TASK.format(id="V900-2")
FILLER = ("z" * 99 + "\n") * 100  # 10 000 bytes of non-task text


def _sized_task(task_id: str, nbytes: int) -> str:
    """A ### Task block of exactly `nbytes` UTF-8 bytes (each line costs len + 1)."""
    head = f"### Task {task_id}: t\n\n**Model:** sonnet — mechanical\n\n"
    lines, rest = divmod(nbytes - len(head.encode("utf-8")), 100)
    body = ("x" * 99 + "\n") * lines
    if rest:
        body += "y" * (rest - 1) + "\n"
    text = head + body
    assert len(text.encode("utf-8")) == nbytes
    return text


def test_task_exactly_at_the_byte_cap_passes(tmp_path):
    body = HEADER + _sized_task("V900-1", 20_000) + SECOND
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 0, out


def test_task_one_byte_over_the_cap_fails(tmp_path):
    body = HEADER + _sized_task("V900-1", 20_001) + SECOND
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 1
    assert ("2026-10-09-v900-demo.md: Task V900-1 is 20.0 KB (cap 20 KB) "
            "-- split into two tasks, never compress") in out
    assert "Task V900-2 is" not in out


def test_size_is_printed_to_one_decimal(tmp_path):
    body = HEADER + _sized_task("V900-1", 23_456) + SECOND
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 1
    assert "Task V900-1 is 23.5 KB (cap 20 KB)" in out


@pytest.mark.parametrize("heading", ["# Phase 2 — second\n", "## Handoff\n"])
def test_size_ends_at_a_phase_or_section_heading(tmp_path, heading):
    # 15 000 + 10 000 would be over the cap if the heading did not close the span.
    body = HEADER + _sized_task("V900-1", 15_000) + heading + FILLER + SECOND
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": body})
    assert code == 0, out


def test_size_resets_per_file(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-09-v900-demo_0-index.md": HEADER,
        "2026-10-09-v900-demo_1-a.md": _sized_task("V900-1", 15_000),
        "2026-10-09-v900-demo_2-b.md": FILLER + SECOND,
    })
    assert code == 0, out


def test_utf8_bytes_count_not_characters(tmp_path):
    head = "### Task V900-1: t\n\n**Model:** sonnet — mechanical\n\n"
    task = head + ("é" * 49 + "\n") * 300  # 99 bytes but 50 characters per line
    assert len(task) < 20_000 < len(task.encode("utf-8"))
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": HEADER + task + SECOND})
    assert code == 1
    assert "Task V900-1 is 29.8 KB (cap 20 KB)" in out


def test_comment_inside_a_code_fence_does_not_end_the_task(tmp_path):
    head = "### Task V900-1: t\n\n**Model:** sonnet — mechanical\n\n"
    task = head + "```python\n# tests/dev/test_x.py\n" + ("x" * 99 + "\n") * 250 + "```\n"
    code, out = _lint(tmp_path, {"2026-10-09-v900-demo.md": HEADER + task + SECOND})
    assert code == 1
    assert "Task V900-1 is 25.1 KB (cap 20 KB)" in out
