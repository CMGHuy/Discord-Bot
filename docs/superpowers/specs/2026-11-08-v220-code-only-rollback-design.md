# v220 — Code-only rollback (keep every trade) and richer stable snapshots

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer

## Goal

Production can already be rolled back, but only as a whole: `restore_stable.sh`
(v120) and `rollback_to.sh` (v116) both restore Postgres, so every trade, plan,
journal row and balance point issued since the target is wiped. The partner
wants the opposite trade-off: put the **technical parts** (code and the bot
image) back to an earlier commit or feature while **keeping all trading data**
issued in the meantime, and be able to name the target as a commit, a feature
(plan id), a version, a date or a stable point.

What changes:

1. A new skill **`/rollback [target] [--release]`**, backed by a new VM script
   `scripts/ops/rollback_code.sh` and a pure-Python planner
   `scripts/ops/rollback_plan.py`. It switches the running image and code
   checkout to the target commit, never touches the database contents,
   `.env` or `market_data/`, and holds further deploys until released.
2. **`/stable-snapshot` is extended** (not replaced) so every stable point
   carries what a code-only rollback needs: Alembic head, versions, the feature
   list since the previous point, a config-key hash, and GHCR image tags that
   survive registry pruning.

The two whole-bot restore paths stay as they are, for disasters.

## Partner decisions (brainstorm 2026-11-08)

| Question | Decision |
|---|---|
| Existing `/stable-snapshot` | Keep it; add rollback data to its manifest |
| `.env` on rollback | Keep current `.env`; refuse if the target's config schema needs a key that is missing |
| Newer migrations | Forward-only schema, never downgrade; refuse if any migration between target and now is not provably additive |
| Target naming | Any form (stable tag, sha, `vNNN`, bot version, date) plus a picker when no argument is given |
| Keeping it rolled back | Deploy hold; `--release` clears it |
| Scanning after rollback | Keeps running (data is intact; open trades need lifecycle monitoring) |

## Findings that shape the design

- **Both existing restores wipe trades.** `restore_stable.sh` loads the dump of
  the point; `rollback_to.sh` runs pgBackRest PITR. Adding a data-preserving
  mode behind a flag would put a DB-wiping and a DB-preserving path one
  mistyped flag apart. Hence a separate script.
- **`deploy/deploy.sh` runs `alembic upgrade head`** (lines ~187 and ~230). An
  older image lacks the newer revision files, so against today's database that
  command fails with "Can't locate revision" and leaves bot, admin and
  refresher stopped. A code rollback must never run it.
- **Every push to `main` deploys**, and CI runs `deploy.sh` **from the VM's
  checked-out tree** (`deploy.yml:~708`), which after a rollback is the
  *target's* `deploy.sh`, and `deploy.sh:44-49` does `git reset --hard
  origin/main` before anything else. A hold check inside `deploy.sh` alone is
  therefore useless; it must live in the workflow (which always runs from the
  pushed commit) and, as a second line, before that reset.
- **CI pushes `sha-<12>` images for every main push** (`deploy.yml:276`), so
  nearly any recent main commit already has an image.
- **`registry-retention.yml` deletes images older than 45 days**, exempting only
  `latest`. The images behind `stable-2026-09-17`, `-10-02` and `-10-06` are
  likely already gone.
- **Known semantic breaks exist below the schema level.** `deploy.sh:181-185`
  documents that rolling back past v197 is unsupported (the old DELETE-drain
  consumer against the new lifecycle queue); `rollback_to.sh:100-102` carries a
  v184 heartbeat-key fix. "Additive schema" is necessary, not sufficient.

## Section 1 — `/rollback`

### Target resolution (`rollback_plan.py resolve`)

Accepted forms, each resolving to exactly one commit on `main` plus its
`ghcr.io/...:sha-<12>` image:

| Form | Resolves to |
|---|---|
| `stable-YYYY-MM-DD[-N]` | the tag's commit (manifest `git_sha` when the snapshot folder exists) |
| hex sha (≥7 chars) | that commit; must be an ancestor of `origin/main` |
| `vNNN` / `vNNN-before` | the parent of the first `main` commit whose subject carries `(vNNN)` — the state just before that plan landed |
| `vNNN-after` | the last `main` commit whose subject carries `(vNNN)` |
| `bot-A.B.C` | the commit that set `VERSION.json` `bot` to `A.B.C` |
| `YYYY-MM-DD[THH:MM]` (UTC) | the deploy live at that moment, from `backups/deploys.jsonl` |

Ambiguous or unknown input is refused with the candidates listed. With no
argument, the skill shows a picker (`AskUserQuestion`) of the last deploys and
stable points with their plan ids and bot versions, restricted to targets at
or above the compatibility floor; "Other" accepts any form above.

### Safety checks (`rollback_plan.py check`), all before anything changes

1. **Compatibility floor.** `rollback_plan.py` keeps a maintained list
   `INCOMPATIBLE_BOUNDARIES`, each entry `(sha, plan, reason)`; the floor is
   the newest entry, and a target passes only when every boundary sha is an
   ancestor of it (`git merge-base --is-ancestor`; these commits landed via
   merges, so `--first-parent` order is not used). Initial entries:
   `66e67c00` (v116 Phase 2 unknown-field round-trip, merged in `14551c3c`;
   older code can strip JSONB fields on re-save), `2d672bab` (v184 `monitor`
   heartbeat key, merged in `b37c6e44`), and `8562c35a` (v197 lifecycle queue;
   migration `a47f9ebc`). A target below the floor is refused, naming the
   boundary. Any future plan that makes old
   code unsafe against new data adds an entry (rule added to
   `schema-evolution.md` and the `schema-change` skill).
2. **Migrations are provably additive.** Walk Alembic's revision graph from
   the target's head (read from the target tree with `git show`) to the
   current head. Parse each `upgrade()` with `ast`:
   - safe: `op.create_table`, `op.create_index`, `op.add_column` with
     `nullable=True` or a `server_default`, and `op.execute` with a literal
     SQL string whose every statement is `CREATE TABLE`, `CREATE INDEX`,
     `INSERT` or `COMMENT`;
   - unsafe: any `drop_*`, `alter_column`, rename, `rename_doc_field`,
     `drop_doc_field`; `CREATE OR REPLACE` of a function, trigger or view;
     **any** `op.get_bind()`, `conn.execute`, non-literal SQL, or call to a
     helper (data rewrites hide there — `v200_001`, `v197_001`).
   A migration may declare a module constant `ROLLBACK_SAFE = "<reason>"`,
   which overrides an unsafe verdict and is printed in the report. A one-time
   audit task marks the existing migrations above the floor where the reason
   is real. Remaining unsafe: refuse, naming revision and call.
3. **Config keys exist.** `swingbot/config.py` has no "required" notion
   (every `Field` defaults to `""` or omits `default=` for optional values),
   so: read the target's `config.py` (via `git show`) with `ast` — never
   import it — and collect every declared field name. A name in the constant
   `CRITICAL_KEYS` (initially `DISCORD_TOKEN`, `POSTGRES_PASSWORD`,
   `DATABASE_URL`) missing from the current `.env`: refuse. Any other target
   field absent from `.env` and no longer declared at HEAD (a key the old code
   used that was since removed): warn in the dry-run report. Names only;
   values are never read into output.
4. **Open-trade vocabulary is known to the target.** A read-only query over
   open plans and journal rows collects the distinct values of the stored
   vocabularies — `PlanStatus` values, strategy names (`ALL_STRATEGIES`,
   `backtest.py`), lifecycle event kinds (`lifecycle_events.py`), and the plan
   fields `source`, `entry_type` and `ledger`; each value must occur as a
   literal in the target tree (`git grep` on the target sha). (`exit_model` is
   a backtest parameter, never stored, so it is not checked.) Unknown value: refuse (old lifecycle code would mis-manage the
   trade).
5. **Compose `db` service unchanged.** The `db` service block of
   `docker-compose.yml` at the target must equal HEAD's; otherwise refuse
   (Compose would recreate Postgres under the old definition).
6. **Market-data writer unchanged.** If any path in the constant
   `MARKET_DATA_WRITER_PATHS` (the refresher package plus the module that
   writes `market_data/daily`, named in the plan from the code brief) differs
   between target and HEAD, the dry-run report warns and the refresher stays stopped
   during the hold unless the partner confirms otherwise (the live cache never
   self-heals — `known-traps.md`).
7. **Image exists** (`docker manifest inspect`) and **VM tree is clean**
   (`git status --porcelain` as `deploy` prints nothing — an unmirrored live
   edit refuses).
8. **Not already there.** Target equals the running sha: no-op. An existing
   hold is shown, and a new rollback replaces it.

### Execution (`rollback_code.sh <sha> <image> --dry-run | --i-mean-it`, on the VM as root)

The script is not present in older trees, so its first act is to copy itself
to the run's temp directory and re-exec from there; everything lives in
`main()` with one call line (the `restore_stable.sh` pattern, which has
`main()` but no self-copy). Then:

1. Re-run the image and clean-tree checks; log the plan to `logs/rollback.log`.
2. Safety net: `pgbackrest --type=diff backup` (no restore, ever).
3. Write `backups/deploy_hold.json` `{sha, image, from_sha, from_image,
   db_image, reason, at}` **before** touching code, so no deploy can race in.
4. `runuser -u deploy -- git -C /opt/swing-bot checkout --detach <sha>`.
5. `env_set.py SWING_BOT_IMAGE <image>`; `docker pull`; probe `import
   swingbot.refresher` in the image (the v201 guard used by `deploy.sh:215-220`
   and `rollback_to.sh`); `docker compose up -d --no-deps bot admin` plus
   `refresher` only when the probe passes and check 6 allows it. **No**
   `alembic upgrade`. `SWING_BOT_DB_IMAGE` is left as is.
6. Smoke check, 3 minutes max: containers healthy, `bot_heartbeat` fresh,
   admin `/api/health` 200, and `python -m swingbot.core.infra.rollback_smoke`
   when the image carries it (v220 onward): reads open plans and journal rows
   and runs one lifecycle evaluation over them **with writes disabled**,
   failing on any exception or unknown value. Images without the module rely
   on check 4 plus heartbeat and health.
7. Pass: append a `kind: "rollback"` line to `backups/deploys.jsonl` carrying
   every field `pitr_resolve.py` indexes (`ts`, `git_sha`, `bot_image`,
   `db_image`) plus `from_sha`. Fail: restore `from_sha`/`from_image` the same
   way, delete the hold, write nothing to `deploys.jsonl`, exit non-zero.

### Release (`/rollback --release`)

1. Delete the hold.
2. `runuser -u deploy -- git -C /opt/swing-bot checkout main` (back from
   detached).
3. Run `deploy/deploy.sh` with `SWING_BOT_IMAGE=…:sha-<origin/main 12>` and
   the current db image exported, so the new code runs the new image and
   `alembic upgrade head` finds its revisions.
4. Append a `kind: "release"` line to `deploys.jsonl` (same fields), closing
   the rollback window.
5. Report rows updated during the window (by `updated_at` between the
   rollback and release lines) with a top-level key count compared to their
   last pre-window state where history exists, so any field an old writer
   dropped is visible.

`/rollback <newer target>` is also allowed and replaces the hold.

### Deploy hold

- **Primary:** a new first job `hold` in `.github/workflows/deploy.yml`
  reads `backups/deploy_hold.json` over SSH and outputs `held`. When held it
  logs `deploy held by rollback to <sha> (<reason>, since <at>)` and runs
  `scripts/ops/hold_notice.sh` on the VM, which posts one ops notice to
  `OPS_ALERT_WEBHOOK_URL` (the existing VM-side alert path,
  `heartbeat_watch.sh`; the workflow has no notification step of its own).
  `cleanup` (whose image prune would delete `from_image` locally) and `deploy`
  both depend on `hold` and run only when `held != 'true'`; `deploy`'s
  condition must also tolerate `cleanup` being skipped. The run stays green.
  Existing tests pinning `deploy.needs`/`steps[0]`
  (`tests/dev/test_ci_db_image.py`) are updated.
- **Secondary:** `deploy.sh` checks the hold in phase 1, before `git reset
  --hard origin/main`, and exits 0 when it is present (covers manual runs of a
  post-v220 `deploy.sh`).
- The SessionStart hook prints a `HOLD` line (read-only check through
  `ssh-hetzner.sh`, cached, never blocking session start on a network error).
- The `/deploy` skill refuses while a hold is set and points at
  `/rollback --release`.
- While held, no backtest or research job runs from the VM checkout (the
  v162 history-store cron and its scripts may not exist in the target tree);
  the cron is checked after rollback and after release.

### What is never touched

All Postgres contents (trades, plans, journal, account and balance history,
signal state, watchlist, runtime flags, killswitch, admin data), the `db`
container, `.env`, `market_data/`, Discord messages already posted, logs.

### Rollback windows in analytics

Rows created during a hold were made by older code. The window is recorded
by the `rollback`/`release` lines in `deploys.jsonl`; excluding or tagging
those rows in analytics is out of scope for v220 (see Out of scope).

## Section 2 — `/stable-snapshot` extension

- Manifest (`backup_manifest.py`) gains `alembic_head`, `bot_version`,
  `ui_version`, `config_keys_sha256` (hash of the sorted required config
  field names), and `features`: the plan ids `(vNNN)` and commit subjects on
  `main` since the previous stable point. `verify` accepts manifests without
  these fields (older points) and reports them as "pre-v220".
- The VM's GHCR login is a read-only PAT, so the images are tagged
  `stable-YYYY-MM-DD[-N]` by a new `workflow_dispatch` workflow
  `pin-stable-image.yml` (`packages: write` via `GITHUB_TOKEN`, inputs: name,
  bot image, db image), which the skill triggers with `gh workflow run` after
  the VM snapshot and waits for; `registry-retention.yml` excludes
  `stable-*` tags. The plan verifies that the retention action keeps a
  version carrying both a `sha-` and a `stable-` tag.
- The skill's report adds the feature list and the matching `/rollback
  stable-…` command next to the existing restore command, and says whether
  the point is above the compatibility floor.

## Repo bookkeeping

- New skill `.claude/skills/rollback/SKILL.md` (`disable-model-invocation:
  true`, invoked explicitly), Codex mirror via `scripts/dev/sync_codex.py`, one
  condensed `AGENTS.md` line.
- `docs/deploy/DB_RESTORE.md` gains "Code-only rollback (v220)", contrasting
  it with the two whole-bot restores in a table.
- `schema-change` skill and `docs/claude/schema-evolution.md`: a new migration
  states whether it is rollback-safe (`ROLLBACK_SAFE` only with a real
  reason), and a change that makes old code unsafe against new data adds an
  `INCOMPATIBLE_BOUNDARIES` entry.
- Every new function stays under complexity 15.

## Testing

- `rollback_plan.py resolve`: each target form, ambiguous and unknown input,
  sha not on main, `vNNN` with no commits, target below the floor.
- Migration scanner: one fixture per safe and unsafe rule, `get_bind`/helper
  calls, `CREATE OR REPLACE FUNCTION`, multi-statement SQL, the
  `ROLLBACK_SAFE` override, and a real-repo test that every existing revision
  classifies without error.
- Config check (AST): missing required key, extra key, unparsable target file
  (refuse).
- Vocabulary check: a value absent from the target tree refuses; all present
  passes.
- Compose `db` diff and writer diff checks.
- `backup_manifest.py`: new fields written, old manifests still verify.
- Hold: the workflow step's script and `deploy.sh`'s phase-1 check, each run
  by a pytest wrapper against a temp directory (hold present → skip, exit 0;
  absent → continue).
- `deploys.jsonl` rollback/release lines parse through `pitr_resolve.py`.
- `rollback_smoke`: unit-tested against the test database, asserting it
  writes nothing.
- New test files join an existing suite in `tests/suites.toml` (ops
  scripts), splitting by feature if it passes `max_tests`.
- **Drill:** one rollback, a forced smoke failure (auto-restore), and a
  release on a scratch stack, recorded in `DB_RESTORE.md`. No production
  rollback during implementation.

## Out of scope

- Reverting a single feature while keeping later ones (that is a `git revert`
  on `main`, a normal change).
- Downgrading the schema or restoring any data.
- Rolling back `.env` or `market_data/` (the whole-bot paths do that).
- Rebuilding images that GHCR has already pruned.
- Excluding or tagging rollback-window rows in analytics (a follow-on if a
  rollback is ever used in anger).

## Panel review

- staff-engineer: hold inside `deploy.sh` cannot stop CI (target's `deploy.sh` runs, reset precedes any check) -- applied: primary check in `deploy.yml`, secondary before the reset.
- staff-engineer: release must export the new image or `alembic upgrade` fails with services stopped -- applied: Release step 3.
- staff-engineer: no v201 refresher import guard -- applied: Execution step 5.
- staff-engineer: scanner passes `get_bind`/`conn.execute`/helper data rewrites and `CREATE OR REPLACE FUNCTION` -- applied: those are unsafe; AST parse; one-time `ROLLBACK_SAFE` audit.
- staff-engineer: v116 floor misses v197 queue and v184 heartbeat breaks -- applied: maintained `INCOMPATIBLE_BOUNDARIES` list.
- staff-engineer: `compose up` may recreate `db` from the target's compose file -- applied: `--no-deps` and check 5.
- staff-engineer (advisory): rollback line must carry `pitr_resolve` fields and be written only after smoke -- applied: Execution step 7.
- staff-engineer (advisory): no `main()`/checkout precedent; script deletes itself on checkout -- applied: self-copy and re-exec (`restore_stable.sh` does have `main()`, per the code brief).
- staff-engineer (advisory): dirty tree and detached HEAD after release -- applied: check 7 and Release step 2.
- staff-engineer (advisory): confirm retention exclusion with dual tags; held image may age out -- applied: verification in Section 2; ageing-out accepted (a hold is meant to be short; the re-pull failure is reported).
- staff-engineer (advisory): `cleanup` prune removes `from_image` during a hold -- applied: the hold step skips cleanup.
- staff-engineer (advisory): importing the target's `config.py` runs old code as root -- applied: AST read.
- quant-engineer: no check that old lifecycle code can manage open trades written by newer exit logic -- applied: check 4 (vocabulary) for every target, plus a write-free lifecycle evaluation in `rollback_smoke` for v220+ images.
- quant-engineer: smoke reads but never evaluates, and must not write -- applied: Execution step 6.
- quant-engineer (advisory): rollback-window rows carry old semantics -- applied as record only (`rollback`/`release` lines); analytics tagging out of scope.
- quant-engineer (advisory): old refresher may write `market_data/` in an old format -- applied: check 6.
- quant-engineer (advisory): v162 history store and cron during a hold -- applied: no research jobs while held; cron checked after rollback and release.
- quant-engineer (advisory): rows re-saved during the hold read by new code after release -- applied: Release step 5 report.
- quant-engineer (advisory): manifest should record config/registry state -- applied in part: `config_keys_sha256`; registry version rejected: the target sha already pins the registry code exactly.

## Code-brief corrections (2026-11-08)

The plan brief found gaps, fixed above: config has no required fields (now
`CRITICAL_KEYS` plus a removed-key warning); `exit_model` is not stored
(vocabulary list corrected); the workflow has no notification step (VM-side
`OPS_ALERT_WEBHOOK_URL`); `deploy` needs `cleanup` (new `hold` job and
conditions); the VM cannot push GHCR tags (`pin-stable-image.yml`); boundary
shas named and tested by ancestry.
