# v184 — Stop-monitor liveness, part 3: watch, rollback and release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md)
**Index:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](2026-10-21-v184-stop-monitor-liveness_0-index.md) holds the Goal, the Global Constraints, the Spec clarifications, the Contracts (§ Watch script, § Rollback) and the `## Parallelisation` table. Every task below obeys them.

This part covers tasks V184-8..V184-12: the heartbeat block of `scripts/ops/heartbeat_watch.sh` turned into a function, the monitor check with its verdicts, state file and dry-run flags, the rollback reminder and doc step, the bot patch bump with the plan's single full-suite run and the merge, and the read-only post-deploy verification. V184-8..V184-11 run in `.claude/worktrees/2026-10-21-v184-stop-monitor-liveness` (created by V184-1); every path below is relative to that worktree unless a step names the main tree. V184-12 runs after the merge, from the main tree, against production.

Shorthands used in commands: `WT=/e/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness`, `MAIN=/e/Documents/Private/Projects/Discord-Bot`, `BR=2026-10-21-v184-stop-monitor-liveness`.

# Phase 4 — The out-of-process watch

### Task V184-8: heartbeat_watch.sh: heartbeat block into a function (refactor)

**Model:** sonnet — a behaviour-preserving bash refactor with three early exits to unwind; the existing tests are the safety net, the judgement is keeping every byte of output identical.

**Files:**
- Modify: `scripts/ops/heartbeat_watch.sh` (main body, lines 122-150 today)
- Test: `tests/scripts/test_heartbeat_watch.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the bash function `heartbeat_check` (no arguments; reads `DRY_RUN`, `AGE_ARG`, `STATE_FILE`; logs exactly the line it logs today; never `exit`s) and the global `HB_VERDICT` (set to `ok`, `stale` or `unreadable` by `heartbeat_check`, `""` before it runs). V184-9 calls `heartbeat_check` and reads `HB_VERDICT` to suppress a double `unreadable` post.

**Why this task exists.** Today the heartbeat block is the script's main body and leaves through one of three `exit 0`s. V184-9 must run the monitor check *after* it on every path, so the block becomes a function that `return`s. This task changes nothing observable: same verdict line, same state file, same posts, same exit codes. Every pre-existing test in `tests/scripts/test_heartbeat_watch.py` passes **unmodified**; this task only adds tests.

- [ ] **Step 1: Write the new tests (one shape test that fails, line pins that pass before and after)**

In `tests/scripts/test_heartbeat_watch.py`, add `import re` to the imports (alphabetical, after `import pathlib`):

```python
import os
import pathlib
import re
import shlex
import shutil
import subprocess
```

Append to the `# --- shape (always runs) ---` block, right after `test_installer_schedules_every_five_minutes_and_replaces_its_own_line`:

```python
def test_the_heartbeat_block_is_one_function_that_never_exits():
    """v184: the heartbeat block returns, so a later check always runs after it."""
    text = _text("heartbeat_watch.sh")
    assert "\nheartbeat_check() {" in text
    assert 'HB_VERDICT="$verdict"' in text
    body = text.split("\nheartbeat_check() {", 1)[1].split("\n}\n", 1)[0]
    assert "exit" not in body
    assert body.count("return 0") == 3
    assert text.rstrip().endswith("exit 0")
```

Append at the end of the file (behaviour block):

```python
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
```

- [ ] **Step 2: Run the file and confirm only the shape test fails**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch.py
```

Expected: `test_the_heartbeat_block_is_one_function_that_never_exits` FAILS (`assert "\nheartbeat_check() {" in text`). Every other test, including the eight new line pins, PASSES. If a line pin fails here, the pin is wrong, not the script: fix the pin to match today's output before touching the script. (Where no bash can see the repo and the tmp dir, the behaviour tests skip and only the shape tests run. On this Windows machine `_working_bash` finds Git for Windows' bash.)

- [ ] **Step 3: Turn the main body into `heartbeat_check`**

In `scripts/ops/heartbeat_watch.sh`, insert this function after `post()` (after line 108, before `mkdir -p "$ROOT/logs"`). The body is today's lines 122-149 with each `exit 0` replaced by `return 0`, the locals declared, and `HB_VERDICT` set:

```bash
heartbeat_check() { # the v148 heartbeat verdict: one line, its own state file; sets HB_VERDICT
  local threshold age verdict previous action line
  threshold="$(stale_after)"
  if [ "$DRY_RUN" = 1 ]; then age="$AGE_ARG"; else age="$(read_age)"; fi
  verdict="$(verdict_for "$age" "$threshold")"
  HB_VERDICT="$verdict"
  previous="$(cat "$STATE_FILE" 2>/dev/null || true)"
  action="$(action_for "$verdict" "$previous")"
  line="$(now_iso) verdict=$verdict age_s=${age:-none} threshold_s=$threshold previous=${previous:-none} action=$action"

  if [ "$DRY_RUN" = 1 ]; then
    record "$line dry_run=1"
    return 0
  fi
  if [ "$action" = none ]; then
    echo "$verdict" > "$STATE_FILE"
    record "$line"
    return 0
  fi
  if [ -z "$(env_value OPS_ALERT_WEBHOOK_URL)" ]; then
    # State untouched: the incident posts on the first run after a URL is set.
    record "$line delivered=no-webhook"
    return 0
  fi
  if post "$(message_for "$action" "$verdict" "$age" "$threshold" "$previous")"; then
    echo "$verdict" > "$STATE_FILE"
    record "$line delivered=yes"
  else
    # State untouched: retried on the next run.
    record "$line delivered=failed"
  fi
}
```

Declare the locals on their own line (as above), never `local x="$(cmd)"`: that form hides a failing command's status from `set -e`.

Then replace today's lines 122-150 (from `threshold="$(stale_after)"` to the final `exit 0`) with:

```bash
HB_VERDICT=""
heartbeat_check
exit 0
```

The `--test` block above it (lines 113-120) stays exactly as it is. The argument loop and the `[ "$DRY_RUN" = "$AGE_GIVEN" ] || usage` guard stay exactly as they are (V184-9 changes them).

The end of the file now reads:

```bash
mkdir -p "$ROOT/logs"
touch "$LOG"

if [ "$TEST_POST" = 1 ]; then
  if post "[swingbot ops] heartbeat_watch TEST post from ${HOSTNAME:-the VM} at $(now_iso). No action needed."; then
    record "$(now_iso) test delivered=yes"
    exit 0
  fi
  record "$(now_iso) test delivered=no (OPS_ALERT_WEBHOOK_URL unset or the post failed)"
  exit 1
fi

HB_VERDICT=""
heartbeat_check
exit 0
```

Keep the file LF-only. Edit it with the Edit tool or a Python script, never `sed -i`, and never let an editor convert line endings. Check:

```bash
cd "$WT" && python -c "import pathlib; b = pathlib.Path('scripts/ops/heartbeat_watch.sh').read_bytes(); print('CRLF' if b'\r' in b else 'LF ok')"
```

Expected: `LF ok`.

- [ ] **Step 4: Run the file again**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch.py
```

Expected: every test PASSES, `0 failed`, including all pre-existing tests unmodified. Then confirm no pre-existing test line was edited:

```bash
cd "$WT" && git diff -U0 tests/scripts/test_heartbeat_watch.py | grep '^-' | grep -v '^---'
```

Expected: no output (the diff only adds lines).

- [ ] **Step 5: Commit**

```bash
cd "$WT"
git add scripts/ops/heartbeat_watch.sh tests/scripts/test_heartbeat_watch.py
git commit -m "refactor(v184): heartbeat_watch.sh heartbeat block into a function that returns

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V184-9: heartbeat_watch.sh: monitor check, verdicts, state file, dry-run flags

**Model:** sonnet — a bash state machine, a JSONB query and two test harnesses written against a fully pinned contract (index § Watch script); the traps are `set -e` inside `||`, the `|` row parse, and keeping the heartbeat line, its state and the exit code untouched.

**Files:**
- Modify: `scripts/ops/heartbeat_watch.sh` (header, constants, flags, new functions, main)
- Modify: `tests/scripts/test_heartbeat_watch.py` (the `docker` stub only: it now answers the monitor query with `absent`)
- Create: `tests/scripts/test_heartbeat_watch_monitor.py` (bash harness, dry-run and live verdicts)
- Create: `tests/scripts/test_heartbeat_watch_monitor_sql.py` (`MONITOR_SQL` against the test Postgres)

**Interfaces:**
- Consumes: `heartbeat_check` and global `HB_VERDICT` (V184-8); the `STOPS_UNCHECKED_S` value from the index's `## Threshold decision` line (V184-1); the `monitor` heartbeat key shape (index § Monitor stamp, written by V184-6/V184-7: `started_at`, `tick_at`, `positions` array or `null`, `unquoted`, `unquoted_count`, `fetch_failed`, `check_errors`, `priced_at` or `null`, `market_open`).
- Produces: in `heartbeat_watch.sh`, the constants `MONITOR_STATE_FILE`, `MONITOR_STALE_S=300`, `STOPS_UNCHECKED_S`, `MONITOR_SQL`; the functions `read_monitor`, `monitor_row`, `is_int`, `monitor_verdict_for`, `unchecked_count`, `monitor_message_for`, `monitor_deliver`, `monitor_check`; the flags `--monitor-age <s|absent|''>`, `--priced-age <s>`, `--market-open <true|false>`, `--positions <n|null>`; the log line `<iso> monitor verdict=...`; the state file `logs/monitor_watch.state`. V184-12 runs these flags on production.

**Why this task exists.** The watch reads only the scan loop's `timestamp`, so a wedged or dead trade monitor looks healthy (spec § Why, points 1-2). This task adds the second check the spec (§ 2) defines, after the heartbeat check and isolated from it.

**Behaviour, in one table** (index § Watch script is authoritative):

| verdict | condition, in this order | action | state file |
|---|---|---|---|
| `not_deployed` | the row is the literal `absent` | always `none` (logs only) | untouched |
| `unreadable` | `tick_age` not an integer (query failed, empty) | `action_for` | untouched and no post when `HB_VERDICT=unreadable` (` suppressed=heartbeat-unreadable`); otherwise like the heartbeat |
| `monitor_stale` | `tick_age > MONITOR_STALE_S` | `action_for` | like the heartbeat |
| `stops_unchecked` | `market_open = true` and `positions` is `null` or not `0`, and `priced_age > STOPS_UNCHECKED_S` (a non-integer `priced_age` here is `unreadable`) | `action_for` | like the heartbeat |
| `ok` | otherwise | `action_for` | like the heartbeat |

"Like the heartbeat" means: write the state on action `none` or on a delivered post; leave it untouched on no webhook or a failed post.

- [ ] **Step 1: Read the threshold V184-1 recorded**

```bash
cd "$WT" && awk '/^## Threshold decision/{f=1;next} /^## Contracts/{f=0} f' docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md | grep -n "STOPS_UNCHECKED_S="
```

Expected: exactly one dated line, e.g. ``- **2026-10-22:** kept `STOPS_UNCHECKED_S=600` (case 1: …)``. Use that value wherever this task writes `STOPS_UNCHECKED_S=600` below. If there is no such line, stop and report `BLOCKED: V184-1 has not recorded the stops_unchecked threshold`. The tests read the value back out of the script, so they need no edit for a value other than 600.

- [ ] **Step 2: Teach the existing harness's `docker` stub about the monitor query**

After this task, every live run of the script also runs the monitor query. The old stub answers every `docker` call with `$STUB/age`, which would turn the heartbeat age into a monitor row and post. So the stub must answer the monitor query on its own. With no `$STUB/monitor` file it prints `absent`, which gives `not_deployed`: silent, no post, no state. Every existing assertion then holds unchanged.

In `tests/scripts/test_heartbeat_watch.py`, replace the comment and the `_STUBS` definition (lines 24-31) with:

```python
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
```

No other line of that file changes. The heartbeat `SQL` does not contain the word `monitor`, so the `*monitor*` branch can only match the new query.

- [ ] **Step 3: Write the bash harness tests**

Create `tests/scripts/test_heartbeat_watch_monitor.py`:

```python
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


def test_monitor_stale_posts_once_then_recovers_once_through_its_own_state(bash, root):
    r = _run(bash, root, monitor=_row(tick_age=STALE + 100))
    assert _monitor_line(r).endswith("action=alert delivered=yes")
    assert len(_posts(root)) == 1
    assert "Stop monitor STALE" in _posts(root)[0]
    assert f"last tick ended {STALE + 100}s ago (threshold {STALE}s)" in _posts(root)[0]
    assert _state(root) == "monitor_stale" and _state(root, "heartbeat_watch") == "ok"

    _run(bash, root, monitor=_row(tick_age=STALE + 400))
    assert len(_posts(root)) == 1

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
```

- [ ] **Step 4: Write the SQL test**

Create `tests/scripts/test_heartbeat_watch_monitor_sql.py`. It runs the script's own `MONITOR_SQL` string against the test Postgres inside a rolled-back transaction (`db_conn`, from `tests/db/conftest.py`, registered globally by `tests/conftest.py`):

```python
"""v184: MONITOR_SQL from heartbeat_watch.sh against a real Postgres.

The query is read out of the script, so this pins the exact string cron runs.
Each test writes the bot_heartbeat row inside a rolled-back transaction, and
computes every expected age from the transaction's own now(). Skips when the
test database is not up (docker compose --profile test up -d db-test)."""
import datetime as dt
import json
import math
import re
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from tests.scripts.test_heartbeat_watch import SCRIPT

NY = ZoneInfo("America/New_York")
MONITOR_SQL = re.search(r'^MONITOR_SQL="(.*)"$', SCRIPT.read_text(encoding="utf-8"), re.M).group(1)


def _now(conn):
    return conn.execute(sa.text("SELECT now()")).scalar_one()


def _ago(now, seconds):
    """A whole-second instant `seconds` before now (the stamp writes whole seconds)."""
    return (now - dt.timedelta(seconds=seconds)).replace(microsecond=0)


def _iso(ts):
    return ts.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _today_open(now):
    return dt.datetime.combine(now.astimezone(NY).date(), dt.time(9, 30), tzinfo=NY)


def _age(now, then):
    return math.floor((now - then).total_seconds())


def _monitor(now, **over):
    doc = {"started_at": _iso(_ago(now, 90000)), "tick_at": _iso(_ago(now, 42)),
           "outcome": "ok", "positions": ["AAPL", "MSFT", "NVDA"],
           "unquoted": ["AAPL", "MSFT"], "unquoted_count": 2, "fetch_failed": True,
           "check_errors": ["<plan manager>"], "priced_at": _iso(_ago(now, 700)),
           "market_open": True}
    doc.update(over)
    return doc


def _put(conn, doc):
    conn.execute(sa.text("DELETE FROM bot_heartbeat"))
    conn.execute(sa.text("INSERT INTO bot_heartbeat (key, ts, doc) "
                         "VALUES ('bot', now(), CAST(:doc AS jsonb))"), {"doc": json.dumps(doc)})


def _query(conn):
    return conn.exec_driver_sql(MONITOR_SQL).scalar_one_or_none()


def test_no_row_reads_as_nothing(db_conn):
    db_conn.execute(sa.text("DELETE FROM bot_heartbeat"))
    assert _query(db_conn) is None


def test_a_row_without_the_monitor_key_reads_absent(db_conn):
    _put(db_conn, {"timestamp": _iso(_now(db_conn))})
    assert _query(db_conn) == "absent"


def test_a_full_monitor_key_reads_as_one_row_of_eight_fields(db_conn):
    now = _now(db_conn)
    tick, priced = _ago(now, 42), _ago(now, 700)
    _put(db_conn, {"timestamp": _iso(now),
                   "monitor": _monitor(now, tick_at=_iso(tick), priced_at=_iso(priced))})
    fields = _query(db_conn).split("|")
    assert len(fields) == 8
    assert fields[0] == str(_age(now, tick))
    assert fields[1] == str(_age(now, max(priced, _today_open(now))))
    assert fields[2:] == ["true", "3", "2", "AAPL,MSFT", "true", "<plan manager>"]


def test_a_null_priced_at_counts_from_started_at(db_conn):
    now = _now(db_conn)
    started = _ago(now, 120)
    _put(db_conn, {"monitor": _monitor(now, priced_at=None, started_at=_iso(started))})
    fields = _query(db_conn).split("|")
    assert fields[1] == str(_age(now, max(started, _today_open(now))))


def test_yesterdays_priced_at_counts_from_todays_open(db_conn):
    now = _now(db_conn)
    priced = _ago(now, 2 * 86400)
    _put(db_conn, {"monitor": _monitor(now, priced_at=_iso(priced))})
    fields = _query(db_conn).split("|")
    assert fields[1] == str(_age(now, _today_open(now)))
    assert int(fields[1]) < _age(now, priced)


def test_unknown_positions_and_empty_lists(db_conn):
    now = _now(db_conn)
    _put(db_conn, {"monitor": _monitor(now, positions=None, unquoted=[], unquoted_count=0,
                                       fetch_failed=False, check_errors=[], market_open=False)})
    assert _query(db_conn).split("|")[2:] == ["false", "null", "0", "", "false", ""]


def test_missing_fields_read_as_unknown_never_as_zero(db_conn):
    now = _now(db_conn)
    _put(db_conn, {"monitor": {"tick_at": _iso(_ago(now, 5)), "started_at": _iso(_ago(now, 60))}})
    fields = _query(db_conn).split("|")
    assert fields[0] == "5"
    assert fields[2:] == ["", "null", "0", "", "false", ""]
```

`exec_driver_sql` sends the string as-is (no SQLAlchemy bind parsing of `:30` in `'09:30'` or of `::`). `concat_ws` skips NULL arguments, which would shift the fields; every argument in `MONITOR_SQL` is wrapped in `coalesce` or a `CASE` for exactly that reason, and the last two tests pin it.

- [ ] **Step 5: Run the new tests and confirm they fail**

If this is the session's first database test run, run `/replicate-prod-db` first (CLAUDE.md), and make sure the test database is up (`docker compose --profile test up -d db-test`).

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch_monitor.py
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch_monitor_sql.py
```

Expected: both files fail at import or collection with `AttributeError: 'NoneType' object has no attribute 'group'` (the script has no `MONITOR_STALE_S` / `MONITOR_SQL` yet).

- [ ] **Step 6: Header, constants and flags**

In `scripts/ops/heartbeat_watch.sh`, replace the two owner lines (14-15) and the usage block (17-21) with:

```bash
# v184: a second check follows the heartbeat check, for the trade monitor's own
# `monitor` key in the same row (swingbot/commands/scanning/monitor_liveness.py,
# written at the end of every 60 s tick, at most every 120 s unless something
# material changed). Verdicts: monitor_stale (last tick ended > 300 s ago, any
# hour), stops_unchecked (NYSE regular session, positions open or unknown, not
# all checked for > STOPS_UNCHECKED_S, counted from the later of the last clean
# tick and today's 09:30 ET), not_deployed (no key: logged, silent), unreadable
# (not posted when the heartbeat is unreadable in the same run). Its own line
# ("<iso> monitor verdict=..."), after the heartbeat line in the same log, and
# its own state file, logs/monitor_watch.state. Nothing in it can change the
# heartbeat line, the heartbeat state or the exit code.
#
# Owner: the partner (ops), for both checks and both state files. Permanent:
# removed only when a monitor outside the VM replaces it, by its own spec,
# together with logs/monitor_watch.state. It dies with the VM.
#
#   heartbeat_watch.sh                       # the cron run: both checks
#   heartbeat_watch.sh --dry-run --age 42    # heartbeat verdict for a given age (s): no psql,
#                                            # no curl, no state write
#   heartbeat_watch.sh --dry-run --age ''    # verdict for an unreadable heartbeat
#   heartbeat_watch.sh --dry-run --monitor-age 42 [--priced-age 700] [--market-open true]
#                      [--positions 3|null]  # monitor verdict only (defaults 0, false, 0)
#   heartbeat_watch.sh --dry-run --monitor-age absent   # a pre-v184 row: not_deployed
#   heartbeat_watch.sh --test                # force one test post (exit 1 if not delivered)
```

After the `SQL=...` line (32), add:

```bash
MONITOR_STATE_FILE="$ROOT/logs/monitor_watch.state"
MONITOR_STALE_S=300
STOPS_UNCHECKED_S=600
# One row: tick_age|priced_age|market_open|positions|unquoted_count|unquoted|fetch_failed|check_errors,
# or the literal `absent` (no monitor key). priced_age counts from the later of
# priced_at (or started_at after a restart) and today's 09:30 ET.
MONITOR_SQL="SELECT CASE WHEN NOT (doc ? 'monitor') THEN 'absent' ELSE concat_ws('|', coalesce(floor(extract(epoch FROM now() - (doc->'monitor'->>'tick_at')::timestamptz))::bigint::text, ''), coalesce(floor(extract(epoch FROM now() - greatest(coalesce((doc->'monitor'->>'priced_at')::timestamptz, (doc->'monitor'->>'started_at')::timestamptz), ((now() AT TIME ZONE 'America/New_York')::date + time '09:30') AT TIME ZONE 'America/New_York')))::bigint::text, ''), coalesce(doc->'monitor'->>'market_open', ''), CASE WHEN jsonb_typeof(doc->'monitor'->'positions') = 'array' THEN jsonb_array_length(doc->'monitor'->'positions')::text ELSE 'null' END, coalesce(doc->'monitor'->>'unquoted_count', '0'), coalesce((SELECT string_agg(value, ',') FROM jsonb_array_elements_text(coalesce(doc->'monitor'->'unquoted', '[]'::jsonb))), ''), coalesce(doc->'monitor'->>'fetch_failed', 'false'), coalesce((SELECT string_agg(value, ',') FROM jsonb_array_elements_text(coalesce(doc->'monitor'->'check_errors', '[]'::jsonb))), '')) END FROM bot_heartbeat WHERE key = 'bot'"
```

(`STOPS_UNCHECKED_S` takes the value from Step 1.) `MONITOR_SQL` stays on one physical line: the SQL test extracts it with `^MONITOR_SQL="(.*)"$`.

Replace the flag variables (lines 34-37), `usage`, the argument loop and the guard (lines 39-53) with:

```bash
DRY_RUN=0
TEST_POST=0
AGE_GIVEN=0
AGE_ARG=""
MON_GIVEN=0
MON_AGE_ARG=0
PRICED_AGE_ARG=0
MARKET_OPEN_ARG=false
POSITIONS_ARG=0

usage() {
  echo "usage: heartbeat_watch.sh [--dry-run [--age <seconds>] [--monitor-age <s|absent> --priced-age <s> --market-open <true|false> --positions <n|null>]] [--test]" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --age) [ "$#" -ge 2 ] || usage; AGE_ARG="$2"; AGE_GIVEN=1; shift ;;
    --monitor-age) [ "$#" -ge 2 ] || usage; MON_AGE_ARG="$2"; MON_GIVEN=1; shift ;;
    --priced-age) [ "$#" -ge 2 ] || usage; PRICED_AGE_ARG="$2"; MON_GIVEN=1; shift ;;
    --market-open) [ "$#" -ge 2 ] || usage; MARKET_OPEN_ARG="$2"; MON_GIVEN=1; shift ;;
    --positions) [ "$#" -ge 2 ] || usage; POSITIONS_ARG="$2"; MON_GIVEN=1; shift ;;
    --test) TEST_POST=1 ;;
    *) usage ;;
  esac
  shift
done
# A dry run needs --age, a monitor flag, or both; those flags need a dry run.
# Bare --dry-run still exits 2.
[ "$DRY_RUN" = 1 ] || [ "$AGE_GIVEN$MON_GIVEN" = 00 ] || usage
[ "$DRY_RUN" = 0 ] || [ "$AGE_GIVEN$MON_GIVEN" != 00 ] || usage
```

- [ ] **Step 7: The monitor functions**

Insert after `heartbeat_check` (V184-8), before `mkdir -p "$ROOT/logs"`:

```bash
read_monitor() {    # one '|' row from the monitor key, the literal absent, or nothing
  { (cd "$ROOT" && docker compose exec -T db psql -U swingbot -d swingbot -tA \
      -v ON_ERROR_STOP=1 -c "$MONITOR_SQL" </dev/null 2>/dev/null) || true; } | tr -d '\r\n'
}

monitor_row() {     # the dry-run flags as a row, or the live row
  if [ "$DRY_RUN" = 0 ]; then read_monitor; return 0; fi
  if [ "$MON_AGE_ARG" = absent ]; then echo absent; return 0; fi
  echo "$MON_AGE_ARG|$PRICED_AGE_ARG|$MARKET_OPEN_ARG|$POSITIONS_ARG|0||false|"
}

is_int() { [[ "$1" =~ ^-?[0-9]+$ ]]; }

monitor_verdict_for() { # tick_age priced_age market_open positions -> one verdict
  if [ "$1" = absent ]; then echo not_deployed; return 0; fi
  if ! is_int "$1"; then echo unreadable; return 0; fi
  if [ "$1" -gt "$MONITOR_STALE_S" ]; then echo monitor_stale; return 0; fi
  if [ "$3" != true ] || [ "$4" = 0 ]; then echo ok; return 0; fi
  if ! is_int "$2"; then echo unreadable; return 0; fi
  if [ "$2" -gt "$STOPS_UNCHECKED_S" ]; then echo stops_unchecked; else echo ok; fi
}

unchecked_count() { # positions unquoted_count check_errors -> n for the message, or unknown
  local errors=0
  if [ "$1" = null ] || ! is_int "$2"; then echo unknown; return 0; fi
  if [ -n "$3" ]; then errors=$(( $(printf '%s' "$3" | tr -cd ',' | wc -c) + 1 )); fi
  echo $(( $2 + errors ))
}

monitor_message_for() { # action verdict tick_age priced_age n tickers fetch_failed check_errors previous
  local host="${HOSTNAME:-the VM}"
  case "$1:$2" in
    alert:monitor_stale) echo "[swingbot ops] Stop monitor STALE on $host: last tick ended $3s ago (threshold ${MONITOR_STALE_S}s). Open stops are not being checked." ;;
    alert:stops_unchecked) echo "[swingbot ops] Stops UNCHECKED on $host: $5 position(s) not checked for $4s during the regular session (${6:-none}; fetch_failed=${7:-false}; check_errors=${8:-none})." ;;
    alert:unreadable) echo "[swingbot ops] Stop monitor UNREADABLE on $host: cannot read the monitor key from bot_heartbeat. Check docker compose ps (is db up?)." ;;
    *) echo "[swingbot ops] Stop monitor RECOVERED on $host: last tick ended $3s ago and stops are being checked (was $9)." ;;
  esac
}

monitor_deliver() { # verdict action line message -> logs the line with one suffix, keeps the state
  if [ "$DRY_RUN" = 1 ]; then record "$3 dry_run=1"; return 0; fi
  if [ "$1" = unreadable ] && [ "$HB_VERDICT" = unreadable ]; then
    # One database outage posts once (the heartbeat's post); state untouched.
    record "$3 suppressed=heartbeat-unreadable"
    return 0
  fi
  if [ "$1" = not_deployed ]; then record "$3"; return 0; fi   # pre-v184 row: silent, state untouched
  if [ "$2" = none ]; then
    echo "$1" > "$MONITOR_STATE_FILE"
    record "$3"
    return 0
  fi
  if [ -z "$(env_value OPS_ALERT_WEBHOOK_URL)" ]; then
    record "$3 delivered=no-webhook"   # state untouched: posts once a URL is set
    return 0
  fi
  if post "$4"; then
    echo "$1" > "$MONITOR_STATE_FILE"
    record "$3 delivered=yes"
  else
    record "$3 delivered=failed"       # state untouched: retried on the next run
  fi
}

monitor_check() {   # the v184 stop-monitor verdict: its own line after the heartbeat's, its own state
  local row tick_age priced_age market_open positions unquoted_count tickers fetch_failed check_errors
  local verdict previous action line n message
  row="$(monitor_row)"
  IFS='|' read -r tick_age priced_age market_open positions unquoted_count tickers fetch_failed \
    check_errors <<< "$row" || true
  verdict="$(monitor_verdict_for "$tick_age" "$priced_age" "$market_open" "$positions")"
  previous="$(cat "$MONITOR_STATE_FILE" 2>/dev/null || true)"
  action=none
  [ "$verdict" = not_deployed ] || action="$(action_for "$verdict" "$previous")"
  line="$(now_iso) monitor verdict=$verdict tick_age_s=${tick_age:-none} priced_age_s=${priced_age:-none} market_open=${market_open:-none} positions=${positions:-none} previous=${previous:-none} action=$action"
  n="$(unchecked_count "$positions" "$unquoted_count" "$check_errors")"
  message="$(monitor_message_for "$action" "$verdict" "$tick_age" "$priced_age" "$n" "$tickers" "$fetch_failed" "$check_errors" "$previous")"
  monitor_deliver "$verdict" "$action" "$line" "$message"
}
```

Notes for the implementer:
- `read_monitor` strips only `\r` and `\n`, never all whitespace: `<plan manager>` carries a space.
- `monitor_check` runs on the left of `||` in main, so bash disables `set -e` inside it. A failing command there (an unwritable state file, say) does not abort; it falls through to the next line, and the run still exits 0. That is the isolation the spec asks for, and `test_a_broken_monitor_state_never_touches_the_heartbeat` pins it.
- No message contains `"` or `\`: `post` builds its JSON body by string interpolation.

- [ ] **Step 8: Main**

Replace the three-line main from V184-8 (`HB_VERDICT=""`, `heartbeat_check`, `exit 0`) with:

```bash
HB_VERDICT=""
if [ "$DRY_RUN" = 0 ] || [ "$AGE_GIVEN" = 1 ]; then heartbeat_check; fi
if [ "$DRY_RUN" = 0 ] || [ "$MON_GIVEN" = 1 ]; then
  monitor_check || record "$(now_iso) monitor verdict=error action=none"
fi
exit 0
```

Check LF endings as in V184-8 Step 3 (`LF ok`), and that `sed -i`, `source ` and `. "$ROOT/.env"` still appear nowhere in the script.

- [ ] **Step 9: Run all three script test files**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch.py
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch_monitor.py
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch_monitor_sql.py
```

Expected: all PASS, `0 failed`. In `test_heartbeat_watch.py` that includes every pre-existing test and V184-8's byte-for-byte line pins, with only the stub edited. If the SQL file reports skips, the test database is not up: start it (`docker compose --profile test up -d db-test`) and re-run that file alone. A skip is not a pass for this task.

Then the suite this directory belongs to, once, for the neighbours (`tests/scripts/` is suite `tooling`):

```bash
cd "$WT" && python scripts/dev/testrun.py suite tooling
```

Expected: `0 failed`.

- [ ] **Step 10: Commit**

```bash
cd "$WT"
git add scripts/ops/heartbeat_watch.sh tests/scripts/test_heartbeat_watch.py \
  tests/scripts/test_heartbeat_watch_monitor.py tests/scripts/test_heartbeat_watch_monitor_sql.py
git commit -m "feat(v184): heartbeat watch alerts on a stale stop monitor and on stops unchecked in session

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


# Phase 5 — Rollback and release

### Task V184-10: Rollback: key-removal step in DEPLOY_HETZNER and rollback_to.sh reminder

**Model:** haiku — one printed reminder and two doc paragraphs with fixed text, pinned by shape tests; no logic.

**Files:**
- Modify: `scripts/ops/rollback_to.sh` (step 9, after the "Scanning is PAUSED" line, today line 93)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (`## Rolling back`, and `### Point-in-time rollback`)
- Test: `tests/scripts/test_rollback_to_shape.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (the key name `monitor` and the watch verdicts `not_deployed` / `monitor_stale` are fixed by the index § Contracts).
- Produces: nothing later tasks call.

**Why this task exists.** A rollback swaps the image (and, for `rollback_to.sh`, Postgres), but the VM's checkout keeps the new `heartbeat_watch.sh`. A database restored to before v184 has no `monitor` key, which the watch reads as `not_deployed` and keeps silent. A stale key left behind by an image-only rollback reads `monitor_stale` for good. Removing the key turns that into `not_deployed` (spec § 3). The SQL is a no-op when the key is absent, so printing the reminder after every rollback is harmless.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_rollback_to_shape.py`:

```python
MONITOR_KEY_SQL = "UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'"
DEPLOY_DOC = SCRIPT.parents[2] / "docs" / "deploy" / "DEPLOY_HETZNER.md"


def test_it_reminds_to_clear_the_v184_monitor_key_after_the_restart(src):
    """v184 spec section 3: a stale `monitor` key reads monitor_stale for good."""
    assert "REMINDER (v184)" in src and MONITOR_KEY_SQL in src
    start = src.index("docker compose up -d --no-build --wait bot admin")
    paused = src.index("Scanning is PAUSED")
    reminder = src.index("REMINDER (v184)")
    finished = src.index('rollback to $TARGET finished')
    assert start < paused < reminder < finished


def test_the_deploy_doc_names_the_key_removal_in_both_rollback_sections():
    doc = DEPLOY_DOC.read_text(encoding="utf-8")
    image = doc.split("\n## Rolling back\n", 1)[1].split("\n### After every deploy or rollback", 1)[0]
    pitr = doc.split("\n### Point-in-time rollback\n", 1)[1].split("\n**Backups.**", 1)[0]
    assert MONITOR_KEY_SQL in image
    assert "not_deployed" in image and "monitor_stale" in image
    assert "REMINDER (v184)" in pitr and "Rolling back" in pitr
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py
```

Expected: the two new tests FAIL (`assert "REMINDER (v184)" in src`, and the doc assertion on `MONITOR_KEY_SQL`). The four existing tests PASS.

- [ ] **Step 3: Print the reminder in `rollback_to.sh`**

In `scripts/ops/rollback_to.sh`, between the `echo "Scanning is PAUSED. …"` line and the `echo "$(date -u …) rollback to $TARGET finished" >> "$LOG"` line, insert:

```bash
cat <<'V184_REMINDER'
REMINDER (v184): if the restored image predates v184, clear the stale monitor key: docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c "UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'"
V184_REMINDER
```

A quoted heredoc prints the line exactly, double and single quotes included, and needs no escaping. The tail of the script now reads:

```bash
echo "Restored: Postgres to $TARGET, market_data to $restic_time, .env $env_file, images of git $git_sha."
echo "Scanning is PAUSED. Unpause from the admin UI once the book looks right."
cat <<'V184_REMINDER'
REMINDER (v184): if the restored image predates v184, clear the stale monitor key: docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c "UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'"
V184_REMINDER
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback to $TARGET finished" >> "$LOG"
```

Keep the file LF-only (an existing test checks it), and never use `sed -i`.

- [ ] **Step 4: Add the step to `DEPLOY_HETZNER.md`**

In `## Rolling back`, right after the paragraph that ends `…the "Publishing as …" line of the run that shipped it.` (before `**The admin's server is chosen inside the image (v148).**`), insert:

````markdown
**Rolling back past v184: clear the stop-monitor key.** From v184 the trade
monitor writes a `monitor` key into the `bot_heartbeat` row, and
`scripts/ops/heartbeat_watch.sh`, which the checkout keeps across a rollback,
alerts on it. A pre-v184 image never rewrites that key, so it ages and the
watch reads `monitor_stale` for good. After rolling back to an image older than
v184, remove the key once. An absent key reads `not_deployed`, which is logged
and never posted:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c \"UPDATE bot_heartbeat SET doc = doc - 'monitor' WHERE key = 'bot'\""
```

Rolling forward again needs nothing: the first tick of a v184-or-later bot
writes the key back.
````

In `### Point-in-time rollback`, after the paragraph that ends `…both start from compose's python admin_ui.py, so no compose edit is needed either way (see "Rolling back").` (lines 335-338 today; before `**Backups.**`), insert:

```markdown
The script ends with a `REMINDER (v184)` line. If the restored image predates
v184 while the `monitor` key survived the restore, clear the key with the
command in "Rolling back". When the key is absent, that command changes
nothing, so it is safe to run whenever in doubt.
```

- [ ] **Step 5: Run the tests**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_rollback_to_shape.py
cd "$WT" && bash -n scripts/ops/rollback_to.sh && echo "syntax ok"
```

Expected: 6 passed, `0 failed`; `syntax ok`.

- [ ] **Step 6: Commit**

```bash
cd "$WT"
git add scripts/ops/rollback_to.sh docs/deploy/DEPLOY_HETZNER.md tests/scripts/test_rollback_to_shape.py
git commit -m "docs(v184): rollback clears a stale stop-monitor key; rollback_to.sh prints the reminder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V184-11: Bot patch bump, full suite, merge

**Model:** sonnet — release mechanics with fixed commands and one judgement call (stopping on a conflict, a red suite or a missing threshold line); no product code.

This task holds the plan's single full-suite run, then the release commits and the merge to `main`. The order is fixed:
1. Check the gates.
2. Sync `main` into the branch.
3. Run the full suite.
4. Bump.
5. Merge.

No full suite runs after the merge (CLAUDE.md). `/close-out` is **not** run here: it waits for V184-12, whose results doc is part of what close-out records.

**Files:**
- Modify: `VERSION.json` (the `bot` line and `bot_updated` only)
- Modify: `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`, never hand-edited)

**Interfaces:**
- Consumes: every commit of V184-1..V184-10 on branch `2026-10-21-v184-stop-monitor-liveness`, including V184-1's dated line under the index's `## Threshold decision`.
- Produces: the merged branch on `main`, with two release commits (`release(bot)`, then `chore(bot)`). V184-12 verifies that release on production once it is deployed.

Run every command with `git -C` and the absolute paths `$WT` / `$MAIN` from the part header, never by `cd`-ing between trees.

- [ ] **Step 1: Check the gates: branch complete, threshold recorded, main tree clean**

```bash
git -C "$WT" status --short                 # expected: empty
git -C "$WT" log --oneline main..HEAD       # expected: the V184-1..V184-10 commits
awk '/^## Threshold decision/{f=1;next} /^## Contracts/{f=0} f' \
  "$WT/docs/superpowers/plans/2026-10-21-v184-stop-monitor-liveness_0-index.md" | grep -c "STOPS_UNCHECKED_S="
grep -n "^STOPS_UNCHECKED_S=" "$WT/scripts/ops/heartbeat_watch.sh"
ls "$WT"/docs/superpowers/results/*-v184-stops-unchecked-threshold.md
git -C "$MAIN" status --short -- swingbot scripts tests docs/deploy VERSION.json   # expected: no v184 path
```

Expected:
- the `grep -c` prints `1`;
- the script's `STOPS_UNCHECKED_S=` value equals the value in that index line;
- exactly one threshold results doc.

**If the index line is missing, stop and do not merge** (index § Threshold decision). Report `BLOCKED: no stops_unchecked threshold line`. If the two values differ, fix the script constant in a `fix(v184): …` commit, re-run `python scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch_monitor.py`, and carry on. If the main tree shows a v184 path (a subagent edited the wrong tree), stop and report it; revert it there only if it matches the branch's commit for that file.

- [ ] **Step 2: Bring `main` into the branch, so the suite runs on what will merge**

```bash
git -C "$WT" rev-list --count HEAD..main    # commits on main the branch lacks
```

If the count is 0, go to Step 3. Otherwise run `git -C "$WT" merge --no-edit main`. On a conflict, run `git -C "$WT" merge --abort` and stop: another session's work is involved (`worktree-lifecycle`), and the partner decides. Never resolve a conflict in another plan's file.

- [ ] **Step 3: Run the full suite once, through `test-runner`**

The suite includes database tests: if no database test has run in this session yet, run `/replicate-prod-db` first (CLAUDE.md), and make sure the test database is up (`docker compose --profile test up -d db-test`).

Dispatch the `test-runner` agent with this exact instruction:

> In `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-21-v184-stop-monitor-liveness`, run `python scripts/dev/testrun.py full` and report only the verdict line, the failed/xfailed test ids if any, the skipped count for `tests/scripts/test_heartbeat_watch_monitor_sql.py` and `tests/scripts/test_heartbeat_watch_monitor.py`, and the complexity-gate result.

Expected:
- `0 failed`, `0 xfailed`;
- complexity gate clean, which proves `loops.trade_monitor` is below 15 and `PlanManager.poll` did not grow past its baseline of 20;
- the two v184 script files report no skips (a skip there means bash or the test database was missing, and the new watch was not exercised: fix the environment and re-run those files alone).

A changed pass count is not a failure (`testing-cost.md`). There is no frontend change in v184, so no `ng test` run.

On any failure:
1. Fix it in the file of the task that owns the failing behaviour.
2. Re-run that test alone (`python scripts/dev/testrun.py file <test>`).
3. Commit `fix(v184): <what> -- <why>`.

Never re-run the full suite for a fix. A failure in code no v184 task touched that also fails on `main` is pre-existing: record its id in the task report and carry on.

- [ ] **Step 4: Bump `bot` by one patch, resolved from `VERSION.json` now**

Read `"$WT/VERSION.json"`, never this plan's numbers: after Step 2 it equals `main`'s file, and v183 may already have moved `bot`. The header says **Bump: bot patch**, so `X.Y.Z` → `X.Y.(Z+1)`, and `ui` stays untouched. The stamp format is `YYYY-MM-DD HH-MM-SS` in Europe/Berlin time, as in the existing file; Git Bash has no timezone data, so take it from Python:

```bash
cd "$WT" && python - <<'PYEOF'
import datetime, json, pathlib, zoneinfo
p = pathlib.Path("VERSION.json")
v = json.loads(p.read_text(encoding="utf-8"))
major, minor, patch = (int(x) for x in v["bot"].split("."))
v["bot"] = f"{major}.{minor}.{patch + 1}"
v["bot_updated"] = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H-%M-%S")
p.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")
print("bot", v["bot"])
PYEOF
git -C "$WT" diff VERSION.json
```

Expected: `bot <next patch>`; the diff shows exactly the `bot` and `bot_updated` lines changed.

Commit `VERSION.json` alone, then regenerate the history and commit it alone (close-out Step 4 order: bump, then regenerate, never combined):

```bash
git -C "$WT" add VERSION.json
git -C "$WT" commit -m "release(bot): <bot version> -- the stop monitor stamps its own liveness, and the VM watch alerts when open stops stop being checked (v184)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd "$WT" && python scripts/dev/build_version_matrix.py
git -C "$WT" add swingbot/admin/version_history.json
git -C "$WT" commit -m "chore(bot): <bot version> -- the stop monitor stamps its own liveness, and the VM watch alerts when open stops stop being checked (v184)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd "$WT" && python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: the last run passes (the regenerated file's `current` pair equals `VERSION.json`).

- [ ] **Step 5: Merge into `main`**

```bash
git worktree list                                  # the v184 worktree is listed; note any other live worktree
git -C "$MAIN" branch --show-current               # expected: main
git -C "$MAIN" rev-list --count "$BR"..main        # expected: 0
```

A non-zero count means `main` moved since Step 2. Repeat Step 2 in the worktree.
- If the new `main` commits include a `VERSION.json` bump, the merge conflicts on it. Abort the merge, drop nothing, and redo Step 4 on top of `main`'s values in a new release-then-chore pair.
- Re-run only the tests the merged-in commits reach: `python scripts/dev/testrun.py changed`. This is not the full suite.

Then merge from the main tree:

```bash
git -C "$MAIN" merge --no-ff "$BR" -m "merge(v184): stop-monitor liveness -- monitor heartbeat key, monitor_stale and stops_unchecked ops alerts, rollback step

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$MAIN" log --oneline -1                    # expected: the merge(v184) commit
git -C "$MAIN" rev-list --count main.."$BR"        # expected: 0
```

If the merge stops on a conflict in the main tree, run `git -C "$MAIN" merge --abort` and report it; do not resolve it there. Do not run the full suite after the merge. Do not push and do not deploy: pushing `main` runs CI, which deploys to production, and that is the controller's call with the partner (`mirror-prod`). Report the merge commit id and the new `bot` version; V184-12 starts once that version is live.

### Task V184-12: Post-deploy read-only verification on production

**Model:** sonnet — read-only production checks with fixed commands and expected outputs; the judgement is telling a real incident from a verification slip, and stopping before the one outward-facing post.

**Files:**
- Create: `docs/superpowers/results/<run-date>-v184-post-deploy-verification.md` (on `main`, in the main tree; `<run-date>` is the day you run it, `YYYY-MM-DD`)
- Scratch (not committed): `<scratchpad>/v184_dryruns.sh`
- Moves at close-out (done by `/close-out` in Step 8, listed so the reviewer expects them):
  - the four plan files (`_0-index`, `_1-measurement-and-core-signals`, `_2-monitor-stamp`, `_3-watch-rollback-and-release`) → `docs/superpowers/plans/implemented/`
  - the spec → `docs/superpowers/specs/implemented/`

**Interfaces:**
- Consumes: the `merge(v184)` commit and the new `bot` version from V184-11, deployed to production by the normal CI deploy (a push of `main`, triggered by the controller with the partner); the watch flags from V184-9; the `monitor` key from V184-7.
- Produces: the verification record that closes the plan.

**Production is read-only here,** with one exception: the single `--test` post in Step 6, which only the controller sends, and only after the partner says yes. The dry runs use a throwaway root under `/tmp`, so the production log and state files are not touched. Connect only through `bash scripts/ops/ssh-hetzner.sh` (CLAUDE.md). The wrapper expands `$(...)` locally, so every multi-command check is piped in on stdin. No fault is injected (spec § Rollout).

- [ ] **Step 1: Confirm v184 is what runs**

Put the merge commit id from V184-11 in place of `<merge-sha>`:

```bash
cd "$MAIN"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && git log --oneline -1 && git merge-base --is-ancestor <merge-sha> HEAD && echo checkout-has-v184"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot cat VERSION.json"
bash scripts/ops/ssh-hetzner.sh "crontab -l | grep -F heartbeat_watch.sh"
```

Expected:
- `checkout-has-v184`;
- the container's `bot` value equals the version V184-11 released;
- the cron line is unchanged: `*/5 * * * * /usr/bin/env bash /opt/swing-bot/scripts/ops/heartbeat_watch.sh >/dev/null 2>> /opt/swing-bot/logs/heartbeat_watch.log`.

If the checkout or the image is older, the deploy has not happened yet. Stop and report it; do not deploy from this task.

- [ ] **Step 2: Dry-run every verdict on the VM, against a throwaway root**

Write `<scratchpad>/v184_dryruns.sh`:

```bash
set -u
R=/tmp/v184-dry
W=/opt/swing-bot/scripts/ops/heartbeat_watch.sh
rm -rf "$R"
mkdir -p "$R/logs"
run() {
  echo "== $*"
  HEARTBEAT_WATCH_ROOT="$R" bash "$W" --dry-run "$@"
  echo "rc=$?"
}
run --monitor-age 30
run --monitor-age 301
run --monitor-age absent
run --monitor-age ''
run --monitor-age 30 --market-open true --positions 3 --priced-age 100000
run --monitor-age 30 --market-open true --positions null --priced-age 100000
run --monitor-age 30 --market-open false --positions 3 --priced-age 100000
run --monitor-age 301 --market-open true --positions 3 --priced-age 100000
run --age 30
run --age 30 --monitor-age 30
echo "== bare --dry-run"
HEARTBEAT_WATCH_ROOT="$R" bash "$W" --dry-run 2>/dev/null
echo "rc=$?"
ls "$R/logs"
rm -rf "$R"
```

Run it:

```bash
cd "$MAIN" && bash scripts/ops/ssh-hetzner.sh "bash -s" < "<scratchpad>/v184_dryruns.sh"
```

Expected, in order (each line also carries its `<iso>` prefix and ends `dry_run=1`, and each `rc=0`):

| flags | expected line |
|---|---|
| `--monitor-age 30` | `monitor verdict=ok … action=none` |
| `--monitor-age 301` | `monitor verdict=monitor_stale … action=alert` |
| `--monitor-age absent` | `monitor verdict=not_deployed tick_age_s=absent … action=none` |
| `--monitor-age ''` | `monitor verdict=unreadable tick_age_s=none … action=alert` |
| open, 3 positions, priced 100000 s ago | `monitor verdict=stops_unchecked … action=alert` |
| open, `null` positions | `monitor verdict=stops_unchecked … positions=null …` |
| closed market | `monitor verdict=ok …` |
| stale and unchecked | `monitor verdict=monitor_stale …` (stale wins) |
| `--age 30` | one line only: `verdict=ok age_s=30 threshold_s=900 previous=none action=none dry_run=1` |
| `--age 30 --monitor-age 30` | that same heartbeat line, then one `monitor verdict=ok` line |
| bare `--dry-run` | `rc=2` |

`ls "$R/logs"` lists only `heartbeat_watch.log`: no state file is written by a dry run. Any mismatch is a bug in V184-9. Stop and report it with the offending line; do not patch the script on the VM (`mirror-prod`).

- [ ] **Step 3: Read the cron's own runs: one real `monitor verdict=ok` with a fresh tick**

Wait until at least 15 minutes after the deploy finished (three cron runs), then:

```bash
cd "$MAIN"
bash scripts/ops/ssh-hetzner.sh "grep -F ' monitor verdict=' /opt/swing-bot/logs/heartbeat_watch.log | tail -n 6"
bash scripts/ops/ssh-hetzner.sh "grep -v -F ' monitor ' /opt/swing-bot/logs/heartbeat_watch.log | tail -n 3"
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/monitor_watch.state /opt/swing-bot/logs/heartbeat_watch.state"
```

Expected:
- every monitor line reads `monitor verdict=ok`, none reads `verdict=error`, and at least one carries `tick_age_s=` below `120`. All are below `300`, because the stamp writes at most every 120 s and the cron reads every 5 minutes;
- the heartbeat lines keep the pre-v184 format (`<iso> verdict=ok age_s=… threshold_s=… previous=… action=none`);
- both state files read `ok`.

If a monitor line is `not_deployed`, the bot has not stamped yet: check Step 1's image, wait one more cron run, then report. If it is `monitor_stale` or `stops_unchecked`, that is a live incident or a stamp bug. Record the line, read Step 4, and report to the controller before going on. Never clear the key or edit state files to make the check pass.

- [ ] **Step 4: Read the `monitor` key itself**

```bash
cd "$MAIN" && bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -tA -c \"SELECT now(), jsonb_pretty(doc->'monitor'), doc->>'timestamp' FROM bot_heartbeat WHERE key = 'bot'\""
```

Expected: every field in index § Monitor stamp is present: `started_at`, `tick_at`, `outcome`, `positions` (an array), `unquoted`, `unquoted_count`, `fetch_failed`, `check_errors`, `priced_at` and `market_open`. Also:
- `outcome` is `ok`;
- `started_at` is near the deploy time;
- `doc->>'timestamp'` is still the scan loop's own and still advances. Re-read it after 5 minutes if needed: the monitor merge never writes `timestamp`.

If the read falls in the NYSE regular session, also record:
- `market_open` (`true`);
- the number of `positions`;
- `unquoted_count` and the names;
- `priced_at`'s age against `STOPS_UNCHECKED_S`.

This is the per-tick recheck that V184-1 named, if V184-1 recorded case 4 (insufficient). Outside the session, `market_open` must be `false`. Note when the next session read is due, and record that read in the same results doc before Step 8.

- [ ] **Step 5: Write the results doc**

In the main tree, create `docs/superpowers/results/<run-date>-v184-post-deploy-verification.md`:

```markdown
# v184 — post-deploy verification on production

**Plan:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](../plans/2026-10-21-v184-stop-monitor-liveness_0-index.md) · Task V184-12
**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md) § Rollout
**Run:** <run-date>, read-only on production (Hetzner VM), bot <version>, checkout <sha>

## 1. Deployed
<Step 1 output, three lines>

## 2. Dry runs, one per verdict
<Step 2 output, verbatim>

## 3. The cron's own runs
<Step 3 output; the freshest tick_age_s; both state files>

## 4. The monitor key
<Step 4 output; in-session figures if the read was in session>

## 5. Test post
<filled in after Step 6: sent or not, and the log line>

## Verdict
<three to five lines: each Rollout item passed or not; anything that needs a
follow-up, e.g. a threshold recheck from V184-1 case 4>
```

Do not commit yet: Step 6 completes section 5.

- [ ] **Step 6: The one `--test` post — controller only, after the partner says yes**

**The implementer stops here and hands back to the controller,** reporting Steps 1-5. The post is outward-facing (it reaches the ops Discord channel). The controller asks the partner with `AskUserQuestion`, one question, recommended option first:
- *Send the test post now (recommended)*;
- *Skip it*.

Only on a yes, the controller runs:

```bash
cd "$MAIN" && bash scripts/ops/ssh-hetzner.sh "bash /opt/swing-bot/scripts/ops/heartbeat_watch.sh --test; echo rc=\$?"
```

Expected: `<iso> test delivered=yes` and `rc=0`, and the partner sees `[swingbot ops] heartbeat_watch TEST post from …` in the ops channel. (`rc=1` with `delivered=no` means `OPS_ALERT_WEBHOOK_URL` is unset on the VM: report it and do not set it from this task.) On a skip, write "not sent (partner's choice, <date>)" in section 5.

- [ ] **Step 7: Commit the results doc on `main`**

```bash
cd "$MAIN"
git add docs/superpowers/results/*-v184-post-deploy-verification.md
git commit -m "results(v184): post-deploy verification -- every watch verdict dry-runs, monitor stamp live

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Run `/close-out`**

Invoke the `close-out` skill (standing permission, CLAUDE.md). Notes for its steps:
- **Step 2 (panel):** the spec carries `**Panel:** staff-engineer, quant-engineer`. Run `/panel` with those two roles over `<merge-sha>^1...$BR`, with both v184 results docs. An unresolved `BLOCKING` finding stops the close-out.
- **Steps 3-4 (bump):** V184-11 already made the bump, and its two commits are on `main`. Confirm that `VERSION.json` on `main` shows the bumped `bot` and that `swingbot/admin/version_history.json` was regenerated after it. Do not bump again.
- **Step 5 (prediction):** check `Bump: bot patch` and `Edge: none (integrity)` against what shipped. If the work turned out otherwise, amend the index header with one clause saying why.
- **Step 6 (move):** `git mv` the four plan files into `docs/superpowers/plans/implemented/` and the spec into `docs/superpowers/specs/implemented/`. Nothing else builds from that spec. The watchdog and outside-the-VM alerting in its "Out of scope" are follow-ups without a spec.
- **Step 7 (worktree):** confirm `git rev-list --count main..$BR` is `0`. The branch name contains no `backup` and does not start with `stable-`. Then remove the worktree and delete the branch.
