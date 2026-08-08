== REGIME_ALLOW evidence | TRAIN 2020-01-01..2023-12-31 | 78 tickers x 11 strategies x 10 horizons ==

Pre-registered rule: deny (strategy, regime) iff N>=30 AND expectancy_r<0 AND negative in >=3 of 4 sub-folds (a sub-fold with N<30 counts as 'not negative').
Selection is on expectancy. Win rate is reported, never selected on.

Strategy               Regime               N     ExpR   Win%  Folds-  fold N (- = negative & N>=30)     DENY
-------------------------------------------------------------------------------------------------------------
EMA Crossover          bull_quiet          34   -0.115   66.7       0  2020:13. 2021:7. 2022:1. 2023:13.      
EMA Crossover          bull_volatile       22   +0.177   94.4       0  2020:15. 2021:3. 2022:4. 2023:0.      
EMA Crossover          bear_quiet           3   +0.067  100.0       0  2020:0. 2021:0. 2022:0. 2023:3.       
EMA Crossover          bear_volatile       31   +0.152   95.2       0  2020:4. 2021:0. 2022:27. 2023:0.      
VWAP                   bull_quiet         174   -0.036   75.2       1  2020:29. 2021:86. 2022:2. 2023:57-      
VWAP                   bull_volatile       49   -0.016   76.3       0  2020:16. 2021:12. 2022:15. 2023:6.      
VWAP                   bear_quiet          18   +0.078   85.7       0  2020:0. 2021:0. 2022:11. 2023:7.      
VWAP                   bear_volatile       24   -0.028   75.0       0  2020:3. 2021:0. 2022:21. 2023:0.      
Fibonacci              bull_quiet         334   +0.027   78.5       1  2020:52. 2021:186- 2022:1. 2023:95.      
Fibonacci              bull_volatile       83   -0.093   65.5       1  2020:28. 2021:23. 2022:31- 2023:1.      
Fibonacci              bear_quiet          28   +0.149   90.0       0  2020:0. 2021:0. 2022:13. 2023:15.      
Fibonacci              bear_volatile       58   -0.022   73.5       1  2020:18. 2021:0. 2022:40- 2023:0.      
Support/Resistance     bull_quiet         298   +0.070   87.6       1  2020:74. 2021:128. 2022:4. 2023:92-      
Support/Resistance     bull_volatile       78   -0.066   70.4       1  2020:41- 2021:14. 2022:23. 2023:0.      
Support/Resistance     bear_quiet          11   -0.054   71.4       0  2020:0. 2021:0. 2022:5. 2023:6.       
Support/Resistance     bear_volatile       12   -0.048   72.7       0  2020:4. 2021:0. 2022:8. 2023:0.       
RSI                    bull_quiet          20   +0.164  100.0       0  2020:10. 2021:0. 2022:0. 2023:10.      
RSI                    bull_volatile       30   +0.308   96.7       0  2020:10. 2021:0. 2022:20. 2023:0.      
RSI                    bear_quiet           0       --     --       0  2020:0. 2021:0. 2022:0. 2023:0.       
RSI                    bear_volatile       20   +0.102   90.9       0  2020:0. 2021:0. 2022:20. 2023:0.      
MACD                   bull_quiet         207   +0.087   87.2       0  2020:29. 2021:122. 2022:1. 2023:55.      
MACD                   bull_volatile       74   -0.018   76.5       0  2020:32. 2021:16. 2022:26. 2023:0.      
MACD                   bear_quiet           8   +0.083  100.0       0  2020:0. 2021:0. 2022:1. 2023:7.       
MACD                   bear_volatile       33   -0.032   75.0       0  2020:7. 2021:0. 2022:26. 2023:0.      
Elliott Wave           bull_quiet          84   +0.029   81.6       0  2020:21. 2021:37. 2022:3. 2023:23.      
Elliott Wave           bull_volatile       26   -0.141   63.2       0  2020:16. 2021:2. 2022:8. 2023:0.      
Elliott Wave           bear_quiet           6   -0.249   50.0       0  2020:0. 2021:0. 2022:2. 2023:4.       
Elliott Wave           bear_volatile       31   +0.006   78.9       0  2020:3. 2021:0. 2022:28. 2023:0.      
MA Ribbon              bull_quiet         280   +0.025   81.3       1  2020:39. 2021:138- 2022:0. 2023:103.      
MA Ribbon              bull_volatile      108   +0.028   81.8       0  2020:49. 2021:24. 2022:23. 2023:12.      
MA Ribbon              bear_quiet          42   +0.200  100.0       0  2020:0. 2021:0. 2022:20. 2023:22.      
MA Ribbon              bear_volatile       32   +0.051   83.3       0  2020:4. 2021:0. 2022:28. 2023:0.      
Break & Retest         bull_quiet         489   -0.018   77.5       1  2020:78. 2021:215- 2022:5. 2023:191.      
Break & Retest         bull_volatile      170   +0.013   80.7       1  2020:71- 2021:56. 2022:24. 2023:19.      
Break & Retest         bear_quiet          41   -0.131   65.6       1  2020:0. 2021:0. 2022:30- 2023:11.      
Break & Retest         bear_volatile       56   +0.035   82.9       0  2020:7. 2021:0. 2022:49. 2023:0.      
RSI Divergence         bull_quiet        1710   -0.036   72.2       2  2020:322- 2021:782. 2022:10. 2023:596-      
RSI Divergence         bull_volatile      563   +0.111   87.1       1  2020:341. 2021:102. 2022:110- 2023:10.      
RSI Divergence         bear_quiet         242   -0.267   49.2       2  2020:0. 2021:0. 2022:120- 2023:122-      
RSI Divergence         bear_volatile      383   -0.122   63.6       1  2020:20. 2021:0. 2022:363- 2023:0.      
Volume Profile         bull_quiet         130   -0.028   73.1       1  2020:19. 2021:68. 2022:3. 2023:40-      
Volume Profile         bull_volatile       31   -0.001   75.0       0  2020:14. 2021:6. 2022:8. 2023:3.      
Volume Profile         bear_quiet          14   +0.167   90.9       0  2020:0. 2021:0. 2022:8. 2023:6.       
Volume Profile         bear_volatile       15   -0.078   66.7       0  2020:4. 2021:0. 2022:11. 2023:0.      

REGIME_ALLOW: dict[str, tuple] = {}   # no cell cleared the rule

NO GATE JUSTIFIED. This is a legitimate recorded outcome, not a prompt
to loosen the thresholds and retry -- that is precisely what the
one-shot validation budget exists to prevent.
