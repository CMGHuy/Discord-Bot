# v145 Expert role skills, review panels and per-task model routing: Implementation Plan, part 1 — role skills

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Header, global constraints, file map and parallelisation: `2026-10-09-v145-expert-roles-model-routing_0-index.md`.

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`](../specs/2026-10-09-v145-expert-roles-model-routing.md)

# Phase 1 — Role skills

Three tasks, three roles each. Every role skill is model-invocable (registered in `TIER_1_AND_3`), so it carries a `## Trigger table` whose rows are mirrored one-for-one by trigger cases under `.claude/skills/<role>/evals/` in the v96 format (`docs/claude/skills-tools.md` § Proving a skill fires). The should-not-fire rows are deliberately a *neighbouring* role's lens, so the cases prove the lenses do not overlap.

### Task V145-1: Role-skill shape test, roles table, and the quant-researcher, risk-manager and financial-advisor skills

**Model:** sonnet — creates a new test module plus three shape-tested skills; the content is given verbatim but the first task sets the pattern the next two copy.

**Files:**
- Create: `tests/hooks/test_role_skills.py`
- Create: `.claude/skills/quant-researcher/SKILL.md` and six trigger cases under `.claude/skills/quant-researcher/evals/`
- Create: `.claude/skills/risk-manager/SKILL.md` and six trigger cases under `.claude/skills/risk-manager/evals/`
- Create: `.claude/skills/financial-advisor/SKILL.md` and six trigger cases under `.claude/skills/financial-advisor/evals/`
- Modify: `tests/hooks/test_skill_shape.py` (the `TIER_1_AND_3` set, line 22)
- Modify: `docs/claude/skills-tools.md` (new `## Expert roles (v145)` section directly above `## Which agent for what (v107)`)
- Modify: `AGENTS.md` (new paragraph after the line `your equivalent.` in `## Skills: the same ones Claude uses`)
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`, the `docs/claude/` row near line 259)
- Modify: `tests/dev/test_select_tests.py` (`_with_readers` and the `docs/claude/backtest-methodology.md` case of `test_data_read_path_routes_to_its_readers`)
- Generated: `.agents/skills/{quant-researcher,risk-manager,financial-advisor}/SKILL.md` (by `python scripts/dev/sync_codex.py`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `tests/hooks/test_role_skills.py` with module constants `ROLES: dict[str, str]` (role → reviewer model; V145-2 and V145-3 add rows), `SKILLS_DIR`, `SKILLS_TOOLS`, and helpers `_text(path) -> str`, `_body(name) -> str` (SKILL.md body after the frontmatter), `_section(body, heading) -> str`, `lens_skills(skills_dir=SKILLS_DIR) -> set[str]` (every skill whose SKILL.md has a `## Lens` heading). V145-5 and V145-8 add tests that call `_body` and `_text`. The `## Expert roles (v145)` table in `docs/claude/skills-tools.md`, rows of the exact form ``| `<role>` | <model> | <lens> |``, which `/panel` (V145-5) reads.

**Cited paths, verified at writing:** `docs/superpowers/results/preregistration-ledger.jsonl`, `swingbot/core/backtesting/instrument/stats.py` (`ledger_qvalues`, `week_cluster_bootstrap`), `swingbot/core/backtesting/validation_registry.json`, `swingbot/config.py` (`MAX_STOP_LOSS_PCT`, `PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`), `swingbot/core/edge/{heat,correlation,sizing,stops,ruin,throttle,frictions,growth}.py`, `swingbot/core/planning/{stop_scope,account}.py`, `swingbot/core/risk_limits.py`, `swingbot/core/analytics/risk_metrics.py`, `swingbot/admin/api_v1/risk.py`, `swingbot/core/scanning/dedup.py`, `swingbot/commands/growth.py`; `known-traps.md` §§ "Stop floor and 2% cap: the empty band, and the v115 clamp", "The level-lifecycle stop breaches the 2% cap in the backtest", "Live plans are almost never VALIDATED, and the WEAK ledger is empty — both by design (2026-10-09)".

- [ ] **Step 0: Create the worktree**

Load the `worktree-lifecycle` skill, then create branch and worktree `2026-10-09-v145-expert-roles-model-routing` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v145-expert-roles-model-routing` from `main`, and root the session there with `EnterWorktree`. Confirm: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v145-expert-roles-model-routing status --short` prints nothing.

- [ ] **Step 1: Write the failing test and register the three roles**

Create `tests/hooks/test_role_skills.py` with exactly:

```python
"""v145 § 1: the expert role skills -- one shape for nine lenses.

Each role skill carries Lens, Checklist, Red flags and Out of scope in that
order, states the hard boundaries every seat shares, and ships trigger cases
in the v96 format. Its reviewer model is recorded once, in the roles table of
docs/claude/skills-tools.md, which /panel reads. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".claude" / "skills"
SKILLS_TOOLS = ROOT / "docs/claude/skills-tools.md"

# role -> reviewer model (spec § 1). Each role-skill task adds its own rows.
ROLES = {
    "quant-researcher": "opus",
    "risk-manager": "sonnet",
    "financial-advisor": "sonnet",
}

SECTIONS = ("## Lens", "## Checklist", "## Red flags", "## Out of scope")
BOUNDARIES = ("never decide", "never lower a gate", "`pooled-numbers`",
              "`backtest-gate`", "BLOCKING", "ADVISORY")
MIN_CHECKS, MAX_CHECKS = 8, 15
REVIEWER_MODELS = {"sonnet", "opus"}   # no reviewer runs on haiku
CASE_FILES = ("prompt.md", "graders/skill-fired.md")


def _text(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(name):
    return _text(SKILLS_DIR / name / "SKILL.md").split("---", 2)[2]


def _section(body, heading):
    start = body.index(heading + "\n") + len(heading)
    end = body.find("\n## ", start)
    return body[start:] if end == -1 else body[start:end]


def lens_skills(skills_dir=SKILLS_DIR):
    """Every skill that declares a Lens is a role skill."""
    return {p.parent.name for p in pathlib.Path(skills_dir).glob("*/SKILL.md")
            if "\n## Lens\n" in _text(p)}


def _cases(role):
    root = SKILLS_DIR / role / "evals"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def _case_problems(role, case):
    missing = [rel for rel in CASE_FILES if not (case / rel).is_file()]
    if missing:
        return [f"{case.name}: missing {missing}"]
    grader = _text(case / "graders/skill-fired.md")
    expected = [f"input_match: {role}\n"]
    expected += ["min: 0", "max: 0"] if case.name.startswith("no-fire-") else ["min: 1"]
    return [f"{case.name}: grader lacks {line!r}" for line in expected if line not in grader]


def test_every_lens_skill_is_a_registered_role():
    assert lens_skills() == set(ROLES)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_has_the_four_sections_in_order(role):
    body = _body(role)
    positions = [body.find(heading + "\n") for heading in SECTIONS]
    assert -1 not in positions, dict(zip(SECTIONS, positions))
    assert positions == sorted(positions)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_checklist_has_eight_to_fifteen_items(role):
    items = [line for line in _section(_body(role), "## Checklist").splitlines()
             if line.startswith("- ")]
    assert MIN_CHECKS <= len(items) <= MAX_CHECKS, len(items)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_states_the_hard_boundaries(role):
    body = _body(role)
    missing = [phrase for phrase in BOUNDARIES if phrase not in body]
    assert not missing, missing


def test_financial_advisor_is_educational_not_personal_advice():
    assert "educational, not personalised financial advice" in _body("financial-advisor")


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_ships_fire_and_no_fire_cases(role):
    cases = _cases(role)
    fire = [c.name for c in cases if c.name.startswith("fire-")]
    quiet = [c.name for c in cases if c.name.startswith("no-fire-")]
    assert fire and quiet, [c.name for c in cases]
    assert len(fire) + len(quiet) == len(cases), "every case is fire-* or no-fire-*"
    assert [problem for case in cases for problem in _case_problems(role, case)] == []


@pytest.mark.parametrize("role", sorted(ROLES))
def test_reviewer_model_is_recorded_in_the_roles_table(role):
    assert ROLES[role] in REVIEWER_MODELS
    assert f"| `{role}` | {ROLES[role]} |" in _text(SKILLS_TOOLS)
```

In `tests/hooks/test_skill_shape.py`, extend the `TIER_1_AND_3` set (line 22) so it reads:

```python
TIER_1_AND_3 = {"backtest-gate", "no-lookahead", "pooled-numbers", "mirror-prod", "edge-module", "alert-surface", "schema-change", "worktree-lifecycle",
                "quant-researcher", "risk-manager", "financial-advisor"}   # each skill task appends its own name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: FAIL — `test_every_skill_is_registered_in_exactly_one_tier` (three registered names have no directory) and every `test_role_skills.py` test (`FileNotFoundError` on `.claude/skills/<role>/SKILL.md`, or `lens_skills()` returning an empty set).

- [ ] **Step 3: Write `.claude/skills/quant-researcher/SKILL.md`**

Exactly:

```markdown
---
name: quant-researcher
description: Use when judging, from the quant-researcher seat, whether a statistical claim holds up -- an ExpR or win-rate lift, a grid winner, a pre-registration, a screen verdict or a badge tier -- in a spec, plan, diff or results doc, or when the expert-reviewer agent is dispatched with role=quant-researcher. Checks sample size, overfitting, multiple comparisons and pre-registration discipline. Not for lookahead or cache bugs in code (quant-engineer) and not for whether a setup can be traded (veteran-trader).
---

# Quant researcher

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Whether the evidence supports the claim: sample size and power, overfitting to
a window or a grid, multiple comparisons across cells and ideas, and whether a
pre-registration was honoured as written. You own the statistical verdict, not
the code that produced the numbers.

## Checklist

- Every ExpR, win rate or N in the target is re-derived per `pooled-numbers`, with window, N and source in the same sentence (`docs/claude/edge-priorities.md`).
- The run went through `backtest-gate` before it ran, and is scored against the acceptance gate in `docs/claude/backtest-methodology.md`, not a looser local one.
- A new entry strategy or filter cites a `SCREEN-PASS` row in `docs/superpowers/results/preregistration-ledger.jsonl` (`backtest-methodology.md` § Stage −2), and its `**Screen:**` header matches that row.
- No knob, window or cell from `backtest-methodology.md` § Closed pre-registrations is re-run, re-gridded or re-windowed under a new name.
- Thresholds, cells and the winner rule were frozen in a results doc dated before TRAIN was read.
- VALIDATION and the holdout are spent at most once per pre-registration; a sealed-thin cell is reported as thin, never as a pass.
- Multiple comparisons are counted: cells, ideas and directions tried are stated, and `ledger_qvalues` (`swingbot/core/backtesting/instrument/stats.py`) is cited where the ledger applies.
- Uncertainty comes from `week_cluster_bootstrap` (`instrument/stats.py`), not a per-trade interval that treats same-week trades as independent.
- A grid winner sits on a plateau with its neighbours, not on an isolated peak.
- N was not shrunk and no window was narrowed to reach a gate (root `CLAUDE.md` § Prioritise expectancy and win rate).
- An ExpR gain from a tighter stop is checked for R-unit inflation: if win rate and dollar outcome do not move with it, it is called inflation.
- A badge tier read from `swingbot/core/backtesting/validation_registry.json` is checked against its `run_date` and the population it claims.
- Concentration is reported: a lift carried by one direction or two horizons says so.
- The `**Edge:**` prediction matches what was measured; a miss is amended, not hidden (`docs/claude/document-conventions.md` § The header block).

## Red flags

- A pass claimed on a closed pre-registration, a re-spent VALIDATION or holdout, or a shrunk N.
- A pooled figure quoted without re-derivation, window or N.
- A new entry strategy or filter spec with no `SCREEN-PASS` row behind its `Screen:` line.
- Thresholds or a winner rule chosen after TRAIN or VALIDATION was read.

## Out of scope

- Lookahead, cache choice and numeric bugs in the code behind the numbers: `quant-engineer`.
- Whether a passing setup can be traded at the open: `veteran-trader`.
- Stop placement and portfolio heat: `risk-manager`.
- Whether an indicator or pattern is coded as traders define it: `technical-analyst`.

## Trigger table

Should fire: asking whether a grid winner in a results doc is real or overfit.
Should fire: reviewing a spec whose `Edge: expectancy` rests on a TRAIN ExpR lift.
Should fire: reviewing a pre-registration's frozen thresholds before its TRAIN run.
Should not fire: checking whether a feature column in `market/signals.py` reads a future bar.
Should not fire: asking whether an alert's entry can be filled if the stock gaps at the open.
Should not fire: checking portfolio heat after a sizing change.
```

- [ ] **Step 4: Write `.claude/skills/risk-manager/SKILL.md`**

Exactly:

```markdown
---
name: risk-manager
description: Use when reviewing a spec, plan or diff from the risk-manager seat -- the 2% dollar-risk cap, position sizing, portfolio heat, correlated exposure and stop placement -- or when the expert-reviewer agent is dispatched with role=risk-manager. Not for whether a stop survives market noise in practice (veteran-trader) and not for account suitability or tax drag (financial-advisor).
---

# Risk manager

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Loss containment: dollar risk per trade, portfolio heat, correlated exposure
and stop placement. The partner trades real money off the alerts, so the 2%
rule is dollar risk on the account, not a percentage of price.

## Checklist

- Dollar risk is sized from the entry-to-stop distance against the account, and the stop cap (`MAX_STOP_LOSS_PCT` in `swingbot/config.py`) still binds (`docs/claude/known-traps.md` § Stop floor and 2% cap).
- A structural or level-lifecycle stop respects the cap in the backtest as well as live (`known-traps.md` § The level-lifecycle stop breaches the 2% cap in the backtest).
- Portfolio heat including the new trade stays under `PORTFOLIO_HEAT_CAP_PCT`, computed by `swingbot/core/edge/heat.py`.
- Clustered names count together against `CORRELATED_HEAT_CAP_PCT` (`swingbot/core/edge/correlation.py`).
- The sizing mode in `swingbot/core/edge/sizing.py` agrees with the suggested size the alert shows.
- Stop logic (`swingbot/core/edge/stops.py`, `swingbot/core/planning/stop_scope.py`) never widens a stop after entry.
- A change that raises per-trade risk or trade count states its drawdown and ruin effect (`swingbot/core/edge/ruin.py`, `swingbot/core/analytics/risk_metrics.py`).
- Throttles and limits (`swingbot/core/edge/throttle.py`, `swingbot/core/risk_limits.py`) apply on every path that issues an alert.
- A gap through the stop is counted in R as the loss it is, not as the planned loss.
- A rejected plan logs why (the "plan rejected (" lines), so a quiet day caused by the cap is diagnosable.
- An ExpR gain bought with wider stops is also shown in dollars at fixed risk.
- The admin risk view (`swingbot/admin/api_v1/risk.py`) shows the same heat the scanner enforces.

## Red flags

- Any alert path that bypasses the stop cap, the heat cap or the correlated cap.
- A stop that can move away from price after entry.
- Sizing that differs between the alert and the engine.

## Out of scope

- Whether a lift is statistically real: `quant-researcher`.
- Whether the stop survives market noise and gaps in practice: `veteran-trader`.
- Account suitability, allocation and tax drag: `financial-advisor`.

## Trigger table

Should fire: reviewing a change to `edge/sizing.py` or `edge/heat.py`.
Should fire: asking whether a new stop rule still respects the 2% dollar-risk cap.
Should fire: asking whether three open trades in one sector are too much correlated exposure.
Should not fire: asking whether an alert's entry can be filled at the open.
Should not fire: asking how swing turnover affects after-tax results.
Should not fire: reviewing a migration's rollback plan.
```

- [ ] **Step 5: Write `.claude/skills/financial-advisor/SKILL.md`**

Exactly:

```markdown
---
name: financial-advisor
description: Use when reviewing a spec, plan, diff or admin screen from the financial-advisor seat -- whether the bot's output suits a real-money retail swing trader: allocation, account fit, tax drag of swing turnover, alert frequency, and how performance and risk are presented -- or when the expert-reviewer agent is dispatched with role=financial-advisor. Educational review of the bot's output, never personal financial advice. Not for enforcing caps in code (risk-manager).
---

# Financial advisor

Your output is educational, not personalised financial advice. You review
whether the bot's output suits a real-money retail swing trader; you never
review the partner's personal finances, taxes or accounts.

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Suitability of the bot's output for one retail trader with real money:
allocation, account fit, tax drag of swing turnover, and whether alert
frequency and risk match what one person with a day job can follow.

## Checklist

- Alert cadence is one a person with a day job can follow; a volume change states alerts per week, not only per scan (`swingbot/core/scanning/dedup.py`, `swingbot/core/edge/throttle.py`).
- Account assumptions (`swingbot/core/planning/account.py`, the Account Defaults fields in `swingbot/config.py`) fit a retail account, including the smallest position a broker fills.
- Total capital at risk across open plans is shown against the account (`PORTFOLIO_HEAT_CAP_PCT`); enforcing it belongs to `risk-manager`.
- Turnover and short holds are named as tax drag; a claimed ExpR is pre-tax and says so.
- Frictions in `swingbot/core/edge/frictions.py` include the commissions a retail broker actually charges.
- Drawdown is shown in units a retail trader feels -- dollars and losing streaks, not only R (`swingbot/core/analytics/risk_metrics.py`).
- Expectancy leads and win rate is a constraint, in copy as well as in ranking (`docs/claude/edge-priorities.md`).
- Embeds and the admin UI show staleness and badge tier, so a WEAK or unvalidated strategy never reads as validated (`docs/claude/known-traps.md` § Live plans are almost never VALIDATED).
- Copy never promises returns or certainty, and the bot itself stays paper-trades-only.
- Growth projections (`swingbot/core/edge/growth.py`, `swingbot/commands/growth.py`) state their assumptions and are not presented as forecasts.
- Concentration in one sector or a handful of names is visible to the trader.

## Red flags

- Output that reads as a personalised recommendation, a return promise or a guarantee.
- A volume or risk change one retail trader could not follow or afford.
- A displayed performance figure that is pre-cost or pre-tax without saying so.

## Out of scope

- Enforcing caps, stops and sizing in code: `risk-manager`.
- Statistical validity of any performance shown: `quant-researcher`.
- Design and operations of the admin UI itself: `staff-engineer`.
- The partner's own finances: no role reviews them.

## Trigger table

Should fire: reviewing an alert-volume spec for whether a retail trader can keep up.
Should fire: asking whether the growth projection on the admin dashboard misleads a retail account holder.
Should fire: asking how swing turnover affects the after-tax result of following the alerts.
Should not fire: checking whether a stop in `edge/stops.py` breaches the cap.
Should not fire: checking an indicator's formula against its textbook definition.
Should not fire: checking a grid result for overfitting.
```

- [ ] **Step 6: Write the eighteen trigger cases**

Write two files per row with the Write tool (never a shell loop: see the index's note on the word that a worktree session refuses). For case directory `<case>` of role `<role>`:

`.claude/skills/<role>/evals/<case>/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

<prompt text from the table below, verbatim>
```

`.claude/skills/<role>/evals/<case>/graders/skill-fired.md` for a `fire-*` row:

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 1
---

The `<role>` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

and for a `no-fire-*` row (the explicit `min: 0` is required: `min` defaults to 1, so a bare `max: 0` asks for the impossible range `1..0`):

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 0
max: 0
---

The `<role>` skill must stay silent on this prompt: it is a should-not-fire row of that skill's trigger table.
```

Each row mirrors one line of that skill's `## Trigger table`; the should-not-fire rows are deliberately a neighbouring role's lens.

**`quant-researcher`** — six directories under `.claude/skills/quant-researcher/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-grid-winner-overfit` | `min: 1` | The v103 results doc says `b=0.1` won the grid. Is that winner real, or is it overfit to TRAIN? |
| `fire-spec-expectancy-claim` | `min: 1` | Review this draft spec before I commit it: its `Edge: expectancy` claim rests on one TRAIN grid's ExpR lift. |
| `fire-preregistration-thresholds` | `min: 1` | Here is the pre-registration for the new pullback filter. Check the frozen thresholds and the winner rule before we start the TRAIN run. |
| `no-fire-feature-lookahead` | `min: 0`, `max: 0` | Does the new `atr_ratio` column I added in `swingbot/core/market/signals.py` read a bar it should not know about yet? |
| `no-fire-gap-fill` | `min: 0`, `max: 0` | If AAPL gaps above today's alert entry at the open, does the resting buy order still fill sensibly? |
| `no-fire-portfolio-heat` | `min: 0`, `max: 0` | After the sizing change in `edge/sizing.py`, does portfolio heat still stay under the cap with five open trades? |

**`risk-manager`** — six directories under `.claude/skills/risk-manager/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-sizing-heat-change` | `min: 1` | Review this diff to `swingbot/core/edge/sizing.py` and `edge/heat.py` before I merge it. |
| `fire-stop-rule-cap` | `min: 1` | Does the new structural stop rule still respect the 2% dollar-risk cap on the account? |
| `fire-sector-correlation` | `min: 1` | I have three open trades in semiconductors. Is that too much correlated exposure? |
| `no-fire-open-fill` | `min: 0`, `max: 0` | Could the alert's entry be filled if the stock opens above it? |
| `no-fire-tax-drag` | `min: 0`, `max: 0` | How much does swing-trade turnover cut the after-tax result of following the alerts? |
| `no-fire-migration-rollback` | `min: 0`, `max: 0` | Review the rollback plan for tonight's Postgres migration on the VM. |

**`financial-advisor`** — six directories under `.claude/skills/financial-advisor/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-alert-volume-retail` | `min: 1` | Review this spec that doubles alert volume: can someone with a day job actually keep up with it? |
| `fire-growth-projection` | `min: 1` | Is the growth projection on the admin dashboard misleading for a small retail account? |
| `fire-tax-drag` | `min: 1` | How does swing turnover affect the after-tax result of following these alerts? |
| `no-fire-stop-cap-code` | `min: 0`, `max: 0` | Does the stop computed in `swingbot/core/edge/stops.py` ever breach `MAX_STOP_LOSS_PCT`? |
| `no-fire-indicator-formula` | `min: 0`, `max: 0` | Is the ATR in `market/indicators.py` using Wilder smoothing like the textbook? |
| `no-fire-grid-overfit` | `min: 0`, `max: 0` | Check the v103 grid result for overfitting. |

- [ ] **Step 7: Add the roles table to `docs/claude/skills-tools.md`**

Insert this section directly above the line `## Which agent for what (v107)`:

```markdown
## Expert roles (v145)

Nine role skills each hold one reviewer's lens, in four sections -- Lens,
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
```

- [ ] **Step 8: Mirror to Codex**

In `AGENTS.md`, insert after the line `your equivalent.` (end of the rituals paragraph in `## Skills: the same ones Claude uses`), separated by one blank line:

```markdown
Expert role skills (v145) each hold one reviewer's lens -- Lens, Checklist,
Red flags, Out of scope -- and load when you review from that seat:
`quant-researcher` (sample size, overfitting, multiple comparisons,
pre-registration discipline), `risk-manager` (2% dollar risk, portfolio heat,
correlated exposure, stops), `financial-advisor` (retail suitability, account
fit, tax drag, alert cadence; educational, not personal financial advice).
A role raises cited `BLOCKING`/`ADVISORY` findings; it never decides and never
lowers a gate.
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.`

- [ ] **Step 9: Route `docs/claude/` edits to the role test**

`test_role_skills.py` reads the roles table in `docs/claude/skills-tools.md`, so an edit there must select it under `testrun.py changed`. In `scripts/dev/select_tests.py`, change the `docs/claude/` row of `DATA_READERS` from:

```python
    # backtest-methodology.md's closed table (test_guardrails); every
    # reference doc must be named in AGENTS.md (sync_codex via test_codex_mirror).
    ("docs/claude/", ("tests/hooks/test_guardrails.py",
                      "tests/hooks/test_codex_mirror.py")),
```

to:

```python
    # backtest-methodology.md's closed table (test_guardrails); every
    # reference doc must be named in AGENTS.md (sync_codex via test_codex_mirror);
    # skills-tools.md's roles table pins each reviewer model (test_role_skills).
    ("docs/claude/", ("tests/hooks/test_guardrails.py",
                      "tests/hooks/test_codex_mirror.py",
                      "tests/hooks/test_role_skills.py")),
```

In `tests/dev/test_select_tests.py`, the fixture repo must contain the new reader (a reader missing on disk widens to a full run). Change the tuple in `_with_readers` to:

```python
    for rel in ("tests/hooks/test_guardrails.py", "tests/hooks/test_codex_mirror.py",
                "tests/hooks/test_role_skills.py",
                "tests/dev/test_testrun_ci_invocations.py"):
```

and the `docs/claude/backtest-methodology.md` case of `test_data_read_path_routes_to_its_readers` to:

```python
    ("docs/claude/backtest-methodology.md",
     ["tests/hooks/test_codex_mirror.py", "tests/hooks/test_guardrails.py",
      "tests/hooks/test_role_skills.py"]),
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/` then `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: both PASS, `0 failed`. Then `python -m radon cc -s -n C tests/hooks/test_role_skills.py` prints nothing.

- [ ] **Step 11: Commit**

```bash
git add tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py .claude/skills/quant-researcher .claude/skills/risk-manager .claude/skills/financial-advisor .agents/skills docs/claude/skills-tools.md AGENTS.md scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "feat(v145): quant-researcher, risk-manager and financial-advisor role skills with trigger cases"
```

### Task V145-2: The veteran-trader, technical-analyst and fundamental-analyst skills

**Model:** haiku — fully specified: the three skill files, eighteen cases and every edit are given verbatim, and the V145-1 test pins the result.

**Files:**
- Create: `.claude/skills/veteran-trader/SKILL.md` and six trigger cases under `.claude/skills/veteran-trader/evals/`
- Create: `.claude/skills/technical-analyst/SKILL.md` and six trigger cases under `.claude/skills/technical-analyst/evals/`
- Create: `.claude/skills/fundamental-analyst/SKILL.md` and six trigger cases under `.claude/skills/fundamental-analyst/evals/`
- Modify: `tests/hooks/test_role_skills.py` (`ROLES`), `tests/hooks/test_skill_shape.py` (`TIER_1_AND_3`)
- Modify: `docs/claude/skills-tools.md` (three rows in the `## Expert roles (v145)` table)
- Modify: `AGENTS.md` (the expert-role paragraph V145-1 added)
- Generated: `.agents/skills/{veteran-trader,technical-analyst,fundamental-analyst}/SKILL.md`

**Interfaces:**
- Consumes: `ROLES` in `tests/hooks/test_role_skills.py` and the `## Expert roles (v145)` table, both created by V145-1.
- Produces: three more `ROLES` rows and table rows; nothing new for later tasks beyond the role names.

**Cited paths, verified at writing:** `swingbot/core/scanning/{alert_embeds,execution_embeds,regime}.py`, `swingbot/core/planning/{exit_sim,time_exit}.py`, `swingbot/core/edge/{frictions,regime2,correlation}.py`, `swingbot/core/market/{session,events,opex,strategy_types,levels,levels_lifecycle,indicators,chart_patterns,candlestick_patterns,fvg,fib_leg,trendlines,structure,mtf,entry_filters,explain,earnings_calendar,earnings_context,earnings_history,market_events,market_context}.py`, `swingbot/core/charts/chart_strategy_overlay.py`, `swingbot/core/backtesting/earnings_blackout.py`, `swingbot/core/marketdata/{asset_class,pit_membership,adjustments}.py`; `known-traps.md` §§ "Futures skipped for dollar volume is deliberate (v115)", "The full state machine now runs across the whole Berlin-local active window", "Stop floor and 2% cap: the empty band, and the v115 clamp", "The dead-cat-bounce veto is invisible to `run_backtest_range.py`".

- [ ] **Step 1: Register the three roles (failing)**

In `tests/hooks/test_role_skills.py`, extend `ROLES` so it reads:

```python
ROLES = {
    "quant-researcher": "opus",
    "risk-manager": "sonnet",
    "financial-advisor": "sonnet",
    "veteran-trader": "sonnet",
    "technical-analyst": "sonnet",
    "fundamental-analyst": "sonnet",
}
```

In `tests/hooks/test_skill_shape.py`, extend `TIER_1_AND_3` so it reads:

```python
TIER_1_AND_3 = {"backtest-gate", "no-lookahead", "pooled-numbers", "mirror-prod", "edge-module", "alert-surface", "schema-change", "worktree-lifecycle",
                "quant-researcher", "risk-manager", "financial-advisor",
                "veteran-trader", "technical-analyst", "fundamental-analyst"}   # each skill task appends its own name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: FAIL — the three new names have no `SKILL.md` (tier registration and every parametrised `test_role_skills.py` case for them).

- [ ] **Step 3: Write `.claude/skills/veteran-trader/SKILL.md`**

Exactly:

```markdown
---
name: veteran-trader
description: Use when reviewing a spec, plan, diff or alert from the veteran-trader seat -- whether a setup is tradeable: fills, gaps, liquidity, regime, session timing, and whether an alert can be placed as resting orders before the open -- or when the expert-reviewer agent is dispatched with role=veteran-trader. Not for whether a lift is statistically real (quant-researcher) and not for position sizing or heat caps (risk-manager).
---

# Veteran trader

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Whether an alert is a trade a person can actually take: fills, gaps,
liquidity and regime, and whether the plan works as resting orders placed at
alert time, before the open, by someone who is not watching the screen.

## Checklist

- The partner places resting orders at alert time: entry, stop and targets can be entered as orders without re-deriving anything (`swingbot/core/scanning/alert_embeds.py`, `execution_embeds.py`).
- A gap through the entry or the stop is handled, and the simulated fill on a gap matches what an order gets (`swingbot/core/planning/exit_sim.py`).
- Slippage and commission come from `swingbot/core/edge/frictions.py`, are not zero, and apply to the same trades the claim rests on.
- Liquidity suits the size; futures skipped for dollar volume stay skipped by design (`docs/claude/known-traps.md` § Futures skipped for dollar volume is deliberate).
- Alert timing fits the session (`known-traps.md` § The full state machine now runs across the whole Berlin-local active window; `swingbot/core/market/session.py`).
- The stop survives normal noise for its horizon (`swingbot/core/market/strategy_types.py:HORIZONS`) and does not land in the empty band of `known-traps.md` § Stop floor and 2% cap.
- Regime is considered: how the setup behaves in trend versus chop (`swingbot/core/edge/regime2.py`, `swingbot/core/scanning/regime.py`).
- Earnings, OPEX and macro dates inside the holding window are named (`swingbot/core/market/events.py`, `opex.py`); depth goes to `fundamental-analyst`.
- Expiry and time exits are stated, so no resting order works past the plan's validity (`swingbot/core/planning/time_exit.py`).
- A silent stop move, a missing expiry or a lost send on the alert channel is real-money divergence and is `Edge: harvest` (`docs/claude/edge-priorities.md`).
- Alert volume is one a person can act on before the open.
- A gap between the backtest and live paths is named, not assumed away (`known-traps.md` § The dead-cat-bounce veto is invisible to `run_backtest_range.py`).

## Red flags

- An alert whose entry, stop or target cannot be placed as an order as written.
- A fill model that assumes fills a gap or a thin book would not give.
- A stop or expiry that can change after the alert with no follow-up message.
- Zero frictions behind a claimed lift.

## Out of scope

- Whether the lift is statistically real: `quant-researcher`.
- Position size, portfolio heat and correlated exposure: `risk-manager`.
- Earnings and catalyst depth: `fundamental-analyst`.
- Indicator and pattern correctness in code: `technical-analyst`.

## Trigger table

Should fire: asking whether an alert's entry could be filled if the stock gaps at the open.
Should fire: reviewing an alert embed change for whether the plan can be placed as resting orders.
Should fire: asking whether a new setup is tradeable in thinly traded names.
Should not fire: checking the bootstrap interval on a grid result.
Should not fire: checking a new helper function's cyclomatic complexity.
Should not fire: reviewing an Alembic migration's downgrade path.
```

- [ ] **Step 4: Write `.claude/skills/technical-analyst/SKILL.md`**

Exactly:

```markdown
---
name: technical-analyst
description: Use when reviewing a spec, plan or diff from the technical-analyst seat -- support/resistance, chart and candlestick patterns, FVG, Fibonacci, trendlines and indicator logic: is the code computing what the setup is named for, the way traders trade it -- or when the expert-reviewer agent is dispatched with role=technical-analyst. Not for whether the pattern pays (quant-researcher) and not for cache or replay plumbing (quant-engineer).
---

# Technical analyst

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

S/R, pattern and indicator logic: does the code compute what the setup is
named for, and is that setup the one traders actually trade?

## Checklist

- Level detection and clustering (`swingbot/core/market/levels.py`, `levels_lifecycle.py`) define support and resistance as the alert describes them; touch, break and retest are distinct states.
- Indicators in `swingbot/core/market/indicators.py` use the standard definition (Wilder smoothing for RSI and ATR unless the strategy says otherwise) and the lookback the strategy names.
- Patterns (`chart_patterns.py`, `candlestick_patterns.py`, `fvg.py`, `fib_leg.py`, `trendlines.py`, `structure.py` under `swingbot/core/market/`) confirm on closed bars only, and the `no-lookahead` truncation test exists.
- Multi-timeframe logic (`swingbot/core/market/mtf.py`) aligns higher-timeframe bars by their close time, not their open.
- Entry gates in `swingbot/core/market/entry_filters.py` match the setup's narrative: a pullback entry does not fire on a breakout bar.
- A setup runs only on horizons in `swingbot/core/market/strategy_types.py:HORIZONS` that it was measured on.
- Confluence counts independent evidence: two signals derived from the same moving average are one confirmation, not two.
- The chart overlay (`swingbot/core/charts/chart_strategy_overlay.py`) draws the same levels the plan uses.
- Closed ideas in `docs/claude/backtest-methodology.md` § Closed pre-registrations (FVG modes, Fibonacci stops, S/R touch gates) do not return as a new pattern under a new name.
- The strategy explanation (`swingbot/core/market/explain.py`) describes the rule that fired, not a generic setup.
- A new indicator or pattern goes through the `edge-module` skill for its registry entry and wiring.

## Red flags

- A pattern or indicator that reads an unclosed or future bar.
- Code that computes a different indicator from the one its name and the alert claim.
- A closed idea reintroduced without a new mechanism.

## Out of scope

- Statistical evidence that the pattern pays: `quant-researcher`.
- Cache choice and backtest or replay plumbing: `quant-engineer`.
- Whether the resulting alert can be filled: `veteran-trader`.

## Trigger table

Should fire: reviewing a change to support/resistance clustering in `market/levels.py`.
Should fire: asking whether the FVG detector in `market/fvg.py` matches how traders define a fair value gap.
Should fire: checking that a new RSI divergence rule uses the standard RSI.
Should not fire: checking whether earnings fall inside a plan's holding window.
Should not fire: reviewing portfolio heat after a sizing change.
Should not fire: reviewing an Alembic migration's downgrade path.
```

- [ ] **Step 5: Write `.claude/skills/fundamental-analyst/SKILL.md`**

Exactly:

```markdown
---
name: fundamental-analyst
description: Use when reviewing a spec, plan or diff from the fundamental-analyst seat -- earnings dates, catalysts, macro events, sector and macro concentration, point-in-time fundamentals and universe membership, the price-only bot's blind spot -- or when the expert-reviewer agent is dispatched with role=fundamental-analyst. Not for pattern or indicator logic (technical-analyst) and not for heat caps in code (risk-manager).
---

# Fundamental analyst

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

What price data cannot see: earnings, catalysts, macro events, and sector and
macro concentration. The bot is technical; this seat names where that blind
spot costs money.

## Checklist

- Earnings inside the holding window are detected (`get_next_earnings_date`, `earnings_within_window` in `swingbot/core/market/events.py`) and the plan says what it does about them.
- The earnings source (`swingbot/core/market/earnings_calendar.py`) and its staleness are known; a missing date is never read as "no earnings".
- A backtest that claims an earnings filter applies the same rule live (`swingbot/core/backtesting/earnings_blackout.py` against the live path).
- Earnings context and history (`swingbot/core/market/earnings_context.py`, `earnings_history.py`) are point-in-time: no estimate or result dated after the bar.
- Macro events and OPEX inside the holding window are named (`swingbot/core/market/market_events.py`, `opex.py`).
- Sector concentration uses `swingbot/core/edge/correlation.py` and its sector fallback; a watchlist or alert batch heavy in one sector says so.
- ETFs, futures and metals (`swingbot/core/marketdata/asset_class.py`) never get single-stock earnings logic.
- Market context (`swingbot/core/market/market_context.py`) reflects index and sector regime, not only the ticker.
- A news-driven gap is treated as a catalyst event, not a technical breakout.
- Any historical claim uses point-in-time universe membership (`swingbot/core/marketdata/pit_membership.py`).
- Splits and dividends are adjusted before levels are computed (`swingbot/core/marketdata/adjustments.py`).

## Red flags

- An alert issued with earnings inside its holding window and no mention of them.
- Survivorship: a historical claim made on today's membership.
- A fundamental value dated after the bar it is used on.

## Out of scope

- Statistical validity of an earnings filter's lift: `quant-researcher`.
- Correlated heat caps in code: `risk-manager`.
- Pattern and indicator logic: `technical-analyst`.

## Trigger table

Should fire: reviewing a spec that adds an earnings blackout filter.
Should fire: asking whether today's alerts are over-concentrated in semiconductors.
Should fire: asking whether a backtest's earnings dates are point-in-time.
Should not fire: checking an RSI formula against its textbook definition.
Should not fire: asking whether a stop survives intraday noise.
Should not fire: checking a new helper function's cyclomatic complexity.
```

- [ ] **Step 6: Write the eighteen trigger cases**

Write two files per row with the Write tool (never a shell loop: see the index's note on the word that a worktree session refuses). For case directory `<case>` of role `<role>`:

`.claude/skills/<role>/evals/<case>/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

<prompt text from the table below, verbatim>
```

`.claude/skills/<role>/evals/<case>/graders/skill-fired.md` for a `fire-*` row:

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 1
---

The `<role>` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

and for a `no-fire-*` row (the explicit `min: 0` is required: `min` defaults to 1, so a bare `max: 0` asks for the impossible range `1..0`):

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 0
max: 0
---

The `<role>` skill must stay silent on this prompt: it is a should-not-fire row of that skill's trigger table.
```

Each row mirrors one line of that skill's `## Trigger table`; the should-not-fire rows are deliberately a neighbouring role's lens.

**`veteran-trader`** — six directories under `.claude/skills/veteran-trader/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-gap-at-open` | `min: 1` | If the stock gaps above the alert's entry at the open, could I actually get filled on this alert? |
| `fire-resting-orders` | `min: 1` | Review this change to `alert_embeds.py`: can I still place the entry, the stop and both targets as resting orders straight from the alert? |
| `fire-thin-names` | `min: 1` | Is the new inside-bar setup tradeable in thinly traded small caps, or will the spread eat it? |
| `no-fire-bootstrap-interval` | `min: 0`, `max: 0` | Is the week-cluster bootstrap interval on this grid result computed correctly? |
| `no-fire-helper-complexity` | `min: 0`, `max: 0` | Check the cyclomatic complexity of the new helper in `scanning/qualify.py`. |
| `no-fire-migration-downgrade` | `min: 0`, `max: 0` | Review the downgrade path of the new Alembic revision for the trades table. |

**`technical-analyst`** — six directories under `.claude/skills/technical-analyst/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-sr-clustering` | `min: 1` | Review this change to how `market/levels.py` clusters support and resistance levels. |
| `fire-fvg-definition` | `min: 1` | Does the FVG detector in `market/fvg.py` match how traders actually define a fair value gap? |
| `fire-rsi-divergence` | `min: 1` | I added an RSI divergence rule. Check that it uses the standard RSI and the right lookback. |
| `no-fire-earnings-window` | `min: 0`, `max: 0` | Does any of today's alerts have earnings inside its holding window? |
| `no-fire-heat-after-sizing` | `min: 0`, `max: 0` | Does portfolio heat still stay under the cap after the sizing change? |
| `no-fire-migration-downgrade` | `min: 0`, `max: 0` | Review the downgrade path of the new Alembic revision. |

**`fundamental-analyst`** — six directories under `.claude/skills/fundamental-analyst/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-earnings-blackout-spec` | `min: 1` | Review this spec that adds an earnings blackout filter to the scanner. |
| `fire-sector-concentration` | `min: 1` | Are today's alerts over-concentrated in semiconductors? |
| `fire-pit-earnings-dates` | `min: 1` | Are the earnings dates the backtest uses point-in-time, or today's calendar back-filled? |
| `no-fire-rsi-formula` | `min: 0`, `max: 0` | Is the RSI in `market/indicators.py` the textbook Wilder RSI? |
| `no-fire-stop-noise` | `min: 0`, `max: 0` | Will a stop one ATR below the level survive normal intraday noise on a daily swing? |
| `no-fire-helper-complexity` | `min: 0`, `max: 0` | Check the cyclomatic complexity of the new helper in `scanning/qualify.py`. |

- [ ] **Step 7: Add the three table rows to `docs/claude/skills-tools.md`**

Append directly below the `financial-advisor` row of the `## Expert roles (v145)` table:

```markdown
| `veteran-trader` | sonnet | Tradeability: fills, gaps, liquidity, regime, whether an alert is actionable before the open |
| `technical-analyst` | sonnet | S/R, pattern and indicator logic: correct in code and true to how the setup is traded |
| `fundamental-analyst` | sonnet | Earnings, catalysts, sector and macro concentration: the bot's blind spot |
```

- [ ] **Step 8: Mirror to Codex**

In `AGENTS.md`, replace the expert-role paragraph (the one starting `Expert role skills (v145)`) with:

```markdown
Expert role skills (v145) each hold one reviewer's lens -- Lens, Checklist,
Red flags, Out of scope -- and load when you review from that seat:
`quant-researcher` (sample size, overfitting, multiple comparisons,
pre-registration discipline), `risk-manager` (2% dollar risk, portfolio heat,
correlated exposure, stops), `financial-advisor` (retail suitability, account
fit, tax drag, alert cadence; educational, not personal financial advice),
`veteran-trader` (fills, gaps, liquidity, regime, resting orders before the
open), `technical-analyst` (S/R, pattern and indicator logic),
`fundamental-analyst` (earnings, catalysts, sector and macro concentration).
A role raises cited `BLOCKING`/`ADVISORY` findings; it never decides and never
lowers a gate.
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.`

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: PASS, `0 failed`.

- [ ] **Step 10: Commit**

```bash
git add tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py .claude/skills/veteran-trader .claude/skills/technical-analyst .claude/skills/fundamental-analyst .agents/skills docs/claude/skills-tools.md AGENTS.md
git commit -m "feat(v145): veteran-trader, technical-analyst and fundamental-analyst role skills with trigger cases"
```

### Task V145-3: The staff-engineer, quant-engineer and senior-engineer skills

**Model:** haiku — fully specified: the three skill files, eighteen cases and every edit are given verbatim, and the V145-1 test pins the result.

**Files:**
- Create: `.claude/skills/staff-engineer/SKILL.md` and six trigger cases under `.claude/skills/staff-engineer/evals/`
- Create: `.claude/skills/quant-engineer/SKILL.md` and six trigger cases under `.claude/skills/quant-engineer/evals/`
- Create: `.claude/skills/senior-engineer/SKILL.md` and six trigger cases under `.claude/skills/senior-engineer/evals/`
- Modify: `tests/hooks/test_role_skills.py` (`ROLES`), `tests/hooks/test_skill_shape.py` (`TIER_1_AND_3`)
- Modify: `docs/claude/skills-tools.md` (three rows in the `## Expert roles (v145)` table)
- Modify: `AGENTS.md` (the expert-role paragraph)
- Generated: `.agents/skills/{staff-engineer,quant-engineer,senior-engineer}/SKILL.md`

**Interfaces:**
- Consumes: `ROLES` and the roles table (V145-1), extended by V145-2.
- Produces: the complete nine-role roster. `senior-engineer` is the skill `task-reviewer` preloads in V145-4; `expert-reviewer` (V145-4) lists all nine names.

**Cited paths, verified at writing:** `swingbot/core/db/write_failure.py` (`StoreWriteHalt`), `swingbot/config.py`, `scripts/ops/rollback_to.sh` (documented in `AGENTS.md` and `docs/deploy/DEPLOY_HETZNER.md`), `scripts/dev/select_tests.py` (`DATA_READERS`), `swingbot/core/marketdata/{backtest_cache,data_store,adjustments}.py`, `swingbot/core/scanning/{scan_replay,engine,embeds}.py`, `swingbot/commands/scanning.py`, `swingbot/core/edge/frictions.py`, `swingbot/core/backtesting/instrument/stats.py` (`WEEK_BOOTSTRAP_SEED`); `schema-evolution.md` § "Before running a data revision on production"; `working-conventions.md` §§ "Mirroring production changes back", "Codex mirror", "Scheduling far-off work", "The three levels", "Long-running scripts must report progress"; `code-complexity.md` § "A refactor must not change behaviour"; `known-traps.md` §§ "The market_data cache never self-heals (v116 follow-up)", "Scan parameter and replay gate parity (v74)"; `.claude/skills/task-brief/SKILL.md` steps 3b and 3d.

- [ ] **Step 1: Register the three roles (failing)**

In `tests/hooks/test_role_skills.py`, extend `ROLES` so it reads:

```python
ROLES = {
    "quant-researcher": "opus",
    "risk-manager": "sonnet",
    "financial-advisor": "sonnet",
    "veteran-trader": "sonnet",
    "technical-analyst": "sonnet",
    "fundamental-analyst": "sonnet",
    "staff-engineer": "opus",
    "quant-engineer": "sonnet",
    "senior-engineer": "sonnet",
}
```

In `tests/hooks/test_skill_shape.py`, extend `TIER_1_AND_3` so it reads:

```python
TIER_1_AND_3 = {"backtest-gate", "no-lookahead", "pooled-numbers", "mirror-prod", "edge-module", "alert-surface", "schema-change", "worktree-lifecycle",
                "quant-researcher", "risk-manager", "financial-advisor",
                "veteran-trader", "technical-analyst", "fundamental-analyst",
                "staff-engineer", "quant-engineer", "senior-engineer"}   # each skill task appends its own name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: FAIL — the three new names have no `SKILL.md`.

- [ ] **Step 3: Write `.claude/skills/staff-engineer/SKILL.md`**

Exactly:

```markdown
---
name: staff-engineer
description: Use when reviewing a spec, plan or diff from the staff-engineer seat -- cross-cutting design: seams between swingbot/core packages, schema migrations, production VM operations, blast radius and long-run maintenance cost -- or when the expert-reviewer agent is dispatched with role=staff-engineer. Not for line-level quality inside one module (senior-engineer) and not for backtest plumbing (quant-engineer).
---

# Staff engineer

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

The shape of the change across the system: which seams it crosses, what it
migrates, what it does to the production VM, how far a failure spreads, and
what it costs to keep for a year.

## Checklist

- The change respects the package seams and scan-pipeline order in `docs/claude/architecture.md`; a new import between `swingbot/core` packages is justified, not incidental.
- A table or stored-record shape change follows `docs/claude/schema-evolution.md` (add, rename, drop, promote; no read-time upcasting) and the `schema-change` skill, as an Alembic revision.
- A data revision has a production run plan per `schema-evolution.md` § Before running a data revision on production.
- A production change is mirrored back per the `mirror-prod` skill and `docs/claude/working-conventions.md` § Mirroring production changes back.
- A new `.env` field is declared in `swingbot/config.py`'s schema and survives the SIGHUP hot reload; nothing reads `os.environ` directly.
- A store write that can fail at alert issuance halts scanning rather than half-writing (`StoreWriteHalt` in `swingbot/core/db/write_failure.py`).
- Both containers (`bot.py`, `admin_ui.py`) still start off the one image, and `docs/deploy/DEPLOY_HETZNER.md` needs no undocumented step.
- Blast radius is named: what breaks, who sees it (alert channel, admin UI, backtests) and how it rolls back (`scripts/ops/rollback_to.sh`, `DEPLOY_HETZNER.md`).
- A Claude setup change ships its Codex mirror in the same commit (`working-conventions.md` § Codex mirror).
- Far-off scheduled work runs as a cron on the VM, never on the laptop (`working-conventions.md` § Scheduling far-off work).
- A new data file that tests read has a `DATA_READERS` row in `scripts/dev/select_tests.py`.
- The `Bump:` level matches the observable difference (`working-conventions.md` § The three levels).
- Long-run cost is stated: a new cache, cron, table or flag names its owner and when it can be removed.

## Red flags

- A production change with no repo mirror, or a schema change outside an Alembic revision.
- A write path that can fail silently or half-write a trading store.
- A change crossing `swingbot/core` packages where one package's failure can stop the scan loop.
- A rollback that needs a step nobody wrote down.

## Out of scope

- Function-level quality, complexity and tests inside one module: `senior-engineer`.
- Lookahead, the OHLCV caches and backtest reproducibility: `quant-engineer`.
- Whether admin UI figures mislead a retail reader: `financial-advisor`.

## Trigger table

Should fire: reviewing a spec that adds a Postgres table and a new cron on the VM.
Should fire: asking whether moving code between `swingbot/core/scanning` and `swingbot/core/planning` is safe to ship.
Should fire: reviewing the rollback story of a deploy plan.
Should not fire: checking one function's cyclomatic complexity in a task diff.
Should not fire: checking whether a backtest script reads the right OHLCV cache.
Should not fire: judging whether a strategy's ExpR lift is overfit.
```

- [ ] **Step 4: Write `.claude/skills/quant-engineer/SKILL.md`**

Exactly:

```markdown
---
name: quant-engineer
description: Use when reviewing a spec, plan or diff from the quant-engineer seat -- the plumbing under every backtest and replay number: lookahead, numerics, the two OHLCV caches, live/backtest parity and reproducibility -- or when the expert-reviewer agent is dispatched with role=quant-engineer. Loads no-lookahead for feature code. Not for whether a result is statistically meaningful (quant-researcher) and not for general code quality (senior-engineer).
---

# Quant engineer

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

The plumbing under every number: lookahead, numerics, the two OHLCV caches,
live/backtest parity and whether a result can be reproduced from what was
recorded.

## Checklist

- Load the `no-lookahead` skill for any feature, entry-signal or indicator change; its truncation test exists and passes.
- The right cache is read: `swingbot/core/marketdata/backtest_cache.py` (`data/backtest_cache/`, daily, what backtests read) or `swingbot/core/marketdata/data_store.py` (`market_data/<timeframe>/`), through `cache_path()`/`load_from_disk()` (`docs/claude/known-traps.md`).
- A stale or truncated `market_data` file is detected, never silently used (`known-traps.md` § The market_data cache never self-heals).
- Scan parameters and the replay gate agree (`known-traps.md` § Scan parameter and replay gate parity (v74); `swingbot/core/scanning/scan_replay.py`).
- Backtest and live read the same entry-signal single source (`docs/claude/architecture.md`).
- Numerics: no division by zero, NaN does not propagate into a gate, gates end in `.fillna(False)`, price comparisons use a tolerance.
- Frictions are applied once, in `swingbot/core/edge/frictions.py`, never again downstream.
- Runs reproduce: seeds fixed (`WEEK_BOOTSTRAP_SEED` in `swingbot/core/backtesting/instrument/stats.py`), window and universe recorded in the results doc, the cache not refetched mid-study.
- Long runs print flushed progress and a percent figure (`docs/claude/working-conventions.md` § Long-running scripts must report progress).
- No claim assumes deeper intraday history than Yahoo serves (`.claude/skills/task-brief/SKILL.md` step 3d).
- Split adjustment and timezones agree between the caches (`swingbot/core/marketdata/adjustments.py`).
- A parity test pins live and backtest to the same output, run with `python scripts/dev/testrun.py file <test>`.

## Red flags

- Any lookahead: a value at bar k that changes when later bars are removed.
- A backtest reading `market_data/`, or a live path reading `data/backtest_cache/`, by accident.
- A result that cannot be reproduced from its recorded command, window and universe.

## Out of scope

- Whether the result is statistically meaningful: `quant-researcher`.
- Whether an indicator matches its textbook definition: `technical-analyst`.
- General code quality and complexity: `senior-engineer`.

## Trigger table

Should fire: reviewing a backtest script change that loads OHLCV data from a cache.
Should fire: asking why the replay disagrees with the live scan for one alert.
Should fire: asking whether a new results doc can be reproduced from its recorded command.
Should not fire: judging whether a grid winner is overfit.
Should not fire: reviewing alert copy for how a retail reader will take it.
Should not fire: checking stop placement against the 2% cap.
```

- [ ] **Step 5: Write `.claude/skills/senior-engineer/SKILL.md`**

Exactly:

```markdown
---
name: senior-engineer
description: Use when reviewing a diff or a plan task from the senior-engineer seat -- code-level quality inside the change: correctness at the line, the cyclomatic complexity limit, tests that prove behaviour, wiring that takes effect, and code that reads like its surroundings -- or when the expert-reviewer agent is dispatched with role=senior-engineer. task-reviewer preloads it. Not for cross-package design or migrations (staff-engineer) and not for lookahead or caches (quant-engineer).
---

# Senior engineer

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Code-level quality inside the diff: correct at the line, under the complexity
limit, proven by tests, wired where it takes effect, and reading like the
code around it.

## Checklist

- Every function the diff writes or changes is under the limit in `docs/claude/code-complexity.md` (`python -m radon cc -s -n C <files>`); a legacy function already over it got no worse.
- A refactor changes no behaviour (`code-complexity.md` § A refactor must not change behaviour).
- Tests came first and failed for the right reason; each asserts behaviour, not implementation.
- The narrow run (`python scripts/dev/testrun.py file <test>`) passes and its verdict line is quoted; "should pass" is not evidence.
- Wiring lands where it takes effect: sizing and embed fields in `swingbot/core/scanning/engine.py`, not the posting path in `swingbot/commands/scanning.py` (`.claude/skills/task-brief/SKILL.md` step 3b).
- Embed fields go through the `sections["headline"]` accumulator in `swingbot/core/scanning/embeds.py`, never a raw `add_field`.
- No silent no-op: no call into a removed shim or an unwired function (`docs/claude/known-traps.md`).
- Names, error handling and structure match the surrounding module; an existing helper is reused rather than re-written.
- A stored record changes shape only per `docs/claude/schema-evolution.md`, with no read-time upcasting.
- Every symbol the brief names exists (`git grep -n`), or the task that creates it is named.
- No dead code, debug prints or commented-out blocks remain.
- The edge cases the brief names (empty frame, missing ticker, NaN) each have a test.

## Red flags

- A function the diff touched that is at or over the complexity limit.
- A behaviour change hidden inside a refactor.
- A wiring change that is a silent no-op.
- A claim of passing tests with no run output behind it.

## Out of scope

- Cross-package design, migrations and VM operations: `staff-engineer`.
- Lookahead and the OHLCV cache plumbing: `quant-engineer`.
- Whether the feature is worth building at all: `quant-researcher`.

## Trigger table

Should fire: reviewing one plan task's diff for complexity and test quality.
Should fire: asking whether a refactor of `scanning/engine.py` preserves behaviour.
Should fire: checking that a new helper reads like the module around it.
Should not fire: reviewing a schema migration's rollback plan.
Should not fire: checking whether a backtest reads the right OHLCV cache.
Should not fire: asking whether an alert is tradeable at the open.
```

- [ ] **Step 6: Write the eighteen trigger cases**

Write two files per row with the Write tool (never a shell loop: see the index's note on the word that a worktree session refuses). For case directory `<case>` of role `<role>`:

`.claude/skills/<role>/evals/<case>/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

<prompt text from the table below, verbatim>
```

`.claude/skills/<role>/evals/<case>/graders/skill-fired.md` for a `fire-*` row:

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 1
---

The `<role>` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

and for a `no-fire-*` row (the explicit `min: 0` is required: `min` defaults to 1, so a bare `max: 0` asks for the impossible range `1..0`):

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 0
max: 0
---

The `<role>` skill must stay silent on this prompt: it is a should-not-fire row of that skill's trigger table.
```

Each row mirrors one line of that skill's `## Trigger table`; the should-not-fire rows are deliberately a neighbouring role's lens.

**`staff-engineer`** — six directories under `.claude/skills/staff-engineer/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-new-table-and-cron` | `min: 1` | Review this spec: it adds a Postgres table for alert outcomes and a nightly cron on the Hetzner VM that fills it. |
| `fire-cross-package-move` | `min: 1` | I want to move the stop-scope logic from `swingbot/core/planning` into `swingbot/core/scanning`. Is that safe to ship? |
| `fire-deploy-rollback` | `min: 1` | Review the rollback story in this deploy plan: if the new image fails on the VM, how do we get back? |
| `no-fire-function-complexity` | `min: 0`, `max: 0` | Check whether `_build_headline` in this task's diff is over the cyclomatic complexity limit. |
| `no-fire-backtest-cache` | `min: 0`, `max: 0` | After my change, does `scripts/backtest/run_backtest_range.py` read `data/backtest_cache/` or `market_data/`? |
| `no-fire-overfit-lift` | `min: 0`, `max: 0` | Is the ExpR lift for the MACD bullish cell in the v104 results real, or overfit? |

**`quant-engineer`** — six directories under `.claude/skills/quant-engineer/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-backtest-cache-load` | `min: 1` | Review my change to `scripts/backtest/run_backtest_range.py` that loads OHLCV data from the cache. |
| `fire-replay-disagrees` | `min: 1` | Why does the replay disagree with the live scan for yesterday's NVDA alert? |
| `fire-reproduce-results` | `min: 1` | Can the v128 FVG results doc be reproduced from the command it recorded? |
| `no-fire-grid-overfit` | `min: 0`, `max: 0` | Is the grid winner in the v103 results doc overfit? |
| `no-fire-retail-copy` | `min: 0`, `max: 0` | Review the new alert footer copy for how a retail trader will read it. |
| `no-fire-stop-cap` | `min: 0`, `max: 0` | Does the new stop placement respect the 2% cap? |

**`senior-engineer`** — six directories under `.claude/skills/senior-engineer/evals/`:

| Case directory | Grader | Prompt text |
|---|---|---|
| `fire-task-diff-review` | `min: 1` | Review this plan task's diff for complexity and test quality before I merge it. |
| `fire-refactor-behaviour` | `min: 1` | Is my refactor of `swingbot/core/scanning/engine.py` behaviour-preserving? |
| `fire-helper-reads-like-module` | `min: 1` | Does the new helper in `scanning/qualify.py` read like the rest of the module? |
| `no-fire-migration-rollback` | `min: 0`, `max: 0` | Review the rollback plan for the schema migration in this spec. |
| `no-fire-backtest-cache` | `min: 0`, `max: 0` | Does the backtest read the right OHLCV cache after this change? |
| `no-fire-alert-tradeable` | `min: 0`, `max: 0` | Is this alert actually tradeable at the open? |

- [ ] **Step 7: Add the three table rows to `docs/claude/skills-tools.md`**

Append directly below the `fundamental-analyst` row of the `## Expert roles (v145)` table:

```markdown
| `staff-engineer` | opus | Cross-cutting design: seams, migrations, VM ops, blast radius, long-run cost |
| `quant-engineer` | sonnet | Backtest and data plumbing: lookahead (loads `no-lookahead`), numerics, the two OHLCV caches, reproducibility |
| `senior-engineer` | sonnet | Code-level quality, the complexity limit, reads like its surroundings; `task-reviewer` preloads it |
```

- [ ] **Step 8: Mirror to Codex**

In `AGENTS.md`, replace the expert-role paragraph (the one starting `Expert role skills (v145)`) with:

```markdown
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
`quant-engineer` (lookahead, numerics, the two OHLCV caches, reproducibility),
`senior-engineer` (code-level quality and the complexity limit).
A role raises cited `BLOCKING`/`ADVISORY` findings; it never decides and never
lowers a gate.
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.`

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: PASS, `0 failed` — `test_every_lens_skill_is_a_registered_role` now sees all nine.

- [ ] **Step 10: Commit**

```bash
git add tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py .claude/skills/staff-engineer .claude/skills/quant-engineer .claude/skills/senior-engineer .agents/skills docs/claude/skills-tools.md AGENTS.md
git commit -m "feat(v145): staff-engineer, quant-engineer and senior-engineer role skills with trigger cases"
```
