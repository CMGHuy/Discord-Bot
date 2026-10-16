# v162 Alpaca history store, part 5: VM backfill, pull, §5 re-baseline, full suite, merge, cron

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH21:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_5-production-rebaseline.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (§1 sizes, §2 runs on the VM, §4 pulling, §5 re-baseline, § Research discipline, Acceptance 1–8, Panel review quant-engineer "§5 not reproducible", quant-researcher "§5 differences need week-clustered intervals")
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts and the task ledger. Every task below implicitly includes them. Ledger part 5 outgrew the 1500-line cap: AH21–AH23 are here, AH24 and AH25 are in [`2026-10-15-v162-alpaca-history-store_5b-rebaseline-runs-close.md`](2026-10-15-v162-alpaca-history-store_5b-rebaseline-runs-close.md).

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = `E:/Documents/Private/Projects/Discord-Bot` (the main tree). Never `cd`; use `git -C $WT` and absolute paths. After each task `git -C $R status --short` shows no tracked file of the main tree changed (`data/` is gitignored, so the pulled store and the snapshots never show).
- **Production tasks (AH21, AH25) run in the main session, never in a subagent.** Each asks the partner with `AskUserQuestion` (one question, recommended option first) before its first production command. Every VM command goes through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"` (the wrapper is uncommitted and exists only in the main tree), with a script piped on stdin when it has more than one line. Never a raw `ssh`/`scp`. **Never put `$(...)` inside the quoted remote command**: the wrapper's WSL hop expands it on the dev machine first (memory: v116-closed-postgres-only). Put such logic in the stdin script instead.
- **The worktree has no store and a 3-ticker watchlist.** Everything that reads data in AH22–AH24 points at the main tree explicitly: `HISTORY_STORE_DIR=$R/data/market_data`, `BACKTEST_CACHE_DIR=<absolute snapshot dir>`, `--tickers-file <absolute path>`. A run that reads `$WT/data/` is a bug.
- **Training-switch names used here, exactly as AH10/AH11 define them:** `training_data.select(name=None)` (`None` means `"yfinance"` whenever env `BACKTEST_CACHE_DIR` is set and non-blank, else `config.TRAINING_DATA_SOURCE`), `training_data.provenance_path(out)` = `<out>.provenance.json`, `training_data.reset()`; `run_backtest_range.py --data-source {alpaca,yfinance}` writes the provenance sidecar next to both `--json` and `--trades-jsonl` outputs (`_write_provenance`); `history_store.manifest(tf)`, `history_store.store_root()`. AH13 owns `scripts/backtest/cache_dir_source.py`; this part does not touch it.
- **Guardrail.** `.claude/hooks/guardrails.py` `_rule_closed_preregistration` denies a Bash command that names `run_backtest_range.py` or `tune_strategy.py` together with a closed knob name, and that list includes the literal registry status word for a passing row. No command below does that. Never add `--emit-registry` or `--pass-wr` to a §5 run: §5 writes no registry row.
- **Research discipline (spec, binding for AH24).** §5 describes a data change. No §5 number is a lift, none selects anything, and none is read on the VALIDATION window: every §5 run is TRAIN (`--train`) or the fold-train window (`--from 2018-06-01 --to 2022-12-31`), never `--validation`. If the Alpaca leg comes out worse, the source stays Alpaca.
- Per-task runs: `python $WT/scripts/dev/testrun.py file <test>`. Complexity: `python -m radon cc -s -n C <files>` lists no new function, and every legacy function it lists keeps its score (`run_backtest_range.main` F(65), `run_scenario_mode` C(19)).

# Phase F: production backfill, pull, re-baseline, close

### Task AH21: Production: stage the branch, full backfill, check, no-op update (partner-gated)

**Model:** opus — the first write of 1.2 GB onto the production disk beside the PITR repository, through a staging mount of unreleased code, with judgement calls (a flagged ticker, an unexplained gap, a refetch on the no-op night) that decide whether the store is fit to train on.

**Files:**
- Create: `$WT/docs/superpowers/results/<run-day>-v162-history-store-backfill.md`, where `<run-day>` is the UTC date the full run starts (`YYYY-MM-DD`). The ledger names it `2026-10-15-v162-history-store-backfill.md`; rename the date, keep the rest. AH22 appends to the same file.
- No code change. VM-side effects (listed in the results doc, Step 12): `/opt/swing-bot/staging/v162/` (read-only code copy, removed by AH25), `/opt/swing-bot/data/market_data/` (the store), `/opt/swing-bot/logs/v162_backfill.log`, `/opt/swing-bot/logs/v162_check.log`, `/opt/swing-bot/logs/v162_update_noop.log`.

**Interfaces:**
- Consumes (AH7, AH8): `python scripts/data/fetch_alpaca_history.py [--mode full|update] [--tickers A,B] [--timeframes ...] [--start YYYY-MM-DD] [--root DIR] [--force] [--force-hours]`; exit 0 ok, 1 guard refused (stderr `refused: <reason>`), 2 auth error (stderr `stopped: Alpaca rejected the key (...)`); the last stdout block is `RunSummary.render()`: first line `written <n>, unchanged <n>, refetched <n>, skipped <n>, flagged <n>, requests <n>`, then one `  skipped <TICKER>/<tf>: <reason>` or `  flagged <TICKER>/<tf>: <reason>` line each. Default tickers are `fetch_backtest_data.training_tickers(load_watchlist(), config.MARKET_REGIME_TICKER, None)`: the watchlist plus SPY, the same population `data/backtest_cache/` holds. Default root `history_store.store_root()` = `/app/data/market_data` in the container.
- Consumes (AH9): `python scripts/data/check_history_store.py [--root DIR] [--tickers A,B] [--verify-hashes]`; hash problems print as lines starting `HASH `, the last line is `check: <n> unexplained gap(s), <m> hash problem(s)`; exit 1 on any.
- Consumes (index): manifest shape (Global Constraints), `MIN_FREE_BYTES = 3 * 1024**3`.
- Produces (ledger AH21, used by AH22, AH24, AH25): the VM store; the results doc with the measured full-run size per timeframe, the weekly growth estimate, the skip and flag list with reasons, the three manifest top-level hashes, the staged commit SHA, and the sector-ETF parity note.

**Why the code is staged, not deployed.** The image is only rebuilt on a push to `main` (`docs/deploy/DEPLOY_HETZNER.md` §1), and the plan merges only after the full suite (AH25). The image is `COPY . .` into `WORKDIR /app` (`Dockerfile:67,89`), so mounting the branch's `swingbot/` and `scripts/` read-only over `/app/swingbot` and `/app/scripts` runs the branch's code with the deployed image's dependencies (alpaca-py 0.44.0 is already in it since v106). The live `bot` and `admin` containers keep their own code: `compose run --rm` starts a separate, short-lived container.

**Ticker population (coordinator decision, binding).** The default list is the watchlist plus `config.MARKET_REGIME_TICKER` (SPY). **Do not add the sector ETFs** of `data/universe/etfs.json`: they are not in today's yfinance `data/backtest_cache/` either, so adding them to the Alpaca store alone would make the two training populations differ and confound the §5 legs. Under `alpaca`, `run_backtest_range._build_asof_map` loads sector ETFs through `load_cached` and finds none, exactly as it finds none under `yfinance` today. That is parity, not a gap; Step 9 measures it on both stores and the results doc records it. **SPY must be `ok` in all three timeframes** before this task moves on: it is AH9's session calendar and the regime benchmark every backtest reads (`run_backtest_range._market_frame`).

- [ ] **Step 0: Ask the partner (gate)**

Use `AskUserQuestion`, one question:

> "AH21 runs the v162 backfill on production: it copies branch commit `<git -C $WT rev-parse --short HEAD>` read-only to `/opt/swing-bot/staging/v162/`, runs `docker compose run --rm` (never `exec`) outside US regular hours at up to 120 Alpaca requests a minute, and writes about 1.2 GB into `/opt/swing-bot/data/market_data/`. The live bot, its caches and every alert are untouched. Start it now?"
> 1. "Yes, start now (outside US hours)" (Recommended)
> 2. "Not now, I will say when"

Stop here on option 2. Run no production command before the answer.

- [ ] **Step 1: Local preconditions**

```bash
git -C $WT status --short
git -C $WT log --oneline -25
python $WT/scripts/dev/testrun.py suite history-store
```

Expected: an empty status; the log shows AH1–AH20 committed on the branch; the suite reports `0 failed` and `0 xfailed`. A failure here stops the task: fix it in the task that owns the file, never on the VM.

- [ ] **Step 2: Read-only VM pre-checks**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" <<'VM_EOF'
set -u
cd /opt/swing-bot
echo "now UTC: $(date -u +%FT%TZ)   now ET: $(TZ=America/New_York date +'%F %a %H:%M')"
df -B1 --output=avail,size /opt/swing-bot | tail -1
docker compose ps --format '{{.Service}} {{.State}}'
grep -cE '^ALPACA_API_KEY_ID=.+' .env
grep -cE '^ALPACA_API_SECRET_KEY=.+' .env
ls -d data/market_data 2>/dev/null && find data/market_data -type f | wc -l
ls data/backtest_cache | wc -l
ls -d staging/v162 2>/dev/null || echo "no staging dir"
VM_EOF
```

Expected and what each line decides:
- ET time is outside 09:30–16:00 on a weekday (or it is a weekend or NYSE holiday). Otherwise wait: the script's hours guard refuses anyway, and `--force-hours` is never used in this task.
- Free bytes are above `1.2e9 + 3 * 1024**3` (about 4.5 GB). Below that, stop and ask the partner: the disk also holds the PITR repository and the nightly dumps.
- `db`, `bot` and `admin` are `running`.
- Both key counts print `1`. The values are never printed.
- `data/market_data` does not exist. If it exists (an earlier attempt), stop and ask the partner whether to resume into it (the run skips complete files) or move it aside; never delete it unasked.
- `data/backtest_cache` holds the identity references (one CSV per watchlist ticker, plus SPY).
- No staging dir. An existing one is from an earlier attempt: Step 3 replaces it.

- [ ] **Step 3: Stage the branch's code read-only**

```bash
SHA=$(git -C $WT rev-parse HEAD)
bash $R/scripts/ops/ssh-hetzner.sh "if [ -d /opt/swing-bot/staging/v162 ]; then chmod -R u+w /opt/swing-bot/staging/v162 && rm -rf /opt/swing-bot/staging/v162; fi; mkdir -p /opt/swing-bot/staging/v162"
git -C $WT archive --format=tar.gz HEAD swingbot scripts | base64 -w0 | bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot/staging/v162 && base64 -d | tar xzf - && echo $SHA > STAGED_SHA && chmod -R a-w /opt/swing-bot/staging/v162 && cat STAGED_SHA && find swingbot scripts -type f | wc -l"
git -C $WT ls-files swingbot scripts | wc -l
```

`$SHA` expands on the dev machine on purpose (it is a value, not a remote command). Expected: the VM prints the full SHA of `git -C $WT rev-parse HEAD` and a file count equal to the last local line. A mismatch means a broken stream: run Step 3 again.

The base64 transport is the one `pull_backups.sh` and AH20's pull use; a binary tar straight through the WSL hop is unverified (code brief §6).

- [ ] **Step 4: Smoke run into a throwaway root**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" <<'VM_EOF'
cd /opt/swing-bot
docker compose run --rm -T -v /opt/swing-bot/staging/v162/swingbot:/app/swingbot:ro -v /opt/swing-bot/staging/v162/scripts:/app/scripts:ro bot python scripts/data/fetch_alpaca_history.py --tickers SPY,AAPL --timeframes daily,hourly,15min --start 2025-06-01 --root /app/data/market_data_probe
echo "smoke-exit=$?"
docker compose run --rm -T -v /opt/swing-bot/staging/v162/swingbot:/app/swingbot:ro -v /opt/swing-bot/staging/v162/scripts:/app/scripts:ro bot python scripts/data/check_history_store.py --root /app/data/market_data_probe --verify-hashes
echo "check-exit=$?"
VM_EOF
bash $R/scripts/ops/ssh-hetzner.sh "head -3 /opt/swing-bot/data/market_data_probe/15min/SPY.csv; head -3 /opt/swing-bot/data/market_data_probe/hourly/SPY.csv; head -3 /opt/swing-bot/data/market_data_probe/daily/SPY.csv"
```

(The exit codes are read inside the stdin script, so nothing expands on the dev machine.) Expected:
- `smoke-exit=0`; the summary line reads `written 6, unchanged 0, refetched 0, skipped 0, flagged 0, requests <n>` (two tickers × three timeframes; one or two yearly requests each).
- `check-exit=0` and `check: 0 unexplained gap(s), 0 hash problem(s)`.
- The CSV heads show `Datetime,Open,High,Low,Close,Volume` with naive New York wall-clock times (15min starts at an extended-hours time on 2025-06-02, `04:00:00` or soon after, never a UTC time such as `08:00:00`; hourly starts `2025-06-02 09:30:00`) and `Date,...` with a naive date for daily.

Any other result stops the task: the fix goes into the owning task's code on the branch, then Step 3 restages. Then remove the probe:

```bash
bash $R/scripts/ops/ssh-hetzner.sh "rm -rf /opt/swing-bot/data/market_data_probe && ls /opt/swing-bot/data"
```

Expected: no `market_data_probe` in the listing.

- [ ] **Step 5: Start the full backfill, detached**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" <<'VM_EOF'
set -eu
cd /opt/swing-bot
date -u +%FT%TZ > logs/v162_backfill.started
nohup setsid bash -c 'cd /opt/swing-bot && docker compose run --rm -T -v /opt/swing-bot/staging/v162/swingbot:/app/swingbot:ro -v /opt/swing-bot/staging/v162/scripts:/app/scripts:ro bot python scripts/data/fetch_alpaca_history.py --mode full; echo "backfill exit $?"' > logs/v162_backfill.log 2>&1 < /dev/null &
sleep 5
cat logs/v162_backfill.started
tail -n 5 logs/v162_backfill.log
VM_EOF
```

No flag beyond `--mode full`: the defaults are the spec's (`--timeframes 15min,hourly,daily`, `--start 2016-01-01`, watchlist plus SPY, root `/app/data/market_data`). Expected: the start stamp and the first lines of the log, with no `refused:` and no `stopped:` line.

- [ ] **Step 6: Watch it to the end**

Poll with the Monitor tool (an until-loop, at most once every 5 minutes), never a foreground `sleep`:

```bash
bash $R/scripts/ops/ssh-hetzner.sh "tail -n 3 /opt/swing-bot/logs/v162_backfill.log; grep -c . /opt/swing-bot/logs/v162_backfill.log"
```

Done when the log's last line is `backfill exit <code>`. A run over 15 minutes prints a percent (AH3 `Progress`); report it to the partner at each poll in one line. By exit code:
- `backfill exit 0`: go on.
- `backfill exit 1` with `refused: ...`: a guard stopped it (hours or disk). Read the reason, tell the partner, and repeat Step 5 when the condition clears; the run resumes, skipping complete files.
- `backfill exit 2` (`stopped: Alpaca rejected the key`): stop and ask the partner. Never retry an auth error in a loop.
- A crash (a traceback, any other code): copy the traceback into the results doc, fix the owning task's code on the branch, restage (Step 3), then repeat Step 5. Files already written stay; the manifest marks what is complete.

- [ ] **Step 7: Check row counts and hashes**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" <<'VM_EOF'
cd /opt/swing-bot
docker compose run --rm -T -v /opt/swing-bot/staging/v162/swingbot:/app/swingbot:ro -v /opt/swing-bot/staging/v162/scripts:/app/scripts:ro bot python scripts/data/check_history_store.py --verify-hashes > logs/v162_check.log 2>&1
echo "check-exit=$?"
tail -n 40 logs/v162_check.log
VM_EOF
```

Expected: `check: 0 unexplained gap(s), 0 hash problem(s)` and `check-exit=0` (Acceptance 2). A hash problem is a broken write: stop and investigate before anything else. An unexplained gap is listed by ticker, timeframe and date: for each, look at that date in the file (`grep '^<date>' /opt/swing-bot/data/market_data/<tf>/<SAFE>.csv | wc -l`) and either explain it (a trading halt, a known exchange outage) in the results doc or ask the partner. Never edit a store file by hand.

- [ ] **Step 8: Manifest summary, SPY gate, size and growth**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "python3 -" <<'PY'
import json, os, pathlib, shutil
root = pathlib.Path("/opt/swing-bot/data/market_data")
WEEKLY_ROWS = {"15min": 64 * 5, "hourly": 7 * 5, "daily": 5}   # all-session 15m bars, RTH hourly, daily
for tf in ("daily", "hourly", "15min"):
    m = json.loads((root / tf / "_manifest.json").read_text())
    entries = m["tickers"]
    ok = {t: e for t, e in entries.items() if e["status"] == "ok"}
    other = {t: e["status"] for t, e in entries.items() if e["status"] != "ok"}
    files = [p for p in (root / tf).glob("*.csv")]
    size = sum(p.stat().st_size for p in files)
    rows = sum(e["rows"] or 0 for e in entries.values())
    per_row = size / rows if rows else 0.0
    print(f"== {tf}: hash {m['hash']} updated_at {m['updated_at']} feed {m['feed']} adjustment {m['adjustment']}")
    print(f"   tickers {len(entries)} ok {len(ok)} not-ok {len(other)} files {len(files)} rows {rows} bytes {size} ({size/1e9:.3f} GB, {per_row:.1f} B/row)")
    print(f"   weekly growth estimate {WEEKLY_ROWS[tf] * len(ok) * per_row / 1e6:.2f} MB")
    print(f"   first: earliest {min(e['first'] for e in ok.values())} latest {max(e['first'] for e in ok.values())}")
    print(f"   last:  earliest {min(e['last'] for e in ok.values())} latest {max(e['last'] for e in ok.values())}")
    print(f"   SPY: {entries.get('SPY', {}).get('status', 'MISSING')}")
    for t, s in sorted(other.items()):
        print(f"   {t}: {s}")
    dropped = {t: e["identity"]["dropped_before"] for t, e in entries.items()
               if e.get("identity") and e["identity"].get("dropped_before")}
    for t, d in sorted(dropped.items()):
        print(f"   {t}: bars before {d} dropped (identity)")
total, used, free = shutil.disk_usage("/opt/swing-bot")
print(f"disk free after: {free} B ({free/1e9:.2f} GB)")
PY
```

Gates (each stops the task until resolved with the partner):
- **SPY is `ok` in all three timeframes.** `SPY: ok` on each of the three `==` blocks. Anything else (`flagged: ...`, `skipped: ...`, `MISSING`) stops here: SPY is the session calendar of AH9 and the regime benchmark of every backtest, and without it every `alpaca` run has no market context.
- **Acceptance 1:** every equity of the watchlist is `ok` or listed with a reason. `first` is `2016-01-04` (daily) or the listing date; the daily `last` is within one session of the run day for every `ok` ticker. A stale `last` (a delisted or renamed ticker) is a line in the results doc.
- **Disk:** free space is above `MIN_FREE_BYTES` (3 GiB).

Every `flagged:` ticker is reported to the partner by name with its `median_ratio` and `overlap` (`jq '.tickers.<T>.identity' /opt/swing-bot/data/market_data/daily/_manifest.json` through the wrapper). A flagged ticker stays in the store and is excluded from training by `training_data` (index Global Constraints); the partner decides only whether that is acceptable for now, not whether to un-flag it.

- [ ] **Step 9: Sector-ETF parity, measured on both stores**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose run --rm -T -v /opt/swing-bot/staging/v162/swingbot:/app/swingbot:ro -v /opt/swing-bot/staging/v162/scripts:/app/scripts:ro bot python -" <<'PY'
from swingbot.core.marketdata import history_store
from swingbot.core.marketdata.backtest_cache import cache_path
from swingbot.core.marketdata.universe import sector_map
etfs = sorted(sector_map("etfs"))
in_yf = [e for e in etfs if cache_path(e).exists()]
in_store = [e for e in etfs if history_store.file_path(e, "daily").is_file()]
print("sector ETFs:", len(etfs))
print("in data/backtest_cache:", in_yf)
print("in data/market_data/daily:", in_store)
PY
```

Expected: both lists are equal (the coordinator's reading: both empty, except an ETF that is itself on the watchlist, which then appears in both). Two equal lists mean sector-relative context is equally thin under both sources: parity, not a gap. **Unequal lists stop the task**: tell the partner which ETFs differ; do not fetch anything to equalise them.

- [ ] **Step 10: No-op update (Acceptance 4, on the VM)**

Run it the same night, before the next session opens, so no new daily bar exists:

```bash
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" <<'VM_EOF'
set -u
cd /opt/swing-bot
touch /tmp/v162_noop_marker
sleep 2
docker compose run --rm -T -v /opt/swing-bot/staging/v162/swingbot:/app/swingbot:ro -v /opt/swing-bot/staging/v162/scripts:/app/scripts:ro bot python scripts/data/fetch_alpaca_history.py --mode update > logs/v162_update_noop.log 2>&1
echo "update exit $?"
grep -E '^written ' logs/v162_update_noop.log
echo "files newer than the marker: $(find data/market_data -newer /tmp/v162_noop_marker -type f | wc -l)"
for tf in daily hourly 15min; do python3 -c "import json,sys; print(sys.argv[1], json.load(open(sys.argv[2]))['updated_at'])" "$tf" "data/market_data/$tf/_manifest.json"; done
rm -f /tmp/v162_noop_marker
VM_EOF
```

Expected: `update exit 0`; `written 0, unchanged <n>, refetched 0, ...`; `files newer than the marker: 0`; each manifest's `updated_at` equals the value Step 8 printed. If the run refetched a ticker (a dividend or split posted after the full run), that is the lockstep rule working, not a failure: record the ticker and its three timeframes in the results doc, check that all three `<tf>/<SAFE>.csv` files of that ticker are newer than the marker and no file of any other ticker is, and repeat this step the next night for the no-write proof.

- [ ] **Step 11: Write the results doc**

Create `$WT/docs/superpowers/results/<run-day>-v162-history-store-backfill.md` with the Write tool, filling every `<...>` from the outputs above (values, never estimates where a measurement exists):

```markdown
# v162 history store: production backfill (<run-day>)

**Spec:** [v162 design](../specs/2026-10-15-v162-alpaca-history-store-design.md) · **Plan:** [v162 index](../plans/2026-10-15-v162-alpaca-history-store_0-index.md), task AH21
**Code:** branch `2026-10-15-v162-alpaca-history-store` at `<STAGED_SHA>`, staged read-only at `/opt/swing-bot/staging/v162/` over the deployed image `<SWING_BOT_IMAGE tag from /opt/swing-bot/.env>`
**Run:** `docker compose run --rm` on the VM, `--mode full`, defaults (15min, hourly, daily; start 2016-01-01; watchlist plus SPY), started `<v162_backfill.started>`, finished `<UTC>`, `<requests>` requests

## Manifests

| timeframe | top-level hash | tickers | ok | not ok | rows | bytes | B/row |
|---|---|---|---|---|---|---|---|
| daily | `<hash>` | <n> | <n> | <n> | <rows> | <bytes> | <b> |
| hourly | `<hash>` | <n> | <n> | <n> | <rows> | <bytes> | <b> |
| 15min | `<hash>` | <n> | <n> | <n> | <rows> | <bytes> | <b> |

Measured full-run size: <total GB> (spec estimate 1.2 GB). Weekly growth estimate from the measured bytes per row: <MB> a week (15min <MB>, hourly <MB>, daily <MB>). Disk free after the run: <GB>.

## Skipped and flagged

| ticker | status | detail |
|---|---|---|
| <T> | <skipped: ... / flagged: ...> | <median_ratio, overlap, dropped_before, or why> |

Bars dropped before the identity reference's first bar: <ticker: date, ... or "none">.

## Checks

- Row counts and hashes (`check_history_store.py --verify-hashes`): `<last line>`. <each unexplained gap with its explanation, or "none">
- SPY is `ok` in daily, hourly and 15min (session calendar of the check script, regime benchmark of every backtest).
- No-op update (`--mode update`, same night): `<summary line>`; files written: <0>; manifest `updated_at` unchanged. <any lockstep refetch and the night it was re-proved>
- Sector-relative context: the sector ETFs of `data/universe/etfs.json` present in `data/backtest_cache/` are <list>, and in `data/market_data/daily/` <list>. The lists are equal, so sector-relative context is equally thin under both sources: parity, not a gap. No ETF was added to the store, because adding them to one source only would make the §5 legs train on different populations.

## Production changes and their mirror

- `/opt/swing-bot/data/market_data/` (the store): data under the gitignored `data/` bind mount, written only by the committed `scripts/data/fetch_alpaca_history.py`. Not mirrored by design.
- `/opt/swing-bot/staging/v162/`: a read-only copy of the branch's `swingbot/` and `scripts/` at the SHA above. Temporary; AH25 removes it once the merged image is deployed.
- `/opt/swing-bot/logs/v162_{backfill,check,update_noop}.log`: run logs.
- No crontab, `.env`, compose or image change. The weekly cron is installed by AH25 from the committed `scripts/ops/install_v162_history_cron.sh`.
```

- [ ] **Step 12: Commit**

```bash
git -C $WT add docs/superpowers/results/<run-day>-v162-history-store-backfill.md
git -C $WT commit -m "docs(v162): AH21 production backfill results -- sizes, manifest hashes, skips and flags, no-op update

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows no tracked change. Tell the partner in two lines: the measured size and the skip and flag counts.

### Task AH22: Pull the store to the dev machine and verify hashes

**Model:** sonnet — runs AH20's finished pull script, then compares hashes and records them; the only judgement is stopping on a mismatch.

**Files:**
- Modify: `$WT/docs/superpowers/results/<run-day>-v162-history-store-backfill.md` (AH21's file; append a `## Pulled to the dev machine` section)
- Local data only: `$R/data/market_data/` (gitignored by the unanchored `market_data/` pattern, `.gitignore:31`), `$R/data/market_data.check.txt`

**Interfaces:**
- Consumes (AH20): `bash $WT/scripts/ops/pull_history_store.sh [--probe]`. It reaches the VM only through `SSH_HETZNER` (default `E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh`), writes the **main tree's** `data/market_data/` (the parent of git's common dir, so running it from `$WT` still lands in `$R`), extracts into `data/market_data.partial/`, verifies with `check_history_store.py --root <partial> --verify-hashes` and only then swaps in (keeping `data/market_data.prev/`). It prints `pull_history_store: probe PASS <sha>` / `pull_history_store: PASS <dest> bytes=<n>`; exit 1 on a hash failure (leaves `.partial` and `.partial.check.txt`), exit 2 when `.partial` already exists.
- Consumes (AH9): `python scripts/data/check_history_store.py --root DIR --verify-hashes`, last line `check: <n> unexplained gap(s), <m> hash problem(s)`.
- Consumes (AH10, AH2): `training_data.select("alpaca")`, `training_data.provenance()`, `training_data.available_tickers()`; `history_store.manifest(tf)`; env `HISTORY_STORE_DIR` read on every call.
- Consumes (AH21): the three manifest top-level hashes recorded in the results doc.
- Produces (ledger AH22, used by AH24): `$R/data/market_data/{15min,hourly,daily}/` identical to the VM store, with the same three manifest hashes.

No VM write happens here: the pull's remote side only reads (AH20 rule), so this task needs no partner gate. It does need AH21 finished, and the weekly cron is not installed yet (AH25), so the VM store cannot move between AH21 and this pull.

- [ ] **Step 1: Prove the binary path on one small file**

```bash
bash $WT/scripts/ops/pull_history_store.sh --probe
```

Expected: `pull_history_store: probe PASS <sha256>`. `probe FAIL` means the base64-over-WSL stream corrupts data: stop, do not run the full pull, and report the two hashes to the partner.

- [ ] **Step 2: Pull, verify, swap in**

```bash
ls -d $R/data/market_data $R/data/market_data.partial 2>/dev/null || echo "no local store yet"
bash $WT/scripts/ops/pull_history_store.sh
```

Expected: `pull_history_store: streaming 15min`, `... hourly`, `... daily`, the `check:` line with `0 hash problem(s)`, then `pull_history_store: PASS E:/Documents/Private/Projects/Discord-Bot/data/market_data bytes=<n>`. The byte count is within a few KB of the sum of AH21's three `bytes` figures (the manifests and `check.txt` add a little).

On `FAIL hash verify`: read `$R/data/market_data.partial.check.txt`, run Step 1 again, and ask the partner before deleting `.partial` (the script never deletes it). On exit 2 (a `.partial` from an earlier attempt): show the partner its `check.txt` and ask before removing it.

- [ ] **Step 3: Compare the manifest hashes with the VM's**

```bash
for tf in daily hourly 15min; do python -c "import json,sys; m=json.load(open(sys.argv[1])); print(sys.argv[2], m['hash'], m['updated_at'], len(m['tickers']))" "$R/data/market_data/$tf/_manifest.json" "$tf"; done
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" <<'VM_EOF'
for tf in daily hourly 15min; do python3 -c "import json,sys; m=json.load(open(sys.argv[1])); print(sys.argv[2], m['hash'], m['updated_at'], len(m['tickers']))" "/opt/swing-bot/data/market_data/$tf/_manifest.json" "$tf"; done
VM_EOF
```

Expected: the three local lines equal the three VM lines exactly, and the hashes equal the ones in AH21's results doc. Any difference stops the task.

- [ ] **Step 4: The local copy is readable through the seam, and ignored by git**

```bash
HISTORY_STORE_DIR=$R/data/market_data python $WT/scripts/data/check_history_store.py --root $R/data/market_data --verify-hashes | tail -n 1
HISTORY_STORE_DIR=$R/data/market_data PYTHONPATH=$WT python -c "from swingbot.core.marketdata import training_data, history_store; print(training_data.select('alpaca')); p = training_data.provenance(); print(p['manifest_hash'], p['feed'], p['adjustment'], len(p['excluded'])); print(len(training_data.available_tickers()), 'trainable'); print(history_store.load('SPY', 'daily').index[[0, -1]].tolist())"
git -C $R check-ignore -v data/market_data/daily/SPY.csv data/market_data/daily/_manifest.json
git -C $R status --short
```

Expected:
- `check: 0 unexplained gap(s), 0 hash problem(s)` (the same verdict AH21 got on the VM).
- `alpaca`; the daily manifest hash, `sip all`, and the number of not-`ok` daily tickers from AH21; a trainable count equal to AH21's daily `ok` count; SPY's first and last daily dates (`2016-01-04` and the run's last session).
- Both paths ignored by `.gitignore:31 market_data/`.
- `git status` shows no `data/market_data` path.

- [ ] **Step 5: Append to the results doc**

Append to `$WT/docs/superpowers/results/<run-day>-v162-history-store-backfill.md` with the Edit tool:

```markdown
## Pulled to the dev machine (<UTC date>)

`bash scripts/ops/pull_history_store.sh` (probe first: `probe PASS <sha256>`), into `E:/Documents/Private/Projects/Discord-Bot/data/market_data/`, <bytes> bytes. Local manifest hashes equal the VM's: daily `<hash>`, hourly `<hash>`, 15min `<hash>`. `check_history_store.py --verify-hashes` on the local copy: `<last line>`. `training_data.select("alpaca")` on it: <n> trainable tickers, <n> excluded.
```

- [ ] **Step 6: Commit**

```bash
git -C $WT add docs/superpowers/results/<run-day>-v162-history-store-backfill.md
git -C $WT commit -m "docs(v162): AH22 store pulled to the dev machine, manifest hashes match the VM

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows no tracked change.

### Task AH23: §5 tooling: frozen snapshot, `--tickers-file`, re-baseline report

**Model:** opus — the tooling that makes a data-change measurement reproducible: frozen hashed inputs, one shared ticker set, provenance checks per leg and week-clustered paired intervals; a mistake here produces numbers that look like a lift.

**Files:**
- Create: `scripts/data/snapshot_backtest_cache.py`
- Create: `scripts/reports/v162_rebaseline_report.py`
- Modify: `scripts/backtest/run_backtest_range.py` (`run_scenario_mode` signature and its `_tickers_for_run` line :260-265; `_tickers_for_run` :324-331; `main` argparse after `--universe` :468-470; the `run_scenario_mode(...)` call :537-539; normal-mode `tickers = _tickers_for_run(args.universe)` :555). Line numbers are from `main` before AH11; find each by its text.
- Test: `tests/history_store/test_rebaseline.py`

**Interfaces:**
- Consumes (AH2): `history_store.require_manifest("daily") -> dict` (raises `MissingStoreError`, a `RuntimeError`, naming the path), env `HISTORY_STORE_DIR`, fixture `store_root(tmp_path, monkeypatch) -> Path` from `tests/history_store/conftest.py` (also puts `scripts/data` and `scripts/ops` on `sys.path`). (AH10): `training_data.provenance_path(out) -> Path` (`<out>.provenance.json`); the yfinance provenance dict is `{"data_source": "yfinance", "feed": "yfinance", "adjustment": "auto_adjust", "manifest_hash": None, "store_dir": str(backtest_cache.CACHE_DIR), "excluded": {}}`, the alpaca one has `feed`, `adjustment`, `manifest_hash`, `store_dir` from the store. (AH11): `run_backtest_range._write_provenance` writes that sidecar next to `--trades-jsonl`. Existing: `backtest_cache.cache_path(ticker).name` (the CSV name, `=`,`^`,`/` → `_`), `config.MARKET_REGIME_TICKER`, `stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed)`, `stats.WEEK_BOOTSTRAP_RESAMPLES = 10_000`, `stats.WEEK_BOOTSTRAP_SEED = 42` (`swingbot/core/backtesting/instrument/stats.py:24-25,57`), the `--trades-jsonl` row shape of `write_trades_jsonl` (`ticker`, `strategy`, `horizon_key` plus every `BacktestTrade` field: `entry_date`, `outcome` in `win|loss|scratch|timeout`, `r_multiple`, ...).
- Produces (ledger AH23, used by AH24):
  - `python scripts/data/snapshot_backtest_cache.py --src DIR --out DIR [--start YYYY-MM-DD] [--tickers-file PATH]`: copies the cache (byte for byte without `--start`; rows before `--start` dropped with it) and writes `<out>/_hashes.json` = `{"src", "start", "created_at", "files": {name: sha256}, "hash"}`. With `--tickers-file`, it copies exactly those tickers plus `config.MARKET_REGIME_TICKER` and fails on any missing file. It refuses a non-empty `--out`. Two extra modes, used only by AH24: `--verify DIR` (exit 1 on any `MISSING`/`CHANGED`/`EXTRA`/`HASH` line) and `--intersect-out PATH --watchlist-file PATH --src DIR` (writes the §5 ticker set: watchlist tickers that are `ok` in the store's daily manifest and have a CSV in `--src`).
  - Python: `read_tickers_file(path) -> list[str]` (one ticker per line, `#` comments, upper-cased, de-duplicated, sorted), `csv_name(ticker) -> str`, `combined_hash(files: dict[str, str]) -> str`, `snapshot(src, out, *, start=None, tickers=None, now=None) -> dict`, `verify(out) -> list[str]`, `intersection_tickers(watchlist, manifest, cache_dir) -> list[str]`, `main(argv=None) -> int`.
  - `run_backtest_range.py --tickers-file PATH`: `_tickers_from_file(path: str) -> list[str]` (delegates to `read_tickers_file`; `SystemExit` on an empty list); `_tickers_for_run(universe, tickers_file=None)` (the file wins; `SystemExit` when both are given); `run_scenario_mode(..., tickers_file=None)`.
  - `python scripts/reports/v162_rebaseline_report.py --leg a=PATH[,PATH...] --leg b=PATH[,PATH...] --leg c=PATH[,PATH...] --window {train,fold-train} --out PATH [--md PATH] [--resamples N]`: PATHs are `--trades-jsonl` outputs, each with its provenance sidecar. `--out` is a JSON file `{"windows": {<window>: <report>}}` that a second call (the other window) extends; the markdown section is printed and, with `--md`, also written. Exit 1 with `error: ...` on a provenance, window or snapshot problem. Python: `LEG_SOURCES`, `WINDOWS`, `COMPARISONS`, `Trade`, `parse_leg`, `load_trades`, `load_provenance`, `leg_stats`, `win_rate`, `expectancy`, `difference`, `ticker_counts`, `build_report`, `render_markdown`, `merge_into`, `main`.

**Rules this task freezes (spec §5, Panel quant-engineer "§5 not reproducible", quant-researcher "week-clustered intervals"):**
- **Frozen inputs.** The yfinance legs read a snapshot whose every file is hashed; the report refuses a yfinance leg whose `store_dir` has no `_hashes.json`, and records the snapshot's top-level hash next to the Alpaca leg's manifest hash.
- **One ticker set.** Every leg runs `--tickers-file <the intersection>`; the benchmark (SPY) is copied into each snapshot for market context but is traded only if the watchlist holds it.
- **Leg sources are fixed:** `a` and `b` must be `yfinance`, `c` must be `alpaca`, read from each file's sidecar. A leg made of several files (a per-strategy chunked run) must have identical sidecars.
- **Every trade lies in the named window** (`train` 2020-01-01..2023-12-31, `fold-train` 2018-06-01..2022-12-31), or the report refuses: a mislabeled file never lands under the wrong window.
- **Statistics match `run_backtest_range.pool`:** win rate is wins over win+loss, in percent; ExpR is the mean `r_multiple` over every closed trade (`win`, `loss`, `scratch`, `timeout`). Rows with any other outcome are ignored; a closed row with no `r_multiple` is an error.
- **Intervals:** every ExpR and win-rate difference is the paired week-clustered bootstrap (`stats.week_cluster_bootstrap`, both legs resampled with the same week draw, default 10,000 resamples, seed 42), reported as the 2.5th and 97.5th percentiles. Each markdown sentence carries the difference, its interval, the window and N. The section says the numbers describe a data change and are not a lift.
- **Not in this task:** running any leg (AH24), any `--validation` run, any registry or ledger write.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_rebaseline.py`:

```python
"""v162 AH23: the §5 re-baseline tooling. A frozen, hashed yfinance snapshot,
one explicit ticker set for every leg, and a report that checks each leg's
provenance and window before it computes paired week-clustered intervals."""
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

import snapshot_backtest_cache as snap
from swingbot import config
from swingbot.core.marketdata import training_data

ROOT = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rbr = _load("rbr_v162_ah23", "scripts/backtest/run_backtest_range.py")
rep = _load("v162_rebaseline_report", "scripts/reports/v162_rebaseline_report.py")


def _cache(folder: Path, tickers, start="2014-01-02", days=600):
    folder.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=days, name="Date")
    for t in tickers:
        frame = pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100.0},
                             index=idx)
        frame.to_csv(folder / f"{t}.csv")
    return folder


# --- tickers file ------------------------------------------------------------

def test_tickers_file_is_upper_cased_deduplicated_sorted_with_comments(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("msft\n# a comment line\nAAPL  # trailing comment\n\nmsft\n", encoding="utf-8")
    assert snap.read_tickers_file(f) == ["AAPL", "MSFT"]


def test_csv_name_follows_the_cache_naming():
    assert snap.csv_name("AAPL") == "AAPL.csv"
    assert snap.csv_name("GC=F") == "GC_F.csv"


# --- snapshot ----------------------------------------------------------------

def test_snapshot_copies_bytes_and_hashes_every_file(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL", "SPY"])
    manifest = snap.snapshot(src, tmp_path / "snap")
    assert sorted(manifest["files"]) == ["AAPL.csv", "SPY.csv"]
    assert (tmp_path / "snap" / "AAPL.csv").read_bytes() == (src / "AAPL.csv").read_bytes()
    on_disk = json.loads((tmp_path / "snap" / "_hashes.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    assert manifest["hash"] == snap.combined_hash(manifest["files"])
    assert manifest["start"] is None and manifest["src"] == str(src)
    assert snap.verify(tmp_path / "snap") == []


def test_start_drops_earlier_rows_and_keeps_the_date_header(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL"], start="2015-06-01")
    snap.snapshot(src, tmp_path / "snap", start="2016-01-01")
    out = pd.read_csv(tmp_path / "snap" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert out.index.min() >= pd.Timestamp("2016-01-01")
    assert out.index.min() < pd.Timestamp("2016-01-08")
    full = pd.read_csv(src / "AAPL.csv", index_col="Date", parse_dates=True)
    assert len(out) == int((full.index >= pd.Timestamp("2016-01-01")).sum())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_a_ticker_list_copies_exactly_those_and_fails_on_a_missing_one(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL", "MSFT", "SPY"])
    manifest = snap.snapshot(src, tmp_path / "snap", tickers=["AAPL", "SPY"])
    assert sorted(manifest["files"]) == ["AAPL.csv", "SPY.csv"]
    with pytest.raises(FileNotFoundError, match="NVDA.csv"):
        snap.snapshot(src, tmp_path / "snap2", tickers=["AAPL", "NVDA"])
    assert not (tmp_path / "snap2").exists()


def test_a_non_empty_target_is_never_overwritten(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL"])
    snap.snapshot(src, tmp_path / "snap")
    with pytest.raises(FileExistsError):
        snap.snapshot(src, tmp_path / "snap")


def test_verify_names_changed_missing_and_extra_files(tmp_path):
    src = _cache(tmp_path / "cache", ["AAPL", "MSFT"])
    out = tmp_path / "snap"
    snap.snapshot(src, out)
    (out / "AAPL.csv").write_text("Date,Open\n", encoding="utf-8")
    (out / "MSFT.csv").unlink()
    (out / "NVDA.csv").write_text("Date,Open\n", encoding="utf-8")
    assert snap.verify(out) == ["CHANGED AAPL.csv", "MISSING MSFT.csv", "EXTRA NVDA.csv"]


def test_cli_adds_the_benchmark_to_a_ticker_list(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    src = _cache(tmp_path / "cache", ["AAPL", "MSFT", "SPY"])
    tickers = tmp_path / "t.txt"
    tickers.write_text("AAPL\n", encoding="utf-8")
    out = tmp_path / "snap"
    assert snap.main(["--src", str(src), "--out", str(out), "--tickers-file", str(tickers)]) == 0
    assert sorted(json.loads((out / "_hashes.json").read_text(encoding="utf-8"))["files"]) == ["AAPL.csv", "SPY.csv"]
    assert snap.main(["--verify", str(out)]) == 0
    (out / "AAPL.csv").write_text("x\n", encoding="utf-8")
    assert snap.main(["--verify", str(out)]) == 1


def test_cli_reports_a_refusal_as_exit_1(tmp_path, capsys):
    src = _cache(tmp_path / "cache", ["AAPL"])
    snap.snapshot(src, tmp_path / "snap")
    assert snap.main(["--src", str(src), "--out", str(tmp_path / "snap")]) == 1
    assert "never overwritten" in capsys.readouterr().err


# --- intersection --------------------------------------------------------------

def _manifest(statuses):
    return {"timeframe": "daily", "feed": "sip", "adjustment": "all", "hash": "h",
            "tickers": {t: {"status": s} for t, s in statuses.items()}}


def test_intersection_keeps_watchlist_tickers_ok_in_the_store_and_cached(tmp_path):
    cache = _cache(tmp_path / "cache", ["AAPL", "MSFT", "SPY", "TSLA"])
    manifest = _manifest({"AAPL": "ok", "MSFT": "flagged: price-mismatch", "SPY": "ok",
                          "NVDA": "ok", "TSLA": "ok"})
    watchlist = ["aapl", "MSFT", "NVDA", "TSLA"]
    assert snap.intersection_tickers(watchlist, manifest, cache) == ["AAPL", "TSLA"]


def test_cli_writes_the_intersection_from_the_store_manifest(tmp_path, store_root):
    daily = store_root / "daily"
    daily.mkdir(parents=True)
    (daily / "_manifest.json").write_text(json.dumps(_manifest({"AAPL": "ok", "MSFT": "ok"})),
                                          encoding="utf-8")
    cache = _cache(tmp_path / "cache", ["AAPL"])
    watch = tmp_path / "watch.txt"
    watch.write_text("AAPL\nMSFT\n", encoding="utf-8")
    out = tmp_path / "tickers.txt"
    assert snap.main(["--intersect-out", str(out), "--watchlist-file", str(watch),
                      "--src", str(cache)]) == 0
    assert out.read_text(encoding="utf-8") == "AAPL\n"


def test_cli_intersection_without_a_store_is_an_error(tmp_path, store_root, capsys):
    watch = tmp_path / "watch.txt"
    watch.write_text("AAPL\n", encoding="utf-8")
    assert snap.main(["--intersect-out", str(tmp_path / "t.txt"), "--watchlist-file", str(watch),
                      "--src", str(_cache(tmp_path / "cache", ["AAPL"]))]) == 1
    assert "_manifest.json" in capsys.readouterr().err


# --- run_backtest_range --tickers-file ---------------------------------------

def test_tickers_file_replaces_the_watchlist(tmp_path, monkeypatch):
    f = tmp_path / "t.txt"
    f.write_text("msft\nAAPL\n", encoding="utf-8")
    monkeypatch.setattr(rbr, "load_watchlist", lambda: pytest.fail("the watchlist was read"))
    assert rbr._tickers_for_run(None, str(f)) == ["AAPL", "MSFT"]


def test_without_a_file_the_watchlist_is_used(monkeypatch):
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["MSFT", "AAPL"])
    assert rbr._tickers_for_run(None) == ["AAPL", "MSFT"]


def test_tickers_file_and_universe_are_exclusive(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("AAPL\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="exclusive"):
        rbr._tickers_for_run("etfs", str(f))


def test_an_empty_tickers_file_is_an_error(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="names no ticker"):
        rbr._tickers_from_file(str(f))


def test_both_run_modes_pass_the_file_through():
    src = (ROOT / "scripts" / "backtest" / "run_backtest_range.py").read_text(encoding="utf-8")
    assert '"--tickers-file"' in src
    assert "tickers = _tickers_for_run(args.universe, args.tickers_file)" in src
    assert "tickers = _tickers_for_run(universe, tickers_file)" in src
    assert "tickers_file=args.tickers_file" in src


# --- report ------------------------------------------------------------------

WEEKS = ("2021-01-04", "2021-01-11", "2021-01-18", "2021-01-25")


def _row(ticker, day, outcome, r):
    return {"ticker": ticker, "strategy": "RSI", "horizon_key": "swing", "entry_date": day,
            "exit_date": day, "direction": "long", "entry": 10.0, "stop_loss": 9.0,
            "take_profit": 12.0, "outcome": outcome, "exit_price": 11.0, "return_pct": 1.0,
            "r_multiple": r, "holding_days": 3, "runner_outcome": None, "context": None}


def _snapshot_dir(tmp_path, name="snap", digest="snaphash"):
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    (folder / "_hashes.json").write_text(json.dumps({"hash": digest, "files": {}}), encoding="utf-8")
    return folder


def _write_leg(tmp_path, name, rows, *, source, store_dir):
    path = tmp_path / f"{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    prov = {"data_source": source, "feed": "sip" if source == "alpaca" else "yfinance",
            "adjustment": "all" if source == "alpaca" else "auto_adjust",
            "manifest_hash": "mhash" if source == "alpaca" else None,
            "store_dir": str(store_dir), "excluded": {}}
    training_data.provenance_path(path).write_text(json.dumps(prov), encoding="utf-8")
    return path


A_ROWS = [_row("AAPL", WEEKS[0], "win", 2.0), _row("AAPL", WEEKS[1], "loss", -1.0),
          _row("MSFT", WEEKS[2], "win", 2.0), _row("MSFT", WEEKS[3], "loss", -1.0)]
C_ROWS = [_row("AAPL", WEEKS[0], "win", 2.0), _row("AAPL", WEEKS[1], "win", 2.0),
          _row("MSFT", WEEKS[2], "win", 2.0), _row("MSFT", WEEKS[3], "loss", -1.0),
          _row("MSFT", WEEKS[3], "not_triggered", 0.0)]


@pytest.fixture
def legs(tmp_path):
    yf = _snapshot_dir(tmp_path)
    return {"a": _write_leg(tmp_path, "a", A_ROWS, source="yfinance", store_dir=yf),
            "b": _write_leg(tmp_path, "b", A_ROWS, source="yfinance", store_dir=yf),
            "c": _write_leg(tmp_path, "c", C_ROWS, source="alpaca", store_dir=tmp_path / "store")}


def _report(legs, window="train", resamples=300):
    trades = {k: rep.load_trades([p]) for k, p in legs.items()}
    prov = {k: rep.load_provenance(k, [p]) for k, p in legs.items()}
    return rep.build_report(trades, prov, window, n_resamples=resamples)


def test_parse_leg():
    assert rep.parse_leg("a=x.jsonl") == ("a", [Path("x.jsonl")])
    assert rep.parse_leg("C=x.jsonl,y.jsonl") == ("c", [Path("x.jsonl"), Path("y.jsonl")])
    for bad in ("d=x.jsonl", "a", "a="):
        with pytest.raises(Exception):
            rep.parse_leg(bad)


def test_leg_stats_match_the_runner_pool(legs):
    report = _report(legs)
    a, c = report["legs"]["a"], report["legs"]["c"]
    assert (a["trades"], a["n_eval"], a["wins"], a["win_rate"], a["expectancy_r"]) == (4, 4, 2, 50.0, 0.5)
    assert (c["trades"], c["n_eval"], c["wins"], c["win_rate"], c["expectancy_r"]) == (4, 4, 3, 75.0, 1.25)
    assert c["tickers"] == 2


def test_differences_carry_paired_week_clustered_intervals(legs):
    report = _report(legs)
    total = next(x for x in report["comparisons"] if (x["base"], x["comp"]) == ("a", "c"))
    assert total["expectancy_r"]["point"] == pytest.approx(0.75)
    assert total["win_rate"]["point"] == pytest.approx(25.0)
    lo, hi = total["expectancy_r"]["ci95"]
    assert lo <= 0.75 <= hi and total["expectancy_r"]["draws"] == 300
    same = next(x for x in report["comparisons"] if (x["base"], x["comp"]) == ("a", "b"))
    assert same["expectancy_r"]["point"] == 0.0 and same["expectancy_r"]["ci95"] == [0.0, 0.0]
    assert [(x["base"], x["comp"]) for x in report["comparisons"]] == [("a", "b"), ("b", "c"), ("a", "c")]


def test_provenance_and_snapshot_hash_are_recorded(legs):
    report = _report(legs)
    assert report["legs"]["a"]["provenance"]["snapshot_hash"] == "snaphash"
    assert report["legs"]["c"]["provenance"]["manifest_hash"] == "mhash"
    assert (report["window"], report["from"], report["to"]) == ("train", "2020-01-01", "2023-12-31")


def test_per_ticker_counts(legs):
    assert _report(legs)["per_ticker"] == {"AAPL": {"a": 2, "b": 2, "c": 2},
                                           "MSFT": {"a": 2, "b": 2, "c": 2}}


def test_a_leg_with_the_wrong_source_is_refused(tmp_path):
    path = _write_leg(tmp_path, "c", C_ROWS, source="yfinance", store_dir=_snapshot_dir(tmp_path))
    with pytest.raises(ValueError, match="leg c must be alpaca"):
        rep.load_provenance("c", [path])


def test_a_yfinance_leg_off_a_live_cache_is_refused(tmp_path):
    path = _write_leg(tmp_path, "a", A_ROWS, source="yfinance", store_dir=tmp_path / "live_cache")
    with pytest.raises(ValueError, match="not a v162 snapshot"):
        rep.load_provenance("a", [path])


def test_chunk_files_must_agree_on_provenance(tmp_path):
    one = _write_leg(tmp_path, "c1", C_ROWS, source="alpaca", store_dir=tmp_path / "store")
    two = _write_leg(tmp_path, "c2", C_ROWS, source="alpaca", store_dir=tmp_path / "other")
    with pytest.raises(ValueError, match="disagree"):
        rep.load_provenance("c", [one, two])
    assert len(rep.load_trades([one, one])) == 8


def test_a_missing_sidecar_is_refused(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text(json.dumps(A_ROWS[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no provenance sidecar"):
        rep.load_provenance("a", [path])


def test_a_trade_outside_the_window_is_refused(legs):
    with pytest.raises(ValueError, match="outside fold-train"):
        trades = {k: rep.load_trades([p]) for k, p in legs.items()}
        trades["a"].append(rep.Trade("AAPL", "RSI", "2023-06-01", "win", 2.0))
        prov = {k: rep.load_provenance(k, [p]) for k, p in legs.items()}
        rep.build_report(trades, prov, "fold-train", n_resamples=50)


def test_a_closed_trade_without_r_is_an_error(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text(json.dumps(_row("AAPL", WEEKS[0], "win", None)) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="without r_multiple"):
        rep.load_trades([path])


def test_markdown_puts_difference_interval_window_and_n_in_one_sentence(legs):
    md = rep.render_markdown(_report(legs))
    line = next(l for l in md.splitlines() if l.startswith("- total"))
    assert "ExpR +0.750 R" in line and "95% CI" in line
    assert "window train 2020-01-01..2023-12-31" in line and "N 4 -> 4" in line
    assert "not a lift" in md


def test_cli_merges_both_windows_into_one_json(legs, tmp_path):
    out = tmp_path / "rebaseline.json"
    md = tmp_path / "train.md"
    args = [f"--leg=a={legs['a']}", f"--leg=b={legs['b']}", f"--leg=c={legs['c']}",
            "--out", str(out), "--resamples", "100"]
    assert rep.main(args + ["--window", "train", "--md", str(md)]) == 0
    assert rep.main(args + ["--window", "fold-train"]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(doc["windows"]) == ["fold-train", "train"]
    assert md.read_text(encoding="utf-8").startswith("### Window train")


def test_cli_needs_each_leg_once(legs):
    with pytest.raises(SystemExit):
        rep.main([f"--leg=a={legs['a']}", f"--leg=c={legs['c']}", "--window", "train",
                  "--out", "x.json"])


def test_cli_turns_a_provenance_problem_into_exit_1(tmp_path, capsys):
    yf = _snapshot_dir(tmp_path)
    a = _write_leg(tmp_path, "a", A_ROWS, source="yfinance", store_dir=yf)
    c = _write_leg(tmp_path, "c", C_ROWS, source="yfinance", store_dir=yf)
    code = rep.main([f"--leg=a={a}", f"--leg=b={a}", f"--leg=c={c}", "--window", "train",
                     "--out", str(tmp_path / "o.json"), "--resamples", "50"])
    assert code == 1 and "leg c must be alpaca" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_rebaseline.py`
Expected: collection error, `ModuleNotFoundError: No module named 'snapshot_backtest_cache'`.

- [ ] **Step 3: Write the snapshot script**

Create `$WT/scripts/data/snapshot_backtest_cache.py`:

```python
"""v162 §5: freeze a yfinance daily cache into a hashed snapshot.

The §5 re-baseline must be reproducible, and data/backtest_cache/ is refreshed
by the live bot. So the yfinance legs read a copy whose every file is hashed:

  python scripts/data/snapshot_backtest_cache.py --src data/backtest_cache \\
      --out data/backtest_cache_snapshot_v162 --tickers-file T.txt          # leg a
  python scripts/data/snapshot_backtest_cache.py --src data/backtest_cache \\
      --out data/backtest_cache_snapshot_v162_from2016 --tickers-file T.txt \\
      --start 2016-01-01                                                    # leg b
  python scripts/data/snapshot_backtest_cache.py --verify data/backtest_cache_snapshot_v162
  python scripts/data/snapshot_backtest_cache.py --intersect-out T.txt \\
      --watchlist-file W.txt --src data/backtest_cache                      # the §5 ticker set

With --tickers-file the benchmark (config.MARKET_REGIME_TICKER) is always
copied too: every backtest reads it for market context. A snapshot is never
overwritten; <out>/_hashes.json holds a SHA-256 per file and one over all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HASHES_FILE = "_hashes.json"


def read_tickers_file(path) -> list[str]:
    """One ticker per line; '#' starts a comment. Upper-cased, de-duplicated, sorted."""
    found = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0].strip().upper()
        if text:
            found.add(text)
    return sorted(found)


def csv_name(ticker: str) -> str:
    """The CSV file name the yfinance cache uses for a ticker."""
    from swingbot.core.marketdata.backtest_cache import cache_path
    return cache_path(ticker).name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_hash(files: dict[str, str]) -> str:
    text = "\n".join(f"{name}:{sha}" for name, sha in sorted(files.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sources(src: Path, tickers) -> list[Path]:
    if tickers is None:
        return sorted(src.glob("*.csv"))
    paths = [src / csv_name(t) for t in tickers]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"not in {src}: {', '.join(missing)}")
    return paths


def _copy(path: Path, target: Path, start: str | None) -> None:
    if start is None:
        shutil.copyfile(path, target)
        return
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame = frame[frame.index >= pd.Timestamp(start)]
    frame.to_csv(target, index_label=frame.index.name or "Date")


def snapshot(src, out, *, start: str | None = None, tickers=None,
             now: datetime | None = None) -> dict:
    """Copy the cache (all CSVs, or exactly `tickers`) into `out` and hash it."""
    src, out = Path(src), Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} exists and is not empty; a snapshot is never overwritten")
    paths = _sources(src, tickers)
    out.mkdir(parents=True, exist_ok=True)
    for path in paths:
        _copy(path, out / path.name, start)
    files = {p.name: _sha256(out / p.name) for p in paths}
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {"src": str(src), "start": start, "created_at": stamp,
                "files": files, "hash": combined_hash(files)}
    (out / HASHES_FILE).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")
    return manifest


def verify(out) -> list[str]:
    """One problem line per changed, missing or extra file; [] when intact."""
    out = Path(out)
    hashes = out / HASHES_FILE
    if not hashes.is_file():
        return [f"MISSING {HASHES_FILE}"]
    manifest = json.loads(hashes.read_text(encoding="utf-8"))
    problems = []
    for name, sha in sorted(manifest["files"].items()):
        path = out / name
        if not path.is_file():
            problems.append(f"MISSING {name}")
        elif _sha256(path) != sha:
            problems.append(f"CHANGED {name}")
    problems += [f"EXTRA {p.name}" for p in sorted(out.glob("*.csv"))
                 if p.name not in manifest["files"]]
    if combined_hash(manifest["files"]) != manifest.get("hash"):
        problems.append("HASH top-level hash does not match the file list")
    return problems


def intersection_tickers(watchlist, manifest: dict | None, cache_dir) -> list[str]:
    """Watchlist tickers that are 'ok' in the store's daily manifest AND cached."""
    entries = (manifest or {}).get("tickers") or {}
    ok = {t for t, e in entries.items() if (e or {}).get("status") == "ok"}
    wanted = {w.strip().upper() for w in watchlist if w.strip()}
    return sorted(t for t in wanted
                  if t in ok and (Path(cache_dir) / csv_name(t)).is_file())


def _iso_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=None, help="the yfinance cache to copy")
    ap.add_argument("--out", type=Path, default=None, help="the snapshot directory (must not exist)")
    ap.add_argument("--start", type=_iso_date, default=None, help="drop rows before this date")
    ap.add_argument("--tickers-file", type=Path, default=None,
                    help="copy exactly these tickers (plus the market benchmark)")
    ap.add_argument("--verify", type=Path, default=None, metavar="DIR",
                    help="check a snapshot against its _hashes.json")
    ap.add_argument("--intersect-out", type=Path, default=None, metavar="PATH",
                    help="write the §5 ticker set (needs --watchlist-file and --src)")
    ap.add_argument("--watchlist-file", type=Path, default=None)
    return ap.parse_args(argv)


def _run_verify(args) -> int:
    problems = verify(args.verify)
    for line in problems:
        print(line)
    print(f"verify: {len(problems)} problem(s) in {args.verify}")
    return 1 if problems else 0


def _run_intersect(args) -> int:
    if not (args.src and args.watchlist_file):
        raise ValueError("--intersect-out needs --watchlist-file and --src")
    from swingbot.core.marketdata import history_store
    tickers = intersection_tickers(read_tickers_file(args.watchlist_file),
                                   history_store.require_manifest("daily"), args.src)
    if not tickers:
        raise ValueError("the intersection is empty")
    args.intersect_out.write_text("\n".join(tickers) + "\n", encoding="utf-8")
    print(f"intersection: {len(tickers)} ticker(s) -> {args.intersect_out}")
    return 0


def _run_snapshot(args) -> int:
    if not (args.src and args.out):
        raise ValueError("a snapshot needs --src and --out")
    tickers = None
    if args.tickers_file:
        from swingbot import config
        tickers = sorted(set(read_tickers_file(args.tickers_file))
                         | {str(config.MARKET_REGIME_TICKER).upper()})
    manifest = snapshot(args.src, args.out, start=args.start, tickers=tickers)
    print(f"snapshot: {len(manifest['files'])} file(s) -> {args.out} hash {manifest['hash']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.verify:
            return _run_verify(args)
        if args.intersect_out:
            return _run_intersect(args)
        return _run_snapshot(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`history_store.MissingStoreError` is a `RuntimeError`, so a missing store is exit 1 with the path in the message (the test checks `_manifest.json` appears).

- [ ] **Step 4: Add `--tickers-file` to `run_backtest_range.py`**

Use the Edit tool (guardrail note in the part header). Four edits, each anchored on existing text.

(a) Replace the whole `_tickers_for_run` function with:

```python
def _tickers_from_file(path: str) -> list[str]:
    """v162 §5: an explicit ticker list (one per line, '#' comments), so every
    leg of a comparison runs on the same set, whatever the watchlist holds."""
    from snapshot_backtest_cache import read_tickers_file
    tickers = read_tickers_file(path)
    if not tickers:
        raise SystemExit(f"error: --tickers-file {path} names no ticker")
    return tickers


def _tickers_for_run(universe: str | None, tickers_file: str | None = None) -> list:
    """Ticker set for the scan: a named universe (e.g. 'etfs', Task E80)
    when given, else the watchlist -- same override seam as
    backtest_wf._symbols_for_folds/run_folds' tickers= param. v162: an
    explicit --tickers-file replaces both and cannot be combined with a universe."""
    if tickers_file:
        if universe:
            raise SystemExit("error: --tickers-file and --universe are exclusive")
        return _tickers_from_file(tickers_file)
    if universe:
        from swingbot.core.marketdata.universe import universe_symbols
        return sorted(universe_symbols(universe))
    return sorted(load_watchlist())
```

(`scripts/data` is already on `sys.path` at the top of the script, which is how `fetch_backtest_data` is imported.)

(b) In `run_scenario_mode`, change the signature's last line from `record_blocked=None):` to `record_blocked=None, tickers_file=None):`, and its first statement from `tickers = _tickers_for_run(universe)` to `tickers = _tickers_for_run(universe, tickers_file)`.

(c) In `main`, directly after the `--universe` `add_argument(...)` call (it ends with `"swingbot.core.marketdata.universe.universe_symbols, instead of the watchlist")`), add:

```python
    ap.add_argument("--tickers-file", dest="tickers_file", default=None,
                    help="v162: run exactly the tickers listed in this file (one per line, "
                         "'#' comments) instead of the watchlist; exclusive with --universe")
```

In the `if args.scenarios:` call, change `record_blocked=args.record_blocked)` to `record_blocked=args.record_blocked, tickers_file=args.tickers_file)`.

(d) In the normal mode, change `tickers = _tickers_for_run(args.universe)` to `tickers = _tickers_for_run(args.universe, args.tickers_file)`.

None of these adds a branch to `main` or `run_scenario_mode`.

- [ ] **Step 5: Write the report script**

Create `$WT/scripts/reports/v162_rebaseline_report.py`:

```python
"""v162 §5: the three-leg re-baseline report for one window.

Each leg is one or more `run_backtest_range.py --trades-jsonl` files, each with
its provenance sidecar (<file>.provenance.json):
  a  yfinance, full history     (BACKTEST_CACHE_DIR = the v162 snapshot)
  b  yfinance from 2016-01-01   (BACKTEST_CACHE_DIR = the truncated snapshot)
  c  the Alpaca SIP store       (--data-source alpaca)
a -> b isolates the shorter warm-up, b -> c the vendor. Every ExpR and win-rate
difference carries its paired week-clustered bootstrap 95% interval. These
numbers describe a data change. They are never a lift and select nothing.

  python scripts/reports/v162_rebaseline_report.py --leg a=A.jsonl --leg b=B.jsonl \\
      --leg c=C.jsonl --window train --out rebaseline.json [--md train.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402

LEG_SOURCES = {"a": "yfinance", "b": "yfinance", "c": "alpaca"}
LEG_NAMES = {"a": "yfinance, full history", "b": "yfinance from 2016-01-01",
             "c": "Alpaca SIP store"}
COMPARISONS = (("a", "b", "warm-up"), ("b", "c", "vendor"), ("a", "c", "total"))
WINDOWS = {"train": ("2020-01-01", "2023-12-31"), "fold-train": ("2018-06-01", "2022-12-31")}
CLOSED = ("win", "loss", "scratch", "timeout")
SNAPSHOT_HASHES = "_hashes.json"
TOP_TICKERS = 15


@dataclass(frozen=True)
class Trade:
    ticker: str
    strategy: str
    entry_date: str
    outcome: str
    r_multiple: float


def parse_leg(text: str) -> tuple[str, list[Path]]:
    label, sep, paths = text.partition("=")
    label = label.strip().lower()
    files = [Path(p.strip()) for p in paths.split(",") if p.strip()]
    if not sep or label not in LEG_SOURCES or not files:
        raise argparse.ArgumentTypeError(f"--leg wants a|b|c=PATH[,PATH...], got {text!r}")
    return label, files


def _trade(row: dict, path: Path) -> Trade:
    r = row.get("r_multiple")
    if r is None:
        raise ValueError(f"{path}: closed trade without r_multiple "
                         f"({row.get('ticker')} {row.get('entry_date')})")
    return Trade(str(row["ticker"]), str(row["strategy"]), str(row["entry_date"])[:10],
                 str(row["outcome"]), float(r))


def load_trades(paths: list[Path]) -> list[Trade]:
    """Every closed trade of a leg's files (other outcomes are not trades)."""
    trades: list[Trade] = []
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        trades += [_trade(row, path) for row in rows if row.get("outcome") in CLOSED]
    return trades


def _sidecar(path: Path) -> dict:
    side = training_data.provenance_path(path)
    if not side.is_file():
        raise ValueError(f"{path}: no provenance sidecar {side.name}; "
                         f"re-run the leg with the v162 runner")
    return json.loads(side.read_text(encoding="utf-8"))


def _snapshot_hash(prov: dict) -> str | None:
    hashes = Path(prov.get("store_dir") or "") / SNAPSHOT_HASHES
    if not hashes.is_file():
        return None
    return json.loads(hashes.read_text(encoding="utf-8")).get("hash")


def load_provenance(label: str, paths: list[Path]) -> dict:
    """The leg's provenance: one for all its files, of the leg's fixed source;
    a yfinance leg must read a hashed snapshot."""
    provs = [_sidecar(Path(p)) for p in paths]
    if any(p != provs[0] for p in provs[1:]):
        raise ValueError(f"leg {label}: its files disagree on provenance")
    prov = dict(provs[0])
    want = LEG_SOURCES[label]
    if prov.get("data_source") != want:
        raise ValueError(f"leg {label} must be {want}, its sidecar says "
                         f"{prov.get('data_source')!r}")
    if want == "yfinance":
        prov["snapshot_hash"] = _snapshot_hash(prov)
        if prov["snapshot_hash"] is None:
            raise ValueError(f"leg {label}: {prov.get('store_dir')} is not a v162 snapshot "
                             f"(no {SNAPSHOT_HASHES})")
    return prov


def _check_window(label: str, trades: list[Trade], window: str) -> None:
    lo, hi = WINDOWS[window]
    outside = [t for t in trades if not lo <= t.entry_date <= hi]
    if outside:
        raise ValueError(f"leg {label}: {len(outside)} trade(s) outside {window} {lo}..{hi}, "
                         f"first {outside[0].entry_date}")


def _evaluated(trades: list[Trade]) -> list[Trade]:
    return [t for t in trades if t.outcome in ("win", "loss")]


def win_rate(trades: list[Trade]) -> float | None:
    """Wins over win+loss, in percent (run_backtest_range.pool)."""
    ev = _evaluated(trades)
    return 100.0 * sum(t.outcome == "win" for t in ev) / len(ev) if ev else None


def expectancy(trades: list[Trade]) -> float | None:
    """Mean R over every closed trade (run_backtest_range.pool)."""
    return float(np.mean([t.r_multiple for t in trades])) if trades else None


def leg_stats(trades: list[Trade]) -> dict:
    ev = _evaluated(trades)
    return {"trades": len(trades), "n_eval": len(ev), "wins": sum(t.outcome == "win" for t in ev),
            "win_rate": win_rate(trades), "expectancy_r": expectancy(trades),
            "tickers": len({t.ticker for t in trades})}


def _delta(metric):
    def statistic(base, comp):
        b, c = metric(base), metric(comp)
        return None if b is None or c is None else c - b
    return statistic


def difference(base: list[Trade], comp: list[Trade], metric, *, n_resamples: int,
               seed: int = stats.WEEK_BOOTSTRAP_SEED) -> dict:
    """comp minus base, with the paired week-clustered bootstrap 95% interval."""
    draws = stats.week_cluster_bootstrap(base, comp, _delta(metric),
                                         n_resamples=n_resamples, seed=seed)
    ci = ([float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]
          if draws.size else None)
    return {"point": _delta(metric)(base, comp), "ci95": ci, "draws": int(draws.size)}


def ticker_counts(legs: dict[str, list[Trade]]) -> dict[str, dict[str, int]]:
    counts = {label: Counter(t.ticker for t in trades) for label, trades in legs.items()}
    names = sorted(set().union(*counts.values())) if counts else []
    return {name: {label: counts[label][name] for label in sorted(legs)} for name in names}


def build_report(legs: dict[str, list[Trade]], provenance: dict[str, dict], window: str, *,
                 n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
                 seed: int = stats.WEEK_BOOTSTRAP_SEED) -> dict:
    for label, trades in legs.items():
        _check_window(label, trades, window)
    comparisons = [{"base": base, "comp": comp, "what": what,
                    "expectancy_r": difference(legs[base], legs[comp], expectancy,
                                               n_resamples=n_resamples, seed=seed),
                    "win_rate": difference(legs[base], legs[comp], win_rate,
                                           n_resamples=n_resamples, seed=seed)}
                   for base, comp, what in COMPARISONS]
    lo, hi = WINDOWS[window]
    return {"window": window, "from": lo, "to": hi, "n_resamples": n_resamples, "seed": seed,
            "legs": {label: {"name": LEG_NAMES[label], **leg_stats(legs[label]),
                             "provenance": provenance[label]} for label in sorted(legs)},
            "comparisons": comparisons, "per_ticker": ticker_counts(legs)}


def _fmt(value, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def _ci(diff: dict, spec: str) -> str:
    if diff["ci95"] is None:
        return "n/a"
    return f"{format(diff['ci95'][0], spec)}..{format(diff['ci95'][1], spec)}"


def _sentence(report: dict, cmp: dict) -> str:
    base, comp = report["legs"][cmp["base"]], report["legs"][cmp["comp"]]
    span = f"window {report['window']} {report['from']}..{report['to']}"
    e, w = cmp["expectancy_r"], cmp["win_rate"]
    return (f"- {cmp['what']} ({cmp['base']} -> {cmp['comp']}): ExpR {_fmt(e['point'], '+.3f')} R "
            f"(week-clustered 95% CI {_ci(e, '+.3f')}), {span}, "
            f"N {base['trades']} -> {comp['trades']} trades; win rate "
            f"{_fmt(w['point'], '+.1f')} pp (95% CI {_ci(w, '+.1f')}), {span}, "
            f"N {base['n_eval']} -> {comp['n_eval']} win+loss.")


def _leg_row(label: str, leg: dict) -> str:
    prov = leg["provenance"]
    digest = prov.get("snapshot_hash") or prov.get("manifest_hash") or "-"
    wr = "n/a" if leg["win_rate"] is None else f"{leg['win_rate']:.1f}%"
    return (f"| {label} | {leg['name']} | {leg['trades']} | {leg['n_eval']} | {wr} | "
            f"{_fmt(leg['expectancy_r'], '+.3f')} | {leg['tickers']} | `{str(digest)[:12]}` |")


def _ticker_rows(per_ticker: dict) -> list[str]:
    def change(item):
        name, n = item
        return (-abs(n.get("c", 0) - n.get("a", 0)), name)
    rows = sorted(per_ticker.items(), key=change)[:TOP_TICKERS]
    return [f"| {name} | {n.get('a', 0)} | {n.get('b', 0)} | {n.get('c', 0)} | "
            f"{n.get('c', 0) - n.get('a', 0):+d} |" for name, n in rows]


def render_markdown(report: dict) -> str:
    lines = [f"### Window {report['window']} ({report['from']}..{report['to']})", "",
             "| leg | data | trades | win+loss | win rate | ExpR | tickers traded | input hash |",
             "|---|---|---|---|---|---|---|---|"]
    lines += [_leg_row(label, leg) for label, leg in report["legs"].items()]
    lines += ["", "These differences describe a data change; each is not a lift and selects "
                  "nothing.", ""]
    lines += [_sentence(report, cmp) for cmp in report["comparisons"]]
    lines += ["", f"Largest per-ticker trade-count changes, a -> c (top {TOP_TICKERS}):", "",
              "| ticker | a | b | c | c - a |", "|---|---|---|---|---|"]
    lines += _ticker_rows(report["per_ticker"])
    return "\n".join(lines) + "\n"


def merge_into(out: Path, report: dict) -> None:
    """Add (or replace) this window's block in the JSON at `out`."""
    out = Path(out)
    doc = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    doc.setdefault("windows", {})[report["window"]] = report
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", type=parse_leg, action="append", required=True)
    ap.add_argument("--window", choices=sorted(WINDOWS), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--md", type=Path, default=None, help="also write the markdown section here")
    ap.add_argument("--resamples", type=int, default=stats.WEEK_BOOTSTRAP_RESAMPLES)
    args = ap.parse_args(argv)
    labels = [label for label, _ in args.leg]
    if sorted(labels) != ["a", "b", "c"]:
        ap.error(f"give --leg a=, b= and c= exactly once each (got {labels})")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        legs = {label: load_trades(paths) for label, paths in args.leg}
        provenance = {label: load_provenance(label, paths) for label, paths in args.leg}
        report = build_report(legs, provenance, args.window, n_resamples=args.resamples)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    merge_into(args.out, report)
    markdown = render_markdown(report)
    if args.md:
        args.md.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The test `test_markdown_puts_difference_interval_window_and_n_in_one_sentence` reads the line starting `- total`; `test_differences_carry_paired_week_clustered_intervals` expects `[0.0, 0.0]` for two identical legs (every paired draw is 0).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_rebaseline.py`
Expected: PASS, 0 failed.

- [ ] **Step 7: Neighbours, complexity**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_rbr_data_source.py`
Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_emit_registry.py`
Expected: both 0 failed (AH11's switch and the registry writer are untouched by the ticker-list change).

Run: `python -m radon cc -s -n C $WT/scripts/data/snapshot_backtest_cache.py $WT/scripts/reports/v162_rebaseline_report.py $WT/scripts/backtest/run_backtest_range.py`
Expected: only the legacy `run_backtest_range` entries (`main` F, `run_scenario_mode` C, `pool` C), each at the score it had at the task's base commit; nothing from the two new files.

Check the new snapshot directories stay out of git (AH19 added the pattern `data/backtest_cache_snapshot_v162*/`):

Run: `git -C $WT check-ignore -v data/backtest_cache_snapshot_v162/AAPL.csv data/backtest_cache_snapshot_v162_from2016/AAPL.csv`
Expected: both paths reported against that `.gitignore` line.

- [ ] **Step 8: Commit**

```bash
git -C $WT add scripts/data/snapshot_backtest_cache.py scripts/reports/v162_rebaseline_report.py scripts/backtest/run_backtest_range.py tests/history_store/test_rebaseline.py
git -C $WT commit -m "feat(v162): AH23 re-baseline tooling -- hashed cache snapshot, --tickers-file, three-leg week-clustered report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows no tracked change.

