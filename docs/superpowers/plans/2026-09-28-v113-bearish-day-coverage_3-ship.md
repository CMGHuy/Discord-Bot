# v113 Part 3 — Ship decisions (passes only), documentation, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, amendments, Review Focus and Parallelisation live in `2026-09-28-v113-bearish-day-coverage_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md` §5, §7

Each of V113-18, V113-19 and V113-20 starts by reading `results/<date>-v113-holdout.md` and the holdout JSONs. **A block runs only for a candidate whose holdout JSON has `"status": "scored"` and `"passes": true`.** With no pass anywhere, skip straight to V113-21.

Code changes (V113-18, V113-20) happen on a worktree branch named `2026-09-28-v113-bearish-day-coverage-wiring` (`worktree-lifecycle`), created by whichever of the two runs first. Iterate with `testrun.py file`; run `testrun.py fast` once after the last of them, then merge.

---

# Phase C — Ship and close-out

### Task V113-18: Wire the Part B cells that passed

**Files (only if a Part B cell passed):**
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES`)
- Modify: `swingbot/core/backtesting/validation_registry.json` (via `emit-registry`)
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts:21`, `frontend/src/app/workspaces/trades/trades.ts:684` and every other hard-coded horizon list `git grep` finds
- Modify: `tests/market/test_v113_horizon.py`, `tests/market/test_v113_horizon_vocab.py` (the "no cell ships yet" assertions)
- Create: `tests/market/test_v113_shipped.py`

**Interfaces:**
- Consumes: `admits`/`cells` and `live_horizons()` (V113-2); `measure_v113 emit-registry` (V113-11); the passing `b-*` holdout JSONs (V113-17).
- Produces: live admission of exactly the passing `(strategy, direction, "1w")` pairs; one `(strategy, "1w")` registry row per strategy.

- [ ] **Step 1: List the passes.**

```bash
python - <<'EOF'
import json, glob
for p in sorted(glob.glob("docs/superpowers/results/*-v113-holdout-b-*.json")):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("status") == "scored" and d.get("passes"):
        print(p, d["strategy"], d["direction"], d["stats"]["n"], d["stats"]["win_rate"], d["stats"]["expectancy_r"])
EOF
```

No line printed → this task is a no-op; go to V113-19.

- [ ] **Step 2: Admit each passing pair through `cells`.** In `STRATEGY_GATES`, for each passing strategy add (or extend) a `"cells"` key holding exactly its passing pairs, leaving every other key untouched. A strategy with no entry today (EMA Crossover, Elliott Wave, RSI Divergence) gets a new entry holding only `"cells"` — its legacy axes stay "all directions, all legacy horizons". Above each change add one comment line: `# v113 Part B (<date>): <direction> on 1w -- TRAIN N=<n> WR=<wr> ExpR=<e>; holdout N=<n> WR=<wr> ExpR=<e>, Tier 1 + lower bound.` Example shape:

```python
    "MACD": {"directions": ("bullish",), "horizons": ("3m", "4m", "7m", "8m", "9m"),
             "cells": {("bearish", "1w")}},
```

- [ ] **Step 3: Registry rows.** For each strategy, pass all of its passing Part B holdout JSONs together (the script refuses a set that differs from the shipped `cells`):

```bash
python scripts/backtest/measure_v113.py emit-registry --holdout-json <that strategy's passing b-* holdout JSONs> --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
```

- [ ] **Step 4: Tests that assumed nothing ships.** In `tests/market/test_v113_horizon.py`, add at the top:

```python
@pytest.fixture
def no_cells(monkeypatch):
    """The pre-ship world: STRATEGY_GATES without any v113 cells."""
    stripped = {name: {k: v for k, v in gates.items() if k != "cells"} for name, gates in st.STRATEGY_GATES.items()}
    monkeypatch.setattr(st, "STRATEGY_GATES", stripped)
```

and add `no_cells` as a parameter to `test_every_registered_strategy_is_masked_on_1w_by_default` and `test_live_horizons_is_legacy_until_a_cell_admits_1w` (they describe the rule, not today's gates). In `tests/market/test_v113_horizon_vocab.py`, change `test_slash_horizon_choices_are_the_live_vocabulary`'s expectation to `[*st.live_horizons(), "all"]` and `test_run_full_backtest_walks_the_live_vocabulary`'s to `sorted(st.live_horizons())`; add `assert st.live_horizons()[0] == "1w"` to the first.

Create `tests/market/test_v113_shipped.py`:

```python
"""v113 Part B: exactly the holdout-passing (strategy, direction) pairs are admitted on 1w."""
from swingbot.core.market import strategy_types as st

SHIPPED = {<("Strategy", "direction"), one per passing cell>}


def test_v113_shipped_1w_cells():
    admitted = {(name, direction) for name, gates in st.STRATEGY_GATES.items()
                for direction, horizon in gates.get("cells", ()) if horizon == "1w"}
    assert admitted == SHIPPED
    for name, direction in SHIPPED:
        assert st.admits(name, direction, "1w")
    assert st.live_horizons()[0] == "1w"
```

- [ ] **Step 5: Frontend horizon lists.** Run `git grep -n "'2w', '4w', '2m', '3m'" -- frontend/src`. In every non-spec list (at least `analytics.ts` `FALLBACK_HORIZONS` and `trades.ts` `horizonOptions`) prepend `'1w'`, and update the adjacent comment that says "ten" to "eleven". Update any spec file that asserts one of those lists' contents. Run each touched spec: `npm --prefix frontend test -- --include <spec path>`.

- [ ] **Step 6: Soak, not alerts.** Leave `STRATEGY_ALERTS_MODE` and `STRATEGY_ALERTS_LIVE_STRATEGIES` alone (amendment 6).

- [ ] **Step 7: Run and commit**

Run: `python scripts/dev/testrun.py file tests/market/test_v113_shipped.py tests/market/test_v113_horizon.py tests/market/test_v113_horizon_vocab.py tests/market/test_v113_horizon_witness.py tests/backtesting/test_registry.py tests/admin/test_gate_description.py`
Expected: all PASS.

```bash
git add swingbot/core/market/strategy_types.py swingbot/core/backtesting/validation_registry.json tests/market/test_v113_shipped.py tests/market/test_v113_horizon.py tests/market/test_v113_horizon_vocab.py <each frontend file and spec touched in Step 5>
git commit -m "feat(v113): ship Part B 1w cells <list> -- Tier 1 + lower bound on the 2026 holdout; registry rows (strategy, 1w)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-19: Part A decision — record, keep masked, ask about live execution

**Files:** none (the outcome is written by V113-21).

**Interfaces:**
- Consumes: `results/<date>-v113-holdout-a-fade.json` if it exists.
- Produces: one of three outcomes for V113-21: `NO-LIFT at <stage>`, `SEALED-THIN (retry at HOLDOUT_END ≥ 2026-12-31)`, or `PASS — blocked on live execution`, plus the partner's answer in the last case.

This task changes no code. Amendment 2: live execution cannot match what was measured, so an A pass does not unmask the fade.

- [ ] **Step 1: Read the outcome.** No `*-v113-holdout-a-fade.json` → A ended on TRAIN; take the stage and clause from `results/<date>-v113-partA.md`. `sealed-thin` → record N and the retry date. `scored` and not `passes` → record the failing clause.

- [ ] **Step 2: Only if it passed — check each live gap is still real** (another plan may have closed one since this plan was written):
  - `git grep -n '"limit"' -- swingbot/core/planning/plan_manager.py` — no match means the live `PlanManager` cannot fill a limit entry.
  - `git grep -n "tp1_fraction" -- swingbot/core/planning/plan_manager.py` — confirm `_step_active` always moves to `PARTIAL` at TP1 (no whole-position close).
  - `git grep -n "max_holding_days\|hold_cap_bars" -- swingbot/core/planning/plan_manager.py` — no match means no live time-stop exit.
  - `git grep -n "earnings_context" -- swingbot/core/scanning/strategy_pass.py` — no match means live strategy frames carry no `evt_*` columns, so the fade would never fire live.

  If all four gaps are closed by then, stop and ask the controller whether to unmask now (`"Downtrend Overbought Fade": {"directions": (), "cells": {("bearish", "1w")}}` plus a registry row via `emit-registry`).

- [ ] **Step 3: Only if it passed and a gap remains — ask the partner** with `AskUserQuestion` (one question, recommended option first):
  - Question: "The Downtrend Overbought Fade passed its 2026 holdout (N=<n>, WR <wr>%, ExpR <e>). Live tracking can't yet run it as measured (limit entry, whole-position target, 7-bar time stop, earnings context). Open a follow-up spec for that live execution?"
  - Options: "Yes — brainstorm the live-execution follow-up now (recommended)", "Record the pass only; revisit later".
  Record the answer for V113-21. Write a project memory: the pass, the four gaps, and that the fade stays masked until the follow-up ships.

---

### Task V113-20: Wire Part D if it passed — inverse ETFs join the watchlist, tagged

**Files (only if `d-inverse-etfs` passed):**
- Modify: `swingbot/core/marketdata/universe.py` (`is_etf`; new `_inverse_rows`, `is_inverse`, `inverse_label`)
- Modify: `swingbot/core/edge/rs_gate.py` (`rs_verdict`)
- Modify: `swingbot/core/scanning/alert_embeds.py` (`build_strategy_alert_embed`)
- Modify: `swingbot/core/scanning/scan_run.py` (new `_confluence_tickers`; two expressions in `_sync_run_scan`) — recommended option only
- Modify: `swingbot/core/scanning/strategy_pass.py` (new `_measured`; one loop header in `run_strategy_pass`) — recommended option only
- Create: `tests/test_v113_inverse_etfs.py`

**Interfaces:**
- Consumes: `data/universe/inverse_etfs.json` (V113-12); the passing `d-inverse-etfs` holdout JSON (V113-17).
- Produces: `universe.is_inverse(symbol) -> bool`, `universe.inverse_label(symbol) -> str | None`; the RS leader gate never blocks an inverse ETF; the strategy alert labels it; (recommended) inverse tickers skip the confluence scan and bearish strategy signals. The watchlist change itself happens in V113-22 after deploy.

- [ ] **Step 1: Ask the partner about the unmeasured populations** (`AskUserQuestion`, one question, recommended first). Part D measured only the live **bullish strategy** masks. Adding the four ETFs to the watchlist would also feed them to the confluence scan and to bearish strategy signals — neither measured.
  - Question: "Part D passed (N=<n>, WR <wr>%, ExpR <e> on the 2026 holdout). On SH/PSQ/RWM/DOG, alert only through what was measured — bullish strategy signals — or through the full scan?"
  - Options: "Measured population only: skip the confluence scan and bearish signals on the four (recommended)", "Full scan, like any other ticker (unmeasured)".
  Do Step 5 only for the recommended answer; for the other, skip it and record in V113-21 that the confluence and bearish populations on inverse tickers ship unmeasured.

- [ ] **Step 2: Write the failing tests** — `tests/test_v113_inverse_etfs.py`:

```python
"""v113 §5: inverse ETFs are tagged, never RS-leader-gated, and labelled."""
import pytest

from swingbot import config
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.marketdata import universe


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    monkeypatch.setattr(universe, "_INVERSE_CACHE", None)
    monkeypatch.setattr(universe, "_ETF_CACHE", None)


def test_the_manifest_tags_the_four_inverse_etfs():
    assert all(universe.is_inverse(t) for t in ("SH", "psq", "RWM", "DOG"))
    assert not universe.is_inverse("SPY") and not universe.is_inverse("AAPL")
    assert universe.is_etf("SH")
    assert universe.inverse_label("SH") == "Long SH = short S&P 500"
    assert universe.inverse_label("SPY") is None


def test_the_bullish_rs_leader_gate_never_applies_to_an_inverse_etf(monkeypatch):
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 60.0, raising=False)   # switch the (off) gate on
    assert rs_verdict("AAPL", "bullish", 10.0, rs_available=True)["status"] == "block"
    assert rs_verdict("SH", "bullish", 10.0, rs_available=True)["status"] == "exempt"


def test_the_bearish_laggard_rule_still_reads_an_inverse_etf(monkeypatch):
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 25.0, raising=False)
    assert rs_verdict("SH", "bearish", 90.0, rs_available=True)["status"] == "block"


def test_the_strategy_alert_labels_an_inverse_etf():
    from types import SimpleNamespace
    from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed
    plan = SimpleNamespace(ticker="SH", direction="bullish", strategy="RSI", horizon_key="4w",
                           badge="WEAK", trigger_price=40.0, stop_loss=39.2, tp1=41.5, tp2=None,
                           ledger="main", plan_id="p1")
    fields = {f.name: f.value for f in build_strategy_alert_embed(plan).fields}
    assert fields["Inverse ETF"] == "Long SH = short S&P 500"
    plan.ticker = "AAPL"
    assert "Inverse ETF" not in {f.name for f in build_strategy_alert_embed(plan).fields}


def test_measured_population_only():
    from swingbot.core.scanning import scan_run, strategy_pass
    assert scan_run._confluence_tickers(["AAPL", "SH", "DOG", "MSFT"]) == ["AAPL", "MSFT"]
    fired = [("RSI", "bullish"), ("Break & Retest", "bearish")]
    assert strategy_pass._measured("SH", fired) == [("RSI", "bullish")]
    assert strategy_pass._measured("AAPL", fired) == fired
```

(If the partner chose the full scan, delete `test_measured_population_only`.)

Run: `python scripts/dev/testrun.py file tests/test_v113_inverse_etfs.py`
Expected: FAIL — `AttributeError: module ... has no attribute '_INVERSE_CACHE'`.

- [ ] **Step 3: Universe tags.** In `swingbot/core/marketdata/universe.py`, change `is_etf`'s loop to `for name in ("etfs", "sp500", "inverse_etfs"):` and add after `is_etf`:

```python
# --- Inverse-ETF tag (v113 Part D) -------------------------------------------
#
# Read raw from data/universe/inverse_etfs.json: load() keeps only the four
# required keys, and the label needs "tracks".

_INVERSE_CACHE: dict | None = None


def _inverse_rows() -> dict:
    global _INVERSE_CACHE
    if _INVERSE_CACHE is None:
        try:
            with open(os.path.join(UNIVERSE_DIR, "inverse_etfs.json"), "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw = []
        _INVERSE_CACHE = {str(row["symbol"]).upper(): row for row in raw
                          if isinstance(row, dict) and row.get("inverse")}
    return _INVERSE_CACHE


def is_inverse(symbol: str) -> bool:
    """True for a 1x inverse index ETF (v113 D): long it = short its index."""
    return str(symbol).upper() in _inverse_rows()


def inverse_label(symbol: str) -> str | None:
    """"Long SH = short S&P 500" for an inverse ETF, else None."""
    row = _inverse_rows().get(str(symbol).upper())
    return None if row is None else f"Long {row['symbol']} = short {row['tracks']}"
```

- [ ] **Step 4: RS exemption and the label.**
  - `swingbot/core/edge/rs_gate.py` `rs_verdict`: directly after the `is_rs_eligible` block add

```python
    if direction == "bullish":
        from swingbot.core.marketdata.universe import is_inverse
        if is_inverse(symbol):
            return {"status": "exempt",
                    "reason": f"{symbol} is an inverse ETF -- its RS vs SPY is structurally negative"}
```

  - `swingbot/core/scanning/alert_embeds.py` `build_strategy_alert_embed`: directly after the `add_field(name="Plan (v2)", ...)` call add

```python
    from swingbot.core.marketdata.universe import inverse_label
    label = inverse_label(plan.ticker)
    if label:
        embed.add_field(name="Inverse ETF", value=label, inline=False)
```

- [ ] **Step 5 (recommended answer only): measured population only.**
  - `swingbot/core/scanning/scan_run.py`: add near the other module-level helpers

```python
def _confluence_tickers(tickers):
    """v113 D: inverse ETFs trade only through the population Part D measured
    (live bullish strategy masks) -- never the confluence scan."""
    from swingbot.core.marketdata.universe import is_inverse
    return [ticker for ticker in tickers if not is_inverse(ticker)]
```

  In `_sync_run_scan`, change `progress.total = len(tickers) * max(1, len(horizons_to_scan))` to `progress.total = len(_confluence_tickers(tickers)) * max(1, len(horizons_to_scan))`, and the `tickers,` argument that closes the `fetch.map_tickers(` call to `_confluence_tickers(tickers),`. Change nothing else in that function.
  - `swingbot/core/scanning/strategy_pass.py`: add above `run_strategy_pass`

```python
def _measured(ticker, fired):
    """v113 D: on an inverse ETF only bullish strategy signals were measured."""
    from swingbot.core.marketdata.universe import is_inverse
    if not is_inverse(ticker):
        return fired
    return [(strategy, direction) for strategy, direction in fired if direction == "bullish"]
```

  and in `run_strategy_pass` change `for strategy, direction in strategy_signals(frame, horizon, spy_df=spy_df):` to `for strategy, direction in _measured(ticker, strategy_signals(frame, horizon, spy_df=spy_df)):`.

- [ ] **Step 6: Run and commit**

Run: `python scripts/dev/testrun.py file tests/test_v113_inverse_etfs.py tests/scanning/test_rs_gate_wiring.py tests/scanning/ tests/edge/`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/edge/rs_gate.py swingbot/core/marketdata/universe.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/scan_run.py`
Expected: `_sync_run_scan` still `F (108)`; no new function listed; no function's grade worse.

```bash
git add swingbot/core/marketdata/universe.py swingbot/core/edge/rs_gate.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/strategy_pass.py tests/test_v113_inverse_etfs.py
git commit -m "feat(v113): inverse-ETF tag -- RS leader gate exempt, labelled alerts, measured population only; ETFs join the watchlist at release

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Drop `scan_run.py`/`strategy_pass.py` from the command if the partner chose the full scan.)

- [ ] **Step 7: Close the wiring branch.** After V113-18 and V113-20 (whichever ran): `python scripts/dev/testrun.py fast` once (`0 failed`, `0 xfailed`); if V113-18 touched `frontend/`, also `npm --prefix frontend test` once. Then merge the wiring branch into `main` per `worktree-lifecycle`, after checking `git log main` for other sessions' commits to the same files.

---

### Task V113-21: Methodology rows and strategy docs (every outcome)

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Modify: `docs/strategy-types/README.md`, `docs/strategy-types/shared-mechanics.md`, each Part B strategy page
- Create: `docs/strategy-types/downtrend-overbought-fade.md`

**Interfaces:**
- Consumes: every v113 results file; V113-18/19/20 outcomes and the partner's answers.
- Produces: the permanent record — what died where and why, and what reopening needs.

- [ ] **Step 1: Methodology rows.** Load `pooled-numbers`. Add three rows to the closed pre-registrations table, in the v104 rows' style, with no ALL-CAPS token in backticks unless it is a closed knob (`tests/hooks/test_guardrails.py` checks this):
  - **Part A — Downtrend Overbought Fade on 1w (v113):** the stage it ended at; per `m` the TRAIN N / WR / ExpR / lower bound; the plateau and winner; folds; the holdout outcome; if it passed, "PASS — blocked on live execution" with the four gaps and the partner's answer. What reopening needs if it failed (a new mechanism, not another `m`).
  - **Part B — 22 legacy cells on 1w (v113):** how many cells ended at Stage 1, Stage 2, holdout pass / fail / sealed-thin; the passing pairs with TRAIN and holdout figures; which empty cells are arithmetic (cap-bind or floor-drop) rather than market verdicts.
  - **Part D — inverse-ETF longs (v113):** the pooled TRAIN and holdout figures; the survivors of the liquidity filter; whether shipped, sealed-thin (retry date) or failed; the partner's population choice if it shipped.

- [ ] **Step 2: Strategy docs.**
  - Create `docs/strategy-types/downtrend-overbought-fade.md` in the existing page format (idea, entry rule, plan, measured, pseudocode), sourced from `short_entries.py`, `short_builders.py` and the Part A results.
  - `shared-mechanics.md`: a section "The 1w horizon and `cells` (v113)" — the horizon values, masked-by-default, `admits`, `live_horizons`, the strategy-plan reward floor, the limit entry type and its fill-bar rule.
  - Each Part B strategy page: a `## Measured` line with its two 1w cells' TRAIN figures and outcome.
  - `README.md`: add the fade to the table.

- [ ] **Step 3: Commit on `main`**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py tests/hooks/test_codex_mirror.py`
Expected: PASS. If the Codex mirror test fails because of the methodology edit, mirror it into `AGENTS.md` per `docs/claude/working-conventions.md` § Codex mirror and stage `AGENTS.md` too.

```bash
git add docs/claude/backtest-methodology.md docs/strategy-types/
git commit -m "docs(v113): methodology rows and strategy-type pages -- A <outcome>, B <k>/22, D <outcome>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-22: Full-suite verification, release, production watchlist, close-out

**Files:**
- Modify (only if something shipped): `VERSION.json`, `swingbot/admin/version_history.json`, `data/watchlist.json` (mirror of production, D only)

**Interfaces:**
- Consumes: everything above, on `main`.
- Produces: a green suite; a `bot minor` release if V113-18 or V113-20 shipped; the plan moved to `implemented/`.

- [ ] **Step 1: Full suite, once.** Dispatch `test-runner` for `python scripts/dev/testrun.py full` on `main`. Require `0 failed` and `0 xfailed`. If V113-18 touched `frontend/`, also run `npm --prefix frontend test` once. **If either is not green, fix forward from those failures** — they are this plan's regressions. A failure that passes in isolation and sits in code v113 never touched is reported with both outputs; the suite is not called green.

- [ ] **Step 2: Close out.** Invoke `/close-out v113`. It resolves the bump from the then-current `VERSION.json`: `bot minor` if V113-18 or V113-20 shipped anything, otherwise no release commit (Phase A's code is on `main` but inert). It regenerates `version_history.json` with any bump, moves the spec and all six plan files (`_0-index`, `_1a-horizon`, `_1b-fade`, `_1c-measure-script`, `_2-measurement`, `_3-ship`) to `implemented/` (the code reached `main` either way), and removes the worktrees. Add the spec Status line: `**Status:** <Shipped <list> | Closed no-lift> <date>; holdout spent: <list>; sealed-thin: <list or none>; A: <outcome>.`

- [ ] **Step 3 (only if Part D shipped): the production watchlist.** Load `mirror-prod`. Deploy the release first (`deploy` skill) so the inverse tag, RS exemption and measured-population filter are live before any ETF is scanned. Then ask the partner (`AskUserQuestion`: "Add SH, PSQ, RWM and DOG to the production watchlist now? (recommended: yes — the tag and filters are deployed)") — real money trades from these alerts. On yes:

```bash
bash scripts/ops/ssh-hetzner.sh "test -f /opt/swing-bot/data/universe/inverse_etfs.json && echo manifest-ok"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot.core.marketdata.watchlist import add_ticker; [add_ticker(t) for t in (\"SH\", \"PSQ\", \"RWM\", \"DOG\")]; print(\"added\")'"
```

(`cd` here runs on the VM inside the quoted remote command, not in this shell.) If `manifest-ok` is missing, stop: the tag would be absent live. Then mirror: add the four tickers to `data/watchlist.json` in the repo (keep its sort order) and commit `chore(v113): mirror production watchlist -- SH, PSQ, RWM, DOG` with the trailer.

- [ ] **Step 4: Remember sealed-thin shots.** If any candidate is `sealed-thin`, write a project memory: the candidate list, "retry once when HOLDOUT_END ≥ 2026-12-31", and the V113-17 Step 2 command for each. Otherwise no session will remember the shot.
