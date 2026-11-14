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

**Time basis.** Journal `opened_at` and `closed_at` are aware ISO strings in
UTC (`+00:00`). The archive CSVs carry UTC offsets (checked on production
2026-11-14 for Yahoo-only and Alpaca-eligible tickers, all `+00:00`) and
`data_store.load_normalized` strips the zone with `tz_localize(None)`, so the
index it returns is naive UTC, and each bar is stamped with its **start**. The
function converts the trade's times to naive UTC before comparing.
`load_normalized` returns `None` for a file with mixed offsets; that is counted
as an unreadable file, never as no coverage. The plan's first task pins both facts with a test
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

`journal.build_entry` and `journal_trade_close` take the frames mapping in
place of the single daily frame (their other callers,
`backfill_journal.py` and `rejournal_fill_mismatch.py`, are updated in the same
task), and `build_entry` adds `excursion_source` to the entry. It is a new field in
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

**Inputs per entry.** A journal entry does not carry the entry, stop and exit
prices, so the pass joins each entry to its `TradeLog` trade by id and hands
the trade to `compute_excursion` and `tags_for`. An entry whose trade is gone
is counted `no_trade` and skipped.

**Write path.** `Repository.patch` (`swingbot/core/db/repositories/base.py`)
has no condition today, so this spec adds one: an optional predicate on a doc
field, used here as "stored `excursion_source` is in the set of coarser
sources". The pass writes through `JournalRepository.patch` (the atomic
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

One Alembic data revision, chained to the Alembic head on disk when the task
runs (`v208_001` on 2026-11-14; the task re-reads it), stamps `excursion_source = "daily"` on every journal
entry that has `mfe_r` and no source. After it, no reader has to treat a
missing source as anything. Its downgrade is a **no-op**: stripping the field
would also strip `5min` and `hourly` sources written later, and a re-upgrade
would then label intraday numbers `daily`; older code keeps unknown doc fields
(`test_unknown_field_round_trip.py`), so leaving it is safe. The revision
declares `ROLLBACK_SAFE` (v220) saying so, and notes the one loss: older code
re-journaling a trade upserts the entry without the field.

One operator script, `scripts/ops/backfill_excursions.py`, then calls
`upgrade_excursions` over the whole book. The VM's 5-minute and 15-minute
archives are merge-only and start on 2026-06-23 (checked 2026-11-14), which is
before the first live trade, so every entry with bars can reach `5min`. It checkpoints per ticker and a restart skips finished
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
- **Admin SPA.** One rule everywhere: a figure is marked when its source is
  `daily` and the trade was held under two days, the same threshold the
  aggregates use. The visible text carries the meaning, `est. (daily bars)`,
  so nothing depends on hover; the one-line explanation ("held under 2 days,
  intraday bars unavailable, the range may be overstated") sits in a
  tap-reachable, keyboard-focusable element with an `aria-label`.
  - *Trade detail* (`stores/trade-detail.store.ts`): the `excursions` rows gain
    an optional `estimate` flag; MFE, MAE **and** Exit efficiency carry the
    marker, since efficiency is derived from MFE.
  - *Calendar day card* (`calendar/day/day-trade-card.ts`): the marker goes
    inside the existing `MFE · MAE` text line and wraps with it; the layout
    audit checks the card at 390 px for no sideways scroll. The card's data
    comes from `pnl_calendar.ROW_KEYS`, so `excursion_source` joins `ROW_KEYS`
    and `CalendarTrade` in `api/models.ts`, and the three contract tests that
    pin those shapes are updated (`tests/analytics/test_pnl_calendar.py`,
    `tests/admin/test_api_v1_calendar.py`, `_ENTRY_SHAPE` in
    `tests/admin/test_api_journal.py`). The older MFE/MAE drawer in
    `calendar/calendar.ts` shows the same figures and takes the same marker.
  - *Analytics execution tab*: it shows no per-trade figure, so no marker. The
    Exit efficiency panel's caption states the exclusion in plain text, "n of N
    trades; M short holds on daily bars excluded", visible on a phone. The
    Execution verdict card also quotes exit efficiency and carries the same
    count in its hint.
  - Checked at phone, tablet and desktop together per `docs/claude/ui-design.md`.
- **Discord trade-view chart** (`swingbot/core/scanning/lifecycle_embeds.py`):
  the MFE and MAE annotations take a `(daily est.)` suffix under the same rule,
  so the embed and the admin screen read the same. Closed-trade chart images are
  cached at a deterministic path; charts already rendered are not re-rendered,
  so the suffix appears on charts drawn after this ships.
- **`scripts/ops/export_book_rows.sh`** appends `excursion_source` as column 39
  in **both** branches of the `UNION` (`NULL::text` in the plan branch), which
  keeps the positional `ORDER BY`; `tests/scout/test_export_script.py` is
  updated to pin it.
- **`scripts/reports/book_autopsy.py`** builds MFE- and MAE-derived cells only
  from rows with an intraday source, and prints how many rows that dropped. A
  CSV without the column stops the run with a message naming the fix, rather
  than dropping every MFE row quietly. The loader accepts two older header
  shapes today (38 and 36 columns); both now stop the same way unless the run
  passes `--no-excursion-cells`, which builds every other cell and prints that
  the excursion cells were left out.

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
- The data revision: upgrade stamps only rows with `mfe_r`; downgrade leaves stamped rows unchanged.
- Backfill script: checkpoint written per ticker, restart skips.
- Exit-quality aggregates: the exclusion rule and its count; empty book.
- Frontend: marker shown and hidden by source and holding time, at 390, 768 and
  1280 px.
- Export script column pin; autopsy drop count.

Suite size: `tests/analytics/` holds about 1,121 tests against a `max_tests`
of 1,200. If these tests would pass the limit, the excursion tests go in their
own directory joined to one suite in the same commit; the limit is not raised.

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
- ux-designer: a hover tooltip is unreachable on touch -- applied (visible text carries the meaning; explanation is tap- and keyboard-reachable).
- ux-designer: day card renders MFE and MAE as one inline line -- applied (marker inside the line, 390 px audit).
- ux-designer: trade-detail excursion rows have no slot for a marker; efficiency unaddressed -- applied (`estimate` flag, all three rows).
- ux-designer: the execution tab has no per-trade MFE/MAE figure; excluded count unplaced -- applied (caption on the Exit efficiency panel, no marker).
- ux-designer: the Discord trade-view chart shows the same figures unmarked -- applied (suffix).
- ux-designer: "daily estimate" wording unclear -- applied (`est. (daily bars)`; explanation says overstated, which is the measured direction, not understated).
- quant-engineer (v229 review, carried here): the sub-hourly archive is merge-only and unpruned, not 60 days -- applied (backfill covers the whole book).
- plan brief (code check, 2026-11-14): journal times are aware UTC, not naive; `Repository.patch` has no condition; the pass must join trades by id; the calendar card reads `pnl_calendar.ROW_KEYS`; `build_entry` takes one frame; chart images are cached; the autopsy loader accepts older headers; the Alembic head is `v208_001`; the analytics suite is near its limit -- all applied above.
- plan index (2026-11-14): Testing said the downgrade restores, against the no-op body -- applied (Testing corrected); the older calendar drawer was unnamed -- applied (marked like the card).
