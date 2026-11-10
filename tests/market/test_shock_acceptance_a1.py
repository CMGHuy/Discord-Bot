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
