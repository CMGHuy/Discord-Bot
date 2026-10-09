"""Codex runs a generated mirror of the Claude setup (AGENTS.md, .agents/skills/,
.codex/agents/, .codex/hooks.json). A Claude setup change that skipped
`python scripts/dev/sync_codex.py` fails here, which is what makes "every Claude
setup change also updates Codex" a gate rather than a habit."""
import importlib.util
import json
import pathlib

_ROOT = pathlib.Path(__file__).parent.parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "sync_codex", _ROOT / "scripts" / "dev" / "sync_codex.py")
sync_codex = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sync_codex)


def test_codex_mirror_is_current():
    problems = sync_codex.check()
    assert not problems, (
        "Codex mirror drifted -- run `python scripts/dev/sync_codex.py` and fix "
        "AGENTS.md / .codex/hooks.json:\n" + "\n".join(problems))


def test_every_claude_skill_and_agent_has_a_codex_copy():
    expected = {p.relative_to(_ROOT).as_posix() for p in sync_codex.expected_files()}
    for skill in (_ROOT / ".claude" / "skills").glob("*/SKILL.md"):
        assert f".agents/skills/{skill.parent.name}/SKILL.md" in expected
    for agent in (_ROOT / ".claude" / "agents").glob("*.md"):
        assert f".codex/agents/{agent.stem}.toml" in expected


def test_slash_only_skills_are_not_implicitly_invoked_by_codex():
    for skill in (_ROOT / ".claude" / "skills").glob("*/SKILL.md"):
        meta, _ = sync_codex._split_frontmatter(skill.read_text(encoding="utf-8"))
        policy = _ROOT / ".agents" / "skills" / skill.parent.name / "agents" / "openai.yaml"
        slash_only = meta.get("disable-model-invocation") == "true"
        assert policy.exists() == slash_only, skill.parent.name


def test_generated_agent_toml_parses_and_keeps_the_prompt():
    import tomllib
    for agent in (_ROOT / ".claude" / "agents").glob("*.md"):
        meta, body = sync_codex._split_frontmatter(agent.read_text(encoding="utf-8"))
        toml = _ROOT / ".codex" / "agents" / f"{agent.stem}.toml"
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
        assert data["name"] == meta["name"]
        assert data["description"] == meta["description"]
        assert data["developer_instructions"].strip() == body.strip()


def test_generated_agent_toml_carries_the_codex_tier_of_the_claude_model():
    """A Claude `model:` tier must reach Codex as a model and reasoning effort;
    without it every Codex agent silently runs on the session default."""
    import tomllib
    for agent in (_ROOT / ".claude" / "agents").glob("*.md"):
        meta, _ = sync_codex._split_frontmatter(agent.read_text(encoding="utf-8"))
        assert meta.get("model") in sync_codex.CODEX_TIERS, agent.name
        toml = _ROOT / ".codex" / "agents" / f"{agent.stem}.toml"
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
        model, effort = sync_codex.CODEX_TIERS[meta["model"]]
        assert (data["model"], data["model_reasoning_effort"]) == (model, effort)


def test_agents_md_documents_every_codex_tier():
    agents_md = (_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for tier, (model, effort) in sync_codex.CODEX_TIERS.items():
        assert f"| `{tier}` | `{model}` | `{effort}` |" in agents_md, tier


def test_codex_hooks_mirror_the_claude_guardrail_and_session_hooks():
    claude = json.loads((_ROOT / ".claude" / "settings.json").read_text())["hooks"]
    codex = json.loads((_ROOT / ".codex" / "hooks.json").read_text())["hooks"]
    claude_pre = {h["command"] for e in claude["PreToolUse"] for h in e["hooks"]}
    codex_pre = {h["command"] for e in codex["PreToolUse"] for h in e["hooks"]}
    assert claude_pre == codex_pre
    codex_start = {h["command"] for e in codex["SessionStart"] for h in e["hooks"]}
    assert "pwsh -NoProfile -File .claude/hooks/session-cursor.ps1" in codex_start
