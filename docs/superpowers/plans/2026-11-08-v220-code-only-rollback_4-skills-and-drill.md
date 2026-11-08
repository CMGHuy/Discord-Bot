# v220 — Code-only rollback, Part 4: skills, release and the scratch-stack drill (V220-15, V220-17, V220-18)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the `/rollback` skill and the `/deploy` refusal with their Codex mirror (V220-15), the bot patch release (V220-17), and the drill on a scratch compose project on the VM that records its result in a new `## Code-only rollback (v220)` section of `docs/deploy/DB_RESTORE.md` (V220-18). V220-16 moved to v221 as V221-4, which adds the comparison table under the heading V220-18 creates.

Binding facts for this part (from Parts 3/3b and the code brief):

- **The skill reaches the VM only through** `bash scripts/ops/ssh-hetzner.sh`, and always takes `rollback_code.sh` from `origin/main` with `git show` first (index "How the skill reaches the VM"): a rolled-back checkout may be a pre-v220 tree that lacks the script.
- **`rollback_code.sh` CLI** (V220-9/9b/10): `--resolve <target>`, `--candidates`, `<sha40> <image> --dry-run|--i-mean-it [--reason TEXT] [--keep-refresher] [--allow-writer-drift]`, `--release --dry-run|--i-mean-it`. Exit `0` pass, `1` failed (after an automatic restore on the rollback path), `2` refused, `3` no-op / no hold. Env `ROLLBACK_APP_DIR`, `ROLLBACK_TOOLS_REF`, `ROLLBACK_DRILL=1`, `ROLLBACK_FORCE_SMOKE_FAIL=1` (only with the drill flag). `--keep-refresher` keeps the refresher **stopped**. The writer refusal text contains `market-data writer differs` and `--allow-writer-drift` (V220-6b).
- **Drill mode** (V220-9b/10): no pgBackRest backup, `admin` (plus the refresher) without `bot`, no heartbeat check; the release fast-forwards the scratch checkout and runs `alembic upgrade head` in the admin container instead of `deploy.sh`. The stack is chosen by the caller's `COMPOSE_PROJECT_NAME`/`COMPOSE_FILE`; the override file lives **outside** the checkout.
- **`hold_status.py`** (V220-12): `--line | --refresh [--if-stale] [--cache PATH]`; the hook line starts `HOLD     : deploy held by rollback to`.
- **Skill shape and citation tests** (`tests/hooks/test_skill_shape.py`, `tests/hooks/test_skill_citations.py`, suite `dev-setup`): a skill sits in exactly one tier set (`TIER_2` for slash-only rituals, which must carry `disable-model-invocation: true`); at most 80 lines; no bare threshold (`= 2`, `>= 3`, `5R`, `3pp`); every backticked word that contains `/` and ends in `.py/.md/.json/.jsonl/.sh/...` must be a **tracked** file unless it starts with `logs/`, `data/`, `market_data/` or `.superpowers/` or carries a template mark (`<`, `>`, `*`, `{`, `}`, `$`, `=`, `://`), and every backticked `UPPER_SNAKE` word must occur in `swingbot/`, `scripts/` or `tests/`. Runtime paths such as the hold file therefore appear only in plain text or inside fenced blocks (the lint skips fences).
- **Codex mirror:** `python scripts/dev/sync_codex.py` regenerates `.agents/skills/<name>/SKILL.md` and `agents/openai.yaml`; `--check` must pass; `AGENTS.md` must name every skill.

# Phase 4 — Skills, release, drill

### Task V220-15: `/rollback` skill, `/deploy` refusal, Codex mirror

**Model:** sonnet — skill prose from the fixed CLI contract

**Files:**
- Create: `.claude/skills/rollback/SKILL.md`
- Modify: `.claude/skills/deploy/SKILL.md` (Step 3 opens with the hold refusal)
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_2` gains `"rollback"`; two new tests)
- Modify: `AGENTS.md` (explicit-only rituals list, ~l247-249)
- Modify: `docs/claude/skills-tools.md` (skills table row and the slash-only sentence, ~l149-170)
- Create (generated): `.agents/skills/rollback/SKILL.md`, `.agents/skills/rollback/agents/openai.yaml`
- Modify (generated): `.agents/skills/deploy/SKILL.md`

**Interfaces:**
- Consumes: the `rollback_code.sh` CLI and exit codes (V220-9, V220-9b, V220-10); the picker rows `{"label","sha","kind","bot_version","plans","above_floor"}` (V220-2b, via `--candidates`); `scripts/dev/hold_status.py --refresh | --line` and the `HOLD` line (V220-12); the CI `hold` job (V220-11) and the `deploy/deploy.sh` guard (V220-12), named only.
- Produces: skill `rollback` (`disable-model-invocation: true`, Tier 2); `/deploy` refuses while a hold is set. No later task consumes a symbol from here; V220-18 runs the script directly with the drill env, not through the skill.

Decisions this task fixes:

- **Two `AskUserQuestion` gates, always:** before adding `--allow-writer-drift` (recommended answer: stop) and before `--i-mean-it` (rollback and release alike). Only the partner's answer is consent; a dry run never counts as one.
- **Stable points need nothing from v221:** a `stable-…` target resolves through its manifest `git_sha` or its git tag (V220-1's `_manifest_sha`), which every existing point has.
- **The skill never summarises the script's report**: it shows the output (plan, refusals, window report) as printed. The release window report is the only place a dropped field becomes visible.
- `docs/claude/skills-tools.md` and `tests/hooks/test_skill_shape.py` are edited here although the ledger row names only the skill files: the shape test fails on a skill missing from its tier sets, and the skills table lists every Tier 2 ritual. No other v220 task touches either file.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_skill_shape.py`, extend the `TIER_2` set (keep its trailing comment) so its second line reads:

```python
          "result-digest", "handoff", "screen", "prereg", "data-check", "replicate-prod-db",
          "rollback"}        # each ritual task appends its own name
```

Append at the end of the file:

```python
def test_rollback_skill_runs_main_s_script_and_asks_before_every_override():
    """v220: the checkout may be an older target without the script, so it
    always comes from origin/main; the partner answers before the writer
    override and before anything changes."""
    meta, body = _read_skill("rollback")
    assert meta.get("disable-model-invocation") == "true"
    assert "bash scripts/ops/ssh-hetzner.sh" in body
    assert "git show origin/main:scripts/ops/rollback_code.sh" in body
    for flag in ("--resolve", "--candidates", "--dry-run", "--release"):
        assert flag in body, flag
    assert "Ask with `AskUserQuestion` before adding `--allow-writer-drift`" in body
    assert body.count("Ask with `AskUserQuestion` before `--i-mean-it`") == 2   # rollback and release
    assert "market-data writer differs" in body
    assert "manifest `git_sha` or its git tag" in body
    assert "scripts/ops/restore_stable.sh" in body and "scripts/ops/rollback_to.sh" in body
    assert "alembic upgrade" not in body.lower()


def test_deploy_skill_refuses_while_a_rollback_holds_deploys():
    _, body = _read_skill("deploy")
    step3 = body[body.index("## Step 3"):body.index("## Step 4")]
    assert "deploy_hold.json" in step3 and "/rollback --release" in step3
    assert step3.index("deploy_hold.json") < step3.index("git push origin")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — `test_every_skill_is_registered_in_exactly_one_tier` (the set has `rollback`, the disk has not), and both new tests (`FileNotFoundError` for `rollback`; no `deploy_hold.json` in `deploy`).

- [ ] **Step 3: Create the skill**

Create `.claude/skills/rollback/SKILL.md` exactly (the outer fence uses four backticks only because the file holds a three-backtick block):

````markdown
---
name: rollback
description: "Code-only rollback -- put the VM's checkout and bot image back to an earlier main commit while keeping every trade and data row, and hold deploys until /rollback --release. Invoked explicitly as /rollback [target] [--release], never model-triggered."
disable-model-invocation: true
---

# Rollback (code only, keeps every trade)

## Step 1 — Read the authority, pick the path

`docs/deploy/DB_RESTORE.md` and the header of `scripts/ops/rollback_code.sh`.
This skill is the checklist. It keeps every trade, plan, journal row and
balance point: Postgres contents, the db container, `.env` values and the
market data cache are never touched, and no schema migration runs. If the
partner wants the data back too, this is the wrong path: stop and name
`scripts/ops/restore_stable.sh` (a stable point) or `scripts/ops/rollback_to.sh`
(a point in time).

## Step 2 — Always run main's script

The VM checkout may be an older target that lacks the script, so every call
takes it from `origin/main` first. `RB <args>` below means:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && runuser -u deploy -- git fetch -q origin main && runuser -u deploy -- git show origin/main:scripts/ops/rollback_code.sh > backups/rollback_code.sh && bash backups/rollback_code.sh <args>"
```

Exit codes: 0 pass, 1 failed (previous code and image already restored),
2 refused (nothing changed), 3 no-op. Show the partner the output as printed.

## Step 3 — Resolve the target

- Argument given (stable point, sha, `vNNN`, `vNNN-before`, `vNNN-after`,
  `bot-A.B.C`, UTC date): `RB --resolve <target>`. A refusal lists
  candidates; offer them with `AskUserQuestion`.
- No argument: `RB --candidates`, then `AskUserQuestion` with the newest rows
  whose `above_floor` is true, each labelled with bot version and plan ids;
  "Other" accepts any form above.
- A stable point resolves through its manifest `git_sha` or its git tag, so
  points made before v221 work; nothing here needs newer manifest fields.

## Step 4 — Dry run

Ask the partner for a one-line reason (it goes into the hold), then
`RB <sha> <image> --dry-run --reason "<reason>"`.

- Exit 3: already running there; stop.
- Exit 2 naming "market-data writer differs": Ask with `AskUserQuestion` before adding `--allow-writer-drift`,
  recommending to stop: the refresher then stays stopped, the admin may
  still write the cache, and the cache never self-heals
  (`docs/claude/known-traps.md`). Only on a yes, re-run the dry run with it.
- Any other exit 2: show the refusals and stop. Never work around one.
- Exit 0: show the plan (from and to, refresher, migrations, warnings).

## Step 5 — Execute on the partner's word only

Ask with `AskUserQuestion` before `--i-mean-it`, quoting from/to sha and image.
On a yes: `RB <sha> <image> --i-mean-it --reason "<reason>"` with the dry run's
flags. It takes a pgBackRest diff backup, writes the hold, switches checkout
and image (no Alembic), smoke-checks for up to three minutes, and on failure
restores the previous code and image by itself (exit 1: report and stop).
`/rollback <other target>` while held replaces the hold (Steps 3 to 5).

## Release (`/rollback --release`)

`RB --release --dry-run`, show it, Ask with `AskUserQuestion` before `--i-mean-it`, then
`RB --release --i-mean-it`. It removes the hold, checks out main, runs
`deploy/deploy.sh` with main's image, appends a release line and prints the
window report (rows the old code re-saved, keys dropped): show it verbatim.
Exit 3 means there was no hold. A failed release leaves the hold removed;
relay `deploy/deploy.sh`'s own message.

## The gate

Rolled back: `python scripts/dev/hold_status.py --refresh` then `--line`
shows the hold and the VM's `docker compose ps` shows admin healthy.
Released: no `HOLD` line. Nothing changed on the VM is missing from
`git log` (`mirror-prod`).
````

- [ ] **Step 4: Add the refusal to `/deploy`**

In `.claude/skills/deploy/SKILL.md`, insert directly under the `## Step 3 — Build and deploy` heading (above "Normal path — CI builds the image"):

````markdown
**First, the deploy hold (v220).** While a code-only rollback holds deploys,
this skill refuses. Check the VM:

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/backups/deploy_hold.json 2>/dev/null || echo 'no deploy hold'"
```

A hold printed here (or a `HOLD` line at session start) means stop: deploying
would move the VM off the rollback target. Point the partner at
`/rollback --release`. A push while held is harmless but deploys nothing: the
CI `hold` job skips `cleanup` and `deploy`, and `deploy/deploy.sh` exits before
its `git reset`.

````

(The hold path stays inside the fenced block and the inline `deploy_hold.json` span has no `/`, so the citation lint ignores both.)

- [ ] **Step 5: Register the skill in the docs and `AGENTS.md`**

`docs/claude/skills-tools.md`: insert below the `backup-pull` row of the skills table:

```markdown
| `rollback` | 2 | slash-only (`/rollback [target] [--release]`) | none — Step 1 reads `docs/deploy/DB_RESTORE.md` and the header of `scripts/ops/rollback_code.sh`, not `docs/claude/` |
```

and in the paragraph under the table replace `` `/backup-pull`, `/result-digest`, `/handoff`, `/screen`, `` with `` `/backup-pull`, `/rollback`, `/result-digest`, `/handoff`, `/screen`, ``.

`AGENTS.md` (explicit-only rituals paragraph): replace

```text
`deploy` (Hetzner deploy
sequence), `stable-snapshot` (pin a known-good point),
```

with

```text
`deploy` (Hetzner deploy
sequence; refuses while a rollback holds deploys), `stable-snapshot` (pin a known-good point),
`rollback` (code-only rollback that keeps every trade; holds deploys until `--release`; asks before
`--allow-writer-drift` and before `--i-mean-it`),
```

Read the lines first (`grep -n "Explicit-only rituals" -A 4 AGENTS.md`); if the wrap differs, keep the wording and wrap at the same width.

- [ ] **Step 6: Regenerate the Codex mirror**

```bash
python scripts/dev/sync_codex.py
python scripts/dev/sync_codex.py --check
```

Expected: the first writes `.agents/skills/rollback/SKILL.md` and `.agents/skills/rollback/agents/openai.yaml` (`allow_implicit_invocation: false`) and rewrites `.agents/skills/deploy/SKILL.md`; `--check` exits 0. Never hand-edit the generated files.

- [ ] **Step 7: Run the tests to verify they pass**

Run each:
- `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
- `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
- `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`

Expected: `0 failed` each. A citation finding names the word: un-backtick a runtime path or move it into a fence; never add it to `tests/hooks/skill_citation_allowlist.txt`. If `test_new_skills_restate_no_thresholds` fires, reword the number in words; never move the skill to `GRANDFATHERED`. If the 80-line budget fires, tighten prose in Steps 3–4 and keep every phrase the new test asserts.

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/rollback/SKILL.md .claude/skills/deploy/SKILL.md tests/hooks/test_skill_shape.py AGENTS.md docs/claude/skills-tools.md .agents/skills/rollback .agents/skills/deploy/SKILL.md
git commit -m "feat(v220): /rollback skill (asks before --allow-writer-drift and --i-mean-it), /deploy refuses while held, Codex mirror"
```

### Task V220-17: Release: bot patch, version history

**Model:** haiku — fixed `VERSION.json` bump and regeneration

**Files:**
- Modify: `VERSION.json` (`bot` patch +1, `bot_updated`)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)
- Test: `tests/scripts/test_build_version_matrix.py` (existing; `test_the_committed_file_matches_the_current_generator` pins `current` to `VERSION.json`)

**Interfaces:**
- Consumes: V220-1..V220-15 merged into the worktree branch (the bump describes the whole change; index Parallelisation).
- Produces: nothing a later task consumes. V220-18 runs after the merge to `main` and only reads the version.

Decisions this task fixes:

- **Bot patch only** (header `**Bump:** bot patch`): no `ui` change, no `ui_updated` change. The planner and VM scripts are ops tooling; `rollback_smoke` ships in the image but changes no bot behaviour. The new version is read from `VERSION.json` at the time of the task (`bot` was `2.17.3` when the plan was written; another plan may have moved it): patch = last part + 1.
- Order per `docs/claude/working-conventions.md` § How: bump commit first, then regenerate, then commit the artifact. Regenerating before the bump commit records `"commit": "uncommitted"`.

- [ ] **Step 1: Write the failing check**

The existing generator test is the check. Before touching anything, confirm it is green against the current version, so a red run after Step 3 can only mean the regeneration is missing:

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: `0 failed`.

Then pin the bump itself with a throwaway assertion run (not committed), which fails until Step 2:

```bash
python - <<'PY'
import json, subprocess
old = json.loads(subprocess.run(["git", "show", "HEAD:VERSION.json"], capture_output=True, text=True, check=True).stdout)
new = json.load(open("VERSION.json", encoding="utf-8"))
a, b, c = (int(x) for x in old["bot"].split("."))
assert new["bot"] == f"{a}.{b}.{c + 1}", (old["bot"], new["bot"])
assert new["ui"] == old["ui"] and new["ui_updated"] == old["ui_updated"]
assert new["bot_updated"] != old["bot_updated"]
print("bump ok:", old["bot"], "->", new["bot"])
PY
```

Expected now: `AssertionError` (nothing bumped yet).

- [ ] **Step 2: Bump `VERSION.json`**

Set `bot` to the next patch and `bot_updated` to the current UTC time as `YYYY-MM-DD HH-MM-SS` (compute it with `date -u +"%Y-%m-%d %H-%M-%S"`; Git Bash has no timezone data, `-u` is exact). Leave `ui` and `ui_updated` as they are. With `bot` at `2.17.3`, the file becomes:

```json
{
  "ui": "1.40.3",
  "bot": "2.17.4",
  "ui_updated": "2026-11-06 16-35-41",
  "bot_updated": "<date -u output>"
}
```

(The `ui` values shown are the ones on disk when the plan was written; keep whatever the file holds.)

Re-run the Step 1 assertion snippet. Expected: `bump ok: 2.17.3 -> 2.17.4` (or the actual pair).

- [ ] **Step 3: Commit the bump**

```bash
git add VERSION.json
git commit -m "release(bot): <new bot version> -- code-only rollback: /rollback, deploy hold, rollback_smoke (v220)"
```

- [ ] **Step 4: Regenerate the version history and verify**

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: `swingbot/admin/version_history.json` changes (its `current` pair now carries the new bot version and the release commit, not `"uncommitted"`); `0 failed`. Check with `grep -n '"uncommitted"' swingbot/admin/version_history.json` — expected: no output.

- [ ] **Step 5: Commit the artifact**

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <new bot version> -- code-only rollback: /rollback, deploy hold, rollback_smoke (v220)"
```

### Task V220-18: Scratch-stack drill: rollback, forced smoke failure, release

**Model:** sonnet — runs the shipped scripts on a scratch project and records the result

**Files:**
- Create: `deploy/drill/rollback-drill.override.yml`
- Test: `tests/scripts/test_rollback_drill_override.py` (new, suite `tooling`; not in the ledger row, added so the override carries a test; no other task touches it)
- Modify: `docs/deploy/DB_RESTORE.md` (new last section `## Code-only rollback (v220)` with `### Drill <date> (v220 V220-18)`)
- Scratch only (session scratchpad, piped to the VM over stdin, never committed): the five drill scripts of Step 8.

**Interfaces:**
- Consumes: v220 merged on `main` and deployed by CI (the VM's `origin/main` carries `rollback_code.sh` and the planner modules); the `rollback_code.sh` CLI, env knobs and exit codes (V220-9, V220-9b, V220-10); picker rows (V220-2b).
- Produces: heading `## Code-only rollback (v220)` (last section of `docs/deploy/DB_RESTORE.md`; v221's V221-4 adds the comparison table under it) and the drill record `### Drill <date> (v220 V220-18)`.

Decisions this task fixes:

- **The partner confirms first.** The drill creates containers, a volume and a checkout on the production VM. The controller asks with `AskUserQuestion` before Step 7 runs anything there (an implementer subagent stops at Step 6 and hands back); no answer, no drill.
- **Scratch project `rbdrill`:** checkout `/opt/swing-bot-rbdrill` (a `deploy`-owned clone of the live checkout with `origin` set to the live remote URL), override copied to `/opt/swing-bot-rbdrill.override.yml` (outside the checkout: checking out an older target must not delete it), selected by `COMPOSE_PROJECT_NAME=rbdrill` and `COMPOSE_FILE=docker-compose.yml:/opt/swing-bot-rbdrill.override.yml`, `ROLLBACK_APP_DIR=/opt/swing-bot-rbdrill`, `ROLLBACK_DRILL=1`. Precedent: `scripts/ops/pitr_drill.sh`.
- **The bot service never starts** (a second bot on the live token would post to the live guild). The scratch `.env` is a mode-600, `deploy`-owned copy of the live one with `DISCORD_TOKEN` set to `drill-disabled`, `OPS_ALERT_WEBHOOK_URL`, `NTFY_TOPIC`, `SMTP_PASSWORD` emptied, `ALERT_EMAIL_ENABLED=false` and `PG_ARCHIVE_MODE=off` (the live value is `on`; the scratch db must not archive). Key names stay, so check 3 sees them; no value is ever printed.
- **Production is only read:** `pg_dump` from `swing-db` (37 MB), a copy of `market_data/` (227 MB, so the scratch refresher does not refetch the universe on the live API keys), `backups/deploys.jsonl` and each stable point's `manifest.json`. A before/after snapshot of the live stack proves nothing changed. Do not push to `main` while the drill runs (a CI deploy would change the "after" snapshot).
- **Run order:** dry run, forced smoke failure (the automatic restore, before any real switch), rollback, release. Target: the newest `deploy` candidate above the floor other than the scratch `HEAD`, a pre-v220 image, which also covers "no `rollback_smoke` in the image".
- **Any unexpected exit stops the drill:** teardown (Step 16), record the failure in the drill record, return `BLOCKED:`. Never patch a script on the VM.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_rollback_drill_override.py`:

```python
"""The v220 rollback drill's compose override (deploy/drill/rollback-drill.override.yml):
it may only rename containers, drop host ports and point the admin's container
controls at a bot that does not exist, so a scratch project can run next to
the live stack on the VM."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[2]
OVERRIDE = ROOT / "deploy" / "drill" / "rollback-drill.override.yml"


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!reset", lambda loader, node: ("!reset", loader.construct_sequence(node)))


@pytest.fixture(scope="module")
def base():
    return yaml.load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), Loader=_Loader)["services"]


@pytest.fixture(scope="module")
def over():
    return yaml.load(OVERRIDE.read_text(encoding="utf-8"), Loader=_Loader)["services"]


def test_every_fixed_container_name_is_renamed(base, over):
    named = {svc for svc, spec in base.items() if "container_name" in spec}
    assert named == {svc for svc, spec in over.items() if "container_name" in spec}
    for svc in named:
        assert over[svc]["container_name"].startswith("rbdrill-"), svc
        assert over[svc]["container_name"] != base[svc]["container_name"]


def test_no_host_port_is_published(base, over):
    for svc, spec in base.items():
        if "ports" in spec:
            assert over[svc]["ports"] == ("!reset", []), svc


def test_admin_controls_point_at_a_bot_that_does_not_exist(over):
    assert over["admin"]["environment"]["BOT_CONTAINER_NAME"] == over["bot"]["container_name"]


def test_it_changes_nothing_but_names_ports_and_the_bot_pointer(over):
    allowed = {"container_name", "ports", "environment"}
    for svc, spec in over.items():
        assert set(spec) <= allowed, (svc, set(spec) - allowed)


def test_the_header_says_the_bot_never_starts():
    assert "never started" in OVERRIDE.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_drill_override.py`
Expected: FAIL (`FileNotFoundError` for the override).

- [ ] **Step 3: Create the override**

Create `deploy/drill/rollback-drill.override.yml`:

```yaml
# v220 V220-18: scratch project for the code-only rollback drill. Used ONLY as
#   COMPOSE_PROJECT_NAME=rbdrill COMPOSE_FILE=docker-compose.yml:/opt/swing-bot-rbdrill.override.yml
# from the scratch checkout /opt/swing-bot-rbdrill, with this file copied
# outside the checkout (the drill checks out older trees, which lack it).
# It renames every fixed container_name so nothing collides with the live
# stack, publishes no host port, and points the admin's container controls
# at a bot container that does not exist. The bot service is never started
# in the drill: a second bot on the live token would post to the live guild.
services:
  db:
    container_name: rbdrill-db
  db-test:
    container_name: rbdrill-db-test
    ports: !reset []
  bot:
    container_name: rbdrill-bot
  admin:
    container_name: rbdrill-admin
    ports: !reset []
    environment:
      BOT_CONTAINER_NAME: rbdrill-bot
  refresher:
    container_name: rbdrill-refresher
  cloudflared:
    container_name: rbdrill-cloudflared
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_drill_override.py`
Expected: `0 failed`. (A service added to `docker-compose.yml` since the plan needs its rename or `!reset` here.)

- [ ] **Step 5: Commit the override**

```bash
git add deploy/drill/rollback-drill.override.yml tests/scripts/test_rollback_drill_override.py
git commit -m "test(v220): rollback drill compose override -- renamed containers, no host ports, no bot"
```

- [ ] **Step 6: Preconditions (read-only)**

- `git fetch` locally; the v220 merge is on `origin/main` and the latest `Deploy to Hetzner` run for it is green (`gh run list --workflow deploy.yml --limit 3`).
- `bash scripts/ops/ssh-hetzner.sh "runuser -u deploy -- git -C /opt/swing-bot rev-parse HEAD; test -f /opt/swing-bot/backups/deploy_hold.json && echo HOLD || echo nohold; test -e /opt/swing-bot-rbdrill && echo LEFTOVER || echo clean; docker compose version --short"` prints `origin/main`'s sha, `nohold`, `clean`, and a compose version that supports `!reset` (2.24 or newer).

Any miss: stop and report it. An implementer subagent stops here and hands back to the controller.

- [ ] **Step 7: Ask the partner (controller only)**

`AskUserQuestion`: "Run the v220 rollback drill on the production VM now? It runs a scratch project `rbdrill` (db, admin, refresher; no bot) next to the live stack for about 30 minutes, seeded by a read-only `pg_dump`, removed afterwards." Options: "Run the drill now (Recommended)", "Not now". On "Not now", stop; V220-18 stays open.

- [ ] **Step 8: Set up the scratch project**

Write the five scripts below into the session scratchpad (`$S`). Copy the override, then run the setup:

```bash
bash scripts/ops/ssh-hetzner.sh "cat > /opt/swing-bot-rbdrill.override.yml" < deploy/drill/rollback-drill.override.yml
bash scripts/ops/ssh-hetzner.sh "bash -s" < "$S/rbdrill_setup.sh" > "$S/setup.log" 2>&1; tail -n 15 "$S/setup.log"
```

`rbdrill_setup.sh`:

```bash
set -euo pipefail
D=/opt/swing-bot-rbdrill; O=/opt/swing-bot-rbdrill.override.yml; LIVE=/opt/swing-bot
export COMPOSE_PROJECT_NAME=rbdrill COMPOSE_FILE="docker-compose.yml:$O"
if [ -e "$D" ] || docker ps -a --format '{{.Names}}' | grep -q '^rbdrill-'; then
  echo "REFUSE: a previous drill is still there; run rbdrill_teardown.sh first" >&2; exit 2
fi
[ -f "$O" ] || { echo "REFUSE: $O is missing" >&2; exit 2; }
url="$(runuser -u deploy -- git -C "$LIVE" remote get-url origin)"
install -d -o deploy -g deploy "$D"
runuser -u deploy -- git clone -q "$LIVE" "$D"
runuser -u deploy -- git -C "$D" remote set-url origin "$url"
runuser -u deploy -- git -C "$D" fetch -q origin main
runuser -u deploy -- git -C "$D" checkout -q -B main origin/main
cd "$D"
install -d -o deploy -g deploy backups backups/env backups/stable logs data exports market_data
install -m 600 -o deploy -g deploy "$LIVE/.env" .env   # the planner reads key names as deploy
touch .env.bak
python3 - .env <<'PY'
import sys
path = sys.argv[1]
want = {"DISCORD_TOKEN": "drill-disabled", "OPS_ALERT_WEBHOOK_URL": "", "NTFY_TOPIC": "",
        "SMTP_PASSWORD": "", "ALERT_EMAIL_ENABLED": "false", "PG_ARCHIVE_MODE": "off"}
out, seen = [], set()
for line in open(path, encoding="utf-8").read().splitlines():
    key = line.split("=", 1)[0].strip()
    if key in want and "=" in line and not line.lstrip().startswith("#"):
        out.append(f"{key}={want[key]}"); seen.add(key)
    else:
        out.append(line)
out += [f"{k}={v}" for k, v in want.items() if k not in seen]
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("neutralised:", ", ".join(sorted(want)))
PY
cp "$LIVE/backups/deploys.jsonl" backups/deploys.jsonl
for m in "$LIVE"/backups/stable/*/manifest.json; do
  [ -f "$m" ] || continue
  n="$(basename "$(dirname "$m")")"; install -d "backups/stable/$n"; cp "$m" "backups/stable/$n/"
done
cp -a "$LIVE/market_data/." market_data/
docker compose config --services >/dev/null
docker compose up -d --no-build --wait db
docker exec -i swing-db pg_dump -U swingbot -d swingbot --no-owner --no-privileges </dev/null \
  | docker compose exec -T db psql -U swingbot -d swingbot -q -v ON_ERROR_STOP=1 >/dev/null
docker compose up -d --no-deps --no-build --wait admin refresher
echo "scratch HEAD $(runuser -u deploy -- git rev-parse HEAD)"
for t in plans journal_entries; do
  echo "$t live=$(docker exec swing-db psql -U swingbot -d swingbot -tAc "SELECT count(*) FROM $t") scratch=$(docker compose exec -T db psql -U swingbot -d swingbot -tAc "SELECT count(*) FROM $t" </dev/null)"
done
docker compose ps --format '{{.Service}} {{.State}} {{.Health}}'
```

Expected: `neutralised: …`, scratch `HEAD` = `origin/main`, equal live/scratch counts, `admin running healthy`, `db running healthy`, `refresher running`.

`rbdrill_run.sh` (every drill call goes through it; arguments after `bash -s --`):

```bash
set -uo pipefail
cd /opt/swing-bot-rbdrill
export COMPOSE_PROJECT_NAME=rbdrill COMPOSE_FILE=docker-compose.yml:/opt/swing-bot-rbdrill.override.yml
export ROLLBACK_APP_DIR=/opt/swing-bot-rbdrill ROLLBACK_DRILL=1
runuser -u deploy -- git fetch -q origin main
runuser -u deploy -- git show origin/main:scripts/ops/rollback_code.sh > backups/rollback_code.sh
bash backups/rollback_code.sh "$@"; rc=$?
echo "EXIT $rc"
```

`rbdrill_state.sh`:

```bash
cd /opt/swing-bot-rbdrill
export COMPOSE_PROJECT_NAME=rbdrill COMPOSE_FILE=docker-compose.yml:/opt/swing-bot-rbdrill.override.yml
echo "head $(runuser -u deploy -- git rev-parse HEAD) branch $(runuser -u deploy -- git symbolic-ref -q --short HEAD || echo detached)"
echo "env image $(python3 scripts/ops/env_set.py --get SWING_BOT_IMAGE)"
echo "admin image $(docker inspect -f '{{.Config.Image}}' rbdrill-admin)"
if [ -f backups/deploy_hold.json ]; then echo "hold $(cat backups/deploy_hold.json | tr -d '\n')"; else echo "no hold"; fi
echo "deploys $(wc -l < backups/deploys.jsonl) last: $(tail -n 1 backups/deploys.jsonl)"
ls backups/rollback_keys_*.json 2>/dev/null || echo "no key snapshot"
docker compose ps --format '{{.Service}} {{.State}} {{.Health}}'
docker compose exec -T admin alembic current </dev/null 2>/dev/null | tail -n 1
```

`prod_state.sh` (read-only):

```bash
cd /opt/swing-bot
docker ps --filter name=swing- --format '{{.Names}} {{.ID}} {{.CreatedAt}} {{.Image}}' | sort
echo "head $(runuser -u deploy -- git rev-parse HEAD)"
echo "env mtime $(stat -c %Y .env)"
if [ -f backups/deploy_hold.json ]; then echo "HOLD PRESENT"; else echo "no hold"; fi
echo "deploys $(wc -l < backups/deploys.jsonl)"
```

`rbdrill_teardown.sh`:

```bash
set -uo pipefail
D=/opt/swing-bot-rbdrill; O=/opt/swing-bot-rbdrill.override.yml
if [ -d "$D" ] && [ -f "$O" ]; then
  (cd "$D" && COMPOSE_PROJECT_NAME=rbdrill COMPOSE_FILE="docker-compose.yml:$O" docker compose down -v --remove-orphans)
fi
docker ps -aq --filter name=rbdrill- | xargs -r docker rm -f
docker volume ls -q --filter name=rbdrill | xargs -r docker volume rm
cd / && rm -rf "$D" "$O"
echo "left: $(docker ps -a --filter name=rbdrill- --format '{{.Names}}' | tr '\n' ' ')$(docker volume ls -q --filter name=rbdrill | tr '\n' ' ')"
```

- [ ] **Step 9: Snapshot production before**

`bash scripts/ops/ssh-hetzner.sh "bash -s" < "$S/prod_state.sh" > "$S/prod_before.txt"`

- [ ] **Step 10: Pick and resolve the target**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s -- --candidates" < "$S/rbdrill_run.sh" > "$S/candidates.json"
```

Pick the first row with `"kind": "deploy"`, `"above_floor": true` and a `sha` different from the scratch `HEAD`, then resolve its first 12 hex: `bash scripts/ops/ssh-hetzner.sh "bash -s -- --resolve <sha12>" < "$S/rbdrill_run.sh"`. Expected: one JSON object with `sha`, `image`, `form` `sha`, then `EXIT 0`. Keep `SHA` and `IMAGE` from it.

- [ ] **Step 11: Dry run**

`bash scripts/ops/ssh-hetzner.sh "bash -s -- <SHA> <IMAGE> --dry-run --reason 'v220 drill'" < "$S/rbdrill_run.sh" > "$S/dry.log" 2>&1; tail -n 25 "$S/dry.log"`
Expected: the report JSON with `"ok": true`, the plan lines, `Dry run: nothing changed.`, `EXIT 0`. On `EXIT 2` naming `market-data writer differs`, the controller asks the partner (`AskUserQuestion`) before adding `--allow-writer-drift` to this and the next two calls; any other refusal stops the drill.

- [ ] **Step 12: Forced smoke failure**

```bash
bash scripts/ops/ssh-hetzner.sh "ROLLBACK_FORCE_SMOKE_FAIL=1 bash -s -- <SHA> <IMAGE> --i-mean-it --reason 'v220 drill: forced smoke failure'" < "$S/rbdrill_run.sh" > "$S/forced.log" 2>&1; tail -n 15 "$S/forced.log"
bash scripts/ops/ssh-hetzner.sh "bash -s" < "$S/rbdrill_state.sh"
```

Expected: `drill: forced smoke failure`, `restoring git …`, `restored git <scratch HEAD>, image <from image>; nothing written to deploys.jsonl`, `EXIT 1`; state: `head` = `origin/main` on branch `main`, env and admin image = the from image, `no hold`, `deploys` count unchanged from setup.

- [ ] **Step 13: Real rollback**

Same call as Step 12 without `ROLLBACK_FORCE_SMOKE_FAIL=1` and with `--reason 'v220 drill'` (log to `$S/rollback.log`), then the state script.
Expected: `image has no rollback_smoke (pre-v220)…` (a pre-v220 target), `rollback to <SHA> finished; deploys are held until /rollback --release`, `EXIT 0`; state: `head` = `SHA`, detached; env and admin image = `IMAGE`; `hold` with all seven keys; one more `deploys` line, the last with `"kind": "rollback"`; one key snapshot. `prod_state.sh` still says `no hold`.

- [ ] **Step 14: Release**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s -- --release --dry-run" < "$S/rbdrill_run.sh"
bash scripts/ops/ssh-hetzner.sh "bash -s -- --release --i-mean-it" < "$S/rbdrill_run.sh" > "$S/release.log" 2>&1; tail -n 25 "$S/release.log"
bash scripts/ops/ssh-hetzner.sh "bash -s" < "$S/rbdrill_state.sh"
```

Expected: the dry run prints `Release plan:` and `EXIT 0`; the release prints the window report JSON (`{"tables": …}`) and `released: main …; deploys resume`, `EXIT 0`; state: `head` = `origin/main` on branch `main`, image `…:sha-<origin/main 12>`, `no hold`, last line `"kind": "release"`, `alembic current` ends in `(head)`.

- [ ] **Step 15: Snapshot production after and compare**

`bash scripts/ops/ssh-hetzner.sh "bash -s" < "$S/prod_state.sh" > "$S/prod_after.txt"; diff "$S/prod_before.txt" "$S/prod_after.txt" && echo "production unchanged"`
Expected: `production unchanged`. A difference that a CI deploy or a settings save explains is noted in the record; any other one is a finding (`BLOCKED:`).

- [ ] **Step 16: Tear down**

`bash scripts/ops/ssh-hetzner.sh "bash -s" < "$S/rbdrill_teardown.sh"`
Expected: `left: ` followed by nothing. Nothing on the VM needs mirroring: the scratch project is gone and the override is in the repo.

- [ ] **Step 17: Record the drill**

Append to `docs/deploy/DB_RESTORE.md`, after the last line of the file, filling every `<…>` from the logs in `$S` (dates UTC):

```markdown

## Code-only rollback (v220)

`/rollback` (`.claude/skills/rollback/SKILL.md`, `scripts/ops/rollback_code.sh`) puts the VM's
checkout and bot image back to an earlier `main` commit and keeps every row of trading data (the
two restores above put Postgres back). While rolled back, `backups/deploy_hold.json` holds every
deploy (CI `hold` job, `deploy/deploy.sh`, `HOLD` line, `/deploy`) until `/rollback --release`.
It was proven on a scratch project, never by a production rollback.

### Drill <YYYY-MM-DD> (v220 V220-18)

Scratch project `rbdrill` on the VM: checkout `/opt/swing-bot-rbdrill` at `main` <sha12>
(bot <version>), override `deploy/drill/rollback-drill.override.yml` copied outside the checkout,
database seeded by `pg_dump` from production (<n> plans, <n> journal rows), `ROLLBACK_DRILL=1`
(no pgBackRest backup, no bot service, no heartbeat check). Target <label> <sha12>
(bot <version>), image `…:sha-<12>`, found with `--candidates` and `--resolve`.

| Step | Exit | Result |
|---|---|---|
| Dry run | 0 | <ok; warnings; refresher start or keep-stopped; n migrations, all safe> |
| Forced smoke failure | 1 | restored main <sha12> and its image; no hold; `deploys.jsonl` unchanged |
| Rollback | 0 | checkout <sha12>, admin on the target image, hold written, `rollback` line, smoke passed without `rollback_smoke` (pre-v220 image) |
| Release | 0 | main <sha12> back, hold gone, `release` line, Alembic at <head>; window report: <tables, updated, fewer_keys> |

Production was untouched: container ids and creation times, checkout `HEAD`, `.env` mtime, no hold
file, `deploys.jsonl` <n> lines before and after. The scratch project, its volume, the checkout and
the override copy were removed afterwards.
```

- [ ] **Step 18: Commit the record**

```bash
git add docs/deploy/DB_RESTORE.md
git commit -m "docs(v220): code-only rollback drill on a scratch project -- dry run, forced smoke failure, rollback, release"
```

The close-out follows this task (index Parallelisation).
