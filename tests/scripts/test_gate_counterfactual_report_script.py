"""v147 V147-15: scripts/reports/gate_counterfactual_report.py stays a thin wrapper over build_report."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import gate_counterfactual_report as gcr
from swingbot.core.backtesting.blocked_recorder import gate_row, write_gate_rows

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("gcr_script", ROOT / "scripts" / "reports" / "gate_counterfactual_report.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(gcr, "BOOTSTRAP_RESAMPLES", 200)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))


def _train_file(tmp_path) -> Path:
    rows = [gate_row(population="train", arm="blocked", source="confluence", ticker=f"T{i}", strategy="Fibonacci",
                     horizon="2w", direction="bullish", signal_date=f"2021-03-{i + 1:02d}", gate="plan_rejected",
                     reason="risk_cap", margin=0.3, cf_status="filled", cf_r=-1.0, win=False,
                     planned_loss_pct=2.3, expiry_bars=0)
            for i in range(3)]
    path = tmp_path / "v147-blocked-confluence.jsonl"
    write_gate_rows(rows, path)
    return path


def test_a_train_only_reading_prints_cells_rows_and_limitations_without_writing(tmp_path, capsys):
    out = tmp_path / "out.json"
    code = script.main(["--train", str(_train_file(tmp_path)), "--no-live", "--no-write", "--json", str(out)])
    printed = capsys.readouterr().out
    assert code == 0
    assert "WAITING (3/30" in printed and "no TRAIN population" in printed
    assert "over-cap" in printed and "-1.0R" in printed
    assert "reading only" in printed                             # --no-write is never a verdict of record
    assert json.loads(out.read_text(encoding="utf-8"))["cells"]
    assert gcr.load_report() is None                             # nothing written


def test_a_written_run_persists_what_load_report_reads(tmp_path, capsys):
    assert script.main(["--train", str(_train_file(tmp_path)), "--no-live"]) == 0
    loaded = gcr.load_report()
    assert loaded is not None and [r["population"] for r in loaded["rows"]] == ["train"]


def test_a_verdict_line_shows_the_reading_and_the_record():
    cell = {"gate": "risk_cap", "population": "train", "verdict": "GATE COSTS", "n": 41, "note": None,
            "in_sample": False, "latest": {"difference": 0.21, "ci_low": 0.05, "ci_high": 0.4, "q": 0.03, "p": 0.006},
            "verdict_of_record": {"verdict": "GATE COSTS", "date": "2026-12-04", "n": 31}}
    (line,) = script.cell_lines({"cells": [cell]})[1:]
    assert "GATE COSTS" in line and "n=41" in line and "+0.21" in line and "q=0.030" in line
    assert "of record: GATE COSTS (2026-12-04, n=31)" in line
