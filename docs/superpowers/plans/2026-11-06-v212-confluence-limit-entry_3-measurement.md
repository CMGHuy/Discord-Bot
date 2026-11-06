# v212 — Confluence limit entry, part 3: measurement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v212 — Confluence limit entry partway to the support](../specs/2026-11-06-v212-confluence-limit-entry.md) (rule 6 as corrected in e5dd654f: a gap through the stop fills at the open and exits at that open, about 0R less frictions, outcome `"loss"`; the from-L reading is only the disclosed `gap_stop_r_from_limit`)
**Index:** [`2026-11-06-v212-confluence-limit-entry_0-index.md`](2026-11-06-v212-confluence-limit-entry_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md`

Tasks V212-11 .. V212-14: the paired replay module (reference and arm plans
derived from one knob-0 replay, frictions applied at scoring), the
`portfolio_replay` extension (notional caps, a cluster callback, per-reason
skips), the measure script (stage chain, the three clauses, plateau, thin
seal, per-ticker checkpoint, ledger rows) and the disclosures module. All paths
are relative to the worktree
`.claude/worktrees/2026-11-06-v212-confluence-limit-entry` (created in V212-1
Step 0). Every task's verification is the narrow run; no task runs the full
suite. No task here reads the database, so none needs `/replicate-prod-db`.

**Data.** Backtests read the flat CSV cache `data/backtest_cache_ext` through
`BACKTEST_CACHE_DIR` and `MEASURE_ARMS_UNIVERSE=cache` (`measure_arms.load_frame`,
`cached_universe`); nothing here reads root `market_data/` except the earnings
CSVs (`earnings_calendar.EARNINGS_CSV_DIR`), used for one disclosure only.

**Windows (v139 precedent, `acceptance_exit_funnel`).** TRAIN
2020-01-01..2023-12-31 (Stages −1, 0, 1, 2), Stage 2 folds 2021 / 2022 / 2023
(the three folds `gate_expectancy_harvest` requires), VALIDATION
2024-01-01..2025-12-31 (Stage 3, one shot, the selected cell only).

# Phase D — measurement


### Task V212-11: Replay module, part 1: scope, paired arms from one stream, outcome-blind census, net R

**Model:** opus — new measurement module whose scope, pairing and R denominator decide the verdict; a silent mistake here biases every stage.

**Files:**
- Create: `swingbot/core/backtesting/confluence_limit_replay.py`
- Test: `tests/backtesting/test_confluence_limit_replay.py`

**Interfaces:**
- Consumes: `builders.apply_confluence_limit(plan, level, f, min_rr) -> TradePlanV2 | str` (V212-2), `builders.clamped_distance` (exists, `builders.py:588`); `limit_entry_rule.bar_outcome` (V212-4); `backtest_scenarios.replay_scenarios(ticker, df, horizon_key, *, gates=None)`, `frictions.apply_frictions` / `commission_r` / `borrow_r`, `risk_limits.planned_loss_pct` / `HARD_MAX_PLANNED_LOSS_PCT` (exist).
- Produces (consumed by V212-11b, V212-13, V212-14):
  - `F_GRID = (1/3, 1/2, 2/3)`; `cell_key(f) -> str` (`"f0.333"`, `"f0.5"`, `"f0.667"`); `CELLS`; `GUARDED_KNOBS`.
  - `in_scope(plan) -> bool`; `arm_plans(ref, *, cells=F_GRID, min_rr) -> dict[str, TradePlanV2 | str]`.
  - `paired_alerts(ticker, df, horizon_key, *, cells=F_GRID, gates=None) -> list[tuple[int, TradePlanV2, dict[str, TradePlanV2 | str]]]`.
  - `census_row(df, i, ref, arms) -> dict` — keys `key` (`"<ticker>|<horizon>|<signal date>|<direction>"`), `ticker`, `horizon_key`, `strategy`, `direction`, `entry_date` (signal date), `d_pct`, `drops` (cell → reason or None), `fill_state` (cell → `"filled"`, `"gap_stopped"`, `"tp1_cancel"`, `"expired"`, or None when dropped), `filled` (cell → bool).
  - `net_r(direction, entry, exit_legs, risk, days) -> float` — `exit_legs` is `[(fraction, exit_price), ...]`.
  - `census(ticker, frame, horizons, window, *, cells=F_GRID) -> list[dict]` — `window = (start, end)`, ISO or None, on the signal date; `cells` is an additive keyword beyond the ledger (Stage 3 replays the selected cell only, the v139 precedent).
  - Private helpers V212-11b reuses: `_date(df, j)`, `_identity(df, i, ref)`, `_alerts(ticker, frame, horizons, window, cells)`, `_is_bull(plan)`.

**Decisions fixed here** (index Global Constraints; spec § The rule 6–7, § Pass rule):
- **One plan stream.** Arms are derived from the knob-0 reference plan (`trigger_price` = M, `acceptance_level` = S, `tp1`, `tp2`, all frozen at bar t), so cooldown and alert set are identical by construction. A guard refuses to run with any v139/v191/v212 knob non-zero.
- **Scope** = confluence, `entry_type == "market"`, `clamped_distance(M, S, is_bull) is not None`: a missing level and a level at exactly 2% are out of scope, never a crash. Scope never depends on f; drops do.
- **R denominator = the sizing risk** `|plan.trigger_price − stop|` (M for the reference, L for an arm), used by V212-11b: the position is sized on it, so dollar P&L / dollar risk is the R scored. `net_r` takes that risk as an argument.
- **Frictions** (`edge/frictions.py`) at scoring: entry slipped against the trade, every exit leg slipped against the trade, round-trip `commission_r()`, `borrow_r` on shorts over calendar days held.
- **The 2% assertion** (rule 7): `arm_plans` raises `ValueError` for a kept arm plan with `planned_loss_pct(L, stop) > HARD_MAX_PLANNED_LOSS_PCT`.
- **Census is outcome-blind:** it decides fill / gap stop / TP1 cancel / expiry from `bar_outcome` over bars t+1..t+3 only and never walks an exit.

- [ ] **Step 1: Write the failing test** `tests/backtesting/test_confluence_limit_replay.py`

```python
"""v212 replay module, part 1: scope, paired arms from one reference stream,
the outcome-blind census and frictions in net R. V212-11b's row tests import
the fixtures below."""
import pytest

from swingbot import config
from swingbot.core.backtesting import confluence_limit_replay as clr
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.helpers import make_ohlcv

FLAT = [(100.0, 100.1, 99.9, 100.0)] * 20          # signal bar i = 19 (2021-01-29), M = 100
I = 19
TAIL = [(104.2, 106.5, 104.0, 106.3)] + [(106.3, 106.4, 106.2, 106.3)] * 6
DIP = (100.0, 100.2, 98.0, 99.0)                  # trades through 98.5, only touches 98.0
TO_TP1 = (99.0, 104.5, 98.9, 104.2)
GAP_UNDER_STOP = (96.0, 96.5, 95.5, 96.2)         # opens under the 96.75 arm stop
FRICTION_CONFIG = (("SLIPPAGE_BPS", 5.0), ("COMMISSION_PER_TRADE", 1.0),
                   ("COMMISSION_RISK_BASIS", 100.0), ("CONFLUENCE_LIMIT_ENTRY_F", 0.0),
                   ("CONFLUENCE_STRUCTURAL_STOP_PCT", 0.0), ("CONFLUENCE_STOP_DROP_PCT", 0.0),
                   ("CONFLUENCE_ATR_STOP_FLOOR", 0.0))


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    for attr, value in FRICTION_CONFIG:
        monkeypatch.setattr(config, attr, value, raising=False)


def ref_plan(direction="bullish", **kw):
    bull = direction == "bullish"
    base = dict(plan_id="r1", ticker="XYZ", created_at="2021-01-29", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
                stop_loss=98.25 if bull else 101.75, tp1=104.0 if bull else 96.0,
                tp1_fraction=0.5, tp2=106.0 if bull else 94.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.ACTIVE, status_history=[],
                acceptance_level=97.0 if bull else 103.0)
    base.update(kw)
    return TradePlanV2(**base)


def frame(*bars):
    return make_ohlcv(FLAT + list(bars) + TAIL, start="2021-01-04")


def test_grid_and_cell_keys():
    assert clr.CELLS == ("f0.333", "f0.5", "f0.667")
    assert [clr.cell_key(f) for f in clr.F_GRID] == list(clr.CELLS)


@pytest.mark.parametrize("kw,expected", [
    ({}, True),
    ({"acceptance_level": 99.0}, False),          # within 2%: stop already on structure
    ({"acceptance_level": 98.0}, False),          # exactly 2%: out of scope
    ({"acceptance_level": None}, False),          # missing level: out, never a crash
    ({"entry_type": "stop_entry", "entry_price": None}, False),
    ({"source": "strategy"}, False),
])
def test_scope(kw, expected):
    assert clr.in_scope(ref_plan(**kw)) is expected


def test_arm_plans_keep_drop_and_never_touch_the_reference():
    ref = ref_plan()
    arms = clr.arm_plans(ref, min_rr=1.5)
    assert arms["f0.333"] == "limit_stop_beyond_cap"         # (99 - 96.75) / 99 > 2%
    assert (arms["f0.5"].trigger_price, arms["f0.5"].stop_loss) == (98.5, 96.75)
    assert arms["f0.667"].trigger_price == 98.0
    assert (ref.entry_type, ref.trigger_price, ref.stop_loss) == ("market", 100.0, 98.25)


def test_a_kept_arm_past_two_percent_raises(monkeypatch):
    bad = ref_plan(entry_type="limit", stop_loss=97.0, limit_entry_f=0.5)
    monkeypatch.setattr(clr, "apply_confluence_limit", lambda *a, **k: bad)
    with pytest.raises(ValueError, match="2%"):
        clr.arm_plans(ref_plan(), min_rr=1.5)


def test_paired_alerts_keep_in_scope_plans_only(monkeypatch):
    monkeypatch.setattr(clr, "replay_scenarios",
                        lambda *a, **k: [(I, ref_plan()), (I + 1, ref_plan(acceptance_level=None))])
    out = clr.paired_alerts("XYZ", frame(DIP, TO_TP1), "4w", gates={})
    assert [(i, sorted(arms)) for i, _, arms in out] == [(I, sorted(clr.CELLS))]


def test_the_guard_refuses_a_live_knob(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)
    with pytest.raises(RuntimeError, match="must be 0"):
        clr.paired_alerts("XYZ", frame(DIP), "4w", gates={})


def test_census_is_outcome_blind_and_counts_fills():
    df, ref = frame(DIP, TO_TP1), ref_plan()
    row = clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))
    assert row["key"] == "XYZ|4w|2021-01-29|bullish"
    assert row["drops"] == {"f0.333": "limit_stop_beyond_cap", "f0.5": None, "f0.667": None}
    assert row["fill_state"] == {"f0.333": None, "f0.5": "filled", "f0.667": "tp1_cancel"}
    assert row["filled"] == {"f0.333": False, "f0.5": True, "f0.667": False}
    assert row["d_pct"] == pytest.approx(3.0)
    assert "r_net" not in row and "outcome" not in row


def test_census_counts_a_gap_stop_as_a_fill():
    df, ref = frame(GAP_UNDER_STOP), ref_plan()
    row = clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))
    assert row["fill_state"]["f0.5"] == "gap_stopped" and row["filled"]["f0.5"] is True


def test_census_expires_after_three_bars():
    quiet = (100.0, 100.1, 99.9, 100.0)
    df, ref = make_ohlcv(FLAT + [quiet] * 4 + [DIP] + TAIL, start="2021-01-04"), ref_plan()
    assert clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))["fill_state"]["f0.5"] == "expired"


def test_census_mirrors_for_a_short():
    ref = ref_plan("bearish")
    df = frame((100.0, 101.6, 99.9, 101.0), (101.0, 101.1, 95.5, 95.8))
    row = clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))
    assert row["filled"] == {"f0.333": False, "f0.5": True, "f0.667": False}


def test_net_r_long_and_short():
    # long: entry 100.05, exit 101.949 -> 0.9495 - 0.02 commission
    assert clr.net_r("bullish", 100.0, [(1.0, 102.0)], 2.0, 3) == pytest.approx(0.9295)
    # short: entry 99.95, exit 98.049 -> 0.9505 - 0.02 - 0.25 borrow (365 days)
    assert clr.net_r("bearish", 100.0, [(1.0, 98.0)], 2.0, 365) == pytest.approx(0.6805)
    # a gap stop: entry = exit = the open, risk 1.75 -> frictions only
    assert -0.1 < clr.net_r("bullish", 96.0, [(1.0, 96.0)], 1.75, 0) < 0.0
    with pytest.raises(ValueError):
        clr.net_r("bullish", 100.0, [(1.0, 102.0)], 0.0, 3)


def test_census_window_filters_on_the_signal_date(monkeypatch):
    monkeypatch.setattr(clr, "replay_scenarios", lambda *a, **k: [(I, ref_plan())])
    df = frame(DIP, TO_TP1)
    assert clr.census("XYZ", df, ["4w"], ("2021-02-01", None)) == []
    assert len(clr.census("XYZ", df, ["4w"], ("2021-01-29", "2021-01-29"))) == 1
    one = clr.census("XYZ", df, ["4w"], (None, None), cells=(0.5,))
    assert list(one[0]["drops"]) == ["f0.5"]
```

(The expiry test puts the dip on bar t+5, after the three-bar life: `to_limit_plan` sets `expiry_bars = 3`.)

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_replay.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.confluence_limit_replay'`.

- [ ] **Step 3: Write the module** `swingbot/core/backtesting/confluence_limit_replay.py`

```python
"""v212 confluence limit entry: paired reference/arm replay (spec § The rule,
§ Pass rule; plan V212-11 and V212-11b).

Every arm plan is derived from the knob-0 reference plan replay_scenarios
yields, so both arms see the same alert stream and the same cooldown. The
frictions of edge/frictions.py are applied here, at scoring, on the sizing
risk |trigger_price - stop| -- the R the account books. Census rows read no
outcome (Stage -1); entry rows (V212-11b) carry outcomes (Stages 0-3). Reads
whatever frame the caller passes (the measure script: data/backtest_cache_ext).
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r
from swingbot.core.planning.builders import apply_confluence_limit, clamped_distance
from swingbot.core.planning.limit_entry_rule import bar_outcome
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.scan_params import ScanParams

#: PRE-REGISTERED grid (spec § The rule). Changing it is a new pre-registration.
F_GRID = (1 / 3, 1 / 2, 2 / 3)
GUARDED_KNOBS = ("CONFLUENCE_LIMIT_ENTRY_F", "CONFLUENCE_STRUCTURAL_STOP_PCT",
                 "CONFLUENCE_STOP_DROP_PCT", "CONFLUENCE_ATR_STOP_FLOOR")
_TOL = 1e-9


def cell_key(f) -> str:
    """'f0.333', 'f0.5', 'f0.667'."""
    return f"f{round(float(f), 3):g}"


CELLS = tuple(cell_key(f) for f in F_GRID)


def _check_knobs_off() -> None:
    live = [attr for attr in GUARDED_KNOBS if getattr(config, attr, 0)]
    if live:
        raise RuntimeError(f"{', '.join(live)} must be 0 while measuring: the reference "
                           "is today's plan and every cell is applied explicitly")


def _is_bull(plan) -> bool:
    return plan.direction == "bullish"


def in_scope(plan) -> bool:
    """Spec § The rule, Scope: a confluence market plan whose pre-clamp level
    lies more than 2% from M (builders.clamped_distance)."""
    if plan.source != "confluence" or plan.entry_type != "market":
        return False
    return clamped_distance(plan.trigger_price, plan.acceptance_level, _is_bull(plan)) is not None


def _checked(arm):
    """Rule 7: every kept plan risks at most 2% of its limit."""
    if not isinstance(arm, str) and \
            planned_loss_pct(arm.trigger_price, arm.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + _TOL:
        raise ValueError(f"v212 arm plan {arm.ticker} risks more than 2% of its limit")
    return arm


def arm_plans(ref, *, cells=F_GRID, min_rr) -> dict:
    """{cell_key: limit plan | drop reason} for one in-scope reference plan."""
    out = {}
    for f in cells:
        arm = apply_confluence_limit(ref, ref.acceptance_level, float(f), min_rr)
        if arm is ref:
            raise RuntimeError(f"{ref.ticker}: in_scope and apply_confluence_limit disagree")
        out[cell_key(f)] = _checked(arm)
    return out


def paired_alerts(ticker, df, horizon_key, *, cells=F_GRID, gates=None) -> list:
    """[(signal_index, reference_plan, {cell: arm plan | reason})], in-scope only."""
    _check_knobs_off()
    min_rr = ScanParams.from_config().min_risk_reward_ratio
    plans = replay_scenarios(ticker, df, horizon_key, gates=gates)
    return [(int(i), ref, arm_plans(ref, cells=cells, min_rr=min_rr))
            for i, ref in plans if in_scope(ref)]


def _date(df, j) -> str | None:
    return None if j is None else str(df.index[int(j)].date())


def _identity(df, i, ref) -> dict:
    entry_date = _date(df, i)
    return {"key": f"{ref.ticker}|{ref.horizon_key}|{entry_date}|{ref.direction}",
            "ticker": ref.ticker, "horizon_key": ref.horizon_key, "strategy": ref.strategy,
            "direction": ref.direction, "entry_date": entry_date,
            "d_pct": clamped_distance(ref.trigger_price, ref.acceptance_level, _is_bull(ref))}


def _fill_state(df, i, plan) -> str:
    """The limit's fate over its expiry window, from bar_outcome alone -- no
    exit is walked, so the census stays outcome-blind."""
    last = min(i + plan.expiry_bars, len(df) - 1)
    for j in range(i + 1, last + 1):
        out = bar_outcome(plan, open_=float(df["Open"].iloc[j]), high=float(df["High"].iloc[j]),
                          low=float(df["Low"].iloc[j]))
        if out.kind == "fill":
            return "gap_stopped" if out.gap_stopped else "filled"
        if out.kind == "cancel":
            return "tp1_cancel"
    return "expired"


def census_row(df, i, ref, arms) -> dict:
    """Plans and fills only (Stage -1)."""
    states = {key: None if isinstance(arm, str) else _fill_state(df, i, arm)
              for key, arm in arms.items()}
    return {**_identity(df, i, ref),
            "drops": {key: arm if isinstance(arm, str) else None for key, arm in arms.items()},
            "fill_state": states,
            "filled": {key: state in ("filled", "gap_stopped") for key, state in states.items()}}


def net_r(direction, entry, exit_legs, risk, days) -> float:
    """R after frictions: entry and every exit slipped against the trade,
    round-trip commission, and a short's borrow over `days` calendar days.
    `risk` is the sizing risk |trigger_price - stop|."""
    if not risk or risk <= 0:
        raise ValueError("net_r needs a positive risk")
    bull = direction == "bullish"
    sign = 1.0 if bull else -1.0
    entry_net = apply_frictions(entry, "buy" if bull else "sell")
    exit_side = "sell" if bull else "buy"
    gross = sum(frac * sign * (apply_frictions(px, exit_side) - entry_net)
                for frac, px in exit_legs)
    r = gross / risk - commission_r()
    return r if bull else r - borrow_r(entry, risk, days)


def _in_window(signal_date, window) -> bool:
    start, end = window
    return not ((start and signal_date < start) or (end and signal_date > end))


def _alerts(ticker, frame, horizons, window, cells):
    for horizon_key in horizons:
        for i, ref, arms in paired_alerts(ticker, frame, horizon_key, cells=cells):
            if _in_window(_date(frame, i), window):
                yield i, ref, arms


def census(ticker, frame, horizons, window, *, cells=F_GRID) -> list:
    """Stage -1 rows for one ticker."""
    return [census_row(frame, i, ref, arms)
            for i, ref, arms in _alerts(ticker, frame, horizons, window, tuple(cells))]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_replay.py`
Expected: PASS.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS (every new function well under 15).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/confluence_limit_replay.py tests/backtesting/test_confluence_limit_replay.py
git commit -m "feat(v212): confluence limit replay -- scope, paired arms, census, net R (V212-11)"
```


### Task V212-11b: Replay module, part 2: entry rows (fill, gap stop, TP1 cancel, touch sensitivity) and `replay_entries`

**Model:** opus — fill-versus-exit semantics and the R each arm books are the measured quantity; the gap-through-stop row must score about 0R less frictions, never −1R or a scratch.

**Files:**
- Modify: `swingbot/core/backtesting/confluence_limit_replay.py` (imports; constants after `GUARDED_KNOBS`; the row helpers and `replay_entries` after `census`)
- Test: `tests/backtesting/test_confluence_limit_replay_rows.py`

**Interfaces:**
- Consumes: from V212-11 `arm_plans`, `net_r`, `_identity`, `_date`, `_alerts`, `_is_bull`, `cell_key`, `CELLS`; from V212-5 `simulate_exit_v2(df, signal_index, plan, instrument, *, scale_out=False, max_holding_days=None, touch_fill=False)`, `ExitResult.exit_reason`, `ExitResult.gap_stop_r_from_limit`, `ExitResult.entry_index` / `exit_index` / `entry_price` / `legs`, `exit_sim_v2.FILLED_STOPPED_GAP`; existing `acceptance.planned_rr(entry, stop, target)`, `instrument.contract.resolve`, `ZERO_COSTS`.
- Produces (consumed by V212-13, V212-14):
  - `EARLY_STOP_BARS = 3`; `REPLAY_INSTRUMENT = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)`; `UNTRIGGERED = ("not_triggered", "no_trade")`.
  - `entry_rows(df, i, ref, arms, *, touch=False) -> list[dict]` — one `"ref"` row, then one row per cell, every one always emitted. Keys: the ledger's `key`, `arm` (`"ref"` or a cell key), `ticker`, `horizon_key`, `direction`, `entry_date` (signal date, the pairing key), `fill_date`, `exit_date`, `entry`, `stop_loss`, `stop_pct`, `outcome`, `r_gross`, `r_net`, `exit_reason`, `gap_stopped`, `early_stop`, `atr14_pct`, `d_pct`; plus `strategy`, `market` (M), `limit` (L, None on the reference and on drops), `expiry_date`, `filled`, `dropped` (reason or None), `planned_rr`, `wick_through`, `gap_stop_r_from_limit`, `fill_rule` (`"trade_through"` / `"touch"`). A dropped cell has `outcome == "dropped"`; an unfilled one `"not_triggered"`; neither carries an R.
  - `replay_entries(ticker, frame, horizons, window, *, touch=False, cells=F_GRID) -> list[dict]`.

**Decisions fixed here** (index Global Constraints; spec § The rule 6):
- **Simulation.** Both arms run `simulate_exit_v2` under `REPLAY_INSTRUMENT`: v2 fills (market at the next open, gap-through fills) with `ZERO_COSTS`, so the sim stays frictionless and frictions come only from `net_r`. The reference fills at bar t+1's open; the arm rests on bars t+1..t+3. Both start after the alert at t's close.
- **R on the sizing risk** `|plan.trigger_price − stop|`, for `r_gross` and `r_net` alike, so the two differ only by frictions. A gap-through-stop arm fill (entry = exit = the open) is 0R gross.
- **Touch is arm-only.** The reference row is always simulated with `touch_fill=False`; only its `fill_rule` label follows the run.
- `early_stop`: a filled loss whose exit bar is fewer than `EARLY_STOP_BARS` bars after its fill bar (v131's adverse-selection diagnostic). `wick_through`: a stop exit whose bar closed back on the trade's side of the stop (stop-run diagnostic, never grounds to widen the buffer). `atr14_pct`: ATR14 as % of the signal close, bars ≤ t only.

- [ ] **Step 1: Write the failing test** `tests/backtesting/test_confluence_limit_replay_rows.py`

```python
"""v212 replay module, part 2: entry rows for the reference and every cell --
a fill, a TP1 cancel, a drop, a gap through the stop, the touch sensitivity
-- and the window filter on replay_entries."""
import pytest

from swingbot.core.backtesting import confluence_limit_replay as clr
from tests.backtesting.test_confluence_limit_replay import (  # noqa: F401  (autouse fixture)
    DIP, GAP_UNDER_STOP, I, TO_TP1, _frictions, frame, ref_plan)


def _rows(df, ref=None, touch=False):
    ref = ref or ref_plan()
    rows = clr.entry_rows(df, I, ref, clr.arm_plans(ref, min_rr=1.5), touch=touch)
    return {row["arm"]: row for row in rows}


def test_instrument_is_v2_fills_with_zero_costs():
    costs = clr.REPLAY_INSTRUMENT.cost_model
    assert clr.REPLAY_INSTRUMENT.fill_model.market_entry == "next_open"
    assert (costs.slippage_bps, costs.stop_slippage_bps, costs.commission_per_share) == (0, 0, 0)


def test_every_arm_gets_a_row_with_the_same_pairing_key():
    rows = _rows(frame(DIP, TO_TP1))
    assert set(rows) == {"ref", *clr.CELLS}
    assert {row["key"] for row in rows.values()} == {"XYZ|4w|2021-01-29|bullish"}
    assert {row["market"] for row in rows.values()} == {100.0}


def test_reference_fills_at_the_next_open_and_stops():
    ref = _rows(frame(DIP, TO_TP1))["ref"]
    assert (ref["filled"], ref["entry"], ref["fill_date"]) == (True, 100.0, "2021-02-01")
    assert (ref["outcome"], ref["r_gross"]) == ("loss", pytest.approx(-1.0))
    assert ref["r_net"] < ref["r_gross"]
    assert ref["early_stop"] is True and ref["limit"] is None


def test_a_filled_arm_books_a_win():
    half = _rows(frame(DIP, TO_TP1))["f0.5"]
    assert (half["filled"], half["entry"], half["outcome"]) == (True, 98.5, "win")
    assert (half["entry_date"], half["fill_date"]) == ("2021-01-29", "2021-02-01")
    assert (half["limit"], half["stop_loss"]) == (98.5, 96.75)
    assert half["stop_pct"] == pytest.approx(1.7766, abs=1e-3)
    assert half["r_gross"] > half["r_net"] > 0
    assert half["early_stop"] is False and half["gap_stopped"] is False
    assert half["fill_rule"] == "trade_through"


def test_tp1_first_cancels_and_a_drop_carries_its_reason():
    rows = _rows(frame(DIP, TO_TP1))
    two_thirds, third = rows["f0.667"], rows["f0.333"]
    assert (two_thirds["filled"], two_thirds["outcome"]) == (False, "not_triggered")
    assert (two_thirds["exit_reason"], two_thirds["r_net"]) == ("limit_tp1_cancel", None)
    assert (third["outcome"], third["dropped"], third["r_net"]) == (
        "dropped", "limit_stop_beyond_cap", None)


def test_touch_sensitivity_fills_a_bare_touch_and_leaves_the_reference():
    rows = _rows(frame(DIP, TO_TP1), touch=True)
    assert (rows["f0.667"]["filled"], rows["f0.667"]["entry"]) == (True, 98.0)
    assert rows["f0.667"]["fill_rule"] == "touch"
    assert rows["ref"] == {**_rows(frame(DIP, TO_TP1))["ref"], "fill_rule": "touch"}


def test_gap_through_the_stop_is_a_realised_fill_at_the_open():
    rows = _rows(frame(GAP_UNDER_STOP))
    half = rows["f0.5"]
    assert (half["filled"], half["entry"], half["gap_stopped"]) == (True, 96.0, True)
    assert (half["outcome"], half["exit_reason"]) == ("loss", "filled_stopped_gap")
    assert half["fill_date"] == half["exit_date"] == "2021-02-01"
    assert half["r_gross"] == pytest.approx(0.0)
    assert -0.1 < half["r_net"] < 0.0                    # frictions only, never -1R
    assert half["gap_stop_r_from_limit"] < -1.0          # the pessimistic from-L reading
    assert rows["ref"]["filled"] is False                # the market plan's own gap cancel


def test_atr_reads_bars_up_to_the_signal_only():
    calm, wild = _rows(frame(DIP, TO_TP1))["ref"], _rows(frame(GAP_UNDER_STOP))["ref"]
    assert calm["atr14_pct"] == pytest.approx(0.2) == wild["atr14_pct"]


def test_replay_entries_window_and_cells(monkeypatch):
    monkeypatch.setattr(clr, "replay_scenarios", lambda *a, **k: [(I, ref_plan())])
    df = frame(DIP, TO_TP1)
    assert clr.replay_entries("XYZ", df, ["4w"], ("2021-02-01", None)) == []
    assert len(clr.replay_entries("XYZ", df, ["4w"], ("2021-01-29", "2021-01-29"))) == 4
    one = clr.replay_entries("XYZ", df, ["4w"], (None, None), cells=(0.5,))
    assert [row["arm"] for row in one] == ["ref", "f0.5"]
    touched = clr.replay_entries("XYZ", df, ["4w"], (None, None), touch=True)
    assert {row["fill_rule"] for row in touched} == {"touch"}
```

(ATR: every flat bar has a 0.2 range and no gap, so ATR14 at i = 19 is 0.2% whatever follows; the gap row's `gap_stop_r_from_limit` is (96 − 98.5) / 1.75 ≈ −1.43R before the zero costs.)

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_replay_rows.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'entry_rows'`.

- [ ] **Step 3: Extend the module**

Imports — add to the import block of `confluence_limit_replay.py`:

```python
import dataclasses

import pandas as pd

from swingbot.core.backtesting.acceptance import planned_rr
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning.exit_sim_v2 import FILLED_STOPPED_GAP, simulate_exit_v2
```

Constants — after `GUARDED_KNOBS`:

```python
EARLY_STOP_BARS = 3
#: v2 fills (market at the next open, gap-through) with zero costs: the sim
#: stays frictionless and net_r applies edge/frictions.py at scoring.
REPLAY_INSTRUMENT = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
UNTRIGGERED = ("not_triggered", "no_trade")
```

Row helpers and `replay_entries` — after `census`:

```python
def _gross_r(direction, entry, exit_legs, risk) -> float:
    sign = 1.0 if direction == "bullish" else -1.0
    return sum(frac * sign * (px - entry) for frac, px in exit_legs) / risk


def _atr14_pct(df, i) -> float | None:
    """ATR14 as % of the signal close, bars <= i only."""
    if i < 14:
        return None
    window = df.iloc[i - 14:i + 1]
    prev = window["Close"].shift(1)
    tr = pd.concat([window["High"] - window["Low"], (window["High"] - prev).abs(),
                    (window["Low"] - prev).abs()], axis=1).max(axis=1).iloc[1:]
    return float(tr.mean() / float(df["Close"].iloc[i]) * 100.0)


def _wick_through(df, plan, res) -> bool:
    """Stopped on a wick: the stop bar closed back on the trade's side."""
    if not res.legs or res.legs[-1].get("reason") != "stop":
        return False
    close = float(df["Close"].iloc[res.exit_index])
    return close > plan.stop_loss if _is_bull(plan) else close < plan.stop_loss


def _days(df, res) -> int:
    start, end = df.index[res.entry_index].date(), df.index[res.exit_index].date()
    return max((end - start).days, 0)


def _scores(df, plan, res) -> dict:
    """Both R readings on the sizing risk, plus the stop diagnostics."""
    risk = abs(plan.trigger_price - plan.stop_loss)
    legs = [(leg["fraction"], leg["exit_price"]) for leg in res.legs]
    return {"r_gross": _gross_r(plan.direction, res.entry_price, legs, risk),
            "r_net": net_r(plan.direction, res.entry_price, legs, risk, _days(df, res)),
            "stop_pct": planned_loss_pct(res.entry_price, plan.stop_loss),
            "early_stop": res.outcome == "loss"
            and res.exit_index - res.entry_index < EARLY_STOP_BARS,
            "wick_through": _wick_through(df, plan, res)}


_EMPTY_SCORES = {"r_gross": None, "r_net": None, "stop_pct": None, "early_stop": False,
                 "wick_through": False}


def _fill_rule(touch) -> str:
    return "touch" if touch else "trade_through"


def _row(df, i, ref, arm_name, plan, res, touch) -> dict:
    filled = res.outcome not in UNTRIGGERED
    reason = getattr(res, "exit_reason", None)
    return {**_identity(df, i, ref), "arm": arm_name, "dropped": None, "filled": filled,
            "market": ref.trigger_price, "limit": None if arm_name == "ref" else plan.trigger_price,
            "stop_loss": plan.stop_loss, "outcome": res.outcome,
            "entry": res.entry_price if filled else None,
            "fill_date": _date(df, res.entry_index) if filled else None,
            "exit_date": _date(df, res.exit_index) if filled else None,
            "expiry_date": _date(df, min(i + plan.expiry_bars, len(df) - 1)),
            "exit_reason": reason, "gap_stopped": reason == FILLED_STOPPED_GAP,
            "gap_stop_r_from_limit": getattr(res, "gap_stop_r_from_limit", None),
            "planned_rr": planned_rr(plan.trigger_price, plan.stop_loss, plan.tp1),
            "atr14_pct": _atr14_pct(df, i), "fill_rule": _fill_rule(touch),
            **(_scores(df, plan, res) if filled else _EMPTY_SCORES)}


def _dropped_row(df, i, ref, arm_name, reason, touch) -> dict:
    return {**_identity(df, i, ref), "arm": arm_name, "dropped": reason, "filled": False,
            "market": ref.trigger_price, "limit": None, "stop_loss": None, "outcome": "dropped",
            "entry": None, "fill_date": None, "exit_date": None, "expiry_date": None,
            "exit_reason": None, "gap_stopped": False, "gap_stop_r_from_limit": None,
            "planned_rr": None, "atr14_pct": _atr14_pct(df, i), "fill_rule": _fill_rule(touch),
            **_EMPTY_SCORES}


def _simulate(df, i, plan, touch):
    return simulate_exit_v2(df, i, plan, REPLAY_INSTRUMENT, scale_out=True, touch_fill=touch)


def entry_rows(df, i, ref, arms, *, touch=False) -> list:
    """The reference row, then one row per cell (dropped, unfilled or filled).
    The reference never reads `touch` for its fill: touch is arm-only."""
    rows = [_row(df, i, ref, "ref", ref, _simulate(df, i, ref, False), touch)]
    for key, arm in arms.items():
        if isinstance(arm, str):
            rows.append(_dropped_row(df, i, ref, key, arm, touch))
        else:
            rows.append(_row(df, i, ref, key, arm, _simulate(df, i, arm, touch), touch))
    return rows


def replay_entries(ticker, frame, horizons, window, *, touch=False, cells=F_GRID) -> list:
    """Outcome rows for one ticker; the exit walk may run past `window`'s end."""
    return [row for i, ref, arms in _alerts(ticker, frame, horizons, window, tuple(cells))
            for row in entry_rows(frame, i, ref, arms, touch=touch)]
```

Update the module docstring's last paragraph to name both row shapes as shipped.

- [ ] **Step 4: Run both test files**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_replay_rows.py
python scripts/dev/testrun.py file tests/backtesting/test_confluence_limit_replay.py
```
Expected: PASS. If the f0.5 trade is not `"win"`, print its `res.legs`: TP1 trades on bar t+2 and TP2 on bar t+3, so `scale_out=True` must book a win. Fix the code, never the assertion.

- [ ] **Step 5: Complexity and the knob-0 witness**

```bash
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/backtesting/test_v212_flag_off_golden.py
```
Expected: gate PASS (`_row` is the busiest function: a dict literal with five conditional expressions); the golden passes untouched.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/confluence_limit_replay.py tests/backtesting/test_confluence_limit_replay_rows.py
git commit -m "feat(v212): confluence limit replay entry rows, gap stop realised, touch sensitivity (V212-11b)"
```


### Task V212-12: `portfolio_replay`: notional caps, cluster callback, skip reasons, taken keys

**Model:** opus — edits a shared legacy function above the complexity limit that other closed results depend on; every addition must be branch-free inside it and byte-identical when unused.

**Files:**
- Modify: `swingbot/core/backtesting/backtest_wf.py` (`portfolio_replay` at ~line 316, and three new module-level helpers placed directly above it)
- Test: `tests/backtesting/test_portfolio_replay_v212.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (disjoint from V212-11; group D may run it beside groups B and C).
- Produces (consumed by V212-13 `portfolio_pass`, V212-14 disclosures):
  - `portfolio_replay(signals, *, ..., max_position_pct: float | None = None, max_position_value: float | None = None, cluster_fn: Callable[[list[dict], dict, float], bool] | None = None, track_keys: bool = False) -> dict`.
  - Signals may carry `stop_pct` (planned stop distance, % of entry; the notional caps read it) and `key` (any hashable; recorded in `taken_keys`).
  - `cluster_fn(open_pos, sig, eff_risk) -> bool` returns **True when the signal breaches the cluster cap** (skip). `open_pos` entries carry `ticker`, `sector`, `risk_pct`, `entry_date`, `exit_date`, `direction`.
  - When any of the four new options is set, the result gains `notional_capped: int` (signals whose risk a notional cap cut), `skip_reasons: dict[str, int]` (keys among `"throttle"`, `"one_per_ticker"`, `"heat"`, `"sector"`, `"cluster"`, `"max_open"`) and `taken_keys: list` (each taken signal's `key`, in take order). With all four at their defaults the result dict is exactly today's.
- Helpers (module-level, private): `_notional_capped_risk(sig, balance, eff_risk, max_pct, max_value, extra) -> float`, `_capacity_reason(open_pos, sec, eff_risk, sig, heat_cap_pct, sector_cap_pct, max_open, cluster_fn) -> str | None`, `_note_skip(extra, reason) -> None`, `_with_v212(out, extra, options) -> dict`.

**Rules (spec § The rule 7–8; index Global Constraints "Sizing", "Heat at fill"):**
- Shares are fixed-dollar risk over the stop distance, so the notional is `balance × eff_risk / stop_pct` (both in %). `MAX_POSITION_SIZE_PCT` caps it at `balance × max_position_pct / 100`; `MAX_POSITION_VALUE_ABSOLUTE` at `max_position_value` when > 0 (`account._uncut_size_caps` treats 0 as off). A cut scales the carried risk by `cap / notional`; the trade's R (`r_multiple`) is untouched — R stays scored on the plan's stop, only the balance step and the heat use the cut risk. A signal without `stop_pct` is never capped.
- Order inside one signal, as today plus the new checks: close due positions → throttle → one-per-ticker → **notional cut** → capacity in the order heat, sector, cluster, max_open (the same order `fill_heat.heat_at_fill_reason` uses). Heat runs on the cut risk.
- `portfolio_replay` is a legacy function at or above complexity 15 (`complexity_baseline.json`): it may not get worse. Every new decision lives in a helper; inside the function only calls and one `if reason is not None` replace the old compound capacity condition (which removes three boolean operators).

- [ ] **Step 1: Write the failing test** `tests/backtesting/test_portfolio_replay_v212.py`

```python
"""v212 portfolio_replay options: notional caps scale carried risk (R stays
on the plan's stop), per-reason skips, a cluster callback, taken keys, and
today's dict exactly when no option is set."""
import pytest

from swingbot.core.backtesting.backtest_wf import portfolio_replay

LEGACY_KEYS = {"equity_curve", "final_multiple", "max_dd_pct", "trades_taken",
               "trades_skipped", "trades_per_month", "r_multiples_taken", "per_strategy_wr",
               "reversals", "reversals_r_delta"}


def _sig(ticker="AAA", date="2021-01-04", exit_date="2021-01-08", r=1.0, **kw):
    return {"ticker": ticker, "date": date, "exit_date": exit_date, "r_multiple": r,
            "direction": "bullish", "outcome": "win" if r > 0 else "loss",
            "strategy": "S/R Confluence", "stop_pct": 1.0, "key": f"{ticker}|{date}", **kw}


def _run(signals, **kw):
    return portfolio_replay(signals, throttles=False, sector_cap_pct=100.0, **kw)


def test_no_option_returns_todays_dict_exactly():
    signals = [_sig(), _sig("BBB", r=-1.0)]
    out = _run(signals)
    assert set(out) == LEGACY_KEYS
    assert out == _run(signals, max_position_pct=None, max_position_value=None,
                       cluster_fn=None, track_keys=False)
    assert out["final_multiple"] == pytest.approx(1.01 * 0.99)


@pytest.mark.parametrize("kw,multiple", [
    ({"max_position_value": 1000.0}, 1.001),      # $10k notional cut to $1k: risk 0.1%
    ({"max_position_pct": 50.0}, 1.005),          # cut to $5k: risk 0.5%
    ({"max_position_pct": 50.0, "max_position_value": 1000.0}, 1.001),   # the tighter wins
    ({"max_position_value": 0.0}, 1.01),          # 0 = off, as account._uncut_size_caps
    ({"max_position_pct": 200.0}, 1.01),          # cap above the notional: no cut
])
def test_notional_caps_scale_the_carried_risk(kw, multiple):
    out = _run([_sig()], **kw)
    assert out["final_multiple"] == pytest.approx(multiple)
    assert out["r_multiples_taken"] == [1.0]                 # R stays on the plan's stop
    assert out["notional_capped"] == (0 if multiple == 1.01 else 1)


def test_a_signal_without_stop_pct_is_never_capped():
    sig = _sig()
    del sig["stop_pct"]
    out = _run([sig], max_position_value=1000.0)
    assert (out["final_multiple"], out["notional_capped"]) == (pytest.approx(1.01), 0)


def test_heat_runs_on_the_cut_risk():
    signals = [_sig(), _sig("BBB")]                       # both open the same day
    assert _run(signals, heat_cap_pct=1.5)["trades_taken"] == 1
    out = _run(signals, heat_cap_pct=1.5, max_position_value=5000.0)   # 0.5% each
    assert out["trades_taken"] == 2


def test_skip_reasons_name_each_cap():
    two = [_sig(), _sig("BBB")]
    assert _run(two, heat_cap_pct=1.5, track_keys=True)["skip_reasons"] == {"heat": 1}
    sectors = {"AAA": "Tech", "BBB": "Tech"}
    out = portfolio_replay(two, throttles=False, sectors=sectors, sector_cap_pct=1.5,
                           track_keys=True)
    assert out["skip_reasons"] == {"sector": 1}
    assert _run(two, max_open=1, track_keys=True)["skip_reasons"] == {"max_open": 1}
    same = [_sig(), _sig(date="2021-01-05")]
    assert _run(same, track_keys=True)["skip_reasons"] == {"one_per_ticker": 1}


def test_the_cluster_callback_skips_and_sees_the_open_book():
    seen = []

    def cluster_fn(open_pos, sig, eff_risk):
        seen.append(([p["ticker"] for p in open_pos], sig["ticker"], eff_risk))
        return bool(open_pos)

    out = _run([_sig(), _sig("BBB")], cluster_fn=cluster_fn)
    assert (out["trades_taken"], out["skip_reasons"]) == (1, {"cluster": 1})
    assert seen == [([], "AAA", 1.0), (["AAA"], "BBB", 1.0)]


def test_taken_keys_follow_take_order_and_exits_free_capacity():
    signals = [_sig(), _sig("BBB"), _sig("CCC", date="2021-01-11", exit_date="2021-01-15")]
    out = _run(signals, max_open=1, track_keys=True)
    assert out["taken_keys"] == ["AAA|2021-01-04", "CCC|2021-01-11"]
    assert (out["trades_skipped"], out["notional_capped"]) == (1, 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_portfolio_replay_v212.py`
Expected: FAIL — `TypeError: portfolio_replay() got an unexpected keyword argument 'max_position_value'` (and `KeyError: 'notional_capped'`).

- [ ] **Step 3: Add the helpers** directly above `def portfolio_replay` in `swingbot/core/backtesting/backtest_wf.py`

```python
_V212_OPTIONS = ("max_position_pct", "max_position_value", "cluster_fn", "track_keys")


def _note_skip(extra: dict, reason: str) -> None:
    extra["skip_reasons"][reason] = extra["skip_reasons"].get(reason, 0) + 1


def _notional_capped_risk(sig, balance, eff_risk, max_pct, max_value, extra) -> float:
    """v212 rule 7: shares = dollar risk / stop distance, so the notional is
    balance * eff_risk / stop_pct. A notional cap cuts the shares and with
    them the risk carried; the trade's R is untouched. 0 or None = no cap;
    a signal without stop_pct is never capped."""
    stop_pct = sig.get("stop_pct")
    caps = [cap for cap in (None if max_pct is None else balance * max_pct / 100.0,
                            max_value if max_value else None) if cap is not None]
    if not caps or not stop_pct or stop_pct <= 0 or balance <= 0:
        return eff_risk
    notional = balance * eff_risk / stop_pct
    cap = min(caps)
    if notional <= cap + 1e-9:
        return eff_risk
    extra["notional_capped"] += 1
    return eff_risk * cap / notional


def _capacity_reason(open_pos, sec, eff_risk, sig, heat_cap_pct, sector_cap_pct, max_open,
                     cluster_fn) -> str | None:
    """The first cap a new position breaches -- heat, sector, cluster,
    max_open (fill_heat's order) -- or None. Today's checks, unchanged in
    value; cluster only when a callback is given."""
    heat = sum(p["risk_pct"] for p in open_pos)
    if heat + eff_risk > heat_cap_pct + 1e-9:
        return "heat"
    sec_heat = sum(p["risk_pct"] for p in open_pos if p["sector"] == sec)
    if sec and sec_heat + eff_risk > sector_cap_pct + 1e-9:
        return "sector"
    if cluster_fn is not None and cluster_fn(open_pos, sig, eff_risk):
        return "cluster"
    if max_open is not None and len(open_pos) >= max_open:
        return "max_open"
    return None


def _with_v212(out: dict, extra: dict, options: dict) -> dict:
    """Today's dict unless a v212 option was set (a 0.0 cap counts as set)."""
    used = bool(options["track_keys"]) or any(options[name] is not None
                                              for name in _V212_OPTIONS[:3])
    return {**out, **extra} if used else out
```

- [ ] **Step 4: Wire them into `portfolio_replay`** (edits only; nothing else in the function moves)

1. Signature — append after `rev_max_per_day: int = 1`:

```python
                     rev_max_per_day: int = 1,
                     max_position_pct: float | None = None,
                     max_position_value: float | None = None,
                     cluster_fn=None,
                     track_keys: bool = False) -> dict:
```

and add one docstring paragraph: "v212: `max_position_pct` / `max_position_value` apply the notional caps to signals carrying `stop_pct` (the cut scales carried risk, never `r_multiple`); `cluster_fn(open_pos, sig, eff_risk)` returns True to skip a signal on the cluster cap; `track_keys` records each taken signal's `key`. With all four unset the result is exactly the pre-v212 dict."

2. After the `taken_strategy_outcomes: list[...] = []` line:

```python
    options = {"max_position_pct": max_position_pct, "max_position_value": max_position_value,
               "cluster_fn": cluster_fn, "track_keys": track_keys}
    extra = {"notional_capped": 0, "skip_reasons": {}, "taken_keys": []}
```

3. The throttle skip (`if eff_risk <= 0:`) becomes:

```python
        if eff_risk <= 0:
            skipped += 1
            _note_skip(extra, "throttle")
            continue
```

4. The one-per-ticker skip (`if not flipped:`) becomes:

```python
                if not flipped:
                    skipped += 1
                    _note_skip(extra, "one_per_ticker")
                    continue
```

5. Replace the whole `# 3) capacity checks` block (the `heat = ...`, `sec = ...`, `sec_heat = ...` lines and the compound `if (...)`) with:

```python
        # 3) capacity checks (v212: notional cut first, then heat on the cut risk)
        eff_risk = _notional_capped_risk(sig, balance, eff_risk, max_position_pct,
                                         max_position_value, extra)
        sec = (sectors or {}).get(sig["ticker"], sig.get("sector"))
        reason = _capacity_reason(open_pos, sec, eff_risk, sig, heat_cap_pct, sector_cap_pct,
                                  max_open, cluster_fn)
        if reason is not None:
            skipped += 1
            _note_skip(extra, reason)
            continue
```

6. After `taken_strategy_outcomes.append(...)`:

```python
        extra["taken_keys"].append(sig.get("key"))
```

7. The final `return {"equity_curve": curve, ...}` becomes `out = {...}` (same literal, same comments) followed by:

```python
    return _with_v212(out, extra, options)
```

- [ ] **Step 5: Run the new and the existing portfolio tests**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_portfolio_replay_v212.py
python scripts/dev/testrun.py file tests/backtesting/test_portfolio_reversals.py
python scripts/dev/testrun.py file tests/backtesting/test_wf_portfolio.py
```
Expected: all PASS; the two existing files unchanged and green (the no-option path is today's arithmetic).

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: PASS — `portfolio_replay` no higher than its baseline entry (the compound capacity condition is gone, the new lines are calls); the four helpers are each under 8.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/backtest_wf.py tests/backtesting/test_portfolio_replay_v212.py
git commit -m "feat(v212): portfolio_replay notional caps, cluster callback, skip reasons, taken keys (V212-12)"
```


### Task V212-13: Measure script, part 1: frozen constants, pre-registration refusal, per-ticker checkpointed build, `census` / `rows` CLI

**Model:** opus — the checkpoint and the pre-registration refusal guard a one-shot measurement; a resume that replays a finished ticker under different code, or a run before the record is committed, spends the shot dishonestly.

**Files:**
- Create: `scripts/backtest/measure_confluence_limit.py`
- Test: `tests/backtest_scripts/test_measure_confluence_limit.py`

**Interfaces:**
- Consumes: V212-11/11b `confluence_limit_replay.census(ticker, frame, horizons, window, *, cells)`, `replay_entries(ticker, frame, horizons, window, *, touch, cells)`, `F_GRID`, `CELLS`, `cell_key`; existing `acceptance_exit_funnel.TRAIN` / `VALIDATION`, `backtest_scenarios._resolve_replay_workers`, `measure_arms.load_frame` / `cached_universe`, `strategy_types.LEGACY_HORIZONS`.
- Produces (consumed by V212-13b, V212-13c, V212-14 and the V212-15/16 commands):
  - Constants: `RESULTS` (`docs/superpowers/results/v212`), `CHECKPOINTS` (`logs/v212-checkpoints`), `TRAIN = ("2020-01-01", "2023-12-31")`, `VALIDATION = ("2024-01-01", "2025-12-31")`, `WINDOWS`, `FOLD_YEARS = (2021, 2022, 2023)`, `REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}`, `ADVANCING`, `FILLS_SHARE = 0.5`, `WR_SLACK_PP = 2.0`, `THIN_PER_DIRECTION = 30`, `DIRECTIONS`, `CLAUSE_NAMES`.
  - `_load(path)`, `_write(path, blob, indent=1)`, `_refuse(message)` (raises `SystemExit("refused: ...")`).
  - Stage files: `stage_path(out_dir, stage) -> Path` (`v212-stageM1.json`, `v212-stage0.json` .. `v212-stage3.json`); `rows_file(out_dir, kind, window_name, touch=False) -> Path` (`v212-<kind>-<window>[-touch]-rows.json`, also what the CLI writes); `_previous(out_dir, stage) -> dict` (the verdict JSON a stage consumes per `REQUIRES`, or a refusal naming the stage to run first or the verdict that closed the run).
  - `require_preregistration(path) -> None` — refuses unless the name ends `-v212-preregistration.md`, the file exists and `_committed(path)` (git: tracked and clean).
  - `universe() -> list[str]`; `build(kind, window, *, touch=False, cells=F_GRID, tickers=None, workers=None, checkpoint_dir=CHECKPOINTS, worker=None) -> list[dict]` — each finished ticker is written at once to `checkpoint_dir/<tag>/<TICKER>.json`; a restart loads it and replays nothing finished; `<tag>` separates kind, window, fill rule and cells.
  - CLI: `census` and `rows` subcommands (`--window train` only: VALIDATION rows are built by `stage --stage 3` alone, for the selected cell; `--cells`, `rows --touch`, plus the shared `--preregistration` (required), `--out` (a directory, default `RESULTS`), `--checkpoint-dir`, `--tickers`, `--workers`); output `<out>/v212-<command>-<window>[-touch]-rows.json`. `COMMANDS: dict[str, Callable]`, `_common(sub)` and `_parser() -> (parser, subparsers)` are the extension points V212-13c uses for `stage` and `ledger`.

**Decisions fixed here** (spec § G3, index Global Constraints; CLAUDE.md § Long runs must checkpoint):
- **Every command refuses before the pre-registration is committed** (v131 precedent: the record freezes rule, grid, clauses, windows and gate before any compute).
- **Checkpoint unit = one ticker**, written the moment it finishes, with a flushed `done/total (pct%)` line; the final row list is in ticker order whatever order the pool finishes in.
- **Data:** `measure_arms.load_frame` reads the flat CSV cache (`BACKTEST_CACHE_DIR=data/backtest_cache_ext`; universe `MEASURE_ARMS_UNIVERSE=cache`); horizons are `LEGACY_HORIZONS` (v139 precedent). Windows are the v139 / `acceptance_exit_funnel` ones.

- [ ] **Step 1: Write the failing test** `tests/backtest_scripts/test_measure_confluence_limit.py`

```python
"""V212-13: the v212 measure script's frozen constants, the pre-registration
refusal and the per-ticker checkpoint. No replay runs: the worker is faked."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_confluence_limit as mcl  # noqa: E402


def test_frozen_constants():
    assert mcl.REQUIRES == {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"),
                            3: (2, "PASS")}
    assert (mcl.FILLS_SHARE, mcl.WR_SLACK_PP, mcl.THIN_PER_DIRECTION) == (0.5, 2.0, 30)
    assert (mcl.TRAIN, mcl.VALIDATION) == (("2020-01-01", "2023-12-31"),
                                           ("2024-01-01", "2025-12-31"))
    assert mcl.FOLD_YEARS == (2021, 2022, 2023)
    assert mcl.RESULTS.parts[-3:] == ("superpowers", "results", "v212")
    assert mcl.CLAUSE_NAMES == ("expr_beats_reference", "fills_half_of_reference",
                                "wr_within_2pp")


def test_require_preregistration_refuses(tmp_path, monkeypatch):
    wrong = tmp_path / "2026-11-06-v131-preregistration.md"
    wrong.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.require_preregistration(wrong)
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.require_preregistration(None)
    missing = tmp_path / "2026-11-07-v212-preregistration.md"
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.require_preregistration(missing)
    right = tmp_path / "2026-11-06-v212-preregistration.md"
    right.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="uncommitted"):     # outside the repo: untracked
        mcl.require_preregistration(right)
    monkeypatch.setattr(mcl, "_committed", lambda path: True)
    assert mcl.require_preregistration(right) is None


def test_stage_files_and_the_requires_chain(tmp_path):
    assert mcl.stage_path("d", -1).name == "v212-stageM1.json"
    assert mcl.stage_path("d", 3).name == "v212-stage3.json"
    assert mcl.rows_file("d", "rows", "train", touch=True).name == "v212-rows-train-touch-rows.json"
    with pytest.raises(SystemExit, match="run stage -1 first"):
        mcl._previous(tmp_path, 0)
    mcl._write(mcl.stage_path(tmp_path, -1), {"verdict": "refused:zero-diff"})
    with pytest.raises(SystemExit, match="closed at stage -1"):
        mcl._previous(tmp_path, 0)
    mcl._write(mcl.stage_path(tmp_path, 0), {"verdict": "POWERED"})
    assert mcl._previous(tmp_path, 1) == {"verdict": "POWERED"}


def _fake_worker(calls):
    def worker(task):
        calls.append(task[1])
        return task[1], [{"ticker": task[1], "kind": task[0], "touch": task[3]}]
    return worker


def test_build_checkpoints_each_ticker_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["BBB", "AAA"])
    calls = []
    first = mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                      worker=_fake_worker(calls))
    assert [r["ticker"] for r in first] == ["AAA", "BBB"]       # ticker order, not run order
    assert len(list(tmp_path.rglob("*.json"))) == 2
    calls.clear()
    again = mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                      worker=_fake_worker(calls))
    assert (again, calls) == (first, [])                          # nothing finished is replayed


def test_build_resumes_a_half_finished_run(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["AAA", "BBB", "CCC"])
    calls = []
    mcl.build("census", mcl.TRAIN, tickers=1, checkpoint_dir=tmp_path, workers=1,
              worker=_fake_worker(calls))
    calls.clear()
    rows = mcl.build("census", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                     worker=_fake_worker(calls))
    assert calls == ["BBB", "CCC"] and len(rows) == 3


def test_touch_cells_and_windows_get_their_own_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "universe", lambda: ["AAA"])
    calls = []
    for kw in ({}, {"touch": True}, {"cells": (0.5,)}):
        mcl.build("rows", mcl.TRAIN, checkpoint_dir=tmp_path, workers=1,
                  worker=_fake_worker(calls), **kw)
    mcl.build("rows", mcl.VALIDATION, checkpoint_dir=tmp_path, workers=1,
              worker=_fake_worker(calls))
    assert calls == ["AAA"] * 4
    assert len({p.parent.name for p in tmp_path.rglob("*.json")}) == 4


def test_the_cli_refuses_before_any_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(mcl, "build", lambda *a, **k: pytest.fail("replayed before refusing"))
    with pytest.raises(SystemExit, match="no-preregistration"):
        mcl.main(["rows", "--window", "train", "--preregistration", str(tmp_path / "x.md")])


def test_the_cli_writes_the_rows_file(tmp_path, monkeypatch):
    seen = {}

    def fake_build(kind, window, **kw):
        seen.update(kind=kind, window=window, **kw)
        return [{"ticker": "AAA"}]

    monkeypatch.setattr(mcl, "require_preregistration", lambda path: None)
    monkeypatch.setattr(mcl, "build", fake_build)
    assert mcl.main(["rows", "--window", "train", "--touch", "--cells", "f0.5",
                     "--preregistration", "p.md", "--out", str(tmp_path)]) == 0
    assert (seen["kind"], seen["window"], seen["touch"]) == ("rows", mcl.TRAIN, True)
    assert list(seen["cells"]) == [0.5]
    assert mcl._load(tmp_path / "v212-rows-train-touch-rows.json") == [{"ticker": "AAA"}]


def test_the_cli_never_builds_validation_rows(monkeypatch):
    monkeypatch.setattr(mcl, "build", lambda *a, **k: pytest.fail("read VALIDATION by hand"))
    for command in ("rows", "census"):
        with pytest.raises(SystemExit):
            mcl.main([command, "--window", "validation", "--preregistration", "p.md"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'measure_confluence_limit'`.

- [ ] **Step 3: Write the script** `scripts/backtest/measure_confluence_limit.py`

```python
#!/usr/bin/env python3
"""v212 confluence limit entry: Stage -1..3 driver (spec § Pass rule).

  census    Stage -1 rows (plans and fills, no outcome)
  rows      outcome rows for a window (--touch: the disclosed touch-fill sensitivity)
  stage     one funnel stage (V212-13c)
  ledger    one preregistration-ledger row per look (V212-13c)

Every command refuses without the committed v212 pre-registration. Rows are
built one ticker at a time and each finished ticker is written to
--checkpoint-dir at once, so a restart skips it; progress prints a flushed
percent. Universe and frames: measure_arms (MEASURE_ARMS_UNIVERSE=cache,
BACKTEST_CACHE_DIR=data/backtest_cache_ext).

Run: python scripts/backtest/measure_confluence_limit.py rows --window train \
         --preregistration docs/superpowers/results/<date>-v212-preregistration.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import confluence_limit_replay as clr  # noqa: E402
from swingbot.core.backtesting.acceptance_exit_funnel import TRAIN, VALIDATION  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v212"
CHECKPOINTS = ROOT / "logs" / "v212-checkpoints"
FOLD_YEARS = (2021, 2022, 2023)
WINDOWS = {"train": TRAIN, "validation": VALIDATION}
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("REACHABLE", "POWERED", "SELECTED", "PASS")
#: PRE-REGISTERED pass clauses (spec § Pass rule). Changing one is a new pre-registration.
FILLS_SHARE = 0.5
WR_SLACK_PP = 2.0
THIN_PER_DIRECTION = 30
DIRECTIONS = ("bullish", "bearish")
CLAUSE_NAMES = ("expr_beats_reference", "fills_half_of_reference", "wr_within_2pp")
KINDS = {"census": clr.census, "rows": clr.replay_entries}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=indent), encoding="utf-8")


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- refusals ------------------------------------------------------------------

def _committed(path: Path) -> bool:
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=ROOT,
                             capture_output=True)
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=ROOT,
                           capture_output=True)
    return tracked.returncode == 0 and clean.returncode == 0


def require_preregistration(path) -> None:
    """Every command refuses before the pre-registration is committed."""
    if path is None or not Path(path).name.endswith("-v212-preregistration.md") \
            or not Path(path).exists():
        _refuse(f"no-preregistration -- pass the committed v212 pre-registration, got {path}")
    if not _committed(Path(path).resolve()):
        _refuse(f"uncommitted-preregistration -- commit {path} before any compute")


# --- stage files ---------------------------------------------------------------

def stage_path(out_dir, stage) -> Path:
    return Path(out_dir) / f"v212-stage{'M1' if stage == -1 else stage}.json"


def rows_file(out_dir, kind, window_name, touch=False) -> Path:
    return Path(out_dir) / f"v212-{kind}-{window_name}{'-touch' if touch else ''}-rows.json"


def _previous(out_dir, stage) -> dict:
    """The verdict JSON `stage` consumes, or a refusal: a closed run never
    advances by hand."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, needed_stage)
    if not path.exists():
        _refuse(f"stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"v212 closed at stage {needed_stage} with {previous['verdict']} "
                f"-- stage {stage} does not run")
    return previous


# --- checkpointed build ----------------------------------------------------------

def universe() -> list[str]:
    from measure_arms import cached_universe
    return cached_universe()


def _worker(task):
    """One ticker, every legacy horizon -- the process-pool entry point."""
    kind, ticker, window, touch, cells = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    extra = {"touch": touch} if kind == "rows" else {}
    return ticker, KINDS[kind](ticker, frame, LEGACY_HORIZONS, window, cells=cells, **extra)


def _tag(kind, window, touch, cells) -> str:
    rule = "touch" if touch else "through"
    return f"{kind}-{window[0]}_{window[1]}-{rule}-{'_'.join(clr.cell_key(c) for c in cells)}"


def _run_tasks(tasks, record, workers, worker) -> None:
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*worker(task))
        return
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for future in as_completed([pool.submit(worker, task) for task in tasks]):
            record(*future.result())


def build(kind, window, *, touch=False, cells=clr.F_GRID, tickers=None, workers=None,
          checkpoint_dir=CHECKPOINTS, worker=None) -> list:
    """Rows for every universe ticker, in ticker order. Each finished ticker
    is persisted at once; a restart loads it instead of replaying it."""
    names = universe()
    names = names[:tickers] if tickers else names
    folder = Path(checkpoint_dir) / _tag(kind, window, touch, cells)
    done = {name: _load(folder / f"{name}.json") for name in names
            if (folder / f"{name}.json").exists()}
    tasks = [(kind, name, tuple(window), touch, tuple(float(c) for c in cells))
             for name in names if name not in done]

    def record(ticker, rows):
        _write(folder / f"{ticker}.json", rows, indent=None)
        done[ticker] = rows
        print(f"  [{kind} {window[0]}..{window[1]}] {len(done)}/{len(names)} "
              f"({len(done) / len(names) * 100:.0f}%) {ticker}: {len(rows)} rows", flush=True)

    _run_tasks(tasks, record, workers, worker or _worker)
    return [row for name in sorted(done) for row in done[name]]


# --- CLI -------------------------------------------------------------------------

def _cells(names) -> tuple:
    return tuple(clr.F_GRID[clr.CELLS.index(name)] for name in names) if names else clr.F_GRID


def _cmd_build(args):
    touch = getattr(args, "touch", False)
    rows = build(args.command, WINDOWS[args.window], touch=touch, cells=_cells(args.cells),
                 tickers=args.tickers, workers=args.workers, checkpoint_dir=args.checkpoint_dir)
    target = rows_file(args.out, args.command, args.window, touch)
    _write(target, rows, indent=None)
    print(f"{args.command} {args.window}: {len(rows)} rows -> {target}", flush=True)
    return 0


COMMANDS = {"census": _cmd_build, "rows": _cmd_build}


def _common(sub) -> None:
    sub.add_argument("--preregistration", type=Path, required=True)
    sub.add_argument("--out", type=Path, default=RESULTS)
    sub.add_argument("--checkpoint-dir", type=Path, default=CHECKPOINTS)
    sub.add_argument("--tickers", type=int, default=None)
    sub.add_argument("--workers", type=int, default=None)


def _parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("census", "rows"):
        sub = subs.add_parser(name)
        _common(sub)
        # VALIDATION rows are built only by `stage --stage 3`, for the selected cell.
        sub.add_argument("--window", choices=["train"], default="train")
        sub.add_argument("--cells", nargs="+", choices=clr.CELLS, default=None)
        if name == "rows":
            sub.add_argument("--touch", action="store_true")
    return parser, subs


def main(argv=None) -> int:
    parser, _ = _parser()
    args = parser.parse_args(argv)
    require_preregistration(args.preregistration)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_limit.py`
Expected: PASS.

- [ ] **Step 5: Complexity gate and the CLI refusal by hand**

```bash
python scripts/dev/complexity_gate.py
python scripts/backtest/measure_confluence_limit.py rows --window train --preregistration nope.md
```
Expected: gate PASS; the second command exits non-zero with `refused: no-preregistration ...`, having replayed nothing.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_confluence_limit.py tests/backtest_scripts/test_measure_confluence_limit.py
git commit -m "feat(v212): measure script -- pre-registration refusal, per-ticker checkpointed build (V212-13)"
```

