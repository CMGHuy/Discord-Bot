# v171 D9 baseline week (count-only)

Window 2026-10-21..2026-10-27 (five in-session trading days, 7 hours each, all counted). Switch to `MARKETDATA_LAYER=count` at V171-36: 2026-10-20. No replacement days were needed. The tape sampler was not installed during this window, so tape coverage is 0 and the blank-tape check is UNMEASURED for the baseline (it is a week-only check, measured from the staging week on).

| Field | Value |
|---|---|
| calls.hours / calls.calls / calls.mean | 35 / 114870 / 3282.0 |
| by_provider | alpaca=114166, yfinance=704 |
| by_kind | quote=114158, earnings=704, intraday=8 |
| by_asker | admin_page=42762, scan=37173, stop_monitor=32265, admin_fresh=2011, background=659 |
| by_outcome | fetched=114768, failed=102 |
| scan.scans / tickers / errors / data_skips / per_ticker | 883 / 67991 / 12 / 1118 / 0.01662 |

Baseline numbers the success check compares against:

- `calls_per_hour baseline = 3282.0` (success threshold: at most 1641.0)
- `errors_per_ticker baseline = 0.01662`

Full JSON (`logs/v171_baseline.json` on the VM):

```json
{
  "since": "2026-10-21",
  "until": "2026-10-27",
  "week": {
    "calls": {
      "hours": 35,
      "calls": 114870,
      "mean": 3282.0,
      "by_provider": {
        "alpaca": 114166,
        "yfinance": 704
      },
      "by_kind": {
        "quote": 114158,
        "earnings": 704,
        "intraday": 8
      },
      "by_asker": {
        "admin_fresh": 2011,
        "admin_page": 42762,
        "scan": 37173,
        "stop_monitor": 32265,
        "background": 659
      },
      "by_outcome": {
        "failed": 102,
        "fetched": 114768
      },
      "days": {
        "2026-10-21": 7,
        "2026-10-22": 7,
        "2026-10-23": 7,
        "2026-10-26": 7,
        "2026-10-27": 7
      }
    },
    "scan": {
      "scans": 883,
      "tickers": 67991,
      "errors": 12,
      "data_skips": 1118,
      "per_ticker": 0.01662
    },
    "quotes": {
      "stamped": 0,
      "misses": 0,
      "max_s": null,
      "miss_ids": []
    },
    "rebuild": {
      "kept": 0,
      "dropped": 0,
      "misses": 0
    },
    "tape": {
      "samples": 0,
      "session_minutes": 1950,
      "coverage": 0.0,
      "blank_minutes": 0,
      "errors": 0
    }
  },
  "baseline": null,
  "checks": [
    {
      "check": "quote_age",
      "threshold": "0 plans over 5 s",
      "value": "0 of 0",
      "verdict": "UNMEASURED"
    },
    {
      "check": "blank_tape",
      "threshold": "0 blank minutes, coverage >= 95%",
      "value": "0 blank, coverage 0.0%",
      "verdict": "UNMEASURED"
    },
    {
      "check": "provider_429s",
      "threshold": "none new",
      "value": "see V171-39",
      "verdict": "UNMEASURED"
    },
    {
      "check": "errors_per_ticker",
      "threshold": "week <= baseline",
      "value": {
        "week": null,
        "baseline": null
      },
      "verdict": "UNMEASURED"
    },
    {
      "check": "calls_per_hour",
      "threshold": "week <= 0.5 x baseline",
      "value": {
        "week": 3282.0,
        "baseline": null
      },
      "verdict": "UNMEASURED"
    },
    {
      "check": "delta_parity",
      "threshold": "zero diffs",
      "value": "see V171-39",
      "verdict": "UNMEASURED"
    }
  ]
}
```
