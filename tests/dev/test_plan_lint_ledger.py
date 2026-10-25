"""plan_lint --ledger: the index's contracts hold before any part is written (v193)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"
INDEX = "2026-10-25-v900-demo_0-index.md"
SPEC = "# v900 spec\n\n## A. Alpha\n\nalpha body\n\n## Testing\n\nunit tests\n"
LEDGER_HEAD = ("| Task | Title | Part | Model | Spec § | Files created / modified "
               "| Creates | Consumes |\n|---|---|---|---|---|---|---|---|\n")
# Built at run time so `git grep` never finds these names in this very file.
GHOST = "ghost" + "_v900_" + "symbol"
FLAG = "--" + "frob" + "v900"


def _row(task, spec="A", files="—", creates="—", consumes="—", title="t"):
    return f"| {task} | {title} | 1 | sonnet | {spec} | {files} | {creates} | {consumes} |\n"


def _index(rows: str, spec_link: str = "spec.md", head: str = LEDGER_HEAD) -> str:
    return ("# v900 Demo (index)\n\n**Bump:** none\n**Edge:** none (integrity)\n"
            f"**Spec:** [spec]({spec_link})\n\n## Parallelisation\n\nSerial.\n\n"
            "## Task ledger\n\n" + head + rows + "\n")


def _check(tmp_path, rows: str, spec_link: str = "spec.md",
           head: str = LEDGER_HEAD) -> tuple[int, str]:
    (tmp_path / "spec.md").write_text(SPEC, encoding="utf-8")
    index = tmp_path / INDEX
    index.write_text(_index(rows, spec_link, head), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--ledger", str(index)],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


def test_ledger_passes_when_contracts_hold(tmp_path):
    rows = (_row("V900-1", files="C `scripts/dev/v900_tool.py`",
                 creates="`alpha_fn(x: int) -> Path \| None`; `TABLE: dict[str, int]`")
            + _row("V900-2", spec="A; Testing",
                   consumes="`alpha_fn`, `TABLE`, `plan_lint.plan_files`, "
                            "`scripts/dev/v900_tool.py`"))
    code, out = _check(tmp_path, rows)
    assert code == 0, out
    assert "LEDGER CHECK: PASS  2 row(s), 0 problem(s)" in out


def test_ledger_flag_named_in_earlier_title_counts(tmp_path):
    rows = (_row("V900-1", title=f"`v900_tool.py {FLAG} <x>`")
            + _row("V900-2", consumes=f"`{FLAG}`"))
    code, out = _check(tmp_path, rows)
    assert code == 0, out


def test_ledger_consumed_before_creation(tmp_path):
    rows = (_row("V900-1", consumes=f"`{GHOST}`")
            + _row("V900-2", creates=f"`{GHOST}() -> None`"))
    code, out = _check(tmp_path, rows)
    assert code == 1
    assert f"ledger: V900-1 consumes `{GHOST}`, created only by later row V900-2" in out
    assert "LEDGER CHECK: FAIL  2 row(s), 1 problem(s)" in out


def test_ledger_unknown_symbol(tmp_path):
    code, out = _check(tmp_path, _row("V900-1", consumes=f"`{GHOST}`"))
    assert code == 1
    assert (f"ledger: V900-1 consumes `{GHOST}`: neither in the repo nor "
            "created by an earlier row") in out


def test_ledger_unresolved_spec_ref(tmp_path):
    code, out = _check(tmp_path, _row("V900-1", spec="A; Q"))
    assert code == 1
    assert "ledger: V900-1 Spec § 'Q' matches no heading in spec.md" in out
    assert "1 problem(s)" in out


def test_ledger_empty_spec_cell(tmp_path):
    code, out = _check(tmp_path, _row("V900-1", spec="—"))
    assert code == 1
    assert "ledger: V900-1 has no Spec § reference" in out


def test_ledger_without_rows(tmp_path):
    code, out = _check(tmp_path, "")
    assert code == 1
    assert "ledger: no rows under ## Task ledger" in out
    assert "LEDGER CHECK: FAIL  0 row(s), 1 problem(s)" in out


def test_ledger_spec_file_not_found(tmp_path):
    code, out = _check(tmp_path, _row("V900-1"), spec_link="missing.md")
    assert code == 1
    assert "ledger: spec file not found" in out


def test_ledger_pre_v193_columns(tmp_path):
    old = ("| Task | Title | Part | Model | Files created / modified "
           "| Creates (consumed later) |\n|---|---|---|---|---|---|\n")
    code, out = _check(tmp_path, "| V900-1 | t | 1 | sonnet | — | — |\n", head=old)
    assert code == 1
    for column in ("Spec §", "Creates", "Consumes"):
        assert f"ledger: no `{column}` column" in out


def test_ledger_usage(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--ledger"],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 2
    assert "--ledger <index>" in proc.stdout
