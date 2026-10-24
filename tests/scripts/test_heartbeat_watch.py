"""v148 O3: the VM's out-of-process heartbeat watch.

The script runs only on the VM, as root, from cron. Here it runs under bash
with `docker` and `curl` replaced by exported bash functions (a stub file is
not executable on Windows -- the test_pitr_crons.py pattern), so the whole
once-per-incident state machine is exercised without Postgres, Docker or a
webhook. Skipped where no bash can see both the repo and the tmp dir.
"""
import os
import pathlib
import re
import shlex
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
SCRIPT = OPS / "heartbeat_watch.sh"
INSTALLER = OPS / "install_heartbeat_watch_cron.sh"
NAMES = ["heartbeat_watch.sh", "install_heartbeat_watch_cron.sh"]
URL = "https://discord.example/api/webhooks/1/secret"

# `docker` answers the heartbeat query with $STUB/age (or fails when it is
# absent) and the v184 monitor query (its SQL names `monitor`) with
# $STUB/monitor, or `absent` -- a pre-v184 row, which the watch logs and keeps
# silent; `curl` records its arguments and returns $STUB/curl_rc.
_STUBS = (
    'docker() { case "$*" in '
    '*monitor*) if [ -f "$STUB/monitor" ]; then cat "$STUB/monitor"; else echo absent; fi ;; '
    '*) [ -f "$STUB/age" ] || return 1; cat "$STUB/age" ;; esac; }; '
    'curl() { printf "%s\\n" "$*" >> "$STUB/curl.log"; '
    'return "$(cat "$STUB/curl_rc" 2>/dev/null || echo 0)"; }; '
    "export -f docker curl; "
)


def _text(name):
    return (OPS / name).read_text(encoding="utf-8")


# --- shape (always runs) -----------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_strict_mode_and_lf(name):
    assert "set -euo pipefail" in _text(name)
    assert b"\r" not in (OPS / name).read_bytes()
    assert "sed -i" not in _text(name)


def test_env_is_grepped_never_sourced():
    text = _text("heartbeat_watch.sh")
    assert "cut -d= -f2-" in text
    assert "source " not in text
    assert '. "$ROOT/.env"' not in text


def test_the_query_reads_the_bots_own_timestamp_not_ts():
    text = _text("heartbeat_watch.sh")
    assert "doc->>'timestamp'" in text
    assert "docker compose exec -T db psql -U swingbot -d swingbot" in text


def test_installer_schedules_every_five_minutes_and_replaces_its_own_line():
    text = _text("install_heartbeat_watch_cron.sh")
    assert "grep -vF" in text and "MARKER=" in text
    assert "*/5 * * * *" in text and "heartbeat_watch.sh" in text


def test_the_heartbeat_block_is_one_function_that_never_exits():
    """v184: the heartbeat block returns, so a later check always runs after it."""
    text = _text("heartbeat_watch.sh")
    assert "\nheartbeat_check() {" in text
    assert 'HB_VERDICT="$verdict"' in text
    body = text.split("\nheartbeat_check() {", 1)[1].split("\n}\n", 1)[0]
    assert "exit" not in body
    assert body.count("return 0") == 3
    assert text.rstrip().endswith("exit 0")


# --- behaviour (needs bash) --------------------------------------------------

def _working_bash(*paths):
    """A bash that resolves these host paths, or None. On Windows `bash` can be
    WSL's, which cannot see `C:/...`; Git for Windows' bash is tried next."""
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
def bash(tmp_path):
    found = _working_bash(SCRIPT, tmp_path)
    if found is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    return found


def _env(root, **values):
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in values.items()),
                               encoding="utf-8", newline="\n")


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "root"
    (r / "logs").mkdir(parents=True)
    (tmp_path / "stub").mkdir()
    _env(r, SCAN_INTERVAL_MINUTES="5", OPS_ALERT_WEBHOOK_URL=URL)
    return r


def _run(bash, root, *args, age=None, curl_rc=0):
    stub = root.parent / "stub"
    if age is None:
        (stub / "age").unlink(missing_ok=True)
    else:
        (stub / "age").write_text(str(age), encoding="utf-8")
    (stub / "curl_rc").write_text(str(curl_rc), encoding="utf-8")
    env = {**os.environ, "HEARTBEAT_WATCH_ROOT": root.as_posix(), "STUB": stub.as_posix()}
    cmd = _STUBS + "bash " + " ".join(shlex.quote(a) for a in (SCRIPT.as_posix(), *args))
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True, timeout=60)


def _posts(root):
    log = root.parent / "stub" / "curl.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _state(root):
    path = root / "logs" / "heartbeat_watch.state"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _log(root):
    return (root / "logs" / "heartbeat_watch.log").read_text(encoding="utf-8").splitlines()


def test_dry_run_prints_a_healthy_verdict_and_touches_nothing(bash, root):
    r = _run(bash, root, "--dry-run", "--age", "30")
    assert r.returncode == 0, r.stderr
    assert "verdict=ok age_s=30 threshold_s=900" in r.stdout
    assert "action=none" in r.stdout and "dry_run=1" in r.stdout
    assert _state(root) is None
    assert _posts(root) == []
    assert len(_log(root)) == 1


def test_dry_run_flags_stale_past_fifteen_minutes_without_posting(bash, root):
    r = _run(bash, root, "--dry-run", "--age", "901")
    assert "verdict=stale" in r.stdout and "action=alert" in r.stdout
    assert _posts(root) == []
    assert _state(root) is None


def test_threshold_is_three_scan_intervals_when_that_is_longer(bash, root):
    _env(root, SCAN_INTERVAL_MINUTES="20", OPS_ALERT_WEBHOOK_URL=URL)
    r = _run(bash, root, "--dry-run", "--age", "2000")
    assert "verdict=ok" in r.stdout and "threshold_s=3600" in r.stdout


def test_a_garbled_interval_falls_back_to_five_minutes(bash, root):
    _env(root, SCAN_INTERVAL_MINUTES="soon")
    assert "threshold_s=900" in _run(bash, root, "--dry-run", "--age", "1").stdout


def test_an_empty_age_is_an_unreadable_heartbeat(bash, root):
    r = _run(bash, root, "--dry-run", "--age", "")
    assert "verdict=unreadable" in r.stdout and "action=alert" in r.stdout


def test_the_log_keeps_its_last_2000_lines(bash, root):
    log = root / "logs" / "heartbeat_watch.log"
    log.write_text("".join(f"old {i}\n" for i in range(2100)), encoding="utf-8", newline="\n")
    _run(bash, root, "--dry-run", "--age", "30")
    lines = _log(root)
    assert len(lines) == 2000
    assert lines[0] == "old 101"
    assert "verdict=ok" in lines[-1]


def test_dry_run_requires_an_age(bash, root):
    assert _run(bash, root, "--dry-run").returncode == 2


def test_first_healthy_run_records_ok_and_posts_nothing(bash, root):
    r = _run(bash, root, age=30)
    assert r.returncode == 0, r.stderr
    assert _state(root) == "ok"
    assert _posts(root) == []


def test_one_post_per_incident_then_one_recovery(bash, root):
    assert "action=alert" in _run(bash, root, age=5000).stdout
    assert len(_posts(root)) == 1 and "STALE" in _posts(root)[0]
    assert _state(root) == "stale"

    assert "action=none" in _run(bash, root, age=5300).stdout
    assert len(_posts(root)) == 1

    assert "action=recover" in _run(bash, root, age=12).stdout
    assert len(_posts(root)) == 2 and "RECOVERED" in _posts(root)[1]
    assert _state(root) == "ok"

    _run(bash, root, age=40)
    assert len(_posts(root)) == 2


def test_the_post_is_a_json_body_to_the_configured_url(bash, root):
    _run(bash, root, age=5000)
    post = _posts(root)[0]
    assert URL in post
    assert '{"content":"' in post
    assert "Content-Type: application/json" in post


def test_a_failed_query_is_its_own_incident(bash, root):
    r = _run(bash, root, age=None)            # the docker stub fails
    assert "verdict=unreadable" in r.stdout and "delivered=yes" in r.stdout
    assert "UNREADABLE" in _posts(root)[0]
    assert _state(root) == "unreadable"


def test_stale_after_unreadable_is_a_new_incident(bash, root):
    _run(bash, root, age=None)
    _run(bash, root, age=5000)
    assert len(_posts(root)) == 2 and "STALE" in _posts(root)[1]


def test_no_webhook_logs_and_exits_zero_without_arming_the_state(bash, root):
    _env(root, SCAN_INTERVAL_MINUTES="5")
    r = _run(bash, root, age=5000)
    assert r.returncode == 0
    assert "delivered=no-webhook" in r.stdout
    assert _posts(root) == []
    assert _state(root) is None


def test_a_failed_post_is_retried_on_the_next_run(bash, root):
    r = _run(bash, root, age=5000, curl_rc=22)
    assert r.returncode == 0 and "delivered=failed" in r.stdout
    assert _state(root) is None
    _run(bash, root, age=5000)
    assert len(_posts(root)) == 2
    assert _state(root) == "stale"


def test_test_flag_forces_one_post(bash, root):
    r = _run(bash, root, "--test")
    assert r.returncode == 0, r.stderr
    assert len(_posts(root)) == 1 and "TEST" in _posts(root)[0]
    assert _state(root) is None


def test_test_flag_without_a_webhook_fails_loudly(bash, root):
    _env(root, SCAN_INTERVAL_MINUTES="5")
    r = _run(bash, root, "--test")
    assert r.returncode == 1
    assert _posts(root) == []


def test_installer_is_idempotent_and_keeps_other_lines(bash, tmp_path):
    store = tmp_path / "crontab.txt"
    store.write_text("0 1 * * * echo keep-me\n", encoding="utf-8", newline="\n")
    env = {**os.environ, "BASE": tmp_path.as_posix()}
    # crontab buffers stdin first, like the real one; an exported bash function
    # because a stub file is not executable on Windows.
    fn = (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}"; '
          f'else d=$(cat); printf "%s\n" "$d" > "{store.as_posix()}"; fi; }}; export -f crontab; '
          f'bash "{INSTALLER.as_posix()}"')
    for _ in range(2):
        subprocess.run([bash, "-c", fn], env=env, check=True, capture_output=True, timeout=60)
    lines = store.read_text(encoding="utf-8").splitlines()
    assert "0 1 * * * echo keep-me" in lines
    watch = [line for line in lines if "heartbeat_watch.sh" in line and not line.startswith("#")]
    assert len(watch) == 1
    assert watch[0].startswith("*/5 * * * * ")
    assert sum(line.startswith("# v148 heartbeat watch") for line in lines) == 1


# --- v184: the heartbeat line is pinned byte for byte --------------------------
# These pass before and after V184-8 (and must keep passing after V184-9, which
# adds a second, monitor line *after* this one). They are the "byte-identical"
# guard the spec asks for.

_ISO = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"


@pytest.mark.parametrize("args, kw, tail", [
    (("--dry-run", "--age", "30"), {},
     "verdict=ok age_s=30 threshold_s=900 previous=none action=none dry_run=1"),
    (("--dry-run", "--age", ""), {},
     "verdict=unreadable age_s=none threshold_s=900 previous=none action=alert dry_run=1"),
    ((), {"age": 30},
     "verdict=ok age_s=30 threshold_s=900 previous=none action=none"),
    ((), {"age": 5000},
     "verdict=stale age_s=5000 threshold_s=900 previous=none action=alert delivered=yes"),
    ((), {"age": 5000, "curl_rc": 22},
     "verdict=stale age_s=5000 threshold_s=900 previous=none action=alert delivered=failed"),
    ((), {"age": None},
     "verdict=unreadable age_s=none threshold_s=900 previous=none action=alert delivered=yes"),
])
def test_the_heartbeat_line_is_pinned_byte_for_byte(bash, root, args, kw, tail):
    r = _run(bash, root, *args, **kw)
    assert r.returncode == 0, r.stderr
    first = r.stdout.splitlines()[0]
    assert re.fullmatch(f"{_ISO} {re.escape(tail)}", first), first
    assert re.fullmatch(f"{_ISO} {re.escape(tail)}", _log(root)[0]), _log(root)[0]


def test_the_no_webhook_line_is_pinned_byte_for_byte(bash, root):
    _env(root, SCAN_INTERVAL_MINUTES="5")
    r = _run(bash, root, age=5000)
    tail = "verdict=stale age_s=5000 threshold_s=900 previous=none action=alert delivered=no-webhook"
    assert re.fullmatch(f"{_ISO} {re.escape(tail)}", r.stdout.splitlines()[0]), r.stdout


def test_a_recovery_line_names_the_previous_verdict(bash, root):
    _run(bash, root, age=5000)
    r = _run(bash, root, age=12)
    tail = "verdict=ok age_s=12 threshold_s=900 previous=stale action=recover delivered=yes"
    assert re.fullmatch(f"{_ISO} {re.escape(tail)}", r.stdout.splitlines()[0]), r.stdout
