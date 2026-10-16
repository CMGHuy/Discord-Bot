"""v161 TS7: the autopsy report and CLI end to end on fixture CSVs (200 resamples)."""
from __future__ import annotations

import csv
import importlib.util
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import bars, cuts, exits, report, rows  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "book_autopsy_script", ROOT / "scripts" / "reports" / "book_autopsy.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

CUT_NAMES = {
    "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday", "friday_entry",
    "weekend_hold", "earnings_proximity", "opex_week", "fomc_proximity", "atr_pct_bucket",
    "session_bucket", "alert_hour", "open_gap_bucket", "gapped_through_entry",
    "dollar_volume_bucket", "near_stop_reversal", "exit_reason", "near_tp_close",
    "gap_through_stop", "holding_bucket"}
FAST = ["--resamples", "200", "--seed", "42"]


@pytest.fixture(autouse=True)
def _today_sectors(monkeypatch):
    monkeypatch.setattr(cuts, "load_sector_map", lambda: {"AAA": "Technology", "BBB": "Energy"})


def _trade(i: int, ticker: str) -> dict:
    plan_day = date(2026, 1, 5) + timedelta(weeks=i % 12)
    win = i % 3 != 0
    return {
        "row_kind": "trade", "trade_id": f"T{i}", "plan_id": f"P{i}", "ticker": ticker,
        "strategy": "RSI" if i % 2 else "MACD", "horizon": "2w", "direction": "bullish",
        "plan_created_at": f"{plan_day} 00:00:00+00",
        "plan_first_status_at": f"{plan_day}T13:00:00+00:00", "plan_status": "CLOSED",
        "entry_type": "stop_entry", "expiry_bars": "2", "planned_entry": "100",
        "opened_at": f"{plan_day + timedelta(days=1)}T15:00:00+00:00", "entry": "100",
        "stop_loss": "98", "take_profit": "103",
        "closed_at": f"{plan_day + timedelta(days=3)}T20:00:00+00:00",
        "exit_price": "103" if win else "98", "close_reason": "tp1_runner_tp2" if win else "loss",
        "outcome": "win" if win else "loss", "r_realized": "1.5" if win else "-1.0",
        "mfe_r": "2.0" if win else "0.3", "holding_days": "3", "stop_width_atr": "1.0",
        "atr_pct": "2.0", "regime2_state": "bull_quiet"}


EXPIRED_PLAN = {
    "row_kind": "plan", "plan_id": "PX", "ticker": "AAA", "strategy": "RSI", "horizon": "2w",
    "direction": "bullish", "plan_created_at": "2026-02-02 00:00:00+00",
    "plan_status": "CANCELLED", "plan_status_reason": "expired", "entry_type": "stop_entry",
    "expiry_bars": "2", "planned_entry": "100"}


def _files(tmp_path: Path, tickers=("AAA", "BBB"), n: int = 48):
    tmp_path.mkdir(parents=True, exist_ok=True)
    records = [_trade(i, tickers[i % len(tickers)]) for i in range(n)] + [EXPIRED_PLAN]
    rows_csv = tmp_path / "rows.csv"
    with rows_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows.EXPORT_COLUMNS))
        writer.writeheader()
        for record in records:
            writer.writerow({c: record.get(c, "") for c in rows.EXPORT_COLUMNS})
    rej_csv = tmp_path / "rejections.csv"
    rej_csv.write_text("date,reason,count\n2026-03-02,risk_cap,4\n"
                       "2026-03-03,stop_beyond_confluence_ceiling,1\n", encoding="utf-8")
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-12-01", "2026-04-30")]
    lines = ["Date,Open,High,Low,Close,Volume"] + [f"{d},100,100.5,99.5,100,1000000" for d in days]
    (bars_dir / "AAA.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows_csv, rej_csv, bars_dir


def _build(tmp_path, **kw):
    rows_csv, rej_csv, bars_dir = _files(tmp_path, **kw)
    return report.build_report(rows.load_rows(rows_csv), rows.load_rejections(rej_csv),
                               bars_dir=bars_dir, n_resamples=200, seed=42, balance=10_000.0)


def test_the_cli_writes_json_and_markdown_named_by_date(tmp_path, capsys):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    out = tmp_path / "results"
    code = script.main([str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir),
                        "--out-dir", str(out), "--date", "2026-10-15", *FAST])
    assert code == 0
    assert "2026-10-15-book-autopsy.json" in capsys.readouterr().out
    data = json.loads((out / "2026-10-15-book-autopsy.json").read_text(encoding="utf-8"))
    md = (out / "2026-10-15-book-autopsy.md").read_text(encoding="utf-8")
    assert set(data) == {"header", "cells", "tallies", "giveback"}
    assert len(md.splitlines()) <= report.MD_MAX_LINES
    for text in ("Cells tested:", "Net of frictions: modelled", "exploratory", "2026-01-08"):
        assert text in md


def test_the_header_carries_window_n_flags_and_the_cells_tested_count(tmp_path):
    data = _build(tmp_path)
    h = data["header"]
    assert h["window"] == ["2026-01-08", "2026-03-26"]
    assert h["n"] == 48 and h["bar_covered_n"] == 24
    assert (h["net_of_frictions"], h["resamples"], h["seed"]) == ("modelled", 200, 42)
    assert h["pooled_win_rate"] == pytest.approx(32 / 48, abs=1e-4)
    assert h["cells_tested"] == sum(1 for c in data["cells"] if c["p"] is not None) > 0
    assert any("CPI" in note for note in h["notes"])
    assert any("modelled" in note for note in h["notes"])


def test_every_cell_is_well_formed_and_bh_covers_all_of_them(tmp_path):
    data = _build(tmp_path)
    cut_names = {c["cut"] for c in data["cells"]}
    assert cut_names <= CUT_NAMES
    assert {"strategy_horizon", "ticker", "exit_reason", "near_tp_close", "holding_bucket",
            "open_gap_bucket"} <= cut_names
    assert all(c["id"] == f"{c['cut']}={c['value']}" for c in data["cells"])
    assert all((c["q"] is None) == (c["p"] is None) for c in data["cells"])
    assert data["giveback"]["n"] == 48


def test_bar_cells_carry_bar_covered_n(tmp_path):
    data = _build(tmp_path)
    bar_names = {name for name, _ in bars.bar_cuts()}
    assert all(c["bar_covered_n"] == 24 for c in data["cells"] if c["cut"] in bar_names)
    assert all(c["bar_covered_n"] is None for c in data["cells"] if c["cut"] == "strategy_horizon")


def test_stop_cells_carry_the_dollar_view_and_report_has_supply_tallies(tmp_path):
    data = _build(tmp_path)
    stop = [c for c in data["cells"] if c["cut"] == "exit_reason"]
    assert stop
    assert all({"mean_stop_atr", "dollar_loss_at_2pct", "mean_overshoot_r"} <= set(c["extra"])
               for c in stop)
    tallies = {t["id"]: t for t in data["tallies"]}
    assert tallies["fill_status=expired_unfilled"]["count"] == 1
    assert tallies["rejection_reason=risk_cap"]["count"] == 4


def test_two_runs_with_one_seed_are_identical(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)

    def run():
        data = report.build_report(rows.load_rows(rows_csv), rows.load_rejections(rej_csv),
                                   bars_dir=bars_dir, n_resamples=200, seed=42, balance=10_000.0)
        return json.dumps(data, sort_keys=True)

    assert run() == run()


def test_many_tickers_still_fit_the_markdown_budget(tmp_path):
    data = _build(tmp_path, tickers=tuple(f"T{k:03d}" for k in range(120)), n=240)
    assert len(report.render_markdown(data).splitlines()) <= report.MD_MAX_LINES


def _synthetic(n_cells: int) -> dict:
    def cell(i):
        return {"id": f"ticker=T{i}", "cut": "ticker", "value": f"T{i}", "n": 40, "weeks": 10,
                "win_rate": 0.5, "net_expr": 0.1, "gross_expr": 0.12, "delta": 0.05,
                "ci": [0.01, 0.09], "p": 0.04, "q": 0.08, "thin": False, "bar_covered_n": None,
                "extra": {"tickers": 1, "top_ticker_share": 1.0}}
    header = {"window": ["2026-01-08", "2026-03-26"], "n": 40, "pooled_net_expr": 0.1,
              "pooled_win_rate": 0.5, "net_of_frictions": "modelled", "cells_tested": n_cells,
              "bar_covered_n": 0, "resamples": 200, "seed": 42, "notes": ["a note"]}
    thin = dict(cell(-1), id="ticker=THIN", value="THIN", thin=True)
    return {"header": header, "cells": [cell(i) for i in range(n_cells)] + [thin],
            "tallies": [], "giveback": {"n": 0, "mean": None, "median": None}}


def test_render_markdown_cuts_the_cell_table_to_the_line_budget():
    md = report.render_markdown(_synthetic(300))
    assert len(md.splitlines()) <= report.MD_MAX_LINES
    assert "more cells in the JSON" in md
    line = next(x for x in md.splitlines() if x.startswith("| ticker=T0 |"))
    assert "+0.050 [0.010, 0.090]" in line and "| 0.080 |" in line
    assert "| ticker=THIN |" not in md
    assert "ticker 1" in md   # the thin count line


def test_markdown_keeps_pipe_delimited_cell_ids_in_one_column():
    data = _synthetic(1)
    data["cells"][0].update(id="strategy_horizon=RSI|2w", cut="strategy_horizon", value="RSI|2w")
    md = report.render_markdown(data)
    line = next(line for line in md.splitlines() if line.startswith("| strategy_horizon="))
    assert line == (
        "| strategy_horizon=RSI\\|2w | 40 | 10 | 50.0% | 0.100 | 0.120 | "
        "+0.050 [0.010, 0.090] | 0.080 | tickers 1; top share 100.0% |")
    assert data["cells"][0]["id"] == "strategy_horizon=RSI|2w"


@pytest.mark.parametrize("reason, outcome", [
    ("loss", "loss"), ("stop", "loss"), ("auto (price monitor)", "loss"),
    ("auto (price monitor)", "win"), ("tp1", "win"), ("", "loss"), ("auto (near-tp stall)", "win")])
def test_the_bar_and_exit_modules_share_one_stop_exit_rule(reason, outcome):
    row = rows.BookRow(row_kind="trade", close_reason=reason, outcome=outcome)
    assert bars._stopped_out(row) is exits.is_stop_exit(row)


def test_cli_records_input_hashes_effective_frictions_and_resolved_invocation(tmp_path, monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 17.0)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 2.5)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 250.0)
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    (bars_dir / "UNUSED.csv").write_text("not consumed", encoding="utf-8")
    out = tmp_path / "results"
    argv = [str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir),
            "--out-dir", str(out), "--date", "2026-10-15", "--balance", "25000", *FAST]
    assert script.main(argv) == 0
    data = json.loads((out / "2026-10-15-book-autopsy.json").read_text(encoding="utf-8"))
    header = data["header"]
    assert header["frictions"] == {"slippage_bps": 17.0, "commission_per_trade": 2.5,
                                    "commission_risk_basis": 250.0, "min_risk_fraction": 0.001}
    expected = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (rows_csv, rej_csv, bars_dir / "AAA.csv")}
    assert header["input_fingerprints"] == expected
    assert header["invocation"]["command"][2:] == argv
    assert header["invocation"]["options"]["balance"] == 25000.0
    assert header["invocation"]["options"]["seed"] == 42
    md = (out / "2026-10-15-book-autopsy.md").read_text(encoding="utf-8")
    assert "SHA-256" in md and "17.0" in md and "Invocation:" in md
    assert len(md.splitlines()) <= report.MD_MAX_LINES


def test_report_records_frictions_for_direct_builds(tmp_path):
    header = _build(tmp_path)["header"]
    assert set(header["frictions"]) == {"slippage_bps", "commission_per_trade",
                                         "commission_risk_basis", "min_risk_fraction"}


@pytest.mark.parametrize("mapping, expected", [
    ({"AAA": "Technology", "UNUSED": "Energy"}, {"AAA": "Technology", "BBB": None}),
    ({"AAA": "Financials"}, {"AAA": "Financials", "BBB": None}),
    ({}, {"AAA": None, "BBB": None}),
])
def test_sector_snapshot_records_exact_mapping_used_once_for_the_cuts(
        tmp_path, monkeypatch, mapping, expected):
    available = iter([mapping])  # a second map load must not silently change the snapshot
    monkeypatch.setattr(cuts, "load_sector_map", lambda: next(available))
    data = _build(tmp_path)
    assert data["header"]["sector_map"] == expected
    sector_values = {cell["value"] for cell in data["cells"] if cell["cut"] == "sector_today"}
    assert sector_values == {sector for sector in expected.values() if sector is not None}
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True).encode("utf-8")).hexdigest()
    md = report.render_markdown(data)
    assert f"Sector map snapshot SHA-256: {digest}" in md
    assert len(md.splitlines()) <= report.MD_MAX_LINES
