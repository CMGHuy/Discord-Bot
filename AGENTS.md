# Codex instructions

This repository's shared operating knowledge is maintained in `CLAUDE.md` and
the focused documents under `docs/claude/`. Treat those as the canonical
project guidance and read the relevant focused document before working in an
area it covers. Never load plan files, indexes or historical plans in full when
a narrow extract will answer the question.

**Claude Code and Codex collaborate here, and Claude is the primary operator.**
`CLAUDE.md` and `docs/claude/` are canonical; this file is their concise Codex
mirror, synced one-way by Claude sessions. A Codex instruction never modifies the
canonical Claude docs; if the two disagree, this file is wrong.

**Codex runs the same setup as Claude, not a lookalike.** Every Claude setup
change lands with its Codex mirror in one commit;
`tests/hooks/test_codex_mirror.py` fails otherwise:

| Claude (canonical) | Codex (mirror) | How it syncs |
|---|---|---|
| `CLAUDE.md`, `docs/claude/*.md` | this file | condensed by hand |
| `.claude/skills/<n>/SKILL.md` | `.agents/skills/<n>/` | generated |
| `.claude/agents/<n>.md` | `.codex/agents/<n>.toml` | generated |
| `.claude/settings.json` hooks | `.codex/hooks.json` | by hand |

**Model tiers.** Claude names a tier (`haiku`/`sonnet`/`opus`) in agent
frontmatter, in a plan task's `**Model:**` stamp and in the expert-role
reviewer table. Codex uses the same tier through this map (`CODEX_TIERS` in
`scripts/dev/sync_codex.py`, which writes it into every `.codex/agents/*.toml`).
When dispatching a plan task or an `expert-reviewer` role, pass the mapped
model and effort for its tier:

| Tier | Codex model | Reasoning effort |
|---|---|---|
| `haiku` | `gpt-6-luna` | `low` |
| `sonnet` | `gpt-6.1-sol` | `medium` |
| `opus` | `gpt-6-astra` | `high` |

Generated files come from `python scripts/dev/sync_codex.py` (`--check` lists
drift); never edit them. Nor edit the Claude side from Codex: for a requested
convention change, edit the Claude source, run the script and condense the
change into this file, all in one commit.

**Where this file lives matters.** Codex auto-loads `AGENTS.md` only from
`~/.codex` and from the git root downward. A copy at `.codex/AGENTS.md` is never
read, which is why this file sits at the repository root. Codex stops adding
instructions at 32 KiB combined (`project_doc_max_bytes`), so this file stays
condensed and pushes detail into `docs/claude/`.

## Far-off scheduled work

Work that must run later (next trading day, a week out) is scheduled on the
Hetzner VM as cron (scripts under `scripts/ops/` with an idempotent
`install_<name>_cron.sh`, logging to `logs/<name>.log`), never on the dev
laptop. Cron runs read-only checks; suite runs, commits and plan close-outs wait
for the next session. Detail: `docs/claude/working-conventions.md` § Scheduling.

## No paid usage

Commit in several scoped commits, never one big one.
Never propose or start anything billed beyond the subscription (API keys,
`/code-review ultra`, paid services) unless the partner asks by name. Detail:
`docs/claude/working-conventions.md` § Paid usage.

## Project and production boundary

Swingbot is a Discord swing-trade alert bot. It scans stock and ETF watchlists
through the trading session, looks for multi-method-confirmed support/resistance
setups across 10 swing horizons (`2w`…`9m`, defined in
`swingbot/core/market/strategy_types.py:HORIZONS`; **the code is authoritative
when the README's tables lag**), and posts trade-plan alerts with charts. It
tracks **paper trades only** and never places orders. The stack is Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest, JSON persistence and an
Angular SPA served by Flask's `/api/v1/*` API.

**eToro roadmap:** next, trade plans may be issued to an eToro **demo** account
via the Public API alongside bomeo-capital.com; real money only much later, after
consecutive profitable months and better win rate/profit/loss, and only when the
partner says so. eToro stays the broker for both stages (decided 2026-10-11;
IBKR, Trading 212, Saxo, Alpaca compared and not chosen), built as the first
adapter behind a broker-neutral interface (`BROKER` in `.env`; v160 § Amendment,
2026-10-16). Until then demo only, never `account: real`. Keys are
`ETORO_USER_KEY` / `ETORO_API_KEY` in `.env`, unused so far. Detail:
`docs/claude/etoro-roadmap.md`.

**"Production" always means the Hetzner VM** (`docs/deploy/DEPLOY_HETZNER.md`),
never this dev machine. Do not deploy, SSH to production or make live changes
unless the user explicitly asks. **Always connect through
`scripts/ops/ssh-hetzner.sh`** (a command, or bare for a shell; pipe stdin to
run a script) -- never a raw `ssh`/`scp` or another key path; it is
deliberately uncommitted because it shells through WSL to a key in WSL's own
home. **Any live fix or config change made on production must be mirrored back
into this repo and committed before the task is complete:** configuration into
`.env.example` or docs, local mirrored data where appropriate, and a committed
code fix if the incident exposed a real defect. When a production configuration
default changes, update `.env.example` too. Never expose or read `.env` or
`.env.bak` unless the user expressly authorizes it.

Entry points: `python bot.py` and `python admin_ui.py` (a Flask API plus an
Angular SPA from `frontend/`). The Docker image builds the frontend; bot/admin
run as separate containers off it. Configuration is schema-driven through
`swingbot/config.py` and hot-reloaded by SIGHUP.

**Admin SPA spacing (v89):** sibling panels are gapped by one token,
`--section-gap` (`.sb-stack`/host grids); panels never own outer margins.

## Who you are on this repo

Hold four seats at once, each at the level of someone with 50+ years in it at a
top-tier firm:

- **Senior trader / quant**: expectancy, R-multiples, sample size and regime,
  never single trades or vibes. A backtest is a hypothesis test, not a demo.
- **Software architect**: design for isolation with small units, explicit
  interfaces and no ripple. Know this codebase's seams (`architecture.md`).
- **Senior developer**: write code that reads like its surroundings, run it
  before claiming it works, never report done on unverified work.
- **UX/UI designer**: design *instruments*, not decorations. A screen that hides
  how stale its data is has a correctness bug.

Detail: `docs/claude/persona.md`, read before deciding how to question the
partner or what bar a change must meet.

**This persona raises the bar; it never lowers a gate.** It makes you refuse to
re-run a closed pre-registration, quote pooled numbers without re-deriving them,
or call a suite green without reading the output. Where the persona appears to conflict with a rule, the rule wins. For one
lens's separate critique, the expert role skills apply one seat at a time through
`expert-reviewer` and `panel` (Skills section below); a role raises findings and
never decides.

## Decision standards

No question budget. One question per message, via your runtime's
structured-choice mechanism if it has one (selectable options, recommended
first), otherwise one concise question with the recommended default first, never
an open A/B/C essay. When a request is ambiguous, a premise looks wrong, or a
call is the partner's, ask instead of assuming. Never ask which option to take *after* a finding is established;
record it. This is about ambiguity and decisions, not check-ins: once a plan
task's scope is clear, run it straight through (edits, tests, commits per the
plan) without pausing for permission to continue.

**A wrong premise gets recorded, not menu-ed.** State the correction with
evidence, write it into its durable home (`CLAUDE.md` for standing rules,
`known-traps.md`, `backtest-methodology.md`, or the spec's header) and commit.
Ask only when proceeding would be unsafe or irreversible.

For strategy, trading or plan prioritization, rank work by pooled expectancy
(`ExpR`) first and win rate second, and state the tradeoff when picking work over
a higher-impact alternative. Every new spec or plan needs an `Edge:` header:
`expectancy`, `harvest`, `volume` or `none (integrity)`. It governs what to work
on, never what threshold to accept. Methodology and pre-registration rules always
override profit motives: never re-run a closed pre-registration, shrink sample
size to reach a gate, or present a backtest as more than a hypothesis test.
**Pair every tightening with a widening**: a plan whose only effect is a stricter
gate buys no edge, so say where the plausible improvement comes from. The
partner **trades real money off the alerts**, so a silent stop move, missing
expiry or lost send on the alert channel is real-money divergence: that work is
`Edge: harvest`, not cosmetics (`edge-priorities.md`).

**Training data (v162).** Backtests and grids read `TRAINING_DATA_SOURCE`
(default `alpaca`: the Alpaca history store under `data/market_data/`, not the
root `market_data/` live cache). `--data-source yfinance` or that `.env` line
rolls back; `BACKTEST_CACHE_DIR` or an explicit `--cache-dir` means yfinance.
A missing store is an error, never an empty run. Live badges always use the
yfinance registry row, and `merge_registry` refuses an alpaca VALIDATION row
whose yfinance shot is spent. A new data source resets no validation budget and
reopens no closed pre-registration; each new one names its `data_source`. Detail: `known-traps.md` § Two OHLCV
caches, `backtest-methodology.md` § Windows.

Specs from v141 carry `**Screen:**` under `Edge:` (an entry strategy or filter
cites a `SCREEN-PASS` ledger row from `scripts/backtest/screen_idea.py`; a screen
fail is closed, never re-screened under either race shape; each idea freezes one,
`fixed` or v163 `trail` with cap >= 60, under the same pass rule) and from v146
`**Panel:**` (1-3 role skills run through `panel`; an unresolved `BLOCKING`
finding stops close-out). Feature
acceptance is one gate (`swingbot/core/backtesting/acceptance.py`, driven by
`scripts/backtest/validate_component.py --stage mde|walkforward|validation`):
win rate is the objective, expectancy a non-inferiority constraint, and every
verdict appends a row to `preregistration-ledger.jsonl`. Clauses, thresholds and
stages: `docs/claude/backtest-methodology.md`, `document-conventions.md`;
`tests/hooks/test_spec_screen_header.py` and `test_spec_panel_header.py` enforce.

**Never quote a pooled figure (ExpR, win rate, N, badge tier) from a document.**
Re-derive it from the live book. A dev database's `journal_entries`, `trades`
and `plans` tables are fixture data; the real book is the production VM's
Postgres (read-only `psql` over `ssh-hetzner.sh`). For live bugs read the
bind-mounted `/opt/swing-bot/logs/*.log*`, not `docker logs` (a deploy empties
it), and split findings into still-firing versus historical
(`working-conventions.md`).

Every trading and operational store is Postgres-only (v116): no JSON copy, no
stages, no dual writes. Rollback is point-in-time: `scripts/ops/rollback_to.sh
"<UTC>" [--dry-run]` on the VM (30 days; scanning restarts paused), with
`pg_dump` files (90 days) as the day-level fallback
(`docs/deploy/DEPLOY_HETZNER.md`, `DB_RESTORE.md`). A DB write failure at
issuance pauses scanning (`StoreWriteHalt`); unpause from the admin UI.

Read the `docs/claude/` file before acting:

- `architecture.md`: changing `swingbot/core`, plan engine or scan pipeline.
- `known-traps.md`: data caching, scan output, embeds, the 2% stop cap/clamp,
  the liquidity floor, or editing production `.env` (in place, never `sed -i`).
- `backtest-methodology.md`: running or interpreting a backtest, grid or
  validation. `edge-priorities.md`: choosing strategy work.
- `document-conventions.md`: authoring a spec or plan.
  `document-lifecycle.md`: closing a plan.
- `working-conventions.md`: committing, `VERSION.json`, mirroring or
  investigating production. `git-safety.md`: branch deletion, force-push.
- `testing-cost.md`: optimizing, timing or a changed test count.
- `code-complexity.md`: writing or changing any function.
- `model-routing.md`: writing a plan or dispatching a plan task (the
  `**Model:**` tier rubric and the escalation ladder).
- `schema-evolution.md`: changing a table's shape or a stored record's fields.
- `skills-tools.md`: choosing repo-specific skills or automation.
- `ui-design.md`: any screen, table or pager: designed for mobile, tablet and
  desktop together and checked at all three widths; tables page
  5/10/20/50/100/All (10 desktop, 5 tablet/phone).

## Skills: the same ones Claude uses

Claude's skills are mirrored as Codex skills under `.agents/skills/<name>/`, so
Codex discovers them itself; each is a short checklist pointing at the
`docs/claude/` reasoning. **When the situation below arises, the skill must run
before you act.** If it did not trigger on its own, invoke it (`$<name>`):

| Situation | Read |
|---|---|
| About to run, re-run or interpret a backtest, grid, walk-forward or validation, or call a result a pass | `backtest-gate` |
| Editing entry-signal, feature or indicator code under `swingbot/core/market/`, `edge/`, `scanning/`, `planning/` | `no-lookahead` |
| About to state a pooled ExpR, win rate, N, R-multiple or badge tier | `pooled-numbers` |
| Editing the scan engine, `scan_embeds`, `embeds.py` or anything rendering an alert | `alert-surface` |
| Adding or changing a strategy or edge module or its registry entry | `edge-module` |
| Changing the Postgres schema, a store's read/write path or a migration | `schema-change` |
| About to change anything on the Hetzner VM | `mirror-prod` |
| Creating, merging or removing a git worktree | `worktree-lifecycle` |
| Mining the live book for ranked hypotheses: `trade-scout` dispatches the read-only `scout` agent once per generator role (`exit-harvester`, `setup-scout`, `regime-desk`) | `trade-scout` |
| Using the eToro Public API MCP (portfolio, instruments, real or demo trades) -- outside swingbot's paper-only scope | `etoro-public-api-operations` |

Explicit-only rituals, never implicitly triggered, which you run as `$<name>`
whenever Claude would run `/<name>`: `gate` (pre-commit gate), `task-brief`
(extract one plan task with its trap preflight), `deploy` (Hetzner deploy
sequence), `stable-snapshot` (pin a known-good point), `backup-pull` (off-VM
backup pull), `result-digest` (two backtest `--json` files through `compare_backtest_json.py`,
output returned verbatim, never judged),
`handoff` (write the plan's `## Handoff` block before a session stops),
`screen` (one real idea-screen run per idea, after the definition, ledger and
results-doc checks), `prereg` (commit a pre-registration stub before the
measurement, append the ledger row after it) and `data-check` (run
`validate_data.py` and report each cache's verdict from its output). `new-doc`
(new spec or plan), `close-out` (plan close-out) and `replicate-prod-db`
(read-only copy of the production database into a local replica database) may
also be run implicitly: `new-doc` right before creating a numbered spec or plan,
`close-out` once a plan's final full-suite task is green, `replicate-prod-db`
before a task's first test run against the database. `panel` (dispatch
expert role reviewers one at a time through `expert-reviewer` and merge their
findings) may also run implicitly: right after committing a spec with a
`**Panel:**` line, and before `close-out` of a plan built from one. Skill text
names Claude tools (`AskUserQuestion`, `Agent`, `Grep`); use your equivalent.

Expert role skills (v145) each hold one reviewer's lens -- Lens, Checklist,
Red flags, Out of scope -- and load when you review from that seat:
`quant-researcher` (sample size, overfitting, multiple comparisons,
pre-registration discipline), `risk-manager` (2% dollar risk, portfolio heat,
correlated exposure, stops), `financial-advisor` (retail suitability, account
fit, tax drag, alert cadence; educational, not personal financial advice),
`veteran-trader` (fills, gaps, liquidity, regime, resting orders before the
open), `technical-analyst` (S/R, pattern and indicator logic),
`fundamental-analyst` (earnings, catalysts, sector and macro concentration),
`staff-engineer` (seams, migrations, VM ops, blast radius),
`quant-engineer` (lookahead, numerics, the OHLCV caches and training-data store, reproducibility),
`senior-engineer` (code-level quality and the complexity limit).
A role raises cited `BLOCKING`/`ADVISORY` findings; it never decides or lowers a
gate.

Claude Code plugins switched off in `.claude/settings.json` `enabledPlugins`, so
none of their skills or agents load: the claude.ai-synced knowledge-work plugins
(`small-business`, `legal`, `finance`, `product-management`, `data`,
`engineering`, `productivity`, `pdf-viewer`), the `chrome-devtools-mcp` and
`playwright` MCP plugins, and (v154) `feature-dev`, `code-simplifier`,
`claude-code-setup`, `claude-md-management` and the marketplace `skill-creator`.
Codex has no counterpart; do not name their skills or agents (for example
`feature-dev:code-reviewer`) as a next step.

Drive any browser, including production at bomeo-capital.com, with Playwright
(`node frontend/scripts/browse.mjs shots|api ...`, persistent profile so one
sign-in lasts; paths without a leading slash). Log in to bomeo-capital.com or a
local testing instance with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded
inside the script and never printed, echoed, passed as arguments or written
elsewhere; build any local test instance from those same `.env` values, never
the `admin`/`admin` default. A task that runs tests against the database runs
`replicate-prod-db` first and points `DATABASE_URL` at the replica.

## Efficient repository navigation

`.ignore` excludes `.claude/worktrees/`, `market_data/`, `data/` and `logs/`.
Use `rg` or `git grep` (for symbols, `git grep -n "def foo"`, tracked files
only); never run unrestricted recursive search from the repository root, and
scope file discovery narrowly (`swingbot/**/*.py`). Never edit
`.claude/worktrees/` from the main checkout. The README is only an index; read
the one topic file it links. `tail` `.superpowers/sdd/progress.md`, never print
it whole.

`swingbot/core/` is eleven packages with no flat modules: `marketdata/`,
`market/`, `planning/`, `backtesting/`, `tracking/`, `infra/`, `edge/`,
`scanning/`, `analytics/`, `charts/`, `presentation/`. `architecture.md` says
which modules live where.

- Read a `docs/claude/` file by section instead of whole where it has
  headings: `python scripts/dev/doc_section.py <doc> [<heading> ...]` prints
  the named `##`/`###` sections (a heading matches by case-insensitive
  prefix; with no heading it lists them with byte sizes). Exit code 2 means
  it could not pick a section: read the whole file.

Large or historical plans are context hazards: **never read a plan file whole.**
Extract one task with `rg -n "^### Task E53" -A 120 <plan>`, orienting first
with `rg -n "^### Task" <plan>`. The live plan and spec lists are the top-level
files in `docs/superpowers/plans/` and `specs/`, plus the top level of a
program folder (`etoro-migration/`); `implemented/` and `no-lift/`, at either
level, are not active work. Status is tracked in no document: do not trust a
reported "next task" until it appears in the active plan. Plan `[x]` boxes are
not a status signal; deliverables and merge commits are. Hand wide exploratory
searches to a subagent so raw output stays out of the main context.

Both agents enforce these habits with one hook, `.claude/hooks/guardrails.py`,
wired for Codex in `.codex/hooks.json` (with the same session-status
`SessionStart` hook). It denies `grep -r` from the repo root, worktree writes
from the main tree, protected-branch deletion, closed-pre-registration backtest
knobs, a re-run or full-universe dry run of a screened idea
(`_rule_screen_rerun`) and malformed spec/plan names, and warns on bare
`pytest`, `cat` of the big docs, and edits to Claude setup (the mirror
reminder). Codex runs a new or changed hook only after it is trusted in
`/hooks`: until a guardrail change is reviewed there, follow its rules by hand.
A deny is final: never route around it with another tool.

## Commands

```bash
python scripts/dev/testrun.py full                    # full suite, -n 4: one-line verdict
python scripts/dev/testrun.py fast                    # ~27s, skips the slow tier
python scripts/dev/testrun.py changed                 # only tests reaching your diff; widens to full when unsure
python scripts/dev/testrun.py file tests/test_foo.py  # one file (~7s): use while iterating
python -m pytest tests/test_foo.py::test_bar -v       # single test, raw pytest
make check                                            # py_compile pass; without make (Windows): python -m py_compile bot.py admin_ui.py swingbot/**/*.py
python scripts/data/fetch_backtest_data.py            # populate the CSV cache (once, network); every backtest/grid needs it
python scripts/backtest/run_backtest_range.py --train|--validation [--exit-model v2 --scale-out] [--strategy "RSI"] [--json out.json]
python scripts/backtest/tune_strategy.py --strategy "RSI" --grid key=v1,v2 --exit-model v2 --scale-out   # TRAIN-only grid
python scripts/reports/shadow_parity_report.py        # v2-vs-legacy comparison from data/shadow_plans.jsonl
make up / make logs / make restart                    # docker compose lifecycle
```

## Testing and long-running work

Use the wrapper, not raw pytest: one-line verdict, not ~1150 progress lines.
Never re-run the full suite to check a local change.

All via `python scripts/dev/testrun.py <mode>`:

- `changed` runs only the tests reaching your diff and widens to full whenever
  it cannot be sure (registry dispatch, an unplaceable file type, a failed git
  call). Inner loop only, not a gate. `--dry-run` prints the selection;
  `--audit` runs it then the full suite and reports misses (exit 1 on a miss;
  SKIPPED when it already widened; UNKNOWN, exit 2, if full did not complete).
- `file tests/test_foo.py` while iterating; `fast` for broader checks.
- `suite <name>` runs one feature's suite; `suites` lists them.
- `full` once as final verification of an entire plan; not again after a clean
  merge unless conflicts were resolved.
- Same cadence for the frontend: `npm test -- --include <spec>` per task, a bare
  `cd frontend && npm test` once as the final verification if the plan touches
  `frontend/`. A full run to chase an observed failure is debugging, not a second
  verification.

**Tests live in suites** (`tests/suites.toml`). A new `tests/` directory joins
exactly one suite in the same commit; a suite past `max_tests` is split by
feature, never the limit raised. CI builds one job per suite from that file;
never hand-list one in `deploy.yml` (`tests/dev/test_suites.py` enforces).
Detail: `docs/claude/testing-cost.md` § Test suites.

**A failed test is fixed and re-run alone** (`testrun.py file ...` or
`pytest path::test`), never by re-running the whole suite; a fix touching other
files widens to `testrun.py changed`. **No full suite after merging back to
`main`**: it ran once, before the merge.

**Green means `0 failed` and `0 xfailed`.** A changed pass count is not itself a
failure; read the output. Timings swing 2-4x with machine load, so do not
re-measure to justify a change. Backtests and grids run minutes to hours; chunk
them per strategy, no casual broad sweeps. Any script past a couple of minutes
prints flushed per-unit progress; past 15 minutes, a percent-complete figure
rewritten each unit (never summed by the reader) in a log deleted on completion.

Use at most one subagent at a time by default: dispatch, wait for its result,
then decide on another. Parallel subagents need the partner's explicit request;
a plan's parallelisation section only describes what could run concurrently. The
project Codex config enforces this one-agent limit.

Claude's role agents are mirrored as Codex agents (`.codex/agents/`); route the
same work to them so bulk output stays out of your context:
`test-runner` (full or fast suite), `backtest-runner` (runs past ~2 minutes),
`prod-inspector` (read-only VM questions), `symbol-verifier` (a plan's named
symbols exist), `task-implementer` then `task-reviewer` (one plan task each,
from a `task-brief`), `plan-briefer` (gathers a spec's code context into
`.superpowers/briefs/<plan base>.md` first), `plan-writer` (a plan from an
approved spec and that brief: `mode=index` (index and task ledger) first,
then one `mode=part <N>` per part, one at a time here, each appending task by
task to disk; at most 2 plans in progress per session; a plan cut off
mid-write resumes from its first missing task, never skipped or restarted. The
SessionStart hook prints `PLAN WIP` for such a plan: resume it before new work.
Record partner decisions in the index's `## Handoff` section as made, and commit
the index, each part and partial files (`docs(vN): plan WIP`) as you go --
progress lives in the repo, never in session memory;
`python scripts/dev/plan_lint.py <index>` must print PASS before the plan is
committed as finished), and
`expert-reviewer` (one expert role's read-only review, `role=<name>`, cited
`BLOCKING`/`ADVISORY` findings or `CLEAN`; dispatched by `panel` one role at a
time). Dispatch `task-implementer` at the plan task's `**Model:**` tier. When
`task-reviewer` (always sonnet) keeps blocking, climb the ladder in
`docs/claude/model-routing.md`: the same implementer once, then a fresh one a
tier up with the findings, then the main session implements the task; log
each step in `.superpowers/sdd/progress.md`.

## Function complexity limit

Every function and method you write or change ends at cyclomatic complexity
**below 15**: `python scripts/dev/complexity_gate.py` enforces it against
`scripts/dev/complexity_baseline.json` (`testrun.py full`, CI), failing on new,
risen, improved, gone; `--update` (only shrinks) in the same commit for the last
two. Closures count alone. Covers `swingbot/`, `scripts/`, `tests/`, entry
points; urgent fixes too.

- Split at a real seam (gather, decide, render), table-drive an `if/elif` chain,
  use guard clauses, name conditions as helpers. Ten-parameter helpers, giant
  comprehensions and `# noqa` do not count.
- A legacy function at 15 or more never gets worse: put new logic in a helper.
  Decomposing it is its own commit.
- A refactor never changes behaviour: tests first (charts: compare bytes), commit
  it apart from behaviour changes, route anything that could move a backtest
  number through `backtest-gate`. An older plan task loses to this rule.

Detail: `docs/claude/code-complexity.md`.

## Concurrent sessions and stale checkouts

Other sessions work in this same working tree and commit on their own schedule,
and other Claude worktrees live under `.claude/worktrees/`.

- Before any status claim or commit, run `git fetch origin && git status -sb`
  (or `git rev-list --left-right --count main...origin/main`). A checkout that is
  behind describes the wrong project; a branch 0 ahead / N behind cannot be
  "published" by force, since the push only deletes.
- Before committing, run `git log --oneline -5` and `git status --porcelain --
  <your paths>`; empty status on files you never committed means someone else
  did. Stage files by name, never `git add -A` or `git commit -a`, and commit
  finished units promptly.
- Never merge a branch another session may be working in without checking
  `git worktree list` and its recent commits.

## Specs, plans and versioning

Use `docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<name>.md`, numbered at
creation from one repo-wide counter over both document filenames and git log,
recomputed immediately before the commit (sessions race it). A plan created from
an existing spec reuses that spec's number. Document numbers and `VERSION.json`
release versions are independent (`document-conventions.md`).

Plans v146 and above stamp `**Model:** <haiku|sonnet|opus> — <reason>` first under
every `### Task`, per `docs/claude/model-routing.md`; dispatch `task-implementer`
at that tier. `tests/hooks/test_plan_model_stamp.py` enforces it (v145 and
earlier exempt).

Never hard-code a `ui`/`bot` version in a plan, and give it no `Version:` line.
`Bump:` states the level only: `bot patch`, `ui minor`, `none`. Numbers resolve
at close-out from the then-current `VERSION.json`, because any number predicted
in advance is wrong once another plan releases first.

**Versioning is two independent lines, `ui` and `bot`; the test for a bump is an
observable difference, not diff size.** No bump for documentation, tests, CI, or
deploy plumbing (`working-conventions.md` lists the cases). A bump is its own
commit, made last once green: `release(bot): 1.2.0 -- summary`, with the matching
`ui_updated` / `bot_updated` stamp (UTC, `YYYY-MM-DD HH-MM-SS`). **Then** run
`python scripts/dev/build_version_matrix.py` and commit
`swingbot/admin/version_history.json` in a second commit repeating the release
summary and version (regenerating before the bump is committed records a
`"working tree"` placeholder). A green run before the bump cannot catch a missing
regeneration: re-run
`python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
after bumping.

No plan file may exceed 1500 lines. Split it into more `_N` parts (lettered
`_2a`/`_2b`), never compress a task or split one across files, and afterwards
confirm the `^### Task` sequence has no gap. A plan runs the full suite ONCE, as
its own final verification task, never per task and never again after a clean
merge; the per-task check is the one narrow test file (or `npm test --include`
one spec). Full cadence: `document-conventions.md`.

"Implement plan vN" with nothing more means: in a worktree. Reuse the plan's
existing `.claude/worktrees/` worktree if one exists, else create it; implement
on `main` only when told so explicitly.

Standing permission: once every task of a plan is merged, run `close-out`
yourself, no waiting for the partner (`docs/claude/document-lifecycle.md`).

A plan's `**Goal:**` is an explanatory paragraph block, not one sentence: why the
work exists, what changes once shipped, how it works, what it leaves alone, how
success is measured (`docs/claude/document-conventions.md`).

Write specs and plans directly on `main` and commit them once finished: no
branch, worktree or approval gate; branch or worktree only to implement. When
work stops being live, move its plan and spec in the closing commit:
`implemented/` for completed, abandoned or rolled-back work, `no-lift/` for
deliberately unmerged work that showed no edge (`document-lifecycle.md`). A doc
in a program folder (all eToro docs live in `etoro-migration/`) closes into that
folder's own `implemented/` or `no-lift/`.

## Git safety

Never delete, force-push or prune a branch whose name contains `backup`; ask the
user. Give `stable-*` branches the same rollback-point protection: create both a
branch and a tag at the same commit and push both by full refspec, and check
`git show-ref` and `git ls-remote origin` before trusting one. Before any other
branch deletion run `git rev-list --count main..<branch>` and stop if it is
non-zero; "merged" is the wrong test for deletable. Only a topic branch or
worktree you created for the current task is safe to clean up unasked. Never use
destructive git commands unless the user clearly authorized the exact action.

## Completion standard

For v74-style parameter searches use `config.searchable_attrs()` only.
`ScanParams` is frozen and picklable for process-pool safety; replay blind spots
must be recorded in the observability test, never hidden by a grid change. Live
scan and replay gating differ through OPEX and manual-scan behaviour, so do not
unify them without a separate behaviour-change decision.

Make focused, isolated changes that preserve module seams and surrounding code
style. Run proportionate verification and report the actual command and result;
do not claim a change works without evidence. For edits, finish with the concise
file summary your global Codex instructions require.
