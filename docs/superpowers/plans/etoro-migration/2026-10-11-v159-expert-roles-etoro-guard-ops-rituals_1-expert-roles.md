# v159 Four expert seats, a demo-only eToro guard, and the ops/UI rituals. Implementation Plan, part 1 (expert roles)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief ER2` or `grep -n "^### Task ER2" -A 300 <this file>`.

**Spec:** [`docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md`](../../specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md) (§ A)
**Index:** [`2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md`](2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md): header block, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints.

**Tasks in this part:** ER1, ER2, ER3, ER4. Strictly serial, in id order: all four append to the same registries (`ROLES`, `TIER_1_AND_3`, the `skills-tools.md` roles table, `AGENTS.md`), ER3 names the roles ER1 and ER2 create, and ER4 edits the `execution-specialist` row ER1 writes.

**Paths.** Every command uses the absolute worktree path
`E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals`,
set as `WT=...` at the top of each command block (shell state does not
persist between calls). Never `cd`. `scripts/dev/testrun.py` and
`scripts/dev/sync_codex.py` resolve the repo root from their own path, so
running the worktree copy runs against the worktree. File edits go through the
Edit/Write tools on `$WT/<path>`.

# Phase A: Four expert seats, the roster and the panel defaults

Three things hold for every task in this phase:

- **Role skill shape** (`tests/hooks/test_role_skills.py`, `test_skill_shape.py`): frontmatter `name` + a double-quoted `description` of at most 260 characters that contains `the <role> seat`, `Not for` and at least one `(<other-role>)` hand-off, and never the string `expert-reviewer`; body sections `## Lens`, `## Checklist` (8 to 15 `- ` items), `## Red flags`, `## Out of scope`, in that order, then `## Trigger table` with three `Should fire:` and three `Should not fire:` lines; the boundary phrases `never decide`, `never lower a gate`, `` `pooled-numbers` ``, `` `backtest-gate` ``, `BLOCKING`, `ADVISORY`; at most 80 lines; no bare threshold (no `>= 5`, `< 15`, `= 10`, `3 R`, `2pp`).
- **Eval cases** live under `.claude/skills/<role>/evals/<fire-*|no-fire-*>/` as `prompt.md` + `graders/skill-fired.md`. A no-fire grader carries both `min: 0` and `max: 0`. Never run the eval suites (each case is a paid `claude` run).
- **Codex mirror** in the same commit: `python "$WT/scripts/dev/sync_codex.py"`, then stage only the generated files of the skills and agents the task touched (`git -C "$WT" add .agents/skills/<name> .codex/agents/<name>.toml`), never `git add -A .agents`.

### Task ER1: Seats `execution-specialist` and `compliance-reviewer`, plus `compliance-publication.md`

**Model:** sonnet — two markdown role skills in a fixed, test-pinned shape plus a new reference doc and one-line registry appends; no code design.

**Files:**
- Create: `.claude/skills/execution-specialist/SKILL.md`
- Create: `.claude/skills/execution-specialist/evals/fire-broker-order-client/prompt.md` (+ `graders/skill-fired.md`)
- Create: `.claude/skills/execution-specialist/evals/fire-limit-vs-market-preopen/prompt.md` (+ grader)
- Create: `.claude/skills/execution-specialist/evals/fire-partial-fill-reconcile/prompt.md` (+ grader)
- Create: `.claude/skills/execution-specialist/evals/no-fire-risk-cap-size/prompt.md` (+ grader)
- Create: `.claude/skills/execution-specialist/evals/no-fire-open-liquidity/prompt.md` (+ grader)
- Create: `.claude/skills/execution-specialist/evals/no-fire-track-record-wording/prompt.md` (+ grader)
- Create: `.claude/skills/compliance-reviewer/SKILL.md`
- Create: `.claude/skills/compliance-reviewer/evals/fire-track-record-page/prompt.md` (+ grader)
- Create: `.claude/skills/compliance-reviewer/evals/fire-personalised-recommendation/prompt.md` (+ grader)
- Create: `.claude/skills/compliance-reviewer/evals/fire-uk-risk-warning/prompt.md` (+ grader)
- Create: `.claude/skills/compliance-reviewer/evals/no-fire-tax-drag/prompt.md` (+ grader)
- Create: `.claude/skills/compliance-reviewer/evals/no-fire-order-retry/prompt.md` (+ grader)
- Create: `.claude/skills/compliance-reviewer/evals/no-fire-backtest-lift/prompt.md` (+ grader)
- Create: `docs/claude/compliance-publication.md`
- Modify: `.claude/skills/financial-advisor/SKILL.md` (one `## Out of scope` bullet naming `compliance-reviewer`; spec § A: "Both `Out of scope` sections name the other seat")
- Modify: `tests/hooks/test_role_skills.py`
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `docs/claude/skills-tools.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Generated: `.agents/skills/execution-specialist/SKILL.md`, `.agents/skills/compliance-reviewer/SKILL.md`, `.agents/skills/financial-advisor/SKILL.md`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `ROLES["execution-specialist"] = "opus"`, `ROLES["compliance-reviewer"] = "opus"` in `tests/hooks/test_role_skills.py`; both names in `TIER_1_AND_3`; roles-table rows beginning `` | `execution-specialist` | opus | `` and `` | `compliance-reviewer` | opus | `` in `docs/claude/skills-tools.md` § Expert roles (ER4 appends the `Places-orders:` owner note to the first); `docs/claude/compliance-publication.md` with sections `## Audience regimes`, `## Paper, demo and real stay apart`, `## Publish all, or state the filter`, `## Draft disclosure and risk warning`; the AGENTS.md role paragraph ending in the `compliance-reviewer` entry that ER2 extends (exact text in Step 9).

- [ ] **Step 0: Create the worktree**

Load the `worktree-lifecycle` skill first. If `git worktree list` already shows the worktree, reuse it and skip the `add`.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals -b 2026-10-11-v159-expert-roles-etoro-guard-ops-rituals main
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" log --oneline -1
wc -l "$WT/CLAUDE.md"
```

Expected: the worktree is on the new branch at `main`'s HEAD; `CLAUDE.md` is 198 lines.

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/hooks/test_role_skills.py`, extend `ROLES` (after `"senior-engineer": "sonnet",`):

```python
    "senior-engineer": "sonnet",
    "execution-specialist": "opus",   # v159: closest seat to real money
    "compliance-reviewer": "opus",    # v159: legal nuance across three regimes
}
```

Change the module docstring's first line from `one shape for nine lenses.` to `one shape for every lens.` (the count lives in `ROLES`, not in prose).

Append at the end of the file:

```python
# -- v159 § A: the execution and compliance seats ---------------------------

COMPLIANCE_DOC = ROOT / "docs/claude/compliance-publication.md"
COMPLIANCE_SECTIONS = ("## Audience regimes", "## Paper, demo and real stay apart",
                       "## Publish all, or state the filter",
                       "## Draft disclosure and risk warning")


def test_execution_specialist_names_the_demo_guard_and_order_mechanics():
    body = _body("execution-specialist")
    for phrase in ("assert_demo", "idempotency key", "CFD", "stops only tighten",
                   "broker/sizing.py", "broker/pre_open.py"):
        assert phrase in body, phrase


def test_compliance_reviewer_is_educational_and_never_rules():
    body = _body("compliance-reviewer")
    assert "Educational only" in body
    assert "`needs counsel`" in body
    assert "compliance-publication.md" in body


def test_compliance_and_financial_advisor_hand_off_to_each_other():
    assert "`financial-advisor`" in _section(_body("compliance-reviewer"), "## Out of scope")
    assert "`compliance-reviewer`" in _section(_body("financial-advisor"), "## Out of scope")


def test_compliance_publication_doc_has_its_four_sections():
    text = _text(COMPLIANCE_DOC)
    missing = [h for h in COMPLIANCE_SECTIONS if f"\n{h}\n" not in text]
    assert not missing, missing
    assert "draft — partner to approve" in _section(text, "## Draft disclosure and risk warning")


def test_compliance_publication_doc_is_indexed_in_both_instruction_files():
    claude_md = _text(ROOT / "CLAUDE.md")
    assert "| `compliance-publication.md` |" in claude_md
    assert len(claude_md.splitlines()) < 200
    assert "docs/claude/compliance-publication.md" in _text(ROOT / "AGENTS.md")
```

In `$WT/tests/hooks/test_skill_shape.py`, extend `TIER_1_AND_3` (the last line of the set literal):

```python
                "staff-engineer", "quant-engineer", "senior-engineer",
                "execution-specialist", "compliance-reviewer"}   # each skill task appends its own name
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
```

Expected: FAIL. `test_role_skills.py` fails every parametrised case for the two new roles (`FileNotFoundError` on `.claude/skills/execution-specialist/SKILL.md`) and the five new tests; `test_skill_shape.py` fails `test_every_skill_is_registered_in_exactly_one_tier` (two names registered with no directory).

- [ ] **Step 3: Write `execution-specialist/SKILL.md`**

Create `$WT/.claude/skills/execution-specialist/SKILL.md` with exactly:

```markdown
---
name: execution-specialist
description: "Use when reviewing a spec, plan or diff from the execution-specialist seat -- order types, stops attached at order time, idempotent submit, reconciliation, CFD vs real share, demo-only guard. Not for cap values (risk-manager) or tradeability (veteran-trader)."
---

# Execution specialist

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Order mechanics between a trade plan and the broker book: what is sent, how it
rests, what it fills at, and whether the journal and the broker agree
afterwards. This is the seat closest to real money. Until the partner unlocks
stage 3, every order is a demo order (`docs/claude/etoro-roadmap.md`).

## Checklist

- Every order path calls `swingbot/core/broker/guard.py:assert_demo` before it sends, then v160's sizing (`broker/sizing.py`) and pre-open checks (`broker/pre_open.py`); a hand-rolled check is never a substitute.
- A resting pre-open order is a limit order, never a market order that fills at whatever the open prints.
- Stop loss and take profit are attached to the order when it is sent, not added by a later call that can fail.
- After entry a stop only ever tightens; no code path moves it away from price.
- Submit carries an idempotency key, and a retry reads the broker state first instead of resending blind.
- Every order sent or rejected writes a journal entry; a rejection records the check that refused it.
- A partial fill is journalled as the units actually filled, and the stop covers what was filled.
- The instrument type (CFD or real share) is read from the broker and journalled with its leverage, margin and overnight financing; a CFD's gap and stop-fill model is never assumed to match a real share's.
- Drift between the paper fill and the demo fill is measured in R per trade, not waved through as noise.
- The journal is reconciled against the broker book (the `reconciler` agent's contract): orphan or missing positions, size and stop mismatches.
- A broker error or timeout leaves a state that can be read back and reconciled, never a half-sent order with no record.
- No real-account marker (`account: real`, a trading route without `/demo/`) appears in code, scripts or MCP calls; `.claude/hooks/guardrails.py` denies them and `assert_demo` is the second layer.

## Red flags

- Any order path that skips `assert_demo` or v160's sizing and pre-open checks.
- Order submit without an idempotency key or a journal entry.
- A market order resting overnight.
- A position that can exist without an attached stop.
- Any stop move away from price after entry (stops only tighten).
- Instrument type (CFD or real share) not read and journalled.

## Out of scope

- Cap values and sizing policy (the 2% dollar-risk rule, the heat caps): `risk-manager`.
- Whether the setup itself is tradeable at the open: `veteran-trader`.
- Cost and tax presentation of demo against real: `financial-advisor`.

## Trigger table

Should fire: reviewing a diff that adds an eToro order client under `swingbot/core/broker/`.
Should fire: asking whether a resting pre-open order should be a limit or a market order.
Should fire: asking how to reconcile the journal against the eToro demo portfolio after a partial fill.
Should not fire: asking whether the 2% dollar-risk cap is the right size for the account.
Should not fire: asking whether a breakout alert's entry is liquid enough to fill at the open.
Should not fire: reviewing the wording of a published track record on bomeo-capital.com.
```

- [ ] **Step 4: Write `compliance-reviewer/SKILL.md`**

Create `$WT/.claude/skills/compliance-reviewer/SKILL.md` with exactly:

```markdown
---
name: compliance-reviewer
description: "Use when reviewing published content, a spec or a diff from the compliance-reviewer seat -- disclosures, risk warnings, the personalised-recommendation test, paper, demo and real kept apart. Not for suitability, cost or tax (financial-advisor)."
---

# Compliance reviewer

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

Regulatory wording and disclosures in what the bot publishes on
bomeo-capital.com and in Discord, read against three regimes: EU MAR Art. 20
and MiFID II, UK FCA financial promotions, and US SEC/FINRA. You check content
against the audience and disclosure text in
`docs/claude/compliance-publication.md`; you never write the final disclosure.
Educational only: this seat gives no legal advice, and a doubtful case is a
`needs counsel` finding, never a ruling.

## Checklist

- Every published figure is labelled paper, demo or real, and no figure or track record mixes two of them (`compliance-publication.md` § Paper, demo and real stay apart).
- A figure shown before costs, financing or tax says so beside the figure.
- ExpR leads and win rate follows (`docs/claude/edge-priorities.md`).
- Each strategy shown carries its badge tier, and each figure its as-of date.
- The page shows every plan the bot issued with its outcome, or states which subset it shows (§ Publish all, or state the filter).
- Hypothetical or backtested results state their method and window, and say they are hypothetical.
- A public plan with entry, stop and size is tested against the personalised-recommendation line (MiFID II investment advice): a sizing line is illustrative, never "your size".
- EU MAR Art. 20: a published recommendation names its author and date and discloses the author's interest (the partner trades the same alerts).
- UK FCA: the promotion is fair, clear and not misleading, and the risk warning sits with the content, not behind a link.
- US SEC/FINRA: content stays impersonal, bona fide and regularly published (the publisher's exclusion), and past or hypothetical performance carries its limits.
- The disclosure used is the one in § Draft disclosure and risk warning, still marked draft until the partner approves it.
- Anything this checklist cannot settle is raised as `needs counsel`, never decided here.

## Red flags

- Published performance not labelled paper, demo or real, or two of those mixed in one figure or track record.
- A figure before costs, financing or tax shown without saying so.
- Win rate led ahead of ExpR.
- A strategy shown without its badge tier, or a stale figure without its as-of date.
- Publishing only filled or approved plans without stating the filter (cherry-picking).
- Hypothetical results without the method.
- A published recommendation with no risk warning, or no disclosure of the author's interest.

## Out of scope

- Suitability, cost and tax presentation, alert cadence and "never promises returns" framing: `financial-advisor`.
- Whether a published figure is statistically sound: `quant-researcher`.
- Layout and readability of the published page: `ux-designer`.
- Legal advice: no seat gives it; a doubtful case goes to counsel.

## Trigger table

Should fire: reviewing the track-record page before it goes live on bomeo-capital.com.
Should fire: asking whether a public trade plan with entry, stop and size reads as a personalised recommendation.
Should fire: asking what risk warning a published Discord alert needs for UK readers.
Should not fire: asking whether swing turnover's tax drag suits a retail account.
Should not fire: reviewing the retry logic of the eToro order client.
Should not fire: asking whether a backtest lift is statistically real.
```

- [ ] **Step 5: Write the twelve eval cases**

Every `prompt.md` has this frontmatter, a blank line, then the prompt from the table below:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

<prompt from the table>
```

Every fire grader (`graders/skill-fired.md`) is, with `<role>` replaced by the skill name:

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 1
---

The `<role>` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

Every no-fire grader is:

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

Prompts (one per directory, under `$WT/.claude/skills/`):

| Directory | Prompt |
|---|---|
| `execution-specialist/evals/fire-broker-order-client` | Review this diff before I merge it: it adds an eToro order client under `swingbot/core/broker/` that sends the morning's plans to the demo account. |
| `execution-specialist/evals/fire-limit-vs-market-preopen` | The bot rests its eToro orders overnight before the US open. Should those be limit orders or market orders? |
| `execution-specialist/evals/fire-partial-fill-reconcile` | One demo order only half filled. How should the journal be reconciled against the eToro demo portfolio now? |
| `execution-specialist/evals/no-fire-risk-cap-size` | Is a 2% dollar-risk cap the right size for a twenty-thousand-dollar account, or should it be lower? |
| `execution-specialist/evals/no-fire-open-liquidity` | Is this breakout alert's entry on a thin small-cap liquid enough to get filled at the open? |
| `execution-specialist/evals/no-fire-track-record-wording` | Read the wording of the track-record paragraph we publish on bomeo-capital.com and tell me if it is clear. |
| `compliance-reviewer/evals/fire-track-record-page` | Before the track-record page goes live on bomeo-capital.com, review what it shows and how it labels the results. |
| `compliance-reviewer/evals/fire-personalised-recommendation` | If we publish a trade plan with entry, stop and suggested size on a public page, does that count as a personalised recommendation? |
| `compliance-reviewer/evals/fire-uk-risk-warning` | What risk warning does an alert we post in a public Discord channel need for readers in the UK? |
| `compliance-reviewer/evals/no-fire-tax-drag` | How much does the tax drag of swing turnover hurt a retail account trading these alerts? |
| `compliance-reviewer/evals/no-fire-order-retry` | Review the retry logic in the eToro order client: does it resend an order after a timeout? |
| `compliance-reviewer/evals/no-fire-backtest-lift` | The new filter lifted backtest ExpR on the train window. Is that lift statistically real? |

- [ ] **Step 6: Write `docs/claude/compliance-publication.md`**

Create `$WT/docs/claude/compliance-publication.md` with exactly:

```markdown
# Publishing trade plans and results: compliance reference

Read before publishing anything the bot produces outside the private Discord
alert channel: the bomeo-capital.com page, a public channel, a track record.
The `compliance-reviewer` seat checks published content against this file.
It is an educational reference, not legal advice: where it does not settle a
case, the finding is `needs counsel` and the partner decides with a lawyer.
Suitability, cost and tax presentation belong to the `financial-advisor` seat.

## Audience regimes

The page can be read in three regimes. Content is written to pass all three,
because a public page cannot choose its reader.

- **EU.** MAR Art. 20 and Delegated Regulation (EU) 2016/958: an investment
  recommendation names its author and date, presents facts apart from
  opinion, and discloses the author's interests and conflicts. MiFID II: a
  recommendation presented as suitable for a person, or based on their
  circumstances, is a **personalised recommendation** (investment advice) and
  needs authorisation. A public plan with entry, stop and size stays general
  research only if it is impersonal and its sizing line is illustrative.
- **UK.** FSMA s.21 and the FCA COBS 4 rules on financial promotions: fair,
  clear and not misleading; benefits never shown without the risks; a risk
  warning that sits with the content. Promotions of CFDs carry the FCA's
  prescribed retail-loss warning.
- **US.** Investment Advisers Act publisher's exclusion (*Lowe v. SEC*):
  content that is impersonal, bona fide and regularly published is not
  investment advice. FINRA Rule 2210 governs member firms' communications;
  where it or the SEC Marketing Rule could apply, past and hypothetical
  performance is shown with its method and limits.

## Paper, demo and real stay apart

The bot produces three kinds of result: **paper** (the journal's simulated
fills), **demo** (eToro demo-account fills, roadmap stage 2) and **real**
(stage 3, not unlocked). Every published figure says which kind it is. No
figure, chart or track record combines two kinds, and a page that shows more
than one shows them side by side, each labelled. A figure before costs,
financing or tax says so beside the figure. ExpR leads and win rate follows
(`edge-priorities.md`); each strategy shown carries its badge tier, and each
figure its as-of date.

## Publish all, or state the filter

Every plan the bot issues is published with its outcome: filled, unfilled,
rejected (with the reason) or not approved. A page that shows only a subset
(filled plans, approved plans, one strategy) says so above the subset, in
words, before any figure. Silently showing only the winners, or only the plans
the partner took, is cherry-picking and is always a finding.

## Draft disclosure and risk warning

Status: `draft — partner to approve`. Not for publication until the partner
approves the final wording; the seat checks that published text matches the
approved version, and never writes it.

> Trade plans on this page are produced automatically by a rules-based scanner
> and are published for educational and informational purposes only. They are
> not investment advice and not a personal recommendation: they take no
> account of your objectives, financial situation or needs. The author trades
> the same plans in his own account and therefore has an interest in the
> instruments shown. Results are labelled paper, demo or real and are never
> combined. Figures are shown before costs, financing and tax unless stated
> otherwise beside the figure. Past and hypothetical performance is not a
> reliable indicator of future results. Trading shares and CFDs carries a high
> risk of losing money; CFDs are leveraged, and most retail CFD accounts lose
> money (state the provider's current published percentage here). Only trade
> money you can afford to lose.
```

- [ ] **Step 7: Name `compliance-reviewer` in `financial-advisor`'s Out of scope**

In `$WT/.claude/skills/financial-advisor/SKILL.md`, replace:

```markdown
- Design and operations of the admin UI itself: `staff-engineer`.
```

with:

```markdown
- Design and operations of the admin UI itself: `staff-engineer`.
- Regulatory wording, disclosures, risk warnings and the personalised-recommendation test in published content: `compliance-reviewer`.
```

(59 lines → 60, under the 80-line budget.)

- [ ] **Step 8: Registry rows in `skills-tools.md` and `CLAUDE.md`**

In `$WT/docs/claude/skills-tools.md` § Expert roles (v145), append two rows after the `senior-engineer` row:

```markdown
| `execution-specialist` | opus | Order mechanics: order types, limit vs market for resting pre-open orders, stop and target attached at order time, partial fills, idempotent submit and retry, journal-vs-broker reconciliation, CFD vs real share, demo-only enforcement (`assert_demo`) |
| `compliance-reviewer` | opus | Published content (bomeo-capital.com, Discord) against EU MAR/MiFID II, UK FCA promotions and US SEC/FINRA: disclosures, risk warnings, the personalised-recommendation test, paper/demo/real kept apart; checked against `compliance-publication.md`; educational only, doubt is `needs counsel` |
```

In `$WT/CLAUDE.md` § Reference docs, append one row after the `etoro-roadmap.md` row (198 → 199 lines):

```markdown
| `compliance-publication.md` | publishing plans or results (bomeo-capital.com, public channels) — audience regimes, paper/demo/real apart, draft disclosure |
```

- [ ] **Step 9: Condensed mirror in `AGENTS.md`**

In `$WT/AGENTS.md`, in the "Expert role skills (v145)" paragraph, replace:

```markdown
`senior-engineer` (code-level quality and the complexity limit).
```

with:

```markdown
`senior-engineer` (code-level quality and the complexity limit),
`execution-specialist` (order types, stops attached at order time, idempotent
submit, journal-vs-broker reconciliation, CFD vs real share, demo-only
enforcement), `compliance-reviewer` (disclosures and risk warnings in published
plans across EU, UK and US; paper, demo and real kept apart; educational only,
doubt is `needs counsel`).
```

In the reading list, after the `docs/claude/schema-evolution.md` bullet (it ends `(add, rename, drop, promote).`), add:

```markdown
- `docs/claude/compliance-publication.md` before publishing trade plans or
  results (bomeo-capital.com, public channels): audience regimes, paper, demo
  and real kept apart, publish-all-or-state-the-filter, the draft disclosure.
```

- [ ] **Step 10: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
```

Expected: `Codex mirror is current.`; status shows only this task's files plus `.agents/skills/execution-specialist/SKILL.md`, `.agents/skills/compliance-reviewer/SKILL.md` and `.agents/skills/financial-advisor/SKILL.md`.

- [ ] **Step 11: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_spec_panel_header.py
wc -l "$WT/CLAUDE.md" "$WT/.claude/skills/execution-specialist/SKILL.md" "$WT/.claude/skills/compliance-reviewer/SKILL.md"
```

Expected: all four files `0 failed`; `CLAUDE.md` 199 lines; each SKILL.md at most 80 lines. If `test_role_description_fits_the_listing_cap` fails, shorten the description inside the cap; never raise `MAX_ROLE_DESCRIPTION`. If `test_new_skills_restate_no_thresholds` fails, reword the matched line so no operator or `<n> R` sits beside a number.

- [ ] **Step 12: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/skills/execution-specialist .claude/skills/compliance-reviewer .claude/skills/financial-advisor/SKILL.md docs/claude/compliance-publication.md tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py docs/claude/skills-tools.md CLAUDE.md AGENTS.md .agents/skills/execution-specialist .agents/skills/compliance-reviewer .agents/skills/financial-advisor
git -C "$WT" commit -m "feat(v159): execution-specialist and compliance-reviewer seats, compliance-publication.md

Two opus role skills in the v145 shape with 3+3 trigger cases each,
registered in ROLES, TIER_1_AND_3 and the skills-tools.md roles table.
compliance-publication.md holds the audience regimes, the paper/demo/real
separation, publish-all-or-state-the-filter and a draft disclosure marked
for partner approval. financial-advisor's Out of scope now names
compliance-reviewer. Codex mirror regenerated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER2: Seats `ux-designer` and `sre`

**Model:** sonnet — two more markdown role skills in the shape ER1 established, with the same one-line registry appends; no code design.

**Files:**
- Create: `.claude/skills/ux-designer/SKILL.md`
- Create: `.claude/skills/ux-designer/evals/fire-dark-mode-dashboard/prompt.md` (+ `graders/skill-fired.md`)
- Create: `.claude/skills/ux-designer/evals/fire-mobile-embed/prompt.md` (+ grader)
- Create: `.claude/skills/ux-designer/evals/fire-heat-display/prompt.md` (+ grader)
- Create: `.claude/skills/ux-designer/evals/no-fire-embed-crash/prompt.md` (+ grader)
- Create: `.claude/skills/ux-designer/evals/no-fire-uk-disclaimer/prompt.md` (+ grader)
- Create: `.claude/skills/ux-designer/evals/no-fire-soak-clause/prompt.md` (+ grader)
- Create: `.claude/skills/sre/SKILL.md`
- Create: `.claude/skills/sre/evals/fire-soak-clauses/prompt.md` (+ grader)
- Create: `.claude/skills/sre/evals/fire-provider-failover/prompt.md` (+ grader)
- Create: `.claude/skills/sre/evals/fire-cron-placement/prompt.md` (+ grader)
- Create: `.claude/skills/sre/evals/no-fire-package-seam/prompt.md` (+ grader)
- Create: `.claude/skills/sre/evals/no-fire-ohlcv-caches/prompt.md` (+ grader)
- Create: `.claude/skills/sre/evals/no-fire-embed-layout/prompt.md` (+ grader)
- Modify: `tests/hooks/test_role_skills.py`
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.agents/skills/ux-designer/SKILL.md`, `.agents/skills/sre/SKILL.md`

**Interfaces:**
- Consumes: ER1's `ROLES` entries (`compliance-reviewer` must already be a role, because `ux-designer`'s description hands off to `(compliance-reviewer)` and `test_role_description_keeps_its_seat_and_a_hand_off` only accepts a hand-off to a registered role); ER1's AGENTS.md paragraph ending `` doubt is `needs counsel`). ``.
- Produces: `ROLES["ux-designer"] = "sonnet"`, `ROLES["sre"] = "sonnet"`; both names in `TIER_1_AND_3`; roles-table rows beginning `` | `ux-designer` | sonnet | `` and `` | `sre` | sonnet | `` (ER14 appends the soak-lock owner note to the `sre` row; ER3 consumes all thirteen roles).

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/hooks/test_role_skills.py`, extend `ROLES` (after the two ER1 rows):

```python
    "compliance-reviewer": "opus",    # v159: legal nuance across three regimes
    "ux-designer": "sonnet",          # v159
    "sre": "sonnet",                  # v159
}
```

Append at the end of the file:

```python
# -- v159 § A: the ux-designer and sre seats --------------------------------

def test_ux_designer_shows_risk_in_dollars_and_expr_first():
    body = _body("ux-designer")
    for phrase in ("dollar risk", "`PORTFOLIO_HEAT_CAP_PCT`",
                   "ExpR is shown before win rate", "`ui-verifier`",
                   "`compliance-reviewer`"):
        assert phrase in body, phrase


def test_sre_flags_razor_edge_clauses_and_keeps_work_on_the_vm():
    body = _body("sre")
    for phrase in ("pre-registered before its window opens", "would flip it",
                   "never on the dev laptop", "`mirror-prod`", "ssh-hetzner.sh"):
        assert phrase in body, phrase
```

In `$WT/tests/hooks/test_skill_shape.py`, extend `TIER_1_AND_3`:

```python
                "execution-specialist", "compliance-reviewer",
                "ux-designer", "sre"}   # each skill task appends its own name
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
```

Expected: FAIL. The parametrised cases for `ux-designer` and `sre` and the two new tests fail with `FileNotFoundError`; `test_every_skill_is_registered_in_exactly_one_tier` fails.

- [ ] **Step 3: Write `ux-designer/SKILL.md`**

Create `$WT/.claude/skills/ux-designer/SKILL.md` with exactly:

```markdown
---
name: ux-designer
description: "Use when reviewing an admin screen, Discord embed, spec or diff from the ux-designer seat -- hierarchy, density, mobile, contrast, how risk and performance read. Not for embed code (senior-engineer) or regulatory wording (compliance-reviewer)."
---

# UX designer

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

How the admin SPA (`frontend/`) and the Discord alert embeds read to the
partner, who acts on them with real money: visual hierarchy, density, the one
action an alert asks for, mobile and PWA use, accessibility, light and dark
themes, and how risk and performance are shown. You judge `ui-verifier`
screenshots when they are supplied.

## Checklist

- An alert's entry, stop, target and size read on a phone without zooming, and the action it asks for is the first thing read.
- One primary figure per card or embed; secondary detail is visibly quieter, never the same weight.
- New panels follow the spacing the SPA already pins (`frontend/src/app/ui/spacing.spec.ts`).
- Both themes keep contrast (`frontend/src/app/ui/contrast.spec.ts`), and a colour that carries meaning also carries a label or an icon.
- R is never shown without the dollar risk beside it, and drawdown is shown in dollars as well as in R.
- Where open positions are listed, total open risk is shown against `PORTFOLIO_HEAT_CAP_PCT`.
- ExpR is shown before win rate (`docs/claude/edge-priorities.md`).
- A strategy figure carries its badge tier and a staleness cue (its as-of date).
- A sizing line reads as illustrative for the configured account, never as a recommendation to the reader.
- Every new control works from the keyboard with a visible focus and a screen-reader label; a dialog traps focus and closes on Escape.
- Each new view has an empty, a loading and an error state, and an empty table that is a measured answer says so (`docs/claude/known-traps.md`).
- The PWA's installed and offline states still render (`frontend/ngsw-config.json`).
- A judgement cites the `ui-verifier` screenshot path it rests on, or names the route and theme it was read in.

## Red flags

- An alert whose entry, stop or size can't be read on mobile.
- A theme that breaks contrast.
- R shown without dollar risk.
- Win rate shown above ExpR.

## Out of scope

- Embed code correctness: the `alert-surface` skill and `senior-engineer`.
- Regulatory wording, disclaimers and risk warnings: `compliance-reviewer`.
- Whether the figures shown are correct: `quant-researcher` and `risk-manager`.

## Trigger table

Should fire: reviewing a screenshot of the admin dashboard in dark mode for hierarchy and contrast.
Should fire: asking whether a Discord alert's entry, stop and size can be read on a phone.
Should fire: asking how the risk workspace should show open risk against the heat cap.
Should not fire: fixing a crash in the embed builder when a plan has no target price.
Should not fire: asking whether the disclaimer on bomeo-capital.com meets UK rules.
Should not fire: asking whether a soak's latency clause is fair.
```

- [ ] **Step 4: Write `sre/SKILL.md`**

Create `$WT/.claude/skills/sre/SKILL.md` with exactly:

```markdown
---
name: sre
description: "Use when reviewing a spec, plan or diff from the sre seat -- VM soaks and razor-edge clauses, data-provider failover, cron, logs and alerting, backup and PITR, capacity. Not for package design (staff-engineer) or backtest numerics (quant-engineer)."
---

# SRE

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

The Hetzner VM as a running service. Production is always that VM, reached
through `scripts/ops/ssh-hetzner.sh`, never the dev machine. The questions: does
a soak's verdict mean what it says, does a provider outage degrade visibly,
does scheduled work run where it should, would the logs and alerts tell us,
and does a restore work.

## Checklist

- A soak is pre-registered before its window opens: clauses, thresholds, measurement definitions and window dates are committed before the first sample (the `soak` ritual).
- Each ratio clause states how many events would flip it at the expected N; a clause a handful of events can flip is flagged in the pre-registration (v106's clause (c) was decided by two skips).
- A soak sampler runs as a cron on the VM, mirrored under `scripts/ops/`, and removes itself after its window.
- A failed soak is diagnosed from telemetry only, and a retry is a new pre-registration with a new attempt number, never an edit of the old one.
- Data-provider failover between yfinance and Alpaca (`swingbot/core/marketdata/`) falls over with a log line, never silently onto stale data.
- Far-off scheduled work runs on the VM, never on the dev laptop (`docs/claude/working-conventions.md` § Scheduling).
- Logs are read from `/opt/swing-bot/logs`, current and rotated files split, not from `docker logs` after a deploy.
- A failure that matters raises an alert someone sees; a new failure mode names where it is logged and who is told.
- A change to the database or its volume keeps `scripts/ops/rollback_to.sh` and the `pg_dump` files working (`docs/deploy/DB_RESTORE.md`).
- `.env` on the VM is a single-file bind mount: it is edited in place, never with `sed -i` or a rename (`docs/claude/known-traps.md`).
- A change that adds scan load, memory or disk states its effect on the VM's headroom, measured on the VM.
- Every live change on the VM is mirrored back into the repo and committed (the `mirror-prod` skill).

## Red flags

- A pass/fail clause one event can flip, with no flag.
- Work scheduled on the dev laptop.
- A live change not mirrored.

## Out of scope

- Cross-package design and the blast radius of a code change: `staff-engineer`.
- Cache, lookahead and backtest numerics: `quant-engineer`.
- Whether a statistical claim drawn from soak data holds: `quant-researcher`.

## Trigger table

Should fire: drafting the pass/fail clauses for the next v106 soak on the VM.
Should fire: asking what happens to scans when yfinance is down and Alpaca must take over.
Should fire: asking whether a new nightly job should run on the laptop or the VM.
Should not fire: reviewing where a new package should sit in `swingbot/core`.
Should not fire: asking whether the two OHLCV caches give the backtest the same bars.
Should not fire: reviewing a Discord embed's layout on mobile.
```

- [ ] **Step 5: Write the twelve eval cases**

Every `prompt.md` has this frontmatter, a blank line, then the prompt from the table below:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

<prompt from the table>
```

Every fire grader (`graders/skill-fired.md`) is, with `<role>` replaced by the skill name:

```markdown
---
type: tool_used
tool: Skill
input_match: <role>
min: 1
---

The `<role>` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

Every no-fire grader is:

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

Prompts (one per directory, under `$WT/.claude/skills/`):

| Directory | Prompt |
|---|---|
| `ux-designer/evals/fire-dark-mode-dashboard` | Here is a screenshot of the admin dashboard in dark mode. Is the hierarchy right, and is the contrast good enough? |
| `ux-designer/evals/fire-mobile-embed` | Can the entry, stop and size in our Discord alert embed actually be read on a phone? |
| `ux-designer/evals/fire-heat-display` | How should the risk workspace show the total open risk against the portfolio heat cap? |
| `ux-designer/evals/no-fire-embed-crash` | The embed builder crashes when a plan has no target price. Fix it. |
| `ux-designer/evals/no-fire-uk-disclaimer` | Does the disclaimer on bomeo-capital.com meet the UK rules for financial promotions? |
| `ux-designer/evals/no-fire-soak-clause` | Is the latency clause in the v106 soak fair, or can it be decided by a couple of slow scans? |
| `sre/evals/fire-soak-clauses` | Help me draft the pass/fail clauses for the next v106 soak on the production VM. |
| `sre/evals/fire-provider-failover` | What happens to the scans when yfinance is down and Alpaca has to take over? |
| `sre/evals/fire-cron-placement` | I want a nightly job that checks yesterday's scans. Should it run on my laptop or on the VM? |
| `sre/evals/no-fire-package-seam` | Where should a new broker package sit in `swingbot/core`, and what may import it? |
| `sre/evals/no-fire-ohlcv-caches` | Do the two OHLCV caches give the backtest the same bars as the live scan? |
| `sre/evals/no-fire-embed-layout` | Review the layout of the new Discord alert embed on mobile. |

- [ ] **Step 6: Registry rows in `skills-tools.md`**

In `$WT/docs/claude/skills-tools.md` § Expert roles (v145), append two rows after the `compliance-reviewer` row:

```markdown
| `ux-designer` | sonnet | Admin SPA and Discord embeds: hierarchy, density, the action an alert asks for, mobile/PWA, accessibility, light and dark themes; dollar risk beside R, open risk against `PORTFOLIO_HEAT_CAP_PCT`, badge tier and staleness, ExpR before win rate; judges `ui-verifier` screenshots |
| `sre` | sonnet | Hetzner VM: soak criteria and razor-edge clauses, yfinance/Alpaca failover, cron and scheduling, logs and alerting, backup and PITR, capacity |
```

- [ ] **Step 7: Condensed mirror in `AGENTS.md`**

In `$WT/AGENTS.md`, replace the tail ER1 wrote:

```markdown
doubt is `needs counsel`).
```

with:

```markdown
doubt is `needs counsel`), `ux-designer` (hierarchy, density, mobile, contrast
in both themes; dollar risk beside R, ExpR before win rate), `sre` (soak
criteria and razor-edge clauses, provider failover, cron on the VM, logs,
backup and PITR, capacity).
```

- [ ] **Step 8: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
```

Expected: `Codex mirror is current.`; status shows only this task's files plus `.agents/skills/ux-designer/SKILL.md` and `.agents/skills/sre/SKILL.md`.

- [ ] **Step 9: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
wc -l "$WT/.claude/skills/ux-designer/SKILL.md" "$WT/.claude/skills/sre/SKILL.md"
```

Expected: all three files `0 failed`; each SKILL.md at most 80 lines. A description over 260 characters is shortened inside the cap; a threshold-regex hit is reworded, never exempted.

- [ ] **Step 10: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/skills/ux-designer .claude/skills/sre tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py docs/claude/skills-tools.md AGENTS.md .agents/skills/ux-designer .agents/skills/sre
git -C "$WT" commit -m "feat(v159): ux-designer and sre seats

Two sonnet role skills in the v145 shape with 3+3 trigger cases each,
registered in ROLES, TIER_1_AND_3 and the skills-tools.md roles table,
condensed into AGENTS.md. Codex mirror regenerated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER3: Roster of thirteen and the new panel defaults

**Model:** haiku — exact text replacements in five markdown files and two test registries, all spelled out below; no judgement left to the implementer.

**Files:**
- Modify: `.claude/agents/expert-reviewer.md`
- Modify: `tests/hooks/test_agent_shape.py`
- Modify: `tests/hooks/test_role_skills.py`
- Modify: `docs/claude/persona.md`
- Modify: `docs/claude/document-conventions.md`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.codex/agents/expert-reviewer.toml`

**Interfaces:**
- Consumes: the thirteen keys of `ROLES` in `tests/hooks/test_role_skills.py` (nine from v145, four from ER1 and ER2).
- Produces: `EXPERT_ROLES` in `tests/hooks/test_agent_shape.py` with thirteen names; `test_role_skills.test_expert_reviewer_lists_every_role`; `test_role_skills.PANEL_DEFAULTS` and `_panel_table_rows()`; panel-table rows "eToro integration, anything that places an order", "Published content (bomeo-capital.com, public channels)", "Admin UI" (replaced) and "Production ops, soaks, providers" in `docs/claude/document-conventions.md`. ER4 adds its `Places-orders:` paragraph directly below that table.

**`/panel` is a no-op here.** The spec says "so does any count the `panel` skill quotes"; `grep -n "nine" .claude/skills/panel/SKILL.md` is empty, so `panel/SKILL.md` is not touched. The commit message records that.

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/hooks/test_agent_shape.py`, replace:

```python
# v145: the nine role skills expert-reviewer must name (spec § 1).
EXPERT_ROLES = ("quant-researcher", "staff-engineer", "veteran-trader",
                "risk-manager", "financial-advisor", "technical-analyst",
                "fundamental-analyst", "quant-engineer", "senior-engineer")
```

with:

```python
# v145 + v159: the thirteen role skills expert-reviewer must name.
EXPERT_ROLES = ("quant-researcher", "staff-engineer", "veteran-trader",
                "risk-manager", "financial-advisor", "technical-analyst",
                "fundamental-analyst", "quant-engineer", "senior-engineer",
                "execution-specialist", "compliance-reviewer", "ux-designer",
                "sre")
```

Append at the end of `$WT/tests/hooks/test_role_skills.py`:

```python
# -- v159 § A: the roster and the panel defaults ----------------------------

EXPERT_REVIEWER = ROOT / ".claude/agents/expert-reviewer.md"
CONVENTIONS = ROOT / "docs/claude/document-conventions.md"
PANEL_TABLE_HEADER = "| Spec is about… | Default panel |"
PANEL_DEFAULTS = {
    "eToro integration, anything that places an order":
        ("execution-specialist", "risk-manager", "financial-advisor"),
    "Published content (bomeo-capital.com, public channels)":
        ("compliance-reviewer", "financial-advisor"),
    "Admin UI": ("ux-designer", "staff-engineer", "financial-advisor"),
    "Production ops, soaks, providers": ("sre", "staff-engineer"),
}


def _panel_table_rows():
    """{subject: (role, ...)} from the document-conventions.md panel table.

    A panel cell may end in a parenthetical note; the roles are the
    comma-separated names before its first "(".
    """
    text = _text(CONVENTIONS)
    lines = text[text.index(PANEL_TABLE_HEADER):].splitlines()[2:]
    rows = {}
    for line in lines:
        if not line.startswith("|"):
            break
        subject, panel = (cell.strip() for cell in line.strip().strip("|").split("|"))
        rows[subject] = tuple(name.strip() for name in panel.split("(")[0].split(","))
    return rows


def test_expert_reviewer_lists_every_role():
    text = _text(EXPERT_REVIEWER)
    missing = [role for role in ROLES if f"`{role}`" not in text]
    assert not missing, missing
    assert len(ROLES) == 13
    assert "nine" not in text
    assert text.count("the thirteen roles") == 2   # description and return shape
    assert "Nine role skills" not in _text(SKILLS_TOOLS)


def test_panel_defaults_seat_the_new_roles():
    rows = _panel_table_rows()
    for subject, panel in PANEL_DEFAULTS.items():
        assert rows.get(subject) == panel, (subject, rows.get(subject))


def test_etoro_default_panel_makes_execution_specialist_mandatory():
    assert "**`execution-specialist` is mandatory**" in _text(CONVENTIONS)


def test_every_default_panel_names_registered_roles_within_the_cap():
    for subject, panel in _panel_table_rows().items():
        assert 1 <= len(panel) <= 3, (subject, panel)
        assert set(panel) <= set(ROLES), (subject, panel)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_agent_shape.py
```

Expected: FAIL. `test_expert_reviewer_lists_every_role` (four roles missing, "nine" present), `test_panel_defaults_seat_the_new_roles` (three rows missing, Admin UI row differs) and `test_etoro_default_panel_makes_execution_specialist_mandatory` fail; `test_every_default_panel_names_registered_roles_within_the_cap` passes already (the six existing rows are valid); `test_expert_reviewer_is_read_only_and_knows_every_role` fails on the four new names.

- [ ] **Step 3: Update `expert-reviewer.md` in its three places**

In `$WT/.claude/agents/expert-reviewer.md`:

1. In the `description:` line, replace `the nine roles are listed in docs/claude/skills-tools.md under Expert roles` with `the thirteen roles are listed in docs/claude/skills-tools.md under Expert roles`.
2. Replace the role list under `## Roles`:

```markdown
`quant-researcher`, `staff-engineer`, `veteran-trader`, `risk-manager`,
`financial-advisor`, `technical-analyst`, `fundamental-analyst`,
`quant-engineer`, `senior-engineer`.
```

with:

```markdown
`quant-researcher`, `staff-engineer`, `veteran-trader`, `risk-manager`,
`financial-advisor`, `technical-analyst`, `fundamental-analyst`,
`quant-engineer`, `senior-engineer`, `execution-specialist`,
`compliance-reviewer`, `ux-designer`, `sre`.
```

3. In `## Return shape`, replace `UNKNOWN ROLE: <given> -- valid: <the nine roles>` with `UNKNOWN ROLE: <given> -- valid: <the thirteen roles>`.

- [ ] **Step 4: Update the role list in `persona.md`**

In `$WT/docs/claude/persona.md` § One seat at a time, replace:

```markdown
reasoned critique, nine role skills hold it — `quant-researcher`,
`staff-engineer`, `veteran-trader`, `risk-manager`, `financial-advisor`,
`technical-analyst`, `fundamental-analyst`, `quant-engineer`,
`senior-engineer` — applied by the `expert-reviewer` agent and run as a panel
```

with:

```markdown
reasoned critique, thirteen role skills hold it — `quant-researcher`,
`staff-engineer`, `veteran-trader`, `risk-manager`, `financial-advisor`,
`technical-analyst`, `fundamental-analyst`, `quant-engineer`,
`senior-engineer`, `execution-specialist`, `compliance-reviewer`,
`ux-designer`, `sre` — applied by the `expert-reviewer` agent and run as a panel
```

- [ ] **Step 5: Panel defaults in `document-conventions.md`**

In `$WT/docs/claude/document-conventions.md`, replace the last row of the panel table:

```markdown
| Admin UI | staff-engineer, financial-advisor |
```

with these four rows (the 1-to-3 roles cap is unchanged):

```markdown
| Admin UI | ux-designer, staff-engineer, financial-advisor |
| eToro integration, anything that places an order | execution-specialist, risk-manager, financial-advisor (**`execution-specialist` is mandatory**; `financial-advisor` covers the cost and tax of demo-to-real) |
| Published content (bomeo-capital.com, public channels) | compliance-reviewer, financial-advisor |
| Production ops, soaks, providers | sre, staff-engineer |
```

- [ ] **Step 6: Roles count in `skills-tools.md`**

In `$WT/docs/claude/skills-tools.md` § Expert roles (v145), replace the opening words:

```markdown
Nine role skills each hold one reviewer's lens, in four sections -- Lens,
```

with:

```markdown
Thirteen role skills (nine from v145, four from v159) each hold one reviewer's lens, in four sections -- Lens,
```

Leave the dated eval baseline ("54/54 cases pass across the nine role suites") as it is: it records a 2026-10-09 run, not the current roster.

- [ ] **Step 7: Condensed mirror in `AGENTS.md`**

In `$WT/AGENTS.md`, in the `**Panel:**` paragraph, replace:

```markdown
`document-conventions.md`), run through `panel` after the spec is committed
```

with:

```markdown
`document-conventions.md`; an eToro or order-placing spec always seats
`execution-specialist`), run through `panel` after the spec is committed
```

- [ ] **Step 8: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
grep -n "nine" "$WT/.claude/skills/panel/SKILL.md" "$WT/.claude/agents/expert-reviewer.md"
```

Expected: `Codex mirror is current.`; status shows only this task's files plus `.codex/agents/expert-reviewer.toml`; the `grep` prints nothing.

- [ ] **Step 9: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_agent_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_spec_panel_header.py
```

Expected: all four files `0 failed`.

- [ ] **Step 10: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/agents/expert-reviewer.md tests/hooks/test_agent_shape.py tests/hooks/test_role_skills.py docs/claude/persona.md docs/claude/document-conventions.md docs/claude/skills-tools.md AGENTS.md .codex/agents/expert-reviewer.toml
git -C "$WT" commit -m "feat(v159): expert-reviewer knows thirteen roles; panel defaults for the new seats

expert-reviewer.md names all thirteen roles in its description, role list
and return shape, so /panel no longer returns UNKNOWN ROLE for the v159
seats. document-conventions.md gains default panels for eToro/orders
(execution-specialist mandatory), published content and production ops,
and the Admin UI row now leads with ux-designer. persona.md and the
skills-tools.md roles prose count thirteen.

The spec's 'and so does any count the panel skill quotes' is a no-op:
panel/SKILL.md quotes no role count (grep -n nine is empty), so it is
unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER4: `Places-orders: yes` requires `execution-specialist`

**Model:** sonnet — one small pure function with unit tests and a repo gate in an existing test module, plus doc edits with a hard line budget on `new-doc/SKILL.md`.

**Files:**
- Modify: `tests/hooks/test_spec_panel_header.py`
- Modify: `.claude/skills/new-doc/SKILL.md`
- Modify: `docs/claude/document-conventions.md`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.agents/skills/new-doc/SKILL.md`

**Interfaces:**
- Consumes: `panel_roles(line: str) -> list`, `checked_specs()`, `spec_number(path)`, `PANEL`, `SCREEN`, `ROOT`, `SKILLS_DIR` (all already in `tests/hooks/test_spec_panel_header.py`); ER1's `execution-specialist` row in `docs/claude/skills-tools.md`; ER3's panel table in `docs/claude/document-conventions.md`.
- Produces (in `tests/hooks/test_spec_panel_header.py`): `PLACES_ORDERS = "**Places-orders:**"`, `FIRST_ORDER_CHECKED = 160`, `ORDER_ROLE = "execution-specialist"`, `places_orders_problems(text: str) -> list[str]` (empty list = fine; otherwise one message `"**Places-orders:** yes needs `execution-specialist` on the **Panel:** line"`).

**The rule.** A spec numbered v160 or above whose **header block** (every line before the first `## ` heading) carries a line starting `**Places-orders:**` whose first word, backticks and trailing punctuation stripped and lower-cased, is `yes`, must name `execution-specialist` on its `**Panel:**` line. `no`, any other value, an absent line, or a `Places-orders` line in the body are not checked: the trigger is a header, never a body mention (spec § A). Split specs carry headers in `_0-index`, which `checked_specs()` already handles.

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/hooks/test_spec_panel_header.py`, append to the module docstring, before its closing `"""`:

```python
v159: from v160, a spec whose header says **Places-orders:** yes must also
seat execution-specialist on its Panel line (places_orders_problems).
```

Add the constants after `SCREEN = "**Screen:**"`:

```python
PLACES_ORDERS = "**Places-orders:**"
FIRST_ORDER_CHECKED = 160
ORDER_ROLE = "execution-specialist"
NEW_DOC_SKILL = SKILLS_DIR / "new-doc" / "SKILL.md"
CONVENTIONS = ROOT / "docs/claude/document-conventions.md"
SKILLS_TOOLS = ROOT / "docs/claude/skills-tools.md"
```

Append these unit tests after `test_exempt_and_non_index_specs_are_skipped` (before the `# -- the repository gate` banner):

```python
def _order_spec(places, panel="risk-manager", *, in_body=False):
    lines = ["# v999 demo", "", "**Bump:** none", "**Edge:** none (integrity)",
             f"{SCREEN} exempt (integrity)", f"{PANEL} {panel}"]
    if places is not None and not in_body:
        lines.append(f"{PLACES_ORDERS} {places}")
    lines += ["", "## Why", "text"]
    if places is not None and in_body:
        lines.append(f"{PLACES_ORDERS} {places}")
    return "\n".join(lines) + "\n"


def test_places_orders_yes_without_execution_specialist_fails():
    assert places_orders_problems(_order_spec("yes")) == [
        "**Places-orders:** yes needs `execution-specialist` on the **Panel:** line"]


def test_places_orders_yes_with_execution_specialist_passes():
    assert places_orders_problems(
        _order_spec("yes", "execution-specialist, risk-manager")) == []
    assert places_orders_problems(
        _order_spec("`yes` (demo orders)", "`execution-specialist`")) == []


def test_places_orders_no_or_absent_is_not_checked():
    assert places_orders_problems(_order_spec("no")) == []
    assert places_orders_problems(_order_spec(None)) == []


def test_case_and_punctuation_do_not_hide_a_yes():
    assert places_orders_problems(_order_spec("Yes.")) != []


def test_a_places_orders_line_in_the_body_is_not_a_header():
    assert places_orders_problems(_order_spec("yes", in_body=True)) == []


def test_places_orders_reads_crlf_like_lf():
    assert places_orders_problems(_order_spec("yes").replace("\n", "\r\n")) != []
    crlf = _order_spec("yes", "execution-specialist").replace("\n", "\r\n")
    assert places_orders_problems(crlf) == []


def test_a_yes_with_no_panel_line_fails():
    text = "# v999\n\n**Edge:** none (integrity)\n**Places-orders:** yes\n\n## Why\n"
    assert places_orders_problems(text) != []
```

Append at the end of the file (after `test_every_spec_above_v145_carries_a_valid_panel_line`):

```python
def test_every_order_placing_spec_above_v159_seats_execution_specialist():
    problems = {p.relative_to(ROOT).as_posix():
                places_orders_problems(p.read_text(encoding="utf-8"))
                for p in checked_specs()
                if (spec_number(p) or 0) >= FIRST_ORDER_CHECKED}
    assert {path: found for path, found in problems.items() if found} == {}


def test_new_doc_asks_for_the_places_orders_line():
    text = NEW_DOC_SKILL.read_text(encoding="utf-8")
    assert PLACES_ORDERS in text and ORDER_ROLE in text


def test_document_conventions_define_the_places_orders_line():
    text = CONVENTIONS.read_text(encoding="utf-8")
    assert PLACES_ORDERS in text and f"v{FIRST_ORDER_CHECKED}" in text


def test_the_places_orders_check_has_an_owner():
    row = next(line for line in SKILLS_TOOLS.read_text(encoding="utf-8").splitlines()
               if line.startswith(f"| `{ORDER_ROLE}` |"))
    assert "Places-orders" in row and "test_spec_panel_header.py" in row
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_spec_panel_header.py
```

Expected: FAIL. The seven unit tests and the repo gate fail with `NameError: name 'places_orders_problems' is not defined`; the three doc tests fail on their assertions. The pre-existing tests still pass.

- [ ] **Step 3: Implement `places_orders_problems`**

In `$WT/tests/hooks/test_spec_panel_header.py`, add after `panel_problems` (before the `# -- unit tests` banner):

```python
def _header_block(lines: list) -> list:
    """Every line before the first `## ` heading: where header lines live."""
    end = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    return lines[:end]


def _says_yes(marker: str) -> bool:
    words = marker[len(PLACES_ORDERS):].replace("`", " ").lower().split()
    return bool(words) and words[0].strip(".,;:()") == "yes"


def places_orders_problems(text: str) -> list[str]:
    """v159: a header `**Places-orders:** yes` must seat execution-specialist.

    The trigger is the header line, never a body mention of eToro. Specs
    below FIRST_ORDER_CHECKED are filtered out by the repo gate, not here.
    """
    header = _header_block(text.replace("\r\n", "\n").split("\n"))
    marker = next((line for line in header if line.startswith(PLACES_ORDERS)), None)
    if marker is None or not _says_yes(marker):
        return []
    panel = next((line for line in header if line.startswith(PANEL)), None)
    if panel is not None and ORDER_ROLE in panel_roles(panel):
        return []
    return [f"{PLACES_ORDERS} yes needs `{ORDER_ROLE}` on the {PANEL} line"]
```

- [ ] **Step 4: Run the unit tests and the repo gate**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_spec_panel_header.py
```

Expected: only the three doc tests still fail. If `test_every_order_placing_spec_above_v159_seats_execution_specialist` fails, a spec (most likely `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md`, owned by another session) already says `Places-orders: yes` without the seat: stop and return `BLOCKED: v160 spec carries Places-orders: yes without execution-specialist -- amend its Panel line or hold ER4?`. Never edit the v160 spec from this task.

- [ ] **Step 5: Define the line in `document-conventions.md`**

In `$WT/docs/claude/document-conventions.md`, directly after the panel table's last row (`| Production ops, soaks, providers | sre, staff-engineer |`, written by ER3) and its blank line, insert this paragraph before `The panel runs through the `panel` skill at two fixed points.`:

```markdown
**`Places-orders:`** — specs only, from **v160**. A spec that touches eToro
carries `**Places-orders:** yes` or `**Places-orders:** no` in its header block
(conventionally right below `Panel:`); `/new-doc` asks for it. `yes` means the
spec's work places, sizes, routes or reconciles an order, and its `Panel:` must
then name `execution-specialist`. The trigger is the header, never a body
mention, so a spec that names eToro in passing is not forced to seat the role.
`tests/hooks/test_spec_panel_header.py` (`places_orders_problems`) fails a
`yes` spec above v159 whose panel lacks the role. Owner: the
`execution-specialist` row in `skills-tools.md` § Expert roles; the check
retires only if order placement leaves the roadmap.

```

- [ ] **Step 6: Owner note on the `execution-specialist` row**

In `$WT/docs/claude/skills-tools.md`, in the row ER1 wrote, replace the row's ending:

```markdown
CFD vs real share, demo-only enforcement (`assert_demo`) |
```

with:

```markdown
CFD vs real share, demo-only enforcement (`assert_demo`). Owns the `Places-orders:` check (`places_orders_problems` in `test_spec_panel_header.py`); it retires only if order placement leaves the roadmap |
```

The row must still begin `` | `execution-specialist` | opus | `` (`test_reviewer_model_is_recorded_in_the_roles_table`).

- [ ] **Step 7: `/new-doc` asks for the line, inside the 80-line budget**

`$WT/.claude/skills/new-doc/SKILL.md` is 79 lines and `MAX_SKILL_LINES` is 80, so this edit adds exactly one line. In Step 3, replace this 7-line paragraph:

```markdown
A spec numbered above v140 also carries `**Screen:**` under `Edge:` -- a
`SCREEN-PASS` ledger id, a `harvest-headroom` results path, or `exempt
(integrity)`. From v146 a spec carries `**Panel:**` directly below
`Screen:`: one to three role skills, defaulting by `Edge:` from the table in
`document-conventions.md`, overridable by the author. From v146 a plan's
first line under every `### Task` is `**Model:**`, per
`docs/claude/model-routing.md`. Which value, and why: `document-conventions.md`.
```

with this 8-line paragraph:

```markdown
A spec numbered above v140 also carries `**Screen:**` under `Edge:` -- a
`SCREEN-PASS` ledger id, a `harvest-headroom` results path, or `exempt
(integrity)`. From v146 a spec carries `**Panel:**` directly below
`Screen:`: one to three role skills, defaulting by `Edge:` from the table in
`document-conventions.md`, overridable by the author. On any spec touching
eToro ask for `**Places-orders:** yes|no`; from v160, `yes` needs
`execution-specialist` on the Panel. From v146 a plan's first line under every
`### Task` is `**Model:**`, per `docs/claude/model-routing.md`. Which value, and why: `document-conventions.md`.
```

- [ ] **Step 8: Condensed mirror in `AGENTS.md`**

In `$WT/AGENTS.md`, replace:

```markdown
`BLOCKING` finding stops the close. `tests/hooks/test_spec_panel_header.py`
enforces it.
```

with:

```markdown
`BLOCKING` finding stops the close. `tests/hooks/test_spec_panel_header.py`
enforces it. From v160 a spec touching eToro also carries
`**Places-orders:** yes|no` in its header; `yes` requires `execution-specialist`
on the panel (same test).
```

- [ ] **Step 9: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
wc -l "$WT/.claude/skills/new-doc/SKILL.md"
```

Expected: `Codex mirror is current.`; status shows only this task's files plus `.agents/skills/new-doc/SKILL.md`; `new-doc/SKILL.md` is 80 lines.

- [ ] **Step 10: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_spec_panel_header.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python -m radon cc -s -n C "$WT/tests/hooks/test_spec_panel_header.py"
```

Expected: all four files `0 failed`; `radon` prints nothing (every function below C).

- [ ] **Step 11: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add tests/hooks/test_spec_panel_header.py .claude/skills/new-doc/SKILL.md docs/claude/document-conventions.md docs/claude/skills-tools.md AGENTS.md .agents/skills/new-doc/SKILL.md
git -C "$WT" commit -m "feat(v159): Places-orders: yes requires execution-specialist on the panel

places_orders_problems in test_spec_panel_header.py fails a spec numbered
v160 or above whose header says Places-orders: yes without seating
execution-specialist. The trigger is the header line, never a body
mention. /new-doc asks for the line on any spec touching eToro;
document-conventions.md defines it, and the execution-specialist row in
skills-tools.md owns the check.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

