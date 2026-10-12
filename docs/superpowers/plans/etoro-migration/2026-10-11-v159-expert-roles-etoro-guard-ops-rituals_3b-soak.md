# v159 Four expert seats, a demo-only eToro guard, and the ops/UI rituals. Part 3b: `/soak` and the soak lock (ER13–ER14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task ER14" -A 400 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md` (§ C1)
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here. Split from part 3 only to keep that file under the 1500-line cap.

**Conventions for every task in this part** (same as part 2)

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals` (created in ER1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`; run Python tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>` and frontend specs as `npm --prefix "$WT/frontend" test -- --include <spec path relative to frontend/> --watch=false`.
- Hook-rule test code that names a protected branch uses `stable-1.9`, and is written through Edit/Write, never a Bash heredoc.
- Skill and agent tasks: write the source under `.claude/`, then `python "$WT/scripts/dev/sync_codex.py"`, and stage **only** the generated files of the skill or agent the task created or edited (`git -C "$WT" add .agents/skills/<name>` / `.codex/agents/<name>.toml`), never `git add -A .agents`.
- Every new or changed Python function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing for the files a task changed.
- Never run the skill eval suites (they cost real money); a task only creates the eval case directories.

# Phase C — ops and UI rituals (ER13–ER14 here; ER15–ER18 continue in part 4)

### Task ER13: `/soak` ritual and the generalised VM sampler

**Model:** sonnet — a slash-only skill, two bash scripts generalised from a template, and behaviour tests that run them under a stubbed `crontab`; the shell is small but its date and crontab logic must be exercised, not just grepped.

Spec § C1. `/soak` is slash-only (`disable-model-invocation: true`, the v155 `/screen` pattern) and turns a production soak into a pre-registered measurement: (1) clauses, thresholds, measurement definitions and the window go into a plan or results doc, committed before the first sample; (2) a razor-edge check per ratio clause; (3) a sampler cron on the VM, mirrored under `scripts/ops/`; (4) a pooled plus per-day verdict in `docs/superpowers/results/`; (5) on FAIL, diagnose from telemetry only, and a retry is a **new** pre-registration with a new attempt number.

This task fixes the **pre-registration block format** that ER14's hook rule reads. The sampler generalises the untracked `scripts/ops/v106_load_sampler.sh` / `install_v106_load_sampler_cron.sh` (read them as the template; **never stage, edit or commit them** — the v106 session owns them).

Block format (one block per document):

```
<!-- soak-prereg -->
window_start: YYYY-MM-DD
window_end: YYYY-MM-DD
<one clause per line>
<!-- /soak-prereg -->
```

Dates are UTC, the sampler's clock. From `window_start` on, ER14 denies any edit that changes the block.

**Files:**
- Create: `.claude/skills/soak/SKILL.md`
- Create: `scripts/ops/soak_sampler.sh`
- Create: `scripts/ops/install_soak_sampler_cron.sh`
- Create: `tests/scripts/test_soak_sampler_scripts.py`
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_2`; one test appended)
- Modify: `docs/claude/skills-tools.md` (skill-tier table after the `data-check` row ~l.113; the slash-only sentence ~l.123-125)
- Modify: `AGENTS.md` (the "Explicit-only rituals" paragraph ~l.250-260)
- Generated: `.agents/skills/soak/SKILL.md`, `.agents/skills/soak/agents/openai.yaml` (by `sync_codex.py`)

**Interfaces:**
- Consumes: existing `test_skill_shape._read_skill`, `TIER_2`, `MODEL_RUN_RITUALS`; the `prod-inspector` agent and `mirror-prod` skill (named in the body).
- Produces (ER14 relies on the first three):
  - the markers `<!-- soak-prereg -->` / `<!-- /soak-prereg -->`, and the lines `window_start: YYYY-MM-DD`, `window_end: YYYY-MM-DD` inside them;
  - `scripts/ops/soak_sampler.sh NAME START END` — NAME `^[a-z0-9][a-z0-9-]*$`, dates `YYYY-MM-DD` UTC; logs to `${SOAK_LOG_DIR:-/opt/swing-bot/logs}/soak_<NAME>.log`; exits 2 on a bad argument; after END removes its own crontab lines (`soak_sampler.sh NAME ` and `# soak sampler NAME `);
  - `scripts/ops/install_soak_sampler_cron.sh NAME START END [HOURS]` — HOURS default `13-20`; `BASE` default `/opt/swing-bot`; marker `# soak sampler NAME (installed by install_soak_sampler_cron.sh)`; cron line `* HOURS * * 1-5 /bin/bash BASE/scripts/ops/soak_sampler.sh NAME START END`.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_skill_shape.py`, add `"soak"` to `TIER_2` (keep every name already there):

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "result-digest", "handoff", "screen", "prereg", "data-check",
          "soak"}        # each ritual task appends its own name
```

Append at the end of the file:

```python
def test_soak_pins_the_prereg_block_the_hook_reads():
    """v159: _rule_soak_prereg_locked (guardrails.py) parses exactly this
    format; a drift here silently unlocks every soak."""
    meta, body = _read_skill("soak")
    assert meta.get("disable-model-invocation") == "true"
    for phrase in ("<!-- soak-prereg -->", "<!-- /soak-prereg -->",
                   "window_start: YYYY-MM-DD", "window_end: YYYY-MM-DD",
                   "One block per document", "razor-edge:", "soak_sampler.sh",
                   "install_soak_sampler_cron.sh", "new attempt number",
                   "`prod-inspector`", "`mirror-prod`", "docs/superpowers/results/"):
        assert phrase in body, phrase
    assert "## Trigger table" not in body and "\n## Lens\n" not in body
```

Create `tests/scripts/test_soak_sampler_scripts.py`:

```python
"""v159: the generalised soak sampler and its cron installer (/soak).

They run only on the VM. What is pinned is the shape an edit would silently
break, plus the date and crontab logic, run here under a stubbed crontab.
Generalised from the v106 load sampler, which its own session owns."""
import os
import pathlib
import shlex
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
SAMPLER = OPS / "soak_sampler.sh"
INSTALLER = OPS / "install_soak_sampler_cron.sh"
LINE = "* 13-20 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/soak_sampler.sh"


def _text(path):
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [SAMPLER, INSTALLER], ids=lambda p: p.name)
def test_strict_mode_lf_and_no_in_place_sed(path):
    assert "set -" in _text(path)
    assert b"\r" not in path.read_bytes()
    assert "sed -i" not in _text(path)


def test_the_sampler_logs_one_file_per_soak():
    text = _text(SAMPLER)
    assert 'LOG_DIR=${SOAK_LOG_DIR:-/opt/swing-bot/logs}' in text
    assert 'LOG="$LOG_DIR/soak_${NAME}.log"' in text


def test_the_installer_defaults_to_the_us_session_hours():
    text = _text(INSTALLER)
    assert "HOURS=${4:-13-20}" in text
    assert ('CRON_LINE="* $HOURS * * 1-5 /bin/bash '
            '$BASE/scripts/ops/soak_sampler.sh $NAME $START $END"') in text


def _working_bash(*paths):
    """A bash that resolves these host paths, or None. On Windows `bash` can be
    WSL's, which cannot see `C:/...`; Git for Windows' bash is tried next.
    (Same helper as tests/scripts/test_pitr_crons.py.)"""
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
    found = _working_bash(SAMPLER, INSTALLER, tmp_path)
    if found is None:
        pytest.skip("no bash that can see host paths")
    return found


def _run(bash, script, args, store, **env):
    """Run `script` with `crontab` stubbed as an exported function over `store`
    (a stub file is not executable on Windows)."""
    fn = (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}"; '
          f'else d=$(cat); printf "%s\\n" "$d" > "{store.as_posix()}"; fi; }}; '
          f'export -f crontab; bash "{script.as_posix()}" '
          + " ".join(shlex.quote(a) for a in args))
    return subprocess.run([bash, "-c", fn], env={**os.environ, **env},
                          capture_output=True, text=True, timeout=60)


def test_the_installer_is_idempotent_and_keeps_other_soaks(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/nightly.sh\n"
                     f"{LINE} other 2026-10-01 2026-10-09\n"
                     f"{LINE} v106-a4 2026-09-01 2026-09-05\n")
    for _ in range(2):
        out = _run(bash, INSTALLER, ["v106-a4", "2026-10-12", "2026-10-16"], store,
                   BASE="/opt/swing-bot")
        assert out.returncode == 0, out.stderr
    lines = store.read_text().splitlines()
    mine = [l for l in lines if "soak_sampler.sh v106-a4 " in l]
    assert mine == [f"{LINE} v106-a4 2026-10-12 2026-10-16"]
    assert lines.count("# soak sampler v106-a4 (installed by install_soak_sampler_cron.sh)") == 1
    assert f"{LINE} other 2026-10-01 2026-10-09" in lines
    assert "0 3 * * * /x/nightly.sh" in lines


def test_the_installer_takes_custom_hours(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("")
    out = _run(bash, INSTALLER, ["v106-a4", "2026-10-12", "2026-10-16", "14-21"], store,
               BASE="/opt/swing-bot")
    assert out.returncode == 0, out.stderr
    assert any(l.startswith("* 14-21 * * 1-5 ") for l in store.read_text().splitlines())


@pytest.mark.parametrize("args", [["V106;rm", "2026-10-12", "2026-10-16"],
                                  ["v106", "2026-1-2", "2026-10-16"],
                                  ["v106", "2026-10-12", "2026-10-16", "all day"]])
def test_the_installer_refuses_a_bad_argument(bash, tmp_path, args):
    store = tmp_path / "cron.txt"
    store.write_text("keep\n")
    assert _run(bash, INSTALLER, args, store).returncode == 2
    assert store.read_text() == "keep\n"


def test_the_sampler_removes_only_its_own_lines_after_the_window(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("# soak sampler v106-a4 (installed by install_soak_sampler_cron.sh)\n"
                     f"{LINE} v106-a4 2020-01-01 2020-01-02\n"
                     f"{LINE} v106-a4b 2020-01-01 2999-12-31\n")
    out = _run(bash, SAMPLER, ["v106-a4", "2020-01-01", "2020-01-02"], store,
               SOAK_LOG_DIR=tmp_path.as_posix())
    assert out.returncode == 0, out.stderr
    assert store.read_text().splitlines() == [f"{LINE} v106-a4b 2020-01-01 2999-12-31"]
    assert "done" in (tmp_path / "soak_v106-a4.log").read_text()


def test_the_sampler_does_nothing_before_the_window(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("keep\n")
    out = _run(bash, SAMPLER, ["v106-a4", "2999-01-01", "2999-01-05"], store,
               SOAK_LOG_DIR=tmp_path.as_posix())
    assert out.returncode == 0
    assert not (tmp_path / "soak_v106-a4.log").exists()
    assert store.read_text() == "keep\n"


def test_the_sampler_appends_one_block_inside_the_window(bash, tmp_path):
    store = tmp_path / "cron.txt"
    store.write_text("")
    out = _run(bash, SAMPLER, ["v106-a4", "2020-01-01", "2999-12-31"], store,
               SOAK_LOG_DIR=tmp_path.as_posix())
    assert out.returncode == 0
    log = (tmp_path / "soak_v106-a4.log").read_text()
    # vmstat/docker may be missing off the VM; their errors land in the log.
    assert log.startswith("=== ") and "loadavg=" in log


@pytest.mark.parametrize("args", [["Bad Name", "2020-01-01", "2020-01-02"],
                                  ["ok", "2020-1-1", "2020-01-02"], []])
def test_the_sampler_refuses_a_bad_argument(bash, tmp_path, args):
    store = tmp_path / "cron.txt"
    store.write_text("keep\n")
    out = _run(bash, SAMPLER, args, store, SOAK_LOG_DIR=tmp_path.as_posix())
    assert out.returncode == 2
    assert store.read_text() == "keep\n"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py`
Expected: FAIL — `test_every_skill_is_registered_in_exactly_one_tier`, `test_ritual_skills_are_slash_only` and `test_soak_pins_the_prereg_block_the_hook_reads` (no `.claude/skills/soak/SKILL.md`).

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_soak_sampler_scripts.py`
Expected: FAIL — `FileNotFoundError` on both scripts (the bash-driven tests skip only if no usable bash exists; on this machine Git for Windows' bash is found).

- [ ] **Step 3: Write the sampler**

Create `scripts/ops/soak_sampler.sh` (LF line endings):

```bash
#!/usr/bin/env bash
# One minute's sample of VM load for a pre-registered soak (the /soak skill,
# .claude/skills/soak/SKILL.md). Generalised from the v106 load sampler.
# Read-only. Appends one block to <log dir>/soak_<NAME>.log: loadavg, vmstat's
# 1 s us/sy/id/wa/st (st = hypervisor steal), per-container CPU/mem and the top
# host processes. Acts only on START..END (UTC dates) and removes its own
# crontab lines once END has passed.
# Usage: soak_sampler.sh NAME START END
set -uo pipefail
NAME=${1:-}
START=${2:-}
END=${3:-}
DATE_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
if ! [[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "soak_sampler: NAME must be lower-case letters, digits and hyphens" >&2
    exit 2
fi
if ! [[ "$START" =~ $DATE_RE && "$END" =~ $DATE_RE ]]; then
    echo "soak_sampler: START and END must be YYYY-MM-DD (UTC)" >&2
    exit 2
fi
TODAY=$(date -u +%Y-%m-%d)
LOG_DIR=${SOAK_LOG_DIR:-/opt/swing-bot/logs}
LOG="$LOG_DIR/soak_${NAME}.log"

if [[ "$TODAY" > "$END" ]]; then
    crontab -l 2>/dev/null | grep -vF "soak_sampler.sh $NAME " \
        | grep -vF "# soak sampler $NAME " | crontab -
    echo "soak $NAME done: crontab lines removed" >> "$LOG"
    exit 0
fi
[[ "$TODAY" < "$START" ]] && exit 0

{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) loadavg=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null)"
    echo "vmstat(1s): $(vmstat 1 2 | tail -1)   [r b swpd free buff cache si so bi bo in cs us sy id wa st]"
    /usr/bin/docker stats --no-stream --format '  {{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' 2>&1
    ps -eo pcpu,pmem,etimes,args --sort=-pcpu | head -7 | cut -c1-150 | sed 's/^/  /'
} >> "$LOG" 2>&1
exit 0
```

- [ ] **Step 4: Write the installer**

Create `scripts/ops/install_soak_sampler_cron.sh` (LF line endings):

```bash
#!/usr/bin/env bash
# Installs (idempotently) the crontab entry for one pre-registered soak (the
# /soak skill): scripts/ops/soak_sampler.sh NAME START END every minute of
# HOURS (UTC, default 13-20) on weekdays. The sampler acts only on START..END
# and removes its own lines after END. Generalised from the v106 installer.
#
# Run ON the VM, e.g. from a dev machine:
#   bash scripts/ops/ssh-hetzner.sh "bash -s -- NAME START END [HOURS]" < scripts/ops/install_soak_sampler_cron.sh
set -euo pipefail
NAME=${1:-}
START=${2:-}
END=${3:-}
HOURS=${4:-13-20}
DATE_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
if ! [[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "usage: install_soak_sampler_cron.sh NAME START END [HOURS] -- NAME is lower-case letters, digits and hyphens" >&2
    exit 2
fi
if ! [[ "$START" =~ $DATE_RE && "$END" =~ $DATE_RE ]]; then
    echo "install_soak_sampler_cron: START and END must be YYYY-MM-DD (UTC)" >&2
    exit 2
fi
if ! [[ "$HOURS" =~ ^[0-9]{1,2}(-[0-9]{1,2})?$ ]]; then
    echo "install_soak_sampler_cron: HOURS is a cron hour field such as 13-20" >&2
    exit 2
fi
BASE=${BASE:-/opt/swing-bot}

MARKER="# soak sampler $NAME (installed by install_soak_sampler_cron.sh)"
CRON_LINE="* $HOURS * * 1-5 /bin/bash $BASE/scripts/ops/soak_sampler.sh $NAME $START $END"

{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "soak_sampler.sh $NAME " || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
```

If the Write tool leaves CRLF on Windows, normalise both files: `python -c "import pathlib,sys; [pathlib.Path(p).write_bytes(pathlib.Path(p).read_bytes().replace(b'\r\n', b'\n')) for p in sys.argv[1:]]" "$WT/scripts/ops/soak_sampler.sh" "$WT/scripts/ops/install_soak_sampler_cron.sh"`.

- [ ] **Step 5: Write the skill**

Create `.claude/skills/soak/SKILL.md`:

````markdown
---
name: soak
description: "Run a production soak as a pre-registered measurement: clauses, thresholds and window committed before the first sample, a razor-edge check, the VM sampler, a pooled and per-day verdict. Invoked explicitly as /soak <name>, never model-triggered."
disable-model-invocation: true
---

# Soak

Arguments: `$ARGUMENTS` is the soak name: lower-case letters, digits and
hyphens, with the attempt number in it (`v106-attempt-4`). It names the
sampler log and the results doc.

## Step 1 — Read the authority

```bash
python scripts/dev/doc_section.py docs/claude/working-conventions.md "Scheduling far-off work" "Mirroring production changes back"
```

Exit code 2 means read the whole file.

## Step 2 — Pre-register before the window opens

Write the clauses, thresholds, measurement definitions and window into the
plan or results doc, and commit it **before the first sample**.
One block per document, in exactly this format (dates are UTC, the sampler's
clock):

```
<!-- soak-prereg -->
window_start: YYYY-MM-DD
window_end: YYYY-MM-DD
<one clause per line: metric, comparison, threshold, how it is measured>
<!-- /soak-prereg -->
```

From `window_start` on, the hook `_rule_soak_prereg_locked` denies any edit
that changes the block. The verdict cites the block by path; it never copies it.

## Step 3 — Razor-edge check

For each ratio clause, work out how many events would flip it at the expected
N. If fewer than five would, add a `razor-edge:` line under that clause, inside
the block, naming the count. v106 clause (c) flipped on two events in 180 scans.

## Step 4 — Sampler on the VM

Load `mirror-prod` first: a cron is a production change. The sampler ships in
the repo; deploy first if the VM checkout predates `scripts/ops/soak_sampler.sh`.

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s -- <name> <window_start> <window_end>" < scripts/ops/install_soak_sampler_cron.sh
```

An optional fourth argument sets the UTC cron hours (default: the US session).
It logs to `/opt/swing-bot/logs/soak_<name>.log` and removes its own crontab
lines after `window_end`. Read the log through `prod-inspector`, never raw.

## Step 5 — Verdict

`docs/superpowers/results/YYYY-MM-DD-<name>.md`: a pooled table (one row per
clause: threshold, measured value, N, PASS or FAIL) and a per-day table. A
razor-edge clause says so next to its verdict.

## Step 6 — On FAIL

Diagnose from telemetry only: the sampler log and the bot logs. A retry is a
new pre-registration with a new attempt number, in a new document, never an
edit of the old one.
````

- [ ] **Step 6: Registries and the Codex mirror**

`docs/claude/skills-tools.md`, skill-tier table, after the `data-check` row:

```markdown
| `soak` | 2 | slash-only (`/soak <name>`) | `working-conventions.md` — Step 1 reads the `Scheduling far-off work` and `Mirroring production changes back` sections with `doc_section.py` |
```

In the paragraph below the table, change `` `/handoff`, `/screen`, `/prereg` and `` + newline + `` `/data-check` also carry `` to:

```markdown
`/handoff`, `/screen`, `/prereg`, `/data-check` and `/soak` also carry
```

`AGENTS.md`, in the "Explicit-only rituals" paragraph, replace

```markdown
measurement, append the ledger row after it) and `data-check` (run
`validate_data.py` and report each cache's verdict from its output). `new-doc`
```

with

```markdown
measurement, append the ledger row after it), `data-check` (run
`validate_data.py` and report each cache's verdict from its output) and `soak`
(pre-register a VM soak's window and clauses between `<!-- soak-prereg -->`
markers before the first sample, run `scripts/ops/soak_sampler.sh` through its
installer, write a pooled and per-day verdict; the block is hook-locked once
its window opens). `new-doc`
```

Then:

```bash
python "$WT/scripts/dev/sync_codex.py"
```

Expected: writes `.agents/skills/soak/SKILL.md` and `.agents/skills/soak/agents/openai.yaml` (`allow_implicit_invocation: false`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/scripts/test_soak_sampler_scripts.py`
Expected: PASS (no skips on this machine).

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS.

Run: `wc -l "$WT/.claude/skills/soak/SKILL.md"`
Expected: ≤ 80.

- [ ] **Step 8: Commit**

`git -C "$WT" status --short scripts/ops` still lists the two untracked v106 originals if they were copied into the worktree; leave them unstaged.

```bash
git -C "$WT" add .claude/skills/soak .agents/skills/soak scripts/ops/soak_sampler.sh scripts/ops/install_soak_sampler_cron.sh tests/scripts/test_soak_sampler_scripts.py tests/hooks/test_skill_shape.py docs/claude/skills-tools.md AGENTS.md
git -C "$WT" commit -m "feat(v159): ER13 -- /soak ritual and the generalised VM sampler

Slash-only /soak: pre-register clauses, thresholds and window between
<!-- soak-prereg --> markers before the first sample, flag razor-edge ratio
clauses, install the sampler cron through mirror-prod, write a pooled and
per-day verdict, and retry only as a new attempt. soak_sampler.sh and
install_soak_sampler_cron.sh generalise the v106 pair (name-scoped log and
crontab lines, validated arguments, self-removal after the window); tests
run both under a stubbed crontab. The v106 originals stay with their session.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER14: `_rule_soak_prereg_locked`

**Model:** sonnet — a second total rule in the fail-open hook, following ER6's exact pattern (isinstance before every access, direct never-raises tests); the in-memory Edit replay and the hunk scan are fully specified below.

Spec § C1 "Hook": deny an Edit, Write or `apply_patch` to the block of a soak pre-registration whose window start date has come. The block is delimited by ER13's `<!-- soak-prereg -->` markers and carries `window_start: YYYY-MM-DD` (UTC). Owner: the `sre` row in `skills-tools.md`. The rule costs nothing when there are no markers: it reads only `.md` files, and stops at a substring test when the marker is absent.

Decisions the spec leaves to the plan, fixed here:
- **Locked from the start date itself** (`window_start <= today`, UTC): the sampler takes its first sample on `START` (ER13), so the window has opened on that day.
- **What counts as changing the block:** for Edit and Write, the rule replays the edit in memory on the on-disk text (`old_string` → `new_string`, honouring `replace_all`; or the whole `content`) and denies when the block afterwards differs or is gone. An `apply_patch` section cannot be replayed safely, so a hunk is denied when it removes or adds a line whose text is a line of the locked block, or adds a line directly after a block line other than the closing marker (an insertion inside the block). Edits outside the block, including right after the closing marker, pass.
- **A new file is never locked:** with nothing on disk there is no pre-registration to protect.
- Only the first block in a file is read (ER13's skill says one block per document).

**Files:**
- Modify: `.claude/hooks/guardrails.py` (`import datetime`; new soak block after ER6's eToro block, before the `# Codex edits files through apply_patch` comment; `_PATCH_PATH_RULES`; `_RULES["Edit"]`, `_RULES["Write"]`)
- Modify: `tests/hooks/test_guardrails.py` (`import datetime`; `_KEYS_THE_RULES_READ["Edit"]`; ER6's `test_patch_path_rules_put_the_etoro_deny_before_the_mirror_warn`; new tests appended)
- Unchanged: `tests/hooks/fixtures/payloads.json` — its `Edit` fixture already carries `old_string`, the one key this rule adds (the ledger lists the file in case it did not).
- Modify: `docs/claude/skills-tools.md` (the `sre` row of § Expert roles)
- Modify: `AGENTS.md` (the hook paragraph ER6 rewrote: one clause naming the new deny)

**Interfaces:**
- Consumes (ER6): `_deny`, `_rule_etoro_real_account`, `_rule_codex_mirror_reminder`, `_PATCH_PATH_RULES`, `_patch_sections`, `_rule_apply_patch` passing `{"file_path": path, "patch_body": section}`; test helpers `evaluate`, `_is_deny`. (ER13) the block format.
- Produces: `SOAK_PREREG_OPEN = "<!-- soak-prereg -->"`, `SOAK_PREREG_CLOSE = "<!-- /soak-prereg -->"`; `_utc_today() -> datetime.date` (module level, monkeypatchable); `_soak_block(text: str) -> tuple[str, datetime.date] | None`; `_rule_soak_prereg_locked(ti: object) -> dict | None` (total) in `_RULES["Edit"]`, `_RULES["Write"]` and `_PATCH_PATH_RULES`, each time after `_rule_etoro_real_account` and before `_rule_codex_mirror_reminder`; `_KEYS_THE_RULES_READ["Edit"] == {"file_path", "old_string", "new_string"}`.

- [ ] **Step 1: Write the failing tests**

All edits to `tests/hooks/test_guardrails.py` go through the Edit tool.

1a. Add `import datetime` as the first import (before `import importlib.util`).

1b. In `_KEYS_THE_RULES_READ`, the `Edit` entry becomes:

```python
    "Edit": {"file_path", "old_string", "new_string"},
```

1c. Replace ER6's `test_patch_path_rules_put_the_etoro_deny_before_the_mirror_warn` with:

```python
def test_patch_path_rules_put_the_etoro_deny_before_the_mirror_warn():
    assert guardrails._PATCH_PATH_RULES == (
        guardrails._rule_worktree_write, guardrails._rule_plan_doc_shape,
        _ETORO, guardrails._rule_soak_prereg_locked,
        guardrails._rule_codex_mirror_reminder)
    for tool in ("Edit", "Write"):
        rules = guardrails._RULES[tool]
        assert rules.index(_ETORO) < rules.index(guardrails._rule_codex_mirror_reminder)
```

1d. Append at the end of the file:

```python
# --- v159: a soak pre-registration locks once its window opens --------------

_SOAK = guardrails._rule_soak_prereg_locked
_OPEN, _CLOSE = "<!-- soak-prereg -->", "<!-- /soak-prereg -->"
_PAST, _FUTURE = "2020-01-01", "2999-01-01"
_CLAUSE_A = "clause a: p95 scan time under the limit, per scan"


def _prereg(start):
    return ("# v106 soak attempt 4\n\nIntro, per the /soak skill.\n\n"
            f"{_OPEN}\nwindow_start: {start}\nwindow_end: 2999-12-31\n"
            f"{_CLAUSE_A}\nclause b: no provider failover, per day\n{_CLOSE}\n\n"
            "## Results\n\npending\n")


@pytest.fixture
def soak_doc(tmp_path):
    def make(start):
        path = tmp_path / "2026-10-12-v106-soak-attempt-4.md"
        path.write_text(_prereg(start), encoding="utf-8")
        return path
    return make


def _edit(path, old, new):
    return {"file_path": str(path), "old_string": old, "new_string": new}


def _hunk(path, *lines):
    return {"file_path": str(path), "patch_body": "\n".join(("@@",) + lines) + "\n"}


def test_the_markers_are_the_ones_the_soak_skill_writes():
    assert guardrails.SOAK_PREREG_OPEN == _OPEN
    assert guardrails.SOAK_PREREG_CLOSE == _CLOSE


def test_soak_block_reads_the_block_and_its_window_start():
    block, start = guardrails._soak_block(_prereg("2026-10-12"))
    assert start == datetime.date(2026, 10, 12)
    assert block.startswith(_OPEN) and block.endswith(_CLOSE)
    assert _CLAUSE_A in block and "## Results" not in block


@pytest.mark.parametrize("text", [
    "no markers here",
    f"{_OPEN}\nwindow_start: 2026-10-12\n",              # never closed
    f"{_OPEN}\n{_CLAUSE_A}\n{_CLOSE}\n",                  # no window_start
    f"{_OPEN}\nwindow_start: 2026-13-40\n{_CLOSE}\n",     # not a date
    f"{_CLOSE}\n{_OPEN}\nwindow_start: 2026-10-12\n",     # close before open
])
def test_soak_block_is_none_when_it_cannot_be_read(text):
    assert guardrails._soak_block(text) is None


def test_editing_a_clause_after_the_window_opened_is_denied(soak_doc):
    path = soak_doc(_PAST)
    out = evaluate({"tool_name": "Edit", "tool_input": _edit(
        path, "under the limit", "under a looser limit")})
    assert _is_deny(out)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert _PAST in reason and "new attempt number" in reason


def test_moving_the_window_start_is_denied(soak_doc):
    path = soak_doc(_PAST)
    assert _is_deny(_SOAK(_edit(path, f"window_start: {_PAST}", f"window_start: {_FUTURE}")))


def test_editing_outside_the_block_is_allowed(soak_doc):
    path = soak_doc(_PAST)
    assert _SOAK(_edit(path, "pending", "FAIL: clause a on three of five days")) is None
    assert _SOAK(_edit(path, "Intro,", "Intro, revised,")) is None


def test_a_block_whose_window_has_not_opened_is_editable(soak_doc):
    path = soak_doc(_FUTURE)
    assert _SOAK(_edit(path, "under the limit", "under a looser limit")) is None


def test_the_block_locks_on_its_start_day(soak_doc, monkeypatch):
    path = soak_doc("2026-10-12")
    monkeypatch.setattr(guardrails, "_utc_today", lambda: datetime.date(2026, 10, 11))
    assert _SOAK(_edit(path, "under the limit", "looser")) is None
    monkeypatch.setattr(guardrails, "_utc_today", lambda: datetime.date(2026, 10, 12))
    assert _is_deny(_SOAK(_edit(path, "under the limit", "looser")))


def test_a_write_is_judged_on_the_block_it_leaves(soak_doc):
    path = soak_doc(_PAST)
    before = path.read_text(encoding="utf-8")
    assert _SOAK({"file_path": str(path), "content": before.replace("pending", "PASS")}) is None
    assert _is_deny(_SOAK({"file_path": str(path),
                           "content": before.replace("under the limit", "x")}))
    assert _is_deny(_SOAK({"file_path": str(path), "content": "# emptied\n"}))


def test_replace_all_reaches_into_the_block(soak_doc):
    path = soak_doc(_PAST)
    # The first "per " is in the intro; the others are inside the block.
    assert _SOAK(_edit(path, "per ", "each ")) is None
    assert _is_deny(_SOAK({**_edit(path, "per ", "each "), "replace_all": True}))


def test_a_patch_that_changes_a_block_line_is_denied(soak_doc):
    path = soak_doc(_PAST)
    assert _is_deny(_SOAK(_hunk(path, f"-{_CLAUSE_A}", "+clause a: anything")))


def test_a_patch_that_inserts_a_line_inside_the_block_is_denied(soak_doc):
    path = soak_doc(_PAST)
    assert _is_deny(_SOAK(_hunk(path, " window_end: 2999-12-31", "+clause z: added late",
                                f" {_CLAUSE_A}")))


def test_a_patch_after_the_block_is_allowed(soak_doc):
    path = soak_doc(_PAST)
    assert _SOAK(_hunk(path, f" {_CLOSE}", "+", "+## Notes")) is None
    assert _SOAK(_hunk(path, " ## Results", " ", "-pending", "+PASS")) is None


def test_apply_patch_reaches_the_soak_rule(soak_doc):
    path = soak_doc(_PAST)
    patch = (f"*** Begin Patch\n*** Update File: {path.as_posix()}\n@@\n"
             f"-window_start: {_PAST}\n+window_start: {_FUTURE}\n*** End Patch\n")
    assert _is_deny(evaluate({"tool_name": "apply_patch", "tool_input": {"command": patch}}))


def test_a_new_file_is_never_locked(tmp_path):
    path = tmp_path / "new-soak.md"
    assert _SOAK({"file_path": str(path), "content": _prereg(_PAST)}) is None


def test_the_soak_rule_runs_on_edit_write_and_patches_before_the_mirror_warn():
    for rules in (guardrails._RULES["Edit"], guardrails._RULES["Write"],
                  guardrails._PATCH_PATH_RULES):
        rules = list(rules)
        assert rules.index(_ETORO) < rules.index(_SOAK)
        assert rules.index(_SOAK) < rules.index(guardrails._rule_codex_mirror_reminder)


@pytest.mark.parametrize("ti", [
    None, 3, "x", [], b"x", {}, {"file_path": None}, {"file_path": 7},
    {"file_path": ""}, {"file_path": "/no/such/dir/x.md", "content": "y"},
    {"file_path": "notes.txt", "content": "y"}, {"file_path": "bad\x00name.md"},
])
def test_the_soak_rule_never_raises_on_malformed_input(ti):
    # Called directly: evaluate() would swallow an exception and allow.
    assert _SOAK(ti) is None


@pytest.mark.parametrize("extra", [
    {}, {"content": None}, {"content": 7}, {"old_string": None, "new_string": "x"},
    {"old_string": "under", "new_string": 5}, {"old_string": "", "new_string": "x"},
    {"patch_body": None}, {"patch_body": 7}, {"patch_body": ""},
])
def test_the_soak_rule_never_raises_on_a_locked_doc_with_odd_fields(soak_doc, extra):
    path = soak_doc(_PAST)
    assert _SOAK({"file_path": str(path), **extra}) is None


def test_the_soak_rule_ignores_a_directory_named_like_markdown(tmp_path):
    folder = tmp_path / "looks-like.md"
    folder.mkdir()
    assert _SOAK({"file_path": str(folder), "content": "x"}) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_guardrails.py`
Expected: FAIL — `AttributeError: ... '_rule_soak_prereg_locked'` at module import of the test (`_SOAK = ...`), so every test in the file errors.

- [ ] **Step 3: Implement the rule**

In `.claude/hooks/guardrails.py`, add `import datetime` to the stdlib imports (alphabetically, before `import glob`). Then insert this block directly **after** ER6's eToro block (after `_rule_etoro_real_account`) and **before** the comment `# Codex edits files through apply_patch, whose tool_input.command is the patch`:

```python
# --- v159: a soak pre-registration is locked once its window opens ----------
# The /soak skill (.claude/skills/soak/SKILL.md) commits a soak's clauses,
# thresholds and window between these markers before the first sample. From
# window_start on (UTC, the sampler's clock) an edit that changes the block is
# denied: a retry is a new pre-registration with a new attempt number. Total,
# like the eToro rule, because evaluate() fails open on any exception. Owner:
# the sre row of docs/claude/skills-tools.md.
SOAK_PREREG_OPEN = "<!-- soak-prereg -->"
SOAK_PREREG_CLOSE = "<!-- /soak-prereg -->"
_SOAK_START_RE = re.compile(r"^window_start:[ \t]*(\d{4}-\d{2}-\d{2})[ \t]*$",
                            re.MULTILINE)
_HUNK_HEADER_RE = re.compile(r"^@@.*$", re.MULTILINE)


def _utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


def _soak_block(text: str):
    """(block text, window_start) for the first soak pre-registration in
    `text`, markers included; None when there is none or it cannot be read."""
    start = text.find(SOAK_PREREG_OPEN)
    end = text.find(SOAK_PREREG_CLOSE, start) if start >= 0 else -1
    if end < 0:
        return None
    block = text[start:end + len(SOAK_PREREG_CLOSE)]
    match = _SOAK_START_RE.search(block)
    if match is None:
        return None
    try:
        return block, datetime.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _read_markdown(path: str) -> str | None:
    """The text of an existing .md file, else None. Pre-registrations live in
    plan and results docs, so nothing else is ever read."""
    if not path.endswith(".md"):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _text_after_edit(ti: dict, before: str) -> str | None:
    """The whole file after a Write (`content`) or an Edit (`old_string` ->
    `new_string`, honouring `replace_all`); None for anything else."""
    content = ti.get("content")
    if isinstance(content, str):
        return content
    old, new = ti.get("old_string"), ti.get("new_string")
    if not (isinstance(old, str) and old and isinstance(new, str)):
        return None
    count = -1 if ti.get("replace_all") is True else 1
    return before.replace(old, new, count)


def _hunk_touches(lines: list, locked: set) -> bool:
    """A hunk changes a locked line, or adds one right after a block line
    other than the closing marker (an insertion inside the block)."""
    inside = False
    for line in lines:
        mark, text = line[:1], line[1:].strip()
        if mark in ("+", "-") and text in locked:
            return True
        if mark == "+" and inside:
            return True
        if mark in (" ", "-"):
            inside = text in locked and text != SOAK_PREREG_CLOSE
    return False


def _patch_touches_block(body: str, block: str) -> bool:
    locked = {line.strip() for line in block.splitlines() if line.strip()}
    return any(_hunk_touches(hunk.splitlines(), locked)
               for hunk in _HUNK_HEADER_RE.split(body))


def _soak_edit_touches(ti: dict, before: str, block: str) -> bool:
    body = ti.get("patch_body")
    if isinstance(body, str):
        return _patch_touches_block(body, block)
    after = _text_after_edit(ti, before)
    if after is None:
        return False
    found = _soak_block(after)
    return found is None or found[0] != block


def _rule_soak_prereg_locked(ti: object):
    """Deny an edit that changes a soak pre-registration whose window has
    opened. Total: returns None for anything it cannot read, never raises."""
    if not isinstance(ti, dict):
        return None
    path = ti.get("file_path")
    if not isinstance(path, str) or not path:
        return None
    before = _read_markdown(path)
    if before is None or SOAK_PREREG_OPEN not in before:
        return None
    found = _soak_block(before)
    if found is None or found[1] > _utc_today():
        return None
    if not _soak_edit_touches(ti, before, found[0]):
        return None
    return _deny(
        f"Denied: the soak pre-registration in {path} is locked -- its window "
        f"opened on {found[1].isoformat()} (UTC). A retry is a new "
        "pre-registration with a new attempt number, never an edit of this one "
        "(/soak, .claude/skills/soak/SKILL.md).")
```

- [ ] **Step 4: Register it**

Replace ER6's `_PATCH_PATH_RULES` assignment (its comment stays) with:

```python
_PATCH_PATH_RULES = (_rule_worktree_write, _rule_plan_doc_shape,
                     _rule_etoro_real_account, _rule_soak_prereg_locked,
                     _rule_codex_mirror_reminder)
```

In `_RULES`, the `Edit` and `Write` entries become:

```python
    "Edit": [_rule_worktree_write, _rule_etoro_real_account,
             _rule_soak_prereg_locked, _rule_codex_mirror_reminder],
    "Write": [_rule_worktree_write, _rule_plan_doc_shape, _rule_etoro_real_account,
              _rule_soak_prereg_locked, _rule_codex_mirror_reminder],
```

`_rule_soak_prereg_locked` must be defined before `_PATCH_PATH_RULES` and `_RULES` (Step 3 places it there).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_guardrails.py`
Expected: PASS, `0 failed`, `0 xfailed`. `test_fixture_payloads_are_all_silently_allowed` still passes: the `Edit` fixture's `swingbot/config.py` is not `.md`, and the `Write` fixture's `scratch/notes.md` does not exist.

Run: `python -m radon cc -s -n C "$WT/.claude/hooks/guardrails.py"`
Expected: no output (`_hunk_touches` and `_rule_soak_prereg_locked` are the largest new functions, both A or B).

Smoke the live entry point once against a throwaway file in the scratchpad (it is outside every repo, so no other rule fires):

```bash
python -c "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('<!-- soak-prereg -->\nwindow_start: 2020-01-01\nclause a: x\n<!-- /soak-prereg -->\n', encoding='utf-8')" "$SCRATCH/soak-smoke.md"
python -c "import json,sys; print(json.dumps({'tool_name':'Edit','tool_input':{'file_path':sys.argv[1],'old_string':'clause a: x','new_string':'clause a: y'}}))" "$SCRATCH/soak-smoke.md" | python "$WT/.claude/hooks/guardrails.py"
```

(`$SCRATCH` is the session scratchpad directory.) Expected: one JSON line with `"permissionDecision": "deny"` and `new attempt number` in the reason.

- [ ] **Step 6: Owner note and the Codex mirror**

`docs/claude/skills-tools.md`, § Expert roles: the `sre` row (from ER2) becomes:

```markdown
| `sre` | sonnet | Hetzner VM: soak criteria and razor-edge clauses, yfinance/Alpaca failover, cron and scheduling, logs and alerting, backup and PITR, capacity. Owns `_rule_soak_prereg_locked` (the `/soak` pre-registration lock in `.claude/hooks/guardrails.py`); it stays while soaks are run |
```

The row must still begin `` | `sre` | sonnet | `` (`test_reviewer_model_is_recorded_in_the_roles_table`).

`AGENTS.md`, in the hook paragraph ER6 wrote, replace

```markdown
or `ETORO_REAL_SIGNOFF` non-empty). It warns on bare `pytest`, `cat` of the
```

with

```markdown
or `ETORO_REAL_SIGNOFF` non-empty), and an edit that changes a soak
pre-registration block (`<!-- soak-prereg -->`) once its `window_start` has
come (`_rule_soak_prereg_locked`). It warns on bare `pytest`, `cat` of the
```

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py`
Expected: PASS.

Run: `python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git -C "$WT" add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py docs/claude/skills-tools.md AGENTS.md
git -C "$WT" commit -m "feat(v159): ER14 -- hook locks a soak pre-registration once its window opens

_rule_soak_prereg_locked (total, never raises) denies an Edit, Write or
apply_patch that changes the <!-- soak-prereg --> block of a .md file whose
window_start (UTC) has come: Edits and Writes are replayed in memory and
the block compared; patch hunks are denied when they touch or insert into
a block line. Text outside the block and new files pass. Registered on
Edit, Write and the apply_patch path rules, before the mirror warn. Owner:
the sre row of skills-tools.md.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

