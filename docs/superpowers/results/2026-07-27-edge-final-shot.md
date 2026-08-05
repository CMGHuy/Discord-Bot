# Task E92: The single 2024-2025 shot

**Pre-registered, run ONCE.** The 2024-2025 window has already been spent
once, on round-1 out-of-sample validation (`swingbot/core/validation_registry.json`,
built by `scripts/run_backtest_range.py --emit-registry` against the
`VALIDATION = ("2024-01-01", "2025-12-31")` window). This run is that
window's one deliberate reuse, for the pooled final system only, under
real portfolio-level constraints (heat/sector caps, same-ticker dedup,
the live throttle) rather than the per-signal view the registry measures.
The numbers below are reported as-is, whatever they say — gates that fail
are not re-run or "adjusted."

## System config

- `git rev-parse HEAD` at the time of this pre-registration: `1e529097e657168691cf697fe6dbca7f78f0ebf8`
- `docs/superpowers/results/adopted_components.json`: `{}` — Task E33's
  component-adoption grid found zero components that cleared the
  pre-registered fold gate, so "the full system" is identical to the
  plain baseline (no component flags layered on top). This also means
  `--full`'s only functional effect (`overrides = {}` instead of parsing
  `--component-json`) is moot in `--portfolio` mode, which never reads
  component overrides at all (`collect_portfolio_signals` has no such
  parameter) — `--full` is included below only for documentation fidelity
  to how this task is described in the plan; it does not change behavior.

## Exact command

```bash
python scripts/wf_run.py --full --portfolio --window 2024-01-01:2025-12-31 \
    --json docs/superpowers/results/2026-07-27-edge-final-shot.json \
    --r-sequence-json data/replay_r_sequence.json \
    --once-guard docs/superpowers/results/2026-07-27-edge-final-shot.md \
    >> docs/superpowers/results/2026-07-27-edge-final-shot.md
```

`--window`/`--once-guard` are new flags added in commit `1e52909` to make
this task's "run ONCE" rule self-enforcing: `--once-guard` refuses to run
(no work done) if this same file already has a `## Result` section, and
the run's own output is appended straight into this file under exactly
that heading — so a second invocation against this same command is a
hard refusal, not a discipline reminder. Estimated wall-clock: on the
order of ~60 minutes, scaled from Run 1's (Task E89) ~88 minutes for a
3-year (2021-2023) portfolio replay down to this run's 2-year window.

## Gates (pinned down before running)

1. **Pooled `expectancy_r` > 0 after frictions** — mean of the result's
   `r_multiples_taken` list (these are the same frictions=True,
   exit_model="v2", scale_out=True r-multiples `_default_run`/Run 1 use
   throughout this plan).
2. **Portfolio max DD < 25%** — the result's `max_dd_pct` field.
3. **Per-strategy WR within 10 points of its fold results** — the
   result's new `per_strategy_wr` field (Task E92 prep, commit `1e52909`)
   against `validation_registry.json`'s pooled (`horizon=null`)
   `source="strategy"` win_rate for that same strategy, which was itself
   built from this identical 2024-2025 window's per-signal (not
   portfolio-constrained) evaluation. Reference values, pinned here
   before this run so there's no room to move the goalposts afterward:

   | Strategy            | Registry WR (n)   |
   |----------------------|-------------------|
   | Break & Retest       | 84.5% (n=148)     |
   | EMA Crossover        | 75.0% (n=36)      |
   | Elliott Wave         | 77.3% (n=75)      |
   | Fibonacci             | 82.3% (n=203)     |
   | MA Ribbon             | 78.1% (n=137)     |
   | MACD                  | 81.3% (n=123)     |
   | RSI                   | 100.0% (n=30)     |
   | RSI Divergence        | 75.8% (n=1099)    |
   | Support/Resistance   | 87.1% (n=186)     |
   | VWAP                  | 80.5% (n=77)      |
   | Volume Profile        | 83.0% (n=47)      |

   A strategy with zero trades taken by the portfolio replay (heat/sector
   caps or dedup skip every one of its signals) has no WR to compare and
   is reported as "n/a — no trades taken," not treated as a pass or fail
   on its own; it doesn't move the other strategies' individual gates,
   but is called out explicitly in the verdict for honesty about coverage.

**Verdict rule (Task E92 Step 3):** all three gates pass ⇒ proceed to
E93. Any gate fails ⇒ since `adopted_components.json` is already `{}`,
there are no separately-adopted components left to revert — a failure
here is a statement about the pooled baseline system itself in
2024-2025, not about some component layered on top of it, and will be
reported as exactly that rather than mechanically forcing the "revert a
component" language from the plan's generic Step 3 onto a case where
there's nothing to revert. No re-runs, no adjusted second attempt either
way.

---

## SUPERSEDED by plan v8 Task V24 — recorded 2026-08-05 (V24 Step 1)

**This shot and plan v8's V24 are the same shot.** Two plans each reserved
"the one permitted reuse" of this window, which is exactly how a one-shot
budget gets spent twice by two sessions that never talk to each other. It is
recorded here, in the artifact the guard reads, rather than only in v8's plan
file.

- **E92 is retired.** It is not cancelled work and it is not debt: the
  measurement it describes is now V24's to make, under V24's rules.
- **The window changed.** E92 pre-registered `2024-01-01..2025-12-31`. A
  human-partner directive on 2026-08-03 widened V24's window to
  **`1999-01-01..2026-08-03`**, which **swallows TRAIN** — so the headline
  from that run is an **in-sample** number over ~90% of its span, and V24 Step
  2 carries a mandatory full / in-sample / out-of-sample decomposition.
  **Adoption reads the out-of-sample row (`2024-01-01..2026-08-03`), never the
  headline.** The gate tables above are E92's, fitted to E92's window; they do
  not transfer unexamined to the wider one.
- **When the run happens, its output belongs under this file's `## Result`
  section**, per V24 Step 3 — one artifact telling the whole story of the
  window's two spends.

**Do not add a `## Result` heading to this file for any other purpose.**
`wf_run.py --once-guard` refuses to run when this file already has one, so
writing that heading by hand — as a placeholder, a stub, or a note — silently
converts the guard from "runs once" into "never runs again", and the failure
mode is a *no-op that looks like a pass*.

**Firing status as of 2026-08-05: NOT FIRED, and not currently justified.**
`git diff HEAD` on this file was empty and it had no `## Result` section when
V24 Step 1 was executed, confirming E92 never ran. V17 and V52 both terminated
with an **empty adopted set**, so there is no adopted config for this window to
validate — firing it now would measure shipped defaults and spend the reuse on
a question nobody asked. Plan v8 records that **V24 must not be fired without
an explicit human decision.**
