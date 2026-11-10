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


# --- v162: history_bars, the history store's one fetch path -------------------

H_START = datetime(2016, 1, 1, tzinfo=timezone.utc)
H_END = datetime(2017, 1, 1, tzinfo=timezone.utc)


def test_history_bars_requests_one_symbol_sip_all_over_the_given_window():
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).history_bars("AAPL", "15min", H_START, H_END)
    req = c.requests[0]
    assert req.symbol_or_symbols == ["AAPL"]
    assert req.timeframe.value == "15Min"
    assert str(req.feed.value) == "sip" and str(req.adjustment.value) == "all"
    # alpaca-py's request model converts datetimes to UTC and drops tzinfo
    assert req.start == datetime(2016, 1, 1) and req.end == datetime(2017, 1, 1)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert str(out.index.tz) == "UTC"


@pytest.mark.parametrize("timeframe,wire", [("15min", "15Min"), ("30min", "30Min"), ("1d", "1Day")])
def test_history_bars_timeframes(timeframe, wire):
    c = FakeClient(bars=_barset(["AAPL"]))
    _prov(c).history_bars("AAPL", timeframe, H_START, H_END)
    assert c.requests[0].timeframe.value == wire


def test_history_bars_unknown_timeframe_raises_before_any_request():
    c = FakeClient(bars=_barset(["AAPL"]))
    with pytest.raises(ValueError, match="1Hour"):
        _prov(c).history_bars("AAPL", "1Hour", H_START, H_END)
    assert c.requests == []


def test_history_bars_clamps_end_to_the_sip_delay():
    c = FakeClient(bars=_barset(["AAPL"]))
    _prov(c).history_bars("AAPL", "1d", H_START, NOW + pd.Timedelta(days=30))
    assert c.requests[0].end == (NOW - ap.SIP_DELAY).replace(tzinfo=None)


def test_history_bars_window_entirely_inside_the_delay_is_none_without_a_request():
    c = FakeClient(bars=_barset(["AAPL"]))
    start = NOW - pd.Timedelta(minutes=5)
    assert _prov(c).history_bars("AAPL", "15min", start, NOW) is None
    assert c.requests == []


@pytest.mark.parametrize("bars", [{}, {"AAPL": []}, None])
def test_history_bars_no_bars_is_none(bars):
    assert _prov(FakeClient(bars=bars)).history_bars("AAPL", "1d", H_START, H_END) is None


def test_history_bars_class_share_uses_the_dotted_symbol():
    c = FakeClient(bars=_barset(["BRK.B"]))
    out = _prov(c).history_bars("BRK-B", "1d", H_START, H_END)
    assert c.requests[0].symbol_or_symbols == ["BRK.B"]
    assert out is not None and len(out) == 2


def test_history_bars_auth_error_propagates():
    err = Exception("forbidden"); err.status_code = 401
    with pytest.raises(ap.AlpacaAuthError):
        _prov(FakeClient(exc=err)).history_bars("AAPL", "1d", H_START, H_END)


def test_history_bars_rate_limit_is_a_miss_with_the_status_on_the_cause():
    err = Exception("too many requests"); err.status_code = 429
    with pytest.raises(ap.AlpacaMiss) as info:
        _prov(FakeClient(exc=err)).history_bars("AAPL", "1d", H_START, H_END)
    assert not isinstance(info.value, ap.AlpacaAuthError)
    assert info.value.__cause__.status_code == 429


from swingbot.core.marketdata.shared.kinds import QuoteDetail


def _qsnap(price, trade_ts, bid=None, ask=None, quote_ts=None):
    trade = None if price is None else SimpleNamespace(price=price, timestamp=trade_ts)
    quote = (None if bid is None and ask is None
             else SimpleNamespace(bid_price=bid, ask_price=ask, timestamp=quote_ts))
    return SimpleNamespace(latest_trade=trade, latest_quote=quote)


def test_latest_quotes_carries_trade_and_quote_timestamps():
    t_trade = NOW - pd.Timedelta(seconds=3)
    t_quote = NOW - pd.Timedelta(seconds=1)
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, t_trade, 189.9, 190.1, t_quote)})
    out = _prov(c).latest_quotes(["AAPL"], 300)
    assert out == {"AAPL": QuoteDetail(symbol="AAPL", price=190.0, trade_at=t_trade,
                                       bid=189.9, ask=190.1, quote_at=t_quote,
                                       source="alpaca-iex")}
    assert str(c.requests[0].feed.value) == "iex"


def test_latest_quotes_stale_trade_in_session_keeps_the_quote():
    t_quote = NOW - pd.Timedelta(seconds=2)
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, NOW - pd.Timedelta(minutes=20),
                                         189.0, 191.0, t_quote)})
    q = _prov(c).latest_quotes(["AAPL"], 300)["AAPL"]
    assert q.price is None and q.trade_at is None
    assert (q.bid, q.ask, q.quote_at) == (189.0, 191.0, t_quote)
    assert q.mid() == 190.0


def test_latest_quotes_symbol_with_no_price_and_one_sided_quote_is_absent():
    c = FakeClient(snaps={"AAPL": _qsnap(None, None, 0.0, 191.0, NOW)})
    assert _prov(c).latest_quotes(["AAPL"], 300) == {}


def test_latest_quotes_rekeys_class_shares():
    c = FakeClient(snaps={"BRK.B": _qsnap(410.0, NOW - pd.Timedelta(seconds=5))})
    assert set(_prov(c).latest_quotes(["BRK-B"], 300)) == {"BRK-B"}


def test_latest_quotes_old_trade_outside_session_is_kept_with_its_timestamp():
    sat = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)
    friday_close = sat - pd.Timedelta(hours=23)
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, friday_close)})
    prov = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: sat)
    q = prov.latest_quotes(["AAPL"], 300)["AAPL"]
    assert q.price == 190.0 and q.trade_at == friday_close


def _at(now, trade_age_h):
    c = FakeClient(snaps={"AAPL": _qsnap(190.0, now - pd.Timedelta(hours=trade_age_h),
                                         189.9, 190.1, now)})
    prov = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: now)
    return prov.latest_quotes(["AAPL"], 300)["AAPL"]


def test_latest_quotes_premarket_friday_print_is_a_miss_so_yfinance_can_answer():
    mon_premarket = datetime(2026, 11, 9, 13, 46, tzinfo=timezone.utc)   # 08:46 ET
    q = _at(mon_premarket, 64)
    assert q.price is None and q.trade_at is None        # router falls back to yfinance
    assert q.quote_at == mon_premarket


def test_latest_quotes_after_hours_old_print_is_a_miss():
    mon_after = datetime(2026, 11, 9, 22, 30, tzinfo=timezone.utc)       # 17:30 ET
    assert _at(mon_after, 3).price is None


def test_latest_quotes_premarket_fresh_print_is_kept():
    mon_premarket = datetime(2026, 11, 9, 13, 46, tzinfo=timezone.utc)
    assert _at(mon_premarket, 0.01).price == 190.0


def test_latest_quotes_overnight_old_print_is_kept():
    mon_night = datetime(2026, 11, 9, 7, 0, tzinfo=timezone.utc)         # 02:00 ET, no tape
    assert _at(mon_night, 10).price == 190.0


def test_daily_bars_between_sends_the_range_on_sip_all():
    from datetime import date
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).daily_bars_between(["AAPL"], date(2026, 9, 20), date(2026, 9, 25))
    req = c.requests[0]
    assert str(req.feed.value) == "sip" and str(req.adjustment.value) == "all"
    assert req.start == datetime(2026, 9, 20)
    assert req.end <= (NOW - pd.Timedelta(minutes=15)).replace(tzinfo=None)
    assert list(out["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]


# --- v223: old print vs miss vs hit ------------------------------------------------
# From 2026-11-01 ET is UTC-5. Tue 2026-11-10 is a full session; Thu 2026-11-26
# (Thanksgiving) a full holiday; Fri 2026-11-27 a 13:00 ET early close.

def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


_HIT, _OLD, _MISS = (190.0, False), (None, True), (None, False)


@pytest.mark.parametrize("now, expected", [
    (_utc(2026, 11, 10, 8, 59), _HIT),     # 03:59 ET, tape closed
    (_utc(2026, 11, 10, 9, 0), _OLD),      # 04:00 ET, pre-market begins
    (_utc(2026, 11, 10, 14, 29), _OLD),    # 09:29 ET
    (_utc(2026, 11, 10, 14, 30), _MISS),   # 09:30 ET, regular session
    (_utc(2026, 11, 10, 20, 59), _MISS),   # 15:59 ET
    (_utc(2026, 11, 10, 21, 0), _OLD),     # 16:00 ET, after-hours
    (_utc(2026, 11, 11, 0, 59), _OLD),     # 19:59 ET
    (_utc(2026, 11, 11, 1, 0), _HIT),      # 20:00 ET, tape closed
    (_utc(2026, 11, 27, 18, 30), _OLD),    # 13:30 ET on the early-close day
    (_utc(2026, 11, 26, 17, 0), _HIT),     # 12:00 ET on a full holiday
])
def test_price_verdict_for_an_hour_old_trade(now, expected):
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(), now=lambda: now)
    snap = _snap(190.0, now - pd.Timedelta(hours=1))
    assert prov._price_verdict(snap, now, 300) == expected


@pytest.mark.parametrize("now", [_utc(2026, 11, 10, 9, 30), _utc(2026, 11, 10, 15, 0),
                                 _utc(2026, 11, 10, 22, 0), _utc(2026, 11, 14, 15, 0)])
def test_price_verdict_fresh_trade_is_a_hit_at_any_time(now):
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(), now=lambda: now)
    assert prov._price_verdict(_snap(190.0, now - pd.Timedelta(seconds=30)), now, 300) == _HIT


@pytest.mark.parametrize("snap", [
    _qsnap(None, None, 189.9, 190.1, _utc(2026, 11, 10, 13, 0)),                       # no trade
    _qsnap(0.0, _utc(2026, 11, 10, 12, 0), 189.9, 190.1, _utc(2026, 11, 10, 13, 0)),   # zero price
    SimpleNamespace(latest_quote=None),                                                # no trade attr
])
def test_price_verdict_without_a_positive_trade_is_a_miss(snap):
    now = _utc(2026, 11, 10, 13, 0)                                    # 08:00 ET, pre-market
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(), now=lambda: now)
    assert prov._price_verdict(snap, now, 300) == _MISS


_PRE = _utc(2026, 11, 10, 13, 0)                                       # 08:00 ET


def _pre_prov(snaps):
    return ap.AlpacaProvider("k", "s", "iex", client=FakeClient(snaps=snaps), now=lambda: _PRE)


def test_no_snapshot_is_a_miss_not_an_old_print():
    assert _pre_prov({}).latest_price_answers(["AAPL"], 300) == ({}, frozenset())
    assert _pre_prov({}).latest_quote_answers(["AAPL"], 300) == ({}, frozenset())


def test_latest_price_answers_names_the_old_prints():
    snaps = {"AAPL": _snap(190.0, _PRE - pd.Timedelta(seconds=30)),
             "MSFT": _snap(410.0, _PRE - pd.Timedelta(hours=12)),
             "NVDA": _snap(0.0, _PRE - pd.Timedelta(seconds=30))}
    prices, old = _pre_prov(snaps).latest_price_answers(["AAPL", "MSFT", "NVDA"], 300)
    assert prices == {"AAPL": 190.0}
    assert old == frozenset({"MSFT"})


def test_latest_quote_answers_old_print_keeps_its_quote():
    snaps = {"AAPL": _qsnap(190.0, _PRE - pd.Timedelta(hours=12), 189.9, 190.1, _PRE)}
    details, old = _pre_prov(snaps).latest_quote_answers(["AAPL"], 300)
    q = details["AAPL"]
    assert q.price is None and q.trade_at is None
    assert (q.bid, q.ask, q.quote_at) == (189.9, 190.1, _PRE)
    assert old == frozenset({"AAPL"})


def test_latest_quote_answers_old_print_without_a_two_sided_quote_is_still_named():
    snaps = {"AAPL": _qsnap(190.0, _PRE - pd.Timedelta(hours=12))}
    assert _pre_prov(snaps).latest_quote_answers(["AAPL"], 300) == ({}, frozenset({"AAPL"}))


def test_latest_quote_answers_rekeys_class_shares_in_both_elements():
    snaps = {"BRK.B": _qsnap(410.0, _PRE - pd.Timedelta(hours=12))}
    assert _pre_prov(snaps).latest_quote_answers(["BRK-B"], 300) == ({}, frozenset({"BRK-B"}))


def test_old_trade_in_the_regular_session_is_never_an_old_print():
    """A frozen IEX feed in regular hours stays an Alpaca miss and still alerts."""
    now = _utc(2026, 11, 10, 16, 0)                                    # 11:00 ET
    snaps = {"AAPL": _qsnap(190.0, now - pd.Timedelta(minutes=20), 189.9, 190.1, now)}
    prov = ap.AlpacaProvider("k", "s", "iex", client=FakeClient(snaps=snaps), now=lambda: now)
    details, old = prov.latest_quote_answers(["AAPL"], 300)
    assert details["AAPL"].price is None and old == frozenset()


def test_the_wrappers_return_exactly_element_zero():
    snaps = {"AAPL": _qsnap(190.0, _PRE - pd.Timedelta(seconds=30), 189.9, 190.1, _PRE),
             "MSFT": _qsnap(410.0, _PRE - pd.Timedelta(hours=12), 409.0, 411.0, _PRE),
             "NVDA": _qsnap(0.0, _PRE, None, None, None)}
    tickers = ["AAPL", "MSFT", "NVDA"]
    assert _pre_prov(snaps).latest_prices(tickers, 300) == \
        _pre_prov(snaps).latest_price_answers(tickers, 300)[0]
    assert _pre_prov(snaps).latest_quotes(tickers, 300) == \
        _pre_prov(snaps).latest_quote_answers(tickers, 300)[0]


def test_answers_make_one_snapshot_call():
    c = FakeClient(snaps={"AAPL": _snap(190.0, _PRE - pd.Timedelta(hours=12))})
    prov = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: _PRE)
    prov.latest_quote_answers(["AAPL", "MSFT"], 300)
    assert len(c.requests) == 1 and str(c.requests[0].feed.value) == "iex"
