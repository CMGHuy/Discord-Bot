# Break-even lock headroom — live book, 2026-11-23

Read-only measurement on the production book, used to license the fee-aware
break-even lock spec. The question: what would moving the break-even stop from
`entry` to `entry + lock` have done to the trades the bot actually closed? The
lock is two €1 broker fees plus the larger of 0.1% of position value or €1.

## Data

- **Book:** 2026-07-06 .. 2026-11-23. Of 1,395 closed trades, 1,360 were
  analysed (LONG 959, SHORT 401). 35 were dropped, 30 of them for having no
  shares snapshot.
- **Plans:** `plans.doc` (`working_stop`, `be_armed_session`, `tp1`,
  `breakeven_trigger_fraction`).
- **Trades:** `trades.doc` (`shares`, `realized_pnl_amount`, `exit_price`,
  `legs`), the `trades.entry`/`stop_loss` columns, and `journal_entries.outcome`.
- **FX:** `fx_daily_rates`, USD→EUR, about 0.86–0.91. The lock is converted at
  the open-day rate. All 89 tickers are treated as USD-quoted.
- **Bars:** daily OHLCV from `/opt/swing-bot/market_data/daily/<TICKER>.csv`.

## Results

| | ALL | LONG | SHORT |
|---|---|---|---|
| Break-even armed | 281 | 225 | 56 |
| Stopped at break-even (exit within 0.1% of entry while armed) | 116 | 96 | 20 |
| Actual R of those stops (sum) | +2.12R | +2.12R | 0 |

- **Lock distance:** median 0.34% of entry, which is **0.17R** (p10 0.13R, p90
  0.19R). Fees dominate at the book's position sizes.
- **Arm rule** (the further of the normal trigger and 2 × the lock distance):
  it would have delayed **0 of 281** arms. Every armed trade's trigger was
  ≥ 0.75R, and the largest 2 × lock distance was 0.68R.
- **Gain:** break-even stop-outs that become lock stop-outs: **+19.32R** against
  their actual R (about +0.16R each).
- **Cost:** armed trades that went on without stopping at break-even but traded
  into the entry→lock band after arming, so they would now close at the lock.
  - **Strict bound** (touch after the arm session and before the close day):
    −1.22R.
  - **Pessimistic bound** (the close day counts as a touch): −13.41R.
  - 92 of the 165 non-break-even armed trades armed and closed on the same
    daily bar. Daily bars cannot order those events, so the cost is only
    bounded.

| Net effect | ALL | LONG | SHORT |
|---|---|---|---|
| Strict | **+18.09R** (≈ +€294) | +14.16R (+€234) | +3.93R (+€60) |
| Pessimistic | **+5.91R** (≈ +€84) | +0.55R (+€2) | +5.36R (+€82) |

The net effect is positive under both bounds. On the LONG side the pessimistic
bound is roughly flat, so the case for LONG rests on the strict bound being
closer to the truth.

## Caveats

1. The cost is a bound, not a point estimate: daily bars, and same-bar
   arm/close days.
2. The lock is counted gross of fees. If stored P&L already includes fees,
   each break-even stop also carries about −€2 today (≈ −€232 total), and the
   lock removes exactly that. This is unverified.
3. "Break-even stop" means exit within 0.1% of entry while armed. Trail-stopped
   exits are excluded.
4. Instruments quoted in other currencies (SI=F, XAGUSD, XAUUSD) were assumed
   to be in USD.
