# v156 Trade autopsy: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief V156-2` or `grep -n "^### Task V156-2" -A 200 <this file>`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-10-v156-review-ritual-skills-design.md`](../specs/2026-10-10-v156-review-ritual-skills-design.md)
**Brief:** `.superpowers/briefs/2026-10-10-v156-trade-autopsy.md` (line numbers from `claude/adoring-cori-u9l0th` @ `4d4f1955`)

**Goal:** Ship `/trade-autopsy <trade id>`, a slash-only forked skill that prints one closed trade in the spec's fixed seven-line shape (measurements, never a verdict), and a look-record writer that appends one row per review to `docs/superpowers/results/looks.jsonl`.

**Architecture:** The trade, plan and journal rows live in Postgres on the Hetzner VM only, so the skill (forked, `model: sonnet`) reads them with a read-only stdin script through `scripts/ops/ssh-hetzner.sh` and keeps raw rows and bars out of the main context. The look writer is a stdlib CLI, `scripts/reports/look_record.py`, that mirrors `scripts/reports/preregistration_ledger.py` and `stats.append_ledger_row` (validate, then append one LF line, never edit). No module under `swingbot/` changes.

**Tech Stack:** Python 3.11 stdlib, pytest, Claude Code skill frontmatter, `scripts/dev/sync_codex.py` for the Codex mirror.

## Global Constraints

- **No shipped code changes.** Nothing under `swingbot/`, `bot.py`, `admin_ui.py` or `frontend/` is touched; `VERSION.json` is not bumped (`Bump: none`). `mfe_mae.py` and `journal.py` are read, never edited (spec § Out of scope).
- **Measurements, never a verdict.** The skill text contains no "stop too tight", "bad setup" or similar judgement, no interval and no significance figure.
- **Excluded fields stay excluded:** the journal's `auto_lesson` and `tags`, anything after the exit, any interval or significance figure. The skill names them as excluded; a test pins that.
- **The fixed closing line is exactly** `Descriptive only, N=1. A pattern seen here is a hypothesis for `/screen` or `/prereg`, not a result.` with `N=1` unspaced (`N = 1` trips `_THRESHOLD_RE` in `tests/hooks/test_skill_shape.py`).
- **The skill is a new skill, not grandfathered:** at most 80 lines (`MAX_SKILL_LINES`), no token matching `_THRESHOLD_RE` in its body (no `=`, `<`, `>`, `<=`, `>=` directly before a digit; no `<digits> R`, `<digits> pp`), registered in `TIER_2` and `FORKED` (`"sonnet"`), carries `disable-model-invocation: true`, `context: fork`, `model: sonnet`.
- **Description is strictly valid YAML as a plain scalar:** no `: `, no ` #`, does not start with a YAML indicator character. v154's strict parser (not yet on disk) will read it.
- **Production is read-only and reached only through `scripts/ops/ssh-hetzner.sh`.** No raw `ssh`/`scp`, no restart, no write. The wrapper is gitignored and absent from cloud checkouts; a task that needs it and does not find it stops with `BLOCKED`, it never substitutes another route.
- **No lookahead in the context line:** dollar volume and the earnings check use bars and reports dated strictly before the alert session (`opened_at`), never `df.tail` of the unsliced cache.
- **A field the data cannot supply prints `not recorded`.** No read-time inference (`docs/claude/schema-evolution.md`).
- **`looks.jsonl` is append-only**; a second look at the same trade is a second row. The first real row is written by V156-3.
- **Codex mirror ships in the same commit as the skill:** `python scripts/dev/sync_codex.py`, the regenerated `.agents/skills/trade-autopsy/**`, and the `` `trade-autopsy` `` mention in `AGENTS.md`'s explicit-only rituals paragraph.
- Every Python function written ends below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>`; radon may need `pip install radon` first).
- Per-task verification is the narrow run: `python scripts/dev/testrun.py file <test>`. The full suite runs once, in V156-4. Green means `0 failed` and `0 xfailed`.
- **Do not commit from a part writer**; the controller commits each task on the implementation branch.

## Decisions fixed by this plan

These fill gaps the spec leaves to the plan.

1. **Task id prefix `V156-`**, four tasks, one file (about 700 lines, under the 1300-line single-file mark).
2. **Writer path and name:** `scripts/reports/look_record.py`, test `tests/scripts/test_look_record_cli.py` — the sibling of `scripts/reports/preregistration_ledger.py` and its test, writing next to `preregistration-ledger.jsonl`. The validation and append logic live in the script itself (stdlib only), not in `swingbot/`, so `Bump: none` holds.
3. **Look row fields, in this order:** `skill` (non-empty text), `date` (ISO date of the look, default today), `trade_id` (non-empty text), `close_date` (ISO date the trade closed). No duplicate refusal: every run is a look.
4. **CLI:** `python scripts/reports/look_record.py --skill <name> --trade-id <id> --close-date YYYY-MM-DD [--date YYYY-MM-DD] [--looks PATH]`; exit 0 and the row printed as one JSON line; exit 2 and `refused: <reason>` on stderr for an invalid row or a corrupt existing file, writing nothing.
5. **When a look is recorded:** only after the seven lines printed for a closed trade. A missing trade, an open trade, or an unreachable production writes no row.
6. **Earnings source:** production's `market_data/earnings/<T>.csv` through `CsvSource` only; no CSV for the ticker prints `not recorded`. `LiveSource` (recent reports only, network) and `risk_features["days_to_earnings"]` (never populated) are not used.
7. **The manual run (V156-3) is typed by the partner** as `/trade-autopsy <id>` on the operator machine (the skill is slash-only, so no agent can invoke it, and the wrapper exists only there). The controller picks the trade id with one read-only query and records the output under `## Results`.

## Parallelisation

A chain, implemented in one worktree in id order. No task runs in parallel with another.

- **V156-1 → V156-2:** the skill's Step 3 cites the writer's path and CLI flags (Decision 4); it is written against the landed CLI so the text and the parser cannot drift.
- **V156-2 → V156-3:** the manual run exercises the committed skill and the writer, and appends the first row to `looks.jsonl`.
- **V156-3 → V156-4:** the full suite and the panel review the plan as finally landed, including the results section.

## Task ledger

| Id | Title | Model | Files created / modified | Creates for later tasks |
|---|---|---|---|---|
| V156-1 | Look-record writer and its test | sonnet | Create `scripts/reports/look_record.py`, `tests/scripts/test_look_record_cli.py` | `LOOKS_PATH`, `LOOK_FIELDS = ("skill", "date", "trade_id", "close_date")`, `validate_look(row) -> None`, `load_looks(path=LOOKS_PATH) -> list`, `append_look(row, path=LOOKS_PATH) -> dict`, `main(argv=None) -> int` with the CLI of Decision 4 |
| V156-2 | `/trade-autopsy` skill, shape tests, Codex mirror | sonnet | Create `.claude/skills/trade-autopsy/SKILL.md`; modify `tests/hooks/test_skill_shape.py`, `AGENTS.md`, `docs/claude/skills-tools.md`; generated `.agents/skills/trade-autopsy/SKILL.md`, `.agents/skills/trade-autopsy/agents/openai.yaml` | `TRADE_AUTOPSY_CLOSING_LINE` in `test_skill_shape.py`; the skill's seven-line output shape for V156-3 |
| V156-3 | Manual run against one real closed trade, recorded | sonnet | Modify this plan (`## Results`); create `docs/superpowers/results/looks.jsonl` (first row, written by the writer) | The first `looks.jsonl` row |
| V156-4 | Full suite, then `/panel quant-researcher,veteran-trader` before close-out | haiku | Modify this plan (`## Results`) | Green suite and merged panel findings for `/close-out` |

## Results

Filled in by V156-3 (manual run) and V156-4 (suite and panel).

# Phase 1 — Writer, skill, verification

### Task V156-1: Look-record writer and its test

**Model:** sonnet — a normal TDD task inside one script, behaviour fixed by the spec and Decisions 2–4.

**Files:**
- Create: `scripts/reports/look_record.py`
- Create: `tests/scripts/test_look_record_cli.py`

Mirrors `scripts/reports/preregistration_ledger.py` (argparse `build_parser()`, `main(argv=None) -> int`, refusal on stderr with exit 2) and `swingbot/core/backtesting/instrument/stats.py:append_ledger_row` (validate, prepend `"\n"` when the file lacks a trailing newline, open with `"a"`, `encoding="utf-8"`, `newline="\n"`, write `json.dumps(ordered, ensure_ascii=False) + "\n"`). Unlike the ledger there is no duplicate-id refusal: every run is a look.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_look_record_cli.py`:

```python
"""v156: every /trade-autopsy run appends one look to looks.jsonl."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import look_record as cli  # noqa: E402


def _args(looks, **over):
    base = {"--skill": "trade-autopsy", "--trade-id": "3f9c0a1b2d4e5f60",
            "--close-date": "2026-10-08", "--date": "2026-10-10",
            "--looks": str(looks)}
    base.update(over)
    return [part for pair in base.items() for part in pair]


_OLD = ('{"skill": "trade-autopsy", "date": "2026-10-01", '
        '"trade_id": "aaaaaaaaaaaaaaaa", "close_date": "2026-09-30"}\n')


def test_one_line_is_appended_and_existing_lines_are_untouched(tmp_path):
    looks = tmp_path / "looks.jsonl"
    looks.write_text(_OLD, encoding="utf-8", newline="\n")
    before = looks.read_bytes()
    assert cli.main(_args(looks)) == 0
    after = looks.read_bytes()
    assert after.startswith(before)
    added = after[len(before):].decode("utf-8")
    assert added.endswith("\n") and added.count("\n") == 1
    assert json.loads(added) == {"skill": "trade-autopsy", "date": "2026-10-10",
                                 "trade_id": "3f9c0a1b2d4e5f60",
                                 "close_date": "2026-10-08"}


def test_fields_are_written_in_the_fixed_order(tmp_path):
    looks = tmp_path / "looks.jsonl"
    assert cli.main(_args(looks)) == 0
    row = json.loads(looks.read_text(encoding="utf-8"))
    assert tuple(row) == cli.LOOK_FIELDS == ("skill", "date", "trade_id", "close_date")


def test_an_absent_file_is_created_with_one_row(tmp_path):
    looks = tmp_path / "looks.jsonl"
    assert cli.main(_args(looks)) == 0
    assert len(cli.load_looks(looks)) == 1


def test_a_file_without_a_trailing_newline_gets_one_first(tmp_path):
    looks = tmp_path / "looks.jsonl"
    looks.write_text(_OLD.rstrip("\n"), encoding="utf-8", newline="\n")
    assert cli.main(_args(looks)) == 0
    rows = cli.load_looks(looks)
    assert [r["trade_id"] for r in rows] == ["aaaaaaaaaaaaaaaa", "3f9c0a1b2d4e5f60"]


def test_a_second_look_at_the_same_trade_is_a_second_row(tmp_path):
    looks = tmp_path / "looks.jsonl"
    assert cli.main(_args(looks)) == 0
    assert cli.main(_args(looks)) == 0
    assert len(cli.load_looks(looks)) == 2


def test_the_look_date_defaults_to_today(tmp_path):
    looks = tmp_path / "looks.jsonl"
    args = _args(looks)
    i = args.index("--date")
    del args[i:i + 2]
    assert cli.main(args) == 0
    assert cli.load_looks(looks)[0]["date"] == date.today().isoformat()


def test_the_cli_prints_the_row_it_wrote(tmp_path, capsys):
    looks = tmp_path / "looks.jsonl"
    assert cli.main(_args(looks)) == 0
    assert json.loads(capsys.readouterr().out) == cli.load_looks(looks)[0]


@pytest.mark.parametrize("flag,value", [("--close-date", "2026-13-01"),
                                        ("--close-date", "08/10/2026"),
                                        ("--date", "yesterday"),
                                        ("--trade-id", "  "),
                                        ("--skill", "")])
def test_an_invalid_row_is_refused_and_nothing_is_written(tmp_path, capsys, flag, value):
    looks = tmp_path / "looks.jsonl"
    looks.write_text(_OLD, encoding="utf-8", newline="\n")
    before = looks.read_bytes()
    assert cli.main(_args(looks, **{flag: value})) == 2
    assert looks.read_bytes() == before
    assert capsys.readouterr().err.startswith("refused: ")


def test_a_corrupt_existing_file_is_refused_and_left_alone(tmp_path, capsys):
    looks = tmp_path / "looks.jsonl"
    looks.write_text(_OLD + "not json\n", encoding="utf-8", newline="\n")
    before = looks.read_bytes()
    assert cli.main(_args(looks)) == 2
    assert looks.read_bytes() == before
    assert "looks line 2" in capsys.readouterr().err


def test_a_row_with_an_extra_field_is_refused():
    row = {"skill": "trade-autopsy", "date": "2026-10-10",
           "trade_id": "x", "close_date": "2026-10-08", "verdict": "bad"}
    with pytest.raises(ValueError, match="extra"):
        cli.validate_look(row)


def test_the_default_path_is_next_to_the_preregistration_ledger():
    assert cli.LOOKS_PATH == ROOT / "docs" / "superpowers" / "results" / "looks.jsonl"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_look_record_cli.py`
Expected: FAIL — collection error, `ModuleNotFoundError: No module named 'look_record'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/look_record.py`:

```python
#!/usr/bin/env python3
"""Append one look at live outcome data to docs/superpowers/results/looks.jsonl.

v156: a review of a closed live trade is a look at the holdout. Each run of a
review skill (today only /trade-autopsy) appends one row -- the skill, the
date of the look, the trade id and the trade's close date -- so a later
pre-registration can list the looks that fell inside its window. The file is
append-only: a row is never edited or removed, and a second look at the same
trade is a second row. Commit it with whatever change follows the review.

    python scripts/reports/look_record.py --skill trade-autopsy \
        --trade-id 3f9c0a1b2d4e5f60 --close-date 2026-10-08
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOOKS_PATH = ROOT / "docs" / "superpowers" / "results" / "looks.jsonl"
LOOK_FIELDS = ("skill", "date", "trade_id", "close_date")


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _iso_date(value) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


_FIELD_CHECKS = {"skill": _text, "date": _iso_date,
                 "trade_id": _text, "close_date": _iso_date}


def validate_look(row) -> None:
    """Raise ValueError unless ``row`` has exactly LOOK_FIELDS, each valid."""
    if not isinstance(row, dict):
        raise ValueError("a look row must be a JSON object")
    missing = sorted(set(LOOK_FIELDS) - set(row))
    extra = sorted(set(row) - set(LOOK_FIELDS))
    if missing or extra:
        raise ValueError(f"look row: missing {missing}, extra {extra}")
    bad = [name for name in LOOK_FIELDS if not _FIELD_CHECKS[name](row[name])]
    if bad:
        raise ValueError(f"look row: invalid field(s) {bad}")


def _parse_line(text: str, lineno: int) -> dict:
    try:
        row = json.loads(text)
        validate_look(row)
    except ValueError as exc:   # json.JSONDecodeError is a ValueError
        raise ValueError(f"looks line {lineno}: {exc}") from exc
    return row


def load_looks(path=LOOKS_PATH) -> list:
    """Every row, validated, in file order. An absent file holds no looks."""
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").split("\n")
    return [_parse_line(line, n) for n, line in enumerate(lines, start=1)
            if line.strip()]


def append_look(row: dict, path=LOOKS_PATH) -> dict:
    """Validate the row and the existing file, then append one LF line."""
    validate_look(row)
    path = Path(path)
    load_looks(path)   # never append to a file that no longer parses
    ordered = {name: row[name] for name in LOOK_FIELDS}
    lead = "\n" if path.exists() and path.read_bytes()[-1:] not in (b"", b"\n") else ""
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(lead + json.dumps(ordered, ensure_ascii=False) + "\n")
    return ordered


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--skill", required=True, help="the review skill, e.g. trade-autopsy")
    p.add_argument("--trade-id", required=True, help="the trades table id")
    p.add_argument("--close-date", required=True, help="YYYY-MM-DD the trade closed")
    p.add_argument("--date", default=None, help="YYYY-MM-DD of the look; default today")
    p.add_argument("--looks", type=Path, default=LOOKS_PATH)
    return p


def row_from_args(args) -> dict:
    return {"skill": args.skill, "date": args.date or date.today().isoformat(),
            "trade_id": args.trade_id, "close_date": args.close_date}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        row = append_look(row_from_args(args), path=args.looks)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_look_record_cli.py`
Expected: PASS — 15 passed (11 tests, the parametrised one counting 5), `0 failed`, `0 xfailed`.

- [ ] **Step 5: Check complexity and that the real file was not touched**

Run: `python -m radon cc -s -n C scripts/reports/look_record.py` (install with `pip install radon` if missing)
Expected: no output (every function below C).

Run: `git status --short docs/superpowers/results/looks.jsonl`
Expected: no output — the tests write only under `tmp_path`; the real file is created in V156-3.

- [ ] **Step 6: Hand back for commit**

Do not commit. The controller commits on the implementation branch:

```bash
git add scripts/reports/look_record.py tests/scripts/test_look_record_cli.py
git commit -m "feat(v156): look-record writer for docs/superpowers/results/looks.jsonl"
```

### Task V156-2: `/trade-autopsy` skill, shape tests, Codex mirror

**Model:** sonnet — skill prose plus test-set edits in one area, behaviour fixed by the spec's Design and "Answered by the brief"; no `swingbot/` code.

**Files:**
- Create: `.claude/skills/trade-autopsy/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `AGENTS.md`
- Modify: `docs/claude/skills-tools.md`
- Generated by `python scripts/dev/sync_codex.py`: `.agents/skills/trade-autopsy/SKILL.md`, `.agents/skills/trade-autopsy/agents/openai.yaml`

Depends on V156-1: the skill's Step 3 cites `scripts/reports/look_record.py` and its flags `--skill`, `--trade-id`, `--close-date`.

Traps (from the brief § 10): `N = 1` with spaces matches `_THRESHOLD_RE`, `N=1` does not; `trade["entry"]` is the fill for stop-entry plans, so the alerted entry is `plan.trigger_price` and slippage uses the alerted risk `|trigger_price - stop_loss|`; the MFE/MAE window starts on the alert day; `opened_at` is the alert time, the fill time lives only in `plan.status_history`. The description must stay a plain YAML scalar: no `: `, no ` #`.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_skill_shape.py`, add the name to `TIER_2` (line 26 today):

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "trade-autopsy"}        # each ritual task appends its own name
```

Add it to `FORKED` (line 97 today), keeping the v107 comment above it unchanged:

```python
FORKED = {"gate": "sonnet", "task-brief": "sonnet", "trade-autopsy": "sonnet"}
```

Append at the end of the file:

```python
# v156: /trade-autopsy is descriptive only. Pin the closing line, the fields
# it must never print, and a description the strict v154 loader accepts.
TRADE_AUTOPSY_CLOSING_LINE = ("Descriptive only, N=1. A pattern seen here is a "
                              "hypothesis for `/screen` or `/prereg`, not a result.")


def test_trade_autopsy_pins_its_closing_line_and_exclusions():
    meta, body = _read_skill("trade-autopsy")
    assert TRADE_AUTOPSY_CLOSING_LINE in body
    excluded = body.split("## Excluded on purpose", 1)[1].split("\n## ", 1)[0]
    for field in ("`auto_lesson`", "`tags`", "anything after the exit",
                  "interval or significance figure"):
        assert field in excluded, field
    assert "`not recorded`" in body
    assert "scripts/ops/ssh-hetzner.sh" in body
    assert "scripts/reports/look_record.py --skill trade-autopsy" in body


def test_trade_autopsy_description_is_a_plain_yaml_scalar():
    meta, _ = _read_skill("trade-autopsy")
    description = meta["description"]
    assert ": " not in description and " #" not in description
    assert description[0] not in "-?:,[]{}#&*!|>'\"%@`"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — `test_every_skill_is_registered_in_exactly_one_tier` (`trade-autopsy` in `TIER_2`, no directory), `test_mechanical_skills_run_forked[trade-autopsy]`, `test_ritual_skills_are_slash_only` and both new tests with `FileNotFoundError` on `.claude/skills/trade-autopsy/SKILL.md`.

- [ ] **Step 3: Write the skill**

Create `.claude/skills/trade-autopsy/SKILL.md` with exactly this content (79 lines; the budget is 80):

```markdown
---
name: trade-autopsy
description: Review one closed trade in a fixed, measured shape (plan as alerted, fill versus plan, placeability, excursions, exit, context) and record the look. Slash-only, run as /trade-autopsy followed by a trade id.
disable-model-invocation: true
context: fork
model: sonnet
---

# Trade autopsy

One closed trade, measured, never judged: the seven lines of Step 2 in order
and nothing else, no verdict ("stop too tight", "bad setup"). A field the data
cannot supply prints `not recorded`, never an estimate. Every figure names its
module and the price it was measured from (`pooled-numbers`).

## Step 1 -- Read the trade on production, read-only

The stores are Postgres on the Hetzner VM only. Use the wrapper and nothing
else (no raw `ssh`, no restart, no write), with a stdin script from the scratchpad:

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < <script>

The script prints one JSON object built from `TradeLog().get_trade_by_id(id)`,
`PlanStore().get_record(trade["plan_id"])` when `plan_id` is set,
`JournalStore().get(id)`, `compute_mfe_mae(trade, df)` with
`df = get_daily_data(ticker)`, and from `df` sliced to sessions strictly
before the alert session: `_avg_dollar_vol(sliced)`
(`swingbot/core/marketdata/universe.py`). Earnings: when
`CsvSource().has_data(ticker)`, the reports whose `reaction_session` falls
from the alert session to the close date (`earnings_calendar.py`). Never
`df.tail` of the unsliced cache: that is lookahead.

Stop with one line, and record no look, when: the wrapper is missing or
errors (quote its error; never fall back to a local copy); the trade id does
not exist; the trade's `status` is `open` (excursions are not final).

## Step 2 -- Print the seven lines

1. **Plan as alerted** -- entry `plan.trigger_price`, `stop_loss`,
   `take_profit` and `target2`, `horizon_key`, `strategy`,
   `confidence_level`, alert time `opened_at`. Never `trade["entry"]` here: a
   stop-entry fill overwrote it. No `plan_id`: entry `not recorded`.
2. **Fill versus plan** -- fill `plan.entry_price` against `trigger_price`
   (no session-open price is stored, so this is not the open gap); fill time
   is the `at` of the first `ACTIVE` entry in `status_history` for a stop
   entry, `not recorded` for a market entry; slippage in R is the signed
   fill minus trigger over the alerted risk `|trigger_price - stop_loss|`;
   entry gapped through when fill differs from trigger, stop gapped through
   when `exit_price` lies beyond `stop_loss`. A paper fill is the poller's
   observed price, not a broker execution.
3. **Placeable before the open** -- yes or no: `opened_at` outside
   `is_regular_session` (`swingbot/core/market/session.py`) and an
   `entry_type` that can rest as an order (not `market`).
4. **Excursions** -- `mfe_r` and `mae_r` from `compute_mfe_mae`
   (`swingbot/core/analytics/mfe_mae.py`), reference price `trade["entry"]`
   labelled filled (stop entry) or alerted, equal to the fill (market entry).
   State that the window starts on the alert day, so bars before the fill
   count. No bar index: the module returns none.
5. **Exit** -- `close_reason_text(trade)`, `exit_price`, `closed_at`, the
   journal's `r_realized`, and any expiry or time-exit state from the plan's
   `status_history`, `time_stop_days` and `stall_exit_day`.
6. **Context** -- earnings inside the holding window, or `not recorded`
   without a CSV (never `LiveSource`, never
   `risk_features["days_to_earnings"]`, which is never populated); dollar
   volume as of the alert against `position_value`.
7. The fixed line, verbatim:
   Descriptive only, N=1. A pattern seen here is a hypothesis for `/screen` or `/prereg`, not a result.

## Excluded on purpose

Never print the journal's `auto_lesson` or `tags` (single-trade verdicts),
anything after the exit, or any interval or significance figure.

## Step 3 -- Record the look

Only after the seven lines printed for a closed trade; the caller commits
`docs/superpowers/results/looks.jsonl` with whatever change follows the review.

    python scripts/reports/look_record.py --skill trade-autopsy --trade-id <id> --close-date <closed_at date>
```

Check the budget and the regex by hand before re-running pytest:

Run: `wc -l .claude/skills/trade-autopsy/SKILL.md`
Expected: `79 .claude/skills/trade-autopsy/SKILL.md` (anything above 80 fails `test_new_skills_stay_within_the_line_budget`; trim prose, never the seven lines or the excluded list).

- [ ] **Step 4: Run the shape tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS — `0 failed`, `0 xfailed` (the parametrised budget and threshold tests now include `trade-autopsy`).

- [ ] **Step 5: Name the skill in `AGENTS.md` and `docs/claude/skills-tools.md`**

In `AGENTS.md`, § Skills, the explicit-only rituals paragraph (line 240 today; locate it with `grep -n "Explicit-only rituals" AGENTS.md`), replace

```text
sequence), `stable-snapshot` (pin a known-good point) and `backup-pull` (off-VM
backup pull). `new-doc` (new spec or plan) and `close-out` (plan close-out) may
```

with

```text
sequence), `stable-snapshot` (pin a known-good point), `backup-pull` (off-VM
backup pull) and `trade-autopsy` (one closed trade in a fixed, measured shape,
read-only from production; each run appends a look to
`docs/superpowers/results/looks.jsonl`). `new-doc` (new spec or plan) and
`close-out` (plan close-out) may
```

In `docs/claude/skills-tools.md`, after the `backup-pull` row of the skills table (line 97 today; `grep -n "^| \`backup-pull\`" docs/claude/skills-tools.md`), insert the row

```text
| `trade-autopsy` | 2 | slash-only (`/trade-autopsy <trade id>`), forked on sonnet | none — Step 1 reads production through `scripts/ops/ssh-hetzner.sh`; Step 3 appends to `docs/superpowers/results/looks.jsonl` (v156) |
```

and in the paragraph below the table replace

```text
checklists for an explicit slash command. `/deploy`, `/stable-snapshot` and
`/backup-pull` also carry `disable-model-invocation: true`: the model never
```

with

```text
checklists for an explicit slash command. `/deploy`, `/stable-snapshot`,
`/backup-pull` and `/trade-autopsy` also carry `disable-model-invocation: true`: the model never
```

- [ ] **Step 6: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py`
Expected: writes `.agents/skills/trade-autopsy/SKILL.md` and `.agents/skills/trade-autopsy/agents/openai.yaml` (the skill carries `disable-model-invocation: true`), then its `check()` prints nothing and exits 0.

Run: `python scripts/dev/sync_codex.py --check`
Expected: exit 0, no output. A line naming `trade-autopsy` and `AGENTS.md` means the Step 5 mention is missing its backticks.

Run: `git status --short .agents .codex`
Expected: only the two new `.agents/skills/trade-autopsy/` files.

- [ ] **Step 7: Run the mirror test**

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS — `0 failed`, `0 xfailed`.

- [ ] **Step 8: Hand back for commit**

Do not commit. The controller commits the skill and its mirror together (CLAUDE.md § Claude is the operator):

```bash
git add .claude/skills/trade-autopsy/SKILL.md tests/hooks/test_skill_shape.py AGENTS.md docs/claude/skills-tools.md .agents/skills/trade-autopsy
git commit -m "feat(v156): /trade-autopsy slash-only forked skill with Codex mirror"
```

### Task V156-3: Manual run against one real closed trade, recorded

**Model:** sonnet — run and check against the spec's output shape; production is read-only and the skill is typed by the partner, so the implementer prepares, checks and records.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-10-v156-review-ritual-skills.md` (`## Results`)
- Create: `docs/superpowers/results/looks.jsonl` (first row, written by `scripts/reports/look_record.py` from the skill's Step 3, never by hand)

This is the spec's manual test ("one run against a real closed trade"). It needs the operator machine: `scripts/ops/ssh-hetzner.sh` is gitignored and exists only there. **If `test -f scripts/ops/ssh-hetzner.sh` fails, stop and return `BLOCKED: V156-3 needs the operator machine (ssh-hetzner.sh absent)`.** Never substitute a raw `ssh`, another key, or a local copy of the data.

- [ ] **Step 1: Confirm the route exists**

Run: `test -f scripts/ops/ssh-hetzner.sh && echo present`
Expected: `present`. Anything else: stop with the `BLOCKED` line above.

- [ ] **Step 2: Pick one closed trade, read-only**

Pick the most recently closed trade that has a `plan_id`, so lines 1 and 2 are exercised rather than printing `not recorded`. Write this to the scratchpad as `pick_trade.py`:

```python
"""v156 V156-3: newest closed trade with a plan_id. Read-only."""
import json

from swingbot.core.tracking.performance import TradeLog

closed = [t for t in TradeLog().get_trades(limit=None)
          if t.get("status") != "open" and t.get("plan_id") and t.get("closed_at")]
closed.sort(key=lambda t: t["closed_at"], reverse=True)
pick = closed[0] if closed else None
print(json.dumps(None if pick is None else {
    "id": pick["id"], "ticker": pick["ticker"], "strategy": pick.get("strategy"),
    "closed_at": pick["closed_at"], "plan_id": pick["plan_id"]}))
```

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < <scratchpad>/pick_trade.py`
Expected: one JSON object with the trade `id`. `null` means no closed trade with a plan exists: record that under `## Results` and drop the `plan_id` filter for a second pick, so lines 1–2 print `not recorded` and that path is the one recorded.

`TradeLog().get_trades(limit=None)` is `performance.py:1109` (its default `limit` is 20, so `None` is required); if its signature has changed (`git grep -n "def get_trades" swingbot/core/tracking/performance.py`), adapt the call, not the filter.

- [ ] **Step 3: The partner runs the skill**

Ask the partner (one `AskUserQuestion`, recommended option first) to type `/trade-autopsy <id>` with the id from Step 2. The skill is slash-only (`disable-model-invocation: true`), so no agent and no controller `Skill` call can run it. Capture its full output.

- [ ] **Step 4: Check the output against the spec**

Each item is yes or no; a no is a finding for the controller, fixed in `.claude/skills/trade-autopsy/SKILL.md` (and re-mirrored with `python scripts/dev/sync_codex.py`) before the results are recorded:

1. Exactly seven numbered lines, in the spec's order, and nothing else.
2. Line 1's entry is `plan.trigger_price`, not `trade["entry"]`.
3. Line 2 prints fill versus trigger, a fill time (stop entry) or `not recorded` (market entry), slippage in R over `|trigger_price - stop_loss|`, and both gapped-through answers.
4. Line 3 is yes or no.
5. Line 4 names `compute_mfe_mae`, its reference price (filled or alerted), and the alert-day window note.
6. Line 6 prints `not recorded` for earnings when production holds no CSV for the ticker, and dollar volume as of the alert.
7. Line 7 is `Descriptive only, N=1. A pattern seen here is a hypothesis for `/screen` or `/prereg`, not a result.` verbatim.
8. No `auto_lesson`, no tags, no verdict wording, nothing after the exit, no interval or significance figure.
9. `docs/superpowers/results/looks.jsonl` gained exactly one row for this trade id, with today's `date` and the trade's close date:

Run: `python -c "import sys; sys.path.insert(0, 'scripts/reports'); import look_record as l; print(l.load_looks()[-1])"`
Expected: `{'skill': 'trade-autopsy', 'date': '<today>', 'trade_id': '<id>', 'close_date': '<closed_at date>'}`.

- [ ] **Step 5: Record the results**

Append to `## Results` in this plan (above `# Phase 1`), as plain text:

```markdown
### V156-3 manual run (<date>)

- Trade: `<id>` (`<ticker>`, `<strategy>`, closed `<closed_at>`), picked as the newest closed trade with a `plan_id`.
- Entry type: `<stop|market|limit>`; earnings CSV on production: `<yes|no>`.
- Output, verbatim:

  <the seven lines>

- Checks 1–9 of Step 4: <all yes | which failed, and the SKILL.md fix>.
- Look row: `<the looks.jsonl line>`.
```

Do not interpret the trade's outcome in the results: they record that the shape held, not what the trade means (N=1).

- [ ] **Step 6: Hand back for commit**

Do not commit. The controller commits the first look row with the results that followed it:

```bash
git add docs/superpowers/results/looks.jsonl docs/superpowers/plans/2026-10-10-v156-review-ritual-skills.md
git commit -m "docs(v156): record the first /trade-autopsy run and its look"
```

If Step 4 needed a skill fix, it goes in the same commit with `.claude/skills/trade-autopsy/SKILL.md` and `.agents/skills/trade-autopsy/` staged too.

### Task V156-4: Full suite, then `/panel quant-researcher,veteran-trader` before close-out

**Model:** haiku — mechanical: dispatch the suite, dispatch the panel, record both verdicts; no code.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-10-v156-review-ritual-skills.md` (`## Results`)

The one full-suite run of this plan (CLAUDE.md § Naming specs and plans), then the spec's `**Panel:**` roles over the landed diff, which `/panel` requires before `/close-out` of a plan built from a spec with a Panel line.

- [ ] **Step 1: Run the full suite through `test-runner`**

Dispatch the `test-runner` subagent with: `python scripts/dev/testrun.py full`. Do not run it in the main context and do not run another suite alongside it.
Expected: one-line verdict with `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Any failure: stop, fix it in the task that owns the file (V156-1 or V156-2), re-run the narrow file, then re-dispatch this step.

- [ ] **Step 2: Run the panel**

Run `/panel quant-researcher,veteran-trader` over the diff of this plan's commits (`git diff <commit before V156-1>..HEAD`), the target being the skill, the writer and the `## Results` of V156-3. The roles review at their own models (`docs/claude/skills-tools.md` § Expert roles).
Expected: merged findings, each BLOCKING or ADVISORY. A BLOCKING finding is fixed in the owning file before close-out (a skill fix re-runs `python scripts/dev/sync_codex.py` and `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`), then Step 1 re-runs once.

- [ ] **Step 3: Record the results**

Append to `## Results` in this plan:

```markdown
### V156-4 full suite and panel (<date>)

- Full suite (`python scripts/dev/testrun.py full`, via `test-runner`): <verdict line>.
- Panel (`quant-researcher`, `veteran-trader`) on `<sha>`: <n> BLOCKING, <n> ADVISORY.
  - <role>: <BLOCKING|ADVISORY> — <finding> — <applied | rejected: reason>.
```

- [ ] **Step 4: Hand back for commit, then close out**

Do not commit. The controller commits:

```bash
git add docs/superpowers/plans/2026-10-10-v156-review-ritual-skills.md
git commit -m "docs(v156): record full suite and panel review"
```

Then `/close-out` (`Bump: none`: no `VERSION.json` change; the plan moves to `implemented/`).

