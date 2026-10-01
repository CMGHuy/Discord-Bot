# Stable snapshots and off-VM backup pull — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle. Steps use `- [ ]` for tracking; read the spec with the task.

**Goal:** A `/stable-snapshot` skill that pins a full known-good point (tag, images, `.env`, dump, market_data restic snapshot) and a manual `/backup-pull` that brings a verified rebuild-from-zero set to this machine.
**Architecture:** One stdlib Python helper (`backup_manifest.py`) owns manifest build/verify/prune/naming; thin bash scripts do the VM-side staging (`stable_snapshot.sh`, `restore_stable.sh`) and the dev-side transfer (`pull_backups.sh`) over `ssh-hetzner.sh`; two Tier 2 skills are the checklists; the SessionStart hook shows pull age.
**Tech Stack:** Bash, Python 3.11 stdlib, pytest, PowerShell (hook), restic, pg_dump.
**Spec:** `docs/superpowers/specs/2026-10-01-v120-stable-snapshots-offsite-pull-design.md`
**Bump:** none
**Edge:** none (integrity)
**Progress:** V120-1 to V120-7 implemented and reviewed on branch `2026-10-01-v120-stable-snapshots-offsite-pull` (17 commits, rebased onto `origin/main` 33580cbc on 2026-10-01 night; not pushed, not merged). V120-10's full-suite gate has not passed yet (see "Status as built"). V120-8 and V120-9 are live production tasks and wait for the partner.

## Status as built (2026-10-01 night) -- read before V120-8, V120-9 and V120-10

**Branch.** `2026-10-01-v120-stable-snapshots-offsite-pull`, 17 commits replayed with `git rebase --onto origin/main 8490329c`
(old pre-rebase tip `537623e0`), 0 behind and 17 ahead of `origin/main`. Every v120 test file passes on it. Reviews: one task review
per task, a whole-branch review on the most capable model, and two targeted re-reviews. Nothing is merged, pushed or deployed.

**Deviations from the task text below** (the text is the original argument; the code is the truth; rulings are in the SDD ledger
`.superpowers/sdd/2026-10-01-v120-stable-snapshots-offsite-pull/progress.md` while that workspace exists):
- Row counts are derived from the dump by `backup_manifest.py count-dump` (COPY blocks), not a live `count(*)`. Keys are schema-qualified
  (`public.trades`, quotes stripped). Other new subcommands: `report-market`; `build` also takes `--pg-version`.
- `market_data.tar` is KEPT in each pull folder (the manifest lists it, so a retained pull must still verify); it goes with the folder on prune.
- `prune --keep` below 1 is rejected. Incremental market_data selection uses ctime (`-newerct`) and reports files absent locally or with
  a different size, report only.
- `pull_backups.sh` keeps `backups/` in the MAIN tree (`git rev-parse --git-common-dir`), `SWINGBOT_BACKUPS_DIR` overrides it; any abort
  after a pull folder exists renames it `<stamp>.FAILED` and writes `LAST_PULL ... FAIL`; local `tar` uses `--force-local` (a drive-letter
  path is read as `host:file` otherwise); a stale VM outbox is swept after two hours.
- VM-side git runs as `runuser -u deploy -- git`; `stable_snapshot.sh` and `restore_stable.sh` refuse an empty git sha before any mutation;
  `restore_stable.sh` runs from `main()`, refuses a dirty tree, recreates db on the pinned image before `restore_db.sh`; the restic
  snapshot is taken under `flock logs/restic.lock`, and a failed run forgets its own restic snapshot.
- The BACKUP hook line uses ` | ` (ASCII), not a middle dot, and warns when the pull folder named in `LAST_GOOD_PULL` is missing.

**Spec statements now stale -- amend the spec at close-out** (`docs/superpowers/specs/2026-10-01-v120-stable-snapshots-offsite-pull-design.md`):
(1) section 3 row_counts and the subcommand/flag lists; (2) section 2 pull folder also holds `market_data.tar`; (3) section 2 overdue line:
warns from 8 whole days, no-pull wording, ASCII separator; (4) section 1 order: the restic snapshot is taken before the manifest, the folder is
built as `<name>.partial` and renamed last, a failed run forgets its restic snapshot; (5) section 1 restore: no flag prints the plan and exits 2,
dirty-tree refusal, checkpoint of now, db recreated on the pinned image, logged to `logs/rollback.log`; (6) manifest holds image
REFERENCES (immutable `sha-` tags), not digests (also in the stable-snapshot skill's old wording); (7) section 2 the outbox trap is client-side
only; (8) failure bookkeeping and the extra `stream-stable` mode; (9) the drill compares schema-qualified keys; (10) `backups/` lives in the main tree.

**Deferred on purpose:** atomic claim of the pull stamp (two sessions pulling in the same UTC minute); `flock -w` plus a locked cleanup forget in
`stable_snapshot.sh`; first-pull progress output; a rotated DB password inside a pinned env; `DROP DATABASE` in `restore_db.sh` blocked by a cron
connection; small leftovers (hook on git older than 2.31 in the main tree, one heuristic test regex, an unguarded `mkdir` in the trap).

**Production on 2026-10-01 21:43 UTC (read-only inspection, re-check before every live step -- it moves):** `33580cbc` "docs(v116): close out",
bot image `sha-33580cbc3368`, two deploys 7 minutes apart that evening; containers healthy; checkout clean; bot 2.0.0 (stores are Postgres-only),
Postgres 18.6, 2 open trades. VM tools: python3 3.14.4, runuser, flock, restic 0.18.1, GNU tar 1.35, Docker Compose v5. `runuser -u deploy -- git`
and root git both work; root can `docker manifest inspect` the deployed image. `/` is 65% used with 13 GB free; `market_data` is 183 MB in 520 files
with no Windows-unsafe names; `logs/` is root-owned, so v120 scripts must run as root (the ssh wrapper is root). No v120 script is on the VM
and the deployed `restic_hourly.sh` has no `--keep-tag` yet. Crons: `backup_db.sh` 03:00, `pitr_backup.sh` 02:30 (no `logs/pitr_backup.log` yet: that
cron was installed after today's 02:30, so its first run is 2026-10-02 02:30 UTC), `restic_hourly.sh` at :07, `pitr_verify.sh` monthly. The nightly-dump
retention in `DEPLOY_HETZNER.md` already says 90 days (corrected upstream). Any v120 script piped to `ssh ... "bash -s"` must give every
`docker compose exec` a `</dev/null`, or the exec swallows the rest of the script (the shipped stage script does).

**Test database.** `origin/main` now carries `be3ec50f` (the schema-free fixture gets its own database) and the autouse store-truncation fixture.
Three full runs on 2026-10-01 each failed on a different unrelated shared-database or timing test, `main` included; the follow-up branch
`2026-10-01-db-test-isolation-followup` makes database names unique per checkout so concurrent sessions stop colliding.

## Global constraints

- Every ops script: `#!/usr/bin/env bash`, `set -euo pipefail`, LF endings, no `sed -i` (the house rules pinned by `tests/scripts/test_pitr_crons.py`).
- The dev side reaches the VM **only** through `bash scripts/ops/ssh-hetzner.sh` (CLAUDE.md), piping the remote script over stdin with `"bash -s"` — never an inline `$(...)` (see the comment in `pull_prod_snapshot.sh`). Make the wrapper path overridable via `SSH_HETZNER`, as `pull_prod_snapshot.sh` does.
- `backup_manifest.py` is standard library only — it runs under the VM host's `python3` and on Windows.
- Nothing on the pull path ever deletes a file under local `backups/market_data/` or `backups/stable/`.
- Never create a `stable-*` **branch**; never touch the three existing `stable-*` branches (`git-safety.md`).
- Functions written or changed stay below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>`).
- Each task runs its own test file with `python scripts/dev/testrun.py file <file>`; the full suite runs once, in V120-10.
- V120-8 and V120-9 touch production: invoke `mirror-prod` first; read `docs/deploy/DB_RESTORE.md` and `DEPLOY_HETZNER.md`.

## File map and interfaces

| File | Responsibility |
|---|---|
| `scripts/ops/backup_manifest.py` (new) | `build`, `verify`, `prune`, `next-name` subcommands. |
| `scripts/ops/restic_hourly.sh` | `forget` gains `--keep-tag stable`. |
| `scripts/ops/stable_snapshot.sh` (new, VM) | Pins `backups/stable/<name>/` + restic snapshot; prints manifest JSON. |
| `scripts/ops/restore_stable.sh` (new, VM) | Restores a pinned point; `--dry-run`, `--i-mean-it`. |
| `scripts/ops/pull_backups.sh` (new, dev) | Stage → stream → clean; verify; extract; prune; `--stable <name>`. |
| `.ignore` | Adds `backups/`. |
| `.claude/hooks/session-cursor.ps1` | `BACKUP   :` line. |
| `.claude/skills/stable-snapshot/SKILL.md`, `.claude/skills/backup-pull/SKILL.md` (new) | Tier 2 checklists. |
| `tests/scripts/test_backup_manifest.py`, `test_stable_snapshot_shape.py`, `test_restore_stable_shape.py`, `test_pull_backups_shape.py`, `test_backups_ignored.py` (new) | Tests. |

## Review focus

1. A failed verify must leave `LAST_GOOD_PULL` untouched and must not extract `market_data.tar` (V120-5).
2. `prune` must never delete anything outside `backups/pulls/` (V120-1).
3. The tag is created only after the VM folder and manifest exist (V120-7 skill order).
4. `restore_stable.sh` changes nothing without `--i-mean-it`, and pauses scanning before starting the bot (V120-4).
5. The hook never fails a session start, even with a garbage `LAST_GOOD_PULL` (V120-6).

## Parallelisation

- **Phase 1:** V120-1 first — V120-3, V120-4 and V120-5 call its CLI. V120-2 is independent (any time). After V120-1, V120-3 / V120-4 / V120-5 touch disjoint files and can run in parallel; V120-6 is independent of all of them.
- **Phase 2:** V120-7 (skills) needs V120-3 and V120-5 to exist so its steps name real flags.
- **Phase 3:** Serial. V120-8 needs everything merged **and deployed** (scripts reach the VM only through `deploy.sh`); V120-9 needs V120-8's good pull (its `--since` and the local mirror); V120-10 is the sole full-suite task.

# Phase 1 — Helper and scripts

### Task V120-1: backup_manifest.py

**Files:** Create `scripts/ops/backup_manifest.py`, `tests/scripts/test_backup_manifest.py`.

**Interfaces:**
- `build_manifest(folder: Path, *, git_sha=None, deploy=None, restic_id=None, row_counts=None, pg_server_version=None, vm_epoch=None, market_files=None) -> dict` — writes `folder/manifest.json` and returns it. Keys: `schema` (1), `created_utc` (ISO, `Z`), `vm_epoch`, `git_sha`, `bot_image`, `db_image` (from `deploy` dict, else `null`), `restic_id`, `row_counts`, `pg_server_version`, `files` (`name -> {"sha256", "bytes"}` for every regular file directly in `folder` except `manifest.json`), `market_files` (`path -> bytes` or `null`).
- `verify_folder(folder: Path) -> list[str]` — empty list = PASS. Problems: missing manifest, listed file missing, size mismatch, sha256 mismatch, unlisted file present, any `*.gz` that fails a full `gzip` read.
- `prune_pulls(backups: Path, keep: int = 10) -> list[Path]` — operates only on `backups/pulls/`. Keeps the newest `keep` good folders (name sort; names are `YYYY-MM-DDTHH-MMZ`); removes good folders beyond that and `*.FAILED` folders whose stamp is older than the newest good one. Returns what it removed. Raises `ValueError` if `backups/pulls` resolves outside `backups`.
- `next_stable_name(date: str, existing: set[str]) -> str` — `stable-<date>`, else `-2`, `-3`, …
- CLI: `build <dir> [--git-sha] [--deploy-json FILE] [--restic-id] [--row-counts FILE] [--pg-version] [--vm-epoch] [--market-files FILE]` (prints the manifest JSON); `verify <dir>` (prints problems, exit 1 if any, else prints `PASS`); `prune <backups> [--keep N]`; `next-name <date> --existing FILE` (one tag per line). `--market-files FILE` is `<bytes>\t<path>` lines (the VM's `find -printf '%s\t%P\n'`).

- [ ] **Step 1: Write failing tests**

```python
"""backup_manifest.py (v120 §3): the verifier is what decides whether an off-VM
copy counts, so every way a copy can be wrong must fail it."""
import gzip
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import backup_manifest as bm  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "2026-10-01T18-04Z"
    d.mkdir()
    with gzip.open(d / "db.sql.gz", "wb") as fh:
        fh.write(b"-- dump\n" * 100)
    (d / "env").write_text("TOKEN=x\n")
    (d / "deploys.jsonl").write_text('{"git_sha": "abc"}\n')
    return d


def test_round_trip_passes(folder):
    m = bm.build_manifest(folder, git_sha="abc", vm_epoch=1759341840,
                          deploy={"bot_image": "b", "db_image": "d"})
    assert m["schema"] == 1 and m["bot_image"] == "b"
    assert set(m["files"]) == {"db.sql.gz", "env", "deploys.jsonl"}
    assert bm.verify_folder(folder) == []


def test_flipped_byte_fails(folder):
    bm.build_manifest(folder)
    p = folder / "env"
    p.write_bytes(b"TOKEN=y\n")
    assert any("sha256" in e for e in bm.verify_folder(folder))


def test_missing_and_unlisted_files_fail(folder):
    bm.build_manifest(folder)
    (folder / "env").unlink()
    (folder / "stray").write_text("x")
    problems = bm.verify_folder(folder)
    assert any("missing" in e and "env" in e for e in problems)
    assert any("unlisted" in e and "stray" in e for e in problems)


def test_truncated_gzip_fails_even_with_matching_hash(folder):
    raw = (folder / "db.sql.gz").read_bytes()
    (folder / "db.sql.gz").write_bytes(raw[: len(raw) // 2])
    bm.build_manifest(folder)                      # hash matches the truncated file
    assert any("gzip" in e for e in bm.verify_folder(folder))


def test_no_manifest_fails(folder):
    assert bm.verify_folder(folder)


def _pull(root, name):
    p = root / "pulls" / name
    p.mkdir(parents=True)
    return p


def test_prune_keeps_newest_good_and_drops_older_failed(tmp_path):
    for i in range(12):
        _pull(tmp_path, f"2026-10-{i + 1:02d}T00-00Z")
    _pull(tmp_path, "2026-09-30T00-00Z.FAILED")
    _pull(tmp_path, "2026-10-13T00-00Z.FAILED")    # newer than newest good: kept
    (tmp_path / "stable" / "stable-2026-09-01").mkdir(parents=True)
    (tmp_path / "market_data").mkdir()
    removed = {p.name for p in bm.prune_pulls(tmp_path, keep=10)}
    assert removed == {"2026-10-01T00-00Z", "2026-10-02T00-00Z", "2026-09-30T00-00Z.FAILED"}
    assert (tmp_path / "stable" / "stable-2026-09-01").exists()
    assert (tmp_path / "market_data").exists()
    assert (tmp_path / "pulls" / "2026-10-13T00-00Z.FAILED").exists()


@pytest.mark.parametrize("existing,expected", [
    (set(), "stable-2026-10-01"),
    ({"stable-2026-10-01"}, "stable-2026-10-01-2"),
    ({"stable-2026-10-01", "stable-2026-10-01-2"}, "stable-2026-10-01-3"),
    ({"stable-2026-09-17"}, "stable-2026-10-01"),
])
def test_next_stable_name(existing, expected):
    assert bm.next_stable_name("2026-10-01", existing) == expected


def test_cli_verify_exit_codes(folder):
    bm.build_manifest(folder)
    cli = [sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py")]
    ok = subprocess.run(cli + ["verify", str(folder)], capture_output=True, text=True)
    assert ok.returncode == 0 and "PASS" in ok.stdout
    (folder / "env").write_text("changed")
    bad = subprocess.run(cli + ["verify", str(folder)], capture_output=True, text=True)
    assert bad.returncode == 1


def test_cli_build_reads_market_files(folder, tmp_path):
    listing = tmp_path / "mf.tsv"
    listing.write_text("120\tdaily/AAPL.csv\n7\tintraday/AAPL/2026-10-01.csv\n")
    cli = [sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py")]
    out = subprocess.run(cli + ["build", str(folder), "--market-files", str(listing)],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["market_files"]["daily/AAPL.csv"] == 120
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/scripts/test_backup_manifest.py` — expect import failure.
- [ ] **Step 3: Implement.** Hash in 1 MiB chunks. Gzip check: read the whole stream with `gzip.open(...).read(1 << 20)` in a loop, catching `OSError`/`EOFError`. `prune_pulls` splits into `_good_and_failed(pulls)` and the removal loop; `shutil.rmtree` only paths whose `resolve()` has `backups/pulls` as parent. `main(argv)` dispatches through a dict of subcommand handlers (keeps CC low). Write `manifest.json` with `sort_keys=True, indent=2`.
- [ ] **Step 4: Run** the file → green; `python -m radon cc -s -n C scripts/ops/backup_manifest.py` → no output.
- [ ] **Step 5: Commit** `feat(v120): backup_manifest.py -- build, verify, prune, next stable name`

### Task V120-2: restic keeps stable snapshots

**Files:** Modify `scripts/ops/restic_hourly.sh`, `tests/scripts/test_pitr_crons.py`.

- [ ] **Step 1: Failing test** appended to `test_pitr_crons.py`:

```python
def test_restic_forget_keeps_stable_snapshots_forever():
    """v120: a stable point's market_data must outlive the 30-day window.
    restic keeps a snapshot when ANY keep policy matches."""
    text = _text("restic_hourly.sh")
    forget = next(l for l in text.splitlines() if "restic forget" in l)
    assert "--keep-within 30d" in forget and "--keep-tag stable" in forget
```

- [ ] **Step 2:** Run the file → fails.
- [ ] **Step 3:** Change the forget line to `restic forget --host swing-bot --tag market_data --keep-within 30d --keep-tag stable --prune`. Add one comment line saying why.
- [ ] **Step 4:** Run → green.
- [ ] **Step 5: Commit** `feat(v120): restic forget keeps snapshots tagged stable`

### Task V120-3: stable_snapshot.sh (VM)

**Files:** Create `scripts/ops/stable_snapshot.sh`, `tests/scripts/test_stable_snapshot_shape.py`.

**Behaviour** (runs on the VM as root, from `/opt/swing-bot`; `stable_snapshot.sh <name>`):
1. Validate `<name>` matches `^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$`; refuse (exit 2) if `backups/stable/<name>` exists.
2. Build into `backups/stable/<name>.partial` (trap removes it on any failure), then `mv` to the final name at the end — a half snapshot never carries the final name.
3. `./scripts/ops/backup_db.sh`, then copy the newest `data/backups/db/swingbot_*.sql.gz` to `db.sql.gz` (`ls -t | head -1` taken immediately after the run).
4. `install -m 600 .env "$DIR/env"`; `tail -n 1 backups/deploys.jsonl > "$DIR/deploy.json"`.
5. Row counts: `docker compose exec -T db psql -U swingbot -d swingbot -At` with a query that emits one JSON object of exact `count(*)` per `public` base table (build it with `string_agg` over `information_schema.tables` and run the generated SQL through `\gexec`, or loop tables in bash — either way exact counts) → `$WORK/rows.json` **outside** the folder. `SHOW server_version` → `pg_version`.
6. restic: `RESTIC_PASSWORD` via `env_set.py --get` (as `restic_hourly.sh`); `restic backup --host swing-bot --tag market_data --tag stable --tag "$NAME" --json "$PWD/market_data"`, take `snapshot_id` from the `summary` message (`python3 -c` on the last line).
7. `python3 scripts/ops/backup_manifest.py build "$DIR.partial" --git-sha "$(git rev-parse HEAD)" --deploy-json "$DIR.partial/deploy.json" --restic-id "$ID" --row-counts "$WORK/rows.json" --pg-version "$PGV" --vm-epoch "$(date +%s)"` → stdout is the manifest; `verify` the folder; `mv`; log one line to `logs/stable_snapshot.log`; print the manifest as the last output.

- [ ] **Step 1: Failing shape tests**, in the style of `test_rollback_to_shape.py`: strict mode, LF, no `sed -i`; name regex present; the refusal on an existing folder comes before `backup_db.sh`; `.partial` + a `trap` that removes it; `install -m 600`; restic call carries all three `--tag`s; `backup_manifest.py build` then `verify` then the final `mv`, in that order; `logs/stable_snapshot.log`.
- [ ] **Step 2:** Run → fails. **Step 3:** Implement. **Step 4:** Run → green; `bash -n scripts/ops/stable_snapshot.sh`.
- [ ] **Step 5: Commit** `feat(v120): stable_snapshot.sh pins a full known-good point on the VM`

### Task V120-4: restore_stable.sh (VM)

**Files:** Create `scripts/ops/restore_stable.sh`, `tests/scripts/test_restore_stable_shape.py`. Read `scripts/ops/rollback_to.sh` first and reuse its pause/start and image-pin idioms verbatim.

**Behaviour** (`restore_stable.sh <name> [--dry-run | --i-mean-it]`, VM, root):
1. `DIR=backups/stable/<name>`; `backup_manifest.py verify "$DIR"` must pass, else exit 2.
2. Read `git_sha`, `bot_image`, `db_image`, `restic_id` from the manifest; `docker manifest inspect` both images (still on ghcr?) — refuse if not.
3. Print the plan. With `--dry-run`, or with neither flag, stop here (exit 0 / exit 2 with a usage line respectively).
4. `--i-mean-it`: pgBackRest `--type=diff backup` and `restic_hourly.sh` checkpoint of *now* (as `rollback_to.sh` step 2); `docker compose stop bot admin`; `restic restore "$restic_id"` into a staging dir under `backups/`, then move it over `market_data/` (the same staging-then-move pattern `rollback_to.sh` uses); `cat "$DIR/env" > .env` (in place, keeps owner), then `chown deploy:deploy .env`; `env_set.py` for `SWING_BOT_IMAGE` / db image keys from the manifest; `./scripts/ops/restore_db.sh "$DIR/db.sql.gz" swingbot --i-mean-it`; `git checkout --detach "$git_sha"`; set scanning paused exactly as `rollback_to.sh` does; `docker compose up -d --no-build --wait bot admin`; log to `logs/rollback.log` with a `restore_stable` prefix.

- [ ] **Step 1: Failing shape tests:** strict/LF/no `sed -i`; `verify` precedes everything; `docker manifest inspect` precedes `docker compose stop bot admin`; the `--dry-run` exit precedes the first mutating command (`--type=diff backup`); `--i-mean-it` is required (string present and checked before stop); step order list as in `test_rollback_to_shape.py::test_the_steps_run_in_the_spec_order` (`verify`, `docker manifest inspect`, `DRY_RUN`, `--type=diff backup`, `docker compose stop bot admin`, `restic restore`, `> .env`, `restore_db.sh`, `git checkout --detach`, `scan_paused`, `docker compose up -d --no-build --wait bot admin`).
- [ ] **Step 2–4:** Run → fails; implement; run → green; `bash -n`.
- [ ] **Step 5: Commit** `feat(v120): restore_stable.sh restores a pinned stable point`

### Task V120-5: pull_backups.sh and the ignore rules

**Files:** Create `scripts/ops/pull_backups.sh`, `tests/scripts/test_pull_backups_shape.py`, `tests/scripts/test_backups_ignored.py`; modify `.ignore`.

**Behaviour** (dev machine, Git Bash; `pull_backups.sh [--stable <name>]`):
- Common: `cd` repo root; `SSH_HETZNER` default as in `pull_prod_snapshot.sh`; `B=backups`; `STAMP=$(date -u +%Y-%m-%dT%H-%MZ)`.
- **Normal pull:**
  1. `SINCE` = third field of `backups/LAST_GOOD_PULL` minus 3600, or `0` when absent.
  2. **Stage** (remote script over stdin, run as root): `mkdir backups/outbox/$STAMP`; `backup_db.sh` and copy newest dump → `db.sql.gz`; `install -m 600 .env env`; `cp backups/deploys.jsonl`; `find market_data -type f -newermt "@$SINCE" -printf '%P\0' | tar --null -T - -C market_data -cf market_data.tar` (an empty list still produces a valid tar); `find market_data -type f -printf '%s\t%P\n' > $WORK/market_files.tsv` (outside the folder); row counts and `pg_version` as in V120-3; `backup_manifest.py build ... --market-files ... --vm-epoch "$(date +%s)"`.
  3. **Stream**: `tar czf - -C backups/outbox $STAMP | base64 -w0` → local `base64 -d | tar xzf - -C backups/pulls/`.
  4. **Clean**: a separate remote call `rm -rf backups/outbox/$STAMP`, also run from a local `trap ... EXIT` so a failed stream never leaves secrets in the outbox.
  5. `python scripts/ops/backup_manifest.py verify backups/pulls/$STAMP`. **Fail** → `mv` to `$STAMP.FAILED`, write `LAST_PULL` `"<iso> FAIL pulls/$STAMP.FAILED"`, exit 1. **Pass** → extract `market_data.tar` into `backups/market_data/`, then delete the tar; list every local mirror file absent from the manifest's `market_files` as `missing on VM: <path>` (report only, never delete); write `LAST_PULL` `"<iso> PASS pulls/$STAMP"` and `LAST_GOOD_PULL` `"<iso> pulls/$STAMP <vm_epoch>"`; `backup_manifest.py prune backups --keep 10`; print a summary (pull dir, bytes, files added, missing-on-VM count).
- **`--stable <name>`:** stream `backups/stable/<name>` from the VM into local `backups/stable/<name>.partial`, verify, `mv` to final; refuse if the local folder exists. No staging, no `LAST_*` writes.
- `.ignore`: add `backups/`.

- [ ] **Step 1: Failing tests.** Shape: strict/LF/no `sed -i`; goes through `$SSH_HETZNER` (never a bare `ssh `/`scp `); `"bash -s"`; the outbox `rm -rf` sits in a `trap`; `verify` precedes the `market_data.tar` extraction and the `LAST_GOOD_PULL` write; the FAIL branch writes `LAST_PULL` and never `LAST_GOOD_PULL`; no `rm` / `rm -rf` targets `backups/market_data` or `backups/stable` (regex over every `rm` line); `prune backups --keep 10` comes after the `LAST_GOOD_PULL` write. Ignore test:

```python
"""Pulled env files hold live tokens (v120 §2): git must never stage them."""
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path", [
    "backups/pulls/2026-10-01T18-04Z/env",
    "backups/stable/stable-2026-10-01/env",
    "backups/market_data/daily/AAPL.csv",
    "backups/LAST_GOOD_PULL",
])
def test_git_ignores_every_backup_path(path):
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO)
    assert r.returncode == 0, f"{path} is not git-ignored"


def test_search_tools_skip_backups():
    lines = (REPO / ".ignore").read_text(encoding="utf-8").splitlines()
    assert "backups/" in lines
```

- [ ] **Step 2–4:** Run both files → fail; implement; run → green; `bash -n scripts/ops/pull_backups.sh`.
- [ ] **Step 5: Commit** `feat(v120): pull_backups.sh brings a verified rebuild-from-zero set off the VM`

### Task V120-6: SessionStart backup line

**Files:** Modify `.claude/hooks/session-cursor.ps1`; create `tests/hooks/test_session_backup_line.py`.

**Behaviour:** inside the existing `try`, after the `WORKTREES` line: read `backups/LAST_GOOD_PULL` (first field ISO UTC); newest `backups/stable/*` folder name by name sort (or `none`). Age in whole days. Emit `BACKUP   : last good pull <N>d ago · newest stable <name>` when `N` is at most 7, else (or when the file is missing or unparsable) `BACKUP   : WARNING no good pull for <N>d -- run /backup-pull` / `... no good pull yet -- run /backup-pull`. Its own inner `try/catch` so a bad file prints the warning and never throws. Make the root overridable by `$env:SWINGBOT_BACKUPS_DIR` (test seam; default `backups`).

- [ ] **Step 1: Failing tests** (skip if `pwsh` is not on PATH): run `pwsh -NoProfile -File .claude/hooks/session-cursor.ps1` with `SWINGBOT_BACKUPS_DIR` set to a tmp dir holding (a) a 2-day-old `LAST_GOOD_PULL` and `stable/stable-2026-10-01/` → line contains `2d ago` and `stable-2026-10-01`; (b) a 9-day-old one → `WARNING`; (c) no file → `no good pull yet`; (d) `LAST_GOOD_PULL` containing `garbage` → `WARNING` and exit code 0.
- [ ] **Step 2–4:** Run → fail; implement; run → green.
- [ ] **Step 5: Commit** `feat(v120): SessionStart shows the age of the last good backup pull`

# Phase 2 — Skills

### Task V120-7: stable-snapshot and backup-pull skills

**Files:** Create `.claude/skills/stable-snapshot/SKILL.md`, `.claude/skills/backup-pull/SKILL.md`; modify `tests/hooks/test_skill_shape.py` (`TIER_2` gains both names), `docs/claude/skills-tools.md` (two table rows, Tier 2, slash-only, Step 1 reads the v120 spec and `docs/deploy/DB_RESTORE.md`), `AGENTS.md` (explicit-only list gains `stable-snapshot` and `backup-pull`); run `python scripts/dev/sync_codex.py` and commit the generated `.agents/skills/` output.

Frontmatter like `deploy`: `name`, a description of at least 40 characters ending "Invoked explicitly as /<name>, never model-triggered.", `disable-model-invocation: true`. Under 80 lines, no Trigger table, no bare numeric thresholds (the `_THRESHOLD_RE` in the shape test — write "the newest ten" in words).

**`stable-snapshot` steps:** 1 Read the authority (spec §1, `DB_RESTORE.md`). 2 Preconditions: `git status --porcelain` empty, branch `main`, `git rev-parse HEAD` equals `git rev-parse origin/main` after `git fetch`; on the VM `git -C /opt/swing-bot rev-parse HEAD` and the last `deploys.jsonl` `git_sha` both equal HEAD; `docker compose ps` shows `bot` and `admin` running — any miss: stop and tell the partner which. 3 Name: `git tag -l 'stable-*'` + `git ls-remote --tags origin 'stable-*'` → `backup_manifest.py next-name <UTC date> --existing`. 4 `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash scripts/ops/stable_snapshot.sh <name>"` — capture the manifest. 5 `git tag -a <name>` with the note, `ui`/`bot` from `VERSION.json` and both image digests; `git push origin <name>`; on push failure retry this step only. Never `git branch`. 6 `bash scripts/ops/pull_backups.sh --stable <name>`. 7 Report name, manifest summary (git SHA, images, restic id, table count, bytes) and the restore command `scripts/ops/restore_stable.sh <name> --dry-run`.

**`backup-pull` steps:** 1 Read spec §2. 2 `bash scripts/ops/pull_backups.sh`. 3 Report PASS/FAIL, pull folder, bytes, files added, missing-on-VM list (if any — say they were kept locally). On FAIL show the verifier's lines and stop; never delete the `.FAILED` folder by hand.

- [ ] **Step 1:** Add names to `TIER_2`; run `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py` → fails.
- [ ] **Step 2:** Write both skills, the docs rows, the `AGENTS.md` line; run `sync_codex.py`.
- [ ] **Step 3:** Run `tests/hooks/test_skill_shape.py` and `tests/hooks/test_codex_mirror.py` → green.
- [ ] **Step 4: Commit** `feat(v120): /stable-snapshot and /backup-pull skills, Codex mirror`

# Phase 3 — Live

### Task V120-8: Deploy, first pull, local restore drill

**Precondition:** V120-10's full-suite gate has passed on the rebased branch; the partner has approved the merge to `main` and the push (outward actions, never assumed); V120-1…7 are on `origin/main` and deployed (the scripts reach the VM only through the normal deploy; follow `/deploy`). Invoke `mirror-prod`. Immediately before the first live step re-read the `backups/deploys.jsonl` tail and `runuser -u deploy -- git -C /opt/swing-bot rev-parse --short HEAD` on the VM: production moved twice in 7 minutes on 2026-10-01. Confirm `python3 scripts/ops/backup_manifest.py --help` runs on the VM's python3 (3.14.4 today).

- [ ] **Step 1:** On the VM confirm the new scripts are present and the deployed `restic_hourly.sh` carries `--keep-tag stable` (`grep -c keep-tag` must be 1 or more; it was 0 before the deploy).
- [ ] **Step 2:** `bash scripts/ops/pull_backups.sh` from the MAIN tree → PASS (first pull: full `market_data/`, about 183 MB in 520 files plus a dump of about 0.5 MB; the VM has 13 GB free; the script prints no progress, so run it in the background and expect minutes). Record bytes and duration. No `FAIL`/`.FAILED` folder may result.
- [ ] **Step 3: Restore drill.** `docker run -d --name v120-drill -e POSTGRES_PASSWORD=drill -e POSTGRES_USER=swingbot -e POSTGRES_DB=swingbot -p 127.0.0.1:55434:5432 postgres:<major>`; the major comes from the manifest's `pg_server_version`, a full string such as `18.6 (Debian ...)` (production is Postgres 18, so use `postgres:18`, not 15); wait for ready; `gunzip -c backups/pulls/<stamp>/db.sql.gz | docker exec -i v120-drill psql -U swingbot -d swingbot -v ON_ERROR_STOP=1`; exact `count(*)` per table equals the manifest's `row_counts` for every key. The keys are schema-qualified (`public.trades`, quotes stripped): split at the first dot and quote both parts (`SELECT count(*) FROM "public"."Odd Name"`); never compare against `pg_stat_user_tables.n_live_tup`, which is approximate. `docker rm -f v120-drill` (no named volume is created; confirm `docker volume ls` shows no leftover anonymous volume, prune it if so).
- [ ] **Step 4:** Run `bash scripts/ops/pull_backups.sh` again → PASS with a small incremental `market_data.tar`.
- [ ] **Step 5:** Append the "Off-VM copy" section to `docs/deploy/DB_RESTORE.md` (after its "Point-in-time recovery (v116)" section): commands, the per-table count table (pull vs restored), first/second pull bytes, VERDICT. Commit `docs(v120): off-VM pull and local restore drill`.

### Task V120-9: First stable snapshot and dry-run restore; docs

- [ ] **Step 1:** Re-check the production head (as in V120-8), then `/stable-snapshot` with the note "first v120 stable point" (ask the partner to type it — Tier 2 skills are slash-only). Start between minute :10 and :55: the hourly restic job holds `logs/restic.lock` at :07 and `stable_snapshot.sh` waits on that lock without a timeout. Expect a new tag, `backups/stable/<name>/` on the VM and in the main tree's `backups/`, both verifying.
- [ ] **Step 2:** On the VM: `bash scripts/ops/restore_stable.sh <name> --dry-run` → prints the dump, restic id, both images, git SHA; changes nothing (`docker compose ps` unchanged). Also run `restic snapshots --tag stable` and confirm the id. Registry access as root was verified on 2026-10-01 (`docker manifest inspect` rc 0). Do NOT run a real `--i-mean-it` restore as part of this task: its open questions (a rotated DB password in the pinned env, `DROP DATABASE` blocked by a cron connection) are not exercised by a dry run.
- [ ] **Step 3:** Docs: `DEPLOY_HETZNER.md` — the nightly-dump retention sentence already says 90 days (corrected upstream; leave it), so only add an "Off-VM copy and stable snapshots" paragraph pointing at `DB_RESTORE.md` and the two skills; v116 spec Honest limits — the "Losing the VM" bullet now reads that losing the VM loses what changed since the last good `/backup-pull` and all point-in-time history; `DB_RESTORE.md` — add the stable snapshot result (name, tag, manifest summary, dry-run output excerpt).
- [ ] **Step 4:** Amend the ten stale spec statements listed in "Status as built" in the same close-out. **Commit** `docs(v120): first stable snapshot, dry-run restore, spec amended`

### Task V120-10: Full-suite verification

- [ ] **Step 1:** Dispatch `test-runner` for `python scripts/dev/testrun.py full` on the rebased branch. Green means `0 failed` and `0 xfailed`. Run it while no other session's suite is running against the shared test database, or give it a private base database through `TEST_DATABASE_URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:55432/<private name>` (create that database first; the conftest appends `_gwN`). If the only failure is `tests/admin/test_api_v1_watchlist.py` (a 1.0 s timing assertion that failed on `main` under load with `can't start new thread`), report it with the measured number and do not loosen it.
- [ ] **Step 2:** `python -m radon cc -s -n C scripts/ops/backup_manifest.py` → no output.
- [ ] **Step 3:** Update **Progress:** to "implemented"; close out per `document-lifecycle.md` (`/close-out`).
