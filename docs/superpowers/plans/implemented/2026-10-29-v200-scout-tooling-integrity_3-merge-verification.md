# Scout tooling integrity, part 3: known-at-entry tags, two-sided merge, verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Scout tooling integrity](../specs/2026-10-29-v200-scout-tooling-integrity.md) (Part 5, Verification)
**Index:** [`_0-index.md`](2026-10-29-v200-scout-tooling-integrity_0-index.md). The Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.

This part covers tasks V200-13 … V200-18, in that order. V200-13 runs after V200-12, because both edit `bars.py` and `report.py`. V200-14 runs after V200-12, because both edit the scout skills and `scout.md` and regenerate the Codex mirror. V200-15 needs V200-13 and V200-14. V200-16 runs after V200-15. V200-17 runs after every earlier task, and V200-18 runs last. `<wt>` is the absolute path of this plan's worktree, and `<scratch>` is the session scratchpad.

Controller decisions binding this part (2026-10-29):

- **Tagging rule.** A cut's `defined_at` tag follows from the row fields its key reads:
  - Any outcome field makes it `outcome`: `exit_date`, `exit_price`, `close_reason`, `outcome`, `gross_r`, `net_r`, `mfe_r`, `mae_r`, `exit_efficiency`, `holding_days`, `bars.reversal`, `bars.wider_stop_lost`.
  - Otherwise any fill-bar field makes it `fill`: `bars.open_gap_pct`, `bars.fill_day_open`.
  - Otherwise the cut is `entry`.
  - Two exceptions are fixed by the spec. `bars.gapped_through` is `entry`, because the fill happens at that open (spec Part 5.2). `entry_date` (weekday, Friday, OPEX week) is `entry`, because the day is known at the moment of entry.
  - V200-13's audit test enforces this rule by recording the attributes each key reads.
- **Where schema 2 applies.** It drives three things: the `defined_at` ban, the `avoid` upper-bound rule, and the two-value dedupe. Schema 1 keeps the pre-v200 behaviour exactly: the one-sided lower-bound rule for every row whatever its `direction`, no ban, no dedupe, and `-lower` ranking. The only additions under schema 1 are the banner and the display-only projected change.
- **Loud failure.** `scout_merge.main` catches `SchemaError`, prints `scout_merge: <message>` to stderr and returns 2. It writes no slate.
- **Out of scope.** `docs/claude/skills-tools.md` § Generator roles states the one-sided rule. V200-15 rewrites that bullet, the one file it touches outside the ledger. The rule there is no gate or threshold change: q ≤ 0.10 and thin stay as they are. `AGENTS.md` does not carry the rule, so it needs no mirror edit.

# Phase 5 — Known-at-entry merge, verification, full suite

### Task V200-13: `defined_at` per cut and `autopsy_schema: 2`

**Model:** opus — the tags decide which scout evidence the merge bans. A wrong tag lets lookahead through without any error, and the audit test has to reason about what each key reads.

**Files:**
- Modify: `scripts/reports/autopsy/cuts.py` (module docstring, new `DEFINED_AT_TAGS`, `CATEGORICAL_DEFINED_AT`)
- Modify: `scripts/reports/autopsy/bars.py` (new `BAR_DEFINED_AT`)
- Modify: `scripts/reports/autopsy/exits.py` (new `EXIT_DEFINED_AT`)
- Modify: `scripts/reports/autopsy/cells.py` (`CellStats.defined_at`, `to_json`)
- Modify: `scripts/reports/autopsy/report.py` (`AUTOPSY_SCHEMA`, new `cut_defined_at`, `_cells`, `_header`, `_extra_text`)
- Create: `tests/scout/test_autopsy_defined_at.py`
- Modify: `tests/scout/test_book_autopsy.py` (one new end-to-end test; it reuses `_build`)

**Interfaces:**
- Consumes:
  - `report._all_cuts(sector_of)`, the one join point of the three cut lists.
  - `CellStats.eras` and `CellStats.notes` (V200-11), and `_extra_text` reading `c.get("notes", [])` (V200-11).
  - `bars.GAP_SIGN_NOTE` as `report.NOTES[-1]` (V200-12). This task appends nothing to `NOTES`.
- Produces:
  - `cuts.DEFINED_AT_TAGS = ("entry", "fill", "outcome")`
  - Three cut-name → tag maps, each a `dict[str, str]`: `cuts.CATEGORICAL_DEFINED_AT`, `bars.BAR_DEFINED_AT` and `exits.EXIT_DEFINED_AT`.
  - `report.AUTOPSY_SCHEMA = 2`, and `header["autopsy_schema"] == 2`.
  - `report.cut_defined_at(sector_of: dict) -> dict[str, str]`:
    - keyed in `_all_cuts` order;
    - raises `ValueError` naming every cut whose tag is missing or not in `DEFINED_AT_TAGS`;
    - reads the three maps through their modules at call time (`cuts.CATEGORICAL_DEFINED_AT`, not a name imported at load), so a monkeypatched map is seen.
  - `CellStats.defined_at: str | None = None`, the last field. `to_json` adds `"defined_at"`, which V200-15 reads.

**Tags this task freezes** (spec Part 5.2; the tagging rule in this part's header):

| Tag | Cuts |
|---|---|
| `outcome` | `weekend_hold` and `fomc_proximity` (both read `exit_date`); `near_stop_reversal` (`bars.reversal`, `bars.wider_stop_lost`); `exit_reason`, `near_tp_close`, `gap_through_stop`, `holding_bucket` |
| `fill` | `open_gap_bucket` (`bars.open_gap_pct`, measured on the bar the fill selected) |
| `entry` | `strategy_horizon`, `direction`, `ticker`, `sector_today`, `regime`, `weekday`, `friday_entry`, `earnings_proximity`, `opex_week`, `atr_pct_bucket`, `session_bucket`, `alert_hour`, `gapped_through_entry`, `dollar_volume_bucket` |

- `apply_bh`, `cut_cells` and `cell_stats` are untouched. Every cell stays in the one BH pass, fill- and outcome-defined ones included (spec Part 5.7).
- In the markdown notes column, a `fill` or `outcome` cell gains `<tag>-defined (not known at entry)`, so a scout sees the ban before proposing. No markdown line is added.

- [ ] **Step 1: Write the failing tests**

Create `tests/scout/test_autopsy_defined_at.py`:

```python
"""v200 Part 5.2: every autopsy cut says when its value is known -- entry, fill or outcome.

The audit records which BookRow attributes and bars keys each cut key reads on a fully
populated row, and derives the tag from them, so a new cut, or a key that starts reading an
outcome field, fails here instead of reaching the merge as known-at-entry evidence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import bars, cells, cuts, exits, report  # noqa: E402
from autopsy.rows import BookRow  # noqa: E402

SECTORS = {"AAA": "Technology"}
OUTCOME_FIELDS = frozenset({
    "exit_date", "exit_price", "close_reason", "outcome", "gross_r", "net_r", "mfe_r",
    "mae_r", "exit_efficiency", "holding_days", "bars.reversal", "bars.wider_stop_lost"})
# bars.gapped_through is read on the fill-day bar too, but the fill happens at that open
# (spec Part 5.2), so it is not a fill field. entry_date is known at the moment of entry.
FILL_FIELDS = frozenset({"bars.open_gap_pct", "bars.fill_day_open"})
CUT_NAMES = [name for name, _ in report._all_cuts(SECTORS)]


class _Bars(dict):
    def __init__(self, data: dict, seen: set):
        super().__init__(data)
        self._seen = seen

    def get(self, key, default=None):
        self._seen.add(f"bars.{key}")
        return super().get(key, default)

    def __getitem__(self, key):
        self._seen.add(f"bars.{key}")
        return super().__getitem__(key)


class _Recorder:
    """Delegates to a BookRow and records every attribute and bars key read."""

    def __init__(self, row: BookRow):
        self._row = row
        self.seen: set[str] = set()

    def __getattr__(self, name):
        if name == "bars":
            return _Bars(self._row.bars, self.seen)
        self.seen.add(name)
        return getattr(self._row, name)


def _full_row() -> BookRow:
    """Every field set, with values that walk each key past its early returns."""
    return BookRow(
        row_kind="trade", trade_id="t1", plan_id="p1", ticker="AAA", strategy="RSI",
        horizon="2w", direction="bullish", plan_date="2026-03-02", plan_hour=9,
        entry_type="limit", planned_entry=100.0, entry_date="2026-03-03", entry=100.0,
        stop=95.0, take_profit=110.0, exit_date="2026-03-12", exit_price=94.0,
        close_reason="loss", outcome="loss", gross_r=-1.2, net_r=-1.25, mfe_r=0.5,
        mae_r=-1.2, exit_efficiency=0.1, holding_days=7.0, stop_width_atr=1.5, atr_pct=2.0,
        days_to_earnings=10.0, regime2_state="bull_quiet", session_bucket="open",
        bars={"covered": True, "open_gap_pct": 0.5, "gapped_through": False,
              "dollar_volume": 3e7, "reversal": False, "wider_stop_lost": True})


def _expected(seen: set[str]) -> str:
    if seen & OUTCOME_FIELDS:
        return "outcome"
    return "fill" if seen & FILL_FIELDS else "entry"


def test_every_cut_has_one_known_tag_in_cut_order():
    tags = report.cut_defined_at(SECTORS)
    assert list(tags) == CUT_NAMES and len(CUT_NAMES) == 22
    assert cuts.DEFINED_AT_TAGS == ("entry", "fill", "outcome")
    assert set(tags.values()) <= set(cuts.DEFINED_AT_TAGS)


@pytest.mark.parametrize("name", CUT_NAMES)
def test_each_cut_tag_matches_the_fields_its_key_reads(name):
    key = dict(report._all_cuts(SECTORS))[name]
    recorder = _Recorder(_full_row())
    key(recorder)
    assert recorder.seen, name
    assert report.cut_defined_at(SECTORS)[name] == _expected(recorder.seen), \
        (name, sorted(recorder.seen))


def test_the_spec_named_cuts_carry_their_tags():
    tags = report.cut_defined_at(SECTORS)
    for name in ("exit_reason", "near_tp_close", "gap_through_stop", "holding_bucket",
                 "weekend_hold", "fomc_proximity", "near_stop_reversal"):
        assert tags[name] == "outcome", name
    assert tags["open_gap_bucket"] == "fill"
    assert tags["gapped_through_entry"] == "entry"
    assert sorted(n for n, t in tags.items() if t == "entry") == sorted((
        "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday",
        "friday_entry", "earnings_proximity", "opex_week", "atr_pct_bucket", "session_bucket",
        "alert_hour", "gapped_through_entry", "dollar_volume_bucket"))


def test_an_untagged_cut_fails_loudly(monkeypatch):
    monkeypatch.setattr(exits, "EXIT_DEFINED_AT",
                        {k: v for k, v in exits.EXIT_DEFINED_AT.items() if k != "holding_bucket"})
    with pytest.raises(ValueError, match="holding_bucket"):
        report.cut_defined_at(SECTORS)


def test_an_unknown_tag_fails_loudly(monkeypatch):
    monkeypatch.setattr(bars, "BAR_DEFINED_AT", dict(bars.BAR_DEFINED_AT, open_gap_bucket="later"))
    with pytest.raises(ValueError, match="open_gap_bucket"):
        report.cut_defined_at(SECTORS)


def test_cell_json_carries_defined_at():
    cell = cells.CellStats(id="a=b", cut="a", value="b", n=1, weeks=1, win_rate=1.0,
                           net_expr=1.0, gross_expr=1.0, delta=None, ci=None, p=None, q=None,
                           thin=True)
    assert cell.to_json()["defined_at"] is None
    cell.defined_at = "fill"
    assert cell.to_json()["defined_at"] == "fill"


@pytest.mark.parametrize("tag, flagged", [
    ("outcome", True), ("fill", True), ("entry", False), (None, False)])
def test_the_notes_column_flags_cells_not_known_at_entry(tag, flagged):
    c = {"extra": {"tickers": 1, "top_ticker_share": 1.0}, "bar_covered_n": None, "notes": []}
    if tag is not None:
        c["defined_at"] = tag
    text = report._extra_text(c)
    assert (f"{tag}-defined (not known at entry)" in text) is flagged
    assert ("not known at entry" in text) is flagged
```

Append to `tests/scout/test_book_autopsy.py`:

```python
def test_the_report_is_schema_2_and_every_cell_carries_its_cut_tag(tmp_path):
    data = _build(tmp_path)
    assert data["header"]["autopsy_schema"] == report.AUTOPSY_SCHEMA == 2
    tags = report.cut_defined_at(data["header"]["sector_map"])
    assert data["cells"]
    for cell in data["cells"]:
        assert cell["defined_at"] == tags[cell["cut"]], cell["id"]
    assert set(data) == {"header", "cells", "tallies", "giveback"}
    assert len(report.render_markdown(data).splitlines()) <= report.MD_MAX_LINES
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_defined_at.py`
Expected: FAIL with `AttributeError: module 'autopsy.report' has no attribute 'cut_defined_at'`. Collection itself succeeds, because `_all_cuts` already exists.

- [ ] **Step 3: Implement the three tag maps**

- **`cuts.py`:**
  - Add `DEFINED_AT_TAGS = ("entry", "fill", "outcome")`.
  - Add `CATEGORICAL_DEFINED_AT` right after `CATEGORICAL_CUT_NAMES`, one entry per name, using the table's tags.
  - In the module docstring, replace "Every input is frozen at issuance (risk_features) or a calendar fact" with: "Inputs are frozen at issuance (risk_features) or are calendar facts, except weekend_hold and fomc_proximity, which read exit_date and are tagged outcome in CATEGORICAL_DEFINED_AT (v200: a cut's defined_at says when its value is known -- entry, fill or outcome)".
- **`bars.py`:** add `BAR_DEFINED_AT` right after `bar_cuts()`:
  - `open_gap_bucket`: `fill`
  - `gapped_through_entry`: `entry`
  - `dollar_volume_bucket`: `entry`
  - `near_stop_reversal`: `outcome`

  Give each entry a trailing comment naming the bars key it reads.
- **`exits.py`:** add `EXIT_DEFINED_AT` right after `exit_cuts()`, with all four exit cuts tagged `outcome`.

- [ ] **Step 4: Wire the tags into `cells.py` and `report.py`**

- **`cells.py`:** add `defined_at: str | None = None` as the last `CellStats` field. In `to_json`, add `"defined_at": self.defined_at`.
- **`report.py`:**
  - Add `AUTOPSY_SCHEMA = 2` beside `MD_MAX_LINES`, commented `# v200: cells carry defined_at; scout_merge reads this to apply the known-at-entry rule`.
  - Add `cut_defined_at(sector_of)` right after `_all_cuts`, per the Interfaces contract.
  - **`_cells`:** call `tags = cut_defined_at(sector_of)` once before the loop, and set `cell.defined_at = tags[name]` beside `_decorate`.
  - **`_header`:** add `"autopsy_schema": AUTOPSY_SCHEMA` to the returned dict.
  - **`_extra_text`:** when `c.get("defined_at") in ("fill", "outcome")`, append `f"{c['defined_at']}-defined (not known at entry)"` to `parts`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_defined_at.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_cuts.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_cells.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_bars.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py
python -m radon cc -s -n C <wt>/scripts/reports/autopsy/report.py <wt>/scripts/reports/autopsy/cells.py <wt>/scripts/reports/autopsy/cuts.py
```

Expected: every run reports `0 failed`, and radon prints nothing.

If the audit test fails for a cut, read the fields the recorder saw:
- Change a tag only where the spec's lists allow it.
- If the key reads a field the rule above does not classify, stop with `BLOCKED: <cut> reads <field>`. Never edit the field sets to make the test pass.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/reports/autopsy/cuts.py scripts/reports/autopsy/bars.py \
    scripts/reports/autopsy/exits.py scripts/reports/autopsy/cells.py \
    scripts/reports/autopsy/report.py tests/scout/test_autopsy_defined_at.py \
    tests/scout/test_book_autopsy.py
git -C <wt> commit -m "feat(autopsy): v200 defined_at per cut (entry/fill/outcome) and autopsy_schema 2 (V200-13)"
```

### Task V200-14: Scout row field `direction`

**Model:** sonnet — one parsed field, plus doc text kept in step across five files and their Codex mirrors. The parser change follows an existing table.

**Files:**
- Modify: `scripts/dev/scout_merge.py` (`ROW_FIELDS`, new `DIRECTIONS`, `ScoutRow.direction`, `_problems`)
- Modify: `.claude/skills/exit-harvester/SKILL.md`, `.claude/skills/regime-desk/SKILL.md`, `.claude/skills/setup-scout/SKILL.md` (`## Row format`)
- Modify: `.claude/skills/trade-scout/SKILL.md` (`## Step 3 — Merge`)
- Modify: `.claude/agents/scout.md` (`## Evidence rule`)
- Modify: `tests/scout/test_scout_merge.py` (`_row`, the CLI `_block`), `tests/scout/test_scout_merge_parse.py` (`BASE`, the `ROW_FIELDS` pin, the malformed cases), `tests/scout/test_generator_roles.py` (`ROW_KEYS`, one new test), `tests/scout/test_trade_scout_skill.py` (two phrase checks)
- Regenerate: the `.agents/skills/<name>/SKILL.md` and `.codex/agents/scout.toml` mirrors that `scripts/dev/sync_codex.py` writes

**Interfaces:**
- Consumes: nothing from earlier tasks. It runs after V200-12, because both edit the three role skills and `scout.md` and run `sync_codex.py`.
- Produces, read by V200-15 and V200-16:
  - `ROW_FIELDS = ("idea", "claim", "evidence", "exploratory", "edge", "direction", "mechanism", "order_form", "manual_actions", "pairs_with", "divergence", "route")`
  - `DIRECTIONS = ("exploit", "avoid")`
  - `ScoutRow.direction: str`, declared right after `edge`.
  - Parse drops:
    - a row without the field drops `malformed: missing direction`, through the existing `missing` check;
    - any other value drops `malformed: direction must be exploit or avoid`.
  - Values match exactly, like `edge`. `Exploit` is malformed.

**Doc text this task fixes.** Each passage goes in verbatim. Wrap it like the surrounding text.

1. **The three role skills.** In `## Row format`, inside the code block, add the line `  direction: exploit | avoid` right after the `  edge: ...` line. Right after the code block, add this paragraph:

   > `direction: exploit` proposes trading the cell: the merge keeps it only when the cell's Δ lower bound is above 0. `direction: avoid` proposes standing aside from it: the merge keeps it only when the cell's Δ upper bound is below 0. Both need q ≤ 0.10. A cell the autopsy marks `not known at entry` (its cut is `fill`- or `outcome`-defined) is no evidence for either, so leave the row out.

2. **`.claude/agents/scout.md`.** Add a new last paragraph to `## Evidence rule`, after the gap sign note from V200-12:

   > Every row carries `direction: exploit | avoid` right after `edge:`. An `exploit` row cites a cell whose Δ interval lies above zero; an `avoid` row cites one whose interval lies below zero. A cell the autopsy marks `not known at entry` is no evidence: leave the row out.

3. **`.claude/skills/trade-scout/SKILL.md`, `## Step 3 — Merge`.** Add this paragraph after "It drops closed, duplicate and unsupported rows with reasons and writes `docs/superpowers/results/<date>-scout-slate.md`.":

   > On a schema-2 autopsy (`"autopsy_schema": 2` in its JSON header), the merge is two-sided:
   > - An `exploit` row needs the cell's Δ lower bound above 0, and an `avoid` row needs its upper bound below 0. Both need q ≤ 0.10.
   > - A row citing a `fill`- or `outcome`-defined cell drops as not known at entry.
   > - On a two-value cut, "avoid X" and "exploit not-X" count as one rule, so the second is dropped.
   > - Rows rank by the bound nearest zero, and each shows its projected pooled change.
   >
   > A schema-1 autopsy re-merges under the old one-sided rule, and the slate opens with the legacy banner. A schema-2 cell without `defined_at` stops the merge with exit code 2 and writes no slate.

- [ ] **Step 1: Write the failing tests**

- **`tests/scout/test_scout_merge_parse.py`:**
  - In `BASE`, add `"direction": "exploit",` right after `"edge": "expectancy",`.
  - Replace the `ROW_FIELDS` pin with:

```python
def test_row_fields_are_the_row_format_keys_in_order():
    assert sm.ROW_FIELDS == ("idea", "claim", "evidence", "exploratory", "edge", "direction",
                             "mechanism", "order_form", "manual_actions", "pairs_with",
                             "divergence", "route")
    assert sm.DIRECTIONS == ("exploit", "avoid")
```

  - Add these cases to the `test_malformed_rows_are_dropped_with_the_reason` parametrize list:

```python
    ({"drop": ("direction",)}, "missing direction"),
    ({"direction": ""}, "missing direction"),
    ({"direction": "both"}, "direction must be exploit or avoid"),
    ({"direction": "Exploit"}, "direction must be exploit or avoid"),
```

  - Append:

```python
def test_parse_rows_reads_the_direction():
    text = _doc(("regime-desk", [_block("friday-skip", direction="avoid"),
                                 _block("risk-on-only")]))
    rows, drops = sm.parse_rows(text)
    assert drops == []
    assert [(r.idea, r.direction) for r in rows] == [("friday-skip", "avoid"),
                                                     ("risk-on-only", "exploit")]
```

- **`tests/scout/test_scout_merge.py`:**
  - In `_row`, add `direction="exploit"` to the defaults right after `edge="expectancy"`.
  - Give the CLI `_block` helper a `direction="exploit"` parameter, and add `f"  direction: {direction}\n"` right after its `edge` line.

- **`tests/scout/test_generator_roles.py`:**
  - Set `ROW_KEYS` to the new `ROW_FIELDS` order, with `"direction"` after `"edge"`.
  - Append:

```python
@pytest.mark.parametrize("name", GENERATORS)
def test_row_format_explains_direction_and_the_known_at_entry_rule(name):
    block = _section(_body(name), "## Row format")
    assert "  direction: exploit | avoid" in block
    for phrase in ("Δ lower bound is above 0", "Δ upper bound is below 0", "q ≤ 0.10",
                   "not known at entry"):
        assert phrase in block, phrase


@pytest.mark.parametrize("name", GENERATORS)
def test_codex_copy_carries_the_direction_key(name):
    copy = (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    assert "  direction: exploit | avoid" in copy
```

- **`tests/scout/test_trade_scout_skill.py`:** append:

```python
def test_merge_step_describes_the_two_sided_rule_and_the_legacy_schema():
    _, body = _parsed(SKILL)
    step = _section(body, "## Step 3 — Merge")
    for phrase in ('"autopsy_schema": 2', "`exploit`", "`avoid`", "not known at entry",
                   "two-value cut", "schema-1", "legacy banner", "exit code 2"):
        assert phrase in step, phrase


def test_scout_agent_states_the_direction_field():
    _, body = _parsed(AGENT)
    section = _section(body, "## Evidence rule")
    assert "`direction: exploit | avoid`" in section
    assert "not known at entry" in section
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_generator_roles.py
```

Expected:
- `test_scout_merge_parse.py`: FAIL. The pin fails with `AttributeError: ... 'DIRECTIONS'`, and every `BASE` row drops as `malformed: unknown field direction`.
- `test_generator_roles.py`: FAIL on `test_row_format_lists_every_key_in_order` (no `  direction: ` line).

- [ ] **Step 3: Implement the parser change in `scripts/dev/scout_merge.py`**

- Insert `"direction"` into `ROW_FIELDS` after `"edge"`, and add `DIRECTIONS = ("exploit", "avoid")` beside `_EDGES`.
- Add `direction: str` to `ScoutRow`, right after `edge: str`.
- In `_problems`, add `("direction", DIRECTIONS, "direction must be exploit or avoid")` to the `checks` tuple, after the `edge` entry. The `missing` line already covers an absent or empty field, and the function's complexity does not change.
- `parse_rows` and `_row_block` need no edit: both iterate `ROW_FIELDS`.

- [ ] **Step 4: Edit the five docs and regenerate the mirror**

Add the three passages above at the placements listed. Then run:

```bash
python <wt>/scripts/dev/sync_codex.py
python <wt>/scripts/dev/sync_codex.py --check
```

Expected: the last command prints `Codex mirror is current.`

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_generator_roles.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_trade_scout_skill.py
python <wt>/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python -m radon cc -s -n C <wt>/scripts/dev/scout_merge.py
```

Expected: every run reports `0 failed`, and radon prints nothing.

- [ ] **Step 6: Commit**

First list the mirror paths that changed. Name every path explicitly; never use `git add -A`.

```bash
git -C <wt> status --short -- .agents .codex
git -C <wt> add scripts/dev/scout_merge.py \
    .claude/skills/exit-harvester/SKILL.md .claude/skills/regime-desk/SKILL.md \
    .claude/skills/setup-scout/SKILL.md .claude/skills/trade-scout/SKILL.md \
    .claude/agents/scout.md \
    tests/scout/test_scout_merge.py tests/scout/test_scout_merge_parse.py \
    tests/scout/test_generator_roles.py tests/scout/test_trade_scout_skill.py \
    <each .agents/ and .codex/ path listed above>
git -C <wt> commit -m "feat(scout): v200 scout rows carry direction exploit|avoid (V200-14)"
```

### Task V200-15: Two-sided known-at-entry screen; schema-1 legacy rule

**Model:** opus — this is the gate every future slate row passes. Schema-1 compatibility, the loud failure and the two-value dedupe all interact, and a slip either lets lookahead evidence through or drops valid rows silently.

**Files:**
- Modify: `scripts/dev/scout_merge.py` (new `SCHEMAS`, `NOT_AT_ENTRY`, `DEFINED_AT_TAGS`, `SchemaError`, `autopsy_schema`, `check_defined_at`, `_upper_bound`, `_bound_reason`, `_known_at_entry_reason`, `rule_key`, `_rule_reason`; changed `_statistical_reason`, `_cell_reason`, `screen_rows`, `main`)
- Modify: `tests/scout/test_scout_merge.py` (`_cell` gains `defined_at="entry"`)
- Create: `tests/scout/test_scout_merge_two_sided.py`
- Modify: `docs/claude/skills-tools.md` (§ Generator roles (v161), the merge-rule bullet only; see this part's header)

**Interfaces:**
- Consumes:
  - From V200-13: each cell's `"defined_at"` (one of `entry` / `fill` / `outcome`) and `header["autopsy_schema"]`.
  - From V200-14: `ScoutRow.direction` (`exploit` / `avoid`).
- Produces, read by V200-16 and V200-17:
  - `SCHEMAS = (1, 2)`, `DEFINED_AT_TAGS = ("entry", "fill", "outcome")`, `NOT_AT_ENTRY = ("fill", "outcome")`.
  - `class SchemaError(ValueError)`.
  - `autopsy_schema(header: dict) -> int`:
    - an absent key gives `1`;
    - an `int` in `SCHEMAS` is returned as is (a `bool` is not an int here);
    - anything else raises `SchemaError("autopsy_schema <value!r> is not one of 1, 2")`.
  - `check_defined_at(cells: dict[str, dict]) -> None`: raises `SchemaError` naming every cell id (sorted, comma-separated) whose `defined_at` is missing or not in `DEFINED_AT_TAGS`. It is called only for schema 2.
  - `screen_rows(rows, *, closed, ledger, cells, schema: int = 1) -> tuple[list[ScoutRow], list[Drop]]`. When `schema == 2` it calls `check_defined_at(cells)` before the first row.
  - `rule_key(row: ScoutRow, cells: dict[str, dict]) -> tuple[str, str] | None` — `(cut, value the rule trades)` for a cell row on a two-value cut, otherwise `None`.
  - `_statistical_reason(cell, direction: str = "exploit", schema: int = 1)`, kept call-compatible with today's one-argument use.

**Rules this task freezes** (spec Part 5.4-5.7; controller decisions in this part's header):

| Check, in `_statistical_reason` order | Schema 1 | Schema 2 |
|---|---|---|
| known at entry | skipped | `defined_at` in `NOT_AT_ENTRY` drops `cell <id> is <tag>-defined (not known at entry)` |
| bound | lower bound must be finite and > 0, whatever the direction; otherwise today's text `cell <id> Δ lower bound <x> is at or below zero or unavailable` | `exploit`: same lower-bound rule and text. `avoid`: upper bound (`ci[1]`) must be finite and < 0; otherwise `cell <id> Δ upper bound <x> is at or above zero or unavailable` (`<x>` via `_signed`, `n/a` when missing) |
| q | today's rule and text (finite, 0 ≤ q ≤ 0.10) | same |

- **Order of checks.** `_cell_reason` keeps its order: no cell id, cell not in the JSON, thin, not exploratory, then `_statistical_reason`, then `_quoted_figures_reason`. Playbook `/screen` rows still skip `_cell_reason` and are never deduped.
- **Two-value dedupe (schema 2 only).**
  - A cut counts as two-value when the autopsy JSON holds exactly two distinct `value`s for it.
  - `rule_key` maps `exploit X` to `(cut, X)`, and `avoid X` to `(cut, <the other value>)`.
  - A later row whose key equals a kept row's key drops: `same rule as the <role> row <idea> on two-value cut <cut>`.
  - Keys are recorded only for kept rows, after every other check passes.
  - Cuts with one value or with three or more are never deduped.
- **BH family.** Unchanged, and the merge never reads `eras`.

- [ ] **Step 1: Write the failing tests**

In `tests/scout/test_scout_merge.py`, give `_cell` a `defined_at="entry"` keyword and put `"defined_at": defined_at` in the returned dict. Every existing test calls `screen_rows` without `schema`, so they stay on the legacy rule.

Create `tests/scout/test_scout_merge_two_sided.py`:

```python
"""v200 Part 5: the two-sided, known-at-entry merge rule (schema 2) and the schema-1 legacy rule."""
import json
import sys
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import scout_merge as merge  # noqa: E402


def _cell(cid, *, lo, hi, q=0.04, n=40, weeks=12, defined_at="entry"):
    cut, value = cid.split("=", 1)
    ci = None if lo is None else [lo, hi]
    delta = None if lo is None else round((lo + hi) / 2, 6)
    out = {"id": cid, "cut": cut, "value": value, "n": n, "weeks": weeks, "win_rate": 0.5,
           "net_expr": 0.2, "gross_expr": 0.22, "delta": delta, "ci": ci, "p": 0.01, "q": q,
           "thin": False, "bar_covered_n": None, "extra": {}}
    if defined_at is not None:
        out["defined_at"] = defined_at
    return out


def _evidence(cell):
    if cell["ci"] is None:
        return f"cell {cell['id']}; N {cell['n']}; weeks {cell['weeks']}; Δ net ExpR 0.000 [0.000, 0.000]; q 0.040"
    lo, hi = cell["ci"]
    return (f"cell {cell['id']}; N {cell['n']}; weeks {cell['weeks']}; "
            f"Δ net ExpR {cell['delta']:.3f} [{lo:.3f}, {hi:.3f}]; q {cell['q']:.3f}")


def _row(cell, direction, idea=None, role="regime-desk"):
    base = {f.name: "" for f in fields(merge.ScoutRow)}
    base.update(role=role, idea=idea or f"{direction}-{cell['id']}", claim="A claim.",
                evidence=_evidence(cell), exploratory="yes", edge="expectancy",
                direction=direction, mechanism="Why.", order_form="limit, day order",
                manual_actions="none", pairs_with="n/a", divergence="no", route="/prereg")
    return merge.ScoutRow(**base)


def _screen(rows, cells, schema=2):
    return merge.screen_rows(rows, closed=set(), ledger={}, cells={c["id"]: c for c in cells},
                             schema=schema)


def _reasons(drops):
    return {d.idea: d.reason for d in drops}


UP = _cell("regime=risk_on", lo=0.05, hi=0.35)
DOWN = _cell("regime=risk_off", lo=-0.35, hi=-0.05)
STRADDLE = _cell("regime=chop", lo=-0.10, hi=0.0)


@pytest.mark.parametrize("header, schema", [
    ({}, 1), ({"autopsy_schema": 1}, 1), ({"autopsy_schema": 2}, 2)])
def test_autopsy_schema_reads_the_header(header, schema):
    assert merge.autopsy_schema(header) == schema


@pytest.mark.parametrize("value", ["2", 3, 0, True, None, 2.0])
def test_an_unknown_autopsy_schema_fails_loudly(value):
    with pytest.raises(merge.SchemaError, match="autopsy_schema"):
        merge.autopsy_schema({"autopsy_schema": value})


def test_exploit_needs_a_lower_bound_above_zero():
    kept, drops = _screen([_row(UP, "exploit"), _row(DOWN, "exploit")], [UP, DOWN, STRADDLE])
    assert [r.idea for r in kept] == ["exploit-regime=risk_on"]
    assert _reasons(drops) == {"exploit-regime=risk_off":
        "cell regime=risk_off Δ lower bound -0.350 is at or below zero or unavailable"}


def test_avoid_needs_an_upper_bound_below_zero():
    rows = [_row(DOWN, "avoid"), _row(STRADDLE, "avoid"), _row(UP, "avoid")]
    kept, drops = _screen(rows, [UP, DOWN, STRADDLE])
    assert [r.idea for r in kept] == ["avoid-regime=risk_off"]
    assert _reasons(drops) == {
        "avoid-regime=chop": "cell regime=chop Δ upper bound +0.000 is at or above zero or unavailable",
        "avoid-regime=risk_on": "cell regime=risk_on Δ upper bound +0.350 is at or above zero or unavailable"}


def test_an_avoid_row_without_an_interval_is_unavailable():
    none = _cell("regime=none", lo=None, hi=None)
    _, drops = _screen([_row(none, "avoid")], [none])
    assert drops[0].reason == "cell regime=none Δ upper bound n/a is at or above zero or unavailable"


@pytest.mark.parametrize("direction, cell", [("exploit", _cell("regime=hiq", lo=0.05, hi=0.3, q=0.2)),
                                             ("avoid", _cell("regime=hiq", lo=-0.3, hi=-0.05, q=0.2))])
def test_q_still_applies_to_both_directions(direction, cell):
    _, drops = _screen([_row(cell, direction)], [cell])
    assert "q must be finite and between 0 and 0.10" in drops[0].reason


@pytest.mark.parametrize("tag", ["fill", "outcome"])
@pytest.mark.parametrize("direction, lo, hi", [("exploit", 0.05, 0.35), ("avoid", -0.35, -0.05)])
def test_fill_and_outcome_cells_drop_as_not_known_at_entry(tag, direction, lo, hi):
    cell = _cell("exit_reason=stop", lo=lo, hi=hi, defined_at=tag)
    kept, drops = _screen([_row(cell, direction)], [cell])
    assert kept == []
    assert drops[0].reason == f"cell exit_reason=stop is {tag}-defined (not known at entry)"


@pytest.mark.parametrize("bad", [None, "later", ""])
def test_schema_2_cell_without_defined_at_fails_loudly(bad):
    broken = _cell("weekday=Mon", lo=0.05, hi=0.3, defined_at=bad)
    if bad == "":
        broken["defined_at"] = ""
    with pytest.raises(merge.SchemaError, match="weekday=Mon"):
        _screen([_row(UP, "exploit")], [UP, broken])          # fails even when the cell is not cited


def test_schema_1_keeps_the_legacy_one_sided_rule_without_a_ban():
    outcome = _cell("exit_reason=stop", lo=0.05, hi=0.35, defined_at=None)
    down = _cell("regime=risk_off", lo=-0.35, hi=-0.05, defined_at=None)
    kept, drops = _screen([_row(outcome, "exploit"), _row(down, "avoid")], [outcome, down], schema=1)
    assert [r.idea for r in kept] == ["exploit-exit_reason=stop"]
    assert _reasons(drops) == {"avoid-regime=risk_off":
        "cell regime=risk_off Δ lower bound -0.350 is at or below zero or unavailable"}


FRI_YES = _cell("friday_entry=yes", lo=-0.35, hi=-0.05)
FRI_NO = _cell("friday_entry=no", lo=0.05, hi=0.35)


def test_avoid_x_and_exploit_not_x_dedupe_by_cut():
    rows = [_row(FRI_YES, "avoid", idea="skip-friday"),
            _row(FRI_NO, "exploit", idea="weekday-entries-only", role="setup-scout")]
    kept, drops = _screen(rows, [FRI_YES, FRI_NO])
    assert [r.idea for r in kept] == ["skip-friday"]
    assert _reasons(drops) == {"weekday-entries-only":
        "same rule as the regime-desk row skip-friday on two-value cut friday_entry"}
    cells = {c["id"]: c for c in (FRI_YES, FRI_NO)}
    assert merge.rule_key(rows[0], cells) == merge.rule_key(rows[1], cells) == ("friday_entry", "no")


def test_a_cut_with_three_values_is_never_deduped():
    cells = [_cell("weekday=Mon", lo=0.05, hi=0.3), _cell("weekday=Tue", lo=0.05, hi=0.3),
             _cell("weekday=Fri", lo=-0.3, hi=-0.05)]
    rows = [_row(cells[2], "avoid"), _row(cells[0], "exploit")]
    kept, drops = _screen(rows, cells)
    assert len(kept) == 2 and drops == []
    assert merge.rule_key(rows[0], {c["id"]: c for c in cells}) is None


def test_a_dropped_row_does_not_claim_its_rule():
    weak = _cell("friday_entry=yes", lo=-0.35, hi=-0.05, q=0.5)
    rows = [_row(weak, "avoid", idea="skip-friday"), _row(FRI_NO, "exploit", idea="weekday-only")]
    kept, _ = _screen(rows, [weak, FRI_NO])
    assert [r.idea for r in kept] == ["weekday-only"]


def _autopsy(tmp_path, cells, schema=2):
    header = {"window": ["2026-01-05", "2026-10-09"], "n": 212, "pooled_net_expr": 0.11,
              "pooled_win_rate": 0.52, "net_of_frictions": "modelled", "cells_tested": 3,
              "notes": []}
    if schema is not None:
        header["autopsy_schema"] = schema
    path = tmp_path / "autopsy.json"
    path.write_text(json.dumps({"header": header, "cells": cells, "tallies": [],
                                "giveback": {"n": 0, "mean": None, "median": None}}),
                    encoding="utf-8")
    return path


def _role_file(tmp_path, rows):
    blocks = []
    for r in rows:
        blocks.append("\n".join([f"- idea: {r.idea}"] + [
            f"  {name}: {getattr(r, name)}" for name in merge.ROW_FIELDS[1:]]))
    path = tmp_path / "roles.md"
    path.write_text("## role: regime-desk\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


def test_main_returns_2_on_a_schema_error_and_writes_no_slate(tmp_path, capsys):
    broken = _cell("weekday=Mon", lo=0.05, hi=0.3, defined_at=None)
    out_dir = tmp_path / "out"
    code = merge.main([str(_role_file(tmp_path, [_row(UP, "exploit", idea="kept-idea")])),
                       "--autopsy", str(_autopsy(tmp_path, [UP, broken])),
                       "--out-dir", str(out_dir), "--date", "2026-10-30"])
    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith("scout_merge: ") and "weekday=Mon" in err
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_main_applies_the_schema_from_the_header(tmp_path):
    outcome = _cell("exit_reason=stop", lo=0.05, hi=0.35, defined_at="outcome")
    rows = [_row(outcome, "exploit", idea="kept-idea")]
    code = merge.main([str(_role_file(tmp_path, rows)),
                       "--autopsy", str(_autopsy(tmp_path, [outcome])),
                       "--out-dir", str(tmp_path), "--date", "2026-10-30"])
    assert code == 0
    slate = (tmp_path / "2026-10-30-scout-slate.md").read_text(encoding="utf-8")
    assert "is outcome-defined (not known at entry)" in slate.split("## Dropped")[1]


def test_the_generator_roles_doc_states_the_two_sided_rule():
    text = (ROOT / "docs" / "claude" / "skills-tools.md").read_text(encoding="utf-8")
    section = text[text.index("## Generator roles (v161)"):text.index("## Which agent for what (v107)")]
    for phrase in ("`exploit`", "`avoid`", "upper bound is below 0", "not known at entry",
                   "schema-1", "q ≤ 0.10"):
        assert phrase in section, phrase
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_two_sided.py`
Expected: FAIL. The `autopsy_schema` and `SchemaError` cases raise `AttributeError: module 'scout_merge' has no attribute ...`, and the `screen_rows` cases fail with `TypeError: screen_rows() got an unexpected keyword argument 'schema'`.

- [ ] **Step 3: Implement the rule in `scripts/dev/scout_merge.py`**

Put the new code in the TS9 section, beside `_lower_bound`. Table-drive it, so that every function stays below complexity 15.

1. **Constants and the error.** Add `SCHEMAS`, `DEFINED_AT_TAGS`, `NOT_AT_ENTRY` and `class SchemaError(ValueError)`, whose docstring reads: "The autopsy JSON breaks the contract the merge relies on (v200): an unknown autopsy_schema, or a schema-2 cell without a valid defined_at."
2. **Schema helpers.** Add `autopsy_schema` and `check_defined_at` as the Interfaces block specifies. `autopsy_schema` tests `type(value) is int`, so `True` and `2.0` are refused.
3. **`_upper_bound(cell) -> float | None`.** Mirror `_lower_bound`, using `cell["ci"][1]`.
4. **`_known_at_entry_reason(cell, schema) -> str | None`.** Return `None` under schema 1. Under schema 2, return the not-known-at-entry text when `cell["defined_at"]` is in `NOT_AT_ENTRY`.
5. **`_bound_reason(cell, direction, schema) -> str | None`.** Use the upper-bound rule only when `schema == 2 and direction == "avoid"`; every other case keeps today's lower-bound rule and its exact text.
6. **`_statistical_reason(cell, direction="exploit", schema=1)`.** Return `_known_at_entry_reason(...) or _bound_reason(...) or <today's q check>`. Keep the docstring's sentence about unrounded JSON.
7. **`_cell_reason(row, cells, schema=1)`.** Pass `row.direction.strip()` and `schema` into `_statistical_reason`.
8. **`rule_key` and `_rule_reason`.**
   - `rule_key(row, cells)` follows the dedupe rule above. Count the distinct values with a set comprehension over `cells.values()` filtered by `cut`.
   - `_rule_reason(row, cells, rules: dict, schema) -> str | None` returns `None` under schema 1, or when `rule_key` is `None`. Otherwise it returns the "same rule as …" text when the key is already in `rules`.
9. **`screen_rows(..., schema=1)`.**
   - When `schema == 2`, call `check_defined_at(cells)` first.
   - For a non-playbook row, the reason becomes `_cell_reason(row, cells, schema) or _rule_reason(row, cells, rules, schema)`.
   - After a row is kept, record `rules[key] = (row.role, row.idea)` whenever `rule_key(row, cells)` is not `None` and the schema is 2.
10. **`main`.**
    - Compute `schema = autopsy_schema(report.get("header", {}))` and pass `schema=schema` to `screen_rows`.
    - Wrap those two steps in `try: ... except SchemaError as exc: print(f"scout_merge: {exc}", file=sys.stderr); return 2`, before anything is written.
    - Add `import sys`.
    - Keep `main` below complexity 15. If needed, move the read-and-screen steps into a helper `_screen_report(args) -> tuple[...]`.

- [ ] **Step 4: Update the generator-roles doc**

In `docs/claude/skills-tools.md` § Generator roles (v161), replace "The merge drops any row whose Δ lower bound is ≤ 0;" with:

> On a schema-2 autopsy the merge keeps an `exploit` row only when the cell's Δ lower bound is above 0, and an `avoid` row only when its Δ upper bound is below 0. It drops a row citing a `fill`- or `outcome`-defined cell as not known at entry, and it keeps one row per rule on a two-value cut. A schema-1 autopsy keeps the old one-sided rule (Δ lower bound above 0) and is marked legacy on the slate.

Keep the clause that follows ("the q cut-off is the roles' filter, …") unchanged. `AGENTS.md` does not carry this rule, so it needs no edit.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_two_sided.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_trade_scout_skill.py
python -m radon cc -s -n C <wt>/scripts/dev/scout_merge.py
```

Expected: every run reports `0 failed`, and radon prints nothing.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/scout_merge.py tests/scout/test_scout_merge.py \
    tests/scout/test_scout_merge_two_sided.py docs/claude/skills-tools.md
git -C <wt> commit -m "feat(scout): v200 two-sided known-at-entry merge on schema-2 autopsies, legacy rule for schema 1 (V200-15)"
```

### Task V200-16: Ranking by bound and projected pooled change; legacy banner

**Model:** sonnet — the formula and the sort key are fixed by the spec and the ledger. The work is wiring them into `_rank_key`, `_row_block` and `render_slate`.

**Files:**
- Modify: `scripts/dev/scout_merge.py` (new `LEGACY_BANNER`, `PROJECTION_LABELS`, `projected_pooled_change`; changed `_rank_key`, `rank`, `_row_block`, `render_slate`, `main`)
- Modify: `tests/scout/test_scout_merge.py` (`HEADER` gains `"autopsy_schema": 2`)
- Modify: `tests/scout/test_scout_merge_two_sided.py` (append tests)

**Interfaces:**
- Consumes, from V200-15: `autopsy_schema(header)`, `_upper_bound(cell)`, `screen_rows(..., schema=)`, and the `_cell` / `_row` / `_autopsy` / `_role_file` helpers in `tests/scout/test_scout_merge_two_sided.py`.
- Produces:
  - `projected_pooled_change(cell: dict | None, header: dict, direction: str) -> float | None`, rounded to 4 places:
    - `exploit` gives `cell.net_expr - pooled`.
    - `avoid` gives `complement - pooled`, where `complement = (N * pooled - n * cell.net_expr) / (N - n)`. Here `N = header.n`, `pooled = header.pooled_net_expr` and `n = cell.n`.
    - The result is `None` when the cell is `None`, any input is missing or not finite, or `N - n <= 0` for `avoid`.
  - `rank(rows, cells, schema: int = 1) -> list[ScoutRow]` and `_rank_key(row, cells, schema: int = 1)`:
    - **Schema 2:** the bound term is `-lower` for `exploit` and `+upper` for `avoid`, so both sort ascending on one scale. A missing bound gives `math.inf`.
    - **Schema 1:** the bound term is `-lower` for every row, as today.
    - Every other key term is unchanged.
  - `LEGACY_BANNER = "legacy autopsy (schema 1): no known-at-entry check"`. It is the first non-blank line under `# Scout slate <date>` when `autopsy_schema(header) == 1`, and absent for schema 2.
  - `render_slate(ranked, drops, header, *, date, autopsy_path, cells: dict | None = None) -> str`. Each ranked row gains one line after its fields: `- projected pooled change: <+0.000 R | n/a> (<label>)`, with labels:
    - `PROJECTION_LABELS = {"exploit": "keep only this cell", "avoid": "drop this cell"}`
    - `no autopsy cell` when the row cites none, or `cells` is `None`

The formula gives the exact complement mean. The spec's "−share · Δ" is the same number when Δ is cell minus complement; the test pins that identity.

- [ ] **Step 1: Write the failing tests**

In `tests/scout/test_scout_merge.py`, add `"autopsy_schema": 2` to `HEADER`. The CLI test there then runs the schema-2 path; its `CELLS` carry `defined_at="entry"` since V200-15.

Append to `tests/scout/test_scout_merge_two_sided.py`:

```python
HEAD2 = {"window": ["2026-01-05", "2026-10-09"], "n": 212, "pooled_net_expr": 0.11,
         "pooled_win_rate": 0.52, "net_of_frictions": "modelled", "cells_tested": 3,
         "autopsy_schema": 2}


def test_projected_change_for_exploit_is_cell_minus_pooled():
    cell = dict(UP, n=40, net_expr=0.3)
    assert merge.projected_pooled_change(cell, HEAD2, "exploit") == pytest.approx(0.19)


def test_projected_change_for_avoid_is_the_exact_complement_minus_pooled():
    cell = dict(DOWN, n=40, net_expr=-0.2)
    got = merge.projected_pooled_change(cell, HEAD2, "avoid")
    complement = (212 * 0.11 - 40 * -0.2) / (212 - 40)
    assert got == round(complement - 0.11, 4) == 0.0721
    share, delta = 40 / 212, -0.2 - complement
    assert got == pytest.approx(-share * delta, abs=1e-4)


@pytest.mark.parametrize("cell, header, direction", [
    (None, HEAD2, "exploit"),
    (dict(UP, n=40, net_expr=0.3), {"n": 212}, "exploit"),
    (dict(UP, n=40, net_expr=None), HEAD2, "exploit"),
    (dict(DOWN, n=212, net_expr=-0.2), HEAD2, "avoid"),
    (dict(DOWN, n=40, net_expr=float("nan")), HEAD2, "avoid"),
    (dict(DOWN, n=40, net_expr=-0.2), dict(HEAD2, n=None), "avoid")])
def test_projected_change_is_none_when_it_cannot_be_computed(cell, header, direction):
    assert merge.projected_pooled_change(cell, header, direction) is None


def test_schema_2_ranks_exploit_and_avoid_by_the_bound_nearest_zero():
    a = _cell("regime=a", lo=0.05, hi=0.35)
    b = _cell("regime=b", lo=-0.40, hi=-0.20)
    c = _cell("regime=c", lo=0.10, hi=0.30)
    cells = {x["id"]: x for x in (a, b, c)}
    rows = [_row(a, "exploit"), _row(b, "avoid"), _row(c, "exploit")]
    assert [r.idea for r in merge.rank(rows, cells, schema=2)] == [
        "avoid-regime=b", "exploit-regime=c", "exploit-regime=a"]


def test_schema_1_ranks_every_row_by_its_lower_bound():
    legacy_avoid = _cell("regime=x", lo=0.20, hi=0.40)
    plain = _cell("regime=y", lo=0.10, hi=0.30)
    cells = {x["id"]: x for x in (legacy_avoid, plain)}
    rows = [_row(plain, "exploit"), _row(legacy_avoid, "avoid")]
    assert [r.idea for r in merge.rank(rows, cells)] == ["avoid-regime=x", "exploit-regime=y"]
    assert [r.idea for r in merge.rank(rows, cells, schema=2)] == ["exploit-regime=y", "avoid-regime=x"]


def test_the_slate_shows_the_projected_pooled_change_per_row():
    up, down = dict(UP, n=40, net_expr=0.3), dict(DOWN, n=40, net_expr=-0.2)
    cells = {up["id"]: up, down["id"]: down}
    playbook = _row(UP, "exploit", idea="pb")
    playbook.evidence, playbook.route = "playbook gap-and-hold", "/screen pb"
    text = merge.render_slate([_row(up, "exploit"), _row(down, "avoid"), playbook], [], HEAD2,
                              date="2026-10-30", autopsy_path="a.json", cells=cells)
    assert "- projected pooled change: +0.190 R (keep only this cell)" in text
    assert "- projected pooled change: +0.072 R (drop this cell)" in text
    assert "- projected pooled change: n/a (no autopsy cell)" in text
    bare = merge.render_slate([_row(up, "exploit")], [], HEAD2, date="2026-10-30",
                              autopsy_path="a.json")
    assert "- projected pooled change: n/a (no autopsy cell)" in bare


def test_a_schema_1_slate_opens_with_the_legacy_banner():
    legacy = {k: v for k, v in HEAD2.items() if k != "autopsy_schema"}
    lines = merge.render_slate([], [], legacy, date="2026-10-30", autopsy_path="a.json").splitlines()
    assert lines[0] == "# Scout slate 2026-10-30"
    assert [line for line in lines[1:] if line.strip()][0] == merge.LEGACY_BANNER
    assert merge.LEGACY_BANNER == "legacy autopsy (schema 1): no known-at-entry check"
    modern = merge.render_slate([], [], HEAD2, date="2026-10-30", autopsy_path="a.json")
    assert merge.LEGACY_BANNER not in modern


def test_the_cli_marks_a_schema_1_autopsy_as_legacy(tmp_path):
    up = _cell("regime=risk_on", lo=0.05, hi=0.35, defined_at=None)
    code = merge.main([str(_role_file(tmp_path, [_row(up, "exploit", idea="kept-idea")])),
                       "--autopsy", str(_autopsy(tmp_path, [up], schema=None)),
                       "--out-dir", str(tmp_path), "--date", "2026-10-30"])
    assert code == 0
    slate = (tmp_path / "2026-10-30-scout-slate.md").read_text(encoding="utf-8")
    assert merge.LEGACY_BANNER in slate.split("## Ranked")[0]
    assert "### 1. kept-idea (regime-desk)" in slate
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_two_sided.py`
Expected: the new tests FAIL with `AttributeError: module 'scout_merge' has no attribute 'projected_pooled_change'` (`'LEGACY_BANNER'`), and with `TypeError` on `rank(..., schema=2)` and `render_slate(..., cells=...)`. The V200-15 tests still pass.

- [ ] **Step 3: Implement in `scripts/dev/scout_merge.py`**

1. Add `LEGACY_BANNER` and `PROJECTION_LABELS` beside `BOUNDARY_NOTE`.
2. **`projected_pooled_change`** (after `_upper_bound`): read every input through `_finite_number`, then use a two-entry dispatch on `direction` rather than nested `if`s. Its docstring says: "Display only: exploit keeps only the cell, avoid drops it; both from the autopsy JSON (spec Part 5.5)."
3. **`_rank_key(row, cells, schema=1)`:** compute the bound term in a helper, `_bound_term(cell, direction, schema) -> float`. The other five tuple entries stay as they are. `rank(rows, cells, schema=1)` passes `schema` through.
4. **`_row_block(position, row, cells, header)`:** after the field lines, add the projected line. Use `cells.get(row.cell_id)` when `cells` is not `None` and the row has a `cell_id`, otherwise `None`. The label is `PROJECTION_LABELS.get(row.direction.strip(), "keep only this cell")` when a cell exists, else `no autopsy cell`. The number prints as `f"{value:+.3f} R"`, or `n/a` when it is `None`.
5. **`render_slate(..., cells=None)`:** when `autopsy_schema(header) == 1`, insert `LEGACY_BANNER, ""` right after the title and its blank line. Pass `cells` and `header` to `_row_block`.
6. **`main`:** pass `schema=schema` to `rank` and `cells=cells` to `render_slate`. `render_slate` may call `autopsy_schema` again, because the header was already validated inside the `try`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_two_sided.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py
python -m radon cc -s -n C <wt>/scripts/dev/scout_merge.py
```

Expected: every run reports `0 failed`, and radon prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add scripts/dev/scout_merge.py tests/scout/test_scout_merge.py \
    tests/scout/test_scout_merge_two_sided.py
git -C <wt> commit -m "feat(scout): v200 rank by the bound nearest zero, show projected pooled change, legacy banner (V200-16)"
```

### Task V200-17: End-to-end verification on fresh data

**Model:** sonnet — runs the finished tool chain and records counts. The checks are scripted below, and the one production command is read-only and taken verbatim from the trade-scout skill.

**Files:**
- Create: `docs/superpowers/results/2026-10-29-v200-verification.md`
- Scratch only, never committed: `<scratch>/v200_rows.csv`, `<scratch>/v200_rejections.csv`, `<scratch>/v200_autopsy/`, `<scratch>/v200_rows_1029.md`, `<scratch>/v200_1029_schema2.json`, `<scratch>/v200_merge_legacy/`, `<scratch>/v200_merge_s2/`, and the three check scripts below.

**Interfaces:**
- Consumes every earlier task's output:
  - From the export and autopsy: the export columns (V200-3), `header.alert_hour_coverage` and the coverage lines (V200-4), the stall line (V200-10), `eras` (V200-11) and `defined_at` / `autopsy_schema` (V200-13).
  - From the merge: `direction` (V200-14), `screen_rows(..., schema=)` and the drop texts (V200-15), and `LEGACY_BANNER` (V200-16).
  - Committed inputs: `docs/superpowers/results/2026-10-29-scout-rows.md` (the raw 10-29 rows) and `docs/superpowers/results/2026-10-29-book-autopsy.json` (schema 1).
- Produces: the results file, which covers spec Verification items 1 and 2 and points to item 3. V200-18 is item 4.

**Before you start:**
- This task runs one read-only production command, the export.
- The controller asks the partner with `AskUserQuestion` before dispatching this task (trade-scout skill, Step 1). It is best run outside the US session and premarket.
- The dispatch prompt says `export approved`. Without that phrase, return `BLOCKED: production export not approved`.
- `scripts/ops/ssh-hetzner.sh` is uncommitted, so it exists only in the main tree. `<main>` below is `E:/Documents/Private/Projects/Discord-Bot`.
- Never write to `docs/superpowers/results/` except the one results file. This run is a verification, not a scout run, so the autopsy pair and the slates stay in `<scratch>`.

**Reporting rules for the results file:**
- Record counts only.
- Quote no pooled ExpR or win rate (`pooled-numbers`).
- Never set a v200 q or Δ beside a 10-29 one (spec Non-goals).
- The re-merged 10-29 figures are the old, fake-hour artefact figures. The re-merge tests the rule, not the book.

- [ ] **Step 1: Export fresh rows (read-only, production)**

```bash
bash <main>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" < <wt>/scripts/ops/export_book_rows.sh > <scratch>/v200_rows.csv
bash <main>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rejections" < <wt>/scripts/ops/export_book_rows.sh > <scratch>/v200_rejections.csv
head -1 <scratch>/v200_rows.csv
```

Expected: the header line ends `,plan_issued_at,plan_issued_at_source`. Note the UTC time of the export from `date -u`.

- [ ] **Step 2: Run the autopsy into the scratchpad**

Use `--bars-dir <scratch>/autopsy_bars` when that directory exists from an earlier run this session; otherwise omit `--bars-dir`, because these checks do not read bar cells. `<date>` is today's date, `date -u +%F`.

```bash
python <wt>/scripts/reports/book_autopsy.py <scratch>/v200_rows.csv <scratch>/v200_rejections.csv \
    --out-dir <scratch>/v200_autopsy --date <date>
```

Expected: exit code 0, writing `<scratch>/v200_autopsy/<date>-book-autopsy.{json,md}`.

- [ ] **Step 3: Check item 1 (the hour comes only from `plan_issued_at`, plus the coverage and stall lines)**

Write `<scratch>/v200_verify_autopsy.py`:

```python
"""V200-17 item 1: every alert hour comes from plan_issued_at, coverage and the stall line print."""
import csv
import json
import sys
from pathlib import Path

wt, scratch, date = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(wt / "scripts" / "reports"))
sys.path.insert(0, str(wt))
from autopsy import rows as R  # noqa: E402
from swingbot.core.market.session import US_MARKET_TZ  # noqa: E402

csv_path = scratch / "v200_rows.csv"
with csv_path.open(encoding="utf-8", newline="") as fh:
    raw = list(csv.DictReader(fh))
assert list(raw[0])[-2:] == ["plan_issued_at", "plan_issued_at_source"], list(raw[0])[-2:]
loaded = R.load_rows(csv_path)
assert len(loaded) == len(raw), (len(loaded), len(raw))     # one BookRow per record, file order
bad, from_issued, status_only = [], 0, 0
for rec, row in zip(raw, loaded):
    issued = (rec.get("plan_issued_at") or "").strip()
    stamp = R._timestamp(issued) if issued else None
    want = None if stamp is None else stamp.astimezone(US_MARKET_TZ).hour
    if row.plan_hour != want:
        bad.append((rec.get("plan_id"), issued, rec.get("plan_first_status_at"), row.plan_hour))
    from_issued += want is not None
    status_only += want is None and bool((rec.get("plan_first_status_at") or "").strip())
assert not bad, bad[:10]
out = scratch / "v200_autopsy"
data = json.loads((out / f"{date}-book-autopsy.json").read_text(encoding="utf-8"))
md = (out / f"{date}-book-autopsy.md").read_text(encoding="utf-8")
h = data["header"]
assert set(data) == {"header", "cells", "tallies", "giveback"}
assert h["autopsy_schema"] == 2
cov = h["alert_hour_coverage"]
assert sum(cov["trades"].values()) == h["n"], (cov["trades"], h["n"])
assert "alert-hour coverage (trades):" in md and "alert-hour coverage (plans):" in md
stall = [line.strip() for line in md.splitlines() if "stall exclusion stall_2026_08:" in line]
assert len(stall) == 1, stall
assert all(c.get("defined_at") in ("entry", "fill", "outcome") for c in data["cells"])
assert all(c.get("eras") is not None for c in data["cells"])
print(json.dumps({"csv_rows": len(raw), "hours_from_issued_at": from_issued,
                  "first_status_stamp_but_hour_unknown": status_only, "coverage": cov,
                  "stall_line": stall[0], "n_after_stall": h["n"],
                  "era_boundary": h["era_boundary"], "cells": len(data["cells"])}, indent=2))
```

Run: `python <scratch>/v200_verify_autopsy.py <wt> <scratch> <date>`
Expected: no `AssertionError`, and one JSON summary printed. If an assertion fails, stop with `BLOCKED: item 1 <assertion text>` and name the owning task (V200-3, V200-4, V200-10 or V200-13). Never fix code here.

- [ ] **Step 4: Prepare the 10-29 re-merge inputs**

The direction rule: a row citing a cell whose Δ interval is negative is `avoid`; a positive interval or a playbook row is `exploit`. Write `<scratch>/v200_prepare_1029.py`:

```python
"""V200-17 item 2 inputs: the raw 10-29 rows with direction added, and a schema-2 view of the
10-29 autopsy (defined_at from the v200 cut tags, every figure unchanged)."""
import json
import re
import sys
from pathlib import Path

wt, scratch = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(wt / "scripts" / "reports"))
sys.path.insert(0, str(wt))
from autopsy import report  # noqa: E402

DIRECTION = {
    "pre-close-exit-on-gap-risk": "avoid", "stop-fill-overshoot-audit": "avoid",
    "bank-partial-on-favourable-open-gap": "avoid", "no-chase-favourable-gap-limit": "avoid",
    "atr-reentry-after-stop": "exploit", "tight-base-breakout": "exploit",
    "after-close-alerts-resting-order-only": "exploit", "weekend-hold-survivor-screen": "exploit"}
results = wt / "docs" / "superpowers" / "results"
out, idea = [], None
for line in (results / "2026-10-29-scout-rows.md").read_text(encoding="utf-8").splitlines():
    start = re.match(r"^- idea:\s*(.*)$", line)
    idea = start.group(1).strip() if start else idea
    out.append(line)
    if line.startswith("  edge:"):
        out.append(f"  direction: {DIRECTION[idea]}")
assert sum(line.startswith("  direction:") for line in out) == len(DIRECTION)
(scratch / "v200_rows_1029.md").write_text("\n".join(out) + "\n", encoding="utf-8")

data = json.loads((results / "2026-10-29-book-autopsy.json").read_text(encoding="utf-8"))
assert "autopsy_schema" not in data["header"]
tags = report.cut_defined_at(data["header"].get("sector_map") or {})
missing = sorted({c["cut"] for c in data["cells"]} - set(tags))
assert not missing, missing
for cell in data["cells"]:
    cell["defined_at"] = tags[cell["cut"]]
data["header"]["autopsy_schema"] = 2
(scratch / "v200_1029_schema2.json").write_text(json.dumps(data), encoding="utf-8")
print(len(DIRECTION), "rows with direction;", len(data["cells"]), "cells tagged")
```

Run: `python <scratch>/v200_prepare_1029.py <wt> <scratch>`
Expected: `8 rows with direction; <k> cells tagged`.

- [ ] **Step 5: Re-merge under both schemas**

```bash
python <wt>/scripts/dev/scout_merge.py <scratch>/v200_rows_1029.md \
    --autopsy <wt>/docs/superpowers/results/2026-10-29-book-autopsy.json \
    --out-dir <scratch>/v200_merge_legacy --date 2026-10-29
python <wt>/scripts/dev/scout_merge.py <scratch>/v200_rows_1029.md \
    --autopsy <scratch>/v200_1029_schema2.json \
    --out-dir <scratch>/v200_merge_s2 --date 2026-10-29
```

Expected: both runs exit 0 and print `scout_merge: <r> ranked, <d> dropped -> ...`.

Write `<scratch>/v200_check_merge.py`:

```python
"""V200-17 item 2: the 10-29 rows re-merged -- legacy banner on schema 1, known-at-entry drops on schema 2."""
import sys
from pathlib import Path

wt, scratch = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(wt / "scripts" / "dev"))
import scout_merge as merge  # noqa: E402

NAME = "2026-10-29-scout-slate.md"
legacy = (scratch / "v200_merge_legacy" / NAME).read_text(encoding="utf-8")
modern = (scratch / "v200_merge_s2" / NAME).read_text(encoding="utf-8")
assert merge.LEGACY_BANNER in legacy.split("## Ranked")[0]
assert merge.LEGACY_BANNER not in modern


def dropped(text):
    section = text.split("## Dropped")[1].split("\n## ")[0]   # stop before ## Panel review
    return {line.split("|")[1].strip(): line for line in section.splitlines()
            if line.startswith("| ") and not line.startswith("| Idea")}


old = dropped((wt / "docs" / "superpowers" / "results" / NAME).read_text(encoding="utf-8"))
new_legacy = dropped(legacy)
for idea, line in old.items():                      # schema 1 reproduces the 10-29 reasons
    assert new_legacy.get(idea) == line, (idea, new_legacy.get(idea), line)
EXPECT = {"pre-close-exit-on-gap-risk": "cell gap_through_stop=through_stop is outcome-defined",
          "stop-fill-overshoot-audit": "cell exit_reason=stop is outcome-defined",
          "bank-partial-on-favourable-open-gap": "cell open_gap_bucket=favourable is fill-defined",
          "no-chase-favourable-gap-limit": "cell open_gap_bucket=favourable is fill-defined",
          "weekend-hold-survivor-screen": "cell weekend_hold=yes is outcome-defined"}
s2 = dropped(modern)
for idea, text in EXPECT.items():
    assert idea in s2 and f"{text} (not known at entry)" in s2[idea], (idea, s2.get(idea))
ranked = [line for line in modern.split("## Ranked")[1].split("## Dropped")[0].splitlines()
          if line.startswith("### ")]
print("legacy dropped:", len(new_legacy), "| schema-2 dropped:", len(s2))
print("schema-2 ranked:", ranked)
for idea, line in sorted(s2.items()):
    print(line)
```

Run: `python <scratch>/v200_check_merge.py <wt> <scratch>`
Expected: no `AssertionError`. `weekend-hold-survivor-screen` is also dropped as outcome-defined: the spec's Part 5.2 tags `weekend_hold` as `outcome`, although its Verification list names only four rows. Record it as a fifth not-known-at-entry drop. A failed assertion stops the task with `BLOCKED: item 2 <assertion text>`.

- [ ] **Step 6: Write the results file**

Create `docs/superpowers/results/2026-10-29-v200-verification.md` with these sections:

- **`# v200 verification`**, then one line linking the spec and the plan index.
- **`## Item 1 — fresh autopsy`:**
  - the export UTC time and the CSV row count;
  - the coverage dicts, trades and plans by `live` / `discord` / `unknown`;
  - `hours_from_issued_at` and `first_status_stamp_but_hour_unknown`, with one sentence: no hour came from a date-only or fill stamp, checked row by row against `plan_issued_at`;
  - the stall line verbatim;
  - `n_after_stall`, `autopsy_schema 2`, the cell count with every cell tagged and carrying eras, and the era boundary;
  - a note that `discord` stays 0 until `v200_001` ships through the partner's deploy.
- **`## Item 2 — 10-29 rows re-merged`:**
  - the direction table and its rule;
  - the legacy run: banner present, the four 10-29 drop reasons reproduced exactly, the ranked list;
  - the schema-2 view: each dropped row with its reason as printed, the ranked list, and the fifth `weekend_hold` drop with the sentence from Step 5;
  - one sentence: the 10-29 figures are the pre-v200 artefact figures, so this tests the rule, not the book, and no v200 q or Δ is compared with them.
- **`## Item 3 — backfill match rate`:** a link to `2026-10-29-v200-backfill-dry-run.md` (V200-6), with the date the partner saw the match rate as recorded there.
- **`## Item 4 — full suite`:** `pending V200-18`.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add docs/superpowers/results/2026-10-29-v200-verification.md
git -C <wt> commit -m "docs(v200): end-to-end verification -- hour coverage, stall line, two-sided re-merge of the 10-29 rows (V200-17)"
```

### Task V200-18: Full suite

**Model:** sonnet — runs the gates and routes each failure to its owning task. It writes no new design.

**Files:**
- Modify: only the files of the task that owns an observed defect, as listed in that task's **Files** block. No new file.
- Modify: `docs/superpowers/results/2026-10-29-v200-verification.md` (fill in `## Item 4 — full suite`)

**Interfaces:**
- Consumes: the whole branch, V200-1 … V200-17.
- Produces: the spec's Verification item 4, a green full suite run once.

- [ ] **Step 1: Sync the database replica if needed**

The full suite includes the database tests (`tests/db/`, and V200-7's `test_v200_discord_issued_at.py`). If `/replicate-prod-db` has not run this session, run it first, into the shared `swing-db` container (`CLAUDE.md`). Never use a per-task container or database.

- [ ] **Step 2: Run the static gates**

```bash
python <wt>/scripts/dev/complexity_gate.py
python <wt>/scripts/dev/sync_codex.py --check
python -m radon cc -s -n C <wt>/scripts/dev/scout_merge.py <wt>/scripts/reports/autopsy/ <wt>/scripts/ops/backfill_issued_at_discord.py
```

Expected:
- `complexity_gate.py` exits 0.
- `sync_codex.py --check` prints `Codex mirror is current.`
- radon prints nothing.

- [ ] **Step 3: Run the full suite once**

Run it through the `test-runner` subagent, so the output stays out of this context: `python <wt>/scripts/dev/testrun.py full`.
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 4: Fix a failure, if any, in its owning task's files only**

For each failing test:
1. Find the task whose **Files** block lists the code under test.
2. Fix it there, behaviour exactly as that task specifies.
3. Re-run only that test: `python <wt>/scripts/dev/testrun.py file <test path>` or `python -m pytest <path>::<test> -v`.

Never re-run the whole suite to check a single fix. Never relax an assertion a v200 task pinned. If a fix would change a cross-task contract in the index, stop with `BLOCKED: <test> needs <contract> changed`.

After the fixes, re-run the static gates from Step 2.

- [ ] **Step 5: Record and commit**

Replace `pending V200-18` in `docs/superpowers/results/2026-10-29-v200-verification.md` with:
- the date;
- the pass, skip and fail counts from the one full run;
- one line per fix, naming the test and the owning task, or `no fixes`.

```bash
git -C <wt> add docs/superpowers/results/2026-10-29-v200-verification.md <each fixed file, named>
git -C <wt> commit -m "test(v200): full suite green; verification item 4 recorded (V200-18)"
```

`/close-out` follows: it applies `Bump: bot patch`. The deploy that ships `v200_001` is the partner's, and it is not part of this plan.
