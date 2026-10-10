---
name: result-digest
description: "Run scripts/backtest/compare_backtest_json.py on two run_backtest_range.py --json files and return its output verbatim, prefixed with both paths and ending with a derived-figures disclaimer. Invoked explicitly as /result-digest <a.json> <b.json>, never model-triggered."
---
<!-- GENERATED from .claude/skills/result-digest/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Result digest

You are a pipe, not an analyst. You run one script on two files and hand its
output back **verbatim**. You never paraphrase, round, reorder, summarise or
recompute a figure, never add a figure of your own, and never call a result a
pass, a fail, better or worse. Judging a result is `backtest-gate`'s job;
quoting one is `pooled-numbers`'.

## Step 1 — Take exactly two paths

Arguments: `$ARGUMENTS`

They must be exactly two paths to `run_backtest_range.py --json` outputs. The
first fills the script's OFF row, the second its ON row. The script has no
one-file mode. With any other number of arguments, reply with this one line
and stop, running nothing:

`Usage: /result-digest <a.json> <b.json> -- both files are required.`

## Step 2 — Run the script

```bash
python scripts/backtest/compare_backtest_json.py <a.json> <b.json>
```

Pass the two paths exactly as given, in the same order, and no third (label)
argument. Capture its stdout and stderr together, and its exit code.

## Step 3 — Reply with this, and nothing else

```
/result-digest
A (OFF row): <a.json as given>
B (ON row):  <b.json as given>
Header: the "=== v35 AVWAP comparison ===" line is the script's own,
hard-coded; it does not mean these files are an AVWAP run. The window is
whatever the two files were run on; the script prints none.

<the script's complete output, verbatim, inside a fenced block>

Derived by compare_backtest_json.py from the named files; not live-book figures — re-derive per pooled-numbers before quoting in a spec, plan or commit.
```

If the script exits non-zero (a missing file, unreadable JSON, a file that is
not a `--json` output), the fenced block holds its error output verbatim and
there are no figures anywhere in the reply. Do not explain the error, retry
with other paths or repair the files.

## The gate

The reply is the block above: both paths, the header line, the script's
output or error untouched, and the closing disclaimer line exactly as written.
