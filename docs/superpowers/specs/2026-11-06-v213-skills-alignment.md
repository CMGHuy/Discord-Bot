# v213 — Skills alignment: citation lint, drift fixes, seat coverage, ux-designer seat

**Version:** ui 1.40.0 · bot 2.17.0
**Bump:** none (Claude setup and tests only; the bot and the admin UI behave identically)
**Edge:** none (integrity) — skills that cite moved code send briefs and reviews to the wrong place, and every task built on them inherits the error. Prediction: no stale citation survives in `.claude/skills` or `.claude/agents`, and panels stop missing whole risk areas (shorts, eToro demo, the UI).
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

New `tests/hooks/test_skill_citations.py`, joining the suite that holds
`tests/hooks/` in `tests/suites.toml`. It scans `.claude/skills/*/SKILL.md`,
`.claude/agents/*.md` and `.claude/skills/*/evals/*/prompt.md` (not the
generated `.agents/` copy, which `test_codex_mirror.py` covers) and fails on:

1. **Paths.** A backticked token that contains `/` and ends in `.py`, `.md`,
   `.json`, `.jsonl`, `.sh`, `.toml`, `.ts` or `.html` must exist relative to
   the repo root, `swingbot/`, `swingbot/core/` or `swingbot/core/market/`.
   Tokens with `<`, `*` or `{` are templates and skipped.
2. **Config names.** A backticked token matching `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$`
   must appear in `swingbot/config.py` or anywhere under `swingbot/`.
3. **Doc sections.** `<doc>.md § <Heading>` must prefix-match a `##` or `###`
   heading of that doc (looked up under `docs/claude/` when the doc is bare).

Deliberate mentions of removed things (task-brief's deleted-shims list) go in
`tests/hooks/skill_citation_allowlist.txt`, one `skill|token|reason` per line.
The test also fails on an allowlist line that matches nothing, so the list
cannot rot. Each failure prints `skill:line: token -- reason`.

The lint lands first and is red on today's tree, which proves it reads what it
claims to; Part B turns it green.

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
  `.env` admin credentials of the main tree. **3k** a SHORT-targeted task keeps
  long plans byte-identical and pins it with a regression test. **3l** a UI
  task is checked at 390, 768 and 1440 px with Playwright.
- Every trap 3a-3l carries `verified <date> against <file>`; `/close-out`
  Step 5b refreshes the stamp when a plan touches that file.
- Step 4's PowerShell-only snippets gain Bash equivalents.

**senior-engineer.** The wiring item is corrected as in 3b; the complexity
item names `scripts/dev/complexity_gate.py`.

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

### C. Seat coverage

The boundary paragraph becomes one canonical text, identical in every role
skill and pinned whole by `test_role_skills.py`. It stays inside each skill,
because a role skill also loads on its own, without `expert-reviewer`.

`test_role_skills.py` caps a checklist at 8-15 items. Additions come in by
merging or dropping, never by raising the cap:

| Seat | Adds | Makes room by |
|---|---|---|
| risk-manager | short gap-aware sizing and squeeze (v183); heat from the current stop, not stored initial risk; eToro: no `account: real` path, no order sent without its stop | merging the two cap-binding items |
| veteran-trader | short borrow and hard-to-borrow names; Berlin-time alerts against the US open, half-days, holidays, the frozen weekend bar; partial fills on limit-at-level entries; eToro CFD vs stock fills | merging alert volume into alert timing |
| quant-researcher | total R (ExpR × N) and trade count beside every ExpR; longs byte-identical on short work; live-book gap named | merging badge `run_date` into the pooled-numbers item; merging concentration with direction |
| quant-engineer | long runs checkpoint each unit and resume on restart; Alpaca/yfinance provider parity; the training-data store | folding flushed progress into the checkpoint item |
| staff-engineer | admin worker load (v206); one CI job per `suites.toml` suite; PITR and backup touched; eToro: idempotent order send, demo only | dropping the `Bump:` item (`/close-out` owns it) |
| senior-engineer | a new test joins its suite; a frontend change ships Vitest specs; a mutation of the fix fails its test | dropping "symbols exist" (`task-brief` owns it) |
| financial-advisor | eToro fees and minimum position size in frictions and account fit (generic; no jurisdiction-specific tax, partner's choice) | none |
| technical-analyst | swing significance tiers and BOS/CHoCH; liquidity sweeps; ATR-band stops as volatility logic; volume confirmation as independent evidence | merging the chart overlay item with `explain.py` |

Every edited seat gains one should-fire trigger line and, where the case is
new, one eval folder. Evals are written, not run (running them is billed).

### D. ux-designer seat

New `.claude/skills/ux-designer/SKILL.md` in the four-section role shape,
reviewer model **sonnet**. Lens: the admin UI and Discord embeds as a person
reads them on phone, tablet and desktop.

Checklist:

- Checked at 390, 768 and 1440 px with Playwright and the `.env` admin login, never claude-in-chrome; no horizontal page scroll at any width.
- Touch targets at least 44 px on phone widths.
- Tables collapse or scroll inside their container; every list longer than a page has a pager.
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
"nine" becomes "ten" wherever it counts the roles; three should-fire and three
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

- `tests/hooks/test_skill_citations.py` (new): red on `090eed23`, green after B.
  Its own cases cover a missing path, a template path skipped, an unknown
  config name, a missing doc heading, an allowlisted token, and a dead
  allowlist line.
- `tests/hooks/test_role_skills.py`: ten roles, `ux-designer: sonnet`, the
  canonical boundary paragraph identical in all ten.
- A gate test: `.claude/skills/gate/SKILL.md` contains no `testrun.py full` and
  does contain the CI-watch step.
- `tests/hooks/test_codex_mirror.py` and `tests/hooks/test_skill_shape.py`
  stay green after every commit.
- Each task runs `python scripts/dev/testrun.py file <test>` on what it touched;
  CI runs the full suite.

## Order

A (lint, red) → B (drift fixes, lint green) → C (seat coverage) → D
(ux-designer and `/panel` table). C and D both edit `test_role_skills.py` and
the `/panel` skill, so they run in sequence.

## What follows

- A per-seat log of rejected panel findings, mined from close-out records
  (`rejected: <why>`), so a rejected finding stops recurring. Deferred until
  enough rejections exist to mine.
- Running the skill evals once the partner chooses to spend on them.
