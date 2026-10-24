# v182 — Part 5: the descriptive blocks, the counts note and the two shots

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md) — Part C (descriptive blocks, the event count before the shot, the two shots), Part B (3 × repricing and `null_unfilled` printed), § The long side stays untouched.
**Index:** [2026-10-21-v182-short-screen-range-breakdown_0-index.md](2026-10-21-v182-short-screen-range-breakdown_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Worktree:** `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` (created in V182-1). Every command below runs from that worktree's root.

**Tasks:** V182-17..V182-21, strictly sequential. V182-17 needs V182-16 (shared `screen_idea.py`, `descriptive.py`, `test_screen_idea.py`); V182-18 needs every code change committed and both A/A docs on disk (V182-8, V182-12); V182-19 → V182-20 → V182-21 by rule (index § Parallelisation).

**Long byte-identity (partner rule):** after V182-17's own narrow run, also run both golden regression files from V182-1 and expect them green:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Never edit the golden files to make a test pass. A long or next-open idea without `control`/`family` must leave `screen_ticker`, `summarise` and `render_results` exactly as they were: nothing new is computed for it and no new section is rendered.

**The cache lives only in the main tree.** `data/backtest_cache_ext/` is gitignored, so the worktree has none. Every real-cache command in this part (the counts, the two shots) passes `--cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext` (v140 precedent). The membership CSV is tracked; the worktree's copy is used. Never fetch into any cache from this plan.

**The guardrail hook reads every Bash line that names the screen script.** Never wrap a screen command in quotes, `bash -c`, a heredoc or an ssh string; the hook denies a line it cannot tokenise, and a deny is the rule (screen skill Step 6). Commit messages in this part never quote a screen command line.

**Contracts from earlier parts this part consumes** (index ledger):

- V182-3: `Idea.direction`, `Idea.entry`, `Idea.levels`, `Idea.control` (callable or `None`), `Idea.family` (tuple of idea names, `()` by default).
- V182-9: `race.LEVEL_SLIPPAGE_FACTOR = 2.0`, `race.REPRICE_SLIPPAGE_FACTOR = 3.0`.
- V182-11: `TickerScreen` fields `null_slots`, `null_unfilled`, `depths` (`{"event": [...], "null": [...]}` or `None`), `repriced` (rows `{"entry_date", "r_event", "r_null"}` or `None`); `_event_rows(ticker, index, kept, null_mean_r, entry_offset=1)`; `_ENTRY_OFFSET = {"next_open": 1, "level": 0}`; `raw_levels(idea, df)`; `_books(idea, ticker, df, ctx, costs, exclude=None, level_factor=race.LEVEL_SLIPPAGE_FACTOR)` reading `ctx.get("levels")`; `_level_report(...)` splatted into the `TickerScreen(...)` call. V182-11 renders none of these; V182-17 does.
- V182-14/15: `IDEAS["range_breakdown_close"]` (`entry="next_open"`) and `IDEAS["range_breakdown_stop"]` (`entry="level"`), both `direction="short"`, `control=control_events`, `family=("range_breakdown_close", "range_breakdown_stop")`.
- V182-16: `screen_idea.ticker_context(idea, df, spans, context=None) -> dict` (keys `raw`, `member`, `warm`, `atr`, `trend`, `levels`); `screen_idea._null_pool(idea, ctx, exclude=None)`; `descriptive.depth_summary(values) -> dict`; `render_counts`'s depth-table row text (`| events | 3 | 0.125 | 0.250 | 0.375 | 33.3% |`) and its `_cell` helper; `--count-only` (refuses non-default windows, `--tickers` and context ideas; never loads the ledger); module-level `CLOSE`, `STOP`, `_universe_fixture`, `_argv`, `_write_csv` in `tests/backtest_scripts/test_screen_idea.py`.

---

# Phase C2 — the descriptive blocks, the count, the shots

### Task V182-17: Descriptive blocks: overlap, trend-only control, SPY regime split, 3 ×, unfilled

**Model:** opus — adds a second book (the control) and a new data input (SPY) to the one path every screen runs, and the long and plain next-open paths must stay byte-identical while the short results doc gains five blocks.

**Files:**
- Modify: `swingbot/core/backtesting/screen/descriptive.py` (append after `check_fill_depth`)
- Modify: `tests/backtesting/screen/test_descriptive.py` (append)
- Modify: `scripts/backtest/screen_idea.py` (`TickerScreen` as V182-11 left it; `screen_ticker` as V182-16 left it; `render_results`; `main`; new helpers beside `_control`/`_overlap` above `screen_ticker` and beside `with_diagnostics`)
- Modify: `tests/backtest_scripts/test_screen_idea.py` (append)

**Interfaces:**
- Consumes: everything listed under **Contracts** in this part's header; `null.member_mask` output and `race.warm_mask` output as held in `ctx["member"]`, `ctx["warm"]`; `screen_idea._spy_calendar(cache_dir, end)` (exists, :228; raises `screen_context.ContextError` when `SPY.csv` is missing); `indicators.sma(values, n)` (exists); `verdict.decide`, `verdict.Verdict` (exist); `screen_idea._fmt`, `_share` (exist).
- Produces:
  - `descriptive.SPY_SMA = 200`.
  - `descriptive.event_overlap(own, other) -> dict` — keys `own`, `other`, `both` (bar counts); `ValueError` on unequal lengths.
  - `descriptive.spy_above_200(spy: pd.DataFrame) -> pd.Series` — bool, `Close > SMA200(Close)`, only on bars where the SMA exists.
  - `descriptive.paired_delta(rows) -> tuple[int, float | None]` — `(n, mean(r_event − r_null))`, `(0, None)` for no rows.
  - `descriptive.regime_split(events, above) -> dict` — `{"above": (n, mean_d), "below": (n, mean_d), "unknown": n}`; the regime is read at the last SPY session strictly before each row's `entry_date`.
  - `TickerScreen` appended after V182-11's fields: `control: list | None = None` (rows of the trend-only control book, as `_event_rows` builds them), `overlap: dict | None = None` (`event_overlap` counts against the family partner).
  - `screen_idea._family_partner(idea) -> Idea | None`, `_overlap(idea, df, ctx) -> dict | None`, `_control(idea, ticker, df, ctx, costs) -> list | None`.
  - `screen_idea.with_short_blocks(summary, screens, idea, spy) -> dict` — returns `summary` itself (the same object) unless `idea.direction == "short"` or `idea.entry == "level"`; otherwise `{**summary, "short": block}` with block keys `partner`, `overlap`, `control` (a `Verdict` or `None`), `regime`, `repriced` (a `Verdict` or `None`), `depths` (`{"event": depth_summary, "null": depth_summary}` or `None`), `slots` (`(null_slots, null_unfilled)` or `None`).
  - `screen_idea._spy_step(args, idea) -> tuple[pd.DataFrame | None, str | None]` — `(None, None)` for an idea without short blocks; a refusal reason when SPY cannot load.
  - `screen_idea._render_short_blocks(idea, summary, run) -> list`, `_depth_row(label, summary) -> str`.
- Consumed by: V182-19 and V182-20 (the two results docs carry these blocks).

**What each block is (spec Part C "Descriptive blocks", Part B repricing and `null_unfilled`); none gates, none enters the verdict:**

- **Event overlap.** For an idea whose `family` names a registered partner: on member and warm bars, the idea's raw event bars, the partner's raw event bars, and the bars both flag. The doc prints both shares. No race is involved; `raw_events(partner, df, None)` is the partner's own frozen `events()`.
- **Trend-only control.** For an idea with `control`: the same `_books` call (same race, same direction, same entry mode and levels, same matched-null method and seed) over `idea.control(df)` instead of `idea.events(df)`. Its ΔExpR and week-clustered interval are printed with the idea's ΔExpR minus the control's.
- **SPY regime split.** The event pairs split by SPY's close against its 200-day SMA at the last close before entry: the signal close for a next-open entry, bar t−1 for a level entry. Both are known when the order is placed, so the split reads no later bar. A short or level idea's run refuses before screening when `SPY.csv` cannot load, so the one-shot doc never lacks the block.
- **Level only:** the fill-depth table (events and filled null), the null slots and `null_unfilled` share, and the book repriced at `REPRICE_SLIPPAGE_FACTOR` × base entry slippage with its change against the 2 × book. These render V182-11's `depths`, `null_slots`, `null_unfilled` and `repriced`.

- [ ] **Step 1: Write the failing tests in `tests/backtesting/screen/test_descriptive.py`** (append)

```python
# --- v182 V182-17: results-doc blocks (descriptive, never gating) ------------
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from tests.backtesting.screen.helpers import frame  # noqa: E402


def test_event_overlap_counts_each_side_and_the_shared_bars():
    own = np.array([True, True, False, False, True])
    other = np.array([True, False, True, False, True])
    assert descriptive.event_overlap(own, other) == {"own": 3, "other": 3, "both": 2}


def test_event_overlap_of_a_nested_pair_shares_every_inner_bar():
    own = np.array([True, False, True, False])
    other = np.array([True, True, True, False])
    assert descriptive.event_overlap(own, other) == {"own": 2, "other": 3, "both": 2}


def test_event_overlap_refuses_unequal_lengths():
    with pytest.raises(ValueError):
        descriptive.event_overlap(np.ones(3, dtype=bool), np.ones(4, dtype=bool))


def test_spy_above_200_starts_where_the_average_exists():
    assert descriptive.SPY_SMA == 200
    spy = frame([100.0] * 200 + [101.0, 99.0, 100.0])
    above = descriptive.spy_above_200(spy)
    # SMA200 at bars 199..202: 100, 100.005, 100, 100 (integer sums, exact)
    assert above.index.equals(spy.index[199:])
    assert above.tolist() == [False, True, False, False]


def _r(day, r_event, r_null):
    return {"entry_date": day, "r_event": r_event, "r_null": r_null}


def test_paired_delta_is_the_mean_event_minus_null():
    assert descriptive.paired_delta([_r("2015-01-06", 1.0, 0.5), _r("2015-01-07", -1.0, 0.0)]) \
        == (2, -0.25)
    assert descriptive.paired_delta([]) == (0, None)


def test_regime_split_reads_the_last_spy_close_before_entry():
    above = pd.Series([True, False, True],
                      index=pd.to_datetime(["2015-01-05", "2015-01-06", "2015-01-07"]))
    rows = [_r("2015-01-06", 1.0, 0.5),     # last close before: 01-05, above
            _r("2015-01-10", 0.0, 0.25),    # a Saturday: 01-07, above
            _r("2015-01-07", -1.0, 0.0),    # 01-06, below (never the entry day's own close)
            _r("2015-01-05", 2.0, 0.0)]     # no SPY close before: unknown
    assert descriptive.regime_split(rows, above) == {
        "above": (2, 0.125), "below": (1, -1.0), "unknown": 1}


def test_regime_split_of_no_events():
    above = pd.Series([True], index=pd.to_datetime(["2015-01-05"]))
    assert descriptive.regime_split([], above) == {
        "above": (0, None), "below": (0, None), "unknown": 0}
```

- [ ] **Step 2: Write the failing tests in `tests/backtest_scripts/test_screen_idea.py`** (append after the V182-16 `--count-only` tests; `CLOSE`, `STOP`, `_universe_fixture`, `_argv`, `_write_csv`, `_fixed_doc_inputs`, `_short_probe`, `ALWAYS`, `random_walk`, `verdict`, `IDEAS` are already in the file)

```python
# --- v182 V182-17: short-side blocks in the results doc ---------------------

from swingbot.core.backtesting.screen import descriptive  # noqa: E402

_COSTS = {"slippage_bps": None, "commission": None}


def test_a_long_or_familyless_idea_gets_no_control_and_no_overlap():
    df = random_walk(2600)
    for idea in (IDEAS["turn_of_month"], _short_probe()):
        out = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
        assert out.control is None and out.overlap is None, idea.name


def test_with_short_blocks_returns_a_long_summary_itself():
    df = random_walk(2600)
    out = screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS)
    summary = screen_idea.summarise([out])
    assert screen_idea.with_short_blocks(summary, [out], IDEAS["turn_of_month"], None) is summary


def test_books_runs_once_for_a_long_idea_and_once_more_for_a_control(monkeypatch):
    calls = []
    real = screen_idea._books

    def spy(*args, **kwargs):
        calls.append(args[0].name)
        return real(*args, **kwargs)

    monkeypatch.setattr(screen_idea, "_books", spy)
    df = random_walk(2700, seed=7)
    for idea in (IDEAS["turn_of_month"], CLOSE, STOP):
        screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert calls.count("turn_of_month") == 1
    assert calls.count("range_breakdown_close") == 2      # the book + the control
    assert calls.count("range_breakdown_stop") == 3       # the book + 3 x repricing + the control


def test_the_control_is_the_same_book_over_the_control_events():
    df = random_walk(2700, seed=7)
    out = screen_idea.screen_ticker(CLOSE, "AAA", df, ALWAYS)
    ctx = screen_idea.ticker_context(CLOSE, df, ALWAYS)
    flags = CLOSE.control(df).reindex(df.index, fill_value=False).to_numpy(dtype=bool)
    kept, _, draw = screen_idea._books(CLOSE, "AAA", df, {**ctx, "raw": flags}, _COSTS)
    assert out.events and out.control                                  # non-vacuous
    assert out.control == screen_idea._event_rows("AAA", df.index, kept, draw.null_mean_r)


def test_a_level_control_enters_on_its_event_bar():
    df = random_walk(2700, seed=7)
    out = screen_idea.screen_ticker(STOP, "AAA", df, ALWAYS)
    days = set(df.index[STOP.control(df).to_numpy(dtype=bool)].strftime("%Y-%m-%d"))
    assert out.control
    assert {row["entry_date"] for row in out.control} <= days


def test_overlap_counts_the_partner_raw_bars_on_member_warm_bars():
    df = random_walk(2700, seed=7)
    out = screen_idea.screen_ticker(CLOSE, "AAA", df, ALWAYS)
    ctx = screen_idea.ticker_context(CLOSE, df, ALWAYS)
    population = np.asarray(ctx["member"], dtype=bool) & np.asarray(ctx["warm"], dtype=bool)
    stop_raw = np.asarray(screen_idea.raw_events(STOP, df, None), dtype=bool)
    assert out.overlap == descriptive.event_overlap(ctx["raw"] & population,
                                                    stop_raw & population)
    # Nested by construction: a close below S is a bar whose low is below S.
    assert out.overlap["both"] == out.overlap["own"] > 0
    assert screen_idea._family_partner(CLOSE) is STOP
    assert screen_idea._family_partner(IDEAS["turn_of_month"]) is None


def test_with_short_blocks_pools_every_block_for_a_level_idea():
    df = random_walk(2700, seed=7)
    screens = [screen_idea.screen_ticker(STOP, t, df, ALWAYS) for t in ("AAA", "BBB")]
    summary = screen_idea.summarise(screens)
    spy = random_walk(2900, seed=9, start="2009-06-01")
    out = screen_idea.with_short_blocks(summary, screens, STOP, spy)
    block = out["short"]
    assert out["verdict"] is summary["verdict"]
    assert block["partner"] == "range_breakdown_close"
    assert block["overlap"] == {k: sum(s.overlap[k] for s in screens)
                                for k in ("own", "other", "both")}
    assert block["control"].n == sum(len(s.control) for s in screens)
    assert block["repriced"].n == len(summary["events"])
    assert block["regime"] == descriptive.regime_split(summary["events"],
                                                       descriptive.spy_above_200(spy))
    assert block["slots"] == (sum(s.null_slots for s in screens),
                              sum(s.null_unfilled for s in screens))
    assert block["depths"] == {
        "event": descriptive.depth_summary([d for s in screens for d in s.depths["event"]]),
        "null": descriptive.depth_summary([d for s in screens for d in s.depths["null"]])}


def test_a_next_open_short_has_no_level_blocks():
    df = random_walk(2700, seed=7)
    screens = [screen_idea.screen_ticker(CLOSE, "AAA", df, ALWAYS)]
    block = screen_idea.with_short_blocks(screen_idea.summarise(screens), screens, CLOSE,
                                          None)["short"]
    assert block["partner"] == "range_breakdown_stop" and block["control"] is not None
    assert block["regime"] is None
    assert (block["depths"], block["slots"], block["repriced"]) == (None, None, None)


def _v(delta, low, high, n=500):
    return verdict.Verdict("SCREEN-FAIL", n, delta, low, high, 0.25, 5, {}, {})


def _short_block(**extra):
    block = {"partner": "range_breakdown_stop",
             "overlap": {"own": 400, "other": 1000, "both": 400},
             "control": _v(0.0125, -0.0375, 0.0625),
             "regime": {"above": (120, 0.25), "below": (280, -0.0625), "unknown": 3},
             "depths": None, "slots": None, "repriced": None}
    block.update(extra)
    return block


SHORT_BLOCK_TEXT = [
    "## Short-side blocks (descriptive, never gating)",
    "",
    "**Event overlap** with `range_breakdown_stop` (raw event bars on member, warm bars): "
    "400 of 400 `range_breakdown_close` bars (100.0%) are also `range_breakdown_stop` bars; "
    "400 of 1000 `range_breakdown_stop` bars (40.0%) are also `range_breakdown_close` bars. "
    "Nested ideas are two looks at one hypothesis: read both results docs together "
    "(family of two, BH q above).",
    "",
    "**Trend-only control** (`control_events`: the idea's trend and first-break clauses, no "
    "range clauses; same race, same matched null): N = 500, ΔExpR +0.0125R, 95% "
    "week-clustered interval -0.0375R to +0.0625R. The idea's ΔExpR minus the control's: "
    "+0.0187R. A pass whose ΔExpR is not clearly above the control is not credited to the "
    "range.",
    "",
    "**SPY regime split** (SPY close vs its 200-day average at the last close before entry):",
    "",
    "| SPY | N | ΔExpR |",
    "|---|---|---|",
    "| above its 200-day average | 120 | +0.2500R |",
    "| below its 200-day average | 280 | -0.0625R |",
    "",
    "Events with no SPY average before entry: 3.",
]


def test_short_blocks_render_overlap_control_and_regime():
    _, summary, _, run = _fixed_doc_inputs()      # the idea's ΔExpR is 0.031234567
    summary = {**summary, "short": _short_block()}
    assert screen_idea._render_short_blocks(CLOSE, summary, run) == SHORT_BLOCK_TEXT


def test_short_blocks_render_the_level_blocks_for_a_level_idea():
    _, summary, _, run = _fixed_doc_inputs()
    block = _short_block(
        partner="range_breakdown_close", overlap=None, control=None, regime=None,
        depths={"event": descriptive.depth_summary([0.0, 0.25, 0.5]),
                "null": descriptive.depth_summary([0.0, 0.25, 0.296875, 0.5])},
        slots=(100, 20), repriced=_v(-0.0125, -0.0625, 0.0375))
    lines = screen_idea._render_short_blocks(STOP, {**summary, "short": block}, run)
    assert lines == [
        "## Short-side blocks (descriptive, never gating)",
        "",
        "**SPY regime split:** not computed (no SPY frame).",
        "",
        "**Fill depth** (ATR14[t−1] below the bar's open; 0 = a gap fill at the open):",
        "",
        "| depth (ATR14[t−1]) | n | q1 | median | q3 | gap fills |",
        "|---|---:|---:|---:|---:|---:|",
        "| events | 3 | 0.125 | 0.250 | 0.375 | 33.3% |",
        "| null fills | 4 | 0.188 | 0.273 | 0.348 | 25.0% |",
        "",
        "**Null slots:** 100; unfilled 20 (20.0%); an event with no filled null is dropped "
        "as `dropped_no_match`.",
        "",
        "**Repriced at 3.0 x base entry slippage** (15.0 bps on the entry fill, events and "
        "null): ΔExpR -0.0125R, 95% week-clustered interval -0.0625R to +0.0375R; change vs "
        "the 2.0 x book -0.0437R. Printed, never gating.",
    ]


def test_an_empty_depth_summary_renders_dashes():
    empty = descriptive.depth_summary([])
    assert screen_idea._depth_row("null fills", empty) == "| null fills | 0 | – | – | – | – |"


def test_render_results_appends_the_short_blocks_after_the_drift():
    _, summary, universe, run = _fixed_doc_inputs()
    text = screen_idea.render_results(CLOSE, {**summary, "short": _short_block()}, universe, run)
    assert "\n\n" + "\n".join(SHORT_BLOCK_TEXT) + "\n" in text
    assert text.index("## Forward drift") < text.index("## Short-side blocks")
    plain = screen_idea.render_results(CLOSE, summary, universe, run)
    assert "Short-side blocks" not in plain


def test_a_short_dry_run_prints_the_short_blocks(tmp_path, capsys):
    cache, membership = _universe_fixture(tmp_path)
    _write_csv(cache / "SPY.csv", random_walk(2900, seed=9, start="2009-06-01"))
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run",
                                  "--tickers", "AAA,BBB", idea="range_breakdown_stop")) == 0
    out = capsys.readouterr().out
    for needle in ("## Short-side blocks (descriptive, never gating)",
                   "**Event overlap** with `range_breakdown_close`",
                   "**Trend-only control**", "**SPY regime split** (", "**Fill depth**",
                   "**Null slots:**", "**Repriced at 3.0 x base entry slippage**"):
        assert needle in out, needle
    assert not (tmp_path / "results").exists()


def test_a_short_run_without_spy_is_refused_before_screening(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(screen_idea, "screen_universe", lambda *a, **k: pytest.fail("screened"))
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run", "--tickers", "AAA",
                                  idea="range_breakdown_close")) == 2
    assert "SPY regime split (v182) cannot load SPY" in capsys.readouterr().err


def test_a_long_run_needs_no_spy(tmp_path):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run",
                                  "--tickers", "AAA")) == 0
```

- [ ] **Step 3: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_descriptive.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
```

Expected: FAIL — `AttributeError: module '...descriptive' has no attribute 'event_overlap'` (and `spy_above_200`, `paired_delta`, `regime_split`, `SPY_SMA`); `TickerScreen` has no `control`; `screen_idea` has no `with_short_blocks`, `_family_partner`, `_render_short_blocks`, `_depth_row`; the SPY refusal test exits 0. `test_a_long_run_needs_no_spy` and `test_a_long_or_familyless_idea_...` fail only on the missing attributes.

- [ ] **Step 4: Implement the maths in `swingbot/core/backtesting/screen/descriptive.py`** (append; add `import pandas as pd` and `from swingbot.core.backtesting.screen import indicators` to the imports)

```python
#: SPY's regime average, in bars (spec Part C: "SPY above/below its 200-day average").
SPY_SMA = 200


def event_overlap(own, other) -> dict:
    """Bars flagged by each idea and by both (spec Part C: the two ideas are nested)."""
    own, other = np.asarray(own, dtype=bool), np.asarray(other, dtype=bool)
    if own.shape != other.shape:
        raise ValueError(f"event_overlap needs equal-length flags, got {own.shape} and {other.shape}")
    return {"own": int(own.sum()), "other": int(other.sum()), "both": int((own & other).sum())}


def spy_above_200(spy: pd.DataFrame) -> pd.Series:
    """SPY's close above its 200-day SMA, only on the bars where the SMA exists."""
    average = indicators.sma(spy["Close"], SPY_SMA)
    return (spy["Close"] > average)[average.notna()]


def paired_delta(rows) -> tuple[int, float | None]:
    """(n, mean(R_event - mean R_null)) of event rows; (0, None) for none."""
    d = [row["r_event"] - row["r_null"] for row in rows]
    return len(d), (float(np.mean(d)) if d else None)


def regime_split(events, above: pd.Series) -> dict:
    """The event pairs by SPY's regime at the last SPY close strictly before
    entry: the signal close for a next-open entry, bar t-1 for a level entry
    -- known when the order is placed either way. Reported, never gating."""
    index = pd.DatetimeIndex(above.index)
    flags = above.to_numpy(dtype=bool)
    groups = {"above": [], "below": [], "unknown": []}
    for row in events:
        pos = index.searchsorted(pd.Timestamp(row["entry_date"]), side="left") - 1
        groups["unknown" if pos < 0 else ("above" if flags[pos] else "below")].append(row)
    return {"above": paired_delta(groups["above"]), "below": paired_delta(groups["below"]),
            "unknown": len(groups["unknown"])}
```

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_descriptive.py` — Expected: `0 failed` (7 from V182-16 plus 9 new).

- [ ] **Step 5: Implement the books and the summary in `scripts/backtest/screen_idea.py`**

1. `TickerScreen`: append, after V182-11's `repriced` field:

```python
    control: list | None = None                           # v182: rows of the trend-only control book
    overlap: dict | None = None                           # v182: raw-bar overlap with the family partner
```

2. Above `screen_ticker`, add `_family_partner(idea)` (the first registered `IDEAS[name]` for `name in idea.family` other than `idea.name`; `None` if there is none), and:

```python
def _overlap(idea: Idea, df: pd.DataFrame, ctx: dict) -> dict | None:
    """v182: raw event bars shared with the family partner, member and warm bars only."""
    partner = _family_partner(idea)
    if partner is None:
        return None
    population = np.asarray(ctx["member"], dtype=bool) & np.asarray(ctx["warm"], dtype=bool)
    other = np.asarray(raw_events(partner, df, None), dtype=bool)
    return descriptive.event_overlap(ctx["raw"] & population, other & population)


def _control(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict) -> list | None:
    """v182: the trend-only control -- the same book (race, direction, entry
    mode, levels, matched null and seed) over idea.control(df). Never gating."""
    if idea.control is None:
        return None
    flags = idea.control(df).reindex(df.index, fill_value=False).to_numpy(dtype=bool)
    kept, _, draw = _books(idea, ticker, df, {**ctx, "raw": flags}, costs)
    return _event_rows(ticker, df.index, kept, draw.null_mean_r,
                       entry_offset=_ENTRY_OFFSET[idea.entry])
```

3. `screen_ticker`: in the `TickerScreen(...)` call, add `control=_control(idea, ticker, df, ctx, costs), overlap=_overlap(idea, df, ctx),` before V182-11's `**_level_report(...)`. No other line changes and no branch is added: a long or familyless idea returns `None` from both helpers before computing anything (the `_books` call-count test pins it).

4. Beside `with_diagnostics`, add:
   - `_needs_short_blocks(idea) -> bool`: `idea.direction == "short" or idea.entry == "level"`.
   - `_pooled(screens, name) -> list | None`: `None` when `getattr(screen, name) is None` for every screen; else every screen's rows of that field, pooled (the `_restricted_pairs` pattern).
   - `_decide(rows) -> verdict.Verdict | None`: `None` for `None`; else `verdict.decide([verdict.PairedEvent(r["entry_date"], r["r_event"] - r["r_null"]) for r in rows])` (attribute lookup on `verdict`, so the test bootstrap patch applies).
   - `_overlap_total(screens) -> dict | None`: the `own`/`other`/`both` counts summed over the screens whose `overlap` is not `None`; `None` if none has one.
   - `_level_blocks(screens) -> dict`: `{"depths": None, "slots": None}` when every `screen.depths is None`; else `{"depths": {"event": descriptive.depth_summary(<every event depth>), "null": descriptive.depth_summary(<every null depth>)}, "slots": (sum of null_slots, sum of null_unfilled)}`.
   - `with_short_blocks(summary, screens, idea, spy) -> dict`:

```python
def with_short_blocks(summary: dict, screens, idea: Idea, spy) -> dict:
    """v182: the summary plus ``"short"`` -- overlap, trend-only control, SPY
    regime split and the level blocks -- for a short or level idea; the same
    dict, untouched, for any other. The verdict object is never rebuilt."""
    if not _needs_short_blocks(idea):
        return summary
    partner = _family_partner(idea)
    regime = (None if spy is None else
              descriptive.regime_split(summary["events"], descriptive.spy_above_200(spy)))
    block = {"partner": None if partner is None else partner.name,
             "overlap": _overlap_total(screens),
             "control": _decide(_pooled(screens, "control")),
             "regime": regime,
             "repriced": _decide(_pooled(screens, "repriced")),
             **_level_blocks(screens)}
    return {**summary, "short": block}
```

5. `_spy_step(args, idea)` beside `_context_step`:

```python
def _spy_step(args, idea: Idea) -> tuple[pd.DataFrame | None, str | None]:
    """v182: a short or level idea's doc splits ΔExpR by SPY's 200-day
    regime, so SPY must load before the one shot; (None, None) otherwise."""
    if not _needs_short_blocks(idea):
        return None, None
    try:
        return _spy_calendar(args.cache_dir, args.end), None
    except screen_context.ContextError as exc:
        return None, f"SPY regime split (v182) cannot load SPY: {exc}"
```

6. `main`: after the `_context_step` block, add `spy = None` and `if reason is None: spy, reason = _spy_step(args, IDEAS[args.idea])` (before the shared `if reason:` refusal). After the `with_diagnostics(...)` line add `summary = with_short_blocks(summary, screens, idea, spy)`. The `--count-only` branch V182-16 placed before the ledger load is untouched (a count never loads SPY).

- [ ] **Step 6: Implement the rendering in `scripts/backtest/screen_idea.py`**

Helpers beside `_render_trail`, each small; `_ratio(a, b)` is `a / b if b else None`; `_fmt`, `_share` exist; `_cell` is V182-16's.

- `_depth_row(label, s) -> str`: `f"| {label} | {s['n']} | {_cell(s['q1'])} | {_cell(s['median'])} | {_cell(s['q3'])} | {gap} |"`, `gap` = `–` for `None`, else `f"{100 * s['gap_share']:.1f}%"`. If V182-16's `_check5_block` builds the same row inline, make it call `_depth_row` (its `| events | 3 | 0.125 | 0.250 | 0.375 | 33.3% |` test pins that the text did not move).
- `_render_overlap(idea, block) -> list`, `_render_control(summary, block) -> list`, `_render_regime(block) -> list`, `_render_level(summary, block, run) -> list` (its last line from `_render_repriced(summary, block, run) -> str`). Exact copy: the two render tests in Step 2, built from `block`, `summary["verdict"].delta_exp_r`, `race.REPRICE_SLIPPAGE_FACTOR`, `race.LEVEL_SLIPPAGE_FACTOR` and `race.REPRICE_SLIPPAGE_FACTOR * run["slippage_bps"]`. A difference with a `None` side prints through `_fmt` as `n/a`.
- `_render_short_blocks(idea, summary, run) -> list`: the heading `## Short-side blocks (descriptive, never gating)`, then, each preceded by one blank line: the overlap paragraph if `block["overlap"]` is not `None`; the control paragraph if `block["control"]` is not `None`; the regime block (always; the `not computed` line when `block["regime"]` is `None`); the level blocks if `block["depths"]` is not `None`.
- `render_results`: after `sections += [_render_years(v), _render_drift(summary)]` and before the context branch, add `if "short" in summary: sections.append(_render_short_blocks(idea, summary, run))`. A summary without the key renders exactly as before (`test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140` and the trail and context doc pins stay green untouched).
- Module docstring: append `v182: a short or level idea's results doc ends with the short-side blocks (event overlap with its family partner, the trend-only control, the SPY 200-day regime split, and for a level idea the fill depths, null_unfilled and the 3 x repricing) -- all printed, none gating; such a run refuses before screening when SPY.csv cannot load.`

- [ ] **Step 7: Run every touched test file, the neighbours, the goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_descriptive.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere and no complexity regression (`main` gains one `if`; `with_short_blocks`, `_render_short_blocks` and every new helper stay well under 15). The calibration tests prove the level and short A/A replicates (which call `screen_ticker` directly, never `main`) still run; `--count-only` tests from V182-16 still pass untouched.

Then one smoke on the real cache, allowed by the hook (dry run, two tickers, writes nothing):

```bash
python scripts/backtest/screen_idea.py --idea range_breakdown_stop --tickers AAPL,MSFT --dry-run --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext | tail -40
```

Expected: exit 0 and the doc ending in `## Short-side blocks (descriptive, never gating)` with the overlap, control, regime and level blocks. Read the structure only; the numbers on two tickers mean nothing and are never recorded.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/backtesting/screen/descriptive.py tests/backtesting/screen/test_descriptive.py scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_idea.py
git commit -m "feat(v182): short-side results blocks -- overlap, trend-only control, SPY regime split, fill depth, null_unfilled, 3 x repricing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-18: Outcome-blind counts for both ideas and the counts note

**Model:** sonnet — two scripted outcome-blind runs, a note assembled from their verbatim output, a fixed gate read off it, and one commit; no code changes.

**Files:**
- Create: `docs/superpowers/results/<run-date>-v182-counts.md` (`<run-date>` = the Berlin date of the run, ISO)

**Interfaces:**
- Consumes: `--count-only` and `render_counts` (V182-16); `IDEAS["range_breakdown_close"]`, `IDEAS["range_breakdown_stop"]` (V182-14/15); every code change of V182-1..V182-17 committed; the A/A docs `docs/superpowers/results/<date>-short-race-calibration.md` (V182-8) and `<date>-short-level-race-calibration.md` (V182-12).
- Produces: the committed counts note: per idea the count N and its gate line; for `range_breakdown_stop` the check 5 table, its two clause lines and its verdict. V182-19 and V182-20 read their go / no-go from it.

**Why this runs before any shot (spec Part C, "Event count before the shot"; Part B check 5):** `--count-only` computes events, member / warm-up / window drops, full-cap non-overlap and the null match, and for a level idea the fill depths. It races nothing and computes no R, so it reveals nothing about outcomes and spends no shot. The note is committed before either real run so the go / no-go was fixed before any outcome was seen.

- [ ] **Step 1: Check the preconditions**

```bash
git status --short
git log --oneline -25
ls docs/superpowers/results/*-short-race-calibration.md docs/superpowers/results/*-short-level-race-calibration.md
head -1 docs/superpowers/results/*-short-race-calibration.md docs/superpowers/results/*-short-level-race-calibration.md
grep -c '"id": "screen-range_breakdown_' docs/superpowers/results/preregistration-ledger.jsonl
ls docs/superpowers/results/ | grep -c "screen-range_breakdown_"
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
```

Expected:
- `git status --short` prints nothing; the log shows the V182-1..V182-17 commits;
- both A/A docs exist, are committed, and both titles end in `-> within the 5% false-pass limit`;
- both `grep -c` / `ls | grep -c` print `0` (neither idea has a ledger row or a results doc);
- all three test files `0 failed`.

Anything else means stop: an uncommitted change, a missing or failed A/A doc (spec: no short idea runs until both pass), or an existing row or doc for either idea (report it to the partner; never run over it).

- [ ] **Step 2: Fix the run date**

Run `date -u +%Y-%m-%dT%H:%M` and add 2 hours (Berlin summer time; Git Bash prints UTC even with `TZ` set). `<run-date>` is that Berlin day. Use it in every step below.

- [ ] **Step 3: Dispatch `backtest-runner` with the two count commands**

Dispatch the `backtest-runner` agent, naming the worktree path `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown`, with these two commands run one after the other from that worktree's root, each exactly as written (no quoting, no wrapper):

```bash
mkdir -p logs
python scripts/backtest/screen_idea.py --idea range_breakdown_close --count-only --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v182-count-range_breakdown_close.md
python scripts/backtest/screen_idea.py --idea range_breakdown_stop --count-only --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v182-count-range_breakdown_stop.md
```

The guardrail hook allows a `--count-only` line (V182-16); it writes nothing but the redirect. Progress lines (`[range_breakdown_close] 50/500 tickers (10%)`) go to the same file before the report. Ask the runner to return, per command: the exit code and everything from the `# v182 count:` line to the end of the file (`sed -n '/^# v182 count:/,$p' logs/v182-count-<idea>.md`).

Expected: exit code 0 for both; each report starts `# v182 count: \`<idea>\` (outcome-blind: no race, no R)`, carries the count table and one `**Gate:**` line; the stop idea's report also carries `## Check 5 — fill depth (outcome-blind)` and one `**Check 5:**` line. An exit code 2 (`refused: ...` on stderr) is a setup fault, not a count: fix it (wrong cache path, membership file) and run again; a refused count reads nothing and costs nothing.

- [ ] **Step 4: Write `docs/superpowers/results/<run-date>-v182-counts.md`**

Layout (fill every `<…>` from Step 1–3; paste each report verbatim except that every heading drops one level, `#` → `##` and `##` → `###`):

```markdown
# v182 outcome-blind event counts -> close <N_close> (<may run | no run>), stop <N_stop> (<may run | no run>; check 5 <PASS | FAIL>)

**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md) § Part C "Event count before the shot", § Part B check 5.
**Run:** <run-date>; code at `<git rev-parse --short HEAD>` (worktree branch `2026-10-21-v182-short-screen-range-breakdown`); window 2010-01-01..2019-12-31, events from 2011-01-01; cache `data/backtest_cache_ext` (main tree), membership as tracked.
**Commands:** `python scripts/backtest/screen_idea.py --idea <idea> --count-only --cache-dir <main tree>/data/backtest_cache_ext`, once per idea.
**Outcome-blind:** `--count-only` races nothing and computes no R; no verdict, no results doc, no ledger read or write. Non-overlap assumes every trade lasts the full 20-bar cap, so each real run books at least as many events before the null match.
**Calibration docs on disk (gate held):** `<short-race-calibration doc>` (<k> of 200), `<short-level-race-calibration doc>` (<k> of 200).
**Renamed variants:** none.

<report for range_breakdown_close, headings demoted>

<report for range_breakdown_stop, headings demoted>

## Reading

- `range_breakdown_close`: <N ≥ 300: the one shot runs (V182-19) | N < 300: no run, no ledger row; reported to the partner>.
- `range_breakdown_stop`: <N ≥ 300 and check 5 PASS: the one shot runs (V182-20) | otherwise: no run, no ledger row; reported to the partner, naming the failing clause>.
```

- [ ] **Step 5: Read the gates**

- **Close idea:** N ≥ 300 → V182-19 runs. N < 300 → V182-19 does not run.
- **Stop idea:** N ≥ 300 **and** `**Check 5:** PASS` → V182-20 runs. N < 300, or check 5 FAIL → V182-20 does not run. A check 5 fail never blocks the close idea (spec Part B check 5).
- **Any "does not run":** commit the note anyway (Step 6). Then stop the plan at that point and report to the partner: the idea, its N (and, for the stop idea, both check 5 clause lines). The shot is not spent and no ledger row is written. Loosening a number would make a new idea with a new name, so it is the partner's call. At most one renamed variant per idea may be cut from count feedback alone; it would need its own module, registry pin and counts-note line, and both names count as one family. Wait for the partner's answer before any further task, V182-21 included. An idea that may still run (the close idea when only the stop idea is blocked) also waits for that answer.

- [ ] **Step 6: Commit the note, alone, before any shot**

```bash
git add docs/superpowers/results/<run-date>-v182-counts.md
git commit -m "docs(v182): outcome-blind counts -- close N=<N_close>, stop N=<N_stop>, check 5 <PASS|FAIL>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: one new commit holding only the note; `git status --short` prints nothing (`logs/` is gitignored). The note now predates both shots in history.

### Task V182-19: One-shot screen of `range_breakdown_close`

**Model:** sonnet — the screen skill's ritual, one dispatched run and one commit; the only judgement is refusing to proceed when a precondition fails.

**Files:**
- Create: `docs/superpowers/results/<run-date>-screen-range_breakdown_close.md` (written by the script)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one row appended by the script)

**Interfaces:**
- Consumes: the committed counts note (V182-18) with `range_breakdown_close` at N ≥ 300; the committed idea (V182-14), race, null, verdict and short blocks (V182-1..V182-17).
- Produces: ledger row `screen-range_breakdown_close` (`ledger_id("range_breakdown_close")`) and its results doc. V182-20 and the partner read the verdict for the family reading.

**One shot, never re-run (spec Part C; `backtest-methodology.md` § Funnel stages).** The real run writes the results doc, then the ledger row. Whatever it prints — `SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED` (N < 300 after the real exits, closed like a fail) — is the result. No retry, no second run with another flag, no edit of the idea afterwards. The partner ruled this idea distinct from the closed v105 before approving the spec (spec **Status** and § How this differs), so the screen skill's Step 5 variant question is already answered.

- [ ] **Step 1: The counts note allows the run**

```bash
ls docs/superpowers/results/*-v182-counts.md
git log --oneline -1 -- docs/superpowers/results/*-v182-counts.md
grep -n "range_breakdown_close" docs/superpowers/results/*-v182-counts.md | grep -n "Gate\|Reading\|may run\|no run"
```

Expected: the note exists and is committed; its gate line for `range_breakdown_close` reads `≥ 300: the one shot may run.` Anything else: do not run; V182-18 Step 5 governs.

- [ ] **Step 2: The screen skill's Steps 2–4 — committed definition, clean package, not screened before**

```bash
git status --short swingbot/core/backtesting/screen/
git status --short
git log -1 --format=%H -- swingbot/core/backtesting/screen/
grep -n '"id": "screen-range_breakdown_close"' docs/superpowers/results/preregistration-ledger.jsonl
ls docs/superpowers/results/*-screen-range_breakdown_close.md
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_close.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
```

Expected: both `git status --short` print nothing; note the hash as the **definition commit**; the `grep` and the `ls` find nothing; both test files `0 failed`. Any hit or anything uncommitted: stop and report it to the partner. A results doc with no ledger row is a crash between the doc write and the ledger append; its verdict was still read, so it is never run again.

- [ ] **Step 3: Fix the run date**

Run `date -u +%Y-%m-%dT%H:%M` and add 2 hours (Berlin summer time). `<run-date>` is that Berlin day.

- [ ] **Step 4: Dispatch `backtest-runner` with the one real run**

Dispatch the `backtest-runner` agent, naming the worktree path `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown`, with exactly this command from that worktree's root (defaults for everything else, so the default `--ledger` and `--results-dir` the hook requires):

```bash
python scripts/backtest/screen_idea.py --idea range_breakdown_close --date <run-date> --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v182-screen-range_breakdown_close.log 2>&1
```

Progress prints every few tickers with a percent, so the runner can report on a run of 15 minutes or more. Ask the runner to return only: the exit code and the last line of the log (`screen-range_breakdown_close: <VERDICT>, N=…, dExpR=…R, lower95=…R, …/9 years -> docs/superpowers/results/<run-date>-screen-range_breakdown_close.md`). Relay that verdict line only.

Expected: exit code 0, the results doc and one new last ledger line. If the run crashes or is refused, **do not run it again**: report the exit code and the log's last 20 lines to the partner and wait. A refusal (exit 2, `refused: …`) reads no outcome; the partner decides whether the fixed command may run.

- [ ] **Step 5: Verify the record**

```bash
tail -1 docs/superpowers/results/preregistration-ledger.jsonl
head -8 docs/superpowers/results/<run-date>-screen-range_breakdown_close.md
grep -n "short only\.\|^\*\*Trade:\*\* short;\|^## Short-side blocks\|^\*\*Event overlap\*\*\|^\*\*Trend-only control\*\*\|^\*\*SPY regime split\*\*" docs/superpowers/results/<run-date>-screen-range_breakdown_close.md
```

Expected: the last ledger line has `"id": "screen-range_breakdown_close"`, the verdict the runner relayed, `"record": "docs/superpowers/results/<run-date>-screen-range_breakdown_close.md"`, and a hypothesis starting `range_breakdown_close: ` and naming `SHORT`. The doc's header says `short only.`, its trade line starts `**Trade:** short;`, and the short-side section carries the overlap, control and regime blocks (no level blocks: this is the next-open idea).

- [ ] **Step 6: Record the definition commit and commit doc and ledger together**

Edit the results doc: directly under its H1 line insert one blank line and `**Definition commit:** <hash from Step 2>` (screen skill Step 8). Then:

```bash
git add docs/superpowers/results/<run-date>-screen-range_breakdown_close.md docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v182): screen range_breakdown_close -- <VERDICT exactly as printed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: one commit with exactly those two files; `git status --short` prints nothing. The message names the idea and the verdict and never quotes the command line (the hook reads a quoted run as a wrapped one). Report the verdict line to the partner as printed; no interpretation beyond the spec's family reading, which waits for V182-20.

### Task V182-20: One-shot screen of `range_breakdown_stop`

**Model:** sonnet — the same ritual as V182-19 with the level idea's extra checks; one dispatched run and one commit.

**Files:**
- Create: `docs/superpowers/results/<run-date>-screen-range_breakdown_stop.md` (written by the script)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one row appended by the script)

**Interfaces:**
- Consumes: the committed counts note (V182-18) with `range_breakdown_stop` at N ≥ 300 **and** `**Check 5:** PASS`; the committed idea (V182-15), level race (V182-9), level null (V182-10), level threading (V182-11), short blocks (V182-17); V182-19's committed record (or the partner's answer if V182-19 was blocked).
- Produces: ledger row `screen-range_breakdown_stop` (`ledger_id("range_breakdown_stop")`) and its results doc; the family reading reported to the partner.

**One shot, never re-run** — exactly as V182-19. The level idea's doc also carries the fill-depth table, `null_unfilled` and the 3 × repricing; all are printed and none gates.

- [ ] **Step 1: The counts note allows the run**

```bash
grep -n "range_breakdown_stop\|Check 5:" docs/superpowers/results/*-v182-counts.md | grep -n "Gate\|Check 5\|Reading\|may run\|no run"
git log --oneline -3
```

Expected: the stop idea's gate line reads `≥ 300: the one shot may run.`, its line reads `**Check 5:** PASS -- range_breakdown_stop may run.`, and V182-19's commit (`docs(v182): screen range_breakdown_close -- …`) is in the log, or the partner has answered a V182-18 stop. Anything else: do not run; V182-18 Step 5 governs.

- [ ] **Step 2: The screen skill's Steps 2–4**

```bash
git status --short swingbot/core/backtesting/screen/
git status --short
git log -1 --format=%H -- swingbot/core/backtesting/screen/
grep -n '"id": "screen-range_breakdown_stop"' docs/superpowers/results/preregistration-ledger.jsonl
ls docs/superpowers/results/*-screen-range_breakdown_stop.md
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_range_breakdown_stop.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
```

Expected: both `git status --short` print nothing; the definition hash is the same as V182-19's (no screen file changed between the shots; a different hash means something changed under the second shot — stop and report it); the `grep` and the `ls` find nothing; both test files `0 failed`.

- [ ] **Step 3: Fix the run date**

Run `date -u +%Y-%m-%dT%H:%M` and add 2 hours (Berlin summer time). `<run-date>` is that Berlin day (it may differ from V182-19's).

- [ ] **Step 4: Dispatch `backtest-runner` with the one real run**

Dispatch the `backtest-runner` agent, naming the worktree path `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown`, with exactly this command from that worktree's root:

```bash
python scripts/backtest/screen_idea.py --idea range_breakdown_stop --date <run-date> --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v182-screen-range_breakdown_stop.log 2>&1
```

Ask the runner to return only the exit code and the log's last line (`screen-range_breakdown_stop: <VERDICT>, N=…, … -> docs/superpowers/results/<run-date>-screen-range_breakdown_stop.md`). Relay that verdict line only. A crash or refusal is handled as in V182-19 Step 4: never run again; report and wait.

- [ ] **Step 5: Verify the record**

```bash
tail -1 docs/superpowers/results/preregistration-ledger.jsonl
head -8 docs/superpowers/results/<run-date>-screen-range_breakdown_stop.md
grep -n "short only\.\|^\*\*Trade:\*\* short; sell-stop\|^## Short-side blocks\|^\*\*Event overlap\*\*\|^\*\*Trend-only control\*\*\|^\*\*SPY regime split\*\*\|^\*\*Fill depth\*\*\|^\*\*Null slots:\*\*\|^\*\*Repriced at 3.0 x" docs/superpowers/results/<run-date>-screen-range_breakdown_stop.md
```

Expected: the last ledger line has `"id": "screen-range_breakdown_stop"`, the relayed verdict and the doc as `record`; its hypothesis names `SHORT, sell-stop at the level, filled on the event bar`. The doc's trade line starts `**Trade:** short; sell-stop`, and the short-side section carries all six blocks (overlap, control, regime, fill depth, null slots, repricing).

- [ ] **Step 6: Record the definition commit and commit doc and ledger together**

Edit the results doc: directly under its H1 line insert one blank line and `**Definition commit:** <hash from Step 2>`. Then:

```bash
git add docs/superpowers/results/<run-date>-screen-range_breakdown_stop.md docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v182): screen range_breakdown_stop -- <VERDICT exactly as printed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short
```

Expected: one commit with exactly those two files; `git status --short` prints nothing.

- [ ] **Step 7: Report the family reading to the partner**

The two ideas are nested (spec Part C), so report both verdict lines together with the spec's reading, word for word for the case that occurred, and nothing more:

- **Both `SCREEN-PASS`:** the follow-on spec (`Edge: volume`, `Screen:` a passing ledger id) picks the trigger, citing both results docs.
- **Only one passes:** the follow-on spec may use only that trigger, must say the other failed, and treats the pass as weaker than a lone pass (family of two, BH q printed).
- **Neither:** both are closed. A fail closes exactly the frozen definition (30-bar two-touch range, falling SMA50, that trigger, the fixed 20-bar race, short only), not breakdowns in general.

A pass whose ΔExpR is not clearly above its trend-only control block is not credited to the range (spec Part C); name the two ΔExpR figures from the doc beside each pass. No spec is written in this plan.

### Task V182-21: Full suite, merge, panel, close-out

**Model:** sonnet — one dispatched full run, a merge after the concurrency check, two skills run as written; failures are fixed one test at a time.

**Files:**
- None created by hand (a merge commit on `main`; `/close-out` moves the spec and every plan part and removes the worktree).

**Interfaces:**
- Consumes: every commit of V182-1..V182-20 on the worktree branch `2026-10-21-v182-short-screen-range-breakdown` (or V182-1..V182-18 plus the partner's answer, if a gate stopped a shot).
- Produces: v182 merged on `main`, panel findings handled, the plan closed out.

This is the plan's one full-suite run (CLAUDE.md "Full suite once per plan, as its final task"). It runs only after the shots are recorded or the partner has answered a V182-18 stop.

- [ ] **Step 1: Sync the database replica**

Run `/replicate-prod-db` (CLAUDE.md: a task that runs tests against the database runs it first). Expected: the skill reports the local row counts matching production.

- [ ] **Step 2: The full suite, once, by `test-runner`**

Dispatch the `test-runner` agent, naming the worktree path `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown`, with:

```bash
python scripts/dev/testrun.py full
```

Ask for the summary line and any failure's test id and first error line only. Expected: `0 failed` and `0 xfailed` (a changed pass count is not a failure; `docs/claude/testing-cost.md`). The full run includes the complexity gate, `tests/hooks/test_codex_mirror.py` and both long goldens.

A failure is fixed and re-run alone (`python scripts/dev/testrun.py file <test file>` or `python -m pytest <path>::<test> -v`), never by re-running the full suite. A fix that touches `swingbot/core/backtesting/screen/` after a shot cannot change a recorded result: it is reported to the partner with the fix, and no screen is ever re-run. Commit each fix on the worktree branch with its own message ending in the `Co-Authored-By` line.

- [ ] **Step 3: Merge to `main`**

Invoke the `worktree-lifecycle` skill and follow its merge steps (another session may be on `main`; pause and confirm with the partner if concurrent activity shows). From the main checkout:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -5 main
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline main..2026-10-21-v182-short-screen-range-breakdown
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-21-v182-short-screen-range-breakdown -m "merge(v182): idea screen for shorts, level-entry race, range-breakdown screens

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: the main tree is clean before the merge; the branch log lists the V182 commits (the golden capture first); the merge completes without conflicts. A conflict in `docs/superpowers/results/preregistration-ledger.jsonl` (another session appended a row) is resolved by keeping **every** row from both sides, in date order, never dropping or editing one. No full suite after the merge (CLAUDE.md).

- [ ] **Step 4: Panel review**

Run `/panel quant-researcher,quant-engineer,veteran-trader` (the spec's `**Panel:**` line) over the merged diff (`git diff <merge-base>..main`, where `<merge-base>` is `git merge-base main^1 main^2`) together with the results docs and the counts note. Handle findings as the panel skill says:
- a code defect gets a test and a fix, committed on `main` in its own scoped commit, run narrowly (`python scripts/dev/testrun.py file <test>`);
- nothing ever edits a results doc, the counts note or a ledger row, and nothing re-runs a screen or a count; a finding that questions a recorded result goes to the partner as a finding, not a fix.

- [ ] **Step 5: Close out**

Run `/close-out` (standing permission; `docs/claude/document-lifecycle.md`). The plan's `**Bump:**` is `none`. The instrument shipped on `main`, so the spec and all six plan files (`_0-index` and `_1`..`_5`) move to `implemented/`; the screens' verdicts live in the ledger and the results docs. Close-out removes the worktree. Never delete a branch whose name contains `backup` or starts `stable-`; before any branch deletion run `git rev-list --count main..2026-10-21-v182-short-screen-range-breakdown` and stop on a non-zero count (`docs/claude/git-safety.md`).

Expected: `git status --short` on `main` prints nothing; `git worktree list` no longer shows the v182 worktree; the SessionStart `PLAN WIP` line no longer names v182.

