import pytest
from swingbot.core.marketdata.asset_class import classify, is_rs_eligible


@pytest.mark.parametrize("symbol,expected", [
    ("AAPL", "equity"), ("NVDA", "equity"),
    ("EURUSD=X", "fx"), ("JPY=X", "fx"),
    ("GC=F", "future"), ("CL=F", "future"),
    ("^GSPC", "index"), ("^VIX", "index"),
])
def test_classify_by_resolved_symbol_shape(symbol, expected):
    assert classify(symbol) == expected


def test_etfs_classify_as_etf_via_the_universe_table():
    assert classify("SPY") == "etf"
    assert classify("XLK") == "etf"


@pytest.mark.parametrize("symbol", ["EURUSD=X", "GC=F", "^GSPC"])
def test_non_equities_are_not_rs_eligible(symbol):
    """RS-vs-SPY is meaningless for FX, futures and indices. They are exempt
    from the gate -- they pass, and the exemption is logged as such."""
    assert is_rs_eligible(symbol) is False


@pytest.mark.parametrize("symbol", ["AAPL", "SPY"])
def test_equities_and_etfs_are_rs_eligible(symbol):
    assert is_rs_eligible(symbol) is True


def test_classification_uses_the_resolved_symbol_not_the_alias():
    """XAUUSD resolves to GC=F. The gate must classify what was actually
    fetched, not the alias the user typed.

    ticker_utils exposes candidate_symbols(ticker) -> list[str] (there is no
    resolve_ticker); candidate_symbols("XAUUSD")[0] is "XAUUSD" (not valid in
    Yahoo), so [1] is "GC=F" (the actual resolved symbol).
    """
    from swingbot.core.marketdata.ticker_utils import candidate_symbols
    assert classify(candidate_symbols("XAUUSD")[1]) == "future"


@pytest.mark.parametrize("symbol,expected", [
    ("BTC-USD", "crypto"), ("ETH-USD", "crypto"),
])
def test_resolved_crypto_forms_classify_as_crypto(symbol, expected):
    assert classify(symbol) == expected


def test_crypto_is_not_rs_eligible():
    assert is_rs_eligible("BTC-USD") is False


@pytest.mark.parametrize("symbol,expected", [
    # Final-review Finding 1: the real gate call site (engine.py) passes
    # the RAW watchlist string into rs_verdict() -> classify(), never a
    # pre-resolved symbol. classify() must handle these unresolved forms
    # itself, not merely a hand-resolved symbol handed to it by a test.
    ("XAUUSD", "future"),
    ("SPX", "index"),
    ("BTC", "crypto"),
    ("BTCUSD", "crypto"),
])
def test_classify_handles_unresolved_watchlist_aliases(symbol, expected):
    assert classify(symbol) == expected


@pytest.mark.parametrize("symbol", ["XAUUSD", "SPX", "BTC", "BTCUSD", "BTC-USD"])
def test_unresolved_and_resolved_non_equity_forms_are_not_rs_eligible(symbol):
    """The gate must never fire on these -- an unresolved alias reaching
    is_rs_eligible() unhandled used to read as 'equity' and so was never
    exempted, the exact bug this fix closes."""
    assert is_rs_eligible(symbol) is False


@pytest.mark.parametrize("symbol,expected", [
    # classify() vs data.py fetch-semantics finding: GOLD and OIL are
    # ALIASES keys (ticker_utils.py) that are ALSO real, fetchable Yahoo
    # tickers. data.py's get_daily_data() tries the bare symbol first and
    # only falls back to the ALIASES mapping if that fetch fails, so these
    # must classify as what actually gets fetched (equity/etf), not as
    # what their alias implies (future) -- the walk-all-candidates default
    # would otherwise wrongly exempt them from the RS gate.
    ("GOLD", "equity"),
    ("OIL", "etf"),
])
def test_aliases_keys_that_are_also_real_tickers_classify_by_the_bare_symbol(symbol, expected):
    assert classify(symbol) == expected


@pytest.mark.parametrize("symbol", ["GOLD", "OIL"])
def test_aliases_keys_that_are_also_real_tickers_are_rs_eligible(symbol):
    """The opposite-direction bug from the unresolved-alias fix above:
    these must NOT be exempted, because the data actually fetched for them
    is ordinary equity/ETF data, not the futures/ETN the alias implies."""
    assert is_rs_eligible(symbol) is True
