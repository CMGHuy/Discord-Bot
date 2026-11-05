# R-multiples and expectancy (ExpR)

## R

**R is the dollar amount risked on one trade**: the distance from entry to stop
times the position size. Every outcome is expressed as a multiple of it:

| Outcome | R |
|---|---|
| Stopped out at the planned stop | about -1R |
| Exit at half the risk lost | -0.5R |
| Exit at twice the risk gained | +2R |

Because outcomes are in R, trades of different size and price are comparable.
(The 2% cap limits the dollars behind 1R; see `docs/claude/` notes on the cap.)

## ExpR (expectancy)

**ExpR is the mean R-multiple across closed trades**: the average profit or loss
per trade, in units of risk.

    ExpR = win_rate x avg_win_R  -  loss_rate x avg_loss_R

Positive means the strategy makes money per trade on average; negative means it
loses. This repo ranks work by **pooled ExpR first, win rate second** (win rate
is a constraint, not the objective).

## Why win rate can rise while ExpR falls

Win rate counts how often a trade wins and ignores how much. ExpR falls if the
average win shrinks, or the average loss grows, by more than the extra wins add.

Made-up example, 100 trades each:

| | Wins | Losses | ExpR | Win rate |
|---|---|---|---|---|
| Baseline | 40 at +2R | 60 at -1R | (80 - 60) / 100 = **+0.20R** | 40% |
| Variant | 44 at +1.2R | 56 at -1R | (52.8 - 56) / 100 = **-0.03R** | 44% |

The variant wins more often but earns less per trade.

Typical causes when a filter or veto does this:

- it removes some big winners along with the losers;
- it moves the entry price, shrinking the distance to target on winners;
- it adds or cuts trades that were small wins or small losses.

Real case: v192 (gap-toward-stop reclaim veto), Stage 1, g = 0.10 gave
+3.49pp win rate but -0.129R ExpR, and failed the expectancy floor. A filter
that lifts win rate and lowers ExpR makes the strategy worse, which is why the
acceptance gates test ExpR.

## See also

- `docs/claude/edge-priorities.md`: the `Edge:` taxonomy and why ExpR leads.
- `docs/claude/backtest-methodology.md`: acceptance gate and windows.
