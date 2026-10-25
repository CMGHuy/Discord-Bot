"""plan_slice.py: one part writer's whole context in one read (v193, spec § C)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_slice.py"
INDEX = "2026-10-25-v900-demo_0-index.md"
HEAD = ("| Task | Title | Part | Model | Spec § | Files created / modified | Creates "
        "| Consumes |\n|---|---|---|---|---|---|---|---|\n")
ROWS = ("| V900-1 | one | 1 | sonnet | A | M `scripts/dev/x.py` | — | — |\n"
        "| V900-2 | two | 2 | sonnet | B | M `scripts/dev/y.py:10-20`; "
        "C `scripts/dev/new_tool.py` | — | — |\n")
SPEC = ("# v900 spec\n\n## A. Alpha\n\nalpha-body\n\n## B. Beta\n\nbeta-body\n\n"
        "### B.1 Detail\n\nbeta-detail\n\n## Testing\n\ntesting-body\n")
BRIEF = ("# Brief\n\n## scripts/dev/x.py\n\nx-brief\n\n## scripts/dev/y.py (120 lines)\n\n"
         "y-brief\n\n## Traps\n\ntrap-line\n")


def _index(rows: str = ROWS, extra: str = "") -> str:
    return ("# v900 Demo (index)\n\n**Bump:** none\n**Edge:** none (integrity)\n"
            "**Spec:** [spec](spec.md)\n\n## Goal\n\ngoal-text-not-sliced\n\n"
            "## Global Constraints\n\n- constraint-one\n\n### Standard task close\n\n"
            "close-steps-here\n\n## Parallelisation\n\nparallel-not-sliced\n\n" + extra
            + "## Task ledger\n\n" + HEAD + rows + "\n")


def _slice(tmp_path, part="2", rows=ROWS, extra="", brief="brief.md"):
    (tmp_path / "spec.md").write_text(SPEC, encoding="utf-8")
    (tmp_path / "brief.md").write_text(BRIEF, encoding="utf-8")
    index = tmp_path / INDEX
    index.write_text(_index(rows, extra), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(index), part,
                           "--brief", str(tmp_path / brief)],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


def test_slice_prints_only_this_parts_context(tmp_path):
    code, out = _slice(tmp_path)
    assert code == 0, out
    for wanted in ("**Bump:** none", "constraint-one", "close-steps-here",
                   "| V900-1 |", "| V900-2 |", "beta-body", "beta-detail",
                   "y-brief", "trap-line"):
        assert wanted in out, wanted
    for unwanted in ("alpha-body", "testing-body", "x-brief",
                     "goal-text-not-sliced", "parallel-not-sliced", "MISSING"):
        assert unwanted not in out, unwanted


def test_slice_includes_handoff(tmp_path):
    code, out = _slice(tmp_path, extra="## Handoff\n\npartner-decision\n\n")
    assert code == 0, out
    assert "partner-decision" in out


def test_slice_missing_spec_section(tmp_path):
    rows = "| V900-2 | two | 2 | sonnet | B; Q | M `scripts/dev/y.py` | — | — |\n"
    code, out = _slice(tmp_path, rows=rows)
    assert code == 0, out
    assert "MISSING: spec section 'Q'" in out
    assert "beta-body" in out


def test_slice_missing_brief_section(tmp_path):
    rows = "| V900-2 | two | 2 | sonnet | B | M `scripts/dev/z.py` | — | — |\n"
    code, out = _slice(tmp_path, rows=rows)
    assert code == 0, out
    assert "MISSING: brief section 'scripts/dev/z.py'" in out


def test_slice_without_brief(tmp_path):
    code, out = _slice(tmp_path, brief="absent.md")
    assert code == 0, out
    assert "MISSING: brief file" in out
    assert "constraint-one" in out and "beta-body" in out


def test_slice_unknown_part(tmp_path):
    code, out = _slice(tmp_path, part="7")
    assert code == 2
    assert out.strip() == f"plan_slice: no ledger rows for part '7' in {INDEX}"


def test_slice_part_label_is_exact(tmp_path):
    code, out = _slice(tmp_path, part="2b")
    assert code == 2


def test_slice_usage():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                          text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 2
    assert proc.stdout.startswith("usage:")


def test_default_brief_strips_part_suffix():
    spec = importlib.util.spec_from_file_location("plan_slice", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = ROOT / ".superpowers" / "briefs" / "2026-10-25-v900-demo.md"
    assert mod.default_brief(Path("docs/p/2026-10-25-v900-demo_0-index.md")) == want
    assert mod.default_brief(Path("docs/p/2026-10-25-v900-demo_2b-spill.md")) == want
    assert mod.default_brief(Path("docs/p/2026-10-25-v900-demo.md")) == want


GAP_ROWS = ("| V900-1 | one | 1 | sonnet | A | M `scripts/dev/x.py`; M `scripts/dev/z.py` | — | — |\n"
            "| V900-2 | two | 2 | sonnet | B | M `scripts/dev/z.py`; M `tests/dev/test_q.py`; "
            "C `scripts/dev/new_tool.py` | — | — |\n"
            "| V900-3 | three | 2b | sonnet | B | M `scripts/dev/y.py` | — | — |\n")


def test_gaps_lists_unbriefed_modified_files_once_with_parts(tmp_path):
    code, out = _slice(tmp_path, part="--gaps", rows=GAP_ROWS)
    assert code == 1, out
    assert out.splitlines() == [
        "GAP: scripts/dev/z.py (parts 1, 2)",
        "GAP: tests/dev/test_q.py (parts 2)",
        "BRIEF GAPS: 2 file(s)",
    ]


def test_gaps_none_when_brief_covers_every_modified_file(tmp_path):
    code, out = _slice(tmp_path, part="--gaps")
    assert code == 0, out
    assert out.splitlines() == ["BRIEF GAPS: 0 file(s)"]


def test_gaps_without_brief_file(tmp_path):
    code, out = _slice(tmp_path, part="--gaps", brief="absent.md")
    assert code == 2
    assert "MISSING: brief file" in out


def test_slice_blocks_when_brief_gaps_exceed_budget(tmp_path):
    rows = "".join(
        f"| V900-{n} | t | 1 | sonnet | A | M `scripts/dev/g{n}.py` | — | — |\n"
        for n in range(1, 8))
    code, out = _slice(tmp_path, part="1", rows=rows)
    assert code == 3, out
    assert "BLOCKED: brief gaps (7 files, budget 5)" in out


def test_slice_within_gap_budget_is_not_blocked(tmp_path):
    rows = "".join(
        f"| V900-{n} | t | 1 | sonnet | A | M `scripts/dev/g{n}.py` | — | — |\n"
        for n in range(1, 4))
    code, out = _slice(tmp_path, part="1", rows=rows)
    assert code == 0, out
    assert "BLOCKED" not in out
