# v154 — Skill layer repair and token cuts: six roles that never trigger, and a 60 KB doc read whole

**Version:** ui 1.22.0 · bot 2.3.0 (at writing)
**Bump:** none (Claude/Codex tooling and `docs/claude/` only; no shipped code)
**Edge:** none (integrity) — it repairs how rules load and what they cost. It sets no threshold, re-runs nothing and changes no wording of any gate.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer
**Status:** spec written 2026-10-10; panel review applied; no plan yet.
**Depends on:** nothing unbuilt. Builds on v96 (skills layer) and v145 (expert roles).

## Why

Measured on 2026-10-10 from a fresh main-tree session:

1. **Six of the nine v145 role skills do not trigger.** The session's skill
   listing shows `financial-advisor`, `quant-engineer`, `senior-engineer`,
   `staff-engineer`, `technical-analyst` and `veteran-trader` with the
   description `Financial advisor`, `Quant engineer`, … — the title-cased name,
   not the trigger text. Each of the six has an unquoted `description:` scalar
   containing an inner `: ` (`... is tradeable: fills, gaps ...`), which is not
   valid YAML. The three roles without an inner `: ` (`fundamental-analyst`,
   `quant-researcher`, `risk-manager`) list correctly. The suite stayed green
   because `_read_skill` in `tests/hooks/test_skill_shape.py:45` parses
   frontmatter with `line.split(":", 1)`, which accepts what the real loader
   rejects.
2. **The costliest load in the repo is one skill step.** `backtest-gate` and
   `pooled-numbers` open with "Step 1 — Read the authority":
   `docs/claude/backtest-methodology.md`, which is 59.8 KB in 256 lines with
   one `#` heading and one `###`. It cannot be read by section, so every fire
   pays for all of it. `alert-surface` and `no-lookahead` do the same with
   `known-traps.md` (26.3 KB), whose relevant rules are bold bullets in an
   unheaded preamble; `architecture.md` likewise has a single heading.
3. **Role descriptions are long.** The nine run 392–541 characters, and each
   repeats "or when the expert-reviewer agent is dispatched with role=X", which
   the agent does not need: it invokes the skill by name.
4. **Listing overhead from plugins this repo never uses.** `feature-dev`,
   `code-simplifier`, `claude-code-setup`, `claude-md-management` and a second
   copy of `skill-creator` each add skills and agents to every session and
   every subagent. `.claude/settings.json` already disables ten plugins the
   same way.

## Decisions taken in the brainstorm

- **Roles stay model-invocable** (partner, 2026-10-10). v145's decision stands:
  the six are repaired, and all nine descriptions are trimmed to at most 260
  characters. Panel-only roles were considered and rejected.
- **No file is split and no existing line changes.** About forty code, test
  and doc references name `backtest-methodology.md`, and
  `tests/hooks/test_guardrails.py:390` splits it on the literal
  `### Closed pre-registrations`. The three docs gain headings by insertion
  only.
- **No new dependency.** PyYAML is not in `requirements.txt`, which is the one
  file CI and the image install from; the frontmatter check is a strict rule in
  the existing parser instead.
- **Section reads go through a script, not a skill.**
- **New skills are slash-only** so they add nothing to the listing.

## Design

### 1. Frontmatter repair and one strict parser

- Wrap every `description:` value in `.claude/skills/*/SKILL.md` in double
  quotes — all 25, so the next inner colon is harmless.
- The colon splitter exists three times: `tests/hooks/test_skill_shape.py:45`,
  `scripts/dev/sync_codex.py:56,70` and `tests/hooks/test_codex_mirror.py:33`.
  It moves to one stdlib helper, `scripts/dev/skill_frontmatter.py`, imported
  by all three. Values stay strings, so the existing `== "true"` comparison at
  `test_skill_shape.py:110` is untouched.
- The helper raises on what the real loader rejects or misreads: an unquoted
  value containing `: ` or ` #`, a quoted value with an unescaped inner quote,
  and a line that is not `key: value`. `sync_codex.py` strips the quotes it now
  reads and re-emits them, so `.agents/skills/` stays byte-stable apart from
  the quoting.
- A regression fixture holds one of today's six broken frontmatters and
  asserts the helper rejects it.

### 2. Role descriptions at most 260 characters

Each keeps the seat, the three to five things it checks, and its two
"Not for … (other-role)" hand-offs, and drops the `expert-reviewer` clause.
`tests/hooks/test_role_skills.py` pins `len(description) <= 260` for the nine.

The v145 eval suites (54 cases) are the regression check: re-run all nine with
`claude plugin eval .claude/skills/<role> --runs 1 --no-publish --trust-plugin
--ablation none`. A missed fire case is fixed by rewording within the cap,
never by raising it.

### 3. Addressable `docs/claude/` sections

**Headings by insertion only.** `backtest-methodology.md`, `known-traps.md`
and `architecture.md` gain `##` heading lines (each followed by a blank line)
between existing lines. No bullet is promoted, no paragraph is cut, and the
existing `### Closed pre-registrations` keeps its level and text. `Stage −2`
stays the bold bullet it is at `backtest-methodology.md:53`; the ten
`§ Stage −2` citations keep pointing at it, now inside a funnel section. The
check is mechanical: deleting the inserted lines reproduces the old file byte
for byte.

Headings to insert (exact line positions are the plan's job):

| Doc | Sections |
|---|---|
| `backtest-methodology.md` | acceptance gate; badge scoring (`:32-38`); funnel stages (covers Stage −2 and the `measure_arms` rules, `:53-110`); windows; frozen constants; harvest gate |
| `known-traps.md` preamble | two OHLCV caches (`:7`, `:137`); silent no-op shims (`:56`); measured-empty tables (`:75`) |
| `architecture.md` | module map; NO-LOOKAHEAD (`:72`); entry-signal single source |

**`scripts/dev/doc_section.py <doc> [<heading> ...]`** — stdlib only. With no
heading it prints the doc's `##` and `###` headings with byte sizes; with one
or more it prints those sections. A heading matches by case-insensitive
prefix; no match or an ambiguous match exits 2 and prints the heading list. A
doc with no headings exits 2 and says to read the file — it never returns a
silent whole-file or empty result.

**What each skill's Step 1 reads:**

| Skill | Mandatory | Whole file instead when |
|---|---|---|
| `backtest-gate` | acceptance gate, funnel stages, windows, frozen constants, closed pre-registrations (everything but badge scoring, the harvest gate and the tail) | the run is `--validation`, or a result is about to be called a pass or fail |
| `pooled-numbers` | `edge-priorities.md` whole; methodology: windows, badge scoring | a badge tier is being assigned or changed |
| `alert-surface` | `known-traps.md`: the three preamble sections, replay parity (`:186`), market_data self-heal (`:351`) | editing `scan_embeds` or a legacy shim |
| `no-lookahead` | `architecture.md`: NO-LOOKAHEAD, entry-signal single source; `known-traps.md`: two caches, replay parity | a change crosses more than one `swingbot/core` package |

The third column is a literal condition in the skill text, not a judgement
call. `backtest-gate` therefore still reads most of its doc; the saving in
this section comes from the other three skills.

`CLAUDE.md` Token discipline gains one line pointing at `doc_section.py`.
`scripts/dev/select_tests.py:260` (the `docs/claude/` row) gains the heading
pin test and `tests/dev/test_doc_section.py`, so `testrun.py changed` selects
them.

### 4. Listing overhead

`.claude/settings.json` `enabledPlugins` gains `false` for `feature-dev`,
`code-simplifier`, `claude-code-setup`, `claude-md-management` and the
plugin-marketplace `skill-creator`. `frontend-design`, `code-review`,
`commit-commands` and `superpowers` stay. `anthropic-skills:*` and the
claude.ai connectors are not locally disableable
(`docs/claude/skills-tools.md:32-33`) and are untouched. The disabled-plugins
list in that doc is updated to match.

### 5. Two slash-only helpers

- `/result-digest <a.json> [<b.json>]` — `context: fork`, `model: haiku`.
  Runs `scripts/backtest/compare_backtest_json.py` and returns its output
  **verbatim**, prefixed with the file paths, the window and N, and ending with
  the fixed line "Derived by compare_backtest_json.py from the named files;
  not live-book figures — re-derive per pooled-numbers before quoting in a
  spec, plan or commit." It never paraphrases a figure and never says pass.
- `/handoff` — main context (it needs the conversation). Writes the plan's
  `## Handoff` block per `skills-tools.md` § Plan writing.
- Both carry `disable-model-invocation: true` and join `TIER_2`.

### Codex mirror

Each commit that touches a skill runs `sync_codex.py`. `AGENTS.md` gains, in
the same commit as the change it mirrors: the `doc_section.py` line, the two
new skills, and the disabled-plugin list. `sync_codex.py:66-68` drops
`context` and `model`, so Codex runs `/result-digest` unforked; that is
accepted and stated in `AGENTS.md`.

## Edge cases

- `test_guardrails.py:390` keeps splitting on `### Closed pre-registrations`;
  a failure means a heading was inserted inside that section's table.
- A description containing a double quote: none today; the helper rejects an
  unescaped one.
- `/result-digest` given a file `compare_backtest_json.py` cannot read returns
  the script's error verbatim and no figures.

## Testing

- `test_skill_shape.py` and `test_codex_mirror.py` through the shared helper;
  the broken-frontmatter fixture; existing assertions unchanged.
- `test_role_skills.py`: the 260-character cap.
- New `tests/dev/test_doc_section.py`: list mode, prefix match, several
  headings, ambiguous, missing, heading-less doc.
- New heading pin test: each doc carries the sections in the table above and
  `backtest-methodology.md` still contains `### Closed pre-registrations`.
- Insertion-only check, run once in the plan and recorded: old file equals new
  file minus inserted lines, for all three docs.
- Manual, recorded in the plan's results: a fresh session lists all nine role
  descriptions; the nine role suites and the four edited Tier 1/3 suites pass.

## Parallelisation

- **Group A (sequential):** §1 then §2 — both edit the same frontmatter lines.
- **Group B (sequential):** §3 headings, then `doc_section.py`, then the four
  skill edits — each consumes the previous step's output.
- **Group C (independent):** §4.
- **Group D:** §5, after §1 because new skills are written against the strict
  helper.
- `sync_codex.py` rewrites `.agents/skills/` in every skill commit, so A, B
  and D commit one at a time even where their edits do not overlap.

## Out of scope

- Forking `close-out` (see Panel review); making roles panel-only; removing
  the superpowers SessionStart block.
- Any change to the wording of a gate, window, constant or closed
  pre-registration.
- The research-integrity and attribution/market skills — separate specs.

## Panel review

Run 2026-10-10 on `558bfed0`. staff-engineer returned eight ADVISORY;
quant-engineer three BLOCKING and three ADVISORY.

- quant-engineer: BLOCKING — `backtest-gate` needs funnel stages and frozen constants, not "on demand" — applied (§3 table).
- quant-engineer: BLOCKING — `architecture.md` has no NO-LOOKAHEAD section to address — applied (headings inserted there too).
- quant-engineer: BLOCKING — the `known-traps.md` rules the skills need sit in an unheaded preamble — applied (preamble headings; replay parity and self-heal named).
- staff-engineer: `guardrails.py` does not parse the doc; `test_guardrails.py:390` splits on the `###` heading — applied (heading level and text kept).
- staff-engineer: Stage −2 is a bold bullet, so the byte-identity check conflicted with the design — applied (insertion only).
- staff-engineer: `yaml.safe_load` returns booleans and leaves two other splitters behind — applied (one shared strict helper, strings kept).
- staff-engineer: a forked `close-out` would dispatch `/panel` from a subagent and lose the judgement in steps 5 and 7 — applied (fork dropped).
- staff-engineer: PyYAML is undeclared and would enter the image — applied (no dependency).
- staff-engineer: `select_tests.py:260` needs rows for the new tests — applied.
- staff-engineer: the `anthropic-skills` question is already answered at `skills-tools.md:32-33` — applied.
- staff-engineer: `AGENTS.md` mentions and the dropped `context`/`model` keys — applied (Codex mirror section).
- quant-engineer: name where the badge-scoring heading goes — applied (`:32-38`).
- quant-engineer: `/result-digest` figures are derived and a small model paraphrases — applied (verbatim output, fixed disclaimer).
- quant-engineer: "any doubt" is judgement; give a literal stop condition — applied (third column; a heading-less doc exits 2).
