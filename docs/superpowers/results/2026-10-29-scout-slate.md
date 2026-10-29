# Scout slate 2026-10-29

**Autopsy:** `docs/superpowers/results/2026-10-29-book-autopsy.json`
**Window:** 2026-07-20 to 2026-10-29 · **N:** 828 · **Cells tested:** 368 · **Net of frictions:** modelled

> Every autopsy-derived row is exploratory, and the holdout is protected: the live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, scripts/backtest/measure_v104.py). A row picked from this slate and sent to /prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows that end before the autopsy window starts, and its pre-registration records that the holdout is contaminated for that idea (never spent as confirmation). A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap).

A slate row is a hypothesis. No gate moves: it never edits code, config, thresholds or live alerts, and never licenses a re-run of a closed pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` row before its spec.

## Ranked

### 1. weekend-hold-survivor-screen (regime-desk)

- claim: Test whether a deliberate weekend carry, meaning no forced Friday flatten and Friday-issued plans left to run, explains the positive net ExpR of weekend-spanning trades, or whether the cell is only survivorship.
- evidence: cell weekend_hold=yes; N 72; weeks 14; Δ net ExpR +0.630 [0.109, 1.219]; q 0.042
- exploratory: yes
- edge: expectancy
- mechanism: Weekend-spanning trades may keep their winners through the Monday open, where the 2-day weekend gap compounds the move. The cell is defined by the exit date, so it may only reflect trades that had not been stopped by Friday. The screen has to condition on what was known at entry, for example Friday-issued plans (friday_entry=yes shows no edge on its own: Δ +0.108 [-0.166, 0.481], q 0.667, cell friday_entry=yes), before any claim is made.
- order_form: unchanged stop-buy or limit entry, validity unchanged; the test varies only whether the position is carried across Friday close
- manual_actions: none
- pairs_with: n/a (the test changes no entry filter, so no volume is removed)
- divergence: no
- route: /screen weekend-hold-survivor-screen

### 2. after-close-alerts-resting-order-only (regime-desk)

- claim: Treat the after-close alert (hour 20) as the only entry-eligible timing, and route premarket and regular-session alerts to a next-session resting order instead of an immediate entry, to lift net ExpR.
- evidence: cell alert_hour=20; N 518; weeks 14; Δ net ExpR +0.362 [0.034, 0.936]; q 0.083
- exploratory: yes
- edge: expectancy
- mechanism: An after-close alert gives a trader who is not watching time to rest the order before the open, and the plan is built on a completed daily bar. Alerts at other hours are issued against a bar that is still forming, or at a price that has already moved.
- order_form: stop-buy or limit resting order placed after the alert, valid for the next regular session only
- manual_actions: none
- pairs_with: premarket and regular-session alerts are re-timed to the next after-close scan, not dropped, so volume returns one session later (tallies: alert_hour_session=regular 83, premarket 38, after_close 613; actionable_before_open=no 83)
- divergence: no
- route: /screen after-close-alerts-resting-order-only

### 3. atr-reentry-after-stop (setup-scout)

- claim: Re-arm the original setup once, within a small fixed bar window, after a stop-out, because the stop cell is the largest loss bucket and some stops are noise.
- evidence: playbook atr-reentry-after-stop
- exploratory: yes
- edge: expectancy
- mechanism: Stops are tight (0.38 ATR median in cell exit_reason=stop, N 184, weeks 13) and a quick return through the entry trigger shows the stop was a wick. A single re-entry at the original ATR multiple recovers some of those. Caveat: it can stack losses in one name if the setup is truly broken, so cap it at one re-entry.
- order_form: stop-buy at the original trigger, valid for a fixed re-arm window; stop re-placed at the original ATR multiple
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen atr-reentry-after-stop

### 4. tight-base-breakout (setup-scout)

- claim: Add a narrow multi-week range breakout on above-average volume as an entry the registry lacks, to bring new volume rather than filter the existing book.
- evidence: playbook tight-base-breakout
- exploratory: yes
- edge: volume
- mechanism: Contracting ranges store energy and a volume break out of the base marks a trend start with a close stop under the base low. Alerts are concentrated after the close (alert_hour_session=after_close: 613), so a stop-buy form suits that timing.
- order_form: stop-buy above the base high, valid for a fixed number of sessions; stop under the base low
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen tight-base-breakout

## Dropped

| Idea | Role | Reason |
|---|---|---|
| pre-close-exit-on-gap-risk | exit-harvester | cell gap_through_stop=through_stop Δ lower bound -1.115 is at or below zero or unavailable |
| stop-fill-overshoot-audit | exit-harvester | cell exit_reason=stop Δ lower bound -2.032 is at or below zero or unavailable |
| bank-partial-on-favourable-open-gap | exit-harvester | cell open_gap_bucket=favourable Δ lower bound -1.175 is at or below zero or unavailable |
| no-chase-favourable-gap-limit | setup-scout | cell open_gap_bucket=favourable Δ lower bound -1.175 is at or below zero or unavailable |

## Panel review

Run 2026-10-29 over `bf8e6b37` (quant-researcher on opus). No BLOCKING findings.

- quant-researcher [ADVISORY]: `alert_hour=20` is a timestamp artefact. `_alert_hour` (`scripts/reports/autopsy/rows.py:125-132`) takes a date-only `plan_first_status_at` as 00:00 UTC, which is 20:00 EDT. Controller check: in the export, 521 trade rows carry a 10-character date-only value, 74 carry a full timestamp and 236 are empty. The cell's own net ExpR is -0.051, its q 0.083 -- **applied**: Rank 2 withdrawn. The `after_close 613` tally is inflated by the same artefact. Fix owner: quant-engineer.
- quant-researcher [ADVISORY]: `weekend_hold=yes` is survivorship. The cut (`scripts/reports/autopsy/cuts.py:68-73`) is exit-defined. 749 of the 756 non-weekend trades lasted under 3 calendar days, and the entry-time cut `friday_entry=yes` shows nothing (Δ +0.108, q 0.667) -- **applied**: Rank 1 withdrawn.
- quant-researcher [ADVISORY]: no forced Friday flatten exists in code, and a daily-bar /screen cannot test a carry policy or intraday alert timing -- recorded; moot after the withdrawals.
- quant-researcher [ADVISORY]: both scouts misread the `open_gap_bucket=favourable` sign again (`scripts/reports/autopsy/bars.py:129-133`; 2026-10-21 panel, 2nd bullet). The drops stand, for the wrong reason, and the contrast counts once -- recorded. The playbook and role prompts still carry no sign note: quant-engineer.
- quant-researcher [ADVISORY]: the merge's one-sided rule (`scripts/dev/scout_merge.py:294-298`) can never rank a row that reduces a losing cell, and it ignores q -- recorded as the partner's call.
- quant-researcher [ADVISORY]: the 32 trades closed in the 2026-08-04/05 stop-monitor stall batches (18 below -1.05R gross, worst -6.03R) still feed the stop cells -- recorded; exclusion owner: quant-engineer.
- quant-researcher [ADVISORY]: there is no exit-model era split (exit changes 2026-09-03/09/10), unlike the 10-21 slate -- recorded.
- quant-researcher [ADVISORY]: Rank 3 (atr-reentry-after-stop) borders the closed v108 E re-arm and the v114/v139 stop-geometry work (`docs/claude/backtest-methodology.md:260-261,288`). A /screen must freeze a distinct trigger with unchanged stop width, and the edge is probably `volume` as well -- recorded as a condition on that route.
- quant-researcher [ADVISORY]: Rank 4 (tight-base-breakout) borders `range_breakdown_close` SCREEN-FAIL, `high52w` SCREEN-FAIL and v105 NO-LIFT (`backtest-methodology.md:266,309,323`). Controller note: Support/Resistance already carries a tight-base breakout (`docs/strategy-types/support-resistance.md:21`, WEAK). It was picked for /screen on 2026-10-16 and never screened -- recorded as a condition on that route.
- quant-researcher [ADVISORY]: uncertainty comes from 14 week-clusters with lopsided complements, and thin complements should be reported as thin -- recorded.
