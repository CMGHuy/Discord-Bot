"""Hand-computed account-currency (EUR) money of the golden book (v205 V205-4b).

Never computed through fx_convert. V205-15's rule: the rate for day D is the
fx_daily_rates row for D (golden_book.FX_DAILY_ROWS: the last positive USDEUR=X
close dated strictly before D), D being the UTC date of the amount's stamp
(fx_convert._day; V205-16 moves it to the Berlin date); an open position
converts at the frozen date.today() (2026-11-04). Rounded to cents per leg, then
the sum rounded.
V205-15 and V205-16 change these values, each with its arithmetic, never the goldens.
"""
from tests.admin_perf.golden_book import ENDPOINTS

T1_SAP_WIN = 120.00       # EUR quote: no conversion
T2_AAPL_WIN = 43.40       # 50.00 x 0.8680 (row 2026-11-03: close 2026-11-02; exit 2026-11-03 20:30 UTC)
T3_AAPL_LOSS = -25.92     # -30.00 x 0.8640 (row 2026-11-02: close 2026-10-30; exit 2026-11-02 23:30 UTC)
T4_LEG1 = 43.10           # 50.00 x 0.8620 (row 2026-10-29: close 2026-10-27, the 10-28 close is 0.0)
T4_LEG2 = 17.28           # 20.00 x 0.8640 (row 2026-11-02: close 2026-10-30)
T4_TOTAL = 60.38          # round(43.10 + 17.28, 2)
T5_OPEN_AAPL = 34.80      # 40.00 x 0.8700 (row 2026-11-04, the frozen date.today())
T6_OPEN_SAP = 60.00       # EUR quote: no conversion
DAY_2026_11_02 = -8.64    # T3 + T4 leg 2 = -25.92 + 17.28 (the Calendar buckets closed_at[:10])
DAY_2026_11_03 = 163.40   # T1 + T2 = 120.00 + 43.40
MONTH_2026_11 = 154.76    # -8.64 + 163.40
T4_TRADES_ROW = 60.48     # 70.00 x 0.8640 (row 2026-11-02: close 2026-10-30): /trades converts T4's
                          # whole amount at closed_at (2026-11-02), not per leg (T4_TOTAL);
                          # V205-16 decides which rule stands
VS_AVG_DAY_2026_11_03 = 146.17  # 163.40 - (43.10 + -8.64) / 2 = 163.40 - 17.23
                                # (the day vs the mean of the book's other trading days, 10-29 and 11-02)

#: endpoint name -> JSON pointer -> hand-computed value. Exactly the FX-sensitive
#: pointers (test_money_pointers_are_exactly_the_fx_sensitive_fields).
EXPECTED_MONEY: dict[str, dict[str, float | None]] = {
    "dashboard": {
        "/open_pnl_amount": round(T5_OPEN_AAPL + T6_OPEN_SAP, 2),     # 34.80 + 60.00 = 94.80
    },
    "dashboard_today": {
        "/open_pnl_amount": round(T5_OPEN_AAPL + T6_OPEN_SAP, 2),     # 34.80 + 60.00 = 94.80
    },
    "trades": {
        "/items/0/realized_pnl_amount": T5_OPEN_AAPL,      # T5 open: 40.00 x 0.8700
        "/items/2/realized_pnl_amount": T2_AAPL_WIN,       # 50.00 x 0.8680
        "/items/3/realized_pnl_amount": T3_AAPL_LOSS,      # -30.00 x 0.8640
        "/items/4/realized_pnl_amount": T4_TRADES_ROW,     # 70.00 x 0.8640
    },
    "trades_open": {
        "/items/0/realized_pnl_amount": T5_OPEN_AAPL,      # T5 open: 40.00 x 0.8700
    },
    "live": {},
    "calendar_month": {
        "/best_day/net_pnl_amount": DAY_2026_11_03,                          # 120.00 + 43.40
        "/worst_day/net_pnl_amount": DAY_2026_11_02,                         # -25.92 + 17.28
        "/days/0/net_pnl_amount": DAY_2026_11_02,                            # 2026-11-02
        "/days/1/net_pnl_amount": DAY_2026_11_03,                            # 2026-11-03
        "/totals/net_pnl_amount": MONTH_2026_11,                             # -8.64 + 163.40
        "/day_of_week/0/avg_pnl_amount": (T3_AAPL_LOSS + T4_LEG2) / 2,       # Mon: (-25.92 + 17.28) / 2 = -4.32
        "/day_of_week/1/avg_pnl_amount": (T1_SAP_WIN + T2_AAPL_WIN) / 2,     # Tue: (120.00 + 43.40) / 2 = 81.70
        "/day_of_week/3/avg_pnl_amount": T4_LEG1,                            # Thu 2026-10-29: 50.00 x 0.8620
    },
    "calendar_day": {
        "/total_ccy": DAY_2026_11_03,                                # 120.00 + 43.40
        "/breakdown/direction/0/pnl_amount": DAY_2026_11_03,         # bullish: T1 + T2
        "/breakdown/exit_reason/0/pnl_amount": DAY_2026_11_03,       # other: T1 + T2
        "/breakdown/horizon/0/pnl_amount": DAY_2026_11_03,           # 4w: T1 + T2
        "/breakdown/strategy/0/pnl_amount": DAY_2026_11_03,          # S/R Confluence: T1 + T2
        "/context/vs_avg_day/pnl_amount": VS_AVG_DAY_2026_11_03,     # 163.40 - 17.23
        "/contributors/1/pnl": T2_AAPL_WIN,                          # AAPL: 50.00 x 0.8680
        "/trades/1/pnl_amount": T2_AAPL_WIN,                         # golden-t2-usd-win
    },
    "calendar_sparklines": {},
}
assert set(EXPECTED_MONEY) == set(ENDPOINTS), "EXPECTED_MONEY must name every profiled endpoint"
