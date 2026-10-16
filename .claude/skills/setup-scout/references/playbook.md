# Setup playbook (setup-scout)

Curated trader setups for `setup-scout` (spec v161 § 3). Each entry is a
**candidate for `/screen`**, never a strategy: it routes to `/screen <idea>`
and cites `playbook <entry id>` as its evidence. Seeds avoid every closed row
in `docs/claude/backtest-methodology.md` § Closed pre-registrations — do not
re-run these and the one `SCREEN-PASS` (`screen-uptrend_pullback`). The
partner may edit, add or retire entries; an entry that reaches the ledger
names its ledger id here.

Left out on purpose: post-earnings drift (needs point-in-time estimates and a
`fundamental-analyst` review); 52-week-high and 20-EMA-pullback variants (too
close to `screen-high52w` and `screen-uptrend_pullback`).

## `gap-and-hold`

- **Rule:** the stock gaps up above the prior session's high and closes in the upper part of the day's range without filling the gap.
- **Horizon:** 1w to 2w swing.
- **Order form:** next-session stop-buy a tick above the gap day's high, valid one session; stop under the gap day's low.
- **Failure mode:** the gap fills on day two; a stop-buy that triggers into an opening fade.
- **Must not duplicate:** `screen-gap_volume` (SCREEN-FAIL: entry on the gap day itself, volume filter).

## `gap-fill-reversal`

- **Rule:** a gap away from a prior support or resistance level fills back into that level and the level holds on a closing basis.
- **Horizon:** 1w swing.
- **Order form:** limit at the level, valid one session; stop beyond the level by an ATR fraction fixed in the idea's screen definition.
- **Failure mode:** the level breaks on the fill; a limit filled on a trend day.
- **Must not duplicate:** `screen-gap_volume`; the confluence S/R levels already traded by the bot (a level the bot alerts on is not a new idea).

## `tight-base-breakout`

- **Rule:** a narrow multi-week range (contracting daily ranges) breaks out on above-average volume.
- **Horizon:** 2w to 1m swing.
- **Order form:** stop-buy above the base high, valid until cancelled for a fixed number of sessions; stop under the base low.
- **Failure mode:** a false breakout that closes back inside the base; a base too wide for the stop at the 2% dollar-risk cap.
- **Must not duplicate:** v122 pullback volume dry-up gate; `screen-high52w`.

## `rs-leader-index-pullback`

- **Rule:** a stock in the top relative-strength group holds above its own prior low on a day the index pulls back.
- **Horizon:** 2w to 1m swing.
- **Order form:** next-session stop-buy above the pullback day's high, valid one session.
- **Failure mode:** the index pullback becomes a regime change; leaders roll over last, then hard.
- **Must not duplicate:** `RS_GATE` (v34, shipped as a gate); `screen-uptrend_pullback` (own-RSI pullback, not index-relative).

## `failed-breakdown-reclaim`

- **Rule:** price breaks below a prior swing low, then closes back above it within a few sessions.
- **Horizon:** 1w to 2w swing.
- **Order form:** stop-buy above the reclaim bar's high, valid one session; stop under the failed-breakdown low.
- **Failure mode:** the reclaim fails and the breakdown resumes; thin names whipsaw through the stop.
- **Must not duplicate:** v127 structure-break armed entries; v88/v90 armed confluence entries.

## `atr-reentry-after-stop`

- **Rule:** after a stop-out, the original setup re-arms (price back through the entry trigger) within a small fixed number of bars.
- **Horizon:** the original plan's horizon.
- **Order form:** stop-buy at the original trigger, valid for the re-arm window; stop re-placed at the original ATR multiple.
- **Failure mode:** re-entering a broken setup twice; stacking losses in one name.
- **Must not duplicate:** v108 E EMA Crossover re-arm (first K pullback touches).

## `three-bar-weekly-reversal`

- **Rule:** a three-bar reversal pattern on daily bars at a level drawn from weekly bars.
- **Horizon:** 2w to 1m swing.
- **Order form:** stop-buy above the third bar's high, valid one session; stop under the pattern low.
- **Failure mode:** the weekly level is stale; the pattern prints mid-range, away from any level.
- **Must not duplicate:** `Double Pattern` (v69); the v124 Fibonacci confirmation trigger.
