# v162 Alpaca history store, part 5b: §5 re-baseline runs, full suite, merge, deploy, cron

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH24:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_5b-rebaseline-runs-close.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (§5 re-baseline, § Research discipline, Acceptance 5–8, Panel review quant-engineer "§5 not reproducible", quant-researcher "§5 must not change the source choice", "§5 differences need week-clustered intervals")
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts and the task ledger. Every task below implicitly includes them. Ledger part 5 outgrew the 1500-line cap: AH21–AH23 are in [`2026-10-15-v162-alpaca-history-store_5-production-rebaseline.md`](2026-10-15-v162-alpaca-history-store_5-production-rebaseline.md), AH24 and AH25 are here.

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = `E:/Documents/Private/Projects/Discord-Bot` (the main tree). Never `cd`; use `git -C $WT` and absolute paths.
- `$RUNS` = `E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_snapshot_v162_runs`: the §5 run outputs (watchlist, ticker set, trades, sidecars). The name matches AH19's `.gitignore` pattern `data/backtest_cache_snapshot_v162*/` on purpose, so nothing there can be committed by accident; `data/` as a whole is not ignored.
- **Production commands (AH24 Step 2–3 read only; AH25 Steps 5–9 change production)** go through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"` only, with multi-line scripts on stdin, and never a `$(...)` inside the quoted remote command (the WSL hop expands it locally). AH25 asks the partner with `AskUserQuestion` before its first production change and runs in the main session, never in a subagent.
- **The worktree has no store and a 3-ticker watchlist.** Every §5 run reads the main tree's data explicitly: `HISTORY_STORE_DIR=$R/data/market_data`, `BACKTEST_CACHE_DIR=<absolute snapshot dir>`, `--tickers-file $RUNS/tickers.txt`.
- **Guardrail.** `.claude/hooks/guardrails.py` `_rule_closed_preregistration` denies a Bash command that names `run_backtest_range.py` or `tune_strategy.py` together with a closed knob name, and that list includes the literal registry status word for a passing row. No command below does that, and none adds `--emit-registry`, `--pass-wr` or `--validation`.
- **Research discipline (binding).** §5 describes a data change. No number from it is a lift, none selects a component, none is read on the VALIDATION window, and none reopens a closed pre-registration (v122, v127, v129, v135, v139, v143). If the Alpaca leg comes out worse, the source stays Alpaca: there is no switch back and no per-ticker or per-strategy source choice. Every ExpR and win-rate difference is written with its week-clustered 95% interval, window and N in the same sentence.

# Phase F (end): re-baseline runs, final gate, merge, deploy, cron

### Task AH24: §5 three legs × two windows, results doc, leg (a) reproduction

**Model:** opus — six long backtests whose only value is that they differ in the data alone; the task freezes inputs, holds config and tickers fixed across legs, and writes numbers that must never read as a lift.

**Files:**
- Create: `$WT/docs/superpowers/results/<run-day>-v162-rebaseline.md` and `$WT/docs/superpowers/results/<run-day>-v162-rebaseline.json`, where `<run-day>` is the UTC date of the first leg run. The ledger names them `2026-10-15-v162-rebaseline.{md,json}`; rename the date, keep the rest.
- Local data only (gitignored): `$R/data/backtest_cache_snapshot_v162/`, `$R/data/backtest_cache_snapshot_v162_from2016/`, `$RUNS/`.

**Interfaces:**
- Consumes (AH23): `python $WT/scripts/data/snapshot_backtest_cache.py --src DIR --out DIR [--start YYYY-MM-DD] [--tickers-file PATH]` (adds `config.MARKET_REGIME_TICKER` to a ticker list; refuses a non-empty `--out`; prints `snapshot: <n> file(s) -> <out> hash <sha>`), `--verify DIR` (prints `verify: <n> problem(s) in <DIR>`, exit 1 on any), `--intersect-out PATH --watchlist-file PATH --src DIR` (prints `intersection: <n> ticker(s) -> <PATH>`; reads the store manifest through `HISTORY_STORE_DIR`); `run_backtest_range.py --tickers-file PATH`; `python $WT/scripts/reports/v162_rebaseline_report.py --leg a=PATH --leg b=PATH --leg c=PATH --window {train,fold-train} --out PATH [--md PATH]` (a leg may be a comma list of chunk files with identical sidecars).
- Consumes (AH10, AH11): `run_backtest_range.py --data-source {alpaca,yfinance}`, the `<out>.provenance.json` sidecar next to `--json` and `--trades-jsonl`, the start-of-run line `training data: <source> (<n> excluded)`, the hard error naming the missing manifest path; `BACKTEST_CACHE_DIR` is read once at import (`backtest_cache.py:45`) and, when set, makes `None` resolve to `yfinance`.
- Consumes (AH21, AH22): the pulled store at `$R/data/market_data/` and its daily manifest hash (in the backfill results doc).
- Produces (ledger AH24): the committed re-baseline doc and JSON (Acceptance 5 and 7).

**What stays fixed across the three legs (the point of §5):**
- **Code and config:** one commit (`git -C $WT rev-parse HEAD`, recorded), one `.env` (`$WT/.env`), the same command flags. Only the data differs: `BACKTEST_CACHE_DIR` and `--data-source`.
- **Tickers:** `--tickers-file $RUNS/tickers.txt` on every run: the VM watchlist's tickers that are `ok` in the Alpaca store and cached in `data/backtest_cache/`. SPY is in each snapshot for market context (the Alpaca store holds it too, AH21 Step 8 gate).
- **Inputs:** both yfinance snapshots are hashed and re-verified after the last run; the Alpaca leg reads the store at the manifest hash AH22 recorded.
- **Sector context:** neither source holds the sector ETFs (AH21 Step 9 measured it), so `_build_asof_map` loads none in any leg.

**Long runs:** each run is one `run_backtest_range.py` process over every strategy. Dispatch each to the `backtest-runner` agent (`run_in_background`), **at most 2 at once**, and wait for its notification; never poll its output. If a run would exceed the agent's limits, chunk it per strategy (`--strategy <S>`, one `--json`/`--trades-jsonl` pair per chunk named `<leg>_<window>_<S>.*`) and give the report the comma list of that leg's chunk files. Every run writes `backtest_range_summary.txt` into the working directory (gitignored, `.gitignore:93`); it is not an input to anything here, and two concurrent runs overwrite it harmlessly.

- [ ] **Step 0: Load the backtest gate**

Invoke the `backtest-gate` skill before the first command, and follow it. Its checks apply here as written: TRAIN and the fold-train window only, no `--validation`, no registry write, no closed component re-measured as a hypothesis (§5 measures a data change, it tests no component).

- [ ] **Step 1: Preconditions and the config the legs share**

```bash
git -C $WT status --short
git -C $WT log --oneline -4
git -C $WT rev-parse HEAD
ls $R/data/market_data/daily/_manifest.json $R/data/backtest_cache/SPY.csv
mkdir -p $RUNS
PYTHONPATH=$WT python -c "from swingbot import config; print('PLAN_ENGINE_V2', config.PLAN_ENGINE_V2); print('SCALE_OUT_ENABLED', config.SCALE_OUT_ENABLED); print('TRAINING_DATA_SOURCE', config.TRAINING_DATA_SOURCE); print('MARKET_REGIME_TICKER', config.MARKET_REGIME_TICKER)"
```

Expected: a clean status; AH22 and AH23 are the latest commits; both files exist; the config prints. Record the SHA.

Read the live values on the VM (read only):

```bash
bash $R/scripts/ops/ssh-hetzner.sh "grep -E '^(PLAN_ENGINE_V2|SCALE_OUT_ENABLED|MARKET_REGIME_TICKER)=' /opt/swing-bot/.env"
```

The legs run "the current live config" (spec §5): `PLAN_ENGINE_V2=true` on the VM means `--exit-model v2`, otherwise `--exit-model v1`; `SCALE_OUT_ENABLED=true` adds `--scale-out` (with v2 only). Write the chosen flags once as `EXIT_FLAGS` (for example `--exit-model v2 --scale-out`) and use exactly them on all six runs. If the VM's values differ from what `$WT`'s config printed, the flags still follow the VM; record both in the results doc. `--frictions on`, `--context on` and `--tp2 levels` stay at their defaults on every run.

- [ ] **Step 2: The VM watchlist (read only)**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" > $RUNS/watchlist.txt <<'PY'
from swingbot.core.marketdata.watchlist import load_watchlist
print("\n".join(sorted(load_watchlist())))
PY
wc -l $RUNS/watchlist.txt
head -3 $RUNS/watchlist.txt
```

Expected: one ticker per line, the same count as the watchlist the backfill used (AH21's daily manifest holds that count plus SPY when SPY is not on the watchlist). `exec` here only reads one table in the running bot.

- [ ] **Step 3: The shared ticker set**

```bash
HISTORY_STORE_DIR=$R/data/market_data python $WT/scripts/data/snapshot_backtest_cache.py --intersect-out $RUNS/tickers.txt --watchlist-file $RUNS/watchlist.txt --src $R/data/backtest_cache
comm -23 <(sort $RUNS/watchlist.txt) <(sort $RUNS/tickers.txt)
```

Expected: `intersection: <n> ticker(s) -> .../tickers.txt`. The `comm` output lists the watchlist tickers left out; each one is either not `ok` in the store (its AH21 status) or has no CSV in the dev cache. Record each with its reason in the results doc. If more than a handful of tickers lack a dev CSV, stop and ask the partner whether to refresh the dev cache first (`python scripts/data/fetch_backtest_data.py`, network) before the snapshot freezes it.

- [ ] **Step 4: Freeze the two yfinance snapshots**

```bash
python $WT/scripts/data/snapshot_backtest_cache.py --src $R/data/backtest_cache --out $R/data/backtest_cache_snapshot_v162 --tickers-file $RUNS/tickers.txt
python $WT/scripts/data/snapshot_backtest_cache.py --src $R/data/backtest_cache --out $R/data/backtest_cache_snapshot_v162_from2016 --tickers-file $RUNS/tickers.txt --start 2016-01-01
python $WT/scripts/data/snapshot_backtest_cache.py --verify $R/data/backtest_cache_snapshot_v162
python $WT/scripts/data/snapshot_backtest_cache.py --verify $R/data/backtest_cache_snapshot_v162_from2016
head -2 $R/data/backtest_cache_snapshot_v162_from2016/SPY.csv
git -C $R status --short
```

Expected: two `snapshot: <n+1> file(s)` lines (the ticker set plus SPY when SPY is not in it) with their hashes (record both); `verify: 0 problem(s)` twice; the truncated SPY file's first data row is the first session of 2016 (`2016-01-04`); `git status` lists no snapshot path.

- [ ] **Step 5: The six runs**

Each line below is one `backtest-runner` dispatch. Replace `EXIT_FLAGS` with Step 1's flags; nothing else changes between legs except the data selection. `env -u` makes sure no inherited variable leaks into a leg.

Leg (a), yfinance, full history:

```bash
env -u HISTORY_STORE_DIR BACKTEST_CACHE_DIR=$R/data/backtest_cache_snapshot_v162 python $WT/scripts/backtest/run_backtest_range.py --train --data-source yfinance --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/a_train.json --trades-jsonl $RUNS/a_train.jsonl
env -u HISTORY_STORE_DIR BACKTEST_CACHE_DIR=$R/data/backtest_cache_snapshot_v162 python $WT/scripts/backtest/run_backtest_range.py --from 2018-06-01 --to 2022-12-31 --data-source yfinance --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/a_fold.json --trades-jsonl $RUNS/a_fold.jsonl
```

Leg (b), yfinance from 2016-01-01:

```bash
env -u HISTORY_STORE_DIR BACKTEST_CACHE_DIR=$R/data/backtest_cache_snapshot_v162_from2016 python $WT/scripts/backtest/run_backtest_range.py --train --data-source yfinance --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/b_train.json --trades-jsonl $RUNS/b_train.jsonl
env -u HISTORY_STORE_DIR BACKTEST_CACHE_DIR=$R/data/backtest_cache_snapshot_v162_from2016 python $WT/scripts/backtest/run_backtest_range.py --from 2018-06-01 --to 2022-12-31 --data-source yfinance --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/b_fold.json --trades-jsonl $RUNS/b_fold.jsonl
```

Leg (c), the Alpaca store. The TRAIN run carries **no** `--data-source`: it is Acceptance 5's "with no flag it reads the Alpaca store and stamps provenance" (valid only while `$WT/.env` leaves `TRAINING_DATA_SOURCE` at its default `alpaca`, which Step 1 printed):

```bash
env -u BACKTEST_CACHE_DIR HISTORY_STORE_DIR=$R/data/market_data python $WT/scripts/backtest/run_backtest_range.py --train --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/c_train.json --trades-jsonl $RUNS/c_train.jsonl
env -u BACKTEST_CACHE_DIR HISTORY_STORE_DIR=$R/data/market_data python $WT/scripts/backtest/run_backtest_range.py --from 2018-06-01 --to 2022-12-31 --data-source alpaca --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/c_fold.json --trades-jsonl $RUNS/c_fold.jsonl
```

For each run, the agent reports: the `training data: ...` line (yfinance legs `(0 excluded)`; leg c `alpaca (<n> excluded)` where no excluded ticker is in `tickers.txt`), any `excluded (illiquid|bad data)` lines, the pooled table, and that both sidecars exist (`$RUNS/<leg>_<window>.json.provenance.json` and `.jsonl.provenance.json`). A traceback, a missing sidecar or a `WARNING: SPY is not in the backtest cache` line fails the run: fix the cause, then rerun only that run.

- [ ] **Step 6: The store refuses to run without its manifest (Acceptance 5)**

```bash
env -u BACKTEST_CACHE_DIR HISTORY_STORE_DIR=$R/data/no_store_here python $WT/scripts/backtest/run_backtest_range.py --train --strategy RSI --tickers-file $RUNS/tickers.txt; echo "exit $?"
```

Expected: a non-zero exit within seconds, with `error:` and the path `.../no_store_here/daily/_manifest.json` in the message; no backtest runs.

- [ ] **Step 7: Reproduce leg (a)**

Run leg (a)'s TRAIN command again into new files (one more `backtest-runner` dispatch):

```bash
env -u HISTORY_STORE_DIR BACKTEST_CACHE_DIR=$R/data/backtest_cache_snapshot_v162 python $WT/scripts/backtest/run_backtest_range.py --train --data-source yfinance --tickers-file $RUNS/tickers.txt EXIT_FLAGS --json $RUNS/a_train_repro.json --trades-jsonl $RUNS/a_train_repro.jsonl
```

Then compare:

```bash
python -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); print('json equal', a == b)" $RUNS/a_train.json $RUNS/a_train_repro.json
sha256sum $RUNS/a_train.jsonl $RUNS/a_train_repro.jsonl
python $WT/scripts/data/snapshot_backtest_cache.py --verify $R/data/backtest_cache_snapshot_v162
python $WT/scripts/data/snapshot_backtest_cache.py --verify $R/data/backtest_cache_snapshot_v162_from2016
```

Expected: `json equal True`, two equal SHA-256 sums, and `verify: 0 problem(s)` twice (the snapshots did not move during the runs). If the trades files differ but the JSON is equal, compare sorted lines (`sort $RUNS/a_train.jsonl | sha256sum` and the same for the repro) and record which held; a difference in the pooled JSON is a reproducibility bug and stops the task.

- [ ] **Step 8: The report, both windows**

```bash
python $WT/scripts/reports/v162_rebaseline_report.py --leg a=$RUNS/a_train.jsonl --leg b=$RUNS/b_train.jsonl --leg c=$RUNS/c_train.jsonl --window train --out $WT/docs/superpowers/results/<run-day>-v162-rebaseline.json --md $RUNS/train.md
python $WT/scripts/reports/v162_rebaseline_report.py --leg a=$RUNS/a_fold.jsonl --leg b=$RUNS/b_fold.jsonl --leg c=$RUNS/c_fold.jsonl --window fold-train --out $WT/docs/superpowers/results/<run-day>-v162-rebaseline.json --md $RUNS/fold.md
```

Expected: exit 0 twice; the JSON holds `windows.train` and `windows.fold-train`; each markdown section has the legs table, three comparison sentences and the per-ticker table. Exit 1 names the problem (a wrong-source leg, an unhashed snapshot, a trade outside the window): fix the input, never the check.

- [ ] **Step 9: Write the results doc**

Create `$WT/docs/superpowers/results/<run-day>-v162-rebaseline.md` with the Write tool. Paste the two generated sections verbatim from `$RUNS/train.md` and `$RUNS/fold.md`; fill every other `<...>` from the steps above. Describe; do not interpret a difference as better or worse strategy behaviour.

```markdown
# v162 §5 re-baseline: yfinance vs the Alpaca history store (<run-day>)

**Spec:** [v162 design §5](../specs/2026-10-15-v162-alpaca-history-store-design.md) · **Plan:** [v162 index](../plans/2026-10-15-v162-alpaca-history-store_0-index.md), task AH24
**Edge:** none (integrity). These numbers describe a data change. None of them is a lift, none selects a component, and none changes the source: training stays on Alpaca whatever they show (spec § Research discipline).

## Inputs

- Code: branch `2026-10-15-v162-alpaca-history-store` at `<sha>`; config from `$WT/.env`; live flags on the VM `PLAN_ENGINE_V2=<v>`, `SCALE_OUT_ENABLED=<v>` -> every run used `<EXIT_FLAGS>`, `--frictions on`, `--context on`, `--tp2 levels`.
- Tickers: <n> on every leg, the VM watchlist ∩ `ok` in the Alpaca store ∩ cached by yfinance: <comma list>. Left out: <ticker: reason, ...>.
- Leg a: `data/backtest_cache_snapshot_v162/`, snapshot hash `<hash>` (<n> files, SPY included for market context).
- Leg b: `data/backtest_cache_snapshot_v162_from2016/` (rows before 2016-01-01 dropped), snapshot hash `<hash>`.
- Leg c: `data/market_data/` daily manifest hash `<hash>` (feed `sip`, adjustment `all`), pulled by AH22.
- Sector ETFs: in neither source (AH21 Step 9), so sector-relative context is equally thin in every leg.
- Intervals: paired week-clustered bootstrap (`stats.week_cluster_bootstrap`), 10,000 resamples, seed 42, 2.5th–97.5th percentiles.

## Results

<paste $RUNS/train.md>

<paste $RUNS/fold.md>

## Reproducibility (Acceptance 5)

- Leg a, TRAIN, run twice on the frozen snapshot: pooled JSON equal: <True>; trades files <byte-identical / identical after sorting>.
- Both snapshots re-verified after the last run: 0 problems.
- Leg c TRAIN ran with no `--data-source`; its sidecar says `alpaca` with manifest hash `<hash>`.
- With `HISTORY_STORE_DIR` pointing at a directory without a store, the runner stopped with `<error line>`.

## What this does not license

- No VALIDATION budget is reset by the new source; 2024–2025 stays tainted for every selection decision.
- Closed pre-registrations (v122, v127, v129, v135, v139, v143) stay closed on Alpaca bars.
- No per-ticker or per-strategy source choice follows from the per-ticker table.
- Each new pre-registration names its `data_source` before TRAIN is read.
```

- [ ] **Step 10: Commit**

```bash
git -C $WT add docs/superpowers/results/<run-day>-v162-rebaseline.md docs/superpowers/results/<run-day>-v162-rebaseline.json
git -C $WT commit -m "docs(v162): AH24 three-leg two-window re-baseline (a data change, not a lift), leg a reproduced

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows no tracked change. Tell the partner, in at most three lines, the TRAIN-window total (a -> c) ExpR and win-rate differences, each with its interval, window and N, and that the source stays Alpaca.

### Task AH25: Full suite, merge, deploy, install the weekly cron

**Model:** sonnet — the final gate and the hand-over to production follow fixed recipes (test-runner, `worktree-lifecycle`, the push-to-deploy pipeline, AH20's installer); the partner gate and the stop conditions are spelled out below.

**Files:**
- Modify (on `main`, after the merge): `docs/superpowers/results/<run-day>-v162-history-store-backfill.md` (AH21's file; append `## Deployed and scheduled`)
- VM: the crontab (through the committed `scripts/ops/install_v162_history_cron.sh`), removal of `/opt/swing-bot/staging/v162/`

**Interfaces:**
- Consumes (AH20): `scripts/ops/install_v162_history_cron.sh` (run on the VM as root via `bash $R/scripts/ops/ssh-hetzner.sh "bash -s" < <script>`; idempotent; prints `Installed crontab:` and the table), cron `30 6 * * 0` with the marker `# v162 alpaca history store weekly update (installed by install_v162_history_cron.sh)`, log `/opt/swing-bot/logs/history_store_cron.log` (one `=== <UTC> ===` header, then `update exit <n>` and `check exit <n>` per run).
- Consumes (AH10, AH2): `training_data.select()`, `training_data.provenance()`, `history_store.store_root()`, `config.TRAINING_DATA_SOURCE` inside the deployed containers.
- Consumes (AH21): the three manifest hashes in the backfill results doc.
- Produces: the merged, deployed bot (bump: bot patch, applied by `/close-out`, not here) and the weekly update running on the VM (Acceptance 8).

**Order matters.** The full suite runs once, in the worktree, before the merge; there is no second full run after it (CLAUDE.md). The cron is installed only after the deploy, because `compose run` uses the image named by `SWING_BOT_IMAGE` in `/opt/swing-bot/.env`, and only the merged image has `fetch_alpaca_history.py`. The staging copy goes last, once nothing reads it.

- [ ] **Step 1: Full suite (the one full run of this plan)**

Dispatch the `test-runner` agent with:

```bash
python $WT/scripts/dev/testrun.py full
```

Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). A failing test is fixed in the task that owns its file and re-run alone (`python $WT/scripts/dev/testrun.py file <test>`), never by re-running the whole suite; commit the fix on the branch.

Frontend (AH17 changed the Tuning tab):

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
```

Expected: every spec passes. A 60-second `Timeout waiting for worker` with `no tests` is machine load: run it again (`testing-cost.md` § Frontend).

- [ ] **Step 2: Complexity and a clean branch**

```bash
git -C $WT diff --name-only main...HEAD -- '*.py' | sed "s#^#$WT/#" | xargs python -m radon cc -s -n C
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: radon lists only the legacy functions the index names (`run_backtest_range.main` F(65), `tune_strategy.main` D(29), `run_config` C(17), `run_scenario_mode` C(19), `pool` C(15), `data_store.load_normalized` C(13) if touched), each at or below its score on `main`; no new function. The status is clean, and the log shows one or more commits per task AH1–AH24.

- [ ] **Step 3: Ask the partner (gate)**

Use `AskUserQuestion`, one question:

> "v162 is green (full suite and frontend). Next: merge the branch into `main` and push, which deploys bot and admin through GitHub Actions; then install the Sunday 06:30 UTC history-store update cron on the VM and remove the staging copy. From the deploy on, every backtest and admin grid trains on the Alpaca store by default; rollback is the one `.env` line `TRAINING_DATA_SOURCE=yfinance`. Go ahead?"
> 1. "Yes: merge, push, deploy, install the cron" (Recommended)
> 2. "Merge and push only; I will install the cron later"
> 3. "Not yet"

On 3, stop. On 2, skip Steps 7–8 and record the open cron in the results doc and to the partner.

- [ ] **Step 4: Merge into `main`**

Invoke the `worktree-lifecycle` skill and follow its merge section: it checks for other sessions on the main tree before merging. Then:

```bash
git -C $R status --short
git -C $R merge --no-ff 2026-10-15-v162-alpaca-history-store -m "merge(v162): Alpaca history store as the training data

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R log --oneline -3
```

Expected: the main tree's status shows nothing tracked as modified before the merge (untracked plan files of other sessions may be listed; leave them alone); the merge commits without conflict. A conflict is resolved by hand, keeping both sides' intent, followed by `python $R/scripts/dev/testrun.py changed` (not the full suite). No full suite after the merge.

- [ ] **Step 5: Push and watch the deploy**

```bash
git -C $R push origin main
gh run list --workflow deploy.yml --limit 1
```

Then wait for that run with `gh run watch <run-id> --exit-status` (in the background; wait for its notification). Expected: the `test`, `frontend`, image and deploy jobs all succeed. A failed CI job is fixed on `main` with a scoped commit and pushed again; never by re-running the deploy by hand.

- [ ] **Step 6: Verify the deployed containers read the store**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "grep -E '^SWING_BOT_IMAGE=' /opt/swing-bot/.env; cd /opt/swing-bot && docker compose ps --format '{{.Service}} {{.State}} {{.Image}}'"
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -" <<'PY'
from swingbot import config
from swingbot.core.marketdata import history_store, training_data
print("TRAINING_DATA_SOURCE", config.TRAINING_DATA_SOURCE)
print("store", history_store.store_root())
print("selected", training_data.select())
prov = training_data.provenance()
print("manifest", prov["manifest_hash"], prov["feed"], prov["adjustment"], len(prov["excluded"]), "excluded")
PY
```

Expected: the image tag names the merge commit (`sha-<12 chars of git -C $R rev-parse HEAD>`); `bot`, `admin`, `db` are `running`; `TRAINING_DATA_SOURCE alpaca`, store `/app/data/market_data`, `selected alpaca`, and the daily manifest hash from AH21 with `sip all`. A `MissingStoreError` here means the admin container does not see `./data` (it mounts it at `docker-compose.yml:206`): stop and tell the partner; the rollback line is `TRAINING_DATA_SOURCE=yfinance` in the VM's `.env`, mirrored per the production rule.

- [ ] **Step 7: Install the weekly cron**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "bash -s" < $R/scripts/ops/install_v162_history_cron.sh
bash $R/scripts/ops/ssh-hetzner.sh "crontab -l | grep -c 'install_v162_history_cron.sh'; crontab -l | grep -c 'fetch_alpaca_history.py --mode update'"
```

Expected: `Installed crontab:` with the marker line followed by the `30 6 * * 0 ...` line; both counts print `1`. The crontab is a production change whose source is the committed installer, so it is mirrored by construction.

- [ ] **Step 8: Remove the staging copy**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "chmod -R u+w /opt/swing-bot/staging/v162 && rm -rf /opt/swing-bot/staging/v162 && rmdir --ignore-fail-on-non-empty /opt/swing-bot/staging && ls /opt/swing-bot"
```

Expected: no `staging` entry in the listing (or `staging` still there only because it holds something else, which is left untouched).

- [ ] **Step 9: Record and commit on `main`**

Append to `$R/docs/superpowers/results/<run-day>-v162-history-store-backfill.md` with the Edit tool:

```markdown
## Deployed and scheduled (<UTC date>)

- Merged as `<merge sha>`, deployed image `<SWING_BOT_IMAGE>`. In the admin container `training_data.select()` returns `alpaca` with daily manifest `<hash>` (<n> excluded).
- Weekly update installed from `scripts/ops/install_v162_history_cron.sh`: Sunday 06:30 UTC, `compose run --rm` update then `check_history_store.py --verify-hashes`; log `/opt/swing-bot/logs/history_store_cron.log` (`update exit` / `check exit` per run). First run: <date of the next Sunday>.
- `/opt/swing-bot/staging/v162/` removed. No production change remains outside the repo.
- Rollback: `TRAINING_DATA_SOURCE=yfinance` in `/opt/swing-bot/.env`, mirrored in a commit.
```

```bash
git -C $R add docs/superpowers/results/<run-day>-v162-history-store-backfill.md
git -C $R commit -m "docs(v162): AH25 deployed, weekly history-store update scheduled, staging removed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R push origin main
git -C $R status --short
```

Expected: the commit lands on `main` and pushes (a docs-only change; the deploy it triggers changes nothing at runtime). Then run `/close-out` for v162: it applies the bot patch bump, moves the plan files to `implemented/` and removes the worktree.

