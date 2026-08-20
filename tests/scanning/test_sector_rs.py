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
        engine._etf_symbol_of_sector(),
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


def test_partial_sector_etf_fetch_failure_falls_back_not_corrupted():
    """Task-review fix: sector_etf_frames non-empty (other sectors' ETFs
    fetched fine this scan) but THIS ticker's own sector's ETF (XLF for
    Financials) is specifically missing -- e.g. one of 11 sequential,
    independently try/excepted sector-ETF fetches failed. Before the fix,
    `if sector and sector_etf_frames` only checked the dict was non-empty,
    so this fell through to sector_rs_percentile(), which can't tell
    "wasn't fetched" from "genuinely at the median" and returns its own
    50.0 sentinel either way -- silently corrupting item.rs_combined with
    a synthetic reading instead of falling back to item.rs_percentile
    alone."""
    item = _scan_item_for(
        "JPM", sector="Financials",
        sector_frames={"XLK": object(), "XLE": object()},  # XLF absent
    )
    assert item.rs_combined == item.rs_percentile
    assert item.sector_rs_percentile is None


def test_fewer_than_two_total_sector_frames_falls_back_not_corrupted():
    """Final-review Finding 3: THIS ticker's own sector ETF frame IS present,
    but fewer than 2 sector ETF frames were fetched overall this scan (heavy
    partial fetch failure). sector_rs_percentile() (edge/factors.py) has its
    own synthetic-50.0 sentinel for `len(rels) < 2` that the ticker-specific
    guard alone doesn't cover -- the guard must also require enough sector
    ETF frames overall, or this reaches sector_rs_percentile() and gets its
    50.0 sentinel back, corrupting item.rs_combined instead of falling back
    to item.rs_percentile alone."""
    item = _scan_item_for(
        "AAPL", sector="Technology",
        sector_frames={"XLK": object()},  # only this ticker's own ETF, 1 total
    )
    assert item.rs_combined == item.rs_percentile
    assert item.sector_rs_percentile is None
