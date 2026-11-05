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
| It kept buying after the market turned | `entry_context.regime2_state` was first stamped `bear_volatile` at 14:36 UTC; **18 longs opened after that** (12 closed, all losses but MU and SNDK; 6 still open). Most closed trades hit their stop in 0.1–1.5 h. These 12 are the only `bear_volatile` longs the book has ever closed |
| It bought the same falling names again and again | MU opened 5× in two sessions, MRVL 3×, WDC 3×; mostly memory and chip names (MU, WDC, STX, SNDK, MRVL, NVDA, AMAT) with `rs_pctile` 7–17, `sector_pctile` 11, RSI 23–30 |
| Stops were inside normal price movement | `entry_context.stop_atr` 0.02–0.4 for almost every trade closed that day (1.7–2.0 % of price) |
| Same pattern on other days | 2026-10-30 −11.9R (22 of 25 long), 2026-10-22 −7.1R |
| Every plan is stamped `COHORT_UNKNOWN` | Separate defect, out of scope here (see Non-goals) |

Live-book counterfactuals. The window is trades closed 2026-07-06..2026-11-05
with status `win`/`loss`: 992 trades, of which **962** have a computable R
(`realized_pnl_amount / (|entry − stop_loss| × shares)`). They cover 84
trading days, and losses cluster by day, so the effective N is nearer 84
than 962. They are also in-sample: these days suggested the rules. The
source is the replica snapshot above; the query is the one this spec's
investigation ran, with each rule applied to `opened_at` / `closed_at` in
time order. **They justify a measurement, not a gate:**

| Rule | Kept N | Win % kept | ExpR kept | Blocked N | R of blocked |
|---|---|---|---|---|---|
| Current behaviour | 962 | 48 | −0.106 | – | – |
| No new entries after 5 losses in a session | 591 | 48 | −0.055 | 371 | −69.8 |
| No same-day re-entry after a stop | 862 | 49 | −0.102 | 100 | −13.9 |
| No longs in `bear_volatile` | 950 | 48 | −0.102 | 12 | −5.7 |

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

  **Not the opening print.** The entry condition must hold on **two
  consecutive** readings, and readings taken before
  `SHOCK_OPEN_SETTLE_MIN` (15) minutes after the US open never count
  toward entry. In the first minutes of a session a −1 ATR move is mostly
  the opening gap, not a flush.
- **SHOCK → RECOVERY.** All of these must hold:
  - minimum dwell `SHOCK_MIN_DWELL_MIN` has passed
  - `breadth_frac ≤ SHOCK_BREADTH_EXIT` (well below the entry bars)
  - VIX is at least `RECOVERY_VIX_OFF_HIGH_PCT` below its session high, or
    below the prior close
  - SPY has regained at least `RECOVERY_SPY_RETRACE` of the session's drop
    from the prior close
- **RECOVERY → NORMAL.** The RECOVERY conditions keep holding for
  `RECOVERY_MIN_DWELL_MIN`.
- **RECOVERY → SHOCK (second leg).** Re-entry is cheaper than entry from
  NORMAL. Either is enough:
  - `breadth_frac ≥ SHOCK_BREADTH_REENTER` (0.30) and rising since the
    previous reading
  - SPY prints a new session low

  A second leg down usually starts with breadth under the full entry bar
  but climbing, and a dead-cat bounce must not leave the bot sitting in
  RECOVERY through it.
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
| `sectors_down` | number of sectors with at least 2 members whose median `(last − prev_close) / ATR14 ≤ −SHOCK_ATR_K`. Sectors come from the `sector_of_ticker` map the scan already builds (`universe.sector_map("sp500")`, `scan_run.py:614`). A name without a sector counts toward breadth but toward no sector |
| `sectors_total` | sectors with at least 2 members in the pass |
| `breadth_speed` | `breadth_frac` minus the previous reading's, when that reading is from the same session; else `None` |
| `spy_atr_move`, `qqq_atr_move` | the same ATR-scaled move. "SPY" is `config.MARKET_REGIME_TICKER`, as the scan already loads it (`scan_run.py:586`). QQQ is used only if it is in the pass's frames, else `None`. A missing SPY frame makes the SPY-retrace recovery clause unmet (RECOVERY then waits) and the new-session-low re-entry clause inert |
| `vix_level`, `vix_chg_pct`, `vix_off_high_pct` | from the `^VIX` tape row (`marketdata/shared/tape.py`). `read_tape` never fetches (`tape.py:160`). The row is refreshed by `tape_feed` only when `TAPE_SHARED_ENABLED` is true and `MARKETDATA_LAYER=on` (`loops.py:1314-1318`), and `TAPE_SHARED_ENABLED` defaults to false. The plan verifies both values on production before deploying, and the admin badge shows "VIX missing" whenever the field is `None`. The session high is the highest level seen in readings this session. A missing or stale row (older than `SHOCK_VIX_MAX_AGE_S`) is `None` |
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
| `SHOCK_SECTORS_FRAC` | 0.6 (fraction of `sectors_total`; the count needed is `ceil(0.6 × sectors_total)`) | `RECOVERY_SPY_RETRACE` | 0.5 |
| `SHOCK_BREADTH_FAST` | 0.25 | `SHOCK_MIN_DWELL_MIN` | 45 |
| `SHOCK_SPEED_ENTER` | 0.10 per reading | `RECOVERY_MIN_DWELL_MIN` | 30 |
| `SHOCK_VIX_SPIKE_PCT` | 15.0 | `SHOCK_MIN_NAMES` | 20 |
| `SHOCK_VIX_RELIEF` | 0.05 | `SHOCK_VIX_MAX_AGE_S` | 600 |
| `SHOCK_BREADTH_REENTER` | 0.30 | `SHOCK_OPEN_SETTLE_MIN` | 15 |
| `SHOCK_READINGS_KEEP_DAYS` | 180 | | |

Every field is declared in `swingbot/config.py`'s schema, in a new
"Market Shock" section.

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
  - **Only the scheduled `session_scan` steps the state,** and only while
    `data.is_us_market_active()` is true, the same gate `tape_feed` uses
    (`loops.py:1316-1317`). The scan's own `in_session()` gate runs
    08:00–23:00 Berlin and would feed yesterday's or a frozen bar into
    dwell times and the session-first reading. `!check`
    (`commands.py:199`) and the recap (`recap.py:104`) also go through
    `run_scan`. They read the current state for the plan stamp and never
    write a reading or step the state. `run_scan` takes an explicit
    `step_shock: bool` argument, default `False`, and only `session_scan`
    passes `True`.
  - **The label reaches planning as an argument,** the way `regime2_state`
    does (`scan_run.py:406-411`). That covers the main loop, the strategy
    pass (`scan_run.py:103`), the SHORT lane `short_run`
    (`scan_run.py:678-680`) and requote rebuilds (`scan_run.py:418`).
    Planning never reads the shock repository.
- **Persistence (Alembic revision, `schema-evolution.md`).**
  - `market_shock_state`: a single row with the current label, `since`,
    `session_date`, `vix_session_high` and the last reading's id.
  - `market_shock_readings`: one row per stepped scan pass, with every
    reading field plus `state_after`.
  - A repository in `swingbot/core/db/repositories/` writes the reading and
    the state row **in one transaction**, so `last_reading_id` never
    dangles.
  - **Retention:** readings older than `SHOCK_READINGS_KEEP_DAYS` (180) are
    deleted by the existing nightly maintenance path. At about 28 stepped
    passes a session, that is roughly 5,000 rows. The owner is this spec's
    follow-on. If that follow-on is closed with no live behaviour, the
    tables are dropped in its close-out.
- **Plan stamp.** Under `shadow` and `live`, each new plan's
  `entry_context` gains `shock_state`, the label at the moment the plan was
  built. The live book can then measure shock-state cohorts directly. This
  adds a field and no table shape, per `schema-evolution.md`'s rules for
  stored records. **Under `off` the key is absent,** so `off` is a true
  byte-identical kill switch.
- **Discord notices** go through the v197 durable notify queue
  (`db/repositories/notify_queue.py`) to the ops channel (`_ops_channel()`,
  `loops.py:53-61`, which falls back to the trades channel). `run_scan`
  runs in a worker thread and cannot send to Discord itself
  (`scan_run.py:499-501`). A notice is never an alert embed.
  - On each transition: one message with the label, the trigger numbers
    (breadth %, sectors down/total, speed, SPY and QQQ ATR move, VIX level
    and change) and the time.
  - On entering SHOCK, and on a RECOVERY → SHOCK second leg: the message
    also lists every open **long**, one line each, written for someone with
    resting orders at a broker:
    - ticker, entry, stop, **last price**, open R
    - age
    - **"THROUGH STOP"** if the last price is already past the stop.
      Otherwise "stop at broker untouched: X.XX".

    It ends with "The bot moved no stop and closed nothing. Stop move-up
    and long block are pending screen (v209 Track 2)."
  - Rate limit: at most one notice per `SHOCK_MIN_DWELL_MIN`, **except**
    any transition *into* SHOCK, which is always sent. A second leg is the
    most actionable message for open positions.
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
  - the two-consecutive-readings rule; readings before
    `SHOCK_OPEN_SETTLE_MIN` never count
  - hysteresis (a reading between the entry and exit bars holds the state)
  - minimum dwell
  - re-entry from RECOVERY on rising breadth at 0.30 and on a new SPY
    session low
  - overnight carry, both a gap-up repair and a second leg down
  - an `insufficient` reading holds the state; a missing SPY frame leaves
    RECOVERY waiting
- **Gating:** `!check` and the recap never write a reading; a pass outside
  `is_us_market_active()` never steps the state.
- **Kill switch:** under `off` there are no writes, no notices and no
  `shock_state` key.
- **Replay of 2026-11-05.** A fixture built from the replica's readings,
  reconstructed from the day's partial bars, must reach SHOCK **no later
  than** the 14:36 UTC STX long entry.
- **Long and short plans are byte-identical** under `MARKET_SHOCK_MODE=off`
  and `shadow`, apart from the new `entry_context.shock_state` key (pinned
  byte-for-byte, as for any short-side change).
- **Repository round-trip** against the shared `swing-db` replica, run
  after `/replicate-prod-db`.
- **Notice formatting:** zero open longs, many open longs, a long
  already through its stop, the rate limit and its SHOCK-entry exemption.
- **Frontend:** the badge in all three states and the narrow-width
  wrapping.

## Track 2 — the shock-conditioned short screens

Both screens run on the standard Stage −2 machinery
(`backtest-methodology.md` § Funnel stages): point-in-time S&P 500 members,
2010-01-01..2019-12-31, the fixed race, K = 20 matched random bars, and the
standard frictions: 5 bps slippage a side, commission, and the short
borrow charge `BORROW_RATE_ANNUAL` that `screen_idea.py` already applies.
The pass rule is unchanged and **one shot each.** The definitions below are
**frozen at this commit.** A changed value is a new idea with a new name.

The two ideas form **one `FAMILY`** (`shock_breakdown`), as v182's pair did
(`ideas/_range_breakdown.py`). They overlap: a failed-bounce close below
`Low[b]` is often also a 20-day-low close. The results doc cites
`ledger_qvalues` across every short idea screened so far: v104 Part B, v182
and these two.

### The shared daily inputs

The idea interface reads per-symbol context series (`screen/context.py`,
as `dollar_drop` reads `UUP`). It has no cross-sectional input, so:

- **`BREADTH_ATR1` (context symbol, precomputed).** Its `Close[t]` is
  `d_breadth[t]`: the share of that date's point-in-time S&P 500 members
  with `(Close[t] − Close[t−1]) / ATR14[t−1] ≤ −1.0`. The ATR uses bars
  dated `t−1` and earlier only.
  - It is a continuous fraction, not a 0/1 flag, so it passes the
    loader's `trailing_z` coverage check (`screen_idea.py:351-364`,
    `MIN_Z_COVERAGE` 0.95) the way `UUP` does. If the precompute task
    measures coverage below 0.95 anyway, the task **stops and reports**.
    It never changes the shared v174 load checks without a spec amendment.
  - A plan task builds it and pins its no-lookahead behaviour with a
    test: truncating the input at `t` leaves `d_breadth[t]` unchanged.
- **`^VIX` daily (context symbol, fetched).** A plan task fetches
  2009–2019 daily `^VIX` from Yahoo, the same source as the tape. It is
  the one new data dependency.
- **Where the two files live.** `screen/context.py:138-151` reads a
  context file by stem, and `scripts/backtest/cache_dir_source.py:66-69`
  `listing()` treats every `*.csv` in the cache dir as a ticker. So the
  plan either stores both files where the context loader finds them but
  `listing()` excludes them, or extends `listing()` to skip context stems.
  Either way, a test pins that no ticker-listing script ever sees
  `BREADTH_ATR1` or `^VIX`.
- **The daily shock state**, computed inside each idea from the two
  context series, using bars dated `t` and earlier only:
  - It **enters** SHOCK on any date with `d_breadth[t] ≥ 0.40`.
  - While in SHOCK, it **releases** on the first date `t` with
    `d_breadth[t] ≤ 0.10` and `^VIX Close[t] < ^VIX Close[t−1]`. The state
    on date `t` itself is still SHOCK.
  - On `t+1` the state is NORMAL **unless** `d_breadth[t+1] ≥ 0.40`, in
    which case it is SHOCK again. The entry rule is evaluated as usual on
    every date, including the date after a release.
  - There is no RECOVERY tier, because daily bars cannot see the intraday
    repair.
  - A test pins this reading, including re-entry on the day after a
    release.

### Idea 1 — `shock_support_break_short`

- the daily shock state is SHOCK on `t`
- and `Close[t] < min(Low[t−20 .. t−1])`: a close below the prior 20-day low
- and **first break only:** no bar in the same SHOCK episode before `t`
  closed below its own prior 20-day low
- short at the next open; `RACE = "fixed"`, `CAP = 10`,
  `DIRECTION = "short"`

### Idea 2 — `shock_failed_bounce_short`

The daily shock state is SHOCK on `t`, and:

1. **A decline.** Some `b` in `t−5 .. t−1` with
   `Close[b−1] ≤ max(High[b−10 .. b−2]) − 1.0 × ATR14[b−2]`. That is, a
   decline of at least 1 ATR from the recent high.
2. **A bounce bar.** That `b` has `Close[b] > Close[b−1]`.
3. **A lower high.** `High[b] < max(High[b−10 .. b−2])`.
4. **The failure.** `Close[t] < Low[b]`, and no bar between `b+1` and
   `t−1` closed below `Low[b]` (first failure only).
5. If several bars qualify as `b`, the latest one counts.

Short at the next open; `RACE = "fixed"`, `CAP = 10`, `DIRECTION = "short"`.

The race uses its standard 1.5 × ATR14 stop. **The live follow-on's
placeable stop is a resting buy-stop just above `High[b]`.** It is recorded
here so that a pass can be turned into orders; it is not part of the
frozen race.

### Printed alongside each verdict (never gating)

Every one of these is frozen now, before any TRAIN result is read.

- **Shock-matched second null.** The standard null matches ticker, month
  and trend state (`screen/null.py:74-75`), never the shock state. So the
  standard paired delta mixes the stock trigger with the market's drift
  after a shock day. A second null of K = 20 bars drawn **only from the
  same ticker's SHOCK days** separates the two. It is printed beside the
  verdict.
- **Unconditional control.** `control_events`: the same trigger with the
  shock state ignored, as v182 did (`ideas/range_breakdown_close.py:38-42`).
  It shows whether "conditional" adds anything over "a 20-day-low close
  short works anyway".
- **Outcome-blind preflight.** Before the shot is spent, and before any
  race is run, the screen prints:
  - shock days per year
  - shock weeks per year (the bootstrap's clusters, `verdict.py:62-64`)
  - event counts per year

  This lets the results doc state the effective N. It does not decide
  whether to run: the shot is run as registered. If it fails mainly
  because years are empty, the doc says so.
- **Gap split.** Results bucketed by the next-open gap relative to the
  signal close: `≤ −1 %`, `−1 % .. +1 %`, `≥ +1 %`.
  - The race fills the entry at the next open, gap included, and fills
    any gap through the stop at the open (`race.py`).
  - A gap-up open after a flush (a V-reversal) is exactly where these
    shorts lose, so this split shows how much of the result rests on it.
- **Day of the episode.** The day after the breadth peak, versus later
  days of the same SHOCK episode. Capitulation-then-rip patterns put the
  first entry at the worst point.
- **Friction stress.** The book re-priced at 3 × slippage (shock-day
  spreads widen 2–5×), using `screen_idea.py`'s existing stress path.
- **`skipped_overlap`.** Events dropped by the race's overlap rule
  (`race.py:237-291`), printed next to N.

### What the screens can and cannot say

- **They test the daily version.** A pass says that breadth-shock-conditioned
  breakdown shorts carry information at daily resolution, on the
  point-in-time S&P 500. **It does not license the Track 1 detector's
  labels.** The two are different rules:
  - `SHOCK_D` has no sector clause, no fast path, no VIX relief and no
    RECOVERY tier.
  - `SHOCK_D` runs on the index membership; the detector runs on the
    watchlist.

  The follow-on must replay the live detector itself: Stage −1
  reachability on the bot's own replay over the 15-minute Alpaca store
  (v162, history from about 2016), then the funnel.
- **The year rule may sink a crash-only edge.** The rule needs the same
  sign in at least 7 of 9 years (2011–2019), and a year with no events
  counts against. 2017 had almost no shock days. A `SCREEN-FAIL` or
  `SCREEN-UNDERPOWERED` is closed and is not re-run with a looser
  definition.
- **The shadow log alone never opens live behaviour.** It is in-sample, on
  few episodes. After a fail, live shock behaviour needs a new idea that
  passes its own screen, or the bot's-replay funnel above. The shadow log
  can motivate an idea; it cannot license one.
- **Live-path gaps the screen cannot model:**
  - the short-sale uptick rule (SSR, once a stock is down 10 % from the
    prior close, for that day and the next)
  - hard-to-borrow or no-locate names
  - squeeze risk in heavily shorted names (memory and chip names can rip
    5–10 % on a headline)

  The follow-on spec must handle these on the order path, starting from
  v183's gap-aware short sizing and squeeze notice.

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

## Rollback

- **Behaviour.** Set `MARKET_SHOCK_MODE=off` (it hot-reloads with SIGHUP).
  Then there are no readings, no state writes, no notices and no
  `shock_state` key: the bot behaves as bot 2.16.5 did.
- **Schema.** The Alembic revision ships a working `downgrade()` that drops
  both tables. Both tables are additive and nothing else reads them, so
  older code runs against the new head. But `scripts/ops/rollback_to.sh` to
  a release **before** this revision must run
  `alembic downgrade <previous head>` first, or the old image will refuse
  an unknown head. The plan's deploy task verifies what `rollback_to.sh`
  does with a newer head, and writes that step into
  `docs/deploy/DEPLOY_HETZNER.md` if the script does not handle it.
- **Stored plans.** Plans written with `entry_context.shock_state` keep the
  key after a rollback. Older readers ignore unknown `entry_context` keys,
  so no upcasting is needed.

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
- **Stale partial bars outside regular hours.** Readings are stepped only
  while `data.is_us_market_active()` is true, never on the scan's wider
  `in_session()` window. Weekend and pre-market frozen bars never produce a
  reading.
- **VIX tape gaps.** Every rule that uses VIX has a non-VIX path. A missing
  VIX never blocks a transition into SHOCK. It can delay RECOVERY only
  through `RECOVERY_VIX_OFF_HIGH_PCT`, and the SPY retrace still applies.

## Panel review

Run 2026-11-05 on `512dcf83`, one role at a time. BLOCKING findings first.

- quant-researcher [BLOCKING]: the counterfactual figures had no dated window, no N for the filtered rows and no source -- applied (window 2026-07-06..2026-11-05, 962 of 992, 84 days, kept and blocked N per row, replica source).
- quant-researcher [BLOCKING]: "about 20 longs after the flip" contradicted the 12 blocked by the `bear_volatile` rule -- applied (re-queried: 18 opened after 14:36 UTC, 12 closed and 6 open; those 12 are the book's only closed `bear_volatile` longs; "about 7 weeks" corrected to 84 trading days).
- staff-engineer [BLOCKING]: no rollback written -- applied (§ Rollback: `off` is a full kill switch, a working `downgrade()`, the `rollback_to.sh` head check is a deploy-task step).
- veteran-trader [BLOCKING]: the open-long notice gave nothing to act on -- applied (last price, open R, THROUGH STOP or "stop at broker untouched", an explicit "nothing moved" line).
- veteran-trader [BLOCKING]: the next-open short fill had no gap handling or split -- applied (the race's gap fill is stated; a gap-bucket split is printed).
- veteran-trader [BLOCKING]: short frictions understated (spreads, SSR, borrow) -- applied (the existing borrow charge is named, a 3x-slippage stress is printed, SSR, locate and squeeze are named as live-path gaps for the follow-on).
- staff-engineer: a 0/1 `SHOCK_D` series fails the z-coverage load check -- applied (the context is now the continuous `BREADTH_ATR1` fraction, and the state is computed inside the idea; if coverage still fails, the task stops rather than change shared checks).
- staff-engineer: no `^VIX` daily history in the cache -- applied (a fetch task is named).
- staff-engineer: a synthetic CSV would be listed as a ticker -- applied (location rule plus a test that pins it).
- staff-engineer: `in_session()` is wider than US hours -- applied (stepping is gated on `is_us_market_active()`).
- staff-engineer: `!check` and the recap would step the state -- applied (an explicit `step_shock` argument; only `session_scan` steps).
- staff-engineer: the VIX tape depends on `TAPE_SHARED_ENABLED` and `MARKETDATA_LAYER` -- applied (named; the plan verifies the prod values; the badge shows "VIX missing").
- staff-engineer: the worker thread cannot send to Discord -- applied (v197 notify queue to `_ops_channel()`).
- staff-engineer: the label must reach every plan builder as an argument -- applied (main loop, strategy pass, `short_run`, requote).
- staff-engineer: reuse the scan's sector map; SPY/QQQ fallbacks -- applied.
- staff-engineer: no transaction or retention for the two writes -- applied (one transaction, 180-day retention, owner and drop condition).
- staff-engineer: `off` must omit the key; the sector ratio was presented as a count -- applied (`SHOCK_SECTORS_FRAC`, key absent under `off`).
- quant-researcher: the null is not shock-matched -- applied (a printed shock-matched second null; the claim is reworded).
- quant-researcher: no unconditional control -- applied (`control_events`, printed).
- quant-researcher: `SHOCK_D` differs from the live detector -- applied (a pass explicitly does not license the detector's labels).
- quant-researcher: the release rule was ambiguous -- applied (the t+1 reading is spelled out and pinned by a test).
- quant-researcher: effective N from clustered episodes -- applied (an outcome-blind preflight printing shock days, weeks and events per year; the shot is still run as registered).
- quant-researcher: the shadow log was a back door after a fail -- applied (the shadow log can motivate an idea, never license one).
- quant-researcher: multiple comparisons and overlap -- applied (one `FAMILY`, `ledger_qvalues` cited).
- quant-researcher: no first-break clause; overlap drops are silent -- applied (a first break per episode; `skipped_overlap` printed).
- veteran-trader: a dead-cat bounce leaves RECOVERY through a second leg -- applied (cheaper re-entry at 0.30 rising breadth or a new SPY session low).
- veteran-trader: the first reading measures the opening gap -- applied (two consecutive readings, a 15-min settle).
- veteran-trader: the rate limit could swallow a second-leg notice -- applied (entry into SHOCK is exempt).
- veteran-trader: report the day after the peak separately -- applied (printed split).
- veteran-trader: Idea 2 needs a placeable stop and a squeeze cap -- applied (a buy-stop above `High[b]` recorded for the follow-on; squeeze handling is on the follow-on's order path, from v183).
