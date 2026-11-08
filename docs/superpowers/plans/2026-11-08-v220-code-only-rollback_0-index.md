# v220 — Code-only rollback (keep every trade) (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md) (panel review and code-brief corrections applied, 0334ba82; the "Code-brief corrections" section supersedes earlier wording)

## Goal

Production can be rolled back today, but only as a whole. `restore_stable.sh`
(v120) loads a stable point's dump and `rollback_to.sh` (v116) runs a
pgBackRest point-in-time restore; both put Postgres back, so every trade,
plan, journal row and balance point issued since the target is wiped. The
partner wants the other trade-off as well: put the **code and the bot image**
back to an earlier commit or feature while **keeping every row of trading
data** issued in the meantime, and name the target as a stable point, a
commit, a plan id, a bot version or a date.

Once this plan ships there is a third, separate path. `/rollback [target]
[--release]` resolves the target to one `main` commit and its `sha-<12>`
image, runs eight safety checks, and only then switches the VM's checkout and
running image. It never touches the database contents, the `db` container,
`.env` or `market_data/`. While rolled back, a **deploy hold** stops every
CI deploy (the workflow's new first job reads the hold file and skips
`cleanup` and `deploy`, the run stays green). `deploy.sh` checks the same file
before its `git reset`, the SessionStart hook prints a `HOLD` line and the
`/deploy` skill refuses. `--release` clears the hold and redeploys `main`.
The spec's Section 2 (`/stable-snapshot` records an Alembic head, versions, a
config-key hash and the features since the previous point, and pins its
images with `stable-…` tags) ships separately as
[v221](2026-11-08-v221-stable-snapshot-rollback-fields.md), moved out to keep
this plan inside the 20-task cap; `/rollback stable-…` works without it.

How it works in idea: a stdlib-only planner (`scripts/ops/rollback_plan.py`
plus three sibling modules) reads the target's tree with `git show`, never
imports or runs it, and refuses unless (1) the target is at or above every
`INCOMPATIBLE_BOUNDARIES` commit, (2) every Alembic revision between the
target's head and today's head parses as additive (or carries a reasoned
`ROLLBACK_SAFE`), (3) the target's critical config keys are in `.env`, (4)
every stored vocabulary value of open trades occurs in the target tree,
(5) the compose `db` block is unchanged, plus a market-data-writer warning,
the image and clean-tree checks, and the no-op check. The VM script
`scripts/ops/rollback_code.sh` copies itself and the planner out of the tree
before the checkout, takes a pgBackRest diff backup as a safety net, writes
the hold, switches code and image without `alembic upgrade`, smoke-checks for
three minutes (including a write-free lifecycle evaluation from the new
`swingbot.core.infra.rollback_smoke` in v220+ images), and restores the
previous code and image by itself on failure.

What it leaves alone: `restore_stable.sh`, `rollback_to.sh`, `pitr_resolve.py`
and `env_set.py` stay exactly as they are, for disasters. No schema change,
no stored field, no exit or entry logic, no analytics tagging of rows written
during a rollback window (the `rollback`/`release` lines in
`backups/deploys.jsonl` only record the window).

Success is measured by the tests (each target form, every scanner rule, each
check's refuse and pass case, the hold in the workflow and in `deploy.sh`,
`rollback_smoke` writing nothing) and by one drill on a scratch stack: a rollback, a forced
smoke failure that restores itself, and a release, recorded in
`docs/deploy/DB_RESTORE.md`. No production rollback happens during
implementation. It is integrity work, so no ExpR or win-rate claim follows.

## Architecture

- **Planner (Parts 1–2), `scripts/ops/`, stdlib only.** The VM host runs it
  with its own `python3` (like `backup_manifest.py` and `env_set.py`), so it
  imports nothing from `swingbot` and nothing outside the standard library.
  - `rollback_plan.py`: target resolution, `INCOMPATIBLE_BOUNDARIES` and the
    floor, the picker's candidate list, the assembled `check` report and the
    `deploys.jsonl` line. CLI subcommands `resolve`, `candidates`, `floor`,
    `check`, `deploy-line`.
  - `rollback_migrations.py`: the AST migration scanner and an Alembic
    revision graph built from any commit's tree (`git ls-tree` + `git show`),
    never from Alembic's `ScriptDirectory` (which reads the working tree).
  - `rollback_checks.py`: config keys (AST over the target's `config.py`),
    compose `db` block, market-data writer paths, stored-vocabulary check, and
    the one `psql` runner (`docker compose exec -T db psql …`).
  - `rollback_window.py`: the doc-key snapshot taken at rollback and the
    release-time report of rows updated during the window. Own CLI.
- **Smoke (Part 2).** `swingbot/core/infra/rollback_smoke.py`, run as
  `python -m swingbot.core.infra.rollback_smoke` inside the image: reads open
  plans and open journal rows, runs one `PlanManager._step` per open plan
  through a read-only store on a read-only database session, fails on any
  exception or unknown vocabulary value.
- **VM script (Part 3).** `scripts/ops/rollback_code.sh`, run as root from a
  copy taken out of `origin/main` by the skill: `--resolve`, `--candidates`,
  `<sha> <image> --dry-run|--i-mean-it`, `--release --dry-run|--i-mean-it`.
  Self-copy and re-exec, everything in `main()`, one call line.
- **Hold (Part 3).** `backups/deploy_hold.json` on the VM. Primary check: new
  first job `hold` in `.github/workflows/deploy.yml`, with
  `scripts/ops/hold_notice.sh` posting one ops notice to
  `OPS_ALERT_WEBHOOK_URL`. Secondary: `deploy/deploy.sh` phase 1, before the
  `git fetch`/`git reset`. Visibility: `scripts/dev/hold_status.py` behind a
  `HOLD` line in `.claude/hooks/session-cursor.ps1`; refusal in the `/deploy`
  skill.
- **Stable snapshots: moved to v221** (manifest fields, `pin-stable-image.yml`,
  retention exclusion, `/stable-snapshot` report). v220 reads a stable point
  only through its manifest `git_sha` (`<repo>/backups/stable/<name>/manifest.json`,
  which every existing point has) or its git tag.
- **Bookkeeping (Part 4).** `.claude/skills/rollback/SKILL.md`, Codex mirror,
  `AGENTS.md`, the release bump and the scratch-stack drill (recorded in
  `DB_RESTORE.md`). The `DB_RESTORE.md` comparison table, `schema-evolution.md`
  and the `schema-change` skill moved to v221 (V221-4).

## Global Constraints

- **Never touched by any v220 code path:** Postgres contents (trades, plans, journal, account and balance history, signal state, watchlist, runtime flags, killswitch, admin data), the `db` container, `.env` contents, `market_data/`, posted Discord messages, logs. No `alembic upgrade` on the rollback path; `SWING_BOT_DB_IMAGE` is never changed by a rollback.
- **Untouched files:** `scripts/ops/rollback_to.sh`, `scripts/ops/restore_stable.sh`, `scripts/ops/pitr_resolve.py`, `scripts/ops/env_set.py`.
- **`scripts/ops/rollback_*.py` are standard-library only** and never import `swingbot` (the VM host's `python3` runs them, from a copy outside the checkout).
- **The target tree is read, never run:** `git show <sha>:<path>` plus `ast.parse`; never `import` or `exec` a target file.
- **`.env` values are never read into output:** key names only (`env_key_names`); CLAUDE.md forbids printing, echoing or logging any value.
- **Every git command on the VM runs as `runuser -u deploy -- git …`**; the clean-tree test is `git status --porcelain --untracked-files=no` (untracked `data/`, `logs/`, `backups/` exist).
- **Image names derive from the current `SWING_BOT_IMAGE`** (strip the tag, add `:sha-<first 12 hex>`); the repository path is never hard-coded.
- **`INCOMPATIBLE_BOUNDARIES` initial entries, verbatim:** `("66e67c00", "v116", "unknown-field round-trip; older code can strip JSONB fields on re-save (merged in 14551c3c)")`, `("2d672bab", "v184", "monitor heartbeat key (merged in b37c6e44)")`, `("8562c35a", "v197", "durable lifecycle queue replaces the DELETE-drain consumer (migration a47f9ebc)")`. Ancestry by `git merge-base --is-ancestor <boundary> <target>`, never `--first-parent`.
- **`CRITICAL_KEYS = ("DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL")`.**
- **Hold file** `backups/deploy_hold.json`: `{"sha", "image", "from_sha", "from_image", "db_image", "reason", "at"}` (`at` = `date -u +%Y-%m-%dT%H:%M:%SZ`). Held message, verbatim: `deploy held by rollback to <sha> (<reason>, since <at>)`.
- **`deploys.jsonl` rollback/release lines** carry `ts`, `git_sha`, `bot_image`, `db_image` (every field `pitr_resolve.py` reads) plus `kind` (`"rollback"`/`"release"`) and `from_sha`; written only after the smoke check passes.
- **Exit codes, everywhere in v220:** `0` pass, `1` failed (after an automatic restore where one applies), `2` refused (nothing changed), `3` no-op (target already running).
- Every function < complexity 15 (`scripts/dev/complexity_gate.py`); table-drive the scanner rules and the target forms.
- New test files go into existing suites: `tests/scripts/` = `tooling`, `tests/dev/` = `dev-setup`, `tests/db/` = its existing suite; no new `tests/` directory.
- Shell scripts cannot run in CI as-is: text-pin their order with a `*_shape.py` test (the `tests/scripts/test_rollback_to_shape.py` pattern); the two hold checks are also run by a pytest wrapper on a temp copy with a stub `git` on `PATH`, skipped when `bash` is absent.
- Narrow runs only: `python scripts/dev/testrun.py file <test>`. No task runs the full suite (CI does). A task whose tests reach Postgres runs `/replicate-prod-db` first against the shared `swing-db` (port 56789).
- No production rollback, hold or retag during implementation; production is read only (`scripts/ops/ssh-hetzner.sh`). The drill (V220-18) uses a scratch compose project on the VM, after the merge.
- Skill or `docs/claude/` edits ship their Codex mirror in the same commit (`python scripts/dev/sync_codex.py`, then `--check`; condensed `AGENTS.md` line).

## CLI contract (shared by Parts 1–4)

```
python3 rollback_plan.py resolve <target> [--repo DIR] [--ref origin/main] [--deploys FILE] [--current-image IMG]
    -> stdout {"sha": <40 hex>, "image": <repo>:sha-<12>, "form": <form>, "label": <str>}; exit 0
    -> stderr "REFUSE: <why>" then one "  candidate: <label> <sha12>" per candidate; exit 2
python3 rollback_plan.py candidates [--repo] [--ref] [--deploys FILE] [--stable-dir DIR] [--limit 10]
    -> stdout JSON list of {"label","sha","kind":"deploy"|"stable","bot_version","plans":[...],"above_floor":bool}
python3 rollback_plan.py floor <sha> [--repo]
    -> "above floor" exit 0 | "below floor: <sha> <plan> <reason>" per boundary, exit 2
python3 rollback_plan.py check <sha> --image IMG [--repo] [--ref] [--env FILE] [--running-sha SHA] [--hold FILE] [--skip-host]
    -> stdout JSON report {"ok","noop","refusals":[str],"warnings":[str],"notes":[str],
                           "refresher":"start"|"keep-stopped","migrations":[{"revision","safe","reasons","override"}],
                           "hold":<dict|null>}
    -> exit 0 ok, 2 refused, 3 noop
python3 rollback_plan.py deploy-line --kind rollback|release --sha SHA --image IMG --db-image IMG --from-sha SHA
    -> one JSON line (sort_keys) on stdout
python3 rollback_window.py snapshot --out FILE          (doc top-level key names of plans and journal_entries)
python3 rollback_window.py report --snapshot FILE --since TS --until TS
    -> stdout JSON {"tables": {<table>: {"updated": n, "new": n, "fewer_keys": [{"id","before","after","dropped":[...]}]}}}

bash rollback_code.sh --resolve <target> | --candidates
bash rollback_code.sh <sha> <image> --dry-run|--i-mean-it [--reason TEXT] [--keep-refresher]
bash rollback_code.sh --release --dry-run|--i-mean-it
    env: ROLLBACK_APP_DIR (default /opt/swing-bot), ROLLBACK_TOOLS_REF (default origin/main),
         ROLLBACK_DRILL=1 (scratch project only: no pgBackRest, bot service and heartbeat skipped,
         release runs compose up + alembic instead of deploy.sh), ROLLBACK_FORCE_SMOKE_FAIL=1 (honoured only with ROLLBACK_DRILL=1)

python -m swingbot.core.infra.rollback_smoke    (inside the image)
    -> stdout one JSON line {"plans","journal","steps","errors":[str],"unknown":[str]}; exit 0 pass, 1 fail

bash scripts/ops/hold_notice.sh [APP_DIR]       -> prints the held message, posts it to OPS_ALERT_WEBHOOK_URL; always exit 0
python scripts/dev/hold_status.py --line | --refresh   (cache logs/deploy_hold_cache.json)
```

How the skill reaches the VM (the tree may be a pre-v220 target without these files):

```
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && runuser -u deploy -- git fetch -q origin main && runuser -u deploy -- git show origin/main:scripts/ops/rollback_code.sh > backups/rollback_code.sh && bash backups/rollback_code.sh <args>"
```

`rollback_code.sh` then copies itself to `$WORK` (`mktemp -d $APP_DIR/backups/rollback.XXXXXX`) and re-execs, and writes `rollback_plan.py`, `rollback_migrations.py`, `rollback_checks.py` and `rollback_window.py` into `$WORK` from `git show "$ROLLBACK_TOOLS_REF":scripts/ops/<file>`.

## Parallelisation

At most 2 implementers at once.

- **Lane P (planner, Parts 1 and 1b):** V220-1 → V220-1b → V220-2 → V220-2b are sequential (same files `rollback_plan.py`, `tests/scripts/test_rollback_plan_resolve.py`, `tests/scripts/test_rollback_plan_floor.py`; each consumes the previous one's helpers and fixtures). V220-3 → V220-3b are sequential (same files `rollback_migrations.py` and its test; V220-3b consumes `scan_upgrade`, `Verdict`) and share no file or contract with V220-1..2b, so they run alongside them. V220-4 (`rollback_checks.py`) shares nothing with V220-1..3b and can start at any time. V220-4 → V220-5 are sequential (same file `rollback_checks.py`; V220-5 consumes the module and its test helpers).
- **V220-6** (`check` and `deploy-line` in `rollback_plan.py`) waits for V220-2b (same file), V220-3b (`check_migrations`) and V220-5 (`missing_vocabulary`, `vocab_from_db`, the V220-4 checks).
- **V220-6b** (checks 4/6/7, `deploy_line`, the `check`/`deploy-line` CLIs) follows V220-6 (same two files).
- **V220-7** (`rollback_window.py`, own CLI) and **V220-8** (`rollback_smoke`, `tests/db/`) share no file or contract with Lane P; each can start at any time.
- **V220-9** (`rollback_code.sh` up to the dry run) waits for V220-6b (it calls the planner's CLIs). **V220-9b** (hold, switch, smoke, restore) follows V220-9 (same file and shape test) and also waits for V220-7 (`rollback_window.py snapshot`) and V220-8 (it runs the module). **V220-10** follows V220-9b (same file and shape test).
- **V220-11** (`deploy.yml`, `hold_notice.sh`, `tests/dev/test_ci_db_image.py`) and **V220-12** (`deploy.sh`, `hold_status.py`, `session-cursor.ps1`) touch disjoint files and depend only on the hold-file contract above; both can start at any time.
- **V220-15** (`/rollback` and `/deploy` skills) waits for V220-2b (it documents the picker), V220-10 and V220-12 (it documents their CLIs and the hold line). It may name `stable-…` targets but **must not require the v221 manifest fields**: a stable point resolves through its manifest `git_sha` or its git tag, which older points already have.
- **V220-17** (release) runs after V220-1..15 are merged into the worktree: the bump describes the whole change.
- **V220-18** (drill) runs last, after the branch is merged to `main` and CI has deployed it: `rollback_code.sh` reads its tools from `origin/main` on the VM. It edits only `DB_RESTORE.md` (creating the `## Code-only rollback (v220)` heading with its drill record) and creates the drill override file; the close-out follows it.
- **v221 does not block v220.** v221 runs after v220 is merged (it imports `declared_config_keys` and calls the `floor` CLI; its V221-4 docs task fills the `DB_RESTORE.md` heading V220-18 creates); the v220 drill never takes a stable snapshot and needs nothing from v221.

## Task ledger

| ID | Title | Part | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V220-1 | Target resolution: sha and stable-point forms, `resolve` CLI | 1 | sonnet — new stdlib module, behaviour fixed by the spec's form table | C `scripts/ops/rollback_plan.py`, C `tests/scripts/rollback_repo.py`, C `tests/scripts/test_rollback_plan_resolve.py` | `git_out(repo: Path, *args: str) -> str`; `git_ok(repo, *args) -> bool`; `@dataclass(frozen=True) Target(sha: str, image: str, form: str, label: str)`; `class Refused(Exception)` with `.candidates: list[str]`; `image_for(sha: str, current_image: str) -> str`; `resolve(target: str, repo: Path, *, deploys_path: Path, current_image: str, ref: str = "origin/main") -> Target`; `STABLE_RE`, `_manifest_sha(repo, name)` (reads `<repo>/backups/stable/<name>/manifest.json`, else the git tag), `_full`, `_Ctx`, `_on_main`, `_stable_candidates`, `_FORMS` (`(pattern, form, handler)` rows); CLI `resolve`; test helper `tests/scripts/rollback_repo.py`: `make_repo(tmp_path, commits: list[dict]) -> Path`, `git`, `sha_of`, `commit_off_main` |
| V220-1b | Target resolution: bot-version and date forms | 1 | sonnet — extends one module's form table, behaviour fixed by the spec | M `scripts/ops/rollback_plan.py`, M `tests/scripts/test_rollback_plan_resolve.py` | `parse_ts(text: str) -> datetime` (UTC-aware; a bare `YYYY-MM-DD` is the end of that UTC day, 23:59:59); `load_deploys(path: Path) -> list[dict]` (oldest first, rollback/release lines included); `_bot_version(repo: Path, sha: str) -> str \| None`; `_FORMS` rows `"bot"`, `"date"` |
| V220-2 | `vNNN` forms and the compatibility floor | 1 | sonnet — extends one module, behaviour fixed by the spec | M `scripts/ops/rollback_plan.py`, M `tests/scripts/test_rollback_plan_resolve.py`, C `tests/scripts/test_rollback_plan_floor.py` | `class Boundary(NamedTuple): sha, plan, reason`; `INCOMPATIBLE_BOUNDARIES: tuple[Boundary, ...]` (the three Global Constraints entries); `floor_violations(sha: str, repo: Path, boundaries=INCOMPATIBLE_BOUNDARIES) -> list[Boundary]` (a missing boundary sha is a violation); `resolve(..., boundaries: tuple[Boundary, ...] \| None = None)` refuses below the floor; `PLAN_RE`; `_FORMS` row `"plan"`; CLI `floor`; test fixture `chain` |
| V220-2b | Picker candidates | 1 | sonnet — one read-only listing function and its CLI in an existing module | M `scripts/ops/rollback_plan.py`, M `tests/scripts/test_rollback_plan_floor.py` | `candidates(repo: Path, *, deploys_path: Path, stable_dir: Path \| None, ref: str = "origin/main", limit: int = 10, boundaries: tuple[Boundary, ...] \| None = None) -> list[dict]` (rows `{"label","sha","kind","bot_version","plans","above_floor"}`); CLI `candidates` |
| V220-3 | AST migration scanner and its rules | 1b | opus — classifies Alembic revisions statement by statement | C `scripts/ops/rollback_migrations.py`, C `tests/scripts/test_rollback_migrations.py` | `MIGRATIONS_DIR = "swingbot/core/db/migrations/versions"`; `@dataclass Verdict(revision: str, path: str, safe: bool, reasons: list[str], override: str \| None)`; `scan_upgrade(source: str, *, revision: str = "?", path: str = "?") -> Verdict` (a non-blank module-level `ROLLBACK_SAFE` overrides); `split_sql(sql: str) -> list[str]` |
| V220-3b | Revision graph from a tree, `check_migrations`, `ROLLBACK_SAFE` audit | 1b | opus — reads Alembic graphs from git trees and may mark migration files | M `scripts/ops/rollback_migrations.py`, M `tests/scripts/test_rollback_migrations.py`, M `swingbot/core/db/migrations/versions/*.py` only where the audit finds an unsafe revision above the floor with a real reason | `@dataclass(frozen=True) Rev(revision: str, down: tuple[str, ...], path: str, source: str)`; `revision_graph(files: dict[str, str]) -> dict[str, Rev]`; `tree_migrations(repo: Path, sha: str) -> dict[str, str]`; `head_of(graph) -> str`; `between(graph, target_head: str, *, known: set[str] \| None = None) -> list[Rev]` (oldest first; `LookupError` when absent); `check_migrations(repo: Path, target_sha: str, head_sha: str) -> list[Verdict]` (every revision the target tree lacks: current graph minus target graph, via `known`); debug CLI `rollback_migrations.py <target_sha> [--head] [--repo]` |
| V220-4 | Config-key, compose `db` block and market-data writer checks | 1b | sonnet — pure stdlib checks in one new module | C `scripts/ops/rollback_checks.py`, C `tests/scripts/test_rollback_checks.py` | `CRITICAL_KEYS`; `declared_config_keys(source: str) -> list[str]` (raises `ValueError` when unparsable; also consumed by v221 `config_keys_sha256`); `env_key_names(env_text: str) -> set[str]`; `check_config(target_config: str, head_config: str, env_names: set[str]) -> tuple[list[str], list[str]]` (refusals, warnings); `compose_db_block(compose_text: str) -> str`; `check_compose(target_text: str, head_text: str) -> list[str]`; `MARKET_DATA_WRITER_PATHS: tuple[str, ...]`; `changed_writer_paths(repo: Path, target_sha: str, head_sha: str, paths=MARKET_DATA_WRITER_PATHS) -> list[str]`; `show(repo: Path, sha: str, path: str) -> str \| None` |
| V220-5 | Open-trade vocabulary check | 2 | sonnet — one SQL constant and a git-grep check in one module | M `scripts/ops/rollback_checks.py`, C `tests/scripts/test_rollback_vocabulary.py` | `VOCAB_SQL: str`; `psql_lines(sql: str, *, app_dir: Path, run=subprocess.run) -> list[str]`; `vocab_from_db(*, app_dir: Path, run=subprocess.run) -> dict[str, set[str]]` (keys `status`, `strategy`, `source`, `entry_type`, `ledger`, `lifecycle_kind`); `missing_vocabulary(repo: Path, sha: str, values: dict[str, set[str]]) -> list[str]` (`"<field>=<value>"`) |
| V220-6 | `check` report framework, checks 1/2/3/5, `run_checks` | 2 | sonnet — assembles earlier checks behind one CLI | M `scripts/ops/rollback_plan.py`, C `tests/scripts/test_rollback_plan_check.py` | `run_checks(sha: str, image: str, *, repo: Path, ref: str, env_path: Path, running_sha: str, hold_path: Path, host: bool = True) -> dict` (the CLI report shape); `deploy_line(kind: str, *, ts: str, git_sha: str, bot_image: str, db_image: str, from_sha: str) -> str`; CLI `check`, `deploy-line` |
| V220-6b | Checks 4/6/7, `deploy_line`, `check` and `deploy-line` CLIs | 2 | sonnet — completes the same report behind one CLI | M `scripts/ops/rollback_plan.py`, M `tests/scripts/test_rollback_plan_check.py` | `run_checks(..., allow_writer_drift=False, run=subprocess.run)`; `deploy_line(kind, *, ts, git_sha, bot_image, db_image, from_sha) -> str`; CLI `check` (`--allow-writer-drift`), `deploy-line` (`--ts` optional) |
| V220-7 | Rollback-window key snapshot and release report | 2 | sonnet — one new stdlib module with its own CLI | C `scripts/ops/rollback_window.py`, C `tests/scripts/test_rollback_window.py` | `KEYS_SQL: str`; `UPDATED_SQL: str`; `keys_snapshot(*, app_dir: Path, run=subprocess.run) -> dict` (`{"at", "plans": {id: [keys]}, "journal_entries": {id: [keys]}}`); `window_report(snapshot: dict, current: dict, updated: dict[str, list[str]]) -> dict`; CLI `snapshot`, `report` |
| V220-8 | `rollback_smoke`: write-free lifecycle evaluation | 2 | opus — crosses `swingbot/core/infra`, `planning` and `db` | C `swingbot/core/infra/rollback_smoke.py`, C `tests/db/test_rollback_smoke.py` | module `swingbot.core.infra.rollback_smoke`: `class ReadOnlyPlanStore` (wraps `PlanStore`; writes recorded in `.attempted`, never persisted), `evaluate(plans, journal_rows, *, manager_factory=None) -> dict` (the JSON line), `main(argv: list[str] \| None = None) -> int` |
| V220-9 | `rollback_code.sh`: self-copy, tools, resolve, checks, dry run | 3 | sonnet — one shell script from a fixed step list, text-pinned | C `scripts/ops/rollback_code.sh`, C `tests/scripts/test_rollback_code_shape.py` | the `rollback_code.sh` CLI (`--resolve`, `--candidates`, `<sha40> <image> --dry-run\|--i-mean-it [--reason] [--keep-refresher] [--allow-writer-drift]`) and env knobs; log `logs/rollback.log`; shell functions `stamp`, `log`, `refuse`, `git_d`, `planner`, `env_get`, `json_field`, `parse_args`, `fetch_tools`, `run_check`, `host_checks`, `print_plan`, `run_rollback`, `main`; globals `FROM_SHA`, `FROM_REF`, `FROM_IMAGE`, `FROM_REFRESHER`, `DB_IMAGE`, `START_REFRESHER` |
| V220-9b | `rollback_code.sh`: hold, switch, smoke, auto-restore, deploy line | 3 | sonnet — completes the same script from the spec's Execution steps, text-pinned | M `scripts/ops/rollback_code.sh`, M `tests/scripts/test_rollback_code_shape.py` | `--i-mean-it` path; `ROLLBACK_FORCE_SMOKE_FAIL`; key snapshot `backups/rollback_keys_<at>.json`; shell functions `services_for <start\|keep-stopped>`, `switch_image <image> <start\|keep-stopped>`, `record_line <kind> <sha> <image> <from_sha>`, `smoke`, `restore_previous` |
| V220-10 | `rollback_code.sh --release` | 3 | sonnet — second path of the same script, text-pinned | M `scripts/ops/rollback_code.sh`, M `tests/scripts/test_rollback_code_shape.py` | `--release` path; `kind: "release"` line; window report printed |
| V220-11 | Deploy hold in CI: `hold` job and `hold_notice.sh` | 3 | sonnet — workflow job graph plus a small VM script | M `.github/workflows/deploy.yml`, C `scripts/ops/hold_notice.sh`, M `tests/dev/test_ci_db_image.py`, C `tests/dev/test_deploy_hold_job.py` | job `hold` with output `held` (`'true'`/`'false'`); `cleanup` and `deploy` gated on it |
| V220-12 | Hold in `deploy.sh` phase 1 and the SessionStart `HOLD` line | 3b | sonnet — two small guards and a cached status helper | M `deploy/deploy.sh`, C `tests/scripts/test_deploy_hold_check.py`, C `scripts/dev/hold_status.py`, C `tests/dev/test_hold_status.py`, M `.claude/hooks/session-cursor.ps1` | `hold_status.py`: `hold_line(cache: dict \| None) -> str \| None`, `refresh(cache_path: Path, *, run=subprocess.run) -> dict`, CLI `--line`/`--refresh`; cache `logs/deploy_hold_cache.json` (`{"checked_at", "hold": dict \| None, "error": str \| None}`) |
| V220-15 | `/rollback` skill, `/deploy` refusal, Codex mirror | 4 | sonnet — skill prose from the fixed CLI contract | C `.claude/skills/rollback/SKILL.md`, M `.claude/skills/deploy/SKILL.md`, M `AGENTS.md`, C/M `.agents/skills/rollback/SKILL.md`, `.agents/skills/deploy/SKILL.md` (generated), M `tests/hooks/test_skill_shape.py`, M `docs/claude/skills-tools.md` | skill `rollback` (`disable-model-invocation: true`) |
| V220-17 | Release: bot patch, version history | 4 | haiku — fixed `VERSION.json` bump and regeneration | M `VERSION.json`, M `swingbot/admin/version_history.json` | — |
| V220-18 | Scratch-stack drill: rollback, forced smoke failure, release | 4 | sonnet — runs the shipped scripts on a scratch project and records the result | C `deploy/drill/rollback-drill.override.yml`, M `docs/deploy/DB_RESTORE.md`, C `tests/scripts/test_rollback_drill_override.py` | heading `## Code-only rollback (v220)` (new, last section; v221 V221-4 adds the comparison table under it) and the drill record `### Drill <date> (v220 V220-18)` |

V220-13 (stable manifest fields) and V220-14 (`pin-stable-image.yml`, retention exclusion, `/stable-snapshot` report) moved to [v221](2026-11-08-v221-stable-snapshot-rollback-fields.md) as V221-1..V221-3; V220-16 (`DB_RESTORE.md` comparison, `schema-evolution.md`, `schema-change` skill) moved to v221 as V221-4 when V220-9 split into V220-9/V220-9b at the 20 KB task cap; V220-18 now creates the `DB_RESTORE.md` heading itself. The remaining ids are unchanged. 20 ledger rows.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [`2026-11-08-v220-code-only-rollback_1-planner.md`](2026-11-08-v220-code-only-rollback_1-planner.md) | V220-1, V220-1b, V220-2, V220-2b | Target resolution (every form), the floor, picker candidates |
| 1b | [`2026-11-08-v220-code-only-rollback_1b-scanner-and-checks.md`](2026-11-08-v220-code-only-rollback_1b-scanner-and-checks.md) | V220-3, V220-3b, V220-4 | Migration scanner, tree-built revision graph and audit, config/compose/writer checks |
| 2 | [`2026-11-08-v220-code-only-rollback_2-checks-and-smoke.md`](2026-11-08-v220-code-only-rollback_2-checks-and-smoke.md) | V220-5, V220-6, V220-6b, V220-7 | Vocabulary check, `check` report (framework + checks 1/2/3/5, then 4/6/7 and `deploy-line`), window snapshot and report |
| 2b | [`2026-11-08-v220-code-only-rollback_2b-smoke.md`](2026-11-08-v220-code-only-rollback_2b-smoke.md) | V220-8 | `rollback_smoke`: write-free lifecycle evaluation |
| 3 | [`2026-11-08-v220-code-only-rollback_3-vm-script-and-hold.md`](2026-11-08-v220-code-only-rollback_3-vm-script-and-hold.md) | V220-9, V220-9b, V220-10, V220-11 | `rollback_code.sh` rollback (checks, then switch/smoke/restore) and release, the CI hold job |
| 3b | [`2026-11-08-v220-code-only-rollback_3b-hold-visibility.md`](2026-11-08-v220-code-only-rollback_3b-hold-visibility.md) | V220-12 | The `deploy.sh` hold and the SessionStart `HOLD` line |
| 4 | [`2026-11-08-v220-code-only-rollback_4-skills-and-drill.md`](2026-11-08-v220-code-only-rollback_4-skills-and-drill.md) | V220-15, V220-17, V220-18 | Skills, release, drill |

## Notes for the part writers

- **Findings from Part 1 (binding on later parts):** check 2 scans **every revision the target tree lacks** (current graph minus target graph, passed to `between(..., known=)`), not an ancestry walk from the target's head: the v197 branch tip carries `v197_001` with `down_revision = "v173_002"`, while on `main` it sits after `v201_001 → v200_001 → v205_001`. A bare date target is the **end of that UTC day**. A stable point's manifest is at `<repo>/backups/stable/<name>/manifest.json`.
- **Boundary shas are short;** `floor_violations` passes them to `git merge-base --is-ancestor`, which accepts abbreviations. A test asserts each `INCOMPATIBLE_BOUNDARIES` sha is an ancestor of `HEAD` in the real repo (skip when the repo is shallow).
- **`vNNN` matching:** `\(vNNN\)` matches scopes (`feat(v197):`) and trailing tags alike, so the first match is usually the spec's `docs(vNNN)` commit. The spec defines `vNNN-before` as its parent; follow it. Walk `git log <ref> --reverse --format=%H%x09%s` (all reachable commits, not `--first-parent`; merged branch commits are reachable). `merge main into v197` has no parentheses and does not match.
- **`bot-A.B.C`:** the oldest commit from `git log <ref> --reverse -S'"bot": "A.B.C"' --format=%H -- VERSION.json` whose `git show <sha>:VERSION.json` has `bot == A.B.C`.
- **Date form:** `pitr_resolve.load_deploys` cannot be imported from the copy in `$WORK` unless copied too; reimplement a 10-line reader in `rollback_plan.py` (lines are dicts with a truthy `ts`, sorted by `ts`, last at or before the moment). Rollback/release lines are deploys for this purpose (they record what was live).
- **Revision chain is not numeric:** today `v173_002 → v201_001 → v200_001 → v205_001 → v197_001 → v207_001 → v204_001` (head); `p6_000_merge_p2_p3` has a tuple `down_revision`. Revisions above the floor today: `v207_001`, `v204_001` (both `create_table`/`create_index` only, expected safe without `ROLLBACK_SAFE`); `v200_001` (uses `op.get_bind()`, unsafe) and `v197_001` (helper calls, unsafe) sit at or below the floor's head, so no target above the floor walks them. The V220-3b real-repo test pins that every revision classifies without error and that every revision above the floor is safe or carries `ROLLBACK_SAFE`; the audit adds `ROLLBACK_SAFE` only where the reason is real.
- **`MARKET_DATA_WRITER_PATHS`:** `swingbot/refresher/`, `swingbot/core/marketdata/data_store.py` (`save_to_disk`, the only writer of `market_data/<interval>/<TICKER>.csv`) and `swingbot/core/marketdata/data_refresh.py` (`refresh_symbol`). V220-4 confirms with `git grep -n "save_to_disk(\|refresh_symbol("` that no other package writes the cache and adds any it finds (e.g. `swingbot/core/marketdata/shared/` if `admin_refresh` writes it).
- **Vocabulary sources:** `plans` table columns `status`, `strategy` plus doc fields `source`, `entry_type`, `ledger` for open statuses (`PENDING`, `ACTIVE`, `PARTIAL`, `plan_store._OPEN_STATUSES`); `journal_entries.strategy` where `closed_at IS NULL`; lifecycle event `kind` from the v197 queue table (find its name in `v197_001`'s `upgrade()` / `repositories/notify_queue.py`). Each value must occur as a quoted literal (`"x"` or `'x'`) in the target tree: `git grep -l -F -e '"x"' -e "'x'" <sha> -- swingbot`.
- **`rollback_smoke`:** a write-free run needs two locks. (1) `ReadOnlyPlanStore` (reads delegate to `PlanStore`; `add`/`update`/`lock_for_update` record the plan id in `.attempted` and return without touching the store). (2) A database session forced read-only (`SET SESSION default_transaction_read_only = on` on connect for the engine the module builds), so any writer the step reaches raises instead of writing. Price per plan = its entry price (no network); `PlanManager(store, price_fn=…, trade_log=None)` with every optional fn `None`. Any exception from `_step` (call it directly, not `_step_safely`, which swallows) is an error; any write attempt is reported but not an error (the store absorbed it). The test asserts row counts and every `updated_at` are unchanged afterwards.
- **The hold job's output:** `appleboy/ssh-action@v1.2.5` supports `capture_stdout: true` with output `stdout`; V220-11 verifies that from the action's README at that tag (`gh api repos/appleboy/ssh-action/contents/README.md?ref=v1.2.5`) before relying on it, and a follow-up `run:` step writes `held=true|false` to `$GITHUB_OUTPUT` from a `HELD ` prefix line. The `deploy` job's `if:` is `always() && <main push> && needs.hold.result == 'success' && needs.hold.outputs.held != 'true' && <docker-build, db-image, publish-image, compose-lint succeeded> && contains(fromJSON('["success","skipped"]'), needs.cleanup.result)` (fail closed when the hold check itself fails). The hold job fetches `hold_notice.sh` with `git -C "$APP_DIR" fetch -q origin main && git -C "$APP_DIR" show origin/main:scripts/ops/hold_notice.sh > /tmp/hold_notice.sh` only when the hold file exists.
- **Drill stack:** `docker-compose.yml` hard-codes `container_name` (`swing-db`, `swing-bot-admin`, `swing-refresher`), so the scratch project needs `deploy/drill/rollback-drill.override.yml` renaming them (`rbdrill-*`), clearing host ports (`ports: !reset []`) and leaving out `cloudflared`. The bot service is not started in the drill (a second bot on the real token would post to the live guild); `ROLLBACK_DRILL=1` skips it and its heartbeat check. Seed the scratch database with `pg_dump` from production piped into the scratch `db` (read-only on production). Precedent: `scripts/ops/pitr_drill.sh` (`swingbot-drill` project, removed afterwards).
- **Check 6 is a refusal (spec amended 2026-11-08):** a non-empty `changed_writer_paths` refuses in `run_checks` (V220-6) unless `--allow-writer-drift` is passed to `check` and `rollback_code.sh` (V220-9), because `swingbot/admin/freshness.py` calls the same writers from the admin container; with the override, `refresher: "keep-stopped"` and the report warns that the admin may still write. The `/rollback` skill (V220-15) asks the partner before adding the flag.
