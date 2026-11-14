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

**Slice rule, intraday frames.** Bars whose start is at or after `opened_at`
and at or before `closed_at`. The bar that contains the entry is dropped,
because its high and low include price before the fill. The bar that contains
the exit is kept; its post-exit part can overstate the excursion by at most one
bar.

**Anchors.** The entry price and the exit price are always points on the path:
`mfe_r >= max(0, r at exit)` and `mae_r >= max(0, -r at exit)`. A trade that
opens and closes inside one bar therefore gets a real answer from its own two
prices, and an empty slice is not a failure.

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
`auto_lesson` on that entry. `note` and every other field are left alone. An
entry is never downgraded, and an unchanged entry is not written.

It runs in the `refresher` container after the intraday archive refresh, over
the last 7 days. The report (entries read, upgraded per source, skipped for no
coverage) goes to the log as one line.

### 4. Existing rows

One Alembic data revision stamps `excursion_source = "daily"` on every journal
entry that has `mfe_r` and no source, with `drop_doc_field` as its downgrade.
After it, no reader has to treat a missing source as anything.

One operator script, `scripts/ops/backfill_excursions.py`, then calls
`upgrade_excursions` over the full retained window (5-minute and 15-minute
archives hold 60 days; hourly holds about two years). It checkpoints per ticker
and a restart skips finished tickers. It runs on the VM through `/deploy`'s
post-deploy step and is listed in the plan's production task with `mirror-prod`.

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
- **`scripts/ops/export_book_rows.sh`** appends `excursion_source` as column 39;
  `tests/scout/test_export_script.py` is updated to pin it.
- **`scripts/reports/book_autopsy.py`** builds MFE- and MAE-derived cells only
  from rows with an intraday source, and prints how many rows that dropped.

## What does not change

- No alert, plan, stop, target or lifecycle message. The partner's resting
  orders are untouched.
- No backtest or replay code: `exit_sim` computes its own excursions on the bars
  it races.
- `r_realized`, `outcome`, `holding_days` and `risk_features` on existing rows.

## Edge cases

- **Extended-hours fills.** The 5-minute archive may hold regular hours only. A
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
