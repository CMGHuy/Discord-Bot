# Scout slate 2026-10-21

**Autopsy:** `docs/superpowers/results/2026-10-21-book-autopsy-sep-era.json`
**Window:** 2026-09-02 to 2026-10-21 · **N:** 221 · **Cells tested:** 244 · **Net of frictions:** modelled

> Every autopsy-derived row is exploratory, and the holdout is protected: the live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, scripts/backtest/measure_v104.py). A row picked from this slate and sent to /prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows that end before the autopsy window starts, and its pre-registration records that the holdout is contaminated for that idea (never spent as confirmation). A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap).

A slate row is a hypothesis. No gate moves: it never edits code, config, thresholds or live alerts, and never licenses a re-run of a closed pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` row before its spec.

## Ranked

### 1. gap-fill-reversal-at-level (setup-scout)

- claim: Take the gap-away-then-fill-back-into-a-held-level setup as its own entry, because plans that open with a large adverse gap already outperform their complement.
- evidence: cell open_gap_bucket=adverse_large; N 83; weeks 8; Δ net ExpR +0.350 [0.017, 0.871]; q 0.056
- exploratory: yes
- edge: expectancy
- mechanism: A limit sitting at a support or resistance level fills at a better price when the open gaps against the trade. If the level then holds on a closing basis, the stop is tight against a level the market has just tested. The cell is carried by 40 tickers, with the top ticker at 7.2% of N, so it is not a few names. Its lower bound is barely above zero, so it is a hint rather than a result.
- order_form: limit at the level, valid one session; stop beyond the level by an ATR fraction fixed in the screen definition
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen gap-fill-reversal

### 2. atr-reentry-after-stop (setup-scout)

- claim: Re-arm the original setup once, within a short window, when price comes back through the entry trigger after a stop-out.
- evidence: playbook atr-reentry-after-stop
- exploratory: yes
- edge: volume
- mechanism: Many stop-outs are shakeouts of a setup that is still valid. A capped single re-arm recovers the move, and a cap on stacked losses in one name bounds the cost.
- order_form: stop-buy at the original trigger, valid for a fixed re-arm window; stop re-placed at the original ATR multiple
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen atr-reentry-after-stop

### 3. failed-breakdown-reclaim (setup-scout)

- claim: Add the playbook setup where price breaks a prior swing low and closes back above it within a few sessions, which the registry lacks.
- evidence: playbook failed-breakdown-reclaim
- exploratory: yes
- edge: volume
- mechanism: Stops resting under a swing low are run, and the reclaim shows that selling is exhausted. The stop then sits just under the failed-breakdown low, which keeps the risk small.
- order_form: stop-buy above the reclaim bar's high, valid one session; stop under the failed-breakdown low
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen failed-breakdown-reclaim

### 4. rs-leader-index-pullback (setup-scout)

- claim: Buy top relative-strength names that hold their prior low on a day the index pulls back, which is an index-relative pullback and not the own-RSI pullback already passed.
- evidence: playbook rs-leader-index-pullback
- exploratory: yes
- edge: volume
- mechanism: Leaders hold up while the index dips, so the next session's resumption tends to be bought first. Relative strength is measured against the index, not the stock's own RSI.
- order_form: next-session stop-buy above the pullback day's high, valid one session
- manual_actions: none
- pairs_with: n/a
- divergence: no
- route: /screen rs-leader-index-pullback

## Dropped

| Idea | Role | Reason |
|---|---|---|
| favourable-gap-limit-reentry | setup-scout | cell open_gap_bucket=favourable Δ lower bound -1.271 is at or below zero or unavailable |
| skip-favourable-open-gap-fills | regime-desk | cell open_gap_bucket=favourable Δ lower bound -1.271 is at or below zero or unavailable |

## Generator results

- exit-harvester: NO ROWS. Every ranked cell is an exit-outcome label or a calendar cell. The wider-stop reading of exit_reason=stop (stop 0.37 ATR) falls under the closed v114/v139 stop-geometry work.
- setup-scout: 5 rows returned, 1 dropped by the merge.
- regime-desk: 1 row returned, dropped by the merge.
- Input: the 2026-10-21 production export (776 closed trades). The scouts read the current exit-model era autopsy (`2026-10-21-book-autopsy-sep-era.md`, trades opened from 2026-09-01, N 221). Jul–Aug trades mostly carried a 0.35R first target and dominate the unfiltered book (`2026-10-21-book-autopsy.md`, net ExpR -0.107 against +0.063 for the era). The rejections export came back empty (header only).

## Controller notes (not slate rows)

These come from a hand pass over the raw export, outside the autopsy's BH family, so they are descriptive only. None is a slate row.

- **Dropped by the positive-Δ rule:** the two dropped rows rest on the strongest era cell, open_gap_bucket=favourable (N 88, Δ -0.696 [-1.271, -0.370], q 0.001). The merge accepts only cells whose Δ lower bound is above zero, so a filter that removes a losing cell cannot pass it as written. Routing a removal filter on that cell is the partner's call.
- **Integrity, stop enforcement:** 12 trades closed at `2026-08-04 18:55` UTC for -29.5R gross, and 6 more at `2026-08-05 15:34` for -12.9R. Some fills sat well past their stops (NBIS -6.0R, DELL -3.5R). Losses beyond -1.05R total -56.4R of excess across the book, and over half of it falls in those two minutes. This looks like a stalled price monitor catching up. It is unverified against the logs.
- **Stacked exposure:** 388 of 776 trades share a ticker, entry day and direction with another trade. On 2026-08-03, 17 long semiconductor trades (8 of them MU) lost -23.3R. In the era, singleton entries made +0.17R and pairs -0.02R. 53 ticker-days carried both a long and a short.
- **Telemetry gaps:** days_to_earnings is populated on 28 of 776 trades, and regime2_state and stop_width_atr on about 23%. About 4% of rows have mfe_r below the realised R, or a full stop with mae_r under 0.9.
