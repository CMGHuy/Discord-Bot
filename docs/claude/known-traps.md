# Known traps

Referenced from the root `CLAUDE.md`. Each of these has already cost a
session — read this before touching data caching, `scan_engine`/`scan_embeds`,
`embeds.py`, or the scan loop.

- **Two parallel OHLCV cache subsystems — do not conflate them.** Both now
  live in `swingbot/core/marketdata/` (v27 repo restructure, 2026-08-15).
  `marketdata/backtest_cache.py` → `data/backtest_cache/` (flat `TICKER.csv`,
  daily only, ~77 tickers, what every existing backtest/grid script reads).
  `marketdata/data_store.py` → `market_data/` (grouped by candle timeframe:
  `{timeframe}/{TICKER}.csv`, e.g. `market_data/daily/AAPL.csv`, ~521 daily +
  78 hourly, what the edge-engine tasks depend on -- and, since v47, what
  the live scan reads first). Both are gitignored.
  Check which one a script reads before pointing it at a path.
- **Spot metals are never cached under their own name (v109).** `XAUUSD` /
  `XAGUSD` bars are `GC=F` / `SI=F` bars × a live spot ratio
  (`marketdata/spot_metals.py`). Only the raw future is cached (`GC_F.csv`);
  `save_to_disk` and `data_refresh._merge_save` raise on a spot name, and
  `refresh_all`, `update_cache` and `backtest_cache.ensure_cached` map it to
  the future. A cached scaled frame would freeze one day's ratio into later
  levels. The scan crawl skips the disk cache for spot symbols entirely.
- **`market_data/` is timeframe-first, not ticker-first.** Folders are the
  semantic names in `data_store.TIMEFRAMES` (`monthly`, `weekly`, `daily`,
  `hourly`, `15min`, …); filenames are sanitized (`GC=F` → `GC_F.csv`, same
  scheme as `backtest_cache`). Every accessor takes EITHER the semantic name
  or the yfinance code — `load_from_disk(t, "1h")` and
  `load_from_disk(t, "hourly")` resolve to the same file. Go through
  `cache_path()`/`load_from_disk()`; never hand-build the path.
- **The bot self-refreshes this cache while running**
  (`core/marketdata/data_refresh.py`, driven by the `market_data_refresh`
  task loop in `commands/scanning.py`).
  Incremental and staleness-gated per timeframe (hourly 4h, daily 12h,
  weekly/monthly 24h), so most wake-ups cost no network. Flags:
  `MARKET_DATA_AUTO_REFRESH`, `MARKET_DATA_REFRESH_MINUTES`,
  `MARKET_DATA_TIMEFRAMES`.
- **Yahoo's intraday depth is a hard ceiling, not a tuning knob.** 1h serves
  ~730 *trading* days (~3 calendar years, measured); 15m/30m/5m only ~60 days;
  1m ~30 days. "Since IPO" hourly data does not exist from this source at any
  tier — only daily and coarser reach the listing date. Do not write a task
  that assumes otherwise.
- **The legacy shims are gone — do not go looking for them.**
  `core/scan_engine.py` (an `import *` shim over `core/scanning/engine.py`)
  and `core/trade_plan.py` (a deprecated adapter over
  `planning/plan_engine.build_strategy_plan`) were both removed 2026-08-15 by
  the v27 repo restructure, alongside the `core/scan_embeds.py`,
  `core/confidence.py` and `core/regime.py` shims that predated them (those
  three had no callers left even before v27). Every call site now imports the
  real module directly — `from swingbot.core.scanning import engine as
  scan_engine` is the live equivalent of the old `scan_engine.py` shim import,
  keeping the `scan_engine.*` vocabulary at usage sites unchanged.
- **Sizing and embed-building happen in `core/scanning/scan_run.py`'s
  alert-building loop** (inside `_sync_run_scan`: the heat / cluster /
  kill-switch stamps, then `build_embed()` and `build_simple_alert()`) —
  *not* in `commands/scanning/alerts.py::_send_alerts`, which only posts
  already-built tuples. Wiring sizing there is a silent no-op. The v2
  ticket's share count comes from `plan_table._sizing_snapshot`, called by
  `execution_embeds.build_ticket_embed`.
- **Add embed fields through the `sections[...]` accumulator** in
  `core/scanning/alert_embeds.py::build_embed`, never a raw
  `embed.add_field()` — the latter breaks `presentation.SECTION_ORDER`
  (`core/presentation/tokens.py`).
- **Every pushed message is styled by `core/presentation/kinds.py` (v110)
  and built as a `PushEmbed`.** Send it with
  `channel.send(**ui.push_kwargs(embed))`. A bare `send(embed=embed)` still
  posts, but silently drops the push-preview `content` line, which is the only
  text a phone notification shows. Command replies call
  `apply_chrome(accent=…)` and are deliberately not registry-styled.
- **Scan-loop ordering invariant:** ticker screens (liquidity, data quality)
  go *after* `update_open_trades`/`_check_near_close` and *before* the
  new-signal horizon loop, so an already-open paper trade keeps being
  monitored for SL/TP even on a day its ticker fails the screen.
- **An empty config table is not automatically an unfinished one.**
  `strategy_types.REGIME_ALLOW = {}` with `REGIME_GATES_ENABLED` defaulting off
  reads like a stub someone forgot to fill. It is the **measured answer**: the
  v17 P2a harness (`scripts/data/fill_regime_allow.py`) ran the pre-registered rule
  across 78 tickers × 11 strategies × 10 horizons on TRAIN and no cell cleared
  it, recorded in `docs/superpowers/results/2026-08-08-regime-allow-train.md`.
  The spec pre-committed to accepting that outcome. Filling the table by hand,
  or re-running with looser thresholds, undoes a closed pre-registration —
  see `docs/claude/backtest-methodology.md`. **Before "finishing" any empty
  table or default-off flag, grep `docs/superpowers/results/` for its name.**
- **An "unused import" here is often a deliberate re-export — check before
  deleting one.** A linter's unused-import list is not a delete list in this
  repo: `core/market/strategy.py` re-exports its `signals`/`strategy_types`
  split so `from swingbot.core.market.strategy import <anything>` keeps
  working, `core/scanning/engine.py` re-exports embeds symbols that callers
  reach directly now that the `core/scan_engine.py` `import *` shim is gone
  (removed 2026-08-15 by v27), and `admin/app.py` re-exports
  `docker_sdk`/`_SECTION_META` purely for `api_v1/system.py`. A
  2026-08-14 cleanup pass found **4 of 29** flagged imports were load-bearing
  this way. Before removing one, grep for both `from <module> import <name>`
  and `<module>.<name>` across `swingbot/`, `tests/` and `scripts/`. The known
  re-export blocks now carry `# noqa: F401` and a comment saying so — leave
  them.
- **`get_current_price()` serves a stale cached price by default — trading
  code must pass `allow_stale=False`.** The last-known-good fallback keeps a
  dashboard from blanking on one failed quote, and returns a price of any
  age. Anything that acts on the answer (the plan manager's `_price_fn`,
  `trade_monitor`, reversal and manual-close fills) passes
  `allow_stale=False` and skips on None: a repeated cached print counts as a
  fresh confirming tick for `EXTENDED_HOURS_DEBOUNCE_TICKS` (2) and fills at a
  price that stopped being current an unknown time ago (fixed 2026-09-11).
- **A trade row and its v2 plan close together, or the plan manager keeps
  managing a position that no longer exists.** `PlanManager.poll()` re-reads
  each plan after its price fetch (the admin closes plans from another
  process), `trade_monitor` ticks the manager even with no open trade rows,
  and `close_trade_reversed` closes the linked plan. A new path that closes
  a plan-linked trade row outside the manager must do the same
  (`performance._close_linked_plan_safely`).
- **Function names that don't exist** (plans and briefs guess wrong at these
  constantly — verify before use): there is no `market_events.days_to_earnings`
  (use `events.get_next_earnings_date` / `earnings_within_window`), no
  `jsonio.write_json` (use `atomic_write_json`), no `TradeLog().all_trades()`
  (use `get_trades(limit=None)`). **A plan file is a design document, not
  ground truth about the current code** — grep the symbol before you call it.
- Scans run through `map_tickers()` (`SCAN_WORKERS`, default 1 as of v56 --
  was 4, but measured directly against the real watchlist: cpu-time/wall-time
  stayed ~1.0x at every worker count 1-8, since the per-ticker work is
  pure-Python-glue-heavy, not vectorized enough to release the GIL for a
  useful stretch, so more threads bought no real parallelism and were
  measurably slower than serial). Anything touching shared state
  (`state.confirm_or_update`, funnel counters) must stay serial/post-join.
- **`market_data/daily/{TICKER}.csv` holds each ticker's FULL history since
  listing, not `DEFAULT_HISTORY_PERIOD` (2y)** — `data_store.load_normalized()`
  never trims it, so it grows every incremental refresh (11,500+ daily bars /
  45 years for AAPL on production). Anything in the scan hot path that scales
  worse than linear in `len(df)` will blow up on real data even though it
  looks fine against short synthetic test frames — see
  `trendlines.MAX_PIVOT_SCAN_BARS` (v56: an uncapped O(pivots³) trendline
  scan measured 6–9 SECONDS *per horizon* on AAPL/AMD, the direct cause of a
  production CPU-pegged-at-100% incident) before trusting a "should be fast"
  assumption about full-history algorithms here.
- **The live scan reads `market_data/daily/` now (v47).** `_crawl_latest_data`
  is cache-first: `_load_cached_daily()` serves any ticker whose CSV is fresher
  than `SCAN_CACHE_MAX_AGE_HOURS` (6h), and only the cold remainder is fetched.
  So the two OHLCV caches are no longer "backtest reads one, scan reads
  neither" -- `market_data/` is now on the live path, and a change to
  `data_store.load_normalized()` affects live alerts.
- **Cold fetches use PROCESSES, never threads** (`_fetch_cold_frames`). yfinance
  0.2.66's `download()` writes a shared module global (`_DFS`) non-reentrantly;
  a thread pool here once attributed one ticker's price data to another and
  logged both as open trades with identical values.
  `tests/scanning/test_no_cross_ticker_mixing.py` is the standing guard -- if
  you ever make this concurrent a different way, that test must still pass.
- **Trade History: filtering, sorting and paging must stay on the SAME side.**
  The dashboard's `ct-*` controls used to hide/reorder rows in the DOM while
  the server shipped up to 500 pre-rendered rows. Once paging moved
  server-side (plan v9; the route is `/api/v1/trades` now, the Jinja
  `/api/trade-history` having gone with Release B), any control left in the
  browser would silently operate on *the current page only* — a ticker filter
  would quietly mean "matches among these 25", which is worse than no paging
  at all. All six filters, all 14 sort columns and the pager go through
  `query_closed_trades()`, which survived the Jinja deletion precisely
  because it is builder-level and the v1 API uses it too. If you add a Trade
  History control, add it there too; do not filter or sort rows client-side.
  **The filter dropdown *options* used to be the deliberate exception** — the
  Jinja page built them from the FULL history via
  `dashboard.build_filter_options`, never from the loaded page, because values
  appearing only in older trades would otherwise become unselectable. The SPA
  answered that differently: the ticker filter is a free-text input, so there
  is no option list to go stale. `build_filter_options` had no caller left
  after Release B and was deleted on 2026-08-14. **If you ever reintroduce an
  enumerated filter dropdown, build its options from the full history
  server-side** — deriving them from the loaded page is the original bug.
- **Only four sources are still files, and only one is written atomically.**
  Every trading and operational store is a Postgres table (v116), so there is
  no `data/trades.json` to tear. The four file sources raise their SSE event
  themselves through `notify.publish` (`core/db/events.py` `FILE_PUBLISHERS`):
  `analytics_snapshot.json` (`jsonio.atomic_write_json`, temp file + fsync +
  `os.replace`), `scan_snapshots.json` (`core/scanning/snapshots.py`, plain
  `open(path, "w")` + `json.dump`: truncate, then fill, so a reader inside
  that window sees a torn document), `scan_telemetry.jsonl` (append-only; a
  torn trailing line is the reader's problem) and `.env` (`admin/helpers.py`
  `_write_env_text`, temp file + rename). The SPA refetches through the v1 API
  on the event, which parses; the 250ms trailing debounce puts that refetch
  after the write in practice, so the `scan_snapshots.json` race is narrow, not
  a live bug. Use `atomic_write_json` for any new file under `data/`.
- **A database write failure at issuance pauses scanning (`StoreWriteHalt`).**
  `core/db/write_failure.py` halts the scan loop rather than alert on a plan
  that was never recorded. Unpause from the admin UI after fixing the
  database; the unpause is the acknowledgement.

## `PlanManager.check_bar()` is unwired — do not "fix" it

## Scan parameter and replay gate parity (v74)

`ScanParams` is frozen and picklable so process-pool search cells cannot share
mutable config state. Historical replay has a horizon-expanded scenario gate;
the live scan preserves its snapshot plus OPEX and `!check` override path.
Do not silently unify them: v68 deliberately measured `min_confluence=1` and
`min_risk_reward=0.0`, unlike the shipped 2 and 1.5, and its fixture inherits
that population. `tests/backtesting/test_knob_observability.py` documents the
replay harness blind spots explicitly.

`check_bar` / `_check_bar_active` / `_check_bar_partial` model overnight gap fills and are tested, but production never calls them. The live bot exits exclusively through `poll()`. Keep the path inert: wiring it would create a second authority for the `plans` table. Change `_step_active` / `_step_partial` for live exits; mirror bar checks only to keep their tests honest.

## The full state machine now runs across the whole Berlin-local active window

Through v70, `PlanManager.poll()` routed a tick three ways: dark in the
Berlin-local quiet window, the full `_step()` machine only inside true NYSE
RTH (09:30–16:00 ET), and a narrow, debounced `_step_extended()` (terminal
exits only — no break-even arming, no TP1 banking, no trailing ratchet, no
PENDING fills) for everything else. That narrowness existed specifically to
avoid "Divergence B": a single thin premarket/after-hours print once armed
break-even permanently or closed a position outright, on a print the
daily-bar backtest never modeled.

**2026-09-14, on direct request, that boundary is gone.** `poll()` now
treats "regular" as simply "not quiet hours" — `_step()` (the whole state
machine, single tick, no debounce) runs for all of it:

| Clock (with `INTRADAY_RTH_ONLY` on) | Path | What it may do |
|---|---|---|
| Quiet window (`QUIET_HOURS_START_BERLIN`–`QUIET_HOURS_END_BERLIN` Berlin time, all weekend Berlin-local) | none | nothing at all |
| Everything else | `_step()` | the whole state machine — break-even arms, TP1 banks, the trailing ratchet moves, PENDING plans fill, all off any single tick, premarket/after-hours included |

The operator explicitly accepted the Divergence B risk this reopens: a real
resting-order equivalent will now act on a thin extended-hours print exactly
like it acts on an RTH one, with no debounce cushion in between.

**`_step_extended()`, `_extended_candidate_active`/`_extended_candidate_partial`,
and the debounce map (`_eh_breach_streak`) are consequently unreachable from
`poll()` in normal (`INTRADAY_RTH_ONLY` on) operation** — nothing calls them.
Left in place rather than torn out in the same change that stopped calling
them; `tests/planning/test_plan_manager_extended_hours.py`'s direct
`_step_extended()`-calling tests still correctly describe what that function
does, they just no longer describe what `poll()` does. A follow-up should
remove the function and that half of the test file properly.

**The trap this leaves:** a new exit/entry rule only needs to go in
`_step_active`/`_step_partial`/`_step_pending` now — there is no second path
to keep in sync. If you find yourself reaching for
`_extended_candidate_active`/`_partial` to mirror a rule there, stop: that
code is dead weight, not a second call site to maintain.

One more property worth knowing: **`poll()` now records `_last_seen` on
every non-quiet tick**, premarket/after-hours included (previously "regular
branch only"). That map feeds `_continuous()`, which lets a stop fill *at
the stop* instead of at the observed price — an extended-hours print is no
longer the case where "nobody watched the tape cross"; the operator asked
for it to be watched.

## The dead-cat-bounce veto is invisible to `run_backtest_range.py`

It lives on the confluence path (`build_scenarios`), which the strategy
backtest never reaches. Measuring it needs `backtest_scenarios.py` — the same
split that made v34's `RS_GATE` need its own instrument
(`measure_rs_gate_effect.py`) and that made `DATA_DRIVEN_STOPS_ENABLED`
unmeasurable by construction. v68 built its own instrument
(`scripts/backtest/measure_dcb_veto.py`) for the same reason; it FAILed
VALIDATION (see `docs/claude/backtest-methodology.md`'s closed-pre-registration
table) and ships default-off, but the invisibility trap outlives that
particular result — any future confluence-path-only gate needs its own
purpose-built measurement script, never `run_backtest_range.py`.

## The level-lifecycle stop breaches the 2% cap in the backtest

Every builder caps a strategy stop at `capped_planned_loss_pct(...) = 2%`, but
`apply_level_lifecycle` (`LEVEL_LIFECYCLE_STOPS_ENABLED`, default **on**) runs
afterwards on both paths. It widens the stop behind a tested level, bounded by
the horizon's `max_risk_pct` (3–11%), **not** by 2%. Live, a pending plan whose
fill would exceed 2% is cancelled (`plan_manager.py`, `cancelled_risk_cap`).
The backtest has no such check, so it scores trades live would never open.

Found 2026-09-25 by a spot check: 5 tickers x Fibonacci/MACD/Support-Resistance
x 4w/3m/6m, v2 exits with scale-out.
- **Lifecycle on:** 22 of 83 trades had an initial stop over 2%, the worst at 8.87%.
- **Lifecycle off:** the worst was exactly 2.00%.

Every post-cap TRAIN/VALIDATION figure (v101–v103 included) was measured
with this gap in place. Detail: `docs/strategy-types/shared-mechanics.md` §4a.

**Fixed by v104 Part 0 (V104-2):** the widening ceiling is now
`stop_scope.stop_ceiling(...)` -- 2% out of scope. Numbers measured before
this fix are not comparable to numbers after it.

## Editing production `.env` with `sed -i` changes nothing live

`docker-compose.yml` bind-mounts `.env` as a single file, which tracks the
inode. `sed -i`, and any other tool that writes a temp file and renames it,
leaves both containers reading the old inode. The admin UI then saves into
that orphan, and the bot's reload never fires. Found 2026-09-30, when a
`MIN_STOP_DISTANCE_PCT` edit showed on the host but read 2.0 in the container.

- **Edit in place:** `python3 scripts/ops/env_set.py KEY value` (edits in
  place, then snapshots the file), nano, or `cat new > .env`.
- **Or recreate:** `SWING_BOT_IMAGE=<running sha- image> docker compose up -d
  --force-recreate --no-build --wait bot admin`. Without `SWING_BOT_IMAGE`,
  compose falls back to the non-existent `swing-bot:latest`.
- **Verify:** `docker compose exec -T bot grep <KEY> /app/.env`.

## Stop floor and 2% cap: the empty band, and the v115 clamp

`f01e87e2` rejects any plan with a stop over 2% (`risk_cap` in
`attach_plan_v2`). With `MIN_STOP_DISTANCE_PCT` >= 2.0, only a stop of exactly
2.0% survived, and production posted nothing from Sep 25 to Sep 30. A replay
on live data gave 0 setups at a 2.0 or 1.5 floor and 10 at 1.0, so production
ran 1.0 as a stopgap on 2026-09-30.

**v115 (`CLAMP_STOP_TO_HARD_CAP`, default on)** moves a wider confluence stop
to **1.75%** from the trigger inside `build_confluence_plan`, before target
selection. That is the 2% cap minus `CLAMP_HEADROOM_PCT` (0.25, a constant in
`builders.py`). The floor is back at 2.0 (production back on 2.0 since
2026-09-30 20:44 UTC, when the v115 image was live). The `risk_cap` reject in `attach_plan_v2` stays as a safety net.

- **Why 1.75, not 2.0.** `plan_manager._step_pending` cancels a stop-entry
  fill `risk_cap` when `planned_loss_pct(fill, stop) > 2.0`, with no
  tolerance. A stop at exactly 2% is cancelled on any fill past the trigger,
  and float rounding can tip a stop at exactly 2% over the cap.
  0.25% of headroom absorbs a small gap. A fill more than about 0.25% past
  the trigger is still cancelled `risk_cap`: that is the 2% policy working,
  not a bug.

- **With the clamp off, the empty band comes back.** A funnel of "N checked ->
  N no entry point" or a run of `risk_cap` rejects is this band, not a data
  fault.
- **Replay clamps by default.** `replay_scenarios` and `armed_replay.plan_at`
  call `build_confluence_plan`. Confluence replay numbers produced before
  v115 used the unclamped stop and are not comparable to later ones. To
  reproduce them, set `CLAMP_STOP_TO_HARD_CAP=false`. The backtest has no
  fill guard, so it never models a gap cancel: live can cancel a clamped
  plan that replay fills.
- `armed_replay.plan_at` stores the scenario's **unclamped**
  `stop_distance_pct` while its plan carries the clamped stop. Read the stop
  off the plan, never off that field. This is known and deliberately left
  unchanged.
- A clamped stop sits at no structural level. It reaches an alert only with
  `PLAN_ENGINE_V2=on`, and then the clamped stop shows everywhere in the
  alert: plan table, chart, ticket, headline, simple mirror and explanation.
  The stop % and R come from the v2 plan **only when the stop was clamped**
  (`explain.v2_stop_was_moved`, used by `plan_table.stop_figures_for_display`);
  every other alert, and every target figure, is unchanged. In `shadow`, the
  scenario's unclamped stop is what posts.
- v114 (a 1.5-2.0 band, measured before shipping) was abandoned before any
  build on 2026-09-30 (`no-lift/`), with its VALIDATION shot unspent. It is
  still the measured route if the partner later wants the band instead of
  the clamp.

## Futures skipped for dollar volume is deliberate (v115)

`SI=F: skipping new-signal scan -- avg dollar vol $0.1M < $20M floor` is the
configured behaviour, not a bug. Yahoo reports futures volume in contracts and
FX/index volume as 0. `4a649b36` exempted those classes. v115 put that
exemption behind `LIQUIDITY_EXEMPT_NON_EQUITY`, default **off**, to restore
the 09-22 scan. Turn it on to scan thin-contract futures again. The v109 spot
metals (`spot_metals.SPOT_PAIRS`: XAUUSD, XAGUSD) stay exempt either way
(partner, 2026-09-30). They carry their future's contract volume, so XAGUSD
scans while SI=F, on the same bars, is skipped. That is by design.

## The market_data cache never self-heals (v116 follow-up)

`data_refresh._merge_save` is a UNION that never overwrites bars already on disk, and a warm
refresh fetches only bars newer than the last cached one; `refresh_symbol(force=True)` merges
too. So a single bad full fetch is permanent: around 2026-08-05 16 daily and 5 hourly files
(PLTR, SNOW, SOFI, SBUX, TSLA, ... AVGO, AXON, BA, BKNG, CRM) ended up with another
instrument's older history (SOFI started in 2000, TSLA in 1992, SNOW and PLTR shared one
row count and start date), with correct recent bars appended on top for two months. The
signs: the scan found almost nothing for those tickers, and `history_splice` refused to
splice them ("overlap closes disagree").

- **Audit and repair with `scripts/ops/market_cache_repair.py`** (`plan` is read-only;
  `apply` quarantines each bad file under `market_data/_quarantine/<stamp>/` and refetches it
  cold, only when the fresh frame agrees with Alpaca). Re-run `plan` after any suspicious
  refresh or provider change; it should print only `OK`.
- **Never "fix" one by deleting rows or forcing a refresh**: a forced refresh merges, so the
  wrong older bars survive. Move the file away first, then refetch.
- Weekly/monthly files differ from a fresh yfinance download by a small uniform offset
  (adjustment basis); that is not this problem and is deliberately not repaired.
