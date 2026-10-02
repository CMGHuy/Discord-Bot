"""V118-7: the scan-level SHORT-universe instrument (Stage -1 contract).

The replay runs the live candidate selector (`build_extra_candidates`), the
live bearish scenario scoring (`scan_extra_candidate`) and the live per-item
gates (`qualify_short_item`) at each historical decision date, against a
point-in-time membership/sector fixture -- never `data/universe`. Two
fixtures pin the contract the plan names:

1. one PIT member (AAA) passes end to end and one ex-member (BBB, the same
   bars) disappears; base alerts are identical with the lane off and on;
2. the same bars with the RS gate failing produce zero added rows.
"""
import dataclasses
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import reachability
from swingbot.core.backtesting.arms.short_universe_engine import ShortUniverseEngine
from swingbot.core.marketdata import universe
from swingbot.core.scanning import analyze, scan_replay
from swingbot.scan_params import ScanParams

from tests.backtesting.test_v74_fixture import load_v74_fixture

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

# Fixture shape, frozen once it fired (architecture.md: synthetic fixtures need
# tuning). Real AAPL bars build a bearish 4w/3m scenario on 2025-01-10 at a
# 0.5% stop floor (the live 2.0% floor leaves two tickers' bars almost no
# scenario -- known-traps' empty band). XLE rises 0.25%/session, so AAA is an
# isolated laggard; SPY rises 0.06%/session, so the regime is not bearish; four
# synthetic members rise 0.4%/session and fill the reference panel above AAA
# (AAA ranks 20th percentile, under the 25 laggard gate). BASE is XOM's bars
# shifted 30 sessions later so its bullish 4w alert lands on the same date.
WINDOW = ("2019-01-11", "2019-01-11")
HORIZONS = ("4w", "3m")
BASE_TICKERS = ("BASE",)
BASE_SHIFT = 30
# The real bars are relabelled 313 whole weeks earlier (2025-01-10 -> 2019-01-11,
# weekdays kept) so the fixture sits inside the pilot window and never touches
# the 2024-2025 VALIDATION window -- the v100 stamp gate refuses that contact.
DATE_SHIFT = pd.Timedelta(weeks=313)
RISERS = ("CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ")


def _synthetic(index, start, daily):
    close = start * ((1.0 + daily) ** np.arange(len(index)))
    return pd.DataFrame({"Open": close, "High": close * 1.004, "Low": close * 0.996,
                         "Close": close, "Volume": 5e7}, index=index)


def _frames():
    real = load_v74_fixture()
    aapl = real["AAPL"]
    index = aapl.index
    base = real["XOM"].iloc[:len(index) - BASE_SHIFT].copy()
    base.index = index[BASE_SHIFT:]
    frames = {"AAA": aapl, "BBB": aapl.copy(), "BASE": base,
              "SPY": _synthetic(index, 400.0, 0.0006), "XLE": _synthetic(index, 80.0, 0.0025)}
    for i, symbol in enumerate(RISERS):
        frames[symbol] = _synthetic(index, 50.0 + i, 0.004)
    for frame in frames.values():
        frame.index = frame.index - DATE_SHIFT
    return frames


MEMBERSHIP = """ticker,start_date,end_date
AAA,2000-01-03,
BBB,2000-01-03,2018-06-04
BASE,2000-01-03,
CCC,2000-01-03,
DDD,2000-01-03,
EEE,2000-01-03,
FFF,2000-01-03,
GGG,2000-01-03,
HHH,2000-01-03,
III,2000-01-03,
JJJ,2000-01-03,
"""
SECTORS = "ticker,start_date,end_date,sector\n" + "".join(
    f"{s},2000-01-03,,Energy\n" for s in ("AAA", "BBB", "BASE", *RISERS))


@pytest.fixture
def pit_universe(tmp_path, monkeypatch):
    """A fixture membership + sector-history directory; data/universe is never read."""
    (tmp_path / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    (tmp_path / "sp500_sector_history.csv").write_text(SECTORS, encoding="utf-8")
    shutil.copy(ROOT / "data" / "universe" / "etfs.json", tmp_path / "etfs.json")
    monkeypatch.setattr(universe, "UNIVERSE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def gates(monkeypatch, pit_universe):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 25.0)
    monkeypatch.setattr(config, "SIGNAL_CONFIRMATION_SCANS", 1)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    monkeypatch.setattr(config, "MIN_TARGET_CONFLUENCE_COUNT", 2)
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", False)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.5)


class _Sealed:
    def __getattr__(self, name):
        raise AssertionError(f"the replay reached a live singleton: {name}")


@pytest.fixture
def sealed(monkeypatch, gates):
    """Journal, open-trade store, stop flag and network are unreachable."""
    monkeypatch.setattr(analyze, "trade_log", _Sealed())
    monkeypatch.setattr(analyze, "runstate", _Sealed())
    from swingbot.core.scanning import fetch, short_run
    monkeypatch.setattr(short_run, "trade_log", _Sealed())
    monkeypatch.setattr(short_run, "state", _Sealed())
    monkeypatch.setattr(fetch, "_fetch_frames", _Sealed())
    monkeypatch.setattr(fetch, "_crawl_latest_data", _Sealed())


def _replay(mode, frames=None):
    return scan_replay.replay_short_universe(
        frames or _frames(), WINDOW, ScanParams.from_config(), mode=mode,
        spec=scan_replay.ReplaySpec(base_tickers=BASE_TICKERS, horizons=HORIZONS))


# --- fixture 1: one PIT member is added, the ex-member disappears -------------------

def test_one_pit_member_is_added_and_the_ex_member_disappears(sealed):
    measured = _replay("isolated")
    baseline = _replay("off")
    assert [row.ticker for row in measured.added] == ["AAA"]
    assert measured.added[0].direction == "bearish"
    assert measured.added[0].planned_rr is not None
    assert measured.added[0].source == "confluence"
    assert measured.base_alerts == baseline.base_alerts
    assert baseline.added == []


def test_an_added_row_records_mode_dates_prices_and_outcome(sealed):
    row = _replay("isolated").added[0]
    assert (row.lane, row.mode, row.decision_date) == ("short_universe", "isolated", "2019-01-11")
    assert row.stop > row.entry > row.target
    assert row.outcome in ("win", "loss", "scratch", "timeout", "not_triggered", "no_trade")


def test_ex_member_is_absent_from_every_record(sealed):
    measured = _replay("isolated")
    assert all(row.ticker != "BBB" for row in measured.added + measured.base_alerts)
    assert all(ex.ticker != "BBB" for ex in measured.excluded)


def test_disallowed_mode_is_excluded_with_a_reason(sealed):
    measured = _replay("broad")
    assert measured.added == []
    assert any((ex.ticker, ex.reason) == ("AAA", "mode_not_allowed") for ex in measured.excluded)


def test_decisions_do_not_change_when_the_future_is_removed(sealed):
    """Truncation (no-lookahead): bars after the window's last decision date may
    move only the exit outcome, never which alert was issued or its prices."""
    full = _replay("isolated")
    cut = {symbol: frame.loc[:WINDOW[1]] for symbol, frame in _frames().items()}
    truncated = _replay("isolated", frames=cut)

    def decided(rows):
        return [(r.ticker, r.horizon_key, r.decision_date, r.entry, r.stop, r.target) for r in rows]
    assert decided(truncated.added) == decided(full.added)
    assert decided(truncated.base_alerts) == decided(full.base_alerts)


def test_missing_sector_history_skips_the_lane_with_a_count(sealed, pit_universe):
    (pit_universe / "sp500_sector_history.csv").unlink()
    measured = _replay("isolated")
    assert measured.added == []
    assert [ex.reason for ex in measured.excluded if ex.lane == "short_universe"] == ["no_snapshot"]


# --- fixture 2: the RS gate fails, nothing is added ---------------------------------

def test_rs_failure_adds_zero_rows(sealed, monkeypatch):
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 5.0)
    measured = _replay("isolated")
    assert measured.added == []
    assert any((ex.ticker, ex.stage, ex.reason) == ("AAA", "rs", "rs_blocked") for ex in measured.excluded)
    assert measured.base_alerts == _replay("off").base_alerts


# --- the arm engine and the standard producer ----------------------------------------

def _engine_run(mode):
    return ShortUniverseEngine(base_tickers=BASE_TICKERS, horizons=HORIZONS).run_population(
        _frames(), WINDOW, ScanParams.from_config(), mode=mode)


def test_engine_off_is_the_base_rows_and_on_adds_the_short(sealed):
    off, on = _engine_run("off"), _engine_run("isolated")
    assert all(isinstance(row, ArmTrade) for row in on)
    added = [row for row in on if row not in off]
    assert off == [row for row in on if row.ticker != "AAA"]
    assert [(row.ticker, row.direction, row.source) for row in added] == [("AAA", "bearish", "confluence")]


def test_research_mode_knob_is_reachable_only_through_the_population_engine():
    reach = reachability.REGISTRY["SHORT_UNIVERSE_RESEARCH_MODE"]
    assert reach.cls == reachability.REACHABLE
    assert reach.observed_by == frozenset({"short_universe"})
    assert config.SHORT_UNIVERSE_RESEARCH_MODE == "off"


def test_producer_runs_baseline_off_and_component_on_with_one_stamp(sealed, monkeypatch):
    frames = _frames()
    monkeypatch.setattr(ma, "load_frame", lambda ticker: frames.get(ticker))
    monkeypatch.setattr(ma, "population_symbols", lambda: sorted(frames))
    spec = dataclasses.replace(ma.windows.resolve("pilot"), signal_window=WINDOW)
    blob = ma.produce("pilot", {"SHORT_UNIVERSE_RESEARCH_MODE": "isolated"}, universe=list(BASE_TICKERS),
                      spec=spec, horizons=HORIZONS, workers=1)
    stamp = blob["provenance"]
    assert stamp["engines"] == ["short_universe"]
    assert stamp["universe"] == list(BASE_TICKERS)
    assert stamp["engine_hash"]["baseline"] == stamp["engine_hash"]["component"]
    assert stamp["changed_outcomes"] == 1
    added = [row for row in blob["component"] if row not in blob["baseline"]]
    assert [(row["ticker"], row["direction"]) for row in added] == [("AAA", "bearish")]
    json.dumps(blob)


def test_stage_minus_one_fixture_is_reachable(sealed, monkeypatch, tmp_path, capsys):
    """The single deterministic Stage -1 fixture: the producer's stamped blob, read
    by validate_component's reachability stage, is REACHABLE (fixture only --
    no cached universe, no data/universe file is read)."""
    import validate_component as vc
    frames = _frames()
    monkeypatch.setattr(ma, "load_frame", lambda ticker: frames.get(ticker))
    monkeypatch.setattr(ma, "population_symbols", lambda: sorted(frames))
    spec = dataclasses.replace(ma.windows.resolve("pilot"), signal_window=WINDOW)
    arms = tmp_path / "stage-1-fixture.json"
    arms.write_text(json.dumps(ma.produce("pilot", {"SHORT_UNIVERSE_RESEARCH_MODE": "isolated"},
                                          universe=list(BASE_TICKERS), spec=spec, horizons=HORIZONS)))
    rc = vc.main(["--stage", "reachability", "--arms", str(arms), "--title", "v118 fixture",
                  "--window", "fixture"])
    out = capsys.readouterr().out
    assert rc == 0 and "REACHABLE" in out and "changed outcomes: 1" in out


def test_cli_refuses_when_the_population_engine_is_absent(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ma, "get_population_engine",
                        lambda engine_id, **kw: (_ for _ in ()).throw(KeyError(engine_id)))
    monkeypatch.setattr(ma, "produce", lambda *a, **k: pytest.fail("computed"))
    rc = ma.main(["--knob", "SHORT_UNIVERSE_RESEARCH_MODE=broad", "--stage", "pilot",
                  "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "refused:no-population-engine" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_bad_research_mode_value_is_refused(capsys, tmp_path):
    rc = ma.main(["--knob", "SHORT_UNIVERSE_RESEARCH_MODE=sideways", "--stage", "pilot",
                  "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "refused:bad-knob" in capsys.readouterr().err


def test_now_is_after_the_close_of_the_decision_date():
    now = scan_replay.decision_now("2025-01-10")
    assert now.tzinfo is not None and now.astimezone(dt.timezone.utc).date() == dt.date(2025, 1, 10)
