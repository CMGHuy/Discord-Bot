# v228 — Intraday MFE/MAE for the journal

**Version:** ui 1.43.0 · bot 2.18.7
**Bump:** bot patch, ui patch
**Edge:** none (integrity) — the journal's MFE, MAE and exit efficiency become true for trades that live hours, not days. It buys no edge itself; it makes every later harvest read of the live book honest.
**Screen:** exempt (integrity)
**Panel:** quant-engineer, staff-engineer, ux-designer

## Why

`swingbot/core/analytics/mfe_mae.py:compute_mfe_mae` slices **daily** bars from
the entry day to the exit day. Since 2026-10-01 stops sit at 1.75–2.0% of price
(about 0.35 ATR), and 54% of LONG trades close the day they open. For those
trades the daily bar's range includes price action before the entry and after
the exit, so the stored figures describe the day, not the trade.

Measured on production, 2026-11-14
(`docs/superpowers/results/2026-11-14-long-book-read.md`, finding 1), LONG
trades closed since 2026-10-01, recomputed from 5-minute bars:

| Last leg | N | Median MFE, 5-minute | Median MFE, stored |
|---|---|---|---|
| `loss` | 192 | 0.31R | 1.24R |
| `scratch` | 71 | 1.38R | 1.67R |

Only 13 of 192 losers truly reached +1R; the stored field says most did. Three
things inherit the error: `exit_efficiency`, the `near_miss_tp` tag and
`_auto_lesson` in `swingbot/core/analytics/journal.py`, and every give-back or
headroom read the trade scout makes from the book export.

## What changes

### 1. The excursion is measured on the finest bars that cover the trade

A new pure function in `swingbot/core/analytics/mfe_mae.py`:

`compute_excursion(trade, frames) -> dict | None`

`frames` is an ordered mapping of timeframe name to DataFrame, finest first:
`5min`, `15min`, `hourly`, `daily`. The function uses the **first** frame that
covers the trade and returns `mfe_r`, `mae_r`, `exit_efficiency` and
`excursion_source` (the timeframe name used).

**Coverage rule.** An intraday frame covers the trade when its first bar starts
at or before `opened_at` and its last bar starts at or after `closed_at` minus
one bar length. A frame that fails either side is skipped. `daily` covers when
the existing date-level slice is non-empty (today's rule, unchanged).

**Density rule.** First and last bars are not enough: a frame with a hole in
the middle of the hold would under-measure silently. Inside the slice window,
two consecutive bars on the same calendar date may be at most four bar lengths
apart; a frame that breaks this is skipped like an uncovered one
(`known-traps.md`: a stale or truncated `market_data` file is never used
silently).

**Time basis.** Journal `opened_at` and `closed_at` are naive UTC. The archive
CSVs carry UTC offsets and `data_store.load_normalized` strips the zone with
`tz_localize(None)`, so the index it returns is naive UTC, and each bar is
stamped with its **start**. The plan's first task pins both facts with a test
on real archive files for every provider that writes them (Yahoo and Alpaca);
if either fails for a provider, the function converts that frame to naive UTC
bar starts before comparing, and nothing is compared across bases.

**Slice rule, intraday frames.** Bars whose start is at or after `opened_at`
and at or before `closed_at`. The bar that contains the entry is dropped,
because its high and low include price before the fill. The bar that contains
the exit is kept; its post-exit part can overstate the excursion by at most one
bar.

**Anchors.** The entry price and the exit price are always points on the path:
`mfe_r >= max(0, r at exit)` and `mae_r >= max(0, -r at exit)`. A trade that
opens and closes inside one bar therefore gets a real answer from its own two
prices, and an empty slice is not a failure. Such an answer is a lower bound:
`excursion_source` names the bars consulted, not the precision achieved.

**Daily frame.** Exactly today's arithmetic, so a trade measured on daily bars
keeps today's numbers and is labelled `daily`.

`compute_mfe_mae(trade, df)` stays as a thin wrapper
(`compute_excursion(trade, {"daily": df})` minus the source key) so existing
callers and tests keep their contract. Its complexity is 16 in
`scripts/dev/complexity_baseline.json`; the split into `_cover`, `_slice` and
`_excursion_r` helpers takes both functions under 15 and the baseline row is
removed.

### 2. The journal records the source

`journal.build_entry` adds `excursion_source` to the entry. It is a new field in
the journal `doc` (schema operation **add**, no DDL).

At close time the 15-minute and 5-minute archives may be up to 24 hours stale
(`data_refresh.py` refreshes them daily), so `journal_trade_close` usually finds
only daily bars covering a trade that just closed. That is expected: the entry
is written with whatever covers it, normally `daily`, and is upgraded by step 3.

### 3. A nightly pass upgrades entries once finer bars arrive

`swingbot/core/analytics/excursion_upgrade.py`:

`upgrade_excursions(since, until=None) -> UpgradeReport`

For each journal entry closed in the window whose `excursion_source` is coarser
than `5min` (or absent), load the frames through
`swingbot/core/marketdata/data_store.load_normalized`, call
`compute_excursion`, and when the result's source is **finer** than the stored
one, rewrite `mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`, `tags` and
`auto_lesson` on that entry. An entry is never downgraded, and an unchanged
entry is not written.

**Write path.** The pass writes through `JournalRepository.patch` (the atomic
JSONB merge `set_note` already uses), never `JournalStore.add` or
`build_entry`: `add` upserts the whole record and `build_entry` writes
`"note": ""`, which would wipe the partner's notes. The patch carries only the
six fields above and is **conditional on the stored source rank**: the `UPDATE`
matches only while the row's `excursion_source` is still coarser than the new
one. The bot's pass and the backfill script can reach the same entry at the
same time; with the condition in the statement, the finer write wins whichever
lands first and a coarser one becomes a no-op. A read-then-write check is not
enough and is not used.

It runs in the **bot** container from the `market_data_refresh` loop
(`swingbot/commands/scanning/loops.py`, after `refresh_all`), over the last 7
days: that loop is what refreshes the archives, so the bars are on disk when
the pass reads them. The loop wakes every `MARKET_DATA_REFRESH_MINUTES` and its
docstring records the 2026-08-24 gateway-starvation incident, so the pass is
fenced three ways: it runs **at most once per UTC date** (a module-level stamp;
a restart may run it again, which is harmless), it runs through
`asyncio.to_thread` so the event loop is never blocked, and it stops at a
60-second budget, leaving the rest for the next day. Entries that cannot reach
a finer source (no file, extended-hours fills) are therefore re-read once a day
for seven days, not on every tick. The `refresher` container never calls `data_refresh` and
is not involved. A failure in the pass is logged and never fails the refresh.
The report (entries read, upgraded per source, skipped for no file, skipped for
no coverage, skipped for density) goes to the log as one line; a missing file
and an uncovered trade are counted separately.

### 4. Existing rows

One Alembic data revision stamps `excursion_source = "daily"` on every journal
entry that has `mfe_r` and no source. After it, no reader has to treat a
missing source as anything. Its downgrade is a **no-op**: stripping the field
would also strip `5min` and `hourly` sources written later, and a re-upgrade
would then label intraday numbers `daily`; older code keeps unknown doc fields
(`test_unknown_field_round_trip.py`), so leaving it is safe. The revision
declares `ROLLBACK_SAFE` (v220) saying so, and notes the one loss: older code
re-journaling a trade upserts the entry without the field.

One operator script, `scripts/ops/backfill_excursions.py`, then calls
`upgrade_excursions` over the full retained window (5-minute and 15-minute
archives hold 60 days; hourly holds about two years, so older trades can reach
`hourly` at best). It checkpoints per ticker and a restart skips finished
tickers; a ticker interrupted halfway is simply redone, which is safe because
each entry's upgrade is idempotent and never downgrades. The plan verifies that
production's `MARKET_DATA_TIMEFRAMES` lists `15min` and `5min` before the
backfill is scheduled. `/deploy` has no post-deploy step, so the
plan's production task spells the run out under `mirror-prod`: the PITR-drill
check required before a data revision on production (`schema-evolution.md`),
the deploy, the `MARKET_DATA_TIMEFRAMES` check, the script run detached on the
VM with its checkpoint on a mounted volume, the report line read back, and the
mirror recorded in the repo.

### 5. Readers

- **`swingbot/core/analytics/exit_quality.py`** adds `excursion_source` to each
  point and a per-source count to its summary. Aggregates (median efficiency,
  the MFE/MAE scatter) use only entries whose source is intraday **or** whose
  `holding_days >= 2`; the excluded count is returned so the UI can say so.
- **Admin SPA** (`trade-detail`, the calendar day card, the analytics execution
  tab): the MFE/MAE figures show a small "daily estimate" marker when the source
  is `daily` and the trade was held under two days. Phone, tablet and desktop
  are checked together per `docs/claude/ui-design.md`; the marker is text plus a
  tooltip, wraps under the figure at 390 px and adds no column.
- **`scripts/ops/export_book_rows.sh`** appends `excursion_source` as column 39
  in **both** branches of the `UNION` (`NULL::text` in the plan branch), which
  keeps the positional `ORDER BY`; `tests/scout/test_export_script.py` is
  updated to pin it.
- **`scripts/reports/book_autopsy.py`** builds MFE- and MAE-derived cells only
  from rows with an intraday source, and prints how many rows that dropped. A
  CSV without the column (exported before this change) stops the run with a
  message naming the fix, rather than dropping every MFE row quietly.

## What does not change

- No alert, plan, stop, target or lifecycle message. The partner's resting
  orders are untouched.
- No backtest or replay code: `exit_sim` computes its own excursions on the bars
  it races.
- `r_realized`, `outcome`, `holding_days` and `risk_features` on existing rows.

## Edge cases

- **Extended-hours fills.** The archives are fetched without `prepost`, so they
  hold regular hours only, while the plan manager can exit in extended hours. A
  trade opened or closed outside them still passes coverage by the
  one-bar-length tolerance only if a bar is adjacent; otherwise the next coarser
  frame is used. The anchors keep the answer bounded either way.
- **No bars at all.** Every excursion field is `None` and `excursion_source` is
  `None`, as today.
- **Crypto and FX tickers** (24-hour sessions): the same rules; coverage is
  judged on the bars the store holds.
- **A bar gap inside the hold** (halt, missing data): the slice simply has fewer
  bars; no interpolation.
- **Bearish trades** mirror every rule.

## Testing

- `compute_excursion`: same-bar trade (anchors only), entry-bar exclusion,
  exit-bar inclusion, coverage failure falling through each rung, bullish and
  bearish, daily parity with the current `compute_mfe_mae` on existing fixtures,
  empty and `None` frames.
- `upgrade_excursions`: upgrades on a finer source, never downgrades, leaves
  `note` alone, idempotent on a second run, tags and lesson re-derived.
- The data revision: upgrade stamps only rows with `mfe_r`, downgrade restores.
- Backfill script: checkpoint written per ticker, restart skips.
- Exit-quality aggregates: the exclusion rule and its count; empty book.
- Frontend: marker shown and hidden by source and holding time, at 390, 768 and
  1280 px.
- Export script column pin; autopsy drop count.

## What follows

- The scout's exit-harvester role reads the next autopsy on corrected figures.
- The breakeven-trigger idea is closed on today's evidence (results doc,
  finding 2) and is not reopened by this spec.

## Panel review

- quant-engineer: the nightly pass was placed in the `refresher` container, which never refreshes the archives -- applied (moved to the end of the bot's `market_data_refresh` loop).
- quant-engineer: bar-index time zone and start-versus-end stamping undefined against naive-UTC journal times -- applied (Time basis rule, pinned by a test on real files per provider).
- quant-engineer: first/last-bar coverage passes a frame with an interior hole -- applied (Density rule).
- quant-engineer: an anchors-only answer is a lower bound, source is not precision -- applied.
- quant-engineer: archives are regular-hours only while exits can be extended-hours -- applied (edge case reworded).
- quant-engineer: `MARKET_DATA_TIMEFRAMES` on production and 60-day retention limit the backfill -- applied.
- quant-engineer: a missing file must not be counted as no coverage -- applied (separate report counts).
- quant-engineer: per-ticker checkpoint versus per-entry upgrade needs its idempotence argument -- applied.
- staff-engineer: never-downgrade was a read then a write, so the bot pass and the backfill could downgrade each other -- applied (conditional patch on source rank).
- staff-engineer: the refresh loop is not nightly and has a starvation history; no thread, budget or once-a-day fence -- applied (once per UTC date, `asyncio.to_thread`, 60-second budget).
- staff-engineer: writing through `add`/`build_entry` would wipe notes -- applied (`JournalRepository.patch` only).
- staff-engineer: `drop_doc_field` downgrade strips later intraday sources -- applied (no-op downgrade).
- staff-engineer: revision needs `ROLLBACK_SAFE` -- applied.
- staff-engineer: `/deploy` has no post-deploy step; production run and PITR check unspecified -- applied.
- staff-engineer: export column must be in both UNION branches; autopsy must fail loudly on an old CSV -- applied.
