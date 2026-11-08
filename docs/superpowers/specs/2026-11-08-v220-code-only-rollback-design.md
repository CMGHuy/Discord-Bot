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
   list since the previous point, and GHCR image tags that survive registry
   pruning.

The two whole-bot restore paths stay as they are, for disasters.

## Partner decisions (brainstorm 2026-11-08)

| Question | Decision |
|---|---|
| Existing `/stable-snapshot` | Keep it; add rollback data to its manifest |
| `.env` on rollback | Keep current `.env`; refuse if the target's config schema needs a key that is missing |
| Newer migrations | Forward-only schema, never downgrade; refuse if any migration between target and now is non-additive |
| Target naming | Any form (stable tag, sha, `vNNN`, bot version, date) plus a picker when no argument is given |
| Keeping it rolled back | Deploy hold on the VM; `--release` clears it |
| Scanning after rollback | Keeps running (data is intact; open trades need lifecycle monitoring) |

## Findings that shape the design

- **Both existing restores wipe trades.** `restore_stable.sh` loads the dump of
  the point; `rollback_to.sh` runs pgBackRest PITR. Neither has a data-preserving
  mode, and adding one behind a flag would put a DB-wiping and a DB-preserving
  path one mistyped flag apart. Hence a separate script.
- **`deploy/deploy.sh` runs `alembic upgrade head`** (lines ~187 and ~230). An
  older image lacks the newer revision files, so against today's database that
  command fails with "Can't locate revision". A code rollback must never run it.
- **Every push to `main` deploys** (`.github/workflows/deploy.yml`). Without a
  hold, the next commit from any session silently undoes a rollback.
- **CI pushes `sha-<12>` images for every main push** (`deploy.yml:276`), so
  nearly any recent main commit already has an image; deploys.jsonl records only
  the deployed ones.
- **`registry-retention.yml` deletes images older than 45 days**, exempting only
  `latest`. The images behind `stable-2026-09-17`, `-10-02` and `-10-06` are
  likely already gone, so those points can no longer restore their code.

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
stable points with their plan ids and bot versions; "Other" accepts any form
above.

### Safety checks (`rollback_plan.py check`), all before anything changes

1. **Migrations are additive.** Walk Alembic's revision graph from the target
   commit's head (read from the target's tree with `git show`, not filenames)
   to the current head. Classify every `op.*` call in each `upgrade()`:
   - safe: `create_table`, `create_index`, `add_column` with `nullable=True`
     or a `server_default`, and `op.execute` whose SQL statements are only
     `CREATE`, `INSERT` or `COMMENT`;
   - unsafe: any `drop_*`, `alter_column`, rename, `rename_doc_field`,
     `drop_doc_field`, and any SQL it cannot classify.
   A migration may declare a module constant `ROLLBACK_SAFE = "<reason>"`,
   which overrides an unsafe verdict and is printed in the report. Any
   remaining unsafe call refuses, naming revision and call.
2. **Config keys exist.** Load the target's `swingbot/config.py` from
   `git show <sha>:swingbot/config.py` into an isolated module and check that
   every required field without a default is present in the current `.env`
   (key names only, values never read into output). Missing key: refuse.
   Extra keys: listed as info.
3. **Unknown-field floor.** The target must be at or after the commit that
   introduced the repositories' unknown-field round-trip guarantee (v116
   Phase 2), stored as the constant `UNKNOWN_FIELD_FLOOR_SHA` in
   `rollback_plan.py`; older code could strip JSONB fields written by newer
   code when it re-saves a row. Older target: refuse.
4. **Image exists.** `docker manifest inspect` on the resolved image.
5. **Not already there / no conflicting hold.** Target equals the running sha:
   no-op. An existing hold is shown, and a new rollback replaces it.

### Execution (`rollback_code.sh <sha> <image> --dry-run | --i-mean-it`, on the VM as root)

Mirrors `rollback_to.sh` structure (everything in `main()`, one call line, so
the git checkout cannot rewrite the running script):

1. Re-run the image check; write the plan to `logs/rollback.log`.
2. Safety net: `pgbackrest --type=diff backup` (no restore, ever).
3. `runuser -u deploy -- git -C /opt/swing-bot checkout --detach <sha>`.
4. `env_set.py SWING_BOT_IMAGE <image>`; `docker pull`; `docker compose up -d
   bot admin refresher` — **no** `alembic upgrade`. `SWING_BOT_DB_IMAGE` is
   left as is (the database server never goes back).
5. Write `backups/deploy_hold.json` `{sha, image, from_sha, from_image, reason,
   at}` and append a `kind: "rollback"` line to `backups/deploys.jsonl`.
6. Smoke check, 3 minutes max: containers healthy, `bot_heartbeat` fresh,
   admin `/api/health` 200, and a read of open plans and the latest journal
   rows through the old code (`docker compose exec -T bot python -m
   swingbot.core.infra.rollback_smoke`, a module added now so future images
   carry it; images without it fall back to the heartbeat and health checks).
   Failure: automatically restore `from_sha`/`from_image` the same way, keep
   no hold, exit non-zero.

### Release (`/rollback --release`)

Deletes the hold, then runs the normal `deploy/deploy.sh` for `origin/main`
HEAD, which includes `alembic upgrade head`. `/rollback <newer target>` is
also allowed and replaces the hold.

### Deploy hold

- `deploy/deploy.sh` checks `backups/deploy_hold.json` first; when present it
  logs `deploy held by rollback to <sha> (<reason>, since <at>)`, posts one ops
  notice through the existing deploy notification path, and exits 0 so CI
  stays green.
- The SessionStart hook prints a `HOLD` line (read-only check through
  `ssh-hetzner.sh`, cached, never blocking session start on a network error).
- The `/deploy` skill refuses while a hold is set and points at
  `/rollback --release`.

### What is never touched

All Postgres contents (trades, plans, journal, account and balance history,
signal state, watchlist, runtime flags, killswitch, admin data), `.env`,
`market_data/`, Discord messages already posted, logs.

## Section 2 — `/stable-snapshot` extension

- Manifest (`backup_manifest.py`) gains `alembic_head`, `bot_version`,
  `ui_version`, and `features`: the plan ids `(vNNN)` and commit subjects on
  `main` since the previous stable point. `verify` accepts manifests without
  these fields (older points) and reports them as "pre-v220".
- `stable_snapshot.sh` additionally tags the bot and db images as
  `stable-YYYY-MM-DD[-N]` on GHCR; `registry-retention.yml` excludes
  `stable-*` tags from pruning.
- The skill's report adds the feature list and the matching `/rollback
  stable-…` command next to the existing restore command.

## Repo bookkeeping

- New skill `.claude/skills/rollback/SKILL.md` (`disable-model-invocation:
  true`, invoked explicitly), Codex mirror via `scripts/dev/sync_codex.py`, one
  condensed `AGENTS.md` line.
- `docs/deploy/DB_RESTORE.md` gains "Code-only rollback (v220)", contrasting
  it with the two whole-bot restores in a table.
- `schema-change` skill and `docs/claude/schema-evolution.md`: a new migration
  states whether it is rollback-safe; a non-additive one should set
  `ROLLBACK_SAFE` only with a real reason.
- Every new function stays under complexity 15.

## Testing

- `rollback_plan.py resolve`: each target form, ambiguous and unknown input,
  sha not on main, `vNNN` with no commits.
- Migration scanner: one fixture migration per safe and unsafe rule, the
  `ROLLBACK_SAFE` override, multi-statement SQL, and a real-repo test that
  every existing revision classifies without error.
- Config check: missing required key, extra key, target config that fails to
  import (refuse).
- Unknown-field floor: target before and after the floor.
- `backup_manifest.py`: new fields written, old manifests still verify.
- `deploy.sh` hold: a pytest wrapper running the hold-check function against a
  temp directory (hold present → skip and exit 0; absent → continue).
- `rollback_smoke` module: unit-tested against the test database.
- New test files join an existing suite in `tests/suites.toml` (ops scripts),
  splitting by feature if it passes `max_tests`.
- **Drill:** one rollback, smoke failure simulation and release on a scratch
  stack, recorded in `DB_RESTORE.md`. No production rollback during
  implementation.

## Out of scope

- Reverting a single feature while keeping later ones (that is a `git revert`
  on `main`, a normal change).
- Downgrading the schema or restoring any data.
- Rolling back `.env` or `market_data/` (the whole-bot paths do that).
- Rebuilding images that GHCR has already pruned.
