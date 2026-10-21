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
older than 35 days → shown with `STALE`. Exact fields and cache location are
the builder's, verified against yfinance at build time.

**Coverage and misses (my call):** the daily refresh covers the watchlist
plus every ticker with an open or pending short plan. A cache miss at alert
time shows `n/a` and adds the ticker to the next refresh; no alert is held
or edited afterwards.

**Snapshot (my call):** the notice values are saved with the plan when the
alert goes out, and the plan page shows that snapshot, so the page always
matches the alert (channel parity holds on every day, not only the first).
Plans created before this ships have no snapshot and show no notice.

**Never** used by any filter, score, confidence or backtest; a test pins that
no scan decision changes when the notice data changes.

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
