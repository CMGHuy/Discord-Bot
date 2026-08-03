# V17 chunks that ran *before* the 1.75% loss cap — kept deliberately

These three chunks (`EMA Crossover`, `VWAP`, `Fibonacci`) started before V51
Step 1's `MAX_LOSS_PCT` cap was committed (2026-08-02 22:01) and therefore ran
**uncapped**. The other eight chunks in the parent directory started after it
and ran capped.

`tune_sizing.py` never touches `MAX_LOSS_CAP_ENABLED` (default `true`), so each
chunk silently inherited whatever the working tree held at its process start.
Nothing in the run announced this; it was caught by lining chunk start times up
against `git log`.

They are **not** part of V17's result — the aggregator globs `v17/*.json`
non-recursively, so these are excluded from every table. They are kept because
the re-run makes them the other arm of a controlled comparison: same grid, same
window, same tickers, one knob different. That contrast is reported by
`scripts/summarize_v17_grid.py` and is the cleanest measurement in the plan of
what the cap costs in win rate and buys in expectancy.

Do not merge these back into the parent directory.
