"""v232 V232-11: the layer 2 runner over the unchanged scan replay."""
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.marketdata import history_store
from swingbot.core.marketdata.universe import ShortSnapshot
from swingbot.core.scanning import scan_replay
from swingbot.core.scanning.scan_replay import ReplayAlert
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer2, layer2_run, records  # noqa: E402

WINDOW = ("2026-10-05", "2026-10-09")
SPY = config.MARKET_REGIME_TICKER


def _alert(ticker="AAA", lane="base", mode=None, direction="bullish"):
    return ReplayAlert(lane=lane, ticker=ticker, direction=direction, source="confluence",
                       mode=mode, decision_date="2026-10-06", horizon_key="2w", strategy="RSI",
                       entry=100.0, stop=98.0, target=104.0, planned_rr=2.0, outcome="loss",
                       r_multiple=-1.0, exit_date="2026-10-08")


class _Replay:
    def __init__(self, alerts):
        self.alerts, self.calls = alerts, []

    def __call__(self, frames, window, params, *, spec, allowed_modes=None):
        self.calls.append({"window": window, "spec": spec, "allowed_modes": allowed_modes})
        return SimpleNamespace(alerts=list(self.alerts), excluded=[])


@pytest.fixture
def lanes(monkeypatch):
    base = _Replay([_alert(), _alert("BBB")])
    extra = _Replay([_alert("CCC", "short_universe", "isolated", "bearish")])
    monkeypatch.setattr(scan_replay, "replay_base_scan", base)
    monkeypatch.setattr(scan_replay, "replay_extra_short_scan", extra)
    return SimpleNamespace(base=base, extra=extra)


def _frames():
    return {SPY: make_ohlcv([100.0] * 5, start="2026-10-05"),
            "AAA": make_ohlcv([50.0] * 3, start="2026-10-05")}


def _run(tmp_path, params=None, modes=frozenset(), window=WINDOW, tickers=("AAA", "BBB")):
    out = []
    signals = layer2_run.run_layer2(_frames(), window, params or ScanParams.from_config(),
                                    base_tickers=tickers, modes=modes,
                                    checkpoint_dir=tmp_path, out=out.append)
    return signals, out


def test_replay_tickers_are_the_watchlist_plans_and_rejections():
    doc = {"plan_id": "P1", "ticker": "PPP", "direction": "bullish"}
    export = records.Export((records.LiveRecord("P1", "PPP", "bullish", doc, None, None),),
                            ({"ticker": "RRR", "gate": "rs_gate"},), ("WWW", "PPP"), ())
    assert layer2_run.replay_tickers(export) == ("PPP", "RRR", "WWW")


@pytest.mark.parametrize("enabled,broad,isolated,expected", [
    (False, True, True, frozenset()),
    (True, False, True, frozenset({"isolated"})),
    (True, True, True, frozenset({"broad", "isolated"}))])
def test_live_short_modes_follow_the_live_flags(monkeypatch, enabled, broad, isolated, expected):
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", enabled, raising=False)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_BROAD_ENABLED", broad, raising=False)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ISOLATED_ENABLED", isolated, raising=False)
    assert layer2_run.live_short_modes() == expected


def test_reference_symbols_add_pit_members_only_with_an_extra_lane(monkeypatch):
    monkeypatch.setattr(layer2_run, "_sector_etfs", lambda: ("XLK",))
    monkeypatch.setattr(layer2_run, "_pit_members", lambda: ("MMM", "ZZZ"))
    assert layer2_run.reference_symbols(frozenset()) == tuple(sorted({SPY, "XLK"}))
    assert layer2_run.reference_symbols({"isolated"}) == tuple(sorted({SPY, "XLK", "MMM", "ZZZ"}))


def test_load_frames_lists_what_the_store_lacks():
    frame = make_ohlcv([1.0, 2.0])

    def load(symbol, timeframe):
        assert timeframe == "daily"
        if symbol == "BAD":
            raise history_store.MissingStoreError("no store")
        return frame if symbol == "AAA" else None

    frames, missing = layer2_run.load_frames(["AAA", "NONE", "BAD"], load=load)
    assert list(frames) == ["AAA"] and missing == ["NONE", "BAD"]


def test_coverage_lists_sessions_without_inputs(monkeypatch):
    monkeypatch.setattr(layer2_run, "_sector_etfs", lambda: ("XLK",))
    xlk = make_ohlcv([10.0] * 5, start="2026-10-05")
    frames = {**_frames(), "XLK": xlk.drop(xlk.index[2])}                   # no 10-07 bar

    def snapshot(day):
        return None if day == "2026-10-06" else ShortSnapshot(("AAA", "PIT1"), day, {})

    cov = layer2_run.coverage(frames, WINDOW, base_tickers=("AAA",), modes={"broad"},
                              snapshot_fn=snapshot)
    assert (cov["sessions"], cov["spy_missing"]) == (5, False)
    assert cov["base_missing_days"] == {"AAA": 2}
    assert cov["panel_gaps"] == {"2026-10-07": ["XLK"]}
    assert cov["snapshot_missing"] == ["2026-10-06"]
    assert cov["extra_missing"] == {d: 1 for d in ("2026-10-05", "2026-10-07", "2026-10-08",
                                                   "2026-10-09")}


def test_coverage_without_an_extra_lane_never_asks_for_snapshots(monkeypatch):
    monkeypatch.setattr(layer2_run, "_sector_etfs", lambda: ())

    def snapshot(day):
        raise AssertionError("no snapshot without an extra lane")

    cov = layer2_run.coverage(_frames(), WINDOW, base_tickers=("AAA",), modes=frozenset(),
                              snapshot_fn=snapshot)
    assert cov["snapshot_missing"] == [] and cov["extra_missing"] == {}


def test_params_digest_is_stable_and_moves_with_a_parameter():
    params = ScanParams.from_config()
    assert layer2_run.params_digest(params) == layer2_run.params_digest(ScanParams.from_config())
    moved = dataclasses.replace(params, min_reward_pct=params.min_reward_pct + 1.0)
    assert layer2_run.params_digest(moved) != layer2_run.params_digest(params)


def test_the_base_lane_runs_with_live_horizons_and_no_extra_lane(tmp_path, lanes):
    signals, _ = _run(tmp_path)
    assert [s.ticker for s in signals] == ["AAA", "BBB"]
    assert all(isinstance(s, layer2.ReplaySignal) for s in signals)
    (call,) = lanes.base.calls
    assert call["spec"].base_tickers == ("AAA", "BBB") and lanes.extra.calls == []
    assert call["spec"].horizons == tuple(layer2_run.LEGACY_HORIZONS)
    assert not (tmp_path / "lane-extra.jsonl").exists()


def test_a_finished_lane_is_read_back_not_replayed(tmp_path, lanes):
    first, _ = _run(tmp_path, modes={"isolated"})
    again, out = _run(tmp_path, modes={"isolated"})
    assert again == first
    assert len(lanes.base.calls) == 1 and len(lanes.extra.calls) == 1
    assert [s.ticker for s in first] == ["AAA", "BBB", "CCC"]
    assert lanes.extra.calls[0]["allowed_modes"] == frozenset({"isolated"})
    assert any("from lane-base.jsonl" in line for line in out)


def test_lane_files_carry_no_outcome_key(tmp_path, lanes):
    _run(tmp_path, modes={"isolated"})
    for path in tmp_path.glob("lane-*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            keys = set(row) | set(row.get("signal", {}))
            assert keys.isdisjoint(layer2.OUTCOME_FIELDS), path.name


@pytest.mark.parametrize("change", ["params", "window", "tickers"])
def test_a_changed_input_replays_the_lane(tmp_path, lanes, change):
    _run(tmp_path)
    params = ScanParams.from_config()
    kwargs = {"params": dataclasses.replace(params, min_reward_pct=params.min_reward_pct + 1.0),
              "window": ("2026-10-05", "2026-10-08"), "tickers": ("AAA",)}
    _run(tmp_path, **{change: kwargs[change]})
    assert len(lanes.base.calls) == 2


def test_a_torn_lane_file_is_replayed(tmp_path, lanes):
    _run(tmp_path)
    path = tmp_path / "lane-base.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8", newline="\n")   # no end line
    signals, _ = _run(tmp_path)
    assert len(lanes.base.calls) == 2 and len(signals) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_a_lane_file_with_an_outcome_field_is_refused(tmp_path, lanes):
    _run(tmp_path)
    path = tmp_path / "lane-base.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    rows[1]["signal"]["r_multiple"] = 2.0
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="r_multiple"):
        _run(tmp_path)


def test_no_benchmark_frame_is_refused(tmp_path, lanes):
    with pytest.raises(ValueError, match="the replay has no dates"):
        layer2_run.run_layer2({}, WINDOW, ScanParams.from_config(), base_tickers=("AAA",),
                              modes=frozenset(), checkpoint_dir=tmp_path, out=lambda _: None)
