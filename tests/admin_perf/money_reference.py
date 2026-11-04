"""Hand-computed account-currency (EUR) money of the golden book (v205 V205-4b).

Never computed through fx_convert. Today's rule (fx.py `_close_on_or_before`,
fx_convert `_day`): the rate is the last positive USDEUR=X close ON or before the
UTC date of the amount's stamp; an open position converts at `date.today()`
(frozen: 2026-11-04). Rounded to cents per leg, then the sum rounded.
V205-15 and V205-16 change these values, each with its arithmetic, never the goldens.
"""
from tests.admin_perf.golden_book import ENDPOINTS

T1_SAP_WIN = 120.00       # EUR quote: no conversion
T2_AAPL_WIN = 43.50       # 50.00 x 0.8700 (close 2026-11-03; exit 2026-11-03 20:30 UTC)
T3_AAPL_LOSS = -26.04     # -30.00 x 0.8680 (close 2026-11-02; exit 2026-11-02 23:30 UTC)
T4_LEG1 = 43.25           # 50.00 x 0.8650 (close 2026-10-29)
T4_LEG2 = 17.36           # 20.00 x 0.8680 (close 2026-11-02)
T4_TOTAL = 60.61          # round(43.25 + 17.36, 2)
T5_OPEN_AAPL = 34.88      # 40.00 x 0.8720 (close 2026-11-04, the frozen date.today())
T6_OPEN_SAP = 60.00       # EUR quote: no conversion
DAY_2026_11_02 = -8.68    # T3 + T4 leg 2 = -26.04 + 17.36 (the Calendar buckets closed_at[:10])
DAY_2026_11_03 = 163.50   # T1 + T2 = 120.00 + 43.50
MONTH_2026_11 = 154.82    # -8.68 + 163.50
T4_TRADES_ROW = 60.76     # 70.00 x 0.8680: /trades converts T4's whole amount at closed_at (2026-11-02),
                          # not per leg (T4_TOTAL); V205-15/16 decide which rule stands
VS_AVG_DAY_2026_11_03 = 146.22  # 163.50 - (43.25 + -8.68) / 2 = 163.50 - 17.285 -> cents
                                # (the day vs the mean of the book's other trading days, 10-29 and 11-02)

#: endpoint name -> JSON pointer -> hand-computed value. Exactly the FX-sensitive
#: pointers (test_money_pointers_are_exactly_the_fx_sensitive_fields).
EXPECTED_MONEY: dict[str, dict[str, float | None]] = {
    "dashboard": {
        "/open_pnl_amount": round(T5_OPEN_AAPL + T6_OPEN_SAP, 2),     # 34.88 + 60.00 = 94.88
    },
    "dashboard_today": {
        "/open_pnl_amount": round(T5_OPEN_AAPL + T6_OPEN_SAP, 2),     # 34.88 + 60.00 = 94.88
    },
    "trades": {
        "/items/0/realized_pnl_amount": T5_OPEN_AAPL,      # T5 open: 40.00 x 0.8720
        "/items/2/realized_pnl_amount": T2_AAPL_WIN,       # 50.00 x 0.8700
        "/items/3/realized_pnl_amount": T3_AAPL_LOSS,      # -30.00 x 0.8680
        "/items/4/realized_pnl_amount": T4_TRADES_ROW,     # 70.00 x 0.8680
    },
    "trades_open": {
        "/items/0/realized_pnl_amount": T5_OPEN_AAPL,      # T5 open: 40.00 x 0.8720
    },
    "live": {},
    "calendar_month": {
        "/best_day/net_pnl_amount": DAY_2026_11_03,                          # 120.00 + 43.50
        "/worst_day/net_pnl_amount": DAY_2026_11_02,                         # -26.04 + 17.36
        "/days/0/net_pnl_amount": DAY_2026_11_02,                            # 2026-11-02
        "/days/1/net_pnl_amount": DAY_2026_11_03,                            # 2026-11-03
        "/totals/net_pnl_amount": MONTH_2026_11,                             # -8.68 + 163.50
        "/day_of_week/0/avg_pnl_amount": (T3_AAPL_LOSS + T4_LEG2) / 2,       # Mon: (-26.04 + 17.36) / 2 = -4.34
        "/day_of_week/1/avg_pnl_amount": (T1_SAP_WIN + T2_AAPL_WIN) / 2,     # Tue: (120.00 + 43.50) / 2 = 81.75
        "/day_of_week/3/avg_pnl_amount": T4_LEG1,                            # Thu 2026-10-29: 50.00 x 0.8650
    },
    "calendar_day": {
        "/total_ccy": DAY_2026_11_03,                                # 120.00 + 43.50
        "/breakdown/direction/0/pnl_amount": DAY_2026_11_03,         # bullish: T1 + T2
        "/breakdown/exit_reason/0/pnl_amount": DAY_2026_11_03,       # other: T1 + T2
        "/breakdown/horizon/0/pnl_amount": DAY_2026_11_03,           # 4w: T1 + T2
        "/breakdown/strategy/0/pnl_amount": DAY_2026_11_03,          # S/R Confluence: T1 + T2
        "/context/vs_avg_day/pnl_amount": VS_AVG_DAY_2026_11_03,     # 163.50 - 17.285
        "/contributors/1/pnl": T2_AAPL_WIN,                          # AAPL: 50.00 x 0.8700
        "/trades/1/pnl_amount": T2_AAPL_WIN,                         # golden-t2-usd-win
    },
    "calendar_sparklines": {},
}
assert set(EXPECTED_MONEY) == set(ENDPOINTS), "EXPECTED_MONEY must name every profiled endpoint"
