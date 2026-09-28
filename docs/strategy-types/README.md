# Strategy types

One page per strategy: the trading idea, the exact algorithm the code runs
(entry rule, stop, target, exits), where it is wired in, and what the
measurements say about it. Each page names its source files. Code is
authoritative when a page lags. Traced from `main` at `6dd9636d` (2026-09-25).

Start with **[shared-mechanics.md](shared-mechanics.md)**. It covers the
shared tape gates, the direction/horizon gates, the three sizing families,
the 2% cap and the level-lifecycle finding, the exit model, and how to read a
badge. For how the bot as a whole decides (the confluence pipeline, gates,
plan building), see `docs/strategy/strategy.md`.

| Strategy | Style | Live gate | Sizing | Badge (registry) | Page |
|---|---|---|---|---|---|
| MACD | momentum resumption | bullish · 3m 4m 7m 8m 9m | ATR | **VALIDATED** | [macd.md](macd.md) |
| Volume Profile | bounce off a high-volume node | bullish · 7m | ATR | **VALIDATED** | [volume-profile.md](volume-profile.md) |
| VWAP | reclaim of a rising VWAP | bullish · 4w | ATR | WEAK | [vwap.md](vwap.md) |
| Break & Retest | retest of an old broken level | both · 2m 3m 4m | ATR | WEAK | [break-and-retest.md](break-and-retest.md) |
| Support/Resistance | breakout from a tight base | bullish · 2m 3m | structural (fixed 2%) | WEAK | [support-resistance.md](support-resistance.md) |
| Fibonacci | bounce at a 38.2–61.8% retracement | bullish · all | structural | WEAK | [fibonacci.md](fibonacci.md) |
| MA Ribbon | EMA/SMA stack aligning | bullish · all | ATR | WEAK (stale) | [ma-ribbon.md](ma-ribbon.md) |
| EMA Crossover | first pullback after a cross | both · all | ATR | WEAK (stale) | [ema-crossover.md](ema-crossover.md) |
| RSI Divergence | hidden divergence + RSI turn | both · all | ATR | WEAK (stale) | [rsi-divergence.md](rsi-divergence.md) |
| Elliott Wave | wave-3 breakout | both · 4w only | structural | WEAK (stale) | [elliott-wave.md](elliott-wave.md) |
| RSI | oversold bounce in a range | bullish · all | ATR | WEAK, negative ExpR | [rsi.md](rsi.md) |
| Fibonacci Continuation | break of the swing high after a held retracement | **masked** | structural | none (v103 NO-LIFT) | [fibonacci-continuation.md](fibonacci-continuation.md) |
| Bull Trap | failed breakout, short-only | **masked** | structural (v104 stop scope) | none (v104 NO-LIFT) | [bull-trap.md](bull-trap.md) |
| Vol Expansion Breakdown | breakdown in a falling, volatility-expanding market, short-only | **masked** | structural (v104 stop scope) | none (v104 NO-LIFT) | [vol-expansion-breakdown.md](vol-expansion-breakdown.md) |
| Earnings Gap Drift | unrecovered post-earnings gap-down, short-only | **masked** | structural (v104 stop scope) | none (v104 NO-LIFT) | [earnings-gap-drift.md](earnings-gap-drift.md) |

"Stale" means the registry row's `run_date` (2026-07-18) predates v31's
target arithmetic. No row post-dates the 2% cap (2026-09-21), and every figure
is subject to the lifecycle finding in shared-mechanics §4a (fixed by v104
for the strategies named in its own structural-stop scope list, currently
empty — see §4b).
