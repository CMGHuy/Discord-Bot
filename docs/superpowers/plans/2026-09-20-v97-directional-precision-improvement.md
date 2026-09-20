# Stock trade-plan precision improvement

**Bump:** none (this document is a research and implementation roadmap; child implementation plans declare their own release level)
**Edge:** expectancy (selection and entry first; exit work is a separate harvest experiment)
**Status:** Planned; no production snapshot, experiment, or deployment performed.
**Basis:** User decisions in the September 20 brainstorming conversation and inspection of the current backend.

## Agreed outcome and boundaries

- Individual stocks in the production watchlist only. Exclude ETFs, CFDs, and other instruments. Benchmark ETFs may still supply market context; they are not trade candidates.
- LONG buys shares; SHORT borrows shares. Use explicit broker-neutral execution and borrowing assumptions.
- Baseline is the actual production configuration and software revision, not repository defaults. Its values have not been inspected or verified in this session.
- A win is positive net P&L on the entire completed position, aggregating partial and final exits after costs. Every closed position counts, including scratches and timeouts. Zero net P&L is not a win.
- Aim for at least 75% net-profitable positions separately for LONG and SHORT. This is aspirational, not a hard release threshold or a promised result.
- Statistically supported improvement below 75% may qualify. Statistical power determines the detectable improvement; do not manufacture a sample-size target from the desired result.
- Preserve average net profit per trade and require independent evidence of profitability for each promoted direction.
- Retain at least 75% of baseline actionable-plan volume separately for LONG and SHORT. WATCH notices do not count. Do not increase alerts by splitting one opportunity into repeated plans.
- If a candidate fails profitability, precision, or volume requirements, reject it and retain current behavior. Do not loosen thresholds or silently pause a direction.
- Each direction qualifies independently. One passing direction can progress while a failing direction keeps its existing behavior; neither direction can borrow the other's evidence.
- Cover selection/entry first, measurement integrity as its prerequisite, and exits subsequently. Compare completed daily and completed intraday confirmation separately.
- Allow WATCH -> confirmed actionable plan within a frozen expiry window. Expired, invalidated, or unconfirmed watches do not become actionable alerts.
- This roadmap authorizes no orders or production deployment. The bot remains a paper-trade alert system. No further user questions are needed to author the plan.

## Current evidence and constraints

Verified code observations, not claims of measured performance lift:

1. `scanning/confidence.py:_expectancy_adjustment` uses an assumed 50% win rate with insufficient history and accepts empirical history at five closed trades. Isolated execution reproduced a +1 adjustment at 2:1 RR with zero history. `scanning/analyze.py` supplies confidence-level history rather than a direction-specific profitability estimate.
2. `planning/quality.py:rs_points` and `breadth_points` reward high RS and breadth without direction adjustment. Isolated execution returned RS points 0 at percentile 10 and 8 at percentile 90. Their influence on final issuance must be traced under the production flags before claiming a trading impact.
3. `scanning/strategy_pass.py` builds from completed daily bars. `planning/builders.py` sets market entries ACTIVE at that bar's close, and the strategy pass logs the trigger as entry. This creates stale-price risk when issuance occurs later. The path is opt-in; production enablement is unknown.
4. `scanning/scan_run.py` runs confluence before the strategy pass. The strategy pass opens the first eligible candidate when the ticker has no open trade. Candidate order can affect which opportunity wins the slot.
5. `backtesting/acceptance.py` currently defines wins over win/loss outcomes only. `ArmTrade` lacks direction and pairs by entry date; both are insufficient for this study's directional tests and delayed entries.
6. The live runner and daily simulator intentionally diverge on same-session post-TP1 exits. Keep this explicit; do not silently change the simulator or quote its results as intraday execution parity.

Respect `docs/claude/backtest-methodology.md`. In particular, do not rerun closed v33/v34/v49/v68/v82/v84/v88/v90/v93 hypotheses under new labels. The v93 bearish-arm experiment rejected all seven tested bullish-only masks. Do not enable them to meet SHORT volume.

Dependencies: inspect the delivered state of v87 intraday archiving and issuance timestamps before extending it; reuse v92 harvest work for exits; respect v86's still-open cohort test and its fixed stopping rule. A plan file's presence does not prove implementation, deployment, data coverage, or a running job.

## Evaluation contract

Create a versioned study contract before selecting candidates. Retain the existing acceptance API and historical outcome labels; introduce explicit new metrics rather than redefining past reports.

For each direction and experimental arm, report:

- Unique underlying opportunities, WATCH events, actionable plans, actual simulated fills, closed positions, open/censored positions, expiries, invalidations, and rejection reasons.
- Net profitable-position rate = closed positions with net P&L > 0 divided by all closed positions.
- Mean net R on all closed positions under a common fixed initial-risk budget. Also report comparable dollar P&L, mean winner/loser R, drawdown, exposure, and costs. Position sizing is frozen so increasing size cannot manufacture preserved profit.
- TP1-touch rate as a separate diagnostic, never as the primary win metric.
- LONG/SHORT x source x strategy x horizon breakdowns, raw and baseline-mix-standardized results, evidence dates, and confidence intervals. Sparse cells remain unknown; do not fit a separate rule to every cell.

Use stable opportunity IDs including ticker, direction, source/setup identity, horizon, and signal timestamp. Separate opportunity ID, plan ID, and fill time. Pair delayed entries by their original opportunity, not their changed entry date. Compare all baseline opportunities, including those the candidate rejects; matching only common fills conceals selection effects.

Admission rules for each promoted direction:

1. Net profitable-position rate improves with a pre-registered one-sided test at 5%, adjusted for the actual family of confirmatory hypotheses. Use ticker-cluster resampling and a date-block sensitivity check for shared market shocks; document how overlap across long horizons is handled.
2. Mean net R is positive, with a one-sided 95% lower bound above zero. Its candidate-minus-baseline difference must also have a nonnegative lower confidence bound. This is deliberately stricter than the legacy -0.01R non-inferiority margin because the user selected preservation of average profit. Inadequate power is inconclusive, not a pass.
3. Unique actionable plans are at least 75% of the frozen baseline count for that direction over the same opportunity window. Report fill counts separately. A zero baseline denominator is not a pass; establish an evaluable baseline first.
4. Selection-only experiments retain the existing geometry protections and removed-population mechanism check where applicable. Delayed-entry experiments explain their changed realized geometry and retain payoff safeguards; exit experiments use a separately registered harvest gate.
5. Walk-forward stability, permutation checks, missing-data checks, and live/replay parity must pass. Apply the repository's fold consistency requirements to the new win metric, with sufficient direction-specific power rather than pooled sample sufficiency.
6. The fixed cost-stress case preserves positive expectancy and shows no mean-profit regression against its equally stressed baseline. Report sensitivity even when nominal results pass.

Seventy-five percent win rate is a progress indicator, not a threshold used to select dates, tickers, or stopping times. Report point estimates and uncertainty. Do not call the target achieved merely because a small sample crosses it.

## Work sequence

### Task P1: Freeze the production baseline and inspect observability

**Edge:** none (integrity).

Create a sanitized manifest containing production code revision, effective non-secret flags, stock-only watchlist snapshot, source modes, horizon masks, entry/exit policies, session calendar, risk sizing, cost settings, and snapshot time. Use an authorized export or explicitly authorized read-only production access when implementation reaches this task; selecting production as the baseline is not permission to SSH or read secrets. Do not substitute `.env.example` if the snapshot is unavailable.

Inventory available plan/trade outcomes, issuance and first-seen timestamps, corporate actions, and daily/intraday coverage. Distinguish replay of today's fixed watchlist from historical point-in-time membership: the former supports claims only about today's watchlist and has survivorship limitations.

Deliver a baseline report and hashes of all inputs. Resolve data/price adjustment consistency for splits and SHORT dividend liabilities. Record baseline metrics separately by direction and source, including opt-in strategy paths actually enabled.

**Exit criterion:** reproducible baseline manifest, coverage matrix, and reconciled position-level results. Missing production data blocks production-relative claims, but not offline tooling work.

### Task P2: Implement the study metric and replay audit

**Edge:** none (integrity).

Add a versioned position-result adapter and study acceptance module beside `backtesting/acceptance.py`. Extend study records with direction, source, signal/issuance/fill timestamps, opportunity ID, and cost components. Keep old public metrics unchanged and label the new metric clearly.

Reconcile leg quantities and cash flows to final net position P&L. Separate not-triggered opportunities from filled positions; never drop a losing timeout because its legacy outcome label is not `loss`. Use complete follow-up for the maximum tested holding horizon or explicit censoring rules frozen before scoring. Do not remove still-open losing candidates selectively.

Broker-neutral starting assumptions: retain the existing configured slippage and commission model as the anchor; pre-register a 2x friction stress. For SHORT, propose annual borrow-rate scenarios of 1%, 5%, and 15%, with 5% nominal and 15% stress, accruing on daily outstanding short market value; include dividends owed. These are transparent study assumptions, not measured broker quotes. If availability/recall data are absent, label stock SHORT results conditional on borrow availability; missing availability is never represented as confirmed borrowable.

**Tests:** scaled-out winners with losing runners; net-negative TP1 touches; profitable and losing timeouts; exact-zero net P&L; missing costs; SHORT sign conventions/dividends; direction isolation; delayed-entry pairing; censoring; immutable legacy metrics.

**Exit criterion:** reconciled accounting and reliable measurement of the user-selected objective, with no edge claim from accounting changes alone.

### Task P3: Correct execution timing in a shadow candidate

**Edge:** none (integrity), followed by a separately measured expectancy candidate.

Trace `strategy_pass.py`, `builders.py`, `plan_manager.py`, `scan_run.py`, and their replay counterparts under the frozen production flags. Track signal time, issuance time, first eligible fill time, and the data available at each decision. Do not record a previous bar's close as an executable later fill.

Introduce a shared causal execution adapter: completed-bar signals may first fill on the next eligible observation, with adverse friction. No same-bar high/low fill inferred from a signal known only at that bar's close. Recompute realized entry-to-stop risk and target RR; expire or invalidate opportunities outside a pre-registered entry envelope. Freeze stops/targets/exits for this experiment; do not move targets merely to rescue RR.

Maintain both the existing-production ledger and a consistently executable replay of its rules. Apply the same accounting and execution assumptions to baseline and candidate when claiming selection lift. Quantify corrections separately so removal of optimistic baseline fills is not advertised as a new edge.

**Tests:** overnight gap through target/stop; delayed scan; stale quote; same-bar ambiguity; LONG/SHORT symmetry; daylight-saving/session boundaries; idempotent fills; restart recovery. Name each live rule's replay counterpart and disclose unavoidable divergence.

**Exit criterion:** executable, timestamped shadow plans with traceable live/replay differences; no automatic production change.

### Task P4: Test confidence reliability and candidate selection

**Edge:** expectancy.

First trace which scores actually change alert admission, deduplication, or sizing under the baseline. Do not spend a validation shot on an observational score with no behavioral effect.

Evaluate separately: (a) insufficient-evidence confidence remains neutral instead of gaining assumed-expectancy points; (b) direction-conditioned empirical net-R evidence with shrinkage and an unknown state; (c) collect-then-rank candidate issuance instead of incidental source/iteration priority. Use fixed risk and unchanged exits. Preserve WEAK and research visibility; do not silently suppress them or change their ledger meaning.

Direction-aware RS/breadth is an offline diagnostic initially. Reversing a LONG bonus does not prove a SHORT benefit, and the closed bullish RS experiment is not reopened. Any behavioral candidate must state its distinct mechanism and measurement budget before selection.

Build calibration tables from fold-train data only. Report future-fold reliability by score band and direction. Do not label heuristic scores as probabilities. No ML imports enter the live backend.

**Tests:** zero-history neutrality; missing evidence; no future journal information; direction/source separation; deterministic candidate ordering; one-position-per-ticker policy; conflicting LONG/SHORT candidates; preserved research records.

**Exit criterion:** one frozen eligible candidate per registered comparison, or a recorded negative/inconclusive result. Do not combine individually unproven components into a single opaque score.

### Task P5: Compare daily and intraday confirmation

**Edge:** expectancy.

Reuse v87's archive and coverage reporting if delivered. Candidate resolutions are completed daily, 15-minute, and 5-minute bars; exact trigger, expiry, invalidation, session policy, maximum entry drift, and experiment family are frozen using fold-train data before held-out scoring. Missing intraday history is a data prerequisite, never a reason to synthesize intraday bars from daily OHLC.

Scope the mechanism to one confirmation window per baseline opportunity, with no repeated re-arming. Entry must improve executability or location while preserving the required volume. This is not a rerun of v88/v90: explicitly compare the proposed rule against their test/reaction/cooldown mechanics before registering it; if materially equivalent, stop and record that no new experiment is justified.

Represent WATCH separately from executable PENDING/ACTIVE plans. WATCH creates no paper fill, occupies no position, and counts toward neither actionable volume nor win-rate denominators. Persist CONFIRMED, EXPIRED, INVALIDATED, and SUPERSEDED outcomes with reasons, and make transitions idempotent across restart/repeated scans. Suppress duplicate Discord notices through an explicit delivery policy.

Compare immediate baseline, daily confirmation, and intraday confirmation on the same covered opportunity population, with the same costs, exit policy, trading hours, and available information. Report daily full-coverage results separately rather than claiming superiority from different market periods. Repeated watches cannot inflate volume as they did in prior armed-entry work.

**Tests:** truncation/no-lookahead; incomplete bar rejection; next-observation fill; expiry in exchange sessions; invalidation before trigger; gaps; missing bars; restart/deduplication; matched coverage; 75% volume test per direction.

**Exit criterion:** frozen timing rule supported by matched evidence, or no change. Prospectively collect data when historical coverage is insufficient; do not declare an intraday winner prematurely.

### Task P6: Validate and run a prospective paper comparison

Use the MDE precheck, fold-train selection, parameter-stability checks, and anchored walk-forward structure already documented. Treat 2024-2025 as tainted for selection. Check every hypothesis against the closed-registration ledger; only a genuinely new hypothesis may use its explicitly registered one-shot validation budget. If that window cannot provide defensible evidence for this study, freeze the candidate and use a prospectively collected holdout.

Daily and intraday arms require honest matched coverage; a daily-history backtest cannot validate an intraday trigger. Pre-register sample requirements, maximum observation window, missing-data policy, multiplicity adjustment, and stopping rule. When underpowered, report inconclusive; do not inspect repeatedly until p < 0.05.

Run shadow baseline and candidate under identical capital/exposure constraints. Keep incumbent alerts unchanged during measurement. Record disagreement cases and hypothetical fills without counting them as live orders. Directional releases are independent; only the passing direction is eligible, and it must retain its own volume floor.

**Deliverables:** signed-off data manifest, frozen candidate parameters, full directional results, uncertainty, cost sensitivity, rejected populations, parity report, and PASS/FAIL/INCONCLUSIVE decision. Do not claim 75% win rate without its actual evidence.

### Task P7: Extend to exits after entry research

**Edge:** harvest.

Inspect the actual state of v92 before duplicating adaptive-trail or stall-exit work. Reuse its implemented measurement and gate where compatible; do not rerun a closed result. Hold the chosen entry policy fixed and measure one exit mechanism at a time, retaining this study's net-position win definition, directional profitability, and volume requirements.

Stops, TP1/TP2, scale-out, breakeven, and time exits may change only through their own registered harvest experiment. Test same-session runner behavior with suitable intraday evidence; reconcile or explicitly version the intentional daily/live divergence. Prefer improved realized net R over artificial TP1-touch inflation.

**Exit criterion:** a separately accepted exit policy or an explicit retain-current-policy result. Entry improvements do not depend on an exit experiment succeeding.

### Task P8: Verify, release selectively, and monitor

Each child implementation uses an isolated branch, focused tests during development, and the full suite once as its final verification task. Use `scripts/dev/testrun.py`; add tests for economically meaningful failures rather than mirroring implementation. Documentation-only delivery runs formatting/link/consistency checks, not the backend suite.

Keep policy versions and issuance-time evidence immutable on plans. Show WATCH versus actionable state, data age, actual entry envelope, invalidation, targets, costs, sample size, and uncertainty. A quality score is not a win probability.

Default candidate flags off until the corresponding directional gate passes and production rollout is explicitly authorized. Preserve a reversible configuration rollback and the frozen incumbent baseline. Pre-register monitoring windows and review triggers for execution drift, missing prices/borrow assumptions, profit deterioration, and volume retention; do not silently loosen the gate or disable a direction.

## Recommended first implementation slice

P1 baseline capture plus P2 position-level evaluation, then P3 executable-entry shadowing. This is the minimum trustworthy foundation for selection/entry research, not a switch to an accounting-only project. Continue directly into P4 and P5 once it can measure their effects. P7 follows; no improvement is promised until its own evaluation passes.

## Completion of this planning task

The roadmap is complete when it preserves all user choices, identifies concrete code seams and existing research dependencies, separates integrity work from hypothesized edge, and defines falsifiable directional acceptance criteria. Implementation, production access, historical sweeps, and rollout remain future work; this document does not report them as completed.
