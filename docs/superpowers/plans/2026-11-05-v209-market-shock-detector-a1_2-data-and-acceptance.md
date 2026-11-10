# v209 Amendment A1 — part 2: the frozen data run and the one-shot acceptance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md), § Amendment A1 (Validation set, Acceptance), § Panel review (A1)
**Index:** [`_0-index.md`](2026-11-05-v209-market-shock-detector-a1_0-index.md) — Global Constraints, Review Focus, Parallelisation and the task ledger apply to every task below.
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector-a1.md`

All work happens in the worktree `.claude/worktrees/2026-11-05-v209-market-shock-detector`
(`cd` there first). V209-A1-3 needs V209-A1-2 and V209-A1-2b committed on the
branch; V209-A1-4 needs V209-A1-1 and V209-A1-3.

**Pre-registration order, binding:** the day list is committed (V209-A1-3
Step 2) before any validation fixture is fetched, and the detector runs on a
validation day only inside V209-A1-4's acceptance run. Nothing in this part
reads a detector output to choose, keep or drop a day.

# Phase A1-C — the data run

### Task V209-A1-3: Freeze the day list, fetch and commit the validation fixtures

**Model:** sonnet — an operational run of finished tools; the judgement is keeping every failure on the record.

**Files:**
- Create: `tests/fixtures/shock_replay/validation_days.json` (written by `scripts/data/shock_validation_days.py`)
- Create: `tests/fixtures/shock_replay/<YYYY-MM-DD>.json.gz`, one per listed day (26), written by `scripts/data/build_shock_replay_fixture.py --validation-days`

**Interfaces:**
- Consumes: V209-A1-2 (`shock_validation_days.main`, the day-list JSON), V209-A1-2b (`run_validation`, `--unbuildable`, the day-fixture JSON, `fixture_tickers(DEFAULT_OUT)` = the 87-name 2026-11-05 watchlist).
- Produces: the committed list and 26 committed day fixtures that V209-A1-4 replays. No detector call happens here.

**Rules:**
- Never edit, regenerate or hand-pick the list; the selector refuses to overwrite it. A `ValueError` from a short class is a stop: report it, do not relax a rule.
- A day the builder writes as `unbuildable` stays so. A day that raises on three consecutive restarts is recorded with `--unbuildable <iso> --reason "<last error>"`, never skipped. No synthetic fixture is ever written for a validation day.
- The raw cache (`market_data/shock_replay/`) is gitignored and never committed.
- The run is long (about 26 days × 89 tickers × 2 fetches at `RATE_PER_MINUTE = 120`, roughly 40–50 minutes). It checkpoints per (day, ticker) and per day and prints a percent, so run it in the background and restart it after any interruption; never rerun from scratch.

- [ ] **Step 1: Preconditions**

```bash
git log --oneline -4
git status --short
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
for f in data/market_data_pit/daily/SPY.csv data/market_data_pit/daily/QQQ.csv market_data/vix/VIX_daily.csv; do
  python - "$MAIN/$f" <<'PYEOF'
import sys, pandas as pd
df = pd.read_csv(sys.argv[1], parse_dates=["Date"])
w = df[(df.Date >= "2022-12-01") & (df.Date <= "2025-12-31")]
print(sys.argv[1].split("/")[-1], len(w), w.Date.min().date(), w.Date.max().date())
PYEOF
done
test ! -e tests/fixtures/shock_replay/validation_days.json && echo "no list yet"
```

Expected: the V209-A1-2 and V209-A1-2b commits on top, a clean tree, about 770 rows per series spanning 2022-12-01..2025-12-31, and `no list yet`. Any series short of 2025-12-31: stop and report.

- [ ] **Step 2: Freeze the day list and commit it alone**

```bash
python scripts/data/shock_validation_days.py
python - <<'PYEOF'
import json
d = json.load(open("tests/fixtures/shock_replay/validation_days.json", encoding="utf-8"))
sizes = {k: len(v) for k, v in d["classes"].items()}
every = [x for v in d["classes"].values() for x in v]
assert sizes == {"shock": 6, "hard": 4, "rotation": 4, "calm": 12}, sizes
assert len(set(every)) == 26 and all("2023-01-02" <= x <= "2025-12-31" for x in every)
for k, v in d["classes"].items():
    print(k, " ".join(v))
PYEOF
git add tests/fixtures/shock_replay/validation_days.json
git commit -m "data(v209): freeze the A1 validation day list -- 26 days from daily SPY/QQQ/VIX, before any fetch or run"
```

Expected: four class lines and a commit. Copy the four lines into `.superpowers/sdd/progress.md` with the commit sha. The sha is the pre-registration record V209-A1-4 checks.

- [ ] **Step 3: Fetch the fixtures (background, checkpointed)**

Alpaca keys come from `.env` the way the V209-12 build loaded them (never printed). Run with `run_in_background`:

```bash
python scripts/data/build_shock_replay_fixture.py --validation-days tests/fixtures/shock_replay/validation_days.json
```

Expected progress lines `[i/26 pct%] <iso> <class> alpaca|unbuildable <n> steps`, ending without a traceback. Exit 2 with an `AlpacaAuthError` message means keys are missing: fix the environment, then rerun (nothing was written). On any other traceback, rerun the same command: finished days and cached tickers are skipped. If the same day raises on three consecutive runs:

```bash
python scripts/data/build_shock_replay_fixture.py --validation-days tests/fixtures/shock_replay/validation_days.json --unbuildable <iso> --reason "<exception class>: <message>"
```

then rerun the main command for the remaining days.

- [ ] **Step 4: Verify the set without replaying it**

```bash
python - <<'PYEOF'
import gzip, json, pathlib
root = pathlib.Path("tests/fixtures/shock_replay")
days = json.load(open(root / "validation_days.json", encoding="utf-8"))["days"]
total = 0
for iso in sorted(days):
    path = root / f"{iso}.json.gz"
    fx = json.loads(gzip.decompress(path.read_bytes()))
    total += path.stat().st_size
    eq = sum(n["is_equity"] for n in fx["steps"][0]["names"]) if fx["steps"] else 0
    assert fx["session_date"] == iso and fx["class"] == days[iso]["class"]
    assert fx["source"] in ("alpaca", "unbuildable")
    print(iso, fx["class"], fx["source"], len(fx["steps"]), eq, fx["open_utc"][11:16])
print("files", len(days), "bytes", total)
PYEOF
git check-ignore market_data/shock_replay
```

Expected: 26 lines, each `alpaca` day with 26 steps (14 on a half day) and its open at 13:30 or 14:30; total size printed (expect low single-digit MB); `git check-ignore` prints the cache path. Do **not** compute breadth, call `shock.measure` or look at the detector on these files. Record the per-day `source` column and the total size in `.superpowers/sdd/progress.md`; any `unbuildable` day is listed with its note.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/shock_replay/*.json.gz
git commit -m "data(v209): A1 validation fixtures -- 26 days, <a> alpaca, <u> unbuildable"
```

(Fill `<a>`/`<u>` from Step 4.)

# Phase A1-D — the acceptance

### Task V209-A1-4: A1 acceptance test (rewrite of V209-12b)

**Model:** opus — statistical code that is the one-shot gate deciding whether v209 ships or closes `no-lift/`.

**Files:**
- Create: `tests/market/test_shock_acceptance_a1.py`, by `git mv tests/market/test_shock_replay_2026_11_05.py tests/market/test_shock_acceptance_a1.py` (on the v209 branch), then rewritten whole (suite `market-signals`; no `suites.toml` change)
- Modify: `scripts/dev/select_tests.py` (the two rows V209-A1-2b added: target renamed)
- Modify: `tests/dev/test_select_tests.py` (`test_shock_replay_fixtures_route_to_the_replay_test`: target renamed)

**Interfaces:**
- Consumes: V209-A1-1's detector (`ShockThresholds()` defaults, `measure`, `step`, `ShockState`); V209-A1-3's committed list and day fixtures (shape in the index ledger, V209-A1-2b row); the legacy `tests/fixtures/shock_replay_2026_11_05.json` (V209-12 shape plus `long_entries`).
- Produces: the verdict. PASS: the parent plan's V209-13 proceeds. FAIL: stop and report; the controller closes v209 (and v210) to `no-lift/`, and v211 goes to the partner.

**Rules (spec A1 § Acceptance, verbatim):**
- Every day replays from a fresh `ShockState()` with `ShockThresholds()`; each step's VIX is stamped with the step's own `as_of`.
- **Hit** (shock class) = fixture built, no reading `insufficient`, SHOCK reached. **False fire** (calm, rotation, hard) = fixture unbuildable, or any reading `insufficient`, or SHOCK reached.
- Gates: hits ≥ 5 of 6; false fires ≤ 1 of 12 calm, ≤ 1 of 4 rotation, ≤ 1 of 4 hard; on every built day and on 2026-11-05, a first SHOCK is never earlier than open + 30 min (15:00 UTC on a 14:30 open).
- Reported, never gated: 2026-11-05's first SHOCK (in-sample) and the longs-opened-before-SHOCK line; per shock day the first-SHOCK time, the share of the day's SPY drop (prior close to close) still ahead at that moment, and the SHOCK dwell; the grind/flush mix (flush = the opening gap is at least half the prior-close-to-close drop) and the clustering (calendar days between consecutive shock days); the power caveat.
- Run the gated tests **once**. A red gate is a measured answer: no threshold change, refetch, regenerated list, new fixture or second run with changes. Old V209-12b's `≤ 15:00` 11-05 gate and its "synthetic" escape are gone (spec A1, panel).

- [ ] **Step 1: Check the pre-registration order**

```bash
git log --oneline --follow -- tests/fixtures/shock_replay/validation_days.json
git log --oneline -- tests/fixtures/shock_replay/*.json.gz
```

Expected: exactly one commit for the list (the freeze sha in `.superpowers/sdd/progress.md`), older than the fixtures commit. Anything else: stop and report.

- [ ] **Step 2: Rename and write the test**

```bash
git mv tests/market/test_shock_replay_2026_11_05.py tests/market/test_shock_acceptance_a1.py
```

`tests/market/test_shock_acceptance_a1.py`, whole:

```python
"""v209 A1 acceptance: the re-registered detector over the frozen validation days.

One shot (spec § Amendment A1, Acceptance). scripts/data/shock_validation_days.py
froze the day list; scripts/data/build_shock_replay_fixture.py --validation-days
built one fixture per day (V209-A1-3). A missing fixture fails. An unbuildable
day, or a day with any insufficient reading, scores against its class. 2026-11-05
is an in-sample fit check: reported, never gated. A red gate is a measured
answer: v209 closes no-lift; nothing is tuned, refetched or regenerated."""
import functools
import gzip
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from swingbot.core.market import shock

UTC = timezone.utc
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DAY_DIR = FIXTURES / "shock_replay"
DAY_LIST = DAY_DIR / "validation_days.json"
FIXTURE_1105 = FIXTURES / "shock_replay_2026_11_05.json"
CLASS_SIZES = {"shock": 6, "hard": 4, "rotation": 4, "calm": 12}
RECALL_MIN = 5
FALSE_FIRE_MAX = {"calm": 1, "rotation": 1, "hard": 1}
EARLIEST = timedelta(minutes=30)   # settle 15 min + two 15-minute readings


@dataclass(frozen=True)
class DayResult:
    day: str
    cls: str
    buildable: bool
    insufficient: bool
    open_utc: datetime | None
    first_shock: datetime | None
    dwell_min: float | None
    spy_at_shock: float | None


def _row(d):
    return shock.NameRow(**d) if d else None


def _snapshot(step, session_date: date) -> shock.ShockSnapshot:
    as_of = datetime.fromisoformat(step["as_of"])
    vix = shock.VixTape(step["vix"]["level"], step["vix"]["chg_pct"], as_of)
    return shock.ShockSnapshot(
        as_of=as_of, session_date=session_date, minutes_since_open=step["minutes_since_open"],
        names=tuple(_row(n) for n in step["names"]), spy=_row(step["spy"]),
        qqq=_row(step["qqq"]), vix=vix)


def replay(fx: dict, session_date: date) -> list[tuple[shock.ShockReading, str]]:
    th, state, prev, out = shock.ShockThresholds(), shock.ShockState(), None, []
    for step in fx["steps"]:
        reading = shock.measure(_snapshot(step, session_date), prev, th)
        state, prev = shock.step(state, reading, th), reading
        out.append((reading, state.label))
    return out


def _dwell(out, first: datetime | None, close: datetime) -> float | None:
    if first is None:
        return None
    left = [r.as_of for r, label in out if r.as_of > first and label != "SHOCK"]
    return ((left[0] if left else close) - first).total_seconds() / 60.0


def _when(fx: dict, key: str) -> datetime | None:
    return datetime.fromisoformat(fx[key]) if fx.get(key) else None


def score_day(fx: dict, day: str, cls: str) -> DayResult:
    if fx.get("source") == "unbuildable" or not fx.get("steps"):
        return DayResult(day, cls, False, False, _when(fx, "open_utc"), None, None, None)
    out = replay(fx, date.fromisoformat(day))
    shocked = [r for r, label in out if label == "SHOCK"]
    first = shocked[0].as_of if shocked else None
    close = _when(fx, "close_utc") or out[-1][0].as_of
    return DayResult(day, cls, True, any(r.insufficient for r, _ in out), _when(fx, "open_utc"),
                     first, _dwell(out, first, close), shocked[0].spy_last if shocked else None)


def is_hit(r: DayResult) -> bool:
    return r.buildable and not r.insufficient and r.first_shock is not None


def is_false_fire(r: DayResult) -> bool:
    return not r.buildable or r.insufficient or r.first_shock is not None


def too_early(r: DayResult) -> bool:
    return (r.first_shock is not None and r.open_utc is not None
            and r.first_shock < r.open_utc + EARLIEST)


def lead_share(r: DayResult, spy: dict) -> float | None:
    """Share of the prior-close-to-close SPY drop still ahead at the first SHOCK."""
    drop = spy["prev_close"] - spy["close"]
    if r.spy_at_shock is None or drop <= 0:
        return None
    return (r.spy_at_shock - spy["close"]) / drop


def day_shape(spy: dict) -> str:
    drop = spy["prev_close"] - spy["close"]
    if drop <= 0:
        return "n/a"
    return "flush" if (spy["prev_close"] - spy["open"]) / drop >= 0.5 else "grind"


# --- the frozen data ---------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _day_list() -> dict:
    assert DAY_LIST.exists(), "V209-A1-3 freezes the day list"
    return json.loads(DAY_LIST.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def _day_fixture(day: str) -> dict:
    path = DAY_DIR / f"{day}.json.gz"
    assert path.exists(), f"{path.name} missing: V209-A1-3 builds it"
    return json.loads(gzip.decompress(path.read_bytes()))


@functools.lru_cache(maxsize=1)
def _results() -> tuple[DayResult, ...]:
    days = _day_list()["days"]
    return tuple(score_day(_day_fixture(d), d, days[d]["class"]) for d in sorted(days))


def _of(cls: str) -> list[DayResult]:
    return [r for r in _results() if r.cls == cls]


def _fixture_1105() -> dict:
    assert FIXTURE_1105.exists(), "V209-12's frozen 2026-11-05 fixture"
    fx = json.loads(FIXTURE_1105.read_text(encoding="utf-8"))
    return {**fx, "open_utc": "2026-11-05T14:30:00+00:00", "close_utc": "2026-11-05T21:00:00+00:00"}


def _fmt(r: DayResult) -> str:
    if not r.buildable:
        return f"{r.day} {r.cls:8} unbuildable"
    first = f"{r.first_shock:%H:%M}Z +{(r.first_shock - r.open_utc).total_seconds() / 60:.0f}m" \
        if r.first_shock else "never"
    return (f"{r.day} {r.cls:8} first SHOCK {first:>14}  dwell {r.dwell_min or 0:5.0f}m"
            f"{'  INSUFFICIENT' if r.insufficient else ''}")


def _table(rows) -> str:
    return "\n".join(_fmt(r) for r in rows)


# --- scoring rules on synthetic days ----------------------------------------

OPEN = datetime(2025, 7, 15, 13, 30, tzinfo=UTC)
SPY_ROW = {"ticker": "SPY", "sector": None, "last": 500.0, "prev_close": 500.0, "atr14": 5.0,
           "is_equity": False}


def _name(i: int, down: bool) -> dict:
    return {"ticker": f"N{i:02d}", "sector": f"S{i % 3}", "last": 98.0 if down else 100.0,
            "prev_close": 100.0, "atr14": 2.0, "is_equity": True}


def _fx(downs, thin_at=None) -> dict:
    steps = [{"as_of": (OPEN + timedelta(minutes=15 * (k + 1))).isoformat(),
              "minutes_since_open": 15.0 * (k + 1), "vix": {"level": 20.0, "chg_pct": 0.0},
              "spy": SPY_ROW, "qqq": None,
              "names": [_name(i, i < down) for i in range(10 if k == thin_at else 30)]}
             for k, down in enumerate(downs)]
    return {"source": "alpaca", "open_utc": OPEN.isoformat(),
            "close_utc": (OPEN + timedelta(minutes=390)).isoformat(), "steps": steps}


def test_a_clean_majority_day_is_a_hit_at_the_earliest_allowed_reading():
    r = score_day(_fx([0, 18, 18, 18]), "2025-07-15", "shock")
    assert r.first_shock == OPEN + timedelta(minutes=45) and is_hit(r) and not too_early(r)
    assert r.dwell_min > 0


def test_a_quiet_day_is_neither_a_hit_nor_a_false_fire():
    r = score_day(_fx([0] * 6), "2025-07-15", "calm")
    assert r.first_shock is None and not is_hit(r) and not is_false_fire(r)


def test_one_insufficient_reading_scores_against_the_class():
    r = score_day(_fx([0, 18, 18, 18], thin_at=0), "2025-07-15", "shock")
    assert r.insufficient and not is_hit(r) and is_false_fire(r)


def test_an_unbuildable_day_is_a_miss_and_a_false_fire():
    r = score_day({"source": "unbuildable", "steps": []}, "2025-07-15", "hard")
    assert not r.buildable and not is_hit(r) and is_false_fire(r)


def test_too_early_lead_share_and_shape():
    early = DayResult("d", "shock", True, False, OPEN, OPEN + timedelta(minutes=15), 30.0, 590.0)
    assert too_early(early)
    assert not too_early(DayResult("d", "shock", True, False, OPEN, OPEN + EARLIEST, 30.0, 590.0))
    assert lead_share(early, {"prev_close": 600.0, "open": 590.0, "close": 580.0}) == 0.5
    assert lead_share(early, {"prev_close": 600.0, "open": 600.0, "close": 605.0}) is None
    assert day_shape({"prev_close": 600.0, "open": 590.0, "close": 580.0}) == "flush"
    assert day_shape({"prev_close": 600.0, "open": 598.0, "close": 580.0}) == "grind"


# --- the frozen set ----------------------------------------------------------

def test_the_day_list_is_frozen_and_every_day_has_its_fixture():
    d = _day_list()
    assert d["window"] == ["2023-01-02", "2025-12-31"] and d["seed"] == 209
    assert {k: len(v) for k, v in d["classes"].items()} == CLASS_SIZES
    every = [x for v in d["classes"].values() for x in v]
    assert len(set(every)) == 26 and set(every) == set(d["days"])
    for day in every:
        fx = _day_fixture(day)
        assert fx["session_date"] == day and fx["class"] == d["days"][day]["class"]
        assert fx["source"] in ("alpaca", "unbuildable")


def test_the_2026_11_05_fixture_keeps_its_frozen_shape():
    fx = _fixture_1105()
    assert fx["source"] == "alpaca" and fx["vix_interpolated"] is True
    times = [datetime.fromisoformat(s["as_of"]) for s in fx["steps"]]
    assert times == sorted(times) and len(times) == 26
    assert (times[0], times[-1]) == (datetime(2026, 11, 5, 14, 45, tzinfo=UTC),
                                     datetime(2026, 11, 5, 21, 0, tzinfo=UTC))


def test_recall_at_least_five_of_six_shock_days():
    rows = _of("shock")
    assert sum(map(is_hit, rows)) >= RECALL_MIN, _table(rows)


@pytest.mark.parametrize("cls", sorted(FALSE_FIRE_MAX))
def test_false_fires_per_negative_class(cls):
    rows = _of(cls)
    assert sum(map(is_false_fire, rows)) <= FALSE_FIRE_MAX[cls], _table(rows)


def test_shock_never_comes_within_thirty_minutes_of_the_open():
    rows = [*_results(), score_day(_fixture_1105(), "2026-11-05", "in-sample")]
    assert not [r for r in rows if too_early(r)], _table(rows)


def _shock_day_lines(days: dict) -> list[str]:
    out = []
    for r in _of("shock"):
        spy = days[r.day]
        share = lead_share(r, {"prev_close": spy["spy_prev_close"], "open": spy["spy_open"],
                               "close": spy["spy_close"]})
        shape = day_shape({"prev_close": spy["spy_prev_close"], "open": spy["spy_open"],
                           "close": spy["spy_close"]})
        ahead = f"{share:.0%} of the drop still ahead" if share is not None else "no SHOCK"
        out.append(f"  {r.day} SPY {spy['spy_ret']:+.2f}% {shape:5}  {ahead}")
    return out


def _clustering() -> str:
    shock_days = sorted(date.fromisoformat(d) for d in _day_list()["classes"]["shock"])
    gaps = [(b - a).days for a, b in zip(shock_days, shock_days[1:])]
    return f"calendar days between consecutive shock days: {gaps}"


def _longs_line(r: DayResult, fx: dict) -> str:
    entries = fx.get("long_entries", [])
    if r.first_shock is None:
        return f"2026-11-05 (in-sample): no SHOCK; all {len(entries)} post-turn longs opened without one"
    before = [e for e in entries if datetime.fromisoformat(e["opened_at"]) < r.first_shock]
    return (f"2026-11-05 (in-sample): first SHOCK {r.first_shock:%H:%M} UTC; {len(before)} of "
            f"{len(entries)} longs opened at/after 14:36 UTC came before it")


def test_report_the_a1_validation(capsys):
    days = _day_list()["days"]
    hits = sum(map(is_hit, _of("shock")))
    fires = {c: sum(map(is_false_fire, _of(c))) for c in FALSE_FIRE_MAX}
    passed = hits >= RECALL_MIN and all(fires[c] <= FALSE_FIRE_MAX[c] for c in fires)
    fx = _fixture_1105()
    r1105 = score_day(fx, "2026-11-05", "in-sample")
    shapes = [day_shape({"prev_close": days[d]["spy_prev_close"], "open": days[d]["spy_open"],
                         "close": days[d]["spy_close"]}) for d in _day_list()["classes"]["shock"]]
    lines = ["", "v209 A1 acceptance (one shot)", _table(_results()), "shock days:",
             *_shock_day_lines(days),
             f"mix: {shapes.count('flush')} flush / {shapes.count('grind')} grind; {_clustering()}",
             f"recall {hits}/6 (gate >= 5); false fires calm {fires['calm']}/12, "
             f"rotation {fires['rotation']}/4, hard {fires['hard']}/4 (gate <= 1 each)",
             _longs_line(r1105, fx),
             f"verdict: {'PASS' if passed else 'FAIL'} -- N = 6 recall days and 20 negatives: "
             "a sanity screen, not proof"]
    with capsys.disabled():
        print("\n".join(lines))
```

In `scripts/dev/select_tests.py`, both A1 rows target `"tests/market/test_shock_acceptance_a1.py"` instead of the old file; in `tests/dev/test_select_tests.py`, `test_shock_replay_fixtures_route_to_the_replay_test`'s `target` becomes the same path.

- [ ] **Step 3: Run the scoring-rule tests alone first**

```bash
python -m pytest tests/market/test_shock_acceptance_a1.py -v -k "clean_majority or quiet_day or insufficient_reading or unbuildable_day or too_early_lead"
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
```

Expected: the five scoring tests PASS and `test_select_tests.py` is green. A scoring test that fails is a bug in the test helpers or in V209-A1-1. Fix that before Step 4, because nothing has looked at a validation day yet.

- [ ] **Step 4: The one-shot run**

```bash
python -m pytest tests/market/test_shock_acceptance_a1.py -v -s
```

Copy the whole report block (the per-day table through the `verdict:` line) verbatim into `.superpowers/sdd/progress.md` under `V209-A1-4 acceptance (one shot)`, with the HEAD sha.

- **PASS** (every gated test green, `0 failed`, `0 xfailed`): go to Step 5.
- **FAIL** (any of recall, the three false-fire caps or the 30-minute invariant red): go to Step 5 anyway. Commit the test unchanged as the record, do **not** merge the branch, and report to the controller: the report block, which gate failed, and "v209 closes no-lift (v210 with it); v211 is the partner's call (spec A1)". Do not touch a threshold, fixture, list or rule, and do not rerun with a change.
- A test that errors (a missing fixture, a `KeyError` in a fixture) is not a verdict. Fix the setup (V209-A1-3's output), then rerun Step 4 once; record both runs.

- [ ] **Step 5: Complexity gate and commit**

```bash
python scripts/dev/complexity_gate.py
git add tests/market/test_shock_acceptance_a1.py scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "test(v209): A1 one-shot acceptance over the frozen validation days -- <PASS|FAIL> (recall <h>/6, false fires <c>/12 <r>/4 <x>/4)"
```

Fill the subject from the report. On FAIL the branch stays unmerged, and the controller's `/close-out` moves both v209 stems to `no-lift/`.

