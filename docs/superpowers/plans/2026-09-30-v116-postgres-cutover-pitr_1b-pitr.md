# v116 — Part 1b: Phase 0, point-in-time rollback (V116-06 … V116-10)

Continues `_1a-pitr.md`, which carries this phase's parallelisation and worktree setup. Header, global constraints and revision ids: `_0-index.md`.

---

# Phase 0 — Point-in-time rollback (continued)

### Task V116-06: `rollback_to.sh` and its resolver; `parity_report --dual`

**Files:**
- Create: `scripts/ops/pitr_resolve.py`
- Create: `scripts/ops/rollback_to.sh`
- Modify: `scripts/db/parity_report.py` (add `STAGE_STORES`, `dual_stores()`, `--dual`)
- Create: `tests/scripts/test_pitr_resolve.py`, `tests/scripts/test_rollback_to_shape.py`, `tests/scripts/test_parity_dual.py`

**Interfaces:**
- Consumes: `env_snapshot.snapshot_names/stamp_of` and `env_set.py` (V116-03); `backups/deploys.jsonl` (V116-04); `restic_hourly.sh` (V116-05).
- Produces: `pitr_resolve.parse_ts(text) -> datetime`, `load_deploys(path) -> list[dict]` (each with `_at`), `env_versions(dir) -> list[tuple[datetime, str]]`, `restic_snapshots(json_text) -> list[tuple[datetime, str]]`, `pgbackrest_oldest(json_text) -> datetime | None`, `resolve(target, now, deploys, envs, snapshots, pg_oldest) -> Resolution`, `shell_lines(res) -> list[str]`; exit code 2 = refused. `parity_report.STAGE_STORES: dict[str, tuple[str, ...]]` (stage name → parity stores) and `parity_report.dual_stores() -> list[str]` — V116-24 reuses both. `logs/rollback.log` gets one line per started rollback (V116-33 reads it).

- [ ] **Step 1: Write the failing tests**

`tests/scripts/test_pitr_resolve.py`:

```python
"""pitr_resolve: what rollback_to.sh restores for a target second (v116)."""
import ast
import datetime as dt
import json
import pathlib
import shlex
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import pitr_resolve as pr  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
FIRST_BACKUP_STOP = dt.datetime(2026, 9, 1, 1, 0, tzinfo=UTC)


@pytest.fixture
def inputs(tmp_path):
    deploys = tmp_path / "deploys.jsonl"
    deploys.write_text(
        json.dumps({"ts": "2026-09-01T00:00:00Z", "git_sha": "a" * 40,
                    "bot_image": "ghcr.io/o/r:sha-aaa", "db_image": "ghcr.io/o/r-db:pgcfg-111"}) + "\n"
        + "not json\n"
        + json.dumps({"ts": "2026-09-20T12:00:00Z", "git_sha": "b" * 40,
                      "bot_image": "ghcr.io/o/r:sha-bbb", "db_image": "ghcr.io/o/r-db:pgcfg-111"}) + "\n",
        encoding="utf-8")
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    for name in ("2026-09-01T00-00-00-000000Z.env", "2026-09-25T08-00-00-000000Z.env"):
        (env_dir / name).write_text(name, encoding="utf-8")
    restic = json.dumps([
        {"time": "2026-09-25T07:07:01.123456789Z", "short_id": "aaaa1111", "id": "aaaa1111ff"},
        {"time": "2026-09-25T08:07:02.5Z", "short_id": "bbbb2222", "id": "bbbb2222ff"},
    ])
    pgbackrest = json.dumps([{"name": "swingbot", "backup": [
        {"type": "full", "timestamp": {"start": int(FIRST_BACKUP_STOP.timestamp()) - 600,
                                       "stop": int(FIRST_BACKUP_STOP.timestamp())}}]}])
    return {"deploys": pr.load_deploys(str(deploys)), "envs": pr.env_versions(str(env_dir)),
            "snapshots": pr.restic_snapshots(restic), "pg_oldest": pr.pgbackrest_oldest(pgbackrest),
            "paths": (deploys, env_dir, restic, pgbackrest)}


def _resolve(inputs, target):
    return pr.resolve(target, NOW, inputs["deploys"], inputs["envs"], inputs["snapshots"],
                      inputs["pg_oldest"])


def test_parse_ts_accepts_every_form_the_inputs_use():
    expected = dt.datetime(2026, 9, 25, 8, 0, 30, tzinfo=UTC)
    for text in ("2026-09-25T08:00:30Z", "2026-09-25 08:00:30", "2026-09-25T08:00:30+00:00"):
        assert pr.parse_ts(text) == expected
    assert pr.parse_ts("2026-09-25T08:00:30.123456789Z") == expected.replace(microsecond=123456)


def test_a_malformed_deploy_line_is_skipped(inputs):
    assert [row["git_sha"][0] for row in inputs["deploys"]] == ["a", "b"]


def test_resolves_the_artifacts_current_at_the_target(inputs):
    res = _resolve(inputs, dt.datetime(2026, 9, 25, 8, 0, 30, tzinfo=UTC))
    assert res.refusals == []
    assert res.deploy["git_sha"] == "b" * 40
    assert res.env_file.endswith("2026-09-25T08-00-00-000000Z.env")
    assert res.restic[1] == "aaaa1111"          # 08:07 is after the target


def test_refuses_a_future_target(inputs):
    res = _resolve(inputs, NOW + dt.timedelta(seconds=1))
    assert any("future" in line for line in res.refusals)


def test_refuses_a_target_before_the_oldest_restorable_point(inputs):
    res = _resolve(inputs, FIRST_BACKUP_STOP - dt.timedelta(seconds=1))
    assert any("oldest restorable point" in line for line in res.refusals)


def test_refuses_when_no_market_data_snapshot_predates_the_target(inputs):
    res = _resolve(inputs, dt.datetime(2026, 9, 10, tzinfo=UTC))
    assert "no market_data snapshot at or before the target" in res.refusals


def test_main_prints_assignments_a_shell_can_eval(inputs, tmp_path, capsys):
    deploys, env_dir, restic, pgbackrest = inputs["paths"]
    (tmp_path / "r.json").write_text(restic, encoding="utf-8")
    (tmp_path / "p.json").write_text(pgbackrest, encoding="utf-8")
    code = pr.main(["--target", "2026-09-25T08:00:30Z", "--now", "2026-10-01T12:00:00Z",
                    "--deploys", str(deploys), "--env-dir", str(env_dir),
                    "--restic-json", str(tmp_path / "r.json"),
                    "--pgbackrest-json", str(tmp_path / "p.json")])
    assert code == 0
    pairs = dict(shlex.split(line)[0].split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert pairs["target_pg"] == "2026-09-25 08:00:30+00"
    assert pairs["bot_image"] == "ghcr.io/o/r:sha-bbb"
    assert pairs["restic_id"] == "aaaa1111"


def test_main_exits_2_with_refusals(inputs, tmp_path, capsys):
    deploys, env_dir, restic, pgbackrest = inputs["paths"]
    (tmp_path / "r.json").write_text(restic, encoding="utf-8")
    (tmp_path / "p.json").write_text(pgbackrest, encoding="utf-8")
    code = pr.main(["--target", "2027-01-01T00:00:00Z", "--now", "2026-10-01T12:00:00Z",
                    "--deploys", str(deploys), "--env-dir", str(env_dir),
                    "--restic-json", str(tmp_path / "r.json"),
                    "--pgbackrest-json", str(tmp_path / "p.json")])
    assert code == 2
    assert capsys.readouterr().out.startswith("REFUSE: ")


def test_it_is_stdlib_only_apart_from_env_snapshot():
    tree = ast.parse((ROOT / "scripts" / "ops" / "pitr_resolve.py").read_text(encoding="utf-8"))
    roots = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    froms = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert roots <= set(sys.stdlib_module_names)
    assert {m for m in froms if m.split(".")[0] not in sys.stdlib_module_names} \
        <= {"__future__", "swingbot.core.infra"}
```

`tests/scripts/test_rollback_to_shape.py`:

```python
"""rollback_to.sh's step order (spec § rollback_to.sh). The real restore is
proven by the V116-10 drill; this pins the order an edit could break."""
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "rollback_to.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


def test_the_steps_run_in_the_spec_order(src):
    markers = [
        "pitr_resolve.py",                                 # 1 + 3 refuse / resolve
        'if [ "$DRY_RUN" = 1 ]',                           # --dry-run stops here
        "--type=diff backup",                              # 2 checkpoint of now
        "scripts/ops/restic_hourly.sh",
        "docker compose stop bot admin",                   # 4
        "restic restore",                                  # 5
        'cat "$env_file" > .env',                          # 6 (in place)
        "env_set.py SWING_BOT_IMAGE",
        "--type=time",                                     # 7
        "scan_paused",                                     # 8 pause before start
        "docker compose up -d --no-build --wait bot admin",  # 9
        "parity_report.py --dual",
    ]
    positions = [src.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_the_restore_promotes_and_uses_delta(src):
    assert "--delta" in src and "--target-action=promote" in src


def test_images_must_still_be_on_ghcr_before_anything_stops(src):
    assert src.index("docker manifest inspect") < src.index("docker compose stop bot admin")


def test_it_logs_every_rollback_and_never_sed(src):
    assert "logs/rollback.log" in src
    assert "sed -i" not in src
    assert "set -euo pipefail" in src
    assert b"\r" not in SCRIPT.read_bytes()
```

`tests/scripts/test_parity_dual.py`:

```python
"""parity_report --dual: compare only stores that are at dual right now."""
from swingbot import config
from scripts.db import parity_report as pr


def test_every_parity_store_belongs_to_exactly_one_stage():
    covered = [store for stores in pr.STAGE_STORES.values() for store in stores]
    assert sorted(covered) == sorted(pr.STORES)


def test_dual_stores_follows_db_stores(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual,state:db,tuning:dual")
    assert pr.dual_stores() == ["tuning", "tuning_proposals", "watchlist"]


def test_dual_is_a_no_op_when_nothing_is_dual(monkeypatch, capsys):
    monkeypatch.setattr(config, "DB_STORES", "")
    assert pr.main(["--dual"]) == 0
    assert "no-op" in capsys.readouterr().out


def test_dual_runs_parity_for_each_dual_store(monkeypatch):
    class Clean:
        ok = True

        def render(self):
            return "clean"

    seen = []
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual")
    monkeypatch.setattr(pr, "parity", lambda name, source_path=None: seen.append(name) or Clean())
    assert pr.main(["--dual"]) == 0
    assert seen == ["watchlist"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_pitr_resolve.py tests/scripts/test_rollback_to_shape.py tests/scripts/test_parity_dual.py`
Expected: FAIL — `ModuleNotFoundError: pitr_resolve`, missing script, `AttributeError: STAGE_STORES`.

- [ ] **Step 3: Create `scripts/ops/pitr_resolve.py`**

```python
#!/usr/bin/env python3
"""Resolve what rollback_to.sh restores for one target second (v116 Phase 0).

Reads backups/deploys.jsonl, the backups/env/ versions, `restic snapshots
--json` and `pgbackrest info --output=json`. Prints REFUSE lines (exit 2), or
shell assignments for `eval` (exit 0). Stdlib only: it runs on the VM host
while the containers are stopped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from swingbot.core.infra import env_snapshot  # noqa: E402  (stdlib-only)

UTC = dt.timezone.utc


def parse_ts(text: str) -> dt.datetime:
    """`...Z`, `YYYY-MM-DD HH:MM:SS`, `+00:00`, and restic's nanoseconds. Naive is UTC."""
    raw = text.strip().replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    head, dot, tail = raw.partition(".")
    if dot:
        digits = "".join(ch for ch in tail if ch.isdigit())
        raw = f"{head}.{digits[:6]}{tail[len(digits):]}"
    parsed = dt.datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json_line(line: str) -> dict | None:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    return row if isinstance(row, dict) and row.get("ts") else None


def load_deploys(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        rows = [row for row in map(_json_line, handle) if row is not None]
    return sorted(({**row, "_at": parse_ts(row["ts"])} for row in rows), key=lambda r: r["_at"])


def env_versions(directory: str) -> list[tuple[dt.datetime, str]]:
    return [(env_snapshot.stamp_of(name), os.path.join(directory, name))
            for name in env_snapshot.snapshot_names(directory)]


def restic_snapshots(text: str) -> list[tuple[dt.datetime, str]]:
    rows = json.loads(text or "[]") or []
    return sorted((parse_ts(row["time"]), row.get("short_id") or row["id"][:8])
                  for row in rows if row.get("time"))


def pgbackrest_oldest(text: str) -> dt.datetime | None:
    stanzas = json.loads(text or "[]") or []
    stops = [backup["timestamp"]["stop"] for stanza in stanzas
             for backup in stanza.get("backup", [])]
    return dt.datetime.fromtimestamp(min(stops), UTC) if stops else None


def last_at_or_before(items: list[tuple], target: dt.datetime):
    eligible = [item for item in items if item[0] <= target]
    return eligible[-1] if eligible else None


@dataclass
class Resolution:
    target: dt.datetime
    deploy: dict | None = None
    env_file: str | None = None
    restic: tuple | None = None
    refusals: list[str] = field(default_factory=list)


def _refusals(target, now, pg_oldest, found: dict) -> list[str]:
    out = []
    if target > now:
        out.append(f"target {target.isoformat()} is in the future (now {now.isoformat()})")
    if pg_oldest is None:
        out.append("pgBackRest has no completed backup, so nothing is restorable")
    elif target < pg_oldest:
        out.append(f"target is older than the oldest restorable point {pg_oldest.isoformat()}")
    out.extend(f"no {label} at or before the target" for label, item in found.items() if item is None)
    return out


def resolve(target, now, deploys, envs, snapshots, pg_oldest) -> Resolution:
    deploy = last_at_or_before([(row["_at"], row) for row in deploys], target)
    env = last_at_or_before(envs, target)
    snap = last_at_or_before(snapshots, target)
    found = {"deploy record": deploy, ".env version": env, "market_data snapshot": snap}
    return Resolution(target=target, deploy=deploy[1] if deploy else None,
                      env_file=env[1] if env else None, restic=snap,
                      refusals=_refusals(target, now, pg_oldest, found))


def shell_lines(res: Resolution) -> list[str]:
    pairs = {
        "target_pg": res.target.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S+00"),
        "git_sha": res.deploy["git_sha"],
        "bot_image": res.deploy["bot_image"],
        "db_image": res.deploy["db_image"],
        "env_file": res.env_file,
        "restic_id": res.restic[1],
        "restic_time": res.restic[0].isoformat(),
    }
    return [f"{key}={shlex.quote(str(value))}" for key, value in pairs.items()]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True)
    parser.add_argument("--now")
    parser.add_argument("--deploys", default="backups/deploys.jsonl")
    parser.add_argument("--env-dir", default="backups/env")
    parser.add_argument("--restic-json", required=True)
    parser.add_argument("--pgbackrest-json", required=True)
    args = parser.parse_args(argv)
    now = parse_ts(args.now) if args.now else dt.datetime.now(UTC)
    res = resolve(parse_ts(args.target).astimezone(UTC), now, load_deploys(args.deploys),
                  env_versions(args.env_dir), restic_snapshots(_read(args.restic_json)),
                  pgbackrest_oldest(_read(args.pgbackrest_json)))
    if res.refusals:
        print("\n".join(f"REFUSE: {line}" for line in res.refusals))
        return 2
    print("\n".join(shell_lines(res)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add `STAGE_STORES`, `dual_stores()` and `--dual` to `scripts/db/parity_report.py`**

After the `STORES` dict:

```python
#: Stage name (a `config.DB_STORES` key) -> the parity stores it governs.
#: `tuning` governs both tuning tables; five ops stages (flags, heartbeat,
#: notify_queue, scan_progress, market_data_state) are ephemeral and have no
#: parity spec, so they are absent here on purpose.
STAGE_STORES: dict[str, tuple[str, ...]] = {
    "watchlist": ("watchlist",), "state": ("state",),
    "plans": ("plans",), "starred_plans": ("starred_plans",), "trades": ("trades",),
    "account": ("account",), "journal": ("journal",),
    "jobs": ("jobs",), "scheduled_jobs": ("scheduled_jobs",),
    "preferences": ("preferences",), "settings_audit": ("settings_audit",),
    "killswitch": ("killswitch",), "ticker_directory": ("ticker_directory",),
    "tuning": ("tuning", "tuning_proposals"),
}


def dual_stores() -> list[str]:
    """Parity stores whose stage is `dual` now -- the only ones where the JSON
    file and the table are both written and so must agree. At `db` the file
    is stale by design, so comparing it would report noise."""
    from swingbot.core.db import stages
    return sorted(store for stage_name, stores in STAGE_STORES.items()
                  if stages.stage_for(stage_name) == stages.DUAL for store in stores)
```

Replace `main` with:

```python
def _selected(args) -> list[str]:
    if args.dual:
        return dual_stores()
    return sorted(STORES) if args.all else [args.store]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", choices=sorted(STORES))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dual", action="store_true",
                        help="only the stores whose stage is dual right now")
    args = parser.parse_args(argv)
    if not (args.store or args.all or args.dual):
        parser.error("pass --store <name>, --all or --dual")
    names = _selected(args)
    if not names:
        print("parity: no store is at dual -- nothing to compare (no-op)")
        return 0
    failures = 0
    for name in names:
        report = parity(name)
        print(f"[{name}]")
        print(report.render())
        failures += not report.ok
    return int(bool(failures))
```

- [ ] **Step 5: Create `scripts/ops/rollback_to.sh`**

```bash
#!/usr/bin/env bash
# Roll the whole bot back to one UTC second in the last 30 days (v116 Phase 0).
#
#   scripts/ops/rollback_to.sh "2026-10-14 13:05:00" [--dry-run]
#
# Restores Postgres to the second (pgBackRest PITR), market_data/ (restic),
# .env (backups/env) and the bot + db images (backups/deploys.jsonl), then
# starts with scanning PAUSED -- unpause from the admin UI. Not rolled back, by
# design: Discord messages already posted, logs, telemetry, caches.
# While a store is still at json/dual its data/*.json file is the source of
# truth and is NOT rolled back; the dry run lists those stores.
# Runs ON the VM as root. Spec: 2026-09-30-v116 § rollback_to.sh.
set -euo pipefail
cd /opt/swing-bot

TARGET="${1:?usage: rollback_to.sh '<UTC timestamp>' [--dry-run]}"
DRY_RUN=0
[ "${2:-}" = "--dry-run" ] && DRY_RUN=1
LOG=logs/rollback.log
mkdir -p backups
WORK="$(mktemp -d /opt/swing-bot/backups/rollback.XXXXXX)"   # same filesystem: mv is atomic
trap 'rm -rf "$WORK"' EXIT

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
export RESTIC_PASSWORD
export RESTIC_REPOSITORY=/opt/swing-bot/backups/restic

# 1 + 3. Refuse an unrestorable target; resolve the artifacts current at it.
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --output=json info \
  </dev/null > "$WORK/pgbackrest.json"
restic snapshots --host swing-bot --tag market_data --json > "$WORK/restic.json"
PLAN="$(python3 scripts/ops/pitr_resolve.py --target "$TARGET" \
  --deploys backups/deploys.jsonl --env-dir backups/env \
  --restic-json "$WORK/restic.json" --pgbackrest-json "$WORK/pgbackrest.json")" \
  || { echo "$PLAN"; exit 2; }
eval "$PLAN"
echo "Target $TARGET resolves to:"
echo "  code       git $git_sha"
echo "  bot image  $bot_image"
echo "  db image   $db_image"
echo "  .env       $env_file"
echo "  market     restic $restic_id ($restic_time)"
if ! docker manifest inspect "$bot_image" >/dev/null || ! docker manifest inspect "$db_image" >/dev/null; then
  echo "REFUSE: an image recorded for the target is no longer on GHCR"
  exit 2
fi
echo "Stores whose JSON file stays as it is now (not at db at the target):"
grep -E '^[[:space:]]*DB_STORES[[:space:]]*=' "$env_file" | tail -1 || echo "  DB_STORES unset: every store is json"
if [ "$DRY_RUN" = 1 ]; then
  echo "Dry run: nothing changed."
  exit 0
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback to $TARGET started (git $git_sha)" >> "$LOG"

# 2. Checkpoint of now, so the rollback itself can be undone. PITR opens a new
# timeline; a later restore can still target any second on the old one.
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=diff backup </dev/null
scripts/ops/restic_hourly.sh
python3 -m swingbot.core.infra.env_snapshot snapshot .env

# 4. Stop the writers.
docker compose stop bot admin

# 5. market_data, swapped in atomically.
restic restore "$restic_id" --target "$WORK/md" --include /opt/swing-bot/market_data
mv market_data "backups/market_data.pre-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
mv "$WORK/md/opt/swing-bot/market_data" market_data

# 6. Config and code: the .env of the target, in place; the images of the target.
cat "$env_file" > .env
python3 scripts/ops/env_set.py SWING_BOT_IMAGE "$bot_image"
python3 scripts/ops/env_set.py SWING_BOT_DB_IMAGE "$db_image"
docker pull "$bot_image"
docker pull "$db_image"

# 7. Postgres to the second.
docker compose stop db
docker compose run --rm --no-deps -u postgres --entrypoint pgbackrest db \
  --stanza=swingbot --delta --type=time "--target=$target_pg" --target-action=promote restore
docker compose up -d --no-build --wait db

# 8. Pause scanning BEFORE the bot starts: otherwise it re-posts alerts for
# setups it had already alerted on after the target second.
touch data/scan_paused.flag
docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c \
  "INSERT INTO runtime_flags (name, set_at) VALUES ('scan_paused', now())
   ON CONFLICT (name) DO UPDATE SET set_at = EXCLUDED.set_at" </dev/null

# 9. Start and verify.
docker compose up -d --no-build --wait bot admin
echo "--- alembic (current must equal heads) ---"
docker compose exec -T bot alembic current </dev/null
docker compose exec -T bot alembic heads </dev/null
echo "--- parity (dual stores only; a no-op when none is dual) ---"
docker compose exec -T bot python scripts/db/parity_report.py --dual </dev/null || true
docker compose ps
echo "Restored: Postgres to $TARGET, market_data to $restic_time, .env $env_file, images of git $git_sha."
echo "Scanning is PAUSED. Unpause from the admin UI once the book looks right."
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback to $TARGET finished" >> "$LOG"
```

- [ ] **Step 6: Run the tests, and bash's syntax check**

Run: `python scripts/dev/testrun.py file tests/scripts/test_pitr_resolve.py tests/scripts/test_rollback_to_shape.py tests/scripts/test_parity_dual.py tests/scripts/test_parity_report.py`
Expected: PASS. `bash -n scripts/ops/rollback_to.sh` — no output.

- [ ] **Step 7: Complexity and commit**

Run: `python -m radon cc -s -n C scripts/ops/pitr_resolve.py scripts/db/parity_report.py` — no output.

```bash
git add --chmod=+x scripts/ops/pitr_resolve.py scripts/ops/rollback_to.sh
git add scripts/db/parity_report.py tests/scripts/test_pitr_resolve.py tests/scripts/test_rollback_to_shape.py tests/scripts/test_parity_dual.py
git commit -m "feat(v116): rollback_to.sh -- whole-bot point-in-time rollback; parity_report --dual

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-07: Alarms — WAL archiver failures and backups-disk usage

**Files:**
- Create: `swingbot/core/infra/pitr_watch.py`
- Modify: `swingbot/commands/scanning/notices.py` (add `pitr_notice_embed`)
- Modify: `swingbot/commands/scanning/loops.py` (new `pitr_watch_loop`; `on_ready` loop starts moved into `_start_background_loops`)
- Create: `tests/infra/test_pitr_watch.py`, `tests/commands/test_pitr_watch_loop.py`

**Interfaces:**
- Consumes: `swingbot.core.db.engine.get_engine`, `loops._ops_channel()`, `notices.system_embed`, `notices.send_guarded`, `Kind.HEALTH_ALERT`/`Kind.HEALTH_RECOVERED`.
- Produces: `pitr_watch.DISK_ALARM_PCT = 80.0`, `ArchiverSample(failed_count, last_failed_time, last_archived_time)`, `read_archiver() -> ArchiverSample | None`, `archiver_failing(previous, current) -> bool`, `disk_used_pct(path) -> float`, `Notice(recovered, detail, description)`, `PitrWatch.tick(sample, used_pct) -> list[Notice]`; `notices.pitr_notice_embed(notice)`; `loops.pitr_watch_loop` (15 min), `loops._start_background_loops()`, `loops._always_on_loops()`.

- [ ] **Step 1: Write the failing tests**

`tests/infra/test_pitr_watch.py`:

```python
"""PITR alarms: one alert and one recovery per episode (v116 Phase 0)."""
import datetime as dt

from swingbot import config
from swingbot.core.infra import pitr_watch as pw

T = dt.datetime(2026, 10, 1, 10, 0, tzinfo=dt.timezone.utc)
OK = pw.ArchiverSample(0, None, T)


def test_growth_in_failed_count_is_failing():
    assert pw.archiver_failing(OK, pw.ArchiverSample(1, T, T - dt.timedelta(minutes=5))) is True


def test_a_failure_newer_than_the_last_success_is_failing_without_history():
    assert pw.archiver_failing(None, pw.ArchiverSample(3, T, T - dt.timedelta(minutes=1))) is True


def test_an_old_failure_followed_by_success_is_healthy():
    assert pw.archiver_failing(None, pw.ArchiverSample(3, T - dt.timedelta(hours=1), T)) is False


def test_archiver_alarm_fires_once_then_recovers_once():
    watch = pw.PitrWatch()
    assert watch.tick(OK, 10.0) == []
    failing = pw.ArchiverSample(1, T, T - dt.timedelta(minutes=5))
    first = watch.tick(failing, 10.0)
    assert [n.recovered for n in first] == [False]
    assert watch.tick(pw.ArchiverSample(2, T + dt.timedelta(minutes=1), T), 10.0) == []
    healed = watch.tick(pw.ArchiverSample(2, T, T + dt.timedelta(minutes=2)), 10.0)
    assert [n.recovered for n in healed] == [True]


def test_disk_alarm_is_strictly_above_eighty_percent():
    watch = pw.PitrWatch()
    assert watch.tick(None, 80.0) == []
    alert = watch.tick(None, 80.1)
    assert len(alert) == 1 and not alert[0].recovered and "80%" in alert[0].detail
    assert watch.tick(None, 95.0) == []
    assert [n.recovered for n in watch.tick(None, 50.0)] == [True]


def test_an_unreadable_archiver_changes_nothing():
    watch = pw.PitrWatch()
    watch.tick(pw.ArchiverSample(1, T, None), 10.0)
    assert watch.archiver_alarm is True
    assert watch.tick(None, 10.0) == []
    assert watch.archiver_alarm is True


def test_disk_used_pct_is_a_percentage(tmp_path):
    assert 0.0 <= pw.disk_used_pct(str(tmp_path)) <= 100.0


def test_read_archiver_reads_the_real_view(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    sample = pw.read_archiver()
    reset_engine()
    assert sample is not None and sample.failed_count >= 0
```

`tests/commands/test_pitr_watch_loop.py`:

```python
"""The PITR alarm loop posts to the ops channel once per episode."""
import asyncio
import datetime as dt

from swingbot.commands.scanning import loops
from swingbot.core.infra import pitr_watch

T = dt.datetime(2026, 10, 1, 10, 0, tzinfo=dt.timezone.utc)


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append({"content": content, **kw})


def _arm(monkeypatch, sample, used):
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops, "_PITR_WATCH", pitr_watch.PitrWatch())
    monkeypatch.setattr(pitr_watch, "read_archiver", lambda: sample)
    monkeypatch.setattr(pitr_watch, "disk_used_pct", lambda _path: used)
    return channel


def test_a_failing_archiver_posts_one_health_alert(monkeypatch):
    channel = _arm(monkeypatch, pitr_watch.ArchiverSample(4, T, T - dt.timedelta(minutes=9)), 20.0)
    asyncio.run(loops.pitr_watch_loop.coro())
    asyncio.run(loops.pitr_watch_loop.coro())
    assert len(channel.sent) == 1
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "WAL archiving failing" in channel.sent[0]["embed"].title


def test_a_healthy_tick_posts_nothing(monkeypatch):
    channel = _arm(monkeypatch, pitr_watch.ArchiverSample(0, None, T), 20.0)
    asyncio.run(loops.pitr_watch_loop.coro())
    assert channel.sent == []


def test_the_loop_is_started_with_the_others():
    assert loops.pitr_watch_loop in loops._always_on_loops()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_pitr_watch.py tests/commands/test_pitr_watch_loop.py`
Expected: FAIL — `ImportError: cannot import name 'pitr_watch'`.

- [ ] **Step 3: Create `swingbot/core/infra/pitr_watch.py`**

```python
"""Point-in-time-recovery alarms the bot polls (v116 Phase 0).

Two conditions, each posted to the ops channel once per episode:

* the WAL archiver is failing. A failing ``archive_command`` piles WAL up on
  the database disk, so a silent archiver ends in a full disk AND a PITR window
  that quietly stopped growing -- this alarm is not optional (spec § Proof);
* the disk holding data/ and backups/ (one VM disk) is more than 80% full.

Pure apart from ``read_archiver`` and ``disk_used_pct``.
"""
from __future__ import annotations

import datetime as dt
import logging
import shutil
from dataclasses import dataclass

log = logging.getLogger(__name__)

DISK_ALARM_PCT = 80.0
ARCHIVER_SQL = ("SELECT failed_count, last_failed_time, last_archived_time "
                "FROM pg_stat_archiver")


@dataclass(frozen=True)
class ArchiverSample:
    failed_count: int
    last_failed_time: dt.datetime | None
    last_archived_time: dt.datetime | None


@dataclass(frozen=True)
class Notice:
    recovered: bool
    detail: str
    description: str


def read_archiver() -> ArchiverSample | None:
    """The pg_stat_archiver row, or None when the database cannot be read."""
    import sqlalchemy as sa

    from swingbot.core.db.engine import get_engine
    try:
        with get_engine().connect() as conn:
            row = conn.execute(sa.text(ARCHIVER_SQL)).one()
    except Exception:  # noqa: BLE001 -- unreadable is "unknown", not an alarm
        log.debug("pitr watch: pg_stat_archiver unreadable", exc_info=True)
        return None
    return ArchiverSample(int(row[0] or 0), row[1], row[2])


def archiver_failing(previous: ArchiverSample | None, current: ArchiverSample) -> bool:
    grew = previous is not None and current.failed_count > previous.failed_count
    failed, archived = current.last_failed_time, current.last_archived_time
    stuck = failed is not None and (archived is None or failed > archived)
    return grew or stuck


def disk_used_pct(path: str) -> float:
    usage = shutil.disk_usage(path)
    return 100.0 * usage.used / usage.total if usage.total else 0.0


class PitrWatch:
    """Successive samples in, at most one alert and one recovery per episode out."""

    def __init__(self) -> None:
        self._previous: ArchiverSample | None = None
        self.archiver_alarm = False
        self.disk_alarm = False

    def tick(self, sample: ArchiverSample | None, used_pct: float) -> list[Notice]:
        notices = self._archiver(sample) if sample is not None else []
        return notices + self._disk(used_pct)

    def _archiver(self, sample: ArchiverSample) -> list[Notice]:
        failing = archiver_failing(self._previous, sample)
        self._previous = sample
        if failing == self.archiver_alarm:
            return []
        self.archiver_alarm = failing
        if not failing:
            return [Notice(True, "WAL archiving healthy again", "The archiver is keeping up again.")]
        return [Notice(False, "WAL archiving failing", (
            f"pg_stat_archiver.failed_count = {sample.failed_count}, last failure "
            f"{sample.last_failed_time}. WAL is piling up on the database disk and the "
            "point-in-time window has stopped growing. Check `docker compose logs db`."))]

    def _disk(self, used_pct: float) -> list[Notice]:
        over = used_pct > DISK_ALARM_PCT
        if over == self.disk_alarm:
            return []
        self.disk_alarm = over
        if not over:
            return [Notice(True, f"backups disk back to {used_pct:.0f}%",
                           "Disk usage is below the alarm threshold again.")]
        return [Notice(False, f"backups disk {used_pct:.0f}% full (alarm above {DISK_ALARM_PCT:.0f}%)", (
            f"The VM disk holding data/ and backups/ is {used_pct:.1f}% used. pgBackRest, "
            "restic and pg_dump all write there."))]
```

- [ ] **Step 4: Add the embed builder to `swingbot/commands/scanning/notices.py`** (after `health_recovered_embed`):

```python
def pitr_notice_embed(notice):
    """v116: a PITR alarm or its recovery, in the existing HEALTH kinds."""
    kind = Kind.HEALTH_RECOVERED if notice.recovered else Kind.HEALTH_ALERT
    return system_embed(kind, notice.detail, notice.description)
```

- [ ] **Step 5: Add the loop and move `on_ready`'s loop starts into a helper in `loops.py`**

`on_ready` is already at complexity 15; adding a sixteenth branch is forbidden, so the starts move into a table (behaviour unchanged, same order). Add `from swingbot.core.infra import pitr_watch` to the imports, then after the `market_data_refresh` loop definitions:

```python
_PITR_WATCH = pitr_watch.PitrWatch()


@tasks.loop(minutes=15)
async def pitr_watch_loop():
    """v116: WAL-archiver and backups-disk alarms, once per episode, to ops."""
    try:
        sample = await asyncio.to_thread(pitr_watch.read_archiver)
        due = _PITR_WATCH.tick(sample, pitr_watch.disk_used_pct(config.DATA_DIR))
    except Exception:
        log.exception("pitr watch tick failed")
        return
    channel = _ops_channel()
    if channel is None:
        return
    for notice in due:
        await notices.send_guarded(channel, notices.pitr_notice_embed(notice), what="PITR alarm")


def _always_on_loops() -> tuple:
    """Loops on_ready starts unconditionally, in start order."""
    return (session_scan, heartbeat, config_watcher, trade_monitor, daily_recap,
            weekend_deep_scan_task, weekly_earnings_refresh, pitr_watch_loop)


def _start_background_loops() -> None:
    for loop in _always_on_loops():
        if not loop.is_running():
            loop.start()
    if config.MARKET_DATA_AUTO_REFRESH and not market_data_refresh.is_running():
        market_data_refresh.start()
```

In `on_ready`, replace the sixteen lines from `if not session_scan.is_running():` through `market_data_refresh.start()` with:

```python
    _start_background_loops()
```

- [ ] **Step 6: Run the tests, and the existing loop tests**

Run: `python scripts/dev/testrun.py file tests/infra/test_pitr_watch.py tests/commands/test_pitr_watch_loop.py tests/scanning/test_heartbeat_outcome.py tests/commands/test_scanning_package.py tests/commands/test_system_notices.py`
Expected: PASS (the `read_archiver` DB test skips without `db-test`).

- [ ] **Step 7: Complexity and commit**

Run: `python -m radon cc -s swingbot/commands/scanning/loops.py | grep -E "on_ready|pitr_watch_loop|_start_background_loops"` — `on_ready` below 15 now, the two new functions A.

```bash
git add swingbot/core/infra/pitr_watch.py swingbot/commands/scanning/notices.py swingbot/commands/scanning/loops.py tests/infra/test_pitr_watch.py tests/commands/test_pitr_watch_loop.py
git commit -m "feat(v116): alarm the ops channel on WAL-archiver failures and backups disk above 80%

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-08: PITR drill script and its scratch Compose project

**Files:**
- Create: `deploy/db/docker-compose.drill.yml`
- Create: `scripts/ops/pitr_drill.sh`
- Create: `tests/scripts/test_pitr_drill_shape.py`

**Interfaces:**
- Consumes: the db image (V116-01), `env_set.py --get` (V116-03).
- Produces: `scripts/ops/pitr_drill.sh` (re-runnable on the VM), appending to `logs/pitr_drill.log` and ending with `VERDICT <date> target=<ts> PASS|FAIL`. V116-10 and V116-33 run it; V116-33 reads the newest VERDICT.

- [ ] **Step 1: Write the failing test**

```python
"""The PITR drill (spec § Proof). It runs only on the VM; this pins what
keeps it from harming production and what makes it a real proof."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
REPO = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = REPO / "deploy" / "db" / "docker-compose.drill.yml"
SCRIPT = REPO / "scripts" / "ops" / "pitr_drill.sh"


@pytest.fixture(scope="module")
def drill():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_scratch_project_never_archives_into_production(drill):
    db = drill["services"]["db"]
    assert "archive_mode=off" in db["command"]
    for service in drill["services"].values():
        assert "/opt/swing-bot/backups/pitr:/var/lib/pgbackrest:ro" in service["volumes"]
        assert not any(v.startswith("pgdata:") for v in service["volumes"])


def test_scratch_project_has_its_own_name_port_and_volume(drill):
    assert drill["name"] == "swingbot-drill"
    assert drill["services"]["db"]["ports"] == ["127.0.0.1:55433:5432"]
    assert "drill_pgdata" in drill["volumes"]


def test_the_restore_targets_a_time_and_promotes(drill):
    command = " ".join(drill["services"]["restore"]["command"])
    assert "--type=time" in command and "--target-action=promote" in command


def test_the_drill_brackets_the_target_with_two_marks_and_checks_both():
    src = SCRIPT.read_text(encoding="utf-8")
    before, target, after = (src.index("-before')"), src.index("TARGET=\"$(psql_prod"),
                             src.index("-after')"))
    assert before < target < after
    assert "pg_switch_wal()" in src
    assert 'AFTER" = "0"' in src and 'BEFORE" = "1"' in src
    assert "VERDICT" in src and "logs/pitr_drill.log" in src
    assert "down -v" in src
    assert b"\r" not in SCRIPT.read_bytes()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_pitr_drill_shape.py`
Expected: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Create `deploy/db/docker-compose.drill.yml`**

```yaml
# Scratch Postgres for the v116 PITR drill (scripts/ops/pitr_drill.sh).
# Its own project, volume and port, and archive_mode OFF: a restored cluster
# must never push its new timeline into production's pgBackRest repo, which
# is mounted read-only here for the same reason.
name: swingbot-drill
services:
  restore:
    image: ${SWING_BOT_DB_IMAGE:?set SWING_BOT_DB_IMAGE to the production db image}
    profiles: ["restore"]
    user: postgres
    entrypoint: ["pgbackrest"]
    command: ["--stanza=swingbot", "--type=time", "--target=${DRILL_TARGET:?set DRILL_TARGET}",
              "--target-action=promote", "restore"]
    volumes:
      - drill_pgdata:/var/lib/postgresql
      - /opt/swing-bot/backups/pitr:/var/lib/pgbackrest:ro
  db:
    image: ${SWING_BOT_DB_IMAGE:?set SWING_BOT_DB_IMAGE to the production db image}
    command: ["postgres", "-c", "archive_mode=off"]
    environment:
      POSTGRES_USER: swingbot
      POSTGRES_DB: swingbot
      POSTGRES_PASSWORD: drill-only
    ports:
      - "127.0.0.1:55433:5432"
    volumes:
      - drill_pgdata:/var/lib/postgresql
      - /opt/swing-bot/backups/pitr:/var/lib/pgbackrest:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U swingbot -d swingbot"]
      interval: 5s
      timeout: 3s
      retries: 60
volumes:
  drill_pgdata:
```

- [ ] **Step 4: Create `scripts/ops/pitr_drill.sh`**

```bash
#!/usr/bin/env bash
# PITR drill (v116 Phase 0): prove a restore lands on an exact second.
#
# Writes one mark before and one after a target second into a throwaway
# `pitr_drill` schema in production (outside schema.py; nothing reads it),
# restores that second into the scratch project deploy/db/docker-compose.drill.yml,
# and checks: the "before" mark is there, the "after" mark is not, and a known
# trade record and the whole signal_state table hash to what production held at
# the target. Appends to logs/pitr_drill.log; last line is the VERDICT.
# Runs ON the VM as root; re-runnable (V116-33 repeats it within 7 days of Phase 4).
set -euo pipefail
cd /opt/swing-bot
LOG=logs/pitr_drill.log
DRILL="docker compose -p swingbot-drill -f deploy/db/docker-compose.drill.yml"
SWING_BOT_DB_IMAGE="$(python3 scripts/ops/env_set.py --get SWING_BOT_DB_IMAGE)"
export SWING_BOT_DB_IMAGE
psql_prod() { docker compose exec -T db psql -U swingbot -d swingbot -tA -v ON_ERROR_STOP=1 -c "$1" </dev/null; }
psql_drill() { $DRILL exec -T db psql -U swingbot -d swingbot -tA -v ON_ERROR_STOP=1 -c "$1" </dev/null; }
TRADE_SQL="SELECT coalesce(md5(doc::text || status), 'none') FROM trades ORDER BY trade_id LIMIT 1"
STATE_SQL="SELECT md5(coalesce(string_agg(key || doc::text, ',' ORDER BY key), '')) FROM signal_state"

{
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) PITR drill (db image $SWING_BOT_DB_IMAGE) ==="
psql_prod "CREATE SCHEMA IF NOT EXISTS pitr_drill"
psql_prod "CREATE TABLE IF NOT EXISTS pitr_drill.marks (id bigserial PRIMARY KEY, note text NOT NULL, at timestamptz NOT NULL DEFAULT clock_timestamp())"
RUN="drill-$(date -u +%Y%m%dT%H%M%SZ)"
psql_prod "INSERT INTO pitr_drill.marks (note) VALUES ('${RUN}-before')"
sleep 2
TARGET="$(psql_prod "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') || '+00'")"
TRADE_AT="$(psql_prod "$TRADE_SQL")"
STATE_AT="$(psql_prod "$STATE_SQL")"
sleep 2
psql_prod "INSERT INTO pitr_drill.marks (note) VALUES ('${RUN}-after')"
psql_prod "SELECT pg_switch_wal()" >/dev/null
for _ in $(seq 1 60); do
  [ "$(psql_prod "SELECT last_archived_time > now() - interval '2 minutes' FROM pg_stat_archiver")" = "t" ] && break
  sleep 5
done
echo "target=$TARGET trade_md5=$TRADE_AT state_md5=$STATE_AT"

$DRILL --profile restore down -v --remove-orphans >/dev/null 2>&1 || true
$DRILL --profile restore run --rm --entrypoint sh restore \
  -c 'mkdir -p /var/lib/postgresql/18/docker && chmod 700 /var/lib/postgresql/18/docker'
DRILL_TARGET="$TARGET" $DRILL --profile restore run --rm restore
$DRILL up -d --wait db
for _ in $(seq 1 60); do
  [ "$(psql_drill "SELECT NOT pg_is_in_recovery()")" = "t" ] && break
  sleep 5
done
BEFORE="$(psql_drill "SELECT count(*) FROM pitr_drill.marks WHERE note = '${RUN}-before'")"
AFTER="$(psql_drill "SELECT count(*) FROM pitr_drill.marks WHERE note = '${RUN}-after'")"
TRADE_R="$(psql_drill "$TRADE_SQL")"
STATE_R="$(psql_drill "$STATE_SQL")"
echo "restored: before_mark=$BEFORE after_mark=$AFTER trade_md5=$TRADE_R state_md5=$STATE_R"
ok=1
[ "$BEFORE" = "1" ] || ok=0
[ "$AFTER" = "0" ] || ok=0
[ "$TRADE_R" = "$TRADE_AT" ] || ok=0
[ "$STATE_R" = "$STATE_AT" ] || ok=0
$DRILL --profile restore down -v --remove-orphans
psql_prod "DELETE FROM pitr_drill.marks WHERE at < now() - interval '30 days'" >/dev/null
if [ "$ok" = 1 ]; then
  echo "VERDICT $(date -u +%F) target=$TARGET PASS"
else
  echo "VERDICT $(date -u +%F) target=$TARGET FAIL"
fi
} 2>&1 | tee -a "$LOG"
```

- [ ] **Step 5: Run the test and syntax checks**

Run: `python scripts/dev/testrun.py file tests/scripts/test_pitr_drill_shape.py` — PASS.
Run: `bash -n scripts/ops/pitr_drill.sh && SWING_BOT_DB_IMAGE=x DRILL_TARGET=y docker compose -f deploy/db/docker-compose.drill.yml --profile restore config --quiet` — exit 0.

- [ ] **Step 6: Commit**

```bash
git add --chmod=+x scripts/ops/pitr_drill.sh
git add deploy/db/docker-compose.drill.yml tests/scripts/test_pitr_drill_shape.py
git commit -m "feat(v116): PITR drill -- restore an exact second into a scratch compose project

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-09: Ship Phase 0 and switch on archiving — TOUCHES PRODUCTION

**Files:**
- Modify: `docs/deploy/DB_RESTORE.md` (new `## Point-in-time recovery (v116)` section: what was run, when)

**Interfaces:**
- Consumes: every Phase 0 task, committed on the branch.
- Produces: production running the pgBackRest image with `archive_mode=on`, stanza `swingbot` created, a first full backup, a restic repo with a first snapshot, the three crons installed, `backups/deploys.jsonl` with its first line, `backups/env/` with versions. V116-10 needs all of it.

Use the `mirror-prod` and `worktree-lifecycle` skills before starting. Do this outside the session window.

- [ ] **Step 1: Gate the branch**

From the worktree: `python scripts/dev/testrun.py fast` — expect `0 failed`. `python -m radon cc -s -n C swingbot/core/infra swingbot/commands/scanning/loops.py scripts/ops/*.py scripts/db/parity_report.py` — nothing new at C or above (the three legacy `loops.py` functions listed in the index may still print; none may be higher than listed). If Phase 1 tasks are also on the branch, every started one must be complete.

- [ ] **Step 2: Merge to `main` and let CI deploy**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot log -1 --oneline
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-09-30-v116-postgres-cutover-pitr -m "merge(v116): Phase 0 -- point-in-time rollback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
gh run watch --exit-status
```

Expected: `db-image` publishes `ghcr.io/<owner>/<repo>-db:pgcfg-<12>`, `deploy` green. The db container is recreated on the new image with archiving still off (the VM `.env` has no `PG_ARCHIVE_MODE` yet).

- [ ] **Step 3: Verify the deploy record and the pins**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && tail -1 backups/deploys.jsonl && python3 scripts/ops/env_set.py --get SWING_BOT_DB_IMAGE && ls backups/env && docker compose exec -T db pgbackrest version && docker compose exec -T db id postgres"
```

Expected: one JSON line whose `db_image` equals the pin; at least one `.env` version; `pgBackRest 2.…`; `uid=70(postgres)`. If a previous stage of the plan merged Phase 1 too, also run `docker compose exec -T bot alembic upgrade head` and confirm `alembic current` shows the head.

- [ ] **Step 4: Host prerequisites and directories**

```bash
bash scripts/ops/ssh-hetzner.sh "apt-get install -y restic python3 && restic version && python3 --version"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && mkdir -p backups/pitr backups/env backups/restic && chown 70:70 backups/pitr && chmod 700 backups/env backups/restic && ls -ld backups/*"
```

- [ ] **Step 5: Set the two keys in place, switch archiving on**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py RESTIC_PASSWORD \$(openssl rand -hex 32) && python3 scripts/ops/env_set.py PG_ARCHIVE_MODE on"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose up -d --no-build --wait db bot admin && docker compose exec -T db psql -U swingbot -d swingbot -tAc 'show archive_mode; show archive_timeout; show archive_command'"
```

Expected: `on`, `5min`, `pgbackrest --stanza=swingbot archive-push %p`. (Archiving fails until Step 6 creates the stanza; do Step 6 immediately.)

- [ ] **Step 6: Create the stanza, check it, take the first full backup**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot stanza-create && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot check && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=full backup && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot info"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -tAc 'select archived_count, failed_count, last_archived_time from pg_stat_archiver'"
```

Expected: `check` ends `completed successfully`; `info` lists one `full backup`; `archived_count` > 0. A non-zero `failed_count` from the minutes before the stanza existed is expected once — the alarm's "stuck" test uses the times, not the count.

- [ ] **Step 7: restic repo and first snapshot; crons**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && RESTIC_PASSWORD=\$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD) RESTIC_REPOSITORY=/opt/swing-bot/backups/restic restic init && scripts/ops/restic_hourly.sh"
bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_pitr_crons.sh
```

Expected: `created restic repository`, a `snapshot … saved`, and the crontab listing the three v116 lines plus the existing `backup_db.sh` line.

- [ ] **Step 8: The alarm loop is live**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c \"from swingbot.core.infra import pitr_watch as p; print(p.read_archiver(), p.disk_used_pct('/app/data'))\""
```

Expected: a sample with `last_archived_time` set, and a percentage under 80. If above 80, stop and free disk before continuing.

- [ ] **Step 9: Mirror what was run into `docs/deploy/DB_RESTORE.md`, commit on `main`**

Append a `## Point-in-time recovery (v116)` section listing: the date; the db image tag; the stanza name; the first full backup's label from `pgbackrest info`; the restic repo path and first snapshot id; the three cron lines; and "`.env` keys set in place with `env_set.py`: `PG_ARCHIVE_MODE=on`, `RESTIC_PASSWORD` (value only on the VM)". Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/deploy/DB_RESTORE.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v116): record the production PITR setup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```

Merge `main` back into the worktree branch (`git -C .claude/worktrees/2026-09-30-v116-postgres-cutover-pitr merge origin/main`) so later tasks see the doc.

---

### Task V116-10: Drill — restore a past second into a scratch stack — TOUCHES PRODUCTION

**Files:**
- Modify: `docs/deploy/DB_RESTORE.md` (append `### Drill <date>` under the v116 section)

**Interfaces:**
- Consumes: V116-08's script on the VM (deployed by V116-09), the stanza and first full backup (V116-09).
- Produces: a `VERDICT … PASS` line in `/opt/swing-bot/logs/pitr_drill.log` and its record in `DB_RESTORE.md`. **No Phase 3 flip may start until this passes** (V116-27 checks it).

- [ ] **Step 1: Wait for enough WAL**

At least one hour after V116-09 Step 6 (so the target is inside archived WAL after a base backup). Confirm: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot info"` shows the full backup and a WAL range.

- [ ] **Step 2: Run the drill**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && scripts/ops/pitr_drill.sh"
```

Expected, last lines:

```
target=2026-…+00 trade_md5=<hash> state_md5=<hash>
restored: before_mark=1 after_mark=0 trade_md5=<same> state_md5=<same>
VERDICT 2026-… target=2026-…+00 PASS
```

- [ ] **Step 3: If it FAILs**

Do not flip anything. Read the whole block in `logs/pitr_drill.log`. `after_mark=1` means the restore overshot the target (check the `--target` string and time zone). `before_mark=0` means WAL for the target was not archived (check `pg_stat_archiver`, the wait loop). A hash mismatch with correct marks means the comparison queries differ between the two sides. Fix the script on the branch, ship it (repeat V116-09 Steps 1–2 only), and re-run. Record each failed attempt too.

- [ ] **Step 4: Confirm the scratch stack is gone and production untouched**

```bash
bash scripts/ops/ssh-hetzner.sh "docker ps -a --format '{{.Names}}' | grep -c swingbot-drill; docker volume ls | grep -c drill_pgdata; cd /opt/swing-bot && docker compose ps"
```

Expected: `0`, `0`, and `bot`, `admin`, `db` healthy.

- [ ] **Step 5: Record the drill and commit on `main`**

Append to `docs/deploy/DB_RESTORE.md` under the v116 section:

```markdown
### Drill <YYYY-MM-DD> (v116 V116-10)

`scripts/ops/pitr_drill.sh` restored `<target>` into the `swingbot-drill`
scratch project (127.0.0.1:55433, volume `drill_pgdata`, `archive_mode=off`,
repo mounted read-only).

| check | at target (production) | restored |
|---|---|---|
| mark written 2 s before | present | <before_mark> |
| mark written 2 s after | present in production | <after_mark> |
| first trade record md5 | <trade_md5> | <trade_md5> |
| signal_state md5 | <state_md5> | <state_md5> |

VERDICT: <PASS|FAIL>. Scratch project and volume removed afterwards.
```

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/deploy/DB_RESTORE.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v116): PITR drill <date> -- <PASS|FAIL>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```
