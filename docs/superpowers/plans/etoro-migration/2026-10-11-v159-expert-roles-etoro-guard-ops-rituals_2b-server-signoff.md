# v159 Four expert seats, a demo-only eToro guard, and the ops/UI rituals. Part 2b: server-side sign-off check (ER9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md` (§ B2, "Admin UI unlock path")
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md` — its Global Constraints, Parallelisation and Task ledger apply. ER9 was split out of part 2 only to keep that file under the 1500-line cap; part 2's "Conventions for every task" (the `WT` worktree root, no `cd`, `testrun.py file`, isolated `.env` fixtures, complexity < 15) apply here unchanged.

# Phase B — eToro demo-only guard (continued)

### Task ER9: `save_settings` refuses an unlock without a valid sign-off; `env_set.py` refuses both keys

**Model:** sonnet — one helper beside a complexity-21 function it must not touch, three call sites and flag-gated tests through the existing isolated fixtures.

Spec § B2 "Admin UI unlock path". A body that would leave `ETORO_ALLOW_REAL` on without a valid `ETORO_REAL_SIGNOFF` gets HTTP 400 `real_money_signoff`, on save **and** preview (same rule, so the shown diff and the write agree). The paste-import route gets the same check: it writes through the same `.env` and would otherwise unlock with no sign-off. A body that touches neither key is never blocked, so a hand-edited VM `.env` does not freeze unrelated saves. `_validate` (cc 21) is not changed. `scripts/ops/env_set.py` refuses both keys outright; `--get` still reads them.

**Files:**
- Modify: `swingbot/admin/api_v1/system.py` (new `_real_money_problem` after `_validate`; `preview_settings`, `save_settings`, `import_settings`)
- Modify: `tests/admin/test_api_v1_system_settings.py` (append)
- Modify: `scripts/ops/env_set.py` (`REFUSED_KEYS`, `main`)
- Modify: `tests/scripts/test_env_set.py` (append; add `import pytest`)

**Interfaces:**
- Consumes (ER7): `guard.signoff_valid(raw, today=None) -> bool`, `guard.UNLOCK_KEYS`; existing `_truthy`, `_validate`, `error`, `helpers._read_env_values() -> dict`.
- Produces (ER10's error path relies on the code): `_real_money_problem(values: Mapping, existing: Mapping) -> tuple[str, str] | None`, returning `("real_money_signoff", <message>)`; HTTP 400 code `real_money_signoff`; `env_set.REFUSED_KEYS = frozenset({"ETORO_ALLOW_REAL", "ETORO_REAL_SIGNOFF"})`; `env_set.main` returns `2` for a write to either.
- Ledger note: the ledger wrote the second parameter as `env_text: str`. It is the parsed on-disk values (`_read_env_values()`), which every call site already has; no other task calls the helper.

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_v1_system_settings.py`:

```python
# --- v159: the real-money unlock needs a valid sign-off -----------------------

def _put(client, settings):
    return client.put("/api/v1/system/settings", json={"settings": settings})


@pytest.mark.parametrize("signoff", [None, "", "2026-13-01", "2999-01-01", "soon"])
def test_turning_on_real_money_without_a_valid_signoff_is_rejected(logged_in, env_file, signoff):
    env_file({"ETORO_ALLOW_REAL": "false"})
    body = {"ETORO_ALLOW_REAL": True}
    if signoff is not None:
        body["ETORO_REAL_SIGNOFF"] = signoff
    assert_error(_put(logged_in, body), "real_money_signoff", 400)
    assert env_file.read()["ETORO_ALLOW_REAL"] == "false", "a rejected save writes nothing"


def test_the_flag_with_a_valid_signoff_saves(logged_in, env_file):
    env_file({"ETORO_ALLOW_REAL": "false"})
    resp = _put(logged_in, {"ETORO_ALLOW_REAL": True, "ETORO_REAL_SIGNOFF": "2026-01-01"})
    assert resp.status_code == 200
    saved = env_file.read()
    assert saved["ETORO_ALLOW_REAL"] == "true" and saved["ETORO_REAL_SIGNOFF"] == "2026-01-01"


def test_clearing_the_signoff_while_the_flag_is_on_is_rejected(logged_in, env_file):
    env_file({"ETORO_ALLOW_REAL": "true", "ETORO_REAL_SIGNOFF": "2026-01-01"})
    assert_error(_put(logged_in, {"ETORO_REAL_SIGNOFF": ""}), "real_money_signoff", 400)


def test_turning_real_money_off_always_saves(logged_in, env_file):
    env_file({"ETORO_ALLOW_REAL": "true", "ETORO_REAL_SIGNOFF": "2026-01-01"})
    assert _put(logged_in, {"ETORO_ALLOW_REAL": False}).status_code == 200
    assert env_file.read()["ETORO_ALLOW_REAL"] == "false"


def test_a_save_that_touches_neither_key_is_not_blocked(logged_in, env_file):
    env_file({"ETORO_ALLOW_REAL": "true", "LOG_LEVEL": "INFO"})   # hand-edited, no sign-off
    assert _put(logged_in, {"LOG_LEVEL": "DEBUG"}).status_code == 200


def test_the_preview_applies_the_same_rule(logged_in, env_file):
    env_file({"ETORO_ALLOW_REAL": "false"})
    resp = logged_in.post("/api/v1/system/settings/preview",
                          json={"settings": {"ETORO_ALLOW_REAL": True}})
    assert_error(resp, "real_money_signoff", 400)


def test_an_import_cannot_unlock_real_money(logged_in, env_file):
    env_file({"ETORO_ALLOW_REAL": "false"})
    resp = logged_in.post("/api/v1/system/settings/import",
                          json={"text": "ETORO_ALLOW_REAL=true\n"})
    assert_error(resp, "real_money_signoff", 400)
    assert env_file.read()["ETORO_ALLOW_REAL"] == "false"
```

In `tests/scripts/test_env_set.py` add `import pytest` after `import sys`, then append:

```python
@pytest.mark.parametrize("key, value", [("ETORO_ALLOW_REAL", "true"),
                                        ("ETORO_ALLOW_REAL", "false"),
                                        ("ETORO_REAL_SIGNOFF", "2026-01-01")])
def test_main_refuses_the_real_money_keys(tmp_path, capsys, key, value):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    assert env_set.main(["--env", str(env), key, value]) == 2
    assert env.read_text(encoding="utf-8") == "A=1\n"
    assert "refused" in capsys.readouterr().err
    assert env_set.REFUSED_KEYS == frozenset({"ETORO_ALLOW_REAL", "ETORO_REAL_SIGNOFF"})


def test_get_still_reads_a_refused_key(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("ETORO_ALLOW_REAL=false\n", encoding="utf-8")
    assert env_set.main(["--env", str(env), "--get", "ETORO_ALLOW_REAL"]) == 0
    assert capsys.readouterr().out.strip() == "false"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/admin/test_api_v1_system_settings.py`
Expected: FAIL — the rejection, preview and import cases get 200 instead of 400.

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_env_set.py`
Expected: FAIL — `main` returns 0 and `AttributeError: ... 'REFUSED_KEYS'`.

- [ ] **Step 3: Implement**

`swingbot/admin/api_v1/system.py` — add `import io` to the stdlib imports and `from swingbot.core.broker import guard` after `from swingbot import config`. Insert after `_validate`:

```python
def _real_money_problem(values: Mapping, existing: Mapping) -> tuple[str, str] | None:
    """("real_money_signoff", message) when this body would leave
    ETORO_ALLOW_REAL on without a valid ETORO_REAL_SIGNOFF (v159).

    A body that touches neither key passes, so a hand-edited .env never blocks
    an unrelated save. Kept out of _validate, which is already complexity 21.
    """
    if not any(key in values for key in guard.UNLOCK_KEYS):
        return None
    allow = values.get("ETORO_ALLOW_REAL", existing.get("ETORO_ALLOW_REAL", "false"))
    signoff = values.get("ETORO_REAL_SIGNOFF", existing.get("ETORO_REAL_SIGNOFF", ""))
    if not _truthy(allow) or guard.signoff_valid(signoff):
        return None
    return ("real_money_signoff",
            "Real money is stage 3 (docs/claude/etoro-roadmap.md). Turning on "
            "ETORO_ALLOW_REAL needs ETORO_REAL_SIGNOFF set to an ISO date "
            "(YYYY-MM-DD) no later than today, Europe/Berlin.")
```

In `preview_settings`, add `from swingbot.admin.helpers import _read_env_values` as its first line and change the validation line to:

```python
    problem = _validate(values) or _real_money_problem(values, _read_env_values())
```

In `save_settings` (it already imports `_read_env_values`), the same one-line change:

```python
    problem = _validate(values) or _real_money_problem(values, _read_env_values())
```

In `import_settings`, change its import line and insert the check between the empty-text rejection and `import_env_text(text)`:

```python
    from dotenv import dotenv_values

    from swingbot.admin.helpers import _read_env_values, import_env_text
```

```python
    parsed = {k: v for k, v in dotenv_values(stream=io.StringIO(text)).items()
              if v is not None}
    problem = _real_money_problem(parsed, _read_env_values())
    if problem:
        return error(problem[0], problem[1], 400)
```

`scripts/ops/env_set.py` — after the imports add:

```python
# The stage-3 real-money lock (v159, docs/claude/etoro-roadmap.md). Only the
# admin Settings page, with its typed-date confirm, or a hand edit on the VM
# may set these.
REFUSED_KEYS = frozenset({"ETORO_ALLOW_REAL", "ETORO_REAL_SIGNOFF"})
```

In `main`, directly after the `parser.error("pass KEY VALUE, or --get KEY")` check and before `_snapshot_or_warn(args.env, "before")`:

```python
    if args.key in REFUSED_KEYS:
        print(f"env_set: refused -- {args.key} is the stage-3 real-money lock; set it "
              "on the admin Settings page or by hand on the VM "
              "(docs/claude/etoro-roadmap.md)", file=sys.stderr)
        return 2
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/admin/test_api_v1_system_settings.py`
Expected: PASS, `0 failed`, `0 xfailed` (the pre-existing import round-trip tests still pass: their text carries no unlock).

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_env_set.py`
Expected: PASS.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS (the AST scan: `system.py` and `env_set.py` name the lock keys, not the eToro credentials or host).

Run: `python -m radon cc -s -n C "$WT/swingbot/admin/api_v1/system.py" "$WT/scripts/ops/env_set.py"`
Expected: exactly one line, `_validate` at D (21), unchanged; nothing else.

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add swingbot/admin/api_v1/system.py tests/admin/test_api_v1_system_settings.py scripts/ops/env_set.py tests/scripts/test_env_set.py
git -C "$WT" commit -m "feat(v159): ER9 -- server refuses a real-money unlock without a sign-off

Save, preview and paste-import return 400 real_money_signoff when the body
would leave ETORO_ALLOW_REAL on without a valid ETORO_REAL_SIGNOFF; a body
touching neither key is never blocked. _validate (cc 21) is untouched.
scripts/ops/env_set.py refuses both keys (exit 2); --get still reads them.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
