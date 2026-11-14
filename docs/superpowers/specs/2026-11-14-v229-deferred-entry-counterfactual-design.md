# v229 — Deferred-entry counterfactual: do late-session entries beat early ones?

**Version:** ui 1.43.0 · bot 2.18.7
**Bump:** none (a measurement: one report script, a pair log and a VM cron; nothing the bot posts, trades or shows changes)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-researcher, veteran-trader, quant-engineer

## Why

On the production LONG book since 2026-10-01
(`docs/superpowers/results/2026-11-14-long-book-read.md`), trades entered in the
`close` session bucket (15:30 ET onward) made +0.672R on N=35, against -0.043R
at the `open` (N=178) and -0.006R `midday` (N=150). 54% of longs close the day
they open, at -0.382R. Stops sit near 0.35 ATR, so a market entry early in the
session has the whole day's noise to survive.

The cell is small and picked from many slices, so it is a lead, not evidence.
Two things stop the usual route:

- **The idea screen cannot see it.** Stage -2 races daily bars; the session a
  plan was issued in does not exist there.
- **Intraday history is short.** The VM's 5-minute archive holds 60 days. A
  replay over a longer window would need hourly bars from December 2023, all of
  it inside the VALIDATION and holdout windows.

So this spec measures the question on the bot's **own live plans**, twice: an
exploratory read on plans already closed, then a forward confirmation on plans
issued after the rule is frozen. The live book is exploratory by rule; no
TRAIN, VALIDATION or holdout replay is read, and no budget is spent.

The hypothesis overlaps v212 (limit entry under the support): both attack noise
stop-outs. They differ in mechanism (wait for time, versus wait for price), and
this spec changes nothing live, so the two do not interfere.

## The question

For a LONG market plan the bot issued before 15:30 ET, would entering at 15:30
instead have produced a better result per alert?

## What changes

### 1. One script: `scripts/reports/deferred_entry_counterfactual.py`

Inputs: closed trades (`--rows <csv>` from `scripts/ops/export_book_rows.sh`, or
`--from-db` read-only inside the bot container) and a 5-minute bars directory
(`--bars-dir`, default `market_data/5min`).

**Population.** A trade is eligible when all hold:

- `direction` is `bullish` (bearish pairs are computed and printed as a
  disclosure; they never enter the verdict);
- `entry_type` is `market`;
- `opened_at` falls in a regular NYSE session and before 15:30 ET
  (`session_bucket` is `open` or `midday`);
- 5-minute bars cover from `opened_at` to the end of the fifth session after
  it. A trade without coverage is counted as `no_coverage` and left out.

Tickers without a regular-session 5-minute bar on the entry date (metals, FX,
crypto) fail the coverage clause and drop out by construction.

**Three simulated arms, one simulator.** Every arm is raced by the same
function on the same 5-minute bars, so simulator error cancels in the pair:

| Arm | Fill | Skip rule |
|---|---|---|
| **C** control | the trade's own `entry`, from the first bar starting at or after `opened_at` | never |
| **A** defer | open of the first bar starting at or after 15:30 ET on the entry date | never |
| **B** defer if held | as A | no trade when any bar between `opened_at` and 15:30 traded at or below the plan's original stop |

For A and B the stop keeps its **distance** (`fill - (entry - stop_loss)`) and
TP1 keeps its **distance** (`fill + (take_profit - entry)`), so risk and reward
in R are the plan's own.

**Race rule (frozen simplification).** Single leg to TP1, the round-1 rule of
`swingbot/core/planning/exit_sim.py:_single_leg_exit_walk` applied to 5-minute
bars: stop checked before target within a bar; the stop moves to the fill once
price reaches `BREAKEVEN_TRIGGER_FRACTION` of the TP1 distance and protects
later bars only; win = +TP1 distance in R, loss = -1R, scratch = 0R; a trade
still open at the end of the fifth session after entry is marked to that bar's
close. A skipped arm-B plan scores 0R. No runner, no TP2: the live scale-out is
not reproduced, and that is disclosed in every output.

**Statistic.** Per eligible plan, `d_A = R_A - R_C` and `d_B = R_B - R_C`. The
estimate is the mean per plan (ExpR per alert, skipped plans included at 0R).
Intervals come from a bootstrap clustered by entry date, 10,000 resamples, seed
fixed in the script. Two arms are read, so each uses a one-sided 97.5% lower
bound.

**Calibration clause.** The script also prints mean `R_C` beside the mean live
`r_realized` of the same trades, and their rank correlation. When the absolute
difference of means exceeds 0.25R or the correlation is under 0.6, the output
is stamped `UNCALIBRATED` and no verdict is issued from it.

**Outputs.** One Markdown results doc and one JSON beside it: population funnel
(eligible, `no_coverage`, per-bucket counts), the three arms' N, win rate and
ExpR, both deltas with bounds, the calibration lines, per-week deltas, the
arm-B skip count with the control result of the skipped plans, and the bearish
disclosure.

### 2. The pair log

5-minute bars expire after 60 days, so pairs are persisted as they are computed:
`data/v229/pairs.jsonl`, one row per eligible plan (trade id, entry date, the
three arm results, coverage flags), appended once per trade id and never
rewritten. A re-run skips trade ids already present. The file is registered as
a data file per the `DATA_READERS` convention.

### 3. Two reads, frozen before either

**Freeze.** The plan commits a pre-registration
(`docs/superpowers/results/<date>-v229-preregistration.md`) and a ledger row
`v229-deferred-entry` before the script reads production. Its commit timestamp
is `T0`.

**Exploratory read.** Eligible plans opened before `T0`, as far back as the
5-minute archive reaches (about 60 days). Run once. It is labelled exploratory,
issues no verdict and ships nothing; its purpose is to check calibration and
give the forward read a prior.

**Forward read.** Eligible plans opened at or after `T0`. A weekly VM cron
(`scripts/ops/`, per `docs/claude/working-conventions.md` § Scheduling)
appends new pairs to the log and prints only the count. The verdict is computed
**once**, the first time the forward log holds N ≥ 300 LONG pairs (about five
weeks at the current rate); the script refuses a verdict below N and refuses a
second one after the ledger row carries a verdict.

**Verdict rule, per arm.** `PASS` when the forward mean delta is at least
+0.10R, its one-sided 97.5% lower bound is above 0, and the forward run is
calibrated. Otherwise `NO-LIFT`. `UNCALIBRATED` closes the read as inconclusive.

- A `PASS` earns a spec for a deferred-entry mode. It ships nothing by itself.
- `NO-LIFT` or `UNCALIBRATED` closes the question in
  `docs/claude/backtest-methodology.md` § Closed pre-registrations. A different
  deferral time, a different skip rule or a different race is a new idea, not a
  retry.

## What does not change

- No alert, plan, order form or lifecycle message. The partner's resting orders
  are untouched.
- No replay, backtest or screen code, and no VALIDATION or holdout window.
- Nothing in the bot process: the cron runs the report script only.

## Edge cases

- **Half days.** The deferral time is 15:30 ET; on a 13:00 close there is no
  such bar, the plan fails coverage for arms A and B, and it is counted
  `no_deferral_bar` and left out of all three arms.
- **Entry bar.** The control starts at the first bar that begins at or after
  `opened_at`, so the bar containing the entry is not raced. A stop-out inside
  that bar is therefore missed by the control; the calibration clause is what
  bounds this.
- **Trade opened after 15:30.** Not eligible (already a late entry); printed as
  the `close` bucket's own live result for context.
- **Arm B, stop touched in the entry bar.** The entry bar is excluded from the
  held check, consistent with the control.
- **Same ticker, several plans in a day.** Each plan is its own pair; the
  date-clustered bootstrap carries the dependence.
- **Empty forward log** (bot paused, holiday week): the cron prints 0 and exits
  0.

## Testing

- Simulator: stop before target in one bar; breakeven move protecting later
  bars only; five-session mark; gap through the stop at a session open.
- Arms: distance-preserving stop and TP1; arm-B skip on a touch and no skip
  without one; half-day exclusion; no-coverage exclusion.
- Pair log: append-once per trade id, restart skips, malformed row refused.
- Verdict guard: refuses below N, refuses a second verdict, `UNCALIBRATED`
  path.
- Bootstrap: deterministic under the fixed seed; single-date book returns no
  interval rather than a zero-width one.
- Empty inputs: no trades, no bars.

## Open questions for the panel

- Whether single-leg-to-TP1 is an acceptable stand-in for the live scale-out in
  a paired design, or whether the calibration thresholds (0.25R, 0.6) need to
  be tighter.
- Whether a `PASS` could ever be confirmed out of sample beyond the forward
  read, given the funnel replays daily bars; the follow-on spec would have to
  name its gate.
- For the partner's real orders: a deferred entry means placing the order near
  the close, which changes the day's routine. Out of scope here, in scope for
  any follow-on.
