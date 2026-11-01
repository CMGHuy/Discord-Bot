"""v158 WC2: the 2009-06 cache-coverage precondition (spec section 1)."""
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.instrument import contract, coverage
from swingbot.core.backtesting.instrument.coverage import CoverageReport

HEADER = "Date,Open,High,Low,Close,Volume\n"
MEMBERSHIP = (
    "ticker,start_date,end_date\n"
    "AAA,2005-01-03,\n"            # member through the whole research span
    "BBB,2000-01-03,2009-12-31\n"  # left before the research span: not a research member
    "CCC,2012-03-01,2015-01-02\n"  # joined inside the span
    "BRK.B,2008-02-01,\n"          # normalised to BRK-B, the cache spelling
    "DDD,2026-02-02,\n"            # joined after research_end: not a research member
)


def _csv(cache: Path, name: str, first_day: str | None, extra_header: str = "") -> None:
    rows = "" if first_day is None else f"{first_day},1,1,1,1,100\n{first_day[:8]}28,1,1,1,1,100\n"
    (cache / f"{name}.csv").write_text(HEADER + extra_header + rows, encoding="utf-8")


@pytest.fixture
def universe_dir(tmp_path, monkeypatch):
    """A synthetic data/ dir: pit_membership reads config.DATA_DIR at call time."""
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    return data


# --- first_bar_date --------------------------------------------------------------

def test_first_bar_date_reads_the_first_dated_row(tmp_path):
    _csv(tmp_path, "AAA", "2009-06-01")
    assert coverage.first_bar_date(tmp_path / "AAA.csv") == "2009-06-01"


def test_first_bar_date_trims_a_timestamp_to_the_day(tmp_path):
    (tmp_path / "AAA.csv").write_text(HEADER + "2009-06-01 00:00:00,1,1,1,1,100\n",
                                      encoding="utf-8")
    assert coverage.first_bar_date(tmp_path / "AAA.csv") == "2009-06-01"


def test_first_bar_date_skips_undated_header_rows(tmp_path):
    """yfinance multi-index CSVs carry 'Ticker,...' and 'Date,,,' rows first."""
    _csv(tmp_path, "AAA", "2010-01-04", extra_header="Ticker,AAA,AAA,AAA,AAA,AAA\nDate,,,,,\n")
    assert coverage.first_bar_date(tmp_path / "AAA.csv") == "2010-01-04"


def test_first_bar_date_is_none_for_an_absent_or_empty_csv(tmp_path):
    _csv(tmp_path, "EMPTY", None)
    assert coverage.first_bar_date(tmp_path / "EMPTY.csv") is None
    assert coverage.first_bar_date(tmp_path / "NOPE.csv") is None


# --- check_coverage ----------------------------------------------------------------

def test_check_coverage_sorts_covered_late_and_missing(tmp_path):
    _csv(tmp_path, "AAA", "2009-06-01")   # exactly the required day: covered
    _csv(tmp_path, "OLD", "1999-11-18")   # earlier: covered
    _csv(tmp_path, "CCC", "2009-06-02")   # one day late
    _csv(tmp_path, "EMPTY", None)         # no dated row: missing
    report = coverage.check_coverage(["CCC", "AAA", "OLD", "EMPTY", "GONE", "AAA"],
                                     "2009-06-01", tmp_path)
    assert report == CoverageReport(required_start="2009-06-01", covered=("AAA", "OLD"),
                                    late=(("CCC", "2009-06-02"),), missing=("EMPTY", "GONE"))
    assert report.gaps == 3


def test_check_coverage_uses_the_backtest_cache_filename_rule(tmp_path):
    """'^VIX' is cached as _VIX.csv (backtest_cache.cache_path), never re-derived here."""
    _csv(tmp_path, "_VIX", "2009-01-02")
    report = coverage.check_coverage(["^VIX"], "2009-06-01", tmp_path)
    assert report.covered == ("^VIX",)
    assert report.gaps == 0


def test_check_coverage_never_reads_market_data(tmp_path, monkeypatch):
    """Two OHLCV caches (known-traps.md): only the cache_dir passed in is read."""
    seen = []
    real = coverage.first_bar_date
    monkeypatch.setattr(coverage, "first_bar_date", lambda p: seen.append(Path(p)) or real(p))
    coverage.check_coverage(["AAA"], "2009-06-01", tmp_path)
    assert seen == [tmp_path / "AAA.csv"]


# --- research members and their first membership -----------------------------------

def test_research_members_are_every_pit_member_inside_the_v2_research_span(universe_dir):
    assert coverage.research_members(contract.resolve("v2")) == ["AAA", "BRK-B", "CCC"]


def test_research_members_refuse_an_instrument_without_a_pit_universe(universe_dir):
    with pytest.raises(ValueError, match="no point-in-time universe"):
        coverage.research_members(contract.resolve("v1"))


def test_research_members_refuse_a_missing_membership_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="sp500_membership.csv"):
        coverage.research_members(contract.resolve("v2"))


def test_first_membership_is_the_earliest_span_start_touching_the_research_span(universe_dir):
    spec = contract.resolve("v2")
    assert coverage.first_membership(spec, ["AAA", "CCC", "BRK-B", "ZZZ"]) == {
        "AAA": "2005-01-03", "CCC": "2012-03-01", "BRK-B": "2008-02-01"}


# --- render_markdown -------------------------------------------------------------------

def test_render_markdown_lists_every_gap_with_its_first_membership():
    report = CoverageReport(required_start="2009-06-01", covered=("AAA",),
                            late=(("CCC", "2012-03-05"),), missing=("GONE",))
    text = coverage.render_markdown(report, {"CCC": "2012-03-01", "GONE": "2010-01-04"})
    assert "Required first bar: 2009-06-01" in text
    assert "| Covered | 1 |" in text
    assert "| Late | 1 |" in text
    assert "| Missing | 1 |" in text
    assert "| Gaps | 2 |" in text
    assert "| CCC | 2012-03-05 | 2012-03-01 |" in text
    assert "| GONE | 2010-01-04 |" in text


def test_render_markdown_says_so_when_there_is_no_gap():
    report = CoverageReport(required_start="2009-06-01", covered=("AAA",), late=(), missing=())
    text = coverage.render_markdown(report, {})
    assert "| Gaps | 0 |" in text
    assert "No gaps" in text


# --- CLI -------------------------------------------------------------------------------

def test_cli_writes_the_report_and_exits_one_on_gaps(universe_dir, tmp_path):
    from scripts.data import check_cache_coverage as cli
    cache = tmp_path / "cache"
    cache.mkdir()
    _csv(cache, "AAA", "2009-06-01")
    _csv(cache, "CCC", "2010-01-04")   # BRK-B has no CSV at all
    out = tmp_path / "coverage.md"
    code = cli.run(["--instrument", "v2", "--cache-dir", str(cache), "--out", str(out)])
    assert code == 1
    text = out.read_text(encoding="utf-8")
    assert f"Cache: `{cache}`" in text
    assert "Instrument: v2" in text
    assert "| CCC | 2010-01-04 | 2012-03-01 |" in text
    assert "| BRK-B | 2008-02-01 |" in text


def test_cli_exits_zero_when_every_member_is_covered(universe_dir, tmp_path):
    from scripts.data import check_cache_coverage as cli
    cache = tmp_path / "cache"
    cache.mkdir()
    for name in ("AAA", "BRK-B", "CCC"):
        _csv(cache, name, "2009-05-01")
    assert cli.run(["--instrument", "v2", "--cache-dir", str(cache)]) == 0


def test_cli_refuses_v1_which_defines_no_warmup(universe_dir, tmp_path, capsys):
    from scripts.data import check_cache_coverage as cli
    assert cli.run(["--instrument", "v1", "--cache-dir", str(tmp_path)]) == 2
    assert "nothing to check" in capsys.readouterr().err


def test_cli_defaults_to_the_backtest_cache_dir(universe_dir, tmp_path, monkeypatch):
    from scripts.data import check_cache_coverage as cli
    from swingbot.core.marketdata import backtest_cache
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    for name in ("AAA", "BRK-B", "CCC"):
        _csv(tmp_path, name, "2009-05-01")
    assert cli.run(["--instrument", "v2"]) == 0


# --- v190: the PIT store layout (<root>/daily/<SAFE>.csv) -------------------------------

def _store_csv(root: Path, name: str, first_day: str | None) -> None:
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    _csv(folder, name, first_day)


def test_store_first_bar_reads_the_store_daily_layout(tmp_path):
    _store_csv(tmp_path, "BRK-B", "2016-01-04")
    _store_csv(tmp_path, "GC_F", "2016-02-01")
    assert coverage.store_first_bar(tmp_path, "BRK-B") == pd.Timestamp("2016-01-04")
    assert coverage.store_first_bar(tmp_path, "GC=F") == pd.Timestamp("2016-02-01")
    assert coverage.store_first_bar(tmp_path, "NOPE") is None


def test_store_first_bar_is_none_for_a_file_with_no_dated_row(tmp_path):
    _store_csv(tmp_path, "EMPTY", None)
    assert coverage.store_first_bar(tmp_path, "EMPTY") is None


def test_check_store_coverage_sorts_covered_late_and_missing(tmp_path):
    _store_csv(tmp_path, "AAA", "2016-01-04")
    _store_csv(tmp_path, "CCC", "2018-03-01")
    report = coverage.check_store_coverage(["CCC", "AAA", "ZZZ", "AAA"], "2016-01-04", tmp_path)
    assert report == CoverageReport("2016-01-04", ("AAA",), (("CCC", "2018-03-01"),), ("ZZZ",))


def test_check_store_coverage_ignores_a_cache_style_file_at_the_root(tmp_path):
    _csv(tmp_path, "AAA", "2016-01-04")          # backtest-cache layout, not daily/
    assert coverage.check_store_coverage(["AAA"], "2016-01-04", tmp_path).missing == ("AAA",)


def test_check_store_coverage_of_an_empty_store_lists_every_member_missing(tmp_path):
    report = coverage.check_store_coverage(["AAA", "BRK-B"], "2016-01-04", tmp_path)
    assert report.missing == ("AAA", "BRK-B") and report.gaps == 2


def test_cli_v3_checks_the_pit_store_from_2016(universe_dir, tmp_path, capsys):
    from scripts.data import check_cache_coverage as cli
    store = tmp_path / "pit"
    _store_csv(store, "AAA", "2016-01-04")
    _store_csv(store, "BRK-B", "2017-05-01")
    out = tmp_path / "coverage.md"
    code = cli.run(["--instrument", "v3", "--store-root", str(store), "--out", str(out)])
    assert code == 1
    text = out.read_text(encoding="utf-8")
    assert "Instrument: v3 (universe sp500_pit, research 2017-01-01..2025-12-31)" in text
    assert f"Store: `{store}`" in text
    assert "Members checked: 2" in text                 # CCC left in 2015, DDD joins in 2026
    assert "Required first bar: 2016-01-04" in text
    assert "| BRK-B | 2017-05-01 | 2008-02-01 |" in text
    assert f"COVERAGE: GAPS  1 gap(s), store {store}" in capsys.readouterr().err


def test_cli_v3_exits_zero_when_the_store_covers_every_member(universe_dir, tmp_path):
    from scripts.data import check_cache_coverage as cli
    store = tmp_path / "pit"
    for name in ("AAA", "BRK-B"):
        _store_csv(store, name, "2016-01-04")
    assert cli.run(["--instrument", "v3", "--store-root", str(store)]) == 0


def test_cli_v3_defaults_to_the_pit_root_and_ignores_history_store_dir(universe_dir, tmp_path,
                                                                        monkeypatch):
    from scripts.data import check_cache_coverage as cli
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "watchlist_store"))
    for name in ("AAA", "BRK-B"):
        _store_csv(universe_dir / "market_data_pit", name, "2016-01-04")
    assert cli.run(["--instrument", "v3"]) == 0


def test_cli_refuses_a_cache_dir_with_v3_and_a_store_root_with_v2(universe_dir, tmp_path, capsys):
    from scripts.data import check_cache_coverage as cli
    assert cli.run(["--instrument", "v3", "--cache-dir", str(tmp_path)]) == 2
    assert "--store-root" in capsys.readouterr().err
    assert cli.run(["--instrument", "v2", "--store-root", str(tmp_path)]) == 2
    assert "--cache-dir" in capsys.readouterr().err
