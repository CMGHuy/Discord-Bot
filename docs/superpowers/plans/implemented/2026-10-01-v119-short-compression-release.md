# First bearish compression release SHORT — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle. Steps use `- [ ]` for tracking; read the spec with the task.

**Goal:** Test a first bearish squeeze release as a 3–10-session share-SHORT with a next-session resting trigger, lower-support target, and hard tenth-session close.
**Architecture:** Refactor the existing squeeze calculation into one causal series, register a masked bearish-only 2w strategy, and construct the same pending plan in live scan and replay. Add a live hard-cap notice and paper close that agree with replay, then run a separate pre-registered evidence funnel for broad and isolated weakness.
**Tech Stack:** Python 3.11, pandas, existing strategy/plan/scan/notification modules, pytest.
**Spec:** `docs/superpowers/specs/2026-10-01-v119-short-compression-release-design.md`
**Bump:** none (the strategy stays masked; no alert or exit lifecycle ships live)
**Edge:** expectancy
**Progress:** implemented and merged 2026-10-04 (masked, 2w only). Both arms recorded `unmeasurable` (no as-of earnings archive; isolated arm also lacks dated sector history and sector ETFs); see docs/superpowers/results/2026-10-04-v119-compression-short-result.md. Unmask gates open: measurement data, acceptance amendment A1-A3 instrument, universe decision, production official auction_close_fn.

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
| `swingbot/core/scanning/strategy_pass.py`, `swingbot/core/backtesting/arms/strategy_engine.py` | Identical completed-bar/mode/earnings pre-entry decision in live and stamped research. |
| `swingbot/core/planning/short_builders.py`, `builders.py`, `params.py` | Resting trigger, structural stop, lower-support target, whole-position shape. |
| `swingbot/core/planning/exit_sim.py`, `plan_manager.py`, `plan_types.py` | Fill-aware gap/risk behavior, durable time-exit notices and 10-session close parity. |
| `swingbot/core/market/session.py` or existing calendar provider | Official session dates, early closes and the notification deadline. |
| `swingbot/core/scanning/alert_embeds.py`, lifecycle delivery | Actionable pending, cancel, time-due and confirmed-close text. |
| `scripts/backtest/measure_arms.py`, `swingbot/core/backtesting/arms/reachability.py` | Stamped baseline/component research arm and separate mode cohorts. |

The named new helpers below are design interfaces, not claims that they already exist. `backtesting/backtest.py:_trade_plan_at()` still constructs a parallel plan, whereas `arms/strategy_engine.py` calls the live `build_strategy_plan()` on truncated bars; the stamped arm must use the latter. `events.get_earnings_datetimes()` returns `[]` for both no report and fetch failure, so it cannot satisfy an unknown-is-excluded gate alone. `targets.select_structural_target()` synthesizes a capped target when a support is beyond max RR, contrary to this spec's literal support target; this strategy needs a support-only selector. Keep other strategies' current interfaces and behavior.

## Review focus

1. A forming release bar or later extra bar must never create an earlier signal; Task V119-1/2 test truncation.
2. A gap through the sell stop can exceed the planned-loss cap; Task V119-6 tests cancellation in live and replay.
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

**Interfaces:** `squeeze_release_series(df, bb_window=20, num_std=2.0, kc_ema_period=20, kc_atr_period=10, kc_multiplier=1.5, volume_multiple=1.5) -> DataFrame` with boolean `is_squeeze`, `squeeze_off`, `bullish_breakout`, `bearish_breakout`, `volume_confirmed`, `bullish_confirmed`, `bearish_confirmed`. Existing `squeeze_breakout_confirmation(df, direction, ...)` passes its arguments through, reads the directional last row and retains all current dict keys and values.

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

**Implementation detail.** Do not change the scalar function's return contract while extracting a vectorized series. Its current short-history branch returns all false/zero; its bullish and bearish results are both witness tests. The series uses only rolling windows and `shift(1)` and returns false for bars lacking history. Use the current `bollinger_bands()` and `keltner_channel()` helpers, not a second indicator implementation.

```python
# market/volatility.py -- core of the new helper.
def squeeze_release_series(df: pd.DataFrame, bb_window=20, num_std=2.0,
                           kc_ema_period=20, kc_atr_period=10,
                           kc_multiplier=1.5, volume_multiple=1.5) -> pd.DataFrame:
    bb = bollinger_bands(df, window=bb_window, num_std=num_std)
    kc = keltner_channel(df, ema_period=kc_ema_period,
                         atr_period=kc_atr_period, multiplier=kc_multiplier)
    squeezed = (bb["upper"] < kc["upper"]) & (bb["lower"] > kc["lower"])
    first_release = squeezed.shift(1).fillna(False) & ~squeezed
    prior_volume = df["Volume"].rolling(bb_window).mean().shift(1)
    enough_volume = (prior_volume.gt(0) &
                     df["Volume"].ge(volume_multiple * prior_volume)).fillna(False)
    bearish = (df["Close"] < bb["lower"].shift(1)).fillna(False)
    bullish = (df["Close"] > bb["upper"].shift(1)).fillna(False)
    enough_history = pd.Series(range(len(df)), index=df.index).ge(
        max(bb_window, kc_ema_period, kc_atr_period) + 4)
    return pd.DataFrame({
        "is_squeeze": squeezed.fillna(False), "squeeze_off": first_release,
        "volume_confirmed": enough_volume,
        "bearish_breakout": bearish, "bullish_breakout": bullish,
        "bearish_confirmed": (first_release & enough_volume & bearish & enough_history).fillna(False),
        "bullish_confirmed": (first_release & enough_volume & bullish & enough_history).fillna(False),
    }, index=df.index)
```

The snippet uses the verified `keltner_channel(ema_period, atr_period, multiplier)` names. Wrap the old scalar using the final series row, preserving `width_pct` rounding, custom arguments and short-frame semantics. A confidence-snapshot test must compare the complete old dict before/after this refactor, not just `confirmed`. Commit `volatility.py` and `tests/market/test_squeeze_release_series.py` before touching strategy registration.

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

**Implementation detail.** The entry frame exposes a bar-level signal even while `entries_for()` masks live admission. Do not add the strategy to `backtest.ALL_STRATEGIES` (which currently contains the legacy eleven and no v104 shorts); Task V119-10 opts its research arm in explicitly. No `1w` cell is admitted.

```python
# market/short_entries.py
COMPRESSION_SHORT = "First Bearish Compression Release"

def compression_short_frame(df, horizon_key, params=None):
    frame = _empty(df)
    if horizon_key != "2w":
        return frame
    release = squeeze_release_series(df)
    frame["signal"] = release["bearish_confirmed"].fillna(False).astype(bool)
    frame["level"] = df["Close"].astype(float)
    frame["stop"] = df["High"] + STOP_ATR * atr(df, 14)
    return frame

FRAMES[COMPRESSION_SHORT] = compression_short_frame
# _register() installs the usual _short_only wrapper in ENTRY_FUNCS.
```

Add `COMPRESSION_SHORT` to `SHORT_STRATEGIES`, with `STRATEGY_GATES[COMPRESSION_SHORT] = {"directions": ()}`. Import the existing ATR indicator in `short_entries.py`. Test `compression_short_frame(frame.iloc[:i+1]).iloc[-1]` equals the full-frame row at `i`, while `entries_for(COMPRESSION_SHORT, frame, "2w")` remains false without a scoped research override. Run radon for the changed modules and commit the entry/registry/test files.

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

**Implementation detail.** Reuse v118's `aligned_window()`/dated sector history when available, but do not require v118's feature flag or current static sector map. `get_market_regime(spy).trend` is the existing SPY EMA200 result and needs at least 220 bars. Only the isolated arm needs a sector frame; both need stock/SPY on the same completed date. The signal date, market mode and sector provenance are returned to live and research from one helper.

```python
# scanning/compression_context.py
def compression_mode(stock, spy, sector, *, now, spy_regime):
    aligned = aligned_window(stock, spy, sector if spy_regime.trend != "bearish" else None, now)
    if aligned is None:
        return None, "unaligned_or_short_history"
    stock_ok, spy_ok, sector_ok = aligned
    if spy_regime.trend == "bearish":
        return "broad", None
    if sector_ok is None:
        return None, "missing_sector"
    if return_63(stock_ok) < return_63(sector_ok):
        return "isolated", None
    return None, "not_sector_laggard"
```

The live caller passes only `strategy_pass.completed_frame()` data and the shared SPY regime result. The research caller reconstructs the same as-of frames and dated sector mapping; it never reads today's `universe.sector_map("sp500")` for a historical decision. Add a test where changing tomorrow's sector frame cannot change today's mode. Commit context module, strategy-pass adapter and tests.

# Phase 2 — Executable paper plan

### Task V119-4: Fresh earnings exclusion

**Files:** Modify `swingbot/core/scanning/strategy_pass.py` and the earnings adapter under `swingbot/core/market/events.py` only as needed; create `tests/scanning/test_compression_earnings_gate.py`.

**Interfaces:** `earnings_clear_for_ten_sessions(ticker, decision_at, calendar_snapshot, calendar) -> tuple[bool, str]`. Reasons include `earnings_within_window`, `earnings_unknown` and `earnings_stale`; the boolean is never true for an unverified calendar. Historical replay uses event knowledge observed by the exact decision timestamp, not a future report list exposed retroactively.

- [ ] Test reports on session 1 and 10 reject, session 11 can pass, no scheduled report with a fresh calendar passes, missing/stale calendar rejects, ETF/nonreporting assumptions never silently substitute for a stock calendar. Count exclusions by mode.

  ```python
  assert earnings_clear_for_ten_sessions("ABC", signal_at, missing, calendar) == (False, "earnings_unknown")
  assert earnings_clear_for_ten_sessions("ABC", signal_at, report_on_tenth, calendar) == (False, "earnings_within_window")
  assert earnings_clear_for_ten_sessions("ABC", signal_at, report_on_eleventh, calendar)[0]
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/scanning/test_compression_earnings_gate.py`; expect failure.
- [ ] Build the gate from the existing cached earnings source and `SessionCalendar` session counting. Keep it before plan construction and keep the existing `exit_before` behavior of other strategies untouched. If historical calendar-as-known data is unavailable, mark that cohort unmeasurable and stop before selection backtests.
- [ ] Run the narrow file plus `tests/market/test_earnings_calendar.py`; commit.

**Implementation detail.** The current `events.get_earnings_datetimes()` returns an empty list after a failed Yahoo fetch and after a successful no-report response, so do not treat `[]` as a clean calendar. Add a typed snapshot API that preserves status, observation time and source; leave the old display API unchanged. Freeze the maximum freshness at five completed sessions, and compare report **reaction session** (before-open report same day, after-close report next session) to sessions 1–10 after the signal. Return a reason, not a fabricated `False` from a missing row.

```python
# market/events.py -- new adapter; existing get_earnings_datetimes stays intact.
@dataclass(frozen=True)
class EarningsSnapshot:
    observed_at: datetime
    reports: tuple[datetime, ...]
    query_ok: bool
    source: str

# scanning/compression_context.py -- the gate consumes that typed snapshot.
def earnings_clear_for_ten_sessions(ticker, decision_at, snapshot, calendar):
    if snapshot is None or not snapshot.query_ok:
        return False, "earnings_unknown"
    if snapshot.observed_at > decision_at or snapshot_age_sessions(snapshot, decision_at.date(), calendar) > 5:
        return False, "earnings_stale"
    next_ten = ten_sessions_after_signal(decision_at.date(), calendar)
    if any(reaction_session(report, calendar) in next_ten for report in snapshot.reports):
        return False, "earnings_within_window"
    return True, "clear"
```

Normalize `observed_at`, `decision_at` and report timestamps to timezone-aware UTC before comparing them; convert only for exchange-session assignment. Reject naive or ambiguous timestamps. Historical replay needs an observed-as-of earnings snapshot archive. `earnings_context.attach()`'s future event positions are unsuitable for this pre-entry gate. If no archive provides observations as known on the signal date, this strategy is unmeasurable and must stop before MDE/TRAIN rather than look ahead. Test a before-open report on session 10, an after-close report whose reaction is session 11, a fresh successful empty response, a network failure and a naive timestamp. Commit the snapshot adapter and its tests separately from a future data acquisition.

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
- [ ] Use a strategy-scoped $0.01 tick for the screened US shares and test penny rounding. Use confirmed lower supports without `atr_target_candidates()` or `select_structural_target()`'s synthetic max-RR cap. Keep the exact release-bar stop; a failed ceiling rejects, never clamps. Carry trigger into the plan and set existing `hold_cap_bars=10` on this strategy's plan only.
- [ ] Run the narrow file plus `tests/planning/test_build_strategy_plan.py`, radon on changed files, and commit.

**Implementation detail.** `build_strategy_plan()` currently uses signal `Close` for `_BranchInputs.close`, `apply_level_lifecycle()`, `_geometry_ok()` and `TradePlanV2.trigger_price`. Introduce one strategy-scoped entry-reference helper and pass its result to all four, leaving other strategies' `close` unchanged. `hold_cap_bars` already exists on `TradePlanV2`; no schema field is needed for that cap. Build the level map from `df.iloc[:index+1]` at signal time even though `EXIT_V2_PARAMS[COMPRESSION_SHORT]["tp2"]` is false; the existing `StrategyEngine` only supplies a map when TP2 is wanted.

```python
# planning/builders.py
def strategy_entry_reference(df, index, strategy):
    if strategy != COMPRESSION_SHORT:
        return float(df["Close"].iloc[index])
    return round(float(df["Low"].iloc[index]) - 0.01, 2)

# planning/short_builders.py -- exact support target, no synthetic cap.
def compression_structure(df, index, *, trigger, atr_val, horizon_key, scan_params):
    stop = float(df["High"].iloc[index]) + STRUCTURE_BUFFER_ATR * atr_val
    if not _valid_stop(COMPRESSION_SHORT, horizon_key, trigger, stop):
        return None
    window = df.iloc[:index + 1]
    supports, _ = build_level_map(window, HORIZONS[horizon_key], trigger)
    risk = stop - trigger
    prices = (float(level.price) for level in supports)
    valid = [price for price in prices if price < trigger and
             scan_params.min_risk_reward_ratio <= (trigger - price) / risk <=
             scan_params.max_risk_reward_ratio]
    return (stop, max(valid)) if valid else None
```

`max(valid)` is the nearest qualifying support below a SHORT entry. `select_structural_target()` is deliberately **not** used: when a real support is beyond max RR it returns a synthetic capped price, which violates the single-support target contract. Add an as-of test by appending tomorrow's large swing low and confirming today's chosen support stays unchanged. Set `PLAN_SHAPES[COMPRESSION_SHORT]` to stop-entry/one-bar/whole-position/no-BE, `EXIT_V2_PARAMS[COMPRESSION_SHORT]["tp2"] = False`, `plan.hold_cap_bars = 10`, `plan.tp2 = None`. Invoke `reward_floor.clears()` on trigger/target. Commit builder/params/test files explicitly.

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

**Implementation detail.** In `exit_sim.simulate_exit()` the current stop-entry loop gets a worst-of fill but does **not** recheck planned loss or call `_fill_bar_exit()`; the live `_step_pending()` does check the risk cap. Add a strategy-specific common policy helper so existing stop-entry populations remain byte-identical. A replay gap above the hard cap is an excluded `not_triggered` row with `cancel_reason="risk_cap"`; never score it as a filled win/loss. The fill bar itself may hit the stop after entry, and conservative stop-first ordering applies.

```python
# planning/exit_sim.py -- inside the stop_entry trigger branch.
entry_price = fill_price(plan, float(open_[j]))
if plan.strategy == COMPRESSION_SHORT:
    if planned_loss_pct(entry_price, plan.stop_loss) > plan_stop_ceiling(plan):
        return _not_triggered(cancel_reason="risk_cap")
    early = _fill_bar_exit(df, j, entry_price, plan)
    if early is not None:
        return early
return _walk_for(plan, scale_out)(df, j, entry_price, plan, max_holding_days)
```

Add optional `cancel_reason: str | None = None` to `ExitResult` **after** its existing required fields, preserving existing constructors. In live `_step_pending()`, keep its worst-of observed price and cap; for this strategy expire at the official close of the only eligible next session, not at the first poll the following morning. If no regular-session price crosses the trigger, queue `cancelled_expired` with a resting-order cancellation instruction at that close. `SessionCalendar.next_session(signal_day)` determines the eligible date, so a holiday does not use a raw one-calendar-day offset. Test on the fill bar both `High >= stop` and `Low <= target`; stop wins. Commit simulator, manager and one narrow test file; never weaken other strategies' gap behavior.

### Task V119-7: Ten-session paper close and advance notice

**Files:** Modify `swingbot/core/planning/plan_manager.py`, `exit_sim.py`; create `swingbot/core/planning/time_exit.py`, `tests/planning/test_compression_time_exit.py`. Modify the calendar provider only if it lacks early-close times.

**Interfaces:** `tenth_session(fill_session, calendar) -> date`; `notice_deadline(close_time_et) -> datetime` is 15:30 ET on a standard 16:00 close and at least 20 minutes before an early close; `time_exit_due(plan, now, calendar)` is idempotent. Official close causes one `closed` event with reason `time_exit` and paper closing-auction price.

- [ ] Test fill on Friday before a Monday holiday, exact tenth-session date, early-close notice deadline, repeated polls/restart, prior stop/target, ACTIVE and persisted PARTIAL, and missing official-close price. No price must mean an explicit pending/failure notice, never a fabricated fill. Pin replay bar index convention against live `bar_count_fn`: session of fill is session 1 and the tenth exit bar is fill index + 9.

  ```python
  assert tenth_session(friday_fill, calendar) == calendar.sessions(friday_fill, end)[9]
  assert notice_deadline(standard_close).time().isoformat() == "15:30:00"
  assert replay_exit_index == fill_index + 9
  assert len([e for e in repeated_events if e.transition == "time_exit_due"]) == 1
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py`; expect failure.
- [ ] Add the smallest shared calendar/session helper. Check stop/target before the time close; on session 10 queue one due notice and at official close persist one terminal leg via `_persist_terminal`. Extend the durable notice queue because one `pending_notice` slot cannot hold due and terminal notices at once. For a legacy PARTIAL instance, close its remaining fraction without creating a second target or reopening. Leave other strategies' advisory `time_stop_days` unchanged.
- [ ] Run the narrow file plus `tests/planning/test_plan_manager_active.py` and `tests/planning/test_exit_sim_hold_cap.py`; run radon and commit.

**Implementation detail.** `SessionCalendar` knows trading **dates** but not early closing times. Add a dated exchange-close schedule in `market/session.py` or a focused sibling loader, with one timezone-aware close datetime per covered date. Source the schedule from the published exchange calendar and test regular, holiday and early-close fixtures; when the current live date is missing, fail closed with an urgent `time_exit_unresolved` notice rather than guessing 16:00 ET. The notification deadline is `min(15:30 ET, official_close - 20 minutes)`; a missed deadline sends immediately with `LATE` in the instruction.

```python
# planning/time_exit.py
def tenth_session(fill_day: date, calendar: SessionCalendar) -> date:
    days = calendar.sessions(fill_day, calendar.last)
    if not days or days[0] != fill_day or len(days) < 10:
        raise ValueError("fill session outside calendar coverage")
    return days[9]  # fill session is session 1

def notice_deadline(close_at_et: datetime) -> datetime:
    standard = close_at_et.replace(hour=15, minute=30)
    return min(standard, close_at_et - timedelta(minutes=20))
```

The replay cap is currently `entry_index + max_holding_days`, so `hold_cap_bars=10` would close on the **eleventh** position session. For this strategy only, the single-leg walker ends at `entry_index + hold_cap_bars - 1`; stop and target retain priority on that bar, and an unclosed position books `timeout` with leg reason `time_exit`, price basis `daily_close_proxy`. Do not change other strategies' bar counts. In live manager, determine fill date from the `ACTIVE` status-history transition, not `created_at`. At `now >= notice_deadline` on the tenth session, emit `time_exit_due` once with cover size and auction time. At the verified official close, use an injected `closing_auction_price_fn(ticker, day) -> (price, source, asof) | None`; only a source explicitly identified as official can persist a paper close through `_persist_terminal`. A generic last quote or daily `Close` is insufficient. If unavailable, mark the exit unresolved, keep it out of new entry/exit logic, and resend an actionable notice until the price is reconciled. A legacy PARTIAL plan closes its remaining fraction, with its prior leg untouched.

The current `pending_notice` slot stores only one transition, so a due notice could be overwritten by a terminal close during a delivery outage. Add `pending_time_notices: list[dict]` and `time_exit_due_date: str | None` with defaults to `TradePlanV2`; keep old `pending_notice` behavior for other strategies. Each time notice has stable id `plan_id + transition + session_date`, payload, queued UTC time and ack flag. `_feed_bookkeeping()` excludes the new time events from its single-slot `pending_notice` assignment and appends them to the new list. `resend_notices()` emits unacked time notices without the ordinary five-day drop; `ack_notified()` removes only the matching id. Invoke `schema-change` before changing the store's serialized read/write path, and test old plan JSON still loads with defaults. Do not close a plan merely because a notice was sent.

```python
# plan_manager.py -- new method, called only after existing stop/target checks.
def _compression_time_events(self, plan, now) -> list[PlanEvent]:
    fill_day = fill_day_from_history(plan.status_history)
    due_day = tenth_session(fill_day, nyse_calendar())
    if now_et(now).date() != due_day:
        return []
    close_at = official_close_at(due_day)  # None when schedule is unavailable
    if close_at is None:
        event = self._queue_time_notice_once(plan, "time_exit_unresolved", due_day)
        return [event] if event is not None else []
    events = []
    if now_et(now) >= notice_deadline(close_at) and plan.time_exit_due_date != due_day.isoformat():
        event = self._queue_time_notice_once(plan, "time_exit_due", due_day)
        if event is not None:
            events.append(event)
        plan.time_exit_due_date = due_day.isoformat()
        self.store.update(plan)
    if now_et(now) < close_at:
        return events
    observed = self.auction_close_fn(plan.ticker, due_day)
    if observed is None or observed.source != "official_auction":
        event = self._queue_time_notice_once(plan, "time_exit_unresolved", due_day)
        if event is not None:
            events.append(event)
        return events
    events.append(self._close_time_exit(plan, observed.price, now))
    return events
```

This task defines `fill_day_from_history(history) -> date` from the first `ACTIVE` transition, `official_close_at(day) -> datetime | None` from the dated schedule, `_queue_time_notice_once()` using `pending_time_notices` stable ids, and `_close_time_exit()` using `_persist_terminal`. Inject `auction_close_fn` into `PlanManager` with a fail-closed default that returns `None`. The new method is called **after** existing stop/target checks in `_step_active()` and `_step_partial()`, never as their replacement. When an official price is unavailable, `time_exit_unresolved` remains actionable and the plan's `time_exit_due_date` prevents duplicate MOC staging; further live ticks cannot fabricate a close or reopen the plan. Add tests for a missed 15:30 poll, restart after due but before close, due/terminal queued simultaneously, early close, no official price, and a stop after MOC was staged. Commit calendar, policy, plan type/manager, simulator and tests as an isolated lifecycle unit.

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

**Implementation detail.** Strategy alerts render through `alert_embeds.build_strategy_alert_embed()` and `build_strategy_simple_embed()`. Lifecycle instructions pass through `presentation/instructions.instruction_for()` → `scanning/execution_embeds.build_instruction_embed()` → `lifecycle_embeds.notify_plan_events()`. Add one strategy-scoped format helper in `presentation/short_notice.py` that consumes the persisted plan and `PlanEvent.detail`; do not format prices independently in each channel. The initial alert shows sell-stop trigger, expiry session/date, structural stop, whole-position support target, mode, completed-bar date and literal `CHECK BORROW AVAILABILITY`. A due notice contains the remaining shares, buy-to-cover MOC instruction, official close and broker check. A stop/target after due adds `CANCEL/VERIFY STAGED MOC` even when the paper plan has already closed.

```python
# planning/plan_manager.py -- extend the durable feed classifications.
NOTICE_EVENTS = NOTICE_EVENTS | frozenset({
    "time_exit_due", "time_exit_unresolved", "cancel_or_verify_moc",
})

# presentation/short_notice.py -- shared words, numbers come from plan.
def compression_instruction(plan, event) -> str:
    if event.transition == "time_exit_due":
        return (f"BUY TO COVER {event.detail['shares']} shares by MOC "
                f"{event.detail['close_at_et']} · confirm broker order status")
    if event.transition == "cancel_or_verify_moc":
        return "CANCEL/VERIFY STAGED MOC after stop or target fill"
    return entry_or_close_instruction(plan, event)
```

`entry_or_close_instruction()` is a new focused helper in the same file for pending/fill/expiry/risk-cap/close cases; tests pin each exact verb. `notify_plan_events()` must return a `Delivery` for the stable time-notice id only after feed or fallback-history delivery succeeds. On failure, keep that notice in `pending_time_notices` for `run_notice_sweep()` to retry. Test two outstanding notices survive a restart and are acknowledged independently. Do not claim broker OCO/MOC cancellation: this bot has no broker API. Commit presentation, lifecycle, manager and tests; invoke `alert-surface` before editing.

### Task V119-9: Live/replay reachability and mask tests

**Files:** Create `tests/backtesting/test_compression_reachability.py`; modify `swingbot/core/scanning/strategy_pass.py` and the strategy replay adapter only if the test exposes a gap.

**Interfaces:** Both paths call `build_strategy_plan()` on the same completed bar; results agree on mode, trigger, expiry, stop, lower-support target, earnings exclusion and tenth-session close. `STRATEGY_GATES` remains masked; `STRATEGY_ALERTS_MODE` remains globally off by default.

- [ ] Construct one synthetic full path that compresses, releases, triggers next session, misses target/stop, and closes at session 10. Construct a second that expires and a third with earnings. Assert live scan and replay payloads agree and no legacy `1w` or closed v104/v113 cell is admitted.

  ```python
  assert live_plan.trigger_price == replay_plan.trigger_price
  assert live_plan.stop_loss == replay_plan.stop_loss
  assert live_plan.tp1 == replay_plan.tp1
  assert live_exit.detail["reason"] == replay_exit.legs[-1]["reason"] == "time_exit"
  assert live_exit.detail["exit_session_date"] == str(tenth_session(fill_day, calendar))
  assert frame.index[replay_exit.exit_index].date() == tenth_session(fill_day, calendar)
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_compression_reachability.py`; expect failure until every seam is wired.
- [ ] Connect shadow strategy evaluation to the shared constructor, calendar and exit policy. Keep the live mask closed. Record scan-level reasons for no support, over-cap stop, calendar unknown, expiry and gap-risk cancellation, split by broad/isolated mode.
- [ ] Run the narrow file plus `tests/scanning/test_strategy_pass_signals.py`; commit.

**Implementation detail.** The same pure pre-entry decision function must be called before `build_strategy_plan()` in both `strategy_pass.py` and `arms/strategy_engine.py`. It consumes a completed stock frame, SPY frame, dated sector frame, typed earnings snapshot, decision timestamp and mode allowlist; it returns `(mode, reason)` or rejects. The live shadow evaluator calls the raw `compression_short_frame()` while `STRATEGY_GATES` stays masked, builds a plan for audit, and writes a shadow record without adding an alert tuple, paper trade or order instruction. The live on path additionally requires the existing global `STRATEGY_ALERTS_MODE` admission and this strategy's own `("bearish", "2w")` cell.

```python
# scanning/strategy_pass.py -- dedicated shadow path, no mask bypass in live alerts.
def compression_shadow_plan(frame, *, ticker, spy, sector, earnings, now):
    completed = completed_frame(frame, now)
    if completed.empty or not bool(compression_short_frame(completed, "2w")["signal"].iloc[-1]):
        return None
    mode, reason = compression_candidate_decision(
        completed, spy, sector, earnings, now=now)
    if mode is None:
        return None
    return build_strategy_plan(completed, len(completed) - 1, ticker=ticker,
                               strategy=COMPRESSION_SHORT, horizon_key="2w",
                               direction="bearish")
```

The production helper must also record the rejection reason and pass the same structural level path as research. In `StrategyEngine.iter_trades()` use a scoped `entry_filters.gate_override(COMPRESSION_SHORT, {"cells": {("bearish", "2w")}})` only for the stamped research knob; never mutate the global mask for a live scan. `StrategyEngine` already calls `build_strategy_plan()` on `df.iloc[:index+1]`, so use that path rather than `backtest._trade_plan_at()`/`_bt_plan()` (which still uses the signal close). Load SPY, as-of sector and historical earnings snapshots through an explicit offline context provider before each candidate decision. Test the live/replay plan fields and exact exit bar, plus a no-context failure and a shadow raw signal that produces zero live alerts. Assert confidence scoring does not award the squeeze event twice for this strategy. Commit the parity wiring and narrow test.

### Task V119-10: Pre-registration and serial measurement

**Files:** Modify `swingbot/core/backtesting/arms/strategy_engine.py`, `reachability.py`, `swingbot/config.py`; create `tests/backtesting/test_measure_compression_short.py` and a v119 pre-registration/result record under `docs/superpowers/results/`. Use the existing `scripts/backtest/measure_arms.py`, not a bespoke measurement script.

**Interfaces:** The harness emits distinct broad and isolated rows, one per point-in-time eligible signal, with excluded candidates and exit reason. It uses the live constructor and the same replay hold cap, not a parallel formula. Record borrow-fee break-even sensitivity, not fictitious locate history.

- [ ] Test historical PIT membership, no future earnings knowledge, no same-bar entry, support-only target, tenth close and per-mode exclusion totals on a tiny deterministic fixture. Keep supplemental diagnostics distinct from stamped `ArmTrade` rows, whose schema has no mode or signal-date field.

  ```python
  assert all(row["entry_date"] > row["signal_date"] for row in measured.signal_diagnostics)
  assert measured.mode in {"broad", "isolated"}
  assert measured.diagnostics["earnings_unknown"] == 1
  assert measured.exit_reasons["time_exit"] == 1
  ```
- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_measure_compression_short.py`; expect failure.
- [ ] Freeze both arms' population, dates, fees/slippage, entry/exit/expiry, calendar freshness and selection rule **before** reading outcomes. Name two required admission checks: the existing per-strategy `2w` badge thresholds and the standard v72 additive feature gate for incremental alerts. Confirm its stamped arms and all applicable clauses, including geometry, faithfully represent this new signal and plan; if not, write a pre-registered acceptance amendment and stop before selection runs. The harvest gate applies only to a separately proposed paired exit-only study on identical entries.
- [ ] Invoke `backtest-gate` before every run or interpretation. Stage −1 → MDE → TRAIN plateau → folds → single VALIDATION/holdout shot only as each prior gate permits. Do not rerun closed v104/v113 rows. Report each arm independently; no pooled success hides an arm failure. Keep the strategy masked unless evidence, parity, delivery and broker workflow all pass. Commit frozen record and any measured result without claiming a pass from reachability alone.

**Implementation detail.** Add a research-only schema field `COMPRESSION_SHORT_RESEARCH_MODE` with `off|broad|isolated`, default `off`, and classify it reachable **only after** the stamped StrategyEngine test changes outcomes on a pilot fixture. Under `apply_knobs()` the component arm includes `COMPRESSION_SHORT` in `StrategyEngine` while the baseline does not. The scoped gate override from V119-9 exposes only `("bearish", "2w")` inside that research engine. The live `STRATEGY_GATES` remains masked. Both modes get separate pre-registered arm files and independent decisions; neither can be rescued by pooling.

```python
# arms/strategy_engine.py -- inside run_ticker/iter_trades setup.
mode = config.COMPRESSION_SHORT_RESEARCH_MODE
strategies = list(self.strategies)
if mode != "off" and COMPRESSION_SHORT not in strategies:
    strategies.append(COMPRESSION_SHORT)
for strategy in strategies:
    scope = (gate_override(COMPRESSION_SHORT, {"cells": {("bearish", "2w")}})
             if strategy == COMPRESSION_SHORT else nullcontext())
    with scope:
        yield from self.iter_trades_for_strategy(ticker, df, strategy, mode, context)
```

Import `nullcontext` from `contextlib`. Split the existing loop into `iter_trades_for_strategy()` in a behavior-preserving commit before adding the new strategy branch; the code above names the new seam and de-duplicates a name already present in `self.strategies`. The override is scoped to compression so existing strategies retain their current gates. `context` is an explicit offline loader of cached SPY, PIT sector mapping and observed-as-of earnings snapshots; missing inputs reject with recorded reasons. `ArmTrade` has no mode field, so one `--knob COMPRESSION_SHORT_RESEARCH_MODE=broad` run and one `...=isolated` run produce the two separate cohorts without altering acceptance's schema or stratum math. A research arm is stamped through `measure_arms.py` and checked by `validate_component.py`; no hand-authored JSON. The daily close used for research time exits is labelled `daily_close_proxy` in the supplemental exclusion/exit report; it does not prove the live official auction-price feed.

Freeze the rule and datasets in `docs/superpowers/results/2026-10-01-v119-compression-short-preregistration.md` and commit it first. Then invoke `backtest-gate` and run `python scripts/backtest/measure_arms.py --stage pilot --knob COMPRESSION_SHORT_RESEARCH_MODE=broad --preregistration docs/superpowers/results/2026-10-01-v119-compression-short-preregistration.md --out docs/superpowers/results/2026-10-01-v119-broad-pilot-arms.json` for Stage −1, and the same command with `isolated`/`isolated-pilot-arms.json` for the second arm. Use the documented stage-specific windows and full-universe stamp for later stages. If dated sector or earnings observations are absent, record `unmeasurable` and stop before MDE; do not backfill today's facts into 2020–2023. For each mode, require the `2w` strategy badge (`win_rate >= 50`, `expectancy_r > 0`, TRAIN `N >= 30`, VALIDATION `N >= 15`, scratches plus timeouts <= 50% of closed trades) and the pre-registered additive v72 feature gate before default-on admission. Do not substitute the v92 harvest gate for an entry-population change or waive a geometry failure because the new plan differs from existing ones.

### Task V119-11: Full-suite verification

**Files:** No new feature files; fix only failures attributable to this plan and their narrow tests.

- [ ] Run `python scripts/dev/testrun.py full` once (or dispatch the `test-runner` role). Green requires `0 failed`, `0 xfailed`.
- [ ] Resolve failures by the named narrow file, check radon for every changed function, and review completed-bar timing, live/replay fill parity, time-exit notice delivery and broker-order wording.
- [ ] Close the plan as implemented or no-lift per document lifecycle. Only a shipped alert/exit lifecycle receives the spec's bot patch, resolved from then-current `VERSION.json`; no release number is fixed in this plan.
