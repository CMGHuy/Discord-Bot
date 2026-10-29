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
