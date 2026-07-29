#!/usr/bin/env python3
"""Build data/macro/event_history.json (2018 -> currently published future).

USAGE (network; NEVER imported by tests):
    FRED_API_KEY=... python scripts/build_event_history.py
    python scripts/build_event_history.py --fomc-only   # no key, no network

Sources:
- FOMC decision days: the Fed's published calendars --
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  (+ the "historical materials" pages for 2018-2020). These are the SECOND
  day of each two-day meeting (decision announced 14:00 ET). They were
  transcribed by hand: the validator below only checks the COUNT per year,
  so spot-check a few dates against the Fed's page before trusting them for
  anything that matters.
- CPI/PPI/NFP/PCE: fred_release_dates() -- release ids CPI=10, PPI=46,
  Employment Situation=50, Personal Income & Outlays=54; prints 08:30 ET.

--fomc-only writes the FOMC half without touching the network, so the
calendar is usable before a FRED key exists. Re-run without the flag once
a key is configured -- the file is rewritten whole, never appended to.
"""
import argparse
import datetime as dt
import sys

sys.path.insert(0, ".")

from swingbot.core.jsonio import atomic_write_json
from swingbot.core.macro.calendar_events import EVENTS_PATH, IMPORTANCE
from swingbot.core.macro.fred import fred_release_dates

FOMC_DECISION_DAYS: list[str] = [
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13",
    "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19",
    "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    # 2020: the scheduled Mar 17-18 meeting was replaced by the Mar 15
    # emergency cut; Mar 3 was also unscheduled. Nine entries by design.
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
    "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
    "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

RELEASES = {"cpi": 10, "ppi": 46, "nfp": 50, "pce": 54}


def _validate_fomc(days: list[str]) -> None:
    per_year: dict[str, int] = {}
    for d in days:
        dt.date.fromisoformat(d)                      # raises on a bad paste
        per_year[d[:4]] = per_year.get(d[:4], 0) + 1
    assert len(set(days)) == len(days), "duplicate FOMC dates"
    for year, n in sorted(per_year.items()):
        current = dt.date.today().year
        if int(year) < current:                        # future years may be partial
            assert 7 <= n <= 9, f"{year}: {n} FOMC days — check the paste"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fomc-only", action="store_true",
                    help="skip the FRED releases (no API key / no network)")
    args = ap.parse_args()

    assert FOMC_DECISION_DAYS, "paste the FOMC decision days first (see header)"
    _validate_fomc(FOMC_DECISION_DAYS)
    events = [{"date": d, "time_et": "14:00", "kind": "fomc",
               "label": "FOMC decision", "importance": 3}
              for d in FOMC_DECISION_DAYS]
    if args.fomc_only:
        print("--fomc-only: skipping CPI/PPI/NFP/PCE releases")
    else:
        for kind, release_id in RELEASES.items():
            dates = fred_release_dates(release_id, include_future=True)
            assert dates, f"no release dates for {kind} — check FRED_API_KEY"
            events += [{"date": d, "time_et": "08:30", "kind": kind,
                        "label": f"{kind.upper()} release",
                        "importance": IMPORTANCE[kind]}
                       for d in dates if d >= "2018-01-01"]
            print(f"  + {kind}: {len(dates)} release dates")
    events.sort(key=lambda e: (e["date"], e["kind"]))
    atomic_write_json(EVENTS_PATH, events)
    print(f"wrote {len(events)} events -> {EVENTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
