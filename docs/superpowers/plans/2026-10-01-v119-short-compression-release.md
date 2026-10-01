# First bearish compression release SHORT — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle. Steps use `- [ ]` for tracking; read the spec with the task.

**Goal:** Test a first bearish squeeze release as a 3–10-session share-SHORT with a next-session resting trigger, lower-support target, and hard tenth-session close.
**Architecture:** Refactor the existing squeeze calculation into one causal series, register a masked bearish-only 2w strategy, and construct the same pending plan in live scan and replay. Add a live hard-cap notice and paper close that agree with replay, then run a separate pre-registered evidence funnel for broad and isolated weakness.
**Tech Stack:** Python 3.11, pandas, existing strategy/plan/scan/notification modules, pytest.
**Spec:** `docs/superpowers/specs/2026-10-01-v119-short-compression-release-design.md`
**Bump:** bot patch (only if the new alert and exit lifecycle ship)
**Edge:** expectancy
**Progress:** planning complete; implementation, broker-workflow confirmation and measurement not started.

## Global constraints

- This is a new compression-state → first-release event. Do not reopen the closed Break & Retest, v104 or v113 arms; do not grid the frozen squeeze defaults.
- `1w` stays masked. The signal registers only for `2w` and uses a 10-regular-session cap from fill; an earlier stop/target can close it sooner.
- BB window 20, BB standard deviations 2, KC EMA 20, ATR period 10, KC multiplier 1.5, volume multiple 1.5. Preceding completed bar is squeezed; release bar is the first outside state and closes below the preceding lower BB.
- Bearish stop entry is one valid minimum stock tick below release low, valid the next regular session only; stop above release high with existing structural ATR buffer; one confirmed lower-support target; no ATR target fallback, scale-out, BE move or runner.
- Known earnings within the next 10 sessions and missing/stale earnings calendars exclude a signal. SPY/stock/sector completed dates must align. Broad and isolated are separate arms.
- No broker order placement. Alert says `CHECK BORROW AVAILABILITY`. Live trade instructions stay masked until evidence, live/replay parity, notification delivery and broker MOC/protective-order workflow gates clear. This plan does not authorize production SSH/deploy.
- Invoke `edge-module`, `no-lookahead`, `alert-surface`, `schema-change` (if adding persisted fields), and `backtest-gate` at their boundaries. Read `architecture.md`, `known-traps.md`, `backtest-methodology.md`, and `code-complexity.md` before editing. Functions changed stay below CC 15.
- Each task uses its narrow test file and a focused commit. The full Python suite runs once in the final plan task.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/core/market/volatility.py` | Pure squeeze state/release series, shared by confidence and entry. |
| `swingbot/core/market/short_entries.py`, `strategy_types.py` | Bearish-only entry frame, registration and masked 2w cell. |
| `swingbot/core/scanning/strategy_pass.py` | Completed-bar/mode/earnings pre-entry gate and dedup. |
| `swingbot/core/planning/short_builders.py`, `builders.py`, `params.py` | Resting trigger, structural stop, lower-support target, whole-position shape. |
| `swingbot/core/planning/exit_sim.py`, `plan_manager.py` | Fill-aware gap/risk behavior and 10-session close parity. |
| `swingbot/core/market/session.py` or existing calendar provider | Official session dates, early closes and the notification deadline. |
| `swingbot/core/scanning/alert_embeds.py`, lifecycle delivery | Actionable pending, cancel, time-due and confirmed-close text. |
| `scripts/backtest/measure_compression_short.py` | Separate mode cohorts and sequential gate evidence. |

The named new helpers below are design interfaces, not claims that they already exist. The implementer confirms existing call sites with narrow reads before editing. Keep the production modules' current interfaces for other strategies.

## Review focus

1. A forming release bar or later extra bar must never create an earlier signal; Task V119-1/2 test truncation.
2. A gap through the sell stop can exceed the planned-loss cap; Task V119-5 tests cancellation in live and replay.
3. A missing earnings calendar and a report on session 10 must both exclude entry; Task V119-4 tests them.
4. A holiday, early close or restart near session 10 must not miss or duplicate the MOC instruction; Task V119-7 tests these.
5. A stop/target after a staged MOC must instruct broker cancel/verify and never claim that an order was auto-cancelled; Task V119-8 tests this.

## Parallelisation

- **Phase 1:** Sequential V119-1 → V119-2 → V119-3; each consumes the preceding series/strategy contract.
- **Phase 2:** V119-4 and V119-5 can prepare tests in disjoint files, but plan construction consumes the entry gate and must integrate serially. V119-6 freezes the common fill/session semantics before V119-7.
- **Phase 3:** V119-8 follows the event contract, V119-9 the complete live/replay path, V119-10 the frozen measurement record. The funnel is serial. V119-11 is the sole final full-suite task.

# Phase 1 — Causal signal

### Task V119-1: Behavior-preserving squeeze series

**Files:** Modify `swingbot/core/market/volatility.py`; create `tests/market/test_squeeze_release_series.py`.

**Interfaces:** `squeeze_release_series(df) -> DataFrame` with boolean `is_squeeze`, `squeeze_off`, `bullish_breakout`, `bearish_breakout`, `volume_confirmed`, `bullish_confirmed`, `bearish_confirmed`. Existing `squeeze_breakout_confirmation(df, direction)` reads the appropriate directional last row and retains all current dict keys and values.

- [ ] Before changing production code, capture witness cases for short history, zero/NaN prior volume, continuing squeeze, first release and a later outside bar; compare the current scalar result to frozen expected dictionaries. Add a truncation assertion: series at index `t` equals the series from `df.iloc[:t+1]` at `t`.

  ```python
  for cut in range(25, len(frame) + 1):
      prefix = squeeze_release_series(frame.iloc[:cut]).iloc[-1]
      full = squeeze_release_series(frame).iloc[cut - 1]
      assert bool(prefix["bearish_confirmed"]) == bool(full["bearish_confirmed"])
  assert squeeze_breakout_confirmation(frame, "bullish") == bullish_witness
  assert squeeze_breakout_confirmation(frame, "bearish") == bearish_witness
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/market/test_squeeze_release_series.py`; the witness cases should pass and the missing new series API should fail.
- [ ] Compute BB/KC once as vector series. Set `squeeze_off = is_squeeze.shift(1).fillna(False) & ~is_squeeze`; `bearish_breakout = Close < lower_bb.shift(1)` and `bullish_breakout = Close > upper_bb.shift(1)`; `volume_confirmed = Volume >= 1.5 * Volume.rolling(20).mean().shift(1)`. Combine each direction's three booleans with `.fillna(False)`. Preserve the old scalar `width_pct` rounding and short-frame behavior in its wrapper.
- [ ] Rerun the narrow file plus the existing volatility/confidence file found with `git ls-files tests/market tests/scanning | Select-String 'volatility|confidence'`; run radon on `volatility.py`; commit behavior-preserving refactor separately from the new signal.

### Task V119-2: Bearish-only first-release entry

**Files:** Modify `swingbot/core/market/short_entries.py`, `strategy_types.py`; create `tests/market/test_compression_short_entry.py`.

**Interfaces:** `COMPRESSION_SHORT = "First Bearish Compression Release"`; `compression_short_frame(df, horizon_key, params=None) -> DataFrame` uses `squeeze_release_series`, `FRAMES`, and `_register()`. Register a masked `STRATEGY_GATES[COMPRESSION_SHORT] = {"directions": ()}`; `2w` only after admission.

- [ ] Test a first release fires bearish on `2w`, never bullish or on `1w`/other horizons, and a second outside bar does not fire. Add full-frame versus truncated-frame equality and an RTH current-bar exclusion through `strategy_pass.completed_frame()`.

  ```python
  assert bool(compression_short_frame(release_frame, "2w")["signal"].iloc[-1])
  assert not entries_for(COMPRESSION_SHORT, release_frame, "2w")[1].any()  # masked
  assert not entries_for(COMPRESSION_SHORT, release_frame, "1w")[1].any()
  assert not bool(compression_short_frame(outside_again, "2w")["signal"].iloc[-1])
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/market/test_compression_short_entry.py`; expect missing strategy failure.
- [ ] Add the name to `SHORT_STRATEGIES`, one `FRAMES` entry and one mask. Return a frame with `signal`, release `level`, prospective `stop`, `target_a`/`target_b` fields as required by the existing frame contract, but leave final geometry to Task V119-5. Do not count the squeeze event again in confidence/quality.
- [ ] Run the narrow file and `tests/market/test_short_entries.py`; run radon; commit.

### Task V119-3: Distinct broad and isolated regime arms

**Files:** Create `swingbot/core/scanning/compression_context.py`, `tests/scanning/test_compression_context.py`; modify `strategy_pass.py` only to call the new pure context selector when the masked strategy is being shadow-evaluated.

**Interfaces:** `compression_mode(stock, spy, sector, *, now, spy_regime) -> tuple[str | None, str | None]`, returning `("broad", None)`, `("isolated", None)` or `(None, rejection_reason)`. Reuse v118's aligned reference helper if it exists; otherwise implement the same contract locally without making v119 depend on the v118 feature flag.

- [ ] Test broad bearish SPY, isolated nonbearish SPY with stock trailing 63-session return below sector ETF, stock stronger than sector, missing SPY, missing sector mapping/ETF and mismatched last completed date. Assert a ticker cannot be in both arms.

  ```python
  assert compression_mode(weak_stock, falling_spy, sector, now=asof,
                          spy_regime=bearish)[0] == "broad"
  assert compression_mode(weak_stock, rising_spy, sector, now=asof,
                          spy_regime=neutral)[0] == "isolated"
  assert compression_mode(weak_stock, stale_spy, sector, now=asof,
                          spy_regime=neutral) == (None, "unaligned_spy")
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_compression_context.py`; expect failure.
- [ ] Use `completed_frame()` for all three frames, align on common exchange dates, and apply the SPY trend already used by the scan. Store mode and bar date in the shadow candidate; do not turn on a live strategy cell.
- [ ] Run the narrow file and `tests/scanning/test_strategy_pass_frame.py`; commit.

# Phase 2 — Executable paper plan

### Task V119-4: Fresh earnings exclusion

**Files:** Modify `swingbot/core/scanning/strategy_pass.py` and the earnings adapter under `swingbot/core/market/events.py` only as needed; create `tests/scanning/test_compression_earnings_gate.py`.

**Interfaces:** `earnings_clear_for_ten_sessions(ticker, decision_date, calendar_snapshot) -> tuple[bool, str]`. Reasons include `earnings_within_window`, `earnings_unknown` and `earnings_stale`; the boolean is never true for an unverified calendar. Historical replay uses point-in-time event knowledge, not a future report list exposed retroactively.

- [ ] Test reports on session 1 and 10 reject, session 11 can pass, no scheduled report with a fresh calendar passes, missing/stale calendar rejects, ETF/nonreporting assumptions never silently substitute for a stock calendar. Count exclusions by mode.

  ```python
  assert earnings_clear_for_ten_sessions("ABC", signal_day, missing) == (False, "earnings_unknown")
  assert earnings_clear_for_ten_sessions("ABC", signal_day, report_on_tenth) == (False, "earnings_within_window")
  assert earnings_clear_for_ten_sessions("ABC", signal_day, report_on_eleventh)[0]
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_compression_earnings_gate.py`; expect failure.
- [ ] Build the gate from the existing cached earnings source and `SessionCalendar` session counting. Keep it before plan construction and keep the existing `exit_before` behavior of other strategies untouched. If historical calendar-as-known data is unavailable, mark that cohort unmeasurable and stop before selection backtests.
- [ ] Run the narrow file plus `tests/market/test_earnings_calendar.py`; commit.

### Task V119-5: Resting trigger, stop and one support target

**Files:** Modify `swingbot/core/planning/short_builders.py`, `builders.py`, `params.py`; create `tests/planning/test_compression_short_plan.py`.

**Interfaces:** `compression_structure(df, index, *, trigger, atr_val, horizon_key, level_map, scan_params) -> tuple[stop, target] | None`; `build_strategy_plan()` passes the explicit trigger through structure selection, `apply_level_lifecycle()` and `_geometry_ok()` for this strategy only. `PLAN_SHAPES[COMPRESSION_SHORT]` has `entry_type="stop_entry"`, `expiry_bars=1`, `tp1_fraction=1.0`, `breakeven_trigger_fraction=1.0`.

- [ ] Test trigger one US stock tick below release low, never signal close; stop above release high plus current ATR buffer, reject when beyond `stop_ceiling`; nearest *confirmed* lower support inside current RR band selected; no lower support yields no plan; target closes 100% with `tp2 is None`. Test trigger-based risk/RR differs from close-based risk/RR on a crafted bar.

  ```python
  plan = build_strategy_plan(release_frame, len(release_frame) - 1,
                             ticker="ABC", strategy=COMPRESSION_SHORT,
                             horizon_key="2w", direction="bearish", level_map=levels)
  assert plan.trigger_price == release_low - 0.01
  assert plan.stop_loss > release_high
  assert plan.tp1 < plan.trigger_price
  assert (plan.tp1_fraction, plan.tp2, plan.expiry_bars, plan.hold_cap_bars) == (1.0, None, 1, 10)
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_compression_short_plan.py`; expect failure.
- [ ] Use the existing minimum tick helper if present, otherwise define a strategy-scoped $0.01 tick for the screened US shares and test penny rounding. Use `_swing_lows_below()`/`select_structural_target()` without `atr_target_candidates()`. Keep the exact release-bar stop; a failed ceiling rejects, never clamps. Carry trigger into the plan and set `hold_cap_bars=10` on this strategy's plan only. If that field is already persisted, use it; if changing persistence, invoke `schema-change`.
- [ ] Run the narrow file plus `tests/planning/test_build_strategy_plan.py`, radon on changed files, and commit.

### Task V119-6: Next-session fill, expiry and gap-risk parity

**Files:** Modify `swingbot/core/planning/exit_sim.py`, `plan_manager.py` only where the current shared implementation diverges; create `tests/planning/test_compression_short_fill.py`.

**Interfaces:** For signal bar `t`, only session `t+1` can fill. A bearish gap below trigger fills at the observed/open price (worse for the seller), then `planned_loss_pct(fill, stop)` is checked before ACTIVE. Rejected gap records `cancelled_risk_cap` in both paths.

- [ ] Test no same-bar fill; trigger touch in next session; no touch then `cancelled_expired`; gap below trigger at open; gap that breaches the cap; market closure/holiday between signal and next session. Assert replay/live entry price, status and cancellation reason agree.

  ```python
  assert replay_gap.entry_price == live_gap.entry_price == next_open
  assert replay_bad_gap.reason == live_bad_gap.reason == "cancelled_risk_cap"
  assert replay_unfilled.status == live_unfilled.status == "CANCELLED"
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_compression_short_fill.py`; expect at least one parity failure.
- [ ] Reuse `pending_expired`, `trigger_hit` and `fill_price` in replay and `_step_pending` in live. Add a risk-cap check in replay for this strategy if absent; do not loosen live's existing cap. Make expiry count sessions rather than raw calendar days and emit explicit cancel-resting-order event on expiry.
- [ ] Run narrow file plus `tests/planning/test_exit_sim_entry.py` and `tests/planning/test_plan_manager_pending.py`; commit.

### Task V119-7: Ten-session paper close and advance notice

**Files:** Modify `swingbot/core/planning/plan_manager.py`, `exit_sim.py`; create `swingbot/core/planning/time_exit.py`, `tests/planning/test_compression_time_exit.py`. Modify the calendar provider only if it lacks early-close times.

**Interfaces:** `tenth_session(fill_session, calendar) -> date`; `notice_deadline(close_time_et) -> datetime` is 15:30 ET on a standard 16:00 close and at least 20 minutes before an early close; `time_exit_due(plan, now, calendar)` is idempotent. Official close causes one `closed` event with reason `time_exit` and paper closing-auction price.

- [ ] Test fill on Friday before a Monday holiday, exact tenth-session date, early-close notice deadline, repeated polls/restart, prior stop/target, ACTIVE and persisted PARTIAL, and missing official-close price. No price must mean an explicit pending/failure notice, never a fabricated fill. Pin replay bar index convention against live `bar_count_fn`: session of fill is session 1 and the tenth exit bar is fill index + 9.

  ```python
  assert tenth_session(friday_fill, calendar) == calendar.sessions(friday_fill, end)[9]
  assert notice_deadline(standard_close).time().isoformat() == "15:30:00"
  assert replay_exit_index == fill_index + 9
  assert len([e for e in repeated_events if e.kind == "time_exit_due"]) == 1
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py`; expect failure.
- [ ] Add the smallest shared calendar/session helper. Check stop/target before the time close; on session 10 queue one due notice and at official close persist one terminal leg via `_persist_terminal`. Use existing `pending_notice`/ack retry mechanism. For a legacy PARTIAL instance, close its remaining fraction without creating a second target or reopening. Leave other strategies' advisory `time_stop_days` unchanged.
- [ ] Run the narrow file plus `tests/planning/test_plan_manager_active.py` and `tests/planning/test_exit_sim_hold_cap.py`; run radon and commit.

# Phase 3 — Alerts and evidence

### Task V119-8: Resting-order and MOC instructions in every channel

**Files:** Modify `swingbot/core/scanning/alert_embeds.py` and lifecycle delivery module discovered by `rg -n "pending_notice|ack_notified|cancelled_expired|time_exit_due" swingbot bot.py`; create `tests/scanning/test_compression_instructions.py`.

**Interfaces:** Render one common instruction payload for `pending`, `cancelled_expired`, `cancelled_risk_cap`, `time_exit_due`, `time_exit_closed` and `cancel_or_verify_moc`. All messages include ticker, direction, shares if known, trigger/stop/target/expiry or cover time, and `CHECK BORROW AVAILABILITY` at entry.

- [ ] Test Discord and simple/email/push parity for the pending trade numbers; expiry and risk-cap events explicitly say cancel the resting sell stop; MOC due says buy to cover by the stated closing auction; a stop/target after due says cancel/verify staged MOC. Simulate send failure and retry/ack once, with no duplicate terminal close. Do not assert any broker order was automatically cancelled.

  ```python
  assert "CHECK BORROW AVAILABILITY" in pending_discord
  assert "cancel" in expired_instruction.lower()
  assert "buy to cover" in due_instruction.lower()
  assert "cancel/verify" in after_stop_instruction.lower()
  assert delivered_closed_notices == 1
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_compression_instructions.py`; expect failure.
- [ ] Route plan events through existing durable notice queue, not an ephemeral scan log. Use the plan's actual fill/stop/target and exchange session calendar. Keep live trade-instruction emission masked until the broker confirms the protective-order/MOC linkage or cancellation process; shadow mode may emit research records only.
- [ ] Run narrow file plus `tests/scanning/test_lifecycle_push.py` and `tests/scanning/test_notifier_clamped_stop.py`; commit.

### Task V119-9: Live/replay reachability and mask tests

**Files:** Create `tests/backtesting/test_compression_reachability.py`; modify `swingbot/core/scanning/strategy_pass.py` and the strategy replay adapter only if the test exposes a gap.

**Interfaces:** Both paths call `build_strategy_plan()` on the same completed bar; results agree on mode, trigger, expiry, stop, lower-support target, earnings exclusion and tenth-session close. `STRATEGY_GATES` remains masked; `STRATEGY_ALERTS_MODE` remains globally off by default.

- [ ] Construct one synthetic full path that compresses, releases, triggers next session, misses target/stop, and closes at session 10. Construct a second that expires and a third with earnings. Assert live scan and replay payloads agree and no legacy `1w` or closed v104/v113 cell is admitted.

  ```python
  assert live_plan.trigger_price == replay_plan.trigger_price
  assert live_plan.stop_loss == replay_plan.stop_loss
  assert live_plan.tp1 == replay_plan.tp1
  assert live_exit.reason == replay_exit.reason == "time_exit"
  assert live_exit.session == replay_exit.session == tenth_session(fill_day, calendar)
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_compression_reachability.py`; expect failure until every seam is wired.
- [ ] Connect shadow strategy evaluation to the shared constructor, calendar and exit policy. Keep the live mask closed. Record scan-level reasons for no support, over-cap stop, calendar unknown, expiry and gap-risk cancellation, split by broad/isolated mode.
- [ ] Run the narrow file plus `tests/scanning/test_strategy_pass_signals.py`; commit.

### Task V119-10: Pre-registration and serial measurement

**Files:** Create `scripts/backtest/measure_compression_short.py`, `tests/backtesting/test_measure_compression_short.py`, and a v119 pre-registration/result record under the repo's active results convention.

**Interfaces:** The harness emits distinct broad and isolated rows, one per point-in-time eligible signal, with excluded candidates and exit reason. It uses the live constructor and the same replay hold cap, not a parallel formula. Record borrow-fee break-even sensitivity, not fictitious locate history.

- [ ] Test historical PIT membership, no future earnings knowledge, no same-bar entry, support-only target, tenth close and per-mode exclusion totals on a tiny deterministic fixture.

  ```python
  assert all(row.entry_date > row.signal_date for row in measured.trades)
  assert {row.mode for row in measured.trades} <= {"broad", "isolated"}
  assert measured.exclusions["earnings_unknown"] == 1
  assert measured.trades[0].exit_reason == "time_exit"
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_measure_compression_short.py`; expect failure.
- [ ] Freeze both arms' population, dates, fees/slippage, entry/exit/expiry, calendar freshness, selection rule and applicable strategy/harvest gate **before** reading outcomes. Confirm the acceptance instrument can represent this new signal and changed exit geometry; if not, write a pre-registered amendment and stop before selection runs.
- [ ] Invoke `backtest-gate` before every run or interpretation. Stage −1 → MDE → TRAIN plateau → folds → single VALIDATION/holdout shot only as each prior gate permits. Do not rerun closed v104/v113 rows. Report each arm independently; no pooled success hides an arm failure. Keep the strategy masked unless evidence, parity, delivery and broker workflow all pass. Commit frozen record and any measured result without claiming a pass from reachability alone.

### Task V119-11: Full-suite verification

**Files:** No new feature files; fix only failures attributable to this plan and their narrow tests.

- [ ] Run `python scripts/dev/testrun.py full` once (or dispatch the `test-runner` role). Green requires `0 failed`, `0 xfailed`.
- [ ] Resolve failures by the named narrow file, check radon for every changed function, and review completed-bar timing, live/replay fill parity, time-exit notice delivery and broker-order wording.
- [ ] Close the plan as implemented or no-lift per document lifecycle. Only a shipped alert/exit lifecycle receives the spec's bot patch, resolved from then-current `VERSION.json`; no release number is fixed in this plan.
