"""plan_lint catches the defects plan writers used to check by hand."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"

HEADER = ("# v900 Demo\n\n**Bump:** none\n**Edge:** none (integrity)\n"
          "**Spec:** [spec](../specs/x.md)\n\n## Parallelisation\n\nSerial.\n\n"
          "## Task ledger\n\n| Id | Title |\n|---|---|\n| V900-1 | a |\n| V900-2 | b |\n\n")
TASK = ("### Task {id}: t\n\n**Model:** sonnet — mechanical\n\n- Modify: `bot.py`\n\n"
        "Close: standard (test: tests/dev/test_x.py)\n\n")


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
            + "Close: standard (test: tests/dev/test_x.py)\n\n"
            + "### Task V900-2: t\n\n**Model:** sonnet — code\n\n- Modify: `new/mod.py`\n\n"
            + "**Close:** standard (test: tests/dev/test_x.py)\n")
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


CLOSE = "Close: standard (test: tests/dev/test_x.py)"


def _task(task_id: str, n_lines: int, *, close: str | None = CLOSE,
          modify: tuple[str, ...] = ("`bot.py`",)) -> str:
    """A task exactly n_lines long, its ### Task line included."""
    lines = [f"### Task {task_id}: t", "", "**Model:** sonnet — mechanical", ""]
    lines += [f"- Modify: {m}" for m in modify] + [""]
    if close:
        lines.append(close)
    lines += ["x"] * (n_lines - len(lines))
    return "\n".join(lines) + "\n"


def _bot_py_lines() -> int:
    return len((ROOT / "bot.py").read_text(encoding="utf-8").splitlines())


def test_v192_plan_skips_new_rules(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-24-v192-demo_0-index.md": HEADER,
        "2026-10-24-v192-demo_1-a.md": _task("V900-1", 709, close=None,
                                             modify=("`bot.py:1-999999`",)),
        "2026-10-24-v192-demo_2-b.md": _task("V900-2", 20, close=None),
    })
    assert code == 0, out
    assert "PLAN LINT: PASS  3 file(s)" in out


def test_new_rules_close_line_and_ceiling(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-25-v900-demo_0-index.md": HEADER,
        "2026-10-25-v900-demo_1-a.md": _task("V900-1", 401),
        "2026-10-25-v900-demo_2-b.md": _task("V900-2", 400, close=None),
    })
    assert code == 1
    assert "Task V900-1 -- 401 lines (ceiling 400) -- split into two tasks" in out
    assert "Task V900-2 -- no Close: line" in out
    assert "V900-2 -- 400 lines" not in out
    assert "V900-1 -- no Close: line" not in out


def test_close_line_variants_pass(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-25-v900-demo_0-index.md": HEADER,
        "2026-10-25-v900-demo_1-a.md": _task("V900-1", 30, close="**Close:** standard (test: t.py)"),
        "2026-10-25-v900-demo_2-b.md": _task("V900-2", 30, close="- [ ] Close: standard; no commit"),
    })
    assert code == 0, out


def test_modify_range_variants(tmp_path):
    n = _bot_py_lines()
    first = ("### Task V900-1: t\n\n**Model:** sonnet — code\n\n- Create: `new/mod.py`\n\n"
             f"{CLOSE}\n\n")
    second = _task("V900-2", 30, modify=(
        "`bot.py`", "`bot.py:1`", f"`bot.py:1-{n} (main)`", f"`bot.py:1-{n}` (main)",
        "`new/mod.py:120-180` (created by V900-1)"))
    code, out = _lint(tmp_path, {"2026-10-25-v900-demo.md": HEADER + first + second})
    assert code == 0, out


def test_modify_range_past_end_fails(tmp_path):
    n = _bot_py_lines()
    body = HEADER + _task("V900-1", 30) + _task("V900-2", 30, modify=(f"`bot.py:{n}-{n + 1}` (main)",))
    code, out = _lint(tmp_path, {"2026-10-25-v900-demo.md": body})
    assert code == 1
    assert f"Modify `bot.py:{n}-{n + 1}` ends past line {n} of the file" in out
