# v171 Shared market-data fetch. Part 4: pre-post rebuild (V171-17..V171-22)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V171-20:" -A 300 docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_4-rebuild.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v171-shared-market-data-fetch-design.md`](../specs/2026-10-16-v171-shared-market-data-fetch-design.md) (this part: D2 "every plan, alert and exit record stores the timestamp of the quote", D5 whole, the Success row "quote age at post exceeds 5 s", Review Focus 5)
**Index:** [`2026-10-16-v171-shared-market-data-fetch_0-index.md`](2026-10-16-v171-shared-market-data-fetch_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch` (created in V171-1). Never `cd`; use `git -C $WT` and `python $WT/scripts/dev/testrun.py file <test>`. All file paths below are relative to `$WT`. After every task run `git -C $R status --short` and confirm the main tree is clean.

**Order.** V171-17 -> V171-18 -> V171-20 -> V171-21 -> V171-22; V171-19 may start right after V171-17 (disjoint files from V171-18). V171-20 also needs V171-9 (`data.get_quote_batch`) and V171-1 (`PLAN_REBUILD_ENABLED`, `QUOTE_MAX_AGE_REQUOTE_S`, `REBUILD_PRICE_MAX_AGE_S`).

**Consumed from parts 1-2 (ledger names, verified against part 2's V171-7/V171-9/V171-10 text):** `swingbot.core.marketdata.shared.kinds`: `QuoteDetail(symbol, price, trade_at, bid, ask, quote_at, source)` with `mid()` (`(bid+ask)/2` only when both > 0 and `ask >= bid`), `Asker.REQUOTE`. `data.get_quote_batch(tickers, *, asker, max_age_s=None, fresh_only=False) -> dict[str, QuoteDetail]`. Part 2 fixes: **`QuoteDetail.source` names who supplied `price`** (`"alpaca-iex"`, `"yfinance-1m"`, `"spot"`; the `off`-mode monitor wrapper uses `"legacy"` with no timestamps), while `bid`/`ask`/`quote_at` stay Alpaca's IEX quote even when `price` came from the yfinance fallback. A regular-session IEX trade older than `ALPACA_MAX_TRADE_AGE_SECONDS` arrives as `price=None` (then yfinance fills `price`); outside regular hours an old trade (yesterday's close) arrives with its own `trade_at`. `plan_manager._session_label` (V171-10) is the same rule `rebuild.session_label` implements; this part does not import `plan_manager` into `rebuild.py` (it would pull the whole manager into the planning core).

**Decisions this part fixes** (inside the ledger's contracts):

- **Price order, read off one `QuoteDetail`** (`choose_rebuild_price`): (1) `kind="trade"`: `price > 0`, `trade_at` set, `source != "yfinance-1m"`, age < `REBUILD_PRICE_MAX_AGE_S`; (2) `kind="mid"`: `mid()` not None, `quote_at` set, age < the same limit; (3) `kind="yf-1m"`: `source == "yfinance-1m"`, `trade_at` age < the limit; (4) else `kind="scan"`, the scan's own price, `confirmed=False`. Strict `<`. Ages are clamped at 0 (a print stamped a few ms in the future is age 0, not negative). A `"spot"` price counts as a trade (its `trade_at` is the spot quote's own `updated_at`).
- **An unconfirmed price never rebuilds.** `kind="scan"` keeps the scan-built plan unchanged and only stamps it (D5 "the plan is never rebuilt from an older print"). Every confirmed price rebuilds, whatever the move (D5 "always rebuilt").
- **The re-quote fetches fresh** (`max_age_s=0.0`, tier 2), never a cache hit. The 5 s clock starts "when that symbol's quote fetch completes"; `get_quote_batch` returns values without their cache age, so only a fetch made by this call knows when it completed. Cost: one small batched Alpaca call per scan with alerts (single-flighted, and written to the shared cache for the monitor). `QUOTE_MAX_AGE_REQUOTE_S` (5) stays the re-quote and miss threshold.
- **The 5 s clock:** `Requote` records `clock()` right after each fetch returns. When an item is pulled and its symbol's quote is already older than 5 s (earlier alerts took the time), that symbol is re-quoted once. `age_at_persist(ticker)` freezes the age on its first call (the plan write, or the trade write when no v2 plan is persisted) and counts a miss when it exceeds 5 s.
- **What a rebuild re-runs:** `analyze.rescenario` recomputes candidate levels, the level map, `atr_floor_pct`, `build_scenarios` (min reward, min/max stop distance, R:R, dead-cat veto) and the v135 headroom filter at the new price, from the **same frame** and the same trendline candidates; `attach_plan_v2` (through the lane's existing attach helper) re-runs `build_confluence_plan` (v115 stop clamp, trigger, expiry), the 2 % cap band (`plan_stop_ceiling`, `planned_loss_pct`) and `risk_sizing_ok`. Not re-run: confirmation, dedup, cooldown, RS gate, MTF gate, pullback dry-up (frame-only), heat, lane overlap, confidence scoring and requirements. A dropped plan revokes its confirmation exactly like a build-time rejection (`_skip_rejected_plan` / `qualify._revoke`), so it consumes no cooldown and alerts again on a later scan.
- **Display:** the embed and the simple alert read the stamp from `item.plan_v2` when present, else from the legacy `item.plan` scenario (both are stamped by `stamp_quote`, a plain `setattr`). The shown age is the print's own age at plan build (`issued_at - quote_at`), not the fetch-to-persist age.

---

# Phase 4 — Rebuild: quote stamp fields, the rebuild entry point, the analyze seam, `Requote` and lane wiring, alert surface

### Task V171-17: Quote stamp fields on `TradePlanV2` and trade records; readers show `n/a`

**Model:** opus — stored-record shape change across `planning` and `tracking`

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (append five fields after `cancel_reason_message`, the last field, ~:185)
- Modify: `swingbot/core/tracking/performance.py` (`TradeLog.log_trade` :655-764; new module helpers `_quote_field` and `format_quote_age` beside `_confidence_point_fields` :541)
- Test: `tests/planning/test_plan_quote_fields.py` (create), `tests/tracking/test_trade_quote_field.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `TradePlanV2.quote_at: str | None = None` (ISO time of the print or quote the price came from), `quote_kind: str | None = None` (`"trade"`/`"mid"`/`"yf-1m"`/`"scan"`), `quote_age_s: float | None = None` (fetch completed to plan persisted), `quote_session: str | None = None` (`"regular"`/`"pre-market"`/`"after-hours"`/`"closed"`), `price_confirmed: bool | None = None`. They round-trip through `plan_to_dict`/`plan_from_dict` with no other change (both already copy every dataclass field; missing keys take the defaults, so a pre-v171 row reads all five as `None`).
  - `TradeLog.log_trade(..., quote: dict | None = None)`: the last keyword. `quote` is the dict `{"at", "kind", "age_s", "session", "confirmed"}` built by V171-18's `rebuild.quote_record`. Stored as `record["quote"]` (a copy) only when given; `None` writes no key, so a trade logged with the flag off is byte-identical to today's.
  - `performance._quote_field(quote: dict | None) -> dict`: `{"quote": dict(quote)}` or `{}`.
  - `performance.format_quote_age(quote: dict | None) -> str`: `"n/a"` for `None`, a missing or `None` `age_s`; else `f"{age_s:.1f} s"`.

No migration: plans and trades are hybrid tables whose non-promoted fields live in `doc` JSONB (`docs/claude/schema-evolution.md` "add"). No read-time upcasting: readers that find no value show `n/a`.

- [ ] **Step 1: Write the failing plan-field tests**

Create `tests/planning/test_plan_quote_fields.py`:

```python
"""v171 D2: a plan stores the quote it was built from; pre-v171 plans read None."""
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import TradePlanV2, plan_from_dict, plan_to_dict
from tests.planning.test_plan_engine_model import _plan

FIELDS = ("quote_at", "quote_kind", "quote_age_s", "quote_session", "price_confirmed")
STAMP = {"quote_at": "2026-10-16T14:30:01+00:00", "quote_kind": "mid",
         "quote_age_s": 1.4, "quote_session": "regular", "price_confirmed": True}


def test_new_fields_default_to_none():
    plan = _plan()
    assert all(getattr(plan, name) is None for name in FIELDS)


def test_fields_round_trip_through_the_dict():
    back = plan_from_dict(plan_to_dict(_plan(**STAMP)))
    assert {name: getattr(back, name) for name in FIELDS} == STAMP


def test_a_pre_v171_dict_reads_every_field_as_none():
    d = plan_to_dict(_plan())
    for name in FIELDS:
        d.pop(name)
    back = plan_from_dict(d)
    assert isinstance(back, TradePlanV2)
    assert all(getattr(back, name) is None for name in FIELDS)


def test_fields_round_trip_through_the_plan_store():
    store = PlanStore()
    store.add(_plan(plan_id="v171-q1", **STAMP))
    back = store.get("v171-q1")
    assert {name: getattr(back, name) for name in FIELDS} == STAMP


def test_unconfirmed_scan_price_round_trips_false_not_none():
    back = plan_from_dict(plan_to_dict(_plan(quote_kind="scan", price_confirmed=False)))
    assert back.price_confirmed is False and back.quote_kind == "scan"
```

- [ ] **Step 2: Write the failing trade-record tests**

Create `tests/tracking/test_trade_quote_field.py`:

```python
"""v171 D2: a trade stores the quote stamp of the plan it was opened from."""
import inspect

from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog, format_quote_age

QUOTE = {"at": "2026-10-16T14:30:01+00:00", "kind": "trade", "age_s": 2.3,
         "session": "regular", "confirmed": True}


def _open(log, **kw):
    return log.log_trade(ticker="AAPL", strategy="S/R Confluence", horizon_key="4w",
                         direction="bullish", confidence_level=3, confidence_label="Medium",
                         entry=100.0, stop_loss=98.0, take_profit=106.0, **kw)


def test_log_trade_stores_the_quote_stamp():
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, quote=QUOTE))
    assert trade["quote"] == QUOTE


def test_log_trade_copies_the_quote_dict():
    log = TradeLog()
    quote = dict(QUOTE)
    trade_id = _open(log, quote=quote)
    quote["age_s"] = 99.0
    assert log.get_trade_by_id(trade_id)["quote"]["age_s"] == 2.3


def test_log_trade_without_a_quote_writes_no_key():
    log = TradeLog()
    assert "quote" not in log.get_trade_by_id(_open(log))


def test_quote_is_the_last_keyword_and_defaults_to_none():
    params = inspect.signature(TradeLog.log_trade).parameters
    assert list(params)[-1] == "quote" and params["quote"].default is None


def test_quote_field_helper():
    assert performance._quote_field(None) == {}
    assert performance._quote_field(QUOTE) == {"quote": QUOTE}


def test_format_quote_age():
    assert format_quote_age(None) == "n/a"
    assert format_quote_age({"age_s": None}) == "n/a"
    assert format_quote_age({}) == "n/a"
    assert format_quote_age(QUOTE) == "2.3 s"
    assert format_quote_age({"age_s": 0}) == "0.0 s"
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_quote_fields.py` and `python $WT/scripts/dev/testrun.py file tests/tracking/test_trade_quote_field.py`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'quote_at'`, `... 'quote'`, `ImportError: cannot import name 'format_quote_age'`).

- [ ] **Step 4: Add the plan fields**

In `swingbot/core/planning/plan_types.py`, after `cancel_reason_message: str | None = None`:

```python
    # v171 D2: the quote this plan was built from (planning/rebuild.py stamps it
    # before the first post). quote_at: ISO time of the print or bid/ask quote;
    # quote_kind: "trade" | "mid" | "yf-1m" | "scan"; quote_age_s: seconds from
    # that quote's fetch completing to this plan being persisted;
    # quote_session: "regular" | "pre-market" | "after-hours" | "closed";
    # price_confirmed: False = built on the scan price ("price not confirmed
    # live"). None everywhere = written before v171 or with the rebuild off;
    # readers show n/a and never infer a value.
    quote_at: str | None = None
    quote_kind: str | None = None
    quote_age_s: float | None = None
    quote_session: str | None = None
    price_confirmed: bool | None = None
```

- [ ] **Step 5: Add the trade field and the helpers**

In `swingbot/core/tracking/performance.py`, after `_confidence_point_fields`, add `_quote_field(quote)` and `format_quote_age(quote)` with the Interfaces behaviour (docstring of `format_quote_age`: "the reader side of the v171 trade quote stamp; n/a for pre-v171 rows"). In `TradeLog.log_trade`, append `quote=None` as the last keyword of the signature and, directly after the `if trendline_fit:` block, add one unconditional line:

```python
        record.update(_quote_field(quote))   # v171 D2: present only when stamped
```

No branch is added inside `log_trade`.

- [ ] **Step 6: Run both test files to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_quote_fields.py` and `python $WT/scripts/dev/testrun.py file tests/tracking/test_trade_quote_field.py`
Expected: PASS (5 and 6 tests).

- [ ] **Step 7: Regression and complexity**

Run: `python $WT/scripts/dev/testrun.py file tests/tracking/test_log_trade_confidence_points.py`, `python $WT/scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`, `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_engine_model.py`
Expected: PASS.
Run: `python -m radon cc -s -n C $WT/swingbot/core/tracking/performance.py $WT/swingbot/core/planning/plan_types.py`
Expected: `TradeLog.log_trade - C (15)` unchanged; `_quote_field` and `format_quote_age` absent (below C).

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/planning/plan_types.py swingbot/core/tracking/performance.py tests/planning/test_plan_quote_fields.py tests/tracking/test_trade_quote_field.py
git -C $WT commit -m "feat(v171): quote stamp fields on plans and trade records (V171-17)"
git -C $R status --short
```

### Task V171-18: `planning/rebuild.py`: D5 price choice and the one rebuild entry point

**Model:** opus — the price every posted plan is built from, gates re-run

**Files:**
- Create: `swingbot/core/planning/rebuild.py`
- Test: `tests/planning/test_rebuild.py` (create)

**Interfaces:**
- Consumes: `QuoteDetail` (V171-2: `price`, `trade_at`, `bid`, `ask`, `quote_at`, `source`, `mid()`); `config.REBUILD_PRICE_MAX_AGE_S` (V171-1, 60); `config.PLAN_ENGINE_V2` (exists); `swingbot.core.market.session.is_regular_session`, `is_tape_open`, `now_et`, `RTH_OPEN` (exist); the five plan fields (V171-17).
- Produces (ledger row, plus the kind constants):
  - `KIND_TRADE = "trade"`, `KIND_MID = "mid"`, `KIND_YF = "yf-1m"`, `KIND_SCAN = "scan"`.
  - `@dataclass(frozen=True) class RebuildPrice: price: float; kind: str; age_s: float | None; quote_at: str | None; fetched_at: float | None; confirmed: bool; session: str`. `age_s` is the chosen print's own age at choice time (rounded to 0.1 s; `None` for `"scan"`); `fetched_at` is the `time.monotonic()` reading when the symbol's quote fetch completed (`None` from `choose_rebuild_price`; V171-20's `Requote` sets it with `dataclasses.replace`).
  - `session_label(now: datetime) -> str`: `"regular"` / `"pre-market"` / `"after-hours"` / `"closed"`, the same rule as V171-10's `plan_manager._session_label`.
  - `choose_rebuild_price(quote: QuoteDetail | None, scan_price: float, now: datetime, *, max_age_s: float | None = None) -> RebuildPrice`: the order in this part's header. `max_age_s` overrides `REBUILD_PRICE_MAX_AGE_S`.
  - `@dataclass class RebuildOutcome: kept: bool; reason: str | None; price: RebuildPrice`.
  - `rebuild_before_post(item, price: RebuildPrice, *, rescenario: Callable[[float], Any | None], attach: Callable[[Any], None]) -> RebuildOutcome`.
  - `stamp_quote(plan, price: RebuildPrice, age_at_persist_s: float | None = None) -> None`: sets `quote_at`, `quote_kind`, `quote_age_s` (= `age_at_persist_s`), `quote_session`, `price_confirmed` with `setattr` (works on `TradePlanV2` and on the legacy `levels.Scenario`).
  - `quote_record(price: RebuildPrice, age_at_persist_s: float | None) -> dict`: `{"at": price.quote_at, "kind": price.kind, "age_s": age_at_persist_s, "session": price.session, "confirmed": price.confirmed}` (V171-17's trade `quote`).

`rebuild_before_post` behaviour, in order:
1. `price.confirmed is False`: stamp the display target, return `RebuildOutcome(True, None, price)`. `rescenario` and `attach` are not called; the plan stays exactly as the scan built it.
2. `scenario = rescenario(price.price)`; `None` -> `RebuildOutcome(False, "rebuild:no_scenario", price)`.
3. Re-price the item: `item.plan = scenario`; `item.plan_v2 = None`; `item.plan_v2_rejected = None`; `item.plan_v2_rejected_plan = None`; `item.plan_v2_rejected_margin = None`; `item.result.close = price.price`; `item.result.scenario = scenario`. Then `attach(scenario)`.
4. Only when `config.PLAN_ENGINE_V2 == "on"`: a set `item.plan_v2_rejected` drops with `f"rebuild:{reason}"`; a missing `item.plan_v2` (the builder raised and `attach_plan_v2` logged it) drops with `"rebuild:no_plan"`, so a rebuild never posts un-gated legacy numbers in `on` mode.
5. Stamp the display target and return kept. The display target is `item.plan_v2` when not None, else `item.plan`.

No I/O, no clock reads except through `now` and the arguments; `rebuild.py` imports nothing from `scanning` (the lanes pass `rescenario`/`attach` in), so it stays one entry point for every lane (spec D5 "one function in `swingbot/core/planning/`").

- [ ] **Step 1: Write the failing price-choice tests**

Create `tests/planning/test_rebuild.py`:

```python
"""v171 D5: the rebuild price order and the one rebuild entry point."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning import rebuild
from swingbot.core.planning.rebuild import (RebuildPrice, choose_rebuild_price, quote_record,
                                            rebuild_before_post, session_label, stamp_quote)
from tests.planning.test_plan_engine_model import _plan

ET = ZoneInfo("America/New_York")
REG = datetime(2026, 10, 15, 11, 0, tzinfo=ET).astimezone(timezone.utc)   # Thursday, in session
PRE = datetime(2026, 10, 15, 8, 0, tzinfo=ET).astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def _limit(monkeypatch):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)


def _ago(now, s):
    return now - timedelta(seconds=s)


def _q(now=REG, price=101.0, trade_age=2.0, bid=None, ask=None, quote_age=None,
       source="alpaca-iex"):
    return QuoteDetail(symbol="AAPL", price=price,
                       trade_at=None if trade_age is None else _ago(now, trade_age),
                       bid=bid, ask=ask,
                       quote_at=None if quote_age is None else _ago(now, quote_age),
                       source=source)


def test_live_trade_under_60s_wins():
    q = _q(trade_age=2.0, bid=100.9, ask=101.1, quote_age=1.0)
    p = choose_rebuild_price(q, 100.0, REG)
    assert (p.price, p.kind, p.age_s, p.confirmed, p.session) == (101.0, "trade", 2.0, True, "regular")
    assert p.quote_at == q.trade_at.isoformat() and p.fetched_at is None


def test_stale_trade_falls_to_a_fresh_mid():
    q = _q(trade_age=90.0, bid=100.0, ask=100.4, quote_age=3.0)
    p = choose_rebuild_price(q, 99.0, REG)
    assert (p.price, p.kind, p.age_s, p.confirmed) == (100.2, "mid", 3.0, True)
    assert p.quote_at == q.quote_at.isoformat()


def test_iex_stale_in_session_uses_the_mid_before_the_yfinance_bar():
    """Router: stale IEX trade -> price from yfinance, bid/ask still IEX."""
    q = _q(price=101.5, trade_age=20.0, bid=101.0, ask=101.2, quote_age=4.0, source="yfinance-1m")
    assert choose_rebuild_price(q, 99.0, REG).kind == "mid"


def test_yfinance_minute_bar_under_60s_when_no_fresh_mid():
    q = _q(price=101.5, trade_age=20.0, bid=101.0, ask=101.2, quote_age=120.0, source="yfinance-1m")
    p = choose_rebuild_price(q, 99.0, REG)
    assert (p.price, p.kind, p.age_s, p.confirmed) == (101.5, "yf-1m", 20.0, True)


def test_old_yfinance_bar_keeps_the_scan_price_unconfirmed():
    q = _q(price=101.5, trade_age=90.0, source="yfinance-1m")
    p = choose_rebuild_price(q, 99.0, REG)
    assert (p.price, p.kind, p.age_s, p.quote_at, p.confirmed) == (99.0, "scan", None, None, False)


def test_pre_market_with_yesterdays_close_and_an_old_quote_is_not_confirmed():
    """Review Focus 5: last IEX trade is yesterday's close, quote 5 min old."""
    q = _q(now=PRE, trade_age=15 * 3600, bid=100.0, ask=100.2, quote_age=300.0)
    p = choose_rebuild_price(q, 99.5, PRE)
    assert (p.price, p.kind, p.confirmed, p.session) == (99.5, "scan", False, "pre-market")


def test_exactly_60s_is_too_old():
    assert choose_rebuild_price(_q(trade_age=60.0), 99.0, REG).kind == "scan"


def test_a_print_stamped_in_the_future_has_age_zero():
    p = choose_rebuild_price(_q(trade_age=-0.4), 99.0, REG)
    assert (p.kind, p.age_s) == ("trade", 0.0)


def test_crossed_or_one_sided_quote_gives_no_mid():
    assert choose_rebuild_price(_q(price=None, trade_age=None, bid=101.0, ask=100.0,
                                   quote_age=1.0), 99.0, REG).kind == "scan"
    assert choose_rebuild_price(_q(price=None, trade_age=None, bid=None, ask=100.0,
                                   quote_age=1.0), 99.0, REG).kind == "scan"


def test_no_quote_or_no_timestamps_keeps_the_scan_price():
    assert choose_rebuild_price(None, 99.0, REG).kind == "scan"
    legacy = _q(trade_age=None, source="legacy")
    assert choose_rebuild_price(legacy, 99.0, REG).kind == "scan"


def test_spot_price_counts_as_a_trade():
    assert choose_rebuild_price(_q(trade_age=5.0, source="spot"), 99.0, REG).kind == "trade"


def test_max_age_override():
    assert choose_rebuild_price(_q(trade_age=10.0), 99.0, REG, max_age_s=5).kind == "scan"


@pytest.mark.parametrize("when, label", [
    (datetime(2026, 10, 15, 11, 0, tzinfo=ET), "regular"),
    (datetime(2026, 10, 15, 8, 0, tzinfo=ET), "pre-market"),
    (datetime(2026, 10, 15, 17, 0, tzinfo=ET), "after-hours"),
    (datetime(2026, 10, 15, 2, 0, tzinfo=ET), "closed"),
    (datetime(2026, 10, 17, 11, 0, tzinfo=ET), "closed"),          # Saturday
])
def test_session_label(when, label):
    assert session_label(when) == label
```

- [ ] **Step 2: Write the failing rebuild-entry tests**

Append to `tests/planning/test_rebuild.py`:

```python
def _price(kind="trade", price=101.0, confirmed=True, session="regular"):
    return RebuildPrice(price=price, kind=kind, age_s=2.0 if confirmed else None,
                        quote_at=REG.isoformat() if confirmed else None,
                        fetched_at=None, confirmed=confirmed, session=session)


def _item(plan_v2="old-v2"):
    old = SimpleNamespace(entry=100.0, direction="bullish")
    return SimpleNamespace(result=SimpleNamespace(ticker="AAPL", close=100.0, scenario=old),
                           plan=old, plan_v2=plan_v2, plan_v2_rejected=None,
                           plan_v2_rejected_plan=None, plan_v2_rejected_margin=None)


class _Calls:
    def __init__(self, scenario, build=True, reject=None):
        self.scenario, self.build, self.reject = scenario, build, reject
        self.rescenario_prices, self.attached = [], []

    def rescenario(self, price):
        self.rescenario_prices.append(price)
        return self.scenario

    def attach_to(self, item):
        def attach(scenario):
            assert item.plan is scenario and item.plan_v2 is None   # cleared before attach
            self.attached.append(scenario)
            if self.reject:
                item.plan_v2_rejected = self.reject
            elif self.build:
                item.plan_v2 = _plan(trigger_price=scenario.entry)
        return attach


def _run(item, calls, price):
    return rebuild_before_post(item, price, rescenario=calls.rescenario,
                               attach=calls.attach_to(item))


def test_a_confirmed_price_rebuilds_and_stamps_the_new_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item, new = _item(), SimpleNamespace(entry=101.0, direction="bullish")
    calls = _Calls(new)
    out = _run(item, calls, _price())
    assert (out.kept, out.reason) == (True, None)
    assert calls.rescenario_prices == [101.0] and calls.attached == [new]
    assert item.plan is new and item.result.scenario is new and item.result.close == 101.0
    assert item.plan_v2.trigger_price == 101.0
    assert (item.plan_v2.quote_kind, item.plan_v2.price_confirmed,
            item.plan_v2.quote_session, item.plan_v2.quote_at) == ("trade", True, "regular",
                                                                   REG.isoformat())
    assert item.plan_v2.quote_age_s is None          # set at persist time (V171-20)


def test_no_scenario_at_the_new_price_drops_the_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = _item()
    calls = _Calls(None)
    out = _run(item, calls, _price())
    assert (out.kept, out.reason) == (False, "rebuild:no_scenario")
    assert calls.attached == []


def test_a_gate_rejection_at_the_new_price_drops_the_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = _item()
    out = _run(item, _Calls(SimpleNamespace(entry=101.0), reject="risk_cap"), _price())
    assert (out.kept, out.reason) == (False, "rebuild:risk_cap")


def test_a_builder_failure_in_on_mode_never_posts_legacy_numbers(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    out = _run(_item(), _Calls(SimpleNamespace(entry=101.0), build=False), _price())
    assert (out.kept, out.reason) == (False, "rebuild:no_plan")


def test_legacy_mode_keeps_and_stamps_the_scenario(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item, new = _item(plan_v2=None), SimpleNamespace(entry=101.0, direction="bullish")
    out = _run(item, _Calls(new, build=False), _price(kind="mid"))
    assert out.kept and item.plan is new
    assert (new.quote_kind, new.price_confirmed) == ("mid", True)


def test_an_unconfirmed_price_never_rebuilds(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    v2 = _plan()
    item = _item(plan_v2=v2)
    old = item.plan
    calls = _Calls(SimpleNamespace(entry=999.0))
    out = _run(item, calls, _price(kind="scan", price=100.0, confirmed=False, session="pre-market"))
    assert (out.kept, out.reason) == (True, None)
    assert calls.rescenario_prices == [] and calls.attached == []
    assert item.plan is old and item.plan_v2 is v2 and item.result.close == 100.0
    assert (v2.quote_kind, v2.price_confirmed, v2.quote_session, v2.quote_at) == (
        "scan", False, "pre-market", None)


def test_stamp_quote_and_quote_record():
    plan, price = _plan(), _price(kind="mid")
    stamp_quote(plan, price, 1.7)
    assert (plan.quote_at, plan.quote_kind, plan.quote_age_s, plan.quote_session,
            plan.price_confirmed) == (REG.isoformat(), "mid", 1.7, "regular", True)
    assert quote_record(price, 1.7) == {"at": REG.isoformat(), "kind": "mid", "age_s": 1.7,
                                        "session": "regular", "confirmed": True}


def test_rebuild_imports_nothing_from_scanning():
    import inspect
    assert "swingbot.core.scanning" not in inspect.getsource(rebuild)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_rebuild.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.planning.rebuild'`.

- [ ] **Step 4: Implement `swingbot/core/planning/rebuild.py`**

Module docstring: "v171 D5: the one pre-post rebuild entry point. The lanes pass `rescenario` (re-run the scan's scenario build at the new price, same frame) and `attach` (their existing plan attach); this module chooses the price, re-prices the item and stamps the record. Posted plans never reach it." Imports: `dataclasses.dataclass`, `datetime`, `typing.Any, Callable`, `swingbot.config`, `swingbot.core.market.session` (`RTH_OPEN`, `is_regular_session`, `is_tape_open`, `now_et`), and `QuoteDetail` under `TYPE_CHECKING` only.

`session_label` is the four-line rule of V171-10's `_session_label` (regular, else closed when the tape is shut, else pre-market before `RTH_OPEN`, else after-hours). The price choice is the one algorithm the tests do not fully pin, so it is spelled out (each helper below stays at A/B complexity):

```python
def _age(ts, now) -> float | None:
    return None if ts is None else max(0.0, (now - ts).total_seconds())

def _fresh(ts, now, limit) -> bool:
    age = _age(ts, now)
    return age is not None and age < limit

def _candidates(quote):
    """(kind, price, timestamp) in the D5 order; a candidate missing a part is skipped."""
    if quote is None:
        return ()
    traded = quote.price if quote.source != "yfinance-1m" else None
    yf = quote.price if quote.source == "yfinance-1m" else None
    return ((KIND_TRADE, traded, quote.trade_at),
            (KIND_MID, quote.mid(), quote.quote_at),
            (KIND_YF, yf, quote.trade_at))

def choose_rebuild_price(quote, scan_price, now, *, max_age_s=None) -> RebuildPrice:
    limit = float(config.REBUILD_PRICE_MAX_AGE_S if max_age_s is None else max_age_s)
    session = session_label(now)
    for kind, price, ts in _candidates(quote):
        if price and price > 0 and _fresh(ts, now, limit):
            return RebuildPrice(float(price), kind, round(_age(ts, now), 1),
                                ts.isoformat(), None, True, session)
    return RebuildPrice(float(scan_price), KIND_SCAN, None, None, None, False, session)
```

`rebuild_before_post` follows the five numbered steps above through three helpers: `_reprice(item, scenario, price: float) -> None` (step 3's assignments), `_rejection(item) -> str | None` (step 4: `None` unless `PLAN_ENGINE_V2 == "on"`; then `item.plan_v2_rejected`, else `"no_plan"` when `item.plan_v2` is None), `_display_target(item)` (`item.plan_v2` if not None else `item.plan`). `stamp_quote` and `quote_record` follow the Interfaces block.

- [ ] **Step 5: Run to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_rebuild.py`
Expected: PASS (25 tests).

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/core/planning/rebuild.py`
Expected: no output (every function below C).

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/planning/rebuild.py tests/planning/test_rebuild.py
git -C $WT commit -m "feat(v171): planning/rebuild.py, the D5 price order and rebuild entry point (V171-18)"
git -C $R status --short
```

### Task V171-19: Analyze seam: extract per-horizon scenario build from `_scan_one`; `rescenario` at a new price; `ScanItem` keeps trendline candidates and scan price

**Model:** opus — splits a CC 36 function in signal territory without changing behaviour

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (`ScanItem` :74-103; `_scan_one` :755-1150, the `hard_filters or {...}` default at ~:809 and the `collect_candidate_levels` .. `build_scenarios` block at ~:949-998; new helpers after `_apply_pullback_dryup` :742-752)
- Test: `tests/scanning/test_rescenario.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks (V171-18's `rebuild_before_post` calls `rescenario` through the lanes' closures in V171-20/V171-21).
- Produces:
  - `class HorizonBuild(NamedTuple): candidates: Any; supports: list; resistances: list; scenarios: list`.
  - `analyze._horizon_scenarios(df, h: dict, current_price: float, trendline_candidates, hard_filters: dict) -> HorizonBuild`: exactly today's block (`levels.collect_candidate_levels(df, h, current_price, trendline_candidates=...)`, `levels.build_level_map(..., candidates=...)`, `levels.atr_floor_pct`, the `effective_min_reward` / `effective_max_stop` lines with their whole comment, `levels.build_scenarios(..., block_bullish=veto_bullish_for(df))`). **Two refinements of the ledger row, both local to this task:** it returns `HorizonBuild` rather than the bare scenario list (`_scan_one` keeps using `candidates`, `supports` and `resistances` after the call, and `rescenario` needs the new level map), and it takes no `horizon_key` (the block never read it; the two debug lines that name the ticker and horizon stay in `_scan_one`). No other task calls `_horizon_scenarios`.
  - `analyze._default_hard_filters() -> dict`: the six-key dict `_scan_one` builds today when `hard_filters` is None (`min_reward_pct`, `max_stop_loss_pct`, `min_stop_distance_pct`, `min_risk_reward_ratio`, `mtf_adjacent_gate`, `confluence_deviation_pct` from `config`).
  - `ScanItem.trendline_candidates: object = None`, `ScanItem.scan_price: float | None = None`, and one more additive field, `ScanItem.hard_filters: dict | None = None` (the scan's `ScanParams` snapshot: `_sync_run_scan` passes `_hard_filters_snapshot()`, which can differ from `config`, so `rescenario` must reuse the scan's own filters, not re-read config). All three are set in `_scan_one`'s `ScanItem(...)` constructor call.
  - `analyze.rescenario(item, df, price: float) -> Scenario | None`: `None` when `df` is None or `price` is not > 0. Otherwise `_horizon_scenarios(df, HORIZONS[item.result.horizon_key], price, item.trendline_candidates, item.hard_filters or _default_hard_filters())`, then `_apply_headroom(build.scenarios, build.supports, build.resistances, {"failed_counts": {"headroom": 0}}, ticker, horizon_key)` (v135 headroom reads the path from the entry to target 1, so it is price-dependent and re-runs), then the first scenario whose `direction == item.plan.direction`. When one is found, `item.level_map = (build.supports, build.resistances)` before returning it, so `attach_plan_v2` builds its targets from the map at the new price; when none is found, `item.level_map` is left untouched.

**What does not change.** `_scan_one`'s results are identical (same calls, same order, same arguments). Pullback dry-up (frame-only), the MTF gate, confluence counts, confidence and requirements are not re-run by `rescenario`. The trendline candidates are the scan's (computed once per ticker at the scan price, spec D5 "level inputs reused"). **NO-LOOKAHEAD:** `rescenario` reads only the frame the scan analysed; it never appends a bar, never writes the quote into the forming bar, never mutates `df` (spec D5 "not spliced into today's forming bar").

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_rescenario.py`:

```python
"""v171 D5: the per-horizon scenario seam and rescenario at a re-quoted price."""
import dataclasses

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.edge import gates as gates_mod
from swingbot.core.scanning import analyze
from tests.scanning.test_engine_v2_plans import _structured_df

HF = {"min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
      "min_risk_reward_ratio": 0.01, "mtf_adjacent_gate": False,
      "confluence_deviation_pct": 1.0}


@pytest.fixture
def loose(monkeypatch):
    monkeypatch.setitem(analyze.HORIZONS["4w"], "sr_target_min_pct", 1.0)


def _items(df):
    stats = analyze._scan_one("T0", df, ["4w"], None, None, 0, 0, hard_filters=dict(HF))
    assert stats["items"], "the structured frame must build a 4w scenario"
    return stats["items"]


def test_horizon_scenarios_matches_the_inline_calls(loose):
    df = _structured_df()
    h, price = analyze.HORIZONS["4w"], float(df["Close"].iloc[-1])
    build = analyze._horizon_scenarios(df, h, price, None, dict(HF))
    cands = levels.collect_candidate_levels(df, h, price, trendline_candidates=None)
    sup, res = levels.build_level_map(df, h, price, candidates=cands)
    oracle = levels.build_scenarios(
        price, sup, res, max(HF["min_reward_pct"], h["sr_target_min_pct"] * 0.15),
        atr_floor=levels.atr_floor_pct(df, price, h), min_stop_distance_pct=0.0,
        max_stop_distance_pct=max(HF["max_stop_loss_pct"], h.get("max_risk_pct", 50.0)),
        min_risk_reward=0.01, block_bullish=analyze.veto_bullish_for(df))
    assert [(s.direction, s.entry, s.stop_loss, s.take_profit) for s in build.scenarios] == \
           [(s.direction, s.entry, s.stop_loss, s.take_profit) for s in oracle]
    assert [lv.price for lv in build.supports] == [lv.price for lv in sup]


def test_default_hard_filters_reads_config(monkeypatch):
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 4.5)
    assert analyze._default_hard_filters()["min_reward_pct"] == 4.5
    assert set(analyze._default_hard_filters()) == set(HF)


def test_scan_items_carry_scan_price_candidates_and_filters(loose):
    df = _structured_df()
    item = _items(df)[0]
    assert item.scan_price == pytest.approx(float(df["Close"].iloc[-1]))
    assert item.trendline_candidates is not None
    assert item.hard_filters == HF


def test_rescenario_at_the_scan_price_reproduces_the_scenario(loose):
    df = _structured_df()
    item = next(i for i in _items(df) if i.level_map is not None)
    again = analyze.rescenario(item, df, item.scan_price)
    assert again is not None
    assert (again.direction, again.entry, again.stop_loss, again.take_profit) == (
        item.plan.direction, item.plan.entry, item.plan.stop_loss, item.plan.take_profit)


def test_rescenario_rebuilds_at_the_new_price_from_the_stored_inputs(loose, monkeypatch):
    df = _structured_df()
    item = _items(df)[0]
    seen = {}
    real_collect, real_build = levels.collect_candidate_levels, levels.build_scenarios

    def collect(df_, h, price, trendline_candidates=None):
        seen["collect"] = (price, trendline_candidates)
        return real_collect(df_, h, price, trendline_candidates=trendline_candidates)

    def build(price, *a, **k):
        seen["build_price"] = price
        return real_build(price, *a, **k)

    monkeypatch.setattr(levels, "collect_candidate_levels", collect)
    monkeypatch.setattr(levels, "build_scenarios", build)
    new = item.scan_price * 1.003
    out = analyze.rescenario(item, df, new)
    assert seen["collect"][0] == new and seen["collect"][1] is item.trendline_candidates
    assert seen["build_price"] == new
    if out is not None:
        assert out.entry == pytest.approx(new) and out.direction == item.plan.direction


def test_rescenario_updates_the_level_map_only_when_kept(loose, monkeypatch):
    df = _structured_df()
    item = _items(df)[0]
    before = item.level_map
    other = "bearish" if item.plan.direction == "bullish" else "bullish"
    fake = analyze.HorizonBuild(None, ["S"], ["R"],
                                [dataclasses.replace(item.plan, direction=other)])
    monkeypatch.setattr(analyze, "_horizon_scenarios", lambda *a, **k: fake)
    monkeypatch.setattr(gates_mod, "filter_headroom", lambda s, sup, res: (list(s), []))
    assert analyze.rescenario(item, df, item.scan_price) is None
    assert item.level_map is before
    same = analyze.HorizonBuild(None, ["S"], ["R"], [item.plan])
    monkeypatch.setattr(analyze, "_horizon_scenarios", lambda *a, **k: same)
    assert analyze.rescenario(item, df, item.scan_price) is item.plan
    assert item.level_map == (["S"], ["R"])


def test_rescenario_reruns_the_headroom_filter(loose, monkeypatch):
    df = _structured_df()
    item = _items(df)[0]
    monkeypatch.setattr(gates_mod, "filter_headroom", lambda s, sup, res: ([], list(s)))
    assert analyze.rescenario(item, df, item.scan_price) is None


def test_rescenario_without_a_frame_or_a_price_is_none(loose):
    df = _structured_df()
    item = _items(df)[0]
    assert analyze.rescenario(item, None, 100.0) is None
    assert analyze.rescenario(item, df, 0.0) is None
    assert analyze.rescenario(item, df, None) is None


def test_rescenario_reads_only_the_scan_frame(loose):
    """NO-LOOKAHEAD: the frame is the scan's, truncated at its last bar; the
    rebuild never appends, splices or mutates a bar."""
    full = _structured_df()
    extra = full.iloc[[-1]].copy()
    extra.index = [full.index[-1] + pd.offsets.BDay(1)]
    full = pd.concat([full, extra * 1.05])
    trunc = full.iloc[:-1].copy()
    snapshot = trunc.copy()
    item = _items(trunc)[0]
    a = analyze.rescenario(item, trunc, item.scan_price * 1.002)
    b = analyze.rescenario(item, full.iloc[:-1], item.scan_price * 1.002)
    assert trunc.equals(snapshot)
    assert (a is None) == (b is None)
    if a is not None:
        assert (a.entry, a.stop_loss, a.take_profit) == (b.entry, b.stop_loss, b.take_profit)
```

(`gates_mod` is `swingbot.core.edge.gates`, the module `analyze.py` imports at :22, so patching `filter_headroom` there reaches `_apply_headroom`. `_scan_one` with `io=None` uses `LIVE_IO`, whose monitoring and track record read the per-checkout test database, as `test_store_write_halt_partial.py` already does.)

- [ ] **Step 2: Run to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_rescenario.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.scanning.analyze' has no attribute '_horizon_scenarios'` (and `rescenario`, `HorizonBuild`, `_default_hard_filters`).

- [ ] **Step 3: Add the `ScanItem` fields**

After `candidate_context` in `ScanItem`:

```python
    # v171 D5: what the pre-post rebuild needs to re-run this item's scenario
    # build at a re-quoted price from the same frame (analyze.rescenario).
    trendline_candidates: object = None   # the scan's per-ticker trendline levels
    scan_price: float | None = None       # current_price this item was built at
    hard_filters: dict | None = None      # the scan's hard-filter snapshot
```

- [ ] **Step 4: Extract the helpers and rewire `_scan_one`**

Add `HorizonBuild`, `_default_hard_filters` and `_horizon_scenarios` (Interfaces) after `_apply_pullback_dryup`. Move the `effective_min_reward`/`effective_max_stop` lines and their whole comment into `_horizon_scenarios` verbatim. In `_scan_one`:
- `hard_filters = hard_filters or _default_hard_filters()` replaces the inline dict.
- Inside the horizon loop, the `log.debug(... building levels ...)` line stays; then `candidates, supports, resistances, scenarios = _horizon_scenarios(df, h, current_price, trendline_candidates, hard_filters)`; then the existing `log.debug(... support level(s) ...)` line. `floor_pct`, `effective_min_reward` and `effective_max_stop` were used only by the moved block; remove them from `_scan_one`.
- The `ScanItem(...)` call gains `trendline_candidates=trendline_candidates, scan_price=current_price, hard_filters=hard_filters`.

Then add `rescenario(item, df, price)` per Interfaces, docstring: "v171 D5: the item's scenario rebuilt at `price` from the scan's own frame, trendline candidates and hard filters; None when that direction no longer qualifies. Never touches `df`."

- [ ] **Step 5: Run to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_rescenario.py`
Expected: PASS (10 tests).

- [ ] **Step 6: Behaviour regression on the scan paths that drive `_scan_one`**

Run each: `python $WT/scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`, `... file tests/scanning/test_headroom_live.py`, `... file tests/scanning/test_pullback_dryup_live.py`, `... file tests/scanning/test_mtf_gate.py`, `... file tests/scanning/test_short_lane_scan.py`, `... file tests/scanning/test_engine_quality_inputs.py`
Expected: PASS, the same counts as before the change.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/analyze.py`
Expected: `_scan_one` below its E (36) (the `or` default moved out), `build_decision_context` D (24), `attach_plan_v2` C (12), `_check_near_close` C (12) unchanged; `_horizon_scenarios`, `rescenario`, `_default_hard_filters` absent (below C).

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/scanning/analyze.py tests/scanning/test_rescenario.py
git -C $WT commit -m "refactor(v171): per-horizon scenario seam and rescenario at a re-quoted price (V171-19)"
git -C $R status --short
```

### Task V171-20: `Requote` (one batched quote, per-item re-quote once, persist age) and main-scan wiring

**Model:** opus — the alert loop of `_sync_run_scan` F(100), new logic only via unconditional helpers

**Files:**
- Create: `swingbot/core/scanning/requote.py`
- Modify: `swingbot/core/scanning/scan_run.py` (imports :1-50; `_persist_plan_v2` :334-353; the plan-attach block in the merge loop :691-706; the alert loop `for item in deduped:` :801; the `_persist_plan_v2(plan_v2, alerts)` call :990; the `trade_log.log_trade(...)` call :992-1013; the `scan_stats` dict :1163-1176; new helpers after `_persist_plan_v2`)
- Test: `tests/scanning/test_requote.py` (create), `tests/scanning/test_scan_rebuild_wiring.py` (create)

**Interfaces:**
- Consumes: `data.get_quote_batch(tickers, *, asker, max_age_s=None, fresh_only=False)` (V171-9); `Asker.REQUOTE`, `QuoteDetail` (V171-2); `config.PLAN_REBUILD_ENABLED`, `config.QUOTE_MAX_AGE_REQUOTE_S` (V171-1); `rebuild.choose_rebuild_price`, `RebuildPrice`, `RebuildOutcome`, `rebuild_before_post`, `quote_record` (V171-18); `analyze.rescenario`, `ScanItem.scan_price` (V171-19); `TradeLog.log_trade(..., quote=)` and the plan fields (V171-17).
- Produces:
  - `class Requote` in `swingbot/core/scanning/requote.py`:
    - `__init__(self, items, *, quote_fn: Callable[[list[str]], dict[str, QuoteDetail]] | None = None, clock=time.monotonic, now_fn=None)`. Reads `config.PLAN_REBUILD_ENABLED` once into `self.enabled`. Collects the unique tickers, in order, of the items with `all_requirements_met` (only those can alert). `quote_fn` defaults to the module function `_default_quote_fn` (looked up at construction, so tests patch the module attribute). `now_fn` defaults to `datetime.now(timezone.utc)`.
    - `iter_fresh(self, items, *, rebuild: Callable[[Any, RebuildPrice], RebuildOutcome]) -> Iterator`. Flag off: `yield from items`, no fetch, no call to `rebuild`. Flag on: an item without `all_requirements_met` is yielded untouched. For the first quotable item, one batched `quote_fn(all tickers)`. For a later item whose symbol's quote fetch completed more than `QUOTE_MAX_AGE_REQUOTE_S` ago, one `quote_fn([ticker])`, at most once per symbol per scan. Then `choose_rebuild_price(quote, item.scan_price or item.result.close, now_fn())`, with `fetched_at` set via `dataclasses.replace`, then `rebuild(item, price)`. A kept item is yielded and counted `kept`; a dropped one is counted `dropped`, logged at INFO (`"%s (%s, %s): not posted -- %s (rebuild at %.2f, %s)"`: ticker, horizon, trend, reason, price, kind) and not yielded.
    - `age_at_persist(self, ticker: str) -> float | None`. The first call per ticker freezes `round(clock() - fetched_at, 2)` and counts a miss when it is above `QUOTE_MAX_AGE_REQUOTE_S`; later calls return the frozen value. `None` when the symbol was never quoted (flag off included).
    - `price_for(self, ticker: str) -> RebuildPrice | None`: the price the symbol's last kept item was built from. An addition to the ledger row, consumed only by `scan_run._trade_quote` and V171-21.
    - `misses` (property, int); `stats(self) -> dict` = `{"kept": int, "dropped": int, "misses": int}`.
  - `requote._default_quote_fn(tickers: list[str]) -> dict[str, QuoteDetail]` = `data.get_quote_batch(tickers, asker=Asker.REQUOTE, max_age_s=0.0)` (fresh fetch, see this part's header; tier 2 is never budget-deferred, and the layer treats a 0 window as "never serve from cache", the rule `ADMIN_FRESH` already relies on). `data` is imported inside the function, so `scanning.requote` does not import `marketdata.data` at module load.
  - In `scan_run.py`:
    - `_persist_plan_v2(plan_v2, alerts=(), requote=None) -> None`: before `PlanStore().add`, `_stamp_persist_age(plan_v2, requote)`.
    - `_stamp_persist_age(plan_v2, requote) -> None`: no-op when `requote` is None or not enabled; else `plan_v2.quote_age_s = requote.age_at_persist(plan_v2.ticker)`.
    - `_trade_quote(requote, ticker: str) -> dict | None`: `None` when `requote` is None, not enabled, or has no price for `ticker`; else `rebuild.quote_record(price, requote.age_at_persist(ticker))`.
    - `_attach_item_plan(item, scenario, df, regimes, regime) -> None`: today's attach block (`analyze._regime_at(regimes, df.index[-1] if df is not None and len(df) > 0 else None)`, `analyze.attach_plan_v2(item, scenario, df, ticker, horizon_key, level_map=item.level_map, regime=regime, rs_percentile=item.rs_percentile, breadth=item.breadth, regime2_state=...)`, then `regime_aligned`), moved out of `_sync_run_scan` unchanged and called from both the merge loop and the rebuild.
    - `_rebuild_item(item, price, *, fresh_data, regimes, regime, require_confirmation) -> RebuildOutcome`: `rebuild.rebuild_before_post(item, price, rescenario=lambda p: analyze.rescenario(item, df, p), attach=lambda s: _attach_item_plan(item, s, df, regimes, regime))` with `df = fresh_data.get(item.result.ticker)`. On a drop: `item.plan_v2_rejected = outcome.reason`, then `_skip_rejected_plan(item, require_confirmation)` (logs and revokes the confirmation, so the drop consumes nothing).
    - `_rebuild_stats(requote) -> dict`: `{}` when not enabled, else `{"rebuild": requote.stats()}`.
    - `scan_stats` gains `**_rebuild_stats(requote)`, so the key exists only with the flag on.

**`_sync_run_scan` edits, each a call or an argument, no new branch:**
1. Merge loop (:696-706): the `df_for_item`/`regime2_state`/`attach_plan_v2`/`regime_aligned` lines become `_attach_item_plan(item, item.plan, fresh_data.get(item.result.ticker), regimes, regime)`. The `if (config.PLAN_ENGINE_V2 == "on" and ...plan_v2_rejected)` block below stays as is.
2. Directly before the alert loop: `requote = Requote(deduped)`. The loop header `for item in deduped:` becomes `for item in requote.iter_fresh(deduped, rebuild=functools.partial(_rebuild_item, fresh_data=fresh_data, regimes=regimes, regime=regime, require_confirmation=require_confirmation)):`. The body's first line `result, plan, conf = item.result, item.plan, item.conf` therefore reads the rebuilt plan, so the log line, `build_explanation`, `plan_numbers_for_display`, the trendline fit, the trade row, the chart (`render_decision_chart(... item.plan_v2 ...)` or `generate_trade_chart(... nums ..., market_price=plan.market_price)`), the embed and the simple alert all come from it (spec D5 "what the user sees matches").
3. `_persist_plan_v2(plan_v2, alerts)` becomes `_persist_plan_v2(plan_v2, alerts, requote)`.
4. `trade_log.log_trade(...)` gains `quote=_trade_quote(requote, result.ticker)` after `**_confidence_point_kwargs(conf)`.
5. `scan_stats` gains `**_rebuild_stats(requote)` after `**fetch.fetch_stats()`.

Imports added: `import functools`, `from swingbot.core.planning import rebuild`, `from .requote import Requote`.

- [ ] **Step 1: Write the failing `Requote` tests**

Create `tests/scanning/test_requote.py`:

```python
"""v171 D5: one batched re-quote, a per-symbol re-quote once, the 5 s clock."""
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning.rebuild import RebuildOutcome
from swingbot.core.scanning import requote as requote_mod
from swingbot.core.scanning.requote import Requote

NOW = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)      # 11:00 ET, in session


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def _item(ticker, ok=True, scan_price=100.0, horizon="4w"):
    return SimpleNamespace(result=SimpleNamespace(ticker=ticker, close=scan_price,
                                                  horizon_key=horizon, trend="bullish"),
                           all_requirements_met=ok, scan_price=scan_price)


def _quote(ticker, price=101.0, age=1.0):
    return QuoteDetail(symbol=ticker, price=price, trade_at=NOW - timedelta(seconds=age),
                       bid=None, ask=None, quote_at=None, source="alpaca-iex")


class Quotes:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, tickers):
        self.calls.append(list(tickers))
        if self.fail:
            raise TimeoutError("alpaca")
        return {t: _quote(t) for t in tickers}


def _keep(seen):
    def rebuild(item, price):
        seen.append((item.result.ticker, price))
        return RebuildOutcome(True, None, price)
    return rebuild


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", True)
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_REQUOTE_S", 5)
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)


def test_flag_off_yields_everything_untouched_with_no_fetch(monkeypatch):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", False)
    items, quotes, seen = [_item("AAPL"), _item("MSFT", ok=False)], Quotes(), []
    rq = Requote(items, quote_fn=quotes)
    assert list(rq.iter_fresh(items, rebuild=_keep(seen))) == items
    assert quotes.calls == [] and seen == []
    assert rq.age_at_persist("AAPL") is None and rq.price_for("AAPL") is None


def test_one_batched_fetch_for_the_alerting_symbols_only(on):
    items = [_item("AAPL"), _item("MSFT", ok=False), _item("NVDA"), _item("AAPL", horizon="2w")]
    quotes, seen = Quotes(), []
    rq = Requote(items, quote_fn=quotes, clock=Clock(), now_fn=lambda: NOW)
    out = list(rq.iter_fresh(items, rebuild=_keep(seen)))
    assert out == items                               # the unmet item passes through untouched
    assert quotes.calls == [["AAPL", "NVDA"]]
    assert [t for t, _ in seen] == ["AAPL", "NVDA", "AAPL"]
    assert seen[0][1].kind == "trade" and seen[0][1].price == 101.0
    assert seen[0][1].fetched_at == 1000.0


def test_a_symbol_whose_quote_aged_past_5s_is_requoted_once(on):
    items = [_item("AAPL"), _item("NVDA"), _item("NVDA", horizon="2w")]
    clock, quotes, seen = Clock(), Quotes(), []
    rq = Requote(items, quote_fn=quotes, clock=clock, now_fn=lambda: NOW)
    it = rq.iter_fresh(items, rebuild=_keep(seen))
    next(it)
    clock.t += 6.0                                    # the first alert took 6 s
    next(it)
    clock.t += 6.0
    next(it)
    assert quotes.calls == [["AAPL", "NVDA"], ["NVDA"]]
    assert seen[1][1].fetched_at == 1006.0


def test_age_at_persist_freezes_and_counts_a_miss(on):
    items = [_item("AAPL"), _item("NVDA")]
    clock = Clock()
    rq = Requote(items, quote_fn=Quotes(), clock=clock, now_fn=lambda: NOW)
    it = rq.iter_fresh(items, rebuild=_keep([]))
    next(it)
    clock.t += 1.25
    assert rq.age_at_persist("AAPL") == 1.25
    clock.t += 10.0
    assert rq.age_at_persist("AAPL") == 1.25          # frozen at the first (persist) call
    next(it)
    assert rq.age_at_persist("NVDA") == 11.25 and rq.misses == 1
    assert rq.stats() == {"kept": 2, "dropped": 0, "misses": 1}


def test_a_dropped_item_is_skipped_and_logged(on, caplog):
    items = [_item("AAPL"), _item("NVDA")]
    rq = Requote(items, quote_fn=Quotes(), clock=Clock(), now_fn=lambda: NOW)

    def rebuild(item, price):
        kept = item.result.ticker != "AAPL"
        return RebuildOutcome(kept, None if kept else "rebuild:risk_cap", price)

    with caplog.at_level(logging.INFO, logger=requote_mod.log.name):
        out = list(rq.iter_fresh(items, rebuild=rebuild))
    assert [i.result.ticker for i in out] == ["NVDA"]
    assert rq.stats() == {"kept": 1, "dropped": 1, "misses": 0}
    assert "AAPL (4w, bullish): not posted -- rebuild:risk_cap" in caplog.text
    assert rq.price_for("AAPL") is None and rq.price_for("NVDA").kind == "trade"


def test_a_failed_fetch_keeps_the_scan_price_unconfirmed(on):
    items = [_item("AAPL", scan_price=99.0)]
    seen = []
    rq = Requote(items, quote_fn=Quotes(fail=True), clock=Clock(), now_fn=lambda: NOW)
    assert list(rq.iter_fresh(items, rebuild=_keep(seen))) == items
    price = seen[0][1]
    assert (price.kind, price.price, price.confirmed) == ("scan", 99.0, False)
    assert price.fetched_at == 1000.0


def test_scan_price_falls_back_to_the_result_close(on):
    item = _item("AAPL")
    item.scan_price = None
    item.result.close = 98.0
    seen = []
    rq = Requote([item], quote_fn=lambda t: {}, clock=Clock(), now_fn=lambda: NOW)
    list(rq.iter_fresh([item], rebuild=_keep(seen)))
    assert seen[0][1].price == 98.0


def test_default_quote_fn_fetches_fresh_at_tier_2(monkeypatch):
    from swingbot.core.marketdata import data
    calls = []
    monkeypatch.setattr(data, "get_quote_batch",
                        lambda tickers, **kw: calls.append((list(tickers), kw)) or {})
    requote_mod._default_quote_fn(["AAPL"])
    assert calls == [(["AAPL"], {"asker": Asker.REQUOTE, "max_age_s": 0.0})]
```

- [ ] **Step 2: Write the failing wiring tests**

Create `tests/scanning/test_scan_rebuild_wiring.py`:

```python
"""v171 D5: the main scan rebuilds every alerting plan from the re-quote, and the
embed, chart, plan and trade all come from the rebuilt plan."""
import dataclasses
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import swingbot.config as config
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, engine, fetch, requote as requote_mod, runstate, scan_run
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.scanning.test_engine_v2_plans import _structured_df

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-10-15T15:00:00+00:00", 1000.0, True, "regular")


class _Store:
    plans: list = []
    def add(self, plan): type(self).plans.append(plan)


class _FakeRequote:
    enabled = True
    def __init__(self, age=1.5, price=PRICE): self.age, self.price = age, price
    def age_at_persist(self, ticker): return self.age
    def price_for(self, ticker): return self.price
    def stats(self): return {"kept": 1, "dropped": 0, "misses": 0}


def test_persist_stamps_the_age_only_with_a_live_requote(monkeypatch):
    monkeypatch.setattr(scan_run, "PlanStore", _Store)
    monkeypatch.setattr(scan_run, "log_plan_armed", lambda p: None)
    plan = _plan()
    scan_run._persist_plan_v2(plan, (), _FakeRequote(age=2.25))
    assert plan.quote_age_s == 2.25
    off = _FakeRequote()
    off.enabled = False
    other = _plan(plan_id="p2")
    scan_run._persist_plan_v2(other, (), off)
    scan_run._persist_plan_v2(_plan(plan_id="p3"))
    assert other.quote_age_s is None


def test_trade_quote_and_rebuild_stats():
    assert scan_run._trade_quote(None, "AAPL") is None
    assert scan_run._trade_quote(_FakeRequote(price=None), "AAPL") is None
    assert scan_run._trade_quote(_FakeRequote(age=1.5), "AAPL") == {
        "at": PRICE.quote_at, "kind": "trade", "age_s": 1.5, "session": "regular",
        "confirmed": True}
    off = _FakeRequote()
    off.enabled = False
    assert scan_run._rebuild_stats(off) == {}
    assert scan_run._rebuild_stats(_FakeRequote()) == {
        "rebuild": {"kept": 1, "dropped": 0, "misses": 0}}


def test_a_rebuild_drop_revokes_the_confirmation(monkeypatch):
    revoked = []
    monkeypatch.setattr(scan_run.state, "revoke_confirmation",
                        lambda key, value, prev: revoked.append((key, value, prev)))
    monkeypatch.setattr(scan_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(False, "rebuild:risk_cap", price))
    item = SimpleNamespace(result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend="bullish",
                                                  state_key="k", state_value="v"),
                           plan=SimpleNamespace(stop_distance_pct=2.5), previous_confirmed="p",
                           plan_v2_rejected=None)
    out = scan_run._rebuild_item(item, PRICE, fresh_data={}, regimes=None, regime=None,
                                 require_confirmation=True)
    assert not out.kept and item.plan_v2_rejected == "rebuild:risk_cap"
    assert revoked == [("k", "v", "p")]


def _scan_env(monkeypatch, *, rebuild_on: bool):
    df = _structured_df()
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", rebuild_on)
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_REQUOTE_S", 5)
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "DECISION_CHART_ENABLED", False)
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.01)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setitem(scan_run.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["T0"])
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "T0" else None)
    log = TradeLog()
    monkeypatch.setattr(scan_run, "trade_log", log)
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(scan_run, "earnings_within_window", lambda t, d: None)
    monkeypatch.setattr(scan_run, "get_market_events", lambda d: [])
    monkeypatch.setattr(scan_run, "notify_secondary", lambda *a, **k: None)
    monkeypatch.setattr(scan_run, "log_plan_armed", lambda p: None)
    monkeypatch.setattr(scan_run, "build_simple_alert", lambda item: "simple")
    _Store.plans = []
    monkeypatch.setattr(scan_run, "PlanStore", _Store)
    seen = {"embed_plans": [], "chart_entries": [], "rebuilt": [], "quotes": []}
    monkeypatch.setattr(scan_run, "build_embed",
                        lambda item, *a, **k: seen["embed_plans"].append(item.plan) or "embed")
    monkeypatch.setattr(scan_run, "generate_trade_chart",
                        lambda ticker, df_, entry, *a, **k: seen["chart_entries"].append(entry))
    real = analyze.rescenario

    def spy(item, frame, price):
        out = real(item, frame, price)
        out = dataclasses.replace(out) if out is not None else None   # a new object
        seen["rebuilt"].append(out)
        return out

    monkeypatch.setattr(analyze, "rescenario", spy)
    close = float(df["Close"].iloc[-1])

    def quotes(tickers):
        seen["quotes"].append(list(tickers))
        now = datetime.now(timezone.utc)
        return {t: QuoteDetail(t, close, now - timedelta(seconds=1), None, None, None,
                               "alpaca-iex") for t in tickers}

    monkeypatch.setattr(requote_mod, "_default_quote_fn", quotes)
    return log, seen


def test_main_scan_posts_only_the_rebuilt_plan(monkeypatch, stub_batch_fetch):
    log, seen = _scan_env(monkeypatch, rebuild_on=True)
    alerts, _, _ = engine._sync_run_scan("4w", require_confirmation=False, progress=None,
                                         min_confluence=0)
    assert alerts, "the structured frame must alert"
    assert seen["quotes"] == [["T0"]]                       # one batched re-quote
    assert seen["embed_plans"] and all(any(p is r for r in seen["rebuilt"])
                                        for p in seen["embed_plans"])   # identity: the rebuilt object
    stored = _Store.plans
    assert stored and all(p.quote_kind == "trade" and p.price_confirmed for p in stored)
    assert all(p.quote_age_s is not None and p.quote_age_s < 5 for p in stored)
    trades = log.get_trades(status=None, limit=None)
    assert trades and all(t["quote"]["kind"] == "trade" for t in trades)
    assert seen["chart_entries"] == [t["entry"] for t in trades]


def test_flag_off_scan_is_todays_path(monkeypatch, stub_batch_fetch):
    log, seen = _scan_env(monkeypatch, rebuild_on=False)
    alerts, _, _ = engine._sync_run_scan("4w", require_confirmation=False, progress=None,
                                         min_confluence=0)
    assert alerts and seen["quotes"] == [] and seen["rebuilt"] == []
    assert all(p.quote_kind is None and p.quote_age_s is None for p in _Store.plans)
    assert all("quote" not in t for t in log.get_trades(status=None, limit=None))
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_requote.py` and `python $WT/scripts/dev/testrun.py file tests/scanning/test_scan_rebuild_wiring.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.scanning.requote'`.

- [ ] **Step 4: Implement `swingbot/core/scanning/requote.py`**

Module docstring: "v171 D5: the pre-post re-quote. One batched fresh quote for the symbols about to alert, a re-quote once per symbol whose quote aged past QUOTE_MAX_AGE_REQUOTE_S, and the 5 s clock from fetch completion to persist." `log = logging.getLogger(__name__)`. Module helpers: `_wants_quote(item) -> bool` (`getattr(item, "all_requirements_met", True)`), `_ticker(item) -> str`, `_scan_price(item) -> float` (`getattr(item, "scan_price", None) or item.result.close`), `_default_quote_fn` (Interfaces).

The class keeps `self._quotes: dict[str, QuoteDetail]`, `self._fetched_at: dict[str, float]`, `self._ages: dict[str, float]`, `self._prices: dict[str, RebuildPrice]`, `self._requoted: set[str]`, `self._batched: bool`, `self.kept`, `self.dropped`, `self._misses`. Private methods, each below C:
- `_fetch(self, tickers: list[str]) -> None`: `quote_fn(list(tickers))` under `try/except Exception` (warning `"Re-quote failed for %d symbol(s): %s"` and `{}`). `done = self._clock()`. A ticker that got a quote stores it and `fetched_at = done`. A ticker that did not keeps any earlier quote and its earlier `fetched_at`, or gets `fetched_at = done` when it had none (the clock still started: the fetch completed, empty).
- `_ensure_fresh(self, ticker: str) -> None`: the first call does the batched `_fetch(self._tickers)`; a later call re-fetches `[ticker]` only when `self._clock() - self._fetched_at.get(ticker, float("-inf")) > config.QUOTE_MAX_AGE_REQUOTE_S` and the ticker is not in `self._requoted` (then it is added).
- `_rebuild(self, item, rebuild) -> RebuildOutcome`: `_ensure_fresh`, choose the price, `dataclasses.replace(price, fetched_at=self._fetched_at.get(ticker))`, call `rebuild`, record `self._prices[ticker] = outcome.price` when kept.

`iter_fresh`, `age_at_persist`, `price_for`, `misses`, `stats` per Interfaces.

- [ ] **Step 5: Wire `scan_run.py`**

Add the imports, `_stamp_persist_age`, `_trade_quote`, `_attach_item_plan`, `_rebuild_item`, `_rebuild_stats` after `_persist_plan_v2`, the `requote=None` parameter of `_persist_plan_v2` (its first line becomes `_stamp_persist_age(plan_v2, requote)`), and the five `_sync_run_scan` edits listed above. `_persist_plan_v2`'s docstring gains: "v171: `requote` stamps the plan's fetch-to-persist quote age (and counts a miss) right before the write."

- [ ] **Step 6: Run both test files to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_requote.py` and `python $WT/scripts/dev/testrun.py file tests/scanning/test_scan_rebuild_wiring.py`
Expected: PASS (8 and 5 tests).

- [ ] **Step 7: Regression on every test that drives `_sync_run_scan`**

Run each: `python $WT/scripts/dev/testrun.py file tests/scanning/test_store_write_halt_partial.py`, `... file tests/scanning/test_engine_v2_plans.py`, `... file tests/scanning/test_gate_rejection_hooks.py`, `... file tests/scanning/test_headroom_live.py`, `... file tests/scanning/test_rs_gate_wiring.py`, `... file tests/scanning/test_engine_quality_inputs.py`, `... file tests/scanning/test_short_lane_split.py`, `... file tests/tracking/test_log_trade_confidence_points.py`
Expected: PASS, same counts as before (the flag defaults to off).

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/scan_run.py $WT/swingbot/core/scanning/requote.py`
Expected: `_sync_run_scan` at most F (100) (it drops by the moved attach block's branches); no other function at C or above in either file.

- [ ] **Step 9: Commit**

```bash
git -C $WT add swingbot/core/scanning/requote.py swingbot/core/scanning/scan_run.py tests/scanning/test_requote.py tests/scanning/test_scan_rebuild_wiring.py
git -C $WT commit -m "feat(v171): Requote and the main-scan pre-post rebuild (V171-20)"
git -C $R status --short
```

### Task V171-21: SHORT lane through the same `Requote` and `rebuild_before_post`

**Model:** sonnet — one scanning module reusing V171-18/V171-20 contracts

**Files:**
- Modify: `swingbot/core/scanning/short_run.py` (imports :13-43; `_log_trade` :174-197; `_alert_for` :272-299; `_build_alerts` :302-314; the `_build_alerts(...)` call in `_sync_run_short_scan` :~420; new helpers before `_build_alerts`)
- Test: `tests/scanning/test_short_lane_rebuild.py` (create)

**Interfaces:**
- Consumes: `Requote` (`iter_fresh`, `enabled`), `scan_run._persist_plan_v2(plan_v2, alerts, requote)`, `scan_run._trade_quote(requote, ticker)` (V171-20); `rebuild.rebuild_before_post`, `RebuildOutcome` (V171-18); `analyze.rescenario` (V171-19); `qualify._attach_plan(item, context)`, `qualify._revoke(item, context)`, `qualify.QualifyContext` (exist, qualify.py:47-108).
- Produces (the ledger row; `_attach_for` takes the lane's `QualifyContext` instead of `frames`, because `qualify._attach_plan` needs the regimes and breadth it carries; no other task calls it):
  - `short_run._rescenario_for(item, frames) -> Callable[[float], Scenario | None]`: `lambda price: analyze.rescenario(item, frames.get(item.result.ticker), price)`.
  - `short_run._attach_for(item, context: qualify.QualifyContext) -> Callable[[Scenario], None]`: sets `item.plan = scenario`, then `qualify._attach_plan(item, context)` (the lane's existing attach: same frame, regimes, `regime_aligned`).
  - `short_run._bare_context(frames) -> qualify.QualifyContext`: `QualifyContext(frames=frames, spy=None, sector_of={}, etf_symbol_of={}, sector_frames={}, regime=None, regimes=None)`, only for callers that pass no context (the existing tests call `_build_alerts` positionally).
  - `short_run._rebuild_fn(frames, context) -> Callable[[Any, RebuildPrice], RebuildOutcome]`: runs `rebuild.rebuild_before_post(item, price, rescenario=_rescenario_for(item, frames), attach=_attach_for(item, context))`. On a drop it sets `item.plan_v2_rejected = outcome.reason` and calls `qualify._revoke(item, context)` (log plus confirmation revoke, the lane's own build-time rejection path).
  - `_build_alerts(deduped, require_confirmation, frames, spy_df, funnel=None, qualify_context=None)`: `requote = Requote(deduped)`. The loop iterates `requote.iter_fresh(deduped, rebuild=_rebuild_fn(frames, qualify_context or _bare_context(frames)))`; the body is unchanged except `_alert_for(..., funnel, requote=requote)`.
  - `_alert_for(item, frames, spy_df, account_cfg, alerts, funnel=None, requote=None)` passes `requote=requote` to `_log_trade`. `_log_trade(item, nums, explanation, fit, alerts, origin=None, requote=None)` calls `scan_run._persist_plan_v2(plan_v2, alerts, requote)` and adds `quote=scan_run._trade_quote(requote, result.ticker)` to `trade_log.log_trade(...)`. No branch is added (`_log_trade` stays C (13)).
  - `_sync_run_short_scan` passes `qualify_context=_qualify_context(require_confirmation, frames, lane)` to `_build_alerts`.

Because `_alert_for` reads `item.plan`, `item.plan_v2` and `item.result` after the rebuild, the SHORT embed, the chart (`_render_chart`), the trendline fit and the trade row come from the rebuilt plan, exactly as in the main lane.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_short_lane_rebuild.py`:

```python
"""v171 D5: the SHORT lane rebuilds through the same Requote and entry point."""
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, qualify, requote as requote_mod, short_run

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-10-15T15:00:00+00:00", 1000.0, True, "regular")


def _item(ticker="AAA"):
    return SimpleNamespace(result=SimpleNamespace(ticker=ticker, close=100.0, horizon_key="4w",
                                                  trend="bearish"),
                           all_requirements_met=True, scan_price=100.0, plan="old",
                           plan_v2=None, plan_v2_rejected=None)


def test_rescenario_for_uses_the_lane_frame(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "rescenario", lambda item, df, p: calls.append((df, p)) or "s")
    item = _item()
    assert short_run._rescenario_for(item, {"AAA": "frame"})(101.0) == "s"
    assert short_run._rescenario_for(item, {})(99.0) == "s"
    assert calls == [("frame", 101.0), (None, 99.0)]


def test_attach_for_sets_the_scenario_then_uses_the_lane_attach(monkeypatch):
    seen = []
    monkeypatch.setattr(qualify, "_attach_plan", lambda item, ctx: seen.append((item.plan, ctx)))
    item, ctx = _item(), short_run._bare_context({})
    short_run._attach_for(item, ctx)("new")
    assert item.plan == "new" and seen == [("new", ctx)]


def test_a_dropped_short_revokes_through_the_lane_path(monkeypatch):
    revoked = []
    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(False, "rebuild:no_scenario", price))
    monkeypatch.setattr(qualify, "_revoke", lambda item, ctx: revoked.append(item.plan_v2_rejected))
    item = _item()
    out = short_run._rebuild_fn({}, short_run._bare_context({}))(item, PRICE)
    assert not out.kept and revoked == ["rebuild:no_scenario"]


@pytest.fixture
def lane(monkeypatch):
    posted = []
    monkeypatch.setattr(short_run, "load_account_config", lambda: {})
    monkeypatch.setattr(short_run.runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(short_run, "_alert_for",
                        lambda item, frames, spy, cfg, alerts, funnel=None, requote=None:
                        posted.append((item.result.ticker, requote)))
    return posted


def test_build_alerts_rebuilds_and_posts_only_kept_items(monkeypatch, lane):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", True)
    quotes = []
    monkeypatch.setattr(requote_mod, "_default_quote_fn", lambda t: quotes.append(list(t)) or {})
    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(item.result.ticker == "AAA",
                                                                 None, price))
    monkeypatch.setattr(qualify, "_revoke", lambda item, ctx: None)
    short_run._build_alerts([_item("AAA"), _item("BBB")], False, {}, None)
    assert quotes == [["AAA", "BBB"]]
    assert [t for t, _ in lane] == ["AAA"] and lane[0][1] is not None


def test_build_alerts_flag_off_is_todays_loop(monkeypatch, lane):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", False)
    monkeypatch.setattr(requote_mod, "_default_quote_fn",
                        lambda t: pytest.fail("no re-quote with the flag off"))
    short_run._build_alerts([_item("AAA"), _item("BBB")], False, {}, None)
    assert [t for t, _ in lane] == ["AAA", "BBB"]


def test_log_trade_carries_the_requote(monkeypatch):
    seen = {}
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(short_run.scan_run, "_persist_plan_v2",
                        lambda plan, alerts, requote=None: seen.setdefault("persist", requote))
    monkeypatch.setattr(short_run.scan_run, "_trade_quote", lambda rq, t: {"kind": "trade", "t": t})
    monkeypatch.setattr(short_run.trade_log, "log_trade",
                        lambda **kw: seen.setdefault("quote", kw["quote"]) and "tid")
    from tests.planning.test_plan_engine_model import _plan
    from tests.scanning.test_short_lane_scan import scenario
    item = SimpleNamespace(result=SimpleNamespace(ticker="AAA", strategy="S/R Confluence",
                                                  horizon_key="4w", trend="bearish"),
                           plan=scenario("bearish"), plan_v2=_plan(ticker="AAA"),
                           conf=SimpleNamespace(level=3, label="Medium", score=60, breakdown={}),
                           level_map=None, combined_from=[])
    nums = {"entry": 100.0, "stop_loss": 102.0, "take_profit": 94.0, "target2": None}
    rq = object()
    short_run._log_trade(item, nums, "why", None, [], requote=rq)
    assert seen["persist"] is rq and seen["quote"] == {"kind": "trade", "t": "AAA"}


def test_the_lane_passes_its_qualify_context():
    src = inspect.getsource(short_run._sync_run_short_scan)
    assert "qualify_context=_qualify_context(require_confirmation, frames, lane)" in src
```

- [ ] **Step 2: Run to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_rebuild.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.scanning.short_run' has no attribute '_rescenario_for'`.

- [ ] **Step 3: Implement in `short_run.py`**

Add `from swingbot.core.planning import rebuild` and `from .requote import Requote` to the imports, the four helpers (Interfaces) before `_build_alerts`, and the parameter and argument changes to `_build_alerts`, `_alert_for`, `_log_trade` and `_sync_run_short_scan`. `_build_alerts`'s docstring line: "v171: every postable item is first rebuilt from one batched re-quote (planning/rebuild.py); a drop revokes its confirmation and never posts."

- [ ] **Step 4: Run to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_rebuild.py`
Expected: PASS (7 tests).

- [ ] **Step 5: Regression and complexity**

Run each: `python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py`, `... file tests/scanning/test_short_funnel.py`, `... file tests/scanning/test_short_lane_split.py`, `... file tests/scanning/test_short_alert_parity.py`
Expected: PASS, same counts as before.
Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/short_run.py`
Expected: `_log_trade - C (13)` unchanged; nothing else at C or above.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/scanning/short_run.py tests/scanning/test_short_lane_rebuild.py
git -C $WT commit -m "feat(v171): SHORT lane pre-post rebuild through Requote (V171-21)"
git -C $R status --short
```

### Task V171-22: Alert surface: price kind, session label and "price not confirmed live" in the embed and simple alert; chart and embed from the rebuilt plan

**Model:** sonnet — presentation fields read from the stamped plan

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` (new helpers before `build_embed` :103; one line in `build_embed` after `sections["headline"].extend(_short_notice_fields(...))` :~144; one line in `build_simple_alert` :306-318 before `return embed`)
- Test: `tests/scanning/test_embed_quote_line.py` (create)

**Interfaces:**
- Consumes: the plan fields `quote_at`, `quote_kind`, `quote_session`, `price_confirmed` (V171-17), stamped by `rebuild.stamp_quote` (V171-18) on `item.plan_v2`, or on the legacy `item.plan` scenario when there is no v2 plan; `TradePlanV2.issued_at` (exists, set by `attach_plan_v2` at rebuild time).
- Produces:
  - `alert_embeds.QUOTE_FIELD = "Quote"`.
  - `alert_embeds.quote_line(plan) -> str | None`: `None` when `getattr(plan, "quote_kind", None)` is None (pre-v171 plans, rebuild off). Unconfirmed (`price_confirmed` falsy or kind `"scan"`): `"Price not confirmed live (scan price)"`. Confirmed: `"Price: <kind words>"` plus `", <n> s"` when the print's age is known. Kind words: `trade` -> `live trade`, `mid` -> `bid/ask mid`, `yf-1m` -> `Yahoo 1-min bar`. Either form ends with `", <session>"` when the session is set and not `"regular"` (`pre-market`, `after-hours`, `closed`, spec D5 "the alert shows the session label beside the price kind"). The age is `issued_at - quote_at` in whole seconds (`f"{age:.0f} s"`, clamped at 0), shown only when both parse as ISO times; a legacy scenario has no `issued_at` and shows no age.
  - `alert_embeds._quote_target(item)`: `item.plan_v2` when not None, else `item.plan`.
  - `alert_embeds._quote_fields(item) -> list[tuple[str, str, bool]]`: `[(QUOTE_FIELD, line, False)]` or `[]`.
  - `build_embed` adds, unconditionally, `sections["plan"].extend(_quote_fields(item))`: the field goes through the shared section accumulator (alert-surface skill: never a raw `add_field` in `build_embed`), into the plan section beside the levels it priced. `build_simple_alert` appends the same field through `_add_quote_field(embed, item) -> None` (a loop over `_quote_fields`). Neither function gains a branch; `build_embed` stays E (33).

With the rebuild off, nothing is stamped, `quote_line` returns None and both embeds are byte-identical to today's.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_embed_quote_line.py`:

```python
"""v171 D5: the alert names the price it was built from; unchanged without a stamp."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.scanning import alert_embeds, snapshots
from swingbot.core.scanning.alert_embeds import build_embed, build_simple_alert, quote_line
from tests.scanning.test_embeds_v3 import PERF_STATS_EMPTY, make_item, make_plan_v2

T = "2026-10-15T15:00:00+00:00"


@pytest.fixture(autouse=True)
def _isolated_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "scan_snapshots.json"))


def _stamped(kind="trade", confirmed=True, session="regular", age=2, quote_at=T):
    plan = make_plan_v2()
    plan.issued_at = "2026-10-15T15:00:%02d+00:00" % age
    plan.quote_at, plan.quote_kind = (quote_at if confirmed else None), kind
    plan.quote_session, plan.price_confirmed = session, confirmed
    return plan


def test_no_stamp_no_line():
    assert quote_line(make_plan_v2()) is None
    assert quote_line(SimpleNamespace()) is None


@pytest.mark.parametrize("kwargs, text", [
    ({}, "Price: live trade, 2 s"),
    ({"kind": "mid", "age": 8, "session": "pre-market"}, "Price: bid/ask mid, 8 s, pre-market"),
    ({"kind": "yf-1m", "age": 20, "session": "after-hours"},
     "Price: Yahoo 1-min bar, 20 s, after-hours"),
    ({"kind": "scan", "confirmed": False}, "Price not confirmed live (scan price)"),
    ({"kind": "scan", "confirmed": False, "session": "pre-market"},   # Review Focus 5
     "Price not confirmed live (scan price), pre-market"),
])
def test_quote_line_copy(kwargs, text):
    assert quote_line(_stamped(**kwargs)) == text


def test_legacy_scenario_shows_the_kind_without_an_age():
    scenario = SimpleNamespace(quote_kind="trade", quote_at=T, quote_session="regular",
                               price_confirmed=True)
    assert quote_line(scenario) == "Price: live trade"


def _fields(embed):
    return [(f.name, f.value) for f in embed.fields]


def test_full_embed_adds_exactly_one_quote_field(monkeypatch, tmp_path):
    """Rendered before/after (alert-surface gate): the only difference is the field."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plain = build_embed(make_item(plan_v2=make_plan_v2()), "why", PERF_STATS_EMPTY, None, None)
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "second.json"))  # no diff field
    stamped = build_embed(make_item(plan_v2=_stamped(kind="mid", age=8, session="pre-market")),
                          "why", PERF_STATS_EMPTY, None, None)
    before, after = _fields(plain), _fields(stamped)
    added = [f for f in after if f not in before]
    assert added == [("Quote", "Price: bid/ask mid, 8 s, pre-market")]
    assert [f for f in after if f[0] != "Quote"] == before
    assert plain.description == stamped.description


def test_simple_alert_adds_the_same_line(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = make_item()
    item.plan.quote_kind, item.plan.quote_at = "scan", None
    item.plan.quote_session, item.plan.price_confirmed = "after-hours", False
    plain = _fields(build_simple_alert(make_item()))
    after = _fields(build_simple_alert(item))
    assert [f for f in after if f not in plain] == [
        ("Quote", "Price not confirmed live (scan price), after-hours")]


def test_unstamped_alerts_render_exactly_as_today(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    a = build_embed(make_item(plan_v2=make_plan_v2()), "why", PERF_STATS_EMPTY, None, None)
    assert "Quote" not in [f.name for f in a.fields]
    assert "Quote" not in [f.name for f in build_simple_alert(make_item()).fields]


def test_the_embed_reads_the_v2_plan_before_the_scenario():
    item = make_item(plan_v2=_stamped())
    item.plan.quote_kind, item.plan.price_confirmed = "scan", False
    assert alert_embeds._quote_fields(item) == [("Quote", "Price: live trade, 2 s", False)]
```

`make_legacy_plan()` is a `SimpleNamespace` (tests/scanning/test_embeds_v3.py:34), so it takes the stamp attributes the way `stamp_quote` sets them on a real `Scenario` in production.

- [ ] **Step 2: Run to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embed_quote_line.py`
Expected: FAIL with `ImportError: cannot import name 'quote_line' from 'swingbot.core.scanning.alert_embeds'`.

- [ ] **Step 3: Implement in `alert_embeds.py`**

Add `QUOTE_FIELD`, `_KIND_WORDS = {"trade": "live trade", "mid": "bid/ask mid", "yf-1m": "Yahoo 1-min bar"}`, `_print_age_s(plan) -> float | None` (both ISO strings parsed with `datetime.fromisoformat` under `try/except (TypeError, ValueError)` -> None; `max(0.0, seconds)`), `quote_line`, `_quote_target`, `_quote_fields` and `_add_quote_field` before `build_embed`, then the two one-line calls. Docstring of `quote_line`: "v171 D5: which price this plan was built from, its age and session; None for an unstamped plan, so pre-v171 rendering is unchanged."

- [ ] **Step 4: Run to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embed_quote_line.py`
Expected: PASS (11 tests).

- [ ] **Step 5: Regression, complexity and the rendered gate**

Run each: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`, `... file tests/scanning/test_simple_alerts.py`, `... file tests/scanning/test_short_alert_parity.py`, `... file tests/scanning/test_embed_plan_link.py`, `... file tests/scanning/test_scan_rebuild_wiring.py`
Expected: PASS, same counts as before.
Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/alert_embeds.py`
Expected: `build_embed - E (33)` unchanged; nothing new at C or above.
The rendered before/after diff the alert-surface skill requires is `test_full_embed_adds_exactly_one_quote_field` and `test_simple_alert_adds_the_same_line`: both render the real embed with and without a stamp and assert that the only difference is the one `Quote` field. The end-to-end proof that the chart, embed, plan and trade come from the rebuilt plan is `test_main_scan_posts_only_the_rebuilt_plan` (V171-20) and `test_log_trade_carries_the_requote` (V171-21).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/scanning/alert_embeds.py tests/scanning/test_embed_quote_line.py
git -C $WT commit -m "feat(v171): alert quote line, session label and price-not-confirmed flag (V171-22)"
git -C $R status --short
```
