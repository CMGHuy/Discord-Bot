"""v228 operator backfill: per-ticker checkpoints, restart skips finished
tickers, a half-done ticker is redone, the report line is printed and saved."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from swingbot.core.analytics.excursion_upgrade import UpgradeReport

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "backfill_excursions.py"

_spec = importlib.util.spec_from_file_location("backfill_excursions", SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)


def _pairs(n):
    return [({"trade_id": f"t{i}", "excursion_source": "daily"}, {"id": f"t{i}"})
            for i in range(n)]


@pytest.fixture
def fake_pass(monkeypatch):
    """pending_by_ticker returns three tickers; upgrade_ticker upgrades every
    pair to 5min and records the order it was called in."""
    state = {"pending": {"AAPL": _pairs(2), "GC=F": _pairs(1), "MSFT": _pairs(3)},
             "calls": [], "fail_on": None, "since": []}

    def pending(since, until=None):
        state["since"].append(since)
        return {t: list(p) for t, p in state["pending"].items()}

    def upgrade(ticker, pairs, report, *, base_dir=None, deadline=None):
        if ticker == state["fail_on"]:
            raise KeyboardInterrupt("operator stopped the run")
        state["calls"].append((ticker, base_dir, deadline))
        report.read += len(pairs)
        report.upgraded["5min"] = report.upgraded.get("5min", 0) + len(pairs)
        return True

    monkeypatch.setattr(bf, "pending_by_ticker", pending)
    monkeypatch.setattr(bf, "upgrade_ticker", upgrade)
    return state


def test_a_fresh_run_upgrades_every_ticker_and_removes_its_checkpoints(
        fake_pass, tmp_path, capsys):
    ckpt = tmp_path / "ckpt"
    report = bf.run(ckpt, base_dir="md")
    assert [c[0] for c in fake_pass["calls"]] == ["AAPL", "GC=F", "MSFT"]
    assert all(c[1] == "md" and c[2] is None for c in fake_pass["calls"])
    assert report.read == 6 and report.upgraded["5min"] == 6
    assert not ckpt.exists()
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "resuming: 0/3 tickers restored"


def test_each_finished_ticker_writes_a_checkpoint(fake_pass, tmp_path):
    ckpt = tmp_path / "ckpt"
    fake_pass["fail_on"] = "MSFT"
    with pytest.raises(KeyboardInterrupt):
        bf.run(ckpt)
    files = sorted(p.name for p in ckpt.glob("*.json"))
    assert files == ["AAPL.json", "GC_F.json"]
    blob = json.loads((ckpt / "GC_F.json").read_text(encoding="utf-8"))
    assert blob["fingerprint"] == bf.FINGERPRINT
    assert blob["ticker"] == "GC=F"
    assert blob["counts"]["read"] == 1 and blob["counts"]["upgraded"]["5min"] == 1
    assert not list(ckpt.glob("*.tmp"))


def test_a_restart_skips_finished_tickers_and_redoes_the_interrupted_one(
        fake_pass, tmp_path, capsys):
    ckpt = tmp_path / "ckpt"
    fake_pass["fail_on"] = "MSFT"
    with pytest.raises(KeyboardInterrupt):
        bf.run(ckpt)
    capsys.readouterr()
    fake_pass["fail_on"] = None
    fake_pass["calls"].clear()

    report = bf.run(ckpt)

    assert [c[0] for c in fake_pass["calls"]] == ["MSFT"]
    assert report.read == 6 and report.upgraded["5min"] == 6   # restored + redone
    assert capsys.readouterr().out.splitlines()[0] == "resuming: 2/3 tickers restored"
    assert not ckpt.exists()


def test_a_restored_ticker_no_longer_pending_still_counts(fake_pass, tmp_path, capsys):
    """After a first run upgraded all of AAPL to 5min, pending_by_ticker no
    longer returns AAPL; its checkpoint must still be restored and counted."""
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    done = UpgradeReport()
    done.read, done.upgraded = 2, {"5min": 2}
    (ckpt / "AAPL.json").write_text(json.dumps(
        {"fingerprint": bf.FINGERPRINT, "ticker": "AAPL", "counts": done.as_dict()}),
        encoding="utf-8")
    del fake_pass["pending"]["AAPL"]

    report = bf.run(ckpt)

    assert [c[0] for c in fake_pass["calls"]] == ["GC=F", "MSFT"]
    assert report.read == 6
    assert capsys.readouterr().out.splitlines()[0] == "resuming: 1/3 tickers restored"


def test_checkpoints_from_other_code_or_corrupt_files_are_redone(fake_pass, tmp_path):
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    (ckpt / "AAPL.json").write_text(json.dumps(
        {"fingerprint": "older-code", "ticker": "AAPL", "counts": {"read": 99}}),
        encoding="utf-8")
    (ckpt / "MSFT.json").write_text("{not json", encoding="utf-8")
    (ckpt / "GC_F.json").write_text(json.dumps({"fingerprint": bf.FINGERPRINT}),
                                    encoding="utf-8")   # no ticker / counts

    report = bf.run(ckpt)

    assert [c[0] for c in fake_pass["calls"]] == ["AAPL", "GC=F", "MSFT"]
    assert report.read == 6


def test_an_empty_book_prints_zero_and_a_report_line(fake_pass, tmp_path, capsys):
    fake_pass["pending"] = {}
    report = bf.run(tmp_path / "ckpt")
    assert report.read == 0 and fake_pass["calls"] == []
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "resuming: 0/0 tickers restored"
    assert out[-1].startswith("excursion upgrade:")


def test_since_is_passed_through(fake_pass, tmp_path):
    bf.run(tmp_path / "ckpt", since="2026-10-01T00:00:00+00:00")
    assert fake_pass["since"] == ["2026-10-01T00:00:00+00:00"]


def test_main_writes_the_report_file_and_prints_the_line_last(fake_pass, tmp_path, capsys):
    ckpt, report_file = tmp_path / "ckpt", tmp_path / "out" / "report.txt"
    code = bf.main(["--checkpoint-dir", str(ckpt), "--report-file", str(report_file),
                    "--since", "2026-06-23"])
    assert code == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1].startswith("excursion upgrade:")
    assert report_file.read_text(encoding="utf-8").strip() == out[-1]
    assert fake_pass["since"] == ["2026-06-23"]


def test_cli_defaults_sit_under_logs():
    args = bf.parse_args([])
    assert args.checkpoint_dir == pathlib.Path("logs/backfill_excursions.ckpt")
    assert args.report_file == pathlib.Path("logs/backfill_excursions.report.txt")
    assert args.since is None


@pytest.mark.parametrize("ticker,name", [
    ("AAPL", "AAPL.json"), ("GC=F", "GC_F.json"), ("^VIX", "_VIX.json"),
    ("BRK-B", "BRK-B.json"), ("BTC/USD", "BTC_USD.json"),
])
def test_checkpoint_filenames_are_safe(ticker, name):
    assert bf.checkpoint_name(ticker) == name
