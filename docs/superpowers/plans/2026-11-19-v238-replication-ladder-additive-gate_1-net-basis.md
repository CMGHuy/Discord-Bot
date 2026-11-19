# v238 — Replication ladder and additive gate: Part 1, net basis (V238-1..V238-3b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V238-2" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (Part C, "Costs are net on both arms")
**Index:** [2026-11-19-v238-replication-ladder-additive-gate_0-index.md](2026-11-19-v238-replication-ladder-additive-gate_0-index.md) — Goal, `## Global Constraints`, `## Handoff` rulings 2–4, `## Cross-plan contracts (v231)` and `## Parallelisation` live there and bind every task below.

Lane C1, sequential: V238-1 creates `frictions.net_r_legs`; V238-2 (`arms/net_basis.py`) and V238-2b (the engines) book arm rows through it on a requested basis; V238-3 stamps the basis on the arm file and gives `--gate additive` (Part 3) its refusal; V238-3b adds `measure_arms.py --r-basis`. V238-2 and V238-3 were split for the 20 KB task cap (`SPLIT: V238-2 -> V238-2b`, `V238-3 -> V238-3b`); the ledger's V238-2/V238-3 symbols are delivered across each pair. The default (`r_basis=None`) stays byte-identical throughout: today's rows, today's stamp.

# Phase 1 — Net basis

### Task V238-1: Shared net-R function for arm rows

**Model:** sonnet — one pure function with a fixed formula and hand-checkable tests; no seam to judge.

**Files:**
- Modify: `swingbot/core/edge/frictions.py` (docstring, imports, append after `borrow_r`, currently the last function, :36-40)
- Test: `tests/edge/test_edge_frictions.py` (append; suite `edge`)

**Interfaces:**
- Consumes: `frictions.apply_frictions(fill_price, side, slippage_bps=None)`, `frictions.commission_r()`, `frictions.borrow_r(entry, risk, days)` (all exist, `frictions.py:15/:22/:36`).
- Produces (index `## Cross-plan contracts (v231)`, final — v231 cites it by name):
  - `NET_R_SIDES: dict[str, str] = {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}`
  - `net_r_legs(entry: float, stop_loss: float, direction: str, legs: Sequence[Mapping], *, days: float) -> float` — planned `risk = abs(entry - stop_loss)` (never re-based on the fill); entry slipped against the trade (`apply_frictions`, default bps), each leg's `exit_price` slipped on the exit side and weighted by `leg["fraction"]`; minus one `commission_r()`; shorts minus `borrow_r(entry, risk, days)`, longs never read `days`. `ValueError` on no legs, zero risk, unknown direction, or fractions not summing to 1 (±1e-9).

**Why this function and not the two that exist.** `expectancy_attribution.net_r` re-bases risk on the slipped fill and charges no borrow; `screen/sides.net_r` charges borrow but takes one exit price, not legs, and lives in the screen package, which nothing under `swingbot/` outside `swingbot/core/backtesting/` may import (`tests/backtesting/screen/test_import_guard.py`) — v231 calls the net function from live journal code. `net_r_legs` is `sides.net_r`'s formula generalised to weighted exit legs (the `ExitResult.legs` shape `[{"fraction", "exit_price", "r", "reason"}]`, fractions summing to 1 — `swingbot/core/planning/exit_sim.py:702-706`), placed in `swingbot/core/edge/`. Because the fractions sum to 1, commission and borrow are linear: a two-leg result is the fraction-weighted mean of the two one-leg results, which the tests pin. Neither existing function is changed (ruling 3: Turtle Soup's booking under `r_basis=None` stays on `expectancy_attribution.net_r`). Tests may import the screen package (the guard scans `swingbot/` only).

- [ ] **Step 1: Write the failing tests**

In `tests/edge/test_edge_frictions.py`, replace the existing `from swingbot.core.edge.frictions import (...)` statement (lines 6-7) with:

```python
from swingbot.core.edge.frictions import (BORROW_RATE_ANNUAL, NET_R_SIDES, apply_frictions,
                                          borrow_r, commission_r, net_r_legs)
```

Then append at the end of the file:

```python
# --- v238: net_r_legs, the one net-R function for arm rows ----------------------------

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import sides  # noqa: E402


@pytest.fixture
def costs(monkeypatch):
    """Pin the frictions defaults: 5 bps a side, $1 a side on a $100 basis = 0.02R."""
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _leg(price, fraction=1.0):
    return {"fraction": fraction, "exit_price": price, "r": 99.0, "reason": "tp1"}


def test_net_r_legs_long_single_leg_is_the_hand_computed_value(costs):
    # entry 100 slipped to 100.05, exit 106 slipped to 105.947, planned risk 3, commission 0.02
    expected = (106.0 * (1 - 0.0005) - 100.0 * (1 + 0.0005)) / 3.0 - 0.02
    assert net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=4) == pytest.approx(expected, abs=1e-12)


def test_net_r_legs_ignores_the_recorded_leg_r(costs):
    leg = _leg(106.0)
    other = dict(leg, r=-5.0)
    assert net_r_legs(100.0, 97.0, "long", [leg], days=4) == net_r_legs(100.0, 97.0, "long", [other], days=4)


@pytest.mark.parametrize("direction,stop,exit_price,days", [
    ("long", 97.0, 106.0, 4), ("long", 97.0, 95.0, 9),
    ("short", 103.0, 94.0, 10), ("short", 103.0, 104.5, 3),
])
def test_net_r_legs_matches_the_screen_net_r_on_a_single_leg(costs, direction, stop, exit_price, days):
    ours = net_r_legs(100.0, stop, direction, [_leg(exit_price)], days=days)
    screen = sides.net_r(100.0, exit_price, abs(100.0 - stop), direction=direction, days=days)
    assert ours == pytest.approx(float(screen), abs=1e-12)


def test_net_r_legs_risk_is_planned_not_re_based_on_the_fill(costs):
    got = net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=0)
    re_based_risk = 100.05 - 97.0
    re_based = (106.0 * (1 - 0.0005) - 100.05) / re_based_risk - 0.02
    assert got != pytest.approx(re_based, abs=1e-9)


def test_net_r_legs_two_legs_are_the_fraction_weighted_mean_of_one_leg_results(costs):
    for direction, stop, tp1, runner in (("long", 97.0, 103.0, 109.0), ("short", 103.0, 97.0, 91.0)):
        both = net_r_legs(100.0, stop, direction, [_leg(tp1, 0.5), _leg(runner, 0.5)], days=12)
        one = net_r_legs(100.0, stop, direction, [_leg(tp1)], days=12)
        two = net_r_legs(100.0, stop, direction, [_leg(runner)], days=12)
        assert both == pytest.approx(0.5 * one + 0.5 * two, abs=1e-12)


def test_net_r_legs_commission_comes_off_once_not_per_leg(costs):
    flat = [_leg(100.0, 0.25), _leg(100.0, 0.75)]
    # exit at the entry price: only the two slippages and one commission remain
    expected = (100.0 * (1 - 0.0005) - 100.0 * (1 + 0.0005)) / 3.0 - 0.02
    assert net_r_legs(100.0, 97.0, "long", flat, days=5) == pytest.approx(expected, abs=1e-12)


def test_net_r_legs_long_never_reads_days(costs):
    a = net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=0)
    b = net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=365)
    assert a == b


def test_net_r_legs_short_pays_borrow_over_calendar_days(costs):
    same_day = net_r_legs(100.0, 103.0, "short", [_leg(94.0)], days=0)
    held = net_r_legs(100.0, 103.0, "short", [_leg(94.0)], days=30)
    assert same_day - held == pytest.approx(borrow_r(100.0, 3.0, 30), abs=1e-12)
    assert borrow_r(100.0, 3.0, 30) == pytest.approx(100.0 * BORROW_RATE_ANNUAL / 365.0 * 30 / 3.0)


@pytest.mark.parametrize("alias,side", [("bullish", "long"), ("bearish", "short")])
def test_net_r_legs_takes_the_arm_direction_spellings(costs, alias, side):
    stop = 97.0 if side == "long" else 103.0
    assert (net_r_legs(100.0, stop, alias, [_leg(101.0)], days=7)
            == net_r_legs(100.0, stop, side, [_leg(101.0)], days=7))


def test_net_r_sides_maps_every_spelling():
    assert NET_R_SIDES == {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}


def test_net_r_legs_returns_a_plain_float(costs):
    assert type(net_r_legs(100.0, 103.0, "short", [_leg(94.0)], days=3)) is float


@pytest.mark.parametrize("entry,stop,direction,legs,match", [
    (100.0, 97.0, "long", [], "leg"),
    (100.0, 100.0, "long", [_leg(106.0)], "stop distance"),
    (100.0, 97.0, "sideways", [_leg(106.0)], "direction"),
    (100.0, 97.0, "long", [_leg(106.0, 0.5), _leg(104.0, 0.4)], "fractions"),
    (100.0, 97.0, "long", [_leg(106.0, 0.6), _leg(104.0, 0.6)], "fractions"),
])
def test_net_r_legs_refuses_malformed_input(costs, entry, stop, direction, legs, match):
    with pytest.raises(ValueError, match=match):
        net_r_legs(entry, stop, direction, legs, days=1)


def test_net_r_legs_accepts_fractions_within_rounding(costs):
    legs = [_leg(103.0, 0.1), _leg(103.0, 0.2), _leg(103.0, 0.7)]     # 0.1+0.2+0.7 != 1.0 exactly
    assert net_r_legs(100.0, 97.0, "long", legs, days=2) == pytest.approx(
        net_r_legs(100.0, 97.0, "long", [_leg(103.0)], days=2), abs=1e-12)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_frictions.py`
Expected: collection error — `ImportError: cannot import name 'NET_R_SIDES' from 'swingbot.core.edge.frictions'`.

- [ ] **Step 3: Implement `net_r_legs`**

In `swingbot/core/edge/frictions.py`, replace the module docstring and imports (lines 1-12) with:

```python
"""Execution frictions: slippage, commission and (v182) the short borrow fee.

The clean backtest fills at exact trigger/stop/target prices. Real fills
don't. 5 bps of slippage per side and a commission per trade is a
conservative-for-liquid-names model (the E12 liquidity screen is what
makes this assumption defensible). Commission is expressed in R against
a fixed risk basis (default $100 risked/trade = 1% of a $10k account)
so the unit-less backtest can subtract it from r_multiple.

v238: ``net_r_legs`` is the one net-R function for arm rows (replay arms
now, live journal rows in v231): the screen's net formula over weighted
exit legs, borrow charged on shorts only.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from swingbot import config
```

Append at the end of the file:

```python
#: v238: the direction spellings net_r_legs accepts -> the side they trade.
#: Arm rows say bullish/bearish; the screen says long/short.
NET_R_SIDES = {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}

_FRACTION_TOLERANCE = 1e-9


def _checked_side(direction: str, risk: float, legs: Sequence[Mapping]) -> str:
    """The side ``direction`` trades, or ValueError for input net_r_legs cannot price."""
    side = NET_R_SIDES.get(direction)
    if side is None:
        raise ValueError(f"unknown direction {direction!r}; expected one of {sorted(NET_R_SIDES)}")
    if not legs:
        raise ValueError("net_r_legs needs at least one exit leg")
    if risk == 0:
        raise ValueError("net_r_legs needs a non-zero stop distance")
    total = sum(float(leg["fraction"]) for leg in legs)
    if abs(total - 1.0) > _FRACTION_TOLERANCE:
        raise ValueError(f"leg fractions sum to {total!r}, not 1")
    return side


def net_r_legs(entry: float, stop_loss: float, direction: str, legs: Sequence[Mapping], *,
               days: float) -> float:
    """R net of costs for one trade from its entry and its exit legs (v238).

    Risk is the PLANNED stop distance ``abs(entry - stop_loss)``, never re-based on
    the slipped fill (the screen's ``sides.net_r`` convention). The entry is slipped
    against the trade, every leg's ``exit_price`` is slipped on the exit side and
    weighted by its ``fraction``; one round-trip ``commission_r()`` comes off; a short
    also pays ``borrow_r(entry, risk, days)`` over ``days`` calendar days held, a long
    never reads ``days``. A leg's recorded ``r`` is ignored. ValueError on no legs, a
    zero stop distance, an unknown direction, or fractions not summing to 1 (+-1e-9)."""
    entry, stop_loss = float(entry), float(stop_loss)
    risk = abs(entry - stop_loss)
    side = _checked_side(direction, risk, legs)
    is_long = side == "long"
    entry_fill = apply_frictions(entry, "buy" if is_long else "sell")
    sign = 1.0 if is_long else -1.0
    gross = 0.0
    for leg in legs:
        exit_fill = apply_frictions(float(leg["exit_price"]), "sell" if is_long else "buy")
        gross += float(leg["fraction"]) * (exit_fill - entry_fill) * sign / risk
    net = gross - commission_r()
    if not is_long:
        net -= borrow_r(entry, risk, days)
    return float(net)
```

Note the `ValueError` messages: the refusal test matches `"leg"` (no legs), `"stop distance"`, `"direction"` and `"fractions"` — keep those words in the messages.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_frictions.py`
Expected: every test passes, `0 failed`, `0 xfailed` (the existing slippage, commission and borrow tests unchanged).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (both new functions are well under 15).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/frictions.py tests/edge/test_edge_frictions.py
git commit -m "feat(edge): v238 net_r_legs -- one net-R function for arm rows, borrow on shorts only"
```

### Task V238-2: Arm engines book on a requested R basis

**Model:** opus — the basis rules decide what every later net arm means (Turtle Soup, costed instruments, planned risk); the module is small but the semantics are load-bearing for v231.

Split for size (`SPLIT: V238-2 -> V238-2b`): this task creates `arms/net_basis.py` and its unit tests; **V238-2b** threads `r_basis` through `engine.py` and both per-ticker engines. The ledger row's symbols are delivered across the pair.

**Files:**
- Create: `swingbot/core/backtesting/arms/net_basis.py`
- Test: `tests/backtesting/arms/test_net_basis.py` (create; suite `backtesting-arms`)

**Interfaces:**
- Consumes: `frictions.net_r_legs(entry, stop_loss, direction, legs, *, days) -> float` (V238-1). `ExitResult` (`swingbot/core/planning/exit_sim.py:63`: `entry_index`, `exit_index`, `entry_price`, `r_total`, `legs`). `InstrumentSpec.version` (`swingbot/core/backtesting/instrument/contract.py:66`; `"v1"` is the frozen instrument; `resolve(version)` at :155).
- Produces (index ledger and `## Cross-plan contracts (v231)`, final):
  - `net_basis.R_BASES = ("net", "gross")`
  - `net_basis.holding_days(df, result) -> int` — calendar days from `df.index[result.entry_index]` to `df.index[result.exit_index]`.
  - `net_basis.check_basis(r_basis, *, instrument) -> None` — `None` always passes; anything not in `R_BASES` raises `ValueError` (message names `r_basis`); a basis under a non-v1 instrument raises `ValueError` (message names `instrument`).
  - `net_basis.booked_r(plan, result, df, *, r_basis: str) -> float` — `"gross"`: `result.r_total`; `"net"`: `net_r_legs(result.entry_price, plan.stop_loss, plan.direction, result.legs, days=holding_days(df, result))`; anything else (`None` included) `ValueError`.

**Rules this task fixes (index rulings 2–3, `## Decisions this index fixes`).**
- `r_basis=None` is today's booking and never reaches this module (V238-2b keeps the engines' `None` branch on today's code).
- `"net"` books planned risk from the actual fill price (`result.entry_price`, the price the share count would be sized on), both sides slipped, one commission, borrow over calendar days held on shorts only — exactly `net_r_legs`.
- `"gross"` books `result.r_total`, so a `gross` stamp means what it says.
- Any basis under a non-v1 instrument is refused: the v2/v3 instruments already price their own fills and costs into `r_total`, so neither a `net` re-pricing nor a `gross` label would be true. (The index names the `net` case; `gross` is refused for the same reason.)
- `ArmTrade` gains no field (ruling 2).

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/arms/test_net_basis.py`:

```python
"""V238-2: arms.net_basis books one closed trade on a requested R basis. "net" re-prices
the row through frictions.net_r_legs (planned risk, both sides slipped, one commission,
borrow on shorts over calendar days held); "gross" is the walk's r_total. A basis is
refused under any non-v1 instrument."""
import types

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import net_basis
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.edge.frictions import borrow_r, net_r_legs
from swingbot.core.planning.exit_sim import ExitResult

FRIDAY_START = pd.bdate_range("2024-01-05", periods=8)     # 2024-01-05 is a Friday


@pytest.fixture(autouse=True)
def _costs(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _frame():
    return pd.DataFrame({"Close": range(len(FRIDAY_START))}, index=FRIDAY_START)


def _result(entry_index=0, exit_index=1, legs=None, r_total=1.5):
    legs = legs or [{"fraction": 1.0, "exit_price": 108.0, "r": 1.6, "reason": "tp1"}]
    return ExitResult(outcome="win", runner_outcome=None, entry_index=entry_index,
                      exit_index=exit_index, entry_price=100.0, r_total=r_total, legs=legs)


def _long():
    return types.SimpleNamespace(stop_loss=95.0, direction="bullish")


# --- holding_days ----------------------------------------------------------------------

def test_holding_days_counts_calendar_days_over_a_weekend():
    df = _frame()
    assert net_basis.holding_days(df, _result(0, 0)) == 0
    assert net_basis.holding_days(df, _result(0, 1)) == 3          # Friday -> Monday
    assert net_basis.holding_days(df, _result(0, 5)) == 7
    assert type(net_basis.holding_days(df, _result(0, 5))) is int


# --- booked_r --------------------------------------------------------------------------

def test_gross_basis_is_the_walk_r_total():
    assert net_basis.booked_r(_long(), _result(r_total=1.234), _frame(), r_basis="gross") == 1.234


def test_net_basis_prices_every_leg_through_net_r_legs():
    legs = [{"fraction": 0.5, "exit_price": 105.0, "r": 1.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 112.0, "r": 2.4, "reason": "runner_tp2"}]
    result = _result(0, 3, legs=legs, r_total=1.7)              # gross: 0.5 x 1.0 + 0.5 x 2.4
    expected = net_r_legs(100.0, 95.0, "bullish", legs, days=net_basis.holding_days(_frame(), result))
    assert net_basis.booked_r(_long(), result, _frame(), r_basis="net") == expected
    assert expected < result.r_total


def test_net_basis_charges_a_bearish_row_borrow_over_days_held():
    plan = types.SimpleNamespace(stop_loss=105.0, direction="bearish")
    legs = [{"fraction": 1.0, "exit_price": 92.0, "r": 1.6, "reason": "tp1"}]
    short_hold = net_basis.booked_r(plan, _result(0, 1, legs=legs), _frame(), r_basis="net")
    long_hold = net_basis.booked_r(plan, _result(0, 5, legs=legs), _frame(), r_basis="net")
    assert short_hold - long_hold == pytest.approx(borrow_r(100.0, 5.0, 7) - borrow_r(100.0, 5.0, 3), abs=1e-12)


def test_net_basis_never_charges_a_bullish_row_borrow():
    one = net_basis.booked_r(_long(), _result(0, 1), _frame(), r_basis="net")
    seven = net_basis.booked_r(_long(), _result(0, 5), _frame(), r_basis="net")
    assert one == seven


@pytest.mark.parametrize("basis", [None, "bogus", "NET"])
def test_booked_r_refuses_anything_but_net_or_gross(basis):
    with pytest.raises(ValueError, match="r_basis"):
        net_basis.booked_r(_long(), _result(), _frame(), r_basis=basis)


# --- check_basis -----------------------------------------------------------------------

@pytest.mark.parametrize("basis", [None, "net", "gross"])
def test_check_basis_accepts_the_known_bases_under_v1(basis):
    assert net_basis.check_basis(basis, instrument=None) is None
    assert net_basis.check_basis(basis, instrument=resolve("v1")) is None


def test_check_basis_refuses_an_unknown_basis():
    with pytest.raises(ValueError, match="r_basis"):
        net_basis.check_basis("bogus", instrument=None)


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_check_basis_refuses_any_basis_under_a_costed_instrument(basis):
    with pytest.raises(ValueError, match="instrument"):
        net_basis.check_basis(basis, instrument=resolve("v2"))
    assert net_basis.check_basis(None, instrument=resolve("v2")) is None


def test_r_bases_are_net_then_gross():
    assert net_basis.R_BASES == ("net", "gross")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_net_basis.py`
Expected: collection error — `ImportError: cannot import name 'net_basis' from 'swingbot.core.backtesting.arms'`.

- [ ] **Step 3: Create `swingbot/core/backtesting/arms/net_basis.py`**

```python
"""v238: book an arm row on a requested R basis.

``r_basis=None`` -- the default in every engine -- is today's booking and never reaches this
module: gross ``r_total`` for every row, Turtle Soup net through
``turtle_soup_research.net_r`` (v180). A requested basis books every row alike:
``"gross"`` is the walk's ``r_total``; ``"net"`` re-prices the row from its entry fill and
exit legs through ``frictions.net_r_legs`` -- planned risk, both sides slipped, one
round-trip commission, borrow over calendar days held on shorts only -- the one net-R
function v231 also books live journal rows with.

The basis is recorded on the arm FILE (``provenance["r_basis"]``, V238-3), never on a row:
``ArmTrade`` gains no field. A requested basis is refused under any non-v1 instrument, whose
fills and costs already shape ``r_total``.
"""
from __future__ import annotations

from swingbot.core.edge.frictions import net_r_legs

#: The bases an engine may book on (None = today's booking, outside this tuple).
R_BASES = ("net", "gross")


def holding_days(df, result) -> int:
    """Calendar days from the entry bar's date to the exit bar's date (the borrow clock)."""
    return int((df.index[result.exit_index] - df.index[result.entry_index]).days)


def check_basis(r_basis, *, instrument) -> None:
    """Refuse a basis an engine cannot honour: an unknown value, or any basis under an
    instrument other than v1. None always passes (today's booking)."""
    if r_basis is None:
        return
    if r_basis not in R_BASES:
        raise ValueError(f"unknown r_basis {r_basis!r}; expected one of {R_BASES} or None")
    version = "v1" if instrument is None else getattr(instrument, "version", None)
    if version != "v1":
        raise ValueError(f"r_basis={r_basis!r} needs the v1 instrument; instrument {version} "
                         "already prices its own fills and costs into r_total")


def booked_r(plan, result, df, *, r_basis: str) -> float:
    """The R one closed trade books on ``r_basis`` ("net" or "gross")."""
    if r_basis == "gross":
        return result.r_total
    if r_basis == "net":
        return net_r_legs(result.entry_price, plan.stop_loss, plan.direction, result.legs,
                          days=holding_days(df, result))
    raise ValueError(f"unknown r_basis {r_basis!r}; expected one of {R_BASES}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_net_basis.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/net_basis.py tests/backtesting/arms/test_net_basis.py
git commit -m "feat(arms): v238 net_basis -- book one arm row net or gross, refused under costed instruments"
```

### Task V238-2b: Thread r_basis through get_engine, run_arm and both per-ticker engines

**Model:** opus — edits the shared replay engines under every closed pre-registration; the byte-identical default and the Turtle Soup branch need judgement.

Second half of `SPLIT: V238-2 -> V238-2b`; needs V238-2 (`arms/net_basis.py`).

**Files:**
- Modify: `swingbot/core/backtesting/arms/engine.py` (`get_engine` :18-28, `run_arm` :31-42)
- Modify: `swingbot/core/backtesting/arms/confluence_engine.py` (`__init__` :14-16, the `arm_trade_from_plan` call :31-34; new method `_booked_r`)
- Modify: `swingbot/core/backtesting/arms/strategy_engine.py` (module docstring, imports, `__init__` :127-146, `_booked_r` :188-194; new method `_basis_r`)
- Test: `tests/backtesting/arms/test_net_basis_engines.py` (create; suite `backtesting-arms`)

**Interfaces:**
- Consumes: `net_basis.check_basis(r_basis, *, instrument) -> None`, `net_basis.booked_r(plan, result, df, *, r_basis) -> float` (V238-2).
- Produces (index ledger, final):
  - `engine.get_engine(engine_id, *, instrument=None, r_basis=None)`.
  - `engine.run_arm(ticker, df, engine_ids, horizons, signal_window, delta, *, instrument=None, r_basis=None)` — forwards `r_basis` to `get_engine` **only when it is not None**.
  - `ConfluenceEngine(instrument=None, r_basis=None)`; `StrategyEngine(strategies=None, compression_context=None, instrument=None, *, blocked_sink=None, compression_allowlist=None, r_basis=None)`; both expose `.r_basis` and call `check_basis` in `__init__`.

**Rules.**
- `r_basis=None` is today: the confluence engine books `result.r_total` (gross); the strategy engine books gross for every strategy and Turtle Soup net through `turtle_soup_research.net_r`, untouched. `run_arm` passes no `r_basis` keyword under `None`, so every existing fake keeps working (`tests/backtesting/arms/test_engine_instrument.py:79` defines `fake_get_engine(engine_id, *, instrument=None)`).
- A requested basis books **every** row, Turtle Soup included, through `net_basis.booked_r`; the Turtle Soup sidecar event is still logged, carrying the booked R.
- `StrategyEngine`'s first three positional parameters stay `(strategies, compression_context, instrument)` (`test_engine_instrument.py:66` pins them); `r_basis` is keyword-only.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/arms/test_net_basis_engines.py`:

```python
"""V238-2b: get_engine, run_arm and both per-ticker engines carry r_basis. None (the
default) is today's booking, byte for byte, and today's call (no r_basis keyword); a
requested basis books every row -- Turtle Soup included -- through arms.net_basis."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import confluence_engine, engine, net_basis, strategy_engine
from swingbot.core.backtesting.arms import turtle_soup_research as tsr
from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.market.strategy_types import MIN_BARS, TURTLE_SOUP
from swingbot.core.planning.exit_sim import ExitResult, simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

SIGNAL = (100.0, 100.5, 99.5, 100.0)
DRIFT = (101.0, 102.0, 100.5, 101.5)
TARGET = (102.0, 111.0, 101.5, 110.0)
FRIDAY_START = pd.bdate_range("2024-01-05", periods=8)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="RSI", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _frame():
    return pd.DataFrame({"Close": range(len(FRIDAY_START))}, index=FRIDAY_START)


def _result():
    return ExitResult(outcome="win", runner_outcome=None, entry_index=0, exit_index=1,
                      entry_price=100.0, r_total=1.5,
                      legs=[{"fraction": 1.0, "exit_price": 108.0, "r": 1.6, "reason": "tp1"}])


# --- engine seam -----------------------------------------------------------------------

@pytest.mark.parametrize("engine_id", ["strategy", "confluence"])
def test_get_engine_hands_the_basis_to_the_engine(engine_id):
    assert engine.get_engine(engine_id, r_basis="net").r_basis == "net"
    assert engine.get_engine(engine_id).r_basis is None


@pytest.mark.parametrize("engine_id", ["strategy", "confluence"])
def test_get_engine_refuses_a_basis_under_a_costed_instrument(engine_id):
    with pytest.raises(ValueError, match="instrument"):
        engine.get_engine(engine_id, instrument=resolve("v2"), r_basis="net")


@pytest.mark.parametrize("basis,forwarded", [(None, {}), ("net", {"r_basis": "net"}),
                                             ("gross", {"r_basis": "gross"})])
def test_run_arm_forwards_the_basis_only_when_set(monkeypatch, basis, forwarded):
    seen = []

    class Fake:
        def run_ticker(self, ticker, df, horizons, signal_window, params):
            return []

    def fake_get_engine(engine_id, *, instrument=None, **kwargs):
        seen.append(kwargs)
        return Fake()

    monkeypatch.setattr(engine, "get_engine", fake_get_engine)
    kwargs = {} if basis is None else {"r_basis": basis}
    engine.run_arm("T", None, ("strategy", "confluence"), ("4w",), ("2024-01-01", "2024-12-31"), {}, **kwargs)
    assert seen == [forwarded, forwarded]


# --- the confluence engine -------------------------------------------------------------

def _confluence(monkeypatch, r_basis):
    df = make_ohlcv([SIGNAL, DRIFT, TARGET, DRIFT])

    def one_scenario(ticker, signal_df, horizon_key, params=None):
        yield 0, _plan()

    monkeypatch.setattr(confluence_engine, "replay_scenarios", one_scenario)
    window = (str(df.index[0].date()), str(df.index[-1].date()))
    [trade] = ConfluenceEngine(r_basis=r_basis).run_ticker("T", df, ("4w",), window, None)
    return df, trade, simulate_exit(df, 0, _plan(), scale_out=True)


def test_confluence_default_books_the_gross_r_total(monkeypatch):
    _, trade, walk = _confluence(monkeypatch, None)
    assert trade.r_multiple == walk.r_total


def test_confluence_gross_basis_books_the_r_total(monkeypatch):
    _, trade, walk = _confluence(monkeypatch, "gross")
    assert trade.r_multiple == walk.r_total


def test_confluence_net_basis_books_the_net_row(monkeypatch):
    df, trade, walk = _confluence(monkeypatch, "net")
    assert trade.r_multiple == net_basis.booked_r(_plan(), walk, df, r_basis="net")
    assert trade.r_multiple < walk.r_total                        # same prices and risk, costs only subtract


# --- the strategy engine ---------------------------------------------------------------

def _strategy(monkeypatch, r_basis):
    signal = MIN_BARS["4w"]
    df = make_ohlcv([100.0] * signal + [SIGNAL, DRIFT, TARGET] + [100.0] * 8)

    def one_signal(self, frame, strategy, horizon_key):
        bull = pd.Series(False, index=frame.index)
        bull.iloc[signal] = True
        return bull, pd.Series(False, index=frame.index)

    monkeypatch.setattr(StrategyEngine, "_entries", one_signal)
    monkeypatch.setattr(StrategyEngine, "_candidate_plan", lambda self, *a, **k: (_plan(), {}))
    monkeypatch.setattr(strategy_engine, "exit_params_for", lambda strategy: {"tp2": None})
    window = (str(df.index[signal].date()), str(df.index[-1].date()))
    [trade] = StrategyEngine(strategies=("RSI",), r_basis=r_basis).run_ticker("T", df, ("4w",), window, None)
    return df, trade, simulate_exit(df, signal, _plan(), scale_out=True)


def test_strategy_default_books_the_gross_r_total(monkeypatch):
    _, trade, walk = _strategy(monkeypatch, None)
    assert trade.r_multiple == walk.r_total


def test_strategy_net_basis_books_the_net_row(monkeypatch):
    df, trade, walk = _strategy(monkeypatch, "net")
    assert trade.r_multiple == net_basis.booked_r(_plan(), walk, df, r_basis="net")
    assert trade.r_multiple < walk.r_total


def test_strategy_engine_keeps_its_positional_arguments_with_a_basis():
    built = StrategyEngine(("RSI",), None, None, r_basis="gross")
    assert (built.strategies, built.instrument, built.r_basis) == (("RSI",), None, "gross")


def _turtle_events(monkeypatch):
    events = []
    monkeypatch.setattr(tsr, "trade_event",
                        lambda ticker, df, date, plan, result, r_net: events.append(r_net) or {"r": r_net})
    return events


def test_turtle_soup_default_stays_on_its_own_net_function(monkeypatch):
    events = _turtle_events(monkeypatch)
    monkeypatch.setattr(tsr, "net_r", lambda plan, result: 0.123)
    r = StrategyEngine(strategies=("RSI",))._booked_r("T", _frame(), "2024-01-05",
                                                      _plan(strategy=TURTLE_SOUP), _result())
    assert r == 0.123 and events == [0.123]


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_turtle_soup_under_a_basis_is_booked_like_every_other_row(monkeypatch, basis):
    events = _turtle_events(monkeypatch)
    monkeypatch.setattr(tsr, "net_r", lambda plan, result: pytest.fail("the v180 path ran"))
    plan, result = _plan(strategy=TURTLE_SOUP), _result()
    r = StrategyEngine(strategies=("RSI",), r_basis=basis)._booked_r("T", _frame(), "2024-01-05", plan, result)
    assert r == net_basis.booked_r(plan, result, _frame(), r_basis=basis)
    assert events == [r]


def test_a_non_turtle_row_under_a_basis_logs_no_turtle_event(monkeypatch):
    events = _turtle_events(monkeypatch)
    StrategyEngine(strategies=("RSI",), r_basis="net")._booked_r("T", _frame(), "2024-01-05", _plan(), _result())
    assert events == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_net_basis_engines.py`
Expected: FAIL — `TypeError: get_engine() got an unexpected keyword argument 'r_basis'` and `TypeError: ... __init__() got an unexpected keyword argument 'r_basis'`.

- [ ] **Step 3: Thread the basis through `engine.py`**

Replace `get_engine` and `run_arm` in `swingbot/core/backtesting/arms/engine.py` (:18-42) with:

```python
def get_engine(engine_id: str, *, instrument=None, r_basis=None) -> ArmEngine:
    """Construct a registered engine without importing inactive engines.
    ``instrument`` (v157): None is v1; any other spec walks every trade under
    its fills and costs (exit_sim.simulate_exit's seam). ``r_basis`` (v238): None
    books today's rows; "net" / "gross" book every row on that basis (arms.net_basis)."""
    if engine_id == "confluence":
        from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
        return ConfluenceEngine(instrument=instrument, r_basis=r_basis)
    if engine_id == "strategy":
        from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
        return StrategyEngine(instrument=instrument, r_basis=r_basis)
    raise ValueError(f"unknown engine {engine_id!r}; expected one of {DEFAULT_ENGINES}")


def run_arm(ticker: str, df, engine_ids, horizons, signal_window, delta: dict, *,
            instrument=None, r_basis=None) -> list:
    """Run one ticker arm, applying its config globals inside this worker.
    ``instrument`` goes to every engine (get_engine); None is v1. ``r_basis`` (v238)
    is forwarded only when set, so the default call is today's call exactly."""
    from swingbot.scan_params import ScanParams

    basis = {} if r_basis is None else {"r_basis": r_basis}
    with apply_knobs(delta):
        params = ScanParams.from_config()
        out: list = []
        for engine_id in engine_ids:
            out.extend(get_engine(engine_id, instrument=instrument, **basis).run_ticker(
                ticker, df, horizons, signal_window, params))
    return out
```

- [ ] **Step 4: The confluence engine**

In `swingbot/core/backtesting/arms/confluence_engine.py`, add below `from swingbot.core.backtesting.acceptance import arm_trade_from_plan`:

```python
from swingbot.core.backtesting.arms import net_basis
```

Replace `__init__` with:

```python
    def __init__(self, instrument=None, r_basis=None):
        # v157: the backtest instrument every simulate_exit call runs under; None is v1.
        self.instrument = instrument
        # v238: None books today's gross r_total; "net" / "gross" book through arms.net_basis.
        net_basis.check_basis(r_basis, instrument=instrument)
        self.r_basis = r_basis
```

In `run_ticker`, change `r_multiple=result.r_total,` (inside `arm_trade_from_plan(...)`) to `r_multiple=self._booked_r(plan, result, df),` and add below `run_ticker`:

```python
    def _booked_r(self, plan, result, df) -> float:
        """Today's gross r_total under r_basis=None; otherwise the requested basis (v238)."""
        if self.r_basis is None:
            return result.r_total
        return net_basis.booked_r(plan, result, df, r_basis=self.r_basis)
```

- [ ] **Step 5: The strategy engine**

In `swingbot/core/backtesting/arms/strategy_engine.py`, add below `from swingbot.core.backtesting.arms import turtle_soup_research as tsr`:

```python
from swingbot.core.backtesting.arms import net_basis
```

Append one paragraph to the module docstring (after the v180 paragraph, before the closing `"""`):

```
v238: ``StrategyEngine(r_basis=...)`` -- None (the default) keeps the booking above, byte for
byte; "net" or "gross" books EVERY row, Turtle Soup included, through ``arms.net_basis`` (its
sidecar event still logged, with the booked R).
```

Change the `__init__` signature and add two statements after `self.instrument = instrument` (the rest of `__init__` unchanged):

```python
    def __init__(self, strategies=None, compression_context: CompressionResearchContext | None = None,
                 instrument=None, *, blocked_sink: list | None = None,
                 compression_allowlist: tuple | None = None, r_basis=None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)
        self.compression_context = compression_context
        # v157: the backtest instrument every simulate_exit call runs under; None is v1.
        self.instrument = instrument
        # v238: the R basis rows are booked on; None is today's booking (see _booked_r).
        net_basis.check_basis(r_basis, instrument=instrument)
        self.r_basis = r_basis
```

Replace `_booked_r` (:188-194) with:

```python
    def _booked_r(self, ticker, df, date, plan, result) -> float:
        """Gross R for every strategy but Turtle Soup, whose row is booked net and logged (v180).
        Under a requested r_basis (v238) every row is booked through arms.net_basis alike."""
        if self.r_basis is not None:
            return self._basis_r(ticker, df, date, plan, result)
        if plan.strategy != TURTLE_SOUP:
            return result.r_total
        r_net = tsr.net_r(plan, result)
        self.turtle_soup_events.append(tsr.trade_event(ticker, df, date, plan, result, r_net))
        return r_net

    def _basis_r(self, ticker, df, date, plan, result) -> float:
        """One row on the requested basis; a Turtle Soup row still logs its sidecar event."""
        r = net_basis.booked_r(plan, result, df, r_basis=self.r_basis)
        if plan.strategy == TURTLE_SOUP:
            self.turtle_soup_events.append(tsr.trade_event(ticker, df, date, plan, result, r))
        return r
```

- [ ] **Step 6: Run the new tests and the byte-identical guards**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_net_basis_engines.py`
Expected: every test passes, `0 failed`.

Run each (the default must be untouched; no existing test is edited):
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_engine_instrument.py`
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py`
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_confluence_engine.py`
- `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_baseline_delta.py`

Expected: all green, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/arms/engine.py swingbot/core/backtesting/arms/confluence_engine.py \
        swingbot/core/backtesting/arms/strategy_engine.py tests/backtesting/arms/test_net_basis_engines.py
git commit -m "feat(arms): v238 r_basis through get_engine, run_arm and both engines, default byte-identical"
```

### Task V238-3: r_basis stamp and refusal token in provenance

**Model:** sonnet — additive kwarg and one checker following the v192 `baseline_knob_delta` precedent exactly; the contract is fixed in the index.

Split for size (`SPLIT: V238-3 -> V238-3b`): this task is the stamp, the token and `check_r_basis`; **V238-3b** is the producer flag in `measure_arms.py`. Needs V238-2 (`net_basis.R_BASES`).

**Files:**
- Modify: `swingbot/core/backtesting/arms/provenance.py` (imports and constants :9-14, `build_stamp` :36-53; new `check_r_basis` after `check_stamp`)
- Test: `tests/backtesting/arms/test_provenance.py` (append; suite `backtesting-arms`)

**Interfaces:**
- Consumes: `net_basis.R_BASES` (V238-2).
- Produces (index `## Cross-plan contracts (v231)`, final):
  - `provenance.R_BASIS_KEY = "r_basis"`; `provenance.R_BASES = ("net", "gross")` (the same object as `net_basis.R_BASES`).
  - `provenance.R_BASIS_REFUSAL = "refused:r-basis"`, appended **last** to `REFUSAL_TOKENS` (the six existing tokens keep their order).
  - `build_stamp(..., preregistration=None, baseline_knob_delta=None, r_basis=None)` — writes `stamp["r_basis"]` only when not None (`ValueError` for a value outside `R_BASES`), so a stamp built without it is key-for-key today's stamp.
  - `check_r_basis(blob: dict, *, required: str = "net") -> str | None` — `R_BASIS_REFUSAL` for a missing `provenance`, a missing key, or any value other than `required`; `None` otherwise. `check_stamp` is **not edited** and never returns this token (rulings 2, 6); V238-7 calls `check_r_basis` from `--gate additive` only.

- [ ] **Step 1: Write the failing provenance tests**

Append to `tests/backtesting/arms/test_provenance.py`:

```python
# --- v238: the r_basis stamp and its refusal -----------------------------------------

from swingbot.core.backtesting.arms import net_basis  # noqa: E402

TODAYS_KEYS = {"producer", "producer_version", "stage", "signal_window", "universe", "universe_count",
               "horizons", "engines", "knob_delta", "engine_hash", "changed_outcomes",
               "preregistration", "git_head", "created_at"}


def test_a_stamp_without_a_basis_is_key_for_key_todays_stamp():
    assert set(stamp()["provenance"]) == TODAYS_KEYS
    assert set(stamp(r_basis=None)["provenance"]) == TODAYS_KEYS


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_a_basis_is_written_under_its_key_beside_todays_keys(basis):
    prov = stamp(r_basis=basis)["provenance"]
    assert prov[pv.R_BASIS_KEY] == basis
    assert set(prov) == TODAYS_KEYS | {"r_basis"}


def test_build_stamp_refuses_an_unknown_basis():
    with pytest.raises(ValueError, match="r_basis"):
        stamp(r_basis="NET")


def test_the_r_basis_constants_are_the_contract():
    assert pv.R_BASIS_KEY == "r_basis"
    assert pv.R_BASES == ("net", "gross")
    assert pv.R_BASES is net_basis.R_BASES
    assert pv.R_BASIS_REFUSAL == "refused:r-basis"


def test_the_basis_token_is_appended_last_and_the_others_keep_their_order():
    assert pv.REFUSAL_TOKENS == ("refused:unstamped", "refused:stage-mismatch", "refused:engine-mismatch",
                                 "refused:window-contact", "refused:narrow-universe", "refused:zero-diff",
                                 "refused:r-basis")


def test_check_r_basis_passes_a_net_stamp():
    assert pv.check_r_basis(stamp(r_basis="net")) is None


@pytest.mark.parametrize("blob", [
    stamp(),                                              # today's stamp: no key
    stamp(r_basis="gross"),
    {"baseline": [], "component": []},                    # unstamped
    {"provenance": None},
    {"provenance": {"r_basis": ["net"]}},                 # malformed
    {"provenance": {"r_basis": "Net"}},
], ids=["no-key", "gross", "unstamped", "null-provenance", "list-value", "wrong-case"])
def test_check_r_basis_refuses_anything_but_net(blob):
    assert pv.check_r_basis(blob) == pv.R_BASIS_REFUSAL
    assert pv.R_BASIS_REFUSAL in pv.REFUSAL_TOKENS


def test_check_r_basis_honours_the_required_basis():
    assert pv.check_r_basis(stamp(r_basis="gross"), required="gross") is None
    assert pv.check_r_basis(stamp(r_basis="net"), required="gross") == pv.R_BASIS_REFUSAL


@pytest.mark.parametrize("basis", [None, "net", "gross"])
def test_check_stamp_never_reads_the_basis(basis):
    assert pv.check_stamp(stamp(r_basis=basis), funnel_stage="mde", full_universe=UNIVERSE) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_provenance.py`
Expected: FAIL — `TypeError: build_stamp() got an unexpected keyword argument 'r_basis'` and `AttributeError: module ... has no attribute 'R_BASIS_KEY'`; the six existing tests still pass.

- [ ] **Step 3: Implement the stamp and the refusal in `provenance.py`**

Replace lines 9-14 of `swingbot/core/backtesting/arms/provenance.py` (the `windows` import through `REFUSAL_TOKENS`) with:

```python
from swingbot.core.backtesting.arms.net_basis import R_BASES
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, FUNNEL_TO_PRODUCER_STAGE, VALIDATION_START

PRODUCER_VERSION = 1
SWINGBOT_ROOT = Path(__file__).resolve().parents[3]
#: v238: the arm file's R basis stamp (values R_BASES, re-exported from arms.net_basis)
#: and the refusal the additive gate returns for a file not stamped net.
R_BASIS_KEY = "r_basis"
R_BASIS_REFUSAL = "refused:r-basis"
REFUSAL_TOKENS = ("refused:unstamped", "refused:stage-mismatch", "refused:engine-mismatch",
                  "refused:window-contact", "refused:narrow-universe", "refused:zero-diff",
                  R_BASIS_REFUSAL)
```

Replace `build_stamp` with:

```python
def build_stamp(*, stage, signal_window, universe, horizons, engines, knob_delta,
                engine_hash_baseline, engine_hash_component, changed_outcomes,
                preregistration=None, baseline_knob_delta=None, r_basis=None) -> dict:
    """The producer stamp. ``baseline_knob_delta`` (v192) is the config delta the BASELINE arm
    ran under; it is written only when non-empty, so a stamp made without one is key-for-key
    the pre-v192 stamp. ``r_basis`` (v238) is the basis both arms were booked on ("net" or
    "gross"); written only when not None, for the same reason."""
    stamp = {"producer": "measure_arms", "producer_version": PRODUCER_VERSION,
             "stage": stage, "signal_window": list(signal_window), "universe": sorted(universe),
             "universe_count": len(universe), "horizons": list(horizons), "engines": list(engines),
             "knob_delta": dict(knob_delta),
             "engine_hash": {"baseline": engine_hash_baseline, "component": engine_hash_component},
             "changed_outcomes": int(changed_outcomes), "preregistration": preregistration,
             "git_head": git_head(),
             "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    if baseline_knob_delta:
        stamp["baseline_knob_delta"] = dict(baseline_knob_delta)
    if r_basis is not None:
        if r_basis not in R_BASES:
            raise ValueError(f"unknown r_basis {r_basis!r}; expected one of {R_BASES}")
        stamp[R_BASIS_KEY] = r_basis
    return stamp
```

Leave `check_stamp` exactly as it is. Append after it:

```python
def check_r_basis(blob: dict, *, required: str = "net") -> str | None:
    """v238: R_BASIS_REFUSAL unless the arm file is stamped ``r_basis == required``.

    Refuses a missing stamp, a stamp without the key (every file produced before v238) and
    any other value. Called by ``validate_component --gate additive`` only -- under
    ``--bespoke-instrument`` too, since net arms are a precondition of that gate -- and never
    from ``check_stamp``, so the v72/v92 gates load stamp-less and gross files unchanged."""
    stamp = blob.get("provenance") if isinstance(blob, dict) else None
    if not isinstance(stamp, dict) or stamp.get(R_BASIS_KEY) != required:
        return R_BASIS_REFUSAL
    return None
```

- [ ] **Step 4: Run the provenance tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_provenance.py`
Expected: every test passes, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/provenance.py tests/backtesting/arms/test_provenance.py
git commit -m "feat(arms): v238 provenance r_basis stamp and refused:r-basis, check_stamp untouched"
```

### Task V238-3b: measure_arms --r-basis books and stamps both arms

**Model:** sonnet — threads one keyword through the producer and adds one flag and one refusal, mirroring `--baseline-knob`; the contract is fixed in the index.

Second half of `SPLIT: V238-3 -> V238-3b`; needs V238-2b (`run_arm(..., r_basis=)`) and V238-3 (`build_stamp(r_basis=)`, `provenance.R_BASES`).

**Files:**
- Modify: `scripts/backtest/measure_arms.py` (module docstring :2-8, import :27, `_refusal` :108-111, `_worker` :134-143, `_run_arm_all` :154-170, `produce` :217-248, `main` :362-399)
- Test: `tests/backtest_scripts/test_measure_arms_r_basis.py` (create; suite `backtest-scripts`)

**Interfaces:**
- Consumes: `engine.run_arm(..., *, instrument=None, r_basis=None)` (V238-2b, forwards `r_basis` only when set); `provenance.build_stamp(..., r_basis=None)` and `provenance.R_BASES` (V238-3).
- Produces (index ledger, final):
  - `measure_arms.produce(..., preregistration=None, r_basis=None)` — books both arms on `r_basis` and stamps it; `ValueError` when a population engine would run (scan-replay rows are not booked by `net_basis`; index decision).
  - CLI `measure_arms.py --r-basis {net,gross}` (absent = today's booking, no stamp key); a population knob with `--r-basis` is refused before any compute with `refused:r-basis-population`, exit 1.

- [ ] **Step 1: Write the failing producer tests**

Create `tests/backtest_scripts/test_measure_arms_r_basis.py`:

```python
"""V238-3: measure_arms --r-basis books both arms on the requested basis and stamps
provenance["r_basis"]. Without the flag every call, row and stamp is today's. A population
engine's rows are not booked by arms.net_basis, so --r-basis with a population knob is
refused before any compute."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.arms.windows import StageSpec  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402

FIXTURE = load_v74_fixture()
PILOT = StageSpec("pilot", ("2024-01-01", "2025-12-31"), full_width=False)
NEXT_OPEN = {"MARKET_ENTRY_NEXT_OPEN": True}


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    monkeypatch.setattr(ma, "load_frame", lambda ticker: FIXTURE.get(ticker))
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAPL"])
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    yield
    training_data.reset()


def _recording(monkeypatch):
    seen = []

    def fake_run_arm(ticker, frame, engine_ids, horizons, signal_window, delta, **kwargs):
        seen.append(kwargs)
        return []
    monkeypatch.setattr(ma, "run_arm", fake_run_arm)
    return seen


def _produce(**kw):
    return ma.produce("pilot", NEXT_OPEN, universe=["AAPL"], spec=PILOT, horizons=("4w",),
                      engines=("confluence",), workers=1, **kw)


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_produce_books_both_arms_on_the_basis_and_stamps_it(monkeypatch, basis):
    seen = _recording(monkeypatch)
    blob = _produce(r_basis=basis)
    assert seen == [{"r_basis": basis}, {"r_basis": basis}]          # baseline, then component
    assert blob["provenance"]["r_basis"] == basis


def test_produce_without_a_basis_is_todays_call_and_stamp(monkeypatch):
    seen = _recording(monkeypatch)
    blob = _produce()
    assert seen == [{}, {}]
    assert "r_basis" not in blob["provenance"]


def test_net_rows_are_the_same_trades_repriced():
    default = _produce()
    net = _produce(r_basis="net")
    assert default["baseline"], "the v74 fixture yields 4w confluence trades in the pilot window"

    def keys(rows):
        return [(r["ticker"], r["strategy"], r["horizon_key"], r["entry_date"], r["outcome"]) for r in rows]

    assert keys(net["baseline"]) == keys(default["baseline"])
    assert keys(net["component"]) == keys(default["component"])
    assert all(n["r_multiple"] < d["r_multiple"] for n, d in zip(net["component"], default["component"]))


def test_produce_refuses_a_basis_on_the_population_path(monkeypatch):
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop")
    monkeypatch.setattr(ma, "_produce_population", lambda *a, **k: pytest.fail("computed"))
    with pytest.raises(ValueError, match="population"):
        ma.produce("pilot", NEXT_OPEN, universe=["AAPL"], spec=PILOT, horizons=("4w",), workers=1,
                   r_basis="net")


def _main(tmp_path, *extra):
    return ma.main(["--knob", "MIN_REWARD_PCT=4", "--stage", "pilot",
                    "--out", str(tmp_path / "arms.json"), "--workers", "1", *extra])


def _capture_produce(monkeypatch):
    captured = {}

    def fake_produce(stage, delta, **kw):
        captured.update(kw)
        return {"provenance": {"changed_outcomes": 3}}
    monkeypatch.setattr(ma, "produce", fake_produce)
    monkeypatch.setattr(ma, "_write_sidecar_or_warn", lambda *a: None)
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    return captured


@pytest.mark.parametrize("extra,expected", [((), None), (("--r-basis", "net"), "net"),
                                            (("--r-basis", "gross"), "gross")])
def test_main_passes_the_basis_to_produce(monkeypatch, tmp_path, extra, expected):
    captured = _capture_produce(monkeypatch)
    assert _main(tmp_path, *extra) == 0
    assert captured["r_basis"] == expected


def test_main_rejects_an_unknown_basis(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _main(tmp_path, "--r-basis", "NET")
    assert exc.value.code == 2


def test_main_refuses_a_basis_with_a_population_knob_before_any_compute(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(ma, "produce", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop" if "MIN_REWARD_PCT" in delta else None)
    monkeypatch.setattr(ma, "get_population_engine", lambda engine_id, **kw: object())
    assert _main(tmp_path, "--r-basis", "net") == 1
    assert "refused:r-basis-population" in capsys.readouterr().err
    assert not (tmp_path / "arms.json").exists()


def test_a_population_knob_without_a_basis_is_not_refused_by_the_basis_check(monkeypatch, tmp_path):
    captured = _capture_produce(monkeypatch)
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop" if "MIN_REWARD_PCT" in delta else None)
    monkeypatch.setattr(ma, "get_population_engine", lambda engine_id, **kw: object())
    assert _main(tmp_path) == 0
    assert captured["r_basis"] is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_r_basis.py`
Expected: FAIL — `TypeError: produce() got an unexpected keyword argument 'r_basis'`, and `--r-basis` unrecognised (`SystemExit: 2` where 0 is expected).

- [ ] **Step 3: Implement the producer flag in `measure_arms.py`**

Module docstring: add one line after the last `v192:` line:

```
v238: --r-basis {net,gross} books BOTH arms on that basis (arms.net_basis) and stamps provenance["r_basis"]; absent = today.
```

Import: change line 27 to

```python
from swingbot.core.backtesting.arms.provenance import R_BASES, build_stamp, code_hash  # noqa: E402
```

Replace `_refusal` (:108-111) with these two functions:

```python
def _basis_refusal(delta: dict, r_basis):
    """v238: a population engine's rows are not booked by arms.net_basis, so a basis is refused there."""
    engine_id = population_engine_for(delta)
    if r_basis is None or engine_id is None:
        return None
    return "refused:r-basis-population", (
        f"{engine_id} rows are not booked by arms.net_basis; --r-basis needs the per-ticker engines.")


def _refusal(delta: dict, baseline_delta: dict, r_basis=None):
    """The first static or population refusal over the component delta, then the baseline delta,
    then (v238) the basis refusal."""
    return (static_refusal(delta) or population_refusal(delta) or static_refusal(baseline_delta)
            or population_refusal(baseline_delta) or _baseline_population_refusal(delta, baseline_delta)
            or _basis_refusal(delta, r_basis))
```

Replace `_worker` (:134-143) with:

```python
def _worker(task):
    ticker, engine_ids, horizons, signal_window, delta, r_basis = task
    basis = {} if r_basis is None else {"r_basis": r_basis}      # v238: today's call when unset
    try:
        frame = load_frame(ticker)
        if frame is None:
            raise RuntimeError("no cached frame")
        trades = run_arm(ticker, frame, engine_ids, horizons, signal_window, delta, **basis)
    except Exception as exc:
        raise RuntimeError(f"{ticker}: {exc!r}") from exc
    return ticker, trades
```

In `_run_arm_all`, change the signature and the task tuple (the rest unchanged):

```python
def _run_arm_all(label, universe, engines, horizons, signal_window, delta, workers, progress_path, counter, total,
                 r_basis=None):
    tasks = [(ticker, tuple(engines), tuple(horizons), signal_window, delta, r_basis) for ticker in universe]
```

Replace `produce`'s signature, docstring and body up to the `stamp = build_stamp(...)` statement (:217-238) with:

```python
def produce(stage, delta, *, universe, baseline_delta=None, spec=None, horizons=None, engines=DEFAULT_ENGINES,
            workers=None, progress_path=None, preregistration=None, r_basis=None) -> dict:
    """v192: ``baseline_delta`` is the baseline arm's own config delta (default none, today's
    baseline); the stamp records it as ``baseline_knob_delta`` when non-empty. v238: ``r_basis``
    ("net" / "gross") books both arms on that basis and is stamped; None is today's booking.
    A basis on the population path raises ValueError (its rows are not booked by net_basis)."""
    spec = spec or windows.resolve(stage)
    horizons = tuple(horizons or windows.ALL_HORIZONS)
    baseline_delta = dict(baseline_delta or {})
    population = population_engine_for(delta)
    if population is not None and r_basis is not None:
        raise ValueError(f"r_basis={r_basis!r}: population engine {population} rows are not booked by arms.net_basis")
    if population is not None:
        engines = (population,)
        baseline_hash, baseline, component_hash, component = _produce_population(
            population, universe, horizons, spec.signal_window, delta, baseline_delta)
    else:
        workers = _resolve_replay_workers(workers)
        total, counter = 2 * len(universe), [0]
        baseline_hash = code_hash()
        baseline = _run_arm_all("baseline", universe, engines, horizons, spec.signal_window, baseline_delta,
                                workers, progress_path, counter, total, r_basis=r_basis)
        component_hash = code_hash()
        component = _run_arm_all("component", universe, engines, horizons, spec.signal_window, delta,
                                 workers, progress_path, counter, total, r_basis=r_basis)
    stamp = build_stamp(stage=stage, signal_window=spec.signal_window, universe=universe, horizons=horizons,
                        engines=engines, knob_delta=delta, engine_hash_baseline=baseline_hash,
                        engine_hash_component=component_hash, changed_outcomes=changed_outcomes(baseline, component),
                        preregistration=preregistration, baseline_knob_delta=baseline_delta, r_basis=r_basis)
```

(the `blob = ...` lines after the stamp stay as they are).

In `main`: add the argument after `--preregistration`:

```python
    parser.add_argument("--r-basis", dest="r_basis", choices=R_BASES, default=None,
                        help="v238: book both arms net or gross and stamp provenance['r_basis'] "
                             "(default: today's booking, no stamp key; --gate additive needs net)")
```

change `refusal = _refusal(delta, baseline_delta)` to `refusal = _refusal(delta, baseline_delta, args.r_basis)`, and add `r_basis=args.r_basis` to the `produce(...)` call:

```python
    blob = produce(args.stage, delta, universe=universe, baseline_delta=baseline_delta, workers=args.workers,
                   progress_path=progress, preregistration=str(args.preregistration) if args.preregistration else None,
                   r_basis=args.r_basis)
```

- [ ] **Step 4: Run the producer tests and the untouched neighbours**

Run each:
- `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_r_basis.py`
- `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms.py`
- `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_baseline_delta.py`
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_provenance.py`

Expected: all green, `0 failed`, `0 xfailed`; no existing test edited (the recording fakes in `test_measure_arms_baseline_delta.py` take no keyword arguments, which is why `_worker` passes `r_basis` only when set).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`produce` rises from 9 to 11, `_refusal` from 5 to 6; `main` unchanged at 9).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_arms.py tests/backtest_scripts/test_measure_arms_r_basis.py
git commit -m "feat(measure_arms): v238 --r-basis books both arms net or gross and stamps it"
```

