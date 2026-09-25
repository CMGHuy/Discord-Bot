# RSI oversold bounce

`ENTRY_FUNCS["RSI"]` = `rsi_entries` · signal `rsi_signal` · sizing **ATR
family** · gate **bullish, all horizons**. Shared rules:
[shared-mechanics.md](shared-mechanics.md).

## Idea

Mean reversion. After RSI has been oversold for a couple of days, buy the
first bar where it recovers and price confirms the bounce. Only do this in a
**sideways** market inside a structurally healthy long-term up-trend.

## Entry rule (bullish; bearish mirrors)

**The entry rule does not depend on the horizon.** The same bars fire on all
10 horizons; only sizing, holding time and the exit differ.

1. **Oversold, then recovering:** `RSI14[t−1] < 35` and `RSI14[t−2] < 35`
   (`os_level`), and `RSI14[t] ≥ 35`.
2. **Still low:** `RSI14 < 40`.
3. **Price confirms:** `close > High[t−1]` (`confirm = "prev_high"`).
4. **Not a falling knife:** `close > close[t−3]`.
5. **Long-term regime, slope only:** `MA200 > MA200[t−120]`. This is the one
   strategy without `close > MA200/MA50`, because dip-buys sit below the
   short MAs by construction.
6. **Range regime:** `ADX14 < 20` (`max_adx`, Task 95 rescue gate).
7. Shared: `atr_floor`, `atr_calm`, `vol_ok`.

Bearish: RSI above 65 for 2 bars and now ≤ 65, `RSI > 60`,
`close < Low[t−1]`, `close < close[t−3]`, and MA200 falling over 120 bars.
The same ADX gate applies.

`require_bb_range` (Bollinger containment) is off.

## Plan and exits

Stop `2 × ATR14`, capped at 2%. TP1 comes from the ATR ladder. Exits: trail
**2.0** × ATR, no TP2.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-09-10) | TRAIN 2020–23 | 38 | 23.7% | **−0.120** | **WEAK** (legacy badge refresh, pre-2% cap) |

**Negative expectancy** on current arithmetic. It is the weakest strategy in
the registry. The pre-v31 VALIDATED badge described deleted arithmetic and was
corrected on 2026-09-10. Reopening needs a new mechanism
(`backtest-methodology.md`).

## Pseudocode

```python
fire if RSI[t-1] < 35 and RSI[t-2] < 35 and 35 <= RSI[t] < 40
        and Close > High[t-1] and Close > Close[t-3]
        and MA200 > MA200[t-120] and ADX14 < 20 and tape_ok
```
