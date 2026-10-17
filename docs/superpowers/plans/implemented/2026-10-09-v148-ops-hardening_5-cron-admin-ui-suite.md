# v148 Ops hardening, part 5: VM heartbeat cron, `/system/health`, frontend health store (OH19–OH21)

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH20:" -A 320 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ O3 "Out-of-process cron", § "Admin surface", § Testing, § Parallelisation "After merge and deploy")
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md`. Its Global Constraints, Parallelisation and task ledger are binding here and are not repeated.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`. Frontend runs use `npm --prefix $WT/frontend test -- --include <spec>`.

Order inside this part: OH19 needs only OH2 (same doc) and OH5 (the webhook key), so it can run beside Phase C/D. OH20 needs OH5, OH6, OH8 and OH16. OH20 → OH21 → OH22 run strictly in sequence, because each one consumes the previous one's contract. **OH22–OH24 are in part 5b** (`2026-10-09-v148-ops-hardening_5b-panels-suite-rollout.md`), split only to keep each file under 1500 lines. OH23 is the last repo task. OH24 runs on production only, after the branch is merged and deployed.

Contracts consumed from earlier parts (ledger, final):
- OH5: `config.PROVIDER_FALLBACK_ALERT_PCT` and `config.EMPTY_SYMBOLS_ALERT_PCT` are ints (defaults 20 and 5). `OPS_ALERT_WEBHOOK_URL` is in `.env.example`, and no process reads it. Only OH19's cron reads it from `.env`.
- OH6: `from swingbot.core.infra import swallowed as swallowed_mod` gives `snapshot() -> {tag: {"count", "first_at", "last_at", "last_error"}}`, `reset()`, and `swallowed(log, tag, exc, msg="", *args, level=..., exc_info=...)`.
- OH8: the heartbeat doc carries `swallowed: {"since": <bot STARTED_AT iso>, "counts": <snapshot>}`, rewritten every tick by `runstate._write_heartbeat`. `runstate._read_heartbeat()` returns the doc fields, or `{}` (counted under `runstate.read_heartbeat`).
- OH16: every scan row in `data/scan_telemetry.jsonl` written from v148 on carries `provider_fallback_rate: float | None`, `empty_symbols: int`, `empty_rate: float | None` and `stale_symbols: int | None`. Older rows do not have these keys.
- OH15: the repo-wide untagged `except Exception` count is pinned. Nothing in this part adds an `except Exception`.

# Phase E — VM cron, health endpoint, frontend panels, full suites, production rollout

### Task OH19: Heartbeat cron on the VM

**Model:** sonnet — two new bash scripts with a small state machine plus a stubbed-bash test harness; it runs on production and must not page twice, so not haiku.

**Files:**
- Create: `scripts/ops/heartbeat_watch.sh`
- Create: `scripts/ops/install_heartbeat_watch_cron.sh`
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (a "Liveness" table right after the Backups table; OH2 has already edited § Rolling back and § Point-in-time rollback, so this is a separate hunk)
- Create: `tests/scripts/test_heartbeat_watch.py`

**Why:** spec O3 "Out-of-process cron". The in-bot watchdog (OH18) cannot see a dead process or a blocked event loop. This cron runs outside the bot every 5 minutes, 24/7. It reads `doc->>'timestamp'`, which only the bot's `_write_heartbeat` writes, at the start of every tick, whatever the session. It does not read the promoted `ts` column, because admin-side writes such as an unpause also bump `ts`. The heartbeat is stale when it is older than `max(900 s, 3 × SCAN_INTERVAL_MINUTES × 60)`. A failed query is an incident of its own (`unreadable`). The script posts to `OPS_ALERT_WEBHOOK_URL` once per incident and once on recovery. It appends one verdict line per run to `logs/heartbeat_watch.log`, capped at 2000 lines (about a week at 288 runs a day). Owner: the partner (ops). The cron is permanent and is replaced only by a monitor outside the VM, under its own spec.

Contract (ledger, final): CLI `heartbeat_watch.sh [--dry-run --age <s>] [--test]`; state `logs/heartbeat_watch.state` (one word: `ok`, `stale` or `unreadable`); log `logs/heartbeat_watch.log`; env override `HEARTBEAT_WATCH_ROOT` (default `/opt/swing-bot`). The installer honours `BASE` (default `/opt/swing-bot`), as `install_pitr_crons.sh` does, so the test can point it at a tmp dir.

Decisions fixed here (inside the spec, not new scope):
- **State changes only when a post is delivered**, or when the verdict is `ok` with nothing to post. If no webhook is configured (spec: "logs and exits 0") or curl fails, the state is left alone. The incident then posts on the first run after a URL is set or the network comes back, so it is never silently marked "already alerted".
- `--dry-run --age <s>` (spec Testing) takes the age instead of querying. It never runs psql or curl and never writes the state. It still appends its verdict line to the log and applies the cap, which is what the cap test drives. `--age ''` means "unreadable".
- `--test` posts one fixed test message and exits 0 when it was delivered. With no URL, or a failed post, it exits 1, because OH24 uses it to prove the channel is wired.
- `.env` is read with `grep '^KEY=' | cut -d= -f2-`, never sourced. A non-integer `SCAN_INTERVAL_MINUTES` falls back to 5. The threshold floor of 15 minutes still holds, so a fractional interval can only make the check later, never noisier.
- Messages contain no `"` or `\`, so the JSON body `{"content":"..."}` needs no escaping. The webhook URL is never echoed, and curl's `-sS` error text does not include it.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scripts/test_heartbeat_watch.py`:

```python
"""v148 O3: the VM's out-of-process heartbeat watch.

The script runs only on the VM, as root, from cron. Here it runs under bash
with `docker` and `curl` replaced by exported bash functions (a stub file is
not executable on Windows -- the test_pitr_crons.py pattern), so the whole
once-per-incident state machine is exercised without Postgres, Docker or a
webhook. Skipped where no bash can see both the repo and the tmp dir.
"""
import os
import pathlib
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

# `docker` prints $STUB/age (or fails when it is absent); `curl` records its
# arguments and returns $STUB/curl_rc.
_STUBS = (
    'docker() { [ -f "$STUB/age" ] || return 1; cat "$STUB/age"; }; '
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
```

- [ ] **Step 2: Run it and watch it fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch.py
```

Expected: the four shape tests fail with `FileNotFoundError`. Every behaviour test skips ("no bash that can see …"), because `_working_bash` tests that `SCRIPT` exists.

- [ ] **Step 3: Write the watch script**

Create `$WT/scripts/ops/heartbeat_watch.sh` with LF endings:

```bash
#!/usr/bin/env bash
# v148 O3: out-of-process liveness check for the bot. Runs from cron on the
# Hetzner VM every 5 minutes, 24/7 (installed by install_heartbeat_watch_cron.sh).
#
# Reads doc->>'timestamp' from the singleton bot_heartbeat row. Only the bot's
# runstate._write_heartbeat writes it, at the start of every tick, in session
# or not; admin-side writes (an unpause) bump the `ts` column, never this
# field. Stale when older than max(15 min, 3 x SCAN_INTERVAL_MINUTES); a failed
# query is an incident of its own ("unreadable"). Posts to
# OPS_ALERT_WEBHOOK_URL once per incident and once on recovery; the last
# delivered verdict lives in logs/heartbeat_watch.state; every run appends one
# verdict line to logs/heartbeat_watch.log, which keeps its last 2000 lines.
#
# Owner: the partner (ops). Permanent: removed only when a monitor outside the
# VM replaces it, by its own spec. It dies with the VM.
#
#   heartbeat_watch.sh                       # the cron run
#   heartbeat_watch.sh --dry-run --age 42    # verdict for a given age (s): no psql,
#                                            # no curl, no state write
#   heartbeat_watch.sh --dry-run --age ''    # verdict for an unreadable heartbeat
#   heartbeat_watch.sh --test                # force one test post (exit 1 if not delivered)
#
# .env is read with grep | cut, never sourced: a `$` in any value would be
# expanded (docs/deploy/DEPLOY_HETZNER.md).
set -euo pipefail

ROOT="${HEARTBEAT_WATCH_ROOT:-/opt/swing-bot}"
LOG="$ROOT/logs/heartbeat_watch.log"
STATE_FILE="$ROOT/logs/heartbeat_watch.state"
MAX_LOG_LINES=2000
MIN_STALE_S=900
SQL="SELECT floor(extract(epoch FROM now() - (doc->>'timestamp')::timestamptz))::bigint FROM bot_heartbeat WHERE key = 'bot'"

DRY_RUN=0
TEST_POST=0
AGE_GIVEN=0
AGE_ARG=""

usage() {
  echo "usage: heartbeat_watch.sh [--dry-run --age <seconds>] [--test]" >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --age) [ "$#" -ge 2 ] || usage; AGE_ARG="$2"; AGE_GIVEN=1; shift ;;
    --test) TEST_POST=1 ;;
    *) usage ;;
  esac
  shift
done
[ "$DRY_RUN" = "$AGE_GIVEN" ] || usage

env_value() {   # KEY -> its value in .env, or nothing
  { grep "^$1=" "$ROOT/.env" 2>/dev/null || true; } | tail -n 1 | cut -d= -f2- | tr -d '\r'
}

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

record() {      # print one line, append it to the log, keep the last 2000 lines
  echo "$1"
  echo "$1" >> "$LOG"
  tail -n "$MAX_LOG_LINES" "$LOG" > "$LOG.tmp"
  mv "$LOG.tmp" "$LOG"
}

stale_after() { # seconds: max(900, 3 x SCAN_INTERVAL_MINUTES x 60)
  local minutes seconds
  minutes="$(env_value SCAN_INTERVAL_MINUTES)"
  case "$minutes" in ''|*[!0-9]*) minutes=5 ;; esac
  seconds=$((minutes * 180))
  [ "$seconds" -ge "$MIN_STALE_S" ] || seconds="$MIN_STALE_S"
  echo "$seconds"
}

read_age() {    # seconds since the bot's last heartbeat, or nothing
  { (cd "$ROOT" && docker compose exec -T db psql -U swingbot -d swingbot -tA \
      -v ON_ERROR_STOP=1 -c "$SQL" </dev/null 2>/dev/null) || true; } | tr -d '[:space:]'
}

verdict_for() { # age threshold -> ok | stale | unreadable
  if ! [[ "$1" =~ ^-?[0-9]+$ ]]; then echo unreadable; return; fi
  if [ "$1" -gt "$2" ]; then echo stale; else echo ok; fi
}

action_for() {  # verdict previous -> alert | recover | none
  if [ "$1" != ok ] && [ "$1" != "$2" ]; then echo alert
  elif [ "$1" = ok ] && [ -n "$2" ] && [ "$2" != ok ]; then echo recover
  else echo none; fi
}

message_for() { # action verdict age threshold previous
  local host="${HOSTNAME:-the VM}"
  case "$1:$2" in
    alert:stale) echo "[swingbot ops] Heartbeat STALE on $host: the bot last wrote its heartbeat $3s ago (threshold $4s). The bot process may be dead or its event loop blocked. Check docker compose ps and docker compose logs --tail 200 bot." ;;
    alert:unreadable) echo "[swingbot ops] Heartbeat UNREADABLE on $host: cannot read the bot_heartbeat row from Postgres. Check docker compose ps (is db up?)." ;;
    *) echo "[swingbot ops] Heartbeat RECOVERED on $host: the bot wrote its heartbeat $3s ago (was $5)." ;;
  esac
}

post() {        # message -> 0 when delivered; never echoes the URL
  local url
  url="$(env_value OPS_ALERT_WEBHOOK_URL)"
  [ -n "$url" ] || return 1
  curl -fsS -m 15 -o /dev/null -H 'Content-Type: application/json' \
    -d "{\"content\":\"$1\"}" "$url"
}

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

threshold="$(stale_after)"
if [ "$DRY_RUN" = 1 ]; then age="$AGE_ARG"; else age="$(read_age)"; fi
verdict="$(verdict_for "$age" "$threshold")"
previous="$(cat "$STATE_FILE" 2>/dev/null || true)"
action="$(action_for "$verdict" "$previous")"
line="$(now_iso) verdict=$verdict age_s=${age:-none} threshold_s=$threshold previous=${previous:-none} action=$action"

if [ "$DRY_RUN" = 1 ]; then
  record "$line dry_run=1"
  exit 0
fi
if [ "$action" = none ]; then
  echo "$verdict" > "$STATE_FILE"
  record "$line"
  exit 0
fi
if [ -z "$(env_value OPS_ALERT_WEBHOOK_URL)" ]; then
  # State untouched: the incident posts on the first run after a URL is set.
  record "$line delivered=no-webhook"
  exit 0
fi
if post "$(message_for "$action" "$verdict" "$age" "$threshold" "$previous")"; then
  echo "$verdict" > "$STATE_FILE"
  record "$line delivered=yes"
else
  # State untouched: retried on the next run.
  record "$line delivered=failed"
fi
exit 0
```

`[ "$DRY_RUN" = "$AGE_GIVEN" ] || usage` covers both mistakes: `--dry-run` without `--age`, and `--age` without `--dry-run`. `--test` is checked before anything that reads the age.

- [ ] **Step 4: Write the installer**

Create `$WT/scripts/ops/install_heartbeat_watch_cron.sh` with LF endings, using the marker-line pattern of `install_intraday_coverage_cron.sh`:

```bash
#!/usr/bin/env bash
# Installs (idempotently) the v148 heartbeat watch on the Hetzner VM: every
# 5 minutes, 24/7, scripts/ops/heartbeat_watch.sh checks the bot's heartbeat
# row and posts to OPS_ALERT_WEBHOOK_URL once per incident and on recovery.
# The script writes its own verdict line to logs/heartbeat_watch.log; cron
# discards stdout and appends stderr to the same log.
#
# Permanent (not one-shot). Owner: the partner (ops). Run this ON the VM as
# root, from a dev machine:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_heartbeat_watch_cron.sh
#
# Safe to re-run: it replaces any prior line this script installed rather
# than appending a duplicate. BASE overrides /opt/swing-bot (tests only).
set -euo pipefail

BASE="${BASE:-/opt/swing-bot}"
MARKER='# v148 heartbeat watch (installed by install_heartbeat_watch_cron.sh)'
CRON_LINE="*/5 * * * * /usr/bin/env bash $BASE/scripts/ops/heartbeat_watch.sh >/dev/null 2>> $BASE/logs/heartbeat_watch.log"

mkdir -p "$BASE/logs"
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "heartbeat_watch.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
```

The marker contains `install_heartbeat_watch_cron.sh` but not the substring `heartbeat_watch.sh`, so each `grep -vF` removes only its own line.

- [ ] **Step 5: Add the cron row to `DEPLOY_HETZNER.md`**

Use `Edit` (not `sed -i`). In `$WT/docs/deploy/DEPLOY_HETZNER.md`, directly after the Backups table's last row (the line starting `` | `0 3 * * *` | `backup_db.sh` ``) and its following blank line, insert this text, followed by one blank line:

```markdown
**Liveness (v148).** Installed by `scripts/ops/install_heartbeat_watch_cron.sh` (idempotent). It is permanent and owned by the partner (ops):

| Cron (VM time) | Script | What |
|---|---|---|
| `*/5 * * * *` | `heartbeat_watch.sh` | reads the bot's last heartbeat (`bot_heartbeat.doc->>'timestamp'`, written only by the bot). When it is stale past max(15 min, 3 × `SCAN_INTERVAL_MINUTES`), or cannot be read, the script posts once to `OPS_ALERT_WEBHOOK_URL`, and once more on recovery. One verdict line per run goes to `logs/heartbeat_watch.log` (last 2000 lines kept), and the state goes to `logs/heartbeat_watch.state` |

`bash scripts/ops/heartbeat_watch.sh --test` forces one post, to check the webhook. `--dry-run --age <s>` prints the verdict for a given age without touching Postgres, the webhook or the state. With no webhook set, it logs and exits 0 and posts the incident once a URL is set. It dies with the VM: a monitor outside the VM would need its own spec.
```

- [ ] **Step 6: Run the tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scripts/test_heartbeat_watch.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_pitr_crons.py
bash -n $WT/scripts/ops/heartbeat_watch.sh && bash -n $WT/scripts/ops/install_heartbeat_watch_cron.sh && echo "syntax ok"
grep -c $'\r' $WT/scripts/ops/heartbeat_watch.sh $WT/scripts/ops/install_heartbeat_watch_cron.sh || true
```

Expected: both files `0 failed`, `0 xfailed`. On this Linux dev machine no test skips. `syntax ok`, and the CR count is `0` for both files. If a behaviour test fails on quoting, run the exact `bash -c` command from `_run` by hand with `set -x` added to the script copy in `/tmp/claude-oh19/`. Never edit the test to fit.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add --chmod=+x scripts/ops/heartbeat_watch.sh scripts/ops/install_heartbeat_watch_cron.sh
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add docs/deploy/DEPLOY_HETZNER.md tests/scripts/test_heartbeat_watch.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH19: out-of-process heartbeat watch cron for the VM"
```

### Task OH20: `GET /api/v1/system/health`

**Model:** sonnet — one read-only endpoint that joins three already-built sources (telemetry rows, heartbeat doc, in-memory counter) under a typed contract test; no new logic beyond shaping and sorting.

**Files:**
- Create: `swingbot/admin/api_v1/ops_health.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (the deferred import tuple in `register()`, lines 208-210)
- Create: `tests/admin/test_api_v1_ops_health.py`

**Why:** spec § "Admin surface". The System → Scan tab's two new panels (OH22) read one payload. `providers` holds the last 20 scan rows of `scan_telemetry.jsonl` (via `telemetry.recent_scan_telemetry`, which already skips deploy markers), newest first, cut down to `at`, `tickers` and OH16's four fields. A row written before v148 has none of the four. It is passed through as `null`, never back-filled (`schema-evolution.md`: no read-time upcasting). `swallowed` merges the bot's per-tag counts, read from the heartbeat doc's `swallowed` key (OH8, rewritten every tick), with the admin's own in-memory `swallowed_mod.snapshot()`. Reading the admin's counts from memory is valid because the admin runs one worker (O1). `thresholds` echoes the two hot-reloadable alert levels (OH5), so the panel marks a breach with the same numbers `ops_watch` alerts on.

Contract (ledger, final): `{providers: [{at, tickers, provider_fallback_rate, stale_symbols, empty_symbols, empty_rate}] (newest first, ≤ 20), thresholds: {fallback_pct, empty_pct}, swallowed: [{process: "bot"|"admin", tag, count, first_at, last_at, last_error}] (count desc), bot_counts_since: str | null}`. Ties in `swallowed` sort by `process`, then `tag`, so the order is deterministic.

Endpoint modules are imported only inside `register()` (circular-import guard, `api_v1/__init__.py` comment above the tuple), so `ops_health` joins that tuple and nothing else. The module adds no `except Exception`, so OH15's `BASELINE` does not move. `runstate._read_heartbeat` already swallows and counts its own failure under `runstate.read_heartbeat`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/admin/test_api_v1_ops_health.py`:

```python
"""v148: GET /api/v1/system/health -- provider rows and swallowed-error counts.

The System -> Scan panels render exactly this payload, so the shape is pinned
with types (api_v1_contract.assert_shape), not key presence: a rate that
turned into a string would render as "NaN%" without failing anything else.
"""
import json
import logging

import pytest

from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR, NUMBER,
                                         assert_error, assert_shape)

_LOGIN = {"username": "admin", "password": "admin"}
_PROVIDER_ROW = {
    "at": str,
    "tickers": NUMBER,
    "provider_fallback_rate": NULLABLE_NUMBER,
    "stale_symbols": NULLABLE_NUMBER,
    "empty_symbols": NULLABLE_NUMBER,
    "empty_rate": NULLABLE_NUMBER,
}
_SWALLOWED_ROW = {
    "process": str,
    "tag": str,
    "count": NUMBER,
    "first_at": NULLABLE_STR,
    "last_at": NULLABLE_STR,
    "last_error": NULLABLE_STR,
}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def _clean_counts():
    """The admin's counter is module-level and this test process is the
    admin: clear it so another test's swallowed errors never show up here."""
    from swingbot.core.infra import swallowed as swallowed_mod
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


@pytest.fixture
def telemetry_rows(tmp_path, monkeypatch):
    from swingbot.core.scanning import telemetry
    path = tmp_path / "scan_telemetry.jsonl"
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(path))

    def write(*rows):
        with path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
    return write


def _scan_row(minute, **fields):
    return {"at": f"2026-10-09T14:{minute:02d}:00+00:00", "duration_s": 60.0,
            "tickers": 150, **fields}


def _health(client):
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _beat(**fields):
    from swingbot.core.db.repositories.heartbeat import heartbeat_repo
    heartbeat_repo().beat(fields)


def test_requires_auth(client):
    assert_error(client.get("/api/v1/system/health"), "auth", 401)


def test_nothing_recorded_yet_is_empty_not_an_error(logged_in, telemetry_rows):
    body = _health(logged_in)
    assert_shape(body, {"providers": list, "thresholds": dict, "swallowed": list,
                        "bot_counts_since": NULLABLE_STR})
    assert_shape(body["thresholds"], {"fallback_pct": NUMBER, "empty_pct": NUMBER},
                 where="thresholds")
    assert body["providers"] == []
    assert body["swallowed"] == []
    assert body["bot_counts_since"] is None


def test_provider_rows_are_newest_first_and_capped_at_20(logged_in, telemetry_rows):
    telemetry_rows(*[_scan_row(m, provider_fallback_rate=m / 100, stale_symbols=0,
                               empty_symbols=m, empty_rate=m / 150) for m in range(25)])

    rows = _health(logged_in)["providers"]

    assert len(rows) == 20
    assert rows[0]["at"] == "2026-10-09T14:24:00+00:00"
    assert rows[-1]["at"] == "2026-10-09T14:05:00+00:00"
    assert rows[0]["empty_symbols"] == 24
    for row in rows:
        assert_shape(row, _PROVIDER_ROW, where="provider row")


def test_a_pre_v148_row_reads_as_null_and_deploy_markers_are_skipped(logged_in, telemetry_rows):
    telemetry_rows(
        _scan_row(1),                                          # pre-v148: no provider keys
        {"type": "deploy", "at": "2026-10-09T14:02:00+00:00"},  # not a scan row
        _scan_row(3, provider_fallback_rate=None, stale_symbols=None,
                  empty_symbols=0, empty_rate=0.0),
    )

    rows = _health(logged_in)["providers"]

    assert [r["at"] for r in rows] == ["2026-10-09T14:03:00+00:00",
                                       "2026-10-09T14:01:00+00:00"]
    assert rows[1] == {"at": "2026-10-09T14:01:00+00:00", "tickers": 150,
                       "provider_fallback_rate": None, "stale_symbols": None,
                       "empty_symbols": None, "empty_rate": None}
    assert rows[0]["empty_symbols"] == 0 and rows[0]["provider_fallback_rate"] is None


def test_thresholds_follow_the_live_config(logged_in, telemetry_rows, monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "PROVIDER_FALLBACK_ALERT_PCT", 35)
    monkeypatch.setattr(config, "EMPTY_SYMBOLS_ALERT_PCT", 8)

    assert _health(logged_in)["thresholds"] == {"fallback_pct": 35, "empty_pct": 8}


def test_bot_counts_come_from_the_heartbeat_and_admin_counts_from_memory(
        logged_in, telemetry_rows):
    from swingbot.core.infra import swallowed as swallowed_mod
    _beat(timestamp="2026-10-10T12:00:00+00:00", swallowed={
        "since": "2026-10-10T06:00:00+00:00",
        "counts": {
            "scan.run_bounded": {"count": 7, "first_at": "2026-10-10T06:05:00+00:00",
                                 "last_at": "2026-10-10T11:55:00+00:00",
                                 "last_error": "TimeoutError: cold-fetch chunk 3"},
            "marketdata.price_batch": {"count": 2, "first_at": "2026-10-10T07:00:00+00:00",
                                       "last_at": "2026-10-10T09:00:00+00:00",
                                       "last_error": "KeyError: 'AAPL'"},
        },
    })
    swallowed_mod.swallowed(logging.getLogger("tests.ops_health"), "ops.test_admin_site",
                            ValueError("boom"), "test site failed")

    body = _health(logged_in)

    assert body["bot_counts_since"] == "2026-10-10T06:00:00+00:00"
    ours = {"scan.run_bounded", "marketdata.price_batch", "ops.test_admin_site"}
    got = [(r["process"], r["tag"], r["count"]) for r in body["swallowed"] if r["tag"] in ours]
    assert got == [("bot", "scan.run_bounded", 7),
                   ("bot", "marketdata.price_batch", 2),
                   ("admin", "ops.test_admin_site", 1)]
    for row in body["swallowed"]:
        assert_shape(row, _SWALLOWED_ROW, where="swallowed row")
    admin = next(r for r in body["swallowed"] if r["tag"] == "ops.test_admin_site")
    assert admin["last_error"] == "ValueError: boom"
    counts = [r["count"] for r in body["swallowed"]]
    assert counts == sorted(counts, reverse=True)


def test_a_garbled_heartbeat_block_reads_as_no_bot_rows(logged_in, telemetry_rows):
    _beat(timestamp="2026-10-10T12:00:00+00:00", swallowed="garbled")

    body = _health(logged_in)

    assert [r for r in body["swallowed"] if r["process"] == "bot"] == []
    assert body["bot_counts_since"] is None
```

- [ ] **Step 2: Run it and watch it fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/admin/test_api_v1_ops_health.py
```

Expected: every test fails with HTTP 404 instead of 401 or 200, because an unrouted `/api/v1` path answers a JSON 404 before any auth check. If the tests skip with a "db-test" message, start the test database first (`tests/conftest.py::_store_database` prints the command).

- [ ] **Step 3: Write the endpoint**

First confirm that the endpoint name is free: `git -C $WT grep -n "def get_system_health" -- swingbot` prints nothing.

Create `$WT/swingbot/admin/api_v1/ops_health.py`:

```python
"""GET /api/v1/system/health -- v148: provider degradation and swallowed errors.

Two panels on System -> Scan read this one payload:

* ``providers`` -- the last 20 scan rows of ``scan_telemetry.jsonl``, newest
  first, cut down to ``at``, ``tickers`` and the four v148 provider fields.
  A row written before v148 has none of the four; it is passed through as
  ``null`` (rendered "—"), never back-filled -- no read-time upcasting
  (docs/claude/schema-evolution.md).
* ``swallowed`` -- per-tag counts of errors caught and carried on from. The
  bot's come from the ``swallowed`` key it rewrites on the heartbeat row every
  tick; the admin's are this process's own memory, which is the whole admin
  because it runs one worker (v148 O1). Both start at zero when their process
  starts; ``bot_counts_since`` says when the bot's did.

``thresholds`` echoes the two hot-reloadable alert levels, so the provider
panel marks a breach with the same numbers ``ops_watch`` alerts on.
"""
from __future__ import annotations

from flask import jsonify

from swingbot import config
from swingbot.core.infra import swallowed as swallowed_mod

from . import api_v1
from .auth import require_auth

_WINDOW = 20
_PROVIDER_KEYS = ("at", "tickers", "provider_fallback_rate", "stale_symbols",
                  "empty_symbols", "empty_rate")


def _provider_rows() -> list[dict]:
    """Newest first; a key the row never had reads as None."""
    from swingbot.core.scanning import telemetry
    rows = telemetry.recent_scan_telemetry(_WINDOW)
    return [{key: row.get(key) for key in _PROVIDER_KEYS} for row in reversed(rows)]


def _swallowed_rows(process: str, counts) -> list[dict]:
    if not isinstance(counts, dict):
        return []
    return [
        {"process": process, "tag": str(tag), "count": int(entry.get("count") or 0),
         "first_at": entry.get("first_at"), "last_at": entry.get("last_at"),
         "last_error": entry.get("last_error")}
        for tag, entry in counts.items() if isinstance(entry, dict)
    ]


def _bot_block() -> dict:
    """The heartbeat's ``swallowed`` block, or {} when absent or malformed."""
    from swingbot.commands.scanning import runstate
    block = runstate._read_heartbeat().get("swallowed")
    return block if isinstance(block, dict) else {}


@api_v1.route("/system/health", methods=["GET"])
@require_auth
def get_system_health():
    bot = _bot_block()
    rows = (_swallowed_rows("bot", bot.get("counts"))
            + _swallowed_rows("admin", swallowed_mod.snapshot()))
    rows.sort(key=lambda r: (-r["count"], r["process"], r["tag"]))
    since = bot.get("since")
    return jsonify({
        "providers": _provider_rows(),
        "thresholds": {"fallback_pct": config.PROVIDER_FALLBACK_ALERT_PCT,
                       "empty_pct": config.EMPTY_SYMBOLS_ALERT_PCT},
        "swallowed": rows,
        "bot_counts_since": since if isinstance(since, str) else None,
    })
```

`config.PROVIDER_FALLBACK_ALERT_PCT` is read at request time, never at import, so a SIGHUP reload shows up on the next request.

- [ ] **Step 4: Register the module**

Use `Edit` on `$WT/swingbot/admin/api_v1/__init__.py`: add `ops_health` to the deferred `from . import (...)` tuple in `register()`, in alphabetical position, keeping every name other plans added (v150 adds `reports` and `research`). Re-read the tuple first; never paste a literal over it. On today's tuple:

```python
    from . import (analytics, calendar, dashboard, jobs, market,  # noqa: F401
                   risk, session, system, trade_commands, trades,
                   versions, watchlist)  # (register routes)
```

becomes:

```python
    from . import (analytics, calendar, dashboard, jobs, market,  # noqa: F401
                   ops_health, risk, session, system, trade_commands,
                   trades, versions, watchlist)  # (register routes)
```

- [ ] **Step 5: Run the tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_ops_health.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. The ratchet stays green because `ops_health.py` has no `except` at all. If `test_bot_counts_come_from_the_heartbeat…` shows an extra admin row, some admin code path swallowed an error during the request. The test filters to its own tags on purpose. Report that tag to the controller, because it is a real swallowed error in the admin.

- [ ] **Step 6: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/admin/api_v1/ops_health.py $WT/swingbot/admin/api_v1/__init__.py
```

Expected: radon prints nothing (every function below C).

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/admin/api_v1/ops_health.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_v1_ops_health.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH20: GET /api/v1/system/health -- provider rows and swallowed counts"
```

### Task OH21: Frontend health types, client and store

**Model:** sonnet — typed models, one client method and a store change that alters what an existing resolver fetches; existing specs' `boot()` helpers must learn the new request or their `backend.verify()` calls break.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (after `ScanCommandResult`, line 1030-1034)
- Modify: `frontend/src/app/api/api-client.ts` (models import list; a method after `scanStatus()`, line 430)
- Modify: `frontend/src/app/stores/system.store.ts` (rxjs and models imports, `SystemSlice`, initial state, `resolveScan` at line 469, the returned methods)
- Modify: `frontend/src/app/stores/system.store.spec.ts` (fixture `HEALTH`, `boot()` and `bootWithLog()`, four new tests)

**Why:** spec § "Admin surface": "Data via `system.store.ts`, refreshed on the existing `scan` and `bot` SSE events." The System route already refreshes the Scan tab on `scan` and `bot` events (`system.routes.ts:16`) by calling `resolveTab('scan')`, which is `resolveScan()`. Making `resolveScan()` fetch `/system/health` beside `/system/scan` therefore wires both refresh events without touching routing or the event stream. The two requests are independent. A failed health fetch sets `healthError` and leaves the scan status and the route intact. `routeRequest` already turns a non-auth error into a completed `undefined`, so `forkJoin` still completes.

Contract (ledger, final): TS `ProviderHealthRow`, `SwallowedRow`, `SystemHealth`; `ApiClient.systemHealth(): Observable<SystemHealth>`; `SystemStore` state `health: SystemHealth | null`, `healthError: string | null`; method `resolveHealth(): Observable<void>`; `resolveScan()` also resolves health.

**Existing specs that change and why:** `system.store.spec.ts`'s `boot()` and `bootWithLog()` call `store.resolveScan()`, and several tests end in `backend.verify()` (lines 224, 517, 622, 682, 699). After this change each of them leaves an open `/api/v1/system/health` request unless the helper flushes it. Both helpers gain one `expectOne('/api/v1/system/health').flush(HEALTH)` line. No assertion changes.

- [ ] **Step 1: Write the failing tests**

In `$WT/frontend/src/app/stores/system.store.spec.ts`:

(a) Directly after the `const SCAN = { … };` block (ends line 114), add:

```ts
const HEALTH = {
  providers: [
    {
      at: '2026-10-09T14:05:00+00:00',
      tickers: 150,
      provider_fallback_rate: 0.04,
      stale_symbols: 0,
      empty_symbols: 2,
      empty_rate: 0.0133,
    },
  ],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  swallowed: [
    {
      process: 'bot' as const,
      tag: 'scan.run_bounded',
      count: 3,
      first_at: '2026-10-09T13:00:00+00:00',
      last_at: '2026-10-09T14:00:00+00:00',
      last_error: 'TimeoutError: cold-fetch chunk 2',
    },
  ],
  bot_counts_since: '2026-10-09T06:00:00+00:00',
};
```

(b) The exact statement `backend.expectOne('/api/v1/system/scan').flush(SCAN);` occurs twice: once in `boot()` (four-space indent) and once in `bootWithLog()` (six-space indent). After each one, add this line at the same indentation, using two `Edit` calls, one per helper:

```ts
backend.expectOne('/api/v1/system/health').flush(HEALTH);
```

(c) Before the file's last line (the `});` that closes `describe('SystemStore', …)`), add:

```ts

  /* -- v148: system health ------------------------------------------------ */

  it('resolves health together with the scan status', () => {
    store.resolveScan().subscribe();
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
    backend.expectOne('/api/v1/system/health').flush(HEALTH);

    expect(store.health()).toEqual(HEALTH);
    expect(store.healthError()).toBeNull();
  });

  it('refreshes health with the scan tab, so scan and bot events update both panels', () => {
    store.resolveTab('scan').subscribe();
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
    backend.expectOne('/api/v1/system/health').flush({ ...HEALTH, swallowed: [] });

    expect(store.health()?.swallowed).toEqual([]);
    backend.expectNone('/api/v1/system/settings');
  });

  it('keeps the scan status and finishes the route when health fails', () => {
    let finished = 0;
    store.resolveScan().subscribe({ complete: () => { finished += 1; } });
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
    backend.expectOne('/api/v1/system/health').flush(
      { error: { code: 'unavailable', message: 'down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );

    expect(store.botAlive()).toBe(true);
    expect(store.health()).toBeNull();
    expect(store.healthError()).toBe('The admin is not responding.');
    expect(finished).toBe(1);
  });

  it('shows the server message for a health error that is not unavailability', () => {
    store.resolveHealth().subscribe();
    backend.expectOne('/api/v1/system/health').flush(
      { error: { code: 'invalid', message: 'bad telemetry row' } },
      { status: 400, statusText: 'Bad Request' },
    );

    expect(store.healthError()).toBe('bad telemetry row');
  });
```

- [ ] **Step 2: Run it and watch it fail**

```bash
npm --prefix /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend test -- --include src/app/stores/system.store.spec.ts
```

Expected: a compile error (`resolveHealth`, `health`, `healthError` do not exist on the store), or, once those compile, `expectOne('/api/v1/system/health')` failing with "found none".

- [ ] **Step 3: Add the types**

In `$WT/frontend/src/app/api/models.ts`, directly after the `ScanCommandResult` interface (its closing `}` and the blank line after it), insert:

```ts
/* -- system health (v148) ------------------------------------------------ */

/** One scheduled scan's provider figures, from `GET /system/health`.
 *  Rates are fractions (0.05 = 5%). The four figures are null on a row
 *  written before v148 -- render "—", never 0. */
export interface ProviderHealthRow {
  at: string;
  tickers: number;
  /** yfinance-fallback / (alpaca + yfinance-fallback), daily frames and live
   *  prices pooled; null when Alpaca was asked for nothing. */
  provider_fallback_rate: number | null;
  /** Frames whose last bar is before the previous NYSE session. Display
   *  only: no alert reads it. */
  stale_symbols: number | null;
  empty_symbols: number | null;
  empty_rate: number | null;
}

/** Errors a process caught and carried on from, per call-site tag. */
export interface SwallowedRow {
  process: 'bot' | 'admin';
  tag: string;
  count: number;
  first_at: string | null;
  last_at: string | null;
  /** `Type: message`, at most 200 characters; no traceback. */
  last_error: string | null;
}

export interface SystemHealth {
  /** Newest first, at most 20. */
  providers: ProviderHealthRow[];
  /** Percent (1-100): the levels the ops-channel alert fires above. */
  thresholds: { fallback_pct: number; empty_pct: number };
  /** Highest count first. */
  swallowed: SwallowedRow[];
  /** When the bot's counts began (its process start); null when the bot has
   *  not yet written them. */
  bot_counts_since: string | null;
}

```

- [ ] **Step 4: Add the client method**

In `$WT/frontend/src/app/api/api-client.ts`:

1. In the `import { … } from './models';` list, add `SystemHealth,` on its own line directly after `SettingsSaveResult,` (line 49).
2. Directly after the `scanStatus()` method (lines 430-432), add:

```ts

  /** v148 — provider rows and swallowed-error counts for System → Scan. */
  systemHealth(): Observable<SystemHealth> {
    return this.http.get<SystemHealth>(`${this.base}/system/health`);
  }
```

- [ ] **Step 5: Extend the store**

In `$WT/frontend/src/app/stores/system.store.ts`:

1. Replace `import { Observable, of } from 'rxjs';` with:

```ts
import { Observable, forkJoin, map, of } from 'rxjs';
```

2. In the `import { … } from '../api/models';` list, add `SystemHealth,` directly after `SettingsSaveResult,`.

3. In `interface SystemSlice`, directly after `scanMessage: string | null;`, add:

```ts
  /** v148 — provider rows and swallowed-error counts for the Scan tab's two
   *  health panels. Null until the first answer. A failed refresh keeps the
   *  last good payload and says so in `healthError`: a stale table that is
   *  labelled stale beats an empty one. */
  health: SystemHealth | null;
  healthError: string | null;
```

4. In the initial state, replace the two consecutive lines

```ts
    scanPending: null,
    scanMessage: null,
```

with

```ts
    scanPending: null,
    scanMessage: null,
    health: null,
    healthError: null,
```

5. Replace the whole `resolveScan` constant:

```ts
    const resolveScan = (): Observable<void> => routeRequest(api.scanStatus(), {
      start: () => undefined,
      next: (scan) => patchState(store, { scan, scanError: null }),
      error: (error) => patchState(store, {
        scanError: error.code === 'unavailable'
          ? 'The admin is not responding.' : error.message,
      }),
    });
```

with:

```ts
    const resolveScanStatus = (): Observable<void> => routeRequest(api.scanStatus(), {
      start: () => undefined,
      next: (scan) => patchState(store, { scan, scanError: null }),
      error: (error) => patchState(store, {
        scanError: error.code === 'unavailable'
          ? 'The admin is not responding.' : error.message,
      }),
    });

    const resolveHealth = (): Observable<void> => routeRequest(api.systemHealth(), {
      start: () => undefined,
      next: (health) => patchState(store, { health, healthError: null }),
      error: (error) => patchState(store, {
        healthError: error.code === 'unavailable'
          ? 'The admin is not responding.' : error.message,
      }),
    });

    /** v148: the Scan tab is the status AND the two health panels. One
     *  resolver for both means the route's existing `scan`/`bot` refresh
     *  updates all three; `routeRequest` turns a non-auth failure into a
     *  completed `undefined`, so a health failure never blocks the status. */
    const resolveScan = (): Observable<void> =>
      forkJoin([resolveScanStatus(), resolveHealth()]).pipe(map(() => undefined));
```

6. In the returned object, replace

```ts
      resolveScan,
      resolveTab,
```

with

```ts
      resolveScan,
      resolveHealth,
      resolveTab,
```

`runScanCommand` keeps taking `scan` from its command response, with no follow-up GET. The spec test "takes the new status from the command response, with no follow-up GET" pins that, and it passes unchanged.

- [ ] **Step 6: Run the tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
npm --prefix $WT/frontend test -- --include src/app/stores/system.store.spec.ts
npm --prefix $WT/frontend test -- --include src/app/api/api-client.spec.ts
npm --prefix $WT/frontend test -- --include src/app/workspaces/system/scan-tab.spec.ts
```

Expected: all three pass, with 0 failed. Every pre-existing `system.store.spec.ts` test still passes; the four new ones pass.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/system.store.ts frontend/src/app/stores/system.store.spec.ts
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH21: system health types, client and store refresh with the scan tab"
```

