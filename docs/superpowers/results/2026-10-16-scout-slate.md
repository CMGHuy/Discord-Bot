# Scout slate 2026-10-16

**Autopsy:** `E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/2026-10-16-book-autopsy.json`
**Window:** 2026-07-20 to 2026-10-15 · **N:** 732 · **Cells tested:** 351 · **Net of frictions:** modelled

> Every autopsy-derived row is exploratory, and the holdout is protected: the live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, scripts/backtest/measure_v104.py). A row picked from this slate and sent to /prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows that end before the autopsy window starts, and its pre-registration records that the holdout is contaminated for that idea (never spent as confirmation). A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap).

A slate row is a hypothesis. No gate moves: it never edits code, config, thresholds or live alerts, and never licenses a re-run of a closed pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` row before its spec.

## Ranked

### 1. evening-resting-order-preparation (regime-desk)

- claim: Test an additional evening preparation pass for still-valid setups to increase next-session opportunities that traders can prepare before the open.
- evidence: cell alert_hour=20; N 434; weeks 12; Δ net ExpR +0.374 [0.162, 0.996]; q 0.007
- exploratory: yes
- edge: volume
- mechanism: Evening preparation may give traders time to place conditional orders before the next session. The association in the 2026-07-20 to 2026-10-15 window does not establish that changing issuance time improves outcomes.
- order_form: stop-buy for bullish setups or corresponding sell-stop for bearish setups; valid for the next regular session, subject to plan invalidation.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen evening-resting-order-preparation

### 2. gap-and-hold (setup-scout)

- claim: Screen a continuation entry after an unfilled gap holds through the close to test whether confirmed acceptance adds profitable opportunities.
- evidence: playbook gap-and-hold
- exploratory: yes
- edge: volume
- mechanism: A close above the prior session's high with the gap intact may show sustained demand. Entry requires a subsequent break above the completed gap bar; this differs from the failed gap-day volume-filter idea.
- order_form: stop-buy above the gap bar's high, valid the next session.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen gap-and-hold

### 3. three-bar-weekly-reversal (setup-scout)

- claim: Screen a completed three-bar daily reversal at a previously established weekly level to test whether it adds profitable reversal entries.
- evidence: playbook three-bar-weekly-reversal
- exploratory: yes
- edge: volume
- mechanism: A daily reversal at a weekly reference level may identify rejection across timeframes. The screen must isolate the completed three-bar pattern from Double Pattern and Fibonacci confirmation triggers.
- order_form: stop-buy above the completed pattern's final bar high, valid the next session.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen three-bar-weekly-reversal

### 4. tight-base-breakout (setup-scout)

- claim: Screen a breakout from a contracting multi-week base to test whether a distinct consolidation setup adds profitable entries.
- evidence: playbook tight-base-breakout
- exploratory: yes
- edge: volume
- mechanism: Contracting ranges followed by a breakout on above-average volume may identify an imbalance after consolidation. The mechanism is a base breakout rather than a pullback volume dry-up gate or proximity to an annual high.
- order_form: stop-buy above the completed base high, valid for a fixed session window frozen in the screen definition.
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen tight-base-breakout

## Dropped

None.

## Generator results

- exit-harvester: NO ROWS. Positive exit cells describe realised outcomes without an actionable prospective rule; alternatives are thin or lack the required cell statistics.
- setup-scout: 3 rows returned.
- regime-desk: 1 row returned.
- This slate uses the corrected 2026-10-16 export that includes plans linked to open trades. It supersedes the earlier same-date slate committed as `6648d737`.

## Panel review

Run 2026-10-16 over `b389ca09` (quant-researcher on opus).

- quant-researcher [ADVISORY]: Rank 1's issuance-hour association does not measure whether an extra evening preparation pass produces incremental actionable opportunities. The proposed `/screen` route measures entry outcomes, not that intervention. Row 1 is withdrawn from the partner's choice pending a defined opportunity outcome and comparator; the ranked output above remains an audit record (`docs/superpowers/results/2026-10-16-scout-slate.md:14-23`; `docs/claude/backtest-methodology.md:62`).
- quant-researcher [ADVISORY]: The issuance-hour comparison excludes records with missing timestamps and may reflect selection, strategy or session effects. This limitation applies to the withdrawn row (`docs/superpowers/results/2026-10-16-book-autopsy.json:7527`; `scripts/reports/autopsy/cells.py:153`).
- Rows 2-4 remain exploratory playbook hypotheses requiring their own `/screen` runs before any spec.
- Dispatch note: the named `scout` agent was unavailable in this session; the three roles ran serially through the plan's read-only general-agent fallback.

## Partner pick

On 2026-10-16 the partner chose all three surviving setup ideas from this corrected slate for future screens:

- `gap-and-hold` -> `/screen gap-and-hold`
- `three-bar-weekly-reversal` -> `/screen three-bar-weekly-reversal`
- `tight-base-breakout` -> `/screen tight-base-breakout`

This records routing only; no screen was started. The earlier pick for the superseded slate does not carry forward its `rs-leader-index-pullback` row.
