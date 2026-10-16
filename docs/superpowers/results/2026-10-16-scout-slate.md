# Scout slate 2026-10-16

**Autopsy:** `E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/2026-10-16-book-autopsy.json`
**Window:** 2026-07-20 to 2026-10-15 · **N:** 732 · **Cells tested:** 351 · **Net of frictions:** modelled

> Every autopsy-derived row is exploratory, and the holdout is protected: the live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, scripts/backtest/measure_v104.py). A row picked from this slate and sent to /prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows that end before the autopsy window starts, and its pre-registration records that the holdout is contaminated for that idea (never spent as confirmation). A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap).

A slate row is a hypothesis. No gate moves: it never edits code, config, thresholds or live alerts, and never licenses a re-run of a closed pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` row before its spec.

## Ranked

### 1. evening-alert-premarket-refresh (regime-desk)

- claim: Test a premarket refresh of evening alerts to improve the ability to act on qualified plans before the next session.
- evidence: cell alert_hour=20; N 434; weeks 12; Δ net ExpR +0.374 [0.162, 0.996]; q 0.007
- exploratory: yes
- edge: harvest
- mechanism: Evening issuance leaves time to prepare resting orders; a premarket refresh could make still-valid plans easier to execute without continuous monitoring. The timing association supports investigation, but does not establish that reminders improve outcomes.
- order_form: stop-buy / limit at the published entry, subject to the original validity and expiry
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /prereg

### 2. gap-and-hold (setup-scout)

- claim: Screen a continuation entry after a gap remains unfilled through the close, testing whether confirmed acceptance adds profitable setups.
- evidence: playbook gap-and-hold
- exploratory: yes
- edge: volume
- mechanism: An unfilled gap with a close near the session high may indicate sustained demand; entry requires a subsequent break above that session's high. Waiting for the gap day's completed close distinguishes this mechanism from the failed gap-day volume screen.
- order_form: stop-buy above the completed gap day's high, valid next session only.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen gap-and-hold

### 3. rs-leader-index-pullback (setup-scout)

- claim: Screen a new entry that buys a relative-strength leader after it holds its prior low during an index pullback, testing whether this adds profitable setups.
- evidence: playbook rs-leader-index-pullback
- exploratory: yes
- edge: volume
- mechanism: Holding support while the index retreats may reveal persistent demand; a subsequent break above the pullback bar supplies an entry trigger. This tests index-relative resilience as a setup, distinct from the existing RS gate and own-RSI pullback.
- order_form: stop-buy above the pullback day's high, valid next session only.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen rs-leader-index-pullback

### 4. three-bar-weekly-reversal (setup-scout)

- claim: Screen a daily reversal pattern at support drawn from completed weekly bars, testing whether this adds profitable setups absent from the strategy registry.
- evidence: playbook three-bar-weekly-reversal
- exploratory: yes
- edge: volume
- mechanism: A completed reversal at a previously known weekly support level may identify renewed demand with a defined invalidation point. The mechanism requires weekly support plus the daily reversal sequence, distinct from double patterns and Fibonacci confirmation.
- order_form: stop-buy above the final reversal bar's high, valid next session only.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen three-bar-weekly-reversal

## Dropped

None.

## Generator results

- exit-harvester: NO ROWS. Eligible positive exit cells describe realised outcomes rather than a testable change; alternatives are thin or miss the evidence gate.
- setup-scout: 3 rows returned.
- regime-desk: 1 row returned.
