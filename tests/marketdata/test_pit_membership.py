"""v110: point-in-time S&P 500 membership for survivorship-aware universes."""
import json

import pytest

from swingbot.core.marketdata import pit_membership as pm

CSV = """ticker,start_date,end_date
AAL,1996-01-02,1997-01-15
AAL,2015-03-23,2024-09-23
BRK.B,2010-02-16,
OLD,2005-01-03,2012-06-01
"""


@pytest.fixture
def membership_csv(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


def test_load_intervals_normalises_symbols_and_open_ends(membership_csv):
    iv = pm.load_intervals(str(membership_csv))
    assert iv["AAL"] == [("1996-01-02", "1997-01-15"), ("2015-03-23", "2024-09-23")]
    assert iv["BRK-B"] == [("2010-02-16", pm.OPEN_END)]


def test_end_date_is_exclusive(membership_csv):
    spans = pm.load_intervals(str(membership_csv))["AAL"]
    assert pm.is_member("2024-09-20", spans)
    assert not pm.is_member("2024-09-23", spans)   # first session outside the index
    assert not pm.is_member("2000-01-03", spans)   # between the two memberships
    assert pm.is_member("2015-03-23", spans)


def test_none_spans_means_unmasked_and_empty_means_never():
    assert pm.is_member("2020-01-02", None)
    assert not pm.is_member("2020-01-02", [])


def test_is_member_accepts_timestamp_like_strings(membership_csv):
    spans = pm.load_intervals(str(membership_csv))["BRK-B"]
    assert pm.is_member("2020-01-02 00:00:00", spans)


def test_members_between_includes_leavers(membership_csv):
    iv = pm.load_intervals(str(membership_csv))
    assert pm.members_between(iv, "2010-01-01", "2023-12-31") == ["AAL", "BRK-B", "OLD"]
    assert pm.members_between(iv, "2013-01-01", "2014-12-31") == ["BRK-B"]


def test_missing_file_loads_empty(tmp_path):
    assert pm.load_intervals(str(tmp_path / "nope.csv")) == {}


@pytest.mark.parametrize("name", [None, "sp500", "etfs", "sp500+etfs", "nasdaq_pit"])
def test_only_known_pit_universes_are_masked(name):
    assert pm.membership_file_for(name) is None
    assert pm.membership_map(name, ["AAPL"]) is None


def test_membership_map_gives_unlisted_symbols_no_spans(monkeypatch, membership_csv):
    monkeypatch.setattr(pm, "membership_file_for", lambda u: str(membership_csv))
    mm = pm.membership_map("sp500_pit", ["AAL", "SPY"])
    assert mm["SPY"] == []
    assert len(mm["AAL"]) == 2


def test_committed_membership_file_covers_the_training_window():
    """The committed CSV is what every sp500_pit run masks against."""
    iv = pm.load_intervals(pm.membership_file_for("sp500_pit"))
    ever = pm.members_between(iv, "2010-01-01", "2023-12-31")
    current = [s for s, spans in iv.items() if any(e == pm.OPEN_END for _, e in spans)]
    assert 480 <= len(current) <= 510
    assert len(ever) > len(current) + 200   # leavers are the point of the file


def test_committed_pit_universe_matches_membership():
    from swingbot.core.marketdata import universe
    rows = universe.load("sp500_pit")
    iv = pm.load_intervals(pm.membership_file_for("sp500_pit"))
    assert {r["symbol"] for r in rows} <= set(iv)
    assert len(rows) > 800
    assert json.loads(json.dumps(rows))  # plain JSON rows, loader-valid
