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
