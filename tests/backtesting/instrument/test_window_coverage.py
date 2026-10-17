"""v158 WC2: the 2009-06 cache-coverage precondition (spec section 1)."""
from pathlib import Path

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
