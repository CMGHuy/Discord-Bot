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

These are counts from a hand pass over the same export the autopsy hashed (input manifest a74fa6ae… in `2026-10-21-book-autopsy.json`). They sit outside the BH family and are descriptive only. The raw CSV stays in the scratchpad, so no pooled-R figure is quoted here. Each item is a lead for quant-engineer to verify, never evidence for a row.

- **Stop enforcement (integrity):** 12 closed trades share the close timestamp `2026-08-04 18:55` UTC, and 6 more share `2026-08-05 15:34`. Across the book, 82 of 348 losing trades closed beyond -1.05R gross. The largest were NBIS (-6.0R) and DELL, GLW and MRNA (about -3.3 to -3.5R each). The pattern fits a stalled price monitor that caught up later. It is unverified against the logs.
- **Stacked exposure:** 388 of 776 closed trades share (ticker, entry date, direction) with at least one other trade, across 145 such groups. 53 ticker-days carried both a long and a short. On 2026-08-03, 17 long entries were opened, 8 of them MU. Every cell N above therefore overstates the number of independent bets.
- **Telemetry gaps:** days_to_earnings is populated on 28 of 776 trades, and regime2_state and stop_width_atr on about 180 each. Among winners, 23 of 392 have mfe_r more than 0.05 below realised R. Among full stops, 30 of 309 have mae_r under 0.9.
- **Dropped rows:** the merge's rule (Δ lower bound > 0) dropped both rows on open_gap_bucket=favourable. See the panel finding on sign below.

## Panel review

Run 2026-10-21 over `66a0445b` (quant-researcher on opus).

- quant-researcher [BLOCKING]: the Controller notes quoted pooled R without N or a reproducible source -- **applied**: cut down to counts with the export manifest named, and no pooled R.
- quant-researcher [ADVISORY]: the open_gap_bucket sign is the reverse of both scouts' reading (`scripts/reports/autopsy/bars.py:128-137`, `pct = (open - planned_entry)/planned_entry * sign`). **adverse_large** is a fill-day open more than 1% *past* entry in the trade's direction. **favourable** is an open through entry against the trade, the losing cell. Rank 1's mechanism (a limit filling at a better price) is therefore inverted, and so are the dropped rows' "do not chase" readings. gapped_through_entry is uncovered on 207 of 221 trades, so the cell does not identify an order form -- **applied**: Rank 1 is withdrawn from the partner's choice. The contrast reads as "gaps against the plan through entry lose, gaps with the plan win". Whether that leads to a cancel-at-open rule is a veteran-trader question for a future /screen, not a row.
- quant-researcher [ADVISORY]: Rank 1 and both dropped rows are one contrast on a single cut (favourable N 88 against adverse_large N 83 of 208) -- applied: counted once, as above.
- quant-researcher [ADVISORY]: the 2026-09-01 era boundary was chosen after the data was read and is not pinned to a deployment commit; exit changes landed 2026-09-03, 09-09 and 09-10. Both BH families (362 and 244 cells) were looks -- recorded. The full book agrees on both gap cells but is not independent. Any /prereg must use windows that end before 2026-07-20, so the boundary does not reach a gate.
- quant-researcher [ADVISORY]: Rank 1's interval comes from 8 week-clusters, which tends to run narrow -- recorded; moot after the withdrawal.
- quant-researcher [ADVISORY]: a removal filter on the favourable cell is a new filter. It needs SCREEN-PASS, scoring on pooled ExpR and total R over the whole population with the N shrink disclosed, and a tradeability check (at the open it becomes a cancel rule) -- recorded; the merge rule stays unbent.
- quant-researcher [ADVISORY]: distinct ticker-day counts should sit next to cell N -- recorded under Stacked exposure above.
- quant-researcher [ADVISORY]: Rank 4 (rs-leader-index-pullback) sits next to the closed v34 RS-leader arm (`docs/claude/backtest-methodology.md:271`). A /screen must freeze an index-relative trigger distinct from `RS_LEADER_PERCENTILE` -- recorded as a condition on that route.
- quant-researcher [ADVISORY]: the stop-monitor stall, telemetry coverage and the mfe_r inconsistency belong to quant-engineer before full-book cells count as support -- recorded.

## Partner pick

On 2026-10-21 the partner sent no ranked row onward and chose to verify the 2026-08-04/05 stop-enforcement lead first (Controller notes). That check is an integrity question for production, not a /screen or /prereg route.
