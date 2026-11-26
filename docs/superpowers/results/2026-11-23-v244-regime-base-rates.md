# v244 — SPY base rates under the v239 bear-regime rules (to 2026-11-20)

**Kind:** DESCRIPTION (ledger row `v244-regime-base-rates`). Describes SPY base rates, not a strategy: never a lift, selects nothing, moves no gate and spends no validation budget. The window spans TRAIN and VALIDATION; no figure here licenses B7–B9 (their screens decide). A later spec may cite only its N and coverage columns, never as evidence for a gate.
**Command:** `python scripts/research/regime_base_rates.py`
**End:** 2026-11-20 (fixed) · **Labelled sessions:** 1993-12-13 → 2026-11-20 (8292)
**Inputs:** `data/backtest_cache_regime/` · SPY sha256 `02d8dc5665a5a26122112c4b04a207b883e4048da932b7bb710f72b316a741dc` · ^VIX sha256 `6900aee90918862eabcddb84b4369e8768743d7f208f4066e5454689602c25f2`
**Rules:** `swingbot/core/market/bear_regime.py` (frozen, v239); episodes confirmed after 2 sessions (`regime_episodes`).
**Forward return:** percent change of SPY's adjusted close over `h` sessions. Episode rows run from the close of D (the episode's first day) to D + h: D is selected only once D+1 confirms it, and D+1's label reads close D. Pullback rows run from `s` (the bar before D, the close the label read) to `s + h`: the trigger reads only bars <= s. A day whose `h` runs past the last bar is dropped for that `h` only.

## Episodes per state

| Episode | Count | Median sessions | Q1 | Q3 |
| --- | --- | --- | --- | --- |
| BEAR | 31 | 21.0 | 5.5 | 40.0 |
| CORRECTION_STRESS | 27 | 5.0 | 3.0 | 9.0 |
| CORRECTION | 72 | 6.0 | 3.0 | 13.25 |
| NORMAL | 87 | 46.0 | 6.5 | 96.0 |
| UNKNOWN | 0 | n/a | n/a | n/a |

## CORRECTION → BEAR conversion

Spells 69 · resolved 68 · converted 12 · rate 0.176 · median sessions to switch 19.0

| Start | End | Sessions | Stress | Outcome | Next episode |
| --- | --- | --- | --- | --- | --- |
| 1994-03-09 | 1994-03-15 | 5 | False | normal | 1994-03-16 |
| 1994-03-25 | 1994-04-29 | 24 | False | bear | 1994-05-02 |
| 1994-11-21 | 1994-11-22 | 2 | False | bear | 1994-11-23 |
| 1996-05-07 | 1996-05-08 | 2 | False | normal | 1996-05-09 |
| 1996-07-16 | 1996-08-02 | 14 | False | normal | 1996-08-05 |
| 1997-04-03 | 1997-04-29 | 19 | False | normal | 1997-04-30 |
| 1997-10-31 | 1997-11-05 | 4 | True | normal | 1997-11-06 |
| 1997-12-24 | 1997-12-29 | 3 | True | normal | 1997-12-30 |
| 1998-08-06 | 1998-10-01 | 40 | True | bear | 1998-10-02 |
| 1999-06-01 | 1999-06-03 | 3 | True | normal | 1999-06-04 |
| 1999-06-25 | 1999-06-28 | 2 | False | normal | 1999-06-29 |
| 1999-09-15 | 1999-10-08 | 18 | True | normal | 1999-10-11 |
| 1999-10-14 | 1999-10-28 | 11 | True | normal | 1999-10-29 |
| 2000-02-01 | 2000-02-07 | 5 | False | normal | 2000-02-08 |
| 2000-02-16 | 2000-03-16 | 21 | True | normal | 2000-03-17 |
| 2000-05-30 | 2000-06-01 | 3 | False | normal | 2000-06-02 |
| 2000-09-21 | 2000-10-16 | 18 | True | bear | 2000-10-17 |
| 2004-03-23 | 2004-04-01 | 8 | False | normal | 2004-04-02 |
| 2004-04-21 | 2004-04-22 | 2 | False | normal | 2004-04-23 |
| 2004-04-29 | 2004-05-26 | 20 | False | normal | 2004-05-27 |
| 2004-07-09 | 2004-07-28 | 14 | False | normal | 2004-07-29 |
| 2004-08-09 | 2004-08-25 | 13 | False | normal | 2004-08-26 |
| 2005-01-28 | 2005-02-01 | 3 | False | normal | 2005-02-02 |
| 2005-03-17 | 2005-04-05 | 13 | False | normal | 2005-04-06 |
| 2005-04-18 | 2005-05-17 | 22 | False | normal | 2005-05-18 |
| 2005-09-27 | 2005-09-29 | 3 | False | normal | 2005-09-30 |
| 2005-10-05 | 2005-11-02 | 21 | False | normal | 2005-11-03 |
| 2006-05-23 | 2006-06-30 | 28 | False | normal | 2006-07-03 |
| 2006-07-10 | 2006-07-24 | 11 | False | normal | 2006-07-25 |
| 2007-03-05 | 2007-03-21 | 13 | False | normal | 2007-03-22 |
| 2007-07-31 | 2007-09-13 | 32 | True | normal | 2007-09-14 |
| 2007-11-15 | 2007-12-06 | 15 | True | normal | 2007-12-07 |
| 2007-12-12 | 2007-12-21 | 8 | False | normal | 2007-12-24 |
| 2010-02-01 | 2010-02-18 | 13 | True | normal | 2010-02-19 |
| 2010-05-21 | 2010-07-07 | 32 | True | bear | 2010-07-08 |
| 2011-06-09 | 2011-06-30 | 16 | False | normal | 2011-07-01 |
| 2011-07-28 | 2011-08-17 | 15 | True | bear | 2011-08-18 |
| 2012-05-14 | 2012-06-18 | 25 | True | normal | 2012-06-19 |
| 2012-06-22 | 2012-06-29 | 6 | False | normal | 2012-07-02 |
| 2012-11-12 | 2012-12-06 | 18 | False | normal | 2012-12-07 |
| 2013-10-09 | 2013-10-10 | 2 | False | normal | 2013-10-11 |
| 2014-02-04 | 2014-02-11 | 6 | False | normal | 2014-02-12 |
| 2014-10-03 | 2014-10-24 | 16 | True | normal | 2014-10-27 |
| 2015-02-02 | 2015-02-03 | 2 | False | normal | 2015-02-04 |
| 2015-07-01 | 2015-07-13 | 8 | False | normal | 2015-07-14 |
| 2015-07-28 | 2015-07-29 | 2 | False | normal | 2015-07-30 |
| 2015-08-07 | 2015-08-14 | 6 | False | normal | 2015-08-17 |
| 2015-08-24 | 2015-09-03 | 9 | True | bear | 2015-09-04 |
| 2016-06-29 | 2016-06-30 | 2 | False | normal | 2016-07-01 |
| 2016-10-12 | 2016-11-09 | 21 | False | normal | 2016-11-10 |
| 2018-03-23 | 2018-04-17 | 17 | False | normal | 2018-04-18 |
| 2018-05-01 | 2018-05-09 | 7 | False | normal | 2018-05-10 |
| 2018-10-16 | 2018-11-12 | 20 | False | bear | 2018-11-13 |
| 2018-11-30 | 2018-12-12 | 8 | False | bear | 2018-12-13 |
| 2019-05-31 | 2019-06-07 | 6 | False | normal | 2019-06-10 |
| 2019-08-29 | 2019-09-04 | 4 | False | normal | 2019-09-05 |
| 2019-10-02 | 2019-10-04 | 3 | False | normal | 2019-10-07 |
| 2019-10-09 | 2019-10-10 | 2 | False | normal | 2019-10-11 |
| 2020-03-02 | 2020-03-23 | 16 | True | bear | 2020-03-24 |
| 2020-10-30 | 2020-11-04 | 4 | True | normal | 2020-11-05 |
| 2021-10-06 | 2021-10-14 | 7 | False | normal | 2021-10-15 |
| 2022-01-21 | 2022-03-16 | 38 | True | bear | 2022-03-17 |
| 2023-09-25 | 2023-11-03 | 30 | False | normal | 2023-11-06 |
| 2024-08-09 | 2024-08-12 | 2 | False | normal | 2024-08-13 |
| 2025-02-26 | 2025-04-16 | 36 | True | bear | 2025-04-17 |
| 2026-03-11 | 2026-04-08 | 20 | True | normal | 2026-04-09 |
| 2026-07-30 | 2026-07-31 | 2 | False | normal | 2026-08-03 |
| 2026-10-23 | 2026-10-27 | 3 | False | normal | 2026-10-28 |
| 2026-11-02 | 2026-11-20 | 15 | True | open | n/a |

## Named episodes

| Year | Expected | Spell start | Sessions | Outcome | Next episode |
| --- | --- | --- | --- | --- | --- |
| 2000 | convert | 2000-02-01 | 5 | normal | 2000-02-08 |
| 2000 | convert | 2000-02-16 | 21 | normal | 2000-03-17 |
| 2000 | convert | 2000-05-30 | 3 | normal | 2000-06-02 |
| 2000 | convert | 2000-09-21 | 18 | bear | 2000-10-17 |
| 2008 | convert | n/a | n/a | no confirmed CORRECTION | n/a |
| 2022 | convert | 2022-01-21 | 38 | bear | 2022-03-17 |
| 2010 | check | 2010-02-01 | 13 | normal | 2010-02-19 |
| 2010 | check | 2010-05-21 | 32 | bear | 2010-07-08 |
| 2011 | check | 2011-06-09 | 16 | normal | 2011-07-01 |
| 2011 | check | 2011-07-28 | 15 | bear | 2011-08-18 |
| 2018 | check | 2018-03-23 | 17 | normal | 2018-04-18 |
| 2018 | check | 2018-05-01 | 7 | normal | 2018-05-10 |
| 2018 | check | 2018-10-16 | 20 | bear | 2018-11-13 |
| 2018 | check | 2018-11-30 | 8 | bear | 2018-12-13 |
| 2020 | check | 2020-03-02 | 16 | bear | 2020-03-24 |
| 2020 | check | 2020-10-30 | 4 | normal | 2020-11-05 |

## SPY forward returns from episode first days and pullback days

| Group | h | N | Mean % | Median % | Up % |
| --- | --- | --- | --- | --- | --- |
| BEAR | 5 | 31 | +0.60 | +1.35 | 61.3 |
| BEAR | 20 | 31 | +1.02 | +0.96 | 61.3 |
| BEAR | 60 | 31 | +4.61 | +6.92 | 74.2 |
| CORRECTION_STRESS | 5 | 27 | +0.56 | +0.92 | 63.0 |
| CORRECTION_STRESS | 20 | 26 | +2.58 | +3.37 | 73.1 |
| CORRECTION_STRESS | 60 | 26 | +6.65 | +7.07 | 84.6 |
| CORRECTION | 5 | 72 | +0.44 | +0.43 | 58.3 |
| CORRECTION | 20 | 70 | +1.39 | +2.06 | 67.1 |
| CORRECTION | 60 | 69 | +4.44 | +5.16 | 75.4 |
| NORMAL | 5 | 87 | +0.04 | +0.18 | 58.6 |
| NORMAL | 20 | 86 | +0.76 | +1.59 | 67.4 |
| NORMAL | 60 | 86 | +3.53 | +4.02 | 74.4 |
| UNKNOWN | 5 | 0 | n/a | n/a | n/a |
| UNKNOWN | 20 | 0 | n/a | n/a | n/a |
| UNKNOWN | 60 | 0 | n/a | n/a | n/a |
| PULLBACK | 5 | 90 | -0.05 | +0.09 | 53.3 |
| PULLBACK | 20 | 88 | +1.22 | +1.70 | 59.1 |
| PULLBACK | 60 | 88 | +4.19 | +4.66 | 76.1 |

## The same, split by stress

| Group | h | N | Mean % | Median % | Up % |
| --- | --- | --- | --- | --- | --- |
| BEAR / stress False | 5 | 20 | -0.35 | +0.15 | 50.0 |
| BEAR / stress False | 20 | 20 | -1.73 | -2.45 | 45.0 |
| BEAR / stress False | 60 | 20 | +1.26 | +2.97 | 70.0 |
| BEAR / stress True | 5 | 11 | +2.33 | +2.35 | 81.8 |
| BEAR / stress True | 20 | 11 | +6.02 | +5.31 | 90.9 |
| BEAR / stress True | 60 | 11 | +10.70 | +11.18 | 81.8 |
| CORRECTION / stress False | 5 | 72 | +0.44 | +0.43 | 58.3 |
| CORRECTION / stress False | 20 | 70 | +1.39 | +2.06 | 67.1 |
| CORRECTION / stress False | 60 | 69 | +4.44 | +5.16 | 75.4 |
| CORRECTION_STRESS / stress True | 5 | 27 | +0.56 | +0.92 | 63.0 |
| CORRECTION_STRESS / stress True | 20 | 26 | +2.58 | +3.37 | 73.1 |
| CORRECTION_STRESS / stress True | 60 | 26 | +6.65 | +7.07 | 84.6 |
| NORMAL / stress False | 5 | 78 | +0.14 | +0.40 | 61.5 |
| NORMAL / stress False | 20 | 77 | +0.60 | +1.55 | 66.2 |
| NORMAL / stress False | 60 | 77 | +2.88 | +3.77 | 72.7 |
| NORMAL / stress True | 5 | 9 | -0.81 | -0.68 | 33.3 |
| NORMAL / stress True | 20 | 9 | +2.09 | +2.05 | 77.8 |
| NORMAL / stress True | 60 | 9 | +9.04 | +9.47 | 88.9 |
| PULLBACK / stress False | 5 | 70 | +0.69 | +0.79 | 61.4 |
| PULLBACK / stress False | 20 | 68 | +1.76 | +2.58 | 67.6 |
| PULLBACK / stress False | 60 | 68 | +3.55 | +4.51 | 76.5 |
| PULLBACK / stress True | 5 | 20 | -2.66 | -2.03 | 25.0 |
| PULLBACK / stress True | 20 | 20 | -0.62 | -1.18 | 30.0 |
| PULLBACK / stress True | 60 | 20 | +6.34 | +6.08 | 75.0 |
