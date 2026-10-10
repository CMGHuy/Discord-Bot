# v154 — Skill layer repair and token cuts: six roles that never trigger, and a 60 KB doc read whole

**Version:** ui 1.22.0 · bot 2.3.0 (at writing)
**Bump:** none (Claude/Codex tooling and `docs/claude/` only; no shipped code)
**Edge:** none (integrity) — it repairs how rules load and what they cost. It sets no threshold, re-runs nothing and changes no wording of any gate.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer
**Status:** spec written 2026-10-10; panel review pending; no plan yet.
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
   `known-traps.md` (26.3 KB, ten `##` sections it could be addressed by).
3. **Role descriptions are long.** The nine run 392–541 characters, and each
   repeats "or when the expert-reviewer agent is dispatched with role=X", which
   the agent does not need: it invokes the skill by name.
4. **Listing overhead from plugins this repo never uses.** `feature-dev`,
   `code-simplifier`, `claude-code-setup`, `claude-md-management` and a second
   copy of `skill-creator` each add skills and agents to every session and
   every subagent. `.claude/settings.json` already disables ten plugins the
   same way.
5. **`close-out` runs in the main context.** It is a mechanical ritual;
   `gate` and `task-brief` already run as `context: fork` on `model: sonnet`.

## Decisions taken in the brainstorm

- **Roles stay model-invocable** (partner, 2026-10-10). v145's decision stands:
  the six are repaired, and all nine descriptions are trimmed to at most 260
  characters. Panel-only roles were considered and rejected.
- **`backtest-methodology.md` stays one file.** `.claude/hooks/guardrails.py`
  reads the closed pre-registration table from it, and about forty code, test
  and doc references name the path. It gains `##` headings in place; nothing
  moves to another file.
- **Section reads go through a script, not a skill.** A forked Haiku skill
  would spend a model call to do what `sed` does.
- **New skills are slash-only** so they add nothing to the listing.

## Design

### 1. Frontmatter repair and the test that should have caught it

- Wrap every `description:` value in `.claude/skills/*/SKILL.md` in double
  quotes — all 25, not just the six, so the next inner colon is harmless.
- `_read_skill` parses frontmatter with `yaml.safe_load` (PyYAML 5.4.1 is
  already installed; add it to the dev requirements file if it is only there
  transitively). A skill whose frontmatter does not parse fails
  `test_every_skill_declares_name_and_description` by name.
- `tests/hooks/test_agent_shape.py` gets the same parser if it has the same
  splitter.
- `python scripts/dev/sync_codex.py` regenerates `.agents/skills/`; the mirror
  test must stay green.

### 2. Role descriptions at most 260 characters

Each keeps: the seat, the three to five things it checks, and its two
"Not for … (other-role)" hand-offs. Each drops the `expert-reviewer` clause.
A new assertion in `tests/hooks/test_role_skills.py` pins `len(description)
<= 260` for the nine roles.

The v145 eval suites (54 cases) are the regression check: re-run all nine with
`claude plugin eval .claude/skills/<role> --runs 1 --no-publish --trust-plugin
--ablation none`. A missed fire case is fixed by rewording within the cap,
never by raising it. This is the first run in which the six repaired roles are
graded against their real descriptions in a normal session, so failures here
are expected signal, not flake.

### 3. Addressable `docs/claude/` sections

- `backtest-methodology.md` gains `##` headings for the parts the skills name:
  the acceptance gate, the funnel stages (with Stage −2 keeping its exact
  current heading text, cited ten times as `§ Stage −2`), TRAIN/VALIDATION
  windows, frozen constants, and closed pre-registrations (heading text
  unchanged, cited nine times and parsed by `guardrails.py`). **Headings and
  blank lines are the only additions**; a paragraph may be cut at a sentence
  boundary to sit under its heading, with no word changed. The check is
  mechanical: the file with heading lines and blank lines removed, and all
  whitespace collapsed, is byte-identical before and after.
- New `scripts/dev/doc_section.py <doc> [<heading>]`: with no heading, prints
  the doc's headings with byte sizes; with one, prints that section (matching
  by case-insensitive prefix, exit 2 and the heading list on no match or an
  ambiguous match). `<doc>` resolves under `docs/claude/`. Stdlib only.
- The four skills' Step 1 changes from "read the file" to the named sections:

  | Skill | Reads |
  |---|---|
  | `backtest-gate` | acceptance gate, windows, closed pre-registrations; the rest on demand |
  | `pooled-numbers` | `edge-priorities.md` whole (5 KB); methodology: windows and badge scoring only |
  | `alert-surface` | the `known-traps.md` sections on caches, shims and measured-empty tables |
  | `no-lookahead` | `architecture.md` NO-LOOKAHEAD section; `known-traps.md` cache section |

  Each skill keeps its sentence that it restates nothing and that the doc is
  the authority; it adds that any doubt means reading the whole file.
- `CLAUDE.md` Token discipline gains one line pointing at `doc_section.py`;
  `AGENTS.md` mirrors it.

### 4. Listing overhead

- `.claude/settings.json` `enabledPlugins` gains `false` for `feature-dev`,
  `code-simplifier`, `claude-code-setup`, `claude-md-management` and the
  plugin-marketplace `skill-creator` (the `anthropic-skills` copy remains for
  skill work). `frontend-design`, `code-review`, `commit-commands` and
  `superpowers` stay.
- Whether the `anthropic-skills:*` set and unauthenticated connectors can be
  turned off per project is checked through the `claude-code-guide` agent; if
  they can, they are added here, and if not, the spec records that and stops.
- `docs/claude/skills-tools.md` "disabled plugins" list is updated to match.

### 5. Fork `close-out`; three slash-only helpers

- `close-out` gains `context: fork` and `model: sonnet`. It stays
  model-runnable (`MODEL_RUN_RITUALS`). Because a fork does not see the
  conversation, its Step 1 states what the caller must pass as arguments (plan
  path, results line) and stops with a one-line error when they are missing.
- `/result-digest <a.json> [<b.json>]` — fork, haiku. Runs
  `scripts/backtest/compare_backtest_json.py` (or reads one file) and returns
  at most eight lines: window, N, ExpR, win rate, per-strategy deltas. It
  states figures as read from the named file and never calls anything a pass;
  that remains `backtest-gate`'s job.
- `/handoff` — main context (it needs the conversation). Writes the plan's
  `## Handoff` block per `skills-tools.md` § Plan writing.
- All three carry `disable-model-invocation: true` except `close-out`, join
  `TIER_2`, and get Codex mirrors.

## Edge cases

- A description that itself contains a double quote: none today; the YAML test
  catches one if it appears.
- `guardrails.py` parsing the closed table: its tests
  (`tests/hooks/test_guardrails.py`) run unchanged; a failure means a heading
  was inserted inside the table.
- `doc_section.py` on a doc with no `##` headings prints the whole file with a
  one-line note, so a skill step never returns empty.
- A forked `close-out` invoked with no arguments must not guess the plan.

## Testing

- `test_skill_shape.py`: YAML parse for every skill; existing assertions kept.
- `test_role_skills.py`: 260-character cap.
- New `tests/dev/test_doc_section.py`: list mode, prefix match, ambiguous and
  missing heading, heading-less doc.
- New test pinning that `backtest-methodology.md` has the named `##` headings,
  including the two cited ones verbatim.
- `test_codex_mirror.py` green after `sync_codex.py`.
- Manual, recorded in the plan's results: a fresh session's listing shows all
  nine role descriptions; the nine role eval suites and the four edited
  Tier 1/3 suites pass.

## Parallelisation

- **Group A (sequential):** §1 then §2 — both edit the same nine frontmatter
  lines.
- **Group B (sequential):** §3 headings, then `doc_section.py`, then the four
  skill edits — each step consumes the previous one's output.
- **Group C (independent):** §4.
- **Group D (independent of A–C):** §5, except that it must land after §1
  because the new skills are written with quoted descriptions and the YAML test.
- `sync_codex.py` runs inside every commit that touches a skill; A, B and D
  therefore commit one at a time even where their edits do not overlap.

## Out of scope

- Making roles panel-only; removing the superpowers SessionStart block.
- Any change to the wording of a gate, a window, a constant or a closed
  pre-registration.
- Splitting other large `docs/claude/` files.
- The research-integrity skills and the attribution/market skills — separate
  specs, written after this one.
