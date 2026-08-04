"""The live watchlist is untracked (d8cbd22), so a fresh clone has no
data/watchlist.json and must seed from the tracked universe file rather than
the 3-ticker stub -- otherwise a new deployment silently scans almost nothing.
"""
import json
import os

from swingbot.core import watchlist as wl


def test_seeds_from_tracked_universe_file(tmp_path, monkeypatch):
    seed = tmp_path / "watchlist_seed.json"
    seed.write_text(json.dumps(["NVDA", "AMD", "INTC"]))
    monkeypatch.setattr(wl, "SEED_PATH", str(seed))

    path = str(tmp_path / "watchlist.json")
    assert wl.load_watchlist(path) == ["NVDA", "AMD", "INTC"]
    # and it is persisted, so the next boot reads the live file
    assert json.loads(open(path).read()) == ["AMD", "INTC", "NVDA"]


def test_existing_live_watchlist_wins_over_seed(tmp_path, monkeypatch):
    """The seed must never overwrite a real watchlist -- that would silently
    revert the user's Discord/admin-UI edits on every restart."""
    seed = tmp_path / "watchlist_seed.json"
    seed.write_text(json.dumps(["NVDA", "AMD"]))
    monkeypatch.setattr(wl, "SEED_PATH", str(seed))

    path = str(tmp_path / "watchlist.json")
    with open(path, "w") as f:
        json.dump(["TSLA"], f)

    assert wl.load_watchlist(path) == ["TSLA"]


def test_falls_back_to_stub_when_seed_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(wl, "SEED_PATH", str(tmp_path / "nope.json"))
    path = str(tmp_path / "watchlist.json")
    assert wl.load_watchlist(path) == wl._FALLBACK


def test_falls_back_to_stub_when_seed_corrupt(tmp_path, monkeypatch):
    seed = tmp_path / "watchlist_seed.json"
    seed.write_text("{not json")
    monkeypatch.setattr(wl, "SEED_PATH", str(seed))
    path = str(tmp_path / "watchlist.json")
    assert wl.load_watchlist(path) == wl._FALLBACK


def test_shipped_seed_file_is_the_real_universe():
    """Guards the file itself: it is tracked data, so a bad edit ships."""
    assert os.path.exists(wl.SEED_PATH), f"missing seed file {wl.SEED_PATH}"
    tickers = json.loads(open(wl.SEED_PATH).read())
    assert isinstance(tickers, list)
    assert len(tickers) >= 70, f"seed shrank to {len(tickers)} tickers"
    assert tickers == sorted(set(tickers)), "seed must be sorted and unique"
    assert all(t == t.upper() and t.strip() for t in tickers)
    for expected in ("NVDA", "AAPL", "MSFT", "AMD", "INTC"):
        assert expected in tickers
