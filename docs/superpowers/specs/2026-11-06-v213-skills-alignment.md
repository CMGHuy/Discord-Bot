# v213 — Skills alignment: citation lint, drift fixes, seat coverage, ux-designer seat

**Version:** ui 1.40.0 · bot 2.17.0
**Bump:** none (Claude setup and tests only; the bot and the admin UI behave identically)
**Edge:** none (integrity) — skills that cite moved code send briefs and reviews to the wrong place, and every task built on them inherits the error. Prediction: no missing path, unknown config name or dead doc section survives in `.claude/skills` or `.claude/agents` (what the lint cannot see stays with `/close-out` Step 5b), and panels stop missing whole risk areas (shorts, eToro demo, the UI).
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer

## Why

On 2026-11-06 the partner asked what could be improved in ten skills:
`financial-advisor`, `gate`, `quant-engineer`, `quant-researcher`,
`risk-manager`, `senior-engineer`, `staff-engineer`, `task-brief`,
`technical-analyst`, `veteran-trader`. An audit against the tree at `090eed23`
found three kinds of problem.

**Drift: rules that point at the wrong code today.**

- `task-brief` 3b/3c and `senior-engineer` route wiring checks to
  `swingbot/core/scanning/engine.py` and `scanning/embeds.py`, and name
  `swingbot/commands/scanning.py` as the posting module. `build_embed` is
  called from `scan_run.py:1255`, `short_run.py:307` and `outlook_run.py:260`;
  `sections["headline"]` lives in `alert_embeds.py`; `commands/scanning` is a
  package (`commands/scanning/alerts.py`). A trap check that exists to stop
  wrong-place wiring now produces it.
- `task-brief` 3g names `update_open_trades`/`_check_near_close` as scan-loop
  anchors; neither appears in `scan_run.py` (they sit in
  `tracking/performance.py`, `scanning/analyze.py`, `scanning/engine.py`).
- `task-brief`'s intro ("plan files are 358-822 KB", the E7..E49 list) predates
  the v196 size caps; its symbol table (`jsonio.write_json`,
  `TradeLog().all_trades()`) dates from the JSON stores, and every store is
  Postgres-only now.
- `staff-engineer` checks "both containers (`bot.py`, `admin_ui.py`)"; there
  are three (`bot`, `admin`, `refresher`).
- `gate` runs `testrun.py full` locally, which root `CLAUDE.md` forbids ("No
  plan or merge runs the full suite locally; CI does"). Its baseline (1686
  passed) is from August, it never runs frontend tests or the complexity gate,
  and it says "one commit per task" where the rule is several scoped commits.
- `senior-engineer` measures complexity with `radon`; the enforced gate is
  `scripts/dev/complexity_gate.py`.

Nothing caught any of this: no test reads what a skill cites. The partner's
2026-11-06 rule (commit `91e5b4be`, `/close-out` Step 5b) now makes an
implemented plan align every skill it affects; this spec adds the mechanical
net behind that rule and clears the backlog it would otherwise inherit.

**Coverage gaps: risk areas no seat owns.**

- Shorts (v183 gap-aware sizing, squeeze notice; the "short work never
  downgrades longs" rule) appear in no seat.
- The eToro demo stage (root `CLAUDE.md` § eToro roadmap: demo only, never
  `account: real`) appears in no seat.
- Live-book divergence from the backtest is nobody's checklist item, though
  the live book is where the money is.
- `quant-researcher` scores ExpR without total R or trade count, so a filter
  that removes most trades can pass on ExpR alone (the partner's "pair every
  gate tightening with a widening" feedback).
- `risk-manager` does not ask whether heat reads the current stop or the
  stored initial risk (the v187 implementation-panel finding).
- `quant-engineer` asks for progress output but not the checkpoint-and-resume
  rule root `CLAUDE.md` now requires of long runs.
- `technical-analyst` sat on 4 spec `Panel:` lines against 39 for
  `staff-engineer`; its checklist lacks the structure work of the last month
  (swing significance tiers, BOS/CHoCH, sweeps, ATR-band stops).
- The admin UI and how Discord embeds read on a phone have no seat at all,
  though root `CLAUDE.md` makes every UI three-device and the persona includes
  a UX designer.

**Duplication.** All nine role skills open with the same boundary paragraph,
copied by hand and pinned phrase by phrase in `tests/hooks/test_role_skills.py`.

## What changes

### A. Citation lint

The scanner is a module, `scripts/dev/skill_citations.py`, exposing
`scan(root: Path, files: list[Path], tracked: set[str], code_text: str) ->
list[Finding]` (`Finding(file, line, token, reason)`), so its logic is unit
tested on `tmp_path` fixtures apart from the repo. `tests/hooks/
test_skill_citations.py` holds those unit cases plus one repo-wide case; the
file joins the suite that holds `tests/hooks/` in `tests/suites.toml`.

**Scan set.** `.claude/skills/*/SKILL.md`, `.claude/agents/*.md` and
`.claude/skills/*/evals/*/prompt.md`. Not the generated `.agents/` copy
(`test_codex_mirror.py` covers it). Files are read with `encoding="utf-8"` and
`splitlines()`, so CRLF files behave like LF ones. Lines inside fenced code
blocks (between ```` ``` ```` or `~~~` fences) are skipped: the lint reads
prose, not commands.

**Tokens.** Every inline backtick span on a non-fenced line is split on
whitespace into words. Each word is stripped of a trailing `::<symbol>`, a
trailing `:<n>` or `:<n>-<m>` line suffix, and trailing `,.;:)`. A word
containing `<`, `>`, `*`, `{`, `}`, `$`, `=` or `://` is a template and is
skipped. Two citations on one line are two tokens.

1. **Paths.** A word containing `/` and ending in `.py`, `.md`, `.json`,
   `.jsonl`, `.sh`, `.toml`, `.ts`, `.mjs` or `.html` is a path. Words starting
   `.superpowers/`, `logs/`, `data/` or `market_data/` are runtime output and
   skipped. Resolution order: repo root, then `swingbot/`, then
   `swingbot/core/`. A path passes when exactly one candidate is in `tracked`
   (`git ls-files` output, forward slashes, compared case-exactly, so a
   wrong-case citation fails on Windows as it would on Linux CI). No candidate
   gives `reason="missing"`; more than one fallback candidate gives
   `reason="ambiguous"`.
2. **Config names.** A word matching `^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$` must
   match `\b<word>\b` somewhere in `code_text`: every tracked `*.py` under
   `swingbot/`, `scripts/` and `tests/`, read once and joined by the caller.
   Otherwise `reason="unknown name"`.
3. **Doc sections.** On each paragraph (consecutive non-fenced, non-blank
   lines joined with single spaces, a Markdown list item starting a new one, so a citation wrapped across lines still
   reads whole), the pattern `` `?(?P<doc>[\w./-]+\.md)`?\s*§\s*(?P<cite>[^`]+) ``
   finds a cited section. The doc resolves from the repo root when it contains
   `/`, else from `docs/claude/`; a doc not in `tracked` gives
   `reason="missing doc"`. `cite` is stripped of trailing `.,;:)` and dots; it
   passes when, compared case-insensitively, it starts with a heading of that
   doc or a heading starts with it. Headings are `##`, `###` and `####` lines
   outside the doc's own fenced blocks. Otherwise `reason="missing heading"`.

**Allowlist.** `tests/hooks/skill_citation_allowlist.txt`: blank lines and
`#` lines are ignored; every other line is `skill|token|reason`, where `skill`
is the skill folder or agent file stem and `token` matches a finding's token
exactly. One line covers every occurrence in that skill. It exists for
deliberate mentions of removed things (task-brief's deleted-shims list).
`scan` returns every finding, never stopping at the first, so the test can
also fail on an allowlist line that matched no finding (dead line).

**Output.** Each failure prints `<file>:<line>: <token> -- <reason>` (paths
repo-relative, forward slashes). A test asserts this exact format.

**What the lint cannot catch, and who does.** A citation to a file that still
exists as a facade (`scanning/engine.py`, `scanning/embeds.py`), bare
filenames with no `/`, function names, `file:line` numbers that drifted, and
commands inside fenced blocks all pass it. `/close-out` Step 5b owns those:
it greps the skills for everything a plan's diff changed.

**No red CI.** The unit cases land first and are green on their own. The
repo-wide case lands in the same commit as the last Part B fix, so no push
carries a red `tests/hooks/` job. The implementer proves the repo-wide case red
locally (`testrun.py file`) before the B fixes, and records the failure list.

### B. Drift fixes

**task-brief.** Steps 1, 2, 4 and 5 (handoff mechanics) are unchanged.

- Intro keeps the claim "a plan is not ground truth about the current code" and
  drops the KB figures and the E-id list.
- 3a's symbol table is re-verified; entries for symbols that no longer matter
  in the Postgres era go, any still-invented ones stay.
- 3b/3c point at the real wiring: the alert loops in `scan_run.py`,
  `short_run.py`, `outlook_run.py`; fields through `sections["headline"]` in
  `alert_embeds.py`; `commands/scanning/` only posts.
- 3g is re-derived from `scan_run.py` and rewritten to the current anchors.
- New traps: **3i** stores are Postgres-only (no JSON writes); a test reaching
  the database runs `/replicate-prod-db` first against the shared `swing-db`.
  **3j** test placement: a new `tests/` directory joins one suite in
  `suites.toml`; a new data file gets a `DATA_READERS` row in
  `scripts/dev/select_tests.py`; tests that log in to the admin never use the
  main-tree `.env` admin credentials in pytest admin-login fixtures (they
  override the fixture's own and produce 401s, V177); a Playwright or local
  instance check still logs in with the `.env` values, per root `CLAUDE.md`.
  **3k** a SHORT-targeted task keeps
  long plans byte-identical and pins it with a regression test. **3l** a UI
  task is checked at 390, 768 and 1440 px with Playwright.
- Step 4's PowerShell-only snippets gain Bash equivalents.

**senior-engineer.** The wiring item is corrected as in 3b. The complexity
item takes one wording, also applied to `.claude/agents/task-reviewer.md`,
`task-implementer.md` and `plan-briefer.md`: "`scripts/dev/complexity_gate.py`
enforces the limit; `python -m radon cc -s -n C <files>` is for iterating"
(matching `docs/claude/code-complexity.md`).

**staff-engineer.** "Both containers" becomes the three containers off one
image.

**gate** becomes the pre-push gate (partner's choice). In order, each step
pasting its verdict line:

1. CPU check for a live long run (unchanged).
2. Syntax pass (unchanged).
3. `python scripts/dev/complexity_gate.py`.
4. `python scripts/dev/testrun.py changed` (or `file` while iterating).
5. When `frontend/` changed: `npx ng test --watch=false --include <spec>` from
   `frontend/`.
6. `git add <explicit paths>`; several scoped commits, never one large one.
7. Push, then watch the CI run (`working-conventions.md` § Pipeline watch) and
   fix failing tests, each re-run alone, until green.

Green is `0 failed` and `0 xfailed`. The August baseline and the xfail history
go. `disable-model-invocation: true` stays: the gate runs only when typed.

**Findings outside the ten skills.** The scan set is every skill, agent and
eval prompt, so the repo-wide case also meets tokens in skills this spec does
not otherwise touch (the plan-briefer dry run on 27fd81b2 counted about 19 of
29 path findings there: the uncommitted `ssh-hetzner.sh`, the deleted-shim
lists in `symbol-verifier` and `alert-surface`, vendored eToro config paths,
hypothetical paths in eval prompts, a runtime `backups/` path). Part B clears
each one: a real drift is fixed in its skill; a deliberate or uncommitted
mention gets an allowlist line with its reason.

### C. Seat coverage

The boundary paragraph (not byte-identical today) becomes one canonical text,
identical in every role skill, `fundamental-analyst` included, and pinned whole by `test_role_skills.py`. It stays inside each skill,
because a role skill also loads on its own, without `expert-reviewer`.

`test_role_skills.py` caps a checklist at 8-15 items. Additions come in by
merging or dropping, never by raising the cap:

| Seat | Adds | Makes room by |
|---|---|---|
| risk-manager | short gap-aware sizing and squeeze (v183); heat from the current stop, not stored initial risk; eToro: no `account: real` path, no order sent without its stop | merging the two cap-binding items |
| veteran-trader | short borrow and hard-to-borrow names; Berlin-time alerts against the US open, half-days, holidays, the frozen weekend bar; partial fills on limit-at-level entries; eToro CFD vs stock fills | merging alert volume into alert timing |
| quant-researcher | total R (ExpR × N) and trade count beside every ExpR; longs byte-identical on short work; live-book gap named | merging badge `run_date` into the pooled-numbers item; merging concentration with direction |
| quant-engineer | long runs checkpoint each unit and resume on restart; Alpaca/yfinance provider parity; the training-data store | folding flushed progress into the checkpoint item |
| staff-engineer | admin worker load (v206); one CI job per `suites.toml` suite; PITR and backup touched; eToro: idempotent order send, demo only | dropping the `Bump:` item (`/close-out` owns it); folding far-off scheduled work into the long-run-cost item (13 + 4 − 2 = 15) |
| senior-engineer | a new test joins its suite; a frontend change ships Vitest specs; a mutation of the fix fails its test | dropping "symbols exist" (`task-brief` owns it) |
| financial-advisor | eToro fees and minimum position size in frictions and account fit (generic; no jurisdiction-specific tax, partner's choice) | none |
| technical-analyst | swing significance tiers and BOS/CHoCH; liquidity sweeps; ATR-band stops as volatility logic; volume confirmation as independent evidence | merging the chart overlay item with `explain.py` |

Cross-cutting items open with one shared lead so `/panel` can merge them
across seats, then add the seat's own angle in the same bullet, one claim each:
"Shorts: long plans stay byte-identical; <angle>." and "eToro: demo only,
never `account: real`; <angle>." Every checklist bullet carries one claim, as the
existing seats do.

Every edited seat gains one should-fire trigger line and, where the case is
new, one eval folder. Evals are written, not run (running them is billed).

### D. ux-designer seat

New `.claude/skills/ux-designer/SKILL.md` in the four-section role shape,
reviewer model **sonnet**. Lens: the admin UI and Discord embeds as a person
reads them on phone, tablet and desktop.

Checklist:

- A changed screen passes `node frontend/scripts/layout-audit.mjs` at the widths `docs/claude/ui-design.md` names (it owns the overflow, target-size and text-size rules).
- The check is driven by Playwright, never claude-in-chrome.
- A wide table scrolls inside its own container, never the page.
- A list longer than one page has a pager.
- Empty, loading and error states exist and say what to do next.
- Per-page defaults follow `docs/claude/ui-design.md`.
- Discord embed fields read on a phone: no truncated entry, stop or target; the plan fits without scrolling past the chart.
- Numbers carry units and sign consistently between the embed and the admin screen showing the same plan.
- A new control is reachable by keyboard and labelled for a screen reader.

Red flags: a screen that scrolls sideways at any of the three widths; a plan
value truncated or hidden on a phone; a list with no pager. Out of scope:
whether a figure misleads a retail reader (`financial-advisor`), whether the
plan is tradeable (`veteran-trader`), the code behind the screen
(`senior-engineer`).

Wiring: a row in `docs/claude/skills-tools.md` § Expert roles; `ROLES` in
`test_role_skills.py`; the role list in `.claude/agents/expert-reviewer.md`;
`TIER_1_AND_3` in `tests/hooks/test_skill_shape.py`; `EXPERT_ROLES` in `tests/hooks/test_agent_shape.py`; the role list in `AGENTS.md` (checked by `sync_codex.py --check`); the role list in `docs/claude/persona.md`; "nine" becomes "ten" only in live counts (`skills-tools.md` § Expert roles, `expert-reviewer.md`, the `test_role_skills.py` docstring), never in dated results such as the v145 eval measurement; three should-fire and three
should-not-fire eval folders.

`/panel` gains a short table mapping a target's type to suggested seats
(spec by `Edge:`, backtest result, diff touching `frontend/` or embeds, diff
touching `swingbot/core/market/`), so `technical-analyst` and `ux-designer`
are picked when their area is touched.

### Codex mirror

Every commit that changes a skill, an agent or a rule runs
`python scripts/dev/sync_codex.py` and updates `AGENTS.md` where it mirrors the
text, in the same commit (`working-conventions.md` § Codex mirror).

## What stays

- The bot, the admin UI and every store behave identically; no code under
  `swingbot/` or `frontend/` changes.
- The handoff mechanics of `task-brief` (steps 1, 2, 4, 5) and the role-skill
  four-section shape.
- The 8-15 checklist cap and the 80-line skill budget in `test_skill_shape.py`.
- `financial-advisor` stays generic and educational.

## Testing

- `tests/hooks/test_skill_citations.py` (new). Unit cases on `tmp_path`
  fixtures: missing path; path found only by a fallback root; ambiguous
  fallback; wrong-case path; template word skipped; `::symbol` and `:line`
  suffixes stripped; several paths in one multi-word span; two citations on
  one line; a path inside a fenced block skipped; a CRLF file; runtime prefix
  skipped; unknown config name; config name found only in a comment-free
  `scripts/` file; doc section wrapped across two lines; missing heading;
  `####` heading accepted; `##` inside the doc's fenced block not a heading;
  eval `prompt.md` in the scan set; allowlisted token; allowlist comment and
  blank lines; dead allowlist line; the exact output format. One repo-wide
  case, landing with the last Part B fix.
- `tests/hooks/test_role_skills.py`: ten roles, `ux-designer: sonnet`, the
  canonical boundary paragraph identical in all ten.
- A gate test on structure, not wording: the `## Step` headings of
  `.claude/skills/gate/SKILL.md` appear in order and their bodies name, in
  that order, `complexity_gate.py`, `testrun.py changed` and the CI watch;
  `testrun.py full` appears only on a line that also says "never" or "CI";
  the frontmatter `description` does not mention a full suite.
- `tests/hooks/test_codex_mirror.py` and `tests/hooks/test_skill_shape.py`
  stay green after every commit.
- Each task runs `python scripts/dev/testrun.py file <test>` on what it touched;
  CI runs the full suite.

## Order

A (scanner and unit cases, green) → B (drift fixes; the repo-wide case lands with the last fix, so no push is red) → C (seat coverage) → D
(ux-designer and `/panel` table). C and D both edit `test_role_skills.py` and
the `/panel` skill, so they run in sequence.

## What follows

- A per-seat log of rejected panel findings, mined from close-out records
  (`rejected: <why>`), so a rejected finding stops recurring. Deferred until
  enough rejections exist to mine.
- Running the skill evals once the partner chooses to spend on them.

## Panel review

Spec review, 2026-11-06, on `c097d09e`.

- staff-engineer: staff-engineer row ends at 16 items, over the cap -- applied (far-off scheduling folded into long-run cost; 15).
- staff-engineer: ux-designer wiring misses `TIER_1_AND_3`, `EXPERT_ROLES`, the `AGENTS.md` role list, `persona.md` -- applied.
- staff-engineer: `verified <date>` stamps on task-brief traps have no owner and `/close-out` is at its 80-line budget -- applied (stamps dropped; Step 5b's grep already reaches traps that cite a changed file).
- staff-engineer: config-name rule misses live names defined in `scripts/` (`DATA_READERS`) -- applied (search `swingbot/`, `scripts/`, `tests/`).
- staff-engineer: "no stale citation survives" overclaims; facades, bare names, `file:line`, functions pass the lint -- applied (Edge prediction narrowed; "What the lint cannot catch" names Step 5b as owner).
- staff-engineer: `radon` also in three agents and `code-complexity.md` legitimately recommends it for iterating -- applied (one wording in all four).
- staff-engineer: red-first lint reddens the `tests/hooks/` CI job between A and B -- applied (repo-wide case lands with the last B fix; red proof local).
- staff-engineer: trap 3j contradicts the `.env` login rule -- applied (scoped to pytest admin-login fixtures).
- staff-engineer: ux-designer restates `ui-design.md` figures -- applied (cites `layout-audit.mjs`).
- staff-engineer: gate test misses the frontmatter description -- applied.
- staff-engineer: "nine to ten" would rewrite dated results -- applied (live counts only).
- senior-engineer: BLOCKING, path tokenisation undefined -- applied (word split, suffix strip, template skip, runtime prefixes).
- senior-engineer: BLOCKING, fallback roots lenient and order-dependent -- applied (one order, exactly-one-candidate rule, `ambiguous`; `swingbot/core/market/` root dropped).
- senior-engineer: BLOCKING, config-name and allowlist matching unspecified -- applied (word-boundary on joined `*.py`, exact token match, comments and blanks, collect-all findings).
- senior-engineer: BLOCKING, doc-section rule undefined -- applied (paragraph join, pinned regex, case-insensitive two-way prefix, `##`-`####`, fenced headings excluded).
- senior-engineer: CRLF and case-insensitive Windows paths -- applied (`splitlines()`, case-exact compare against `git ls-files`).
- senior-engineer: test cases weak, "red on 090eed23" not a test -- applied (`scan()` module, `tmp_path` cases listed, output format asserted).
- senior-engineer: cross-cutting items worded differently across seats; ux bullet carries four claims -- applied (shared leads; one claim per bullet).
- senior-engineer: gate test is a brittle substring pin -- applied (structural step-order test).
