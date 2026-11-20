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

## 5. Order

1. Screen v2 lands (v238, then the v230 batch re-screen, which includes B2).
2. Fetch `^VIX3M`, then screen B1.
3. Screen B3.
4. B2 gets a spec only if `screen2-uptrend_pullback` passes.

No integrity follow-up: an earlier reading that the regime line stopped logging
after 11-12 came from searching one rotated log file. It logs on every scan.
