"""Generate Codex's copy of the Claude setup, or check that it is current.

Claude is the operator on this repo and its setup is canonical; Codex gets a
generated mirror so both agents run the same skills and role agents:

    .claude/skills/<n>/SKILL.md  ->  .agents/skills/<n>/SKILL.md
                                     (+ agents/openai.yaml for slash-only skills)
    .claude/agents/<n>.md        ->  .codex/agents/<n>.toml

Hooks (`.codex/hooks.json`) and `AGENTS.md` are hand-maintained; `--check`
verifies they still reference every Claude skill, agent, reference doc and the
guardrail hook. tests/hooks/test_codex_mirror.py runs `--check`, so a Claude
setup change that skipped this script fails the suite.

    python scripts/dev/sync_codex.py           # regenerate
    python scripts/dev/sync_codex.py --check   # exit 1 and list drift
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CLAUDE_AGENTS = ROOT / ".claude" / "agents"
CODEX_SKILLS = ROOT / ".agents" / "skills"
CODEX_AGENTS = ROOT / ".codex" / "agents"
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
AGENTS_MD = ROOT / "AGENTS.md"
REFERENCE_DOCS = ROOT / "docs" / "claude"

_IMPLICIT_OFF = "policy:\n  allow_implicit_invocation: false\n"

# Claude model tier -> (Codex model, model_reasoning_effort). The one place a
# tier is translated; AGENTS.md carries the same table for Model: stamps and
# expert-role reviewers dispatched from Codex.
CODEX_TIERS = {
    "haiku": ("gpt-6-luna", "low"),
    "sonnet": ("gpt-6.1-sol", "medium"),
    "opus": ("gpt-6-astra", "high"),
}


def _banner(source: str) -> str:
    return (f"GENERATED from {source} by scripts/dev/sync_codex.py -- edit the "
            "source, then re-run the script. Never edit this copy.")


def _split_frontmatter(text: str):
    """Return ({key: value}, body) for a `---`-fenced markdown file."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            meta[key.strip()] = value.strip()
    return meta, body


def _skill_outputs(skill_md: pathlib.Path) -> dict:
    meta, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = skill_md.parent.name
    source = skill_md.relative_to(ROOT).as_posix()
    text = (f"---\nname: {meta.get('name', name)}\n"
            f"description: {meta.get('description', '')}\n---\n"
            f"<!-- {_banner(source)} -->\n{body}")
    out = {CODEX_SKILLS / name / "SKILL.md": text}
    if meta.get("disable-model-invocation") == "true":
        out[CODEX_SKILLS / name / "agents" / "openai.yaml"] = (
            f"# {_banner(source)}\n{_IMPLICIT_OFF}")
    return out


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # JSON strings are valid TOML


def _agent_outputs(agent_md: pathlib.Path) -> dict:
    meta, body = _split_frontmatter(agent_md.read_text(encoding="utf-8"))
    source = agent_md.relative_to(ROOT).as_posix()
    name = meta.get("name", agent_md.stem)
    model, effort = CODEX_TIERS[meta.get("model", "sonnet")]
    text = (f"# {_banner(source)}\n"
            f"name = {_toml_string(name)}\n"
            f"description = {_toml_string(meta.get('description', ''))}\n"
            f"model = {_toml_string(model)}\n"
            f"model_reasoning_effort = {_toml_string(effort)}\n"
            f"developer_instructions = {_toml_string(body.strip() + chr(10))}\n")
    return {CODEX_AGENTS / f"{agent_md.stem}.toml": text}


def expected_files() -> dict:
    """Every generated path mapped to the content it must have."""
    out = {}
    for skill_md in sorted(CLAUDE_SKILLS.glob("*/SKILL.md")):
        out.update(_skill_outputs(skill_md))
    for agent_md in sorted(CLAUDE_AGENTS.glob("*.md")):
        out.update(_agent_outputs(agent_md))
    return out


def _generated_on_disk() -> set:
    found = set(CODEX_SKILLS.glob("*/SKILL.md"))
    found |= set(CODEX_SKILLS.glob("*/agents/openai.yaml"))
    found |= set(CODEX_AGENTS.glob("*.toml"))
    return found


def _stale_generated(expected: dict) -> list:
    problems = []
    for path, text in expected.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current is None or current.replace("\r\n", "\n") != text:
            problems.append(f"stale or missing: {path.relative_to(ROOT).as_posix()}")
    for path in sorted(_generated_on_disk() - set(expected)):
        problems.append(f"orphan (source deleted): {path.relative_to(ROOT).as_posix()}")
    return problems


def _missing_mentions() -> list:
    """Hand-maintained files must still name everything Claude has."""
    agents_md = AGENTS_MD.read_text(encoding="utf-8")
    names = [p.parent.name for p in CLAUDE_SKILLS.glob("*/SKILL.md")]
    names += [p.stem for p in CLAUDE_AGENTS.glob("*.md")]
    names += [p.name for p in REFERENCE_DOCS.glob("*.md")]
    problems = [f"AGENTS.md never mentions `{n}`" for n in sorted(names)
                if f"`{n}`" not in agents_md and f"docs/claude/{n}" not in agents_md]
    hooks = CODEX_HOOKS.read_text(encoding="utf-8") if CODEX_HOOKS.exists() else ""
    if ".claude/hooks/guardrails.py" not in hooks:
        problems.append(".codex/hooks.json does not run .claude/hooks/guardrails.py")
    return problems


def check() -> list:
    return _stale_generated(expected_files()) + _missing_mentions()


def write() -> None:
    expected = expected_files()
    for path in _generated_on_disk() - set(expected):
        path.unlink()
    for path, text in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list) -> int:
    if "--check" not in argv:
        write()
    problems = check()
    for line in problems:
        print(line)
    if problems:
        print("Codex mirror is out of date: run python scripts/dev/sync_codex.py, "
              "then fix AGENTS.md / .codex/hooks.json by hand.")
        return 1
    print("Codex mirror is current.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
