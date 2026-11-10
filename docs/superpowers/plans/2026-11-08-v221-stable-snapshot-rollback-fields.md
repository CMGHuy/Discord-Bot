# v221 — Stable snapshots carry rollback fields and pinned images

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md), **Section 2 (`/stable-snapshot` extension)** and the "Code-brief corrections" section. Moved out of the v220 plan (formerly V220-13/V220-14, plus the spec's "Repo bookkeeping" docs, formerly V220-16, now V221-4) so v220 stays inside the 20-task cap; v220's own plan is [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md).

## Goal

v220 adds `/rollback`, which puts the code and bot image back to an earlier
`main` commit while keeping every row of trading data. One of its target forms
is a stable point (`/rollback stable-2026-10-20`), and today a stable point is
thin: its `manifest.json` records the git sha, the two images, a restic id and
row counts, nothing about what code the point actually ran or what changed
since the previous one. Its `sha-…` images also age out of GHCR after 45 days
(`registry-retention.yml`), so an old stable point may name an image the
registry no longer has, and the VM's read-only GHCR login cannot add a
protective tag.

Once this plan ships, every new stable point records five more manifest
fields: the database's Alembic head, the `bot` and `ui` versions, a hash of
the declared config key names, and the features (plan ids and commit
subjects) on `main` since the previous stable point. Both of its images get a
`stable-YYYY-MM-DD[-N]` tag from a new `workflow_dispatch` workflow
(`pin-stable-image.yml`, `packages: write` through `GITHUB_TOKEN`) that the
`/stable-snapshot` skill triggers and waits for, and registry pruning skips
`stable-*` tags. The skill's report adds the feature list, the matching
`/rollback stable-…` command and whether the point is above v220's
compatibility floor.

What it leaves alone: older manifests keep verifying unchanged (the verifier
only adds a "pre-v220" note for them, the spec's wording), `restore_stable.sh`,
`pull_backups.sh` and the v220 rollback path. `/rollback stable-…` never
requires the new fields: it resolves a stable point through its manifest
`git_sha` or its git tag, which every point already has. Nothing is retagged
or snapshotted during implementation; the first pinned point is the next real
`/stable-snapshot` run.

Success is measured by the tests: the new fields written and parsed, old
manifests still passing `verify` with the note, the snapshot script's order
and flags text-pinned, the workflow's inputs, permissions, validation and
injection safety pinned, the retention exclusion pinned with the action's own
README sentence quoted, and the skill text pinned. Integrity work, so no ExpR
or win-rate claim follows.

## Architecture

- `scripts/ops/backup_manifest.py` (stdlib only): `ROLLBACK_FIELDS`,
  `config_keys_sha256` (sha256 over `rollback_checks.declared_config_keys`,
  the v220 V220-4 reader, imported lazily so `verify`/`prune` never need it),
  `features_from_log`, `previous_stable_sha`, `manifest_era`; `build` gains
  `--alembic-head`, `--version-json`, `--config-source`, `--features-log`;
  new subcommand `prev-sha`; `verify` prints `era: pre-v220 …` for a stable
  manifest (one with a `restic_id`) that lacks the fields.
- `scripts/ops/stable_snapshot.sh` reads the Alembic head from the database,
  `VERSION.json` and `swingbot/config.py` from `git show $GIT_SHA:…`, and the
  feature log `git log PREV..GIT_SHA` (as `deploy`), then passes them to
  `build`.
- `.github/workflows/pin-stable-image.yml`: retags both images with
  `docker buildx imagetools create` (registry-side, no pull), after
  validating the name and that both refs belong to this repository's packages.
- `.github/workflows/registry-retention.yml`: `image-tags: "!latest,!stable-*"`.
- `.claude/skills/stable-snapshot/SKILL.md`: Step 4b pins, Step 7 reports.

## Global Constraints

- **Runs after v220 is merged on `main`:** V221-1 imports `declared_config_keys` from `scripts/ops/rollback_checks.py` (v220 V220-4); V221-3 calls `scripts/ops/rollback_plan.py floor` (v220 V220-2) and names the `/rollback` skill (v220 V220-15). Verify with `git grep -n "def declared_config_keys" scripts/ops/rollback_checks.py` and `git grep -n "def floor_violations" scripts/ops/rollback_plan.py` before starting; missing means stop.
- `scripts/ops/backup_manifest.py` stays **standard library only** and never imports `swingbot`; the `rollback_checks` import sits inside `config_keys_sha256` only.
- **Manifest field names, verbatim:** `alembic_head` (str; several heads joined by `,`), `bot_version`, `ui_version`, `config_keys_sha256` (64 hex), `features` (`[{"plan": "vNNN" | null, "sha": <40 hex>, "subject": str}]`, newest first). Old manifests without them still `verify` PASS (exit 0).
- `config_keys_sha256` hashes the sorted, de-duplicated **declared** field names joined by `\n` (`config.py` has no "required" notion, per the v220 code brief); values are never read.
- No production snapshot, retag, workflow run or retention run during implementation; production stays read only.
- The workflow never interpolates `${{ inputs.* }}` into a `run:` script: inputs reach the shell through `env:`.
- The `stable-snapshot` skill never contains the word "digest" (`tests/hooks/test_skill_shape.py` pins that) and keeps "do NOT tag".
- Every git command in `stable_snapshot.sh` runs as `runuser -u deploy -- git …` (its shape test enforces it).
- Every function < complexity 15 (`scripts/dev/complexity_gate.py`). New tests go into existing files or suites: `tests/scripts/` = `tooling`, `tests/dev/` = `dev-setup`, `tests/hooks/` = its existing suite; no new `tests/` directory.
- Narrow runs only: `python scripts/dev/testrun.py file <test>`. No task runs the full suite (CI does). No task reaches Postgres.
- A skill edit ships its Codex mirror in the same commit (`python scripts/dev/sync_codex.py`, then `python scripts/dev/sync_codex.py --check`).

## Parallelisation

At most 2 implementers at once.

- **V221-1** (`backup_manifest.py`, `stable_snapshot.sh`, their tests) and **V221-2** (`pin-stable-image.yml`, `registry-retention.yml`, `tests/dev/test_pin_stable_image.py`) touch disjoint files and share no contract: run them side by side.
- **V221-3** (skill) waits for both: it documents V221-1's manifest fields and V221-2's workflow name, inputs and `run-name`.
- **V221-4** (rollback docs, moved from v220's V220-16) waits for V221-3: both edit `AGENTS.md` and regenerate the Codex mirror (`sync_codex.py`). It also needs v220's drill (V220-18) on `main`, which creates the `DB_RESTORE.md` heading it fills.
- **V221-5** (release) runs last, after V221-1..4 are merged into the worktree: the bump describes the whole change.
- The whole plan waits for v220 to merge (Global Constraints). v220 does not wait for v221: its drill (V220-18) never takes a stable snapshot, and its `/rollback` skill resolves stable targets without the new fields.

## Task ledger

| ID | Title | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|
| V221-1 | Manifest rollback fields, pre-v220 verify note, snapshot script feeds them | sonnet — additive fields in one stdlib module plus its shell caller | M `scripts/ops/backup_manifest.py`, M `scripts/ops/stable_snapshot.sh`, M `tests/scripts/test_backup_manifest.py`, M `tests/scripts/test_stable_snapshot_shape.py` | `ROLLBACK_FIELDS`; `config_keys_sha256(config_source: str) -> str`; `features_from_log(lines: list[str]) -> list[dict]`; `previous_stable_sha(stable_dir: Path, exclude: str = "") -> str \| None`; `manifest_era(manifest: dict) -> str` (`"v220"`/`"pre-v220"`); `build_manifest(..., rollback: dict \| None = None)`; CLI `build --alembic-head --version-json --config-source --features-log`, `prev-sha DIR [--exclude NAME]` |
| V221-2 | `pin-stable-image.yml` and the retention exclusion | sonnet — new workflow plus one action input, README-verified | C `.github/workflows/pin-stable-image.yml`, M `.github/workflows/registry-retention.yml`, C `tests/dev/test_pin_stable_image.py` | workflow `pin-stable-image.yml`: inputs `name`, `bot_image`, `db_image`; `run-name: pin <name>`; retention `image-tags: "!latest,!stable-*"` |
| V221-3 | `/stable-snapshot` pins images and reports rollback fields | haiku — fixed skill text from this plan | M `.claude/skills/stable-snapshot/SKILL.md`, M `.agents/skills/stable-snapshot/SKILL.md` (generated), M `tests/hooks/test_skill_shape.py`, M `AGENTS.md` | — |
| V221-4 | Rollback docs: `DB_RESTORE.md` comparison, `schema-evolution.md`, `schema-change` skill | haiku — fixed doc text from the v220 spec (moved from v220 V220-16) | M `docs/deploy/DB_RESTORE.md`, M `docs/claude/schema-evolution.md`, M `.claude/skills/schema-change/SKILL.md`, M `AGENTS.md`, M `.agents/skills/schema-change/SKILL.md` (generated), C `tests/scripts/test_rollback_docs.py` | `schema-evolution.md` section `## Rollback safety (v220)` |
| V221-5 | Release: bot patch, version history | haiku — fixed `VERSION.json` bump and regeneration | M `VERSION.json`, M `swingbot/admin/version_history.json` | — |

# Phase 1 — Manifest, workflow, skill, release

### Task V221-1: Manifest rollback fields, pre-v220 verify note, snapshot script feeds them

**Model:** sonnet — additive fields in one stdlib module plus its shell caller

**Files:**
- Modify: `scripts/ops/backup_manifest.py` (module docstring, new helpers after `next_stable_name`, `build_manifest`, `_cmd_build`, `_cmd_verify`, new `_cmd_prev_sha`, `_parser`, `HANDLERS`)
- Modify: `scripts/ops/stable_snapshot.sh` (new block after the `PGV=` line; the `build` line)
- Modify: `tests/scripts/test_backup_manifest.py` (append)
- Modify: `tests/scripts/test_stable_snapshot_shape.py` (append)

**Interfaces:**
- Consumes (v220 V220-4, on `main`): `scripts/ops/rollback_checks.py::declared_config_keys(source: str) -> list[str]` (raises `ValueError` when unparsable). Check first: `git grep -n "def declared_config_keys" scripts/ops/rollback_checks.py`; no hit means v220 is not merged, stop.
- Produces (per the ledger): `ROLLBACK_FIELDS = ("alembic_head", "bot_version", "ui_version", "config_keys_sha256", "features")`; `config_keys_sha256(config_source: str) -> str`; `features_from_log(lines: list[str]) -> list[dict]`; `previous_stable_sha(stable_dir: Path, exclude: str = "") -> str | None`; `manifest_era(manifest: dict) -> str`; `build_manifest(..., rollback: dict | None = None)`; CLI `build ... --alembic-head S --version-json F --config-source F --features-log F`; CLI `prev-sha DIR [--exclude NAME]` (prints the sha or an empty line, exit 0).

Decisions (spec Section 2, Global Constraints):
- `rollback=None` (every existing caller, `pull_backups.sh` included) writes exactly the old manifest: the five keys are absent, not null.
- The `era: pre-v220 …` line is printed by `verify` only for a **stable** manifest (truthy `restic_id`; only `stable_snapshot.sh` passes `--restic-id`) without all five keys. It is a note, never a problem: exit code and `PASS` are unchanged, so `restore_stable.sh` and `pull_backups.sh` (which test the exit code) behave as before.
- The previous stable point is the newest `backups/stable/stable-YYYY-MM-DD[-N]` folder (date, then `N` numerically, a bare date counts as `N = 1`) that holds a manifest with a `git_sha`, the current name excluded; `.partial` folders never match the name pattern.
- `alembic_head` comes from the database the dump came from (`SELECT version_num FROM alembic_version`), not from the tree: it is what the restore would bring back.

- [ ] **Step 1: Write the failing manifest tests**

Append to `tests/scripts/test_backup_manifest.py`:

```python
# ---- v221: rollback fields (v220 spec Section 2) ------------------------------
import hashlib  # noqa: E402

CONFIG_SRC = (
    "FIELDS = [\n"
    '    Field("DISCORD_TOKEN", "TOKEN", "Discord", "Bot token", type="password"),\n'
    '    Field("SCAN_INTERVAL", "scan_interval", "Scan", "Interval", default="15"),\n'
    "]\n"
)
SHA_A, SHA_B, SHA_C = "a" * 40, "b" * 40, "c" * 40


def test_config_keys_hash_covers_names_not_values_or_order():
    h = bm.config_keys_sha256(CONFIG_SRC)
    assert h == hashlib.sha256(b"DISCORD_TOKEN\nSCAN_INTERVAL").hexdigest()
    reordered = CONFIG_SRC.replace('default="15"', 'default="99"')
    lines = reordered.splitlines()
    swapped = "\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n"
    assert bm.config_keys_sha256(swapped) == h
    added = CONFIG_SRC.replace("]\n", '    Field("NEW_KEY", "new", "S", "L"),\n]\n')
    assert bm.config_keys_sha256(added) != h


def test_config_keys_hash_of_the_real_config_is_hex():
    src = (REPO / "swingbot" / "config.py").read_text(encoding="utf-8")
    h = bm.config_keys_sha256(src)
    assert len(h) == 64 and int(h, 16) >= 0


def test_features_from_log_takes_the_first_plan_id_and_skips_blanks():
    rows = bm.features_from_log([
        f"{SHA_A}\tfeat(v220): resolve targets",
        f"{SHA_B}\tmerge main into worktree",
        "",
        f"{SHA_C}\tdocs(v219): plan part 2 (v218 follow-up)\r\n",
    ])
    assert rows == [
        {"plan": "v220", "sha": SHA_A, "subject": "feat(v220): resolve targets"},
        {"plan": None, "sha": SHA_B, "subject": "merge main into worktree"},
        {"plan": "v219", "sha": SHA_C, "subject": "docs(v219): plan part 2 (v218 follow-up)"},
    ]


def _point(stable, name, sha):
    d = stable / name
    d.mkdir(parents=True)
    if sha is not None:
        (d / "manifest.json").write_text(json.dumps({"git_sha": sha}), encoding="utf-8")


def test_previous_stable_sha_picks_the_newest_point_with_a_sha(tmp_path):
    stable = tmp_path / "stable"
    _point(stable, "stable-2026-10-02", "s1")
    _point(stable, "stable-2026-10-20", "s2")
    _point(stable, "stable-2026-10-20-2", "s3")
    _point(stable, "stable-2026-10-20-10", "s4")      # -10 sorts after -2
    _point(stable, "stable-2026-10-25", None)         # no manifest: skipped
    _point(stable, "stable-2026-11-01.partial", "s5")  # never a point
    _point(stable, "notes", "s6")
    assert bm.previous_stable_sha(stable) == "s4"
    assert bm.previous_stable_sha(stable, exclude="stable-2026-10-20-10") == "s3"
    assert bm.previous_stable_sha(tmp_path / "absent") is None


def test_build_writes_rollback_fields_only_when_given(folder):
    fields = {"alembic_head": "v204_001", "bot_version": "2.17.4", "ui_version": "1.40.3",
              "config_keys_sha256": "f" * 64, "features": []}
    m = bm.build_manifest(folder, git_sha="abc", rollback=fields)
    assert {k: m[k] for k in bm.ROLLBACK_FIELDS} == fields
    assert bm.manifest_era(m) == "v220"
    old = bm.build_manifest(folder, git_sha="abc")
    assert not set(bm.ROLLBACK_FIELDS) & set(old)
    assert bm.manifest_era(old) == "pre-v220"
    assert bm.verify_folder(folder) == []


CLI = [sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py")]


def test_cli_build_reads_the_rollback_inputs(folder, tmp_path):
    (tmp_path / "VERSION.json").write_text('{"ui": "1.40.3", "bot": "2.17.4"}', encoding="utf-8")
    (tmp_path / "config.py").write_text(CONFIG_SRC, encoding="utf-8")
    (tmp_path / "features.tsv").write_text(f"{SHA_A}\tfeat(v220): x\n", encoding="utf-8")
    out = subprocess.run(CLI + ["build", str(folder), "--alembic-head", "v204_001",
                                "--version-json", str(tmp_path / "VERSION.json"),
                                "--config-source", str(tmp_path / "config.py"),
                                "--features-log", str(tmp_path / "features.tsv")],
                         capture_output=True, text=True, check=True)
    m = json.loads(out.stdout)
    assert m["alembic_head"] == "v204_001"
    assert (m["bot_version"], m["ui_version"]) == ("2.17.4", "1.40.3")
    assert m["config_keys_sha256"] == bm.config_keys_sha256(CONFIG_SRC)
    assert m["features"] == [{"plan": "v220", "sha": SHA_A, "subject": "feat(v220): x"}]


def _verify(folder):
    return subprocess.run(CLI + ["verify", str(folder)], capture_output=True, text=True)


def test_verify_notes_a_pre_v220_stable_manifest_and_still_passes(folder):
    bm.build_manifest(folder, git_sha="abc", restic_id="r1")
    res = _verify(folder)
    assert res.returncode == 0
    assert "era: pre-v220" in res.stdout and res.stdout.rstrip().endswith("PASS")


def test_verify_prints_no_era_note_for_new_or_pull_manifests(folder):
    bm.build_manifest(folder, git_sha="abc")                  # a pull: no restic id
    assert "era:" not in _verify(folder).stdout
    fields = {k: None for k in bm.ROLLBACK_FIELDS}
    bm.build_manifest(folder, git_sha="abc", restic_id="r1", rollback=fields)
    assert "era:" not in _verify(folder).stdout


def test_cli_prev_sha_prints_the_sha_or_an_empty_line(tmp_path):
    stable = tmp_path / "stable"
    _point(stable, "stable-2026-10-20", "s2")
    got = subprocess.run(CLI + ["prev-sha", str(stable), "--exclude", "stable-2026-11-08"],
                         capture_output=True, text=True, check=True)
    assert got.stdout.strip() == "s2"
    empty = subprocess.run(CLI + ["prev-sha", str(tmp_path / "none")],
                           capture_output=True, text=True, check=True)
    assert empty.stdout.strip() == ""
```

- [ ] **Step 2: Write the failing shape tests**

Append to `tests/scripts/test_stable_snapshot_shape.py`:

```python
# ---- v221: rollback fields fed to the manifest -------------------------------
V221_INPUTS = (
    "SELECT version_num FROM alembic_version",
    'runuser -u deploy -- git show "$GIT_SHA:VERSION.json"',
    'runuser -u deploy -- git show "$GIT_SHA:swingbot/config.py"',
    'backup_manifest.py prev-sha backups/stable --exclude "$NAME"',
    "runuser -u deploy -- git log --format='%H%x09%s' \"$PREV_SHA..$GIT_SHA\"",
)


def test_v221_inputs_are_gathered_before_the_build(src):
    build = src.index("backup_manifest.py build")
    for needle in V221_INPUTS:
        assert src.index(needle) < build, needle
    line = src[build:src.index(BS_N, build)]
    for flag in ('--alembic-head "$ALEMBIC_HEAD"', '--version-json "$WORK/VERSION.json"',
                 '--config-source "$WORK/config.py"', '--features-log "$WORK/features.tsv"'):
        assert flag in line, flag


def test_v221_inputs_come_before_the_restic_snapshot(src):
    restic = src.index("flock logs/restic.lock restic backup")
    for needle in V221_INPUTS:
        assert src.index(needle) < restic, needle


def test_v221_a_failed_feature_log_warns_instead_of_aborting(src):
    assert ': > "$WORK/features.tsv"' in src
    log = src.index("git log --format=")
    assert "WARNING" in src[log:log + 300]
    assert "alembic_version ORDER BY 1' </dev/null" in src
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backup_manifest.py`
Expected: FAIL — `AttributeError: module 'backup_manifest' has no attribute 'config_keys_sha256'` (and the other new names).

Run: `python scripts/dev/testrun.py file tests/scripts/test_stable_snapshot_shape.py`
Expected: FAIL — `ValueError: substring not found` for `SELECT version_num FROM alembic_version`.

- [ ] **Step 4: Implement the manifest helpers**

In `scripts/ops/backup_manifest.py`, change the docstring's subcommand list to `Subcommands: build, verify, prune, next-name, prev-sha, count-dump, report-market.` and add after `CHUNK = 1 << 20`:

```python
# v221 (v220 spec Section 2): what a stable point needs for /rollback stable-...
ROLLBACK_FIELDS = ("alembic_head", "bot_version", "ui_version", "config_keys_sha256", "features")
PLAN_ID_RE = re.compile(r"\((v\d+)\)")
STABLE_DIR_RE = re.compile(r"^stable-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")
PRE_V220_NOTE = "era: pre-v220 (no rollback fields: alembic_head, versions, config keys, features)"
```

Add the `rollback` keyword to `build_manifest` and merge it before the write:

```python
def build_manifest(folder: Path, *, git_sha=None, deploy=None, restic_id=None,
                   row_counts=None, pg_server_version=None, vm_epoch=None,
                   market_files=None, rollback=None) -> dict:
```

and, directly after the `manifest = {...}` literal and before `(folder / MANIFEST).write_text(...)`:

```python
    if rollback is not None:
        manifest.update({k: rollback.get(k) for k in ROLLBACK_FIELDS})
```

Add after `next_stable_name`:

```python
def config_keys_sha256(config_source: str) -> str:
    """sha256 of the sorted declared config field names, one per line. Names only:
    a value never enters the hash, so adding or removing a key changes it."""
    from rollback_checks import declared_config_keys  # sibling module, stdlib only (v220)
    names = sorted(set(declared_config_keys(config_source)))
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def features_from_log(lines: list[str]) -> list[dict]:
    """`git log --format=%H%x09%s` lines -> [{"plan", "sha", "subject"}], same order."""
    out = []
    for line in lines:
        sha, _, subject = line.rstrip("\r\n").partition("\t")
        if not sha.strip():
            continue
        m = PLAN_ID_RE.search(subject)
        out.append({"plan": m.group(1) if m else None, "sha": sha.strip(), "subject": subject})
    return out


def _stable_key(name: str):
    m = STABLE_DIR_RE.match(name)
    return (m.group(1), int(m.group(2) or 1)) if m else None


def _manifest_git_sha(folder: Path) -> str | None:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8")).get("git_sha") or None
    except (OSError, ValueError):
        return None


def previous_stable_sha(stable_dir: Path, exclude: str = "") -> str | None:
    """git_sha of the newest stable point folder holding a manifest, `exclude` skipped."""
    stable_dir = Path(stable_dir)
    if not stable_dir.is_dir():
        return None
    points = sorted((key, p) for p in stable_dir.iterdir()
                    if p.is_dir() and p.name != exclude and (key := _stable_key(p.name)))
    for _, folder in reversed(points):
        sha = _manifest_git_sha(folder)
        if sha:
            return sha
    return None


def manifest_era(manifest: dict) -> str:
    return "v220" if all(k in manifest for k in ROLLBACK_FIELDS) else "pre-v220"
```

- [ ] **Step 5: Wire the CLI**

Replace `_cmd_build` and `_cmd_verify`, and add `_rollback_inputs`, `_era_note`, `_cmd_prev_sha`:

```python
def _rollback_inputs(args) -> dict | None:
    given = (args.alembic_head, args.version_json, args.config_source, args.features_log)
    if all(v is None for v in given):
        return None
    versions = _load_json(args.version_json) or {}
    config = Path(args.config_source).read_text(encoding="utf-8") if args.config_source else None
    log = (Path(args.features_log).read_text(encoding="utf-8").splitlines()
           if args.features_log else [])
    return {"alembic_head": args.alembic_head or None,
            "bot_version": versions.get("bot"), "ui_version": versions.get("ui"),
            "config_keys_sha256": config_keys_sha256(config) if config is not None else None,
            "features": features_from_log(log)}


def _cmd_build(args) -> int:
    m = build_manifest(
        Path(args.dir), git_sha=args.git_sha, deploy=_load_json(args.deploy_json),
        restic_id=args.restic_id, row_counts=_load_json(args.row_counts),
        pg_server_version=args.pg_version, vm_epoch=args.vm_epoch,
        market_files=_read_market_files(args.market_files),
        rollback=_rollback_inputs(args))
    print(json.dumps(m, sort_keys=True, indent=2))
    return 0


def _era_note(folder: Path) -> str | None:
    """A stable manifest (it has a restic id) from before v221 gets a note, never a problem."""
    try:
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("restic_id") and manifest_era(manifest) == "pre-v220":
        return PRE_V220_NOTE
    return None


def _cmd_verify(args) -> int:
    folder = Path(args.dir)
    problems = verify_folder(folder)
    for p in problems:
        print(p)
    if problems:
        return 1
    note = _era_note(folder)
    if note:
        print(note)
    print("PASS")
    return 0


def _cmd_prev_sha(args) -> int:
    print(previous_stable_sha(Path(args.dir), exclude=args.exclude) or "")
    return 0
```

In `_parser()`, after `b.add_argument("--market-files")`:

```python
    b.add_argument("--alembic-head")
    b.add_argument("--version-json")
    b.add_argument("--config-source")
    b.add_argument("--features-log")
```

and after the `next-name` parser:

```python
    ps = sub.add_parser("prev-sha")
    ps.add_argument("dir")
    ps.add_argument("--exclude", default="")
```

`HANDLERS` gains `"prev-sha": _cmd_prev_sha`.

- [ ] **Step 6: Feed the fields from `stable_snapshot.sh`**

In `scripts/ops/stable_snapshot.sh`, extend the header comment's second sentence to `... sealed by a manifest under backups/stable/<name>/ that also records the Alembic head, versions, config key hash and the features since the previous point (v221).` Then insert directly after the `PGV="$(docker compose exec ...)"` line:

```bash

# v221 rollback fields: the Alembic head of the database this dump came from,
# versions and config key names from the running commit, and the commits on
# main since the previous stable point (none when this is the first one).
ALEMBIC_HEAD="$(docker compose exec -T db psql -U swingbot -d swingbot -At -c 'SELECT version_num FROM alembic_version ORDER BY 1' </dev/null | tr -d '\r' | paste -sd, -)"
runuser -u deploy -- git show "$GIT_SHA:VERSION.json" > "$WORK/VERSION.json"
runuser -u deploy -- git show "$GIT_SHA:swingbot/config.py" > "$WORK/config.py"
PREV_SHA="$(python3 scripts/ops/backup_manifest.py prev-sha backups/stable --exclude "$NAME")"
: > "$WORK/features.tsv"
if [ -n "$PREV_SHA" ]; then
  runuser -u deploy -- git log --format='%H%x09%s' "$PREV_SHA..$GIT_SHA" > "$WORK/features.tsv" \
    || echo "stable_snapshot: WARNING could not list commits since $PREV_SHA; features left empty" >&2
fi
```

Replace the `build` line with (one line):

```bash
python3 scripts/ops/backup_manifest.py build "$DIR.partial" --git-sha "$GIT_SHA" --deploy-json "$DIR.partial/deploy.json" --restic-id "$SNAP_ID" --row-counts "$WORK/rows.json" --pg-version "$PGV" --vm-epoch "$(date +%s)" --alembic-head "$ALEMBIC_HEAD" --version-json "$WORK/VERSION.json" --config-source "$WORK/config.py" --features-log "$WORK/features.tsv" > "$WORK/manifest.json"
```

Keep LF line endings (`test_house_rules` rejects `\r`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backup_manifest.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/scripts/test_stable_snapshot_shape.py`
Expected: PASS, `0 failed` (the existing `bare_git_lines` test included).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add scripts/ops/backup_manifest.py tests/scripts/test_backup_manifest.py
git commit -m "feat(v221): stable manifest records alembic head, versions, config key hash and features"
git add scripts/ops/stable_snapshot.sh tests/scripts/test_stable_snapshot_shape.py
git commit -m "feat(v221): stable_snapshot.sh feeds the rollback fields to the manifest"
```

### Task V221-2: `pin-stable-image.yml` and the retention exclusion

**Model:** sonnet — new workflow plus one action input, README-verified

**Files:**
- Create: `.github/workflows/pin-stable-image.yml`
- Modify: `.github/workflows/registry-retention.yml` (`image-tags` of `steps[0]` and its comment)
- Create: `tests/dev/test_pin_stable_image.py` (suite `dev-setup`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (per the ledger; consumed by V221-3): workflow file `pin-stable-image.yml`, `workflow_dispatch` inputs `name`, `bot_image`, `db_image` (all required strings), `run-name: pin ${{ inputs.name }}` (the skill finds its run by that title); retention `image-tags: "!latest,!stable-*"`.

Decisions (spec Section 2, index note "Retention exclusion"):
- The retag is `docker buildx imagetools create -t <repo>:<name> <source>`, a registry-side copy of the same manifest (the `publish-image` job's precedent in `deploy.yml`): no pull, no rebuild, so the pinned image is exactly the one the stable point ran.
- Both refs must belong to this repository's packages: the bot image starts with `ghcr.io/<owner/repo lowercased>:`, the db image with `ghcr.io/<owner/repo lowercased>-db:`, neither carries `@`, and the tag after the colon is `[A-Za-z0-9_.-]+`. Anything else fails the run before any retag.
- Inputs reach shell only through `env:` (no `${{ … }}` inside any `run:`), so a crafted input cannot inject a command.
- A source image GHCR no longer has fails the run (`imagetools create` exits non-zero); V221-3's skill then stops before tagging.
- The retention change rests on the action's own README at `v3.1.0`. Two facts must be quoted from it: the negation syntax inside the comma-separated `image-tags` list, and that a version is kept when **any** of its tags matches an excluded pattern (a stable image also carries its `sha-` tag). If the README does not establish the second fact, stop after Step 1 and report the README's exact wording to the controller: the retention edit is not made on a guess (the pin workflow alone may still be committed).

- [ ] **Step 1: Read the retention action's README at the pinned tag**

```bash
gh api "repos/snok/container-retention-policy/contents/README.md?ref=v3.1.0" --jq .content > "$TMP/snok_b64.txt"
python -c "import base64,sys; sys.stdout.write(base64.b64decode(open(sys.argv[1]).read()).decode())" "$TMP/snok_b64.txt" > "$TMP/snok_readme.md"
grep -n -i -A6 "image-tags" "$TMP/snok_readme.md"
grep -n -i -B2 -A4 "multiple tags\|several tags\|any of\|all of\|negat\|exclude" "$TMP/snok_readme.md"
```

(`$TMP` is the session scratchpad directory.) Write down the sentence for each fact, verbatim, for Step 5's comment.

- [ ] **Step 2: Write the failing tests**

Create `tests/dev/test_pin_stable_image.py`:

```python
"""v221 (v220 spec Section 2): pin-stable-image.yml retags a stable point's two
images `stable-...` with the run's GITHUB_TOKEN (the VM's GHCR login is read
only), and registry-retention.yml never prunes a `stable-*` tag."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
PIN = WORKFLOWS / "pin-stable-image.yml"
RETENTION = WORKFLOWS / "registry-retention.yml"
NAME_RE = "^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$"


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(wf):
    return wf.get("on", wf.get(True))   # PyYAML reads a bare `on:` key as True


def _pin_job():
    return _load(PIN)["jobs"]["pin"]


def _runs():
    return [s["run"] for s in _pin_job()["steps"] if "run" in s]


def test_dispatch_only_with_three_required_inputs():
    wf = _load(PIN)
    on = _on(wf)
    assert set(on) == {"workflow_dispatch"}
    inputs = on["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"name", "bot_image", "db_image"}
    assert all(i["required"] is True and i["type"] == "string" for i in inputs.values())
    assert wf["run-name"] == "pin ${{ inputs.name }}"


def test_token_scope_is_packages_write_and_contents_read():
    job = _pin_job()
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    login = next(s for s in job["steps"] if "docker/login-action" in s.get("uses", ""))
    assert login["with"]["registry"] == "ghcr.io"
    assert login["with"]["password"] == "${{ secrets.GITHUB_TOKEN }}"


def test_inputs_never_reach_a_shell_script_by_interpolation():
    runs = _runs()
    assert runs
    for run in runs:
        assert "${{" not in run


def test_inputs_are_validated_before_any_retag():
    texts = [s.get("run", "") for s in _pin_job()["steps"]]
    validate = next(i for i, t in enumerate(texts) if NAME_RE in t)
    retag = next(i for i, t in enumerate(texts) if "imagetools create" in t)
    assert validate < retag
    v = texts[validate]
    assert "tr '[:upper:]' '[:lower:]'" in v
    assert '"$BASE:"*' in v and '"$BASE-db:"*' in v and "*@*" in v
    assert "^[A-Za-z0-9_.-]+$" in v


def test_retag_is_registry_side_for_both_images():
    run = next(t for t in _runs() if "imagetools create" in t)
    assert 'for SRC in "$BOT_IMAGE" "$DB_IMAGE"' in run
    assert 'DEST="${SRC%:*}:$NAME"' in run
    assert 'docker buildx imagetools create -t "$DEST" "$SRC"' in run
    assert "docker pull" not in run and "docker push" not in run


def _retention_step():
    return _load(RETENTION)["jobs"]["prune"]["steps"][0]


def test_retention_never_prunes_latest_or_stable_tags():
    tags = [t.strip() for t in _retention_step()["with"]["image-tags"].split(",")]
    assert tags == ["!latest", "!stable-*"]


def test_retention_exclusion_quotes_the_action_readme():
    text = RETENTION.read_text(encoding="utf-8")
    assert "snok/container-retention-policy v3.1.0 README:" in text
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_pin_stable_image.py`
Expected: FAIL — `FileNotFoundError` for `pin-stable-image.yml`, and the retention test sees `["!latest"]`.

- [ ] **Step 4: Write the workflow**

Create `.github/workflows/pin-stable-image.yml`:

```yaml
name: Pin stable images

# v221 (v220 spec Section 2): a stable point's two images get a
# `stable-YYYY-MM-DD[-N]` tag, which registry-retention.yml never prunes, so
# `/rollback stable-...` and restore_stable.sh can still pull them months later.
# The VM's GHCR login is a read-only PAT, so the retag happens here with the
# run's GITHUB_TOKEN. The /stable-snapshot skill starts it after the VM
# snapshot (gh workflow run pin-stable-image.yml -f name=... -f bot_image=...
# -f db_image=...) and waits for the run titled "pin <name>".
run-name: pin ${{ inputs.name }}

on:
  workflow_dispatch:
    inputs:
      name:
        description: "Stable point name, stable-YYYY-MM-DD[-N]"
        required: true
        type: string
      bot_image:
        description: "The manifest's bot_image (ghcr.io/<owner>/<repo>:sha-<12>)"
        required: true
        type: string
      db_image:
        description: "The manifest's db_image (ghcr.io/<owner>/<repo>-db:<tag>)"
        required: true
        type: string

concurrency:
  group: pin-stable-image-${{ inputs.name }}
  cancel-in-progress: false

jobs:
  pin:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      packages: write        # GITHUB_TOKEN pushes the two new tags
    steps:
      # Inputs reach the shell through env only: an input is never pasted into
      # a script, so a crafted value cannot run a command.
      - name: Validate the inputs
        env:
          NAME: ${{ inputs.name }}
          BOT_IMAGE: ${{ inputs.bot_image }}
          DB_IMAGE: ${{ inputs.db_image }}
          REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          BASE="ghcr.io/$(echo "$REPO" | tr '[:upper:]' '[:lower:]')"
          fail() { echo "::error::$1"; exit 1; }
          [[ "$NAME" =~ ^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$ ]] || fail "name must match stable-YYYY-MM-DD[-N], got '$NAME'"
          [[ "$BOT_IMAGE" == "$BASE:"* && "$BOT_IMAGE" != *@* ]] || fail "bot_image must be $BASE:<tag>, got '$BOT_IMAGE'"
          [[ "$DB_IMAGE" == "$BASE-db:"* && "$DB_IMAGE" != *@* ]] || fail "db_image must be $BASE-db:<tag>, got '$DB_IMAGE'"
          for TAG in "${BOT_IMAGE#"$BASE:"}" "${DB_IMAGE#"$BASE-db:"}"; do
            [[ "$TAG" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "bad source tag '$TAG'"
          done
          echo "Pinning $BOT_IMAGE and $DB_IMAGE as $NAME"

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # Registry-side copy of the same manifest (publish-image's precedent in
      # deploy.yml): no pull, no rebuild. A source GHCR no longer has fails here.
      - name: Tag both images
        env:
          NAME: ${{ inputs.name }}
          BOT_IMAGE: ${{ inputs.bot_image }}
          DB_IMAGE: ${{ inputs.db_image }}
        run: |
          set -euo pipefail
          for SRC in "$BOT_IMAGE" "$DB_IMAGE"; do
            DEST="${SRC%:*}:$NAME"
            docker buildx imagetools create -t "$DEST" "$SRC"
            echo "Pinned $SRC as $DEST"
          done
```

- [ ] **Step 5: Exclude `stable-*` from retention**

In `.github/workflows/registry-retention.yml`, replace the two lines

```yaml
          # Never the moving tag, and never an untagged version that a
          # multi-arch manifest still references.
          image-tags: "!latest"
```

with (the two quoted sentences are the ones Step 1 wrote down, verbatim):

```yaml
          # Never the moving tag, and never an untagged version that a
          # multi-arch manifest still references. v221: never a `stable-*`
          # tag either -- pin-stable-image.yml adds one to both images of every
          # stable point, and the version keeps its `sha-` tag beside it.
          # snok/container-retention-policy v3.1.0 README: "<the README's sentence on the image-tags negation syntax>"
          # snok/container-retention-policy v3.1.0 README: "<the README's sentence saying a version with any excluded tag is kept>"
          image-tags: "!latest,!stable-*"
```

The two `<…>` markers are filled with the Step 1 quotes before committing; a commit with a marker still in it fails review. Leave every other line of the step unchanged (`tests/dev/test_ci_db_image.py::test_ghcr_retention_covers_the_rollback_window_for_both_images` pins `cut-off` and `image-names`).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_pin_stable_image.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/dev/test_ci_db_image.py`
Expected: PASS, `0 failed`.

Run: `grep -n "<the README" .github/workflows/registry-retention.yml`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/pin-stable-image.yml tests/dev/test_pin_stable_image.py
git commit -m "ci(v221): pin-stable-image workflow retags a stable point's images with GITHUB_TOKEN"
git add .github/workflows/registry-retention.yml
git commit -m "ci(v221): registry retention never prunes stable-* tags"
```

(If Step 1 stopped the retention edit, commit nothing and report to the controller with the README's wording: the test file pins both halves, so it never lands half green.)

### Task V221-3: `/stable-snapshot` pins images and reports rollback fields

**Model:** haiku — fixed skill text from this plan

**Files:**
- Modify: `.claude/skills/stable-snapshot/SKILL.md` (Step 1, Step 2, new Step 4b, Step 7, the gate)
- Modify: `.agents/skills/stable-snapshot/SKILL.md` (generated by `python scripts/dev/sync_codex.py`, never edited by hand)
- Modify: `tests/hooks/test_skill_shape.py` (append one test)
- Modify: `AGENTS.md` (the `stable-snapshot` entry of the explicit-only rituals list)

**Interfaces:**
- Consumes: V221-1 manifest fields `alembic_head`, `bot_version`, `ui_version`, `config_keys_sha256`, `features`; V221-2 workflow `pin-stable-image.yml` (inputs `name`, `bot_image`, `db_image`; run title `pin <name>`); v220 `python scripts/ops/rollback_plan.py floor <sha> [--repo DIR]` (`above floor` exit 0, `below floor: …` lines exit 2) and the `/rollback` skill (V220-15). Check first: `git grep -n "def floor_violations" scripts/ops/rollback_plan.py` and `ls .claude/skills/rollback/SKILL.md`; a miss means v220 is not merged, stop.
- Produces: nothing a later task consumes.

Decisions (spec Section 2):
- The pin runs after the VM snapshot and before the git tag: a failed pin stops the skill like a failed snapshot does (the VM folder stays, nothing is tagged), because an unpinned point names images that retention will prune.
- The report adds the feature list, the `/rollback stable-<name>` command next to the existing restore command, and the floor verdict.
- A deploy hold (v220) means the VM runs a rollback target, not `main`; Step 2 names it so the refusal is explained, not just a sha mismatch.
- Existing pinned strings stay (`tests/hooks/test_skill_shape.py::test_backup_skills_match_the_v120_final_fixes`): `runuser -u deploy -- git -C /opt/swing-bot rev-parse HEAD`, `do NOT tag`, `` `bot_image` ``, `` `db_image` ``, `image references`, `deletes the .partial by hand`, `re-runs Step 6 only`, `` main tree's `backups/ ``, and the word "digest" never appears.

- [ ] **Step 1: Write the failing test**

Append to `tests/hooks/test_skill_shape.py`:

```python
def test_stable_snapshot_pins_images_and_reports_rollback_fields():
    """v221 (v220 spec Section 2): images pinned before the tag, report carries
    the features, the /rollback command and the floor verdict."""
    snap = (SKILLS_DIR / "stable-snapshot" / "SKILL.md").read_text(encoding="utf-8")
    pin, tag = snap.index("## Step 4b"), snap.index("## Step 5")
    assert pin < tag
    step = snap[pin:tag]
    assert "gh workflow run pin-stable-image.yml" in step
    assert "-f name=<name> -f bot_image=<bot_image> -f db_image=<db_image>" in step
    assert 'displayTitle=="pin <name>"' in step
    assert "gh run watch <id> --exit-status" in step
    assert "do NOT tag" in step
    report = snap[snap.index("## Step 7"):]
    for needle in ("`features`", "`alembic_head`", "`config_keys_sha256`",
                   "/rollback stable-<name>", "python scripts/ops/rollback_plan.py floor <git_sha>"):
        assert needle in report, needle
    assert "backups/deploy_hold.json" in snap[snap.index("## Step 2"):snap.index("## Step 3")]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — `ValueError: substring not found` (`## Step 4b`).

- [ ] **Step 3: Edit the skill**

In `.claude/skills/stable-snapshot/SKILL.md`:

(a) Step 1: after the sentence ending `then \`docs/deploy/DB_RESTORE.md\`.` add:

```markdown
The rollback fields and image pinning (v221) come from Section 2 of
`docs/superpowers/specs/2026-11-08-v220-code-only-rollback-design.md`.
```

(b) Step 2: after the bullet `- VM: \`cd /opt/swing-bot && docker compose ps\` shows \`bot\` and \`admin\` running.` add:

```markdown
- VM: no deploy hold, `test ! -e /opt/swing-bot/backups/deploy_hold.json`.
  While `/rollback` holds deploys the VM runs a rollback target, not `main`,
  so it is never a stable point; release first (`/rollback --release`).
```

(c) Insert a new section between Step 4 and Step 5:

````markdown
## Step 4b — Pin both images

The VM's GHCR login is read only, so a workflow tags the manifest's two
image references `<name>` (registry pruning skips `stable-*` tags):

```bash
gh workflow run pin-stable-image.yml -f name=<name> -f bot_image=<bot_image> -f db_image=<db_image>
gh run list --workflow pin-stable-image.yml -L 5 --json databaseId,displayTitle --jq '.[] | select(.displayTitle=="pin <name>") | .databaseId'
gh run watch <id> --exit-status
```

`<bot_image>` and `<db_image>` are the manifest's `bot_image` and `db_image`.
If `gh run list` prints nothing yet, wait a few seconds and list again. If the
run fails, re-run it once (`gh run rerun <id>`); a second failure: stop, do
NOT tag, and report the run's log (`gh run view <id> --log-failed`). The VM
folder stays.
````

(d) Replace the whole Step 7 section body with:

```markdown
Name, manifest summary (git SHA, both images, restic id, table count, bytes),
and the rollback fields: `alembic_head`, `bot_version` / `ui_version`,
`config_keys_sha256` (first 12 characters) and the `features` list, one line
per entry as `<plan or -> <sha 8> <subject>`. Then:

- the floor verdict from `python scripts/ops/rollback_plan.py floor <git_sha>`
  (`above floor`, or each `below floor:` line: a code-only rollback to this
  point would be refused);
- the code-only rollback command `/rollback stable-<name>` (keeps every
  trade; see the `rollback` skill);
- the whole-bot restore command `scripts/ops/restore_stable.sh <name> --dry-run`.
  Say a real restore needs `--i-mean-it`; this skill never runs one, nor a
  rollback.
```

(e) Replace the gate sentence with:

```markdown
The VM folder, both `<name>` image tags, the pushed git tag and the main
tree's `backups/stable/<name>/` all exist.
```

- [ ] **Step 4: Update `AGENTS.md`**

Replace `` `stable-snapshot` (pin a known-good point) `` with `` `stable-snapshot` (pin a known-good point and its images) ``; leave the rest of that list unchanged.

- [ ] **Step 5: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py`
Then: `python scripts/dev/sync_codex.py --check`
Expected: exit 0, no drift.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS, `0 failed` (the v120 test included: no "digest", "do NOT tag" kept).

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/stable-snapshot/SKILL.md .agents/skills/stable-snapshot/SKILL.md tests/hooks/test_skill_shape.py AGENTS.md
git commit -m "docs(v221): /stable-snapshot pins both images and reports rollback fields, floor and /rollback command"
```

### Task V221-4: Rollback docs: `DB_RESTORE.md` comparison, `schema-evolution.md`, `schema-change` skill

**Model:** haiku — fixed doc text from the v220 spec's "Repo bookkeeping" section

Moved here from the v220 plan (formerly V220-16) when V220-9 split into V220-9/V220-9b and v220 had to stay inside the 20-task cap.

**Files:**
- Modify: `docs/deploy/DB_RESTORE.md` (comparison table under the heading V220-18 created)
- Modify: `docs/claude/schema-evolution.md` (new last section)
- Modify: `.claude/skills/schema-change/SKILL.md` (gate line, one wrong-turn row)
- Modify: `AGENTS.md` (condensed `schema-evolution.md` line)
- Modify: `.agents/skills/schema-change/SKILL.md` (generated by `python scripts/dev/sync_codex.py`)
- Test: `tests/scripts/test_rollback_docs.py` (new, suite `tooling`)

**Interfaces:**
- Consumes: v220 merged on `main`, including V220-18's `## Code-only rollback (v220)` heading and drill record in `docs/deploy/DB_RESTORE.md` (`git grep -n "^## Code-only rollback (v220)" docs/deploy/DB_RESTORE.md`; missing means stop); `ROLLBACK_SAFE` (v220 V220-3) and `INCOMPATIBLE_BOUNDARIES` (v220 V220-2), named only.
- Produces: nothing a later task consumes.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_rollback_docs.py`:

```python
"""The rollback rules are written where a migration author and an operator look
(v220 spec, Repo bookkeeping; moved to v221 V221-4)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_schema_evolution_states_the_rollback_rules():
    text = _read("docs/claude/schema-evolution.md")
    section = text[text.index("## Rollback safety (v220)"):]
    for needle in ("ROLLBACK_SAFE", "INCOMPATIBLE_BOUNDARIES", "scripts/ops/rollback_migrations.py",
                   "scripts/ops/rollback_plan.py", "op.get_bind()"):
        assert needle in section


def test_the_schema_change_gate_names_both_rollback_markers():
    text = _read(".claude/skills/schema-change/SKILL.md")
    gate = text[text.index("## The gate"):text.index("## Known wrong turns")]
    assert "ROLLBACK_SAFE" in gate and "INCOMPATIBLE_BOUNDARIES" in gate
    assert "Older code just ignores the new field" in text


def test_db_restore_compares_the_three_rollback_paths_above_the_drill():
    text = _read("docs/deploy/DB_RESTORE.md")
    section = text[text.index("## Code-only rollback (v220)"):]
    table = section[:section.index("### Drill")]
    for needle in ("`rollback_to.sh", "`restore_stable.sh", "`/rollback", "untouched", "/rollback --release"):
        assert needle in table
    assert "rollback_code.sh" in text[:text.index("## Commands")]


def test_agents_md_carries_the_condensed_rule():
    assert "ROLLBACK_SAFE" in _read("AGENTS.md")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_docs.py`
Expected: FAIL (`ValueError: substring not found` for `## Rollback safety (v220)`).

- [ ] **Step 3: Write the docs**

Append to `docs/claude/schema-evolution.md`:

```markdown

## Rollback safety (v220)

`/rollback` (`scripts/ops/rollback_code.sh`) runs older code on today's
database, so every revision says whether older code survives it:

- `scripts/ops/rollback_migrations.py` reads each revision's `upgrade()` with
  `ast`. Safe without a note: `op.create_table`, `op.create_index`,
  `op.add_column` with `nullable=True` or a `server_default`, and literal
  `op.execute` SQL that only creates tables or indexes, inserts or comments.
  Anything else refuses a rollback across the revision: drops, `alter_column`,
  renames, `rename_doc_field`/`drop_doc_field`, `CREATE OR REPLACE` of a
  function, trigger or view, `op.get_bind()`, `conn.execute`, non-literal SQL,
  any helper call.
- A revision unsafe by that rule but harmless to older code declares
  `ROLLBACK_SAFE = "<reason>"` at module level. The reason says what older code
  does with the new shape, never "reviewed" or "fine"; the `/rollback` report
  prints it.
- A change that makes older code unsafe against new data without a schema
  change (a stored field older code strips on re-save, a queue older code
  drains destructively, a heartbeat key it misreads) adds an
  `INCOMPATIBLE_BOUNDARIES` entry `(sha, plan, reason)` to
  `scripts/ops/rollback_plan.py` in the same plan. No rollback reaches below it.
```

In `.claude/skills/schema-change/SKILL.md`, append to the end of `## The gate` (after the `scripts/ops/rollback_to.sh` sentence):

```markdown
Every new revision states its rollback safety: `ROLLBACK_SAFE = "<reason>"`
only with a real reason, and an `INCOMPATIBLE_BOUNDARIES` entry in
`scripts/ops/rollback_plan.py` when older code would mishandle the new data
(`docs/claude/schema-evolution.md` § Rollback safety).
```

and add this row at the end of the `## Known wrong turns` table:

```markdown
| "Older code just ignores the new field" | Pre-v116 code strips unknown JSONB fields on re-save; such a break is an `INCOMPATIBLE_BOUNDARIES` entry, or `/rollback` lets old code damage new rows. |
```

In `AGENTS.md`, replace the line `- \`schema-evolution.md\`: changing a table's shape or a stored record's fields.` with:

```markdown
- `schema-evolution.md`: changing a table's shape or a stored record's fields;
  every revision states rollback safety (`ROLLBACK_SAFE`, `INCOMPATIBLE_BOUNDARIES`).
```

In `docs/deploy/DB_RESTORE.md`, add after the opening `**Rollback is …**` paragraph (before the blank lines above "An unexercised restore"):

```markdown
**To put back only the code and keep every trade:** `/rollback <target>`
(`scripts/ops/rollback_code.sh`, v220), compared below in "Code-only rollback (v220)".
```

and insert directly under the `## Code-only rollback (v220)` heading, above V220-18's `### Drill` record:

```markdown
Three ways back, for different damage:

| | `rollback_to.sh "<UTC>"` (v116) | `restore_stable.sh <name>` (v120) | `/rollback <target>` (`rollback_code.sh`, v220) |
|---|---|---|---|
| Postgres | restored to the second (pgBackRest PITR) | restored from the point's dump | untouched: every trade, plan and journal row stays |
| Code and bot image | of the target | of the point | of the target |
| db image | of the target | of the point | unchanged |
| `.env` | of the target | of the point | current; only the `SWING_BOT_IMAGE` pin moves |
| `market_data/` | restic, at the target | restic, of the point | untouched |
| Targets | any second in the last 30 days | one stable point | stable point, sha, `vNNN[-before\|-after]`, `bot-A.B.C`, UTC date, at or above the compatibility floor |
| Refuses when | the second is outside the PITR history | the manifest fails verify, an image is gone | any of the eight safety checks fails |
| Afterwards | scanning paused | scanning paused | scanning keeps running; every deploy is held until `/rollback --release` |

Use `/rollback` when a release misbehaves and the data is sound; use the other two when the data itself is damaged.
```

- [ ] **Step 4: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py` then `python scripts/dev/sync_codex.py --check`
Expected: `.agents/skills/schema-change/SKILL.md` updated; `--check` exits 0.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_docs.py`, then `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py` and `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: `0 failed` each (the skill stays under its 80-line budget; no bare threshold added).

- [ ] **Step 6: Commit**

```bash
git add docs/deploy/DB_RESTORE.md docs/claude/schema-evolution.md .claude/skills/schema-change/SKILL.md .agents/skills/schema-change/SKILL.md AGENTS.md tests/scripts/test_rollback_docs.py
git commit -m "docs(v221): rollback docs -- three-way comparison in DB_RESTORE.md, ROLLBACK_SAFE and INCOMPATIBLE_BOUNDARIES rules (moved from v220)"
```

### Task V221-5: Release: bot patch, version history

**Model:** haiku — fixed `VERSION.json` bump and regeneration

**Files:**
- Modify: `VERSION.json` (`bot`, `bot_updated`)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: V221-1..V221-4 merged into the worktree.
- Produces: nothing.

Decisions (header `**Bump:** bot patch`; `.claude/skills/close-out/SKILL.md` Step 4):
- Only the `bot` line moves: the change touches ops scripts, a workflow, skills and docs, no admin UI. Bump the patch number of whatever `bot` is on the branch at this moment (v220's own release lands first, so expect one patch above it); `ui` and `ui_updated` stay.
- Two commits, bump then regenerate, in that order.

- [ ] **Step 1: Read the current versions**

Run: `python -c "import json; v=json.load(open('VERSION.json')); print(v['bot'], v['bot_updated'])"`
Expected: the current `bot` version, e.g. `2.17.4 2026-11-…` (whatever v220 released).

- [ ] **Step 2: Bump the bot patch**

Edit `VERSION.json`: `bot` becomes the next patch (`A.B.C` → `A.B.(C+1)`), `bot_updated` becomes now in the existing format `YYYY-MM-DD HH-MM-SS` (local time, as the existing stamps). Leave `ui` and `ui_updated` unchanged.

- [ ] **Step 3: Verify the file still parses and only bot moved**

Run: `git diff --stat VERSION.json` and `python -c "import json; json.load(open('VERSION.json'))"`
Expected: one file, two changed lines; no exception.

- [ ] **Step 4: Commit the bump**

```bash
git add VERSION.json
git commit -m "release(bot): <new version> -- stable snapshots carry rollback fields and pinned images"
```

- [ ] **Step 5: Regenerate the version history**

Run: `python scripts/dev/build_version_matrix.py`
Expected: `swingbot/admin/version_history.json` changes and names the new bot version.

Run: `git diff --stat swingbot/admin/version_history.json`
Expected: one file changed (no test pins this file; the close-out gate reads it).

- [ ] **Step 6: Commit the regeneration**

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <new version> -- stable snapshots carry rollback fields and pinned images"
```

