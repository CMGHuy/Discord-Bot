"""v204 admin page snapshots: what the refresher stores in `admin_snapshots`.

Each builder returns a `SnapshotResult`: the page document, the inputs it was
computed from, and whether those inputs are stale. The inputs contract
(`build_inputs`) records the quotes, FX rates and daily bar files a document
used, what was missing, the trades it covered, the staleness thresholds in
force and the code version, so a stored page can always be audited.

"Last completed session": daily bars are current when they reach the date of
the latest NYSE close, except that from that close until 20:00 ET the scan
has not had its chance to update the daily file yet, so the previous
session's date still counts as current (`expected_bar_date`). Spot metals
never make a snapshot stale; a symbol without bars is counted as missing.

`analytics_snapshot.json` stays as it is, for Discord.

The module stays light to import: pandas, the DB, `risk_payload`,
`portfolio_state` and `fx` are imported inside the builders.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from swingbot import config
from swingbot.core.market import session
from swingbot.core.marketdata import daily_readonly, spot_metals


@dataclass(frozen=True)
class SnapshotResult:
    doc: dict
    inputs: dict
    stale_inputs: bool


RISK_MIN_ROWS = 21     # risk_metrics._MIN_BARS returns need _MIN_BARS + 1 closes
_SCAN_GRACE_HOUR_ET = 20

_THRESHOLD_FIELDS = (
    ("stale_snapshot_regular_s", "ADMIN_STALE_SNAPSHOT_REGULAR_S"),
    ("stale_snapshot_extended_s", "ADMIN_STALE_SNAPSHOT_EXTENDED_S"),
    ("stale_price_regular_s", "ADMIN_STALE_PRICE_REGULAR_S"),
    ("stale_price_extended_s", "ADMIN_STALE_PRICE_EXTENDED_S"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _code_version():
    from swingbot.core.infra.jsonio import read_json
    return read_json(os.path.join(config._PROJECT_ROOT, "VERSION.json"), {}).get("bot")


def _oldest_iso(values):
    """The earliest ISO timestamp, compared as datetimes, returned as given; else None."""
    stamps = [v for v in values if v]
    if not stamps:
        return None
    return min(stamps, key=datetime.fromisoformat)


def _bars_block(bars) -> dict:
    if bars is None:
        return {"per_symbol": {}, "oldest": None, "newest": None}
    per_symbol = {sym: bars.fingerprints[sym]["last_bar"] for sym in bars.frames}
    dates = list(per_symbol.values())
    return {"per_symbol": per_symbol,
            "oldest": min(dates) if dates else None,
            "newest": max(dates) if dates else None}


def _thresholds() -> dict:
    return {key: float(getattr(config, field)) for key, field in _THRESHOLD_FIELDS}


def build_inputs(*, computed_at: datetime, quotes: dict | None = None, fx: dict | None = None,
                 bars=None, missing_quotes=(), missing_fx=(), ledger=None, trade_ids=()) -> dict:
    """The inputs a snapshot document was computed from (the v204 inputs shape)."""
    quotes = dict(quotes or {})
    fx = dict(fx or {})
    fx_dates = [v.get("as_of") for v in fx.values() if v.get("as_of")]
    return {
        "computed_at": computed_at.isoformat(),
        "oldest_quote_as_of": _oldest_iso(v.get("as_of") for v in quotes.values()),
        "quotes": quotes,
        "fx": fx,
        "oldest_fx_as_of": min(fx_dates) if fx_dates else None,
        "bars_as_of": _bars_block(bars),
        "bar_files": dict(bars.fingerprints) if bars is not None else {},
        "missing": {"quotes": sorted(set(missing_quotes)), "fx": sorted(set(missing_fx)),
                    "bars": dict(bars.missing) if bars is not None else {}},
        "ledger": ledger,
        "trade_ids": list(trade_ids),
        "thresholds": _thresholds(),
        "code_version": _code_version(),
    }


def expected_bar_date(now: datetime | None = None) -> date:
    """The date of the last session whose daily bar the scan has had its chance to write."""
    now = _now() if now is None else now
    close = session.last_regular_close(now)
    now_et = session.now_et(now)    # one reading of a naive `now` (ET), as last_regular_close
    close_et = close.astimezone(session.US_MARKET_TZ)
    if now_et.date() == close_et.date() and now_et.hour < _SCAN_GRACE_HOUR_ET:
        previous = session.last_regular_close(close - timedelta(seconds=1))
        return previous.astimezone(session.US_MARKET_TZ).date()
    return close_et.date()


def stale_inputs_for(per_symbol: dict, now: datetime | None = None) -> bool:
    """True when a non-spot-metal symbol's last bar predates the last completed session."""
    dates = [date.fromisoformat(d) for sym, d in per_symbol.items()
             if not spot_metals.is_spot_metal(sym)]
    if not dates:
        return False
    return min(dates) < expected_bar_date(now)


def _pair_as_of(pair: str):
    seen = daily_readonly.read_cached_daily([pair])
    return seen.fingerprints.get(pair, {}).get("last_bar")


def _fx_inputs(tickers, *, on: date) -> tuple[dict, list[str]]:
    """Each non-account quote currency's rate and pair-file date; never fetches."""
    from swingbot.core.marketdata import fx
    account = fx._major(fx.account_currency_code())[0]
    fx_map: dict = {}
    missing: list[str] = []
    for t in dict.fromkeys(str(t).upper().strip() for t in tickers if t):
        code = fx.quote_currency_code(t, fetch=False)
        if not code:
            missing.append(t)
            continue
        src = fx._major(code)[0]
        if src == account:
            continue
        rate = fx.fx_rate(src, account, on, refresh=False)    # major unit: GBp and GBP share "GBP"
        fx_map[src] = {"rate": rate, "as_of": _pair_as_of(f"{src}{account}=X")}
        if rate is None:
            missing.append(t)
    return fx_map, missing


def build_risk() -> SnapshotResult:
    """The risk page snapshot from read-only bars; every error propagates."""
    from swingbot.core.analytics import risk_payload
    from swingbot.core.edge import portfolio_state
    now = _now()
    reader = daily_readonly.RecordingReader(min_rows=RISK_MIN_ROWS)
    state = portfolio_state.collect_portfolio_state(bars_reader=reader)
    result = risk_payload.metrics_and_correlation(reader, strict=True)
    doc = risk_payload.market_body(state, result)
    open_trades = state.get("open_trades") or []
    fx_map, missing_fx = _fx_inputs([t.get("ticker") for t in open_trades], on=now.date())
    inputs = build_inputs(computed_at=now, fx=fx_map, bars=reader.seen, missing_fx=missing_fx,
                          trade_ids=[t.get("id") for t in open_trades])
    return SnapshotResult(doc=doc, inputs=inputs,
                          stale_inputs=stale_inputs_for(inputs["bars_as_of"]["per_symbol"], now))
