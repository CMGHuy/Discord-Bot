# v154 Skill layer repair and token cuts: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V154-3` or `grep -n "^### Task V154-3" -A 200 <part file>`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md`](../specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md)
**Brief:** `.superpowers/briefs/2026-10-10-v154-skill-layer-repair-token-cuts.md` (line numbers from `main` @ `4b9edabd`)

**Goal:** Make the six role skills that do not trigger load again, cap all nine role descriptions at 260 characters, let the four heaviest "read the authority" skill steps read `docs/claude/` by section instead of whole, switch off five unused plugins, and add two slash-only helper skills.

**Architecture:** One stdlib frontmatter parser (`scripts/dev/skill_frontmatter.py`) replaces the three lenient colon splitters and rejects what the real loader rejects, so a broken `description:` fails the suite instead of silently losing its trigger text. Three `docs/claude/` files gain `##` headings by pure insertion, a stdlib CLI (`scripts/dev/doc_section.py`) prints named sections, and four skills' Step 1 call it with a literal "whole file instead when" condition. Everything else is configuration and skill text, mirrored to Codex in the same commit as the change.

**Tech Stack:** Python 3.11 stdlib only (no PyYAML), pytest, Claude Code skills/agents frontmatter, `scripts/dev/sync_codex.py` for the Codex mirror.

## Global Constraints

- **No new dependency.** `skill_frontmatter.py` and `doc_section.py` are stdlib only; PyYAML is not in `requirements.txt` and does not enter it.
- **Frontmatter values stay strings.** `parse_frontmatter` never returns a bool or a list; the existing `== "true"` comparisons are untouched.
- **Headings by insertion only.** In `docs/claude/backtest-methodology.md`, `docs/claude/known-traps.md` and `docs/claude/architecture.md` no existing line changes, no bullet is promoted, no paragraph is cut. Deleting the inserted heading lines and their inserted blank lines reproduces the old file byte for byte.
- **`### Closed pre-registrations — do not re-run these` keeps its level and exact text** (`backtest-methodology.md:197` before insertion). No heading is inserted at or after that line, and no inserted heading contains the text `### Closed pre-registrations`.
- **`Stage −2` stays the bold bullet it is.** It is not promoted to a heading.
- **No wording of any gate, window, constant or closed pre-registration changes.** This plan sets no threshold and re-runs nothing.
- **No file is split or renamed.**
- **Role descriptions: at most 260 characters of parsed value** (the text inside the quotes), for all nine. A missed fire case in an eval suite is fixed by rewording within the cap, never by raising it. Roles stay model-invocable.
- **Skill bodies restate no thresholds.** `tests/hooks/test_skill_shape.py::test_new_skills_restate_no_thresholds` scans every skill body: name sections, never numbers. New skills stay at or under 80 lines.
- **New skills are slash-only:** `disable-model-invocation: true`, registered in `TIER_2`.
- **Every commit that touches a file under `.claude/skills/` or `.claude/agents/` runs `python scripts/dev/sync_codex.py` and stages `.agents/` and `.codex/` with it.** `AGENTS.md` gains its mirror text in the same commit as the change it mirrors (`doc_section.py` line, the names `` `result-digest` `` and `` `handoff` ``, the disabled-plugin list).
- **`CLAUDE.md` stays under 200 lines** (183 today); this plan adds exactly one line to it.
- **Plugin keys are read, never guessed.** The exact `name@marketplace` keys come from the installed plugin list; a key that cannot be found stops the task with a question.
- **`/result-digest` returns the script's output verbatim**, never paraphrases a figure, never says pass.
- Every Python function written or changed ends below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>`).
- Per-task verification is the narrow run: `python scripts/dev/testrun.py file <test>`. The full suite runs once, in V154-13. Green means `0 failed` and `0 xfailed`.
- Out of scope: forking `close-out`, panel-only roles, the superpowers SessionStart block, any research-integrity or attribution/market skill.

## Decisions fixed by this index

These fill gaps the spec leaves to the plan. Every part is written against them.

1. **Task id prefix `V154-`**, thirteen tasks, three parts.
2. **Heading names and positions** are the brief's § 3 tables, adopted unchanged (see the ledger row for V154-5). `known-traps.md` gets six preamble headings and `architecture.md` four, more than the spec's table names, because a section runs to the next heading and the unrelated bullets between the named topics must not fall inside them.
3. **The heading pin test is `tests/hooks/test_doc_sections.py`**; the helper's own tests are `tests/dev/test_skill_frontmatter.py`; the broken-frontmatter fixture is `tests/hooks/fixtures/broken_frontmatter_SKILL.md`.
4. **A `##` section includes its `###` children** in `doc_section.py`; a `###` is addressable on its own. So `"Closed pre-registrations"` prints only the closed table, and `"Evidence"` prints `:143` onward including it.
5. **`result-digest` joins `FORKED`** in `tests/hooks/test_skill_shape.py` as `"result-digest": "haiku"`, so the existing fork test covers its declared `context: fork` / `model: haiku`.
6. **The eval-suite re-run is one task (V154-12), run after every skill edit has landed**, covering the nine role suites and the four edited Tier 1/3 suites in one pass. It is manual, costs real credit, and is recorded under `## Results` below.
7. **Agent descriptions are quoted too** (all nine files under `.claude/agents/`), and the helper is strict for agents and skills alike; there is no `strict=` flag.
8. **Anchor on text, not line numbers.** The brief's line numbers are from `4b9edabd`; `CLAUDE.md`, `docs/claude/skills-tools.md` and `.claude/agents/plan-writer.md` had uncommitted edits from another session when this index was written (2026-10-10). Every task that edits one of them locates its anchor with `grep -n` on the quoted text first, and re-counts `CLAUDE.md` (`wc -l`) before adding its line.

## Parallelisation

Implemented in one worktree. The file sets below are what decide it.

- **Wave 1, mutually independent (disjoint files, no contract dependency):** V154-1, V154-5, V154-6, V154-9.
  - V154-6's tests build their docs under `tmp_path`, so it does not need V154-5's headings to exist.
- **Sequential edges, each with its reason:**
  - V154-1 → V154-2 → V154-3: V154-2 and V154-3 import `parse_frontmatter` / `quote_value` created by V154-1. V154-2 must precede V154-3 because the strict helper rejects today's unquoted descriptions; the test modules can only switch to it once every description is quoted.
  - V154-2 → V154-4: both edit the same `description:` lines of the nine role skills.
  - V154-3 → V154-4: V154-4's length pin reads the value through the helper wired into the test modules' `sys.path` pattern by V154-3.
  - V154-5 → V154-7: the `select_tests.py` row names `tests/hooks/test_doc_sections.py`, created by V154-5.
  - V154-6 → V154-7: the same row names `tests/dev/test_doc_section.py`, and the `CLAUDE.md` line points at `scripts/dev/doc_section.py`, both created by V154-6.
  - V154-5 → V154-8 and V154-6 → V154-8: the four skills' Step 1 call `doc_section.py` with heading names V154-5 inserts.
  - V154-3 → V154-10 → V154-11: new skills are written against the strict helper; both add to `TIER_2` in `tests/hooks/test_skill_shape.py` and to the same `AGENTS.md` paragraph.
  - V154-9 → V154-7 → V154-10: all three add text to `AGENTS.md` (different sections; serial to avoid a merge on one file).
  - **Every skill commit is serial:** V154-2, V154-4, V154-8, V154-10, V154-11 each run `sync_codex.py`, which rewrites `.agents/skills/`. They commit one at a time, in id order, even where their source edits do not overlap.
  - V154-12 after V154-4, V154-8, V154-10 and V154-11: it evaluates the skills as finally written, and a reword it makes is itself a skill commit.
  - V154-13 last: the single full-suite run.
- **Recommended order for a single implementer:** id order, V154-1 through V154-13.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-10-v154-skill-layer-repair-token-cuts_1-frontmatter-roles.md` | V154-1 .. V154-4 | Spec § 1 and § 2: strict frontmatter helper and fixture, quoting every skill and agent description, the three splitters replaced, nine role descriptions trimmed and pinned |
| 2 | `2026-10-10-v154-skill-layer-repair-token-cuts_2-doc-sections.md` | V154-5 .. V154-8 | Spec § 3: heading insertion with the insertion-only check and the pin test, `doc_section.py`, test selection and the `CLAUDE.md`/`AGENTS.md` pointer, the four skills' Step 1 |
| 3 | `2026-10-10-v154-skill-layer-repair-token-cuts_3-plugins-helpers-verification.md` | V154-9 .. V154-13 | Spec § 4 and § 5 and Testing: disabled plugins, `/result-digest`, `/handoff`, the manual eval re-run, the full suite |

## Task ledger

| Id | Title | Part | Model | Files created / modified | Creates for later tasks |
|---|---|---|---|---|---|
| V154-1 | Strict frontmatter helper and the broken-frontmatter fixture | 1 | sonnet | Create `scripts/dev/skill_frontmatter.py`, `tests/dev/test_skill_frontmatter.py`, `tests/hooks/fixtures/broken_frontmatter_SKILL.md` | `FrontmatterError`, `parse_frontmatter`, `quote_value` (contract C1) |
| V154-2 | Quote every skill and agent description; `sync_codex.py` parses and re-emits through the helper | 1 | sonnet | Modify 25 `.claude/skills/*/SKILL.md`, 9 `.claude/agents/*.md`, `scripts/dev/sync_codex.py`; regenerated `.agents/skills/**`, `.codex/agents/**` | Every `description:` is a double-quoted scalar; `sync_codex._split_frontmatter` keeps its name and return shape and delegates to `parse_frontmatter` |
| V154-3 | `test_skill_shape.py` and `test_agent_shape.py` read frontmatter through the helper | 1 | haiku | Modify `tests/hooks/test_skill_shape.py`, `tests/hooks/test_agent_shape.py` | `_read_skill(name)` and `_read_agent(name)` keep their names and `(meta, body)` shape; the `sys.path` pattern for importing `skill_frontmatter` from a test (contract C2) |
| V154-4 | Nine role descriptions at most 260 characters, pinned | 1 | opus | Modify the nine role `SKILL.md` files, `tests/hooks/test_role_skills.py`; regenerated `.agents/skills/**` | `MAX_ROLE_DESCRIPTION = 260` in `test_role_skills.py`; final role trigger text for V154-12 |
| V154-5 | Insert section headings in three `docs/claude/` files, with the insertion-only check and the pin test | 2 | sonnet | Modify `docs/claude/backtest-methodology.md`, `docs/claude/known-traps.md`, `docs/claude/architecture.md`; create `tests/hooks/test_doc_sections.py`; record in `## Results` | The seventeen heading names (contract C3) |
| V154-6 | `scripts/dev/doc_section.py` | 2 | sonnet | Create `scripts/dev/doc_section.py`, `tests/dev/test_doc_section.py` | The CLI (contract C4) |
| V154-7 | Route the new tests from `docs/claude/` changes; point `CLAUDE.md` and `AGENTS.md` at `doc_section.py` | 2 | haiku | Modify `scripts/dev/select_tests.py`, `tests/dev/test_select_tests.py`, `CLAUDE.md`, `AGENTS.md` | `AGENTS.md` § Efficient repository navigation carries the `doc_section.py` line |
| V154-8 | Four skills read their authority by section | 2 | sonnet | Modify `.claude/skills/backtest-gate/SKILL.md`, `.claude/skills/pooled-numbers/SKILL.md`, `.claude/skills/alert-surface/SKILL.md`, `.claude/skills/no-lookahead/SKILL.md`; regenerated `.agents/skills/**` | Final Step 1 text of the four skills for V154-12 |
| V154-9 | Disable five unused plugins | 3 | sonnet | Modify `.claude/settings.json`, `docs/claude/skills-tools.md`, `AGENTS.md`; record the keys in `## Results` | `AGENTS.md` § Skills carries the disabled-plugin list |
| V154-10 | `/result-digest` slash-only skill | 3 | sonnet | Create `.claude/skills/result-digest/SKILL.md`; modify `tests/hooks/test_skill_shape.py`, `AGENTS.md`; regenerated `.agents/skills/result-digest/**` | `"result-digest"` in `TIER_2` and `FORKED` |
| V154-11 | `/handoff` slash-only skill | 3 | sonnet | Create `.claude/skills/handoff/SKILL.md`; modify `tests/hooks/test_skill_shape.py`, `AGENTS.md`; regenerated `.agents/skills/handoff/**` | `"handoff"` in `TIER_2` |
| V154-12 | Manual eval re-run of thirteen skill suites and the fresh-session listing check | 3 | opus | Record in `## Results`; modify a role `SKILL.md` (and regenerate) only if a fire case is missed | Recorded eval verdicts |
| V154-13 | Full-suite verification | 3 | haiku | Record in `## Results` | The plan's green verdict |

## Cross-task contracts

### C1. `scripts/dev/skill_frontmatter.py` (created by V154-1)

```python
class FrontmatterError(ValueError):
    """Frontmatter the real skill/agent loader rejects or misreads."""

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ({key: value}, body) for a `---`-fenced markdown file."""

def quote_value(value: str) -> str:
    """Return `value` as a double-quoted scalar, `\\` and `"` escaped."""
```

- `\r\n` is normalised to `\n` first.
- Text that does not start with `---\n` returns `({}, text)`.
- An opening fence with no closing `\n---\n` raises `FrontmatterError`.
- `body` is everything after the closing fence line, exactly as `sync_codex._split_frontmatter` returns it today (`text[4:].partition("\n---\n")[2]`), so `.agents/skills/` stays byte-stable apart from the quoting.
- Every value is a `str`. A double-quoted value is returned without its quotes, with `\"` and `\\` unescaped. An unquoted value is returned stripped.
- A `- item` line under a key is folded into that key's value, joined with `", "` (what `_read_agent` does today). Inline `[a, b]` stays the literal string.
- Raises `FrontmatterError`, naming the 1-based frontmatter line, on: an unquoted value containing `: ` or ` #`; a quoted value with an unescaped inner `"` or with text after the closing quote; a non-blank line that is neither `key: value` nor a `- item` under a key.
- `quote_value(parse_frontmatter(...)[0]["description"])` round-trips: `parse_frontmatter` of `f'---\ndescription: {quote_value(v)}\n---\n'` gives back `v`.

### C2. Importing the helper

`scripts/dev/` has no `__init__.py`. `scripts/dev/sync_codex.py` (loaded by path in `tests/hooks/test_codex_mirror.py`) does `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))` before `import skill_frontmatter`. Test modules do the same with `Path(__file__).resolve().parents[2] / "scripts" / "dev"`, then `from skill_frontmatter import parse_frontmatter`.

### C3. Headings inserted by V154-5

`Insert before` is the line number in the file as it is on `main` before this plan. A heading goes in as `## <Heading>` followed by one blank line; where the original preceding line is not blank, one blank line is inserted before the heading as well.

| Doc | Insert before | Heading | Preceding line blank? |
|---|---|---|---|
| `backtest-methodology.md` | 6 | `## Windows` | yes |
| `backtest-methodology.md` | 11 | `## Acceptance gate` | no |
| `backtest-methodology.md` | 38 | `## Badge scoring` | yes |
| `backtest-methodology.md` | 53 | `## Funnel stages` | yes |
| `backtest-methodology.md` | 104 | `## Harvest gate` | yes |
| `backtest-methodology.md` | 138 | `## Frozen constants` | no |
| `backtest-methodology.md` | 143 | `## Evidence, registry and ledger` | no |
| `known-traps.md` | 7 | `## Two OHLCV caches` | yes |
| `known-traps.md` | 42 | `## Legacy shims and silent no-ops` | no |
| `known-traps.md` | 73 | `## Measured-empty tables` | no |
| `known-traps.md` | 83 | `## Re-exports, stale prices and plan closes` | no |
| `known-traps.md` | 124 | `## Full-history cache and the live scan read` | no |
| `known-traps.md` | 146 | `## Trade History, file sources and the write halt` | no |
| `architecture.md` | 6 | `## Module map` | yes |
| `architecture.md` | 66 | `## Entry-signal single source` | no |
| `architecture.md` | 72 | `## NO-LOOKAHEAD` | no |
| `architecture.md` | 76 | `## Plan engine, registry and scan pipeline` | no |

Existing headings the skills also address, untouched: `### Closed pre-registrations — do not re-run these` (`backtest-methodology.md`), `## Scan parameter and replay gate parity (v74)` and `## The market_data cache never self-heals (v116 follow-up)` (`known-traps.md`).

V154-5 re-verifies every "line that follows" against the brief's § 3 tables before inserting; a mismatch (the doc moved since `4b9edabd`) is resolved by anchoring on the following line's text, not the number.

### C4. `scripts/dev/doc_section.py` (created by V154-6)

```
python scripts/dev/doc_section.py <doc> [<heading> ...]
```

- Stdlib only. Reads `<doc>` as UTF-8. Only `##` and `###` lines outside fenced code blocks are headings.
- **No heading argument:** prints one line per heading, in doc order, as `<bytes>  <heading line>` (`<bytes>` is the UTF-8 size of that heading's section, right-aligned), exit 0.
- **One or more heading arguments:** prints those sections in the order requested, separated by one blank line, exit 0. A section runs from its heading line to the line before the next heading of the same or a higher level, so a `##` section includes its `###` children.
- **Matching:** case-insensitive prefix of the heading title (the text after the `#` marks and one space).
- **Exit 2**, with a one-line reason then the heading list, all on stdout, when a heading argument matches nothing (`doc_section: no heading starts with '<arg>'`) or more than one heading (`doc_section: '<arg>' is ambiguous`). Nothing of any section is printed in that case, even for arguments that did match.
- **Exit 2** with `doc_section: <doc> has no ## or ### headings -- read the file` for a heading-less doc, with or without heading arguments, and with `doc_section: cannot read <doc>` for a missing file. It never prints a whole file and never prints nothing with exit 0.

### C5. What each skill's Step 1 runs (written by V154-8)

| Skill | Command(s) | Whole file instead when (literal text in the skill) |
|---|---|---|
| `backtest-gate` | `python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Acceptance gate" "Funnel stages" "Windows" "Frozen constants" "Closed pre-registrations"` | the run is `--validation`, or a result is about to be called a pass or fail |
| `pooled-numbers` | read `docs/claude/edge-priorities.md` whole; `python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Windows" "Badge scoring"` | a badge tier is being assigned or changed |
| `alert-surface` | `python scripts/dev/doc_section.py docs/claude/known-traps.md "Two OHLCV caches" "Full-history cache" "Legacy shims" "Measured-empty tables" "Scan parameter and replay gate parity" "The market_data cache never self-heals"` | editing `scan_embeds` or a legacy shim |
| `no-lookahead` | `python scripts/dev/doc_section.py docs/claude/architecture.md "NO-LOOKAHEAD" "Entry-signal single source"`; `python scripts/dev/doc_section.py docs/claude/known-traps.md "Two OHLCV caches" "Full-history cache" "Scan parameter and replay gate parity"` | a change crosses more than one `swingbot/core` package |

Each Step 1 also says: exit code 2 from `doc_section.py` means read the whole file.

### C6. `AGENTS.md` additions (one owner each)

| Task | Section of `AGENTS.md` | Text added |
|---|---|---|
| V154-9 | end of `## Skills: the same ones Claude uses` | one paragraph listing the plugins disabled for this project |
| V154-7 | `## Efficient repository navigation` | one bullet naming `scripts/dev/doc_section.py <doc> [<heading> ...]` |
| V154-10 | the "Explicit-only rituals" paragraph in `## Skills: the same ones Claude uses` | `` `result-digest` `` with a one-clause gloss |
| V154-11 | the same paragraph | `` `handoff` `` with a one-clause gloss |

## Results

Filled in by the tasks named; nothing here is a threshold or a pass on its own.

| Check | Task | Result |
|---|---|---|
| Insertion-only check, `backtest-methodology.md` | V154-5 | _not yet run_ |
| Insertion-only check, `known-traps.md` | V154-5 | _not yet run_ |
| Insertion-only check, `architecture.md` | V154-5 | _not yet run_ |
| `tests/hooks/test_guardrails.py` and `tests/backtesting/test_preregistration_ledger_file.py` after insertion | V154-5 | _not yet run_ |
| Plugin keys read from the installed list (five) | V154-9 | _not yet run_ |
| Fresh session lists all nine role descriptions | V154-12 | _not yet run_ |
| Nine role eval suites | V154-12 | _not yet run_ |
| Four edited Tier 1/3 eval suites (`backtest-gate`, `pooled-numbers`, `alert-surface`, `no-lookahead`) | V154-12 | _not yet run_ |
| Full suite | V154-13 | _not yet run_ |
