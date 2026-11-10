"""v209 V209-12: the detector replayed over the frozen 2026-11-05 session.

Built by scripts/data/build_shock_replay_fixture.py. A missing fixture
fails: this test never skips (spec, Track 1 tests)."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

from swingbot.core.market import shock

UTC = timezone.utc
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "shock_replay_2026_11_05.json"
SESSION = date(2026, 11, 5)
DEADLINE = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


def _fixture() -> dict:
    assert FIXTURE.exists(), "run scripts/data/build_shock_replay_fixture.py (V209-12)"
    return json.loads(FIXTURE.read_text())


def _row(d):
    return shock.NameRow(**d) if d else None


def _snapshot(step) -> shock.ShockSnapshot:
    as_of = datetime.fromisoformat(step["as_of"])
    vix = shock.VixTape(step["vix"]["level"], step["vix"]["chg_pct"], as_of)
    return shock.ShockSnapshot(
        as_of=as_of, session_date=SESSION, minutes_since_open=step["minutes_since_open"],
        names=tuple(_row(n) for n in step["names"]), spy=_row(step["spy"]),
        qqq=_row(step["qqq"]), vix=vix)


def _replay(fx, th=shock.ShockThresholds()):
    state, prev, out = shock.ShockState(), None, []
    for step in fx["steps"]:
        reading = shock.measure(_snapshot(step), prev, th)
        state, prev = shock.step(state, reading, th), reading
        out.append((reading, state.label))
    return out


def _first_shock(fx) -> datetime:
    return next(r.as_of for r, label in _replay(fx) if label == "SHOCK")


def test_the_fixture_has_the_frozen_shape():
    fx = _fixture()
    assert fx["source"] in ("alpaca", "synthetic") and fx["vix_interpolated"] is True
    assert isinstance(fx["note"], str) and fx["note"]
    times = [datetime.fromisoformat(s["as_of"]) for s in fx["steps"]]
    assert times == sorted(times) and len(times) == 26
    assert times[0] == datetime(2026, 11, 5, 14, 45, tzinfo=UTC)
    assert times[-1] == datetime(2026, 11, 5, 21, 0, tzinfo=UTC)


def test_every_reading_up_to_the_deadline_is_sufficient():
    early = [r for r, _ in _replay(_fixture()) if r.as_of <= DEADLINE]
    assert early and not any(r.insufficient for r in early)


def test_the_detector_reaches_shock_no_later_than_fifteen_hundred_utc():
    assert _first_shock(_fixture()) <= DEADLINE


def test_settle_and_two_readings_still_hold_on_the_day():
    # 15:00 is the earliest SHOCK the spec's rules allow on 15-minute steps
    assert _first_shock(_fixture()) >= DEADLINE


def test_report_the_longs_opened_before_the_first_shock(capsys):
    fx = _fixture()
    first = _first_shock(fx)
    entries = fx["long_entries"]
    before = [e for e in entries if datetime.fromisoformat(e["opened_at"]) < first]
    assert 0 <= len(before) <= len(entries)
    with capsys.disabled():
        print(f"\nv209 replay ({fx['source']}): {len(before)} of {len(entries)} longs "
              f"opened at/after 14:36 UTC opened before the first SHOCK at {first:%H:%M} UTC")
