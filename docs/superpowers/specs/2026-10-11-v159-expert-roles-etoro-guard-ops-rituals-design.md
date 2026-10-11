# v159 — Four new expert seats, a demo-only eToro guard, and the ops/UI rituals

**Version:** ui 1.22.1 · bot 2.3.1 (at writing)
**Bump:** bot patch (one new `.env` field and a guard module the bot imports; no alert, embed or UI changes)
**Edge:** none (integrity). It protects against the most expensive mistake the roadmap allows, a real-money order placed before stage 2. It also closes review blind spots. It adds no strategy, threshold or measurement.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, risk-manager, financial-advisor
**Status:** draft
**Depends on:** v145 (role-skill shape, `expert-reviewer`, `/panel`), v154 (strict frontmatter helper), v155 (slash-only ritual pattern: `/screen`, `/prereg`).

The panel line names seats that already exist. The new `execution-specialist` and `compliance-reviewer` seats would be the natural reviewers, but `test_spec_panel_header.py` rejects a role that has no `## Lens` yet. They review this plan's diff at pre-close-out instead (see § Rollout).

## Why

The roadmap's next three steps each land in an area no seat or ritual covers:

1. **eToro stage 1 (demo orders)** has no reviewer for order mechanics and no hard stop on the real account. The keys exist (`swingbot/config.py:127-136`) and nothing reads them yet, so this is the cheapest moment to put a guard in. The session hook in `.claude/settings.json:138` has the matcher `Glob|Read|Edit|Write|NotebookEdit|Bash`, which misses both **PowerShell** (the main shell on the Windows dev machine) and every `mcp__*` tool, including the eToro MCP server.
2. **Publishing trade plans on bomeo-capital.com** brings disclosure and promotion rules in three regimes (EU, UK, US) that `financial-advisor` does not cover. That seat judges account fit, not publication.
3. **Production reliability.** v106 failed its third soak (`docs/superpowers/results/2026-10-11-v106-soak-attempt-3.md`): p95 3.37 s against a 3 s limit, and clause (c) was decided by two skips. Soaks and incidents are run ad hoc, with no checklist.
4. **Admin UI and alert UX.** `persona.md` makes Claude the UX designer, but no seat reviews hierarchy, density or what an alert asks the reader to do. No skill covers `frontend/` conventions or the chart renderer, and `alert-surface` explicitly excludes chart images.

## Scope

Three parts, one plan. Part A lands first so parts B and C can be reviewed by the new seats.

### A. Four new expert roles (9 → 13)

Each is a `.claude/skills/<role>/SKILL.md` in the v145 shape (`## Lens`, `## Checklist`, `## Red flags`, `## Out of scope`). The opening paragraph is the same as the existing roles: raise findings, never decide, never lower a gate, cite everything, tag `BLOCKING`/`ADVISORY`. Each gets a row in the `skills-tools.md` § Expert roles table, a model pin in `tests/hooks/test_role_skills.py`, and a Codex mirror (`python scripts/dev/sync_codex.py` plus a condensed line in `AGENTS.md`).

| Role | Reviewer model | Lens | Out of scope (owner) |
|---|---|---|---|
| `execution-specialist` | opus (closest seat to real money) | Order types; limit vs market for resting pre-open orders; drift between paper and demo fills; partial fills; idempotent submit and retry; reconciling the journal against the broker book; demo-only enforcement (part B) | sizing, heat (`risk-manager`); setup tradeability (`veteran-trader`) |
| `compliance-reviewer` | opus (legal nuance across three regimes) | Published wording, on bomeo-capital.com and in Discord, against EU MAR Art. 20 / MiFID II investment-recommendation disclosure, UK FCA financial promotions (fair, clear, not misleading; risk warnings), and US SEC/FINRA (publisher's exemption; hypothetical- and past-performance presentation). Paper and demo results always labelled as such. No cherry-picked performance. Educational only: a doubtful case is a `needs counsel` finding, never a ruling | account fit, tax drag (`financial-advisor`) |
| `ux-designer` | sonnet | Admin SPA and Discord embeds: visual hierarchy, density, the action an alert asks for, mobile/PWA, accessibility, light and dark themes. Judges `ui-verifier` screenshots when they're supplied | embed code correctness (`alert-surface`, `senior-engineer`) |
| `sre` | sonnet | Hetzner VM: soak criteria and razor-edge clauses, data-provider failover (yfinance ↔ Alpaca), cron and scheduling, logs and alerting, backup and PITR, capacity | cross-package design (`staff-engineer`); cache and backtest numerics (`quant-engineer`) |

**Red flags that make a finding `BLOCKING`, at least:**
- `execution-specialist`: any path to a real-account order that skips `assert_demo`; order submit without an idempotency key or a journal entry; a market order resting overnight.
- `compliance-reviewer`: published performance not labelled paper/demo; hypothetical results shown without the method; a published recommendation with no risk warning or disclosure of the author's interest.
- `ux-designer`: an alert whose entry, stop or size can't be read on mobile; a theme that breaks contrast.
- `sre`: a pass/fail clause one event can flip, with no flag; work scheduled on the dev laptop; a live change not mirrored.

**Panel defaults.** Add to the `document-conventions.md` panel table. The existing 1–3 roles cap stays.

| Spec is about… | Default panel |
|---|---|
| eToro integration, anything that places an order | execution-specialist, risk-manager, staff-engineer (**`execution-specialist` is mandatory**) |
| Published content (bomeo-capital.com, public channels) | compliance-reviewer, financial-advisor |
| Admin UI | ux-designer, staff-engineer, financial-advisor (replaces the current row) |
| Production ops, soaks, providers | sre, staff-engineer |

`test_spec_panel_header.py` gains a check: a spec whose body mentions `etoro` (case-insensitive), numbered above v159, must list `execution-specialist`.

### B. eToro demo-only guard and reconciler

**B1. Session hook.** Add `_rule_etoro_real_account` to `.claude/hooks/guardrails.py`, in the pattern of the existing `_rule_*` functions. It denies:
- an eToro MCP tool call whose input carries `account: real`, `"real"` as the account or environment value, or a real-trading route;
- a Bash or PowerShell command that sends a request to an eToro trading endpoint without a demo marker in the URL or path;
- an Edit or Write that sets `ETORO_ALLOW_REAL` or `ETORO_REAL_SIGNOFF` in any `.env*` file. Only the human partner changes these by hand.

Widen the matcher in `.claude/settings.json` to `Glob|Read|Edit|Write|NotebookEdit|Bash|PowerShell|mcp__.*` and mirror it into `.codex/hooks.json`. Every other rule reads only the tool inputs it understands, so widening the matcher changes nothing else. Each existing rule gets a regression test proving it ignores PowerShell and MCP inputs it doesn't parse. The plan's first B task confirms the eToro MCP tool-name prefix from the installed server and pins it in a test. If the server isn't installed, the rule matches the name fragment `etoro`.

Error policy: a call the rule can't parse is allowed, as with the existing rules. An explicit real-account marker is always denied. A deny prints the reason and points at `etoro-roadmap.md`.

**B2. Code guard.** New module `swingbot/core/infra/etoro_guard.py` (`infra` owns config-adjacent cross-cutting guards; confirm against `architecture.md` while writing the plan):

```python
class RealAccountBlocked(RuntimeError): ...

def assert_demo(account: str) -> None:
    """Raise RealAccountBlocked unless account == "demo", or real trading is
    explicitly unlocked (ETORO_ALLOW_REAL=true AND ETORO_REAL_SIGNOFF set to
    an ISO date no later than today)."""
```

- New `Field`s in `swingbot/config.py`, section "eToro Paper Trading": `ETORO_ALLOW_REAL` (bool, default false) and `ETORO_REAL_SIGNOFF` (ISO date string, default empty). Help text: stage 2 only, set by the partner by hand, see `etoro-roadmap.md`.
- The sign-off token is there so stage 2 can never be unlocked by flipping one boolean.
- `tests/test_etoro_guard.py`:
  - unit tests for the demo, real-locked, flag-without-signoff, signoff-without-flag, future-dated-signoff and unlocked cases;
  - an AST scan of `swingbot/`, `bot.py`, `admin_ui.py` and `scripts/` that fails when a module references an eToro host, imports an eToro client, or reads `ETORO_USER_KEY`/`ETORO_API_KEY` without also calling `assert_demo`. Exempt: `etoro_guard.py` itself and `config.py`'s field declarations. The scan passes trivially today and guards the first eToro client to land.

**B3. `order-safety` skill.** `.claude/skills/order-safety/SKILL.md`. Claude can invoke it itself. It fires before any eToro operation, from MCP, script or code. Checklist:
1. Demo account only, and say so.
2. A read call first: portfolio, then instrument lookup by symbol.
3. Check the order params against the trade plan they came from: entry, stop, target, and size within the 2% dollar risk (`user-trades-real-money-from-alerts` memory: the rule is dollar risk).
4. Send with an idempotency key.
5. Write a journal entry for every order sent or rejected.
6. Never retry a write blind; read the state first.

It loads `etoro-public-api-operations` for the API itself. It's out of scope for anything that isn't an eToro operation.

**B4. `reconciler` agent.** `.claude/agents/reconciler.md`: sonnet, read-only (Bash through `ssh-hetzner.sh`, Read, Grep). Inputs: the VM journal and the eToro demo portfolio, read through the MCP server or a read-only route. Output: mismatches only. Missing or orphan positions, size or stop mismatch, fill-price drift against the paper fill in R. Returns `CLEAN` when they agree. Dormant until stage 1 places orders. This plan fixes its contract and adds a row in `skills-tools.md` § Which agent for what.

### C. Ops and UI rituals

**C1. `/soak`.** Slash-only (`disable-model-invocation: true`), in the v155 pattern.
1. **Pre-register before the window opens.** Clauses, thresholds, measurement definitions and the window dates go into a plan or results doc, committed before the first sample.
2. **Razor-edge check.** For each ratio clause, work out how many events would flip it at the expected N. If it's fewer than 5, flag it in the pre-registration. v106 clause (c) flipped on 2 events in 180 scans.
3. **Sampler on the VM.** A cron mirrored under `scripts/ops/`. The untracked `v106_load_sampler.sh`/`install_v106_load_sampler_cron.sh` are the template; generalising them is a plan task. The v106 session owns committing the originals.
4. **Verdict.** A pooled table plus a per-day table in `docs/superpowers/results/`.
5. **On FAIL.** Diagnose from telemetry only. A retry is a new pre-registration with a new attempt number, never an edit of the old one.

Hook: `_rule_soak_prereg_locked` denies an Edit/Write to the thresholds block of a soak pre-registration whose window start date is in the past. The block is delimited by `<!-- soak-prereg -->` markers.

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

Every addition ships its mirror in the same commit: skills and agents through `python scripts/dev/sync_codex.py`; the `CLAUDE.md` and `docs/claude/` changes condensed into `AGENTS.md`; the hook matcher and the two new rules into `.codex/hooks.json`. `tests/hooks/test_codex_mirror.py` must stay green. `CLAUDE.md` changes are kept small, to respect the 200-line cap:
- the eToro section gains one line: "`assert_demo` guards every eToro call; `order-safety` fires first";
- the reference table gets no new rows (the content lives in `skills-tools.md`, `etoro-roadmap.md` and `document-conventions.md`).

## Testing

- `tests/hooks/test_role_skills.py`: 13 roles, models pinned per the table above, each with all four sections.
- Skill eval suites (v96 pattern): one positive and one negative prompt per new model-invocable skill (`execution-specialist`, `compliance-reviewer`, `ux-designer`, `sre`, `order-safety`, `frontend`, `chart-render`). The slash-only `/soak` and `/incident` need a test that they're never model-triggered.
- `tests/hooks/test_guardrails.py`: allow and deny cases for `_rule_etoro_real_account` (MCP, Bash, PowerShell, `.env` edit) and `_rule_soak_prereg_locked`, plus the non-interference regressions for the widened matcher.
- `tests/test_etoro_guard.py`: as in B2.
- `tests/hooks/test_spec_panel_header.py`: the mandatory `execution-specialist` check.
- Complexity: every new or changed function stays under 15 (`radon cc -s -n C`).
- One full-suite run, as the plan's final task.

## Rollout

Plan order: A (roles, panel table), then B1 → B2 → B3 → B4, then C1–C5. C has no dependency on B, so C can run in parallel with B once A is done.

The pre-close-out `/panel` on this plan's diff runs `execution-specialist, compliance-reviewer, staff-engineer`. The new seats review the guard and the publication wording they were created for. `/close-out` applies `Bump: bot patch`.

## Risks

- **Widening the hook matcher slows or breaks other rules.** Mitigation: the non-interference regressions, plus the existing allow-on-parse-failure policy.
- **The compliance seat is read as legal advice.** Mitigation: the lens says "educational only" and the `needs counsel` finding type; it never rules.
- **The AST scan for eToro references is evaded by dynamic URLs.** Accepted. The hook, the `order-safety` skill and the `execution-specialist` seat are the other layers. The scan catches the ordinary case: someone writes a client and forgets the guard.
