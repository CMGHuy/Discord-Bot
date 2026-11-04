"""v200 Part 2: the stall exclusion applied in the report -- excluded trades
leave cells, complements, tallies, give-back and the pooled header; one line reports them."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .test_book_autopsy import FAST, _files, _today_sectors, report, rows, script  # noqa: F401
from autopsy import exclusions  # noqa: E402  (scripts/reports is on sys.path via test_book_autopsy)

GONE = ("T1", "T3")     # T1 a win at +1.5 R, T3 a loss at -1.0 R (test_book_autopsy._trade)


def _exclusions(tmp_path: Path, ids=GONE) -> Path:
    path = tmp_path / "exclusions.json"
    path.write_text(json.dumps({"stall_test": {
        "reason": "test", "rule": "test",
        "windows": [{"start": "2026-08-03T16:18:02Z", "end": "2026-08-04T18:55:15Z"}],
        "trade_ids": list(ids)}}), encoding="utf-8")
    return path


def _without(rows_csv: Path, ids) -> Path:
    with rows_csv.open(encoding="utf-8", newline="") as fh:
        records = [r for r in csv.DictReader(fh) if r["trade_id"] not in ids]
    out = rows_csv.with_name("rows_without.csv")
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows.EXPORT_COLUMNS))
        writer.writeheader()
        writer.writerows(records)
    return out


def _report(rows_csv, rej_csv, bars_dir, exclusions_path):
    return report.build_report(rows.load_rows(rows_csv), rows.load_rejections(rej_csv),
                               bars_dir=bars_dir, n_resamples=200, seed=42, balance=10_000.0,
                               exclusions_path=exclusions_path)


def test_excluding_by_file_equals_deleting_the_rows(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    excluded = _report(rows_csv, rej_csv, bars_dir, _exclusions(tmp_path))
    deleted = _report(_without(rows_csv, GONE), rej_csv, bars_dir, None)
    assert excluded["cells"] == deleted["cells"]
    assert excluded["tallies"] == deleted["tallies"]
    assert excluded["giveback"] == deleted["giveback"]
    for key in ("n", "pooled_net_expr", "pooled_win_rate", "window", "cells_tested",
                "bar_covered_n"):
        assert excluded["header"][key] == deleted["header"][key], key
    assert excluded["header"]["n"] == 46
    assert set(excluded) == {"header", "cells", "tallies", "giveback"}


def test_no_cut_ever_sees_an_excluded_trade(tmp_path, monkeypatch):
    seen = set()
    real = report.cut_cells

    def spy(cut, trades, key, **kw):
        seen.update(t.trade_id for t in trades)
        return real(cut, trades, key, **kw)

    monkeypatch.setattr(report, "cut_cells", spy)
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    _report(rows_csv, rej_csv, bars_dir, _exclusions(tmp_path))
    assert seen and not seen & set(GONE)


def test_the_header_and_markdown_carry_the_stall_line(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    path = _exclusions(tmp_path)
    data = _report(rows_csv, rej_csv, bars_dir, path)
    assert data["header"]["stall_exclusions"] == [
        {"key": "stall_test", "n": 2, "gross_expr": 0.25, "worst_r": -1.0}]
    assert data["header"]["input_fingerprints"][str(path.resolve())] == \
        hashlib.sha256(path.read_bytes()).hexdigest()
    md = report.render_markdown(data)
    assert "- stall exclusion stall_test: N 2, gross ExpR 0.250, worst R -1.000" in md.splitlines()
    assert len(md.splitlines()) <= report.MD_MAX_LINES


def test_an_exclusion_matching_nothing_reports_zero(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    data = _report(rows_csv, rej_csv, bars_dir, _exclusions(tmp_path, ids=("NOPE",)))
    assert data["header"]["stall_exclusions"] == [
        {"key": "stall_test", "n": 0, "gross_expr": None, "worst_r": None}]
    assert data["header"]["n"] == 48
    assert "- stall exclusion stall_test: N 0, gross ExpR n/a, worst R n/a" in \
        report.render_markdown(data)


def test_no_exclusions_path_means_no_line_and_no_manifest_entry(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    data = _report(rows_csv, rej_csv, bars_dir, None)
    assert data["header"]["stall_exclusions"] == []
    assert "stall exclusion" not in report.render_markdown(data)


def test_the_default_build_applies_the_committed_file(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    data = report.build_report(rows.load_rows(rows_csv), rows.load_rejections(rej_csv),
                               bars_dir=bars_dir, n_resamples=200, seed=42, balance=10_000.0)
    [line] = data["header"]["stall_exclusions"]
    assert line["key"] == "stall_2026_08"
    assert str(exclusions.EXCLUSIONS_PATH.resolve()) in data["header"]["input_fingerprints"]


def test_markdown_from_an_older_report_without_the_key_still_renders():
    data = {"header": {"window": ["2026-01-01", "2026-02-01"], "n": 0, "bar_covered_n": 0,
                       "pooled_net_expr": None, "pooled_win_rate": None,
                       "net_of_frictions": "modelled", "cells_tested": 0, "resamples": 200,
                       "seed": 42, "notes": []},
            "cells": [], "tallies": [], "giveback": {"n": 0, "mean": None, "median": None}}
    assert "stall exclusion" not in report.render_markdown(data)


def test_the_cli_prints_the_stall_line_and_can_switch_it_off(tmp_path, capsys):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    base = [str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir),
            "--out-dir", str(tmp_path / "out"), "--date", "2026-10-15", *FAST]
    assert script.main(base + ["--exclusions", str(_exclusions(tmp_path))]) == 0
    assert "stall exclusion stall_test: N 2" in capsys.readouterr().out
    assert script.main(base + ["--no-exclusions"]) == 0
    assert "stall exclusion" not in capsys.readouterr().out


def test_apply_exclusions_keeps_plan_rows_and_order(tmp_path):
    plan = rows.BookRow(row_kind="plan", plan_id="T1")
    a = rows.BookRow(row_kind="trade", trade_id="T1")
    b = rows.BookRow(row_kind="trade", trade_id="T2")
    [ex] = exclusions.load_exclusions(_exclusions(tmp_path, ids=("T1",)))
    kept, gone = exclusions.apply_exclusions([a, plan, b], [ex])
    assert kept == [plan, b] and gone == [a]
    assert exclusions.apply_exclusions([a, b], []) == ([a, b], [])
