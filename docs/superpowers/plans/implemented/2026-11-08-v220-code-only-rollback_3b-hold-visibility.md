# v220 — Code-only rollback, Part 3b: hold in `deploy.sh` and the `HOLD` line (V220-12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the secondary deploy hold in `deploy/deploy.sh` phase 1 and the SessionStart `HOLD` line (`scripts/dev/hold_status.py` behind `.claude/hooks/session-cursor.ps1`). It moved here from [Part 3](2026-11-08-v220-code-only-rollback_3-vm-script-and-hold.md) to keep that file under 1500 lines; it depends only on the hold-file contract and can start at any time (index Parallelisation). The binding code facts in Part 3's header apply here too, in particular the bash-stub test pattern (`_working_bash`) and the strings `test_deploy_records.py` and `test_deploy_refresher_guard_shape.py` pin in `deploy.sh`.


# Phase 3b — Hold visibility

### Task V220-12: Hold in `deploy.sh` phase 1 and the SessionStart `HOLD` line

**Model:** sonnet — two small guards and a cached status helper

**Files:**
- Modify: `deploy/deploy.sh` (guard above the phase-1 `git fetch`/`git reset`)
- Test: `tests/scripts/test_deploy_hold_check.py` (new, suite `tooling`)
- Create: `scripts/dev/hold_status.py`
- Test: `tests/dev/test_hold_status.py` (new, suite `dev-setup`)
- Modify: `.claude/hooks/session-cursor.ps1` (one guarded block)

**Interfaces:**
- Consumes: the hold-file contract (Global Constraints); `scripts/ops/ssh-hetzner.sh "<cmd>"` (untracked, on the dev machine only; may be absent).
- Produces (consumed by V220-15): `hold_status.py` with `CACHE = <repo>/logs/deploy_hold_cache.json` (`{"checked_at", "hold": dict | None, "error": str | None}`), `REMOTE_CMD`, `REFRESH_AFTER = timedelta(minutes=30)`, `hold_line(cache: dict | None) -> str | None`, `is_stale(cache: dict | None, now: datetime) -> bool`, `refresh(cache_path: Path, *, run=subprocess.run, ssh: Path = SSH) -> dict` (`ssh` is additive to the ledger signature, for tests), `main(argv=None, *, run=subprocess.run) -> int` with CLI `--line | --refresh [--if-stale] [--cache PATH]`; the hook's line `HOLD     : deploy held by rollback to <sha12> (<reason>, since <at>) -- release with /rollback --release (checked <checked_at>)`.

Decisions this task fixes:

- **The guard sits above the phase split** (`if [ "${1:-}" != "--updated" ]`), so it runs before `git fetch`/`git reset` in phase 1 and again in phase 2; `rollback_code.sh --release` deletes the hold before it calls `deploy.sh`, so the release passes. It exits 0 (spec: "exits 0 when present"). Its text avoids every substring `test_deploy_records.py` and `test_deploy_refresher_guard_shape.py` pin by position.
- **The hook never waits on the network:** `--line` reads only the cache; the hook then starts `--refresh --if-stale` detached, which asks the VM at most every 30 minutes. A refresh error is cached, never printed by the hook; no hold or no cache prints nothing.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deploy_hold_check.py`:

```python
"""deploy.sh refuses, with exit 0, while a code-only rollback holds deploys
(v220). Runs a temp copy of deploy.sh under bash with `git` stubbed: a held
run must stop before any git call."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "deploy.sh"
HOLD = {"sha": "c" * 40, "reason": "v230 broke exits", "at": "2026-11-20T10:00:00Z"}


def test_the_guard_runs_before_the_phase_one_fetch_and_reset():
    src = DEPLOY.read_text(encoding="utf-8")
    guard = src.index("if [ -f backups/deploy_hold.json ]; then")
    assert guard < src.index('if [ "${1:-}" != "--updated" ]; then') < src.index("git fetch origin main")
    block = src[guard:src.index('if [ "${1:-}" != "--updated" ]; then')]
    assert "exit 0" in block and "/rollback --release" in block
    for pinned in ("docker compose up", "env_set.py", ">> backups/deploys.jsonl", "sed -i", "rolling back"):
        assert pinned not in block


def _working_bash(*paths):
    git = shutil.which("git")
    candidates = [shutil.which("bash")]
    if git:
        candidates.append(str(pathlib.Path(git).resolve().parents[1] / "usr" / "bin" / "bash.exe"))
    test = " && ".join(f'test -e "{p.as_posix()}"' for p in paths)
    for bash in filter(None, candidates):
        try:
            if subprocess.run([bash, "-c", test], capture_output=True, timeout=20).returncode == 0:
                return bash
        except OSError:
            continue
    return None


@pytest.fixture
def app(tmp_path):
    bash = _working_bash(DEPLOY, tmp_path)
    if bash is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    (tmp_path / "deploy").mkdir()
    shutil.copy(DEPLOY, tmp_path / "deploy" / "deploy.sh")
    (tmp_path / "backups").mkdir()
    (tmp_path / ".env").write_text("SWING_BOT_IMAGE=x\n", encoding="utf-8", newline="\n")
    return bash, tmp_path


def _run(bash, root):
    stubs = ('git() { echo "git $*" >> "$ROOT/git.log"; return 1; }; '
             'python3() { "$PY" "$@"; }; export -f git python3; ')
    env = {**os.environ, "ROOT": root.as_posix(), "PY": pathlib.Path(sys.executable).as_posix()}
    cmd = stubs + f'bash "{(root / "deploy" / "deploy.sh").as_posix()}"'
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True, timeout=60)


def test_a_held_deploy_exits_0_before_any_git_call(app):
    bash, root = app
    (root / "backups" / "deploy_hold.json").write_text(json.dumps(HOLD), encoding="utf-8")
    proc = _run(bash, root)
    assert proc.returncode == 0
    assert f"deploy held by rollback to {'c' * 40} (v230 broke exits, since 2026-11-20T10:00:00Z)" in proc.stdout
    assert not (root / "git.log").exists()


def test_an_unreadable_hold_still_holds(app):
    bash, root = app
    (root / "backups" / "deploy_hold.json").write_text("{broken", encoding="utf-8")
    proc = _run(bash, root)
    assert proc.returncode == 0 and "unreadable" in proc.stdout
    assert not (root / "git.log").exists()


def test_without_a_hold_phase_one_fetches_main(app):
    bash, root = app
    proc = _run(bash, root)
    assert proc.returncode != 0   # the stub git fails, which stops set -e
    assert (root / "git.log").read_text(encoding="utf-8").splitlines()[0] == "git fetch origin main"
```

Create `tests/dev/test_hold_status.py`:

```python
"""The SessionStart HOLD line (v220): cache-only reads, a background refresh
through ssh-hetzner.sh, and a hook that can never fail on it."""
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import hold_status as hs  # noqa: E402

HOLD = {"sha": "d" * 40, "reason": "v230 broke exits", "at": "2026-11-20T10:00:00Z"}
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _proc(stdout="", rc=0):
    return subprocess.CompletedProcess(["bash"], rc, stdout=stdout, stderr="")


def _ssh(tmp_path):
    p = tmp_path / "ssh-hetzner.sh"
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    return p


def test_hold_line_only_for_a_cached_hold():
    assert hs.hold_line(None) is None
    assert hs.hold_line({"checked_at": "x", "hold": None, "error": None}) is None
    assert hs.hold_line({"checked_at": "x", "hold": None, "error": "ssh exit 255"}) is None
    line = hs.hold_line({"checked_at": "2026-11-20T11:00:00Z", "hold": HOLD, "error": None})
    assert line == ("HOLD     : deploy held by rollback to dddddddddddd (v230 broke exits, since "
                    "2026-11-20T10:00:00Z) -- release with /rollback --release (checked 2026-11-20T11:00:00Z)")


def test_is_stale_after_thirty_minutes_or_without_a_usable_stamp():
    fresh = {"checked_at": (NOW - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    old = {"checked_at": (NOW - timedelta(minutes=31)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert hs.is_stale(fresh, NOW) is False
    assert hs.is_stale(old, NOW) is True
    assert hs.is_stale(None, NOW) is True and hs.is_stale({"checked_at": "junk"}, NOW) is True


def test_refresh_reads_no_hold_a_hold_and_caches_it(tmp_path):
    cache = tmp_path / "logs" / "deploy_hold_cache.json"
    seen = []
    out = hs.refresh(cache, ssh=_ssh(tmp_path), run=lambda cmd, **kw: seen.append(cmd) or _proc("NO_HOLD\n"))
    assert out["hold"] is None and out["error"] is None
    assert seen[0][-1] == hs.REMOTE_CMD and "cat /opt/swing-bot/backups/deploy_hold.json" in hs.REMOTE_CMD
    out = hs.refresh(cache, ssh=_ssh(tmp_path), run=lambda cmd, **kw: _proc(json.dumps(HOLD)))
    assert out["hold"] == HOLD
    assert json.loads(cache.read_text(encoding="utf-8"))["hold"] == HOLD


def test_refresh_caches_every_failure_as_an_error(tmp_path):
    cache = tmp_path / "c.json"
    assert "missing" in hs.refresh(cache, ssh=tmp_path / "absent.sh", run=None)["error"]

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 30)
    for run in (lambda c, **k: _proc("", 255), lambda c, **k: _proc("garbage"), boom):
        out = hs.refresh(cache, ssh=_ssh(tmp_path), run=run)
        assert out["hold"] is None and out["error"]


def test_cli_line_reads_the_cache_and_never_fails(tmp_path, capsys):
    cache = tmp_path / "c.json"
    assert hs.main(["--line", "--cache", str(cache)]) == 0 and capsys.readouterr().out == ""
    cache.write_text("{broken", encoding="utf-8")
    assert hs.main(["--line", "--cache", str(cache)]) == 0 and capsys.readouterr().out == ""
    cache.write_text(json.dumps({"checked_at": "t", "hold": HOLD, "error": None}), encoding="utf-8")
    assert hs.main(["--line", "--cache", str(cache)]) == 0
    assert capsys.readouterr().out.startswith("HOLD     : deploy held by rollback to dddddddddddd")


def test_cli_refresh_if_stale_skips_a_fresh_cache(tmp_path):
    cache = tmp_path / "c.json"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache.write_text(json.dumps({"checked_at": stamp, "hold": None, "error": None}), encoding="utf-8")
    calls = []
    assert hs.main(["--refresh", "--if-stale", "--cache", str(cache)], run=lambda *a, **k: calls.append(a)) == 0
    assert calls == []


def test_the_session_hook_reads_the_cache_and_refreshes_detached():
    src = (ROOT / ".claude" / "hooks" / "session-cursor.ps1").read_text(encoding="utf-8")
    block = src[src.index("# --- deploy hold (v220)"):]
    block = block[:block.index("catch {")]
    assert "scripts/dev/hold_status.py" in block and "--line" in block
    assert "Start-Process" in block and "'--refresh', '--if-stale'" in block
    assert "try {" in block and "Test-Path $hs" in block
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deploy_hold_check.py` and `python scripts/dev/testrun.py file tests/dev/test_hold_status.py`
Expected: FAIL (`ValueError: substring not found` for the guard; `ModuleNotFoundError: hold_status`).

- [ ] **Step 3: Add the `deploy.sh` guard**

In `deploy/deploy.sh`, insert directly above the line `if [ "${1:-}" != "--updated" ]; then` (after the comment block that explains the two phases):

```bash
# v220: while a code-only rollback (scripts/ops/rollback_code.sh) holds
# deploys, nothing deploys -- not even by hand. Checked before the fetch and
# reset below, which would move the checkout off the rollback target. CI
# reads the same file in its own `hold` job; this covers a manual run.
if [ -f backups/deploy_hold.json ]; then
  python3 - backups/deploy_hold.json 2>/dev/null <<'PY' || echo "deploy held by rollback (backups/deploy_hold.json unreadable)"
import json, sys
h = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"deploy held by rollback to {h['sha']} ({h['reason']}, since {h['at']})")
PY
  echo "Nothing deployed. Release the hold with /rollback --release (scripts/ops/rollback_code.sh --release)."
  exit 0
fi

```

- [ ] **Step 4: Write `scripts/dev/hold_status.py`**

```python
"""SessionStart HOLD line (v220): is a code-only rollback holding deploys?

`--line` prints the line from the cache only, never touching the network (the
hook must not block a session start). `--refresh [--if-stale]` asks the VM
through scripts/ops/ssh-hetzner.sh (a read-only `cat`) and rewrites the cache;
the hook starts it detached. Errors are cached, never raised.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "logs" / "deploy_hold_cache.json"
SSH = REPO / "scripts" / "ops" / "ssh-hetzner.sh"
REMOTE_CMD = "cat /opt/swing-bot/backups/deploy_hold.json 2>/dev/null || echo NO_HOLD"
REFRESH_AFTER = timedelta(minutes=30)
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def hold_line(cache: dict | None) -> str | None:
    hold = (cache or {}).get("hold")
    if not isinstance(hold, dict):
        return None
    return (f"HOLD     : deploy held by rollback to {str(hold.get('sha', '?'))[:12]} "
            f"({hold.get('reason', '?')}, since {hold.get('at', '?')}) -- release with /rollback --release "
            f"(checked {cache.get('checked_at', '?')})")


def is_stale(cache: dict | None, now: datetime) -> bool:
    try:
        checked = datetime.strptime((cache or {})["checked_at"], STAMP).replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return True
    return now - checked > REFRESH_AFTER


def _read_vm(run, ssh: Path) -> tuple[dict | None, str | None]:
    if not ssh.exists():
        return None, f"{ssh.name} missing"
    try:
        proc = run(["bash", str(ssh), REMOTE_CMD], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"ssh failed: {type(exc).__name__}"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return None, f"ssh exit {proc.returncode}"
    if out.endswith("NO_HOLD"):
        return None, None
    try:
        hold = json.loads(out)
    except ValueError:
        return None, "unreadable hold file"
    return (hold, None) if isinstance(hold, dict) else (None, "unreadable hold file")


def refresh(cache_path: Path, *, run=subprocess.run, ssh: Path = SSH) -> dict:
    hold, error = _read_vm(run, ssh)
    cache = {"checked_at": datetime.now(timezone.utc).strftime(STAMP), "hold": hold, "error": error}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    tmp.replace(cache_path)
    return cache


def _load(cache_path: Path) -> dict | None:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None, *, run=subprocess.run) -> int:
    parser = argparse.ArgumentParser(description="v220 deploy-hold status for the SessionStart hook")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--line", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    parser.add_argument("--if-stale", action="store_true")
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args(argv)
    cache = _load(args.cache)
    if args.line:
        line = hold_line(cache)
        if line:
            print(line)
        return 0
    if args.if_stale and not is_stale(cache, datetime.now(timezone.utc)):
        return 0
    refresh(args.cache, run=run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Add the hook block**

In `.claude/hooks/session-cursor.ps1`, insert directly after the BACKUP block's closing `catch { Emit "BACKUP   : WARNING no good pull yet (unreadable LAST_GOOD_PULL) -- run /backup-pull" }` (before the outer `}` that closes the main `try`):

```powershell

    # --- deploy hold (v220): cached, never waits on the network ---
    # Own try/catch: --line reads logs/deploy_hold_cache.json only; the refresh
    # (ssh-hetzner.sh, read-only) runs detached, at most every 30 minutes.
    try {
        $hs = 'scripts/dev/hold_status.py'
        if (Test-Path $hs) {
            $hline = @(& python $hs --line 2>$null) | Select-Object -First 1
            if ($hline) { Emit $hline }
            Start-Process -FilePath python -ArgumentList @($hs, '--refresh', '--if-stale') `
                -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
        }
    }
    catch { }
```

Notes for the implementer:
- `logs/` is gitignored, so the cache is never committed; `hold_status.py` creates the folder.
- `tests/hooks/test_session_backup_line.py` and `test_session_plan_wip.py` run the hook under `pwsh` on a copy without `scripts/dev/hold_status.py`; the `Test-Path` guard keeps their output unchanged. Run them in Step 6.
- `ssh-hetzner.sh` is untracked: on CI and in worktrees it is absent and the cache says so, silently.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deploy_hold_check.py`, `python scripts/dev/testrun.py file tests/dev/test_hold_status.py`, `python scripts/dev/testrun.py file tests/scripts/test_deploy_records.py`, `python scripts/dev/testrun.py file tests/scripts/test_deploy_refresher_guard_shape.py`, `python scripts/dev/testrun.py file tests/hooks/test_session_backup_line.py`
Expected: `0 failed` each; `python scripts/dev/complexity_gate.py` exits 0.

- [ ] **Step 7: Commit**

```bash
git add deploy/deploy.sh tests/scripts/test_deploy_hold_check.py scripts/dev/hold_status.py tests/dev/test_hold_status.py .claude/hooks/session-cursor.ps1
git commit -m "feat(v220): deploy hold in deploy.sh phase 1 and a cached SessionStart HOLD line"
```

