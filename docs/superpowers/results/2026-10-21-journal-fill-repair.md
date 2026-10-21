# Journal fill repair -- 2026-10-21

**What:** 55 production `journal_entries` rows re-written by
`scripts/ops/rejournal_fill_mismatch.py --apply` (exit-derived fields only:
outcome, r_realized, mfe_r, mae_r, exit_efficiency, holding_days, tags,
auto_lesson, closed_at). Notes and the issuance snapshot (confidence_level,
risk_features, entry_context) were kept.

**Why:** before 41e9b65e (2026-08-20) the legacy price monitor journaled
plan-linked trades at the stop (or TP1) before the plan manager wrote the
real fill over the trade; the journal kept the first number. Mismatches
(> 0.05R, journal vs final fill): 54 of 528 journaled trades closed before
2026-08-20, 1 of 248 after, 0 of 127 after about 2026-10-01.

**Effect:** summed R over the 55 rows +15.05R -> +9.70R (-5.35R, mean
-0.097R per row); 36 rows lower, 19 higher. Verification after apply: the
dry run reports "No journal rows disagree with their trade's fill."

**Old values (dry-run output before apply):**

```
55 journal row(s) disagree with the fill by > 0.05R:

  ADBE   HTee9i6cWVJZBoiA  2026-08-17  r_realized: 0.7988324844775925 -> 0.36, exit_efficiency: 0.9517 -> 0.214
         all changed: mfe_r, r_realized, auto_lesson, exit_efficiency
  WDC    sGGekkyKAlvSpZnl  2026-08-14  r_realized: 0.6573785810018081 -> 0.25, exit_efficiency: 0.2418 -> 0.0922
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  IREN   EM5TpHvC29G1yBnT  2026-08-14  r_realized: 0.37959274039384033 -> 0.2, exit_efficiency: 0.1747 -> 0.092
         all changed: r_realized, auto_lesson, exit_efficiency
  MRVL   iTAcWCNCLadCdVuf  2026-08-14  r_realized: -1.0 -> -1.1, closed_at: '2026-08-14T14:24:06.099683+00:00' -> '2026-08-14T14:24:07.756988+00:00'
         all changed: mae_r, mfe_r, r_realized, closed_at
  WDC    g4A0rMOItR7fNgkv  2026-08-14  r_realized: 0.45090749847462047 -> 0.18, exit_efficiency: 0.7586 -> 0.1284, closed_at: '2026-08-14T13:33:45.780426+00:00' -> '2026-08-14T13:44:06.766080+00:00'
         all changed: tags, mae_r, mfe_r, r_realized, auto_lesson, holding_days, exit_efficiency, closed_at
  SNDK   VOLQepfKsp3vECoU  2026-08-13  r_realized: 0.3966714344641058 -> 0.24, exit_efficiency: 0.3227 -> 0.1952
         all changed: mae_r, r_realized, auto_lesson, exit_efficiency
  MRVL   oMWli3lildOnNd5x  2026-08-13  r_realized: 0.2990778058126387 -> 0.17, exit_efficiency: 0.8128 -> 0.084
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  NBIS   yyOGbFaTOnz6pr6t  2026-08-13  r_realized: 0.1710897607868174 -> 0.07, exit_efficiency: None -> 0.0193
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  IREN   VBNg8Al1bAZYzXIY  2026-08-13  r_realized: 1.2964507458481582 -> 0.52, exit_efficiency: 0.7633 -> 0.1896
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  DDOG   lhveUwiOGqVP3tmv  2026-08-13  r_realized: -1.0 -> -1.39, closed_at: '2026-08-13T13:36:21.462797+00:00' -> '2026-08-13T13:39:10.533786+00:00'
         all changed: tags, r_realized, closed_at
  AXON   fv127CbKEY4c3sqg  2026-08-07  r_realized: 0.3500000000000035 -> 0.18, exit_efficiency: 0.7037 -> 0.3619
         all changed: r_realized, auto_lesson, exit_efficiency
  IREN   LxP3tQLGoj3zVWxr  2026-08-07  r_realized: 0.6384573647175623 -> 0.27, exit_efficiency: 0.9698 -> 0.1461
         all changed: mfe_r, r_realized, auto_lesson, exit_efficiency
  INTC   RjZhBOwHfRZRlO7T  2026-08-10  r_realized: 0.6224154212288355 -> 0.22, exit_efficiency: 0.7784 -> 0.2751, closed_at: '2026-08-10T08:24:39.460061+00:00' -> '2026-08-10T11:01:52.779966+00:00'
         all changed: tags, mae_r, r_realized, auto_lesson, holding_days, exit_efficiency, closed_at
  MRNA   2A7mCqMB5wiaAdiG  2026-08-07  r_realized: 0.5783809408717424 -> 0.22, exit_efficiency: 0.7 -> 0.1039
         all changed: mfe_r, r_realized, auto_lesson, exit_efficiency
  NBIS   2NPBFWCJmDKVCp0l  2026-08-07  r_realized: 0.4126784223232457 -> 0.14, exit_efficiency: 0.4671 -> 0.1585, closed_at: '2026-08-07T16:32:06.565507+00:00' -> '2026-08-07T18:23:27.262016+00:00'
         all changed: tags, mae_r, r_realized, auto_lesson, holding_days, exit_efficiency, closed_at
  AMD    15TvxIZHaSyqgiWp  2026-08-10  r_realized: -1.1062835863942224 -> -1.01, exit_efficiency: -5.0 -> -1.1319, closed_at: '2026-08-10T08:03:18.172356+00:00' -> '2026-08-10T08:06:52.384183+00:00'
         all changed: tags, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  STX    7RgvIMgmsIcJRc39  2026-08-07  r_realized: -1.3269854911121033 -> -1.2, closed_at: '2026-08-07T13:32:00.656164+00:00' -> '2026-08-07T13:32:57.873219+00:00'
         all changed: mae_r, mfe_r, r_realized, closed_at
  MRVL   aWGrNKeJgnC9XjfI  2026-08-07  r_realized: -0.013101506304182229 -> 0.17, exit_efficiency: None -> 0.1676
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  MRVL   iKOSowR2EQUnzIKF  2026-08-05  r_realized: -0.1805547428425802 -> 0.53, exit_efficiency: -0.1297 -> 0.3837
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  RKLB   HT3DexOJtjckk1XO  2026-08-04  r_realized: -0.0290401116716036 -> 0.71, exit_efficiency: -0.0199 -> 0.487
         all changed: r_realized, auto_lesson, exit_efficiency
  ARM    71zT2er8izPPZv1D  2026-08-05  r_realized: -0.040771664140300624 -> 0.72, exit_efficiency: -0.0078 -> 0.1374
         all changed: r_realized, auto_lesson, exit_efficiency
  IREN   kx8QlV2x8PbnLXmT  2026-08-04  r_realized: 4.548336317251361 -> 3.85, exit_efficiency: 1.0 -> 0.8465
         all changed: r_realized, auto_lesson, exit_efficiency
  MU     U2mHC2mshc6XHxq9  2026-08-04  r_realized: -0.12534137928232517 -> 0.55, exit_efficiency: -0.0668 -> 0.2924
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  INTC   DEjZbkGuJ4JfznAz  2026-08-04  r_realized: -0.0286612944962588 -> 1.19, exit_efficiency: -0.0119 -> 0.4952
         all changed: mae_r, r_realized, auto_lesson, exit_efficiency
  AMD    66YOT3EudCE6iR0E  2026-08-04  r_realized: -0.03064748483991248 -> 0.45, exit_efficiency: -0.02 -> 0.2937
         all changed: r_realized, auto_lesson, exit_efficiency
  INTC   tItOdI4aRphj8yw6  2026-08-04  r_realized: -0.09734260405752929 -> 0.76, exit_efficiency: -0.0603 -> 0.4704
         all changed: mae_r, r_realized, auto_lesson, exit_efficiency
  MU     XSmTbWQ2xeKMLKTS  2026-08-04  r_realized: -0.061806324711397215 -> 0.42, exit_efficiency: -0.045 -> 0.3054
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  INTC   UUtWvns09OMTwCcS  2026-08-04  r_realized: -0.04003230774640115 -> 0.83, exit_efficiency: -0.0235 -> 0.4867
         all changed: mae_r, r_realized, auto_lesson, exit_efficiency
  AMD    NqrBW2RurKaDzqV6  2026-08-04  r_realized: 2.030500194544118 -> 1.37, exit_efficiency: 0.5519 -> 0.3724
         all changed: r_realized, auto_lesson, exit_efficiency
  MU     5cuTOPazpjTh9sOF  2026-08-04  r_realized: 1.6367223347425597 -> 1.11, exit_efficiency: 0.5903 -> 0.4008
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  INTC   Q9EEuTuGGIqmDniH  2026-08-04  r_realized: 2.2719855134782874 -> 1.57, exit_efficiency: 0.4932 -> 0.3307
         all changed: mfe_r, r_realized, auto_lesson, exit_efficiency
  GLW    JHTPE5cWUYsezYJR  2026-08-03  r_realized: 1.598590031918943 -> 1.54, exit_efficiency: None -> 0.4103
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  MU     ouLr3tPjPUVdCUTR  2026-08-03  r_realized: -0.08466181607193322 -> 0.48, exit_efficiency: None -> 0.4264
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  MU     Y1GbxfRXjMjedR7f  2026-08-03  r_realized: -0.03923492314033454 -> 0.43, exit_efficiency: -0.0065 -> 0.0718
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  MRNA   RwsitTNrMNO1ddIX  2026-08-03  r_realized: -0.18615046875060395 -> 0.09, exit_efficiency: -0.0535 -> 0.0259
         all changed: mae_r, r_realized, auto_lesson, exit_efficiency
  AMAT   qPxetgXqY0drQFy1  2026-07-31  r_realized: 0.36039338819962097 -> 0.23, exit_efficiency: 0.1519 -> 0.099
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  MU     mZk9J8U8TNGCfmTK  2026-07-31  r_realized: -1.0294847823352464 -> -1.12, exit_efficiency: -2.8563 -> -3.0585, closed_at: '2026-07-31T17:35:11.627094+00:00' -> '2026-07-31T17:36:29.928802+00:00'
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  RDDT   6aEbgkrlfWbND49y  2026-07-31  r_realized: -0.7864326637179591 -> -0.01, exit_efficiency: -4.7104 -> -0.0508, closed_at: '2026-07-31T14:56:59.584489+00:00' -> '2026-07-31T14:57:01.565982+00:00'
         all changed: tags, mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  RDDT   9Lz0r5d3qpvzZdgL  2026-07-31  r_realized: 0.3786653462457528 -> 0.14, exit_efficiency: 0.8187 -> 0.3027, closed_at: '2026-07-31T15:35:20.632362+00:00' -> '2026-07-31T15:54:25.303169+00:00'
         all changed: tags, mae_r, r_realized, auto_lesson, holding_days, exit_efficiency, closed_at
  MSTR   DpNjRT78FQPBg0Zo  2026-07-31  r_realized: -1.0904979010549962 -> -1.0, exit_efficiency: -5.0 -> -4.8044, closed_at: '2026-07-31T08:02:32.806657+00:00' -> '2026-07-31T08:04:50.665328+00:00'
         all changed: mae_r, r_realized, auto_lesson, exit_efficiency, closed_at
  ARM    XliB0kecLZqXOHpp  2026-07-30  r_realized: -1.0 -> -1.15, exit_efficiency: -0.8318 -> -0.9566, closed_at: '2026-07-30T22:02:50.318934+00:00' -> '2026-07-30T22:02:52.171179+00:00'
         all changed: r_realized, auto_lesson, exit_efficiency, closed_at
  GD     tzs4zo68Uc6G1YAT  2026-07-31  r_realized: -1.0 -> -1.73, exit_efficiency: -1.335 -> -1.7675, closed_at: '2026-07-31T10:14:50.043772+00:00' -> '2026-07-31T10:14:51.383878+00:00'
         all changed: tags, mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  GD     WDWixaabjHd8n8QC  2026-07-31  r_realized: -1.0 -> -1.74, exit_efficiency: -1.3089 -> -1.7471, closed_at: '2026-07-31T10:14:50.043772+00:00' -> '2026-07-31T10:14:51.218608+00:00'
         all changed: tags, mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  ASML   dcFFJ6n4KfTBVbLo  2026-07-29  r_realized: -0.2564184385564166 -> 0.0, exit_efficiency: -0.6323 -> 0.0
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  ADBE   e3tk6C5EIVJr8azA  2026-07-29  r_realized: -1.0 -> -2.52, exit_efficiency: -2.3217 -> -5.0, closed_at: '2026-07-29T21:10:04.919052+00:00' -> '2026-07-29T21:10:07.058077+00:00'
         all changed: tags, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  AMAT   nTCcwrU93cxRLjni  2026-07-29  r_realized: -0.3778485724948015 -> 0.12, exit_efficiency: -1.3416 -> 0.3949, closed_at: '2026-07-29T20:14:07.109574+00:00' -> '2026-07-29T20:18:07.330468+00:00'
         all changed: tags, mae_r, mfe_r, r_realized, auto_lesson, holding_days, exit_efficiency, closed_at
  NBIS   KFkcjid0OVc0YO0i  2026-07-29  r_realized: 0.42370818377105296 -> 0.01, exit_efficiency: 0.6761 -> 0.016, closed_at: '2026-07-29T20:31:44.493950+00:00' -> '2026-07-29T20:33:07.608452+00:00'
         all changed: tags, r_realized, auto_lesson, exit_efficiency, closed_at
  STX    GbW5bDhVm2xcCyze  2026-07-29  r_realized: -1.0 -> -1.15, exit_efficiency: -0.4194 -> -0.4893, closed_at: '2026-07-29T21:42:04.900071+00:00' -> '2026-07-29T21:42:07.723343+00:00'
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  STX    n5Meuq8c8pAF2qWb  2026-07-28  r_realized: 1.7045658232965126 -> 0.83, exit_efficiency: 1.0 -> 0.7234
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  STX    J6owLNmKzCiKhaUR  2026-07-28  r_realized: 1.7941585475041786 -> 0.87, exit_efficiency: 1.0 -> 0.6988
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  STX    WsB4eavXN5FUwUzQ  2026-07-28  r_realized: 1.9865229316329094 -> 0.96, exit_efficiency: 1.0 -> 0.6892
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  ASML   JDyIJz4GIEpGF7iy  2026-07-28  r_realized: 0.3499999999999993 -> 0.19, exit_efficiency: 0.403 -> 0.2188, closed_at: '2026-07-28T20:15:53.197310+00:00' -> '2026-07-28T20:25:53.798831+00:00'
         all changed: tags, mae_r, r_realized, auto_lesson, holding_days, exit_efficiency, closed_at
  INTC   CXR7EQonQLqM8VV5  2026-07-27  r_realized: 0.35000000000000286 -> 0.14, exit_efficiency: 0.2065 -> 0.0826, closed_at: '2026-07-27T19:34:09.471692+00:00' -> '2026-07-27T19:39:09.864773+00:00'
         all changed: tags, mfe_r, r_realized, auto_lesson, exit_efficiency, closed_at
  WMT    9fT5uIpiWhVKfAxG  2026-07-28  r_realized: 0.3500000000000019 -> 0.25, exit_efficiency: 1.0 -> 0.1634
         all changed: mae_r, mfe_r, r_realized, auto_lesson, exit_efficiency
  RKLB   ZQjn6eoMaTYKOYcB  2026-07-27  r_realized: 2.146396152640933 -> 1.29, exit_efficiency: 0.972 -> 0.5842
         all changed: r_realized, auto_lesson, exit_efficiency

Dry run -- pass --apply to write.
```
