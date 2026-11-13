"""v226: the stop-width report -- one TRAIN verdict, disclosures for both
populations, provenance with both replay sidecars, and its own file under
data/reports (never expectancy-attribution.json)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.infra import expectancy_attribution_store as store

REPO = Path(__file__).resolve().parents[2]
REPORT_KEYS = ["generated_at", "study", "seed", "edges", "labels", "verdict",
               "disclosures", "volatility_note", "provenance"]
PROVENANCE_KEYS = ["train_rows", "run_sidecar", "store_provenance", "frictions",
                   "live_fills_include_frictions", "n_resamples"]
STAMP = "2026-11-12T00:00:00+00:00"


def stop_width_rows(n: int, *, live: bool = False, atr: bool = True) -> list[dict]:
    """Synthetic stop-width rows over 200 TRAIN weeks: tight stops
    (stop_atr < 0.35) lose, the rest earn; atr_pct = 1.9 / stop_atr (so
    Spearman rho is -1) unless ``atr`` is False. Imported by the V226-10b
    and V226-11 tests."""
    rows = []
    for i in range(n):
        stop_atr = round(0.2 + (i % 8) * 0.1, 2)
        row = {"r": (-0.6 if stop_atr < 0.35 else 0.1) + ((i * 37) % 11 - 5) / 50.0,
               "r_gross": 0.05,
               "week": (dt.date(2020, 1, 6) + dt.timedelta(weeks=i % 200)).isoformat(),
               "direction": "bearish" if i % 3 == 0 else "bullish", "horizon": "2w",
               "risk_reward_ratio": 2.0, "stop_atr": stop_atr,
               "atr_pct": round(1.9 / stop_atr, 6) if atr else None,
               "stop_clamped": i % 2 == 0}
        if live:
            row.update(opened_at="2026-11-03T14:30:00+00:00",
                       closed_at=f"2026-11-0{3 + i % 2}T20:00:00+00:00",
                       strategy="Fibonacci" if i % 2 else "FVG")
        rows.append(row)
    return rows


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)


def _report(train=None, live=None) -> dict:
    return ea.build_stop_width_report(
        stop_width_rows(800) if train is None else train,
        stop_width_rows(120, live=True) if live is None else live,
        seed=42, generated_at=STAMP)


# --- path and constants ---------------------------------------------------------

def test_the_report_path_is_its_own_file_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    assert ea.stop_width_report_path() == tmp_path / "reports" / "stop-width-attribution.json"
    assert ea.stop_width_report_path().name != Path(store.REPORT_PATH).name
    assert ea.STUDY_ID == "v226-stop-width"


def test_the_run_sidecar_path_matches_the_replay_script():
    sys.path.insert(0, str(REPO / "scripts" / "backtest"))
    import run_backtest_range as rr
    assert ea._run_sidecar_of("x/rows.jsonl") == rr._run_sidecar_path("x/rows.jsonl")


# --- build_stop_width_report ----------------------------------------------------

def test_the_report_has_the_contract_shape():
    train = stop_width_rows(800) + [dict(stop_width_rows(1)[0], stop_atr=None)]
    live = stop_width_rows(120, live=True)
    report = ea.build_stop_width_report(train, live, seed=42, generated_at=STAMP)
    assert list(report) == REPORT_KEYS
    assert report["generated_at"] == STAMP and report["study"] == ea.STUDY_ID
    assert report["seed"] == 42 and report["provenance"] == {}
    groups = ea.stop_width_groups(train, live)
    assert report["edges"] == groups["edges"] == ea.frozen_edges(train, "stop_atr")
    assert report["labels"] == groups["labels"]
    assert report["verdict"] == ea.stop_width_verdict(groups["train"], seed=42)
    assert report["disclosures"] == ea.stop_width_disclosures(groups)
    assert report["disclosures"]["train"]["unknown"] == 1
    json.dumps(report)                                   # plain JSON types only


def test_generated_at_defaults_to_now_in_utc():
    report = ea.build_stop_width_report(stop_width_rows(80), [], seed=42)
    assert report["generated_at"].endswith("+00:00")


def test_the_verdict_and_edges_read_train_only():
    train = stop_width_rows(800)
    quiet = _report(train=train, live=[])
    loud = _report(train=train, live=stop_width_rows(400, live=True))
    assert quiet["verdict"] == loud["verdict"]
    assert quiet["edges"] == loud["edges"]
    assert quiet["verdict"]["verdict"] in ea.STUDY_VERDICTS


def test_a_perfectly_collinear_atr_pct_raises_the_volatility_note():
    assert _report(train=stop_width_rows(160))["volatility_note"] is True
    assert _report(train=stop_width_rows(160, atr=False))["volatility_note"] is False


@pytest.mark.parametrize(("rho", "flag"),
                         [(0.8, True), (-0.8, True), (0.7999, False), (-0.7999, False),
                          (None, False)])
def test_the_volatility_note_boundary_is_inclusive(monkeypatch, rho, flag):
    real = ea.stop_width_disclosures

    def fake(groups):
        out = real(groups)
        out["train"]["rho"] = rho
        out["live"]["rho"] = 0.99                        # live never sets the note
        return out

    monkeypatch.setattr(ea, "stop_width_disclosures", fake)
    assert _report(train=stop_width_rows(80), live=[])["volatility_note"] is flag


# --- run_stop_width -------------------------------------------------------------

def _stub_loaders(monkeypatch, train, live):
    monkeypatch.setattr(ea, "load_stop_width_train_rows", lambda path: train)
    monkeypatch.setattr(ea, "load_stop_width_live_rows", lambda: live)


def _forbid_v146_writes(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the stop-width study must never write the v146 report")

    monkeypatch.setattr(ea, "write_latest", refuse)
    monkeypatch.setattr(store, "write_latest", refuse)


def _files(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_run_writes_only_its_own_report_and_quotes_both_sidecars(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    _forbid_v146_writes(monkeypatch)
    _stub_loaders(monkeypatch, stop_width_rows(160), stop_width_rows(40, live=True))
    train = tmp_path / "rows.jsonl"
    train.write_text('{"ticker": "AAA"}\n', encoding="utf-8")
    Path(str(train) + ".run.json").write_text(json.dumps({"git_head": "abc"}), encoding="utf-8")
    Path(str(train) + ".provenance.json").write_text(json.dumps({"data_source": "alpaca"}),
                                                     encoding="utf-8")
    report = ea.run_stop_width(train, seed=7)
    assert _files(data) == ["reports/stop-width-attribution.json"]
    target = data / "reports" / "stop-width-attribution.json"
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(json.dumps(report))
    prov = report["provenance"]
    assert list(prov) == PROVENANCE_KEYS
    assert prov["train_rows"]["path"] == str(train) and prov["train_rows"]["rows"] == 160
    assert len(prov["train_rows"]["sha256"]) == 64
    assert prov["run_sidecar"] == {"git_head": "abc"}
    assert prov["store_provenance"] == {"data_source": "alpaca"}
    assert prov["live_fills_include_frictions"] is ea.LIVE_FILLS_INCLUDE_FRICTIONS
    assert list(prov["frictions"]) == ["slippage_bps", "commission_r"]
    assert prov["n_resamples"] == 200 and report["seed"] == 7


def test_missing_sidecars_are_none_and_no_write_writes_nothing(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    _forbid_v146_writes(monkeypatch)
    _stub_loaders(monkeypatch, stop_width_rows(80), [])
    train = tmp_path / "rows.jsonl"
    train.write_text("\n", encoding="utf-8")
    report = ea.run_stop_width(train, write=False)
    assert report["seed"] == ea.WEEK_BOOTSTRAP_SEED
    assert report["provenance"]["run_sidecar"] is None
    assert report["provenance"]["store_provenance"] is None
    assert _files(data) == []
