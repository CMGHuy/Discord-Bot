# Scout slate 2026-11-16

**Autopsy:** `docs/superpowers/results/2026-11-16-book-autopsy.json`
**Window:** 2026-07-20 to 2026-11-16 · **N:** 1067 · **Cells tested:** 411 · **Net of frictions:** modelled

> Every autopsy-derived row is exploratory, and the holdout is protected: the live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, scripts/backtest/measure_v104.py). A row picked from this slate and sent to /prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows that end before the autopsy window starts, and its pre-registration records that the holdout is contaminated for that idea (never spent as confirmation). A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap).

A slate row is a hypothesis. No gate moves: it never edits code, config, thresholds or live alerts, and never licenses a re-run of a closed pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` row before its spec.

## Ranked

### 1. avoid-volume-profile-hvn-2w (setup-scout)

- claim: Stand aside from the Volume Profile HVN 2w setup, which loses on net expectancy against the rest of the book.
- evidence: cell strategy_horizon=Volume Profile HVN|2w; N 36; weeks 11; Δ net ExpR -0.386 [-0.703, -0.228]; q 0.001
- exploratory: yes
- edge: expectancy
- direction: avoid
- mechanism: An HVN level is a congestion area, so price can chop through it instead of reacting. The post-era column of the cell is 19 trades at 5.3% WR and -0.600 net ExpR (autopsy cell, era columns carry no CI). Treat that as a pointer only. The two eras disagree (pre-era 17 trades at 58.8% WR, -0.303), so the loss may be a regime effect rather than the setup.
- order_form: n/a (a plan veto, not a new order). Entries stay unchanged for every other setup.
- manual_actions: none
- pairs_with: n/a. This only cuts N (36 trades over 11 weeks in the cell), so the gain is the avoided loss, with no volume to come back.
- divergence: no
- route: /screen avoid-volume-profile-hvn-2w
- projected pooled change: +0.013 R (drop this cell)

### 2. wednesday-entry-stand-aside (regime-desk)

- claim: Stand aside from, or defer to the next session, plans whose weekday is Wednesday, because that cell's net ExpR is below its complement's.
- evidence: cell weekday=Wed; N 242; weeks 15; Δ net ExpR -0.201 [-0.446, -0.024]; q 0.063
- exploratory: yes
- edge: expectancy
- direction: avoid
- mechanism: A Wednesday entry has fewer sessions before the weekend. The only supporting cell, weekend_hold=yes, is outcome-defined and not known at entry, so it is not cited. Pure speculation on the mechanism: the Wednesday cell may be picking up mid-week FOMC or macro-release clustering, but the autopsy carries no CPI or NFP dates and cannot test that.
- order_form: Keep the plan's limit or stop-buy order. A Wednesday-issued plan is held and re-validated at the Thursday pre-market scan, then rested as a day order with the same price levels. If invalidated, it is dropped.
- manual_actions: none
- pairs_with: The deferred Wednesday plans re-enter Thursday if still valid, so volume is delayed, not removed. Mon, Tue, Thu and Fri entries are untouched. The autopsy does not state whether weekday means issue day or fill day, and the screen must pin that first.
- divergence: no
- route: /screen wednesday-entry-stand-aside
- projected pooled change: +0.046 R (drop this cell)

### 3. atr-reentry-after-stop-rearm (setup-scout)

- claim: Re-arm the original setup once, within a short window, after a stop-out when price comes back through the original trigger.
- evidence: playbook atr-reentry-after-stop
- exploratory: yes
- edge: harvest
- direction: exploit
- mechanism: The autopsy shows 317 stop exits (cell exit_reason=stop), but that cell is outcome-defined and is context only. A stop-out on a quick shakeout can leave the thesis intact, and a re-arm recovers part of that R.
- order_form: stop-buy at the original trigger, valid for the re-arm window; stop re-placed at the original ATR multiple.
- manual_actions: none
- pairs_with: n/a (it re-uses stopped setups, so adds volume without loosening any gate). A cap of one re-entry per name limits stacked losses.
- divergence: no
- route: /screen atr-reentry-after-stop
- projected pooled change: n/a (no autopsy cell)

### 4. gap-and-hold-next-session-stop-buy (setup-scout)

- claim: Add a next-session stop-buy above the gap day's high after a gap-up that holds the upper range, so the entry is not taken on the gap day.
- evidence: playbook gap-and-hold
- exploratory: yes
- edge: volume
- direction: exploit
- mechanism: A gap that survives its first session shows demand that did not fade. Entering the day after, above that day's high, skips the gap-day opening fade that sank screen-gap_volume.
- order_form: stop-buy a tick above the gap day's high, valid one session; stop under the gap day's low.
- manual_actions: none
- pairs_with: n/a (a new entry type that adds volume).
- divergence: no
- route: /screen gap-and-hold
- projected pooled change: n/a (no autopsy cell)

### 5. tight-base-breakout-volume (setup-scout)

- claim: Add a stop-buy entry on a break above a narrow multi-week base on above-average volume, a setup missing from the strategy registry.
- evidence: playbook tight-base-breakout
- exploratory: yes
- edge: volume
- direction: exploit
- mechanism: Contracting daily ranges followed by a volume expansion mark supply exhaustion. A narrow base also keeps the stop tight enough for the 2% dollar-risk cap.
- order_form: stop-buy above the base high, valid for a fixed number of sessions; stop under the base low.
- manual_actions: none
- pairs_with: n/a (a new entry type that adds volume).
- divergence: no
- route: /screen tight-base-breakout
- projected pooled change: n/a (no autopsy cell)

## Dropped

None.

## Panel review

quant-researcher (2026-11-16), all ADVISORY, none BLOCKING. Both projected pooled changes re-derived and match (+0.013 R, +0.046 R).

1. quant-researcher: rank 2 (Wednesday) rests on the post-era only (pre-era Wed -0.152 sits among Mon -0.153, Tue -0.117, Thu -0.180; post-era Wed -0.348 against +0.008..+0.226), q 0.063 passes only the 0.10 merge ceiling, it is the worst of five weekday cells and its mechanism is self-described speculation; not fit to route to /screen as written (autopsy.md:41,52,60,79,82; scout_merge.py:384) -- applied: recorded, not routed.
2. quant-researcher: rank 2 does not freeze issue day versus fill day, and its +0.046 R projection assumes the cell is dropped while the order form defers to Thursday (unmeasured); nearest calendar precedent `turn_of_month` is SCREEN-FAIL (backtest-methodology.md:124-126,320) -- applied: recorded, not routed.
3. quant-researcher: rank 1's "the two eras disagree" is wrong on net ExpR: both eras are negative (pre 17 trades -0.303, post 19 trades -0.600), only win rate flips (58.8% vs 5.3%); a 58.8% win rate with negative ExpR points to harvest/R-geometry, and 36 trades over 11 week-clusters is thin (autopsy.md:37) -- applied: recorded.
4. quant-researcher: rank 1 targets Volume Profile, which has an OPEN sealed-thin pre-registration `v104-a-volume-profile-bullish` with one unspent 2026 holdout shot; this autopsy read a VP HVN cell inside that holdout (preregistration-ledger.jsonl:40; backtest-methodology.md:331) -- applied: recorded here; the v104-a retry must note the contamination.
5. quant-researcher: the `2w` part of rank 1 cannot be expressed in the screen (fixed race shapes on PIT S&P 500 2010-2019, no bot horizon); the idea needs redefining and a control_condition before /screen (backtest-methodology.md:95-108,140-160) -- applied: recorded, not routed as written.
6. quant-researcher: total R beside ExpR: rank 1 is about -16.6 R over 36 trades, rank 2 about -58.8 R over 242 trades (23% of the book's trades) (slate rows 1-2) -- applied: recorded.
7. quant-researcher: rank 3 borders the closed v108 E re-arm (NO-LIFT), depends on the bot's own stop-outs which a screen event cannot carry, has a row id differing from its route id, and is a `volume` entry, not `harvest` (backtest-methodology.md:134-136,340; 2026-10-29-scout-slate.md:84) -- applied: recorded, not routed.
8. quant-researcher: rank 4 is distinct from SCREEN-FAIL `gap_volume`, but its next-session stop-buy differs from both screen race shapes (next-open entry); the only stop-entry precedent `range_breakdown_stop` failed fill-depth check 5 (backtest-methodology.md:99-104,319,376) -- applied: recorded; entry form must be frozen before /screen.
9. quant-researcher: rank 5's "missing from the strategy registry" is wrong: Support/Resistance already carries a tight-base clause; it borders `high52w` and `range_breakdown_close` SCREEN-FAIL and v105 NO-LIFT (docs/strategy-types/support-resistance.md:21; backtest-methodology.md:317,361,375) -- applied: recorded, not routed.
10. quant-researcher: ranks 3-5 carry no autopsy evidence and repeat the 2026-10-16, 10-21 and 10-29 slates without restating the earlier panel's route conditions (2026-10-16-scout-slate.md:86-90; 2026-10-29-scout-slate.md:84-85) -- applied: recorded.
11. quant-researcher: both autopsy rows rest on 11 and 15 week-clusters, so the bootstrap bounds are optimistic and should be read as thin (autopsy.md:8,29) -- applied: recorded.
12. quant-researcher: fillability of a post-shakeout re-entry and of a stop-buy at the gap-day high is a veteran-trader question (slate row 3) -- applied: recorded, out of scope here.
