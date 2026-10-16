# v170 Simple alerts: money beside R, symbol labels, plan buttons. Part 3: buttons, legend, render

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: `grep -n "^### Task V170-11" -A 300 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md`](../specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md)
**Index:** [`2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md`](2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md): `## Where to work` (worktree `$WT`, main tree `$R`, test database), `## Global Constraints`, `## Decisions taken while planning`, `## Parallelisation` and the `## Task ledger` all apply to every task below. Read them before starting.
**Bump:** minor
**Edge:** none (integrity)

Tasks in this part: V170-10 (the P&L-now reply module), V170-11 (the feed buttons and their registration), V170-12 (attaching the buttons at the two send sites), V170-13 (the `!help` legend). **V170-14** (radon sweep, before/after render results note, the one full-suite run) is in [`2026-10-16-v170-simple-alerts-money-symbols-buttons_4-render-suite.md`](2026-10-16-v170-simple-alerts-money-symbols-buttons_4-render-suite.md): with it this file would pass the 1500-line cap.

**Contracts this part consumes from earlier parts** (ledger, final; verify each with `git -C $WT grep -n` before starting a task, and stop with `BLOCKED: <symbol> missing` if one is absent):

- V170-1: `tokens.fmt_money(amount, currency) -> str` (ASCII `-`, `+` on zero and above); `tokens.FEED_SYMBOLS` (keys `entry, stop, tp1, runner, tp2, trail, breakeven, expiry, invalid, if_fills, pnl, win, loss, flat, at_or_above, at_or_below`); `tokens.COST_BASIS = "(paper, gross)"`; `tokens.feed_legend() -> str`.
- V170-2: `TradeLog.trade_for_plan(plan_id) -> dict | None` (any status).
- V170-3: `instructions.money_from(shares, currency, *, realized_amount=None, priced=True) -> Money`; `instructions.signed_r(x) -> str` (exists today, U+2212 minus).
- V170-4: `execution_embeds._linked_trade(plan_id) -> dict | None` (tests monkeypatch it).
- V170-5: `instructions.pnl_line(r: float, money: Money | None) -> str` → `"🧾 <$ · >R (paper, gross)"`, the `$` only when `money.realized_amount is not None`.
- V170-8: `components.push_kwargs(embed, view=None) -> dict` (adds `"view"` only when a view is passed); `ui.push_kwargs` re-exports it.
- V170-9: `scan_run.TradeQuote` (frozen: `price: float | None`, `daily_close: date | None = None`); `scan_run.quote_trade(trade: dict) -> tuple[TradeQuote, UnrealizedPnL | None]` (reads `trade["ticker"]`, `["entry"]`, `["stop_loss"]`, `["take_profit"]`, `["direction"]`; a price it cannot get is `TradeQuote(price=None)` with `None` for the P&L).
- Exists today: `instructions.total_r(plan, exit_price) -> float`; `account.compute_unrealized_pnl(entry, stop_loss, take_profit, direction, current_price) -> UnrealizedPnL`; `session.now_et(now)`, `session.is_regular_session(now)`; `views._template`, `views.custom_id_for`, `views._persistable`, `views._PlanButtonMixin`, `views.ChartButton`, `views.BreakdownButton`, `views.WatchButton`, `views.PLAN_BUTTONS`, `views.PlanActionView`, `views.register_persistent_views`; `alerts._mirror`; `lifecycle_embeds.notify_plan_events`, `lifecycle_embeds._warn_throttled`, `lifecycle_embeds._last_warned`; `Kind.TICKET_PLACE`, `Kind.TICKET_DO_NOT_PLACE`, `Kind.STRATEGY_SIGNAL`, `Kind.SETUP_SIMPLE`; `PushEmbed.kind`.

# Phase 5: P&L now and the feed buttons

### Task V170-10: `commands/pnl_now.py`: the P&L-now reply per plan status

**Model:** sonnet — a new pure renderer with four status branches and money arithmetic that must match the feed's R basis; fully specified, no cross-package design.

**Files:**
- Create: `swingbot/commands/pnl_now.py`
- Create: `tests/commands/test_pnl_now.py` (suite `discord`, existing directory, no `suites.toml` edit)

**Interfaces:**
- Consumes: V170-1 `tokens.fmt_money`, `tokens.FEED_SYMBOLS`, `tokens.COST_BASIS`; V170-2 `TradeLog.trade_for_plan`; V170-3 `instructions.money_from`; V170-5 `instructions.pnl_line`; V170-9 `scan_run.quote_trade`, `scan_run.TradeQuote`; existing `instructions.total_r`, `instructions.signed_r`, `tokens.fmt_price`, `tokens.fmt_pct`, `session.now_et`, `session.is_regular_session`, `account.compute_unrealized_pnl` (tests only).
- Produces (ledger contract, final): `pnl_now.GONE = "This plan no longer exists."`; `pnl_now.UNAVAILABLE = "price unavailable"`; `pnl_now.render_reply(plan, trade: dict | None, quote, pnl, *, clock: datetime, market_open: bool) -> str`; `pnl_now.reply_for(plan_id: str, *, now: datetime | None = None) -> str` (never raises); seams `pnl_now._load_plan(plan_id)`, `pnl_now._linked_trade(plan_id) -> dict | None`, `pnl_now._quote(plan, trade) -> tuple[TradeQuote | None, UnrealizedPnL | None]`. Also module constants `NOT_FILLED = "not filled yet"`, `NEVER_FILLED = "never filled"`, `FAILED = "Could not compute P&L just now; please try again."` (used only here and in V170-11's tests). V170-11 calls `pnl_now.reply_for(plan_id)` from the button.

Rules this task enforces (spec §3, A4, A5, A6, index Decision 6, Global Constraints):

- The reply adapts to the plan's status **at click time**: PENDING → last price vs the trigger, `not filled yet`; ACTIVE/PARTIAL → as-of line, the open fraction's contribution (`%`, `$`, `R`), banked legs, total; CLOSED → the final result from the record (`instructions.pnl_line`, so `$` only once settled), no live price; CANCELLED (expired, invalidated, risk cap) → `never filled`, no live price.
- `%` is `compute_unrealized_pnl(...).pct_change` from `scan_run.quote_trade`, the `!pnl` figure. The open line's R is `open_fraction × (price − entry) × sign / |entry − stop_loss|` and its `$` is `record_shares × open_fraction × (price − entry) × sign`, so open + banked = total. Banked legs use record arithmetic: `record_shares × fraction × (exit − entry) × sign` (A3), R `Σ fraction × r`. `entry` is the plan's fill (`plan.entry_price`), the same basis `instructions.total_r` uses; the record's `entry` is moved to the fill at fill time (`performance.py:779`), so `%` and R share it.
- No linked record (or a record with no `shares`): **no `$` at all**, R and `%` only (spec §1 fallback).
- As-of (A6): `last <price> · as of HH:MM ET`, plus `daily close YYYY-MM-DD` when `TradeQuote.daily_close` is set, plus `market closed` when `session.is_regular_session(clock)` is false. No quote carries a timestamp, so the fetch moment (the click) is the as-of.
- Every total ends `(paper, gross)` (`tokens.COST_BASIS`). `$` strings use `fmt_money` (ASCII `-`); R strings use `signed_r` (U+2212). Neither formatter changes.
- A price that cannot be fetched prints `price unavailable` (plus any banked line); **`reply_for` never raises**: a failure anywhere returns `FAILED` (logged with traceback).
- Pure-plus-seams: `render_reply` does no I/O and reads no clock; `reply_for` is the only function that touches the store, the trade log, the price fetch and the clock, each through one seam the tests monkeypatch.
- The `🧾` glyph comes from `tokens.FEED_SYMBOLS["pnl"]` (one meaning: a P&L line's lead) and `▶` from `FEED_SYMBOLS["entry"]`; no other glyph is added.

- [ ] **Step 0: Test database up, contracts present**

`test_linked_trade_reads_the_record_in_any_status` writes a real paper trade. DB-backed tests SKIP (not fail) when the test Postgres is unreachable, and a skip is not green here.

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test
docker ps --filter name=swing-db-test --format "{{.Names}} {{.Ports}}"
```

Expected: `swing-db-test` listed. If its published port is not `55432`, export `TEST_DATABASE_URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:<port>/swingbot_test` for every `testrun.py` call in this task.

Then confirm the consumed contracts exist:

```bash
git -C $WT grep -n "def quote_trade\|class TradeQuote" -- swingbot/core/scanning/scan_run.py
git -C $WT grep -n "def pnl_line\|def money_from\|def total_r\|def signed_r" -- swingbot/core/presentation/instructions.py
git -C $WT grep -n "def trade_for_plan" -- swingbot/core/tracking/performance.py
git -C $WT grep -n "^COST_BASIS\|^def fmt_money\|^FEED_SYMBOLS" -- swingbot/core/presentation/tokens.py
```

Expected: every line found. A missing one means its task has not landed: stop and report `BLOCKED: <symbol> missing (V170-<n>)`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/commands/test_pnl_now.py`:

```python
"""v170 §3 / A4-A6: the 💵 P&L now reply.

render_reply is pure: every status is pinned here by exact text. reply_for
is the only function with I/O; its three seams (_load_plan, _linked_trade,
_quote) are monkeypatched, and it must never raise. No pytest-asyncio.
"""
import datetime as dt
import types

import pytest

from swingbot import config
from swingbot.commands import pnl_now
from swingbot.core.planning.account import compute_unrealized_pnl
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.scanning import scan_run
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
WED = dt.datetime(2026, 10, 7, 14, 30, tzinfo=dt.timezone.utc)   # 10:30 ET, Wednesday
SAT = dt.datetime(2026, 10, 10, 14, 30, tzinfo=dt.timezone.utc)  # Saturday
TP1_LEG = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}
RUNNER_LEG = {"fraction": 0.5, "exit_price": 120.0, "r": 4.0, "reason": "tp1_runner_tp2"}


@pytest.fixture(autouse=True)
def _dollars(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")


def _long(status=PlanStatus.ACTIVE, **kw):
    base = dict(plan_id=PID, status=status, entry_type="stop_entry", trigger_price=100.0,
                entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=120.0, tp1_fraction=0.5)
    base.update(kw)
    return _plan(**base)


def _short(status=PlanStatus.ACTIVE, **kw):
    base = dict(plan_id=PID, status=status, direction="bearish", entry_type="stop_entry",
                trigger_price=100.0, entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=80.0,
                tp1_fraction=0.5)
    base.update(kw)
    return _plan(**base)


def _trade(direction="bullish", stop_loss=95.0, take_profit=110.0, **kw):
    record = {"id": "t1", "plan_id": PID, "ticker": "AAPL", "direction": direction,
              "entry": 100.0, "stop_loss": stop_loss, "take_profit": take_profit,
              "shares": 20.5, "legs": [], "status": "open", "realized_pnl_amount": None,
              "exit_price": None}
    record.update(kw)
    return record


def _quote(price, daily_close=None):
    return types.SimpleNamespace(price=price, daily_close=daily_close)


def _pnl(price, direction="bullish", stop_loss=95.0, take_profit=110.0):
    return compute_unrealized_pnl(entry=100.0, stop_loss=stop_loss, take_profit=take_profit,
                                  direction=direction, current_price=price)


def _render(plan, trade, quote=None, pnl=None, *, clock=WED, market_open=True):
    return pnl_now.render_reply(plan, trade, quote, pnl, clock=clock, market_open=market_open)


# ---------------------------------------------------------------- open plans

def test_an_active_long_shows_price_open_move_and_total_with_its_basis():
    assert _render(_long(), _trade(), _quote(104.0), _pnl(104.0)).splitlines() == [
        "AAPL long · ACTIVE",
        "last 104.00 · as of 10:30 ET",
        "open 100%: +4.0% · +$82.00 · +0.8R",
        "🧾 total +$82.00 · +0.8R (paper, gross)",
    ]


def test_an_active_long_under_water_signs_both_figures():
    lines = _render(_long(), _trade(), _quote(97.0), _pnl(97.0)).splitlines()
    assert lines[2] == "open 100%: \u22123.0% · -$61.50 · \u22120.6R"
    assert lines[3] == "🧾 total -$61.50 · \u22120.6R (paper, gross)"


def test_an_active_short_measures_the_move_the_short_way():
    trade = _trade(direction="bearish", stop_loss=105.0, take_profit=90.0)
    pnl = _pnl(96.0, direction="bearish", stop_loss=105.0, take_profit=90.0)
    assert _render(_short(), trade, _quote(96.0), pnl).splitlines() == [
        "AAPL short · ACTIVE",
        "last 96.00 · as of 10:30 ET",
        "open 100%: +4.0% · +$82.00 · +0.8R",
        "🧾 total +$82.00 · +0.8R (paper, gross)",
    ]


def test_a_partial_adds_the_banked_leg_so_open_plus_banked_is_the_total():
    plan = _long(PlanStatus.PARTIAL, legs_realized=[dict(TP1_LEG)])
    assert _render(plan, _trade(), _quote(112.0), _pnl(112.0)).splitlines() == [
        "AAPL long · PARTIAL",
        "last 112.00 · as of 10:30 ET",
        "open 50%: +12.0% · +$123.00 · +1.2R",
        "banked: +$102.50 · +1.0R",
        "🧾 total +$225.50 · +2.2R (paper, gross)",
    ]


def test_with_no_linked_record_no_dollar_figure_prints():
    lines = _render(_long(), None, _quote(104.0), _pnl(104.0)).splitlines()
    assert lines[2:] == ["open 100%: +4.0% · +0.8R", "🧾 total +0.8R (paper, gross)"]
    assert "$" not in "\n".join(lines)


def test_a_record_without_shares_prints_no_dollar_figure():
    text = _render(_long(), _trade(shares=None), _quote(104.0), _pnl(104.0))
    assert "$" not in text and "+0.8R" in text


def test_market_closed_and_a_daily_close_fallback_are_both_said():
    text = _render(_long(), _trade(), _quote(104.0, dt.date(2026, 10, 9)), _pnl(104.0),
                   clock=SAT, market_open=False)
    assert text.splitlines()[1] == (
        "last 104.00 · as of 10:30 ET · daily close 2026-10-09 · market closed")


def test_a_price_that_could_not_be_fetched_says_so_and_keeps_the_banked_leg():
    plan = _long(PlanStatus.PARTIAL, legs_realized=[dict(TP1_LEG)])
    assert _render(plan, _trade(), _quote(None), None).splitlines() == [
        "AAPL long · PARTIAL", "price unavailable", "banked: +$102.50 · +1.0R"]
    assert _render(_long(), _trade(), None, None).splitlines() == [
        "AAPL long · ACTIVE", "price unavailable"]


# ------------------------------------------------- pending, closed, cancelled

def test_a_pending_plan_shows_the_price_against_its_trigger():
    plan = _long(PlanStatus.PENDING, entry_price=None)
    assert _render(plan, _trade(), _quote(98.5), _pnl(98.5)).splitlines() == [
        "AAPL long · PENDING",
        "last 98.50 · as of 10:30 ET",
        "▶ trigger 100.00 · not filled yet",
    ]


def test_a_closed_plan_shows_the_settled_record_and_no_live_price():
    plan = _long(PlanStatus.CLOSED, legs_realized=[dict(TP1_LEG), dict(RUNNER_LEG)])
    trade = _trade(status="win", realized_pnl_amount=307.5, exit_price=120.0)
    assert _render(plan, trade).splitlines() == [
        "AAPL long · CLOSED", "🧾 +$307.50 · +3.0R (paper, gross)"]


def test_a_closed_pre_tp1_loss_reads_its_exit_from_the_record():
    plan = _long(PlanStatus.CLOSED)
    trade = _trade(status="loss", realized_pnl_amount=-102.5, exit_price=95.0)
    assert _render(plan, trade).splitlines()[1] == "🧾 -$102.50 · \u22121.0R (paper, gross)"


def test_an_unsettled_close_shows_r_only():
    plan = _long(PlanStatus.CLOSED, legs_realized=[dict(TP1_LEG), dict(RUNNER_LEG)])
    assert _render(plan, _trade(status="win")).splitlines()[1] == "🧾 +3.0R (paper, gross)"
    assert _render(plan, None).splitlines()[1] == "🧾 +3.0R (paper, gross)"


def test_a_cancelled_plan_never_filled():
    assert _render(_long(PlanStatus.CANCELLED, entry_price=None), None).splitlines() == [
        "AAPL long · CANCELLED", "never filled"]


# ------------------------------------------------------------ reply_for seams

@pytest.fixture
def seams(monkeypatch):
    """reply_for's three seams, stubbed; `quoted` records every _quote call."""
    state = {"plan": _long(), "trade": _trade(), "quoted": []}

    def quote(plan, trade):
        state["quoted"].append(plan.status)
        return _quote(104.0), _pnl(104.0)

    monkeypatch.setattr(pnl_now, "_load_plan", lambda plan_id: state["plan"])
    monkeypatch.setattr(pnl_now, "_linked_trade", lambda plan_id: state["trade"])
    monkeypatch.setattr(pnl_now, "_quote", quote)
    return state


def test_reply_for_an_open_plan_prices_it_and_stamps_the_click_time(seams):
    text = pnl_now.reply_for(PID, now=WED)
    assert text.splitlines()[1] == "last 104.00 · as of 10:30 ET"
    assert seams["quoted"] == [PlanStatus.ACTIVE]


def test_reply_for_reads_market_closed_from_the_session_clock(seams):
    assert pnl_now.reply_for(PID, now=SAT).splitlines()[1].endswith("· market closed")


def test_reply_for_a_closed_or_cancelled_plan_fetches_no_price(seams):
    for status in (PlanStatus.CLOSED, PlanStatus.CANCELLED):
        seams["plan"] = _long(status)
        pnl_now.reply_for(PID, now=WED)
    assert seams["quoted"] == []


def test_reply_for_a_pruned_plan_says_it_is_gone(seams):
    seams["plan"] = None
    assert pnl_now.reply_for(PID, now=WED) == pnl_now.GONE == "This plan no longer exists."


def test_reply_for_never_raises(seams, monkeypatch):
    def boom(plan_id):
        raise RuntimeError("store down")
    monkeypatch.setattr(pnl_now, "_load_plan", boom)
    assert pnl_now.reply_for(PID, now=WED) == pnl_now.FAILED


def test_a_failing_price_fetch_is_price_unavailable_not_an_exception(monkeypatch):
    def boom(trade):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(scan_run, "quote_trade", boom)
    assert pnl_now._quote(_long(), _trade()) == (None, None)
    monkeypatch.setattr(pnl_now, "_load_plan", lambda plan_id: _long())
    monkeypatch.setattr(pnl_now, "_linked_trade", lambda plan_id: _trade())
    assert pnl_now.reply_for(PID, now=WED).splitlines()[1] == pnl_now.UNAVAILABLE


def test_quote_prices_the_record_or_the_plan_when_there_is_none(monkeypatch):
    seen = []
    monkeypatch.setattr(scan_run, "quote_trade",
                        lambda trade: seen.append(trade) or (_quote(1.0), None))
    record = _trade()
    pnl_now._quote(_long(), record)
    pnl_now._quote(_long(PlanStatus.PENDING, entry_price=None), None)
    assert seen[0] is record
    assert seen[1] == {"ticker": "AAPL", "direction": "bullish", "entry": 100.0,
                       "stop_loss": 95.0, "take_profit": 110.0}


# ------------------------------------------------------- the real record seam

@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog()


def test_linked_trade_reads_the_record_in_any_status(tlog):
    tlog.log_trade(ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
                   confidence_level=4, confidence_label="High", entry=100.0, stop_loss=95.0,
                   take_profit=110.0, plan_id=PID)
    record = pnl_now._linked_trade(PID)
    assert record["plan_id"] == PID and record["ticker"] == "AAPL"
    assert pnl_now._linked_trade("00000000-0000-0000-0000-000000000000") is None


def test_linked_trade_never_raises(monkeypatch):
    from swingbot.core.tracking import performance

    def boom(self, plan_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(performance.TradeLog, "trade_for_plan", boom)
    assert pnl_now._linked_trade(PID) is None
```

Arithmetic behind the pinned strings (record `shares = 20.5`, entry 100, stop 95 long / 105 short, risk 5): long @104 → move +4, R `4/5 = +0.8`, `$ 20.5 × 4 = +82.00`; @97 → `−3/5 = −0.6R`, `-$61.50`; short @96 → move `(96 − 100) × −1 = +4`; PARTIAL @112 with the TP1 leg banked → open `0.5 × 12/5 = +1.2R`, `20.5 × 0.5 × 12 = +$123.00`, banked `0.5 × 2.0 = +1.0R`, `20.5 × 0.5 × (110 − 100) = +$102.50`, total `+2.2R`, `+$225.50`. Closed: `total_r` = `0.5 × 2.0 + 0.5 × 4.0 = +3.0R`; pre-TP1 loss `(95 − 100)/5 = −1.0R`. `%` is `compute_unrealized_pnl`'s `pct_change` from entry 100, printed by `tokens.fmt_pct` at 1 dp.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_pnl_now.py`
Expected: FAIL at collection, `ImportError: cannot import name 'pnl_now' from 'swingbot.commands'`.

- [ ] **Step 3: Write the implementation**

Create `$WT/swingbot/commands/pnl_now.py`:

```python
"""v170 §3 / A4-A6: the 💵 P&L now button's ephemeral reply.

render_reply is pure (plan, paper record, quote and clock in; text out), so
every plan status is unit-testable. reply_for wires the three seams -- the
plan store, the paper-trade record (TradeLog.trade_for_plan, any status) and
the price (scan_run.quote_trade, the single-trade body `!pnl` runs, so the
button and `!pnl` cannot disagree on the open figure) -- and never raises:
a press always gets an answer.

Dollars: the open part and the banked legs are the paper record's own
arithmetic (record shares, not the whole shares a message prints, v170 A3);
with no linked record no dollar figure prints at all. Every total is gross
on the paper account (tokens.COST_BASIS)."""
import datetime as dt
import logging

from swingbot import config
from swingbot.core.market.session import is_regular_session, now_et
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.presentation import tokens
from swingbot.core.presentation.instructions import money_from, pnl_line, signed_r, total_r

log = logging.getLogger(__name__)

GONE = "This plan no longer exists."
UNAVAILABLE = "price unavailable"
NOT_FILLED = "not filled yet"
NEVER_FILLED = "never filled"
FAILED = "Could not compute P&L just now; please try again."

_WORD = {"bullish": "long", "bearish": "short"}
#: statuses whose reply needs a live price (closed/cancelled read the record only).
_LIVE = frozenset({PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL})


def _sign(direction: str) -> int:
    return 1 if direction == "bullish" else -1


def _clean(r: float) -> float:
    """Float noise must not print '−0.0R'."""
    return round(r, 4) + 0.0


def _head(plan) -> str:
    return f"{plan.ticker} {_WORD.get(plan.direction, plan.direction)} · {plan.status}"


def _as_of(quote, clock: dt.datetime, market_open: bool) -> str:
    """'last <price> · as of HH:MM ET' plus the daily-close date and
    'market closed' when they apply (A6: no quote carries a timestamp, so the
    fetch moment is the as-of); UNAVAILABLE when there is no price."""
    if quote is None or quote.price is None:
        return UNAVAILABLE
    parts = [f"last {tokens.fmt_price(quote.price)}", f"as of {now_et(clock):%H:%M} ET"]
    if quote.daily_close is not None:
        parts.append(f"daily close {quote.daily_close.isoformat()}")
    if not market_open:
        parts.append("market closed")
    return " · ".join(parts)


def _record_shares(trade: dict | None) -> float | None:
    shares = (trade or {}).get("shares")
    return float(shares) if shares else None


def _entry(plan, trade: dict | None) -> float:
    """The fill (the basis total_r and the feed measure R from); the
    record's entry, then the trigger, for a plan not filled yet."""
    if plan.entry_price is not None:
        return plan.entry_price
    if trade and trade.get("entry") is not None:
        return float(trade["entry"])
    return plan.trigger_price


def _figures(r: float, usd: float, shares: float | None) -> str:
    """'<$> · <R>' -- the $ only when a record with shares backs it."""
    if shares is None:
        return signed_r(r)
    return f"{tokens.fmt_money(usd, config.CURRENCY_SYMBOL)} · {signed_r(r)}"


def _banked(plan, entry: float, shares: float | None) -> tuple[float, float]:
    """(R, $) of the legs already realised: Σ fraction × r, and the record's
    shares × fraction × (exit − entry), signed by direction."""
    sign = _sign(plan.direction)
    legs = plan.legs_realized or []
    r = sum(leg["fraction"] * leg["r"] for leg in legs)
    usd = sum((shares or 0.0) * leg["fraction"] * (leg["exit_price"] - entry) * sign
              for leg in legs)
    return r, usd


def _open_part(plan, entry: float, shares: float | None, price: float) -> tuple[float, float, float]:
    """(open fraction, its R contribution, its $ contribution) at ``price``."""
    fraction = max(0.0, 1.0 - sum(leg["fraction"] for leg in plan.legs_realized or []))
    risk = abs(entry - plan.stop_loss)
    move = (price - entry) * _sign(plan.direction)
    r = fraction * move / risk if risk else 0.0
    return fraction, r, (shares or 0.0) * fraction * move


def _open_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    shares = _record_shares(trade)
    entry = _entry(plan, trade)
    banked_r, banked_usd = _banked(plan, entry, shares)
    banked = [f"banked: {_figures(_clean(banked_r), banked_usd, shares)}"] if plan.legs_realized else []
    if quote is None or quote.price is None:
        return [UNAVAILABLE, *banked]
    fraction, open_r, open_usd = _open_part(plan, entry, shares, quote.price)
    pct = tokens.fmt_pct(pnl.pct_change if pnl is not None else None)
    total = _figures(_clean(open_r + banked_r), open_usd + banked_usd, shares)
    return [_as_of(quote, clock, market_open),
            f"open {fraction:.0%}: {pct} · {_figures(_clean(open_r), open_usd, shares)}",
            *banked,
            f"{tokens.FEED_SYMBOLS['pnl']} total {total} {tokens.COST_BASIS}"]


def _pending_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    return [_as_of(quote, clock, market_open),
            f"{tokens.FEED_SYMBOLS['entry']} trigger {tokens.fmt_price(plan.trigger_price)} · {NOT_FILLED}"]


def _closed_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    """The final result from the record: the settled realized_pnl_amount
    (R only until it is settled), never a live price."""
    record = trade or {}
    money = money_from(record.get("shares"), config.CURRENCY_SYMBOL,
                       realized_amount=record.get("realized_pnl_amount"))
    return [pnl_line(_clean(total_r(plan, record.get("exit_price"))), money)]


def _cancelled_reply(plan, trade, quote, pnl, clock, market_open) -> list[str]:
    return [NEVER_FILLED]


_REPLIES = {
    PlanStatus.PENDING: _pending_reply,
    PlanStatus.ACTIVE: _open_reply,
    PlanStatus.PARTIAL: _open_reply,
    PlanStatus.CLOSED: _closed_reply,
    PlanStatus.CANCELLED: _cancelled_reply,
}


def render_reply(plan, trade: dict | None, quote, pnl, *, clock: dt.datetime,
                 market_open: bool) -> str:
    """The ephemeral reply text for ``plan`` at its status now (A4)."""
    body = _REPLIES.get(plan.status, lambda *_: [])(plan, trade, quote, pnl, clock, market_open)
    return "\n".join([_head(plan), *body])


def _load_plan(plan_id: str):
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().get(plan_id)


def _linked_trade(plan_id: str) -> dict | None:
    """The plan's paper record in any status, or None. Never raises."""
    try:
        from swingbot.core.tracking.performance import TradeLog
        return TradeLog().trade_for_plan(plan_id)
    except Exception:
        log.warning("P&L now: trade lookup failed for plan %s", plan_id, exc_info=True)
        return None


def _quote_input(plan, trade: dict | None) -> dict:
    """What quote_trade prices: the record itself (the `!pnl` row), or the
    plan's own levels when no record exists."""
    if trade:
        return trade
    return {"ticker": plan.ticker, "direction": plan.direction, "entry": _entry(plan, None),
            "stop_loss": plan.stop_loss, "take_profit": plan.tp1}


def _quote(plan, trade: dict | None):
    """(TradeQuote, UnrealizedPnL | None), or (None, None) when the fetch
    failed -- the reply then says UNAVAILABLE, never raises."""
    try:
        from swingbot.core.scanning import scan_run
        return scan_run.quote_trade(_quote_input(plan, trade))
    except Exception:
        log.warning("P&L now: price fetch failed for %s", plan.ticker, exc_info=True)
        return None, None


def reply_for(plan_id: str, *, now: dt.datetime | None = None) -> str:
    """The button's whole answer. Never raises: any failure is logged and
    answered with FAILED."""
    try:
        plan = _load_plan(plan_id)
        if plan is None:
            return GONE
        trade = _linked_trade(plan_id)
        quote, pnl = _quote(plan, trade) if plan.status in _LIVE else (None, None)
        clock = now or dt.datetime.now(dt.timezone.utc)
        return render_reply(plan, trade, quote, pnl, clock=clock,
                            market_open=is_regular_session(clock))
    except Exception:
        log.warning("P&L now: could not answer for plan %s", plan_id, exc_info=True)
        return FAILED
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_pnl_now.py`
Expected: PASS, `0 failed`, and **no skip** for `test_linked_trade_reads_the_record_in_any_status` (a skip means the test DB is down: fix Step 0, do not accept it).

If a pinned `$` string is off by a cent, the arithmetic is wrong, not the test: recheck it against the table under Step 1.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/pnl_now.py`
Expected: no output (every function grade A or B).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/commands/pnl_now.py tests/commands/test_pnl_now.py
git -C $WT commit -m "feat(v170): P&L now reply per plan status

Pure renderer plus three seams: pending shows the price against the
trigger, open plans the open part and banked legs in %, R and paper
gross dollars with an as-of line, closed plans the settled record,
cancelled plans 'never filled'. reply_for never raises.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged (only what it showed before this task).

### Task V170-11: `PnlNowButton`, `FEED_BUTTONS`, `feed_view`, registration

**Model:** sonnet — a new DynamicItem in an established pattern plus registration; the leak and restart-persistence tests carry the risk.

**Files:**
- Modify: `swingbot/commands/views.py` (module docstring; new button after `DismissButton`; `FEED_BUTTONS` and `feed_view` after `chart_only_view`; `register_persistent_views`)
- Modify: `tests/commands/test_views_persistent.py`
- Create: `tests/commands/test_views_feed.py` (suite `discord`)

**Interfaces:**
- Consumes: V170-10 `pnl_now.reply_for(plan_id, *, now=None) -> str`, `pnl_now.FAILED`, seams `pnl_now._load_plan`, `_linked_trade`, `_quote`; existing `views._template`, `custom_id_for`, `_persistable`, `_PlanButtonMixin`, `ChartButton`, `BreakdownButton`, `WatchButton`, `PLAN_BUTTONS`, `PlanActionView`.
- Produces (ledger contract, final): `views.PnlNowButton` (`ACTION = "pnl"`, `LABEL = "💵 P&L now"`, template `plan:pnl:<uuid>[:<author>]`); `views.FEED_BUTTONS: tuple[type, ...] = (PnlNowButton,)`; `views.feed_view(plan_id: str) -> discord.ui.View` (persistent, `timeout=None`; children Chart, Breakdown, Watch, P&L now in that order, each `author_id=None`; an **empty** view, with a warning, for an id that cannot form a persistent custom_id); `register_persistent_views(bot)` calls `bot.add_dynamic_items(*PLAN_BUTTONS, *FEED_BUTTONS)`. V170-12 imports `feed_view` lazily.

Rules (spec §3, A4, A10, Global Constraints): `PLAN_BUTTONS` is **not** extended (`PlanActionView` iterates it; a leak test pins it); `feed_view` takes no `open_` argument and always holds P&L now (A4); Dismiss and Following are never on the feed; every reply is ephemeral and the button never posts in the channel; the plan/price read runs off the event loop (`asyncio.to_thread`), like every other plan button.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/commands/test_views_feed.py`:

```python
"""v170 §3 / A4 / A10: the execution feed's buttons.

feed_view holds Chart, Breakdown, Watch and the new P&L now; P&L now lives
in FEED_BUTTONS, never in PLAN_BUTTONS, so the full-alert panel cannot grow
it. Every reply is ephemeral. No pytest-asyncio: coroutines run through
asyncio.run.
"""
import asyncio
import datetime as dt
import inspect
import logging
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from swingbot import config
from swingbot.commands import pnl_now, views
from swingbot.commands.views import (
    FEED_BUTTONS,
    PLAN_BUTTONS,
    BreakdownButton,
    ChartButton,
    PlanActionView,
    PnlNowButton,
    WatchButton,
    custom_id_for,
    feed_view,
)
from swingbot.core.planning.account import compute_unrealized_pnl
from swingbot.core.planning.plan_types import PlanStatus
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
OTHER = 876543210987654321
FEED_ORDER = [ChartButton, BreakdownButton, WatchButton, PnlNowButton]


def _interaction(user_id: int = OTHER) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _press(view) -> MagicMock:
    interaction = _interaction()
    button = next(item for item in view.children if isinstance(item, PnlNowButton))
    asyncio.run(button.callback(interaction))
    return interaction


def _reply_text(interaction) -> str:
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.call_args
    assert kwargs == {"ephemeral": True}
    return args[0]


def test_feed_buttons_hold_only_pnl_now():
    assert FEED_BUTTONS == (PnlNowButton,)
    assert (PnlNowButton.ACTION, PnlNowButton.LABEL) == ("pnl", "💵 P&L now")


def test_pnl_now_custom_id_round_trips_after_a_restart():
    custom_id = custom_id_for("pnl", PID, None)
    assert custom_id == f"plan:pnl:{PID}"
    match = PnlNowButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    item = asyncio.run(PnlNowButton.from_custom_id(_interaction(), MagicMock(), match))
    assert isinstance(item, PnlNowButton)
    assert (item.plan_id, item.author_id, item.custom_id) == (PID, None, custom_id)


def test_pnl_now_and_the_plan_buttons_never_claim_each_others_ids():
    pnl_id = custom_id_for("pnl", PID, None)
    assert all(cls.__discord_ui_compiled_template__.fullmatch(pnl_id) is None
               for cls in PLAN_BUTTONS)
    for cls in PLAN_BUTTONS:
        other = custom_id_for(cls.ACTION, PID, None)
        assert PnlNowButton.__discord_ui_compiled_template__.fullmatch(other) is None


def test_feed_view_is_persistent_and_holds_chart_breakdown_watch_and_pnl_now():
    view = feed_view(PID)
    assert view.timeout is None and view.is_persistent()
    assert [type(item) for item in view.children] == FEED_ORDER
    assert [item.custom_id for item in view.children] == [
        custom_id_for(cls.ACTION, PID, None) for cls in FEED_ORDER]


def test_feed_view_never_carries_dismiss_or_following():
    actions = {item.custom_id.split(":")[1] for item in feed_view(PID).children}
    assert actions == {"chart", "breakdown", "watch", "pnl"}


def test_feed_view_for_a_malformed_plan_id_is_empty_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="swingbot.commands.views"):
        view = feed_view("not-a-uuid")
    assert view.children == []
    assert "persistent custom_id" in caplog.text


def test_the_full_alert_panel_never_grows_pnl_now():
    assert PnlNowButton not in PLAN_BUTTONS
    view = PlanActionView(PID, author_id=None)
    assert [type(item) for item in view.children] == list(PLAN_BUTTONS)


def test_pnl_now_replies_ephemerally_and_never_posts_in_the_channel(monkeypatch):
    monkeypatch.setattr(pnl_now, "reply_for", lambda plan_id, now=None: f"reply for {plan_id}")
    interaction = _press(feed_view(PID))
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert _reply_text(interaction) == f"reply for {PID}"
    interaction.response.send_message.assert_not_awaited()
    assert not interaction.channel.send.called


def test_pnl_now_reads_off_the_event_loop():
    source = inspect.getsource(PnlNowButton.callback)
    assert "to_thread(pnl_now.reply_for" in source


def _seams(monkeypatch, plan, trade, quote, *, market_open=True):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(pnl_now, "_load_plan", lambda plan_id: plan)
    monkeypatch.setattr(pnl_now, "_linked_trade", lambda plan_id: trade)
    pnl = (compute_unrealized_pnl(entry=100.0, stop_loss=95.0, take_profit=110.0,
                                  direction="bullish", current_price=quote.price)
           if quote is not None and quote.price is not None else None)
    monkeypatch.setattr(pnl_now, "_quote", lambda p, t: (quote, pnl))
    monkeypatch.setattr(pnl_now, "is_regular_session", lambda now=None: market_open)


TRADE = {"plan_id": PID, "ticker": "AAPL", "direction": "bullish", "entry": 100.0,
         "stop_loss": 95.0, "take_profit": 110.0, "shares": 20.5, "status": "open",
         "realized_pnl_amount": None, "exit_price": None}
LEGS = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
        {"fraction": 0.5, "exit_price": 120.0, "r": 4.0, "reason": "tp1_runner_tp2"}]


@pytest.mark.parametrize("status, legs, trade, price, market_open, expected", [
    ("open", [], TRADE, 104.0, True, "🧾 total +$82.00 · +0.8R (paper, gross)"),
    ("closed", LEGS, {**TRADE, "status": "win", "realized_pnl_amount": 307.5},
     None, True, "🧾 +$307.50 · +3.0R (paper, gross)"),
    ("price unavailable", [], TRADE, None, True, "price unavailable"),
    ("market closed", [], TRADE, 104.0, False, "· market closed"),
])
def test_a_press_answers_each_plan_state_ephemerally(monkeypatch, status, legs, trade,
                                                     price, market_open, expected):
    plan_status = PlanStatus.CLOSED if status == "closed" else PlanStatus.ACTIVE
    plan = _plan(plan_id=PID, status=plan_status, entry_type="stop_entry", trigger_price=100.0,
                 entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=120.0, legs_realized=legs)
    quote = types.SimpleNamespace(price=price, daily_close=None) if status != "closed" else None
    _seams(monkeypatch, plan, trade, quote, market_open=market_open)
    assert expected in _reply_text(_press(feed_view(PID)))
```

In `$WT/tests/commands/test_views_persistent.py`:

1. Add `FEED_BUTTONS,` to the `from swingbot.commands.views import (...)` list (alphabetical, before `LEGACY_REPLY`), and below the `OTHER = ...` constant add:

```python
#: every DynamicItem the bot registers: the full-alert panel's and the feed's.
ALL_BUTTONS = (*PLAN_BUTTONS, *FEED_BUTTONS)
```

2. Replace `PLAN_BUTTONS` with `ALL_BUTTONS` in exactly these four tests: `test_every_custom_id_fits_discords_100_char_limit`, `test_each_button_rebuilds_from_its_custom_id_alone_without_author`, `test_each_button_rebuilds_with_its_author_segment`, `test_the_legacy_static_ids_match_no_dynamic_template`. (`test_plan_action_view_is_persistent_and_holds_one_button_per_action` keeps `PLAN_BUTTONS`: that is the leak pin.)

3. Replace the two registration tests' assertions:

```python
def test_register_persistent_views_adds_every_dynamic_item_and_the_legacy_panel():
    bot = MagicMock()
    register_persistent_views(bot)
    bot.add_dynamic_items.assert_called_once_with(*PLAN_BUTTONS, *FEED_BUTTONS)
    (legacy,), _ = bot.add_view.call_args
    assert isinstance(legacy, LegacyPlanPanel)


def test_register_persistent_views_is_accepted_by_a_real_bot():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    register_persistent_views(bot)
    assert any(isinstance(view, LegacyPlanPanel) for view in bot.persistent_views)
    registered = set(bot._connection._view_store._dynamic_items.values())
    assert registered == set(ALL_BUTTONS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_views_feed.py`
Expected: FAIL at collection, `ImportError: cannot import name 'FEED_BUTTONS' from 'swingbot.commands.views'`.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_views_persistent.py`
Expected: FAIL at collection with the same `ImportError`.

- [ ] **Step 3: Write the implementation**

In `$WT/swingbot/commands/views.py`:

1. Module docstring: after the paragraph ending `keeps the TradesPaginator author-lock / timeout pattern (swingbot/commands/trades.py:83).`, add a paragraph:

```text
v170: the execution feed (simple-alerts channel) carries its own panel,
feed_view: Chart, Breakdown and Watch as above plus PnlNowButton, whose
ephemeral reply is commands/pnl_now.py. P&L now lives in FEED_BUTTONS,
never in PLAN_BUTTONS, so the full-alert panel cannot grow it.
```

2. Imports: below `from swingbot import config`, add:

```python
from swingbot.commands import pnl_now
```

3. Directly after the `DismissButton` class (before `PLAN_BUTTONS = ...`), add:

```python
class PnlNowButton(_PlanButtonMixin, discord.ui.DynamicItem[discord.ui.Button],
                   template=_template("pnl")):
    """v170: the feed's live P&L for one plan, answered for its status at
    click time (commands/pnl_now.py). Ephemeral; never posts in the channel."""

    ACTION = "pnl"
    LABEL = "💵 P&L now"

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        reply = await asyncio.to_thread(pnl_now.reply_for, self.plan_id)
        await interaction.followup.send(reply, ephemeral=True)
```

4. Directly after `chart_only_view` (before `_legacy_reply`), add:

```python
#: v170: the feed's own DynamicItems, registered beside PLAN_BUTTONS. Never
#: appended to PLAN_BUTTONS: PlanActionView iterates that tuple.
FEED_BUTTONS: tuple[type, ...] = (PnlNowButton,)

#: the feed panel, in order: the plan buttons it reuses, then its own.
_FEED_PANEL: tuple[type, ...] = (ChartButton, BreakdownButton, WatchButton, *FEED_BUTTONS)


def feed_view(plan_id: str) -> discord.ui.View:
    """The execution feed's persistent panel (v170 §3, A4): Chart,
    Breakdown, Watch and P&L now, for every plan message whatever its
    status -- P&L now answers for the status at click time. No Dismiss: the
    feed is an order log. Empty when the plan id cannot form a persistent
    custom_id."""
    view = discord.ui.View(timeout=None)
    if not _persistable(plan_id, None):
        log.warning("feed panel: plan %r cannot form a persistent custom_id"
                    " -- posting without buttons", plan_id)
        return view
    for button_cls in _FEED_PANEL:
        view.add_item(button_cls(plan_id))
    return view
```

5. Replace `register_persistent_views`:

```python
def register_persistent_views(bot) -> None:
    """Called once from bot_core.setup_hook, before the gateway connects.
    Reads PLAN_BUTTONS and FEED_BUTTONS at call time, so a button appended
    later registers too."""
    bot.add_dynamic_items(*PLAN_BUTTONS, *FEED_BUTTONS)
    bot.add_view(LegacyPlanPanel())
```

`PnlNowButton.callback` is reached only through a `feed_view` or a registered DynamicItem, so `pnl_now` is imported at module top (commands → commands; `pnl_now` imports nothing from `views`, so there is no cycle). Confirm:

```bash
git -C $WT grep -n "commands.views\|from swingbot.commands import views" -- swingbot/commands/pnl_now.py
```

Expected: no output.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_views_feed.py`
Expected: PASS, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_views_persistent.py`
Expected: PASS, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_views_following.py`
Expected: PASS, `0 failed` (the panel it pins is unchanged).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/views.py`
Expected: only `breakdown_embed` (C 12, untouched, legacy). No line names `feed_view`, `PnlNowButton` or `register_persistent_views`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/commands/views.py tests/commands/test_views_persistent.py tests/commands/test_views_feed.py
git -C $WT commit -m "feat(v170): P&L now button and the feed panel

PnlNowButton is a persistent DynamicItem in its own FEED_BUTTONS tuple,
registered beside PLAN_BUTTONS; feed_view builds Chart, Breakdown,
Watch and P&L now. The full-alert panel is unchanged (leak test).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged.

### Task V170-12: Attach `feed_view` to the feed ticket and every feed lifecycle send

**Model:** sonnet — two send sites across the core/commands seam; layering (A8) and the never-cost-the-ping rule need care, the code is short.

**Files:**
- Modify: `swingbot/commands/scanning/alerts.py` (`_mirror`, new `_TICKET_KINDS`, `_ticket_view`)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`notify_plan_events`, new `_feed_view`, `_send_instruction`)
- Create: `tests/scanning/test_feed_buttons_attach.py` (suite `scanning`)

**Interfaces:**
- Consumes: V170-8 `ui.push_kwargs(embed, view=None)`; V170-11 `views.feed_view(plan_id)`, `views.ChartButton`, `BreakdownButton`, `WatchButton`, `PnlNowButton`; V170-4 `execution_embeds._linked_trade` (monkeypatched in tests); existing `PushEmbed.kind`, `Kind.TICKET_PLACE`, `Kind.TICKET_DO_NOT_PLACE`.
- Produces (ledger contract, final): `alerts._TICKET_KINDS = frozenset({Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE})`; `alerts._ticket_view(simple_embed, plan) -> discord.ui.View | None`; `lifecycle_embeds._feed_view(plan_id: str) -> discord.ui.View | None`; `lifecycle_embeds._send_instruction(feed, history, embed, plan, event) -> bool` (True once any channel took the message).

Rules (spec §3, A7, A8, Global Constraints):

- A view rides only on **plan-backed feed messages**: the v2 ticket (`Kind.TICKET_PLACE` / `Kind.TICKET_DO_NOT_PLACE`) in `_mirror`, and the instruction embed's feed send **and** its history copy in `notify_plan_events`. Never the strategy-signal mirror (`Kind.STRATEGY_SIGNAL`), the legacy mirror (`Kind.SETUP_SIMPLE`), a plain embed, or the history-only `build_plan_event_embed` status embed.
- Each send gets **its own** view (a discord.py View belongs to one message): the feed copy and the history copy never share an instance.
- An empty view (non-persistable id) or a view that fails to build is sent as **no view**: the message still posts and still pings. A button problem never costs a mirror its ping or a lifecycle event its delivery.
- Layering (A8): `lifecycle_embeds.py` imports `feed_view` inside `_feed_view` only; no module-level `swingbot.commands` import in core.
- `push_kwargs` without a view stays byte-identical, so every other send is untouched; `tests/scanning/test_execution_feed_routing.py` and `tests/scanning/test_simple_alerts.py` pass unchanged.
- `notify_plan_events` (C 13 today) must drop: its two sends move into `_send_instruction`.

- [ ] **Step 0: Test database up, contracts present**

The lifecycle tests store plans in `PlanStore` (Postgres). Run the index's DB check (`docker compose ... --profile test up -d db-test`, `docker ps --filter name=swing-db-test`), then:

```bash
git -C $WT grep -n "def push_kwargs(embed, view=None)" -- swingbot/core/presentation/components.py
git -C $WT grep -n "def feed_view\|^FEED_BUTTONS" -- swingbot/commands/views.py
git -C $WT grep -n "def _linked_trade" -- swingbot/core/scanning/execution_embeds.py
```

Expected: all three found; otherwise `BLOCKED: <symbol> missing (V170-8 / V170-11 / V170-4)`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scanning/test_feed_buttons_attach.py`:

```python
"""v170 §3 / A7 / A8: the feed panel rides on plan-backed feed messages only.

The v2 ticket mirror and every lifecycle instruction (feed send and its
history copy) carry feed_view; strategy-signal and legacy mirrors and the
history-only status embed never do. A button problem never costs a ping.
No pytest-asyncio: coroutines run through asyncio.run.
"""
import ast
import asyncio
import inspect
import types

import discord
import pytest

from swingbot import config
from swingbot.commands import views
from swingbot.commands.scanning import alerts
from swingbot.core import presentation as ui
from swingbot.core.planning.plan_manager import Delivery, PlanEvent
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.lifecycle_embeds import notify_plan_events
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
FEED_ORDER = [views.ChartButton, views.BreakdownButton, views.WatchButton, views.PnlNowButton]
PLAN = types.SimpleNamespace(plan_id=PID, ticker="AAPL")


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


def _types(sent: dict) -> list:
    return [type(item) for item in sent["view"].children]


def _boom(plan_id):
    raise RuntimeError("view broke")


# ------------------------------------------------------------ the feed ticket

@pytest.mark.parametrize("kind", [Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE])
def test_the_v2_ticket_mirror_carries_the_feed_panel(kind):
    simple, embed = FakeChannel(), ui.push_embed(kind, "AAPL", "bullish")
    assert asyncio.run(alerts._mirror(simple, embed, PLAN)) is True
    assert _types(simple.sent[0]) == FEED_ORDER
    assert {k: v for k, v in simple.sent[0].items() if k != "view"} == ui.push_kwargs(embed)


@pytest.mark.parametrize("embed, plan", [
    (ui.push_embed(Kind.STRATEGY_SIGNAL, "AAPL", "bullish"), PLAN),
    (ui.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish"), PLAN),
    (discord.Embed(title="plain"), PLAN),
    (ui.push_embed(Kind.TICKET_PLACE, "AAPL", "bullish"), None),
])
def test_mirrors_without_a_plan_backed_ticket_carry_no_view(embed, plan):
    simple = FakeChannel()
    assert asyncio.run(alerts._mirror(simple, embed, plan)) is True
    assert "view" not in simple.sent[0]


def test_a_ticket_whose_panel_cannot_be_built_still_mirrors(monkeypatch):
    monkeypatch.setattr(views, "feed_view", _boom)
    simple = FakeChannel()
    embed = ui.push_embed(Kind.TICKET_PLACE, "AAPL", "bullish")
    assert asyncio.run(alerts._mirror(simple, embed, PLAN)) is True
    assert "view" not in simple.sent[0]


def test_a_ticket_for_a_malformed_plan_id_posts_without_a_view():
    simple = FakeChannel()
    embed = ui.push_embed(Kind.TICKET_PLACE, "AAPL", "bullish")
    asyncio.run(alerts._mirror(simple, embed, types.SimpleNamespace(plan_id="p1", ticker="AAPL")))
    assert "view" not in simple.sent[0]


# ------------------------------------------------------- lifecycle messages

@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)
    monkeypatch.setattr(lifecycle_embeds, "_last_warned", {})
    channels = {"111": FakeChannel(), "222": FakeChannel()}
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "222")
    bot = types.SimpleNamespace(get_channel=lambda channel_id: channels.get(str(channel_id)))
    for plan_id in (PID, "p1"):
        PlanStore().add(_plan(plan_id=plan_id, status="ACTIVE", entry_price=100.0,
                              stop_loss=95.0, tp1=110.0, working_stop=100.0))
    return bot, channels["111"], channels["222"]


def _post(bot, *events):
    return asyncio.run(notify_plan_events(bot, list(events)))


def _be(plan_id=PID):
    return PlanEvent(plan_id, "be_moved", {"working_stop": 100.0})


def test_the_feed_send_and_its_history_copy_each_carry_their_own_panel(wired):
    bot, feed, history = wired
    assert _post(bot, _be()) == [Delivery(PID, "stop", 100.0)]
    assert _types(feed.sent[0]) == FEED_ORDER == _types(history.sent[0])
    assert feed.sent[0]["view"] is not history.sent[0]["view"]
    assert "silent" not in feed.sent[0] and history.sent[0]["silent"] is True


def test_history_notifies_with_the_panel_when_the_feed_is_missing(wired, monkeypatch):
    bot, feed, history = wired
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "")
    assert _post(bot, _be()) == [Delivery(PID, "stop", 100.0)]
    assert _types(history.sent[0]) == FEED_ORDER and "silent" not in history.sent[0]


def test_the_history_only_status_embed_carries_no_panel(wired):
    bot, feed, history = wired
    assert _post(bot, PlanEvent(PID, "pyramid_add", {})) == []
    assert feed.sent == [] and "view" not in history.sent[0]


def test_a_malformed_plan_id_or_a_broken_panel_still_delivers_without_a_view(wired, monkeypatch):
    bot, feed, history = wired
    assert _post(bot, _be("p1")) == [Delivery("p1", "stop", 100.0)]
    monkeypatch.setattr(views, "feed_view", _boom)
    assert _post(bot, _be()) == [Delivery(PID, "stop", 100.0)]
    assert all("view" not in sent for sent in feed.sent + history.sent)


def test_core_never_imports_commands_at_module_level():
    tree = ast.parse(inspect.getsource(lifecycle_embeds))
    names = [node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom)]
    names += [alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names]
    assert not [name for name in names if name.startswith("swingbot.commands")]
    assert "from swingbot.commands.views import feed_view" in inspect.getsource(
        lifecycle_embeds._feed_view)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_feed_buttons_attach.py`
Expected: FAIL — the ticket and lifecycle tests with `KeyError: 'view'`, the layering test with `AttributeError: ... has no attribute '_feed_view'`; the no-view tests already pass.

- [ ] **Step 3: Write the implementation**

In `$WT/swingbot/commands/scanning/alerts.py`, directly above `async def _mirror(...)`, add:

```python
#: v170 A7: the feed panel rides only on the plan-backed v2 ticket.
_TICKET_KINDS = frozenset({Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE})


def _ticket_view(simple_embed, plan):
    """The feed panel for a v2 ticket mirror, else None: a strategy-signal or
    legacy mirror has no plan for the buttons to answer for. Never raises: a
    panel that cannot be built posts the ticket without buttons rather than
    costing the mirror its ping."""
    if plan is None or getattr(simple_embed, "kind", None) not in _TICKET_KINDS:
        return None
    try:
        from swingbot.commands.views import feed_view
        view = feed_view(plan.plan_id)
    except Exception:
        log.warning("simple ticket for %s: posting without buttons",
                    getattr(plan, "ticker", "?"), exc_info=True)
        return None
    return view if view.children else None
```

and in `_mirror` replace the send line

```python
        await simple_channel.send(**ui.push_kwargs(simple_embed))
```

with

```python
        await simple_channel.send(**ui.push_kwargs(simple_embed,
                                                   view=_ticket_view(simple_embed, plan)))
```

In `$WT/swingbot/core/scanning/lifecycle_embeds.py`, directly above `async def notify_plan_events(...)`, add:

```python
def _feed_view(plan_id: str):
    """The feed panel for one lifecycle message, or None. Imported here, not
    at module level: core never imports commands at import time (v170 A8).
    Never raises: a panel that cannot be built leaves the message without
    buttons, never without its delivery."""
    try:
        from swingbot.commands.views import feed_view
        view = feed_view(plan_id)
    except Exception:
        log.warning("execution feed: posting plan %s without buttons", plan_id, exc_info=True)
        return None
    return view if view.children else None


async def _send_instruction(feed, history, embed, plan, event) -> bool:
    """Feed send (notifies), then the history copy (silent once the feed
    landed). Each send builds its own panel: a View belongs to one message.
    True once any channel took the message."""
    from swingbot.core.infra.silent_channel import silence

    pinged = False
    if feed is not None:
        try:
            await feed.send(**ui.push_kwargs(embed, view=_feed_view(plan.plan_id)))
            log_posted(embed, plan.ticker, feed)
            pinged = True
        except Exception as exc:
            _warn_throttled(plan.plan_id, "execution feed: %s for plan %s failed "
                            "on feed (%s); history will notify instead",
                            event.transition, plan.plan_id, exc)
    if history is not None:
        try:
            await (silence(history) if pinged else history).send(
                **ui.push_kwargs(embed, view=_feed_view(plan.plan_id)))
            log_posted(embed, plan.ticker, history)
            pinged = True
        except Exception as exc:
            _warn_throttled(plan.plan_id, "execution feed: history copy of %s for "
                            "plan %s failed: %s", event.transition, plan.plan_id, exc)
    return pinged
```

Then in `notify_plan_events`:

1. Delete the line `from swingbot.core.infra.silent_channel import silence` (it moved into `_send_instruction`).
2. Replace everything from `pinged = False` through the end of the history `try/except` block (the two send blocks, today `lifecycle_embeds.py:477-496`) with:

```python
            pinged = await _send_instruction(feed, history, embed, plan, event)
```

The `if pinged:` delivery/log block that follows stays exactly as it is. The history-only branch above (`status_embed = build_plan_event_embed(plan, event)` … `continue`) is untouched and keeps `ui.push_kwargs(status_embed)` with no view.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_feed_buttons_attach.py`
Expected: PASS, `0 failed`, no skips.

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py`
Expected: PASS unchanged (its plan id `p1` is not persistable, so its sends carry no view).

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py`
Expected: PASS unchanged.

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/lifecycle_embeds.py $WT/swingbot/commands/scanning/alerts.py`
Expected: `build_closed_trade_embed` (C 17, legacy, untouched) may appear; `notify_plan_events` does not appear (it drops below 11, from C 13); no line names `_send_instruction`, `_feed_view`, `_ticket_view` or `_mirror`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/commands/scanning/alerts.py swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_feed_buttons_attach.py
git -C $WT commit -m "feat(v170): feed panel on the ticket and lifecycle messages

The v2 ticket mirror and every lifecycle instruction (feed and history
copy, one view each) carry feed_view; other mirrors and the status
embed do not. Core reaches views through a function-local import, and
a panel failure never costs a ping.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged.

# Phase 6: legend, render gate, full suite

### Task V170-13: `!help` legend from `FEED_SYMBOLS`

**Model:** haiku — one constant rebuilt from an existing function, one test; fully specified.

**Files:**
- Modify: `swingbot/commands/info.py:28` (`HELP_DESCRIPTION`) and its imports
- Modify: `tests/commands/test_help_catalog.py`

**Interfaces:**
- Consumes: V170-1 `tokens.feed_legend() -> str` (`"Feed symbols: ▶ entry · … . Feed dollars: paper account, before fees, slippage and tax."`), `tokens.FEED_SYMBOLS`.
- Produces (ledger contract, final): `info.HELP_DESCRIPTION = "Alerts only, never places trades. Prefix: `!`  •  Slash: `/`" + "\n" + tokens.feed_legend()`.

Rules (spec §2 Legend, Global Constraints, index Decision 8): the legend is generated from `FEED_SYMBOLS` so it cannot drift from what the feed sends; it says "paper account, before fees, slippage and tax"; it lives in `HELP_DESCRIPTION` (the first embed's description), never as a field or a `COMMANDS_BY_CATEGORY` row (`test_help_catalog.py` pins the field list to the categories, and `help_line` would append a slash twin). The first embed stays within Discord's limits (description ≤ 4096, embed ≤ 6000).

- [ ] **Step 1: Write the failing test**

Append to `$WT/tests/commands/test_help_catalog.py`:

```python
def test_help_description_carries_the_feed_legend_from_the_symbol_table():
    from swingbot.core.presentation import tokens
    assert info.HELP_DESCRIPTION == (
        "Alerts only, never places trades. Prefix: `!`  •  Slash: `/`\n" + tokens.feed_legend())
    for glyph in tokens.FEED_SYMBOLS.values():
        assert glyph in info.HELP_DESCRIPTION
    assert "paper account, before fees, slippage and tax" in info.HELP_DESCRIPTION
    first = info.help_embeds()[0]
    assert first.description == info.HELP_DESCRIPTION
    assert len(first.description) <= 4096 and len(first) <= 6000
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_help_catalog.py`
Expected: FAIL on `test_help_description_carries_the_feed_legend_from_the_symbol_table` (the description has no legend yet); every other test passes.

- [ ] **Step 3: Write the implementation**

In `$WT/swingbot/commands/info.py`, add beside `from swingbot.core import presentation as ui`:

```python
from swingbot.core.presentation import tokens
```

and replace line 28 (`HELP_DESCRIPTION = "Alerts only, never places trades. Prefix: `!`  •  Slash: `/`"`) with:

```python
#: The help embed's description; SP17's help_embeds() reuses it. v170: its
#: second line is the execution feed's symbol legend, generated from
#: tokens.FEED_SYMBOLS so it cannot drift from what the feed sends.
HELP_DESCRIPTION = ("Alerts only, never places trades. Prefix: `!`  •  Slash: `/`\n"
                    + tokens.feed_legend())
```

(Delete the old one-line `#: The help embed's description; SP17's help_embeds() reuses it.` comment above it; the new comment replaces it.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_help_catalog.py`
Expected: PASS, `0 failed` (the existing `first.description == info.HELP_DESCRIPTION` and both-prefixes asserts still hold).

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed` (the `info_help` parity case compares the prefix and slash surfaces to each other, not to a golden text).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/info.py`
Expected: no new line (the change adds no function).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/commands/info.py tests/commands/test_help_catalog.py
git -C $WT commit -m "feat(v170): feed symbol legend in !help

The help description's second line is generated from FEED_SYMBOLS plus
the paper/gross cost-basis sentence.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged.

