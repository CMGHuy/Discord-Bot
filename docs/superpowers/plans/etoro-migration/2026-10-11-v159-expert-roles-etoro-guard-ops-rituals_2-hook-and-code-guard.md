# v159 Four expert seats, a demo-only eToro guard, and the ops/UI rituals. Part 2: hook and code guard (ER5–ER8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task ER6" -A 300 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md` (§ B1, § B2)
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here.

**Conventions for every task in this part**

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals` (created in ER1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`, and run tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>` (testrun runs pytest with `cwd` at its own repo root, so a relative test path resolves inside the worktree).
- Hook-rule test code that names a protected branch uses `stable-1.9`, never the other protected word, and is written through Edit/Write, never a Bash heredoc (`_rule_protected_branch_delete` reads command text).
- Never touch the real `.env`. Settings tests go through the `admin_app`/`env_file` fixtures.
- Every new or changed function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing for the files a task changed (except `_validate` in `system.py`, already D 21 and left unchanged).

# Phase B — eToro demo-only guard (ER5–ER8 here; ER9 is in part 2b, `_2b-server-signoff.md`; ER10–ER12 continue in part 3)

### Task ER5: Shell rules registered under `PowerShell`

**Model:** sonnet — a dispatch-table change in a fail-open hook plus parametrised tests; one file of logic, no design choice left open.

Spec § B1 "PowerShell gets the Bash command rules". Today `_RULES` has no `PowerShell` key and `.claude/settings.json:138` does not route `PowerShell` to the hook, so on the Windows dev machine the protected-branch, closed-pre-registration and screen-rerun denies never fire. This task makes Bash and PowerShell share **one** list object, `_SHELL_RULES`, so a rule added to it later (ER6's eToro rule) reaches both shells at once.

**Files:**
- Modify: `.claude/hooks/guardrails.py` (the `_RULES` block, ~l.646-658)
- Modify: `tests/hooks/test_guardrails.py` (`_KEYS_THE_RULES_READ` ~l.290; new tests appended at the end)
- Modify: `tests/hooks/fixtures/payloads.json` (new `PowerShell` entry)
- Modify: `.claude/settings.json` (PreToolUse matcher, ~l.138)

**Interfaces:**
- Consumes: the six existing Bash rules in `.claude/hooks/guardrails.py`: `_rule_protected_branch_delete` (l.227, deny), `_rule_closed_preregistration` (l.276, deny), `_rule_screen_rerun` (l.527, deny), `_rule_recursive_grep_from_root` (deny), `_rule_bare_pytest` (warn), `_rule_cat_big_doc` (warn). All read `ti.get("command")`.
- Produces (ER6 and ER14 rely on these):
  - `_SHELL_RULES: list` — exactly `[_rule_protected_branch_delete, _rule_closed_preregistration, _rule_screen_rerun, _rule_recursive_grep_from_root, _rule_bare_pytest, _rule_cat_big_doc]` (deny before warn).
  - `_RULES["Bash"] is _SHELL_RULES` and `_RULES["PowerShell"] is _SHELL_RULES`.
  - Fixture `PowerShell` in `tests/hooks/fixtures/payloads.json`; `_KEYS_THE_RULES_READ["PowerShell"] == {"command"}`.
  - Claude matcher `Glob|Read|Edit|Write|NotebookEdit|Bash|PowerShell` (ER6 appends `|mcp__.*`).
  - Test helper `_ps(cmd)` in `tests/hooks/test_guardrails.py` (ER6 reuses it).

**Codex mirror note:** Codex has no `PowerShell` tool (its shell is `Bash`), so `.codex/hooks.json` does not change here. The condensed `AGENTS.md` hook paragraph is rewritten once, in ER6, covering both PowerShell and the eToro rule. The `_rule_codex_mirror_reminder` warn fired by editing `.claude/settings.json` and the hook is expected; ER6 is where the mirror lands.

- [ ] **Step 1: Write the failing tests**

Edit `tests/hooks/test_guardrails.py` with the Edit tool (never a Bash heredoc: the protected-branch rule reads command text).

In `_KEYS_THE_RULES_READ` add one entry, so the dict reads:

```python
_KEYS_THE_RULES_READ = {
    "Glob": {"pattern"},
    "Read": {"file_path"},
    "Bash": {"command"},
    "PowerShell": {"command"},
    "Edit": {"file_path"},
    "Write": {"file_path"},
}
```

Append at the end of the file:

```python
# --- v159: PowerShell meets the same shell rules as Bash ----------------------

_SETTINGS_JSON = _REPO_ROOT / ".claude" / "settings.json"


def _ps(cmd):
    return evaluate({"tool_name": "PowerShell", "tool_input": {"command": cmd}})


def _guardrail_matcher(settings_path):
    """The PreToolUse matcher of the entry that runs guardrails.py."""
    entries = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    return next(e["matcher"] for e in entries
                if any("guardrails.py" in h["command"] for h in e["hooks"]))


def test_the_claude_matcher_routes_powershell_to_the_hook():
    assert "PowerShell" in _guardrail_matcher(_SETTINGS_JSON).split("|")


def test_bash_and_powershell_share_one_rule_list():
    # One list object: a rule appended for Bash reaches PowerShell too.
    assert guardrails._RULES["Bash"] is guardrails._SHELL_RULES
    assert guardrails._RULES["PowerShell"] is guardrails._SHELL_RULES


def test_shell_rules_are_the_six_bash_rules_deny_first():
    assert guardrails._SHELL_RULES == [
        guardrails._rule_protected_branch_delete,
        guardrails._rule_closed_preregistration,
        guardrails._rule_screen_rerun,
        guardrails._rule_recursive_grep_from_root,
        guardrails._rule_bare_pytest,
        guardrails._rule_cat_big_doc,
    ]


_PS_CASES = [
    ("_rule_protected_branch_delete", "git branch -D stable-1.9", "deny"),
    ("_rule_closed_preregistration",
     "python scripts/backtest/tune_strategy.py --strategy RSI --grid RS_GATE=on,off",
     "deny"),
    ("_rule_recursive_grep_from_root", "grep -r 'def foo' .", "deny"),
    ("_rule_bare_pytest", "python -m pytest", "allow"),
    ("_rule_cat_big_doc", "cat README.md", "allow"),
]


@pytest.mark.parametrize("rule, cmd, decision", _PS_CASES,
                         ids=[c[0] for c in _PS_CASES])
def test_a_powershell_command_meets_each_bash_rule(rule, cmd, decision):
    assert getattr(guardrails, rule)({"command": cmd}) is not None, "case trips its rule"
    out = _ps(cmd)
    assert out is not None
    assert out == _bash(cmd)
    assert out["hookSpecificOutput"]["permissionDecision"] == decision


def test_a_powershell_screen_rerun_is_denied(screen_repo):
    _screened(screen_repo)
    cmd = f"{_SCREEN} --idea gap_volume"
    out = _ps(cmd)
    assert out == _bash(cmd)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_an_innocuous_powershell_command_is_silent():
    assert _ps("Get-ChildItem swingbot") is None


def test_a_powershell_call_without_a_command_fails_open():
    assert _ps(7) is None
    assert evaluate({"tool_name": "PowerShell", "tool_input": {}}) is None
```

In `tests/hooks/fixtures/payloads.json`, add after the `Bash` entry (keep valid JSON: comma after the `Bash` object's closing brace):

```json
  "PowerShell": {
    "tool_name": "PowerShell",
    "tool_input": {
      "command": "Get-ChildItem swingbot",
      "description": "List the package"
    }
  },
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_guardrails.py`
Expected: FAIL — `AttributeError: module 'guardrails' has no attribute '_SHELL_RULES'`, `test_the_claude_matcher_routes_powershell_to_the_hook` fails, and the parametrised PowerShell cases fail on `out is not None`.

- [ ] **Step 3: Implement**

In `.claude/hooks/guardrails.py`, replace the block from the `# Rules run in list order;` comment through the end of the `_RULES = {...}` literal with:

```python
# Rules for a shell command. Bash and PowerShell share ONE list object (v159):
# PowerShell is the main shell on the Windows dev machine, and before v159 not
# one of these rules fired there -- the protected-branch guard included. A
# rule appended here reaches both shells. Deny rules first, warn rules last.
_SHELL_RULES = [_rule_protected_branch_delete, _rule_closed_preregistration,
                _rule_screen_rerun, _rule_recursive_grep_from_root,
                _rule_bare_pytest, _rule_cat_big_doc]

# Rules run in list order; the first non-None decision wins. Warn rules are
# appended after deny rules on the same tool, so deny takes precedence.
# Codex (.codex/hooks.json) runs this same hook: its shell tool is `Bash` and
# its file edits arrive as `apply_patch`, `Edit` or `Write`.
_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": _SHELL_RULES,
    "PowerShell": _SHELL_RULES,
    "Read": [_rule_huge_implemented_plan, _rule_read_big_doc],
    "Edit": [_rule_worktree_write, _rule_codex_mirror_reminder],
    "Write": [_rule_worktree_write, _rule_plan_doc_shape, _rule_codex_mirror_reminder],
    "NotebookEdit": [_rule_worktree_write],
    "apply_patch": [_rule_apply_patch],
}
```

`evaluate()` is unchanged in this task.

In `.claude/settings.json`, change the guardrails entry's matcher:

```json
        "matcher": "Glob|Read|Edit|Write|NotebookEdit|Bash|PowerShell",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_guardrails.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Then: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS (the command sets are unchanged; only the Claude matcher grew).

Then: `python -m radon cc -s -n C "$WT/.claude/hooks/guardrails.py"`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py tests/hooks/fixtures/payloads.json .claude/settings.json
git -C "$WT" commit -m "feat(v159): ER5 -- PowerShell meets the Bash command rules

_SHELL_RULES is one list shared by Bash and PowerShell, and the Claude
PreToolUse matcher now routes PowerShell to guardrails.py. Before this the
protected-branch, closed-pre-registration and screen-rerun denies never
fired on the main Windows dev shell. Codex has no PowerShell tool, so
.codex/hooks.json is unchanged; AGENTS.md is updated in ER6.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER6: `_rule_etoro_real_account`, MCP prefix table, patch sections, both matchers

**Model:** opus — a never-raising deny rule in a fail-open security hook, over three input shapes and two agents' dispatch; a missed path here is a silent hole in the real-money guard.

Spec § B1. One total rule denies (a) an eToro MCP call carrying an explicit real-account marker or a real trading route, (b) a Bash/PowerShell request to an eToro trading endpoint without `/demo/` in its path, and (c) an Edit, Write or `apply_patch` that writes an **unlock value** into a `.env*` file. Controller decision (2026-10-11, index OPEN 1): only unlock values are denied — `ETORO_ALLOW_REAL` truthy (`true`, `1`, `yes`, `on`, any case) or `ETORO_REAL_SIGNOFF` non-empty. `ETORO_ALLOW_REAL=false` and `ETORO_REAL_SIGNOFF=` pass, so ER7 can add both keys to `.env.example`.

`evaluate()` looks rules up by exact tool name, so MCP tools need a **prefix table** keyed on the server segment of `mcp__<server>__<tool>`. No eToro MCP server is configured in this repo (`.mcp.json` holds only context7); the server is `etoro-public-api-mcp` (`.claude/skills/etoro-public-api-operations/SKILL.md:3`), so the key is the fragment `etoro` and the tests pin both `mcp__etoro-public-api-mcp__<tool>` and the plugin form `mcp__plugin_etoro_etoro__<tool>`.

Route shapes (`etoro-public-api-operations/SKILL.md:288`): demo `/api/v2/trading/execution/demo/orders`, real `/api/v2/trading/execution/orders`. A *trading route* is a path containing `/trading/`; the demo marker is `/demo/` inside that path. eToro read tools default `account` to `"real"` when it is absent (SKILL.md:23,29); an absent account is **not** an explicit marker and is allowed, as the spec says. `place-trade`/`place-close` take only a `token`, so the rule sees the account at `prepare-trade`/`prepare-close`.

**Files:**
- Modify: `.claude/hooks/guardrails.py` (new eToro block before the `# Codex edits files through apply_patch` comment; `_rule_apply_patch`, `_PATCH_PATH_RULES`, `_SHELL_RULES`, `_RULES`, `evaluate`; new `_PREFIX_RULES`, `_rules_for`)
- Modify: `tests/hooks/test_guardrails.py`
- Modify: `tests/hooks/fixtures/payloads.json`
- Modify: `.claude/settings.json` (matcher)
- Modify: `.codex/hooks.json` (matcher)
- Modify: `tests/hooks/test_codex_mirror.py`
- Modify: `AGENTS.md` (the hook paragraph, ~l.325-335)

**Interfaces:**
- Consumes (ER5): `_SHELL_RULES`, `_RULES["Bash"] is _RULES["PowerShell"] is _SHELL_RULES`, test helpers `_ps`, `_bash`, `_guardrail_matcher`, `_SETTINGS_JSON`; existing `_PATCH_PATH_RE`, `_deny`, `_rule_worktree_write`, `_rule_plan_doc_shape`, `_rule_codex_mirror_reminder`.
- Produces (ER14 relies on the last four):
  - `ETORO_MCP_FRAGMENT = "etoro"`; `ETORO_UNLOCK_KEYS = ("ETORO_ALLOW_REAL", "ETORO_REAL_SIGNOFF")`.
  - `_rule_etoro_real_account(ti: object) -> dict | None` — total; never raises.
  - `_PREFIX_RULES = ((ETORO_MCP_FRAGMENT, (_rule_etoro_real_account,)),)`.
  - `_rules_for(tool: object) -> tuple | list` — `_RULES[tool]` when present, else the prefix-table rules for an `mcp__<server>__<tool>` name whose server segment contains a fragment, else `()`.
  - `_patch_sections(patch: str) -> list[tuple[str, str]]` — `(path, section text)` per `*** Add File:` / `Update File:` / `Delete File:` / `Move to:` header, the text running to the next header.
  - `_rule_apply_patch` passes `{"file_path": path, "patch_body": section}` to every rule in `_PATCH_PATH_RULES`.
  - `_PATCH_PATH_RULES = (_rule_worktree_write, _rule_plan_doc_shape, _rule_etoro_real_account, _rule_codex_mirror_reminder)`.
  - Matchers: Claude `Glob|Read|Edit|Write|NotebookEdit|Bash|PowerShell|mcp__.*`; Codex `Bash|apply_patch|Edit|Write|mcp__.*`.
  - `_KEYS_THE_RULES_READ`: `Edit {file_path, new_string}`, `Write {file_path, content}`, `mcp__etoro-public-api-mcp__get-my-portfolio-summary {account}` (ER14 adds `old_string` to `Edit`).

- [ ] **Step 1: Write the failing tests**

All edits to `tests/hooks/test_guardrails.py` go through the Edit tool.

1a. Update `_KEYS_THE_RULES_READ` to:

```python
_KEYS_THE_RULES_READ = {
    "Glob": {"pattern"},
    "Read": {"file_path"},
    "Bash": {"command"},
    "PowerShell": {"command"},
    "Edit": {"file_path", "new_string"},
    "Write": {"file_path", "content"},
    "mcp__etoro-public-api-mcp__get-my-portfolio-summary": {"account"},
}
```

1b. Replace ER5's `test_shell_rules_are_the_six_bash_rules_deny_first` with:

```python
def test_shell_rules_put_every_deny_before_every_warn():
    assert guardrails._SHELL_RULES == [
        guardrails._rule_protected_branch_delete,
        guardrails._rule_closed_preregistration,
        guardrails._rule_screen_rerun,
        guardrails._rule_recursive_grep_from_root,
        guardrails._rule_etoro_real_account,
        guardrails._rule_bare_pytest,
        guardrails._rule_cat_big_doc,
    ]
```

1c. Append at the end of the file:

```python
# --- v159: eToro is demo only (_rule_etoro_real_account) ---------------------

_ETORO = guardrails._rule_etoro_real_account
_SERVER = "mcp__etoro-public-api-mcp__"
_PLUGIN = "mcp__plugin_etoro_etoro__"
_REAL_ORDERS = "/api/v2/trading/execution/orders"
_DEMO_ORDERS = "/api/v2/trading/execution/demo/orders"
_HOST = "https://public-api.etoro.com"


def _mcp(tool, **tool_input):
    return evaluate({"tool_name": tool, "tool_input": tool_input})


def _is_deny(out):
    return (out is not None
            and out["hookSpecificOutput"]["permissionDecision"] == "deny")


def _env_patch(header, *lines):
    body = "\n".join(lines)
    return evaluate({"tool_name": "apply_patch", "tool_input": {
        "command": f"*** Begin Patch\n{header}\n{body}\n*** End Patch\n"}})


def test_the_prefix_table_keys_on_the_etoro_fragment():
    assert guardrails.ETORO_MCP_FRAGMENT == "etoro"
    assert guardrails._PREFIX_RULES == (("etoro", (_ETORO,)),)


@pytest.mark.parametrize("tool", [f"{_SERVER}prepare-trade",
                                  f"{_PLUGIN}prepare-trade",
                                  "mcp__eToro__execute-write"])
def test_an_etoro_mcp_tool_reaches_the_rule(tool):
    assert guardrails._rules_for(tool) == (_ETORO,)


@pytest.mark.parametrize("tool", ["mcp__context7__resolve-library-id",
                                  "mcp__notes__etoro-lookup",   # fragment in the tool part only
                                  "mcp__etoro",                 # no tool segment
                                  "etoro__x__y", "WebFetch", None, 5, ["Bash"]])
def test_other_tool_names_get_no_prefix_rules(tool):
    assert guardrails._rules_for(tool) == ()


def test_an_exact_tool_name_still_wins():
    assert guardrails._rules_for("Bash") is guardrails._SHELL_RULES


@pytest.mark.parametrize("tool, tool_input", [
    (f"{_SERVER}prepare-trade", {"account": "real", "symbol": "AAPL", "amount": 100}),
    (f"{_SERVER}prepare-close", {"account": "REAL", "positionId": 1}),
    (f"{_SERVER}get-my-portfolio-summary", {"account": " Real "}),
    (f"{_SERVER}get-my-positions-and-orders", {"environment": "real"}),
    (f"{_SERVER}execute-write", {"method": "POST", "path": _REAL_ORDERS, "body": "{}"}),
    (f"{_SERVER}execute-read", {"path": "/api/v1/trading/info/portfolio"}),
    (f"{_PLUGIN}prepare-trade", {"account": "real"}),
])
def test_an_etoro_mcp_call_on_the_real_account_is_denied(tool, tool_input):
    out = _mcp(tool, **tool_input)
    assert _is_deny(out)
    assert "etoro-roadmap.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("tool, tool_input", [
    (f"{_SERVER}prepare-trade", {"account": "demo", "symbol": "AAPL", "amount": 100}),
    (f"{_SERVER}get-my-portfolio-summary", {}),            # read default: not explicit
    (f"{_SERVER}execute-write", {"method": "POST", "path": _DEMO_ORDERS}),
    (f"{_SERVER}execute-read", {"path": "/api/v1/market-data/search"}),
    (f"{_SERVER}place-trade", {"token": "abc"}),
    (f"{_SERVER}get-instruments-overview", {"symbols": ["AAPL"]}),
])
def test_an_etoro_mcp_call_on_demo_or_without_a_marker_is_allowed(tool, tool_input):
    assert _mcp(tool, **tool_input) is None


@pytest.mark.parametrize("cmd", [
    f"curl -X POST {_HOST}{_REAL_ORDERS} -d '{{}}'",
    f'curl -H "x-api-key: $ETORO_API_KEY" "$BASE{_REAL_ORDERS}"',
    f"python -c \"import requests; requests.post('{_HOST}{_REAL_ORDERS}')\"",
])
def test_a_bash_request_to_a_real_etoro_trading_endpoint_is_denied(cmd):
    assert _is_deny(_bash(cmd))


def test_a_powershell_request_to_a_real_etoro_trading_endpoint_is_denied():
    out = _ps(f"Invoke-RestMethod -Method Post -Uri {_HOST}{_REAL_ORDERS}")
    assert _is_deny(out)
    assert "etoro-roadmap.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("cmd", [
    f"curl -X POST {_HOST}{_DEMO_ORDERS} -d '{{}}'",
    f"curl https://example.com{_REAL_ORDERS}",                 # not eToro
    "git grep -n etoro",
    'git grep -n "trading/execution" -- docs',                 # no request, no host
    "python scripts/dev/testrun.py file tests/broker/test_guard.py",
])
def test_shell_commands_without_a_real_etoro_request_are_allowed(cmd):
    assert _bash(cmd) is None
    assert _ps(cmd) is None


@pytest.mark.parametrize("path", [".env", ".env.local", ".env.example",
                                  "E:\\repo\\.env", "/opt/swing-bot/.env"])
@pytest.mark.parametrize("text", ["ETORO_ALLOW_REAL=true", "ETORO_ALLOW_REAL=True\n",
                                  "export ETORO_ALLOW_REAL=1",
                                  "ETORO_ALLOW_REAL = yes", 'ETORO_ALLOW_REAL="on"',
                                  "A=1\nETORO_REAL_SIGNOFF=2026-10-11\n",
                                  "ETORO_REAL_SIGNOFF='2027-01-01'"])
def test_an_env_edit_that_unlocks_real_money_is_denied(path, text):
    assert _is_deny(evaluate({"tool_name": "Edit", "tool_input": {
        "file_path": path, "old_string": "x", "new_string": text}}))
    assert _is_deny(evaluate({"tool_name": "Write", "tool_input": {
        "file_path": path, "content": text}}))


@pytest.mark.parametrize("text", ["ETORO_ALLOW_REAL=false", "ETORO_ALLOW_REAL=",
                                  "ETORO_REAL_SIGNOFF=", 'ETORO_REAL_SIGNOFF=""',
                                  "ETORO_REAL_SIGNOFF=   # set on the VM by hand",
                                  "ETORO_USER_KEY=abc\nETORO_API_KEY=def"])
def test_an_env_edit_that_keeps_real_money_locked_is_allowed(text):
    assert evaluate({"tool_name": "Write", "tool_input": {
        "file_path": ".env.example", "content": text}}) is None


def test_unlock_text_outside_an_env_file_is_allowed():
    for path in ("swingbot/config.py", "tests/hooks/test_guardrails.py", "notes.env.md"):
        assert evaluate({"tool_name": "Write", "tool_input": {
            "file_path": path, "content": "ETORO_ALLOW_REAL=true"}}) is None, path


def test_an_apply_patch_that_unlocks_real_money_is_denied():
    out = _env_patch("*** Update File: .env", "@@", "-ETORO_ALLOW_REAL=false",
                     "+ETORO_ALLOW_REAL=true")
    assert _is_deny(out)
    assert _is_deny(_env_patch("*** Add File: deploy/.env.prod",
                               "+ETORO_REAL_SIGNOFF=2026-01-01"))


def test_an_apply_patch_that_relocks_real_money_is_allowed():
    # The removed line carries the unlock value; only added lines count.
    assert _env_patch("*** Update File: .env", "@@", "-ETORO_ALLOW_REAL=true",
                      "+ETORO_ALLOW_REAL=false") is None


def test_an_unlock_in_another_files_patch_section_does_not_leak_into_env():
    out = _env_patch("*** Update File: .env", "@@", "-A=1", "+A=2",
                     "*** Update File: tests/hooks/test_guardrails.py", "@@",
                     "+ETORO_ALLOW_REAL=true")
    assert out is None


def test_patch_sections_split_at_every_file_header():
    patch = ("*** Begin Patch\n*** Update File: a.py\n@@\n+x\n"
             "*** Add File: .env\n+ETORO_ALLOW_REAL=true\n*** End Patch\n")
    sections = guardrails._patch_sections(patch)
    assert [p for p, _ in sections] == ["a.py", ".env"]
    assert "ETORO_ALLOW_REAL" not in sections[0][1]
    assert "+ETORO_ALLOW_REAL=true" in sections[1][1]


def test_patch_path_rules_put_the_etoro_deny_before_the_mirror_warn():
    assert guardrails._PATCH_PATH_RULES == (
        guardrails._rule_worktree_write, guardrails._rule_plan_doc_shape,
        _ETORO, guardrails._rule_codex_mirror_reminder)
    for tool in ("Edit", "Write"):
        rules = guardrails._RULES[tool]
        assert rules.index(_ETORO) < rules.index(guardrails._rule_codex_mirror_reminder)


@pytest.mark.parametrize("ti", [
    None, 7, "account: real", ["account", "real"], b"real", {},
    {"account": None}, {"account": 5}, {"account": ["real"]}, {"environment": {}},
    {"path": None}, {"path": ["/trading/x"]}, {"url": 3},
    {"command": None}, {"command": b"curl etoro /trading/x"}, {"command": ["etoro"]},
    {"file_path": None, "content": "ETORO_ALLOW_REAL=true"},
    {"file_path": 3, "new_string": "ETORO_ALLOW_REAL=true"},
    {"file_path": ".env", "content": None}, {"file_path": ".env", "new_string": 7},
    {"file_path": ".env", "patch_body": None}, {"file_path": ".env", "patch_body": 7},
])
def test_the_etoro_rule_never_raises_on_malformed_input(ti):
    # Called directly: evaluate() would swallow an exception and allow.
    assert _ETORO(ti) is None


@pytest.mark.parametrize("ti", [
    {"account": "real"}, {"account": "REAL"}, {"environment": " real "},
    {"account": "real", "symbol": None, "amount": "x"},
])
def test_an_explicit_real_marker_is_always_denied(ti):
    assert _is_deny(_ETORO(ti))


def test_the_claude_matcher_routes_mcp_tools_to_the_hook():
    alternatives = _guardrail_matcher(_SETTINGS_JSON).split("|")
    assert "mcp__.*" in alternatives and "PowerShell" in alternatives
```

1d. In `tests/hooks/fixtures/payloads.json` add, after the `Write` entry (comma after `Write`'s closing brace):

```json
  "mcp__etoro-public-api-mcp__get-my-portfolio-summary": {
    "tool_name": "mcp__etoro-public-api-mcp__get-my-portfolio-summary",
    "tool_input": {
      "account": "demo"
    }
  }
```

1e. In `tests/hooks/test_codex_mirror.py`, add after `test_codex_hooks_mirror_the_claude_guardrail_and_session_hooks`:

```python
def _guardrail_matcher(hooks: dict) -> str:
    return next(e["matcher"] for e in hooks["PreToolUse"]
                if any("guardrails.py" in h["command"] for h in e["hooks"]))


def test_both_guardrail_matchers_route_mcp_tools():
    """v159: the eToro rule is reached through mcp__* tool names. Codex has its
    own tool names, so its matcher is not a copy of Claude's."""
    claude = json.loads((_ROOT / ".claude" / "settings.json").read_text())["hooks"]
    codex = json.loads((_ROOT / ".codex" / "hooks.json").read_text())["hooks"]
    assert "mcp__.*" in _guardrail_matcher(claude).split("|")
    assert _guardrail_matcher(codex) == "Bash|apply_patch|Edit|Write|mcp__.*"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_guardrails.py`
Expected: FAIL — `AttributeError: ... '_rule_etoro_real_account'` at module import of the test (`_ETORO = ...`), so every test in the file errors.

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: FAIL — `test_both_guardrail_matchers_route_mcp_tools`.

- [ ] **Step 3: Implement the rule**

In `.claude/hooks/guardrails.py`, insert this block immediately **before** the comment `# Codex edits files through apply_patch, whose tool_input.command is the patch`:

```python
# --- v159: eToro is demo only until stage 3 (docs/claude/etoro-roadmap.md) ---
# One rule over three inputs: an eToro MCP call, a shell command, and an edit
# of a .env* file. evaluate() fails open on ANY exception, so this rule is a
# total function: every value is isinstance-checked before use, and
# tests/hooks/test_guardrails.py calls it directly with malformed input.
ETORO_MCP_FRAGMENT = "etoro"
ETORO_UNLOCK_KEYS = ("ETORO_ALLOW_REAL", "ETORO_REAL_SIGNOFF")
_ETORO_ACCOUNT_KEYS = ("account", "environment")
_ETORO_ROUTE_KEYS = ("path", "url", "route")
_ETORO_TRUTHY = frozenset({"true", "1", "yes", "on"})
_ETORO_URL_RE = re.compile(r"https?://[^\s\"'`/]*etoro[^\s\"'`]*", re.IGNORECASE)
_HTTP_CLIENT_RE = re.compile(
    r"\b(?:curl|wget|Invoke-RestMethod|Invoke-WebRequest|irm|iwr|requests|httpx|urllib)\b",
    re.IGNORECASE)
_TRADING_PATH_RE = re.compile(r"/trading/[^\s\"'`]*", re.IGNORECASE)
_ENV_UNLOCK_RE = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(" + "|".join(ETORO_UNLOCK_KEYS) + r")[ \t]*=(.*)$",
    re.MULTILINE)
_ETORO_DENY_TAIL = (
    " Real money is stage 3 of docs/claude/etoro-roadmap.md; until then every "
    "eToro call is demo only. Claude and Codex never unlock it: the partner "
    "does, on the admin Settings page.")


def _is_real_trading_path(text: str) -> bool:
    """`text` names an eToro trading route with no `/demo/` in it."""
    return any("/demo/" not in m.group(0).lower()
               for m in _TRADING_PATH_RE.finditer(text))


def _etoro_mcp_reason(ti: dict) -> str | None:
    for key in _ETORO_ACCOUNT_KEYS:
        value = ti.get(key)
        if isinstance(value, str) and value.strip().lower() == "real":
            return f"an eToro MCP call with `{key}: real`."
    for key in _ETORO_ROUTE_KEYS:
        value = ti.get(key)
        if isinstance(value, str) and _is_real_trading_path(value):
            return f"an eToro MCP call on the real trading route `{value[:120]}`."
    return None


def _etoro_shell_reason(ti: dict) -> str | None:
    cmd = ti.get("command")
    if not isinstance(cmd, str) or ETORO_MCP_FRAGMENT not in cmd.lower():
        return None
    by_url = any(_is_real_trading_path(url) for url in _ETORO_URL_RE.findall(cmd))
    by_client = bool(_HTTP_CLIENT_RE.search(cmd)) and _is_real_trading_path(cmd)
    if by_url or by_client:
        return "a shell request to an eToro trading endpoint without `/demo/` in its path."
    return None


def _is_env_file(path: object) -> bool:
    if not isinstance(path, str):
        return False
    return path.replace("\\", "/").rsplit("/", 1)[-1].startswith(".env")


def _written_text(ti: dict) -> str:
    """What an edit writes: an apply_patch section's ADDED lines, an Edit's
    new_string, or a Write's content. A removed line never counts."""
    body = ti.get("patch_body")
    if isinstance(body, str):
        return "\n".join(line[1:] for line in body.splitlines() if line.startswith("+"))
    for key in ("new_string", "content"):
        value = ti.get(key)
        if isinstance(value, str):
            return value
    return ""


def _is_unlock_value(key: str, raw: str) -> bool:
    value = raw.split(" #", 1)[0].strip().strip("\"'").strip()
    if key == "ETORO_ALLOW_REAL":
        return value.lower() in _ETORO_TRUTHY
    return value != ""


def _etoro_env_reason(ti: dict) -> str | None:
    if not _is_env_file(ti.get("file_path")):
        return None
    for key, raw in _ENV_UNLOCK_RE.findall(_written_text(ti)):
        if _is_unlock_value(key, raw):
            return f"an edit that sets `{key}` to an unlock value in a .env file."
    return None


_ETORO_CHECKS = (_etoro_env_reason, _etoro_shell_reason, _etoro_mcp_reason)


def _rule_etoro_real_account(ti: object):
    """Deny any eToro real-account call or real-money unlock. Total: returns
    None for anything it cannot read, never raises."""
    if not isinstance(ti, dict):
        return None
    for check in _ETORO_CHECKS:
        reason = check(ti)
        if reason is not None:
            return _deny("Denied: " + reason + _ETORO_DENY_TAIL)
    return None
```

- [ ] **Step 4: Wire it into apply_patch, the shell and edit rules, and the prefix table**

Replace `_PATCH_PATH_RULES` and `_rule_apply_patch` with:

```python
# Rule-major order: every path meets the deny rules before any path can warn.
# Each rule receives {"file_path": path, "patch_body": that file's section}, so
# a rule that reads what is written (the eToro unlock, v159) sees only the
# section of its own file.
_PATCH_PATH_RULES = (_rule_worktree_write, _rule_plan_doc_shape,
                     _rule_etoro_real_account, _rule_codex_mirror_reminder)


def _patch_sections(patch: str) -> list[tuple[str, str]]:
    """(path, section text) per file header; a section runs to the next header.
    `Update File: a` + `Move to: b` gives `a` an empty section and `b` the hunks."""
    matches = list(_PATCH_PATH_RE.finditer(patch))
    sections = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(patch)
        sections.append((m.group(1).strip(), patch[m.end():end]))
    return sections


def _rule_apply_patch(ti: dict):
    patch = ti.get("command")
    if not isinstance(patch, str):
        return None
    sections = _patch_sections(patch)
    for rule in _PATCH_PATH_RULES:
        for path, body in sections:
            decision = rule({"file_path": path, "patch_body": body})
            if decision is not None:
                return decision
    return None
```

Replace ER5's `_SHELL_RULES` and the `_RULES` literal with (the comments above them stay):

```python
_SHELL_RULES = [_rule_protected_branch_delete, _rule_closed_preregistration,
                _rule_screen_rerun, _rule_recursive_grep_from_root,
                _rule_etoro_real_account, _rule_bare_pytest, _rule_cat_big_doc]

_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": _SHELL_RULES,
    "PowerShell": _SHELL_RULES,
    "Read": [_rule_huge_implemented_plan, _rule_read_big_doc],
    "Edit": [_rule_worktree_write, _rule_etoro_real_account,
             _rule_codex_mirror_reminder],
    "Write": [_rule_worktree_write, _rule_plan_doc_shape, _rule_etoro_real_account,
              _rule_codex_mirror_reminder],
    "NotebookEdit": [_rule_worktree_write],
    "apply_patch": [_rule_apply_patch],
}

# MCP tools are named mcp__<server>__<tool>, so no exact _RULES key can match a
# server's whole tool set. A fragment of the SERVER segment selects the rules;
# the eToro server is etoro-public-api-mcp, or plugin_etoro_etoro as a plugin.
_PREFIX_RULES = ((ETORO_MCP_FRAGMENT, (_rule_etoro_real_account,)),)


def _mcp_server(tool: str) -> str:
    """The lower-cased server segment of `mcp__<server>__<tool>`, else ''."""
    parts = tool.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return ""
    return parts[1].lower()


def _rules_for(tool: object):
    """The rules for `tool`: its exact _RULES entry, else its MCP prefix rules."""
    if not isinstance(tool, str):
        return ()
    rules = _RULES.get(tool)
    if rules is not None:
        return rules
    server = _mcp_server(tool)
    for fragment, prefix_rules in _PREFIX_RULES:
        if server and fragment in server:
            return prefix_rules
    return ()
```

In `evaluate()`, change the loop line only:

```python
        for rule in _rules_for(tool):
```

- [ ] **Step 5: Matchers**

`.claude/settings.json`, the guardrails entry:

```json
        "matcher": "Glob|Read|Edit|Write|NotebookEdit|Bash|PowerShell|mcp__.*",
```

`.codex/hooks.json`, the PreToolUse entry:

```json
        "matcher": "Bash|apply_patch|Edit|Write|mcp__.*",
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_guardrails.py`
Expected: PASS, `0 failed`, `0 xfailed`. The pre-existing apply_patch tests (`test_apply_patch_*`) still pass: `_patch_sections` yields the same paths `_PATCH_PATH_RE.findall` did.

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS.

Run: `python -m radon cc -s -n C "$WT/.claude/hooks/guardrails.py"`
Expected: no output (`_etoro_mcp_reason` is the largest new function, B).

Smoke the live hook entry point once (stdin JSON, exit 0, a deny printed):

```bash
echo '{"tool_name":"mcp__etoro-public-api-mcp__prepare-trade","tool_input":{"account":"real"}}' | python "$WT/.claude/hooks/guardrails.py"
```
Expected: one JSON line with `"permissionDecision": "deny"` and `etoro-roadmap.md` in the reason.

- [ ] **Step 7: Mirror into `AGENTS.md`**

Replace the paragraph that starts `Both agents enforce these habits with one hook,` and ends `never route around it with another tool.` with:

```markdown
Both agents enforce these habits with one hook, `.claude/hooks/guardrails.py`,
wired for Codex in `.codex/hooks.json` (with the same session-status
`SessionStart` hook). It denies `grep -r` from the repo root, worktree writes
from the main tree, protected-branch deletion, closed-pre-registration backtest
knobs, a re-run or full-universe dry run of a screened idea
(`_rule_screen_rerun`), malformed spec/plan names, and any eToro real-account
call or real-money unlock (`_rule_etoro_real_account`: an eToro MCP call with
`account: real` or a real trading route, a shell request to an eToro trading
endpoint without `/demo/`, or a `.env*` edit that sets `ETORO_ALLOW_REAL` true
or `ETORO_REAL_SIGNOFF` non-empty). It warns on bare `pytest`, `cat` of the
big docs, and edits to Claude setup (the mirror reminder). Claude's shell rules
also run on its `PowerShell` tool, and both matchers route every `mcp__*` tool
to the hook (Codex's matcher is `Bash|apply_patch|Edit|Write|mcp__.*`). Codex
runs a new or changed hook only after it is trusted in `/hooks`: if a guardrail
change has not been reviewed there, follow its rules by hand until it is. A
deny is final: never route around it with another tool.
```

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git -C "$WT" add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py tests/hooks/fixtures/payloads.json .claude/settings.json .codex/hooks.json tests/hooks/test_codex_mirror.py AGENTS.md
git -C "$WT" commit -m "feat(v159): ER6 -- hook denies eToro real-account calls and unlocks

_rule_etoro_real_account is total (never raises; evaluate fails open) and
denies an eToro MCP call with account real or a real trading route, a
Bash/PowerShell request to an eToro trading endpoint without /demo/, and a
.env* edit that writes an unlock value. MCP tools reach it through a new
prefix table keyed on the server segment; apply_patch rules now see each
file's own patch section. Claude and Codex matchers both route mcp__*.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER7: Settings `ETORO_ALLOW_REAL`/`ETORO_REAL_SIGNOFF` and `swingbot/core/broker/guard.py`

**Model:** sonnet — a new leaf module with a small pure API, two schema fields and doc counts; the only subtlety (reload isolation in the SIGHUP test) is spelled out below.

Spec § B2 "Code guard" and "Settings". `assert_demo(account)` raises `RealAccountBlocked` unless the account is `"demo"` or real trading is unlocked: `ETORO_ALLOW_REAL` true **and** `ETORO_REAL_SIGNOFF` an ISO date (`YYYY-MM-DD`) no later than today in Europe/Berlin. Both are read from the hot-reloaded `swingbot.config` globals at call time, never `os.environ`. The package holds **only** `__init__.py` and `guard.py` after this plan; `sizing.py` and `pre_open.py` are v160's.

**Files:**
- Modify: `swingbot/config.py` (eToro section, ~l.127-136)
- Modify: `.env.example` (after l.425, `ETORO_API_KEY=`)
- Modify: `tests/infra/test_config_etoro.py`
- Create: `swingbot/core/broker/__init__.py`
- Create: `swingbot/core/broker/guard.py`
- Create: `tests/broker/__init__.py`
- Create: `tests/broker/test_guard.py`
- Modify: `docs/claude/architecture.md` (module map, ~l.17 and after the `presentation/` sentence)
- Modify: `CLAUDE.md` (~l.85, package count; zero net lines)
- Modify: `AGENTS.md` (~l.304, package count)

**Interfaces:**
- Consumes: `swingbot.config.Field` (`type="checkbox"` casts through `_CASTERS["checkbox"]`, `str(v).lower() == "true"`; `type="text"` stays a `str`); `config.reload()`, `config.ENV_PATH`, `config._ENV_MTIME`; `swingbot.core.market.session.BERLIN_TZ`.
- Produces (ER8, ER9, ER11 and v160 rely on these):
  - `class RealAccountBlocked(RuntimeError)`
  - `signoff_valid(raw: object, today: datetime.date | None = None) -> bool` — `True` only for a `str` matching `^\d{4}-\d{2}-\d{2}$` (after `strip()`) that parses as a date `<= today` (default: today in Europe/Berlin).
  - `real_unlocked(today: datetime.date | None = None) -> bool` — `config.ETORO_ALLOW_REAL is True and signoff_valid(config.ETORO_REAL_SIGNOFF, today)`, read at call time.
  - `assert_demo(account: str) -> None`
  - `_berlin_today() -> datetime.date` (module-level so tests can monkeypatch it)
  - `Field("ETORO_ALLOW_REAL", ..., type="checkbox", default="false")`, `Field("ETORO_REAL_SIGNOFF", ..., type="text", default="")`, both in section `"eToro Paper Trading"`, both hot-reloadable, neither sensitive.

- [ ] **Step 1: Write the failing tests**

Append to `tests/infra/test_config_etoro.py`:

```python
def test_real_money_lock_fields_are_declared_locked_by_default():
    keys = {f.key: f for f in config.FIELDS}
    allow, signoff = keys["ETORO_ALLOW_REAL"], keys["ETORO_REAL_SIGNOFF"]
    assert allow.section == signoff.section == "eToro Paper Trading"
    assert allow.type == "checkbox" and allow.default == "false"
    assert signoff.type == "text" and signoff.default == ""
    assert allow.hot_reloadable and signoff.hot_reloadable
    assert not allow.sensitive and not signoff.sensitive
    assert "stage 3" in allow.help and "etoro-roadmap.md" in allow.help
    assert "ETORO_REAL_SIGNOFF" in allow.help


def test_real_money_lock_globals_have_their_cast_types():
    assert isinstance(config.ETORO_ALLOW_REAL, bool)
    assert isinstance(config.ETORO_REAL_SIGNOFF, str)
```

Create `tests/broker/__init__.py` empty.

Create `tests/broker/test_guard.py`:

```python
"""swingbot.core.broker.guard: eToro is demo only until stage 3 (v159).

Every case sets both settings through monkeypatch, so nothing here depends on
the developer's .env. The SIGHUP case reloads from a tmp_path .env and pins
every global the reload touches, the way tests/admin/conftest.py does."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.broker import guard
from swingbot.core.broker.guard import RealAccountBlocked, assert_demo

TODAY = dt.date(2026, 10, 11)


@pytest.fixture
def lock(monkeypatch):
    """Sets (ETORO_ALLOW_REAL, ETORO_REAL_SIGNOFF); starts locked."""
    def _set(allow, signoff):
        monkeypatch.setattr(config, "ETORO_ALLOW_REAL", allow)
        monkeypatch.setattr(config, "ETORO_REAL_SIGNOFF", signoff)
    _set(False, "")
    return _set


@pytest.fixture(autouse=True)
def berlin_today(monkeypatch):
    monkeypatch.setattr(guard, "_berlin_today", lambda: TODAY)


def test_real_account_blocked_is_a_runtime_error():
    assert issubclass(RealAccountBlocked, RuntimeError)


def test_demo_passes_while_locked(lock):
    assert assert_demo("demo") is None


def test_real_is_blocked_while_locked(lock):
    with pytest.raises(RealAccountBlocked, match="etoro-roadmap.md"):
        assert_demo("real")


def test_the_flag_without_a_signoff_stays_blocked(lock):
    lock(True, "")
    with pytest.raises(RealAccountBlocked):
        assert_demo("real")


def test_a_signoff_without_the_flag_stays_blocked(lock):
    lock(False, "2026-10-01")
    with pytest.raises(RealAccountBlocked):
        assert_demo("real")


def test_a_future_dated_signoff_stays_blocked(lock):
    lock(True, "2026-10-12")
    with pytest.raises(RealAccountBlocked):
        assert_demo("real")


@pytest.mark.parametrize("signoff", ["2026-10-11", "2026-01-01", " 2026-10-11 "])
def test_flag_and_a_past_or_today_signoff_unlock_real(lock, signoff):
    lock(True, signoff)
    assert assert_demo("real") is None


@pytest.mark.parametrize("signoff", ["2026-13-01", "20261011", "2026-10-1", "yesterday",
                                     " ", "2026-10-11T00:00", None, 20261011])
def test_a_malformed_signoff_stays_blocked(lock, signoff):
    lock(True, signoff)
    with pytest.raises(RealAccountBlocked):
        assert_demo("real")


@pytest.mark.parametrize("account", ["Demo", "DEMO", " demo", "", None, "paper"])
def test_anything_but_the_exact_demo_account_is_blocked_while_locked(lock, account):
    with pytest.raises(RealAccountBlocked):
        assert_demo(account)


def test_signoff_valid_takes_an_explicit_today():
    assert guard.signoff_valid("2026-10-11", dt.date(2026, 10, 11)) is True
    assert guard.signoff_valid("2026-10-11", dt.date(2026, 10, 10)) is False


def test_real_unlocked_reads_the_settings_at_call_time(lock):
    assert guard.real_unlocked() is False
    lock(True, "2026-10-01")
    assert guard.real_unlocked() is True


def test_os_environ_alone_never_unlocks(lock, monkeypatch):
    monkeypatch.setenv("ETORO_ALLOW_REAL", "true")
    monkeypatch.setenv("ETORO_REAL_SIGNOFF", "2026-10-01")
    assert guard.real_unlocked() is False


def _reload_from(monkeypatch, tmp_path, text):
    env = tmp_path / ".env"
    env.write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    config.reload()


def test_a_sighup_reload_flips_the_guard(monkeypatch, tmp_path):
    """The SIGHUP handler (swingbot/bot_core.py) calls config.reload(). The
    guard must follow it with no restart and no os.environ read."""
    for key in guard.UNLOCK_KEYS:
        monkeypatch.setenv(key, "")                           # restores os.environ
        monkeypatch.setattr(config, key, getattr(config, key))  # restores the global
    for attr in ("_ENV_MTIME", "_DOTENV_LOADED", "_DOTENV_FROM_CANONICAL_PATH"):
        monkeypatch.setattr(config, attr, getattr(config, attr))  # reload() reassigns these

    _reload_from(monkeypatch, tmp_path,
                 "ETORO_ALLOW_REAL=true\nETORO_REAL_SIGNOFF=2026-10-01\n")
    assert guard.real_unlocked() is True
    assert_demo("real")

    _reload_from(monkeypatch, tmp_path,
                 "ETORO_ALLOW_REAL=false\nETORO_REAL_SIGNOFF=2026-10-01\n")
    assert guard.real_unlocked() is False
    with pytest.raises(RealAccountBlocked):
        assert_demo("real")


def test_the_broker_package_holds_only_the_guard():
    # v160 adds sizing.py and pre_open.py; v159 ships the guard alone.
    from pathlib import Path
    pkg = Path(guard.__file__).parent
    assert sorted(p.name for p in pkg.glob("*.py")) == ["__init__.py", "guard.py"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.broker'`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/infra/test_config_etoro.py`
Expected: FAIL — `KeyError: 'ETORO_ALLOW_REAL'`.

- [ ] **Step 3: Add the two settings**

In `swingbot/config.py`, change the section comment and add the two fields directly after the `ETORO_API_KEY` field:

```python
    # --- eToro paper trading (credentials, plus the stage-3 lock broker/guard.py reads) ---
```

```python
    Field("ETORO_ALLOW_REAL", "ETORO_ALLOW_REAL", "eToro Paper Trading",
          "Allow real-money eToro orders", type="checkbox", default="false",
          help="Real money is stage 3 of docs/claude/etoro-roadmap.md, never earlier. "
               "Has no effect unless ETORO_REAL_SIGNOFF also holds the sign-off date, so "
               "one box can never unlock real trading. Turning it on here asks you to "
               "type that date."),
    Field("ETORO_REAL_SIGNOFF", "ETORO_REAL_SIGNOFF", "eToro Paper Trading",
          "Real-money sign-off date (YYYY-MM-DD)", default="",
          help="The day stage 3 was signed off, Europe/Berlin. Empty, malformed or "
               "future-dated keeps real money locked. A lock, not a performance test."),
```

In `.env.example`, directly after `ETORO_API_KEY=` (the hook allows these lines: `false` and empty are not unlock values):

```
# Stage-3 lock (v159): real money stays off unless BOTH are set. The admin
# Settings page is the unlock path; scripts/ops/env_set.py refuses both keys.
ETORO_ALLOW_REAL=false
ETORO_REAL_SIGNOFF=
```

- [ ] **Step 4: Create the package**

`swingbot/core/broker/__init__.py`:

```python
"""Broker integration (v159). Holds only the account guard for now; v160's
eToro demo mirror adds the client, sizing and pre-open checks beside it."""
```

`swingbot/core/broker/guard.py`:

```python
"""Broker-account guard (v159): eToro is demo only until stage 3.

Stage numbering is docs/claude/etoro-roadmap.md's (1 keys, 2 demo, 3 real).
Every eToro call goes through assert_demo first; the AST scan in
tests/broker/test_guard.py fails any module that touches eToro without it.
Both settings are read from the hot-reloaded swingbot.config globals at call
time, so a SIGHUP reload takes effect on the next call. os.environ is never
read here.
"""
from __future__ import annotations

import datetime as dt
import re

from swingbot import config
from swingbot.core.market.session import BERLIN_TZ

DEMO_ACCOUNT = "demo"
UNLOCK_KEYS = ("ETORO_ALLOW_REAL", "ETORO_REAL_SIGNOFF")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RealAccountBlocked(RuntimeError):
    """An eToro call aimed at a non-demo account while real money is locked."""


def _berlin_today() -> dt.date:
    return dt.datetime.now(BERLIN_TZ).date()


def signoff_valid(raw: object, today: dt.date | None = None) -> bool:
    """True for an ISO date (YYYY-MM-DD) no later than `today` (Berlin)."""
    if not isinstance(raw, str) or not _ISO_DATE_RE.match(raw.strip()):
        return False
    try:
        day = dt.date.fromisoformat(raw.strip())
    except ValueError:
        return False
    return day <= (today or _berlin_today())


def real_unlocked(today: dt.date | None = None) -> bool:
    """Stage 3 is unlocked: the flag is on AND the sign-off date is valid."""
    allow = getattr(config, "ETORO_ALLOW_REAL", False)
    signoff = getattr(config, "ETORO_REAL_SIGNOFF", "")
    return allow is True and signoff_valid(signoff, today)


def assert_demo(account: str) -> None:
    """Raise RealAccountBlocked unless account == "demo", or real trading is
    explicitly unlocked (ETORO_ALLOW_REAL=true AND ETORO_REAL_SIGNOFF set to
    an ISO date no later than today, Europe/Berlin)."""
    if account == DEMO_ACCOUNT or real_unlocked():
        return
    raise RealAccountBlocked(
        f"eToro account {account!r} refused: real money is stage 3 of "
        "docs/claude/etoro-roadmap.md and is locked (ETORO_ALLOW_REAL plus a valid "
        "ETORO_REAL_SIGNOFF, set by the partner on the admin Settings page).")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/infra/test_config_etoro.py`
Expected: PASS.

Run: `python "$WT/scripts/dev/testrun.py" file tests/infra/test_env_example_sync.py`
Expected: PASS (both new keys present in `.env.example`, nothing extra).

Run: `python "$WT/scripts/dev/testrun.py" file tests/admin/test_api_v1_system_settings.py`
Expected: PASS (the Settings document now carries two more fields; no test pins the field count).

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/guard.py"`
Expected: no output.

- [ ] **Step 6: Re-count the packages and correct the docs**

Count, never "+1":

```bash
ls -d "$WT"/swingbot/core/*/ | grep -v __pycache__ | wc -l
ls "$WT"/swingbot/core/*.py
```
Expected: `13`, and the flat files `__init__.py` and `risk_limits.py`. If the count differs, write the counted number below instead of "thirteen" and name the difference in the commit message.

`docs/claude/architecture.md` — replace

```
  `core/` is fully packaged (v27 repo restructure, 2026-08-15) — no flat
  `.py` modules remain under it, only ten subpackages: `core/marketdata/`
```

with

```
  `core/` is packaged (v27 repo restructure, 2026-08-15): thirteen
  subpackages plus one flat module, `risk_limits.py` (counted with `ls`, v159). `core/marketdata/`
```

and directly after the sentence ending `Nothing outside it may touch \`discord.Color\`; its AST guard enforces that boundary.` insert:

```
  `core/broker/` (v159) is the broker-account boundary: `guard.py:assert_demo`
  raises `RealAccountBlocked` for any eToro account but `"demo"` unless stage 3
  is unlocked (`ETORO_ALLOW_REAL` plus a valid `ETORO_REAL_SIGNOFF`, read from
  the hot-reloaded config). v160 adds the eToro client, `sizing.py` and
  `pre_open.py` beside it; `tests/broker/test_guard.py` scans for eToro code
  that skips the guard.
```

`CLAUDE.md` (same two lines, zero net change) — replace

```
- **`swingbot/core/` is eleven packages, no flat modules** — map:
```

with

```
- **`swingbot/core/` is thirteen packages plus `risk_limits.py`** — map:
```

Then: `wc -l "$WT/CLAUDE.md"` — Expected: `199` (ER1's row; this edit adds none). Anything above 199 is a failure.

`AGENTS.md` — replace

```
`swingbot/core/` is eleven packages with no flat modules: `marketdata/`,
`market/`, `planning/`, `backtesting/`, `tracking/`, `infra/`, `edge/`,
`scanning/`, `analytics/`, `charts/`, `presentation/`. `architecture.md` says
which modules live where.
```

with

```
`swingbot/core/` is thirteen packages plus one flat module (`risk_limits.py`):
`marketdata/`, `market/`, `planning/`, `backtesting/`, `tracking/`, `infra/`,
`edge/`, `scanning/`, `analytics/`, `charts/`, `presentation/`, `db/` and
`broker/` (v159: `guard.py:assert_demo` keeps eToro demo only).
`architecture.md` says which modules live where.
```

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git -C "$WT" add swingbot/config.py .env.example tests/infra/test_config_etoro.py swingbot/core/broker/__init__.py swingbot/core/broker/guard.py tests/broker/__init__.py tests/broker/test_guard.py docs/claude/architecture.md CLAUDE.md AGENTS.md
git -C "$WT" commit -m "feat(v159): ER7 -- broker/guard.py assert_demo and the stage-3 lock settings

ETORO_ALLOW_REAL (checkbox, false) and ETORO_REAL_SIGNOFF (ISO date, empty)
join the eToro section; assert_demo raises RealAccountBlocked for any
non-demo account unless both unlock stage 3, read from hot-reloaded config
(SIGHUP test included). New package swingbot/core/broker/ holds only the
guard. Package count corrected from ls: 13 packages plus risk_limits.py
(CLAUDE.md, AGENTS.md and architecture.md all said otherwise).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER8: AST scan — eToro code must call `assert_demo`

**Model:** sonnet — a self-contained AST walker inside one test file, with tmp_path fixtures that pin each trigger.

Spec § B2 Tests. The scan fails when a module under `swingbot/`, `bot.py`, `admin_ui.py` or `scripts/` (a) has a string constant containing `etoro.com`, (b) imports a module whose dotted name contains `etoro`, or (c) reads `ETORO_USER_KEY`/`ETORO_API_KEY` (a name, an attribute or a string constant) **without** also calling `assert_demo` (as `assert_demo(...)` or `<x>.assert_demo(...)`). Exempt: `swingbot/core/broker/guard.py` and `swingbot/config.py` (the field declarations). It passes trivially today (no module touches eToro; all 451 scanned files parse) and guards v160's client. Dynamic URLs evade it; the spec accepts that (§ Risks).

**Files:**
- Modify: `tests/broker/test_guard.py` (append)

**Interfaces:**
- Consumes (ER7): `tests/broker/test_guard.py`, `swingbot/core/broker/guard.py` (exempt path).
- Produces: `SCAN_ROOTS = ("swingbot", "bot.py", "admin_ui.py", "scripts")`, `EXEMPT = {"swingbot/core/broker/guard.py", "swingbot/config.py"}`, `unguarded_etoro_modules(root: Path) -> list[str]` (repo-relative POSIX paths; an unparsable file is reported as `"<path> (unparsable)"`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/broker/test_guard.py`:

```python
# --- the AST scan: every module that touches eToro calls assert_demo ---------

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("swingbot", "bot.py", "admin_ui.py", "scripts")
EXEMPT = {"swingbot/core/broker/guard.py", "swingbot/config.py"}
_KEY_NAMES = frozenset({"ETORO_USER_KEY", "ETORO_API_KEY"})


def _const_hit(node: ast.Constant) -> bool:
    value = node.value
    return isinstance(value, str) and ("etoro.com" in value.lower() or value in _KEY_NAMES)


def _import_hit(node: ast.Import | ast.ImportFrom) -> bool:
    return any("etoro" in alias.name.lower() for alias in node.names)


def _from_hit(node: ast.ImportFrom) -> bool:
    return "etoro" in (node.module or "").lower() or _import_hit(node)


_HITS = {
    ast.Constant: _const_hit,
    ast.Import: _import_hit,
    ast.ImportFrom: _from_hit,
    ast.Name: lambda node: node.id in _KEY_NAMES,
    ast.Attribute: lambda node: node.attr in _KEY_NAMES,
}


def _touches_etoro(tree: ast.AST) -> bool:
    return any(_HITS[type(node)](node) for node in ast.walk(tree) if type(node) in _HITS)


def _is_assert_demo_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return ((isinstance(func, ast.Name) and func.id == "assert_demo")
            or (isinstance(func, ast.Attribute) and func.attr == "assert_demo"))


def _scan_files(root: Path):
    for entry in SCAN_ROOTS:
        path = root / entry
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from (p for p in sorted(path.rglob("*.py"))
                        if "__pycache__" not in p.parts)


def unguarded_etoro_modules(root: Path) -> list[str]:
    """Repo-relative paths of scanned modules that touch eToro without
    calling assert_demo. An unparsable module is reported, never skipped."""
    bad = []
    for path in _scan_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in EXEMPT:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            bad.append(f"{rel} (unparsable)")
            continue
        if _touches_etoro(tree) and not any(map(_is_assert_demo_call, ast.walk(tree))):
            bad.append(rel)
    return bad


def _module(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.mark.parametrize("body", [
    'BASE = "https://public-api.etoro.com"\n',
    "from swingbot.core.broker import etoro_client\n",
    "from swingbot.core.broker.etoro_client import EtoroClient\n",
    "import etoro\n",
    "from swingbot import config\nKEY = config.ETORO_API_KEY\n",
    'import os\nKEY = os.environ["ETORO_USER_KEY"]\n',
    # A mention of the guard is not a call to it.
    'from swingbot.core.broker.guard import assert_demo\nH = "etoro.com"\n',
])
def test_etoro_code_without_the_guard_is_flagged(tmp_path, body):
    _module(tmp_path, "swingbot/core/broker/client.py", body)
    assert unguarded_etoro_modules(tmp_path) == ["swingbot/core/broker/client.py"]


def test_etoro_code_that_calls_the_guard_passes(tmp_path):
    _module(tmp_path, "scripts/ops/probe.py",
            "from swingbot.core.broker.guard import assert_demo\n"
            'BASE = "https://public-api.etoro.com"\n'
            "def go(account):\n    assert_demo(account)\n")
    _module(tmp_path, "bot.py",
            "from swingbot.core.broker import guard\n"
            'URL = "https://public-api.etoro.com"\nguard.assert_demo("demo")\n')
    assert unguarded_etoro_modules(tmp_path) == []


def test_the_exempt_files_are_not_flagged(tmp_path):
    _module(tmp_path, "swingbot/config.py", 'KEY = "ETORO_API_KEY"\n')
    _module(tmp_path, "swingbot/core/broker/guard.py", 'HOST = "etoro.com"\n')
    assert unguarded_etoro_modules(tmp_path) == []


def test_files_outside_the_scan_roots_are_ignored(tmp_path):
    _module(tmp_path, "tests/test_x.py", 'HOST = "https://public-api.etoro.com"\n')
    _module(tmp_path, "swingbot/__pycache__/x.py", 'HOST = "etoro.com"\n')
    assert unguarded_etoro_modules(tmp_path) == []


def test_an_unparsable_module_is_reported(tmp_path):
    _module(tmp_path, "scripts/broken.py", "def (:\n")
    assert unguarded_etoro_modules(tmp_path) == ["scripts/broken.py (unparsable)"]


def test_no_module_in_the_repo_touches_etoro_without_the_guard():
    assert unguarded_etoro_modules(ROOT) == []
```

- [ ] **Step 2: Run the tests to verify the scanner's own cases fail first**

Temporarily change the last line of `unguarded_etoro_modules` to `return []` and run:

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: FAIL — the seven `test_etoro_code_without_the_guard_is_flagged` cases and `test_an_unparsable_module_is_reported`; everything else passes. Restore `return bad`.

- [ ] **Step 3: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS, `0 failed`, `0 xfailed`. If `test_no_module_in_the_repo_touches_etoro_without_the_guard` lists a file, it is real eToro code without the guard: stop and report it (`BLOCKED:`), never add it to `EXEMPT` on your own.

Run: `python -m radon cc -s -n C "$WT/tests/broker/test_guard.py"`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git -C "$WT" add tests/broker/test_guard.py
git -C "$WT" commit -m "test(v159): ER8 -- AST scan fails eToro code that skips assert_demo

Scans swingbot/, bot.py, admin_ui.py and scripts/ for an etoro.com string,
an import naming etoro, or a read of ETORO_USER_KEY/ETORO_API_KEY without
an assert_demo call; guard.py and config.py are exempt. Passes trivially
today and guards v160's client.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

