"""v213 § A: the citation lint over skills, agents and eval prompts.

Unit cases build tiny repos on tmp_path and call the pure scanner in
scripts/dev/skill_citations.py directly. Fixture names below are made up on
purpose and must never be cited by a real skill: this file is part of the
code text the config-name rule searches.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# scripts/dev has no __init__.py: put it on sys.path, then import the module.
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import skill_citations as sc  # noqa: E402


def _write(root: Path, rel: str, text: str, *, crlf: bool = False) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(data.encode("utf-8"))
    return path


def _skill(root: Path, text: str, name: str = "demo", *, crlf: bool = False) -> Path:
    return _write(root, f".claude/skills/{name}/SKILL.md", text, crlf=crlf)


def _scan(root: Path, text: str, tracked=(), code_text: str = "", *, crlf: bool = False):
    path = _skill(root, text, crlf=crlf)
    return sc.scan(root, [path], set(tracked), code_text)


def _rows(findings):
    return [(f.line, f.token, f.reason) for f in findings]


# --- paths -----------------------------------------------------------------

def test_missing_path_is_reported(tmp_path):
    assert _rows(_scan(tmp_path, "see `scripts/dev/gone.py`\n")) == [
        (1, "scripts/dev/gone.py", sc.REASON_MISSING)]


def test_tracked_root_path_passes(tmp_path):
    assert _scan(tmp_path, "see `scripts/dev/here.py`\n", {"scripts/dev/here.py"}) == []


@pytest.mark.parametrize("word, tracked", [
    ("commands/x.py", "swingbot/commands/x.py"),
    ("scanning/x.py", "swingbot/core/scanning/x.py")])
def test_path_found_only_by_one_fallback_root_passes(tmp_path, word, tracked):
    assert _scan(tmp_path, f"see `{word}`\n", {tracked}) == []


def test_two_fallback_candidates_are_ambiguous(tmp_path):
    tracked = {"swingbot/scanning/x.py", "swingbot/core/scanning/x.py"}
    assert _rows(_scan(tmp_path, "see `scanning/x.py`\n", tracked)) == [
        (1, "scanning/x.py", sc.REASON_AMBIGUOUS)]


def test_wrong_case_path_is_missing(tmp_path):
    findings = _scan(tmp_path, "see `swingbot/Config.py`\n", {"swingbot/config.py"})
    assert _rows(findings) == [(1, "swingbot/Config.py", sc.REASON_MISSING)]


@pytest.mark.parametrize("span", [
    "swingbot/<name>.py", "swingbot/**/*.py", "docs/{a,b}.md", "$ROOT/x.py",
    "k=v/a.py", "https://example.com/a.md", "logs/<plan>-rows/{x}.jsonl"])
def test_template_words_are_skipped(tmp_path, span):
    assert _scan(tmp_path, f"run `{span}`\n") == []


@pytest.mark.parametrize("span", [
    "scripts/a.py::test_x", "scripts/a.py:12", "scripts/a.py:12-30",
    "scripts/a.py),", "scripts/a.py.", "scripts/a.py::Klass::method"])
def test_symbol_and_line_suffixes_are_stripped(tmp_path, span):
    assert _scan(tmp_path, f"see `{span}`\n", {"scripts/a.py"}) == []


def test_several_paths_in_one_multi_word_span(tmp_path):
    text = "run `python scripts/a.py scripts/gone.py tests/x.py`\n"
    assert _rows(_scan(tmp_path, text, {"scripts/a.py", "tests/x.py"})) == [
        (1, "scripts/gone.py", sc.REASON_MISSING)]


def test_two_citations_on_one_line_are_two_tokens(tmp_path):
    text = "see `scripts/a.py` and `scripts/b.py`\n"
    assert _rows(_scan(tmp_path, text)) == [
        (1, "scripts/a.py", sc.REASON_MISSING), (1, "scripts/b.py", sc.REASON_MISSING)]


def test_fenced_blocks_are_skipped(tmp_path):
    text = ("```bash\npython `scripts/a.py`\n```\n"
            "~~~\n`scripts/b.py`\n~~~\n"
            "`scripts/c.py`\n")
    assert _rows(_scan(tmp_path, text)) == [(7, "scripts/c.py", sc.REASON_MISSING)]


def test_prose_lines_numbers_from_one_and_skips_fences():
    lines = ["a", "```", "b", "~~~", "still fenced", "```", "c"]
    assert list(sc.prose_lines(lines)) == [(1, "a"), (7, "c")]


def test_crlf_file_behaves_like_lf(tmp_path):
    findings = _scan(tmp_path, "intro\n`scripts/a.py`\n", crlf=True)
    assert _rows(findings) == [(2, "scripts/a.py", sc.REASON_MISSING)]


@pytest.mark.parametrize("word", [
    ".superpowers/briefs/x.md", "logs/run.jsonl", "data/journal.json", "market_data/x.json"])
def test_runtime_prefixes_are_skipped(tmp_path, word):
    assert _scan(tmp_path, f"see `{word}`\n") == []


@pytest.mark.parametrize("word", ["foo.py", "swingbot/core/", "swingbot/x.csv", "a/b"])
def test_words_that_are_not_paths_are_ignored(tmp_path, word):
    assert _scan(tmp_path, f"see `{word}`\n") == []


def test_span_words_cleans_and_drops_templates():
    line = "x `python scripts/a.py:3 <id>` y `docs/b.md),`"
    assert sc.span_words(line) == ["python", "scripts/a.py", "docs/b.md"]


# --- scan set and order ----------------------------------------------------

def test_scan_set_covers_skills_agents_and_eval_prompts(tmp_path):
    rels = [".claude/skills/x/SKILL.md", ".claude/skills/x/evals/fire-a/prompt.md",
            ".claude/skills/x/evals/fire-a/graders/skill-fired.md", ".claude/agents/y.md",
            ".agents/skills/x/SKILL.md", ".claude/skills/x/notes.md"]
    for rel in rels:
        _write(tmp_path, rel, "text\n")
    _write(tmp_path, ".claude/agents/untracked.md", "text\n")
    tracked = set(rels) | {".claude/agents/deleted.md"}
    got = [p.relative_to(tmp_path).as_posix() for p in sc.scan_set(tmp_path, tracked)]
    assert got == [".claude/agents/y.md", ".claude/skills/x/SKILL.md",
                   ".claude/skills/x/evals/fire-a/prompt.md"]


def test_findings_keep_file_order_then_line_order(tmp_path):
    first = _write(tmp_path, ".claude/skills/b/SKILL.md", "`scripts/b1.py`\n\n`scripts/b2.py`\n")
    second = _write(tmp_path, ".claude/agents/a.md", "`scripts/a1.py`\n")
    got = [(f.file, f.line) for f in sc.scan(tmp_path, [first, second], set(), "")]
    assert got == [(".claude/skills/b/SKILL.md", 1), (".claude/skills/b/SKILL.md", 3),
                   (".claude/agents/a.md", 1)]


@pytest.mark.parametrize("rel, skill", [
    (".claude/skills/task-brief/SKILL.md", "task-brief"),
    (".claude/skills/edge-module/evals/fire-x/prompt.md", "edge-module"),
    (".claude/agents/prod-inspector.md", "prod-inspector")])
def test_skill_of(rel, skill):
    assert sc.skill_of(rel) == skill


# --- allowlist -------------------------------------------------------------

ALLOWLIST = """# reviewed mentions of removed or uncommitted things

demo|scripts/kept.py|deleted on purpose, named as history
   # an indented comment
demo|scripts/never.py|no longer cited anywhere
"""


def test_allowlist_skips_comments_and_blank_lines(tmp_path):
    path = _write(tmp_path, "allow.txt", ALLOWLIST)
    entries = sc.load_allowlist(path)
    assert [(e.skill, e.token, e.line) for e in entries] == [
        ("demo", "scripts/kept.py", 3), ("demo", "scripts/never.py", 5)]
    assert entries[0].reason == "deleted on purpose, named as history"


def test_missing_allowlist_is_empty(tmp_path):
    assert sc.load_allowlist(tmp_path / "absent.txt") == []


@pytest.mark.parametrize("bad", ["demo|only-two", "demo||reason", "no separators"])
def test_malformed_allowlist_line_raises(tmp_path, bad):
    path = _write(tmp_path, "allow.txt", f"{bad}\n")
    with pytest.raises(ValueError, match="allow.txt:1"):
        sc.load_allowlist(path)


def test_allowlisted_token_is_removed_and_dead_line_reported(tmp_path):
    findings = _scan(tmp_path, "`scripts/kept.py` `scripts/other.py`\n")
    entries = sc.load_allowlist(_write(tmp_path, "allow.txt", ALLOWLIST))
    remaining, dead = sc.apply_allowlist(findings, entries)
    assert [f.token for f in remaining] == ["scripts/other.py"]
    assert [(e.token, e.line) for e in dead] == [("scripts/never.py", 5)]


def test_one_allowlist_line_covers_every_occurrence_in_its_skill(tmp_path):
    findings = _scan(tmp_path, "`scripts/kept.py`\n\n`scripts/kept.py`\n")
    entries = sc.load_allowlist(_write(tmp_path, "allow.txt", ALLOWLIST))
    remaining, _ = sc.apply_allowlist(findings, entries)
    assert remaining == []


def test_allowlist_matches_the_skill_exactly(tmp_path):
    path = _write(tmp_path, ".claude/skills/other/SKILL.md", "`scripts/kept.py`\n")
    findings = sc.scan(tmp_path, [path], set(), "")
    entries = sc.load_allowlist(_write(tmp_path, "allow.txt", ALLOWLIST))
    remaining, _ = sc.apply_allowlist(findings, entries)
    assert [f.token for f in remaining] == ["scripts/kept.py"]


# --- output ----------------------------------------------------------------

def test_output_format_is_exact(tmp_path):
    (finding,) = _scan(tmp_path, "x\n\nsee `scripts/gone.py`\n")
    assert finding.format() == ".claude/skills/demo/SKILL.md:3: scripts/gone.py -- missing"


# --- config names ----------------------------------------------------------

def test_unknown_config_name_is_reported(tmp_path):
    findings = _scan(tmp_path, "set `NOT_A_REAL_KNOB`\n", code_text="OTHER_FIXTURE_KNOB = 1")
    assert _rows(findings) == [(1, "NOT_A_REAL_KNOB", sc.REASON_UNKNOWN_NAME)]


def test_known_config_name_passes(tmp_path):
    code = "DEMO_FIXTURE_KNOB: int = 3\n"
    assert _scan(tmp_path, "set `DEMO_FIXTURE_KNOB`.\n", code_text=code) == []


def test_config_name_matches_a_whole_word_only(tmp_path):
    findings = _scan(tmp_path, "`DEMO_KNOB`\n", code_text="DEMO_KNOB_EXTRA = 1")
    assert _rows(findings) == [(1, "DEMO_KNOB", sc.REASON_UNKNOWN_NAME)]


@pytest.mark.parametrize("word", ["README", "ExpR", "A_b", "_PRIVATE", "HTTP2"])
def test_words_that_are_not_config_names_are_ignored(tmp_path, word):
    assert _scan(tmp_path, f"`{word}`\n") == []


def test_config_name_found_only_in_a_scripts_file_passes(tmp_path):
    _write(tmp_path, "scripts/dev/tool.py", "DEMO_SCRIPT_TABLE = ()\n")
    tracked = {"scripts/dev/tool.py"}
    code = sc.read_code_text(tmp_path, tracked)
    assert _scan(tmp_path, "`DEMO_SCRIPT_TABLE`\n", tracked, code) == []


def test_read_code_text_reads_only_tracked_python_under_the_code_roots(tmp_path):
    files = {"swingbot/a.py": "IN_SWINGBOT_X = 1", "tests/b.py": "IN_TESTS_X = 1",
             "scripts/c.py": "IN_SCRIPTS_X = 1", "frontend/d.py": "OUT_FRONTEND_X = 1",
             "swingbot/e.md": "OUT_MD_X", "swingbot/untracked.py": "OUT_UNTRACKED_X"}
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    tracked = (set(files) - {"swingbot/untracked.py"}) | {"swingbot/deleted.py"}
    code = sc.read_code_text(tmp_path, tracked)
    for name in ("IN_SWINGBOT_X", "IN_TESTS_X", "IN_SCRIPTS_X"):
        assert name in code
    for name in ("OUT_FRONTEND_X", "OUT_MD_X", "OUT_UNTRACKED_X"):
        assert name not in code


# --- doc sections ----------------------------------------------------------

FENCE = "`" * 3   # built, so no bare fence line sits inside this plan or file
DOC = (
    "# Title\n\n## Funnel stages\n\ntext\n\n"
    "### Closed pre-registrations — do not re-run these\n\n#### Deep heading\n\n"
    f"{FENCE}md\n## Fenced heading\n{FENCE}\n"
)
DOC_REL = "docs/claude/methods.md"


def _doc_scan(tmp_path, text):
    _write(tmp_path, DOC_REL, DOC)
    return _scan(tmp_path, text, {DOC_REL})


def test_doc_headings_are_levels_two_to_four_outside_fences():
    assert sc.doc_headings(DOC) == [
        "funnel stages", "closed pre-registrations — do not re-run these", "deep heading"]


@pytest.mark.parametrize("text", [
    "see `docs/claude/methods.md` § Funnel stages, stage two.\n",
    "see `methods.md` § Funnel stages\n",
    "see `methods.md` § Closed pre-registrations\n",
    "see `methods.md` § Closed pre-registrations — do not re-run these lists it.\n",
    "see `methods.md` § Deep heading).\n",
    "see `methods.md` § FUNNEL STAGES\n"])
def test_section_citation_to_a_real_heading_passes(tmp_path, text):
    assert _doc_scan(tmp_path, text) == []


def test_section_cite_wrapped_across_two_lines_passes(tmp_path):
    text = "see `methods.md` § Closed\npre-registrations — do not re-run these.\n"
    assert _doc_scan(tmp_path, text) == []


def test_missing_heading_is_reported_on_the_paragraphs_first_line(tmp_path):
    text = "intro\n\nfirst line\nsee `methods.md` § Stage two of the funnel.\n"
    assert _rows(_doc_scan(tmp_path, text)) == [
        (3, "methods.md § Stage two of the funnel", sc.REASON_MISSING_HEADING)]


@pytest.mark.parametrize("cite", ["Fenced heading", "Title"])
def test_fenced_and_level_one_headings_are_not_headings(tmp_path, cite):
    findings = _doc_scan(tmp_path, f"`methods.md` § {cite}\n")
    assert [f.reason for f in findings] == [sc.REASON_MISSING_HEADING]


def test_list_item_starts_a_new_paragraph(tmp_path):
    text = "- see `methods.md` § Closed pre-registrations\n- a second bullet\n"
    assert _doc_scan(tmp_path, text) == []


def test_missing_doc_with_a_slash_is_reported_by_both_rules(tmp_path):
    findings = _scan(tmp_path, "`docs/claude/gone.md` § Anything\n")
    assert _rows(findings) == [(1, "docs/claude/gone.md", sc.REASON_MISSING),
                               (1, "docs/claude/gone.md", sc.REASON_MISSING_DOC)]


def test_bare_doc_resolves_from_docs_claude(tmp_path):
    assert _rows(_scan(tmp_path, "`gone.md` § Anything\n")) == [
        (1, "gone.md", sc.REASON_MISSING_DOC)]


def test_paragraphs_break_on_blank_fence_and_list_item():
    lines = ["a", "b", "", "- c", "  d", "- e", "```", "f", "```", "g"]
    assert list(sc.paragraphs(lines)) == [(1, "a b"), (4, "- c d"), (6, "- e"), (10, "g")]


def test_eval_prompt_is_in_the_scan_set_and_scanned(tmp_path):
    rel = ".claude/skills/demo/evals/fire-x/prompt.md"
    _write(tmp_path, rel, "---\nmax_turns: 4\n---\n\nReview `swingbot/core/edge/imaginary.py`.\n")
    files = sc.scan_set(tmp_path, {rel})
    assert _rows(sc.scan(tmp_path, files, {rel}, "")) == [
        (5, "swingbot/core/edge/imaginary.py", sc.REASON_MISSING)]


# --- repo helpers and CLI --------------------------------------------------

def _git_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        _write(root, rel, text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def test_tracked_paths_reads_the_git_index(tmp_path):
    _git_repo(tmp_path, {"a/b.py": "x\n", ".claude/skills/x/SKILL.md": "x\n", "docs/ü.md": "x\n"})
    _write(tmp_path, "untracked.py", "x\n")
    assert sc.tracked_paths(tmp_path) == {"a/b.py", ".claude/skills/x/SKILL.md", "docs/ü.md"}


def test_repo_report_lists_findings_then_dead_lines(tmp_path):
    allow = "# header\nx|scripts/kept.py|named on purpose\nx|scripts/never.py|stale\n"
    _git_repo(tmp_path, {".claude/skills/x/SKILL.md": "`scripts/gone.py` `scripts/kept.py`\n",
                         sc.ALLOWLIST_REL: allow})
    assert sc.repo_report(tmp_path) == [
        ".claude/skills/x/SKILL.md:1: scripts/gone.py -- missing",
        "tests/hooks/skill_citation_allowlist.txt:3: x|scripts/never.py -- dead allowlist line"]


def test_main_exits_zero_on_a_clean_repo(tmp_path, capsys):
    _git_repo(tmp_path, {".claude/skills/x/SKILL.md": "`scripts/here.py`\n",
                         "scripts/here.py": "x = 1\n"})
    assert sc.main(["--root", str(tmp_path)]) == 0
    assert "clean" in capsys.readouterr().out


def test_main_exits_one_and_prints_each_finding(tmp_path, capsys):
    _git_repo(tmp_path, {".claude/skills/x/SKILL.md": "`scripts/gone.py`\n"})
    assert sc.main(["--root", str(tmp_path)]) == 1
    assert ".claude/skills/x/SKILL.md:1: scripts/gone.py -- missing" in capsys.readouterr().out
