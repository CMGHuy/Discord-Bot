from datetime import datetime, timezone
from types import SimpleNamespace
import pandas as pd
import pytest
from swingbot.core.marketdata.providers import alpaca_provider as ap

def _barset(symbols):
    """The bars client's raw_data=True shape: {symbol: [bar dict, ...]}."""
    return {s: [{"t": t, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100, "n": 5, "vw": 1.4}
                for t in ("2026-09-24T04:00:00Z", "2026-09-25T04:00:00Z")]
            for s in symbols}

class FakeClient:
    def __init__(self, bars=None, snaps=None, exc=None):
        self.bars, self.snaps, self.exc, self.requests = bars, snaps, exc, []
    def get_stock_bars(self, req):
        self.requests.append(req)
        if self.exc: raise self.exc
        return self.bars
    def get_stock_snapshot(self, req):
        self.requests.append(req)
        if self.exc: raise self.exc
        return self.snaps

NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)   # 11:00 ET, in session

def _prov(client):
    return ap.AlpacaProvider("k", "s", "iex", client=client, now=lambda: NOW)

def test_daily_bars_uses_sip_all_adjustment_and_delayed_end():
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).daily_bars(["AAPL"], "2y")
    req = c.requests[0]
    assert str(req.feed.value) == "sip" and str(req.adjustment.value) == "all"
    # alpaca-py's request model converts datetimes to UTC and drops tzinfo
    assert req.end <= (NOW - pd.Timedelta(minutes=15)).replace(tzinfo=None)
    assert list(out["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]

def test_daily_bars_rekeys_class_shares():
    out = _prov(FakeClient(bars=_barset(["BRK.B"]))).daily_bars(["BRK-B"], "1y")
    assert set(out) == {"BRK-B"}

def test_symbol_absent_from_response_is_absent_from_result():
    out = _prov(FakeClient(bars=_barset(["AAPL"]))).daily_bars(["AAPL", "ZZZZ"], "1y")
    assert set(out) == {"AAPL"}

def _snap(price, ts):
    return SimpleNamespace(latest_trade=SimpleNamespace(price=price, timestamp=ts))

def test_latest_prices_fresh_trade():
    c = FakeClient(snaps={"AAPL": _snap(190.0, NOW - pd.Timedelta(seconds=30))})
    assert _prov(c).latest_prices(["AAPL"], 300) == {"AAPL": 190.0}
    assert str(c.requests[0].feed.value) == "iex"

def test_stale_iex_trade_is_a_miss_in_session():
    c = FakeClient(snaps={"AAPL": _snap(190.0, NOW - pd.Timedelta(minutes=20))})
    assert _prov(c).latest_prices(["AAPL"], 300) == {}

def test_old_trade_ok_outside_session():
    sat = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)
    c = FakeClient(snaps={"AAPL": _snap(190.0, sat - pd.Timedelta(hours=40))})
    p = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: sat)
    assert p.latest_prices(["AAPL"], 300) == {"AAPL": 190.0}

def test_auth_error_maps_to_alpaca_auth_error():
    err = Exception("forbidden"); err.status_code = 403
    with pytest.raises(ap.AlpacaAuthError):
        _prov(FakeClient(exc=err)).daily_bars(["AAPL"], "1y")

def test_other_error_maps_to_miss():
    with pytest.raises(ap.AlpacaMiss):
        _prov(FakeClient(exc=RuntimeError("500"))).daily_bars(["AAPL"], "1y")

def test_intraday_only_1h_supported():
    assert _prov(FakeClient()).intraday_bars("AAPL", "1d") is None


def test_symbols_per_request_fits_one_page():
    now = datetime(2026, 9, 25, tzinfo=timezone.utc)
    assert ap.symbols_per_request("2y", now) == 19
    for period in ("10y", "nonsense"):
        n = ap.symbols_per_request(period, now)
        rows = (now - ap._start_for(period, now)).days * 252 // 365 + 10
        assert n >= 1 and (n * rows <= ap.ROWS_PER_PAGE or n == 1)


def test_daily_bars_frame_from_raw_dicts():
    out = _prov(FakeClient(bars=_barset(["AAPL"]))).daily_bars(["AAPL"], "2y")
    df = out["AAPL"]
    assert list(df.index) == [pd.Timestamp("2026-09-24"), pd.Timestamp("2026-09-25")]
    assert df.index.name == "Date" and df.index.tz is None
    assert df.iloc[-1].to_dict() == {"Open": 1.0, "High": 2.0, "Low": 0.5,
                                     "Close": 1.5, "Volume": 100.0}
    assert (df.dtypes == "float64").all()


def test_empty_bar_list_is_absent_from_result():
    bars = {**_barset(["AAPL"]), "MSFT": []}
    assert set(_prov(FakeClient(bars=bars)).daily_bars(["AAPL", "MSFT"], "1y")) == {"AAPL"}


def test_intraday_1h_from_raw_30min_dicts():
    bars = {"AAPL": [{"t": t, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10}
                     for t in ("2026-09-24T13:30:00Z", "2026-09-24T14:00:00Z")]}
    df = _prov(FakeClient(bars=bars)).intraday_bars("AAPL", "1h")
    assert len(df) == 1 and df["Volume"].iloc[0] == 20.0
    assert str(df.index[0]) == "2026-09-24 09:30:00-04:00"


def test_default_clients_raw_for_bars_models_for_snapshots(monkeypatch):
    made = []
    monkeypatch.setattr(ap, "StockHistoricalDataClient",
                        lambda *a, **k: made.append(k) or FakeClient())
    ap.AlpacaProvider("k", "s", "iex")
    assert sorted(bool(k.get("raw_data")) for k in made) == [False, True]
