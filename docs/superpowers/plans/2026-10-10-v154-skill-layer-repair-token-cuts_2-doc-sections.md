# v154 Skill layer repair and token cuts: Part 2, addressable `docs/claude/` sections

> Part of the v154 plan. Header, Global Constraints, the decisions fixed by the index, the cross-task contracts C1 to C6, the parallelisation map and the `## Results` table are in [`_0-index`](2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md). **Never read this file whole**: `/task-brief V154-6` or `grep -n "^### Task V154-6" -A 200 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md`](../specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md), section 3.

This part covers tasks V154-5 to V154-8: the headings go into three docs by pure insertion, `scripts/dev/doc_section.py` prints sections by name, the new tests are routed from `docs/claude/` changes, and four skills' Step 1 call the script.

Rules that hold for every task here:

- All commands run from the root of the plan's worktree, in Git Bash.
- **Anchor on text, never on a line number.** Line numbers quoted below are from `main` when this part was written and are there only to help you find the place. Locate every edit with `grep -n` on the quoted text first.
- The three docs, the skills and most scripts are checked out with CRLF line endings on Windows and stored with LF. Use the Edit tool for hand edits (it keeps a file's endings); the one scripted edit in V154-5 works on bytes and keeps them too.
- Scripts run through `python - <<'PY'` are ASCII only on purpose (Windows decodes stdin with the console code page), so non-ASCII characters are written as escapes inside them.
- Do not run the full suite. Each task names its narrow run; the full suite is V154-13.

---

### Task V154-5: Insert section headings in three `docs/claude/` files, with the insertion-only check and the pin test

**Model:** sonnet — a scripted, checked edit of three reference docs plus one new test module; no judgement about wording, but the closed pre-registration table sits in one of the files.

**Files:**
- Create: `tests/hooks/test_doc_sections.py`
- Modify: `docs/claude/backtest-methodology.md`
- Modify: `docs/claude/known-traps.md`
- Modify: `docs/claude/architecture.md`
- Modify: `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md` (four rows of `## Results`)

**Interfaces:**
- Consumes: nothing from another task.
- Produces: the seventeen `##` headings of index contract C3, exactly as spelled there. V154-7 names `tests/hooks/test_doc_sections.py` in `scripts/dev/select_tests.py`; V154-8 passes these heading names to `scripts/dev/doc_section.py`.

**What this task must not do.** These are the spec's hard limits; the check in Step 6 enforces them mechanically.

- No existing line changes, moves or disappears in any of the three docs. No bullet becomes a heading, no paragraph is cut or rewrapped.
- `### Closed pre-registrations — do not re-run these` keeps its level and its exact text, and nothing is inserted at or after it. `tests/hooks/test_guardrails.py` splits the doc on the literal `### Closed pre-registrations`, and `tests/backtesting/test_preregistration_ledger_file.py` looks the full line up with `lines.index(...)`.
- `Stage −2` stays the bold bullet it is. It ends up inside `## Funnel stages`; it is not a heading.
- No wording of any gate, window, constant or closed pre-registration changes. This task re-runs no backtest and sets no threshold.
- The ten `##` sections `known-traps.md` already has (from the `PlanManager.check_bar()` one down) are untouched; all six new headings go into the preamble above them.

**Where the headings go.** One `## <Heading>` line, then one blank line, in front of the line that starts with the anchor text. Where the line above the anchor is not blank today, one blank line goes in before the heading too. Line numbers are from `main` at `53ad9ebe` and are informational; the script in Step 4 finds each place by the anchor text and stops if a doc has moved.

| Doc | Heading | Goes before the line starting | Line (main) | Line above blank? |
|---|---|---|---|---|
| `backtest-methodology.md` | `## Windows` | `- **Windows:** TRAIN = ` | 6 | yes |
| `backtest-methodology.md` | `## Acceptance gate` | `- **Acceptance gates (v72, ` | 11 | no |
| `backtest-methodology.md` | `## Badge scoring` | `  **The surviving badge threshold, and its history**` (two leading spaces) | 38 | yes |
| `backtest-methodology.md` | `## Funnel stages` | `- **Stage −2: the idea screen` | 53 | yes |
| `backtest-methodology.md` | `## Harvest gate` | ``- **`Edge: harvest` features are OUT OF SCOPE`` | 104 | yes |
| `backtest-methodology.md` | `## Frozen constants` | ``- Frozen constants: `MIN_RISK_REWARD_RATIO`` | 138 | no |
| `backtest-methodology.md` | `## Evidence, registry and ledger` | `- **Evidence age.**` | 143 | no |
| `known-traps.md` | `## Two OHLCV caches` | `- **Two parallel OHLCV cache subsystems` | 7 | yes |
| `known-traps.md` | `## Legacy shims and silent no-ops` | `- **The legacy shims are gone` | 42 | no |
| `known-traps.md` | `## Measured-empty tables` | `- **An empty config table is not automatically` | 73 | no |
| `known-traps.md` | `## Re-exports, stale prices and plan closes` | `- **An "unused import" here is often a deliberate re-export` | 83 | no |
| `known-traps.md` | `## Full-history cache and the live scan read` | ``- **`market_data/daily/{TICKER}.csv` holds each ticker's FULL history`` | 124 | no |
| `known-traps.md` | `## Trade History, file sources and the write halt` | `- **Trade History: filtering, sorting and paging must stay` | 146 | no |
| `architecture.md` | `## Module map` | ``- `swingbot/core/` is business logic with **no Discord dependency**`` | 6 | yes |
| `architecture.md` | `## Entry-signal single source` | `- **Entry signals have a single source:**` | 66 | no |
| `architecture.md` | `## NO-LOOKAHEAD` | `- **NO-LOOKAHEAD RULE (law):**` | 72 | no |
| `architecture.md` | `## Plan engine, registry and scan pipeline` | `- **Plan Engine v2** (` | 76 | no |

Resulting line counts: `backtest-methodology.md` 256 to 273 (+17: seven headings, ten blank lines), `known-traps.md` 391 to 408 (+17: six headings, eleven blank lines), `architecture.md` 138 to 149 (+11: four headings, seven blank lines).

The `AGENTS.md` mirror needs no text for this task: no rule changed, only headings were added. The one `AGENTS.md` line about reading by section is V154-7's.

- [ ] **Step 1: Confirm the three docs are clean before touching them**

```bash
git status --short -- docs/claude/backtest-methodology.md docs/claude/known-traps.md docs/claude/architecture.md
git grep -c "^## " -- docs/claude/backtest-methodology.md docs/claude/architecture.md
```

Expected: the first command prints nothing (no uncommitted edit in any of the three), and the second prints nothing either (neither file has a `##` heading yet; `git grep -c` omits files with no match). If the first command prints a file, stop and report it: another session's uncommitted work is in that doc, and the insertion-only check compares against `HEAD`.

- [ ] **Step 2: Write the pin test**

Create `tests/hooks/test_doc_sections.py`:

```python
"""v154: three docs/claude/ files carry the `##` headings skills read by name.

The headings were inserted between existing lines (nothing else in the docs
changed), so that `scripts/dev/doc_section.py` can print one section instead
of the whole file. This module pins that each heading is there, opens the
content it is named for, and that the heading arguments the skills pass match
exactly one heading each. It reads the docs directly and does not run
`doc_section.py`; that script has its own tests in tests/dev/.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "claude"
SKILLS = ROOT / ".claude" / "skills"

CLOSED = "### Closed pre-registrations — do not re-run these"
STAGE_MINUS_TWO = "- **Stage −2: the idea screen"

# doc -> [(inserted heading line, how the first line of its section starts)]
INSERTED = {
    "backtest-methodology.md": [
        ("## Windows", "- **Windows:** TRAIN = "),
        ("## Acceptance gate", "- **Acceptance gates (v72, "),
        ("## Badge scoring", "  **The surviving badge threshold, and its history**"),
        ("## Funnel stages", STAGE_MINUS_TWO),
        ("## Harvest gate", "- **`Edge: harvest` features are OUT OF SCOPE"),
        ("## Frozen constants", "- Frozen constants: `MIN_RISK_REWARD_RATIO"),
        ("## Evidence, registry and ledger", "- **Evidence age.**"),
    ],
    "known-traps.md": [
        ("## Two OHLCV caches", "- **Two parallel OHLCV cache subsystems"),
        ("## Legacy shims and silent no-ops", "- **The legacy shims are gone"),
        ("## Measured-empty tables", "- **An empty config table is not automatically"),
        ("## Re-exports, stale prices and plan closes",
         '- **An "unused import" here is often a deliberate re-export'),
        ("## Full-history cache and the live scan read",
         "- **`market_data/daily/{TICKER}.csv` holds each ticker's FULL history"),
        ("## Trade History, file sources and the write halt",
         "- **Trade History: filtering, sorting and paging must stay"),
    ],
    "architecture.md": [
        ("## Module map", "- `swingbot/core/` is business logic with **no Discord dependency**"),
        ("## Entry-signal single source", "- **Entry signals have a single source:**"),
        ("## NO-LOOKAHEAD", "- **NO-LOOKAHEAD RULE (law):**"),
        ("## Plan engine, registry and scan pipeline", "- **Plan Engine v2** ("),
    ],
}

# Headings that were already there and that skills also read by name.
EXISTING = {
    "backtest-methodology.md": [CLOSED],
    "known-traps.md": [
        "## Scan parameter and replay gate parity (v74)",
        "## The market_data cache never self-heals (v116 follow-up)",
    ],
}

# The heading arguments each skill's Step 1 passes to doc_section.py.
SKILL_READS = {
    "backtest-methodology.md": [
        "Acceptance gate", "Funnel stages", "Windows", "Frozen constants",
        "Closed pre-registrations", "Badge scoring",
    ],
    "known-traps.md": [
        "Two OHLCV caches", "Full-history cache", "Legacy shims",
        "Measured-empty tables", "Scan parameter and replay gate parity",
        "The market_data cache never self-heals",
    ],
    "architecture.md": ["NO-LOOKAHEAD", "Entry-signal single source"],
}

_HEADING_RE = re.compile(r"^#{2,3} (\S.*)$")
_COMMAND_RE = re.compile(r'doc_section\.py (docs/claude/[\w.-]+\.md)((?: "[^"\n]+")+)')


def _lines(doc: str) -> list[str]:
    return (DOCS / doc).read_text(encoding="utf-8").splitlines()


def _titles(doc: str) -> list[str]:
    """Titles of the doc's `##` and `###` headings, lower-cased."""
    found = (_HEADING_RE.match(line) for line in _lines(doc))
    return [m.group(1).strip().lower() for m in found if m]


def _matches(doc: str, argument: str) -> int:
    """How many headings a doc_section.py argument selects (prefix, any case)."""
    return sum(title.startswith(argument.lower()) for title in _titles(doc))


def _skill_commands() -> list[tuple[str, str, list[str]]]:
    """(skill, doc file name, heading arguments) for every doc_section.py
    command line written in a skill."""
    commands = []
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for doc, arguments in _COMMAND_RE.findall(text):
            commands.append((skill_md.parent.name, doc.rsplit("/", 1)[1],
                             re.findall(r'"([^"]+)"', arguments)))
    return commands


@pytest.mark.parametrize("doc", sorted(INSERTED))
def test_inserted_headings_appear_once_and_in_order(doc):
    lines = _lines(doc)
    headings = [heading for heading, _ in INSERTED[doc]]
    assert [lines.count(h) for h in headings] == [1] * len(headings)
    positions = [lines.index(h) for h in headings]
    assert positions == sorted(positions)


@pytest.mark.parametrize(
    "doc, heading, opens_with",
    [(doc, heading, start) for doc in sorted(INSERTED) for heading, start in INSERTED[doc]],
)
def test_inserted_heading_stands_alone_and_opens_its_content(doc, heading, opens_with):
    lines = _lines(doc)
    at = lines.index(heading)
    assert lines[at - 1] == "", "a blank line must precede the heading"
    assert lines[at + 1] == "", "a blank line must follow the heading"
    assert lines[at + 2].startswith(opens_with), lines[at + 2][:80]


def test_closed_preregistrations_heading_keeps_its_level_and_text():
    lines = _lines("backtest-methodology.md")
    text = "\n".join(lines)
    assert lines.count(CLOSED) == 1
    # test_guardrails splits the doc on this literal; a second occurrence, for
    # example inside an inserted heading, would move the split.
    assert text.count("### Closed pre-registrations") == 1
    assert [line for line in lines if line.startswith("### ")] == [CLOSED]
    closed_at = lines.index(CLOSED)
    assert lines.index("## Evidence, registry and ledger") < closed_at
    assert not [line for line in lines[closed_at:] if line.startswith("## ")]


def test_stage_minus_two_stays_a_bullet_inside_funnel_stages():
    lines = _lines("backtest-methodology.md")
    bullets = [i for i, line in enumerate(lines) if line.startswith(STAGE_MINUS_TWO)]
    assert len(bullets) == 1
    assert not [line for line in lines if line.startswith("#") and "Stage" in line]
    funnel = lines.index("## Funnel stages")
    harvest = lines.index("## Harvest gate")
    assert funnel < bullets[0] < harvest
    assert any("measure_arms" in line for line in lines[funnel:harvest])


def test_known_traps_headings_go_in_the_preamble_only():
    lines = _lines("known-traps.md")
    last_inserted = max(lines.index(heading) for heading, _ in INSERTED["known-traps.md"])
    first_existing = min(lines.index(heading) for heading in EXISTING["known-traps.md"])
    assert last_inserted < first_existing


@pytest.mark.parametrize("doc", sorted(EXISTING))
def test_existing_headings_the_skills_read_are_still_there(doc):
    lines = _lines(doc)
    assert [lines.count(heading) for heading in EXISTING[doc]] == [1] * len(EXISTING[doc])


@pytest.mark.parametrize(
    "doc, argument",
    [(doc, argument) for doc in sorted(SKILL_READS) for argument in SKILL_READS[doc]],
)
def test_skill_heading_argument_selects_exactly_one_heading(doc, argument):
    assert _matches(doc, argument) == 1


def test_every_doc_section_command_in_a_skill_names_real_headings():
    """Drift guard for the skill text itself. It finds no command until the
    skills call doc_section.py; from then on a renamed heading or a mistyped
    argument in any skill fails here."""
    problems = [
        f"{skill}: {doc} {argument!r} selects {_matches(doc, argument)} headings"
        for skill, doc, arguments in _skill_commands()
        for argument in arguments
        if _matches(doc, argument) != 1
    ]
    assert problems == []
```

Two notes on it. `SKILL_READS` is index contract C5 flattened per doc: it is checked here, against the docs, so this task depends neither on `doc_section.py` nor on the skill edits. The last test finds zero commands until V154-8 lands and is a drift guard from then on; V154-8 shows it is live.

- [ ] **Step 3: Run the pin test and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`

Expected: `VERDICT: FAIL` with `34 failed` and `6 passed`. The failures are `ValueError: '## Windows' is not in list` and the like (the headings do not exist), and `assert 0 == 1` for the heading arguments that have no heading yet. The six that pass already are the two `EXISTING` cases, the arguments `Closed pre-registrations`, `Scan parameter and replay gate parity` and `The market_data cache never self-heals`, and the skill-command drift guard. If the counts differ, read the failures before going on: a doc has moved since this part was written.

- [ ] **Step 4: Insert the headings with the script**

Do not make these seventeen edits by hand. Run this once, from the worktree root:

```bash
python - <<'PY'
"""One-off: insert the v154 section headings. Pure insertion, byte level."""
import sys
from pathlib import Path

# doc -> [(heading, start of the line the heading goes before, is the line
#          above that one blank today?)]. \u2212 is the minus sign in "Stage -2".
PLAN = {
    "backtest-methodology.md": [
        ("Windows", "- **Windows:** TRAIN = ", True),
        ("Acceptance gate", "- **Acceptance gates (v72, ", False),
        ("Badge scoring", "  **The surviving badge threshold, and its history**", True),
        ("Funnel stages", "- **Stage \u22122: the idea screen", True),
        ("Harvest gate", "- **`Edge: harvest` features are OUT OF SCOPE", True),
        ("Frozen constants", "- Frozen constants: `MIN_RISK_REWARD_RATIO", False),
        ("Evidence, registry and ledger", "- **Evidence age.**", False),
    ],
    "known-traps.md": [
        ("Two OHLCV caches", "- **Two parallel OHLCV cache subsystems", True),
        ("Legacy shims and silent no-ops", "- **The legacy shims are gone", False),
        ("Measured-empty tables", "- **An empty config table is not automatically", False),
        ("Re-exports, stale prices and plan closes",
         '- **An "unused import" here is often a deliberate re-export', False),
        ("Full-history cache and the live scan read",
         "- **`market_data/daily/{TICKER}.csv` holds each ticker's FULL history", False),
        ("Trade History, file sources and the write halt",
         "- **Trade History: filtering, sorting and paging must stay", False),
    ],
    "architecture.md": [
        ("Module map", "- `swingbot/core/` is business logic with **no Discord dependency**", True),
        ("Entry-signal single source", "- **Entry signals have a single source:**", False),
        ("NO-LOOKAHEAD", "- **NO-LOOKAHEAD RULE (law):**", False),
        ("Plan engine, registry and scan pipeline", "- **Plan Engine v2** (", False),
    ],
}


def with_headings(path: Path, rows) -> bytes:
    """The doc's bytes with its headings inserted. Stops on any surprise."""
    lines = path.read_bytes().splitlines(keepends=True)
    for heading, anchor, blank_above in rows:
        heading_line = f"## {heading}".encode("utf-8")
        if any(line.strip() == heading_line for line in lines):
            sys.exit(f"{path.name}: '## {heading}' is already there -- nothing written")
        hits = [i for i, line in enumerate(lines) if line.startswith(anchor.encode("utf-8"))]
        if len(hits) != 1:
            sys.exit(f"{path.name}: {len(hits)} lines start with {anchor!r}, "
                     "need exactly 1 -- nothing written")
        at = hits[0]
        if (lines[at - 1].strip() == b"") != blank_above:
            sys.exit(f"{path.name}: the line above {anchor!r} is "
                     f"{'not ' if blank_above else ''}blank, the table says otherwise "
                     "-- nothing written")
        eol = b"\r\n" if lines[at].endswith(b"\r\n") else b"\n"
        lines[at:at] = ([] if blank_above else [eol]) + [heading_line + eol, eol]
    return b"".join(lines)


def main() -> None:
    docs = Path("docs/claude")
    # Build all three before writing any: a stop leaves every doc untouched.
    built = {name: with_headings(docs / name, rows) for name, rows in PLAN.items()}
    for name, data in built.items():
        before = len((docs / name).read_bytes().splitlines())
        (docs / name).write_bytes(data)
        print(f"{name}: +{len(data.splitlines()) - before} lines")


main()
PY
```

Expected output:

```
backtest-methodology.md: +17 lines
known-traps.md: +17 lines
architecture.md: +11 lines
```

The script builds all three results before it writes any, so a stop (`... -- nothing written`) leaves every doc as it was. It stops when an anchor matches zero or several lines, when the line above an anchor is not blank where the table says it is (or the reverse), or when a heading is already there. On any stop: do not edit the table to make it pass. Open the doc at the anchor, compare it with the table above, and report the mismatch. A doc that has moved is resolved by anchoring on the following line's text, with the controller's agreement.

- [ ] **Step 5: Stage the three docs and look at the shape of the diff**

```bash
git add docs/claude/backtest-methodology.md docs/claude/known-traps.md docs/claude/architecture.md
git diff --cached --numstat -- docs/claude/
```

Expected, exactly (added, deleted, path), with **zero in the deleted column of every row**:

```
11	0	docs/claude/architecture.md
17	0	docs/claude/backtest-methodology.md
17	0	docs/claude/known-traps.md
```

A non-zero deleted count means an existing line was rewritten (a changed line ending counts). Stop, run `git restore --staged --worktree -- docs/claude/backtest-methodology.md docs/claude/known-traps.md docs/claude/architecture.md`, and start again from Step 4.

- [ ] **Step 6: Run the insertion-only check (old file equals new file minus the inserted heading and blank lines)**

This is the check the spec asks to be run once and recorded. It compares the committed blob with the staged blob, byte for byte, for all three docs: every line of the old file must appear in the new one in the same order, and the only extra lines may be the expected `##` headings, in order, plus the expected number of blank lines. Deleting those extra lines therefore reproduces the old file exactly. For `backtest-methodology.md` it also requires the bytes from `### Closed pre-registrations — do not re-run these` to the end of the file to be identical in both.

```bash
python - HEAD INDEX <<'PY'
"""Insertion-only check: old blob == new blob minus inserted heading and blank lines.

    python - [<old rev> [<new rev>]]      defaults: HEAD INDEX (INDEX = staged)
"""
import subprocess
import sys

# doc -> the headings that must be the only non-blank lines added, in order.
EXPECTED = {
    "backtest-methodology.md": [
        "## Windows", "## Acceptance gate", "## Badge scoring", "## Funnel stages",
        "## Harvest gate", "## Frozen constants", "## Evidence, registry and ledger"],
    "known-traps.md": [
        "## Two OHLCV caches", "## Legacy shims and silent no-ops",
        "## Measured-empty tables", "## Re-exports, stale prices and plan closes",
        "## Full-history cache and the live scan read",
        "## Trade History, file sources and the write halt"],
    "architecture.md": [
        "## Module map", "## Entry-signal single source", "## NO-LOOKAHEAD",
        "## Plan engine, registry and scan pipeline"],
}
BLANKS = {"backtest-methodology.md": 10, "known-traps.md": 11, "architecture.md": 7}
CLOSED = b"### Closed pre-registrations \xe2\x80\x94 do not re-run these"


def blob(rev: str, path: str) -> bytes:
    spec = f":{path}" if rev == "INDEX" else f"{rev}:{path}"
    return subprocess.run(["git", "show", spec], capture_output=True, check=True).stdout


def inserted_lines(old: list, new: list) -> list:
    """Lines of `new` that are not in `old`, walking both in order. Returns
    None when `old` is not `new` with lines removed."""
    extra, i = [], 0
    for line in new:
        if i < len(old) and line == old[i]:
            i += 1
        else:
            extra.append(line)
    return extra if i == len(old) else None


def closed_heading_problems(old: bytes, new: bytes) -> list:
    if old.count(CLOSED) != 1 or new.count(CLOSED) != 1:
        return ["the closed pre-registrations heading does not occur exactly once"]
    if old[old.index(CLOSED):] != new[new.index(CLOSED):]:
        return ["bytes changed at or after the closed pre-registrations heading"]
    return []


def problems_for(name: str, old: bytes, new: bytes) -> list:
    extra = inserted_lines(old.split(b"\n"), new.split(b"\n"))
    if extra is None:
        return ["an existing line was changed, moved or deleted"]
    found = []
    headings = [line.decode("utf-8") for line in extra if line != b""]
    if headings != EXPECTED[name]:
        found.append(f"non-blank inserted lines are {headings}")
    blanks = sum(1 for line in extra if line == b"")
    if blanks != BLANKS[name]:
        found.append(f"{blanks} blank lines inserted, expected {BLANKS[name]}")
    if name == "backtest-methodology.md":
        found += closed_heading_problems(old, new)
    return found


def main(argv: list) -> int:
    old_rev = argv[1] if len(argv) > 1 else "HEAD"
    new_rev = argv[2] if len(argv) > 2 else "INDEX"
    failed = False
    for name in EXPECTED:
        path = f"docs/claude/{name}"
        old, new = blob(old_rev, path), blob(new_rev, path)
        found = problems_for(name, old, new)
        failed = failed or bool(found)
        verdict = "FAIL " + "; ".join(found) if found else (
            f"OK  old == new minus {len(EXPECTED[name])} headings and "
            f"{BLANKS[name]} blank lines ({len(old)} -> {len(new)} bytes)")
        print(f"{name}: {verdict}")
    print(f"INSERTION-ONLY: {'FAIL' if failed else 'PASS'}  {old_rev} -> {new_rev}")
    return 1 if failed else 0


sys.exit(main(sys.argv))
PY
```

Expected output (the byte counts are the blobs at `53ad9ebe` and are informational; the verdicts are not):

```
backtest-methodology.md: OK  old == new minus 7 headings and 10 blank lines (59561 -> 59704 bytes)
known-traps.md: OK  old == new minus 6 headings and 11 blank lines (25885 -> 26114 bytes)
architecture.md: OK  old == new minus 4 headings and 7 blank lines (9821 -> 9931 bytes)
INSERTION-ONLY: PASS  HEAD -> INDEX
```

Keep the three `OK` lines; Step 10 pastes them into the index. Any `FAIL` line stops the task: restore the docs (`git restore --staged --worktree -- docs/claude/backtest-methodology.md docs/claude/known-traps.md docs/claude/architecture.md`) and report what the line says. Never adjust `EXPECTED` or `BLANKS` to get a pass.

A reviewer re-runs the same check on the finished commit by pasting the same script with other arguments: `python - HEAD~1 HEAD <<'PY'`, with this task's commit at `HEAD`.

- [ ] **Step 7: Confirm the closed pre-registrations heading by eye**

```bash
git show :docs/claude/backtest-methodology.md | grep -n "^### "
git diff --cached -U0 -- docs/claude/backtest-methodology.md | grep -c "Closed pre-registrations"
```

Expected: the first prints exactly one line, `214:### Closed pre-registrations — do not re-run these` (197 before, plus the seventeen lines inserted above it). The second prints `0`: the heading is in no hunk of the diff.

- [ ] **Step 8: Run the pin test and watch it pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`

Expected: `VERDICT: PASS  40 passed`.

- [ ] **Step 9: Run the two tests that read the closed pre-registrations heading**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py tests/backtesting/test_preregistration_ledger_file.py`

Expected: `VERDICT: PASS`, nothing failed. A failure in `test_every_all_caps_knob_in_the_closed_table_is_in_the_constant` (guardrails) or anywhere in `test_preregistration_ledger_file.py` means a heading landed inside or after the closed table. That cannot happen when Step 6 passed, so re-run Step 6 before anything else.

- [ ] **Step 10: Record the results in the index**

In `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md`, under `## Results`, replace `_not yet run_` in these four rows. Use today's date and the figures the script printed in Step 6:

| Row (its `Check` cell) | New `Result` cell |
|---|---|
| Insertion-only check, `backtest-methodology.md` | `PASS <date>, HEAD -> INDEX: old == new minus 7 headings and 10 blank lines (<old> -> <new> bytes)` |
| Insertion-only check, `known-traps.md` | `PASS <date>, HEAD -> INDEX: old == new minus 6 headings and 11 blank lines (<old> -> <new> bytes)` |
| Insertion-only check, `architecture.md` | `PASS <date>, HEAD -> INDEX: old == new minus 4 headings and 7 blank lines (<old> -> <new> bytes)` |
| `tests/hooks/test_guardrails.py` and `tests/backtesting/test_preregistration_ledger_file.py` after insertion | `PASS <date>: <the VERDICT line of Step 9, verbatim>` |

`<date>`, `<old>`, `<new>` and the verdict line are the values you observed; none of the angle-bracket text stays in the file. Change nothing else in the index.

- [ ] **Step 11: Commit**

```bash
git add tests/hooks/test_doc_sections.py docs/claude/backtest-methodology.md docs/claude/known-traps.md docs/claude/architecture.md docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md
git status --short
git commit -m "docs(claude): section headings in three reference docs, by insertion only (V154-5)"
```

Before the commit, `git status --short` must show exactly those five paths staged (`A` for the test, `M` for the other four) and nothing else staged.

---

### Task V154-6: `scripts/dev/doc_section.py`

**Model:** sonnet — a small stdlib CLI with its behaviour fixed by contract C4, built test-first in one module.

**Files:**
- Create: `scripts/dev/doc_section.py`
- Create: `tests/dev/test_doc_section.py`

**Interfaces:**
- Consumes: nothing from another task. The tests build their docs under `tmp_path`, so this task does not need V154-5's headings. The one test that reads a real doc uses `### Closed pre-registrations — do not re-run these` in `docs/claude/backtest-methodology.md`, which is on `main` today.
- Produces: the CLI of index contract C4, which V154-7 points `CLAUDE.md` and `AGENTS.md` at and V154-8 writes into four skills:

```
python scripts/dev/doc_section.py <doc> [<heading> ...]
```

  - no heading: one line per `##`/`###` heading in doc order, `<bytes>  <heading line>`, size right-aligned, exit code 0;
  - headings: those sections in the order asked, one blank line apart, exit code 0. A heading argument is a case-insensitive prefix of the heading title. A section runs to the next heading of the same or a higher level, so `##` includes its `###` children;
  - exit code 2, everything on stdout: `doc_section: no heading starts with '<arg>'` or `doc_section: '<arg>' is ambiguous`, then the heading list, and no section text at all, even for arguments that did match; `doc_section: <doc> has no ## or ### headings -- read the file`; `doc_section: cannot read <doc>`.

Design notes the tests pin:

- Stdlib only. `scripts/dev/` has no `__init__.py`; the tests run the script as a subprocess, the pattern `tests/dev/test_plan_lint.py` uses.
- Only `##` and `###` lines outside fenced code blocks are headings. `#` and `####` lines are body text.
- A section's size is the UTF-8 length of its lines with one newline counted per line, CRLF read as LF, so the figure is the same on Windows and Linux.
- A printed section has its trailing blank lines removed; sections are joined by exactly one blank line and the output ends with one newline.
- Output is written as UTF-8 bytes, not through `print()`: the docs contain `−` and `—`, which a Windows console code page cannot encode.
- When several arguments fail, only the first failure's reason is printed (one reason line, then the list).

- [ ] **Step 1: Write the failing tests**

Create `tests/dev/test_doc_section.py`:

````python
"""doc_section prints named sections of a doc, and refuses rather than guess."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "doc_section.py"

DOC = """\
# Title

intro, before any section

## Alpha one

alpha body

### Alpha child

child body

## Beta — dash

beta body

```text
## not a heading
```

### Gamma

gamma body
#### deeper stays body

## alpha two

last body
"""


def _run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          cwd=ROOT, timeout=60)
    assert proc.stderr == b"", proc.stderr
    return proc.returncode, proc.stdout.decode("utf-8")


def _doc(tmp_path: Path, text: str = DOC) -> str:
    path = tmp_path / "doc.md"
    path.write_bytes(text.encode("utf-8"))
    return str(path)


def _between(start: str, end: str | None = None) -> str:
    """The slice of DOC from one heading line up to another (or to the end)."""
    stop = DOC.index(end) if end else len(DOC)
    return DOC[DOC.index(start):stop]


LISTING = [
    "## Alpha one",
    "### Alpha child",
    "## Beta — dash",
    "### Gamma",
    "## alpha two",
]


def test_no_heading_lists_every_heading_with_its_section_size(tmp_path):
    code, out = _run(_doc(tmp_path))
    sizes = [
        len(_between("## Alpha one", "## Beta").encode("utf-8")),
        len(_between("### Alpha child", "## Beta").encode("utf-8")),
        len(_between("## Beta", "## alpha two").encode("utf-8")),
        len(_between("### Gamma", "## alpha two").encode("utf-8")),
        len(_between("## alpha two").encode("utf-8")),
    ]
    width = len(str(max(sizes)))
    assert code == 0
    assert out.splitlines() == [f"{size:>{width}}  {line}"
                                for size, line in zip(sizes, LISTING)]


def test_listing_right_aligns_sizes_of_different_widths(tmp_path):
    text = "## Small\n\nx\n\n## Large\n\n" + "y" * 200 + "\n"
    code, out = _run(_doc(tmp_path, text))
    assert code == 0
    assert out.splitlines() == [" 13  ## Small", "211  ## Large"]


def test_heading_matches_by_case_insensitive_prefix(tmp_path):
    code, out = _run(_doc(tmp_path), "BETA")
    assert code == 0
    assert out == _between("## Beta", "## alpha two").rstrip() + "\n"


def test_h2_section_includes_its_h3_children(tmp_path):
    code, out = _run(_doc(tmp_path), "Alpha one")
    assert code == 0
    assert out == _between("## Alpha one", "## Beta").rstrip() + "\n"
    assert "### Alpha child" in out


def test_h3_section_is_addressable_and_stops_at_the_next_heading(tmp_path):
    code, out = _run(_doc(tmp_path), "gamma")
    assert code == 0
    assert out == "### Gamma\n\ngamma body\n#### deeper stays body\n"


def test_several_headings_print_in_the_order_asked_one_blank_line_apart(tmp_path):
    code, out = _run(_doc(tmp_path), "alpha two", "Alpha child")
    assert code == 0
    assert out == "## alpha two\n\nlast body\n\n### Alpha child\n\nchild body\n"


def test_ambiguous_heading_exits_2_with_the_heading_list_and_no_section(tmp_path):
    code, out = _run(_doc(tmp_path), "Beta", "alpha")
    lines = out.splitlines()
    assert code == 2
    assert lines[0] == "doc_section: 'alpha' is ambiguous"
    assert [line.split("  ", 1)[1] for line in lines[1:]] == LISTING
    assert "beta body" not in out


def test_missing_heading_exits_2_with_the_heading_list_and_no_section(tmp_path):
    code, out = _run(_doc(tmp_path), "Beta", "Delta")
    lines = out.splitlines()
    assert code == 2
    assert lines[0] == "doc_section: no heading starts with 'Delta'"
    assert [line.split("  ", 1)[1] for line in lines[1:]] == LISTING
    assert "beta body" not in out


def test_heading_inside_a_code_fence_is_not_a_heading(tmp_path):
    code, out = _run(_doc(tmp_path), "not a heading")
    assert code == 2
    assert out.splitlines()[0] == "doc_section: no heading starts with 'not a heading'"


def test_h1_and_h4_are_not_addressable(tmp_path):
    assert _run(_doc(tmp_path), "Title")[0] == 2
    assert _run(_doc(tmp_path), "deeper")[0] == 2


def test_doc_without_headings_exits_2_and_says_to_read_the_file(tmp_path):
    doc = _doc(tmp_path, "# Only a title\n\n- **bold bullet**, no sections\n")
    expected = f"doc_section: {doc} has no ## or ### headings -- read the file\n"
    assert _run(doc) == (2, expected)
    assert _run(doc, "bold") == (2, expected)


def test_missing_file_exits_2(tmp_path):
    doc = str(tmp_path / "absent.md")
    assert _run(doc, "Alpha") == (2, f"doc_section: cannot read {doc}\n")


def test_no_arguments_exits_2_with_usage():
    code, out = _run()
    assert code == 2
    assert out.startswith("doc_section: usage:")


def test_crlf_doc_prints_the_same_sections(tmp_path):
    doc = _doc(tmp_path, DOC.replace("\n", "\r\n"))
    code, out = _run(doc, "gamma")
    assert code == 0
    assert out == "### Gamma\n\ngamma body\n#### deeper stays body\n"


def test_real_doc_section_is_printed_from_its_heading_line():
    """The one case run against a real doc: a heading that predates v154 and
    that two other tests read, so it is safe to rely on here."""
    code, out = _run("docs/claude/backtest-methodology.md", "closed pre-registrations")
    assert code == 0
    assert out.splitlines()[0] == "### Closed pre-registrations — do not re-run these"
````

The `DOC` fixture contains a fenced block (three backticks, `text`) holding the line `## not a heading`; keep those three lines exactly, they are what `test_heading_inside_a_code_fence_is_not_a_heading` is about.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_doc_section.py`

Expected: `VERDICT: FAIL` with `15 failed`. Every test fails in `_run` on `assert proc.stderr == b""`, because Python reports `can't open file ... doc_section.py`. A failure for any other reason (an import error in the test module, a syntax error) is a mistake in Step 1; fix it before going on.

- [ ] **Step 3: Write the script**

Create `scripts/dev/doc_section.py`:

```python
"""Print named sections of a markdown doc instead of reading it whole.

    python scripts/dev/doc_section.py <doc> [<heading> ...]

No heading: one line per `##`/`###` heading, in doc order, as
`<bytes>  <heading line>` (the UTF-8 size of that heading's section).
With headings: those sections, in the order asked, one blank line apart.

A heading argument is a case-insensitive prefix of the heading title and must
select exactly one heading. A section runs to the next heading of the same or
a higher level, so a `##` section includes its `###` children. Lines inside
fenced code blocks are never headings.

Exit code 2, with a one-line reason on stdout (followed by the heading list
when there is one), when an argument selects no heading or several, when the
doc has no `##`/`###` heading, or when it cannot be read. The script never
prints a whole file and never prints nothing with exit code 0: on 2, read the
file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

USAGE = "doc_section: usage: python scripts/dev/doc_section.py <doc> [<heading> ...]"
HEADING_RE = re.compile(r"^(#{2,3}) (\S.*)$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


class Heading(NamedTuple):
    start: int  # index of the heading line
    end: int    # index one past the last line of its section
    title: str  # the text after the # marks
    line: str   # the heading line as written


def _heading_lines(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) of every ##/### line outside fenced code."""
    found, in_fence = [], False
    for index, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            found.append((index, len(match.group(1)), match.group(2).strip()))
    return found


def find_headings(lines: list[str]) -> list[Heading]:
    raw = _heading_lines(lines)
    headings = []
    for position, (start, level, title) in enumerate(raw):
        later = (index for index, other, _ in raw[position + 1:] if other <= level)
        headings.append(Heading(start, next(later, len(lines)), title, lines[start].rstrip()))
    return headings


def section_size(lines: list[str], heading: Heading) -> int:
    """UTF-8 bytes of the section, one newline counted per line."""
    return sum(len(line.encode("utf-8")) + 1 for line in lines[heading.start:heading.end])


def section_text(lines: list[str], heading: Heading) -> str:
    return "\n".join(lines[heading.start:heading.end]).rstrip()


def listing(lines: list[str], headings: list[Heading]) -> str:
    sizes = [section_size(lines, heading) for heading in headings]
    width = len(str(max(sizes)))
    return "\n".join(f"{size:>{width}}  {heading.line}"
                     for size, heading in zip(sizes, headings))


def resolve(headings: list[Heading], argument: str) -> Heading | str:
    """The one heading `argument` selects, or the reason there is not one."""
    wanted = argument.strip().lower()
    hits = [heading for heading in headings if heading.title.lower().startswith(wanted)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return f"doc_section: no heading starts with '{argument}'"
    return f"doc_section: '{argument}' is ambiguous"


def run(doc: str, arguments: list[str]) -> tuple[int, str]:
    """(exit code, text to print) for one invocation."""
    try:
        text = Path(doc).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 2, f"doc_section: cannot read {doc}"
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    headings = find_headings(lines)
    if not headings:
        return 2, f"doc_section: {doc} has no ## or ### headings -- read the file"
    if not arguments:
        return 0, listing(lines, headings)
    picked = [resolve(headings, argument) for argument in arguments]
    reasons = [item for item in picked if isinstance(item, str)]
    if reasons:
        return 2, reasons[0] + "\n" + listing(lines, headings)
    return 0, "\n\n".join(section_text(lines, heading) for heading in picked)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE)
        return 2
    code, text = run(argv[1], argv[2:])
    # Bytes, not print(): the docs hold characters a Windows console code page
    # cannot encode, and the output must not depend on the terminal.
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_doc_section.py`

Expected: `VERDICT: PASS  15 passed`.

- [ ] **Step 5: Check complexity**

Run: `python -m radon cc -s -n C scripts/dev/doc_section.py tests/dev/test_doc_section.py`

Expected: no output (nothing at rank C or worse; the highest function is `run`, rank B).

- [ ] **Step 6: Try it on a real doc**

```bash
python scripts/dev/doc_section.py docs/claude/known-traps.md | head -5
python scripts/dev/doc_section.py docs/claude/known-traps.md "the market_data cache" | head -3
python scripts/dev/doc_section.py docs/claude/edge-priorities.md "the"; echo "exit=$?"
```

Expected: the first prints heading lines of `known-traps.md`, each prefixed with a right-aligned byte count (which headings depends on whether V154-5 has landed; both are fine). The second prints `## The market_data cache never self-heals (v116 follow-up)` and the start of that section. The third prints `doc_section: 'the' is ambiguous`, then the heading list of `edge-priorities.md`, then `exit=2` (two of its headings start with "The").

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/doc_section.py tests/dev/test_doc_section.py
git commit -m "feat(dev): doc_section.py prints named sections of a doc (V154-6)"
```

---

### Task V154-7: Route the new tests from `docs/claude/` changes; point `CLAUDE.md` and `AGENTS.md` at `doc_section.py`

**Model:** haiku — one tuple row, three pinned expectations and two doc lines, every one of them given verbatim below.

**Files:**
- Modify: `scripts/dev/select_tests.py` (the `("docs/claude/", ...)` row of `DATA_READERS`)
- Modify: `tests/dev/test_select_tests.py` (`_with_readers`, one `parametrize` row, one test)
- Modify: `CLAUDE.md` (one line under `## Token discipline`)
- Modify: `AGENTS.md` (one bullet under `## Efficient repository navigation`)

**Interfaces:**
- Consumes: `tests/hooks/test_doc_sections.py` (created by V154-5) and `tests/dev/test_doc_section.py` plus `scripts/dev/doc_section.py` (created by V154-6). Both tasks must be committed before this one starts: `select_tests.py` widens to the full suite when a reader it names is missing from disk.
- Produces: `AGENTS.md` § Efficient repository navigation carries the `doc_section.py` bullet (index contract C6). After this task, `python scripts/dev/testrun.py changed` selects both new test files for any change under `docs/claude/`.

**`CLAUDE.md` and other setup files had uncommitted edits from another session when this plan was written**, so they may differ from what is quoted here by the time this task runs. Every edit below is anchored on quoted text, never on a line number. Find the anchor with `grep -n` first; if an anchor is missing or appears more than once, stop and report it rather than picking a place.

Two commits come out of this task: the test routing, then the two pointer lines (`CLAUDE.md` and its `AGENTS.md` mirror travel in one commit, per the Codex mirror rule).

- [ ] **Step 1: Confirm the two readers exist**

```bash
ls tests/hooks/test_doc_sections.py tests/dev/test_doc_section.py scripts/dev/doc_section.py
```

Expected: all three paths are listed. A missing one means V154-5 or V154-6 has not landed; stop.

- [ ] **Step 2: Update the three expectations in `tests/dev/test_select_tests.py`**

Edit 1, in `_with_readers` (find it with `grep -n "def _with_readers" tests/dev/test_select_tests.py`). The fixture tree must contain the two new readers, or the selector reports them missing and widens. Add `"tests/hooks/test_doc_sections.py"` and `"tests/dev/test_doc_section.py"` to the tuple in `_with_readers`, keeping every existing entry (if v149 merged, `test_readme_paths.py` and `test_complexity_gate.py` are there; never retype the tuple from this plan). Order inside the tuple does not matter (it only creates fixture files). As written when this plan was drafted, before any other plan touched it, the tuple was:

```python
    for rel in ("tests/hooks/test_guardrails.py", "tests/hooks/test_codex_mirror.py",
                "tests/hooks/test_role_skills.py",
                "tests/dev/test_testrun_ci_invocations.py"):
```

and the two new strings go in as their own lines, for example directly after `"tests/hooks/test_role_skills.py",`.

Edit 2, the last row of the `parametrize` list above `test_data_read_path_routes_to_its_readers` (find it with `grep -n '"docs/claude/backtest-methodology.md"' tests/dev/test_select_tests.py`). The selector returns its targets sorted. Replace:

```python
    ("docs/claude/backtest-methodology.md",
     ["tests/hooks/test_codex_mirror.py", "tests/hooks/test_guardrails.py",
      "tests/hooks/test_role_skills.py"]),
```

with:

```python
    ("docs/claude/backtest-methodology.md",
     ["tests/dev/test_doc_section.py", "tests/hooks/test_codex_mirror.py",
      "tests/hooks/test_doc_sections.py", "tests/hooks/test_guardrails.py",
      "tests/hooks/test_role_skills.py"]),
```

Edit 3, `test_targets_inside_a_selected_directory_are_collapsed`. `tests/hooks/` still swallows the four readers inside it, but the new reader under `tests/dev/` is outside that directory and stays in the result. Replace the whole test:

```python
def test_targets_inside_a_selected_directory_are_collapsed(sel, tmp_path):
    """tests/hooks/ plus tests/hooks/test_guardrails.py would hand pytest the
    same file twice; the directory already covers it."""
    result = sel.select(["AGENTS.md", "docs/claude/testing-cost.md"],
                        _with_readers(_repo(tmp_path)))
    assert (result.full, result.targets) == (False, ["tests/hooks/"])
```

with:

```python
def test_targets_inside_a_selected_directory_are_collapsed(sel, tmp_path):
    """tests/hooks/ plus tests/hooks/test_guardrails.py would hand pytest the
    same file twice; the directory already covers it. The docs/claude/ reader
    outside tests/hooks/ is not covered by it and stays."""
    result = sel.select(["AGENTS.md", "docs/claude/testing-cost.md"],
                        _with_readers(_repo(tmp_path)))
    assert (result.full, result.targets) == (
        False, ["tests/dev/test_doc_section.py", "tests/hooks/"])
```

- [ ] **Step 3: Run the two affected tests and watch them fail**

Run: `python -m pytest tests/dev/test_select_tests.py -q -k "data_read_path_routes or collapsed"`

Expected: `2 failed, 6 passed, 44 deselected` (the deselected count may differ if the file has gained tests). The two failures are `test_data_read_path_routes_to_its_readers[docs/claude/backtest-methodology.md-...]` and `test_targets_inside_a_selected_directory_are_collapsed`: the selector still returns the three old readers.

- [ ] **Step 4: Extend the `docs/claude/` row in `scripts/dev/select_tests.py`**

Find it with `grep -n '("docs/claude/"' scripts/dev/select_tests.py`. Replace the last comment line above the row and the row itself:

```python
    # skills-tools.md's roles table pins each reviewer model (test_role_skills).
    ("docs/claude/", ("tests/hooks/test_guardrails.py",
                      "tests/hooks/test_codex_mirror.py",
                      "tests/hooks/test_role_skills.py")),
```

with:

```python
    # skills-tools.md's roles table pins each reviewer model (test_role_skills);
    # three docs carry pinned section headings (test_doc_sections) that
    # doc_section.py prints, one of them from the real file (test_doc_section).
    ("docs/claude/", ("tests/hooks/test_guardrails.py",
                      "tests/hooks/test_codex_mirror.py",
                      "tests/hooks/test_role_skills.py",
                      "tests/hooks/test_doc_sections.py",
                      "tests/dev/test_doc_section.py")),
```

The two comment lines above it (`# backtest-methodology.md's closed table ...` and `# reference doc must be named in AGENTS.md ...`) stay as they are.

- [ ] **Step 5: Run the selector's tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`

Expected: `VERDICT: PASS`, nothing failed (52 tests when this part was written). If a test reports `result.full is True` with a reason like `% of test files selected`, do not touch `FULL_THRESHOLD`: stop and report the reason text.

- [ ] **Step 6: Commit the routing**

```bash
git add scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "test(dev): docs/claude changes select the doc-section tests (V154-7)"
```

- [ ] **Step 7: Re-count `CLAUDE.md` against its 200-line cap**

`CLAUDE.md` must stay under 200 lines, and this task adds exactly one. It was 183 lines when the spec was written, but another session has edited it since, so count it now:

```bash
wc -l CLAUDE.md
grep -c "^- \*\*Don't re-run the full suite to check a local change\*\*" CLAUDE.md
grep -c "doc_section" CLAUDE.md
```

Expected: a line count of **198 or less**, then `1` (the anchor exists once), then `0` (the pointer is not there yet).

- Line count 199 or more: **stop, do not add the line**. Report `BLOCKED: CLAUDE.md is at <n> lines; adding the doc_section.py pointer would reach the 200-line cap. Which content moves into docs/claude/ to make room?` Moving content out of `CLAUDE.md` is the partner's call, not this task's.
- Anchor count not 1, or the pointer already present: stop and report what you found.

- [ ] **Step 8: Add the one line to `CLAUDE.md`**

Under `## Token discipline (read first — this repo has context landmines)`, insert this single physical line (do not wrap it) directly above the bullet that starts `- **Don't re-run the full suite to check a local change**`:

```markdown
- **Read a `docs/claude/` file by section, not whole:** `python scripts/dev/doc_section.py <doc> [<heading> ...]` (no heading lists them; exit code 2 means read the file).
```

Then confirm:

```bash
wc -l CLAUDE.md
git diff --numstat -- CLAUDE.md
```

Expected: the count is exactly one more than in Step 7 and below 200. `git diff --numstat` shows this task's line as one added line; if the worktree was clean before, the row reads `1	0	CLAUDE.md`.

- [ ] **Step 9: Add the mirror bullet to `AGENTS.md`**

Find the anchor with `grep -n "^which modules live where\.$" AGENTS.md`; expected exactly one hit, under `## Efficient repository navigation` (confirm with `grep -n "^## Efficient repository navigation" AGENTS.md`: the hit is a few lines below it). That line ends the paragraph that starts `` `swingbot/core/` is eleven packages with no flat modules ``. Insert a blank line and this bullet after it, keeping one blank line between the bullet and the next paragraph (`Large or historical plans are context hazards ...`):

```markdown
- Read a `docs/claude/` file by section instead of whole where it has
  headings: `python scripts/dev/doc_section.py <doc> [<heading> ...]` prints
  the named `##`/`###` sections (a heading matches by case-insensitive
  prefix; with no heading it lists them with byte sizes). Exit code 2 means
  it could not pick a section: read the whole file.
```

Change nothing else in `AGENTS.md`. V154-9 has already added a paragraph to a different section (`## Skills: the same ones Claude uses`); leave it alone.

- [ ] **Step 10: Check the mirror and the hook tests**

```bash
python scripts/dev/sync_codex.py --check
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: `Codex mirror is current.` and `VERDICT: PASS`. `--check` writes nothing; do not run `sync_codex.py` without it in this task (no skill or agent changed).

- [ ] **Step 11: Commit the pointers**

```bash
git add CLAUDE.md AGENTS.md
git status --short
git commit -m "docs(claude): point at doc_section.py for reading docs/claude by section (V154-7)"
```

`git status --short` must show only `CLAUDE.md` and `AGENTS.md` staged. Use `git add` with those two paths only, never `git add -A`.

---

### Task V154-8: Four skills read their authority by section

**Model:** sonnet — skill text that decides what gets read before a backtest or an entry-signal edit; the wording is given, the care is in replacing exactly one block per file and keeping the mirror in step.

**Files:**
- Modify: `.claude/skills/backtest-gate/SKILL.md` (the `## Step 1` block only)
- Modify: `.claude/skills/pooled-numbers/SKILL.md` (the `## Step 1` block only)
- Modify: `.claude/skills/alert-surface/SKILL.md` (the `## Step 1` block only)
- Modify: `.claude/skills/no-lookahead/SKILL.md` (the `## Step 1` block only)
- Regenerated by `python scripts/dev/sync_codex.py`, staged with the same commit: `.agents/skills/backtest-gate/SKILL.md`, `.agents/skills/pooled-numbers/SKILL.md`, `.agents/skills/alert-surface/SKILL.md`, `.agents/skills/no-lookahead/SKILL.md`

**Interfaces:**
- Consumes: the heading names inserted by V154-5 (index contract C3) and the `doc_section.py` CLI created by V154-6 (contract C4). Both must be committed first. Also `tests/hooks/test_doc_sections.py` from V154-5: its last test, `test_every_doc_section_command_in_a_skill_names_real_headings`, reads the command lines this task writes.
- Produces: the final Step 1 text of the four skills, which V154-12 evaluates. The commands and the "whole file instead when" conditions are index contract C5, word for word.

**Rules for the new text.**

- Each skill keeps its `## Step 1 — Read the authority` heading (with the em dash) and everything from `## Step 2` on. Only the lines between those two headings change. The frontmatter is not touched here; V154-2 owns it.
- Each `doc_section.py` command stays on **one line** inside a `bash` fence, however long. The drift guard in `tests/hooks/test_doc_sections.py` reads commands line by line, and a wrapped command is one an agent may run half of.
- Each **`Whole file instead when:`** sentence stays on one line and uses the condition from contract C5 literally. It is a condition to match, not advice to weigh.
- No number that reads as a threshold (`tests/hooks/test_skill_shape.py::test_new_skills_restate_no_thresholds` scans the body): the text names sections, never values. "Exit code 2" and "more than one" are fine; a comparison sign followed by a number is not.
- Every skill stays at or under 80 lines. `backtest-gate` is the tight one: 74 lines before, 79 after.

- [ ] **Step 1: Confirm the prerequisites and see the drift guard find nothing yet**

```bash
ls scripts/dev/doc_section.py tests/hooks/test_doc_sections.py
python scripts/dev/doc_section.py docs/claude/architecture.md
wc -l .claude/skills/backtest-gate/SKILL.md .claude/skills/pooled-numbers/SKILL.md .claude/skills/alert-surface/SKILL.md .claude/skills/no-lookahead/SKILL.md
grep -c "doc_section" .claude/skills/*/SKILL.md | grep -v ":0$"
```

Expected: both files are listed. The second command lists four headings of `architecture.md` with byte counts, in this order: `## Module map`, `## Entry-signal single source`, `## NO-LOOKAHEAD`, `## Plan engine, registry and scan pipeline` (if it prints `has no ## or ### headings`, V154-5 has not landed; stop). The line counts are 74, 61, 54 and 65. The last command prints nothing: no skill calls `doc_section.py` yet, so the drift guard currently checks zero commands.

If a line count differs, another task changed that skill's length. Carry on, but re-check the 80-line cap in Step 6 against the real numbers rather than the ones quoted here.

- [ ] **Step 2: Rewrite Step 1 of `backtest-gate`**

In `.claude/skills/backtest-gate/SKILL.md`, find the block with `grep -n "^## Step" .claude/skills/backtest-gate/SKILL.md`. Replace everything from the `## Step 1 — Read the authority` line up to, but not including, the `## Step 2 — Is this shot already spent?` line. The block today:

```markdown
## Step 1 — Read the authority

`docs/claude/backtest-methodology.md`. Read it before anything else here — it
owns the six-clause acceptance gate, the four-stage funnel, the TRAIN/
VALIDATION windows, the frozen constants, and the closed pre-registration
table. This skill does not restate any of that; nothing here substitutes for
reading it.

```

becomes:

````markdown
## Step 1 — Read the authority

```bash
python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Acceptance gate" "Funnel stages" "Windows" "Frozen constants" "Closed pre-registrations"
```

Those sections own the six-clause acceptance gate, the four-stage funnel, the
TRAIN/VALIDATION windows, the frozen constants and the closed
pre-registration table.
**Whole file instead when:** the run is `--validation`, or a result is about to be called a pass or fail.
Exit code 2 from `doc_section.py` means read the whole file. This skill does
not restate any of that; nothing here substitutes for reading it.

````

(One blank line stays between the last sentence and `## Step 2`.) This skill still reads most of its doc: everything except badge scoring, the harvest gate and the tail. That is by design; the spec's saving comes from the other three.

- [ ] **Step 3: Rewrite Step 1 of `pooled-numbers`**

In `.claude/skills/pooled-numbers/SKILL.md`, replace from `## Step 1 — Read the authority` up to, but not including, `## Step 2 — Every pooled figure in a document is stale until re-derived`. The block today:

```markdown
## Step 1 — Read the authority

`docs/claude/edge-priorities.md` for what "pooled" means here and why
expectancy leads win rate. `docs/claude/backtest-methodology.md` for which
window a figure belongs to and how a badge tier is scored. This skill does
not restate either.

```

becomes:

````markdown
## Step 1 — Read the authority

`docs/claude/edge-priorities.md`, whole, for what "pooled" means here and why
expectancy leads win rate. Then which window a figure belongs to and how a
badge tier is scored:

```bash
python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Windows" "Badge scoring"
```

**Whole file instead when:** a badge tier is being assigned or changed.
Exit code 2 from `doc_section.py` means read the whole file. This skill does
not restate either.

````

`edge-priorities.md` is read whole on purpose (the spec says so); do not add a `doc_section.py` command for it.

- [ ] **Step 4: Rewrite Step 1 of `alert-surface`**

In `.claude/skills/alert-surface/SKILL.md`, replace from `## Step 1 — Read the authority` up to, but not including, `## Step 2 — An empty table is an answer`. The block today:

```markdown
## Step 1 — Read the authority

`docs/claude/known-traps.md`, in full -- it is the shortest path to not
breaking this area. This skill does not restate any of it; nothing here
substitutes for reading it.

```

becomes:

````markdown
## Step 1 — Read the authority

```bash
python scripts/dev/doc_section.py docs/claude/known-traps.md "Two OHLCV caches" "Full-history cache" "Legacy shims" "Measured-empty tables" "Scan parameter and replay gate parity" "The market_data cache never self-heals"
```

Those sections of `docs/claude/known-traps.md` are the shortest path to not
breaking this area.
**Whole file instead when:** editing `scan_embeds` or a legacy shim.
Exit code 2 from `doc_section.py` means read the whole file. This skill does
not restate any of it; nothing here substitutes for reading it.

````

- [ ] **Step 5: Rewrite Step 1 of `no-lookahead`**

In `.claude/skills/no-lookahead/SKILL.md`, replace from `## Step 1 — Read the authority` up to, but not including, `## Step 2 — Name the bar`. The block today:

```markdown
## Step 1 — Read the authority

`docs/claude/architecture.md` for the NO-LOOKAHEAD rule itself and the
entry-signal single source both the live scanner and the backtest read from.
Then `docs/claude/known-traps.md` for the two OHLCV caches, which is where a
lookahead bug usually enters — a feature computed against the wrong one sees
a bar it should not yet know about. This skill does not restate either.

```

becomes:

````markdown
## Step 1 — Read the authority

```bash
python scripts/dev/doc_section.py docs/claude/architecture.md "NO-LOOKAHEAD" "Entry-signal single source"
python scripts/dev/doc_section.py docs/claude/known-traps.md "Two OHLCV caches" "Full-history cache" "Scan parameter and replay gate parity"
```

The first prints the NO-LOOKAHEAD rule itself and the entry-signal single
source both the live scanner and the backtest read from. The second prints
the two OHLCV caches, which is where a lookahead bug usually enters — a
feature computed against the wrong one sees a bar it should not yet know
about.
**Whole file instead when:** a change crosses more than one `swingbot/core` package.
Exit code 2 from `doc_section.py` means read the whole file. This skill does
not restate either.

````

- [ ] **Step 6: Check the line budget and the literal conditions**

```bash
wc -l .claude/skills/backtest-gate/SKILL.md .claude/skills/pooled-numbers/SKILL.md .claude/skills/alert-surface/SKILL.md .claude/skills/no-lookahead/SKILL.md
grep -c -F '**Whole file instead when:** the run is `--validation`, or a result is about to be called a pass or fail.' .claude/skills/backtest-gate/SKILL.md
grep -c -F '**Whole file instead when:** a badge tier is being assigned or changed.' .claude/skills/pooled-numbers/SKILL.md
grep -c -F '**Whole file instead when:** editing `scan_embeds` or a legacy shim.' .claude/skills/alert-surface/SKILL.md
grep -c -F '**Whole file instead when:** a change crosses more than one `swingbot/core` package.' .claude/skills/no-lookahead/SKILL.md
grep -c -F 'Exit code 2 from `doc_section.py` means read the whole file.' .claude/skills/backtest-gate/SKILL.md .claude/skills/pooled-numbers/SKILL.md .claude/skills/alert-surface/SKILL.md .claude/skills/no-lookahead/SKILL.md
git diff --stat -- .claude/skills/
```

Expected: line counts 79, 68, 60 and 73, every one at or under 80. Each of the four condition greps prints `1`. The exit-code grep prints `:1` for all four files. `git diff --stat` lists exactly those four `SKILL.md` files.

- [ ] **Step 7: Run every command the skills now carry**

This uses the drift guard's own parser, so it also shows the guard is no longer checking an empty list:

```bash
python - <<'PY'
import subprocess
import sys

sys.path.insert(0, "tests/hooks")
from test_doc_sections import _skill_commands

commands = _skill_commands()
for skill, doc, arguments in commands:
    proc = subprocess.run(
        [sys.executable, "scripts/dev/doc_section.py", f"docs/claude/{doc}", *arguments],
        capture_output=True)
    print(f"{skill}: {doc}, {len(arguments)} headings -> exit {proc.returncode}, "
          f"{len(proc.stdout)} bytes")
print(f"{len(commands)} commands")
PY
```

Expected: five commands, every one `exit 0`. The byte counts below are from the docs as they were when this part was written and will drift as the docs grow; what matters is exit 0 and a non-trivial size:

```
alert-surface: known-traps.md, 6 headings -> exit 0, 9326 bytes
backtest-gate: backtest-methodology.md, 5 headings -> exit 0, 52226 bytes
no-lookahead: architecture.md, 2 headings -> exit 0, 752 bytes
no-lookahead: known-traps.md, 3 headings -> exit 0, 4991 bytes
pooled-numbers: backtest-methodology.md, 2 headings -> exit 0, 1407 bytes
5 commands
```

Fewer than five commands means a command was wrapped onto a second line or its quotes were changed; fix the skill text, not the parser. An `exit 2` means a heading argument is misspelled: compare it with contract C5.

- [ ] **Step 8: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py`

Expected last line: `Codex mirror is current.` Then `git status --short` shows the four `.claude/skills/*/SKILL.md` files and the four matching `.agents/skills/*/SKILL.md` files modified, and nothing else. If `sync_codex.py` rewrites other files, another skill commit is in flight: skill commits are serial (see the index's Parallelisation), so stop and let that one land first.

- [ ] **Step 9: Run the narrow tests**

Run: `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py tests/hooks/test_skill_shape.py tests/hooks/test_codex_mirror.py`

Expected: `VERDICT: PASS`, nothing failed. What each file is checking here: `test_doc_sections.py`, that every heading argument in the four skills selects exactly one heading; `test_skill_shape.py`, the 80-line budget, no restated thresholds and the untouched trigger tables; `test_codex_mirror.py`, that `.agents/skills/` matches a fresh render.

- [ ] **Step 10: Commit**

```bash
git add .claude/skills/backtest-gate/SKILL.md .claude/skills/pooled-numbers/SKILL.md .claude/skills/alert-surface/SKILL.md .claude/skills/no-lookahead/SKILL.md .agents/skills/backtest-gate/SKILL.md .agents/skills/pooled-numbers/SKILL.md .agents/skills/alert-surface/SKILL.md .agents/skills/no-lookahead/SKILL.md
git status --short
git commit -m "feat(skills): four skills read their authority by section through doc_section.py (V154-8)"
```

`git status --short` must show those eight paths staged and nothing else. The eval suites of these four skills are not run here: V154-12 runs them once every skill edit of the plan has landed.
