"""V238-3: measure_arms --r-basis books both arms on the requested basis and stamps
provenance["r_basis"]. Without the flag every call, row and stamp is today's. A population
engine's rows are not booked by arms.net_basis, so --r-basis with a population knob is
refused before any compute."""
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
PILOT = StageSpec("pilot", ("2024-01-01", "2025-12-31"), full_width=False)
NEXT_OPEN = {"MARKET_ENTRY_NEXT_OPEN": True}


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    monkeypatch.setattr(ma, "load_frame", lambda ticker: FIXTURE.get(ticker))
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAPL"])
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    yield
    training_data.reset()


def _recording(monkeypatch):
    seen = []

    def fake_run_arm(ticker, frame, engine_ids, horizons, signal_window, delta, **kwargs):
        seen.append(kwargs)
        return []
    monkeypatch.setattr(ma, "run_arm", fake_run_arm)
    return seen


def _produce(**kw):
    return ma.produce("pilot", NEXT_OPEN, universe=["AAPL"], spec=PILOT, horizons=("4w",),
                      engines=("confluence",), workers=1, **kw)


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_produce_books_both_arms_on_the_basis_and_stamps_it(monkeypatch, basis):
    seen = _recording(monkeypatch)
    blob = _produce(r_basis=basis)
    assert seen == [{"r_basis": basis}, {"r_basis": basis}]          # baseline, then component
    assert blob["provenance"]["r_basis"] == basis


def test_produce_without_a_basis_is_todays_call_and_stamp(monkeypatch):
    seen = _recording(monkeypatch)
    blob = _produce()
    assert seen == [{}, {}]
    assert "r_basis" not in blob["provenance"]


def test_net_rows_are_the_same_trades_repriced():
    default = _produce()
    net = _produce(r_basis="net")
    assert default["baseline"], "the v74 fixture yields 4w confluence trades in the pilot window"

    def keys(rows):
        return [(r["ticker"], r["strategy"], r["horizon_key"], r["entry_date"], r["outcome"]) for r in rows]

    assert keys(net["baseline"]) == keys(default["baseline"])
    assert keys(net["component"]) == keys(default["component"])
    assert all(n["r_multiple"] < d["r_multiple"] for n, d in zip(net["component"], default["component"]))


def test_produce_refuses_a_basis_on_the_population_path(monkeypatch):
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop")
    monkeypatch.setattr(ma, "_produce_population", lambda *a, **k: pytest.fail("computed"))
    with pytest.raises(ValueError, match="population"):
        ma.produce("pilot", NEXT_OPEN, universe=["AAPL"], spec=PILOT, horizons=("4w",), workers=1,
                   r_basis="net")


def _main(tmp_path, *extra):
    return ma.main(["--knob", "MIN_REWARD_PCT=4", "--stage", "pilot",
                    "--out", str(tmp_path / "arms.json"), "--workers", "1", *extra])


def _capture_produce(monkeypatch):
    captured = {}

    def fake_produce(stage, delta, **kw):
        captured.update(kw)
        return {"provenance": {"changed_outcomes": 3}}
    monkeypatch.setattr(ma, "produce", fake_produce)
    monkeypatch.setattr(ma, "_write_sidecar_or_warn", lambda *a: None)
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    return captured


@pytest.mark.parametrize("extra,expected", [((), None), (("--r-basis", "net"), "net"),
                                            (("--r-basis", "gross"), "gross")])
def test_main_passes_the_basis_to_produce(monkeypatch, tmp_path, extra, expected):
    captured = _capture_produce(monkeypatch)
    assert _main(tmp_path, *extra) == 0
    assert captured["r_basis"] == expected


def test_main_rejects_an_unknown_basis(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _main(tmp_path, "--r-basis", "NET")
    assert exc.value.code == 2


def test_main_refuses_a_basis_with_a_population_knob_before_any_compute(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(ma, "produce", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop" if "MIN_REWARD_PCT" in delta else None)
    monkeypatch.setattr(ma, "get_population_engine", lambda engine_id, **kw: object())
    assert _main(tmp_path, "--r-basis", "net") == 1
    assert "refused:r-basis-population" in capsys.readouterr().err
    assert not (tmp_path / "arms.json").exists()


def test_a_population_knob_without_a_basis_is_not_refused_by_the_basis_check(monkeypatch, tmp_path):
    captured = _capture_produce(monkeypatch)
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop" if "MIN_REWARD_PCT" in delta else None)
    monkeypatch.setattr(ma, "get_population_engine", lambda engine_id, **kw: object())
    assert _main(tmp_path) == 0
    assert captured["r_basis"] is None
