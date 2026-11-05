# v209 — Market-shock detector (shadow) and shock-conditioned short screens

**Version:** ui 1.39.1 · bot 2.16.5
**Bump:** bot minor, ui patch (new Discord state-change notices the partner reads and acts on; a state badge beside the existing tape)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-researcher, veteran-trader

## Why

On **2026-11-05**, a broad correction day led by memory and semiconductor
names, the live book closed **26 trades: 3 wins, 21 losses, 2 scratches,
−13.9R**. That is the worst day of the last 25. The partner asked the bot to
**stop issuing LONG trades and switch to SHORT trades when the market turns
sharply**, whether the cause is a correction or news, across all sectors.
The partner also asked it to watch price and VIX to know when to switch back.

Measured on the local production replica (`swingbot_prod_replica`, current
to 2026-11-05 18:01 UTC):

| Finding | Evidence |
|---|---|
| It kept buying after the market turned | `entry_context.regime2_state` flipped to `bear_volatile` intraday; about 20 longs opened after the flip; most hit their stop in 0.1–1.5 h |
| It bought the same falling names again and again | MU opened 5× in two sessions, MRVL 3×, WDC 3×; mostly memory and chip names (MU, WDC, STX, SNDK, MRVL, NVDA, AMAT) with `rs_pctile` 7–17, `sector_pctile` 11, RSI 23–30 |
| Stops were inside normal price movement | `entry_context.stop_atr` 0.02–0.4 for almost every trade closed that day (1.7–2.0 % of price) |
| Same pattern on other days | 2026-10-30 −11.9R (22 of 25 long), 2026-10-22 −7.1R |
| Every plan is stamped `COHORT_UNKNOWN` | Separate defect, out of scope here (see Non-goals) |

Live-book counterfactuals over all 962 closed trades. They are in-sample
and cover about 7 weeks, so the effective N is the number of trading days,
not 962. **They justify a measurement, not a gate:**

| Rule | Win % | ExpR | Trades blocked | R of blocked |
|---|---|---|---|---|
| Current behaviour | 48 | −0.106 | – | – |
| No new entries after 5 losses in a session | 48 | −0.055 | 371 | −69.8 |
| No same-day re-entry after a stop | 49 | −0.102 | 100 | −13.9 |
| No longs in `bear_volatile` | 48 | −0.102 | 12 | −5.7 |

Results this spec must not re-run (`backtest-methodology.md` § Closed
pre-registrations):

- **v17 P2a `REGIME_ALLOW`:** no daily regime gate justified.
- **v34:** bullish RS gate negative.
- **v191:** ATR-band stops, NO-LIFT.
- **v104 Part B:** Bull Trap and Vol Expansion Breakdown shorts NO-LIFT.
- **v182:** `range_breakdown_close` SCREEN-FAIL.

Every one of those was **unconditional**, tested across all days. Two
things are new here:

- **Intraday detection.** The bot reacts within the session, which a
  daily regime label cannot do.
- **The conditional short hypothesis.** Breakdown shorts pay *only while* a
  broad shock is on.

## What changes

Two tracks, approved by the partner on 2026-11-05.

- **Track 1 (built by this spec's plan):** a market-shock detector running
  in **shadow mode**. It measures, records and notifies, and **changes no
  trade**. That is why it is `Edge: none (integrity)` and exempt from the
  screen.
- **Track 2 (pre-registered here, run as plan tasks):** two one-shot idea
  screens for the shock-conditioned shorts. Live behaviour (blocking longs,
  issuing shock shorts, moving stops up) is a **later spec**, written only
  from the parts that pass.

## Track 1 — the detector

### State machine

```
 NORMAL ──(wide breadth drop + speed; VIX spike accelerates)──▶ SHOCK
   ▲                                                              │
   │                                                              ▼
   └──(repair holds MIN_DWELL)── RECOVERY ◀──(VIX turns down + breadth repairs)
```

- **NORMAL → SHOCK.** Either condition is enough:
  - *Breadth and depth:* `breadth_frac ≥ SHOCK_BREADTH_ENTER` and
    `sectors_down ≥ SHOCK_SECTORS_ENTER`.
  - *Breadth and speed:* `breadth_frac ≥ SHOCK_BREADTH_FAST` and
    `breadth_speed ≥ SHOCK_SPEED_ENTER`.

  A VIX day change at or above `SHOCK_VIX_SPIKE_PCT` lowers either breadth
  bar by `SHOCK_VIX_RELIEF`. A SPY or QQQ move is recorded in the reading
  but never triggers SHOCK on its own.
- **SHOCK → RECOVERY.** All of these must hold:
  - minimum dwell `SHOCK_MIN_DWELL_MIN` has passed
  - `breadth_frac ≤ SHOCK_BREADTH_EXIT` (well below the entry bars)
  - VIX is at least `RECOVERY_VIX_OFF_HIGH_PCT` below its session high, or
    below the prior close
  - SPY has regained at least `RECOVERY_SPY_RETRACE` of the session's drop
    from the prior close
- **RECOVERY → NORMAL.** The RECOVERY conditions keep holding for
  `RECOVERY_MIN_DWELL_MIN`. If the SHOCK entry rule fires again during
  RECOVERY, the state returns to SHOCK.
- **Overnight carry.** The state persists across sessions. The first
  reading of a new session re-evaluates it against that session's prior
  close. A gap-up repair moves it to RECOVERY quickly; a second leg down
  keeps it in SHOCK.
- **Hysteresis is the point.** The entry and exit thresholds differ, and
  every state has a minimum dwell. Without that, a scan pass every
  `SCAN_INTERVAL_MINUTES` would flip the state on and off at the turn, and
  in live mode that would stop out longs and shorts alike.

### The reading

One reading per scan pass, built from data the pass already holds:

| Field | Definition |
|---|---|
| `breadth_frac` | share of watchlist equities with `(last − prev_close) / ATR14 ≤ −SHOCK_ATR_K` |
| `sectors_down` | number of sectors (`universe.sector_map`) with at least 2 members whose median `(last − prev_close) / ATR14 ≤ −SHOCK_ATR_K` |
| `sectors_total` | sectors with at least 2 members in the pass |
| `breadth_speed` | `breadth_frac` minus the previous reading's, when that reading is from the same session; else `None` |
| `spy_atr_move`, `qqq_atr_move` | the same ATR-scaled move for the two ETFs |
| `vix_level`, `vix_chg_pct`, `vix_off_high_pct` | from the `^VIX` tape row (`marketdata/shared/tape.py`, refreshed once a minute in session). The session high is the highest level seen in readings this session. A missing or stale row (older than `SHOCK_VIX_MAX_AGE_S`) is `None` |
| `n_names` | equities that contributed. Below `SHOCK_MIN_NAMES`, the reading is `insufficient` and `step` holds the current state |

Non-equity symbols are excluded from breadth (XAUUSD, XAGUSD and the
other FX or metal tickers in the watchlist). So are names with fewer than
15 bars of history.

### Starting thresholds

These are config fields that hot-reload with SIGHUP. Shadow mode uses them
**only to label**, so they are tunable without a screen. **The values used
in Track 2's screens are frozen separately below and never follow these.**

| Field | Default | Field | Default |
|---|---|---|---|
| `SHOCK_ATR_K` | 1.0 | `SHOCK_BREADTH_EXIT` | 0.20 |
| `SHOCK_BREADTH_ENTER` | 0.40 | `RECOVERY_VIX_OFF_HIGH_PCT` | 5.0 |
| `SHOCK_SECTORS_ENTER` | 0.6 × `sectors_total`, rounded up | `RECOVERY_SPY_RETRACE` | 0.5 |
| `SHOCK_BREADTH_FAST` | 0.25 | `SHOCK_MIN_DWELL_MIN` | 45 |
| `SHOCK_SPEED_ENTER` | 0.10 per reading | `RECOVERY_MIN_DWELL_MIN` | 30 |
| `SHOCK_VIX_SPIKE_PCT` | 15.0 | `SHOCK_MIN_NAMES` | 20 |
| `SHOCK_VIX_RELIEF` | 0.05 | `SHOCK_VIX_MAX_AGE_S` | 600 |

`MARKET_SHOCK_MODE`: `off | shadow | live`, default `shadow`. In this spec,
`live` behaves exactly like `shadow`. A later spec gives `live` meaning,
one screened behaviour at a time.

### Units

- **`swingbot/core/market/shock.py`** — pure; no I/O, no config import (the
  thresholds arrive as a frozen `ShockThresholds` dataclass).
  - `ShockSnapshot`: the per-name rows (ticker, sector, last, prev_close,
    atr14, is_equity), SPY and QQQ rows, the VIX tape fields, and `as_of`.
  - `measure(snapshot, prev: ShockReading | None) -> ShockReading`.
  - `step(state: ShockState, reading: ShockReading, th: ShockThresholds)
    -> ShockState`, where `ShockState` holds the label, `since`,
    `session_date`, `vix_session_high` and the session's prior SPY close.
  - Each transition is one table-driven rule function; every function
    stays below complexity 15.
- **Wiring in `scan_run`.** After the pass has loaded its daily frames,
  build a `ShockSnapshot` from them. The last bar is today's partial bar,
  the one before it is `prev_close`, and ATR14 comes from the existing
  indicator path. Read `^VIX` through `read_tape`, call `measure` then
  `step`, and persist both. A failure is logged through `swallowed` and
  never fails the scan.
- **Persistence (Alembic revision, `schema-evolution.md`).**
  - `market_shock_state`: a single row with the current label, `since`,
    `session_date`, `vix_session_high` and the last reading's id.
  - `market_shock_readings`: one row per scan pass, with every reading
    field plus `state_after`.
  - A repository in `swingbot/core/db/repositories/`.
- **Plan stamp.** Each new plan's `entry_context` gains `shock_state`, the
  label at the moment the plan was built. The live book can then measure
  shock-state cohorts directly. This adds a field and no table shape, per
  `schema-evolution.md`'s rules for stored records.
- **Discord notices**, through the bot's existing status channel path, never
  as an alert embed:
  - On each transition: one message with the label, the trigger numbers
    (breadth %, sectors down/total, speed, SPY and QQQ ATR move, VIX level
    and change) and the time.
  - On entering SHOCK: the message also lists every open **long**, with
    ticker, entry, distance to stop in R and age. It ends with the line
    "Stop move-up and long block: pending screen (v209 Track 2) — no plan
    was changed."
  - Rate limit: at most one transition notice per `SHOCK_MIN_DWELL_MIN`.
- **Admin.** The market-tape API response gains a `shock` object (label,
  since, the last reading's headline numbers). The SPA shows a
  NORMAL/SHOCK/RECOVERY badge beside the existing tape. Per `ui-design.md`,
  it is checked at mobile, tablet and desktop widths, never truncating the
  tape and wrapping below it on narrow screens.

### Track 1 tests

- **`measure`:** breadth with equities and non-equities mixed; sector
  minimum of 2 members; `breadth_speed` reset across sessions; missing and
  stale VIX; an empty watchlist and below `SHOCK_MIN_NAMES` (→
  `insufficient`).
- **`step`:**
  - every transition, both entry paths and the VIX relief
  - hysteresis (a reading between the entry and exit bars holds the state)
  - minimum dwell
  - re-entry from RECOVERY
  - overnight carry, both a gap-up repair and a second leg down
  - an `insufficient` reading holds the state
- **Replay of 2026-11-05.** A fixture built from the replica's readings,
  reconstructed from the day's partial bars, must reach SHOCK **no later
  than** the 14:36 UTC STX long entry.
- **Long and short plans are byte-identical** under `MARKET_SHOCK_MODE=off`
  and `shadow`, apart from the new `entry_context.shock_state` key (pinned
  byte-for-byte, as for any short-side change).
- **Repository round-trip** against the shared `swing-db` replica, run
  after `/replicate-prod-db`.
- **Notice formatting:** zero open longs, many open longs, rate limit.
- **Frontend:** the badge in all three states and the narrow-width
  wrapping.

## Track 2 — the shock-conditioned short screens

Both screens run on the standard Stage −2 machinery
(`backtest-methodology.md` § Funnel stages): point-in-time S&P 500 members,
2010-01-01..2019-12-31, the fixed race, 5 bps plus commission, and K = 20
matched random bars. The pass rule is unchanged and **one shot each.** The
definitions below are **frozen at this commit.** A changed value is a new
idea with a new name.

### The shared daily shock series (context symbol `SHOCK_D`)

The screen's idea interface reads per-symbol context series
(`screen/context.py`, as `dollar_drop` reads `UUP`). It has no
cross-sectional input, so a precompute step builds one synthetic daily
series over the point-in-time member set and stores it as context
`SHOCK_D`. A plan task builds it and pins its no-lookahead behaviour with a
test.

- `d_breadth[t]`: the share of members on date `t` with
  `(Close[t] − Close[t−1]) / ATR14[t−1] ≤ −1.0`. The ATR uses bars dated
  `t−1` and earlier only.
- **Daily shock state[t]:**
  - It **enters** on `d_breadth[t] ≥ 0.40`.
  - From SHOCK it **releases** on the first date with `d_breadth[t] ≤ 0.10`
    and `^VIX Close[t] < ^VIX Close[t−1]`. The state on that release date
    is still SHOCK; the next date is NORMAL.
  - There is no RECOVERY tier in the daily series, because daily bars
    cannot see the intraday repair.
- `SHOCK_D[t] = 1` while in SHOCK, else 0. An event on date `t` requires
  `SHOCK_D[t] = 1`, computed from bars dated `t` and earlier only.

### Idea 1 — `shock_support_break_short`

- `SHOCK_D[t] = 1`
- and `Close[t] < min(Low[t−20 .. t−1])` (a close below the prior 20-day
  low)
- short at the next open; `RACE = "fixed"`, `CAP = 10`,
  `DIRECTION = "short"`

### Idea 2 — `shock_failed_bounce_short`

`SHOCK_D[t] = 1`, and:

1. **A decline.** Some `b` in `t−5 .. t−1` with
   `Close[b−1] ≤ max(High[b−10 .. b−2]) − 1.0 × ATR14[b−2]`. That is, a
   decline of at least 1 ATR from the recent high.
2. **A bounce bar.** That `b` has `Close[b] > Close[b−1]`.
3. **A lower high.** `High[b] < max(High[b−10 .. b−2])`.
4. **The failure.** `Close[t] < Low[b]`, and no bar between `b+1` and
   `t−1` closed below `Low[b]` (first failure only).
5. If several bars qualify as `b`, the latest one counts.

Short at the next open; `RACE = "fixed"`, `CAP = 10`, `DIRECTION = "short"`.

### What the screens can and cannot say

- **They test the daily version.** A pass says that breadth-shock-conditioned
  breakdown shorts carry information at daily resolution. It does not
  validate the 15-minute reaction. That reaction is checked by Stage −1
  reachability on the bot's own replay over the 15-minute Alpaca store
  (v162, history from about 2016), in the follow-on spec.
- **The year rule may sink a crash-only edge.** The rule needs the same
  sign in at least 7 of 9 years (2011–2019), and a year with no events
  counts against. 2017 had almost no shock days. A `SCREEN-FAIL` or
  `SCREEN-UNDERPOWERED` caused mainly by empty years is recorded **as
  such** in the results doc. It is still closed, and it is not re-run with
  a looser definition. The evidence path then becomes the Track 1 shadow
  log: shock-state cohorts in the live book.
- **The matched random baseline** draws from the same ticker, month and
  trend state. Shock months are volatile, so the baseline is also drawn
  from turbulent bars. The screen therefore tests the *trigger*, not
  "short in a bad month".

### Follow-on pre-registrations

These are named here, not run here.

- **Long block in SHOCK.** It filters the bot's own plans, so it is judged
  on the bot's replay (Stage −1 reachability, then the funnel), not by the
  idea screen. It opens **only together with** a passing short arm, per
  the partner's rule that every gate tightening ships paired with a
  widening.
- **Stop move-up for open longs on SHOCK entry.** An exit change, so it
  goes through the funnel's exit and harvest gate. It needs a
  `harvest-headroom` results doc first.
- **The live meaning of `MARKET_SHOCK_MODE=live`** is the follow-on spec,
  written from whichever of the above pass.

## Non-goals

- **No trade changes in this spec.** No long is blocked, no short is
  issued, no stop is moved.
- **The `COHORT_UNKNOWN` stamp on every live plan** is a separate defect:
  `cohort_registry` is not resolving on production even though
  `regime2_state` is present. It gets its own fix.
- **No same-day re-entry cooldown or per-sector cap.** The partner chose the
  shock switch. Both remain candidates for the screen if the shock path
  fails.
- **No intraday bars in the live scan.** The detector uses the partial
  daily bar the scan already has.

## Risks

- **False SHOCK on a narrow watchlist.** A watchlist concentrated in one
  theme (chips) can show 40 % breadth on a sector-only drop. The
  `sectors_down` clause is the guard. The shadow log measures how often
  this happens before any live behaviour.
- **Stale partial bars outside regular hours.** Readings are taken only in
  session (the same session gate as the scan). Weekend frozen bars never
  produce a reading.

- **VIX tape gaps.** Every rule that uses VIX has a non-VIX path. A missing
  VIX never blocks a transition into SHOCK. It can delay RECOVERY only
  through `RECOVERY_VIX_OFF_HIGH_PCT`, and the SPY retrace still applies.
