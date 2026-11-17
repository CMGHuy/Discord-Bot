# v229 pre-registration — Deferred-entry counterfactual on the live LONG book

**Spec:** `docs/superpowers/specs/2026-11-14-v229-deferred-entry-counterfactual-design.md`, last changed in `a9f73a62`.
**Plan:** `docs/superpowers/plans/2026-11-15-v229-deferred-entry-counterfactual_0-index.md`.
**Code:** `main` at `a708c61e` (V229-1..V229-11 merged, CI green). No edit under `scripts/reports/deferred_entry/` or to the CLI until the verdict is recorded.
**Driver:** `scripts/reports/deferred_entry_counterfactual.py` (modes `append`, `exploratory`, `verdict`); pair log `data/v229/pairs.jsonl` on the VM.
**Committed before any compute.** This document's first commit is the freeze; its commit timestamp is `T0`, recorded below in a follow-up commit. No ledger row is written now: the one row `v229-deferred-entry` is appended when the study closes (plan Handoff 2).

## Frozen constants

`verdict.FROZEN`, rule hash `8bbaaa9781535813` (sha256 of the sorted JSON, first 16 hex). Every pair row carries this hash; the verdict refuses a log carrying any other.

```json
{
  "be_fraction": 0.5,
  "calibration_min": 0.8,
  "defer_et": "15:30",
  "deferred_entry_bps_mult": 2,
  "floor_r": 0.1,
  "hold_sessions": 5,
  "lower_pct": 2.5,
  "min_pairs": 300,
  "min_weeks": 10,
  "resamples": 10000,
  "seed": 42,
  "window_weeks": 12
}
```

## The measurement (verbatim from the spec)

<!-- spec-quote-begin -->
## The question

For a LONG market plan the bot issued before 15:30 ET, would entering at 15:30
instead have produced a better result per alert?

## What changes

### 1. One script: `scripts/reports/deferred_entry_counterfactual.py`

Inputs: closed trades as `--rows <csv>`, the output of
`scripts/ops/export_book_rows.sh` (the one proven read path; no database mode is
added), and a 5-minute bars directory (`--bars-dir`, default
`market_data/5min`).

**Time basis.** The export writes `opened_at` and `closed_at` as UTC text. The
archive CSVs carry explicit UTC offsets and each bar is stamped with its
**start**; the script reads them itself with UTC parsing and does not go through
`data_store.load_normalized`, which drops the zone. 15:30 ET is derived per
entry date with `zoneinfo` (`America/New_York`) and converted to UTC, so it
moves with daylight saving. A test pins a date on each side of a DST change,
and a test on a real archive file pins the offset and the bar-start stamp.

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
| **B** defer if held | as A | no trade when any bar starting at or after `opened_at` and **strictly before** the 15:30 bar traded at or below the plan's original stop |

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

**Frictions.** Every arm's R is net, through the screen's
`net_r(entry, price, risk, direction=..., entry_bps=...)`
(`swingbot/core/backtesting/screen/sides.py`), which applies
`frictions.apply_frictions` once per fill and `commission_r()` once. The
control uses the default entry slippage; arms A and B pass
`entry_bps = 2 x SLIPPAGE_BPS`, because their fill is a market order in the
last half hour (the convention `range_breakdown_stop` used for a worse fill).
Frictions are applied in this one call and nowhere else. Zero frictions are refused. The gross figures are printed beside
the net ones and gate nothing.

**Statistic.** Per eligible plan, `d_A = R_A - R_C` and `d_B = R_B - R_C`. The
estimate is the mean per plan (ExpR per alert, skipped plans included at 0R).
Intervals come from the repo's `week_cluster_bootstrap`
(`swingbot/core/backtesting/instrument/stats.py`), called with
`baseline = R_C`, `component = R_A` (then `R_B`) and the mean-difference
statistic, clustered by the ISO week of `opened_at`, 10,000 resamples, seed
`WEEK_BOOTSTRAP_SEED`. The one-sided 97.5% lower bound is the 2.5th percentile
of the resampled statistic, and the one-sided `p` is the share of resamples at
or below zero: trades are held up to
five sessions, so pairs from neighbouring dates share bars and a date cluster
would understate the dependence. Two arms are read, so each uses a one-sided
97.5% lower bound (a Bonferroni split of the acceptance gate's 95%).

Every arm's line prints trades taken and total R beside ExpR. Arm B's lift is
partly built in (a plan stopped before 15:30 is about -1R in C and 0R skipped),
so `d_B` is also printed over the plans B actually took, as a disclosure.

**Calibration clause.** The simulator races to TP1 only, so its R cannot match
the live scale-out's R and a gap in means would say nothing. What must match is
the **path class**: stop first (`loss`), breakeven stop (`scratch`), or TP1
reached (any `tp1_*` leg live, `win` simulated). The script prints the 3 × 3
agreement table of simulated control against live outcome for the same trades.
When agreement is under 80% the output is stamped `UNCALIBRATED` and no verdict
is issued from it. Mean `R_C`, mean live `r_realized` and their rank
correlation are printed for information and gate nothing.

**Outputs.** One Markdown results doc and one JSON beside it: population funnel
(eligible, `no_coverage`, per-bucket counts), the three arms' N, win rate and
ExpR, both deltas with bounds, the calibration lines, per-week deltas, the
arm-B skip count with the control result of the skipped plans, and the bearish
disclosure.

**Tradeability record.** A deferred fill is a different trade from the plan's,
so each pair also records what a follow-on would need to judge it. All of it is
printed as disclosure and gates nothing:

- **Where the shifted levels land.** The deferred fill against the plan's entry
  in R; whether the shifted stop sits above the low of the day so far (inside
  the range already traded); `d_A` split by fill above or below the plan's
  entry. If arm A wins only where the stop moved up, that is a different
  strategy and the results doc says so.
- **Overnight exposure.** Per arm, the first overnight gap in R and the count
  of gap-through-stop fills. Arm A holds its first night almost at once; the
  control had most of a session first.
- **The 15:30 bar.** Its volume and range, and its open against the session's
  last 5-minute close, so a market-on-close fill can be compared later.
- **Was the plan still live at 15:30.** Price against the plan's entry, and
  whether the plan had already expired under its own rule.
- **Arm B's judgement.** The low of the day against the stop distance, and the
  15:30 price against the entry. The skip rule is a mechanical wick touch; a
  trader would judge "the level held" by a close or a reclaim. A close-based
  skip is a new idea, not a variant to add here.
- **Event days.** A flag for earnings after the close on the entry date
  (`swingbot/core/market/events.py`), for monthly OPEX and for FOMC days; the
  arms are printed with and without flagged plans.
- **Entry-bar stop-outs.** The count of live trades stopped inside their entry
  bar. The control cannot see these (it starts at the next bar), which flatters
  the control and so biases `d_A` downward on exactly the noise stops the
  hypothesis is about.

<!-- spec-quote-end -->

## The reads and the verdict (verbatim from the spec)

<!-- spec-quote-begin -->
### 3. Two reads, frozen before either

**Freeze.** The plan commits a pre-registration
(`docs/superpowers/results/<date>-v229-preregistration.md`) and a ledger row
`v229-deferred-entry` before the script reads production. Its commit timestamp
is `T0`.

**Exploratory read.** Eligible plans opened before `T0`, as far back as the
5-minute archive reaches (2026-06-23, which covers the live book). Run once. It is labelled exploratory,
issues no verdict and ships nothing; its only purpose is to check calibration.
Its window overlaps the data that motivated the idea, so it is not evidence.
**Nothing in the forward rule may change after it is read**: arms, deferral
time, race, thresholds, window length and cluster unit are those of this spec.
If the exploratory read is `UNCALIBRATED`, the forward read is not started and
the question closes inconclusive; the simulator is not tuned to pass.

**Forward read.** The population is fixed by **entry date**, not by when
trades happen to close: eligible plans with `opened_at` in the twelve complete
ISO weeks that follow `T0`. A weekly VM cron (`scripts/ops/`, per
`docs/claude/working-conventions.md` § Scheduling) appends new pairs to the log
and prints only the count. The verdict is computed **once**, after the window's
last plan has passed its five-session mark, so slow trades opened late are in
and same-day losers are not over-represented. The script refuses a verdict
before that date and refuses a second one after the ledger row carries a
verdict. The window, the thresholds and the floor below cannot be changed once
the first weekly count has been printed.

**Power, stated up front.** Twelve weeks at the current rate is roughly 800
LONG pairs in 12 week clusters. With the paired difference's standard deviation
near 1.5R and same-week correlation, the standard error is on the order of
0.08–0.10R, so the smallest lift this read can reliably detect is about
0.20–0.30R. The +0.10R floor below rarely binds; the lower bound is the real
gate. That is accepted: the live cell that motivates the read is a 0.7R
difference, and a lift too small to see here is too small to justify changing
when the partner places orders. Fewer than 300 forward LONG pairs or fewer than
10 week clusters at the verdict date is `UNDERPOWERED`, closed like a fail.

**Verdict rule, per arm.** `PASS` when the forward mean delta is at least
+0.10R, its one-sided 97.5% lower bound is above 0, and the forward run is
calibrated. Otherwise `NO-LIFT`. `UNCALIBRATED` closes the read as inconclusive.
The ledger row (`id, date, hypothesis, instrument, n, exp_r, p, verdict,
record, data_source`) carries a non-null `p`, the smaller arm's one-sided
bootstrap p doubled for the two arms, so `ledger_qvalues` can score it with the
other ideas; the session cell was picked from many slices.

- A `PASS` earns a spec for a deferred-entry mode. It ships nothing by itself.
  **Binding on that follow-on (partner, 2026-11-14):** this spec is
  `Edge: none (integrity)` only because it changes nothing live. A follow-on
  entry-mode spec carries `Edge: expectancy`, and its `Screen:` status needs the
  partner's explicit approval before the spec is written; this measurement is
  not a way around the idea screen.
- `NO-LIFT` or `UNCALIBRATED` closes the question in
  `docs/claude/backtest-methodology.md` § Closed pre-registrations. A different
  deferral time, a different skip rule or a different race is a new idea, not a
  retry.

<!-- spec-quote-end -->

## Where the code departs from the spec's wording (plan index § Handoff)

- **Ledger.** No row before the read: the ledger is append-only and refuses a duplicate id, so the freeze is this commit (v226 precedent) and exactly one row is appended at the close. Study words map to ledger tokens: PASS -> PASS, NO-LIFT -> NO-LIFT, UNDERPOWERED -> NO-LIFT, UNCALIBRATED -> INCONCLUSIVE; the study word is written into the row's hypothesis. Row verdict PASS when either arm passes; `p = min(1, 2 x the smaller one-sided p)`; `n` the forward LONG pairs; `exp_r` the mean delta of the arm with the smaller p; instrument `v1`.
- **Frictions.** `net_r(..., direction="long"|"short", days=...)`: longs pass `days=0`; the bearish disclosure passes calendar days held, as the screen does.
- **Live path class** comes from `last_leg_reason` (else `close_reason`): `tp1*` win, `scratch` scratch, `loss`/`stop` loss, anything else excluded and counted. The export carries only the last leg, so a TP1 partial whose runner was scratched classes as scratch.
- **Coverage.** Every NYSE session from the entry date to the fifth after it has a bar, and a bar starts at or after the horizon close minus 15 minutes; a half day on the entry date, or no bar in [15:30 ET, close), is `no_deferral_bar`. A forward trade whose horizon is past the archive's last bar is `pending` and recounted by the next run.
- **Forward window** is the twelve complete ISO weeks (Monday to Sunday) after T0's ET date; the verdict opens the day after the fifth NYSE session following the window's last session.
- **Not in the verdict population:** trades opened in the window and still open on the verdict date (the export joins closed journal entries only). Disclosed in the verdict doc.
- **T0 is an input** (`--t0`, baked into the cron line): the script cannot read its own freeze commit on the VM.

## Freeze

**T0:** 2026-11-17T18:43:37+00:00
**Forward window:** 2026-11-23 .. 2027-02-14 (entry dates, ET)
**Verdict opens:** 2027-02-23

T0 is the first commit of this document (`git log --diff-filter=A -1 --format=%cI -- docs/superpowers/results/2026-11-17-v229-preregistration.md` = `2026-11-17T19:43:37+01:00`), converted to UTC. Plans opened before T0's ET date are exploratory; the verdict is computed once, on or after the date above (Task V229-15).

## Weekly cron

Installed 2026-11-17T19:11:06Z on the VM root crontab by `scripts/ops/install_v229_cron.sh` (plan V229-14), marker `# v229 deferred-entry pairs`:

```
15 8 * * 6 /bin/bash /opt/swing-bot/scripts/ops/v229_pairs_cron.sh 2026-11-17T18:43:37+00:00
```

First count (runner run by hand at install): `v229 pairs: appended 0, total 392, forward 0`. From this count on, the window, the thresholds and the floor are locked. The log is `/opt/swing-bot/logs/v229-pairs.log`; Task V229-15 removes the entry after the verdict.
