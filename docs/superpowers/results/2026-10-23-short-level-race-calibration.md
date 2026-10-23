# v182 short race A/A calibration (level entry) -> within the 5% false-pass limit

**Spec:** `docs/superpowers/specs/2026-10-21-v182-short-screen-range-breakdown-design.md` § Part B (calibration item 4).

**Run:** 2026-10-23; `python scripts/backtest/screen_trail_calibration.py --replicates 200 --seed 0 --tickers 24 --resamples 10000 --direction short --entry level`; replicate r uses seed 0 + r; 24 tickers x 2600 business days from 2010-01-04; bootstrap 10,000 week resamples, seed 42.

**Generator:** Student-t innovations t, df = 3, scaled to unit variance; two-state volatility regime, daily sigma 0.01 / 0.025, per-bar switch probability 0.02 (calm -> stressed) / 0.05 (stressed -> calm); no drift. Open-anchored bars: the open gaps off the prior close by exp(0.3 x sigma x N(0,1)) and Close = Open x exp(sigma x t), so a bar's open noise (its fill depth) is not coupled to its own move (the next-open A/A anchors Close to the prior close instead). Synthetic data only; no cached price file is read and no ledger row is written.

**Race:** the real `screen_ticker` with a fixed short level idea (cap 20 bars; a sell-stop at Close[t-1] - 0.5 x ATR14[t-1], placed before bar t opens and filled on bar t at the lower of the open and the level, entry slippage 2.0 x base; stop 1.5 x ATR14[t-1] above, target 3.0 x ATR14[t-1] below, only the stop counts on the fill bar; borrow 0.5% a year on calendar days held) against a short matched null that copies each event's fill depth (K = 20, unfilled draws replaced on the child stream), pooled through the real `verdict.decide` (pass rule unchanged). Events: a bar is drawn with probability 0.05 and is an event only when the order fills (Low[t] < level). Decision rule: false-pass rate ≤ 5% (10 of 200 at the registered run); the Wilson 95% interval is printed, never gating. This A/A shows only that the level-mode code adds no false passes; it cannot show that the depth-copy null is fair to real events (check 5 on the real cache does that, for range_breakdown_stop).

## Result

| | value | rule |
|---|---|---|
| full-verdict false-pass rate | 2 of 200 = 1.0% | ≤ 5% (gating) |
| Wilson 95% interval of the false-pass rate | 0.3% .. 3.6% | reported, not gated |
| coverage of the 95% interval for ΔExpR = 0 | 189 of 200 = 94.5% | reported, not gated |
| mean kept events N per replicate | 911.2 | — |

Verdicts: SCREEN-PASS 2, SCREEN-FAIL 198, SCREEN-UNDERPOWERED 0. A replicate with no interval (no events) counts as not covering.

## Per replicate

| seed | verdict | N | ΔExpR | lower 95% | upper 95% |
|---|---|---|---|---|---|
| 0 | SCREEN-FAIL | 933 | -0.0187 | -0.0863 | +0.0481 |
| 1 | SCREEN-FAIL | 945 | +0.0330 | -0.0459 | +0.1143 |
| 2 | SCREEN-FAIL | 939 | -0.0240 | -0.0907 | +0.0440 |
| 3 | SCREEN-FAIL | 869 | +0.0082 | -0.0633 | +0.0811 |
| 4 | SCREEN-FAIL | 939 | -0.0127 | -0.0843 | +0.0583 |
| 5 | SCREEN-FAIL | 907 | -0.0369 | -0.1105 | +0.0361 |
| 6 | SCREEN-FAIL | 909 | -0.0208 | -0.0930 | +0.0497 |
| 7 | SCREEN-FAIL | 902 | -0.0288 | -0.1019 | +0.0429 |
| 8 | SCREEN-FAIL | 922 | +0.0466 | -0.0257 | +0.1179 |
| 9 | SCREEN-FAIL | 931 | -0.0037 | -0.0719 | +0.0641 |
| 10 | SCREEN-FAIL | 893 | +0.0138 | -0.0613 | +0.0900 |
| 11 | SCREEN-FAIL | 902 | -0.0312 | -0.1062 | +0.0458 |
| 12 | SCREEN-FAIL | 899 | -0.0004 | -0.0781 | +0.0808 |
| 13 | SCREEN-FAIL | 917 | -0.0051 | -0.0727 | +0.0653 |
| 14 | SCREEN-FAIL | 921 | -0.0197 | -0.0872 | +0.0487 |
| 15 | SCREEN-FAIL | 901 | +0.0767 | +0.0106 | +0.1436 |
| 16 | SCREEN-FAIL | 908 | -0.0466 | -0.1189 | +0.0260 |
| 17 | SCREEN-FAIL | 947 | +0.0094 | -0.0583 | +0.0753 |
| 18 | SCREEN-FAIL | 928 | -0.0413 | -0.1095 | +0.0292 |
| 19 | SCREEN-FAIL | 849 | -0.0298 | -0.1051 | +0.0439 |
| 20 | SCREEN-FAIL | 909 | -0.0464 | -0.1143 | +0.0226 |
| 21 | SCREEN-FAIL | 927 | -0.0292 | -0.1010 | +0.0426 |
| 22 | SCREEN-FAIL | 912 | +0.0071 | -0.0592 | +0.0747 |
| 23 | SCREEN-FAIL | 895 | +0.0351 | -0.0384 | +0.1111 |
| 24 | SCREEN-FAIL | 911 | -0.0438 | -0.1144 | +0.0262 |
| 25 | SCREEN-FAIL | 910 | -0.0400 | -0.1103 | +0.0314 |
| 26 | SCREEN-FAIL | 919 | -0.0123 | -0.0911 | +0.0652 |
| 27 | SCREEN-FAIL | 904 | -0.0594 | -0.1348 | +0.0177 |
| 28 | SCREEN-FAIL | 946 | +0.0053 | -0.0653 | +0.0740 |
| 29 | SCREEN-FAIL | 915 | -0.0184 | -0.0861 | +0.0480 |
| 30 | SCREEN-FAIL | 901 | +0.0798 | -0.0050 | +0.1674 |
| 31 | SCREEN-FAIL | 898 | -0.0270 | -0.0995 | +0.0490 |
| 32 | SCREEN-FAIL | 901 | +0.0205 | -0.0571 | +0.0992 |
| 33 | SCREEN-FAIL | 945 | +0.0226 | -0.0495 | +0.0965 |
| 34 | SCREEN-FAIL | 923 | +0.0026 | -0.0707 | +0.0755 |
| 35 | SCREEN-FAIL | 883 | -0.0172 | -0.0943 | +0.0593 |
| 36 | SCREEN-FAIL | 908 | -0.0021 | -0.0672 | +0.0632 |
| 37 | SCREEN-FAIL | 896 | -0.0161 | -0.0910 | +0.0597 |
| 38 | SCREEN-FAIL | 896 | -0.0071 | -0.0751 | +0.0595 |
| 39 | SCREEN-FAIL | 941 | +0.0039 | -0.0745 | +0.0818 |
| 40 | SCREEN-FAIL | 858 | -0.0013 | -0.0750 | +0.0725 |
| 41 | SCREEN-FAIL | 925 | +0.0092 | -0.0618 | +0.0810 |
| 42 | SCREEN-PASS | 900 | +0.1013 | +0.0282 | +0.1750 |
| 43 | SCREEN-FAIL | 891 | +0.0024 | -0.0749 | +0.0796 |
| 44 | SCREEN-FAIL | 838 | +0.0658 | -0.0135 | +0.1467 |
| 45 | SCREEN-FAIL | 923 | -0.0245 | -0.0965 | +0.0462 |
| 46 | SCREEN-FAIL | 886 | -0.0794 | -0.1512 | -0.0050 |
| 47 | SCREEN-FAIL | 923 | -0.0256 | -0.0964 | +0.0438 |
| 48 | SCREEN-FAIL | 916 | -0.0712 | -0.1385 | -0.0041 |
| 49 | SCREEN-FAIL | 977 | +0.0236 | -0.0450 | +0.0925 |
| 50 | SCREEN-FAIL | 919 | +0.0154 | -0.0560 | +0.0875 |
| 51 | SCREEN-FAIL | 909 | -0.0322 | -0.1073 | +0.0446 |
| 52 | SCREEN-FAIL | 913 | +0.0139 | -0.0618 | +0.0909 |
| 53 | SCREEN-FAIL | 924 | -0.0537 | -0.1223 | +0.0156 |
| 54 | SCREEN-FAIL | 860 | -0.0444 | -0.1202 | +0.0324 |
| 55 | SCREEN-FAIL | 889 | +0.0185 | -0.0576 | +0.0955 |
| 56 | SCREEN-FAIL | 931 | +0.0425 | -0.0333 | +0.1190 |
| 57 | SCREEN-FAIL | 853 | -0.0375 | -0.1113 | +0.0352 |
| 58 | SCREEN-FAIL | 914 | -0.0185 | -0.0914 | +0.0558 |
| 59 | SCREEN-FAIL | 893 | +0.0030 | -0.0702 | +0.0752 |
| 60 | SCREEN-FAIL | 922 | -0.0134 | -0.0876 | +0.0613 |
| 61 | SCREEN-FAIL | 942 | -0.0520 | -0.1254 | +0.0258 |
| 62 | SCREEN-FAIL | 964 | -0.0364 | -0.1032 | +0.0313 |
| 63 | SCREEN-FAIL | 934 | -0.0107 | -0.0795 | +0.0591 |
| 64 | SCREEN-FAIL | 886 | -0.0236 | -0.0938 | +0.0476 |
| 65 | SCREEN-FAIL | 908 | -0.0213 | -0.0893 | +0.0483 |
| 66 | SCREEN-FAIL | 902 | +0.0453 | -0.0271 | +0.1184 |
| 67 | SCREEN-FAIL | 896 | -0.0844 | -0.1552 | -0.0136 |
| 68 | SCREEN-FAIL | 919 | -0.0400 | -0.1093 | +0.0276 |
| 69 | SCREEN-FAIL | 928 | -0.0492 | -0.1225 | +0.0242 |
| 70 | SCREEN-FAIL | 878 | -0.0090 | -0.0784 | +0.0608 |
| 71 | SCREEN-FAIL | 881 | +0.0248 | -0.0522 | +0.1001 |
| 72 | SCREEN-FAIL | 931 | +0.0172 | -0.0550 | +0.0901 |
| 73 | SCREEN-FAIL | 914 | -0.0738 | -0.1417 | -0.0056 |
| 74 | SCREEN-FAIL | 903 | +0.0618 | -0.0244 | +0.1550 |
| 75 | SCREEN-FAIL | 886 | -0.0058 | -0.0780 | +0.0676 |
| 76 | SCREEN-FAIL | 922 | -0.0093 | -0.0763 | +0.0561 |
| 77 | SCREEN-FAIL | 892 | -0.0702 | -0.1405 | +0.0005 |
| 78 | SCREEN-FAIL | 908 | +0.0289 | -0.0444 | +0.1043 |
| 79 | SCREEN-FAIL | 924 | +0.0488 | -0.0244 | +0.1212 |
| 80 | SCREEN-FAIL | 919 | +0.0017 | -0.0700 | +0.0733 |
| 81 | SCREEN-FAIL | 931 | -0.0251 | -0.0977 | +0.0453 |
| 82 | SCREEN-FAIL | 911 | +0.0224 | -0.0528 | +0.0970 |
| 83 | SCREEN-FAIL | 910 | -0.0084 | -0.0800 | +0.0631 |
| 84 | SCREEN-FAIL | 889 | +0.0072 | -0.0712 | +0.0853 |
| 85 | SCREEN-FAIL | 881 | +0.0522 | -0.0189 | +0.1247 |
| 86 | SCREEN-FAIL | 905 | +0.0136 | -0.0587 | +0.0853 |
| 87 | SCREEN-FAIL | 904 | +0.0348 | -0.0338 | +0.1039 |
| 88 | SCREEN-FAIL | 930 | +0.0056 | -0.0633 | +0.0739 |
| 89 | SCREEN-FAIL | 850 | -0.0279 | -0.1077 | +0.0530 |
| 90 | SCREEN-FAIL | 924 | -0.0335 | -0.1115 | +0.0460 |
| 91 | SCREEN-FAIL | 884 | +0.0146 | -0.0553 | +0.0881 |
| 92 | SCREEN-FAIL | 938 | -0.0938 | -0.1671 | -0.0209 |
| 93 | SCREEN-FAIL | 887 | -0.0403 | -0.1068 | +0.0274 |
| 94 | SCREEN-FAIL | 872 | -0.0184 | -0.0902 | +0.0531 |
| 95 | SCREEN-FAIL | 903 | -0.0243 | -0.0950 | +0.0477 |
| 96 | SCREEN-FAIL | 935 | -0.0564 | -0.1285 | +0.0203 |
| 97 | SCREEN-FAIL | 930 | -0.0150 | -0.0919 | +0.0643 |
| 98 | SCREEN-FAIL | 949 | +0.0779 | +0.0037 | +0.1539 |
| 99 | SCREEN-FAIL | 912 | +0.0287 | -0.0416 | +0.0979 |
| 100 | SCREEN-FAIL | 924 | -0.0474 | -0.1189 | +0.0252 |
| 101 | SCREEN-FAIL | 965 | +0.0714 | -0.0033 | +0.1500 |
| 102 | SCREEN-FAIL | 856 | -0.0024 | -0.0772 | +0.0730 |
| 103 | SCREEN-FAIL | 932 | -0.0082 | -0.0808 | +0.0660 |
| 104 | SCREEN-FAIL | 922 | +0.0409 | -0.0285 | +0.1099 |
| 105 | SCREEN-FAIL | 921 | +0.0144 | -0.0549 | +0.0810 |
| 106 | SCREEN-FAIL | 927 | -0.0439 | -0.1135 | +0.0252 |
| 107 | SCREEN-FAIL | 908 | +0.0043 | -0.0667 | +0.0772 |
| 108 | SCREEN-FAIL | 909 | -0.0466 | -0.1219 | +0.0283 |
| 109 | SCREEN-FAIL | 896 | +0.0216 | -0.0546 | +0.0986 |
| 110 | SCREEN-FAIL | 928 | -0.0513 | -0.1221 | +0.0204 |
| 111 | SCREEN-FAIL | 933 | -0.0446 | -0.1116 | +0.0224 |
| 112 | SCREEN-FAIL | 887 | +0.0362 | -0.0345 | +0.1100 |
| 113 | SCREEN-FAIL | 939 | +0.0411 | -0.0325 | +0.1157 |
| 114 | SCREEN-FAIL | 923 | -0.0193 | -0.0947 | +0.0561 |
| 115 | SCREEN-FAIL | 913 | +0.0311 | -0.0460 | +0.1099 |
| 116 | SCREEN-FAIL | 926 | +0.0160 | -0.0614 | +0.0928 |
| 117 | SCREEN-FAIL | 911 | +0.0416 | -0.0303 | +0.1146 |
| 118 | SCREEN-FAIL | 904 | -0.0300 | -0.1069 | +0.0478 |
| 119 | SCREEN-FAIL | 919 | -0.0496 | -0.1211 | +0.0247 |
| 120 | SCREEN-FAIL | 888 | -0.0223 | -0.1000 | +0.0570 |
| 121 | SCREEN-FAIL | 882 | +0.0315 | -0.0443 | +0.1066 |
| 122 | SCREEN-FAIL | 925 | -0.0271 | -0.0950 | +0.0423 |
| 123 | SCREEN-FAIL | 872 | -0.0435 | -0.1112 | +0.0247 |
| 124 | SCREEN-FAIL | 978 | +0.0138 | -0.0560 | +0.0867 |
| 125 | SCREEN-FAIL | 907 | +0.0125 | -0.0589 | +0.0841 |
| 126 | SCREEN-FAIL | 925 | +0.0092 | -0.0665 | +0.0855 |
| 127 | SCREEN-FAIL | 890 | +0.0145 | -0.0555 | +0.0848 |
| 128 | SCREEN-FAIL | 894 | +0.0627 | -0.0072 | +0.1312 |
| 129 | SCREEN-FAIL | 905 | -0.0121 | -0.0839 | +0.0606 |
| 130 | SCREEN-FAIL | 961 | -0.0034 | -0.0714 | +0.0634 |
| 131 | SCREEN-FAIL | 941 | -0.0039 | -0.0787 | +0.0714 |
| 132 | SCREEN-FAIL | 894 | +0.0239 | -0.0473 | +0.0950 |
| 133 | SCREEN-FAIL | 903 | -0.0016 | -0.0715 | +0.0710 |
| 134 | SCREEN-FAIL | 883 | +0.0309 | -0.0411 | +0.1038 |
| 135 | SCREEN-FAIL | 911 | +0.0313 | -0.0416 | +0.1014 |
| 136 | SCREEN-FAIL | 924 | +0.0807 | +0.0081 | +0.1544 |
| 137 | SCREEN-FAIL | 901 | +0.0380 | -0.0415 | +0.1173 |
| 138 | SCREEN-FAIL | 907 | +0.0272 | -0.0474 | +0.1018 |
| 139 | SCREEN-FAIL | 865 | -0.0327 | -0.1074 | +0.0436 |
| 140 | SCREEN-FAIL | 923 | +0.0651 | -0.0047 | +0.1352 |
| 141 | SCREEN-FAIL | 900 | -0.0262 | -0.1057 | +0.0518 |
| 142 | SCREEN-FAIL | 946 | -0.0114 | -0.0789 | +0.0582 |
| 143 | SCREEN-FAIL | 948 | -0.0663 | -0.1332 | +0.0017 |
| 144 | SCREEN-FAIL | 934 | -0.0368 | -0.1101 | +0.0365 |
| 145 | SCREEN-FAIL | 956 | +0.0084 | -0.0600 | +0.0789 |
| 146 | SCREEN-FAIL | 884 | -0.0473 | -0.1172 | +0.0223 |
| 147 | SCREEN-FAIL | 898 | -0.0191 | -0.0920 | +0.0546 |
| 148 | SCREEN-FAIL | 925 | +0.0323 | -0.0389 | +0.1032 |
| 149 | SCREEN-FAIL | 883 | +0.0321 | -0.0435 | +0.1082 |
| 150 | SCREEN-FAIL | 899 | -0.0017 | -0.0707 | +0.0710 |
| 151 | SCREEN-FAIL | 952 | +0.0230 | -0.0518 | +0.0988 |
| 152 | SCREEN-FAIL | 899 | +0.0106 | -0.0604 | +0.0804 |
| 153 | SCREEN-FAIL | 929 | -0.0434 | -0.1139 | +0.0255 |
| 154 | SCREEN-FAIL | 924 | +0.0567 | -0.0165 | +0.1259 |
| 155 | SCREEN-FAIL | 922 | -0.0166 | -0.0855 | +0.0547 |
| 156 | SCREEN-FAIL | 917 | -0.0197 | -0.0910 | +0.0504 |
| 157 | SCREEN-FAIL | 871 | -0.0006 | -0.0715 | +0.0712 |
| 158 | SCREEN-FAIL | 937 | -0.0159 | -0.0866 | +0.0552 |
| 159 | SCREEN-FAIL | 922 | +0.0059 | -0.0662 | +0.0780 |
| 160 | SCREEN-FAIL | 895 | +0.0277 | -0.0460 | +0.1034 |
| 161 | SCREEN-FAIL | 905 | +0.0325 | -0.0406 | +0.1043 |
| 162 | SCREEN-FAIL | 925 | +0.0521 | -0.0250 | +0.1291 |
| 163 | SCREEN-FAIL | 875 | +0.0252 | -0.0496 | +0.0981 |
| 164 | SCREEN-FAIL | 891 | -0.0584 | -0.1296 | +0.0138 |
| 165 | SCREEN-FAIL | 907 | -0.0262 | -0.0970 | +0.0474 |
| 166 | SCREEN-FAIL | 901 | -0.0159 | -0.0980 | +0.0673 |
| 167 | SCREEN-FAIL | 915 | +0.0082 | -0.0630 | +0.0789 |
| 168 | SCREEN-FAIL | 899 | +0.0192 | -0.0553 | +0.0942 |
| 169 | SCREEN-PASS | 907 | +0.1125 | +0.0344 | +0.1926 |
| 170 | SCREEN-FAIL | 915 | -0.0414 | -0.1164 | +0.0337 |
| 171 | SCREEN-FAIL | 947 | +0.0224 | -0.0514 | +0.0961 |
| 172 | SCREEN-FAIL | 933 | -0.0401 | -0.1088 | +0.0294 |
| 173 | SCREEN-FAIL | 928 | +0.0574 | -0.0110 | +0.1276 |
| 174 | SCREEN-FAIL | 926 | +0.0643 | -0.0152 | +0.1429 |
| 175 | SCREEN-FAIL | 892 | -0.0330 | -0.1067 | +0.0424 |
| 176 | SCREEN-FAIL | 896 | -0.0160 | -0.0883 | +0.0556 |
| 177 | SCREEN-FAIL | 945 | +0.0355 | -0.0345 | +0.1098 |
| 178 | SCREEN-FAIL | 864 | +0.0363 | -0.0469 | +0.1214 |
| 179 | SCREEN-FAIL | 920 | -0.0213 | -0.0948 | +0.0525 |
| 180 | SCREEN-FAIL | 932 | +0.0401 | -0.0367 | +0.1179 |
| 181 | SCREEN-FAIL | 885 | +0.0171 | -0.0634 | +0.0989 |
| 182 | SCREEN-FAIL | 872 | +0.0190 | -0.0528 | +0.0926 |
| 183 | SCREEN-FAIL | 934 | -0.0079 | -0.0812 | +0.0658 |
| 184 | SCREEN-FAIL | 921 | -0.0877 | -0.1594 | -0.0154 |
| 185 | SCREEN-FAIL | 929 | -0.0455 | -0.1161 | +0.0261 |
| 186 | SCREEN-FAIL | 875 | -0.0692 | -0.1413 | +0.0021 |
| 187 | SCREEN-FAIL | 868 | +0.0059 | -0.0728 | +0.0849 |
| 188 | SCREEN-FAIL | 898 | +0.0149 | -0.0617 | +0.0934 |
| 189 | SCREEN-FAIL | 950 | -0.0029 | -0.0744 | +0.0681 |
| 190 | SCREEN-FAIL | 958 | +0.0169 | -0.0514 | +0.0875 |
| 191 | SCREEN-FAIL | 877 | -0.0119 | -0.0873 | +0.0630 |
| 192 | SCREEN-FAIL | 912 | +0.0425 | -0.0304 | +0.1150 |
| 193 | SCREEN-FAIL | 920 | -0.0251 | -0.0958 | +0.0457 |
| 194 | SCREEN-FAIL | 886 | +0.0008 | -0.0682 | +0.0723 |
| 195 | SCREEN-FAIL | 920 | -0.0374 | -0.1105 | +0.0337 |
| 196 | SCREEN-FAIL | 926 | -0.0217 | -0.0950 | +0.0508 |
| 197 | SCREEN-FAIL | 920 | -0.0007 | -0.0690 | +0.0681 |
| 198 | SCREEN-FAIL | 961 | +0.0194 | -0.0471 | +0.0883 |
| 199 | SCREEN-FAIL | 898 | -0.0532 | -0.1212 | +0.0138 |
