# Volume in context — reference notes

Source: six spreads from a Vietnamese forex/commodities TA handbook
("Sổ tay giao dịch ngoại hối & phân tích kỹ thuật", BigWhale), shared by the
partner on 2026-10-02. Translated and condensed here so specs can cite one
place. **This is teaching material, not measured evidence** — every rule below
is a hypothesis for this repo until it passes the acceptance funnel in
`docs/claude/backtest-methodology.md`.

## The one thesis

Volume measures **activity**. Price action measures **how price reacts**.
Structure (HH/HL vs LH/LL) measures **what state price is in**. Volume never
predicts direction on its own; it is read *after* structure and price action,
as supplementary data. "Don't let the indicator tell the story for price."

## The six lessons

1. **Falling volume ≠ falling price.** Price up + volume down = "price is still
   rising — check price action and structure." Price down + volume down = "it
   may still be falling — falling volume is not enough to call direction."
   Breakout + volume up = "activity is rising — worth attention."
2. **Volume cools after a breakout while the trend continues.** Breakout bar
   spikes; subsequent HH/HL legs print on lower and lower volume. That is a
   market moving from an explosive phase to a steadier one, not a reversal.
3. **Hide volume first.** Before reading any indicator ask: what is the trend?
   Are HH/HL still intact? Did the pullback break structure? Is the key
   support still defended? Is price action strong, weak or unclear? Only then
   ask what volume adds.
4. **Falling volume becomes a warning only alongside other signs** — candle
   range narrowing, price making less progress per leg, a failed higher high,
   price action slowing. The question changes from "is volume falling?" to
   "is price rising but finding it harder and harder to make new progress?"
   "Don't count one signal; look for agreement between several."
5. **Same volume, different meaning by context:**
   - breakout + volume spike — participation confirms the break;
   - pullback + volume decrease — healthy, low-conviction counter-move;
   - high volume + narrow price progress — **absorption** (supply/demand being
     soaked up at a level);
   - high volume + structure break — the break has participation.
6. **Workflow:** market context → price action → volume → compare price with
   volume → hypothesis → execution.

## How this maps onto the bot (2026-10-02)

| Lesson | Bot today | Follow-up |
|---|---|---|
| 5 (context decides) | `planning/quality.py:component_volume` rewards a high entry-bar volume ratio for every setup type | v122 tests a pullback dry-up gate instead of a score weight |
| 2/5 (breakout spike) | S/R and squeeze entries require ≥ `SR_VOLUME_MULTIPLE` | already aligned |
| 3 (structure first) | no HH/HL state anywhere; `swing_high_atr`/`swing_low_atr` snapshot keys never filled | v121 adds causal structure features to the entry-context snapshot |
| 5 (absorption) | nothing | v121 records it; no gate until measured |
| 4 (progress stall) | exits are ATR / R / time only | v123 tests a structure-aware runner exit |

Closed neighbours that these do **not** reopen: RSI Divergence
`min_volume_ratio` (volume *expansion*, opposite sign), v68 dead-cat-bounce
volume ratio, v92 adaptive runner trail and stall exit (ATR- and time-based,
not structure-based).
