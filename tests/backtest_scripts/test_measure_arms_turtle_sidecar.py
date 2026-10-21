"""V180-8: measure_arms writes the Turtle Soup diagnostics beside the stamped arms as
<out stem>.turtle_soup.json, never touches the arm rows, and a sidecar failure only warns. The badge
CLI scores the added Turtle Soup rows of a stamped pair."""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.market.strategy_types import TURTLE_SOUP
from tests.backtesting.test_turtle_soup_engine import FULL_PATH, SIGNAL_DAY, pin_world

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402
import turtle_soup_report as cli  # noqa: E402

KNOB = "TURTLE_SOUP_RESEARCH_MODE"
ALWAYS = {"TS1": [("2000-01-01", "9999-12-31")]}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    pin_world(monkeypatch)
    monkeypatch.setattr(ma, "load_frame", lambda ticker: {"TS1": FULL_PATH}.get(ticker))
    monkeypatch.setattr(ma, "cached_universe", lambda: ["TS1"])
    monkeypatch.setattr(ma, "_sp500_intervals", lambda: ALWAYS)
    yield
    training_data.reset()


def _pilot_blob():
    return ma.produce("pilot", {KNOB: "structural"}, universe=["TS1"], horizons=("2w",),
                      engines=("strategy",), workers=1)


def test_the_knob_constant():
    assert ma.TURTLE_SOUP_KNOB == KNOB


def test_no_sidecar_without_the_knob():
    spec = ma.windows.resolve("pilot")
    assert ma.turtle_soup_sidecar({}, {"MIN_REWARD_PCT": 4.0}, ["TS1"], spec) is None
    assert ma.turtle_soup_sidecar({}, {KNOB: "off"}, ["TS1"], spec) is None


def test_the_sidecar_matches_the_stamped_component_rows():
    blob = _pilot_blob()
    side = ma.turtle_soup_sidecar(blob, {KNOB: "structural"}, ["TS1"], ma.windows.resolve("pilot"))
    assert side["knob_delta"] == {KNOB: "structural"} and side["universe_count"] == 1
    assert side["signals"] == 1 and side["trades"] == 1 and side["matches_component_rows"] is True
    assert [(r["ticker"], r["signal_date"], r["status"]) for r in side["rows"]] == [("TS1", SIGNAL_DAY, "trade")]
    assert side["regime"]["unknown"]["n"] == 1                       # no SPY frame in this world
    assert side["universe"] == {"n": 1, "outside_sp500": 0, "share": 0.0}


def test_a_stamped_row_the_sidecar_does_not_see_is_a_mismatch():
    blob = _pilot_blob()
    extra = dict(next(r for r in blob["component"] if r["strategy"] == TURTLE_SOUP), entry_date="2019-06-03")
    blob["component"].append(extra)
    side = ma.turtle_soup_sidecar(blob, {KNOB: "structural"}, ["TS1"], ma.windows.resolve("pilot"))
    assert side["matches_component_rows"] is False


def test_main_writes_the_turtle_sidecar_beside_untouched_arms(tmp_path):
    out = tmp_path / "v180-pilot-arms.json"
    assert ma.main(["--knob", f"{KNOB}=structural", "--stage", "pilot", "--out", str(out), "--workers", "1"]) == 0
    side = json.loads((tmp_path / "v180-pilot-arms.turtle_soup.json").read_text(encoding="utf-8"))
    assert side["trades"] == 1 and side["matches_component_rows"] is True
    assert not (tmp_path / "v180-pilot-arms.diagnostics.json").exists()      # compression knob off
    blob = json.loads(out.read_text(encoding="utf-8"))
    stamped = {f.name for f in dataclasses.fields(ArmTrade)}
    assert all(set(row) == stamped for row in blob["component"] + blob["baseline"])


def test_a_failing_turtle_sidecar_only_warns(monkeypatch, tmp_path, capsys):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ma, "turtle_soup_sidecar", boom)
    out = tmp_path / "v180-pilot-arms.json"
    assert ma.main(["--knob", f"{KNOB}=structural", "--stage", "pilot", "--out", str(out), "--workers", "1"]) == 0
    assert "warning: turtle_soup sidecar not written (OSError: disk full)" in capsys.readouterr().err
    assert out.exists() and not (tmp_path / "v180-pilot-arms.turtle_soup.json").exists()


def _row(ticker, outcome, r, strategy=TURTLE_SOUP):
    return dataclasses.asdict(ArmTrade(ticker, strategy, "2w", "2024-03-01", outcome, r, 2.0,
                                       direction="bullish"))


def _arms(tmp_path, added, baseline=None):
    baseline = baseline if baseline is not None else [_row("B0", "win", 1.0, strategy="RSI")]
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"provenance": {"stage": "validation"}, "baseline": baseline,
                                "component": baseline + added}), encoding="utf-8")
    return path


def test_the_badge_cli_scores_only_the_added_turtle_rows(tmp_path, capsys):
    added = [_row(f"W{i}", "win", 1.8) for i in range(8)] + [_row(f"L{i}", "loss", -1.0) for i in range(7)]
    out_json = tmp_path / "badge.json"
    assert cli.main(["--arms", str(_arms(tmp_path, added)), "--out-json", str(out_json)]) == 0
    assert "BADGE: PASS" in capsys.readouterr().out
    badge = json.loads(out_json.read_text(encoding="utf-8"))
    assert badge["n"] == 15 and badge["verdict"] == "PASS" and badge["stage"] == "validation"


def test_the_badge_cli_reports_a_fail_with_exit_zero(tmp_path, capsys):
    added = [_row(f"W{i}", "win", 1.8) for i in range(3)]
    assert cli.main(["--arms", str(_arms(tmp_path, added))]) == 0
    assert "BADGE: FAIL" in capsys.readouterr().out


def test_the_badge_cli_refuses_a_pair_that_is_not_additive(tmp_path, capsys):
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"provenance": {}, "baseline": [_row("B0", "win", 1.0, strategy="RSI")],
                                "component": []}), encoding="utf-8")
    assert cli.main(["--arms", str(path)]) == 2
    assert "refused:not-additive" in capsys.readouterr().err


def test_the_badge_cli_refuses_malformed_arms(tmp_path, capsys):
    path = tmp_path / "arms.json"
    path.write_text("{}", encoding="utf-8")
    assert cli.main(["--arms", str(path)]) == 2
    assert "refused:malformed-arms" in capsys.readouterr().err
