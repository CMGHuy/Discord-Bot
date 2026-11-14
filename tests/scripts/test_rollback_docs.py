"""The rollback rules are written where a migration author and an operator look
(v220 spec, Repo bookkeeping; moved to v221 V221-4)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_schema_evolution_states_the_rollback_rules():
    text = _read("docs/claude/schema-evolution.md")
    section = text[text.index("## Rollback safety (v220)"):]
    for needle in ("ROLLBACK_SAFE", "INCOMPATIBLE_BOUNDARIES", "scripts/ops/rollback_migrations.py",
                   "scripts/ops/rollback_plan.py", "op.get_bind()"):
        assert needle in section


def test_the_schema_change_gate_names_both_rollback_markers():
    text = _read(".claude/skills/schema-change/SKILL.md")
    gate = text[text.index("## The gate"):text.index("## Known wrong turns")]
    assert "ROLLBACK_SAFE" in gate and "INCOMPATIBLE_BOUNDARIES" in gate
    assert "Older code just ignores the new field" in text


def test_db_restore_compares_the_three_rollback_paths_above_the_drill():
    text = _read("docs/deploy/DB_RESTORE.md")
    section = text[text.index("## Code-only rollback (v220)"):]
    table = section[:section.index("### Drill")]
    for needle in ("`rollback_to.sh", "`restore_stable.sh", "`/rollback", "untouched", "/rollback --release"):
        assert needle in table
    assert "rollback_code.sh" in text[:text.index("## Commands")]


def test_agents_md_carries_the_condensed_rule():
    assert "ROLLBACK_SAFE" in _read("AGENTS.md")
