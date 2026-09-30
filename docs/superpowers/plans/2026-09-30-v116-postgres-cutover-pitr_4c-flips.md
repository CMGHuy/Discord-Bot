# v116 — Part 4c: Phase 3 flips (V116-27 … V116-33)

Header, global constraints (stage names, groups, the `.env` rule) and revision ids: `_0-index.md`. Readiness: `_4a-readiness.md`, `_4b-readiness.md`. Spec: `docs/superpowers/specs/2026-09-30-v116-postgres-cutover-pitr-design.md` § Phase 3.

**Parallelisation (Phase 3 flips, group E):** sequential throughout — a chain of calendar soaks. V116-27 needs V116-10 (a passed drill: no store reaches `db` before the rollback is proven) and V116-26 (readiness deployed, soak cron live). Each later task needs the one before it: the spec orders the groups ops → reference → trading, and every `dual → db` gate needs five trading days of the state the previous task created.

**Every task here TOUCHES PRODUCTION.** Use the `mirror-prod` skill. Work outside the session window. `.env` changes go through `python3 scripts/ops/env_set.py` (in place), then `docker compose restart bot admin`, then a check inside **both** containers. `SCRATCH` below is the session's scratchpad directory.

**Calendar waits.** A gate task that reports `WAIT` is not failed and not done: stop, and resume it in a later session (the VM cron keeps logging). Never shorten the five days, never count a day at another stage, never re-run a dirty day into a clean one.

**The status block.** V116-27 adds a `## Status (Phase 3)` section at the end of the spec with one row per event (`date | group | from → to | evidence`). Every flip, every gate verdict and every failed gate's cause goes there, committed on `main` in the same task. A failed gate's cause is written **before** any retry (spec § Phase 3).

**Rollback to `dual` for one group** (used by any gate task whose group is already at `db` and must go back; `<names>` and `<value>` are given per task):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose stop bot admin"
for s in <names>; do
  bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose run --rm --no-deps bot python scripts/db/export_json.py --store $s --force"
done
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py DB_STORES '<value>' && docker compose up -d --no-build --wait bot admin && docker compose exec -T bot python scripts/db/parity_report.py --dual"
```

Export writes the tables back to `data/` while nothing writes (bot and admin stopped), so the files are current when `dual` resumes writing both. Expected: every parity block `VERDICT: OK`.

---

# Phase 3 — Staged production flip (flips)

### Task V116-27: ops group `json → dual` — TOUCHES PRODUCTION

**Files:**
- Modify: `.env.example` (the comment line "the live value is DB_STORES=…")
- Modify: `docs/superpowers/specs/2026-09-30-v116-postgres-cutover-pitr-design.md` (new `## Status (Phase 3)` section)

**Interfaces:**
- Consumes: V116-10 PASS in `docs/deploy/DB_RESTORE.md`; V116-26 deployed (head `v116_002`, soak cron); importers `import_jobs.py`, `import_scheduled.py`, `import_killswitch.py`.
- Produces: production `DB_STORES=watchlist:dual,state:dual,flags:dual,heartbeat:dual,jobs:dual,scheduled_jobs:dual,killswitch:dual,notify_queue:dual,scan_progress:dual,market_data_state:dual`. The ops soak starts the next trading day.

- [ ] **Step 1: Preconditions**

`grep -n "VERDICT.*PASS" docs/deploy/DB_RESTORE.md` shows the V116-10 drill; `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current && python3 scripts/ops/env_set.py --get DB_STORES && crontab -l | grep v116"` shows `v116_002 (head)`, `watchlist:dual,state:dual`, and the soak and PITR cron lines. Any difference: stop and reconcile first.

- [ ] **Step 2: Empty the ops tables while nothing reads them** (at `json` they are unused; stale rows would show as parity `EXTRA`):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c 'TRUNCATE runtime_flags, bot_heartbeat, admin_jobs, scheduled_jobs, killswitch, manual_close_notify, scan_progress, market_data_state RESTART IDENTITY'"
```

- [ ] **Step 3: Flip, restart, verify in both containers**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py DB_STORES 'watchlist:dual,state:dual,flags:dual,heartbeat:dual,jobs:dual,scheduled_jobs:dual,killswitch:dual,notify_queue:dual,scan_progress:dual,market_data_state:dual' && docker compose restart bot admin"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && for s in bot admin; do docker compose exec -T \$s python -c 'from swingbot import config; from swingbot.core.db import stages; print(stages.parse(config.DB_STORES))'; done"
```

Expected: both print the same ten `name: dual` pairs.

- [ ] **Step 4: Import the persistent ops state (flip first, then import: nothing written in between is missed; the imports are idempotent upserts)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && for s in jobs scheduled killswitch; do docker compose exec -T bot python scripts/db/import_\$s.py </dev/null | tail -4; done"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && test -f data/scan_paused.flag && docker compose exec -T bot python -c 'from swingbot.commands.scanning import runstate; runstate.set_scan_paused(True)' || echo 'not paused'"
```

The second line copies a pause set before the flip into `runtime_flags` (at `dual`, `set_scan_paused` writes both). Heartbeat, queue, progress and market-data state rewrite themselves within one tick/refresh.

- [ ] **Step 5: Parity now**

`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/db/parity_report.py --dual"`
Expected: `jobs`, `killswitch`, `scheduled_jobs`, `state`, `watchlist` all `VERDICT: OK`. A mismatch: re-run Step 4, then investigate; do not leave the group at `dual` with a failing parity overnight — flip back (`env_set.py DB_STORES 'watchlist:dual,state:dual'`, restart) and record the cause.

- [ ] **Step 6: Mirror and record, on `main`**

In `.env.example`, the comment line `# all-JSON; the live value is DB_STORES=watchlist:dual,state:dual.` becomes `# all-JSON; the live value (v116 Phase 3) is in the spec's Status section.` — **only the first time**; afterwards the spec's status block is the live record. Append to the spec:

```markdown
## Status (Phase 3)

| Date (UTC) | Group | Change | Evidence |
|---|---|---|---|
| <date> | ops | json → dual | parity --dual clean (jobs, killswitch, scheduled_jobs); DB_STORES=<value> |
```

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add .env.example docs/superpowers/specs/2026-09-30-v116-postgres-cutover-pitr-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "ops(v116): ops group to dual on production

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot push origin main
```

---

### Task V116-28: ops gate `dual → db` — TOUCHES PRODUCTION (calendar wait)

**Files:**
- Modify: the spec's `## Status (Phase 3)` table

**Interfaces:**
- Consumes: `logs/v116_parity.log` (V116-24 cron), `scripts/ops/v116_soak.py gate`.
- Produces: `DB_STORES=watchlist:dual,state:dual,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db`.

- [ ] **Step 1: Read the gate**

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/v116_parity.log" > "$SCRATCH/v116_parity.log"
python scripts/ops/v116_soak.py gate --log "$SCRATCH/v116_parity.log" --group ops --stage dual
```

Pass criteria (spec § Gate): **five consecutive trading days**, each with parity clean for every ops store that has a parity spec (`jobs`, `scheduled_jobs`, `killswitch`) and **zero** database error lines (`dual[`, `sqlalchemy.exc.`, `psycopg.`, `DatabaseUnavailable`, `StoreWriteHalt`) in the bot and admin logs.

- `GATE … WAIT` (exit 3): stop here; resume in a later session. Nothing to record.
- `GATE … DIRTY` (exit 1): the gate failed. Read the dirty day's block in the log (store lines and the first 20 error lines). Write the cause into the status table **now** (`<date> | ops | gate failed | <day>: <cause>`), commit it, fix the cause (a code fix goes through a branch commit and a ship as in V116-26 Steps 1–3), and leave the group at `dual`: the streak restarts from the next clean day. The task stays open.
- `GATE … PASS` (exit 0): continue.

- [ ] **Step 2: Flip to `db`**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py DB_STORES 'watchlist:dual,state:dual,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db' && docker compose restart bot admin"
```

Verify both containers as in V116-27 Step 3 (eight `db`, two `dual`).

- [ ] **Step 3: Smoke the ops stores at `db`**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot.commands.scanning import runstate as r; print(r.is_scan_paused(), r._read_heartbeat().get(\"timestamp\"))' && docker compose exec -T bot python scripts/db/parity_report.py --dual"
```

Expected: the pause state the partner expects, a heartbeat timestamp from the last minutes (after one session tick), and parity clean for `state`/`watchlist`. Check the admin Dashboard shows the bot alive.

- [ ] **Step 4: Record, on `main`** — status row `<date> | ops | dual → db | gate PASS, streak <n> (<first day>…<last day>)`; commit `ops(v116): ops group to db on production`; push.

If anything breaks within the Phase 4 gate window (V116-33), run the **Rollback to `dual`** procedure at the top of this part with `<names>` = `flags heartbeat jobs scheduled_jobs killswitch notify_queue scan_progress market_data_state` and `<value>` = the V116-27 value, and record it.

---

### Task V116-29: reference group `json → dual` — TOUCHES PRODUCTION

**Files:**
- Modify: the spec's `## Status (Phase 3)` table

**Interfaces:**
- Consumes: V116-28 done (ops at `db`); importers `import_ticker_directory.py`, `import_preferences.py`, `import_settings_audit.py`, `import_tuning.py`.
- Produces: `DB_STORES=watchlist:dual,state:dual,ticker_directory:dual,preferences:dual,settings_audit:dual,tuning:dual,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db`.

- [ ] **Step 1: Preconditions** — `python3 scripts/ops/env_set.py --get DB_STORES` on the VM equals the V116-28 value.

- [ ] **Step 2: Empty the four tables that are not yet written** (watchlist and signal_state are live at `dual` since v91 and are left alone):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c 'TRUNCATE ticker_directory, ui_preferences, settings_audit, tuning_results, tuning_proposals RESTART IDENTITY'"
```

- [ ] **Step 3: Flip, restart, verify in both containers**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py DB_STORES 'watchlist:dual,state:dual,ticker_directory:dual,preferences:dual,settings_audit:dual,tuning:dual,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db' && docker compose restart bot admin"
```

Verify as in V116-27 Step 3.

- [ ] **Step 4: Import, then parity**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && for s in ticker_directory preferences settings_audit tuning; do docker compose exec -T bot python scripts/db/import_\$s.py </dev/null | tail -4; done && docker compose exec -T bot python scripts/db/parity_report.py --dual"
```

Expected: `preferences`, `settings_audit`, `state`, `ticker_directory`, `tuning`, `tuning_proposals`, `watchlist` all `VERDICT: OK`. On a mismatch, flip the four back to `json` (the V116-28 value), restart, record the cause.

- [ ] **Step 5: Record, on `main`** — status row `<date> | reference | json → dual | parity --dual clean (7 stores)`; commit `ops(v116): reference group to dual on production`; push.

---

### Task V116-30: reference gate `dual → db` — TOUCHES PRODUCTION (calendar wait)

**Files:**
- Modify: the spec's `## Status (Phase 3)` table

**Interfaces:**
- Consumes: `logs/v116_parity.log`, `logs/v91_dual_check.log`, `v116_soak.py gate`.
- Produces: `DB_STORES=watchlist:db,state:db,ticker_directory:db,preferences:db,settings_audit:db,tuning:db,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db`.

- [ ] **Step 1: Record the watchlist/state head start** (spec: their v91 days count once verified from the log)

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/v91_dual_check.log" > "$SCRATCH/v91_dual_check.log"
grep -n "VERDICT" "$SCRATCH/v91_dual_check.log"
```

Write the verified v91 days into the status table (`<date> | reference | head start | watchlist/state dual since <date>, v91 check <VERDICT line>`). They show watchlist and state were already sound; they do **not** shorten this gate, because the group goes to `db` together and the other four stages have only the days since V116-29 (`_0-index.md` § Spec points, 13).

- [ ] **Step 2: Read the gate**

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/v116_parity.log" > "$SCRATCH/v116_parity.log"
python scripts/ops/v116_soak.py gate --log "$SCRATCH/v116_parity.log" --group reference --stage dual
```

Same pass criteria and `WAIT`/`DIRTY`/`PASS` handling as V116-28 Step 1, for the seven reference parity stores. A `DIRTY` leaves the group at `dual` and records the cause first.

- [ ] **Step 3: Flip to `db`, restart, verify** — `env_set.py DB_STORES` with the value above, `docker compose restart bot admin`, both containers show fourteen `db` pairs.

- [ ] **Step 4: Smoke** — the admin Watchlist, Settings (audit list) and Tuning screens load; `docker compose exec -T bot python -c "from swingbot.core.marketdata.watchlist import load_watchlist; print(len(load_watchlist()))"` prints the watchlist size the partner expects; `parity_report.py --dual` prints the no-op line.

- [ ] **Step 5: Record, on `main`** — status row `<date> | reference | dual → db | gate PASS, streak <n>`; commit `ops(v116): reference group to db on production`; push.

Rollback within the Phase 4 window: the procedure at the top with `<names>` = `watchlist state ticker_directory preferences settings_audit tuning tuning_proposals` and `<value>` = the V116-29 value.

---

### Task V116-31: trading group `json → dual` — TOUCHES PRODUCTION

**Files:**
- Modify: the spec's `## Status (Phase 3)` table

**Interfaces:**
- Consumes: V116-30 done; importers `import_plans.py`, `import_starred.py`, `import_trades.py`, `import_account.py`, `import_journal.py` (the order `scripts/ops/reimport_production.sh` documents: `starred_plans` has a foreign key into `plans`).
- Produces: `DB_STORES=plans:dual,starred_plans:dual,trades:dual,account:dual,journal:dual,watchlist:db,state:db,ticker_directory:db,preferences:db,settings_audit:db,tuning:db,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db`.

This is the real book (`memory: the partner trades real money from these alerts`). Do it on a weekend or after `SESSION_END_HOUR`, with the partner told beforehand.

- [ ] **Step 1: A checkpoint before touching the book**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type=diff backup && ./scripts/ops/backup_db.sh && date -u +%Y-%m-%dT%H:%M:%SZ"
```

Write the printed time into the status table as this flip's rollback point.

- [ ] **Step 2: Empty the trading tables (stale since the 2026-09-30 reimport; nothing reads them at `json`)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -c 'TRUNCATE starred_plans, plans, trades, account, account_balance_history, journal_entries RESTART IDENTITY CASCADE'"
```

- [ ] **Step 3: Flip, restart, verify** — `env_set.py DB_STORES` with the value above; `docker compose restart bot admin`; both containers show the five trading stages at `dual`.

- [ ] **Step 4: Import in foreign-key order, then parity**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && for s in plans starred trades account journal; do docker compose exec -T bot python scripts/db/import_\$s.py </dev/null | tail -4; done && docker compose exec -T bot python scripts/db/parity_report.py --dual"
```

Expected: `account`, `journal`, `plans`, `starred_plans`, `trades` all `VERDICT: OK`, with counts equal to the JSON files (`jq length data/trades.json` etc. on the VM). On any mismatch: flip trading back to `json` (the V116-30 value), restart, record the cause. The JSON files were never touched, so nothing is lost.

- [ ] **Step 5: Record, on `main`** — status row `<date> | trading | json → dual | checkpoint <time>; parity clean; counts <trades>/<plans>/<journal>`; commit `ops(v116): trading group to dual on production`; push.

---

### Task V116-32: trading gate `dual → db`, and `events:db` — TOUCHES PRODUCTION (calendar wait)

**Files:**
- Modify: the spec's `## Status (Phase 3)` table

**Interfaces:**
- Consumes: `logs/v116_parity.log`; the store-write halt (V116-23); the listener reconnect (V116-15).
- Produces: every store at `db`, plus `events:db` (the admin switches from stat()-polling to LISTEN/NOTIFY for every table-backed concern; `broker._default_watcher` requires every table-backed store at `db` first, which holds from this edit on). `DB_STORES=plans:db,starred_plans:db,trades:db,account:db,journal:db,watchlist:db,state:db,ticker_directory:db,preferences:db,settings_audit:db,tuning:db,flags:db,heartbeat:db,jobs:db,scheduled_jobs:db,killswitch:db,notify_queue:db,scan_progress:db,market_data_state:db,events:db`.

- [ ] **Step 1: Read the gate** — as V116-28 Step 1 with `--group trading --stage dual`; same pass criteria, five parity stores. `WAIT` stops; `DIRTY` records the cause and leaves trading at `dual`.

- [ ] **Step 2: Checkpoint** — V116-31 Step 1 again; record the time.

- [ ] **Step 3: Flip, restart, verify** — `env_set.py DB_STORES` with the value above (outside session); `docker compose restart bot admin`; both containers show twenty `db` pairs including `events`.

- [ ] **Step 4: Smoke the live path**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && P=\$(python3 scripts/ops/env_set.py --get ADMIN_PASSWORD); U=\$(python3 scripts/ops/env_set.py --get ADMIN_USERNAME); curl -s -m 5 -u \"\${U:-admin}:\$P\" http://localhost:\${ADMIN_PORT:-1234}/api/v1/events | head -5; docker compose logs --since 2m admin | grep -E 'Listening on|event listener' | tail -3"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot.core.tracking.performance import TradeLog; print(TradeLog().get_stats())'"
```

Expected: the stream opens with an `event: resync` frame; the admin log shows `Listening on trades, account, …`; `get_stats()` counts match the V116-31 import counts plus trades opened since. Then in the admin UI: Dashboard, Trades and Plans show the same book as before the flip; closing nothing, just looking.

- [ ] **Step 5: Record, on `main`** — status row `<date> | trading | dual → db, events:db | gate PASS, streak <n>; checkpoint <time>`; commit `ops(v116): trading group and events to db on production`; push.

Rollback within the Phase 4 window: the procedure at the top with `<names>` = `plans starred_plans trades account journal` and `<value>` = the V116-31 value (which also drops `events:db`, since the file watcher must watch the trading files again). If the book itself looks wrong right after the flip, `scripts/ops/rollback_to.sh "<checkpoint time>" --dry-run` first, then the partner decides.

---

### Task V116-33: Gate to Phase 4 — TOUCHES PRODUCTION (calendar wait)

**Files:**
- Modify: the spec's `## Status (Phase 3)` table
- Modify: `docs/deploy/DB_RESTORE.md` (the fresh drill)

**Interfaces:**
- Consumes: `logs/v116_parity.log`, `logs/rollback.log`, `scripts/ops/pitr_drill.sh`.
- Produces: the go-ahead for Phase 4 (`_5-delete.md`). Nothing is deleted before this task records PASS.

Pass criteria (spec § Gate to Phase 4), all three:

- [ ] **Step 1: Every group at `db` for five trading days**

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/v116_parity.log" > "$SCRATCH/v116_parity.log"
for g in ops reference trading; do python scripts/ops/v116_soak.py gate --log "$SCRATCH/v116_parity.log" --group $g --stage db; done
```

All three `PASS`. At `db` a day is clean when there are zero database error lines (parity does not apply). `WAIT` stops the task; `DIRTY` means that group goes back to `dual` with the rollback procedure at the top of this part, the cause is recorded, and the chain resumes from that group's gate.

- [ ] **Step 2: No rollback used since the first `db` flip**

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/rollback.log 2>/dev/null || echo 'no rollbacks'"
```

No `started` line dated on or after V116-28's flip date. Also no rollback-to-`dual` row in the status table since then.

- [ ] **Step 3: A drill within the last seven days — run one now**

`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && scripts/ops/pitr_drill.sh"` → `VERDICT … PASS`. Append it to `docs/deploy/DB_RESTORE.md` in the V116-10 format (this one restores a book that now lives only in Postgres, so the trade md5 compares live data).

- [ ] **Step 4: Record, on `main`** — status row `<date> | all | Phase 4 gate | db streaks ops <n>/reference <n>/trading <n>; no rollback since <date>; drill PASS <date>`; commit `ops(v116): Phase 4 gate passed`; push.

Phase 4 must start within seven days of Step 3's drill, or this step is repeated first.
