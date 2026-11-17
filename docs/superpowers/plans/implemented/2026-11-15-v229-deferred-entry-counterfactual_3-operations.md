# v229 — Deferred-entry counterfactual: Part 3 — operations (V229-11..V229-15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V229-13" -A 300 <this file>`); never read the file whole.

**Spec:** [2026-11-14-v229-deferred-entry-counterfactual-design.md](../specs/2026-11-14-v229-deferred-entry-counterfactual-design.md)
**Index:** [2026-11-15-v229-deferred-entry-counterfactual_0-index.md](2026-11-15-v229-deferred-entry-counterfactual_0-index.md) — Global Constraints, Parallelisation, the task ledger, the shared shapes (PAIR, DELTA, CALIBRATION, FROZEN) and the `## Handoff` resolutions all live there and bind every task below.

V229-11 is code (two shell scripts and their test) and runs in the plan's
worktree with V229-1..10. V229-12..15 are operations on `main` after
V229-1..11 are merged and CI is green: they write results documents, touch
the VM only through `bash scripts/ops/ssh-hetzner.sh`, and treat every VM
write (`/opt/swing-bot/data/v229/`, the crontab) as a production change under
the `mirror-prod` skill. **No task deploys**; the script reaches the bot image
through the partner's next routine `/deploy` (Handoff 14). **V229-15 is
blocked until `verdict.verdict_open_date(T0)`** (about late February 2027).

Common shell names used below (set them in each Bash call; never `cd`):

```bash
R=/e/Documents/Private/Projects/Discord-Bot        # the main tree on the dev machine
SSH="bash $R/scripts/ops/ssh-hetzner.sh"            # the only way onto the VM
W=E:/Documents/Private/Projects/Discord-Bot          # the same tree in the form Python on Windows needs
SCRATCH=<the session scratchpad, Git Bash form>      # temp files; never inside the repo
```

# Phase 3 — operations

### Task V229-11: Weekly VM cron scripts

**Model:** haiku — two short shell scripts on an existing installer pattern (`install_v171_cron.sh`) plus a pinned-shape test; no contract design.

Runs in the plan's worktree, in parallel with V229-2..10 (disjoint files). The
scripts call the CLI by the flags fixed in the ledger row of V229-10; they do
not import it, so this task needs nothing from V229-2..10 to pass its tests.

**Files:**
- Create: `scripts/ops/v229_pairs_cron.sh`
- Create: `scripts/ops/install_v229_cron.sh`
- Test: `tests/scripts/test_v229_cron_scripts.py` (suite `tooling`; no `tests/suites.toml` edit)
- Read only, never edit: `scripts/ops/export_book_rows.sh`

**Interfaces:**
- Consumes (by command line only, ledger V229-10): `python scripts/reports/deferred_entry_counterfactual.py --mode append --rows <csv> --t0 <ISO UTC>`; defaults `--bars-dir market_data/5min`, `--pairs-log data/v229/pairs.jsonl` (container cwd `/app`, so relative paths land in the host mount `/opt/swing-bot/data`). `bash scripts/ops/export_book_rows.sh rows` (host side; it `cd`s to `${SWING_BOT_DIR:-/opt/swing-bot}` itself).
- Produces: `install_v229_cron.sh <T0>` — idempotent crontab entry, MARKER `# v229 deferred-entry pairs`, schedule `15 8 * * 6` (Saturday 08:15 UTC, after the Friday close and the nightly archive refresh), line `/bin/bash <BASE>/scripts/ops/v229_pairs_cron.sh <T0>`; refuses (exit 2) a `T0` that is not ISO 8601 with seconds and an offset. `v229_pairs_cron.sh <T0>` — writes `<BASE>/data/v229/rows.csv` (atomically, through `rows.csv.tmp`), then runs the CLI in `append` mode, all output appended to `<BASE>/logs/v229-pairs.log`; a failed export leaves the previous `rows.csv` and appends nothing; exit status is the failing step's. Test seams: `SWING_BOT_DIR` (default `/opt/swing-bot`) and `DOCKER` (default `/usr/bin/docker`).

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_v229_cron_scripts.py`:

```python
"""The v229 weekly cron scripts (plan v229 V229-11). They run only on the VM;
these tests pin their shape and run both under a stubbed crontab and docker.
crontab and docker are exported bash functions: a stub file is not
executable on Windows (the precedent is tests/scripts/test_pitr_crons.py)."""
import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
RUNNER, INSTALLER = "v229_pairs_cron.sh", "install_v229_cron.sh"
T0 = "2026-11-16T09:00:00+00:00"
MARKER = "# v229 deferred-entry pairs"
EXPORT_OK = 'echo "row_kind,trade_id"\necho "trade,t-1"\n'
EXPORT_FAIL = 'echo "partial"\nexit 3\n'


def _text(name):
    return (OPS / name).read_text(encoding="utf-8")


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
    found = _working_bash(OPS / RUNNER, tmp_path)
    if found is None:
        pytest.skip("no bash that can see host paths")
    return found


def _crontab_fn(store):
    return (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}" 2>/dev/null; '
            f'else d=$(cat); printf "%s\n" "$d" > "{store.as_posix()}"; fi; }}; export -f crontab; ')


def _install(bash, tmp_path, store, t0=T0):
    env = {**os.environ, "SWING_BOT_DIR": tmp_path.as_posix()}
    cmd = _crontab_fn(store) + f'bash "{(OPS / INSTALLER).as_posix()}" "{t0}"'
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True)


def _run_runner(bash, tmp_path, *, export_body, docker_rc=0, args=(T0,)):
    ops = tmp_path / "scripts" / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / "export_book_rows.sh").write_text(export_body, encoding="utf-8", newline="\n")
    fn = f'docker_stub() {{ echo "DOCKER $*"; return {docker_rc}; }}; export -f docker_stub; '
    env = {**os.environ, "SWING_BOT_DIR": tmp_path.as_posix(), "DOCKER": "docker_stub"}
    quoted = " ".join(f'"{a}"' for a in args)
    cmd = fn + f'bash "{(OPS / RUNNER).as_posix()}" {quoted}'
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True)


def _log(tmp_path):
    return (tmp_path / "logs" / "v229-pairs.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", [RUNNER, INSTALLER])
def test_strict_mode_lf_and_no_in_place_sed(name):
    assert "set -" in _text(name)
    assert b"\r" not in (OPS / name).read_bytes()
    assert "sed -i" not in _text(name)


def test_installer_is_weekly_marked_and_rewrites_its_own_line():
    text = _text(INSTALLER)
    assert f"MARKER='{MARKER}'" in text
    assert "15 8 * * 6 /bin/bash" in text
    assert "grep -vF" in text


def test_runner_calls_the_cli_in_append_mode_only():
    text = _text(RUNNER)
    assert "scripts/reports/deferred_entry_counterfactual.py" in text
    assert "--mode append" in text
    assert "--mode verdict" not in text and "--mode exploratory" not in text


def test_runner_exports_then_appends(bash, tmp_path):
    out = _run_runner(bash, tmp_path, export_body=EXPORT_OK)
    assert out.returncode == 0, out.stderr
    v229 = tmp_path / "data" / "v229"
    assert (v229 / "rows.csv").read_text(encoding="utf-8").splitlines() == [
        "row_kind,trade_id", "trade,t-1"]
    assert not (v229 / "rows.csv.tmp").exists()
    log = _log(tmp_path)
    assert log.startswith("=== ")
    docker = [line for line in log.splitlines() if line.startswith("DOCKER ")]
    assert docker == ["DOCKER compose exec -T bot python "
                      "scripts/reports/deferred_entry_counterfactual.py "
                      f"--mode append --rows data/v229/rows.csv --t0 {T0}"]


def test_a_failed_export_keeps_the_last_rows_and_appends_nothing(bash, tmp_path):
    v229 = tmp_path / "data" / "v229"
    v229.mkdir(parents=True)
    (v229 / "rows.csv").write_text("old\n", encoding="utf-8")
    out = _run_runner(bash, tmp_path, export_body=EXPORT_FAIL)
    assert out.returncode == 1
    assert (v229 / "rows.csv").read_text(encoding="utf-8") == "old\n"
    assert not (v229 / "rows.csv.tmp").exists()
    log = _log(tmp_path)
    assert "export failed" in log
    assert "DOCKER" not in log


def test_a_failed_append_is_the_runner_exit_status(bash, tmp_path):
    out = _run_runner(bash, tmp_path, export_body=EXPORT_OK, docker_rc=5)
    assert out.returncode == 5
    assert "DOCKER compose exec" in _log(tmp_path)


def test_runner_without_t0_does_nothing(bash, tmp_path):
    out = _run_runner(bash, tmp_path, export_body=EXPORT_OK, args=())
    assert out.returncode != 0
    assert not (tmp_path / "logs" / "v229-pairs.log").exists()
    assert not (tmp_path / "data" / "v229" / "rows.csv").exists()


def test_installer_is_idempotent_and_replaces_an_old_v229_line(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n" + MARKER + "\n"
                     "15 8 * * 6 /bin/bash /old/scripts/ops/v229_pairs_cron.sh "
                     "2026-01-01T00:00:00+00:00\n", encoding="utf-8")
    for _ in range(2):
        out = _install(bash, tmp_path, store)
        assert out.returncode == 0, out.stderr
    lines = store.read_text(encoding="utf-8").splitlines()
    assert sum("backup_db.sh" in line for line in lines) == 1
    assert lines.count(MARKER) == 1
    v229 = [line for line in lines if "v229_pairs_cron.sh" in line]
    assert v229 == [f"15 8 * * 6 /bin/bash {tmp_path.as_posix()}/scripts/ops/v229_pairs_cron.sh {T0}"]
    assert (tmp_path / "logs").is_dir() and (tmp_path / "data" / "v229").is_dir()


@pytest.mark.parametrize("bad", ["2026-11-16", "2026-11-16T09:00:00",
                                 "2026-11-16 09:00:00+00:00", "2026-11-16T09:00:00+00:00 x"])
def test_installer_refuses_a_malformed_t0(bash, tmp_path, bad):
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n", encoding="utf-8")
    out = _install(bash, tmp_path, store, t0=bad)
    assert out.returncode == 2
    assert "T0" in out.stderr
    assert store.read_text(encoding="utf-8") == "0 3 * * * /x/backup_db.sh\n"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_v229_cron_scripts.py`
Expected: FAIL — the static tests raise `FileNotFoundError` on `scripts/ops/v229_pairs_cron.sh`; the bash-driven ones skip for now (the fixture probes the runner's path) and must PASS, not skip, after Step 4.

- [ ] **Step 3: Write the runner**

Create `scripts/ops/v229_pairs_cron.sh` (LF line endings; `.gitattributes` already forces `*.sh` to LF):

```bash
#!/usr/bin/env bash
# v229 weekly pair append (plan docs/superpowers/plans/implemented/2026-11-15-v229-deferred-entry-counterfactual_0-index.md,
# Task V229-11). Runs ON THE VM from the crontab line install_v229_cron.sh writes.
#   1. The read-only book export, on the HOST (the bot container has no psql
#      path), into data/v229/rows.csv (= /app/data/v229/rows.csv in the bot
#      container), written through rows.csv.tmp so a failed export never
#      leaves a half file behind.
#   2. The deferred-entry CLI in append mode inside the bot container: it
#      appends the new eligible pairs to data/v229/pairs.jsonl (append-once
#      per trade id) and prints one count line.
# It decides, resolves and removes nothing: the verdict is Task V229-15's, by
# hand, after verdict_open_date(T0). An empty week prints a count of 0 and exits 0.
# Usage: v229_pairs_cron.sh <T0>   (ISO 8601 UTC, the pre-registration commit time)
# SWING_BOT_DIR / DOCKER are test seams; a real run takes the defaults.
set -uo pipefail

T0=${1:?usage: v229_pairs_cron.sh <T0>}
BASE=${SWING_BOT_DIR:-/opt/swing-bot}
DOCKER=${DOCKER:-/usr/bin/docker}

cd "$BASE" || exit 1
mkdir -p data/v229 logs

run() {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    if ! bash scripts/ops/export_book_rows.sh rows > data/v229/rows.csv.tmp; then
        rm -f data/v229/rows.csv.tmp
        echo "v229 pairs: export failed; rows.csv left as it was, nothing appended"
        return 1
    fi
    mv -f data/v229/rows.csv.tmp data/v229/rows.csv
    "$DOCKER" compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py \
        --mode append --rows data/v229/rows.csv --t0 "$T0"
}

run >> logs/v229-pairs.log 2>&1
exit $?
```

- [ ] **Step 4: Write the installer**

Create `scripts/ops/install_v229_cron.sh`:

```bash
#!/usr/bin/env bash
# Installs (idempotently) the v229 weekly pair-append crontab entry on the
# Hetzner VM (plan v229, Tasks V229-11 and V229-14). A re-run replaces its own
# line, never duplicates. T0 is baked into the line: the CLI needs it in every
# mode and cannot read its own freeze commit on the VM (plan Handoff 13).
# Run ON the VM as root, after the deploy that ships scripts/ops/v229_pairs_cron.sh:
#   bash scripts/ops/ssh-hetzner.sh "bash -s -- <T0>" < scripts/ops/install_v229_cron.sh
# Removal (Task V229-15, after the verdict):
#   crontab -l | grep -vF '# v229 deferred-entry pairs' | grep -vF v229_pairs_cron.sh | crontab -
# SWING_BOT_DIR is a test seam; a real run takes the default.
set -euo pipefail

T0=${1:?usage: install_v229_cron.sh <T0>}
if ! [[ "$T0" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$ ]]; then
    echo "install_v229_cron: T0 must be ISO 8601 with seconds and an offset, got '$T0'" >&2
    exit 2
fi

BASE=${SWING_BOT_DIR:-/opt/swing-bot}
MARKER='# v229 deferred-entry pairs'
CRON_LINE="15 8 * * 6 /bin/bash $BASE/scripts/ops/v229_pairs_cron.sh $T0"

mkdir -p "$BASE/logs" "$BASE/data/v229"
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v229_pairs_cron.sh" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_v229_cron_scripts.py`
Expected: PASS, 0 failed, and on this dev machine 0 skipped (Git Bash sees `C:/...` paths; a skip here means the wrong bash was found, which is a failure to chase, not to accept). Then confirm the export script is untouched:

```bash
git diff --quiet -- scripts/ops/export_book_rows.sh && echo "export untouched"
```

Expected: `export untouched`.

- [ ] **Step 6: Commit**

Both scripts get the executable bit like their precedent (`scripts/ops/install_v171_cron.sh` is `100755`; cron calls them through `/bin/bash`, so this is hygiene, not a requirement):

```bash
git add scripts/ops/v229_pairs_cron.sh scripts/ops/install_v229_cron.sh tests/scripts/test_v229_cron_scripts.py
git update-index --chmod=+x scripts/ops/v229_pairs_cron.sh scripts/ops/install_v229_cron.sh
git commit -m "feat(v229): weekly VM cron that exports the book and appends deferred-entry pairs (V229-11)"
```

### Task V229-12: Freeze — pre-registration and T0

**Model:** sonnet — a scripted document build with verbatim-quote and hash checks; judgement is limited to the stop conditions, which are spelled out.

Runs on `main`, after V229-1..11 are merged and CI is green. It writes no
code and touches the VM read-only. The forward rule is frozen by this
document's **first commit**; its commit timestamp is `T0` (Handoff 2, 13).
No ledger row is written here: the one row `v229-deferred-entry` is appended
when the study closes (V229-13 on an uncalibrated read, else V229-15).

**Files:**
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v229-preregistration.md` (the UTC date the doc is written; later tasks find it with `ls docs/superpowers/results/*-v229-preregistration.md`)

**Interfaces:**
- Consumes: `deferred_entry.verdict.FROZEN`, `verdict.rule_hash() -> str`, `verdict.forward_window(t0) -> (date, date)`, `verdict.verdict_open_date(t0) -> date`, `verdict.LEDGER_ID` (V229-8); `scripts/reports/deferred_entry_counterfactual.py` present on `main` (V229-10).
- Produces: the doc, with a line `**T0:** <ISO 8601 UTC>` (format `2026-11-16T09:00:00+00:00`) added by the second commit, plus `**Forward window:** <start> .. <end>` and `**Verdict opens:** <date>`. V229-13..15 read `T0` with `sed -n 's/^\*\*T0:\*\* //p' <doc>`.

- [ ] **Step 1: Check the preconditions (read-only)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
git -C "$R" fetch -q origin && git -C "$R" status -sb | head -1
git -C "$R" ls-files scripts/reports/deferred_entry_counterfactual.py scripts/reports/deferred_entry/verdict.py scripts/ops/v229_pairs_cron.sh scripts/ops/install_v229_cron.sh
git -C "$R" grep -n '"v229-deferred-entry"' -- docs/superpowers/results/preregistration-ledger.jsonl || echo "ledger clean"
ls "$R"/docs/superpowers/results/*-v229-preregistration.md 2>/dev/null || echo "no prereg yet"
gh run list --branch main --limit 1 --json conclusion,headSha,displayTitle
$SSH "cd /opt/swing-bot && docker compose exec -T bot test -f scripts/reports/deferred_entry_counterfactual.py && echo IMAGE-HAS-SCRIPT || echo IMAGE-MISSING-SCRIPT"
```

Expected: `main` level with `origin/main`; all four files listed; `ledger clean`; `no prereg yet`; the latest `main` run `success`; `IMAGE-HAS-SCRIPT`.

Stop conditions (do not work around any of them):
- a file missing, the run not green, or the ledger already holding the id: stop and report `BLOCKED` with the line that failed;
- `IMAGE-MISSING-SCRIPT`: the reads run from the bot image and **no task deploys** (Handoff 14). Ask the partner through `AskUserQuestion` to run the routine `/deploy` (recommended option: "deploy now, then resume V229-12"), wait, and re-run this step.

Then check that the image's frozen rule is the committed one (a stale image would freeze one rule and run another). Python on this machine needs the Windows form of the repo path, `W`:

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
HASH='import sys; sys.path.insert(0, "scripts/reports"); from deferred_entry import verdict; print(verdict.rule_hash())'
echo "local $(python -c "import sys; sys.path.insert(0, '$W/scripts/reports'); from deferred_entry import verdict; print(verdict.rule_hash())")"
echo "vm    $(echo "$HASH" | $SSH "cd /opt/swing-bot && docker compose exec -T bot python -")"
```

Expected: the two 16-hex hashes are equal. Unequal means the image predates a `verdict.py` change on `main`: stop and ask for the routine `/deploy` exactly as above.

- [ ] **Step 2: Build the document**

The quoted spec text is copied by the script, never retyped, so it is verbatim by construction. Save as `$SCRATCH/v229_prereg.py` (the session scratchpad) and run `python "$SCRATCH/v229_prereg.py"`:

```python
"""Build the v229 pre-registration doc (plan V229-12). Run once, from anywhere."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

R = Path("E:/Documents/Private/Projects/Discord-Bot")
sys.path.insert(0, str(R / "scripts" / "reports"))
from deferred_entry import verdict  # noqa: E402

SPEC = "docs/superpowers/specs/implemented/2026-11-14-v229-deferred-entry-counterfactual-design.md"
PLAN = "docs/superpowers/plans/implemented/2026-11-15-v229-deferred-entry-counterfactual_0-index.md"
CLI = "scripts/reports/deferred_entry_counterfactual.py"
spec = (R / SPEC).read_text(encoding="utf-8")


def git(*args):
    return subprocess.run(["git", "-C", str(R), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def quote(start, stop):
    a = spec.index(start)
    return spec[a:spec.index(stop, a)].rstrip() + "\n"


today = dt.datetime.now(dt.timezone.utc).date().isoformat()
doc = R / "docs" / "superpowers" / "results" / f"{today}-v229-preregistration.md"
assert not doc.exists(), doc
frozen = json.dumps(verdict.FROZEN, sort_keys=True, indent=2)
lines = [
    "# v229 pre-registration — Deferred-entry counterfactual on the live LONG book", "",
    f"**Spec:** `{SPEC}`, last changed in `{git('log', '-1', '--format=%h', '--', SPEC)}`.",
    f"**Plan:** `{PLAN}`.",
    f"**Code:** `main` at `{git('rev-parse', '--short=8', 'HEAD')}` (V229-1..V229-11 merged, CI green). "
    "No edit under `scripts/reports/deferred_entry/` or to the CLI until the verdict is recorded.",
    f"**Driver:** `{CLI}` (modes `append`, `exploratory`, `verdict`); pair log `data/v229/pairs.jsonl` on the VM.",
    "**Committed before any compute.** This document's first commit is the freeze; its commit "
    "timestamp is `T0`, recorded below in a follow-up commit. No ledger row is written now: the one "
    f"row `{verdict.LEDGER_ID}` is appended when the study closes (plan Handoff 2).", "",
    "## Frozen constants", "",
    f"`verdict.FROZEN`, rule hash `{verdict.rule_hash()}` (sha256 of the sorted JSON, first 16 hex). "
    "Every pair row carries this hash; the verdict refuses a log carrying any other.", "",
    "```json", frozen, "```", "",
    "## The measurement (verbatim from the spec)", "",
    "<!-- spec-quote-begin -->", quote("## The question", "### 2. The pair log"),
    "<!-- spec-quote-end -->", "",
    "## The reads and the verdict (verbatim from the spec)", "",
    "<!-- spec-quote-begin -->", quote("### 3. Two reads, frozen before either", "## What does not change"),
    "<!-- spec-quote-end -->", "",
    "## Where the code departs from the spec's wording (plan index § Handoff)", "",
    "- **Ledger.** No row before the read: the ledger is append-only and refuses a duplicate id, so "
    "the freeze is this commit (v226 precedent) and exactly one row is appended at the close. Study "
    "words map to ledger tokens: PASS -> PASS, NO-LIFT -> NO-LIFT, UNDERPOWERED -> NO-LIFT, "
    "UNCALIBRATED -> INCONCLUSIVE; the study word is written into the row's hypothesis. Row verdict "
    "PASS when either arm passes; `p = min(1, 2 x the smaller one-sided p)`; `n` the forward LONG "
    "pairs; `exp_r` the mean delta of the arm with the smaller p; instrument `v1`.",
    "- **Frictions.** `net_r(..., direction=\"long\"|\"short\", days=...)`: longs pass `days=0`; the "
    "bearish disclosure passes calendar days held, as the screen does.",
    "- **Live path class** comes from `last_leg_reason` (else `close_reason`): `tp1*` win, "
    "`scratch` scratch, `loss`/`stop` loss, anything else excluded and counted. The export carries "
    "only the last leg, so a TP1 partial whose runner was scratched classes as scratch.",
    "- **Coverage.** Every NYSE session from the entry date to the fifth after it has a bar, and a "
    "bar starts at or after the horizon close minus 15 minutes; a half day on the entry date, or no "
    "bar in [15:30 ET, close), is `no_deferral_bar`. A forward trade whose horizon is past the "
    "archive's last bar is `pending` and recounted by the next run.",
    "- **Forward window** is the twelve complete ISO weeks (Monday to Sunday) after T0's ET date; "
    "the verdict opens the day after the fifth NYSE session following the window's last session.",
    "- **Not in the verdict population:** trades opened in the window and still open on the "
    "verdict date (the export joins closed journal entries only). Disclosed in the verdict doc.",
    "- **T0 is an input** (`--t0`, baked into the cron line): the script cannot read its own "
    "freeze commit on the VM.", "",
]
doc.write_text("\n".join(lines), encoding="utf-8", newline="\n")
print(doc.relative_to(R).as_posix())
```

Expected: one line, `docs/superpowers/results/<today>-v229-preregistration.md`.

- [ ] **Step 3: Verify the document**

Save as `$SCRATCH/v229_prereg_check.py` and run `python "$SCRATCH/v229_prereg_check.py"`:

```python
import json
import re
import sys
from pathlib import Path

R = Path("E:/Documents/Private/Projects/Discord-Bot")
sys.path.insert(0, str(R / "scripts" / "reports"))
from deferred_entry import verdict  # noqa: E402

spec = (R / "docs/superpowers/specs/implemented/2026-11-14-v229-deferred-entry-counterfactual-design.md").read_text(encoding="utf-8")
(doc,) = sorted((R / "docs/superpowers/results").glob("*-v229-preregistration.md"))
text = doc.read_text(encoding="utf-8")
quotes = re.findall(r"<!-- spec-quote-begin -->\n(.*?)\n<!-- spec-quote-end -->", text, re.S)
assert len(quotes) == 2 and all(q.strip() and q.strip() in spec for q in quotes), "quote drifted"
assert f"rule hash `{verdict.rule_hash()}`" in text, "hash mismatch"
frozen = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
assert frozen == verdict.FROZEN, "FROZEN block mismatch"
assert "**T0:**" not in text, "T0 belongs to the follow-up commit"
print("prereg OK", doc.name, verdict.rule_hash())
```

Expected: `prereg OK <file> <hash>`.

- [ ] **Step 4: Commit the freeze**

```bash
R=/e/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); DOC=${DOC#"$R"/}
git -C "$R" add "$DOC"
git -C "$R" commit -m "docs(v229): pre-registration -- forward rule frozen before any compute (V229-12)"
```

- [ ] **Step 5: Record T0, the forward window and the verdict date**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); DOC=${DOC#"$R"/}
RAW=$(git -C "$R" log --diff-filter=A -1 --format=%cI -- "$DOC")
python - "$W" "$DOC" "$RAW" <<'PY'
import sys
from pathlib import Path
import pandas as pd
root, rel, raw = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.path.insert(0, str(root / "scripts" / "reports"))
from deferred_entry import verdict  # noqa: E402
t0 = pd.Timestamp(raw).tz_convert("UTC")
start, end = verdict.forward_window(t0)
opens = verdict.verdict_open_date(t0)
block = ("\n## Freeze\n\n"
         f"**T0:** {t0.isoformat()}\n"
         f"**Forward window:** {start.isoformat()} .. {end.isoformat()} (entry dates, ET)\n"
         f"**Verdict opens:** {opens.isoformat()}\n\n"
         f"T0 is the first commit of this document (`git log --diff-filter=A -1 --format=%cI -- {rel}` "
         f"= `{raw}`), converted to UTC. Plans opened before T0's ET date are exploratory; the "
         "verdict is computed once, on or after the date above (Task V229-15).\n")
path = root / rel
path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + block, encoding="utf-8", newline="\n")
print(block)
PY
sed -n 's/^\*\*T0:\*\* //p' "$R/$DOC"
```

Expected: the block printed, then one line, the UTC `T0` (for example `2026-11-16T09:00:00+00:00`). `pd.Timestamp(raw).tz_convert` works because `%cI` always carries an offset.

- [ ] **Step 6: Commit T0**

```bash
R=/e/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); DOC=${DOC#"$R"/}
git -C "$R" add "$DOC"
git -C "$R" commit -m "docs(v229): record T0, the forward window and the verdict date (V229-12)"
```

Report to the controller: `T0`, the window, the verdict date and the rule hash. The controller pushes both commits before V229-13 starts (the freeze must be public before production is read).

### Task V229-13: Exploratory read (VM, read-only archive)

**Model:** sonnet — scripted production run plus a two-branch close-out whose rule is fixed by the spec; the only judgement is noticing a stop condition.

Runs on `main` after V229-12's two commits are pushed. It reads production
(the book export, the 5-minute archive) and writes only under
`/opt/swing-bot/data/v229/` on the VM, which the spec allows; that write is a
production change, so **invoke the `mirror-prod` skill first** and follow it
(there is nothing to mirror back except the results committed here). The read
is run **once**: it is exploratory, issues no verdict and ships nothing; its
only purpose is calibration. **Nothing in the forward rule changes after it is
read**, whatever it shows; an `UNCALIBRATED` read closes the study instead of
tuning the simulator.

**Files:**
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v229-exploratory-read.md` (UTC date of the run)
- Create: `docs/superpowers/results/v229/exploratory.json`
- Only if the read is `UNCALIBRATED`: Modify `docs/superpowers/results/preregistration-ledger.jsonl` (one appended row), Modify `docs/claude/backtest-methodology.md` (one row in § Closed pre-registrations)
- VM: `/opt/swing-bot/data/v229/rows.csv`, `pairs.jsonl`, `exploratory.{md,json}` (created by the CLI)

**Interfaces:**
- Consumes: the CLI (V229-10) with `--mode append|exploratory`, `--rows`, `--t0`, defaults `--bars-dir market_data/5min`, `--pairs-log data/v229/pairs.jsonl`, `--out-dir data/v229`; `append` prints `v229 pairs: appended <a>, total <t>, forward <f>`; `exploratory` writes `<out-dir>/exploratory.{md,json}`. The JSON is `report.build_payload(...)` (V229-9): keys `study, phase, t0, rule_hash, frozen, archive_last_bar, git_sha, disclosures, funnel, buckets, arms, deltas, b_over_taken, calibration, weekly, splits, skips, tradeability, close_bucket, bearish, verdict`; `verdict` is `verdict.exploratory_close(calibration, n_pairs)` — `None` when calibrated, else `{"study": "UNCALIBRATED", ..., "ledger": {"verdict": "INCONCLUSIVE", "n": <pairs>, "exp_r": None, "p": None}}` (V229-8). `T0` from the pre-registration doc (V229-12).
- Produces: `data/v229/pairs.jsonl` on the VM seeded with the exploratory pairs (every row's `rule_hash` equal to `verdict.rule_hash()`); the calibration decision V229-14 depends on.

- [ ] **Step 1: Check the preconditions (read-only)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
echo "T0=$T0"
git -C "$R" fetch -q origin && git -C "$R" rev-list --count origin/main..main
ls "$R"/docs/superpowers/results/*-v229-exploratory-read.md 2>/dev/null || echo "no exploratory read yet"
HASH='import sys; sys.path.insert(0, "scripts/reports"); from deferred_entry import verdict; print(verdict.rule_hash())'
echo "local $(python -c "import sys; sys.path.insert(0, '$W/scripts/reports'); from deferred_entry import verdict; print(verdict.rule_hash())")"
echo "vm    $(echo "$HASH" | $SSH "cd /opt/swing-bot && docker compose exec -T bot python -")"
$SSH "ls -la /opt/swing-bot/data/v229 2>&1; ls /opt/swing-bot/market_data/5min | wc -l; git -C /opt/swing-bot rev-parse HEAD; crontab -l 2>/dev/null | grep -c v229_pairs_cron.sh"
```

Expected: a non-empty `T0`; `0` commits unpushed (the freeze is public); `no exploratory read yet`; equal hashes; `data/v229` absent or holding no `pairs.jsonl`; a non-zero archive file count; the host checkout SHA (record it as `HOST_SHA`); `0` v229 cron lines.

Stop conditions: an empty `T0` or unpushed commits (finish V229-12); an existing exploratory doc or `pairs.jsonl` (the read is run once: report `BLOCKED` with the listing, never delete the log); unequal hashes (ask the partner for the routine `/deploy` through `AskUserQuestion`; no task deploys).

- [ ] **Step 2: Export the book on the VM host**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
$SSH "cd /opt/swing-bot && mkdir -p data/v229 && bash scripts/ops/export_book_rows.sh rows > data/v229/rows.csv.tmp && mv -f data/v229/rows.csv.tmp data/v229/rows.csv && wc -l data/v229/rows.csv && head -1 data/v229/rows.csv | tr ',' '\n' | grep -c ."
```

Expected: a line count in the hundreds or more, then `38` (or `39` once v228's column has shipped; the reader works on both, Handoff 7). A failed export leaves `rows.csv.tmp`; re-run the step.

- [ ] **Step 3: Append the exploratory pairs**

The log is the checkpoint (one fsynced line per pair); if the command is killed, re-run it unchanged and it skips the ids already present.

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
$SSH "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py --mode append --rows data/v229/rows.csv --t0 $T0"
```

Expected: exactly one line `v229 pairs: appended <a>, total <t>, forward 0` with `a == t > 0`. `forward` must be `0` (the window starts the Monday after T0); a non-zero `forward` means `T0` is wrong: stop and report.

- [ ] **Step 4: Run the exploratory read**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
$SSH "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py --mode exploratory --rows data/v229/rows.csv --t0 $T0 --git-sha \$(git -C /opt/swing-bot rev-parse HEAD) && ls -la data/v229"
```

Expected: exit 0 and `exploratory.md` and `exploratory.json` listed beside `pairs.jsonl` and `rows.csv`.

- [ ] **Step 5: Copy the outputs and build the results doc**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
mkdir -p "$R/docs/superpowers/results/v229"
$SSH "cat /opt/swing-bot/data/v229/exploratory.json" > "$R/docs/superpowers/results/v229/exploratory.json"
$SSH "cat /opt/swing-bot/data/v229/exploratory.md" > "$SCRATCH/v229_exploratory.md"
HOST_SHA=$($SSH "git -C /opt/swing-bot rev-parse HEAD")
python - "$W" "$SCRATCH/v229_exploratory.md" "$HOST_SHA" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

root, body_path, host_sha = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].strip()
sys.path.insert(0, str(root / "scripts" / "reports"))
from deferred_entry import verdict  # noqa: E402

payload = json.loads((root / "docs/superpowers/results/v229/exploratory.json").read_text(encoding="utf-8"))
assert payload["phase"] == "exploratory", payload["phase"]
assert payload["rule_hash"] == verdict.rule_hash(), "image ran another rule"
assert payload["frozen"] == verdict.FROZEN
(pre,) = sorted((root / "docs/superpowers/results").glob("*-v229-preregistration.md"))
today = dt.datetime.now(dt.timezone.utc).date().isoformat()
doc = root / "docs/superpowers/results" / f"{today}-v229-exploratory-read.md"
cal = payload["calibration"]
header = [
    "# v229 exploratory read — deferred entry on the live LONG book", "",
    "**Spec:** `docs/superpowers/specs/implemented/2026-11-14-v229-deferred-entry-counterfactual-design.md`.",
    "**Plan:** `docs/superpowers/plans/implemented/2026-11-15-v229-deferred-entry-counterfactual_0-index.md`, Task V229-13.",
    f"**Pre-registration:** `{pre.relative_to(root).as_posix()}`; T0 `{payload['t0']}`; rule hash `{payload['rule_hash']}`.",
    f"**Host checkout:** `{host_sha}` (script SHA in the report body: `{payload['git_sha']}`); "
    f"archive last bar `{payload['archive_last_bar']}`.",
    "**Run:** `export_book_rows.sh rows` on the VM host, then the CLI in `append` and `exploratory` "
    "mode in the bot container (commands in plan V229-13).",
    "**Exploratory: no verdict, not evidence.** Its window overlaps the data that motivated the "
    "idea; it only checks calibration. Nothing in the forward rule changes after it.",
    f"**Calibration:** agreement {cal['agreement']} on {cal['n']} plans, {cal['excluded']} excluded; "
    f"{'CALIBRATED: the forward read starts (V229-14)' if cal['calibrated'] else 'UNCALIBRATED: the study closes inconclusive, the forward read is not started'}.",
    "", "---", "",
]
doc.write_text("\n".join(header) + body_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
print(doc.relative_to(root).as_posix())
print(json.dumps({"calibration": cal, "funnel": payload["funnel"], "deltas": payload["deltas"],
                  "verdict": payload["verdict"]}, indent=2))
PY
```

Expected: the doc path, then the calibration (3x3 `table`, `n`, `agreement`, `excluded`, `calibrated`), the funnel with every reason including zeros, both deltas, and `verdict` (`null` when calibrated). The three asserts guard the frozen rule; a failure is a stop, not a re-run.

- [ ] **Step 6: Commit the read**

```bash
R=/e/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-exploratory-read.md); DOC=${DOC#"$R"/}
git -C "$R" add "$DOC" docs/superpowers/results/v229/exploratory.json
git -C "$R" commit -m "docs(v229): exploratory read -- calibration check on plans closed before T0 (V229-13)"
```

(`git -C "$R" add` resolves the relative JSON path against `$R`.)

- [ ] **Step 7a: Calibrated — report and hand on**

When `calibration.calibrated` is `true`: report to the controller and the partner the 3x3 table, the agreement, the `excluded` and `scratch` counts (plan index § OPEN: the export carries only the last leg, so a TP1 partial with a scratched runner classes as `scratch`), both exploratory deltas **labelled exploratory**, and that V229-14 installs the weekly cron next. No question is asked: the spec fixes the branch, and the rule is frozen. Steps 7b and 8 do not run.

- [ ] **Step 7b: Uncalibrated — close the study**

When `calibration.calibrated` is `false` (and `verdict.study == "UNCALIBRATED"`), append the one ledger row from the payload's `verdict.ledger`:

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-exploratory-read.md); DOC=${DOC#"$R"/}
N=$(python -c "import json; print(json.load(open('$W/docs/superpowers/results/v229/exploratory.json'))['verdict']['ledger']['n'])")
python "$W/scripts/reports/preregistration_ledger.py" --id v229-deferred-entry --instrument v1 \
  --hypothesis "Deferred LONG market entry on the live book: enter at the open of the first 5-minute bar at or after 15:30 ET (arm A), or the same but skip plans whose original stop traded before that bar (arm B), stop and TP1 distances kept, against the filled control; single-leg TP1 race on 5-minute bars, net of frictions (deferred arms 2x entry slippage); per-plan delta, week-clustered bootstrap. Study: UNCALIBRATED on the exploratory read (path-class agreement under 0.80); forward read never started." \
  --n "$N" --exp-r null --p null --verdict INCONCLUSIVE --record "$DOC"
```

Expected: `v229-deferred-entry: verdict INCONCLUSIVE, p=null, BH q=n/a (no p-value) ...`. A `refused:` line means the id is already in the ledger: stop and report.

Then add one row at the end of the table under `### Closed pre-registrations — do not re-run these` in `docs/claude/backtest-methodology.md`, filling the numbers from the JSON. **Do not wrap any all-caps word of five or more letters in backticks** (`tests/hooks/test_guardrails.py::test_every_all_caps_knob_in_the_closed_table_is_in_the_constant` treats those as closed knobs):

```markdown
| Deferred LONG market entry to the 15:30 ET bar (arm A) and the same skipping plans whose original stop traded before 15:30 (arm B), stop and TP1 distances kept, live-book counterfactual on 5-minute bars [v229] | **INCONCLUSIVE: simulator uncalibrated, forward read never started.** Exploratory path-class agreement <agreement> under 0.80 on <n> plans (<excluded> excluded). The simulator is not tuned to pass. A different deferral time, a close-based skip, a different race or a market-on-close fill is a new idea with a new name, not a retry. | `results/<date>-v229-exploratory-read.md`, ledger `v229-deferred-entry` |
```

Run both checks:

```bash
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
```

Expected: both PASS, 0 failed.

- [ ] **Step 8: Commit the close (uncalibrated only)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot
git -C "$R" add docs/superpowers/results/preregistration-ledger.jsonl docs/claude/backtest-methodology.md
git -C "$R" commit -m "docs(v229): close the study inconclusive -- exploratory read uncalibrated (V229-13)"
```

Report to the controller: the study is closed; V229-14 and V229-15 do not run (the cron was never installed, so there is nothing to remove); the plan goes to `/close-out` as no-lift.

### Task V229-14: Install the weekly cron

**Model:** haiku — runs one committed installer over SSH and records its output; no decisions beyond the listed stop conditions.

Runs on `main` only after V229-13 committed a **calibrated** exploratory read
(an uncalibrated read closed the study; this task then does not run).
Installing a crontab entry is a production change: **invoke the `mirror-prod`
skill first**. The installer and runner are already committed (V229-11) and
reach the host checkout through the deploy, so the crontab line is the only
live change, and it is mirrored by recording it in the pre-registration doc.
Once the first count below is printed, **the window, thresholds and floor are
locked** (spec § 3).

**Files:**
- VM: root crontab gains the `# v229 deferred-entry pairs` entry (via `scripts/ops/install_v229_cron.sh`)
- Modify: `docs/superpowers/results/<YYYY-MM-DD>-v229-preregistration.md` (append a `## Weekly cron` section)

**Interfaces:**
- Consumes: `install_v229_cron.sh <T0>` and `v229_pairs_cron.sh <T0>` (V229-11; MARKER `# v229 deferred-entry pairs`, schedule `15 8 * * 6`, log `/opt/swing-bot/logs/v229-pairs.log`); `T0` from the pre-registration doc (V229-12); the CLI's append line `v229 pairs: appended <a>, total <t>, forward <f>` (V229-10).
- Produces: the installed crontab line and the first weekly count, recorded in the pre-registration doc; V229-15 removes the line.

- [ ] **Step 1: Check the preconditions (read-only)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE"); echo "T0=$T0"
python -c "import json; print('calibrated', json.load(open('$W/docs/superpowers/results/v229/exploratory.json'))['calibration']['calibrated'])"
git -C "$R" grep -n '"v229-deferred-entry"' -- docs/superpowers/results/preregistration-ledger.jsonl || echo "ledger clean"
$SSH "test -f /opt/swing-bot/scripts/ops/v229_pairs_cron.sh && test -f /opt/swing-bot/scripts/ops/install_v229_cron.sh && echo HOST-HAS-SCRIPTS || echo HOST-MISSING-SCRIPTS; crontab -l 2>/dev/null | grep -c v229_pairs_cron.sh; wc -l < /opt/swing-bot/data/v229/pairs.jsonl"
```

Expected: a non-empty `T0`; `calibrated True`; `ledger clean`; `HOST-HAS-SCRIPTS`; `0` existing v229 lines; the pair count V229-13 appended.

Stop conditions: `calibrated False` or the ledger holding the id (the study is closed; report and stop); `HOST-MISSING-SCRIPTS` (the host checkout predates V229-11; ask the partner through `AskUserQuestion` for the routine `/deploy`, never deploy).

- [ ] **Step 2: Install the entry**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
$SSH "bash -s -- $T0" < "$R/scripts/ops/install_v229_cron.sh"
```

Expected: `Installed crontab:` followed by the existing lines, then exactly

```
# v229 deferred-entry pairs
15 8 * * 6 /bin/bash /opt/swing-bot/scripts/ops/v229_pairs_cron.sh <T0>
```

An exit 2 (`T0 must be ISO 8601 ...`) means the doc's `T0` line is malformed: stop and report; do not hand-edit the crontab.

- [ ] **Step 3: Run the runner once now and read the first count**

This is the first weekly count: it proves the export, the container call and the log path work today instead of on Saturday.

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
$SSH "bash /opt/swing-bot/scripts/ops/v229_pairs_cron.sh $T0; echo exit=\$?; tail -n 3 /opt/swing-bot/logs/v229-pairs.log"
```

Expected: `exit=0`, then a `=== <UTC stamp> ===` line and `v229 pairs: appended 0, total <t>, forward 0` (nothing new since V229-13 on the same day; a non-zero `appended` is fine if plans closed in between, `forward` stays `0` until the window opens). An `export failed` line or a non-zero exit: stop, leave the entry installed, report the log tail. (The `\$?` is escaped so the VM, not the dev machine, expands it.)

- [ ] **Step 4: Record the install in the pre-registration doc**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); PRE=${PRE#"$R"/}
LINE=$($SSH "crontab -l | grep -F v229_pairs_cron.sh")
COUNT=$($SSH "grep -F 'v229 pairs:' /opt/swing-bot/logs/v229-pairs.log | tail -n 1")
python - "$W/$PRE" "$LINE" "$COUNT" <<'PY'
import datetime as dt
import sys
from pathlib import Path
path, line, count = Path(sys.argv[1]), sys.argv[2].strip(), sys.argv[3].strip()
assert line.startswith("15 8 * * 6 /bin/bash /opt/swing-bot/scripts/ops/v229_pairs_cron.sh "), line
assert count.startswith("v229 pairs: appended "), count
now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
block = ("\n## Weekly cron\n\n"
         f"Installed {now} on the VM root crontab by `scripts/ops/install_v229_cron.sh` (plan V229-14), "
         "marker `# v229 deferred-entry pairs`:\n\n"
         f"```\n{line}\n```\n\n"
         f"First count (runner run by hand at install): `{count}`. From this count on, the window, the "
         "thresholds and the floor are locked. The log is `/opt/swing-bot/logs/v229-pairs.log`; "
         "Task V229-15 removes the entry after the verdict.\n")
path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + block, encoding="utf-8", newline="\n")
print(block)
PY
```

Expected: the block printed; both asserts pass.

- [ ] **Step 5: Commit**

```bash
R=/e/Documents/Private/Projects/Discord-Bot
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); PRE=${PRE#"$R"/}
git -C "$R" add "$PRE"
git -C "$R" commit -m "docs(v229): weekly pair cron installed on the VM; first count recorded (V229-14)"
```

Tell the partner (scheduling rule, `working-conventions.md` § Scheduling far-off work): the cron runs every Saturday at 08:15 UTC, appends forward pairs and prints one count line to `/opt/swing-bot/logs/v229-pairs.log`; the verdict opens on the doc's `**Verdict opens:**` date and is V229-15's, by hand. The controller pushes the commit.

### Task V229-15: Forward verdict (blocked until `verdict_open_date(T0)`)

**Model:** opus — the one verdict of a pre-registration: it must refuse every shortcut (early date, stale ledger, mixed rule hash), map study words to ledger tokens exactly and write the closing records without bending the frozen rule.

> **BLOCKED until `verdict.verdict_open_date(T0)`** — the day after the fifth NYSE session following the forward window's last session (the `**Verdict opens:**` line of the pre-registration doc; about late February 2027 for a November 2026 `T0`). Before that date this task is **not available work**: Step 1 stops it, and nothing else may run. It also does not run at all when V229-13 closed the study as uncalibrated.

Runs on `main`. Writing `/opt/swing-bot/data/v229/` and removing the crontab
entry are production changes: **invoke the `mirror-prod` skill first**. The
verdict is computed **once**; the script refuses a second one (the ledger
already holding `v229-deferred-entry`) and one before the open date.

**Files:**
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v229-forward-verdict.md` (UTC date of the run)
- Create: `docs/superpowers/results/v229/forward-verdict.json`
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one appended row, id `v229-deferred-entry`)
- Modify (study not `PASS` only): `docs/claude/backtest-methodology.md` (one row in § Closed pre-registrations)
- VM: `/opt/swing-bot/data/v229/ledger.jsonl` (a copy of the repo ledger for the guard), `forward-verdict.{md,json}` (written by the CLI); the `# v229 deferred-entry pairs` crontab entry removed

**Interfaces:**
- Consumes: `verdict.verdict_open_date(t0) -> date`, `verdict.rule_hash()`, `verdict.LEDGER_ID`, `verdict.STUDY_TO_LEDGER` (V229-8); the CLI `--mode verdict --rows --t0 --ledger` writing `<out-dir>/forward-verdict.{md,json}` (V229-10), whose guard refuses before the open date, on a ledger holding `LEDGER_ID`, or on a log with another `rule_hash`; the payload's `verdict` = `verdict.study_verdict(...)` -> `{"study", "arms": {"A", "B"}, "ledger": {"verdict", "n", "exp_r", "p"}}` (V229-9, V229-8); `v229_pairs_cron.sh <T0>` (V229-11); `scripts/reports/preregistration_ledger.py` (existing CLI, `--exp-r null` / `--p null` accepted).
- Produces: the ledger row `v229-deferred-entry` (instrument `v1`, no `data_source`), scored by `stats.ledger_qvalues` with the other ideas.

- [ ] **Step 1: Gate on the open date (read-only)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
python - "$W" "$T0" <<'PY'
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "reports"))
from deferred_entry import verdict  # noqa: E402
opens = verdict.verdict_open_date(sys.argv[2])
today = dt.datetime.now(dt.timezone.utc).date()
print(f"verdict opens {opens}, today {today}: {'OPEN' if today >= opens else 'BLOCKED'}")
PY
```

Expected: `... OPEN`. `BLOCKED` means stop here and report `BLOCKED: v229 verdict opens <date>`; run nothing else (no append, no copy, no cron change).

- [ ] **Step 2: Check the remaining preconditions (read-only)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
git -C "$R" fetch -q origin && git -C "$R" status -sb | head -1
git -C "$R" grep -n '"v229-deferred-entry"' -- docs/superpowers/results/preregistration-ledger.jsonl || echo "ledger clean"
HASH='import sys; sys.path.insert(0, "scripts/reports"); from deferred_entry import verdict; print(verdict.rule_hash())'
echo "local $(python -c "import sys; sys.path.insert(0, '$W/scripts/reports'); from deferred_entry import verdict; print(verdict.rule_hash())")"
echo "vm    $(echo "$HASH" | $SSH "cd /opt/swing-bot && docker compose exec -T bot python -")"
$SSH "crontab -l 2>/dev/null | grep -c v229_pairs_cron.sh; grep -F 'v229 pairs:' /opt/swing-bot/logs/v229-pairs.log | tail -n 3; git -C /opt/swing-bot rev-parse HEAD"
```

Expected: `main` level with `origin/main`; `ledger clean`; equal hashes; `1` cron line; the last three weekly counts with `forward` growing week on week; the host SHA (record it as `HOST_SHA`).

Stop conditions: the ledger already holding the id (a verdict exists: report, never append a second); unequal hashes (an image built after a rule change would refuse or mislead: report `BLOCKED` and ask the partner, never edit `verdict.py` to match); weekly counts missing for weeks inside the window (report the gap in the verdict doc's limitations; the append-once log still recounts every closed trade, so run on).

- [ ] **Step 3: Final append and the guard's ledger**

The last weekly run may predate trades that closed since; append them, then hand the guard the **repo's** ledger (the image's copy is as old as its build):

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
$SSH "bash /opt/swing-bot/scripts/ops/v229_pairs_cron.sh $T0; echo exit=\$?; tail -n 1 /opt/swing-bot/logs/v229-pairs.log"
$SSH "cat > /opt/swing-bot/data/v229/ledger.jsonl" < "$R/docs/superpowers/results/preregistration-ledger.jsonl"
$SSH "wc -l < /opt/swing-bot/data/v229/ledger.jsonl"; wc -l < "$R/docs/superpowers/results/preregistration-ledger.jsonl"
```

Expected: `exit=0` and a count line; the two ledger line counts equal.

- [ ] **Step 4: Compute the verdict**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
PRE=$(ls "$R"/docs/superpowers/results/*-v229-preregistration.md); T0=$(sed -n 's/^\*\*T0:\*\* //p' "$PRE")
$SSH "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py --mode verdict --rows data/v229/rows.csv --t0 $T0 --git-sha \$(git -C /opt/swing-bot rev-parse HEAD) --ledger data/v229/ledger.jsonl; echo exit=\$?; ls -la data/v229"
```

Expected: `exit=0` and `forward-verdict.md`, `forward-verdict.json` listed. A refusal (non-zero exit, `VerdictRefused` message) is the guard doing its job: report it verbatim and stop; never pass a different `--t0`, `--today` or ledger to get past it.

- [ ] **Step 5: Copy the outputs and build the results doc**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
mkdir -p "$R/docs/superpowers/results/v229"
$SSH "cat /opt/swing-bot/data/v229/forward-verdict.json" > "$R/docs/superpowers/results/v229/forward-verdict.json"
$SSH "cat /opt/swing-bot/data/v229/forward-verdict.md" > "$SCRATCH/v229_forward.md"
HOST_SHA=$($SSH "git -C /opt/swing-bot rev-parse HEAD")
python - "$W" "$SCRATCH/v229_forward.md" "$HOST_SHA" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

root, body_path, host_sha = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].strip()
sys.path.insert(0, str(root / "scripts" / "reports"))
from deferred_entry import verdict  # noqa: E402

payload = json.loads((root / "docs/superpowers/results/v229/forward-verdict.json").read_text(encoding="utf-8"))
v = payload["verdict"]
assert payload["rule_hash"] == verdict.rule_hash() and payload["frozen"] == verdict.FROZEN
assert v["study"] in verdict.STUDY_TO_LEDGER and v["ledger"]["verdict"] == verdict.STUDY_TO_LEDGER[v["study"]]
(pre,) = sorted((root / "docs/superpowers/results").glob("*-v229-preregistration.md"))
today = dt.datetime.now(dt.timezone.utc).date().isoformat()
doc = root / "docs/superpowers/results" / f"{today}-v229-forward-verdict.md"
header = [
    f"# v229 forward verdict — deferred entry on the live LONG book: {v['study']}", "",
    "**Spec:** `docs/superpowers/specs/implemented/2026-11-14-v229-deferred-entry-counterfactual-design.md`.",
    "**Plan:** `docs/superpowers/plans/implemented/2026-11-15-v229-deferred-entry-counterfactual_0-index.md`, Task V229-15.",
    f"**Pre-registration:** `{pre.relative_to(root).as_posix()}`; T0 `{payload['t0']}`; rule hash `{payload['rule_hash']}`.",
    f"**Host checkout:** `{host_sha}` (script SHA in the report body: `{payload['git_sha']}`); "
    f"archive last bar `{payload['archive_last_bar']}`.",
    f"**Study:** {v['study']}; arm A {v['arms']['A']}, arm B {v['arms']['B']}. Ledger row "
    f"`{verdict.LEDGER_ID}`: verdict {v['ledger']['verdict']}, n {v['ledger']['n']}, "
    f"exp_r {v['ledger']['exp_r']}, p {v['ledger']['p']}.",
    "**Limitations:** single-leg TP1 race (no runner, no TP2); the export carries only the last leg, "
    "so a TP1 partial with a scratched runner classes as scratch; trades opened in the window and "
    "still open on the verdict date are not in the export and so not in the population; the "
    "control starts at the bar after its entry, so entry-bar stop-outs are invisible to it "
    "(count in the tradeability section).",
    "**Cron:** the `# v229 deferred-entry pairs` entry is removed from the VM crontab by this task.",
    "", "---", "",
]
doc.write_text("\n".join(header) + body_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
print(doc.relative_to(root).as_posix())
print(json.dumps({"verdict": v, "deltas": payload["deltas"], "calibration": payload["calibration"]}, indent=2))
PY
```

Expected: the doc path, then the study, both arm verdicts, the ledger fields, both deltas (`n`, `weeks`, `mean`, `lower`, `p`) and the calibration. The asserts guard the frozen rule; a failure is a stop.

- [ ] **Step 6: Append the ledger row**

Fill `VERDICT`, `N`, `EXPR`, `P` from `verdict.ledger` (null stays `null`) and `STUDY`, `ARMS` from the payload (`ARMS` names the passing arms, or `none`):

```bash
R=/e/Documents/Private/Projects/Discord-Bot; W=E:/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-forward-verdict.md); DOC=${DOC#"$R"/}
read -r VERDICT N EXPR P STUDY ARMS < <(python -c "
import json
v = json.load(open('$W/docs/superpowers/results/v229/forward-verdict.json'))['verdict']
f = lambda x: 'null' if x is None else x
arms = ','.join(a for a, w in sorted(v['arms'].items()) if w == 'PASS') or 'none'
print(v['ledger']['verdict'], f(v['ledger']['n']), f(v['ledger']['exp_r']), f(v['ledger']['p']), v['study'], arms)
")
echo "$VERDICT $N $EXPR $P $STUDY $ARMS"
python "$W/scripts/reports/preregistration_ledger.py" --id v229-deferred-entry --instrument v1 \
  --hypothesis "Deferred LONG market entry on the live book: enter at the open of the first 5-minute bar at or after 15:30 ET (arm A), or the same but skip plans whose original stop traded before that bar (arm B), stop and TP1 distances kept, against the filled control; single-leg TP1 race on 5-minute bars, net of frictions (deferred arms 2x entry slippage); per-plan delta over the twelve ISO weeks after T0, week-clustered bootstrap, one-sided 97.5% bound, PASS at mean >= +0.10R with bound > 0 and calibrated; p = min(1, 2 x smaller arm p). Study: $STUDY; passing arms: $ARMS." \
  --n "$N" --exp-r "$EXPR" --p "$P" --verdict "$VERDICT" --record "$DOC"
```

Expected: `v229-deferred-entry: verdict <VERDICT>, p=<P>, BH q=<q> across <m> ledger p-values ... Reported, not gating.` Quote the BH q in the report. A `refused:` line: stop and report (never edit the ledger by hand).

- [ ] **Step 7: Close the question or hand on the PASS**

**Study not `PASS`** (`NO-LIFT`, `UNDERPOWERED`, `UNCALIBRATED`): add one row at the end of the table under `### Closed pre-registrations — do not re-run these` in `docs/claude/backtest-methodology.md`, numbers from the JSON. **Never wrap an all-caps word of five or more letters in backticks** (`tests/hooks/test_guardrails.py` reads those as closed knobs):

```markdown
| Deferred LONG market entry to the 15:30 ET bar (arm A) and the same skipping plans whose original stop traded before 15:30 (arm B), stop and TP1 distances kept, live-book counterfactual on 5-minute bars, forward read over the twelve ISO weeks after T0 [v229] | **<ledger verdict>, one shot spent (study: <study word>).** Forward LONG pairs <n> in <weeks> weeks; d_A <mean A>R (lower97.5 <lower A>), d_B <mean B>R (lower97.5 <lower B>); calibration agreement <agreement>; ledger p <p>, BH q <q>. Never re-run; a different deferral time, a close-based skip, a different race or a market-on-close fill is a new idea with a new name, not a retry. | `results/<date>-v229-forward-verdict.md`, ledger `v229-deferred-entry` |
```

**Study `PASS`:** no closed row. Report to the partner that the PASS earns a follow-on deferred-entry-mode **spec** and ships nothing by itself; binding on that spec (partner, 2026-11-14): it carries `Edge: expectancy`, and its `Screen:` status needs the partner's explicit approval before it is written.

Then run the checks:

```bash
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
```

Expected: both PASS, 0 failed.

- [ ] **Step 8: Remove the cron entry**

```bash
R=/e/Documents/Private/Projects/Discord-Bot; SSH="bash $R/scripts/ops/ssh-hetzner.sh"
$SSH "crontab -l | grep -vF '# v229 deferred-entry pairs' | grep -vF v229_pairs_cron.sh | crontab -; crontab -l | grep -c v229 || true"
```

Expected: `0`. The pair log, rows and outputs under `/opt/swing-bot/data/v229/` stay on the VM as the record's raw data; nothing is deleted.

- [ ] **Step 9: Commit (two scoped commits)**

```bash
R=/e/Documents/Private/Projects/Discord-Bot
DOC=$(ls "$R"/docs/superpowers/results/*-v229-forward-verdict.md); DOC=${DOC#"$R"/}
git -C "$R" add "$DOC" docs/superpowers/results/v229/forward-verdict.json
git -C "$R" commit -m "docs(v229): forward verdict -- deferred entry on the live LONG book (V229-15)"
git -C "$R" add docs/superpowers/results/preregistration-ledger.jsonl docs/claude/backtest-methodology.md
git -C "$R" commit -m "docs(v229): ledger row v229-deferred-entry; weekly cron removed from the VM (V229-15)"
```

(On a `PASS`, `backtest-methodology.md` is unchanged and `git add` simply stages the ledger.)

Report to the controller: the study word, both arm verdicts, the ledger row with its BH q, the cron removal, and that the plan is ready for `/close-out` (to `implemented/` on a `PASS`, `no-lift/` otherwise).
