"""v205 V205-4: the fixed book the admin goldens are recorded from -- stores, quote
currencies, FX closes, prices, bars and the wall clock. Goldens are never regenerated."""
from __future__ import annotations

import copy
import datetime as _dt
import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import admin_endpoint_timing  # noqa: E402

FROZEN_NOW = _dt.datetime(2026, 11, 4, 12, 0, tzinfo=_dt.timezone.utc)
MONTH = "2026-11"
DAY = "2026-11-03"
ENDPOINTS: dict[str, str] = admin_endpoint_timing.endpoints(MONTH, DAY)
GOLDEN_DIR = Path(__file__).with_name("golden")
MASK = "<masked>"

#: Modules whose module-level datetime/date/dt names the frozen clock replaces.
#: test_clock_modules_cover_every_clock_read fails when the call path reads the
#: clock from a module missing here. fx_convert reads Berlin today since V205-16.
CLOCK_MODULES: tuple[str, ...] = (
    "swingbot.admin.api_v1.calendar",
    "swingbot.admin.api_v1.dashboard",
    "swingbot.admin.api_v1.live",
    "swingbot.admin.api_v1.live_events",
    "swingbot.admin.api_v1.trades",
    "swingbot.admin.dashboard",
    "swingbot.core.analytics.admin_snapshots",   # v204: snapshot computed_at
    "swingbot.core.analytics.page_bodies",       # v204: calendar/analytics as_of
    "swingbot.core.analytics.rank",
    "swingbot.core.analytics.snapshots",
    "swingbot.core.market.session",
    "swingbot.core.marketdata.fx_convert",
    "swingbot.core.planning.account",
    "swingbot.core.tracking.performance",
)

#: Keys still nondeterministic under the frozen clock, key -> why. Masked anywhere.
VOLATILE_KEYS: dict[str, str] = {}

#: Keys a later plan ADDED to a frozen payload on purpose, endpoint -> pointer -> why.
#: The goldens stay frozen; `without_added` drops exactly these pointers from the
#: live payload before comparing, so every field the golden pins stays pinned.
ADDED_POINTERS: dict[str, dict[str, str]] = {
    "dashboard": {"/equity_30d/market_meta": "v204 sparkline snapshot meta; tests/admin_snapshots"},
    "dashboard_today": {"/equity_30d/market_meta": "v204 sparkline snapshot meta; tests/admin_snapshots"},
    "calendar_month": {
        "/market_meta": "v204 calendar snapshot meta; tests/admin_snapshots",
        "/month_day_of_week": "fa6290fd by-weekday table for the month on show; tests/admin/test_api_v1_calendar.py",
    },
}

ACCOUNT_CODE = "EUR"
QUOTES: dict[str, str] = {"AAPL": "USD", "SAP.DE": "EUR"}
PRICES: dict[str, float] = {"AAPL": 104.0, "SAP.DE": 212.0}
FX_CLOSES: dict[str, dict[str, float]] = {"USDEUR=X": {
    "2026-10-26": 0.8600, "2026-10-27": 0.8620, "2026-10-28": 0.0, "2026-10-29": 0.8650,
    "2026-10-30": 0.8640, "2026-11-02": 0.8680, "2026-11-03": 0.8700, "2026-11-04": 0.8720}}
#: fx_daily_rates rows for USD -> EUR, written by hand from FX_CLOSES (v205 V205-15):
#: Berlin day -> (rate, bar_date), the last positive close dated strictly before the day.
FX_DAILY_ROWS: dict[str, tuple[float, str]] = {
    "2026-10-27": (0.8600, "2026-10-26"),
    "2026-10-28": (0.8620, "2026-10-27"),
    "2026-10-29": (0.8620, "2026-10-27"),   # the 10-28 close is 0.0: skipped
    "2026-10-30": (0.8650, "2026-10-29"),
    "2026-10-31": (0.8640, "2026-10-30"),
    "2026-11-01": (0.8640, "2026-10-30"),
    "2026-11-02": (0.8640, "2026-10-30"),   # Monday: Friday's close
    "2026-11-03": (0.8680, "2026-11-02"),
    "2026-11-04": (0.8700, "2026-11-03"),   # FROZEN_NOW's Berlin day
}
BARS: dict[str, dict[str, float]] = {
    "AAPL": {"2026-10-28": 99.0, "2026-10-29": 101.0, "2026-10-30": 100.5,
             "2026-11-02": 102.0, "2026-11-03": 104.0},
    "SAP.DE": {"2026-10-28": 201.0, "2026-10-29": 203.0, "2026-10-30": 205.0,
               "2026-11-02": 208.0, "2026-11-03": 212.0}}
PLAN_ACTIVE = "11111111-1111-4111-8111-111111111111"
PLAN_PENDING = "22222222-2222-4222-8222-222222222222"


def frame(closes: dict[str, float]) -> pd.DataFrame:
    values = list(closes.values())
    return pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                         "Volume": [0] * len(values)}, index=pd.DatetimeIndex(list(closes)))


def fx_daily_rows(scale: float = 1.0) -> list[dict]:
    return [{"base": "USD", "account": ACCOUNT_CODE, "day": _dt.date.fromisoformat(day),
             "rate": rate * scale, "bar_date": _dt.date.fromisoformat(bar),
             "snapped_at": FROZEN_NOW, "source": "backfill"}
            for day, (rate, bar) in FX_DAILY_ROWS.items()]


def seed_fx_daily(scale: float = 1.0) -> None:
    """Replace fx_daily_rates with FX_DAILY_ROWS x scale and load the process memo.

    Loading it here models production's steady state (one table read per minute,
    not per request), so V205-5's statement budgets stay as they are."""
    import sqlalchemy as sa

    from swingbot.core.db import engine, schema
    from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo
    from swingbot.core.marketdata import fx_daily
    with engine.get_engine().begin() as conn:
        conn.execute(sa.delete(schema.fx_daily_rates))
        fx_daily_rate_repo().insert_if_absent(fx_daily_rows(scale), conn=conn)
    fx_daily.reset_memo()
    fx_daily.lookup("USD", ACCOUNT_CODE, FROZEN_NOW.date())


def fx_frames(scale: float = 1.0) -> dict[str, pd.DataFrame]:
    return {pair: frame({d: c * scale for d, c in closes.items()}) for pair, closes in FX_CLOSES.items()}


def bars() -> dict[str, pd.DataFrame]:
    return {ticker: frame(closes) for ticker, closes in BARS.items()}


def _plan(plan_id: str, ticker: str, status: str, entry: float) -> dict:
    return {"plan_id": plan_id, "ticker": ticker, "created_at": "2026-11-02T08:00:00+00:00",
            "source": "confluence", "strategy": "S/R Confluence", "horizon_key": "4w",
            "direction": "bullish", "entry_type": "stop_entry", "trigger_price": entry,
            "entry_price": entry, "expiry_bars": 5, "stop_loss": round(entry * 0.95, 2),
            "tp1": round(entry * 1.1, 2), "tp1_fraction": 0.5, "tp2": round(entry * 1.2, 2),
            "breakeven_trigger_fraction": 0.5, "trail_atr_mult": 1.5, "quality_score": 72,
            "quality_breakdown": [], "tier": "A", "badge": "VALIDATED", "badge_stats": {},
            "status": status, "status_history": [], "legs_realized": []}


def plans() -> list[dict]:
    return [_plan(PLAN_ACTIVE, "AAPL", "ACTIVE", 100.0), _plan(PLAN_PENDING, "SAP.DE", "PENDING", 215.0)]


def _trade(trade_id, ticker, *, status, entry, shares, closed_at=None, exit_price=None,
           pnl=None, plan_id=None, legs=()) -> dict:
    return {"id": trade_id, "plan_id": plan_id, "ticker": ticker, "strategy": "S/R Confluence",
            "horizon_key": "4w", "direction": "bullish", "confidence_level": 4,
            "confidence_label": "High", "confidence_score": 81.0, "entry": entry,
            "stop_loss": round(entry * 0.95, 2), "take_profit": round(entry * 1.2, 2),
            "target2": None, "risk_reward_ratio": 2.0, "badge": "VALIDATED", "quality_score": 72,
            "source": "confluence", "legs": list(legs), "opened_at": "2026-10-27T14:00:00+00:00",
            "status": status, "closed_at": closed_at, "exit_price": exit_price,
            "realized_pnl_amount": pnl, "shares": shares, "position_value": entry * shares,
            "target_sources": [], "stop_sources": [], "target2_sources": [], "confirmed_by": [],
            "explanation": None, "confidence_breakdown": None}


def trades() -> list[dict]:
    legs = [{"fraction": 0.5, "exit_price": 110.0, "closed_at": "2026-10-29T15:00:00+00:00", "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 104.0, "closed_at": "2026-11-02T15:00:00+00:00", "r": 0.8, "reason": "trail"}]
    return [
        _trade("golden-t1-sap-win", "SAP.DE", status="win", entry=200.0, shares=10,
               closed_at="2026-11-03T14:00:00+00:00", exit_price=212.0, pnl=120.0),
        _trade("golden-t2-usd-win", "AAPL", status="win", entry=100.0, shares=10,
               closed_at="2026-11-03T20:30:00+00:00", exit_price=105.0, pnl=50.0),
        _trade("golden-t3-usd-midnight", "AAPL", status="loss", entry=100.0, shares=10,
               closed_at="2026-11-02T23:30:00+00:00", exit_price=97.0, pnl=-30.0),
        _trade("golden-t4-usd-scaleout", "AAPL", status="win", entry=100.0, shares=10,
               closed_at="2026-11-02T15:00:00+00:00", exit_price=104.0, pnl=70.0, legs=legs),
        _trade("golden-t5-usd-open", "AAPL", status="open", entry=100.0, shares=10, plan_id=PLAN_ACTIVE),
        _trade("golden-t6-sap-open", "SAP.DE", status="open", entry=200.0, shares=5),
    ]


# --- the frozen clock ------------------------------------------------------

#: Modules that read the clock through a frozen class (probe_clock's evidence).
CALLERS: set[str] = set()


def _caller() -> str:
    return sys._getframe(2).f_globals.get("__name__", "?")


class _FrozenMeta(type):
    """isinstance/issubclass answer for the real class (a patched module still accepts real datetimes)."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls._real)


class FrozenDatetime(_dt.datetime, metaclass=_FrozenMeta):
    _real = _dt.datetime

    @classmethod
    def now(cls, tz=None):
        CALLERS.add(_caller())
        return FROZEN_NOW.astimezone(tz) if tz is not None else FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def utcnow(cls):
        CALLERS.add(_caller())
        return FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def today(cls):
        CALLERS.add(_caller())
        return FROZEN_NOW.replace(tzinfo=None)


class FrozenDate(_dt.date, metaclass=_FrozenMeta):
    _real = _dt.date

    @classmethod
    def today(cls):
        CALLERS.add(_caller())
        return FROZEN_NOW.date()


def freeze(monkeypatch, modules) -> None:
    """Replace every module-level alias of datetime.datetime, datetime.date and the
    datetime module itself in ``modules`` (``import datetime as dt`` included)."""
    proxy = types.ModuleType("datetime")
    proxy.__dict__.update(vars(_dt))
    proxy.datetime, proxy.date = FrozenDatetime, FrozenDate
    swaps = {id(_dt.datetime): FrozenDatetime, id(_dt.date): FrozenDate, id(_dt): proxy}
    for module in modules:
        for name, value in list(vars(module).items()):
            if id(value) in swaps:
                monkeypatch.setattr(module, name, swaps[id(value)])


# --- JSON pointers ---------------------------------------------------------

def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.json"


def resolve(payload, pointer: str):
    node = payload
    for part in pointer.split("/")[1:]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _set(payload, pointer: str, value) -> None:
    *parents, last = pointer.split("/")[1:]
    node = resolve(payload, "/" + "/".join(parents)) if parents else payload
    node[int(last) if isinstance(node, list) else last] = value


def without_added(name: str, payload):
    """A deep copy of ``payload`` minus ADDED_POINTERS[name]; a pointer already absent is skipped."""
    out = copy.deepcopy(payload)
    for pointer in ADDED_POINTERS.get(name, {}):
        *parents, last = pointer.split("/")[1:]
        try:
            node = resolve(out, "/" + "/".join(parents)) if parents else out
        except (KeyError, IndexError, TypeError):
            continue
        if isinstance(node, dict):
            node.pop(last, None)
    return out


def _mask_keys(node) -> None:
    if isinstance(node, dict):
        for key in node:
            if key in VOLATILE_KEYS:
                node[key] = MASK
            else:
                _mask_keys(node[key])
    elif isinstance(node, list):
        for item in node:
            _mask_keys(item)


def mask(payload, pointers=()):
    """A deep copy with VOLATILE_KEYS and the given money pointers replaced by MASK."""
    out = copy.deepcopy(payload)
    _mask_keys(out)
    for pointer in pointers:
        _set(out, pointer, MASK)
    return out


def diff_pointers(a, b, prefix: str = "") -> set[str]:
    """Pointers of the leaves where ``a`` and ``b`` differ (a whole list if its length does)."""
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return set().union(*(diff_pointers(a[k], b[k], f"{prefix}/{k}") for k in a))
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return set().union(*(diff_pointers(x, y, f"{prefix}/{i}") for i, (x, y) in enumerate(zip(a, b))))
    return set() if a == b else {prefix}
