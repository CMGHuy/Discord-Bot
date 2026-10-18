# v175 — Normal bad luck: showing when a losing run is within the book's past range

**Version:** ui 1.27.0 · bot 2.10.0 (at writing)
**Bump:** bot minor — a new book-status message posts when the book's losing-run zone changes, and a new API endpoint serves the band; ui minor — the Analytics Overview tab gains a "Normal bad luck" panel.
**Edge:** none (integrity) — framing only. It changes no signal, gate, stop, size or badge. Any benefit is behavioural (not abandoning a working system mid-run) and is not claimed.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, financial-advisor, veteran-trader
**Status:** spec written 2026-10-18 from a brainstorm with the partner (panel plus an alert-side note, thresholds and placement approved in chat); revised the same day after the panel. The unit became the close day, and the per-plan alert line became a zone-change message (see `## Panel review`).

## Why

Douglas (*Trading in the Zone*) argues that the trader with an edge fails
when a losing run, which is normal for that edge, is read as proof that the
edge is gone. The reverse is also a failure: calling a broken system "just
variance".

Every alert already shows its setup's pedigree: N, win rate and ExpR via
`badge_stats_line` (`scanning/plan_table.py:43`), plus the v86 cohort
lines. Nothing tells the trader how long or deep a losing run **this book's
own past produces by chance**, or whether the current run is inside that
range.

## Goals

- G1. A pure band computation over the closed book. **Close days** are the
  unit, and **week blocks** are the resampling unit. It gives the range of
  losing-day runs and drawdowns over the next 20 and 50 close days, and
  where the book sits now on the same statistic.
- G2. A "Normal bad luck" panel on Analytics → Overview.
- G3. One short book-status message in the alert channel **when the zone
  changes** into rough or outside. Plan alerts stay exactly as v170 left
  them.

## Non-goals

- No instruction to the trader. Copy describes; it has no verbs like stop,
  check, skip, size or review.
- No unrealised P&L. The band covers **closed trades only**, and says so.
  Including open positions is a separate scope decision.
- No change to plan embeds, the throttle or the kill switch
  (`edge/throttle.py`).
- No per-strategy or per-horizon bands. The band is book-wide, labelled
  "whole book", and does not follow the Analytics scope bar.
- No change to `metrics.streaks` (`metrics.py:315-350`), which stays the
  trade-status streak. This spec's statistic is named differently
  ("losing days in a row") so the two are never confused.
- No Dashboard placement. v172 is reshaping the Dashboard's equity chart.

## Design

### 1. Core — `swingbot/core/analytics/variance_band.py`

Pure functions, no I/O.

**Input:** every closed plan with a computable R (`metrics.r_multiple`,
the single R definition, skipped when `None` as in `metrics.r_multiples`)
and its close date.

- **Close-day series:** the R values are summed per NYSE close date, in
  date order.
  - A day with net R < −`SCRATCH_R` is a **loss day**.
  - A day with net R > +`SCRATCH_R` is a **win day**.
  - Anything else is a **scratch day**.
  - One gap day that stops out five positions is therefore one loss day,
    not five losses.
- **Era:** if the plan doc carries an exit-model era marker (the
  plan-briefer names the field), the pool is restricted to the current era
  once that era alone has at least `MIN_DAYS` close days; until then it
  uses the whole book. Either way the band reports its composition: close
  days per era and trades per horizon.

**Frozen constants:**

| Constant | Value | Meaning |
|---|---|---|
| `MIN_DAYS` | 100 | Close days needed, else `insufficient` |
| `MIN_WEEKS` | 20 | Distinct ISO weeks needed, else `insufficient` |
| `HORIZONS` | (20, 50) | Simulated run lengths, in close days |
| `PATHS` | 10 000 | Bootstrap paths per horizon |
| `SEED` | `WEEK_BOOTSTRAP_SEED` (`instrument/stats.py`) | Reproducible bands |
| `SCRATCH_R` | 0.05 | \|net day R\| ≤ this is a scratch day |
| `ROUGH_PCT`, `OUTSIDE_PCT` | 80, 95 | Zone cut-offs |

**Losing run:** consecutive loss days. A scratch day neither extends nor
breaks it, and a win day ends it. The bootstrap and the current state use
this same rule.

**Drawdown:** the gap from the running peak of the cumulative close-day R,
in R.

**Bootstrap, week blocks:**
- Each path concatenates whole ISO weeks of close days, drawn with
  replacement, until it holds `h` close days; the last week is truncated.
  Correlated same-week losses stay together, the repo's week-cluster
  convention.
- Per horizon the band records the longest losing run and the maximum
  drawdown within the path, and reports p80 and p95 of each.
- The band also reports its own uncertainty: p95's 10–90% range across 200
  outer resamples of the week set, shown as "p95 ≈ 7 (6–8)".

**Current state, same statistic as the band:**
- `current_run`: the losing run in progress at the latest close day.
- `current_drawdown`: the drawdown **within the last 50 close days**,
  peak-to-now inside that window. This matches the 50-day band's statistic
  rather than an all-time drawdown that keeps growing with the book's age.
- Also: the run's and the drawdown's age in calendar days.
- Each is placed against the 50-day band:

| Zone | Condition | Panel copy |
|---|---|---|
| `normal` | ≤ p80 | "Within the range this book's past trades produce" |
| `rough` | > p80 and ≤ p95 | "Deeper than 80% of simulated runs, within 95%" |
| `outside` | > p95 | "Beyond 95% of simulated runs" |

- **Ties:** when p80 == p95 (integer runs), the `rough` zone is empty and
  the copy skips it. A test covers this.
- **ExpR beside the band:** the band always carries the closed book's ExpR
  with N and window, re-derived on every call (`pooled-numbers`), and its
  week-cluster interval (`week_cluster_bootstrap`). If that ExpR is ≤ 0,
  or its interval includes 0, every zone's copy adds: "This book's past
  results are not positive. A run within their range is still a losing
  run." The word "edge" never appears.
- **Look rate, stated honestly:** p95 is a per-look rate. The panel
  recomputes on every view and the message on every scan, so over months
  `outside` fires by chance more often than 5%. The panel caption says so
  (§3). The calibration test (§ Testing) measures the per-look rate.

**Dollars:** a drawdown in dollars is shown as **≈ $X**, computed as R ×
the book's median per-trade dollar risk. The plan-briefer names the stored
field v170's alerts read. If it's missing, the figure is omitted, not shown
as "—". The panel says how it is derived. All figures come from the paper
book and are pre-tax.

`variance_band(closed) -> Band` returns either `{status: "insufficient",
days, weeks}` or the full band.

### 2. API

`GET /api/v1/analytics/variance-band` is computed on request, behind
`require_auth`, and returns the `Band`. Its scope is the whole closed book,
and the response carries `scope: "whole_book"`.

### 3. Panel "Normal bad luck"

The panel goes on `analytics/tabs/overview.ts` and uses the tab's existing
`Panel`/`PanelHeader`/`PanelError` pieces. It is **not interactive**:
nothing on it is tappable except the panel's standard retry.

- **Header:** "Whole book, closed trades only. Filters don't apply."
- **Two band bars:**
  - Losing days in a row.
  - Drawdown over the last 50 close days, in R with ≈ $ beside it.
  - Each bar has three labelled segments (normal / rough / outside) with
    the p80 and p95 values as text, not colour alone, and a "you are here"
    marker with a text equivalent ("now: 4 days, 9 calendar days long").
  - The zone copy sits under each bar and wraps without truncation.
  - The 20-day p95 is on a secondary line. Both horizons also show an
    approximate span ("50 close days ≈ 13 weeks at this book's pace").
- **ExpR line:** "Book: ExpR {+0.21R} over N={n} trades ({window})". The
  not-positive caveat appears when it applies.
- **Composition line:** close days per era, trades per horizon.
- **Caption:** "Simulated from this book's closed trades, resampled by
  week. It shows the range of losing runs these past results produce by
  chance; it is not a forecast. Checked continuously, so 'beyond 95%'
  will sometimes appear by chance alone. Paper book, before tax."
- **`insufficient`:** "Needs 100 close days over 20 weeks ({d} days, {w}
  weeks so far)."
- **Layout:** the bars stack on phones, with no horizontal scroll and all
  values as text. Checked at mobile, tablet and desktop widths with
  Playwright (`ui-design.md`).

### 4. Book-status message (zone change only)

Once per scan cycle the bot computes the band, cached for that cycle, and
compares the worse of the two zones (run, drawdown) with the last zone it
posted. That last zone is persisted in a small state record (the
plan-briefer picks the existing store, e.g. the bot state used by the
throttle). A message posts **only when the zone rises** into `rough` or
`outside`.

| Transition | Message (one line, its own message, not on a plan) |
|---|---|
| → rough | `📉 Book: {k} losing days in a row / {dd}R (≈ ${x}) down over 50 close days, deeper than 80% of simulated runs, within 95%. Closed trades only.` |
| → outside | `📉 Book: {k} losing days in a row / {dd}R (≈ ${x}) down over 50 close days, beyond 95% of simulated runs. Closed trades only.` |

- A fall back to a lower zone posts nothing and resets the stored zone. The
  next rise posts again.
- The ExpR-not-positive caveat is appended when it applies.
- Each trade is still sized by the existing rules. The message carries no
  sizing language and no verb.
- The message is a new presentation kind in its own family
  (`presentation/kinds.py`), with no outcome mark, following the
  `alert-surface` skill. Plan embeds are untouched, so no plan field can be
  displaced or truncated.
- An `insufficient` band posts nothing.

## Testing

- Close days:
  - Five losses on one date are one loss day.
  - Mixed R on one date nets out.
  - A scratch day neither breaks nor extends a run.
  - A win day ends it.
  - A trade with no computable R is skipped.
- Drawdown:
  - The 50-day window drawdown is measured from that window's peak.
  - An older, deeper all-time drawdown outside the window does not count.
- Bootstrap:
  - Week blocks stay intact, and paths are truncated to `h`.
  - The seed makes runs reproducible.
  - An all-win book gives a p95 run of 0.
  - p80 == p95 skips the rough zone.
- **Calibration:** simulate i.i.d. and week-correlated books of known
  length. The measured per-look `outside` rate for the compared statistic
  sits near 5% for the 50-day drawdown and at or below 5% for the run.
  The test records the measured rates, and the panel caption's wording
  rests on them.
- Thresholds:
  - 99 close days or 19 weeks → `insufficient`.
  - Zone boundaries exactly at p80 and p95.
- ExpR caveat: present when ExpR ≤ 0 or its interval includes 0, absent
  otherwise. No copy contains "edge".
- Message:
  - Posts on normal→rough, rough→outside and normal→outside.
  - Silent on a repeat of the same zone and on a fall.
  - Posts again after a fall then a rise.
  - Never posts while `insufficient`.
  - No plan embed changes (the existing embed tests still pass unchanged).
- API shape test: `scope: "whole_book"`, and dollars omitted when the field
  is missing.
- Frontend spec: each zone's copy, the tie case, the caveat, the
  insufficient state, the text equivalents and the stacked phone layout.

Every test uses fixture data and never the database, including the local
production replica. Any pooled figure a plan or results doc quotes is
re-derived from the live production book with its N, window and source
(`pooled-numbers`). A replica is a snapshot, not the live book.

## Risks

- **A book's R distribution drifts** (new strategies, a new exit model).
  The era restriction and the composition line contain it but don't
  remove it.
- **Closed trades only.** On a gap day with open positions underwater, the
  band lags until they close. The header and the message say "closed
  trades only".
- **By-chance `outside`.** Continuous looking makes it appear by chance
  over months. The caption says so, and the message fires only on a zone
  change, not on every scan.

## Panel review

2026-10-18. The three roles ran serially on commit `170c71eb`.

- financial-advisor [BLOCKING]: "normal for this edge" asserts an edge and
  reassures a losing book -- applied: the copy describes "the range this
  book's past trades produce", ExpR is always shown, and a not-positive
  caveat is added; "edge" is never used.
- financial-advisor [BLOCKING]: "check the system" / "See Analytics" are
  instructions -- applied: verb-free copy ("beyond 95% of simulated runs").
- quant-researcher: the current drawdown (all-time) was not the band's
  statistic -- applied: a 50-close-day window drawdown, matching the band.
- quant-researcher: multiple looks -- applied: a caption sentence and a
  zone-change-only message.
- quant-researcher + veteran-trader: i.i.d. trades ignore correlated
  stop-outs -- applied: close-day netting plus a week-block bootstrap.
- quant-researcher: mixed eras -- applied: a current-era restriction once
  it reaches the floor, plus a composition line.
- quant-researcher: an extreme quantile from a small pool, and the p80 ==
  p95 tie -- applied: the floor raised to 100 close days / 20 weeks, the
  band's own uncertainty shown, and a tie test.
- quant-researcher: reversed quantile copy -- applied: "deeper than 80% …
  within 95%" and "beyond 95%".
- quant-researcher: two streak definitions -- applied: named "losing days
  in a row", with `metrics.streaks` unchanged and stated.
- quant-researcher: no calibration test -- applied.
- quant-researcher: dev-DB wording after the replica rule -- applied:
  fixtures only, never the database or the replica, and pooled figures
  from the live book.
- quant-researcher: dollar approximation belongs to other seats --
  handled under financial-advisor below.
- financial-advisor + veteran-trader: a streak line on a fresh plan nudges
  (gambler's fallacy, "this one is shaky") and repeats into noise --
  applied: no plan-embed line; a separate message only on a zone rise, and
  the plain 3-loss trigger dropped.
- financial-advisor: approximate dollars, pre-tax, paper -- applied: "≈ $",
  the derivation shown, omitted when the field is missing, and "paper
  book, before tax".
- financial-advisor + veteran-trader: horizons in trades mean nothing in
  time -- applied: close days, an approximate span in weeks, and the
  run's and drawdown's age in calendar days.
- financial-advisor: whole-book scope and the reassurance asymmetry --
  applied: a "Whole book … filters don't apply" header. The asymmetry is
  intended: only a rise into rough or outside posts.
- financial-advisor: mobile text equivalents, wrapping and touch targets --
  applied: text labels and values, no truncation, and the panel declared
  non-interactive.
- veteran-trader: unrealised drawdown ignored -- applied as scope: "closed
  trades only" in the copy. Unrealised P&L is a Non-goal for a later
  decision.
- veteran-trader: the line could displace plan fields -- applied: plan
  embeds are untouched, and a test asserts the existing embed tests pass
  unchanged.
