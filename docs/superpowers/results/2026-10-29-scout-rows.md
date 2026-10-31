# Scout rows 2026-10-29 (raw, pre-merge)

The three roles' raw rows as fed to `scripts/dev/scout_merge.py` for `2026-10-29-scout-slate.md`. Kept as the V200-17 re-merge fixture.

## role: exit-harvester

- idea: pre-close-exit-on-gap-risk
  claim: Flag open longs and shorts carrying overnight gap risk and close or halve them at the prior close, so a gap through the stop stops costing about 1.9R.
  evidence: cell gap_through_stop=through_stop; N 51; weeks 8; Δ net ExpR -0.846 [-1.115, -0.331]; q 0.001
  exploratory: yes
  edge: expectancy
  mechanism: Through-stop exits net -1.915 R, against -1.069 R when the stop fills at the level (cell gap_through_stop=at_stop, N 210). The 0.846 R difference is pure gap overshoot, and the dollar loss at 2% risk is $383 against $214 at the stop. An exit before a known gap catalyst converts the overshoot into a smaller, ordinary loss. The cell spans exactly 8 weeks, so treat it as borderline coverage.
  order_form: market-on-close sell (or buy-to-cover), valid for the session of the flagged day
  manual_actions: a close-early notice on the alert thread the afternoon before the flagged event; it needs a new alert message
  pairs_with: protects the stop-cell loss (cell exit_reason=stop, N 184, net ExpR -1.307) and frees heat for later entries
  divergence: no
  route: /prereg

- idea: stop-fill-overshoot-audit
  claim: Check why realised stop losses exceed the 2% dollar cap, and test a resting-order stop fill to cut the overshoot, without widening the stop.
  evidence: cell exit_reason=stop; N 184; weeks 13; Δ net ExpR -1.535 [-2.032, -1.222]; q 0.001
  exploratory: yes
  edge: expectancy
  mechanism: The stop cell prints a loss at 2% risk of $261 against the $200 cap, an overshoot of 0.852, a stop distance of 0.38 ATR and a net ExpR of -1.307. Gross ExpR is -1.236, so the stop loses more than 1R on average. Part of that is gap fills (cell gap_through_stop=through_stop, N 51, $383), and part may be how the stop executes. The row targets execution and fill modelling only. It does not move the stop, because stop distance changes are in the closed set.
  order_form: resting stop order (stop-market), valid GTC, in place of a price check on the poll
  manual_actions: none
  pairs_with: recovers R on the 184 stop exits without changing entries
  divergence: yes
  route: /prereg

- idea: bank-partial-on-favourable-open-gap
  claim: When a position opens with a favourable gap, take a partial or full profit at the open instead of holding to the original targets.
  evidence: cell open_gap_bucket=favourable; N 256; weeks 14; Δ net ExpR -0.665 [-1.175, -0.311]; q 0.001
  exploratory: yes
  edge: harvest
  mechanism: Favourable-gap trades win only 35.2% of the time and net -0.444 R. The adverse_large bucket does better, at +0.220 R and 56.1% (cell open_gap_bucket=adverse_large, N 205, q 0.004). That pattern is consistent with a gap that pulls forward the move and then fades. Banking the gap at the open would harvest it before the fade. The cell is fully bar-covered (256 of 256), but the mechanism is a guess and rests on this window alone.
  order_form: market-on-open sell, or a limit just inside the gapped price, for the first session only
  manual_actions: a "target gapped, banked at open" update message on the alert thread
  pairs_with: the banked R shrinks the give-back, which the autopsy puts at a mean of 1.662 and a median of 1.324 over N 801
  divergence: yes
  route: /prereg

## role: setup-scout

- idea: no-chase-favourable-gap-limit
  claim: Fills where the open gaps in the trade's favour past the planned entry lose money, so replace the market-on-open fill on such a gap with a limit at the planned entry that lapses if price never returns.
  evidence: cell open_gap_bucket=favourable; N 256; weeks 14; Δ net ExpR -0.665 [-1.175, -0.311]; q 0.001
  exploratory: yes
  edge: expectancy
  mechanism: A favourable open gap hands the entry a worse price relative to the planned stop (a bigger risk per share) and often precedes an opening fade. A resting limit at the plan price only fills if the gap retraces into the plan level. Spread over 57 tickers, top share 7.4%, so it is not a few names.
  order_form: limit at the planned entry price, valid the gap session only; unfilled lapses (no stop-buy chase)
  manual_actions: none
  pairs_with: Plans that retrace into the planned entry still fill, and the lapsed plans are measured as unfilled in shadow; the volume loss must be read off the fill_status tallies (908 filled of 970 plans), never assumed.
  divergence: no
  route: /screen no-chase-favourable-gap-limit

- idea: atr-reentry-after-stop
  claim: Re-arm the original setup once, within a small fixed bar window, after a stop-out, because the stop cell is the largest loss bucket and some stops are noise.
  evidence: playbook atr-reentry-after-stop
  exploratory: yes
  edge: expectancy
  mechanism: Stops are tight (0.38 ATR median in cell exit_reason=stop, N 184, weeks 13) and a quick return through the entry trigger shows the stop was a wick. A single re-entry at the original ATR multiple recovers some of those. Caveat: it can stack losses in one name if the setup is truly broken, so cap it at one re-entry.
  order_form: stop-buy at the original trigger, valid for a fixed re-arm window; stop re-placed at the original ATR multiple
  manual_actions: none
  pairs_with: n/a
  divergence: no
  route: /screen atr-reentry-after-stop

- idea: tight-base-breakout
  claim: Add a narrow multi-week range breakout on above-average volume as an entry the registry lacks, to bring new volume rather than filter the existing book.
  evidence: playbook tight-base-breakout
  exploratory: yes
  edge: volume
  mechanism: Contracting ranges store energy and a volume break out of the base marks a trend start with a close stop under the base low. Alerts are concentrated after the close (alert_hour_session=after_close: 613), so a stop-buy form suits that timing.
  order_form: stop-buy above the base high, valid for a fixed number of sessions; stop under the base low
  manual_actions: none
  pairs_with: n/a
  divergence: no
  route: /screen tight-base-breakout

## role: regime-desk

- idea: after-close-alerts-resting-order-only
  claim: Treat the after-close alert (hour 20) as the only entry-eligible timing, and route premarket and regular-session alerts to a next-session resting order instead of an immediate entry, to lift net ExpR.
  evidence: cell alert_hour=20; N 518; weeks 14; Δ net ExpR +0.362 [0.034, 0.936]; q 0.083
  exploratory: yes
  edge: expectancy
  mechanism: An after-close alert gives a trader who is not watching time to rest the order before the open, and the plan is built on a completed daily bar. Alerts at other hours are issued against a bar that is still forming, or at a price that has already moved.
  order_form: stop-buy or limit resting order placed after the alert, valid for the next regular session only
  manual_actions: none
  pairs_with: premarket and regular-session alerts are re-timed to the next after-close scan, not dropped, so volume returns one session later (tallies: alert_hour_session=regular 83, premarket 38, after_close 613; actionable_before_open=no 83)
  divergence: no
  route: /screen after-close-alerts-resting-order-only

- idea: weekend-hold-survivor-screen
  claim: Test whether a deliberate weekend carry, meaning no forced Friday flatten and Friday-issued plans left to run, explains the positive net ExpR of weekend-spanning trades, or whether the cell is only survivorship.
  evidence: cell weekend_hold=yes; N 72; weeks 14; Δ net ExpR +0.630 [0.109, 1.219]; q 0.042
  exploratory: yes
  edge: expectancy
  mechanism: Weekend-spanning trades may keep their winners through the Monday open, where the 2-day weekend gap compounds the move. The cell is defined by the exit date, so it may only reflect trades that had not been stopped by Friday. The screen has to condition on what was known at entry, for example Friday-issued plans (friday_entry=yes shows no edge on its own: Δ +0.108 [-0.166, 0.481], q 0.667, cell friday_entry=yes), before any claim is made.
  order_form: unchanged stop-buy or limit entry, validity unchanged; the test varies only whether the position is carried across Friday close
  manual_actions: none
  pairs_with: n/a (the test changes no entry filter, so no volume is removed)
  divergence: no
  route: /screen weekend-hold-survivor-screen
