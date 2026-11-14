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
