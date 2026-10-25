"""plan_doc: the one markdown/ledger parser plan_lint.py and plan_slice.py share (v193)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("plan_doc", ROOT / "scripts" / "dev" / "plan_doc.py")
plan_doc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plan_doc)

LEDGER = (
    "# v900 Demo\n\n## Goal\n\nWhy.\n\n## Task ledger\n\n"
    "| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| V900-1 | Parser | 1 | sonnet | C | C `scripts/dev/x.py` | `f(x) -> Path \\| None`; `K = 1` | — |\n"
    "| V900-2 | Use it | 2 | haiku | A; § Model tier | M `scripts/dev/x.py` | — | `f` |\n"
    "| V900-3 | Short |\n"
    "\n## After\n\ntext\n"
)


def test_backticked():
    assert plan_doc.backticked("C `a/b.py`, `c.py`, ` d ` and ` `") == ["a/b.py", "c.py", "d"]
    assert plan_doc.backticked("no ticks") == []


def test_sections_level2_stops_at_same_or_higher_and_skips_fences():
    text = ("# Title\n\n## A. One\n\nbody\n\n```bash\n# not a heading\n## nor this\n```\n\n"
            "### Sub\n\nsub body\n\n## B\n\nb body\n\n# Phase 2\n\n## C\n")
    got = plan_doc.sections(text)
    assert list(got) == ["A. One", "B", "C"]
    assert got["A. One"].startswith("## A. One\n")
    assert "# not a heading" in got["A. One"] and "sub body" in got["A. One"]
    assert "## B" not in got["A. One"]
    assert got["B"] == "## B\n\nb body\n"
    assert got["C"] == "## C\n"


def test_sections_other_level_and_duplicate_heading():
    text = "## X\n\n### Sub\n\none\n\n### Sub\n\ntwo\n\n## Y\n"
    got = plan_doc.sections(text, level=3)
    assert got == {"Sub": "### Sub\n\none\n"}


def test_ledger_rows_keyed_by_header():
    rows = plan_doc.ledger_rows(LEDGER)
    assert [r[plan_doc.COL_TASK] for r in rows] == ["V900-1", "V900-2", "V900-3"]
    assert rows[1][plan_doc.COL_SPEC] == "A; § Model tier"
    assert rows[1][plan_doc.COL_FILES] == "M `scripts/dev/x.py`"
    assert rows[1][plan_doc.COL_CONSUMES] == "`f`"
    assert rows[2][plan_doc.COL_PART] == "" and rows[2][plan_doc.COL_CONSUMES] == ""


def test_ledger_rows_escaped_pipe():
    row = plan_doc.ledger_rows(LEDGER)[0]
    assert row[plan_doc.COL_CREATES] == "`f(x) -> Path | None`; `K = 1`"
    assert row[plan_doc.COL_CONSUMES] == "—"


def test_ledger_rows_empty_when_no_ledger_or_no_table():
    assert plan_doc.ledger_rows("# v900\n\n## Goal\n\nx\n") == []
    assert plan_doc.ledger_rows("## Task ledger\n\nnone yet\n") == []


def test_spec_refs():
    assert plan_doc.spec_refs("A; § Model tier, C") == ["A", "Model tier", "C"]
    assert plan_doc.spec_refs("§Testing") == ["Testing"]
    for empty in ("", "—", "-", " – "):
        assert plan_doc.spec_refs(empty) == []


HEADINGS = ["Why", "A. Split right the first time (agreed 2026-10-25)",
            "Model tier for prose parts", "Testing", "AB. Other"]


@pytest.mark.parametrize("ref, want", [
    ("Testing", "Testing"),
    ("A", "A. Split right the first time (agreed 2026-10-25)"),
    ("Model tier", "Model tier for prose parts"),
    ("AB", "AB. Other"),
    ("B", None),
    ("Test", None),
])
def test_resolve_ref(ref, want):
    assert plan_doc.resolve_ref(ref, HEADINGS) == want


def test_spec_path_link_relative_backticked_and_missing(tmp_path, monkeypatch):
    plans, specs = tmp_path / "plans", tmp_path / "specs"
    plans.mkdir()
    specs.mkdir()
    (specs / "s.md").write_text("# s\n", encoding="utf-8")
    index = plans / "i.md"
    link = "**Bump:** none\n**Spec:** [s.md](../specs/s.md#why)\n"
    assert plan_doc.spec_path(index, link) == (specs / "s.md").resolve()
    monkeypatch.chdir(tmp_path)
    assert plan_doc.spec_path(index, "**Spec:** `specs/s.md`\n") == (specs / "s.md").resolve()
    assert plan_doc.spec_path(index, "**Spec:** [x](../specs/gone.md)\n") is None
    assert plan_doc.spec_path(index, "no spec line\n") is None


@pytest.mark.parametrize("token, want", [
    ("backticked(cell: str) -> list[str]", "backticked"),
    ("plan_lint.plan_number", "plan_number"),
    ("tests/dev/test_x.py::test_a", "tests/dev/test_x.py::test_a"),
    ("scripts/dev/plan_slice.py <index> <part>", "scripts/dev/plan_slice.py"),
    ("--ledger <index>", "--ledger"),
    ("--stats", "--stats"),
    ("COMMANDS: dict[str, Callable[[list[str]], int]]", "COMMANDS"),
    ("NEW_RULES_FROM = 194", "NEW_RULES_FROM"),
    ("mod::Cls.method(x)", "method"),
    ("f(x) -> Path | None", "f"),
    ("  ", ""),
])
def test_symbol_name(token, want):
    assert plan_doc.symbol_name(token) == want


def test_real_v193_index_ledger_resolves_against_its_spec():
    index = ROOT / "docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md"
    text = index.read_text(encoding="utf-8")
    rows = plan_doc.ledger_rows(text)
    assert [r[plan_doc.COL_TASK] for r in rows][:2] == ["V193-1", "V193-2"]
    spec = plan_doc.spec_path(index, text)
    assert spec is not None and spec.name == "2026-10-25-v193-plan-writer-pipeline.md"
    headings = list(plan_doc.sections(spec.read_text(encoding="utf-8")))
    for row in rows:
        for ref in plan_doc.spec_refs(row[plan_doc.COL_SPEC]):
            assert plan_doc.resolve_ref(ref, headings), (row[plan_doc.COL_TASK], ref)
