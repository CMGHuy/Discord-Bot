"""plan_lint --stats: measured lines per task over the newest plans (v193)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"

# v192 measured task sizes (2026-10-24-v192-*, 26 tasks)
V192_SIZES = [288, 364, 153, 497, 236, 522, 242, 709, 202, 393, 313, 232, 379,
              446, 495, 428, 449, 693, 202, 168, 274, 235, 300, 175, 380, 153]


def _run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, cwd=ROOT, timeout=120)
    return proc.returncode, proc.stdout


def _task(task_id: str, n_lines: int) -> str:
    """A task exactly n_lines long, its ### Task line included."""
    return "\n".join([f"### Task {task_id}: t", ""] + ["x"] * (n_lines - 2)) + "\n"


def _write(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text, encoding="utf-8")


def _corpus(d: Path) -> None:
    _write(d, "v32-old-undated.md", _task("V32-1", 900))
    for k in range(1, 6):  # v801..v805 dated 2026-01-01..05, one task of 10*k lines
        _write(d, f"2026-01-0{k}-v80{k}-p.md", "# plan\n\n" + _task(f"V80{k}-1", 10 * k))
    _write(d, "2026-01-06-v806-split_0-index.md", "# index, no tasks\n")
    _write(d, "2026-01-06-v806-split_1-a.md", _task("V806-1", 60) + _task("V806-2", 70))
    _write(d, "2026-01-07-v807-notasks.md", "# newest, but no ### Task headings\n")


def test_stats_newest_five_dated_plans_with_tasks(tmp_path):
    _corpus(tmp_path)
    code, out = _run("--stats", str(tmp_path))
    assert code == 0, out
    # v807 has no tasks (skipped, takes no slot); v801 is the sixth-newest; v32 is undated
    assert out.strip() == ("PLAN STATS: 5 plan(s), 6 task(s) -- median 45, p90 70 lines/task; "
                           "20 task(s) per part at p90 (budget 1400)")


def test_stats_matches_v192_calibration(tmp_path):
    body = "".join(_task(f"V192-{k}", n) for k, n in enumerate(V192_SIZES, start=1))
    _write(tmp_path, "2026-10-24-v192-demo.md", "# v192\n\n" + body)
    code, out = _run("--stats", str(tmp_path))
    assert code == 0, out
    assert "1 plan(s), 26 task(s) -- median 306, p90 522 lines/task; 2 task(s) per part" in out


def test_stats_no_dated_plan_with_tasks(tmp_path):
    _write(tmp_path, "v32-old.md", _task("V32-1", 50))
    _write(tmp_path, "2026-01-07-v807-notasks.md", "# no tasks\n")
    code, out = _run("--stats", str(tmp_path))
    assert code == 1
    assert "PLAN STATS: no dated plan with ### Task headings under" in out


def test_stats_bad_arguments_print_usage(tmp_path):
    for args in (("--stats", str(tmp_path / "missing")), ("--stats", str(tmp_path), "extra")):
        code, out = _run(*args)
        assert code == 2, args
        assert "usage:" in out and "--stats [dir]" in out


def test_unknown_flag_and_no_argument_fall_back_to_lint_usage():
    for args in (("--bogus",), ()):
        code, out = _run(*args)
        assert code == 2, args
        assert "usage:" in out


def test_stats_real_corpus_defaults_to_implemented():
    code, out = _run("--stats")
    assert code == 0, out
    assert out.startswith("PLAN STATS: 5 plan(s), ")
