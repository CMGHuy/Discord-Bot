# v146 Expectancy attribution: Implementation Plan, part 4 -- runs and results

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V146-14:" -A 400 docs/superpowers/plans/2026-10-09-v146-expectancy-attribution_4-runs-results.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`](../specs/2026-10-09-v146-expectancy-attribution-design.md)
**Index:** [`2026-10-09-v146-expectancy-attribution_0-index.md`](2026-10-09-v146-expectancy-attribution_0-index.md) -- Global Constraints, Handoff, Parallelisation and the task ledger live there and bind every task below.

Tasks V146-13 .. V146-15: the one TRAIN confluence replay, the one verdict run (live on a local scratch copy of the production `trades` rows, Handoff #8) with its results document, and the single full-suite run.

All three tasks run in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution` (below: `$WT`). Commands use absolute paths or `git -C`; never `cd` in Bash. The main tree is `E:/Documents/Private/Projects/Discord-Bot` (below: `$MAIN`).

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
MAIN=E:/Documents/Private/Projects/Discord-Bot
```

# Phase 4 -- runs and results

### Task V146-13: TRAIN confluence replay run

**Model:** sonnet — runs one pre-specified command through `backtest-runner` and checks its output file; no code is written.

**Cross-plan (audit 2026-10-10):** v158 may add an `--instrument` flag to `run_backtest_range.py`. Before Step 3, run `python "$WT/scripts/backtest/run_backtest_range.py" --help`; if it lists `--instrument`, append `--instrument v1` to the Step 3 command (the only permitted change to it) and pass the same line to the runner. The Step 5 manifest records which: `"instrument": "v1"` when the flag was passed, `"instrument": null` when `--help` did not list it.

**Files:**
- Modify: `.gitignore` (one line, `data/reports/`, only if Step 1 finds it missing: `data/` is not ignored wholesale, only named files under it, and on 2026-10-10 `git check-ignore data/reports/x.json` matched nothing).
- Writes (gitignored, never committed): `data/reports/v146-train-scenarios.jsonl` in the worktree, its log `logs/v146/train-replay.log`, and `logs/v146/train-manifest.json`.

**Interfaces:**
- Consumes: `python scripts/backtest/run_backtest_range.py --train --scenarios --exit-model v2 --scale-out --trades-jsonl PATH` (V146-8: `run_scenario_mode(..., trades_jsonl=...)`, one row per closed `ExitResult`, progress file `<PATH>.progress` deleted on completion); row keys from V146-7 `scenario_trade_row`: `ticker, horizon_key, signal_date, direction, entry, stop_loss, take_profit, risk_reward_ratio, outcome, runner_outcome, r_total, entry_price, legs, entry_context, confluence_count, confidence_score, confidence_level, confidence_points, confidence_unevaluated`.
- Produces: `$WT/data/reports/v146-train-scenarios.jsonl` (the TRAIN population V146-14 reads) and `$WT/logs/v146/train-manifest.json` = `{"path", "rows", "sha256", "by_horizon": {hk: rows}, "signal_date_min", "signal_date_max", "tickers_loaded", "tickers_total", "watchlist_sha256", "tickers", "run_started", "run_finished"}`.

Skills: load `backtest-gate` before Step 3. This is the one TRAIN run of the plan: it is never re-run to get a different number. VALIDATION is never read: the flag is `--train` and nothing else selects the window.

- [ ] **Step 1: Preconditions -- every code task is in, nothing else is running**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
git -C "$WT" log --oneline main..HEAD
git -C "$WT" status --short
git -C "$WT" check-ignore -v data/reports/v146-train-scenarios.jsonl logs/v146/train-replay.log
python -m radon cc -s -n C "$WT/swingbot/core/backtesting/backtest_scenarios.py" "$WT/swingbot/core/backtesting/scenario_rows.py"
```

Expected: commits for V146-1 .. V146-12 (V146-7 and V146-8 are the ones this task needs), a clean status, `logs/v146/train-replay.log` reported as ignored by `logs/`, and radon listing only the legacy `_aggregate` (C18) and nothing new.

If `check-ignore` prints no rule for `data/reports/v146-train-scenarios.jsonl` (the expected case unless an earlier task added one), make `data/reports/` ignored -- both this file and the study's `data/reports/expectancy-attribution.json` are run output, never committed:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
git -C "$WT" check-ignore -q data/reports/v146-train-scenarios.jsonl || {
  printf '\n# v146 expectancy attribution: run output (TRAIN rows, latest report)\ndata/reports/\n' >> "$WT/.gitignore"
  git -C "$WT" add .gitignore
  git -C "$WT" commit -m "chore(v146): ignore data/reports/ run output"
}
git -C "$WT" check-ignore -v data/reports/v146-train-scenarios.jsonl data/reports/expectancy-attribution.json
```

Expected: both paths reported as ignored by the `data/reports/` line. Never run anything below while either path is unignored: the output would land in the repo.

Then check no heavy run is live (concurrent sessions share this machine; two runs slow each other and have been killed mid-run before):

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300 | Select-Object Id, StartTime, CPU
```

Expected: no rows. If a heavy run is live, do not launch; report the conflict to the controller and stop.

- [ ] **Step 2: Preflight -- the universe and the caches the run will actually read**

Three worktree traps, each checked, none assumed:

1. `data/backtest_cache/` is gitignored, so the worktree has none. Every command below sets `BACKTEST_CACHE_DIR=$MAIN/data/backtest_cache`.
2. The universe is the watchlist table in Postgres, read through the worktree's `.env` (`scripts/data/fetch_backtest_data.load_watchlist`). A worktree without `.env` has no `DATABASE_URL`. If `$WT/.env` is missing, copy the main tree's (it is gitignored; `git check-ignore` confirms it before the copy). Never commit it.
3. A worktree watchlist has been a 3-ticker fixture before (v103 nearly closed cells on `universe_n 3`). The count is checked against the cache below.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
MAIN=E:/Documents/Private/Projects/Discord-Bot
test -f "$WT/.env" || { git -C "$WT" check-ignore -q .env && cp "$MAIN/.env" "$WT/.env"; }
mkdir -p "$WT/logs/v146" "$WT/data/reports"
ls "$MAIN/data/backtest_cache"/*.csv | wc -l
BACKTEST_CACHE_DIR="$MAIN/data/backtest_cache" python - "$WT" <<'PY'
import hashlib, json, sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[1] + "/scripts/data")
from fetch_backtest_data import load_watchlist, cache_path
tickers = sorted(load_watchlist())
missing = [t for t in tickers if not cache_path(t).exists()]
digest = hashlib.sha256("\n".join(tickers).encode()).hexdigest()
print(json.dumps({"watchlist_n": len(tickers), "missing_cache": missing,
                  "watchlist_sha256": digest, "tickers": tickers}))
PY
```

Expected: the cache holds about 75 CSVs; `watchlist_n` is at least 70; `missing_cache` lists at most a handful of names (each is skipped by the run and recorded). **If `watchlist_n` is below 70, stop and return `BLOCKED: worktree watchlist has <n> tickers` to the controller** -- do not edit the watchlist, do not pass `--universe`, do not run on a shrunken universe. Keep the printed JSON: Step 5 copies `watchlist_sha256` and the ticker list into the manifest.

- [ ] **Step 3: Launch the replay once, through `backtest-runner`, in the background**

Dispatch the `backtest-runner` agent with the worktree path and exactly this command (it backgrounds it and polls the log; nothing streams into the controller's context):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
MAIN=E:/Documents/Private/Projects/Discord-Bot
BACKTEST_CACHE_DIR="$MAIN/data/backtest_cache" PYTHONUNBUFFERED=1 \
  python "$WT/scripts/backtest/run_backtest_range.py" \
    --train --scenarios --exit-model v2 --scale-out \
    --trades-jsonl "$WT/data/reports/v146-train-scenarios.jsonl" \
  > "$WT/logs/v146/train-replay.log" 2>&1
```

Brief for the runner, verbatim:

> Run the command once, in the background, logging to `logs/v146/train-replay.log`. Before launching, record `date -u +%Y-%m-%dT%H:%M:%SZ` as run_started. It replays the confluence scan on every cached watchlist ticker over the legacy horizons; expect hours. Poll `Get-Content -Tail 5 <WT>/logs/v146/train-replay.log` and `Get-Content <WT>/data/reports/v146-train-scenarios.jsonl.progress` (a percent figure; it is deleted on completion) at 10-minute intervals. Do not change any argument, do not pass `--validation`, `--from`, `--to` or `--universe`, and do not restart a finished run to "check" a number. If the process dies, report the last 40 log lines and stop; do not relaunch. On exit, record run_finished and return: the exit code, the `loaded X/Y cached tickers` line, the excluded-ticker blocks, the full printed table (every `confluence/<horizon>` row and the pooled row), and whether the `.progress` file is gone.

Expected: exit code 0; the table printed; `data/reports/v146-train-scenarios.jsonl` exists; `data/reports/v146-train-scenarios.jsonl.progress` does not.

- [ ] **Step 4: Check the rows file against the printed table and the window**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
python - "$WT/data/reports/v146-train-scenarios.jsonl" <<'PY'
import collections, hashlib, json, sys
path = sys.argv[1]
KEYS = {"ticker", "horizon_key", "signal_date", "direction", "entry", "stop_loss",
        "take_profit", "risk_reward_ratio", "outcome", "runner_outcome", "r_total",
        "entry_price", "legs", "entry_context", "confluence_count", "confidence_score",
        "confidence_level", "confidence_points", "confidence_unevaluated"}
raw = open(path, "rb").read()
rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
missing = collections.Counter(k for r in rows for k in KEYS - r.keys())
dates = sorted(r["signal_date"] for r in rows)
ctx = [r.get("entry_context") or {} for r in rows]
summary = {
    "rows": len(rows),
    "sha256": hashlib.sha256(raw).hexdigest(),
    "by_horizon": dict(sorted(collections.Counter(r["horizon_key"] for r in rows).items())),
    "by_outcome": dict(collections.Counter(r["outcome"] for r in rows)),
    "signal_date_min": dates[0] if dates else None,
    "signal_date_max": dates[-1] if dates else None,
    "missing_keys": dict(missing),
    "score_null": sum(r.get("confidence_score") is None for r in rows),
    "points_empty": sum(not r.get("confidence_points") for r in rows),
    "confluence_min": min((r["confluence_count"] for r in rows), default=None),
    "not_triggered": sum(r["outcome"] == "not_triggered" for r in rows),
    "rs_pctile_present": sum(c.get("rs_pctile") is not None for c in ctx),
    "regime2_present": sum(c.get("regime2_state") is not None for c in ctx),
}
print(json.dumps(summary, indent=1))
PY
```

Expected, each one checked:

- `rows` > 0, and for every horizon `by_horizon[hk]` equals that horizon's `N + Scr + TO` in the printed table (the replay's closed set is every `ExitResult` whose outcome is not `not_triggered`; `N` counts only wins and losses). The pooled row's `N + Scr + TO` equals `rows`.
- `signal_date_min` >= `2020-01-01` and `signal_date_max` <= `2023-12-31`: nothing from VALIDATION.
- `missing_keys` is `{}`; `not_triggered` is 0; `score_null` is 0 (every TRAIN row is scored); `confluence_min` is at least the confluence gate's minimum.
- `rs_pctile_present` and `regime2_present` are most of `rows` (the as-of map V146-8 added is live). If either is 0, stop and report: the as-of map did not reach the replay, and the RS / regime buckets would be empty.
- `points_empty` is small relative to `rows` (a row is empty only when the scorer emitted no factor line).

A failed check is reported to the controller with the summary; the run is not repeated to make it pass.

- [ ] **Step 5: Write the manifest**

Fill every slot from Steps 2-4 (the zeros and empty strings are slots, not defaults to keep), then run:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
python - "$WT" <<'PY'
import json, sys
wt = sys.argv[1]
manifest = {
    "path": "data/reports/v146-train-scenarios.jsonl",
    "rows": 0,                 # Step 4 "rows"
    "sha256": "",              # Step 4 "sha256"
    "by_horizon": {},          # Step 4 "by_horizon"
    "signal_date_min": "",     # Step 4
    "signal_date_max": "",     # Step 4
    "tickers_loaded": 0,       # "loaded X/Y cached tickers": X
    "tickers_total": 0,        # Y
    "watchlist_sha256": "",    # Step 2
    "tickers": [],             # Step 2
    "run_started": "",         # Step 3
    "run_finished": "",        # Step 3
    "instrument": None,        # "v1" if Step 3 appended --instrument v1 (v158 merged), else None
}
assert manifest["rows"] > 0 and len(manifest["sha256"]) == 64, "fill the slots first"
with open(f"{wt}/logs/v146/train-manifest.json", "w", encoding="utf-8") as fh:
    fh.write(json.dumps(manifest, indent=1) + "\n")
print("manifest ok", manifest["rows"], manifest["sha256"][:12])
PY
git -C "$WT" status --short
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: `manifest ok <rows> <hash prefix>`; both statuses clean (every output is gitignored).

- [ ] **Step 6: Hand back**

Nothing else is committed (the only tracked change this task can make is the Step 1 `.gitignore` line, committed there). Report to the controller: rows, sha256, by-horizon counts, the pooled printed row, tickers loaded/total, excluded tickers, run wall time. These go into the V146-14 results document verbatim; this task states no ExpR conclusion of its own.


---

### Task V146-14: Verdict run and results document

**Model:** opus — the plan's one pre-registered verdict run, on a scratch copy of the production book, plus the closed-table row; a mistake here cannot be re-run away.

**Cross-plan (audit 2026-10-10):** the live readings use 2026 trades, which overlap the v2 instrument's sealed holdout (2026-01-01 onward). Step 10's Caveats carry a bullet saying so: any follow-on filter screened from these tables has seen that period. A second Caveats bullet names the instrument V146-13's manifest records (`train_m.get("instrument")`; `null` when no `--instrument` flag existed).

**Files:**
- Create: `docs/superpowers/results/<run-date>-v146-expectancy-attribution.md` (`<run-date>` is `verdict_of_record.date` from the generated JSON; Step 10 builds the name, nobody types it).
- Modify: `docs/claude/backtest-methodology.md` (one row at the top of the table under `### Closed pre-registrations — do not re-run these`).
- Modify: `tests/backtesting/test_preregistration_ledger_file.py:35-41` (`EXEMPT`, one entry).
- Writes (gitignored, never committed): `data/reports/expectancy-attribution.json`; under `logs/v146/`: `scratch_run.py`, `prod-fingerprint.sql`, `prod-export.sql`, `prod-fingerprint.txt`, `prod-exported-at.txt`, `scratch-fingerprint.txt`, `prod-closed-trades.copy`, `alembic-base.log`, `alembic-v146_001.log`, `verdict-run.log`, `live-manifest.json`, `closed-row.md`.

**Interfaces:**
- Consumes: `$WT/data/reports/v146-train-scenarios.jsonl` and `$WT/logs/v146/train-manifest.json` (V146-13: `path`, `rows`, `sha256`, `by_horizon`, `signal_date_min`, `signal_date_max`, `tickers_loaded`, `tickers_total`, `watchlist_sha256`, `run_started`, `run_finished`); CLI `python scripts/reports/expectancy_attribution.py --train-jsonl PATH [--seed N] [--no-write]`, `expectancy_attribution.population_passes(mono: dict) -> bool` (V146-11) and `expectancy_attribution.LIVE_FILLS_INCLUDE_FRICTIONS: bool` (V146-12 Step 1, Handoff 5); the report file `<DATA_DIR>/reports/expectancy-attribution.json` written by `write_latest` (V146-9) in the index's **Report shape**: `{generated_at, verdict, verdict_of_record: {verdict, date, n}, looks, seed, provenance, populations: {live, train}}`, each population `{window, n, monotonicity, factors, buckets, splits: {direction, horizon}, notes}`; revision `v146_001`, whose `upgrade()` logs `v146_001 <key>: parsed=<n> skipped=<n> unparsed=<n>` per key and `v146_001: stamped <n> trade row(s)` on logger `alembic.runtime.migration` (V146-3); `stats.WEEK_BOOTSTRAP_SEED` (existing, `swingbot/core/backtesting/instrument/stats.py:25`).
- Produces: the verdict of record (`verdict_of_record` in the JSON, carried forward unchanged by every later run), the results document, the closed-table row, `EXEMPT["v146"]`.

**The verdict is pre-registered (spec § The verdict). It is computed once, in Step 6, and never re-run to change the outcome.** No `--seed`, no changed argument, no second run "to check", no threshold read off these tables. A failed check after Step 6 is reported to the controller with the numbers as they are. Later runs (the v150 page, a growing book) are descriptive and never revise it; a new verdict needs a new spec.

**Production is read-only.** Two `SELECT`-only scripts inside `READ ONLY` transactions, both through `bash "$MAIN/scripts/ops/ssh-hetzner.sh"` (the wrapper is uncommitted and exists only in the main tree; never a raw `ssh`/`scp`). The SQL travels on stdin, so nothing is quoted or expanded on the way. Nothing is written, restarted or deployed there; `v146_001` reaches production only through the normal deploy after merge.

**Why a launcher instead of a bare `DATABASE_URL=...` prefix.** `swingbot/config.py:1379` loads `.env` with `load_dotenv(..., override=True)`: a `DATABASE_URL` exported in the shell is overwritten by the worktree's `.env`, which points at the dev database. The dev `trades` table is fixture data and must never produce a pooled figure (`docs/claude/working-conventions.md` § Investigating production). `logs/v146/scratch_run.py` (Step 2) sets `config.DATABASE_URL` after import, the same way `tests/db/conftest.py:160` does, and refuses to continue unless `SELECT current_database()` answers `v146_scratch`. Alembic and the study both run through it. `.env` is never edited.

Skills: invoke `pooled-numbers` before Step 6 (every figure below is re-derived from the copy of the live book, none quoted from a document or typed from memory).

- [ ] **Step 1: Preconditions — code in, TRAIN file intact, no verdict on disk yet**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
git -C "$WT" log --oneline main..HEAD | wc -l
git -C "$WT" status --short
git -C "$WT" grep -n "LIVE_FILLS_INCLUDE_FRICTIONS" -- swingbot/core/analytics/expectancy_attribution.py
git -C "$WT" grep -n "^revision\|^down_revision" -- swingbot/core/db/migrations/versions/v146_001_confidence_points.py
test -e "$WT/data/reports/expectancy-attribution.json" && echo "REPORT ALREADY EXISTS" || echo "no report yet"
python - "$WT" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / "logs/v146/train-manifest.json").read_text(encoding="utf-8"))
raw = (root / manifest["path"]).read_bytes()
rows = sum(1 for line in raw.decode("utf-8").splitlines() if line.strip())
digest = hashlib.sha256(raw).hexdigest()
print("rows", rows, "manifest", manifest["rows"])
print("sha256", digest, "manifest", manifest["sha256"])
assert rows == manifest["rows"] and digest == manifest["sha256"], "TRAIN file differs from the V146-13 hand-back"
print("train file ok")
PY
```

Expected: commits for V146-1 .. V146-12 present (V146-13 commits at most the `.gitignore` line); clean status; a `LIVE_FILLS_INCLUDE_FRICTIONS = True` or `= False` assignment (V146-12 Step 1 set it after verifying what live fills include; this task reads it, never changes it); `revision = "v146_001"`; `no report yet`; `train file ok` with both numbers equal to what V146-13 handed back.

- If the TRAIN file differs from the manifest: stop and report. Do not re-run the replay.
- If `REPORT ALREADY EXISTS`: stop and report to the controller. `write_latest` carries an existing `verdict_of_record` forward unchanged, so a file left by a smoke run on fixture data would become the verdict of record. Whether to delete it is the controller's decision, not this task's.

The TRAIN earnings buckets read `market_data/earnings/` relative to the code (`earnings_calendar.EARNINGS_CSV_DIR`), and `market_data/` is gitignored, so a worktree has none. Without it every TRAIN row buckets as `unknown`:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$WT" check-ignore -q market_data/earnings/AAPL.csv && echo ignored
test -d "$WT/market_data/earnings" || { mkdir -p "$WT/market_data" && cp -r "$MAIN/market_data/earnings" "$WT/market_data/earnings"; }
ls "$MAIN/market_data/earnings" | wc -l
ls "$WT/market_data/earnings" | wc -l
git -C "$WT" status --short
```

Expected: `ignored`; the two counts equal (76 files on 2026-10-10); status still clean. If `ignored` is not printed, do not copy; stop and report.

- [ ] **Step 2: Start the test Postgres, create the scratch database, write the launcher**

The Compose `db-test` service (`docker-compose.yml:83-104`, container `swing-db-test`, `127.0.0.1:55432`, user and password `swingbot`, tmpfs storage) is the server the test suite uses. The scratch database is a separate database on it, so the suite's `swingbot_test` is untouched. Never `docker compose down` it: other sessions may be mid-suite.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
MAIN=E:/Documents/Private/Projects/Discord-Bot
docker compose -f "$MAIN/docker-compose.yml" --profile test up -d db-test
docker exec swing-db-test pg_isready -U swingbot -d swingbot_test
docker exec swing-db-test psql -U swingbot -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS v146_scratch"
docker exec swing-db-test psql -U swingbot -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE v146_scratch"
mkdir -p "$WT/logs/v146"
cat > "$WT/logs/v146/scratch_run.py" <<'PY'
"""Run alembic or one script against the v146 scratch database, and nothing else.

usage: scratch_run.py <worktree> <url> alembic <alembic args...>
       scratch_run.py <worktree> <url> script <script path> <script args...>
"""
import os
import runpy
import sys

WT, URL, MODE, *REST = sys.argv[1:]
os.environ["DATABASE_URL"] = URL
os.chdir(WT)
sys.path.insert(0, WT)

from swingbot import config  # noqa: E402

# .env is loaded with override=True, so the environment variable alone loses.
config.DATABASE_URL = URL

import sqlalchemy as sa  # noqa: E402
from swingbot.core.db.engine import get_engine  # noqa: E402

with get_engine().connect() as conn:
    database = conn.execute(sa.text("SELECT current_database()")).scalar()
if database != "v146_scratch":
    sys.exit(f"REFUSING: connected to {database!r}, not v146_scratch")
print(f"scratch_run: database={database}", file=sys.stderr, flush=True)

if MODE == "alembic":
    from alembic.config import main
    main(argv=REST)
elif MODE == "script":
    sys.argv = REST
    runpy.run_path(REST[0], run_name="__main__")
else:
    sys.exit(f"unknown mode {MODE!r}")
PY
git -C "$WT" check-ignore -v logs/v146/scratch_run.py
```

Expected: the container reports `accepting connections` (give it a few seconds after `up` and repeat `pg_isready` if not); `DROP DATABASE` then `CREATE DATABASE`; `logs/v146/scratch_run.py` reported as ignored by `logs/`. A leftover `v146_scratch` from an aborted attempt is dropped here on purpose: it is scratch, and no verdict was computed from it (Step 1 proved no report exists).

- [ ] **Step 3: Export the closed production trades, read-only**

Closed means `status <> 'open'` (`swingbot/core/db/repositories/trades.py:9`, `OPEN_STATUS = "open"`; the repository's own closed filter at `:62`). Both ledgers are included: the ledger is a `doc` field, not a filter here.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
MAIN=E:/Documents/Private/Projects/Discord-Bot
cat > "$WT/logs/v146/prod-fingerprint.sql" <<'SQL'
BEGIN TRANSACTION READ ONLY;
SELECT 'alembic=' || version_num FROM alembic_version;
SELECT 'closed=' || count(*) FROM trades WHERE status <> 'open';
SELECT 'fingerprint=' || md5(string_agg(trade_id || md5(doc::text), '' ORDER BY trade_id)) FROM trades WHERE status <> 'open';
COMMIT;
SQL
cat > "$WT/logs/v146/prod-export.sql" <<'SQL'
BEGIN TRANSACTION READ ONLY;
COPY (SELECT trade_id, ticker, strategy, horizon, direction, status, opened_at, closed_at, entry, stop_loss, doc, updated_at FROM trades WHERE status <> 'open' ORDER BY id) TO STDOUT;
COMMIT;
SQL
PSQL="cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -q -At"
bash "$MAIN/scripts/ops/ssh-hetzner.sh" "$PSQL" < "$WT/logs/v146/prod-export.sql" > "$WT/logs/v146/prod-closed-trades.copy"
bash "$MAIN/scripts/ops/ssh-hetzner.sh" "$PSQL" < "$WT/logs/v146/prod-fingerprint.sql" > "$WT/logs/v146/prod-fingerprint.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$WT/logs/v146/prod-exported-at.txt"
cat "$WT/logs/v146/prod-fingerprint.txt"
wc -l < "$WT/logs/v146/prod-closed-trades.copy"
```

Expected: three lines, `alembic=v144_001`, `closed=<n>`, `fingerprint=<32 hex>`; the `wc -l` figure equals `<n>` (COPY text format writes one line per row; newlines inside `doc` are escaped). `<n>` is the live book's closed-trade count and is not known in advance: do not compare it with any figure from a document.

- If `closed` and `wc -l` differ by a trade, one closed between the two reads. Run both `ssh-hetzner.sh` lines again back to back (reading production again is not re-running the verdict) until they agree. Outside US market hours they agree first time.
- If `alembic=` is not `v144_001`: use whatever it prints in place of `v144_001` in Step 4, provided `git -C "$WT" grep -l "^revision = \"<that id>\"" -- swingbot/core/db/migrations/versions` finds it. If the worktree does not know that revision, stop and report.
- If the wrapper fails (key, WSL, network): stop and report the error text. Do not try another key path or a raw `ssh`.

- [ ] **Step 4: Build the scratch schema at production's revision, load the rows, prove the copy is exact**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:55432/v146_scratch
python "$WT/logs/v146/scratch_run.py" "$WT" "$URL" alembic upgrade v144_001 > "$WT/logs/v146/alembic-base.log" 2>&1; echo "exit $?"
head -n 1 "$WT/logs/v146/alembic-base.log"
tail -n 3 "$WT/logs/v146/alembic-base.log"
docker exec -i swing-db-test psql -U swingbot -d v146_scratch -v ON_ERROR_STOP=1 -q \
  -c "COPY trades (trade_id, ticker, strategy, horizon, direction, status, opened_at, closed_at, entry, stop_loss, doc, updated_at) FROM STDIN" \
  < "$WT/logs/v146/prod-closed-trades.copy"
docker exec -i swing-db-test psql -U swingbot -d v146_scratch -v ON_ERROR_STOP=1 -q -At \
  < "$WT/logs/v146/prod-fingerprint.sql" > "$WT/logs/v146/scratch-fingerprint.txt"
diff "$WT/logs/v146/prod-fingerprint.txt" "$WT/logs/v146/scratch-fingerprint.txt" && echo "copy exact"
```

Expected: `exit 0`; the log's first line is `scratch_run: database=v146_scratch` and its last migration line runs to `v144_001`; `diff` prints nothing and `copy exact` follows (same revision, same closed count, same per-row `doc` fingerprint on both sides).

If `diff` shows a difference, the copy is not the book: stop and report both files. Do not go on to Step 5 on a copy that does not match.

- [ ] **Step 5: Run `v146_001` on the real rows and record its counts**

This is the first run of the backfill on real breakdown text. Its counts go into the results document.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:55432/v146_scratch
python "$WT/logs/v146/scratch_run.py" "$WT" "$URL" alembic upgrade head > "$WT/logs/v146/alembic-v146_001.log" 2>&1; echo "exit $?"
grep -n "v146_001" "$WT/logs/v146/alembic-v146_001.log"
docker exec swing-db-test psql -U swingbot -d v146_scratch -q -At \
  -c "SELECT 'alembic=' || version_num FROM alembic_version" \
  -c "SELECT 'with_points=' || count(*) FROM trades WHERE doc ? 'confidence_points'" \
  -c "SELECT 'with_breakdown=' || count(*) FROM trades WHERE jsonb_typeof(doc->'confidence_breakdown') = 'object'"
python - "$WT" <<'PY'
import hashlib, json, pathlib, re, sys
logs = pathlib.Path(sys.argv[1]) / "logs/v146"
fingerprint = dict(line.split("=", 1) for line in (logs / "prod-fingerprint.txt").read_text().split())
text = (logs / "alembic-v146_001.log").read_text(encoding="utf-8", errors="replace")
keys = {key: {"parsed": int(p), "skipped": int(s), "unparsed": int(u)}
        for key, p, s, u in re.findall(r"v146_001 (.+?): parsed=(\d+) skipped=(\d+) unparsed=(\d+)", text)}
stamped = re.search(r"v146_001: stamped (\d+) trade row\(s\)", text)
assert keys and stamped, "the revision's count lines are missing from the log"
manifest = {
    "exported_at": (logs / "prod-exported-at.txt").read_text().strip(),
    "prod_alembic": fingerprint["alembic"],
    "closed_rows": int(fingerprint["closed"]),
    "fingerprint_md5": fingerprint["fingerprint"],
    "export_sha256": hashlib.sha256((logs / "prod-closed-trades.copy").read_bytes()).hexdigest(),
    "migration": {"stamped": int(stamped.group(1)), "keys": keys},
}
(logs / "live-manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
totals = {k: sum(v[k] for v in keys.values()) for k in ("parsed", "skipped", "unparsed")}
print("stamped", manifest["migration"]["stamped"], "of", manifest["closed_rows"], "totals", totals)
PY
```

Expected: `exit 0`; one `v146_001 <key>: parsed=… skipped=… unparsed=…` line per breakdown key and one `v146_001: stamped <n> trade row(s)`; `alembic=` the worktree's single head (`python -m alembic heads` run in `$WT`; another merged plan's revision may sit above `v146_001`), and the log contains the `v146_001` lines; `with_points` equals the stamped count and equals `with_breakdown` (every row whose `confidence_breakdown` is an object gets stamped); the manifest line printed.

`unparsed` lines are a finding, not a failure: the revision counts them and leaves them out of `points` by design. Do not edit the revision and re-run it here to make a key parse; report the unparsed keys and counts to the controller in the hand-back, and they appear in the results document. If the upgrade exits non-zero, stop and report the last 40 log lines; Step 8 still runs.

- [ ] **Step 6: The verdict run — once**

Invoke the `pooled-numbers` skill now. Then run the study, exactly as below, one time. It is the spec's command (`python scripts/reports/expectancy_attribution.py --train-jsonl data/reports/v146-train-scenarios.jsonl`) with the database pointed at the scratch copy by the launcher. It bootstraps 10,000 week-clustered resamples per look, so start it in the background (`run_in_background`) and wait for it to exit.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:55432/v146_scratch
PYTHONUNBUFFERED=1 python "$WT/logs/v146/scratch_run.py" "$WT" "$URL" script \
  "$WT/scripts/reports/expectancy_attribution.py" \
  --train-jsonl "$WT/data/reports/v146-train-scenarios.jsonl" \
  > "$WT/logs/v146/verdict-run.log" 2>&1; echo "exit $?" >> "$WT/logs/v146/verdict-run.log"
```

When it has exited:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
head -n 1 "$WT/logs/v146/verdict-run.log"
tail -n 25 "$WT/logs/v146/verdict-run.log"
ls -l "$WT/data/reports/expectancy-attribution.json"
```

Expected: first line `scratch_run: database=v146_scratch`; last line `exit 0`; the report file exists. No `--seed` (the default is the recorded `WEEK_BOOTSTRAP_SEED`), no `--no-write`.

If it exits non-zero **and no report file was written**, no verdict exists yet: stop, report the last 40 log lines to the controller, run Step 8, and wait. If a report file was written, the verdict of record is fixed, whatever it says: go on to Step 7.

- [ ] **Step 7: Check the report against its contract (read only; nothing here changes a number)**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
python - "$WT" <<'PY'
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
root = pathlib.Path(sys.argv[1])
from swingbot.core.backtesting.instrument.stats import WEEK_BOOTSTRAP_SEED
report = json.loads((root / "data/reports/expectancy-attribution.json").read_text(encoding="utf-8"))
train_m = json.loads((root / "logs/v146/train-manifest.json").read_text(encoding="utf-8"))
live_m = json.loads((root / "logs/v146/live-manifest.json").read_text(encoding="utf-8"))
live, train = report["populations"].get("live"), report["populations"].get("train")
vor = report["verdict_of_record"]
mono_n = sum((pop or {}).get("monotonicity", {}).get("n", 0) for pop in (live, train))
checks = {
    "top-level keys": set(report) >= {"generated_at", "verdict", "verdict_of_record", "looks", "seed", "provenance", "populations"},
    "verdict in the pre-registered enum": report["verdict"] in ("PREDICTIVE", "WEAK", "NOT PREDICTIVE"),
    "verdict_of_record.verdict == verdict": vor["verdict"] == report["verdict"],
    "verdict_of_record.n == live mono n + train mono n": vor["n"] == mono_n,
    "seed is the recorded default": report["seed"] == WEEK_BOOTSTRAP_SEED,
    "looks is a positive int": isinstance(report["looks"], int) and report["looks"] > 0,
    "both populations present": live is not None and train is not None,
}
for name, ok in checks.items():
    print("OK  " if ok else "FAIL", name)
print("verdict", report["verdict"], "| of record", vor, "| looks", report["looks"], "| seed", report["seed"])
for label, pop, source_n in (("live", live, live_m["closed_rows"]), ("train", train, train_m["rows"])):
    if pop is None:
        print(label, "population is null; source rows", source_n)
        continue
    print(label, "n", pop["n"], "of", source_n, "source rows | monotonicity", json.dumps(pop["monotonicity"], sort_keys=True))
    print(label, "groupings", sorted(pop["buckets"]), "| factors", len(pop["factors"]), "| notes", pop.get("notes"))
PY
```

Expected: seven `OK` lines. TRAIN `n` equals the manifest's `rows` (every TRAIN row is scored); live `n` is at most the exported closed count (the study drops rows with no R). The groupings cover the spec's list: confidence decile, confidence level, confluence count, `regime2_state`, RS quintile, direction, horizon, earnings bucket, earnings inside the hold.

A `FAIL`, a population that is `null`, a missing grouping or an `n` that does not reconcile is reported to the controller with this output. **Nothing is re-run to make it pass**; the controller decides what the finding means, and the results document states it.

- [ ] **Step 8: Drop the scratch database (run this even if an earlier step failed)**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
docker exec swing-db-test psql -U swingbot -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS v146_scratch"
docker exec swing-db-test psql -U swingbot -d postgres -q -At -c "SELECT count(*) FROM pg_database WHERE datname = 'v146_scratch'"
git -C "$WT" status --short
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: `DROP DATABASE`; `0`; both statuses clean (the export, the logs and the report are all gitignored). Leave `swing-db-test` running: V146-15's suite uses it. The export file stays under `logs/v146/` as the audit copy of what the verdict read.

- [ ] **Step 9: Write the failing test — `v146` in `EXEMPT`**

v146 is a read-only measurement with no budget and no ledger row, so it is exempt from the ledger the way v143 is (Handoff 11). In `$WT/tests/backtesting/test_preregistration_ledger_file.py`, add the `"v146"` entry to `EXEMPT`, after the `"v143"` line:

```python
#: Closed-table versions deliberately absent from the ledger (reason each).
EXEMPT = {
    "v124": "read-only diagnostic, four arms, no budget spent",
    "v127": "NO_ELIGIBLE_CELL at Stage 1, budget intact; verdict not in the ledger enum",
    "v143": "read-only diagnostic, nine features at three geometries, no budget spent",
    "v146": "read-only measurement, one pre-registered verdict on two populations, no budget spent",
    "v140": "ledgered as screen-<idea> (instrument screen-v1), not under a v140- prefix",
    "v72": "named only as the funnel pointer in a screen row's closing sentence",
}
```

Run: `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py` (with the worktree as the session root)
Expected: FAIL in `test_every_exempt_version_is_in_the_table_and_has_no_ledger_row`, `['v146'] == []`: the exemption has no closed-table row yet.

- [ ] **Step 10: Generate the results document and the closed-table row from the JSON**

No figure is typed. The script below reads `data/reports/expectancy-attribution.json`, the two manifests and the study module's `LIVE_FILLS_INCLUDE_FRICTIONS`, and writes the whole document plus the table row. Numbers print as stored (floats to four decimals, in the JSON's own units and key names). The layout follows `docs/superpowers/results/2026-10-09-v143-fvg-bullish-diagnostic.md` (title, `**Run:**`, `**Spec:**`, `**Verdict:**`, then tables) with the sections the spec's Study and Output sections require.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
python - "$WT" "$(git -C "$WT" rev-parse --short HEAD)" <<'PY'
import json, pathlib, sys

wt, head = sys.argv[1], sys.argv[2]
sys.path.insert(0, wt)
root = pathlib.Path(wt)
from swingbot.core.analytics import expectancy_attribution as study


def load(rel):
    return json.loads((root / rel).read_text(encoding="utf-8"))


report = load("data/reports/expectancy-attribution.json")
train_m = load("logs/v146/train-manifest.json")
live_m = load("logs/v146/live-manifest.json")
vor = report["verdict_of_record"]
pops = {"Live": report["populations"].get("live"), "TRAIN": report["populations"].get("train")}
MONO = ("n", "spearman_rho", "tercile_spread", "ci_low", "ci_high", "p", "inverted", "tercile_n", "rr_by_tercile")
BUCKET = ("label", "n", "win_rate", "exp_r", "exp_r_gross", "ci_low", "ci_high", "p", "q", "thin")
EXTRA = ("unevaluated_n", "rr")
FACTOR = ("key", "n", "n_pos", "n_zero", "delta", "ci_low", "ci_high", "p", "q")
CLOSES = ("Closes \"raise the confidence floor\" as a measured no; any bucket candidate stands on its own "
          "and needs its own Stage -2 screen.")
LICENCE = {
    "PREDICTIVE": "Licenses one Stage -2 screen for a confidence floor or confidence-weighted sizing; nothing ships from it directly.",
    "WEAK": CLOSES,
    "NOT PREDICTIVE": CLOSES,
}
FRICTIONS = {
    True: "Live fills already include frictions (`LIVE_FILLS_INCLUDE_FRICTIONS = True`): live R is `metrics.r_multiple` as stored.",
    False: ("Live fills are not friction-adjusted (`LIVE_FILLS_INCLUDE_FRICTIONS = False`): the study applies the same "
            "`apply_frictions` + `commission_r` model to live rows as to TRAIN rows."),
}[bool(study.LIVE_FILLS_INCLUDE_FRICTIONS)]


def cell(value):
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True).replace("|", "/")
    return str(value).replace("|", "/")


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def verdict_table():
    rows = [[label] + [pop["monotonicity"].get(k) for k in MONO] + [study.population_passes(pop["monotonicity"])]
            for label, pop in pops.items() if pop]
    return table(("population",) + MONO + ("clause passes",), rows)


def split_tables():
    out = []
    for kind in ("direction", "horizon"):
        rows = [[label, name] + [(mono or {}).get(k) for k in MONO]
                for label, pop in pops.items() if pop
                for name, mono in pop.get("splits", {}).get(kind, {}).items()]
        out += ["", f"### By {kind}", ""] + table(("population", kind) + MONO, rows)
    return out


def bucket_tables():
    names = []
    for pop in pops.values():
        names += [name for name in (pop or {}).get("buckets", {}) if name not in names]
    out = []
    for name in names:
        rows = [(label, b) for label, pop in pops.items() for b in (pop or {}).get("buckets", {}).get(name, [])]
        cols = BUCKET + tuple(k for k in EXTRA if any(k in b for _, b in rows))
        out += ["", f"### {name}", ""]
        out += table(("population",) + cols, [[label] + [b.get(k) for k in cols] for label, b in rows])
    return out


def factor_table():
    rows = [[label] + [f.get(k) for k in FACTOR] for label, pop in pops.items() for f in (pop or {}).get("factors", [])]
    return table(("population",) + FACTOR, rows)


def candidates():
    rows = []
    for label, pop in pops.items():
        for name, buckets in (pop or {}).get("buckets", {}).items():
            rows += [[label, f"bucket {name} = {b['label']}", b["n"], b.get("exp_r"), b["q"]]
                     for b in buckets if not b.get("thin") and b.get("q") is not None and b["q"] < 0.10]
        rows += [[label, f"factor {f['key']}", f["n"], f.get("delta"), f["q"]]
                 for f in (pop or {}).get("factors", []) if f.get("q") is not None and f["q"] < 0.10]
    if not rows:
        return ["None. No bucket and no factor has a BH q-value below 0.10 over all looks."]
    return table(("population", "look", "n", "ExpR or delta", "q"), rows)


def migration_table():
    keys = live_m["migration"]["keys"]
    return table(("breakdown key", "parsed", "skipped", "unparsed"),
                 [[k, v["parsed"], v["skipped"], v["unparsed"]] for k, v in sorted(keys.items())])


def phrase(label, pop):
    if not pop:
        return f"{label}: no rows"
    mono = pop["monotonicity"]
    if mono.get("tercile_spread") is None:
        return f"{label} n={mono['n']}, no tercile spread"
    inverted = ", inverted" if mono.get("inverted") else ""
    return (f"{label} n={mono['n']}, top-minus-bottom tercile {mono['tercile_spread']:+.3f}R, "
            f"95% CI [{cell(mono.get('ci_low'))}, {cell(mono.get('ci_high'))}]{inverted}")


def dumps(value):
    return json.dumps(value, sort_keys=True)


verdict = vor["verdict"]
name = f"{vor['date']}-v146-expectancy-attribution.md"
doc = [
    "# v146 Expectancy attribution: result", "",
    f"**Run:** {vor['date']}, live book (closed production trades, both ledgers, read from a local copy) and TRAIN confluence replay "
    f"{train_m['signal_date_min']}..{train_m['signal_date_max']} (signal date), side by side and never pooled. "
    "Read-only; VALIDATION never read.",
    "**Spec:** `docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`", "",
    f"**Verdict: {verdict}.** {LICENCE[verdict]}", "",
    f"Verdict of record: `{dumps(vor)}` (`n` is the live monotonicity n plus the TRAIN monotonicity n). "
    f"{report['looks']} looks in the BH family; bootstrap seed {report['seed']}. "
    "The verdict was pre-registered in the spec and computed once, in this run. "
    "Later runs are descriptive and never revise it; a new verdict needs a new spec.", "",
    "Rule, on the top-minus-bottom tercile ExpR and its 95% week-clustered bootstrap CI: PREDICTIVE needs a lower bound "
    "above 0 and a point estimate of at least +0.10R in both populations; WEAK is that in exactly one; NOT PREDICTIVE "
    "otherwise. A tercile with N < 30 fails its population's clause. A CI wholly below zero is reported as inverted "
    "inside NOT PREDICTIVE, not as a fourth verdict.", "",
    "All figures are as stored in `data/reports/expectancy-attribution.json` (floats to four decimals, the file's own "
    "key names and units). R is net of frictions; `exp_r_gross` is the gross figure beside it.", "",
    "## The verdict table: confidence score against R", "", *verdict_table(), "",
    "## Verdict table split by direction and horizon", *split_tables(), "",
    "## Buckets", "",
    "One row per bucket and population. `thin` buckets (N < 30) are shown and enter no verdict and no look.",
    *bucket_tables(), "",
    "## Per-factor ExpR delta", "",
    "ExpR where the factor scored, minus ExpR where it scored 0; rows where the factor was unevaluated are excluded. "
    "Live history before v146 carries points from the backfill below.", "", *factor_table(), "",
    "## Screen candidates (BH q < 0.10 over all looks)", "",
    "A row here has earned a Stage -2 screen of its own, never a filter.", "", *candidates(), "",
    "## Frictions", "",
    FRICTIONS + " TRAIN rows: the confluence replay's exit simulation applies no frictions, so the study re-applies them.", "",
    "## Backfill: `v146_001` on the copy of the production rows", "",
    f"Production was at `{live_m['prod_alembic']}`; {live_m['closed_rows']} closed rows were exported at "
    f"{live_m['exported_at']} and {live_m['migration']['stamped']} were stamped with `confidence_points`. "
    "An unparsed line is counted and left out of the points.", "", *migration_table(), "",
    "## Provenance", "",
    f"- Code: branch `2026-10-09-v146-expectancy-attribution` at `{head}`.",
    f"- Report: `data/reports/expectancy-attribution.json`, generated_at {report['generated_at']}; "
    f"provenance `{dumps(report['provenance'])}`.",
    f"- Live: scratch copy of the production `trades` table (closed rows only), export sha256 `{live_m['export_sha256']}`, "
    f"row fingerprint `{live_m['fingerprint_md5']}` equal on production and on the copy; the scratch database was dropped "
    "after the run. Production was never written.",
    f"- TRAIN: `{train_m['path']}`, {train_m['rows']} rows, sha256 `{train_m['sha256']}`, "
    f"{train_m['tickers_loaded']}/{train_m['tickers_total']} tickers, watchlist sha256 `{train_m['watchlist_sha256']}`, "
    f"run {train_m['run_started']}..{train_m['run_finished']}; by horizon `{dumps(train_m['by_horizon'])}`.",
    *[f"- {label} window `{dumps(pop.get('window'))}`, n {pop['n']}; notes `{dumps(pop.get('notes'))}`."
      for label, pop in pops.items() if pop],
    "- Earnings: the `market_data/earnings/` file set named in the report provenance above, on the v82 earnings "
    "calendar (`swingbot/core/market/earnings_calendar.py`).", "",
    "## Caveats", "",
    "- **The score is level-major.** The legacy scorer repositions the quality score inside the final level's band, so "
    "score order is level order first and quality order within a level. The deciles are close to \"level, then "
    "quality\". Stated, not corrected.",
    "- **The live book is range-restricted.** Only trades at or above the alert level were ever paper-traded, which "
    "attenuates any score-R slope live; the TRAIN replay is not level-gated. A weaker live slope is the expected shape, "
    "not by itself a contradiction. The per-level table is there so a live NOT PREDICTIVE is not misread as \"score "
    "useless\" when the alert gate already took the edge.",
    "- **The TRAIN score neutralises the expectancy adjustment** (`scenario_rows.TRAIN_NEUTRAL_EXPECTANCY`, frozen "
    "before the run): the replay has no track record, and the adjustment is not neutral without one. R:R is reported "
    "per tercile beside the spread.",
    "- **Earnings definitions differ and are never merged.** Live is a provider point-in-time estimate, `unknown` for "
    "every trade before v146 shipped. TRAIN uses actual report dates: `0-5` and `6-10` are mostly knowable at the "
    "signal, `11-20` partly, `>20` and `none` are ex-post. Report timing (before open / after close) is ex-post and can "
    "move a row across the `0-5` edge. Any earnings screen candidate needs a point-in-time re-check before its "
    "Stage -2 screen.",
    "- **Fill models differ.** The backtest and the live tracker do not model gap fills identically "
    "(`swingbot/core/backtesting/exit_sim.py:541-548`), so R is comparable in sign and order, not to the last hundredth.",
    f"- **Multiple comparisons.** {report['looks']} looks; a bucket or factor is a screen candidate only at BH q < 0.10 "
    "over all of them. No threshold is chosen from these tables.",
    "- **The live rows overlap v2's sealed holdout.** The live book's 2026 trades fall inside the v2 instrument's "
    "sealed holdout (2026-01-01 onward). Any follow-on filter screened from these tables has seen that period, so it "
    "cannot use that holdout as unseen data.",
    f"- **Instrument:** TRAIN replay run with `--instrument {train_m.get('instrument')}`." if train_m.get("instrument")
    else "- **Instrument:** TRAIN replay run without an `--instrument` flag (none was offered).",
    "- **Populations are never pooled.** No figure in this document combines live and TRAIN.", "",
    "## What this licenses", "", LICENCE[verdict],
    "Any bucket that looks bad (a regime, an RS quintile, an earnings bucket, a factor with a negative delta) is a "
    "screen candidate, never a filter.", "",
]
(root / "docs/superpowers/results" / name).write_text("\n".join(doc), encoding="utf-8", newline="\n")
row = ("| Confidence score as a ranker of realised R: top-minus-bottom tercile ExpR on the live book and on the TRAIN "
       "confluence replay, never pooled (v146 read-only measurement) | "
       f"**{verdict}; pre-registered verdict, computed once, no budget spent.** {phrase('Live', pops['Live'])}. "
       f"{phrase('TRAIN', pops['TRAIN'])}. Rule: PREDICTIVE needs a CI lower bound above 0 and a point estimate of at "
       "least +0.10R in both populations, WEAK in exactly one; a tercile under N=30 fails its population. "
       f"{report['looks']} looks, seed {report['seed']}, R net of frictions. {LICENCE[verdict]} "
       "Later runs are descriptive and never revise this verdict; a new verdict needs a new spec. | "
       f"`results/{name}` |")
(root / "logs/v146/closed-row.md").write_text(row + "\n", encoding="utf-8", newline="\n")
print(name, len(doc), "lines")
print(row)
PY
```

Expected: the file name and a line count, then the row. Read the generated document once, top to bottom: every table has rows for both populations, no cell reads `n/a` where the Step 7 output showed a number, and the verdict line matches Step 7's `verdict`. A layout defect is fixed in this script and the script re-run (it only re-reads the JSON; it computes nothing). A figure is never edited by hand, and the study is not run again.

Then put the row at the top of the closed table (newest first, directly under the header separator, where the v143 row sits):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
python - "$WT" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
path = root / "docs/claude/backtest-methodology.md"
row = (root / "logs/v146/closed-row.md").read_text(encoding="utf-8").strip()
lines = path.read_text(encoding="utf-8").split("\n")
assert not any("(v146" in line for line in lines), "a v146 row is already in the table"
start = lines.index("### Closed pre-registrations — do not re-run these")
separator = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("|---"))
lines.insert(separator + 1, row)
path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
print("inserted at line", separator + 2)
PY
git -C "$WT" diff --stat
```

Expected: `inserted at line <n>`; the diff stat shows one line added to `docs/claude/backtest-methodology.md` and one to the test file. The row contains `(v146`, which is what `_closed_table_tags()` in the test reads, and no other `(v<digits>` token.

- [ ] **Step 11: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Expected: PASS, `0 failed`. (`test_every_closed_table_version_has_a_ledger_row` passes because `v146` is exempt; `test_every_exempt_version_is_in_the_table_and_has_no_ledger_row` passes because the row is now tabled and no ledger id starts with `v146-`.)

No row is added to `docs/superpowers/results/preregistration-ledger.jsonl`: v146 spends no budget and has no ledger-enum verdict.

- [ ] **Step 12: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
git -C "$WT" add docs/superpowers/results docs/claude/backtest-methodology.md tests/backtesting/test_preregistration_ledger_file.py
git -C "$WT" status --short
git -C "$WT" commit -m "docs(v146): expectancy attribution verdict of record, results and closed-table row (V146-14)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: exactly three paths staged (the new results file, the methodology file, the test file), nothing from `data/` or `logs/`; the main tree unchanged.

- [ ] **Step 13: Hand back**

Report to the controller: the verdict and `verdict_of_record`, both populations' `n` and monotonicity dicts as printed in Step 7, `looks`, the seed, the frictions branch, the backfill's stamped count and every key with `unparsed > 0`, the production revision and closed-row count, any `FAIL` or reconciliation gap from Step 7, and the results file path. State that the study ran once.

---

### Task V146-15: Full suite

**Model:** haiku — dispatches one pre-specified run and relays its one-line verdict; nothing is written or decided.

**Files:** none. This task changes no file and makes no commit.

**Interfaces:**
- Consumes: every commit of V146-1 .. V146-14 on branch `2026-10-09-v146-expectancy-attribution`.
- Produces: the plan's one full-suite verdict, and the hand-off to `/panel` and `/close-out`.

This is the plan's only full-suite run. Every earlier task verified itself with the narrow run; do not add another full run before or after this one "to be sure".

- [ ] **Step 1: Preconditions**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
git -C "$WT" status --short
git -C "$WT" log --oneline main..HEAD | head -n 20
docker exec swing-db-test pg_isready -U swingbot -d swingbot_test
docker exec swing-db-test psql -U swingbot -d postgres -q -At -c "SELECT count(*) FROM pg_database WHERE datname = 'v146_scratch'"
```

Expected: a clean status; the V146-14 commit on top; `accepting connections`; `0` (V146-14 Step 8 dropped the scratch database). If the test database is not up, start it, otherwise every database test SKIPs instead of running:

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test
```

- [ ] **Step 2: Complexity of everything the branch touched**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution
git -C "$WT" diff --name-only main...HEAD -- "*.py" | sed "s|^|$WT/|" | xargs python -m radon cc -s -n C
```

Expected: only the legacy functions the index's Global Constraints name, none higher than listed there: `_score_confidence_legacy` E40, `TradeLog.log_trade` C15, `replay_scenarios` C15, `run_scenario_mode` C19, `run_backtest_range.main` F65, plus functions in those files that were already at C or above on `main` (for example `_aggregate` C18, `get_trades` C18). A function this branch added or changed that shows at C or above is reported to the controller; this task does not refactor.

- [ ] **Step 3: Run the full suite once, through `test-runner`**

Dispatch the `test-runner` subagent (so none of the ~1150 progress lines reach this context) with this brief, verbatim:

> In the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution` (session root; do not run in the main tree), run `python scripts/dev/testrun.py full` once. Return the one-line verdict, the failed and xfailed counts, the skipped count, and for every failure the test id plus the assertion line. Do not fix anything, do not re-run a failing test with other flags, and do not run the suite a second time.

Expected: the verdict line shows `0 failed` and `0 xfailed`. **Green means exactly that.** A pass count that differs from an earlier plan's is not a failure (`docs/claude/testing-cost.md`): this plan adds tests. A skipped count far above the usual means the test database was down; fix Step 1 and report that the run must be repeated for that reason only.

- [ ] **Step 4: If the suite is not green**

Do not fix anything in this task. Report each failing test id and its assertion line to the controller, who dispatches a fix at the tier of the task that owns the file (the index's Task ledger) and then repeats Step 3. A failure in `tests/backtesting/test_preregistration_ledger_file.py` or in any study test is never fixed by re-running the V146-14 study: the verdict of record stands.

- [ ] **Step 5: Hand off to the panel and the close-out**

Report to the controller: the suite's verdict line, the commit at the branch head, and that the main tree is unchanged:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution rev-parse --short HEAD
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The controller then runs, in this order (index § Where to work):

1. `/panel quant-researcher,quant-engineer,veteran-trader main...2026-10-09-v146-expectancy-attribution` — the spec carries `Panel: quant-researcher, quant-engineer, veteran-trader`, so the panel reviews the branch diff before close-out. A panel finding about the results document is applied as wording or as a stated caveat; no finding re-opens the verdict or re-runs the study.
2. `/close-out` — version bump (`Bump: bot patch`), `version_history.json`, the plan moved to `implemented/`, the worktree removed. The `v146_001` revision reaches production only through the normal deploy after merge, which is the partner's call (`mirror-prod`).
