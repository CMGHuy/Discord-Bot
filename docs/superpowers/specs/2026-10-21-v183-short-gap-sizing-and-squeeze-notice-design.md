# v183 — Gap-aware short sizing, and a squeeze/event notice on every short

**Version:** ui 1.33.1 · bot 2.14.2 (at writing)
**Bump:** bot minor, ui patch — every short plan's suggested share count can shrink and every short alert gains notice lines (bot); the plan page shows the same lines (ui, display only).
**Edge:** none (integrity) — both parts control and disclose short-side risk. R stays defined on the stop, so neither part moves win rate or ExpR in R; Part A lowers dollar loss on a gap through a short's stop and also lowers dollar profit on the same names.
**Screen:** exempt (integrity)
**Panel:** risk-manager, veteran-trader, staff-engineer
**Status:** spec written 2026-10-21 from a brainstorm with the partner (sources: Schwab "Short Selling: The Risks and Rewards", CMC Markets "What Is a Short Squeeze?", TradersPost "Short Selling Strategies Guide"). Partner decisions are marked **(partner)**; the author's calls are marked **(my call)**.

## Why

The partner wants SHORT trades planned better and winning more often. The
three sources name five short-specific risks. A survey against the repo:

| Source risk | Already handled | Gap |
|---|---|---|
| Stops can gap (Schwab) | Backtest/screen gap fills at the open (v182 Part A); `gap_stats` p90/p99 and `gap_fragile` recorded in `entry_context` (`swingbot/core/edge/gates.py:15`, `swingbot/core/edge/context.py:106`) | Live sizing ignores the gap: a gap through a short's stop can cost far more than the 2% dollar cap |
| Borrow cost jumps (Schwab) | `borrow_r` 0.5%/yr in the screen (v182); `CHECK BORROW AVAILABILITY` on extra-lane shorts (v118) | No historical borrow data exists; nothing more can be measured |
| Squeeze signs: high short interest, low float (CMC) | Named as "cannot see" in v182 | Never shown to the partner on an alert |
| Catalysts (CMC) | v82 earnings blackout **closed** (near-earnings trades scored *better*, do not re-run); v104 shorts' earnings axis mixed | No earnings/ex-div line on short alerts |
| Breakouts above resistance (CMC) | — | Queued as a screen idea, see "What follows" |
| Small size (TradersPost) | — | Its author's view, not a standard; it changes nothing in R. Not adopted. |

Live-book evidence (read-only production check, 2026-10-21, script in the
session scratchpad, not committed): 265 of 333 closed shorts analysable, WR
51%, mean R −0.076. Stop-outs average −1.13R for shorts and −1.15R for longs
(v182 spec), so the *average* overshoot is not short-specific. Part A is
insurance against the tail (a squeeze gap), adopted by the partner without a
tail measurement first **(partner: "build the sizing regardless")**.

The ex-dividend risk nets to about zero (the ex-date drop the short gains
roughly equals the dividend it pays, and adjusted backtest prices already
reflect it), so it is disclosed, not filtered **(partner)**.

## Goals

1. A short's suggested size keeps a gap the size of the ticker's routine bad
   gap inside the configured per-trade dollar risk.
2. Every short alert and plan page tells the partner, before entry: short
   interest, days to cover and float, with a ⚠ when a squeeze threshold
   trips; any earnings date and ex-dividend date inside the planned hold.

## Non-goals

- No filter, veto or gate. Nothing in this spec blocks, rejects or alters a
  plan's entry, stop or targets.
- No backtest, screen or replay change. Short interest and float have no
  point-in-time history here and must never enter a backtest.
- No borrow or locate check; the bot still never places an order.
- No change to how R, win rate, ExpR or heat-in-R are computed.

## Anti-goals (failure even if it "works")

- **Any LONG output changes.** Long sizing and long alerts stay
  byte-identical, pinned by regression tests (repo rule: short work never
  downgrades longs).
- A notice value is fabricated, defaulted to 0, or silently stale. Missing is
  `n/a`; every short-interest figure carries its report date.
- A yfinance call on the scan hot path. A slow per-ticker info lookup blocked
  the watchlist before; notice data is fetched off the scan path and cached.
- Discord, email, push and the plan page wording the notice differently.

## Constraints

- The 2% cap is **dollar** risk **(partner, standing)**: a short may get a
  smaller size; its stop is never moved to fit.
- Every function < complexity 15 (`complexity_gate.py`).
- UI: plan page lines designed and checked at phone, tablet and desktop
  widths (`docs/claude/ui-design.md`).
- `.env` is the single config source; any new knob is a `swingbot/config.py`
  Field, hot-reloaded.
- Schema: any new stored field follows `docs/claude/schema-evolution.md`.

## Part A — gap-aware short sizing

**Rule (partner: p99 gap over 250 bars).** For a **short** plan only, the
distance used to turn the per-trade dollar risk into a share count is

    sizing_distance = max(|entry − stop|, entry × gap_p99_pct / 100)

where `gap_p99_pct` is `gap_stats(df, lookback=250)["p99_gap_pct"]` from the
completed daily bars at plan creation. Every existing cap (`max_position_pct`,
`MAX_POSITION_VALUE_ABSOLUTE`, `MAX_RISK_AMOUNT_ABSOLUTE`) applies after, and
the tightest still wins (`compute_position_size`,
`swingbot/core/planning/account.py:405`). A long never reaches the new branch.

**Decided:**
- R stays measured on the stop. `risk_amount` keeps its meaning (final shares
  × stop distance). A new returned field, `gap_risk_amount` (final shares ×
  `sizing_distance`), is what a p99-sized gap would cost. `capped`-style
  flag: `gap_sized` true when the gap term was the larger one.
- The p99 value is computed once, when the plan is created, and stored with
  the plan, so Discord, the dashboard and every later re-sizing
  (`plan_table.py:130`, `outlook_run.py:201`, `admin/dashboard.py:447`,
  `scanning/analyze.py:254`) use the same number without re-fetching bars.
- **The paper book trades the gap-sized shares (partner).** The calls that
  fix a paper trade's share count — `TradeLog.log_trade` and
  `record_plan_fill` (`swingbot/core/tracking/performance.py:778`, `:828`) —
  use the same gap-aware sizing as the alert, so alert and paper book always
  agree, and a later eToro demo order would use the same size. Short dollar
  P&L and the balance curve shift from ship day; R, WR and ExpR stay
  comparable. `compute_position_size` therefore needs direction and the
  stored p99 threaded in at every call site that sizes a short.
- No usable p99 (fewer than ~60 gaps, missing bars, or a plan created before
  this ships): size on the stop exactly as today, and show "gap risk n/a".
- The alert shows both figures, e.g. `Risk $200 at stop · $200 on a p99 gap
  (2.8%)`; when gap-sized, the line says the size was cut for gap risk.

**My calls (builder may revisit, say so):**
- Portfolio heat keeps using `risk_amount` (stop risk) so heat stays
  comparable with history; `gap_risk_amount` is displayed, not summed.
- The edge sizing modes (`kelly`, `vol_target`, `min_of_all`) and
  `account_pct` mode: the gap floor applies wherever stop distance turns
  risk into shares; in `account_pct` mode it applies through the
  `MAX_RISK_AMOUNT_ABSOLUTE` check only. The builder pins each mode with a
  test.
- One config switch, `SHORT_GAP_SIZING` (default on), so the partner can
  turn it off without a deploy. Off must reproduce today's short sizing
  byte-for-byte.

## Part B — squeeze and event notice on every short

**Applies to** every short plan the bot alerts on, whichever path made it
(confluence, strategy, v104/v118/v119 lanes) **(my call; the partner chose
"every short alert")**. It extends `swingbot/core/presentation/short_notice.py`,
the one module that already words short notices for Discord (full and
simple), email and push; the plan page reads the same text.

**Lines (partner: always shown, ⚠ past thresholds):**
1. `Short interest 18.2% of float · 4.1 days to cover · float 45.3M (as of
   2026-10-15)`; prefixed `⚠ SQUEEZE RISK ·` when short interest ≥ 10% of
   float or days to cover ≥ 5. Thresholds are config Fields
   (`SHORT_SQUEEZE_SI_PCT=10`, `SHORT_SQUEEZE_DTC=5`).
2. `Earnings in hold: 2026-10-28` when the next report falls inside the
   **hold window**: from the signal bar through the entry expiry plus the
   horizon's maximum hold, the longest the plan could be open **(my call:
   the widest window, so the line never gives false comfort)**; otherwise
   `No earnings in hold`. Source: the existing earnings
   calendar (`swingbot/core/market/events.py:61` / `earnings_calendar.py`).
3. `Ex-div in hold: 2026-10-24 · ~$0.42/sh owed` when an ex-dividend date
   falls in the same window; otherwise omitted.
4. `CHECK BORROW AVAILABILITY` stays.

**Data (my call):** yfinance per-ticker info (`sharesShort` /
`shortPercentOfFloat`, `shortRatio`, `floatShares`, `dateShortInterest`,
`exDividendDate`, `dividendRate` or the dividends calendar), fetched by a
daily background refresh for the watchlist and short universe and cached
per ticker; the alert reads only the cache. Absent or unparsable → `n/a`;
older than 21 days → shown with `STALE` (short interest is published
semi-monthly and lags); a dividend amount that is a forward estimate is
labelled `est.`. Exact fields and cache location are
the builder's, verified against yfinance at build time.

**Coverage and misses (my call):** the daily refresh covers every ticker the
scan can evaluate for a short (watchlist plus every short lane's universe)
and every ticker with an open or pending short plan. A cache miss at alert
time never reads as comfort: the line becomes `⚠ Squeeze data not checked —
verify short interest at your broker`, and the ticker joins the next
refresh; no alert is held or edited afterwards. The earnings line reads the
existing earnings calendar, not this cache; a ticker absent from the
calendar prints `Earnings: not checked`, never `No earnings in hold`.

**Snapshot (my call):** the notice values are saved with the plan when the
alert goes out, and the plan page shows that snapshot, so the page always
matches the alert (channel parity holds on every day, not only the first).
Plans created before this ships have no snapshot and show no notice.

**Never** used by any filter, score, confidence or backtest; a test pins that
no scan decision changes when the notice data changes.

## Requirements added by the panel review

**Sizing (Part A):**
- **Adverse side only (my call, refining the partner's "p99 gap").** For a
  short the gap that hurts is an *up* gap through the stop, so
  `gap_p99_pct` is the 99th percentile of up-gaps (`Open / prev Close − 1 >
  0`) over the same 250 bars, not of absolute gaps. `gap_stats` gains this
  as a new key; its existing keys and every existing caller stay unchanged.
  p99 over ~125 up-gaps is noisy (roughly the 1–2 largest); accepted and
  disclosed.
- **One sizing path.** All six sites that size a short (the four re-size
  sites, `TradeLog.log_trade`, `record_plan_fill`) call one function, which
  reads the p99 and the `SHORT_GAP_SIZING` state **stored on the plan at
  creation**. A switch flip or a missing p99 later never changes an already
  alerted plan's rule; balance-driven re-sizing behaves as today. A parity
  test pins alert share count = paper-book share count for a gap-sized
  short.
- **Caps hold on the cut size.** Heat and correlated-cluster checks
  (`scan_run.py` confluence, `short_run._stamp_risk_flags` for v118/v119/v144)
  use the configured `risk_pct`, never the final share count, and the stop
  cap is a stop-distance check; a gap cut only lowers shares, so every
  existing check stays a valid upper bound. Pinned by tests per lane that the
  cut never raises any capped quantity. The strategy lane
  (`strategy_pass._open_trade`, v104) has no heat check today: an older gap,
  noted, not fixed here. The gap floor can only shrink size, never grow it,
  in every sizing mode (`kelly`, `vol_target`, `min_of_all` and `risk_pct`
  share one branch; `account_pct` is reached only through
  `MAX_RISK_AMOUNT_ABSOLUTE`); the size shown equals the size returned. The
  seventh sizing site, `stop_scope.py:71` (`risk_sizing_ok`), stays valid
  because shares only shrink.
- **Gap fills book their real R.** A paper short stopped by a gap books the
  R of its actual fill (e.g. −2.4R), never a clamped −1R; pinned by a test.
- **Failures fall back loudly.** Missing p99 or an exception while threading
  direction/p99 into `log_trade`/`record_plan_fill` (which today swallow
  exceptions to `sizing = None`) falls back to stop-only sizing, never to
  unsized, and logs one line in the style of the existing `plan rejected (`
  lines.
- **Shown where the order is.** The final share count, and that it was cut
  for gap risk, appear in the same block as entry, stop and targets.
- **Open gap risk shown.** The admin risk view (`swingbot/admin/api_v1/risk.py`
  and its page) adds one figure: summed `gap_risk_amount` across open
  shorts, beside heat. Display only; heat itself stays on stop risk.
- **Measured once, after build (not a gate).** A results doc
  (`docs/superpowers/results/<date>-v183-gap-sizing-impact.md`) re-sizes
  the live book's closed shorts under the rule from their stored bars:
  share of shorts gap-sized, mean size cut, dollar P&L at fixed per-trade
  risk before/after, the worst five dollar losses before/after, and max
  drawdown of the short book before/after (`edge/ruin.py`,
  `risk_metrics.py`). The cut is unvalidated until then;
  `SHORT_GAP_SIZING=off` is the revert path.

**Notice (Part B):**
- **Never stops a scan or an alert.** A refresh crash, cache-read error or
  yfinance failure degrades every affected line to its "not checked" form;
  alert issuance and the scan loop never wait on or fail because of it.
  Pinned by a test that raises inside the cache read.
- **Off switch:** `SHORT_RISK_NOTICE` (default on); off reproduces today's
  short alerts byte-for-byte.
- **Earnings line carries the distance:** `Earnings in hold: 2026-10-28 (in
  6 sessions)`, so a wide window stays readable rather than noise.
- **Refresh owner:** a bot loop beside `weekly_earnings_refresh`
  (`swingbot/commands/scanning/loops.py:966`), daily after the close; it
  lives as long as Part B does and is removed with it.

**Storage and rollback (both parts):**
- Storage per `docs/claude/schema-evolution.md`: a new key in a stored doc
  (`gap_p99_pct` in `entry_context`, the sizing-rule state, the notice
  snapshot) is an "add" and needs no Alembic revision; a notice-cache table,
  if chosen, does. **The notice snapshot is its own plan field, never an
  `entry_context` key**, because `entry_context` is also built in backtests
  and live-only data must never enter it.
- Rollback: both switches off restores today's behaviour without a deploy.
  A code rollback (`rollback_to.sh`) leaves the new columns/keys and cache
  unread and harmless; paper trades already sized by the gap rule stay in
  the book as recorded (not re-sized), and the rollback note says so.
- `compute_position_size` (complexity 18) and `TradeLog.log_trade` (15) are
  legacy ≥ 15: the new branch goes in named helpers so neither score rises.

## What is left to the builder

- Where `gap_p99_pct` is stored on the plan (an `entry_context` key beside
  `gap_p90_pct` is the obvious home) and the schema-evolution path for it.
- How the notice cache is stored (file under `data/` vs a small table) and
  scheduled (existing loop in `swingbot/commands/scanning/loops.py` vs new).
- Exact wording and layout of the lines, within the content above.
- Plan split and task order.

## Tests the builder must include

- Long sizing and long alert text byte-identical before/after on a fixed
  set of long plans.
- Short sizing: stop > gap (unchanged), gap > stop (shares cut, `gap_sized`),
  no p99 (unchanged, `n/a`), switch off (byte-identical to today), every
  sizing mode.
- Notice: threshold trip on each of the two conditions, below both, every
  field missing, stale date, earnings inside/outside the window, ex-div
  inside/outside.
- One channel-parity test: Discord full, simple, email, push and the plan
  page API carry the same notice text.

## What follows (not built here)

**Queued screen idea — near-high short veto (partner).** Rule written down
now so it cannot drift: *short only when the signal bar's close is at least
3 × ATR14 below the highest high of the 20 bars ending at the signal bar*
(ATR14 and the high from bars ≤ the signal bar). It runs as a short idea
through `screen_idea.py` under the unchanged Stage −2 pass rule (flip-side
form, partner-approved), `RACE = "fixed"`, once v182 Part A (the short race)
is merged. Motivation, labelled post-hoc: in the live book shorts within
~3 ATR of the 20-day high went ~43% WR / ~−0.24R (N=134) vs ~60% / ~+0.09R
further below (N=131); the cut was chosen after seeing quartiles and the
quartiles are not monotonic. One shot; a fail closes it. A pass buys an
`Edge: expectancy` filter spec.

**Not pursued:** a short-only earnings blackout (v82 closed; would need a
partner ruling that it is distinct), an ex-dividend filter (nets ~0),
smaller short size as a rule (no effect in R).

## Panel review

Run 2026-10-21, serially: risk-manager, veteran-trader, staff-engineer.

- risk-manager 1 (BLOCKING): stop/heat/correlated caps not re-checked on the gap-cut size on every lane -- applied (caps re-checked, one test per lane).
- risk-manager 2 (BLOCKING): alert vs paper-book sizing can diverge across six sites -- applied (one sizing path reading plan-stored p99 and switch state; parity test).
- risk-manager 3 (BLOCKING): no drawdown/ruin or dollar-at-fixed-risk effect stated -- applied (post-build results doc on the live book's closed shorts; disclosed as unvalidated until then).
- risk-manager 4: gap fills must book real R, not −1R -- applied (test).
- risk-manager 5: heat understates short gap tail -- applied as display (summed gap risk in the admin risk view); heat stays on stop risk.
- risk-manager 6: gap floor only shrinks size in every mode -- applied.
- risk-manager 7: silent p99 fallback -- applied (logged fallback).
- risk-manager 8: which rule re-sizes an alerted plan -- applied (rule state stored on the plan).
- veteran-trader 1 (BLOCKING): alerted size can change silently after the alert -- applied (same as risk-manager 2/8).
- veteran-trader 2 (BLOCKING): `n/a` on a cache miss reads as comfort -- applied (explicit "not checked" lines; earnings read from the calendar, not the cache).
- veteran-trader 3: symmetric p99 over-cuts; p99 is noisy -- applied (up-gaps only, as my call refining the partner's choice); noise accepted and disclosed.
- veteran-trader 4: show final shares and the cut in the order block -- applied.
- veteran-trader 5: wide hold window makes the earnings line noise -- applied (sessions-to-earnings shown).
- veteran-trader 6: 35-day STALE too lenient; forward dividend -- applied (21 days; `est.` label).
- veteran-trader 7: say the cut is unvalidated and name the revert path -- applied.
- staff-engineer 1 (BLOCKING): a refresh/cache failure could stop alerts or the scan -- applied (degrade to "not checked"; test).
- staff-engineer 2 (BLOCKING): Part B has no switch, rollback unstated -- applied (`SHORT_RISK_NOTICE`; rollback note incl. gap-sized paper trades staying as recorded).
- staff-engineer 3: `log_trade`/`record_plan_fill` swallow exceptions -- applied (fall back to stop sizing, logged).
- staff-engineer 4: new stored fields need Alembic and `DATA_READERS` -- applied.
- staff-engineer 5: refresh owner and lifetime -- applied (bot loop beside `weekly_earnings_refresh`).
- staff-engineer 6: legacy complexity 18/15 must not rise -- applied (named helpers).

- Post-panel correction from the plan brief (2026-10-21): seven sizing sites, not six; heat/cluster caps read config `risk_pct`, so "re-check on the cut size" became "the cut never raises a capped quantity"; doc-key adds need no Alembic; notice snapshot kept out of `entry_context` -- applied.
