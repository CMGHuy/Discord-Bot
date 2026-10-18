import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.arms.windows import StageSpec  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402

FIXTURE = load_v74_fixture()
FIXTURE_PILOT = StageSpec("pilot", ("2024-01-01", "2025-12-31"), full_width=False)
FIXTURE_WF = StageSpec("walkforward", ("2024-01-01", "2025-12-31"), full_width=True,
                       folds=(("2024", "2024-01-01", "2024-12-31"),
                              ("2025", "2025-01-01", "2025-12-31")),
                       fold_key="folds", fold_label_key="test_year")


@pytest.fixture(autouse=True)
def fixture_frames(monkeypatch):
    monkeypatch.setattr(ma, "load_frame", lambda ticker: FIXTURE.get(ticker))


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def test_static_refusal_happens_before_any_compute(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ma, "run_arm", lambda *args, **kwargs: pytest.fail("computed"))
    rc = ma.main(["--knob", "STALL_EXIT_ENABLED=true", "--stage", "pilot", "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "refused:unreachable:journal_dependent" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_unclassified_knob_is_refused(capsys, tmp_path):
    assert ma.main(["--knob", "LOG_LEVEL=DEBUG", "--stage", "pilot", "--out", str(tmp_path / "x.json")]) == 1
    assert "refused:unreachable:unclassified" in capsys.readouterr().err


def test_validation_requires_a_preregistration(capsys, tmp_path):
    assert ma.main(["--knob", "MIN_REWARD_PCT=4", "--stage", "validation", "--out", str(tmp_path / "x.json")]) == 1
    assert "--preregistration" in capsys.readouterr().err


def test_pilot_blob_is_stamped_keyed_and_paired():
    blob = ma.produce("pilot", {"MIN_REWARD_PCT": 100.0}, universe=["AAPL", "XOM"],
                      spec=FIXTURE_PILOT, horizons=("4w",), engines=("confluence",), workers=1)
    provenance = blob["provenance"]
    assert provenance["stage"] == "pilot" and provenance["universe_count"] == 2
    assert provenance["engine_hash"]["baseline"] == provenance["engine_hash"]["component"]
    assert provenance["changed_outcomes"] > 0
    assert blob["baseline"] and all("source" in row and "direction" in row for row in blob["baseline"])


def test_walkforward_blob_has_one_entry_per_fold():
    blob = ma.produce("walkforward", {}, universe=["AAPL"], spec=FIXTURE_WF,
                      horizons=("4w",), engines=("confluence",), workers=1)
    assert [fold["test_year"] for fold in blob["folds"]] == ["2024", "2025"]
    assert "baseline" not in blob


def test_a_failing_ticker_fails_the_whole_run(monkeypatch):
    monkeypatch.setattr(ma, "load_frame", lambda ticker: None if ticker == "XOM" else FIXTURE[ticker])
    with pytest.raises(RuntimeError, match="XOM"):
        ma.produce("pilot", {}, universe=["AAPL", "XOM"], spec=FIXTURE_PILOT,
                   horizons=("4w",), engines=("confluence",), workers=1)


def test_progress_file_is_deleted_on_success(tmp_path):
    progress = tmp_path / "p.progress"
    ma.produce("pilot", {}, universe=["AAPL"], spec=FIXTURE_PILOT, horizons=("4w",),
               engines=("confluence",), workers=1, progress_path=progress)
    assert not progress.exists()


def _cache(tmp_path, monkeypatch, names):
    from swingbot.core.marketdata import backtest_cache
    for name in names:
        (tmp_path / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)


def test_universe_defaults_to_the_cached_watchlist(tmp_path, monkeypatch):
    import run_backtest_range
    _cache(tmp_path, monkeypatch, ["AAPL.csv", "MSFT.csv"])
    monkeypatch.delenv(ma.UNIVERSE_ENV, raising=False)
    monkeypatch.setattr(run_backtest_range, "_tickers_for_run",
                        lambda universe: ["MSFT", "AAPL", "NOPE"])
    assert ma.cached_universe() == ["AAPL", "MSFT"]


def test_cache_source_lists_every_cached_csv_without_the_watchlist(tmp_path, monkeypatch):
    import run_backtest_range
    _cache(tmp_path, monkeypatch, ["MSFT.csv", "AAPL.csv", "SPY.csv", "notes.txt"])
    monkeypatch.setenv(ma.UNIVERSE_ENV, "cache")
    monkeypatch.setattr(run_backtest_range, "_tickers_for_run",
                        lambda universe: pytest.fail("the watchlist was read"))
    assert ma.cached_universe() == ["AAPL", "MSFT", "SPY"]


def test_unknown_source_raises_never_falls_back(monkeypatch):
    monkeypatch.setenv(ma.UNIVERSE_ENV, "postgres")
    with pytest.raises(ValueError, match=ma.UNIVERSE_ENV):
        ma.cached_universe()


def test_the_judges_read_the_same_universe(tmp_path, monkeypatch):
    import validate_component as vc
    from scripts.backtest import permutation_test as pt
    _cache(tmp_path, monkeypatch, ["AAPL.csv", "DELL.csv"])
    monkeypatch.setenv(ma.UNIVERSE_ENV, "cache")
    assert vc._full_universe() == ["AAPL", "DELL"]
    assert pt._full_universe() == ["AAPL", "DELL"]
