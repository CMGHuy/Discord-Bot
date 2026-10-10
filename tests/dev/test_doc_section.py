"""doc_section prints named sections of a doc, and refuses rather than guess."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "doc_section.py"

DOC = """\
# Title

intro, before any section

## Alpha one

alpha body

### Alpha child

child body

## Beta — dash

beta body

```text
## not a heading
```

### Gamma

gamma body
#### deeper stays body

## alpha two

last body
"""


def _run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          cwd=ROOT, timeout=60)
    assert proc.stderr == b"", proc.stderr
    return proc.returncode, proc.stdout.decode("utf-8")


def _doc(tmp_path: Path, text: str = DOC) -> str:
    path = tmp_path / "doc.md"
    path.write_bytes(text.encode("utf-8"))
    return str(path)


def _between(start: str, end: str | None = None) -> str:
    """The slice of DOC from one heading line up to another (or to the end)."""
    stop = DOC.index(end) if end else len(DOC)
    return DOC[DOC.index(start):stop]


LISTING = [
    "## Alpha one",
    "### Alpha child",
    "## Beta — dash",
    "### Gamma",
    "## alpha two",
]


def test_no_heading_lists_every_heading_with_its_section_size(tmp_path):
    code, out = _run(_doc(tmp_path))
    sizes = [
        len(_between("## Alpha one", "## Beta").encode("utf-8")),
        len(_between("### Alpha child", "## Beta").encode("utf-8")),
        len(_between("## Beta", "## alpha two").encode("utf-8")),
        len(_between("### Gamma", "## alpha two").encode("utf-8")),
        len(_between("## alpha two").encode("utf-8")),
    ]
    width = len(str(max(sizes)))
    assert code == 0
    assert out.splitlines() == [f"{size:>{width}}  {line}"
                                for size, line in zip(sizes, LISTING)]


def test_listing_right_aligns_sizes_of_different_widths(tmp_path):
    text = "## Small\n\nx\n\n## Large\n\n" + "y" * 200 + "\n"
    code, out = _run(_doc(tmp_path, text))
    assert code == 0
    assert out.splitlines() == [" 13  ## Small", "211  ## Large"]


def test_heading_matches_by_case_insensitive_prefix(tmp_path):
    code, out = _run(_doc(tmp_path), "BETA")
    assert code == 0
    assert out == _between("## Beta", "## alpha two").rstrip() + "\n"


def test_h2_section_includes_its_h3_children(tmp_path):
    code, out = _run(_doc(tmp_path), "Alpha one")
    assert code == 0
    assert out == _between("## Alpha one", "## Beta").rstrip() + "\n"
    assert "### Alpha child" in out


def test_h3_section_is_addressable_and_stops_at_the_next_heading(tmp_path):
    code, out = _run(_doc(tmp_path), "gamma")
    assert code == 0
    assert out == "### Gamma\n\ngamma body\n#### deeper stays body\n"


def test_several_headings_print_in_the_order_asked_one_blank_line_apart(tmp_path):
    code, out = _run(_doc(tmp_path), "alpha two", "Alpha child")
    assert code == 0
    assert out == "## alpha two\n\nlast body\n\n### Alpha child\n\nchild body\n"


def test_ambiguous_heading_exits_2_with_the_heading_list_and_no_section(tmp_path):
    code, out = _run(_doc(tmp_path), "Beta", "alpha")
    lines = out.splitlines()
    assert code == 2
    assert lines[0] == "doc_section: 'alpha' is ambiguous"
    assert [line.split("  ", 1)[1] for line in lines[1:]] == LISTING
    assert "beta body" not in out


def test_missing_heading_exits_2_with_the_heading_list_and_no_section(tmp_path):
    code, out = _run(_doc(tmp_path), "Beta", "Delta")
    lines = out.splitlines()
    assert code == 2
    assert lines[0] == "doc_section: no heading starts with 'Delta'"
    assert [line.split("  ", 1)[1] for line in lines[1:]] == LISTING
    assert "beta body" not in out


def test_heading_inside_a_code_fence_is_not_a_heading(tmp_path):
    code, out = _run(_doc(tmp_path), "not a heading")
    assert code == 2
    assert out.splitlines()[0] == "doc_section: no heading starts with 'not a heading'"


def test_h1_and_h4_are_not_addressable(tmp_path):
    assert _run(_doc(tmp_path), "Title")[0] == 2
    assert _run(_doc(tmp_path), "deeper")[0] == 2


def test_doc_without_headings_exits_2_and_says_to_read_the_file(tmp_path):
    doc = _doc(tmp_path, "# Only a title\n\n- **bold bullet**, no sections\n")
    expected = f"doc_section: {doc} has no ## or ### headings -- read the file\n"
    assert _run(doc) == (2, expected)
    assert _run(doc, "bold") == (2, expected)


def test_missing_file_exits_2(tmp_path):
    doc = str(tmp_path / "absent.md")
    assert _run(doc, "Alpha") == (2, f"doc_section: cannot read {doc}\n")


def test_no_arguments_exits_2_with_usage():
    code, out = _run()
    assert code == 2
    assert out.startswith("doc_section: usage:")


def test_crlf_doc_prints_the_same_sections(tmp_path):
    doc = _doc(tmp_path, DOC.replace("\n", "\r\n"))
    code, out = _run(doc, "gamma")
    assert code == 0
    assert out == "### Gamma\n\ngamma body\n#### deeper stays body\n"


def test_real_doc_section_is_printed_from_its_heading_line():
    """The one case run against a real doc: a heading that predates v154 and
    that two other tests read, so it is safe to rely on here."""
    code, out = _run("docs/claude/backtest-methodology.md", "closed pre-registrations")
    assert code == 0
    assert out.splitlines()[0] == "### Closed pre-registrations — do not re-run these"
