"""V192-19: book_autopsy --entry-type keeps one entry family's rows (the v192 pre-TRAIN
market-only disclosure); without the flag the report and its file names are unchanged."""
import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from tests.scout.test_book_autopsy import EXPIRED_PLAN, FAST, _trade, cuts, rows, script

TYPES = ("market", "stop_entry", "limit")


@pytest.fixture(autouse=True)
def _today_sectors(monkeypatch):
    monkeypatch.setattr(cuts, "load_sector_map", lambda: {"AAA": "Technology", "BBB": "Energy"})


def _files(tmp_path: Path, n: int = 90):
    records = [dict(_trade(i, ("AAA", "BBB")[i % 2]), entry_type=TYPES[i % 3]) for i in range(n)]
    records.append(EXPIRED_PLAN)                                       # a stop_entry plan row
    rows_csv = tmp_path / "rows.csv"
    with rows_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows.EXPORT_COLUMNS))
        writer.writeheader()
        for record in records:
            writer.writerow({c: record.get(c, "") for c in rows.EXPORT_COLUMNS})
    rej_csv = tmp_path / "rejections.csv"
    rej_csv.write_text("date,reason,count\n2026-03-02,risk_cap,4\n", encoding="utf-8")
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-12-01", "2026-04-30")]
    lines = ["Date,Open,High,Low,Close,Volume"] + [f"{d},100,100.5,99.5,100,1000000" for d in days]
    (bars_dir / "AAA.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows_csv, rej_csv, bars_dir


def _run(tmp_path, *extra):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    out = tmp_path / "results"
    code = script.main([str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir), "--out-dir", str(out),
                        "--date", "2026-10-24", *FAST, *extra])
    return code, out


def test_filter_entry_type_keeps_one_family_and_none_keeps_all(tmp_path):
    loaded = rows.load_rows(_files(tmp_path)[0])
    assert script.ENTRY_TYPES == TYPES
    assert script.filter_entry_type(loaded, None) == loaded
    market = script.filter_entry_type(loaded, "market")
    assert len(market) == 30 and {r.entry_type for r in market} == {"market"}
    assert len(script.filter_entry_type(loaded, "stop_entry")) == 31      # 30 trades + the plan row
    assert len(script.filter_entry_type(loaded, "limit")) == 30


@pytest.mark.parametrize("entry_type", [None, *TYPES])
def test_an_empty_book_remains_empty(entry_type):
    assert script.filter_entry_type([], entry_type) == []


def test_the_market_only_report_is_written_under_its_own_name(tmp_path):
    code, out = _run(tmp_path, "--entry-type", "market")
    assert code == 0
    data = json.loads((out / "2026-10-24-book-autopsy-market.json").read_text(encoding="utf-8"))
    assert data["header"]["n"] == 30 and data["header"]["entry_type_filter"] == "market"
    assert any("entry-type filter: market" in note for note in data["header"]["notes"])
    md = (out / "2026-10-24-book-autopsy-market.md").read_text(encoding="utf-8")
    assert "- Note: entry-type filter: market" in md
    assert not (out / "2026-10-24-book-autopsy.json").exists()


def test_without_the_flag_nothing_changes(tmp_path):
    code, out = _run(tmp_path)
    assert code == 0
    data = json.loads((out / "2026-10-24-book-autopsy.json").read_text(encoding="utf-8"))
    assert data["header"]["n"] == 90 and "entry_type_filter" not in data["header"]
    assert not any("entry-type filter" in note for note in data["header"]["notes"])


def test_an_unknown_entry_type_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path, "--entry-type", "moc")
