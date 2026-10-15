# v147 block-point enumeration

**Plan:** [`2026-10-09-v147-gate-counterfactual_0-index.md`](../plans/2026-10-09-v147-gate-counterfactual_0-index.md)
**Verified at:** 8f3338c9 on 2026-10-14

Every place a candidate is thrown away in the live scan or the TRAIN replays,
and whether v147 records it. Covered = one of the three gates in the spec
(RS, plan rejected, compression/earnings).

## Covered

| # | Path | File:line | Site | `gate` / `reason` | Population | Hook task |
|---|---|---|---|---|---|---|
| L1 | strategy | `strategy_pass.py:254` | `_emit_signal` -> `_rs_blocked` (`result.rs_blocked += 1`, return at 255-256) | `rs` / `rs_blocked` | live | V147-10 |
| L2 | strategy | `strategy_pass.py:260` | `_emit_signal` -> `_compression_context` reject, `_count_compression_reject` at 262 | `compression` / decide reason (`earnings_*` included) | live | V147-10 |
| L3 | confluence | `scan_run.py:664` | `_sync_run_scan` RS block under `config.RS_GATE`; drop at 671-675 (`rs_blocked += 1`, `funnel.record_item(item, "rs", "rs_blocked")`, `continue`); a `None` RS value passes `rs_available=False` and is `exempt`, not `block` | `rs` / `rs_blocked` | live | V147-10 |
| L4 | confluence | `scan_run.py:695` | `_sync_run_scan` `plan_v2_rejected` drop, only when `config.PLAN_ENGINE_V2 == "on"` (under `shadow` the rejected plan is not dropped, so not a block); drop at 697-700. The reason set reaching this site is the four `analyze.attach_plan_v2` reasons (`analyze.py:389` `no_qualifying_target` or `stop_beyond_confluence_ceiling`, `:399` `risk_cap`, `:406` `risk_sizing`); only `no_qualifying_target` and `risk_cap` are v147 (see O11/O12) | `plan_rejected` / `no_qualifying_target`, `risk_cap` | live | V147-10 |
| L5 | short lane | `short_run.py:152` | `_qualified_items` sees `Rejected(stage="rs")` from `qualify.py:125-126` | `rs` / `rs_blocked` | live | V147-10 |
| L6 | short lane | `short_run.py:152` | `_qualified_items` sees `Rejected(stage="plan")` from `qualify.py:128-129` (after `_revoke`) | `plan_rejected` / reason (same four-reason set as L4) | live | V147-10 |
| T1 | TRAIN strategy | `arms/strategy_engine.py:232` | `_candidate_plan` compression reject (`_compression_stamp` reason, decide reasons only; counted at 234-235) | `compression` | TRAIN, in-sample | V147-6 |
| T2 | TRAIN confluence | `backtest_scenarios.py:181` | `replay_scenarios` `plan is None` (`continue`). The replay does not distinguish `no_qualifying_target` from `stop_beyond_confluence_ceiling`; live uses `analyze._no_plan_reason` | `plan_rejected` / `no_qualifying_target` | TRAIN | V147-5 |
| T3 | TRAIN confluence | `backtest_scenarios.py:237` | shadow in `_replay_ticker` after `simulate_exit`; the plan-time cap check has no replay counterpart (live: `analyze.py:391-399`), so this is a record-only shadow | `plan_rejected` / `risk_cap` | TRAIN shadow, over-cap | V147-5 |

## Out of scope

| # | Path | File:line | Site | Why not recorded |
|---|---|---|---|---|
| O1 | strategy | `strategy_pass.py:266-270` | `plan is None` -> `_count_plan_none` (for the compression strategy it counts `compression_rejection_reason`, a builder-geometry answer, not a `decide_compression_entry` reason) | the constructor found no geometry; not one of the three gates; nothing to simulate. NOTE: the counter lands in `compression_reasons`, so it is tallied beside L2 but is not recorded by v147 |
| O2 | strategy | `strategy_pass.py:275` | `risk_sizing_ok(plan)` false (`sizing_blocked`) | v104 configuration fail-closed guard, not a quality gate |
| O3 | all | `strategy_pass.py:251`, `scan_run.py:748`, `scan_run.py:802-832` | dedup (`already_emitted`, `dedup.dedup_scan_items`), existing-trade / reversal cooldown | "already have this trade" |
| O4 | strategy / confluence | `strategy_pass.py:257`, `analyze.py:644`, `backtest_scenarios.py:163`, `arms/strategy_engine.py:260` | pullback dry-up (`_dryup_blocked`, `_apply_pullback_dryup`, `_dryup_kept`, `gates.pullback_dryup_blocks`) | inactive since v122 (its scope knob defaults off, so the filter is a no-op) |
| O5 | confluence / short | `short_funnel.py:24`, `short_funnel.py:96` | requirement rejects (`_REQUIREMENT_STAGE`, geometry / confidence stages) | out by the spec |
| O6 | confluence / short | `scan_run.py:1076-1078`, `short_run.py:223-237`, `short_run.py:288`, `edge/portfolio_state.py:44` | heat cap, correlated-cluster cap, kill switch, `_stamp_risk_flags` | flagged (`kill_switch_blocked`, heat state), never dropped (size 0) |
| O7 | strategy | `strategy_pass.py:284-287` | masked strategies (`_goes_live` false -> `stored_only`) | stored, not rejected |
| O8 | TRAIN strategy | `arms/strategy_engine.py:242-246`, `:219-220` | plan None (`_count_plan_none`), `_skipped` not_triggered | O1's twin; fill-time cancels are taken-arm `no-fill` rows |
| O9 | confluence | `analyze.py:54`, `analyze.py:893` | dead-cat-bounce veto (`veto_bullish_for`, passed as `block_bullish` to `levels.build_scenarios`) | the bullish scenario is never built inside `_scan_one` (a `map_tickers` worker); no candidate exists to record |
| O10 | all | `market/entry_filters.py:114-124`, `:153` | regime gate (`apply_regime_gate`, `REGIME_GATES_ENABLED`; `scan_run.py:477-499` only stamps context) | DROPS, but on the entry-signal series before any candidate exists (`bull & ok` zeroes the bar), so there is no plan to simulate; `REGIME_ALLOW` is empty by default so it is inert. Not one of the three gates |
| O11 | confluence / strategy | `analyze.py:633-637` (`_apply_headroom`, call at `:918`), `backtest_scenarios.py:119-122` (call `:164`), `strategy_pass.py:235-241` (call `:271`), `arms/strategy_engine.py:267-270` | v135 `headroom` reject | a v135 gate, not one of the three; applied before the plan exists (confluence) or after it (strategy) and never reaches L4/L6/T2; `cell_key` -> `"other"`, never pooled into `risk_cap` |
| O12 | confluence | `analyze.py:351-355`, `:389` (`stop_beyond_confluence_ceiling`), `analyze.py:406` (`risk_sizing`) | v139 `stop_beyond_confluence_ceiling` / `risk_sizing` rejections inside `attach_plan_v2` | v139 gates, not one of the three. They surface through `item.plan_v2_rejected`, so L4/L6 WOULD see them as `plan_rejected`; the hook must store the reason verbatim, never pool them into `risk_cap` (`cell_key` -> `"other"`). T2 cannot tell `stop_beyond_confluence_ceiling` from `no_qualifying_target` in the replay |
| O13 | strategy | `strategy_pass.py:169-202` | `compression_shadow_record` (masked compression strategy, `_count_compression_reject` at the reject) | shadow evaluation only: never a stored plan, alert or trade; the masked cell is not a live candidate |
| O14 | short lane / confluence | `qualify.py:117-118`, `:120-121`, `:130-131` | `Rejected(stage="direction" / "confirmation" / "trade_decision")` | not one of the three gates (not_bearish, awaiting confirmation, existing trade) |
| O15 | TRAIN strategy | `arms/strategy_engine.py:169-170` | `_compression_stamp` returns `not_pit_member` before the decision | research universe mask, not the gate |
| O16 | all | `qualify.py:111` call sites: `outlook_run.py:166`, `scan_replay.py:220`, `short_run.py:152` | `qualify_short_item` is also called by outlook and replay | the live hook belongs in `short_run._qualified_items` only; `arms/short_universe_engine.py` imports the gates through the same function and is never hooked |
