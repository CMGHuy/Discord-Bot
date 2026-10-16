---
name: trade-scout
description: "Run the trade scout (/trade-scout [roles=...] [autopsy=<path>]): live-book autopsy, one scout agent per generator role in series, scout_merge.py slate, quant-researcher panel. Use when asking what to test next from the live book."
---

# Trade scout

Turns the live book into a ranked slate of hypotheses for `/screen` or
`/prereg`. No gate moves: a slate row never edits code, config, thresholds or
live alerts, and never licenses a re-run of a closed pre-registration. Every
entry or filter idea still needs a `SCREEN-PASS` row before its spec.
No paid usage: the autopsy and merge are scripts; the roles run as subagents.
The evidence rule lives in `docs/claude/skills-tools.md` § Generator roles (v161).

## Step 1 — The autopsy

Use the newest `docs/superpowers/results/*-book-autopsy.md` (or `autopsy=<path>`).
If it is older than a week or absent, ask the partner with `AskUserQuestion`
before the export: it is read-only but a production command, preferably run
outside the US session and premarket. On yes, from the main tree:

- `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" < scripts/ops/export_book_rows.sh > <scratchpad>/rows.csv`, then the same with `rejections` into `<scratchpad>/rejections.csv`. Raw CSVs stay in the scratchpad, never committed.
- Fetch bars for the book's tickers into a scratch cache: `BACKTEST_CACHE_DIR=<scratchpad>/autopsy_bars python scripts/data/fetch_backtest_data.py --tickers <list> --start <first plan date minus at least 550 calendar days> --end today`. The fetcher requires 260 daily bars, so include this warm-up history even for a young book. Never into `data/backtest_cache/`.
- `python scripts/reports/book_autopsy.py <scratchpad>/rows.csv <scratchpad>/rejections.csv --bars-dir <scratchpad>/autopsy_bars`.

## Step 2 — Dispatch the roles serially

Roles come from `roles=` or default to `exit-harvester`, `setup-scout`,
`regime-desk`, in that order; an unknown role stops the run and names the
valid ones. Dispatch the `scout` agent once per role with
`role=<role> autopsy=<the .md path>`, serially: wait for each to return before
the next, never in parallel. `UNKNOWN ROLE` or `BLOCKED:` stops the run;
`NO ROWS` is recorded and skipped.

## Step 3 — Merge

Write every role's rows to one scratchpad file, each role's blocks under a
`## role: <name>` line, then run
`python scripts/dev/scout_merge.py <file> --autopsy <the .json path>`.
It drops closed, duplicate and unsupported rows with reasons and writes
`docs/superpowers/results/<date>-scout-slate.md`.

## Step 4 — Commit and panel

Commit the autopsy pair and the slate on `main`. Run
`/panel quant-researcher <slate>` and append its findings to the slate as
`## Panel review`; commit again.

## Step 5 — The partner picks

Present the top rows with `AskUserQuestion`: one question, recommended row
first. The partner's pick goes to `/screen` or `/prereg`; the scout itself
starts neither.

## Removal condition

If three consecutive slates send no row to `/screen` or `/prereg`, record that
in the latest slate and ask the partner whether to retire the tooling.

## Trigger table

Should fire: /trade-scout.
Should fire: asking what hypothesis to test next from the live book's results.
Should fire: asking for a ranked slate of ideas from the latest book autopsy.
Should not fire: running an idea screen that is already defined.
Should not fire: reviewing a spec through one expert role.
Should not fire: checking today's alerts on the production VM.
