# v171 success week: not run (partner skipped it at close-out, 2026-11-04)

The plan's V171-39 one-week check against the spec's `## Success` table was skipped by the partner. The only
post-switch measurement is the staging report, 2026-10-29..2026-11-03, a window mixing layer-off and layer-on
days (VM `logs/v171_staging_cron.log`). Recorded as measured, never as a pass:

| Row | Threshold | Staging value | Verdict |
|---|---|---|---|
| Posted plans with quote age > 5 s | 0 | 0 of 20 (max 3.55 s) | PASS (staging) |
| Blank tape minutes in session | 0 | sampler not yet running | UNMEASURED |
| Alpaca / yfinance 429s | 0 | logs not read | UNMEASURED |
| Scan errors + data skips per ticker | not above baseline 0.0166 | 0.0262 | MISS (mixed window) |
| Provider calls per in-session hour | at most 0.5 x baseline (1641) | 2789 vs 3282 | MISS (mixed window) |
| Cache + delta vs full download, bar for bar | zero diffs | never run on production | UNMEASURED |

Rebuild in staging: kept 45, dropped 44, 0 quote misses.

The two MISS rows are not a clean verdict (the window is mixed), but the plan's main objective, halving provider
calls, is **not demonstrated**. Follow-up if wanted: run delta parity (a weekend), read the 429s, and read the
2026-11-04..11-10 report the VM cron still produces. Panel advisories carried are in `.superpowers/sdd/progress.md`.
