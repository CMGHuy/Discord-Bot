"""v190 section 3: signal-date cuts (missing-session runs, trailing-coverage
failures) are subtracted from the membership spans the signal mask applies.
With no cuts, membership_map is byte-identical to before."""
import pytest

from swingbot import config
from swingbot.core.marketdata import pit_membership as pm

MEMBERSHIP = ("ticker,start_date,end_date\n"
              "AAA,2015-01-02,\n"
              "BBB,2016-03-01,2018-06-08\n"
              "BBB,2020-01-02,2022-01-03\n"
              "BRK.B,2010-01-04,\n")


@pytest.fixture
def universe_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    return data


# --- subtract_spans -------------------------------------------------------------------

@pytest.mark.parametrize("spans, cuts, expected", [
    # no cuts: the spans as they are
    ([("2016-01-04", "2018-01-02")], [], [("2016-01-04", "2018-01-02")]),
    # a cut inside a span splits it; the cut's end is the first admitted day again
    ([("2016-01-04", "2018-01-02")], [("2017-03-01", "2017-03-20")],
     [("2016-01-04", "2017-03-01"), ("2017-03-20", "2018-01-02")]),
    # a cut over the span's start / end trims it
    ([("2016-01-04", "2018-01-02")], [("2015-06-01", "2016-02-01")],
     [("2016-02-01", "2018-01-02")]),
    ([("2016-01-04", "2018-01-02")], [("2017-12-01", "2019-01-01")],
     [("2016-01-04", "2017-12-01")]),
    # a cut covering the whole span removes it (a zero-coverage span)
    ([("2016-01-04", "2018-01-02")], [("2016-01-04", "2018-01-02")], []),
    ([("2016-01-04", "2018-01-02")], [("2010-01-01", "9999-12-31")], []),
    # cuts touching a span's edge only (half-open) remove nothing
    ([("2016-01-04", "2018-01-02")], [("2018-01-02", "2018-03-01"), ("2015-01-01", "2016-01-04")],
     [("2016-01-04", "2018-01-02")]),
    # unsorted, overlapping cuts across two spans
    ([("2016-03-01", "2018-06-08"), ("2020-01-02", "2022-01-03")],
     [("2021-01-04", "2021-02-01"), ("2016-05-02", "2016-06-01"), ("2016-05-20", "2016-07-01")],
     [("2016-03-01", "2016-05-02"), ("2016-07-01", "2018-06-08"),
      ("2020-01-02", "2021-01-04"), ("2021-02-01", "2022-01-03")]),
    # an open-ended membership
    ([("2015-01-02", pm.OPEN_END)], [("2017-03-01", "2017-03-20")],
     [("2015-01-02", "2017-03-01"), ("2017-03-20", pm.OPEN_END)]),
    # no spans at all (a symbol with no membership row)
    ([], [("2017-03-01", "2017-03-20")], []),
])
def test_subtract_spans(spans, cuts, expected):
    assert pm.subtract_spans(spans, cuts) == expected


def test_subtract_spans_mutates_nothing():
    spans, cuts = [("2016-01-04", "2018-01-02")], [("2017-03-01", "2017-03-20")]
    pm.subtract_spans(spans, cuts)
    assert spans == [("2016-01-04", "2018-01-02")]
    assert cuts == [("2017-03-01", "2017-03-20")]


def test_a_cut_date_is_no_longer_a_member_but_its_end_is():
    spans = pm.subtract_spans([("2016-01-04", "2018-01-02")], [("2017-03-01", "2017-03-20")])
    assert pm.is_member("2017-02-28", spans)
    assert not pm.is_member("2017-03-01", spans)
    assert not pm.is_member("2017-03-19", spans)
    assert pm.is_member("2017-03-20", spans)


# --- membership_map(cuts=) --------------------------------------------------------------

def test_no_cuts_is_byte_identical(universe_dir):
    symbols = ["AAA", "BBB", "BRK-B", "SPY"]
    before = pm.membership_map("sp500_pit", symbols)
    assert pm.membership_map("sp500_pit", symbols, None) == before
    assert pm.membership_map("sp500_pit", symbols, cuts={}) == before
    assert before["SPY"] == []


def test_cuts_are_subtracted_per_symbol(universe_dir):
    got = pm.membership_map("sp500_pit", ["AAA", "BBB", "SPY"],
                            cuts={"BBB": [("2017-01-03", "2017-02-01")],
                                  "SPY": [("2017-01-03", "2017-02-01")],
                                  "ZZZ": [("2017-01-03", "2017-02-01")]})
    assert got["AAA"] == [("2015-01-02", pm.OPEN_END)]
    assert got["BBB"] == [("2016-03-01", "2017-01-03"), ("2017-02-01", "2018-06-08"),
                          ("2020-01-02", "2022-01-03")]
    assert got["SPY"] == []
    assert set(got) == {"AAA", "BBB", "SPY"}


def test_a_non_pit_universe_ignores_cuts(universe_dir):
    assert pm.membership_map("sp500", ["AAA"], cuts={"AAA": [("2017-01-03", "2017-02-01")]}) is None
    assert pm.membership_map(None, ["AAA"], cuts={"AAA": [("2017-01-03", "2017-02-01")]}) is None
