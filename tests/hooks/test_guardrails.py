import importlib.util
import json
import os
import pathlib

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "guardrails",
    _REPO_ROOT / ".claude" / "hooks" / "guardrails.py",
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


def test_glob_with_path_dot_is_still_denied():
    # path="." is the repo-root walk the rule exists to prevent, not scoping.
    for root in (".", "./", ' "." '):
        out = evaluate({"tool_name": "Glob",
                        "tool_input": {GLOB_PATTERN_KEY: "**/*.py", "path": root}})
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny", root


def test_glob_deny_message_does_not_advertise_path_dot_as_an_escape():
    out = evaluate({"tool_name": "Glob", "tool_input": {GLOB_PATTERN_KEY: "**/*.py"}})
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert 'path="swingbot"' in reason
    assert "or pass path=." not in reason


def test_recursive_grep_from_root_is_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep -r 'def foo' ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git grep" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_capital_r_grep_from_root_is_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep -R foo ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_long_option_recursive_grep_from_root_is_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep --recursive foo ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_clustered_recursive_grep_flags_are_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep -rn foo ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_quoted_root_target_is_denied():
    for cmd in ('grep -r foo "."', "grep -r foo '.'"):
        out = evaluate({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny", cmd


def test_bare_rg_from_root_is_denied_without_any_flag():
    # ripgrep recurses by default -- no -r needed for the mistake to happen.
    for cmd in ("rg foo .", "rg foo"):
        out = evaluate({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny", cmd


def test_rg_replace_flag_is_not_read_as_recursion():
    # rg -r means --replace; the deny (rg still recurses from root) must not
    # blame `grep -r`, and a scoped rg -r must be allowed.
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "rg -r x pat ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "recurses by default" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "rg -r x pat swingbot/core"}}) is None


def test_recursive_grep_piped_from_root_is_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep -r foo . | head -5"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_scoped_grep_is_allowed():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "grep -r 'def foo' swingbot/core"}}) is None


def test_scoped_rg_is_allowed():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "rg 'def foo' swingbot/core"}}) is None


def test_grep_without_r_is_allowed():
    assert evaluate({"tool_name": "Bash", "tool_input": {"command": "grep foo file.txt"}}) is None


def test_grep_with_unrelated_flags_is_allowed():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "grep -in foo file.txt"}}) is None


def test_git_grep_is_allowed():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "git grep -n 'def foo'"}}) is None


def _edit(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": path}}


def test_main_tree_session_editing_a_worktree_is_denied(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: "/repo")
    out = evaluate(_edit("/repo/.claude/worktrees/x/swingbot/config.py"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "main-tree session" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_edit_in_the_main_tree_is_allowed(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: "/repo")
    assert evaluate(_edit("/repo/swingbot/config.py")) is None


def test_worktree_session_editing_its_own_worktree_is_allowed(monkeypatch):
    # Regression guard: plan execution happens inside a worktree, whose own
    # paths necessarily contain .claude/worktrees/<name>/. Blocking that would
    # block the normal workflow with no recovery path.
    monkeypatch.setattr(os, "getcwd", lambda: "/repo/.claude/worktrees/v60-thing")
    assert evaluate(_edit("/repo/.claude/worktrees/v60-thing/swingbot/config.py")) is None
    assert evaluate({"tool_name": "Write", "tool_input": {
        "file_path": "/repo/.claude/worktrees/v60-thing/notes.md"}}) is None


def test_worktree_session_editing_a_different_worktree_is_denied(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: "/repo/.claude/worktrees/v60-thing")
    out = evaluate(_edit("/repo/.claude/worktrees/v61-other/swingbot/config.py"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_backslash_worktree_paths_are_compared_too(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: r"E:\repo\.claude\worktrees\v60-thing")
    assert evaluate(_edit(r"E:\repo\.claude\worktrees\v60-thing\swingbot\config.py")) is None
    out = evaluate(_edit(r"E:\repo\.claude\worktrees\v61-other\swingbot\config.py"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_unreadable_cwd_fails_open(monkeypatch):
    def boom():
        raise OSError("cwd is gone")
    monkeypatch.setattr(os, "getcwd", boom)
    assert evaluate(_edit("/repo/.claude/worktrees/x/swingbot/config.py")) is None


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


def test_bare_pytest_warns_but_allows():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "python -m pytest"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "testrun.py" in out["additionalContext"]


def test_pytest_with_a_file_is_silent():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "python -m pytest tests/test_edge_gates.py -v"}}) is None


def test_testrun_wrapper_is_silent():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "python scripts/dev/testrun.py fast"}}) is None


def test_cat_on_progress_md_warns():
    out = evaluate({"tool_name": "Bash",
                    "tool_input": {"command": "cat .superpowers/sdd/progress.md"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "tail" in out["additionalContext"]


def test_cat_on_readme_warns():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "cat README.md"}})
    assert "documentation index" in out["additionalContext"]


def test_read_on_progress_md_warns():
    out = evaluate({"tool_name": "Read",
                    "tool_input": {"file_path": ".superpowers/sdd/progress.md"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "tail" in out["additionalContext"]


def test_read_on_readme_warns():
    out = evaluate({"tool_name": "Read", "tool_input": {"file_path": "/repo/README.md"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "documentation index" in out["additionalContext"]


def test_read_on_an_ordinary_file_is_silent():
    assert evaluate({"tool_name": "Read",
                     "tool_input": {"file_path": "swingbot/config.py"}}) is None


def test_deny_rules_are_ordered_before_warn_rules():
    # Structural form of the precedence claim: reordering _RULES turns this red.
    bash = guardrails._RULES["Bash"]
    assert bash.index(guardrails._rule_recursive_grep_from_root) < bash.index(
        guardrails._rule_bare_pytest)
    assert bash.index(guardrails._rule_recursive_grep_from_root) < bash.index(
        guardrails._rule_cat_big_doc)
    read = guardrails._RULES["Read"]
    assert read.index(guardrails._rule_huge_implemented_plan) < read.index(
        guardrails._rule_read_big_doc)


def test_deny_wins_over_warn_when_both_match():
    # This command genuinely trips both: a recursive grep from root (deny) and
    # a trailing bare `python -m pytest` (warn). Both rules fire in isolation.
    cmd = "grep -r foo . && python -m pytest"
    assert guardrails._rule_recursive_grep_from_root({"command": cmd}) is not None
    assert guardrails._rule_bare_pytest({"command": cmd}) is not None
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": cmd}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


_FIXTURES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "payloads.json").read_text())
# The tool_input key each tool's rules actually read.
_KEYS_THE_RULES_READ = {
    "Glob": {"pattern"},
    "Read": {"file_path"},
    "Bash": {"command"},
    "Edit": {"file_path"},
    "Write": {"file_path"},
}


def test_fixture_payloads_carry_the_keys_the_rules_read():
    tools = [k for k in _FIXTURES if not k.startswith("_")]
    assert set(tools) == set(_KEYS_THE_RULES_READ)
    for tool in tools:
        payload = _FIXTURES[tool]
        assert payload["tool_name"] == tool
        assert _KEYS_THE_RULES_READ[tool] <= set(payload["tool_input"]), tool


def test_fixture_payloads_are_all_silently_allowed():
    # These are representative innocuous calls; none of them should trip a rule.
    for tool, payload in _FIXTURES.items():
        if tool.startswith("_"):
            continue
        assert evaluate(payload) is None, tool
