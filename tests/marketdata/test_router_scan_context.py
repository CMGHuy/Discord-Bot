"""v111 §2: the Alpaca call runs on the router's pool in the caller's scan context."""
from swingbot.core.infra.logsetup import scan_context, scan_id_var
from swingbot.core.marketdata.providers import router
from tests.marketdata.test_provider_router import FakeProvider, _use, enabled  # noqa: F401


class _ContextProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.seen = []

    def daily_bars(self, tickers, period):
        self.seen.append(scan_id_var.get())
        return {}


def test_alpaca_call_runs_in_the_callers_scan_context(enabled, monkeypatch):
    prov = _ContextProvider()
    _use(monkeypatch, prov)
    with scan_context("s-1200ab"):
        router.daily_bars(["AAPL"], "2y", lambda tickers, period: {})
    assert prov.seen == ["s-1200ab"]
