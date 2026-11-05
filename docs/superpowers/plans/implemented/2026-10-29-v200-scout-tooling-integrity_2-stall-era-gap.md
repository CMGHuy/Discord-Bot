# Scout tooling integrity, part 2: stall exclusion, era split, gap names

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Scout tooling integrity](../specs/2026-10-29-v200-scout-tooling-integrity.md) (Parts 2, 3, 4)
**Index:** [`_0-index.md`](2026-10-29-v200-scout-tooling-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.

Tasks V200-9 … V200-12. They run in this order, after V200-1 (production facts file) and V200-3 (`BookRow.opened_at_utc` / `closed_at_utc`), and V200-10 after V200-4 (header coverage lines). `<wt>` is the absolute path of this plan's worktree; `<scratch>` is the session scratchpad.

Controller decisions binding this part (2026-10-29):

- Era `post` = opened after the boundary **and** on a later Eastern date than the boundary's; a boundary-day entry is `straddle`.
- The stall rule acts on the committed `trade_ids` list at report time (by id); the rule itself is only re-run by the rebuild test and the CLI. A trade missing `opened_at` or `closed_at` is never matched by the rule (it cannot be placed in time), and the CLI says how many such trade rows it saw.

# Phase 4 — Stall exclusion, era split, gap names

### Task V200-9: Stall exclusion rule and `exclusions.json`

**Model:** sonnet — new pure module plus a read-only production export and a data file built from it; the rule is fixed by the spec.

**Files:**
- Create: `scripts/reports/autopsy/exclusions.py`
- Create: `scripts/reports/autopsy/exclusions.json`
- Create: `tests/scout/fixtures/stall_2026_08_trades.csv`
- Create: `tests/scout/test_autopsy_exclusions.py`

**Interfaces:**
- Consumes: `docs/superpowers/results/2026-10-29-v200-prod-reads.md` (V200-1): the `stall_windows` in its fenced `json` block (two `{start, end}` UTC ISO pairs). `rows.BookRow.opened_at_utc` / `closed_at_utc: dt.datetime | None` (tz-aware UTC, V200-3). `rows.load_rows`, `rows._timestamp`, `rows.EXPORT_COLUMNS`.
- Produces (V200-10 consumes):
  - `EXCLUSIONS_PATH = Path(__file__).with_name("exclusions.json")`
  - `@dataclass(frozen=True) class Window: start: dt.datetime; end: dt.datetime` (tz-aware UTC)
  - `@dataclass(frozen=True) class Exclusion: key: str; reason: str; rule: str; windows: tuple[Window, ...]; trade_ids: frozenset[str]`
  - `load_exclusions(path: Path = EXCLUSIONS_PATH, *, input_fingerprints: dict | None = None) -> list[Exclusion]`: sorted by key; records `str(path.resolve()) -> sha256 hex` of the exact bytes read, the same format as `rows.read_input`.
  - `open_in_window(opened: dt.datetime | None, closed: dt.datetime | None, window: Window) -> bool`
  - `rebuild_trade_ids(rows, windows) -> list[str]` (sorted, unique)
  - `main(argv: list[str] | None = None) -> int`; CLI `python scripts/reports/autopsy/exclusions.py <rows.csv>` prints the rebuilt ids as a JSON list on stdout.

**Rules this task freezes** (spec Part 2; index Global Constraints "Stall rule"):

- A trade is excluded when `opened < window.end and closed >= window.start` for any window. That means open at any moment in it, whatever its close reason or close time. Both bounds compare tz-aware UTC instants to the second.
- A missing `opened` or `closed` gives `False` (never matched).
- Only `row_kind == "trade"` rows with a `trade_id` are candidates.
- `exclusions.py` has **no relative import** at module level, so it runs both as `autopsy.exclusions` and as a script. `main` imports `autopsy.rows` lazily after putting the repo root and `scripts/reports` on `sys.path` (the `book_autopsy.py` pattern).
- `load_exclusions` refuses, raising a `ValueError` that names the key, any of these: a window with `start >= end`, a timestamp without an offset, or an entry missing any of `reason`, `rule`, `windows`, `trade_ids`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scout/test_autopsy_exclusions.py`:

```python
"""v200 Part 2: the August stall exclusion -- the open-at-any-moment rule, the
committed file, and the trade ids rebuilt from the rule against a production extract."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import exclusions, rows  # noqa: E402

FIXTURE = ROOT / "tests" / "scout" / "fixtures" / "stall_2026_08_trades.csv"
UTC = dt.timezone.utc
W = exclusions.Window(dt.datetime(2026, 8, 3, 16, 18, 2, tzinfo=UTC),
                      dt.datetime(2026, 8, 4, 18, 55, 43, tzinfo=UTC))


def _at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


def _trade(tid, opened, closed, kind="trade"):
    return SimpleNamespace(row_kind=kind, trade_id=tid,
                           opened_at_utc=_at(opened) if opened else None,
                           closed_at_utc=_at(closed) if closed else None)


@pytest.mark.parametrize("opened, closed", [
    ("2026-08-01T14:00:00", "2026-08-04T18:55:43"),   # opened before, closed by the catch-up batch
    ("2026-08-01T14:00:00", "2026-08-03T17:00:00"),   # closed by hand inside the window
    ("2026-08-03T17:00:00", "2026-08-10T15:00:00"),   # opened inside, closed long after
    ("2026-07-20T14:00:00", "2026-08-03T16:18:02"),   # closed exactly at the window start
    ("2026-08-01T14:00:00", "2026-08-20T15:00:00"),   # spans the whole window
])
def test_open_at_any_moment_is_excluded_whatever_the_close(opened, closed):
    assert exclusions.open_in_window(_at(opened), _at(closed), W) is True


@pytest.mark.parametrize("opened, closed", [
    ("2026-07-20T14:00:00", "2026-08-03T16:18:01"),   # closed one second before the start
    ("2026-08-04T18:55:43", "2026-08-06T15:00:00"),   # opened exactly at the window end
    ("2026-08-05T14:00:00", "2026-08-07T15:00:00"),   # opened after the window
])
def test_closed_just_before_the_window_is_kept(opened, closed):
    assert exclusions.open_in_window(_at(opened), _at(closed), W) is False


def test_a_trade_missing_a_timestamp_is_never_matched():
    assert exclusions.open_in_window(None, _at("2026-08-04T00:00:00"), W) is False
    assert exclusions.open_in_window(_at("2026-08-03T17:00:00"), None, W) is False


def test_rebuild_returns_sorted_unique_trade_ids_of_trade_rows_only():
    data = [_trade("T9", "2026-08-01T14:00:00", "2026-08-04T18:55:43"),
            _trade("T2", "2026-08-03T17:00:00", "2026-08-05T15:00:00"),
            _trade("T2", "2026-08-03T17:00:00", "2026-08-05T15:00:00"),
            _trade("P1", "2026-08-03T17:00:00", "2026-08-05T15:00:00", kind="plan"),
            _trade("T5", "2026-07-01T14:00:00", "2026-07-02T15:00:00")]
    assert exclusions.rebuild_trade_ids(data, [W]) == ["T2", "T9"]
    assert exclusions.rebuild_trade_ids([], [W]) == []


def _write(tmp_path, payload) -> Path:
    path = tmp_path / "exclusions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


GOOD = {"k": {"reason": "r", "rule": "u",
              "windows": [{"start": "2026-08-03T16:18:02Z", "end": "2026-08-04T18:55:43Z"}],
              "trade_ids": ["T2", "T1"]}}


def test_load_parses_utc_windows_ids_and_records_the_file_hash(tmp_path):
    path = _write(tmp_path, GOOD)
    inputs = {}
    [ex] = exclusions.load_exclusions(path, input_fingerprints=inputs)
    assert ex.key == "k" and ex.trade_ids == frozenset({"T1", "T2"})
    assert ex.windows == (W,)
    assert inputs == {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize("window", [
    {"start": "2026-08-04T18:55:43Z", "end": "2026-08-03T16:18:02Z"},   # start after end
    {"start": "2026-08-03T16:18:02", "end": "2026-08-04T18:55:43Z"},    # no offset
])
def test_load_refuses_a_bad_window_naming_the_key(tmp_path, window):
    payload = {"k": dict(GOOD["k"], windows=[window])}
    with pytest.raises(ValueError, match="k"):
        exclusions.load_exclusions(_write(tmp_path, payload))


def test_load_refuses_an_entry_missing_a_field(tmp_path):
    payload = {"k": {key: v for key, v in GOOD["k"].items() if key != "rule"}}
    with pytest.raises(ValueError, match="rule"):
        exclusions.load_exclusions(_write(tmp_path, payload))


def test_the_committed_file_has_one_stall_entry_with_two_windows():
    [ex] = exclusions.load_exclusions()
    assert ex.key == "stall_2026_08"
    assert len(ex.windows) == 2
    assert ex.windows[0].start == dt.datetime(2026, 8, 3, 16, 18, 2, tzinfo=UTC)
    assert ex.windows[0].end == dt.datetime(2026, 8, 4, 18, 55, 43, tzinfo=UTC)
    assert ex.windows[1].end == dt.datetime(2026, 8, 5, 15, 34, 8, tzinfo=UTC)
    assert ex.windows[0].end <= ex.windows[1].start < ex.windows[1].end
    assert ex.trade_ids


def _fixture_rows():
    with FIXTURE.open(encoding="utf-8", newline="") as fh:
        return [SimpleNamespace(row_kind="trade", trade_id=r["trade_id"],
                                opened_at_utc=rows._timestamp(r["opened_at"]),
                                closed_at_utc=rows._timestamp(r["closed_at"]))
                for r in csv.DictReader(fh)]


def test_the_committed_trade_ids_are_rebuilt_exactly_from_the_rule():
    [ex] = exclusions.load_exclusions()
    rebuilt = exclusions.rebuild_trade_ids(_fixture_rows(), ex.windows)
    assert rebuilt == sorted(ex.trade_ids)


def test_the_fixture_holds_near_misses_beside_the_excluded_trades():
    """The extract is a band around the windows, not only the excluded trades."""
    [ex] = exclusions.load_exclusions()
    ids = {r.trade_id for r in _fixture_rows()}
    assert ex.trade_ids <= ids
    assert ids - ex.trade_ids


def test_the_cli_prints_the_rebuilt_ids_as_json(tmp_path, capsys):
    header = list(rows.EXPORT_COLUMNS)
    rec = {c: "" for c in header}
    rec.update(row_kind="trade", trade_id="T1", plan_id="P1", ticker="AAA", direction="bullish",
               opened_at="2026-08-03T17:00:00+00:00", closed_at="2026-08-05T15:00:00+00:00",
               entry="100", stop_loss="98", r_realized="-1.0")
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerow(rec)
    assert exclusions.main([str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == ["T1"]
```

`rows._timestamp` returns a tz-aware value (naive input is read as UTC), so comparing it against the UTC windows is valid. If V200-3 made it return naive values, wrap it with `.replace(tzinfo=UTC)` here rather than changing `rows.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_exclusions.py`
Expected: a collection error, `ImportError: cannot import name 'exclusions'`.

- [ ] **Step 3: Implement `scripts/reports/autopsy/exclusions.py`**

The module docstring states the rule verbatim (the "Rules this task freezes" list above), says the report applies the committed `trade_ids` by id (V200-10), and gives the CLI usage line. Functions are as listed under **Interfaces**.

- **Parsing:** `dt.datetime.fromisoformat(text.replace("Z", "+00:00"))`, refuse a naive result, then `.astimezone(dt.timezone.utc)`.
- **`load_exclusions`:** read `path.read_bytes()` once. Hash those bytes into `input_fingerprints` when given, then `json.loads`. Put the per-entry validation in a `_entry(key: str, raw: dict) -> Exclusion` helper so each function stays below complexity 15.
- **`main`:** this body is fixed:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v200: rebuild the stall trade ids from a rows export")
    parser.add_argument("rows", type=Path)
    parser.add_argument("--exclusions", type=Path, default=EXCLUSIONS_PATH)
    parser.add_argument("--key", default="stall_2026_08")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(root), str(root / "scripts" / "reports")]
    from autopsy.rows import load_rows
    loaded = load_rows(args.rows)
    [entry] = [e for e in load_exclusions(args.exclusions) if e.key == args.key]
    untimed = sum(1 for r in loaded if r.row_kind == "trade"
                  and (r.opened_at_utc is None or r.closed_at_utc is None))
    print(f"{untimed} trade rows lack opened_at or closed_at and are never matched", file=sys.stderr)
    print(json.dumps(rebuild_trade_ids(loaded, entry.windows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write `exclusions.json` with the windows from V200-1 and an empty id list**

Copy `stall_windows` exactly from the json block in `<wt>/docs/superpowers/results/2026-10-29-v200-prod-reads.md`. If that file is missing (V200-1 not merged), stop and return `BLOCKED: V200-1 not merged`.

```json
{
  "stall_2026_08": {
    "reason": "stop monitor stalled 2026-08-03..08-05: stops were enforced only by the 08-04 and 08-05 catch-up batches, so every trade open then carries the stall in its exit",
    "rule": "exclude a trade when opened_at < window.end and closed_at >= window.start (open at any moment in a window), whatever its close reason; rebuilt by scripts/reports/autopsy/exclusions.py",
    "windows": [
      {"start": "2026-08-03T16:18:02Z", "end": "2026-08-04T18:55:43Z"},
      {"start": "<window 2 start from V200-1>", "end": "2026-08-05T15:34:08Z"}
    ],
    "trade_ids": []
  }
}
```

- [ ] **Step 5: Export the production rows read-only, rebuild the ids and build the fixture**

```bash
bash <wt>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" \
    < <wt>/scripts/ops/export_book_rows.sh > "<scratch>/v200_rows.csv"
python <wt>/scripts/reports/autopsy/exclusions.py "<scratch>/v200_rows.csv" > "<scratch>/v200_stall_ids.json"
```

Expected: stderr prints the untimed count and stdout a non-empty JSON list.

1. Paste that list as `trade_ids` into `exclusions.json`, sorted, one id per line.
2. Write the fixture with a short one-off script kept in `<scratch>` (not committed):
   - **Rows:** every `row_kind == "trade"` row of `<scratch>/v200_rows.csv` with `closed_at >= 2026-07-27` and `opened_at < 2026-08-12` (UTC).
   - **Columns:** exactly `trade_id,opened_at,closed_at`, with the raw export text unchanged.
   - **Order:** sorted by `trade_id`.

The fixture holds no prices, tickers or R, only ids and timestamps. It is the only committed derivative of the export (index Global Constraints). The raw export stays in `<scratch>`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_exclusions.py`
Expected: all pass, `0 failed`. Then `python -m radon cc -s -n C <wt>/scripts/reports/autopsy/exclusions.py` prints nothing.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add scripts/reports/autopsy/exclusions.py scripts/reports/autopsy/exclusions.json \
    tests/scout/fixtures/stall_2026_08_trades.csv tests/scout/test_autopsy_exclusions.py
git -C <wt> commit -m "feat(autopsy): v200 stall exclusion rule and committed trade ids (V200-9)"
```

### Task V200-10: Apply the exclusion in the report; stall line; test routing

**Model:** sonnet — wires a finished module into `build_report` and the CLI with a pinned header shape; no statistics change.

**Files:**
- Modify: `scripts/reports/autopsy/exclusions.py` (add `apply_exclusions`, `stall_summary`)
- Modify: `scripts/reports/autopsy/report.py` (`build_report`, `_header_lines`)
- Modify: `scripts/reports/book_autopsy.py` (`_parser`, `main`)
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`)
- Modify: `tests/scout/test_book_autopsy.py` (`test_cli_records_input_hashes_effective_frictions_and_resolved_invocation`)
- Modify: `tests/scout/test_scout_routing.py` (`CASES`)
- Create: `tests/scout/test_autopsy_stall_report.py`

**Interfaces:**
- Consumes: from V200-9, `exclusions.EXCLUSIONS_PATH`, `load_exclusions(path, *, input_fingerprints=None)`, `Exclusion.key`, `Exclusion.trade_ids`. From V200-4, `build_report` already writes `header["alert_hour_coverage"]`; keep it, computed over the rows that remain after exclusion.
- Produces:
  - `exclusions.apply_exclusions(rows: list, exclusions: list[Exclusion]) -> tuple[list, list]` returns `(kept rows, excluded trade rows)`. A row is excluded when `row.row_kind == "trade"` and `row.trade_id` is in any exclusion's `trade_ids`. Plan rows are always kept. Order is preserved.
  - `exclusions.stall_summary(exclusions: list[Exclusion], excluded: list) -> list[dict]` gives one dict per exclusion, in key order: `{"key", "n", "gross_expr", "worst_r"}`. `n` counts the excluded rows of that key with a `gross_r`. `gross_expr` is their mean `gross_r` rounded to 4 places, and `worst_r` their minimum. Both are `None` when `n == 0`.
  - `report.build_report(..., exclusions_path: Path | None = EXCLUSIONS_PATH)`. With `None` there is no exclusion: `header["stall_exclusions"] == []` and no manifest entry.
  - `header["stall_exclusions"]` (list above). The exclusions file's SHA-256 is in `header["input_fingerprints"]` under `str(path.resolve())`.
  - Markdown, one line per exclusion directly under the pooled line: `- stall exclusion <key>: N <n>, gross ExpR <x.xxx|n/a>, worst R <x.xxx|n/a>`.
  - CLI: `--exclusions PATH` (default `EXCLUSIONS_PATH`) and `--no-exclusions`. stdout gains `stall exclusion <key>: N <n>` per exclusion.

**Placement (spec Part 2):** in `build_report`, the first thing after `inputs = ...` is to load the exclusions and call `apply_exclusions`. Everything below it (`enrich_with_bars`, `closed_trades`, `_sector_snapshot`, `_cells`, `apply_bh`, `fill_tallies`, `alert_supply_tallies`, `_header`, the V200-4 coverage, `giveback_summary`) then reads the kept rows only. That covers cells, complements, the BH family, tallies, give-back and the pooled header figures in one place. Set `header["stall_exclusions"]` with the other `header.update(...)` keys. The four top-level keys stay exactly `{"header", "cells", "tallies", "giveback"}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scout/test_autopsy_stall_report.py`:

```python
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
        "windows": [{"start": "2026-08-03T16:18:02Z", "end": "2026-08-04T18:55:43Z"}],
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
```

`_today_sectors` is imported so that the autouse sector-map patch from `test_book_autopsy` also runs in this module. The `_report(...)` calls rely on `_files` writing exactly 48 trades (`T0`..`T47`) plus one expired plan.

In `tests/scout/test_book_autopsy.py::test_cli_records_input_hashes_effective_frictions_and_resolved_invocation`, the `expected` manifest gains the committed exclusions file:

```python
    from autopsy import exclusions
    expected = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (rows_csv, rej_csv, bars_dir / "AAA.csv", exclusions.EXCLUSIONS_PATH)}
```

In `tests/scout/test_scout_routing.py`, `CASES` gains:

```python
    "scripts/reports/autopsy/exclusions.json": ("tests/scout/",),
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_stall_report.py`
Expected: FAIL with `TypeError: build_report() got an unexpected keyword argument 'exclusions_path'` and `AttributeError: module 'autopsy.exclusions' has no attribute 'apply_exclusions'`.

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_routing.py`
Expected: FAIL on `scripts/reports/autopsy/exclusions.json` (routes to the wide default, not `tests/scout/`).

- [ ] **Step 3: Implement**

- **`exclusions.py`:** add `apply_exclusions` and `stall_summary` as described under **Interfaces**.
- **`report.py`:**
  - Add `from .exclusions import EXCLUSIONS_PATH, apply_exclusions, load_exclusions, stall_summary`.
  - In `build_report`, add the `exclusions_path` keyword and follow the placement paragraph above.
  - In `_header_lines`, insert the stall lines (`h.get("stall_exclusions", [])`, formatted with the existing `_fmt`) right after the pooled-ExpR line.
- **`book_autopsy.py`:**
  - In `_parser`, add `--exclusions` (`type=Path`, default `EXCLUSIONS_PATH`) and `--no-exclusions` (`store_true`).
  - In `main`, pass `exclusions_path=None if args.no_exclusions else args.exclusions`, and print `stall exclusion {key}: N {n}` per `header["stall_exclusions"]` entry after the existing summary line.
- **`select_tests.py`:** in `DATA_READERS`, add this row directly after the `scripts/dev/complexity_baseline.json` row:

```python
    # v200: the autopsy report loads the committed stall exclusion list.
    ("scripts/reports/autopsy/exclusions.json", ("tests/scout/",)),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_stall_report.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_routing.py
python <wt>/scripts/dev/testrun.py file tests/dev/test_select_tests.py
python -m radon cc -s -n C <wt>/scripts/reports/autopsy/report.py <wt>/scripts/reports/autopsy/exclusions.py <wt>/scripts/reports/book_autopsy.py
```

Expected: all four test runs report `0 failed`, and radon prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add scripts/reports/autopsy/exclusions.py scripts/reports/autopsy/report.py \
    scripts/reports/book_autopsy.py scripts/dev/select_tests.py \
    tests/scout/test_autopsy_stall_report.py tests/scout/test_book_autopsy.py tests/scout/test_scout_routing.py
git -C <wt> commit -m "feat(autopsy): v200 drop stall trades before every figure and report them on one line (V200-10)"
```

### Task V200-11: Exit-model era split per cell

**Model:** sonnet — a small pure module and two decoration points; the era rule is fixed by the spec and the controller's boundary-day decision.

**Files:**
- Create: `scripts/reports/autopsy/eras.py`
- Create: `tests/scout/test_autopsy_eras.py`
- Modify: `scripts/reports/autopsy/cells.py` (`CellStats`, `to_json`)
- Modify: `scripts/reports/autopsy/report.py` (`_decorate`, `build_report`, `_header_lines`, `_extra_text`, `_cell_row`, `_cell_lines`)
- Modify: `tests/scout/test_book_autopsy.py` (`test_markdown_keeps_pipe_delimited_cell_ids_in_one_column`, plus one new test)

**Interfaces:**
- Consumes: the `era_boundary_utc` and `era_boundary_source` values from the fenced `json` block in `docs/superpowers/results/2026-10-29-v200-prod-reads.md` (V200-1). `BookRow.opened_at_utc` / `closed_at_utc` (V200-3). `cells.net_value`. `swingbot.core.market.session.US_MARKET_TZ`.
- Produces:
  - `eras.ERA_BOUNDARY_UTC: dt.datetime` (tz-aware UTC, to the second) and `eras.ERA_BOUNDARY_SOURCE: str`, both copied from V200-1.
  - `eras.ERAS = ("pre", "straddle", "post")`
  - `eras.era_of(row, boundary: dt.datetime = ERA_BOUNDARY_UTC) -> str | None`
  - `eras.era_stats(members: list, boundary: dt.datetime = ERA_BOUNDARY_UTC) -> dict[str, dict]` always returns all three keys, each `{"n": int, "win_rate": float | None, "net_expr": float | None}` (4 places, `None` at n 0).
  - `eras.sign_flip(stats: dict | None) -> bool`
  - `CellStats.eras: dict | None = None` and `CellStats.notes: list[str] = field(default_factory=list)`. `to_json` adds `"eras"` (a copy or `None`) and `"notes"` (a list).
  - `header["era_boundary"] = {"utc": "<YYYY-MM-DDTHH:MM:SSZ>", "source": ERA_BOUNDARY_SOURCE}`

**Rules this task freezes** (spec Part 3, controller decision 2026-10-29):

| Condition, checked in order | Era |
|---|---|
| `closed_at_utc` is `None` | `None` |
| `closed_at_utc < boundary` | `pre` |
| `opened_at_utc` is `None` | `None` |
| Eastern date of `opened_at_utc` > Eastern date of `boundary` | `post` |
| otherwise (opened before or on the boundary's Eastern day, closed at or after it) | `straddle` |

- `win_rate` counts `gross_r > 0` over the era's members, as `cell_stats` does. `net_expr` is the mean of `net_value`. A row whose era is `None` counts in no era.
- `sign_flip` is true only when both `pre` and `post` `net_expr` are non-`None` and `pre * post < 0` (a zero is no sign).
- Era numbers carry no CI and no q. `apply_bh`, `cell_stats` and `cut_cells` are untouched, and the merge never reads `eras` (index cross-task contracts).
- **Markdown:** one new column between `q` and `notes`, headed `eras pre / straddle / post (N WR net)`. Its text is `"<n> <wr> <net> / <n> <wr> <net> / <n> <wr> <net>"`, with `wr` formatted by the existing `_pct` (`60.0%`) and `net` as `+0.000`. An era with n 0 shows `0 n/a`. A cell without `eras` (an older report) shows `n/a`. The `era sign flip` note joins the notes column. The header gains one line: `- Exit-model era boundary (production deploy of b4ef2e87): <utc> (source: <source>); era columns carry no CI and no q`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scout/test_autopsy_eras.py`:

```python
"""v200 Part 3: exit-model eras around the production deploy of b4ef2e87."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import cells, eras, report, rows  # noqa: E402

UTC = dt.timezone.utc
B = dt.datetime(2026, 9, 11, 14, 0, 0, tzinfo=UTC)      # 10:00 EDT on 2026-09-11


def _at(text):
    return None if text is None else dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


def _row(opened, closed, gross=1.0):
    return rows.BookRow(row_kind="trade", gross_r=gross, net_r=gross,
                        opened_at_utc=_at(opened), closed_at_utc=_at(closed))


@pytest.mark.parametrize("opened, closed, era", [
    ("2026-09-08T14:00:00", "2026-09-11T13:59:59", "pre"),       # closed a second before
    ("2026-09-08T14:00:00", "2026-09-11T14:00:00", "straddle"),  # closed exactly at the boundary
    ("2026-09-08T14:00:00", "2026-09-15T15:00:00", "straddle"),  # opened before, closed after
    ("2026-09-11T15:00:00", "2026-09-15T15:00:00", "straddle"),  # boundary-day entry, after the deploy
    ("2026-09-12T02:00:00", "2026-09-15T15:00:00", "straddle"),  # 22:00 EDT on 09-11: still the boundary's Eastern day
    ("2026-09-12T13:30:00", "2026-09-15T15:00:00", "post"),      # the next Eastern day
    (None, "2026-09-01T15:00:00", "pre"),                         # closed before: opened is not needed
    (None, "2026-09-15T15:00:00", None),
    ("2026-09-08T14:00:00", None, None),
])
def test_era_of(opened, closed, era):
    assert eras.era_of(_row(opened, closed), B) == era


def test_era_stats_reports_every_era_and_skips_unplaced_rows():
    members = [_row("2026-09-01T14:00:00", "2026-09-03T15:00:00", 1.0),
               _row("2026-09-01T14:00:00", "2026-09-03T15:00:00", -1.0),
               _row("2026-09-01T14:00:00", "2026-09-03T15:00:00", 2.0),
               _row("2026-09-14T14:00:00", "2026-09-16T15:00:00", -0.5),
               _row(None, "2026-09-16T15:00:00", 9.0)]
    assert eras.era_stats(members, B) == {
        "pre": {"n": 3, "win_rate": 0.6667, "net_expr": 0.6667},
        "straddle": {"n": 0, "win_rate": None, "net_expr": None},
        "post": {"n": 1, "win_rate": 0.0, "net_expr": -0.5}}
    assert eras.era_stats([], B) == {k: {"n": 0, "win_rate": None, "net_expr": None}
                                     for k in eras.ERAS}


@pytest.mark.parametrize("pre, post, flip", [
    (0.2, -0.1, True), (-0.2, 0.1, True), (0.2, 0.1, False),
    (None, -0.1, False), (0.0, -0.1, False)])
def test_sign_flip(pre, post, flip):
    stats = {"pre": {"n": 1, "win_rate": 1.0, "net_expr": pre},
             "straddle": {"n": 0, "win_rate": None, "net_expr": None},
             "post": {"n": 1, "win_rate": 0.0, "net_expr": post}}
    assert eras.sign_flip(stats) is flip
    assert eras.sign_flip(None) is False


def test_the_boundary_is_a_utc_deploy_time_not_the_commit_time():
    assert eras.ERA_BOUNDARY_UTC.utcoffset() == dt.timedelta(0)
    assert eras.ERA_BOUNDARY_UTC != dt.datetime(2026, 9, 11, 7, 59, 35, tzinfo=UTC)
    assert eras.ERA_BOUNDARY_UTC > dt.datetime(2026, 9, 11, 7, 59, 35, tzinfo=UTC)
    assert eras.ERA_BOUNDARY_SOURCE.strip()


def test_cell_json_carries_eras_and_notes():
    cell = cells.CellStats(id="a=b", cut="a", value="b", n=1, weeks=1, win_rate=1.0,
                           net_expr=1.0, gross_expr=1.0, delta=None, ci=None, p=None, q=None,
                           thin=True)
    assert cell.to_json()["eras"] is None and cell.to_json()["notes"] == []
    cell.eras = {"pre": {"n": 1, "win_rate": 1.0, "net_expr": 1.0}}
    cell.notes.append("era sign flip")
    out = cell.to_json()
    assert out["eras"] == cell.eras and out["eras"] is not cell.eras
    assert out["notes"] == ["era sign flip"]


def _md_cell(**over):
    base = {"id": "regime=x", "cut": "regime", "value": "x", "n": 40, "weeks": 10,
            "win_rate": 0.5, "net_expr": 0.1, "gross_expr": 0.12, "delta": 0.05,
            "ci": [0.01, 0.09], "p": 0.04, "q": 0.08, "thin": False, "bar_covered_n": None,
            "extra": {"tickers": 1, "top_ticker_share": 1.0}, "notes": ["era sign flip"],
            "eras": {"pre": {"n": 30, "win_rate": 0.6, "net_expr": 0.25},
                     "straddle": {"n": 0, "win_rate": None, "net_expr": None},
                     "post": {"n": 10, "win_rate": 0.2, "net_expr": -0.35}}}
    base.update(over)
    return base


def test_the_markdown_row_shows_the_eras_and_the_flip_note():
    data = {"header": {"window": ["2026-01-08", "2026-10-26"], "n": 40, "pooled_net_expr": 0.1,
                       "pooled_win_rate": 0.5, "net_of_frictions": "modelled", "cells_tested": 1,
                       "bar_covered_n": 0, "resamples": 200, "seed": 42, "notes": [],
                       "era_boundary": {"utc": "2026-09-11T14:00:00Z", "source": "deploy log"}},
            "cells": [_md_cell()], "tallies": [],
            "giveback": {"n": 0, "mean": None, "median": None}}
    md = report.render_markdown(data).splitlines()
    assert ("- Exit-model era boundary (production deploy of b4ef2e87): 2026-09-11T14:00:00Z "
            "(source: deploy log); era columns carry no CI and no q") in md
    assert any("| eras pre / straddle / post (N WR net) |" in line for line in md)
    row = next(line for line in md if line.startswith("| regime=x |"))
    assert "| 30 60.0% +0.250 / 0 n/a / 10 20.0% -0.350 |" in row
    assert "era sign flip" in row
```

In `tests/scout/test_book_autopsy.py`, update the exact line in `test_markdown_keeps_pipe_delimited_cell_ids_in_one_column` (the `_synthetic` cells carry no `eras`):

```python
    assert line == (
        "| strategy_horizon=RSI\\|2w | 40 | 10 | 50.0% | 0.100 | 0.120 | "
        "+0.050 [0.010, 0.090] | 0.080 | n/a | tickers 1; top share 100.0% |")
```

and add:

```python
def test_every_cell_carries_three_eras_and_the_header_the_boundary(tmp_path):
    from autopsy import eras
    data = _build(tmp_path)
    assert data["header"]["era_boundary"] == {
        "utc": eras.ERA_BOUNDARY_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": eras.ERA_BOUNDARY_SOURCE}
    for cell in data["cells"]:
        assert set(cell["eras"]) == set(eras.ERAS), cell["id"]
        assert cell["eras"]["pre"]["n"] == cell["n"], cell["id"]   # fixture trades close Jan-Apr 2026
        assert cell["notes"] == []
    assert len(report.render_markdown(data).splitlines()) <= report.MD_MAX_LINES
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_eras.py`
Expected: a collection error, `ImportError: cannot import name 'eras'`.

- [ ] **Step 3: Copy the boundary from V200-1 and implement `eras.py`**

1. Read the json block in `<wt>/docs/superpowers/results/2026-10-29-v200-prod-reads.md`. Write `ERA_BOUNDARY_UTC = dt.datetime(<Y>, <M>, <D>, <h>, <m>, <s>, tzinfo=dt.timezone.utc)` from `era_boundary_utc` and `ERA_BOUNDARY_SOURCE = "<era_boundary_source>"` verbatim, with a comment naming the results file.
   - If the file or the key is missing, stop and return `BLOCKED: V200-1 boundary not recorded`.
   - The commit time is never a fallback (index cross-task contracts).
2. The module docstring carries the rule table above and the sentence "Era numbers carry no CI and no q; the merge never reads them."
3. Compute the boundary's Eastern date as `boundary.astimezone(US_MARKET_TZ).date()`. Compute the opened date the same way.

- [ ] **Step 4: Wire it into `cells.py` and `report.py`**

- **`cells.py`:** add the two `CellStats` fields after `extra` (keep every existing positional field order). `to_json` adds `"eras": None if self.eras is None else {k: dict(v) for k, v in self.eras.items()}` and `"notes": list(self.notes)`.
- **`report.py`:**
  - **`_decorate`:** set `cell.eras = eras.era_stats(members)`, and append `"era sign flip"` to `cell.notes` when `eras.sign_flip(cell.eras)`.
  - **`build_report`:** add `era_boundary={"utc": eras.ERA_BOUNDARY_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": eras.ERA_BOUNDARY_SOURCE}` to the `header.update(...)` call.
  - **`_header_lines`:** after the cells-tested line, append the boundary line when `h.get("era_boundary")` is present.
  - **New `_eras_text(c: dict) -> str`:** returns `n/a` when `c.get("eras")` is falsy.
  - **`_cell_row`:** insert ` {_eras_text(c)} |` between the q column and the notes column.
  - **`_cell_lines`:** add the column to the header row, and add one `---|` to the separator row.
  - **`_extra_text`:** append `c.get("notes", [])` entries to `parts`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_eras.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_cells.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_stall_report.py
python -m radon cc -s -n C <wt>/scripts/reports/autopsy/eras.py <wt>/scripts/reports/autopsy/report.py <wt>/scripts/reports/autopsy/cells.py
```

Expected: every run reports `0 failed`, and radon prints nothing.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/reports/autopsy/eras.py scripts/reports/autopsy/cells.py \
    scripts/reports/autopsy/report.py tests/scout/test_autopsy_eras.py tests/scout/test_book_autopsy.py
git -C <wt> commit -m "feat(autopsy): v200 pre/straddle/post era numbers per cell around the b4ef2e87 deploy (V200-11)"
```

### Task V200-12: Gap bucket names and the sign note

**Model:** haiku — a mechanical rename plus one fixed sentence copied into named files; thresholds and logic are untouched.

**Files:**
- Modify: `scripts/reports/autopsy/bars.py` (`GAP_LARGE_PCT` comment, `_gap` docstring, `_open_gap_bucket`, new `GAP_SIGN_NOTE`)
- Modify: `scripts/reports/autopsy/report.py` (`NOTES`)
- Modify: `tests/scout/test_autopsy_bars.py`, `tests/scout/test_book_autopsy.py` (`test_bar_cells_carry_bar_covered_n`)
- Modify: `.claude/skills/exit-harvester/SKILL.md`, `.claude/skills/setup-scout/SKILL.md`, `.claude/skills/regime-desk/SKILL.md` (last bullet of `## Checklist`)
- Modify: `.claude/agents/scout.md` (end of `## Evidence rule`)
- Modify: `.claude/skills/setup-scout/references/playbook.md` (a paragraph right before `` ## `gap-and-hold` ``)
- Regenerate: the `.agents/` / `.codex/` mirrors that `scripts/dev/sync_codex.py` writes for those files

**Interfaces:**
- Consumes: nothing from earlier tasks. It runs after V200-11 only because both edit `report.py`.
- Produces:
  - `_open_gap_bucket(row) -> str | None` returns one of `open_better` / `flat` / `open_worse_small` / `open_worse_large` (or `None`), with `GAP_FLAT_PCT = 0.25` and `GAP_LARGE_PCT = 1.0` unchanged.
  - `bars.GAP_SIGN_NOTE: str`, exactly:

```python
GAP_SIGN_NOTE = (
    "Gap sign: open_gap_pct compares the fill-day open with the planned entry and is "
    "positive when the open was worse for the trade (higher for a long, lower for a short), "
    "so open_better is an open more than 0.25% on the trade's side of the planned entry, "
    "flat is within 0.25%, open_worse_small is worse by up to 1.0% and open_worse_large "
    "is worse by more than 1.0%.")
```

**Placement:** the sentence appears verbatim, compared after collapsing whitespace, in all of these:
- `bars._gap.__doc__`
- `report.NOTES`, as its last entry (`bars.GAP_SIGN_NOTE` itself)
- the three role skills, as a new last bullet of `## Checklist` (`- ` + the sentence)
- `.claude/agents/scout.md`, as a new last paragraph of `## Evidence rule`
- `playbook.md`, as a paragraph after the "Left out on purpose" paragraph

Past autopsies and slates under `docs/superpowers/results/` are not touched (spec Part 4).

- [ ] **Step 1: Write the failing tests**

In `tests/scout/test_autopsy_bars.py`:
- in `test_a_bullish_stop_entry_that_opens_above_its_trigger_gapped_through`, change `"adverse_large"` to `"open_worse_large"`;
- in `test_a_bearish_limit_that_opens_beyond_its_limit_filled_better`, change `"favourable"` to `"open_better"`;
- append:

```python
@pytest.mark.parametrize("pct, bucket", [
    (-0.26, "open_better"), (-0.25, "flat"), (0.0, "flat"), (0.25, "flat"),
    (0.26, "open_worse_small"), (1.0, "open_worse_small"), (1.01, "open_worse_large"),
    (None, None), (float("nan"), None)])
def test_open_gap_bucket_names_say_which_side_the_open_was_on(pct, bucket):
    row = _trade()
    row.bars = {"open_gap_pct": pct}
    assert bars._open_gap_bucket(row) == bucket


SIGN_NOTE_DOCS = (
    ".claude/skills/exit-harvester/SKILL.md", ".claude/skills/setup-scout/SKILL.md",
    ".claude/skills/regime-desk/SKILL.md", ".claude/agents/scout.md",
    ".claude/skills/setup-scout/references/playbook.md")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_gap_sign_note_names_the_thresholds_it_describes():
    assert f"{bars.GAP_FLAT_PCT}%" in bars.GAP_SIGN_NOTE
    assert f"{bars.GAP_LARGE_PCT}%" in bars.GAP_SIGN_NOTE
    for name in ("open_better", "flat", "open_worse_small", "open_worse_large"):
        assert name in bars.GAP_SIGN_NOTE


@pytest.mark.parametrize("doc", SIGN_NOTE_DOCS)
def test_the_gap_sign_note_is_verbatim_in_every_scout_doc(doc):
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert _flat(bars.GAP_SIGN_NOTE) in _flat(text), doc


def test_the_gap_sign_note_is_in_the_gap_docstring_and_the_autopsy_notes():
    from autopsy import report
    assert _flat(bars.GAP_SIGN_NOTE) in _flat(bars._gap.__doc__)
    assert report.NOTES[-1] == bars.GAP_SIGN_NOTE


def test_no_old_gap_bucket_name_is_left_in_the_autopsy_code():
    source = (ROOT / "scripts" / "reports" / "autopsy" / "bars.py").read_text(encoding="utf-8")
    for old in ('"favourable"', '"adverse_small"', '"adverse_large"'):
        assert old not in source
```

In `tests/scout/test_book_autopsy.py::test_bar_cells_carry_bar_covered_n`:

```python
    assert gaps == {"flat": (20, 20), "open_worse_small": (4, 4)}
```

Then run `git -C <wt> grep -n -E "favourable|adverse_small|adverse_large" -- scripts/reports tests/scout .claude`. Every hit must be one of the edits above or a past-document reference; update any other autopsy test hit the same way.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_bars.py`
Expected: FAIL. The renamed assertions get `favourable` / `adverse_large`, and the new tests fail with `AttributeError: module 'autopsy.bars' has no attribute 'GAP_SIGN_NOTE'`.

- [ ] **Step 3: Implement**

- **`bars.py`:**
  - Add `GAP_SIGN_NOTE` (exact text above) beside `GAP_FLAT_PCT` / `GAP_LARGE_PCT`.
  - Change the `GAP_LARGE_PCT` comment to `# a worse open above this is "open_worse_large"`.
  - In `_open_gap_bucket`, return the new names (same comparisons).
  - Replace `_gap`'s docstring with: `"""Open gap in percent and the gapped-through flag.` followed by a blank line and the sentence, wrapped over lines.
- **`report.py`:** append `bars.GAP_SIGN_NOTE` as the last item of the `NOTES` tuple.
- **The five docs:** add the sentence at the placements listed above, wrapped like the surrounding text.
- **Codex mirror:** regenerate it, then confirm it is current:

```bash
python <wt>/scripts/dev/sync_codex.py
python <wt>/scripts/dev/sync_codex.py --check
```

Expected: the last command prints `Codex mirror is current.`

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_bars.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_generator_roles.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_trade_scout_skill.py
python <wt>/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: every run reports `0 failed`. The markdown budget test in `test_book_autopsy.py` still passes with one more note line.

- [ ] **Step 5: Commit**

Stage the source, test and doc files, plus every mirror path `git -C <wt> status --short -- .agents .codex` lists. Name each path explicitly; never use `git add -A`.

```bash
git -C <wt> status --short -- .agents .codex
git -C <wt> add scripts/reports/autopsy/bars.py scripts/reports/autopsy/report.py \
    tests/scout/test_autopsy_bars.py tests/scout/test_book_autopsy.py \
    .claude/skills/exit-harvester/SKILL.md .claude/skills/setup-scout/SKILL.md \
    .claude/skills/regime-desk/SKILL.md .claude/agents/scout.md \
    .claude/skills/setup-scout/references/playbook.md \
    <each .agents/ and .codex/ path listed above>
git -C <wt> commit -m "feat(autopsy): v200 gap buckets say which side the open was on, with one sign note (V200-12)"
```

