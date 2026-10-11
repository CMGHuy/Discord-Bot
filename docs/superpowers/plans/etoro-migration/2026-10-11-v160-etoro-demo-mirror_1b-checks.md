# v160 eToro demo mirror, part 1b: order checks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task EM5" -A 400 <this file>`; never read the plan whole.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)

**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md` carries the Global Constraints, the `## Parallelisation` table and the task ledger. Every task below implicitly includes those constraints. This file holds **EM4–EM5** (Phase 2, `checks.py`), which the index assigns to part 1; they live here because part 1 (`_1-foundations-and-checks.md`, EM1–EM3) would otherwise pass the 1500-line cap.

**Shell variables used in every task** (Git Bash; never `cd`):

```bash
REPO="E:/Documents/Private/Projects/Discord-Bot"
WT="$REPO/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror"
```

## Parallelisation (this file)

EM4 after EM1 (EM3's `sizing` constants are imported, so after EM3 too); it may run beside EM7 from part 2. EM5 after EM4: same file (`checks.py`), it appends to `_OPEN_CHECKS`. EM6 (part 2) consumes `check_stop_move` from EM4 and may run beside EM5.

# Phase 2 (continued): order checks

### Task EM4: `checks.py` I: inputs, eligibility parsing, stop/size checks, `check_stop_move`

**Model:** sonnet — a pure, table-driven module whose every branch is spelled out by the spec's check table; NaN handling is the one subtlety and is pinned by tests.

Spec § Sizing and order checks (the order-check table through `above_max_units`; "Stops only tighten"), § Event mapping (settlement rule: a long is `real` when eligible at leverage 1, else `cfd`; a short is `cfd`). Index § Global Constraints (`no_position`, Units precision).

**Files:**
- Create: `swingbot/core/broker/checks.py`
- Create: `tests/broker/test_checks.py`

**Interfaces:**
- Consumes: `swingbot.core.risk_limits.capped_planned_loss_pct(configured_pct) -> float` and `planned_loss_pct(entry_price, stop_loss) -> float` (inf when invalid) (`swingbot/core/risk_limits.py:12`, `:17`); `sizing.WHOLE_UNIT_DECIMALS`, `sizing.FRACTIONAL_UNIT_DECIMALS` (EM3); `config.ETORO_MAX_TRADE_USD` (EM1), `config.MAX_STOP_LOSS_PCT` (`config.py:182`), the `risk_pct` the sizer used (`planning.account.compute_position_size(...)["risk_pct"]`; NOT `config.RISK_PER_TRADE_PCT`, which is informational only, default 0.01 -- controller decision 2026-10-11), `config.PORTFOLIO_HEAT_CAP_PCT` (`config.py:518`), `config.CORRELATED_HEAT_CAP_PCT` (`config.py:524`).
- Produces (EM5, EM6, EM8 rely on these exact names):
  - `SKIP_REASONS = ("no_trade_cap", "no_stop", "ineligible", "stop_breached", "stop_cap", "stop_too_tight", "dollar_risk", "zero_units", "below_min_exposure", "above_max_units", "portfolio_heat", "correlated_heat", "stop_widen", "no_position")`
  - `@dataclass(frozen=True) OpenOrder(ticker: str, direction: str, entry: float, stop: float | None, units: float)`: `direction` is `TradePlanV2.direction` (`"bullish"`/`"bearish"`), `entry` the plan's paper fill, `stop` the rounded `plan.stop_loss`, `units` from `sizing.mirror_units`.
  - `@dataclass(frozen=True) Quote(bid: float, ask: float, at: str)`
  - `@dataclass(frozen=True) Eligibility(instrument_id: int, symbol: str, allow_open: bool, settlement_type: str | None, min_exposure_usd: float, max_units: float | None, min_stop_pct: float | None, max_stop_pct: float | None, unit_decimals: int)`
  - `@dataclass(frozen=True) MirrorBook(open_trades: tuple, balance: float, dfs: dict, sectors: dict | None)`: `open_trades` holds the mirror's open `open` rows exactly as `BrokerOrderRepository.open_positions()` returns them (flat records with `ticker`, `avg_price`, `stop_sent`, `units_filled`); `balance` is the sizing balance (`compute_position_size(...)["balance"]`).
  - `@dataclass(frozen=True) CheckConfig(max_trade_usd: float, max_stop_loss_pct: float, risk_per_trade_pct: float, portfolio_heat_cap_pct: float, correlated_heat_cap_pct: float)` with `CheckConfig.from_config(risk_pct: float) -> CheckConfig` (reads the four settings at call time; `risk_pct` is the sizer's risk % for this order, passed in by the executor).
  - `resolve_settlement(leverage_configs: list, direction: str) -> str | None`
  - `parse_eligibility(body: object, symbol: str, direction: str) -> Eligibility | None`
  - `order_price(direction: str, quote: Quote) -> float`: `quote.ask` for `"bullish"`, `quote.bid` otherwise.
  - `check_open(order: OpenOrder, quote: Quote, eligibility: Eligibility | None, book: MirrorBook, cfg: CheckConfig) -> str | None`, the first failing entry of `_OPEN_CHECKS`.
  - `_OPEN_CHECKS: list[Callable[[OpenOrder, Quote, Eligibility | None, MirrorBook, CheckConfig], str | None]]`, in this order: `_check_trade_cap`, `_check_stop_present`, `_check_eligible`, `_check_stop_breached`, `_check_stop_cap`, `_check_stop_bounds`, `_check_dollar_risk`, `_check_zero_units`, `_check_min_exposure`, `_check_max_units` (EM5 appends two).
  - `check_stop_move(direction: str, last_stop: float | None, new_stop: float | None) -> str | None`: `"stop_widen"` or `None`.

**Semantics fixed here (the spec leaves them open):**
- Every cap comparison is `value <= cap + 1e-9` (the tolerance `entry_filters.py` and `edge/heat.py` use), written so a NaN compares as a breach: a non-finite quote, stop or size is skipped, never sent.
- `stop_cap` compares against `capped_planned_loss_pct(MAX_STOP_LOSS_PCT)`, from the plan entry **and** from the order price (ask for a long, bid for a short).
- `stop_too_tight` (eToro's bounds) measures the stop distance from the order price, as a percent of it, against the leverage config of the resolved settlement type, falling back to the eligibility item's own `minStopLossPercentage`/`maxStopLossPercentage`. A missing bound is not checked.
- `below_min_exposure` uses `units × order price`. Eligibility symbols match case-insensitively and exactly; no other item is ever used for a ticker.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/broker/test_checks.py`:

```python
"""broker.checks (v160), part I: every order-risk check the mirror owns up to
`above_max_units`, eligibility parsing, and stops-only-tighten. Pure: no DB,
no network, no clock. Heat checks are tests/broker/test_checks_heat.py."""
import ast
import inspect

import pytest

from swingbot import config
from swingbot.core.broker import checks
from swingbot.core.broker.checks import (
    SKIP_REASONS, CheckConfig, Eligibility, MirrorBook, OpenOrder, Quote, check_open,
    check_stop_move, order_price, parse_eligibility, resolve_settlement)

NAN = float("nan")
QUOTE = Quote(bid=99.9, ask=100.1, at="2026-10-12T14:30:00+00:00")
BOOK = MirrorBook(open_trades=(), balance=10_000.0, dfs={}, sectors=None)


def _order(**kw):
    base = dict(ticker="AAPL", direction="bullish", entry=100.0, stop=98.5, units=0.9)
    base.update(kw)
    return OpenOrder(**base)


def _short(**kw):
    return _order(direction="bearish", stop=101.5, **kw)


def _elig(**kw):
    base = dict(instrument_id=1001, symbol="AAPL", allow_open=True, settlement_type="real",
                min_exposure_usd=10.0, max_units=1000.0, min_stop_pct=0.5, max_stop_pct=75.0,
                unit_decimals=4)
    base.update(kw)
    return Eligibility(**base)


def _cfg(**kw):
    base = dict(max_trade_usd=100.0, max_stop_loss_pct=2.0, risk_per_trade_pct=2.0,
                portfolio_heat_cap_pct=6.0, correlated_heat_cap_pct=3.0)
    base.update(kw)
    return CheckConfig(**base)


def _check(order=None, quote=QUOTE, elig=None, book=BOOK, cfg=None):
    return check_open(order or _order(), quote, _elig() if elig is None else elig,
                      book, cfg or _cfg())


# --- the vocabulary and the order ------------------------------------------------

def test_skip_reasons_are_the_spec_table_plus_no_position():
    assert SKIP_REASONS == (
        "no_trade_cap", "no_stop", "ineligible", "stop_breached", "stop_cap",
        "stop_too_tight", "dollar_risk", "zero_units", "below_min_exposure",
        "above_max_units", "portfolio_heat", "correlated_heat", "stop_widen", "no_position")


def test_the_checks_run_in_the_spec_order():
    names = [check.__name__ for check in checks._OPEN_CHECKS]
    assert names[:10] == [
        "_check_trade_cap", "_check_stop_present", "_check_eligible", "_check_stop_breached",
        "_check_stop_cap", "_check_stop_bounds", "_check_dollar_risk", "_check_zero_units",
        "_check_min_exposure", "_check_max_units"]


def test_the_first_failing_check_is_the_reason():
    assert _check(_order(stop=None), cfg=_cfg(max_trade_usd=0.0)) == "no_trade_cap"
    assert _check(_order(stop=None), elig=False) == "no_stop"


def test_a_clean_long_and_a_clean_short_pass():
    assert _check() is None
    assert _check(_short(), elig=_elig(settlement_type="cfd")) is None


# --- one test per skip reason ------------------------------------------------------

@pytest.mark.parametrize("cap", [0.0, -1.0, NAN])
def test_no_trade_cap(cap):
    assert _check(cfg=_cfg(max_trade_usd=cap)) == "no_trade_cap"


@pytest.mark.parametrize("stop", [None, NAN, 0.0])
def test_no_stop(stop):
    assert _check(_order(stop=stop)) == "no_stop"


def test_ineligible():
    assert check_open(_order(), QUOTE, None, BOOK, _cfg()) == "ineligible"
    assert _check(elig=_elig(allow_open=False)) == "ineligible"
    assert _check(elig=_elig(settlement_type=None)) == "ineligible"


def test_stop_breached_long_at_or_above_the_bid():
    assert _check(_order(stop=99.9)) == "stop_breached"
    assert _check(_order(stop=99.95)) == "stop_breached"


def test_stop_breached_short_at_or_below_the_ask():
    elig = _elig(settlement_type="cfd")
    assert _check(_order(direction="bearish", stop=100.1), elig=elig) == "stop_breached"
    assert _check(_order(direction="bearish", stop=100.0), elig=elig) == "stop_breached"


def test_a_non_finite_quote_is_never_sent():
    assert _check(quote=Quote(bid=NAN, ask=NAN, at="")) == "stop_breached"


def test_stop_cap_from_the_entry():
    assert _check(_order(stop=97.9)) == "stop_cap"               # 2.1% from 100.00


def test_stop_cap_from_the_quote():
    # 1.95% from the entry, 2.15% from the ask the order would pay.
    quote = Quote(bid=100.0, ask=100.2, at="")
    assert _check(_order(stop=98.05), quote=quote) == "stop_cap"


def test_stop_cap_is_clamped_to_the_hard_two_percent():
    assert _check(_order(stop=97.0), cfg=_cfg(max_stop_loss_pct=5.0)) == "stop_cap"


def test_stop_too_tight_inside_etoros_minimum_distance():
    assert _check(elig=_elig(min_stop_pct=2.0)) == "stop_too_tight"   # 1.6% from the ask


def test_stop_too_tight_beyond_etoros_maximum_distance():
    assert _check(elig=_elig(max_stop_pct=1.0)) == "stop_too_tight"


def test_missing_stop_bounds_are_not_checked():
    assert _check(elig=_elig(min_stop_pct=None, max_stop_pct=None)) is None


def test_dollar_risk_above_the_risk_budget():
    small = MirrorBook(open_trades=(), balance=50.0, dfs={}, sectors=None)
    assert _check(book=small) == "dollar_risk"                  # 1.35 at risk > 1.00


def test_dollar_risk_at_five_percent_is_clamped_to_two():
    # 0.9 x 1.5 = 1.35 at risk. At balance 50, 5% would allow 2.50; the hard
    # cap clamps it to 2% = 1.00, so the order is refused.
    small = MirrorBook(open_trades=(), balance=50.0, dfs={}, sectors=None)
    assert _check(book=small, cfg=_cfg(risk_per_trade_pct=5.0)) == "dollar_risk"
    roomy = MirrorBook(open_trades=(), balance=100.0, dfs={}, sectors=None)
    assert _check(book=roomy, cfg=_cfg(risk_per_trade_pct=5.0)) is None   # 1.35 <= 2.00


def test_zero_units():
    assert _check(_order(units=0.0)) == "zero_units"


def test_below_min_exposure():
    assert _check(elig=_elig(min_exposure_usd=500.0)) == "below_min_exposure"   # 90.09


def test_above_max_units():
    assert _check(elig=_elig(max_units=0.5)) == "above_max_units"
    assert _check(elig=_elig(max_units=None)) is None


# --- settings --------------------------------------------------------------------

def test_check_config_reads_the_settings_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "ETORO_MAX_TRADE_USD", 250.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 1.5)
    monkeypatch.setattr(config, "RISK_PER_TRADE_PCT", 0.01)   # informational field: never read
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 8.0)
    monkeypatch.setattr(config, "CORRELATED_HEAT_CAP_PCT", 4.0)
    assert CheckConfig.from_config(5.0) == CheckConfig(250.0, 1.5, 5.0, 8.0, 4.0)
    monkeypatch.setattr(config, "ETORO_MAX_TRADE_USD", 0.0)
    assert CheckConfig.from_config(2.0).max_trade_usd == 0.0


# --- settlement and eligibility ---------------------------------------------------

REAL_1 = {"settlementType": "Real", "direction": "long", "leverageValues": [1]}
CFD_LONG = {"settlementType": "CFD", "direction": "long", "leverageValues": [1, 2, 5]}
CFD_SHORT = {"settlementType": "CFD", "direction": "short", "leverageValues": [1, 2]}


@pytest.mark.parametrize("configs, direction, expected", [
    ([REAL_1, CFD_LONG, CFD_SHORT], "bullish", "real"),
    ([CFD_LONG, CFD_SHORT], "bullish", "cfd"),
    ([dict(REAL_1, leverageValues=[2]), CFD_LONG], "bullish", "cfd"),
    ([dict(REAL_1, leverageValues=[2])], "bullish", None),
    ([REAL_1, CFD_LONG, CFD_SHORT], "bearish", "cfd"),
    ([REAL_1, CFD_LONG], "bearish", None),
    ([{"settlementType": "CFD", "leverageValues": [1]}], "bearish", "cfd"),   # no direction: both
    ([REAL_1, CFD_SHORT], "sideways", None),
    (None, "bullish", None),
    ([{"settlementType": "Real", "direction": "long"}], "bullish", None),     # no leverages listed
])
def test_resolve_settlement(configs, direction, expected):
    assert resolve_settlement(configs, direction) == expected


BODY = {"eligibilities": [
    {"instrumentId": 7, "symbol": "MSFT", "allowOpenPosition": True, "leverageConfigs": [REAL_1]},
    {"instrumentId": 1001, "symbol": "AAPL", "allowOpenPosition": True,
     "minPositionExposure": 10, "maxUnitsPerOrder": 5000, "unitsQuantityType": "Fractional",
     "minStopLossPercentage": 0.25, "maxStopLossPercentage": 90,
     "leverageConfigs": [
         dict(REAL_1, minStopLossPercentage=0.5, maxStopLossPercentage=100),
         dict(CFD_LONG, minStopLossPercentage=0.5, maxStopLossPercentage=50),
         CFD_SHORT]},
]}


def test_parse_eligibility_for_a_long():
    assert parse_eligibility(BODY, "aapl", "bullish") == Eligibility(
        instrument_id=1001, symbol="AAPL", allow_open=True, settlement_type="real",
        min_exposure_usd=10.0, max_units=5000.0, min_stop_pct=0.5, max_stop_pct=100.0,
        unit_decimals=4)


def test_parse_eligibility_for_a_short_falls_back_to_item_stop_bounds():
    elig = parse_eligibility(BODY, "AAPL", "bearish")
    assert elig.settlement_type == "cfd"
    assert (elig.min_stop_pct, elig.max_stop_pct) == (0.25, 90.0)


def test_parse_eligibility_defaults():
    elig = parse_eligibility(BODY, "MSFT", "bullish")
    assert elig.unit_decimals == 0 and elig.min_exposure_usd == 0.0
    assert elig.max_units is None and elig.min_stop_pct is None


def test_allow_open_must_be_literally_true():
    body = {"eligibilities": [dict(BODY["eligibilities"][1], allowOpenPosition="yes")]}
    assert parse_eligibility(body, "AAPL", "bullish").allow_open is False


@pytest.mark.parametrize("body", [
    None, [], {}, {"eligibilities": None}, {"eligibilities": [{"symbol": "AAPL"}]},
    {"eligibilities": [{"instrumentId": 1, "symbol": "AAPL.US"}]},
])
def test_parse_eligibility_returns_none_without_a_matching_instrument(body):
    assert parse_eligibility(body, "AAPL", "bullish") is None


def test_order_price_is_the_side_the_order_pays():
    assert order_price("bullish", QUOTE) == 100.1
    assert order_price("bearish", QUOTE) == 99.9


# --- stops only tighten -------------------------------------------------------

@pytest.mark.parametrize("direction, last, new, expected", [
    ("bullish", 98.0, 99.0, None),
    ("bullish", 98.0, 98.0, "stop_widen"),
    ("bullish", 98.0, 97.5, "stop_widen"),
    ("bearish", 102.0, 101.0, None),
    ("bearish", 102.0, 102.0, "stop_widen"),
    ("bearish", 102.0, 102.5, "stop_widen"),
    ("bullish", 98.0, None, "stop_widen"),          # clearing the stop
    ("bearish", 102.0, None, "stop_widen"),
    ("bullish", 98.0, NAN, "stop_widen"),
    ("bullish", 98.0, 0.0, "stop_widen"),
    ("bullish", None, 97.0, None),                  # nothing sent yet to compare
    ("sideways", 98.0, 99.0, "stop_widen"),
])
def test_check_stop_move(direction, last, new, expected):
    assert check_stop_move(direction, last, new) == expected


def test_checks_is_pure():
    tree = ast.parse(inspect.getsource(checks))
    modules = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    modules |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert modules <= {"__future__", "math", "dataclasses", "typing", "swingbot",
                       "swingbot.core.risk_limits", "swingbot.core.broker.sizing",
                       "swingbot.core.edge.heat", "swingbot.core.edge.correlation"}
```

In `test_the_first_failing_check_is_the_reason`, `elig=False` is deliberate: it is not `None`, so `_check` passes it through, and `no_stop` must fire before anything reads the eligibility.

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_checks.py`
Expected: FAIL: `ModuleNotFoundError: No module named 'swingbot.core.broker.checks'`.

- [ ] **Step 3: Write the module**

Create `$WT/swingbot/core/broker/checks.py`:

```python
"""Order-risk checks for the eToro demo mirror (v160). Pure.

`check_open` runs every pre-send check in the spec's order and returns the
first failing check's skip reason, or None. The size is never raised here and
an open is never sent without its stop. `check_stop_move` refuses any stop move
that does not tighten. Nothing here does I/O or reads a clock: the executor
fetches the quote, the eligibility body, the open mirror rows and the price
frames, and passes them in.

Every cap is compared as `value <= cap + 1e-9`, written so a NaN compares as a
breach: a non-finite quote, stop or size is skipped, never sent.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from swingbot import config
from swingbot.core.broker.sizing import FRACTIONAL_UNIT_DECIMALS, WHOLE_UNIT_DECIMALS
from swingbot.core.risk_limits import capped_planned_loss_pct, planned_loss_pct

SKIP_REASONS = (
    "no_trade_cap", "no_stop", "ineligible", "stop_breached", "stop_cap", "stop_too_tight",
    "dollar_risk", "zero_units", "below_min_exposure", "above_max_units",
    "portfolio_heat", "correlated_heat", "stop_widen", "no_position",
)

_TOLERANCE = 1e-9                      # as entry_filters.py and edge/heat.py compare caps
_LONG, _SHORT = "bullish", "bearish"
_SIDE = {_LONG: "long", _SHORT: "short"}
_UNIT_DECIMALS = {"whole": WHOLE_UNIT_DECIMALS, "fractional": FRACTIONAL_UNIT_DECIMALS}


@dataclass(frozen=True)
class OpenOrder:
    ticker: str
    direction: str          # TradePlanV2.direction: "bullish" | "bearish"
    entry: float            # plan.entry_price, the paper fill
    stop: float | None      # plan.stop_loss, rounded to rate precision
    units: float            # after sizing.mirror_units


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    at: str                 # ISO time of the rate


@dataclass(frozen=True)
class Eligibility:
    instrument_id: int
    symbol: str
    allow_open: bool
    settlement_type: str | None     # "real" | "cfd" | None: nothing eligible at leverage 1
    min_exposure_usd: float
    max_units: float | None
    min_stop_pct: float | None
    max_stop_pct: float | None
    unit_decimals: int


@dataclass(frozen=True)
class MirrorBook:
    open_trades: tuple      # open `open` rows, as BrokerOrderRepository.open_positions() returns
    balance: float          # the sizing balance: compute_position_size(...)["balance"]
    dfs: dict               # {ticker: daily OHLCV frame}, for correlated heat
    sectors: dict | None    # {ticker: sector}, the thin-history fallback


@dataclass(frozen=True)
class CheckConfig:
    max_trade_usd: float
    max_stop_loss_pct: float
    risk_per_trade_pct: float
    portfolio_heat_cap_pct: float
    correlated_heat_cap_pct: float

    @classmethod
    def from_config(cls, risk_pct: float) -> "CheckConfig":
        """Read every cap at call time, so a SIGHUP reload applies on the next tick.
        risk_pct is the risk % the sizer used for this order (compute_position_size's
        "risk_pct"), not config.RISK_PER_TRADE_PCT, which is informational only."""
        return cls(max_trade_usd=float(config.ETORO_MAX_TRADE_USD),
                   max_stop_loss_pct=float(config.MAX_STOP_LOSS_PCT),
                   risk_per_trade_pct=float(risk_pct),
                   portfolio_heat_cap_pct=float(config.PORTFOLIO_HEAT_CAP_PCT),
                   correlated_heat_cap_pct=float(config.CORRELATED_HEAT_CAP_PCT))


# --- small helpers ------------------------------------------------------------

def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _float_or_none(value) -> float | None:
    return float(value) if _finite(value) else None


def _within(value: float, cap: float) -> bool:
    """value <= cap; False for NaN, so a non-finite input fails the check."""
    return value <= cap + _TOLERANCE


def order_price(direction: str, quote: Quote) -> float:
    """The side of the book the order pays: the ask for a long, the bid for a short."""
    return quote.ask if direction == _LONG else quote.bid


# --- settlement and eligibility -------------------------------------------------

def _at_leverage_one(leverage_config: dict) -> bool:
    values = leverage_config.get("leverageValues")
    return isinstance(values, list) and any(_finite(v) and float(v) == 1.0 for v in values)


def _for_side(leverage_config: dict, side: str) -> bool:
    wanted = leverage_config.get("direction")
    return wanted is None or str(wanted).lower() == side


def _settlement_of(leverage_config: dict) -> str:
    return str(leverage_config.get("settlementType") or "").lower()


def _usable_configs(leverage_configs, direction: str) -> list[dict]:
    """Leverage configs that allow this direction at leverage 1."""
    side = _SIDE.get(direction)
    if side is None or not isinstance(leverage_configs, list):
        return []
    return [c for c in leverage_configs
            if isinstance(c, dict) and _for_side(c, side) and _at_leverage_one(c)]


def resolve_settlement(leverage_configs: list, direction: str) -> str | None:
    """Long: "real" when eligible at leverage 1, else "cfd"; short: "cfd"; else None."""
    types = {_settlement_of(c) for c in _usable_configs(leverage_configs, direction)}
    if direction == _LONG and "real" in types:
        return "real"
    return "cfd" if "cfd" in types else None


def _find_item(body: object, symbol: str) -> dict | None:
    items = body.get("eligibilities") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and str(item.get("symbol", "")).upper() == symbol.upper():
            return item
    return None


def _config_for(item: dict, direction: str, settlement: str | None) -> dict:
    for leverage_config in _usable_configs(item.get("leverageConfigs"), direction):
        if _settlement_of(leverage_config) == settlement:
            return leverage_config
    return {}


def _stop_bound(item: dict, chosen: dict, key: str) -> float | None:
    value = chosen.get(key)
    return _float_or_none(item.get(key) if value is None else value)


def parse_eligibility(body: object, symbol: str, direction: str) -> Eligibility | None:
    """The eligibility route's answer for one symbol, or None when it has none."""
    item = _find_item(body, symbol)
    if item is None or not _finite(item.get("instrumentId")):
        return None
    settlement = resolve_settlement(item.get("leverageConfigs"), direction)
    chosen = _config_for(item, direction, settlement)
    units_type = str(item.get("unitsQuantityType") or "").lower()
    return Eligibility(
        instrument_id=int(item["instrumentId"]),
        symbol=str(item.get("symbol")),
        allow_open=item.get("allowOpenPosition") is True,
        settlement_type=settlement,
        min_exposure_usd=_float_or_none(item.get("minPositionExposure")) or 0.0,
        max_units=_float_or_none(item.get("maxUnitsPerOrder")),
        min_stop_pct=_stop_bound(item, chosen, "minStopLossPercentage"),
        max_stop_pct=_stop_bound(item, chosen, "maxStopLossPercentage"),
        unit_decimals=_UNIT_DECIMALS.get(units_type, WHOLE_UNIT_DECIMALS),
    )


# --- the open checks, in the spec's order ---------------------------------------

def _check_trade_cap(order, quote, eligibility, book, cfg) -> str | None:
    return None if cfg.max_trade_usd > 0 else "no_trade_cap"


def _check_stop_present(order, quote, eligibility, book, cfg) -> str | None:
    return None if _finite(order.stop) and order.stop > 0 else "no_stop"


def _check_eligible(order, quote, eligibility, book, cfg) -> str | None:
    if eligibility is None or not eligibility.allow_open or eligibility.settlement_type is None:
        return "ineligible"
    return None


def _check_stop_breached(order, quote, eligibility, book, cfg) -> str | None:
    if order.direction == _LONG:
        return None if order.stop < quote.bid else "stop_breached"
    return None if order.stop > quote.ask else "stop_breached"


def _check_stop_cap(order, quote, eligibility, book, cfg) -> str | None:
    cap = capped_planned_loss_pct(cfg.max_stop_loss_pct)
    from_entry = planned_loss_pct(order.entry, order.stop)
    from_quote = planned_loss_pct(order_price(order.direction, quote), order.stop)
    return None if _within(from_entry, cap) and _within(from_quote, cap) else "stop_cap"


def _check_stop_bounds(order, quote, eligibility, book, cfg) -> str | None:
    distance = planned_loss_pct(order_price(order.direction, quote), order.stop)
    too_close = eligibility.min_stop_pct is not None and distance < eligibility.min_stop_pct
    too_far = eligibility.max_stop_pct is not None and distance > eligibility.max_stop_pct
    return "stop_too_tight" if too_close or too_far else None


def _check_dollar_risk(order, quote, eligibility, book, cfg) -> str | None:
    allowed = capped_planned_loss_pct(cfg.risk_per_trade_pct) / 100.0 * book.balance
    at_risk = order.units * abs(order.entry - order.stop)
    return None if _within(at_risk, allowed) else "dollar_risk"


def _check_zero_units(order, quote, eligibility, book, cfg) -> str | None:
    return None if _finite(order.units) and order.units > 0 else "zero_units"


def _check_min_exposure(order, quote, eligibility, book, cfg) -> str | None:
    exposure = order.units * order_price(order.direction, quote)
    return None if exposure + _TOLERANCE >= eligibility.min_exposure_usd else "below_min_exposure"


def _check_max_units(order, quote, eligibility, book, cfg) -> str | None:
    if eligibility.max_units is None:
        return None
    return None if _within(order.units, eligibility.max_units) else "above_max_units"


_OPEN_CHECKS: list[Callable[[OpenOrder, Quote, Eligibility | None, MirrorBook, CheckConfig],
                            str | None]] = [
    _check_trade_cap, _check_stop_present, _check_eligible, _check_stop_breached,
    _check_stop_cap, _check_stop_bounds, _check_dollar_risk, _check_zero_units,
    _check_min_exposure, _check_max_units,
]


def check_open(order: OpenOrder, quote: Quote, eligibility: Eligibility | None,
               book: MirrorBook, cfg: CheckConfig) -> str | None:
    """The first failing check's skip reason, or None when the open may be sent."""
    for check in _OPEN_CHECKS:
        reason = check(order, quote, eligibility, book, cfg)
        if reason is not None:
            return reason
    return None


# --- stops only tighten ------------------------------------------------------------

def check_stop_move(direction: str, last_stop: float | None,
                    new_stop: float | None) -> str | None:
    """None when the move tightens; "stop_widen" when it loosens, holds level,
    clears the stop, is not a finite price, or the direction is unknown."""
    if not _finite(new_stop) or new_stop <= 0:
        return "stop_widen"
    if last_stop is None:
        return None
    if direction == _LONG:
        return None if new_stop > last_stop else "stop_widen"
    if direction == _SHORT:
        return None if new_stop < last_stop else "stop_widen"
    return "stop_widen"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_checks.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS (`checks.py` is allow-listed; it touches no eToro name).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/checks.py"`
Expected: no output (the busiest functions, `parse_eligibility` and `check_stop_move`, are B or below).

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add swingbot/core/broker/checks.py tests/broker/test_checks.py
git -C "$WT" commit -m "feat(v160): EM4 -- broker checks: eligibility, stop and size checks, stops only tighten

check_open runs the spec's order checks table-driven (no_trade_cap through
above_max_units) and returns the first skip reason; a non-finite input
fails its check rather than slipping past it. parse_eligibility resolves
real-at-leverage-1 for longs, cfd otherwise, and eToro's stop bounds.
check_stop_move refuses any move that does not tighten, including a cleared
stop. Pure; heat checks follow in EM5.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task EM5: `checks.py` II: portfolio and correlated heat over mirror rows

**Model:** opus — risk-cap logic over the mirror's own positions, where a wrong row mapping or balance silently lets heat through; the spec's risk-manager blocking finding 1 lands here.

Spec § Sizing and order checks (rows `portfolio_heat` and `correlated_heat`: `edge.heat.heat_check` over the mirror's open rows with `entry = avg_price`, `stop_loss = stop_sent`, `shares = units_filled` against the sizing balance; `edge.correlation.cluster_check`), § Panel review risk-manager 1. Index ledger EM5 (candidate risk % = `units × |entry − stop| / balance × 100`).

**Files:**
- Modify: `swingbot/core/broker/checks.py` (created by EM4: imports, a new section before `_OPEN_CHECKS`, two entries appended to `_OPEN_CHECKS`)
- Create: `tests/broker/test_checks_heat.py`

**Interfaces:**
- Consumes: EM4's `checks.py` (`OpenOrder`, `Quote`, `Eligibility`, `MirrorBook`, `CheckConfig`, `check_open`, `_OPEN_CHECKS`, `_finite`); `swingbot.core.edge.heat.heat_check(open_trades: list, balance: float, candidate_risk_pct: float, cap_pct: float | None = None) -> dict` (`"allowed"`, `swingbot/core/edge/heat.py:27`); `swingbot.core.edge.correlation.cluster_exposure(open_trades, candidate_ticker, dfs, balance, *, window=90, threshold=0.75, sectors=None) -> dict` and `cluster_check(exposure, candidate_risk_pct, cap_pct=None) -> dict` (`"allowed"`, `swingbot/core/edge/correlation.py:27`, `:51`). Both edge functions read trades shaped `{"ticker", "entry", "stop_loss", "shares"}`.
- Produces (EM8 relies on these):
  - `heat_trades(open_rows: list[dict]) -> list[dict]`: each row with finite `avg_price`, `stop_sent` and `units_filled` becomes `{"ticker": row["ticker"], "entry": avg_price, "stop_loss": stop_sent, "shares": units_filled}`; a row missing any of the three (absent, `None`, NaN, not a number) is dropped.
  - `_check_portfolio_heat`, `_check_correlated_heat` appended to `_OPEN_CHECKS` (reasons `"portfolio_heat"`, `"correlated_heat"`), so `check_open` now runs twelve checks. Both use `cfg.portfolio_heat_cap_pct` / `cfg.correlated_heat_cap_pct`, never the edge modules' config fallbacks, and the candidate risk % from `order.units`, `order.entry`, `order.stop` and `book.balance` (`inf` when the balance is not a finite positive number, so the order is refused).
  - The executor builds `MirrorBook(open_trades=tuple(repo.open_positions()), balance=<sizing balance>, dfs=..., sectors=...)` (EM8); `checks` converts the rows itself.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/broker/test_checks_heat.py`:

```python
"""broker.checks (v160), part II: portfolio and correlated heat over the
mirror's OWN open rows (entry = avg_price, stop_loss = stop_sent,
shares = units_filled) against the sizing balance. Pure; frames are synthetic."""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.broker import checks
from swingbot.core.broker.checks import (
    CheckConfig, Eligibility, MirrorBook, OpenOrder, Quote, check_open, heat_trades)

NAN = float("nan")
QUOTE = Quote(bid=99.9, ask=100.1, at="2026-10-12T14:30:00+00:00")
ELIG = Eligibility(instrument_id=1001, symbol="AAPL", allow_open=True, settlement_type="real",
                   min_exposure_usd=10.0, max_units=None, min_stop_pct=0.5, max_stop_pct=75.0,
                   unit_decimals=4)
CFG = CheckConfig(max_trade_usd=100.0, max_stop_loss_pct=2.0, risk_per_trade_pct=2.0,
                  portfolio_heat_cap_pct=6.0, correlated_heat_cap_pct=3.0)


def _order(units, ticker="AAPL"):
    # 1.5 stop distance: risk = units x 1.5; at balance 10,000 that is units x 0.015 %.
    return OpenOrder(ticker=ticker, direction="bullish", entry=100.0, stop=98.5, units=units)


def _row(ticker, avg_price, stop_sent, units_filled):
    return {"plan_id": f"P-{ticker}", "action": "open", "status": "filled", "ticker": ticker,
            "avg_price": avg_price, "stop_sent": stop_sent, "units_filled": units_filled}


def _frame(seed):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, 120))
    return pd.DataFrame({"Close": close}, index=pd.bdate_range("2026-04-01", periods=120))


def _book(rows, dfs=None, sectors=None, balance=10_000.0):
    return MirrorBook(open_trades=tuple(rows), balance=balance, dfs=dfs or {}, sectors=sectors)


def test_heat_checks_run_last_in_the_spec_order():
    names = [check.__name__ for check in checks._OPEN_CHECKS]
    assert len(names) == 12
    assert names[-2:] == ["_check_portfolio_heat", "_check_correlated_heat"]


# --- row mapping ----------------------------------------------------------------

def test_heat_trades_map_mirror_rows_to_the_edge_shape():
    assert heat_trades([_row("MSFT", 410.0, 400.0, 0.2)]) == [
        {"ticker": "MSFT", "entry": 410.0, "stop_loss": 400.0, "shares": 0.2}]


@pytest.mark.parametrize("bad", [
    {"avg_price": None}, {"stop_sent": None}, {"units_filled": NAN}, {"avg_price": "n/a"}])
def test_heat_trades_drop_rows_missing_a_number(bad):
    row = {**_row("MSFT", 410.0, 400.0, 0.2), **bad}
    assert heat_trades([row, _row("XOM", 110.0, 108.0, 1.0)]) == [
        {"ticker": "XOM", "entry": 110.0, "stop_loss": 108.0, "shares": 1.0}]


def test_heat_trades_drop_a_row_without_the_field_at_all():
    row = _row("MSFT", 410.0, 400.0, 0.2)
    del row["units_filled"]
    assert heat_trades([row]) == []


# --- portfolio heat ---------------------------------------------------------------

def test_portfolio_heat_within_the_cap_passes():
    book = _book([_row("MSFT", 100.0, 95.0, 100.0)])           # 500 at risk = 5.0 %
    assert check_open(_order(50), QUOTE, ELIG, book, CFG) is None          # + 0.75 % = 5.75


def test_portfolio_heat_above_the_cap_is_refused():
    book = _book([_row("MSFT", 100.0, 95.0, 100.0)])
    assert check_open(_order(100), QUOTE, ELIG, book, CFG) == "portfolio_heat"   # 6.5 %


def test_portfolio_heat_exactly_at_the_cap_passes():
    book = _book([_row("MSFT", 100.0, 95.5, 100.0)])           # 4.5 %
    assert check_open(_order(100), QUOTE, ELIG, book, CFG) is None          # + 1.5 = 6.0


def test_the_cap_comes_from_check_config_not_the_settings(monkeypatch):
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 1.0)
    book = _book([_row("MSFT", 100.0, 95.0, 100.0)])
    roomy = CheckConfig(100.0, 2.0, 2.0, 20.0, 3.0)
    assert check_open(_order(100), QUOTE, ELIG, book, roomy) is None


def test_rows_without_fill_data_add_no_heat():
    book = _book([_row("MSFT", None, 95.0, 10_000.0)])
    assert check_open(_order(100), QUOTE, ELIG, book, CFG) is None


def test_a_non_positive_balance_refuses_the_order():
    book = _book([], balance=0.0)
    assert checks._check_portfolio_heat(_order(1), QUOTE, ELIG, book, CFG) == "portfolio_heat"
    assert checks._check_correlated_heat(_order(1), QUOTE, ELIG, book, CFG) == "correlated_heat"


# --- correlated heat ---------------------------------------------------------------

def test_correlated_heat_within_the_cluster_cap_passes():
    dfs = {"AAPL": _frame(1), "QQQ": _frame(1)}               # identical returns: corr 1.0
    book = _book([_row("QQQ", 100.0, 98.0, 100.0)], dfs=dfs)  # 2.0 % in the cluster
    assert check_open(_order(50), QUOTE, ELIG, book, CFG) is None          # + 0.75 = 2.75


def test_correlated_heat_above_the_cluster_cap_is_refused():
    dfs = {"AAPL": _frame(1), "QQQ": _frame(1)}
    book = _book([_row("QQQ", 100.0, 98.0, 100.0)], dfs=dfs)
    assert check_open(_order(80), QUOTE, ELIG, book, CFG) == "correlated_heat"   # 3.2 %


def test_uncorrelated_positions_do_not_count_against_the_cluster():
    dfs = {"AAPL": _frame(1), "XOM": _frame(2)}
    book = _book([_row("XOM", 100.0, 98.0, 100.0)], dfs=dfs)
    assert check_open(_order(80), QUOTE, ELIG, book, CFG) is None


def test_thin_history_falls_back_to_the_same_sector():
    rows = [_row("MSFT", 100.0, 98.0, 100.0)]
    same = _book(rows, sectors={"AAPL": "Technology", "MSFT": "Technology"})
    other = _book(rows, sectors={"AAPL": "Technology", "MSFT": "Energy"})
    assert check_open(_order(80), QUOTE, ELIG, same, CFG) == "correlated_heat"
    assert check_open(_order(80), QUOTE, ELIG, other, CFG) is None


def test_an_empty_book_passes_both_heat_checks():
    assert check_open(_order(50), QUOTE, ELIG, _book([]), CFG) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_checks_heat.py`
Expected: FAIL: `ImportError: cannot import name 'heat_trades' from 'swingbot.core.broker.checks'`.

- [ ] **Step 3: Add the heat checks**

In `$WT/swingbot/core/broker/checks.py`:

1. Add to the module docstring, after its first paragraph:

```python
Heat is measured over the mirror's OWN open positions (avg_price, stop_sent,
units_filled from broker_orders) against the sizing balance, so mirror-only
skips are expected: the mirror's book is not the paper book.
```

2. Add these imports after `from swingbot.core.broker.sizing import ...`:

```python
from swingbot.core.edge.correlation import cluster_check, cluster_exposure
from swingbot.core.edge.heat import heat_check
```

3. Directly before the `_OPEN_CHECKS: list[...] = [` assignment, add:

```python
# --- heat over the mirror's own open rows ------------------------------------------

_HEAT_FIELDS = ("avg_price", "stop_sent", "units_filled")


def heat_trades(open_rows: list[dict]) -> list[dict]:
    """Mirror rows in edge.heat's trade shape; a row missing a number is dropped."""
    trades = []
    for row in open_rows:
        values = [row.get(field) for field in _HEAT_FIELDS]
        if all(_finite(value) for value in values):
            entry, stop, units = (float(value) for value in values)
            trades.append({"ticker": row.get("ticker"), "entry": entry,
                           "stop_loss": stop, "shares": units})
    return trades


def _candidate_risk_pct(order: OpenOrder, book: MirrorBook) -> float:
    """This order's risk to its stop as % of the sizing balance; inf without a balance."""
    if not (_finite(book.balance) and book.balance > 0):
        return math.inf
    return order.units * abs(order.entry - order.stop) / book.balance * 100.0


def _check_portfolio_heat(order, quote, eligibility, book, cfg) -> str | None:
    result = heat_check(heat_trades(list(book.open_trades)), book.balance,
                        _candidate_risk_pct(order, book), cap_pct=cfg.portfolio_heat_cap_pct)
    return None if result["allowed"] else "portfolio_heat"


def _check_correlated_heat(order, quote, eligibility, book, cfg) -> str | None:
    exposure = cluster_exposure(heat_trades(list(book.open_trades)), order.ticker,
                                book.dfs or {}, book.balance, sectors=book.sectors)
    result = cluster_check(exposure, _candidate_risk_pct(order, book),
                           cap_pct=cfg.correlated_heat_cap_pct)
    return None if result["allowed"] else "correlated_heat"
```

4. Append the two checks to the end of the `_OPEN_CHECKS` list, so it reads:

```python
_OPEN_CHECKS: list[Callable[[OpenOrder, Quote, Eligibility | None, MirrorBook, CheckConfig],
                            str | None]] = [
    _check_trade_cap, _check_stop_present, _check_eligible, _check_stop_breached,
    _check_stop_cap, _check_stop_bounds, _check_dollar_risk, _check_zero_units,
    _check_min_exposure, _check_max_units, _check_portfolio_heat, _check_correlated_heat,
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_checks_heat.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_checks.py`
Expected: PASS: EM4's cases still hold with twelve checks (their book is empty, so neither heat check fires), and `test_checks_is_pure` already allows the two `edge` imports.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/checks.py"`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add swingbot/core/broker/checks.py tests/broker/test_checks_heat.py
git -C "$WT" commit -m "feat(v160): EM5 -- broker checks: portfolio and correlated heat over mirror rows

The mirror enforces its own heat caps: open demo positions (avg_price,
stop_sent, units_filled) mapped into edge.heat's trade shape, measured
against the sizing balance with PORTFOLIO_HEAT_CAP_PCT and, through
edge.correlation's cluster check, CORRELATED_HEAT_CAP_PCT. A missing
balance refuses the order. check_open now runs all twelve open checks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

