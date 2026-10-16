"""The trade-scout skill, the scout agent and their docs section (v161 TS11).

Pinned: serial dispatch, the merge command, the partner gate before the
production export, the panel step, the partner's pick, the removal
condition, the read-only agent, and the one place the thresholds live."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

SKILL = ROOT / ".claude" / "skills" / "trade-scout" / "SKILL.md"
AGENT = ROOT / ".claude" / "agents" / "scout.md"
SKILLS_TOOLS = ROOT / "docs" / "claude" / "skills-tools.md"
GENERATORS = ("exit-harvester", "setup-scout", "regime-desk")


def _parsed(path):
    return parse_frontmatter(path.read_text(encoding="utf-8").replace("\r\n", "\n"))


def _section(text, heading):
    start = text.index(heading + "\n") + len(heading)
    end = text.find("\n## ", start)
    return text[start:] if end == -1 else text[start:end]


SKILL_PHRASES = (
    "serially", "never in parallel", "`scout`",
    "python scripts/dev/scout_merge.py", "--autopsy",
    "python scripts/reports/book_autopsy.py", "scripts/ops/export_book_rows.sh",
    "scripts/ops/ssh-hetzner.sh", "AskUserQuestion", "premarket", "scratchpad",
    "/panel quant-researcher", "## Panel review", "/screen", "/prereg",
    "starts neither", "three consecutive slates", "## role: <name>",
    "`docs/claude/skills-tools.md` § Generator roles (v161)",
)


def test_trade_scout_skill_names_every_step():
    meta, body = _parsed(SKILL)
    assert meta["name"] == "trade-scout"
    missing = [p for p in SKILL_PHRASES if p not in body]
    assert not missing, missing
    for role in GENERATORS:
        assert f"`{role}`" in body, role


def test_trade_scout_never_edits_gates_or_runs_paid_work():
    _, body = _parsed(SKILL)
    for phrase in ("No gate moves", "closed pre-registration", "`SCREEN-PASS`", "No paid usage"):
        assert phrase in body, phrase


def test_scout_agent_is_read_only_and_knows_its_roles():
    meta, body = _parsed(AGENT)
    tools = {t.strip() for t in meta["tools"].split(",")}
    assert tools == {"Read", "Grep", "Glob", "Skill"}
    assert meta["model"] == "sonnet"
    for role in GENERATORS:
        assert f"`{role}`" in body, role
    for word in ("NO ROWS", "UNKNOWN ROLE", "BLOCKED:", "## Return shape",
                 "playbook.md", "never decide", "never lower a gate", "`pooled-numbers`"):
        assert word in body, word


def test_docs_section_holds_the_thresholds_and_the_agent_row():
    text = SKILLS_TOOLS.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.index("## Expert roles (v145)") < text.index("## Generator roles (v161)") \
        < text.index("## Which agent for what (v107)")
    section = _section(text, "## Generator roles (v161)")
    for phrase in ("q ≤ 0.10", "N < 30", "fewer than 8 distinct ISO weeks", "THIN_MIN_N",
                   "THIN_MIN_WEEKS", "exploratory: yes", "contaminated", "three consecutive slates",
                   "`SCREEN-PASS`", "`/trade-scout`", "`scout`"):
        assert phrase in section, phrase
    for role in GENERATORS:
        assert f"`{role}`" in section, role
    agents = _section(text, "## Which agent for what (v107)")
    assert "| `scout` | sonnet |" in agents
