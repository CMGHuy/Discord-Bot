# v182 short race A/A calibration (next-open entry) -> within the 5% false-pass limit

**Spec:** `docs/superpowers/specs/2026-10-21-v182-short-screen-range-breakdown-design.md` § Part A (calibration item 2).

**Run:** 2026-10-23; `python scripts/backtest/screen_trail_calibration.py --replicates 200 --seed 0 --tickers 24 --resamples 10000 --direction short --entry next_open`; replicate r uses seed 0 + r; 24 tickers x 2600 business days from 2010-01-04; bootstrap 10,000 week resamples, seed 42.

**Generator:** Student-t innovations, df = 3, scaled to unit variance; two-state volatility regime, daily sigma 0.01 / 0.025, per-bar switch probability 0.02 (calm -> stressed) / 0.05 (stressed -> calm); no drift. Events: every bar independently with probability 0.02, no planted effect. Synthetic data only; no cached price file is read and no ledger row is written.

**Race:** the real `screen_ticker` with a fixed short idea (cap 20 bars; entry next open, sold; stop 1.5 x ATR14[t] above, target 3.0 x ATR14[t] below; borrow 0.5% a year on calendar days held) against a short matched null (K = 20), pooled through the real `verdict.decide` (pass rule unchanged). Decision rule: false-pass rate ≤ 5% (10 of 200 at the registered run); the Wilson 95% interval is printed, never gating.

## Result

| | value | rule |
|---|---|---|
| full-verdict false-pass rate | 0 of 200 = 0.0% | ≤ 5% (gating) |
| Wilson 95% interval of the false-pass rate | 0.0% .. 1.9% | reported, not gated |
| coverage of the 95% interval for ΔExpR = 0 | 193 of 200 = 96.5% | reported, not gated |
| mean kept events N per replicate | 915.5 | — |

Verdicts: SCREEN-PASS 0, SCREEN-FAIL 200, SCREEN-UNDERPOWERED 0. A replicate with no interval (no events) counts as not covering.

## Per replicate

| seed | verdict | N | ΔExpR | lower 95% | upper 95% |
|---|---|---|---|---|---|
| 0 | SCREEN-FAIL | 925 | -0.0356 | -0.0972 | +0.0263 |
| 1 | SCREEN-FAIL | 922 | +0.0279 | -0.0354 | +0.0923 |
| 2 | SCREEN-FAIL | 934 | -0.0480 | -0.1139 | +0.0189 |
| 3 | SCREEN-FAIL | 873 | +0.0559 | -0.0117 | +0.1234 |
| 4 | SCREEN-FAIL | 882 | +0.0107 | -0.0490 | +0.0722 |
| 5 | SCREEN-FAIL | 904 | +0.0175 | -0.0439 | +0.0784 |
| 6 | SCREEN-FAIL | 896 | -0.0094 | -0.0697 | +0.0514 |
| 7 | SCREEN-FAIL | 871 | +0.0272 | -0.0399 | +0.0945 |
| 8 | SCREEN-FAIL | 931 | -0.0098 | -0.0720 | +0.0515 |
| 9 | SCREEN-FAIL | 940 | -0.0052 | -0.0710 | +0.0598 |
| 10 | SCREEN-FAIL | 888 | +0.0460 | -0.0200 | +0.1127 |
| 11 | SCREEN-FAIL | 907 | -0.0127 | -0.0774 | +0.0531 |
| 12 | SCREEN-FAIL | 901 | +0.0249 | -0.0436 | +0.0939 |
| 13 | SCREEN-FAIL | 922 | +0.0229 | -0.0409 | +0.0849 |
| 14 | SCREEN-FAIL | 908 | +0.0269 | -0.0346 | +0.0894 |
| 15 | SCREEN-FAIL | 913 | -0.0019 | -0.0605 | +0.0560 |
| 16 | SCREEN-FAIL | 920 | -0.0754 | -0.1397 | -0.0097 |
| 17 | SCREEN-FAIL | 945 | -0.0242 | -0.0816 | +0.0313 |
| 18 | SCREEN-FAIL | 950 | +0.0007 | -0.0586 | +0.0604 |
| 19 | SCREEN-FAIL | 886 | +0.0169 | -0.0446 | +0.0767 |
| 20 | SCREEN-FAIL | 904 | +0.0166 | -0.0519 | +0.0832 |
| 21 | SCREEN-FAIL | 919 | +0.0410 | -0.0245 | +0.1068 |
| 22 | SCREEN-FAIL | 888 | +0.0535 | -0.0118 | +0.1184 |
| 23 | SCREEN-FAIL | 947 | +0.0145 | -0.0486 | +0.0784 |
| 24 | SCREEN-FAIL | 917 | +0.0082 | -0.0548 | +0.0707 |
| 25 | SCREEN-FAIL | 908 | -0.0252 | -0.0860 | +0.0376 |
| 26 | SCREEN-FAIL | 929 | +0.0058 | -0.0543 | +0.0657 |
| 27 | SCREEN-FAIL | 938 | +0.0436 | -0.0184 | +0.1044 |
| 28 | SCREEN-FAIL | 968 | -0.0444 | -0.1021 | +0.0141 |
| 29 | SCREEN-FAIL | 902 | +0.0583 | -0.0029 | +0.1192 |
| 30 | SCREEN-FAIL | 899 | +0.0385 | -0.0234 | +0.1014 |
| 31 | SCREEN-FAIL | 928 | +0.0291 | -0.0297 | +0.0871 |
| 32 | SCREEN-FAIL | 949 | -0.0006 | -0.0655 | +0.0648 |
| 33 | SCREEN-FAIL | 895 | +0.0347 | -0.0262 | +0.0963 |
| 34 | SCREEN-FAIL | 903 | +0.0412 | -0.0224 | +0.1067 |
| 35 | SCREEN-FAIL | 941 | +0.0039 | -0.0573 | +0.0653 |
| 36 | SCREEN-FAIL | 928 | +0.0465 | -0.0153 | +0.1108 |
| 37 | SCREEN-FAIL | 918 | +0.0198 | -0.0414 | +0.0804 |
| 38 | SCREEN-FAIL | 917 | -0.0072 | -0.0697 | +0.0561 |
| 39 | SCREEN-FAIL | 931 | +0.0093 | -0.0582 | +0.0782 |
| 40 | SCREEN-FAIL | 868 | +0.0407 | -0.0203 | +0.1033 |
| 41 | SCREEN-FAIL | 960 | +0.0769 | +0.0180 | +0.1375 |
| 42 | SCREEN-FAIL | 899 | +0.0238 | -0.0468 | +0.0931 |
| 43 | SCREEN-FAIL | 914 | +0.0031 | -0.0644 | +0.0687 |
| 44 | SCREEN-FAIL | 889 | +0.0359 | -0.0280 | +0.1001 |
| 45 | SCREEN-FAIL | 906 | +0.0083 | -0.0535 | +0.0727 |
| 46 | SCREEN-FAIL | 930 | -0.0019 | -0.0640 | +0.0611 |
| 47 | SCREEN-FAIL | 900 | -0.0062 | -0.0688 | +0.0571 |
| 48 | SCREEN-FAIL | 907 | +0.0020 | -0.0608 | +0.0677 |
| 49 | SCREEN-FAIL | 934 | +0.0186 | -0.0446 | +0.0817 |
| 50 | SCREEN-FAIL | 907 | +0.0324 | -0.0306 | +0.0941 |
| 51 | SCREEN-FAIL | 912 | -0.0092 | -0.0696 | +0.0528 |
| 52 | SCREEN-FAIL | 917 | +0.0320 | -0.0331 | +0.0963 |
| 53 | SCREEN-FAIL | 915 | +0.0394 | -0.0245 | +0.1023 |
| 54 | SCREEN-FAIL | 896 | -0.0086 | -0.0751 | +0.0601 |
| 55 | SCREEN-FAIL | 924 | +0.0223 | -0.0417 | +0.0846 |
| 56 | SCREEN-FAIL | 917 | +0.0108 | -0.0521 | +0.0733 |
| 57 | SCREEN-FAIL | 887 | -0.0148 | -0.0768 | +0.0465 |
| 58 | SCREEN-FAIL | 905 | +0.0457 | -0.0218 | +0.1123 |
| 59 | SCREEN-FAIL | 884 | -0.0216 | -0.0842 | +0.0397 |
| 60 | SCREEN-FAIL | 964 | -0.0022 | -0.0675 | +0.0640 |
| 61 | SCREEN-FAIL | 893 | +0.0226 | -0.0414 | +0.0880 |
| 62 | SCREEN-FAIL | 923 | +0.0613 | +0.0002 | +0.1232 |
| 63 | SCREEN-FAIL | 916 | +0.0466 | -0.0234 | +0.1134 |
| 64 | SCREEN-FAIL | 860 | -0.0085 | -0.0695 | +0.0522 |
| 65 | SCREEN-FAIL | 885 | +0.0631 | -0.0036 | +0.1283 |
| 66 | SCREEN-FAIL | 901 | +0.0149 | -0.0494 | +0.0801 |
| 67 | SCREEN-FAIL | 930 | -0.0012 | -0.0615 | +0.0598 |
| 68 | SCREEN-FAIL | 925 | -0.0372 | -0.1016 | +0.0265 |
| 69 | SCREEN-FAIL | 913 | +0.0142 | -0.0532 | +0.0813 |
| 70 | SCREEN-FAIL | 882 | +0.0265 | -0.0369 | +0.0914 |
| 71 | SCREEN-FAIL | 885 | +0.0244 | -0.0415 | +0.0908 |
| 72 | SCREEN-FAIL | 867 | +0.0035 | -0.0632 | +0.0721 |
| 73 | SCREEN-FAIL | 880 | -0.0533 | -0.1183 | +0.0113 |
| 74 | SCREEN-FAIL | 850 | +0.0029 | -0.0573 | +0.0641 |
| 75 | SCREEN-FAIL | 889 | -0.0335 | -0.0966 | +0.0299 |
| 76 | SCREEN-FAIL | 933 | -0.0225 | -0.0847 | +0.0416 |
| 77 | SCREEN-FAIL | 876 | +0.0408 | -0.0213 | +0.1020 |
| 78 | SCREEN-FAIL | 915 | -0.0227 | -0.0866 | +0.0413 |
| 79 | SCREEN-FAIL | 991 | +0.0030 | -0.0584 | +0.0643 |
| 80 | SCREEN-FAIL | 900 | -0.0151 | -0.0820 | +0.0513 |
| 81 | SCREEN-FAIL | 900 | -0.0286 | -0.0920 | +0.0367 |
| 82 | SCREEN-FAIL | 920 | +0.0026 | -0.0577 | +0.0643 |
| 83 | SCREEN-FAIL | 912 | +0.0261 | -0.0350 | +0.0897 |
| 84 | SCREEN-FAIL | 914 | -0.0434 | -0.1060 | +0.0208 |
| 85 | SCREEN-FAIL | 854 | +0.0175 | -0.0509 | +0.0842 |
| 86 | SCREEN-FAIL | 930 | -0.0160 | -0.0749 | +0.0449 |
| 87 | SCREEN-FAIL | 878 | -0.0249 | -0.0874 | +0.0385 |
| 88 | SCREEN-FAIL | 897 | -0.0341 | -0.1045 | +0.0364 |
| 89 | SCREEN-FAIL | 903 | +0.0239 | -0.0391 | +0.0880 |
| 90 | SCREEN-FAIL | 921 | +0.0218 | -0.0453 | +0.0902 |
| 91 | SCREEN-FAIL | 903 | -0.0170 | -0.0819 | +0.0451 |
| 92 | SCREEN-FAIL | 968 | +0.0007 | -0.0630 | +0.0634 |
| 93 | SCREEN-FAIL | 933 | +0.0229 | -0.0372 | +0.0844 |
| 94 | SCREEN-FAIL | 899 | +0.0294 | -0.0383 | +0.0992 |
| 95 | SCREEN-FAIL | 897 | +0.0157 | -0.0486 | +0.0800 |
| 96 | SCREEN-FAIL | 967 | +0.0270 | -0.0357 | +0.0869 |
| 97 | SCREEN-FAIL | 921 | +0.0507 | -0.0130 | +0.1168 |
| 98 | SCREEN-FAIL | 945 | -0.0152 | -0.0774 | +0.0473 |
| 99 | SCREEN-FAIL | 912 | +0.0147 | -0.0478 | +0.0780 |
| 100 | SCREEN-FAIL | 862 | -0.0317 | -0.0928 | +0.0291 |
| 101 | SCREEN-FAIL | 933 | +0.0128 | -0.0508 | +0.0756 |
| 102 | SCREEN-FAIL | 883 | +0.0379 | -0.0247 | +0.1008 |
| 103 | SCREEN-FAIL | 909 | +0.0409 | -0.0235 | +0.1072 |
| 104 | SCREEN-FAIL | 908 | +0.0102 | -0.0542 | +0.0734 |
| 105 | SCREEN-FAIL | 914 | +0.0358 | -0.0260 | +0.0980 |
| 106 | SCREEN-FAIL | 957 | +0.0082 | -0.0559 | +0.0732 |
| 107 | SCREEN-FAIL | 922 | -0.0198 | -0.0814 | +0.0409 |
| 108 | SCREEN-FAIL | 932 | +0.0126 | -0.0486 | +0.0760 |
| 109 | SCREEN-FAIL | 947 | -0.0121 | -0.0792 | +0.0528 |
| 110 | SCREEN-FAIL | 916 | -0.0140 | -0.0801 | +0.0519 |
| 111 | SCREEN-FAIL | 938 | +0.0155 | -0.0452 | +0.0762 |
| 112 | SCREEN-FAIL | 912 | -0.0138 | -0.0742 | +0.0477 |
| 113 | SCREEN-FAIL | 910 | +0.0137 | -0.0468 | +0.0764 |
| 114 | SCREEN-FAIL | 902 | +0.0341 | -0.0293 | +0.0984 |
| 115 | SCREEN-FAIL | 907 | +0.0257 | -0.0387 | +0.0905 |
| 116 | SCREEN-FAIL | 901 | +0.0010 | -0.0615 | +0.0626 |
| 117 | SCREEN-FAIL | 913 | +0.0382 | -0.0291 | +0.1078 |
| 118 | SCREEN-FAIL | 921 | +0.0439 | -0.0229 | +0.1108 |
| 119 | SCREEN-FAIL | 886 | +0.0232 | -0.0393 | +0.0863 |
| 120 | SCREEN-FAIL | 941 | -0.0206 | -0.0854 | +0.0445 |
| 121 | SCREEN-FAIL | 924 | +0.0430 | -0.0189 | +0.1048 |
| 122 | SCREEN-FAIL | 947 | +0.0435 | -0.0213 | +0.1075 |
| 123 | SCREEN-FAIL | 940 | -0.0237 | -0.0841 | +0.0379 |
| 124 | SCREEN-FAIL | 918 | +0.0099 | -0.0544 | +0.0738 |
| 125 | SCREEN-FAIL | 946 | +0.0096 | -0.0551 | +0.0758 |
| 126 | SCREEN-FAIL | 934 | +0.0264 | -0.0342 | +0.0873 |
| 127 | SCREEN-FAIL | 877 | +0.0267 | -0.0349 | +0.0906 |
| 128 | SCREEN-FAIL | 928 | +0.0390 | -0.0269 | +0.1057 |
| 129 | SCREEN-FAIL | 894 | +0.0198 | -0.0468 | +0.0857 |
| 130 | SCREEN-FAIL | 927 | -0.0205 | -0.0849 | +0.0463 |
| 131 | SCREEN-FAIL | 946 | +0.0166 | -0.0429 | +0.0761 |
| 132 | SCREEN-FAIL | 936 | +0.0247 | -0.0396 | +0.0905 |
| 133 | SCREEN-FAIL | 896 | +0.0084 | -0.0562 | +0.0762 |
| 134 | SCREEN-FAIL | 892 | +0.0017 | -0.0620 | +0.0650 |
| 135 | SCREEN-FAIL | 947 | +0.0669 | +0.0053 | +0.1307 |
| 136 | SCREEN-FAIL | 943 | +0.0308 | -0.0335 | +0.0958 |
| 137 | SCREEN-FAIL | 911 | -0.0565 | -0.1229 | +0.0108 |
| 138 | SCREEN-FAIL | 943 | +0.0484 | -0.0151 | +0.1123 |
| 139 | SCREEN-FAIL | 953 | -0.0005 | -0.0606 | +0.0597 |
| 140 | SCREEN-FAIL | 948 | -0.0177 | -0.0776 | +0.0427 |
| 141 | SCREEN-FAIL | 932 | +0.0512 | -0.0149 | +0.1175 |
| 142 | SCREEN-FAIL | 893 | +0.0014 | -0.0595 | +0.0619 |
| 143 | SCREEN-FAIL | 924 | -0.0012 | -0.0627 | +0.0622 |
| 144 | SCREEN-FAIL | 909 | -0.0029 | -0.0704 | +0.0640 |
| 145 | SCREEN-FAIL | 952 | +0.0149 | -0.0450 | +0.0732 |
| 146 | SCREEN-FAIL | 928 | +0.0138 | -0.0481 | +0.0760 |
| 147 | SCREEN-FAIL | 910 | +0.0083 | -0.0549 | +0.0733 |
| 148 | SCREEN-FAIL | 905 | -0.0292 | -0.0867 | +0.0283 |
| 149 | SCREEN-FAIL | 886 | -0.0317 | -0.0933 | +0.0304 |
| 150 | SCREEN-FAIL | 921 | +0.0518 | -0.0110 | +0.1180 |
| 151 | SCREEN-FAIL | 937 | -0.0038 | -0.0665 | +0.0599 |
| 152 | SCREEN-FAIL | 914 | -0.0774 | -0.1356 | -0.0189 |
| 153 | SCREEN-FAIL | 924 | -0.0114 | -0.0715 | +0.0481 |
| 154 | SCREEN-FAIL | 896 | +0.0177 | -0.0439 | +0.0794 |
| 155 | SCREEN-FAIL | 881 | +0.0035 | -0.0642 | +0.0728 |
| 156 | SCREEN-FAIL | 942 | +0.0585 | -0.0053 | +0.1226 |
| 157 | SCREEN-FAIL | 898 | +0.0712 | +0.0039 | +0.1388 |
| 158 | SCREEN-FAIL | 939 | +0.0147 | -0.0511 | +0.0829 |
| 159 | SCREEN-FAIL | 930 | +0.0383 | -0.0228 | +0.0996 |
| 160 | SCREEN-FAIL | 914 | -0.0287 | -0.0913 | +0.0355 |
| 161 | SCREEN-FAIL | 930 | -0.0009 | -0.0710 | +0.0668 |
| 162 | SCREEN-FAIL | 891 | +0.0324 | -0.0271 | +0.0936 |
| 163 | SCREEN-FAIL | 896 | +0.0193 | -0.0452 | +0.0833 |
| 164 | SCREEN-FAIL | 912 | -0.0146 | -0.0776 | +0.0491 |
| 165 | SCREEN-FAIL | 898 | +0.0105 | -0.0533 | +0.0746 |
| 166 | SCREEN-FAIL | 894 | -0.0363 | -0.1020 | +0.0284 |
| 167 | SCREEN-FAIL | 913 | -0.0292 | -0.0987 | +0.0378 |
| 168 | SCREEN-FAIL | 932 | +0.0156 | -0.0400 | +0.0713 |
| 169 | SCREEN-FAIL | 929 | -0.0244 | -0.0850 | +0.0349 |
| 170 | SCREEN-FAIL | 901 | -0.0235 | -0.0846 | +0.0383 |
| 171 | SCREEN-FAIL | 963 | +0.0068 | -0.0519 | +0.0670 |
| 172 | SCREEN-FAIL | 919 | -0.0106 | -0.0763 | +0.0560 |
| 173 | SCREEN-FAIL | 929 | +0.0010 | -0.0587 | +0.0609 |
| 174 | SCREEN-FAIL | 897 | +0.0311 | -0.0384 | +0.1022 |
| 175 | SCREEN-FAIL | 954 | -0.0319 | -0.0938 | +0.0294 |
| 176 | SCREEN-FAIL | 952 | -0.0228 | -0.0890 | +0.0438 |
| 177 | SCREEN-FAIL | 942 | +0.0336 | -0.0332 | +0.1015 |
| 178 | SCREEN-FAIL | 919 | +0.0460 | -0.0190 | +0.1109 |
| 179 | SCREEN-FAIL | 867 | -0.0379 | -0.1037 | +0.0274 |
| 180 | SCREEN-FAIL | 945 | +0.0076 | -0.0585 | +0.0724 |
| 181 | SCREEN-FAIL | 920 | +0.0038 | -0.0595 | +0.0677 |
| 182 | SCREEN-FAIL | 924 | +0.0513 | -0.0090 | +0.1112 |
| 183 | SCREEN-FAIL | 954 | -0.0218 | -0.0818 | +0.0395 |
| 184 | SCREEN-FAIL | 920 | +0.0402 | -0.0235 | +0.1039 |
| 185 | SCREEN-FAIL | 936 | -0.0042 | -0.0637 | +0.0567 |
| 186 | SCREEN-FAIL | 903 | -0.0597 | -0.1245 | +0.0033 |
| 187 | SCREEN-FAIL | 906 | +0.0066 | -0.0567 | +0.0691 |
| 188 | SCREEN-FAIL | 904 | -0.0184 | -0.0842 | +0.0462 |
| 189 | SCREEN-FAIL | 933 | -0.0297 | -0.0912 | +0.0345 |
| 190 | SCREEN-FAIL | 962 | +0.0046 | -0.0615 | +0.0716 |
| 191 | SCREEN-FAIL | 881 | +0.0009 | -0.0603 | +0.0634 |
| 192 | SCREEN-FAIL | 920 | +0.0172 | -0.0452 | +0.0791 |
| 193 | SCREEN-FAIL | 957 | -0.0309 | -0.0914 | +0.0314 |
| 194 | SCREEN-FAIL | 902 | +0.0146 | -0.0481 | +0.0781 |
| 195 | SCREEN-FAIL | 880 | -0.0772 | -0.1402 | -0.0139 |
| 196 | SCREEN-FAIL | 918 | +0.0073 | -0.0543 | +0.0685 |
| 197 | SCREEN-FAIL | 875 | -0.0054 | -0.0703 | +0.0610 |
| 198 | SCREEN-FAIL | 923 | +0.0374 | -0.0260 | +0.1017 |
| 199 | SCREEN-FAIL | 932 | -0.0324 | -0.0929 | +0.0290 |
