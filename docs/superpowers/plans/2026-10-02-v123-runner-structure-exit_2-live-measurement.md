# Structure-aware runner exit — implementation plan, part 2 (Phases 3–5)

> Part of v123. Header, global constraints, file map, spec reconciliations, review focus and `## Parallelisation` live in `2026-10-02-v123-runner-structure-exit_0-index.md`; read it and the spec (`docs/superpowers/specs/2026-10-02-v123-runner-structure-exit-design.md`) with any task here.

# Phase 3 — Live

### Task V123-6: Behaviour-preserving split of `_step_partial`

**Files:** Modify `swingbot/core/planning/plan_manager.py`.

**Interfaces:**
- Produces: `PlanManager._maybe_suggest_pyramid(plan, price) -> list[PlanEvent]`, `PlanManager._ratchet_chandelier(plan, price, is_bull, entry) -> None`, `PlanManager._entered_at(plan) -> str | None`. `_step_partial` and `_days_since_entry` have unchanged behaviour.

`_step_partial` is CC 19 (legacy). This commit only moves code, so the existing tests are the witness.

- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`, then the same for `test_plan_manager_runner_session.py`, `test_plan_manager_feed.py` and `test_plan_manager_active.py`. Record that all pass before the change.
- [ ] **Refactor.** Move the pyramiding block (lines 689–694) and the chandelier block (lines 719–733) verbatim into the two methods below, and make `_days_since_entry` read through `_entered_at`.

```python
    def _maybe_suggest_pyramid(self, plan, price) -> list[PlanEvent]:
        """Edge E38 suggestion, flag-gated OFF, at most once per plan."""
        if not config.PYRAMIDING_ENABLED or plan.pyramid_add is not None:
            return []
        add = maybe_pyramid(plan, price)
        if add is None:
            return []
        plan.pyramid_add = add
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "pyramid_add", dict(add))]

    def _ratchet_chandelier(self, plan, price, is_bull, entry) -> None:
        """Live chandelier ratchet off the extreme tick since TP1 (Task 66)."""
        if self.atr_fn is None:
            return
        extreme = plan.runner_high_close
        extreme = price if extreme is None else (max(extreme, price) if is_bull
                                                 else min(extreme, price))
        if extreme == plan.runner_high_close:
            return
        plan.runner_high_close = extreme
        atr_val = float(self.atr_fn(plan.ticker))
        trail = chandelier_stop(extreme, atr_val, plan.trail_atr_mult, plan.direction)
        floor = (plan.working_stop if plan.working_stop is not None
                 else runner_floor(entry, plan.tp1))
        new_stop = max(floor, trail) if is_bull else min(floor, trail)
        if new_stop != plan.working_stop:
            plan.working_stop = new_stop
        self.store.update(plan)

    def _entered_at(self, plan) -> str | None:
        """The `at` of the transition that moved this plan to ACTIVE, or None."""
        return next((h.get("at") for h in plan.status_history
                     if h.get("status") == PlanStatus.ACTIVE), None)
```

In `_step_partial`, keep the existing comment blocks and replace the moved code with `pyramid = self._maybe_suggest_pyramid(plan, price)` / `if pyramid: return pyramid` and a final `self._ratchet_chandelier(plan, price, is_bull, entry)` / `return []`. `_days_since_entry` becomes `entered_at = self._entered_at(plan)` plus its existing None check and `bar_count_fn` call.

- [ ] Rerun the four files and expect identical PASS. Run `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py`: `_step_partial` is now below 15 and the new methods are under 15. Commit: `refactor(v123): extract pyramid/chandelier helpers from _step_partial`.

### Task V123-7: Completed-daily-bar structure step in the live manager

**Files:** Modify `swingbot/core/planning/plan_manager.py`. Create `tests/planning/test_plan_manager_structure_exit.py`.

**Interfaces:**
- Consumes: `exit_sim.runner_structure_frame`, `runner_structure_step`, `targets._safe_atr_value`, `strategy_pass.completed_frame`, `session.is_regular_session/session_date`, and V123-6's `_entered_at`.
- Produces:
  - Module function `entry_bar_position(frame, entered_at) -> int | None`.
  - Module function `_holding_cap(plan) -> int`.
  - `PlanManager(..., daily_frame_fn=None)`, where `daily_frame_fn` maps a ticker to a daily OHLCV DataFrame.
  - `PlanManager._structure_runner_step(plan, price, now=None) -> list[PlanEvent]`.
  - Close reason `tp1_runner_progress_stall`.
  - INFO log line label `structure trail`.
  - Production `_daily_frame(ticker)`, wired in `_manager()`.

**Rules (Spec reconciliation 1):**
- Evaluate only the last row of `completed_frame(daily_frame_fn(ticker), now)`, once per (plan, completed bar date) in an in-memory map.
- Skip a bar dated on or before `plan.runner_floor_session` (the TP1 bar) and any bar at or past `entry + holding cap`.
- `hl_trail` writes `working_stop` immediately: the tick that first sees bar `j` completed is after `j`'s close, hence "from `j+1`".
- A stall closes the runner at the current price only when `is_regular_session(now)` and `session_date(now)` is after the bar's date. The step runs **before** the stop check, mirroring replay's open-first order.
- Any failure (fetch error, unparseable ACTIVE `at`, no entry bar) returns `[]`.

- [ ] **Write the failing tests.**

```python
# tests/planning/test_plan_manager_structure_exit.py
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, record_transition, runner_floor
from swingbot.core.planning.plan_manager import PlanManager, entry_bar_position
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.structure_fixtures import WARMUP, sawtooth, stall_frame
from tests.planning.test_plan_engine_model import _plan


def at(day, hour):
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)


def partial_plan(df, entered_at=None):
    p = _plan(entry_type="market", horizon_key="2m", trigger_price=100.0, entry_price=100.0,
              stop_loss=95.0, tp1=101.0, tp2=None, trail_atr_mult=50.0)
    entry_day, tp1_day = df.index[WARMUP - 1].date(), df.index[WARMUP].date()
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry",
                      at=entered_at or at(entry_day, 20).isoformat())
    record_transition(p, PlanStatus.PARTIAL, reason="tp1_partial", at=at(tp1_day, 15).isoformat())
    p.legs_realized = [{"fraction": 0.5, "exit_price": 101.0, "r": 0.2, "reason": "tp1"}]
    p.working_stop, p.runner_floor_session = runner_floor(100.0, 101.0), str(tp1_day)
    return p


def manager(df, plan, view):
    store = PlanStore()
    store.add(plan)
    return store, PlanManager(store, FakePriceFeed().get_price,
                              daily_frame_fn=lambda t: df.iloc[:view[0]])


def step(store, mgr, price, now):
    return mgr._step_partial(store.get("p1"), price, now)


def test_entry_bar_position_maps_fill_session():
    df = sawtooth(1)
    assert entry_bar_position(df, at(df.index[59].date(), 20).isoformat()) == 59
    assert entry_bar_position(df, "t0") is None and entry_bar_position(df, None) is None


def test_off_mode_never_fetches(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    df = sawtooth(4)
    store = PlanStore()
    store.add(partial_plan(df))
    mgr = PlanManager(store, FakePriceFeed().get_price,
                      daily_frame_fn=lambda t: pytest.fail("fetched in off mode"))
    assert step(store, mgr, 120.0, at(df.index[-1].date(), 15)) == []


def test_hl_trail_raises_working_stop_once_per_completed_bar(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.0)
    df = sawtooth(4)
    confirm = WARMUP + 9
    view = [confirm + 2]                 # bar confirm+1 is forming during its session
    store, mgr = manager(df, partial_plan(df), view)
    step(store, mgr, float(df["Open"].iloc[confirm + 1]), at(df.index[confirm + 1].date(), 15))
    assert store.get("p1").working_stop == pytest.approx(float(df["Low"].iloc[WARMUP + 6]))


def test_tp1_session_bar_is_not_evaluated(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    df = sawtooth(4)
    view = [WARMUP + 2]                  # completed through the TP1 bar only
    store, mgr = manager(df, partial_plan(df), view)
    step(store, mgr, 102.0, at(df.index[WARMUP + 1].date(), 15))
    assert store.get("p1").working_stop == pytest.approx(runner_floor(100.0, 101.0))


def _stall_bar(df):
    from tests.planning.test_exit_sim_runner_structure import _stall_j
    return _stall_j(df)


def test_stall_waits_for_the_next_regular_session(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "progress_stall")
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.70)
    df = stall_frame()
    j = _stall_bar(df)
    view = [j + 1]                                   # bar j completed (after its close)
    store, mgr = manager(df, partial_plan(df), view)
    assert step(store, mgr, 121.0, at(df.index[j].date(), 22)) == []          # after-hours j
    assert step(store, mgr, 121.0, at(df.index[j + 1].date(), 12)) == []      # premarket j+1
    view[0] = j + 2                                  # session j+1 forming, dropped by completed_frame
    events = step(store, mgr, float(df["Open"].iloc[j + 1]), at(df.index[j + 1].date(), 15))
    assert [e.detail["reason"] for e in events] == ["tp1_runner_progress_stall"]
    assert store.get("p1").status == PlanStatus.CLOSED


def test_restart_rederives_the_stall_without_state(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "progress_stall")
    df = stall_frame()
    j = _stall_bar(df)
    view = [j + 2]
    store, mgr = manager(df, partial_plan(df), view)
    fresh = PlanManager(store, FakePriceFeed().get_price, daily_frame_fn=lambda t: df.iloc[:view[0]])
    events = fresh._step_partial(store.get("p1"), 120.0, at(df.index[j + 1].date(), 15))
    assert [e.detail["reason"] for e in events] == ["tp1_runner_progress_stall"]


@pytest.mark.parametrize("entered", ["t0", None])
def test_legacy_or_failing_inputs_are_skipped(monkeypatch, entered):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    df = sawtooth(4)
    plan = partial_plan(df, entered_at="t0") if entered else partial_plan(df)
    store = PlanStore()
    store.add(plan)

    def frames(ticker):                  # t0: a good frame, unparseable fill time
        if entered is None:              # None: a normal plan whose fetch fails
            raise RuntimeError("yf down")
        return df
    mgr = PlanManager(store, FakePriceFeed().get_price, daily_frame_fn=frames)
    assert step(store, mgr, 120.0, at(df.index[-1].date(), 15)) == []
    assert store.get("p1").working_stop == pytest.approx(runner_floor(100.0, 101.0))
```

- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_plan_manager_structure_exit.py`. Expect failures.
- [ ] **Implement.** Imports: `from swingbot.core.planning.exit_sim import runner_structure_frame, runner_structure_step`, `from swingbot.core.planning.targets import _safe_atr_value`, `from swingbot.core.market.strategy_types import HORIZONS`. Add `daily_frame_fn=None` as the last `__init__` keyword, then `self.daily_frame_fn = daily_frame_fn` (ticker -> daily OHLCV, v123) and `self._structure_seen: dict[str, tuple[str, bool]] = {}`.

```python
def entry_bar_position(frame, entered_at) -> int | None:
    """Position of the fill session's daily bar in `frame` (v123), or None."""
    if entered_at is None:
        return None
    try:
        when = datetime.fromisoformat(str(entered_at))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    fill_day = session_date(when)
    position = sum(day.isoformat() <= fill_day for day in frame.index.date) - 1
    return position if position >= 0 else None


def _holding_cap(plan) -> int:
    """Bars after entry the replay walk covers (simulate_exit's max_holding_days)."""
    cap = HORIZONS[plan.horizon_key]["max_holding_days"]
    hold = getattr(plan, "hold_cap_bars", None)
    return min(cap, int(hold)) if hold is not None else cap


def _daily_frame(ticker):
    from swingbot.core.marketdata.data import get_daily_data
    return get_daily_data(ticker)
```

`PlanManager` methods:

```python
    def _structure_runner_step(self, plan, price, now=None) -> list[PlanEvent]:
        """v123: the runner's structure exit on the last COMPLETED daily bar,
        never a tick. A stall closes at the first regular-session tick after
        the confirming bar -- the live counterpart of replay's Open[j+1]."""
        if config.RUNNER_STRUCTURE_EXIT == "off" or self.daily_frame_fn is None:
            return []
        verdict = self._structure_verdict(plan, now)
        if verdict is None or not verdict[1]:
            return []
        if not is_regular_session(now) or session_date(now) <= verdict[0]:
            return []
        risk = abs(plan.entry_price - plan.stop_loss)
        sign = 1 if plan.direction == "bullish" else -1
        return self._close_runner(plan, price, "tp1_runner_progress_stall", risk, sign)

    def _structure_verdict(self, plan, now) -> tuple[str, bool] | None:
        """(completed bar date, stall fired), evaluated once per completed bar."""
        bar = self._completed_runner_bar(plan, now)
        if bar is None:
            return None
        completed, j, entry_index, bar_date = bar
        cached = self._structure_seen.get(plan.plan_id)
        if cached is not None and cached[0] == bar_date:
            return cached
        verdict = (bar_date, self._apply_structure_bar(plan, completed, j, entry_index))
        self._structure_seen[plan.plan_id] = verdict
        return verdict

    def _completed_runner_bar(self, plan, now):
        from swingbot.core.scanning.strategy_pass import completed_frame
        try:
            completed = completed_frame(self.daily_frame_fn(plan.ticker), now)
        except Exception as exc:
            log.debug("structure exit: daily frame failed for %s: %s", plan.ticker, exc)
            return None
        if completed is None or len(completed) == 0:
            return None
        j = len(completed) - 1
        bar_date = completed.index[j].date().isoformat()
        entry_index = entry_bar_position(completed, self._entered_at(plan))
        if entry_index is None or j <= entry_index or j >= entry_index + _holding_cap(plan):
            return None
        if plan.runner_floor_session is not None and bar_date <= plan.runner_floor_session:
            return None
        return completed, j, entry_index, bar_date

    def _apply_structure_bar(self, plan, completed, j, entry_index) -> bool:
        from swingbot.core.market.indicators import atr
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(plan.entry_price, plan.tp1))
        atr_value = _safe_atr_value(plan.entry_price, float(atr(completed, 14).iloc[j]))
        new_stop, fires = runner_structure_step(
            runner_structure_frame(completed), j, entry_index=entry_index,
            direction=plan.direction, runner_stop=stop, atr_value=atr_value)
        if new_stop != stop:
            plan.working_stop = new_stop
            self.store.update(plan)
            _plan_line("structure trail", plan, new_stop, " reason=structure_trail")
        return fires
```

In `_step_partial`, insert directly after the `risk = ...` line, before `stop = ...`:

```python
        structure = self._structure_runner_step(plan, price, now)
        if structure:
            return structure
```

In `_manager()`, pass `daily_frame_fn=_daily_frame`. Add `"tp1_runner_progress_stall"` to the `PlanEvent.transition` comment's close reasons. **Do not** add it to `_STOPPED_REASONS`: it is not a stop.

- [ ] Rerun the narrow file plus `test_plan_manager_partial.py`, `test_plan_manager_feed.py` and `test_trade_monitor_wiring.py`. Expect PASS. Invoke `no-lookahead` on `_completed_runner_bar` and `_apply_structure_bar`: `completed_frame` drops the forming bar, and the ATR and frame are computed on `completed` only. Run radon: new methods under 15, and `_step_partial` still under 15. Commit: `feat(v123): live completed-bar runner structure exit`.

### Task V123-8: Wording for the stall close

**Files:** Modify `swingbot/core/presentation/instructions.py` and `swingbot/core/scanning/lifecycle_embeds.py`. Extend `tests/presentation/test_instructions.py` and `tests/scanning/test_transition_embeds.py`.

**Interfaces:**
- Consumes: the reason string `tp1_runner_progress_stall` (V123-7).
- Produces: a `_MARKET_EXIT_REASONS` frozenset in `instructions.py` and a `CLOSE_REASON_STYLES["tp1_runner_progress_stall"]` entry.

A stall close has no resting broker order behind it, so the reader must close manually. The instruction is the `CLOSE AT MARKET` verb, not "if your broker order did not fill".

- [ ] Invoke `alert-surface`. **Write the failing tests**, using each file's existing `_event`/plan helpers:

```python
# tests/presentation/test_instructions.py (append)
def test_progress_stall_close_says_close_at_market():
    plan = _partial_plan_for_close()          # reuse the helper the tp1_runner_trail test at line ~236 uses
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_progress_stall",
                                         exit_price=112.0, session="regular"))
    assert i.verb == ins.CLOSE_AT_MARKET
    assert "higher high failed" in i.headline


# tests/scanning/test_transition_embeds.py (append)
def test_progress_stall_close_is_a_win_style():
    from swingbot.core.scanning.lifecycle_embeds import CLOSE_REASON_STYLES
    kind, outcome, phrase = CLOSE_REASON_STYLES["tp1_runner_progress_stall"]
    assert outcome == "win" and "higher high" in phrase
```

Before writing the first test, read lines 225–245 of `tests/presentation/test_instructions.py` and use the same plan construction its `tp1_runner_trail` test uses. `_partial_plan_for_close` above stands for that existing construction; inline it if no named helper exists.

- [ ] Run both files narrowly. Expect FAIL.
- [ ] **Implement.** In `instructions.py`:

```python
#: Closes the bot books with no resting broker order behind them (v123):
#: the reader must act at market, exactly like an extended-hours exit.
_MARKET_EXIT_REASONS = frozenset({"tp1_runner_progress_stall"})
```

Add `"tp1_runner_progress_stall": "higher high failed on cooling range and volume"` to `_EXIT_WORDS`. In `_closed`, change the extended-hours branch condition to `if detail.get("session") == "extended" or detail.get("reason") in _MARKET_EXIT_REASONS:`. Inside it, pick the first line with `_market_close_line(side, exit_price, detail)`:

```python
def _market_close_line(side: dict, exit_price, detail: dict) -> str:
    if detail.get("reason") in _MARKET_EXIT_REASONS:
        return (f"{side['exit']} at market: the runner's {_EXIT_WORDS[detail['reason']]} "
                f"(bot exit @ {_price(exit_price)}); no resting order covers this exit")
    return (f"{side['exit']}: the bot exited on an extended-hours print @ "
            f"{_price(exit_price)}; resting stop orders do not fire outside regular hours")
```

Make the headline `f"CLOSE AT MARKET now — {_EXIT_WORDS[reason]}"` for a market-exit reason, keeping `"CLOSE AT MARKET now"` for extended hours. In `lifecycle_embeds.py`, add `"tp1_runner_progress_stall": (Kind.WIN, "win", "runner exited: higher high failed on cooling volume"),` to `CLOSE_REASON_STYLES`.

- [ ] Rerun both files and expect PASS. Run radon on `_closed` (8 now, at most 10 after). Commit: `feat(v123): close-at-market wording for the progress-stall runner exit`.

### Task V123-9: Replay/live parity

**Files:** Create `tests/backtesting/test_runner_structure_parity.py`.

**Interfaces:**
- Consumes: `_scale_out_exit_walk(..., trace=)` (V123-5), `PlanManager._step_partial` with `daily_frame_fn` (V123-7), and the fixtures.

- [ ] **Write the test.** It replays a fixture through the walk, then drives the manager session by session: on day `k+1`, the ticks are `[Open, Low, Close]` of bar `k+1`, and the frame includes the forming bar `k+1`. With the chandelier neutralised (`trail_atr_mult=50` in replay; `atr_fn=None` live), the stop after each completed bar and the exit session must match.

```python
# tests/backtesting/test_runner_structure_parity.py
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import _scale_out_exit_walk
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.structure_fixtures import WARMUP, sawtooth, sawtooth_closes, stall_frame
from tests.planning.test_exit_sim_runner_structure import _runner_plan
from tests.planning.test_plan_manager_structure_exit import at, manager, partial_plan


def _live(df):
    view = [WARMUP + 2]
    store, mgr = manager(df, partial_plan(df), view)
    stops, exit_day = {}, None
    for k in range(WARMUP + 1, len(df) - 1):
        view[0] = k + 2
        day = df.index[k + 1].date()
        for n, col in enumerate(("Open", "Low", "Close")):
            events = mgr._step_partial(store.get("p1"), float(df[col].iloc[k + 1]), at(day, 15 + n))
            if n == 0:
                stops[k] = store.get("p1").working_stop
            if store.get("p1").status == PlanStatus.CLOSED:
                exit_day = day
                break
        if exit_day is not None:
            break
    return stops, exit_day


@pytest.mark.parametrize("mode,frame", [("hl_trail", "drop"), ("progress_stall", "stall")])
def test_replay_and_live_agree(monkeypatch, mode, frame):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", mode)
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.25)
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.70)
    df = stall_frame() if frame == "stall" else sawtooth(4, tail=(sawtooth_closes(4)[-1] - 2.0,))
    trace = []
    replay = _scale_out_exit_walk(df, WARMUP - 1, 100.0, _runner_plan(), 60, trace=trace)
    stops, exit_day = _live(df)
    for j, stop in trace:
        if j in stops:
            assert stops[j] == pytest.approx(stop), f"stop after bar {j}"
    assert exit_day == df.index[replay.exit_index].date()
```

- [ ] Run `python scripts/dev/testrun.py file tests/backtesting/test_runner_structure_parity.py`. Expect PASS. A failure is a real divergence: fix the live side, never the test. Commit: `test(v123): replay/live parity for both runner structure arms`.

# Phase 4 — Instruments

### Task V123-10: Reachability

**Files:** Modify `swingbot/core/backtesting/arms/reachability.py` and `tests/test_runner_structure_knobs.py`. Create `tests/backtesting/test_runner_structure_reach.py`.

- [ ] **Write the failing test.** Run the stamped engines on the v74 fixture: each arm at its most active grid value must change at least one outcome or R. Then flip the knob test's expectation to `REACHABLE`.

```python
# tests/backtesting/test_runner_structure_reach.py
import pytest

from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.backtesting.arms.pairing import changed_outcomes
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")


def _arm(delta):
    return [t for ticker, frame in load_v74_fixture().items()
            for t in run_arm(ticker, frame, ("confluence", "strategy"), ("4w", "3m"), WINDOW, delta)]


@pytest.mark.slow
@pytest.mark.parametrize("delta", [{"RUNNER_STRUCTURE_EXIT": "hl_trail", "RUNNER_HL_TRAIL_ATR_BUFFER": 0.0},
                                   {"RUNNER_STRUCTURE_EXIT": "progress_stall", "RUNNER_STALL_RANGE_MAX": 1.0}])
def test_structure_exit_changes_replayed_trades(delta):
    assert changed_outcomes(_arm({}), _arm(delta)) > 0


def test_registered_reachable():
    for attr in ("RUNNER_STRUCTURE_EXIT", "RUNNER_HL_TRAIL_ATR_BUFFER", "RUNNER_STALL_RANGE_MAX"):
        assert reach.classify(attr) == reach.REACHABLE
```

- [ ] Run it narrowly. Expect `test_registered_reachable` to FAIL. **If `test_structure_exit_changes_replayed_trades` also fails** for an arm, the v74 fixture never reaches that rule: record `fixture_observable=False` with the measured reason, as the ADAPTIVE row does, and delete that parametrize case. Coverage stays with V123-5's tests.
- [ ] **Implement.** Replace the three `_outside(_V123)` rows. `"RUNNER_STRUCTURE_EXIT": Reach(REACHABLE, "Post-TP1 runner rule in simulate_exit's scale-out walk (exit_sim.runner_structure_step); both engines simulate scale_out=True.", CS)`. The buffer and range rows are `Reach(REACHABLE, _V123_PARAM, CS)`, with `_V123_PARAM = "Only active under its RUNNER_STRUCTURE_EXIT mode; a lone perturbation at mode off is inert by design."`. Delete `_V123`. In `tests/test_runner_structure_knobs.py`, delete `test_unwired_knobs_are_refused_by_the_producer`.
- [ ] Rerun the narrow file, `tests/backtesting/arms/test_reachability.py`, `tests/backtesting/test_knob_observability.py` and `tests/test_runner_structure_knobs.py`. Commit: `feat(v123): runner structure knobs reachable in replay`.

### Task V123-11: Harvest gate for the walkforward and validation stages, and the ΔExpR permutation

**Files:** Modify `swingbot/core/backtesting/backtest_wf.py`, `swingbot/core/backtesting/acceptance_harvest.py`, `scripts/backtest/validate_component.py` and `scripts/backtest/permutation_test.py`. Create `tests/backtesting/test_harvest_stage_gates.py`.

**Interfaces:**
- Produces in `backtest_wf`: `HARVEST_GATE_MIN_POSITIVE_FOLDS = 2`, `HARVEST_GATE_MAX_FOLD_LOSS_R = 0.02`, `HARVEST_GATE_MIN_TP1_PER_FOLD = 30`, and `gate_expectancy_harvest(result: dict) -> str`. Each fold row is `{"test_years", "delta_expectancy_r", "n_tp1"}`.
- Produces in `acceptance_harvest`: `permutation_p_expectancy(baseline, component, *, n_perm=200, seed=42) -> float | None`.
- In `validate_component`, `--gate harvest` now routes the walkforward stage to `gate_expectancy_harvest` and the validation stage to `evaluate_harvest(structurally_immune_to_wr=True)`, which prints the outcome-flip, added and removed counts.
- `permutation_test.py --harvest-arms PATH [--n 200]` prints `{"p_value": ...}`.

Today `validate_component`'s walkforward stage is win-rate-only, its validation stage runs the v72 `evaluate`, and `permutation_test.py` permutes entry dates through `run_folds`. Shifting entries tests the entry signal, not an exit-only change. The new permutation is a ticker-cluster arm-label swap on ΔExpR: n = 200, p = share of permuted ΔExpR ≥ observed, the same `p_value` convention. V123-13 pre-registers it as the `not_luck` instrument.

- [ ] **Write the failing tests.**

```python
# tests/backtesting/test_harvest_stage_gates.py
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.acceptance_harvest import permutation_p_expectancy
from swingbot.core.backtesting.backtest_wf import gate_expectancy_harvest


def _fold(d, n=40):
    return {"test_years": "y", "delta_expectancy_r": d, "n_tp1": n}


def test_harvest_fold_gate():
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(0.01), _fold(-0.01)]}) == "PASS"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(-0.01), _fold(-0.01)]}) == "FAIL"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(0.05), _fold(-0.03)]}) == "FAIL"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(0.05), _fold(0.05, n=29)]}) == "FAIL"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(None), _fold(0.05)]}) == "FAIL"


def _t(ticker, r, i):
    return ArmTrade(ticker, "S", "2w", f"2021-01-{i:02d}", "win", r, 2.0)


def test_permutation_detects_a_uniform_lift_and_not_noise():
    base = [_t(f"T{k}", 1.0, i) for k in range(30) for i in range(1, 4)]
    lift = [_t(t.ticker, t.r_multiple + 0.3, int(t.entry_date[-2:])) for t in base]
    assert permutation_p_expectancy(base, lift) < 0.05
    assert permutation_p_expectancy(base, base) == 1.0
```

- [ ] Run narrowly and expect an import failure.
- [ ] **Implement.** In `backtest_wf.py`, beside `gate_win_rate`:

```python
#: v123 PRE-REGISTERED Stage 2 rule for an exit-only (harvest) component:
#: >= 2 of 3 folds with dExpR > 0, none below -0.02R, >= 30 TP1-touched per fold.
HARVEST_GATE_MIN_POSITIVE_FOLDS = 2
HARVEST_GATE_MAX_FOLD_LOSS_R = 0.02
HARVEST_GATE_MIN_TP1_PER_FOLD = 30


def gate_expectancy_harvest(result: dict) -> str:
    folds = result["folds"]
    deltas = [f.get("delta_expectancy_r") for f in folds]
    if len(folds) != 3 or any(d is None for d in deltas):
        return "FAIL"
    if any(f["n_tp1"] < HARVEST_GATE_MIN_TP1_PER_FOLD for f in folds):
        return "FAIL"
    if sum(d > 0 for d in deltas) < HARVEST_GATE_MIN_POSITIVE_FOLDS:
        return "FAIL"
    if any(d < -HARVEST_GATE_MAX_FOLD_LOSS_R for d in deltas):
        return "FAIL"
    return "PASS"
```

In `acceptance_harvest.py` (import `_group_by_ticker` from `.acceptance` and add the function to `__all__`):

```python
def _swapped(b_by, c_by, tickers, swap):
    pb, pc = [], []
    for ticker, flip in zip(tickers, swap):
        b, c = b_by.get(ticker, []), c_by.get(ticker, [])
        pb.extend(c if flip else b)
        pc.extend(b if flip else c)
    return pb, pc


def permutation_p_expectancy(baseline, component, *, n_perm: int = 200,
                             seed: int = 42) -> float | None:
    """v123 not_luck instrument for paired exit-only designs: swap the arm
    labels of a random half of tickers (clusters), recompute dExpR, and
    report the share of permutations at or above the observed dExpR."""
    observed = delta_expectancy_r(baseline, component)
    if observed is None:
        return None
    b_by, c_by = _group_by_ticker(baseline), _group_by_ticker(component)
    tickers = sorted(set(b_by) | set(c_by))
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_perm):
        delta = delta_expectancy_r(*_swapped(b_by, c_by, tickers, rng.random(len(tickers)) < 0.5))
        hits += delta is not None and delta >= observed - 1e-12
    return hits / n_perm
```

In `validate_component.py`, add:

```python
from swingbot.core.backtesting.acceptance_harvest import evaluate_harvest  # noqa: E402
from swingbot.core.backtesting.backtest_wf import gate_expectancy_harvest  # noqa: E402

def _harvest_fold_rows(folds):
    return [{"test_years": f["test_year"], "delta_expectancy_r": delta_expectancy_r(f["baseline"], f["component"]),
             "n_tp1": min(sum(t.outcome == "win" for t in f["baseline"]), sum(t.outcome == "win" for t in f["component"]))} for f in folds]

def _stage_walkforward_harvest(args, folds):
    rows = _harvest_fold_rows(folds); verdict = gate_expectancy_harvest({"folds": rows})
    print(f"{verdict} -- stage 2 walkforward harvest gate (dExpR)")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps({"verdict": verdict, "folds": rows}, indent=1), encoding="utf-8")
    return 0 if verdict == "PASS" else 1

def _evaluate_for(args, baseline, component, stage):
    if args.gate == "harvest":
        result = evaluate_harvest(baseline, component, stage=stage, structurally_immune_to_wr=True, permutation_p=args.permutation_p, n_resamples=args.resamples, seed=args.seed)
        print(f"disclosure: outcome flips={result.split['changed']} added={result.split['added']} removed={result.split['removed']}")
        return result
    return evaluate(baseline, component, stage=stage, permutation_p=args.permutation_p, n_resamples=args.resamples, seed=args.seed)
```

In `stage_walkforward`, after the well-formed check, add `if args.gate == "harvest": return _stage_walkforward_harvest(args, folds)`. In `_run_gate`, replace the `evaluate(...)` call with `_evaluate_for(args, baseline, component, stage)`. In `permutation_test.py`'s `__main__`, add `p.add_argument("--harvest-arms", default=None)`. When it is set, load the two arms the way `validate_component.load_arms` does (`ArmTrade(**row)` for `blob["baseline"]` and `blob["component"]`), print `json.dumps({"p_value": permutation_p_expectancy(b, c, n_perm=args.n), "instrument": "ticker-cluster arm-label swap on dExpR (v123)"})`, and exit before the `run_folds` path.

- [ ] Rerun narrowly, then `tests/backtesting/test_validate_component_cli.py`, `tests/backtesting/test_acceptance_harvest.py` and `tests/backtesting/test_wf_gate_winrate.py` (the existing `--gate` default must be unchanged). Run radon on the four files. Commit: `feat(v123): harvest walkforward/validation gates and dExpR permutation`.

### Task V123-12: Stage 1 harvest selection over a grid

**Files:** Create `scripts/backtest/harvest_select.py` and `tests/scripts/test_harvest_select.py`.

**Interfaces:**
- Produces: `select(cells: list[tuple[float, list, list]], *, param: str, less_aggressive: str, refused=()) -> dict` with keys `verdict` (`SELECTED|NO_ELIGIBLE_CELL|NO_PLATEAU`), `selected`, `rows` (`value, n, delta_r, lo95, eligible, plateau`). CLI: `--param NAME --cell VALUE=PATH` (repeated, in grid order), `--less-aggressive larger|smaller`, `--mde-refused VALUE` (repeated), `--out-json`.
- Consumes: `bootstrap_delta(..., delta_expectancy_r)`, `plateau_report`, `check_stamp(blob, funnel_stage="mde", ...)`. The `selection` producer stage is the mde funnel's stage.

Rule (spec Stage 1, verbatim in V123-13):
- Eligible means: the bootstrap lower 95% bound of ΔExpR is > 0 on fold-train (the selection-stage window), and Stage 0 did not refuse the cell.
- Qualifying means: eligible, plus `plateau_report(param, grid, ΔExpR list, value)["is_plateau"]`, plus at least one **eligible** grid neighbour.
- Pick the largest ΔExpR among qualifying cells. On a tie at 4 dp, take the less aggressive value (`b`: larger; `c`: smaller).

- [ ] **Write the failing test.**

```python
# tests/scripts/test_harvest_select.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
from harvest_select import select  # noqa: E402

from swingbot.core.backtesting.acceptance import ArmTrade


def _arm(lift, n=60):
    base = [ArmTrade(f"T{k % 20}", "S", "2w", f"2020-01-{k % 28 + 1:02d}-{k}", "win", 1.0, 2.0) for k in range(n)]
    comp = [ArmTrade(t.ticker, t.strategy, t.horizon_key, t.entry_date, t.outcome, 1.0 + lift, 2.0) for t in base]
    return base, comp


def test_plateau_of_eligible_neighbours_selects_largest_then_less_aggressive():
    cells = [(0.0, *_arm(0.05)), (0.25, *_arm(0.05)), (0.5, *_arm(0.0))]
    out = select(cells, param="b", less_aggressive="larger")
    assert out["verdict"] == "SELECTED" and out["selected"] == 0.25


def test_isolated_eligible_cell_is_not_selected():
    cells = [(0.70, *_arm(0.0)), (0.85, *_arm(0.2)), (1.00, *_arm(0.0))]
    assert select(cells, param="c", less_aggressive="smaller")["verdict"] == "NO_PLATEAU"


def test_mde_refused_cells_are_ineligible():
    cells = [(0.0, *_arm(0.05)), (0.25, *_arm(0.05)), (0.5, *_arm(0.05))]
    out = select(cells, param="b", less_aggressive="larger", refused=(0.0, 0.25, 0.5))
    assert out["verdict"] == "NO_ELIGIBLE_CELL"
```

- [ ] Run narrowly and expect an import failure.
- [ ] **Implement.**

```python
#!/usr/bin/env python3
"""v123 Stage 1: harvest selection over a grid of stamped selection-stage arms."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting.acceptance import ArmTrade, bootstrap_delta, delta_expectancy_r  # noqa: E402
from swingbot.core.backtesting.backtest_wf import plateau_report  # noqa: E402


def _row(value, baseline, component, refused):
    res = bootstrap_delta(baseline, component, delta_expectancy_r)
    eligible = value not in refused and res.lo is not None and res.lo > 0
    return {"value": value, "n": len(component), "delta_r": res.point, "lo95": res.lo, "eligible": eligible}


def _qualifies(rows, i, param, grid, deltas):
    if not rows[i]["eligible"]:
        return False
    neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(rows)]
    plateau = plateau_report(param, grid, deltas, grid[i])["is_plateau"]
    return plateau and any(rows[j]["eligible"] for j in neighbours)


def select(cells, *, param, less_aggressive, refused=()) -> dict:
    rows = [_row(v, b, c, set(refused)) for v, b, c in cells]
    grid, deltas = [r["value"] for r in rows], [r["delta_r"] or 0.0 for r in rows]
    for i, row in enumerate(rows):
        row["plateau"] = _qualifies(rows, i, param, grid, deltas)
    if not any(r["eligible"] for r in rows):
        return {"verdict": "NO_ELIGIBLE_CELL", "selected": None, "rows": rows}
    pool = [r for r in rows if r["plateau"]]
    if not pool:
        return {"verdict": "NO_PLATEAU", "selected": None, "rows": rows}
    best = max(round(r["delta_r"], 4) for r in pool)
    tied = [r["value"] for r in pool if round(r["delta_r"], 4) == best]
    pick = max(tied) if less_aggressive == "larger" else min(tied)
    return {"verdict": "SELECTED", "selected": pick, "rows": rows}


def _load(path):
    from swingbot.core.backtesting.arms.provenance import check_stamp
    from measure_arms import cached_universe
    blob = json.loads(Path(path).read_text())
    token = check_stamp(blob, funnel_stage="mde", full_universe=cached_universe())
    if token:
        raise SystemExit(f"{token} -- {path}. Budget intact.")
    return [ArmTrade(**r) for r in blob["baseline"]], [ArmTrade(**r) for r in blob["component"]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--param", required=True)
    p.add_argument("--cell", action="append", required=True)
    p.add_argument("--less-aggressive", choices=("larger", "smaller"), required=True)
    p.add_argument("--mde-refused", action="append", type=float, default=[])
    p.add_argument("--out-json", type=Path, required=True)
    args = p.parse_args(argv)
    cells = [(float(v), *_load(path)) for v, _, path in (c.partition("=") for c in args.cell)]
    out = select(cells, param=args.param, less_aggressive=args.less_aggressive, refused=args.mde_refused)
    args.out_json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0 if out["verdict"] == "SELECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
```

The JSON plus the result doc written in V123-14/15 carry the table.

- [ ] Rerun narrowly and expect PASS. Run radon. Commit: `feat(v123): harvest Stage 1 selection script`.

### Task V123-13: Pre-registration record

**Files:** Create `docs/superpowers/results/2026-10-02-v123-preregistration.md`.

- [ ] Invoke `backtest-gate` (Steps 1–3). Confirm against the closed table that neither arm is a closed row (spec § "Not a re-run").
- [ ] Write the record **before any outcome is read**. It states that the v72 funnel is not used and that the gate is the v92 harvest gate. It freezes the following, quoting the spec:
  - **Hypothesis.** Each arm's mechanism and grid (`b ∈ {0.00, 0.25, 0.50}`; `c ∈ {0.70, 0.85, 1.00}`, volume ≤ 1.0 frozen, `k = 3`).
  - **Population.** Both engines, `scale_out=True`, the full cached universe and all ten horizons, code defaults otherwise.
  - **Stages and windows.** Pilot 2018-06..2020-12 (10 tickers); selection/MDE 2018-06-01..2022-12-31; walk-forward 2021/2022/2023; VALIDATION 2024-01-01..2025-12-31, one shot per arm.
  - **Stage −1.** Run at `b = 0.00` and `c = 1.00` (the most active values). Zero changed outcomes means refused, budget intact.
  - **Stage 0.** `validate_component.py --stage mde --gate harvest --train-effect-r <cell ΔExpR>` per grid cell, with paired MDE. A refused cell is ineligible.
  - **Stage 1.** The V123-12 rule, verbatim, including the tie-break.
  - **Stage 2.** `gate_expectancy_harvest`: ≥ 2 of 3 folds with ΔExpR > 0, none below −0.02R, per-fold N(TP1-touched) ≥ 30.
  - **Stage 3.** All four harvest clauses. `not_luck` uses the V123-11 ticker-cluster arm-label permutation on ΔExpR (n = 200, seed 42). A missing p is FAIL.
  - **Disclosure.** The outcome-flip count must be 0; non-zero is a bug and stops the run. Added and removed counts are disclosed. `win_rate_floor` is SKIPPED only if `evaluate_harvest` confirms immunity; otherwise its −2pp floor is bootstrapped for real.
  - **Headroom.** V123-0's verdict and capture figure. If the verdict is `NO_HEADROOM`, the record says both arms close without a shot.
  - **Ship rule.** Copied from the spec.
- [ ] Commit the record alone: `docs(v123): pre-registration (harvest gate, two serial arms)`.

# Phase 5 — Measurement (serial, stop on fail)

### Task V123-14: `hl_trail` funnel

**Files:** Create `docs/superpowers/results/2026-10-02-v123-hl-trail.md` and its arm/JSON files under `docs/superpowers/results/`.

Skip this task if V123-0 returned `NO_HEADROOM`. Invoke `backtest-gate` before **every** command below. Dispatch `backtest-runner` for any `measure_arms.py` run (it prints flushed per-ticker progress and writes a `logs/measure_arms.*.progress` percent file). **Stop at the first failing stage**, record the result as-is and go to V123-15.

- [ ] **Stage −1:** `python scripts/backtest/measure_arms.py --stage pilot --knob RUNNER_STRUCTURE_EXIT=hl_trail --knob RUNNER_HL_TRAIL_ATR_BUFFER=0.0 --preregistration docs/superpowers/results/2026-10-02-v123-preregistration.md --out docs/superpowers/results/2026-10-02-v123-hl-trail-pilot.json`, then `python scripts/backtest/validate_component.py --stage reachability --arms docs/superpowers/results/2026-10-02-v123-hl-trail-pilot.json --title "v123 hl_trail" --window pilot`. `refused:zero-diff` means STOP: closed, budget intact.
- [ ] **Selection arms**, one per `b ∈ {0.0, 0.25, 0.5}`: `measure_arms.py --stage selection --knob RUNNER_STRUCTURE_EXIT=hl_trail --knob RUNNER_HL_TRAIL_ATR_BUFFER=<b> --preregistration ... --out docs/superpowers/results/2026-10-02-v123-hl-trail-sel-b<b>.json`.
- [ ] **Stage 0**, per cell: compute the cell's ΔExpR with `python scripts/backtest/harvest_select.py --param b --less-aggressive larger --cell 0.0=...-b0.0.json --cell 0.25=... --cell 0.5=... --out-json docs/superpowers/results/2026-10-02-v123-hl-trail-stage1.json`. Its `rows[].delta_r` is the claimed effect. Then run `validate_component.py --stage mde --gate harvest --arms <cell file> --title "v123 hl_trail b=<b>" --window selection --train-effect-r <delta_r>` per cell. Note every `REFUSED`. If all three are refused, STOP: closed at Stage 0, budget intact.
- [ ] **Stage 1:** rerun `harvest_select.py` with `--mde-refused <b>` for each refused cell. A verdict other than `SELECTED` means STOP: closed at Stage 1.
- [ ] **Stage 2:** `measure_arms.py --stage walkforward --knob RUNNER_STRUCTURE_EXIT=hl_trail --knob RUNNER_HL_TRAIL_ATR_BUFFER=<selected> --out ...-hl-trail-wf.json`, then `validate_component.py --stage walkforward --gate harvest --arms ...-hl-trail-wf.json --title "v123 hl_trail" --window walkforward --out-json ...-hl-trail-wf-gate.json`. FAIL means STOP.
- [ ] **Stage 3 (the one shot):** `measure_arms.py --stage validation --knob ... --preregistration docs/superpowers/results/2026-10-02-v123-preregistration.md --out ...-hl-trail-validation.json`. Then `python scripts/backtest/permutation_test.py --harvest-arms ...-hl-trail-validation.json --n 200`, then `validate_component.py --stage validation --gate harvest --arms ...-hl-trail-validation.json --title "v123 hl_trail VALIDATION" --window 2024-01-01..2025-12-31 --permutation-p <p> --out-md ...-hl-trail-validation.md --out-json ...-hl-trail-validation-gate.json`. A printed `outcome flips` other than 0 is a bug: stop and report it, never a result.
- [ ] Write `2026-10-02-v123-hl-trail.md`: every stage's table, the pre-registered rule quoted, the disclosure counts and an honest observations section. Commit the result files.

### Task V123-15: `progress_stall` funnel

**Files:** Create `docs/superpowers/results/2026-10-02-v123-progress-stall.md` and its arm/JSON files.

This is a separate budget, run after V123-14 finishes, and never pooled with it. Skip it if V123-0 returned `NO_HEADROOM`.

- [ ] Repeat every V123-14 step with `RUNNER_STRUCTURE_EXIT=progress_stall`, `--knob RUNNER_STALL_RANGE_MAX=<c>` for `c ∈ {0.70, 0.85, 1.00}`, Stage −1 at `c = 1.00`, `--param c --less-aggressive smaller`, and file prefix `2026-10-02-v123-progress-stall-`. Invoke `backtest-gate` before every command, stop at the first failing stage, record as-is, and commit.

### Task V123-16: Close-out — closed rows or ship

**Files:**
- Modify `docs/claude/backtest-methodology.md` and `AGENTS.md` if needed.
- On a ship only: modify `swingbot/config.py`, `.env.example`, `tests/test_v115_strategy_work_off.py`, `swingbot/core/analytics/metrics.py`, `VERSION.json` and the version matrix output.
- `config.py` is shared with v122, so this task does not run beside a v122 task.

- [ ] **For each arm that failed or was skipped,** append one row to "Closed pre-registrations — do not re-run these" in `docs/claude/backtest-methodology.md`. Name the component as `RUNNER_STRUCTURE_EXIT=hl_trail` / `=progress_stall` (v123). Give the stage it ended at, with its measured numbers, and whether the budget is spent. Include this reopen clause verbatim: reopening needs a mechanism other than "post-entry confirmed `k=3` swing low minus `b ∈ {0, 0.25, 0.5}` ATR" / "failed HH with range ratio ≤ `c ∈ {0.70, 0.85, 1.00}` and volume ratio ≤ 1.0, exit next open". Link the result records. An arm closed by Task 0 says "closed by the frozen 75% headroom rule, no shot spent". The code ships merged and inert (`RUNNER_STRUCTURE_EXIT=off`). Update the Field `help` text to cite the closed row, as the ADAPTIVE field does.
- [ ] **Codex mirror (CLAUDE.md rule).** `docs/claude/` changed, so check `AGENTS.md` (`grep -n "closed pre-registration\|backtest-methodology" AGENTS.md`). It condenses the rule, not the table. If no condensed sentence changes, leave `AGENTS.md` untouched and say so in the commit body. If one does (for example, a new standing rule this plan established), edit it in the same commit. Run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`.
- [ ] **If one or both arms passed VALIDATION:**
  - Invoke `backtest-gate` ("asked whether a flag should ship default-on").
  - Ship only the arm with the larger VALIDATION ΔExpR. Set its Field default (and its parameter's default to the selected value) in `config.py` and `.env.example`, and remove the v123 row from `FLAGS_OFF`.
  - If the shipped arm is `progress_stall`, add `"runner_progress_stall"` to `metrics.EXIT_REASONS`, `_RUNNER_SUBSTRINGS` and `_EXIT_REASON_ALIASES` (`"tp1_runner_progress_stall": "runner_progress_stall"`), with a test in the existing metrics test file.
  - Add the PASS row (or rows; the second passing arm is recorded unshipped) to the methodology table.
  - Bump per `document-conventions.md` § The header block: read `VERSION.json`, increment `bot` at patch level, stamp `bot_updated`, run `python scripts/dev/build_version_matrix.py`, and commit them together. Never hard-code a version.
- [ ] Commit, naming the closed or shipped arms: `docs(v123): close-out -- <arm verdicts>`.

### Task V123-17: Full-suite verification

**Files:** No new feature files. Fix only failures this plan caused, using their narrow tests.

- [ ] Run `python scripts/dev/testrun.py full` once (or dispatch `test-runner`) over everything Phases 0–5 changed. Green means `0 failed`, `0 xfailed`. If it is not green, fix forward from the named failures. Check `full-suite-flaky-shared-db` against the baseline before blaming a change: run the failing file alone and compare with `main`.
- [ ] Run `python -m radon cc -s -n C` over every file this plan touched. No function written or changed is at 15 or above. `_scale_out_exit_walk` dropped from 30, `_step_partial` from 19, and `_single_leg_exit_walk` is unchanged at 16.
- [ ] Close the plan per `document-lifecycle.md`. Move it to `implemented/` (the code is merged even if inert). Amend `Edge:`/`Bump:` in the closing commit with one clause if the outcome differs from the prediction (for example `Bump: none`, because no arm shipped).
