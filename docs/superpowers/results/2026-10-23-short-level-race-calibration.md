# v182 short race A/A calibration (level entry) -> within the 5% false-pass limit

**Spec:** `docs/superpowers/specs/2026-10-21-v182-short-screen-range-breakdown-design.md` § Part B (calibration item 4).

**Run:** 2026-10-23; `python scripts/backtest/screen_trail_calibration.py --replicates 200 --seed 0 --tickers 24 --resamples 10000 --direction short --entry level`; replicate r uses seed 0 + r; 24 tickers x 2600 business days from 2010-01-04; bootstrap 10,000 week resamples, seed 42.

**Generator:** Student-t innovations, df = 3, scaled to unit variance; two-state volatility regime, daily sigma 0.01 / 0.025, per-bar switch probability 0.02 (calm -> stressed) / 0.05 (stressed -> calm); no drift. Events: every bar independently with probability 0.02, no planted effect. Synthetic data only; no cached price file is read and no ledger row is written.

**Race:** the real `screen_ticker` with a fixed short level idea (cap 20 bars; a sell-stop at Close[t-1] - 0.5 x ATR14[t-1], placed before bar t opens and filled on bar t at the lower of the open and the level, entry slippage 2.0 x base; stop 1.5 x ATR14[t-1] above, target 3.0 x ATR14[t-1] below, only the stop counts on the fill bar; borrow 0.5% a year on calendar days held) against a short matched null that copies each event's fill depth (K = 20, unfilled draws replaced on the child stream), pooled through the real `verdict.decide` (pass rule unchanged). Events: a bar is drawn with probability 0.05 and is an event only when the order fills (Low[t] < level). Decision rule: false-pass rate ≤ 5% (10 of 200 at the registered run); the Wilson 95% interval is printed, never gating. This A/A shows only that the level-mode code adds no false passes; it cannot show that the depth-copy null is fair to real events (check 5 on the real cache does that, for range_breakdown_stop).

## Result

| | value | rule |
|---|---|---|
| full-verdict false-pass rate | 0 of 200 = 0.0% | ≤ 5% (gating) |
| Wilson 95% interval of the false-pass rate | 0.0% .. 1.9% | reported, not gated |
| coverage of the 95% interval for ΔExpR = 0 | 95 of 200 = 47.5% | reported, not gated |
| mean kept events N per replicate | 910.9 | — |

Verdicts: SCREEN-PASS 0, SCREEN-FAIL 200, SCREEN-UNDERPOWERED 0. A replicate with no interval (no events) counts as not covering.

## Per replicate

| seed | verdict | N | ΔExpR | lower 95% | upper 95% |
|---|---|---|---|---|---|
| 0 | SCREEN-FAIL | 927 | -0.0359 | -0.1017 | +0.0307 |
| 1 | SCREEN-FAIL | 963 | -0.0162 | -0.0855 | +0.0533 |
| 2 | SCREEN-FAIL | 969 | -0.1192 | -0.1886 | -0.0496 |
| 3 | SCREEN-FAIL | 873 | -0.0603 | -0.1306 | +0.0087 |
| 4 | SCREEN-FAIL | 948 | -0.1118 | -0.1787 | -0.0428 |
| 5 | SCREEN-FAIL | 904 | -0.0747 | -0.1474 | -0.0014 |
| 6 | SCREEN-FAIL | 902 | -0.0697 | -0.1365 | -0.0016 |
| 7 | SCREEN-FAIL | 897 | -0.0810 | -0.1589 | +0.0011 |
| 8 | SCREEN-FAIL | 925 | -0.0627 | -0.1315 | +0.0066 |
| 9 | SCREEN-FAIL | 947 | -0.0777 | -0.1442 | -0.0087 |
| 10 | SCREEN-FAIL | 901 | -0.0329 | -0.1071 | +0.0431 |
| 11 | SCREEN-FAIL | 934 | -0.1125 | -0.1840 | -0.0406 |
| 12 | SCREEN-FAIL | 898 | -0.0625 | -0.1403 | +0.0108 |
| 13 | SCREEN-FAIL | 908 | -0.0928 | -0.1607 | -0.0227 |
| 14 | SCREEN-FAIL | 927 | -0.1053 | -0.1709 | -0.0403 |
| 15 | SCREEN-FAIL | 907 | -0.0182 | -0.0816 | +0.0464 |
| 16 | SCREEN-FAIL | 934 | -0.0996 | -0.1685 | -0.0286 |
| 17 | SCREEN-FAIL | 952 | -0.0712 | -0.1404 | -0.0021 |
| 18 | SCREEN-FAIL | 934 | -0.0753 | -0.1424 | -0.0087 |
| 19 | SCREEN-FAIL | 850 | -0.0139 | -0.0842 | +0.0595 |
| 20 | SCREEN-FAIL | 898 | -0.0900 | -0.1596 | -0.0211 |
| 21 | SCREEN-FAIL | 918 | -0.1038 | -0.1747 | -0.0339 |
| 22 | SCREEN-FAIL | 921 | -0.0638 | -0.1284 | +0.0033 |
| 23 | SCREEN-FAIL | 913 | -0.0532 | -0.1225 | +0.0157 |
| 24 | SCREEN-FAIL | 923 | -0.1418 | -0.2084 | -0.0754 |
| 25 | SCREEN-FAIL | 908 | -0.0111 | -0.0817 | +0.0595 |
| 26 | SCREEN-FAIL | 926 | -0.1410 | -0.2125 | -0.0673 |
| 27 | SCREEN-FAIL | 898 | -0.0542 | -0.1300 | +0.0199 |
| 28 | SCREEN-FAIL | 962 | -0.0691 | -0.1401 | +0.0027 |
| 29 | SCREEN-FAIL | 929 | -0.0828 | -0.1504 | -0.0155 |
| 30 | SCREEN-FAIL | 884 | -0.0083 | -0.0921 | +0.0776 |
| 31 | SCREEN-FAIL | 910 | -0.1189 | -0.1879 | -0.0493 |
| 32 | SCREEN-FAIL | 901 | -0.1136 | -0.1833 | -0.0428 |
| 33 | SCREEN-FAIL | 941 | -0.0255 | -0.0907 | +0.0397 |
| 34 | SCREEN-FAIL | 922 | -0.0531 | -0.1220 | +0.0175 |
| 35 | SCREEN-FAIL | 882 | -0.0165 | -0.0882 | +0.0563 |
| 36 | SCREEN-FAIL | 911 | -0.0314 | -0.1021 | +0.0379 |
| 37 | SCREEN-FAIL | 873 | -0.0877 | -0.1622 | -0.0114 |
| 38 | SCREEN-FAIL | 900 | -0.1106 | -0.1768 | -0.0457 |
| 39 | SCREEN-FAIL | 925 | -0.0818 | -0.1519 | -0.0090 |
| 40 | SCREEN-FAIL | 868 | -0.1029 | -0.1724 | -0.0305 |
| 41 | SCREEN-FAIL | 923 | -0.0756 | -0.1485 | -0.0017 |
| 42 | SCREEN-FAIL | 913 | +0.0165 | -0.0581 | +0.0931 |
| 43 | SCREEN-FAIL | 855 | -0.0670 | -0.1478 | +0.0115 |
| 44 | SCREEN-FAIL | 821 | -0.0396 | -0.1245 | +0.0478 |
| 45 | SCREEN-FAIL | 907 | -0.1017 | -0.1685 | -0.0332 |
| 46 | SCREEN-FAIL | 880 | -0.0843 | -0.1551 | -0.0122 |
| 47 | SCREEN-FAIL | 927 | -0.0677 | -0.1373 | +0.0043 |
| 48 | SCREEN-FAIL | 898 | -0.1203 | -0.1874 | -0.0519 |
| 49 | SCREEN-FAIL | 953 | -0.0933 | -0.1594 | -0.0286 |
| 50 | SCREEN-FAIL | 911 | -0.0991 | -0.1645 | -0.0342 |
| 51 | SCREEN-FAIL | 930 | -0.0887 | -0.1555 | -0.0232 |
| 52 | SCREEN-FAIL | 908 | -0.0723 | -0.1463 | +0.0006 |
| 53 | SCREEN-FAIL | 926 | -0.1604 | -0.2265 | -0.0935 |
| 54 | SCREEN-FAIL | 872 | -0.0770 | -0.1501 | -0.0022 |
| 55 | SCREEN-FAIL | 909 | -0.0325 | -0.1008 | +0.0359 |
| 56 | SCREEN-FAIL | 942 | -0.0187 | -0.0918 | +0.0565 |
| 57 | SCREEN-FAIL | 879 | -0.1340 | -0.2057 | -0.0604 |
| 58 | SCREEN-FAIL | 901 | -0.0311 | -0.1028 | +0.0422 |
| 59 | SCREEN-FAIL | 867 | -0.1245 | -0.1961 | -0.0510 |
| 60 | SCREEN-FAIL | 926 | -0.0693 | -0.1445 | +0.0035 |
| 61 | SCREEN-FAIL | 941 | -0.0818 | -0.1506 | -0.0135 |
| 62 | SCREEN-FAIL | 932 | -0.0742 | -0.1388 | -0.0087 |
| 63 | SCREEN-FAIL | 948 | -0.0920 | -0.1562 | -0.0255 |
| 64 | SCREEN-FAIL | 873 | -0.0434 | -0.1152 | +0.0298 |
| 65 | SCREEN-FAIL | 885 | -0.0759 | -0.1435 | -0.0069 |
| 66 | SCREEN-FAIL | 891 | +0.0034 | -0.0682 | +0.0751 |
| 67 | SCREEN-FAIL | 907 | -0.0998 | -0.1686 | -0.0285 |
| 68 | SCREEN-FAIL | 928 | -0.0839 | -0.1552 | -0.0127 |
| 69 | SCREEN-FAIL | 923 | -0.1510 | -0.2205 | -0.0803 |
| 70 | SCREEN-FAIL | 872 | -0.0494 | -0.1235 | +0.0274 |
| 71 | SCREEN-FAIL | 873 | -0.0924 | -0.1647 | -0.0209 |
| 72 | SCREEN-FAIL | 934 | -0.0588 | -0.1315 | +0.0115 |
| 73 | SCREEN-FAIL | 917 | -0.1734 | -0.2397 | -0.1050 |
| 74 | SCREEN-FAIL | 897 | -0.0316 | -0.1145 | +0.0560 |
| 75 | SCREEN-FAIL | 889 | -0.0561 | -0.1250 | +0.0137 |
| 76 | SCREEN-FAIL | 936 | -0.1466 | -0.2126 | -0.0789 |
| 77 | SCREEN-FAIL | 866 | -0.1001 | -0.1699 | -0.0276 |
| 78 | SCREEN-FAIL | 907 | -0.0451 | -0.1146 | +0.0241 |
| 79 | SCREEN-FAIL | 932 | +0.0035 | -0.0691 | +0.0771 |
| 80 | SCREEN-FAIL | 922 | -0.0720 | -0.1422 | -0.0017 |
| 81 | SCREEN-FAIL | 912 | -0.0907 | -0.1627 | -0.0201 |
| 82 | SCREEN-FAIL | 893 | -0.1024 | -0.1753 | -0.0270 |
| 83 | SCREEN-FAIL | 927 | -0.1017 | -0.1730 | -0.0294 |
| 84 | SCREEN-FAIL | 886 | -0.0812 | -0.1567 | -0.0061 |
| 85 | SCREEN-FAIL | 901 | -0.0158 | -0.0811 | +0.0497 |
| 86 | SCREEN-FAIL | 893 | -0.0217 | -0.0931 | +0.0482 |
| 87 | SCREEN-FAIL | 910 | -0.0551 | -0.1206 | +0.0117 |
| 88 | SCREEN-FAIL | 915 | -0.1108 | -0.1842 | -0.0379 |
| 89 | SCREEN-FAIL | 887 | -0.0729 | -0.1443 | -0.0015 |
| 90 | SCREEN-FAIL | 916 | -0.0518 | -0.1211 | +0.0207 |
| 91 | SCREEN-FAIL | 875 | -0.0492 | -0.1237 | +0.0270 |
| 92 | SCREEN-FAIL | 922 | -0.1577 | -0.2228 | -0.0884 |
| 93 | SCREEN-FAIL | 874 | -0.1134 | -0.1880 | -0.0398 |
| 94 | SCREEN-FAIL | 888 | -0.1223 | -0.1891 | -0.0552 |
| 95 | SCREEN-FAIL | 909 | -0.1029 | -0.1729 | -0.0342 |
| 96 | SCREEN-FAIL | 934 | -0.0399 | -0.1142 | +0.0357 |
| 97 | SCREEN-FAIL | 934 | -0.0753 | -0.1486 | -0.0012 |
| 98 | SCREEN-FAIL | 954 | -0.0389 | -0.1043 | +0.0287 |
| 99 | SCREEN-FAIL | 903 | -0.0556 | -0.1264 | +0.0139 |
| 100 | SCREEN-FAIL | 904 | -0.1212 | -0.1894 | -0.0531 |
| 101 | SCREEN-FAIL | 954 | -0.0215 | -0.0906 | +0.0480 |
| 102 | SCREEN-FAIL | 866 | -0.0564 | -0.1337 | +0.0193 |
| 103 | SCREEN-FAIL | 921 | -0.1278 | -0.1998 | -0.0559 |
| 104 | SCREEN-FAIL | 928 | -0.0764 | -0.1485 | -0.0046 |
| 105 | SCREEN-FAIL | 920 | -0.0861 | -0.1506 | -0.0235 |
| 106 | SCREEN-FAIL | 942 | -0.0919 | -0.1579 | -0.0268 |
| 107 | SCREEN-FAIL | 911 | -0.1076 | -0.1764 | -0.0372 |
| 108 | SCREEN-FAIL | 906 | -0.1381 | -0.2043 | -0.0684 |
| 109 | SCREEN-FAIL | 917 | -0.0234 | -0.0955 | +0.0494 |
| 110 | SCREEN-FAIL | 909 | -0.0935 | -0.1635 | -0.0241 |
| 111 | SCREEN-FAIL | 930 | -0.0894 | -0.1585 | -0.0223 |
| 112 | SCREEN-FAIL | 902 | -0.0441 | -0.1188 | +0.0325 |
| 113 | SCREEN-FAIL | 927 | -0.0920 | -0.1662 | -0.0174 |
| 114 | SCREEN-FAIL | 884 | -0.0315 | -0.1039 | +0.0407 |
| 115 | SCREEN-FAIL | 935 | -0.0550 | -0.1281 | +0.0189 |
| 116 | SCREEN-FAIL | 922 | -0.0596 | -0.1343 | +0.0144 |
| 117 | SCREEN-FAIL | 920 | -0.0197 | -0.0991 | +0.0580 |
| 118 | SCREEN-FAIL | 903 | -0.1054 | -0.1782 | -0.0333 |
| 119 | SCREEN-FAIL | 904 | -0.0929 | -0.1641 | -0.0224 |
| 120 | SCREEN-FAIL | 893 | -0.0855 | -0.1618 | -0.0125 |
| 121 | SCREEN-FAIL | 871 | -0.0171 | -0.0921 | +0.0581 |
| 122 | SCREEN-FAIL | 932 | -0.0880 | -0.1505 | -0.0242 |
| 123 | SCREEN-FAIL | 886 | -0.0790 | -0.1497 | -0.0072 |
| 124 | SCREEN-FAIL | 968 | -0.0983 | -0.1701 | -0.0278 |
| 125 | SCREEN-FAIL | 898 | -0.0879 | -0.1551 | -0.0187 |
| 126 | SCREEN-FAIL | 913 | -0.0955 | -0.1647 | -0.0217 |
| 127 | SCREEN-FAIL | 898 | -0.0498 | -0.1182 | +0.0198 |
| 128 | SCREEN-FAIL | 894 | -0.0418 | -0.1099 | +0.0254 |
| 129 | SCREEN-FAIL | 899 | -0.0957 | -0.1620 | -0.0314 |
| 130 | SCREEN-FAIL | 967 | -0.0953 | -0.1635 | -0.0274 |
| 131 | SCREEN-FAIL | 955 | -0.0887 | -0.1618 | -0.0132 |
| 132 | SCREEN-FAIL | 916 | -0.0363 | -0.1084 | +0.0338 |
| 133 | SCREEN-FAIL | 912 | -0.0279 | -0.0984 | +0.0430 |
| 134 | SCREEN-FAIL | 892 | -0.0186 | -0.0892 | +0.0547 |
| 135 | SCREEN-FAIL | 914 | -0.0494 | -0.1172 | +0.0196 |
| 136 | SCREEN-FAIL | 921 | -0.0156 | -0.0924 | +0.0596 |
| 137 | SCREEN-FAIL | 922 | -0.0989 | -0.1702 | -0.0244 |
| 138 | SCREEN-FAIL | 894 | -0.0401 | -0.1085 | +0.0305 |
| 139 | SCREEN-FAIL | 884 | -0.0563 | -0.1272 | +0.0156 |
| 140 | SCREEN-FAIL | 890 | -0.0033 | -0.0725 | +0.0687 |
| 141 | SCREEN-FAIL | 920 | -0.1282 | -0.2011 | -0.0576 |
| 142 | SCREEN-FAIL | 942 | -0.0946 | -0.1601 | -0.0287 |
| 143 | SCREEN-FAIL | 934 | -0.0561 | -0.1208 | +0.0087 |
| 144 | SCREEN-FAIL | 933 | -0.0998 | -0.1699 | -0.0303 |
| 145 | SCREEN-FAIL | 955 | -0.0749 | -0.1406 | -0.0096 |
| 146 | SCREEN-FAIL | 888 | -0.1080 | -0.1809 | -0.0355 |
| 147 | SCREEN-FAIL | 912 | -0.0918 | -0.1614 | -0.0207 |
| 148 | SCREEN-FAIL | 914 | -0.0581 | -0.1280 | +0.0110 |
| 149 | SCREEN-FAIL | 881 | -0.0381 | -0.1095 | +0.0339 |
| 150 | SCREEN-FAIL | 904 | -0.0784 | -0.1473 | -0.0090 |
| 151 | SCREEN-FAIL | 972 | -0.0574 | -0.1257 | +0.0101 |
| 152 | SCREEN-FAIL | 916 | -0.0517 | -0.1245 | +0.0204 |
| 153 | SCREEN-FAIL | 933 | -0.1046 | -0.1757 | -0.0338 |
| 154 | SCREEN-FAIL | 929 | -0.0507 | -0.1178 | +0.0181 |
| 155 | SCREEN-FAIL | 906 | -0.0414 | -0.1106 | +0.0278 |
| 156 | SCREEN-FAIL | 918 | -0.0428 | -0.1109 | +0.0264 |
| 157 | SCREEN-FAIL | 852 | -0.0729 | -0.1496 | +0.0035 |
| 158 | SCREEN-FAIL | 949 | -0.1058 | -0.1741 | -0.0366 |
| 159 | SCREEN-FAIL | 917 | -0.0297 | -0.0976 | +0.0393 |
| 160 | SCREEN-FAIL | 882 | -0.0699 | -0.1406 | +0.0012 |
| 161 | SCREEN-FAIL | 916 | -0.0423 | -0.1139 | +0.0298 |
| 162 | SCREEN-FAIL | 915 | -0.0541 | -0.1233 | +0.0143 |
| 163 | SCREEN-FAIL | 869 | -0.0900 | -0.1616 | -0.0191 |
| 164 | SCREEN-FAIL | 880 | -0.1178 | -0.1940 | -0.0428 |
| 165 | SCREEN-FAIL | 896 | -0.0285 | -0.1001 | +0.0447 |
| 166 | SCREEN-FAIL | 890 | -0.0603 | -0.1378 | +0.0195 |
| 167 | SCREEN-FAIL | 923 | -0.0823 | -0.1517 | -0.0121 |
| 168 | SCREEN-FAIL | 902 | -0.1084 | -0.1756 | -0.0413 |
| 169 | SCREEN-FAIL | 898 | -0.0092 | -0.0851 | +0.0727 |
| 170 | SCREEN-FAIL | 903 | -0.1015 | -0.1716 | -0.0300 |
| 171 | SCREEN-FAIL | 954 | -0.1207 | -0.1905 | -0.0499 |
| 172 | SCREEN-FAIL | 935 | -0.0734 | -0.1418 | -0.0022 |
| 173 | SCREEN-FAIL | 914 | -0.0657 | -0.1373 | +0.0050 |
| 174 | SCREEN-FAIL | 933 | -0.0638 | -0.1363 | +0.0136 |
| 175 | SCREEN-FAIL | 884 | -0.0920 | -0.1624 | -0.0174 |
| 176 | SCREEN-FAIL | 880 | -0.0840 | -0.1501 | -0.0171 |
| 177 | SCREEN-FAIL | 935 | -0.0366 | -0.1072 | +0.0330 |
| 178 | SCREEN-FAIL | 883 | -0.0691 | -0.1490 | +0.0083 |
| 179 | SCREEN-FAIL | 894 | -0.0411 | -0.1104 | +0.0265 |
| 180 | SCREEN-FAIL | 920 | -0.0150 | -0.0952 | +0.0653 |
| 181 | SCREEN-FAIL | 899 | -0.0523 | -0.1317 | +0.0281 |
| 182 | SCREEN-FAIL | 863 | -0.0462 | -0.1209 | +0.0275 |
| 183 | SCREEN-FAIL | 920 | -0.0803 | -0.1559 | -0.0029 |
| 184 | SCREEN-FAIL | 914 | -0.0664 | -0.1358 | +0.0046 |
| 185 | SCREEN-FAIL | 921 | -0.0777 | -0.1438 | -0.0104 |
| 186 | SCREEN-FAIL | 871 | -0.2000 | -0.2783 | -0.1220 |
| 187 | SCREEN-FAIL | 874 | -0.0035 | -0.0788 | +0.0705 |
| 188 | SCREEN-FAIL | 906 | -0.0432 | -0.1183 | +0.0337 |
| 189 | SCREEN-FAIL | 928 | -0.0550 | -0.1245 | +0.0140 |
| 190 | SCREEN-FAIL | 967 | -0.0900 | -0.1591 | -0.0177 |
| 191 | SCREEN-FAIL | 882 | -0.0824 | -0.1532 | -0.0123 |
| 192 | SCREEN-FAIL | 926 | -0.0260 | -0.0966 | +0.0471 |
| 193 | SCREEN-FAIL | 928 | -0.0456 | -0.1175 | +0.0298 |
| 194 | SCREEN-FAIL | 884 | -0.0736 | -0.1456 | +0.0024 |
| 195 | SCREEN-FAIL | 934 | -0.1255 | -0.1959 | -0.0555 |
| 196 | SCREEN-FAIL | 929 | -0.0974 | -0.1660 | -0.0272 |
| 197 | SCREEN-FAIL | 907 | -0.0845 | -0.1550 | -0.0130 |
| 198 | SCREEN-FAIL | 952 | +0.0062 | -0.0600 | +0.0725 |
| 199 | SCREEN-FAIL | 895 | -0.0989 | -0.1658 | -0.0310 |
