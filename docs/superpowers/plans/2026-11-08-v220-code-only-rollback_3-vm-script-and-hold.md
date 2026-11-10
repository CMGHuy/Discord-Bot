# v220 — Code-only rollback, Part 3: VM script and CI deploy hold (V220-9, V220-9b, V220-10, V220-11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the VM script `scripts/ops/rollback_code.sh` (checks and dry run in V220-9, hold/switch/smoke/restore in V220-9b, release in V220-10) and the CI deploy hold: the `hold` job with `scripts/ops/hold_notice.sh` (V220-11). The `deploy.sh` phase-1 guard and the SessionStart `HOLD` line (V220-12) sit in [Part 3b](2026-11-08-v220-code-only-rollback_3b-hold-visibility.md), moved out to keep this file under 1500 lines. V220-11 and V220-12 depend only on the hold-file contract and can start at any time.

Facts from the code that bind every task in this part:

- **Shell scripts cannot run in CI as root on a VM.** Each script is text-pinned by a `*_shape.py`-style test, and wherever a path can run without Docker (argument parsing, the hold guards, `hold_notice.sh`) a pytest wrapper runs it under bash with `git`, `python3`, `curl` and `docker` replaced by exported bash functions (the `tests/scripts/test_heartbeat_watch.py` pattern, including its `_working_bash` helper: on Windows `bash` may be WSL's, which cannot see `C:/…`; Git for Windows' bash is tried next; skip when neither sees the paths).
- **The admin has no `/api/health`.** The route is `/api/v1/health` (`swingbot/admin/api_v1/session.py:101`, blueprint prefix `/api/v1`) and it is `@require_auth`, so an unauthenticated probe answers `401` when the app is up and routing. The smoke check accepts `200` or `401` from inside the admin container (curl is in the image, `docker-compose.yml` healthcheck); a connection refusal or any other code fails.
- **The bot heartbeat** is `bot_heartbeat.doc->>'timestamp'` (key `'bot'`), written at the start of every `_session_scan_tick`, in session or not (`scripts/ops/heartbeat_watch.sh` header; `swingbot/commands/scanning/loops.py:222`); a discord.py `tasks.loop` runs its first tick at start, so "fresh" means "written after the switch moment".
- **Pinned strings in `deploy/deploy.sh`** (`tests/scripts/test_deploy_records.py`, `test_deploy_refresher_guard_shape.py`): new text must not contain `docker compose up -d --no-build --wait`, `env_set.py SWING_BOT_IMAGE`, `>> backups/deploys.jsonl`, `rolling back past v201` or `sed -i`.
- **The planner runs as `deploy`:** `runuser -u deploy -- python3 "$WORK/rollback_plan.py" …` (Part 2 note). `$WORK` is `mktemp -d` (root, mode 700), so the script `chmod 755`s it before the `deploy` user reads the modules.


# Phase 3 — VM script and deploy hold

### Task V220-9: `rollback_code.sh`: self-copy, tools, resolve, checks, dry run

**Model:** sonnet — one shell script from a fixed step list, text-pinned

**Files:**
- Create: `scripts/ops/rollback_code.sh`
- Test: `tests/scripts/test_rollback_code_shape.py` (suite `tooling`)

**Interfaces:**
- Consumes: `rollback_plan.py resolve | candidates | check` (V220-1..V220-6b; `check` takes `--allow-writer-drift`, prints the report JSON, exits 0/2/3); `scripts/ops/env_set.py --get KEY` (existing, untouched).
- Produces (consumed by V220-9b, V220-10, V220-15, V220-18): the CLI `bash rollback_code.sh --resolve <target> | --candidates | <sha40> <image> --dry-run|--i-mean-it [--reason TEXT] [--keep-refresher] [--allow-writer-drift]`; env `ROLLBACK_APP_DIR`, `ROLLBACK_TOOLS_REF`, `ROLLBACK_DRILL`; log `logs/rollback.log`; shell globals `APP_DIR`, `TOOLS_REF`, `DRILL`, `HOLD`, `LOG`, `WORK`, `SHA`, `IMAGE`, `MODE`, `REASON`, `FROM_SHA`, `FROM_REF`, `FROM_IMAGE`, `FROM_REFRESHER`, `DB_IMAGE`, `START_REFRESHER` (`start`/`keep-stopped`); shell functions `usage`, `stamp`, `log`, `refuse`, `git_d`, `planner`, `env_get`, `json_field`, `parse_args`, `fetch_tools`, `run_check`, `host_checks`, `print_plan`, `run_rollback`, `main`. `--i-mean-it` refuses ("not wired yet") until V220-9b.

Decisions this task fixes:

- `--keep-refresher` keeps the refresher **stopped** even when the report says `"refresher": "start"` (the operator's way to take the report's `keep-stopped` branch by hand). `--allow-writer-drift` is passed through to `check` unchanged (index note "Check 6 is a refusal").
- The script re-checks the image and the clean tree itself after the planner's report (spec Execution step 1), so a check the report ran as `deploy` minutes earlier is repeated right before anything changes.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_rollback_code_shape.py`:

```python
"""Pins for scripts/ops/rollback_code.sh (v220). The script runs only on the VM
as root, so CI pins its step order and its never-touch rules as text; the
argument-parsing paths, which run before the script touches anything, also run
under bash where one can see the repo."""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "rollback_code.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(src):
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def body(src, name):
    start = src.index(f"\n{name}() {{")
    return src[start:src.index("\n}\n", start)]


def test_everything_lives_in_main_with_one_call_line(src):
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -Eeuo pipefail" in src
    assert src.rstrip().endswith('main "$@"; exit $?')


def test_it_copies_itself_out_of_the_tree_and_reexecs_before_anything_else(src):
    m = body(src, "main")
    assert 'mktemp -d "$APP_DIR/backups/rollback.XXXXXX"' in m
    order = ["parse_args", 'cp "$SELF" "$WORK/rollback_code.sh"',
             'exec bash "$WORK/rollback_code.sh" "$@"', "fetch_tools"]
    pos = [m.index(x) for x in order]
    assert pos == sorted(pos)


def test_the_planner_modules_come_from_the_tools_ref(src):
    assert 'TOOLS="rollback_plan.py rollback_migrations.py rollback_checks.py rollback_window.py"' in src
    assert 'TOOLS_REF="${ROLLBACK_TOOLS_REF:-origin/main}"' in src
    assert 'git_d show "$TOOLS_REF:scripts/ops/$f" > "$WORK/$f"' in body(src, "fetch_tools")


def test_git_and_the_planner_run_as_deploy(code):
    assert 'git_d() { runuser -u deploy -- git -C "$APP_DIR" "$@"; }' in code
    assert 'planner() { runuser -u deploy -- python3 "$WORK/rollback_plan.py" "$@"; }' in code
    bare = [l for l in code.splitlines()
            if re.search(r"(^|[;&|(]|\bthen|\bdo)\s*git\s", l) and "git_d()" not in l]
    assert bare == []


def test_the_checks_run_before_the_dry_run_exit(src):
    b = body(src, "run_rollback")
    order = ["run_check", "host_checks", "print_plan", "Dry run: nothing changed."]
    pos = [b.index(x) for x in order]
    assert pos == sorted(pos)


def test_checks_refuse_with_exit_2_and_a_noop_exits_3(src):
    run = body(src, "run_check")
    assert "--allow-writer-drift" in run and "exit 3" in run and "refuse" in run
    assert "exit 2" in body(src, "refuse")
    hosts = body(src, "host_checks")
    assert 'docker manifest inspect "$IMAGE"' in hosts
    assert "git_d status --porcelain --untracked-files=no" in hosts


def test_the_report_decides_the_refresher_and_keep_refresher_overrides(src):
    run = body(src, "run_check")
    assert 'json_field "$WORK/report.json" refresher' in run
    assert 'if [ "$KEEP_REFRESHER" = 1 ]; then START_REFRESHER=keep-stopped; fi' in run


# --- argument parsing under bash (nothing is touched before it passes) ------

def _working_bash(*paths):
    """A bash that resolves these host paths, or None (WSL's bash cannot see C:/)."""
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


def test_the_script_parses(bash):
    assert subprocess.run([bash, "-n", SCRIPT.as_posix()], capture_output=True).returncode == 0


BAD_ARGS = [
    [], ["--resolve"], ["--resolve", "a", "b"], ["--candidates", "x"], ["--bogus"],
    ["abc123", "img", "--dry-run"], ["a" * 40, "img"], ["a" * 40, "img", "--now"],
    ["a" * 40, "img", "--dry-run", "--bogus"], ["a" * 40, "img", "--dry-run", "--reason"],
]


@pytest.mark.parametrize("args", BAD_ARGS)
def test_bad_arguments_refuse_before_touching_anything(bash, tmp_path, args):
    env = {**os.environ, "ROLLBACK_APP_DIR": tmp_path.as_posix()}
    proc = subprocess.run([bash, SCRIPT.as_posix(), *args], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2
    assert "usage: rollback_code.sh" in proc.stderr
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_code_shape.py`
Expected: FAIL (`FileNotFoundError` for `scripts/ops/rollback_code.sh`).

- [ ] **Step 3: Write the script**

Create `scripts/ops/rollback_code.sh` with LF line endings (after `git add`, `git ls-files --eol scripts/ops/rollback_code.sh` must show `i/lf`):

```bash
#!/usr/bin/env bash
# Code-only rollback (v220): put the VM's checkout and bot image back to an
# earlier main commit while keeping every row of trading data.
#
#   rollback_code.sh --resolve <target>      # one target -> {"sha","image","form","label"}
#   rollback_code.sh --candidates            # picker rows (JSON)
#   rollback_code.sh <sha> <image> --dry-run # every check; nothing changes
#   rollback_code.sh <sha> <image> --i-mean-it [--reason TEXT] [--keep-refresher] [--allow-writer-drift]
#
# Never touched: Postgres contents, the db container, .env beyond the
# SWING_BOT_IMAGE pin, the market data cache. No schema migration runs;
# SWING_BOT_DB_IMAGE stays. While rolled back, backups/deploy_hold.json holds
# every deploy (CI hold job, deploy.sh) until --release.
# Exit: 0 pass, 1 failed (previous code and image restored), 2 refused
# (nothing changed), 3 no-op (target already running).
# Runs ON the VM as root. Its first act copies itself into $WORK and re-execs,
# and the planner modules are written into $WORK from $ROLLBACK_TOOLS_REF, so
# checking out an older tree (which may lack all of them) rewrites nothing
# that is running. Spec: docs/superpowers/specs/2026-11-08-v220-code-only-rollback-design.md
set -Eeuo pipefail

APP_DIR="${ROLLBACK_APP_DIR:-/opt/swing-bot}"
TOOLS_REF="${ROLLBACK_TOOLS_REF:-origin/main}"
DRILL="${ROLLBACK_DRILL:-0}"
TOOLS="rollback_plan.py rollback_migrations.py rollback_checks.py rollback_window.py"
HOLD=backups/deploy_hold.json
LOG=logs/rollback.log

usage() {
  echo "usage: rollback_code.sh --resolve <target> | --candidates" >&2
  echo "       rollback_code.sh <sha40> <image> --dry-run|--i-mean-it [--reason TEXT] [--keep-refresher] [--allow-writer-drift]" >&2
}
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(stamp) rollback_code $*" | tee -a "$LOG"; }
refuse() {
  echo "REFUSE: $*" >&2; echo "$(stamp) rollback_code refused: $*" >> "$LOG"
  exit 2
}
git_d() { runuser -u deploy -- git -C "$APP_DIR" "$@"; }
planner() { runuser -u deploy -- python3 "$WORK/rollback_plan.py" "$@"; }
env_get() { python3 scripts/ops/env_set.py --get "$1"; }
json_field() {
  python3 -c 'import json,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2]); print("" if v is None else v)' "$1" "$2"
}

parse_args() {
  ACTION=""; TARGET=""; SHA=""; IMAGE=""; MODE=""
  REASON="manual rollback"; KEEP_REFRESHER=0; ALLOW_DRIFT=0
  case "${1:-}" in
    --resolve) [ $# -eq 2 ] || return 1; ACTION=resolve; TARGET="$2"; return 0 ;;
    --candidates) [ $# -eq 1 ] || return 1; ACTION=candidates; return 0 ;;
    ''|-*) return 1 ;;
    *) [ $# -ge 3 ] || return 1; ACTION=rollback; SHA="$1"; IMAGE="$2"; MODE="$3"; shift 3 ;;
  esac
  while [ $# -gt 0 ]; do
    case "$1" in
      --reason) [ $# -ge 2 ] || return 1; REASON="$2"; shift 2 ;;
      --keep-refresher) KEEP_REFRESHER=1; shift ;;
      --allow-writer-drift) ALLOW_DRIFT=1; shift ;;
      *) return 1 ;;
    esac
  done
  case "$MODE" in --dry-run|--i-mean-it) ;; *) return 1 ;; esac
  [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] && [ -n "$IMAGE" ]
}

fetch_tools() {
  local f
  git_d fetch -q origin main
  for f in $TOOLS; do
    git_d show "$TOOLS_REF:scripts/ops/$f" > "$WORK/$f"
  done
}

run_check() {
  local rc=0 extra=()
  FROM_SHA="$(git_d rev-parse HEAD)"
  FROM_REF="$(git_d symbolic-ref -q --short HEAD || true)"
  FROM_IMAGE="$(env_get SWING_BOT_IMAGE)"
  DB_IMAGE="$(env_get SWING_BOT_DB_IMAGE)"
  FROM_REFRESHER=keep-stopped
  if [ -n "$(docker compose ps -q --status running refresher 2>/dev/null)" ]; then FROM_REFRESHER=start; fi
  if [ "$ALLOW_DRIFT" = 1 ]; then extra+=(--allow-writer-drift); fi
  planner check "$SHA" --image "$IMAGE" --repo "$APP_DIR" --ref "$TOOLS_REF" --env "$APP_DIR/.env" \
    --running-sha "$FROM_SHA" --hold "$APP_DIR/$HOLD" "${extra[@]}" > "$WORK/report.json" || rc=$?
  cat "$WORK/report.json"
  case "$rc" in
    0) ;;
    3) log "no-op: $SHA is already running"; exit 3 ;;
    2) refuse "safety checks failed (report above)" ;;
    *) echo "rollback_code: planner failed (exit $rc)" >&2; exit 1 ;;
  esac
  START_REFRESHER="$(json_field "$WORK/report.json" refresher)"
  if [ "$KEEP_REFRESHER" = 1 ]; then START_REFRESHER=keep-stopped; fi
}

host_checks() {
  local dirty
  docker manifest inspect "$IMAGE" >/dev/null || refuse "image $IMAGE is not on GHCR"
  dirty="$(git_d status --porcelain --untracked-files=no)"
  if [ -n "$dirty" ]; then refuse "tracked files have local changes (mirror them first): $dirty"; fi
}

print_plan() {
  echo "Code-only rollback plan:"
  echo "  from     git $FROM_SHA  image $FROM_IMAGE"
  echo "  to       git $SHA  image $IMAGE"
  echo "  db image $DB_IMAGE (unchanged); refresher: $START_REFRESHER; reason: $REASON"
  if [ -f "$HOLD" ]; then echo "  replaces the hold: $(cat "$HOLD")"; fi
}

run_rollback() {
  run_check
  host_checks
  print_plan
  if [ "$MODE" = --dry-run ]; then echo "Dry run: nothing changed."; exit 0; fi
  refuse "--i-mean-it is not wired yet (V220-9b)"
}

main() {
  if ! parse_args "$@"; then usage; exit 2; fi
  SELF="$(readlink -f "$0")"
  cd "$APP_DIR"
  mkdir -p backups logs
  if [ -z "${ROLLBACK_WORK:-}" ]; then
    WORK="$(mktemp -d "$APP_DIR/backups/rollback.XXXXXX")"
    chmod 755 "$WORK"
    cp "$SELF" "$WORK/rollback_code.sh"
    ROLLBACK_WORK="$WORK" exec bash "$WORK/rollback_code.sh" "$@"
  fi
  WORK="$ROLLBACK_WORK"
  trap 'rm -rf "$WORK"' EXIT
  fetch_tools
  case "$ACTION" in
    resolve) planner resolve "$TARGET" --repo "$APP_DIR" --ref "$TOOLS_REF" \
               --deploys "$APP_DIR/backups/deploys.jsonl" --current-image "$(env_get SWING_BOT_IMAGE)" || exit $? ;;
    candidates) planner candidates --repo "$APP_DIR" --ref "$TOOLS_REF" \
               --deploys "$APP_DIR/backups/deploys.jsonl" --stable-dir "$APP_DIR/backups/stable" || exit $? ;;
    rollback) run_rollback ;;
  esac
}

main "$@"; exit $?
```

Notes for the implementer:
- Keep every `if …; then …; fi` as written: a bare `[ … ] && cmd` that ends a function returns 1 when the test is false, and `set -e` then kills the caller.
- `"${extra[@]}"` on an empty array is fine under `set -u` on the VM's bash 5.
- After `exec`, the re-executed copy sees `ROLLBACK_WORK` and skips the copy branch; the `EXIT` trap removes `$WORK` and the copy in it (Linux keeps the open file readable until bash exits).
- Argument errors exit before the `cd`, so a typo never creates `backups/` or `logs/` (the bash test asserts the temp dir stays empty).

- [ ] **Step 4: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_code_shape.py`
Expected: `0 failed` (the bash cases skip only where no bash sees the repo).

- [ ] **Step 5: Commit**

```bash
git add scripts/ops/rollback_code.sh tests/scripts/test_rollback_code_shape.py
git commit -m "feat(v220): rollback_code.sh -- self-copy, planner tools from origin/main, resolve, checks, dry run"
```


### Task V220-9b: `rollback_code.sh`: hold, switch, smoke, auto-restore, deploy line

**Model:** sonnet — completes the same script from the spec's Execution steps, text-pinned

**Files:**
- Modify: `scripts/ops/rollback_code.sh` (created by V220-9)
- Test: `tests/scripts/test_rollback_code_shape.py` (created by V220-9)

**Interfaces:**
- Consumes: V220-9's globals and functions (`SHA`, `IMAGE`, `MODE`, `REASON`, `FROM_*`, `DB_IMAGE`, `START_REFRESHER`, `HOLD`, `LOG`, `WORK`, `DRILL`, `stamp`, `log`, `refuse`, `git_d`, `planner`, `json_field`, `run_check`, `host_checks`, `print_plan`); `rollback_window.py snapshot --out FILE --app-dir DIR` (V220-7); `rollback_plan.py deploy-line --kind K --sha S --image I --db-image D --from-sha F` (V220-6b, prints one JSON line); `python -m swingbot.core.infra.rollback_smoke` (V220-8, one JSON line, exit 0/1); `scripts/ops/env_set.py KEY VALUE` (existing, untouched).
- Produces (consumed by V220-10, V220-15, V220-18): the working `--i-mean-it` path; env `ROLLBACK_FORCE_SMOKE_FAIL=1` (honoured only with `ROLLBACK_DRILL=1`); key snapshot `backups/rollback_keys_<at>.json` (`<at>` = the hold's `at`, verbatim); hold file per the Global Constraints; shell functions `services_for <start|keep-stopped>`, `switch_image <image> <start|keep-stopped>` (pins `.env`, brings services up with `--no-deps`, sets `SERVICES` and `SWITCHED_AT`), `record_line <rollback|release> <sha> <image> <from_sha>`, `smoke`, `restore_previous`, `on_error`.

Decisions this task fixes:

- **Replacing a hold** (`/rollback <other target>` while held) keeps the existing hold's `at` and its key snapshot, so the release report covers the whole window; `from_sha`/`from_image` are what runs now, which is what an automatic restore returns to. On a failed smoke the previous hold file is put back, not deleted.
- The refresher is stopped **before** the checkout when it will not run on the target: a target between v197 and v201 has no `refresher` service in its compose file, so stopping it afterwards would fail.
- `ROLLBACK_DRILL=1` skips the pgBackRest backup, starts `admin` (and the refresher) without `bot`, and skips the heartbeat check; the scratch stack is chosen by the caller's `COMPOSE_PROJECT_NAME`/`COMPOSE_FILE` exports (V220-18 keeps its override file outside the checkout, since a checkout of an older target removes it).
- The admin probe is `/api/v1/health` from inside the admin container, accepting `200` or `401` (this part's header: the route is auth-guarded); `rollback_smoke` runs in the admin container, which is up in both the live and the drill stack.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_rollback_code_shape.py` (above the `# --- argument parsing under bash` divider):

```python
def test_the_rollback_steps_run_in_the_spec_order(src):
    b = body(src, "run_rollback")
    order = ["run_check", "host_checks", "print_plan", "Dry run: nothing changed.",
             "trap 'on_error $LINENO' ERR", "pull_and_probe", "safety_backup", "prepare_hold",
             "SWITCHING=1", "write_hold", 'git_d checkout -q --detach "$SHA"', "switch_image",
             "if ! smoke; then restore_previous; exit 1; fi", "SWITCHING=0", "record_line rollback"]
    pos = [b.index(x) for x in order]
    assert pos == sorted(pos)
    assert "not wired yet" not in src


def test_the_hold_carries_the_seven_contract_fields_and_lands_atomically(src):
    w = body(src, "write_hold")
    assert '("sha", "image", "from_sha", "from_image", "db_image", "reason", "at")' in w
    assert 'mv -f "$HOLD.tmp" "$HOLD"' in w and 'chmod 644 "$HOLD.tmp"' in w
    p = body(src, "prepare_hold")
    assert 'AT="$(json_field "$HOLD" at)"' in p
    assert 'KEYS="backups/rollback_keys_$AT.json"' in p
    assert 'rollback_window.py" snapshot --out "$KEYS"' in p


def test_a_failed_smoke_restores_and_writes_no_deploy_line(src):
    r = body(src, "restore_previous")
    assert "record_line" not in r
    assert r.index("trap - ERR") < r.index("set +e") < r.index("git_d checkout")
    assert 'git_d checkout -q --detach "$FROM_SHA"' in r and 'git_d checkout -q "$FROM_REF"' in r
    assert 'switch_image "$FROM_IMAGE" "$FROM_REFRESHER"' in r
    assert 'cp "$WORK/prior_hold.json" "$HOLD"' in r and 'rm -f "$HOLD"' in r
    assert 'if [ "${SWITCHING:-0}" = 1 ]; then restore_previous; fi' in body(src, "on_error")


def test_smoke_covers_health_heartbeat_and_the_write_free_evaluation(src):
    s = body(src, "smoke")
    assert "SMOKE_SECONDS=180" in src
    assert "bot_heartbeat" in src and '"$beat" -ge "$SWITCHED_AT"' in body(src, "heartbeat_fresh")
    assert "/api/v1/health" in body(src, "admin_answers")
    assert "200|401) return 0" in body(src, "admin_answers")
    life = body(src, "lifecycle_smoke")
    assert "import swingbot.core.infra.rollback_smoke" in life
    assert "docker compose exec -T admin python -m swingbot.core.infra.rollback_smoke" in life
    order = ["services_healthy", "heartbeat_fresh", "admin_answers", "lifecycle_smoke"]
    pos = [s.index(x) for x in order]
    assert pos == sorted(pos)
    forced = [l for l in src.splitlines() if "ROLLBACK_FORCE_SMOKE_FAIL" in l]
    assert forced and all('"$DRILL" = 1' in l for l in forced)


def test_the_drill_skips_backup_bot_and_heartbeat(src):
    assert 'if [ "$DRILL" = 1 ]; then log "drill: pgBackRest' in body(src, "safety_backup")
    assert 'if [ "$DRILL" = 1 ]; then s="admin"; fi' in body(src, "services_for")
    assert 'if [ "$DRILL" != 1 ]; then heartbeat_fresh' in body(src, "smoke")


def test_it_never_touches_schema_db_image_env_contents_or_market_data(code):
    assert "alembic" not in code
    assert "env_set.py SWING_BOT_DB_IMAGE" not in code
    assert "> .env" not in code and "sed -i" not in code
    assert "market_data" not in code
    ups = [l for l in code.splitlines() if "docker compose up" in l]
    assert ups and all("--no-deps" in l and "--no-build" in l for l in ups)
    assert not re.search(r"docker compose (down|rm|stop db)", code)
    assert all("--type=diff backup" in l for l in code.splitlines() if "pgbackrest" in l)


def test_the_refresher_is_probed_and_stopped_before_the_checkout(src):
    b = body(src, "run_rollback")
    assert "import swingbot.refresher" in body(src, "pull_and_probe")
    assert b.index("docker compose stop refresher") < b.index('git_d checkout -q --detach "$SHA"')


def test_the_deploy_line_is_written_by_the_planner(src):
    rec = body(src, "record_line")
    assert 'planner deploy-line --kind "$1"' in rec and ">> backups/deploys.jsonl" in rec
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_code_shape.py`
Expected: FAIL (`ValueError: substring not found` for `write_hold`, `smoke`, … and `not wired yet` still present).

- [ ] **Step 3: Write the implementation**

In `scripts/ops/rollback_code.sh`, add two lines after `LOG=logs/rollback.log`:

```bash
SMOKE_SECONDS=180
HEARTBEAT_SQL="SELECT coalesce(floor(extract(epoch FROM (doc->>'timestamp')::timestamptz))::bigint, 0) FROM bot_heartbeat WHERE key = 'bot'"
```

Insert these functions after `print_plan() { … }`:

```bash
pull_and_probe() {
  docker pull "$IMAGE"
  if [ "$START_REFRESHER" = start ] && ! docker run --rm --entrypoint python "$IMAGE" \
      -c "import swingbot.refresher" </dev/null >/dev/null 2>&1; then
    echo "NOTICE: $IMAGE has no swingbot.refresher (pre-v201); the refresher stays stopped." >&2
    START_REFRESHER=keep-stopped
  fi
}

safety_backup() {
  if [ "$DRILL" = 1 ]; then log "drill: pgBackRest safety backup skipped"; return 0; fi
  docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=diff backup </dev/null
}

prepare_hold() {
  AT="$(stamp)"
  if [ -f "$HOLD" ]; then
    cp "$HOLD" "$WORK/prior_hold.json"
    AT="$(json_field "$HOLD" at)"          # the window started at the first rollback
  fi
  KEYS="backups/rollback_keys_$AT.json"
  if [ ! -f "$KEYS" ]; then
    python3 "$WORK/rollback_window.py" snapshot --out "$KEYS" --app-dir "$APP_DIR"
  fi
}

write_hold() {
  python3 - "$HOLD.tmp" "$SHA" "$IMAGE" "$FROM_SHA" "$FROM_IMAGE" "$DB_IMAGE" "$REASON" "$AT" <<'PY'
import json, sys
keys = ("sha", "image", "from_sha", "from_image", "db_image", "reason", "at")
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(dict(zip(keys, sys.argv[2:])), fh, indent=2, sort_keys=True)
PY
  chmod 644 "$HOLD.tmp"
  mv -f "$HOLD.tmp" "$HOLD"
}

services_for() {   # <start|keep-stopped> -> the services to bring up
  local s="bot admin"
  if [ "$DRILL" = 1 ]; then s="admin"; fi
  if [ "$1" = start ]; then s="$s refresher"; fi
  echo "$s"
}

switch_image() {   # <image> <start|keep-stopped>
  local services
  services="$(services_for "$2")"
  python3 scripts/ops/env_set.py SWING_BOT_IMAGE "$1"
  SWITCHED_AT="$(date +%s)"
  SWING_BOT_IMAGE="$1" docker compose up -d --no-deps --no-build --wait $services
  SERVICES="$services"
}

services_healthy() {
  local svc state
  for svc in $SERVICES; do
    state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$(docker compose ps -q "$svc")" 2>/dev/null || echo missing)"
    case "$state" in healthy|running) ;; *) echo "smoke: $svc is $state" >&2; return 1 ;; esac
  done
}

heartbeat_fresh() {   # <deadline epoch>
  local beat
  while [ "$(date +%s)" -lt "$1" ]; do
    beat="$(docker compose exec -T db psql -U swingbot -d swingbot -tAc "$HEARTBEAT_SQL" </dev/null 2>/dev/null | tr -d '[:space:]' || true)"
    if [ -n "$beat" ] && [ "$beat" -ge "$SWITCHED_AT" ]; then return 0; fi
    sleep 10
  done
  echo "smoke: no bot heartbeat since the switch" >&2
  return 1
}

admin_answers() {   # <deadline epoch>; /api/v1/health is auth-guarded: 401 = up and routing
  local code=""
  while [ "$(date +%s)" -lt "$1" ]; do
    code="$(docker compose exec -T admin sh -c \
      'curl -s -o /dev/null -w "%{http_code}" "http://localhost:${ADMIN_PORT:-1234}/api/v1/health"' </dev/null 2>/dev/null || true)"
    case "$code" in 200|401) return 0 ;; esac
    sleep 5
  done
  echo "smoke: admin /api/v1/health answered '${code:-nothing}'" >&2
  return 1
}

lifecycle_smoke() {
  if ! docker run --rm --entrypoint python "$IMAGE" -c "import swingbot.core.infra.rollback_smoke" \
      </dev/null >/dev/null 2>&1; then
    log "image has no rollback_smoke (pre-v220): relying on check 4, heartbeat and health"
    return 0
  fi
  docker compose exec -T admin python -m swingbot.core.infra.rollback_smoke </dev/null
}

smoke() {
  local deadline=$(( $(date +%s) + SMOKE_SECONDS ))
  if [ "$DRILL" = 1 ] && [ "${ROLLBACK_FORCE_SMOKE_FAIL:-0}" = 1 ]; then
    log "drill: forced smoke failure"
    return 1
  fi
  services_healthy || return 1
  if [ "$DRILL" != 1 ]; then heartbeat_fresh "$deadline" || return 1; fi
  admin_answers "$deadline" || return 1
  lifecycle_smoke
}

restore_previous() {
  trap - ERR
  set +e
  log "restoring git $FROM_SHA and image $FROM_IMAGE"
  docker compose stop refresher >/dev/null 2>&1
  if [ -n "$FROM_REF" ]; then git_d checkout -q "$FROM_REF"; else git_d checkout -q --detach "$FROM_SHA"; fi
  switch_image "$FROM_IMAGE" "$FROM_REFRESHER" \
    || log "RESTORE INCOMPLETE: start the services by hand (docker compose up -d --no-deps --no-build --wait <services>)"
  if [ -f "$WORK/prior_hold.json" ]; then cp "$WORK/prior_hold.json" "$HOLD"; else rm -f "$HOLD"; fi
  log "restored git $FROM_SHA, image $FROM_IMAGE; nothing written to deploys.jsonl"
}

on_error() {
  local rc=$?
  echo "$(stamp) rollback_code failed at line $1 (exit $rc)" >> "$LOG"
  if [ "${SWITCHING:-0}" = 1 ]; then restore_previous; fi
  exit 1
}

record_line() {   # <rollback|release> <sha> <image> <from_sha>
  planner deploy-line --kind "$1" --sha "$2" --image "$3" --db-image "$DB_IMAGE" --from-sha "$4" \
    >> backups/deploys.jsonl
}
```

Replace `run_rollback() { … }` with:

```bash
run_rollback() {
  run_check
  host_checks
  print_plan
  if [ "$MODE" = --dry-run ]; then echo "Dry run: nothing changed."; exit 0; fi
  trap 'on_error $LINENO' ERR
  log "rollback to $SHA started (from $FROM_SHA; reason: $REASON)"
  pull_and_probe
  safety_backup
  prepare_hold
  SWITCHING=1
  write_hold
  if [ "$START_REFRESHER" != start ]; then docker compose stop refresher || true; fi
  git_d checkout -q --detach "$SHA"
  switch_image "$IMAGE" "$START_REFRESHER"
  if ! smoke; then restore_previous; exit 1; fi
  SWITCHING=0
  record_line rollback "$SHA" "$IMAGE" "$FROM_SHA"
  log "rollback to $SHA finished; deploys are held until /rollback --release"
}
```

Notes for the implementer:
- `smoke` runs inside `if !`, where bash ignores `set -e` for the whole call tree, so every failure inside it is an explicit `return 1`.
- `SWITCHING=1` is set before `write_hold`: from then on any `ERR` (a failed pull of the checkout, a failed `up`) runs `restore_previous`, which also removes or restores the hold. A failure before it (backup, snapshot) changes nothing and exits 1.
- `on_error`'s `local rc=$?` must stay the first line, or `$?` is lost.
- `record_line` appends as root to a file `deploy` owns; appending keeps the owner. `deploy-line` prints the line with its newline.
- The heartbeat is compared with `SWITCHED_AT` (host clock, taken just before `up`); Postgres runs on the same host, so the clocks agree.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_code_shape.py`
Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ops/rollback_code.sh tests/scripts/test_rollback_code_shape.py
git commit -m "feat(v220): rollback_code.sh -- hold, code and image switch, 3-minute smoke, auto-restore, rollback line"
```


### Task V220-10: `rollback_code.sh --release`

**Model:** sonnet — second path of the same script, text-pinned

**Files:**
- Modify: `scripts/ops/rollback_code.sh` (V220-9, V220-9b)
- Test: `tests/scripts/test_rollback_code_shape.py`

**Interfaces:**
- Consumes: V220-9/V220-9b functions `stamp`, `log`, `refuse`, `git_d`, `env_get`, `json_field`, `host_checks` (checks `$IMAGE` on GHCR and the clean tree), `services_for`, `record_line`, `on_error`, `parse_args`, `main`; `rollback_window.py report --snapshot FILE --since TS --until TS --app-dir DIR` (V220-7); `deploy/deploy.sh` (honours exported `SWING_BOT_IMAGE`/`SWING_BOT_DB_IMAGE`, lines 69-88).
- Produces (consumed by V220-15, V220-18): `bash rollback_code.sh --release --dry-run|--i-mean-it` (exit 0 released, 1 failed, 2 refused, 3 no hold); a `kind: "release"` line in `backups/deploys.jsonl`; the window report on stdout; `check_cron` (also run after a rollback).

Decisions this task fixes:

- **The release image** is main's: strip the tag from the current `SWING_BOT_IMAGE` and add `:sha-<first 12 of origin/main>` (Global Constraints). It must already be on GHCR (`host_checks`), or the release refuses before the hold is touched (CI has not published it yet).
- **`deploy.sh` runs as `deploy`** with both images exported (spec Release step 3): as root it would run its `git reset` as root ("dubious ownership", root-owned files). Its own phase 1 resets `main` to `origin/main` and, with the hold gone, carries on (V220-12's guard sees no file). It also appends its usual deploy line; the `release` line follows it.
- **No automatic restore on release.** The hold is removed first (spec Release step 1); if `deploy.sh` then fails, the script logs that the hold is gone and exits 1: the next CI push deploys `main` normally, and the operator follows `deploy.sh`'s own recovery message.
- **Drill** (`ROLLBACK_DRILL=1`): instead of `deploy.sh` (which would deploy the live stack's way), fast-forward the scratch checkout, pin the image, bring `admin` and the refresher up, and run `alembic upgrade head` in the admin container. This is the only place in the script that runs Alembic.
- **Cron check** after both paths: every `scripts/…` path named in root's or `deploy`'s crontab must exist in the checkout; a missing one is printed as a warning (spec: no research job runs from an older checkout; the v162 history-store cron may name scripts the target lacks).

- [ ] **Step 1: Write the failing tests**

In `tests/scripts/test_rollback_code_shape.py`:

Replace `test_it_never_touches_schema_db_image_env_contents_or_market_data` with:

```python
def test_it_never_touches_schema_db_image_env_contents_or_market_data(src, code):
    drill = body(src, "release_drill")
    assert "alembic upgrade head" in drill
    assert "alembic" not in code.replace(drill, "")
    assert "env_set.py SWING_BOT_DB_IMAGE" not in code
    assert "> .env" not in code and "sed -i" not in code
    assert "market_data" not in code
    ups = [l for l in code.splitlines() if "docker compose up" in l]
    assert ups and all("--no-deps" in l and "--no-build" in l for l in ups)
    assert not re.search(r"docker compose (down|rm|stop db)", code)
    assert all("--type=diff backup" in l for l in code.splitlines() if "pgbackrest" in l)
```

Add, above the `# --- argument parsing under bash` divider:

```python
def test_the_release_steps_run_in_the_spec_order(src):
    b = body(src, "run_release")
    order = ['if [ ! -f "$HOLD" ]', "exit 3", "host_checks", "Dry run: nothing changed.",
             "trap 'on_error $LINENO' ERR", 'rm -f "$HOLD"', "git_d checkout -q main",
             "deploy_main", 'record_line release "$main_sha" "$IMAGE" "$hold_sha"',
             'rollback_window.py" report', "check_cron"]
    pos = [b.index(x) for x in order]
    assert pos == sorted(pos)


def test_the_release_deploys_mains_image_through_deploy_sh_as_deploy(src):
    b = body(src, "run_release")
    assert 'IMAGE="${current%:*}:sha-${main_sha:0:12}"' in b
    assert 'main_sha="$(git_d rev-parse "$TOOLS_REF")"' in b
    d = body(src, "deploy_main")
    assert ('runuser -u deploy -- env SWING_BOT_IMAGE="$IMAGE" SWING_BOT_DB_IMAGE="$DB_IMAGE" '
            'bash "$APP_DIR/deploy/deploy.sh"') in d
    assert 'if [ "$DRILL" = 1 ]; then release_drill' in d


def test_a_failed_release_says_the_hold_is_gone(src):
    b = body(src, "run_release")
    assert "if ! deploy_main; then" in b
    tail = b[b.index("if ! deploy_main; then"):]
    assert "hold" in tail.split("fi")[0] and "exit 1" in tail.split("fi")[0]


def test_cron_is_checked_after_a_rollback_and_after_a_release(src):
    roll = body(src, "run_rollback")
    assert roll.index("record_line rollback") < roll.index("check_cron")
    cron = body(src, "check_cron")
    assert "crontab -l -u deploy" in cron and 'grep -o \'scripts/' in cron
```

Change the `BAD_ARGS` list to:

```python
BAD_ARGS = [
    [], ["--resolve"], ["--resolve", "a", "b"], ["--candidates", "x"], ["--bogus"],
    ["--release"], ["--release", "--now"], ["--release", "--dry-run", "x"],
    ["abc123", "img", "--dry-run"], ["a" * 40, "img"], ["a" * 40, "img", "--now"],
    ["a" * 40, "img", "--dry-run", "--bogus"], ["a" * 40, "img", "--dry-run", "--reason"],
]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_code_shape.py`
Expected: FAIL (`ValueError: substring not found` for `release_drill`, `run_release`, `check_cron`).

- [ ] **Step 3: Write the implementation**

In `scripts/ops/rollback_code.sh`:

1. Header comment: add under the `--i-mean-it` usage line:

```bash
#   rollback_code.sh --release --dry-run|--i-mean-it   # clear the hold, redeploy main
```

2. `usage()`: add a third line:

```bash
  echo "       rollback_code.sh --release --dry-run|--i-mean-it" >&2
```

3. `parse_args()`: add this case **above** the `''|-*) return 1 ;;` line:

```bash
    --release) [ $# -eq 2 ] || return 1; ACTION=release; MODE="$2"
               case "$MODE" in --dry-run|--i-mean-it) return 0 ;; *) return 1 ;; esac ;;
```

4. Insert after `record_line() { … }`:

```bash
check_cron() {   # an older checkout may lack a script a cron line runs
  local path
  for path in $({ crontab -l -u deploy 2>/dev/null; crontab -l 2>/dev/null; } | grep -v '^[[:space:]]*#' \
      | grep -o 'scripts/[A-Za-z0-9_./-]*' | sort -u || true); do
    if [ ! -e "$APP_DIR/$path" ]; then
      echo "WARNING: a cron line runs $path, which this checkout lacks (no research job while held)" >&2
    fi
  done
}

release_drill() {   # scratch project only: deploy.sh would deploy the live stack's way
  git_d merge -q --ff-only "$TOOLS_REF" || return 1
  python3 scripts/ops/env_set.py SWING_BOT_IMAGE "$IMAGE" || return 1
  docker pull "$IMAGE" || return 1
  SWING_BOT_IMAGE="$IMAGE" docker compose up -d --no-deps --no-build --wait $(services_for start) || return 1
  docker compose exec -T admin alembic upgrade head </dev/null
}

deploy_main() {
  if [ "$DRILL" = 1 ]; then release_drill; return; fi
  runuser -u deploy -- env SWING_BOT_IMAGE="$IMAGE" SWING_BOT_DB_IMAGE="$DB_IMAGE" bash "$APP_DIR/deploy/deploy.sh"
}

run_release() {
  local current hold_sha main_sha keys
  if [ ! -f "$HOLD" ]; then log "no-op: no deploy hold to release"; exit 3; fi
  hold_sha="$(json_field "$HOLD" sha)"
  AT="$(json_field "$HOLD" at)"
  DB_IMAGE="$(env_get SWING_BOT_DB_IMAGE)"
  current="$(env_get SWING_BOT_IMAGE)"
  main_sha="$(git_d rev-parse "$TOOLS_REF")"
  IMAGE="${current%:*}:sha-${main_sha:0:12}"
  host_checks
  echo "Release plan:"
  echo "  hold     rollback to $hold_sha since $AT ($(json_field "$HOLD" reason))"
  echo "  deploy   main $main_sha  image $IMAGE  db image $DB_IMAGE"
  if [ "$MODE" = --dry-run ]; then echo "Dry run: nothing changed."; exit 0; fi
  trap 'on_error $LINENO' ERR
  log "release of the hold on $hold_sha started (main $main_sha)"
  cp "$HOLD" "$WORK/released_hold.json"
  rm -f "$HOLD"
  git_d checkout -q main
  if ! deploy_main; then
    log "release FAILED after the hold was removed: main $main_sha is not running; read the deploy output above"
    exit 1
  fi
  record_line release "$main_sha" "$IMAGE" "$hold_sha"
  keys="backups/rollback_keys_$AT.json"
  if [ -f "$keys" ]; then
    python3 "$WORK/rollback_window.py" report --snapshot "$keys" --since "$AT" --until "$(stamp)" \
      --app-dir "$APP_DIR" || log "window report failed (the release itself succeeded)"
  else
    log "no key snapshot for the window since $AT; report skipped"
  fi
  check_cron
  log "released: main $main_sha, image $IMAGE; deploys resume"
}
```

5. `run_rollback()`: add `check_cron` on its own line between `record_line rollback "$SHA" "$IMAGE" "$FROM_SHA"` and the final `log` line.

6. `main()`: add a case line under `rollback) run_rollback ;;`:

```bash
    release) run_release ;;
```

Notes for the implementer:
- `deploy_main` and `release_drill` run inside `if !`, where `set -e` is off, hence the explicit `|| return 1` chain in `release_drill`; `deploy.sh` is its own process with its own `set -euo pipefail`.
- `on_error` sees `SWITCHING` unset on this path, so it only logs and exits 1: there is nothing to restore (the target was the live checkout already).
- `git_d checkout -q main` leaves detached HEAD (spec Release step 2); `deploy.sh` then resets `main` to `origin/main` itself. The drill fast-forwards instead, since `release_drill` never runs `deploy.sh`.
- The `--until` of the window report is taken after the deploy, so rows the new code re-saves during the deploy are counted too.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_code_shape.py`
Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ops/rollback_code.sh tests/scripts/test_rollback_code_shape.py
git commit -m "feat(v220): rollback_code.sh --release -- clear the hold, deploy main's image, release line, window report, cron check"
```


### Task V220-11: Deploy hold in CI: `hold` job and `hold_notice.sh`

**Model:** sonnet — workflow job graph plus a small VM script

**Files:**
- Modify: `.github/workflows/deploy.yml` (new `hold` job before `cleanup`; `cleanup` and `deploy` gated)
- Create: `scripts/ops/hold_notice.sh`
- Modify: `tests/dev/test_ci_db_image.py`
- Test: `tests/dev/test_deploy_hold_job.py` (new, suite `dev-setup`)

**Interfaces:**
- Consumes: the hold-file contract (Global Constraints: `backups/deploy_hold.json` with `sha`, `reason`, `at`, …; held message `deploy held by rollback to <sha> (<reason>, since <at>)`).
- Produces (consumed by V220-15, V220-18): job `hold` with output `held` (`'true'`/`'false'`); `cleanup` runs only when `held == 'false'`; `deploy` runs only when the hold check succeeded and said not held; `bash scripts/ops/hold_notice.sh [APP_DIR]` (prints the held message as its last stdout line, posts it to `OPS_ALERT_WEBHOOK_URL`, always exit 0; prints `no deploy hold` when there is none).

Decisions this task fixes:

- **Verified from the action's `action.yml` at `v1.2.5`** (`gh api "repos/appleboy/ssh-action/contents/action.yml?ref=v1.2.5"`): input `capture_stdout` and output `stdout` exist; there is **no** `script_stop` input, so the hold script handles its own errors and the new job does not pass `script_stop`. Re-run that check in Step 3 before relying on it.
- **Fail closed.** An SSH failure fails the `hold` job, so `cleanup` (needs `hold`, no `always()`) is skipped and `deploy` (`needs.hold.result == 'success'`) is skipped: the run is red, nothing deploys, the image prune does not run. Output that is neither `HELD …` nor `NOT_HELD` fails the decide step the same way.
- **While held** the run stays green: `hold` succeeds with `held=true`, prints a `::warning` with the held message, and `cleanup` and `deploy` are skipped.
- `hold_notice.sh` is fetched from `origin/main` into a `mktemp` file only when the hold file exists, because the VM checkout is the rollback target's tree, which may not have it. If the fetch fails, the job still reports `HELD` with a generic message.

- [ ] **Step 1: Write the failing tests**

Create `tests/dev/test_deploy_hold_job.py`:

```python
"""The CI deploy hold (v220): the workflow's first job reads the VM's
backups/deploy_hold.json and skips cleanup and deploy while it exists; the
job's scripts and hold_notice.sh run here under bash with stubbed git, python3
and curl."""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import pytest

yaml = pytest.importorskip("yaml")
ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
NOTICE = ROOT / "scripts" / "ops" / "hold_notice.sh"
HOLD = {"sha": "a" * 40, "image": "ghcr.io/o/r:sha-aaaaaaaaaaaa", "from_sha": "b" * 40,
        "from_image": "ghcr.io/o/r:sha-bbbbbbbbbbbb", "db_image": "ghcr.io/o/r-db:pgcfg-1",
        "reason": "v230 broke exits", "at": "2026-11-20T10:00:00Z"}
MESSAGE = f"deploy held by rollback to {'a' * 40} (v230 broke exits, since 2026-11-20T10:00:00Z)"
URL = "https://discord.example/api/webhooks/secret-token"


def _jobs():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def test_the_hold_job_runs_first_and_publishes_held():
    hold = _jobs()["hold"]
    assert "needs" not in hold
    assert "refs/heads/main" in hold["if"]
    assert hold["outputs"]["held"] == "${{ steps.decide.outputs.held }}"
    read, decide = hold["steps"][0], hold["steps"][1]
    assert read["id"] == "read" and read["uses"] == "appleboy/ssh-action@v1.2.5"
    assert read["with"]["capture_stdout"] is True and read["with"]["envs"] == "APP_DIR"
    assert "script_stop" not in read["with"]
    assert decide["id"] == "decide" and decide["env"]["SSH_OUT"] == "${{ steps.read.outputs.stdout }}"


def test_cleanup_runs_only_when_not_held():
    cleanup = _jobs()["cleanup"]
    assert cleanup["needs"] == ["hold"]
    assert "needs.hold.outputs.held == 'false'" in cleanup["if"]
    assert "always()" not in cleanup["if"]


def test_deploy_fails_closed_and_tolerates_a_skipped_cleanup():
    deploy = _jobs()["deploy"]
    assert {"hold", "cleanup", "docker-build", "db-image", "publish-image", "compose-lint"} <= set(deploy["needs"])
    cond = deploy["if"]
    for needle in ("always()", "github.ref == 'refs/heads/main'", "needs.hold.result == 'success'",
                   "needs.hold.outputs.held != 'true'",
                   "contains(fromJSON('[\"success\",\"skipped\"]'), needs.cleanup.result)"):
        assert needle in cond
    for job in ("docker-build", "db-image", "publish-image", "compose-lint"):
        assert f"needs.{job}.result == 'success'" in cond


# --- the job's scripts and hold_notice.sh under bash -------------------------

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
def bash(tmp_path):
    found = _working_bash(NOTICE, tmp_path)
    if found is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    return found


STUBS = (
    'python3() { "$PY" "$@"; }; '
    'curl() { printf "%s\\n" "$*" >> "$STUB/curl.log"; return "$(cat "$STUB/curl_rc" 2>/dev/null || echo 0)"; }; '
    'git() { if [ "$3" = fetch ]; then return "$(cat "$STUB/git_rc" 2>/dev/null || echo 0)"; fi; cat "$NOTICE_SRC"; }; '
    "export -f python3 curl git; "
)


@pytest.fixture
def app(tmp_path):
    root = tmp_path / "app"
    (root / "backups").mkdir(parents=True)
    (tmp_path / "stub").mkdir()
    (root / ".env").write_text(f"OPS_ALERT_WEBHOOK_URL={URL}\n", encoding="utf-8", newline="\n")
    return root


def _hold(app, text=None):
    (app / "backups" / "deploy_hold.json").write_text(text or json.dumps(HOLD), encoding="utf-8")


def _run(bash, app, script, **env):
    full = {**os.environ, "APP_DIR": app.as_posix(), "STUB": (app.parent / "stub").as_posix(),
            "PY": pathlib.Path(sys.executable).as_posix(), "NOTICE_SRC": NOTICE.as_posix(), **env}
    return subprocess.run([bash, "-c", STUBS + script], env=full, capture_output=True, text=True, timeout=60)


def _posts(app):
    log = app.parent / "stub" / "curl.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _ssh_script():
    return _jobs()["hold"]["steps"][0]["with"]["script"]


def test_the_ssh_script_says_not_held_without_a_hold_file(bash, app):
    proc = _run(bash, app, _ssh_script())
    assert proc.returncode == 0 and proc.stdout.strip() == "NOT_HELD"
    assert _posts(app) == []


def test_the_ssh_script_says_held_with_the_message_and_posts_once(bash, app):
    _hold(app)
    proc = _run(bash, app, _ssh_script())
    assert proc.returncode == 0
    assert proc.stdout.strip().splitlines()[-1] == f"HELD {MESSAGE}"
    assert len(_posts(app)) == 1 and URL not in proc.stdout + proc.stderr


def test_the_ssh_script_still_holds_when_the_notice_cannot_be_fetched(bash, app):
    _hold(app)
    (app.parent / "stub" / "git_rc").write_text("1", encoding="utf-8")
    proc = _run(bash, app, _ssh_script())
    assert proc.stdout.strip().splitlines()[-1].startswith("HELD deploy held")


@pytest.mark.parametrize("out, held, rc", [
    (f"HELD {MESSAGE}", "true", 0), ("NOT_HELD", "false", 0),
    ("NOT_HELD\r", "false", 0), ("", None, 1), ("ssh: connect refused", None, 1),
])
def test_the_decide_step_maps_the_verdict_and_fails_closed(bash, app, out, held, rc):
    output = app.parent / "gh_output"
    output.write_text("", encoding="utf-8")
    proc = _run(bash, app, _jobs()["hold"]["steps"][1]["run"], SSH_OUT=out, GITHUB_OUTPUT=output.as_posix())
    assert proc.returncode == rc
    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines == ([f"held={held}"] if held else [])


def test_notice_without_a_hold_prints_so_and_posts_nothing(bash, app):
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0 and proc.stdout.strip() == "no deploy hold" and _posts(app) == []


def test_notice_prints_the_verbatim_message_and_never_the_url(bash, app):
    _hold(app)
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0 and proc.stdout.strip().splitlines()[-1] == MESSAGE
    posts = _posts(app)
    assert len(posts) == 1 and MESSAGE in posts[0] and "/rollback --release" in posts[0]
    assert URL not in proc.stdout + proc.stderr


def test_notice_survives_a_failed_post_a_missing_url_and_a_broken_file(bash, app):
    _hold(app)
    (app.parent / "stub" / "curl_rc").write_text("22", encoding="utf-8")
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0 and proc.stdout.strip().splitlines()[-1] == MESSAGE
    (app / ".env").write_text("OTHER=1\n", encoding="utf-8")
    _hold(app, "{not json")
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "deploy held by rollback (backups/deploy_hold.json unreadable)"
    assert len(_posts(app)) == 1   # only the first run posted
```

In `tests/dev/test_ci_db_image.py`, add at the end of `test_the_deploy_waits_for_and_passes_the_db_image`:

```python
    assert "hold" in deploy["needs"]
    assert step["name"] == "Deploy over SSH"   # the hold is a job of its own, not a step here
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_deploy_hold_job.py`
Expected: FAIL (`KeyError: 'hold'`; the notice tests fail on the missing `scripts/ops/hold_notice.sh`).

- [ ] **Step 3: Re-check the action's inputs**

Run: `gh api "repos/appleboy/ssh-action/contents/action.yml?ref=v1.2.5" --jq .content | python -c "import sys,base64; print(base64.b64decode(sys.stdin.read()).decode())" | grep -n "capture_stdout\|stdout:\|script_stop"`
Expected: `capture_stdout:` and `stdout:` lines, no `script_stop`. If `capture_stdout` is missing, stop and report (`BLOCKED`): the job design depends on it.

- [ ] **Step 4: Write `scripts/ops/hold_notice.sh`** (LF line endings)

```bash
#!/usr/bin/env bash
# Deploy hold notice (v220): prints the held message and posts it once to
# OPS_ALERT_WEBHOOK_URL, the VM-side ops alert path heartbeat_watch.sh uses.
#
#   bash scripts/ops/hold_notice.sh [APP_DIR]     # default /opt/swing-bot
#
# Run by the CI `hold` job on the VM (fetched from origin/main, because the
# checkout may be an older rollback target) when backups/deploy_hold.json
# exists. The last stdout line is the message; "no deploy hold" when there is
# none. Always exits 0: a failed post must not turn the hold check red.
# The webhook URL is read from .env without sourcing it and never printed.
set -uo pipefail
APP_DIR="${1:-/opt/swing-bot}"
HOLD_FILE="$APP_DIR/backups/deploy_hold.json"
UNREADABLE="deploy held by rollback (backups/deploy_hold.json unreadable)"

env_value() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=//p" "$APP_DIR/.env" 2>/dev/null | tail -1 | tr -d '\r' \
    | sed -e 's/^["'\'']//' -e 's/["'\'']$//' -e 's/[[:space:]]*$//'
}

held_message() {
  python3 - "$HOLD_FILE" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        h = json.load(fh)
    print(f"deploy held by rollback to {h['sha']} ({h['reason']}, since {h['at']})")
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(1)
PY
}

main() {
  local msg payload url
  if [ ! -f "$HOLD_FILE" ]; then echo "no deploy hold"; return 0; fi
  msg="$(held_message)" || msg="$UNREADABLE"
  url="$(env_value OPS_ALERT_WEBHOOK_URL)"
  if [ -n "$url" ]; then
    payload="$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1] + " -- release with /rollback --release"}))' "$msg")"
    curl -fsS -m 15 -o /dev/null -H 'Content-Type: application/json' -d "$payload" "$url" >/dev/null 2>&1 \
      || echo "hold_notice: ops notice not delivered" >&2
  fi
  echo "$msg"
}

main; exit 0
```

- [ ] **Step 5: Add the `hold` job and gate `cleanup` and `deploy`**

In `.github/workflows/deploy.yml`, insert directly above the comment block that precedes `cleanup:` (keep two-space job indentation):

```yaml
  # ── 4a. Deploy hold (v220) ───────────────────────────────────────────────
  # A code-only rollback (scripts/ops/rollback_code.sh) writes
  # backups/deploy_hold.json on the VM. While it exists no push may deploy:
  # the VM checkout is then the rollback target, whose own deploy.sh may have
  # no hold check and would reset to main first, so the check lives here,
  # in the pushed commit's workflow. Held: this job succeeds with held=true,
  # warns, posts one ops notice (hold_notice.sh), and cleanup + deploy are
  # skipped (the prune would delete the rollback's from_image). The run stays
  # green. A failed check fails closed: nothing is pruned or deployed.
  hold:
    if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      held: ${{ steps.decide.outputs.held }}
    steps:
      - name: Read the deploy hold over SSH
        id: read
        uses: appleboy/ssh-action@v1.2.5
        with:
          host: ${{ secrets.HETZNER_HOST }}
          username: ${{ secrets.HETZNER_USER }}
          key: ${{ secrets.HETZNER_SSH_KEY }}
          port: ${{ secrets.HETZNER_SSH_PORT || 22 }}
          capture_stdout: true
          envs: APP_DIR
          script: |
            HOLD_FILE="$APP_DIR/backups/deploy_hold.json"
            if [ ! -f "$HOLD_FILE" ]; then
              echo "NOT_HELD"
              exit 0
            fi
            msg="deploy held (backups/deploy_hold.json is present)"
            notice="$(mktemp)"
            if git -C "$APP_DIR" fetch -q origin main \
                && git -C "$APP_DIR" show origin/main:scripts/ops/hold_notice.sh > "$notice"; then
              msg="$(bash "$notice" "$APP_DIR" | tail -n 1)"
            fi
            rm -f "$notice"
            echo "HELD $msg"
        env:
          APP_DIR: ${{ secrets.HETZNER_APP_DIR || '/opt/swing-bot' }}
      - name: Decide
        id: decide
        env:
          SSH_OUT: ${{ steps.read.outputs.stdout }}
        run: |
          line="$(printf '%s\n' "$SSH_OUT" | tr -d '\r' | grep '^HELD ' | head -n 1 || true)"
          if [ -n "$line" ]; then
            echo "held=true" >> "$GITHUB_OUTPUT"
            echo "::warning title=Deploy held::${line#HELD }"
          elif printf '%s\n' "$SSH_OUT" | tr -d '\r' | grep -qx 'NOT_HELD'; then
            echo "held=false" >> "$GITHUB_OUTPUT"
          else
            echo "::error::the deploy hold check gave no verdict; not deploying"
            exit 1
          fi

```

Change the `cleanup` job's head to:

```yaml
  cleanup:
    needs: [hold]
    if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request' && needs.hold.outputs.held == 'false'
```

Change the `deploy` job's `needs:` and `if:` (keep the comment lines above them; add one comment line):

```yaml
  deploy:
    needs: [hold, docker-build, db-image, publish-image, cleanup, compose-lint]
    # Skip on a manual run against a branch, where nothing was published --
    # deploying would silently re-run whatever :latest currently points at.
    # v220: always() so a cleanup skipped by the hold is evaluated here, not
    # inherited; every other need must have succeeded, and a failed hold
    # check means no deploy.
    if: >-
      always() && github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
      && needs.hold.result == 'success' && needs.hold.outputs.held != 'true'
      && needs.docker-build.result == 'success' && needs.db-image.result == 'success'
      && needs.publish-image.result == 'success' && needs.compose-lint.result == 'success'
      && contains(fromJSON('["success","skipped"]'), needs.cleanup.result)
```

Notes for the implementer:
- `held != 'true'` together with `needs.hold.result == 'success'` means a hold job that succeeded with `held=false`. When held, `cleanup` is skipped, and the `contains(...)` clause alone would not stop the deploy: the `held` clause does.
- The `>-` folded scalar joins the lines with spaces; the test reads the folded string.
- Do not add `script_stop` to the new step (no such input at `v1.2.5`); the existing steps keep theirs (out of scope).
- The decide step strips `\r` because the action's captured output can carry CRLF.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_deploy_hold_job.py`, then `python scripts/dev/testrun.py file tests/dev/test_ci_db_image.py` and `python scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: `0 failed` each (bash cases skip only where no bash sees the repo).

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/deploy.yml scripts/ops/hold_notice.sh tests/dev/test_deploy_hold_job.py tests/dev/test_ci_db_image.py
git commit -m "feat(v220): CI deploy hold -- hold job gates cleanup and deploy, hold_notice.sh posts one ops notice"
```

