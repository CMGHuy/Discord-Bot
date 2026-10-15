# v161 Trade scout, part 3: merge slate and generator roles (TS9–TS10; TS11–TS14 are in `2026-10-15-v161-trade-scout_3b-agent-routing-run.md`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole:** pull one task with `grep -n "^### Task TS10" -A 400 docs/superpowers/plans/2026-10-15-v161-trade-scout_3-slate-roles-run.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v161-trade-scout-design.md`](../specs/2026-10-15-v161-trade-scout-design.md) (§ 2–6, Retention and removal, Codex mirror and docs, Testing, Panel review)
**Index:** [`2026-10-15-v161-trade-scout_0-index.md`](2026-10-15-v161-trade-scout_0-index.md) — Global Constraints, `## Parallelisation`, the shared contracts (Export columns, cell id, cut names, Autopsy JSON, Row format) and the Task ledger bind every task below.
**Bump:** none
**Edge:** none (integrity)

**Conventions used in every task of this part**

- `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-15-v161-trade-scout` (the branch), `$SCRATCH` = the session scratchpad. Never `cd`; use absolute paths and `git -C $WT`.
- `scripts/dev/scout_merge.py` has no package (`scripts/dev` has no `__init__.py`); tests import it the way TS8's test does:
  ```python
  ROOT = Path(__file__).resolve().parents[2]
  sys.path.insert(0, str(ROOT / "scripts" / "dev"))
  import scout_merge as merge  # noqa: E402
  ```
- Skill and agent text obeys `tests/hooks/test_skill_shape.py`: ≤ 80 lines, no bare comparator before a number, no `<number> R` or `<number> pp` in a body. Thresholds (q cut-off, thin rule) live only in `docs/claude/skills-tools.md` § Generator roles (v161) and in the scripts.
- Every `.claude/skills|agents` change is followed by `python $WT/scripts/dev/sync_codex.py` and the generated `.agents/` / `.codex/` files are committed in the same commit.
- Free only: no `claude plugin eval`, no API keys, no billed or cloud run.

# Phase C (continued): merge ranking and slate

### Task TS9: Merge: drops, pinning, ranking, slate, CLI

**Model:** sonnet — normal TDD inside one script, behaviour fixed by spec § 6 and the ledger.

**Files:**
- Modify: `scripts/dev/scout_merge.py` (append below TS8's code)
- Create: `tests/scout/test_scout_merge.py`

**Interfaces:**
- Consumes (TS8, `scripts/dev/scout_merge.py`, part `_2b`): `ROOT`, `LEDGER`, `METHODOLOGY` (default paths; reuse them, never redefine); `EXACT_ONLY = "="` (closed names from PASS rows match only an identical idea); `ROW_FIELDS: tuple[str, ...]` (the 11 Row format keys, `idea` first); `@dataclass ScoutRow(role, idea, claim, evidence, exploratory, edge, mechanism, order_form, manual_actions, pairs_with, divergence, route)` (all `str`) with properties `cell_id -> str | None` (the `<cut>=<value>` after `cell ` in `evidence`), `playbook_id -> str | None` (the id after `playbook ` in `evidence`), `quoted_n -> int | None` (the integer after `N ` in `evidence`); `@dataclass(frozen=True) Drop(idea: str, role: str, reason: str)`; `normalise(name: str) -> str` (case-insensitive kebab-case: lower-cased, every run of non-alphanumerics becomes one `-`, leading/trailing `-` stripped); `parse_rows(text: str) -> tuple[list[ScoutRow], list[Drop]]` (blocks grouped under `## role: <name>` lines; malformed rows (missing field, `exploratory` not `yes`, unknown `edge` or `divergence`) and duplicate ideas already come back as `Drop`s); `closed_names(methodology: Path = METHODOLOGY) -> set[str]`; `ledger_names(ledger: Path = LEDGER) -> dict[str, str]` (normalised id, id without `screen-`/`vNN-`, short hypothesis head and ALL-CAPS knobs → ledger id; exact matching only); `closed_match(idea: str, names: Iterable[str]) -> str | None` (equal, or a closed name's tokens as a contiguous run inside the idea, e.g. `gap-volume-continuation` → `gap-volume`).
- Consumes (TS7): the Autopsy JSON shape (index § Shared contracts): `header.window`, `header.n`, `header.cells_tested`, `header.net_of_frictions`; `cells[].id`, `.n`, `.weeks`, `.ci` (`[lo, hi]` or `null`), `.thin`.
- Produces: `EDGE_ORDER = ("expectancy", "harvest", "volume")`; `HOLDOUT_REMINDER: str`; `BOUNDARY_NOTE: str`; `screen_rows(rows: list[ScoutRow], *, closed: set[str], ledger: dict[str, str], cells: dict[str, dict]) -> tuple[list[ScoutRow], list[Drop]]`; `rank(rows: list[ScoutRow], cells: dict[str, dict]) -> list[ScoutRow]`; `render_slate(ranked: list[ScoutRow], drops: list[Drop], header: dict, *, date: str, autopsy_path: str) -> str`; CLI `python scripts/dev/scout_merge.py <role-output.md> --autopsy <json> [--ledger PATH] [--methodology PATH] [--out-dir docs/superpowers/results] [--date YYYY-MM-DD]` writing `<out-dir>/<date>-scout-slate.md`; `main(argv: list[str] | None = None) -> int`. TS11's `trade-scout` skill and TS13 call the CLI.

**Rules this task implements (spec § 6, binding):**
- **Drops** (`screen_rows` re-checks duplicates, edge and `exploratory` itself, so it is safe on rows that did not come through `parse_rows`), first matching reason wins, each recorded as a `Drop` with its reason: (1) the normalised idea repeats an already kept row's idea (duplicate); (2) the normalised idea is a key of `ledger` (ledger id or hypothesis); (3) `closed_match(idea, closed)` returns a name; (4) `edge` is not in `EDGE_ORDER`; then, **unless the row is a playbook `/screen` row** (`playbook_id` set and `route` starts with `/screen`): (5) no `cell_id`; (6) the cell is not in the autopsy JSON (an invented figure); (7) the cell is `thin`; (8) the quoted N differs from the cell's N (an invented figure); (9) `exploratory` is not `yes` (boundary 5); (10) the cell's `ci` is `null` or its lower bound is ≤ 0.
- **Rank:** `divergence: yes` rows pinned first; then by `EDGE_ORDER` index; within an edge class a row whose `manual_actions` is not `none` ranks below every `none` row; then Δ lower bound descending (a playbook row has none and sorts last in its class); then cell N descending; then normalised idea (deterministic tie-break).
- **Slate:** the autopsy header's window, N, cells tested and net-of-frictions flag copied verbatim, `HOLDOUT_REMINDER` (boundary 5) and `BOUNDARY_NOTE` (boundaries 1–2) near the top, `## Ranked` then `## Dropped` (a table, every drop with its reason).

- [ ] **Step 1: Write the failing test**

Create `tests/scout/test_scout_merge.py`:

```python
"""scout_merge drops, pinning, ranking and the slate (v161 TS9).

Parsing (parse_rows, closed_names, ledger_names, closed_match) is pinned in
test_scout_merge_parse.py. Here rows are built directly, so each drop and
ranking rule is tested alone; the CLI test runs the whole merge against the
real ledger and the real closed pre-registrations table."""
import json
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import scout_merge as merge  # noqa: E402

GOOD_EVIDENCE = "cell regime=risk_on; N 40; weeks 12; Δ net ExpR 0.200 [0.050, 0.350]; q 0.040"


def _row(**kw):
    base = {f.name: "" for f in fields(merge.ScoutRow)}
    base.update(role="setup-scout", idea="idea-a", claim="A claim.", evidence=GOOD_EVIDENCE,
                exploratory="yes", edge="expectancy", mechanism="Why it pays.",
                order_form="stop-buy above the signal high, day order", manual_actions="none",
                pairs_with="n/a", divergence="no", route="/prereg")
    base.update(kw)
    return merge.ScoutRow(**base)


def _cell(cid, *, n=40, weeks=12, lo=0.05, hi=0.35, thin=False):
    cut, value = cid.split("=", 1)
    ci = None if lo is None else [lo, hi]
    delta = None if lo is None else (lo + hi) / 2
    return {"id": cid, "cut": cut, "value": value, "n": n, "weeks": weeks, "win_rate": 0.5,
            "net_expr": 0.2, "gross_expr": 0.22, "delta": delta, "ci": ci, "p": 0.01,
            "q": 0.04, "thin": thin, "bar_covered_n": None, "extra": {}}


CELLS = {c["id"]: c for c in (
    _cell("regime=risk_on"),
    _cell("strategy_horizon=RSI|1m", n=90, weeks=20, lo=0.10, hi=0.30),
    _cell("weekday=Fri", n=12, weeks=5, thin=True),
    _cell("ticker=AAA", lo=-0.10, hi=0.30),
    _cell("direction=bearish", lo=None),
)}


def _screen(rows, *, closed=(), ledger=None, cells=CELLS):
    return merge.screen_rows(list(rows), closed=set(closed), ledger=dict(ledger or {}), cells=cells)


def _reasons(drops):
    return {d.idea: d.reason for d in drops}


# ---- drops ---------------------------------------------------------------

def test_a_supported_row_is_kept_without_a_drop():
    kept, drops = _screen([_row()])
    assert [r.idea for r in kept] == ["idea-a"] and drops == []


def test_a_ledger_id_is_dropped_naming_the_id():
    kept, drops = _screen([_row(idea="e33-avwap-levels")], ledger={"e33-avwap-levels": "e33-avwap-levels"})
    assert kept == []
    assert "ledger" in drops[0].reason and "e33-avwap-levels" in drops[0].reason
    assert drops[0].role == "setup-scout"


def test_a_closed_name_is_dropped_naming_the_closed_row():
    kept, drops = _screen([_row(idea="regime-allow")], closed={"regime-allow"})
    assert kept == []
    assert "closed pre-registration" in drops[0].reason


def test_a_second_row_with_the_same_idea_is_a_duplicate():
    kept, drops = _screen([_row(idea="idea-a"), _row(idea="Idea_A", role="regime-desk")])
    assert [r.role for r in kept] == ["setup-scout"]
    assert "duplicate" in drops[0].reason and drops[0].role == "regime-desk"


def test_an_unknown_edge_is_dropped():
    _, drops = _screen([_row(edge="integrity")])
    assert "edge" in drops[0].reason


def test_a_thin_cell_is_dropped():
    _, drops = _screen([_row(evidence="cell weekday=Fri; N 12; weeks 5; Δ net ExpR 0.2 [0.05, 0.35]; q 0.04")])
    assert "thin" in drops[0].reason


def test_a_cell_missing_from_the_autopsy_is_an_invented_figure():
    _, drops = _screen([_row(evidence="cell weekday=Mon; N 50; weeks 15; Δ net ExpR 0.3 [0.1, 0.5]; q 0.01")])
    assert "not in the autopsy" in drops[0].reason


def test_a_row_citing_no_cell_and_no_playbook_screen_is_dropped():
    _, drops = _screen([_row(evidence="the book looks weak on Mondays")])
    assert "no autopsy cell" in drops[0].reason


def test_a_quoted_n_that_differs_from_the_cell_is_an_invented_figure():
    _, drops = _screen([_row(evidence="cell regime=risk_on; N 400; weeks 12; Δ net ExpR 0.2 [0.05, 0.35]; q 0.04")])
    assert "quoted N 400" in drops[0].reason


def test_autopsy_evidence_not_marked_exploratory_is_dropped():
    _, drops = _screen([_row(exploratory="no")])
    assert "exploratory" in drops[0].reason


def test_a_lower_bound_at_or_below_zero_is_dropped():
    rows = [_row(idea="neg", evidence="cell ticker=AAA; N 40; weeks 12; Δ net ExpR 0.1 [-0.1, 0.3]; q 0.2"),
            _row(idea="none", evidence="cell direction=bearish; N 40; weeks 12; Δ net ExpR n/a; q n/a")]
    kept, drops = _screen(rows)
    assert kept == []
    reasons = _reasons(drops)
    assert "at or below zero" in reasons["neg"] and "at or below zero" in reasons["none"]


def test_a_playbook_screen_row_needs_no_cell():
    row = _row(idea="gap-and-hold", evidence="playbook gap-and-hold", route="/screen gap-and-hold")
    kept, drops = _screen([row])
    assert [r.idea for r in kept] == ["gap-and-hold"] and drops == []


def test_a_playbook_row_routed_to_prereg_still_needs_a_cell():
    row = _row(idea="gap-and-hold", evidence="playbook gap-and-hold", route="/prereg")
    _, drops = _screen([row])
    assert "no autopsy cell" in drops[0].reason


# ---- ranking -------------------------------------------------------------

def test_rank_orders_by_edge_then_lower_bound_then_n():
    rows = [
        _row(idea="vol", edge="volume"),
        _row(idea="harv", edge="harvest"),
        _row(idea="exp-low", evidence=GOOD_EVIDENCE),
        _row(idea="exp-high", evidence="cell strategy_horizon=RSI|1m; N 90; weeks 20; Δ net ExpR 0.2 [0.10, 0.30]; q 0.01"),
    ]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["exp-high", "exp-low", "harv", "vol"]


def test_equal_lower_bounds_break_on_n_then_name():
    cells = dict(CELLS, **{"regime=risk_off": _cell("regime=risk_off", n=80)})
    rows = [_row(idea="b-small"), _row(idea="a-small"),
            _row(idea="big", evidence="cell regime=risk_off; N 80; weeks 12; Δ net ExpR 0.2 [0.05, 0.35]; q 0.04")]
    assert [r.idea for r in merge.rank(rows, cells)] == ["big", "a-small", "b-small"]


def test_divergence_rows_are_pinned_above_every_edge_class():
    rows = [_row(idea="exp"), _row(idea="div", edge="volume", divergence="yes")]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["div", "exp"]


def test_manual_action_ranks_a_row_down_within_its_edge_class():
    rows = [_row(idea="manual", manual_actions="move the stop to breakeven after the first target",
                 evidence="cell strategy_horizon=RSI|1m; N 90; weeks 20; Δ net ExpR 0.2 [0.10, 0.30]; q 0.01"),
            _row(idea="plain"),
            _row(idea="harv", edge="harvest")]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["plain", "manual", "harv"]


def test_a_playbook_row_sorts_last_in_its_edge_class():
    rows = [_row(idea="pb", evidence="playbook gap-and-hold", route="/screen pb"), _row(idea="cell-backed")]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["cell-backed", "pb"]


# ---- slate ---------------------------------------------------------------

HEADER = {"window": ["2026-01-05", "2026-10-09"], "n": 212, "pooled_net_expr": 0.11,
          "pooled_win_rate": 0.52, "net_of_frictions": "modelled", "cells_tested": 147,
          "bar_covered_n": 190, "resamples": 10000, "seed": 42, "notes": []}


def test_the_slate_copies_the_header_and_carries_both_boundaries():
    text = merge.render_slate([_row()], [], HEADER, date="2026-10-16",
                              autopsy_path="docs/superpowers/results/2026-10-16-book-autopsy.json")
    assert text.startswith("# Scout slate 2026-10-16\n")
    assert "2026-01-05 to 2026-10-09" in text
    assert "**N:** 212" in text and "**Cells tested:** 147" in text and "modelled" in text
    assert "`docs/superpowers/results/2026-10-16-book-autopsy.json`" in text
    assert merge.HOLDOUT_REMINDER in text and merge.BOUNDARY_NOTE in text
    assert text.index("## Ranked") < text.index("## Dropped")
    assert "### 1. idea-a (setup-scout)" in text
    for name in merge.ROW_FIELDS[1:]:
        assert f"- {name}: " in text, name
    assert text.rstrip().endswith("None.")


def test_the_holdout_reminder_states_boundary_five():
    reminder = merge.HOLDOUT_REMINDER
    for phrase in ("exploratory", "holdout", "contaminated", "TRAIN/VALIDATION", "2026-01-01", "/screen"):
        assert phrase in reminder, phrase


def test_every_drop_is_listed_with_its_reason_and_pipes_are_escaped():
    drops = [merge.Drop(idea="x", role="regime-desk", reason="cell strategy_horizon=RSI|1m is thin")]
    text = merge.render_slate([], drops, HEADER, date="2026-10-16", autopsy_path="a.json")
    assert "No row survived the merge." in text
    assert "| x | regime-desk | cell strategy_horizon=RSI\\|1m is thin |" in text


def test_a_pinned_row_says_so_in_its_heading():
    text = merge.render_slate([_row(divergence="yes")], [], HEADER, date="2026-10-16", autopsy_path="a.json")
    assert "### 1. idea-a (setup-scout) — pinned: live diverges from the plan" in text


# ---- CLI, against the real ledger and the real closed table ----------------

def _block(idea, evidence=GOOD_EVIDENCE, route="/prereg", edge="expectancy"):
    return (f"- idea: {idea}\n"
            f"  claim: One sentence.\n"
            f"  evidence: {evidence}\n"
            f"  exploratory: yes\n"
            f"  edge: {edge}\n"
            f"  mechanism: Why a trader expects it to pay.\n"
            f"  order_form: stop-buy above the signal high, day order\n"
            f"  manual_actions: none\n"
            f"  pairs_with: n/a\n"
            f"  divergence: no\n"
            f"  route: {route}\n")


def test_the_cli_drops_ledger_closed_and_renamed_ideas_and_writes_the_slate(tmp_path, capsys):
    role_output = tmp_path / "roles.md"
    role_output.write_text(
        "## role: setup-scout\n\n"
        + _block("kept-idea") + "\n"
        + _block("screen-high52w") + "\n"     # a ledger id
        + _block("gap-volume-continuation") + "\n"   # SCREEN-FAIL `gap_volume` renamed (closed_match)
        + "## role: regime-desk\n\n"
        + _block("regime-allow") + "\n",       # closed table: `REGIME_ALLOW`
        encoding="utf-8")
    autopsy = tmp_path / "autopsy.json"
    autopsy.write_text(json.dumps({"header": HEADER, "cells": list(CELLS.values()),
                                   "tallies": [], "giveback": {"n": 0, "mean": 0.0, "median": 0.0}}),
                       encoding="utf-8")
    out_dir = tmp_path / "results"
    code = merge.main([str(role_output), "--autopsy", str(autopsy),
                       "--out-dir", str(out_dir), "--date", "2026-10-16"])
    assert code == 0
    slate = (out_dir / "2026-10-16-scout-slate.md").read_text(encoding="utf-8")
    ranked, dropped = slate.split("## Dropped")
    assert "### 1. kept-idea (setup-scout)" in ranked
    for idea in ("screen-high52w", "gap-volume-continuation", "regime-allow"):
        assert idea not in ranked, idea
        assert f"| {idea} |" in dropped, idea
    assert "1 ranked, 3 dropped" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_scout_merge.py`
Expected: FAIL — `AttributeError: module 'scout_merge' has no attribute 'screen_rows'` (and the other new names).

- [ ] **Step 3: Write the implementation**

TS8's import block (`from __future__ import annotations`, `json`, `re`, `dataclass`, `Path`, `Iterable`) stays; add these three lines to it, in alphabetical place:

```python
import argparse
import datetime as dt
import math
```

Then append below TS8's code (above any existing `if __name__ == "__main__":` block; the file keeps exactly one such block, at the end):

```python
# ---- v161 TS9: drops, pinning, ranking, slate, CLI ------------------------

# ROOT, LEDGER and METHODOLOGY are TS8's; the slate goes beside the ledger.
DEFAULT_OUT_DIR = ROOT / "docs" / "superpowers" / "results"

EDGE_ORDER = ("expectancy", "harvest", "volume")

# Spec boundary 5, repeated on every slate.
HOLDOUT_REMINDER = (
    "Every autopsy-derived row is exploratory, and the holdout is protected: the "
    "live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, "
    "scripts/backtest/measure_v104.py). A row picked from this slate and sent to "
    "/prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows "
    "that end before the autopsy window starts, and its pre-registration records "
    "that the holdout is contaminated for that idea (never spent as confirmation). "
    "A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap)."
)

# Spec boundaries 1 and 2.
BOUNDARY_NOTE = (
    "A slate row is a hypothesis. No gate moves: it never edits code, config, "
    "thresholds or live alerts, and never licenses a re-run of a closed "
    "pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` "
    "row before its spec."
)


def _is_yes(text: str) -> bool:
    return text.strip().lower() == "yes"


def _is_playbook_screen(row: ScoutRow) -> bool:
    return row.playbook_id is not None and row.route.strip().startswith("/screen")


def _lower_bound(cell: dict | None) -> float | None:
    if not cell or not cell.get("ci"):
        return None
    return float(cell["ci"][0])


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _identity_reason(row: ScoutRow, seen: dict[str, str], closed: set[str],
                     ledger: dict[str, str]) -> str | None:
    """Duplicate, ledger, closed-table and edge checks: they need no cell."""
    key = normalise(row.idea)
    if key in seen:
        return f"duplicate of the {seen[key]} row with the same idea"
    if key in ledger:
        return f"matches ledger id {ledger[key]}"
    hit = closed_match(row.idea, closed)
    if hit is not None:
        return f"matches closed pre-registration {hit}"
    if row.edge.strip() not in EDGE_ORDER:
        return f"edge {row.edge.strip()!r} is not one of {', '.join(EDGE_ORDER)}"
    return None


def _cell_reason(row: ScoutRow, cells: dict[str, dict]) -> str | None:
    """Evidence checks against the autopsy JSON, the only source of figures."""
    cid = row.cell_id
    if cid is None:
        return "cites no autopsy cell and is not a playbook /screen row"
    cell = cells.get(cid)
    if cell is None:
        return f"cell {cid} is not in the autopsy JSON (invented figure)"
    if cell.get("thin"):
        return f"cell {cid} is thin (N {cell['n']}, {cell['weeks']} weeks)"
    if row.quoted_n is not None and row.quoted_n != cell["n"]:
        return f"quoted N {row.quoted_n} differs from the autopsy N {cell['n']} for {cid} (invented figure)"
    if not _is_yes(row.exploratory):
        return "autopsy evidence must be marked exploratory: yes (spec boundary 5)"
    lower = _lower_bound(cell)
    if lower is None or lower <= 0:
        return f"cell {cid} Δ lower bound {_signed(lower)} is at or below zero"
    return None


def screen_rows(rows: list[ScoutRow], *, closed: set[str], ledger: dict[str, str],
                cells: dict[str, dict]) -> tuple[list[ScoutRow], list[Drop]]:
    """Drop closed, duplicate and unsupported rows; every drop keeps its reason."""
    kept: list[ScoutRow] = []
    drops: list[Drop] = []
    seen: dict[str, str] = {}
    for row in rows:
        reason = _identity_reason(row, seen, closed, ledger)
        if reason is None and not _is_playbook_screen(row):
            reason = _cell_reason(row, cells)
        if reason is not None:
            drops.append(Drop(idea=row.idea, role=row.role, reason=reason))
            continue
        seen[normalise(row.idea)] = row.role
        kept.append(row)
    return kept, drops


def _rank_key(row: ScoutRow, cells: dict[str, dict]) -> tuple:
    cell = cells.get(row.cell_id) if row.cell_id else None
    lower = _lower_bound(cell)
    edge = row.edge.strip()
    return (
        not _is_yes(row.divergence),                       # divergence pinned first
        EDGE_ORDER.index(edge) if edge in EDGE_ORDER else len(EDGE_ORDER),
        row.manual_actions.strip().lower() != "none",      # manual action ranks down
        -lower if lower is not None else math.inf,         # higher bound first
        -(cell["n"] if cell else 0),                       # then larger N
        normalise(row.idea),                               # deterministic tie-break
    )


def rank(rows: list[ScoutRow], cells: dict[str, dict]) -> list[ScoutRow]:
    return sorted(rows, key=lambda row: _rank_key(row, cells))


def _table_text(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _header_lines(header: dict, autopsy_path: str) -> list[str]:
    window = header.get("window") or ["?", "?"]
    return [
        f"**Autopsy:** `{autopsy_path}`",
        f"**Window:** {window[0]} to {window[1]} · **N:** {header.get('n')} · "
        f"**Cells tested:** {header.get('cells_tested')} · "
        f"**Net of frictions:** {header.get('net_of_frictions')}",
    ]


def _row_block(position: int, row: ScoutRow) -> list[str]:
    pin = " — pinned: live diverges from the plan" if _is_yes(row.divergence) else ""
    lines = [f"### {position}. {row.idea} ({row.role}){pin}", ""]
    lines += [f"- {name}: {getattr(row, name)}" for name in ROW_FIELDS if name != "idea"]
    return lines + [""]


def _drop_lines(drops: list[Drop]) -> list[str]:
    if not drops:
        return ["None."]
    lines = ["| Idea | Role | Reason |", "|---|---|---|"]
    lines += [f"| {_table_text(d.idea)} | {_table_text(d.role)} | {_table_text(d.reason)} |"
              for d in drops]
    return lines


def render_slate(ranked: list[ScoutRow], drops: list[Drop], header: dict, *,
                 date: str, autopsy_path: str) -> str:
    lines = [f"# Scout slate {date}", "", *_header_lines(header, autopsy_path), "",
             f"> {HOLDOUT_REMINDER}", "", BOUNDARY_NOTE, "", "## Ranked", ""]
    if not ranked:
        lines += ["No row survived the merge.", ""]
    for position, row in enumerate(ranked, start=1):
        lines += _row_block(position, row)
    lines += ["## Dropped", "", *_drop_lines(drops)]
    return "\n".join(lines) + "\n"


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Merge scout role outputs into a ranked slate (v161).")
    ap.add_argument("role_output", type=Path, help="role outputs grouped under '## role: <name>' lines")
    ap.add_argument("--autopsy", type=Path, required=True, help="the *-book-autopsy.json of the same run")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--methodology", type=Path, default=METHODOLOGY)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = json.loads(args.autopsy.read_text(encoding="utf-8"))
    cells = {cell["id"]: cell for cell in report.get("cells", [])}
    rows, parse_drops = parse_rows(args.role_output.read_text(encoding="utf-8"))
    kept, drops = screen_rows(rows, closed=closed_names(args.methodology),
                              ledger=ledger_names(args.ledger), cells=cells)
    ranked = rank(kept, cells)
    all_drops = parse_drops + drops
    slate = render_slate(ranked, all_drops, report.get("header", {}), date=args.date,
                         autopsy_path=_display_path(args.autopsy))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.date}-scout-slate.md"
    out.write_text(slate, encoding="utf-8", newline="\n")
    print(f"scout_merge: {len(ranked)} ranked, {len(all_drops)} dropped -> {out}")
    return 0
```

and make sure the file ends with exactly one:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

If TS8's code on the branch differs from the names used here (for example `ROOT`/`LEDGER`/`METHODOLOGY` missing, `ROW_FIELDS` without `idea` first, or `normalise` keeping underscores), stop and report `BLOCKED:` to the controller: those are ledger contracts, not something to adapt silently.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_scout_merge.py`
Expected: PASS, `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py`
Expected: PASS (TS8's tests still green).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C $WT/scripts/dev/scout_merge.py`
Expected: no output (every function below C).

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/dev/scout_merge.py tests/scout/test_scout_merge.py
git -C $WT commit -m "feat(v161): scout_merge drops, pinning, ranking and slate CLI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase D: generator roles, agent, skill, docs, routing

### Task TS10: Generator role skills, playbook, shape test, AGENTS.md row

**Model:** sonnet — skill text plus a shape test, fully specified by spec § 2–3 and the index's Row format.

**Files:**
- Create: `.claude/skills/exit-harvester/SKILL.md`
- Create: `.claude/skills/setup-scout/SKILL.md`
- Create: `.claude/skills/setup-scout/references/playbook.md`
- Create: `.claude/skills/regime-desk/SKILL.md`
- Create (generated by `sync_codex.py`): `.agents/skills/exit-harvester/SKILL.md`, `.agents/skills/setup-scout/SKILL.md`, `.agents/skills/regime-desk/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (the `TIER_1_AND_3` set)
- Modify: `AGENTS.md` (one row in the `## Skills: the same ones Claude uses` table)
- Create: `tests/scout/test_generator_roles.py`

**Interfaces:**
- Consumes: the index's **Row format** and **Cell id** contracts; the cut and tally names (TS4–TS6) the checklists point at.
- Produces: skills `exit-harvester`, `setup-scout`, `regime-desk`, each with sections `## Generator lens`, `## Checklist`, `## Red flags`, `## Out of scope`, `## Row format`, `## Trigger table` in that order (first `## ` heading is `## Generator lens`, so `tests/hooks/test_role_skills.py`'s `lens_skills()` never picks them up); playbook entry ids `gap-and-hold`, `gap-fill-reversal`, `tight-base-breakout`, `rs-leader-index-pullback`, `failed-breakdown-reclaim`, `atr-reentry-after-stop`, `three-bar-weekly-reversal`. The `AGENTS.md` row names `` `trade-scout` `` and `` `scout` `` already (TS11 creates them), so TS11 adds no `AGENTS.md` text.

**Text rules (enforced by `tests/hooks/test_skill_shape.py`):** each `SKILL.md` ≤ 80 lines; no `>=`, `<=`, `>`, `<` or `=` directly before a number; no number followed by ` R` or ` pp`; `description:` a double-quoted scalar ≥ 40 characters. The q cut-off and the thin rule are named by pointer (`docs/claude/skills-tools.md` § Generator roles (v161), written by TS11), never restated. The generator roles get **no** `evals/` directory (free only) and are **not** added to `tests/hooks/test_role_skills.py`'s `ROLES`.

- [ ] **Step 1: Write the failing test**

Create `tests/scout/test_generator_roles.py`:

```python
"""Shape of the three generator role skills and the setup-scout playbook (v161 TS10).

Generators mirror the reviewer roles' file shape but open with
`## Generator lens`, so test_role_skills.py's lens_skills() never treats
them as reviewers. What is pinned is what a careless edit would remove:
the boundary sentences, the five-row cap, the Row format keys and order,
and each role's red-flag names (spec § 2)."""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

SKILLS_DIR = ROOT / ".claude" / "skills"
GENERATORS = ("exit-harvester", "setup-scout", "regime-desk")
SECTIONS = ("## Generator lens", "## Checklist", "## Red flags", "## Out of scope",
            "## Row format", "## Trigger table")
BOUNDARIES = ("never decide", "never lower a gate", "`pooled-numbers`", "`backtest-gate`",
              "at most 5 rows", "exploratory: yes", "`SCREEN-PASS`",
              "`docs/claude/skills-tools.md` § Generator roles (v161)")
ROW_KEYS = ("idea", "claim", "evidence", "exploratory", "edge", "mechanism", "order_form",
            "manual_actions", "pairs_with", "divergence", "route")
RED_FLAGS = {
    "exit-harvester": ("v129", "arm Z", "arm B", "v139", "`DATA_DRIVEN_STOPS_ENABLED`",
                       "tighter or wider", "fixed 2% risk", "R-unit inflation", "`manual_actions`"),
    "setup-scout": ("`high52w`", "`gap_volume`", "`turn_of_month`", "v122", "v127", "v128",
                    "v131", "v135", "v143", "v36", "v49", "v68"),
    "regime-desk": ("`REGIME_ALLOW`", "v17 P2a", "`EARNINGS_BLACKOUT_SESSIONS`", "v82",
                    "point-in-time", "`pairs_with`"),
}
PLAYBOOK = SKILLS_DIR / "setup-scout" / "references" / "playbook.md"
PLAYBOOK_IDS = ("gap-and-hold", "gap-fill-reversal", "tight-base-breakout",
                "rs-leader-index-pullback", "failed-breakdown-reclaim",
                "atr-reentry-after-stop", "three-bar-weekly-reversal")
AGENTS_MD = ROOT / "AGENTS.md"
CODEX_CAP_BYTES = 32 * 1024


def _text(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(name):
    return parse_frontmatter(_text(SKILLS_DIR / name / "SKILL.md"))[1]


def _section(body, heading):
    start = body.index(heading + "\n") + len(heading)
    end = body.find("\n## ", start)
    return body[start:] if end == -1 else body[start:end]


@pytest.mark.parametrize("name", GENERATORS)
def test_frontmatter_names_the_skill(name):
    meta, _ = parse_frontmatter(_text(SKILLS_DIR / name / "SKILL.md"))
    assert meta["name"] == name
    assert len(meta["description"]) >= 40


@pytest.mark.parametrize("name", GENERATORS)
def test_sections_in_order_and_generator_lens_first(name):
    body = _body(name)
    positions = [body.find(h + "\n") for h in SECTIONS]
    assert -1 not in positions, dict(zip(SECTIONS, positions))
    assert positions == sorted(positions)
    assert re.search(r"^## .*$", body, re.M).group(0) == "## Generator lens"
    assert "\n## Lens\n" not in body          # never a reviewer role


@pytest.mark.parametrize("name", GENERATORS)
def test_boundary_sentences(name):
    body = _body(name)
    missing = [b for b in BOUNDARIES if b not in body]
    assert not missing, missing


@pytest.mark.parametrize("name", GENERATORS)
def test_row_format_lists_every_key_in_order(name):
    block = _section(_body(name), "## Row format")
    positions = [block.find(f"  {key}: ") if key != "idea" else block.find("- idea: ") for key in ROW_KEYS]
    assert -1 not in positions, dict(zip(ROW_KEYS, positions))
    assert positions == sorted(positions)
    assert "NO ROWS" in block


@pytest.mark.parametrize("name", GENERATORS)
def test_red_flags_name_the_closed_rows(name):
    flags = _section(_body(name), "## Red flags")
    missing = [f for f in RED_FLAGS[name] if f not in flags]
    assert not missing, missing


def test_setup_scout_cites_its_playbook_by_repo_path():
    assert "`.claude/skills/setup-scout/references/playbook.md`" in _body("setup-scout")


def test_playbook_has_every_seed_entry_with_an_order_form():
    text = _text(PLAYBOOK)
    for entry in PLAYBOOK_IDS:
        assert f"## `{entry}`" in text, entry
    for part in text.split("\n## `")[1:]:
        for field in ("Rule:", "Horizon:", "Order form:", "Failure mode:", "Must not duplicate:"):
            assert f"**{field}**" in part, (part.splitlines()[0], field)


@pytest.mark.parametrize("name", GENERATORS)
def test_codex_copy_exists(name):
    assert (ROOT / ".agents" / "skills" / name / "SKILL.md").is_file()


def test_agents_md_names_the_scout_tooling_and_stays_under_the_codex_cap():
    text = _text(AGENTS_MD)
    for name in ("trade-scout", "exit-harvester", "setup-scout", "regime-desk", "scout"):
        assert f"`{name}`" in text, name
    assert len(AGENTS_MD.read_bytes()) < CODEX_CAP_BYTES
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_generator_roles.py`
Expected: FAIL — `FileNotFoundError` on `.claude/skills/exit-harvester/SKILL.md`.

- [ ] **Step 3: Write `.claude/skills/exit-harvester/SKILL.md`**

````markdown
---
name: exit-harvester
description: "Generator role: proposes exit and stop hypotheses (give-back, near-TP closes, near-stop reversals, gap-through-stop, holding time) from a book autopsy. Run by the scout agent for /trade-scout."
---

# Exit harvester

You are one generator seat. You propose hypotheses; you never decide, and you
never lower a gate (`docs/claude/persona.md`). No row overrides the
`backtest-gate` skill, the `pooled-numbers` skill or a closed pre-registration
(`docs/claude/backtest-methodology.md` § Closed pre-registrations — do not
re-run these). Quote only figures printed in the autopsy Markdown you were
given, with its window and N. The evidence rule (q cut-off, thin cells) lives
in `docs/claude/skills-tools.md` § Generator roles (v161). Emit at most 5 rows;
every row built on autopsy evidence carries `exploratory: yes`, and any entry
or filter idea still needs a `SCREEN-PASS` row before a spec.

## Generator lens

Money the book earned and gave back, or never took: how trades leave, not how
they enter. A row changes an exit, a trail or a stop, or names where an exit
already measured leaves R on the table.

## Checklist

- Give-back (`mfe_r` minus realised R) across all trades in the autopsy, never winners only; check trail or scale-out headroom against `scripts/reports/runner_headroom.py` before claiming it.
- `exit_reason` and `near_tp_close` cells: the near-TP stall and timeout closes `check_near_tp_timeout` writes (`swingbot/core/tracking/performance.py`).
- `near_stop_reversal` cells beside the trades a wider stop would still have lost; read both, never the reversals alone.
- `gap_through_stop` cells: losses beyond the stop and the gap behind them.
- `holding_bucket` cells: holding time against R per horizon.
- The stop extras on every stop cell: stop distance in ATR and dollar loss at fixed 2% risk.
- Bar-covered N beside total N on every bar-reading cell; a thinly covered cell says so in its claim.
- `order_form` says how the exit rests as an order; `manual_actions` names any mid-trade step and the alert message that carries it.
- An exit idea an existing results doc already measures routes to `harvest-headroom <results path>`.

## Red flags

- v129 acceptance-failure exits (arm Z, arm B), the v139 confluence structural stop or stop drop, `DATA_DRIVEN_STOPS_ENABLED`, `ADAPTIVE_RUNNER_TRAIL_ENABLED`, `STALL_EXIT_ENABLED`, `RUNNER_STRUCTURE_EXIT`: closed, never re-proposed under a new name.
- Any stop change, tighter or wider, without the dollar view at fixed 2% risk (R-unit inflation).
- A trail or breakeven move that needs `manual_actions` with no alert message to carry it.
- A figure not printed in the autopsy Markdown, or a thin cell offered as evidence.

## Out of scope

- New entries, fills and setups: `setup-scout`.
- When to trade or stand aside: `regime-desk`.
- Whether a row's statistics hold: `quant-researcher` on the slate.
- Portfolio heat and sizing: `risk-manager`.

## Row format

One block per row, keys in this order, two-space indent. Nothing fits: return
`NO ROWS: <one line why>`.

```
- idea: <kebab-case name, unique>
  claim: <one sentence: what change, what effect>
  evidence: cell <cell id>; N <n>; weeks <w>; Δ net ExpR <d> [<lo>, <hi>]; q <q>
  exploratory: yes
  edge: expectancy | harvest | volume
  mechanism: <why a trader expects it to pay, one or two sentences>
  order_form: <stop-buy / limit / market-on-open, validity>
  manual_actions: none | <mid-trade action and the alert that carries it>
  pairs_with: <where volume or R comes back> | n/a
  divergence: no | yes
  route: /prereg | harvest-headroom <results path>
```

## Trigger table

Should fire: /trade-scout dispatching the scout agent with role=exit-harvester.
Should fire: asking which exits in the latest book autopsy give back the most.
Should fire: proposing a trail or scale-out hypothesis from autopsy give-back cells.
Should not fire: reviewing a spec's stop change for portfolio heat.
Should not fire: running a backtest of an existing exit model.
Should not fire: proposing a new entry setup from the playbook.
````

- [ ] **Step 4: Write `.claude/skills/setup-scout/SKILL.md`**

````markdown
---
name: setup-scout
description: "Generator role: proposes entry, fill and setup hypotheses from a book autopsy and the setup playbook (order form, liquidity, rejected plans, missing setups). Run by the scout agent for /trade-scout."
---

# Setup scout

You are one generator seat. You propose hypotheses; you never decide, and you
never lower a gate (`docs/claude/persona.md`). No row overrides the
`backtest-gate` skill, the `pooled-numbers` skill or a closed pre-registration
(`docs/claude/backtest-methodology.md` § Closed pre-registrations — do not
re-run these). Quote only figures printed in the autopsy Markdown you were
given, with its window and N. The evidence rule (q cut-off, thin cells) lives
in `docs/claude/skills-tools.md` § Generator roles (v161). Emit at most 5 rows;
every row built on autopsy evidence carries `exploratory: yes`, and any entry
or filter idea still needs a `SCREEN-PASS` row before a spec.

## Generator lens

Entries the bot does not take, or takes badly: fill reality, order form,
liquidity, rejected plans, and trader setups missing from the strategy
registry. Read `.claude/skills/setup-scout/references/playbook.md` too.

## Checklist

- Cells whose Δ interval excludes zero, inside the q cut-off and not thin.
- `strategy_horizon`, `direction`, `ticker`, `sector_today` cells: a strong cell carried by a few names says so (`extra.tickers`, `extra.top_ticker_share`).
- Fill reality: `fill_status` tallies (filled, expired unfilled, never touched) and `open_gap_bucket`, `gapped_through_entry` cells decide the entry order form and validity.
- `dollar_volume_bucket` and `atr_pct_bucket` cells: is a strong cell a handful of thin names?
- `rejection_reason` tallies: a reason that blocks plans is a volume lever, to be measured in shadow, never assumed.
- Playbook setups absent from `swingbot/core/market/strategy_types.py`: such a row cites `playbook <entry id>` and routes to `/screen <idea>`.
- Variants of the one `SCREEN-PASS` (`screen-uptrend_pullback`) only as a new mechanism, never a new threshold.
- `sector_today` is today's map, not point-in-time: describe concentration, never filter on it.
- Any tightening names in `pairs_with` where the volume comes back.

## Red flags

- A SCREEN-FAIL idea under a new name: `high52w`, `gap_volume`, `turn_of_month`.
- v122 volume dry-up gate, v127 structure-break armed entries, v128 FVG level modes, v131 Fibonacci limit, v135 headroom veto, v143 FVG-bullish features, v36 touch strength, v49 effective confluence, v68 dead-cat-bounce veto.
- A 52-week-high or 20-EMA-pullback variant: too close to `screen-high52w` and `screen-uptrend_pullback`.
- A filter whose only effect is to cut N, with no `pairs_with`.
- A figure not printed in the autopsy Markdown, or a thin cell offered as evidence.

## Out of scope

- Exits, trails and stops: `exit-harvester`.
- Regime, calendar and event timing: `regime-desk`.
- Post-earnings drift and catalysts (point-in-time estimates): `fundamental-analyst`.
- Whether a row's statistics hold: `quant-researcher` on the slate.

## Row format

One block per row, keys in this order, two-space indent. Nothing fits: return
`NO ROWS: <one line why>`.

```
- idea: <kebab-case name, unique>
  claim: <one sentence: what change, what effect>
  evidence: cell <cell id>; N <n>; weeks <w>; Δ net ExpR <d> [<lo>, <hi>]; q <q>   |   playbook <entry id>
  exploratory: yes
  edge: expectancy | harvest | volume
  mechanism: <why a trader expects it to pay, one or two sentences>
  order_form: <stop-buy / limit / market-on-open, validity>
  manual_actions: none | <mid-trade action and the alert that carries it>
  pairs_with: <where volume or R comes back> | n/a
  divergence: no | yes
  route: /screen <idea> | /prereg
```

## Trigger table

Should fire: /trade-scout dispatching the scout agent with role=setup-scout.
Should fire: asking which entries in the latest book autopsy fill badly or gap through the limit.
Should fire: proposing a playbook setup the strategy registry does not have.
Should not fire: running an idea screen that is already defined.
Should not fire: reviewing an entry-signal diff for lookahead.
Should not fire: proposing a trail or stop change from give-back cells.
````

- [ ] **Step 5: Write `.claude/skills/setup-scout/references/playbook.md`**

````markdown
# Setup playbook (setup-scout)

Curated trader setups for `setup-scout` (spec v161 § 3). Each entry is a
**candidate for `/screen`**, never a strategy: it routes to `/screen <idea>`
and cites `playbook <entry id>` as its evidence. Seeds avoid every closed row
in `docs/claude/backtest-methodology.md` § Closed pre-registrations — do not
re-run these and the one `SCREEN-PASS` (`screen-uptrend_pullback`). The
partner may edit, add or retire entries; an entry that reaches the ledger
names its ledger id here.

Left out on purpose: post-earnings drift (needs point-in-time estimates and a
`fundamental-analyst` review); 52-week-high and 20-EMA-pullback variants (too
close to `screen-high52w` and `screen-uptrend_pullback`).

## `gap-and-hold`

- **Rule:** the stock gaps up above the prior session's high and closes in the upper part of the day's range without filling the gap.
- **Horizon:** 1w to 2w swing.
- **Order form:** next-session stop-buy a tick above the gap day's high, valid one session; stop under the gap day's low.
- **Failure mode:** the gap fills on day two; a stop-buy that triggers into an opening fade.
- **Must not duplicate:** `screen-gap_volume` (SCREEN-FAIL: entry on the gap day itself, volume filter).

## `gap-fill-reversal`

- **Rule:** a gap away from a prior support or resistance level fills back into that level and the level holds on a closing basis.
- **Horizon:** 1w swing.
- **Order form:** limit at the level, valid one session; stop beyond the level by an ATR fraction fixed in the idea's screen definition.
- **Failure mode:** the level breaks on the fill; a limit filled on a trend day.
- **Must not duplicate:** `screen-gap_volume`; the confluence S/R levels already traded by the bot (a level the bot alerts on is not a new idea).

## `tight-base-breakout`

- **Rule:** a narrow multi-week range (contracting daily ranges) breaks out on above-average volume.
- **Horizon:** 2w to 1m swing.
- **Order form:** stop-buy above the base high, valid until cancelled for a fixed number of sessions; stop under the base low.
- **Failure mode:** a false breakout that closes back inside the base; a base too wide for the stop at the 2% dollar-risk cap.
- **Must not duplicate:** v122 pullback volume dry-up gate; `screen-high52w`.

## `rs-leader-index-pullback`

- **Rule:** a stock in the top relative-strength group holds above its own prior low on a day the index pulls back.
- **Horizon:** 2w to 1m swing.
- **Order form:** next-session stop-buy above the pullback day's high, valid one session.
- **Failure mode:** the index pullback becomes a regime change; leaders roll over last, then hard.
- **Must not duplicate:** `RS_GATE` (v34, shipped as a gate); `screen-uptrend_pullback` (own-RSI pullback, not index-relative).

## `failed-breakdown-reclaim`

- **Rule:** price breaks below a prior swing low, then closes back above it within a few sessions.
- **Horizon:** 1w to 2w swing.
- **Order form:** stop-buy above the reclaim bar's high, valid one session; stop under the failed-breakdown low.
- **Failure mode:** the reclaim fails and the breakdown resumes; thin names whipsaw through the stop.
- **Must not duplicate:** v127 structure-break armed entries; v88/v90 armed confluence entries.

## `atr-reentry-after-stop`

- **Rule:** after a stop-out, the original setup re-arms (price back through the entry trigger) within a small fixed number of bars.
- **Horizon:** the original plan's horizon.
- **Order form:** stop-buy at the original trigger, valid for the re-arm window; stop re-placed at the original ATR multiple.
- **Failure mode:** re-entering a broken setup twice; stacking losses in one name.
- **Must not duplicate:** v108 E EMA Crossover re-arm (first K pullback touches).

## `three-bar-weekly-reversal`

- **Rule:** a three-bar reversal pattern on daily bars at a level drawn from weekly bars.
- **Horizon:** 2w to 1m swing.
- **Order form:** stop-buy above the third bar's high, valid one session; stop under the pattern low.
- **Failure mode:** the weekly level is stale; the pattern prints mid-range, away from any level.
- **Must not duplicate:** `Double Pattern` (v69); the v124 Fibonacci confirmation trigger.
````

- [ ] **Step 6: Write `.claude/skills/regime-desk/SKILL.md`**

````markdown
---
name: regime-desk
description: "Generator role: proposes when-to-trade hypotheses (regime, weekday, weekend hold, OPEX, FOMC, earnings proximity, alert timing) from a book autopsy. Run by the scout agent for /trade-scout."
---

# Regime desk

You are one generator seat. You propose hypotheses; you never decide, and you
never lower a gate (`docs/claude/persona.md`). No row overrides the
`backtest-gate` skill, the `pooled-numbers` skill or a closed pre-registration
(`docs/claude/backtest-methodology.md` § Closed pre-registrations — do not
re-run these). Quote only figures printed in the autopsy Markdown you were
given, with its window and N. The evidence rule (q cut-off, thin cells) lives
in `docs/claude/skills-tools.md` § Generator roles (v161). Emit at most 5 rows;
every row built on autopsy evidence carries `exploratory: yes`, and any entry
or filter idea still needs a `SCREEN-PASS` row before a spec.

## Generator lens

When to trade or stand aside: the regime, calendar and event context of an
entry, alert timing against the session, and same-day clustering of losers.

## Checklist

- `regime` cells: `regime2_state` frozen at issuance (`swingbot/core/edge/regime2.py`, `swingbot/core/market/market_context.py`).
- `weekday`, `friday_entry` and `weekend_hold` cells.
- `opex_week` (`swingbot/core/market/opex.py`) and `fomc_proximity` (`market_events.FOMC_DECISION_DATES`) cells; read the coverage note.
- `earnings_proximity` cells: `days_to_earnings` is often missing, so read the covered N.
- `session_bucket` and `alert_hour` cells, and the `alerts_per_day`, `alert_hour_session` and `actionable_before_open` tallies: can a trader who is not watching rest the order before the open?
- Same-day losers clustered by sector (`swingbot/core/edge/correlation.py`), described from `sector_today` and labelled not point-in-time.
- Every stand-aside row names in `pairs_with` where the volume comes back; a tightening is paired with a widening.

## Red flags

- The `REGIME_ALLOW` gate (v17 P2a: no cell cleared the rule).
- `EARNINGS_BLACKOUT_SESSIONS` (v82: near-earnings trades scored better).
- Any regime variable that is not point-in-time, including `sector_today` as a filter argument.
- A stand-aside filter whose only effect is to cut N, with no `pairs_with`.
- CPI or NFP proximity: the autopsy carries no past dates for them.
- A figure not printed in the autopsy Markdown, or a thin cell offered as evidence.

## Out of scope

- Exits, trails and stops: `exit-harvester`.
- Entry setups and fills: `setup-scout`.
- Earnings and macro catalysts as fundamentals: `fundamental-analyst`.
- Whether a row's statistics hold: `quant-researcher` on the slate.

## Row format

One block per row, keys in this order, two-space indent. Nothing fits: return
`NO ROWS: <one line why>`.

```
- idea: <kebab-case name, unique>
  claim: <one sentence: what change, what effect>
  evidence: cell <cell id>; N <n>; weeks <w>; Δ net ExpR <d> [<lo>, <hi>]; q <q>
  exploratory: yes
  edge: expectancy | harvest | volume
  mechanism: <why a trader expects it to pay, one or two sentences>
  order_form: <stop-buy / limit / market-on-open, validity>
  manual_actions: none | <mid-trade action and the alert that carries it>
  pairs_with: <where volume or R comes back> | n/a
  divergence: no | yes
  route: /screen <idea> | /prereg
```

## Trigger table

Should fire: /trade-scout dispatching the scout agent with role=regime-desk.
Should fire: asking whether the latest book autopsy shows a weekday or OPEX-week effect.
Should fire: proposing a stand-aside or timing hypothesis from autopsy regime cells.
Should not fire: changing `regime2.py` feature code.
Should not fire: reviewing a spec for earnings catalysts.
Should not fire: proposing an exit change from give-back cells.
````

- [ ] **Step 7: Register the three skills and add the `AGENTS.md` row**

In `tests/hooks/test_skill_shape.py`, extend the `TIER_1_AND_3` set literal with the three names (keep the trailing comment):

```python
TIER_1_AND_3 = {"backtest-gate", "no-lookahead", "pooled-numbers", "mirror-prod", "edge-module", "alert-surface", "schema-change", "worktree-lifecycle",
                "quant-researcher", "risk-manager", "financial-advisor",
                "veteran-trader", "technical-analyst", "fundamental-analyst",
                "staff-engineer", "quant-engineer", "senior-engineer",
                "exit-harvester", "setup-scout", "regime-desk"}   # each skill task appends its own name
```

In `AGENTS.md`, in the `## Skills: the same ones Claude uses` table, insert this row directly after the `` `worktree-lifecycle` `` row (before the `etoro-public-api-operations` row):

```markdown
| Mining the live book for ranked hypotheses: `trade-scout` dispatches the read-only `scout` agent once per generator role (`exit-harvester`, `setup-scout`, `regime-desk`) | `trade-scout` |
```

- [ ] **Step 8: Regenerate the Codex mirror**

Run: `python $WT/scripts/dev/sync_codex.py`
Expected: writes `.agents/skills/exit-harvester/SKILL.md`, `.agents/skills/setup-scout/SKILL.md`, `.agents/skills/regime-desk/SKILL.md`. Then `python $WT/scripts/dev/sync_codex.py --check` prints nothing problematic. (`sync_codex` copies only `SKILL.md`; the playbook stays under `.claude/` and `setup-scout` cites it by repo path.)

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_generator_roles.py`
Expected: PASS.
Run: `python $WT/scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS (line budget, no thresholds, trigger tables, tier registration).
Run: `python $WT/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS.
Run: `python $WT/scripts/dev/testrun.py file tests/hooks/test_role_skills.py`
Expected: PASS (`lens_skills()` still equals the nine reviewer roles).

If `test_skill_shape` flags a threshold, reword the line (for example "inside the q cut-off" instead of a number); never move a number into the skill.

- [ ] **Step 10: Commit**

```bash
git -C $WT add .claude/skills/exit-harvester/SKILL.md .claude/skills/setup-scout/SKILL.md .claude/skills/setup-scout/references/playbook.md .claude/skills/regime-desk/SKILL.md .agents/skills/exit-harvester/SKILL.md .agents/skills/setup-scout/SKILL.md .agents/skills/regime-desk/SKILL.md tests/hooks/test_skill_shape.py tests/scout/test_generator_roles.py AGENTS.md
git -C $WT commit -m "feat(v161): exit-harvester, setup-scout and regime-desk generator roles with playbook

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

