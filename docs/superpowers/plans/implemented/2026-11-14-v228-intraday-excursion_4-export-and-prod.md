# v228 — Intraday MFE/MAE for the journal: Part 4, export and production (V228-15 .. V228-17)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V228-16" -A 400 <this file>`); never read the part whole.

**Spec:** [2026-11-14-v228-intraday-excursion-design.md](../specs/2026-11-14-v228-intraday-excursion-design.md)
**Index:** [2026-11-14-v228-intraday-excursion_0-index.md](2026-11-14-v228-intraday-excursion_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the Task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the book export's column 39 and the autopsy column contract (V228-15), the autopsy's intraday-only excursion cells with its loud refusal of an old CSV and the trade-scout skill aligned (V228-16), and the production run under `mirror-prod` — PITR-drill check, deploy, timeframes check, detached backfill, read-back, record (V228-17).

Cross-part contracts consumed here: V228-15 and V228-16 consume nothing from other parts (the export reads the journal `doc` field `excursion_source` that V228-4 writes and V228-7 stamps, by name only). V228-17 runs what parts 1, 2 and 5 built: revision `v228_001` (V228-7), the refresh-loop pass `loops._run_excursion_pass` (V228-6) whose log line starts `excursion upgrade:` (`UpgradeReport.line()`, V228-5), and the operator script `scripts/ops/backfill_excursions.py` (V228-8: `--checkpoint-dir` default `logs/backfill_excursions.ckpt`, `--report-file` default `logs/backfill_excursions.report.txt`, `--since`; prints `resuming: n/N tickers restored` first and one final `excursion upgrade: …` line, which it also writes to `--report-file`).

Branch rule: V228-15 and V228-16 are implemented in the plan's worktree, never on `main`, each ending with its own scoped commit there. V228-17 runs only after every other task is merged to `main`, pushed and green in CI; its one repo edit (the production record in the index's `## Handoff`) is committed on `main`. Per-task verification is the narrow run named in each task; no task runs the full suite (CI does).

# Phase F — Book export and autopsy

### Task V228-15: Export column 39 `excursion_source` and the autopsy column contract

**Model:** sonnet — two-file column append with pinned shapes; mechanical, but both `UNION` branches and the positional `ORDER BY` must stay aligned.

**Files:**
- Modify: `scripts/ops/export_book_rows.sh` (header comment l.17; trade branch after `plan_issued_at_source` ~l.66; plan branch after `plan_issued_at_source` ~l.106)
- Modify: `scripts/reports/autopsy/rows.py` (`EXPORT_COLUMNS` l.24-32, `LEGACY_EXPORT_COLUMNS` l.34, `BookRow` l.47-86, `_journal_fields` l.195-200, `load_rows` l.240-246)
- Test: `tests/scout/test_export_script.py` (`EXPECTED_COLUMNS` l.18-26; four new tests)
- Test: `tests/scout/test_autopsy_rows.py` (column-shape test l.114-117, old-CSV test l.153-158, wrong-header test l.218-227; new parsing tests)

**Interfaces:**
- Consumes: the journal `doc` field `excursion_source` (`"5min" | "15min" | "hourly" | "daily"` or absent), written by V228-4 and stamped by V228-7 — by name only, no import.
- Produces (V228-16 relies on these exact names):
  - `rows.EXCURSION_COLUMN = "excursion_source"`
  - `rows.EXPORT_COLUMNS` — 39 names, the last is `excursion_source`, `[-3:-1] == ISSUED_COLUMNS`
  - `rows.PRE_EXCURSION_COLUMNS = EXPORT_COLUMNS[:-1]` (38, the v200..v227 export)
  - `rows.LEGACY_EXPORT_COLUMNS` — 36, the same value as today (`PRE_EXCURSION_COLUMNS[:-2]`)
  - `BookRow.excursion_source: str | None = None`, filled by `load_rows` from the column (blank → `None`)
  - `load_rows` in this task still **accepts** the 38- and 36-column shapes (excursion source `None`); V228-16 turns them into a refusal.

**Why the order matters:** `ORDER BY 1 DESC, 21, 8, 2, 3` is positional (row_kind, closed_at, plan_created_at, trade_id, plan_id). Appending the new column **last** in both branches keeps every position; inserting it anywhere else would silently re-sort the export. The plan branch must carry `NULL::text AS excursion_source` or the `UNION` fails on column count.

- [ ] **Step 1: Write the failing tests — export script**

In `tests/scout/test_export_script.py`, append `"excursion_source"` to `EXPECTED_COLUMNS` (after `"plan_issued_at_source"`):

```python
EXPECTED_COLUMNS = (
    "row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction",
    "plan_created_at", "plan_first_status_at", "plan_status", "plan_status_reason",
    "entry_type", "expiry_bars", "valid_session", "planned_entry", "opened_at", "entry",
    "stop_loss", "take_profit", "target2", "closed_at", "exit_price", "close_reason",
    "last_leg_reason", "outcome", "r_realized", "mfe_r", "mae_r", "exit_efficiency",
    "holding_days", "stop_width_atr", "atr_pct", "regime2_state", "session_bucket",
    "days_to_earnings", "rs_percentile", "plan_issued_at", "plan_issued_at_source",
    "excursion_source",
)
```

Append these tests at the end of the file:

```python
def test_excursion_source_is_column_39_in_both_branches(source):
    trade_aliases, plan_aliases = select_aliases(source)
    assert len(trade_aliases) == len(plan_aliases) == 39
    assert trade_aliases[38] == plan_aliases[38] == "excursion_source"
    assert "j.doc->>'excursion_source' AS excursion_source" in source
    assert "NULL::text AS excursion_source" in source


def test_the_positional_order_by_is_unchanged(source):
    assert "ORDER BY 1 DESC, 21, 8, 2, 3" in source
    trade_aliases, _ = select_aliases(source)
    assert [trade_aliases[i - 1] for i in (1, 21, 8, 2, 3)] == [
        "row_kind", "closed_at", "plan_created_at", "trade_id", "plan_id"]


def test_the_header_comment_counts_39_columns(source):
    assert "rows: 39" in source
    assert "rows: 38" not in source


def test_the_excursion_column_reads_the_journal_doc(source, book_rows_db):
    book_rows_db.execute(
        "UPDATE journal_entries SET doc = ? WHERE trade_id = 'closed-trade'",
        ('{"excursion_source": "5min", "mfe_r": 0.31}',))
    cursor = book_rows_db.execute(_sqlite_query(source))
    names = [column[0] for column in cursor.description]
    kind, tid, pid, src = (names.index(n) for n in ("row_kind", "trade_id", "plan_id",
                                                     "excursion_source"))
    got = {(row[kind], row[tid] or row[pid]): row[src] for row in cursor.fetchall()}
    assert got[("trade", "closed-trade")] == "5min"
    assert got[("trade", "orphan-closed-trade")] is None          # doc '{}': no source yet
    assert got[("plan", "unfilled-plan")] is None                 # plan rows are NULL
    assert got[("plan", "open-plan")] is None
```

(`select_aliases`, `_sqlite_query` and the `book_rows_db` fixture already exist in this file; `test_both_selects_list_the_export_columns_in_order` and `test_rows_include_each_plan_and_preserve_closed_trades` now pin 39 columns through `EXPECTED_COLUMNS` with no further edit.)

- [ ] **Step 2: Write the failing tests — autopsy rows**

In `tests/scout/test_autopsy_rows.py`:

1. Add `"excursion_source": "5min"` to the `TRADE` dict (after `"rs_percentile": "81"`).

2. Replace `test_export_columns_end_with_the_issued_columns` with:

```python
def test_export_columns_end_with_the_issued_then_the_excursion_column():
    assert len(rows.EXPORT_COLUMNS) == 39
    assert rows.EXCURSION_COLUMN == "excursion_source"
    assert rows.EXPORT_COLUMNS[-1] == rows.EXCURSION_COLUMN
    assert rows.EXPORT_COLUMNS[-3:-1] == rows.ISSUED_COLUMNS == ("plan_issued_at", "plan_issued_at_source")
    assert rows.PRE_EXCURSION_COLUMNS == rows.EXPORT_COLUMNS[:-1]
    assert len(rows.PRE_EXCURSION_COLUMNS) == 38
    assert rows.LEGACY_EXPORT_COLUMNS == rows.EXPORT_COLUMNS[:-3]
    assert len(rows.LEGACY_EXPORT_COLUMNS) == 36
    assert rows.LEGACY_EXPORT_COLUMNS[-1] == "rs_percentile"
```

3. In `test_an_old_csv_without_the_issued_columns_loads_with_unknown_hours`, change the column argument from `columns=EXPECTED_COLUMNS[:-2]` to `columns=rows.LEGACY_EXPORT_COLUMNS` and add `assert trade.excursion_source is None` at the end.

4. In `test_a_wrong_header_is_still_refused_naming_the_gap`, replace the loop's three shapes — the third, `list(EXPECTED_COLUMNS[:-1])`, is now the accepted 38-column export — with four shapes that are still wrong:

```python
    for columns in ([c for c in EXPECTED_COLUMNS if c != "rs_percentile"],
                    [c for c in EXPECTED_COLUMNS[:-3] if c != "rs_percentile"],
                    list(EXPECTED_COLUMNS[:-2]),                       # 37: half the issued pair
                    [*EXPECTED_COLUMNS[:-3], "excursion_source"]):     # 37: no issued pair
        path = _write_csv(tmp_path, [TRADE], columns=columns)
        with pytest.raises(ValueError, match="missing"):
            rows.load_rows(path)
```

Keep the function's last three lines (the `rs_percentile` match) unchanged.

5. Append these tests:

```python
def test_every_book_row_has_no_excursion_source_by_default():
    assert BookRow().excursion_source is None


def test_a_trade_row_carries_its_excursion_source(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [TRADE]))
    assert row.excursion_source == "5min"


@pytest.mark.parametrize("value", ["daily", "hourly", "15min"])
def test_every_source_name_passes_through_verbatim(tmp_path, value):
    [row] = rows.load_rows(_write_csv(tmp_path, [dict(TRADE, excursion_source=value)]))
    assert row.excursion_source == value


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_excursion_source_is_none(tmp_path, value):
    [row] = rows.load_rows(_write_csv(tmp_path, [dict(TRADE, excursion_source=value)]))
    assert row.excursion_source is None


def test_a_plan_row_has_no_excursion_source(tmp_path):
    _, plan = rows.load_rows(_write_csv(tmp_path, [TRADE, PLAN]))
    assert plan.excursion_source is None


def test_a_38_column_export_still_loads_until_the_refusal_lands(tmp_path):
    """V228-15 keeps the v200 shape loading; V228-16 turns it into a refusal."""
    path = _write_csv(tmp_path, [TRADE], columns=rows.PRE_EXCURSION_COLUMNS)
    [row] = rows.load_rows(path)
    assert row.excursion_source is None
    assert (row.plan_hour, row.hour_source) == (9, "live")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_export_script.py`
Expected: FAIL — `test_both_selects_list_the_export_columns_in_order`, `test_excursion_source_is_column_39_in_both_branches`, `test_the_header_comment_counts_39_columns`, `test_the_excursion_column_reads_the_journal_doc`, `test_rows_include_each_plan_and_preserve_closed_trades` (38 aliases against 39 expected).

Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Expected: FAIL — `AttributeError: module 'autopsy.rows' has no attribute 'EXCURSION_COLUMN'`, and header refusals for the 39-column `TRADE` CSV.

- [ ] **Step 4: Implement — the export script**

In `scripts/ops/export_book_rows.sh`, replace the header comment line

```bash
# The output columns are fixed (rows: 38, the last two plan_issued_at and plan_issued_at_source, appended by v200); tests/scout/test_export_script.py pins them.
```

with

```bash
# The output columns are fixed (rows: 39: plan_issued_at and plan_issued_at_source
# appended by v200, then excursion_source -- the bars that measured mfe_r/mae_r --
# appended last by v228 so the positional ORDER BY keeps its meaning);
# tests/scout/test_export_script.py pins them.
```

Trade branch — the last two select lines become three:

```sql
    p.doc->>'issued_at' AS plan_issued_at,
    p.doc->>'issued_at_source' AS plan_issued_at_source,
    j.doc->>'excursion_source' AS excursion_source
  FROM journal_entries j
```

Plan branch — likewise:

```sql
    p.doc->>'issued_at' AS plan_issued_at,
    p.doc->>'issued_at_source' AS plan_issued_at_source,
    NULL::text AS excursion_source
  FROM plans p
```

Leave `ORDER BY 1 DESC, 21, 8, 2, 3` untouched. Write no SQL write keyword in the comment (the guard test scans comments too) and do not name the interpreter that `test_no_python_runs_on_the_vm` forbids.

- [ ] **Step 5: Implement — `scripts/reports/autopsy/rows.py`**

Replace the column block (l.23-34):

```python
ISSUED_COLUMNS = ("plan_issued_at", "plan_issued_at_source")
#: v228: the bars that measured mfe_r / mae_r (``5min`` .. ``daily``); blank on plan rows.
EXCURSION_COLUMN = "excursion_source"
EXPORT_COLUMNS = (
    "row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction",
    "plan_created_at", "plan_first_status_at", "plan_status", "plan_status_reason",
    "entry_type", "expiry_bars", "valid_session", "planned_entry", "opened_at", "entry",
    "stop_loss", "take_profit", "target2", "closed_at", "exit_price", "close_reason",
    "last_leg_reason", "outcome", "r_realized", "mfe_r", "mae_r", "exit_efficiency",
    "holding_days", "stop_width_atr", "atr_pct", "regime2_state", "session_bucket",
    "days_to_earnings", "rs_percentile", *ISSUED_COLUMNS, EXCURSION_COLUMN,
)
#: Exports written v200..v227: issue-time columns, no excursion source.
PRE_EXCURSION_COLUMNS = EXPORT_COLUMNS[:-1]
#: Exports written before v200: no issue-time columns; every hour reads as unknown.
LEGACY_EXPORT_COLUMNS = PRE_EXCURSION_COLUMNS[:-2]
```

In `BookRow`, after `exit_efficiency: float | None = None`, add:

```python
    excursion_source: str | None = None
```

In `_journal_fields`, before `return out`, add (`raw.get`, because an older header has no such key):

```python
    out["excursion_source"] = _text(raw.get(EXCURSION_COLUMN))
```

In `load_rows`, accept both older shapes for now:

```python
    _check_header(reader.fieldnames, EXPORT_COLUMNS, str(path),
                  accepted=(PRE_EXCURSION_COLUMNS, LEGACY_EXPORT_COLUMNS))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_export_script.py`
Expected: PASS (the bash-run tests may skip on a WSL bash, as before).

Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Expected: PASS.

The fixture writers that build CSVs from `rows.EXPORT_COLUMNS` now write 39 columns with a blank source; they must stay green unchanged:

Run: `python scripts/dev/testrun.py file tests/scout/test_book_autopsy.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_stall_report.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_exclusions.py`
Run: `python scripts/dev/testrun.py file tests/scripts/test_book_autopsy_entry_type.py`
Expected: PASS, all four.

- [ ] **Step 7: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: no new violation (`_journal_fields` and `load_rows` gain no branch).

- [ ] **Step 8: Commit**

```bash
git add scripts/ops/export_book_rows.sh scripts/reports/autopsy/rows.py tests/scout/test_export_script.py tests/scout/test_autopsy_rows.py
git commit -m "feat(v228): book export column 39 excursion_source and the autopsy column contract (V228-15)"
```
### Task V228-16: Autopsy: intraday-only MFE cells, drop count, loud refusal, `--no-excursion-cells`

**Model:** sonnet — bounded change across four autopsy modules with fixture tests; the refusal path is the one judgement call and is spelled out below.

**Files:**
- Modify: `scripts/reports/autopsy/rows.py` (`INTRADAY_SOURCES`, `MissingExcursionColumn`, `load_rows(..., allow_no_excursion=False)`)
- Modify: `scripts/reports/autopsy/exits.py` (`giveback_summary` l.96-102)
- Modify: `scripts/reports/autopsy/report.py` (`build_report` l.115-142, `_giveback_lines` l.266-268)
- Modify: `scripts/reports/book_autopsy.py` (`_parser`, `main`)
- Test: `tests/scout/test_autopsy_exits.py` (give-back test l.91-95)
- Test: `tests/scout/test_book_autopsy.py` (`_trade` fixture l.40-55; new CLI tests)
- Test: `tests/scout/test_autopsy_rows.py` (the two old-shape tests V228-15 left loading; new refusal tests)

One file beyond the ledger row, inside group F and touched by no other part: `tests/scout/test_autopsy_rows.py` must change because the refusal flips its two old-shape tests. The ledger row's skill alignment and Codex mirror are split out as **V228-16b** (this task passed 20 KB); V228-16b runs straight after this task, before the branch merges.

**Interfaces:**
- Consumes (V228-15): `rows.EXCURSION_COLUMN`, `rows.EXPORT_COLUMNS` (39), `rows.PRE_EXCURSION_COLUMNS` (38), `rows.LEGACY_EXPORT_COLUMNS` (36), `BookRow.excursion_source`.
- Produces:
  - `rows.INTRADAY_SOURCES = ("5min", "15min", "hourly")` — the same value as `swingbot.core.analytics.mfe_mae.INTRADAY_SOURCES` (V228-2); a literal here so the autopsy, which runs on the dev machine against an export, never imports pandas-heavy analytics; a test pins the two equal.
  - `class MissingExcursionColumn(ValueError)` — raised by `load_rows` for a 38- or 36-column export unless `allow_no_excursion=True`; its message names the fix.
  - `rows.load_rows(path, *, frictions=None, input_fingerprints=None, allow_no_excursion=False) -> list[BookRow]`
  - `exits.giveback_summary(trades) -> {"n": int, "mean": float | None, "median": float | None, "dropped": int}` — only trades with an intraday `excursion_source`; `dropped` counts trades that had both `mfe_r` and `gross_r` but a daily or missing source.
  - `report.build_report(..., excursion_cells: bool = True)`; with `False` the give-back block is `{"n": 0, "mean": None, "median": None, "dropped": <trades>, "omitted": True}` and the header notes carry `report.EXCURSION_OMITTED_NOTE`.
  - CLI `book_autopsy.py --no-excursion-cells`; an old CSV without it exits **2** with the message on stderr and writes nothing.

**Rule (Global Constraints):** MFE/MAE-derived cells come from intraday-source rows only, with the dropped count printed; a 38- or 36-column CSV stops with a message naming the fix unless `--no-excursion-cells`. The only MFE-derived cell in `scripts/reports/autopsy/` is `giveback_summary` (checked: `git grep -n "mfe_r\|mae_r\|exit_efficiency" -- scripts/reports/autopsy` hits only `rows.py` and `exits.py:96-98`). The autopsy rule is source-only (not the admin trust rule with `holding_days >= 2`): a `daily` row is dropped whatever its hold.

`scripts/reports/autopsy/exclusions.py:main` also calls `load_rows(args.rows)`; it rebuilds stall trade ids from a fresh export, so it keeps the default and an old CSV is refused there too. Leave it unchanged.

- [ ] **Step 1: Write the failing tests — give-back (`tests/scout/test_autopsy_exits.py`)**

Replace `test_giveback_covers_losers_as_well_as_winners` with:

```python
def test_giveback_covers_losers_as_well_as_winners_on_intraday_rows():
    trades = [_row(mfe_r=2.0, gross_r=1.0, excursion_source="5min"),
              _row(mfe_r=1.5, gross_r=-1.0, excursion_source="hourly"),
              _row(mfe_r=None, gross_r=0.3, excursion_source="5min")]
    assert exits.giveback_summary(trades) == {"n": 2, "mean": 1.75, "median": 1.75, "dropped": 0}


def test_giveback_drops_daily_and_unsourced_rows_and_counts_them():
    trades = [_row(mfe_r=0.31, gross_r=-1.0, excursion_source="15min"),
              _row(mfe_r=1.24, gross_r=-1.0, excursion_source="daily"),
              _row(mfe_r=1.67, gross_r=0.0, excursion_source=None),
              _row(mfe_r=None, gross_r=-1.0, excursion_source="daily")]   # no mfe: not "dropped"
    assert exits.giveback_summary(trades) == {"n": 1, "mean": 1.31, "median": 1.31, "dropped": 2}


def test_giveback_with_every_row_dropped_has_no_figures():
    trades = [_row(mfe_r=2.0, gross_r=1.0, excursion_source="daily")]
    assert exits.giveback_summary(trades) == {"n": 0, "mean": None, "median": None, "dropped": 1}


def test_giveback_of_an_empty_book():
    assert exits.giveback_summary([]) == {"n": 0, "mean": None, "median": None, "dropped": 0}


def test_intraday_sources_match_the_journal_core():
    assert rows.INTRADAY_SOURCES == ("5min", "15min", "hourly")
    from swingbot.core.analytics import mfe_mae
    assert tuple(mfe_mae.INTRADAY_SOURCES) == rows.INTRADAY_SOURCES
```

(`mfe_mae.INTRADAY_SOURCES` lands with V228-2, which runs before this task; if this task is somehow run first, that last test fails with an `AttributeError` — stop and merge V228-2, do not delete the assertion.)

- [ ] **Step 2: Write the failing tests — loader refusal (`tests/scout/test_autopsy_rows.py`)**

Replace V228-15's `test_a_38_column_export_still_loads_until_the_refusal_lands` with:

```python
@pytest.mark.parametrize("shape", ["PRE_EXCURSION_COLUMNS", "LEGACY_EXPORT_COLUMNS"])
def test_an_export_without_the_excursion_column_is_refused_naming_the_fix(tmp_path, shape):
    path = _write_csv(tmp_path, [TRADE], columns=getattr(rows, shape))
    with pytest.raises(rows.MissingExcursionColumn) as err:
        rows.load_rows(path)
    text = str(err.value)
    assert "excursion_source" in text
    assert "scripts/ops/export_book_rows.sh" in text
    assert "--no-excursion-cells" in text
    assert str(path) in text
    assert isinstance(err.value, ValueError)


def test_a_38_column_export_loads_when_excursion_cells_are_waived(tmp_path):
    path = _write_csv(tmp_path, [TRADE], columns=rows.PRE_EXCURSION_COLUMNS)
    [row] = rows.load_rows(path, allow_no_excursion=True)
    assert row.excursion_source is None
    assert (row.plan_hour, row.hour_source) == (9, "live")


def test_the_waiver_still_reads_a_current_export(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [TRADE]), allow_no_excursion=True)
    assert row.excursion_source == "5min"


def test_the_waiver_never_accepts_a_wrong_header(tmp_path):
    columns = [c for c in EXPECTED_COLUMNS[:-1] if c != "rs_percentile"]
    path = _write_csv(tmp_path, [TRADE], columns=columns)
    with pytest.raises(ValueError, match="rs_percentile") as err:
        rows.load_rows(path, allow_no_excursion=True)
    assert not isinstance(err.value, rows.MissingExcursionColumn)
```

In `test_an_old_csv_without_the_issued_columns_loads_with_unknown_hours`, change the call to `rows.load_rows(path, allow_no_excursion=True)`.

- [ ] **Step 3: Write the failing tests — report and CLI (`tests/scout/test_book_autopsy.py`)**

In `_trade(i, ticker)`, add `"excursion_source": "5min"` to the returned dict (after `"regime2_state": "bull_quiet"`), so `data["giveback"]["n"] == 48` stays true. Append:

```python
def _write_rows(path: Path, records: list[dict], columns) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for record in records:
            writer.writerow({c: record.get(c, "") for c in columns})
    return path


def test_giveback_counts_rows_without_an_intraday_source_as_dropped(tmp_path):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    records = [dict(_trade(i, "AAA"), excursion_source="daily" if i < 10 else "5min")
               for i in range(48)]
    _write_rows(rows_csv, records, rows.EXPORT_COLUMNS)
    data = report.build_report(rows.load_rows(rows_csv), rows.load_rejections(rej_csv),
                               bars_dir=bars_dir, n_resamples=200, seed=42, balance=10_000.0)
    assert (data["giveback"]["n"], data["giveback"]["dropped"]) == (38, 10)
    md = report.render_markdown(data)
    assert "## Give-back (mfe_r minus gross R, intraday-measured trades)" in md
    assert "; dropped 10 (mfe_r from daily bars or no source)" in md


def test_the_cli_refuses_an_export_without_the_excursion_column(tmp_path, capsys):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    _write_rows(rows_csv, [_trade(i, "AAA") for i in range(4)], rows.PRE_EXCURSION_COLUMNS)
    out = tmp_path / "results"
    code = script.main([str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir),
                        "--out-dir", str(out), "--date", "2026-11-20", *FAST])
    err = capsys.readouterr().err
    assert code == 2
    assert "excursion_source" in err and "--no-excursion-cells" in err
    assert not out.exists()


def test_the_cli_waiver_builds_every_other_cell_and_says_so(tmp_path, capsys):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    _write_rows(rows_csv, [_trade(i, ("AAA", "BBB")[i % 2]) for i in range(48)],
                rows.LEGACY_EXPORT_COLUMNS)
    out = tmp_path / "results"
    code = script.main([str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir),
                        "--out-dir", str(out), "--date", "2026-11-20", *FAST,
                        "--no-excursion-cells"])
    printed = capsys.readouterr().out
    assert code == 0
    assert "excursion cells left out (--no-excursion-cells)" in printed
    data = json.loads((out / "2026-11-20-book-autopsy.json").read_text(encoding="utf-8"))
    assert data["giveback"] == {"n": 0, "mean": None, "median": None, "dropped": 48, "omitted": True}
    assert report.EXCURSION_OMITTED_NOTE in data["header"]["notes"]
    assert data["header"]["n"] == 48 and data["cells"]
    md = (out / "2026-11-20-book-autopsy.md").read_text(encoding="utf-8")
    assert "- left out (--no-excursion-cells): the export has no excursion_source column" in md


def test_the_cli_prints_the_giveback_drop_count(tmp_path, capsys):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    code = script.main([str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir),
                        "--out-dir", str(tmp_path / "results"), "--date", "2026-11-20", *FAST])
    assert code == 0
    assert "give-back N 48, dropped 0 (no intraday excursion source)" in capsys.readouterr().out


def test_an_older_report_without_a_drop_count_still_renders():
    g = {"n": 3, "mean": 1.0, "median": 1.0}
    assert report._giveback_lines(g)[2] == "- N 3; mean 1.000; median 1.000"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_book_autopsy.py`
Expected: FAIL in each — missing `dropped` key / `INTRADAY_SOURCES`, `MissingExcursionColumn` not defined, unknown `--no-excursion-cells` argument.

- [ ] **Step 5: Implement — `scripts/reports/autopsy/rows.py`**

After `LEGACY_EXPORT_COLUMNS = ...` add:

```python
#: v228: sources measured on intraday bars; equal to mfe_mae.INTRADAY_SOURCES (pinned by a test).
INTRADAY_SOURCES = ("5min", "15min", "hourly")
#: Accepted header shapes that carry no excursion source (refused unless waived).
_NO_EXCURSION_SHAPES = (PRE_EXCURSION_COLUMNS, LEGACY_EXPORT_COLUMNS)


class MissingExcursionColumn(ValueError):
    """An export written before v228: its mfe_r / mae_r cannot be told daily from intraday."""
```

Add a helper above `load_rows` and route the header through it:

```python
def _check_excursion_header(found, path: Path, allow_no_excursion: bool) -> None:
    if allow_no_excursion or tuple(found or ()) not in _NO_EXCURSION_SHAPES:
        return
    raise MissingExcursionColumn(
        f"{path}: export has no excursion_source column (written before v228), so its "
        "mfe_r/mae_r cannot be told daily from intraday. Fix: re-export with "
        "scripts/ops/export_book_rows.sh rows, or pass --no-excursion-cells to build "
        "every other cell and leave the excursion cells out.")


def load_rows(path: Path, *, frictions: dict | None = None,
              input_fingerprints: dict | None = None,
              allow_no_excursion: bool = False) -> list[BookRow]:
    """Every export row, using one explicit friction snapshot and exact input hash.

    A 38- or 36-column export raises MissingExcursionColumn unless
    ``allow_no_excursion`` (the CLI's --no-excursion-cells)."""
    settings = frictions if frictions is not None else friction_settings()
    reader = csv.DictReader(StringIO(read_input(path, input_fingerprints), newline=""))
    _check_excursion_header(reader.fieldnames, path, allow_no_excursion)
    _check_header(reader.fieldnames, EXPORT_COLUMNS, str(path), accepted=_NO_EXCURSION_SHAPES)
    return [_row(raw, settings) for raw in reader]
```

- [ ] **Step 6: Implement — `scripts/reports/autopsy/exits.py`**

Add `from .rows import INTRADAY_SOURCES` beside `from .cells import Tally`, and replace `giveback_summary`:

```python
def giveback_summary(trades: list) -> dict:
    """``mfe_r - gross_r`` over every trade whose mfe_r was measured on intraday bars
    -- losers included. ``dropped``: trades with both figures but a daily or missing
    ``excursion_source`` (v228: a daily bar's range includes price before the fill
    and after the exit, so its mfe_r overstates a short hold)."""
    measured = [r for r in trades if r.mfe_r is not None and r.gross_r is not None]
    kept = [r for r in measured if r.excursion_source in INTRADAY_SOURCES]
    dropped = len(measured) - len(kept)
    if not kept:
        return {"n": 0, "mean": None, "median": None, "dropped": dropped}
    values = [r.mfe_r - r.gross_r for r in kept]
    return {"n": len(values), "mean": _mean(values),
            "median": round(statistics.median(values), 4), "dropped": dropped}
```

- [ ] **Step 7: Implement — `scripts/reports/autopsy/report.py`**

Near the module constants add:

```python
EXCURSION_OMITTED_NOTE = ("excursion cells left out (--no-excursion-cells): the export has no "
                          "excursion_source column, so give-back is not computed")
_GIVEBACK_TITLE = "## Give-back (mfe_r minus gross R, intraday-measured trades)"


def _giveback(trades: list, excursion_cells: bool) -> dict:
    if excursion_cells:
        return exits.giveback_summary(trades)
    return {"n": 0, "mean": None, "median": None, "dropped": len(trades), "omitted": True}
```

`build_report` gains the keyword `excursion_cells: bool = True` (after `exclusions_path`); after `header["alert_hour_coverage"] = coverage` add

```python
    if not excursion_cells:
        header["notes"].append(EXCURSION_OMITTED_NOTE)
```

and its return uses `"giveback": _giveback(trades, excursion_cells)`. Replace `_giveback_lines` (`.get` keeps older report JSONs without `dropped`/`omitted` rendering, as the existing fixtures in `test_autopsy_eras.py`, `test_autopsy_stall_report.py` and `test_book_autopsy.py` require):

```python
def _giveback_lines(g: dict) -> list[str]:
    if g.get("omitted"):
        body = "- left out (--no-excursion-cells): the export has no excursion_source column"
    else:
        dropped = g.get("dropped")
        tail = "" if dropped is None else f"; dropped {dropped} (mfe_r from daily bars or no source)"
        body = f"- N {g['n']}; mean {_fmt(g['mean'])}; median {_fmt(g['median'])}{tail}"
    return [_GIVEBACK_TITLE, "", body, ""]
```

- [ ] **Step 8: Implement — `scripts/reports/book_autopsy.py`**

Import `MissingExcursionColumn` with the other `autopsy.rows` names. In `_parser`, after `--no-exclusions`:

```python
    p.add_argument("--no-excursion-cells", action="store_true",
                   help="accept an export without excursion_source (pre-v228) and leave the "
                        "MFE/MAE-derived cells out")
```

Add two helpers above `main`:

```python
def _load(args, frictions: dict, inputs: dict) -> list:
    return filter_entry_type(load_rows(args.rows, frictions=frictions, input_fingerprints=inputs,
                                       allow_no_excursion=args.no_excursion_cells),
                             args.entry_type)


def _giveback_line(g: dict) -> str:
    if g.get("omitted"):
        return "give-back: excursion cells left out (--no-excursion-cells)"
    return f"give-back N {g['n']}, dropped {g['dropped']} (no intraday excursion source)"
```

In `main`, replace the `loaded = filter_entry_type(load_rows(...), args.entry_type)` statement with

```python
    try:
        loaded = _load(args, frictions, inputs)
    except MissingExcursionColumn as exc:
        print(f"book_autopsy: {exc}", file=sys.stderr)
        return 2
```

pass `excursion_cells=not args.no_excursion_cells` to `build_report`, and print `_giveback_line(report["giveback"])` right after the `N ..., bar-covered ...` line.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_book_autopsy.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_stall_report.py`
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_eras.py`
Run: `python scripts/dev/testrun.py file tests/scripts/test_book_autopsy_entry_type.py`
Expected: PASS, all six (the stall-report and entry-type fixtures write blank sources; they compare two runs or never read give-back, so they stay green).

- [ ] **Step 10: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: no new violation (`main` gains one `try`; `_load`, `_giveback_line`, `_giveback`, `_check_excursion_header` are each under 5).

- [ ] **Step 11: Commit**

```bash
git add scripts/reports/autopsy/rows.py scripts/reports/autopsy/exits.py scripts/reports/autopsy/report.py scripts/reports/book_autopsy.py tests/scout/test_autopsy_exits.py tests/scout/test_autopsy_rows.py tests/scout/test_book_autopsy.py
git commit -m "feat(v228): autopsy give-back from intraday-measured rows, refusal of pre-v228 exports, --no-excursion-cells (V228-16)"
```

### Task V228-16b: Trade-scout and exit-harvester skills aligned with the autopsy's excursion rule; Codex mirror

**Model:** haiku — two prose edits, one pin test and a mirror script; no logic.

Split from V228-16 (its first draft passed 20 KB). Runs straight after V228-16 in the same worktree, before the branch merges: once V228-16 lands, the trade-scout skill's Step 1 describes an autopsy that no longer behaves as written, and CLAUDE.md requires an implemented plan to align every skill whose facts it changes in the same work.

**Files:**
- Modify: `.claude/skills/trade-scout/SKILL.md` (Step 1, the `book_autopsy.py` bullet, l.24)
- Modify: `.claude/skills/exit-harvester/SKILL.md` (Checklist, the give-back bullet, l.26) — beyond the ledger row: it says give-back is read "across all trades", which V228-16 makes untrue; group F only, no other part touches it
- Modify (generated): `.agents/skills/trade-scout/SKILL.md`, `.agents/skills/exit-harvester/SKILL.md` via `python scripts/dev/sync_codex.py`
- Test: `tests/scout/test_trade_scout_skill.py` (one new pin)

**Interfaces:**
- Consumes (V228-16): the CLI flag `--no-excursion-cells`; exit code 2 on a 38- or 36-column export; give-back built from `excursion_source` in `5min`, `15min`, `hourly` with a printed drop count.
- Produces: nothing code consumes.

- [ ] **Step 1: Write the failing test**

Append to `tests/scout/test_trade_scout_skill.py` (`_parsed` and `SKILL` already exist there):

```python
def test_autopsy_step_names_the_excursion_refusal_and_its_waiver():
    _, body = _parsed(SKILL)
    step = body[body.index("## Step 1"):body.index("## Step 2")]
    for phrase in ("excursion_source", "--no-excursion-cells", "exits with code 2",
                   "intraday-measured"):
        assert phrase in step, phrase


def test_exit_harvester_reads_giveback_on_intraday_rows_only():
    text = (ROOT / ".claude" / "skills" / "exit-harvester" / "SKILL.md").read_text(encoding="utf-8")
    assert "across all intraday-measured trades" in text
    assert "across all trades in the autopsy" not in text
```

(`ROOT` is the module's repository-root `Path`, already used to build `SKILL`; if the module names it differently, use that name.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scout/test_trade_scout_skill.py`
Expected: FAIL — `excursion_source` absent from Step 1; the exit-harvester line still says "across all trades in the autopsy".

- [ ] **Step 3: Edit the trade-scout skill**

`.claude/skills/trade-scout/SKILL.md`, Step 1 — replace the bullet

```markdown
- `python scripts/reports/book_autopsy.py <scratchpad>/rows.csv <scratchpad>/rejections.csv --bars-dir <scratchpad>/autopsy_bars`.
```

with

```markdown
- `python scripts/reports/book_autopsy.py <scratchpad>/rows.csv <scratchpad>/rejections.csv --bars-dir <scratchpad>/autopsy_bars`. Give-back is built from intraday-measured trades only (`excursion_source` 5min, 15min or hourly; v228) and the run prints how many it dropped. An export without the `excursion_source` column (38 or 36 columns, pre-v228) exits with code 2: re-export, or pass `--no-excursion-cells` to build every other cell without give-back.
```

Keep every phrase `SKILL_PHRASES` pins (`python scripts/reports/book_autopsy.py`, `scripts/ops/export_book_rows.sh`, `scratchpad`, …) — the edit only appends to the bullet.

- [ ] **Step 4: Edit the exit-harvester skill**

`.claude/skills/exit-harvester/SKILL.md`, Checklist — replace the first bullet

```markdown
- Give-back (`mfe_r` minus realised R) across all trades in the autopsy, never winners only; check trail or scale-out headroom against `scripts/reports/runner_headroom.py` before claiming it.
```

with

```markdown
- Give-back (`mfe_r` minus realised R) across all intraday-measured trades in the autopsy (v228: rows on daily bars are dropped and counted), never winners only; check trail or scale-out headroom against `scripts/reports/runner_headroom.py` before claiming it.
```

Leave the frontmatter `description:` untouched (its trigger wording stays the same).

- [ ] **Step 5: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py`
Expected: `.agents/skills/trade-scout/SKILL.md` and `.agents/skills/exit-harvester/SKILL.md` rewritten; a second run prints `Codex mirror is current.`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_trade_scout_skill.py`
Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS, both (the mirror test fails on drift if Step 5 was skipped).

- [ ] **Step 7: Commit (skills and mirror together)**

```bash
git add .claude/skills/trade-scout/SKILL.md .claude/skills/exit-harvester/SKILL.md .agents/skills/trade-scout/SKILL.md .agents/skills/exit-harvester/SKILL.md tests/scout/test_trade_scout_skill.py
git status --short   # nothing else modified under .agents/ or .codex/
git commit -m "docs(v228): trade-scout and exit-harvester skills read give-back on intraday-measured rows; Codex mirror (V228-16b)"
```

# Phase G — Production

### Task V228-17: Production: PITR-drill check, deploy, timeframes check, detached backfill, read-back, mirror

**Model:** opus — production VM work with a data revision and a write-heavy backfill; every step gates the next and a wrong call touches the live book.

**Files:**
- Modify: `docs/superpowers/plans/2026-11-14-v228-intraday-excursion_0-index.md` (`## Handoff`: the production record — the mirror of everything this task does on the VM)
- Scratch only (never committed): `<scratchpad>/v228_readback.sql`, `<scratchpad>/v228_notes_before.txt`, `<scratchpad>/v228_notes_after.txt`, `<scratchpad>/v228_readback_before.txt`, `<scratchpad>/v228_readback_after.txt`

**Interfaces:**
- Consumes: revision `v228_001` (V228-7, applied by `deploy/deploy.sh`'s `alembic upgrade head`); `loops._run_excursion_pass` (V228-6, logs one `excursion upgrade: …` line on the first refresh tick of each UTC date); `scripts/ops/backfill_excursions.py` (V228-8: CLI `--checkpoint-dir` default `logs/backfill_excursions.ckpt`, `--report-file` default `logs/backfill_excursions.report.txt`, `--since`; prints `resuming: n/N tickers restored` first and one final `excursion upgrade: …` line, which it also writes to the report file, then removes the checkpoint directory).
- Produces: nothing code consumes; the Handoff record is what `/close-out` and the results doc read.

**Rules for the whole task (CLAUDE.md, non-negotiable):**
- Every VM command goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"` (stdin piped for SQL), never a raw `ssh`/`scp` or another key. The wrapper expands `$(...)` **locally**: put anything with `$` in a file or a quoted heredoc piped on stdin, never inline.
- Read-only commands (logs, `docker compose ps`, read-only `psql`, `pgbackrest info`, `ls`) need no permission. The two production **changes** are the deploy (with its data revision) and the backfill run; both happen under the `mirror-prod` skill, invoked in Step 2.
- Never print a `.env` value: the timeframes check prints a verdict word only.
- If any gate below fails, stop and ask the partner with `AskUserQuestion` (one question, recommended option first); never work around a gate.
- No full test suite runs here; CI runs it on the push.

**Order matters:** the push of `main` *is* the deploy (`.github/workflows/deploy.yml` runs on `push: branches: [main]`; its `deploy` job runs `deploy/deploy.sh`, which applies `v228_001`). So Steps 1–5 (gates and the "before" snapshot) run **before** the merged work is pushed. If the merge was already pushed when this task starts (check Step 1), record in the Handoff that the PITR check ran after the revision, take the rollback target from the CI deploy job's start time, and carry on.

- [ ] **Step 1: Preconditions on the dev machine**

```bash
git fetch origin
git status --short --branch            # on main, clean apart from known untracked scratch
git log --oneline origin/main..main    # the v228 merge commits not yet pushed (empty = already pushed)
python -m alembic heads                # exactly one head: v228_001
git grep -n "^### Task V228-" docs/superpowers/plans/2026-11-14-v228-intraday-excursion_*.md | wc -l
```

Expected: every task V228-1 .. V228-16b has its commit merged on local `main` (check each id against `git log --oneline --grep "V228-"`); one Alembic head `v228_001`; `git log origin/main..main` lists the v228 merges (not yet pushed). If a task is missing, stop: this task runs last.

Also confirm the backfill script is in the tree the image will be built from: `git ls-files scripts/ops/backfill_excursions.py` prints the path (the Dockerfile's `COPY . .` puts it at `/app/scripts/ops/` in the image; `.dockerignore` excludes nothing under `scripts/`).

- [ ] **Step 2: Invoke `mirror-prod` and write the change down before making it**

Invoke the `mirror-prod` skill. Its Step 3 record, written now in your notes and copied into the Handoff in Step 12:

> Target: the Hetzner VM 167.233.26.185, never this machine. Change 1: deploy of `main` at `<sha>` through CI; `deploy/deploy.sh` runs `alembic upgrade head`, applying `v228_001`, which sets `doc.excursion_source = "daily"` on every `journal_entries` row with a non-null `mfe_r` and no source (downgrade is a no-op). Change 2: one detached run of `scripts/ops/backfill_excursions.py` in the `bot` container, rewriting six journal fields (`mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`, `tags`, `auto_lesson`) through `JournalRepository.patch_if_coarser`, finer-only; checkpoint and report under `/opt/swing-bot/logs/`. No file on the VM is edited by hand; no `.env` change.

- [ ] **Step 3: PITR-drill check (required before a data revision on production)**

`docs/claude/schema-evolution.md` § Before running a data revision on production: the last PITR drill must have passed, and the rollback is `scripts/ops/rollback_to.sh` to the second before the revision ran.

```bash
git grep -n "^### Drill\|^VERDICT" -- docs/deploy/DB_RESTORE.md
```

Expected: the most recent `scripts/ops/pitr_drill.sh` drill (on 2026-11-14: `### Drill 2026-10-01 (v116 V116-10)`, `VERDICT: PASS`) passed. The `### Drill 2026-11-12 (v220 V220-18)` entry is the code-rollback drill, not a PITR drill; do not count it.

Then confirm the PITR repository is healthy now (read-only; the same call `scripts/ops/rollback_to.sh` makes):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T -u postgres db pgbackrest --stanza=swingbot info"
```

Expected: `status: ok`, a full or differential backup dated within the last 8 days, and a WAL archive range whose max is from today. If the last PITR drill did not pass, or `status` is not `ok`, or the newest backup is older than 8 days: stop and ask the partner (recommended option: run `scripts/ops/pitr_drill.sh` per `docs/deploy/DB_RESTORE.md` first).

Record the rollback target now: `date -u +%Y-%m-%dT%H:%M:%SZ` (Git Bash prints UTC; this is `T0`, the second before the revision).

- [ ] **Step 4: Deploy hold**

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/backups/deploy_hold.json 2>/dev/null || echo 'no deploy hold'"
```

Expected: `no deploy hold`. A hold means stop and point the partner at `/rollback --release` (the `/deploy` skill, Step 3).

- [ ] **Step 5: The "before" snapshot (read-only)**

Write the read-back SQL once; Steps 5 and 10 both run it.

```bash
cat > "<scratchpad>/v228_readback.sql" <<'SQL'
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
\echo == sources
SELECT coalesce(j.doc->>'excursion_source', '(none)') AS source,
       count(*) AS n,
       count(*) FILTER (WHERE j.doc->>'mfe_r' IS NOT NULL) AS with_mfe
  FROM journal_entries j
 GROUP BY 1 ORDER BY 1;
\echo == unlabelled rows that carry mfe_r (0 after v228_001)
SELECT count(*) AS unlabelled
  FROM journal_entries j
 WHERE j.doc->>'mfe_r' IS NOT NULL AND j.doc->'excursion_source' IS NULL;
\echo == LONG last-leg losers closed since 2026-10-01: median stored MFE (results doc: 1.24R stored, 0.31R on 5-minute bars)
SELECT count(*) AS losers,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY (j.doc->>'mfe_r')::numeric))::numeric, 2) AS median_mfe_r,
       count(*) FILTER (WHERE (j.doc->>'mfe_r')::numeric >= 1) AS reached_1r
  FROM journal_entries j
  JOIN trades t ON t.trade_id = j.trade_id
 WHERE t.direction = 'bullish'
   AND j.closed_at >= '2026-10-01'
   AND (t.doc->'legs'->(-1))->>'reason' = 'loss'
   AND j.doc->>'mfe_r' IS NOT NULL;
\echo == notes fingerprint (must not change)
SELECT md5(string_agg(j.trade_id || ':' || coalesce(j.doc->>'note', ''), '|' ORDER BY j.trade_id)) AS notes_fp,
       count(*) FILTER (WHERE coalesce(j.doc->>'note', '') <> '') AS with_note,
       count(*) AS rows
  FROM journal_entries j;
SQL
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -X -q -v ON_ERROR_STOP=1" \
  < "<scratchpad>/v228_readback.sql" > "<scratchpad>/v228_readback_before.txt"
cat "<scratchpad>/v228_readback_before.txt"
```

Per-row note hashes (hashes only, never note text), so a changed note can be named:

```bash
cat > "<scratchpad>/v228_notes.sql" <<'SQL'
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
COPY (SELECT trade_id, md5(coalesce(doc->>'note', '')) FROM journal_entries ORDER BY 1) TO STDOUT WITH (FORMAT csv);
SQL
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -X -q -v ON_ERROR_STOP=1" \
  < "<scratchpad>/v228_notes.sql" > "<scratchpad>/v228_notes_before.txt"
wc -l "<scratchpad>/v228_notes_before.txt"
```

Expected before the deploy: `(none)` holds every row (no source exists yet); the losers line shows roughly N 192+ with a median near 1.24; the line count equals `rows`.

- [ ] **Step 6: Deploy (push = deploy) and watch CI**

```bash
git push origin main
gh run list --branch main --limit 1 --json databaseId,headSha,status
gh run watch <databaseId> --exit-status     # run_in_background; you are re-invoked when it ends
```

Expected: every suite job, `docker-build`, `container-healthcheck`, `publish-image` and `deploy` green on the pushed sha. A red test job means no deploy happened: fix the failing test (alone, `testrun.py file …`), push again, and repeat this step (CLAUDE.md § Pipeline watch). A red `deploy` job: read its log (`gh run view <id> --log-failed`), run `prod-incident` if the VM is unhealthy, and stop.

- [ ] **Step 7: Verify the deploy on the VM (read-only)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot test -f scripts/ops/backfill_excursions.py && echo SCRIPT_IN_IMAGE"
```

Expected: `bot`, `admin`, `refresher` and `db` up and healthy; `v228_001 (head)`; `SCRIPT_IN_IMAGE`. Re-run the read-back SQL from Step 5 (to the terminal, not the "after" file): `unlabelled` is `0`, `daily` holds the rows that had `mfe_r`, and the notes fingerprint equals Step 5's.

- [ ] **Step 8: Timeframes and archive check (read-only, verdict words only)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c \"from swingbot import config; t = {x.strip() for x in str(config.MARKET_DATA_TIMEFRAMES).split(',')}; print('TIMEFRAMES_OK' if {'5min', '15min'} <= t else 'TIMEFRAMES_MISSING')\""
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && ls market_data/5min | wc -l && ls market_data/15min | wc -l && head -2 market_data/5min/AAPL.csv"
```

Expected: `TIMEFRAMES_OK`; both directories hold hundreds of files; `AAPL.csv` starts with the header `Datetime,Close,High,Low,Open,Volume` and a first row on `2026-06-23 13:30:00+00:00` (the brief's 2026-11-14 check). `TIMEFRAMES_MISSING` or an empty directory: stop and ask the partner — adding a timeframe is a `.env` change under `mirror-prod`, outside this plan.

- [ ] **Step 9: Run the backfill detached on the VM**

The container's working directory is `/app`, so the relative `logs/` paths are the host mount `/opt/swing-bot/logs/` and the checkpoint survives a container restart. The bot's own refresh-loop pass may run at the same time; that is safe, because both write through the conditional patch (the finer write wins, a coarser one is a no-op).

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -d -T bot sh -c 'python scripts/ops/backfill_excursions.py > logs/backfill_excursions.out 2>&1'"
bash scripts/ops/ssh-hetzner.sh "head -1 /opt/swing-bot/logs/backfill_excursions.out; ls /opt/swing-bot/logs/backfill_excursions.ckpt | wc -l"
```

Expected: the first line is `resuming: 0/N tickers restored` (N = tickers with pending entries) and the checkpoint count grows. Wait for the report file with a background loop (the Monitor tool or `run_in_background`; never a foreground sleep):

```bash
until bash scripts/ops/ssh-hetzner.sh "test -f /opt/swing-bot/logs/backfill_excursions.report.txt"; do sleep 60; done
```

If `logs/backfill_excursions.out` ends in a traceback, or the `bot` container restarted (the `exec` dies with it), read the traceback, fix only an environmental cause, and re-run the same `exec -d` command: it prints `resuming: n/N tickers restored` and redoes only unfinished tickers (each entry's upgrade is idempotent and never downgrades). A code fault is a stop-and-ask: the fix goes through a commit and a deploy, never a hand edit on the VM.

- [ ] **Step 10: Read back**

```bash
bash scripts/ops/ssh-hetzner.sh "cat /opt/swing-bot/logs/backfill_excursions.report.txt; test ! -d /opt/swing-bot/logs/backfill_excursions.ckpt && echo CHECKPOINT_REMOVED; tail -3 /opt/swing-bot/logs/backfill_excursions.out"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -X -q -v ON_ERROR_STOP=1" \
  < "<scratchpad>/v228_readback.sql" > "<scratchpad>/v228_readback_after.txt"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -X -q -v ON_ERROR_STOP=1" \
  < "<scratchpad>/v228_notes.sql" > "<scratchpad>/v228_notes_after.txt"
cat "<scratchpad>/v228_readback_after.txt"
diff "<scratchpad>/v228_notes_before.txt" "<scratchpad>/v228_notes_after.txt" && echo NOTES_UNCHANGED
```

Expected:
- The report line starts `excursion upgrade:` with `upgraded` mostly `5min` and `budget_hit` false; `no_file`, `unreadable`, `no_coverage` and `density` each small and counted apart; `CHECKPOINT_REMOVED`.
- `== sources`: most rows `5min`; `daily` left only where no finer frame covers the trade; `unlabelled` `0`.
- The LONG losers' median stored MFE has moved from about 1.24 towards the 0.31 the results doc measured, and `reached_1r` has fallen towards 13 (the success measure in the index Goal). A median that did not move means the pass upgraded nothing — read the report counts before going on.
- `NOTES_UNCHANGED`, and the fingerprint equals Step 5's (a diff line names a trade id whose note changed; ask the partner whether they edited it during the run — the backfill never writes `note`).

- [ ] **Step 11: The refresh-loop pass ran (read-only)**

The pass runs on the first `market_data_refresh` tick after the deploy (the UTC-date stamp starts empty), then once per UTC date:

```bash
bash scripts/ops/ssh-hetzner.sh "grep -h 'excursion upgrade:' /opt/swing-bot/logs/bot.log* | tail -3"
```

Expected: at least one line dated after the deploy (logs live in `/opt/swing-bot/logs`, not `docker logs`). None after two `MARKET_DATA_REFRESH_MINUTES` intervals: grep the same log for `excursion` warnings or tracebacks and ask the partner; the backfill already did the work, so this is a follow-up, not a rollback.

- [ ] **Step 12: Mirror — the production record in the index's `## Handoff`**

Append one bullet to `## Handoff` in `docs/superpowers/plans/2026-11-14-v228-intraday-excursion_0-index.md` (fill every value from Steps 1–11; never paste note text or `.env` values):

```markdown
- <YYYY-MM-DD>, V228-17 production (mirror-prod): deployed `main` <sha> (CI run <id>); last PITR drill <date> PASS, `pgbackrest info` status ok, newest backup <date>; rollback target T0 = <T0> (`scripts/ops/rollback_to.sh`). `alembic current` = v228_001; v228_001 labelled <n> rows `daily`, 0 unlabelled. Timeframes TIMEFRAMES_OK; 5min archive <files> files from 2026-06-23. Backfill `scripts/ops/backfill_excursions.py` run detached in `bot`, <duration>; report: `<the excursion upgrade: line>`. Sources after: <source: n, ...>. LONG last-leg losers since 2026-10-01: N <n>, median stored MFE <before> -> <after> R, reached +1R <before> -> <after>. Notes fingerprint unchanged (<with_note> notes). Refresh-loop pass line seen <timestamp>. No file on the VM edited by hand; no `.env` change.
```

- [ ] **Step 13: Commit the record on `main`**

```bash
git add docs/superpowers/plans/2026-11-14-v228-intraday-excursion_0-index.md
git commit -m "docs(v228): production record -- deploy, v228_001, excursion backfill read-back (V228-17)"
git push origin main
```

The push redeploys the same code plus a docs change (harmless). The `mirror-prod` gate is this commit in `git log`. Then `/close-out` (CLAUDE.md standing permission) once the CI run for this push is green.
