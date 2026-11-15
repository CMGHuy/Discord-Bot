# v229 — Deferred-entry counterfactual: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V229-5" -A 400 <part file>`); never read a part whole.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-14-v229-deferred-entry-counterfactual-design.md](../specs/2026-11-14-v229-deferred-entry-counterfactual-design.md)
**Brief:** `.superpowers/briefs/2026-11-15-v229-deferred-entry-counterfactual.md`

## Goal

The production LONG book since 2026-10-01 shows a striking cell: trades
entered from 15:30 ET onward made +0.672R on N=35, while entries at the open
and midday sat near zero, and 54% of longs close the day they open at -0.382R.
With stops near 0.35 ATR, an early market entry has the whole session's noise
to survive. The cell is small and was picked from many slices, so it is a
lead, not evidence, and the usual route cannot test it: the Stage -2 screen
races daily bars, where the session a plan was issued in does not exist, and
the 5-minute archive only starts on 2026-06-23.

This plan builds the instrument the spec designs and runs it twice on the
bot's **own live plans**. For each LONG market plan issued before 15:30 ET it
races three arms over the same 5-minute bars with one simulator: the control
(the trade as filled), arm A (enter at the 15:30 bar's open, stop and TP1 kept
at the plan's distances) and arm B (as A, but skip when price touched the
original stop before 15:30). Every arm is priced net of frictions, the
deferred arms at double entry slippage. Per plan the deltas `d_A = R_A - R_C`
and `d_B = R_B - R_C` are averaged and given week-clustered bootstrap bounds;
a path-class agreement table against the live outcomes decides whether the
simulator is calibrated at all. Each pair, with a tradeability record a
follow-on would need (shifted levels, overnight gaps, the 15:30 bar, plan
validity, event days, entry-bar stop-outs), is appended once to
`data/v229/pairs.jsonl` on the VM, so a verdict never re-derives twelve weeks.

Once shipped, the rule is frozen by a committed pre-registration (its commit
timestamp is `T0`), one exploratory read checks calibration on plans closed
before `T0`, a weekly VM cron appends forward pairs and prints a count, and
one verdict is computed after the twelve complete ISO weeks following `T0`
have passed their five-session mark (about late February 2027 if `T0` lands
in November 2026). A `PASS` earns a follow-on entry-mode spec, bound to
`Edge: expectancy` and the partner's explicit screen approval; anything else
closes the question in `backtest-methodology.md` § Closed pre-registrations.

What it leaves alone: every alert, plan, order form, lifecycle message and
the partner's resting orders; every replay, backtest and screen path; every
VALIDATION and holdout window; the bot process (the cron runs a report
script only); `scripts/ops/export_book_rows.sh` (read, never edited). Success
is a calibrated exploratory read, a forward log that grows weekly without a
restart losing a pair, and one verdict row in the pre-registration ledger
that `ledger_qvalues` can score with the other ideas.

## Architecture

- **One CLI, one helper package.** `scripts/reports/deferred_entry_counterfactual.py`
  is the spec's script (modes `append`, `exploratory`, `verdict`). Its logic
  lives in `scripts/reports/deferred_entry/` (package precedent:
  `scripts/reports/autopsy/`), one module per concern so each task owns one
  file and one test file:
  - `bars.py` — the time basis: reads the archive CSV itself with UTC parsing
    (never `data_store.load_normalized`), derives 15:30 ET per date through
    `zoneinfo`, the five-session horizon through `nyse_calendar()`.
  - `simulate.py` — the single-leg race, mirroring
    `exit_sim._single_leg_exit_walk`'s round-1 rule on 5-minute bars, plus a
    gap-through-stop fill via `instrument.fills.gap_stop_fill`.
  - `arms.py` — arms C, A, B; distance-preserving levels; frictions through
    `screen.sides.net_r` in this one place; refuses zero frictions.
  - `tradeability.py` — the disclosure record and the event-day flags.
  - `pairs.py` — reads the export CSV **by column name**, classifies every
    trade into the population funnel, assembles one pair dict.
  - `pairlog.py` — append-once JSONL with torn-tail recovery.
  - `analysis.py` — arm summaries, week-clustered deltas, calibration table,
    per-week and split deltas.
  - `verdict.py` — the frozen constants and their hash, the forward window,
    the verdict guard and the ledger-token mapping.
  - `report.py` — the results Markdown and JSON.
- **VM wiring.** `scripts/ops/v229_pairs_cron.sh` runs the export on the host
  into `/opt/swing-bot/data/v229/rows.csv`, then the CLI in the bot container
  in `append` mode; `scripts/ops/install_v229_cron.sh <T0>` installs it weekly.
- **Data flow.** export CSV -> `pairs.read_export` -> `pairs.classify` (funnel)
  -> `pairs.build_pair` (`arms.price_arms` -> `simulate.race`;
  `tradeability.record`) -> `pairlog.append_pair` -> (`exploratory` /
  `verdict` mode) `analysis.*` -> `verdict.study_verdict` -> `report.*`.

## Global Constraints

- **Time basis:** archive bars are stamped with their **start**, UTC offsets explicit; export `opened_at`/`closed_at` are UTC text. Parse both with `pd.to_datetime(..., utc=True)`. 15:30 ET is derived per entry date with `ZoneInfo("America/New_York")` and converted to UTC. Never `data_store.load_normalized`, `load_from_disk` or `cache_path` (it creates directories) on a read path.
- **Population:** `row_kind == "trade"`, `direction == "bullish"` for the verdict (bearish computed and printed only), `entry_type == "market"` (a missing `entry_type` is counted `entry_type_unknown`, never assumed), `opened_at` in a regular NYSE session and before 15:30 ET, bars from `opened_at` to the end of the fifth session after it.
- **Arms:** C fills at the trade's `entry`, raced from the first bar starting at or after `opened_at`; A fills at the open of the first bar starting at or after 15:30 ET on the entry date; B as A, skipped (0R) when any bar starting at or after `opened_at` and **strictly before** the 15:30 bar traded at or below the plan's original stop. A and B keep the stop and TP1 **distances**.
- **Race (frozen):** single leg to TP1; stop checked before target in a bar; stop moves to the fill once price reaches `BREAKEVEN_TRIGGER_FRACTION` (0.5) of the TP1 distance and protects later bars only; a stop hit fills at `gap_stop_fill(bar_open, stop, direction)`; open at the end of the fifth session after entry is marked to that bar's close. No runner, no TP2; disclosed in every output.
- **Frictions:** every arm's R is `net_r(entry, price, risk, direction="long"|"short", days=..., entry_bps=...)` from `swingbot/core/backtesting/screen/sides.py`, called once per arm and nowhere else. Control: default entry slippage. A and B: `entry_bps = 2 * config.SLIPPAGE_BPS`. `SLIPPAGE_BPS <= 0` or `commission_r() <= 0` is refused. Gross R printed beside, gating nothing.
- **Statistic:** per plan `d_A`, `d_B`; mean per plan with skipped B plans at 0R; `week_cluster_bootstrap(baseline=R_C items, component=R_A|R_B items, mean-difference)`, items are objects with `.entry_date` (the ET entry date), 10,000 resamples, seed `WEEK_BOOTSTRAP_SEED` (42). One-sided 97.5% lower bound = `np.percentile(draws, 2.5)`; one-sided `p = (draws <= 0).mean()`. Fewer than 2 distinct ISO weeks: no interval (the script enforces it; the bootstrap does not).
- **Calibration:** 3x3 path-class table (`loss`/`scratch`/`win`) of simulated control against live outcome; agreement < 0.80 is `UNCALIBRATED` and no verdict is issued.
- **Verdict per arm:** `PASS` when forward mean delta >= +0.10R, lower bound > 0 and calibrated; else `NO-LIFT`. Study: fewer than 300 forward LONG pairs or fewer than 10 week clusters is `UNDERPOWERED` (closed like a fail). Ledger `p` = min(1.0, 2 x the smaller arm's one-sided p).
- **Freeze:** nothing in the forward rule changes after the exploratory read; every pair row carries `rule_hash` of `verdict.FROZEN`, and the verdict refuses a log with a different or mixed hash.
- **No production writes beyond the spec's:** the archive `market_data/5min` exists only on the VM and is read-only. VM work goes through `bash scripts/ops/ssh-hetzner.sh` only; writing `data/v229/` and installing or removing the cron are production changes and run under the `mirror-prod` skill. No task deploys: the script reaches the bot image through the partner's next routine `/deploy`.
- **Long runs checkpoint:** the pair log is the checkpoint, one line per finished trade, flushed and fsynced; a restart skips ids present and redoes a torn last line.
- **Tests:** new test files under `tests/scripts/` (suite `tooling`, no `tests/suites.toml` edit); synthetic 5-minute frames with `tz="UTC"` stamps through `tests/scripts/v229_fixtures.py`; one real archive slice at `tests/fixtures/v229/5min/AAPL.csv`. No database. Verification is `python scripts/dev/testrun.py file <test>`; no task runs the full suite (CI does).
- **Complexity < 15** on every new function (`scripts/dev/complexity_gate.py` scans `scripts/` and `tests/`); table-drive arm and direction differences.
- **Soft ordering against plan v228** (`docs/superpowers/plans/2026-11-14-v228-intraday-excursion_0-index.md`, unimplemented): no hard dependency either way. v228 appends export column 39 (`excursion_source`): v229 reads by name and works on 38 or 39 columns. v228 makes `autopsy/rows.load_rows` refuse an older CSV: v229 never imports it. v228 captures `tests/fixtures/v228/archive/5min/AAPL.csv`: v229 captures its own one-session slice so neither waits for the other. v229 edits neither `export_book_rows.sh`, `tests/suites.toml` nor `complexity_baseline.json`.
- **Do not commit from a writer; the implementer commits per task** in the plan's worktree; V229-12..15 run on `main` after V229-1..11 are merged.

## Parallelisation

Every code task owns one module and one test file; the shared names below are
fixed in the ledger, so tests can build their inputs by hand.

- **V229-1 first** (creates the package `__init__.py`, the fixture helper and the `DATA_READERS` rows every later task's tests rely on).
- **After V229-1, in parallel:** V229-2 (simulate), V229-6 (pairlog), V229-7 (analysis), V229-8 (verdict), V229-11 (cron scripts). Disjoint files; analysis and verdict consume only the pair-dict and stats-dict shapes fixed in the ledger, not code.
- **Sequential edges (contract):** V229-3 needs V229-2 (`simulate.race`, `Race`). V229-4 needs V229-3 (`ArmResult`). V229-5 needs V229-3 and V229-4 (`arms.price_arms`, `tradeability.record`, `tradeability.event_flags`). V229-9 needs V229-7 and V229-8 (renders their dicts). V229-10 needs V229-1..9 (wires every module).
- **Sequential edges (operations):** V229-12 (freeze) needs V229-1..11 merged on `main` and the script present in the VM's bot image. V229-13 (exploratory read) needs V229-12 committed (`T0`). V229-14 (cron) needs V229-13 calibrated. **V229-15 (verdict) cannot run until `verdict.verdict_open_date(T0)`**, the first date after the fifth session following the window's last session; it is scheduled as blocked, never as work available now.
- At most 2 implementers at once (session rule).

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V229-1 | Package and time basis | 1 | sonnet | C `scripts/reports/deferred_entry/__init__.py`, C `scripts/reports/deferred_entry/bars.py`, C `tests/scripts/v229_fixtures.py`, C `tests/scripts/test_deferred_entry_bars.py`, C `tests/fixtures/v229/5min/AAPL.csv`, M `scripts/dev/select_tests.py` | `bars.ET`, `bars.DEFER_AT = time(15, 30)`, `bars.BAR_MINUTES = 5`; `class ArchiveError(ValueError)`; `load_bars(bars_dir, ticker) -> pd.DataFrame \| None` (Open/High/Low/Close/Volume, tz-aware UTC index of bar starts, sorted; None when the file is missing; `ArchiveError` when unreadable or naive); `to_utc(text: str) -> pd.Timestamp`; `et_date(ts) -> dt.date`; `et_time(ts) -> dt.time`; `session_open(d) -> pd.Timestamp` (09:30 ET in UTC); `deferral_start(d) -> pd.Timestamp \| None` (15:30 ET in UTC; None on early-close or non-session days); `horizon_end(d, sessions=5) -> pd.Timestamp \| None` (UTC close of `nyse_calendar().session_after(d, sessions)`); `archive_last_bar(bars_dir) -> str \| None` (ISO, max over files' last lines); fixture helper `v229_fixtures.five_min(days, *, base=100.0, overrides=None) -> pd.DataFrame` and `write_bars(dir, ticker, frame) -> Path`; `DATA_READERS` rows for `data/v229/` and `tests/fixtures/v229/` |
| V229-2 | Single-leg race on 5-minute bars | 1 | opus | C `scripts/reports/deferred_entry/simulate.py`, C `tests/scripts/test_deferred_entry_simulate.py` | `@dataclass(frozen=True) Race(outcome: str, exit_price: float \| None, exit_ts: pd.Timestamp \| None, gap_stop: bool, stop_moved: bool)`, outcome in `win/loss/scratch/timeout/no_bars`; `race(bars, *, direction, fill, stop, tp1, start, end, be_fraction=BREAKEVEN_TRIGGER_FRACTION) -> Race` (bars with `start <= index < end`); `gross_r(race, *, direction, fill, risk) -> float` |
| V229-3 | Arms C, A, B with frictions | 1 | opus | C `scripts/reports/deferred_entry/arms.py`, C `tests/scripts/test_deferred_entry_arms.py` | `ARMS = ("C", "A", "B")`; `class FrictionsError(RuntimeError)`; `assert_frictions() -> None`; `shifted_levels(fill, *, entry, stop, tp1) -> tuple[float, float]`; `held_touched(bars, *, direction, stop, start, deferral) -> bool`; `deferral_bar(bars, deferral, close) -> pd.Series \| None` (first bar with `deferral <= index < close`, `.name` its start); `@dataclass(frozen=True) ArmResult(arm, taken, fill, stop, tp1, outcome, r_net, r_gross, exit_ts: str \| None, gap_stop: bool)` with `to_dict()`; `price_arms(bars, *, direction, entry, stop, tp1, opened_at, deferral, close, end) -> dict[str, ArmResult]` |
| V229-4 | Tradeability record and event flags | 1 | sonnet | C `scripts/reports/deferred_entry/tradeability.py`, C `tests/scripts/test_deferred_entry_tradeability.py` | `event_flags(ticker, entry_date, *, earnings_lookup=None) -> dict` keys `earnings_after_close: bool \| None`, `monthly_opex: bool`, `fomc: bool`, `event_day: bool`; `entry_bar_stopout(bars, *, opened_at, closed_at, live_reason) -> bool`; `plan_expired(plan_created_at, expiry_bars, entry_date) -> tuple[bool \| None, int \| None]`; `record(bars, *, direction, entry, stop, tp1, opened_at, deferral, arms, plan_created_at, expiry_bars, closed_at, live_reason, flags) -> dict` with keys `fill_vs_entry_r, fill_above_entry, shifted_stop_above_day_low, day_low, day_low_vs_stop_r, price_1530_vs_entry_r, first_gap_r{C,A,B}, bar_1530{volume, range_r, open_vs_last_close_r}, plan_expired, sessions_since_plan, entry_bar_stopout` plus the four flag keys |
| V229-5 | Export reader, funnel and pair assembly | 1 | opus | C `scripts/reports/deferred_entry/pairs.py`, C `tests/scripts/test_deferred_entry_pairs.py` | `REQUIRED_COLUMNS` (tuple of export names); `REASONS = ("not_trade", "not_market", "entry_type_unknown", "bad_levels", "outside_session", "close_bucket", "no_coverage", "pending", "no_deferral_bar", "eligible")`; `read_export(path) -> list[dict[str, str]]` (DictReader, `ValueError` naming missing columns); `classify(row, bars, *, archive_end) -> str`; `build_pair(row, bars, *, rule_hash, earnings_lookup=None) -> dict` (PAIR shape below) |
| V229-6 | Append-once pair log | 2 | sonnet | C `scripts/reports/deferred_entry/pairlog.py`, C `tests/scripts/test_deferred_entry_pairlog.py` | `DEFAULT_LOG = "data/v229/pairs.jsonl"`; `class PairLogError(ValueError)`; `read_pairs(path) -> dict[str, dict]` (missing file -> `{}`; torn last line truncated and dropped; malformed earlier line -> `PairLogError`); `append_pair(path, pair) -> None` (duplicate `trade_id` -> `PairLogError`; one line, flush, fsync; parents created) |
| V229-7 | Statistics and calibration | 2 | opus | C `scripts/reports/deferred_entry/analysis.py`, C `tests/scripts/test_deferred_entry_analysis.py` | `live_class(reason) -> str \| None`; `sim_class(outcome) -> str \| None`; `arm_summary(pairs, arm) -> dict` keys `n, taken, wins, win_rate, exp_r, total_r, exp_r_gross`; `delta_stats(pairs, arm, *, n_resamples=10_000, seed=WEEK_BOOTSTRAP_SEED) -> dict` keys `arm, n, weeks, mean, lower, p` (`lower`/`p` None under 2 weeks); `delta_over_taken(pairs, arm) -> dict` keys `n, mean`; `calibration(pairs) -> dict` keys `table{sim{live:int}}, n, agreement, calibrated, excluded, mean_r_c, mean_live_r, spearman`; `weekly_deltas(pairs) -> list[dict]` keys `week, n, d_a, d_b`; `split_deltas(pairs) -> dict` keys `fill_above, fill_below, with_events, without_events` (each `{n, d_a, d_b}`); `skip_summary(pairs) -> dict` keys `skipped, control_r_of_skipped` |
| V229-8 | Frozen rule, window and verdict guard | 2 | opus | C `scripts/reports/deferred_entry/verdict.py`, C `tests/scripts/test_deferred_entry_verdict.py` | `FROZEN: dict` (the rule constants); `LEDGER_ID = "v229-deferred-entry"`; `rule_hash() -> str` (16 hex chars); `class VerdictRefused(RuntimeError)`; `forward_window(t0: pd.Timestamp) -> tuple[dt.date, dt.date]`; `phase(entry_date: dt.date, t0) -> str` (`exploratory/forward/after`); `verdict_open_date(t0) -> dt.date`; `guard(*, today, t0, ledger_rows, pairs) -> None`; `arm_verdict(delta, calibrated) -> str`; `study_verdict(*, deltas, calibration, n_pairs, weeks) -> dict` keys `study, arms{A,B}, ledger{verdict, n, exp_r, p}`; `exploratory_close(calibration, n_pairs) -> dict \| None` |
| V229-9 | Results Markdown and JSON | 2 | sonnet | C `scripts/reports/deferred_entry/report.py`, C `tests/scripts/test_deferred_entry_report.py` | `build_payload(*, phase, t0, pairs, bearish, funnel, close_bucket, archive_last_bar, git_sha, verdict=None) -> dict`; `render_markdown(payload) -> str` |
| V229-10 | The CLI | 2 | sonnet | C `scripts/reports/deferred_entry_counterfactual.py`, C `tests/scripts/test_deferred_entry_counterfactual.py` | `main(argv=None) -> int`; flags `--mode {append,exploratory,verdict}`, `--rows`, `--bars-dir` (default `market_data/5min`), `--pairs-log` (default `data/v229/pairs.jsonl`), `--t0` (required, ISO UTC), `--out-dir` (default `data/v229`), `--ledger` (default `stats.LEDGER_PATH`), `--today` (default UTC today); `append` prints one line `v229 pairs: appended <a>, total <t>, forward <f>`; outputs `<out-dir>/exploratory.{md,json}` and `<out-dir>/forward-verdict.{md,json}` |
| V229-11 | Weekly VM cron scripts | 3 | haiku | C `scripts/ops/v229_pairs_cron.sh`, C `scripts/ops/install_v229_cron.sh`, C `tests/scripts/test_v229_cron_scripts.py` | `install_v229_cron.sh <T0>` (MARKER `# v229 deferred-entry pairs`), runner writes `/opt/swing-bot/data/v229/rows.csv` and appends to `/opt/swing-bot/logs/v229-pairs.log` |
| V229-12 | Freeze: pre-registration and T0 | 3 | sonnet | C `docs/superpowers/results/<date>-v229-preregistration.md` | `T0` = that doc's first commit timestamp (`git log --diff-filter=A -1 --format=%cI -- <doc>`), appended to the doc in its own follow-up commit |
| V229-13 | Exploratory read (VM, read-only archive) | 3 | sonnet | C `docs/superpowers/results/<date>-v229-exploratory-read.md`, C `docs/superpowers/results/v229/exploratory.json`; only if `UNCALIBRATED`: M `docs/superpowers/results/preregistration-ledger.jsonl`, M `docs/claude/backtest-methodology.md` | `data/v229/pairs.jsonl` on the VM seeded with exploratory pairs |
| V229-14 | Install the weekly cron | 3 | haiku | VM crontab (via `mirror-prod`); M `docs/superpowers/results/<date>-v229-preregistration.md` (cron install line and first weekly count) | first weekly count printed: thresholds locked |
| V229-15 | Forward verdict (blocked until `verdict_open_date(T0)`) | 3 | opus | C `docs/superpowers/results/<date>-v229-forward-verdict.md`, C `docs/superpowers/results/v229/forward-verdict.json`, M `docs/superpowers/results/preregistration-ledger.jsonl`, M `docs/claude/backtest-methodology.md` (non-PASS), VM crontab entry removed (via `mirror-prod`) | ledger row `v229-deferred-entry` |

### Shared shapes

**PAIR** (one `pairs.jsonl` line, JSON-serialisable; built by `pairs.build_pair`, read by `analysis`, `verdict`, `report`):

```python
{
    "trade_id": "t-123", "ticker": "AAPL", "direction": "bullish",
    "opened_at": "2026-11-03T15:02:10+00:00", "entry_date": "2026-11-03",
    "iso_week": "2026-W45", "bucket": "open",          # "open" | "midday"
    "trade": {"entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0},
    "arms": {"C": ArmResult.to_dict(), "A": ..., "B": ...},
    # ArmResult.to_dict(): {"arm", "taken", "fill", "stop", "tp1", "outcome",
    #                       "r_net", "r_gross", "exit_ts", "gap_stop"}
    "live": {"reason": "loss", "outcome": "loss", "r_realized": -1.02},
    "tradeability": tradeability.record(...),          # keys per V229-4
    "coverage": {"bars_from": "...", "bars_to": "...", "deferral_bar": "..."},
    "rule_hash": "0123abcd4567ef89",
}
```

**DELTA** (`analysis.delta_stats`): `{"arm": "A", "n": int, "weeks": int, "mean": float | None, "lower": float | None, "p": float | None}`.

**CALIBRATION** (`analysis.calibration`): `{"table": {"loss": {"loss": 0, "scratch": 0, "win": 0}, "scratch": {...}, "win": {...}}, "n": int, "agreement": float | None, "calibrated": bool, "excluded": int, "mean_r_c": float | None, "mean_live_r": float | None, "spearman": float | None}`; outer key = simulated class, inner = live class.

**FROZEN** (`verdict.FROZEN`): `{"defer_et": "15:30", "hold_sessions": 5, "window_weeks": 12, "floor_r": 0.10, "lower_pct": 2.5, "calibration_min": 0.80, "min_pairs": 300, "min_weeks": 10, "resamples": 10000, "seed": 42, "be_fraction": 0.5, "deferred_entry_bps_mult": 2}`.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-15-v229-deferred-entry-counterfactual_1-core.md` | V229-1..V229-5 | time basis, simulator, arms, tradeability, export reader and pair assembly |
| 2 | `2026-11-15-v229-deferred-entry-counterfactual_2-analysis.md` | V229-6..V229-10 | pair log, statistics and calibration, frozen rule and guard, report, CLI |
| 3 | `2026-11-15-v229-deferred-entry-counterfactual_3-operations.md` | V229-11..V229-15 | cron scripts, freeze, exploratory read, cron install, forward verdict |

## Handoff

Resolutions of the brief's "differs" verdicts and other places where the plan
departs from the spec's wording. Each follows the code or an existing
precedent; the partner or `/panel` may overrule any of them.

1. **`net_r` call shape.** The spec writes `net_r(entry, price, risk, direction=..., entry_bps=...)`. The real signature (`screen/sides.py:39`) takes `direction="long"|"short"` (not `bullish`) and a required `days=`. Arms map `bullish -> "long"`, `bearish -> "short"`; longs pass `days=0` (never read), shorts pass the sessions held (`nyse_calendar().sessions_between(entry_date, exit_date)`), so borrow cost applies to the bearish disclosure exactly as the screen applies it.
2. **Freeze and verdict in the ledger (v226 precedent).** The ledger is append-only and `append_ledger_row` refuses a duplicate id, so "a row before the read, later carrying a verdict" cannot be an in-place edit. v226, the precedent for a live-book study, froze its rule in a committed document and appended **one** row at the close. v229 does the same: the freeze is the pre-registration doc's commit (`T0`); no ledger row is written until the study closes; then exactly one row, id `v229-deferred-entry`, `instrument: "v1"` (no live-book value exists in `INSTRUMENTS`; v226 used `v1`). The spec's study words have no ledger tokens and none are added: `UNCALIBRATED -> INCONCLUSIVE` (the spec's own word: "closes the read as inconclusive"), `UNDERPOWERED -> NO-LIFT` ("closed like a fail"), `PASS -> PASS`, `NO-LIFT -> NO-LIFT`; the study word is written into the row's `hypothesis` text and the results doc. The row's verdict is `PASS` when either arm passes (the passing arms named in the record), its `p` is `min(1.0, 2 x min(p_A, p_B))` (`_checked_p` refuses > 1), `n` the forward LONG pairs and `exp_r` the mean delta of the arm with the smaller p. An exploratory `UNCALIBRATED` close writes the same id with `INCONCLUSIVE`, `n` the exploratory pairs, `exp_r` and `p` null. "Refuses a second verdict once the row carries a verdict" becomes: `verdict.guard` refuses when the ledger already holds `LEDGER_ID` (and `append_ledger_row` refuses a duplicate as a second line of defence). `data_source` is omitted (optional; the 5-minute archive's provider is not one row value).
3. **"Thresholds cannot change after the first weekly count."** Enforced by `rule_hash` (sha256 of `json.dumps(FROZEN, sort_keys=True)`, first 16 hex) on every pair row; `verdict.guard` refuses a log whose rows carry a hash other than the current `rule_hash()`. The pre-registration doc quotes `FROZEN` and its hash.
4. **Bootstrap.** `week_cluster_bootstrap` does not refuse a one-week book and clusters on `item.entry_date` of objects. `analysis.delta_stats` builds `SimpleNamespace(entry_date=<ET entry date>, r=<arm net R>)` items, counts distinct `iso_week_key`, and returns `lower = p = None` under 2 weeks or with no pairs, before calling `np.percentile`.
5. **Simulator.** `_single_leg_exit_walk` is private and takes a `TradePlanV2` and daily bars. `simulate.race` mirrors its rule on 5-minute bars and adds the gap-through-stop fill (`gap_stop_fill(bar_open, stop, direction)`) on every stop hit; `gap_stop` is recorded only when the hit bar opens a session and its open is beyond the stop. A test calls the private walk on a no-gap path and pins identical outcome and exit price (the test may import a private name; the module never does). The walk's v129 acceptance exit is inert when `acceptance_level` is None, which the parity test's plan leaves at its default.
6. **Plan expiry** is derived from the export's `plan_created_at` and `expiry_bars` as `nyse_calendar().sessions_between(created_date, entry_date) >= int(expiry_bars)`, not from `views._sessions_left` or `trade_why._expires_on` (private, plan objects).
7. **Export read by column name** (`csv.DictReader`, `pairs.REQUIRED_COLUMNS` checked), never `autopsy/rows.load_rows`: works on today's 38 columns and v228's 39.
8. **Package, not one file.** The spec's "one script" is the CLI entry point; its helpers sit in `scripts/reports/deferred_entry/` (the `autopsy/` precedent) so no file or task outgrows its cap. Behaviour is unchanged.
9. **Live path class** comes from the export's `last_leg_reason` (falling back to `close_reason`), lower-cased, matching the live writer (`plan_manager.py`): starts with `tp1` -> `win`; `scratch` -> `scratch`; `loss` or `stop` -> `loss`; anything else (`manual`, `reversed`, `stall_exit`, `time_exit`, empty) is excluded from the 3x3 and counted `excluded`. A simulated `timeout` is excluded likewise. The export carries only the last leg, so a TP1 partial whose runner leg is labelled `scratch` would class as `scratch`; disclosed in every output.
10. **`pending` beside `no_coverage`.** A forward trade whose fifth-session close lies after the archive's last bar is `pending`: not logged, recounted by the next run. `no_coverage` is a missing file or a missing session inside the horizon once the archive has passed it.
11. **Coverage rule, made exact:** every NYSE session from the entry date to the fifth session after it has at least one bar, and a bar starts at or after `horizon_end - 15 minutes`. A half day inside the horizon is fine; a half day **on the entry date** is `no_deferral_bar`, as is a session without a bar in `[15:30 ET, close)`.
12. **Outputs land on the VM first.** The CLI writes `exploratory.{md,json}` / `forward-verdict.{md,json}` under `data/v229/`; V229-13 and V229-15 copy them into `docs/superpowers/results/` (dated Markdown, JSON under `results/v229/`). Each output records the archive's last bar and the script's git SHA (`git rev-parse HEAD` on the host checkout, passed in by the task; `unknown` when absent).
13. **T0 is an input.** The script cannot read its own freeze commit on the VM, so `--t0` is required in every mode and the cron installer bakes it into the crontab line. V229-12 records `T0` in the pre-registration doc in a follow-up commit (the v212 `observed_n` precedent).
14. **Deploy precondition.** The cron and the reads run the script from the bot image. No task deploys; V229-12 stops and asks the partner for the routine `/deploy` when `docker compose exec -T bot test -f scripts/reports/deferred_entry_counterfactual.py` fails on the VM. `Bump: none` stands (no bot behaviour changes).
15. **Bearish disclosure** pairs are computed in memory in `exploratory` and `verdict` modes and never logged (the log holds eligible plans only).

## OPEN

- Trades opened in the forward window but still **open** at the verdict date are not in the export (it joins closed journal entries), so they are absent from the verdict population and cannot be counted. With 54% of longs closing the same day and the verdict five sessions past the window, the gap is small but non-zero; the verdict doc discloses it as a limitation. A fix would edit `export_book_rows.sh`, which this plan does not touch.
- Item 9's single-leg export limitation could understate the `win` class in calibration; V229-13 prints the excluded and `scratch` counts so the partner can judge before the forward read starts.
