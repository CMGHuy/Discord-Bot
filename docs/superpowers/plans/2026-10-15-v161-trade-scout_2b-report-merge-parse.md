# v161 Trade scout, part 2b: report and CLI, merge parsing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task TS8" -A 300 docs/superpowers/plans/2026-10-15-v161-trade-scout_2b-report-merge-parse.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v161-trade-scout-design.md`](../specs/2026-10-15-v161-trade-scout-design.md) (§ 1 output; § 6 merge; Panel review)
**Bump:** none
**Edge:** none (integrity)
**Index:** [`2026-10-15-v161-trade-scout_0-index.md`](2026-10-15-v161-trade-scout_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts and the task ledger. This file holds ledger part 2's TS7 and TS8: part 2 outgrew the 1500-line cap, so it is split here (TS5 and TS6 stay in `2026-10-15-v161-trade-scout_2-bars-exits-report-merge.md`, whose header conventions — `$WT`, `$R`, the `autopsy` import form, the `_row` helper — apply to this file too).

**Conventions (repeated from part 2):** `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout`, `$R` = the main tree; never `cd`, use `git -C $WT` and absolute paths. The autopsy package is imported as `autopsy` with `scripts/reports` on `sys.path`; its modules import each other relatively. Every `BookRow` field has a default (TS2).

# Phase B (end): report

### Task TS7: Report assembly, Markdown, CLI, quant-engineer review

**Model:** sonnet — wires the finished cut modules into one report and a thin CLI; the statistics live in TS3 and the review step sends lookahead and numerics to `quant-engineer`

**Files:**
- Create: `scripts/reports/autopsy/report.py`
- Create: `scripts/reports/book_autopsy.py`
- Test: `tests/scout/test_book_autopsy.py`

**Interfaces:**
- Consumes: TS2 `load_rows`, `load_rejections`, `closed_trades`, `BookRow`, `RejectionCount`, `EXPORT_COLUMNS`; TS3 `cut_cells`, `apply_bh`, `net_value(trade) -> float`, `CellStats.to_json()`, `Tally.to_json()`; TS4 `categorical_cuts(sector_of)`, `load_sector_map()`, `CUT_NOTES`; TS5 `enrich_with_bars`, `bar_cuts`, `fill_tallies`, `SPLIT_GUARD`, `_stopped_out` (agreement test only); TS6 `exit_cuts`, `STOP_CUTS`, `stop_extra`, `giveback_summary`, `alert_supply_tallies`, `is_stop_exit`. Existing: `swingbot/core/backtesting/instrument/stats.py:21-22 WEEK_BOOTSTRAP_RESAMPLES, WEEK_BOOTSTRAP_SEED`.
- Produces (ledger TS7): `MD_MAX_LINES = 150`; `DEFAULT_BALANCE = 10_000.0`; `build_report(rows, rejections, *, bars_dir, n_resamples, seed, balance) -> dict` in the index's Autopsy JSON shape; `render_markdown(report: dict) -> str`; CLI `python scripts/reports/book_autopsy.py <rows.csv> <rejections.csv> [--bars-dir DIR] [--out-dir docs/superpowers/results] [--date YYYY-MM-DD] [--resamples N] [--seed N] [--balance USD]` writing `<out-dir>/<date>-book-autopsy.json` and `.md`; `main(argv: list[str] | None = None) -> int`. TS9 reads the JSON; TS10/TS11 roles read the Markdown; TS13 runs the CLI.

**Rules this task freezes:**
- Cuts run in the order categorical (TS4), bars (TS5), exits (TS6); **one** `apply_bh` over every cell of the run; `header.cells_tested` is its return value.
- Bar cells set `bar_covered_n` to the run's bar-covered closed-trade count (the Markdown prints it beside the cell N). Cells of a cut in `STOP_CUTS` get `stop_extra(members, balance)` merged into `extra`, where members are the trades whose key text equals the cell value (`;` → `,` as `cut_cells` does).
- Header `window` = first and last `exit_date` of the closed trades; `pooled_net_expr` = mean of `net_value` (net, or gross where net could not be modelled, counted in a note); `pooled_win_rate` = share with `gross_r > 0`; `notes` = the modelled-net note, the bar note, the hour-granularity note, the boundary-5 note, every `CUT_NOTES` entry as `<key>: <text>`, the gross-fallback count when non-zero, and the balance the dollar view uses.
- Markdown (≤ `MD_MAX_LINES`): header block; a table of **non-thin** cells sorted by q, then |Δ|, cut to the line budget with a `- <k> more cells in the JSON` line; one line counting thin cells per cut; give-back; tallies (rejection reasons capped at `REJECTION_LINES = 8`).

- [ ] **Step 1: Write the failing test**

Create `tests/scout/test_book_autopsy.py`:

```python
"""v161 TS7: the autopsy report and CLI end to end on fixture CSVs (200 resamples)."""
from __future__ import annotations

import csv
import importlib.util
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


def test_bar_cells_carry_bar_covered_n_and_stop_cells_the_dollar_view(tmp_path):
    data = _build(tmp_path)
    bar_names = {name for name, _ in bars.bar_cuts()}
    assert all(c["bar_covered_n"] == 24 for c in data["cells"] if c["cut"] in bar_names)
    assert all(c["bar_covered_n"] is None for c in data["cells"] if c["cut"] == "strategy_horizon")
    stop = [c for c in data["cells"] if c["cut"] == "exit_reason"]
    assert stop
    assert all({"mean_stop_atr", "dollar_loss_at_2pct", "mean_overshoot_r"} <= set(c["extra"])
               for c in stop)
    tallies = {t["id"]: t for t in data["tallies"]}
    assert tallies["fill_status=expired_unfilled"]["count"] == 1
    assert tallies["rejection_reason=risk_cap"]["count"] == 4


def test_two_runs_with_one_seed_are_identical(tmp_path):
    first = json.dumps(_build(tmp_path / "a"), sort_keys=True)
    assert json.dumps(_build(tmp_path / "b"), sort_keys=True) == first


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


@pytest.mark.parametrize("reason, outcome", [
    ("loss", "loss"), ("stop", "loss"), ("auto (price monitor)", "loss"),
    ("auto (price monitor)", "win"), ("tp1", "win"), ("", "loss"), ("auto (near-tp stall)", "win")])
def test_the_bar_and_exit_modules_share_one_stop_exit_rule(reason, outcome):
    row = rows.BookRow(row_kind="trade", close_reason=reason, outcome=outcome)
    assert bars._stopped_out(row) is exits.is_stop_exit(row)
```

The fixture's arithmetic: trades `i = 0..47`, plan day = Monday 2026-01-05 + `i % 12` weeks, exit three days later at 20:00 UTC (15:00 ET): first exit 2026-01-08, last 2026-03-26; every third trade (`i % 3 == 0`, 16 trades) loses, so the win rate is 32/48; AAA (even `i`, 24 trades) has bars, BBB none.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py`
Expected: FAIL at collection (`FileNotFoundError` for `book_autopsy.py` from `spec_from_file_location`, or `ImportError: cannot import name 'report'`).

- [ ] **Step 3: Write `scripts/reports/autopsy/report.py`**

```python
"""v161 TS7: assemble the book autopsy -- every cut, one BH pass over all cells,
fill and alert-supply tallies, give-back, header -- and render the Markdown
summary (at most MD_MAX_LINES lines) that is the only thing a generator role reads."""
from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

from . import bars, cuts, exits
from .cells import apply_bh, cut_cells, net_value
from .rows import closed_trades

MD_MAX_LINES = 150
DEFAULT_BALANCE = 10_000.0
REJECTION_LINES = 8
BAR_CUT_NAMES = frozenset(name for name, _ in bars.bar_cuts())
NOTES = (
    "net R is modelled locally (apply_frictions slippage on both fills plus commission_r); "
    "live rows store gross R only",
    f"bar cuts read only --bars-dir; a row is bar-covered when its plan-day close lies within "
    f"{bars.SPLIT_GUARD:.0%} of its planned entry",
    "alert hour has hour granularity: 09:00-09:29 ET counts as the regular session",
    "every row drawn from this report is exploratory: the window overlaps the 2026 holdout "
    "(spec v161 boundary 5)",
)


def _key_text(value) -> str | None:
    return None if value is None else str(value).replace(";", ",")


def _all_cuts(sector_of: dict) -> tuple:
    return (*cuts.categorical_cuts(sector_of), *bars.bar_cuts(), *exits.exit_cuts())


def _decorate(cell, members: list, covered_n: int, balance: float) -> None:
    if cell.cut in BAR_CUT_NAMES:
        cell.bar_covered_n = covered_n
    if cell.cut in exits.STOP_CUTS:
        cell.extra.update(exits.stop_extra(members, balance))


def _cells(trades: list, covered_n: int, sector_of: dict, *, n_resamples: int, seed: int,
           balance: float) -> list:
    out = []
    for name, key in _all_cuts(sector_of):
        for cell in cut_cells(name, trades, key, n_resamples=n_resamples, seed=seed):
            members = [t for t in trades if _key_text(key(t)) == cell.value]
            _decorate(cell, members, covered_n, balance)
            out.append(cell)
    return out


def _notes(trades: list, balance: float) -> list[str]:
    out = list(NOTES)
    out += [f"{key}: {text}" for key, text in sorted(cuts.CUT_NOTES.items())]
    gross_only = sum(1 for t in trades if t.net_r is None)
    if gross_only:
        out.append(f"{gross_only} trades could not be modelled net and count at gross R")
    out.append(f"stop cells price the dollar loss at 2% of {balance:,.0f} USD")
    return out


def _header(trades: list, covered_n: int, tested: int, *, n_resamples: int, seed: int,
            balance: float) -> dict:
    exit_days = sorted(t.exit_date for t in trades if t.exit_date)
    pooled = round(statistics.fmean(net_value(t) for t in trades), 4) if trades else None
    wins = round(sum(1 for t in trades if t.gross_r > 0) / len(trades), 4) if trades else None
    return {"window": [exit_days[0], exit_days[-1]] if exit_days else [None, None],
            "n": len(trades), "pooled_net_expr": pooled, "pooled_win_rate": wins,
            "net_of_frictions": "modelled", "cells_tested": tested, "bar_covered_n": covered_n,
            "resamples": n_resamples, "seed": seed, "notes": _notes(trades, balance)}


def build_report(rows: list, rejections: list, *, bars_dir: Path | None, n_resamples: int,
                 seed: int, balance: float) -> dict:
    """The Autopsy JSON (index § Shared contracts) for one export."""
    covered_n = bars.enrich_with_bars(rows, bars_dir)
    trades = closed_trades(rows)
    cells = _cells(trades, covered_n, cuts.load_sector_map(), n_resamples=n_resamples,
                   seed=seed, balance=balance)
    tested = apply_bh(cells)
    tallies = bars.fill_tallies(rows) + exits.alert_supply_tallies(rows, rejections)
    return {"header": _header(trades, covered_n, tested, n_resamples=n_resamples, seed=seed,
                              balance=balance),
            "cells": [c.to_json() for c in cells],
            "tallies": [t.to_json() for t in tallies],
            "giveback": exits.giveback_summary(trades)}


def _fmt(value, spec: str = ".3f") -> str:
    return "n/a" if value is None else format(value, spec)


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _header_lines(h: dict) -> list[str]:
    w0, w1 = h["window"]
    lines = [f"# Book autopsy, {w0} to {w1}", "",
             f"- Window (first and last exit date): {w0} to {w1}",
             f"- N closed trades: {h['n']}; bar-covered: {h['bar_covered_n']}",
             f"- Pooled net ExpR (modelled): {_fmt(h['pooled_net_expr'])}; "
             f"pooled win rate: {_pct(h['pooled_win_rate'])}",
             f"- Net of frictions: {h['net_of_frictions']}",
             f"- Cells tested: {h['cells_tested']} (one BH pass over all of them); "
             f"bootstrap resamples {h['resamples']}, seed {h['seed']}"]
    return lines + [f"- Note: {note}" for note in h["notes"]] + [""]


def _sort_key(c: dict) -> tuple:
    q = c["q"] if c["q"] is not None else 2.0
    return (q, -abs(c["delta"] or 0.0), c["id"])


def _extra_text(c: dict) -> str:
    e = c["extra"]
    parts = [f"tickers {e.get('tickers')}", f"top share {_pct(e.get('top_ticker_share'))}"]
    if c["bar_covered_n"] is not None:
        parts.append(f"bar-covered {c['bar_covered_n']}")
    if "mean_stop_atr" in e:
        parts.append(f"stop {_fmt(e['mean_stop_atr'], '.2f')} ATR, loss at 2% "
                     f"${_fmt(e['dollar_loss_at_2pct'], '.0f')}, "
                     f"overshoot {_fmt(e['mean_overshoot_r'])}")
    return "; ".join(parts)


def _cell_row(c: dict) -> str:
    ci = "n/a" if c["ci"] is None else f"[{c['ci'][0]:.3f}, {c['ci'][1]:.3f}]"
    delta = "n/a" if c["delta"] is None else f"{c['delta']:+.3f}"
    return (f"| {c['id']} | {c['n']} | {c['weeks']} | {_pct(c['win_rate'])} | "
            f"{_fmt(c['net_expr'])} | {_fmt(c['gross_expr'])} | {delta} {ci} | "
            f"{_fmt(c['q'])} | {_extra_text(c)} |")


def _cell_lines(cells: list, budget: int) -> list[str]:
    ranked = sorted((c for c in cells if not c["thin"]), key=_sort_key)
    lines = ["## Cells (not thin; by q, then |Δ|)", "",
             "| cell | N | weeks | WR | net ExpR | gross ExpR | Δ net ExpR [95% CI] | q | notes |",
             "|---|---|---|---|---|---|---|---|---|"]
    shown = ranked[:max(0, budget - len(lines) - 2)]
    lines += [_cell_row(c) for c in shown]
    if len(shown) < len(ranked):
        lines.append(f"- {len(ranked) - len(shown)} more cells in the JSON")
    return lines + [""]


def _thin_lines(cells: list) -> list[str]:
    counts = Counter(c["cut"] for c in cells if c["thin"])
    text = ", ".join(f"{cut} {n}" for cut, n in sorted(counts.items())) or "none"
    return [f"Thin cells (tested and counted in BH, never evidence): {text}", ""]


def _giveback_lines(g: dict) -> list[str]:
    return ["## Give-back (mfe_r minus gross R, every trade)", "",
            f"- N {g['n']}; mean {_fmt(g['mean'])}; median {_fmt(g['median'])}", ""]


def _tally_extra(t: dict) -> str:
    if not t["extra"]:
        return ""
    return " (" + ", ".join(f"{k} {v}" for k, v in t["extra"].items()) + ")"


def _tally_lines(tallies: list) -> list[str]:
    rejections = [t for t in tallies if t["cut"] == "rejection_reason"]
    kept = [t for t in tallies if t["cut"] != "rejection_reason"] + rejections[:REJECTION_LINES]
    lines = ["## Tallies", ""] + [f"- {t['id']}: {t['count']}{_tally_extra(t)}" for t in kept]
    if len(rejections) > REJECTION_LINES:
        lines.append(f"- {len(rejections) - REJECTION_LINES} more rejection reasons in the JSON")
    return lines + [""]


def render_markdown(report: dict) -> str:
    """Header, the non-thin cell table cut to the line budget, thin counts, give-back, tallies."""
    head = _header_lines(report["header"])
    tail = (_thin_lines(report["cells"]) + _giveback_lines(report["giveback"])
            + _tally_lines(report["tallies"]))
    body = _cell_lines(report["cells"], MD_MAX_LINES - len(head) - len(tail))
    return "\n".join((head + body + tail)[:MD_MAX_LINES]) + "\n"
```

- [ ] **Step 4: Write `scripts/reports/book_autopsy.py`**

```python
#!/usr/bin/env python3
"""v161: the live-book autopsy -- two read-only VM exports in, a JSON and a Markdown report out.

    python scripts/reports/book_autopsy.py <rows.csv> <rejections.csv> [--bars-dir DIR]
        [--out-dir docs/superpowers/results] [--date YYYY-MM-DD] [--resamples N]
        [--seed N] [--balance USD]

The CSVs come from scripts/ops/export_book_rows.sh (rows / rejections mode) and
stay in the scratchpad. Writes <out-dir>/<date>-book-autopsy.json and .md.
Deterministic for one seed; no model, no network: bars come only from --bars-dir."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "reports")]

from autopsy.report import DEFAULT_BALANCE, build_report, render_markdown  # noqa: E402
from autopsy.rows import load_rejections, load_rows  # noqa: E402
from swingbot.core.backtesting.instrument.stats import (  # noqa: E402
    WEEK_BOOTSTRAP_RESAMPLES, WEEK_BOOTSTRAP_SEED)

RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="v161 live-book autopsy")
    p.add_argument("rows", type=Path, help="rows-mode export CSV")
    p.add_argument("rejections", type=Path, help="rejections-mode export CSV")
    p.add_argument("--bars-dir", type=Path, default=None,
                   help="daily-bar CSVs named like backtest_cache.cache_path (scratch dir)")
    p.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--resamples", type=int, default=WEEK_BOOTSTRAP_RESAMPLES)
    p.add_argument("--seed", type=int, default=WEEK_BOOTSTRAP_SEED)
    p.add_argument("--balance", type=float, default=DEFAULT_BALANCE,
                   help="account balance the stop cells' 2%% dollar view is priced at")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(load_rows(args.rows), load_rejections(args.rejections),
                          bars_dir=args.bars_dir, n_resamples=args.resamples,
                          seed=args.seed, balance=args.balance)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.date}-book-autopsy.json"
    md_path = args.out_dir / f"{args.date}-book-autopsy.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    h = report["header"]
    print(f"wrote {json_path}\nwrote {md_path}")
    print(f"N {h['n']}, bar-covered {h['bar_covered_n']}, cells tested {h['cells_tested']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py`
Expected: PASS, `0 failed`. Then re-run the whole package's tests once, since this task is the first to load every module together: `python $WT/scripts/dev/testrun.py suite scout` — expected `0 failed`.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C $WT/scripts/reports/autopsy/report.py $WT/scripts/reports/book_autopsy.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add scripts/reports/autopsy/report.py scripts/reports/book_autopsy.py tests/scout/test_book_autopsy.py
git -C $WT commit -m "feat(v161): book autopsy report, Markdown summary and CLI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short   # main tree unchanged
```

- [ ] **Step 8: quant-engineer review (spec panel finding; only once TS4, TS5 and TS6 are on the branch)**

Dispatch the `expert-reviewer` agent (sonnet, read-only) with this prompt:

```
role=quant-engineer
target: the v161 book autopsy on branch 2026-10-15-v161-trade-scout, worktree
E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout.
Files: scripts/reports/autopsy/{rows,cells,cuts,bars,exits,report}.py, scripts/reports/book_autopsy.py.
Spec: docs/superpowers/specs/2026-10-15-v161-trade-scout-design.md § 1 and § Data availability.
Check: lookahead in every bar read (dollar volume ends at the plan day; the fill-day open;
the reversal walk reads only bars strictly after the exit day; risk_features are frozen at
issuance), the two OHLCV caches (bars only from --bars-dir, never data/backtest_cache/),
the split guard, Δ = cell − complement with the same week draw (never a cell against a pool
that contains it), BH over every cell tested, thin by N or weeks, modelled net R labelled.
Return BLOCKING / ADVISORY findings with file:line.
```

Apply every `BLOCKING` finding in the module it names, with a test that fails before the fix, run `python $WT/scripts/dev/testrun.py suite scout` (expected `0 failed`), and commit as `fix(v161): quant-engineer review -- <finding>` with the same trailer. Record the review in `.superpowers/sdd/progress.md` (one line per finding: `TS7 quant-engineer: <finding> -- applied|declined (<why>)`). `ADVISORY` findings are recorded, and applied only when they stay inside this plan's scope.

# Phase C (start): merge parsing

### Task TS8: Merge: role-output parsing and closed-name matching

**Model:** sonnet — text parsing in one new script, behaviour given by spec § 6 and the Row format; no statistics, no `swingbot/` import

**Files:**
- Create: `scripts/dev/scout_merge.py`
- Test: `tests/scout/test_scout_merge_parse.py`

**Interfaces:**
- Consumes: the index's Row format and cell-id contract; the real `docs/claude/backtest-methodology.md` (heading line `### Closed pre-registrations — do not re-run these`, table to EOF today) and `docs/superpowers/results/preregistration-ledger.jsonl` (`{id, hypothesis, verdict, ...}` per line).
- Produces (ledger TS8; TS9 extends this same file): `ROOT`, `LEDGER`, `METHODOLOGY` (default paths); `CLOSED_HEADING`; `ROW_FIELDS` (the 11 Row format keys, in order); `EXACT_ONLY = "="`; `@dataclass ScoutRow(role, idea, claim, evidence, exploratory, edge, mechanism, order_form, manual_actions, pairs_with, divergence, route)` (all `str`) with properties `cell_id -> str | None`, `playbook_id -> str | None`, `quoted_n -> int | None`; `@dataclass(frozen=True) Drop(idea: str, role: str, reason: str)`; `normalise(name: str) -> str`; `parse_rows(text: str) -> tuple[list[ScoutRow], list[Drop]]` (malformed and duplicate rows already dropped); `closed_names(methodology: Path = METHODOLOGY) -> set[str]`; `ledger_names(ledger: Path = LEDGER) -> dict[str, str]`; `closed_match(idea: str, names: Iterable[str]) -> str | None`.
- **How TS9 must use the two name sources:** `closed_match(row.idea, closed)` for the closed table (token-run containment, so a renamed closed idea is caught); `normalise(row.idea) in ledger` (exact) for the ledger. Ledger names include hypothesis knobs such as `sma200` and `validation`, which would drop unrelated ideas under containment, so they never go through `closed_match`.

**Rules this task freezes:**
- **Parsing:** a `## role: <name>` line sets the role; `- idea: <name>` opens a row; two-space-indented `  <key>: <value>` lines fill it. A row is dropped as `malformed: <problems>` when a key is missing or empty, a key is unknown or repeated, no role heading precedes it, `exploratory` is not `yes` (spec boundary 5), `edge` is not one of `expectancy`/`harvest`/`volume`, or `divergence` is not `yes`/`no`. A row whose normalised idea was already seen is dropped as `duplicate of <role>/<idea>` (first one wins).
- **Evidence:** `cell_id` = the text after `cell ` up to the first `;` (cell ids never contain `;`, may contain `|` and spaces); `playbook_id` = the kebab id after `playbook` or `playbook:`; `quoted_n` = the integer after `N `.
- **normalise:** lower-case, every run of characters outside `a-z0-9` becomes one `-`, leading and trailing `-` stripped (`REGIME_ALLOW` → `regime-allow`, `uptrend_pullback` → `uptrend-pullback`).
- **Closed table:** rows from the heading's next line to the first non-blank line that does not start with `|`. From each row: `(vNNN` version tags and backticked identifiers (`^[A-Za-z][A-Za-z0-9_-]{3,}$`) in the first column, plus every backticked `screen-<x>` token in the row as both `screen-x` and `x`; all normalised. A row whose Outcome starts with `**PASS` or `**SCREEN-PASS` contributes its names prefixed `EXACT_ONLY`: a re-run of a passed idea is closed, a new-mechanism variant of it is not (spec § 2 asks `setup-scout` for exactly those).
- **closed_match:** returns the matched name (without the prefix) when the normalised idea equals a name, or, for names without `EXACT_ONLY`, when the name's `-`-tokens occur as a contiguous run inside the idea's tokens (`high52w-volume-confirm` ⊃ `high52w`; `regime-allowance` does not contain `regime-allow`). Names are tried in sorted order, so the result is deterministic.
- **Ledger names:** per row: the `id`; the `id` without `screen-`; the `id` without a leading `v<digits>-`; the hypothesis head before `:` when it is at most 3 words; every ALL-CAPS knob (`[A-Z][A-Z0-9_]{4,}`) in the hypothesis. All normalised; the first row to claim a name keeps it.

- [ ] **Step 1: Write the failing test**

Create `tests/scout/test_scout_merge_parse.py`:

```python
"""v161 TS8: scout_merge parsing -- role-output rows, malformed and duplicate drops,
and the two 'already decided' name sources (closed table, ledger). The closed-table
parse is also pinned against the REAL backtest-methodology.md (spec § 6), so a
rewording of that section fails here instead of silently disabling the drops."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import scout_merge as sm  # noqa: E402

BASE = {
    "claim": "One sentence.",
    "evidence": "cell direction=bullish; N 40; weeks 10; Δ net ExpR 0.20 [0.05, 0.35]; q 0.05",
    "exploratory": "yes", "edge": "expectancy", "mechanism": "Why a trader expects it to pay.",
    "order_form": "stop-buy above the signal high, one session", "manual_actions": "none",
    "pairs_with": "n/a", "divergence": "no", "route": "/prereg"}
PLAYBOOK_IDS = ("gap-and-hold", "gap-fill-reversal", "tight-base-breakout",
                "rs-leader-index-pullback", "failed-breakdown-reclaim", "atr-reentry-after-stop",
                "three-bar-weekly-reversal")


def _block(idea: str, drop=(), extra: str = "", **over) -> str:
    fields = dict(BASE, **over)
    lines = [f"- idea: {idea}"] + [f"  {k}: {v}" for k, v in fields.items() if k not in drop]
    return "\n".join(lines) + "\n" + extra


def _doc(*sections) -> str:
    return "# Scout role outputs\n\n" + "\n".join(
        f"## role: {role}\n\n" + "\n".join(blocks) for role, blocks in sections)


def test_row_fields_are_the_row_format_keys_in_order():
    assert sm.ROW_FIELDS == ("idea", "claim", "evidence", "exploratory", "edge", "mechanism",
                             "order_form", "manual_actions", "pairs_with", "divergence", "route")


def test_parse_rows_reads_each_row_under_its_role():
    text = _doc(("exit-harvester", [_block("near-tp-stall-trail", edge="harvest")]),
                ("setup-scout", [_block("gap-and-hold", evidence="playbook gap-and-hold",
                                        route="/screen gap-and-hold"),
                                 _block("break-retest-two-week")]))
    rows, drops = sm.parse_rows(text)
    assert drops == []
    assert [(r.role, r.idea) for r in rows] == [
        ("exit-harvester", "near-tp-stall-trail"), ("setup-scout", "gap-and-hold"),
        ("setup-scout", "break-retest-two-week")]
    assert rows[0].edge == "harvest" and rows[1].route == "/screen gap-and-hold"


def test_crlf_text_parses_like_lf():
    text = _doc(("regime-desk", [_block("friday-entry-skip")])).replace("\n", "\r\n")
    rows, drops = sm.parse_rows(text)
    assert [r.idea for r in rows] == ["friday-entry-skip"] and drops == []


@pytest.mark.parametrize("evidence, cell, playbook, n", [
    ("cell near_tp_close=near_tp_stall; N 41; weeks 12; Δ net ExpR 0.21 [0.05, 0.37]; q 0.06",
     "near_tp_close=near_tp_stall", None, 41),
    ("cell strategy_horizon=Break & Retest|2w; N 33; weeks 9; Δ net ExpR 0.30 [0.10, 0.50]; q 0.04",
     "strategy_horizon=Break & Retest|2w", None, 33),
    ("playbook gap-and-hold", None, "gap-and-hold", None),
    ("playbook: tight-base-breakout", None, "tight-base-breakout", None),
    ("cell weekday=Fri; N 31; weeks 8; Δ net ExpR 0.10 [0.01, 0.20]; q 0.09   |   "
     "playbook gap-fill-reversal", "weekday=Fri", "gap-fill-reversal", 31)])
def test_evidence_properties(evidence, cell, playbook, n):
    rows, _ = sm.parse_rows(_doc(("setup-scout", [_block("x-idea", evidence=evidence)])))
    assert (rows[0].cell_id, rows[0].playbook_id, rows[0].quoted_n) == (cell, playbook, n)


@pytest.mark.parametrize("kw, reason", [
    ({"drop": ("order_form",)}, "missing order_form"),
    ({"pairs_with": ""}, "missing pairs_with"),
    ({"exploratory": "no"}, "boundary 5"),
    ({"edge": "expectancy | harvest | volume"}, "edge must be"),
    ({"divergence": "maybe"}, "divergence must be yes or no"),
    ({"extra": "  confidence: high\n"}, "unknown field confidence"),
    ({"extra": "  claim: again\n"}, "repeated field claim")])
def test_malformed_rows_are_dropped_with_the_reason(kw, reason):
    rows, drops = sm.parse_rows(_doc(("regime-desk", [_block("opex-week-skip", **kw)])))
    assert rows == []
    assert len(drops) == 1 and drops[0].idea == "opex-week-skip" and drops[0].role == "regime-desk"
    assert drops[0].reason.startswith("malformed: ") and reason in drops[0].reason


def test_a_row_before_any_role_heading_is_malformed():
    rows, drops = sm.parse_rows("# outputs\n\n" + _block("orphan-idea"))
    assert rows == [] and "no '## role:' heading" in drops[0].reason


def test_a_duplicate_idea_keeps_the_first_and_drops_the_rest():
    text = _doc(("exit-harvester", [_block("Gap-Fill")]), ("setup-scout", [_block("gap_fill")]))
    rows, drops = sm.parse_rows(text)
    assert [r.role for r in rows] == ["exit-harvester"]
    assert drops == [sm.Drop("gap_fill", "setup-scout", "duplicate of exit-harvester/Gap-Fill")]


@pytest.mark.parametrize("raw, norm", [
    ("REGIME_ALLOW", "regime-allow"), ("uptrend_pullback", "uptrend-pullback"),
    ("  High52w ", "high52w"), ("Break & Retest|2w", "break-retest-2w"), ("--a--b--", "a-b")])
def test_normalise(raw, norm):
    assert sm.normalise(raw) == norm


FIXTURE_DOC = """\
# Methodology

### Closed pre-registrations — do not re-run these

| Component | Outcome | Record |
|---|---|---|
| `REGIME_ALLOW` regime gate (v17 P2a) | **No gate justified** | ledger `v17-regime-allow` |
| Idea screen `gap_volume` — open gaps up | **SCREEN-FAIL.** N=10 | ledger `screen-gap_volume` |
| Idea screen `uptrend_pullback` — RSI(2) | **SCREEN-PASS.** N=1 | ledger `screen-uptrend_pullback` |
| Headroom, `h ∈ {0.5, 1.0}` (v135) | **NO-LIFT** | x |

## Later section

| `LATER_KNOB` (v999) | **NO-LIFT** | y |
"""


def test_closed_names_reads_the_table_and_stops_at_the_first_non_table_line(tmp_path):
    doc = tmp_path / "methodology.md"
    doc.write_text(FIXTURE_DOC, encoding="utf-8")
    assert sm.closed_names(doc) == {
        "regime-allow", "v17", "gap-volume", "screen-gap-volume", "v135",
        "=uptrend-pullback", "=screen-uptrend-pullback"}


def test_closed_names_fails_loudly_without_the_heading(tmp_path):
    doc = tmp_path / "methodology.md"
    doc.write_text("# Methodology\n\nno table here\n", encoding="utf-8")
    with pytest.raises(ValueError):
        sm.closed_names(doc)


def test_closed_names_against_the_real_methodology_doc():
    names = sm.closed_names()
    assert {"v129", "v135", "high52w", "regime-allow", "gap-volume", "turn-of-month"} <= names
    assert "=uptrend-pullback" in names and "uptrend-pullback" not in names


@pytest.mark.parametrize("idea, match", [
    ("high52w-volume-confirm", "high52w"), ("gap-volume-continuation", "gap-volume"),
    ("turn-of-month-v2", "turn-of-month"), ("regime_allow_by_sector", "regime-allow"),
    ("v129-arm-c", "v129"), ("uptrend-pullback", "uptrend-pullback"),
    ("uptrend-pullback-gap-entry", None), ("regime-allowance", None),
    ("atr-reentry-after-stop", None)])
def test_closed_match_against_the_real_table(idea, match):
    assert sm.closed_match(idea, sm.closed_names()) == match


def test_no_playbook_seed_is_closed():
    names = sm.closed_names()
    assert {pid: sm.closed_match(pid, names) for pid in PLAYBOOK_IDS} == dict.fromkeys(PLAYBOOK_IDS)


def test_ledger_names_map_ids_screen_names_heads_and_knobs(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    rows = [{"id": "v17-regime-allow", "hypothesis": "REGIME_ALLOW regime gate (v17 P2a)"},
            {"id": "screen-high52w", "hypothesis": "high52w: close >= 0.95 x the 252-bar high"},
            {"id": "v99-other", "hypothesis": "Another REGIME_ALLOW mention"}]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n", encoding="utf-8")
    assert sm.ledger_names(ledger) == {
        "v17-regime-allow": "v17-regime-allow", "regime-allow": "v17-regime-allow",
        "screen-high52w": "screen-high52w", "high52w": "screen-high52w",
        "v99-other": "v99-other", "other": "v99-other"}


def test_ledger_names_against_the_real_ledger():
    names = sm.ledger_names()
    assert names["high52w"] == "screen-high52w"
    assert names["regime-allow"] == "v17-regime-allow"
    assert names["uptrend-pullback"] == "screen-uptrend_pullback"
    assert names["screen-uptrend-pullback"] == "screen-uptrend_pullback"
    assert names["e33-avwap-levels"] == "e33-avwap-levels"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'scout_merge'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/dev/scout_merge.py`:

```python
#!/usr/bin/env python3
"""v161: merge the generator roles' rows into one ranked scout slate.

This part (TS8) parses the role-output file into ScoutRows -- dropping malformed and
duplicate rows -- and reads the two sources of already-decided names: the
pre-registration ledger and the closed-pre-registrations table of
docs/claude/backtest-methodology.md. TS9 adds the drops against the autopsy JSON,
the ranking, the slate and the CLI. Deterministic; no model, no network."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER = ROOT / "docs" / "superpowers" / "results" / "preregistration-ledger.jsonl"
METHODOLOGY = ROOT / "docs" / "claude" / "backtest-methodology.md"
CLOSED_HEADING = "### Closed pre-registrations — do not re-run these"
ROW_FIELDS = ("idea", "claim", "evidence", "exploratory", "edge", "mechanism", "order_form",
              "manual_actions", "pairs_with", "divergence", "route")
EXACT_ONLY = "="   # prefix: a name from a PASS row matches only an identical idea
_EDGES = ("expectancy", "harvest", "volume")
_ROLE_RE = re.compile(r"^## role:\s*(\S+)\s*$")
_START_RE = re.compile(r"^- idea:\s*(.*)$")
_FIELD_RE = re.compile(r"^  ([a-z_]+):\s*(.*)$")
_CELL_RE = re.compile(r"\bcell\s+([^;]+?)\s*(?:;|$)")
_PLAYBOOK_RE = re.compile(r"\bplaybook:?\s+([a-z0-9][a-z0-9-]*)")
_N_RE = re.compile(r"\bN\s+(\d+)")
_TAG_RE = re.compile(r"\((v\d+)")
_TICK_RE = re.compile(r"`([^`]+)`")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{3,}$")
_PASS_RE = re.compile(r"^\*\*(SCREEN-)?PASS\b")
_KNOB_RE = re.compile(r"\b[A-Z][A-Z0-9_]{4,}\b")
_HEAD_MAX_WORDS = 3


@dataclass
class ScoutRow:
    role: str
    idea: str
    claim: str
    evidence: str
    exploratory: str
    edge: str
    mechanism: str
    order_form: str
    manual_actions: str
    pairs_with: str
    divergence: str
    route: str

    @property
    def cell_id(self) -> str | None:
        match = _CELL_RE.search(self.evidence)
        return match.group(1) if match else None

    @property
    def playbook_id(self) -> str | None:
        match = _PLAYBOOK_RE.search(self.evidence)
        return match.group(1) if match else None

    @property
    def quoted_n(self) -> int | None:
        match = _N_RE.search(self.evidence)
        return int(match.group(1)) if match else None


@dataclass(frozen=True)
class Drop:
    idea: str
    role: str
    reason: str


def normalise(name: str) -> str:
    """Case-insensitive kebab form: every run outside a-z0-9 becomes one '-'."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _add_field(fields: dict, key: str, value: str, problems: list[str]) -> None:
    if key not in ROW_FIELDS:
        problems.append(f"unknown field {key}")
    elif key in fields:
        problems.append(f"repeated field {key}")
    else:
        fields[key] = value


def _read_blocks(text: str) -> list[tuple[str, dict, list[str]]]:
    """(role, fields, problems) per '- idea:' block, in file order."""
    blocks: list[tuple[str, dict, list[str]]] = []
    role, current = "", None
    for line in text.replace("\r\n", "\n").split("\n"):
        heading, start, field = _ROLE_RE.match(line), _START_RE.match(line), _FIELD_RE.match(line)
        if heading:
            role, current = heading.group(1), None
        elif start:
            current = {"idea": start.group(1).strip()}
            blocks.append((role, current, []))
        elif field and current is not None:
            _add_field(current, field.group(1), field.group(2).strip(), blocks[-1][2])
    return blocks


def _problems(role: str, fields: dict, problems: list[str]) -> list[str]:
    out = list(problems)
    missing = [f for f in ROW_FIELDS if not fields.get(f)]
    if missing:
        out.append("missing " + ", ".join(missing))
    if not role:
        out.append("no '## role:' heading above it")
    checks = (("exploratory", ("yes",), "exploratory must be yes (spec boundary 5)"),
              ("edge", _EDGES, "edge must be expectancy, harvest or volume"),
              ("divergence", ("yes", "no"), "divergence must be yes or no"))
    out += [message for key, allowed, message in checks
            if fields.get(key) and fields[key] not in allowed]
    return out


def parse_rows(text: str) -> tuple[list[ScoutRow], list[Drop]]:
    """Rows in the Row format under '## role:' headings; malformed and duplicates dropped."""
    rows: list[ScoutRow] = []
    drops: list[Drop] = []
    seen: dict[str, str] = {}
    for role, fields, problems in _read_blocks(text):
        idea = fields.get("idea") or "(no idea)"
        bad = _problems(role, fields, problems)
        if bad:
            drops.append(Drop(idea, role, "malformed: " + "; ".join(bad)))
            continue
        key = normalise(idea)
        if key in seen:
            drops.append(Drop(idea, role, f"duplicate of {seen[key]}"))
            continue
        seen[key] = f"{role}/{idea}"
        rows.append(ScoutRow(role=role, **{f: fields[f] for f in ROW_FIELDS}))
    return rows, drops


def _table_rows(lines: list[str]) -> list[str]:
    """The closed table: from the heading to the first non-blank, non-table line.
    ``list.index`` raises ValueError when the heading is gone -- loudly, on purpose."""
    start = lines.index(CLOSED_HEADING)
    out = []
    for line in lines[start + 1:]:
        if line.startswith("|"):
            out.append(line)
        elif line.strip():
            break
    return out


def _names_in_row(line: str) -> set[str]:
    cols = [c.strip() for c in line.strip().strip("|").split("|")]
    raw = set(_TAG_RE.findall(cols[0]))
    raw.update(t for t in _TICK_RE.findall(cols[0]) if _NAME_RE.match(t))
    for token in _TICK_RE.findall(line):
        if token.startswith("screen-"):
            raw.update({token, token.removeprefix("screen-")})
    names = {normalise(n) for n in raw}
    passed = len(cols) > 1 and _PASS_RE.match(cols[1])
    return {EXACT_ONLY + n for n in names} if passed else names


def closed_names(methodology: Path = METHODOLOGY) -> set[str]:
    """Every name the closed-pre-registrations table records (PASS rows prefixed EXACT_ONLY)."""
    lines = Path(methodology).read_text(encoding="utf-8").splitlines()
    names: set[str] = set()
    for line in _table_rows(lines):
        names |= _names_in_row(line)
    return names


def _ledger_row_names(row: dict) -> list[str]:
    rid = row["id"]
    raw = [rid, rid.removeprefix("screen-"), re.sub(r"^v\d+-", "", rid)]
    hypothesis = row.get("hypothesis") or ""
    head = hypothesis.split(":", 1)[0]
    if ":" in hypothesis and len(head.split()) <= _HEAD_MAX_WORDS:
        raw.append(head)
    raw += _KNOB_RE.findall(hypothesis)
    return [n for n in (normalise(r) for r in raw) if n]


def ledger_names(ledger: Path = LEDGER) -> dict[str, str]:
    """Normalised name -> ledger id, for EXACT matching only (never closed_match)."""
    out: dict[str, str] = {}
    for line in Path(ledger).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            for name in _ledger_row_names(row):
                out.setdefault(name, row["id"])
    return out


def _contains(tokens: list[str], needle: list[str]) -> bool:
    size = len(needle)
    return any(tokens[i:i + size] == needle for i in range(len(tokens) - size + 1))


def closed_match(idea: str, names: Iterable[str]) -> str | None:
    """The closed name an idea re-runs: equal, or a contiguous token run inside it."""
    norm = normalise(idea)
    tokens = norm.split("-")
    for name in sorted(names):
        bare = name.removeprefix(EXACT_ONLY)
        if bare == norm or (not name.startswith(EXACT_ONLY) and _contains(tokens, bare.split("-"))):
            return bare
    return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C $WT/scripts/dev/scout_merge.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/dev/scout_merge.py tests/scout/test_scout_merge_parse.py
git -C $WT commit -m "feat(v161): scout merge -- role-output parsing and closed-name matching

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short   # main tree unchanged
```

