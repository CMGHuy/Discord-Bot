# v213 — Skills alignment: citation lint, drift fixes, seat coverage, ux-designer seat (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V213-7:" -A 300 docs/superpowers/plans/2026-11-06-v213-skills-alignment_2-*.md`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v213 — Skills alignment: citation lint, drift fixes, seat coverage, ux-designer seat](../specs/2026-11-06-v213-skills-alignment.md)
**Brief:** `.superpowers/briefs/2026-11-06-v213-skills-alignment.md`
**Worktree:** implement V213-1..V213-13 in `.claude/worktrees/2026-11-06-v213-skills-alignment` (branch of the same name, created in V213-1's first step; `docs/claude/document-lifecycle.md`). V213-14 is the controller's pre-close-out panel, merge, CI watch and `/close-out`.

## Goal

The repo's skills and agents are how every brief, implementation and review
learns where the code lives. On 2026-11-06 an audit of ten skills found them
citing code that has moved (`task-brief` and `senior-engineer` route wiring
checks to a facade and to a module that is now a package), counting two
containers where there are three, and running the full suite locally, which
root `CLAUDE.md` forbids. Nothing caught it, because no test reads what a
skill cites. The same audit found whole risk areas no review seat owns:
shorts, the eToro demo stage, the live-book gap, and the admin UI on a phone.

Once shipped, `tests/hooks/test_skill_citations.py` fails CI whenever a
backticked path in a skill, agent or eval prompt is not a tracked file, an
UPPER_SNAKE config name appears nowhere in the Python, or a `doc.md § Heading`
citation names a heading the doc does not have. Deliberate mentions of removed
or uncommitted things sit in a reviewed allowlist, and a dead allowlist line
fails too. `task-brief`, `senior-engineer`, `staff-engineer`, `gate` and three
agents point at today's code; `gate` becomes the pre-push gate (complexity
gate, `testrun.py changed`, frontend specs, scoped commits, then a CI watch).
All nine role seats share one canonical boundary paragraph pinned whole, eight
seats gain the missing checklist items inside the existing 15-item cap, and a
tenth seat, `ux-designer`, reviews screens and embeds at the three widths.

How it works: the scanner is a pure module (`scan(root, files, tracked,
code_text)`) unit tested on `tmp_path` fixtures; the repo-wide case wires it to
`git ls-files` and lands in the same commit as the last drift fix, so no push
carries a red `tests/hooks/` job. Cross-cutting checklist items open with a
shared lead (`Shorts:`, `eToro:`) that a test pins, so `/panel` can merge the
same concern raised from several seats.

What it leaves alone: the bot, the admin UI and every store behave
identically; nothing under `swingbot/` or `frontend/` changes; `task-brief`'s
handoff mechanics, the four-section role shape, the 8-15 checklist cap and the
80-line skill budget stay. What the lint cannot see (facades, bare filenames,
function names, drifted `file:line`, fenced commands) stays with `/close-out`
Step 5b. Success is measured by the repo-wide case passing on `main` with an
allowlist whose every line still matches a finding, and by the next panels
raising shorts, eToro and UI findings from a named seat.

## Architecture

- **Part A — scanner** (V213-1, V213-2): `scripts/dev/skill_citations.py`, a
  pure module with three rules (paths, config names, doc sections), an
  allowlist reader, repo helpers and a CLI (`python scripts/dev/skill_citations.py`
  prints the repo report, exit 1 on any line). Unit cases in
  `tests/hooks/test_skill_citations.py` (suite `dev-setup`, which already holds
  `tests/hooks/`; no `suites.toml` edit).
- **Part B — drift** (V213-3..V213-6): V213-3 first runs the CLI and records
  the red list (the spec's local red proof), then fixes `task-brief`; V213-4
  rewrites `gate` and adds its structural test; V213-5 fixes `senior-engineer`,
  `staff-engineer` and the radon wording in three agents; V213-6 clears every
  remaining finding (fix or allowlist line) and adds the repo-wide case.
- **Part C — seats** (V213-7..V213-11): canonical boundary and lead tests,
  then two seats per task, each with its trigger line and one new eval folder.
- **Part D — ux-designer** (V213-12, V213-13): the seat and every wiring point
  in one commit; then the `/panel` seat-picking table.
- **V213-14** — `/panel staff-engineer,senior-engineer` over `main...<branch>`,
  merge, CI watch, `/close-out` including Step 5b.

**Scanner contract details the spec leaves open (decided here; see OPEN):**

- A **paragraph** for the doc-section rule is a run of consecutive non-blank,
  non-fenced lines, and **a line whose stripped text starts with `- ` begins a
  new paragraph** (a Markdown list item is its own block). Without this, the
  pinned `[^`]+` cite runs across every bullet of a checklist, and correct
  citations fail (index-time dry run: 12 heading findings without the
  boundary, 6 real ones with it).
- Finding **tokens**: a path or config finding's token is the stripped word; a
  `missing doc` token is the doc as written; a `missing heading` token is
  `<doc> § <cite>` with `cite` as stripped. The finding's `line` is the line
  the word sits on (paths, names) or the paragraph's first line (sections).
- The allowlist's third field is the human reason; matching uses `skill` and
  `token` only, exactly.

**Tech stack:** Python 3.11 stdlib (`re`, `pathlib`, `subprocess`,
`dataclasses`), pytest, Markdown skills.

## Global Constraints

- **No running code changes.** The diff may touch only `.claude/skills/**`, `.claude/agents/**`, the files `python scripts/dev/sync_codex.py` writes (`.agents/**` and any Codex agent files it generates), `AGENTS.md`, `docs/claude/{skills-tools,persona,testing-cost,document-lifecycle}.md`, `scripts/dev/skill_citations.py`, `tests/hooks/**`, and the spec (V213-14 only). Anything under `swingbot/`, `frontend/`, `bot.py` or `admin_ui.py` is a review stop.
- **Codex mirror in the same commit.** Every commit that changes a skill, an agent or a `docs/claude/` rule runs `python scripts/dev/sync_codex.py`, updates `AGENTS.md` where it mirrors that text, and runs `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` green (`docs/claude/working-conventions.md` § Codex mirror).
- **Narrow runs only.** Each task runs `python scripts/dev/testrun.py file <test>` on what it touched; `tests/hooks/test_skill_shape.py` and `tests/hooks/test_codex_mirror.py` stay green after every commit. **From V213-6 on, every task also runs `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`.** No task runs the full suite; CI does.
- **Skill budgets (unchanged, never raised).** Every non-grandfathered skill at most 80 lines; 8 to 15 `- ` items under `## Checklist`; no bare threshold matching `_THRESHOLD_RE` in `tests/hooks/test_skill_shape.py` (write numbers as words or cite the doc that holds them); a role description is a double-quoted scalar of at most 260 characters containing "the <role> seat", "Not for" and a `(other-role)` hand-off. `gate` and `task-brief` stay grandfathered; `gate` keeps `disable-model-invocation: true`.
- **New prose passes the lint.** A backticked path is a tracked file (resolution: repo root, then `swingbot/`, then `swingbot/core/`; exactly one candidate); an UPPER_SNAKE word exists in tracked `*.py` under `swingbot/`, `scripts/` or `tests/`; a `doc.md § X` citation starts with the doc's full heading text (or is a prefix of it); a bare doc name resolves from `docs/claude/`, so never write `` `CLAUDE.md` § `` (say "root `CLAUDE.md`" without `§`). A new file is `git add`ed before the repo-wide case runs (untracked files read as missing).
- **Canonical boundary paragraph** (V213-7 pins it; V213-12 copies it), wrapped exactly as below, directly under each role skill's `# Title` line and one blank line:

  ```
  You are one seat on a review panel. You raise findings; you never decide, and
  you never lower a gate (`docs/claude/persona.md`). No seat's intuition
  overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
  pre-registration, and you quote no pooled figure you did not re-derive. Every
  finding cites `file:line`, a git range or a doc section, and is tagged
  `BLOCKING` (it matches a red flag below) or `ADVISORY`.
  ```
- **Shared leads, exact copy.** A shorts item starts `- Shorts: long plans stay byte-identical; ` and an eToro item starts ``- eToro: demo only, never `account: real`; `` followed by the seat's own angle and a full stop. One claim per bullet.
- **Live counts only.** "nine" becomes "ten" in `docs/claude/skills-tools.md` § Expert roles (v145) (the "Nine role skills" sentence), `.claude/agents/expert-reviewer.md` (description and the `UNKNOWN ROLE` verdict line), `docs/claude/persona.md`, the `tests/hooks/test_role_skills.py` docstring and the `EXPERT_ROLES` comment in `tests/hooks/test_agent_shape.py` — never in dated results (`skills-tools.md` "v145 role suites, 2026-10-09: 54/54 cases pass across the nine role" and "Measured over nine plan-writer runs").
- **Evals are written, never run** (running them is billed). Each eval is `prompt.md` (frontmatter `max_turns: 4`, `allowed_tools: [Read, Glob, Grep, Skill]`) plus `graders/skill-fired.md` (`type: tool_used`, `tool: Skill`, `input_match: <role>`, `min: 1` for `fire-*`; `min: 0` and `max: 0` for `no-fire-*`), shape as brief §7. An eval prompt cites no hypothetical path or config name (it would need an allowlist line).
- **Demo only.** No text anywhere suggests an `account: real` path.
- **Commits.** Several scoped commits; `git add <explicit paths>`; end each message with the session's attribution line. The controller commits plan documents on `main`.

## OPEN (decisions the controller should check)

- The list-item paragraph boundary and the finding-token shapes (Architecture) fill a gap in spec § A; without them the pinned regex fails correct checklist citations.
- V213-4 also rewords the live "pre-commit gate" descriptions of `/gate` in `AGENTS.md`, `docs/claude/skills-tools.md` and `docs/claude/document-lifecycle.md` (the Repo tooling lines), and `docs/claude/testing-cost.md` ("`/gate` and a plan's final verification task still run everything" becomes CI) — the same drift, not named in the spec.
- V213-7 adds one `/panel` line: findings opening with the same lead (`Shorts:`, `eToro:`) from several seats merge into one row (the spec's "so `/panel` can merge them", and its Order note that C edits `/panel`).

## Index-time dry run (tree `affc831f`)

A throwaway re-implementation of the three rules (with the list-item
boundary) found **40 findings**. V213-3 re-runs the real CLI and records the
true list; V213-6 ends with none left.

| Disposition | Findings | Task |
|---|---|---|
| fix | `task-brief:73` `swingbot/commands/scanning.py` | V213-3 |
| fix | `gate:55` `tests/test_edge_gates.py` | V213-4 |
| fix | `senior-engineer:27` `swingbot/commands/scanning.py` | V213-5 |
| fix | `quant-researcher:31` bare `instrument/stats.py` (spell `swingbot/core/backtesting/instrument/stats.py`); `quant-researcher:26` `backtest-methodology.md § Stage −2` (not a heading: a bullet under `## Funnel stages`); `quant-researcher:27` and `technical-analyst:30` `§ Closed pre-registrations …` (heading `### Closed pre-registrations — do not re-run these`); `panel:10` and `handoff:9` `skills-tools.md § Expert roles …` / `§ Plan writing, …` (headings `## Expert roles (v145)`, `### Plan writing (two phases)`); agent `plan-writer:67` `document-conventions.md § The plan's Goal section)` (heading `## The plan's Goal section explains, it does not label`) | V213-6 |
| allowlist | `scripts/ops/ssh-hetzner.sh` (uncommitted by design) in agent `prod-inspector` and skills `backup-pull`, `replicate-prod-db`, `stable-snapshot`, `trade-scout` | V213-6 |
| allowlist | deleted shims `core/scan_engine.py`, `core/scan_embeds.py`, `core/confidence.py`, `core/regime.py`, `core/trade_plan.py` in agent `symbol-verifier` (all five), skill `alert-surface` (`core/scan_embeds.py`, `core/scan_engine.py`), skill `task-brief` 3e (all five) | V213-6 |
| allowlist | vendored `etoro-public-api-operations`: `~/.claude.json`, `~/.cursor/mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `~/.codeium/windsurf/mcp_config.json` | V213-6 |
| allowlist | eval hypotheticals: `edge-module` `swingbot/core/edge/vwap_reclaim.py`; `replicate-prod-db` `tests/charts/test_render.py`; `mirror-prod` `SCAN_INTERVAL_SECONDS`; `no-lookahead` `SCAN_INTERVAL_SECONDS` and `SCAN_INTERVAL_SECS`; runtime path `stable-snapshot` `backups/deploys.jsonl` | V213-6 |

## Parallelisation

In practice one implementer runs at a time (partner preference); the edges
below say what would be unsafe anyway.

- V213-1 → V213-2: same two files.
- V213-2 → V213-3: V213-3's first step runs the CLI for the red proof, which must precede every Part B fix.
- V213-3 → V213-4 and V213-5: the red proof comes first. **V213-4 ∥ V213-5** is safe: disjoint skill and agent files, only V213-4 edits `AGENTS.md`, and `sync_codex.py` regenerates each generated file from its own source.
- V213-4 and V213-5 → V213-6: the repo-wide case is green only after every fix.
- V213-6 → V213-7: both edit `quant-researcher`, `technical-analyst` and `panel`.
- V213-7 → V213-8 → V213-9 → V213-10 → V213-11: each adds rows to `CROSS_CUTTING` in `tests/hooks/test_role_skills.py`, which V213-7 creates with the boundary pin.
- V213-11 → V213-12: `test_role_skills.py` (`ROLES`), `test_skill_shape.py`, `AGENTS.md`.
- V213-12 → V213-13: the `/panel` table names `ux-designer`, which must exist.
- V213-13 → V213-14: the panel reviews the whole branch.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V213-1 | Citation scanner core: scan set, tokens, path rule, allowlist, output format | 1 | sonnet | C `scripts/dev/skill_citations.py`; C `tests/hooks/test_skill_citations.py` | `@dataclass(frozen=True) Finding(file: str, line: int, token: str, reason: str)` with `format() -> str` = `f"{file}:{line}: {token} -- {reason}"` (file repo-relative, forward slashes); `scan(root: Path, files: list[Path], tracked: set[str], code_text: str) -> list[Finding]` (path rule in this task; every finding, file order then line order); `scan_set(root: Path, tracked: set[str]) -> list[Path]` (tracked `.claude/skills/*/SKILL.md`, `.claude/agents/*.md`, `.claude/skills/*/evals/*/prompt.md`, sorted); `prose_lines(lines: list[str]) -> Iterator[tuple[int, str]]` (1-based; fence lines and fenced lines skipped); `span_words(line: str) -> list[str]` (stripped words, templates dropped); `REASON_MISSING = "missing"`, `REASON_AMBIGUOUS = "ambiguous"`; `@dataclass(frozen=True) AllowEntry(skill: str, token: str, reason: str, line: int)`; `load_allowlist(path: Path) -> list[AllowEntry]` (missing file gives `[]`); `skill_of(rel: str) -> str` (skill folder, or agent file stem); `apply_allowlist(findings: list[Finding], entries: list[AllowEntry]) -> tuple[list[Finding], list[AllowEntry]]` (remaining, dead) |
| V213-2 | Config-name and doc-section rules, repo helpers, CLI | 1 | sonnet | M `scripts/dev/skill_citations.py`; M `tests/hooks/test_skill_citations.py`; C `tests/hooks/skill_citation_allowlist.txt` (comment header only) | `REASON_UNKNOWN_NAME = "unknown name"`, `REASON_MISSING_DOC = "missing doc"`, `REASON_MISSING_HEADING = "missing heading"`; `doc_headings(text: str) -> list[str]` (`##` to `####` lines outside fences, `#`s stripped, lower-cased); `tracked_paths(root: Path) -> set[str]` (`git ls-files`, cwd=root); `read_code_text(root: Path, tracked: set[str]) -> str`; `ALLOWLIST_REL = "tests/hooks/skill_citation_allowlist.txt"`; `repo_report(root: Path) -> list[str]` (remaining findings formatted, then each dead line as `tests/hooks/skill_citation_allowlist.txt:<n>: <skill>\|<token> -- dead allowlist line`); `main(argv: list[str] \| None = None) -> int` (`--root`, default the repo root; prints the report; exit 1 when non-empty, else 0) |
| V213-3 | Red proof, then `task-brief` drift (intro, 3a, 3b/3c, 3g, new 3i-3l, Bash for step 4) | 1 | sonnet | M `.claude/skills/task-brief/SKILL.md`; sync_codex outputs | Red list (count and lines) recorded in the commit message body; 3e's deleted-shim list stays verbatim (allowlisted in V213-6) |
| V213-4 | `gate` becomes the pre-push gate, with a structural gate test | 1 | sonnet | M `.claude/skills/gate/SKILL.md`; C `tests/hooks/test_gate_skill.py`; M `AGENTS.md` (`gate` description); M `docs/claude/skills-tools.md` (Repo tooling line); M `docs/claude/document-lifecycle.md` (Repo tooling line); M `docs/claude/testing-cost.md` (inner-loop paragraph); sync_codex outputs | Seven headings `## Step 1 — …` to `## Step 7 — …` (em dash) in the spec's order |
| V213-5 | `senior-engineer` wiring and complexity, `staff-engineer` three containers, radon wording in three agents | 1 | haiku | M `.claude/skills/senior-engineer/SKILL.md`; M `.claude/skills/staff-engineer/SKILL.md`; M `.claude/agents/task-reviewer.md`, `.claude/agents/task-implementer.md`, `.claude/agents/plan-briefer.md`; sync_codex outputs | Complexity wording, exact: "`scripts/dev/complexity_gate.py` enforces the limit; `python -m radon cc -s -n C <files>` is for iterating" |
| V213-6 | Clear the remaining findings; the repo-wide case lands | 1 | sonnet | M `.claude/skills/quant-researcher/SKILL.md`, `.claude/skills/technical-analyst/SKILL.md`, `.claude/skills/panel/SKILL.md`, `.claude/skills/handoff/SKILL.md`; M `.claude/agents/plan-writer.md`; M `tests/hooks/skill_citation_allowlist.txt`; M `tests/hooks/test_skill_citations.py` (`test_repo_has_no_stale_citations`); sync_codex outputs | Repo-wide case live: every later task keeps it green |
| V213-7 | Canonical boundary paragraph in all nine seats; shared-lead tests; `/panel` merge-by-lead line | 2 | haiku | M `.claude/skills/{risk-manager,veteran-trader,quant-researcher,quant-engineer,staff-engineer,senior-engineer,financial-advisor,technical-analyst,fundamental-analyst}/SKILL.md`; M `.claude/skills/panel/SKILL.md`; M `tests/hooks/test_role_skills.py`; sync_codex outputs | In `test_role_skills.py`: `BOUNDARY: str` (the Global Constraints text, lines joined with single spaces); `_boundary(role: str) -> str` (first paragraph after the `# ` title line, joined with single spaces); `LEADS: dict[str, str] = {"Shorts:": "Shorts: long plans stay byte-identical; ", "eToro:": "eToro: demo only, never `account: real`; "}`; `CROSS_CUTTING: dict[str, frozenset[str]] = {}` (role to the lead keys it must carry); tests `test_boundary_paragraph_is_canonical`, `test_cross_cutting_items_use_the_shared_lead`, `test_cross_cutting_seats_carry_their_leads` |
| V213-8 | `risk-manager` and `veteran-trader` coverage | 2 | sonnet | M `.claude/skills/risk-manager/SKILL.md`, `.claude/skills/veteran-trader/SKILL.md`; C `.claude/skills/risk-manager/evals/fire-short-gap-sizing/{prompt.md,graders/skill-fired.md}`; C `.claude/skills/veteran-trader/evals/fire-short-borrow/{prompt.md,graders/skill-fired.md}`; M `tests/hooks/test_role_skills.py` (`CROSS_CUTTING` rows `risk-manager` and `veteran-trader`: `frozenset({"Shorts:", "eToro:"})`); sync_codex outputs | — |
| V213-9 | `quant-researcher` and `quant-engineer` coverage | 2 | sonnet | M `.claude/skills/quant-researcher/SKILL.md`, `.claude/skills/quant-engineer/SKILL.md`; C `.claude/skills/quant-researcher/evals/fire-total-r-beside-expr/{prompt.md,graders/skill-fired.md}`; C `.claude/skills/quant-engineer/evals/fire-long-run-checkpoint/{prompt.md,graders/skill-fired.md}`; M `tests/hooks/test_role_skills.py` (row `quant-researcher`: `frozenset({"Shorts:"})`); sync_codex outputs | — |
| V213-10 | `staff-engineer` and `senior-engineer` coverage | 2 | sonnet | M `.claude/skills/staff-engineer/SKILL.md`, `.claude/skills/senior-engineer/SKILL.md`; C `.claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/{prompt.md,graders/skill-fired.md}`; C `.claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/{prompt.md,graders/skill-fired.md}`; M `tests/hooks/test_role_skills.py` (row `staff-engineer`: `frozenset({"eToro:"})`); sync_codex outputs | — |
| V213-11 | `financial-advisor` and `technical-analyst` coverage | 2 | sonnet | M `.claude/skills/financial-advisor/SKILL.md`, `.claude/skills/technical-analyst/SKILL.md`; C `.claude/skills/financial-advisor/evals/fire-etoro-fees/{prompt.md,graders/skill-fired.md}`; C `.claude/skills/technical-analyst/evals/fire-bos-choch-structure/{prompt.md,graders/skill-fired.md}`; M `tests/hooks/test_role_skills.py` (row `financial-advisor`: `frozenset({"eToro:"})`); sync_codex outputs | — |
| V213-12 | `ux-designer` seat with every wiring point in one commit | 3 | sonnet | C `.claude/skills/ux-designer/SKILL.md`; C `.claude/skills/ux-designer/evals/{fire-admin-table-phone,fire-embed-phone-truncation,fire-list-without-pager,no-fire-stop-placement,no-fire-backtest-expr,no-fire-alembic-migration}/{prompt.md,graders/skill-fired.md}`; M `tests/hooks/test_role_skills.py` (`ROLES["ux-designer"] = "sonnet"`, docstring "ten lenses"); M `tests/hooks/test_skill_shape.py` (`TIER_1_AND_3`); M `tests/hooks/test_agent_shape.py` (`EXPERT_ROLES` and its comment); M `.claude/agents/expert-reviewer.md`; M `docs/claude/skills-tools.md` (§ Expert roles (v145): count and the row `` \| `ux-designer` \| sonnet \| … \| ``); M `docs/claude/persona.md`; M `AGENTS.md` (role list); sync_codex outputs | Skill `ux-designer` (reviewer model sonnet) |
| V213-13 | `/panel` seat-picking table | 3 | haiku | M `.claude/skills/panel/SKILL.md`; M `tests/hooks/test_role_skills.py` (`test_panel_seat_table_names_area_seats`); sync_codex outputs | — |
| V213-14 | Pre-close-out panel (staff-engineer, senior-engineer), merge, CI watch, `/close-out` with Step 5b | 3 | sonnet | M `docs/superpowers/specs/2026-11-06-v213-skills-alignment.md` (§ Panel review, implementation round); plan files moved by `/close-out` | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-06-v213-skills-alignment_1-lint-and-drift.md` | V213-1..V213-6 | scanner and unit cases; red proof; `task-brief`, `gate`, `senior-engineer`, `staff-engineer`, agents; remaining findings and the repo-wide case |
| 2 | `2026-11-06-v213-skills-alignment_2-seat-coverage.md` | V213-7..V213-11 | canonical boundary and lead tests; checklist, trigger and eval additions for eight seats |
| 3 | `2026-11-06-v213-skills-alignment_3-ux-designer.md` | V213-12..V213-14 | `ux-designer` seat and wiring; `/panel` table; panel, merge, close-out |
