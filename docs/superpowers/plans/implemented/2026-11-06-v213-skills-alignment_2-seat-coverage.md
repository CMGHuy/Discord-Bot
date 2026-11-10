# v213 — Skills alignment, part 2: seat coverage

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v213 — Skills alignment](../specs/2026-11-06-v213-skills-alignment.md) (§ C. Seat coverage)
**Index:** [`2026-11-06-v213-skills-alignment_0-index.md`](2026-11-06-v213-skills-alignment_0-index.md) — Goal, Architecture, **Global Constraints**, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

**Tasks:** V213-7..V213-11. They run in order (each adds rows to `CROSS_CUTTING` in `tests/hooks/test_role_skills.py`, which V213-7 creates), after V213-6 (the repo-wide citation case is live, so every task here also runs `tests/hooks/test_skill_citations.py`).

**Where to run.** Every path and command below is relative to the worktree root
`.claude/worktrees/2026-11-06-v213-skills-alignment` (created in V213-1); the
implementer's session root is that worktree. Never `cd` inside a Bash command.

**Editing skills in this part.**

- The skill files use CRLF line endings on disk; edit with the Edit tool, matching the old text below by its words, and keep the file's endings. The tests read through `_text()` (CRLF normalised), so endings never decide a verdict.
- The "Old" texts below are the files as V213-5 and V213-6 left them. If an old text does not match, `git grep -n` the first words of the item and stop with `BLOCKED:` if it is gone; never rewrite a neighbouring item to make room.
- Each edited seat ends at **at most 15** `- ` items under `## Checklist` (`test_checklist_has_eight_to_fifteen_items`) and at most 80 lines (`test_skill_shape.py`). Every count is stated in the task; re-count before the commit.
- New prose obeys the lint (index § Global Constraints, "New prose passes the lint"): every backticked path below was verified with `git ls-files` on `a338eeb3`; every `§` cite starts with a heading the doc has. Do not add a path, an UPPER_SNAKE name or a `§` cite the task does not list.
- No bare thresholds (`_THRESHOLD_RE` in `tests/hooks/test_skill_shape.py`): no `> 3`, `= 15`, `0R`, `2pp`. Write counts as words.
- Evals are written, never run (billed). `.agents/skills/<role>/SKILL.md` is the only generated copy `python scripts/dev/sync_codex.py` writes for a skill; eval folders are not mirrored. No checklist change here touches the role list `AGENTS.md` mirrors, so `AGENTS.md` stays as it is.

**Part-local test contract (this part only; part 3 does not consume it).** V213-8 adds
`COVERAGE: dict[str, tuple[str, ...]]` (role to the substrings its new checklist
items must carry) and `test_seat_names_its_coverage_items` to
`tests/hooks/test_role_skills.py`; V213-9..V213-11 add rows. It pins that each
addition landed, by anchor words and paths, never by whole sentences.

# Phase C — Seat coverage

### Task V213-7: Canonical boundary paragraph in all nine seats; shared-lead tests; `/panel` merge-by-lead line

**Model:** haiku — one paragraph move, a test block given verbatim and a three-line skill edit; no judgement calls.

**Files:**
- Modify: `tests/hooks/test_role_skills.py` (constants after `MAX_ROLE_DESCRIPTION`; helpers after `_section`; three tests at the end; two `PANEL_PHRASES` entries)
- Modify: `.claude/skills/financial-advisor/SKILL.md` (paragraph order only)
- Modify: `.claude/skills/panel/SKILL.md` (`## Step 4 — Merge`)
- Verify only (no edit expected): `.claude/skills/{risk-manager,veteran-trader,quant-researcher,quant-engineer,staff-engineer,senior-engineer,technical-analyst,fundamental-analyst}/SKILL.md`
- Generated: `.agents/skills/financial-advisor/SKILL.md`, `.agents/skills/panel/SKILL.md` (by `python scripts/dev/sync_codex.py`)

**Interfaces:**
- Consumes: `ROLES`, `_text`, `_body`, `_section` in `tests/hooks/test_role_skills.py` (exist, :24-61).
- Produces (V213-8..V213-12 rely on these exact names):
  - `BOUNDARY: str` — the canonical paragraph from index § Global Constraints, its six lines joined with single spaces.
  - `_boundary(role: str) -> str` — the first paragraph after the `# ` title line of `.claude/skills/<role>/SKILL.md`, stripped lines joined with single spaces.
  - `_checklist(role: str) -> list[str]` — the `- ` lines under `## Checklist`.
  - `LEADS: dict[str, str] = {"Shorts:": "Shorts: long plans stay byte-identical; ", "eToro:": "eToro: demo only, never `account: real`; "}`
  - `CROSS_CUTTING: dict[str, frozenset[str]] = {}` — role to the `LEADS` keys its checklist must carry; V213-8..V213-11 add rows.
  - Tests `test_boundary_paragraph_is_canonical` (parametrized over `ROLES`), `test_cross_cutting_items_use_the_shared_lead` (parametrized over `ROLES`), `test_cross_cutting_seats_carry_their_leads` (one test looping over `CROSS_CUTTING`).

**Why the edit is small.** On `a338eeb3` eight seats already carry the canonical paragraph byte for byte, directly under the title (lines 8-13 hash identically in all eight). `financial-advisor` carries it too, but as its *second* paragraph, under the "educational, not personalised financial advice" paragraph, so `_boundary("financial-advisor")` reads the wrong one. The new test fails there and nowhere else; the fix swaps the two paragraphs. `test_financial_advisor_is_educational_not_personal_advice` keeps passing because the educational sentence stays in the body.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_role_skills.py`, directly after the line `MAX_ROLE_DESCRIPTION = 260`, insert:

```python

# v213 § C: the boundary paragraph every seat opens with, pinned whole. It
# stays inside each skill because a role skill also loads on its own, without
# expert-reviewer. Wrapped in the files exactly as these six lines.
BOUNDARY = " ".join((
    "You are one seat on a review panel. You raise findings; you never decide, and",
    "you never lower a gate (`docs/claude/persona.md`). No seat's intuition",
    "overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed",
    "pre-registration, and you quote no pooled figure you did not re-derive. Every",
    "finding cites `file:line`, a git range or a doc section, and is tagged",
    "`BLOCKING` (it matches a red flag below) or `ADVISORY`.",
))

# v213 § C: a cross-cutting checklist item opens with one shared lead, then
# the seat's own angle, so /panel can merge the same concern across seats.
LEADS = {
    "Shorts:": "Shorts: long plans stay byte-identical; ",
    "eToro:": "eToro: demo only, never `account: real`; ",
}
# role -> the LEADS keys its checklist must carry (one item each).
CROSS_CUTTING: dict[str, frozenset[str]] = {}
```

Directly after the `_section` function (before `def lens_skills`), insert:

```python
def _boundary(role):
    """The first paragraph after the `# ` title line, lines joined by spaces."""
    lines = _body(role).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("# ")) + 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    paragraph = []
    for line in lines[start:]:
        if not line.strip():
            break
        paragraph.append(line.strip())
    return " ".join(paragraph)


def _checklist(role):
    return [line for line in _section(_body(role), "## Checklist").splitlines()
            if line.startswith("- ")]


def _lead_problems(item):
    """Why a checklist item that opens with a lead word misuses the lead."""
    for key, lead in LEADS.items():
        if not item.startswith("- " + key.rstrip(":")):
            continue
        if not item.startswith("- " + lead):
            return [f"lead not exact: {item[:60]!r}"]
        angle = item[len("- " + lead):]
        if not angle.strip() or not item.endswith("."):
            return [f"no angle or no full stop: {item[:60]!r}"]
    return []
```

At the end of the file, append:

```python


@pytest.mark.parametrize("role", sorted(ROLES))
def test_boundary_paragraph_is_canonical(role):
    assert _boundary(role) == BOUNDARY


@pytest.mark.parametrize("role", sorted(ROLES))
def test_cross_cutting_items_use_the_shared_lead(role):
    assert [p for item in _checklist(role) for p in _lead_problems(item)] == []


def test_cross_cutting_seats_carry_their_leads():
    assert set(CROSS_CUTTING) <= set(ROLES)
    wrong = {}
    for role, keys in sorted(CROSS_CUTTING.items()):
        assert keys <= set(LEADS), (role, keys)
        for key in sorted(keys):
            hits = [i for i in _checklist(role) if i.startswith("- " + LEADS[key])]
            if len(hits) != 1:
                wrong[f"{role} {key}"] = len(hits)
    assert wrong == {}, "each listed seat carries each lead exactly once"
```

Replace the `PANEL_PHRASES` assignment with:

```python
PANEL_PHRASES = ("expert-reviewer", "serially", "skills-tools.md", "BLOCKING",
                 "## Panel review", "applied", "rejected: <why>", "/close-out",
                 "Model tiers", "`Shorts:`", "`eToro:`")
```

The existing `test_checklist_has_eight_to_fifteen_items` keeps its own inline list; leave it as it is.

- [ ] **Step 2: Run the tests to verify they fail for the right reason**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: FAIL, exactly two tests: `test_boundary_paragraph_is_canonical[financial-advisor]` (it reads the "Your output is educational, …" paragraph) and `test_panel_dispatches_the_expert_reviewer_serially` (missing `` `Shorts:` `` and `` `eToro:` ``). Every other boundary case passes. If another seat fails the boundary case, diff its paragraph against `BOUNDARY` and set that skill's text to the canonical wording in this task (a stray word or a different wrap); name it in the commit body.

- [ ] **Step 3: `financial-advisor` — the boundary paragraph first**

In `.claude/skills/financial-advisor/SKILL.md`, the block under `# Financial advisor` (today lines 8-17) becomes, with one blank line between the two paragraphs and one after:

```markdown
You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

Your output is educational, not personalised financial advice. You review
whether the bot's output suits a real-money retail swing trader; you never
review the partner's personal finances, taxes or accounts.
```

Nothing else in the file changes; its line count stays the same.

- [ ] **Step 4: `/panel` — merge by shared lead**

In `.claude/skills/panel/SKILL.md`, `## Step 4 — Merge`, old:

```markdown
Drop every finding that cites no `file:line`, git range or doc section. Merge
duplicates across roles, keeping the stricter tag. List `BLOCKING` first, then
`ADVISORY`, each line naming its role. A role that returned `CLEAN` is listed
as clean, not omitted.
```

New:

```markdown
Drop every finding that cites no `file:line`, git range or doc section. Merge
duplicates across roles, keeping the stricter tag. Findings that open with the
same shared lead (`Shorts:`, `eToro:`) and cite the same evidence are
duplicates: one line naming every seat that raised them. List `BLOCKING`
first, then `ADVISORY`, each line naming its role. A role that returned
`CLEAN` is listed as clean, not omitted.
```

The skill grows by two lines and stays far under the 80-line budget.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
git status --porcelain
```

Expected: every `testrun.py` call prints `VERDICT: PASS`; `test_cross_cutting_seats_carry_their_leads` passes with `CROSS_CUTTING` empty (V213-8 gives it rows); `git status` lists `tests/hooks/test_role_skills.py`, `.claude/skills/financial-advisor/SKILL.md`, `.claude/skills/panel/SKILL.md` and their two `.agents/skills/` copies, plus any seat Step 2 forced you to fix and its copy.

- [ ] **Step 6: Commit**

```bash
git add tests/hooks/test_role_skills.py .claude/skills/financial-advisor/SKILL.md .claude/skills/panel/SKILL.md .agents/skills/financial-advisor/SKILL.md .agents/skills/panel/SKILL.md
git commit -m "test(v213): boundary paragraph pinned whole; shared leads; panel merges by lead

V213-7. test_role_skills pins the canonical boundary paragraph as the first
paragraph of every seat (financial-advisor now opens with it, its
educational paragraph second), checks that a Shorts:/eToro: item uses the
exact shared lead, and adds CROSS_CUTTING for the seats that must carry
one. /panel merges findings that open with the same lead.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Add any seat fixed under Step 2 (and its `.agents/skills/<role>/SKILL.md`) by its explicit path, and name it in the commit body.

### Task V213-8: `risk-manager` and `veteran-trader` coverage

**Model:** sonnet — two checklist rewrites under a hard item cap plus two eval folders and test rows; needs care, not design.

**Files:**
- Modify: `tests/hooks/test_role_skills.py` (`CROSS_CUTTING` rows; new `COVERAGE` dict and `test_seat_names_its_coverage_items`)
- Modify: `.claude/skills/risk-manager/SKILL.md` (`## Checklist`, `## Trigger table`)
- Modify: `.claude/skills/veteran-trader/SKILL.md` (`## Checklist`, `## Trigger table`)
- Create: `.claude/skills/risk-manager/evals/fire-short-gap-sizing/prompt.md`, `.claude/skills/risk-manager/evals/fire-short-gap-sizing/graders/skill-fired.md`
- Create: `.claude/skills/veteran-trader/evals/fire-short-borrow/prompt.md`, `.claude/skills/veteran-trader/evals/fire-short-borrow/graders/skill-fired.md`
- Generated: `.agents/skills/risk-manager/SKILL.md`, `.agents/skills/veteran-trader/SKILL.md`

**Interfaces:**
- Consumes (V213-7): `LEADS`, `CROSS_CUTTING`, `_checklist(role)`, `test_cross_cutting_items_use_the_shared_lead`, `test_cross_cutting_seats_carry_their_leads`.
- Produces (part-local, V213-9..V213-11 add rows): `COVERAGE: dict[str, tuple[str, ...]]` and `test_seat_names_its_coverage_items` (parametrized over `sorted(COVERAGE)`).

**Spec rows (§ C table).** risk-manager adds short gap-aware sizing and squeeze (v183), heat from the current stop, and an eToro item, making room by merging the two cap-binding items: 12 − 1 + 4 = **15**. veteran-trader adds short borrow and hard-to-borrow names, the Berlin-time session calendar, partial fills on limit-at-level entries and an eToro CFD-versus-stock item, making room by merging alert volume into alert timing: 12 − 1 + 4 = **15**. Paths below were checked with `git ls-files`: `swingbot/core/planning/gap_sizing.py` (v183 gap sizing), `swingbot/core/market/short_interest.py` (v183 squeeze-notice cache), `swingbot/core/edge/frictions.py` (v182 short borrow fee).

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_role_skills.py`, replace

```python
CROSS_CUTTING: dict[str, frozenset[str]] = {}
```

with

```python
CROSS_CUTTING: dict[str, frozenset[str]] = {
    "risk-manager": frozenset({"Shorts:", "eToro:"}),
    "veteran-trader": frozenset({"Shorts:", "eToro:"}),
}

# v213 § C: the anchors each seat's new checklist items must carry -- words
# and paths, never whole sentences, so a reword inside the item still passes.
COVERAGE: dict[str, tuple[str, ...]] = {
    "risk-manager": ("level-lifecycle", "current stop",
                     "`swingbot/core/planning/gap_sizing.py`",
                     "squeeze notice", "`swingbot/core/market/short_interest.py`",
                     "without its stop"),
    "veteran-trader": ("act on before the open", "half-days",
                       "frozen weekend bar", "partial fill", "hard-to-borrow",
                       "CFD"),
}
```

At the end of the file, append:

```python


@pytest.mark.parametrize("role", sorted(COVERAGE))
def test_seat_names_its_coverage_items(role):
    checklist = "\n".join(_checklist(role))
    assert [a for a in COVERAGE[role] if a not in checklist] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: FAIL in `test_cross_cutting_seats_carry_their_leads` (`risk-manager Shorts:`, `risk-manager eToro:`, `veteran-trader Shorts:`, `veteran-trader eToro:` each 0) and in `test_seat_names_its_coverage_items[risk-manager]` and `[veteran-trader]` (`"level-lifecycle"` and `"act on before the open"` are already there; every other anchor is missing). Nothing else fails.

- [ ] **Step 3: `risk-manager` checklist**

In `.claude/skills/risk-manager/SKILL.md`, replace everything between the `## Checklist` line and the `## Red flags` line (exclusive; one blank line after the heading and one before `## Red flags`, as today) with these fifteen items:

```markdown
- Dollar risk is sized from the entry-to-stop distance against the account, and the stop cap (`MAX_STOP_LOSS_PCT` in `swingbot/config.py`) binds live and in the backtest, structural and level-lifecycle stops included (`docs/claude/known-traps.md` § Stop floor and 2% cap; `known-traps.md` § The level-lifecycle stop breaches the 2% cap in the backtest).
- Portfolio heat including the new trade stays under `PORTFOLIO_HEAT_CAP_PCT`, computed by `swingbot/core/edge/heat.py`.
- Heat is computed from each open plan's current stop, never from the initial risk stored at entry.
- Clustered names count together against `CORRELATED_HEAT_CAP_PCT` (`swingbot/core/edge/correlation.py`).
- The sizing mode in `swingbot/core/edge/sizing.py` agrees with the suggested size the alert shows.
- Shorts: long plans stay byte-identical; a short is sized from its gap-aware floor (`swingbot/core/planning/gap_sizing.py`), so an overnight gap through the stop stays inside the dollar cap.
- A short alert on a heavily shorted name carries the squeeze notice, its short-interest facts read from `swingbot/core/market/short_interest.py`.
- Stop logic (`swingbot/core/edge/stops.py`, `swingbot/core/planning/stop_scope.py`) never widens a stop after entry.
- A change that raises per-trade risk or trade count states its drawdown and ruin effect (`swingbot/core/edge/ruin.py`, `swingbot/core/analytics/risk_metrics.py`).
- Throttles and limits (`swingbot/core/edge/throttle.py`, `swingbot/core/risk_limits.py`) apply on every path that issues an alert.
- A gap through the stop is counted in R as the loss it is, not as the planned loss.
- A rejected plan logs why (the "plan rejected (" lines), so a quiet day caused by the cap is diagnosable.
- An ExpR gain bought with wider stops is also shown in dollars at fixed risk.
- The admin risk view (`swingbot/admin/api_v1/risk.py`) shows the same heat the scanner enforces.
- eToro: demo only, never `account: real`; no order is sent without its stop attached.
```

The first item is the old first two merged (both `§` cites kept, each still a heading of `docs/claude/known-traps.md`); the other old items are unchanged words.

In `## Trigger table`, directly after the line `Should fire: asking whether three open trades in one sector are too much correlated exposure.`, insert:

```markdown
Should fire: asking whether gap-aware sizing on short alerts keeps an overnight gap through the stop inside the dollar-risk cap.
```

- [ ] **Step 4: `veteran-trader` checklist**

In `.claude/skills/veteran-trader/SKILL.md`, replace everything between `## Checklist` and `## Red flags` (same rule) with these fifteen items:

```markdown
- The partner places resting orders at alert time: entry, stop and targets can be entered as orders without re-deriving anything (`swingbot/core/scanning/alert_embeds.py`, `execution_embeds.py`).
- A gap through the entry or the stop is handled, and the simulated fill on a gap matches what an order gets (`swingbot/core/planning/exit_sim.py`).
- A limit-at-level entry states what a partial fill does to the stop and the targets.
- Slippage and commission come from `swingbot/core/edge/frictions.py`, are not zero, and apply to the same trades the claim rests on.
- Liquidity suits the size; futures skipped for dollar volume stay skipped by design (`docs/claude/known-traps.md` § Futures skipped for dollar volume is deliberate).
- Shorts: long plans stay byte-identical; a short on a hard-to-borrow name is flagged, and its borrow fee is priced in `swingbot/core/edge/frictions.py`.
- Alert timing fits the session, and alert volume is one a person can act on before the open (`known-traps.md` § The full state machine now runs across the whole Berlin-local active window; `swingbot/core/market/session.py`).
- Berlin-time alerts line up with the US session calendar: the open, half-days, holidays and the frozen weekend bar.
- The stop survives normal noise for its horizon (`swingbot/core/market/strategy_types.py:HORIZONS`) and does not land in the empty band of `known-traps.md` § Stop floor and 2% cap.
- Regime is considered: how the setup behaves in trend versus chop (`swingbot/core/edge/regime2.py`, `swingbot/core/scanning/regime.py`).
- Earnings, OPEX and macro dates inside the holding window are named (`swingbot/core/market/events.py`, `opex.py`); depth goes to `fundamental-analyst`.
- Expiry and time exits are stated, so no resting order works past the plan's validity (`swingbot/core/planning/time_exit.py`).
- A silent stop move, a missing expiry or a lost send on the alert channel is real-money divergence and is `Edge: harvest` (`docs/claude/edge-priorities.md`).
- eToro: demo only, never `account: real`; the plan says whether it assumes an eToro CFD fill or a stock fill, which differ in spread and overnight cost.
- A gap between the backtest and live paths is named, not assumed away (`known-traps.md` § The dead-cat-bounce veto is invisible to `run_backtest_range.py`).
```

The old "Alert volume is one a person can act on before the open." item is gone, folded into the timing item; every other old item keeps its words.

In `## Trigger table`, directly after `Should fire: asking whether a new setup is tradeable in thinly traded names.`, insert:

```markdown
Should fire: asking whether a short alert on a hard-to-borrow name can be borrowed and filled at its entry.
```

- [ ] **Step 5: The two eval folders**

`.claude/skills/risk-manager/evals/fire-short-gap-sizing/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Does the gap-aware sizing on short alerts keep an overnight gap through the stop inside the 2% dollar-risk cap, or can one gap blow through it?
```

`.claude/skills/risk-manager/evals/fire-short-gap-sizing/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: risk-manager
min: 1
---

The `risk-manager` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`.claude/skills/veteran-trader/evals/fire-short-borrow/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

This short alert is on a heavily shorted small cap. Can the short actually be borrowed and filled as a resting order at the alert's entry?
```

`.claude/skills/veteran-trader/evals/fire-short-borrow/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: veteran-trader
min: 1
---

The `veteran-trader` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
git add .claude/skills/risk-manager/evals/fire-short-gap-sizing .claude/skills/veteran-trader/evals/fire-short-borrow
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
git status --porcelain
```

The eval folders are staged first because the repo-wide citation case reads only tracked files. Expected: every `testrun.py` call prints `VERDICT: PASS` (in `test_role_skills.py`: both checklists at fifteen items, `test_role_ships_fire_and_no_fire_cases` green for both seats with seven cases each, the lead and coverage tests green); `git status` lists the two skills, their `.agents/skills/` copies, the four eval files and the test file. A citation finding means a path or cite was retyped: fix it to the text above, never an allowlist line.

- [ ] **Step 7: Commit**

```bash
git add tests/hooks/test_role_skills.py .claude/skills/risk-manager/SKILL.md .claude/skills/veteran-trader/SKILL.md .claude/skills/risk-manager/evals/fire-short-gap-sizing/prompt.md .claude/skills/risk-manager/evals/fire-short-gap-sizing/graders/skill-fired.md .claude/skills/veteran-trader/evals/fire-short-borrow/prompt.md .claude/skills/veteran-trader/evals/fire-short-borrow/graders/skill-fired.md .agents/skills/risk-manager/SKILL.md .agents/skills/veteran-trader/SKILL.md
git commit -m "docs(v213): risk-manager and veteran-trader cover shorts, eToro, the calendar

V213-8. risk-manager: the two cap-binding items merge; adds heat from the
current stop, gap-aware short sizing, the squeeze notice and an eToro
stop-attached item (15). veteran-trader: alert volume folds into timing;
adds partial fills, short borrow, the Berlin-time session calendar and an
eToro CFD-versus-stock item (15). One fire eval each; CROSS_CUTTING and
COVERAGE rows pin the additions.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V213-9: `quant-researcher` and `quant-engineer` coverage

**Model:** sonnet — targeted edits to two checklists already touched by V213-6, under a hard item cap; matching on old text needs care.

**Files:**
- Modify: `tests/hooks/test_role_skills.py` (`CROSS_CUTTING` row `quant-researcher`; `COVERAGE` rows `quant-researcher`, `quant-engineer`)
- Modify: `.claude/skills/quant-researcher/SKILL.md` (`## Checklist`, `## Trigger table`)
- Modify: `.claude/skills/quant-engineer/SKILL.md` (`## Checklist`, `## Trigger table`)
- Create: `.claude/skills/quant-researcher/evals/fire-total-r-beside-expr/prompt.md`, `.claude/skills/quant-researcher/evals/fire-total-r-beside-expr/graders/skill-fired.md`
- Create: `.claude/skills/quant-engineer/evals/fire-long-run-checkpoint/prompt.md`, `.claude/skills/quant-engineer/evals/fire-long-run-checkpoint/graders/skill-fired.md`
- Generated: `.agents/skills/quant-researcher/SKILL.md`, `.agents/skills/quant-engineer/SKILL.md`

**Interfaces:**
- Consumes: `LEADS`, `CROSS_CUTTING`, `_checklist` (V213-7); `COVERAGE`, `test_seat_names_its_coverage_items` (V213-8).
- Produces: nothing new; rows only.

**Spec rows (§ C table).** quant-researcher adds total R (ExpR × N) and trade count beside every ExpR, longs byte-identical on short work, and the live-book gap, making room by merging badge `run_date` into the pooled-numbers item and merging concentration with direction (the concentration item becomes the `Shorts:` item): 14 − 1 + 2 = **15**. quant-engineer adds checkpoint-and-resume for long runs, Alpaca/yfinance provider parity and the training-data store, folding flushed progress into the checkpoint item: 12 + 2 = **14**. New paths, checked with `git ls-files`: `swingbot/core/backtesting/validation_registry.json`, `swingbot/core/marketdata/providers/router.py` (Alpaca and yfinance behind one router, v106), `swingbot/core/marketdata/training_data.py`. New `§` cite: `docs/claude/working-conventions.md` § Long runs must checkpoint (heading `## Long runs must checkpoint (never hold results only in memory)`; the cite is a prefix, so it passes).

`quant-researcher` was edited by V213-6 (its `SCREEN-PASS`, closed-pre-registration and `week_cluster_bootstrap` items). Leave those three as V213-6 left them; the edits below touch other items only, matched by their old text.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_role_skills.py`, add to `CROSS_CUTTING` (after the `veteran-trader` row):

```python
    "quant-researcher": frozenset({"Shorts:"}),
```

and to `COVERAGE` (after the `veteran-trader` row):

```python
    "quant-researcher": ("badge tier", "`swingbot/core/backtesting/validation_registry.json`",
                         "Total R", "trade count", "live-book gap"),
    "quant-engineer": ("§ Long runs must checkpoint", "skips finished units on restart",
                       "`swingbot/core/marketdata/providers/router.py`",
                       "`swingbot/core/marketdata/training_data.py`"),
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: FAIL in `test_cross_cutting_seats_carry_their_leads` (`quant-researcher Shorts:` 0), `test_seat_names_its_coverage_items[quant-researcher]` (`badge tier`, the registry path, `Total R`, `trade count`, `live-book gap`) and `test_seat_names_its_coverage_items[quant-engineer]` (all four). Nothing else fails.

- [ ] **Step 3: `quant-researcher` checklist — five edits**

In `.claude/skills/quant-researcher/SKILL.md`, `## Checklist`:

(a) The first item, old:

```markdown
- Every ExpR, win rate or N in the target is re-derived per `pooled-numbers`, with window, N and source in the same sentence (`docs/claude/edge-priorities.md`).
```

new, followed directly by a new second item:

```markdown
- Every ExpR, win rate, N or badge tier in the target is re-derived per `pooled-numbers`, with window, N and source in the same sentence, and a tier read from `swingbot/core/backtesting/validation_registry.json` is checked against its `run_date` and the population it claims (`docs/claude/edge-priorities.md`).
- Total R (ExpR × N) and the trade count stand beside every ExpR, so a filter that removes most trades cannot pass on ExpR alone.
```

(b) Delete the item (its content is now in the first):

```markdown
- A badge tier read from `swingbot/core/backtesting/validation_registry.json` is checked against its `run_date` and the population it claims.
```

(c) The concentration item, old:

```markdown
- Concentration is reported: a lift carried by one direction or two horizons says so.
```

new, followed directly by a new item:

```markdown
- Shorts: long plans stay byte-identical; a lift carried by one direction or two horizons says so.
- A backtest claim names its live-book gap: how the closed live trades compare, or why no comparison exists yet.
```

(d) Every other item, the three V213-6 items included, keeps its words and its place. Count: fifteen `- ` lines under `## Checklist`.

(e) In `## Trigger table`, directly after `Should fire: reviewing a pre-registration's frozen thresholds before its TRAIN run.`, insert:

```markdown
Should fire: asking whether a filter that lifts ExpR but removes most of the trades is an improvement.
```

- [ ] **Step 4: `quant-engineer` checklist — three edits**

In `.claude/skills/quant-engineer/SKILL.md`, `## Checklist`:

(a) Directly after the item that starts `- A stale or truncated `, insert two items:

```markdown
- Bars from Alpaca and yfinance agree through the provider router (`swingbot/core/marketdata/providers/router.py`) before one result mixes the two.
- A feature or label written to the training-data store (`swingbot/core/marketdata/training_data.py`) is point-in-time and reproducible from its recorded run.
```

(b) The progress item, old:

```markdown
- Long runs print flushed progress and a percent figure (`docs/claude/working-conventions.md` § Long-running scripts must report progress).
```

new:

```markdown
- A long run prints flushed progress and a percent figure, persists each finished unit (ticker, fold, chunk) as it completes, and skips finished units on restart (`docs/claude/working-conventions.md` § Long runs must checkpoint).
```

Every other item keeps its words and its place. Count: fourteen.

(c) In `## Trigger table`, directly after `Should fire: asking whether a new results doc can be reproduced from its recorded command.`, insert:

```markdown
Should fire: reviewing a long backtest script that holds every result in memory until it finishes.
```

- [ ] **Step 5: The two eval folders**

`.claude/skills/quant-researcher/evals/fire-total-r-beside-expr/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

A new entry filter lifts TRAIN ExpR noticeably but cuts the trade count by two thirds. Is that a real improvement worth pre-registering?
```

`.claude/skills/quant-researcher/evals/fire-total-r-beside-expr/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: quant-researcher
min: 1
---

The `quant-researcher` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`.claude/skills/quant-engineer/evals/fire-long-run-checkpoint/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

This new grid script runs for about two hours and keeps every result in a list until the end, then writes one JSON file. Is that acceptable?
```

`.claude/skills/quant-engineer/evals/fire-long-run-checkpoint/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: quant-engineer
min: 1
---

The `quant-engineer` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
git add .claude/skills/quant-researcher/evals/fire-total-r-beside-expr .claude/skills/quant-engineer/evals/fire-long-run-checkpoint
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
git status --porcelain
```

`test_doc_sections.py` runs as a guard: it pins the `backtest-methodology.md` headings (`### Closed pre-registrations — do not re-run these`, the Stage −2 bullet) that `quant-researcher` cites. Expected: every call `VERDICT: PASS`; `quant-researcher` at fifteen items, `quant-engineer` at fourteen, seven eval cases each; `git status` lists the two skills, their `.agents/skills/` copies, the four eval files and the test file. A citation finding means a path or cite was retyped: fix it to the text above, never an allowlist line.

- [ ] **Step 7: Commit**

```bash
git add tests/hooks/test_role_skills.py .claude/skills/quant-researcher/SKILL.md .claude/skills/quant-engineer/SKILL.md .claude/skills/quant-researcher/evals/fire-total-r-beside-expr/prompt.md .claude/skills/quant-researcher/evals/fire-total-r-beside-expr/graders/skill-fired.md .claude/skills/quant-engineer/evals/fire-long-run-checkpoint/prompt.md .claude/skills/quant-engineer/evals/fire-long-run-checkpoint/graders/skill-fired.md .agents/skills/quant-researcher/SKILL.md .agents/skills/quant-engineer/SKILL.md
git commit -m "docs(v213): quant seats ask for total R, the live-book gap and checkpoints

V213-9. quant-researcher: badge run_date folds into the pooled-numbers
item, concentration becomes the Shorts: item; adds total R and trade count
beside every ExpR and the live-book gap (15). quant-engineer: progress
folds into checkpoint-and-resume; adds Alpaca/yfinance provider parity and
the training-data store (14). One fire eval each.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V213-10: `staff-engineer` and `senior-engineer` coverage

**Model:** sonnet — two checklists already touched by V213-5 gain items under a hard cap (one at exactly fifteen); edits are matched by old text.

**Files:**
- Modify: `tests/hooks/test_role_skills.py` (`CROSS_CUTTING` row `staff-engineer`; `COVERAGE` rows `staff-engineer`, `senior-engineer`)
- Modify: `.claude/skills/staff-engineer/SKILL.md` (`## Checklist`, `## Trigger table`)
- Modify: `.claude/skills/senior-engineer/SKILL.md` (`## Checklist`, `## Trigger table`)
- Create: `.claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/prompt.md`, `.claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/graders/skill-fired.md`
- Create: `.claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/prompt.md`, `.claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/graders/skill-fired.md`
- Generated: `.agents/skills/staff-engineer/SKILL.md`, `.agents/skills/senior-engineer/SKILL.md`

**Interfaces:**
- Consumes: `LEADS`, `CROSS_CUTTING`, `_checklist` (V213-7); `COVERAGE`, `test_seat_names_its_coverage_items` (V213-8).
- Produces: nothing new; rows only.

**Spec rows (§ C table).** staff-engineer adds admin worker load (v206), one CI job per `suites.toml` suite, PITR and backups, and an eToro idempotent-send item; it drops the `Bump:` item (`/close-out` owns it) and folds far-off scheduled work into the long-run-cost item: 13 − 2 + 4 = **15**. senior-engineer adds a new test joining its suite, frontend changes shipping Vitest specs and the mutation check, and drops "symbols exist" (`task-brief` owns it): 12 − 1 + 3 = **14**. New paths, checked with `git ls-files`: `deploy/gunicorn.conf.py` (the admin container's worker settings), `tests/suites.toml`, `scripts/ops/pitr_backup.sh`, `scripts/ops/backup_db.sh`. New `§` cite: `docs/claude/testing-cost.md` § Test suites (heading `## Test suites: group, run partially, one CI job each`; the cite is a prefix). The frontend runs Vitest (`frontend/package.json` devDependency `vitest`) through `ng test`.

V213-5 rewrote three items in `senior-engineer` (complexity, wiring, embed fields) and one in `staff-engineer` (three containers). Leave them as V213-5 left them.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_role_skills.py`, add to `CROSS_CUTTING` (after the `quant-researcher` row):

```python
    "staff-engineer": frozenset({"eToro:"}),
```

and to `COVERAGE` (after the `quant-engineer` row):

```python
    "staff-engineer": ("`deploy/gunicorn.conf.py`", "`tests/suites.toml`",
                       "`scripts/ops/pitr_backup.sh`", "§ Scheduling far-off work",
                       "idempotent"),
    "senior-engineer": ("`tests/suites.toml`", "Vitest", "Mutating the fix"),
```

Directly after `test_seat_names_its_coverage_items`, append:

```python


def test_dropped_items_stay_with_their_owners():
    """v213 § C: these checks moved to the skill that owns them."""
    assert "`Bump:`" not in "\n".join(_checklist("staff-engineer"))      # /close-out
    assert "Every symbol the brief names" not in "\n".join(_checklist("senior-engineer"))  # task-brief
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: FAIL in `test_cross_cutting_seats_carry_their_leads` (`staff-engineer eToro:` 0), `test_seat_names_its_coverage_items[staff-engineer]` (every anchor but `§ Scheduling far-off work`), `test_seat_names_its_coverage_items[senior-engineer]` (all three) and `test_dropped_items_stay_with_their_owners`. Nothing else fails.

- [ ] **Step 3: `staff-engineer` checklist — seven edits**

In `.claude/skills/staff-engineer/SKILL.md`, `## Checklist`:

(a) Directly after the item that starts `- A store write that can fail at alert issuance`, insert:

```markdown
- A change to the database, its volume or its crons keeps point-in-time recovery and the backups working (`scripts/ops/pitr_backup.sh`, `scripts/ops/backup_db.sh`).
```

(b) Directly after the three-containers item (it starts `- The three containers off the one image`, as V213-5 wrote it), insert:

```markdown
- An admin endpoint that is added or slowed down is weighed against the worker budget in `deploy/gunicorn.conf.py`, so one polling screen cannot starve every other request (v206).
```

(c) Delete:

```markdown
- Far-off scheduled work runs as a cron on the VM, never on the laptop (`working-conventions.md` § Scheduling far-off work).
```

(d) Directly after the item that starts `` - A new data file that tests read has a `DATA_READERS` row ``, insert:

```markdown
- CI runs one job per suite in `tests/suites.toml`; a suite past its cap is split by feature, never the cap raised (`docs/claude/testing-cost.md` § Test suites).
```

(e) Delete:

```markdown
- The `Bump:` level matches the observable difference (`working-conventions.md` § The three levels).
```

(f) The long-run-cost item, old:

```markdown
- Long-run cost is stated: a new cache, cron, table or flag names its owner and when it can be removed.
```

new, followed directly by the eToro item:

```markdown
- Long-run cost is stated: a new cache, cron, table or flag names its owner and when it can be removed, and far-off scheduled work runs as a cron on the VM, never on the laptop (`working-conventions.md` § Scheduling far-off work).
- eToro: demo only, never `account: real`; an order send is idempotent, so a retried scan never places a second order.
```

Every other item keeps its words and its place. Count: fifteen — exactly the cap; re-count before Step 6.

(g) In `## Trigger table`, directly after `Should fire: reviewing the rollback story of a deploy plan.`, insert:

```markdown
Should fire: reviewing how a plan that sends trade plans to the eToro demo account handles a retried send.
```

- [ ] **Step 4: `senior-engineer` checklist — four edits**

In `.claude/skills/senior-engineer/SKILL.md`, `## Checklist`:

(a) Directly after `- Tests came first and failed for the right reason; each asserts behaviour, not implementation.`, insert:

```markdown
- Mutating the fix (reverting the changed line or flipping its condition) makes its test fail; a test that still passes proves nothing.
```

(b) Directly after the item that starts `` - The narrow run (`python scripts/dev/testrun.py file <test>`) ``, insert:

```markdown
- A new test file sits in a `tests/` directory that belongs to exactly one suite in `tests/suites.toml`; a new directory joins one in the same commit.
- A change under `frontend/` ships its own Vitest specs, run with `npx ng test --watch=false --include <spec>` from `frontend/`.
```

(c) Delete:

```markdown
- Every symbol the brief names exists (`git grep -n`), or the task that creates it is named.
```

Every other item keeps its words and its place. Count: fourteen.

(d) In `## Trigger table`, directly after `Should fire: checking that a new helper reads like the module around it.`, insert:

```markdown
Should fire: reviewing a task diff that changes an Angular component but adds no spec file.
```

- [ ] **Step 5: The two eval folders**

`.claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Review a plan that sends each new trade plan to the eToro demo account from the scan loop. What happens if the scan retries after a timeout?
```

`.claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: staff-engineer
min: 1
---

The `staff-engineer` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`.claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

This task diff changes an Angular table component's sorting logic but adds no spec file. Is it ready to merge?
```

`.claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: senior-engineer
min: 1
---

The `senior-engineer` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
git add .claude/skills/staff-engineer/evals/fire-etoro-order-idempotency .claude/skills/senior-engineer/evals/fire-frontend-spec-coverage
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
git status --porcelain
```

Expected: every call `VERDICT: PASS`; `staff-engineer` at fifteen items, `senior-engineer` at fourteen, seven eval cases each; `git status` lists the two skills, their `.agents/skills/` copies, the four eval files and the test file. A citation finding means a path or cite was retyped: fix it to the text above, never an allowlist line.

- [ ] **Step 7: Commit**

```bash
git add tests/hooks/test_role_skills.py .claude/skills/staff-engineer/SKILL.md .claude/skills/senior-engineer/SKILL.md .claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/prompt.md .claude/skills/staff-engineer/evals/fire-etoro-order-idempotency/graders/skill-fired.md .claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/prompt.md .claude/skills/senior-engineer/evals/fire-frontend-spec-coverage/graders/skill-fired.md .agents/skills/staff-engineer/SKILL.md .agents/skills/senior-engineer/SKILL.md
git commit -m "docs(v213): staff and senior seats cover admin load, suites, PITR, eToro, specs

V213-10. staff-engineer: drops the Bump: item (close-out owns it), folds
far-off scheduling into long-run cost; adds the admin worker budget, one CI
job per suite, PITR and backups, an eToro idempotent-send item (15).
senior-engineer: drops 'symbols exist' (task-brief owns it); adds the
mutation check, suite placement and Vitest specs for frontend changes (14).
One fire eval each.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V213-11: `financial-advisor` and `technical-analyst` coverage

**Model:** sonnet — one eToro item, a merge plus four structure items under the cap, two eval folders and test rows; needs care, not design.

**Files:**
- Modify: `tests/hooks/test_role_skills.py` (`CROSS_CUTTING` row `financial-advisor`; `COVERAGE` rows `financial-advisor`, `technical-analyst`)
- Modify: `.claude/skills/financial-advisor/SKILL.md` (`## Checklist`, `## Trigger table`)
- Modify: `.claude/skills/technical-analyst/SKILL.md` (`## Checklist`, `## Trigger table`)
- Create: `.claude/skills/financial-advisor/evals/fire-etoro-fees/prompt.md`, `.claude/skills/financial-advisor/evals/fire-etoro-fees/graders/skill-fired.md`
- Create: `.claude/skills/technical-analyst/evals/fire-bos-choch-structure/prompt.md`, `.claude/skills/technical-analyst/evals/fire-bos-choch-structure/graders/skill-fired.md`
- Generated: `.agents/skills/financial-advisor/SKILL.md`, `.agents/skills/technical-analyst/SKILL.md`

**Interfaces:**
- Consumes: `LEADS`, `CROSS_CUTTING`, `_checklist` (V213-7); `COVERAGE`, `test_seat_names_its_coverage_items` (V213-8).
- Produces: nothing new; rows only. After this task `CROSS_CUTTING` holds five rows (`risk-manager`, `veteran-trader`, `quant-researcher`, `staff-engineer`, `financial-advisor`), the full set the index ledger names; V213-12 adds none (`ux-designer` carries no shared lead).

**Spec rows (§ C table).** financial-advisor adds eToro fees and minimum position size to frictions and account fit, generic, no jurisdiction-specific tax (partner's choice), nothing removed: 11 + 1 = **12**. technical-analyst adds swing significance tiers with BOS/CHoCH, liquidity sweeps, ATR-band stops as volatility logic, and volume confirmation as independent evidence, making room by merging the chart-overlay item with `explain.py`: 11 − 1 + 4 = **14**. New paths, checked with `git ls-files`: `swingbot/core/market/structure.py` (v121 causal swing structure; `confirmed_pivots` defined at :56), `swingbot/core/market/turtle_soup.py` (v180 live sweep trigger), `swingbot/core/market/atr_band.py`. New `§` cite: `docs/claude/known-traps.md` § Confluence ATR-band stops (v191) (heading `## Confluence ATR-band stops (v191): inert by default, coupled to gap sizing`; after the lint strips the trailing `).` the cite is still a prefix of it).

V213-7 moved `financial-advisor`'s boundary paragraph above its educational paragraph, and V213-6 rewrote `technical-analyst`'s closed-ideas item. Leave both as they are.

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_role_skills.py`, add to `CROSS_CUTTING` (after the `staff-engineer` row):

```python
    "financial-advisor": frozenset({"eToro:"}),
```

and to `COVERAGE` (after the `senior-engineer` row):

```python
    "financial-advisor": ("overnight fees", "minimum position size"),
    "technical-analyst": ("`confirmed_pivots`", "BOS/CHoCH", "significance tier",
                          "`swingbot/core/market/turtle_soup.py`",
                          "`swingbot/core/market/atr_band.py`",
                          "Volume counts as confirmation",
                          "`swingbot/core/market/explain.py`"),
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: FAIL in `test_cross_cutting_seats_carry_their_leads` (`financial-advisor eToro:` 0), `test_seat_names_its_coverage_items[financial-advisor]` (both anchors) and `test_seat_names_its_coverage_items[technical-analyst]` (every anchor except the `explain.py` path, which the old explanation item already carries). Nothing else fails.

- [ ] **Step 3: `financial-advisor` checklist — one item**

In `.claude/skills/financial-advisor/SKILL.md`, `## Checklist`, directly after `` - Frictions in `swingbot/core/edge/frictions.py` include the commissions a retail broker actually charges. ``, insert:

```markdown
- eToro: demo only, never `account: real`; eToro's spread, overnight fees and minimum position size are counted in the frictions and the account fit.
```

Every other item keeps its words and its place. Count: twelve.

In `## Trigger table`, directly after `Should fire: asking how swing turnover affects the after-tax result of following the alerts.`, insert:

```markdown
Should fire: asking whether eToro's spreads, overnight fees and minimum position size change what a small account can follow.
```

- [ ] **Step 4: `technical-analyst` checklist — three edits**

In `.claude/skills/technical-analyst/SKILL.md`, `## Checklist`:

(a) Directly after the patterns item (it starts `` - Patterns (`chart_patterns.py` ``), insert four items:

```markdown
- Swing pivots come from `confirmed_pivots` in `swingbot/core/market/structure.py`, and a break of structure or change of character (BOS/CHoCH) reads confirmed pivots only, each significance tier kept distinct.
- A liquidity sweep (`swingbot/core/market/turtle_soup.py`) is a wick through an aged level that closes back inside it, not any new low.
- An ATR-band stop (`swingbot/core/market/atr_band.py`) is volatility logic around the level, not a structural stop (`docs/claude/known-traps.md` § Confluence ATR-band stops (v191)).
- Volume counts as confirmation only when it is independent of the price move that triggered the setup, not the same bar's range restated.
```

(b) The chart-overlay item, old:

```markdown
- The chart overlay (`swingbot/core/charts/chart_strategy_overlay.py`) draws the same levels the plan uses.
```

new:

```markdown
- The chart overlay (`swingbot/core/charts/chart_strategy_overlay.py`) draws the same levels the plan uses, and the strategy explanation (`swingbot/core/market/explain.py`) describes the rule that fired, not a generic setup.
```

(c) Delete the explanation item, now merged into (b):

```markdown
- The strategy explanation (`swingbot/core/market/explain.py`) describes the rule that fired, not a generic setup.
```

Every other item, V213-6's closed-ideas item included, keeps its words and its place. Count: fourteen.

In `## Trigger table`, directly after `Should fire: checking that a new RSI divergence rule uses the standard RSI.`, insert:

```markdown
Should fire: asking whether a break-of-structure check reads BOS and CHoCH from confirmed swing pivots.
```

- [ ] **Step 5: The two eval folders**

`.claude/skills/financial-advisor/evals/fire-etoro-fees/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

If someone follows the alerts on an eToro account, do its spreads, overnight fees and minimum position size change whether a small retail account can keep up?
```

`.claude/skills/financial-advisor/evals/fire-etoro-fees/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: financial-advisor
min: 1
---

The `financial-advisor` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`.claude/skills/technical-analyst/evals/fire-bos-choch-structure/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Does the new break-of-structure check confirm swing pivots the way traders read a BOS versus a CHoCH, or does it react to pivots that are not confirmed yet?
```

`.claude/skills/technical-analyst/evals/fire-bos-choch-structure/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: technical-analyst
min: 1
---

The `technical-analyst` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

- [ ] **Step 6: Run the tests to verify they pass, then check the part as a whole**

```bash
git add .claude/skills/financial-advisor/evals/fire-etoro-fees .claude/skills/technical-analyst/evals/fire-bos-choch-structure
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
python scripts/dev/skill_citations.py
git status --porcelain
```

Expected: every `testrun.py` call prints `VERDICT: PASS`; the CLI prints `skill citations: clean`; `financial-advisor` at twelve items, `technical-analyst` at fourteen, seven eval cases each; `git status` lists the two skills, their `.agents/skills/` copies, the four eval files and the test file.

Part-level check (this is the last task of Phase C): every seat the spec's § C table names now carries its additions, so these counts hold — `risk-manager` 15, `veteran-trader` 15, `quant-researcher` 15, `quant-engineer` 14, `staff-engineer` 15, `senior-engineer` 14, `financial-advisor` 12, `technical-analyst` 14, `fundamental-analyst` 11 (boundary only). Confirm with:

```bash
python -c "import pathlib;[print(r, sum(1 for l in pathlib.Path('.claude/skills',r,'SKILL.md').read_text(encoding='utf-8').split('## Checklist')[1].split('\n## ')[0].splitlines() if l.startswith('- '))) for r in 'risk-manager veteran-trader quant-researcher quant-engineer staff-engineer senior-engineer financial-advisor technical-analyst fundamental-analyst'.split()]"
```

A count that differs means an item was lost or duplicated in V213-8..V213-11; fix it in the seat it belongs to before the commit (`test_checklist_has_eight_to_fifteen_items` only catches a count outside eight to fifteen).

- [ ] **Step 7: Commit**

```bash
git add tests/hooks/test_role_skills.py .claude/skills/financial-advisor/SKILL.md .claude/skills/technical-analyst/SKILL.md .claude/skills/financial-advisor/evals/fire-etoro-fees/prompt.md .claude/skills/financial-advisor/evals/fire-etoro-fees/graders/skill-fired.md .claude/skills/technical-analyst/evals/fire-bos-choch-structure/prompt.md .claude/skills/technical-analyst/evals/fire-bos-choch-structure/graders/skill-fired.md .agents/skills/financial-advisor/SKILL.md .agents/skills/technical-analyst/SKILL.md
git commit -m "docs(v213): financial-advisor counts eToro costs; technical-analyst covers structure

V213-11. financial-advisor: an eToro item for spread, overnight fees and
minimum position size in frictions and account fit, generic (12).
technical-analyst: the overlay and explain.py items merge; adds confirmed
pivots with BOS/CHoCH and significance tiers, liquidity sweeps, ATR-band
stops as volatility logic, volume as independent evidence (14). One fire
eval each.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

