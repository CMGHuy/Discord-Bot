# v155 — Research ritual skills: the idea screen, the pre-registration and the data check get a checklist and a hook

**Version:** ui 1.22.0 · bot 2.3.0 (at writing)
**Bump:** none (Claude/Codex tooling only; no shipped code)
**Edge:** none (integrity) — it guards how a hypothesis is screened and recorded. It adds no strategy, sets no threshold and runs no measurement itself.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer
**Status:** spec written 2026-10-10; panel review applied; no plan yet.
**Depends on:** v154 (the strict frontmatter helper and quoted descriptions new skills are written against). Builds on v136 (ledger) and v140 (idea screen).

## Why

Three research steps have a script and a rule in `docs/claude/`, but no
checklist that loads when the step is taken and no hook behind the rule:

1. **The idea screen's one-shot rule has one guard and three ways round it.**
   `scripts/backtest/screen_idea.py --idea <name>` appends a `screen-<name>`
   row to `docs/superpowers/results/preregistration-ledger.jsonl` (61 rows on
   2026-10-10) and refuses a second real run of an id already there
   (`screen_idea.py:196-198`). But `--dry-run` without `--tickers` runs the
   full universe and prints the verdict any number of times
   (`screen_idea.py:191-196`); `--ledger <fresh path>` reads as an empty
   ledger (`swingbot/core/backtesting/instrument/stats.py:182`) and runs for
   real; and a crash between the results-doc write and the ledger append
   (`screen_idea.py:393-394`) leaves a read verdict with no row. Each lets a
   definition be changed after its data was seen.
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

In `.claude/hooks/guardrails.py`, a second layer over the script's own
refusal. It does **not** copy `_rule_closed_preregistration`'s substring
matching (`guardrails.py:267-274`). It splits the command on `&&`, `;`, `|`
and newlines (after joining backslash continuations), tokenises each segment
with `shlex`, and reads flags only from the segment whose tokens include a
`screen_idea.py` path or the `screen_idea` module name. Both `--idea <name>`
and `--idea=<name>` are read.

For that segment it denies when any of these holds:

| Condition | Why |
|---|---|
| no `--dry-run`, and `screen-<name>` is in the default ledger, or a results doc `*-screen-<name>.md` exists | a second read of a screened idea, including after a crash before the ledger append |
| `--dry-run` without `--tickers` | a full-universe read that writes nothing |
| `--ledger` resolving to anything but `stats.LEDGER_PATH`, without `--dry-run` | an empty ledger is a bypass, not an error |

The remaining allowed forms are a first real run against the default ledger,
and a `--tickers ... --dry-run` smoke test. The deny message names the ledger
row's date, verdict and record path where there is one.

A command that wraps the script in a quoted string — the ssh wrapper, or
`pwsh -Command "..."` — is matched on the `screen_idea` name anywhere in the
string and denied outright: the screen's cache lives on this machine and there
is no reason to run it through either. The rule stays under complexity 15 by
keeping segment splitting, flag extraction and the ledger and results lookups
in separate helpers.

### 2. `/screen <idea>` (Tier 2, slash-only)

Checklist:

1. Read the Stage −2 rules in `backtest-methodology.md` — through the
   funnel-stages section once v154 has added that heading, otherwise from the
   bullet at `:53`.
2. Confirm `<idea>` is a key of `IDEAS` in
   `swingbot/core/backtesting/screen/ideas/__init__.py:45`. If it is not, the
   idea is added and committed **before** any run, in a commit that touches no
   results file — the definition is the pre-registration.
3. Confirm `git status --short swingbot/core/backtesting/screen/` is empty, so
   the idea module and the shared `race.py`, `null.py` and `verdict.py` are the
   committed ones, and note that commit hash for the results doc.
4. Confirm no `screen-<idea>` ledger row and no `*-screen-<idea>.md` results
   doc exists. If either does, stop and report it.
5. A closed fail is not retried under a similar name. If `<idea>` is a variant
   of an idea already in the ledger, stop and ask the partner whether it is a
   new hypothesis; the skill does not decide that.
6. Optional smoke: `--tickers <two or three> --dry-run`, which writes nothing.
7. Dispatch `backtest-runner` for the real run; relay its verdict line only.
8. Commit the results doc (with the definition hash from step 3) and the
   ledger together. State the verdict as the script printed it. A
   `SCREEN-FAIL` is a finished result.

### 3. `/prereg <id>` (Tier 2, slash-only)

Two phases, and the skill refuses to run the second without the first.

- **Before:** write the results doc stub with hypothesis, instrument (one of
  `stats.INSTRUMENTS`), metric, N floor, pass threshold and stopping rule, each
  quoted from the methodology section that owns it, and commit it. The commit
  hash is the registration.
- **After:** run `preregistration_ledger.py` with the measured `--n`,
  `--exp-r`, `--p` and `--verdict`, with `--record` pointing at that doc.
  Report the printed q-value as reported-only; it gates nothing.

Before the second phase the skill checks two things: the stub was committed
before any results (`git log --format=%H -- <record>` shows the stub commit
first), and the frozen block — hypothesis, instrument, metric, N floor,
threshold, stopping rule — is unchanged since that commit
(`git diff <stub hash> -- <record>` shows additions below the block only).
`--hypothesis` is passed verbatim from the stub. A changed block stops the
ritual and is reported; it is never reconciled silently.

### 4. `/data-check [<universe>]` (Tier 2, slash-only, `context: fork`, `model: haiku`)

Runs `validate_data.py` in default mode, and again with `--universe <name>`
only when a name is given; with no argument it says the extended cache was not
checked. The script always exits 0 (`validate_data.py:87-98` has no
`sys.exit`), so the skill reads its output, never its exit code: the final
`done -- N symbol(s) checked in <dir>, M with issues` line gives the verdict,
and the first five symbols come from the `ISSUE:` lines.

Universe mode skips symbols with no file (`validate_data.py:72-73`), and an
unknown universe name loads as empty and checks only the watchlist
(`universe.py:95,108`). The verdict line therefore reports `checked/total`,
and a run that checked fewer symbols than the universe holds is reported as
incomplete, never as clean.

Which scripts read which cache is taken from the two-caches rules in
`known-traps.md` (`:7`, `:137`), not from the docstring at
`validate_data.py:12-17`, which is stale. The skill fixes nothing; repair stays
with `scripts/ops/market_cache_repair.py` and a human.

### Codex mirror

`sync_codex.py` mirrors the three skills; `AGENTS.md` gains their names and
the new hook rule; `.codex/hooks.json` is unchanged because the rule lives
inside `guardrails.py`, which both already call. All in the same commits.

## Edge cases

- A ledger row whose id merely starts with `screen-<name>`: only an exact id
  match denies in the hook. Whether a similarly named idea is a retry is a
  judgement, handled by `/screen` step 5.
- A crash before anything was written leaves no row and no results doc, so the
  re-run is allowed.
- `/prereg` for a measurement that produces no p-value: `--p null` is valid in
  the script and stays valid here.

## Testing

- `tests/hooks/test_guardrails.py`, with a temp ledger and results directory,
  never the real ones: deny on an existing id; deny on an existing results doc
  with no row; deny a full-universe `--dry-run`; deny a non-default or
  non-existent `--ledger`; allow a first run; allow `--tickers --dry-run`;
  both `--idea` forms; exact-id match only; a chained `cd x && python ...`
  command; a backslash-continued command; a quoted ssh-wrapper string.
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

## Panel review

Run 2026-10-10 on `24d9df0d`. quant-researcher returned two BLOCKING and seven
ADVISORY; quant-engineer three BLOCKING and three ADVISORY.

- quant-researcher: BLOCKING — a full-universe `--dry-run` reads the verdict without writing — applied (hook denies it).
- quant-researcher, quant-engineer: BLOCKING — a fresh `--ledger` path reads as empty and bypasses the rule — applied (non-default ledger denied).
- quant-engineer: BLOCKING — substring matching cannot honour chained or continued commands — applied (segment split, `shlex`, wrapper strings denied).
- quant-engineer: BLOCKING — `validate_data.py` always exits 0 — applied (output parsed, exit code ignored).
- quant-researcher: nothing verified the committed definition at run time — applied (`/screen` step 3, hash recorded).
- quant-researcher: `/prereg` proved commit order only — applied (frozen block diffed against the stub).
- quant-researcher: the `screen-high52w-v2` example was the retry the skill forbids — applied (example removed; `/screen` step 5).
- quant-researcher: a crash between doc write and ledger append — applied (results doc checked in the hook and in step 4).
- quant-researcher: "by convention only" was inaccurate — applied (Why rewritten around `screen_idea.py:196-198`).
- quant-researcher: `IDEAS` lives in `screen/ideas/__init__.py:45` — applied.
- quant-researcher: no funnel-stages heading exists yet — applied (falls back to `:53` until v154 lands).
- quant-engineer: `--universe` needs a name; unknown names and missing symbols — applied (`checked/total`, incomplete is not clean).
- quant-engineer: the script docstring's cache mapping is stale — applied (`known-traps.md` is the source).
- quant-engineer: tests for chained, wrapped and missing-ledger commands — applied.
