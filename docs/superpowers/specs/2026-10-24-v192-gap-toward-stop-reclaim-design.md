# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop

**Version:** ui 1.35.1 · bot 2.15.0 (at writing)
**Bump:** bot patch (one inert knob and a new pending state for market plans; nothing changes until the partner flips it)
**Edge:** expectancy — removes market-entry trades whose next open has already moved toward the stop and never trades back to the planned entry. Prediction (falsifiable, selected cell): decided win rate rises by at least +1.5pp; ΔExpR is positive; the removed population has a lower win rate and ExpR ≤ 0 (v72 clause 6). A result contradicting any of the three is recorded as a missed prediction. The +1.5pp is a judgement, not derived from the autopsy cell: that cell pools stop-entry, limit and market rows and, for live market plans, compares the alert-day open with the alert price (panel).
**Screen:** exempt (post-signal)
**Panel:** quant-researcher, veteran-trader, quant-engineer
**Status:** spec written 2026-10-24 from a brainstorm with the partner the same day. The partner's answers are marked *(partner)*; Claude's calls are marked *(Claude's call)* and listed again at the end.

## Why

**The live book's strongest cell.** In both autopsy windows the trades
whose fill-day open sat beyond the planned entry *toward the stop* (the
autopsy's `open_gap_bucket=favourable`: a better price, a worse position)
were the worst bucket:

- full window (2026-07-20..2026-10-21): N = 226, WR 35.4%, net ExpR −0.467, Δ −0.698R [−1.225, −0.328], q = 0.001;
- current exit-model era (2026-09-02..2026-10-21): N = 88, WR 21.6%, net ExpR −0.301, Δ −0.696R [−1.271, −0.370], q = 0.001.

Opens beyond entry in the trade's direction by more than 1% did better
(`adverse_large`, Δ +0.35R to +0.47R). Both windows overlap the 2026
holdout, so these are exploratory and motivate, never select
(`2026-10-21-book-autopsy.md`, `2026-10-21-book-autopsy-sep-era.md`; bucket
definition `scripts/reports/autopsy/bars.py:128` `_gap`, flat band 0.25%).

**Correction on record.** The first brainstorm message read the autopsy's
"favourable" label as a gap in the trade's direction; it is the opposite
(a cheaper fill because price moved toward the stop). The `gap_volume`
screen (buying after a ≥ 1 ATR gap-up, SCREEN-FAIL at −0.46R) is therefore
**not** evidence for this veto and is not cited as such.

**Why a post-signal veto and not a screen.** The idea screen races events
on any bar with no bot signal beneath them. "A long whose next open gaps
down" with no signal is a buy-the-dip event that often beats a random
entry, so a screen would measure a different thing. The partner chose
(2026-10-24) the funnel on the bot's own replay and a narrow exemption
from the screen rule, committed as `b64dcd22` (`Screen: exempt
(post-signal)`; Stage −1 reachability is mandatory instead).

## Pre-registered claim

On market-entry plans, replacing the unconditional entry with "wait for a
same-session reclaim of the planned entry when the next open gaps toward
the stop by at least `g × ATR14`" raises win rate without breaking the v72
funnel's expectancy, geometry, volume and mechanism clauses.

## Scope

- **Market-entry plans only**, confluence and strategy sources, bullish and
  bearish. A stop-entry plan already waits for its trigger, and a limit plan
  already fills only at its level, so neither changes *(Claude's call)*.
- Every other plan, gate, stop, target and size is untouched.

## Definitions (frozen at the plan's creating bar)

- **Signal bar `t`:** the plan's creating bar; ATR14 is Wilder ATR14 of
  completed bars through `t` (`a_t`, in price). No bar after `t` is read to
  decide the threshold (NO-LOOKAHEAD). `TradePlanV2` has no ATR field, so
  `a_t` (Wilder ATR14 from the plan's own bars) is computed once at
  creation and stored on the plan beside `reclaim_level`; live and replay
  read that one value.
- **`E` in replay** is the plan's `trigger_price`, which equals `Close[t]`
  for a replayed market plan; live it is the scan price. A parity test pins
  `E`, `a_t` and `X` in both.
- **Planned entry `E`:** the plan's `trigger_price` (the scan price a market
  plan carries today).
- **Gap toward the stop at `t+1`:** bullish `E − Open[t+1]`, bearish
  `Open[t+1] − E`, in price; positive means the open sits beyond `E` toward
  the stop.
- **Threshold grid:** `g ∈ {0.10, 0.25, 0.50}`; the veto arms when the gap
  is `≥ g × a_t`.
- **Reclaim:** bullish `High[t+1] ≥ E + 1 tick`, bearish `Low[t+1] ≤ E − 1 tick`
  (a bare touch of `E` is not a reliable stop-order fill; panel). Same session
  only *(partner: wait for a reclaim; Claude's call: one session)*.

## The rule

At session `t+1`:

0. **Overnight stop cross (partner, 2026-10-24):** live, a waiting market
   plan whose stop is crossed in premarket is cancelled `open_through_stop`
   at once, after two consecutive confirming 60 s polls. This is **new
   code**: `EXTENDED_HOURS_EXIT_CHECK` / `EXTENDED_HOURS_DEBOUNCE_TICKS`
   (`config.py:708`, `:725`) are read by nothing since v70's `_step_extended`
   was removed on 2026-09-14; `poll` gates only on quiet hours. The plan adds
   a market-plan step ahead of `_step_pending` (whose stop-entry rule would
   otherwise fill a waiting market plan at any price ≥ E). Replay sees only daily bars, so it cancels on
   the open alone; a premarket cross that recovers by the open is a known
   live-only cancel, counted live and reported, never simulated.
1. Open at or beyond the stop → cancelled, `open_through_stop` (new for ordinary market plans: today only v180 Turtle Soup has this cancel, in replay).
2. Gap toward the stop `< g × a_t` → the plan fills exactly as the baseline does.
3. Gap `≥ g × a_t` → the plan becomes a resting order at `E` for that session:
   - reclaim → fills at `E` as a DAY stop order (buy-stop for a long,
     sell-stop for a short); an open already past `E` cannot occur here by
     construction. The v1 arm replay carries no frictions (raw R in both
     arms), so the stop order's slippage is modelled as a fill at `E + 1
     tick` (`E − 1 tick` for a short);
   - no reclaim → cancelled, reason `gap_no_reclaim`, with a Discord
     follow-up "cancelled: opened toward stop, no reclaim" through the
     existing follow-up path.
4. **Ambiguous bar** (bar `t+1` both reclaims `E` and reaches the stop):
   counted as filled at `E` and then stopped, −1R plus frictions
   *(partner approved; daily bars cannot order the two touches, so the
   conservative reading)*.

The fill price is `E`, so a reclaimed trade's stop, targets and R are the
plan's own. **The fill bar is walked in both arms:** after a fill on `t+1`
(at the open or at `E`), bar `t+1`'s own stop and TP1 touches count, with
the existing stop-first convention on a bar touching both, and the fill
session is session 1 of the hold cap (`SESSION_ONE_HOLD_CAP`). `_walk_for`
scans from `entry_index + 1`, so the plan adds a fill-bar check (as limits
do with `_fill_bar_exit`) for both arms alike; the ambiguous-bar rule is
that same convention applied to a reclaim fill, so it biases neither arm.

## Replay basis (both arms)

Instrument v1 fills a market plan at the signal-bar close
(`exit_sim._market_exit`), so it has no next open to veto. v180 added a
per-plan next-open fill inside v1 (`planning/next_open_entry.py`), but its
walk is single-leg and confluence plans use the scale-out exit. The
measurement therefore runs **both arms on a next-open market fill that
feeds each plan's normal exit walk** (scale-out where the plan uses it):

- **baseline:** every market plan fills at `Open[t+1]`, with an
  open-through-stop cancel and the risk-cap check, longs and shorts (v180's
  helpers are long-only and single-leg, so this is new code, not reuse);
- **component:** the same, plus the rule above.

The next-open fill is its own knob, `MARKET_ENTRY_NEXT_OPEN` (bool, default
off, live and replay). The baseline arm runs with it on and the component
with it on plus `GAP_RECLAIM_ATR = g`, so the measurement driver must take
a **baseline knob delta**: `measure_arms.py` runs its baseline with an
empty delta today, so the plan adds a baseline-delta option (or a sibling
driver). `GAP_RECLAIM_ATR > 0` is honoured only when
`MARKET_ENTRY_NEXT_OPEN` is on (bot-side check at load and reload).

So the comparison isolates the veto *(Claude's call)*. The next-open
baseline differs from today's v1 default (close fill), and its own WR and
ExpR are reported beside today's as disclosure; it decides nothing.
Instrument v1, `data_source` `alpaca` (the v162 store), the watchlist-era
universe v139/v180 used, fold-train 2018-06-01..2022-12-31, VALIDATION
2024-01-01..2025-12-31 *(Claude's call: v190's v3 is refused by the funnel
until mapped)*.

## Gate

The standard v72 funnel through `measure_arms.py`. **Not a pure subset
feature** (panel): reclaimed trades fill at `E` in the component and at
`Open[t+1]` in the baseline, so `population_split` returns
`is_subset=False` and `_clause_mechanism` would return SKIPPED. Frozen
here, before TRAIN:

- strata: **removed** (`gap_no_reclaim` cancels), **re-priced**
  (reclaimed fills), **added** (component trades with no baseline twin,
  which `StrategyEngine.open_until` creates when a baseline trade is
  cancelled) and **unchanged** (everything else; `open_through_stop`
  cancels are `not_triggered` in both arms and excluded from both).
  `population_split` cannot label these today (re-priced trades pair on the
  same key), so the plan adds the labelling;
- clause 6 (mechanism) is scored removed vs unchanged: removed WR <
  unchanged WR and removed ExpR ≤ 0; the re-priced stratum is reported as
  a third row and decides nothing;
- volume cut = removed ÷ baseline N; the geometry lock is computed on every
  kept trade, re-priced included;
- the plan adds this scoring explicitly; a SKIPPED clause counts as a fail
  (`evaluate` does not fail on SKIPPED today, so this is a code change
  behind an opt-in, leaving other components' verdicts as they are).

- **Stage −1 reachability (mandatory, the exemption's condition):** market
  plans per horizon and direction; how many arm the veto at each `g`; how
  many reclaim; ambiguous-bar count. Zero changed outcomes closes the cell
  `refused:zero-diff`.
- **Stage 0:** paired MDE on fold-train, statistic ΔWR
  (`acceptance.mde_paired(..., statistic=...)` as v72 uses it).
- **Stage 1:** winner = the `g` with the highest pooled fold-train ΔWR
  (on the whole fold-train window's rows, once; the selection folds are
  expanding, so pooling them would triple-count the early years) among cells
  with ΔExpR ≥ −0.01R; ties go to the smaller `g`. The plateau check is
  `plateau_report()` (scores ExpR)
  existing tolerance; an edge cell is adoptable with its one neighbour; a
  spike does not proceed.
- **Stage 2:** walk-forward folds 2021 / 2022 / 2023, `gate_win_rate`.
- **Stage 3:** one VALIDATION shot, all six v72 clauses: ΔWR > 0 (p < 0.05),
  ΔExpR lower bound > −0.01R, geometry lock (median planned RR and mean win
  R fall ≤ 2%), volume cut ≤ 25%, permutation p < 0.05, mechanism (removed
  WR < retained WR and removed ExpR ≤ 0).

Frictions: the v1 arm replay applies none (`frictions.py` runs only in the
legacy loop), so both arms are raw R alike; the reclaim fill takes one
adverse tick instead; a gap through a stop fills at the open. Intervals come from
`week_cluster_bootstrap` (`instrument/stats.py`), since one scan day's
plans gap together on market-wide opens. Multiple comparisons: three `g`
cells searched; the source, direction and horizon splits are descriptive
and cannot rescue a pooled fail; the ledger row cites `ledger_qvalues`.
One ledger row.

## Live behaviour (only when the partner flips the knob)

- **The bot decides at the open** *(partner, 2026-10-24)*. The alert reads
  "Enter at the open (market-on-open)". At the open the bot measures the
  gap itself; if it is `≥ g × a_t` it posts a follow-up "Don't buy at the
  open: DAY buy-stop at E" (sell-stop at E for a short), before any fill.
  `X = E ∓ g × a_t`, rounded to the tick away from `E`, is shown on the
  alert for reference. This suits paper trading and the eToro demo API; a
  manual trader looks once at the open.
- Every cancel and the reclaim instruction (`open_through_stop`, the
  premarket cancel, `gap_no_reclaim`, the DAY buy-stop instruction) posts
  to the simple-alerts execution feed as well as to Following followers,
  so a non-follower is never left with a stale order.
- Reclaim detection live is the 60 s plan monitor during regular hours; a
  brief touch between polls can be missed. Live reclaim rate vs the
  replay's is reported after the knob is flipped.
- **Every market plan waits for the next open** *(partner, 2026-10-24)*:
  with `MARKET_ENTRY_NEXT_OPEN` on, a market plan is built PENDING, not
  ACTIVE (`builders.py:477/:488`, `:702/:711` today set `entry_price = close` and
  activate at build), and the trade is logged at the fill, not at creation.
  At the next open it fills at the open, cancels on an open through the
  stop, or (veto armed) rests at `E` for the session and cancels at the
  close with no reclaim. Market plans never pass through `_step_pending`
  today; its stop-entry fill rule `max(price, trigger)` and risk-cap check
  are not reused as they are, and the plan names the new step.
- New transitions `gap_no_reclaim` and `open_through_stop` get entries in
  `plan_manager._TRANSITION_LOG` and in the mapping tables of
  `swingbot/commands/scanning/follow_notify.py`, with placeholder discard in
  `_on_event` like the existing cancels. That path posts only to
  Following followers.
- Sizing is unchanged (`gap_sizing.size_for_plan` on `E` and the stop).
- Computed once: `X` is stored on the plan at creation; a reload never
  rewrites it.

## Config

- `GAP_RECLAIM_ATR` — float `g`, default `0` (off). Search class
  `searchable`; a `ScanParams` slot and a reachability row.
- `MARKET_ENTRY_NEXT_OPEN` — bool, default off; `ScanParams` slot and
  reachability row (replay and live).

With both knobs off, every replay output and live plan is byte-identical to
today, pinned by a flag-off golden captured before any behaviour change.

## Code changes (the plan pins file:line)

- **`planning/exit_sim.py` / a sibling module:** a next-open market fill
  that hands off to `_walk_for(plan, scale_out)`, plus the veto branch.
  The v180 `next_open_entry` single-leg walk stays as it is for Turtle Soup.
- **`planning/plan_types.py`:** `TradePlanV2.reclaim_level: float | None`
  (the stored `X`), JSONB add path, round-trip test.
- **`planning/plan_manager.py`:** the pending-at-open state, reclaim
  activation and end-of-session cancel; the follow-up message reuses
  `follow_notify`'s path.
- **Alert:** one line in the embed and the simple channel text.
- **`core/backtesting/arms/reachability.py`:** the knob's row.

## Reporting (every stage)

- N, ΔWR, ΔExpR with 95% week-cluster bootstrap intervals; outcome flips;
  removed / re-priced / unchanged WR and ExpR.
- Re-priced trades in dollars on a fixed reference account (R units differ
  between the arms: `E − stop` vs `Open − stop`).
- Ambiguous-bar sensitivity: the component with ambiguous bars counted as
  `gap_no_reclaim` cancels instead of −1R fills.
- Stage −1 also reports the distribution of `gap / a_t` over market plans,
  so a grid outside the real gap range is `refused:zero-diff`, not a quiet
  no-op.
- Before TRAIN: the 2026-10-21 autopsy cells re-cut to market plans only,
  as disclosure.
- Per `g`: veto-armed count, reclaim rate, ambiguous-bar count and its
  share of reclaimed trades.
- Split by source (confluence / strategy), direction and horizon, with the
  top-two-horizon share.
- Baseline basis: next-open baseline vs today's v1 close-fill WR and ExpR,
  on fold-train only.
- Regime (`regime2`) cut, descriptive. No earnings-proximity cut: the v1
  row (`ArmTrade`) has no earnings date and no as-of earnings archive exists
  (`compression_research.py:7-13`); recorded as unavailable.

## On a pass / on a fail

- **Pass:** recorded; the knob default stays 0 until the partner decides.
  The veto needs `MARKET_ENTRY_NEXT_OPEN` on, and that knob changes every
  market plan's fill. It is **not licensed by this pass**: it needs its own
  pre-registered non-inferiority check (next-open vs close fill) before the
  partner flips both. This spec reads next-open vs close-fill on fold-train
  only, never on VALIDATION, so that later check still has an unspent
  window.
- **Fail:** one row in "Closed pre-registrations", one ledger row. Reopen
  clause: "a fill rule other than a same-session reclaim of the planned
  entry after a next-open gap toward the stop of `g × ATR14`". Another grid,
  window, reclaim length or MDE ceiling is not a new mechanism.

## Testing

- Flag-off golden first: knob 0 → replay byte-identical. It pins replay
  trade lists and `ExitResult` legs for market, stop-entry, limit and v180
  plans, and the live `TradePlanV2` JSON round-trip with `reclaim_level`
  absent.
- Fill-bar helper: a new next-open fill-bar check covering the stop *and*
  TP1 (stop-first); `_fill_bar_exit`'s 0R `gap_through_stop` scratch is not
  reused, the open-through-stop case is a `not_triggered` cancel in both arms.
- Hold cap: the fill session counts as session 1 for next-open market plans
  that have a hold cap, only when `MARKET_ENTRY_NEXT_OPEN` is on
  (`_counts_fill_session` widened behind the knob). Confluence plans have
  no `hold_cap_bars`, so `_hold_cap_bars` returns early and nothing
  changes for them.
- `measure_arms.py`: the baseline delta is stamped in the artifact beside
  `knob_delta`, `static_refusal` / `population_refusal` run on it, and
  `apply_knobs` enforces the `GAP_RECLAIM_ATR`-needs-next-open guard (not
  only bot load).
- Live: premarket stop cross on a waiting market plan → cancelled after the
  debounce, follow-up posted to the execution feed.
- Rule cases, bullish and bearish: gap just under / exactly at / above
  `g × a_t`; reclaim / no reclaim; open through the stop; ambiguous bar →
  −1R; the exit walk starts after the fill on `t+1`.
- Next-open baseline: a market plan fills at `Open[t+1]`, bar `t+1` is
  walked (stop and TP1 touches on the fill bar count, stop-first), the hold
  cap counts the fill session as session 1, longs and shorts.
- Live: with `MARKET_ENTRY_NEXT_OPEN` on, a market plan is built PENDING and
  logged at the fill; `GAP_RECLAIM_ATR > 0` without it is treated as 0 with
  an error log.
- No lookahead: `a_t` ignores bar `t+1` (mutate it, threshold unchanged).
- `plan_manager`: pending at open → reclaim activates at `E`; no reclaim →
  cancelled at the close with the follow-up; reload leaves `reclaim_level`
  alone.
- `reclaim_level` round-trip against the test DB, never left skipped at
  close-out.
- Complexity < 15 on every function written or changed.

## Out of scope

- Stop-entry and limit plans; any multi-session reclaim; partial size.
- Changing v1's default market fill for anything but this measurement.
- Re-measuring on instrument v3.

## Left to the builder

- Whether the next-open fill lives in `exit_sim.py` or a sibling module.
- The pending-state name in `plan_manager` and its transition reason text.
- Task split and `Model:` tiers.

## Claude's calls, for the partner to check

1. Market-entry plans only (stop-entry and limit already wait).
2. Same-session reclaim only.
3. Both arms on a next-open fill (`MARKET_ENTRY_NEXT_OPEN`) so the comparison isolates the veto; today's close-fill baseline reported beside it; `measure_arms.py` gains a baseline knob delta.
6. The fill bar is walked in both arms with the existing stop-first convention.
4. Instrument v1, `alpaca`, the v139/v180 universe and windows.
5. Panel: quant-researcher, veteran-trader, quant-engineer.

## Parallelisation

- **Group A (parallel):** flag-off golden; config `Field` + `ScanParams` + reachability row; `TradePlanV2.reclaim_level` with its round-trip test. Disjoint files, none changes behaviour.
- **Group B (after A), sequential:** next-open market fill feeding the normal walk → the veto branch → `plan_manager` pending/reclaim/cancel → alert line. All touch the market-entry path.
- **Group C (after B):** Stage −1, one `backtest-runner`.
- **Group D (after C):** Stages 0 → 3, one `backtest-runner` at a time.
- **Sequential tail:** record the result and ledger row, full suite once, close-out.

Builder-check corrections (2026-10-24, before the panel): open-through-stop is new for ordinary market plans; `_walk_for` skips the fill bar, so a fill-bar check is added for both arms; market plans never pass through PENDING today; v180's next-open helpers are long-only; the follow-up path and transition tables need the new reasons; the baseline needs its own knob and a baseline delta in the driver.

## Panel review

2026-10-24, quant-researcher (opus), veteran-trader (sonnet), quant-engineer (sonnet). Partner answers on the order form and the overnight stop cross are marked in the text.

- veteran-trader [BLOCKING]: the reclaim entry cannot be placed as one pre-open order -- applied: the bot decides at the open and posts a DAY buy-stop/sell-stop at E as a follow-up *(partner)*.
- veteran-trader [BLOCKING] + quant-engineer: the reclaim fill at exactly E is optimistic -- applied: E ± 1 tick penetration required, frictions slippage on the adverse side at E.
- veteran-trader [BLOCKING]: non-followers get no cancel message -- applied: cancels and the reclaim instruction also post to the simple-alerts execution feed.
- veteran-trader [BLOCKING]: "every market plan waits" leaves the order type and the stale-order case open -- applied: the alert says market-on-open, and the plan is PENDING from the alert so nobody enters at the close; a stop crossed overnight cancels in premarket *(partner)*.
- quant-researcher + quant-engineer: not a subset feature, so the mechanism clause would be SKIPPED -- applied: three strata (removed / re-priced / unchanged) frozen, clause 6 scored removed vs unchanged, SKIPPED counts as a fail.
- quant-researcher: the motivating cell is not market-only -- applied: the prediction is marked a judgement; a market-only re-cut is disclosed before TRAIN.
- quant-researcher: a pass would license the ungated `MARKET_ENTRY_NEXT_OPEN` -- applied: it needs its own non-inferiority pre-registration; next-open vs close-fill is read on fold-train only.
- quant-researcher: no Stage 1 winner rule -- applied: max pooled fold-train ΔWR with ΔExpR ≥ −0.01R, ties to the smaller g.
- quant-researcher: no interval estimator -- applied: `week_cluster_bootstrap`.
- quant-researcher: multiple comparisons not counted -- applied: 3 cells, splits descriptive, `ledger_qvalues` cited.
- quant-researcher: R units differ on re-priced trades -- applied: dollar view on a fixed reference account.
- quant-engineer: `_fill_bar_exit` checks only the stop and scratches at 0R -- applied: a new fill-bar helper with TP1, and open-through-stop is `not_triggered` in both arms.
- quant-engineer: `SESSION_ONE_HOLD_CAP` covers only two strategies -- applied: widened behind the knob only.
- quant-engineer: the baseline delta is unstamped and the guard is not in `apply_knobs` -- applied.
- quant-engineer: live/replay parity of E, a_t, X and reclaim polling -- applied: parity test, and live reclaim rate reported after the flip.
- quant-engineer: gap/a_t distribution and ATR source -- applied.
- quant-engineer: golden coverage unstated -- applied.
- quant-engineer + veteran-trader: ambiguous bars bias the comparison -- applied: a sensitivity run with ambiguous bars as cancels.
- veteran-trader: frictions at the open -- applied as one adverse tick on the reclaim fill (the v1 arm replay carries no frictions in either arm; plan-briefer).
- veteran-trader: time-in-force -- applied: DAY.
- veteran-trader: liquidity for the reclaim order -- rejected: the replay universe is the liquid watchlist era v139/v180 used; sizing is unchanged and the 2% dollar cap holds.
- veteran-trader: event days not split -- rejected: no point-in-time earnings date exists for the replay (plan-briefer); left to a fundamental-analyst follow-up.

Plan-briefer corrections (2026-10-24, after the panel): `TradePlanV2` has no
ATR field (stored at creation); the extended-hours exit fields are dead
config, so the premarket cancel is new code; the v1 arm replay applies no
frictions (one adverse tick on the reclaim fill instead); the fold-train
winner reads the whole window once; confluence plans have no hold cap;
`population_split` needs re-priced/added labels and `evaluate` a
SKIPPED-fails opt-in; no point-in-time earnings date exists; builder line
numbers fixed. New cancel and reclaim-instruction events need entries in
`NOTICE_EVENTS`, `instructions._CANCEL_LEADS`/`_BUILDERS`,
`PLAN_EVENT_KINDS`, `execution_embeds`, `_TRANSITION_LOG`, the `_on_event`
discard tuple and the `follow_notify` tables (`instructions._cancel_why`
would KeyError otherwise); `_on_event`, `poll` and `_step_active` are
already at or over complexity 15, so the plan splits before it adds.
