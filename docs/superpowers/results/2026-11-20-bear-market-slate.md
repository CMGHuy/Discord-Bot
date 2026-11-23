# Bear-market slate 2026-11-20

**Source:** read-only production query (VM Postgres `trades` ⨝ `journal_entries`
on `trade_id`, `plans`, `benchmark_bars`; logs under `/opt/swing-bot/logs`),
2026-11-20. **Edge:** expectancy. A slate row is a hypothesis: nothing here moves
a gate, a threshold or a live alert, and every entry or filter row still needs
its own screen verdict before a spec.

## 1. Regime

Rule: a bear day is `close < SMA50` and `SMA50[t] < SMA50[t-5]` (SPY daily).
The regime starts on the earliest bear day after which at least 70% of
sessions are bear days, which gives **2026-10-22**. Since then 18 of 22 sessions
are bear days. On 2026-11-19 (last final bar): SPY 715.83, SMA50 760.24 and
falling, SMA200 730.33 and still **rising**, −8.1% from the 52-week high of
779.09 (2026-10-06). VIX was 28.44 on 11-19 and 32.08 intraday on 11-20.

Read: this is a correction with stress (SMA200 still rising, VIX ≥ 28), not a
confirmed secular bear market like 2000–02 or 2008.

## 2. Damage, live book

`doc.source` is `confluence` on every trade, so the strategy path has N = 0.
R is the stored `r_realized`.

| Window | Dir | N | WR % | ExpR | avg win R | avg loss R |
|---|---|---|---|---|---|---|
| main ledger, 09-18..10-21 | ALL | 172 | 26.7 | +0.162 | n/a | n/a |
| since 10-22 (all main ledger) | ALL | 399 | 23.1 | −0.079 | +2.40 | −1.10 |
| since 10-22 | LONG | 321 | 21.5 | −0.114 | +2.43 | −1.09 |
| since 10-22 | SHORT | 78 | 29.5 | +0.066 | +2.32 | −1.17 |

- Compare against the main ledger only. The all-ledger "before" figure
  (N 776, WR 50.6%, ExpR −0.047) mixes in the pre-09-18 exit model, which
  had a very different win/loss shape.
- LONG since 10-22 sums to about −36.6R (−0.114 × 321) and is where the
  money went. SHORT is about +5.1R, but at N = 78 that is indistinguishable
  from zero.
- Plans since 10-22: 323 LONG vs 90 SHORT (78% long into a falling tape).
- Give-back did not worsen: winners realised 0.71 of MFE before vs 0.73 since
  (LONG). Gap-through-stop exits are rare (13 of 182 LONG stop-outs since 10-22).
- Logs (2026-11-09 onward only) show 330 `plan rejected (` lines, all
  `rebuild:no_scenario`. The 2% dollar-risk cap is not rejecting shorts.
- The live regime label (`scanning/regime.py`, SPY vs EMA200) is slow, not
  broken. It read "Bullish (SPY +3.9% vs rising 200EMA)" on 11-12 and
  "Bearish (SPY −4.4% vs rising 200EMA)" on 11-20 (prod `bot.log`). It flips
  only after a drop of this size, and it only feeds `score_confidence(regime_trend=…)`.
  It never gates an alert. The bot has no fast stress signal; B1 would be the first.

## 3. Bear routes already closed — do not re-propose

From `docs/claude/backtest-methodology.md` § Closed pre-registrations:
`REGIME_ALLOW` (v17), bearish arms of seven bullish masks (v93), Bull Trap /
Vol Expansion Breakdown / Earnings Gap Drift shorts (v104 B), Downtrend
Overbought Fade `1w` (v113 A), inverse-ETF longs (v98, v113 D),
`range_breakdown_close` (v182), `shock_support_break_short` and
`shock_failed_bounce_short` (v211), Turtle Soup structural arm (v180). The
bullish RS-leader arm (v34) was negative at every threshold. The repo's
evidence is that **shorting single names does not pay in this universe**. The
bear-market lever is how the bot handles longs.

## 4. Hypotheses (parameters frozen 2026-11-20)

All three wait for **screen v2** (v230 re-screen / v238). The v1 matched null
measured as biased (v230 placebo, `e5776eb2`, "stop gate 1 BIAS"), so spending
a one-shot screen id on v1 would waste it.

### B1. `vix_curve_long_gate` — avoid mode (veto on longs)

- Claim: long entries opened while `^VIX / ^VIX3M > 1.00` (curve in
  backwardation, read from the prior session's close) underperform long
  entries opened while it is not. Gate state latches on at > 1.00 and off
  below 0.95.
- Test: avoid-mode screen with a control arm. Longs in backwardation vs the
  matched null, using the v2 instrument's race, costs and universe.
- Differs from `REGIME_ALLOW`: that gate used price-trend regime labels per
  strategy cell. This one uses implied-volatility term structure (stress, not
  trend) across all longs.
- Prerequisite: `^VIX3M` daily history (Yahoo, from about 2007) is not
  cached; only `market_data/vix/VIX_daily.csv` exists. A context-symbol fetch
  is needed, like v211's `--vix-context`.
- Overlap: v233 lists `vix_curve` as an allocator feature. A pass here makes
  that feature a single-rule baseline v233 must beat.

### B2. `uptrend_pullback` — dip-buy in names still in a long-term uptrend

- Already `screen-uptrend_pullback` SCREEN-PASS on v1 (N 26912, ΔExpR +0.3672R,
  9/9 years, PIT S&P 500 2010–2019). It is one of the twelve v1 rows in the
  v230 batch re-screen, so its spec waits for `screen2-uptrend_pullback`.
  Never screen it separately.
- Bear relevance: in a correction with SMA200 still rising, `close > SMA200`
  plus RSI(2) < 10 is exactly the washout entry. The 2010–2019 window has no
  2008, 2020 or 2022, so any later spec must show results by regime.

### B3. `vix_stretch_reversal_long` — capitulation buy

- Trigger: `^VIX` close ≥ 1.30 × its 20-session SMA within the last 5
  sessions, then the first session where VIX closes below the prior session's
  close **and** the ticker closes above its prior session's high. Buy at the
  next open. One event per VIX episode per ticker.
- Universe: SPY, QQQ and the screen universe's top-beta tercile (60-session
  beta to SPY, known at `t`).
- Differs from the v211 shock screens: those were shorts taken during a
  shock. This is a long taken on the release.

### Addendum 2026-11-23 — week 11-16..11-20 and B4–B6

Read-only production query, 2026-11-23, main ledger. SPY fell 8.6% from the
11-13 close to the 11-20 close, closed below SMA200 from 11-18 on, and closed
11-20 at its low. VIX went 19.3 → 37.6.

| Closed 11-16..11-23 | N | WR % | ExpR | avg win R | avg loss R | sum R |
|---|---|---|---|---|---|---|
| LONG | 74 | 14.9 | −0.39 | +1.90 | −0.79 | −29.1 |
| SHORT | 26 | 34.6 | +0.15 | +2.34 | −1.01 | +3.9 |

- The bot issued 101 plans: 73 bullish, all from the confluence source. Only 2 of
  90 watchlist names rose. LONG stop-outs cost −47.8R.
- Entry-day VIX vs ExpR on those 74 LONG trades: <20 −1.37 (n 8), 20–25 −0.42
  (n 20), 25–30 −0.46 (n 36), >30 +0.60 (n 9). Too thin to act on. The
  direction matches B3.
- Ticker vs its own SMA200 at entry: below −0.47 (n 54), above −0.19
  (n 20). Derived from the daily CSV (`entry_context` lacks the field), which
  can carry split artifacts.
- Worst LONG names: high beta (AMD, COHR, RKLB, RIOT). Best relative names:
  cybersecurity and staples (PANW, CRWD, WMT, PEP).
- Unresolved: the 7 still-open longs show +16.1R price-R, which is implausible
  for this tape. Quote timestamps are unverified, so do not use it.

These are hints, not evidence. They motivate the rows below, and each row
still needs its own screen verdict. Parameters frozen 2026-11-23.

### B4. `below_sma200_long_veto` — avoid mode

- Claim: long entries in a ticker whose prior-session close is below its own
  SMA200 (computable only with ≥ 200 bars) underperform long entries above it.
- Test: avoid-mode screen with a control arm. Longs below SMA200 vs the matched
  null, on the v2 instrument.
- Differs from `uptrend_pullback` (B2): B2 is an entry trigger (above SMA200 +
  RSI(2) < 10). B4 is a veto on every long the bot already issues.

### B5. `high_beta_stress_long_veto` — avoid mode

- Claim: long entries in the screen universe's top-beta tercile (60-session
  beta to SPY, known at `t`) underperform while the SPY Correction rule holds:
  prior SPY close < SMA50 and SMA50[t−1] < SMA50[t−6].
- Test: avoid-mode screen with a control arm. Top-tercile longs in Correction vs
  the matched null.

### B6. `book_drawdown_long_throttle` — book-level pause

- Claim: skipping new longs while the mean `r_realized` of the last 20 LONG
  trades **closed before the entry bar** is < 0 raises the book's long
  ExpR.
- Test: a single-name event screen cannot express it. It runs on a replayed
  bot book (v238 rung-4 output or its successor), comparing the paused book
  with the unpaused one. Window 20 and threshold 0 are frozen now. A changed
  value is a new idea with a new name.

B1–B6 are all long vetoes or long triggers, so they form one BH family.

### B7–B9 — the regime engine's three actions (frozen 2026-11-23)

The partner's goal on 2026-11-23: detect a bear market or a sharp downtrend
and stop issuing longs; tell a fake decline (a correction inside an uptrend)
from a real one; on a fake one prepare the pullback buy, on a real one issue
shorts. The classifier ships in shadow under its own spec, dated 2026-11-23.
Each action below goes live only through its own screen verdict.

The classifier states come from the prior session's close (SPY daily, ^VIX
daily):

- CORRECTION: SPY close < SMA50, SMA50[t] < SMA50[t−5] and SMA200[t] >
  SMA200[t−20].
- BEAR: close < SMA200 and SMA200[t] < SMA200[t−20], or SMA50 < SMA200 with
  close < SMA200. BEAR wins over CORRECTION.
- STRESS: ^VIX close ≥ 25 (an overlay on either state).

- **B9 `regime_engine_long_veto`, avoid mode.** Claim: long entries on BEAR
  days, or on CORRECTION days with STRESS on, underperform the matched null.
  This is the screen that licenses switching the live long veto on.
- **B8 `correction_release_long`, entry.** In CORRECTION, ^VIX closes ≥ 15%
  below its 5-session high and SPY closes above its prior session's high.
  Buy at the next open: SPY, QQQ, and screen-universe names above their own
  SMA200. One event per CORRECTION episode per ticker. Overlaps B3 (B3 has no
  state gate, B8 has no VIX-stretch threshold). Both stay in the family.
- **B7 `bear_state_rally_fail_short`, entry (short).** While SPY is in BEAR:
  the ticker closes below its SMA50, which sits below its SMA200. Within
  the last 3 sessions the high came within 0.5 ATR14 of SMA20 from below.
  Then the close drops below the prior session's low. Short at the next open.
  This is a new idea, not a re-run: it is gated on the BEAR state and none of
  the closed short pre-registrations in §3 was. The 2010–2019 window holds
  little BEAR time (2011, 2015–16, late 2018), so expect `UNDERPOWERED`
  unless screen v2's window reaches 2008 or 2022. That would be a
  measured answer, not a reason to loosen it.

## 5. Order

1. Screen v2 lands (v238, then the v230 batch re-screen, which includes B2).
2. Fetch `^VIX3M`, then screen B1.
3. Screen B3, then B4 and B5.
4. B2 gets a spec only if `screen2-uptrend_pullback` passes.
5. B6 waits for a replayed bot book.
6. B9, then B8 and B7, once the shadow engine is live (the engine is not a
   prerequisite of the screens, but they share its state definitions).

Not a hypothesis: the shadow regime engine (classifier, shadow log, alert
and site surfaces, base-rate study) has its own spec, dated 2026-11-23,
`Edge: none (integrity)`.

No integrity follow-up: an earlier reading that the regime line stopped logging
after 11-12 came from searching one rotated log file. It logs on every scan.
