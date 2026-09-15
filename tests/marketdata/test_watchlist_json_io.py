"""save_watchlist/load_watchlist go through jsonio's atomic write/tolerant
read (A5 audit finding) instead of raw json.dump/json.load, so a crash
mid-write can no longer leave a torn watchlist.json that takes the whole
scan loop down on the next read."""
import os

from swingbot.core.marketdata.watchlist import (
    add_ticker, clear_watchlist, load_watchlist, save_watchlist,
)


def test_a_missing_file_seeds_the_default_watchlist(tmp_path):
    path = os.path.join(tmp_path, "watchlist.json")
    assert load_watchlist(path) == ["AAPL", "MSFT", "SPY"]
    assert os.path.exists(path)


def test_a_corrupt_file_degrades_to_the_seed_instead_of_raising(tmp_path):
    path = os.path.join(tmp_path, "watchlist.json")
    with open(path, "w") as f:
        f.write("{not valid json")   # simulates a crash mid-write
    assert load_watchlist(path) == ["AAPL", "MSFT", "SPY"]


def test_a_deliberately_cleared_watchlist_stays_empty_on_reload(tmp_path):
    path = os.path.join(tmp_path, "watchlist.json")
    save_watchlist(["AAPL"], path)
    clear_watchlist(path)
    # [] is falsy in Python -- must not be mistaken for "missing" and re-seeded.
    assert load_watchlist(path) == []


def test_save_writes_atomically_leaving_no_tmp_file_behind(tmp_path):
    path = os.path.join(tmp_path, "watchlist.json")
    save_watchlist([], path)   # start from an empty, known state
    add_ticker("nvda", path)
    assert load_watchlist(path) == ["NVDA"]
    assert os.listdir(tmp_path) == ["watchlist.json"]
