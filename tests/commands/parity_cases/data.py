"""Reply-parity cases for swingbot/commands/data.py (v153 SP6).

Network and disk seams are stubbed: the watchlist, export_ticker,
download_and_cache, scrape_watchlist_history, config.EXPORT_DIR and the
market-data cache directory. Each stub builds its own temp directory so the
real exports/ and market_data/ trees are never touched (handle_charts
rmtree()s config.EXPORT_DIR).
"""
import os
import tempfile

from swingbot.commands import data as data_mod
from tests.commands.reply_harness import ParityCase


def _tmp() -> str:
    return tempfile.mkdtemp(prefix="v153-data-")


def _watchlist(monkeypatch, tickers=("AAA", "BBB")):
    monkeypatch.setattr(data_mod, "load_watchlist", lambda: list(tickers))
    monkeypatch.setattr(data_mod.config, "EXPORT_DIR", _tmp())


def _stub_charts(monkeypatch):
    _watchlist(monkeypatch)
    src = _tmp()   # outside EXPORT_DIR, which handle_charts wipes
    paths = {}
    for key, name in (("csv", "x.csv"), ("recent_chart", "recent.png"), ("full_chart", "full.png")):
        paths[key] = os.path.join(src, name)
        with open(paths[key], "w") as f:
            f.write("x")
    monkeypatch.setattr(data_mod, "export_ticker",
                        lambda ticker, out_dir: {"bars": 250, **paths})


def _stub_charts_one_fails(monkeypatch):
    _stub_charts(monkeypatch)
    ok = data_mod.export_ticker

    def export(ticker, out_dir):
        if ticker == "BBB":
            raise RuntimeError("yahoo down")
        return ok(ticker, out_dir)
    monkeypatch.setattr(data_mod, "export_ticker", export)


def _stub_download(monkeypatch):
    _watchlist(monkeypatch)
    monkeypatch.setattr(data_mod, "download_and_cache", lambda t, interval: {
        "ticker": t, "rows": 1234, "start": "2020-01-02 00:00:00", "end": "2026-10-09 00:00:00"})


def _stub_download_fails(monkeypatch):
    _watchlist(monkeypatch)

    def boom(t, interval):
        raise RuntimeError("no data")
    monkeypatch.setattr(data_mod, "download_and_cache", boom)


def _stub_cache(monkeypatch):
    base = _tmp()
    os.makedirs(os.path.join(base, "daily"))
    with open(os.path.join(base, "daily", "AAA.csv"), "w") as f:
        f.write("Date,Close\n2026-01-02,1\n2026-01-03,2\n")
    monkeypatch.setattr(data_mod, "CACHE_DIR", base)


def _stub_cache_missing(monkeypatch):
    monkeypatch.setattr(data_mod, "CACHE_DIR", os.path.join(_tmp(), "absent"))


def _scrape_rows(n_ok: int):
    rows = [{"ticker": f"T{i:03d}", "bars": 5000 + i, "start": "2000-01-03",
             "end": "2026-10-09", "from_cache": i % 2 == 0} for i in range(n_ok)]
    return rows + [{"ticker": "BAD", "error": "boom"}]


def _stub_scrape(n_ok: int):
    def stub(monkeypatch):
        _watchlist(monkeypatch, tickers=[f"T{i:03d}" for i in range(n_ok)] + ["BAD"])

        def scrape(tickers, out_dir, force=False, on_ticker_done=None, **_kw):
            os.makedirs(out_dir, exist_ok=True)
            return _scrape_rows(n_ok)
        monkeypatch.setattr(data_mod.export_data, "scrape_watchlist_history", scrape)
    return stub


def _stub_empty_watchlist(monkeypatch):
    _watchlist(monkeypatch, tickers=())


CASES = [
    ParityCase("charts", data_mod.handle_charts, stub=_stub_charts, expect="multi_send"),
    ParityCase("charts_one_export_fails", data_mod.handle_charts,
               stub=_stub_charts_one_fails, expect="multi_send"),
    ParityCase("download_one_ticker", data_mod.handle_download, args=("1d", "aapl"),
               stub=_stub_download, expect="multi_send"),
    ParityCase("download_1m_watchlist", data_mod.handle_download, args=("1m",),
               stub=_stub_download, expect="multi_send"),
    ParityCase("download_hourly_window", data_mod.handle_download, args=("1h",),
               stub=_stub_download, expect="multi_send"),
    ParityCase("download_all_fail", data_mod.handle_download, args=("daily",),
               stub=_stub_download_fails, expect="multi_send"),
    ParityCase("download_unknown_interval", data_mod.handle_download, args=("7y",),
               stub=_stub_download, expect="error"),
    ParityCase("cached", data_mod.handle_cached, stub=_stub_cache),
    ParityCase("cached_nothing", data_mod.handle_cached, stub=_stub_cache_missing),
    ParityCase("scrapeall_short_summary", data_mod.handle_scrapeall,
               stub=_stub_scrape(2), expect="edit"),
    ParityCase("scrapeall_long_summary_attaches_file", data_mod.handle_scrapeall,
               args=("force",), stub=_stub_scrape(60), expect="edit"),
    ParityCase("scrapeall_bad_mode", data_mod.handle_scrapeall, args=("sometimes",),
               stub=_stub_scrape(2), expect="error"),
    ParityCase("scrapeall_empty_watchlist", data_mod.handle_scrapeall,
               stub=_stub_empty_watchlist, expect="error"),
]
