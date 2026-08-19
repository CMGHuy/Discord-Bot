"""v34 Task 5: sector-relative RS wiring -- the crawl-time entry point that
activates sector_rs_percentile()/rs_score() (edge/factors.py:53,70), which
had zero callers anywhere in the codebase before this task.

Two production seams under test:
  - engine._sector_etfs_for_tickers() / engine._fetch_frames(): decide which
    sector ETFs a watchlist touches (via the static sp500.json/etfs.json
    universe files) and fetch them, the same way SPY is already fetched in
    _sync_run_scan's crawl phase.
  - engine._apply_sector_rs(): the per-item combine step the merge loop
    calls right after it sets item.rs_percentile. Must never raise or block
    an item -- an unknown/reclassified ticker, or a sector whose ETF frame
    wasn't fetched this scan, falls back silently to the ticker-only
    rs_percentile (logged, not exceptioned).

This task only wires the sector_rs_percentile/rs_combined FIELDS onto
ScanItem -- nothing here applies a gate on them yet (that's Task 6).
"""
import pytest

from swingbot.core.scanning import engine
from swingbot.core.scanning.engine import ScanItem


def _crawl_with_watchlist(tickers):
    """Mirrors the crawl-phase call sequence _sync_run_scan uses: work out
    which sector ETFs the watchlist touches, then fetch them -- same two
    calls Task 5 wires into the real crawl, alongside SPY."""
    _sector_of_ticker, needed_etfs = engine._sector_etfs_for_tickers(tickers)
    return engine._fetch_frames(needed_etfs)


def _scan_item_for(ticker, sector=None, sector_frames=None, rs_percentile=65.0):
    """Builds a bare ScanItem and runs it through _apply_sector_rs -- the
    same per-item step the merge loop calls after computing
    item.rs_percentile."""
    item = ScanItem(result=None, plan=None, conf=None)
    item.rs_percentile = rs_percentile
    sector_of_ticker = {ticker: sector} if sector else {}
    engine._apply_sector_rs(
        item, ticker, sector_of_ticker,
        sector_frames if sector_frames is not None else {},
        spy_df=None,
    )
    return item


def test_sector_etfs_are_fetched_for_watchlist_sectors(monkeypatch):
    fetched = []
    monkeypatch.setattr("swingbot.core.scanning.engine._fetch_frames",
                        lambda syms: fetched.extend(syms) or {})
    _crawl_with_watchlist(["AAPL", "JPM"])   # tech + financials
    assert "XLK" in fetched
    assert "XLF" in fetched


def test_rs_combined_weights_ticker_seventy_sector_thirty():
    from swingbot.core.edge.factors import rs_score
    assert rs_score(80.0, 40.0) == pytest.approx(68.0)


def test_unknown_sector_falls_back_to_ticker_only_rs():
    """sector_map is static; a reclassified ticker must not get a wrong
    benchmark -- it falls back and the fallback is logged."""
    item = _scan_item_for("SOMENEWTICKER", sector=None)
    assert item.rs_combined == item.rs_percentile


def test_missing_sector_etf_frame_falls_back_not_blocks():
    item = _scan_item_for("AAPL", sector="Technology", sector_frames={})
    assert item.rs_combined == item.rs_percentile
