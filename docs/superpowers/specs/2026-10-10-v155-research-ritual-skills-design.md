# v155 — Research ritual skills: the idea screen, the pre-registration and the data check get a checklist and a hook

**Version:** ui 1.22.0 · bot 2.3.0 (at writing)
**Bump:** none (Claude/Codex tooling only; no shipped code)
**Edge:** none (integrity) — it guards how a hypothesis is screened and recorded. It adds no strategy, sets no threshold and runs no measurement itself.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer
**Status:** spec written 2026-10-10; panel review pending; no plan yet.
**Depends on:** v154 (the strict frontmatter helper and quoted descriptions new skills are written against). Builds on v136 (ledger) and v140 (idea screen).

## Why

Three research steps have a script and a rule in `docs/claude/`, but no
checklist that loads when the step is taken and no hook behind the rule:

1. **The idea screen is one shot, by convention only.**
   `scripts/backtest/screen_idea.py --idea <name>` appends a
   `screen-<name>` row to `docs/superpowers/results/preregistration-ledger.jsonl`
   (61 rows on 2026-10-10) and writes a results doc. `backtest-methodology.md`
   § Stage −2 says a screen is never re-run. `.claude/hooks/guardrails.py` has
   `_rule_closed_preregistration` for tuned knobs, and nothing for a second
   screen of the same idea.
2. **A pre-registration is written by hand.** `scripts/reports/preregistration_ledger.py`
   records the verdict afterwards. Nothing prompts for the hypothesis, metric,
   N floor and threshold to be committed *before* the measurement runs, which
   is the part that makes it a pre-registration.
3. **Two OHLCV caches, one validator, no prompt to use it.**
   `scripts/data/validate_data.py` checks `data/backtest_cache/` by default and
   the extended cache with `--universe`. Which cache a given script reads is in
   `known-traps.md`; nothing asks for a clean validation before a run whose
   result will be recorded.

The first brainstorm listed six skills here. Four were dropped after reading
the code: bootstrap bounds, Benjamini–Hochberg q-values, the permutation test
and the walk-forward gate already exist and `backtest-gate` already fires on
them.

## Decisions taken in the brainstorm

- **A hook denies, a skill teaches** (`skills-tools.md` § The v96 skills
  layer). The screen re-run is mechanically detectable, so it is a hook rule.
- **All three skills are slash-only.** They are rituals the partner starts;
  none joins the model-invocable listing.
- **No skill restates a threshold.** Each names the doc section that owns it
  and reads it with `scripts/dev/doc_section.py` (v154).

## Design

### 1. Hook rule `_rule_screen_rerun`

In `.claude/hooks/guardrails.py`, beside `_rule_closed_preregistration`.
Denies a Bash command that runs `screen_idea.py` with `--idea <name>` and no
`--dry-run` when a row with id `screen-<name>` is already in the ledger. The
deny message names the row's date, verdict and record path. A missing or
unreadable ledger allows the command (the script itself will fail loudly); a
`--ledger <other path>` argument is checked against that path instead.

The function stays under complexity 15: argument extraction and the ledger
lookup are separate helpers.

### 2. `/screen <idea>` (Tier 2, slash-only)

Checklist:

1. Read `backtest-methodology.md` funnel-stages section (Stage −2).
2. Confirm `<idea>` is a key of `IDEAS` in `screen_idea.py`. If it is not, the
   idea must be added and committed **before** any run, in a commit that
   touches no results file — the definition is the pre-registration.
3. Confirm no `screen-<idea>` row exists. If one does, stop and report it.
4. Optional smoke: `--tickers <two or three> --dry-run`, which writes nothing.
5. Dispatch `backtest-runner` for the real run; relay its verdict line only.
6. Commit the results doc and the ledger together. State the verdict as the
   script printed it. A `SCREEN-FAIL` is a finished result, never retried with
   a changed definition under the same or a similar name.

### 3. `/prereg <id>` (Tier 2, slash-only)

Two phases, and the skill refuses to run the second without the first.

- **Before:** write the results doc stub with hypothesis, instrument (one of
  `stats.INSTRUMENTS`), metric, N floor, pass threshold and stopping rule, each
  quoted from the methodology section that owns it, and commit it. The commit
  hash is the registration.
- **After:** run `preregistration_ledger.py` with the measured `--n`,
  `--exp-r`, `--p` and `--verdict`, with `--record` pointing at that doc.
  Report the printed q-value as reported-only; it gates nothing.

The skill checks the stub's commit precedes the results commit
(`git log --format=%H -- <record>` has at least two entries, or the stub is
committed and the working tree holds the results).

### 4. `/data-check [<universe>]` (Tier 2, slash-only, `context: fork`, `model: haiku`)

Runs `validate_data.py` in both modes (default, and `--universe <name>` when
given) and returns one verdict line per cache: issues found or clean, with the
count and the first five symbols. It reads the two-caches section of
`known-traps.md` so the report says which scripts read which cache. It fixes
nothing; repair stays with `scripts/ops/market_cache_repair.py` and a human.

### Codex mirror

`sync_codex.py` mirrors the three skills; `AGENTS.md` gains their names and
the new hook rule; `.codex/hooks.json` is unchanged because the rule lives
inside `guardrails.py`, which both already call. All in the same commits.

## Edge cases

- `--idea` given as `--idea=<name>`: the rule parses both forms.
- A screen invoked through `python -m` or with a path prefix: matched on the
  `screen_idea.py` basename or module name.
- A ledger row whose id merely starts with `screen-<name>` (for example
  `screen-high52w-v2`): only an exact id match denies.
- `/prereg` for a measurement that produces no p-value: `--p null` is valid in
  the script and stays valid here.

## Testing

- `tests/hooks/test_guardrails.py`: deny on an existing id, allow on a new id,
  allow with `--dry-run`, allow on a missing ledger, both `--idea` forms, exact
  match only, `--ledger` override. Uses a temp ledger, never the real file.
- `tests/hooks/test_skill_shape.py`: the three names join `TIER_2` and the
  slash-only set.
- `tests/hooks/test_codex_mirror.py` green after `sync_codex.py`.
- No eval suites: slash-only skills have no trigger to prove.

## Parallelisation

- **Group A:** the hook rule and its tests — independent of the skills.
- **Group B (independent of each other, sequential commits):** `/screen`,
  `/prereg`, `/data-check`. They share `test_skill_shape.py`'s `TIER_2` set and
  `sync_codex.py` output, so they commit one at a time.
- `/screen` text refers to the hook rule; it lands after Group A.

## Out of scope

- Any new statistical method, any new screen idea, any run of a screen.
- Changing `screen_idea.py`, the ledger schema or a threshold.
- Prediction skills (meta-labeling, forecast evaluation, feature research):
  each is a new filter and needs a `SCREEN-PASS` row before it gets a spec.
