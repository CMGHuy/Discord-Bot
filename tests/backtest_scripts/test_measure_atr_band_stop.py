"""V191-17: the v191 driver -- the census before any outcome, the per-arm
stage order, the one-shot and pre-registration refusals, the selected-cell-only
2023 fold and VALIDATION replays, and the two-arm Holm family. `build` is
faked; no replay runs."""
import sys
from unittest import mock
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_atr_band_stop as mabs  # noqa: E402

from swingbot.core.backtesting import atr_band_funnel as funnel
from swingbot.core.backtesting.arms import reachability as reach
from tests.backtesting.test_atr_band_funnel import census_row, lifted_band_rows

N = 200
GRID = [0.75, 1.0, 1.5]
PLATEAU = {"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29}
CENSUS = [census_row(ticker="T01"), census_row(("untouched", "floor", "floor"), ticker="T02")]
YEARS = {funnel.FOLD_TRAIN: (2021, 2022), funnel.FOLD_2023: (2023,), funnel.VALIDATION: (2024,)}


def _fake_build(calls, census=None):
    def build(kind, arm, window, cells):
        calls.append((kind, arm, tuple(window), [float(k) for k in cells]))
        if kind == "census":
            return CENSUS if census is None else census
        keys = [f"k{float(k):g}" for k in cells]
        return [row for year in YEARS[tuple(window)]
                for row in lifted_band_rows({key: PLATEAU[key] for key in keys}, year=year)]
    return build


def _run(arm, stage, out_dir, calls, **kw):
    return mabs.run_stage(arm, stage, out_dir, build=_fake_build(calls, **kw), n_resamples=N)


def _prereg(tmp_path):
    path = tmp_path / mabs.PREREGISTRATION.name
    path.write_text("x", encoding="utf-8")
    return path


def test_paths_and_the_frozen_names():
    assert mabs.stage_path("d", "K", -1).name == "2026-10-24-v191-armK-stageM1.json"
    assert mabs.stage_path("d", "R", 3).name == "2026-10-24-v191-armR-stage3.json"
    assert mabs.rows_path("d", "K", "train").name == "2026-10-24-v191-armK-train-rows.json"
    assert mabs.family_path("d").name == "2026-10-24-v191-family.json"
    assert mabs.RESULTS.parts[-3:] == ("superpowers", "results", "v191")
    assert mabs.PREREGISTRATION.name == "2026-10-24-v191-confluence-atr-band-stops-design.md"


def test_stage0_refuses_without_the_census(tmp_path):
    with pytest.raises(SystemExit, match="run stage -1 first"):
        _run("K", 0, tmp_path, [])


def test_a_zero_diff_census_closes_the_arm(tmp_path):
    calls = []
    out = _run("K", -1, tmp_path, calls, census=[census_row(("untouched",) * 3)])
    assert out["verdict"] == "refused:zero-diff"
    with pytest.raises(SystemExit, match="arm K closed at stage -1 with refused:zero-diff"):
        _run("K", 0, tmp_path, calls)


def test_census_reads_plans_only_then_stage0_builds_train_rows_once(tmp_path):
    calls = []
    assert _run("K", -1, tmp_path, calls)["verdict"] == "REACHABLE"
    assert calls == [("census", "K", funnel.FOLD_TRAIN, GRID)]
    assert _run("K", 0, tmp_path, calls)["verdict"] == "POWERED"
    assert calls[1] == ("rows", "K", funnel.FOLD_TRAIN, GRID)
    _run("K", 0, tmp_path, calls)
    assert len(calls) == 2          # the rows file is reused, not rebuilt


def test_stage0_runs_only_the_reachable_cells(tmp_path):
    calls = []
    _run("R", -1, tmp_path, calls, census=[census_row(("untouched", "floor", "floor"))])
    out = _run("R", 0, tmp_path, calls)
    assert [cell["cell"] for cell in out["cells"]] == ["k1", "k1.5"]


def test_full_chain_replays_2023_and_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    for stage in (-1, 0, 1):
        assert _run("K", stage, tmp_path, calls)["verdict"] in mabs.ADVANCING
    assert mabs._load(mabs.stage_path(tmp_path, "K", 1))["selected"] == {"cell": "k1", "k": 1.0}
    stage2 = _run("K", 2, tmp_path, calls)
    assert stage2["verdict"] == "PASS" and calls[-1] == ("rows", "K", funnel.FOLD_2023, [1.0])
    assert [fold["n"] for fold in stage2["folds"]] == [80, 80, 80]
    out = _run("K", 3, tmp_path, calls)
    assert (out["verdict"], out["cell"]) == ("PASS", "k1")
    assert calls[-1] == ("rows", "K", funnel.VALIDATION, [1.0])
    assert out["report"]["cell"] == "k1"
    assert (out["instrument"], out["data_source"]) == ("v1", "alpaca")


def test_arms_keep_separate_files(tmp_path):
    calls = []
    _run("K", -1, tmp_path, calls)
    with pytest.raises(SystemExit, match="arm R stage 0 needs 2026-10-24-v191-armR-stageM1.json"):
        _run("R", 0, tmp_path, calls)


def test_stage3_refuses_when_output_exists(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run("K", stage, tmp_path, calls)
    with pytest.raises(SystemExit, match="arm K's one VALIDATION shot is spent"):
        _run("K", 3, tmp_path, calls)


def test_family_refuses_while_an_arm_is_open(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run("K", stage, tmp_path, calls)
    _run("R", -1, tmp_path, calls)                        # REACHABLE: arm R is still open
    with pytest.raises(SystemExit, match="arm\\(s\\) R still open"):
        mabs.run_family(tmp_path)


def test_family_holm_with_an_arm_closed_before_stage3(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run("K", stage, tmp_path, calls)
    _run("R", -1, tmp_path, calls, census=[census_row(("untouched",) * 3)])
    out = mabs.run_family(tmp_path)
    p_k = mabs._load(mabs.stage_path(tmp_path, "K", 3))["permutation_p"]
    assert out["arms"]["R"]["p"] == 1.0 and out["arms"]["R"]["reached_stage3"] is False
    assert out["arms"]["K"]["p_holm"] == pytest.approx(min(1.0, 2 * p_k))
    assert mabs.family_path(tmp_path).exists()


def test_cli_refusals(tmp_path, capsys):
    assert mabs.main(["--arm", "K", "--stage", "3", "--out-dir", str(tmp_path)]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    wrong = tmp_path / "other-spec.md"
    wrong.write_text("x", encoding="utf-8")
    assert mabs.main(["--arm", "K", "--stage", "3", "--out-dir", str(tmp_path),
                      "--preregistration", str(wrong)]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    assert mabs.main(["--arm", "K", "--stage", "3", "--tickers", "3", "--out-dir", str(tmp_path),
                      "--preregistration", str(_prereg(tmp_path))]) == 1
    assert "refused:partial-validation" in capsys.readouterr().err
    assert mabs.main(["--arm", "K", "--stage", "0", "--tickers", "3"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_cli_requires_an_arm_and_family_takes_none(tmp_path, capsys):
    assert mabs.main(["--stage", "0", "--out-dir", str(tmp_path)]) == 1
    assert "refused:no-arm" in capsys.readouterr().err
    assert mabs.main(["--family", "--arm", "K", "--out-dir", str(tmp_path)]) == 1
    assert "refused:family-takes-no-arm" in capsys.readouterr().err


def test_cli_accepts_alpaca_and_instrument_v1_only(tmp_path):
    with pytest.raises(SystemExit):
        mabs.main(["--arm", "K", "--stage", "-1", "--out-dir", str(tmp_path),
                   "--data-source", "yfinance"])
    with pytest.raises(SystemExit, match="not wired yet"):
        mabs.main(["--arm", "K", "--stage", "-1", "--out-dir", str(tmp_path),
                   "--instrument", "v2"])


def test_cli_runs_the_census_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(mabs, "build", lambda kind, arm, window, cells, **kw: CENSUS)
    assert mabs.main(["--arm", "K", "--stage", "-1", "--out-dir", str(tmp_path)]) == 0
    assert mabs.stage_path(tmp_path, "K", -1).exists()


def test_build_selects_alpaca_before_any_bar_is_read(monkeypatch):
    selected, loaded = [], []
    def universe():
        assert selected == ["alpaca"]
        return ["AAA", "BBB"]

    monkeypatch.setattr(mabs, "universe", universe)
    monkeypatch.setattr(mabs.training_data, "select", lambda name=None: selected.append(name))
    monkeypatch.setattr(mabs.training_data, "load_daily",
                        lambda ticker: loaded.append((tuple(selected), ticker)))
    assert mabs.build("rows", "K", funnel.FOLD_TRAIN, [1.0], workers=1) == []
    assert selected == ["alpaca"]
    assert loaded == [(("alpaca",), "AAA"), (("alpaca",), "BBB")]


def test_reachability_rows_name_the_driver():
    for attr in ("CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_TARGET_MODE"):
        assert "scripts/backtest/measure_atr_band_stop.py" in reach.REGISTRY[attr].reason
        assert "measure_arms.py" in reach.REGISTRY[attr].reason


def test_validation_refuses_even_a_zero_ticker_limit(tmp_path, capsys):
    assert mabs.main(["--arm", "K", "--stage", "3", "--tickers", "0",
                      "--out-dir", str(tmp_path),
                      "--preregistration", str(_prereg(tmp_path))]) == 1
    assert "refused:partial-validation" in capsys.readouterr().err


def test_preregistration_must_be_a_file(tmp_path):
    path = tmp_path / mabs.PREREGISTRATION.name
    path.mkdir()
    assert mabs._preregistered(path) is False


def test_process_pool_initializes_the_frozen_data_source(monkeypatch):
    tasks = [("rows", "K", ticker, funnel.FOLD_TRAIN, (1.0,)) for ticker in ("AAA", "BBB")]
    results = [("AAA", []), ("BBB", [])]
    futures = [mock.Mock(), mock.Mock()]
    for future, result in zip(futures, results):
        future.result.return_value = result
    monkeypatch.setattr(mabs, "_resolve_replay_workers", lambda workers: 2)
    monkeypatch.setattr(mabs, "as_completed", lambda pending: pending)
    record = mock.Mock()
    with mock.patch.object(mabs, "ProcessPoolExecutor") as executor:
        pool = executor.return_value.__enter__.return_value
        pool.submit.side_effect = futures
        mabs._run_tasks(tasks, record, 2)
    executor.assert_called_once_with(max_workers=2, initializer=mabs._init_worker)
    assert pool.submit.call_args_list == [mock.call(mabs._worker, task) for task in tasks]
    assert record.call_args_list == [mock.call(*result) for result in results]


def test_build_sorts_completed_tickers_and_removes_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(mabs, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mabs.training_data, "select", lambda name: name)
    monkeypatch.setattr(mabs, "universe", lambda: ["AAA", "BBB"])

    def finish_reversed(tasks, record, workers):
        record("BBB", [{"ticker": "BBB"}])
        record("AAA", [{"ticker": "AAA"}])

    monkeypatch.setattr(mabs, "_run_tasks", finish_reversed)
    rows = mabs.build("census", "R", funnel.FOLD_TRAIN, GRID, workers=2)
    assert rows == [{"ticker": "AAA"}, {"ticker": "BBB"}]
    assert not list(tmp_path.glob("*.progress"))
