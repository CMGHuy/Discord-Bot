# v123 progress_stall funnel result -- CLOSED at Stage -1 (refused:zero-diff)

Pre-registration: `docs/superpowers/results/2026-10-02-v123-preregistration.md` (commit 9d210d85), followed as written. Code (`swingbot/`, `scripts/`) is unchanged between 9d210d85 and the run's HEAD 1b9a1269.
Edge: harvest. Separate budget from hl_trail, never pooled. VALIDATION budget intact (Stage 3 never run).

Quoted rule (Stage -1): "Run at `b = 0.00` and `c = 1.00` (the most active values). Zero changed outcomes means refused, budget intact." Plan: `refused:zero-diff` means STOP.

## Stage -1 reachability (pilot 2018-06-01..2020-12-31, 10 tickers, both engines, 10 horizons)
Command: `measure_arms.py --stage pilot --knob RUNNER_STRUCTURE_EXIT=progress_stall --knob RUNNER_STALL_RANGE_MAX=1.00 --preregistration <prereg> --out ...-progress-stall-pilot.json`, then `validate_component.py --stage reachability --arms ...-progress-stall-pilot.json --title "v123 progress_stall" --window pilot`.

| c | baseline N | component N | changed outcomes | verdict |
|---|---|---|---|---|
| 1.00 | 439 | 439 | 0 | refused:zero-diff |

Both commands exited 1 with `refused:zero-diff -- the component reached no trade. Budget intact.`

Stages 0, 1, 2, 3 were not run per the stop rule: no selection arms, MDE, walk-forward, permutation test or VALIDATION.

## Observations
- On the pilot slice, the most active registered setting of progress_stall fired on none of 439 paired trades. For comparison, hl_trail at its most active setting (b=0.0) changed 2 of 439 on the same pilot slice.
- This is a pilot-only measurement (10 tickers, 2018-06..2020-12); the pre-registration defines it as the reachability test and says zero changed outcomes refuses the arm. No parameter, window or slice was altered or re-run.
- The pre-registration's V123-10 disclosure already noted progress_stall at c=1.0 changed 0 outcomes on the v74 fixture; the pilot is consistent with that.

## Environment notes
- Production Postgres (watchlist) is unreachable here, so `cached_universe()` was replaced by a scratchpad wrapper listing the 75 CSVs in the main checkout's `data/backtest_cache` (via `BACKTEST_CACHE_DIR`), same approach as V123-0 and hl_trail. Repo code unchanged. The wrapper needs a `__main__` guard on Windows (spawned workers re-import it); a first attempt without it died with BrokenProcessPool before producing output and was re-run once with the guard (no outcome existed from it).
- The pilot log is git-ignored.
