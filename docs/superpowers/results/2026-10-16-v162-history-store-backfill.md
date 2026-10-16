# v162 history store: production backfill (2026-10-16)

**Spec:** [v162 design](../specs/2026-10-15-v162-alpaca-history-store-design.md) · **Plan:** [v162 index](../plans/2026-10-15-v162-alpaca-history-store_0-index.md), task AH21
**Code:** branch `2026-10-15-v162-alpaca-history-store` at `69a74788072121ccd2b6bc4c2edd6bcdb5a6c4e1`, staged read-only at `/opt/swing-bot/staging/v162/` (528 files, equal to `git ls-files swingbot scripts`) over the deployed image `sha-b22e799e1c59`
**Run:** `docker compose run --rm` on the VM, `--mode full`, defaults (15min, hourly, daily; start 2016-01-01; watchlist plus SPY, 78 tickers), started `2026-10-16T07:42:16Z` (03:42 ET, Friday), finished `2026-10-16T09:24:48Z`, `2508` requests. Exit 0; `written 228, unchanged 0, refetched 0, skipped 2, flagged 9, requests 2508`.

## Manifests

Values right after the full run (`updated_at 2026-10-16T07:42:27Z` on all three; feed `sip`, adjustment `all`):

| timeframe | top-level hash | tickers | ok | not ok | rows | bytes | B/row |
|---|---|---|---|---|---|---|---|
| daily | `9e0a4e0ddd62886d5077f5d27aa86a6f1447b9285ad6af7d6b4af0c292a49b60` | 78 | 67 | 11 | 174265 | 8165612 | 46.9 |
| hourly | `12adebefeb766253dd25e984872697d946279d88d29280d4ecab39ff0ef9dca2` | 78 | 67 | 11 | 1214806 | 67014705 | 55.2 |
| 15min | `12f44d23bfb6b130447ba3084020c044fa734f956dc71b53e38cc786011be10c` | 78 | 67 | 11 | 7680146 | 413415371 | 53.8 |

After the Step 10 update run (see Checks) the daily and hourly hashes are unchanged. The 15min manifest is now `5282956ba7bd6a86dae7f56fea4ce2e97e465018dcf15c9c7f609c6eda4ad06c`, `updated_at 2026-10-16T10:56:15Z`, because 2026-10-16 pre-market bars were appended.

Measured full-run size: 0.489 GB (488.6 MB; spec estimate 1.2 GB). Weekly growth estimate from the measured bytes per row: 1.30 MB a week (15min 1.15 MB, hourly 0.13 MB, daily 0.02 MB). Disk free: 12.39 GB before the run, 26.51 GB after. Something else on the VM freed space during the run (dump or PITR rotation); the store accounts for about 0.49 GB.

Every `ok` ticker's daily `last` is `2026-10-15`, the last session before the run. Daily `first` is `2016-01-04` or the listing date: ABNB 2020-12-10, ARM 2023-09-14, ASTS 2019-11-01, CEG 2022-02-02, CRWD 2019-06-12, CRWV 2025-03-28, DDOG 2019-09-19, DELL 2018-12-28, DOCU 2018-04-27, GEV 2024-04-02, HIMS 2019-09-13, HOOD 2021-07-29, IREN 2021-11-17, MRNA 2018-12-07, NBIS 2024-10-21, PLTR 2020-09-30, QBTS 2020-12-11, RKLB 2020-11-24, SNDK 2025-02-13, SNOW 2020-09-16, SOFI 2021-01-04, UBER 2019-05-10. No stale `last`.

## Skipped and flagged

Identity references: the VM's `data/backtest_cache/` holds only 7 CSVs (GC_F, OSCR, PATH, RDDT, SI_F, SKHY, SPCX), not one per watchlist ticker. For every other ticker the check used the code's documented fallback, the root `market_data/daily/` cache (92 files; SPY 1993-01-29..2026-07-31). The flags below compare Alpaca against that fallback.

| ticker | status | detail |
|---|---|---|
| XAGUSD | skipped: spot metal (built from futures) | not Alpaca-servable |
| XAUUSD | skipped: spot metal (built from futures) | not Alpaca-servable |
| ASML | flagged: price-mismatch | median_ratio 1.00621, overlap 2712 |
| CVX | flagged: price-mismatch | median_ratio 0.991349, overlap 2711 |
| HD | flagged: price-mismatch | median_ratio 0.992685, overlap 2711 |
| HPQ | flagged: price-mismatch | median_ratio 0.990398, overlap 2711 |
| IBM | flagged: price-mismatch | median_ratio 1.038507, overlap 2711 |
| QCOM | flagged: price-mismatch | median_ratio 0.994577, overlap 2711 |
| UNH | flagged: price-mismatch | median_ratio 0.99388, overlap 2712 |
| WDC | flagged: price-mismatch | median_ratio 0.901071, overlap 2712 |
| SPCX | flagged: short-overlap | median_ratio 1.0, overlap 33, dropped_before 2026-06-12 |

The flagged tickers stay in the store and `training_data` excludes them from training. The partner accepted this for now ("document and continue"). The price-mismatch ratios are small, persistent offsets. They are consistent with differences in dividend and spin-off adjustment between Alpaca `adjustment=all` and the yfinance reference (WDC: the SNDK spin-off; IBM: the Kyndryl spin-off). Nothing was un-flagged.

Bars dropped before the identity reference's first bar: NBIS 2024-10-21, SNOW 2020-09-16, SOFI 2021-01-04, SPCX 2026-06-12.

## Checks

- Row counts and hashes (`check_history_store.py --verify-hashes`, `logs/v162_check.log`): `check: 399 unexplained gap(s), 0 hash problem(s)` (exit 1). There are no hash problems. The partner accepted all 399 gaps as documented data artefacts in three families. No store file was edited and nothing was refetched.
  1. **Malformed SPY calendar, 2019-08-12 (58 entries) and 2019-12-24 (61 entries), 15min.** The check builds its session calendar from SPY. On 2019-08-12 SPY's 15min file has 25 slots between 09:30 and 16:00: the 15:45 bar is missing, a hole in Alpaca's SPY data. 2019-12-24 was a 13:00 early close, and SPY has 25 slots in that window: the extended-hours prints after 13:00 fill it, with 14:30 missing. Every other 15min file is flagged on these two dates because of the malformed calendar, not because of its own data. Alpaca's after-close extended-hours bars also make every other early close look like a full day, which is why `half=0` in every summary line.
  2. **SPAC-shell-era days: ASTS, HIMS, QBTS, RKLB.** These are days with a daily bar but no intraday bar, all before the de-SPAC merger, when the shells (NPA, OAC, DPCM, VACQ) traded thinly. ASTS has 20 hourly and 19 15min entries, 2019-11-04..2020-01-02. HIMS has 20 hourly and 20 15min, 2019-09-16..2019-11-21. QBTS has 2021-10-25 and RKLB 2020-11-25 (hourly and 15min each).
  3. **Alpaca intraday hole, 2022-03-08: GD, JNJ, PFE, PLTR, QBTS, SNOW, V** (hourly and 15min, 14 entries). Each has a daily bar, 0 hourly bars and only 2-23 15min bars. 2022-03-07 and 2022-03-09 are complete, and SPY and AAPL are complete on the day. This is a gap in Alpaca's intraday data, not a trading halt.
- SPY is `ok` in daily, hourly and 15min (session calendar of the check script, regime benchmark of every backtest).
- **No-op update (`--mode update`, run 2026-10-16T10:56:05Z..11:07:20Z, 06:56 ET Friday, before the open):** exit 0; `written 222, unchanged 6, refetched 0, skipped 2, flagged 9, requests 988`; files written: 75 (74 `15min/*.csv` plus `15min/_manifest.json`; all but GD and ILMN). Daily and hourly: no file written, and `updated_at` is unchanged at `2026-10-16T07:42:27Z`. That part of Acceptance 4 is proved. **15min is not a no-op.** By 06:56 ET the all-session 15min feed already had 2026-10-16 pre-market bars (04:00-06:30 ET, 627 rows across 74 files), and the update appended them correctly. The plan assumed "no new daily bar, so no new bar", which does not hold for the all-session 15min feed after 04:00 ET. There was no lockstep refetch (`refetched 0`). The `written` counter reads 222 = 74 tickers x 3 timeframes, although only the 15min files changed: it counts a ticker as written in every timeframe when any timeframe gained bars. The 15min no-write proof still needs one update run in a window with no new bars: after an update that captured the 20:00 ET close, before 04:00 ET the next weekday, or on a weekend.
- Sector-relative context: of the 17 sector ETFs in `data/universe/etfs.json`, `data/backtest_cache/` on the VM holds `[]` and `data/market_data/daily/` holds `['SPY']`. The lists differ only by SPY, which is in the store as the market-regime ticker. **The VM's `data/backtest_cache/` (7 CSVs) is not the yfinance training reference**, so it cannot be used for this comparison; the yfinance training cache is the dev machine's `data/backtest_cache/`. No ETF was fetched or added to equalise the lists. Adding sector ETFs to one source only would make the §5 legs train on different populations.

## Plan defect found while running

`docker compose run -T ...` inside a `bash -s` heredoc reads the rest of the stdin script. As written, Steps 4, 7 and 10 lose every line after their first compose call: the first smoke attempt printed only the fetch summary. Every compose call in this run was given `< /dev/null`. The smoke was then re-run from a clean probe root, and every result above comes from those runs. Any future copy of these steps (AH22, AH25, the cron) needs the same redirect.

## Production changes and their mirror

- `/opt/swing-bot/data/market_data/` (the store): data under the gitignored `data/` bind mount, written only by the committed `scripts/data/fetch_alpaca_history.py`. Not mirrored by design.
- `/opt/swing-bot/staging/v162/`: a read-only copy of the branch's `swingbot/` and `scripts/` at the SHA above. Temporary; AH25 removes it once the merged image is deployed.
- `/opt/swing-bot/logs/v162_{backfill,check,update_noop}.log` and `logs/v162_backfill.started`: run logs.
- `/opt/swing-bot/data/market_data_probe/`: the Step 4 smoke root, created and removed.
- No crontab, `.env`, compose or image change. The weekly cron is installed by AH25 from the committed `scripts/ops/install_v162_history_cron.sh`.

## Pulled to the dev machine (2026-10-16)

`bash scripts/ops/pull_history_store.sh` (probe first: `probe PASS f8ae6d86343f9513cfaaccb32defb27edd4431ae3ad0d87406920e81f2975af2`), into `E:/Documents/Private/Projects/Discord-Bot/data/market_data/`, 488718592 bytes. Local manifest hashes equal the VM's, read back after the pull: daily `9e0a4e0ddd62886d5077f5d27aa86a6f1447b9285ad6af7d6b4af0c292a49b60`, hourly `12adebefeb766253dd25e984872697d946279d88d29280d4ecab39ff0ef9dca2`, 15min `5282956ba7bd6a86dae7f56fea4ce2e97e465018dcf15c9c7f609c6eda4ad06c` (the post-update 15min hash; `updated_at` daily/hourly `2026-10-16T07:42:27Z`, 15min `2026-10-16T10:56:15Z`; 78 tickers each). `check_history_store.py --verify-hashes` on the local copy: `check: 399 unexplained gap(s), 0 hash problem(s)`. That is the same verdict as the VM, and the same three accepted gap families listed under Checks. `training_data.select("alpaca")` on it: feed `sip`, adjustment `all`, 67 trainable tickers, 11 excluded. SPY daily runs 2016-01-04..2026-10-15.

Plan defect found: the pull leaves `data/market_data.check.txt` next to the store (and `.prev/` / `.partial/` siblings on later or failed pulls). The unanchored `market_data/` pattern matches only the directory, so these showed in `git status`. Fixed on the branch with `data/market_data.*` in `.gitignore`.

## Deployed and scheduled (2026-10-16)

- Merged as `81843c8e`, deployed image `ghcr.io/cmghuy/discord-bot:sha-81843c8ede31` (deploy run 38914622717; every job green, including `backend-test (history-store)`). In the admin container `training_data.select()` returns `alpaca`, store `/app/data/market_data`, daily manifest `9e0a4e0ddd62886d5077f5d27aa86a6f1447b9285ad6af7d6b4af0c292a49b60` (`sip all`, 11 excluded).
- Final gate before the merge: full suite `8373 passed, 1646 skipped`, 0 failed, 0 xfailed; frontend `168` files, `3017` tests passed. Plan defect: `npm --prefix frontend exec -- ng test` run from the repo root fails every file with `ENOENT ... src/styles/tokens.css` (the test setup resolves it against the cwd); run `npx ng test --watch=false` from inside `frontend/`.
- Weekly update installed from `scripts/ops/install_v162_history_cron.sh`: Sunday 06:30 UTC, `compose run --rm` update then `check_history_store.py --verify-hashes`; log `/opt/swing-bot/logs/history_store_cron.log` (`update exit` / `check exit` per run). First run: 2026-10-18. Every other crontab entry was kept (the stray `# v106 load sampler` comment predates this; the sampler removed its own line, `logs/v106_load_sampler.log`: `one-shot done: crontab line removed`).
- `/opt/swing-bot/staging/v162/` removed. No production change remains outside the repo.
- Rollback: `TRAINING_DATA_SOURCE=yfinance` in `/opt/swing-bot/.env`, mirrored in a commit.
