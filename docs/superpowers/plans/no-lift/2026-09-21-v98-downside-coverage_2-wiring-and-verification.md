# Downside coverage (v98) — Part 2: wiring, the pre-merge gate and verification

> Header block, goal, discrepancies, global constraints and the parallelisation
> map live in `2026-09-21-v98-downside-coverage_0-index.md`. Read it first.
>
> **Do not start this part unless Task D11 (Part 1) recorded a PASS**, per
> instrument and pooled.

# Phase 3 — Wiring and the pre-merge gate

**Do not start this phase unless D11 recorded a PASS**, per instrument and pooled.

### Task D12: Config flag and the measured horizon overlay

Ships **default on** (spec Decision 2). The repo's usual posture is default-off with
a separate enabling decision, but there is no post-merge checkpoint here — the
operator places resting broker orders from alerts, so these are real-money-actionable
the moment the change merges. The safety checkpoint moves **before** merge (D16);
the flag stays afterwards as a **kill switch** so the basket can be turned off
without a revert.

**Files:**
- Modify: `swingbot/config.py`
- Modify: `swingbot/core/market/strategy_types.py` (fill `SYMBOL_HORIZON_OVERLAY`)
- Test: `tests/test_config_schema.py` (find the real name with
  `grep -rln "FIELDS" tests/`)

- [ ] **Step 1: Add two Fields**

Matching the existing shape (`config.py:74-89` defines `Field`; see
`VOLUME_PROFILE_NODES_ENABLED` at line 880 for a checkbox example), in the
`"Universe & Scanning"` section:

```python
    Field("INVERSE_INSTRUMENTS_ENABLED", "INVERSE_INSTRUMENTS_ENABLED",
          "Universe & Scanning", "Inverse-instrument downside coverage",
          type="checkbox", default="true",
          help="Adds the four unleveraged inverse ETFs (PSQ, SH, RWM, DOG) to the scanned "
               "universe as ordinary symbols, so the already-shipped BULLISH strategy arms "
               "trade them -- the book's only downside coverage. No gate, mask or threshold "
               "changes. Default ON because these alerts are real-money-actionable the moment "
               "they merge and the safety checkpoint sits before the merge, not after "
               "(v98 spec, Evaluation contract); this flag is the kill switch. Off restores "
               "an equities-only universe exactly, with no other behaviour change."),
    Field("INVERSE_MAX_CONCURRENT", "INVERSE_MAX_CONCURRENT",
          "Universe & Scanning", "Max concurrent inverse positions",
          type="number", default="4", min=0, max=4, step=1,
          help="Concurrent cap on the inverse basket, held entirely OUTSIDE "
               "max_open_positions -- the two counters never share a number, so the basket "
               "can never consume a long slot and a full long book can never starve it. "
               "4 is the whole basket, so no instrument is arbitrarily locked out of a "
               "decline. The cap is for isolation, not diversification: the four are ~0.95 "
               "correlated with each other and are one trade at 4x size."),
```

Both are hot-reloadable (the default) — the kill switch must work over SIGHUP
without a restart.

- [ ] **Step 2: Fill the overlay from D11's verdict**

Write the *measured* subset per instrument into `SYMBOL_HORIZON_OVERLAY`, with the
results document named in the comment:

```python
# Horizons that cleared Q-INV on TRAIN, per instrument
# (docs/superpowers/results/2026-09-21-v98-q-inv-train.md, 2026-09-21).
SYMBOL_HORIZON_OVERLAY: dict[str, tuple[str, ...]] = {
    "PSQ": (...),   # <- from D11, never a guess
    ...
}
```

Also update the empty-table assertion in
`tests/market/test_symbol_horizon_overlay.py` (D5 Step 1) to assert the measured
contents, and add an assertion that every symbol in the table is in
`INVERSE_SYMBOLS` — the overlay is a per-symbol mechanism, but this plan only
measured it on the basket.

- [ ] **Step 3: Verify and commit**

```bash
python scripts/dev/testrun.py file tests/test_config_schema.py
python scripts/dev/testrun.py file tests/market/test_symbol_horizon_overlay.py
git add swingbot/config.py swingbot/core/market/strategy_types.py \
        tests/test_config_schema.py tests/market/test_symbol_horizon_overlay.py
git commit -m "feat(v98): INVERSE_INSTRUMENTS_ENABLED default-on + measured horizon overlay"
```

### Task D13: Union the basket into the scan universe

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (line 192, `tickers = load_watchlist()`)
- Test: `tests/scanning/test_inverse_universe.py`

**Interfaces:**
- Consumes: `config.INVERSE_INSTRUMENTS_ENABLED` (D12),
  `populations.INVERSE_SYMBOLS` (D1).
- Produces: `scan_run.scan_universe() -> list[str]`.

- [ ] **Step 1: Write the failing test**

```python
def test_universe_gains_the_basket_when_the_flag_is_on(monkeypatch):
    monkeypatch.setattr(config, "INVERSE_INSTRUMENTS_ENABLED", True)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["AAPL", "MSFT"])
    assert scan_run.scan_universe() == ["AAPL", "MSFT", "PSQ", "SH", "RWM", "DOG"]


def test_universe_is_the_watchlist_exactly_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(config, "INVERSE_INSTRUMENTS_ENABLED", False)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["AAPL", "MSFT"])
    assert scan_run.scan_universe() == ["AAPL", "MSFT"]


def test_a_basket_symbol_already_on_the_watchlist_is_not_duplicated(monkeypatch):
    monkeypatch.setattr(config, "INVERSE_INSTRUMENTS_ENABLED", True)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["AAPL", "PSQ"])
    assert scan_run.scan_universe() == ["AAPL", "PSQ", "SH", "RWM", "DOG"]


def test_the_watchlist_file_is_never_written(monkeypatch, tmp_path):
    """The basket is a scan-time union, not a watchlist edit. Writing it into
    data/watchlist.json would survive the flag going off and would show up in
    the admin watchlist page as a user-managed symbol."""
    ...
```

- [ ] **Step 2: Implement**

```python
def scan_universe() -> list[str]:
    """The watchlist, plus the v98 inverse basket when the flag is on.

    A scan-time union, deliberately NOT an edit to data/watchlist.json: the
    watchlist is user-managed state surfaced in the admin UI and persisted
    across restarts, so writing the basket into it would survive the kill
    switch being thrown and would present four bot-managed symbols as the
    operator's own. Order is watchlist-then-basket so the differential test's
    long-alert ordering is unchanged.
    """
    from swingbot import config
    from swingbot.core.market.populations import INVERSE_SYMBOLS
    tickers = load_watchlist()
    if not getattr(config, "INVERSE_INSTRUMENTS_ENABLED", False):
        return tickers
    seen = set(tickers)
    return tickers + [s for s in INVERSE_SYMBOLS if s not in seen]
```

Replace `tickers = load_watchlist()` at line 192 with `tickers = scan_universe()`.
Leave every other `load_watchlist()` caller alone — `commands/scanning/commands.py:310`,
`loops.py:823` and the admin watchlist endpoint are about the *user's* list and must
keep showing exactly that.

Check `loops.py:788` (`refresh_watchlist_earnings(load_watchlist())`): with D1's ETF
tagging the basket short-circuits in `get_next_earnings_date` anyway, so leaving it
on `load_watchlist()` is correct and costs nothing.

- [ ] **Step 3: Verify and commit**

```bash
python scripts/dev/testrun.py file tests/scanning/test_inverse_universe.py
python scripts/dev/testrun.py file tests/scanning/test_scan_run.py
git add swingbot/core/scanning/scan_run.py tests/scanning/test_inverse_universe.py
git commit -m "feat(v98): union the inverse basket into the scan universe behind the flag"
```

### Task D14: The differential test — long alerts byte-identical

**This is the deliverable that discharges the spec's Isolation section.** Everything
else in Phase 1 is a mechanism; this is the proof.

**Files:**
- Create: `tests/scanning/test_inverse_differential.py`

- [ ] **Step 1: Write it**

```python
"""v98 differential: the long book must not move.

Runs the scan pipeline over the same watchlist twice -- once with the inverse
basket present, once absent -- and asserts every emitted LONG alert is
identical. This is the deliverable the spec's Isolation section asks for; the
four coupling-point tasks (D2-D5) are the mechanisms, and this is the proof
that they cover every path between the new population and an existing alert.
"""
import pytest

from swingbot import config
from swingbot.core.market.populations import INVERSE_SYMBOLS, population_of

#: Every field of a long alert a divergence could hide in. Sizes are included
#: because the heat/correlation path is where a new population would leak in
#: without changing a price.
_ALERT_FIELDS = ("ticker", "strategy", "horizon_key", "direction",
                 "trigger_price", "entry_price", "stop_loss", "tp1", "tp2",
                 "shares", "risk_amount", "confidence_level", "quality_score",
                 "badge", "cohort_label", "warning")


def _long_alerts(results):
    return sorted(
        [tuple(getattr(r, f, None) for f in _ALERT_FIELDS) for r in results
         if population_of(getattr(r, "ticker", None)) == "equity"],
        key=lambda row: (row[0], row[1], row[2]),
    )


@pytest.fixture
def frozen_universe(monkeypatch):
    """A fixed, cached multi-ticker slice so both arms see identical bars.
    Use the market_data/ cache, not a network fetch -- a differential test
    whose two arms fetch separately can differ for a reason that is not the
    feature."""
    ...


def test_long_alerts_are_identical_with_and_without_the_basket(monkeypatch, frozen_universe):
    monkeypatch.setattr(config, "INVERSE_INSTRUMENTS_ENABLED", False)
    without = _long_alerts(run_scan_once(frozen_universe))

    monkeypatch.setattr(config, "INVERSE_INSTRUMENTS_ENABLED", True)
    results = run_scan_once(frozen_universe)
    with_ = _long_alerts(results)

    assert with_ == without, "the inverse basket moved a long alert"


def test_the_flag_on_arm_actually_emitted_something_inverse(monkeypatch, frozen_universe):
    """Guards the differential against passing vacuously. A fixture where the
    basket never fires proves nothing about isolation."""
    monkeypatch.setattr(config, "INVERSE_INSTRUMENTS_ENABLED", True)
    results = run_scan_once(frozen_universe)
    assert any(population_of(r.ticker) == "inverse" for r in results)


def test_the_slot_warning_text_is_unchanged_by_open_inverse_positions():
    """DISC-1: max_open_positions composes a warning string and nothing else,
    so the warning text is the ONLY way an open inverse position can reach a
    long alert. It is in _ALERT_FIELDS above; this asserts the mechanism
    directly as well, since a fixture with <30 opens would never exercise it."""
    from swingbot.core.scanning.scan_run import slot_warning
    equities = [{"ticker": "AAPL", "status": "open"}] * 29
    basket = [{"ticker": s, "status": "open"} for s in INVERSE_SYMBOLS]
    assert slot_warning(equities, 30) == slot_warning(equities + basket, 30)


def test_an_inverse_position_never_joins_an_equity_correlation_cluster():
    """The favourable property the spec says to preserve: correlation.py's
    `corr > threshold` is one-sided (correlation.py:38), so an inverse ETF at
    corr ~ -0.9 cannot inflate correlated heat and block a long. This test
    exists so a later 'fix' to two-sided clustering fails loudly here."""
    from swingbot.core.edge.correlation import cluster_exposure
    ...
    assert "PSQ" not in exposure["cluster"]


def test_cohort_lookups_for_equities_are_unchanged_by_an_inverse_cell():
    from swingbot.core.backtesting.cohort_registry import cohort_key
    assert cohort_key("bullish", "bull_quiet") == "bullish|bull_quiet"
```

- [ ] **Step 2: Build the fixture honestly**

The two arms must differ in **exactly one thing**: the flag. Same cached bars, same
`asof`, same account state, same seeds. If `run_scan_once` reaches the network,
stub the fetch layer — a differential whose arms fetch independently can diverge
for a reason that is not the feature, and would then be diagnosed for hours.

The vacuity guard in test 2 is not optional. A fixture where no inverse alert ever
fires makes test 1 pass for free and proves nothing. If the cached window never
produces one, pick a 2022 slice — the spec's synthetic evidence had bull_regime
passing 50.6% on -1x SPY in 2022 and ~0% everywhere else.

- [ ] **Step 3: Run and commit**

```bash
python scripts/dev/testrun.py file tests/scanning/test_inverse_differential.py
git add tests/scanning/test_inverse_differential.py
git commit -m "test(v98): differential proof that the inverse basket leaves long alerts identical"
```

### Task D15: Closed-book invariance

Per **DISC-3**: the spec's N=158 / WR 62.0% / +1.537 had already moved to
161 / 62.73% / +1.6111 by the time this plan was written, because the book is live
and grows every session. Asserting frozen absolute numbers would go red within a
day for a reason that has nothing to do with this plan. Assert the property the
spec actually wants instead: **no already-closed trade's outcome changes.**

**Files:**
- Create: `tests/tracking/test_closed_book_invariance.py`
- Create: `tests/fixtures/v98_closed_book_snapshot.json`

- [ ] **Step 1: Freeze the snapshot**

```bash
python -c "
import json, pathlib
j = json.load(open('data/journal.json'))
dec = [{'trade_id': e['trade_id'], 'r_realized': e['r_realized'],
        'outcome': e.get('outcome'), 'direction': e.get('direction'),
        'ticker': e.get('ticker')}
       for e in j if e.get('r_realized') is not None]
snap = {'taken': '2026-09-21', 'n_decided': len(dec),
        'win_rate': round(100*sum(1 for e in dec if e['r_realized']>0)/len(dec), 4),
        'mean_r': round(sum(e['r_realized'] for e in dec)/len(dec), 6),
        'trades': sorted(dec, key=lambda e: e['trade_id'])}
pathlib.Path('tests/fixtures/v98_closed_book_snapshot.json').write_text(
    json.dumps(snap, indent=2) + '\n', encoding='utf-8')
print(snap['n_decided'], snap['win_rate'], snap['mean_r'])
"
```

Record the printed triple in the test's docstring, and in D11's results document,
as **the figures as of the snapshot date** — not as a permanent invariant.

- [ ] **Step 2: Write the test**

```python
"""v98 closed-book invariance.

The spec asks to "re-derive the closed book and assert N=158 / WR 62.0% /
ExpR +1.537 unchanged". Those figures were already stale hours later (161 /
62.73% / +1.6111) because the book is LIVE and grows every session -- see
DISC-3 in the plan. A frozen absolute N is a time bomb that goes red for an
innocent reason, so this asserts the property the spec actually wants: every
trade that was already decided when v98 started is still decided the same way,
and the pre-v98 book is still 100% bullish.
"""


def test_every_pre_v98_decided_trade_is_unchanged():
    snap = _load_snapshot()
    live = {e["trade_id"]: e for e in _load_journal()}
    for t in snap["trades"]:
        cur = live.get(t["trade_id"])
        assert cur is not None, f"{t['trade_id']} vanished from the journal"
        assert cur["r_realized"] == t["r_realized"]
        assert cur.get("outcome") == t["outcome"]


def test_the_snapshot_derives_the_recorded_headline_figures():
    """Guards the snapshot itself: if someone regenerates it, the numbers in
    the docstring and the results document must be regenerated with it."""
    snap = _load_snapshot()
    rs = [t["r_realized"] for t in snap["trades"]]
    assert len(rs) == snap["n_decided"]
    assert round(100 * sum(1 for r in rs if r > 0) / len(rs), 4) == snap["win_rate"]
    assert round(sum(rs) / len(rs), 6) == snap["mean_r"]


def test_the_pre_v98_book_is_entirely_bullish_equity():
    """The v98 baseline: 0 bearish trades, and no inverse instrument in the
    book before this plan. A failure here means the snapshot was taken after
    the basket started trading and is not a baseline."""
    from swingbot.core.market.populations import EQUITY, population_of
    for t in _load_snapshot()["trades"]:
        assert t["direction"] == "bullish"
        assert population_of(t["ticker"]) == EQUITY


def test_inverse_trades_are_excluded_from_the_equity_book_metrics():
    """The forward-looking half: once the basket trades, an inverse trade must
    not land in the equity population's pooled numbers."""
    ...
```

- [ ] **Step 3: Run and commit**

```bash
python scripts/dev/testrun.py file tests/tracking/test_closed_book_invariance.py
git add tests/tracking/test_closed_book_invariance.py tests/fixtures/v98_closed_book_snapshot.json
git commit -m "test(v98): closed-book invariance by per-trade snapshot, not a frozen N"
```

### Task D16: Pre-merge precondition gate

Default-on moves the safety checkpoint **before** the merge. There is no post-merge
checkpoint to fall back on: the operator places resting broker orders from alerts,
so these become real-money-actionable the moment this branch lands on `main`.

**All three must hold. If any one fails, nothing ships and the flag does not exist.**

- [ ] **Precondition 1 — Q-INV cleared, per instrument AND pooled.**
      Open `docs/superpowers/results/2026-09-21-v98-q-inv-train.md` and read the
      per-instrument table. Confirm all four of PSQ/SH/RWM/DOG clear on their own,
      and that the pooled figures clear. **Do not accept a pooled PASS carrying a
      failing instrument** — that is the exact thing the rule forbids. Record the
      four verdicts here by name.

- [ ] **Precondition 2 — the differential test passes.**
      `python scripts/dev/testrun.py file tests/scanning/test_inverse_differential.py`
      Confirm the vacuity guard
      (`test_the_flag_on_arm_actually_emitted_something_inverse`) passed too — a
      green differential with no inverse alerts in the fixture proves nothing.

- [ ] **Precondition 3 — all four isolation requirements landed.**
      ```bash
      git log --oneline main..HEAD | grep -E "v98"
      ```
      Confirm commits exist for D2 (cohort key), D3 (badge drift), D4 (sub-cap) and
      D5 (overlay). Then confirm the registry was **not** regenerated:
      ```bash
      git log --oneline -- swingbot/core/backtesting/cohort_registry.json
      ```
      The newest commit here must predate this branch. If the registry was
      regenerated mid-plan, revert that file to its pre-branch state and
      re-verify — a registry emitted before D2 landed has equity cells banded
      against a diluted pool.

- [ ] **Step 4: Record the gate result**

Append a short "pre-merge gate" section to
`docs/superpowers/results/2026-09-21-v98-q-inv-train.md` listing all three
preconditions, each with the evidence that satisfied it (the four instrument
verdicts, the test run's verdict line, the four commit hashes). Commit it. A later
session must be able to see that this gate was actually run, not asserted.

### Task D17: Documentation and the production mirror

**Files:**
- Modify: `README.md` (the rollout-flags list)
- Modify: `docs/features/features.md` (or the matching topic file)
- Modify: `docs/claude/architecture.md` (one line on `populations.py`)
- Modify: `.codex/AGENTS.md` **only if** a rule here needs to reach it

- [ ] **Step 1: Document the flag**

Add `INVERSE_INSTRUMENTS_ENABLED` (default **on**) and `INVERSE_MAX_CONCURRENT`
(default 4) to the README's rollout-flags list beside `PLAN_ENGINE_V2`,
`SCALE_OUT_ENABLED` and `INTRADAY_MANAGER_V2`. State in one clause that the flag is
a **kill switch**, not a rollout gate — off restores an equities-only universe
exactly.

- [ ] **Step 2: One architecture line**

In `docs/claude/architecture.md`, beside the "Entry signals have a single source"
bullet:

> **Populations (v98):** `swingbot/core/market/populations.py` is the single source
> for whether a symbol is an equity or part of the inverse basket. The cohort
> registry key, badge drift, the open-slot warning and the per-symbol horizon
> overlay all read it. `SYMBOL_HORIZON_OVERLAY` in `strategy_types.py` is resolved
> at call time inside `entries_for` and never written into `STRATEGY_GATES`.

- [ ] **Step 3: Mirror to production**

Deploying this needs `INVERSE_INSTRUMENTS_ENABLED=true` in the VM's `.env`. Per
`CLAUDE.md`, **any live change must be mirrored back into this repo and committed
before the task is done.** The default is already `true` in the schema, so the
cleanest path is to change nothing on the VM and let the default apply — verify
that after deploy with `/config` or the admin UI rather than editing `.env` by hand.
If `.env` is edited on the VM, mirror it back here in the same session (see
`docs/claude/working-conventions.md` and the `mirror-prod` skill).

- [ ] **Step 4: Bump `VERSION.json`**

At close-out, **read `VERSION.json` from disk** — never this header, never memory —
increment the `bot` line at the **minor** level, set its `*_updated` stamp, then
regenerate and commit the version history with the bump:

```bash
python scripts/dev/build_version_matrix.py
```

The local gate runs before the bump and structurally cannot catch a missed
regeneration; this step is the only thing that does.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/features/features.md docs/claude/architecture.md \
        VERSION.json data/version_history.json
git commit -m "docs(v98): document the inverse basket flag, population source and kill switch"
```

---

# Phase 4 — Verification

### Task D18: Full-suite verification

- [ ] **Step 1: One full run**

Run `python scripts/dev/testrun.py full`, or dispatch the `test-runner` subagent so
~1150 progress lines never enter this context. **Once**, over everything this plan
implemented. Expect `0 failed`, `0 xfailed`. A *changed* pass count is not a
failure — this plan adds test files.

This plan touches no `frontend/` file, so there is no `npm test` run.

- [ ] **Step 2: Fix forward from whatever it names**

A red result here is the start of the work, not a reason to re-litigate an earlier
task. These are this plan's regressions; fix from the failures the run names. The
highest-risk sites, in order: `entry_filters.entries_for`'s new keyword against its
12 existing call sites, `scan_run.py`'s replaced warning block, and
`calibration.badge_drift`'s new filter against the existing analytics tests.

- [ ] **Step 3: Do not re-run after merging**

Per `docs/claude/document-conventions.md`: the branch was green when the merge
started, and a conflict-free merge does not produce code nobody ran. The one
exception is a merge that actually resolved conflicts — that resolution is new,
unrun code and gets the one run.

- [ ] **Step 4: Close the plan out**

Move this file to `docs/superpowers/plans/implemented/` on a PASS, or to
`plans/no-lift/` on a D11 FAIL, per `docs/claude/document-lifecycle.md`. Amend the
`Bump:` header in the closing commit if the level came out differently than
predicted, with one clause saying why.
