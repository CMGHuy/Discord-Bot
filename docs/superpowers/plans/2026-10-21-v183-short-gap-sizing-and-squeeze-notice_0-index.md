# v183 — Gap-aware short sizing, and a squeeze/event notice on every short: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V183-4:" -A 300 docs/superpowers/plans/2026-10-21-v183-short-gap-sizing-and-squeeze-notice_1-gap-sizing-core.md`.

**Bump:** bot minor, ui patch
**Edge:** none (integrity) — both parts control and disclose short-side risk; R stays defined on the stop, so neither part moves win rate or ExpR in R. Part A lowers dollar loss on a gap through a short's stop (and dollar profit on the same names).
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md](../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md)
**Brief:** `.superpowers/briefs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice.md`
**Worktree:** implement every task in `.claude/worktrees/2026-10-21-v183-short-gap-sizing-and-squeeze-notice` (branch of the same name, created in V183-1's first step; `docs/claude/document-lifecycle.md`). The merge to `main` is V183-17's last step.

## Goal

The partner wants short trades planned better. Two short-specific risks named
in the sources (Schwab, CMC Markets) are not handled live today. First, the
2% per-trade cap is a **dollar** cap, but live sizing turns it into shares
using only the stop distance. A short whose stop is gapped through at the open
(a squeeze gap) can lose several times the configured dollar risk. Second, the
partner never sees, before entry, the usual squeeze warning signs (short
interest, days to cover, float) or the catalysts inside the hold (earnings,
ex-dividend). The backtests already fill gaps at the open; the live book and
the alerts do not account for them.

Once this ships, every new **short** plan is sized so that a gap as large as
the ticker's routine bad up-gap still stays inside the dollar risk. The
routine bad up-gap is the 99th percentile of up-gaps over the last 250
completed daily bars. Its size is
`max(|entry − stop|, entry × p99_up_gap / 100)`. The tightest existing cap
still wins after that. The p99 value and the on/off state of the rule are
stamped on the plan when it is created. All seven places that size a trade
read that stamp, so the alert, the dashboard, the execution feed and the
paper book always show the same share count. The alert's order block shows
the stop risk and the gap risk together, and says when the size was cut. The
admin risk page adds one number: the summed gap risk of open shorts, shown
beside heat. Every short alert, on every lane, also gains notice lines:
short interest with its report date (a ⚠ when a squeeze threshold trips), an
earnings line with the sessions to the report, and an ex-dividend line. A
daily bot loop refreshes the short-interest data off the scan path. The alert
reads only that cache. The notice values are saved with the plan, so the plan
page shows exactly what the alert said.

The plan leaves the rest untouched. Longs stay byte-identical in sizing,
alerts and stored records, pinned by regression tests. Nothing blocks,
rejects or moves a plan's entry, stop or target. No backtest, screen or
replay changes; in particular, nothing live-only enters `entry_context`.
R, win rate, ExpR and heat-in-R are computed exactly as before. Two
switches turn each part off without a deploy: `SHORT_GAP_SIZING` and
`SHORT_RISK_NOTICE`. Off reproduces today's short output byte for byte.

Success is measured three ways. The tests pin each case: longs unchanged;
switches off unchanged; the gap cut only ever shrinks size, in every sizing
mode and on every lane; the alert and paper book agree on shares; a gap fill
books its real R; a notice failure never stops a scan or an alert; every
channel words the notice the same. After the build, one read-only results
doc re-sizes the live book's closed shorts under the rule. It reports how
often the rule cuts size, by how much, the dollar P&L, the five worst dollar
losses and the short book's max drawdown, before and after. Until that doc
exists the cut is unvalidated, and `SHORT_GAP_SIZING=false` is the revert
path.

## Architecture

- **Config (V183-1).** Four `swingbot/config.py` Fields, hot-reloaded, plus `.env.example`: `SHORT_GAP_SIZING` (checkbox, default on), `SHORT_RISK_NOTICE` (checkbox, default on), `SHORT_SQUEEZE_SI_PCT` (float, 10), `SHORT_SQUEEZE_DTC` (float, 5). V183-1 also creates the worktree.
- **Adverse-side gap statistic (V183-2).** `gap_stats` gains `p99_up_gap_pct` (99th percentile of `Open / prev Close − 1 > 0`, in %, `None` when there are no up-gaps) and `n_up`. Its three existing keys and every caller stay unchanged.
- **Gap floor in the sizer (V183-3).** `compute_position_size(..., gap_floor_pct=None)`. With `None` (every long, every switch-off short, every existing caller) the function is byte-identical. With a value, the risk-to-shares division and the `MAX_RISK_AMOUNT_ABSOLUTE` cap use `sizing_distance = max(stop_distance, entry × gap_floor_pct / 100)`. `risk_amount` stays final shares × stop distance. The result gains `gap_risk_amount`, `gap_sized` and `gap_floor_pct`. The new logic lives in two named helpers, so the legacy complexity of 18 does not rise. Every edge mode (`kelly`, `vol_target`, `min_of_all`) is rewritten to `risk_pct` before the branch, so they share it. `account_pct` is reached only through the absolute risk cap.
- **One sizing path (V183-4).** New module `swingbot/core/planning/gap_sizing.py`.
  - `gap_sizing_stamp(df, direction)` is computed once at plan creation, from completed bars. It returns `None` for a long, else `{"rule", "up_gap_p99_pct", "n_up_gaps"}`.
  - It is stored as the new top-level field `TradePlanV2.gap_sizing`, **not** in `entry_context`. `entry_context` is also built in backtests, and the rule state is live config.
  - `size_for(...)` / `size_for_plan(...)` / `size_for_trade(...)` are the only sizing entry points, and they read only the stamp. A long, or a stamp with rule `"stop"`, calls `compute_position_size(entry, stop_loss, account_cfg)` exactly as today. A failure in the gap path logs one line and falls back to stop-only sizing.
  - The stamp is written at the two live plan-creation sites (`analyze.py` beside `stamp_entry_context`, `strategy_pass.build_strategy_plan_at`), never inside `stamp_entry_context`.
- **Re-size sites (V183-5).** `plan_table._sizing_snapshot`, `outlook_run._risk_dollars`, the admin dashboard sizing map and `analyze.build_decision_context` call `size_for_plan` / `size_for_trade`. `stop_scope.risk_sizing_ok` (the seventh site) is untouched: it runs before the stamp exists, and a gap cut only lowers shares.
- **Paper book (V183-6).** `TradeLog.log_trade(..., gap_sizing=None)` and `record_plan_fill` size through `size_for`. `record["gap_sizing"]` is written only when the stamp is not `None`, so long records stay byte-identical. A failure logs one line and falls back to stop-only sizing, never to unsized. All four `log_trade` callers pass `plan_v2.gap_sizing`.
- **Invariants (V183-7).** Tests only: per lane, the cut never raises a capped quantity (candidate heat/cluster inputs unchanged, open heat ≤ stop-sized, stop distance unchanged); a gap fill books its real R; longs byte-identical on a fixed plan set.
- **Order-block line (V183-8).** `swingbot/core/presentation/gap_risk.py` words `Risk $X at stop · $Y on a p99 gap (Z%)`, plus `· size cut for gap risk` when cut, or `· gap risk n/a` when there is no p99. Discord full, simple, the v81 ticket and email/push all call it.
- **Risk view (V183-9).** `get_risk()["heat"]` gains `gap_risk_amount` and `gap_risk_unknown`; the risk page shows them beside heat at three widths. Display only.
- **Notice data (V183-10, V183-11).** `swingbot/core/market/short_interest.py` holds a per-ticker cache in `data/short_interest.json`, written with the `earnings_history.py` file pattern (`atomic_write_json` / `read_json`), so no table and no Alembic revision. `parse_info` normalises yfinance `.info`. `refresh_short_interest` runs from a new daily bot loop `daily_short_interest_refresh`, placed beside `weekly_earnings_refresh`. The alert path calls only `cached_short_interest` (disk) and `request_refresh` (queues a miss).
- **Notice snapshot (V183-12).** `swingbot/core/scanning/risk_notice.py`.
  - `build_risk_notice(plan, signal_date)` reads the cache and computes the hold window: the signal bar through `expiry_bars + HORIZONS[h]["max_holding_days"]` sessions, on the NYSE calendar.
  - It reads earnings through `earnings_calendar.CachedSource` and `next_report` (never the network), and the ex-div date from the same cache.
  - `stamp_risk_notice` stores the result on the new field `TradePlanV2.risk_notice` at the same two live sites. Any exception yields the degraded snapshot ("not checked"), never a raise.
- **Wording (V183-13).** `short_notice.risk_notice_lines(snapshot)` is the one wording function. `alert_notice` appends the lines and `CHECK BORROW AVAILABILITY` for any plan carrying a snapshot. The `notifier._short_notice` and `alert_embeds._short_notice_text` gates widen through `has_risk_notice`, so every short gets the field. Longs and switch-off shorts are unchanged.
- **Plan page (V183-14, V183-15).** `log_trade(..., risk_notice=None)` copies the snapshot onto the paper record. `_plan_detail` / `_legacy_detail` return `risk_notice_lines` (the same `risk_notice_lines` output) and a `gap_sizing` block. `plan-detail.ts` shows both inside the levels/order block at phone, tablet and desktop widths. A parity test covers Discord full, simple, email/push and the plan-page API.
- **Impact and release (V183-16, V183-17).** `scripts/reports/short_gap_sizing_impact.py` re-sizes the live book's closed shorts from cached daily bars (read-only; `/replicate-prod-db` first) and writes the results doc, including the rollback note. V183-17 bumps the versions, runs the single full suite and merges.

## Global Constraints

- **Longs byte-identical.** A `"bullish"` plan or trade never reaches the gap branch or the notice: `compute_position_size` result dict, every alert text, every stored plan/trade key set and value unchanged. Pinned in V183-6, V183-7, V183-13. Directions are `"bullish"` / `"bearish"`; a short is `"bearish"`.
- **Switch off = today, byte for byte.** `SHORT_GAP_SIZING` off at plan creation stamps rule `"stop"` and sizing returns exactly `compute_position_size(entry, stop_loss, account_cfg)`. `SHORT_RISK_NOTICE` off stamps no snapshot and every channel's text is unchanged. A switch flip later never changes an already-stamped plan's rule.
- **The 2% cap is dollar risk (partner).** The stop is never moved to fit. The gap floor only ever shrinks shares (`sizing_distance ≥ stop_distance`), in every sizing mode. `risk_amount` keeps its meaning: final shares × stop distance.
- **No filter, veto, gate or score reads any v183 value.** `gap_sizing` and `risk_notice` feed only sizing and display. V183-12 pins that no scan decision changes when the notice data changes.
- **Nothing live-only enters `entry_context`** (it is built in backtests: `backtest_scenarios.py:214`). Neither `gap_sizing` nor `risk_notice` is an `entry_context` key, and `FEATURE_KEYS` is not edited.
- **No network on the scan or alert path.** The alert reads `cached_short_interest` and `CachedSource` only. yfinance `.info` is called only from `refresh_short_interest`, run by the daily loop through `asyncio.to_thread`.
- **Missing is never comfort.** A missing field prints `n/a`; a cache miss prints `⚠ Squeeze data not checked — verify short interest at your broker`; a ticker absent from the earnings calendar prints `Earnings: not checked`. Short interest older than 21 days carries `STALE`, and a forward dividend amount carries `est.`. Every short-interest figure carries its `as of` date.
- **Thresholds:** squeeze ⚠ when short interest ≥ `SHORT_SQUEEZE_SI_PCT` (10) % of float **or** days to cover ≥ `SHORT_SQUEEZE_DTC` (5). Usable p99 needs `n_up ≥ MIN_UP_GAPS = 60` up-gaps over `LOOKBACK = 250` bars.
- **Plan docs omit None v183 fields** (controller ruling): `plan_to_dict` drops `gap_sizing` / `risk_notice` while they are `None` (`plan_types._OMIT_WHEN_NONE`), never writing `null`, so long plan docs stay byte-identical; V183-4 pins the long plan-doc key list.
- **Storage** (`docs/claude/schema-evolution.md`): `TradePlanV2.gap_sizing` / `.risk_notice` and trade keys `gap_sizing` / `risk_notice` are "add" operations landing in `doc`, so there is no Alembic revision. The cache is a file under `data/`. There is no read-time upcasting.
- **Complexity < 15** for every function written or changed (`scripts/dev/complexity_gate.py`). Legacy functions must not rise: `compute_position_size` (18), `TradeLog.log_trade` (15), `build_decision_context` (24), `alert_embeds.build_embed` (33). New logic goes in named helpers, and no branch is added to those four.
- **Channel parity:** Discord full, Discord simple, email, push and the plan-page API take notice text only from `short_notice.risk_notice_lines`, and the gap line only from `gap_risk.gap_risk_line`.
- **UI:** the risk-page figure and the plan-page lines are designed and checked at phone (375), tablet (768) and desktop (1280) widths (`docs/claude/ui-design.md`).
- **Tests:** per-task verification is `python scripts/dev/testrun.py file <test>`, plus `cd frontend && npx ng test --watch=false --include=<spec>` for frontend specs. The full suite runs once, in V183-17. New test files go in existing `tests/` directories only, so `tests/suites.toml` is not edited.
- **Commits:** one scoped commit per task on the worktree branch. Never commit on `main` before V183-17's merge. Never touch v182 plan files (a concurrent session).

## Contracts

### Config (V183-1)

```python
# swingbot/config.py — read as config.<NAME>, the same way existing checkbox Fields
# (e.g. SHORT_UNIVERSE_ENABLED) are read; hot-reloadable, categorised in _SEARCH_CLASSES like their neighbours
SHORT_GAP_SIZING      # checkbox, default "true",  section "Account Defaults"
SHORT_RISK_NOTICE     # checkbox, default "true",  section "Universe & Scanning"
SHORT_SQUEEZE_SI_PCT  # float,    default "10.0", min 1,  max 100, step 0.5
SHORT_SQUEEZE_DTC     # float,    default "5.0",  min 0.5, max 30, step 0.5
```

### Gap statistic (V183-2)

```python
# swingbot/core/edge/gates.py
def gap_stats(df, lookback=250) -> dict
    # existing: "p90_gap_pct", "p99_gap_pct", "n" (absolute gaps, unchanged)
    # added:    "p99_up_gap_pct": float | None   (percentile over gaps > 0 only, in %; None when none)
    #           "n_up": int                       (count of gaps > 0)
    # empty frame: {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0, "p99_up_gap_pct": None, "n_up": 0}
```

### Sizer (V183-3)

```python
# swingbot/core/planning/account.py
def compute_position_size(entry, stop_loss, account_cfg=None, *, strategy_stats=None,
                          ticker_atr_pct=None, open_positions=0,
                          gap_floor_pct: float | None = None) -> dict | None
    # gap_floor_pct None -> result identical to today (no new keys)
    # else adds: "gap_risk_amount": round(shares * sizing_distance, 2), "gap_sized": bool, "gap_floor_pct": float
def _sizing_distance(entry: float, stop_distance: float, gap_floor_pct: float | None) -> float
def _gap_fields(shares: float, uncut_shares: float, sizing_distance: float, gap_floor_pct: float | None) -> dict  # {} when None
    # gap_sized = round(shares, 2) < round(uncut_shares, 2): the floor really lowered the final share count
    # (uncut_shares = the same cap chain run on the stop distance), so a binding position cap never reads as a gap cut
```

### One sizing path (V183-4)

```python
# swingbot/core/planning/gap_sizing.py
RULE_GAP = "gap_p99"; RULE_STOP = "stop"; MIN_UP_GAPS = 60; LOOKBACK = 250
def gap_sizing_stamp(df, direction: str) -> dict | None
    # None unless direction == "bearish"; else
    # {"rule": RULE_GAP if config.SHORT_GAP_SIZING else RULE_STOP,
    #  "up_gap_p99_pct": float | None  (None when n_up < MIN_UP_GAPS), "n_up_gaps": int}
def stamp_gap_sizing(plan, df) -> None          # plan.gap_sizing = stamp; never raises (exception -> stamp with p99 None)
def gap_floor_for(direction: str | None, gap_sizing: dict | None) -> float | None
def size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label: str = "") -> dict | None
    # not bearish, or rule RULE_STOP        -> compute_position_size(entry, stop_loss, account_cfg) exactly
    # bearish, rule RULE_GAP, p99 present   -> compute_position_size(..., gap_floor_pct=p99)
    # bearish, stamp None or p99 None       -> plain result + {"gap_risk_amount": None, "gap_sized": False, "gap_floor_pct": None}
    # exception in the gap path             -> log.info("%s: gap sizing fell back to stop (%s)", label, reason); plain result
def size_for_plan(plan, entry=None, account_cfg=None) -> dict | None   # entry defaults to plan.trigger_price or plan.entry_price
def size_for_trade(trade: dict, entry=None, account_cfg=None) -> dict | None   # entry defaults to trade["entry"]
def gap_risk_amount_for(shares, entry, stop_loss, gap_sizing) -> float | None  # None without a usable p99 or for rule stop

# swingbot/core/planning/plan_types.py
TradePlanV2.gap_sizing: dict | None = None      # restored by plan_from_dict; plan_to_dict OMITS the key while None
_OMIT_WHEN_NONE = ("gap_sizing",)              # plan_types.py; V183-12 appends "risk_notice" -- a None field is never written as null,
                                                # so every long (and every unstamped) plan doc stays byte-identical (controller ruling)
```

### Paper book (V183-6, V183-14)

```python
# swingbot/core/tracking/performance.py
TradeLog.log_trade(..., gap_sizing: dict | None = None, risk_notice: dict | None = None)
    # record["gap_sizing"] / record["risk_notice"] written ONLY when not None (risk_notice: V183-14)
TradeLog.record_plan_fill(plan_id, fill_price) -> str | None   # re-sizes through size_for_trade(t, fill_price)
def _paper_sizing(entry, stop_loss, direction, gap_sizing, label) -> dict | None   # V183-6 helper; logged fallback
```

### Display (V183-8, V183-9)

```python
# swingbot/core/presentation/gap_risk.py
GAP_CUT_TEXT = "size cut for gap risk"; GAP_NA_TEXT = "gap risk n/a"
def gap_risk_line(sizing: dict | None, *, currency: str = "$") -> str | None
    # None when sizing is None or has no "gap_sized" key (longs, rule stop, pre-v183 plans)
    # "Risk $200 at stop · $340 on a p99 gap (2.8%) · size cut for gap risk"  | "Risk $200 at stop · gap risk n/a"

# GET /api/v1/risk  -> body["heat"] gains
#   "gap_risk_amount": number | None   (sum over open bearish trades with a usable p99; None when none)
#   "gap_risk_unknown": int            (open bearish trades without a usable p99)
```

### Notice data (V183-10, V183-11)

```python
# swingbot/core/market/short_interest.py
CACHE_NAME = "short_interest.json"            # os.path.join(config.DATA_DIR, CACHE_NAME)
STALE_DAYS = 21
class ShortInterestCacheError(Exception)
def parse_info(info: dict, *, today: dt.date) -> dict
    # {"short_pct_float": float|None (percent, 18.2 not 0.182), "days_to_cover": float|None,
    #  "float_shares": float|None, "si_date": "YYYY-MM-DD"|None, "ex_div_date": "YYYY-MM-DD"|None,
    #  "div_per_share": float|None, "div_estimated": bool, "fetched_at": iso}
def fetch_short_interest(ticker: str) -> dict          # yfinance .info -> parse_info; raises on failure
def refresh_short_interest(symbols, *, now=None, fetch=None) -> dict   # {"updated": int, "failed": list[str]}
def cached_short_interest(ticker: str) -> dict | None  # disk only; None on miss; ShortInterestCacheError on unreadable file
def request_refresh(ticker: str) -> None               # queue a miss for the next refresh; never raises
def refresh_symbols() -> list[str]                     # watchlist ∪ short-lane universe ∪ open/pending bearish tickers ∪ queued

# swingbot/commands/scanning/loops.py
@tasks.loop(minutes=1) async def daily_short_interest_refresh()   # job "daily_short_interest_refresh", once per weekday after the close
```

### Notice snapshot and wording (V183-12, V183-13)

```python
# swingbot/core/scanning/risk_notice.py
def hold_window(plan, signal_date: dt.date) -> tuple[dt.date, dt.date]
def build_risk_notice(plan, signal_date: dt.date, *, now=None, source=None) -> dict
    # {"version": 1, "built_at": iso, "window": [start_iso, end_iso],
    #  "si_status": "ok" | "not_checked", "short_interest": {parse_info fields + "stale": bool} | None,
    #  "earnings": {"status": "in_hold" | "none_in_hold" | "not_checked" | "etf", "date": iso|None, "sessions": int|None},
    #  "ex_div": {"date": iso, "per_share": float|None, "estimated": bool} | None}
def degraded_notice(plan, signal_date) -> dict          # every line in its "not checked" form
def stamp_risk_notice(plan, df) -> None                 # bearish + SHORT_RISK_NOTICE only; never raises

# swingbot/core/planning/plan_types.py
TradePlanV2.risk_notice: dict | None = None     # appended to _OMIT_WHEN_NONE: omitted from plan_to_dict while None

# swingbot/core/presentation/short_notice.py
SQUEEZE_PREFIX = "⚠ SQUEEZE RISK · "
SQUEEZE_NOT_CHECKED = "⚠ Squeeze data not checked — verify short interest at your broker"
EARNINGS_NOT_CHECKED = "Earnings: not checked"
def squeeze_tripped(si: dict) -> bool
def risk_notice_lines(snapshot: dict | None, *, currency: str = "$") -> list[str]   # [] for None
def has_risk_notice(plan_v2) -> bool
alert_notice(plan_v2, context, nums, *, currency="$") -> str   # appends lines + BORROW_TEXT when has_risk_notice
```

### Plan-page API (V183-14)

```python
# swingbot/admin/api_v1/trades.py: _plan_detail / _legacy_detail detail gains
"risk_notice_lines": list[str] | None    # risk_notice_lines(snapshot) from plan doc, else trade record; None without one
"gap_sizing": {"rule": str, "up_gap_p99_pct": float | None, "shares": float | None,
               "risk_amount": float | None, "gap_risk_amount": float | None,
               "gap_sized": bool, "line": str | None} | None      # None for longs / unstamped
```

## Review Focus

1. **A requoted or rebuilt short** (short lane `_rebuild_fn`, the outlook requote) must carry the same `gap_sizing` stamp as the plan first alerted. Otherwise the alert and the paper book diverge. V183-4 pins a rebuilt plan keeping its stamp, and V183-6 pins the alert and paper share counts.
2. **The `plan_manager` fallback `log_trade`** (a fill with no placeholder) must size a short the same way the alert did. V183-6 passes `plan.gap_sizing` there and tests it.
3. **yfinance gives `shortPercentOfFloat` as a fraction (0.182) and `dateShortInterest` as epoch seconds.** `parse_info` must print `18.2%` and an ISO date, never `0.2%` or a raw integer. Tested in V183-10.
4. **A corrupt or half-written `short_interest.json`** must degrade every short's notice to "not checked" while the scan and the alert carry on. Tested in V183-12, which raises inside the cache read.
5. **A hold window spanning NYSE holidays.** Earnings sessions-away and the window end are counted in NYSE sessions, not calendar days. An ETF prints `Earnings: n/a (ETF)`, never `No earnings in hold` and never `not checked`. Tested in V183-12.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V183-1 | V183-2 (after V183-1's worktree step) | first task: creates the worktree; its Fields are read by V183-4 and V183-10..V183-13 |
| V183-2 | V183-1, V183-3, V183-10 | disjoint file `edge/gates.py`; no contract dependency |
| V183-3 | V183-2, V183-10 | disjoint file `planning/account.py`; no contract dependency |
| V183-4 | V183-10 | after V183-1, V183-2, V183-3: reads `SHORT_GAP_SIZING`, `p99_up_gap_pct`/`n_up` and `gap_floor_pct` (contract dependency) |
| V183-5 | V183-6 | after V183-4: calls `size_for_plan` / `size_for_trade`; files `plan_table.py`, `outlook_run.py`, `dashboard.py`, `analyze.py` are disjoint from V183-6 |
| V183-6 | V183-5 | after V183-4: calls `size_for` and reads `plan.gap_sizing`; same file `strategy_pass.py` as V183-4 |
| V183-7 | V183-8, V183-9 | after V183-5 and V183-6: tests exercise both the re-size sites and the paper book |
| V183-8 | V183-7, V183-9 | after V183-5: the gap line reads the gap keys `_sizing_snapshot` now returns |
| V183-9 | V183-7, V183-8 | after V183-4 (`gap_risk_amount_for`) and V183-6 (trade records carry `gap_sizing`); edits `frontend/src/app/api/models.ts`, so never alongside V183-15 |
| V183-10 | V183-2..V183-9 | after V183-1 (Fields); new files only, no contract dependency on Part A |
| V183-11 | V183-12 | after V183-10: calls `refresh_short_interest` / `refresh_symbols` |
| V183-12 | V183-11 | after V183-10 (cache API), V183-4 (same files `analyze.py`, `strategy_pass.py`, `plan_types.py`) and V183-6 (same file `strategy_pass.py`) |
| V183-13 | — | after V183-12 (snapshot shape) and V183-8 (same files `alert_embeds.py`, `notifier.py`) |
| V183-14 | V183-16 | after V183-13 (`risk_notice_lines`), V183-6 (same `log_trade` signature and call sites) and V183-8 (`gap_risk_line`) |
| V183-15 | V183-16 | after V183-14: renders the new detail keys; after V183-9 too (same file `frontend/src/app/api/models.ts`), never alongside it |
| V183-16 | V183-14, V183-15 | after V183-7: re-sizes with the finished sizing code; new files only |
| V183-17 | — | after every other task: the plan's single full-suite run, then bump and merge |

At most 2 implementers at once (shared tree, CPU). Suggested pairs: V183-2 + V183-3, then V183-4 + V183-10, V183-5 + V183-6, V183-7 + V183-8, V183-9 + V183-11, V183-14 + V183-16.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-21-v183-short-gap-sizing-and-squeeze-notice_1-gap-sizing-core.md` | V183-1..V183-5 | switches and worktree, up-gap p99, gap floor in the sizer, the one sizing path and plan stamp, the four re-size sites |
| 2 | `2026-10-21-v183-short-gap-sizing-and-squeeze-notice_2-paper-book-display-and-risk-view.md` | V183-6..V183-9 | paper-book sizing with logged fallback, cap/R/long invariants, order-block gap line on every channel, risk-view gap figure |
| 3 | `2026-10-21-v183-short-gap-sizing-and-squeeze-notice_3-squeeze-event-notice.md` | V183-10..V183-15 | short-interest cache and daily loop, notice snapshot, one wording module on every short, paper record and plan-page API parity, plan-page UI |
| 4 | `2026-10-21-v183-short-gap-sizing-and-squeeze-notice_4-impact-release-and-full-suite.md` | V183-16..V183-17 | live-book impact results doc with rollback note, version bump, full suite, merge |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V183-1 | Worktree and the four v183 switches | 1 | haiku | M `swingbot/config.py`, `.env.example`; C `tests/planning/test_v183_config_switches.py` | worktree branch; `config.SHORT_GAP_SIZING`, `config.SHORT_RISK_NOTICE`, `config.SHORT_SQUEEZE_SI_PCT`, `config.SHORT_SQUEEZE_DTC` |
| V183-2 | Up-gap p99 in gap_stats | 1 | sonnet | M `swingbot/core/edge/gates.py`, `tests/edge/test_edge_gates.py` | `gap_stats(...)["p99_up_gap_pct"]`, `["n_up"]` |
| V183-3 | Gap floor in compute_position_size, every sizing mode | 1 | opus | M `swingbot/core/planning/account.py`; C `tests/planning/test_gap_floor_sizing.py` | `compute_position_size(..., gap_floor_pct=None)`, result keys `gap_risk_amount`, `gap_sized`, `gap_floor_pct`; `_sizing_distance`, `_gap_fields` |
| V183-4 | One sizing path, plan stamp at creation | 1 | opus | C `swingbot/core/planning/gap_sizing.py`, `tests/planning/test_gap_sizing.py`; M `swingbot/core/planning/plan_types.py`, `swingbot/core/scanning/analyze.py`, `swingbot/core/scanning/strategy_pass.py` | `RULE_GAP`, `RULE_STOP`, `MIN_UP_GAPS`, `LOOKBACK`, `gap_sizing_stamp(df, direction)`, `stamp_gap_sizing(plan, df)`, `gap_floor_for(direction, gap_sizing)`, `size_for(entry, stop_loss, *, direction, gap_sizing, account_cfg=None, label="")`, `size_for_plan(plan, entry=None, account_cfg=None)`, `size_for_trade(trade, entry=None, account_cfg=None)`, `gap_risk_amount_for(shares, entry, stop_loss, gap_sizing)`, `TradePlanV2.gap_sizing` |
| V183-5 | The four re-size sites read the stamp | 1 | opus | M `swingbot/core/scanning/plan_table.py`, `swingbot/core/scanning/outlook_run.py`, `swingbot/admin/dashboard.py`, `swingbot/core/scanning/analyze.py`; C `tests/scanning/test_gap_sizing_resize_sites.py` | `_sizing_snapshot(entry, plan)` (same signature) now returns the gap keys for a stamped short |
| V183-6 | Paper book sizes through size_for, logged fallback, alert/paper parity | 2 | opus | M `swingbot/core/tracking/performance.py`, `swingbot/core/scanning/scan_run.py`, `swingbot/core/scanning/short_run.py`, `swingbot/core/scanning/strategy_pass.py`, `swingbot/core/planning/plan_manager.py`; C `tests/tracking/test_gap_sized_paper_book.py` | `log_trade(..., gap_sizing=None)`, trade key `gap_sizing`, `_paper_sizing(entry, stop_loss, direction, gap_sizing, label)` |
| V183-7 | Invariants: caps per lane, gap-fill real R, longs byte-identical | 2 | sonnet | C `tests/scanning/test_gap_sizing_cap_invariants.py`, `tests/tracking/test_gap_fill_real_r.py`, `tests/planning/test_long_sizing_regression.py` | — (tests only) |
| V183-8 | Order-block gap-risk line on every alert channel | 2 | sonnet | C `swingbot/core/presentation/gap_risk.py`, `tests/presentation/test_gap_risk_line.py`; M `swingbot/core/scanning/alert_embeds.py`, `swingbot/core/scanning/execution_embeds.py`, `swingbot/core/infra/notifier.py` | `GAP_CUT_TEXT`, `GAP_NA_TEXT`, `gap_risk_line(sizing, *, currency="$")` |
| V183-9 | Risk view: summed gap risk of open shorts | 2 | sonnet | M `swingbot/admin/api_v1/risk.py`, `tests/admin/test_api_v1_risk.py`, `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/stores/risk.store.spec.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts` | `heat.gap_risk_amount`, `heat.gap_risk_unknown`; `_open_short_gap_risk(open_trades) -> dict` |
| V183-10 | Short-interest cache: parse, fetch, refresh, cached read | 3 | sonnet | C `swingbot/core/market/short_interest.py`, `tests/market/test_short_interest.py` | `CACHE_NAME`, `STALE_DAYS`, `ShortInterestCacheError`, `parse_info(info, *, today)`, `fetch_short_interest(ticker)`, `refresh_short_interest(symbols, *, now=None, fetch=None)`, `cached_short_interest(ticker)`, `request_refresh(ticker)`, `refresh_symbols()` |
| V183-11 | Daily short-interest refresh loop | 3 | sonnet | M `swingbot/commands/scanning/loops.py`, `swingbot/commands/scanning/__init__.py`, `tests/commands/test_scheduled_jobs.py` | `daily_short_interest_refresh`, `_short_interest_refresh_fired_date` |
| V183-12 | Notice snapshot at plan creation, degrade on failure | 3 | opus | C `swingbot/core/scanning/risk_notice.py`, `tests/scanning/test_risk_notice_snapshot.py`; M `swingbot/core/planning/plan_types.py`, `swingbot/core/scanning/analyze.py`, `swingbot/core/scanning/strategy_pass.py` | `hold_window(plan, signal_date)`, `build_risk_notice(plan, signal_date, *, now=None, source=None)`, `degraded_notice(plan, signal_date)`, `stamp_risk_notice(plan, df)`, `TradePlanV2.risk_notice` |
| V183-13 | One wording module: notice lines on every short alert | 3 | opus | M `swingbot/core/presentation/short_notice.py`, `swingbot/core/scanning/alert_embeds.py`, `swingbot/core/infra/notifier.py`, `tests/scanning/test_short_alert_parity.py`; C `tests/presentation/test_risk_notice_lines.py` | `SQUEEZE_PREFIX`, `SQUEEZE_NOT_CHECKED`, `EARNINGS_NOT_CHECKED`, `squeeze_tripped(si)`, `risk_notice_lines(snapshot, *, currency="$")`, `has_risk_notice(plan_v2)` |
| V183-14 | Paper-record snapshot, plan-page API, five-channel parity | 3 | opus | M `swingbot/core/tracking/performance.py`, `swingbot/core/scanning/scan_run.py`, `swingbot/core/scanning/short_run.py`, `swingbot/core/scanning/strategy_pass.py`, `swingbot/core/planning/plan_manager.py`, `swingbot/admin/api_v1/trades.py`, `tests/scanning/test_short_alert_parity.py`; C `tests/admin/test_api_v1_trade_risk_notice.py` | `log_trade(..., risk_notice=None)`, trade key `risk_notice`, detail keys `risk_notice_lines`, `gap_sizing` |
| V183-15 | Plan page: notice lines and gap cut in the order block, three widths | 3 | sonnet | M `frontend/src/app/workspaces/plans/plan-detail.ts`, `frontend/src/app/workspaces/plans/plan-detail.spec.ts` | — |
| V183-16 | Impact results doc: re-size the live book's closed shorts | 4 | sonnet | C `scripts/reports/short_gap_sizing_impact.py`, `tests/scripts/test_short_gap_sizing_impact.py`, `docs/superpowers/results/<run-date>-v183-gap-sizing-impact.md` | `resize_closed_shorts(trades, frames, *, balance, risk_pct) -> dict`; results doc with rollback note |
| V183-17 | Version bump, full suite, merge | 4 | sonnet | M `VERSION.json`, `version_history.json` (regenerated) | merged branch on `main` |
