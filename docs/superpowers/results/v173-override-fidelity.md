# v173 override fidelity: manual overrides vs the v2 engine

**Spec:** `docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md` (§4, frozen pre-registration; moves to `specs/implemented/` at close-out)
**Ledger id:** `v173-override-fidelity` (`preregistration-ledger.jsonl`, instrument `v2`)
**Authority:** the Postgres table `preregistration_verdicts` on production. This file and the jsonl row are the record, filled by the mirror below.

## What is measured

Each manual close (`reason == "manual"`, individual, stamped, `resolved`) is replayed from its real fill through the v2 exit engine left alone. Delta R = actual R minus engine R, both through one `costs.book` call each, net of modelled costs and pre-tax. The rule is frozen in the spec §4: at least 30 counted overrides over at least 10 distinct ISO weeks, no eligible row open, left-out rows at most 20% of eligible rows; then a week-cluster bootstrap 95% interval on the mean delta R: wholly below 0 is `COST`, wholly above 0 is `SAVED`, otherwise `INCONCLUSIVE`.

The bot's daily job `override_verdict_check` (`swingbot/commands/scanning/loops.py`, 23:50 Europe/Berlin on weekdays) is the only evaluator. It writes the verdict once; the table's primary key makes a second write impossible. Nobody runs the evaluation by hand.

## Recorded verdict

Not recorded yet.

## Standing procedure: mirroring the recorded verdict

Run this when the bot logs the WARNING `override_verdict_check: <VERDICT> verdict v173-override-fidelity recorded on <date> and frozen. ...`, or when a report or the Analytics panel shows a recorded verdict while `docs/superpowers/results/preregistration-ledger.jsonl` has no `v173-override-fidelity` row.

1. Print the stored row on the VM (read-only):

   ```bash
   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/reports/execution_fidelity_report.py --production --mirror-row" > "$SCRATCH/v173-mirror-row.json"
   ```

   The file must hold exactly one line starting `{"id": "v173-override-fidelity"`. `no verdict recorded` means there is nothing to mirror: stop.
2. On `main` in the repo root, append it through the validating writer `stats.append_ledger_row` (it refuses a duplicate id):

   ```bash
   python -c "import json, pathlib, sys; from swingbot.core.backtesting.instrument import stats; stats.append_ledger_row(json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').strip()))" "$SCRATCH/v173-mirror-row.json"
   ```

3. Replace "Not recorded yet." under `## Recorded verdict` above with the row's verdict, date, `n`, mean delta R (`exp_r`) and the CI from its hypothesis.
4. Commit both files on `main`:

   ```bash
   git add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/v173-override-fidelity.md
   git commit -m "docs(v173): mirror the recorded override-fidelity verdict"
   ```

Never edit or delete the table row, and never evaluate again. If the jsonl row and the table ever disagree, the table wins: re-mirror from step 1.
