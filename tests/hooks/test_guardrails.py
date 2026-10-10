import importlib.util
import json
import os
import pathlib
import re

import pytest

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


def _bash(cmd):
    return evaluate({"tool_name": "Bash", "tool_input": {"command": cmd}})


def test_deleting_a_backup_branch_is_denied():
    out = _bash("git branch -D 2026-08-16-v36-backup")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git-safety.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_deleting_a_stable_branch_is_denied():
    assert _bash("git branch -d stable-1.9") is not None


def test_remote_deleting_a_backup_branch_is_denied():
    assert _bash("git push origin --delete backup-pre-v67") is not None


def test_colon_refspec_delete_of_a_backup_branch_is_denied():
    assert _bash("git push origin :backup-pre-v67") is not None


def test_force_pushing_a_backup_branch_is_denied():
    assert _bash("git push --force origin backup-pre-v67") is not None


def test_deleting_an_ordinary_branch_is_allowed():
    assert _bash("git branch -D 2026-09-10-v81-execution-feed") is None


def test_merely_listing_backup_branches_is_allowed():
    assert _bash("git branch --list '*backup*'") is None


def test_branch_rule_fails_open_on_a_non_string_command():
    assert evaluate({"tool_name": "Bash", "tool_input": {"command": None}}) is None


def test_a_closed_knob_in_a_grid_is_denied():
    out = _bash('python scripts/backtest/tune_strategy.py --strategy "RSI" '
                '--grid DEAD_CAT_BOUNCE_VETO=true,false')
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "backtest-methodology.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_closed_knob_as_an_env_assignment_is_denied():
    assert _bash("EARNINGS_BLACKOUT_SESSIONS=3 python scripts/backtest/run_backtest_range.py --train") is not None


def test_an_open_strategy_name_alone_is_allowed():
    assert _bash('python scripts/backtest/tune_strategy.py --strategy "Break & Retest" '
                 '--grid min_pullback_atr=0.5,1.0') is None


def test_a_closed_knob_outside_a_backtest_command_is_allowed():
    assert _bash("grep -n DEAD_CAT_BOUNCE_VETO swingbot/config.py") is None


def test_closed_preregistration_rule_fails_open_on_a_missing_command():
    assert evaluate({"tool_name": "Bash", "tool_input": {}}) is None


def test_every_closed_knob_constant_appears_in_the_methodology_doc():
    doc = (_REPO_ROOT / "docs" / "claude" / "backtest-methodology.md").read_text(encoding="utf-8")
    missing = [k for k in guardrails.CLOSED_PREREGISTRATION_KNOBS if k not in doc]
    assert not missing, f"constant lists knobs the doc does not: {missing}"
    assert len(guardrails.CLOSED_PREREGISTRATION_KNOBS) >= 8


def test_every_all_caps_knob_in_the_closed_table_is_in_the_constant():
    """The drift direction that actually bites: a new closed row lands in the
    doc and the hook never learns about it. Lower-case knobs
    (min_level_touches, confirm_bars) are out of reach of this half -- the
    forward assertion above is their only cover."""
    doc = (_REPO_ROOT / "docs" / "claude" / "backtest-methodology.md").read_text(encoding="utf-8")
    table = doc.split("### Closed pre-registrations", 1)[1]
    found = set(re.findall(r"`([A-Z][A-Z0-9_]{4,})`", table))
    missing = found - set(guardrails.CLOSED_PREREGISTRATION_KNOBS)
    assert not missing, (
        f"backtest-methodology.md closes {sorted(missing)} but guardrails.py does "
        "not list them. Add them to CLOSED_PREREGISTRATION_KNOBS."
    )


def _write(path, content=""):
    return evaluate({"tool_name": "Write",
                     "tool_input": {"file_path": path, "content": content}})


_GOOD_PLAN = "docs/superpowers/plans/implemented/2026-09-18-v96-claude-skills-layer.md"


def test_a_misnumbered_plan_filename_is_denied():
    out = _write("docs/superpowers/plans/skills-layer.md", "# Phase 0 - x\n")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "document-conventions.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_two_hash_phase_heading_is_denied():
    assert _write(_GOOD_PLAN, "## Phase 0 - conventions\n") is not None


def test_a_conforming_plan_write_is_allowed():
    assert _write(_GOOD_PLAN, "# Phase 0 - conventions\n\n### Task S1: x\n") is None


def test_a_two_hash_subsection_heading_beside_a_real_one_hash_phase_is_allowed():
    """A legitimate `## Phase A exit criteria` subsection must not deny a
    write just because a one-hash `# Phase` heading exists somewhere else in
    the document -- e.g. docs/superpowers/plans/2026-09-17-v95-responsive-
    content-priority_1-foundations.md, which the reviewer found denied by
    the naive two-hash check even though it is fully conforming."""
    content = (
        "# Phase A -- Foundations\n\n"
        "### Task A1: x\n\n"
        "## Phase A exit criteria\n\n"
        "- all tasks above are green\n"
    )
    assert _write(_GOOD_PLAN, content) is None


def test_a_split_part_filename_is_allowed():
    assert _write("docs/superpowers/plans/2026-08-29-v67-json-to-postgres_1a-foundation-core.md",
                  "# Phase 1 - x\n") is None


def test_a_closed_out_plan_under_implemented_is_allowed():
    assert _write("docs/superpowers/plans/implemented/2026-09-16-v92-exit-quality-harvest.md",
                  "# Phase 1 - x\n") is None


def test_writes_outside_the_doc_dirs_are_untouched():
    assert _write("swingbot/config.py", "## Phase 0\n") is None


def test_plan_doc_shape_fails_open_on_a_non_string_path():
    assert _write(None, "## Phase 0\n") is None


# --- Codex mirror reminder and Codex's apply_patch payloads -------------------

def test_editing_claude_setup_reminds_to_update_the_codex_mirror():
    for path in ("CLAUDE.md", "/repo/docs/claude/known-traps.md",
                 r"E:\repo\.claude\skills\gate\SKILL.md",
                 ".claude/agents/test-runner.md", ".claude/hooks/guardrails.py",
                 ".claude/settings.json"):
        out = evaluate(_edit(path))
        assert out is not None, path
        assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert "sync_codex.py" in out["additionalContext"]
        assert "AGENTS.md" in out["hookSpecificOutput"]["additionalContext"]


def test_editing_ordinary_files_does_not_mention_codex():
    for path in ("swingbot/config.py", "docs/claude-notes.md",
                 ".claude/skills/gate/evals/x/prompt.md", "AGENTS.md"):
        assert evaluate(_edit(path)) is None, path


def test_setup_files_inside_a_worktree_do_not_warn(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: "/repo/.claude/worktrees/v60-thing")
    assert evaluate(_edit("/repo/.claude/worktrees/v60-thing/CLAUDE.md")) is None


def test_worktree_deny_outranks_the_mirror_reminder_on_write(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: "/repo")
    out = evaluate({"tool_name": "Write", "tool_input": {
        "file_path": "/repo/.claude/worktrees/x/CLAUDE.md", "content": ""}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def _patch(*headers):
    body = "\n".join(headers)
    return evaluate({"tool_name": "apply_patch", "tool_input": {
        "command": f"*** Begin Patch\n{body}\n@@\n-a\n+b\n*** End Patch\n"}})


def test_apply_patch_on_ordinary_code_is_silent():
    assert _patch("*** Update File: swingbot/config.py") is None


def test_apply_patch_into_another_worktree_is_denied(monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: "/repo")
    out = _patch("*** Update File: .claude/worktrees/x/swingbot/config.py")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_apply_patch_with_a_misnamed_plan_is_denied():
    out = _patch("*** Add File: docs/superpowers/plans/my-plan.md")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_apply_patch_deny_on_a_later_path_beats_a_warn_on_an_earlier_one():
    out = _patch("*** Update File: CLAUDE.md",
                 "*** Add File: docs/superpowers/plans/my-plan.md")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_apply_patch_on_claude_setup_warns():
    out = _patch("*** Update File: .claude/skills/gate/SKILL.md")
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "sync_codex.py" in out["additionalContext"]


def test_apply_patch_with_no_patch_text_fails_open():
    assert evaluate({"tool_name": "apply_patch", "tool_input": {}}) is None


# --- v155: idea-screen helpers (_rule_screen_rerun's building blocks) -------

_SCREEN = "python scripts/backtest/screen_idea.py"


def test_screen_ledger_path_matches_stats_ledger_path():
    """The hook is stdlib-only, so it carries its own copy of the ledger path;
    this pins it to the one screen_idea.py actually defaults to."""
    from swingbot.core.backtesting.instrument import stats
    assert (pathlib.Path(guardrails.SCREEN_LEDGER_PATH).resolve()
            == stats.LEDGER_PATH.resolve())


def test_screen_results_dir_holds_the_ledger():
    assert (pathlib.Path(guardrails.SCREEN_LEDGER_PATH).parent
            == pathlib.Path(guardrails.SCREEN_RESULTS_DIR))


def test_command_segments_split_on_separators_and_newlines():
    segs = guardrails._command_segments("cd x && ls -la; echo a | wc -l\ngit status")
    assert segs == [["cd", "x"], ["ls", "-la"], ["echo", "a"], ["wc", "-l"],
                    ["git", "status"]]


def test_command_segments_join_backslash_continuations():
    segs = guardrails._command_segments(f"{_SCREEN} \\\n  --idea gap_volume \\\n  --dry-run")
    assert segs == [["python", "scripts/backtest/screen_idea.py", "--idea",
                     "gap_volume", "--dry-run"]]


def test_command_segments_keep_a_quoted_string_whole():
    segs = guardrails._command_segments('bash x.sh "cd /opt && python y.py"')
    assert segs == [["bash", "x.sh", "cd /opt && python y.py"]]


def test_an_untokenisable_screen_line_gives_none():
    assert guardrails._command_segments(f"{_SCREEN} --idea 'gap_volume") is None


def test_an_untokenisable_unrelated_line_is_skipped():
    assert guardrails._command_segments("echo 'oops\ngit status") == [["git", "status"]]


def test_screen_tokens_cover_paths_and_module_names():
    for tok in ("scripts/backtest/screen_idea.py", "scripts\\backtest\\screen_idea.py",
                "screen_idea.py", "screen_idea", "scripts.backtest.screen_idea"):
        assert guardrails._is_screen_token(tok), tok
    for tok in ("screen_idea_notes.md", "tests/test_screen_idea_x.py", "screen"):
        assert not guardrails._is_screen_token(tok), tok


def test_a_wrapped_screen_needs_both_the_name_and_the_idea_flag():
    assert guardrails._is_wrapped_screen(
        f"cd /opt/swing-bot && {_SCREEN} --idea gap_volume")
    assert not guardrails._is_wrapped_screen("docs mention screen_idea.py only")
    assert not guardrails._is_wrapped_screen("scripts/backtest/screen_idea.py")


def test_screen_flags_is_none_for_a_segment_without_the_script():
    assert guardrails._screen_flags(["git", "status"]) is None


def test_screen_flags_read_both_idea_spellings():
    space = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "gap_volume"])
    equals = guardrails._screen_flags(["python", "screen_idea.py", "--idea=gap_volume"])
    assert space["idea"] == equals["idea"] == "gap_volume"


def test_screen_flags_read_every_checked_option():
    flags = guardrails._screen_flags(
        ["python", "-m", "scripts.backtest.screen_idea", "--idea", "x",
         "--tickers", "AAPL,MSFT", "--dry-run", "--ledger", "l.jsonl",
         "--results-dir=r"])
    assert flags == {"idea": "x", "dry_run": True, "tickers": True,
                     "ticker_count": 2, "ledger": "l.jsonl", "results_dir": "r"}


def test_screen_flags_resolve_unique_abbreviations_like_argparse():
    flags = guardrails._screen_flags(
        ["python", "screen_idea.py", "--id", "x", "--dry", "--led", "l.jsonl",
         "--res=r"])
    assert flags == {"idea": "x", "dry_run": True, "tickers": False,
                     "ticker_count": 0, "ledger": "l.jsonl", "results_dir": "r"}


def test_screen_flags_ignore_an_ambiguous_abbreviation():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x", "--d"])
    assert flags["dry_run"] is False


def test_screen_flags_ignore_tokens_before_the_script():
    flags = guardrails._screen_flags(["X=--dry-run", "python", "screen_idea.py",
                                      "--idea", "x"])
    assert flags["dry_run"] is False


def test_an_empty_tickers_value_is_no_tickers():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x",
                                      "--tickers=", "--dry-run"])
    assert flags["tickers"] is False
    assert flags["ticker_count"] == 0


def test_empty_ticker_entries_do_not_count():
    flags = guardrails._screen_flags(["python", "screen_idea.py", "--idea", "x",
                                      "--tickers", "A,,B,"])
    assert flags["ticker_count"] == 2


@pytest.fixture
def screen_repo(tmp_path, monkeypatch):
    """A throwaway repo root holding an empty results dir, with the hook's
    screen constants pointed at it. Never the real ledger."""
    results = tmp_path / "docs" / "superpowers" / "results"
    results.mkdir(parents=True)
    monkeypatch.setattr(guardrails, "_HOOK_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(guardrails, "SCREEN_RESULTS_DIR", str(results))
    monkeypatch.setattr(guardrails, "SCREEN_LEDGER_PATH",
                        str(results / "preregistration-ledger.jsonl"))
    return results


def _ledger_rows(results, *rows):
    (results / "preregistration-ledger.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_default_ledger_matches_relative_and_absolute_spellings(screen_repo):
    assert guardrails._is_default_ledger(
        "docs/superpowers/results/preregistration-ledger.jsonl")
    assert guardrails._is_default_ledger(
        "./docs/superpowers/results/../results/preregistration-ledger.jsonl")
    assert guardrails._is_default_ledger(str(screen_repo / "preregistration-ledger.jsonl"))
    assert not guardrails._is_default_ledger("fresh.jsonl")


def test_default_results_dir_matches_relative_and_absolute_spellings(screen_repo):
    assert guardrails._is_default_results_dir("docs/superpowers/results")
    assert guardrails._is_default_results_dir("docs/superpowers/results/")
    assert guardrails._is_default_results_dir(str(screen_repo))
    assert not guardrails._is_default_results_dir("elsewhere")


def test_ledger_row_matches_the_exact_id_only(screen_repo):
    _ledger_rows(screen_repo,
                 {"id": "screen-gap_volume_v2", "date": "2026-10-01"},
                 {"id": "screen-gap_volume", "date": "2026-10-02"})
    assert guardrails._screen_ledger_row("gap_volume")["date"] == "2026-10-02"
    assert guardrails._screen_ledger_row("gap") is None


def test_ledger_row_skips_malformed_lines(screen_repo):
    (screen_repo / "preregistration-ledger.jsonl").write_text(
        'not json\n[1, 2]\n{"id": "screen-x", "date": "d"}\n', encoding="utf-8")
    assert guardrails._screen_ledger_row("x") == {"id": "screen-x", "date": "d"}


def test_a_missing_ledger_reads_as_no_row(screen_repo):
    assert guardrails._screen_ledger_row("x") is None


def test_results_doc_is_found_whatever_its_date(screen_repo):
    doc = screen_repo / "2026-10-09-screen-turn_of_month.md"
    doc.write_text("# result\n", encoding="utf-8")
    assert guardrails._screen_results_doc("turn_of_month") == str(doc)
    assert guardrails._screen_results_doc("month") is None


def test_a_missing_results_dir_reads_as_no_doc(screen_repo, monkeypatch):
    monkeypatch.setattr(guardrails, "SCREEN_RESULTS_DIR", str(screen_repo / "absent"))
    assert guardrails._screen_results_doc("x") is None


# --- v155: _rule_screen_rerun (the idea screen's one-shot rule) -------------

_SCREEN_TAIL = (' -- one shot per idea; see docs/claude/backtest-methodology.md '
                '"Funnel stages".')


def _screen_denial(cmd):
    """The deny reason for `cmd`; fails the test when it is not a deny."""
    out = _bash(cmd)
    assert out is not None, cmd
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny", cmd
    reason = hso["permissionDecisionReason"]
    assert reason.startswith("screen_idea: ") and reason.endswith(_SCREEN_TAIL)
    return reason


def _screened(results, idea="gap_volume"):
    """`idea` with a ledger row and its results doc, as a finished screen."""
    record = f"docs/superpowers/results/2026-10-09-screen-{idea}.md"
    _ledger_rows(results, {"id": f"screen-{idea}", "date": "2026-10-09",
                           "verdict": "SCREEN-FAIL", "record": record})
    (results / f"2026-10-09-screen-{idea}.md").write_text("# r\n", encoding="utf-8")


def test_screen_rerun_rule_runs_right_after_the_closed_preregistration_rule():
    bash_rules = guardrails._RULES["Bash"]
    i = bash_rules.index(guardrails._rule_closed_preregistration)
    assert bash_rules[i + 1] is guardrails._rule_screen_rerun


def test_a_first_real_run_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea gap_volume") is None


def test_a_rerun_of_a_screened_idea_is_denied_with_its_ledger_row(screen_repo):
    _screened(screen_repo)
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume")
    assert ("screen-gap_volume is already in the ledger (2026-10-09, SCREEN-FAIL, "
            "docs/superpowers/results/2026-10-09-screen-gap_volume.md)") in reason


def test_both_idea_spellings_are_denied(screen_repo):
    _screened(screen_repo)
    _screen_denial(f"{_SCREEN} --idea=gap_volume")
    _screen_denial(f"{_SCREEN} --idea gap_volume")


def test_only_the_exact_ledger_id_denies(screen_repo):
    _ledger_rows(screen_repo, {"id": "screen-gap_volume_v2", "date": "d",
                               "verdict": "v", "record": "r"})
    assert _bash(f"{_SCREEN} --idea gap_volume") is None
    assert _bash(f"{_SCREEN} --idea gap") is None


def test_a_results_doc_with_no_ledger_row_is_denied(screen_repo):
    (screen_repo / "2026-10-08-screen-turn_of_month.md").write_text(
        "# r\n", encoding="utf-8")
    reason = _screen_denial(f"{_SCREEN} --idea turn_of_month")
    assert ("results doc docs/superpowers/results/2026-10-08-screen-turn_of_month.md "
            "exists with no ledger row") in reason


def test_a_full_universe_dry_run_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --dry-run")
    assert "--dry-run without --tickers" in reason


def test_an_abbreviated_full_universe_dry_run_is_denied(screen_repo):
    assert "--dry-run without --tickers" in _screen_denial(
        f"{_SCREEN} --idea gap_volume --dry")


def test_a_tickers_dry_run_is_allowed_even_for_a_screened_idea(screen_repo):
    _screened(screen_repo)
    assert _bash(f"{_SCREEN} --idea gap_volume --tickers AAPL,MSFT --dry-run") is None


def test_a_three_ticker_dry_run_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea fresh_idea --tickers A,B,C --dry-run") is None


def test_a_four_ticker_dry_run_is_denied(screen_repo):
    reason = _screen_denial(
        f"{_SCREEN} --idea fresh_idea --tickers A,B,C,D --dry-run")
    assert "--dry-run with more than 3 --tickers" in reason


def test_an_equals_form_four_ticker_abbreviated_dry_run_is_denied(screen_repo):
    reason = _screen_denial(
        f"{_SCREEN} --idea fresh_idea --tickers=a,b,c,d --dry")
    assert "--dry-run with more than 3 --tickers" in reason


def test_a_dry_run_with_empty_ticker_entries_counts_only_symbols(screen_repo):
    assert _bash(f"{_SCREEN} --idea fresh_idea --tickers A,,B,,C --dry-run") is None


def test_a_non_default_ledger_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --ledger fresh.jsonl")
    assert "--ledger other than the default (fresh.jsonl)" in reason


def test_a_non_existent_ledger_is_denied(screen_repo):
    reason = _screen_denial(
        f"{_SCREEN} --idea gap_volume --led=/nowhere/absent.jsonl")
    assert "--ledger other than the default" in reason


def test_the_default_ledger_spelled_out_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea gap_volume --ledger "
                 "docs/superpowers/results/preregistration-ledger.jsonl") is None


def test_a_non_default_results_dir_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --results-dir scratch")
    assert "--results-dir other than the default (scratch)" in reason


def test_a_non_default_results_dir_hides_no_doc_from_the_rule(screen_repo):
    (screen_repo / "2026-10-08-screen-gap_volume.md").write_text(
        "# r\n", encoding="utf-8")
    reason = _screen_denial(f"{_SCREEN} --idea gap_volume --res=elsewhere")
    assert "--results-dir other than the default (elsewhere)" in reason


def test_the_default_results_dir_spelled_out_is_allowed(screen_repo):
    assert _bash(f"{_SCREEN} --idea gap_volume "
                 "--results-dir docs/superpowers/results") is None


def test_a_chained_command_reads_the_screen_segment(screen_repo):
    _screened(screen_repo)
    _screen_denial(f"cd scripts && cd .. && {_SCREEN} --idea gap_volume")
    assert _bash("echo --dry-run && "
                 f"{_SCREEN} --idea fresh_idea --tickers AAPL --dry-run") is None


def test_the_first_denying_segment_wins(screen_repo):
    _screened(screen_repo)
    reason = _screen_denial(
        f"{_SCREEN} --idea fresh_idea; {_SCREEN} --idea gap_volume --dry-run")
    assert "--dry-run without --tickers" in reason


def test_a_backslash_continued_command_is_read_whole(screen_repo):
    reason = _screen_denial(f"{_SCREEN} \\\n  --idea gap_volume \\\n  --dry-run")
    assert "--dry-run without --tickers" in reason


def test_the_module_form_is_read(screen_repo):
    _screened(screen_repo)
    _screen_denial("python -m scripts.backtest.screen_idea --idea gap_volume")


def test_a_quoted_ssh_wrapper_is_denied(screen_repo):
    reason = _screen_denial(
        'bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && '
        f'{_SCREEN} --idea gap_volume"')
    assert "inside a quoted wrapper" in reason


def test_a_pwsh_wrapper_is_denied(screen_repo):
    reason = _screen_denial(f"pwsh -Command '{_SCREEN} --idea gap_volume'")
    assert "inside a quoted wrapper" in reason


def test_an_untokenisable_screen_line_is_denied(screen_repo):
    reason = _screen_denial(f"{_SCREEN} --idea 'gap_volume")
    assert "could not tokenise" in reason


def test_mentions_of_the_script_without_a_run_are_allowed(screen_repo):
    _screened(screen_repo)
    for cmd in ("git grep -n screen_idea", 'git grep -n "screen_idea.py"',
                "cat scripts/backtest/screen_idea.py",
                f"{_SCREEN} --help"):
        assert _bash(cmd) is None, cmd


def test_screen_rerun_rule_fails_open_on_a_missing_command():
    assert guardrails._rule_screen_rerun({}) is None
    assert guardrails._rule_screen_rerun({"command": 7}) is None
