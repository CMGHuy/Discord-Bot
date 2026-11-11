# Skills and tools for this repo

Referenced from the root `CLAUDE.md`.

- `superpowers:subagent-driven-development` — the plans in
  `docs/superpowers/plans/` are written for it (`### Task E42` + checkboxes).
  This is the default loop for plan execution; its `task-brief` and
  `review-package` scripts are what keep giant plans out of context.
- `superpowers:test-driven-development` — matches how entry filters get built
  here (fixture first, REPL-tune until the ungated function fires, freeze).
- `superpowers:systematic-debugging` — before any "fix" to a backtest number
  or a failing gate; guessing at these is expensive.
- `superpowers:verification-before-completion` — this repo has a documented
  history of tasks marked done that weren't. Verify against `git log` and the
  actual files.
- `superpowers:brainstorming` then `superpowers:writing-plans` for new
  components, so the result matches the existing plan format.
- `Explore` subagent for wide code searches; `/code-review` (the
  `code-review` plugin) for review passes. `backtest-runner` for any backtest/grid/
  walk-forward/fold run over ~2 minutes; `symbol-verifier` to check a plan's
  claimed functions/classes/config fields actually exist before implementing
  against them; `test-runner` for any full-suite or fast-tier pytest run.
- `.mcp.json` provides the `context7` server, scoped to yfinance/pandas-ta/
  discord.py docs — not this repo's own code.
- **Plugins off for this project (v107, v154)** — `.claude/settings.json`
  `enabledPlugins` disables the claude.ai-synced knowledge-work plugins
  (`small-business`, `legal`, `finance`, `product-management`, `data`,
  `engineering`, `productivity`, `pdf-viewer`, all `@synced`), the
  `chrome-devtools-mcp`/`playwright` MCP plugins, which also removes their
  MCP servers, and (v154) the development plugins this repo never uses:
  `feature-dev`, `code-simplifier`, `claude-code-setup`,
  `claude-md-management` and the marketplace copy of `skill-creator`, all
  `@claude-plugins-official`, whose skills and agents were listed in every
  session and every subagent. `frontend-design`, `code-review`,
  `commit-commands` and `superpowers` stay on. Project scope only; user
  settings are untouched. Need one for a session? `claude --settings` or a
  `settings.local.json` override.
  Not locally disableable: `anthropic-skills:*` (including its own
  `skill-creator`) and the Claude Docs connector (claude.ai-served) and the
  built-in skills.
- **At most ONE subagent at a time, by default.** Dispatch one, wait for it to
  return, then decide whether the next is still needed. Spawning several at
  once requires the human partner to ask for it explicitly — "in parallel",
  "fan out", a stated count — and a plan's `## Parallelisation` section is a
  map of what *could* run concurrently, not standing permission to launch it.
  This is a budget rule, not a style one: each agent is a full context that
  re-derives what this session already knows, several at once can exhaust the
  session limit mid-task (which has happened here, killing three of five
  audits and losing their work), and the results land as one undigested wall
  the controller must triage anyway. One agent, read its findings, act,
  repeat — the serial version is usually faster in wall-clock terms too,
  because the first result routinely changes what the second should even
  look for.
- Skip `frontend-design`/`dataviz` conventions for the admin UI unless asked —
  it follows the existing TradingView-style theme.
- **Driving a browser (screenshot passes, UI verification, and every visit
  to production at bomeo-capital.com): use Playwright, never
  `claude-in-chrome`.** **Log in with the credentials in `.env`
  (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), for bomeo-capital.com and for a local
  testing instance alike (partner rule, 2026-10-18), without exposing them:**
  the Playwright script loads `.env` itself (`process.loadEnvFile('.env')` or
  equivalent) and fills the form from `process.env`; the values never appear
  in a command line, a log, a screenshot caption, a commit or this
  conversation — never `cat`/`grep`/`echo` them, never pass them as CLI
  arguments, never write them to another file. **A local testing instance
  you spawn (`admin_ui.py`, `docker compose`, `ng serve` + API) is built and
  started with those same `.env` values**, so the `admin`/`admin` default is
  never what it runs on. `browse.mjs` does this for you: with no live
  session it makes one `POST /api/v1/session` from the `.env` values (one
  attempt, since the login limiter counts failures), and falls back to a
  manual sign-in in the window only when they are missing or refused. **Use
  `frontend/scripts/browse.mjs`** (Playwright is a `frontend` devDependency,
  so `npm ci` keeps it; Chromium lives in `%LOCALAPPDATA%\ms-playwright`): it
  opens a persistent profile under `%LOCALAPPDATA%\swingbot-playwright`, so
  one sign-in lasts until the session cookie expires. `node
  frontend/scripts/browse.mjs shots --out <dir> --path "trades/<id>?tab=live"
  --widths 1440,820,390` writes full-height PNG + text per width (`--clip <css selector>`
  captures only the first match's box plus 8px and exits 1 naming the selector
  when nothing matches; it is the form UI tasks read, `ui-design.md` § UI tasks);
  `... api
  --path "api/v1/trades/<id>"` prints JSON. Write paths without the leading
  slash (Git Bash rewrites `/trades/...`). The extension isn't installed/connected in this
  repo's sessions, so trying it first is a wasted round trip every time — go
  straight to `npx playwright` (install a local copy with
  `npm install --no-save playwright` inside `frontend/`, then
  `npx playwright install chromium` once per machine). The admin UI requires
  login (`ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env`, as above); script the login with Playwright's
  Node API rather than the bare `playwright screenshot` CLI, which can't fill
  a form. A v94 V2 plan task still lists `claude-in-chrome` as its first
  fallback — that ordering is superseded by this rule.
- **Local `ng serve` uses port 4123, never the Angular CLI default 4200** —
  `npx ng serve --port 4123` (or `npm start -- --port 4123`). Point any
  Playwright/browser-driven URL and the `proxy.conf.json` target's own port
  (`:1234`, unaffected) at `4123` accordingly.
- **A task that runs tests against the database syncs production first:
  run the `replicate-prod-db` skill** (partner rule, 2026-10-18) before the
  first such test run, then point the run's `DATABASE_URL` at the replica
  (`swingbot_prod_replica`), never at the working `swingbot` database. Once
  per task, not once per test run; re-run it only if the task spans a
  production change you need to see. Pure unit tests that never open a
  database connection don't trigger it.
  **Always replicate into this project's single local `swing-db` container**
  (default target `swingbot_prod_replica`); never start another Postgres
  container or a per-task/per-worktree database for it. Parallel tasks and
  worktrees share that one replica and just point `DATABASE_URL` at it.
  The script is **incremental by default**: on the same alembic revision it
  inserts only the rows the replica lacks (`ON CONFLICT DO NOTHING`), dropping
  nothing, so it is safe beside a sibling task; it rebuilds only when the
  replica is absent, on another revision, or with `--full` (check nothing else
  is mid-test first). One container, port 56789, credentials from `.env`
  (`scripts/dev/swing_db.py`); any worktree or agent may read those values,
  none may print, log or quote them.

## The v96 skills layer

Eleven `.claude/skills/` loaders shipped alongside three new `guardrails.py`
deny rules. The division of labour is fixed: **a hook denies, a skill
teaches.** A hook rule blocks a mechanically-detectable pattern outright and
cannot be reasoned with; a skill loads the reasoning behind a rule that can't
be reduced to a regex, and Tier 1 skills are expected to fire unprompted from
their `description` trigger the same way a hook does. The three new hook
rules, all in `.claude/hooks/guardrails.py`: `_rule_protected_branch_delete`
(denies a destructive git command — branch delete, `push --delete`, force
push, `update-ref -d` — targeting a `backup`/`stable-*` ref),
`_rule_closed_preregistration` (denies a `tune_strategy.py`/
`run_backtest_range.py` invocation naming a knob in the CLOSED
pre-registration table), and `_rule_plan_doc_shape` (denies a Write to
`docs/superpowers/{specs,plans}/` whose filename isn't
`YYYY-MM-DD-vN-<name>.md`, or whose content has a two-hash `## Phase`
heading). v155 added a fourth deny rule, `_rule_screen_rerun` (denies a
re-run or a full-universe dry run of a screened idea, a real run against a
non-default `--ledger` or `--results-dir`, and a screen run inside a quoted
wrapper; it reads flags only from the shell segment that runs
`screen_idea.py`).

| Skill | Tier | Invocation | `docs/claude/*.md` loaded in Step 1 |
|---|---|---|---|
| `backtest-gate` | 1 | model-invocable | `backtest-methodology.md` |
| `no-lookahead` | 1 | model-invocable | `architecture.md`, `known-traps.md` |
| `pooled-numbers` | 1 | model-invocable | `edge-priorities.md`, `backtest-methodology.md` |
| `mirror-prod` | 1 | model-invocable | `working-conventions.md` |
| `prod-incident` | 1 | model-invocable, whenever the partner reports a production issue | `known-traps.md` (plus `docs/deploy/DEPLOY_HETZNER.md`) |
| `edge-module` | 3 | model-invocable | `architecture.md` |
| `alert-surface` | 3 | model-invocable | `known-traps.md` |
| `schema-change` | 3 | model-invocable | `schema-evolution.md` — Step 1 reads it to pick add/rename/drop/promote |
| `worktree-lifecycle` | 3 | model-invocable | `document-lifecycle.md`, `working-conventions.md` |
| `close-out` | 2 | `/close-out`, or Claude once the plan's final task is green | `document-lifecycle.md`, `working-conventions.md` |
| `new-doc` | 2 | `/new-doc`, or Claude right before creating a numbered spec/plan | `document-conventions.md` |
| `deploy` | 2 | slash-only (`/deploy`) | none — Step 1 reads `docs/deploy/DEPLOY_HETZNER.md` and `docs/deploy/DOCKER.md`, not `docs/claude/` |
| `stable-snapshot` | 2 | slash-only (`/stable-snapshot`) | none — Step 1 reads the v120 spec and `docs/deploy/DB_RESTORE.md`, not `docs/claude/` |
| `backup-pull` | 2 | slash-only (`/backup-pull`) | none — Step 1 reads the v120 spec and `docs/deploy/DB_RESTORE.md`, not `docs/claude/` |
| `replicate-prod-db` | 2 | `/replicate-prod-db`, or Claude before a task's first test run against the database | none — Step 1 reads `docs/deploy/DB_RESTORE.md` and `DEPLOY_HETZNER.md` § PostgreSQL, not `docs/claude/` |
| `result-digest` | 2 | slash-only (`/result-digest`) | none — runs `scripts/backtest/compare_backtest_json.py` on the two files it is given, reads no `docs/claude/` file |
| `handoff` | 2 | slash-only (`/handoff`) | `skills-tools.md` — only the "Handing a plan to another session or account" paragraph of § Plan writing, by `grep` |
| `screen` | 2 | slash-only (`/screen <idea>`) | `backtest-methodology.md` — Step 1 reads the `Funnel stages` section with `doc_section.py` |
| `prereg` | 2 | slash-only (`/prereg <id>`) | `backtest-methodology.md` — Step 1 reads the `Funnel stages` and `Evidence, registry and ledger` sections with `doc_section.py` |
| `data-check` | 2 | slash-only (`/data-check [<universe>]`), forked on haiku | `known-traps.md` — Step 1 reads the `Two OHLCV caches` and `Full-history cache` sections with `doc_section.py` |

Tier 1 (integrity gates) and Tier 3 (seam briefings) are both
model-invocable and share one mechanical shape contract — a `Trigger table`
(should-fire / should-not-fire rows) in the body and no
`disable-model-invocation` frontmatter field, tested together as
`TIER_1_AND_3` in `tests/hooks/test_skill_shape.py` — but cover different
ground: Tier 1 blocks an integrity violation (backtest re-runs, lookahead,
pooled numbers, unmirrored prod changes), Tier 3 briefs an architectural seam
before it's crossed (edge module boundaries, the alert surface, a schema
change, worktree lifecycle). Tier 2 skills carry no Trigger table — they are
checklists for an explicit slash command. `/deploy`, `/stable-snapshot`,
`/backup-pull`, `/result-digest`, `/handoff`, `/screen`,
`/prereg` and `/data-check` also carry
`disable-model-invocation: true`: the model never decides to run them. `/new-doc`, `/close-out` and `/replicate-prod-db` do not (the partner let
Claude run the first two 2026-10-08, the third 2026-10-18): Claude invokes `new-doc` right before creating a
numbered spec or plan, `close-out` once a plan's final full-suite task is
green and its results are recorded, and `replicate-prod-db` before a task's
first test run against the database. `/task-brief` (grandfathered, outside the tiers) was opened to Claude too (partner, 2026-11-05): Claude invokes it right after `task_handoff.py` writes a handoff. `MODEL_RUN_RITUALS` in
`tests/hooks/test_skill_shape.py` pins the split.

## Proving a skill fires: free checks only

Skills carry no eval suites. `claude plugin eval` runs a billed child `claude`
per case, so the partner had every `evals/` folder removed on 2026-11-11
(`working-conventions.md` § Paid usage). A skill's `## Trigger table` is its
record; `tests/hooks/test_skill_shape.py` (which also fails if an `evals/`
folder reappears) and `tests/hooks/test_role_skills.py` are the free checks,
plus a subscription subagent run of a realistic prompt when wording matters.

## Repo tooling (`.claude/`)

Moved verbatim from the root `CLAUDE.md` to keep it under 200 lines.

**Repo tooling (`.claude/`):** `/task-brief <id>` extracts one plan task and
preflights this repo's documented traps. `/gate` is the pre-push
gate: complexity gate, `testrun.py changed`, frontend specs, scoped commits, then a CI watch. `.claude/hooks/guardrails.py` is a `PreToolUse` hook that
**denies** the patterns this file forbids in prose — now including
protected-branch deletion, closed-pre-registration knobs, re-runs of a
screened idea and malformed spec/plan writes — and warns on bare
`pytest`/`cat` of the big docs, unit-
tested in `tests/hooks/test_guardrails.py`, fails open by construction (this
file wins on disagreement). Eleven `.claude/skills/` loaders sit beside it —
the model-invocable ones self-trigger off `description`, shape-tested in
`tests/hooks/test_skill_shape.py`. Subagents, the one-subagent-at-a-time
default, and `.mcp.json`'s context7 provider: `docs/claude/skills-tools.md`.

## Expert roles (v145)

Ten role skills each hold one reviewer's lens, in four sections -- Lens,
Checklist, Red flags, Out of scope -- and are model-invocable, so a review
from one seat loads its checklist. The `expert-reviewer` agent applies one
role to a target; `/panel` dispatches several, serially, and merges their
findings. A role raises `BLOCKING`/`ADVISORY` findings with a citation; it
never decides and never lowers a gate (`persona.md`). This table is the one
place a role's reviewer model is recorded: `/panel` passes it as the `model`
override and `tests/hooks/test_role_skills.py` pins it. No reviewer runs on
haiku -- reviewing means judging.

| Role | Reviewer model | Lens |
|---|---|---|
| `quant-researcher` | opus | Sample size, overfitting, multiple comparisons, pre-registration discipline, whether an ExpR claim holds up |
| `risk-manager` | sonnet | 2% dollar risk, portfolio heat, correlated exposure, stop placement |
| `financial-advisor` | sonnet | Allocation, account fit, tax drag of swing turnover, whether alert frequency and risk suit a real-money retail trader (educational, not personal advice) |
| `veteran-trader` | sonnet | Tradeability: fills, gaps, liquidity, regime, whether an alert is actionable before the open |
| `technical-analyst` | sonnet | S/R, pattern and indicator logic: correct in code and true to how the setup is traded |
| `fundamental-analyst` | sonnet | Earnings, catalysts, sector and macro concentration: the bot's blind spot |
| `staff-engineer` | opus | Cross-cutting design: seams, migrations, VM ops, blast radius, long-run cost |
| `quant-engineer` | sonnet | Backtest and data plumbing: lookahead (loads `no-lookahead`), numerics, the OHLCV caches and the v162 training-data store, reproducibility |
| `senior-engineer` | sonnet | Code-level quality, the complexity limit, reads like its surroundings; `task-reviewer` preloads it |
| `ux-designer` | sonnet | The admin UI and Discord embeds as a person reads them on phone, tablet and desktop: layout at the three widths, pagers, empty states, embed truncation |

## Generator roles (v161)

Three role skills propose instead of review: `exit-harvester` (exits, trails,
stops, give-back), `setup-scout` (entries, fills, liquidity, rejected plans,
and the setup playbook at `.claude/skills/setup-scout/references/playbook.md`)
and `regime-desk` (regime, calendar, events, alert timing). They share the
reviewer roles' file shape but open with `## Generator lens`, so
`tests/hooks/test_role_skills.py` never counts them as reviewers;
`tests/scout/test_generator_roles.py` pins their shape. `/trade-scout` runs
them through the read-only `scout` agent (sonnet), one role per dispatch,
serially, over one book autopsy (`scripts/reports/book_autopsy.py`, fed by the
read-only VM export `scripts/ops/export_book_rows.sh`); then
`scripts/dev/scout_merge.py` drops and ranks their rows into
`docs/superpowers/results/<date>-scout-slate.md`.

**Evidence rule** -- the thresholds the role skills point at:

- A cell is **thin** when N < 30 or it spans fewer than 8 distinct ISO weeks
  (`THIN_MIN_N`, `THIN_MIN_WEEKS` in `scripts/reports/autopsy/cells.py`).
  A thin cell is tested and counted, never ranked as evidence; the merge
  drops a row that cites one.
- A row's cell needs a Δ interval (cell minus its complement, week-cluster
  bootstrap) that excludes zero and a Benjamini–Hochberg **q ≤ 0.10** across
  every cell tested. On a schema-2 autopsy the merge keeps an `exploit` row only when the cell's Δ lower bound is above 0, and an `avoid` row only when its Δ upper bound is below 0. It drops a row citing a `fill`- or `outcome`-defined cell as not known at entry, and it keeps one row per rule on a two-value cut. A schema-1 autopsy keeps the old one-sided rule (Δ lower bound above 0) and is marked legacy on the slate;
  the q cut-off is the roles' filter, and `quant-researcher` checks it on the
  slate.
- Every autopsy-derived row carries `exploratory: yes`: the live-book window
  overlaps the 2026 holdout, so a `/prereg` built on one freezes its
  thresholds on windows ending before the autopsy window and records the
  holdout as contaminated for that idea. A `/screen` route is unaffected.
- A row quotes only figures printed in the autopsy Markdown
  (`pooled-numbers`); a playbook row routed to `/screen` needs no cell.

**Boundaries:** a slate row is a hypothesis. No gate moves, nothing edits
code, config, thresholds or live alerts, and no closed pre-registration is
re-run. Every entry or filter idea still needs a `SCREEN-PASS` row before its
spec. No paid usage: the export, autopsy and merge are scripts; the roles run
as subagents.

**Retention:** raw export CSVs stay in the session scratchpad. Each run
commits one `*-book-autopsy.{json,md}` and one `*-scout-slate.md` on `main`.
If three consecutive slates send no row to `/screen` or `/prereg`, the next
session records that in the latest slate and asks the partner whether to
retire the tooling.

## Which agent for what (v107)

Serial, one at a time — except plan parts (§ Plan writing below). Opus
(main session) decides; agents do.

| Work | Agent | Model |
|---|---|---|
| Implement one plan task from its handoff file (`task_handoff.py`, then `/task-brief`) | `task-implementer` | the task's `**Model:**` tier (default sonnet) |
| Review that task's commits against the handoff's deliverables | `task-reviewer` | sonnet |
| Review a spec, plan, diff or result through one expert role (via `/panel`) | `expert-reviewer` | the role's model from § Expert roles |
| Propose hypotheses from a book autopsy through one generator role (via `/trade-scout`) | `scout` | sonnet |
| Gather a plan's code context into one brief | `plan-briefer` | sonnet |
| Draft a plan from an approved spec — index, then parts two at a time | `plan-writer` | opus |
| Read-only production question | `prod-inspector` | haiku |
| Backtest / grid / fold run > ~2 min | `backtest-runner` | sonnet |
| Full or fast suite run | `test-runner` | sonnet |
| Check a plan's symbols exist | `symbol-verifier` | haiku |

Plan loop: `task_handoff.py` → `/task-brief <handoff path>` →
`task-implementer`, dispatched with the task's `**Model:**` tier as the
`model` override (plans above v145; default sonnet) → `task-reviewer`
(always sonnet) → Opus reads findings → next task, or the escalation ladder
in `model-routing.md`: `SendMessage` the same implementer once, then a fresh
implementer one tier up with the findings attached, then Opus inline, each
step logged in `.superpowers/sdd/progress.md`. Brainstorming never goes to
an agent — it needs the partner. `/gate` and `/task-brief` run forked on
sonnet, so their tool output never reaches the Opus context.

### Dispatching a plan task (v199)

1. Write the handoff:
   `python scripts/dev/task_handoff.py <plan file> <id> --worktree <wt> --attribution "<line>"`,
   the attribution line copied from your own system reminder. Its last
   output line is the handoff path (`.superpowers/sdd/<plan base>/task-<id>-handoff.md`
   under the main checkout): the task text verbatim, deliverables `D1`…`Dn`,
   and the environment (worktree, branch, test command, test database,
   frontend wrapper, radon, attribution). Exit 2 names the reason: an id in
   no part or in two, a missing plan file, a handoff `/task-brief` already
   filled, or `no deliverables derivable for <id>`. For the last, fix the
   plan task or fall back to `/task-brief <id>` and a pasted brief; both
   agents then report `DELIVERABLES: n/a (no handoff)`.
2. `/task-brief <handoff path>` fills its Preflight and Code slots and
   nothing else.
3. Dispatch with exactly this prompt — no environment, no plan paths, no
   "sed -n the plan":

   ```
   Implement task <id>. Handoff: <handoff path>. Model tier: <tier>.
   Return the report shape in your agent file.
   ```

   and the reviewer with:

   ```
   Review task <id>. Handoff: <handoff path>. Worktree: <wt>. Commits: <base>..<head>.
   Return the report shape in your agent file.
   ```

4. Plans already in flight switch at their next undispatched task; there is
   no cut-over date.

**Standing cost check.**
`python scripts/dev/agent_cost.py [--agent task-implementer] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--root <dir>]`
reads the subagent transcripts under `$CLAUDE_CONFIG_DIR/projects/<repo slug>/`
(falling back to `~/.claude/projects/`) without changing them, and prints
runs, turns, input tokens, lookups before the first edit, image reads and
plan-file touches; for `task-reviewer`, the share of reports in the
required shape and the `missing`/`different` counts. Run it before and
after any change to an agent file, a preloaded skill or the dispatch
prompt, and compare like with like (same `--agent`, a window wholly after
the change). A non-zero `unparsed` count means Claude Code changed its
transcript format. It stays after v199 (spec v199 § 5).

### Plan writing (two phases)

Measured over nine plan-writer runs (v108–v145): wall time scales with what
is written in one serial context — 13 min for a 70 KB plan, 51–55 min for
170–320 KB — and tool execution is under 10% of it. So the plan is written
in parts, two at a time, to disk as it goes:

0. Dispatch `plan-briefer` with the spec path and
   `.superpowers/briefs/<plan base>.md`. Exploration was most of the old
   cost — 50–390 one-line Opus turns per run, each re-reading a growing
   context, repeated by every part writer. On Sonnet, once, it is one file
   every writer reads. The brief is gitignored but in the shared working
   tree, so a resuming session or account reuses it (re-brief if missing).
1. Dispatch `plan-writer` with `mode=index`, the spec path and the brief path. It writes the
   index first (header, constraints, parallelisation, a task ledger fixing
   every cross-task file and contract). A single-file plan (≤ ~1300 lines)
   comes back `DONE` from this one run. **On `SCOPE`** (ledger over 20 tasks),
   stop: ask the partner where to cut (`AskUserQuestion`) and split the spec
   (`document-conventions.md` § Splitting) before any part is written.
2. On `PARTS`, dispatch one `plan-writer` per part with `mode=part <N>`, the
   spec, index and brief paths — **at most 2 part writers at once**: two in
   one message, the next pair only when both have returned (a part that
   returns `BLOCKED:` frees its slot). This is the standing exception to
   serial dispatch, and it stops at two: four Opus writers at once drain the
   5h window before any part is committed. A resume counts the same —
   incomplete parts are re-dispatched two at a time.
   **Commit the index as soon as phase 1 returns**
   (`docs(vN): plan index -- parts pending`), and each part as it returns, so
   a session that runs out of tokens leaves committed, resumable work.
   **On `SPLIT: <id> -> <id>b`**, add the `b` row to the index ledger directly
   below `<id>` before linting. Part writers own their file and the
   controller owns the index.
3. When all return, run `python scripts/dev/plan_lint.py <index>` — header,
   ledger vs tasks, `Model:` lines, the 1500-line cap, the 20 KB task cap
   and the 20-task plan cap (plans above v196), `Modify:` paths,
   placeholders, in one call. It must print `PASS`; then review and commit.
   Writers run it on their own files before returning, so it replaces the
   validation scripts they used to improvise.

Every writer appends one task per tool call, so the files fill visibly; a
part that finds a wrong shared contract returns `BLOCKED:` instead of
diverging from the ledger.

**Never more than 2 plans being written at once in one session.** A plan
counts from its `mode=index` dispatch until all its parts are committed; a
third waits for one to finish. The 2-writer cap is per session, not per
plan: two plans in progress share the same two slots.

**Running out of tokens is resumed, never skipped.** Any plan whose ledger
lists ids missing from its part files is unfinished: re-dispatch the
`mode=part <N>` writer for each incomplete part. The writer appends from the
first missing id and leaves tasks already on disk alone. An unfinished plan
counts toward the 2-plan limit.

**Handing a plan to another session or account.** Progress lives in the
repo, never in account memory: another account (or Codex) has its own
config dir and sees none of this session's memory or context.
- *Detection is automatic.* The SessionStart hook (`session-cursor.ps1`,
  shared by Claude and Codex) prints `PLAN WIP` for every plan whose
  `## Task ledger` names ids with no `### Task` on disk, with the resume
  command. Resume those before starting anything new.
- *Decisions go in the plan, as they are made.* Any partner answer, a
  `BLOCKED:` resolution or a deviation from the spec is written into a
  `## Handoff` section of the index (single file: of the plan) at once — not
  only into the conversation. The hook points the next session at it.
- *Commit as you go.* Index on return, each part on return, and — when the
  usage watcher warns (≥ 90%) or the session is about to stop — the files on
  disk right away as `docs(vN): plan WIP -- <k>/<n> tasks`. A WIP commit is
  never reviewed or closed out; the resuming session finishes it.

For small edits (a few lines of markdown or config), work inline: every agent
spawn is a cold start that costs more than the edit.
