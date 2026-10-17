# v170 execution feed: before/after render

Before: `0fd32eda` (main). After: `4ed34a0c` (v170 branch). Same fixtures both sides (`scripts/dev/render_feed_samples.py`): sizing 54.35 sh, risk $250; after v170 also a linked paper record of 54.35 sh.

Buttons on every plan-backed feed message after v170: 📊 Chart · 🔍 Breakdown · ⭐ Watch · 💵 P&L now. Before: none.

## ticket place long

Before:

~~~
content: 🆕 NEW SETUP · ▲ LONG AAPL · PLACE
title: 🆕 ▲ LONG AAPL · PLACE
```ansi
[1;32m▲ LONG[0m
entry [1;36m182.40[0m
stop  [1;31m177.80[0m
TP1   [1;32m189.10[0m [1;33m1.5R[0m
TP2   [1;32m195.00[0m [1;33m2.7R[0m
```
**BUY STOP 182.40 · 54 sh (risk $250)**
SELL STOP 177.80
TP1 SELL LIMIT 189.10 · 27 sh (50%)
RUNNER 27 sh → TP2 195.00 / trail 2×ATR — stop moves are pinged here
Stop → entry once price reaches 185.75
Cancel if: not triggered by the close of ≈ Wed 21 Oct (5 sessions), or price reaches 177.80 first
~~~

After:

~~~
content: 🆕 NEW SETUP · ▲ LONG AAPL · PLACE
title: 🆕 ▲ LONG AAPL · PLACE
```ansi
[1;32m▲ LONG[0m
entry [1;36m182.40[0m
stop  [1;31m177.80[0m
TP1   [1;32m189.10[0m [1;33m1.5R[0m
TP2   [1;32m195.00[0m [1;33m2.7R[0m
```
**▶ BUY STOP 182.40 · 54 sh**
🛑 SELL STOP 177.80 · if hit -$248.40 · −1.0R
💰 SELL LIMIT 189.10 · 27 sh · if hit +$180.90 · +1.5R
🏃 27 sh: 🎯 SELL LIMIT 195.00 · if hit +$340.20 · +2.7R · 〜 trail 2×ATR, stop moves pinged here
⚖ stop → entry at ≥ 185.75
⏳ CANCEL after Wed 21 Oct (5 sessions) · ⛔ CANCEL if ≤ 177.80 first
~~~

## ticket place short

Before:

~~~
content: 🆕 NEW SETUP · ▼ SHORT AAPL · PLACE
title: 🆕 ▼ SHORT AAPL · PLACE
```ansi
[1;31m▼ SHORT[0m
entry [1;36m50.00[0m
stop  [1;31m52.00[0m
TP1   [1;32m46.00[0m [1;33m2.0R[0m
TP2   [1;32m43.00[0m [1;33m3.5R[0m
```
**SELL STOP 50.00 · 54 sh (risk $250)**
BUY STOP 52.00
TP1 BUY LIMIT 46.00 · 27 sh (50%)
RUNNER 27 sh → TP2 43.00 / trail 2×ATR — stop moves are pinged here
Stop → entry once price reaches 48.00
Cancel if: not triggered by the close of ≈ Wed 21 Oct (5 sessions), or price reaches 52.00 first
~~~

After:

~~~
content: 🆕 NEW SETUP · ▼ SHORT AAPL · PLACE
title: 🆕 ▼ SHORT AAPL · PLACE
```ansi
[1;31m▼ SHORT[0m
entry [1;36m50.00[0m
stop  [1;31m52.00[0m
TP1   [1;32m46.00[0m [1;33m2.0R[0m
TP2   [1;32m43.00[0m [1;33m3.5R[0m
```
**▶ SELL STOP 50.00 · 54 sh**
🛑 BUY STOP 52.00 · if hit -$108.00 · −1.0R
💰 BUY LIMIT 46.00 · 27 sh · if hit +$108.00 · +2.0R
🏃 27 sh: 🎯 BUY LIMIT 43.00 · if hit +$189.00 · +3.5R · 〜 trail 2×ATR, stop moves pinged here
⚖ stop → entry at ≤ 48.00
⏳ CANCEL after Wed 21 Oct (5 sessions) · ⛔ CANCEL if ≥ 52.00 first
~~~

## ticket do-not-place

Before:

~~~
content: 🆕 NEW SETUP · ▲ LONG AAPL · DO NOT PLACE
title: 🆕 ▲ LONG AAPL · DO NOT PLACE
```ansi
[1;32m▲ LONG[0m
entry [1;36m182.40[0m
stop  [1;31m177.80[0m
TP1   [1;32m189.10[0m [1;33m1.5R[0m
TP2   [1;32m195.00[0m [1;33m2.7R[0m
```
**DO NOT PLACE — portfolio heat cap reached**
levels: entry 182.40 · stop 177.80 · TP1 189.10
~~~

After:

~~~
content: 🆕 NEW SETUP · ▲ LONG AAPL · DO NOT PLACE
title: 🆕 ▲ LONG AAPL · DO NOT PLACE
```ansi
[1;32m▲ LONG[0m
entry [1;36m182.40[0m
stop  [1;31m177.80[0m
TP1   [1;32m189.10[0m [1;33m1.5R[0m
TP2   [1;32m195.00[0m [1;33m2.7R[0m
```
**DO NOT PLACE — portfolio heat cap reached**
levels: entry 182.40 · stop 177.80 · TP1 189.10
~~~

## filled

Before:

~~~
content: 🎯 ENTRY · ▲ LONG AAPL · FILLED
title: 🎯 ▲ LONG AAPL · FILLED
```ansi
[1;32m▲ LONG[0m
entry [1;36m182.40[0m
stop  [1;31m177.80[0m
TP1   [1;32m189.10[0m [1;33m1.5R[0m
TP2   [1;32m195.00[0m [1;33m2.7R[0m
```
**FILLED @ 182.40 (bot)**
Confirm your broker filled; the bot's R is measured from 182.40
Resting: SELL STOP 177.80 · TP1 SELL LIMIT 189.10
~~~

After:

~~~
content: 🎯 ENTRY · ▲ LONG AAPL · FILLED
title: 🎯 ▲ LONG AAPL · FILLED
```ansi
[1;32m▲ LONG[0m
entry [1;36m182.40[0m
stop  [1;31m177.80[0m
TP1   [1;32m189.10[0m [1;33m1.5R[0m
TP2   [1;32m195.00[0m [1;33m2.7R[0m
```
**▶ FILLED @ 182.40 (bot)**
Confirm your broker filled; the bot's R is measured from 182.40
Resting: 🛑 SELL STOP 177.80 · 💰 SELL LIMIT 189.10
~~~

## be_moved

Before:

~~~
content: 🛡️ MANAGE · ▲ LONG AAPL · BREAK-EVEN
title: 🛡️ ▲ LONG AAPL · BREAK-EVEN
**MOVE STOP → 182.40 now**
break-even
~~~

After:

~~~
content: 🛡️ MANAGE · ▲ LONG AAPL · BREAK-EVEN
title: 🛡️ ▲ LONG AAPL · BREAK-EVEN
**🛑 MOVE SELL STOP → 182.40 now**
⚖ break-even
🔒 if it fills: +$0.00 · 0.0R total
~~~

## tp1_partial

Before:

~~~
content: 💰 MANAGE · ▲ LONG AAPL · TP1
title: 💰 ▲ LONG AAPL · TP1
**TP1 FILLED 27 sh @ 189.10 (+1.5R)**
MOVE STOP on the runner → 182.40 now (runner floor)
~~~

After:

~~~
content: 💰 MANAGE · ▲ LONG AAPL · TP1
title: 💰 ▲ LONG AAPL · TP1
**💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$182.07 · +1.5R**
🛑 MOVE SELL STOP on the runner → 182.40 now (runner floor)
~~~

## stop_moved

Before:

~~~
content: ✂️ MANAGE · ▲ LONG AAPL · MOVE STOP
title: ✂️ ▲ LONG AAPL · MOVE STOP
**MOVE STOP → 186.00 now**
trail; +0.8R since the last ping
~~~

After:

~~~
content: ✂️ MANAGE · ▲ LONG AAPL · MOVE STOP
title: ✂️ ▲ LONG AAPL · MOVE STOP
**🛑 MOVE SELL STOP → 186.00 now**
〜 trail; +0.8R since the last ping
🔒 if it fills: +$279.27 · +1.1R total
~~~

## closed win

Before:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXITED · ✅ WIN +1.7R
title: 🏁 ▲ LONG AAPL · EXITED · ✅ WIN +1.7R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 191.20 / [1;31m177.80[0m
  +4.8% [1;32m1.7R[0m
```
**EXITED @ 191.20 — TP2 · +1.7R total**
If your broker order did not fill: SELL AT MARKET
~~~

After:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXITED · ✅ WIN +1.7R
title: 🏁 ▲ LONG AAPL · EXITED · ✅ WIN +1.7R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 191.20 / [1;31m177.80[0m
  +4.8% [1;32m1.7R[0m
```
**✅ EXITED @ 191.20 · 🎯 TP2**
🧾 +$421.21 · +1.7R (paper, gross)
If your broker order did not fill: SELL AT MARKET
~~~

## closed loss

Before:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
title: 🏁 ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 177.80 / [1;31m177.80[0m
  −2.5% [1;31m−1.0R[0m
```
**EXITED @ 177.80 — stop · −1.0R total**
If your broker order did not fill: SELL AT MARKET
~~~

After:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
title: 🏁 ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 177.80 / [1;31m177.80[0m
  −2.5% [1;31m−1.0R[0m
```
**❌ EXITED @ 177.80 · 🛑 stop**
🧾 -$250.01 · −1.0R (paper, gross)
If your broker order did not fill: SELL AT MARKET
~~~

## closed unsettled

Before:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
title: 🏁 ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 177.80 / [1;31m177.80[0m
  −2.5% [1;31m−1.0R[0m
```
**EXITED @ 177.80 — stop · −1.0R total**
If your broker order did not fill: SELL AT MARKET
~~~

After:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
title: 🏁 ▲ LONG AAPL · EXITED · ❌ LOSS −1.0R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 177.80 / [1;31m177.80[0m
  −2.5% [1;31m−1.0R[0m
```
**❌ EXITED @ 177.80 · 🛑 stop**
🧾 −1.0R (paper, gross)
If your broker order did not fill: SELL AT MARKET
~~~

## close at market

Before:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · CLOSE AT MARKET · ✅ WIN +1.2R
title: 🏁 ▲ LONG AAPL · CLOSE AT MARKET · ✅ WIN +1.2R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 187.00 / [1;31m177.80[0m
  +2.5% [1;32m1.2R[0m
```
**CLOSE AT MARKET now — higher high failed on cooling range and volume**
SELL AT MARKET at market: the runner's higher high failed on cooling range and volume (bot exit @ 187.00); no resting order covers this exit
+1.2R total
~~~

After:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · CLOSE AT MARKET · ✅ WIN +1.2R
title: 🏁 ▲ LONG AAPL · CLOSE AT MARKET · ✅ WIN +1.2R
```ansi
[1;32m▲ LONG[0m
[1;36m182.40[0m → 187.00 / [1;31m177.80[0m
  +2.5% [1;32m1.2R[0m
```
**✅ CLOSE AT MARKET now — higher high failed on cooling range and volume**
SELL AT MARKET at market: the runner's higher high failed on cooling range and volume (bot exit @ 187.00); no resting order covers this exit
🧾 +$307.08 · +1.2R (paper, gross)
~~~

## cancel expired

Before:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXPIRED · ⏹️
title: 🏁 ▲ LONG AAPL · EXPIRED · ⏹️
**CANCEL BUY STOP 182.40**
not triggered within 5 sessions
~~~

After:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · EXPIRED · ⏹️
title: 🏁 ▲ LONG AAPL · EXPIRED · ⏹️
**⏳ CANCEL BUY STOP 182.40**
not triggered within 5 sessions
~~~

## cancel invalidated

Before:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · INVALIDATED · ⏹️
title: 🏁 ▲ LONG AAPL · INVALIDATED · ⏹️
**CANCEL BUY STOP 182.40**
price reached the stop 177.80 before triggering
~~~

After:

~~~
content: 🏁 RESULT · ▲ LONG AAPL · INVALIDATED · ⏹️
title: 🏁 ▲ LONG AAPL · INVALIDATED · ⏹️
**⛔ CANCEL BUY STOP 182.40**
price reached the stop 177.80 before triggering
~~~

## time exit due

Before:

~~~
content: 🛡️ MANAGE · ▼ SHORT AAPL · PLAN UPDATE
title: 🛡️ ▼ SHORT AAPL · PLAN UPDATE
**BUY TO COVER AT MARKET 54 sh in the closing auction (16:00 ET)**
ten sessions since the fill; stage a market-on-close (MOC) buy to cover, and confirm your broker's order status before the auction
ignore this if you already exited on a stop or target
~~~

After:

~~~
content: 🛡️ MANAGE · ▼ SHORT AAPL · PLAN UPDATE
title: 🛡️ ▼ SHORT AAPL · PLAN UPDATE
**BUY TO COVER AT MARKET 54 sh in the closing auction (16:00 ET)**
ten sessions since the fill; stage a market-on-close (MOC) buy to cover, and confirm your broker's order status before the auction
ignore this if you already exited on a stop or target
~~~

## Checks (alert-surface gate)

- [x] Ticket long: `▶ BUY STOP 182.40 · 54 sh`; stop `🛑 SELL STOP 177.80 · if hit -$248.40 · −1.0R`; TP1 `💰 SELL LIMIT 189.10 · 27 sh · if hit +$180.90 · +1.5R` (the TP1 line also carries its R, an addition to the spec figure); runner `🏃 27 sh: 🎯 SELL LIMIT 195.00 · if hit +$340.20 · +2.7R · 〜 trail 2×ATR, stop moves pinged here`; `⚖` and `⏳ CANCEL` / `⛔ CANCEL` lines present.
- [x] Ticket short flips every verb (`SELL STOP` entry, `BUY STOP` stop, `BUY LIMIT` targets) and the comparison glyphs (`⛔ CANCEL if ≥ 52.00`, `⚖ stop → entry at ≤ 48.00`).
- [x] Do-not-place ticket keeps its wording and shows no "if hit" $.
- [x] Filled leads `▶ FILLED`; be_moved and stop_moved say `MOVE SELL STOP` and carry `🔒 if it fills: … total`; never "locked". Deviation: be_moved at the entry prints `🔒 if it fills: +$0.00 · 0.0R total` (R is plain `0.0R`, never `+-0.0R`; the money zero keeps its `+`).
- [x] TP1 partial: `💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$182.07 · +1.5R`, then `🛑 MOVE SELL STOP on the runner → 182.40 now (runner floor)`.
- [x] Closed win / loss: `✅ EXITED @ 191.20 · 🎯 TP2` / `❌ EXITED @ 177.80 · 🛑 stop`, then `🧾 +$421.21 · +1.7R (paper, gross)` / `🧾 -$250.01 · −1.0R (paper, gross)` (the record's settled amount).
- [x] Closed unsettled: `🧾 −1.0R (paper, gross)`, no $.
- [x] Close at market and time exit due: broker verb words on every order line; wording otherwise unchanged from Before (the existing "SELL AT MARKET at market" repetition is pre-v170).
- [x] Cancels: `CANCEL` on every cancel line; `⏳` leads the expiry cancel, `⛔` the invalidation cancel.
- [x] The `content:` (push-preview) line of every kind is identical Before and After.
- [x] `⚠` appears only in warnings (none in these fixtures); no glyph is used for two meanings.

## Complexity

`python -m radon cc -s -n C` over every file the plan touched printed only legacy functions no v170 commit changed (checked with `git diff 0fd32eda HEAD`): `TradeLog.check_near_tp_timeout` F 42, `update_open_trades` E 31, `get_extended_stats` D 25, `get_stats` D 21, `close_if_live_price_hit` C 20, `get_trades` C 18, `log_trade` C 15, `closed_r_multiple` C 14, `_shadow_sizing` C 14, `weak_summary` C 12, `close_trade_manual` C 11 (all `performance.py`; v170 only added `trade_for_plan`); `_sync_run_scan` F 100 (`scan_run.py`); `breakdown_embed` C 12 (`views.py`); `build_closed_trade_embed` C 17, `regenerate_chart_for_trade` C 12 (`lifecycle_embeds.py`). `instruction_for` and `notify_plan_events` do not appear.

## Full suite

One full run on the branch at `1cd33c39`: 11450 passed, 2 failed, 4 skipped, 0 xfailed. Both failures were `tests/infra/test_swallowed_ratchet.py` (six new untagged `except Exception` handlers: 249 against BASELINE 243). Commit `0168a485` routed all six through `swallowed()`; the ratchet file was re-run alone (10 passed, count back to 243), as were the test files of every file that commit touched. No second full run, per the one-run-per-plan rule.
