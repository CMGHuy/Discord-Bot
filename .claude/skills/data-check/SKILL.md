---
name: data-check
description: "Validate the local OHLCV caches with scripts/data/validate_data.py, in default mode and optionally for one --universe, and report each verdict from the script's output, never its exit code. Invoked explicitly as /data-check [<universe>], never model-triggered."
disable-model-invocation: true
context: fork
model: haiku
---

# Data check

You report; you fix nothing. Repair stays with
`scripts/ops/market_cache_repair.py` and a human. Arguments: `$ARGUMENTS`
(empty, or one universe name such as `sp500`, written `<name>` below).

## Step 1 — Read the authority

`python scripts/dev/doc_section.py docs/claude/known-traps.md "Two OHLCV caches" "Full-history cache"`.
Exit code 2 means a heading is gone: read the whole file instead. Which
script reads which cache comes from there, never from the docstring of
`validate_data.py`, which is stale.

## Step 2 — Default mode

`python scripts/data/validate_data.py` checks `data/backtest_cache/`. It
always exits 0, so ignore the exit code and read the output. Its last line is
`done -- <checked> symbol(s) checked in <dir>, <bad> with issues`: CLEAN when
`<bad>` is zero, ISSUES otherwise. No `done --` line (a traceback) is ERROR,
with the traceback's last line quoted.

## Step 3 — Universe mode, only when a name was given

With no argument, skip to Step 4. Otherwise:

1. `python -c "from swingbot.core.marketdata import universe; print(len(universe.universe_symbols('<name>')))"`.
   Zero means an unknown or empty universe: only the watchlist gets checked,
   so the verdict is INCOMPLETE whatever the run prints.
2. `python scripts/data/validate_data.py --universe <name>` checks
   `market_data/`. Its last line is
   `done -- <checked>/<total> symbol(s) checked in <dir> (watchlist + universe='<name>'), <bad> with issues`.
   Symbols with no file are skipped silently, so `<checked>` below `<total>`
   is INCOMPLETE, never CLEAN. Otherwise CLEAN or ISSUES as in Step 2.

## Step 4 — Reply with this, and nothing else

    /data-check
    Default (data/backtest_cache/): <CLEAN|ISSUES|ERROR> -- <its done line, verbatim>
    Universe '<name>' (market_data/): <CLEAN|ISSUES|INCOMPLETE|ERROR> -- <its done line, verbatim>
    First issues: <the first five ISSUE: lines across both runs, verbatim, or none>
    Read by: <one line per cache, from the Step 1 sections>
    Not checked: data/backtest_cache_ext (the idea-screen cache read by scripts/backtest/screen_idea.py); no validate_data.py mode covers it.

With no argument, the universe line reads
`Universe: not checked -- no universe name given.` instead.

The last line is fixed text. Copy it exactly, every time, even when every
mode is CLEAN: a clean verdict never vouches for an idea-screen run's data.

## The gate

Every verdict taken from a `done --` line, `checked/total` shown for a
universe, and the fixed `Not checked:` line last.
