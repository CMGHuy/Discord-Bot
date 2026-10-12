# v159 — Four new expert seats, a demo-only eToro guard, and the ops/UI rituals

**Version:** ui 1.22.1 · bot 2.3.1 (at writing)
**Bump:** bot patch + ui patch (new eToro settings and a guard module the bot imports; the admin Settings page gains the eToro fields and a confirm step on the real-money unlock; no alert or embed changes)
**Edge:** none (integrity). It protects against the most expensive mistake the roadmap allows: a real-money order placed before stage 3, or by any session or code path that skips the guard. It also closes review blind spots. It adds no strategy, threshold or measurement.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, risk-manager, financial-advisor
**Status:** draft
**Depends on:** v145 (role-skill shape, `expert-reviewer`, `/panel`), v154 (strict frontmatter helper), v155 (slash-only ritual pattern: `/screen`, `/prereg`).

The panel line names seats that already exist. The new `execution-specialist` and `compliance-reviewer` seats would be the natural reviewers, but `test_spec_panel_header.py` rejects a role that has no `## Lens` yet. They review this plan's diff at pre-close-out instead (see § Rollout).

## Why

The roadmap's next three steps each land in an area no seat or ritual covers:

1. **eToro roadmap stage 2 (demo orders)** has no reviewer for order mechanics and no hard stop on the real account. The keys exist (`swingbot/config.py:127-136`) and nothing reads them yet, so this is the cheapest moment to put a guard in. The session hook in `.claude/settings.json:138` has the matcher `Glob|Read|Edit|Write|NotebookEdit|Bash`, which misses both **PowerShell** (the main shell on the Windows dev machine) and every `mcp__*` tool, including the eToro MCP server.
2. **Publishing trade plans on bomeo-capital.com** brings disclosure and promotion rules in three regimes (EU, UK, US) that `financial-advisor` does not cover. That seat judges account fit, not publication.
3. **Production reliability.** v106 failed its third soak (`docs/superpowers/results/2026-10-11-v106-soak-attempt-3.md`): p95 3.37 s against a 3 s limit, and clause (c) was decided by two skips. Soaks and incidents are run ad hoc, with no checklist.
4. **Admin UI and alert UX.** `persona.md` makes Claude the UX designer, but no seat reviews hierarchy, density or what an alert asks the reader to do. No skill covers `frontend/` conventions or the chart renderer, and `alert-surface` explicitly excludes chart images.

## Scope

Three parts, one plan. Part A lands first so parts B and C can be reviewed by the new seats.

### A. Four new expert roles (9 → 13)

Each is a `.claude/skills/<role>/SKILL.md` in the v145 shape (`## Lens`, `## Checklist`, `## Red flags`, `## Out of scope`). The opening paragraph is the same as the existing roles: raise findings, never decide, never lower a gate, cite everything, tag `BLOCKING`/`ADVISORY`. Each gets:
- a row in the `skills-tools.md` § Expert roles table;
- a model pin in `tests/hooks/test_role_skills.py`;
- an entry in the roster `.claude/agents/expert-reviewer.md` hardcodes in three places (description, valid-role list, return shape). Without it `/panel` returns `UNKNOWN ROLE` for every new seat. Those three spots go from "nine" to "thirteen", and so does any count the `panel` skill quotes;
- a Codex mirror: `python scripts/dev/sync_codex.py` plus a condensed line in `AGENTS.md`.

| Role | Reviewer model | Lens | Out of scope (owner) |
|---|---|---|---|
| `execution-specialist` | opus (closest seat to real money) | Order types; limit vs market for resting pre-open orders; stop loss and take profit attached at order time; drift between paper and demo fills; partial fills; idempotent submit and retry; reconciling the journal against the broker book; instrument type (CFD vs real share: leverage, margin, overnight financing, a different gap and stop-fill model); demo-only enforcement (`assert_demo`, part B) and v160's pre-open checks | cap values and sizing policy (`risk-manager`); setup tradeability (`veteran-trader`) |
| `compliance-reviewer` | opus (legal nuance across three regimes) | Regulatory wording and disclosures in content published on bomeo-capital.com and in Discord, checked against EU MAR Art. 20 / MiFID II (investment-recommendation disclosure; whether a public plan with entry, stop and size reads as a **personalised recommendation**), UK FCA financial promotions (fair, clear, not misleading; risk warnings) and US SEC/FINRA (publisher's exemption; hypothetical- and past-performance presentation). Checks against the audience and disclosure text named in `docs/claude/compliance-publication.md` (created by this plan, see below). Paper, demo and real results always kept and labelled apart. Educational only: a doubtful case is a `needs counsel` finding, never a ruling | suitability, cost and tax presentation, alert cadence (`financial-advisor`) |
| `ux-designer` | sonnet | Admin SPA and Discord embeds: visual hierarchy, density, the action an alert asks for, mobile/PWA, accessibility, light and dark themes. How risk and performance are shown: dollar risk and drawdown next to R, total open risk against `PORTFOLIO_HEAT_CAP_PCT`, a badge-tier and staleness cue, ExpR before win rate (`edge-priorities.md`), and a sizing line that does not read as a recommendation. Judges `ui-verifier` screenshots when they're supplied. Wording questions go to `compliance-reviewer` | embed code correctness (`alert-surface`, `senior-engineer`); regulatory wording (`compliance-reviewer`) |
| `sre` | sonnet | Hetzner VM: soak criteria and razor-edge clauses, data-provider failover (yfinance ↔ Alpaca), cron and scheduling, logs and alerting, backup and PITR, capacity | cross-package design (`staff-engineer`); cache and backtest numerics (`quant-engineer`) |

**Red flags that make a finding `BLOCKING`, at least:**
- `execution-specialist`:
  - any order path that skips `assert_demo` or v160's sizing and pre-open checks;
  - order submit without an idempotency key or a journal entry;
  - a market order resting overnight;
  - a position that can exist without an attached stop;
  - any stop move away from price after entry (stops only tighten);
  - instrument type (CFD or real share) not read and journalled.
- `compliance-reviewer`:
  - published performance not labelled paper, demo or real, or two of those mixed in one figure or track record;
  - a figure before costs, financing or tax shown without saying so;
  - win rate led ahead of ExpR;
  - a strategy shown without its badge tier, or a stale figure without its as-of date;
  - publishing only filled or approved plans without stating the filter (cherry-picking);
  - hypothetical results without the method;
  - a published recommendation with no risk warning or disclosure of the author's interest (the partner trades the same alerts).
- `ux-designer`: an alert whose entry, stop or size can't be read on mobile; a theme that breaks contrast; R shown without dollar risk; win rate shown above ExpR.
- `sre`: a pass/fail clause one event can flip, with no flag; work scheduled on the dev laptop; a live change not mirrored.

**Panel defaults.** Add to the `document-conventions.md` panel table. The existing 1–3 roles cap stays.

| Spec is about… | Default panel |
|---|---|
| eToro integration, anything that places an order | execution-specialist, risk-manager, financial-advisor (**`execution-specialist` is mandatory**; financial-advisor covers cost and tax of demo-to-real) |
| Published content (bomeo-capital.com, public channels) | compliance-reviewer, financial-advisor |
| Admin UI | ux-designer, staff-engineer, financial-advisor (replaces the current row) |
| Production ops, soaks, providers | sre, staff-engineer |

`test_spec_panel_header.py` gains a narrow check. A spec numbered above v159 whose header carries `**Places-orders:** yes` must list `execution-specialist`. `/new-doc` asks for that line on any spec touching eToro. The trigger is a header, not a body mention, so a spec that only mentions eToro in passing isn't forced to seat the role. Owner of the check: the `execution-specialist` row in `skills-tools.md`; it retires only if order placement leaves the roadmap.

**Who owns what between `compliance-reviewer` and `financial-advisor`:**
- `compliance-reviewer`: regulatory wording, disclosures, risk warnings, the personalised-recommendation test, and keeping paper, demo and real apart.
- `financial-advisor`: suitability, cost and tax presentation, alert cadence, "never promises returns" framing.
- Both `Out of scope` sections name the other seat.

**`docs/claude/compliance-publication.md`** (new reference doc, plus a row in the `CLAUDE.md` reference table). It names:
- the audience regimes (EU, UK, US);
- the rule that paper, demo and real results stay separate;
- the publish-all-or-state-the-filter rule. Every plan the bot issues is published with its outcome (filled, unfilled, rejected with reason, or not approved), or the page says which subset it shows;
- a **draft** disclosure and risk-warning text, marked `draft — partner to approve`.

The seat checks published content against this doc. It never writes the final disclosure.

### B. eToro demo-only guard and reconciler

Stage numbering follows `docs/claude/etoro-roadmap.md`:
1. keys configured (done);
2. eToro **demo** orders alongside the bomeo-capital page;
3. **real money**.

`CLAUDE.md` § eToro roadmap calls these "Stage 1 (near)" for demo and "Stage 2 (far)" for real; this plan renumbers them to 2 and 3 to match the roadmap.

**B1. Session hook.** Add `_rule_etoro_real_account` to `.claude/hooks/guardrails.py`. It denies:
- an eToro MCP tool call whose input carries `account: real`, `"real"` as the account or environment value, or a real-trading route;
- a Bash or PowerShell command that sends a request to an eToro trading endpoint without a demo marker in the URL or path;
- an Edit, Write or `apply_patch` (Codex) that sets `ETORO_ALLOW_REAL` or `ETORO_REAL_SIGNOFF` in any `.env*` file. Claude and Codex never unlock real money. The partner does it through the admin UI (B2).

Dispatch changes, because `evaluate()` (`guardrails.py:650-676`) looks rules up by exact `tool_name` in `_RULES`:
- `evaluate()` gains a **prefix table**. Any tool name whose server segment contains `etoro` runs `_rule_etoro_real_account`. A test pins it, using the real tool-name prefix read from the installed MCP server. If the server isn't installed, the fragment `etoro` stays the key.
- `evaluate()` swallows every rule exception and allows the call (`guardrails.py:675-676`). So `_rule_etoro_real_account` **must not raise**: its body is a total function over the tool input, with a test that feeds it malformed, empty and non-dict inputs. "An explicit real-account marker is always denied" holds only because of that test.
- **PowerShell gets the Bash command rules.** `PowerShell` has no `_RULES` entry today, so on the main dev shell `_rule_protected_branch_delete`, `_rule_closed_preregistration` and `_rule_screen_rerun` never fire. A `git branch -D *backup*` from PowerShell skips the "never delete a backup branch" guard. Register every Bash command rule, and the new eToro rule, under `PowerShell` too, with a test per rule that a PowerShell input is denied the same way.
- **The `.env` deny joins `_PATCH_PATH_RULES`** (`guardrails.py:629`) so Codex's `apply_patch` path is covered.

Matchers:
- **Claude** (`.claude/settings.json:138`): `Glob|Read|Edit|Write|NotebookEdit|Bash|PowerShell|mcp__.*`.
- **Codex** (`.codex/hooks.json:17`) has its own tool names, so it is **not** a copy of Claude's: `Bash|apply_patch|Edit|Write|mcp__.*`.

`test_codex_mirror.py` compares only hook commands (`:75-76`). It gains an assertion that both matchers include the MCP pattern.

Error policy: a call the rule can't parse is allowed, as with the existing rules. An explicit real-account marker is always denied. A deny prints the reason and points at `etoro-roadmap.md`.

**B2. Code guard.** New package `swingbot/core/broker/`, created by this plan with one module, `guard.py`. v160 (eToro demo mirror) builds the rest of `broker/` (client, sizing, pre-open checks) on top of it. A broker-account guard doesn't fit `core/infra/` ("JSON, locks and delivery channels", `architecture.md:25-27`), and the eToro client imports it from its own package. `architecture.md` § Module map gains `core/broker/`, and the package count in `CLAUDE.md` is corrected in the same commit.

```python
class RealAccountBlocked(RuntimeError): ...

def assert_demo(account: str) -> None:
    """Raise RealAccountBlocked unless account == "demo", or real trading is
    explicitly unlocked (ETORO_ALLOW_REAL=true AND ETORO_REAL_SIGNOFF set to
    an ISO date no later than today, Europe/Berlin)."""
```

**Order-risk checks are v160's, not this plan's** (partner decision, 2026-10-11). The panel's risk findings are applied there, so there is one check per cap and no duplicate code path:
- 2% dollar risk on `ETORO_ACCOUNT_SIZE`: `broker/sizing.py`.
- `MAX_STOP_LOSS_PCT`, portfolio heat and correlated heat at send time: `broker/pre_open.py`.
- The partner's **per-trade invested-amount cap** (`ETORO_MAX_TRADE_USD`, e.g. $100 while the bot plans with $1,000). It is USD because eToro's `amount` is USD-only. Units are scaled down so notional stays under the cap, with entry, stop and target unchanged.
- Stop attached at order time, and **stops only tighten**.

This plan records those additions in v160's spec (§ Panel review below).

**Settings.** New `Field`s in `swingbot/config.py`, section "eToro Paper Trading":
- `ETORO_ALLOW_REAL`: bool, default false.
- `ETORO_REAL_SIGNOFF`: ISO date, default empty.

Help text: real money is stage 3 only, see `etoro-roadmap.md`. The sign-off token is there so stage 3 can never be unlocked by flipping one boolean. `assert_demo` reads both from the hot-reloaded `swingbot.config` settings, never `os.environ`. A test proves a SIGHUP reload flips the result.

**Admin UI unlock path (the partner's choice).** The partner unlocks real money through the admin Settings page:
- `ETORO_ALLOW_REAL` and `ETORO_REAL_SIGNOFF` are editable there.
- Setting `ETORO_ALLOW_REAL=true` needs a confirm step in the SPA. It shows "real money; stage 3; see roadmap" and requires typing the sign-off date.
- `save_settings` (`swingbot/admin/api_v1/system.py:228-247`) rejects a save that sets the flag true without a valid sign-off date.
- `scripts/ops/env_set.py` refuses both keys, so the only routes are the UI or a hand edit of `.env` on the VM.

This is why the release is a `ui patch` as well.

**Tests:**
- `tests/infra/test_config_etoro.py` (the existing pin for this section) gains the two fields: section, defaults, types.
- `tests/broker/test_guard.py`:
  - `assert_demo` cases: demo, real-locked, flag without sign-off, sign-off without flag, future-dated sign-off, unlocked, SIGHUP flip;
  - an AST scan of `swingbot/`, `bot.py`, `admin_ui.py` and `scripts/`. It fails when a module references an eToro host, imports an eToro client, or reads `ETORO_USER_KEY`/`ETORO_API_KEY` without also calling `assert_demo`. Exempt: `broker/guard.py` and `config.py`'s field declarations. The scan passes trivially today and guards v160's client.
- An admin API test that `save_settings` rejects `ETORO_ALLOW_REAL=true` without a sign-off date, and an `env_set.py` test that it refuses both keys.

**B3. `order-safety` skill.** `.claude/skills/order-safety/SKILL.md`. Claude can invoke it itself. It fires before any eToro operation, from MCP, script or code. Checklist:
1. Demo account only, and say so.
2. **One prepare-trade → place-trade per explicit partner approval** (`etoro-roadmap.md` § Rules). Never batch, never place on an earlier approval.
3. A read call first: portfolio, then instrument lookup by symbol. Record the **instrument type (CFD or real share)**, leverage and financing.
4. Build the order through v160's `broker/sizing.py` and `broker/pre_open.py`. A by-hand check of the 2% rule is never a substitute. Stop loss and take profit are attached at order time.
5. Send with an idempotency key.
6. Write a journal entry for every order sent or rejected. A rejection records the `cap` that refused it.
7. Never retry a write blind; read the state first.
8. A stop only ever tightens.

It loads `etoro-public-api-operations` for the API itself. It's out of scope for anything that isn't an eToro operation.

**B4. `reconciler` agent.** `.claude/agents/reconciler.md`: sonnet, read-only (Bash through `ssh-hetzner.sh`, Read, Grep). Inputs: the VM journal and the eToro demo portfolio, read through the MCP server or a read-only route. Output: mismatches only.
- Missing or orphan positions.
- Size or stop mismatch.
- **Any open position without an attached stop.**
- **A stop moved away from price** since entry.
- Dollar risk recomputed from the broker's actual fill and stop, flagged if above 2% of the sizing equity or above the `ETORO_MAX_TRADE_USD` notional.
- **Broker-book portfolio heat against the scanner's heat.**
- Fill-price drift against the paper fill, in R.
- A gap through the stop, reported as the realised loss in R it is.

Returns `CLEAN` when they agree. Dormant until stage 2 places demo orders. This plan fixes its contract and adds a row in `skills-tools.md` § Which agent for what.

### C. Ops and UI rituals

**C1. `/soak`.** Slash-only (`disable-model-invocation: true`), in the v155 pattern.
1. **Pre-register before the window opens.** Clauses, thresholds, measurement definitions and the window dates go into a plan or results doc, committed before the first sample.
2. **Razor-edge check.** For each ratio clause, work out how many events would flip it at the expected N. If it's fewer than 5, flag it in the pre-registration. v106 clause (c) flipped on 2 events in 180 scans.
3. **Sampler on the VM.** A cron mirrored under `scripts/ops/`. The untracked `v106_load_sampler.sh`/`install_v106_load_sampler_cron.sh` are the template; generalising them is a plan task. The v106 session owns committing the originals.
4. **Verdict.** A pooled table plus a per-day table in `docs/superpowers/results/`.
5. **On FAIL.** Diagnose from telemetry only. A retry is a new pre-registration with a new attempt number, never an edit of the old one.

Hook: `_rule_soak_prereg_locked` denies an Edit, Write or `apply_patch` to the thresholds block of a soak pre-registration whose window start date is in the past. The block is delimited by `<!-- soak-prereg -->` markers. Owner: the `sre` row in `skills-tools.md`. The rule costs nothing when there are no markers, so it stays as long as soaks are run.

**C2. `/incident`.** Slash-only.
1. **Triage.** Dispatch `prod-inspector` with one question.
2. **Mitigate.** The smallest change that works, with `mirror-prod` loaded.
3. **Mirror and commit.**
4. **Postmortem.** `docs/superpowers/results/YYYY-MM-DD-incident-<name>.md`: timeline, cause, fix, and a guard against recurrence. A test or hook rule is preferred; "none feasible" needs a reason.

**C3. `frontend` skill.** Claude can invoke it itself when editing under `frontend/`. It covers:
- the `frontend/src/app` layout (`api`, `pwa`, `routing`, `shell`, `stores`, `testing`, `ui`, `workspaces`);
- how the SPA calls `admin_ui.py`;
- how to build and test it;
- theming.

Out of scope: visual judgement (`ux-designer`), alert embeds (`alert-surface`).

**C4. `chart-render` skill.** Claude can invoke it itself when editing `swingbot/core/charts/` (`trade_chart.py`, `decision_chart.py`, `decision_panels.py`, `chart_annotations.py`, `chart_style.py`). It covers:
- which chart each alert path renders;
- annotation layering;
- Discord image size limits;
- render tests.

The NO-LOOKAHEAD boundary: a chart draws only bars the alert knew about. It loads `no-lookahead` when annotations come from computed levels. `alert-surface`'s description gains a pointer to this skill.

**C5. `ui-verifier` agent.** `.claude/agents/ui-verifier.md`: sonnet. Tools: Bash, Read, and the browser (Claude in Chrome, or the built-in browser where available). It:
- opens the admin UI, local or a given URL;
- walks the routes a diff touches;
- takes light and dark screenshots into the session scratchpad;
- reads the console for errors.

It returns findings plus screenshot paths only, and `ux-designer` reviews can cite those paths. It never submits forms that change state, and it never triggers dialogs.

**Not included (YAGNI):** a market-calendar or session skill (no planned work needs one yet), and an SRE agent (`prod-inspector` covers read-only inspection).

## Codex mirror

Every addition ships its mirror in the same commit:
- skills and agents through `python scripts/dev/sync_codex.py`, which already covers skills, slash-only `openai.yaml` and agents;
- the `CLAUDE.md` and `docs/claude/` changes condensed into `AGENTS.md`;
- the Codex matcher (B1, its own tool names) into `.codex/hooks.json`.

`tests/hooks/test_codex_mirror.py` must stay green. `CLAUDE.md` changes are kept small, to respect the 200-line cap:
- the eToro section: "Stage 1 (near)" / "Stage 2 (far)" become "Stage 2 (near)" / "Stage 3 (far)" to match the roadmap, plus one line: "`broker/guard.py:assert_demo` guards every eToro call; `order-safety` fires first";
- one reference-table row for `compliance-publication.md`.

## Testing

- `tests/hooks/test_role_skills.py`: 13 roles, models pinned per the table above, each with all four sections. Also checks that `expert-reviewer.md` lists all 13.
- Skill eval suites (v96 pattern): one positive and one negative prompt per new model-invocable skill (`execution-specialist`, `compliance-reviewer`, `ux-designer`, `sre`, `order-safety`, `frontend`, `chart-render`). The slash-only `/soak` and `/incident` need a test that they're never model-triggered.
- `tests/hooks/test_guardrails.py`:
  - allow and deny cases for `_rule_etoro_real_account` (MCP via the prefix table, Bash, PowerShell, `.env` Edit/Write/`apply_patch`), plus its never-raises cases;
  - `_rule_soak_prereg_locked`;
  - one PowerShell deny case for each Bash command rule now registered under `PowerShell`.
- `tests/hooks/test_codex_mirror.py`: both matchers include the MCP pattern.
- `tests/broker/test_guard.py`, `tests/infra/test_config_etoro.py`, the `save_settings` and `env_set.py` tests: as in B2.
- `tests/hooks/test_spec_panel_header.py`: `Places-orders: yes` requires `execution-specialist`.
- Complexity: every new or changed function stays under 15 (`radon cc -s -n C`).
- One full-suite run, as the plan's final task.

## Rollout

Plan order: A (roles, panel table), then B1 → B2 → B3 → B4, then C1–C5. C has no dependency on B, so C can run in parallel with B once A is done.

The pre-close-out `/panel` on this plan's diff runs `execution-specialist, compliance-reviewer, risk-manager`. The new seats review the guard and the publication wording they were created for, and `risk-manager` re-checks that its blocking findings landed in v160's spec. `/close-out` applies `Bump: bot patch + ui patch`.

## Risks

- **Registering the Bash rules under PowerShell denies a command that used to pass.** That is intended: the backup-branch and pre-registration guards were silently missing on the main dev shell. Mitigation: one test per rule, and the existing allow-on-parse-failure policy.
- **v160 lands before this plan's B2.** v160 depends on `broker/guard.py`, so its eToro-code tasks wait for this plan's B2 merge (v160 § Parallelisation, Group 2).
- **The admin UI unlock is one form away from real money.** That was the partner's choice. Mitigation: the confirm step, the server-side sign-off check in `save_settings`, `env_set.py` refusing the keys, and the hook keeping Claude and Codex out of it.
- **The compliance seat is read as legal advice.** Mitigation: the lens says "educational only" and the `needs counsel` finding type; it never rules.
- **The AST scan for eToro references is evaded by dynamic URLs.** Accepted. The hook, the `order-safety` skill and the `execution-specialist` seat are the other layers. The scan catches the ordinary case: someone writes a client and forgets the guard.

## Open roadmap items (recorded, not decided here)

This plan adds these to `docs/claude/etoro-roadmap.md` as open items. Answering them is the partner's call, in a later spec:

1. **CFD vs real shares decides whether demo evidence counts.** A CFD demo fill carries spread, overnight financing, leverage and the EU retail loss-disclosure regime; a real-share fill doesn't. Answer this **before** demo performance is used as a gate for stage 3, not in the stage-3 spec.
2. **The stage-3 unlock criteria are led by win rate** ("consecutive profitable months, better win rate"), with no minimum N, no drawdown bound and no cost or tax netting. The panel suggests ExpR with a sample floor, a maximum drawdown in dollars, and results net of costs and tax. `quant-researcher` should judge the statistics. The `ETORO_REAL_SIGNOFF` date is a lock, not a performance test.

## Panel review

Spec review on 2026-10-11 over `8cd599bc`, seats run one at a time: staff-engineer (opus), risk-manager (sonnet), financial-advisor (sonnet). The partner decided two points during the review: the admin UI is the unlock path, and eToro uses a per-trade invested-amount cap. On the move to `etoro-migration/` the partner also assigned every order-risk check to v160, so the risk findings below are applied **in v160's spec**, not here.

- risk-manager B1: order-safety checks only per-trade 2%, not portfolio or correlated heat or `MAX_STOP_LOSS_PCT` -- applied in v160 (`pre_open.py` stop, heat and correlated checks)
- risk-manager B2: no code-level sizing guard, the 2% check was prose -- applied in v160 (`sizing.py`, clamped through `capped_planned_loss_pct`, tested)
- risk-manager B3: no stop-at-order-time or stops-only-tighten rule -- applied: red flags and reconciler here; stop-at-order-time and stops-only-tighten added to v160's pre-open checks
- risk-manager B4: demo sizing basis undefined -- applied in v160 (fixed `ETORO_ACCOUNT_SIZE`, plus the partner's `ETORO_MAX_TRADE_USD` invested-amount cap; USD because eToro amounts are USD-only)
- financial-advisor B1: presentation test was only "labelled paper/demo" -- applied (compliance red flags: pre-cost or pre-tax, ExpR first, badge tier, staleness)
- financial-advisor B2: no rule keeping paper, demo and real results apart -- applied (compliance lens, red flag, `compliance-publication.md`)
- staff-engineer A1: new fields appear in admin Settings and are editable there, which the hook never sees -- applied (partner chose the UI as the unlock path; confirm step, server-side sign-off check, `env_set.py` refuses the keys; Bump gains `ui patch`)
- staff-engineer A2: `evaluate()` exact-name lookup misses MCP tools; swallowed exceptions -- applied (prefix table, never-raises tests)
- staff-engineer A3: PowerShell skips every Bash command rule, including the backup-branch guard -- applied (Bash command rules registered under PowerShell)
- staff-engineer A4: Codex matcher is separate; `apply_patch` path; mirror test ignores matchers -- applied
- staff-engineer A5: `infra` is the wrong home for the guard -- applied (`core/broker/guard.py`, the package v160 extends; architecture.md updated)
- staff-engineer A6: flag source and timezone unstated -- applied (hot-reloaded settings, SIGHUP test, Europe/Berlin)
- staff-engineer A7: `expert-reviewer.md` hardcodes nine roles -- applied
- staff-engineer A8: stage numbering differs from the roadmap; order-safety misses one-approval-per-trade -- applied (real money = stage 3, `CLAUDE.md` corrected, checklist step 2)
- staff-engineer A9: `test_config_etoro.py` not extended -- applied
- staff-engineer A10: new rules have no owner; the "mentions etoro" trigger is too broad -- applied (`Places-orders:` header trigger, owners named)
- staff-engineer A11: Bump level -- applied (`bot patch + ui patch`)
- risk-manager A5 / financial-advisor A6: CFD leverage and its effect on demo evidence -- applied to the execution lens and order-safety step 3; the evidence-gate question is recorded as open roadmap item 1
- risk-manager A6: reconciler contract too thin -- applied
- risk-manager A7: rejection reason not journalled -- applied in v160 (skip reasons journalled)
- risk-manager A8: no test ties order params to the plan -- applied in v160 (`tests/broker/test_pre_open.py`, `test_sizing.py`)
- financial-advisor A3: compliance / financial-advisor boundary; personalised-recommendation test -- applied
- financial-advisor A4: no audience or disclosure artefact -- applied (`compliance-publication.md` with draft text for partner approval)
- financial-advisor A5: ux lens lacks risk and performance display -- applied
- financial-advisor A7: stage-3 criteria led by win rate -- rejected for this spec: the roadmap criteria are the partner's; recorded as open roadmap item 2
- financial-advisor A8: publish-all-or-state-the-filter -- applied (`compliance-publication.md`, compliance red flag)
- financial-advisor A9: no seat for tax drag on eToro specs -- applied (financial-advisor added to the eToro panel default)
