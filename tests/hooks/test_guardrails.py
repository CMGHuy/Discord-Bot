import importlib.util
import json
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "guardrails",
    pathlib.Path(__file__).parent.parent.parent / ".claude" / "hooks" / "guardrails.py",
)
guardrails = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guardrails)

evaluate, _deny, _warn = guardrails.evaluate, guardrails._deny, guardrails._warn


def test_unknown_tool_is_silently_allowed():
    assert evaluate({"tool_name": "WebFetch", "tool_input": {"url": "x"}}) is None


def test_missing_tool_input_is_silently_allowed():
    assert evaluate({"tool_name": "Glob"}) is None


def test_empty_payload_is_silently_allowed():
    assert evaluate({}) is None


def test_deny_shape_matches_the_contract():
    out = _deny("because")
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"] == "because"


def test_warn_allows_and_carries_context():
    out = _warn("heads up")
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["additionalContext"] == "heads up"


GLOB_PATTERN_KEY = "pattern"   # resolved in Task 1 from this session's own Glob tool schema


def test_unscoped_glob_is_denied():
    out = evaluate({"tool_name": "Glob", "tool_input": {GLOB_PATTERN_KEY: "**/*.py"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "swingbot/**/*.py" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_scoped_glob_is_allowed():
    assert evaluate({"tool_name": "Glob", "tool_input": {GLOB_PATTERN_KEY: "swingbot/**/*.py"}}) is None


def test_glob_with_explicit_path_is_allowed():
    assert evaluate({"tool_name": "Glob",
                     "tool_input": {GLOB_PATTERN_KEY: "**/*.py", "path": "swingbot"}}) is None


def test_recursive_grep_from_root_is_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep -r 'def foo' ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git grep" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_scoped_grep_is_allowed():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "grep -r 'def foo' swingbot/core"}}) is None


def test_grep_without_r_is_allowed():
    assert evaluate({"tool_name": "Bash", "tool_input": {"command": "grep foo file.txt"}}) is None


def test_edit_inside_a_worktree_is_denied():
    out = evaluate({"tool_name": "Edit",
                    "tool_input": {"file_path": "/repo/.claude/worktrees/x/swingbot/config.py"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_edit_in_the_main_tree_is_allowed():
    assert evaluate({"tool_name": "Edit",
                     "tool_input": {"file_path": "/repo/swingbot/config.py"}}) is None


def test_reading_a_huge_implemented_plan_is_denied(tmp_path):
    big = tmp_path / "implemented" / "2026-07-11-v3-cockpit.md"
    big.parent.mkdir(parents=True)
    big.write_text("x" * 200_000)
    out = evaluate({"tool_name": "Read", "tool_input": {"file_path": str(big)}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "task-brief" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_reading_a_small_implemented_plan_is_allowed(tmp_path):
    small = tmp_path / "implemented" / "tiny.md"
    small.parent.mkdir(parents=True)
    small.write_text("hello")
    assert evaluate({"tool_name": "Read", "tool_input": {"file_path": str(small)}}) is None


def test_reading_a_live_plan_is_allowed(tmp_path):
    live = tmp_path / "plans" / "2026-08-25-v61-thing.md"
    live.parent.mkdir(parents=True)
    live.write_text("x" * 200_000)
    assert evaluate({"tool_name": "Read", "tool_input": {"file_path": str(live)}}) is None
