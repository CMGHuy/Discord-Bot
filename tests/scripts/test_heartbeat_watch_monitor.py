"""v184: the stop-monitor check in heartbeat_watch.sh (spec section 2).

Same harness as test_heartbeat_watch.py: bash with `docker` and `curl` as
exported functions (a stub file is not executable on Windows). Here `docker`
answers the monitor query from $STUB/monitor and the heartbeat query from
$STUB/age, each failing when its file is absent, so the two checks are driven
independently. Skipped where no bash can see both the repo and the tmp dir.
"""
import os
import re
import shlex
import subprocess

import pytest

from tests.scripts.test_heartbeat_watch import SCRIPT, URL, _env, _working_bash

_STUBS = (
    'docker() { case "$*" in '
    '*monitor*) [ -f "$STUB/monitor" ] || return 1; cat "$STUB/monitor" ;; '
    '*) [ -f "$STUB/age" ] || return 1; cat "$STUB/age" ;; esac; }; '
    'curl() { printf "%s\\n" "$*" >> "$STUB/curl.log"; '
    'return "$(cat "$STUB/curl_rc" 2>/dev/null || echo 0)"; }; '
    "export -f docker curl; "
)
_ISO = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
_TEXT = SCRIPT.read_text(encoding="utf-8")


def _const(name):
    return int(re.search(rf"^{name}=(\d+)$", _TEXT, re.M).group(1))


STALE = _const("MONITOR_STALE_S")
UNCHECKED = _const("STOPS_UNCHECKED_S")


# --- shape (always runs) -----------------------------------------------------

def test_thresholds_and_state_file_are_script_constants():
    assert STALE == 300
    assert UNCHECKED % 300 == 0 and 600 <= UNCHECKED <= 1800   # 600 unless V184-1 set it
    assert 'MONITOR_STATE_FILE="$ROOT/logs/monitor_watch.state"' in _TEXT
    assert "env_value MONITOR_STALE_S" not in _TEXT        # constants, never an .env knob
    assert "env_value STOPS_UNCHECKED_S" not in _TEXT


def test_the_heartbeat_query_floor_and_state_are_unchanged():
    assert ('SQL="SELECT floor(extract(epoch FROM now() - (doc->>\'timestamp\')::timestamptz))'
            '::bigint FROM bot_heartbeat WHERE key = \'bot\'"') in _TEXT
    assert "\nMIN_STALE_S=900\n" in _TEXT
    assert 'STATE_FILE="$ROOT/logs/heartbeat_watch.state"' in _TEXT


def test_the_monitor_query_is_one_line_and_reads_the_monitor_key():
    line = next(l for l in _TEXT.splitlines() if l.startswith("MONITOR_SQL="))
    assert "doc ? 'monitor'" in line and "'America/New_York'" in line
    assert line.endswith("FROM bot_heartbeat WHERE key = 'bot'\"")


def test_a_monitor_failure_is_logged_never_fatal():
    assert 'monitor_check || record "$(now_iso) monitor verdict=error action=none"' in _TEXT
    assert _TEXT.index("then heartbeat_check; fi") < _TEXT.index("monitor_check ||")
    assert _TEXT.rstrip().endswith("exit 0")


def test_the_header_names_the_owner_of_the_monitor_state():
    head = _TEXT.split("set -euo pipefail", 1)[0]
    assert "monitor_watch.state" in head and "Owner: the partner (ops)" in head
    assert "--monitor-age" in head


# --- behaviour (needs bash) --------------------------------------------------

@pytest.fixture
def bash(tmp_path):
    found = _working_bash(SCRIPT, tmp_path)
    if found is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    return found


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "root"
    (r / "logs").mkdir(parents=True)
    (tmp_path / "stub").mkdir()
    _env(r, SCAN_INTERVAL_MINUTES="5", OPS_ALERT_WEBHOOK_URL=URL)
    return r


def _row(tick_age=30, priced_age=0, market_open="true", positions=3, unquoted_count=0,
         unquoted="", fetch_failed="false", check_errors=""):
    """One MONITOR_SQL row: tick_age|priced_age|market_open|positions|unquoted_count|unquoted|fetch_failed|check_errors."""
    return "|".join(str(v) for v in (tick_age, priced_age, market_open, positions,
                                     unquoted_count, unquoted, fetch_failed, check_errors))


def _run(bash, root, *args, age=30, monitor=None, curl_rc=0):
    """age / monitor None = that query fails; monitor is a _row() or 'absent'."""
    stub = root.parent / "stub"
    for name, value in (("age", age), ("monitor", monitor)):
        if value is None:
            (stub / name).unlink(missing_ok=True)
        else:
            (stub / name).write_text(str(value), encoding="utf-8", newline="\n")
    (stub / "curl_rc").write_text(str(curl_rc), encoding="utf-8")
    env = {**os.environ, "HEARTBEAT_WATCH_ROOT": root.as_posix(), "STUB": stub.as_posix()}
    cmd = _STUBS + "bash " + " ".join(shlex.quote(a) for a in (SCRIPT.as_posix(), *args))
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True, timeout=60)


def _posts(root):
    log = root.parent / "stub" / "curl.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _state(root, name="monitor_watch"):
    path = root / "logs" / f"{name}.state"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _monitor_line(r):
    lines = [line for line in r.stdout.splitlines() if " monitor verdict=" in line]
    assert len(lines) == 1, r.stdout + r.stderr
    return lines[0]


# dry runs: every verdict without psql, curl or a state write

@pytest.mark.parametrize("flags, verdict", [
    (["--monitor-age", "30"], "ok"),
    (["--monitor-age", str(STALE)], "ok"),
    (["--monitor-age", str(STALE + 1)], "monitor_stale"),
    (["--monitor-age", "absent"], "not_deployed"),
    (["--monitor-age", ""], "unreadable"),
    (["--monitor-age", "30", "--market-open", "true", "--positions", "3",
      "--priced-age", str(UNCHECKED + 1)], "stops_unchecked"),
    (["--monitor-age", "30", "--market-open", "true", "--positions", "3",
      "--priced-age", str(UNCHECKED)], "ok"),
    (["--monitor-age", "30", "--market-open", "true", "--positions", "null",
      "--priced-age", str(UNCHECKED + 1)], "stops_unchecked"),
    (["--monitor-age", "30", "--market-open", "true", "--positions", "0",
      "--priced-age", "99999"], "ok"),
    (["--monitor-age", "30", "--market-open", "false", "--positions", "3",
      "--priced-age", "99999"], "ok"),
    (["--monitor-age", "30", "--market-open", "true", "--positions", "3",
      "--priced-age", ""], "unreadable"),
    # monitor_stale beats stops_unchecked
    (["--monitor-age", str(STALE + 1), "--market-open", "true", "--positions", "3",
      "--priced-age", "99999"], "monitor_stale"),
])
def test_dry_run_monitor_verdicts(bash, root, flags, verdict):
    r = _run(bash, root, "--dry-run", *flags)
    assert r.returncode == 0, r.stderr
    line = _monitor_line(r)
    assert f" monitor verdict={verdict} " in line and line.endswith(" dry_run=1"), line
    assert _posts(root) == []
    assert _state(root) is None


def test_a_monitor_only_dry_run_is_valid_and_skips_the_heartbeat(bash, root):
    r = _run(bash, root, "--dry-run", "--monitor-age", "10")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert len(lines) == 1
    tail = ("monitor verdict=ok tick_age_s=10 priced_age_s=0 market_open=false "
            "positions=0 previous=none action=none dry_run=1")
    assert re.fullmatch(f"{_ISO} {re.escape(tail)}", lines[0]), lines[0]


def test_an_age_only_dry_run_skips_the_monitor(bash, root):
    r = _run(bash, root, "--dry-run", "--age", "30")
    assert len(r.stdout.splitlines()) == 1 and " monitor " not in r.stdout


@pytest.mark.parametrize("args", [
    ["--monitor-age", "30"], ["--priced-age", "1"], ["--market-open", "true"],
    ["--positions", "3"], ["--age", "30"], ["--dry-run"], ["--dry-run", "--monitor-age"],
])
def test_flag_guards_exit_2(bash, root, args):
    assert _run(bash, root, *args).returncode == 2


def test_the_heartbeat_line_is_identical_with_and_without_the_monitor_check(bash, root):
    alone = _run(bash, root, "--dry-run", "--age", "30").stdout.splitlines()
    both = _run(bash, root, "--dry-run", "--age", "30",
                "--monitor-age", str(STALE + 1)).stdout.splitlines()
    assert len(alone) == 1 and len(both) == 2
    assert both[0].split(" ", 1)[1] == alone[0].split(" ", 1)[1]
    assert " monitor verdict=monitor_stale " in both[1]


# live runs: the state machine on logs/monitor_watch.state

def test_a_live_run_logs_the_heartbeat_line_first_then_the_monitor_line(bash, root):
    r = _run(bash, root, age=30, monitor=_row(tick_age=42, priced_age=10, positions=3))
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert len(lines) == 2
    assert re.fullmatch(f"{_ISO} verdict=ok age_s=30 threshold_s=900 previous=none action=none",
                        lines[0]), lines[0]
    tail = ("monitor verdict=ok tick_age_s=42 priced_age_s=10 market_open=true positions=3 "
            "previous=none action=none")
    assert re.fullmatch(f"{_ISO} {re.escape(tail)}", lines[1]), lines[1]
    assert _state(root, "heartbeat_watch") == "ok" and _state(root) == "ok"
    log = (root / "logs" / "heartbeat_watch.log").read_text(encoding="utf-8").splitlines()
    assert log == lines


def test_monitor_stale_posts_once_through_its_own_state(bash, root):
    r = _run(bash, root, monitor=_row(tick_age=STALE + 100))
    assert _monitor_line(r).endswith("action=alert delivered=yes")
    assert len(_posts(root)) == 1
    assert "Stop monitor STALE" in _posts(root)[0]
    assert f"last tick ended {STALE + 100}s ago (threshold {STALE}s)" in _posts(root)[0]
    assert _state(root) == "monitor_stale" and _state(root, "heartbeat_watch") == "ok"

    _run(bash, root, monitor=_row(tick_age=STALE + 400))
    assert len(_posts(root)) == 1


def test_monitor_recovers_once_through_its_own_state(bash, root):
    _run(bash, root, monitor=_row(tick_age=STALE + 100))
    r = _run(bash, root, monitor=_row(tick_age=20))
    assert " action=recover " in _monitor_line(r)
    assert len(_posts(root)) == 2
    assert "Stop monitor RECOVERED" in _posts(root)[1]
    assert "(was monitor_stale)" in _posts(root)[1]
    assert _state(root) == "ok"

    _run(bash, root, monitor=_row(tick_age=25))
    assert len(_posts(root)) == 2


def test_stops_unchecked_posts_the_count_tickers_and_causes(bash, root):
    row = _row(tick_age=30, priced_age=UNCHECKED + 60, positions=5, unquoted_count=2,
               unquoted="AAPL,MSFT", fetch_failed="true", check_errors="NVDA,<plan manager>")
    r = _run(bash, root, monitor=row)
    assert " monitor verdict=stops_unchecked " in _monitor_line(r)
    post = _posts(root)[0]
    assert "Stops UNCHECKED on " in post
    assert (f"4 position(s) not checked for {UNCHECKED + 60}s during the regular session "
            f"(AAPL,MSFT; fetch_failed=true; check_errors=NVDA,<plan manager>).") in post
    assert _state(root) == "stops_unchecked"


def test_an_unknown_book_reports_an_unknown_count(bash, root):
    _run(bash, root, monitor=_row(priced_age=UNCHECKED + 1, positions="null"))
    assert "unknown position(s) not checked" in _posts(root)[0]


def test_an_absent_key_is_not_deployed_and_silent(bash, root):
    r = _run(bash, root, monitor="absent")
    line = _monitor_line(r)
    assert " monitor verdict=not_deployed tick_age_s=absent " in line
    assert line.endswith(" action=none"), line
    assert _posts(root) == []
    assert _state(root) is None


def test_not_deployed_leaves_an_open_incident_alone(bash, root):
    _run(bash, root, monitor=_row(tick_age=STALE + 1))
    _run(bash, root, monitor="absent")
    assert _state(root) == "monitor_stale" and len(_posts(root)) == 1


def test_an_unreadable_monitor_is_its_own_incident_when_the_heartbeat_is_fine(bash, root):
    r = _run(bash, root, age=30, monitor=None)
    assert " monitor verdict=unreadable " in _monitor_line(r)
    assert _monitor_line(r).endswith(" action=alert delivered=yes")
    assert len(_posts(root)) == 1 and "Stop monitor UNREADABLE" in _posts(root)[0]
    assert _state(root) == "unreadable"


def test_one_database_outage_posts_once_not_twice(bash, root):
    r = _run(bash, root, age=None, monitor=None)
    assert r.returncode == 0, r.stderr
    assert _monitor_line(r).endswith(" suppressed=heartbeat-unreadable")
    assert len(_posts(root)) == 1 and "Heartbeat UNREADABLE" in _posts(root)[0]
    assert _state(root, "heartbeat_watch") == "unreadable"
    assert _state(root) is None


def test_no_webhook_and_failed_posts_leave_the_monitor_state_unarmed(bash, root):
    _env(root, SCAN_INTERVAL_MINUTES="5")
    r = _run(bash, root, monitor=_row(tick_age=STALE + 1))
    assert _monitor_line(r).endswith(" delivered=no-webhook") and _state(root) is None
    _env(root, SCAN_INTERVAL_MINUTES="5", OPS_ALERT_WEBHOOK_URL=URL)
    r = _run(bash, root, monitor=_row(tick_age=STALE + 1), curl_rc=22)
    assert _monitor_line(r).endswith(" delivered=failed") and _state(root) is None
    _run(bash, root, monitor=_row(tick_age=STALE + 1))
    assert _state(root) == "monitor_stale"


def test_the_two_incidents_never_mask_each_other(bash, root):
    _run(bash, root, age=5000, monitor=_row(tick_age=STALE + 1))
    posts = _posts(root)
    assert len(posts) == 2
    assert "Heartbeat STALE" in posts[0] and "Stop monitor STALE" in posts[1]
    _run(bash, root, age=30, monitor=_row(tick_age=STALE + 1))
    assert len(_posts(root)) == 3 and "Heartbeat RECOVERED" in _posts(root)[2]
    assert _state(root, "heartbeat_watch") == "ok" and _state(root) == "monitor_stale"


def test_a_broken_monitor_state_never_touches_the_heartbeat(bash, root):
    (root / "logs" / "monitor_watch.state").mkdir()      # neither readable nor writable as a file
    r = _run(bash, root, age=5000, monitor=_row(tick_age=STALE + 1))
    assert r.returncode == 0
    assert re.fullmatch(
        f"{_ISO} verdict=stale age_s=5000 threshold_s=900 previous=none action=alert delivered=yes",
        r.stdout.splitlines()[0]), r.stdout
    assert _state(root, "heartbeat_watch") == "stale"
